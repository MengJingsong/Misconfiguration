<!-- file: cases/max-compaction-threshold-getCandidatesFor-candidatesSize--autonomous.md -->
# max_threshold (maxCompactionThreshold) as L0 input cap in LCS — verification solution  <!-- file: cases/max-compaction-threshold-getCandidatesFor-candidatesSize--autonomous.md -->

| Field | Value |
|---|---|
| Entry pointer | `src/java/org/apache/cassandra/db/compaction/LeveledManifest.java:548` |
| Pinned source | `cassandra-5.0.9` |
| Session / date | Claude Sonnet 5.5 (claude-sonnet-5-5), Claude Code CLI via Agent SDK, 2026-10-26 |
| Estimate | `negative`. The constraint caps the number of L0 sstables in one LCS compaction, not the bytes (L0 sstables have no size bound) and not the total input set, because overlapping L1 sstables are added after the cap (`LeveledManifest.java:567`). |
| Ground | The operand is a count (`candidates.size()`), not a byte quantity. Disk and heap cost of a compaction scales with the bytes of its inputs and output. Those bytes depend on L0 sstable sizes (flush size, unbounded by this knob) and on the L1 sstables that overlap, which are appended unbounded. So usage should not follow the knob in a proportional or bounded way. |

## A. Constraint trace

**A1. The constraint.** `max_threshold`, a per-table compaction sub-option (`compaction = {'class': 'LeveledCompactionStrategy', 'max_threshold': N}`), read in the code as `cfs.getMaximumCompactionThreshold()`.
- Kind: table schema option plus a runtime-adjustable per-node override.
- First declared: `schema/CompactionParams.java:55` (`Option.MAX_THRESHOLD`); default `DEFAULT_MAX_THRESHOLD = 32` at `schema/CompactionParams.java:80`. Parsed by `CompactionParams.maxCompactionThreshold()` (`CompactionParams.java:175-181`), which returns 32 when the option is absent. Validated at `CompactionParams.java:233-257` (must be positive, min <= max).
- Held in `ColumnFamilyStore.maxCompactionThreshold` (`db/ColumnFamilyStore.java:315`, initialised at `:494`, re-derived on schema change at `:390-392`), read at `ColumnFamilyStore.java:3086-3089`.
- Unit: number of sstables.
- Setting: CQL `ALTER TABLE ... WITH compaction = {... 'max_threshold': N}` (persistent, no restart). Per node and non-persistent: JMX `setMaximumCompactionThreshold` (`ColumnFamilyStore.java:3091`) and `nodetool setcompactionthreshold <ks> <table> <min> <max>` (`tools/nodetool/SetCompactionThreshold.java`). No yaml key.
- Related constant at the same site: `MAX_COMPACTING_L0 = 32` (`LeveledManifest.java:62`), not settable.

**A2. What it caps.** Intended: the number of sstables in one compaction, which indirectly bounds the compaction's working set (open readers, merge-iterator buffers, transient disk). The quantity compared at line 548 is `candidates.size()`, the count of L0 sstables chosen so far.

**A3. Mechanism.**
1. `LeveledCompactionStrategy.getNextBackgroundTask` (`LeveledCompactionStrategy.java:131-137`) calls `manifest.getCompactionCandidates()` (`LeveledManifest.java:199`).
2. That method first computes an optional STCS-in-L0 candidate (`:243`, `:304-317`), taken only when L0 holds more than `MAX_COMPACTING_L0 = 32` sstables and `-Dcassandra.disable_stcs_in_l0` is not set (`DatabaseDescriptor.java:223`, `CassandraRelevantProperties.java:197`). That path is trimmed by `max_threshold` through `mostInterestingBucket` (`SizeTieredCompactionStrategy.java:116-131`).
3. Higher levels with score > 1.001 go first (`:245-288`). Otherwise `getCandidatesFor(0)` (`:293`) is called.
4. In `getCandidatesFor(0)` (`:495-573`): L0 sstables are walked oldest first (`ageSortedSSTables`, `:607-609`, by max timestamp). For each, the sstable and its overlapping L0 peers are added (`:537-546`). Peers are added as a whole group, so the set can exceed the limit before it is checked.
5. Line 548: if `candidates.size() > max_threshold`, the set is trimmed to the `max_threshold` oldest (`:551`) and the loop breaks. If the size is exactly equal, the loop continues and the next group is added, then trimmed.
6. Line 557: if the candidates' total bytes exceed `maxSSTableSizeInBytes` (default 160 MiB, `LeveledCompactionStrategy.java:67`, `:97`), every L1 sstable overlapping the candidates is added (`:562-567`). The overlap set is not bounded by `max_threshold`. L0 sstables span the whole token range, so this is typically all of L1 (about 10 sstables of 160 MiB at default fanout, `maxBytesForLevel` `:180-189`).
7. The result goes to a `LeveledCompactionTask` (`LeveledCompactionStrategy.java:149`, `:193`, `:211`). For L0 inputs the output is split by `maxSSTableBytes` but the task does not limit input bytes (`level == 0 ? Long.MAX_VALUE`, `:211`).
8. The only disk guard is `CompactionTask`'s space check, which drops sstables or aborts when space is short (`CompactionTask.java:98`, `:410-421`). It is independent of `max_threshold`.

