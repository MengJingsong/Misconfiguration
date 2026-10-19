# Stage 3 — lines considered and rejected

Lines read **with the Cassandra source open** and refused against the three
rules ([`../README.md` §3.4–§3.6](../README.md#3-core-concept-the-if-check-case)).
This is the stage-3 rejection store; it moved here from `_INDEX.md` when the
stage folders were introduced (2026-09-23).

**Decided 2026-10-19: a rejection is written up as a case file.** Every entry below
has no case file yet and is a queue: each is to be written up in `cases/` (by either
agent, with the judgment `rejected` or `does not cap`) with a verification solution
that tests that usage does not follow the constraint. When the file lands, the
entry here is replaced by a one-line pointer to it and `_INDEX.md` gets a row. New
rejections go straight to a case file and need no entry here.

**This is the only rejection file in the experiment, and it is
authoritative for every rejection.** Stage 2 cannot reject — it gives a hopeless
row the bottom band instead — so every refusal here was made with the source
open. A stage-2 `negatives.md` held row-level rule-outs until stage 2 stopped
rejecting on 2026-09-23; it was deleted on 2026-09-24 and its rows carry band
D in `../stage2-ai-preprocessing/bands.csv`, with the per-helper arguments in
git history at `43a3c27`.

A line is recorded in exactly one place. If stage 2 reaches a line stage 3
already judged, cite the entry here rather than re-recording it.

_Track if-checks that were examined but don't qualify (no branch divergence
on object creation, pure validation, etc.), so later passes don't re-examine
them._

| Location | Reason rejected |
|----------|------------------|
| `AbstractCompactionStrategy.java:456` (`thresholdValue < 0`) | Config-value validation (throws on negative input), not a runtime object-creation gate. |
| `LeveledCompactionTask.java:95` (`l0SSTableCount > 1`) | Selects which SSTable to treat as "largest" for splitting; doesn't gate whether an object gets created. |
| `LeveledCompactionStrategy.java:78,81` (`configuredMaxSSTableSize` bounds) | Startup config-value validation/clamping, not a runtime allocation check. |
| `LeveledCompactionStrategy.java:580,597` (`ssSize < 1`, `fanoutSize < 1`) | Config-value validation (throws `ConfigurationException`). |
| `CompactionTask.java:318` (`count == 0`) | Early-return on empty input set, not a capacity/limit comparison. |
| `CompactionTask.java:479` / `LeveledManifest.java:371` (`max` tracking) | Plain running-max computation (finding oldest/latest), not a capacity limit. |
| `SizeTieredCompactionStrategyOptions.java:73` (`minSSTableSize < 0`) | Config-value validation. |
| `SSTableSplitter.java:52` (`sstableSizeInMB <= 0`) | Input-argument validation for a CLI tool, not a runtime gate. |
| `unified/Controller.java:202,268,381,385,499,504,529,609` | All are config/derived-value validation or arithmetic branches for computing target SSTable size — none diverge into "create vs. block" for an object. |
| `unified/Controller.java:305` (`count > MAX_SHARD_SPLIT`) | Clamps a shard-split count downward (`count = MAX_SHARD_SPLIT`), doesn't block object creation — compaction proceeds either way, just with fewer shards. |
| `TimeWindowCompactionStrategyOptions.java:126` (`sstableWindowSize < 1`) | Config-value validation. |
| `UnifiedCompactionStrategy.java:617,671,768,782` | Bucket-selection/candidate-picking logic (choosing which SSTables to compact), not a resource-creation vs. reject divergence. |
| `CompactionManager.java:245` (`concurrent_compactors`, `submitBackground()`) | **Written up 2026-10-19:** [`cases/concurrent_compactors-submitBackground-getMaximumPoolSize--guided.md`](cases/concurrent_compactors-submitBackground-getMaximumPoolSize--guided.md). Recorded ground: Fails Rule 2 (see README § Core concept): limit-side operand is `executor.getMaximumPoolSize()`, a thread-pool size. Changing `concurrent_compactors` changes how many compactions run *concurrently* (speed/throughput), not the total bytes memtable/compaction machinery can hold — the allocations a compaction task performs once running are unaffected by this cap. Case file drafted then removed once this rule was adopted. |
| `CommitLogSegment.java:246` (`next >= endOfBuffer`) — *line corrected 2026-09-28, recorded as `:242`* | Doesn't diverge on object creation — the "full" branch creates a *new* segment rather than blocking/rejecting; same non-diverging pattern as prior compaction rejects. |
| `HintsBuffer.java:190` (`(prev+totalSize) > slab.capacity()`) | Same non-diverging pattern — the "full" branch triggers allocation of a new buffer rather than blocking/rejecting. |
| `BatchStatement.java:352` (`verifyBatchSize()`, `size > failThreshold`) — *line corrected 2026-09-28, recorded as `:349`* | **Written up 2026-10-19:** [`cases/batch_size_fail_threshold-verifyBatchSize-failThreshold--guided.md`](cases/batch_size_fail_threshold-verifyBatchSize-failThreshold--guided.md). Recorded ground: Runs after the batch's mutations are already fully constructed — doesn't gate object creation, only rejects an already-built batch post hoc. |
| `SEPExecutor.java:135,165,175,196,373,384` / `SEPWorker.java:165,282,330,342` / `SharedExecutorPool.java:137` (task/work permit checks) | Thread-pool worker/permit concurrency accounting, same as `concurrent_compactors` — bounds how many tasks run concurrently, not the bytes any task allocates. |
| `Dispatcher.java:345` (`hasQueueCapacity()`, `oldestTaskQueueTime() < timeout*threshold`) | **Written up 2026-10-19:** [`cases/native_transport_queue_max_item_age_threshold-hasQueueCapacity-oldestTaskQueueTime--guided.md`](cases/native_transport_queue_max_item_age_threshold-hasQueueCapacity-oldestTaskQueueTime--guided.md) (line is `:348` in the pinned tree). Recorded ground: Time-based (item age in queue), not a byte/capacity comparison — fails Rule 2. |
| `ConnectionLimitHandler.java:93,121` (`count > limit`, per-IP/global connection count caps) | **Written up 2026-10-19:** [`cases/native_transport_max_concurrent_connections-channelActive-limit--guided.md`](cases/native_transport_max_concurrent_connections-channelActive-limit--guided.md). Recorded ground: Bounds concurrent *connection count*, not bytes; per-connection memory footprint isn't fixed/derivable at this check, and the actual byte-level enforcement for CQL traffic is the separate `native_transport_receive_queue_capacity`/`native_transport_max_request_data_in_flight` mechanism (see `deferred.md`'s parked candidate). Deferred rather than firmly rejected — revisit if a fixed per-connection footprint can be derived. |
| `CQLMessageHandler.java:551` (`messageSize > getNativeTransportMaxMessageSizeInBytes()`) | **Written up 2026-10-19:** [`cases/native_transport_max_message_size-processFirstFrameOfLargeMessage-maxMessageSize--guided.md`](cases/native_transport_max_message_size-processFirstFrameOfLargeMessage-maxMessageSize--guided.md) (the write-up's source reading disagrees with the ground below; see its §10). Recorded ground: Rejects a single oversized frame outright (protocol/sanity bound on one message), not a running-total capacity check — distinct from the `queueCapacity`-based candidate, since promoted to a case file (see `../stage2-ai-preprocessing/bands.md`). |
| `Flusher.java:152,183,282,303,332,345` (`MAX_FRAMED_PAYLOAD_SIZE`, flush-buffer bookkeeping) | Governs how outbound response bytes are chunked/framed for writing, not a cap on how much gets allocated — buffers are sized to the response regardless of branch taken. |
| `cache/` subpackage (`AutoSavingCache`, `CaffeineCache`, `ChunkCache`, `NopCacheProvider`, `RefCountedMemory`, `SerializingCache`) | Surveyed in full (15 rows) — ref-counting (`refCount == 0`), `int`-overflow guards (`size > MAX_VALUE`), and cache-save bookkeeping; no capacity-vs-limit divergence gating new object creation found. |
| `db/compaction/` subpackage, remaining files not already logged above (208 rows total, full subpackage now surveyed) | Extends the earlier informal compaction survey's conclusion to every file in the subpackage. Three recurring non-qualifying patterns account for nearly all rows: (1) **SSTable-candidate selection/threshold logic** (`LeveledManifest`, `UnifiedCompactionStrategy`, `SizeTieredCompactionStrategy`, `TimeWindowCompactionStrategy`, `ShardManager*`) — comparisons that choose *which* SSTables to compact or how to bucket/level them, not a create-vs-block divergence. (2) **Writer-switch-on-full** (`CompactionAwareWriter.maybeSwitchLocation`, `MajorLeveledCompactionWriter`, `SplittingSizeTieredCompactionWriter`, `Sharded*Writer`, e.g. `totalWrittenInCurrentWriter > maxSSTableSize`) — same non-diverging "start a new writer instead of blocking" pattern already rejected for `CommitLogSegment.java:242`/`HintsBuffer.java:190` (writing proceeds regardless of branch) — rejected under Rule 2's writer-rollover edge case even with disk now in scope, since total bytes written aren't bounded, only their chunking. (3) **Config validation / arithmetic derivation** (`validateOptions()` methods across every strategy, `Controller.java`'s remaining rows) — startup-time checks or plain derived-value math, not runtime allocation gates. No candidate survived from these three patterns. **`CompactionAwareWriter.getWriteDirectory():282`** (`availableSpace < estimatedWriteSize`) was rejected here as disk-scoped/out-of-scope — **reclassified as a live candidate 2026-09-18** once disk was brought into this folder's scope (README § Core concept); now parked in `deferred.md` as pattern (c), per the 2026-09-22 scope decision (README §7.5). |

