<!-- file: cases/tombstone-failure-threshold-withMetricsRecording-failureThreshold--autonomous.md -->
# tombstone_failure_threshold (with tombstone_warn_threshold) — verification solution

| Field | Value |
|---|---|
| Entry pointer | `src/java/org/apache/cassandra/db/ReadCommand.java:639` |
| Pinned source | `cassandra-5.0.9` |
| Session / date | Claude Sonnet 5.5 (claude-sonnet-5-5), Claude Code CLI, 2026-10-26 |
| Estimate | `positive` (qualified): the per-read tombstone count is capped by `tombstone_failure_threshold` and tombstones are buffered on heap in the replica data response, so heap per read is bounded by roughly threshold x tombstone size. The bound is a count, not bytes, so it is loose. |
| Ground | — |

## A. Constraint trace

**A1. The constraint.** The entry line (`ReadCommand.java:639`, `if (tombstones < failureThreshold) metric.tombstoneWarnings.inc();`) only updates a metric inside the warn branch. The enforcing constraint is `tombstone_failure_threshold` (configuration entry, runtime-queried through `DatabaseDescriptor`), paired with `tombstone_warn_threshold`. Declared at `src/java/org/apache/cassandra/config/Config.java:534-535` (`public volatile int`): warn 1000, failure 100000 (fixed defaults, not derived); same in `conf/cassandra.yaml:1814-1815`. Unit: tombstones (count of tombstone cells/markers) per local read command. Set by yaml key, or at runtime through JMX `StorageServiceMBean` `setTombstoneWarnThreshold` / `setTombstoneFailureThreshold` (`service/StorageService.java:6714-6731`, `DatabaseDescriptor.java:2832-2849`). No restart is needed. Each `MetricRecording` reads both values when it is constructed (`ReadCommand.java:529-530`), so a change applies to the next read command.

**A2. What it caps.** Heap, indirectly. The quantity compared is `tombstones`, an int counter local to one `MetricRecording` (one local read command) (`ReadCommand.java:536-537`). The yaml comment (`conf/cassandra.yaml:1799-1807`) says tombstones are kept in memory to return to the coordinator and "can exhaust the server heap".

**A3. Mechanism.**
1. `executeLocally` (`ReadCommand.java:426`) wraps the merged, purge-filtered iterator with `withMetricsRecording` (`:461`).
2. `applyToRow` counts each non-live cell (`:556-562`) and primary-key-deletion rows (`:567-572`). `applyToMarker` counts every range tombstone marker (`:580-584`). `applyToStatic` also counts.
3. `countTombstone` (`:586`) increments `tombstones`. When `tombstones > failureThreshold && respectTombstoneThresholds` it traces, increments `metric.tombstoneFailures` and records the fail param when `trackWarnings` is set. It then throws `TombstoneOverwhelmingException` (`:594-601`), so the read aborts.
4. At `onClose` (`:620-651`), if `tombstones > warningThreshold` it logs and sends a client warning (or `MessageParams` when tracking). Line 639 increments `tombstoneWarnings` only when the count is below the failure threshold. This is metric bookkeeping and has no effect on memory.
5. Tombstones that pass the check are materialised: `ReadResponse.LocalDataResponse.build` (`db/ReadResponse.java:197-201`) serializes the whole iterator into a heap `DataOutputBuffer`. This is why the count bounds the response buffer.

Bypasses and overshoot:
- `respectTombstoneThresholds` is false for local system and virtual keyspaces (`:532`, `SchemaConstants.java:118`).
- The counter is per read command, so concurrent reads each get their own budget. The cap is per read, not per node.
- The check runs after `withoutPurgeableTombstones` (`:458`), so purgeable (gc_grace-expired) tombstones are not counted, although the sstable/memtable merge still reads them.
- Counting is by number, not size. Range-tombstone markers with large clustering values or cells with large values can make 100000 tombstones much bigger than the average.
- `liveRows` and the other rows in the response are not limited by this check (`local_read_size_*`, `withQuerySizeTracking` at `:663`, is separate).
- Tombstones read and merged before the counter sees them (merge heap, sstable read buffers) are not bounded by it.
- Setting the threshold to `Integer.MAX_VALUE` effectively disables the cap.

