# sstable_size_in_mb (LCS) — verification solution  <!-- file: cases/sstable-size-in-mb-getnextlevel-candidate-total-bytes--autonomous.md -->

| Field | Value |
|---|---|
| Entry pointer | `src/java/org/apache/cassandra/db/compaction/LeveledManifest.java:678` |
| Pinned source | `cassandra-5.0.9` |
| Session / date | Claude Sonnet 5.5 (claude-sonnet-5-5), Claude Code CLI (version not reported to the agent), 2026-10-24 |
| Estimate | `negative`: `sstable_size_in_mb` is a target size for each compaction output sstable and the unit for the level quotas. It is not a cap on the disk a node or table uses. The comparison at line 678 only decides whether a small L0 compaction output stays in L0 or is promoted. |
| Ground | (1) The line-678 check picks a level and allocates no memory or disk. (2) The per-sstable size is only checked between partitions (`MaxSSTableSizeWriter.java:76-78`), so one large partition can exceed it. (3) L0 STCS compactions pass `Long.MAX_VALUE` (`LeveledManifest.java:209,312`), so their output is unbounded. (4) Level "maximums" (`maxBytesForLevel`, `:185-193`) are compaction triggers, not limits: data written faster than compaction keeps up simply accumulates, and the top level only logs a warning (`:262-267`). (5) Total table disk is set by the data volume, overwrites, tombstones and compaction backlog, so it is not bounded by the option. |

## A. Constraint trace

**A1. The constraint.** `sstable_size_in_mb`, a table-level LCS compaction sub-option.
- Kind: per-table schema option (CQL `compaction = {'class': 'LeveledCompactionStrategy', 'sstable_size_in_mb': N}`). It is not a `cassandra.yaml` entry and not a JVM property.
- First declared: `LeveledCompactionStrategy.java:52` (`SSTABLE_SIZE_OPTION = "sstable_size_in_mb"`). It is parsed at `:73-75`.
- Unit: MiB. It is stored as `maxSSTableSizeInMiB` (`:60`, `:97`) and converted to bytes at `LeveledCompactionStrategy.java:291` and `LeveledManifest.java:84` (`maxSSTableSizeInMB * 1024L * 1024L`). The `maxSSTableSizeInBytes` field is declared at `LeveledManifest.java:76`, and line 678 is its use in `getNextLevel`.
- Default: 160 MiB, a hard-coded literal (`LeveledCompactionStrategy.java:67`). Note that `validateOptions` falls back to `"1"` when the option is absent (`:576`). That is only for validation and does not change the runtime default.
- Valid range: integer >= 1 (`:580-583`). The product with `fanout_size^(MAX_LEVEL_COUNT-1)` must fit in a long (`:607-621`, `MAX_LEVEL_COUNT = 9` at `LeveledGenerations.java:57`). Values >= 1000 or < 50 only log warnings (`:76-84`) unless `-Dcassandra.tolerate_sstable_size=true` (`CassandraRelevantProperties.java:604`, read at `LeveledCompactionStrategy.java:53`) silences them.
- How it is set: `CREATE TABLE ... WITH compaction = {...}` or `ALTER TABLE`. An ALTER reloads the strategy, so no node restart is needed. Existing sstables are not rewritten and only pick up the new size as they are compacted.
- Related knob: `fanout_size` (default 10, `:56`, `:54`), which scales the level quotas.

**A2. What it caps.** Disk, indirectly, and only as a granularity: the target on-disk size of each sstable produced by an LCS compaction, plus the level byte quotas derived from it.
- The quantity compared at the target line is `SSTableReader.getTotalBytes(sstables)`, the sum of on-disk sstable bytes of the compaction candidates, against `maxSSTableSizeInBytes`.
- Other comparisons using the same operand: level score (`LeveledManifest.java:254-258`), L0 candidate selection (`:557`), the pending-task estimate (`:651`), and the writer's switch threshold (`MaxSSTableSizeWriter.java:78`, `MajorLeveledCompactionWriter.java:75`).

