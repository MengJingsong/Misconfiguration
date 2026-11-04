# LCS per-level capacity (`maxBytesForLevel`, from `sstable_size_in_mb` × `fanout_size`^level) — verification solution  <!-- file: cases/lcs-level-capacity-shouldSwitchWriterInCurrentLocation-totalWrittenInLevel--autonomous.md -->

| Field | Value |
|---|---|
| Entry pointer | `src/java/org/apache/cassandra/db/compaction/writers/MajorLeveledCompactionWriter.java:78` |
| Pinned source | `cassandra-5.0.9` |
| Session / date | Claude Sonnet 5.5 (`claude-sonnet-5-5`), Claude Code CLI (version not exposed to the agent), 2026-10-24 |
| Estimate | `negative`: the line-78 comparison only decides which *level number* is stamped on the next output sstables of a major compaction; it never stops, throttles or truncates writing, so neither disk nor memory use is bounded by it. |
| Ground | The compared quantity (`totalWrittenInLevel`) is a running sum of bytes already written; when it exceeds the level capacity the only effect is `currentLevel++` (`:80-81`), and `return true` at `:83` is reached whether or not the level check fires (it is gated by the per-file `maxSSTableSize` test at `:75`). The top level is unbounded (no max level). Total disk after the compaction equals the merged data size regardless of the capacity. The only size-like bound in this method is the per-file switch at `:75`, which is a different, soft (one-partition-overshoot) limit. |

## A. Constraint trace

**A1. The constraint.** `LeveledManifest.maxBytesForLevel(level, levelFanoutSize, maxSSTableSizeInBytes)` (`src/java/org/apache/cassandra/db/compaction/LeveledManifest.java:185-193`): level 0 → `4 * maxSSTableSize`; level n≥1 → `fanout^n * maxSSTableSize` (throws only if the product overflows `long`). Kind: runtime-computed limit derived from two table-level compaction options.
- `sstable_size_in_mb`: declared `LeveledCompactionStrategy.java:52`; unit MiB; default `160` hard-coded at `:67` (`configuredMaxSSTableSize = 160`), parsed at `:73-75`, validated >0 at `:576-590`; converted to bytes by `getMaxSSTableBytes()` (`:289-291`). Warns if ≥1000 or <50 (`:78-83`), suppressed by `TOLERATE_SSTABLE_SIZE`.
- `fanout_size`: declared `:54`; default `DEFAULT_LEVEL_FANOUT_SIZE = 10` (`:56`, applied `:68`), parsed `:87-90`, validated >0 `:593-604`. Read by the writer from `cfs.getLevelFanoutSize()` (`MajorLeveledCompactionWriter.java:59`; `ColumnFamilyStore.java:3216`).
- Setting: per-table CQL `WITH compaction = {'class':'LeveledCompactionStrategy','sstable_size_in_mb':..,'fanout_size':..}` (ALTER TABLE; no restart, strategy is reloaded). Not a cassandra.yaml key or `-D` property. The value is passed to the writer through `LeveledCompactionStrategy.getMaximalTask` → `new LeveledCompactionTask(..., getMaxSSTableBytes(), true)` (`:193`) → `LeveledCompactionTask.getCompactionAwareWriter` (`LeveledCompactionTask.java:51-52`).

**A2. What it caps.** Intended: the nominal byte capacity of LCS level n (used by the manifest for compaction scoring, `LeveledManifest.java:254-255`, and here for level assignment). Resource: disk (sstable bytes), but only as a *scheduling target*, not an enforced cap. The quantity compared at `:78` is `totalWrittenInLevel`, the sum of `getEstimatedOnDiskBytesWritten()` (file pointer, `SSTableWriter.java:209-212`) of the finished output files already assigned to `currentLevel`.