Bypasses and overshoots: (a) L1 overlap added after the cap (`:567`); (b) the STCS-in-L0 and bootstrap STCS paths (`:205`, `:304`) use a different selector with the same count limit; (c) the L0 size gate means L0 sstables can be arbitrarily large (a flush or streamed file is not bounded by `sstable_size_in_mb`); (d) `getCompactionCandidates` is per strategy instance, so concurrent compactors each take their own set. `max_threshold` bounds the count per task, not the number of tasks.

**A4. Other consumers.** Memtables and flush buffers (heap/off-heap); the other tables' compactions run on `concurrent_compactors` threads; bloom filters, index summaries and key cache of every open sstable; the commit log; the hints and snapshot directories on the same data disk; streaming.

**A5. Evidence beyond the source.** Code comments at `LeveledManifest.java:213-239` and `:516-524` (rationale: bound L0 batch size "since we might run out of memory"). Unit test touching the ordering: `test/unit/org/apache/cassandra/db/compaction/LeveledCompactionStrategyTest.java:546`. No external documents were needed.

## B. Verification solution

**B1. Claim under test.** Raising or lowering `max_threshold` does not make the peak compaction input bytes (and therefore peak transient disk and compaction heap) track it: the L0 part is bounded only in count, and the L1 overlap is added on top. Equivalently, a compaction selected with `max_threshold = N` can contain more than N sstables and more bytes than N times the L0 sstable size.

### B2. Unit tier

**B2a. Environment and build.** JDK 11, Ant. Copy the tree to local disk (`cp -r ~/cassandra-5.0.9 /local/c509`; never build in the shared tree). `cd /local/c509 && ant jar`. Add a test class in the local copy, `test/unit/org/apache/cassandra/db/compaction/LcsMaxThresholdTest.java`, modelled on `LeveledCompactionStrategyTest` (which builds a `ColumnFamilyStore`, writes sstables and fetches `strategy.manifest`). Run `ant testsome -Dtest.name=LcsMaxThresholdTest`. JVM `-Xmx1g`.

**B2b. Knobs.** `max_threshold` in {4, 8, 32, 64}, set by schema (`cfs.setCompactionParameters` or CREATE TABLE options) and also via `cfs.setMaximumCompactionThreshold(n)`. `sstable_size_in_mb` fixed at 160 (default) for the main run and 1 for a variant (to make the L0 bytes gate at `:557` easy to pass). L0 sstable size: two classes, small (about 1 MiB) and large (about 20x larger, 20 MiB).

**B2c. Workload.** Write 100 L0 sstables by repeated insert plus `forceBlockingFlush`, with keys spanning the full token range so every L0 sstable overlaps all others (then all are in one overlap group and the cap binds at once). Place 10 sstables in L1 through `manifest.add` with level 1 (or by running compactions down) so L1 overlap is 10 sstables. Arithmetic: with 100 L0 sstables and N = 8, `candidates.size()` at line 548 reaches 100 > 8 on the first iteration, so the trim to 8 must occur; total L0 bytes 8 x 1 MiB = 8 MiB, which is below 160 MiB, so with default `sstable_size_in_mb` no L1 is added (inputs = 8). With `sstable_size_in_mb = 1` and 1 MiB sstables, 8 MiB > 1 MiB so L1 overlap (10) is added (inputs = 18 > N).

