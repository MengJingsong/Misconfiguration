# sstable_size_in_mb (LCS) — verification solution  <!-- file: cases/sstable_size_in_mb-shouldSwitchWriterInCurrentLocation-maxSSTableSize--autonomous.md -->

| Field | Value |
|---|---|
| Entry pointer | `src/java/org/apache/cassandra/db/compaction/writers/MajorLeveledCompactionWriter.java:75` |
| Pinned source | `cassandra-5.0.9` |
| Session / date | Claude Sonnet 5.5 (`claude-sonnet-5-5`), Claude Code CLI (version not exposed to the session), 2026-10-24 |
| Estimate | `positive`, with a scope limit. The LCS table option `sstable_size_in_mb` caps the on-disk size of each sstable that a major LCS compaction writes. The cap is soft: it is checked before each partition, so a file overshoots by up to one partition (plus write-buffer/chunk granularity). It does not cap total table or node disk usage. |
| Ground | — (the cap on file size is real. The "usage" it does not bound is the total bytes on disk, see A2 and A4.) |

## A. Constraint trace

**A1. The constraint.** `sstable_size_in_mb`, a per-table compaction sub-option of
`LeveledCompactionStrategy`. Kind: configuration entry (table schema option, not `cassandra.yaml`).
- Declared at `src/java/org/apache/cassandra/db/compaction/LeveledCompactionStrategy.java:52` (`SSTABLE_SIZE_OPTION = "sstable_size_in_mb"`).
- Parsed in the constructor at `LeveledCompactionStrategy.java:73-75` into `maxSSTableSizeInMiB` (field at `:60`).
- Unit: MiB (an `int`). Converted to bytes by `getMaxSSTableBytes()` at `LeveledCompactionStrategy.java:289-292` (`* 1024L * 1024L`).
- Default: 160, a hard-coded literal at `LeveledCompactionStrategy.java:67`, used when the option is absent. Not derived from anything else. `validateOptions` falls back to `"1"` at `:576`, but only to validate, so it does not change the runtime default. The docs state default 160 (`doc/modules/cassandra/pages/managing/operating/compaction/lcs.adoc:78-83`).
- Validation: must be an integer >= 1 (`:580-582`). `maxBytes = fanout^(MAX_LEVEL_COUNT-1) * size` must fit in a `long` (`:608-621`). Values >= 1000 or < 50 only log a warning (`:78-83`), unless `TOLERATE_SSTABLE_SIZE` is set (`:53`).
- Set with `CREATE/ALTER TABLE ... WITH compaction = {'class':'LeveledCompactionStrategy','sstable_size_in_mb':'N'}`. No restart is needed: an ALTER reloads the strategy. Not a `-D` property and not JMX-settable here.
- The operand at the target line, `maxSSTableSize`, is the constructor argument at `MajorLeveledCompactionWriter.java:54/58`. It reaches the writer through `LeveledCompactionTask.getCompactionAwareWriter` (`LeveledCompactionTask.java:51-52`) from `maxSSTableBytes` (`:34/41`). For a major compaction that value comes from `LeveledCompactionStrategy.getMaximalTask` (`LeveledCompactionStrategy.java:183-193`, `getMaxSSTableBytes()` with `majorCompaction=true`).

**A2. What it caps.** Resource: disk. The quantity compared is
`sstableWriter.currentWriter().getEstimatedOnDiskBytesWritten()` (`MajorLeveledCompactionWriter.java:74`). That is the bytes written so far to the current output sstable's Data.db. For an uncompressed file it is the file position (`SequentialWriter.java:314-317`). For a compressed file it is `chunkOffset`, i.e. compressed bytes at the last chunk boundary (`CompressedSequentialWriter.java:127-131`). It is compared against `maxSSTableSize` at `:75`. So the object bounded is the size of a single output sstable's Data.db, not the node's total disk.

