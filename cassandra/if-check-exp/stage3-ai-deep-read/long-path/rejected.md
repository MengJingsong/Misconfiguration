# Stage 3 — lines considered and rejected

Lines read **with the Cassandra source open** and refused against the three
rules ([`../../README.md` §3.4–§3.6](../../README.md#3-core-concept-the-if-check-case)).
This is the stage-3 rejection store; it moved here from `_INDEX.md` when the
stage folders were introduced (2026-09-23), so `_INDEX.md` is now a master
index of **cases only**.

**This is the only rejection file in the experiment, and it is
authoritative for every rejection.** Stage 2 cannot reject — it gives a hopeless
row the bottom band instead — so every refusal here was made with the source
open. A stage-2 `negatives.md` held row-level rule-outs until stage 2 stopped
rejecting on 2026-09-23; it was deleted on 2026-09-24 and its rows carry band
D in `../../stage2-ai-preprocessing/bands.csv`, with the per-helper arguments in
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
| `CompactionManager.java:245` (`concurrent_compactors`, `submitBackground()`) | Fails Rule 2 (see README § Core concept): limit-side operand is `executor.getMaximumPoolSize()`, a thread-pool size. Changing `concurrent_compactors` changes how many compactions run *concurrently* (speed/throughput), not the total bytes memtable/compaction machinery can hold — the allocations a compaction task performs once running are unaffected by this cap. Case file drafted then removed once this rule was adopted. |
| `CommitLogSegment.java:246` (`next >= endOfBuffer`) — *line corrected 2026-09-28, recorded as `:242`* | Doesn't diverge on object creation — the "full" branch creates a *new* segment rather than blocking/rejecting; same non-diverging pattern as prior compaction rejects. |
| `HintsBuffer.java:190` (`(prev+totalSize) > slab.capacity()`) | Same non-diverging pattern — the "full" branch triggers allocation of a new buffer rather than blocking/rejecting. |
| `BatchStatement.java:352` (`verifyBatchSize()`, `size > failThreshold`) — *line corrected 2026-09-28, recorded as `:349`* | Runs after the batch's mutations are already fully constructed — doesn't gate object creation, only rejects an already-built batch post hoc. |
| `SEPExecutor.java:135,165,175,196,373,384` / `SEPWorker.java:165,282,330,342` / `SharedExecutorPool.java:137` (task/work permit checks) | Thread-pool worker/permit concurrency accounting, same as `concurrent_compactors` — bounds how many tasks run concurrently, not the bytes any task allocates. |
| `Dispatcher.java:345` (`hasQueueCapacity()`, `oldestTaskQueueTime() < timeout*threshold`) | Time-based (item age in queue), not a byte/capacity comparison — fails Rule 2. |
| `ConnectionLimitHandler.java:93,121` (`count > limit`, per-IP/global connection count caps) | Bounds concurrent *connection count*, not bytes; per-connection memory footprint isn't fixed/derivable at this check, and the actual byte-level enforcement for CQL traffic is the separate `native_transport_receive_queue_capacity`/`native_transport_max_request_data_in_flight` mechanism (see `deferred.md`'s parked candidate). Deferred rather than firmly rejected — revisit if a fixed per-connection footprint can be derived. |
| `CQLMessageHandler.java:551` (`messageSize > getNativeTransportMaxMessageSizeInBytes()`) | Rejects a single oversized frame outright (protocol/sanity bound on one message), not a running-total capacity check — distinct from the `queueCapacity`-based candidate, since promoted to a case file (see `../../stage2-ai-preprocessing/bands.md`). |
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
[`../../stage2-ai-preprocessing/bands.md`](../../stage2-ai-preprocessing/bands.md)
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
| | *(recorded)* still-open candidates | `QueryController:449` (`MAX_MATERIALIZED_KEYS`), `TeeDataInputPlus:58` (`TeeDataInputPlus_limit`, since filed as the second site of `CACHEABLE_MUTATION_SIZE_LIMIT`) | 2 |
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
[`../../stage2-ai-preprocessing/bands.md`](../../stage2-ai-preprocessing/bands.md)
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
| `BufferPool.java:910`, `:940` (2 rows) | `size > NORMAL_CHUNK_SIZE` | **Rule 3, path selection.** An oversized request skips the pool (`tryGet` returns `null`) and `get()` calls `allocate(size, OFF_HEAP)` directly. The same bytes are allocated on both branches. This is the uncapped fallback the filed [`file_cache_size`](cases/file_cache_size-allocateMoreChunks-memoryUsageThreshold.md) case already records — useful context there, not a check of its own. |
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
([case](cases/local_read_size_fail_threshold-addSize-failBytes.md)). `pending.md` said
its warn twin was "already rejected (Rule 3)", but only the row-index twin
(`RowIndexEntry.java:403`, A1 table above) had been recorded; this is the
other one. It is a band-B row of stage 2 (`bands.csv`: `ReadCommand.java:724#2`
in batch 18, and `:724#1` in batch 03), not an A1 row, so it is not counted in
the A1 disposition table.

| Row | Check | Ground |
|---|---|---|
| `ReadCommand.java:724` | `warnBytes != -1 && this.sizeInBytes >= warnBytes` | **Rule 3, logging-only branch.** The warn twin of the qualifying fail threshold at `:715`: it records the `LOCAL_READ_SIZE_WARN` parameter for the client warning and goes on, so nothing diverges on object creation. The same judgement as `RowIndexEntry.java:403`. |
