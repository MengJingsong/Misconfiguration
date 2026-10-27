# none — SAI addTerm empty-term skip — verification solution  <!-- file: cases/none-addterm-term_remaining--autonomous.md -->

| Field | Value |
|---|---|
| Entry pointer | [`SSTableIndexWriter.java:221`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/index/sai/disk/v1/SSTableIndexWriter.java#L221) |
| Pinned source | `cassandra-5.0.9` |
| Session / date | Claude Code CLI (Agent-tool subagent), 2026-10-27 |
| Estimate | `negative`: the line is a per-value validity check (skip empty buffers for types that do not index them) with no limit behind it; it bounds no memory or disk object. The nearest cap, `sai_options.segment_write_buffer_size`, is a different statement in the same method and is a soft cap. |
| Ground | The condition `term.remaining() == 0 && skipsEmptyValue()` compares against the literal 0 and the column type's properties. Skipping an empty term only avoids adding zero-length data; it cannot make usage follow any configured limit. Usage of the segment builder is governed by other code (the limiter, A3 steps 5-6). |

> Link rule applied: declaration and if statement are permalinks at `cassandra-5.0.9`.

## A. Constraint trace

**A1. The constraint.** At the target there is no resource constraint. The line is `if (term.remaining() == 0 && index.termType().skipsEmptyValue()) return;` at [`SSTableIndexWriter.java:221`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/index/sai/disk/v1/SSTableIndexWriter.java#L221), inside `addTerm` (declared at line 205). `skipsEmptyValue()` is `!indexType.allowsEmpty() || !isLiteral()` ([`IndexTermType.java:284`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/index/sai/utils/IndexTermType.java#L284)). `allowsEmpty()` defaults to `false` (AbstractType.java:513-516) and `Int32Type` overrides it to `true` (Int32Type.java:50-53); I did not check other types (not verified). `isLiteral()` tests a capability flag (IndexTermType.java:177-180). So: kind = type property, no yaml key, no `-D`, no JMX, not settable, no restart question; no unit, no default.

The nearest memory constraint (the one the same method feeds) is `sai_options.segment_write_buffer_size`:
- declared at [`StorageAttachedIndexOptions.java:35`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/StorageAttachedIndexOptions.java#L35) (configuration entry, `IntMebibytesBound`, MiB);
- default `DEFAULT_SEGMENT_BUFFER_MB = 1024` (StorageAttachedIndexOptions.java:27); maximum 32768 MiB enforced by `validate()` (StorageAttachedIndexOptions.java:30, 39-45);
- yaml: commented example `# segment_write_buffer_size: 1024MiB` under `# sai_options:` (conf/cassandra.yaml:1790-1794); `Config.sai_options` is at Config.java:804; read by `DatabaseDescriptor.getSAISegmentWriteBufferSpace()` (DatabaseDescriptor.java:5264-5267);
- converted to bytes once, into a `static final` at class load: [`V1OnDiskFormat.java:126`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/index/sai/disk/v1/V1OnDiskFormat.java#L126), then wrapped in `SEGMENT_BUILD_MEMORY_LIMITER` (V1OnDiskFormat.java:128-129). Because it is a static final read at class load, a change needs a restart (follows from the code; not run). I found no JMX setter (grep over `src/java` for the name showed only the files above).

**A2. What it caps.** The target line caps nothing. The nearest cap is heap: the sum of bytes that all currently-building SAI segment builders have allocated (`limiter.currentBytesUsed()`, NamedMemoryLimiter.java:72-75), compared with `limitBytes` (NamedMemoryLimiter.java:53-56). Each builder's `totalBytesAllocated` comes from `SegmentTrieBuffer.memoryUsed()` / `add` (SegmentTrieBuffer.java:57, 62; SegmentBuilder.java:84).

**A3. Mechanism.** In `addTerm` ([`SSTableIndexWriter.java:205`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/index/sai/disk/v1/SSTableIndexWriter.java#L205)):
1. Line 207: `index.validateTermSize(..., false, null)`; for non-client mutations it returns false when the max-term-size guardrail fails (StorageAttachedIndex.java:815-834, the `failsOn` check at 823), which skips the term with a log. This is a per-term size check, not a total cap.
2. Lines 210-218: create a builder if none; else `shouldFlush` and, if true, flush and start a new builder.
3. **The if statement** [`SSTableIndexWriter.java:221`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/index/sai/disk/v1/SSTableIndexWriter.java#L221): if the term is empty and the type skips empties, return. Outcome true: nothing added, the limiter and builder are untouched. Outcome false: continue to line 223.
4. Lines 223-236: add the term (or each analyzer token) with `limiter.increment(currentBuilder.add(...))`, so the limiter rises by the bytes the builder allocated.
5. `shouldFlush` (lines 245-262): flush when `limiter.usageExceedsLimit() && currentBuilder.hasReachedMinimumFlushSize()` (line 248), or `exceedsSegmentLimit(row)` (line 262, SegmentBuilder.java:258-267). `minimumFlushBytes = limitBytes / activeBuilderCount` (SegmentBuilder.java:149).
6. Flush releases the builder's bytes (SSTableIndexWriter.java:293-295, SegmentBuilder.java:230-237).

Overshoot/bypass paths: (a) the check at line 248 runs only on the *next* `addTerm` call, and a flush needs both conditions, so global usage can exceed the limit until each builder passes its share of the minimum flush size; one large term or many concurrent builders increases the overshoot (reasoning from the code, not run). (b) The limiter is used only for non-flush builds: `V1OnDiskFormat.newPerColumnIndexWriter` returns `SSTableIndexWriter` only if the op is not a FLUSH or the index initial build has not started (V1OnDiskFormat.java:175-181); memtable flush uses `MemtableIndexWriter` instead (V1OnDiskFormat.java:183-188), which does not use this limiter. (c) The limiter is only an accounting counter (NamedMemoryLimiter.java:58-63): it never blocks an allocation.

**A4. Other consumers.** SAI memtable index memory (the flush path in A3(b)), the memtable itself, key cache/chunk cache, and the compaction/index-build buffers outside the segment trie buffer share the heap and are not counted by this limiter. Several `SSTableIndexWriter` instances (one per index per concurrent build/compaction) share the single static limiter.

**A5. Evidence beyond the source.** conf/cassandra.yaml:1790-1794 (comment: "Total permitted memory allowed for writing SAI index segments... split between all SAI indexes being built"); Javadoc at V1OnDiskFormat.java:114-125. No issue numbers relied on.

## B. Verification solution

**B1. Claim under test.** The empty-term skip at line 221 does not bound memory or disk: a workload of only empty values on a type that skips them leaves the segment-build limiter at its baseline and produces no index segment data whatever `segment_write_buffer_size` is, while the same workload with non-empty values does raise the limiter and triggers flushes governed by that setting (positive control). Falsified if empty values raise the limiter or the on-disk index size, or change with the knob.

### B2. Unit tier

**B2a. Environment and build.** JDK 11, Ant. Copy the tree to local disk (`rsync -a /users/jason92/cassandra-5.0.9/ $WORK/c5/`); never build in the shared tree. `cd $WORK/c5 && ant jar`. Put a new test class under `$WORK/c5/test/unit/org/apache/cassandra/index/sai/disk/v1/` (new file, `SSTableIndexWriterEmptyTermTest`) extending `SAITester` (test/unit/org/apache/cassandra/index/sai/SAITester.java exists). Run with `ant testsome -Dtest.name=SSTableIndexWriterEmptyTermTest`; JVM options as the test target default; add `-Xmx2g`.

**B2b. Knobs.** (1) Limiter limit via `new NamedMemoryLimiter(limitBytes, "test")` (public constructor, NamedMemoryLimiter.java:42; `setLimitBytes` at :83): 64 KiB (small, forces flushes), 1 MiB, 1 GiB. (2) Value kind: empty vs non-empty. (3) Column type: `int` (`allowsEmpty` true, non-literal, so skip applies at line 221) and `text` (literal; whether skipping applies depends on its `allowsEmpty`, not verified; record the observed outcome). The limiter is passed directly to `new SSTableIndexWriter(indexDescriptor, index, limiter, () -> true)` (SSTableIndexWriter.java:65-75), so no yaml change is needed.

**B2c. Workload.** Call `writer.addRow(key, row, rowId)` for N = 100,000 rows with strictly increasing row ids (SegmentBuilder.add asserts non-decreasing ids, SegmentBuilder.java:171). Variant E: every `int` value is `ByteBufferUtil.EMPTY_BYTE_BUFFER` (zero bytes). Variant N: every value a distinct 4-byte int. Arithmetic: variant N allocates at least 4 bytes x 100,000 = 400 KB of term payload plus trie overhead, which exceeds the 64 KiB limit about six times over, so at least one flush occurs; variant E allocates 0 by design.

**B2d. Observables and instruments.** `limiter.currentBytesUsed()` after every 1,000 rows; `SegmentBuilder.getActiveBuilderCount()` (SegmentBuilder.java:140); number of flushes (count `flushSegment` log lines at debug, logger in SSTableIndexWriter, or segment count after `complete`); size of the written index component files in the test's temp directory (`du -sb`). Not observable directly: true heap retained by the trie buffer (only the builder's own estimate).

**B2e. Procedure.** (1) Build; (2) for each limit in {64 KiB, 1 MiB, 1 GiB} and each variant in {E, N}: create a fresh limiter and writer, add rows, sample the limiter, call `complete`, record flush count, final limiter value, component bytes; (3) repeat for `text` with E; (4) delete the temp directory.

**B2f. Predictions.** Variant E: limiter value stays equal to its starting value (the builder's initial `totalBytesAllocated` is added once at builder creation, SSTableIndexWriter.java:330; so a constant, not growing) at every sample, zero flushes triggered by the limit, identical for all three limits. Variant N: limiter grows with rows, exceeds the 64 KiB limit and flushes repeatedly (drops back after each flush); at 1 GiB no limit-triggered flush; flush count falls as the limit rises.

**B2g. Readings.**

| Observation | Meaning |
|---|---|
| E: limiter flat and flush count 0 at all limits; N: limiter rises and flush count falls with larger limit | Claim confirmed: the skip bounds nothing, the control shows the limiter works |
| E: limiter grows with rows or depends on the limit | Claim refuted: empties are being accumulated or governed by the knob |
| E: flat, but N does not move either (no growth, no flushes at 64 KiB) | Not confirmed: the control failed (check the writer is wired, rowIds, type) |
| N: limiter never exceeds the limit by more than one builder's share | Cap holds tightly in this setup (useful for B3 comparison) |
| N: limiter exceeds the limit by a lot between flushes | Overshoot noted in A3(a) is real |

**B2h. Controls.** The N variant is the positive control (same writer, same row count, non-empty). Run E with a non-skipping case if one is found in the `text` run, to show that when the skip does not apply, empty values do add (small) bytes. Fresh limiter per run so state does not leak.

### B3. Cluster tier

**B3a. Environment and build.** One node, JDK 11, local copy built as in B2a (`ant jar`), data, commitlog, hints and saved_caches on a local disk directory of known size (>= 20 GiB free), `-Xms2g -Xmx2g`. Config: `sai_options: {segment_write_buffer_size: <value>MiB}` in the node's cassandra.yaml (key name verified at StorageAttachedIndexOptions.java:35; the commented sample in conf/cassandra.yaml:1790-1794 shows the nesting). `cassandra -f` with a separate `-Dcassandra.config` copy.

**B3b. Knobs.** `segment_write_buffer_size` = 1 MiB (small; the smallest positive value since the type is whole MiB) and 1024 MiB (default); changed by editing the yaml and restarting. Value kind (empty vs non-empty), as in B2b.

**B3c. Workload.** Create keyspace (RF 1) and table `t(pk int PRIMARY KEY, v int)`. Load data first, then create the SAI index afterwards (`CREATE CUSTOM INDEX ON t(v) USING 'StorageAttachedIndex'`), so the build runs through the non-flush path that uses the limiter (V1OnDiskFormat.java:175-181, as per A3(b)). Variant E: 5,000,000 rows with `v = blobAsInt(0x)` (empty int; `Int32Type.allowsEmpty` is true). Variant N: 5,000,000 rows with distinct `v`. Load with `cassandra-stress` or a CQL batch script; flush with `nodetool flush` before creating the index. 5M rows with distinct 4-byte values exceed 1 MiB by far.

**B3d. Observables and instruments.** JMX/metric `SegmentBufferSpaceUsedBytes` and `SegmentBufferSpaceLimitBytes` (registered at V1OnDiskFormat.java:133-137), read every second via `nodetool sjk mx` or a JMX poller during the build; heap used by `jcmd <pid> GC.heap_info` or `jstat -gc` every second; index component bytes with `du -sb` on the table's `*SAI*` files after the build; `nodetool` / system.log lines "Memory limiter using limit of ..." (NamedMemoryLimiter.java:47) and debug "Flushed segment" lines. Not observable: the builder's internal estimate vs real retained heap beyond what GC info shows.

**B3e. Procedure.** (1) Start the node with limit L; (2) create schema, load variant data, `nodetool flush`; (3) start pollers; (4) create the index and wait for the build to finish (`nodetool compactionstats`, `system_distributed`/index status via `SELECT * FROM system."IndexInfo"`); (5) record peak metric, peak heap, final index bytes, segment count; (6) stop the node, drop data directory; (7) repeat for each (L, variant) pair; (8) confirm no `CassandraDaemon` process remains (`pgrep -f CassandraDaemon`).

**B3f. Predictions.** Variant E: `SegmentBufferSpaceUsedBytes` stays at its baseline (near 0, only builder initial overhead), peak heap rise during the build is unrelated to L, the SAI term data is empty or trivial, and the result is the same at 1 MiB and 1024 MiB. Variant N at 1 MiB: used-bytes oscillates around about 1 MiB (modest overshoot), many segments; at 1024 MiB: used-bytes grows far larger, fewer segments, peak heap rise larger.

**B3g. Readings.**

| Observation | Meaning |
|---|---|
| E: used-bytes flat, heap rise and index size unrelated to L; N: used-bytes and segment count track L | Claim confirmed |
| E: used-bytes or index bytes grow or change with L | Claim refuted |
| E flat but N also flat (build never used the limiter, e.g. memtable path taken) | Not confirmed: control did not move; check the index was created after the flush |
| N: peak heap far above L plus baseline | The cap is soft or other consumers dominate (informational for A3(a), A4) |

**B3h. Controls.** N is the positive control at the same row count. Same JVM options, same data directory size, fresh data directory per run; run E twice to see noise in heap readings; run a baseline with no index to separate heap noise from index build.

**B4. Risks and cleanup.** Disk: 5M-row tables and index files (a few GiB at most); keep everything under a local directory of known size, not the shared tree or shared storage. Processes: the unit JVM and Cassandra node; stop with `nodetool stopdaemon` or `kill`, then `pgrep -f "CassandraDaemon|ant"` must be empty. Cleanup: `rm -rf` the data/commitlog/hints/saved_caches directories and the test temp directory; remove the local source copy if not needed. Nothing is changed outside the nodes.

## C. Sources read

- /users/jason92/cassandra-5.0.9/src/java/org/apache/cassandra/index/sai/disk/v1/SSTableIndexWriter.java
- /users/jason92/cassandra-5.0.9/src/java/org/apache/cassandra/index/sai/utils/IndexTermType.java
- /users/jason92/cassandra-5.0.9/src/java/org/apache/cassandra/index/sai/disk/v1/V1OnDiskFormat.java
- /users/jason92/cassandra-5.0.9/src/java/org/apache/cassandra/index/sai/disk/v1/segment/SegmentBuilder.java
- /users/jason92/cassandra-5.0.9/src/java/org/apache/cassandra/index/sai/utils/NamedMemoryLimiter.java
- /users/jason92/cassandra-5.0.9/src/java/org/apache/cassandra/index/sai/StorageAttachedIndex.java
- /users/jason92/cassandra-5.0.9/src/java/org/apache/cassandra/config/StorageAttachedIndexOptions.java
- /users/jason92/cassandra-5.0.9/src/java/org/apache/cassandra/config/DatabaseDescriptor.java
- /users/jason92/cassandra-5.0.9/src/java/org/apache/cassandra/db/marshal/AbstractType.java, Int32Type.java
- /users/jason92/cassandra-5.0.9/conf/cassandra.yaml

## D. Stage-4 feedback

`none yet`