**A3. Mechanism.**
1. `LeveledCompactionStrategy` constructor reads the option (`:67-75`) and creates `new LeveledManifest(cfs, maxSSTableSizeInMiB, levelFanoutSize, localOptions)` (`:101`). The manifest computes bytes (`LeveledManifest.java:84`).
2. `getCompactionCandidates()` (`:199`) scores each level above L0 as `remainingBytes / maxBytesForLevel(i)` (`:253-255`). `maxBytesForLevel` is `4 * size` for L0 and `fanout^level * size` otherwise (`:185-193`). A score above 1.001 picks candidates (`:258, :274`) and calls `getNextLevel(candidates)` (`:277`). L0 candidates come from `getCandidatesFor(0)` and then `getNextLevel` (`:293, :301`).
3. `getCandidatesFor(0)` (`:502-572`) collects L0 sstables up to `cfs.getMaximumCompactionThreshold()` (`:548-553`). If their total is at most `maxSSTableSizeInBytes` (`:557`), it does not add L1 overlap, so the compaction is L0 to L0.
4. **Target line (`:667-688`).** `getNextLevel` takes the min and max level of the inputs. If all inputs are L0 and their total bytes are below `maxSSTableSizeInBytes` (`:678`), the output level is 0 (`:680`). Otherwise the output level is `max+1` when min == max, else `max` (`:684`), with `assert newLevel > 0` (`:685`). So the check only picks the destination level and has no limit-reached outcome.
5. The candidate carries `maxSSTableBytes` (`:281, :301`) into `LeveledCompactionTask` (`LeveledCompactionStrategy.java:172`), which builds `MaxSSTableSizeWriter` (`LeveledCompactionTask.java:53`). That writer starts a new output sstable when `getEstimatedOnDiskBytesWritten() > maxSSTableSize` (`MaxSSTableSizeWriter.java:76-78`). The test runs per partition boundary (`shouldSwitchWriterInCurrentLocation(DecoratedKey)`).
6. The task also bounds the space it needs: `getExpectedWriteSize()` is `min(maxSSTableSize, ...)` (`:91-95`), which is used for the free-disk check. `reduceScopeForLimitedSpace` (`LeveledCompactionTask.java:67-107`) drops the largest L0 input when there is not enough space.

Bypasses and overshoot:
- A single partition larger than the target cannot be split, so the output sstable is larger.
- L0 STCS candidates use `Long.MAX_VALUE` (`LeveledManifest.java:209, :312`), giving unbounded outputs.
- `getUserDefinedTask` for L0 uses `Long.MAX_VALUE` (`LeveledCompactionStrategy.java:211`).
- `getMaximalTask` uses `MajorLeveledCompactionWriter` with `maxSSTableSize` but a different per-level cutoff (`MajorLeveledCompactionWriter.java:75-78`).
- Streamed, repaired or bootstrapped sstables and flushes are not size-capped by this option. Flushed L0 sstable size follows memtable size.
- Level quotas are only compaction triggers. A backlog lets levels exceed them without bound (`LeveledManifest.java:258-267` only warns for the top level).

**A4. Other consumers.** Commit log, hints, snapshots, other tables' sstables, compaction temporary files (inputs plus outputs coexist until the transaction commits), tombstones and overwritten data not yet compacted away, secondary index and materialized view sstables, and the OS page cache. None of these are under this option's control.

**A5. Evidence beyond the source.** None used. Comments in the tree (`LeveledCompactionStrategy.java:82` references CASSANDRA-5727) were read but no external page was fetched.

## B. Verification solution

**B1. Claim under test.** A node's or table's on-disk size does not follow `sstable_size_in_mb`. The option sets only the target size of each compacted sstable (and the level quotas), so for the same data and workload, total table disk after compaction settles to nearly the same value across option values (within about 10%, set by compaction overhead), and individual sstables can be larger than the option (large partitions, L0 STCS). The line-678 check only picks a level: a compaction whose inputs are all in L0 and total below the option stays in L0, otherwise it goes to a higher level.

