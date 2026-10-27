# LAST_VALID_SEGMENT_ROW_ID — verification solution  <!-- file: cases/last_valid_segment_row_id-exceedssegmentlimit-sstablerowid--autonomous.md -->

| Field | Value |
|---|---|
| Entry pointer | [`SegmentBuilder.java:260`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/index/sai/disk/v1/segment/SegmentBuilder.java#L260) (the empty-builder test `getRowCount() == 0` in `exceedsSegmentLimit`); the comparison that enforces the constant is [`SegmentBuilder.java:266`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/index/sai/disk/v1/segment/SegmentBuilder.java#L266) |
| Pinned source | `cassandra-5.0.9` |
| Session / date | Claude Code CLI (Agent-tool subagent), 2026-10-27 |
| Estimate | `negative`: the constant caps a segment's row-id span (about 1.07 billion ids), not bytes; the heap the segment builder holds is governed by the separate byte limiter (`segment_write_buffer_size`), which binds long before the row-id cap at default settings. |
| Ground | The compared quantity is a row-id difference (`ssTableRowId - segmentRowIdOffset`), a count, and the constant is a fixed compile-time value with no unit conversion to bytes. At the default value a builder holding that many entries would need far more heap than the default 1024 MiB byte limit, so the byte limit triggers a flush first (reasoning from the source, not measured). The constant is a correctness guard for the 2B-entry on-disk structure, not a memory or disk cap. Note: if the test hook sets the cap very low, segments do become small, so the row cap can bound memory only when set far below its default; that is what the positive-direction control exercises. |

> **Link rule.** Followed: declaration and if statements are permalinks at tag `cassandra-5.0.9`.

## A. Constraint trace

**A1. The constraint.** `SegmentBuilder.LAST_VALID_SEGMENT_ROW_ID`. Kind: constant (`public static final long`). Declared at [`SegmentBuilder.java:46`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/index/sai/disk/v1/segment/SegmentBuilder.java#L46); the comment on line 45 reads "Served as safe net in case memory limit is not triggered or when merger merges small segments..". Unit: segment-relative SSTable row ids (a count of row positions). Default: `(Integer.MAX_VALUE / 2) - 1L` (line 46) = 1073741822, derived from `Integer.MAX_VALUE`. Each builder copies it into the instance field `lastValidSegmentRowID` (declared line 55) in the constructor at line 147, unless the static `testLastValidSegmentRowId` (line 47, initial -1) is >= 0. Settable: not via yaml, `-D` or JMX (no such path in this file; the only other source reference is the check at SSTableIndexWriter, which reads nothing configurable, grep over `src/` for the name found only SegmentBuilder.java). Only the `@VisibleForTesting` static `updateLastValidSegmentRowId` (lines 269-273) overrides it, and it is a static that affects builders created after the call. Changing the real default requires editing the source and rebuilding. The earlier trace's A1 held on every point I re-checked (lines 45, 46, 47, 55, 147, 269-273); its statement that the memory limit's source was untraced is resolved in A2/A3 below.

**A2. What it caps.** Not a byte quantity. The code compares `ssTableRowId - segmentRowIdOffset` (row-id span from the first row in the current segment, `segmentRowIdOffset` set at line 186 when `rowCount == 0`, field at line 61) to `lastValidSegmentRowID` (line 266). So it caps how wide (in SSTable row-id positions) one index segment can be. The comment at lines 263-265 gives the reason: the on-disk index structure has a 2B limitation, and `castToSegmentRowId` uses `Math.toIntExact` (lines 201-204) which would throw past int range. Memory and disk are only indirectly affected: a segment spanning N row ids holds at most N indexed entries, so the cap is an upper bound on entries per segment, with bytes per entry unconstrained by it. Note that non-indexed rows still advance the row-id span, so a segment can contain far fewer entries than the cap.

**A3. Mechanism.**
1. `SSTableIndexWriter.addRow` (line 78) calls `addTerm` (line 205) for each indexed value.
2. In `addTerm`: if `currentBuilder == null`, create one (lines 210-213); else call `shouldFlush(sstableRowId)` (line 214).
3. `shouldFlush` (lines 245-262) computes `reachMemoryLimit = limiter.usageExceedsLimit() && currentBuilder.hasReachedMinimumFlushSize()` (line 248) and returns `reachMemoryLimit || currentBuilder.exceedsSegmentLimit(sstableRowId)` (line 261).
4. [`exceedsSegmentLimit`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/index/sai/disk/v1/segment/SegmentBuilder.java#L258) first returns false if the builder is empty (the if statement at [line 260](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/index/sai/disk/v1/segment/SegmentBuilder.java#L260)), so a fresh builder always accepts its first row. Otherwise it returns [`ssTableRowId - segmentRowIdOffset > lastValidSegmentRowID`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/index/sai/disk/v1/segment/SegmentBuilder.java#L266) (line 266).
5. If true: `flushSegment()` (line 216; defined line 264) writes the segment, releases the builder's bytes against the limiter (line 294, `release` at SegmentBuilder.java:230-242), sets `currentBuilder = null`, and a new builder is made (line 217). Note the new row is then added to the new builder, whose offset is that row's id (lines 183-187).
6. If false (and the memory test is false too): the row is added to the current builder (line 225 or 235) and its bytes are counted in the limiter.
The byte limiter: `V1OnDiskFormat.SEGMENT_BUILD_MEMORY_LIMIT` is `DatabaseDescriptor.getSAISegmentWriteBufferSpace().toBytes()` (V1OnDiskFormat.java:126), backed by yaml `sai_options.segment_write_buffer_size` (StorageAttachedIndexOptions.java:35, default 1024 MiB at line 26, maximum 32768 MiB at line 29); it feeds a `NamedMemoryLimiter` (V1OnDiskFormat.java:128; `usageExceedsLimit` at NamedMemoryLimiter.java:53-56). A builder is only eligible once its bytes reach `limitBytes / activeBuilderCount` (SegmentBuilder.java:149, 213).
Bypass/overshoot: (a) the row-id cap is checked only when the next row arrives and only against that row's id, so a segment's last row id can equal the cap exactly (strict `>`, line 266); (b) the check is evaluated before the add, so the memory limit is likewise only exceeded by whatever the current add contributes; (c) the byte limit is global across builders, so a single builder can exceed `limit / activeBuilderCount` while the global total stays under the limit (not verified beyond the source reading); (d) the per-term `addInternal` allocation (e.g. `segmentTrieBuffer.add`, SegmentBuilder.java:90) is not capped by the row-id constant, so a few very large terms can use heap with a tiny row span.


The check itself is the if statement at [`SegmentBuilder.java:266`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/index/sai/disk/v1/segment/SegmentBuilder.java#L266).

**A4. Other consumers.** Other heap or disk use of the same resource outside this constant: the global SAI segment-build byte limiter above (separate cap); memtable and memtable-index memory; the on-disk SAI components written at flush (sizes depend on term size and count, not on this constant); compaction and sstable writer buffers; vector builders (`VectorSegmentBuilder`, lines 109-136) hold an on-heap graph whose size is counted via the returned bytes of `graphIndex.add` (line 128; the accounting accuracy is not verified). Not verified: how `totalBytesAllocated` compares to real heap.

**A5. Evidence beyond the source.** In-tree tests that use the hook: `test/unit/org/apache/cassandra/index/sai/disk/v1/SegmentFlushTest.java` (lines 94, 111, 244-254: flush happens between row ids at `LAST_VALID_SEGMENT_ROW_ID + 1` but not at exactly the constant), `test/unit/org/apache/cassandra/index/sai/cql/VectorSegmentationTest.java:51,97`, `StorageAttachedIndexDDLTest.java:1444`, `VectorLocalTest.java:435,494`, `virtual/SegmentsSystemViewTest.java:128`. No external documentation relied on. No issue numbers cited.

## B. Verification solution

**B1. Claim under test.** At its default value, `LAST_VALID_SEGMENT_ROW_ID` does not govern the heap used by SAI segment building: the heap is governed by `segment_write_buffer_size`, so changing the byte limit moves peak builder bytes and segment count while the row-id cap never triggers a flush on a workload whose row-id span is far below 1073741822. Falsified if, with default cap, builder bytes or segment boundaries follow the row-id cap instead of the byte limit.

### B2. Unit tier

**B2a. Environment and build.** JDK 11, Ant. Copy the tree to local disk (e.g. `$HOME/work/c509`), never build in the shared tree. `ant jar` (or `ant build-test`), then add a test class `SegmentRowCapProbeTest` under `test/unit/org/apache/cassandra/index/sai/disk/v1/` modelled on `SegmentFlushTest` (it constructs `SSTableIndexWriter` with `IndexDescriptor.create(...)` over a temp dir, and calls `writer.addRow(...)` with chosen row ids). Run: `ant testsome -Dtest.name=SegmentRowCapProbeTest`. JVM `-Xmx` as in the default test config; heap measured, not sized.

**B2b. Knobs.** (1) Row cap via `SegmentBuilder.updateLastValidSegmentRowId(v)` with v in {-1 (default 1073741822), 1000, 100}; (2) the byte limit via a `NamedMemoryLimiter` instance passed to the writer: limit L in {1 MiB, 64 MiB, 1024 MiB}. A custom limiter object is passed straight to the `SSTableIndexWriter` constructor (SSTableIndexWriter.java:65-68), so no yaml is needed. Values: the default shows the claim, 1000 and 100 are the positive control for the row cap (known to bind at a small value).

**B2c. Workload.** Add N rows with consecutive row ids 0..N-1 and fixed term size S bytes (e.g. 100 bytes, distinct values) to one writer, N = 200000. Arithmetic: row-id span 200000 is far below the default cap 1073741822, so no cap flush is possible at default; at cap 1000, a flush is expected about every 1001 rows (a row with id offset 1001 gives span 1001 > 1000, line 266), i.e. roughly 200 segments; at cap 100, roughly 2000. For the byte limit: total entry bytes about N * (S + overhead) > 64 MiB only if overhead is large, so choose S = 1000 so that N*S is about 200 MB, which exceeds 64 MiB and 1 MiB but not 1024 MiB.

**B2d. Observables and instruments.** (a) Number of segments flushed: count of `SegmentMetadata` or the `segments` list size (private; use the debug log line "Flushed segment with {} cells" at SSTableIndexWriter.java:286, or read the written META component). (b) Peak `limiter.currentBytesUsed()` sampled after every `addRow` (NamedMemoryLimiter). (c) Per-segment `numRows`. Not directly observable: true heap of the trie buffer; use (b) as the operand and a GC-forced `Runtime.totalMemory()-freeMemory()` sample every 10000 rows as a cross-check only.

**B2e. Procedure.**
1. Copy tree, build.
2. Write the probe: for each (cap, L) pair in the matrix, reset (`updateLastValidSegmentRowId(-1)` in `@After`, as SegmentFlushTest.java:94 does), create a fresh writer, drive N rows, call `complete`, record segment count, per-segment rows, peak limiter bytes.
3. Run each of 3 caps x 3 limits (9 runs), repeat 3 times.
4. Also run the boundary pair from SegmentFlushTest (rows at 0 and cap, then 0 and cap+1) to confirm the strict `>`.
5. Delete the temp dirs.

**B2f. Predictions (before any run).** Default cap, L = 1024 MiB: segment count 1; peak bytes grows with N. Default cap, L = 64 MiB and 1 MiB: segment count > 1, peak bytes stays near L (overshoot bounded by one add plus the minimum-flush condition); segment boundaries do not depend on the cap. Cap 1000: about 200 segments of about 1001 rows regardless of L (when L is large), peak bytes about 1001 * entry size, far below L. Cap 100: about 2000 segments, peak bytes about 101 entries. Boundary: rows at id 0 and cap give 1 segment, 0 and cap+1 give 2. A contradiction would be a flush at default cap with span 200000, or a peak not tracking L.

**B2g. Readings.**

| Observation | Meaning |
|---|---|
| Default cap: segments and peak bytes change when L changes, no change when cap is left at default | claim confirmed (usage follows the byte limit, not the constant) |
| Default cap: a flush occurs at row-id span 200000 with large L | claim refuted (an unexpected cap path) |
| Cap 1000/100 shrinks peak bytes and segment size independent of L | positive control moves: the row cap binds only at a tiny value; consistent with claim at default |
| Cap 1000/100 does not change segment count | control did not move: harness not driving the hook (hook is static and applies to builders created after the call; check ordering); not confirmed |
| Peak bytes never reaches L at L = 1 MiB | limit never reached; not confirmed, enlarge S or N |
| Boundary pair yields 2 segments at cap not cap+1 | contradicts strict `>` at line 266; correct A3 |

**B2h. Controls.** Fixed term size and values across runs; same N; reset the static hook between runs; run with the limiter large and cap default as baseline; a run with the row cap tiny and L large separates the two limits; repeat 3 times to see variance. Non-indexed rows (gaps in row ids) test: add rows at ids 0 and 1073741823 only, one term each: two segments, tiny bytes, showing the cap acts on id span, not bytes.

### B3. Cluster tier

**B3a. Environment and build.** One node first, JDK 11, built from a local copy (`ant jar`), data/commitlog/hints under a local disk directory of known size (>= 30 GB free, set `data_file_directories`, `commitlog_directory`, `hints_directory`, `saved_caches_directory` to it). Heap `-Xms4G -Xmx4G` via `jvm11-server.options`/`cassandra-env.sh`. Enable SAI as shipped in 5.0. Real cap changes need a code edit, so build a second variant jar with `LAST_VALID_SEGMENT_ROW_ID` set to a small value (e.g. 10000) in the local copy only (positive control).

**B3b. Knobs.** `sai_options.segment_write_buffer_size` in cassandra.yaml in {16MiB, 256MiB, 1024MiB (default)}; the build variant (default constant vs the edited small constant). Restart needed for both.

**B3c. Workload.** Table with a text or int column and a SAI index created after data load (index build over existing sstables is where SegmentBuilder is used outside memtable flush, per V1OnDiskFormat.java:113-125 comment); create the index afterwards with `CREATE CUSTOM INDEX ... USING 'StorageAttachedIndex'`. Load with `cassandra-stress` or CQL: 5,000,000 rows, 1 KB values, distinct (about 5 GB raw), single sstable via `nodetool flush` and compaction. Row-id span is 5,000,000, far below the default cap, so the cap cannot trigger. Duration: each index build several minutes.

**B3d. Observables and instruments.** Heap: `jcmd <pid> GC.heap_info` and JMX `java.lang:type=Memory` HeapMemoryUsage sampled every 2 s during the build; GC log (`-Xlog:gc*`); debug logs for the SAI lines ("Flushed segment with ... cells", "Global limit of ... exceeded") by enabling DEBUG for `org.apache.cassandra.index.sai`; count of segments from the system view `system_views.sai_sstable_indexes`/segments view (names not verified; check `SegmentsSystemViewTest.java` for the exact virtual table); on-disk index size via `du` on the `*SAI*` components. Not observable: per-builder bytes (use log lines).

**B3e. Procedure.**
1. Copy tree, build default jar and the small-constant variant jar in separate local dirs.
2. Start the node with default jar, 16MiB limit. Load data, flush, create the index, record heap peak, number of segments, log lines, index size; stop the node, wipe, repeat for 256MiB and 1024MiB.
3. Repeat step 2 using the small-constant jar at 1024MiB.
4. Stop all Cassandra processes (`pgrep -f CassandraDaemon`), verify none left.

**B3f. Predictions.** Default constant: segment count decreases and peak extra heap during the build increases as the byte limit goes 16 -> 256 -> 1024 MiB; "Global limit of ... exceeded" logs appear at 16 MiB and not at 1024 MiB for this data; no segment is split at row-id span near 5,000,000. Small constant (10000): about 500 segments for 5,000,000 rows irrespective of limit, and lower peak heap than the default at 1024 MiB. Exact numbers are not stated here, only the relation.

**B3g. Readings.**

| Observation | Meaning |
|---|---|
| With default constant, heap peak and segment count track `segment_write_buffer_size` | claim confirmed |
| With default constant, segment count and heap unchanged by the byte limit and splits near the row cap | claim refuted |
| Small-constant jar produces about 500 segments and lower peak heap | positive control moved (the row cap can bind when tiny) |
| Small-constant jar shows no change | control did not move; check the jar is actually used; not confirmed |
| Byte limit never exceeded at 16 MiB (no log line) | limit never reached; increase data volume; not confirmed |

**B3h. Controls.** Same data and heap size across runs, node wiped between runs, same sstable layout (single sstable), page cache dropped is not required; GC settings unchanged; one variable changed per run. Check heap noise by repeating the 256MiB run twice.

**B4. Risks and cleanup.** Disk: about 5 GB data plus index per run; use local disk of known size, delete the data dirs after each run. No shared storage and no writes into the shared source tree (work in the local copy). Stop every started JVM and test run, check with `pgrep -f "CassandraDaemon|ant"`; remove temp dirs created by the probe test (`Files.createTempDirectory`); remove the variant build directories when finished. Lowering the heap limit may cause GC pressure on the node, which is expected.

## C. Sources read

- /tmp/claude-20001/-proj-misconfiguration-PG0-git-repos-Misconfiguration/d3cfd622-d93d-5998-b33d-926864ab48d4/scratchpad/agent-docs/INSTRUCTIONS.md
- /tmp/claude-20001/-proj-misconfiguration-PG0-git-repos-Misconfiguration/d3cfd622-d93d-5998-b33d-926864ab48d4/scratchpad/agent-docs/playbook-autonomous.md
- /tmp/claude-20001/-proj-misconfiguration-PG0-git-repos-Misconfiguration/d3cfd622-d93d-5998-b33d-926864ab48d4/scratchpad/agent-docs/_TEMPLATE-autonomous.md
- /tmp/claude-20001/-proj-misconfiguration-PG0-git-repos-Misconfiguration/d3cfd622-d93d-5998-b33d-926864ab48d4/scratchpad/agent-in/149.md
- src/java/org/apache/cassandra/index/sai/disk/v1/segment/SegmentBuilder.java
- src/java/org/apache/cassandra/index/sai/disk/v1/SSTableIndexWriter.java
- src/java/org/apache/cassandra/index/sai/disk/v1/V1OnDiskFormat.java (lines 112-130)
- src/java/org/apache/cassandra/index/sai/utils/NamedMemoryLimiter.java (grep excerpts)
- src/java/org/apache/cassandra/config/StorageAttachedIndexOptions.java, DatabaseDescriptor.java (grep excerpts)
- test/unit/org/apache/cassandra/index/sai/disk/v1/SegmentFlushTest.java (lines 80-100, 235-260 and grep hits)
- grep hits over src/ and test/ for `LAST_VALID_SEGMENT_ROW_ID`, `updateLastValidSegmentRowId`, `exceedsSegmentLimit`

## D. Stage-4 feedback

`none yet`
