<!-- file: cases/max-threshold-getEstimatedTasks-l0SstableCount--autonomous.md -->
# max_threshold (compaction max_threshold, as used by the L0 estimate) — verification solution  <!-- file: cases/max-threshold-getEstimatedTasks-l0SstableCount--autonomous.md -->

| Field | Value |
|---|---|
| Entry pointer | `src/java/org/apache/cassandra/db/compaction/LeveledManifest.java:655` |
| Pinned source | `cassandra-5.0.9` |
| Session / date | Claude Sonnet 5.5 (claude-sonnet-5-5), Claude Code CLI, 2026-10-26 |
| Estimate | `negative`. The line only computes a pending-task count for the metric, from `generations.get(0).size() / max_threshold`; it allocates and bounds nothing. |
| Ground | The expression feeds `getEstimatedRemainingTasks()` (`LeveledCompactionStrategy.java:278`), which is reported as the pending-compactions metric and read by a repair-admission check (`service/ActiveRepairService.java:639`). It does not limit the bytes or sstables a compaction reads or writes, and it does not limit L0 growth. The value `max_threshold` does bound the input count of an STCS-in-L0 compaction (`LeveledManifest.java:328`, `:548-551`), but that is a different code path from line 655, and an sstable count is not a byte bound. |

## A. Constraint trace

**A1. The constraint.** The target line holds two operands.
- `cfs.getMaximumCompactionThreshold()` is the per-table compaction option `max_threshold`.
  - Kind: table-schema option, runtime-queried.
  - Declared: `schema/CompactionParams.java:55` (`Option.MAX_THRESHOLD`) with the default in `schema/CompactionParams.java:80` (`DEFAULT_MAX_THRESHOLD = 32`).
  - Read: `db/ColumnFamilyStore.java:3086-3088` returns `maxCompactionThreshold.value()`.
  - Unit: number of sstables. Default 32.
  - Setting: `CREATE/ALTER TABLE ... WITH compaction = {'class':'LeveledCompactionStrategy','max_threshold':N}`, or `nodetool setcompactionthreshold <ks> <table> <min> <max>`. No restart is needed.
- `DatabaseDescriptor.getDisableSTCSInL0()` is the JVM property `-Dcassandra.disable_stcs_in_l0` (`config/CassandraRelevantProperties.java:197`, loaded at `config/DatabaseDescriptor.java:223`). Default false. It can also be set at runtime via JMX `CompactionManager.setDisableSTCSInL0` (`db/compaction/CompactionManager.java:2353-2358`).

The traced constraint is `max_threshold`, because it is the only operand whose value is chosen by the operator and could plausibly be read as a resource limit.

**A2. What it caps.** Nominally the number of sstables in one STCS-style compaction (a disk-read and heap/off-heap-metadata amplification proxy). At line 655 it caps nothing. The compared quantity is `generations.get(0).size()`, the L0 sstable count, and the result is only added to an integer `tasks`.

**A3. Mechanism.**
1. `getEstimatedTasks(Function)` (`LeveledManifest.java:643`) sums per-level estimates `ceil(max(0, bytes_i - 1.001*maxBytesForLevel(i)) / maxSSTableSizeInBytes)` (`:648-653`).
2. Line 655: if STCS-in-L0 is enabled and L0 holds more than `max_threshold` sstables, then `l0compactions = L0size / max_threshold` (`:657`). It is added to `tasks` and `estimated[0]` (`:658-659`).
3. The result is returned through `Ints.checkedCast` (`:664`). It is only logged at trace level (`:662`) and returned.
4. Consumers: `LeveledCompactionStrategy.getEstimatedRemainingTasks()` (`:276-281`), then `CompactionStrategyManager.getEstimatedRemainingTasks()` (`:1132`), then the pending-tasks metric. `ActiveRepairService.java:639` reads `getPendingTasks()`.
5. Outcomes. If L0 is at most `max_threshold`, or STCS-in-L0 is disabled, nothing is added. If L0 is larger, the count rises. In neither case is any write, read, allocation or admission blocked.
6. No overshoot or bypass exists at this line because it is not an enforcement point. The real use of `max_threshold` is separate: the STCS-in-L0 candidate selection (`:305-327`, which triggers when L0 > the hard-coded `MAX_COMPACTING_L0 = 32` at `:62`, so it is not tied to `max_threshold`), and the L0 candidate truncation at `:548-551`. Those bound the sstable count per task (the byte total is only checked against `maxSSTableSizeInBytes` at `:557`). The estimate at 655 uses `max_threshold` while the trigger at 306 uses the constant 32, so the two diverge when `max_threshold != 32`.

