# DEFAULT_SMALLEST_SSTABLE_BYTES — verification solution  <!-- file: cases/DEFAULT_SMALLEST_SSTABLE_BYTES-shouldSwitchWriterInCurrentLocation-getEstimatedOnDiskBytesWritten--autonomous.md -->

| Field | Value |
|---|---|
| Entry pointer | `src/java/org/apache/cassandra/db/compaction/writers/SplittingSizeTieredCompactionWriter.java:84` |
| Pinned source | `cassandra-5.0.9` |
| Session / date | Claude Sonnet 5.5 (claude-sonnet-5-5), Claude Code CLI (Agent SDK), 2026-10-25 |
| Estimate | `negative`. The constant `DEFAULT_SMALLEST_SSTABLE_BYTES` (50,000,000 bytes) is a floor on the size of the split output pieces of a `nodetool compact -s` on STCS. It decides how many pieces there are, not how many bytes are written, so it does not bound memory or disk use. |
| Ground | The split ratios are fractions of `totalSize` (the input size), so the sum of output sizes equals the input size for any value of the constant. The constant only changes how that total is divided (at most 20 pieces; the last piece takes the remainder). The writer also has no hard stop: the last piece is never switched away from (line 84, `currentRatioIndex < ratios.length - 1`). The only disk-space check on this path (`CompactionAwareWriter.getWriteDirectory`) uses `getExpectedWriteSize()`, which is `totalSize * ratios[0]`, about half the input. It uses a different quantity from the line-84 comparison. |

## A. Constraint trace

**A1. The constraint.**
- Name: `SplittingSizeTieredCompactionWriter.DEFAULT_SMALLEST_SSTABLE_BYTES`, passed into the constructor parameter `smallestSSTable`.
- Kind: compile-time constant, `public static final long`.
- Declared at `SplittingSizeTieredCompactionWriter.java:42` (`= 50_000_000`, decimal 50 MB although the comments say "50MiB" at lines 36 and 68).
- Unit: bytes.
- Default: the literal 50,000,000. It is not derived from anything.
- Setting: not settable by yaml, `-D` or JMX. The 4-argument constructor (line 49-52) always passes the default. The 5-argument constructor (line 54) takes an explicit value, and only the unit test uses it (`test/unit/.../CompactionAwareWriterTest.java:139`, passes 0). Changing the value in production means editing the source and rebuilding.
- The only production caller is `SizeTieredCompactionStrategy.SplittingCompactionTask.getCompactionAwareWriter` (`SizeTieredCompactionStrategy.java:361`). It is created in `getMaximalTask(..., splitOutput=true)` (`SizeTieredCompactionStrategy.java:205-214`), reached from `nodetool compact -s/--split-output` (`tools/nodetool/Compact.java:38-39`, `NodeProbe.java:476-478`, `ColumnFamilyStore.java:2518-2520`, `CompactionStrategyManager.java:1076`). `Compact.java:60` rejects `-s` combined with a user-defined or token-range compaction.
- The line-84 comparison therefore only runs for a major compaction with split output on an STCS table.

**A2. What it caps.**
- Resource: disk (sstable output files written by a compaction). No heap or off-heap object is bounded.
- Quantity compared at line 84: `sstableWriter.currentWriter().getEstimatedOnDiskBytesWritten()` (bytes written so far to the current output data file) against `currentBytesToWrite` (= `Math.round(totalSize * ratios[currentRatioIndex])`).
  - For an uncompressed table the value is `SequentialWriter.getEstimatedOnDiskBytesWritten` = `position()` (`io/util/SequentialWriter.java:314-317`, `getOnDiskFilePointer` at ~line 310).
  - For a compressed table it is `CompressedSequentialWriter.getEstimatedOnDiskBytesWritten` = `chunkOffset` (`io/compress/CompressedSequentialWriter.java:128-132`).
  - `SortedTableWriter.java:339-341` delegates to the data writer.
- The 50 MB constant is used only at line 72, to decide how many ratios to keep. It is never compared to bytes written.

