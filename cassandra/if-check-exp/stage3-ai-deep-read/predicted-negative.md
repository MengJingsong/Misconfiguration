# Stage 3 — predicted negative (lines considered and rejected)

If statements read **with the Cassandra source open** (`cassandra-5.0.9`) and
rejected against the three rules
([`../README.md` §3.4–§3.6](../README.md#3-core-concept-the-if-check-case)). A line
here carries a **negative estimate**: a prediction from the source that usage
does not follow the constraint. Stage 4 confirms or refutes it.

- **This is the only rejection file in the experiment**, and it is
  authoritative for every rejection. Stage 2 cannot reject: it gives a hopeless
  row band D in `../stage2-ai-preprocessing/bands.csv` instead.
- **Each entry is a write-up queue item** (decided 2026-10-19). It is to be
  written up in `cases/` by either agent, with the estimate `negative` and a
  verification solution that tests that usage does not follow the constraint.
  New rejections go straight to a case file.
- **An entry leaves this file once its case is verified at stage 4**; its
  verdict is then in [`_INDEX.md`](_INDEX.md) §1. Until then, a written-up
  entry links its case file in the reason. Lessons from these reads are in
  [`playbook-guided.md`](playbook-guided.md) §3.1. A line is recorded in one place
  only: if a later pass reaches a line already here, cite this entry.
- **Organised by the reason for rejection** (2026-10-21), not by pass or date.
  The rules are cited as Rule 1 (the limit side is a capacity), Rule 2 (changing
  the limit moves a maximum of bytes) and Rule 3 (the branches diverge on object
  creation). The earlier per-pass layout, with its counts and the stage-2 band of
  each row, is in git at commit `acecd48`.
- **Re-examine first:** one entry rests on the "count of concurrent tasks"
  reasoning that stage 4 refuted for `concurrent_compactors` (usage = tasks ×
  per-task bytes): `SEPExecutor` / `SEPWorker` in
  [§10](#10-count-time-rate-and-work-thresholds); its `SEPExecutor.java:196` left on
  2026-10-21 (Confirmed — does not cap), the other lines of that row are untested. The other, `StorageProxy.java:1592`
  (`maxHintsInProgress`), left this file on 2026-10-21, verified at stage 4 as
  Confirmed — does not cap, on a different ground: its per-destination counter is a bare
  `CacheLoader`, so the check never fires (see `_INDEX.md` §1).
- **First write-up batch (2026-10-21).** Four entries were written up by fresh autonomous
  agents and run at stage 4. **Three came back with a positive estimate and stage 4 found
  usage follows the knob**, so their grounds here did not hold:
  `commitlog_total_space` (`:249`, caps, soft), `index_summary_capacity` (`:341`, caps at each
  resize run, with bypasses), and `tombstone_failure_threshold` (`ReadCommand.java:591`, left
  this file: the abort fires while tombstones are serialized into the replica's response, so
  one read's buffer is bounded by about (T + 1) tombstones; the node heap under concurrent
  readers is not). The fourth, `SEPExecutor.java:165`, is above. Lesson for the remaining
  entries: "counts items, not bytes" and "a soft target, not a ceiling" are weak grounds
  when each item has a known size or the target is enforced periodically.
- **Second write-up batch (2026-10-21/22).** Five §9 entries were written up by fresh
  autonomous agents and run at stage 4; all five **left this file** (verdicts in
  [`_INDEX.md`](_INDEX.md) §1). Four came back with a positive estimate and usage follows the
  knob for all four, so their grounds here did not hold:
  `AbstractCommitLogSegmentManager.java:259` (`commitlog_total_space`; picks just enough
  segments to bring the log back to the limit; caps (soft), unit Confirmed, cluster Not
  confirmed: unthrottled peaks set by flush speed, not the limit),
  `IndexSummaryRedistribution.java:258` (`index_summary_capacity`; the operand is
  pool − floors exactly; caps only on some paths, as for `:341`),
  `OutboundConnection.java:449` (`internode_application_send_queue_capacity`; the release
  keeps the reserve at exactly max(0, pending − C); queued bytes cap at C + reserve, heap
  linear in C plus a ~42 MiB offset), and `MemtablePool.java:128`
  (`memtable_heap_space` × `memtable_cleanup_threshold`; the soft trigger fires exactly above
  L·t and holds memtable heap there; caps). The fifth, `AbstractAllocatorMemtable.java:274`
  (written up as `largestRatio`, estimate negative), held on the ceiling (L is set by
  `memtable_heap_space`, not this line) but the unit tier refuted "same peak/L whatever is
  selected": the selection moves usage below L, and a changed selection wasted heap in slab
  regions. Lesson: "release / soft target" rows that hand back or trigger on a byte operand
  tied to a knob behave as caps at runtime; re-read the rest of §9 with that in mind.
- **Third write-up batch (2026-10-22).** Five more §9 lines were written up by fresh autonomous
  agents and run at stage 4; all five **left this file** (verdicts in [`_INDEX.md`](_INDEX.md) §1).
  Three kept a negative estimate and no tier refuted it: `BufferPool.java:1521`
  (`NORMAL_CHUNK_SIZE`; unit Confirmed — does not cap, neither outcome moves reserved or direct
  memory; the overflow trim at `:883-885` drives `OverflowSize` to −14.7 GB),
  `OutboundConnection.java:767` (`OTCP_LARGE_MESSAGE_THRESHOLD`; cluster Confirmed — does not cap,
  queued bytes set by the send-queue cap; unit pool peak rose ~3 frames, < 0.5 MiB) and `:871`
  (`flushLowWaterMark`; both tiers Not confirmed on one size prediction each, readings flat in the
  low mark). Two came back positive: `PreV5Handlers.java:127`
  (`native_transport_max_request_data_in_flight`; Confirmed — caps (soft), peak exactly one
  request over L plus one per connection) and `StorageAttachedIndex.java:1006`
  (`memtable_heap_space`; the SAI charge is exact and the pool caps it, ~3.5 × held; cluster
  Not confirmed on an under-sampled sawtooth row). The "release / soft target" lesson held for
  lines whose operand is a configurable byte count; it did not for hard-coded water marks and
  pool-internal bookkeeping.
- **Fourth write-up batch (2026-10-22).** The last two §9 lines and three §10 `SEPExecutor` lines were
  written up by fresh autonomous agents and run at stage 4; all five **left this file** (verdicts in
  [`_INDEX.md`](_INDEX.md) §1). Two came back positive and Confirmed — caps:
  `AbstractMessageHandler.java:447` (`internode_application_receive_queue_reserve_global_capacity`; the
  release-back branch keeps the reserve exact, accounted peak ≤ Q + G; the held memory is off-heap, 1.4–1.5 ×
  accounted) and `CommitLogSegmentManagerCDC.java:93` (`cdc_total_space`; `cdc_raw` plateau at the cap, soft by
  at most a segment). Three kept a negative estimate with the unit tier Confirmed — does not cap and the cluster
  tier Not confirmed: `SEPExecutor.java:175` and `:135` (both resolved to the hard-coded
  `getMaxTasksQueued() = Integer.MAX_VALUE`; queued tasks are unbounded) and `:384` (`maximumPoolSize`
  resize). Lesson: a thread-pool permit line is a clean unit-tier "does not cap", but the cluster tier cannot
  separate the pool size from the upstream in-flight byte limits and `native_transport_max_threads`.

Contents: [1](#1-configuration-and-argument-validation) validation ·
[2](#2-logging-warning-or-diagnostic-only) logging only ·
[3](#3-per-item-bounds) per-item bounds ·
[4](#4-rollover-and-chunking) rollover ·
[5](#5-path-selection) path selection ·
[6](#6-growth-and-layout-of-a-structure) growth ·
[7](#7-invariant-guards-and-checks-that-allocate-nothing) invariant guards ·
[8](#8-read-validation-against-the-inputs-own-length) read validation ·
[9](#9-release-reclaim-and-soft-targets) release and reclaim ·
[10](#10-count-time-rate-and-work-thresholds) counts, time, rate ·
[11](#11-selection-and-strategy) selection ·
[12](#12-emptiness-sentinel-and-enabled-tests) emptiness tests ·
[13](#13-not-production-code) not production ·
[14](#14-whole-package-surveys) package surveys ·
[Observations for Target 3](#observations-for-target-3)

## 1. Configuration and argument validation

Range and cross-key checks at startup, in a setter, at schema creation or on a
tool's arguments. They throw or clamp a setting; no runtime allocation is gated.
The limits they validate are enforced elsewhere.

| If statement | Reason rejected |
|---|---|
| `AbstractCompactionStrategy.java:456` `thresholdValue < 0` | Throws on a negative option value. |
| `LeveledCompactionStrategy.java:78`, `:81` `configuredMaxSSTableSize` bounds | Startup validation and clamping of the option. |
| `LeveledCompactionStrategy.java:580`, `:597` `ssSize < 1`, `fanoutSize < 1` | Throws `ConfigurationException`. |
| `SizeTieredCompactionStrategyOptions.java:73` `minSSTableSize < 0` | Option validation. |
| `TimeWindowCompactionStrategyOptions.java:126` `sstableWindowSize < 1` | Option validation. |
| `unified/Controller.java:202`, `:268`, `:381`, `:385`, `:499`, `:504`, `:529`, `:609`, `:613` | Validation of options and arithmetic deriving the target SSTable size; none diverges into "create or block". |
| `SSTableSplitter.java:52` `sstableSizeInMB <= 0` | Argument check of a CLI tool. |
| `DatabaseDescriptor.java:911`, `:914`, `:978`, `:981`, `:984`, `:987` | A message size must not exceed the in-flight and reserve caps. |
| `DatabaseDescriptor.java:1016` (2 units), `:4093`, `:5347` (2 units) | Startup range checks. |
| `GuardrailsOptions.java:1219`, `:1257` | A guardrail's fail threshold must not be below its warn threshold. |
| `StorageAttachedIndexOptions.java:41`; `IndexMode.java:190`; `SAICodecUtils.java:129` (2 units) | Index option checks; SASI's flush memory is clamped to 100 GiB.<br>**Trace-back 2026-10-27, rejected (not a memory/disk cap):** `SAICodecUtils.java:129` (`checkBlockSize`) tests a block size against `AbstractBlockPackedWriter.MIN_BLOCK_SIZE` (64) and `MAX_BLOCK_SIZE` (`1 << 27`), `AbstractBlockPackedWriter.java:34-35`: hard-coded format-sanity bounds, not settable. |
| `CQLSSTableWriter.java:539`; `CompressionParams.java:352`, `:456#2` | Writer and compression option checks. |
| `KeyspaceMetadata.java:68`; `TableMetadata.java:517`; `CreateIndexStatement.java:213` | Schema checks: a name fits its length.<br>**Trace-back 2026-10-27, rejected (not a memory/disk cap):** `SchemaConstants.NAME_LENGTH` = 48 (`SchemaConstants.java:75`) for `KeyspaceMetadata.java:68` and `CreateIndexStatement.java:213`; `TABLE_NAME_LENGTH` = 222 (`SchemaConstants.java:91`) for `TableMetadata.java:517`. Hard-coded name-length limits so file and directory names fit. |
| `ColumnFamilyStore.java:2185` | A ratio lies in [0, 1].<br>**Trace-back 2026-10-27, rejected (not a memory/disk cap):** Correction: `ColumnFamilyStore.java:2185` is `snapshotName.length() > SchemaConstants.FILENAME_LENGTH` (255, `SchemaConstants.java:80`) in the snapshot-name validation, enforced only when `cassandra.snapshot.validation` is true; it is not a ratio test. |
| `StorageService.java:6889` (2 units), `:6905` (2 units) | JMX setter range checks (e.g. the growth factor in [1.2, 5]). |
| `InMemoryTrie.java:64` (2 units) | Validates the trie size threshold; see [Observations](#observations-for-target-3) on its property. |
| `RepairTokenRangeSplitter.java:181` | Validates two repair options against each other. |
| `ByteBufferUtil.java:815` `0 > outputLength` | Throws `IllegalArgumentException` on a negative size. |

## 2. Logging, warning or diagnostic only

**Rule 3.** The branch logs, warns the client, bumps a metric or builds an error
message, and the operation goes on; nothing diverges on object creation. Several
are the warn twin of a filed fail threshold.

| If statement | Reason rejected |
|---|---|
| `RowIndexEntry.java:403` `estimatedMemory > warnThreshold.toBytes()` | Warn twin of the filed `row_index_read_size_fail_threshold` at `:392`. |
| `ReadCommand.java:724` `warnBytes != -1 && sizeInBytes >= warnBytes` | Warn twin of the filed `local_read_size_fail_threshold` at `:715`. |
| `ResultSetBuilder.java:87` (2 units) | Warn twin of `shouldReject()` (`:95-98`), the filed `coordinator_read_size_fail_threshold`. |
| `ReplicaFilteringProtection.java:333` | Warn twin of the undecided `:323` ([`undetermined.md`](undetermined.md) §7). |
| `ReadCommand.java:639`; `DatabaseDescriptor.java:726`, `:741`; `CommitLog.java:609`; `SimpleSeedProvider.java:110` | Log or warn and continue. |
| `DatabaseDescriptor.java:4096` | Logs when `repair_session_space` is above a quarter of the heap. |
| `NativeLibrary.java:197`; `SigarLibrary.java:78` (2 units), `:99` (2 units), `:120`; `StartupChecks.java:497`, `:554` | Startup checks of the OS environment (`mlockall` `ENOMEM`, process, file and address-space limits, read-ahead, `vm.max_map_count`), compared once and logged. |
| `MutationExceededMaxSizeException.makeTopKeysString():76` | Rule 2, not memory-significant: truncates the key list inside an error message. |
| `HeapUtils.java:115` `freeSpaceBytes < 2 * maxMemoryBytes` | Rule 2: refuses to start a heap dump unless the disk can hold twice the heap. One diagnostic file; no steady-state usage, no tunable term. |

## 3. Per-item bounds

**Rule 2.** The check throws for, or skips, **one** oversized item. It bounds no
total: every other item is unaffected, and the total is bounded elsewhere (or
not at all). Most limits here are encoding or type limits, not configuration.

| If statement | Reason rejected |
|---|---|
| `OutboundConnection.java:793`, `:979` `messageSize > getInternodeMaxMessageSizeInBytes()` | One oversized message; total outbound memory is bounded by `internode_application_send_queue_capacity` and its reserves. At `:979` the check sits after `new AsyncMessageOutputPlus(...)`, so it does not gate that allocation. |
| `HintsBuffer.java:152` `totalSize > slab.capacity() / 2` | One oversized hint; the hints ceiling is the filed `MAX_HINT_BUFFERS` case. |
| `OnDiskIndexBuilder.java:167`; `PerSSTableIndexWriter.java:218`; `TrieMemIndex.java:84` `term.remaining() >= MAX_TERM_SIZE` | Skips one term over a hardcoded `Short.MAX_VALUE` (stage 2's "configured" was wrong). The index's memory is bounded by `maxMemorySize` ([§4](#4-rollover-and-chunking)). SASI, deprecated in 5.0. |
| `NativeCell.java:100` `size > Integer.MAX_VALUE` | One native cell over 2 GiB; turns an overflow into a clean exception. |
| `OffHeapBitSet.java:43` `wordCount > Integer.MAX_VALUE` | One bloom filter over 16 GiB. |
| `DataOutputBuffer.java:152` `saturatedSize <= capacity()` | One buffer that can no longer grow past `MAX_ARRAY_SIZE`. Contrast `IndexSummaryBuilder.java:204` (a filed case), whose type bound caps a structure that grows with data. |
| `QueryProcessor.java:259`, `:758`; `Validation.java:51`; `ClusteringPrefix.java:278`, `:284`; `CassandraIndex.java:618` | One key, clustering or indexed value over the 65,535-byte unsigned-short length.<br>**Trace-back 2026-10-27, rejected (not a memory/disk cap):** `CassandraIndex.java:618` checks the indexed value against `FBUtilities.MAX_UNSIGNED_SHORT` = 0xFFFF (`FBUtilities.java:158`), a hard-coded serialization-format limit, not settable. |
| `SortedTableWriter.java:169`, helper `verifyPartition()`; `UnbufferedDataOutputStreamPlus.java:274` | One partition key, or one `writeUTF` string, over the same length. |
| `CacheService.java:504`; `ClientWarn.java:79`; `ByteBufferUtil.java:766` | A saved cache key, the client-warning list, one buffer: the same encoding bound. |
| `FrameEncoderCrc.java:71`; `FrameEncoderLZ4.java:73`; `FrameEncoderUnprotected.java:53` | The 128 KiB frame payload. |
| `StreamingMultiplexedChannel.java:231` | The 1 GiB stream control message. |
| `BlockBalancedTreeWriter.java:651`; `AbstractTokenTreeBuilder.java:297`, `:323`; `OnDiskIndexBuilder.java:598` | An index file format field.<br>**Trace-back 2026-10-27, rejected (not a memory/disk cap):** `BlockBalancedTreeWriter.java:651` guards Lucene's `ArrayUtil.MAX_ARRAY_LENGTH` (the Java array-length limit) for `bytesPerValue * numLeaves`; `TokenTreeBuilder.MAX_OFFSET` = 2^47-1 (`TokenTreeBuilder.java:37`) for `AbstractTokenTreeBuilder.java:297`; `OVERFLOW_TRAILER_CAPACITY` = 8 (`TokenTreeBuilder.java:35`) for `:323`; `MAX_KEYS_SPARSE` = 5 (`OnDiskIndexBuilder.java:575`) for `OnDiskIndexBuilder.java:598`. All hard-coded, not settable. |
| helper `OutboundConnection.isMaxPendingCount()` | Saturation of the packed pending-count field inside the filed send-queue case's `acquireCapacity()` (`OutboundConnection.java:391`): a type bound, not the byte cap. |
| `CodecUtils.java:101`, `:250` | Protocol v1/v2's 65,535 elements or bytes per collection.<br>**Trace-back 2026-10-27, rejected (not a memory/disk cap):** `CodecUtils.java:101` (65535 elements) and `:250` (65535 bytes) are hard-coded literals from the 2-byte length field of native protocol v1/v2; not settable. |
| `StorageAttachedIndex.java:503` | The ANN top-*k* cap per query. |
| `MappedBuffer.java:63`, `:105` (2 units), `:119` (2 units); `Memory.java:147#3`, `:188` (3 units) | Position, limit and copy bounds that throw `IndexOutOfBounds`. |
| `AsyncMessageOutputPlus.java:96` | A serialized size that disagrees with the declared one. |
| `InMemoryTrie.java:148` | One trie's 2 GiB addressing limit (`SpaceExhaustedException`). |
| helper `StandardAnalyzer.incrementToken()` | SASI's minimum token length. |

## 4. Rollover and chunking

**Rule 2, rollover** ([`../README.md` §3.5](../README.md#3-core-concept-the-if-check-case)'s
edge case). A buffer, page, block, segment, file or writer is full, so it is
written out and the next one starts. Every byte is still written or held; the
check only sets how it is split.

| If statement | Reason rejected |
|---|---|
| `MmappedRegions.updateState():208` `segmentSize + chunk.length + 4 > MAX_SEGMENT_SIZE` | Starts a new mmap segment; the whole file is mapped either way. |
| `MmappedRegions.java:170` `compressedFileLength - state.length <= MAX_SEGMENT_SIZE` | Picks the `updateState` overload; same as `:208`. |
| `IncrementalTrieWriterPageAware.complete():167` `nodeSize + branchSize < maxBytesPerPage` | Node placement within pages; everything is written. |
| `IncrementalTrieWriterPageAware.java:125`, `:127`, `:135`, `:141`, `:213`, `:215` | Page packing, as `:167`. |
| `HintsWriteExecutor.java:247`, helper `flushInternal()` `session.position() >= maxHintsFileSize` | Rolls to a new hints file; every hint is written. |
| `HintsWriter.java:205`, `:214` | Hints buffer written out and the next started.<br>Case files (2026-10-27, estimate negative): [`hints_write_buffer_size-append-hint_remaining`](cases/hints_write_buffer_size-append-hint_remaining--autonomous.md) (`:205`), [`write_buffer_size-append-hint`](cases/write_buffer_size-append-hint--autonomous.md) (`:214`). |
| `SSTableSimpleUnsortedWriter.java:110` `currentSize > maxSStableSizeInBytes` | `sync()` and a new SSTable (bulk loader). |
| helper `SSTableSimpleWriter.shouldSwitchToNewWriter()` | Same, for the sorted writer. |
| `BigFormatPartitionWriter.java:213`; `BtiFormatPartitionWriter.java:82` | Close a row-index block at `column_index_size`; the read-side heap of those entries is the filed `column_index_cache_size` and `row_index_read_size_fail_threshold` cases. |
| `PerSSTableIndexWriter.java:247` `currentBuilder.estimatedMemoryUse() < maxMemorySize` | Over the threshold a segment flush starts and a new builder is used; the token was added first. `maxMemorySize` is `1GiB` for flush, else `maxCompactionFlushMemoryInBytes` (`:365-369`). SASI. |
| `NamedMemoryLimiter.usageExceedsLimit():55`, read at `SSTableIndexWriter.shouldFlush():248` | SAI twin of `PerSSTableIndexWriter.java:247`. `limitBytes` is `segment_write_buffer_size` (1,024 MiB, shared node-wide, `V1OnDiskFormat.java:126-128`); over it a builder flushes and starts another, and the term is still added (`SSTableIndexWriter.java:225`). A soft target. |
| `BlockBalancedTreeWriter.java:528`; `AbstractBlockPackedWriter.java:62`; `PostingsWriter.java:222` | Index block cadence.<br>**Trace-back 2026-10-27, rejected (not a memory/disk cap):** `BlockBalancedTreeWriter.java:528`: `DEFAULT_MAX_POINTS_IN_LEAF_NODE` = 1024 (`:96`), hard-coded leaf size; `AbstractBlockPackedWriter.java:62`: `blockIndex == blockValues.length`, a buffer-full flush at hard-coded block sizes (`NumericValuesWriter.BLOCK_SIZE` 128 and `MONOTONIC_BLOCK_SIZE` 16384); `PostingsWriter.java:222`: `BLOCK_SIZE` = 128 (`:89`), a fixed postings-per-block format parameter. |
| `AbstractTokenTreeBuilder.java:520`; `OnDiskIndexBuilder.java:497` | SASI block cadence.<br>**Trace-back 2026-10-27, rejected (not a memory/disk cap):** `AbstractTokenTreeBuilder.java:520`: `TOKENS_PER_BLOCK` = 248 (`TokenTreeBuilder.java:36`); `OnDiskIndexBuilder.java:497`: `SUPER_BLOCK_SIZE` = 64 (`OnDiskIndexBuilder.java:129`). Hard-coded on-disk layout parameters. |
| `SSTableRewriter.java:156` | Reopens the new SSTable early every `sstable_preemptive_open_interval`: I/O scheduling. |
| `SequentialWriter.java:227` `bytesSinceTrickleFsync >= trickleFsyncByteInterval()` | Triggers an fsync: when data is forced to disk, not how much is written. |
| `Flusher.java:152`, `:183`, `:282`, `:303`, `:332`, `:345` (`MAX_FRAMED_PAYLOAD_SIZE`, flush-buffer bookkeeping) | How outbound response bytes are framed; buffers are sized to the response on either branch. |

## 5. Path selection

**Rule 3.** The comparison picks a route for the same bytes: the disallow
branch allocates or moves the same amount somewhere else.

| If statement | Reason rejected |
|---|---|
| `BufferPool.java:910`, `:940` `size > NORMAL_CHUNK_SIZE` | An oversized request skips the pool and `get()` calls `allocate(size, OFF_HEAP)`. The uncapped fallback the filed `file_cache_size` case records. |
| `BufferPool.java:929`, `:1602` | A tiny or a normal pool allocation. |
| `BufferedDataOutputStreamPlus.java:169`, `:191`, `:201`, `:211` | A typed write through the buffer or the slow path. |
| `RebufferingInputStream.java:195`, `:210`, `:219`, `:228`, `:250`, `:256`, `:287`, `:296` | A typed read from the buffer or the slow path. |
| `CompressedSequentialWriter.java:160`, `:163` | A chunk written compressed or raw. |
| `InboundMessageHandler.java:148`; `OutboundConnections.java:215`; `OutboundConnection.java:796` | Small or large message path or connection. |
| `FrameDecoderWith8bHeader.java:114`, `:129` | A partial frame stashed or decoded. |
| `ColumnFamilyStore.java:1931`, helper `isFilterFullyCoveredBy()` | A row served from the row cache or from SSTables. |
| `SimpleClient.java:770`, `:777`, `:818`, `:838` | The client side (stress and tests), not node code. |
| `TrieMemoryIndex.java:228`; `RangeTombstoneList.java:213` | Recursive or iterative insertion; a merge or a per-item add.<br>**Trace-back 2026-10-27, rejected (not a memory/disk cap):** `TrieMemoryIndex.java:228`: `MAX_RECURSIVE_KEY_LENGTH` = 128 (`TrieMemoryIndex.java:64`), hard-coded, only picks the insertion path in `addTerm`.<br>**Trace-back 2026-10-27, rejected (no constraint):** `RangeTombstoneList.java:213` in `addAll`: `size > 10 * tombstones.size` is a performance heuristic choosing `add()` or a merge (comment at `:196-211`). |
| `VectorMemoryIndex.java:190`, `:229`, helper `VectorIndexSegmentSearcher.shouldUseBruteForce()` | Brute-force or graph search.<br>**Trace-back 2026-10-27, rejected (no constraint):** `shouldUseBruteForce` (`VectorIndexSegmentSearcher.java:349`, `numRows <= maxBruteForceRows`) is a cost heuristic for brute-force versus graph search. |
| `RandomAccessReaderAdapter.java:69`, `:117` | A read across a region boundary through a temporary buffer.<br>**Trace-back 2026-10-27, rejected (no constraint):** `RandomAccessReaderAdapter.java:69` and `:117` compare the requested float or int count with what remains in the current buffered region; the region size was not traced to a setting. |
| helper `ByteBufferUtil.canMinimize()` | Whether a buffer can be trimmed. |

## 6. Growth and layout of a structure

**Rule 1 and Rule 3.** The limit side is the structure's own size or fan-out,
set by earlier growth from the data or by a structural constant; no user sets a
ceiling. The item is stored on both branches, and the "full" branch allocates
**more**. Whatever bounds these structures is upstream.

| If statement | Reason rejected |
|---|---|
| `CompressionMetadata.java:366`; `Walker.java:442`; `AbstractReplicaCollection.java:109`; `HistogramBuilder.java:45`; `ByteSourceInverse.java:424`; `Stack.java:94`; `LongTimSort.java:821` | Grow when full: `size == capacity` or `array.length < required` on the structure's own array; a copy at 1.5–3× or the required length. |
| `InMemoryReadTrie.java:501`; `InMemoryTrie.java:670`; `TriePathReconstructor.java:33`, `:41` | Grow when full, as above. |
| `BTree.java:1538`, `:1573`, `:1600`; `BTreeSet.java:133`, `:477` | Grow when full; `BTreeSet.java:477` trims to a shorter array, and both branches still write every element. |
| `PrunableArrayQueue.java:71` | The internode outbound queue (`OutboundMessageQueue.java:70`); `offer()` always returns `true`. Its bytes are bounded by the filed send-queue case's `acquireCapacity()`. |
| `MmappedRegions.java:383` | Grows only the arrays of region references; the region is mapped at `:379`, before the comparison. |
| `CompressedInputStream.java:144`; `CompressedChecksummedDataInput.java:118`, `:134`; `CompressedHintsWriter.java:53`; `EncryptedChecksummedDataInput.java:126`; `CompressedSequentialWriter.java:247` | A reusable scratch buffer replaced when too small (`buffer.capacity() < required`); the operation proceeds on both branches, sized to one item. `CompressedInputStream`'s buffer serves only chunks below `maxCompressedLength()` (`:142`). |
| `ThreadLocalByteBufferHolder.java:74`; `FrameDecoder.java:393`; `EncryptionUtils.java:134`; `CBUtil.java:105` | Same. The frame stash at `:393` holds one frame whose length is a 17-bit header field (`FrameDecoderCrc.java:79`, `FrameDecoderLZ4.java:73`). |
| `ByteBufferUtil.java:817` | Same; it throws when `allowBufferResize` is false (`:819-820`), but every production caller (via `EncryptionUtils`) passes `true`, so in a node it only grows. |
| `DataOutputBuffer.java:166` `capacity > 1024L * 1024L * DOUBLING_THRESHOLD` | Rule 2, a growth step: switches from doubling to +50 % above `cassandra.DOB_DOUBLING_THRESHOLD_MB` (default 64). |
| `BTree$LeafBuilder.copy():2575`, `:2608`, `.prepend():2700`; `$BranchBuilder.prepend():2956`, `.copyPreceding():3185` `count + length > MAX_KEYS` | Node fan-out (`MAX_KEYS = BRANCH_FACTOR - 1`, from `cassandra.btree.branchshift`); keys spill into the next node. |
| `BTree.java:137`, `:231`, `:2530`, `:2558`, `:2712`, `:2832`, `:3064`; `BTreeRemoval.java:88`, `:90`, `:99` | Splitting, overflowing or redistributing B-tree nodes; all keys stored. |
| helpers `BTree$LeafOrBranchBuilder.isSufficient()`, `mustRedistribute()` | Same. |
| `NativeAllocator.java:166`; `SafeMemoryWriter.java:52`; `BufferPoolAllocator.java:121` | Size a region or resize a buffer.<br>Case file (2026-10-27, estimate negative): [`max_region_size-tryswapregion-minsize`](cases/max_region_size-tryswapregion-minsize--autonomous.md) (`NativeAllocator.java:166`). |
| helper `StreamingTombstoneHistogramBuilder$DataHolder.isFull()` | Merges histogram bins in an array allocated once. |
| `InMemoryTrie.java:145` | The next trie chunk is allocated when the current one is used up. |

## 7. Invariant guards and checks that allocate nothing

**Rule 3.** The memory was spent when the structure was sized, or no branch
allocates. The check throws when a pre-sized structure would overflow, or
decides something other than creation.

| If statement | Reason rejected |
|---|---|
| `MerkleTree.java:1103`, `:1137`, `:1322`, `:1420` `buffer.remaining() < maxOffHeapSize(...)` | The off-heap buffer is already sized for the whole tree; each throws `IllegalStateException` if a node would not fit. |
| `Accumulator.java:60` `insertPos >= values.length` | `values` is a fixed array from the constructor; `add()` only stores a reference. |
| `Accumulator.java:75` | Runs after the item is stored, in the loop that publishes `presentCount` to readers. |
| `SegmentRowIdOrdinalPairs.java:55` `size == capacity` | The `int[]` is allocated once at the size its caller computed (`:45`; `VectorIndexSegmentSearcher.java:164`, `:299`); `add()` throws instead of growing. |
| `StreamingTombstoneHistogramBuilder.java:452`, helper `$Spool.tryAddOrAccumulate()` `size > capacity` | Spool arrays allocated once (`:433-434`); on `false` the caller flushes and retries (`:109-112`). |
| `FrameDecoder.java:375` `bytesToSize > in.remaining()` | `copyToSize()` copies into an existing stash and reports whether the frame is complete. |
| `EncryptionUtils.java:142` `metadataBuffer.remaining() < ENCRYPTED_BLOCK_HEADER_SIZE` | Throws on a short read of the 8-byte block header. |
| `DynamicList.isWellFormed():216` `i + 1 < maxHeight` | Inside an invariant checker walking skip-list levels. |
| `FBUtilities.copy():1291` `limit < buffer.length + copied` | Clamps the next read into a fixed 64-byte buffer. |

## 8. Read validation against the input's own length

**Rule 1.** The limit is the length of what is being read (a row's serialized
size, a hint's size, the bytes left in a message, a block's declared size). It
is data, not a capacity: no setting moves it, and the disallow branch throws on
corrupt or short input.

| If statement | Reason rejected |
|---|---|
| `TrackedDataInputPlus.checkCanRead():184` `limit >= 0 && bytesRead + size > limit` | The only production site that passes a limit is `UnfilteredSerializer.deserializeRowBody():587` with `rowSize` read from the SSTable (`:585`). The other four construction sites (`CassandraStreamReader.java:134`, `CassandraCompressedStreamReader.java:76`, `HintMessage.java:157`, `RowIndexEntry.java:557`) use `limit = -1` (`:40-43`), which disables the guard. |
| `ChecksummedDataInput.checkLimit():161` `getPosition() + length > limit` | A digest-boundary guard that throws.<br>**Trace-back 2026-10-27, rejected (no constraint):** `checkLimit` compares against `limit`, which `HintsReader.readHint` and `readBuffer` set from each hint's own CRC-validated size (`HintsReader.java:234`, `:340`); no setting is involved. |
| `VIntCoding.getUnsignedVInt():162`, `:211` `readerIndex + size > readerLimit` | Bounds reading one vint within a buffer, returning `-1`. |
| `CBUtil.java:457`, `:666`; `EncryptionUtils.java:197` | The bytes left in a message, a block's declared size. |

## 9. Release, reclaim and soft targets

**Rule 3, nothing withheld.** The comparison decides how much to hand back,
when to resume, or when to trigger a flush or reclaim; allocation proceeds on
both branches. A reclaim target can be exceeded, so it is not a ceiling.

| If statement | Reason rejected |
|---|---|

## 10. Count, time, rate and work thresholds

**Rule 2, not a byte ceiling.** The operand counts items of no fixed size
(tasks, rows, hints, SSTables, entries), measures time or rate, or budgets work
done rather than bytes held.

| If statement | Reason rejected |
|---|---|
| `SEPExecutor.java:373`; `SEPWorker.java:165`, `:282`, `:330`, `:342`; `SharedExecutorPool.java:137` | Thread-pool permits: how many tasks run at once. **Re-examine:** the same reasoning was refuted at stage 4 for `concurrent_compactors` (usage = tasks × per-task bytes). `SEPExecutor.java:196` (`takeWorkPermit`, `concurrent_writes`) left this row on 2026-10-21, verified at stage 4 as Confirmed — does not cap ([case](cases/concurrent_writes-takeWorkPermit-workPermits--autonomous.md), `_INDEX.md` §1): excess mutations queue unbounded on the heap, 887.5 MiB at pool size 0. That run tested only `:196` and never made the pool bind under load, so the lines left here stay unverified. **`SEPExecutor.java:165`** (`takeTaskPermit`, pool `maximumPoolSize`) left this row on 2026-10-21 ([case](cases/maximumPoolSize-takeTaskPermit-workPermits--autonomous.md)): unit Confirmed — does not cap (queued heap 125 MiB at every pool size); cluster Not confirmed (BIND-5). That run made the pool bind (Active = v at 1 · 8 · 32 · 128): for **large internode mutations** (> 64 KiB, deserialized only when a worker runs them) heap follows running tasks × per-task bytes (live +5.5 → +70.2 MiB) while the queue waits off heap, bounded by the receive reserve; small mutations are flat. So the queue is uncapped at `:196` and `:165`, and the `concurrent_compactors` pattern holds for heap on the large-message path only. `ReadStage` and `Native-Transport-Requests` have no binding test yet. |
| `PartitionDenylist.java:419`, `:445` `results.size() > limit` | Rule 3 too: the result set is fully built before the check, which then logs and truncates. |
| `DataLimits.java:993`, `:1000`, `:1041` (2 units); helpers `GroupByAwareCounter.isDone()`, `isDoneForPartition()` | Same: the query's limits or page size.<br>`DataLimits.java:1041`: estimate changed to **positive** at the 2026-10-27 write-up; its entry is now in [`predicted-positive.md`](predicted-positive.md) (case file [`default_page_size-cqlgroupbylimits_onclose-rowlimit`](cases/default_page_size-cqlgroupbylimits_onclose-rowlimit--autonomous.md)). |
| `ExpirationDateOverflowHandling.java:82` `ttl + nowInSecs > ...MaxDeletiontionTime()` | A timestamp-overflow guard (CASSANDRA-14092). |
| `ContentionStrategy.java:401` `minWaitMicros + minDeltaMicros > maxWaitMicros` | Microsecond back-off arithmetic. |
| `RepairTokenRangeSplitter.java:312`, `:360` `... < maxBytesPerSchedule` | Repair work per schedule: bytes examined, a throughput budget. `:312` only chooses to merge assignments. |
| `RepairTokenRangeSplitter.java:238`; `AutoRepair.java:459` | Repair scheduling counts. |
| helpers `AutoRepairUtils.keyspaceMaxRepairTimeExceeded()`, `tableMaxRepairTimeExceeded()` | Elapsed repair time. |
| `ActiveRepairService.java:641`, helper `verifyCompactionsPendingThreshold()` | A count of pending compactions. |
| `MigrationCoordinator.java:290` | Outstanding schema pulls. |
| `StreamSession.java:989` | A stream count. |
| `CQLMessageHandler.java:345#2`, `:408` | Consecutive protocol errors. |
| helper `StartupClusterConnectivityChecker$AckMap.incrementAndCheck()` | A count of acks. |
| `DiagnosticSnapshotService.java:147` | Snapshot ranges. |
| `TopPartitionTracker.java:239` | A top-*N* report per table (`max_top_size_partition_count`, default 10): negligible. |
| `LogMessagesTable.java:193`; `VirtualTableAppender.java:125` | The logs virtual table keeps at most `cassandra.virtual.logs.max.rows` messages (default 50,000) and evicts the oldest; the appender is off in the shipped `logback.xml`. Entries are unsized.<br>Case file (2026-10-27, estimate negative): [`logs_virtual_table_default_rows-addtobuffer-messagebuffer_size`](cases/logs_virtual_table_default_rows-addtobuffer-messagebuffer_size--autonomous.md) (`VirtualTableAppender.java:125`). |
| `DiagnosticEventMemoryStore.java:56` | Keeps 200 events; diagnostics are off by default.<br>Estimate changed to **positive** at the 2026-10-27 write-up; its entry is now in [`predicted-positive.md`](predicted-positive.md) (case file [`diagnostic_event_memory_store_max_size-store-keyhead`](cases/diagnostic_event_memory_store_max_size-store-keyhead--autonomous.md)). |
| `Ref.java:435`; `LightweightRecycler.java:69` `pool.size() < capacity()` | A recycler pool of 1,024 objects: keep or leave to GC; negligible and not tunable. |
| `LimitingRebufferer.java:55`, `:58` | Permits from a `RateLimiter` per chunk (compaction and streaming throughput): speed, not bytes. |

## 11. Selection and strategy

**Rule 2 / Rule 3.** The comparison chooses which items to work on, or how, not
whether an object is created.

| If statement | Reason rejected |
|---|---|
| `LeveledCompactionTask.java:95` `l0SSTableCount > 1` | Which SSTable is treated as "largest" for splitting. |
| `CompactionTask.java:479`; `LeveledManifest.java:371` | A running maximum (oldest, latest). |
| `UnifiedCompactionStrategy.java:617`, `:671`, `:768`, `:782`; `Overlaps.java:205` | Which SSTables to compact and how to bucket them. |
| `unified/Controller.java:305` `count > MAX_SHARD_SPLIT` | Clamps a shard-split count; compaction proceeds with fewer shards.<br>Case file (2026-10-27, estimate negative): [`max_shard_split-getnumshards-count`](cases/max_shard_split-getnumshards-count--autonomous.md). |
| `AtomicBTreePartition.java:272`, helpers `updateWastedAllocationTracker()`, `useLock()` | Switches a hot partition from CAS to a lock once wasted allocation passes 10 MiB per interval: a concurrency strategy.<br>Case files (2026-10-27, estimate negative): [`excess_waste_bytes-updatewastedallocationtracker-wastedbytes-2`](cases/excess_waste_bytes-updatewastedallocationtracker-wastedbytes-2--autonomous.md) (`:272`), [`excess_waste_bytes-updatewastedallocationtracker-wastedbytes`](cases/excess_waste_bytes-updatewastedallocationtracker-wastedbytes--autonomous.md) (`updateWastedAllocationTracker()`), [`excess_waste_bytes-uselock-wastetracker`](cases/excess_waste_bytes-uselock-wastetracker--autonomous.md) (`useLock()`). |
| `StreamSession.java:894`, `:913` | Skip empty stream summaries before the disk check. |
| helper `StandaloneSplitter.isSSTableLargerEnough()` | The offline `sstablesplit` tool. |

## 12. Emptiness, sentinel and enabled tests

**Rule 1, no limit compared.** An empty input, a capacity of `0` meaning "off"
or "unthrottled", a CAS or tracker sentinel, a reference count reaching zero.

| If statement | Reason rejected |
|---|---|
| `CompactionTask.java:318` `count == 0` | Early return on an empty input set. |
| `QueryProcessor.java:251`; `Validation.java:47`; `UDFDataType.java:177` | An empty key or value.<br>**Trace-back 2026-10-27, rejected (no constraint):** `QueryProcessor.java:251` is `key == null` or `key.remaining() == 0` ("Key may not be empty"; compared with the literal 0); the adjacent size check at `:259` uses `FBUtilities.MAX_UNSIGNED_SHORT`, see §3.<br>**Trace-back 2026-10-27, rejected (no constraint):** `Validation.java:47` is the same empty-key test (`key == null` or `key.remaining() == 0`, `Validation.java:48` throws); the literal 0, no setting.<br>**Trace-back 2026-10-27, rejected (no constraint):** `UDFDataType.java:177` in `compose` tests `buffer == null` or (`buffer.remaining() == 0` and `isEmptyValueMeaningless()`): null/empty bookkeeping. |
| `StorageAttachedIndex.java:791`; `SSTableIndexWriter.java:221`; `SegmentBuilder.java:260` | An empty term or index.<br>**Trace-back 2026-10-27, rejected (no constraint):** `SSTableIndexWriter.java:221` is `term.remaining() == 0 && skipsEmptyValue()`: a data-validity check on the column type.<br>**Trace-back 2026-10-27, rejected (not a memory/disk cap):** `SegmentBuilder.java:260` is only `getRowCount() == 0`; the real comparison is `:266`, `ssTableRowId - segmentRowIdOffset > lastValidSegmentRowID` against `LAST_VALID_SEGMENT_ROW_ID` = `(Integer.MAX_VALUE/2)-1` (`SegmentBuilder.java:46`), a hard-coded per-segment row-id cap, not settable. |
| `ColumnFamilyStore.java:2501`, `:2508`, helpers `isCounterCacheEnabled()`, `isRowCacheEnabled()` | Cache on or off; the caches' capacities are enforced inside the cache implementations. |
| `CounterMutation.java:213`; `MonitoringTask.java:221`; `ThrottledUnfilteredIterator.java:234` | `0` meaning off or unthrottled. |
| `AtomicBTreePartition.java:283`, `:300` (2 units); `NativeAllocator.java:194` | CAS or tracker sentinels.<br>**Trace-back 2026-10-27, rejected (no constraint):** `AtomicBTreePartition.java:300` (`avoidReservedValues`) only keeps the tracker value off the sentinels `TRACKER_NEVER_WASTED` and `TRACKER_PESSIMISTIC_LOCKING` (`:57-58`).<br>**Trace-back 2026-10-27, rejected (no constraint):** `NativeAllocator.java:194` asserts `region.allocate(size) != -1` for a region created with capacity equal to `size` (`:190`); the nearby `MAX_CLONED_SIZE` (128 KiB, `:47`) only routes large allocations. |
| `ClientResourceLimits.java:176` | A sentinel test. |
| helper `CQLSSTableWriter$Builder.isMaxSSTableSizeUnset()` | An unset option. |

## 13. Not production code

| If statement | Reason rejected |
|---|---|
| `BlockingQueues.java:69`, `:81`, helper `BlockingQueues$Sync.offer()` `wrapped.size() == capacity` | `BlockingQueues.Sync` is built only by the simulator (`InterceptorOfGlobalMethods.java:393`); in a node `newBlockingQueue` returns a JDK `LinkedBlockingQueue` (`:43-47`). The capacities passed in belong to their callers. |
| `DynamicList.java:113` `size >= maxSize` | Built only by its own `main()` (`:231`); the `Node` is also allocated at `:112`, before the check. |

## 14. Whole-package surveys

| If statement | Reason rejected |
|---|---|
| `cache/` (`AutoSavingCache`, `CaffeineCache`, `ChunkCache`, `NopCacheProvider`, `RefCountedMemory`, `SerializingCache`; 15 rows) | Reference counting (`refCount == 0`), `int`-overflow guards (`size > Integer.MAX_VALUE`, e.g. `CaffeineCache.java:65`, `SerializingCache.java:71`, `:94`) and cache-save bookkeeping (`AutoSavingCache.java:305#2`, `:388`). No capacity comparison gates creation. |
| `db/compaction/` (all 208 rows not listed above) | Three patterns: SSTable selection and levelling (`LeveledManifest`, `SizeTieredCompactionStrategy`, `TimeWindowCompactionStrategy`, `ShardManager*`); writer switch on full (`CompactionAwareWriter.maybeSwitchLocation`, `MajorLeveledCompactionWriter`, `SplittingSizeTieredCompactionWriter`, `Sharded*Writer`), a rollover ([§4](#4-rollover-and-chunking)); and option validation (`validateOptions()` in every strategy). |

## Observations for Target 3

Not checks to file: findings from the reads above where usage can exceed or
escape a configured value.

- **Soft targets.** `commitlog_total_space` ([§9](#9-release-reclaim-and-soft-targets)),
  `segment_write_buffer_size` ([§4](#4-rollover-and-chunking)), SASI's
  `max_flush_memory` and the trie memtable threshold (below) trigger a flush or
  reclaim instead of refusing, so none is a ceiling. They are the likeliest
  places for "usage exceeds the configured value".
- **One property, two units.** The trie memtable's per-shard size threshold
  (default 2048 × 10 / 11 MiB; reaching it schedules a flush,
  `TrieMemtable.java:192-195`) is read from the JVM property
  `cassandra.memtable.row_overhead_size` (`InMemoryTrie.java:63`,
  `CassandraRelevantProperties.java:356`). `SkipListMemtable` reads the same
  property as its per-row heap overhead **in bytes** (`SkipListMemtable.java:75-77`).
  Setting it to 200 to tune one makes every trie memtable flush at 200 MiB per
  shard, and a value above 2047 stops `InMemoryTrie` from initialising
  (`AssertionError`, `:64-66`).
- **Retained high-water buffers have no limit.** Four reusable thread-local
  buffers (`ThreadLocalByteBufferHolder`, `CBUtil`'s `TL_CHAR_BUFFER`, and the
  `reusableBuffers` of `EncryptionUtils` and `EncryptedChecksummedDataInput`) grow
  to the largest item their thread has handled and never shrink. The one cap on
  this kind of retention found so far is the filed `DOB_MAX_RECYCLE_BYTES` case.