**A3. Mechanism.**
1. `CompactionAwareWriter.append` calls `maybeSwitchWriter(key)` before every partition (`CompactionAwareWriter.java:138-141`).
2. `maybeSwitchWriter` first calls `maybeSwitchLocation`. That only switches on the first partition or when the next data directory is reached (`:166-173`, `:179-204`). Otherwise it calls the abstract `shouldSwitchWriterInCurrentLocation` (`:171`, `:210`).
3. `MajorLeveledCompactionWriter.shouldSwitchWriterInCurrentLocation` (`:71-87`) reads the current writer's bytes (`:74`). If the bytes are `> maxSSTableSize` (`:75`, strict) it adds them to `totalWrittenInLevel` (`:77`). If that exceeds `LeveledManifest.maxBytesForLevel(currentLevel, fanout, maxSSTableSize)` (`:78`; `LeveledManifest.java:185-193`: L0 = 4x, Ln = fanout^n x size) it resets the counter and increments `currentLevel` (`:80-81`). It then returns true (`:83`).
4. True leads to `switchCompactionWriter` (`:90-96` → `CompactionAwareWriter.java:220-224`). That finishes the current sstable and opens a new one at `sstableLevel()` (`:98-101`).
5. When the limit is not reached it returns false (`:85`) and the partition goes into the current file (`realAppend`, `:65-69`).

Outcome at the limit: the current file is closed and a new one opened. Nothing is rejected or throttled.

Overshoot and bypass paths:
- **Check-before-append.** The test is made before the next partition is written, so every non-final output file has size `> maxSSTableSize`. It is bounded above by `maxSSTableSize` plus the size of the last partition appended, plus buffer/chunk granularity (compressed: `chunkOffset` lags the true position).
- **Large partition.** A single partition larger than the limit is never split, so that file is larger than the limit.
- **Other writers.** `MajorLeveledCompactionWriter` is used only when `majorCompaction == true` (`LeveledCompactionTask.java:51-52`), i.e. `nodetool compact` through `CompactionManager.submitMaximal` (`CompactionManager.java:991-1001`) → `getMaximalTask`. Normal LCS compactions use `MaxSSTableSizeWriter`, whose check is the same kind (`MaxSSTableSizeWriter.java:78`). `getUserDefinedTask` passes `Long.MAX_VALUE` for level 0 (`LeveledCompactionStrategy.java:211`), so no cap applies there.
- **Flush.** Flushed memtables are not sized by this option.
- **Expected-size hint.** `getExpectedWriteSize` is `min(maxSSTableSize, ...)` (`MajorLeveledCompactionWriter.java:108-112`). It is used only to choose a data directory with enough free space.

**A4. Other consumers.** Disk used outside this constraint's control:
- Input sstables are held until the compaction commits, so peak usage during a major compaction is roughly input plus output.
- Other tables, snapshots, backups, commit log, hints, and flushed L0 sstables.
- Index and metadata components (Index.db, Summary/Filter, Statistics, and so on) that sit beside Data.db (the check measures Data.db only).
- Total table size is set by the data volume, not by this option. Per-level size targets (`maxBytesForLevel`) govern when compactions are scheduled, not a hard ceiling.

**A5. Evidence beyond the source.**
- `doc/modules/cassandra/pages/managing/operating/compaction/lcs.adoc:78-83` (in tree) states the option and default 160, and says a compaction "could produce a larger SSTable".
- Existing unit test `test/unit/org/apache/cassandra/db/compaction/writers/CompactionAwareWriterTest.java:164-191` drives this exact class with `sstableSize = beforeSize/50` and asserts 50 output sstables, 10 in L1 and the rest in L2.
- CASSANDRA-5727 (cited in the warning at `LeveledCompactionStrategy.java:82`) is the origin of the 160 MB recommendation; not re-read.

## B. Verification solution

**B1. Claim under test.** For a major LCS compaction, every output Data.db except the last has size in `(S, S + one-partition + granularity]`, where `S = sstable_size_in_mb * 1 MiB`. The number of outputs is about `ceil(total / S)` and moves inversely with `S`. Falsified if non-final files are clearly larger than `S` plus one partition, or if file count/size does not follow `S`.

### B2. Unit tier

