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

## C. Sources read

- `/users/jason92/cassandra-5.0.9/src/java/org/apache/cassandra/index/sai/disk/v1/postings/PostingsWriter.java`
- `/users/jason92/cassandra-5.0.9/src/java/org/apache/cassandra/index/sai/disk/v1/postings/PostingsReader.java` (grep lines 88-298 only)
- `/users/jason92/cassandra-5.0.9/src/java/org/apache/cassandra/config/StorageAttachedIndexOptions.java` (grep lines 32-41 only)
- grep for `new PostingsWriter` across `/users/jason92/cassandra-5.0.9/src`

## D. Stage-4 feedback

`none yet`
