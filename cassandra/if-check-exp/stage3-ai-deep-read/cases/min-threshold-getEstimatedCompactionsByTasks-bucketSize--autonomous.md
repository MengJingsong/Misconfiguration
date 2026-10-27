<!-- file: cases/min-threshold-getEstimatedCompactionsByTasks-bucketSize--autonomous.md -->
# min_threshold (compaction) as used in the pending-compaction estimate — verification solution

| Field | Value |
|---|---|
| Entry pointer | `src/java/org/apache/cassandra/db/compaction/SizeTieredCompactionStrategy.java:301` |
| Pinned source | `cassandra-5.0.9` |
| Session / date | Claude Sonnet 5.5 (claude-sonnet-5-5), Claude Code CLI, 2026-10-27 |
| Estimate | `negative`: at this line `min_threshold` only decides whether a bucket counts toward a pending-task estimate (a gauge/log number). Nothing here bounds heap, off-heap or disk. |
| Ground | The compared operand (`bucket.size()`, an SSTable count) is only summed into an `int` that feeds `estimatedRemainingTasks`, the `PendingCompactions` / `PendingTasks` metrics, the compaction log, and the repair-reject check (`ActiveRepairService.java:639`). No allocation or write is gated by it. Disk and memory usage is governed elsewhere (the real min-threshold gate is in `mostInterestingBucket`, `SizeTieredCompactionStrategy.java:123`, and it affects SSTable count and space amplification only indirectly, not as a cap). |

## A. Constraint trace

**A1. The constraint.** Table compaction option `min_threshold` (STCS/others; `CompactionParams.Option.MIN_THRESHOLD`, `schema/CompactionParams.java:54`). Kind: per-table schema option. Default `DEFAULT_MIN_THRESHOLD = 4` (`CompactionParams.java:79`), filled in at `CompactionParams.java:87,140`. Unit: number of SSTables in a bucket. Set via CQL `ALTER TABLE ... WITH compaction = {'class':'SizeTieredCompactionStrategy','min_threshold':'N'}`, or at runtime via JMX/nodetool `setcompactionthreshold` (`ColumnFamilyStore.setCompactionThresholds`/`setMinimumCompactionThreshold`, `ColumnFamilyStore.java:3066-3084`); no restart. Validation: min <= max and neither 0 (`ColumnFamilyStore.java:3097-3103`). The strategy reads the value through `cfs.getMinimumCompactionThreshold()` (`ColumnFamilyStore.java:3075-3078`).

**A2. What it caps.** Nothing resource-wise at this line. The code compares the number of SSTables in a size bucket (`bucket.size()`, line 301) with the threshold to decide whether the bucket is counted as one or more pending compaction tasks. The quantity is a task count, not bytes.

**A3. Mechanism.** `getEstimatedCompactionsByTasks` (`SizeTieredCompactionStrategy.java:296-305`): for each bucket, if `bucket.size() >= cfs.getMinimumCompactionThreshold()` (line 301), add `ceil(bucket.size() / maxThreshold)` (line 302). Called only from `getNextBackgroundSSTables` (line 89), which stores the result in `estimatedRemainingTasks` (line 68, volatile) and logs it (`compactionLogger.pending`, line 90). Reached: below the threshold the bucket adds 0; at or above it adds >= 1. Consumers: `getEstimatedRemainingTasks()` (line 232) -> `CompactionStrategyManager.getEstimatedRemainingTasks` (`CompactionStrategyManager.java:1132`) -> `TableMetrics.PendingCompactions` (`metrics/TableMetrics.java:636`) and `CompactionMetrics.pendingTasks` (`metrics/CompactionMetrics.java:71-83`) -> `CompactionManager.getPendingTasks` (`CompactionManager.java:2206`) -> `ActiveRepairService.verifyCompactionsPendingThreshold` (`ActiveRepairService.java:637-646`), which rejects incoming repairs above a pending-compaction threshold. So a side effect exists (a repair may be refused), but it is control-plane, not a memory or disk limit. Bypass/overshoot: none relevant; the value is not enforced against anything.

**A4. Other consumers.** The same option is read in `getNextBackgroundSSTables` (lines 80-81) and applied in `mostInterestingBucket` (line 123: buckets below minThreshold are skipped), which decides whether a compaction runs; that governs how many SSTables accumulate on disk and read amplification, but that is behavior of a different line. Disk usage is also driven by flushes, tombstones/TTL, snapshots, hints, commit log; heap/off-heap by memtables, caches, bloom filters, index summaries.

