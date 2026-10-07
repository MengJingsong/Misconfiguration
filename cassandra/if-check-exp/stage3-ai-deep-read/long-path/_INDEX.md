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
| `max_value_size` | [`AbstractType.read():594`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/marshal/AbstractType.java#L594) | [`AbstractType.read():594`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/marshal/AbstractType.java#L594) | `marshal` | `bytearray` | (c) | 3a | [`max_value_size-read-maxValueSize`](cases/max_value_size-read-maxValueSize.md) |
| `CACHEABLE_MUTATION_SIZE_LIMIT` | [`Mutation$MutationSerializer.serialization():451`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/Mutation.java#L451) | [`Mutation$MutationSerializer.serialization():451-463`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/Mutation.java#L451-L463) | `mutation` | `cachedserialization` | (a) | 3a | [`CACHEABLE_MUTATION_SIZE_LIMIT-serialization-CACHEABLE_MUTATION_SIZE_LIMIT`](cases/CACHEABLE_MUTATION_SIZE_LIMIT-serialization-CACHEABLE_MUTATION_SIZE_LIMIT.md) |
| `local_read_size_fail_threshold` | [`ReadCommand$QuerySizeTracking.addSize():715`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/ReadCommand.java#L715) | [`ReadCommand$QuerySizeTracking.addSize():722`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/ReadCommand.java#L722) | `read_path` | `row` | (c) | 3a | [`local_read_size_fail_threshold-addSize-failBytes`](cases/local_read_size_fail_threshold-addSize-failBytes.md) |
| `row_index_read_size_fail_threshold` | [`RowIndexEntry$Serializer.checkSize():392`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/io/sstable/format/big/RowIndexEntry.java#L392) | [`RowIndexEntry$Serializer.checkSize():401`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/io/sstable/format/big/RowIndexEntry.java#L401) | `sstable_index` | `rowindexentry` | (c) | 3a | [`row_index_read_size_fail_threshold-checkSize-failThreshold`](cases/row_index_read_size_fail_threshold-checkSize-failThreshold.md) |
| `internode_application_send_queue_capacity` | [`OutboundConnection.acquireCapacity():398`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/net/OutboundConnection.java#L398) | [`OutboundConnection.enqueue():335-346`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/net/OutboundConnection.java#L335-L346) | `net` | `message` | (b) | 3a | [`internode_application_send_queue_capacity-acquireCapacity-pendingCapacityInBytes`](cases/internode_application_send_queue_capacity-acquireCapacity-pendingCapacityInBytes.md) |

<!-- Add one row per case. -->

## 2. Coverage summary

| Metric | Count |
|--------|-------|
| Modules covered | 10 |
| Total cases | 17 |
| Found via feed 3b (raw source) | 9 |
| Found via feed 3a (stage 1/2) | **8** |

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
Internode messaging and native (CQL client) transport module covering inbound and outbound connection handling (`net/`, `transport/`). Three cases so far:
- **`internode_application_receive_queue_capacity-acquireCapacity-queueCapacity`:** per-connection byte cap in `AbstractMessageHandler.acquireCapacity()`, gating `Message` deserialization for inbound internode traffic. Disallow branch backpressures (registers on a wait queue) rather than dropping the message.
- **`native_transport_receive_queue_capacity-acquireCapacity-queueCapacity`:** the same `AbstractMessageHandler.acquireCapacity()` if-check as its internode sibling, reached via `CQLMessageHandler` for CQL client connections (default 1MiB vs. 4MiB). **Its disallow branch is config-dependent, and under the default it withholds nothing** — flagged as Target-3-relevant; the mechanism and both config paths are in [the case file](cases/native_transport_receive_queue_capacity-acquireCapacity-queueCapacity.md) §5–§6b, which is authoritative. Established by deep-reading the source (feed 3b); stage 2's `transport` batch had also ranked this line. Written up 2026-09-18.
- **`internode_application_send_queue_capacity-acquireCapacity-pendingCapacityInBytes`:** the **send-side mirror** of the internode receive case: a per-connection byte allowance in `OutboundConnection.acquireCapacity()`, with the excess borrowed from a per-peer and a node-wide reserve (`ResourceLimits`), read by `enqueue()`. **Its disallow drops the message** and does not wait: the sender is not slowed, the request's callback is failed at once with `TIMEOUT`, and an ordinary write is **hinted** on the coordinator (a counter write is not). **Three findings that make the limit weaker than its name:** (1) the **per-peer reserve is read from the receive-side key** (`OutboundConnectionSettings:395`, with `withDefaults()` running before `withDefaultReserveLimits()`), so `internode_application_send_queue_reserve_endpoint_capacity` reaches no limit on the production path (derived from reading; unit step U10 and scenario C test it); (2) the ceiling is **per link** (`3·P·C` plus `min(P·E, G)`), and **at the defaults the reserves, not the capacity, are the large term** (12 MiB per peer against up to 128 MiB per peer and 512 MiB per node); (3) **expiry is lazy on a connected link:** a full link whose delivery is stalled refuses offers before `queue.add()`, where pruning otherwise runs, so its bytes stay pinned past the messages' deadlines. A peer that cannot be reached is the strictest case: no reserve is tried and the capacity is a hard cap. **Rule 3 holds in a weaker form than for the inbound twin:** the message exists before the check, so the branches diverge on its retention and serialization buffers, not its creation (§7 of the case). `ResourceLimits.Concurrent.tryAllocate():138` is cited as the mechanism, not filed (`deferred.md` §5 item 3 stays open); the delivery's frame buffers come from the networking pool (`pending.md` item 10). Found via stage-3 feed **3a** (band A1, rows `OutboundConnection.java:398` and `:416`; `:416` turned out not to be a check); written up 2026-10-07.

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
(`io/sstable/format/big`, `cache`, `service/CacheService`). Two cases so far:
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

- **`row_index_read_size_fail_threshold-checkSize-failThreshold`:** byte limit on the **estimated in-memory size of one partition's
  index entry**, compared in `RowIndexEntry.Serializer.checkSize()` (pattern (c)) before `deserialize()` builds either an `IndexedEntry` or a
  `ShallowIndexedEntry`; a refusal throws, leaves nothing in the key cache and fails the read as `READ_SIZE`. **The folder's first guard on an
  estimate rather than a measured quantity,** and the estimate is made **before** `column_index_cache_size` decides whether the entry is built,
  so at stock settings it can refuse only entries that would have been shallow and bounds no heap; it binds heap only where that case's
  threshold is raised (the upstream test sets it to 1 GiB). **The guard dominates lexically and is inert conditionally:** it returns at once
  unless a `ReadCommand` is registered on the thread, which is true only while `executeLocally()` runs, so a key-cache hit, a reloaded key
  cache, an SSTable opened lazily after it returns (derived from the lower-bound merge, tested by an arm) and every range scan are not checked.
  **Off by default** (limit `null`, master switch false). The sibling of `local_read_size_fail_threshold` (same switch and reporting channel),
  but it does not require the coordinator's `trackWarnings` flag, so an unflagged read turns the abort into an `UNKNOWN` failure (derived).
  Its test design reads the **real weight** of what was built from the key cache (a refused read leaves it unchanged) and the check's own
  operands from a Byteman rule on a node. Found via stage-3 feed **3a** (band A1, row `RowIndexEntry.java:392`); written up 2026-10-06.

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

### 3.7 marshal
Value types and their (de)serialization (`db/marshal`; the deserializers that call into it are in `db/rows`, `db` and `db/commitlog`). One case so far:
- **`max_value_size-read-maxValueSize`:** per-value sanity bound on a length decoded from a stream, compared in `AbstractType.read()` and enforced as a
  guard (pattern (c)) before `accessor.read(in, l)` allocates `new byte[l]` at full size, before any byte is read. **The guard dominates the allocation for every
  production caller** (four call sites, all passing the configured limit; the unguarded `readBuffer(in)` overload has no production caller) **but not the sibling
  primitives** (`ByteBufferUtil.readWithVIntLength` and `readWithLength`, 29 call sites with no limit, including the partition key of every inbound partition) **and
  not the write side**: nothing compares a value with it when it is written, so a value above the limit is accepted, held in the memtable and flushed, and fails only
  when read back — **as corruption**: the SSTable is marked suspect and left out of compaction, an inbound message is dropped, and a commit-log replay stops the node
  starting (replay **is** guarded, unlike `max_mutation_size`'s). **At stock settings a client cannot reach it:** the default 256 MiB is above every write-side cap, so it
  fires on damaged data only; and only the cell-value call site can fire on data a client wrote, since partition keys and the clustering values of row writes are limited to 64 KiB.
  A **per-item** bound like `max_mutation_size`; the node-wide ceiling is `limit × N` (§8). The first case whose test design measures the **bytes a thread allocates**
  across the check (`ThreadMXBean`, unit tier) and traces **allocation requests** with Byteman on a node. Found via stage-3 feed **3a** (band A1, row
  `AbstractType.java:594`); written up 2026-10-06.

### 3.8 mutation
The write object and its serialization (`db/Mutation`, `io/util/TeeDataInputPlus`). One case so far:
- **`CACHEABLE_MUTATION_SIZE_LIMIT-serialization-CACHEABLE_MUTATION_SIZE_LIMIT`:** byte threshold on **one mutation's serialized size**, deciding whether the mutation keeps a
  serialized copy on the heap (`CachedSerialization`, a `byte[]` of exactly that size) or only its size (`SizeOnlyCacheableSerialization`). **The second case where both outcomes
  allocate**, after `column_index_cache_size`: what the check withholds is a **copy** beside the mutation's own heap, and the divergence is in retained size. **Two check sites on one
  constraint, of different patterns:** `Mutation$MutationSerializer.serialization():451` is **(a)** and decides the copy for every mutation the node serializes; the receive side,
  `TeeDataInputPlus.maybeWrite():58`, is (a) for each write into a scratch buffer and sets a flag (`limitReached`) that `Mutation.deserialize():518` reads to decide the copy (b), and it is
  reached from every deserialization (network, commit-log replay, hints, batchlog, counters, schema). The two agree on the boundary: a copy is kept iff *T* < limit. **A per-copy bound:**
  the node-wide extra heap is about `limit × N`, *N* being the live mutations just under the limit, which nothing here or in the in-flight request caps bounds. **A JVM property,
  restart-only** (`cassandra.cacheable_mutation_size_limit_bytes`, default 1,000,000; no yaml key or JMX), frozen in a `static final` of `Mutation`. **The disallow is not a refusal:**
  the mutation is still sent, logged and applied; the node spends CPU, re-walking the partition updates at every later serialization, instead of memory. **An escape value:** a limit of
  0 or less caches nothing on the serialize side and **removes the bound on the receive side** (`limit <= 0` is the tee's "unbounded"), so the two sites read it in opposite senses.
  `validateSize()` reaches this check, so measuring a mutation below the limit builds its copy (`max_mutation_size`). Its node tier reaches the **receive site on a real node through
  commit-log replay**, holding writes in memory with a Byteman delay and counting live copies with a class histogram. Found via stage-3 feed **3a** (band A1, rows
  `Mutation.java:451` and `TeeDataInputPlus.java:58`); written up 2026-10-06.

### 3.9 read_path
Replica-side read and the guardrails wrapped around it (`db/ReadCommand`, `db/transform`, `service/reads/thresholds`). One case so far:
- **`local_read_size_fail_threshold-addSize-failBytes`:** running total of the heap sizes of what **one local read command** pulls from storage,
  compared in `ReadCommand.QuerySizeTracking.addSize()` (pattern (c)); reaching the limit (`>=`) throws `LocalReadSizeTooLargeException`. **Per
  command, not per query:** each page of a paged query and each partition of an `IN` read has its own counter, so a query paged below the limit is
  never aborted. **A guard in a lazy pipeline:** it runs after the row that crosses the limit has been built (a one-row overshoot) and dominates
  every later row, but not a names-filter point read, which builds its rows into an `ImmutableBTreePartition` before the guard is attached. It
  **counts what storage yields before any filtering**, so a filtered read that returns nothing can still abort. **The disallow is swallowed by the
  replica, which answers empty with a note attached;** the coordinator decides whether the query fails (with a replica to spare it is only a
  warning). **Off by default** (limit `null`, master switch false) and **live-settable**. The first case whose cluster tier measures the bytes a
  replica thread allocates across the guard, with a Byteman rule on the read runnable. Found via stage-3 feed **3a** (band A1, row
  `ReadCommand.java:715`); written up 2026-10-06.