**B2a. Environment and build.** Linux, JDK 11, Ant. Copy the tree to local disk first (never build in the shared tree): `rsync -a <src>/ /local/work/cass-unit/`. Then in the copy, `cd /local/work/cass-unit && ant jar` (or `ant build-test`). Add a new test class `test/unit/org/apache/cassandra/db/compaction/writers/MajorLeveledSizeCapTest.java`, modelled on `CompactionAwareWriterTest` (`:60-191`): same table setup, `populate`, `compact` helpers. Run: `ant testsome -Dtest.name=org.apache.cassandra.db.compaction.writers.MajorLeveledSizeCapTest`. Use the default test JVM options and put the test data directory on local disk (the ant test config uses `build/test/cassandra`, inside the copy).

**B2b. Knobs.** The constructor argument `maxSSTableSize` (the A1 operand, `MajorLeveledCompactionWriter.java:54`). Values: `S = total/10`, `total/50`, `total/200` bytes (3 values, same input), then `S = Long.MAX_VALUE` as a negative control. Set directly in code through the constructor. No restart is involved.

**B2c. Workload.** Table `(k int, t int, v blob, PRIMARY KEY (k,t))`, as in the existing test. Populate with deterministic random blobs, so compression cannot hide size. Use 20000 partitions x 10 rows x ~1 KiB (`ROW_PER_PARTITION = 10` at `CompactionAwareWriterTest.java:63`), about 200 MiB (read the real `beforeSize` from `onDiskLength()`, as in `:173`). Flush to a single sstable. Take one `LifecycleTransaction` over it. For each `S`, construct the writer over that input, then append all partitions through `compact()`. Arithmetic: `total/50` gives about 50 outputs (cf. the existing `:177`). A typical partition is about 10 KiB, which is `< 0.5%` of `S`.

**B2d. Observables and instruments.**
- Per output sstable: `SSTableReader.onDiskLength()` (Data.db bytes), `getSSTableLevel()`, and the count of `cfs.getLiveSSTables()`.
- The operand itself: in a subclass of `MajorLeveledCompactionWriter` (or a spy) override `shouldSwitchWriterInCurrentLocation` to record `sstableWriter.currentWriter().getEstimatedOnDiskBytesWritten()` and the returned boolean. `sstableWriter` is protected in the base class, so this is possible.
- The size of the largest single partition (known from the generator).
- Not observable directly: the true file position inside a compressed chunk, since the check sees only `chunkOffset`. Disable compression in the test table (or use random data) so the two agree.

**B2e. Procedure.**
1. Build the copy and add the test.
2. Populate and flush, then record `total` and the max partition size.
3. For each `S` in (`total/10`, `total/50`, `total/200`, `Long.MAX_VALUE`): create the writer, run `compact`, and record the sorted list of output sizes, levels and the recorded operand values. Call `validateData` and truncate between runs.
4. Run the whole class once more with compression on, to see the granularity effect.
5. Print the results. Record the pass/fail of the assertions below.

**B2f. Predictions (before any run).**
- Output count: about 10, 50 and 200 for the three `S` values (the existing test shows exactly 50 for `total/50`; the others within about ±10%). Exactly 1 for `Long.MAX_VALUE`.
- Every non-final output has `S < size <= S + maxPartitionSize + granularity`. Uncompressed, granularity is under one 4 KiB-class buffer. Compressed, it is under about one chunk.
- The final output has size `<= S + overshoot` (it may be much smaller).
- The recorded operand at each `true` return exceeds `S`. At every `false` return it is `<= S`.
- Levels (fanout 10): for the 50-file run, 10 files at L1 and 40 at L2 (existing assertions at `:185-186`). For the 10-file run, all 10 or fewer at L1.

**B2g. Readings.**

| Observation | Meaning |
|---|---|
| Non-final outputs in `(S, S + maxPartition + granularity]`; output count ≈ `total/S` | Claim holds: the operand caps single-file size as traced |
| Any non-final output `> S + maxPartition + granularity` | Claim wrong: the check is not the only bound (or `getEstimatedOnDiskBytesWritten` misreports) |
| Any non-final output `<= S` | The strict `>` at `:75` or the trace is wrong |
| Output count does not change with `S` | Operand not wired to the splitting (claim wrong) |
| `S = Long.MAX_VALUE` still yields several files | Another split source exists (for example directory boundaries); investigate |
| Only one output for all `S` | `S` never reached: inputs too small, so no conclusion |