**A3. Mechanism.**
1. Constructor (lines 54-79): `totalSize = cfs.getExpectedCompactedFileSize(nonExpiredSSTables, txn.opType())` (line 58). For a COMPACTION operation this is the sum of input sstable on-disk bytes (`ColumnFamilyStore.java:1698-1703`, `SSTableReader.getTotalBytes`). Only CLEANUP gets the local-range and compression-ratio estimate.
2. Lines 59-65 build `potentialRatios[20]` = 1/2, 1/4, ... 1/2^20.
3. Lines 67-76: loop adds ratios until the first one with `ratio * totalSize < smallestSSTable`. That ratio is included (the `break` follows the `noPointIndex++`). `ratios` = the first `noPointIndex` entries (line 77). For `totalSize` of 1 GB: 0.5, 0.25, 0.125, 0.0625, 0.03125 (31 MB < 50 MB) gives 5 ratios. If `totalSize` < 100 MB the loop stops at index 0 and there is a single ratio (0.5) and therefore a single output sstable.
4. Line 78: `currentBytesToWrite = round(totalSize * ratios[0])` (about half the input).
5. Per partition, `CompactionAwareWriter.append` (`CompactionAwareWriter.java`, `maybeSwitchWriter`) calls `maybeSwitchLocation` first (line ~178-204), then `shouldSwitchWriterInCurrentLocation` (the target method).
6. Line 84, switch when `bytesWrittenInCurrentWriter > currentBytesToWrite && currentRatioIndex < ratios.length - 1`.
   - True: `currentRatioIndex++`, `currentBytesToWrite = getExpectedWriteSize()` (= `round(totalSize * ratios[newIndex])`, lines 107-110), log "Switching writer", return true. The base class then calls `switchCompactionWriter`, which builds a new sstable writer with `setKeyCount(sstableKeyCount())` (lines 99-104: `round(ratios[idx] * estimatedTotalKeys)`).
   - False: keep appending to the same sstable.
7. Consequences:
   - The check runs before the append, so each non-final piece overshoots its target by up to one partition (a large partition is not split).
   - The last piece never triggers a switch, so it gets everything left, whatever its target. Its target `totalSize * ratios[last]` is never compared (it only sets the key-count hint). Example: for 1 GB the pieces are about 500, 250, 125, 62.5 MB and about 62.5 MB remainder. The comment at line 84 says the same.
   - Because the targets are fractions of the input size, the sum of output pieces is about the compaction output size (input minus shadowed data and tombstones, so at most the input).
   - No branch stops, throttles or fails the compaction because of the constant.
   - If the on-disk size shrinks (overwrites, TTL, compression change), the actual output can be much smaller than `totalSize` and the later pieces never reach their targets. Fewer pieces than planned are produced, with no error.
8. Disk-space check: for the first writer, `maybeSwitchLocation` calls `getWriteDirectory(nonExpiredSSTables, getExpectedWriteSize())` (`CompactionAwareWriter.java:185`, `:265-298`). `getExpectedWriteSize()` is overridden to `round(totalSize * ratios[currentRatioIndex])`, i.e. half the input, and `available < estimate` throws "Not enough space" (`:281-286`). So the split compaction reserves/checks only about half of its final output, which is an under-estimate and independent of the 50 MB constant. Whether `CompactionTask` has an earlier whole-task space check was not read (see C).
   - **[Amended 2026-10-25, stage-4 audit; see B3i.5]** `CompactionTask` does have one: `CompactionTask.java:147-153` calls `buildCompactionCandidatesForAvailableDiskSpace` (`:384-452`) before the writer exists. It asks `Directories.hasDiskSpaceForCompactionsAndStreams` (`Directories.java:524-561`) for the whole expected output, `getExpectedCompactedFileSize` = the sum of the input `onDiskLength` (`ColumnFamilyStore.java:1698-1703`), i.e. all of `totalSize`, not `totalSize * ratios[0]`, against `usable space * max_space_usable_for_compactions_in_percentage (0.95) - min_free_space_per_drive (50 MiB)`. It does not read the 50 MB constant. So the "only about half is reserved" statement above holds for the writer's own check only; the task-level check is stricter and runs first.

**A4. Other consumers.**
- Disk on the same data directories is also used by the input sstables (kept until commit, so peak is about input + output, i.e. about 2x), other concurrent compactions, flushes, commit log, hints, snapshots and backups, and `Directories`/`DiskBoundaries` logic.
- Memory: `SSTableRewriter`, bloom filters, partition index and compression metadata per open writer, plus off-heap buffers. None are governed by this constant. `setKeyCount(sstableKeyCount())` sizes the bloom filter per piece, and the sum of the hints is about `estimatedTotalKeys`.
- Compaction throughput throttling (`compaction_throughput`) and `concurrent_compactors` govern rate and concurrency, not size.

**A5. Evidence beyond the source.**
- Test `test/unit/org/apache/cassandra/db/compaction/writers/CompactionAwareWriterTest.java:130-165` (`testSplittingSizeTieredCompactionWriter`): with `smallestSSTable=0`, expects output sizes about 1/2, 1/4, ... of the input (1% tolerance) and the last piece taking the rest.
- Class javadoc, `SplittingSizeTieredCompactionWriter.java:32-37`.
- No external links are relied on.

## B. Verification solution