**A4. Other consumers.** Memtables, row/key/chunk/counter caches, bloom filters and index summaries, compaction, other concurrent reads and coordinator-side result buffers (the coordinator holds the same tombstones in its response merge). Per-read size limits: `local_read_size_warn/fail_threshold` (`ReadCommand.java:663`).

**A5. Evidence beyond the source.** `conf/cassandra.yaml:1799-1815` comment. CASSANDRA-6117 (introduced the thresholds), per the project issue tracker (not re-fetched in this session).

## B. Verification solution

**B1. Claim under test.** Lowering or raising `tombstone_failure_threshold` moves the peak heap that a single tombstone-heavy read holds on a replica roughly in proportion to the threshold, and a read that would exceed it fails instead of growing. If heap use per read stays flat as the threshold changes while the read succeeds or fails as expected, the cap does not govern memory.

### B2. Unit tier

**B2a. Environment and build.** Copy the tree to local disk (`rsync -a ~/cassandra-5.0.9/ /localdisk/c509/`), JDK 11, `ant jar` and `ant build-test` in the copy. Test class under `test/unit/org/apache/cassandra/db/` in the copy only. JVM: `-Xmx1g -Dcassandra.config=file:///localdisk/c509/test/conf/cassandra.yaml`.

**B2b. Knobs.** `DatabaseDescriptor.setTombstoneFailureThreshold(T)` with T in {1000, 10000, 100000}; warn threshold fixed at 500. Three values over two decades make a proportional relation visible.

**B2c. Workload.** Create keyspace `ks`, table `t (pk int, ck int, v text, primary key (pk, ck))`. Insert 120000 rows in partition 0 and delete each by clustering key (row tombstones) with `gc_grace_seconds` 864000 so none are purgeable; flush so they sit in an sstable. Run `SELECT * FROM ks.t WHERE pk = 0` as a local `ReadCommand` (`executeLocally`). Reachable: 120000 > 100000, so T=100000 trips; T=1000 and T=10000 trip earlier.

**B2d. Observables and instruments.** (a) Whether `TombstoneOverwhelmingException` is thrown and the `tombstones` count in its message. (b) `ColumnFamilyStore.metric.tombstoneFailures` and `tombstoneWarnings`. (c) Heap retained by the built `ReadResponse`: `ReadResponse.createDataResponse` then `serializedSize` or `ByteBuffer` size of the data response. Force GC (`System.gc()`) before and after and read `Runtime.totalMemory()-freeMemory()`. Cannot be observed directly: transient merge-heap garbage.

**B2e. Procedure.**
1. Build; start the test JVM.
2. Load the workload, flush.
3. For each T: set the threshold, run the read three times, record exception or response size, metrics, and retained heap.
4. Positive control: same table, `LIMIT` large on live rows (no deletes) with `local_read_size_fail_threshold` set to a small value, to show a known cap bound and move the response size.

**B2f. Predictions.** T=1000: abort after 1001 tombstones, no response. T=10000: abort after 10001. T=100000: abort after 100001 (table has 120000), `tombstoneFailures` +1 each time. Raising T above 120000 (extra run, T=200000): read succeeds, response size about 120000 x per-tombstone bytes (several MB). Counted tombstones at abort = T+1 exactly.

**B2g. Readings.**

| Observation | Meaning |
|---|---|
| Abort at T+1 for every T, response size grows with T when T > 120000 | Mechanism works as traced |
| Read succeeds with count above T | Claim wrong; the check is bypassed |
| Retained heap same for T=10000 and T=100000 on succeeding reads | Claim wrong for memory |
| Read aborts at T but no memory difference ever shows | Count enforced, memory relation not shown (not confirmed) |

**B2h. Controls.** Same data with `respectTombstoneThresholds` false (create the table in `system_distributed` or use a local system keyspace): no abort. A table with live rows only: no tombstone count. Repeat with GC forced to remove noise.

