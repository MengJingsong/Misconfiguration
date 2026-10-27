<!-- file: cases/max-unsigned-short-validate-sum--autonomous.md -->
# FBUtilities.MAX_UNSIGNED_SHORT (65535) as cap on a clustering prefix's total value size — verification solution  <!-- file: cases/max-unsigned-short-validate-sum--autonomous.md -->

| Field | Value |
|---|---|
| Entry pointer | `src/java/org/apache/cassandra/db/ClusteringPrefix.java:284` |
| Pinned source | `cassandra-5.0.9` |
| Session / date | Claude Sonnet 5.5 (claude-sonnet-5-5), Claude Code CLI via Agent SDK, 2026-10-26 |
| Estimate | `negative`: the constant bounds the byte size of ONE clustering key (sum of its column values, <= 65535 B), a per-object limit; node memory/disk is the product of this with the number of rows, which nothing here limits. |
| Ground | The check is a per-clustering-key width limit that exists because on-heap/off-heap clustering encodings store the data size in an unsigned short (`NativeClustering.java:50,59`). It does not bound any aggregate (memtable, partition, SSTable, disk). Resource use grows with row count regardless of the constant. |

## A. Constraint trace

**A1. The constraint.** `FBUtilities.MAX_UNSIGNED_SHORT`, a `public static final int` constant `= 0xFFFF` (65535) (`src/java/org/apache/cassandra/utils/FBUtilities.java:158`). Kind: hard-coded constant. Unit: bytes (here), though the same constant is reused as a count/length limit elsewhere (e.g. bind markers, `QueryProcessor.java:758`; client warnings count, `ClientWarn.java:79`). Default: fixed by the 16-bit field width. Not settable (no yaml key, no `-D`, no JMX); changing it needs a source change and rebuild.

**A2. What it caps.** Neither heap nor disk in aggregate. The compared quantity at the target line is `sum`, the total of `accessor.size(v)` over all non-null values of one `ClusteringPrefix` (`ClusteringPrefix.java:274-283`). The per-value check just above (`:278`) limits any single value to 65535 B; line 284 limits the total across all clustering columns. Maximum extra memory implied per clustering is therefore about 64 KiB of value data.