**B1. Claim under test.** Changing the "smallest sstable" threshold changes only the number and sizes of the output pieces of a split STCS major compaction and not the total bytes written to disk (about the input size, within the compaction's normal shrink), and it does not stop a piece from exceeding the threshold: the last piece exceeds it by design and the others exceed their targets by up to one partition. Equivalently, the 50 MB constant is not a cap on disk use.

### B2. Unit tier

**B2a. Environment and build.**
- Linux, JDK 11, Ant.
- Copy the tag to local disk (for example `rsync -a ~/cassandra-5.0.9/ /local/$USER/c509/`), never build in the shared tree.
- Build there with `ant jar` (or `ant build-test`).
- Put a new JUnit class `SplittingWriterProbeTest` next to `CompactionAwareWriterTest` in the copy (`test/unit/org/apache/cassandra/db/compaction/writers/`), reusing its helpers (`populate`, `getColumnFamilyStore`, `compact`, see `CompactionAwareWriterTest.java:131-139`).
- Run with `ant testsome -Dtest.name=org.apache.cassandra.db.compaction.writers.SplittingWriterProbeTest`. Use `-Xmx1g` (the ant test default is fine). Data dir under the test's default `build/test/cassandra`, which is on local disk in the copy.

**B2b. Knobs.** The 5-argument constructor's `smallestSSTable` is the only knob, since the constant is not otherwise settable.
- Values: 0 (the existing test; the 20-piece maximum), 50_000_000 (the production default), and a value larger than the input (for example `10 * inputBytes`) to force a single piece.
- Also vary the input size (see B2c).
- Set by passing the argument in the constructor call.

**B2c. Workload.**
- Create one sstable of known on-disk size S by `populate(rowCount)` with sizeable values (for example 200,000 rows of 1 KB blob, about 200 MB uncompressed; set the table `compression = {'enabled': false}` so that `chunkOffset` and `position()` coincide). Flush, disable autocompaction.
- Open a `LifecycleTransaction` over all sstables and run `compact(cfs, txn, writer)` as the existing test does.
- Arithmetic for S = 200 MB and the default 50 MB: ratios 0.5 (100 MB), 0.25 (50 MB, not below 50 MB so continue), 0.125 (25 MB < 50 MB, stop and include). That gives 3 ratios and so 3 pieces: about 100, 50 and the remainder of about 50 MB. With `smallestSSTable=0`: 20 ratios, pieces about 100, 50, 25, ... 12 pieces' worth until the data runs out. The last piece takes the remainder (at least 1/2^19 of S).
- Also run S = 40 MB (below 100 MB): exactly 1 ratio and 1 piece.

**B2d. Observables and instruments.**
- Via reflection or a small subclass: `ratios` length and values, `currentBytesToWrite` after each switch.
- Count of `shouldSwitchWriterInCurrentLocation` true returns (wrap in a subclass that records the return value and `getEstimatedOnDiskBytesWritten()` at each call; the method is protected, so subclass in the same package).
- After `finish()`: the list of live sstables with `onDiskLength()`; sum of output sizes vs input size; the size of the last piece vs `smallestSSTable`.
- The invariant that cannot be observed directly in the unit tier: real heap or disk pressure. Only the check's own operand is observed.

**B2e. Procedure.**
1. Build the test copy; create the probe test.
2. For each (S, `smallestSSTable`) pair in {(200 MB, 0), (200 MB, 50e6), (200 MB, 10*S), (40 MB, 50e6)}: truncate, `populate`, record `inputBytes = sum(onDiskLength)`.
3. Build the writer, run `compact`, record the number of pieces N, each piece's `onDiskLength`, `ratios.length`, the switch count, and sum(output).
4. For the (200 MB, 50e6) run also log the value of `getEstimatedOnDiskBytesWritten()` at each switch.
5. Assert nothing; print one table. Then `rm -rf build/test/cassandra/*` and confirm no leftover java process (`pgrep -f ant`).

**B2f. Predictions (stated before any run).**
- (200 MB, 50e6): `ratios.length == 3`, N == 3, pieces about 100 / 50 / 50 MB (the first two within 1% plus one partition of the target; the last is the remainder). Switch count == 2.
- (200 MB, 0): `ratios.length == 20` (no ratio satisfies `< 0`), so N is at most 20; the first pieces about 100, 50, 25, 12.5, 6.25 ... MB; the last piece is the remainder. Switch count == N-1.
- (200 MB, 10*S): `ratios.length == 1`, N == 1, one piece of about S, switch count 0.
- (40 MB, 50e6): `ratios.length == 1`, N == 1, one piece about 40 MB, which is below the "smallest" 50 MB (a piece smaller than the constant is possible, so the constant is not a minimum guaranteed).
- In every run sum(output) is within about 1-2% of `inputBytes` (no tombstones or overwrites in the workload), independent of `smallestSSTable`.
- The last piece's size can be larger than `smallestSSTable` and than its own target (`totalSize * ratios[last]`).

**B2g. Readings.**

| Observation | Meaning |
|---|---|
| sum(output) is the same (within 2%) for all `smallestSSTable` values while N and `ratios.length` change as predicted | Claim confirmed: the constant partitions the output and does not change the volume. |
| sum(output) shrinks or grows with `smallestSSTable` by more than the normal 2% | Claim refuted: the constant changes bytes written, so re-trace. |
| Last piece size > `totalSize*ratios[last]` and > `smallestSSTable` in the (200 MB, 0) run | Confirms no hard cap (the last piece takes the remainder). |
| A piece (non-final) larger than target + one partition | Overshoot beyond the traced rule, a new finding. |
| `ratios.length` differs from the arithmetic in B2c | The loop trace (lines 67-77) is wrong, so re-read. |
| Positive control (B2h) does not move with its own knob | Not confirmed: the harness is not measuring the operand. |
| N == 1 for (200 MB, 50e6) | The input was smaller than assumed (check `inputBytes`), so not confirmed. |

**B2h. Controls.**
- Positive control: run the same input through `MaxSSTableSizeWriter` (`writers/MaxSSTableSizeWriter.java:78`, `getEstimatedOnDiskBytesWritten() > maxSSTableSize`, a real per-piece cap that does bind). With `maxSSTableSize` = 20 MB every piece except the last is about 20 MB (+ one partition), and the number of pieces rises as the knob falls, showing the harness can see a binding size limit. This is the "cap that binds" comparator.
- Disable compression so the operand is `position()`; repeat once with default LZ4 compression to show `chunkOffset` gives the same shape.
- Fixed seed and fixed row sizes so that input size is identical across runs.

**B2i. Amendments from the stage-4 audit (2026-10-25, before any reading; they sharpen B2c to B2h and change no direction of B2f or B2g).**
1. *Exact input.* One uncompressed sstable built from 20,000 partitions x 10 rows x 1,024 bytes of distinct seeded random bytes (the writer is driven directly, so the strategy of the input table is irrelevant). `T` = `totalSize` in the writer = the input's `onDiskLength()` = its Data.db length (`SSTableReader.getTotalBytes`, `SSTableReader.java:541-547`, `onDiskLength` `:983-986`), about 208 MB. **Validity gates:** `200e6 <= T < 400e6` for the (T, 50e6) arm (B2f's N == 3 needs `T/4 >= 50e6` and `T/8 < 50e6`), and `T < 100e6` for the small arm (3,800 partitions, about 39.6 MB). A run outside the gate is Invalid, not Refuted.
2. *Ratio-count rule, derived from lines 61-77.* `ratios.length` = min(20, the first k >= 1 with `T / 2^k < smallestSSTable`), and 20 when `smallestSSTable = 0`. For T in [200e6, 320e6): 50e6 gives 3, 5e6 gives 6 (`T/32 >= 5e6`, `T/64 < 5e6`), 0 gives 20, `10 * T` gives 1.
3. *Size relation, derived from lines 84, 87 and 107-110.* The i-th output (i = 0, 1, ...) that is not last has `size` in `(round(T * 2^-(i+1)), round(T * 2^-(i+1)) + maxPartition]`, where `maxPartition` is the largest partition (about 10.4 KB here), because the test runs before each append and the Data.db length equals the operand (uncompressed). The last output is the remainder. With S = 0 the targets fall below one partition from i = 14 on, so those outputs hold one partition each and the last output holds whatever remains; the analyzer computes the exact N from the partition size (a model check, reported as `MODEL`; the verdict rows are B2f and B2g).
4. *Extra knob value.* `smallestSSTable = 5_000_000` (6 outputs for the 208 MB input) is added, so the arms are 0, 5e6, 50e6 (default) and `10 * T`, all on the same input; the 40 MB arm and one compressed arm (default LZ4, same seeded random bytes, so nearly incompressible; relation 3 holds with `maxPartition + 2 * 16 KiB + 64 B` as the granularity, as in the closed sibling case) complete B2e.
5. *Positive control, exact.* The same input through `MaxSSTableSizeWriter(cfs, dirs, txn, originals, m, 0)` for m = 20e6 and m = 40e6: every output but the last in `(m, m + maxPartition]`, counts about `T/m` (10 or 11 and 5 or 6), and the count falls when `m` rises. It is the same recording, the same files, the same analyzer, so a null result on the split writer cannot be a blind instrument.
6. *Instrument.* A subclass of `SplittingSizeTieredCompactionWriter` in the same package records, at each `shouldSwitchWriterInCurrentLocation` call, the operand, the returned boolean, `currentBytesToWrite` and `currentRatioIndex` (reflection on the private fields), then calls `super`. `ratios` is read by reflection after construction.