**B2h. Controls.** (1) `S = Long.MAX_VALUE`: must give 1 file, which shows the splitting comes from the operand. (2) Same input, same order, fresh table each run, so only `S` varies. (3) Repeat with a single oversized partition (for example one 3x`S` partition): it must yield one file larger than `S`, which demonstrates the documented bypass. (4) Uncompressed vs compressed run, to separate granularity from the cap.

**B2i. Stage-4 audit amendments, 2026-10-24.** Each is derived from the pinned source alone, before any run or reading; none changes B1 or the direction of a prediction.

1. **Workload (B2c).** `CompactionAwareWriterTest.populate` writes one identical 5,000-byte payload into every row (`:288-291`), so LZ4 hides its size and 20,000 partitions are about 1 GB of inserts per arm. The test therefore uses its own `populate`: 20,000 partitions x 10 rows x 1,024-byte blobs, each blob distinct (seeded `Random`), into a table with `compression = {'enabled':'false'}` (a second table with the default LZ4 compression for the compressed run, B2e.4). The input is one sstable (flush; if the memtable flushed more than once, `forceMajorCompaction()` as the existing helper does; the table uses STCS so this does not split). The table uses `durable_writes=false` and autocompaction is disabled.
2. **Expected relations derived from the source (B2f).** (a) Uncompressed, `getEstimatedOnDiskBytesWritten()` is the exact file pointer (`SequentialWriter.java:314-317`), and a switch happens before the next partition is appended, so each non-final output's Data.db length equals the operand recorded at its `true` return; this is recorded as an instrument check and a mismatch is reported in part 6, not as a row. (b) The previous check returned `false`, so its operand was `<= S`; the partition appended since then bounds the overshoot, so `size - S <= ` that partition's bytes (about 10.3 KiB at 10 rows x 1 KiB). (c) Levels for `S = total/200` (about 200 outputs, each slightly above `S`): the L1 total passes `10 S` at the 10th file, the L2 total passes `100 S` at the 100th, so about 10 / 100 / rest in L1 / L2 / L3; for `S = total/10` all outputs are in L1 (L1 would need 10 closed files above `S`, but at most 9 close).
3. **Compressed run (B2e.4, B2f "under about one chunk").** The compressed table has the default 16 KiB chunk (`CompressionParams.DEFAULT_CHUNK_LENGTH`). The operand is `chunkOffset`, which rises only at chunk flushes, and the closed file also holds the final partial chunk (at most one more chunk plus its CRC). The bound used is therefore `S + maxPartition + 2 x 16 KiB + 64 B`, and "about one chunk" in B2f is read with that bound. Compressed `S = total/50` uses `total` = the compressed input's `onDiskLength()`.
4. **Wide partition (B2h.3).** The control table has `S = 4 MiB` (fixed, passed to the constructor), 10,000 small partitions plus one partition of 12,288 rows x 1 KiB (12 MiB, 3 x `S`). Prediction: exactly one output has Data.db length above `S + maxSmallPartition`; it is at least 12 MiB and at most 12 MiB + `S` + one small partition (the check runs before the wide partition, so it joins a file that holds up to `S` already, and the next check closes it).
5. **Run mechanics.** One JUnit class, all arms in one JVM (the knob is a constructor argument, so no restart is involved); per-arm lines `ARM ...` and a per-call operand file are written under the test's output directory. `ant testsome -Dtest.name=...` is run from a `copy-source.sh` tree with the test class added; the test data directory is the tree's `build/test/cassandra` on local disk.

### B3. Cluster tier

**B3a. Environment and build.** One node is enough (RF 1, `SimpleSeedProvider` with 127.0.0.1). JDK 11, Ant. Copy the tree to local disk (`rsync -a <src>/ /local/work/cass-node/`) and run `ant jar`. In the copy's `conf/cassandra.yaml` set `data_file_directories`, `commitlog_directory`, `saved_caches_directory` and `hints_directory` to `/local/work/node-data/...` on a local disk with at least 10 GiB free. Use a single data directory (so no `diskBoundaries` split). Set `compaction_throughput: 0` (unthrottled, per 5.0's yaml option name `compaction_throughput`) so runs are short. Heap: `MAX_HEAP_SIZE=2G` through `conf/jvm11-server.options` (`-Xms2G -Xmx2G`). Start with `bin/cassandra -f` in the background, logging to a file.