**A3. Mechanism.**
1. `ClusteringPrefix.validate()` (`:272-288`) iterates `getRawValues()`, throws `InvalidRequestException` ("Key length of %d is longer than maximum of %d") if any single value exceeds 65535 (`:278-281`), accumulates `sum` (`:282`), and after the loop throws the same exception if `sum > 65535` (`:284-287`).
2. Caller on the write path: `ModificationStatement` calls `clustering.validate()` for each clustering of an INSERT/UPDATE/DELETE before `addUpdateForKey` (`cql3/statements/ModificationStatement.java:815`). Rejected requests fail before any mutation is created, so nothing is written.
3. Backstop: `NativeClustering` constructor `assert dataSize <= MAX_UNSIGNED_SHORT` (`db/NativeClustering.java:50`) and stores `dataSize` as a short (`:59`); this is the reason for the limit (off-heap memtable allocation encoding). Asserts are only active with `-ea` (Cassandra's default scripts enable it).
Outcomes: at/below the limit the write proceeds; above it the statement fails with InvalidRequestException (client error). Bypasses/overshoots: the check is in the CQL modification path only; other entry points (e.g. thrift-less internal writes, streaming, batchlog replay, hints, SSTable import) do not pass through this `validate()` in the traced path; and the check bounds only key bytes, not the cell values, row count, or per-partition totals. The check at `:278` makes the per-value limit redundant for one-column keys.

**A4. Other consumers.** Memtable heap/off-heap (all rows, cell values, partition keys, per-row overhead), commit log, SSTables, row/key/chunk caches, compaction. Clustering key data is only a small slice and is multiplied by row count, which is unbounded by this constant. Row values themselves are limited elsewhere (e.g. `native_transport_max_frame_size`, 2 GiB value limits), not here.

**A5. Evidence beyond the source.** none (conclusions are from the 5.0.9 source only).

## B. Verification solution

**B1. Claim under test.** The constant caps only the size of one clustering key (<= 65535 B total); it does NOT cap memory or disk used by a node: memtable and on-disk usage grow linearly with the number of rows of maximal-size clustering keys, with no ceiling imposed by the constant.

### B2. Unit tier

**B2a. Environment and build.** Linux, JDK 11, Ant. Copy the tree to local disk (e.g. `rsync -a ~/cassandra-5.0.9/ /local/scratch/c509/`), then `cd /local/scratch/c509 && ant jar` (and `ant build-test` if using a JUnit test). Put a small test class under the copy's `test/unit/org/apache/cassandra/db/ClusteringValidateSizeTest.java`. Run with `ant testsome -Dtest.name=org.apache.cassandra.db.ClusteringValidateSizeTest` (JVM opts from build.xml, `-ea` on, `-Xmx1G`).

**B2b. Knobs.** The constant is not settable, so the knobs are the input shape: (i) number of clustering columns n in {1, 2, 4}; (ii) per-column value length so that total sum S takes values {65534, 65535, 65536, 65537} (with each value <= 65535 so the line-278 check is not the trigger); (iii) number of clusterings N held live in {1e3, 1e4, 1e5} (with S = 65535 or small=16 B as the positive-control contrast).

**B2c. Workload.** Build `Clustering.make(ByteBuffer...)` values, e.g. n=2 with lengths (32768, 32767)=65535 and (32768, 32768)=65536; call `validate()`. Then allocate N clusterings of S=65535 and measure retained size. Arithmetic: N=1e4 x 65535 B ~ 655 MB (use N up to 1e3 under -Xmx1G, i.e. ~65 MB, and extrapolate; if memory allows use a 4 GB heap for 1e4).

**B2d. Observables and instruments.** (1) Whether `validate()` throws and the message's `sum` value. (2) Retained heap: `ObjectSizes.measureDeep(list)` (org.apache.cassandra.utils.ObjectSizes) or JOL `GraphLayout.parseInstance(list).totalSize()`, plus `Runtime.totalMemory()-freeMemory()` after `System.gc()`. Cannot observe node-level resources at this tier.

**B2e. Procedure.**
1. Write the test: loop over the (n, S) grid and assert throw/no-throw exactly at S>65535.
2. For N in {1e3, 1e4}: build N clusterings with S=65535 and, as contrast, N with S=16; record deep size. Also build with S=65536 and confirm validate rejects (they could still be constructed, validate is not called by constructors).
3. Run with `ant testsome ...`; collect output.

**B2f. Predictions.** Throw iff S>65535 (S=65535 passes, 65536 fails; message reports the sum). Deep size is linear in N: size(N=1e4)/size(N=1e3) is about 10 (+-5%), and roughly N x S + small overhead for S=65535; for S=16 it is about N x (16 + ~50 B overhead). There is no value of N at which validate() or the constant limits retained size; only per-clustering S is bounded.

**B2g. Readings.**

| Observation | Meaning |
|---|---|
| Throw exactly when S>65535, no throw at 65535 | mechanism works as traced |
| Retained size scales ~linearly with N, sum-per-key held <= 65535 | claim confirmed: usage not capped by the constant (positive control: the S=16 vs S=65535 runs show usage moves with the accepted key size, and with N) |
| Retained size plateaus as N grows, independent of heap | claim refuted (some aggregate cap exists) |
| validate() accepts S>65535, or rejects <=65535 | trace wrong (e.g. line-278 per-value check or off-by-one) |
| Heap exhausted/OOM before N reached, or sizes not different between S=16 and S=65535 | not confirmed (control did not move) |

**B2h. Controls.** Same N with tiny keys (S=16) as control; run each size twice after a forced GC; use `measureDeep` and JOL together to rule out instrument error; assert validate() is not invoked during construction so the bytes counted are not an artifact.

**B2i. Stage-4 audit amendments, 2026-10-26** (made before any reading; none depends on a reading; B2g is unchanged).
1. *Paths and build (B2a).* No `/local/scratch` path exists and `ant testsome` forks a 1 GiB JVM. The tree is a `copy-source.sh` copy at `~/s4-b9-cs` built once with `ant jar`; the driver (`harness/max-unsigned-short-validate-sum--autonomous/ClusterKeyDriver.java`) is compiled outside the tree against `build/classes/main`, `build/lib/jars/*` and `conf` and run in its own JVM with `-Xmx3g` and `-Dcassandra.config=file://<tree>/conf/cassandra.yaml` (no JUnit class, no JOL). `validate()` needs no `TableMetadata`: `new BufferClustering(ByteBuffer...)` and `new ArrayClustering(byte[]...)` suffice.
2. *Boundary grid made exact (B2b, B2f).* The target line `:284` is reached only when every component is at most 65535 (otherwise the per-value branch `:278-281` throws first). The cells therefore use several components. Cells: S in {1, 1000, 32767, 32768, 65534, 65535, 65536, 70000} x N in {1, 2, 3} (each component S bytes), plus S = 1000 with N = 65 and N = 66, plus mixed cells (65535 and 1; 65535 and 0 bytes; 65535 and a null component; 32768 and 32767; 32768 and 32768; 32767, 32768 and 1; 65536 and 1; null and 65536; 1 and 70000; `Clustering.EMPTY` and `STATIC_CLUSTERING`). Rule: reject if any non-null component is larger than 65535 (message reports `dataSize()`, the **sum of all components**, `:280`, `:317-326`); otherwise reject if the sum exceeds 65535 (message reports the sum). Both read `Key length of <n> is longer than maximum of 65535`. So (32768, 32768) is rejected through the sum branch `:284` with n = 65536, (65535, 65535) through the sum branch with n = 131070, (65536, 1) through the per-value branch with n = 65537; (32768, 32767), (1000 x 65), (65535, 0 bytes) and a null component are accepted. Also `ArrayClustering` (byte[] accessor) at (32768, 32767) accepted and (32768, 32768) rejected. B2f's "(>=32768, N=2)" is exact only for S = 32768 and above; S = 32767 with N = 2 is accepted.
3. *The N grid of B2b, restated (B2c).* N = 1e5 clusterings of S = 65535 cannot be held (6.5 GB, 2 x the JVM). The held series is two components of 32768 and 32767 bytes (sum 65535, accepted at the sum limit) with M = 1,000 to 10,000 in steps of 1,000 (65.5 MB to 655 MB) in a `-Xmx3g` JVM; the contrast series uses two components of 8 bytes, M = 10,000 to 100,000 in steps of 10,000.
4. *Heap numbers made explicit (B2f).* "N x S plus small overhead" is restated: per key the heap after a full GC grows by 65535 + overhead with overhead between 40 and 300 B (a `BufferClustering`, its two-element `ByteBuffer[]`, two heap `ByteBuffer`s and two `byte[]`); the slope over the series is between 65,575 and 65,835 B per key, every 1,000-step stays within 10 percent of the mean step, and `validate()` never throws. B2f's "size(1e4)/size(1e3) about 10 (+-5%)" is stated on the deltas above the baseline heap, not on totals. The contrast series (8 + 8 bytes) has a slope below 600 B per key, and the ratio of the big slope over the small slope is above 100. Three JVMs repeat the big series; their slopes agree within 5 percent.
5. *Aggregate part (B2c, B2f).* Besides the held list, stream M = 100,000 distinct two-component clusterings (32768 + 32767 bytes, each at the sum limit) through `validate()` without holding them (6.55 x 10^9 bytes validated, 100,000 times the per-key cap): all accepted, heap after a final GC below 100 MB. This shows that the check itself retains nothing and bounds nothing in aggregate.
6. *Positive control specified (B2g row 2, B2h).* Capped control: the big series in which the list keeps only the newest 2,000 entries (a known cap, 131 MB): the heap at M = 10,000 is within 10 MB of the heap at M = 3,000, while the uncapped series grows by more than 400 MB between the same points. Together with the S = 16 contrast this shows the instrument tells a capped from an uncapped retention. B2h's "JOL" is dropped (not in the build; `Runtime` after three `System.gc()` is the instrument; the gap is named in item 7).
7. *Gap named (B2d).* The heap readings measure the driver's own list; `validate()` itself retains nothing. They show what holding that many accepted keys costs, not the memtable accounting, which only the cluster tier sees. "Assert validate() is not invoked during construction" is satisfied by construction: the driver calls `validate()` only explicitly, and a constructed 65536-byte clustering is never rejected until validated (grid).
8. *Leftover check (B2e).* The driver's own PID is checked, not `ps | grep java` (other sessions run JVMs on the same host).

### B3. Cluster tier

**B3a. Environment and build.** One node, local disk of known size (e.g. a 20 GiB local partition for `data_file_directories`, `commitlog_directory`, `hints_directory`, `saved_caches_directory`), built from the local copy: `ant jar`. JVM: `-Xms2G -Xmx2G`, G1 default. Config: `memtable_allocation_type: offheap_objects` (second run `heap_buffers`), `memtable_heap_space: 512MiB`, `memtable_offheap_space: 512MiB`, `commitlog_total_space: 1GiB`, `concurrent_compactors: 1`. Tool: `cassandra-stress` or a Python/Java driver script from the build (`tools/bin/cassandra-stress`), plus `nodetool`.

**B3b. Knobs.** Clustering key total size S in {16, 1024, 32768, 65535} bytes (two clustering columns, text/blob, each S/2 bytes); accepted vs. rejected 65536 as an edge. Number of rows per run R chosen so that R x S = 4 GiB (R = 262144 for S=16 KiB scaled...; for S=16 use R=4e6). The cap itself cannot be changed.

**B3c. Workload.** Table `ks.t (pk int, c1 blob, c2 blob, v int, PRIMARY KEY (pk, c1, c2))`. Insert R rows per run using prepared statements with c1,c2 of S/2 bytes each, through the driver on port 9042, spread over 1000 partitions. Arithmetic: S=65535 B x R=65536 rows = ~4 GiB of key data, well above the 512 MiB memtable limits and the 1 GiB commit log, so flushes and commit log recycling occur; duration about 10-30 minutes per run. A final statement with S=65536 shows rejection.

**B3d. Observables and instruments.** `nodetool tablestats ks.t` (Memtable data size, off-heap memory used, Space used (live/total)); `nodetool info` (heap and off-heap memory); `du -sb` on the data and commitlog directories every 10 s; `jcmd <pid> GC.heap_info`; JMX `org.apache.cassandra.metrics:type=Table,name=MemtableOnHeapSize/MemtableOffHeapSize`. The server log is checked for InvalidRequestException counts at the client. Cannot see per-key allocator overhead directly.

**B3e. Procedure.**
1. Copy the tree to local disk, `ant jar`, set the config above, start the node, record baseline `nodetool info`, `du`.
2. Create keyspace (RF=1) and table. 
3. For each S in {16, 1024, 32768, 65535}: truncate, insert R rows at rate with the driver, sampling instruments every 10 s; at end run `nodetool flush` and record `Space used (live)`.
4. Insert one row with S=65536; confirm client error "Key length of 65536 is longer than maximum of 65535" and no change in the table row count.
5. Repeat the S=65535 run with `memtable_allocation_type: heap_buffers`.
6. Stop the node (`nodetool drain` then kill), verify no process left (`pgrep -f CassandraDaemon`), delete the data directories.

**B3f. Predictions.** Total bytes inserted scales as R x S; peak memtable size is bounded by `memtable_*_space` (a different cap), flushed SSTable bytes `Space used` for a run grows linearly with R x S (about 1.0-1.2 x key bytes plus values), with S=65535 runs using roughly 4000 times more disk per row than S=16. Total disk after ingesting 4 GiB of S=65535 keys is on the order of 4 GiB (compression of random blobs ~1.0), far beyond 65535 B. The S=65536 insert fails; nothing about the constant prevents disk or memory growth by repeating rows.

**B3g. Readings.**

| Observation | Meaning |
|---|---|
| Disk and memtable-resident bytes grow ~ R x S for all S<=65535 while 65536 is rejected | claim confirmed (constant bounds one key, not usage) |
| Usage for the S=65535 run plateaus at ~64 KiB x small factor, regardless of R | claim refuted |
| S=65536 accepted | trace wrong (check bypassed on this path) |
| Usage at the S=16 run is not smaller per row than S=65535 | positive control failed: control did not move; not confirmed |
| Run stops early (disk full, OOM, client timeouts) before R rows | limit never reached; not confirmed |

Positive control: the same workload with the memtable cap (`memtable_offheap_space`) lowered shows flushes/memtable size plateauing at the configured cap, i.e. a cap that is known to bind moves usage, while the clustering-size constant does not.

**B3h. Controls.** Baseline idle node; S=16 run with the same R; both memtable allocation types; fixed data/commitlog on same local disk; compression off (`WITH compression = {'enabled': false}`) in a repeat to remove compression effects; disable compaction (`nodetool disableautocompaction`) while measuring flush sizes.

**B3i. Stage-4 audit amendments, 2026-10-26** (made before any reading; none depends on a reading; B3g is unchanged).
1. *Paths and node set-up (B3a).* No 20 GiB local partition and no `/local` path exist; the tree is `~/s4-b9-cs` (`copy-source.sh` + `ant jar`), and a copy of its `conf/` lives on tmpfs `/dev/shm/s4-b9-cs/node` with data, commitlog, hints and saved_caches there (tmpfs bytes stand for disk bytes; 126 GB free; other cases use other directories). Port slot 7: node address 127.0.7.1, JMX 7170, native 9042 on that address. Extra yaml lines beyond B3a: `memtable_cleanup_threshold: 0.99` (otherwise the pool limit is never reached), `auto_snapshot: false` (drop must not snapshot), `native_transport_timeout: 30s`, `write_request_timeout: 20000ms`, `num_tokens: 16`. The JVM is `MAX_HEAP_SIZE=2G` (B3a says `-Xms2G -Xmx2G`), `ulimit -n 100000`. `commitlog_total_space: 1GiB` is kept; the pools of B3a (512 MiB each) are replaced by 256 MiB each so that a 655 MB to 1 GB workload exceeds the pool several times without 4 GiB of data per arm (item 3); the control lowers both to 64 MiB.
2. *Schema and keys (B3c).* The key is always two components, so the sum branch `:284` is the trigger: `ks.t_<arm>(pk int, c1 blob, c2 blob, v int, PRIMARY KEY (pk, c1, c2))`, a fresh table per arm, S = |c1| + |c2| with c1 = ceil(S/2) bytes (an 8-byte big-endian counter plus seeded random bytes, distinct and incompressible) and c2 = floor(S/2) random bytes, except S = 65535 where c1 = 32768 and c2 = 32767. Rows over 100 partitions (pk = i mod 100, not 1000), 8 requests in flight for S >= 32768 and 32 below, protocol 4, consistency ONE, prepared statement. B3b's "R = 262144 for S = 16 KiB scaled..." is not a number and is replaced by item 3.
3. *Arms and arithmetic (B3b, B3c).* B3c's 4 GiB per arm (x4 arms plus a rerun) is more tmpfs, time and commit-log traffic than the question needs: the claim is shown once usage exceeds the pool and 65535 by orders of magnitude. Life 1 (pools 256 MiB, offheap_objects): boundary precheck (item 4), then S = 16 with R = 200,000 (3.2 MB of key bytes), S = 1024 with R = 1,000,000 (1.0 GB), S = 32768 with R = 20,000 (655 MB), S = 65535 with R = 10,000 (655 MB), S = 65536 with R = 10,000 (every write rejected through the sum branch). Life 2 (the known-binding control of B3f, restart with both pools at 64 MiB): S = 65535 with R = 10,000 again. Life 3 (`memtable_allocation_type: heap_buffers`, both pools 256 MiB): S = 65535 with R = 10,000, informational (B3e.5). Then the probe of item 8.
4. *First-trigger precheck (B3e.4).* Before any arm, on a two-component table: 3 inserts (32768, 32767) must succeed; 3 inserts (32768, 32768) must fail with exactly `Key length of 65536 is longer than maximum of 65535` (the sum branch `:284`); 3 inserts (65535, 65535) must fail with `Key length of 131070 is longer than maximum of 65535`; 3 inserts (70000, 10) must fail with `Key length of 70010 is longer than maximum of 65535` (per-value branch, message = sum). If any differs, the run stops (B3g row 3: the traced boundary is wrong). B3e.4's "no change in the table row count" is read from the table directory and the memtable (item 7).
5. *Control (B3e.5, B3h) restated.* The pool control uses the same workload as the S = 65535 arm, so only the pool changes. The clustering bytes of `offheap_objects` rows are in the off-heap pool, hence both pools are lowered together.
6. *Numbers for B3f.* After the flush, Data.db plus Index.db for S = 65535 (R = 10,000), S = 32768 (R = 20,000) and S = 1024 (R = 1,000,000) are between 1.0 and 3.0 times R x S (Index.db repeats the keys at the first and last name of each index block); Data+Index grows in the order S=16 (R=2e5) < S=65535 (R=1e4) and S=1024 (R=1e6) > S=65535 (R=1e4) in bytes, and the per-row Data+Index ratio S=65535 over S=16 is above 500 (B3f's "roughly 4000x" was for key bytes only; per row the row overhead and the int v bound it). Plateau: at 256 MiB the arms with 1 GB and 655 MB of key bytes each log at least one `MEMTABLE_LIMIT` flush with logged off-heap usage at most 320 MiB; the S = 16 arm logs none; at 64 MiB the S = 65535 arm logs at least one with usage at most 80 MiB; the ratio of the first `MEMTABLE_LIMIT` off-heap usage at 256 MiB over that at 64 MiB is between 2.5 and 6. S = 65536: 10,000 of 10,000 rejected, the table directory unchanged, the memtable empty. B3f's "peak memtable size bounded by `memtable_*_space`" is the plateau line. B3f's "compression of random blobs ~1.0" holds because keys are random; no separate compression-off repeat is run (B3h) since the Data+Index ratio band covers it.
7. *Observables (B3d).* Real resources: sstable bytes on tmpfs, `RssAnon` of the node (`/proc/<pid>/status`, not `VmRSS`), the node's own flush log lines (`Enqueuing flush of ..., Reason: MEMTABLE_LIMIT, Usage: ...`); `nodetool tablestats` is context only (its memtable data size may omit key bytes). `jcmd GC.heap_info` and `nodetool info` are replaced by the log lines and `RssAnon`, because the key bytes are off-heap malloc. `du -sb` is a walk of the table directory and the commit log every 2 s (not 10 s). `nodetool disableautocompaction` is not needed (no compaction triggers in a one-flush-per-memtable arm; the table directory is read after the arm's own flush).
8. *Probe outside B3g (informational; it does not change any conclusion row).* The text of A3 says other entry points skip the check. In the source the call `ModificationStatement.java:815` is inside `addUpdates` (plain statements, batches); the conditional path (`buildCasRequest`, `:573`) takes its clustering from `createClustering` without `validate()`, and a slice delete (`:762-787`) has no `validate()`. Also `PartitionKeySingleRestrictionSet.java:67` calls the same method for composite partition keys. After the main arms, on a fresh table (life 2): (a) a plain insert whose two-component ck sums to 65536, expected rejected with the exact text; (b) `INSERT ... IF NOT EXISTS` with the same ck, expected not rejected with that text at statement level; (c) `DELETE ... WHERE pk = ? AND c1 = ? AND c2 > ?` with a 1-byte c1 and a 70000-byte c2 bound, expected not rejected with that text. Whatever happens is recorded; the write of (b) may trip `NativeClustering.java:50`'s assert or be accepted. A side finding, outside the verdict.
9. *Leftover check (B3e.6).* The node is stopped by its PID file/`stopdaemon` and checked by PID; no `pkill`; no `pgrep -f CassandraDaemon` (other sessions' nodes run on the same host).

**B4. Risks and cleanup.** Unit tier uses up to ~4 GB heap in one JVM; kill after tests. Cluster tier writes up to ~4-5 GiB per run to local disk only (size the partition at >= 20 GiB and truncate between runs; never use shared storage; commit log capped at 1 GiB). At the end: `nodetool drain`, stop the node, `pgrep -f CassandraDaemon` and `pgrep -f cassandra-stress` must be empty, remove data, commitlog, hints and saved_caches directories and the source copy's `build/`.

## C. Sources read

- /users/jason92/writeup-A/playbook-autonomous.md
- /users/jason92/writeup-A/_TEMPLATE-autonomous.md
- src/java/org/apache/cassandra/db/ClusteringPrefix.java (lines 230-349)
- src/java/org/apache/cassandra/db/NativeClustering.java (lines 40-70)
- src/java/org/apache/cassandra/cql3/statements/ModificationStatement.java (lines 800-822)
- src/java/org/apache/cassandra/db/rows/AbstractRow.java (lines 90-104)
- src/java/org/apache/cassandra/utils/FBUtilities.java (grep of line 158)
- grep results over src/java for MAX_UNSIGNED_SHORT users

## D. Stage-4 feedback

**2026-10-26, stage 4 run 1 (node pc12, no run 2): unit tier Confirmed - does not cap; cluster tier Confirmed - does not cap. Outcome class: true negative.** Results: `stage4-runtime-verification/results/max-unsigned-short-validate-sum--autonomous.md`; harness: `stage4-runtime-verification/harness/max-unsigned-short-validate-sum--autonomous/`. The estimate stands as filed.
- Unit: the sum branch (`ClusteringPrefix.java:284`) rejects (32768, 32768) with "Key length of 65536 ..." and accepts (32768, 32767); 100,000 distinct 65535-byte two-component clusterings (6.55 x 10^9 bytes) validated without a rejection and without retention (heap 13.3 MB after); held clusterings retain 65,720 B each (65,535 + about 190), 334 times the 16-byte control's slope; a capped list stays flat.
- Cluster: all 10,000 writes at S = 65536 (two components of 32768) rejected with the exact text, nothing written; S = 65535 x 10,000 rows wrote 1.97 GB (Data.db 1.005 x R*S, Index.db 2.0 x R*S), about 30,000 times the per-key limit; memtable pools were the cap that bound (first `MEMTABLE_LIMIT` flush at 253.6 MiB with 256 MiB pools, 63.8 MiB with 64 MiB pools, ratio 3.97).
- Notes for stage 3: `ClusteringPrefix.validate()` has two branches with one message (the per-value branch `:278-281` also reports the sum, `dataSize()`), so a reached `:284` needs every component at most 65535; B2f's "(>=32768, N=2)" is exact only from 32768 and the estimate's "S=16 vs 65535 = 4000 times more disk per row" holds for key bytes, not for Data+Index. Side findings: a conditional write skips `validate()` and trips the `NativeClustering.java:50` assert; a range delete with a 70000-byte bound is accepted and its flush fails with `AssertionError` in `ByteBufferUtil.writeWithShortLength` (`StatsMetadata` serialization); `PartitionKeySingleRestrictionSet.java:67` also calls this method. Amendments: B2i, B3i (2026-10-26).

Stage-4 audit amendments of 2026-10-26 are B2i and B3i above. Citation checks (pinned `cassandra-5.0.9`): `ClusteringPrefix.java:272-288` and `:317-326`, `NativeClustering.java:50,59`, `ModificationStatement.java:815`, `FBUtilities.java:158` hold.
