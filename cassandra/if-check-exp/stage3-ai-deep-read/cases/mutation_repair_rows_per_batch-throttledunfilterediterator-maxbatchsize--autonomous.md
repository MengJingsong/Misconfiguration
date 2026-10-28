# Mutation-repair rows-per-batch opt-out (maxBatchSize == 0) — verification solution  <!-- file: cases/mutation_repair_rows_per_batch-throttledunfilterediterator-maxbatchsize--autonomous.md -->

| Field | Value |
|---|---|
| Entry pointer | [`ThrottledUnfilteredIterator.java:234`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/rows/ThrottledUnfilteredIterator.java#L234) |
| Pinned source | `cassandra-5.0.9` |
| Session / date | Claude Sonnet 5.5, Claude Code CLI (Agent SDK), 2026-10-27 |
| Estimate | `positive`: with a non-zero value the heap held per streamed Mutation is capped at about N unfiltereds per partition slice; 0 removes the cap, so one whole partition becomes one Mutation. |
| Ground | — |

**Type:** non-config (hard-coded constant: the literal `0` in the comparison; the compared value `maxBatchSize` also comes from the JVM property `cassandra.repair.mutation_repair_rows_per_batch`, so both are named)

## A. Constraint trace

**A1. The constraint.** `maxBatchSize` (rows/unfiltereds per batch), passed from `CassandraStreamReceiver`. Declared as JVM property [`REPAIR_MUTATION_REPAIR_ROWS_PER_BATCH`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/CassandraRelevantProperties.java#L410) (`cassandra.repair.mutation_repair_rows_per_batch`, default `"100"`), read once into the static final `MAX_ROWS_PER_BATCH` at `CassandraStreamReceiver.java:63`. Unit: unfiltereds (rows and range tombstone markers). Settable only with `-D` at JVM start (static final, needs restart); not in yaml, not JMX. The check also involves the numeric literal `0` (constant rule): `0` means "no throttle", the check is `maxBatchSize == 0`. Non-zero values must be greater than 1 (assert at `ThrottledUnfilteredIterator.java:64`; with assertions off, 1 or a negative value would misbehave, since `count < throttle` is never true after the first element or at all).

**A2. What it caps.** Heap. The number of Unfilteds from one partition that are put into one `PartitionUpdate`/`Mutation` (`CassandraStreamReceiver.java:212-222`) when received sstables go through the write path (CDC, MV, or `streamToMemtable`). The compared quantity is the per-batch `count` against `throttle` (`:148`).

**A3. Mechanism.** Enclosing method: static `throttle(UnfilteredPartitionIterator, int)` at [`ThrottledUnfilteredIterator.java:232`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/rows/ThrottledUnfilteredIterator.java#L232); the check is [`:234`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/rows/ThrottledUnfilteredIterator.java#L234).
- True (`0`): returns the raw `partitionIterator` (`:235`); each partition is returned whole, so `PartitionUpdate.fromIterator` (`CassandraStreamReceiver.java:218`) materializes the entire partition in heap as one Mutation.
- False: wraps each partition in `ThrottledUnfilteredIterator` (`:251`), which yields sub-iterators of at most `throttle` Unfilteds (`withinLimit`, `:146-149`), plus one extra close marker when a range tombstone is open at the boundary (`:139-143`, `:108`), so a batch can reach throttle+1 elements. Each batch becomes a separate Mutation applied via `ks.apply` (`CassandraStreamReceiver.java:218-221`).
- Only caller: `CassandraStreamReceiver.sendThroughWritePath` (`:212`), reached from `finished()` only when `requiresWritePath` (`:197-212` region: CDC-on-repair, `streamToMemtable`, or MV on repair). Plain sstable streaming never goes through it.
- Bypass/overshoot: the cap is per partition slice, not per stream; wide cells/large rows in a batch still make a batch big in bytes (limit counts rows, not bytes); the +1 close marker; whole-sstable streaming (no write path) is not covered.

**A4. Other consumers.** Memtable memory after `ks.apply` (memtable_heap_space/offheap), commit log, and the scanner/reader buffers and the partition-index/key cache for the sstable being scanned are outside this cap.

**A5. Evidence beyond the source.** Code comment at `CassandraStreamReceiver.java:209-211` ("avoid OOMing and generating heap pressure"); unit test `test/unit/org/apache/cassandra/db/rows/ThrottledUnfilteredIteratorTest.java:121-170` exercises `throttle(scanner, 100)` and `throttle(scanner, 0)`. No other sources consulted.

## B. Verification solution

**B1. Claim under test.** With `maxBatchSize` = N > 1, no Mutation built by the streaming write path holds more than about N+1 Unfilteds of a partition (heap per Mutation bounded by N); with `maxBatchSize` = 0, one Mutation holds the whole partition, and peak heap grows with partition size.

### B2. Unit tier

**B2a. Environment and build.** JDK 11, Ant. Copy the tag to a private directory (e.g. `~/w/cass-unit`), `ant jar` there; write a CQLTester-style test beside `ThrottledUnfilteredIteratorTest` in the copy (never in the shared tree). Run `ant testsome -Dtest.name=org.apache.cassandra.db.rows.ThrottledUnfilteredIteratorTest` with `-Xmx1g`.

**B2b. Knobs.** The `maxBatchSize` argument: 0, 2, 100, 1000 (direct call to `throttle`; the property itself is static final, so the argument is the knob here).

**B2c. Workload.** Table `(pk int, ck int, v text, PRIMARY KEY(pk, ck))`; insert 1 partition with 100000 rows of 100-byte values; flush; get a scanner on the sstable (`reader.getScanner()`).

**B2d. Observables and instruments.** For each batch returned: count Unfilteds iterated (the batch size); max over batches; number of batches. Heap per Mutation: `PartitionUpdate.fromIterator(...).dataSize()` / `unsharedHeapSize()`. Peak heap is not measured here.

**B2e. Procedure.** For each N: open scanner; `throttle(scanner, N)`; loop `next()`, build `PartitionUpdate.fromIterator(it, ColumnFilter.all(metadata))`, record `update.rowCount()` and `unsharedHeapSize()`; close.

**B2f. Predictions.** N=0: 1 batch, 100000 rows, size ~ whole partition (about 10 MB data). N=2: max rows per batch 2 or 3, ~50000 batches. N=100: max 100 (101 only if a tombstone is open; none here), 1000 batches. N=1000: max 1000, 100 batches. Max batch rows follows N; unsharedHeapSize per batch scales linearly with N.

**B2g. Readings.**

| Observation | Meaning |
|---|---|
| max rows per batch <= N+1 for N>1, and 1 batch with all rows for N=0 | claim confirmed |
| a batch with more than N+1 Unfilteds for N>1 | claim wrong (cap leaks) |
| N=0 still produces several batches | opt-out not working, claim wrong |
| Heap per batch not growing with N | row count not a proxy for heap here; check row size |

**B2h. Controls.** Same data and sstable for all N; repeat with rows of 10 B and 1000 B values to show bytes scale with rows x size; add a variant with an open range tombstone at the boundary to see the N+1 case.

> **Amendments to B2 (stage-4 audit, 2026-10-27, before the unit tier ran).** Citation fixes (no effect on the claim): `PartitionUpdate.fromIterator` is called at `CassandraStreamReceiver.java:221` (the filed `:218` is the `try` that opens the scanner at `:211-212`), and `requiresWritePath` is at `:195-200`.
> - **U1 (B2a, B2e: how it runs).** The test class is `MutationRepairBatchProbeTest` (a `CQLTester`, package `org.apache.cassandra.db.rows`, harness folder), run with `ant testsome -Dtest.name=org.apache.cassandra.db.rows.MutationRepairBatchProbeTest` in the run copy (`-Xmx` as `ant` sets it, about 1 GiB); the variant list and the output file are passed in the environment (`PROBE_VAR`, `PROBE_OUT`). It does what `CassandraStreamReceiver.sendThroughWritePath` does for one sstable: `reader.getScanner()` -> `ThrottledUnfilteredIterator.throttle(scanner, N)` -> `PartitionUpdate.fromIterator(batch, ColumnFilter.all(metadata))` (the object that becomes a Mutation), with each batch wrapped in a counter of the Unfilteds it hands out (rows and range-tombstone markers).
> - **U2 (B2b, B2c, B2h: the runs).** N in {0, 2, 100, 1000, 10000} on the filed table (1 partition, 100000 rows of 100-byte values, flushed and major-compacted to one sstable); the same N list on 10-byte and on 1000-byte values (bytes scale with rows x size); and the tombstone variant: 20000 rows `ck` 0..19999 written at timestamp 200 under a range tombstone `ck >= 0 AND ck < 20000` at timestamp 100 (the tombstone is open across every batch boundary), N in {2, 100, 1000}.
> - **U3 (B2d: observables).** Per batch: Unfilteds iterated, `rowCount()`, `dataSize()`, `unsharedHeapSize()` (maximum over batches); per N: the number of batches, whether `throttle` returned the scanner object itself (`sameObjectAsScanner`), and the **retained heap of the largest update** (used heap after 4 x `System.gc()` with the update still referenced, minus the same before the scan): the real resource, so the counter and the byte figure can be compared.
> - **U4 (B2f: numeric predictions, written before any reading).** Filed table: N = 0: `sameObjectAsScanner=true`, 1 batch, 100000 rows. N = 2: 50000 batches, every batch exactly 2 Unfilteds. N = 100: 1000 batches of exactly 100. N = 1000: 100 batches of exactly 1000. N = 10000: 10 batches of exactly 10000. Totals: 100000 rows for every N. Tombstone variant: the largest batch has **N + 1** Unfilteds (N elements plus the synthesized close marker) for every N tested, and every batch except the last ends with a close marker. Heap: `maxUnsharedHeapSize` for N >= 100 is proportional to N within 10 percent (`heap(1000)/heap(100)` in [9, 11], `heap(10000)/heap(1000)` in [9, 11]); `heap(N = 0) / heap(N = 100)` in [900, 1100]; per row (100-byte values) the unshared heap is in [150, 450] bytes; the per-row heap on 1000-byte values exceeds that on 10-byte values by 990 +- 20 percent bytes; `retainedHeapOfLargestUpdate` is in [0.7, 1.5] x its `maxUnsharedHeapSize` for the batches of 1000 rows and larger.
> - **U5 (B2g: added rows).** "N = 0 returns a different object from the scanner": the opt-out branch is not the one traced. "Batches > N + 1 Unfilteds in the tombstone variant": the +1 close marker is not the only overshoot. "Retained heap far from `unsharedHeapSize`": the counter is a poor proxy for the real heap here, which weakens the byte reading but not the row-count cap.
> - **U6 (runbook defect, 2026-10-27, found in the first unit attempt; claim, prediction and conclusions table unchanged).** In the first attempt the `retainedHeapOfLargestUpdate` column was invalid (3.5 MB for an update whose `unsharedHeapSize` was 32 MB, and negative values for the others): the reference to the largest update was not used after the measurement, so the JIT treated it as dead and the update was collected before the used heap was read. Fix: `held.rowCount()` is read after the measurement (column `heldRows`). The other columns of that attempt were consistent with U4 and are kept in `run1/unit-attempt1/`; the unit tier was run again from its beginning with the fixed probe, and the second attempt's readings are the ones used.

### B3. Cluster tier

**B3a. Environment and build.** Two nodes (RF=2) built from a private copy of the tag with `ant jar`; JDK 11; `-Xmx2g -Xms2g`, G1. Enable the write path: `cdc_enabled: true` with `cdc_on_repair_enabled: true` (default) on a table with `cdc = true`, or use a table with a materialized view and `materialized_views_on_repair_enabled: true`. Property `-Dcassandra.repair.mutation_repair_rows_per_batch=<N>` in `jvm11-server.options` of node 2 (the receiver).

**B3b. Knobs.** N = 0, 100, 10000, each on a fresh node-2 start (static final).

**B3c. Workload.** Node 1 only up (node 2 down while writing) is not needed: write with node 2 stopped via `cassandra-stress` or CQL: one wide partition of 2,000,000 rows, 200-byte values (~400 MB raw, far above the 2 GB heap's young gen), then flush node 1; start node 2 and run `nodetool repair -full <ks>` on node 2 so node 2 receives the stream. Duration: until repair finishes.

**B3d. Observables and instruments.** Node 2: `jstat -gc <pid> 1000` (heap used/GC), `jcmd <pid> GC.class_histogram` at the midpoint for `PartitionUpdate`/`BTree` instances, GC log (`-Xlog:gc*`), repair duration; logs for OOM. Not directly observable: per-Mutation size (use histogram instead).

**B3e. Procedure.** 1) Start both nodes, create keyspace RF=2 and table with `cdc=true`. 2) Stop node 2. 3) Load data on node 1; `nodetool flush`. 4) Stop node 1's writes, start node 2 with the N under test. 5) Run repair; sample as above. 6) Stop both nodes, wipe the private data dirs, repeat for next N.

