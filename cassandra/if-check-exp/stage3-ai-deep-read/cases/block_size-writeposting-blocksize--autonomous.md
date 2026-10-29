# BLOCK_SIZE (SAI postings block size) — verification solution  <!-- file: cases/block_size-writeposting-blocksize--autonomous.md -->

| Field | Value |
|---|---|
| Entry pointer | [`PostingsWriter.java:222`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/index/sai/disk/v1/postings/PostingsWriter.java#L222) |
| Pinned source | `cassandra-5.0.9` |
| Session / date | Claude Code CLI (Agent-tool subagent), 2026-10-27 |
| Estimate | `negative`: `BLOCK_SIZE` is a hard-coded constant (128) that sets the number of postings per on-disk block, and it bounds neither a memory nor a disk quantity in any operator-controllable way. |
| Ground | The value is a compile-time format constant with no yaml key, `-D` property or JMX setter. The only memory it sizes is one `long[128]` array per writer (about 1 KiB). Disk size of a posting list is set by the number of postings and their delta bit width, not by a cap; the block size only changes per-block padding and skip-table granularity. |

> **Link rule.** Declaration (A1) and if statement (Entry pointer, A3) are permalinks at tag `cassandra-5.0.9`.

## A. Constraint trace

**A1. The constraint.** `BLOCK_SIZE`, a constant, declared at [`PostingsWriter.java:89`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/index/sai/disk/v1/postings/PostingsWriter.java#L89) (`private final static int BLOCK_SIZE = 128;`). The comment at line 88 says it mirrors Lucene's `Lucene50PostingsFormat.BLOCK_SIZE`; the class javadoc (lines 49-50) calls the block size fixed, "currently 128". Unit: postings (longs) per FoR-compressed block. The two public constructors pass it at lines 110 and 115; the instance field `blockSize` is assigned at line 126 in the private constructor. The package-private constructor at lines 118-122 (`@VisibleForTesting`) lets a caller pass another value; the only non-test callers found by grep are `LiteralIndexWriter.java:60` and `BlockBalancedTreePostingsWriter.java:135`, and both use a public constructor (so 128). Settable: no yaml key, no `-D` property, no JMX; changing it needs a source edit and rebuild. The 128 is not derived from anything in this repository. The earlier (unreviewed) trace held up against the source: line numbers 88, 89, 110, 115, 119-122, 126, 129 and 222-226 were all re-checked and are correct. It is not a memory or disk cap.

**A2. What it caps.** Nothing in terms of resource. The quantity compared at line 222 is `bufferUpto`, the number of deltas buffered in the current block (`PostingsWriter.java:102`), against `blockSize`. It bounds the writer's delta buffer `deltaBuffer = new long[blockSize]` (`:129`), i.e. 128 longs = 1024 bytes of heap per writer, and the number of postings per packed block. It is a layout parameter, not a limit on usage.

**A3. Mechanism.** `write(PostingList)` (`:170`) loops over postings and calls `writePosting` (`:186`). In `writePosting` (`:205`), each posting stores a delta in `deltaBuffer[bufferUpto++]` (`:210`, `:218`). The check is [`PostingsWriter.java:222`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/index/sai/disk/v1/postings/PostingsWriter.java#L222) (`if (bufferUpto == blockSize)`).
- True: `addBlockToSkipTable()` (`:224`, body `:246-250`) appends the current file pointer and last posting to two `LongArrayList`s; `writePostingsBlock()` (`:225`, body `:273-301`) writes the block with bit width `unsignedBitsRequired(maxDelta)` (`:275`) via `DirectWriter` (`:285`); `resetBlockCounters()` (`:226`, body `:239-244`) zeroes `bufferUpto`.
- False: the posting stays buffered; nothing is written.
- Tail: `finish()` (`:230-237`) writes a final partial block, padded with zeros up to `blockSize` when bit width is above 0 (`:290-298`).
- `writeSummary` writes `blockSize` into the file (`:254`) and the reader reads it back (`PostingsReader.java:97`), so the value is part of the on-disk format.
Bypass or overshoot: there is no limit to bypass. Memory that does grow with input and is not governed by `blockSize`: `blockOffsets` and `blockMaximumPostings` (`:96-97`) grow by one entry per block within one posting list (cleared per list at `:177-178`), so they scale with list length divided by block size; `inMemoryOutput` (`:98`) holds the compressed offsets for the skip table (`:265-269`).

**A4. Other consumers.** The same heap and disk are used by the SAI segment build buffer and the rest of the index build (the real memory limit there is `segment_write_buffer_size`, declared at `StorageAttachedIndexOptions.java:35`, not verified further here), by memtable and sstable data, the commit log and the page/chunk caches. The posting list data written here ends up in SAI on-disk components, whose total size depends on the number of indexed rows, not on this constant.

**A5. Evidence beyond the source.** none (conclusion drawn from source only).

## B. Verification solution

**B1. Claim under test.** Memory and disk used by the posting-list writer do not follow `BLOCK_SIZE` as a cap: the writer's heap is a fixed small array regardless of how many postings are written, and the on-disk size of a posting list grows with the number of postings (linearly, with only a small per-block overhead change) rather than saturating at a limit. A reading that shows usage saturating at, or being bounded by, a value derived from `BLOCK_SIZE` would refute the claim.

### B2. Unit tier

> **Amended 2026-10-28 (stage-4 audit): see B5, which overrides this section where they conflict.**

**B2a. Environment and build.** JDK 11, Ant, a local copy of the tag on local disk (never the shared tree): `rsync -a <source>/ $WORK/cassandra-5.0.9/`, `cd $WORK/cassandra-5.0.9 && ant jar`. Write a JUnit test in package `org.apache.cassandra.index.sai.disk.v1.postings` under the copy's `test/unit/...` (needed for the package-private constructor at `:119`). Run with `ant testsome -Dtest.name=<TestClass>`. JVM options: `-Xmx512m`, `-XX:+UseSerialGC` (for stable allocation counting).

**B2b. Knobs.** `blockSize` via the package-private constructor (`:119`): 16, 128 (the real constant), 1024. Also the number of postings per list N: 1,000, 100,000, 1,000,000. Set in test code. Why: 128 is the shipped value; 16 and 1024 show whether any quantity follows the block size.

**B2c. Workload.** One `PostingList` yielding N ascending postings with a fixed stride (for example posting i = i * 3) so the delta bit width is constant; write one list per run, and also M = 1,000 small lists (N = 50) in one writer to exercise per-list reset. Number of blocks = ceil(N / blockSize), for N = 100,000 and blockSize 128 that is 782.

**B2d. Observables and instruments.** (1) Bytes written: `getFilePointer()` (`:136`) before and after `write`, and the file length on disk. (2) Heap retained by the writer: `ThreadMXBean` per-thread allocated bytes (`com.sun.management.ThreadMXBean.getThreadAllocatedBytes`) around the write, plus a heap histogram (`jcmd <pid> GC.class_histogram`) for `long[]` and `LongArrayList` after a forced GC with the writer still referenced. (3) `bufferUpto` cannot be read (private); infer the block count from the skip-table size field in the summary (`:262`). Cannot observe directly: the `DirectWriter` internal buffer.

**B2e. Procedure.**
1. Build as in B2a; confirm the test class compiles against the package-private constructor.
2. For each blockSize in {16, 128, 1024} and each N, create a fresh temp directory on local disk, open the writer, record allocated bytes, call `write(list)`, call `complete()`, record `getFilePointer()` and allocated bytes, close.
3. Force GC and take a class histogram with the writer still reachable; record `long[]` and `LongArrayList` footprint.
4. Repeat the M-small-lists case once per blockSize.
5. Positive control (see B2h): run the same N with a different stride to raise the delta bit width and show file size moves.
6. Delete the temp directories.

**B2f. Predictions.** (stated before any run)
- `deltaBuffer` size is `8 * blockSize` bytes: about 128 B, 1 KiB, 8 KiB for the three values, independent of N.
- Retained heap after the write does not grow with N beyond the skip-table lists, which grow as ceil(N / blockSize) entries of 8 bytes each (two lists).
- File size grows about linearly in N for every blockSize; at fixed N the three file sizes differ only by a small amount (per-block header bytes and tail padding), under a few percent for N = 1,000,000.
- No run shows file size or heap flattening at a value related to blockSize.

**B2g. Readings.**

| Observation | Meaning |
|---|---|
| File size and heap grow with N for every blockSize; only the 1 KiB-scale buffer and skip-table counts change with blockSize | Claim confirmed: no cap |
| File size or heap stays bounded at some value as N increases, with that value tracking blockSize | Claim refuted: usage follows the constant |
| Usage flat in N for all blockSize and the positive control (stride change) also does not move file size | Not confirmed: workload or instrument failed |
| N never exceeds blockSize in some runs (N = 1,000 with blockSize 1024) | Those runs are uninformative; use the larger N |

**B2h. Controls.** Positive control: the same workload with a larger stride (for example 3 versus 1,000,003) raises `maxDelta`, hence bits per value (`:275`), and must raise file size per posting. Second control: N below blockSize writes exactly one tail block (`:230-237`), confirming the block-count arithmetic. Repeat each run twice to rule out JIT or GC noise in allocation counts.

### B3. Cluster tier

> **Amended 2026-10-28 (stage-4 audit): see B5, which overrides this section where they conflict.**

**B3a. Environment and build.** One node, JDK 11, built from a local copy (`ant jar`), data, commit log and hints directories on local disk of known size (at least 20 GiB free, set explicitly in `cassandra.yaml`). Heap `-Xms2G -Xmx2G`. SAI must be enabled for the table (default for 5.0 SAI index creation; not verified beyond the code read). Because `BLOCK_SIZE` cannot be configured, a second build with the constant edited to 32 and then 512 in the local copy (`PostingsWriter.java:89`) is the only way to vary it; build each into its own directory.

**B3b. Knobs.** The constant value in the source copy: 32, 128 (stock), 512, one build each. Held fixed: `segment_write_buffer_size` (default; line 35 of `StorageAttachedIndexOptions.java`). Positive control knob: `segment_write_buffer_size` set to a small value (for example 16MiB) versus default, which does bound memory used in the SAI segment build (the cap's binding is not verified here; the control's job is to show it moves). Set in `cassandra.yaml`.

**B3c. Workload.** Table with a text column carrying an SAI `StorageAttachedIndex` and a numeric column with another; insert 5,000,000 rows via `cassandra-stress` (or CQL batches) where the text column has few distinct values (about 100, giving about 50,000 postings per term, so about 390 blocks per term at 128) and the numeric column has many; flush (`nodetool flush`) so the SAI components are written; then run `nodetool compact` once to exercise the merge path (`BlockBalancedTreePostingsWriter.java:135`). Duration: until flush and compaction finish.

**B3d. Observables and instruments.** Total size of the SAI component files on disk (`du -sb` on the table's directory, per component file name pattern; names not verified, list the directory instead); JVM heap use during flush/compaction by `jstat -gc <pid> 1000` and `jcmd <pid> GC.heap_info`; peak RSS from `/proc/<pid>/status` (VmHWM). Cannot observe: the writer's own array in isolation inside a running node.

**B3e. Procedure.**
1. Build three copies (constant 32, 128, 512), each `ant jar`.
2. For each build: start a fresh node with empty local data directories, create keyspace/table/indexes, start `jstat` sampling, run the workload, flush, record SAI file sizes, compact, record sizes and peak heap/RSS.
3. Stop the node, confirm no Java process remains (`pgrep -f CassandraDaemon`), delete data directories.
4. Positive control: on the 128 build, repeat with `segment_write_buffer_size: 16MiB`.

**B3f. Predictions.** (before any run)
- Total SAI posting-file size differs by under a few percent across 32, 128, 512 for the same data; it scales with the row count, not with the constant.
- Peak heap during flush/compaction shows no systematic change across the three builds (differences within run-to-run noise).
- The positive control (smaller `segment_write_buffer_size`) changes the number of segments or peak heap visibly.

**B3g. Readings.**

| Observation | Meaning |
|---|---|
| Disk and heap unchanged (within noise) across 32/128/512 while the positive control moves | Claim confirmed |
| Disk or peak heap changes strongly and monotonically with the constant | Claim refuted: usage follows the constant |
| Neither the constant nor the positive control moves anything | Not confirmed: workload too small, SAI files not produced, or instrument failed |
| Disk grows only with row count | Consistent with the claim |

**B3h. Controls.** Same data, same seed and same yaml across builds; empty data directory per run; the stock build run twice to measure noise; the positive control above; confirm the SAI component files were created (directory listing) so the writer was exercised.

**B4. Risks and cleanup.** Unit tier: temp files only, in a local temp directory removed at the end of the test. Cluster tier: about 5 million rows plus SAI components could use several GiB; keep all directories on local disk of known size and never on shared storage; three builds each need their own directory. After each run stop the node and check with `pgrep -f CassandraDaemon` and `pgrep -f cassandra-stress`; remove data, commit log, hints and the source copies. Never build in or write into the shared source tree.

### B5. Stage-4 audit amendments (2026-10-28)

Made before any reading; they override the text of the sections named where they conflict. None depends on a reading.

1. **B2a (run form).** Plain `java -cp` against `build/classes/main` and `build/test/classes` of a `copy-source.sh` copy, probe class in package `org.apache.cassandra.index.sai.disk.v1.postings` (for the package-private constructor at `:119`; the postings come from the existing test class `ArrayPostingList`), `-Xmx512m -XX:+UseSerialGC`.
2. **B2f (file-size prediction, arithmetic).** "Under a few percent for N = 1,000,000" is wrong for blockSize 16: with stride 3 the deltas need 2 bits, a block of 16 is 4 B of packed data plus 1 B of bits-per-value, against 32 B + 1 B at 128 and 256 B + 1 B at 1024, so the per-block overhead alone is about 20 % at blockSize 16 (and 1 to 3 % between 128 and 1024), plus the skip table (two `LongArrayList`s of ceil(N/blockSize) entries). The prediction is replaced by a model: size(N, bs) = header + ceil(N/bs) x (1 + ceil(bs x bits / 8)) + skip table (measured from the summary), and a reading follows the model if it is within 2 % of it. Refuted only if size saturates or flattens in N, or exceeds the model by more than 2 % in a way that grows with N.
3. **B2c.** N = 1,000 with blockSize 1024 is a single tail block (already marked uninformative in B2g); the sweep N is 1,000, 100,000, 1,000,000 for all three sizes and the M = 1,000 small-list case is run once per size.
4. **B3a/B3c/B3e (workload size and load path).** 5M rows is replaced by **3,000,000 rows** of the shared seed table (`pk` int = i/100, `ck` int = i%100, `v` int random below 10^6, `txt` text `'w'+(i%100)` = 100 distinct terms, so 30,000 postings per term = 234 blocks of 128; `v_idx` goes through `BlockBalancedTreePostingsWriter.java:135`, `txt_idx` through `LiteralIndexWriter.java:60`). **Load path (cluster tier, replaces the flush-and-compact load).** The rows are loaded once per row count into an *unindexed* table with the bundled python driver and left as one flushed, compacted SSTable (a seed data directory on local disk); every arm restores a copy of the seed, starts a node on its build, runs `CREATE INDEX ... USING 'sai'` (the initial index build) and then `nodetool rebuild_index` (a repeat). The index build and the memtable flush both write the per-SSTable and per-index components through `StorageAttachedIndexWriter` (`SSTableComponentsWriter` is created at `StorageAttachedIndexWriter.java:95` via `V1OnDiskFormat.java:162-164`), so the traced writers run on this path; a Byteman ledger (one line per writer construction, with the array length) is added as an instrument and proves it in every arm. Reason: it removes the memtable and commit log from the comparison and makes the arms differ only in the build and the yaml. Builds 32 / 128 / 512 (one directory each, `javap -constants` confirms), heap `-Xms2G -Xmx2G`. One stock arm at 750,000 rows shows disk growing with rows.
5. **B3b/B3h (control).** **Positive control, defined (all SAI cluster tiers).** The control is the stock build at the largest row count with `sai_options.segment_write_buffer_size: 16MiB` against the default 1024MiB. It *moves* iff (i) the peak of the JMX gauge `SegmentBufferSpaceUsedBytes` in the 16MiB arm is <= 20 MiB, (ii) the default arm's peak is > 32 MiB (the limit was reached), and (iii) the 16MiB arm's `debug.log` has the `Global limit of ... exceeded` memory-limit flush lines that the default arm lacks. Peak heap (500 ms JMX samples) and RSS are reported for every arm but are not decisive: a heap peak between garbage collections is noisy.
6. **B3f (tolerance).** "Under a few percent" for the posting-file size across 32 / 128 / 512 is fixed at **5 %** of the stock figure for the sum of the `Postings` components; the Byteman ledger must show `deltaBuffer` lengths 32 / 128 / 512 and peak heap is reported with the same noise allowance as the other SAI cases (2 % of the heap beyond the ledger difference).
7. **B3g (added row).** An arm whose queries fail (`SELECT count(*)` on both indexed columns different from the seed row count) is *Not confirmed*.
8. **Post-freeze correction of control (iii) (2026-10-28, made after the first cluster arm (stock, 3M rows) had been seen; claim, predictions and rows unchanged, and not made from any reading of the tested quantity across builds).** Item 5's condition (iii) assumed the default 1024 MiB arm never reaches its segment-buffer limit. The first arm showed the opposite: at 3,000,000 rows the default arm's gauge peaked at 1,073,743,912 B (the limit, 1,073,741,824 B) with 8 memory-limit flush lines in `debug.log`. Condition (iii) is therefore read as: the 16 MiB arm has **more** `Global limit of ... exceeded` lines than the default arm. Conditions (i) and (ii) stand as written ((ii) is met by that reading). Run 1 was not restarted: the procedure and the raw data are unchanged, only this evaluation criterion is (recorded as a runbook defect in the results file).

## C. Sources read

- `/users/jason92/cassandra-5.0.9/src/java/org/apache/cassandra/index/sai/disk/v1/postings/PostingsWriter.java`
- `/users/jason92/cassandra-5.0.9/src/java/org/apache/cassandra/index/sai/disk/v1/postings/PostingsReader.java` (grep lines 88-298 only)
- `/users/jason92/cassandra-5.0.9/src/java/org/apache/cassandra/config/StorageAttachedIndexOptions.java` (grep lines 32-41 only)
- grep for `new PostingsWriter` across `/users/jason92/cassandra-5.0.9/src`

## D. Stage-4 feedback

**2026-10-28 (stage 4, node `pc39`; results: `stage4-runtime-verification/results/block_size-writeposting-blocksize--autonomous.md`).** Unit tier **Confirmed**, effect **does not cap**; cluster tier **Not confirmed (no matching row)** on the frozen 5 % bound, effect **does not cap**; outcome class **true negative** (estimate `negative`).

- Unit: the on-disk bytes of a list follow the per-block model to the byte (`1 + blocks x (1 + ceil(bs x 2 / 8))` at stride 3), grow 10.0 x for 10 x the postings at bs 16, 128 and 1024, and are 656 / 301 / 257 KB (file) for 1M postings; `deltaBuffer` is 8 bs + 16; the retained arrays beyond it are the two skip-table lists (1.14 MB at bs 16, N = 1M); a wide stride (20 bits) raised the bytes 9.8 to 10.0 x (control).
- Cluster (3M rows, seed + `CREATE INDEX` + `rebuild_index`): ledger `deltaBuffer` 32 / 128 / 512 per arm; posting files 11.61 / 10.76 / 11.04 MB (+7.9 % and +2.7 %: U-shaped, per-block overhead at 32, tail padding at 512), total SAI bytes 49.99 / 49.13 / 49.42 MB (+1.7 %, +0.6 %); heap peaks 1,892 / 1,918 / 1,915 MiB; 4.23 x posting bytes for 4 x rows; control `segment_write_buffer_size` 16 MiB: gauge 16.0 MiB against 1,024 MiB, 848 against 8 limit flushes, heap peak 1,280 against 1,918 MiB, `v_idx` posting file 3.2 against 7.6 MB.
- Amendments at the audit (B5.1 to B5.7, 2026-10-28): run form, the file-size model replacing "under a few percent" (which was wrong at bs 16 by arithmetic), 3M rows, seed load path, the control definition, the 5 % tolerance; B5.8 (post-freeze, before the first arm of this case) on control condition (iii).
- Findings for stage 3: (1) the prediction "differs by under a few percent" is right in size but not in shape: the posting bytes are U-shaped in the block size, and 5 % was narrowly missed (+7.9 % at 32); a claim of "no cap, a few percent of layout overhead" would have been met. (2) In `PostingsWriter.writePostingsBlock` every list's last block is padded to a full block, so small lists (the `v_idx` lists) pay up to `blockSize x bits / 8` bytes each: the constant matters most for many small lists. (3) The default segment buffer is reached at 3M rows, so `segment_write_buffer_size` is a working positive control for all SAI cases.