### B3. Cluster tier

**B3a. Environment and build.**
- One node (a second node adds nothing for a local compaction), Linux, JDK 11.
- Build from the local copy of the tag on local disk: `ant jar` in `/local/$USER/c509`. Run from `/local/$USER/c509/bin/cassandra -f`.
- Config (`conf/cassandra.yaml`): `data_file_directories`, `commitlog_directory`, `hints_directory`, `saved_caches_directory` all under `/local/$USER/node1/` (local disk of known size, at least 3x the data size for the split run).
- `compaction_throughput: 0` (unthrottled) so the runs finish quickly. `concurrent_compactors: 1`. `listen_address`/`rpc_address` = 127.0.0.1.
- JVM: `-Xms2G -Xmx2G`.
- Table: `CREATE TABLE ks.t (k bigint, c int, v blob, PRIMARY KEY (k, c)) WITH compaction = {'class':'SizeTieredCompactionStrategy'} AND compression = {'enabled':'false'}`.

**B3b. Knobs.**
- Knob 1: `nodetool compact` with and without `-s` (split vs single output). This is the only user-visible switch for the code path; the 50 MB constant itself is not settable at runtime.
- Knob 2 (build-time): build two jars from the copy, one with `DEFAULT_SMALLEST_SSTABLE_BYTES` at 50_000_000 and one edited to 5_000_000 (line 42), to vary the constant itself. Edit only the local copy.
- Knob 3: total data size D (see B3c).