**B2d. Observables and instruments.** Call `strategy.manifest.getCompactionCandidates()` (in-package access) and record: count of sstables in `candidate.sstables`, count of those in L0 and in L1, and the sum of `SSTableReader.onDiskLength()` (`SSTableReader.getTotalBytes`). Not observable here: real heap and disk use during the merge.

**B2e. Procedure.**
1. Build, create the table with LCS and `max_threshold = N`.
2. Write and flush the sstables per B2c; confirm level counts with `manifest.getSStableCountPerLevel()`.
3. Call `getCompactionCandidates()` once with nothing marked compacting; record the three numbers.
4. Repeat for each N, each size class and each `sstable_size_in_mb`. Also repeat with `-Dcassandra.disable_stcs_in_l0=true`, and with 100 L0 sstables versus 20 (STCS path off at <= 32).
5. Positive control run: the STCS selector, calling `SizeTieredCompactionStrategy.mostInterestingBucket` on the same L0 sstables with `maxThreshold = N`.

**B2f. Predictions (before any run).**
- L0 count in the candidate set = min(N, 100) for every N (the cap binds on the L0 part).
- Large-sstable class with `sstable_size_in_mb = 160`: L0 bytes = N x 20 MiB. N = 8 gives 160 MiB, which is not above the 160 MiB gate (gate is strict `>`), so no L1; N = 32 gives 640 MiB, so L1 (10 sstables, about 1.6 GiB) is added. Total candidate count = N + 10 > N, and bytes are about 2.2 GiB, which is not proportional to N.
- Small class, `sstable_size_in_mb = 160`: no L1 for any N <= 64 (64 MiB < 160 MiB).
- Total candidate bytes is a step function of N (jumps when the gate at `:557` is crossed), not linear in N.

**B2g. Readings.**

| Observation | Meaning |
|---|---|
| Total candidate count <= N and bytes <= N x L0 sstable size for all runs | Usage follows the knob: claim refuted |
| L0 count = N but total count > N and bytes include an L1 jump not proportional to N, while the STCS control's count stays <= N and its bytes scale as N x size | Cap binds on count only; claim confirmed (usage flat or step-wise versus the knob while the positive control moves) |
| L0 count > N | Cap at :548 does not bind at all; claim confirmed, and the trace is wrong |
| L0 count < N for all N, or the gate at :557 is never crossed in any run | Limit never reached; not confirmed |
| The STCS control does not scale with N | Control did not move; not confirmed |

**B2h. Controls.** (i) The STCS selector on the same files (a known count/byte cap by trimming, `SizeTieredCompactionStrategy.java:116-135`); (ii) a run with L1 empty to isolate the L1 contribution; (iii) a run with nothing in L0 overlapping (to show the group-add overshoot before the trim); (iv) the same files with N = 100 to show no trim.

### B3. Cluster tier

**B3a. Environment and build.** One node, JDK 11, built from the local copy (`ant jar`). Data, commit log, hints and saved caches on a local disk of known size (for example a 20 GiB partition or loop-mounted file), never shared storage. JVM: `-Xms2g -Xmx2g` (set in `conf/jvm11-server.options`), G1. `concurrent_compactors: 1` and `compaction_throughput: 0` (unthrottled) in `cassandra.yaml` for clean readings. `memtable_flush_writers: 1`. Start with `-Dcassandra.disable_stcs_in_l0=true` to isolate the L0 non-STCS path.

**B3b. Knobs.** `max_threshold` in {4, 16, 32, 64} via `nodetool setcompactionthreshold ks t 2 N` (min must stay <= max) and, for a persistent variant, ALTER TABLE. `sstable_size_in_mb` = 160. Table `ks.t` with LCS, no compression to keep sizes predictable.

**B3c. Workload.** Disable autocompaction (`nodetool disableautocompaction ks t`), then write with `cassandra-stress` (user-defined or `write n=...`) using random keys over the full range, issuing `nodetool flush` every 64 MiB of writes until L0 holds 100 sstables of about 64 MiB (6.4 GiB; fits a 20 GiB disk with output room). Get a populated L1 first: enable compaction briefly, let it finish, so L1 holds about 10 sstables, then stop and refill L0 to 100 sstables. Then `nodetool enableautocompaction ks t` with `concurrent_compactors: 1` so exactly one task runs per step. Duration: until the first L0 task finishes (about minutes).