**Amendments to B2, stage-4 audit, 2026-10-26** (all made before run 1 of this tier; none depends on a reading).
- **A1 (B2a/B2b, paths and fixed settings).** `/localdisk/c509` and `rsync ~/cassandra-5.0.9` do not exist. The tree is made with `stage4-runtime-verification/copy-source.sh ~/s4-b10-tf-src` (never `cassandra/cassandra-5.0.9/`), the test class is `org.apache.cassandra.db.TombstoneFailureThresholdMetricsRecordingTest`, and the run is `ant testsome -Dtest.name=…` (forks a 1 GiB JVM, `build.xml:1153`); no `-Dcassandra.config` is needed because the tree's `test/conf/cassandra.yaml` is used. That yaml enables `local_read_size_*` and `row_index_read_size_*` at 8 MiB (`test/conf/cassandra.yaml:66-69`), a node default does not (`Config.java:526`, `read_thresholds_enabled = false`): the tombstone arms set `DatabaseDescriptor.setReadThresholdsEnabled(false)` and restore it afterwards. `DatabaseDescriptor` state is read in `@BeforeClass`, not in a static initialiser.
- **A2 (B2b/B2d/B2f, values and observables).** T takes the values {1000, 10000, 100000 (default), 120000 (= N), 200000, Integer.MAX_VALUE}; warn threshold 500 throughout. For T < N the read aborts and no `ReadResponse` exists, so "heap retained by the response" (B2d(c)) is empty for exactly the values that test the cap. Added observables, taken for every read: (d) bytes allocated by the reading thread, `com.sun.management.ThreadMXBean.getThreadAllocatedBytes`, median of 5 repetitions, written A(T); (e) the serialized response size for reads that succeed. The `System.gc()` retained-heap delta of B2d(c) is kept only as a secondary reading for succeeding reads. Sub-prediction added to B2f, about the entry line itself: `tombstoneWarnings` rises only for a read that completes with warn < count < T (`ReadCommand.java:639`): +5 at T = 200000 and T = MAX, +0 at T <= 100000 (aborts: count = T+1 is not < T) and +0 at T = 120000 (count = T). It is a metric and does not move memory. `tombstoneFailures` rises by exactly 5 per aborting T.
- **A3 (B2e step 4 and B2h, controls).** The `system_distributed` suggestion of B2h is invalid: `respectTombstoneThresholds` is false only for `system`, `system_schema` (`SchemaConstants.java:59-60`) and virtual keyspaces (`:118-121`), so `system_distributed` is respected, and a user table cannot be created in a local system keyspace. The "cap disengaged" arm is T = Integer.MAX_VALUE on the same data (the check runs but cannot fire). Positive control (a different cap binding on the same resource): a live-row partition pk 1 (`N_LIVE` = 30,000 rows with a 1 KB `v`, about 30 MB) read with `cmd.trackWarnings()` (`ReadCommand.java:253`) and `local_read_size_fail_threshold` = 1 MiB, `read_thresholds_enabled` true, against the same read with the threshold off: expect abort with `LocalReadSizeTooLargeException` and A well below the unrestricted A. Negative control: pk 1 read at every T of the sweep: no tombstone count, A flat.
- **A4 (B2g, decisive criteria; the original rows stay).** "Retained heap same for T=10000 and T=100000 on succeeding reads" cannot be tested as written, because both abort (N = 120000). Row 3 is read as the same-A relation over the aborting T (A(T) not increasing). Row 1 ("Abort at T+1 for every T, response size grows with T when T > 120000") is decided by these checks, all required: (c1) exception iff T < N, with count exactly T+1; (c2) A(T) strictly increasing over the aborting T values; (c3) A(1000) <= 0.10 x A(MAX) (the abort point is 0.8 % of the scan); (c4) A(120000), A(200000), A(MAX) each within +-10 % of A(MAX) and every succeeding read has N unfiltered items in its response; (c5) tombstone metrics as in A2; (c6) pk 1 flat, max/min of A <= 1.10. If c1 holds but A(1000) >= 0.5 x A(MAX): B2g row 3 (the abort does not save the allocation). If c1 holds and c3 or c2 fails short of that: Not confirmed (partial). If c1 fails: Not confirmed (no matching row); a read that succeeds with a count above T is B2g row 2. The positive control not moving (A of the 1 MiB-capped read within 20 % of the unrestricted one) invalidates the tier.

### B3. Cluster tier

**B3a. Environment and build.** One node (second optional), JDK 11, `ant jar` in the local copy, data, commitlog and hints on a local disk of known size (>= 20 GB free). `-Xms2g -Xmx2g`, `-XX:+HeapDumpOnOutOfMemoryError -XX:HeapDumpPath=/localdisk/dumps`. `num_tokens: 1`, `concurrent_reads: 4`.

**B3b. Knobs.** `tombstone_failure_threshold` in {10000, 100000, 1000000}, warn at 1000 (yaml, or JMX at runtime). Values span two decades and the largest may exhaust the 2 GB heap if concurrent.

