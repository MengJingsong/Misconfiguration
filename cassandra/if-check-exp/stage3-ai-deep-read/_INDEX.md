# If-Check Cases — Master Index

Navigation hub and progress tracker for all if-check cases.
See [README.md](README.md) for the format.

**Source:** apache/cassandra @ tag `cassandra-5.0.9`
**Pattern legend** (README §3.2): **(a)** the capacity check is the decision · **(b)** the check sets a verdict (flag, enum, return value) that a separate decision point reads · **(c)** guard clause(s) before an allocation outside any branch

## 1. Master Index

| Constraint name | Capacity check | Decision point | Module | Object | Pattern | Feed | File |
|-----------------|----------------|----------------|--------|--------|---------|------|------|
| `memtable_heap_space` | [`SubPool.tryAllocate():156`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/utils/memory/MemtablePool.java#L156) | [`MemtableAllocator.SubAllocator.allocate():169-197`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/utils/memory/MemtableAllocator.java#L169-L197) | `memtable` | `bytebuffer` | (b) | 3b | [`memtable_heap_space-tryAllocate-limit`](cases/memtable_heap_space-tryAllocate-limit.md) |
| `memtable_offheap_space` | [`SubPool.tryAllocate():156`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/utils/memory/MemtablePool.java#L156) | [`MemtableAllocator.SubAllocator.allocate():169-197`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/utils/memory/MemtableAllocator.java#L169-L197) | `memtable` | `region` | (b) | 3b | [`memtable_offheap_space-tryAllocate-limit`](cases/memtable_offheap_space-tryAllocate-limit.md) |
| `internode_application_receive_queue_capacity` | [`AbstractMessageHandler.acquireCapacity():419`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/net/AbstractMessageHandler.java#L419) | [`InboundMessageHandler.processOneContainedMessage():139-151`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/net/InboundMessageHandler.java#L139-L151) | `net` | `message` | (b) | 3b | [`internode_application_receive_queue_capacity-acquireCapacity-queueCapacity`](cases/internode_application_receive_queue_capacity-acquireCapacity-queueCapacity.md) |
| `native_transport_receive_queue_capacity` | [`AbstractMessageHandler.acquireCapacity():419`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/net/AbstractMessageHandler.java#L419) | [`CQLMessageHandler.processOneContainedMessage():196-256`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/transport/CQLMessageHandler.java#L196-L256) | `net` | `message` | (b) | 3b | [`native_transport_receive_queue_capacity-acquireCapacity-queueCapacity`](cases/native_transport_receive_queue_capacity-acquireCapacity-queueCapacity.md) |
| `MAX_HINT_BUFFERS` | [`HintsBufferPool.switchCurrentBuffer():113`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/hints/HintsBufferPool.java#L113) | [`HintsBufferPool.switchCurrentBuffer():113`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/hints/HintsBufferPool.java#L113) | `hints` | `hintsbuffer` | (a) | 3b | [`MAX_HINT_BUFFERS-switchCurrentBuffer-MAX_ALLOCATED_BUFFERS`](cases/MAX_HINT_BUFFERS-switchCurrentBuffer-MAX_ALLOCATED_BUFFERS.md) |
| `cdc_total_space` | [`CDCSizeTracker.processNewSegment():335`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/commitlog/CommitLogSegmentManagerCDC.java#L335) | [`throwIfForbidden():214`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/commitlog/CommitLogSegmentManagerCDC.java#L214) | `commitlog` | `allocation` | (b) | 3b | [`cdc_total_space-processNewSegment-allowance`](cases/cdc_total_space-processNewSegment-allowance.md) |

| `DataDirectory_getAvailableSpace` | [`CompactionAwareWriter.getWriteDirectory():282`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/compaction/writers/CompactionAwareWriter.java#L282) | [`CompactionAwareWriter.getWriteDirectory():283-286`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/compaction/writers/CompactionAwareWriter.java#L283-L286) | `compaction` | `sstablewriter` | (c) | 3b | [`DataDirectory_getAvailableSpace-getWriteDirectory-availableSpace`](cases/DataDirectory_getAvailableSpace-getWriteDirectory-availableSpace.md) |

<!-- Add one row per case. -->

## 2. Coverage summary

| Metric | Count |
|--------|-------|
| Modules covered | 5 |
| Total cases | 7 |
| Found via feed 3b (raw source) | 7 |
| Found via feed 3a (stage 1/2) | 0 |

> **Every case so far came from feed 3b — reading the source directly.**
> Stage 1/2 have surfaced and ranked rows (some matching these same lines),
> but no case has yet been *established* from that queue: the 4 P1
> candidates awaiting write-up would be the first. This is the main evidence
> that feed 3b is not optional.
>
> Feed counts are not a progress bar. Only 3a has a denominator — its
> remaining work is sized in
> [`stage2-ai-preprocessing/README.md`](../stage2-ai-preprocessing/README.md)'s
> "Progress at a glance". 3b is unbounded, so there is no percentage for it.

## 3. Notes on Modules

### 3.0 compaction

- **`DataDirectory_getAvailableSpace-getWriteDirectory-availableSpace`:** the
  folder's first **disk-scoped** case and first **pattern-(c)** case. A guard
  in `CompactionAwareWriter.getWriteDirectory()` refuses to start a compaction
  whose estimated output exceeds the target data directory's free space
  (device usable bytes minus the configurable `min_free_space_per_drive`,
  default 50MiB). Where reached, the disallow outcome is a clean
  `RuntimeException` before any writer or file exists.
  **Notable finding — the guard does not dominate the allocation.** Its only
  caller, `maybeSwitchLocation()`, consults it solely when the table has no
  disk boundaries; on the `diskBoundaries != null` path — the **default**,
  with `Murmur3Partitioner` on a node owning ranges — it selects a directory
  by key range and creates the `SSTableWriter` with **no disk-space check at
  all**. Flagged as Target-3-relevant; a stronger default-mode gap than the
  memtable or native-transport escape hatches, since the check is not
  overridden but never executed. Found via stage-3 feed **3b** (direct AI
  reading), which is also what exposed the non-domination — the CodeQL row
  alone shows only the comparison.

### 3.1 memtable
Storage-engine module covering memtable memory allocation and pooling
(`utils/memory`, `db/memtable`). One case so far:
- **`memtable_heap_space-tryAllocate-limit`:** hard allocation cap in `SubPool.tryAllocate()`, gating `ByteBuffer.allocate()` for memtable writes. Verified via new `HeapPoolTest` unit test (2026-09-16).
- **`memtable_offheap_space-tryAllocate-limit`:** sibling case, same `SubPool.tryAllocate()` if-check on the `offHeap` `SubPool`, reached via `NativeAllocator` — gates off-heap `Region`/native memory allocation instead of `ByteBuffer`. Note: accounting call is decoupled from the physical allocation call (see case notes). Verified via existing `NativeAllocatorTest.testBookKeeping()` (2026-09-16).

### 3.2 net
Internode messaging and native (CQL client) transport module covering inbound connection handling (`net/`, `transport/`). Two cases so far:
- **`internode_application_receive_queue_capacity-acquireCapacity-queueCapacity`:** per-connection byte cap in `AbstractMessageHandler.acquireCapacity()`, gating `Message` deserialization for inbound internode traffic. Disallow branch backpressures (registers on a wait queue) rather than dropping the message.
- **`native_transport_receive_queue_capacity-acquireCapacity-queueCapacity`:** same `AbstractMessageHandler.acquireCapacity()` if-check, reached via `CQLMessageHandler` for CQL client connections instead of internode peers. **Notable divergence from its sibling:** under the default `native_transport_throw_on_overload=false` config, the disallow branch does *not* withhold message deserialization at all — decoding proceeds regardless, only a client-visible overload flag is set. Only under the non-default `throwOnOverload=true` does it behave like the internode case (clean reject via `OverloadedException`). Flagged as Target-3-relevant (default-mode escape hatch). Found via stage-3 feed 3a (see `stage2-ai-preprocessing/positives.md`), written up 2026-09-18.

### 3.3 hints
Hint buffering and dispatch module, covering writes stashed for temporarily-unreachable replicas (`hints/`). One case so far:
- **`MAX_HINT_BUFFERS-switchCurrentBuffer-MAX_ALLOCATED_BUFFERS`:** cap (JVM system property, default 3) on how many off-heap `HintsBuffer`s the pool will ever allocate, in `HintsBufferPool.switchCurrentBuffer()`. Disallow branch blocks on `reserveBuffers.take()` until a buffer is recycled, rather than allocating a new one.

### 3.4 commitlog
Storage-engine module covering the write-ahead commit log and its Change Data Capture (CDC) variant (`db/commitlog`). One case so far:
- **`cdc_total_space-processNewSegment-allowance`:** byte cap on total un-consumed CDC-hard-linked commit log segment data, compared in `CDCSizeTracker.processNewSegment()` (re-evaluated by `permitSegmentMaybe()`), which sets a per-segment `FORBIDDEN`/`PERMITTED` state read by the decision point `CommitLogSegmentManagerCDC.throwIfForbidden()` (pattern (b)). Disallow branch cleanly throws `CDCWriteException` — a real write rejection, unlike the memtable/hints/net cases' block-and-wait or backpressure semantics. Escape hatch found: `cdc_block_writes = false` bypasses the check entirely.
