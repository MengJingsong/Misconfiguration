<!-- file: cases/compaction-min-threshold-mostInterestingBucket-minThreshold--autonomous.md -->
# compaction min_threshold (STCS minThreshold) — verification solution  <!-- file: cases/compaction-min-threshold-mostInterestingBucket-minThreshold--autonomous.md -->

| Field | Value |
|---|---|
| Entry pointer | `src/java/org/apache/cassandra/db/compaction/SizeTieredCompactionStrategy.java:123` |
| Pinned source | `cassandra-5.0.9` |
| Session / date | Claude (Sonnet 5.5), Claude Code CLI, 2026-10-26 |
| Estimate | `negative`: `min_threshold` is a lower bound on how many similar-size SSTables must exist before a compaction starts; it triggers work and does not bound any memory or disk quantity. |
| Ground | The check `size >= minThreshold` is a trigger, not a cap. Raising it lets more SSTables accumulate on disk before they are merged, so on-disk bytes and open-file/index/bloom-filter memory tend to rise with it, not stay under it. The sibling `max_threshold` bounds the SSTable count per task (line 151), not bytes, so it is not a byte cap either. |

## A. Constraint trace

**A1. The constraint.** Table compaction sub-option `min_threshold` (the operand `minThreshold` at line 123). Kind: per-table schema option (runtime-adjustable). Declared in `schema/CompactionParams.java:54` (enum `Option.MIN_THRESHOLD`); default `DEFAULT_MIN_THRESHOLD = 4` at `CompactionParams.java:79`, injected as a default option at `:87` and `:140`, read at `:169`. Unit: number of SSTables. Set with `CREATE/ALTER TABLE ... WITH compaction = {'class':'SizeTieredCompactionStrategy','min_threshold':'N'}` (persisted in schema, no restart), or at runtime with `nodetool setcompactionthreshold <ks> <table> <min> <max>` (JMX, `ColumnFamilyStore.java:3066`, `:3080`; per-node, not persisted, lost on restart). Value is held in `ColumnFamilyStore.minCompactionThreshold` (`ColumnFamilyStore.java:314`, initialised from the schema at `:493`, read via `getMinimumCompactionThreshold()` at `:3075`). Validation requires it to be positive and no larger than max (`ColumnFamilyStore.java:530`, `CompactionParams.java:225-238`).

**A2. What it caps.** Nothing in bytes. The quantity compared is the count of SSTables in a size bucket after trimming (`bucketAndHotness.left.size()`, line 123) against `minThreshold`. It is a minimum count to start a compaction. Resource touched indirectly: disk (SSTable files awaiting compaction, plus temporary output of a compaction) and heap/off-heap per-SSTable structures (bloom filters, index summaries, open readers).

**A3. Mechanism.**
1. `getNextBackgroundSSTables` copies `minThreshold`/`maxThreshold` from the CFS (`SizeTieredCompactionStrategy.java:82-83`).
2. Candidates are bucketed by size (`:87`, `getBuckets` at `:248`; same bucket if within `bucketLow/bucketHigh` of the average, or both under `min_sstable_size`, default 50 MiB, `SizeTieredCompactionStrategyOptions.java:26`, check at `:274-275`).
3. `mostInterestingBucket` (`:116`) trims each bucket to at most `maxThreshold` SSTables, dropping the coldest (`trimToThresholdWithHotness`, `:151`).
4. Line 123 keeps a bucket only if the trimmed size is `>= minThreshold`; otherwise it is skipped (never compacted by this path).
5. If no bucket qualifies, `mostInterestingBucket` returns empty (`:126-127`); the caller then falls back to a single-SSTable tombstone compaction (`:97-106`, subject to tombstone ratio checks) or returns nothing. Result: SSTables stay on disk.
6. The chosen bucket becomes a `CompactionTask` (`:198-200`). Disk-space safety is separate: `CompactionTask.reduceScopeForLimitedSpace` (`CompactionTask.java:98`, called at `:421`) may drop SSTables from the task if free space is short.
Bypasses/overshoot: major compaction (`getMaximalTask`, `:205`) ignores thresholds; the tombstone fallback compacts one SSTable regardless of `minThreshold`; other strategies' tasks (e.g. repair/anticompaction, `nodetool compact`, cleanup, scrub) do not consult it. `estimatedRemainingTasks` (`:89`, `AbstractCompactionStrategy.java:221`) uses `max_threshold`, not `min_threshold`, for its estimate.