**B3c. Workload.** Table as in B2c with a 200-byte `v`. Insert 1.2M rows into one partition, delete all (cqlsh/`cassandra-stress` user profile), flush, keep `gc_grace_seconds` 864000. Then 8 concurrent clients run `SELECT * FROM ks.t WHERE pk=0` for 5 minutes per threshold value (partition-level scan reaches 1.2M tombstones, above every T). Also a size variant: delete with range tombstones whose clustering is 1 KB.

**B3d. Observables and instruments.** Heap used and old-gen after GC: `jcmd <pid> GC.heap_info`, `jstat -gcutil <pid> 1000`; peak via GC logs (`-Xlog:gc*`). Table metrics `TombstoneScannedHistogram`, `tombstoneFailures` (`nodetool tablestats`, JMX). `system.log` warning and error lines. Cannot be observed: per-request heap attribution (use heap dump class histogram for `DataOutputBuffer`/`BufferClustering`).

**B3e. Procedure.**
1. Start node; create schema; load and delete; flush; stop writes.
2. For each T (set through JMX `StorageService.setTombstoneFailureThreshold`): run the 8 clients for 5 minutes; sample `jstat` once a second; take one heap histogram (`jcmd GC.class_histogram`) mid-run; record failures count.
3. Positive control: repeat with `local_read_size_fail_threshold: 1MiB` on a live-row table of equal size.
4. Stop clients, `nodetool drain`, stop the node, check `pgrep -f CassandraDaemon`.

**B3f. Predictions.** T=10000: every read fails fast, peak heap rise small (about 10000 x about 100 B, about 1 MB per read, about 8 MB total). T=100000: about 10 MB per read, about 80 MB at 8 clients. T=1000000: about 100 MB per read or more (about 800 MB at 8 clients), approaching OOM risk on the 2 GB heap. Peak heap above baseline scales within a factor of 3 of linear in T. `tombstoneFailures` rises on every read at every T.

**B3g. Readings.**

| Observation | Meaning |
|---|---|
| Heap above baseline scales about linearly with T | Claim confirmed |
| Peak heap equal at 10000 and 1000000 | Claim wrong: not a memory cap |
| Reads at T=1000000 succeed with tombstones counted far above T | Cap bypassed, claim wrong |
| Heap grows with T but bytes per tombstone vary 10x between row and range variants | Cap bounds count, not bytes (loose cap) |
| Positive control does not move heap | Control invalid, no conclusion |

**B3h. Controls.** Same node and heap for every T; restart or full GC between runs; same data; client count fixed; warn threshold unchanged; the live-row control above.