**B3d. Observables and instruments.** `nodetool compactionstats` (task id, total bytes, sstable count; `-H` for sizes) polled every 2 s; `nodetool tablestats ks.t` (SSTables in each level); `du -sb` of the data dir every 2 s (peak transient disk); `jcmd <pid> GC.heap_info` and `jstat -gcutil <pid> 1000` for heap; `system.log` line "Compacting (...) [...]" lists input sstables. Not directly observable: per-task off-heap memory (partly via `nodetool info` off-heap and native memory tracking `-XX:NativeMemoryTracking=summary`, `jcmd VM.native_memory`).

**B3e. Procedure.**
1. Build and start the node with the settings in B3a; create `ks.t`.
2. Load and flush per B3c; record `nodetool tablestats` and `du -sb`.
3. For each N: `nodetool setcompactionthreshold ks t 2 N`; `nodetool enableautocompaction`; start the pollers; wait for the first task; record the task's input sstable count and bytes from `compactionstats` and the log; record peak `du` minus baseline and peak heap used; `nodetool disableautocompaction`. Restore the fixture (restart from a copied snapshot of the data dir) before the next N.
4. Positive control: same fixture but table switched to STCS (`ALTER TABLE ... compaction = {'class':'SizeTieredCompactionStrategy','max_threshold': N,'min_threshold':2}`), same N list, record the same numbers. Also N = 32 with 20 L0 files (below the STCS-L0 threshold) as a reference.
5. Cleanup per B4.

**B3f. Predictions (before any run).**
- LCS: the first task has N L0 sstables (about N x 64 MiB) plus about 10 L1 sstables (about 1.6 GiB) once L0 bytes exceed 160 MiB, which holds for every N >= 3. Input count = N + about 10; input bytes = N x 64 MiB + about 1.6 GiB. Peak transient disk is about input + output bytes, so it rises with N only through the L0 term and has a fixed L1 offset of about 1.6 GiB (for N = 4: about 256 MiB + 1.6 GiB; for N = 64: about 4 GiB + 1.6 GiB, i.e. total larger than 64 x size not tracked by the knob alone).
- Heap used during the task is expected to differ little between N values (compaction streams rows; reader count changes buffer totals by about N x a few hundred KiB, not tens of MiB).
- STCS control: input count <= N exactly and peak transient disk about proportional to N x 64 MiB.

**B3g. Readings.**

| Observation | Meaning |
|---|---|
| Task input count <= N and peak disk delta <= N x file size for LCS | Usage follows the knob: claim refuted |
| LCS task input count = N + about 10 and peak disk has the fixed L1 offset, heap about flat across N, while STCS control scales with N | Claim confirmed |
| LCS count > N + L1 (more than the trace allows) | Trace wrong in another direction (group-add overshoot); report as extra finding |
| Fewer than N L0 files overlap or the first task is a higher-level compaction | Limit never reached; not confirmed (refill fixture) |
| STCS control does not move with N, or the STCS-in-L0 path (not disabled) runs instead of the LCS path | Control invalid or confounded; not confirmed |

**B3h. Controls.** (i) STCS positive control above; (ii) STCS-in-L0 off with the system property, and a run with it on to show its different count behaviour; (iii) empty L1 run to isolate the L1 offset; (iv) `concurrent_compactors: 1` so only one task is active; (v) identical fixture restored for each N; (vi) idle baseline of heap and `du` before each run.

**B4. Risks and cleanup.** Disk: the fixture needs about 6.4 GiB input plus about 2 x that as transient output; use a local partition of at least 20 GiB and stop if usage passes 80 percent. No shared storage; the source copy is built on local disk. After each run: `nodetool drain`, stop the node (`pkill -f CassandraDaemon`; check with `pgrep -f CassandraDaemon` and `jps`), stop cassandra-stress, remove the data, commitlog, hints, saved_caches and the copied tree, and confirm that no Java process from the run remains.