### B2. Unit tier

**B2a. Environment and build.**
- JDK 11, Ant. Copy the tree to local disk, e.g. `rsync -a ~/cassandra-5.0.9/ /local/scratch/c509-unit/`. Never build in the shared tree.
- Build: `cd /local/scratch/c509-unit && ant jar` (and `ant build-test` for test classes).
- Test source: a new class `test/unit/org/apache/cassandra/db/compaction/LCSSizeProbeTest.java` in the local copy, in the style of `LeveledCompactionStrategyTest` (using `SchemaLoader`, `Keyspace.open`, and `LeveledManifest`/`LeveledCompactionStrategy` access from the same package for package-private methods).
- Run: `ant testsome -Dtest.name=org.apache.cassandra.db.compaction.LCSSizeProbeTest`. Use JVM args `-Xmx1g` and a `build/test/cassandra` data dir on local disk of known free space (>= 5 GiB).

**B2b. Knobs.** `sstable_size_in_mb` in {1, 5, 20, 160}, set through the table's `compaction` map in the test schema (`KeyspaceParams.simple(1)` plus `.compaction(CompactionParams.lcs(Collections.singletonMap("sstable_size_in_mb", "<N>")))`). Values chosen to straddle the data volume: small values trigger many levels and splits, 160 (default) keeps the test data in L0. Second factor: input mix (all L0 / mixed L0+L1).

**B2c. Workload.** Create several sstables of known on-disk size using `Mutation` writes plus `cfs.forceBlockingFlush()`. Pad values to a known size (e.g. 1 KiB values x 2000 rows per flush gives roughly 2 MiB per sstable; check with `getTotalBytes`). Two input sets:
- Set A: 3 L0 sstables totalling about 0.8 x N MiB (below the limit).
- Set B: 3 L0 sstables totalling about 1.5 x N MiB (above the limit), for N = 1 or 5.

For N=160 with 2 MiB flushes, both sets are far below the limit, which acts as a "limit never reached" row.

**B2d. Observables and instruments.**
- `manifest.getNextLevel(sstables)` return value (direct call; it is public).
- `SSTableReader.getTotalBytes(sstables)` and `maxSSTableSizeInBytes` (via `strategy.getMaxSSTableBytes()`, `LeveledCompactionStrategy.java:289`).
- Output sstables of a `LeveledCompactionTask` run through `cfs.forceMajorCompaction()` or by invoking `getNextBackgroundTask(gcBefore).execute(...)`: count and each `onDiskLength()`.
- One oversized partition (single partition key with ~3x N MiB of clustering rows) to show an output sstable larger than N.
- Cannot be observed: real process heap/disk effect (that is the cluster tier).

**B2e. Procedure.**
1. Build as above.
2. For each N, create the table with the option, write and flush to make Set A, and record `getTotalBytes`, `getMaxSSTableBytes`, and `getNextLevel(setA)`.
3. Repeat for Set B.
4. Run the background compaction on Set B and list output sstable count, sizes and levels.
5. Add one table (N=5) holding one ~15 MiB partition plus small partitions; compact and list sizes.
6. Add a mixed-level case: put one sstable at L1 with `sstable.mutateLevelAndReload(1)` and call `getNextLevel` on {L0, L1}.
7. Clean up the data directory (B4).

**B2f. Predictions.** (stated before any run)
- Set A (total < N MiB, all L0): `getNextLevel == 0`. Set B (total > N MiB, all L0): `getNextLevel == 1`.
- The threshold equals exactly `N * 1048576` bytes: at total == N MiB the result is 1, since the comparison is strict `<`.
- Mixed {L0, L1}: result 1 (min != max gives `max`). All L1: 2.
- Output of the Set B compaction: sstable count about `ceil(totalBytes / (N MiB))`, each at most N MiB plus the size of one partition. The sum of output sizes changes by less than 10% across N.
- Oversized partition: one output sstable is greater than N MiB (about the partition size).
- N=160: all sets give level 0 and a single output sstable.