**Amendments to B3, stage-4 audit, 2026-10-26** (before run 1 of this tier; none depends on a reading of this case).
- **A5 (B3a, environment).** `/localdisk` does not exist and several nodes share a host. The node is a single local node at loopback 127.0.1.1 (port slot 1): storage 7000, native 9042, JMX 7110, data/commitlog/hints/saved_caches on tmpfs `/dev/shm/s4-b10-tf`, logs and heap dumps (`-XX:HeapDumpPath`) under `~/s4-b10-tf-logs` (local disk, not `/proj`). Heap 2 GiB (`MAX_HEAP_SIZE=2G`, G1 as shipped), `num_tokens: 1`, `concurrent_reads: 4`, `read_request_timeout` 120000ms, `range_request_timeout` 120000ms, `native_transport_timeout` 180s, `read_thresholds_enabled` false for the tombstone lifetimes, `ulimit -n 100000` in the shell that starts the node. `jstat` cannot attach under the shipped `-XX:+PerfDisableSharedMem`; heap is sampled over JMX (G1 Eden/Old/Survivor used) every 250 ms instead of `jstat` once a second.
- **A6 (B3c, workload).** Table `ks.t (pk int, ck int, v text, PRIMARY KEY (pk, ck))`; pk 0 holds N = 1,200,000 row deletions written as `DELETE FROM ks.t WHERE pk = 0 AND ck = ?` in unlogged batches of 20 loaded with `cqlsh -f` (the preceding INSERT of the filed text is omitted: insert and delete in one memtable leave only the deletion in the flushed sstable, so the 200-byte `v` never reaches disk), flushed, `gc_grace_seconds` 864000. A "client" is a loop of `cqlsh -e "CONSISTENCY ONE; SELECT * FROM ks.t WHERE pk = 0;"` (default page size 100; a tombstone-only partition fills no page, so one page scans on to the threshold) with `--request-timeout=180`; 8 clients in parallel, each looping for 300 s per T. T takes {10000, 100000 (default), 1000000} through the yaml, one node lifetime per T (fresh JVM, so no carry-over heap), confirmed by JMX read-back. Size variant: table `ks.t2 (pk int, ck text, v text, PRIMARY KEY (pk, ck))`, pk 0 with 60,000 disjoint range deletions `ck > a AND ck < b` with 1000-character clusterings (120,000 markers, about 120 MB), read with ONE client, 3 repetitions, at T = 10000 and 100000 (8 clients at T = 100000 would hold 8 x 128 MiB or more in a 2 GiB heap). Control table `ks.live (pk int, ck int, v text)` with pk 0 = 30,000 rows of a 1 KB `v`, read with `PAGING OFF` (cqlsh's default 100-row pages make each page its own read command of about 110 KB, below any 1 MiB cap; found in a shakedown, not a reading) once per lifetime with thresholds off, and in one extra lifetime with `read_thresholds_enabled: true`, `local_read_size_fail_threshold: 1MiB` (positive control, known cap on the same resource).
- **A7 (B3d, observables and definitions; B3f/B3g rows stay).** Per T and arm: (i) outcome of every read from the client output (`ReadFailure` code `TOO_MANY_TOMBSTONES` vs success) and the `Scanned over T+1 tombstones` lines in `system.log`; (ii) `TombstoneFailures` (JMX table metric); (iii) per-read allocation A(T) = the node's allocated bytes during the storm (sum of `getThreadAllocatedBytes` over all threads, before and after) divided by the number of reads in it, after removing the node's background allocation (rate measured over the 30 s idle window with the same JMX polling running, times the storm's duration); this still includes a constant per request; (iv) the largest `DataOutputBuffer.expandToFit` allocation in a JFR recording (`settings=profile`), B(T), reported as a secondary reading only (a shakedown showed JFR does not sample allocations below the TLAB size, so B is unreliable below about 1 MiB); (v) node heap: P(T) = the peak of Eden + Old + Survivor used (JMX, 250 ms) over the storm minus the lowest value of that sum over the 30 s idle window and the storm together (a node that has not collected for a while shows an idle level above its post-GC floor, so an idle baseline alone can exceed the storm peak). Row "Heap above baseline scales about linearly with T" is decided by (b1) all reads fail with the tombstone code at every T, and the log lines read T+1; (b2) A(T) ratio between consecutive T values in [10/3, 30] (the "factor of 3" of B3f applied to a decade); (b3) P(10k) < P(100k) < P(1M) and each consecutive P ratio in [10/3, 30]. B3g gets a row, added here before any reading: **b1 and b2 hold and b3 fails (the node peak saturates)** is *Not confirmed (partial)*: the cap bounds each read, the node-level peak is not shown to follow it. A(10k) and A(1M) within 25 % of each other is the "equal" row. The size variant is compared with the row variant in B bytes per marker (T+1 markers per read): the 10x of the row "bytes per tombstone vary 10x". The positive control not lowering A (control A within 20 % of the unrestricted live read's A at the same T) is "control invalid".

**B4. Risks and cleanup.** Heap exhaustion at T=1000000 (heap dump up to 2 GB goes to local disk only). Data, commitlog, hints and dumps on local disk; delete `/localdisk/c509-data` and `/localdisk/dumps` afterwards. Stop all clients and nodes, confirm no `CassandraDaemon` or test JVM is left. No change to the shared source tree.

## C. Sources read

- /users/jason92/writeup-A/playbook-autonomous.md
- /users/jason92/writeup-A/_TEMPLATE-autonomous.md
- src/java/org/apache/cassandra/db/ReadCommand.java (lines 424-470, 515-670)
- src/java/org/apache/cassandra/db/ReadResponse.java (lines 182-210)
- src/java/org/apache/cassandra/config/Config.java (lines 534-535)
- src/java/org/apache/cassandra/config/DatabaseDescriptor.java (lines 2832-2849)
- src/java/org/apache/cassandra/service/StorageService.java (lines 6705-6732)
- src/java/org/apache/cassandra/schema/SchemaConstants.java (lines 118-121)
- conf/cassandra.yaml (lines 1795-1818)

## D. Stage-4 feedback

**2026-10-26 — run 1 closed: unit Confirmed — caps (per read); cluster Not confirmed (partial) — caps per read, node-level heap peak not shown** (the A7 row added by the audit before any reading; no run 2). Outcome class: undetermined. Results: [`results/tombstone-failure-threshold-withMetricsRecording-failureThreshold--autonomous.md`](../../stage4-runtime-verification/results/tombstone-failure-threshold-withMetricsRecording-failureThreshold--autonomous.md); harness `stage4-runtime-verification/harness/tombstone-failure-threshold-withMetricsRecording-failureThreshold--autonomous/`. Run on `pc07` (node0) from fresh copies `~/s4-b10-tf-src` (unit) and `~/s4-b10-tf-n` (cluster), port slot 1.

- **Unit (B2g row 1).** pk 0 with 120,000 row deletions aborts at exactly T+1 for T = 1000 / 10000 / 100000 (`tombstoneFailures` +5 each) and succeeds for T >= N with a constant 1,400,426-byte response (11.7 B per row tombstone). Allocation per read 0.68 · 6.53 · 54.73 MB at the three aborting T, 64.82 MB at T >= N (540-676 B per tombstone counted); A(1000)/A(MAX) = 0.0104. The live partition is flat (1.000) and the 1 MiB `local_read_size_fail_threshold` control aborts with 3.36 against 111.37 MB.
- **Cluster (A7 partial row).** 7,778 of 7,778 main reads (8 clients x 300 s at each T = 10000 / 100000 / 1000000) abort with `READ_TOO_MANY_TOMBSTONES` and the log counts are exactly T+1. Allocation per read 10.7 · 69.4 · 612.7 MB (6.5x and 8.8x per decade); the largest response buffer 0.13 · 2.0 · 16.0 MiB; the node's heap rise 1,262 · 1,258 · 1,817 MB (1.0x and 1.4x): the per-read measures follow T, the node-level peak does not. The B3f numbers all missed (a row tombstone is 11.7 B, not 100 B, so the buffer is about 8x smaller than predicted, and the allocation per read about 6x larger than the buffer alone would give). Size variant: 100,000 range markers with 1000-character clusterings give a 145 MiB buffer (72-129x the row tombstone), so the cap bounds the count and not the bytes. The 1 MiB read-size control moved usage (16.4 against 155.8 MB).
- **Defects in this file found by stage 4 (audit, applied above).** A1 paths and the test yaml's 8 MiB read thresholds; A2 the retained heap of an aborted read is empty, so allocation per read is the observable; A3 the `system_distributed` control is invalid (`SchemaConstants.java:59-60`); A4 B2g row 3 untestable as filed; A5-A7 cluster environment, workload and measurement definitions; A8 citations (`countTombstone` `:588`, failure branch `:591-601`, `onClose` `:622`). Shakedown findings: the live control needs `PAGING OFF`; JFR does not sample allocations below the TLAB size.
- **Not applied (left for stage 3).** S1 a held-heap reading (a held read plus a class histogram) would test the node-level sentence of B1; the `tombstoneWarnings` metric skips a read that completes with exactly T tombstones (`ReadCommand.java:639`, `<` not `<=`).
- **Effect.** The threshold caps each read command's response memory at about (T+1) x one tombstone's serialized size (1.4 MB at the default with row tombstones, 145 MiB with 1 KB range markers) and bounds the scan's allocation at about 600 B x (T+1). It does not cap the node's heap under concurrent tombstone-heavy reads: eight clients at the default already hold the heap at about 1.3 GB of 2 GiB, as at T = 10000.

**2026-10-26 — stage-4 audit (before run 1): Ready after amendments.** Amendments A1-A7 sit next to B2h and B3h above. A8, citation fixes (do not touch any prediction): `countTombstone` is `ReadCommand.java:588` (filed `:586`), its failure branch `:591-601` (filed `:594-601`), `onClose` starts at `:622` (filed `:620`), `applyToMarker` is `:582`; the entry pointer `:639` and the `MetricRecording` fields `:529-532` are right. Results: `stage4-runtime-verification/results/tombstone-failure-threshold-withMetricsRecording-failureThreshold--autonomous.md`. Pre-audit sha256 of this file: `c54919847c88774a1a4ff1b0658f91dbb40d592f880729937872b4feda3f5ac7`.