**Audit amendments (stage 4 step 0, 2026-10-26).** Made before any harness code, build output, run or reading; each leaves B1 and the rows of B2g/B3g as filed and fixes only an operational gap or an arithmetic point that does not depend on a reading. Where an amendment corrects text above, the amendment governs. Reasons are in the results file section 1.1.
- **U1 (B2c, fixtures).** Fixture F: 100 L0 sstables, each from a flush of at least 1,000 distinct keys (unique per sstable) so that every sstable spans the whole token range and overlaps all the others; 10 L1 sstables made from keys bucketed by token into 10 disjoint contiguous bands, flushed one band at a time, raised with `mutateLevelAndReload(1)` and gathered with `LeveledManifest.create(cfs, sizeMiB, 10, all)` (L1 sstables must not overlap each other, or `LeveledGenerations.addAll` sends them to L0, `LeveledGenerations.java:154-161`). L0 size classes: small about 1 MiB, large about 20 MiB. L1 sstables are small (about 0.3 MiB each); the 1.6 GiB L1 of B3 is not built at the unit tier, so the unit predictions are in counts and in measured bytes, not in the GiB figures of B2f.
- **U2 (B2f, gate arithmetic).** The L1 gate is strict and uses the measured on-disk bytes (`SSTableReader.getTotalBytes`, `LeveledManifest.java:557`). "N = 8 gives 160 MiB, which is not above the gate" is an arithmetic coincidence that depends on the exact file sizes (about 20 MiB each), so it is not predicted. The prediction is the rule: L1 sstables (10) are in the candidate set if and only if the measured L0 candidate bytes exceed 160 MiB; large class N = 4 (about 80 MiB) and N = 32, 64 (above 600 MiB) are predicted without and with L1; N = 8 is recorded and judged by the rule. Small class: no L1 for any N (at most 64 MiB). The figure "about 2.2 GiB" applies to the cluster tier only.
- **U3 (B2e step 4, repeats).** `-Dcassandra.disable_stcs_in_l0=true` is applied in the test with `DatabaseDescriptor.setDisableSTCSInL0(true)` (`DatabaseDescriptor.java:2594`). In fixture F the L1 score is below 1.001, so `getCandidatesFor(0)` is non-empty and the STCS-in-L0 candidate (`:243`, `:304`) is not returned: the prediction is an identical candidate set with the property on and off. The "20 versus 100 L0 sstables" repeat predicts L0 count = min(N, number of L0 sstables). B2f's "min(N, 100)" reads "min(N, number of L0 sstables in the fixture)".
- **U4 (B2h iii, group-add control).** Fixture G (small class): 100 L0 sstables in 25 groups of 4; the 4 sstables of a group overlap each other and no other group, with key bands disjoint between groups. Prediction: the L0 count in the candidate set is min(N, 100) for N in {4, 8, 32, 64}, because the loop at `:548` trims to the N oldest as soon as the accumulated set exceeds N (a set of exactly N is not trimmed, so for N = 4 the loop continues to the second group and trims then). The L0 count never exceeds N in any fixture; B2g's row "L0 count > N" is the refuting reading.
- **U5 (B2e step 5, STCS control).** `SizeTieredCompactionStrategy.createSSTableAndLengthPairs`, `getBuckets` (bucketHigh 1.5, bucketLow 0.5, minSSTableSize 50 MB defaults, so all L0 sstables fall in one bucket) and `mostInterestingBucket(buckets, 2, N)` on the 100 L0 sstables of fixture F, small class. Prediction: bucket size = min(N, 100), bytes about N x 1 MiB.
- **C1 (B3a/B3c, how the cluster fixtures are built and held).** Data, commit log, hints and saved caches on a dedicated 40 GiB tmpfs (the data volume of B3c, 6.4 GiB L0 plus 1.5 GiB L1, plus a copy and the largest task output, does not fit a 20 GiB partition with copies). The LCS table `ks.lcs` is created with `'enabled':'false'` in its schema (so a restart does not start compaction), sstable_size_in_mb 160, no compression, columns as the sibling harness. Fixture build, phase 1: `nodetool enableautocompaction ks lcs`, stress write of 1,500,000 rows (about 1.5 GiB, below the 1.6 GiB L1 target so the L1 score stays below 1.001), wait until `tpstats` shows no compaction task and the file bytes are unchanged for three reads 20 s apart, then `nodetool disableautocompaction`; check by `tablestats` that L0 = 0 and L2 = 0 and L1 holds 9 to 11 sstables, otherwise the fixture is rebuilt with a different row count. Phase 2: 100 times, `cassandra-stress write n=65536 -pop seq=<a>..<b>` on disjoint key ranges followed by `nodetool flush ks lcs` (65,536 rows of about 1 KiB give an sstable of about 64 MiB; keys hash across the whole range, so every L0 sstable overlaps all of L1). The node is then stopped and the data directory is copied (`cp -a`) to a fixture directory on the same tmpfs. The STCS control table `ks.stcs` is a separate fixture (compaction STCS, `'enabled':'false'`, no L1): the same 100 flushes only.
- **C2 (B3e step 3, one run per N).** Each run starts from a fresh copy of the fixture, starts the node (`concurrent_compactors: 1`, `compaction_throughput: 0`, G1, `-Xms2g -Xmx2g`), checks that L0 holds 100 sstables, sets N with `nodetool setcompactionthreshold ks lcs 2 N`, starts the samplers (every 1 s: bytes of the table directory, `jstat -gc` heap used, `RssAnon` of the daemon; every 5 s: `compactionstats`), records `date +%s%3N`, runs `nodetool enableautocompaction ks lcs`, waits for the first `Compacting (` line of the table in `system.log`, immediately runs `nodetool disableautocompaction ks lcs`, waits until `tpstats` shows no compaction task and the file bytes are unchanged for three reads 20 s apart, takes `tablestats`, stops the node. The input count and bytes come from the task's `Compacting (...)` and `Compacted (...)` log lines and are cross-checked against the sampled bytes. A second `Compacting (` line for the table before the disable is recorded and the run is valid only if the first task is the one analysed (it is read from its task id). N is varied in the order 32, 4, 64, 16 and the STCS control uses the same order (N is also reset by restart, since the JMX override is not persistent).
- **C3 (B3f, predictions stated for the fixture as built).** The L1 offset is the measured L1 file count and bytes of the fixture (about 10 sstables, about 1.5 GiB), not an assumed 1.6 GiB. Task input count for LCS = N + L1 count (L1 count about 10); input bytes = measured; the peak table-directory bytes above the pre-enable baseline is about the task's output bytes, which are about its input bytes; heap and `RssAnon` maxima are compared across N as a proxy (G1 used heap includes garbage; the gap is named in the results file).
- **C4 (B3g, unreachable row).** The row "LCS count > N + L1 (group-add overshoot)" cannot occur by the code (the trim at `:551` bounds the L0 part by N); if a reading shows it, it is reported as a trace error and the claim is judged on the L0 count. The "N = 32 with 20 L0 files" reference of B3e step 4 has no prediction in B3f and is not run.
- **C5 (B3e step 4, STCS control).** The control runs on the separate L0-only STCS fixture of C1 (not on the LCS fixture): with 10 L1 sstables of 160 MiB beside 100 of 64 MiB, STCS has two buckets and the chosen bucket (equal hotness, nothing read) would be arbitrary. Prediction: input count = N exactly and input bytes about N x 64 MiB for N in {4, 16, 32, 64}.