## Batch: the capacity-word pass, corpus-wide — 2026-09-22

Deep read of its 34 rows — those with a capacity word on either side **and** a
compound usage side. (This was the top tier of the keyword scale that stage 2
used until 2026-09-23, when the scale was dropped for the A–D bands; the pass
and its verdicts stand, only the label is retired.) **22 rows rejected**, grounds below. The other 12: 4 candidates
(`pending.md`), 3 rows deferred as pattern (b)/(c) (`deferred.md`), 5
already covered by existing records.

These are **source-level rejections** — the pass applied the three rules
with the code open, unlike a stage-2 row-level pass.

**15 table rows, 22 corpus rows** — three entries cover several lines each
(BTree 5, `DataLimits` 3, `VIntCoding` 2); the rest are one row apiece.

| Row | Check | Ground |
|---|---|---|
| `NativeAllocator$Region.allocate():273` | `newOffset + size > capacity` | Rule 2, writer-rollover. On failure the caller `trySwapRegion()` allocates a **new** region (`new Region(MemoryUtil.allocate(size), size)`), so total bytes are not bounded — only chunked. The real memtable ceiling is the already-filed `MemtablePool.tryAllocate()`. |
| `SlabAllocator$Region.allocate():201` | `newOffset + size > data.capacity()` | Rule 2, same archetype — returns `null`, caller creates a new region. |
| `MmappedRegions.updateState():208` | `segmentSize + chunk.length + 4 > MAX_SEGMENT_SIZE` | Rule 2, chunking. Starts a new mmap segment at the boundary; the whole file is mapped either way, just in more segments. |
| `BTree$LeafBuilder.copy():2575`, `:2608`, `.prepend():2700`, `$BranchBuilder.prepend():2956`, `.copyPreceding():3185` | `count + length >/<= MAX_KEYS` | Rule 2, node fanout. `MAX_KEYS = BRANCH_FACTOR - 1` is a structural tree parameter; over it the keys spill into an overflow/next node. All data is stored either way. 5 rows, one judgement. |
| `IncrementalTrieWriterPageAware.complete():167` | `nodeSize + branchSize < maxBytesPerPage` | Rule 2, page packing. Decides node placement within pages; everything is written regardless. |
| `DataLimits$CQLCounter.incrementRowCount():509`, `:511`, `$GroupByAwareCounter:986` (3 rows) | `++rowsCounted >= rowLimit`, `>= perPartitionLimit` | Rule 2. CQL query `LIMIT` semantics, not a resource constraint: per-row footprint is not fixed or derivable, and the limit is user-supplied per query rather than a system capacity. |
| `ExpirationDateOverflowHandling.maybeApplyExpirationDateOverflowPolicy():82` | `ttl + nowInSecs > getVersionedMaxDeletiontionTime()` | Rule 2, time-based. A timestamp-overflow guard (CASSANDRA-14092); bounds no bytes. |
| `MutationExceededMaxSizeException.makeTopKeysString():76` | `stringBuilder.length() + key.length() + 2 <= maxLength` | Rule 2, not memory-significant. Truncates the key list inside a diagnostic error message. |
| `ChecksummedDataInput.checkLimit():161` | `getPosition() + length > limit` | Rule 3. A digest-boundary guard that throws; gates no object creation. |
| `VIntCoding.getUnsignedVInt():162`, `:211` (2 rows) | `readerIndex + size > readerLimit` | Rule 3. Bounds reading a vint within a buffer, returning `-1`; nothing is allocated either way. |
| `ContentionStrategy.computeWaitUntilForContention():401` | `minWaitMicros + minDeltaMicros > maxWaitMicros` | Rule 2, time-based. Microsecond back-off arithmetic. |
| `DynamicList.isWellFormed():216` | `i + 1 < maxHeight` | Rule 3. Inside an invariant checker walking skip-list levels; not an allocation gate. |
| `FBUtilities.copy():1291` | `limit < buffer.length + copied` | Rule 3. Clamps the next read size into a fixed 64-byte buffer; no divergence in object creation. |
| `RepairTokenRangeSplitter.getRepairAssignmentsForKeyspace():312` | `currentAssignmentsBytes + tableAssignmentsBytes < maxBytesPerSchedule` | Rule 2/3, bucketing. Chooses whether to merge assignments or add them separately — they are added either way. |
| `RepairTokenRangeSplitter.filterRepairAssignments():360` | `bytesSoFar + getEstimatedBytes() > maxBytesPerSchedule` | Rule 2. Bounds the volume of repair *work* scheduled, not bytes resident or written by an allocation. |

## Batch: clearing the deferred (b)/(c) queue — 2026-09-28

The three entries parked in [`deferred.md`](deferred.md) §1b/§1c, read against
the three rules now that all patterns are in scope (README §7.5). Two
qualified and are filed as cases; **one is refused here.** The §2 re-audit
remains scheduled, folded into the band-A pass.

