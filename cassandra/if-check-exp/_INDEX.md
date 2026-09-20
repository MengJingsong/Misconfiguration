# If-Check Cases — Master Index

Navigation hub and progress tracker for all if-check cases.
See [README.md](README.md) for the format.

**Source:** apache/cassandra @ tag `cassandra-5.0.9`
**Status legend:** `pending` · `in-progress` · `verified`

| Module | Limit | Object | Location | Status | File |
|--------|-------|--------|----------|--------|------|
| `memtable` | `memtable_heap_space` | `bytebuffer` | [`SubPool.tryAllocate():156`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/utils/memory/MemtablePool.java#L156) | verified | [link](memtable/memtable_heap_space-bytebuffer.md) |
| `memtable` | `memtable_offheap_space` | `region` | [`SubPool.tryAllocate():156`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/utils/memory/MemtablePool.java#L156) | verified | [link](memtable/memtable_offheap_space-region.md) |
| `net` | `internode_application_receive_queue_capacity` | `message` | [`AbstractMessageHandler.acquireCapacity():419`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/net/AbstractMessageHandler.java#L419) | pending | [link](net/internode_application_receive_queue_capacity-message.md) |
| `hints` | `HintsBufferPool_MAX_ALLOCATED_BUFFERS` | `hintsbuffer` | [`HintsBufferPool.switchCurrentBuffer():113`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/hints/HintsBufferPool.java#L113) | pending | [link](hints/HintsBufferPool_MAX_ALLOCATED_BUFFERS-hintsbuffer.md) |
| `commitlog` | `cdc_total_space` | `allocation` | [`CommitLogSegmentManagerCDC.throwIfForbidden():214`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/commitlog/CommitLogSegmentManagerCDC.java#L214) | pending | [link](commitlog/cdc_total_space-allocation.md) |

<!-- Add one row per case. -->

## Coverage summary

| Metric | Count |
|--------|-------|
| Modules covered | 4 |
| Total cases | 5 |
| Verified | 2 |
| Pending / in-progress | 3 |

## Lines considered and rejected

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

## Notes on Modules

### memtable
Storage-engine module covering memtable memory allocation and pooling
(`utils/memory`, `db/memtable`). One case so far:
- **`memtable_heap_space-bytebuffer`:** hard allocation cap in `SubPool.tryAllocate()`, gating `ByteBuffer.allocate()` for memtable writes. Verified via new `HeapPoolTest` unit test (2026-09-16).
- **`memtable_offheap_space-region`:** sibling case, same `SubPool.tryAllocate()` if-check on the `offHeap` `SubPool`, reached via `NativeAllocator` — gates off-heap `Region`/native memory allocation instead of `ByteBuffer`. Note: accounting call is decoupled from the physical allocation call (see case notes). Verified via existing `NativeAllocatorTest.testBookKeeping()` (2026-09-16).

### net
Internode messaging module covering inbound connection handling (`net/`). One case so far:
- **`internode_application_receive_queue_capacity-message`:** per-connection byte cap in `AbstractMessageHandler.acquireCapacity()`, gating `Message` deserialization for inbound internode traffic. Disallow branch backpressures (registers on a wait queue) rather than dropping the message. Status: pending — trigger not yet designed/run. Sibling candidate noted but not filed: the CQL/native-transport side of the same check (`native_transport_receive_queue_capacity`).

### hints
Hint buffering and dispatch module, covering writes stashed for temporarily-unreachable replicas (`hints/`). One case so far:
- **`HintsBufferPool_MAX_ALLOCATED_BUFFERS-hintsbuffer`:** cap (JVM system property, default 3) on how many off-heap `HintsBuffer`s the pool will ever allocate, in `HintsBufferPool.switchCurrentBuffer()`. Disallow branch blocks on `reserveBuffers.take()` until a buffer is recycled, rather than allocating a new one. Status: pending — an existing test (`HintsBufferPoolTest.testBackpressure()`, using a byteman rule at the exact `take()` call) already targets this line and just needs to be run.

### commitlog
Storage-engine module covering the write-ahead commit log and its Change Data Capture (CDC) variant (`db/commitlog`). One case so far:
- **`cdc_total_space-allocation`:** byte cap on total un-consumed CDC-hard-linked commit log segment data, enforced in `CommitLogSegmentManagerCDC.throwIfForbidden()` (fed by the byte-count comparison in the sibling `permitSegmentMaybe()`). Disallow branch cleanly throws `CDCWriteException` — a real write rejection, unlike the memtable/hints/net cases' block-and-wait or backpressure semantics. Escape hatch found: `cdc_block_writes = false` bypasses the check entirely. Status: pending — an existing test (`CommitLogSegmentManagerCDCTest`'s `testWithCDCSpaceInMb()`-driven tests) already targets this exact boundary and just needs to be run.
