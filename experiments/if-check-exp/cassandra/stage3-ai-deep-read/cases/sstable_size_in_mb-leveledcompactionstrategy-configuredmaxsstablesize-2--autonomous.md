# sstable_size_in_mb — verification solution  <!-- file: cases/sstable_size_in_mb-leveledcompactionstrategy-configuredmaxsstablesize-2--autonomous.md -->

| Field | Value |
|---|---|
| Entry pointer | the if statement: [`LeveledCompactionStrategy.java:81`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/compaction/LeveledCompactionStrategy.java#L81) (`if (configuredMaxSSTableSize < 50)`) |
| Pinned source | `cassandra-5.0.9` |
| Session / date | Claude Code CLI (Agent-tool subagent), 2026-10-27 |
| Estimate | `negative`: the checked line only logs a warning and bounds nothing; the option it inspects sets a per-file target size and per-level size targets, not a ceiling on a node's total disk or memory. |
| Ground | The if at line 81 has no effect except `logger.warn`. The option itself (`sstable_size_in_mb`) only decides where compaction output is split into files and the per-level score denominator; total on-disk bytes are set by the data written and by how fast compaction keeps up, and a flushed or streamed SSTable enters L0 at any size. Disk and heap usage therefore track data volume and SSTable count, not the option. |

> Link rule followed: the declaration (A1) and the if statement (Entry pointer, A3) are permalinks at `cassandra-5.0.9`. All line numbers were re-checked against `/users/jason92/cassandra-5.0.9`.

## A. Constraint trace

**A1. The constraint.** `sstable_size_in_mb`: a per-table compaction sub-option of LeveledCompactionStrategy (LCS), set in CQL schema (not a cassandra.yaml entry, not a JVM property). Declared as the string constant [`SSTABLE_SIZE_OPTION = "sstable_size_in_mb"` at LeveledCompactionStrategy.java:52](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/compaction/LeveledCompactionStrategy.java#L52). Unit: MiB (converted to bytes by `* 1024L * 1024L` at LeveledManifest.java:84 and LeveledCompactionStrategy.java:291). Default: the hard-coded `160` assigned to `configuredMaxSSTableSize` at LeveledCompactionStrategy.java:67, used when the option is absent (not derived from anything else). The `"1"` fallback at LeveledCompactionStrategy.java:576 is only for `validateOptions`, which rejects values < 1 (lines 578-582) and non-integers (lines 585-587). Settable per table with `CREATE/ALTER TABLE ... WITH compaction = {'class':'LeveledCompactionStrategy','sstable_size_in_mb': N}`. An ALTER reaches `CompactionStrategyManager.maybeReloadParamsFromSchema` (CompactionStrategyManager.java:478), which calls `reloadParamsFromSchema` (line 499); that the strategy is rebuilt without a node restart is inferred from these names and not verified beyond them. A related JVM property `cassandra.tolerate_sstable_size` ([CassandraRelevantProperties.java:604](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/CassandraRelevantProperties.java#L604)) is read once into a `static final` at LeveledCompactionStrategy.java:53, so changing it needs a restart; it only turns off the warnings below.

**A2. What it caps.** Nominally: the target size of one LCS output SSTable on disk (the unit of compaction) and, through `maxBytesForLevel`, the size target of each level (L0 = 4 x size, Ln = fanout^n x size; LeveledManifest.java:185-192). The quantity compared in the entry-point check is the parsed option value itself in MiB (`configuredMaxSSTableSize`), compared against the literal 50. The quantities compared in the real uses are (a) `getEstimatedOnDiskBytesWritten()` against `maxSSTableSize` (MaxSSTableSizeWriter.java:78) and (b) level bytes / `maxBytesForLevel` as the compaction score (LeveledManifest.java:254-255). Neither is a limit on total node disk or memory.

**A3. Mechanism.**
1. Constructor [`LeveledCompactionStrategy(ColumnFamilyStore, Map)`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/compaction/LeveledCompactionStrategy.java#L64) starts with 160 (line 67); if the option is present it does `Integer.parseInt` (line 75).
2. If `!tolerateSstableSize` (line 76): `>= 1000` logs a "probably a bad idea" warning (line 78-80); the entry-point check [`if (configuredMaxSSTableSize < 50)` at line 81](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/compaction/LeveledCompactionStrategy.java#L81) logs a warning citing CASSANDRA-5727 (text taken from the source at line 82). Neither branch throws, clamps or changes the value. Outcome of the check: a log line only; the value flows on unchanged.
3. The value is stored (line 97) and passed to `new LeveledManifest(...)` (line 101), which stores `maxSSTableSizeInBytes` (LeveledManifest.java:84).
4. Scoring: for each level i >= 1 the score is remaining bytes / `maxBytesForLevel(i, ...)` (LeveledManifest.java:254-255); above 1.001 the level is a compaction source (line 262); the highest level only warns (lines 263-267) and is never compacted for being over target.
5. Output splitting: the candidate carries `maxSSTableSizeInBytes` (LeveledManifest.java:281, 301) into `LeveledCompactionTask` (LeveledCompactionTask.java:41), which builds a `MaxSSTableSizeWriter` (line 53). `shouldSwitchWriterInCurrentLocation` returns true once the current writer's estimated on-disk bytes exceed the limit (MaxSSTableSizeWriter.java:76-79); `getExpectedWriteSize` is `min(maxSSTableSize, ...)` (line 94) and feeds the pre-compaction free-space reservation.
6. Disk-space abort: `CompactionTask` aborts with "Not enough space for compaction" when the reservation fails (CompactionTask.java:428-442); the strategy's `getMaxSSTableBytes()` (LeveledCompactionStrategy.java:289-292) is used only to print the estimated SSTable count in that message.

Bypasses and overshoot: (a) the split test runs when a new partition starts, so a file can exceed the target by up to one partition (wide partitions give files far larger than the option); (b) memtable flushes, streamed and bulk-loaded SSTables enter L0 with no size relation to the option; (c) L0 can get STCS-style compaction when it is behind (LeveledManifest.java:306), which produces files not sized by the option; (d) the highest level can exceed its target indefinitely (lines 263-267); (e) a major LCS compaction uses `MajorLeveledCompactionWriter` (LeveledCompactionTask.java:52), not verified in detail here.


The check itself is the if statement at [`LeveledCompactionStrategy.java:81`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/compaction/LeveledCompactionStrategy.java#L81).

**A4. Other consumers.** Disk: commit log, hints, snapshots, other tables' SSTables, tombstone-retaining data, temporary files of in-flight compactions (input and output coexist until the transaction finishes), and uncompacted L0 backlog. Heap/off-heap (the memory-significant link, which the option affects only indirectly through SSTable count): per-SSTable bloom filters, index summaries, compression metadata, key cache, chunk cache, memtables, and compaction-time buffers. None of these is bounded by this option.

**A5. Evidence beyond the source.** The only external pointer is the issue number printed inside the source warning (CASSANDRA-5727, LeveledCompactionStrategy.java:82), cited as printed there and not otherwise verified. Public LCS documentation (https://cassandra.apache.org/doc/5.0/cassandra/managing/operating/compaction/lcs.html) describes `sstable_size_in_mb` as the target file size; not re-read for this case. Otherwise none.

## B. Verification solution

**B1. Claim under test.** Changing `sstable_size_in_mb` (including to values that trigger the line-81 warning, < 50, or the line-78 warning, >= 1000) changes how many files the same data is split into and the per-level targets, but does not cap or reduce a table's total on-disk bytes or the node's heap/off-heap usage beyond the second-order effect of the SSTable count; the line-81 check itself changes nothing but a log line.

### B2. Unit tier

**B2a. Environment and build.** Copy the tree to local disk: `rsync -a /users/jason92/cassandra-5.0.9/ $WORK/cassandra-5.0.9/` (never build in the shared tree). JDK 11, Ant. `cd $WORK/cassandra-5.0.9 && ant jar`. Put a JUnit class under `test/unit/org/apache/cassandra/db/compaction/` of the copy (name it `SstableSizeOptionProbeTest`) in the style of the existing LCS unit tests (a `CQLTester` or `SchemaLoader` table with `compaction` set to LCS; the existing test classes there are the model, not verified file-by-file here). Run with `ant testsome -Dtest.name=SstableSizeOptionProbeTest -Dtest.methods=...`. JVM options for the test: default test heap; add `-Dcassandra.tolerate_sstable_size=false` explicitly (the default) in one run and `=true` in a second.

**B2b. Knobs.** `sstable_size_in_mb` in {10, 49, 50, 160, 999, 1000}: 49 and 50 straddle line 81, 999 and 1000 straddle line 78, 160 is the default (positive-control baseline for "no warning"), 10 is a clearly small value. Set via `ALTER TABLE ... WITH compaction = {...}` or the table's `compaction` map in the test. Second knob: `cassandra.tolerate_sstable_size` false/true (JVM `-D`, requires a fresh JVM per value because it is a `static final`).

**B2c. Workload.** (1) Construction only: build the strategy for each knob value and capture log output with a Logback list appender attached to the `LeveledCompactionStrategy` logger. (2) Splitting: write about 400 MiB of non-compressible data (random bytes, partitions of about 1 KiB, so no single partition dominates) into the table using `cfs.getTablesFor`-style flushes of about 20 MiB each (about 20 L0 SSTables), then run `CompactionManager.instance.performMaximal`-free, plain `cfs.enableAutoCompaction()` plus `CompactionManager.instance.submitBackground(cfs)` until `getCompactionStrategyManager().getEstimatedRemainingTasks() == 0`. Arithmetic: 400 MiB / 160 MiB gives at least 3 output files; 400 / 10 gives about 40; so the SSTable count should differ by an order of magnitude across knob values while total bytes should not.

**B2d. Observables and instruments.** (a) Captured WARN events (message text, count) per construction. (b) After compaction: number of live SSTables per level (`getAllLevelSize()`, LeveledCompactionStrategy.java:118-121 region, and `getAllLevelSizeBytes()`), per-file `onDiskLength()`, and the sum of `cfs.metric.liveDiskSpaceUsed`. (c) Heap proxy: `sum(sstable.getBloomFilter().serializedSize())` / `offHeapSize()` over live SSTables via `SSTableReader` accessors (accessor names to be confirmed against the tree by the executor). Not observable here: real JVM heap effect of a live node.

**B2e. Procedure.**
1. Build the copy; add the test class.
2. For each knob value: fresh JVM, create table with that option, record WARN output (step B2c-1).
3. Same JVM: perform the B2c-2 workload; wait until no pending compactions; record B2d (b) and (c).
4. Repeat with `-Dcassandra.tolerate_sstable_size=true` for values 10, 49, 1000 and record WARN output.
5. Positive control (below) in the same harness.
6. `ant clean` is not needed; delete `$WORK` at the end.

**B2f. Predictions.** Warnings: 49 and 10 emit exactly the line-81 warning; 1000 emits exactly the line-78 warning; 50, 160, 999 emit none; with tolerate=true none emit any. SSTable count after settling is roughly inversely proportional to the knob (10 gives many times more files than 160); max single-file size is at most about the knob plus one partition, except L0 leftovers. Total live disk bytes are within a few percent across knob values (same data, same compression). Bloom-filter total size changes little (it scales with key count), while the per-SSTable count and fixed per-file overhead rise at small knob values.

**B2g. Readings.**

| Observation | Meaning |
|---|---|
| Warnings exactly as in B2f, no change in total bytes across knob values | Mechanism as traced; claim (negative) confirmed |
| Total live bytes or heap proxy falls as the knob falls (beyond a few percent, beyond the file-count overhead) | Usage follows the knob; claim refuted |
| Warning missing at 49 with tolerate=false, or present with tolerate=true | Trace of lines 53/76/81 wrong |
| Total flat while the positive control moves | Claim confirmed |
| Single files larger than the knob by more than one partition, outside L0 | Splitting rule differs from trace (MaxSSTableSizeWriter.java:78); investigate |
| Limit never reached (all data stays in L0) or the control does not move | Not confirmed; extend workload |

**B2h. Controls.** Positive control: the same harness with a constraint known to bind on the same quantity, a deliberately tiny write quota for compaction output is not available, so use the writer's own limit as seen through the quantity it does bind: file size. Show that max file size follows the knob (10 vs 160), proving the harness can detect the effect it is supposed to; then show the total does not. Also run a control with identical data and knob 160 twice to measure run-to-run variance of total bytes. Fix the random seed for the data.

### B3. Cluster tier

**B3a. Environment and build.** One node (a second node is optional and not needed). Local copy of the tag built with `ant jar`; run from the copy with data, commit log, hints, saved caches in directories on a local disk of known size (at least 20 GiB free; set `data_file_directories`, `commitlog_directory`, `hints_directory`, `saved_caches_directory` in the copy's `conf/cassandra.yaml`). JVM: `-Xms2G -Xmx2G` (set in the copy's `conf/jvm11-server.options`), G1. `compaction_throughput: 64MiB/s` is the default (cassandra.yaml:1251); set `compaction_throughput: 0MiB/s` for the run so compaction is not rate-limited, and note it in the report. Leave `concurrent_compactors` at default. Use `cassandra-stress` from the copy as the client.

**B3b. Knobs.** Table-level `sstable_size_in_mb` in {10, 160, 1000} on three otherwise identical tables in separate keyspaces or in sequential runs from an empty data directory (sequential is cleaner). 10 and 1000 hit the line-81 and line-78 warnings; 160 is the default. Set by `ALTER TABLE ... WITH compaction = {'class':'LeveledCompactionStrategy','sstable_size_in_mb':N}`.

**B3c. Workload.** `cassandra-stress` write-only with fixed seed: about 4 GiB of logical data per run (for example `n=4000000` rows of about 1 KiB; adjust to the actual row size after a small trial), `-rate threads=32`, unique keys so the compacted size is the same for all knob values. Arithmetic: 4 GiB / 160 MiB gives about 25 files at steady state, 4 GiB / 10 MiB about 400, 4 GiB / 1000 MiB about 4. Then idle until `nodetool compactionstats` shows no pending tasks. Duration: write phase about 10 to 20 minutes, plus settling.

**B3d. Observables and instruments.** Disk: `du -sb` of the table's data directory, sampled every 10 s during the run (peak and final); `nodetool tablestats <ks.table>` (Space used (live), SSTable count, SSTables in each level, Bloom filter off-heap memory used, Index summary off-heap memory used, Compression metadata off-heap memory used). Heap: `jcmd <pid> GC.heap_info` and `nodetool info` (heap used) sampled every 10 s; GC logs for the heap after full collection. Off-heap: `nodetool tablestats` fields above and process RSS via `ps -o rss`. Not directly observable: the exact temporary space reserved by a single compaction (inferred from peak `du` minus final).

**B3e. Procedure.**
1. Copy and build: `rsync -a /users/jason92/cassandra-5.0.9/ $WORK/c/ && cd $WORK/c && ant jar`.
2. Edit the copy's yaml/jvm options as in B3a; ensure the local directories are empty.
3. Start the node; confirm with `nodetool status`.
4. Create keyspace (RF 1) and table through `cqlsh` with LCS and `sstable_size_in_mb`=N. Grep the node log for the line-78/line-81 warnings.
5. Start the samplers (B3d) and run the stress write.
6. Wait for compactions to finish; record final `tablestats` and `du`.
7. Stop the node, delete the data directories, repeat for the next N. Run each N twice.
8. Positive control (B3h).
9. Cleanup as in B4.

**B3f. Predictions.** Logs: warnings only for 10 (line 81) and 1000 (line 78). Final SSTable count follows approximately 4 GiB / N (many files at 10, few at 1000); the largest file at the end is on the order of N plus one partition. Final live disk bytes are about the same across N (within a few percent); peak disk during compaction is somewhat larger when N is large (a single large compaction keeps inputs and outputs together), not smaller when N is small. Heap after GC is similar across N; bloom filter plus index-summary off-heap totals are similar, with small per-file overhead growth at N=10. No setting causes writes to stop or the table to stay below a fixed size.

**B3g. Readings.**

| Observation | Meaning |
|---|---|
| File count and max file size follow N; live bytes, heap after GC and off-heap totals roughly equal across N | Claim confirmed: option shapes file layout, not usage |
| Live bytes, heap or off-heap totals fall materially as N falls (beyond the few-percent noise measured by the repeat run) | Usage follows the knob; claim refuted |
| Peak disk much lower at small N | Partial dependence of transient disk on N; record as a refinement of the claim, not a cap |
| Warning absent at 10 or 1000 | Trace of A3 wrong |
| Usage flat but the positive control also flat, or the compactions never finish (backlog remains) | Not confirmed; extend run or reduce rate |

**B3h. Controls.** Positive control on the same stress workload: repeat once with a cap known to bind on disk or memory, for example a table with `default_time_to_live` small enough to expire data (live bytes fall with TTL after compaction and `gc_grace_seconds` reached; set `gc_grace_seconds` to 0 for the test), or `-Xmx` lowered to show heap reacting to a real cap; either shows the instruments can see a change. Repeat the N=160 run to measure noise. Use a fixed stress seed and the same data directory size.

**B4. Risks and cleanup.** Disk: unit tier writes about 400 MiB per knob value; cluster tier about 4 GiB of data and up to about twice that at peak per run, on a local disk with a known size (check `df` first; abort if free space falls under 5 GiB). Do not write in the shared source tree or on shared storage. Leftover processes: stop `cassandra-stress`, the node (`nodetool drain` then kill the pid), and any test JVM; verify with `pgrep -fa 'cassandra|CassandraDaemon|ant'` that none remain. Remove `$WORK` and the data, commit log, hints and saved-caches directories. Setting `sstable_size_in_mb` to 10 creates many files; check the open-file limit (`ulimit -n`) before the run.

## C. Sources read

- /tmp/claude-20001/-proj-misconfiguration-PG0-git-repos-Misconfiguration/d3cfd622-d93d-5998-b33d-926864ab48d4/scratchpad/agent-docs/INSTRUCTIONS.md
- /tmp/claude-20001/-proj-misconfiguration-PG0-git-repos-Misconfiguration/d3cfd622-d93d-5998-b33d-926864ab48d4/scratchpad/agent-docs/playbook-autonomous.md
- /tmp/claude-20001/-proj-misconfiguration-PG0-git-repos-Misconfiguration/d3cfd622-d93d-5998-b33d-926864ab48d4/scratchpad/agent-docs/_TEMPLATE-autonomous.md
- /tmp/claude-20001/-proj-misconfiguration-PG0-git-repos-Misconfiguration/d3cfd622-d93d-5998-b33d-926864ab48d4/scratchpad/agent-in/135.md
- /users/jason92/cassandra-5.0.9/src/java/org/apache/cassandra/db/compaction/LeveledCompactionStrategy.java
- /users/jason92/cassandra-5.0.9/src/java/org/apache/cassandra/db/compaction/LeveledManifest.java
- /users/jason92/cassandra-5.0.9/src/java/org/apache/cassandra/db/compaction/LeveledCompactionTask.java
- /users/jason92/cassandra-5.0.9/src/java/org/apache/cassandra/db/compaction/writers/MaxSSTableSizeWriter.java
- /users/jason92/cassandra-5.0.9/src/java/org/apache/cassandra/db/compaction/CompactionTask.java (lines 428-442)
- /users/jason92/cassandra-5.0.9/src/java/org/apache/cassandra/db/compaction/CompactionStrategyManager.java (grep and lines 318-330)
- /users/jason92/cassandra-5.0.9/src/java/org/apache/cassandra/config/CassandraRelevantProperties.java (grep, line 604)
- /users/jason92/cassandra-5.0.9/conf/cassandra.yaml (grep, line 1251)

## D. Stage-4 feedback

`none yet`