- **C6 (runbook defects D3 and D4 of the results file, 2026-10-26, found in discarded small-scale shakedowns before any cluster reading; B3f/B3g unchanged).** (a) After phase 1 of C1 one sstable can remain in L0: a lone L0 sstable below `sstable_size_in_mb` yields no candidate (`LeveledManifest.java:569`), so it cannot be compacted away. It counts toward the 100 L0 sstables, and phase 2 flushes (stress write of 65,536 rows, then `nodetool flush`) until `tablestats` shows exactly 100 sstables in L0 (a round can add more than one sstable). The fixture's L0 sstable sizes are recorded, not assumed. (b) C2's "immediately runs `nodetool disableautocompaction`" is done through a JMX connection held open by a helper (`StorageService.enableAutoCompaction` / `disableAutoCompaction`, milliseconds), because a `nodetool` JVM takes about 2 s, longer than a small first task; the first task is read from its own `Compacting (` and `Compacted (` log lines, and the sampled window is the span between them.

## C. Sources read

- /users/jason92/writeup-A/playbook-autonomous.md
- /users/jason92/writeup-A/_TEMPLATE-autonomous.md
- src/java/org/apache/cassandra/db/compaction/LeveledManifest.java (lines 59-84, 180-340, 480-610, 640-680)
- src/java/org/apache/cassandra/db/compaction/LeveledCompactionStrategy.java (131-211, 289)
- src/java/org/apache/cassandra/db/compaction/SizeTieredCompactionStrategy.java (91-135)
- src/java/org/apache/cassandra/db/compaction/CompactionTask.java (98, 410-430)
- src/java/org/apache/cassandra/schema/CompactionParams.java
- src/java/org/apache/cassandra/db/ColumnFamilyStore.java (315, 390, 494, 3040-3095)
- src/java/org/apache/cassandra/config/DatabaseDescriptor.java:223; CassandraRelevantProperties.java:197
- test/unit/org/apache/cassandra/db/compaction/LeveledCompactionStrategyTest.java (grep only)