**A4. Other consumers.** Disk and memory used by L0 sstables, by the memtable flush rate (which creates L0 sstables faster than compaction removes them), by `concurrent_compactors`, by `compaction_throughput`, by compaction-space headroom and by index summaries, bloom filters and compression metadata for every open sstable. None of these is governed by the line-655 value.

**A5. Evidence beyond the source.** none (source only). Possible follow-up: the Cassandra docs on LCS `max_threshold` and on `cassandra.disable_stcs_in_l0`; not relied on.

## B. Verification solution

**B1. Claim under test.** The L0 term at `LeveledManifest.java:655-659` does not limit memory or disk use. Changing `max_threshold` changes the reported estimated task count (L0size / max_threshold) but does not change the heap, off-heap or disk consumed by a node holding the same L0 backlog.

### B2. Unit tier

**B2a. Environment and build.** JDK 11, Ant. Copy the tree to local disk (for example `cp -r /users/jason92/cassandra-5.0.9 /local/c509`), then `ant jar` in the copy. Put a JUnit test beside `test/unit/org/apache/cassandra/db/compaction/LeveledCompactionStrategyTest.java` (the existing test class sets up a `ColumnFamilyStore` with LCS). Run with `ant testsome -Dtest.name=LeveledCompactionStrategyTest -Dtest.methods=<new method>`. JVM options: the test defaults (`-Xmx1g`), plus `-Dcassandra.disable_stcs_in_l0=false`.

**B2b. Knobs.** `max_threshold` in {4, 32, 128}, set with `cfs.setMaximumCompactionThreshold(n)` (this requires `min_threshold <= n`; keep `min_threshold = 4`). 32 is the default, 4 is the minimum useful value, and 128 shows the effect when the threshold is raised. The second knob is `DatabaseDescriptor.setDisableSTCSInL0(true/false)`, used as a control.

**B2c. Workload.** Create 200 small L0 sstables with flushes of 1 row each (`cfs.forceBlockingFlush` per row, with compaction disabled by `cfs.disableAutoCompaction()`), so all sstables sit in L0. The expected result is `L0size = 200`. For each setting, add the arithmetic term `200 / max_threshold`: 50, 6, 1.

**B2d. Observables and instruments.**
- `strategy.getEstimatedRemainingTasks()` (the operand).
- `cfs.getLiveDiskSpaceUsed()`.
- Heap after `System.gc()` via `Runtime.totalMemory()-freeMemory()`. This is only coarse.
- Count of files in the data directory.

The per-task byte cost cannot be observed because no compaction is run.

**B2e. Procedure.**
1. Start the test class.
2. Disable auto compaction and create the 200 L0 sstables.
3. For each `max_threshold` value, record `getEstimatedRemainingTasks()`, disk used and heap used.
4. Repeat each value with `setDisableSTCSInL0(true)`.
5. Print all results.
6. Delete the test data directories (the test harness does this on exit).

**B2f. Predictions.** Estimated tasks, with STCS-in-L0 enabled and 200 L0 sstables of near-zero size, are the byte-based term (0) plus 200 / max_threshold: 50 at 4, 6 at 32, 1 at 128. With STCS-in-L0 disabled the value is 0 for all three. Disk used and the file count are identical across all three `max_threshold` values (the same 200 sstables). Heap differs only by noise (under 5%).