**A5. Evidence beyond the source.** Cassandra docs, compaction (STCS) options `min_threshold` / `max_threshold`: https://cassandra.apache.org/doc/5.0/cassandra/managing/operating/compaction/stcs.html . None other.

## B. Verification solution

**B1. Claim under test.** Changing `min_threshold` changes only the pending-compaction estimate computed at line 301 (a count) and does not bound node memory or disk consumed by that estimate; the byte usage tracked by a node is not a function of this operand. (Negative: usage does not follow the constraint.)

### B2. Unit tier

**B2a. Environment and build.** JDK 11, Ant. Copy the tree to local disk (stage 4 uses `copy-source.sh`; *amendment 2026-10-27: the `rsync` path and `ant jar` of the original text are replaced by `copy-source.sh` and `ant build-test`*). Put a JUnit test in the copy at `test/unit/org/apache/cassandra/db/compaction/EstimateMinThresholdProbe.java` (copy only, never the shared tree), run with `ant testsome -Dtest.name=EstimateMinThresholdProbe`. JVM options: default test options plus `-Xmx512m`.

**B2b. Knobs.** `min_threshold` in {2, 4 (default), 8, 9}, with `max_threshold` fixed at 32. Values bracket the default and put the bucket size (below) on both sides of each threshold. *Amendment 2026-10-27 (stage 4 audit): 33 was replaced by 9. `validateCompactionThresholds` (`ColumnFamilyStore.java:3097-3100`) throws when min > max, so (min 33, max 32) cannot be set; 9 is the smallest value above the 8-SSTable bucket and is valid. Reason from source, no reading.* Set by `cfs.setMinimumCompactionThreshold(n)` or the table's compaction map in `SchemaLoader.createKeyspace`.

**B2c. Workload.** Create a table with STCS, `disableAutoCompaction()`. Flush 8 equal-size SSTables of ~1 MiB each (`insert` 1000 rows of 1 KiB via `QueryProcessor.executeInternal`, `cfs.forceBlockingFlush`) so they fall in one bucket (bucketLow 0.5 / bucketHigh 1.5 default; every SSTable below `min_sstable_size`, 50 MB default, shares the first bucket anyway). Bucket size is 8. Also a second run with 40 SSTables (bucket 40 > max_threshold 32). Arithmetic: estimate = ceil(8/32) = 1 when min <= 8, else 0; for 40 SSTables = ceil(40/32) = 2 for min <= 40, 0 for min = 9 with the 8-SSTable run only (*amended 2026-10-27, was 33; see B2b*).

**B2d. Observables and instruments.** (1) `getEstimatedRemainingTasks()` after calling `getNextBackgroundTask(gcBefore)` (the estimate is only refreshed there, line 89). *Amendment 2026-10-27: the call goes to the table's `SizeTieredCompactionStrategy` instance directly (and its returned task is aborted), not through `CompactionStrategyManager`, because `cfs.disableAutoCompaction()` makes the manager's `getNextBackgroundTask` return null before any strategy runs (`CompactionStrategyManager.java:203`). The manager-level sum (`getEstimatedRemainingTasks`) and the `PendingCompactions` gauge are read as well.* (2) Total `cfs.metric.liveDiskSpaceUsed` / `totalDiskSpaceUsed` and the sum of `sstable.onDiskLength()`. (3) JVM heap used after `System.gc()` (`Runtime.totalMemory()-freeMemory()`), sampled once per configuration. Not observable: off-heap per object.

**B2e. Procedure.** For each min value: set it, call `getNextBackgroundTask` once, record estimate, disk bytes, heap. Do not execute the returned task for the estimate readings (control step below does).

**B2f. Predictions.** Estimate per (min, SSTables): (2,8)=1, (4,8)=1, (8,8)=1, (9,8)=0 (*amended 2026-10-27, was (33,8)*); (2,40)=2, (4,40)=2. Disk bytes (sum of the same 8 or 40 files) are identical for all min values (equal to the flushed data, ~8 MiB / ~40 MiB) because no compaction has run; heap difference between runs is within noise (< 1 MiB). Claim would be wrong if bytes or heap moved systematically with min while the SSTable set is unchanged.

**B2g. Readings.**