**A4. Other consumers.** Memtable flushes (new SSTables), commit log, hints, snapshots, streaming/repair-received SSTables, other tables' compactions competing for `concurrent_compactors`, and compaction temporary outputs, all share the same data disk. Heap/off-heap is also used by memtables, key/chunk caches, and per-SSTable bloom filters/index summaries.

**A5. Evidence beyond the source.** none (conclusions from source only; stage 4 to confirm).

## B. Verification solution

**B1. Claim under test.** Usage does not follow `min_threshold`: with a larger `min_threshold`, an STCS table keeps more SSTables and more bytes on disk (and more per-SSTable memory) for the same ingest, so `min_threshold` is not an upper cap on disk or memory. At line 123 the only effect is whether a same-size bucket is compacted.

### B2. Unit tier

**B2a. Environment and build.** JDK 11, Ant. Copy the tree to local disk (`rsync -a ~/cassandra-5.0.9/ /local/scratch/c509/`), `cd /local/scratch/c509 && ant jar` (and `ant build-test` if using a JUnit test). Test source: a new class `test/unit/org/apache/cassandra/db/compaction/StcsMinThresholdProbeTest.java` in the local copy only, or a main class using `SizeTieredCompactionStrategy.mostInterestingBucket` (public static) and `getBuckets` (public static). Run with `ant testsome -Dtest.name=StcsMinThresholdProbeTest` (JVM opts default; `-Xmx1g`).

**B2b. Knobs.** `minThreshold` in {2, 4 (default), 8, 16, 32}, `maxThreshold` fixed at 32; set as method arguments. Also vary SSTable count N in {3, 7, 15, 31, 40} in one size class. Why: straddles the default and the max cap boundary.

**B2c. Workload.** Create N synthetic same-size SSTables (use real small SSTables written via `CQLSSTableWriter`, each ~1 MiB, below `min_sstable_size` so all land in one bucket; or mocked `SSTableReader` as in `SizeTieredCompactionStrategyTest`). Arithmetic: one bucket holds N SSTables; the bucket is returned iff `min(N, 32) >= minThreshold`. Limit "reached" when N = minThreshold - 1 (not returned) and N = minThreshold (returned).

**B2d. Observables and instruments.** Return value of `mostInterestingBucket` (size, empty or not); total bytes of the returned and left-behind SSTables (`SSTableReader.bytesOnDisk()`); read directly from the call. No heap measurement is needed at this tier.

**B2e. Procedure.** (1) Build as in B2a. (2) For each (N, minThreshold) pair, call `getBuckets(createSSTableAndLengthPairs(ssts), 1.5, 0.5, 50MiB)`, then `mostInterestingBucket(buckets, minThreshold, 32)`. (3) Record returned size and the sum of bytes left uncompacted. (4) Positive control: same N, vary `maxThreshold` in {4, 8, 32} with `minThreshold=4`; returned size must equal `min(N, maxThreshold)`, showing a count cap that does bind. (5) Delete the scratch directory.

**B2f. Predictions.** Returned size = `min(N,32)` if `min(N,32) >= minThreshold`, else empty. For N=7: minThreshold 2/4 returns 7, 8/16/32 returns empty and 7 SSTables (7 MiB) remain uncompacted. For N=40: returned size is always 32 for every minThreshold <= 32. Uncompacted bytes grow monotonically with minThreshold for fixed N.

**B2g. Readings.**

| Observation | Meaning |
|---|---|
| Uncompacted bytes grow (or stay equal) as `minThreshold` rises | Claim confirmed: the knob is a trigger, not a cap |
| Uncompacted bytes shrink as `minThreshold` rises | Claim refuted |
| Returned size = `min(N, maxThreshold)` in control, while uncompacted bytes under `minThreshold` sweep do not drop | Usage flat/rising while the positive control (maxThreshold) moves the returned count: confirmed |
| Bucket never formed, or control returned size did not change with `maxThreshold` | Not confirmed; check bucket sizing |

**B2h. Controls.** Fixed SSTable sizes and hotness (read meters absent so hotness 0); only `minThreshold` changes between runs; `maxThreshold` sweep as the positive control.

### B3. Cluster tier

**B3a. Environment and build.** One node, local copy built with `ant jar`, JDK 11, `-Xms2g -Xmx2g` (set in `conf/jvm11-server.options`), data/commitlog/hints under a 20 GiB local directory (`data_file_directories`, `commitlog_directory`, `hints_directory` pointed at it). Disable unrelated work: `concurrent_compactors: 1`, `compaction_throughput: 0`, auto-snapshot off, `num_tokens: 1`.