**A3. Mechanism.**
1. Constructor stores `maxSSTableSize`, `levelFanoutSize` (`MajorLeveledCompactionWriter.java:58-59`); `currentLevel` starts at 1 (`:33`).
2. Each partition: `CompactionAwareWriter.append` → `maybeSwitchWriter` → `shouldSwitchWriterInCurrentLocation` (`CompactionAwareWriter.java:138-173`).
3. `:74-75`: if the current file's on-disk bytes > `maxSSTableSize`, a switch is requested (so files are ≈ `maxSSTableSize` + at most the overshoot of one partition plus buffered chunk lag; the position is "may not be accurate", `SSTableWriter.java:205-208`).
4. `:77`: add that file's size to `totalWrittenInLevel`. `:78`: if it now exceeds `maxBytesForLevel(currentLevel, fanout, maxSSTableSize)`, reset to 0 and `currentLevel++` (`:80-81`). New writer is created with `sstableLevel()` = `currentLevel` (`:98-101`, `CompactionAwareWriter.java:229-230`).
5. Outcomes at the limit: only the level number changes. Writing continues; nothing is rejected, spilled or aborted. Not reached (`<=`): same level stays.
- Consequences/overshoot: the file that crosses the threshold was already stamped with the old level, so the file counts toward the old level's total, and because every file is strictly > `maxSSTableSize`, level n (n≥1) holds at most `fanout^n` files; fewer if files overshoot (`ceil`-style, see B2f). The last (unfinished) file is never added, so the final level may be partial. Sum is of closed files only. `sstablesWritten` is never incremented (`:37`, reset `:94`), which only affects `averageEstimatedKeysPerSSTable`, not this check. No upper bound on `currentLevel`: a large enough compaction produces L3, L4, … (the existing test comments "if we want more levels, fix this", `CompactionAwareWriterTest.java:186`). Only reached for `majorCompaction == true` (`nodetool compact` on an LCS table); regular LCS compactions use `MaxSSTableSizeWriter` with fixed level (`LeveledCompactionTask.java:53`).

**A4. Other consumers.** Disk is also used by commit log, hints, snapshots, un-compacted input sstables (kept until the compaction commits, so a major compaction needs up to ~input size of extra temporary space; checked once up front by `getWriteDirectory`/`getExpectedWriteSize`, `CompactionAwareWriter.java:265-294`, `MajorLeveledCompactionWriter.java:108-112`), other tables, and later LCS compactions that re-write the data. Memory is not touched by this check.

**A5. Evidence beyond the source.** In-tree test `test/unit/org/apache/cassandra/db/compaction/writers/CompactionAwareWriterTest.java:165-191` (`testMajorLeveledCompactionWriter`) asserts 10 sstables in L1 and the rest in L2 with `sstableSize = beforeSize/50`; it is the template for the unit tier. No external sources relied on.

## B. Verification solution

**B1. Claim under test.** (Negative) Total disk occupied by the output of an LCS major compaction does not follow `maxBytesForLevel` (`sstable_size_in_mb`×`fanout_size`^level): changing `fanout_size` (or the level capacity) changes only the level labels of the output sstables, not their count or total bytes, and data far beyond the nominal capacity of a level is still written (levels are not capped). Refuted if total output bytes or file count vary with `fanout_size` at fixed `sstable_size_in_mb`, or writing stops/truncates at a capacity.

### B2. Unit tier

**B2a. Environment and build.** Linux, JDK 11, Ant. Copy the tree to local disk (`rsync -a <src>/ /local/work/c509/`; never build in the shared tree). `cd /local/work/c509 && ant jar` (or `ant build-test`). Add a new JUnit class `test/unit/org/apache/cassandra/db/compaction/writers/MajorLeveledLevelCapacityTest.java` modeled on `CompactionAwareWriterTest` (same base class, `getColumnFamilyStore()`, `populate`, `compact`). Run: `ant testsome -Dtest.name=org.apache.cassandra.db.compaction.writers.MajorLeveledLevelCapacityTest`. JVM defaults of the ant test target (heap per `build.xml`); data dir is the test's temp dir on local disk.