**B3b. Knobs.** `sstable_size_in_mb` via `ALTER TABLE ... WITH compaction = {...}`, values 5, 20, 80 (MiB; below the 50 warning threshold is fine, and the warning at `LeveledCompactionStrategy.java:81` is harmless). The arithmetic: with 400 MiB of data these give about 80, 20 and 5 files. Also the default (omit the option, so 160 → 3 files) as a fourth point. Fixed: `fanout_size` 10, compression disabled.

**B3c. Workload.** Table `ks.t (pk bigint, ck int, v blob, PRIMARY KEY (pk, ck)) WITH compression = {'enabled':'false'} AND compaction = {'class':'LeveledCompactionStrategy', 'sstable_size_in_mb':'<S>'}`. Insert 40,000 partitions x 10 rows x 1 KiB random blobs (about 400 MiB plus overhead) with `cassandra-stress` or a driver script through the native port, so the writes go through the normal client path. Auto-compaction off (`nodetool disableautocompaction ks t`) during the load, `nodetool flush` every ~50 MiB to get a spread of L0 files, then re-enable and run `nodetool compact ks t` (this is the major compaction that selects `MajorLeveledCompactionWriter`, A3). Also separate runs: a table with one 3x`S` partition (wide-row control). Duration: load a few minutes, compaction under a minute per run.

**B3d. Observables and instruments.**
- Per-file sizes: `ls -l /local/work/node-data/data/ks/t-*/*-Data.db` (or `stat -c %s`), taken after the compaction.
- Levels: `tools/bin/sstablemetadata <Data.db>` (field "SSTable Level").
- Table-level: `nodetool tablestats ks.t` (SSTable count, "Space used (live)"), `nodetool compactionstats` (to know the compaction is done).
- Node disk: `du -sb /local/work/node-data` sampled every 1 s during the compaction (`watch`/loop), giving peak vs steady usage.
- Not observable: the in-writer counter. Use the unit tier for that.

**B3e. Procedure.**
1. Build the copy; configure as B3a; start the node and wait for `nodetool status` to show UN.
2. For each `S` in (5, 20, 80, default): create keyspace `ks` (RF 1) and the table with that `S`; load the data and flush (B3c).
3. Start the `du` sampler. Run `nodetool compact ks t`, then wait until `nodetool compactionstats` shows no active compaction.
4. Record the Data.db sizes, count, levels and `du` peak. `DROP TABLE` and clear snapshots before the next `S`.
5. Wide-row control: repeat with `S = 20` and one 60 MiB partition (60 one-MiB rows of one pk).
6. Stop the node (`nodetool drain`, then kill the PID), check `pgrep -f CassandraDaemon` is empty, delete `/local/work/node-data`.

**B3f. Predictions (before any run).**
- Total live size is about 400 MiB for every `S`, so file count scales inversely with `S`: about 80 / 20 / 5 files for `S` = 5 / 20 / 80, and about 3 for the default 160. Counts within roughly ±1 file plus ±5%.
- For each run, all but the last Data.db are within `(S, S + ~11 KiB]` (one 10 KiB partition, uncompressed), hence under `1.01 S` for `S >= 5`.
- Levels (fanout 10): at most 10 files in L1 and the rest in L2 (the `maxBytesForLevel` rule at `MajorLeveledCompactionWriter.java:78`).
- Peak `du` during the compaction is about input + output, i.e. up to roughly 2x the live size, independent of `S` to first order. The option does not bound it.
- Wide-row control: one file is about 60 MiB, which is `> S = 20`, so it breaks `S + 1 partition` (the documented bypass).

**B3g. Readings.**

| Observation | Meaning |
|---|---|
| File count follows ~400/S and non-final files within `S + one partition` | Claim holds on the real node |
| Non-final file `> S + one partition` (apart from the wide-row control) | Claim wrong: the cap is not enforced as traced |
| File count unchanged across `S` | The option is not governing output size (claim wrong, or ALTER not applied: check `DESCRIBE TABLE`) |
| Peak `du` ≈ 2x live regardless of `S` | Expected: the option bounds file size, not total or transient disk. Consistent with the Estimate scope |
| Peak `du` much lower for small `S` | Unexpected; would mean `S` also bounds transient usage |
| Only one file for all `S` | Data volume too small for `S`: not a refutation; raise the volume |
| Wide-row control file `<= S` | Trace wrong about the bypass |

