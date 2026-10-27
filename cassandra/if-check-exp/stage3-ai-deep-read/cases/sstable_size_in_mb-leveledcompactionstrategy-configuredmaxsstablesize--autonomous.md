<!-- file: cases/sstable_size_in_mb-leveledcompactionstrategy-configuredmaxsstablesize--autonomous.md -->
# sstable_size_in_mb — verification solution  <!-- file: cases/sstable_size_in_mb-leveledcompactionstrategy-configuredmaxsstablesize--autonomous.md -->

| Field | Value |
|---|---|
| Entry pointer | [`LeveledCompactionStrategy.java:78`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/compaction/LeveledCompactionStrategy.java#L78) (`if (configuredMaxSSTableSize >= 1000)`) |
| Pinned source | `cassandra-5.0.9` |
| Session / date | Claude Code CLI (Agent-tool subagent), 2026-10-27 |
| Estimate | `negative`. The line-78 check only logs a warning. The option sets the target size of one compaction output file and the per-level capacity, not a bound on total disk or memory. |
| Ground | The check at line 78 calls `logger.warn` and nothing else, so it enforces nothing. The option feeds the output-file rollover threshold of leveled compaction and the level-size scoring, which decide when and how data is moved between levels. Total disk used still grows with the data written, and level 0 and the last level can exceed their nominal size. A partition is never split, so one file can exceed the value. |

> **Link rule.** The constraint declaration (A1) and the if statement (this Entry pointer row and A3) are permalinks at tag `cassandra-5.0.9`. Other citations are plain `file:line` relative to `src/java/org/apache/cassandra/` unless a full path is given.

## A. Constraint trace

**A1. The constraint.** `sstable_size_in_mb`: a per-table compaction sub-option of `LeveledCompactionStrategy` (CQL `compaction = {'class': 'LeveledCompactionStrategy', 'sstable_size_in_mb': N}`). It is not a cassandra.yaml entry. The option key is declared at [`LeveledCompactionStrategy.java:52`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/compaction/LeveledCompactionStrategy.java#L52) (`SSTABLE_SIZE_OPTION = "sstable_size_in_mb"`).

- **Unit:** MiB. It is stored as `int maxSSTableSizeInMiB` (`db/compaction/LeveledCompactionStrategy.java:60`, assigned at line 97) and converted to bytes at line 291 (`maxSSTableSizeInMiB * 1024L * 1024L`).
- **Default:** 160, hard-coded as the initial value of the local `configuredMaxSSTableSize` at line 67 and used when the option key is absent (line 73).
- **How it is set:** per table through CQL `CREATE TABLE` or `ALTER TABLE ... WITH compaction = {...}`. Validation is in `validateOptions` (lines 570-621): it must parse as a base-10 int (lines 579, 585-587) and be at least 1 (lines 580-583). The byte size times `fanout^(MAX_LEVEL_COUNT-1)` must not exceed `Long.MAX_VALUE` (lines 610-616), and `Math.multiplyExact` overflow is rejected at lines 618-620. Whether `ALTER TABLE` takes effect on a running node without restart (the strategy being re-instantiated) is **not verified** in the source; the cluster tier checks it empirically (B3e).
- **Related warning switch:** the JVM property `cassandra.tolerate_sstable_size` (`config/CassandraRelevantProperties.java:604`) is read into a `private static final boolean tolerateSstableSize` at `db/compaction/LeveledCompactionStrategy.java:53`, so it is fixed at class load and needs a restart. When true, the warning block (lines 76-84) is skipped.
- **Hard-coded thresholds at the entry point:** >= 1000 (line 78, warning at lines 79-80) and < 50 (line 81, warning at lines 82-83). The warning for < 50 cites a CASSANDRA-5727 test in the log text (the string is in the source at line 82; the issue content itself is not verified).

**A2. What it caps.** Nominally the disk size of one SSTable file written by a leveled compaction (the roll-over threshold of the output writer), and indirectly the per-level capacity: level 0 is 4 x the value, level n >= 1 is fanout^n x the value (`db/compaction/LeveledManifest.java:185-192`). The quantity the code compares against the limit is the number of bytes already written to the current output SSTable (`getEstimatedOnDiskBytesWritten()`, `db/compaction/writers/MaxSSTableSizeWriter.java:78`), and the total bytes of a level against its capacity (`LeveledManifest.java:254-258`). It does not cap total table disk, off-heap or heap. It is an aggregate file-size target, not a resource cap.

**A3. Mechanism.**
1. Constructor parses the option: [`LeveledCompactionStrategy.java:78`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/compaction/LeveledCompactionStrategy.java#L78) is `if (configuredMaxSSTableSize >= 1000)` (the value was parsed at line 75). The only effect of either outcome is a `logger.warn` (lines 79-80); false does nothing. Nothing is rejected, clamped or throttled. With `cassandra.tolerate_sstable_size=true` even the warning is skipped (line 76).
2. The value is stored (line 97) and handed to `new LeveledManifest(cfs, maxSSTableSizeInMiB, ...)` (line 101), where it becomes `maxSSTableSizeInBytes` (`LeveledManifest.java:84`).
3. Candidate selection: for levels >= 1 the score is level bytes (minus compacting) divided by `maxBytesForLevel` (`LeveledManifest.java:253-255`); score > 1.001 triggers a compaction (line 258). L0 candidates are left alone until their total exceeds one `maxSSTableSizeInBytes` (line 557). The candidate carries `maxSSTableBytes` into the task (lines 281, 301 of the manifest; line 172 of the strategy).
4. The task builds its writer: `MaxSSTableSizeWriter` (`LeveledCompactionTask.java:53`) or, for a major compaction, `MajorLeveledCompactionWriter` (line 52).
5. Before each partition, `CompactionAwareWriter.append` calls `maybeSwitchWriter` (`db/compaction/writers/CompactionAwareWriter.java:138-140`, 166-173), which calls `shouldSwitchWriterInCurrentLocation`. `MaxSSTableSizeWriter` returns `currentWriter().getEstimatedOnDiskBytesWritten() > maxSSTableSize` (line 78); the Major writer does the same at `MajorLeveledCompactionWriter.java:74-75`. A true result closes the current file and starts a new one.

**Outcomes, bypasses and overshoot.**
- The roll-over test runs only at partition boundaries, so one output file can exceed the value by up to a whole partition (a single huge partition is never split).
- The comparison is strict (`>`) on an estimate, so files can slightly exceed the value.
- Memtable flushes write to level 0 and are not bounded by this option (flush path not traced here; **not verified**).
- User-defined compaction of more than one SSTable uses `Long.MAX_VALUE` as `maxSSTableBytes` (`LeveledCompactionStrategy.java:211`), so the output is not split, up to one unbounded file.
- Level capacities are soft: compaction lags under write pressure, so levels and L0 can exceed their nominal size.
- Total disk is unbounded by the option: more data means more files and more levels.

**A4. Other consumers.** Disk: commit log, hints, snapshots, other tables' SSTables, tombstones that cannot be purged, and the temporary space for in-flight compactions (output plus inputs coexist until the transaction commits). Heap/off-heap: per-SSTable bloom filters, index summaries, and compression metadata scale with the number of files and keys, not with this option directly (smaller files mean more files and more per-file metadata; the direction of that effect is a hypothesis, not traced here). Memtables and the key/chunk caches are governed by their own settings.

**A5. Evidence beyond the source.**
- Cassandra docs, LeveledCompactionStrategy options: https://cassandra.apache.org/doc/5.0/cassandra/managing/operating/compaction/lcs.html (consulted from memory of the public docs; the exact page text was not re-read here, so treat it as not verified).
- Unit test class that exercises the strategy: `test/unit/org/apache/cassandra/db/compaction/LeveledCompactionStrategyTest.java` (file exists; its contents were not read).
- CASSANDRA-5727 appears only in the log string at line 82; not verified further.

## B. Verification solution

**B1. Claim under test.** The `sstable_size_in_mb` check at line 78 only logs a warning and does not cap memory or disk. Specifically, (a) the option changes the target size of compaction output files but not the total on-disk size of a table holding the same data, and (b) setting a very large value (or `-Dcassandra.tolerate_sstable_size=true`) is accepted and changes no resource-protecting behaviour. Refuted if total table disk usage tracks the option value rather than the data volume, or if the node rejects or clamps large values.

### B2. Unit tier

**B2a. Environment and build.** JDK 11, Ant. Copy the tag to local disk (e.g. `/local/scratch/$USER/cassandra-5.0.9`; never build in the shared tree). `ant jar` then `ant testsome -Dtest.name=org.apache.cassandra.db.compaction.LeveledCompactionStrategyTest` to confirm the harness works. Put the new test class next to it in `test/unit/org/apache/cassandra/db/compaction/` as `SstableSizeOptionProbeTest` (name chosen here; it does not exist). JVM options come from the `ant` test target defaults; add `-Dcassandra.tolerate_sstable_size=true` only for the tolerate run, in a separate JVM.

**B2b. Knobs.** `sstable_size_in_mb` set through the table's `CompactionParams` options: 1, 49, 50, 160 (default, option absent), 999, 1000, 4096, and 2147483647 (the int maximum, expected to hit the overflow rejection in validation). Chosen to straddle the 50 and 1000 warning thresholds and the validation limits. Second knob: `cassandra.tolerate_sstable_size` false/true (separate JVM per value because the field is static final, line 53).

**B2c. Workload.** (1) Construction and validation only: build `LeveledCompactionStrategy(cfs, options)` for each value and call `LeveledCompactionStrategy.validateOptions`. (2) Writer behaviour: create a test table with LCS, write partitions of fixed size (e.g. 1 KiB rows x 1000 rows per partition) into several L0 SSTables via `Keyspace`/`ColumnFamilyStore` flushes, then run a `LeveledCompactionTask` with `maxSSTableBytes = N MiB`. To reach the threshold, total input must exceed N MiB: for N = 1 use about 5 MiB of data (expect about 5 output files); for N = 50 use about 200 MiB. Values of N of 1000 and above are tested only for construction and `getMaxSSTableBytes()` (no 1 GiB data needed). (3) Overshoot: one partition larger than N (e.g. N = 1, a 3 MiB partition) to show that the file exceeds N.

**B2d. Observables and instruments.**
- Warning emitted at lines 79-80 / 82-83: capture logback output for the `LeveledCompactionStrategy` logger (a test appender) and count messages.
- `strategy.getMaxSSTableBytes()` (line 289) equals N x 1048576.
- Number and on-disk size of output SSTables after the compaction (`SSTableReader.onDiskLength()` for each, `cfs.getLiveSSTables()`), and their sum (total bytes), and per-file max.
- `validateOptions` result (accepted or `ConfigurationException`).
- Not observable directly: the writer's internal estimate `getEstimatedOnDiskBytesWritten()` mid-run; only final file sizes are read.

**B2e. Procedure.**
1. Copy the tree, `ant jar`.
2. Write the probe test. For each N: create a keyspace and table with `compaction = {'class':'LeveledCompactionStrategy','sstable_size_in_mb':'N'}`, attach a log appender, construct the strategy (`cfs.getCompactionStrategyManager()` or direct construction as the existing test does), record warnings and `getMaxSSTableBytes()`.
3. For N in {1, 50, 160}: write data, flush into at least 4 L0 SSTables, run the compaction synchronously (`CompactionManager.instance.performMaximal(cfs, false)` or the strategy's `getNextBackgroundTask`), then read output sizes.
4. For the overshoot case, write the single large partition with N = 1.
5. Repeat the warning checks in a second JVM with `-Dcassandra.tolerate_sstable_size=true`.
6. Run: `ant testsome -Dtest.name=org.apache.cassandra.db.compaction.SstableSizeOptionProbeTest`.

**B2f. Predictions (before any run).**
- N = 1000, 4096: one warning "probably a bad idea" each; no exception; `getMaxSSTableBytes()` = N x 2^20.
- N = 1, 49: one warning about performance below 50; none at 50 and 160 and 999.
- N = 2147483647: `validateOptions` throws `ConfigurationException`.
- Tolerate = true: zero warnings for every N.
- Compaction output: number of files about ceil(total / N); per-file size close to N MiB except the last file; total bytes of output is the same for every N (equal to input after dedup, within a few percent for metadata).
- Overshoot: the file holding the large partition is larger than N.

**B2g. Readings.**

| Observation | Meaning |
|---|---|
| Warnings as predicted and large N accepted | Line 78 is a log-only check (claim consistent). |
| A large N is rejected or clamped (apart from the overflow value) | Claim refuted: there is enforcement beyond a warning. |
| Per-file size follows N, total output bytes flat across N | Option governs file granularity, not total usage (claim confirmed). Per-file size is the positive control: the option binds file size. |
| Total output bytes grows or shrinks with N | Claim refuted. |
| Per-file size does not follow N, or the compaction produces one file for every N | Control did not move: not confirmed. Check the input was larger than N. |
| Limit never reached (input smaller than N) | Not confirmed for that N. |
| A file larger than N holding the big partition | Expected overshoot; the option is not a hard cap. |

**B2h. Controls.** Positive control: per-file size at N = 1 versus N = 50 versus N = 160 on the same input shows the option does bind something. Same input data and same random seed for every N. Run each N after a fresh `truncate`. Tolerate run isolates the warning from other log lines. Repeat each case three times to rule out timing differences from flush.

### B3. Cluster tier

**B3a. Environment and build.** One node, JDK 11, built from a local copy of the tag (`ant jar`). Data, commit log, hints and saved caches under a local directory of known size (for example `/local/scratch/$USER/c1/{data,commitlog,hints,saved_caches}` on a volume of at least 40 GB free; verify with `df`). `cassandra.yaml`: `num_tokens: 1`, `concurrent_compactors: 2`, `compaction_throughput: 0MiB/s`, `memtable_heap_space: 256MiB` (keep flushes frequent), `auto_snapshot: false`. Heap `-Xms2G -Xmx2G` in `conf/jvm11-server.options`. Use a separate cluster directory (own `CASSANDRA_CONF`) per run.

**B3b. Knobs.** The table option `sstable_size_in_mb` at 5, 50, 160 and 1000, each on its own table in the same run (so same node, same data): `t_5`, `t_50`, `t_160`, `t_1000`. Plus a run with `-Dcassandra.tolerate_sstable_size=true` appended to `JVM_EXTRA_OPTS` and a control run without it. Values chosen to give many, several, default and a few files for about 3 GB of data per table, and to cross the 1000 warning.

**B3c. Workload.** Same data into each table via `cassandra-stress` (shipped with the tree, `tools/bin/cassandra-stress`) or a CQL loop: 3,000,000 partitions x about 1 KiB each (about 3 GB logical per table, compressed on disk less), random non-repeating keys, so no overwrites; then wait until pending compactions reach 0. Arithmetic: at 5 MiB per file, about 600 files in the top levels; at 1000 MiB, level 1 holds up to 10 x 1000 MiB so most data sits in L0/L1 with few files, so the options are distinguishable. Duration: load about 30-60 minutes per table plus compaction drain time, depending on hardware. Positive control for a different known cap (see B3g): run the same load while varying `memtable_heap_space` (a cap known to bind heap; the yaml key is declared at `config/Config.java:187`).

**B3d. Observables and instruments.**
- Total disk of each table: `du -sb` on its data directory and `nodetool tablestats <ks>.<t>` "Space used (live)", sampled every 60 s.
- Per-file sizes: `ls -l *-Data.db` per table, and `nodetool tablestats` "SSTable count", "SSTables in each level" and `nodetool tablestats` "Max SSTable size" (field `maxSSTableSize`, `tools/nodetool/stats/TableStatsPrinter.java:89`).
- Heap: `jstat -gc <pid> 5000` and `nodetool info` (heap and off-heap); off-heap from `nodetool tablestats` bloom filter and index summary off-heap lines.
- Log lines containing "Max sstable size of" in `system.log`.
- Not observable directly: the writer's internal estimate; only final files.

**B3e. Procedure.**
1. Copy the tree to local disk, `ant jar`, set the directories and options of B3a.
2. Start the node; record PID.
3. Create keyspace (`SimpleStrategy`, RF 1) and four tables with identical schema, differing only in `sstable_size_in_mb`. Record the warning lines at creation (expect one for `t_1000`, none for others except `t_5`, which is < 50).
4. Load identical data into each table. Sample instruments of B3d for the whole run.
5. Wait until `nodetool compactionstats` shows 0 pending, then record the final per-file sizes, level counts and total disk per table.
6. Optionally exercise runtime change: `ALTER TABLE ks.t_160 WITH compaction = {'class':'LeveledCompactionStrategy','sstable_size_in_mb':'20'}`, load another 1 GB, and see whether newly written files follow the new value (answers the restart question left open in A1).
7. Restart the node with `-Dcassandra.tolerate_sstable_size=true`, re-create `t_1000_b` and confirm no warning.
8. Positive control run: repeat the load into `t_160` with `memtable_heap_space` of 64MiB, 256MiB and 1024MiB and record heap use (B3d). Stop the node (`nodetool drain` then kill the PID) and confirm with `pgrep -f CassandraDaemon`.

**B3f. Predictions (before any run).**
- Final total live space of the four tables within about 10% of each other (same data), with no monotonic relation to the option value.
- Median file size in the top levels: about 5 MiB, 50 MiB, 160 MiB for `t_5`, `t_50`, `t_160`; `t_1000` has fewer, larger files (up to about 1000 MiB each), possibly with most data in L0/L1 if the load ends early.
- Number of files: `t_5` > `t_50` > `t_160` > `t_1000`, roughly inverse to the option.
- Warnings in `system.log` for `t_5` and `t_1000` only (and none with tolerate=true).
- Heap use for the same load differs by far less across the four tables than the difference caused by the `memtable_heap_space` control (positive control).
- Peak transient disk during compaction rises with the option (a larger compaction unit holds inputs and outputs at once); it is a transient, not a cap.

**B3g. Readings.**

| Observation | Meaning |
|---|---|
| Totals flat across tables, file size and count follow the option | Option governs file granularity only; usage does not follow it (claim confirmed). |
| Total live space follows the option monotonic (e.g. smaller option, much smaller total) beyond metadata differences | Claim refuted. |
| `t_1000` accepted, only a warning; files larger than for others | Line 78 is log-only (confirmed). |
| `t_1000` rejected, or its files are clamped at a lower size | Claim refuted: enforcement exists. |
| Heap moves with `memtable_heap_space` but not with the option | Positive control moved; option does not cap heap (confirmed). |
| Heap does not move with `memtable_heap_space` either | Control did not move: not confirmed; fix the load or the sampling. |
| Compaction still has pending tasks at the end, so levels not at steady state | Limit not reached: not confirmed; extend the wait. |
| ALTER changes later files without restart | Answers the A1 open question; neutral for the claim. |

**B3h. Controls.** Same node, same data and the same load order for all tables, so hardware, JVM and data are held fixed. Interleave the loads (round robin by batch) so time-varying conditions affect all tables equally. Include a table at the default (option absent) as another reference. Run `nodetool compact`-free (no manual compaction) so the background strategy is what is measured. Repeat once from a clean data directory to check reproducibility. Positive control is the `memtable_heap_space` sweep (B3c, B3e step 8).

**B4. Risks and cleanup.** Disk: 4 tables x about 3 GB, plus compaction transient (inputs plus outputs), plus commit log: budget at least 30 GB on the local volume and check `df` before each phase; if the volume is under 10 GB free, abort. Never use shared storage. A 1000 MiB unit makes transient space large, so keep an eye on it. Processes: record the PIDs of Cassandra and any `cassandra-stress` or `jstat` started; at the end run `pgrep -fl "CassandraDaemon|cassandra-stress|jstat"` and kill leftovers. Unit tier: the test creates data under the build's `build/test` directories in the local copy; remove it with `ant clean` or `rm -rf` of the local copy. Cleanup: delete the local data, commit log, hints, saved-caches directories and the local source copy; the shared source tree is never modified.

## C. Sources read

- `/users/jason92/cassandra-5.0.9/src/java/org/apache/cassandra/db/compaction/LeveledCompactionStrategy.java` (lines 45-125, 140-215, 280-300, 570-630)
- `/users/jason92/cassandra-5.0.9/src/java/org/apache/cassandra/config/CassandraRelevantProperties.java` (line 604, via grep)
- `/users/jason92/cassandra-5.0.9/src/java/org/apache/cassandra/db/compaction/LeveledManifest.java` (lines 176-195, 245-262, 548-562, plus grep hits)
- `/users/jason92/cassandra-5.0.9/src/java/org/apache/cassandra/db/compaction/LeveledCompactionTask.java` (lines 40-108)
- `/users/jason92/cassandra-5.0.9/src/java/org/apache/cassandra/db/compaction/writers/MaxSSTableSizeWriter.java` (lines 60-96)
- `/users/jason92/cassandra-5.0.9/src/java/org/apache/cassandra/db/compaction/writers/MajorLeveledCompactionWriter.java` (lines 40-85)
- `/users/jason92/cassandra-5.0.9/src/java/org/apache/cassandra/db/compaction/writers/CompactionAwareWriter.java` (lines 136-190)
- `/users/jason92/cassandra-5.0.9/src/java/org/apache/cassandra/config/Config.java` (line 187, via grep)
- `/users/jason92/cassandra-5.0.9/src/java/org/apache/cassandra/tools/nodetool/stats/TableStatsPrinter.java` (line 89, via grep)
- `/users/jason92/cassandra-5.0.9/conf/cassandra.yaml` (grep for memtable_heap_space)
- Grep hits (no full read) over `src/java` for `getMaxSSTableBytes` and `maxSSTableSize`.
- Existence check only: `test/unit/org/apache/cassandra/db/compaction/LeveledCompactionStrategyTest.java`

## D. Stage-4 feedback

`none yet`