**B2b. Knobs.** `levelFanoutSize` as seen by the writer, set via the table option `fanout_size` in the test's `CREATE TABLE ... WITH compaction={'class':'LeveledCompactionStrategy','fanout_size':'F','sstable_size_in_mb':'1'}` (so `cfs.getLevelFanoutSize()` returns F). Values F ∈ {2, 4, 10 (default), 100}: spans small to large capacity, including one where all output fits in L1 (F=100). Also the `sstableSize` constructor argument (the writer API takes bytes directly): keep constant at `beforeSize/50` (≈ 50 output files, as in the existing test) for the fanout sweep; second sweep `beforeSize/20`, `/50`, `/100` at F=10 as the positive control (B2h).

**B2c. Workload.** `populate(rowCount=20000)` (existing helper) into one input sstable, flush, so `beforeSize` is known from `onDiskLength()`. With `sstableSize = beforeSize/50` the writer produces ≈50 files (the in-tree test asserts exactly 50 at F=10). Capacity arithmetic: L1 cap = F×size, L2 = F²×size, L3 = F³×size. F=2 → L1 holds ~2 files, L2 ~4, L3 ~8, L4 ~16, L5 the rest (~20): levels past 4 appear (size the level-count array ≥ 8). F=10 → 10 in L1, 40 in L2. F=100 → all 50 in L1. In every case the capacity of the top level is far exceeded by nothing; the check is whether total bytes are independent of it.

**B2d. Observables and instruments.** From `cfs.getLiveSSTables()` after `compact()`: per-sstable `getSSTableLevel()`, `onDiskLength()`, count; total bytes = Σ`onDiskLength()`; row count returned by `compact` (must equal `rowCount`). Optionally a Byteman/test subclass wrapper recording `totalWrittenInLevel` and `currentLevel` at each switch (they are private: use reflection, `setAccessible(true)`, read after each `append`). Cannot observe directly: `getEstimatedOnDiskBytesWritten` at each switch (use reflection on the subclass override of `shouldSwitchWriterInCurrentLocation`, or infer from final file lengths).

**B2e. Procedure.**
1. Copy tree, `ant jar build-test`.
2. For each F in {2,4,10,100}: create table with that `fanout_size`, `sstable_size_in_mb=1`, disable autocompaction, populate 20000 rows, flush, open txn on `getLiveSSTables()`, construct `new MajorLeveledCompactionWriter(cfs, dirs, txn, txn.originals(), beforeSize/50)`, run `compact`, record per-level file counts, total bytes, rows; `validateData`; `truncateBlocking`.
3. Repeat at F=10 for sizes `beforeSize/20`, `/50`, `/100`.
4. Run `ant testsome ...` and read the per-run lines the test prints (one line per run: F, size, files, bytes, level counts).