**B2g. Readings.**

| Observation | Meaning |
|---|---|
| Estimate changes with `max_threshold` as predicted; disk and heap are flat | Claim confirmed (the line is a counter only). |
| Disk or heap changes monotonically with `max_threshold` | Claim refuted. |
| Estimate does not follow 200 / `max_threshold` | The trace is wrong (for example, SSTables were not all in L0, or L0 was auto-compacted). Not confirmed. |
| Estimate is 0 when STCS-in-L0 is enabled | L0 did not exceed `max_threshold` or the sstables were promoted. Limit not reached; not confirmed. |
| Positive control (see B2h) did not move | Not confirmed. |

**B2h. Controls.** Positive control: change the real cap `max_sstable_size_in_mb` (LCS option) and note that the byte-based part of the estimate and the on-disk sstable sizes change, which shows the harness can see a binding limit. Also repeat with identical `max_threshold` to measure run-to-run noise. The `disable_stcs_in_l0` toggle shows that the L0 term is the only contribution.

**Amendments to B2 (stage 4 audit, 2026-10-26; none depends on a reading; B2f and B2g keep their text).**
- **U1 (B2a, build).** The tree is a `copy-source.sh` copy of `cassandra/cassandra-5.0.9/` on local disk (never `cp` of another tree), built with `ant build-test`; the probe class is `ColumnFamilyStore`-level code in `test/unit/org/apache/cassandra/db/compaction/` and runs with `ant testsome`.
- **U2 (B2c, call names).** `forceBlockingFlush` does not exist in 5.0.9; each flush is `Util.flush(cfs)` after one `UpdateBuilder` row. The setter is `cfs.setMaximumCompactionThreshold(n)` (`ColumnFamilyStore.java:3091`; it only checks `min <= max`, and the `min_threshold` stays 4). The estimate is read from `LeveledCompactionStrategy.getEstimatedRemainingTasks()` of the unrepaired strategy.
- **U3 (B2d, B2f heap tolerance and sequence).** "Heap" is `Runtime.totalMemory()-freeMemory()` after three `System.gc()` calls. The values are run in the order 4, 32, 128, 32, 4, 128, 32 on the same 200 sstables, so the three readings at 32 give the noise. B2f's "under 5%" is read as: the spread across the three `max_threshold` values is at most the larger of 5% of the mean and the spread of the three readings at 32. Disk used = sum of `onDiskLength()` of the live sstables, `getLiveDiskSpaceUsed()`, and the count of `*-Data.db` files in the table directory.
- **U4 (B2h, positive control, named exactly).** The knob is `sstable_size_in_mb` (there is no `max_sstable_size_in_mb` in 5.0.9; `LeveledCompactionStrategy.java:52`). Two tables, `sstable_size_in_mb` = 1 and 160, each given the same 200 one-MiB L0 sstables: (a) the byte part of the estimate (`getEstimatedRemainingTasks()` with `disable_stcs_in_l0=true`, so only the byte term counts) differs between them; (b) a table with 6 overlapping L0 sstables of about 2 MiB is compacted once (`getNextBackgroundTask(0).execute`) at sizes 1 and 160 and the largest output file follows the size knob (about 1 MiB against one file holding all the data). The same `onDiskLength` instrument reads both. The control "moves" if (a) differs by more than 50 tasks and (b) the largest output at size 1 is below 1.5 MiB while at 160 it is above 10 MiB.

### B3. Cluster tier

**B3a. Environment and build.** One node, JDK 11, built with `ant jar` from a local copy. Heap `-Xms2g -Xmx2g`, `memtable_allocation_type: offheap_objects`, `data_file_directories`, `commitlog_directory`, `hints_directory` and `saved_caches_directory` all on a local disk of known size (at least 20 GB free). Set `concurrent_compactors: 1`, `compaction_throughput: 1MiB/s` (so the backlog stays in L0), and `-Dcassandra.disable_stcs_in_l0=false`.