**B2g. Readings.**

| Observation | Meaning |
|---|---|
| `getNextLevel` flips 0 to 1 exactly at total = N MiB for each N | The line-678 check works as traced (supports only the mechanism, not the cap) |
| Output sstable larger than N (oversized partition) | Per-sstable size is a soft target, supports the negative claim |
| Sum of output bytes about equal across N | Total size does not follow N (claim confirmed) |
| Sum of output bytes scales with N | Total size follows the option (claim refuted) |
| Every output sstable is at most N MiB, even with a 3x N partition | Claim wrong for the per-sstable size |
| Sizes unchanged but the positive control (see B2h) also did not move | Not confirmed: the control failed |
| Totals never reach N (N=160 rows) | Limit not reached; row does not test the claim |

**B2h. Controls.** Positive control: `MaxSSTableSizeWriter` output sstable count must grow as N shrinks for the same input (this is where the option does bind), so a flat total with a moving sstable count shows the knob works but does not cap total bytes. Also run with identical data, same compression and `gc_grace` for all N, and fix the random seed. Repeat each N three times.

### B3. Cluster tier

**B3a. Environment and build.**
- One node suffices (a second only to test streaming; not required). Linux, JDK 11, Ant. Copy the tree: `rsync -a ~/cassandra-5.0.9/ /local/scratch/c509-node/ && cd /local/scratch/c509-node && ant jar`.
- `conf/cassandra.yaml`: `data_file_directories`, `commitlog_directory`, `saved_caches_directory`, `hints_directory` all under `/local/scratch/c509-data/` (a local filesystem with >= 20 GiB free and not shared). `concurrent_compactors: 1` (default would hide backlog), `compaction_throughput: 0MiB/s` for the main run, `memtable_heap_space: 128MiB` (key `memtable_heap_space`), `-Xmx2g`.
- Use unique ports or a fresh `cluster_name` if any other Cassandra runs on the host.

**B3b. Knobs.** `sstable_size_in_mb` in {5, 20, 160}, applied with `ALTER TABLE` (no restart). Optional second axis: `compaction_throughput` 16MiB/s to build a backlog so level quotas are exceeded (shows quotas as triggers only). Values chosen so that with about 2 GiB of data, N=5 yields hundreds of sstables across L0-L3 while N=160 yields about a dozen.

**B3c. Workload.** `cassandra-stress` (from `tools/bin`) with a user profile or `write n=4000000 -col size=FIXED(256) n=FIXED(4) -pop seq=1..4000000 -rate threads=32`. Roughly 4M partitions x about 1 KiB = about 4 GiB raw before compression. Run once per N on a fresh table (or fresh node data), then let compaction drain (`nodetool compactionstats` shows 0 pending, 10 min stable). Add a phase that overwrites the same keys (`-pop seq=1..4000000` again) to test that disk after compaction tracks live data and not N. Add a large-partition table (`-pop` with few partition keys, each ~50 MiB) to show sstables above N. Duration: about 20-40 minutes per N.

**B3d. Observables and instruments.**
- Actual disk: `du -sb /local/scratch/c509-data/data/<ks>/<table>-*` sampled every 10 s, plus `nodetool tablestats <ks>.<table>` ("Space used (live)", "Space used (total)", "SSTable count", "SSTables in each level").
- Per-sstable size: `ls -l *-Data.db`, and `tools/bin/sstablemetadata` for level.
- Pending work: `nodetool compactionstats`; log lines `"L0 is too far behind"` and `"maximum supported level"` in `system.log`.
- Heap is not the target resource here; `jcmd <pid> GC.heap_info` once at the end for completeness.
- Cannot observe directly: the in-memory score values (only trace logs; enable `org.apache.cassandra.db.compaction.LeveledManifest` at TRACE with `nodetool setlogginglevel` if wanted).