| Observation | Meaning |
|---|---|
| Estimate flips as predicted, disk bytes and heap constant across min | Claim confirmed: the operand drives a count only |
| Disk bytes or heap vary monotonically with min with SSTable set unchanged | Claim refuted: usage follows the knob |
| Estimate does not change at all across min | Mechanism not as traced (e.g. estimate not refreshed); not confirmed |
| Positive control (B2h) moves disk bytes while the estimate-only knob did not | Confirms negative |
| Limit never reached (bucket never reaches min, e.g. 9 with 8 SSTables; *amended 2026-10-27, was 33*) | That row confirms only the 0 case; need rows on both sides |

**B2h. Controls.** Positive control: after the estimate readings, run the compaction for the (4,8) case (`task.execute`) and observe that `sstable count` drops 8 -> 1 and `totalDiskSpaceUsed` changes; this shows the harness can see usage move when a compaction actually executes. Also set `max_threshold` to 4 vs 32 with 40 SSTables and show the number of SSTables per compaction (4 vs 32) changes the peak temporary space of one compaction (where a cap does bind: `mostInterestingBucket` trims to maxThreshold, line ~121).

### B3. Cluster tier

**B3a. Environment and build.** One node, JDK 11, built from a local copy of the tag (`ant jar` in `/tmp/c509`). Data, commit log, hints on local disk (>= 20 GiB free, e.g. `/tmp/cnode/{data,commitlog,hints}`), `-Xms2g -Xmx2g`, `concurrent_compactors=1`, `compaction_throughput=0` for repeatability. *Amendment 2026-10-27: `compaction_throughput` is 8 MiB/s instead of 0, so that the estimate, which is stale-then-recomputed only when a compaction check runs, stays readable for several seconds while a compaction runs (B3e); unthrottled, a 200 MiB compaction ends in seconds. The node is a loopback node on tmpfs (`/dev/shm`) under the stage-4 protocol, not `/tmp`.* Stop all processes afterward.

**B3b. Knobs.** Table compaction `min_threshold` in {2, 4, 16}, `max_threshold=32`, STCS, via `ALTER TABLE ks.t WITH compaction = {...}` and `nodetool setcompactionthreshold ks t <min> 32`. Also `nodetool disableautocompaction` during ingest so SSTable counts are controlled.

