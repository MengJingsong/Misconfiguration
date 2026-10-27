# block_packed_max_block_size-checkblocksize-blocksize — verification solution  <!-- file: cases/block_packed_max_block_size-checkblocksize-blocksize--autonomous.md -->

| Field | Value |
|---|---|
| Entry pointer | [`SAICodecUtils.java:129`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/index/sai/disk/v1/SAICodecUtils.java#L129) |
| Pinned source | `cassandra-5.0.9` |
| Session / date | Claude Code CLI (Agent-tool subagent), 2026-10-27 |
| Estimate | `negative`: the bound is a hard-coded format-sanity check on a block size that the code only ever sets to 128 or 16384, so it does not bound any memory- or disk-significant quantity in practice; total SAI heap/disk scales with row count, not with this limit. |
| Ground | `MAX_BLOCK_SIZE` (2^27 values) is far above every block size the writers use (`NumericValuesWriter.java:34-35`), is not configurable, and each writer's buffer is one fixed `long[blockSize]`. The check's real job on the read path is rejecting a corrupt `blockSize` read from file before `numBlocks`-sized arrays are allocated. Heap and disk of the numeric-values components grow with the number of rows (`rows / blockSize` entries in reader arrays), which this constant does not limit. |

> **Link rule.** Declaration (A1) and if statement (Entry pointer, A3) are permalinks at tag `cassandra-5.0.9`. All other citations are plain `file:line` under `src/java/org/apache/cassandra/index/sai/disk/v1/` unless a full path is given.

## A. Constraint trace

**A1. The constraint.** `AbstractBlockPackedWriter.MAX_BLOCK_SIZE`, with lower bound `MIN_BLOCK_SIZE`. Kind: hard-coded `static final int` constants (not a yaml entry, not a `-D` property, not runtime-queried). Declared at [`AbstractBlockPackedWriter.java:35`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/index/sai/disk/v1/bitpack/AbstractBlockPackedWriter.java#L35) (`MAX_BLOCK_SIZE = 1 << (30 - 3)`); `MIN_BLOCK_SIZE = 64` is at `bitpack/AbstractBlockPackedWriter.java:34`. Both are package-private. Unit: number of `long` values per block. Default: the literals, 64 and 134,217,728 (2^27); the shift `30 - 3` is, by its form, a "2^30 bytes divided by 8 bytes per long" bound (the derivation is inferred from the expression, no comment in the source states it; not verified). Setting: not settable by yaml, `-D` or JMX (a grep of `src/java` for the two names finds only the uses listed below); changing needs a code change and rebuild. The target is the generic helper `SAICodecUtils.checkBlockSize(int blockSize, int minBlockSize, int maxBlockSize)` declared at `SAICodecUtils.java:127`, described in the source as copied from Lucene `PackedInts` (`SAICodecUtils.java:125`).

**A2. What it caps.** Nominally: the size of the in-memory block buffer of the block-packed writers, `new long[blockSize]` (`bitpack/AbstractBlockPackedWriter.java:52`), i.e. at most 8 x 2^27 = 1 GiB of heap per writer instance by arithmetic, plus the `ByteBuffersDataOutput` sized by the same value (`bitpack/AbstractBlockPackedWriter.java:51`, `ResettableByteBuffersIndexOutput.java:45-47`). The quantity compared is the `int blockSize` argument. On the read side the compared value is `meta.blockSize`, read from the file (`bitpack/NumericValuesMeta.java:34`), so it also guards the `numBlocks`-sized arrays allocated next (`bitpack/BlockPackedReader.java:57-60`, `bitpack/MonotonicBlockPackedReader.java:55-59`). The resource is heap (writer buffer; reader arrays). Disk is not capped.

**A3. Mechanism.** Step by step:
1. Writer: `AbstractBlockPackedWriter(IndexOutput, int)` calls `checkBlockSize(blockSize, MIN_BLOCK_SIZE, MAX_BLOCK_SIZE)` at `bitpack/AbstractBlockPackedWriter.java:49`, before allocating at lines 51-52.
2. Callers pick the size: `NumericValuesWriter` uses `MONOTONIC_BLOCK_SIZE = 16384` or `BLOCK_SIZE = 128` (`bitpack/NumericValuesWriter.java:34-35`, selected at line 49). The only other path is the public 5-argument constructor (`bitpack/NumericValuesWriter.java:52-58`); in `src/java` it is not called with a custom size (the five production uses are `SSTableComponentsWriter.java:58,59,60,62,72`, all 4-argument); tests call it with `1 << nextInt(8, 15)` (`test/unit/org/apache/cassandra/index/sai/disk/v1/bitpack/NumericValuesTest.java:104,109`).
3. The chosen size is persisted in the metadata (`bitpack/NumericValuesWriter.java:75`, `NumericValuesMeta.write` at `bitpack/NumericValuesMeta.java:38-43`).
4. Readers: `BlockPackedReader` (`bitpack/BlockPackedReader.java:55`) and `MonotonicBlockPackedReader` (`bitpack/MonotonicBlockPackedReader.java:53`) call `checkBlockSize(meta.blockSize, ...)` on the value read back from the file, then compute `numBlocks` (`SAICodecUtils.java:146-160`) and allocate arrays of that length.
5. The check itself: the if statement is [`SAICodecUtils.java:129`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/index/sai/disk/v1/SAICodecUtils.java#L129), `if (blockSize >= minBlockSize && blockSize <= maxBlockSize)`.
   - True: a nested check at `SAICodecUtils.java:131` throws `IllegalArgumentException` (line 133) if `blockSize` is not a power of two; otherwise returns `Integer.numberOfTrailingZeros(blockSize)` (line 137), used as `blockShift`.
   - False: throws `IllegalArgumentException("blockSize must be >= ... and <= ...")` (line 142). On the write path this aborts index/component construction before the buffer is allocated; on the read path it fails the open of the component (how the failure surfaces to the caller, for example whether the index is marked non-queryable, is not verified).

Bypass/overshoot: none for the buffer (check precedes allocation). Both writer buffers exist for the whole life of an `NumericValuesWriter`; there are five per-SSTable writers when the table has clustering columns (`SSTableComponentsWriter.java:58-62,72`), each with its own buffer, so total writer buffer is the sum, and is not bounded by `MAX_BLOCK_SIZE` as a whole. The reader arrays scale with `valueCount / blockSize`, not bounded by this constant.

**A4. Other consumers.** Everything else SAI holds: the per-index in-memory trie/term buffers governed by the SAI segment write buffer (`conf/cassandra.yaml:1790-1794` shows the commented `sai_options` / `segment_write_buffer_size` entry; the enforcing code is not verified here), the chunk cache, the memtable index, the primary-key lookup structures (`KeyLookup`, `SkinnyPrimaryKeyMap.java:86-90`), and general JVM heap. Disk: the numeric-values component files grow with row count.

**A5. Evidence beyond the source.** Unit test of the helper: `test/unit/org/apache/cassandra/index/sai/disk/v1/SAICodecUtilsTest.java:356-371` (checks rejection of out-of-range and non-power-of-two sizes, and returned shift). Lucene `PackedInts.checkBlockSize` is the origin per the source comment (`SAICodecUtils.java:125`); upstream docs not consulted. No issue numbers cited.

## B. Verification solution

**B1. Claim under test.** Usage does not follow this constraint: raising or lowering the value of `MAX_BLOCK_SIZE` (or the accepted block size) within the range actually used does not change heap or disk used by SAI numeric-values components, which instead track row count and the fixed block sizes 128 / 16384; the constraint only rejects out-of-range sizes, and the 2^27 bound is never approached by a running node. Refuted if the node's heap or disk for these components moves with the bound, or if a production path ever allocates near `MAX_BLOCK_SIZE`.

### B2. Unit tier

**B2a. Environment and build.** JDK 11, Ant. Copy the tree to local disk (`rsync -a /users/jason92/cassandra-5.0.9/ $WORK/cassandra-5.0.9/`, never build in the shared tree), `ant jar` there, and add one JUnit test class in `$WORK/cassandra-5.0.9/test/unit/org/apache/cassandra/index/sai/disk/v1/bitpack/BlockSizeBoundProbeTest.java` (same package as the writers so the package-private constants are visible; otherwise read them reflectively). Run with `ant testsome -Dtest.name=BlockSizeBoundProbeTest`, with test JVM options `-Xmx3g -Xms3g` set through `test.jvm.args` or `ant -Dtest.jvm.args=...` (the exact property name for this tree is not verified; check `build.xml`). A `-XX:+UseSerialGC` option keeps allocation accounting simple.

**B2b. Knobs.** The `blockSize` argument passed to `new BlockPackedWriter(IndexOutput, int)` / `new MonotonicBlockPackedWriter(...)` (public constructors, `bitpack/BlockPackedWriter.java:38`, `bitpack/MonotonicBlockPackedWriter.java:38`). Values: 32 and 96 (below min / not power of two), 64 (min), 128 and 16384 (production values), 2^20, 2^26, 2^27 (max), 2^28 (above max). Chosen to straddle each branch of the check and to cover the sizes in use. Set by passing the argument in the probe.

**B2c. Workload.** Construct a writer for each size against a throwaway in-memory `IndexOutput` (for example `ByteBuffersIndexOutput` over a `ByteBuffersDataOutput`), then `add(long)` N = 3 x blockSize values capped at 2^22 for the large sizes (so at least one flush happens only when blockSize <= 2^21; for larger sizes only the construction is measured), then `finish()`. Arithmetic: `blockValues` = 8 x blockSize bytes (128 -> 1 KiB, 16384 -> 128 KiB, 2^27 -> 1 GiB); the 3 GiB heap holds the 2^27 case. Also for the read side: write a small component pair (128 and 16384 block sizes, 1,000,000 values) and a hand-built `NumericValuesMeta` with `blockSize` forged to 2^28 and to 99 to exercise the reader check (the forged `DataInput` is built with `ByteBuffersDataInput`).

**B2d. Observables and instruments.** Per construction: bytes allocated by the thread, from `((com.sun.management.ThreadMXBean) ManagementFactory.getThreadMXBean()).getThreadAllocatedBytes(Thread.currentThread().getId())` before and after; also `Runtime.totalMemory() - freeMemory()` after `System.gc()` as a cross-check; exception type and message from `checkBlockSize`; returned shift. Not observable: the node's real heap (that is the cluster tier).

**B2e. Procedure.**
1. Build as in B2a.
2. For each size in B2b: record allocated bytes, call the constructor, record allocated bytes again, catch `IllegalArgumentException`, log size, delta, outcome.
3. For accepted sizes, do the B2c writes and record allocation to `finish()`.
4. Read-side: construct `BlockPackedReader` and `MonotonicBlockPackedReader` with the real metadata and with the forged ones; record outcome and allocation.
5. Repeat each measurement 3 times in fresh JVM invocations to exclude warm-up noise.
6. Stop the JVM; check `jps` shows no leftover process.

**B2f. Predictions (before any run).**
- 32, 96, 2^28: `IllegalArgumentException` at the constructor, delta approximately zero allocation for the `long[]` (the check precedes it). 96 gives the power-of-two message; 32 and 2^28 give the range message (`SAICodecUtils.java:133,142`).
- 64, 128, 16384, 2^20, 2^26, 2^27: accepted; allocation delta at least 8 x blockSize bytes (so about 1 KiB, 128 KiB, ..., 1 GiB) and linear in blockSize; returned shifts 6, 7, 14, 20, 26, 27.
- Reader with forged 2^28 or 99: exception before any `numBlocks`-sized array is allocated.
- Claim (negative): at the production sizes the allocation is the same whether `MAX_BLOCK_SIZE` is 2^27 or any larger value; confirm by also running a patched copy with `MAX_BLOCK_SIZE = 1 << 28` (separate build directory) and observing identical deltas for 128 and 16384.

**B2g. Readings.**

| Observation | Meaning |
|---|---|
| Allocation at 128 / 16384 identical in stock and patched-bound builds, linear in blockSize for accepted sizes | Claim confirmed: usage depends on the block size actually used, not on the bound |
| Allocation at 128 / 16384 differs between stock and patched-bound builds | Claim refuted: usage follows the bound |
| 2^27 accepted and about 1 GiB allocated; 2^28 rejected with no large allocation (positive control: the cap binds on what is accepted) | The check works as traced; it caps only values nobody passes |
| 2^27 not accepted, or 2^28 accepted | Trace of the check is wrong; revise A3 |
| Allocation not linear or the large cases OOM because of heap size | Not confirmed; raise `-Xmx` and rerun |
| Forged reader size allocates `numBlocks` arrays before failing | Check ordering differs from A3 |

**B2h. Controls.** Positive control: the 2^27 / 2^28 pair, where the bound is shown to bind. Baseline: sizes 128 and 16384 with the stock bound. The patched-bound build isolates the constant from other effects. Fresh JVMs and `System.gc()` before each sample rule out leftover garbage.

### B3. Cluster tier

**B3a. Environment and build.** One node (a second optional) on local disk of known size (at least 20 GiB free). JDK 11. Copy the tree to local disk, `ant jar`, run from `$WORK/cassandra-5.0.9/bin/cassandra -f` with `-Xms2g -Xmx2g`, `data_file_directories`, `commitlog_directory`, `hints_directory`, `saved_caches_directory` pointed under `$WORK/data`, `listen_address`/`rpc_address` on loopback or the node's local address. Two builds: stock, and a copy with `MAX_BLOCK_SIZE` changed to `1 << 20` (still above 16384, so all production sizes remain valid) and a second copy with `MAX_BLOCK_SIZE = 1 << 14` (rejects nothing used by monotonic writers? 16384 = 2^14 is exactly the monotonic size and is allowed because the check is `<=`; so also try `1 << 13`, expected to make the monotonic writer fail at flush time of the first SSTable index build).

**B3b. Knobs.** The compiled constant (three builds: `1 << 27` stock, `1 << 20`, `1 << 13`); row count of the table (1M, 4M, 16M rows) as the control variable that should move usage. Not settable at runtime. Block sizes 128/16384 are fixed by code.

**B3c. Workload.** Table `ks.t (pk int, ck int, v int, primary key (pk, ck))` with `CREATE CUSTOM INDEX ON ks.t (v) USING 'StorageAttachedIndex'`; write with `cassandra-stress` (`user profile` or `write n=<rows>`) or a short CQL driver loop; rows per partition 100, so the table has clustering and all five numeric-values components are written (`SSTableComponentsWriter.java:58-72`). Flush with `nodetool flush ks t` after each batch of rows so each SSTable index build runs the writers. Arithmetic: 1M rows at 128 values per block gives about 7,813 blocks for `ROW_TO_TOKEN`, and 16384-sized blocks give about 62 for `ROW_TO_PARTITION`; reader arrays are therefore a few tens of KiB per SSTable and scale linearly with rows, nowhere near 1 GiB. Duration: about 10 minutes per build and size.

**B3d. Observables and instruments.** Heap: `jcmd <pid> GC.class_histogram` (count of `long[]`, `byte[]` instances and bytes) and `jcmd <pid> GC.heap_info` after `nodetool` forced GC (`jcmd <pid> GC.run`); JMX `java.lang:type=Memory` HeapMemoryUsage sampled each second via `jconsole`/`jmxterm`. Disk: `du -sb` of the SSTable directory and `ls -l` of the `*SAI*RowToToken*`, `*RowToPartition*`, `*PartitionToSize*`, `*PartitionKeyBlockOffsets*` component files (exact component file names depend on the on-disk naming and are not verified). Logs: `grep -i "blockSize must be" logs/system.log`. Not directly observable: the writer buffer's instantaneous size (short-lived); infer from the histogram taken during the flush.

**B3e. Procedure.**
1. Build and start the stock node; confirm up with `nodetool status`.
2. Create keyspace/table/index; insert 1M rows; `nodetool flush`; take histogram and heap info after `jcmd <pid> GC.run`; record SAI component sizes.
3. Repeat for 4M and 16M rows (new SSTables, no compaction: `nodetool disableautocompaction ks t`).
4. Stop the node; start the `1 << 20` build on a fresh data directory, repeat step 2 and compare.
5. Start the `1 << 13` build on a fresh data directory; insert 1M rows; flush; read `system.log` for the exception and whether the index build fails and how the table behaves (not verified, to be recorded).
6. Positive control (bounded memory known to bind): rerun step 2 with `memtable_heap_space` set to a small value (for example 64MiB, `conf/cassandra.yaml`), same workload, and observe memtable flush frequency increasing and memtable-held bytes bounded; shows a real cap moves usage under this workload.
7. Stop all nodes (`nodetool drain` then kill), `jps` to confirm nothing remains, delete `$WORK/data`.

**B3f. Predictions (before any run).**
- Stock vs `1 << 20`: SAI numeric-component file sizes and heap histogram counts for these structures identical within sampling noise at equal row counts.
- Within a build: component file sizes and reader-array bytes grow approximately linearly with rows (4M about 4x of 1M, 16M about 16x), regardless of the bound.
- No `long[]` instance anywhere near 8 x 2^27 bytes in the histogram on the stock build; the largest SAI-related `long[]` from these writers about 128 KiB (16384 x 8) plus unrelated JVM arrays.
- `1 << 13` build: the first index build that constructs a `MonotonicBlockPackedWriter` (16384 > 8192) throws `IllegalArgumentException`; the other writers (128) still construct.
- Claim wrong if usage differs between stock and `1 << 20` builds.

**B3g. Readings.**

| Observation | Meaning |
|---|---|
| Stock and `1 << 20` give the same component sizes / histogram; both scale with rows | Claim confirmed: usage does not follow the constraint |
| Sizes or heap differ between stock and `1 << 20` at equal rows | Claim refuted: usage follows the bound |
| Usage flat across builds while the positive control (`memtable_heap_space`) visibly changes flush behaviour/heap | Confirmed with a working control |
| Positive control shows no change, or the index builds never run (no SAI components written) | Not confirmed: workload did not reach the writers or the control is not binding; fix the workload |
| `1 << 13` build throws as predicted | The check does reject values above the bound at the write path; informs A3 |
| `1 << 13` build does not throw | A3 step 1 or the block-size selection is wrong |

**B3h. Controls.** Positive control: `memtable_heap_space` (item 6). Baseline: stock build at three row counts. Fresh data directory per build; no compaction; forced GC before each heap sample; same JVM options for all builds so differences cannot come from heap settings.

**B4. Risks and cleanup.** Unit tier: the 2^27 case needs a 1 GiB heap array plus overhead, so a 3 GiB heap; the 2^28 case would need 2 GiB if the check were wrong. Build only in a copy under local disk; no shared files written. Cluster tier: 16M rows with five components stays well under 20 GiB on local disk (not verified numerically; check `df` first and stop if data exceeds 10 GiB); commit log and hints on local disk; drop the table or delete `$WORK/data` afterwards; stop the node and confirm with `jps` and `pgrep -f CassandraDaemon` that none remains; delete the build copies when done.

## C. Sources read

- /tmp/claude-20001/-proj-misconfiguration-PG0-git-repos-Misconfiguration/d3cfd622-d93d-5998-b33d-926864ab48d4/scratchpad/agent-docs/INSTRUCTIONS.md
- /tmp/claude-20001/-proj-misconfiguration-PG0-git-repos-Misconfiguration/d3cfd622-d93d-5998-b33d-926864ab48d4/scratchpad/agent-docs/playbook-autonomous.md
- /tmp/claude-20001/-proj-misconfiguration-PG0-git-repos-Misconfiguration/d3cfd622-d93d-5998-b33d-926864ab48d4/scratchpad/agent-docs/_TEMPLATE-autonomous.md
- /tmp/claude-20001/-proj-misconfiguration-PG0-git-repos-Misconfiguration/d3cfd622-d93d-5998-b33d-926864ab48d4/scratchpad/agent-in/147.md
- /users/jason92/cassandra-5.0.9/src/java/org/apache/cassandra/index/sai/disk/v1/SAICodecUtils.java
- /users/jason92/cassandra-5.0.9/src/java/org/apache/cassandra/index/sai/disk/v1/bitpack/AbstractBlockPackedWriter.java
- /users/jason92/cassandra-5.0.9/src/java/org/apache/cassandra/index/sai/disk/v1/bitpack/BlockPackedReader.java
- /users/jason92/cassandra-5.0.9/src/java/org/apache/cassandra/index/sai/disk/v1/bitpack/MonotonicBlockPackedReader.java
- /users/jason92/cassandra-5.0.9/src/java/org/apache/cassandra/index/sai/disk/v1/bitpack/NumericValuesWriter.java
- /users/jason92/cassandra-5.0.9/src/java/org/apache/cassandra/index/sai/disk/v1/bitpack/NumericValuesMeta.java
- /users/jason92/cassandra-5.0.9/src/java/org/apache/cassandra/index/sai/disk/v1/SSTableComponentsWriter.java
- /users/jason92/cassandra-5.0.9/src/java/org/apache/cassandra/index/sai/disk/v1/SkinnyPrimaryKeyMap.java (grep excerpt)
- /users/jason92/cassandra-5.0.9/src/java/org/apache/cassandra/index/sai/disk/ResettableByteBuffersIndexOutput.java
- /users/jason92/cassandra-5.0.9/test/unit/org/apache/cassandra/index/sai/disk/v1/SAICodecUtilsTest.java
- /users/jason92/cassandra-5.0.9/test/unit/org/apache/cassandra/index/sai/disk/v1/bitpack/NumericValuesTest.java
- /users/jason92/cassandra-5.0.9/conf/cassandra.yaml (grep excerpt)

## D. Stage-4 feedback

`none yet`