**B2f. Predictions** (before any run). *(Amended 2026-10-24: F=100 cannot be set; it is replaced by F=41, see B2i item 6.)*
- File count N and total bytes B are the same for F=2,4,10,100 at fixed `sstableSize` (N≈50 ±1, B equal within a few percent of one file's size, since compaction output bytes depend only on input data and file switching).
- Level histogram depends on F. With every file slightly > size, level n gets min(F^n, remaining) files: F=2 → L1=2, L2=4, L3=8, L4=16, L5=remaining (20 of 50); F=4 → 4, 16, 30 (L3); F=10 → 10, 40 (matches in-tree test); F=100 → 50 in L1, none above. If files overshoot by fraction δ the level holds ceil(F^n/(1+δ)) files, i.e. ≤ F^n, never more.
- No level 0 file. No exception. Sum of bytes in any non-top level ≤ ~F^n × (size+ one partition).
- Control: with F=10, N ≈ 20, 50, 100 for the three sizes, total bytes unchanged, and per-file bytes ≈ `sstableSize` (≤ size + one partition + chunk lag).
- Claim wrong if: B varies with F beyond one file's size, N varies with F, or any level's bytes are truncated to its capacity (rows lost).

**B2g. Readings.**

| Observation | Meaning |
|---|---|
| N, B constant across F; only level histogram changes as predicted | Claim confirmed: capacity only labels levels, does not bound disk |
| N or B changes monotonically with F | Claim refuted: usage follows the capacity |
| Rows < 20000 or exception when a level is over capacity | Refuted (capacity truncates/aborts) |
| Control (varying `sstableSize`) changes N inversely and per-file bytes track `sstableSize` while B stays flat | Positive control works: the per-file cap at `:75` binds, the level cap does not |
| Control did not move N or file size | Not confirmed (test harness not hitting the writer, or size unit wrong) |
| F=100 leaves everything in L1 (limit never exceeded) | Expected; that row contributes no evidence of "past the limit"; rely on F=2/4 rows. If F=2 also never exceeds capacity, not confirmed (too few files) |

**B2h. Controls.** Fixed data and seed per run (same single input sstable re-created identically); same `sstableSize` across the F sweep; the existing F=10 run must reproduce the in-tree assertion (10 in L1, 40 in L2), which validates the harness; the `sstableSize` sweep is the positive control showing a size knob that *does* bound a file. Run with autocompaction off so no background compaction rewrites files.

**B2i. Stage-4 audit amendments, 2026-10-24.** Each is derived from the pinned source alone, before any run or reading; none changes B1 or the direction of a prediction.

1. **How F reaches the writer (B2b, B2e).** `cfs.getLevelFanoutSize()` is `CompactionStrategyManager.fanout`, set at reload from the first strategy only if it is a `LeveledCompactionStrategy` (`CompactionStrategyManager.java:325, 640-643`). `CompactionAwareWriterTest.populate` calls `forceMajorCompaction()` when the flush made more than one sstable; on an LCS table with `sstable_size_in_mb = 1` that would itself write about 200 files and trip `populate`'s single-sstable assertion. Each arm therefore creates an STCS table, populates it (one sstable), then runs `ALTER TABLE ... WITH compaction = {'class':'LeveledCompactionStrategy','fanout_size':'F','sstable_size_in_mb':'1'}`, calls `disableAutoCompaction()` again, and asserts `cfs.getLevelFanoutSize() == F` before the writer is built (instrument check). Each arm uses a fresh table, dropped afterwards.
2. **Workload (B2c).** The existing helper writes one identical 5,000-byte payload into every row (`CompactionAwareWriterTest.java:288-291`; LZ4 hides its size, and 20,000 partitions are about 1 GB of inserts per arm). The test uses its own populate: 20,000 partitions x 10 rows x 1,024-byte distinct seeded blobs, `compression = {'enabled':'false'}`, as in B3c's "byte-predictable sizes". "20000 rows" in B2c means 20,000 partitions (`populate(20000)` writes 20,000 partitions of 10 rows); the row count read back is 200,000 (`SSTableReader.getTotalRows()` summed over the outputs) and the `compact` return value is 20,000 partitions.
3. **Level stamping (B2f).** A file takes the level in force when its writer is created, which is after `currentLevel++` ran at the previous file's close (`MajorLeveledCompactionWriter.java:78-82`, `CompactionAwareWriter.java:229-230`); the crossing file keeps the old level. With every file slightly above `S`, level n therefore holds exactly `F^n` files while `F^n` files remain, so the B2f histograms stand (F=2: 2/4/8/16/20; F=4: 4/16/30; F=10: 10/40; F=100: 50 in L1). For the control sizes at F=10: `S = total/20` gives 10 in L1 and the rest in L2, `total/100` gives 10 in L1 and the rest in L2 (the L2 capacity needs 100 closed files above `S`, and at most 99 close).
4. **Recording (B2d).** A subclass of `MajorLeveledCompactionWriter` overrides `shouldSwitchWriterInCurrentLocation`, calls `super`, and then reads `currentLevel` and `totalWrittenInLevel` (private) by reflection and the operand `sstableWriter.currentWriter().getEstimatedOnDiskBytesWritten()` (protected field), one line per call, with the returned boolean.
5. **Run mechanics.** One JUnit class, all arms in one JVM; `ant testsome` from a `copy-source.sh` tree with the test class added; data in the tree's `build/test/cassandra` on local disk.
6. **F = 100 cannot be set (B2b, B2c, B2f, B2g).** `validateOptions` rejects a table whose `fanout_size^8 x sstable_size_in_mb` (bytes) exceeds `Long.MAX_VALUE` (`LeveledCompactionStrategy.java:608-621`, `MAX_LEVEL_COUNT = 9` at `LeveledGenerations.java:57`). `100^8 x 1 MiB` is about 1.05e22 against 9.22e18, so `CREATE`/`ALTER` with `fanout_size = 100` fails for every `sstable_size_in_mb >= 1`; the largest valid F at 1 MiB is 41 (`41^8` = 7.98e12 MiB-units <= 8.80e12; `42^8` = 9.68e12 is not). The F = 100 arm is replaced by **F = 41** at `sstable_size_in_mb = 1`, `S = total/50`. Prediction for it, from the level rule: L1 holds `min(41, 50)` = 41 files (the L1 total passes `41 S` at the 41st file), L2 the other 9, none above; N and B equal to the other arms. The B2f line "F=100 -> 50 in L1" and the B2g row "F=100 leaves everything in L1" are withdrawn; the "past the limit" evidence comes from F = 2, 4, 10 and 41 (each exceeds the L1 capacity), so the B2g row about F = 2 never exceeding capacity stays as filed.

### B3. Cluster tier

**B3a. Environment and build.** One node suffices (optionally a second to show it is per-node); JDK 11, Ant; copy tree to local disk, `ant jar`. Config (`conf/cassandra.yaml` of the copy): `data_file_directories`, `commitlog_directory`, `hints_directory`, `saved_caches_directory` all under a local dir `/local/work/node1/` on a filesystem with ≥ 20 GiB free; single `num_tokens: 16` is fine; `concurrent_compactors: 1`, `compaction_throughput: 0MiB/s` (unthrottled; 5.0 key name `compaction_throughput`) so the run is short. Heap default (≥ 2 GiB). Start with `bin/cassandra -f` in background, log to local file.

**B3b. Knobs.** *(Amended 2026-10-24: F=100 cannot be set; it is replaced by F=31, see B3i item 7.)* Table option `fanout_size` ∈ {2, 10, 100}, at fixed `sstable_size_in_mb = 10` (small so many files are produced from modest data), set with `ALTER TABLE ks.t WITH compaction = {'class':'LeveledCompactionStrategy','sstable_size_in_mb':'10','fanout_size':'F'}`. Positive control: `sstable_size_in_mb` ∈ {10, 40} at F=10.

**B3c. Workload.** Create keyspace `ks` (RF 1), table `t(id bigint primary key, v blob)` with `compression = {'enabled': 'false'}` for byte-predictable sizes. Insert 600,000 rows with a 1 KiB random blob each via `cassandra-stress` (`tools/bin/cassandra-stress user` or `write n=600000 -col size=FIXED(1024) n=FIXED(1) -rate threads=16`), ≈ 650 MB of live data; `nodetool flush`. Arithmetic: at `sstable_size_in_mb=10`, ≈ 65 output files from the major compaction; F=2 → capacity L1=20 MiB (2 files), L2 = 40 MiB (4), L3 = 80 (8), L4 = 160 (16), L5 = 320 (rest ~35): nominal capacity of low levels is clearly exceeded by the total. F=100 → everything in L1. Duration: ingest a few minutes; compaction a few minutes.

**B3d. Observables and instruments.** Disk: `du -sb` of the table's data directory after the compaction completes, and `nodetool tablestats ks.t` ("Space used (live)", "SSTables in each level"); per-file sizes `ls -l *-Data.db`; levels with `sstablemetadata <Data.db>` ("SSTable Level"). Peak disk during the run: a `df`/`du` sampler every 1 s in the background (`while sleep 1; do du -sb $DIR >> du.log; done`). Heap/off-heap are not touched by this check; sample `nodetool info` heap just to show it is unaffected (not claimed). Cannot observe `totalWrittenInLevel` directly on a live node.

**B3e. Procedure.**
1. Build and start node; wait for `nodetool status` UN.
2. Create schema with F=10, `sstable_size_in_mb=10`, auto-compaction off (`nodetool disableautocompaction ks t`).
3. Ingest with stress; `nodetool flush ks t`; record `du -sb`.
4. `nodetool compact ks t` (major compaction; this is the only path to `MajorLeveledCompactionWriter`, `LeveledCompactionStrategy.java:193`). Wait for `nodetool compactionstats` to show none. Record total bytes, per-level counts, `sstablemetadata` levels, peak of `du.log`.
5. Truncate or recreate the table, repeat with F=2, then F=100 (re-ingest the same stress seed), and then F=10 with `sstable_size_in_mb=40` (control).
6. Stop the node, confirm no leftover java processes, delete `/local/work/node1`.

**B3f. Predictions.** *(Amended 2026-10-24: the F=2 level line is corrected in B3i item 1.)*
- Final live bytes and file count (≈ 65 ±2 at size 10 MiB) are equal across F=2,10,100 within one file size (≈10 MiB + one partition); peak disk during compaction ≈ input + output ≈ 2× data in each run, independent of F.
- "SSTables in each level": F=2 → L1=2, L2=4, L3=8, L4=16, L5=remaining; F=10 → L1=10, L2=remaining ~55; F=100 → all in L1 (stats show L1 over its 10-file "capacity" notion only for the others).
- Control: size 40 MiB → ≈ 16 files, each ≈ 40 MiB, total bytes unchanged.
- Claim wrong if total or peak bytes differ by more than ~one file between F values, or files are dropped/not written at a capacity.

**B3g. Readings.**

| Observation | Meaning |
|---|---|
| Total/peak bytes and file count constant across F; level histogram changes as predicted | Confirmed: level capacity doesn't cap disk |
| Total or peak bytes scales with F | Refuted |
| Data loss (read-back count < 600000 via `select count(*)` / stress read) or compaction error at over-capacity | Refuted |
| Control: file size and count follow `sstable_size_in_mb`, total constant | Positive control works: per-file cap binds, level cap does not |
| Control did not change file size/count | Not confirmed |
| Fewer than ~20 files so F=2 never exceeds L1 capacity | Not confirmed (limit not reached) |

**B3h. Controls.** Same stress seed and data each run; identical node config; auto-compaction disabled so only the manual major compaction runs; compare with `du` of input before compaction; check `system.log` for "Compacted" line (bytes in/out) to match tablestats. Repeat the F=10 run once to measure run-to-run variation.

**B3i. Stage-4 audit amendments, 2026-10-24.** Each is derived from the pinned source alone, before any run or reading; none changes B1 or the direction of a prediction.

1. **Level histogram for F=2 (B3f).** The B3f line "F=2 -> L1=2, L2=4, L3=8, L4=16, L5=remaining" is wrong for about 65 files: L5 holds `2^5 = 32` files (the L5 total passes `32 S` at the 32nd file) and the remaining 3 go to L6. Corrected prediction, from the level rule alone: F=2 -> L1=2, L2=4, L3=8, L4=16, L5=32, L6=the remainder (about 3 of about 65 files); F=10 -> L1=10, L2=the rest; F=100 -> all in L1. Levels stay below the LCS maximum, so nothing is rejected at L6. The unit tier's 50-file F=2 histogram (2/4/8/16/20) is unaffected.
2. **Auto-compaction stays off through the major compaction (B3c, B3e).** B3c re-enables it before `nodetool compact`; `LeveledCompactionStrategy.getMaximalTask` takes every manifest sstable in one `tryModify` and returns `null` if any is already compacting (`LeveledCompactionStrategy.java:183-193`), and background L0 compaction starts on the flushed files once re-enabled, so the manual compaction could be a no-op or run on a rewritten input. Auto-compaction therefore stays disabled for the whole arm (`nodetool compact` runs regardless); the major compaction is confirmed from the `Compacted` log line.
3. **Load (B3c).** A Python loader on the bundled driver (the table is B3c's `t(id bigint primary key, v blob)`, not cassandra-stress's schema): 600,000 rows of 1,024-byte distinct seeded blobs, 128 requests in flight, `nodetool flush` after every 100,000 rows (6 L0 files); one table per arm (`t_f10a`, `t_f2`, `t_f100`, `t_s40`, `t_f10b`), each created with its options and dropped after the arm; `auto_snapshot: false`. Arm order: F=10 (a), F=2, F=100, `sstable_size_in_mb`=40, F=10 (b, the repeat of B3h).
4. **Data-loss read-back (B3g).** A paged driver query (`SELECT id FROM <table>`, fetch size 10,000) counts the rows after the compaction; `SELECT count(*)` is not used (the 10 s `range_request_timeout`).
5. **Disk observable (B3d).** The 1 s `du -sb` sampler reads the table directory `data/ks/<table>-*` (live size, input + output). The node-data total is also sampled but includes the commit log and is not what B3f refers to.
6. **Node configuration.** `compaction_throughput: 0MiB/s`, `auto_snapshot: false`, `MAX_HEAP_SIZE=2G HEAP_NEWSIZE=512M` from the environment, `ulimit -n 100000`, one data directory under `~/stage4-lcl2/node` on `/` (local, 47 GB free at audit; the largest arm needs about 1.5 GB).
7. **F = 100 cannot be set (B3b, B3c, B3f, B3g).** The table-option validation bound in B2i item 6 applies: at `sstable_size_in_mb = 10`, `100^8 x 10 MiB` exceeds `Long.MAX_VALUE`, and the largest valid F is 31 (`31^8` = 8.53e11 <= 8.80e11 MiB-units; `32^8` = 1.10e12 is not). The F = 100 arm is replaced by **F = 31**. Prediction for it, from the level rule: about 65 files, L1 = 31, L2 = the remainder (about 34; the L2 capacity of `961 S` is never reached), none above; file count and total bytes equal to the other arms. "F=100 -> all in L1" in B3f is withdrawn; the arm order is F=10 (a), F=2, F=31, `sstable_size_in_mb`=40 at F=10, F=10 (b), and the tier row "F in {2, 10, 100}" reads {2, 10, 31}. The B3g row "fewer than ~20 files so F=2 never exceeds L1 capacity" is unchanged.

**B4. Risks and cleanup.** Disk: data ≈ 0.65 GB, peak ≈ 1.5 GB, plus commit log; all under `/local/work/node1` on local disk; do not use shared storage. Unit tier uses the test temp dir (small). Cleanup: `nodetool drain`, kill the Cassandra pid, `pgrep -f CassandraDaemon` and `pgrep -f cassandra-stress` must be empty, `rm -rf /local/work/node1 /local/work/c509`.

## C. Sources read

- /users/jason92/writeup-A/playbook-autonomous.md
- /users/jason92/writeup-A/_TEMPLATE-autonomous.md
- src/java/org/apache/cassandra/db/compaction/writers/MajorLeveledCompactionWriter.java
- src/java/org/apache/cassandra/db/compaction/writers/CompactionAwareWriter.java
- src/java/org/apache/cassandra/db/compaction/LeveledManifest.java
- src/java/org/apache/cassandra/db/compaction/LeveledCompactionTask.java
- src/java/org/apache/cassandra/db/compaction/LeveledCompactionStrategy.java
- src/java/org/apache/cassandra/io/sstable/format/SSTableWriter.java
- test/unit/org/apache/cassandra/db/compaction/writers/CompactionAwareWriterTest.java
- grep results over src/java and test/unit/.../compaction (ColumnFamilyStore.java, CompactionStrategyManager.java, CompactionManager.java, etc.)

## D. Stage-4 feedback

**2026-10-24, stage 4 (pc12, one run per tier, no run 2).** Results: [`results/lcs-level-capacity-shouldSwitchWriterInCurrentLocation-totalWrittenInLevel--autonomous.md`](../../stage4-runtime-verification/results/lcs-level-capacity-shouldSwitchWriterInCurrentLocation-totalWrittenInLevel--autonomous.md). Case-file version: sha256 `8796b85bfe4f58ad3aa3aad355fbdb273603f07d515d35371d9f31b192c6829e` (after the audit's B2i and B3i amendments; the file is untracked, so no commit holds it).

- **Verdict:** unit **Confirmed — does not cap**; cluster **Confirmed — does not cap** (with the numeric deviation below). **Outcome class: true negative** (estimate `negative`, effect `does not cap`).
- **What was measured:** across `fanout_size` the number of output files and the total bytes did not change (unit: 50 files, 208.4 MB for F = 2 / 4 / 10 / 41, spread 79 KB; cluster: 61 files, 634.76 MB for F = 2 / 10 / 31 and the repeat of 10, spread 4.8 KB; peak table-directory bytes 2.00 to 2.03 x the input), only the level labels moved (F=2: 2 / 4 / 8 / 16 / 20 in the unit tier and 2 / 4 / 8 / 16 / 31 on the node; F=10: 10 in L1, the rest in L2). No row was lost (200,000 in the unit tier; 600,000 of 600,000 read back), nothing stopped at a capacity, even where the L1 capacity (20 MiB at F = 2) was exceeded about 30 times. Positive control: the per-file knob moved file count (unit 20 / 50 / 100; cluster 16 vs 61 files) with total bytes flat.
- **Amended before run 1 (B2i, B3i, 2026-10-24):** **F = 100 cannot be set** (`validateOptions` rejects `fanout^8 x sstable_size_in_mb` above `Long.MAX_VALUE`, `LeveledCompactionStrategy.java:608-621`; the largest valid F is 41 at 1 MiB and 31 at 10 MiB), so it was replaced by F = 41 (unit) and 31 (cluster) and the "all in L1" arm is lost; the input is built on an STCS table and altered to LCS (`populate`'s `forceMajorCompaction()` on an LCS table would write about 200 files); own populate with distinct 1 KiB blobs; the cluster F = 2 histogram corrected (L5 holds 32 files); auto-compaction kept off through `nodetool compact`.
- **Not caught by the audit (a defect of the frozen text, recorded, not edited):** B3c / B3f size the load as about 650 MB and 65 files, but 600,000 rows of 1 KiB occupy 605 MiB (634.76 MB), giving 61 files; the F = 2 line therefore read L5 = 31 with no L6 on the node. The B3g rows that decide the verdict (constant across F, histogram changes as predicted, control moves) held; the numeric sub-predictions did not. A reader who wants "Confirmed" to require every number can downgrade the cluster tier to *Not confirmed (no matching row)*; the effect on the constraint is `does not cap` either way.
- **For stage 3:** the level-capacity claim is fully consistent with the traced path (`totalWrittenInLevel` only advances `currentLevel`; `MajorLeveledCompactionWriter.java:77-82`). Data-volume arithmetic in B3c should use binary units and row overhead.