**B3c. Workload.**
- Load D = 2 GB of unique partitions with `cassandra-stress` or a CQL loop: 2,000,000 rows x 1 KB blob, written with `flush` between batches of 250,000 rows so that 8 sstables of about 250 MB each exist (STCS min threshold 4 would merge them in the background, so run `nodetool disableautocompaction ks t` before the load).
- Arithmetic for the default 50 MB: with `totalSize` = 2 GB the ratios are 0.5 (1 GB), 0.25 (512 MB), 0.125, 0.0625, 0.03125, 0.0156 (31 MB < 50 MB, stop): 7 ratios, so up to 7 output sstables, last one holding the remainder (about 32 MB or more). **[Corrected 2026-10-25, B3i.1: the listed ratios are six, so 6 ratios and 6 outputs.]**
- With the constant at 5 MB: ratios down to 0.0019 (4 MB) and so 10 ratios, up to 10 outputs. **[Corrected 2026-10-25, B3i.1: 0.0019 is the 9th ratio (2^-9), so 9 ratios and 9 outputs for T about 2.08e9.]**
- Also a small-data case, D = 80 MB: ratios.length is 1 and the split compaction yields 1 sstable. **[Amended 2026-10-25, B3i.1: for the 5 MB jar the same data gives 5 ratios.]**
- Duration: a few minutes per compaction at unthrottled speed on local disk.

**B3d. Observables and instruments.**
- Disk: `du -sb /local/$USER/node1/data/ks/t-*` sampled every 1 s during the compaction (shell loop or `watch`), recording the peak and the final value. `ls -l *-Data.db` after the compaction gives per-piece sizes.
- `nodetool tablestats ks.t` (Space used (live), Space used (total), SSTable count), `nodetool compactionstats` for progress.
- Log lines "Switching writer, currentBytesToWrite" (set `logger.org.apache.cassandra.db.compaction.writers` to DEBUG with `nodetool setlogginglevel org.apache.cassandra.db.compaction.writers DEBUG`).
- Heap: `jstat -gc <pid> 1000` for context, to show heap does not change systematically with the constant.
- Not observable directly: the writer's `ratios` array (read it from the DEBUG log pattern instead).

**B3e. Procedure.**
1. Build the jar; start the node; create the keyspace/table; `nodetool disableautocompaction ks t`; enable DEBUG log level above.
2. Load D = 2 GB in 8 flushed batches. Record `du -sb` (baseline B0) and sstable count (8).
3. Run A: `nodetool compact ks t` (no `-s`, the control). Start the `du` sampler beforehand. Record peak, final, N sstables. Expect N = 1.
4. Reload the same data (stop node, wipe the data dir, restart, reload; or use `nodetool snapshot` + restore before step 3) to the same 8-sstable state.
5. Run B: `nodetool compact -s ks t` with the 50 MB jar. Record peak du, final du, per-piece sizes, N, and the DEBUG switch lines.
6. Restore the 8-sstable state again; stop the node; swap in the 5 MB jar (line 42 edited in the local copy); restart; run C: `nodetool compact -s ks t`. Record the same.
7. Repeat with D = 80 MB for the small-data case.
8. Positive control: with the original jar, set `compaction = {'class':'LeveledCompactionStrategy','sstable_size_in_mb':'100'}` on a copy of the table, load the same data and run `nodetool compact` (`MajorLeveledCompactionWriter`, which switches on `maxSSTableSize`, `MajorLeveledCompactionWriter.java:74`). Record the sstable count, which should be about D / 100 MB, and that it moves when `sstable_size_in_mb` changes to 50.
9. Cleanup (B4).

