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
| `max_space_usable_for_compactions_in_percentage` | [`Directories.hasDiskSpaceForCompactionsAndStreams():551`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/Directories.java#L551) | [`CompactionTask.buildCompactionCandidatesForAvailableDiskSpace():412-413`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/compaction/CompactionTask.java#L412-L413) | `compaction` | `compactionwriter` | (b) | 3a | [`max_space_usable_for_compactions_in_percentage-hasDiskSpaceForCompactionsAndStreams-availableForCompaction`](cases/max_space_usable_for_compactions_in_percentage-hasDiskSpaceForCompactionsAndStreams-availableForCompaction.md) |
| `column_index_cache_size` | [`BigFormatPartitionWriter.indexSamples():113`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/io/sstable/format/big/BigFormatPartitionWriter.java#L113) | [`RowIndexEntry.create():227-238`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/io/sstable/format/big/RowIndexEntry.java#L227-L238) | `sstable_index` | `rowindexentry` | (b) | 3b | [`column_index_cache_size-indexSamples-cacheSizeThreshold`](cases/column_index_cache_size-indexSamples-cacheSizeThreshold.md) |
| `max_hints_size_per_host` | [`StorageProxy.shouldHint():2492`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/service/StorageProxy.java#L2492) | [`StorageProxy.sendToHintedReplicas():1552-1558`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/service/StorageProxy.java#L1552-L1558) | `hints` | `hint` | (b) | 3a | [`max_hints_size_per_host-shouldHint-maxHintsSize`](cases/max_hints_size_per_host-shouldHint-maxHintsSize.md) |
| `file_cache_size` | [`BufferPool$GlobalPool.allocateMoreChunks():443`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/utils/memory/BufferPool.java#L443) | [`BufferPool$GlobalPool.allocateMoreChunks():443-453`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/utils/memory/BufferPool.java#L443-L453) | `buffer_pool` | `chunk` | (a) | 3b | [`file_cache_size-allocateMoreChunks-memoryUsageThreshold`](cases/file_cache_size-allocateMoreChunks-memoryUsageThreshold.md) |
| `max_mutation_size` | [`Mutation.validateSize():172`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/Mutation.java#L172) | [`CommitLog.add():304`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/commitlog/CommitLog.java#L304) | `commitlog` | `allocation` | (c) | 3a | [`max_mutation_size-validateSize-MAX_MUTATION_SIZE`](cases/max_mutation_size-validateSize-MAX_MUTATION_SIZE.md) |

<!-- Add one row per case. -->

## 2. Coverage summary

| Metric | Count |
|--------|-------|
| Modules covered | 7 |
| Total cases | 12 |
| Found via feed 3b (raw source) | 9 |
| Found via feed 3a (stage 1/2) | **3** |

> **Feed 3a has its first case, as of 2026-09-28.**
> `max_space_usable_for_compactions_in_percentage` was surfaced by the first
> stage-2 batch and is the first case established from that queue — and it is
> worth recording *how*: the row's own reported comparisons were both noise
> (`size() > 0`, `sstablesRemoved > 0`), and what made it a case was the
> **method name** on the helper row, which pointed the read two calls deeper.
> A 3a row's value is not always the comparison it reports.
>
> The other eight came from feed 3b — reading the source directly. That
> remains the main evidence 3b is not optional: it found the `cdc_total_space`
> ternary, which stage 1 cannot surface at all.
>
> Feed counts are not a progress bar. Only 3a has a denominator — its
> remaining work is sized in
> [`stage2-ai-preprocessing/README.md`](../../stage2-ai-preprocessing/README.md)'s
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

- **`max_space_usable_for_compactions_in_percentage-hasDiskSpaceForCompactionsAndStreams-availableForCompaction`:**
  the second compaction disk case, and **the folder's first case from feed
  3a**. An admission gate that runs *before* a compaction task starts: it sums
  this compaction's expected output with the remaining output of every
  compaction already in flight, per file store, and compares that against
  `(usable bytes − min_free_space_per_drive) × max_space_usable_for_compactions_in_percentage`
  (default 95%). Distinctive in two ways. Its disallow outcome is **not a
  refusal but a negotiation** — `reduceScopeForLimitedSpace()` drops the
  largest input SSTable and re-checks, repeatedly, so a node under disk
  pressure compacts in smaller units rather than stopping; the abort and its
  `RuntimeException` come only at the bottom of that ladder. And its
  dose-response **runs the opposite way to every other case here**: lowering
  the limit means less compaction, hence *more* data on disk, so the case must
  be judged on the shrink/abort metrics and admitted compaction size, not on
  `du`. Two escape hatches recorded: the check is skipped per table over JMX
  (`compactionDiskSpaceCheck`, `OperationType.COMPACTION` only), and an
  exception while computing it is **treated as allow** (fail-open).
  Complements rather than duplicates `DataDirectory_getAvailableSpace` — see
  that case's §11 for the axis-by-axis comparison.

### 3.1 memtable
Storage-engine module covering memtable memory allocation and pooling
(`utils/memory`, `db/memtable`). One case so far:
- **`memtable_heap_space-tryAllocate-limit`:** allocation cap in `SubPool.tryAllocate()`, gating `ByteBuffer.allocate()` for memtable writes via `HeapPool` (reached only under `memtable_allocation_type: unslabbed_heap_buffers`). Disallow parks the writer; a `markBlocking()` write overshoots the limit, so the cap is not hard. A unit test, `HeapPoolTest`, was run on 2026-09-16, before stage 4 existed — prior evidence, not a stage-4 result.
- **`memtable_offheap_space-tryAllocate-limit`:** sibling case, same `SubPool.tryAllocate()` if-check on the `offHeap` `SubPool`, reached via `NativeAllocator` — gates off-heap `Region`/native memory allocation instead of `ByteBuffer`. Note: accounting call is decoupled from the physical allocation call (see case notes). Verified via existing `NativeAllocatorTest.testBookKeeping()` (2026-09-16).

### 3.2 net
Internode messaging and native (CQL client) transport module covering inbound connection handling (`net/`, `transport/`). Two cases so far:
- **`internode_application_receive_queue_capacity-acquireCapacity-queueCapacity`:** per-connection byte cap in `AbstractMessageHandler.acquireCapacity()`, gating `Message` deserialization for inbound internode traffic. Disallow branch backpressures (registers on a wait queue) rather than dropping the message.
- **`native_transport_receive_queue_capacity-acquireCapacity-queueCapacity`:** the same `AbstractMessageHandler.acquireCapacity()` if-check as its internode sibling, reached via `CQLMessageHandler` for CQL client connections (default 1MiB vs. 4MiB). **Its disallow branch is config-dependent, and under the default it withholds nothing** — flagged as Target-3-relevant; the mechanism and both config paths are in [the case file](cases/native_transport_receive_queue_capacity-acquireCapacity-queueCapacity.md) §5–§6b, which is authoritative. Established by deep-reading the source (feed 3b); stage 2's `transport` batch had also ranked this line. Written up 2026-09-18.

### 3.3 hints
Hint buffering and dispatch module, covering writes stashed for temporarily-unreachable replicas (`hints/`). One case so far:
- **`MAX_HINT_BUFFERS-switchCurrentBuffer-MAX_ALLOCATED_BUFFERS`:** cap (JVM system property, default 3) on how many off-heap `HintsBuffer`s the pool will ever allocate, in `HintsBufferPool.switchCurrentBuffer()`. Disallow branch blocks on `reserveBuffers.take()` until a buffer is recycled, rather than allocating a new one.

- **`max_hints_size_per_host-shouldHint-maxHintsSize`:** the other half of the
  hints story — this one bounds the **hint files on disk**, per destination
  host, where `MAX_HINT_BUFFERS` bounds the off-heap buffers. **Disabled by
  default** (`0B`, and `if (maxHintsSize > 0)` skips the comparison), which is
  a third kind of default-mode gap: not overridden like the memtable hatch, not
  unreached like the compaction guard, simply not switched on. Its disallow is
  the folder's first that **loses data** — the hint is silently skipped, the
  write still succeeds, and the replica stays short of the mutation until a
  repair. Also the first case whose pattern-(b) verdict is read at **seven**
  decision points. No metric fires on the disallow path, unlike the adjacent
  hint-window rejection four lines above.

### 3.4 commitlog
Storage-engine module covering the write-ahead commit log and its Change Data Capture (CDC) variant (`db/commitlog`). Two cases so far:
- **`cdc_total_space-processNewSegment-allowance`:** byte cap on total un-consumed CDC-hard-linked commit log segment data, compared in `CDCSizeTracker.processNewSegment()` (re-evaluated by `permitSegmentMaybe()`), which sets a per-segment `FORBIDDEN`/`PERMITTED` state read by the decision point `CommitLogSegmentManagerCDC.throwIfForbidden()` (pattern (b)). Disallow branch cleanly throws `CDCWriteException` — a real write rejection, unlike the memtable/hints/net cases' block-and-wait or backpressure semantics. `cdc_block_writes = false` turns off the rejection but not the cap: the tracker deletes the oldest un-consumed CDC links to stay under the allowance (stage 4, 2026-10-01), so data is lost instead of writes failing. Stage 4 closed this case 2026-10-01: with no consumer the node keeps `⌊limit/segmentSize⌋` links, or one more when the check's counter is stale (at most `limit + segmentSize` bytes).

- **`max_mutation_size-validateSize-MAX_MUTATION_SIZE`:** byte cap on **one commit-log entry**, compared in
  `Mutation.validateSize()` (second site `CounterMutation.validateSize()`) and enforced as the first statement of `CommitLog.add()`. Pattern (c), and
  **the guard dominates the allocation**: the off-heap serialization buffer and the segment reservation both come after it; disallow is a clean
  `InvalidRequestException`-family throw that reserves nothing. **A per-item bound, the folder's first:** it caps each entry, not any total, so the node-wide ceiling is
  `limit × N` (§8). Distinctive points: the same verdict is read at **five call sites** (coordinator, replica verb handler, commit log, read repair, virtual
  tables) of which only the commit-log one runs before new allocation, so the case rests on it; the limit is **frozen at class initialization**
  (an interface constant, restart-only) and **derived from `commitlog_segment_size / 2`** when unset, which also derives the CQL transport's message cap and
  the hints buffer size, so a sweep must hold them fixed; **at stock settings the transport's own caps equal it, so client writes are shadowed**; **replay is
  unguarded**; counter refusals are not metered. A logged batch is the client-reachable way to the commit-log site (the batchlog entry). Found via
  stage-3 feed **3a** (band A1, rows `Mutation.java:172` and `CounterMutation.java:94`); written up 2026-10-06.


### 3.5 sstable_index
On-disk index entries for wide partitions and the key cache that holds them
(`io/sstable/format/big`, `cache`, `service/CacheService`). One case so far:
- **`column_index_cache_size-indexSamples-cacheSizeThreshold`:** byte
  threshold on one partition's serialized block index, deciding whether the
  index is retained on heap as an `IndexInfo[]` (`IndexedEntry`) or left on
  disk behind a file position (`ShallowIndexedEntry`). **The first case where
  both outcomes allocate** — the divergence is in retained size, not in
  existence, and the classes' own `unsharedHeapSize()` implementations state
  it directly. Three check sites on one constraint, and they are not all the
  same pattern: the two write-path sites are (b), while
  `RowIndexEntry$Serializer.deserialize():360` is **(a)** and is the site that
  governs steady-state heap. **The ceiling claim is per entry, not node-wide** —
  cached entries are charged their `unsharedHeapSize()` against
  `key_cache_size`, so raising the threshold buys fewer, fatter cache entries
  rather than more heap; the uncapped terms are the per-writer
  `DataOutputBuffer` of `2 × threshold` and transient flush/compaction
  entries. No flag-style escape hatch exists — but the check is
  **format-scoped** (BIG only; BTI does not reach it), and the read-path site
  reads config **live per deserialization**, so a JMX change alters the
  memory behaviour of already-written SSTables with no rewrite.

### 3.6 buffer_pool
Off-heap buffer pooling for file reads and networking (`utils/memory/BufferPool`,
`utils/memory/BufferPools`). One case so far:
- **`file_cache_size-allocateMoreChunks-memoryUsageThreshold`:** byte ceiling on
  the `chunk-cache` pool's reserved off-heap memory, gating creation of its
  8 MiB macro chunks. **The folder's clearest pool-versus-resource case:** the
  disallow branch withholds the `Chunk`, but the caller then allocates the
  buffer straight from the OS via `ByteBuffer.allocateDirect`, counted as
  `overflowMemoryUsage` with **no ceiling of its own** — so `file_cache_size`
  bounds the pool, not the node's off-heap footprint. Uniquely well
  instrumented: `BufferPoolMetrics` publishes the limit (`Capacity`), the
  operand (`Size`) and the escape hatch (`OverflowSize`) as gauges, so §8's
  claim can be settled rather than merely predicted. Two config entries drive
  one check — the `networking_cache_size` sibling is a separate case, not yet
  filed (`pending.md`). Source bug noted: `MACRO_CHUNK_SIZE`'s comment says
  1 MiB, the arithmetic gives 8 MiB.