**B3b. Knobs.** `max_threshold` in {4, 32, 128} via `ALTER TABLE ... WITH compaction = {'class':'LeveledCompactionStrategy','max_threshold':'N'}`. Same values and reasons as B2b. Control knob: `nodetool disableautocompaction` to hold L0.

**B3c. Workload.** `cassandra-stress` write (`n=20M`, 1 KB values, about 20 GB raw), or a smaller run with `nodetool flush` every 10 s to create 300+ L0 sstables. Duration: 30 minutes per setting, with the same total data for each setting. Arithmetic: 300 L0 sstables gives estimate 75 at max_threshold 4, 9 at 32 and 2 at 128.

**B3d. Observables and instruments.**
- JMX/`nodetool compactionstats` for pending tasks.
- `nodetool tablestats`: L0 sstable count (SSTables in each level), live and total disk space used.
- `du -sb` on the data directory every 30 s.
- Heap and off-heap: `jcmd <pid> GC.heap_info` and `nodetool info`; resident memory via `ps -o rss`.
- Native memory: `jcmd <pid> VM.native_memory summary` (start with `-XX:NativeMemoryTracking=summary`).

**B3e. Procedure.**
1. Build and start the node with the settings above.
2. Create the keyspace and table with LCS.
3. Set `max_threshold` to the first value.
4. Run the workload while sampling every 30 s.
5. Record pending tasks, L0 count, disk, RSS and heap.
6. Drop the keyspace and wipe the data directories.
7. Repeat for the other values.
8. `nodetool drain`, stop the node, and confirm with `ps` that no Cassandra process remains.

**B3f. Predictions.** Pending-task metric at the peak L0 backlog is about `L0count / max_threshold` plus the byte-based levels' term, so it falls by roughly 8x from 4 to 32 (when L0 count is the same). L0 count, disk used, heap and RSS have the same curves across the three settings within +/-10% (the backlog is set by flush rate versus the 1 MiB/s compaction throughput, not by `max_threshold`). Any difference comes from different compaction behavior due to STCS-in-L0 batch size, not from line 655.

**B3g. Readings.**

| Observation | Meaning |
|---|---|
| Pending tasks scale as L0count / `max_threshold`; disk, heap and RSS flat across values | Claim confirmed. |
| Disk or memory scales with `max_threshold` | Usage does follow the knob; claim refuted (the cause should then be traced to the real use at `:548-551`, not the line-655 estimate). |
| Pending tasks do not change | L0 did not exceed `max_threshold`, or STCS-in-L0 was off. Limit not reached; not confirmed. |
| Positive control (changing `compaction_throughput` or `max_sstable_size_in_mb`) does not move disk or L0 count | Harness not sensitive; not confirmed. |

**B3h. Controls.** Positive control: repeat with `compaction_throughput: 64MiB/s` (a cap known to bind): L0 backlog and disk should fall. Repeat one value twice to measure noise. Run once with `-Dcassandra.disable_stcs_in_l0=true` (or JMX `setDisableSTCSInL0`) to show the L0 term disappears from the estimate while disk and memory behavior is unchanged in kind.