**B3c. Workload.** `cassandra-stress` (from the tree's `tools/`): `write n=200000` with 1 KiB values (~200 MiB) and `nodetool flush` every 20000 writes giving 10 SSTables of roughly equal size (one bucket). *Clarification 2026-10-27: this is ten `write n=20000` invocations over disjoint `-pop seq=` ranges, each followed by a flush.* Each setting uses a fresh table. 10 SSTables put the bucket above min=2 and 4 but below 16. Run ~5 min of observation.

**B3d. Observables and instruments.** JMX/`nodetool tablestats` fields `Pending Flushes`, `SSTable count`, `Space used (live)`, `Space used (total)`; `nodetool compactionstats` (pending tasks); JMX `org.apache.cassandra.metrics:type=Table,name=PendingCompactions` and `Compaction,name=PendingTasks`; `df` on the data dir; heap and off-heap from `nodetool info` and `jcmd <pid> GC.heap_info` / NMT (`-XX:NativeMemoryTracking=summary`). Sampled every 10 s. Not observable: attribution of heap to this estimate (it is one int).

**B3e. Procedure.** (1) Start node, create keyspace/table. (2) `nodetool disableautocompaction ks t`. (3) For each min value: ingest + flush to 10 SSTables; set thresholds; read `PendingCompactions` (note it refreshes only when the strategy builds a task, so call `nodetool enableautocompaction` briefly or trigger `submitBackground` by `setcompactionthreshold`, which does that at `ColumnFamilyStore.java:3072`); record disk and heap samples before compaction is allowed. *Amendment 2026-10-27: `setcompactionthreshold` cannot refresh the estimate while autocompaction is disabled (`submitBackground` returns at once, `CompactionManager.java:232`). The refresh is `nodetool enableautocompaction ks t` (`ColumnFamilyStore.java:3013-3016`), after the thresholds are set. The disk and memory baseline is therefore sampled after `setcompactionthreshold` and before `enableautocompaction`; after the enable, min 2 and 4 start a compaction at once (so disk then moves for a reason other than the estimate), and `PendingCompactions` is polled about every 2 s while that compaction runs throttled.* (4) Positive control: enable autocompaction and let the compaction run; record SSTable count and space transitions. (5) Drop table, stop node, `rm -rf /tmp/cnode`.

**B3f. Predictions.** `PendingCompactions` = 1 for min=2 and 4 (10 SSTables >= min, ceil(10/32)=1) and 0 for min=16, at the moment of the estimate (before any compaction). `Space used (total)` is the same (~200 MiB, within SSTable overhead) and heap/off-heap steady-state the same (+-5%) across min values while compaction is held off (*the baseline sample of the B3e amendment: min already set, autocompaction still disabled*). Falsified if disk/heap differs by min with the same SSTable set.

**B3g. Readings.**

| Observation | Meaning |
|---|---|
| Pending changes with min, disk and memory flat | Claim confirmed |
| Disk or memory differ by min before any compaction runs | Claim refuted |
| Pending never refreshes/changes | Not confirmed; revisit trigger |
| Positive control (step 4) shows disk usage rising during compaction (temporary extra space) and falling after, while the estimate-only change did not | Confirms the estimate is not the resource-affecting path |
| min=16 never triggers compaction because 10 < 16, and disk stays at ~200 MiB with 10 files | Shows the real gate (mostInterestingBucket) affects SSTable count, a different line; does not refute the claim about line 301 |

**B3h. Controls.** Same data, same flush pattern, fresh table per setting; autocompaction held off in the estimate phase; repeat 3 times; run the same workload with `max_threshold` 4 vs 32 as a known binding limit on compaction width. *Clarification 2026-10-27: that control is two extra tables with min 4 and max 4 or 32; the evidence is the first `Compacted (id) N sstables` line of `system.log` (N = 4 vs 10) and the peak `du` of the table directory above its baseline during that first compaction.*

**B4. Risks and cleanup.** Disk: ~1 GiB max locally (several tables of 200 MiB plus compaction temp); use local disk of known size, not shared storage. Stop the Cassandra process and any `cassandra-stress`/JUnit JVM (`pgrep -f cassandra` must be empty); delete `/tmp/c509` and `/tmp/cnode`.

## C. Sources read

- ~/writeup-A/playbook-autonomous.md
- ~/writeup-A/_TEMPLATE-autonomous.md
- src/java/org/apache/cassandra/db/compaction/SizeTieredCompactionStrategy.java
- src/java/org/apache/cassandra/db/compaction/CompactionStrategyManager.java (1128-1146)
- src/java/org/apache/cassandra/db/ColumnFamilyStore.java (3060-3105 and grep)
- src/java/org/apache/cassandra/schema/CompactionParams.java (76-90)
- src/java/org/apache/cassandra/metrics/CompactionMetrics.java (66-86)
- src/java/org/apache/cassandra/metrics/TableMetrics.java (grep, 636)
- src/java/org/apache/cassandra/service/ActiveRepairService.java (625-660)
- https://cassandra.apache.org/doc/5.0/cassandra/managing/operating/compaction/stcs.html (cited, not fetched)

## D. Stage-4 feedback

**Stage 4, 2026-10-27 (run 1, results `stage4-runtime-verification/results/min-threshold-getEstimatedCompactionsByTasks-bucketSize--autonomous.md`):** unit **Confirmed** (does not cap): the estimate flipped exactly as ceil(n/32) or 0 for min 2/4/8/9 at 8 SSTables and 2/4/9 at 40, forward and reverse; disk bytes identical, heap spread 0.007 MiB; positive controls (executed compaction 8 -> 1; `max_threshold` 4 vs 32 gave 4 vs 32 inputs). Cluster **Confirmed** (does not cap): `PendingCompactions` 1/1/0 for min 2/4/16 in 3 of 3 repetitions, baseline disk identical to < 0.0001 %, RssAnon flat to 0.2 %; live heap per-min means differed 5.4 % against the frozen 5 % tolerance (noise and unrandomized arm order, recorded); controls: max 4 vs 32 first compaction 4 vs 10 sstables, peak du +84 vs +209 MB. Outcome class true negative. The estimate is refreshed only when a compaction check runs; it is stale while autocompaction is disabled.

**Audit amendments, 2026-10-27 (stage 4, before run 1):** B2b/B2f/B2g `33` -> `9` (min above max cannot be set); B2d call goes to the STCS instance; B2a build; B3a throttle 8 MiB/s; B3e the estimate refreshes on `enableautocompaction`, baseline sample defined; B3c/B3h clarified; `mostInterestingBucket` citation `:125` -> `:123`. None depends on a reading. Not tested by this case: the repair-reject consumer (`ActiveRepairService.java:637-646`) is a control-plane effect named in A3 and outside the memory/disk question.