**B3f. Predictions.** N=100 and N=10000: peak old/live heap during the stream stays roughly flat and low (batch <= ~20 KB for 100, ~2 MB for 10000, plus memtable); N=0: a single ~400 MB Mutation, heap peak exceeds the other runs by a few hundred MB and can OOM at -Xmx2g. Peak heap rises with N.

**B3g. Readings.**

| Observation | Meaning |
|---|---|
| peak live heap(N=0) >> peak(N=100), and rising with N | claim confirmed |
| peak heap equal across N | cap not binding on this path (check that write path was actually taken: log/histogram shows `PartitionUpdate`) or claim wrong |
| N=0 OOM, N=100 completes | strong confirmation |
| repair did not stream or did not use write path | not confirmed; fix setup |

**B3h. Controls.** Same data, JVM and sstable layout for each N; confirm the write path was taken by checking CDC commit log segments / MV updates; run once with plain table (no CDC) as negative control, where N should not change heap since the write path is not used.

> **Amendments to B3 (stage-4 audit, 2026-10-27, before the cluster tier ran).**
> - **C1 (B3a: nodes and write path; the filed text leaves three things open).** Two nodes on loopback addresses of the pc41 host, N_A = 127.0.0.2 (sender, JMX 7102, no property) and N_B = 127.0.0.3 (receiver, JMX 7103, the property), RF = 2, `auto_bootstrap: false`, one token each (the closed `repair_session_space` harness' layout); `cdc_enabled: true` on both and the two tables of C3; `memtable_allocation_type: offheap_buffers` with a 3 GiB off-heap space so the received data does not sit on the heap; node B at `-Xms2g -Xmx2g`, G1 (the shipped default), a GC log, NMT, and the Byteman agent with the rules of `bm.btm`. Entire-sstable streaming does not bypass the write path: `finished()` calls `sendThroughWritePath` for any received sstable when `requiresWritePath` is true (`CassandraStreamReceiver.java:238-245`), and the Byteman rule below proves it per run.
> - **C2 (B3a/B3f: the commit log is a second cap on the same mutation; not foreseen by the file).** With `cdc = true` the write path goes through the commit log (`writeCDCCommitLog`, `:204`, `:221-224`), and a Mutation larger than `max_mutation_size` (half of `commitlog_segment_size`, default 32 MiB / 2 = 16 MiB) is rejected. A 2,000,000-row partition of 200-byte values is about 430 MB, so the unthrottled arm N = 0 (one Mutation of the whole partition) is expected to **fail in `ks.apply` after the whole PartitionUpdate has been materialised**; N = 100000 (about 21 MB per Mutation) is expected to fail at the first batch for the same reason; N = 1000 (about 0.2 MB) and 10000 (about 2.1 MB) fit. The claim under test (heap held per Mutation) is read from the materialised update, not from the apply, so a failed apply does not invalidate an arm; it is recorded.
> - **C3 (B3b, B3c: data, arms).** Node A is loaded once by `prep-data.sh` (the driver-based `LoadWide`): keyspace `ks` (SimpleStrategy, RF 2), two tables `wide_cdc` (`cdc = true`) and `wide_plain` (`cdc = false`), each one partition `pk = 1` of 2,000,000 rows (`ck` 0..1999999, 200 random bytes), flushed and compacted to one sstable; A's data directory is copied to a backup and restored before each arm. Arms (receiver property N): `unset` (default 100) and 1000, 10000, 100000 and 0 on `wide_cdc`; and 0 on `wide_plain` (B3h negative control). Each arm: fresh B, then `nodetool -p 7103 repair -full ks <table>` on B.
> - **C4 (B3d: observables).** Byteman on B, one line per update built by `PartitionUpdate.fromIterator` for keyspace `ks` (`S4BATCH`: rows, `unsharedHeapSize()`, `dataSize()`) and one line per call of `ThrottledUnfilteredIterator.throttle` (`S4THROTTLE maxBatchSize=<value>`: the knob as the check sees it); a sampler on B every 4 s: a collecting class histogram (live bytes in total and of `BufferCell`, `ArrayClustering`, `BTreeRow`, `[B`) and the heap used; the G1 GC log (`-Xlog:gc*`); B's `system.log` (stream and repair outcome, `MutationExceededMaxSizeException`, OOM); `tablestats` and a row count on B after the repair. The `jstat` of the filed text is replaced by the GC log.
> - **C5 (B3f: numeric predictions, written before any cluster reading).** `S4THROTTLE` shows `maxBatchSize` = N (100 for `unset`) on `wide_cdc`; no `S4BATCH` and no `S4THROTTLE` line for `wide_plain`. `S4BATCH` rows per update: at most N for every N > 0, and exactly N for all but the last update of a partition; the number of updates is `ceil(2,000,000 / N)` (20000 for 100, 2000 for 1000, 200 for 10000, 20 for 100000); N = 0: one update of 2,000,000 rows. Per-update heap (`S4BATCH heap`) is proportional to rows: the heap per row of the cluster (200-byte values) agrees within 30 percent with the unit tier's per-row heap interpolated linearly in the value size between its 100-byte and 1000-byte variants (these unit readings exist before the cluster tier runs; the shakedown arm on 200,000 rows, seen before this freeze and not a reading, printed 416.6 B per row). The live heap of B (maximum `total_live_bytes` of the sampler) for N = 0 exceeds that for `unset` by at least 150 MB (2,000,000 rows x at least 150 B x 0.5); for 100, 1000 and 10000 the maxima agree within 50 MB (a 10000-row update is about 3.5 MB, below the sampler's noise: only the Byteman lines resolve these). Repair outcome: `unset`, 1000, 10000 complete (B holds the 2,000,000 rows); 100000 and 0 on `wide_cdc` fail with `MutationExceededMaxSizeException` (C2); 0 on `wide_plain` completes.
> - **C6 (B3g: added rows).** "N = 0 repair fails with `MutationExceededMaxSizeException` while the update held 2,000,000 rows": claim confirmed for the heap (the whole partition was one object) and a second cap observed. "N = 0 completes": the commit-log size limit did not apply (check `commitlog_segment_size`). "`wide_plain` arm builds updates": the write path is taken without CDC (claim about the path wrong). "`S4THROTTLE` value differs from the property": the knob is not read as traced.
> - **C7 (B3e step 6, B4).** "No process remains" is checked on the node with `ps -eo pid,comm,args | awk '$2=="java" && /CassandraDaemon/'`. Data directories (about 1 GB per node and table, plus `cdc_raw`) are under `~/stage4-mrb/`, local disk.
> - **C8 (runbook defects found by the shakedown, 2026-10-27; claim, prediction and rows unchanged).** (a) The node must run in the foreground mode of `bin/cassandra` (`-f`, put in the background by the harness's `node.sh`, which writes the pid file itself): in the default daemon mode `CassandraDaemon` closes `System.out` after start-up and Byteman's `traceln` lines are lost (the first shakedown showed 0 `S4BATCH` lines for a repair that had written 41 MB to `cdc_raw`). (b) `cp -a <backup> <A>/data` into an existing directory nests the copy; the harness copies `<backup>/.`. (c) `LoadWide` needs Guava on the compile and run class path (`build/lib/jars/*`) and registers a listener with `addListener` instead of Guava's `Futures`.

**B4. Risks and cleanup.** ~1 GB disk per node for data plus commit log/cdc_raw; use a private scratch directory, not shared storage. Stop both Cassandra JVMs, `pgrep -f CassandraDaemon` must be empty; delete data, commitlog, cdc_raw and logs afterwards.

## C. Sources read

- src/java/org/apache/cassandra/db/rows/ThrottledUnfilteredIterator.java
- src/java/org/apache/cassandra/db/streaming/CassandraStreamReceiver.java
- src/java/org/apache/cassandra/config/CassandraRelevantProperties.java (lines 410, 794-800, 881-888)
- test/unit/org/apache/cassandra/db/rows/ThrottledUnfilteredIteratorTest.java (grep only)

## D. Stage-4 feedback

**2026-10-27, node pc41, results [`results/mutation_repair_rows_per_batch-throttledunfilterediterator-maxbatchsize--autonomous.md`](../../stage4-runtime-verification/results/mutation_repair_rows_per_batch-throttledunfilterediterator-maxbatchsize--autonomous.md) (not committed by the session that ran it; frozen versions: unit `443ee733f606f31e451affa5e90ab591c3fdd5e5207e32db2f025580ec22147f` (after the dated defect fix U6; first attempt on `cd21e2ee665526bb1419ade2806bd517c14139837358deca3a58ac40103facbf`), cluster `3eec471acc6472eab1a6af31c428b36bbd09ecfc717f7e546620063fd98f23e1`).**

- **Verdict:** unit **Confirmed, caps**; cluster **Confirmed, caps** (heap per Mutation). Outcome class **true positive** (estimate `positive`, effect `caps`). Unit: with N = 2, 100, 1000, 10000 every batch has exactly N Unfilteds (N + 1 with a range tombstone open at the boundary), the heap of the update is linear in N (9.98x per decade; 320 B per row for 100-byte values) and equal to its retained heap (ratio 1.00-1.13), and N = 0 returns the scanner itself (one batch of 100000 rows, 998 times the heap of an N = 100 batch). Cluster (two loopback nodes, one 2,000,000-row partition of 200-byte values, receiver B at 2 GB): the Byteman line per update shows 20000 / 2000 / 200 updates of 100 / 1000 / 10000 rows at 416 B per row (41.7 KB / 416 KB / 4.16 MB), and at N = 0 one update of 2,000,000 rows with 832 MB of heap; the plain-table control builds no update.
- **Not foreseen by the file (amended, C2):** with `cdc = true` the Mutation is also limited by `max_mutation_size` (16 MiB at the default 32 MiB commit-log segment). N = 0 (426 MB) and N = 100000 (21 MB) were rejected with `MutationExceededMaxSizeException` after the update had been materialised and the repair failed; so the unthrottled path on a CDC table does not end in an out-of-memory error at 2 GB, it ends in a failed repair. The row-count cap does not bound bytes (A3's bypass note): 100000 rows is already too large for the commit log.
- **Missed (recorded, not tuned):** the process-level heap readings of the cluster tier (a histogram sampler every 4 s; the G1 log) did not separate N = 100, 1000 and 10000 (a transient of about 0.5 GB on the receive/apply side, 516 / 596 / 576 MB, the same within 80 MB although the updates differ 100-fold), and the sampler did not catch the N = 0 peak (92 MB; the G1 log shows 884 MiB). The reading that decides the question is the per-update heap from Byteman.
- **Runbook details (C8):** run the nodes with `bin/cassandra -f` or Byteman's `traceln` output is lost (the daemon closes `System.out`); a `SELECT count(*)` on the 2,000,000-row partition times out (B's content was read from the update totals and `tablestats`).
- **For stage 3:** A5's pointer to `ThrottledUnfilteredIteratorTest` is right (7 tests pass); the file's B3f numbers (20 KB for N = 100, 2 MB for N = 10000) were low by a factor of two (41.7 KB and 4.16 MB for 200-byte values), i.e. a row costs about 220 bytes plus its value.