| Row | Check | Ground |
|---|---|---|
| `TrackedDataInputPlus.checkCanRead():184` | `limit >= 0 && bytesRead + size > limit` | **Rule 1, and Rule 2.** `limit`'s origin was the open question that kept this parked; it is settled. The only production site that passes a limit at all is [`UnfilteredSerializer.deserializeRowBody():587`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/rows/UnfilteredSerializer.java#L587), `new TrackedDataInputPlus(in, rowSize)`, where `rowSize` is `in.readUnsignedVInt()` read at [`:585`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/rows/UnfilteredSerializer.java#L585) — **the row's own serialized length, read out of the SSTable being deserialized.** It is therefore data, not a capacity: it is not configured, not constant, not a type bound, and not a runtime-queried resource figure, and it varies per row. Rule 1 asks the limit-side operand to represent a capacity; a per-record stream framing boundary does not. Rule 2 fails consequently — there is no value an operator or the build can change that would move the maximum bytes resident, because a larger row simply arrives with a larger `limit`. The guard's actual purpose is corruption safety: stop a malformed length field from reading past the end of one row's body. Same archetype as the already-rejected [`ChecksummedDataInput.checkLimit():161`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/hints/ChecksummedDataInput.java#L161) and `VIntCoding.getUnsignedVInt()` above. **Second, independent ground:** the other four production construction sites — [`CassandraStreamReader.java:134`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/streaming/CassandraStreamReader.java#L134), [`CassandraCompressedStreamReader.java:76`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/streaming/CassandraCompressedStreamReader.java#L76), [`HintMessage.java:157`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/hints/HintMessage.java#L157), [`RowIndexEntry.java:557`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/io/sstable/format/big/RowIndexEntry.java#L557) — all use the single-argument constructor, which sets `limit = -1` ([`:40-43`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/io/util/TrackedDataInputPlus.java#L40-L43)) and so disables the guard entirely via the `limit >= 0` conjunct. The class is a **byte-counter** first and a bounded reader only incidentally. Checked 2026-09-28. |

**Worth carrying forward.** This is the first entry refused on **Rule 1** —
every previous rejection failed Rule 2 or Rule 3. The distinction is useful for
the band-A pass: a comparison can be perfectly shaped like a capacity check,
with a compound usage side and an operand literally named `limit`, and still
have no constraint on the limit side at all. The question to ask is not "is
this a limit?" but "**where does this number come from, and what could change
it?**" If the answer is "the data being read", it fails at Rule 1 and the
other two rules never need to be reached.

## Batch: band A1, the first stage-3 pass over stage 2's queue — 2026-09-28

The 65 A1 rows from
[`../stage2-ai-preprocessing/bands.md`](../stage2-ai-preprocessing/bands.md)
(feed **3a**), read with the source open. The 65 split **21 pending, 34
rejected, 10 deferred**; rows already recorded by earlier passes were cited
rather than re-judged and are counted in the bucket of that earlier record.
**39 were newly judged** here: 10 pending (8 qualifying rows plus 2 second
check sites), **26 refused below**, grouped by the argument that refuses them
(several rows share one judgement), and 3 undecided in
[`deferred.md`](deferred.md) §5. The other 26 were recorded earlier: 11
pending, 8 rejected, 7 deferred. (Counts corrected 2026-10-01; this section
previously said 21 / 8 / 3 / 33. Row-by-row split:
[A1 disposition table](#a1-disposition-table--all-65-rows) below.)

**A1's hit rate is 8/39 newly-judged rows** (65 − 26 already recorded). Stage 2 promised only a reading
order and that is what it delivered: band A1 is dense with real
usage-vs-limit comparisons, and most of them still fail Rule 2 or Rule 3.

| Row(s) | Check | Ground |
|---|---|---|
| `Message.java:817`, `OutboundConnection.java:331`, `:793`, `:979` (4 rows) | `messageSize > getInternodeMaxMessageSizeInBytes()` | **Rule 2, per-item sanity bound.** Rejects one oversized message; the *total* outbound memory is bounded by `internode_application_send_queue_capacity` and its reserves, not by this. Raising `internode_max_message_size` alone does not move any maximum — the queue cap still binds. Same archetype as `CQLMessageHandler.java:551` above. At `:979` the check sits **after** `new AsyncMessageOutputPlus(...)`, so it does not even gate that allocation. |
| `HintsBuffer.java:152` | `totalSize > slab.capacity() / 2` | **Rule 2, same archetype.** Throws for a single oversized hint. The hints ceiling is `MAX_ALLOCATED_BUFFERS × bufferSize` — a filed case — and this comparison does not move it. |
| `QueryProcessor.java:825` | `getSizeOfPreparedStatementForCache(...) > capacityToBytes(getPreparedStatementsCacheSizeMiB())` | **Rule 2.** Refuses to cache a statement larger than the *whole* cache. The cache's own capacity (a Caffeine weigher over the same config) is what bounds total heap; this is the degenerate single-item case of it, not an independent ceiling. |
| `AbstractMessageHandler.java:464`, `OutboundConnection.java:449` (2 rows) | `queueSize > queueCapacity` / `pendingBytes(prev) > pendingCapacityInBytes` | **Rule 3, release-path accounting.** Both sit in `releaseCapacity()` and decide how much of a borrowed reserve to hand back. No allocation is gated in either branch — the bytes have already been released. The acquiring comparisons in the same classes are the real checks and are filed cases / `pending.md`. |
| `HintsWriteExecutor.java:247` and helper `flushInternal()` | `session.position() >= maxHintsFileSize` | **Rule 2, writer rollover.** Returns `false` so the caller rolls to a new hints file. Every hint is still written, just split across more files — the edge case README §3.5 names explicitly. |
| `HintsWriter.java:237` | `totalSize > buffer.remaining()` | **Rule 2, buffer rollover**, and inverted: the disallow side flushes and may `ByteBuffer.allocate(totalSize)` a **dedicated** buffer for the hint. The branch that "fails" allocates more, not less. |
| `SSTableSimpleUnsortedWriter.java:110` | `currentSize > maxSStableSizeInBytes` | **Rule 2, writer rollover** — triggers `sync()` and a new SSTable. Bulk-loader class; all rows are written regardless. |
| `PerSSTableIndexWriter.java:247` | `currentBuilder.estimatedMemoryUse() < maxMemorySize` | **Rule 2, rollover.** Crossing the threshold submits a segment flush and starts a new builder; every token was already added to the builder before the comparison. `maxMemorySize` is also half-hardcoded — `1GiB` for flush, the per-index `maxCompactionFlushMemoryInBytes` otherwise ([`:365-369`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/index/sasi/disk/PerSSTableIndexWriter.java#L365-L369)). |
| `OnDiskIndexBuilder.java:167`, `PerSSTableIndexWriter.java:218`, `TrieMemIndex.java:84` (3 rows) | `term.remaining() >= MAX_TERM_SIZE` | **Rule 2, per-item constant bound.** `MAX_TERM_SIZE` is a hardcoded `Short.MAX_VALUE`, not configuration — stage 2's reason ("configured max term size") is wrong on the row. Skipping one oversized term bounds no total: every other term is still indexed, and the index's memory is bounded by `maxMemorySize` above. Three rows, one judgement. (All three are SASI, deprecated in 5.0.) |
| `SequentialWriter.java:227` | `bytesSinceTrickleFsync >= trickleFsyncByteInterval()` | **Rule 2, I/O scheduling.** Triggers an fsync at a byte interval. Governs *when* data is forced to disk, not how much is written or held. |
| `RowIndexEntry.java:403` | `estimatedMemory > warnThreshold.toBytes()` | **Rule 3, logging-only branch.** The warn twin of the qualifying fail threshold at `:392`: it records a parameter for the client warning and continues. Nothing diverges on object creation. |
| `PartitionDenylist.java:419`, `:445` (2 rows) | `results.size() > limit` | **Rule 3, post hoc**, plus Rule 2. The CQL result set is fully materialized before the comparison, which then logs a violation and truncates — the heap was already spent. The operand is also a *count* of variable-size partition keys, so total bytes are not `count × fixed size`. Same shape as `BatchStatement` below. |
| `StorageProxy.java:1592` | `totalHintsInProgress > maxHintsInProgress` | **Rule 2, in-flight count cap.** Despite the comment ("avoid OOMing due to excess hints") the operand is a count of in-flight hints with no fixed per-hint footprint — the same reasoning as `concurrent_compactors` and the thread-pool rows above. The byte-level hint bounds are the filed `MAX_HINT_BUFFERS` case and the `max_hints_size_per_host` candidate in `pending.md`. |
| `HeapUtils.java:115` | `freeSpaceBytes < 2 * maxMemoryBytes` | **Rule 2, one-off diagnostic precondition.** Refuses to start a heap dump unless the disk can hold twice the heap. It gates a single diagnostic file, bounds no steady-state usage, and its limit side is the device with no tunable term. Closest precedent: the `SSTableSplitter` CLI validation above. |
| helper `needsCleaning()` (`MemtablePool.java:128`) | `used() > nextClean` | **Rule 3, reclaim trigger.** Crossing `nextClean` (= `limit × memtable_cleanup_threshold`) calls `cleaner.trigger()` to flush the largest memtable. Allocation proceeds in both branches; nothing is withheld. **Record the cross-reference, though:** this soft threshold is why the *hard* limit in the filed `memtable_heap_space` / `memtable_offheap_space` cases is rarely reached in practice, and both of those cases' §9 designs now say to raise `memtable_cleanup_threshold` or the experiment measures this instead. |

### A1 disposition table — all 65 rows

Added 2026-10-01, restructured the same day. Every `bands.md` A1 row appears
once, filed under the bucket its record **started** in: **pending 21,
rejected 34, deferred 10**. "Recorded" is not a bucket — rows recorded by
earlier passes sit in the bucket of that earlier record and are marked
*(recorded)*; rows first judged by the A1 pass are marked *(A1 pass)*.
"Filed" means a pending or deferred row has since become a case file.

| Bucket | Group | Rows | Count |
|---|---|---|---|
| **Pending (21)** | A1 pass — qualifies | `AbstractType:594` (since filed), `Mutation:172` (since filed), `Mutation:451` (since filed), `ReadCommand:715`, `RowIndexEntry:392`, `OutboundConnection:398`, `MerkleTree:409`, `StorageProxy:2492` (since filed) | 8 |
| | A1 pass — second site of a new candidate | `CounterMutation:94` (of `Mutation:172`, since filed), `OutboundConnection:416` (of `:398`) | 2 |
| | *(recorded)* still-open candidates | `QueryController:449` (`MAX_MATERIALIZED_KEYS`, since filed as `SAI_VECTOR_SEARCH_MAX_MATERIALIZE_KEYS`), `TeeDataInputPlus:58` (`TeeDataInputPlus_limit`, since filed as the second site of `CACHEABLE_MUTATION_SIZE_LIMIT`) | 2 |
| | *(recorded)* second site of a filed case | `CommitLogSegmentManagerCDC:200` (`cdc_total_space`), `ResourceLimits:213` (reserve sub-checks of the two `*_receive_queue_capacity` cases) | 2 |
| | *(recorded)* pending → filed | `BufferPool:443`, `MemtablePool:156`, helper `tryAllocate()`, `AbstractMessageHandler:419`, `HintsBufferPool:113`, helper `switchCurrentBuffer()`, `CommitLogSegmentManagerCDC:345` | 7 |
| **Rejected (34)** | A1 pass | `Message:817`, `OutboundConnection:331`, `:793`, `:979`, `HintsBuffer:152`, `QueryProcessor:825`, `AbstractMessageHandler:464`, `OutboundConnection:449`, `HintsWriteExecutor:247`, `HintsWriter:237`, `SSTableSimpleUnsortedWriter:110`, `PerSSTableIndexWriter:247`, `OnDiskIndexBuilder:167`, `PerSSTableIndexWriter:218`, `TrieMemIndex:84`, `SequentialWriter:227`, `RowIndexEntry:403`, `PartitionDenylist:419`, `:445`, `StorageProxy:1592`, `HeapUtils:115`; helpers `flushInternal()`, `needsCleaning()`, `isStillAllocating()`; the two re-cited rows `CommitLogSegment:246`, `BatchStatement:352` | 26 |
| | *(recorded)* own entries above | `HintsBuffer:190`, `CQLMessageHandler:551` | 2 |
| | *(recorded)* `db/compaction/` subpackage entry (selection logic, writer-switch-on-full) | `LeveledManifest:190`, `:557`, `:678`, `MajorLeveledCompactionWriter:75`, `:78`, `SplittingSizeTieredCompactionWriter:84` | 6 |
| **Deferred (10)** | A1 pass — undecided (`deferred.md` §5) | `IndexSummaryRedistribution:341`, `SystemKeyspace:1919`, `ResourceLimits:138` | 3 |
| | *(recorded)* deferred → filed | `Directories:551`, helper `hasDiskSpaceForCompactionsAndStreams()`, `BigFormatPartitionWriter:113`, `:171`, `RowIndexEntry:360`, `CompactionAwareWriter:282`, `Directories:453` | 7 |
| **Total** | | 21 + 34 + 10 | **65** |

Of the 65, 39 were newly judged by the A1 pass (10 pending + 26 rejected +
3 deferred) and 26 were recorded earlier (11 pending + 8 rejected + 7
deferred). Counting only rows that stand alone, the four second-site rows
(two new, two recorded) come out of pending: 17 pending, 61 rows.

### Two line numbers corrected while re-reading

Both rows were already refused; only the citation was wrong. Checked against
the pinned clone 2026-09-28.

| Recorded as | Actually at | Note |
|---|---|---|
| `CommitLogSegment.java:242` (`next >= endOfBuffer`) | **`:246`** | `:242` is the enclosing `while (true)`. Same check, same rejection (writer rollover). Also covers A1's helper row `isStillAllocating()`. |
| `BatchStatement.java:349` (`size > failThreshold`) | **`:352`** | Same check, same rejection (runs after the batch is fully constructed). |

### What A1 taught, for the B and C passes

- **Per-item sanity bounds are the dominant false positive in A1**, and they
  read exactly like capacity checks: a byte count on each side, a config name
  on the limit. The discriminator is Rule 2's own test — *does changing this
  value move a maximum?* For `internode_max_message_size` it does not, because
  a separate queue cap binds; for `max_mutation_size` it does, because the
  commitlog entry, the serialization buffer and the hints buffer all scale
  with it. Ask which value actually binds the total before judging.
- **Rollover is the second.** Five A1 rows are "the current buffer/file/segment
  is full, start another". README §3.5's edge case covers all of them, and
  none needed more than the caller read to settle.
- **Check the release path.** Two rows are the same comparison as a filed case,
  in the `releaseCapacity()` method rather than the acquiring one. Stage 2
  cannot tell them apart from the row; stage 3 settles it in one look.
- **Stage 2's one-line reason can be wrong about the limit's kind.** Three
  rows were described as "configured max term size" for a hardcoded
  `Short.MAX_VALUE`. Trust the row for *where to look*, never for *what the
  limit is*.

## Batch: band A2, constants and structural bounds — 2026-09-29

The 30 A2 rows from
[`../stage2-ai-preprocessing/bands.md`](../stage2-ai-preprocessing/bands.md)
(feed **3a**), read with the source open. **7 were already recorded** and are
cited, not re-judged: `NativeAllocator.java:273`, `SlabAllocator.java:201` and
`MmappedRegions.java:208` (capacity-word pass, above);
`CaffeineCache.java:65`, `SerializingCache.java:71` and `:94` (the `cache/`
subpackage survey, above — all three are `size > Integer.MAX_VALUE`); and
`IndexSummaryBuilder.java:204` (the `Integer_MAX_VALUE` candidate in
[`pending.md`](pending.md)). **No new candidate qualifies.** One row,
`IndexSummaryBuilder.java:108`, joins that existing candidate as a second check
site ([`pending.md`](pending.md)); one, `Envelope.java:429`, is undecided
([`deferred.md`](deferred.md) §6). The remaining **21 are refused below**.

| Row(s) | Check | Ground |
|---|---|---|
| `BlockingQueues.java:69`, `:81`, helper `BlockingQueues$Sync.offer()` (3 rows) | `wrapped.size() == capacity` | **Not production code.** `BlockingQueues.Sync` is constructed only by the simulator, [`InterceptorOfGlobalMethods.java:393`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/test/simulator/main/org/apache/cassandra/simulator/systems/InterceptorOfGlobalMethods.java#L393), which replaces `newBlockingQueue(capacity)` under test. In production that factory returns a JDK `LinkedBlockingQueue` ([`BlockingQueues.java:43-47`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/utils/concurrent/BlockingQueues.java#L43-L47)), so neither line runs in a node. `:81` is also a release path — it `notify()`s from `poll()`. The *capacities* passed to `newBlockingQueue` are real and belong to their callers (e.g. the filed `MAX_HINT_BUFFERS` case), not to this class. |
| `BufferPool.java:1521` | `size == capacity` in `freeUnusedPortion()` | **Rule 3, release path.** Returns early when there is no spare tail to hand back to the chunk. It frees slots; it gates no allocation. |
| `BufferPool.java:910`, `:940` (2 rows) | `size > NORMAL_CHUNK_SIZE` | **Rule 3, path selection.** An oversized request skips the pool (`tryGet` returns `null`) and `get()` calls `allocate(size, OFF_HEAP)` directly. The same bytes are allocated on both branches. This is the uncapped fallback the filed [`file_cache_size`](cases/file_cache_size-allocateMoreChunks-memoryUsageThreshold--guided.md) case already records — useful context there, not a check of its own. |
| `NativeAllocator.java:144`, `SlabAllocator.java:92` (2 rows) | `size > MAX_CLONED_SIZE` | **Rule 3, path selection.** An oversized value is allocated on its own (`allocateOversize`, or a dedicated `Region`) instead of inside the current region. The bytes are already charged to the memtable pool **before** the comparison ([`NativeAllocator.java:141`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/utils/memory/NativeAllocator.java#L141), [`SlabAllocator.java:89`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/utils/memory/SlabAllocator.java#L89)); that charge is the filed `memtable_*_space` cases. Stage 2's reason ("rejecting the on-heap clone") is wrong — nothing is rejected. |
| `NativeCell.java:100`, `OffHeapBitSet.java:43`, `DataOutputBuffer.java:152` (3 rows) | `size > Integer.MAX_VALUE`, `wordCount > Integer.MAX_VALUE`, `saturatedSize <= capacity()` | **Rule 2, per-item type bound.** Each throws when **one** object would pass a Java `int`/array limit: one native cell over 2GiB, one bloom filter over 16GiB, one `DataOutputBuffer` that can no longer grow past `MAX_ARRAY_SIZE`. None bounds a total — every other cell, filter or buffer is unaffected — and none can be changed by a user. The check turns an overflow into a clean exception. Same archetype as the `cache/` rows above. *Contrast with `IndexSummaryBuilder.java:204` in `pending.md`:* that type bound caps a structure that grows with data volume, and its disallow degrades and continues; these three are single-allocation guards that throw. |
| `MmappedRegions.java:170` | `compressedFileLength - state.length <= MAX_SEGMENT_SIZE` | **Rule 2, chunking** — the same judgement as `:208` above. It picks which `updateState` overload splits the file into mmap segments; the whole file is mapped either way. |
| `MerkleTree.java:1103`, `:1137`, `:1322`, `:1420` (4 rows) | `buffer.remaining() < maxOffHeapSize(...)` | **Rule 3, invariant guard.** The off-heap buffer is already allocated and sized for the whole tree; each line throws `IllegalStateException` if a node would not fit. It checks that the pre-sizing was right. Nothing is allocated on either branch. Four rows, one judgement. |
| `Accumulator.java:60` | `insertPos >= values.length` | **Rule 3, invariant guard.** `values` is a fixed `Object[]` allocated in the constructor; `add()` only stores a reference into it. The check throws on overflow of a structure whose memory is already spent. |
| `DynamicList.java:113` | `size >= maxSize` | **No production caller.** `DynamicList` and its subclass `LockedDynamicList` are not constructed anywhere in `src/java` except `DynamicList`'s own `main()` test harness ([`:231`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/utils/DynamicList.java#L231)). Also fails Rule 3 on its own terms: the `Node` is allocated at `:112`, **before** the check. |
| `LightweightRecycler.java:69` | `pool.size() < capacity()` | **Rule 2, negligible and not tunable.** Decides whether a finished object is kept in a per-thread reuse pool or left to GC — no allocation is withheld. The only production pool is `IncrementalTrieWriterBase`'s children-list recycler, capped at a hardcoded `CHILDREN_LIST_RECYCLER_LIMIT = 1024` ([`IncrementalTrieWriterBase.java:182`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/io/tries/IncrementalTrieWriterBase.java#L182)) cleared `ArrayList`s per thread — on the order of a megabyte per thread at most. |
| `StreamingTombstoneHistogramBuilder.java:452`, helper `$Spool.tryAddOrAccumulate()` (2 rows) | `size > capacity` | **Rule 3.** The spool's `points`/`values` arrays are allocated once in its constructor ([`:433-434`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/utils/streamhist/StreamingTombstoneHistogramBuilder.java#L433-L434)). On `false` the caller flushes the spool into the histogram and retries ([`:109-112`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/utils/streamhist/StreamingTombstoneHistogramBuilder.java#L109-L112)). No allocation diverges; the point is recorded either way. |

### What A2 taught, for A3 and band B

- **A2's hit rate is 0/21 newly-judged rows** (plus one second check site for
  an existing candidate). As `bands.md` predicted, constants and structural
  bounds almost never name a constraint.
- **Path selection is A2's dominant false positive** — four rows compare a size
  against a chunk or clone threshold only to choose *where* to allocate. Ask
  whether the disallow branch allocates the same bytes somewhere else.
- **Invariant guards are the second** — five rows throw when a pre-sized
  structure would overflow. The memory was spent when the structure was sized;
  if a limit exists, it is at that sizing, not at the guard.
- **Check that the class runs in production.** Two classes here
  (`BlockingQueues.Sync`, `DynamicList`) have no production construction site.
  One grep for the constructor settles it before any rule is applied.

## Recorded while filing write-up queue items 4 and 5 — 2026-10-06

One line refused while writing up `local_read_size_fail_threshold`
([case](cases/local_read_size_fail_threshold-addSize-failBytes--guided.md)). `pending.md` said
its warn twin was "already rejected (Rule 3)", but only the row-index twin
(`RowIndexEntry.java:403`, A1 table above) had been recorded; this is the
other one. It is a band-B row of stage 2 (`bands.csv`: `ReadCommand.java:724#2`
in batch 18, and `:724#1` in batch 03), not an A1 row, so it is not counted in
the A1 disposition table.

| Row | Check | Ground |
|---|---|---|
| `ReadCommand.java:724` | `warnBytes != -1 && this.sizeInBytes >= warnBytes` | **Rule 3, logging-only branch.** The warn twin of the qualifying fail threshold at `:715`: it records the `LOCAL_READ_SIZE_WARN` parameter for the client warning and goes on, so nothing diverges on object creation. The same judgement as `RowIndexEntry.java:403`. |

## Batch: band A3, grow-when-full reallocations — 2026-10-13

The 39 A3 rows from
[`../stage2-ai-preprocessing/bands.md`](../stage2-ai-preprocessing/bands.md)
(feed **3a**), read with the source open (`cassandra-src` at `cassandra-5.0.9`).
**1 was already recorded** and is cited, not re-judged: `Flusher.java:282` (the
`Flusher.java` entry in the first table of this file). **No candidate qualifies**,
none is deferred and none is a second site of an existing case. The other **38
are refused below**, in four groups. `bands.md` was right that one argument
disposes of most of them, but not of all: five rows are not grow-when-full at
all (group 4), and two carry a number that does trace to configuration (group 3).

| Group | Row(s) | Check | Ground |
|---|---|---|---|
| 1. Grow-when-full (20 rows) | `RangeTombstoneList.java:668`, `:696`; `CompressionMetadata.java:366`; `Walker.java:442`; `MmappedRegions.java:383`; `AbstractReplicaCollection.java:109`; `PrunableArrayQueue.java:71`; `HistogramBuilder.java:45`; `BTree.java:1538`, `:1573`, `:1600`; `ByteSourceInverse.java:424`; `Stack.java:94`; `InMemoryReadTrie.java:501`; `InMemoryTrie.java:670`; `TriePathReconstructor.java:33`, `:41`; `LongTimSort.java:821`; `BTreeSet.java:133`, `:477` | `size == capacity`, `array.length < required`, on the structure's own array | **Rule 1 and Rule 3.** The limit side is the structure's own current length, which earlier growth set from the data; no user sets it. The branches withhold nothing: the item is stored on both, and the "full" branch allocates **more** (a copy at 1.5–3×, or at the required length), the inverse of a constraint, as with `HintsWriter.java:237` in the A1 batch. None of these structures has a ceiling of its own; whatever bounds them is upstream. Pointers: `PrunableArrayQueue` is the internode outbound queue ([`OutboundMessageQueue.java:70`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/net/OutboundMessageQueue.java#L70)) and its `offer()` always returns `true`; the bytes it holds are bounded by the filed [`internode_application_send_queue_capacity`](cases/internode_application_send_queue_capacity-acquireCapacity-pendingCapacityInBytes--guided.md) case's `acquireCapacity()`, not here. `MmappedRegions.java:383` grows only the arrays of region references; the region was mapped at [`:379`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/io/util/MmappedRegions.java#L379), before the comparison. `BTreeSet.java:477` copies to a *shorter* array (it trims, not grows); it sits here because both branches still write every element. |
| 2. Reusable buffer replaced when too small (11 rows) | `CompressedInputStream.java:144`; `CompressedChecksummedDataInput.java:118`, `:134`; `CompressedHintsWriter.java:53`; `EncryptedChecksummedDataInput.java:126`; `CompressedSequentialWriter.java:247`; `ThreadLocalByteBufferHolder.java:74`; `FrameDecoder.java:393`; `EncryptionUtils.java:134`; `ByteBufferUtil.java:817`; `CBUtil.java:105` | `buffer.capacity() < required` | **Rule 1 and Rule 3**, group 1's argument applied to a scratch buffer reused across calls. When it is too small it is freed (or returned to the `BufferPool`) and replaced by one of the required size; the read, write, decode or decompression proceeds on both branches. The required size is one item's: a compressed chunk, a hints block, one frame, one string. Where that is bounded, the bound is per item and elsewhere: the frame decoder's stash at `:393` holds one frame whose length is a 17-bit header field ([`FrameDecoderCrc.java:79`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/net/FrameDecoderCrc.java#L79), [`FrameDecoderLZ4.java:73`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/net/FrameDecoderLZ4.java#L73)), and `CompressedInputStream`'s buffer serves only chunks shorter than the table's `maxCompressedLength()` ([`:142`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/streaming/CompressedInputStream.java#L142)). `ByteBufferUtil.java:817` has a branch that does diverge: it throws when `allowBufferResize` is false ([`:819-820`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/utils/ByteBufferUtil.java#L819-L820)). But its only caller is `EncryptionUtils`, and every production caller of that passes `true` (`EncryptedSegment.java:125`, `:128`; `CommitLogSegmentReader.java:385-386`; `EncryptedChecksummedDataInput.java:123-124`; `EncryptedHintsWriter.java:49-50`; and `EncryptionUtils.java:136` itself), so in a node it only grows. |
| 3. Growth-policy knobs (2 rows) | `RangeTombstoneList.java:685`; `DataOutputBuffer.java:166` | `newLength <= capacity()`; `capacity > 1024L * 1024L * DOUBLING_THRESHOLD` | **Rule 2, a growth step, not a ceiling.** These are the only A3 rows whose number traces to configuration. `:685` is the fallback when `capacity() × range_tombstone_list_growth_factor` ([`:683`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/RangeTombstoneList.java#L683); [`Config.java:802`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/Config.java#L802), default 1.5, absent from `cassandra.yaml`, settable over JMX within [1.2, 5] at [`StorageService.java:6905`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/service/StorageService.java#L6905)) would not grow the list. `:166` switches a `DataOutputBuffer` from doubling to +50 % above `cassandra.DOB_DOUBLING_THRESHOLD_MB` ([`CassandraRelevantProperties.java:203`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/CassandraRelevantProperties.java#L203), default 64). Both branches allocate. Changing either knob changes how much spare capacity one structure carries past its data, at most the growth factor times what the data needs; no maximum moves. |
| 4. Not grow-when-full; stage 2's reason is wrong (5 rows) | `SegmentRowIdOrdinalPairs.java:55` | `size == capacity` | **Rule 3, invariant guard**, A2's archetype. The `int[]` is allocated once in the constructor ([`:45`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/index/sai/disk/v1/vector/SegmentRowIdOrdinalPairs.java#L45)) at the size its caller computed for the row range (`VectorIndexSegmentSearcher.java:164`, `:299`), and `add()` throws `ArrayIndexOutOfBoundsException` instead of growing. The memory is spent at construction. |
| | `Accumulator.java:75` | `cur != insertPos && (cur == values.length \|\| values[cur] == null)` | **Rule 3, no allocation.** Runs after the item is stored, in the loop that publishes `presentCount` to readers; it decides when to stop advancing the count. The array is fixed; its overflow guard `:60` was refused in the A2 batch. |
| | `FrameDecoder.java:375` | `bytesToSize > in.remaining()` | **Rule 3, no allocation.** `copyToSize()` copies what has arrived into an existing stash and reports whether the frame is complete; neither branch allocates. |
| | `EncryptionUtils.java:142` | `metadataBuffer.remaining() < ENCRYPTED_BLOCK_HEADER_SIZE` | **Rule 3, read validation.** Throws `IllegalStateException` (`:143`) on a short read of the 8-byte block header; nothing is allocated either way. |
| | `ByteBufferUtil.java:815` | `0 > outputLength` | **Argument validation.** Throws `IllegalArgumentException` on a negative size. |

**Disposition, all 39:** 1 recorded (`Flusher.java:282`, rejected) + 38 newly
refused (group 1: 20, group 2: 11, group 3: 2, group 4: 5). Pending 0, deferred 0.

### What A3 taught, for bands B and C

- **A3's hit rate is 0/38 newly-judged rows**, as `bands.md` predicted.
  Grow-when-full is settled by one question: *is the item stored on both
  branches?* If so, the check sizes a structure; it does not limit one.
- **Stage 2's reason was wrong on 5 of 39 rows**: an invariant guard, a
  publication loop, a partial copy and two argument checks were all labelled
  grow-when-full. A1's lesson holds: trust the row for where to look.
- **A configurable growth factor is not a limit.** `range_tombstone_list_growth_factor`
  and `DOB_DOUBLING_THRESHOLD_MB` set the slack of one structure, not a
  ceiling. Growth-policy rows in B and C can be refused on the same ground.
- **Retained high-water buffers have no limit at all.** Four reusable
  thread-local buffers (`ThreadLocalByteBufferHolder`, `CBUtil`'s
  `TL_CHAR_BUFFER`, `EncryptionUtils`' and `EncryptedChecksummedDataInput`'s
  `reusableBuffers`) grow to the largest item their thread has handled and
  never shrink. Nothing in A3 caps them, so there is no check to file. The one
  cap on this kind of retention found so far is `DataOutputBuffer`'s recycle
  check, [`DataOutputBuffer.java:73`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/io/util/DataOutputBuffer.java#L73)
  (`buffer.capacity() <= MAX_RECYCLE_BUFFER_SIZE`, from
  `cassandra.dob_max_recycle_bytes`, default 1 MiB). That is a **band C** row,
  not judged here; read it with care in the C pass, because its disallow branch
  does replace the retained buffer.

## Batch: band B — 2026-10-13

The 174 band-B units of
[`../stage2-ai-preprocessing/bands.csv`](../stage2-ai-preprocessing/bands.csv)
(157 rows and 17 helpers; feed **3a**), read with the source open (`cassandra-src`
at `cassandra-5.0.9`). Outcome:

- **21 already recorded**, cited, not re-judged (list below).
- **1 new candidate** (2 units): `repair_disk_headroom_reject_ratio`,
  `ActiveRepairService.java:655` and its helper `verifyDiskHeadroomThreshold()`
  → [`pending.md`](pending.md) item 12.
- **2 joined to open items**: `IndexSummaryRedistribution.java:258` to
  [`deferred.md`](deferred.md) §5 item 1, `Envelope.java:441` to §6 item 1.
- **1 undecided**: `ReplicaFilteringProtection.java:323`
  ([`deferred.md`](deferred.md) §7).
- **148 refused below**, in eleven groups.

**Cited, already recorded (21):** `ReadCommand.java:715#1` (the enabled test of the
filed [`local_read_size_fail_threshold`](cases/local_read_size_fail_threshold-addSize-failBytes--guided.md)
check, same expression); `ReadCommand.java:724#1`, `#2` (refused 2026-10-06, the warn
twin); `TrackedDataInputPlus.java:184` (refused 2026-09-28, Rule 1);
`ConnectionLimitHandler.java:93`, `:121` and `Flusher.java:152`, `:183`, `:303` (first
table of this file); `AbstractCompactionStrategy.java:408`, `LeveledManifest.java:306`,
`:548`, `:655`, `SizeTieredCompactionStrategy.java:123`, `:274` (4 units), `:301` (the
`db/compaction/` subpackage entry, selection logic); `AutoSavingCache.java:305#2`, `:388`
(the `cache/` subpackage entry).

| Group | Row(s) | Ground |
|---|---|---|
| 1. Warn, log or diagnostic only (10) | `ResultSetBuilder.java:87` (2 units); `BatchStatement.java:340`, `:388`; `ReadCommand.java:639`; `ReplicaFilteringProtection.java:333`; `DatabaseDescriptor.java:726`, `:741`; `CommitLog.java:609`; `SimpleSeedProvider.java:110` | **Rule 3, logging-only branch.** Each logs, warns the client, bumps a metric or builds an error message, and goes on. `ResultSetBuilder.java:87` is the warn twin of `shouldReject()` (`:95-98`), the check of the unjudged `coordinator_read_size_fail_threshold` ([`pending.md`](pending.md) item 11); `BatchStatement.java:340` is the warn twin of the refused `:352`; `ReplicaFilteringProtection.java:333` the warn twin of the deferred `:323`. |
| 2. Per-item format and type bounds (21) | `QueryProcessor.java:259`, `:758`; `Validation.java:51`; `ClusteringPrefix.java:278`, `:284`; `CassandraIndex.java:618`; `SortedTableWriter.java:169` and helper `verifyPartition()`; `UnbufferedDataOutputStreamPlus.java:274`; `CacheService.java:504`; `ClientWarn.java:79`; `ByteBufferUtil.java:766`; `FrameEncoderCrc.java:71`; `FrameEncoderLZ4.java:73`; `FrameEncoderUnprotected.java:53`; `StreamingMultiplexedChannel.java:231`; `BlockBalancedTreeWriter.java:651`; `AbstractTokenTreeBuilder.java:297`, `:323`; `OnDiskIndexBuilder.java:598`; helper `OutboundConnection.isMaxPendingCount()` | **Rule 2, per-item bound.** Each throws (or skips one item) when **one** key, value, string, frame, message or term would not fit an encoding: the 65,535-byte unsigned-short length (keys, clustering, indexed values, `writeUTF`, saved key cache, the client-warning list), the 128 KiB frame payload, the 1 GiB stream control message, an index file format field. None bounds a total and none is configuration. `isMaxPendingCount()` is the saturation of the pending-count bit field inside the filed `internode_application_send_queue_capacity` case's `acquireCapacity()` ([`OutboundConnection.java:391`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/net/OutboundConnection.java#L391)): a type bound on the packed counter, not the byte cap. |
| 3. Rollover and block cadence (18) | `BlockBalancedTreeWriter.java:528`; `AbstractBlockPackedWriter.java:62`; `PostingsWriter.java:222`; `AbstractTokenTreeBuilder.java:520`; `OnDiskIndexBuilder.java:497`; `IncrementalTrieWriterPageAware.java:125`, `:127`, `:135`, `:141`, `:167`, `:213`, `:215`; `HintsWriter.java:205`, `:214`; `BigFormatPartitionWriter.java:213`; `BtiFormatPartitionWriter.java:82`; helper `SSTableSimpleWriter.shouldSwitchToNewWriter()`; `SSTableRewriter.java:156` | **Rule 2, rollover** (README §3.5's edge case). A block, page, index block, buffer or writer is full, so it is written out or padded and the next one starts; every byte is written either way. `BigFormatPartitionWriter.java:213` and `BtiFormatPartitionWriter.java:82` close a row-index block at `column_index_size`: that sets how many index entries a partition gets, and the heap those entries cost on read is the filed `column_index_cache_size` and `row_index_read_size_fail_threshold` cases. `SSTableRewriter.java:156` reopens the new SSTable early every `sstable_preemptive_open_interval`: I/O scheduling, not a byte bound. |
| 4. Fast/slow path and route selection (29) | `BufferedDataOutputStreamPlus.java:169`, `:191`, `:201`, `:211`; `RebufferingInputStream.java:195`, `:210`, `:219`, `:228`, `:250`, `:256`, `:287`, `:296`; `CompressedSequentialWriter.java:160`, `:163`; `InboundMessageHandler.java:148`; `OutboundConnections.java:215`; `OutboundConnection.java:796`; `FrameDecoderWith8bHeader.java:114`, `:129`; `BufferPool.java:929`, `:1602`; `ColumnFamilyStore.java:1931` and helper `isFilterFullyCoveredBy()`; `DataLimits.java:414`, `:417`; `SimpleClient.java:770`, `:777`, `:818`, `:838` | **Rule 3, path selection.** The comparison picks a route for the same bytes: a typed read or write from the buffer or through the slow path, a chunk written compressed or raw, a small or large message path or connection, a partial frame stashed or decoded, a tiny or normal pool allocation, a row served from the row cache or from SSTables. `SimpleClient` is the client side (stress and tests), not node code. |
| 5. Growth, sizing and node layout (19) | `BTree.java:137`, `:231`, `:2530`, `:2558`, `:2575`, `:2608`, `:2712`, `:2832`, `:3064`, `:3185`; `BTreeRemoval.java:88`, `:90`, `:99`; helpers `BTree$LeafOrBranchBuilder.isSufficient()`, `mustRedistribute()`; `NativeAllocator.java:166`; `SafeMemoryWriter.java:52`; `BufferPoolAllocator.java:121`; helper `StreamingTombstoneHistogramBuilder$DataHolder.isFull()` | **Rule 1 and Rule 3**, band A3's ground. `MAX_KEYS`/`MIN_KEYS` are the B-tree's node fan-out (from `cassandra.btree.branchshift`); splitting, overflowing or redistributing a node lays out keys that are all stored. The others size a region, resize a buffer, or merge histogram bins in an array allocated once. |
| 6. Release, reclaim and bookkeeping (7) | `AbstractMessageHandler.java:447`; `OutboundConnection.java:767`, `:871`; `CommitLogSegmentManagerCDC.java:93`; `AbstractCommitLogSegmentManager.java:249`, `:259`; `AbstractAllocatorMemtable.java:274` | **Rule 3, nothing withheld.** `AbstractMessageHandler.java:447` returns over-borrowed reserve inside the filed receive case's `acquireCapacity()`; `OutboundConnection.java:871` resumes delivery below the flush low-water mark (the bytes are still counted by the filed send case until `releaseCapacity()` at `:866`), `:767` stops when nothing is pending; `CommitLogSegmentManagerCDC.java:93` is the deletion path of the filed `cdc_total_space` case; `AbstractAllocatorMemtable.java:274` picks the largest memtable to flush. **`AbstractCommitLogSegmentManager.java:249`, `:259` are `commitlog_total_space`**, judged here for the first time: the manager thread creates the next segment ([`:189`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/commitlog/AbstractCommitLogSegmentManager.java#L189)) and only afterwards calls `maybeFlushToReclaim()` ([`:200`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/commitlog/AbstractCommitLogSegmentManager.java#L200)), which, over the limit ([`:447`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/commitlog/AbstractCommitLogSegmentManager.java#L447)), flushes memtables so old segments can be recycled ([`:262`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/commitlog/AbstractCommitLogSegmentManager.java#L262)). A reclaim trigger, the same judgement as `needsCleaning()` in the A1 batch: the commit log can exceed it. |
| 7. Count, time, work and error thresholds (25) | `ReadCommand.java:591`; `DataLimits.java:509`, `:511`, `:986`, `:993`, `:1000`, `:1041` (2 units) and helpers `GroupByAwareCounter.isDone()`, `isDoneForPartition()`; `AutoRepair.java:459`; `MigrationCoordinator.java:290`; `ActiveRepairService.java:641` and helper `verifyCompactionsPendingThreshold()`; `StreamSession.java:989`; `CQLMessageHandler.java:345#2`, `:408`; helpers `AutoRepairUtils.keyspaceMaxRepairTimeExceeded()`, `tableMaxRepairTimeExceeded()`; helper `StartupClusterConnectivityChecker$AckMap.incrementAndCheck()`; `DiagnosticSnapshotService.java:147`; `RepairTokenRangeSplitter.java:238`, `:312`, `:360`; `TopPartitionTracker.java:239` | **Rule 2, not a byte ceiling.** Counts of SSTables, pending compactions, outstanding schema pulls, consecutive protocol errors, acks or snapshot ranges; elapsed repair time; repair work per schedule (`max_bytes_per_schedule` budgets bytes *examined*, a throughput limit). `DataLimits` stops at the query's own `LIMIT`, per-partition limit or page size, a client parameter, so it also fails Rule 1. `TopPartitionTracker.java:239` caps a top-*N* report (`max_top_size_partition_count`, default 10, [`Config.java:1150`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/Config.java#L1150)) per table: one partition key per entry, negligible at its scale. **`ReadCommand.java:591` (`tombstone_failure_threshold`) is the nearest miss:** it does abort the read ([`:601`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/ReadCommand.java#L601)), but it counts tombstones **scanned** as they stream past the iterator, of no fixed size and not held by the check's structure; the byte bound on the same read is the filed `local_read_size_fail_threshold`. Contrast `ReplicaFilteringProtection.java:323` (deferred), whose rows are held. |
| 8. Bounded in-memory logs and recyclers (4) | `LogMessagesTable.java:193`; `VirtualTableAppender.java:125`; `DiagnosticEventMemoryStore.java:56`; `Ref.java:435` | **Rule 2, count of variable or negligible entries.** The logs virtual table keeps at most `cassandra.virtual.logs.max.rows` messages ([`LogMessagesTable.java:149`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/virtual/LogMessagesTable.java#L149), clamped to [1,000, 100,000], default 50,000) and evicts the oldest; its appender is commented out in the shipped `logback.xml` (line 114), and `VirtualTableAppender.java:125` caps its pre-startup buffer at the same default. The diagnostic store keeps 200 events (diagnostics are off by default); `Ref.java:435` caps a recycler pool at 1,024, like `LightweightRecycler.java:69` in the A2 batch. Each bounds a **count** of entries whose size the code does not bound, and a ring buffer bounds by evicting, not by withholding (see "What band B taught"). |
| 9. Configuration plumbing and validation (4) | `DatabaseDescriptor.java:3369`, `:3386`, `:1152`; `RepairTokenRangeSplitter.java:181` | **No allocation.** `:3369` and `:3386` turn `-1` into the default (heap/40, heap/10) of `native_transport_max_request_data_in_flight(_per_ip)`, whose enforcement is elsewhere; `:1152` derives the default `commitlog_total_space` and `cdc_total_space` from the volume size (`:669`, `:689`); `:181` validates two repair options against each other. |
| 10. Read validation against the input's own length (4) | `ChecksummedDataInput.java:161`; `CBUtil.java:457`, `:666`; `EncryptionUtils.java:197` | **Rule 1**, `TrackedDataInputPlus`'s ground: the limit is the length of what is being read (a hint's serialized size, the bytes left in a message, a block's declared size) and the disallow throws on corrupt or short input. |
| 11. Strategy and selection (7) | `AtomicBTreePartition.java:272` and helpers `updateWastedAllocationTracker()`, `useLock()`; `Overlaps.java:205`; `StreamSession.java:894`, `:913`; helper `StandaloneSplitter.isSSTableLargerEnough()` | **Rule 2 / Rule 3.** `AtomicBTreePartition` switches a hot partition from optimistic CAS to a lock once wasted allocation passes 10 MiB per interval: a concurrency strategy. `Overlaps.java:205` selects compaction inputs. `StreamSession.java:894`, `:913` skip empty stream summaries before the disk check (see the note below). `StandaloneSplitter` is the offline `sstablesplit` tool. |

**Disposition, all 174:** 21 cited + 1 candidate (2 units) + 2 joined + 1 deferred +
148 refused (10 + 21 + 18 + 29 + 19 + 7 + 25 + 4 + 4 + 4 + 7).

### Notes for filed cases, recorded here and not applied

- **`max_space_usable_for_compactions_in_percentage`** has a second decision point
  the case does not list: the **stream receive** check. `StreamSession.checkDiskSpace()`
  calls the same `Directories.hasDiskSpaceForCompactionsAndStreams()`
  ([`StreamSession.java:937`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/streaming/StreamSession.java#L937))
  with the incoming bytes plus ongoing stream and compaction writes, and a refusal
  throws and fails the session ([`:872`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/streaming/StreamSession.java#L872));
  it is reached from `:798` and `:827`, and skipped when `skip_stream_disk_space_check`
  is set ([`:858`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/streaming/StreamSession.java#L858),
  default false). For the case's §1 Location and §10, and a possible third scenario at stage 4.
- **`max_mutation_size`**, §5: "the commit log's total size is held by
  `commitlog_total_space`" overstates it. Group 6 above shows `commitlog_total_space`
  is a reclaim target that the commit log can exceed, not a ceiling.

### What band B taught, for band C

- **Band B's hit rate is 1 candidate in 150 newly judged units** (174 − 21 cited − 2 joined
  − 1 deferred). Stage 2's themes were accurate; most of the band is per-item encoding
  bounds, rollover and path selection, which one look at the branch settles.
- **The one candidate is an admission check on disk**, the same shape as the filed
  compaction case. Disk admission checks are worth looking for in C: search for callers of
  `DiskUsageMonitor`, `getAvailableSpace` and `hasDiskSpaceForCompactionsAndStreams`.
- **Count caps on materialized rows need a ruling.** Earlier passes refused count caps
  whose items have no fixed size (`StorageProxy.java:1592`, `PartitionDenylist`), and this
  pass refused `tombstone_failure_threshold` on the same ground. `cached_rows_fail_threshold`
  is harder: its rows are held on heap, withheld before they are stored, and nothing else
  bounds them. It is deferred (§7) for a decision on whether a count of held rows of
  table-bounded size passes Rule 2.
- **A ring buffer bounds by eviction, not by withholding.** Rule 3 is written for a check
  that withholds creation; a capped log or event store creates the new entry and drops the
  oldest. None in B qualified on Rule 2 grounds, so the question did not need answering,
  but a byte-weighted evicting store in C would need it.
- **A soft limit is a finding even when the line is refused.** `commitlog_total_space` is
  not a ceiling, and a filed case said it was; a refusal can correct a case.

## Batch: band C, the insurance band — 2026-10-13

The 94 band-C units of
[`../stage2-ai-preprocessing/bands.csv`](../stage2-ai-preprocessing/bands.csv)
(87 rows and 7 helpers; feed **3a**), read with the source open (`cassandra-src`
at `cassandra-5.0.9`). Outcome:

- **7 already recorded**, cited, not re-judged: `LeveledCompactionStrategy.java:78`,
  `:81`, `unified/Controller.java:305` and `Dispatcher.java:345` with its helper
  `hasQueueCapacity()` (first table of this file); `unified/Controller.java:613` (the
  `db/compaction/` subpackage entry); `NopCacheProvider.java:39` (the `cache/` entry).
- **1 new candidate**: `DOB_MAX_RECYCLE_BYTES`, `DataOutputBuffer.java:73`, the row
  band A3 pointed to → [`pending.md`](pending.md) item 13.
- **86 refused below**, in six groups. Nothing deferred.

Stage 2 called C the band with "named operands, nothing resource-shaped", and it was
right for 86 of 87 newly judged units: most are emptiness tests, enabled-switches and
configuration validation of a limit enforced somewhere else.

| Group | Row(s) | Ground |
|---|---|---|
| 1. Emptiness, sentinel, enabled and release tests (21) | `QueryProcessor.java:251`; `Validation.java:47`; `UDFDataType.java:177`; `StorageAttachedIndex.java:791`, `:1006`; `SSTableIndexWriter.java:221`; `SegmentBuilder.java:260`; `ColumnFamilyStore.java:2501`, `:2508` and helpers `isCounterCacheEnabled()`, `isRowCacheEnabled()`; `CounterMutation.java:213`; `MonitoringTask.java:221`; `ThrottledUnfilteredIterator.java:234`; `AtomicBTreePartition.java:283`, `:300` (2 units); `NativeAllocator.java:194`; `ClientResourceLimits.java:176`; `PreV5Handlers.java:127`; helper `CQLSSTableWriter$Builder.isMaxSSTableSizeUnset()` | **Rule 1, no limit compared.** An empty key, value or term; a capacity of `0` meaning "cache off" or "unthrottled"; a CAS or tracker sentinel; a reference count reaching zero. The caches' own capacities (`row_cache_size`, `counter_cache_size`) are enforced inside the cache implementations, not at these lines. `PreV5Handlers.java:127` unpauses a pre-v5 connection once in-flight bytes drop: the release side of the `native_transport_max_request_data_in_flight` limits. `StorageAttachedIndex.java:1006` charges SAI memtable-index growth to the memtable's on-heap count (`markExtraOnHeapUsed`) and drops decreases: accounting, no allocation gated. |
| 2. Configuration and schema validation (30) | `DatabaseDescriptor.java:911`, `:914`, `:978`, `:981`, `:984`, `:987`, `:1016` (2 units), `:4093`, `:5347` (2 units); `GuardrailsOptions.java:1219`, `:1257`; `StorageAttachedIndexOptions.java:41`; `CQLSSTableWriter.java:539`; `CompressionParams.java:352`, `:456#2`; `KeyspaceMetadata.java:68`; `TableMetadata.java:517`; `CreateIndexStatement.java:213`; `ColumnFamilyStore.java:2185`; `InMemoryTrie.java:64` (2 units); `StorageService.java:6889` (2 units), `:6905` (2 units); `IndexMode.java:190`; `SAICodecUtils.java:129` (2 units) | **No allocation.** Range checks and cross-key checks at startup, in a setter or at schema creation: a message size must not exceed the in-flight and reserve caps (`:911`–`:987`), a ratio lies in [0, 1], a name fits a length, a guardrail's fail threshold is not below its warn threshold, SASI's flush memory is clamped to 100 GiB. The limits they validate are enforced elsewhere, several by filed cases or pending items. `InMemoryTrie.java:64` validates the trie size threshold; see the note on its property below. |
| 3. Startup and OS environment checks, log only (9) | `DatabaseDescriptor.java:4096`; `NativeLibrary.java:197`; `SigarLibrary.java:78` (2 units), `:99` (2 units), `:120`; `StartupChecks.java:497`, `:554` | **Rule 3, logging-only.** `repair_session_space` above a quarter of the heap, `mlockall` failing with `ENOMEM`, the process and file limits, the address-space limit, read-ahead and `vm.max_map_count`: each is compared once at startup and logged. |
| 4. Per-item format bounds and invariants (15) | `CodecUtils.java:101`, `:250`; `StorageAttachedIndex.java:503`; `MappedBuffer.java:63`, `:105` (2 units), `:119` (2 units); `Memory.java:147#3`, `:188` (3 units); `AsyncMessageOutputPlus.java:96`; `InMemoryTrie.java:148`; helper `StandardAnalyzer.incrementToken()` | **Rule 2, per-item bound.** Protocol v1/v2's 65,535 elements or bytes per collection, the ANN top-*k* cap per query, position/limit and copy bounds that throw `IndexOutOfBounds`, a serialized size that disagrees with the declared one, one trie's 2 GiB addressing limit (`SpaceExhaustedException`), SASI's minimum token length. |
| 5. Path selection and growth (9) | `InMemoryTrie.java:145`; `RangeTombstoneList.java:213`; `TrieMemoryIndex.java:228`; `VectorMemoryIndex.java:190`, `:229` and helper `VectorIndexSegmentSearcher.shouldUseBruteForce()`; `RandomAccessReaderAdapter.java:69`, `:117`; helper `ByteBufferUtil.canMinimize()` | **Rule 3**, bands A3 and B's grounds: the next trie chunk is allocated when the current one is used up; a merge or per-item add; recursive or iterative insertion; brute-force or graph search; a read across a region boundary through a temporary buffer; whether a buffer can be trimmed. |
| 6. Rate limiting (2) | `LimitingRebufferer.java:55`, `:58` | **Rule 2, rate.** The rebufferer acquires permits from a `RateLimiter` per chunk (compaction and streaming throughput): speed, not bytes held. |

**Disposition, all 94:** 7 cited + 1 candidate + 86 refused (21 + 30 + 9 + 15 + 9 + 2).

### Recorded while reading band C (feed 3b)

One line that is not a stage-2 row was read while settling `StorageAttachedIndexOptions.java:41`.

| Row | Check | Ground |
|---|---|---|
| `NamedMemoryLimiter.usageExceedsLimit():55`, read at `SSTableIndexWriter.shouldFlush():248` | `currentBytesUsed() > limitBytes` | **Rule 2, rollover**, the ground on which the A1 batch refused its SASI twin `PerSSTableIndexWriter.java:247`. `limitBytes` is `sai_options.segment_write_buffer_size` (default 1,024 MiB), shared node-wide by every SAI segment build ([`V1OnDiskFormat.java:126-128`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/index/sai/disk/v1/V1OnDiskFormat.java#L126-L128)). Over the budget, a builder past its minimum flush size flushes its segment and starts another; the term is still added ([`SSTableIndexWriter.java:225`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/index/sai/disk/v1/SSTableIndexWriter.java#L225)). A soft target, like `commitlog_total_space` in band B. |

### A misconfiguration hazard found while reading `InMemoryTrie.java:64`

Not a check to file, but Target 3 material. The trie memtable's per-shard size threshold
(default 2048 × 10 / 11 MiB; reaching it schedules a flush,
[`TrieMemtable.java:192-195`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/memtable/TrieMemtable.java#L192-L195))
is read from the JVM property **`cassandra.memtable.row_overhead_size`**
([`InMemoryTrie.java:63`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/tries/InMemoryTrie.java#L63),
[`CassandraRelevantProperties.java:356`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/CassandraRelevantProperties.java#L356)).
`SkipListMemtable` reads the same property as its per-row heap overhead **in bytes**
([`SkipListMemtable.java:75-77`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/memtable/SkipListMemtable.java#L75-L77)).
Setting it to tune one sets the other in a different unit: a row overhead of, say,
200 bytes makes every trie memtable flush at 200 MiB per shard, and a value above
2047 stops `InMemoryTrie` from initialising (`AssertionError`, `:64-66`). The same
kind of finding as the send-queue case's reserve key read from its receive-side twin.

### What band C taught

- **The insurance band paid once.** 1 candidate in 87 newly judged units, and it was
  the row band A3's reading pointed to, not one stage 2 ranked for itself; C's rows are
  overwhelmingly the validation and enabled-switch side of limits enforced elsewhere.
- **Rule 3's failing condition settles retention caps.** README §3.6 fails a check only
  for "zero observable effect". A recycle cap keeps or frees the buffer, which is an
  effect on what stays resident, so `DOB_MAX_RECYCLE_BYTES` passes. This answers band B's
  open note for a byte-compared retention cap; band B's evicting logs were refused on
  Rule 2 (counts of unsized entries), not Rule 3, and are unaffected.
- **Soft targets are a pattern worth a list.** `commitlog_total_space` (band B),
  `segment_write_buffer_size` (above), the SASI `max_flush_memory` (A1) and the trie
  threshold (above) all trigger a flush rather than refuse, so none is a ceiling. They
  are refused here, but they are where Target 3's "usage can exceed the configured
  value" findings are likely to be.

## Written up by the autonomous agent — 2026-10-19

First wave of the rejected-entry write-up by the autonomous agent (target `file:line` only). The agents read the source and ran nothing. **Their judgments are recorded in the case files and are not yet reviewed; the entries above keep the recorded ground.** Two of the six overlap a closed case, and two target the same constraint.

| Rejected site | Case file (`cases/…--autonomous.md`) | Agent's judgment | Against the recorded ground |
|---|---|---|---|
| `QueryProcessor.java:825` | [`prepared_statements_cache_size-storePreparedStatement-capacityToBytes`](cases/prepared_statements_cache_size-storePreparedStatement-capacityToBytes--autonomous.md) | qualifies | reverses |
| `Message.java:817` | [`internode_max_message_size-inferMessageSize-size`](cases/internode_max_message_size-inferMessageSize-size--autonomous.md) | qualifies | reverses; same constraint as the next row |
| `OutboundConnection.java:331` | [`internode_max_message_size-enqueue-getInternodeMaxMessageSizeInBytes`](cases/internode_max_message_size-enqueue-getInternodeMaxMessageSizeInBytes--autonomous.md) | qualifies (weakly) | reverses; send side of the same constraint |
| `HintsBuffer.java:190` | [`max_mutation_size-allocateBytes-slabCapacity`](cases/max_mutation_size-allocateBytes-slabCapacity--autonomous.md) | qualifies, with a caveat | reverses in part; same mechanism as the closed `MAX_HINT_BUFFERS` case |
| `HintsWriter.java:237` | [`WRITE_BUFFER_SIZE-append-remaining`](cases/WRITE_BUFFER_SIZE-append-remaining--autonomous.md) | does not cap | agrees |
| `AbstractMessageHandler.java:464` | [`internode_application_receive_queue_capacity-releaseCapacity-queueCapacity`](cases/internode_application_receive_queue_capacity-releaseCapacity-queueCapacity--autonomous.md) | qualifies | reverses in part; release half of the closed `internode_application_receive_queue_capacity` case |
