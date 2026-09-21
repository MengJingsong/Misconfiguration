# If-Check Cases — Master Index

Navigation hub and progress tracker for all if-check cases.
See [README.md](README.md) for the format.

**Source:** apache/cassandra @ tag `cassandra-5.0.9`
**Status legend:** `pending` · `in-progress` · `verified`
**Pattern legend** (README §3.2): **(a)** the capacity check is the decision · **(b)** the check sets a verdict (flag, enum, return value) that a separate decision point reads · **(c)** guard clause(s) before an allocation outside any branch

## 1. Master Index

| Case | Module | Limit | Object | Pattern | Capacity check | Status | File |
|------|--------|-------|--------|---------|----------------|--------|------|
| `memtable_heap_space-tryAllocate-limit` | `memtable` | `memtable_heap_space` | `bytebuffer` | (b) | [`SubPool.tryAllocate():156`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/utils/memory/MemtablePool.java#L156) | verified | [link](memtable/memtable_heap_space-tryAllocate-limit.md) |
| `memtable_offheap_space-tryAllocate-limit` | `memtable` | `memtable_offheap_space` | `region` | (b) | [`SubPool.tryAllocate():156`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/utils/memory/MemtablePool.java#L156) | verified | [link](memtable/memtable_offheap_space-tryAllocate-limit.md) |
| `internode_application_receive_queue_capacity-acquireCapacity-queueCapacity` | `net` | `internode_application_receive_queue_capacity` | `message` | (b) | [`AbstractMessageHandler.acquireCapacity():419`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/net/AbstractMessageHandler.java#L419) | pending | [link](net/internode_application_receive_queue_capacity-acquireCapacity-queueCapacity.md) |
| `native_transport_receive_queue_capacity-acquireCapacity-queueCapacity` | `net` | `native_transport_receive_queue_capacity` | `message` | (b) | [`AbstractMessageHandler.acquireCapacity():419`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/net/AbstractMessageHandler.java#L419) | pending | [link](net/native_transport_receive_queue_capacity-acquireCapacity-queueCapacity.md) |
| `MAX_HINT_BUFFERS-switchCurrentBuffer-MAX_ALLOCATED_BUFFERS` | `hints` | `HintsBufferPool_MAX_ALLOCATED_BUFFERS` | `hintsbuffer` | (a) | [`HintsBufferPool.switchCurrentBuffer():113`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/hints/HintsBufferPool.java#L113) | pending | [link](hints/MAX_HINT_BUFFERS-switchCurrentBuffer-MAX_ALLOCATED_BUFFERS.md) |
| `cdc_total_space-processNewSegment-allowance` | `commitlog` | `cdc_total_space` | `allocation` | (b) | [`CDCSizeTracker.processNewSegment():335`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/commitlog/CommitLogSegmentManagerCDC.java#L335) | pending | [link](commitlog/cdc_total_space-processNewSegment-allowance.md) |

<!-- Add one row per case. -->

## 2. Coverage summary

| Metric | Count |
|--------|-------|
| Modules covered | 4 |
| Total cases | 6 |
| Verified | 2 |
| Pending / in-progress | 4 |

## 3. Lines considered and rejected

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
| `ConnectionLimitHandler.java:93,121` (`count > limit`, per-IP/global connection count caps) | Bounds concurrent *connection count*, not bytes; per-connection memory footprint isn't fixed/derivable at this check, and the actual byte-level enforcement for CQL traffic is the separate `native_transport_receive_queue_capacity`/`native_transport_max_request_data_in_flight` mechanism (see `candidates/candidates.md`'s live candidate). Deferred rather than firmly rejected — revisit if a fixed per-connection footprint can be derived. |
| `CQLMessageHandler.java:551` (`messageSize > getNativeTransportMaxMessageSizeInBytes()`) | Rejects a single oversized frame outright (protocol/sanity bound on one message), not a running-total capacity check — distinct from the `queueCapacity`-based candidate filed in `candidates/candidates.md`. |
| `Flusher.java:152,183,282,303,332,345` (`MAX_FRAMED_PAYLOAD_SIZE`, flush-buffer bookkeeping) | Governs how outbound response bytes are chunked/framed for writing, not a cap on how much gets allocated — buffers are sized to the response regardless of branch taken. |
| `cache/` subpackage (`AutoSavingCache`, `CaffeineCache`, `ChunkCache`, `NopCacheProvider`, `RefCountedMemory`, `SerializingCache`) | Surveyed in full (15 rows) — ref-counting (`refCount == 0`), `int`-overflow guards (`size > MAX_VALUE`), and cache-save bookkeeping; no capacity-vs-limit divergence gating new object creation found. |
| `db/compaction/` subpackage, remaining files not already logged above (208 rows total, full subpackage now surveyed) | Extends the earlier informal compaction survey's conclusion to every file in the subpackage. Three recurring non-qualifying patterns account for nearly all rows: (1) **SSTable-candidate selection/threshold logic** (`LeveledManifest`, `UnifiedCompactionStrategy`, `SizeTieredCompactionStrategy`, `TimeWindowCompactionStrategy`, `ShardManager*`) — comparisons that choose *which* SSTables to compact or how to bucket/level them, not a create-vs-block divergence. (2) **Writer-switch-on-full** (`CompactionAwareWriter.maybeSwitchLocation`, `MajorLeveledCompactionWriter`, `SplittingSizeTieredCompactionWriter`, `Sharded*Writer`, e.g. `totalWrittenInCurrentWriter > maxSSTableSize`) — same non-diverging "start a new writer instead of blocking" pattern already rejected for `CommitLogSegment.java:242`/`HintsBuffer.java:190` (writing proceeds regardless of branch) — rejected under Rule 2's writer-rollover edge case even with disk now in scope, since total bytes written aren't bounded, only their chunking. (3) **Config validation / arithmetic derivation** (`validateOptions()` methods across every strategy, `Controller.java`'s remaining rows) — startup-time checks or plain derived-value math, not runtime allocation gates. No candidate survived from these three patterns. **`CompactionAwareWriter.getWriteDirectory():282`** (`availableSpace < estimatedWriteSize`) was rejected here as disk-scoped/out-of-scope — **reclassified as a live candidate 2026-09-18** once disk was brought into this folder's scope (README § Core concept); see `candidates/candidates.md`. |

## 4. Notes on Modules

### 4.1 memtable
Storage-engine module covering memtable memory allocation and pooling
(`utils/memory`, `db/memtable`). One case so far:
- **`memtable_heap_space-tryAllocate-limit`:** hard allocation cap in `SubPool.tryAllocate()`, gating `ByteBuffer.allocate()` for memtable writes. Verified via new `HeapPoolTest` unit test (2026-09-16).
- **`memtable_offheap_space-tryAllocate-limit`:** sibling case, same `SubPool.tryAllocate()` if-check on the `offHeap` `SubPool`, reached via `NativeAllocator` — gates off-heap `Region`/native memory allocation instead of `ByteBuffer`. Note: accounting call is decoupled from the physical allocation call (see case notes). Verified via existing `NativeAllocatorTest.testBookKeeping()` (2026-09-16).

### 4.2 net
Internode messaging and native (CQL client) transport module covering inbound connection handling (`net/`, `transport/`). Two cases so far:
- **`internode_application_receive_queue_capacity-acquireCapacity-queueCapacity`:** per-connection byte cap in `AbstractMessageHandler.acquireCapacity()`, gating `Message` deserialization for inbound internode traffic. Disallow branch backpressures (registers on a wait queue) rather than dropping the message. Status: pending — trigger not yet designed/run.
- **`native_transport_receive_queue_capacity-acquireCapacity-queueCapacity`:** same `AbstractMessageHandler.acquireCapacity()` if-check, reached via `CQLMessageHandler` for CQL client connections instead of internode peers. **Notable divergence from its sibling:** under the default `native_transport_throw_on_overload=false` config, the disallow branch does *not* withhold message deserialization at all — decoding proceeds regardless, only a client-visible overload flag is set. Only under the non-default `throwOnOverload=true` does it behave like the internode case (clean reject via `OverloadedException`). Flagged as Target-3-relevant (default-mode escape hatch). Status: pending — trigger not yet designed/run. Promoted from `candidates/candidates.md` 2026-09-18.

### 4.3 hints
Hint buffering and dispatch module, covering writes stashed for temporarily-unreachable replicas (`hints/`). One case so far:
- **`MAX_HINT_BUFFERS-switchCurrentBuffer-MAX_ALLOCATED_BUFFERS`:** cap (JVM system property, default 3) on how many off-heap `HintsBuffer`s the pool will ever allocate, in `HintsBufferPool.switchCurrentBuffer()`. Disallow branch blocks on `reserveBuffers.take()` until a buffer is recycled, rather than allocating a new one. Status: pending — an existing test (`HintsBufferPoolTest.testBackpressure()`, using a byteman rule at the exact `take()` call) already targets this line and just needs to be run.

### 4.4 commitlog
Storage-engine module covering the write-ahead commit log and its Change Data Capture (CDC) variant (`db/commitlog`). One case so far:
- **`cdc_total_space-processNewSegment-allowance`:** byte cap on total un-consumed CDC-hard-linked commit log segment data, compared in `CDCSizeTracker.processNewSegment()` (re-evaluated by `permitSegmentMaybe()`), which sets a per-segment `FORBIDDEN`/`PERMITTED` state read by the decision point `CommitLogSegmentManagerCDC.throwIfForbidden()` (pattern (b)). Disallow branch cleanly throws `CDCWriteException` — a real write rejection, unlike the memtable/hints/net cases' block-and-wait or backpressure semantics. Escape hatch found: `cdc_block_writes = false` bypasses the check entirely. Status: pending — an existing test (`CommitLogSegmentManagerCDCTest`'s `testWithCDCSpaceInMb()`-driven tests) already targets this exact boundary and just needs to be run.