**B3h. Controls.** (1) Same data and table schema, `STCS` instead of LCS: `nodetool compact` gives one file regardless of `sstable_size_in_mb`. This is the positive control that file size is governed by the LCS option and not by the workload. (2) The default `S` (160) run. (3) The wide-row run shows the overshoot path. (4) Confirm with `DESCRIBE TABLE ks.t` before each run that the option took effect. (5) Run on an otherwise idle node and local disk.

**B3i. Stage-4 audit amendments, 2026-10-24.** Each is derived from the pinned source alone, before any run or reading; none changes B1 or the direction of a prediction.

1. **Auto-compaction stays off through the major compaction (B3c, B3e).** B3c re-enables auto-compaction before `nodetool compact`. `LeveledCompactionStrategy.getMaximalTask` takes every sstable of the manifest in one `tryModify` and returns `null` when any is already compacting (`LeveledCompactionStrategy.java:183-193`), and background L0 compaction starts on the flushed L0 files as soon as it is re-enabled, so the manual compaction could do nothing or run on a rewritten input. Auto-compaction therefore stays disabled for the whole arm (`nodetool compact` runs regardless). The compaction is confirmed from the `Compacted` log line and the `MAJOR_COMPACTION` entry in `compactionstats`/`system.log`.
2. **Load (B3c).** A Python loader on the bundled driver (no `cassandra-stress`, whose schema is not B3c's table): 40,000 partitions x 10 rows x 1,024-byte blobs, each blob distinct and seeded, 128 requests in flight, with `nodetool flush ks <table>` after every 5,000 partitions (8 L0 files). One table per arm (`t_s5`, `t_s20`, ...) dropped after the arm; `auto_snapshot: false` in the node yaml so a drop leaves no snapshot.
3. **Disk observable (B3d).** The `du -sb` sampler (1 s) reads the table directory `data/ks/<table>-*`; the node-data total is sampled too but includes the commit log and is not the quantity B3f refers to ("live size": input + output).
4. **Controls (B3h).** The STCS control is the same data in an STCS table without the option (STCS rejects `sstable_size_in_mb` as an unknown option); `nodetool compact` leaves one file. The wide-row control (S = 20) adds one partition `pk = -1` of 60 rows x 1 MiB to the same 400 MiB base; prediction: one Data.db of at least 60 MiB.
5. **Expected live size.** 400,000 rows x (1,024 B + keys and row overhead) is about 410-420 MiB, so S = 80 gives 5 or 6 files and the default gives 3; B3f's "within roughly +-1 file plus +-5 %" covers both.
6. **Node configuration.** `compaction_throughput: 0MiB/s`, `auto_snapshot: false`, `MAX_HEAP_SIZE=2G HEAP_NEWSIZE=512M` from the environment, `ulimit -n 100000`, one data directory under `~/stage4-sml1/node` on `/` (local, 47 GB free at audit), `nodetool setcompactionthroughput 0` checked; `compactionstats`, `tablestats` and `sstablemetadata` as in B3d.

**B4. Risks and cleanup.**
- Disk: unit tier writes under the copy's `build/test/cassandra` (about 1 GiB at peak). The cluster tier peaks at about 2 x 400 MiB per run plus commit log, so provision >= 10 GiB local and check `df` first. Never point any directory at shared storage.
- Processes: stop the node (`nodetool drain`, kill), confirm with `pgrep -f CassandraDaemon` and `pgrep -f ant`, and stop the `du` sampler and any stress process.
- Cleanup: `DROP KEYSPACE ks`, `nodetool clearsnapshot`, remove `/local/work/node-data`, `/local/work/cass-unit` and `/local/work/cass-node`.
- Do not build or edit in the shared source tree. All edits are in the local copy.

## C. Sources read

- /users/jason92/writeup-A/playbook-autonomous.md
- /users/jason92/writeup-A/_TEMPLATE-autonomous.md
- src/java/org/apache/cassandra/db/compaction/writers/MajorLeveledCompactionWriter.java
- src/java/org/apache/cassandra/db/compaction/LeveledCompactionStrategy.java (lines 50-110, 180-295, 568-627)
- src/java/org/apache/cassandra/db/compaction/LeveledCompactionTask.java (lines 30-80)
- src/java/org/apache/cassandra/db/compaction/LeveledManifest.java (lines 178-195, plus grep hits)
- src/java/org/apache/cassandra/db/compaction/writers/CompactionAwareWriter.java (lines 130-320)
- src/java/org/apache/cassandra/db/compaction/writers/MaxSSTableSizeWriter.java (grep hit only, line 78)
- src/java/org/apache/cassandra/db/compaction/CompactionManager.java (lines 984-1013)
- src/java/org/apache/cassandra/io/util/SequentialWriter.java (lines 300-325)
- src/java/org/apache/cassandra/io/compress/CompressedSequentialWriter.java (lines 115-145)
- doc/modules/cassandra/pages/managing/operating/compaction/lcs.adoc (grep lines 78-83)
- test/unit/org/apache/cassandra/db/compaction/writers/CompactionAwareWriterTest.java (lines 60-90, 160-200)
- test/unit/org/apache/cassandra/db/compaction/LeveledCompactionStrategyTest.java (grep hits)
- Grep sweeps over src/java for `sstable_size_in_mb`, `getEstimatedOnDiskBytesWritten`, `MajorLeveledCompactionWriter`

## D. Stage-4 feedback

**2026-10-24, stage 4 (pc12, one run per tier, no run 2).** Results: [`results/sstable_size_in_mb-shouldSwitchWriterInCurrentLocation-maxSSTableSize--autonomous.md`](../../stage4-runtime-verification/results/sstable_size_in_mb-shouldSwitchWriterInCurrentLocation-maxSSTableSize--autonomous.md). Case-file version: sha256 `56434a6293ee9c6ec2e5acbb10d1c3a46921760e1eb1db471c02b827be1a0d84` (after the audit's B2i and B3i amendments; the file is untracked, so no commit holds it).

- **Verdict:** unit **Confirmed — caps**; cluster **Confirmed — caps**. **Outcome class: true positive** (estimate `positive`, effect `caps`).
- **What was measured:** every non-final output Data.db of a major LCS compaction was just above `sstable_size_in_mb` (excess 4 to 10 KiB, at most one partition; the file length equals the operand recorded at the switch); the output count followed the option (unit: 10 / 50 / 199 / 1 files for `S` = total/10, /50, /200, `Long.MAX_VALUE`; cluster: 80 / 20 / 5 / 3 files for 5 / 20 / 80 / 160 MiB on 417 MB, exactly the B3f counts). Levels followed the `maxBytesForLevel` fill (10 in L1 and 40 in L2 for 50 files). Peak table-directory bytes were 2.00 to 2.01 x the input in every arm, independent of the option, so the scope limit in the estimate stands: the option caps file size, not total or transient disk.
- **Bypass recorded:** one partition larger than the limit is never split (unit: a 12 MiB partition at `S` = 4 MiB gave a 13.35 MB file; cluster: a 60 MiB partition at 20 MiB gave a 75.6 MB file). An STCS table of the same data gave one file.
- **Amended before run 1 (B2i, B3i, 2026-10-24):** own populate with distinct 1 KiB blobs (the upstream helper's identical payload is hidden by LZ4); compressed-run bound `S + maxPartition + 2 x 16 KiB + 64 B`; exact wide-partition arm; auto-compaction kept off through `nodetool compact` (`getMaximalTask` returns `null` when any sstable is already compacting); driver loader, flush cadence, `du` on the table directory (node-data `du` includes the commit log); the STCS control cannot carry `sstable_size_in_mb`.
- **For stage 3:** in A1, the validation `fanout^8 x sstable_size_in_mb` must fit a `long` (`LeveledCompactionStrategy.java:608-621`); the paths in B2a/B3a/B4 (`/local/work/...`, `~/writeup-A`) do not exist on the stage-4 nodes.