**B3f. Predictions.**
- Run A (no `-s`): 1 output sstable of about D; peak du about B0 + D (about 2D).
- Run B (50 MB constant, D = 2 GB): 7 outputs, sizes about 1 GB, 512, 256, 128, 64 MB, and then 2 remaining pieces, with the last one the remainder (about 32 MB or more, bigger than its 31 MB target and, if the arithmetic holds, about 32 MB) **[Corrected 2026-10-25, B3i.1: 6 outputs, about 0.5T, 0.25T, 0.125T, 0.0625T, 0.03125T and a remainder of about 0.03125T (about 65 MB, above its own target 0.015625T and above 50 MB)]**; total final du within 2% of Run A's final du. Peak du about B0 + D, within 5% of run A's peak.
- Run C (5 MB constant): about 10 outputs **[Corrected 2026-10-25, B3i.1: 9 outputs]**, final total and peak within 2% / 5% of run A and B.
- D = 80 MB: 1 output sstable (about 80 MB, which is below the 100 MB threshold), with either jar's output the same, only for the 5 MB jar can ratios reach 0.0625 (5 MB) giving up to 4-5 pieces. **[Corrected 2026-10-25, B3i.1: this sentence contradicts itself; the 50 MB jar gives 1 output and the 5 MB jar gives 5 outputs for T about 92 MB.]**
- Heap (`jstat`) shows no relation between the constant and the peak old-gen usage within normal noise (less than 10% difference between runs).
- Positive control: LCS sstable count about 20 for 100 MB and about 40 for 50 MB (a knob that does bind).

**B3g. Readings.**