**Amendments to B3 (stage 4 audit, 2026-10-26; none depends on a reading; B3f and B3g keep their text unless stated).**
- **C1 (B3a, B3c scale and layout).** 20 GB per setting does not fit the node's local disk (21 GB free) and six arms would take hours. B3c's "smaller run" is used: per arm `cassandra-stress write n=800000` (4 columns x 256 B, about 1 KB a row, `-rate threads=8 throttle=1800/s`, about 445 s) with a loop of `nodetool flush ks standard1` back to back (each call takes about 1.5 s) until the stress ends, so each arm creates at least 250 L0 sstables (target 300) and writes about 0.8 GB. Data, commit log, hints and saved caches are on a tmpfs mounted for this run (8 GiB, `/mnt/s4b10lm`). Heap `-Xms2g -Xmx2g` as in B3a; `memtable_allocation_type: offheap_objects`; `concurrent_compactors: 1`; `compaction_throughput: 1MiB/s`; `-Dcassandra.disable_stcs_in_l0=false` (true for the disable arm only). Table `ks.standard1` is created with `cqlsh` in the stress layout with `compaction = {'class':'LeveledCompactionStrategy','max_threshold':'N'}`.
- **C2 (B3e, two phases per arm).** Phase A (hold): `nodetool disableautocompaction ks standard1` before the stress and kept through the whole write; the L0 count is then the number of flushes and no compaction runs, so only the line-655 term can differ between arms. After the write: a check that no compaction ran on the table (`nodetool compactionhistory` has no `standard1` row, and the sstable count equals the L0 count; the executor's completed-task counter is not used because it counts empty background submissions), 60 s of sampling, then a live-heap class histogram (`jcmd GC.class_histogram`, total bytes) and `RssAnon`. Phase B (as B3a/B3e filed): `nodetool enableautocompaction`, compaction throughput 1 MiB/s (64 MiB/s in the control arm), 180 s of sampling, then the same histogram and `RssAnon`.
- **C3 (B3b, arms).** `max_threshold` 4, 32, 128 (arms `mt4`, `mt32`, `mt128`); `mt32b` (a second identical arm for noise); `c64` (`max_threshold` 32, throughput 64 MiB/s in phase B: the known-binding cap, B3h); `d32` (`max_threshold` 32, STCS in L0 disabled, B3h). Order: mt4, mt32, mt128, mt32b, c64, d32; one node at a time; the node is restarted and its tmpfs emptied for each arm.
- **C4 (B3d observables).** Pending tasks: the `pending tasks` line of `nodetool compactionstats` (the sum over tables; the value before the stress is the baseline and is subtracted); L0 count and per-level bytes from `nodetool tablestats ks.standard1`; disk: `du`-style sum of file sizes in the table directory (5 s) and of the whole data directory at the end of each phase; memory: `RssAnon` of the daemon (5 s), live heap by class histogram. Native Memory Tracking is not used (gap: off-heap memtable memory is JNA `malloc` and invisible to it; `RssAnon` covers it).
- **C5 (B3f arithmetic; corrected 2026-10-26, runbook defect D3).** The pending-task prediction at the end of phase A is B3f's own sum, the L0 term plus the byte term: `floor(L0count / max_threshold) + ceil(max(0, L0bytes - (long)(4 x 160 MiB x 1.001)) / 160 MiB)` (`LeveledManifest.java:648-653,185-188`), with `L0count` and `L0bytes` read from `nodetool tablestats` in the same snapshot and the levels above 0 empty. The first version of this line said the byte term is 0; that was an arithmetic error in the amendment (an arm writes about 0.9 GB, above the 640 MiB L0 target, so the byte term is 2), found when the first full arm (`mt4`) read pending 81 against 79 (`floor(317/4)`; byte term 2 explains the 2). The arm was discarded; the cluster tier restarted from its beginning; B3f and B3g text is unchanged. In the disable arm the expected value is the byte term alone.
- **C6 (B3g, reading of the second row).** B1 is about the line-655 term. Row 2 ("disk or memory scales with `max_threshold`") is judged on phase A. If usage differs between values only in phase B, where compaction runs, it is the real use of `max_threshold` (`LeveledManifest.java:328`, `:548-551`), a different path: the line-655 claim is still **Confirmed**, and the phase B differences are recorded in the results file as a separate finding. Row 3 is "pending tasks equal the baseline at phase A's end for an arm that should show L0 over `max_threshold`". "Flat" means the spread across mt4, mt32, mt128 at phase A's end is within 10% (disk, RssAnon, live heap) and not larger than 2 x the spread between mt32 and mt32b plus 2% of the mean.
- **C7 (B3h control reading).** The control moves if, at phase B's end, the L0 count of `c64` is below half of that of `mt32` and `mt32b` (the known cap, compaction throughput, binds the backlog).

**B4. Risks and cleanup.** Disk: keep all Cassandra directories on local disk of known size and delete them after each run (monitor with `df`). No shared storage is used and no files are added to the shared source tree (work only in the local copy). Stop the node with `nodetool drain` then kill; check `ps -ef | grep CassandraDaemon` and `jps` show nothing; remove any `cassandra-stress` processes.

## C. Sources read

- /users/jason92/writeup-A/playbook-autonomous.md
- /users/jason92/writeup-A/_TEMPLATE-autonomous.md
- src/java/org/apache/cassandra/db/compaction/LeveledManifest.java (lines 60-90, 180-190, 300-335, 610-700)
- src/java/org/apache/cassandra/db/compaction/LeveledCompactionStrategy.java (lines 270-290)
- src/java/org/apache/cassandra/db/compaction/CompactionManager.java (2200-2215, 2345-2360)
- src/java/org/apache/cassandra/db/ColumnFamilyStore.java (3080-3092)
- src/java/org/apache/cassandra/config/CassandraRelevantProperties.java, config/DatabaseDescriptor.java (grep hits and 2585-2595)
- src/java/org/apache/cassandra/schema/CompactionParams.java (grep hits)
- grep results across src/java for `getEstimatedRemainingTasks`, `getPendingTasks`, `getMaximumCompactionThreshold`, `DISABLE_STCS_IN_L0`

## D. Stage-4 feedback

**2026-10-26 (stage 4, [results](../../stage4-runtime-verification/results/max-threshold-getEstimatedTasks-l0SstableCount--autonomous.md)).** Unit **Confirmed** — does not cap; cluster **Confirmed** — does not cap. Outcome class: true negative (estimate negative, the claim held). Unit: 200 L0 sstables, estimate 50 / 6 / 1 at `max_threshold` 4 / 32 / 128 and 0 with STCS-in-L0 off, disk and heap identical. Cluster (six arms of about 300 L0 sstables, 0.93 GB, compaction held in phase A): pending tasks = `floor(L0/max_threshold)` + a byte term of 2 (77+2, 9+2, 2+2), and with STCS-in-L0 off only the byte term (2); table bytes, `RssAnon` and live heap flat across the three values within 1%. Positive controls moved: output file size follows `sstable_size_in_mb` (1.0 vs 12.2 MiB), and 64 MiB/s compaction throughput emptied the L0 backlog (1 sstable against 268-290).

The audit corrected the file (dated amendments U1-U4 in B2, C1-C7 in B3): the setter and flush call names, the knob name `sstable_size_in_mb` (the file said `max_sstable_size_in_mb`, which does not exist in 5.0.9), the scale of the cluster workload, and C5 (the byte-based term of the estimate is part of the expected pending count; it was 2 at 0.93 GB, which the first version of C5 had set to 0). B2f/B2g/B3f/B3g are unchanged.

Separate finding, outside the line-655 claim: in phase B (compaction on) the table directory's peak bytes rose 54 / 94 / 172 MB above the start at `max_threshold` 4 / 32 / 128. That is the in-flight output of an STCS-in-L0 compaction whose input count `max_threshold` bounds at `:328` and `:548-551`, a different path from the estimate at `:655`. Stage 3 note: the estimate at `:655` uses `max_threshold` while the STCS-in-L0 trigger at `:306` uses the constant `MAX_COMPACTING_L0 = 32` (A3 step 6), so the two diverge when `max_threshold != 32`; the runs saw 79 and 4 pending tasks at L0 counts of 308 and 310 with no change in resource use.
