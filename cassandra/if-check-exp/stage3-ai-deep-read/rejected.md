# Stage 3 — lines considered and rejected

Lines read **with the Cassandra source open** and refused against the three
rules ([`../README.md` §3.4–§3.6](../README.md#3-core-concept-the-if-check-case)).
This is the stage-3 rejection store; it moved here from `_INDEX.md` when the
stage folders were introduced (2026-09-23), so `_INDEX.md` is now a master
index of **cases only**.

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
| `CompactionManager.java:245` (`concurrent_compactors`, `submitBackground()`) | Fails Rule 2 (see README § Core concept): limit-side operand is `executor.getMaximumPoolSize()`, a thread-pool size. Changing `concurrent_compactors` changes how many compactions run *concurrently* (speed/throughput), not the total bytes memtable/compaction machinery can hold — the allocations a compaction task performs once running are unaffected by this cap. Case file drafted then removed once this rule was adopted. |
| `CommitLogSegment.java:242` (`next >= endOfBuffer`) | Doesn't diverge on object creation — the "full" branch creates a *new* segment rather than blocking/rejecting; same non-diverging pattern as prior compaction rejects. |
| `HintsBuffer.java:190` (`(prev+totalSize) > slab.capacity()`) | Same non-diverging pattern — the "full" branch triggers allocation of a new buffer rather than blocking/rejecting. |
| `BatchStatement.java:349` (`verifyBatchSize()`, `size > failThreshold`) | Runs after the batch's mutations are already fully constructed — doesn't gate object creation, only rejects an already-built batch post hoc. |
| `SEPExecutor.java:135,165,175,196,373,384` / `SEPWorker.java:165,282,330,342` / `SharedExecutorPool.java:137` (task/work permit checks) | Thread-pool worker/permit concurrency accounting, same as `concurrent_compactors` — bounds how many tasks run concurrently, not the bytes any task allocates. |
| `Dispatcher.java:345` (`hasQueueCapacity()`, `oldestTaskQueueTime() < timeout*threshold`) | Time-based (item age in queue), not a byte/capacity comparison — fails Rule 2. |
| `ConnectionLimitHandler.java:93,121` (`count > limit`, per-IP/global connection count caps) | Bounds concurrent *connection count*, not bytes; per-connection memory footprint isn't fixed/derivable at this check, and the actual byte-level enforcement for CQL traffic is the separate `native_transport_receive_queue_capacity`/`native_transport_max_request_data_in_flight` mechanism (see `deferred.md`'s parked candidate). Deferred rather than firmly rejected — revisit if a fixed per-connection footprint can be derived. |
| `CQLMessageHandler.java:551` (`messageSize > getNativeTransportMaxMessageSizeInBytes()`) | Rejects a single oversized frame outright (protocol/sanity bound on one message), not a running-total capacity check — distinct from the `queueCapacity`-based candidate, since promoted to a case file (see `../stage2-ai-preprocessing/bands.md`). |
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