**B3b. Knobs.** Table `ks.t` with `compaction = {'class':'SizeTieredCompactionStrategy','min_threshold':'M','max_threshold':'32'}`, M in {2, 4, 16, 32}, set via `ALTER TABLE` (one fresh table or fresh node per M). Why: from aggressive to the maximum allowed.

**B3c. Workload.** `cassandra-stress` (from the tree's `tools/bin`) write: `cassandra-stress write n=2000000 -schema "replication(factor=1)" ... -rate threads=16`, flushing with `nodetool flush` every 100k rows (20 flushes of ~tens of MiB each; keep each flush below ~50 MiB so all fall into one STCS bucket). Reachability: 20 same-size SSTables exceed M=2,4,16 but not 32, so M=32 never triggers compaction.

**B3d. Observables and instruments.** On-disk bytes: `nodetool tablestats ks.t` (Space used (total), SSTable count) and `du -sb <data dir>/ks/t-*`; sample every flush and 5 minutes after the last. Heap/off-heap: `nodetool tablestats` bloom filter memory and index summary off-heap, `nodetool info` heap, `jcmd <pid> GC.heap_info`. `nodetool compactionstats` for activity. Cannot observe the bucket choice directly except through `logger.trace` (enable via `nodetool setlogginglevel org.apache.cassandra.db.compaction TRACE`).

**B3e. Procedure.** (1) Build and start the node. (2) Create the table with M. (3) Run the workload with periodic flush. (4) Wait for `compactionstats` idle. (5) Record SSTable count, bytes, bloom/summary memory. (6) Positive control: repeat with `max_threshold=4`, `min_threshold=4`, same workload; SSTable count should be capped lower by merging. (7) Stop the node (`nodetool drain`, kill, check `pgrep -f CassandraDaemon`), delete the data directory.

**B3f. Predictions.** After 20 flushes: M=2 and M=4 end with SSTable count well below 20 (merged into few larger SSTables, typically under 8); M=16 ends with at most ~15 or merged after the 16th flush; M=32 keeps all 20 SSTables. SSTable count and per-SSTable memory are non-decreasing in M; total bytes on disk are higher at larger M when overwrites/tombstones exist (use `-pop dist=UNIFORM(1..200000)` so duplicates exist: bytes for M=32 should exceed M=2 by the duplicate fraction).

**B3g. Readings.**

| Observation | Meaning |
|---|---|
| SSTable count, bloom/summary memory and (with overwrites) bytes rise with M | Claim confirmed: no cap |
| Bytes and memory fall as M rises | Claim refuted |
| Flat usage across M while control (`max_threshold`/`min_threshold` lowered together) lowers SSTable count | Confirmed, knob irrelevant to usage |
| No flushes produced equal-size SSTables, or control shows no change | Not confirmed; rerun with sizes in one bucket |

**B3h. Controls.** Same data distribution, seed (`-pop seed=1`), JVM options and machine for all M; one table per run on a fresh node; compaction throughput unthrottled; no other writers.

**B4. Risks and cleanup.** Disk: cap at ~2 GiB of data per run on the 20 GiB local directory; never use shared storage. Stop cassandra-stress and the node, verify with `pgrep -f 'CassandraDaemon|cassandra-stress'`, remove the data, commitlog, hints and scratch source copy. Unit tier writes only to a temp directory under local disk.

**Audit amendments (stage 4 step 0, 2026-10-26).** Made before any harness code, build output, run or reading; each leaves B1 and the rows of B2f/B2g/B3f/B3g as filed and fixes only a wrong citation, an operational gap or an ambiguity that does not depend on a reading. Where an amendment corrects text above, the amendment governs. Reasons are in the results file section 1.1.
- **A1 (A1 and A3, validation and estimate, citation errors).** (a) `min_threshold` must be an integer of at least 2 and not above `max_threshold`: `CompactionParams.java:247-251` ("cannot be less than 2") and `:253-257` (min greater than max); `:225-231` is only the numeric check, and `ColumnFamilyStore.java:530-534` is a legacy path that disables compaction for a threshold of 0 or less (CQL cannot reach it after `:241`). The runtime setters validate min <= max (`ColumnFamilyStore.java:3066-3099`), and `setCompactionThresholds` also calls `CompactionManager.submitBackground` (`:3071`), so a runtime change starts a background pass at once. So the swept values {2, 4, 8, 16, 32} are the valid range with the default 4 and max 32; 1 is rejected. (b) The last sentence of A3 is wrong: `estimatedRemainingTasks` (`SizeTieredCompactionStrategy.java:89`, `getEstimatedCompactionsByTasks`, `:296-304`) uses **both** thresholds: a bucket counts only if `bucket.size() >= minCompactionThreshold`, then `ceil(size / maxThreshold)` tasks (`AbstractCompactionStrategy.java:221` is only the accessor). So pending-task counts also depend on `min_threshold`. The tombstone fallback is `:93-106`. None of this changes B1 or the prediction.
- **U1 (B2a-B2c, the fixture, real sstables).** The unit test uses real sstables, not mocks: an STCS table (`min_sstable_size` default 50 MiB) with autocompaction disabled, N flushes of 1,000 rows with 1 KiB values (about 1 MiB each, so every sstable is under `min_sstable_size` and falls in one bucket), N in {3, 7, 15, 31, 40}, a fresh table content per N (`truncateBlocking`). Each pair (N, M), M in {2, 4, 8, 16, 32}, max 32, is evaluated two ways: (i) the static `mostInterestingBucket(getBuckets(createSSTableAndLengthPairs(live), 1.5, 0.5, 50 MiB), M, 32)` as filed; (ii) the real path: `cfs.setCompactionThresholds(M, 32)` then `getNextBackgroundTask(0)` on the strategy instance (a task is returned if and only if the bucket is non-empty; its input count and bytes are read, then its transaction is aborted so nothing is compacted). "Uncompacted bytes" = sum of `onDiskLength` of the live sstables minus the returned bucket's. Both ways must agree; (i) is the reading judged against B2f/B2g, (ii) is the check that the static call is the one the strategy uses.
- **U2 (B2f, disk bytes with a real compaction).** To observe real disk bytes at the unit tier, a second table is written with 7 flushes of the same 1,000 keys (overwrites). With M = 4 the task from (ii) is executed and the live bytes before and after are read; with M = 8 no task exists and the bytes stay. Additional prediction (rows of B2g unchanged): M = 4 reduces live bytes to at most 0.25 of the before value (7 copies of the same rows collapse to about one); M = 8 leaves live bytes unchanged (ratio 1.0).
- **U3 (B2h, positive control).** The `maxThreshold` sweep {4, 8, 32} with M = 4 is run for N = 7 and N = 40; the returned size must equal `min(N, maxThreshold)` (4, 7, 7 for N = 7; 4, 8, 32 for N = 40), through both ways of U1.
- **C1 (B3a-B3c, table and node).** The cluster runs use the table `ks.standard1` created with `cqlsh` before the stress (columns `key blob, "C0".."C4" blob`, `compression = {'enabled':'false'}` so byte counts are not blurred by compression, `compaction = {'class':'SizeTieredCompactionStrategy','min_threshold':'M','max_threshold':'32'}`) and `cassandra-stress ... -schema keyspace=ks`; the "ks.t" of B3b means this table. One fresh node per arm, data, commit log, hints and saved caches on a tmpfs of 8 GiB, `-Xms2g -Xmx2g`. Node settings of B3a otherwise as filed (`concurrent_compactors: 1`, `compaction_throughput: 0`, `auto_snapshot: false`, `num_tokens: 1`). `nodetool setlogginglevel org.apache.cassandra.db.compaction TRACE` is set in every arm after start-up so `Compaction buckets are` lines are in `system.log`.
- **C2 (B3c, the workload, exact).** 20 chunks: chunk i (i = 1..20) is `cassandra-stress write n=100000 -pop 'dist=UNIFORM(1..200000)' -rate threads=16 -schema keyspace=ks -node <addr> -port jmx=<jmx>` followed by `nodetool flush ks standard1`. (`-pop` has no `seed` option: `cassandra-stress` printed `Invalid parameter seed=1` on the first shakedown, so the `seed=i` first written here is dropped; every chunk uses the same command, and the chunk-to-chunk overlap of keys is whatever stress generates, recorded through the bytes of the M = 2 and M = 32 arms.) Each flush is at most about 79,000 distinct keys, 20 MiB or less, far under `min_sstable_size`; the total key space is 200,000, so summed sstable rows are about 1.6 million against between 79,000 and 200,000 live keys (duplicate factor between 8 and 20). B3b's "M in {2, 4, 16, 32}" are four arms; B3e step 6 is a fifth arm (min 4, max 4, same workload). Rows are unthrottled.
- **C3 (B3d, what is judged).** The judged values are the end-state values: after chunk 20's flush wait until `compactionstats` shows no pending tasks and `tpstats` shows no active `CompactionExecutor` task in three polls 10 s apart (at most 300 s), then hold 120 s (instead of 5 min; idle is confirmed by the polls) and record: SSTable count, `Space used (total)`, `du -sb` of the table directory, `Bloom filter off heap memory used`, `Index summary off heap memory used` (`nodetool tablestats ks.standard1`), `RssAnon` of the daemon, live heap (`GC.class_histogram` total), `compactionhistory` row count, the `Compaction buckets are` trace count. The peak of the table-directory bytes during the run (sampled every 5 s) is recorded for information (compaction needs input plus output); it is not what B3f/B3g judge.
- **C4 (B3e, controls).** (a) Runtime flip in the M = 32 arm, after its end-state record: `nodetool setcompactionthreshold ks standard1 4 32`, wait for idle as in C3, record again. Prediction: the SSTable count falls from 20 to at most 5 and the live bytes fall by the duplicate fraction, with the same data; this is both the direct evidence that the check at line 123 (and nothing else) held the 20 sstables, and a known-binding change that moves usage. (b) The arm with min 4 and max 4 (B3e step 6) is as filed; its count must be below 20. A hold-fixed check per arm: `nodetool getcompactionthreshold ks standard1` prints the arm's min and max.
- **C5 (B3f, precision, no change of rows).** M = 2 and M = 4: SSTable count at most 4 at end-state (B3f's "under 8" governs the row). M = 16: the 16th flush starts a merge of 16, then 4 more flushes join the merged output (all are under 50 MiB, one bucket), so the expected count is 5; B3f's "at most about 15, or merged after the 16th flush" governs the row. M = 32: exactly 20 sstables and zero `compactionhistory` rows for the table. Bytes: M = 32 total bytes at least 3 times M = 2's (expected between 8 and 20).

## C. Sources read

- /users/jason92/writeup-A/playbook-autonomous.md
- /users/jason92/writeup-A/_TEMPLATE-autonomous.md
- src/java/org/apache/cassandra/db/compaction/SizeTieredCompactionStrategy.java
- src/java/org/apache/cassandra/db/compaction/SizeTieredCompactionStrategyOptions.java (grep)
- src/java/org/apache/cassandra/schema/CompactionParams.java (grep)
- src/java/org/apache/cassandra/db/ColumnFamilyStore.java (grep)
- src/java/org/apache/cassandra/db/compaction/AbstractCompactionStrategy.java (grep)
- src/java/org/apache/cassandra/db/compaction/CompactionTask.java (grep)

## D. Stage-4 feedback

Stage 4 run 1, 2026-10-26 (results: `stage4-runtime-verification/results/compaction-min-threshold-mostInterestingBucket-minThreshold--autonomous.md`). Unit **Confirmed** — does not cap; cluster **Confirmed** — does not cap. Outcome class: true negative. Estimate stands.
- Audit amendments A1, U1-U3, C1-C5 (section B, 2026-10-26): A1 corrects the validation citations (`min_threshold` must be >= 2 and <= `max_threshold`: `CompactionParams.java:247-257`) and the claim that the estimate ignores `min_threshold` (it counts a bucket only when `size >= min`, `SizeTieredCompactionStrategy.java:296-304`); the rest fix operational gaps. The `seed=i` option in the first C2 wording does not exist in `cassandra-stress -pop` and was removed before any reading.
- Cluster numbers (min_threshold 2 / 4 / 16 / 32, 20 flushes of 22.6 MB, 198,927 live keys): 1 / 2 / 5 / 20 sstables, 49.5 / 72.2 / 140.0 / 452.5 MB, bloom filter off-heap 0.25 / 0.37 / 0.71 / 2.32 MB. A runtime `setcompactionthreshold 4 32` on the M = 32 table merged the 20 sstables into 1 (452.5 -> 49.5 MB). Process `RssAnon` (2.9 GB) and live heap (91-96 MB) stayed flat, so the memory effect is visible only in the per-SSTable counters.
- Note for B1: disk bytes differ with `min_threshold` only when rows are overwritten or deleted; sstable count and per-SSTable memory differ regardless.
