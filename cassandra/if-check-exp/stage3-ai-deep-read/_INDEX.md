# If-Check Cases — Master Index

Navigation hub and progress tracker for all case files of both agents.
See [README.md](README.md) for the format. Each case file is named `<stem>--guided.md`
or `<stem>--autonomous.md`; the Agent column repeats the suffix. Estimate is `positive`, `negative` or `undetermined` (a prediction from the source; stage 4 confirms or refutes it); Ground names the rule or reason for a negative. A column the
autonomous template does not ask for (decision point, module, object, pattern) is `—`
on an autonomous row.

**Source:** apache/cassandra @ tag `cassandra-5.0.9`
**Pattern legend** (README §3.2; the pattern is recorded in each guided case file's §1): **(a)** the capacity check is the decision · **(b)** the check sets a verdict (flag, enum, return value) that a separate decision point reads · **(c)** guard clause(s) before an allocation outside any branch

## 1. Master Index

The constraint name links to the case file and the Stage 4 cell to its results file. Since 2026-10-20 the table keeps only these four columns; the capacity check, decision point, module, object, pattern, feed and ground of each case are in the case file (guided: §1, §3 and §10; autonomous: the header table and section A).

| Constraint (→ case file) | Agent | Estimate | Stage 4 |
|---|---|---|---|
| [`memtable_heap_space`](cases/memtable_heap_space-tryAllocate-limit--guided.md) | guided | positive | [Confirmed](../stage4-runtime-verification/results/memtable_heap_space-tryAllocate-limit--guided.md) |
| [`memtable_offheap_space`](cases/memtable_offheap_space-tryAllocate-limit--guided.md) | guided | positive | [Confirmed](../stage4-runtime-verification/results/memtable_offheap_space-tryAllocate-limit--guided.md) |
| [`internode_application_receive_queue_capacity`](cases/internode_application_receive_queue_capacity-acquireCapacity-queueCapacity--guided.md) | guided | positive | [Confirmed](../stage4-runtime-verification/results/internode_application_receive_queue_capacity-acquireCapacity-queueCapacity--guided.md) |
| [`native_transport_receive_queue_capacity`](cases/native_transport_receive_queue_capacity-acquireCapacity-queueCapacity--guided.md) | guided | positive | [Confirmed](../stage4-runtime-verification/results/native_transport_receive_queue_capacity-acquireCapacity-queueCapacity--guided.md) |
| [`MAX_HINT_BUFFERS`](cases/MAX_HINT_BUFFERS-switchCurrentBuffer-MAX_ALLOCATED_BUFFERS--guided.md) | guided | positive | [Confirmed](../stage4-runtime-verification/results/MAX_HINT_BUFFERS-switchCurrentBuffer-MAX_ALLOCATED_BUFFERS--guided.md) |
| [`cdc_total_space`](cases/cdc_total_space-processNewSegment-allowance--guided.md) | guided | positive | [Confirmed](../stage4-runtime-verification/results/cdc_total_space-processNewSegment-allowance--guided.md) |
| [`DataDirectory_getAvailableSpace`](cases/DataDirectory_getAvailableSpace-getWriteDirectory-availableSpace--guided.md) | guided | positive | [Confirmed](../stage4-runtime-verification/results/DataDirectory_getAvailableSpace-getWriteDirectory-availableSpace--guided.md) |
| [`max_space_usable_for_compactions_in_percentage`](cases/max_space_usable_for_compactions_in_percentage-hasDiskSpaceForCompactionsAndStreams-availableForCompaction--guided.md) | guided | positive | [Confirmed](../stage4-runtime-verification/results/max_space_usable_for_compactions_in_percentage-hasDiskSpaceForCompactionsAndStreams-availableForCompaction--guided.md) |
| [`column_index_cache_size`](cases/column_index_cache_size-indexSamples-cacheSizeThreshold--guided.md) | guided | positive | [Confirmed](../stage4-runtime-verification/results/column_index_cache_size-indexSamples-cacheSizeThreshold--guided.md) |
| [`max_hints_size_per_host`](cases/max_hints_size_per_host-shouldHint-maxHintsSize--guided.md) | guided | positive | [Confirmed](../stage4-runtime-verification/results/max_hints_size_per_host-shouldHint-maxHintsSize--guided.md) |
| [`file_cache_size`](cases/file_cache_size-allocateMoreChunks-memoryUsageThreshold--guided.md) | guided | positive | [Confirmed](../stage4-runtime-verification/results/file_cache_size-allocateMoreChunks-memoryUsageThreshold--guided.md) |
| [`max_mutation_size`](cases/max_mutation_size-validateSize-MAX_MUTATION_SIZE--guided.md) | guided | positive | [Confirmed](../stage4-runtime-verification/results/max_mutation_size-validateSize-MAX_MUTATION_SIZE--guided.md) |
| [`max_value_size`](cases/max_value_size-read-maxValueSize--guided.md) | guided | positive | [Confirmed](../stage4-runtime-verification/results/max_value_size-read-maxValueSize--guided.md) |
| [`CACHEABLE_MUTATION_SIZE_LIMIT`](cases/CACHEABLE_MUTATION_SIZE_LIMIT-serialization-CACHEABLE_MUTATION_SIZE_LIMIT--guided.md) | guided | positive | [Confirmed](../stage4-runtime-verification/results/CACHEABLE_MUTATION_SIZE_LIMIT-serialization-CACHEABLE_MUTATION_SIZE_LIMIT--guided.md) |
| [`local_read_size_fail_threshold`](cases/local_read_size_fail_threshold-addSize-failBytes--guided.md) | guided | positive | [Confirmed](../stage4-runtime-verification/results/local_read_size_fail_threshold-addSize-failBytes--guided.md) |
| [`row_index_read_size_fail_threshold`](cases/row_index_read_size_fail_threshold-checkSize-failThreshold--guided.md) | guided | positive | [Confirmed](../stage4-runtime-verification/results/row_index_read_size_fail_threshold-checkSize-failThreshold--guided.md) |
| [`internode_application_send_queue_capacity`](cases/internode_application_send_queue_capacity-acquireCapacity-pendingCapacityInBytes--guided.md) | guided | positive | [Confirmed](../stage4-runtime-verification/results/internode_application_send_queue_capacity-acquireCapacity-pendingCapacityInBytes--guided.md) |
| [`repair_session_space`](cases/repair_session_space-split-maxsize--guided.md) | guided | positive | [Confirmed](../stage4-runtime-verification/results/repair_session_space-split-maxsize--guided.md) |
| [`SAI_VECTOR_SEARCH_MAX_MATERIALIZE_KEYS`](cases/SAI_VECTOR_SEARCH_MAX_MATERIALIZE_KEYS-materializeKeysAndCloseSource-MAX_MATERIALIZED_KEYS--guided.md) | guided | positive | [Confirmed](../stage4-runtime-verification/results/SAI_VECTOR_SEARCH_MAX_MATERIALIZE_KEYS-materializeKeysAndCloseSource-MAX_MATERIALIZED_KEYS--guided.md) |
| [`Integer_MAX_VALUE`](cases/Integer_MAX_VALUE-maybeAddEntry-Integer_MAX_VALUE--guided.md) | guided | positive | [Confirmed](../stage4-runtime-verification/results/Integer_MAX_VALUE-maybeAddEntry-Integer_MAX_VALUE--guided.md) |
| [`networking_cache_size`](cases/networking_cache_size-allocateMoreChunks-memoryUsageThreshold--guided.md) | guided | positive | [Confirmed](../stage4-runtime-verification/results/networking_cache_size-allocateMoreChunks-memoryUsageThreshold--guided.md) |
| [`coordinator_read_size_fail_threshold`](cases/coordinator_read_size_fail_threshold-shouldReject-thresholdBytes--guided.md) | guided | positive | [Confirmed](../stage4-runtime-verification/results/coordinator_read_size_fail_threshold-shouldReject-thresholdBytes--guided.md) |
| [`repair_disk_headroom_reject_ratio`](cases/repair_disk_headroom_reject_ratio-verifyDiskHeadroomThreshold-rejectRatio--guided.md) | guided | positive | [Confirmed](../stage4-runtime-verification/results/repair_disk_headroom_reject_ratio-verifyDiskHeadroomThreshold-rejectRatio--guided.md) |
| [`DOB_MAX_RECYCLE_BYTES`](cases/DOB_MAX_RECYCLE_BYTES-close-MAX_RECYCLE_BUFFER_SIZE--guided.md) | guided | positive | [Confirmed](../stage4-runtime-verification/results/DOB_MAX_RECYCLE_BYTES-close-MAX_RECYCLE_BUFFER_SIZE--guided.md) |
| [`memtable_heap_space`](cases/memtable_heap_space-tryAllocate-limit--autonomous.md) | autonomous | positive | [Confirmed](../stage4-runtime-verification/results/memtable_heap_space-tryAllocate-limit--autonomous.md) |
| [`max_space_usable_for_compactions_in_percentage`](cases/max_space_usable_for_compactions_in_percentage-hasDiskSpaceForCompactionsAndStreams-availableForCompaction--autonomous.md) | autonomous | positive | [Confirmed](../stage4-runtime-verification/results/max_space_usable_for_compactions_in_percentage-hasDiskSpaceForCompactionsAndStreams-availableForCompaction--autonomous.md) |
| [`concurrent_compactors`](cases/concurrent_compactors-submitBackground-getMaximumPoolSize--guided.md) | guided | negative | [**Refuted**](../stage4-runtime-verification/results/concurrent_compactors-submitBackground-getMaximumPoolSize--guided.md) |
| [`batch_size_fail_threshold`](cases/batch_size_fail_threshold-verifyBatchSize-failThreshold--guided.md) | guided | negative | [audited, not run](../stage4-runtime-verification/results/batch_size_fail_threshold-verifyBatchSize-failThreshold--guided.md) |
| [`native_transport_max_message_size`](cases/native_transport_max_message_size-processFirstFrameOfLargeMessage-maxMessageSize--guided.md) | guided | negative | [audited, not run](../stage4-runtime-verification/results/native_transport_max_message_size-processFirstFrameOfLargeMessage-maxMessageSize--guided.md) |
| [`native_transport_max_concurrent_connections`](cases/native_transport_max_concurrent_connections-channelActive-limit--guided.md) | guided | negative | [audited, not run](../stage4-runtime-verification/results/native_transport_max_concurrent_connections-channelActive-limit--guided.md) |
| [`native_transport_queue_max_item_age_threshold`](cases/native_transport_queue_max_item_age_threshold-hasQueueCapacity-oldestTaskQueueTime--guided.md) | guided | negative | [audited, not run](../stage4-runtime-verification/results/native_transport_queue_max_item_age_threshold-hasQueueCapacity-oldestTaskQueueTime--guided.md) |
| [`prepared_statements_cache_size`](cases/prepared_statements_cache_size-storePreparedStatement-capacityToBytes--autonomous.md) | autonomous | positive | [Confirmed](../stage4-runtime-verification/results/prepared_statements_cache_size-storePreparedStatement-capacityToBytes--autonomous.md) |
| [`internode_max_message_size` · `inferMessageSize`](cases/internode_max_message_size-inferMessageSize-size--autonomous.md) | autonomous | positive | [audited, not run](../stage4-runtime-verification/results/internode_max_message_size-inferMessageSize-size--autonomous.md) |
| [`internode_max_message_size` · `enqueue`](cases/internode_max_message_size-enqueue-getInternodeMaxMessageSizeInBytes--autonomous.md) | autonomous | positive | [audited, not run](../stage4-runtime-verification/results/internode_max_message_size-enqueue-getInternodeMaxMessageSizeInBytes--autonomous.md) |
| [`max_mutation_size`](cases/max_mutation_size-allocateBytes-slabCapacity--autonomous.md) | autonomous | positive | [audited, not run](../stage4-runtime-verification/results/max_mutation_size-allocateBytes-slabCapacity--autonomous.md) |
| [`WRITE_BUFFER_SIZE`](cases/WRITE_BUFFER_SIZE-append-remaining--autonomous.md) | autonomous | negative | [audited, not run](../stage4-runtime-verification/results/WRITE_BUFFER_SIZE-append-remaining--autonomous.md) |
| [`internode_application_receive_queue_capacity`](cases/internode_application_receive_queue_capacity-releaseCapacity-queueCapacity--autonomous.md) | autonomous | positive | [audited, not run](../stage4-runtime-verification/results/internode_application_receive_queue_capacity-releaseCapacity-queueCapacity--autonomous.md) |

<!-- Add one row per case. -->

## 2. Coverage summary

| Metric | Count |
|--------|-------|
| Modules covered | 12 (guided files) |
| Total case files | 37 (29 guided, 8 autonomous) |
| of which negative estimates | 6 (5 guided, written up 2026-10-19 as the pilot of the `predicted-negative.md` write-up, and 1 autonomous) |
| Found via feed 3b (raw source) | 13 |
| Found via feed 3a (stage 1/2) | **11** |
| Stage 4 closed (all tiers Confirmed; see `../stage4-runtime-verification/results/`) | **27** (24 guided positive, 3 autonomous), as of 2026-10-19 |
| Stage 4 closed, estimate refuted | **1** — `concurrent_compactors` (negative estimate, **Refuted** 2026-10-20), results `../stage4-runtime-verification/results/concurrent_compactors-submitBackground-getMaximumPoolSize--guided.md`: peak extra disk follows `min(n, 8)` × one compaction's output; the estimate stays as filed |
| Stage 4 not yet run | **9** (4 guided `rejected`, 5 autonomous: 4 positive, 1 negative); all 9 audited 2026-10-20 |

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
- **`native_transport_receive_queue_capacity-acquireCapacity-queueCapacity`:** the same `AbstractMessageHandler.acquireCapacity()` if-check as its internode sibling, reached via `CQLMessageHandler` for CQL client connections (default 1MiB vs. 4MiB). **Its disallow branch is config-dependent, and under the default it withholds nothing** — flagged as Target-3-relevant; the mechanism and both config paths are in [the case file](cases/native_transport_receive_queue_capacity-acquireCapacity-queueCapacity--guided.md) §5–§6b, which is authoritative. Established by deep-reading the source (feed 3b); stage 2's `transport` batch had also ranked this line. Written up 2026-09-18.
- **`internode_application_send_queue_capacity-acquireCapacity-pendingCapacityInBytes`:** the **send-side mirror** of the internode receive case: a per-connection byte allowance in `OutboundConnection.acquireCapacity()`, with the excess borrowed from a per-peer and a node-wide reserve (`ResourceLimits`), read by `enqueue()`. **Its disallow drops the message** and does not wait: the sender is not slowed, the request's callback is failed at once with `TIMEOUT`, and an ordinary write is **hinted** on the coordinator (a counter write is not). **Three findings that make the limit weaker than its name:** (1) the **per-peer reserve is read from the receive-side key** (`OutboundConnectionSettings:395`, with `withDefaults()` running before `withDefaultReserveLimits()`), so `internode_application_send_queue_reserve_endpoint_capacity` reaches no limit on the production path (derived from reading; unit step U10 and scenario C test it); (2) the ceiling is **per link** (`3·P·C` plus `min(P·E, G)`), and **at the defaults the reserves, not the capacity, are the large term** (12 MiB per peer against up to 128 MiB per peer and 512 MiB per node); (3) **expiry is lazy on a connected link:** a full link whose delivery is stalled refuses offers before `queue.add()`, where pruning otherwise runs, so its bytes stay pinned past the messages' deadlines. A peer that cannot be reached is the strictest case: no reserve is tried and the capacity is a hard cap. **Rule 3 holds in a weaker form than for the inbound twin:** the message exists before the check, so the branches diverge on its retention and serialization buffers, not its creation (§7 of the case). `ResourceLimits.Concurrent.tryAllocate():138` is cited as the mechanism, not filed (`undetermined.md` §5 item 3 stays open); the delivery's frame buffers come from the networking pool (`predicted-positive.md` item 10). Found via stage-3 feed **3a** (band A1, rows `OutboundConnection.java:398` and `:416`; `:416` turned out not to be a check); written up 2026-10-07.

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
On-disk index entries for wide partitions, the index summary and the key cache that holds them
(`io/sstable/format/big`, `io/sstable/indexsummary`, `cache`, `service/CacheService`). Three cases so far:
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

- **`Integer_MAX_VALUE-maybeAddEntry-Integer_MAX_VALUE`:** the folder's first **type-bound** case. One BIG SSTable's off-heap index summary
  cannot hold more than 2^31−1 bytes of sampled entries (key + 8 B each), because entry offsets are 32-bit `int`s.
  `IndexSummaryBuilder.maybeAddEntry():204` refuses the first entry that would cross the bound, with one `ERROR` line, and **no later key is
  sampled** (the next sample position is not advanced); reads of uncovered keys still find them by scanning `Index.db` linearly from the last
  sample, so memory is traded for index reads and no data is lost. A second site, the constructor's `:108`, clamps the up-front reservation and
  raises the sampling interval when the *expected* summary (expected keys × the `cassandra.index_summary_expected_key_size` estimate, default
  64 B) would pass 2 GiB; that raised interval is persisted, so every restart rebuilds the summary (derived). No knob moves the limit, and it can
  only be lowered: the test design moves it with a Byteman offset on `getEntrySize()` and reaches the real 2 GiB unpatched with 60,000-byte keys
  at `min_index_interval` 1. Per SSTable; the node total belongs to `index_summary_capacity` (`undetermined.md` §5). BIG only. Found via stage-3
  feed **3b** (capacity-word pass), with the second site from band A2 (`IndexSummaryBuilder.java:108`); written up 2026-10-15.

### 3.6 buffer_pool
Off-heap buffer pooling for file reads and networking (`utils/memory/BufferPool`,
`utils/memory/BufferPools`). Two cases so far:
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
  one check — the `networking_cache_size` sibling is a separate case (filed
  2026-10-15, below). Source bug noted: `MACRO_CHUNK_SIZE`'s comment says
  1 MiB, the arithmetic gives 8 MiB.
- **`networking_cache_size-allocateMoreChunks-memoryUsageThreshold`:** the same check on the
  `networking` pool (internode framing, streaming, native-protocol-v5 frames; v4 and older use
  Netty's own allocator), default `min(128MiB, heap/16)`, restart-only. Same escape as the sibling:
  a refusal becomes an unbounded `allocateDirect` overflow (no production code calls `tryGet` in
  either pool). **It differs in recycling:** `recyclePartially = false`, so a chunk returns only
  when fully free and the pool should grow to its peak demand, not fill to its limit as the
  sibling's did at stage 4 (derived, tested by U3 and scenario M). The knob therefore bounds the
  memory retained after a burst, not the burst itself. Its cluster tier drives the pool with a
  native-v5 client that stops reading: nothing in `transport` caps the response backlog. Derived and
  not observed: large (≥ 128 KiB) native-v5 requests never release their frame buffers
  (`CQLMessageHandler.onComplete()`), which arm L tests. Found via stage-3 feed **3b** (the
  capacity-word pass's second `BufferPool` instance); written up 2026-10-15.

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
Replica- and coordinator-side read and the guardrails wrapped around it (`db/ReadCommand`, `db/transform`, `service/reads/thresholds`, `cql3/statements/SelectStatement`, `cql3/selection/ResultSetBuilder`). Two cases so far:
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
- **`coordinator_read_size_fail_threshold-shouldReject-thresholdBytes`:** running total of the **value bytes placed in one request's CQL
  `ResultSet`** on the coordinator, compared in `ResultSetBuilder.shouldReject()` (`size > thresholdBytes`) and read by
  `SelectStatement.maybeFail()`, which throws `ReadSizeAbortException` (pattern (b)). **Inside the result loop, after the replicas have
  answered:** the throw stops further rows being deserialized and added, the response frame (pooled direct) and, on a scan, later range
  requests, but every replica response of a single-partition read is already in memory, so that half is post hoc and recorded as not gated.
  **Permissive by one row:** it checks after the previous row is added and never checks the last, so a read of *n* rows of *s* bytes completes
  iff (*n*−1)·*s* ≤ limit. **Per request, so per page**, reset every page; aggregates count only output rows. **No exemptions:** system
  keyspaces, internal queries, superusers and driver metadata reads are refused like any client read, and the request fails outright (failure
  code 4 from protocol 5), with no replica to spare. **Off by default** (limit `null`, master switch false, shared with the replica guards) and
  **live-settable** (JMX `CoordinatorLargeReadAbortThreshold`, captured per request). Found via stage-3 feed **3b** (while writing up
  `local_read_size_fail_threshold`; stage 2 had banded the helper `shouldReject()` D); written up 2026-10-15.

### 3.10 repair
Anti-entropy repair: validation builds a Merkle tree per range and the coordinator compares the replicas' trees (`repair/`, `utils/MerkleTree`); admission of a repair (`service/ActiveRepairService`). Two cases so far:
- **`repair_session_space-split-maxsize`:** a ceiling on the **leaves of each validation's Merkle tree**, `maxsize` = 2^`min(ceil(log2 n), depth(space / RF × share), repair_session_max_tree_depth)`, compared in `MerkleTree.split()` (pattern (a)): at `size >= maxsize` no node is created and the sampling loop stops, so the cost moves to over-streaming. **The comparison runs only on the order-preserving partitioners** (with BIG SSTables); on the default Murmur3 the same `maxsize` is built in one step by `init()`, with no check. Named after `repair_session_space` (default heap / 16, live over JMX), not the queue's deprecated `repair_session_max_tree_depth`, which only caps the depth at 20; the budget binds below heaps of about 6 to 12 GiB at RF 3, the partition count on small tables. **The MiB-to-bytes conversion is 32-bit**, so from 2048 MiB (the default at a 32 GiB heap) every tree has two leaves. Per validation, not node-wide: sessions, tables and vnode ranges multiply it, and the coordinator holds trees sized by the replicas' settings. Found via stage-3 feed **3a** (band A1, row `MerkleTree.java:409`); written up 2026-10-13.
- **`repair_disk_headroom_reject_ratio-verifyDiskHeadroomThreshold-rejectRatio`:** an **admission check on data-disk usage**, `diskUsage + rejectRatio > 1` (pattern (b)). The coordinator reads it in `prepareForRepair()`, failing the repair before anything is registered; each participant reads it on `PREPARE_MSG`, answering `FAILURE_RSP` before registering; either way nothing is validated, snapshotted, streamed or anticompacted. `diskUsage` is recomputed at every call: the apparent bytes of the data directories (snapshots, backups and each hard link included) plus all memtables, over `min(used + usable, data_disk_usage_max_disk_size)`, rounded up to 5 decimals. It can exceed 1, so **the "disabled" default 0.0 still refuses above 100 %**. **Admission only:** an admitted repair's writes are neither counted nor checked again, so usage can pass `1 − ratio` by what it streams. **Every repair kind is checked**, preview and paxos-only included, despite the JMX name `IncrementalRepairDiskHeadroomRejectRatio`. The ratio is live over JMX, has no `nodetool` command, and a yaml value is not range-checked. Found via stage-3 feed **3a** (band B, row `ActiveRepairService.java:655` and its helper); written up 2026-10-15.

### 3.11 io_buffers
Reusable serialization buffers (`io/util/DataOutputBuffer` and its per-thread scratch instance), used by the commit log, mutation serialization, SSTable row writing and hints. One case so far:
- **`DOB_MAX_RECYCLE_BYTES-close-MAX_RECYCLE_BUFFER_SIZE`:** per-thread cap on the **idle** capacity of the scratch buffer. When the buffer is handed back (`DataOutputBuffer$1$1.close()`, a nested anonymous class), it is kept if it is at most the limit, otherwise it is freed at once and replaced by 128 bytes (pattern (a)). **Rule 3 is passed on retention, not withheld creation**: the buffer grows to fit the item whatever the limit, and the over-limit branch is the one that allocates (the refusal text is ready in the case's §11 if the rule is read strictly). A JVM property, restart-only (`cassandra.dob_max_recycle_bytes`, default 1 MiB, no range check), with buffers direct by default. Node-wide retention is threads × limit, and most of those threads are shared-pool workers that never time out. In-use size is up to 2(S − 1) at the commit log and unbounded at SSTable row writing. The cluster tier uses a Byteman ledger of every scratch buffer against the direct buffer-pool bean. Found via stage-3 feed **3a** (band C, row `DataOutputBuffer.java:73`); written up 2026-10-15.

### 3.12 sai
Storage-attached secondary indexes, including vector (ANN) search and its query planning (`index/sai/`). One case so far:
- **`SAI_VECTOR_SEARCH_MAX_MATERIALIZE_KEYS-materializeKeysAndCloseSource-MAX_MATERIALIZED_KEYS`:** a **count** cap on the primary keys one **hybrid vector query** (`ORDER BY … ANN OF` plus another indexed restriction) materializes into a list on each replica, compared in `QueryController.materializeKeysAndCloseSource()` (pattern (a)); JVM property `cassandra.sai.vector_search.max_materialized_keys`, default 16,000, restart-only. **Its disallow re-plans rather than refuses:** at the (*L* + 1)-th key the list is dropped and the query switches to an ANN search of the whole index with the filter applied to each row read. The folder's first case whose disallow branch **has an unbounded cost of its own**: that plan keeps every rejected key in `processedKeys`, up to every non-matching row on the replica when the matches are far from the query vector, so lowering the limit can *raise* a query's heap; the knob caps one plan's memory, not the query's. Also: the allow plan sizes an `int` array by the whole list in every SSTable segment (about *S* × *M*, derived); memtable matches are collected before the check (references only); 0 and `Integer.MAX_VALUE` switch always and never. Per command per replica, multiplied by the hybrid queries in flight. Found via stage-3 feed **3b** (the 2026-09-22 capacity-word pass; also band-A row `QueryController.java:449`); queued as `MAX_MATERIALIZED_KEYS` and named after the `CassandraRelevantProperties` constant; written up 2026-10-14.

## 4. Autonomous files — sha256 at filing

The hash of each autonomous file as filed (before any stage-4 amendment). A later
dated amendment adds a line here with its date and the new hash.

| File | sha256 | Filed |
|---|---|---|
| `memtable_heap_space-tryAllocate-limit--autonomous.md` | `31f017feea820dd6d9df3db04ef0d5aa50a81c1733819850d1fd027795e46126` | 2026-10-05 (claude-sonnet-5) |
| `max_space_usable_for_compactions_in_percentage-hasDiskSpaceForCompactionsAndStreams-availableForCompaction--autonomous.md` | `e8b505e1802722d76642c664e71a55ee2cbb23536bb88e1852edecce143ae7b1` | 2026-10-08 (claude-sonnet-5) |
| `prepared_statements_cache_size-storePreparedStatement-capacityToBytes--autonomous.md` | `f086b0d230352fd2aa54016d6403a7d5d9e7a578ead3b5a32981059f36c59c3f` | 2026-10-19 (autonomous agent, rejected-entry write-up) | (hash after the 2026-10-19 Judgment → Estimate label rename) |
| `prepared_statements_cache_size-storePreparedStatement-capacityToBytes--autonomous.md` | `b055bdde92e1f4861f05424defc1d19a994dd39ac4893fcceb7abe9232aba812` | 2026-10-19 stage-4 step-0 audit amendments (one cache entry per statement, test-yaml knob, live-heap instrument, two over-count rows); the frozen version | (hash above after the amendments; section D feedback added after the freeze, 2026-10-19) |
| `internode_max_message_size-inferMessageSize-size--autonomous.md` | `b204d619b862d6f9a78a9e9860ca7ebb41aabe94fe9dea083dce8c8ffe0777fb` | 2026-10-19 (autonomous agent, rejected-entry write-up) | (hash after the 2026-10-19 Judgment → Estimate label rename) |
| `internode_max_message_size-enqueue-getInternodeMaxMessageSizeInBytes--autonomous.md` | `b8f001f77ddaae019ccb673e3a269edb3094e3c2de93734a1f85b5409b0e5b3f` | 2026-10-19 (autonomous agent, rejected-entry write-up) | (hash after the 2026-10-19 Judgment → Estimate label rename) |
| `max_mutation_size-allocateBytes-slabCapacity--autonomous.md` | `47acc75811952dcd70e6b2ad0fd038833c1f0a2afe4da8e9fcde9a23c4cbf66f` | 2026-10-19 (autonomous agent, rejected-entry write-up) | (hash after the 2026-10-19 Judgment → Estimate label rename) |
| `WRITE_BUFFER_SIZE-append-remaining--autonomous.md` | `2ba8c54eb9f494ef6d6d74848ad558b2681634852e4693dcab51f2c489760e38` | 2026-10-19 (autonomous agent, rejected-entry write-up) | (hash after the 2026-10-19 Judgment → Estimate label rename) |
| `internode_application_receive_queue_capacity-releaseCapacity-queueCapacity--autonomous.md` | `239cf86ea5e682b82b6b8f0de86edeafada6a7bb03dae85c5f929c3a43a336a0` | 2026-10-19 (autonomous agent, rejected-entry write-up) | (hash after the 2026-10-19 Judgment → Estimate label rename) |
| `internode_max_message_size-enqueue-getInternodeMaxMessageSizeInBytes--autonomous.md` | `9edf2196d46995984e00dd37d7497dc48fafc363bfc545e17196520f555154f0` | 2026-10-20 stage-4 step-0 audit amendments (R1–R5: default-value run, networking-pool gauges, wire/disk arithmetic, metric path, hints off); the frozen version | (hash above after the amendments; section D feedback added after the freeze, if any) |
| `internode_max_message_size-inferMessageSize-size--autonomous.md` | `46d2788e90644e4835d69e728ec6cac99769453d7dbf0f6f30ccfaca2e5eb437` | 2026-10-20 stage-4 step-0 audit amendments (R1–R4: default run R0, networking-pool gauges, hints off, keep derived client frame size); the frozen version | (hash above after the amendments; section D feedback added after the freeze, if any) |
| `max_mutation_size-allocateBytes-slabCapacity--autonomous.md` | `8ecb18b22d2fe470942b0dbbb77bfb1636fddd9cda4c3f5b0058d467dfe352ca` | 2026-10-20 stage-4 step-0 audit amendments (R1–R3: `MAX_HINT_BUFFERS` and 17 MiB rows, 17 MiB bullet corrected, exact flush period); the frozen version | (hash above after the amendments; section D feedback added after the freeze, if any) |
| `WRITE_BUFFER_SIZE-append-remaining--autonomous.md` | `55bf043e43ebcbb70b926e214b47356edd69ce76a20a9d4aee7d832563bc5ab6` | 2026-10-20 stage-4 step-0 audit amendments (R1–R3: memory-control row, truncate table between runs, citation); the frozen version | (hash above after the amendments; section D feedback added after the freeze, if any) |
| `internode_application_receive_queue_capacity-releaseCapacity-queueCapacity--autonomous.md` | `b63484779685490d51411d3ac753f84f9cd78c29e146076c69d43940b7ddb631` | 2026-10-20 stage-4 step-0 audit amendments (R1–R5: mutation that must fail, ceilings Q + reserve, write timeout, backlog and disk plan); the frozen version | (hash above after the amendments; section D feedback added after the freeze, if any) |