| Observation | Meaning |
|---|---|
| Final du and peak du equal across Runs A, B, C (within 2% / 5%), piece count changes with the constant, positive control moves with its knob | Claim confirmed: the constant does not cap disk, it only splits. |
| Final or peak du differs systematically between Run B and Run C by more than 5% | Claim refuted: usage follows the constant, so re-trace. |
| Piece count equal for both jars | The edit did not take effect or `-s` path not used (check DEBUG "Switching writer" lines), so not confirmed. |
| Positive control (LCS) sstable count does not change with `sstable_size_in_mb` | Control failed, so not confirmed. |
| Peak du does not exceed B0 + D (the 2x input/output overlap) | Consistent with the input kept until commit (A4). |
| Last piece larger than the 50 MB constant | Confirms no hard stop on the final piece. |
| A "Not enough space" `RuntimeException` appears at half of D free | Confirms the space check only reserves `totalSize*ratios[0]` (A3 step 8) and is a separate finding about the check, not about the constant. **[Amended 2026-10-25, B3i.5: not run. The task-level check asks for all of T first, so the writer's T/2 check is not reachable by lowering free space; this row is replaced by the next one.]** |
| The bytes the task-level space check asks for (`checking if we can write Y bytes`, Directories DEBUG line) differ between arms | Unexpected: Y should equal the input T in every arm and not depend on the constant (B3i.5). |
| Heap peak differs with the constant by more than 10% | Unexpected, so investigate before concluding. |

**B3h. Controls.**
- Run A (unsplit) is the baseline.
- Same data, same flush pattern, same order and the same unthrottled compaction in all runs; restore the identical 8-sstable state before each.
- Compression disabled so `du` equals logical bytes; repeat once with compression on to confirm piece ratios still follow on-disk bytes.
- One compaction at a time (`concurrent_compactors: 1`, autocompaction disabled), no repairs, no other load, so that `du` is only this compaction.
- Positive control in step 8 (LCS `sstable_size_in_mb`) for a cap that does bind.

**B3i. Amendments from the stage-4 audit (2026-10-25, before any reading).** They correct arithmetic and wording found by re-deriving B3 from the source; none depends on a reading.
1. *Corrected ratio counts.* The input is 200,000 partitions x 10 rows x 1,024-byte seeded blobs (2,000,000 rows), loaded in 8 flushes of 25,000 partitions, `T` about 2.085e9 B (the closed sibling case measured 1,042 B per row on disk, so 2.0e6 rows give about 2.085e9). Ratios: constant 50e6 gives 6 (`T/32 = 65e6 >= 50e6`, `T/64 = 32.6e6 < 50e6`; needs `1.6e9 <= T < 3.2e9`), constant 5e6 gives 9 (`T/256 = 8.1e6 >= 5e6`, `T/512 = 4.07e6 < 5e6`; needs `1.28e9 <= T < 2.56e9`), constant 500e6 gives 3 (`T/4 = 521e6 >= 500e6`, `T/8 < 500e6`; needs `2.0e9 <= T < 4.0e9`). **Validity gate: `2.0e9 <= T < 2.56e9`**, else the arm is Invalid. Outputs: the i-th non-final output is in `(round(T * 2^-(i+1)), that + maxPartition]` (about 10.4 KB); the last is the remainder, about `T * 2^-(len-1)`: 65 MB for the 50e6 jar, 8.1 MB for the 5e6 jar, 521 MB for the 500e6 jar. The small-data case (8 flushes of 1,100 partitions, `T` about 92e6, gate `80e6 <= T < 100e6`): 1 output with the 50e6 jar, 5 outputs (0.5T, 0.25T, 0.125T, 0.0625T, remainder 0.0625T) with the 5e6 jar.
2. *Third constant value.* A third jar with the constant edited to 500_000_000 (line 42) is added to B3b knob 2, so the values are 5e6, 50e6 (default) and 500e6 (3 jars: three copies of the tree, each built with `ant jar`; the node runs from one tree at a time). Predicted outputs for `nodetool compact -s` on the 2 GB input: 9, 6 and 3; the plain `nodetool compact` (no `-s`) gives 1.
3. *Arms, all on the same seeded data, one table per arm, auto-compaction disabled, `auto_snapshot: false`:* default jar: plain, split, split again (noise floor), split on a compressed table (default LZ4, nearly incompressible data, so `T` is within about 1% and the same counts hold), small-data split, LCS `sstable_size_in_mb` = 100 and 50 (positive control, step 8 as filed: `nodetool compact` on LCS, `MajorLeveledCompactionWriter`, files about `T / S`, i.e. 20 and 40 within one); 5e6 jar: split and small-data split; 500e6 jar: split. LCS is the closed `sstable_size_in_mb` case's mechanism, so it is a known-binding cap on the same resource (files bytes on local disk) measured by the same instruments.
4. *Direct disallow evidence.* `nodetool setlogginglevel org.apache.cassandra.db.compaction.writers DEBUG` (before each compaction; the lines go to `debug.log`, not `system.log`, whose threshold is INFO). Each `Switching writer, currentBytesToWrite = X` line is one `true` return of line 84; the count is `ratios.length - 1` and the i-th X is `round(T * 2^-(i+2))`.
5. *CompactionTask space check (the open caveat), read in the audit.* See A3 step 8 (amended). Effects on this file: (a) it compares the whole expected output T, not ratios or the 50 MB constant, so it is a different constraint (free space against the compaction's total size) and does not change B1; (b) because it asks for `T` where the writer asks for `T/2`, and it runs first, the filed row "Not enough space at half of D free" cannot be reached by lowering free space, so it is not run (replaced above in B3g); (c) the DEBUG line `checking if we can write Y bytes` (`Directories.java:550`, enable `org.apache.cassandra.db.Directories` DEBUG) is read in every arm: Y must equal T and be the same for every constant. On the test node (about 50 GB free, T about 2 GB) the check never fails; a disk too small for T would make a major compaction drop its largest input (`reduceScopeForLimitedSpace`, `partialCompactionsAcceptable()` is true because `nodetool compact` is not user-defined) or throw `Not enough space for compaction`, regardless of the constant.
6. *Heap is context.* `jstat -gc` (1 s) and `RssAnon` (0.5 s) are sampled and reported; because heap readings carry garbage-collection noise, the B3g heap row is read against the spread between the two identical split arms of the default jar: a difference between constants counts only if it exceeds both 10% and that spread.
7. *Environment.* The node uses its own tree, data directory and ports (loopback address 127.0.0.77, JMX 7277) because the node is shared with another run; no reading depends on that. Not read back from the live node: nothing else (heap 2 GB, `compaction_throughput: 0MiB/s`, `concurrent_compactors: 1` are set in the yaml and environment and checked in `debug.log`/`nodetool` output where possible).

**B4. Risks and cleanup.**
- Disk: a split compaction needs about 2x D free on the local data volume (input + output). With D = 2 GB provision at least 8 GB. Check `df` before starting and never point any directory at shared storage (NFS or home).
- Unit tier writes only under `build/test/cassandra` of the local copy; remove it after each run.
- Never build in or write to the shared source tree: all edits (line 42 in the 5 MB build, the probe test) are in the local copy only.
- Processes: stop the node (`nodetool drain` then kill the pid, or Ctrl-C of `-f`), kill any `ant`, `jstat`, `du` or `watch` loops, then verify `pgrep -fl 'cassandra|ant|jstat'` is empty.
- Cleanup: `rm -rf /local/$USER/node1 /local/$USER/c509/build/test/cassandra`; delete the copy when done.

## C. Sources read

- `/users/jason92/writeup-A/playbook-autonomous.md`
- `/users/jason92/writeup-A/_TEMPLATE-autonomous.md`
- `src/java/org/apache/cassandra/db/compaction/writers/SplittingSizeTieredCompactionWriter.java`
- `src/java/org/apache/cassandra/db/compaction/writers/CompactionAwareWriter.java` (lines 40-300 and `getExpectedWriteSize` at ~303)
- `src/java/org/apache/cassandra/db/compaction/SizeTieredCompactionStrategy.java` (lines 205-214, 336-367)
- `src/java/org/apache/cassandra/db/ColumnFamilyStore.java` (lines 1698-1720, via grep for 2518)
- `src/java/org/apache/cassandra/io/util/SequentialWriter.java` (~305-320)
- `src/java/org/apache/cassandra/io/compress/CompressedSequentialWriter.java` (~120-140)
- `test/unit/org/apache/cassandra/db/compaction/writers/CompactionAwareWriterTest.java` (125-175)
- grep results (not full reads) for `SplittingSizeTieredCompactionWriter`, `DEFAULT_SMALLEST_SSTABLE_BYTES`, `getEstimatedOnDiskBytesWritten`, `splitOutput` across `src/` and `test/`, and for `Compact.java`, `NodeProbe.java`, `CompactionStrategyManager.java`, `MaxSSTableSizeWriter.java:78`, `MajorLeveledCompactionWriter.java:74`, `SortedTableWriter.java:339`.
- Not read: `CompactionTask`'s own whole-task disk-space check (the claim in A3 step 8 is about the writer only). **[Amended 2026-10-25: read by the stage-4 audit, `CompactionTask.java:95-125, 147-153, 379-452` and `Directories.java:517-569`; see A3 step 8 and B3i.5.]**

## D. Stage-4 feedback

**Stage-4 result (2026-10-25): both tiers Confirmed; effect on the constraint: does not cap; outcome class: true negative (estimate `negative`).** Full record: [`results/DEFAULT_SMALLEST_SSTABLE_BYTES-shouldSwitchWriterInCurrentLocation-getEstimatedOnDiskBytesWritten--autonomous.md`](../../stage4-runtime-verification/results/DEFAULT_SMALLEST_SSTABLE_BYTES-shouldSwitchWriterInCurrentLocation-getEstimatedOnDiskBytesWritten--autonomous.md). The prediction tables were frozen at sha256 `85fd62603142696ba3ccd5d5e7f2512dc195fd811c3400e8d0bf82f3a89b455c` (this file after the audit amendments below and before this section was filled).

- **Unit (B2): Confirmed, B2g row 1.** The same 208 MB input through `smallestSSTable` = 0 / 5e6 / 50e6 / 10 x T gave 12 / 6 / 3 / 1 outputs and 208.44 to 208.53 MB written in all four (0.04% apart); every non-final piece was within one partition (at most 10,386 B) above its target `round(T x 2^-(i+1))`; the last piece exceeded its own target (52.1 MB against 26.1 MB, and above the 50 MB constant, for the default). The positive control `MaxSSTableSizeWriter` gave 11 then 6 outputs at 20e6 then 40e6. 72 checks pass.
- **Cluster (B3): Confirmed, B3g row 1.** On 2.085e9 B (200,000 partitions), `nodetool compact -s` with the constant edited to 5e6 / 50e6 / 500e6 gave 9 / 6 / 3 pieces (the `Switching writer` DEBUG lines carried exactly `round(T x 2^-(i+2))`), the same output bytes (2,086,353,942 / 2,086,357,759 / 2,086,357,167, and 2,086,357,597 for the unsplit run) and the same peak table-directory bytes (2.00 x the input, within 0.42%). LCS `sstable_size_in_mb` = 100 / 50 gave 20 / 40 files (positive control). 78 checks pass; the independent self-check holds (67 of 68; the one that does not is an auxiliary peak-ratio assertion on a 1.5 s compaction that the 0.25 s sampler under-sampled).
- **The open caveat (C): resolved.** `CompactionTask` has a whole-task space check (`CompactionTask.java:147-153, 384-452`, `Directories.java:524-569`) that runs before the writer exists. It asks for all of `T` (not `T x ratios[0]`) against 0.95 x usable space less 50 MiB, and for a non-user-defined major compaction drops the largest input until it fits. It never reads the constant. Measured: the DEBUG line `checking if we can write Y bytes` has `Y` = `T` exactly in all 10 cluster arms. So the A3 step 8 statement (the split writer reserves about half of its output) is true of the writer's own check only; the task-level check is stricter and runs first.
- **Corrections made at the audit (before any reading), all in the file above:** B3c/B3f counted 7 and 10 outputs for the 50e6 and 5e6 constants; the arithmetic is 6 and 9 (and 3 for 500e6, added as a third value). The small-data bullet contradicted itself (1 piece for 50e6; 5 for 5e6 on 92 MB). The B3g row "Not enough space at half of D free" is unreachable because the task-level check asks for `T` first; replaced by the row on the bytes it asks for. The DEBUG lines land in `debug.log`, not `system.log`.
- **Notes for the case:** a single output may exceed the constant (the 92 MB input with the default jar made one 91.8 MB output), which is another instance of the claim; the cluster input became 24 sstables (size-triggered flushes), not 8, with no effect on `T`; heap context differed 7.3% across constants against a 0.6% repeat spread (below the 10% rule); the `jstat` named in B3d cannot attach to the node, `jcmd GC.heap_info` was used. `_INDEX.md`, the CSV and `predicted-negative.md` were not edited by stage 4.