## D. Stage-4 feedback

**Stage 4, 2026-10-26 — unit Confirmed, cluster Confirmed — caps only on some paths (bypass); outcome class: false negative** (estimate `negative`; the effect counts as caps). Results: [`stage4-runtime-verification/results/max-compaction-threshold-getCandidatesFor-candidatesSize--autonomous.md`](../../stage4-runtime-verification/results/max-compaction-threshold-getCandidatesFor-candidatesSize--autonomous.md); harness `stage4-runtime-verification/harness/max-compaction-threshold-getCandidatesFor-candidatesSize--autonomous/`. Not committed (the orchestrator commits).

- **Unit:** the cap at `:548` binds on the L0 part in all 58 probes (L0 count = min(N, L0 sstables), never above N, for N from 4 to 100, schema and setter paths, both L0 size classes, 25-group fixture); the 10 overlapping L1 sstables are added exactly when the measured L0 candidate bytes exceed `sstable_size_in_mb` (strict `>`, crossed between N = 6 and 8 for 21 MiB sstables), so the set has N + 10 sstables; the STCS selector (control) returns N. STCS-in-L0 on or off changes nothing in this fixture.
- **Cluster:** 100 L0 sstables (67.3 MiB) + 9 L1 sstables (1,401 MiB); the first LCS task at N = 4 / 16 / 32 / 64 had N L0 inputs (the N oldest) plus all 9 L1: 13 / 25 / 41 / 73 sstables, 1,680 / 2,488 / 3,565 / 5,719 MiB; peak table bytes above baseline = 68.9 MiB x N + 1,429 MiB; live heap 90-97 MiB, flat. The STCS control took exactly N sstables (65.8-69.0 MiB per N of peak bytes).
- **What it changes in the trace:** the claim of B1 holds as the tables word it (count N + L1, fixed L1 offset), but the usage did follow N linearly through the L0 part, with the same slope as the control; the L1 overlap is a fixed offset the knob does not limit (up to the L1 target, 10 x `sstable_size_in_mb`). A3 step 6 and the A3 "bypasses" list (a) are confirmed at runtime; (b) to (d) were not exercised. The estimate stays as filed (a refuted or mismatched estimate is not re-estimated); the Effect field reads `caps only on some paths (bypass)`, which is why the class is false negative. Whether the unbounded L1 term and L0 size justify `does not cap` instead (true negative) is an overrule point recorded in the results file section 8.
- **Amendments made at the audit and before any reading (2026-10-26):** U1-U5 (fixture mechanism, strict gate arithmetic, STCS-in-L0 repeat, group control, STCS selector call) and C1-C6 (tmpfs, fixture phases, per-N procedure, measured L1 offset, unreachable "overshoot" row, separate STCS control fixture, lone L0 sstable, JMX enable/disable helper). Predictions B2f/B3f and rows B2g/B3g unchanged (sha256 of the two tables recorded in the results file).
- **Run 1 / run 2:** run 1's cluster tier had no fully matching row (the heap measured as `GC.heap_info` used includes garbage and rose with task length in LCS and the control alike; one control reading was under-sampled); run 2 (same fixtures, sampler with live heap by class histogram) matches the Confirmed row. Details in the results file sections 3, 5 and 6.
- **Upstream/doc candidate:** the comment at `LeveledManifest.java:516-524` ("At most max_threshold sstables from L0 will be compacted at once") is exact for the L0 part; a reader can take it as a bound on the task, but the task also takes every overlapping L1 sstable (observed 73 inputs at N = 64 and 13 at N = 4 with 9 L1 sstables). A one-line note in the `max_threshold` documentation for LCS would say so; the documentation itself was not checked.