**B3e. Procedure.**
1. Build, edit yaml as in B3a, start the node (`bin/cassandra -f > /local/scratch/node.log 2>&1 &`, record the PID).
2. `CREATE KEYSPACE ks WITH replication={'class':'SimpleStrategy','replication_factor':1}` and the stress-created table; `ALTER TABLE ... WITH compaction={'class':'LeveledCompactionStrategy','sstable_size_in_mb':'<N>'}`.
3. Start the du/tablestats sampler loop.
4. Run the write workload, wait for pending tasks to hit 0 and disk to stabilise (3 consecutive identical readings, 60 s apart).
5. Record: total live bytes, sstable count, per-level counts, min/avg/max sstable size.
6. Run the overwrite phase, wait for stability, record again.
7. Run the large-partition table and record max sstable size.
8. `nodetool drain`, stop the node, `kill` the PID if needed, check with `pgrep -f CassandraDaemon`.
9. Wipe `/local/scratch/c509-data/*` between N values; repeat for the other N. Then run the positive control (B3h).

**B3f. Predictions.**
- Settled live bytes for the same dataset differ by less than 10% across N=5/20/160 (the option is not a size cap).
- SSTable count falls as N rises: roughly total / N, so about 4x fewer at N=20 than at N=5 and about 8x fewer at N=160 than at N=20 (limited by dataset size).
- Max sstable size is about N MiB for the regular table, but exceeds N for the large-partition table (about the partition size).
- Peak `du` during compaction exceeds settled size by about the size of the inputs being compacted, so it is higher than the settled number regardless of N.
- With throttled compaction, L1+ levels exceed `fanout^level * N` while a backlog exists.
- The claim is wrong if settled disk scales with N, or if no sstable exceeds N even for the large partitions.

**B3g. Readings.**

| Observation | Meaning |
|---|---|
| Settled live bytes about equal across N, sstable count scales inversely with N | Claim confirmed: option sets granularity, not total disk |
| Settled live bytes scale with N | Claim refuted: usage follows the option |
| Max sstable > N on the large-partition table | Soft target, as traced |
| All sstables <= N even with 50 MiB partitions | Claim wrong for per-sstable cap |
| Levels above `fanout^level * N` under throttled compaction | Quotas are triggers, not limits (supports negative) |
| Positive control (B3h) does not move usage | Not confirmed: the run cannot tell |
| Settled bytes never approach any level quota (dataset too small for N=5 deep levels) | Limit not reached for that N; row not conclusive |

**B3h. Controls.** Positive control: a knob known to bind disk, e.g. fill with the same workload, then lower the amount of live data (`TRUNCATE`, or a TTL with `default_time_to_live` and `gc_grace_seconds=0` plus `nodetool compact`). Disk must fall to near zero, showing the instrument sees real changes and that total disk follows the live data. Also keep the dataset, compression, key order (`-pop seq`) and node count identical across N, and compare against an STCS table with the same data as a second reference.

**B4. Risks and cleanup.** Unit tier writes under the local copy's `build/test` directory; delete it afterwards. Cluster tier fills up to about 2-3x dataset size on peak (4 GiB x 2-3) on the local scratch disk: confirm `df -h /local/scratch` shows >= 20 GiB free before starting and that nothing is on shared storage. Never build or write in `~/cassandra-5.0.9`. After each run: stop the node (`nodetool drain`, then kill the PID), confirm `pgrep -f "CassandraDaemon|cassandra-stress|ant"` returns nothing, and `rm -rf /local/scratch/c509-data /local/scratch/c509-unit /local/scratch/c509-node` when done.

**Audit amendments (stage 4 step 0, 2026-10-24).** Made before any build output, run or reading; each leaves B1, B2f/B3f and B2g/B3g as filed. Where an amendment corrects text above, the amendment governs. Reasons are in the results file §1.1.
- **N1 (B2f, "total == N MiB gives 1").** A flushed sstable cannot be made exactly `N × 1048576` bytes, so the three boundary points (N MiB − 1, N MiB, N MiB + 1 total) use `MockSchema.sstableWithLevel(generation, size, level, cfs)` (`MockSchema.java:153`), whose `onDiskLength` is the given `size`, for N ∈ {1, 5, 20, 160} (size is an `int`; 160 MiB fits). Sets A and B stay real flushed sstables as filed.
- **N2 (B2c, B2e, keys and values).** Random-byte values, unique keys, `ByteOrderedPartitioner` unit yaml (`test/conf/cassandra.yaml:18`). Mixed-level case: one sstable at L1 by `mutateLevelAndReload(1)` plus L0 ones, `getNextLevel` called directly. "All L1" uses two L1 sstables.
- **N3 (B2e step 4).** The Set B compaction is `strategy.getNextBackgroundTask(gcBefore)` executed once on a `LeveledCompactionStrategy` over the live sstables; outputs are read from `cfs.getLiveSSTables()` after it. The positive control is the output count growing as N falls (B2h).
- **N4 (B3a, B3c, storage and workload).** Dedicated tmpfs of 24 GiB for data, commit log, hints and saved caches (spinning-disk stalls; `du` reads the same file bytes); `n=2,000,000` rows instead of 4 M (≈ 2 GiB). Table `ks.t` is created by `cqlsh` with the `standard1` layout (`key blob`, `C0..C3 blob`), compression off, then `cassandra-stress write n=2000000 -col size=FIXED(256) n=FIXED(4) -pop seq=1..2000000 -schema keyspace=ks`. Arithmetic: N=5 gives about 400 files of 5 MiB; N=160 about 12; the N=160 L0 target is 640 MiB.
- **N5 (B3e steps 4 and 6, drain and overwrite).** The filed main run already uses `compaction_throughput 0` and `concurrent_compactors 1`; "stable" is 3 reads 20 s apart with 0 pending and identical `du -sb` (cap 25 min). The overwrite phase repeats the same stress command (same keys; the stress generator is seeded, so values are identical) and is a **supplementary reading**, not part of a B3f prediction.
- **N6 (B3c, large partition).** The large-partition table is written by a Python-driver script, not `cassandra-stress`: 3 partitions of ≈ 40 MiB (10,000 clustering rows × 4 KiB) in table `ks.big` with the same N, protocol 4, UNLOGGED batches of 10 rows (20 rows = 80 KiB would exceed `batch_size_fail_threshold`, 50 KiB).
- **N7 (B3b, second axis; B3h, STCS and control).** The throttled run is N=20 with `setcompactionthroughput 16` for the whole write, reading per-level bytes from `nodetool tablestats` (**SSTable bytes in each level**, `TableStatsHolder.java:264`). The STCS reference is one run of the same data on `SizeTieredCompactionStrategy`. The positive control is `TRUNCATE` at the end of every run (`du -sb` must fall to ≈ 0); the filed `default_time_to_live` variant is not run.
- **N8 (runbook defect D1, 2026-10-24, found in a discarded shakedown before any cluster reading; leaves B3f/B3g unchanged).** N5's "0 pending" can never hold when one L0 sstable is left without a partner (`LeveledManifest.java:569`): `compactionstats` shows only an estimate. "Stable" is now: three reads 20 s apart with `CompactionExecutor` active + pending = 0 in `nodetool tpstats` and identical file bytes (cap 25 min).

## C. Sources read

- /users/jason92/writeup-A/playbook-autonomous.md
- /users/jason92/writeup-A/_TEMPLATE-autonomous.md
- src/java/org/apache/cassandra/db/compaction/LeveledManifest.java (lines 55-95, 175-325, 495-575, 630-719)
- src/java/org/apache/cassandra/db/compaction/LeveledCompactionStrategy.java (lines 50-300, 565-625)
- src/java/org/apache/cassandra/db/compaction/LeveledCompactionTask.java (lines 30-108)
- src/java/org/apache/cassandra/db/compaction/writers/MaxSSTableSizeWriter.java (lines 50-96)
- Grep results over src/java/org/apache/cassandra/db/compaction (matches in MajorLeveledCompactionWriter.java, CompactionStrategyManager.java, LeveledGenerations.java, CassandraRelevantProperties.java were seen only as grep lines)
- conf/ (grep for `sstable_size_in_mb`, no matches)

## D. Stage-4 feedback

**Stage 4, run 1, 2026-10-24 — unit Confirmed, cluster Confirmed — does not cap; outcome class: true negative** (estimate `negative`, effect `does not cap`). Results: [`stage4-runtime-verification/results/sstable_size_in_mb-getnextlevel-candidate-total-bytes--autonomous.md`](../../stage4-runtime-verification/results/sstable_size_in_mb-getnextlevel-candidate-total-bytes--autonomous.md). One run per tier, self-checked from the raw files (18 claims hold), no run 2. Not committed (the human commits).

- **Unit (B2):** `getNextLevel` returns 0 at exactly N MiB − 1 and 1 at N MiB and N MiB + 1 (strict `<`, byte-exact MockSchema sstables, N = 1/5/20/160); {L0, L1} → 1, {L1, L1} → 2; Set A (0.79 N) → 0, Set B (1.48 N) → 1; the same ≈ 29 MiB input compacted at N = 1/5/20/160 gives 29/6/2/1 files with bytes unchanged (×1.0001); a ≈ 15 MiB partition stays one 14.9 MiB file at N=5.
- **Cluster (B3):** 2,000,000 rows (≈ 2 GiB) per label. Settled table bytes 2,054.6 / 2,050.5 / 2,049.0 MiB for N = 5 / 20 / 160 (spread 0.3%), the STCS reference 2,049.4 MiB; files 508 / 112 / 13 (×4.5, ×8.6) of exactly 5.0 / 20.0 / 160.0 MiB; L0 reached 71× / 16.6× / 3.0× its quota with 0 write errors. N5's large-partition table kept three 39.2 MiB files (7.8 × N) from compaction; at N=20 and 160 the ≈ 117.7 MiB file is the flush output.
- **Sub-predictions not met (no row changed):** (1) B3f "with throttled compaction, L1+ levels exceed `fanout^level × N`": in the throttled T20 write window L0 was 17.8× its quota but L1 only 0.87×; L1 went over its quota later, in the unthrottled overwrite phase (5.12×; N5 27×, N20 7×). (2) The large-partition arm at N=160 cannot show an oversized file: its three ≈ 39 MiB partitions are smaller than N (a sizing error of my amendment N6, not of the file; the filed text says "each ~50 MiB", which also stays below 160 MiB).
- **Supplementary, not a prediction:** the overwrite phase (same keys again) left 2,333 / 2,737 MiB at N = 20 / 160 (2,632 at N=5, 2,357 for T20, 4,183 for STCS) against 2,050 live: dead rows below a level's quota stay until it triggers, non-monotone in N, one repetition. A TTL or repeated-overwrite arm with several repetitions would be needed to say whether the level quotas change the residue.
- **Amendments made at the audit (2026-10-24, before any reading):** N1-N7 (exact boundary with MockSchema sstables; random values, unique keys; Set B task; tmpfs, 2 M rows, `ks.standard1`; supplementary overwrite phase; large-partition script; throttled run, STCS reference, truncate control). **Runbook defects:** D1 (N8) "0 pending" cannot hold with one unpaired L0 sstable; D5 the B2h same-input positive control had not been implemented (unit tier re-run); D6 the large-partition writer failed in N5 attempt 1 and the label was re-run in full. N6's batch size was corrected to 10 rows (80 KiB exceeds `batch_size_fail_threshold`) before any run.
- **For stage 3:** the entry line `:678` picks a level and nothing else; the byte-exact boundary is the strongest single check. B3f's bullet on throttling should name the window in which L1 exceeds its quota (it is a transient of L0→L1 merges, seen with and without throttle).
- **Left on the node:** none running; `~/cassandra-lcsN`, `~/stage4-logs/lcs/` (see the results file).
