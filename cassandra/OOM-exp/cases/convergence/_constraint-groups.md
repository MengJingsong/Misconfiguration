# Convergence candidate groups — surveyed from if-check-exp

Reference list, not a case file. Surveys every row in
[`../../../if-check-exp/stage3-ai-deep-read/_INDEX.md`](../../../if-check-exp/stage3-ai-deep-read/_INDEX.md)
whose outcome class means **the constraint actually caps usage, per stage 4**
— **true positive**, **weak true positive**, and **false negative** (a false
negative is a case where the stage-3 estimate guessed `negative` but stage 4
measured `caps` anyway; the estimate was wrong, the real effect is a cap, so
it counts the same as a true positive here — see
[`../../../if-check-exp/stage4-runtime-verification/README.md#outcome-class`](../../../if-check-exp/stage4-runtime-verification/README.md)).
**True negative and false positive are excluded** — those are confirmed
*not* to cap, so there's no load to converge. 73 rows, ~50 distinct
constraints (several rows are the same constraint checked at a different
decision point), grouped by the shared budget they draw on, per
`convergence-playbook.md`'s "Picking combinations" step 1.

**How to use this:** before picking a combination, check
[`_batch-log.md`](_batch-log.md)'s "Shared-budget group status" table for
which group is open/exhausted/parked/skipped, then pick 2–3 **standing-pool**
constraints (see note below) from an open group here, preferring config-type.

**Standing pool vs. per-request guardrail.** Within each budget, a
constraint is only a good convergence candidate if it's a **standing
pool** — usage that accumulates and can sit *at* capacity for a sustained
window (a cache, a queue, a memtable). A **per-request/per-item guardrail**
(a size check on one mutation, one query response, one message) rejects or
passes a single operation and releases immediately — there's no window
where it's "parked at capacity" for a second constraint to converge with.
Guardrails are listed under "Not a shared budget" even when they are,
technically, heap or off-heap bytes.

## On-heap (JVM `-Xmx`)

**Status:** exhausted for the 3 constraints already run (`memtable_heap_space`,
`counter_cache_size`, `key_cache_size`) — see `_batch-log.md`. The rest below
are unused candidates for a future on-heap case, if the group is reopened for
a different sizing question (e.g. the tighter-boundary follow-up).

| Constraint | Case file | What it caps | Scale | Config-type |
|---|---|---|---|---|
| `memtable_heap_space` *(used, exhausted)* | [case](../../../if-check-exp/stage3-ai-deep-read/cases/memtable_heap_space-tryAllocate-limit--guided.md) | Memtable pool on-heap bytes, self-reclaiming | default 1/4 heap | yaml |
| `counter_cache_size` *(used, exhausted)* | [case](../../../if-check-exp/stage3-ai-deep-read/cases/counter_cache_size-iscountercacheenabled-capacity--autonomous.md) | Counter cache (Caffeine-weighted), non-self-reclaiming | default ≈2.5% heap | yaml |
| `key_cache_size` *(used, exhausted)* | [case](../../../if-check-exp/stage3-ai-deep-read/cases/key_cache_size-create-size--autonomous.md) | Key cache (Caffeine-weighted) | config-set | yaml |
| `column_index_cache_size` | [case](../../../if-check-exp/stage3-ai-deep-read/cases/column_index_cache_size-indexSamples-cacheSizeThreshold--guided.md) | Retained `IndexInfo[]` per row-index entry (write+read path) | per-partition, config-set threshold | yaml |
| `prepared_statements_cache_size` | [case](../../../if-check-exp/stage3-ai-deep-read/cases/prepared_statements_cache_size-storePreparedStatement-capacityToBytes--autonomous.md) | `QueryProcessor.preparedStatements` (Caffeine, `measureDeep` weight) | config-set | yaml |
| `diagnostic_event_memory_store_max_size` | [case](../../../if-check-exp/stage3-ai-deep-read/cases/diagnostic_event_memory_store_max_size-store-keyhead--autonomous.md) | `ConcurrentSkipListMap` of diagnostic events, count-capped | count × event size | hard-coded constant (non-config) |
| `monitoring_max_operations` | [case](../../../if-check-exp/stage3-ai-deep-read/cases/monitoring_max_operations-operationsqueue_offer-maxoperations--autonomous.md) | `LinkedBlockingQueue<Operation>` (slow/failed query monitor), count-capped, each pins a `ReadCommand` | default 50 per queue ×2 queues | JVM property (`-Dcassandra.monitoring_max_operations`) |
| `virtual_logs_max_rows` | [case](../../../if-check-exp/stage3-ai-deep-read/cases/virtual_logs_max_rows-boundedlinkedlist_add-size--autonomous.md) | `BoundedLinkedList` backing `system_views.logs`, count-capped | rows × message size (small, ~30 MB at 100k×300B) | hard-coded constant, but typed "config" in index — verify before use |
| `max_compaction_flush_memory_in_mb` | [case](../../../if-check-exp/stage3-ai-deep-read/cases/max_compaction_flush_memory_in_mb-getmode-maxmembytes--autonomous.md) | Heap of the active SASI index builder during compaction flush | config-set MB, sustained only while a flush/compaction runs | per-table/per-index option (non-config) |
| `repair_session_space` *(mixed — see Disk too)* | [case](../../../if-check-exp/stage3-ai-deep-read/cases/repair_session_space-split-maxsize--guided.md) | Merkle-tree leaves: on-heap per leaf+inner-node, **and** an off-heap buffer per tree (`82L+32` bytes) — sustained only during an active repair session | config-set, RF/partitioner-dependent | yaml |
| `native_transport_max_concurrent_connections` *(false negative — see note)* | [case](../../../if-check-exp/stage3-ai-deep-read/cases/native_transport_max_concurrent_connections-channelActive-limit--guided.md) | Live heap of idle open connections — stage-3 estimated this wouldn't move memory; stage 4 confirmed it does: `min(4000, L)` connections × 1,329.6 B/idle connection | ~1.3 KB × connection limit, small at realistic limits | yaml |

## Off-heap / direct memory

**Status:** open for untried candidates only. The `row_cache_size` +
`index_summary_capacity` pair is closed as OOMed (run 6: row cache full,
then an index-summary burst, cgroup OOM-kill during flush/compaction; runs
4-5 did not reach it, see `_batch-log.md`).

**Important correction found while running run 4, worth checking before
picking any other candidate from this table:** `-XX:MaxDirectMemorySize`
does **not** actually bind `row_cache_size` or `index_summary_capacity`
(confirmed from source and from measurement). Both allocate through
`Memory.allocate → MemoryUtil.allocate → JNA Native.malloc` — plain libc
malloc — which never touches the JVM's `DirectByteBuffer`/`Bits.reserveMemory`
accounting that `-XX:MaxDirectMemorySize` polices. This is stated explicitly
in both constraints' own if-check-exp case files (their A2 sections), and is
why both stage-4 results measure `RssAnon` from `/proc/<pid>/status`, never
a JVM-reported "direct memory" figure. **Before assuming any other row in
this table is bounded by `-XX:MaxDirectMemorySize`, check whether its real
allocation path is JNA/malloc (not bound by the flag) or a genuine
`java.nio.DirectByteBuffer`/Netty pooled buffer (bound by the flag) — the
Netty/BufferPool-backed rows below (`internode_application_*`,
`native_transport_*`, `file_cache_size`, `networking_cache_size`) are more
likely to be the latter, but this has not been verified for this table; only
`row_cache_size` and `index_summary_capacity` have been checked.** The
working budget mechanism for this group, confirmed in run 4, is a cgroup v2
`memory.max` (via `systemd-run --user --scope -p MemoryMax=...`), which
bounds the whole process (heap + every off-heap/native allocation) regardless
of which JVM accounting path, if any, a given off-heap constraint uses.

| Constraint | Case file | What it caps | Scale | Config-type |
|---|---|---|---|---|
| `memtable_offheap_space` | [case](../../../if-check-exp/stage3-ai-deep-read/cases/memtable_offheap_space-tryAllocate-limit--guided.md) | Memtable pool off-heap bytes (direct buffers) | yaml-set | yaml |
| `row_cache_size` *(used, runs 4-6 — OOMed in run 6)* | [case](../../../if-check-exp/stage3-ai-deep-read/cases/row_cache_size-create-serialized_size--autonomous.md) | Row cache, serialized off-heap (JNA `Native.malloc`, **not** bound by `-XX:MaxDirectMemorySize`) | yaml-set | yaml |
| `nopcache_capacity` | [case](../../../if-check-exp/stage3-ai-deep-read/cases/nopcache_capacity-setcapacity-capacity--autonomous.md) | Same row-cache-memory family as `row_cache_size` (off-heap, read as `RssAnon`) | yaml-set | hard-coded constant |
| `index_summary_capacity` *(used, runs 4-6 — OOMed in run 6)* | [case](../../../if-check-exp/stage3-ai-deep-read/cases/index_summary_capacity-distributeRemainingSpace-extraSpaceRequired--autonomous.md) | Off-heap index-summary bytes (same JNA `Native.malloc` path, **not** bound by `-XX:MaxDirectMemorySize`; enforced only at periodic resize — see run 4's case file for the bypass window this creates) | yaml-set | yaml |
| `DOB_MAX_RECYCLE_BYTES` | [case](../../../if-check-exp/stage3-ai-deep-read/cases/DOB_MAX_RECYCLE_BYTES-close-MAX_RECYCLE_BUFFER_SIZE--guided.md) | Per-thread scratch-buffer recycle pool (direct bytes held between uses; heap in one control arm) | staircase from 2,048 B up to tens of MB per thread × held-thread count | JVM property |
| `MAX_HINT_BUFFERS` | [case](../../../if-check-exp/stage3-ai-deep-read/cases/MAX_HINT_BUFFERS-switchCurrentBuffer-MAX_ALLOCATED_BUFFERS--guided.md) | Off-heap direct `ByteBuffer`s for hints, `n × bufferSize` | config-set | JVM property |
| hints buffer slabs (indexed under `max_mutation_size` in the index — really a hints constraint) | [case](../../../if-check-exp/stage3-ai-deep-read/cases/hints-HintsBuffer-put-slabCapacity--autonomous.md) | Off-heap direct `ByteBuffer` slabs (`HintsBuffer.allocateDirect`) | slab-sized | yaml (same family as `hints_write_buffer_size`/`MAX_HINT_BUFFERS` — verify exact knob before use) |
| `internode_application_receive_queue_capacity` | [case](../../../if-check-exp/stage3-ai-deep-read/cases/internode_application_receive_queue_capacity-acquireCapacity-queueCapacity--guided.md) | Off-heap networking pool (large messages; small messages' heap holding was refuted at stage 4 — **off-heap is the confirmed path**) | yaml-set, per-connection | yaml ×2 |
| `internode_application_send_queue_capacity` | [case](../../../if-check-exp/stage3-ai-deep-read/cases/internode_application_send_queue_capacity-acquireCapacity-pendingCapacityInBytes--guided.md) | Same off-heap networking pool family, send side | yaml-set | yaml |
| `internode_application_receive_queue_reserve_global_capacity` | [case](../../../if-check-exp/stage3-ai-deep-read/cases/internode_application_receive_queue_reserve_global_capacity-acquireCapacity-actualExcess--autonomous.md) | Same family, global reserve across connections | yaml-set | yaml, typed "not-a-case" in index — verify |
| `native_transport_receive_queue_capacity` | [case](../../../if-check-exp/stage3-ai-deep-read/cases/native_transport_receive_queue_capacity-acquireCapacity-queueCapacity--guided.md) | Off-heap client-facing networking pool (same `BufferPoolAllocator` family as internode, client side) | yaml-set | yaml |
| `native_transport_max_request_data_in_flight` | [case](../../../if-check-exp/stage3-ai-deep-read/cases/native_transport_max_request_data_in_flight-releaseItem-globalInFlightBytesBelowLimit--autonomous.md) | Same client-facing off-heap pool family, global in-flight bytes | yaml-set | yaml ×2 |
| `file_cache_size` | [case](../../../if-check-exp/stage3-ai-deep-read/cases/file_cache_size-allocateMoreChunks-memoryUsageThreshold--guided.md) | Chunk-cache `BufferPool`, pooled direct bytes (`memoryAllocated`) | yaml-set | yaml ×2 |
| `networking_cache_size` | [case](../../../if-check-exp/stage3-ai-deep-read/cases/networking_cache_size-allocateMoreChunks-memoryUsageThreshold--guided.md) | Same `BufferPool` family, "networking" pool slabs | yaml-set | yaml |
| `trie_2gb_hard_limit` | [case](../../../if-check-exp/stage3-ai-deep-read/cases/trie_2gb_hard_limit-allocateblock-leadbit--autonomous.md) | One trie memtable's buffers — **off-heap or on-heap depending on `memtable_allocation_type`** (tested both `OFF_HEAP` and `ON_HEAP`); shares the same pool as `memtable_offheap_space`/`memtable_heap_space` when that allocation type is active | hard 2 GiB/trie ceiling | hard-coded constant |
| `row_overhead_size` | [case](../../../if-check-exp/stage3-ai-deep-read/cases/row_overhead_size-intrie_init-limitinmb--autonomous.md) | Same trie-memtable family as `trie_2gb_hard_limit` — one trie's buffer threshold | config-set MB | hard-coded constant, typed "not-a-case" — verify |
| `native_transport_queue_max_item_age_threshold` *(false negative — see note)* | [case](../../../if-check-exp/stage3-ai-deep-read/cases/native_transport_queue_max_item_age_threshold-hasQueueCapacity-oldestTaskQueueTime--guided.md) | Same off-heap client-facing networking pool family as `native_transport_receive_queue_capacity`/`native_transport_max_request_data_in_flight` (`RequestsSize`/global-reserve bytes) — stage-3 estimated negative, stage 4 confirmed it caps in throwing mode (only slows growth in default mode) | pool-dependent, same family scale | yaml |

## Disk

**Status:** skipped by request (2026-11-02) — do not pick from this group.
Listed here for completeness only.

| Constraint | Case file | What it caps | Scale | Config-type |
|---|---|---|---|---|
| `commitlog_total_space` *(skipped)* | [case](../../../if-check-exp/stage3-ai-deep-read/cases/commitlog_total_space-maybeFlushToReclaim-unused--autonomous.md) | Total commit-log disk bytes | yaml-set | yaml |
| `max_hints_size_per_host` *(skipped)* | [case](../../../if-check-exp/stage3-ai-deep-read/cases/max_hints_size_per_host-shouldHint-maxHintsSize--guided.md) | Hints-on-disk bytes per down replica | yaml-set | yaml |
| `cdc_total_space` | [case](../../../if-check-exp/stage3-ai-deep-read/cases/cdc_total_space-processNewSegment-allowance--guided.md) | Total CDC commit-log-segment disk bytes | yaml-set | yaml |
| `commitlog_segment_size` | [case](../../../if-check-exp/stage3-ai-deep-read/cases/commitlog_segment_size-allocate-endOfBuffer--autonomous.md) | One commit-log segment's disk bytes (not the directory total — a per-segment cap, pairs naturally with `commitlog_total_space`) | yaml-set | yaml |
| `DataDirectory_getAvailableSpace` | [case](../../../if-check-exp/stage3-ai-deep-read/cases/DataDirectory_getAvailableSpace-getWriteDirectory-availableSpace--guided.md) | Free bytes on the data-file filesystem, checked before compaction output | filesystem-dependent | runtime-queried (mixed) |
| `max_space_usable_for_compactions_in_percentage` | [case](../../../if-check-exp/stage3-ai-deep-read/cases/max_space_usable_for_compactions_in_percentage-hasDiskSpaceForCompactionsAndStreams-availableForCompaction--guided.md) | Disk-bytes headroom reserved against compaction/stream output | % of usable disk | yaml (mixed) |
| `repair_disk_headroom_reject_ratio` | [case](../../../if-check-exp/stage3-ai-deep-read/cases/repair_disk_headroom_reject_ratio-verifyDiskHeadroomThreshold-rejectRatio--guided.md) | Data-directory apparent bytes + memtables vs. `(1−r)×T` headroom | yaml-set ratio | yaml |
| `sstable_size_in_mb` | [case](../../../if-check-exp/stage3-ai-deep-read/cases/sstable_size_in_mb-shouldSwitchWriterInCurrentLocation-maxSSTableSize--autonomous.md) | One output sstable's disk bytes (per-table option) | yaml-set MB | per-table option (non-config) |
| `cache_keys_to_save` | [case](../../../if-check-exp/stage3-ai-deep-read/cases/cache_keys_to_save-saveCache-keysEstimate--autonomous.md) | Saved-cache file bytes on disk (entry count × entry size) | config-set key count | yaml ×3 |
| `repair_session_space` *(see On-heap too)* | [case](../../../if-check-exp/stage3-ai-deep-read/cases/repair_session_space-split-maxsize--guided.md) | Off-heap buffer per merkle tree (`82L+32` bytes) is memory, not disk — listed here only because its on-heap counterpart is cross-referenced above | — | yaml |

## Not a shared budget (per-request/per-item guardrails — excluded from convergence picking)

These cap a single operation's size or count and release immediately after
that operation completes — there's no sustained "parked at capacity" window
for a second constraint to converge with, even where the underlying bytes
are heap or off-heap. Not candidates for this playbook's combinations.

| Constraint | Case file | Why excluded |
|---|---|---|
| `Integer_MAX_VALUE` | [case](../../../if-check-exp/stage3-ai-deep-read/cases/Integer_MAX_VALUE-maybeAddEntry-Integer_MAX_VALUE--guided.md) | Generic overflow guard, not a budget |
| `rows-per-partition` | [case](../../../if-check-exp/stage3-ai-deep-read/cases/rows-per-partition-hasEnoughLiveData-rowLimit--autonomous.md) | Per-query row-count paging limit |
| `group-by-row-limit` | [case](../../../if-check-exp/stage3-ai-deep-read/cases/group-by-row-limit-incrementRowCount-rowsCounted--autonomous.md) | Per-query group/row-count paging limit |
| `default_page_size` | [case](../../../if-check-exp/stage3-ai-deep-read/cases/default_page_size-cqlgroupbylimits_onclose-rowlimit--autonomous.md) | Hard-coded per-query page row count |
| `local_read_size_fail_threshold` | [case](../../../if-check-exp/stage3-ai-deep-read/cases/local_read_size_fail_threshold-addSize-failBytes--guided.md) | Per-command response-buffer byte threshold, releases after the read |
| `row_index_read_size_fail_threshold` | [case](../../../if-check-exp/stage3-ai-deep-read/cases/row_index_read_size_fail_threshold-checkSize-failThreshold--guided.md) | Same family, per-command |
| `coordinator_read_size_fail_threshold` | [case](../../../if-check-exp/stage3-ai-deep-read/cases/coordinator_read_size_fail_threshold-shouldReject-thresholdBytes--guided.md) | Same family, per-command |
| `tombstone_failure_threshold` | [case](../../../if-check-exp/stage3-ai-deep-read/cases/tombstone_failure_threshold-countTombstone-tombstones--autonomous.md) | Per-read response-buffer bound, count-based |
| `max_mutation_size` | [case](../../../if-check-exp/stage3-ai-deep-read/cases/max_mutation_size-validateSize-MAX_MUTATION_SIZE--guided.md) | Per-mutation byte limit (commit-log entry + off-heap serialization buffer), rejects a single oversized mutation |
| `max_value_size` | [case](../../../if-check-exp/stage3-ai-deep-read/cases/max_value_size-read-maxValueSize--guided.md) | Per-column-value byte limit |
| `internode_max_message_size` | [case](../../../if-check-exp/stage3-ai-deep-read/cases/internode_max_message_size-inferMessageSize-size--autonomous.md) | Per-message byte limit (direct+heap pinned by one message, not a standing pool) |
| `CACHEABLE_MUTATION_SIZE_LIMIT` | [case](../../../if-check-exp/stage3-ai-deep-read/cases/CACHEABLE_MUTATION_SIZE_LIMIT-serialization-CACHEABLE_MUTATION_SIZE_LIMIT--guided.md) | Per-mutation heap byte[] used only to decide cacheability, transient |
| `SAI_VECTOR_SEARCH_MAX_MATERIALIZE_KEYS` | [case](../../../if-check-exp/stage3-ai-deep-read/cases/SAI_VECTOR_SEARCH_MAX_MATERIALIZE_KEYS-materializeKeysAndCloseSource-MAX_MATERIALIZED_KEYS--guided.md) | Per-query key-list bound, released when the query ends |
| `mutation_repair_rows_per_batch` | [case](../../../if-check-exp/stage3-ai-deep-read/cases/mutation_repair_rows_per_batch-throttledunfilterediterator-maxbatchsize--autonomous.md) | Per-batch row-count throttle during repair streaming, not a standing pool |
| `native_transport_max_message_size` *(false negative)* | [case](../../../if-check-exp/stage3-ai-deep-read/cases/native_transport_max_message_size-processFirstFrameOfLargeMessage-maxMessageSize--guided.md) | Per-message byte limit — "caps it per request"; released once the message is handled, not a standing pool |

## Others (not memory/disk bytes at all — count- or time-based caps)

Caps a **count** or a **duration**, not bytes of a shared pool — out of
scope for this playbook's byte-budget convergence model even when the cap
is real and confirmed. Listed for completeness; not candidates.

| Constraint | Case file | What it actually caps | Why excluded |
|---|---|---|---|
| `concurrent_compactors` *(false negative)* | [case](../../../if-check-exp/stage3-ai-deep-read/cases/concurrent_compactors-submitBackground-getMaximumPoolSize--guided.md) | Max compaction thread-pool **size** (thread count) | Count, not bytes |
| `max-compaction-threshold` *(false negative, bypass)* | [case](../../../if-check-exp/stage3-ai-deep-read/cases/max-compaction-threshold-getCandidatesFor-candidatesSize--autonomous.md) | Candidate-sstable **count** grouped per compaction round, "caps only on some paths (bypass)" | Count, not bytes — but the confirmed bypass mechanism is a candidate for `bypass-playbook.md`, not here |

## Surprises / notes for whoever picks next

- **A sixth false negative,
  `prepared_statements_cache_size-loadPreparedStatements-preparedBytesLoaded`**
  ([case](../../../if-check-exp/stage3-ai-deep-read/cases/prepared_statements_cache_size-loadpreparedstatements-preparedbytesloaded--autonomous.md)),
  isn't listed above at all: stage 4 found the prepared-statement cache
  itself is **not** bounded by this specific check (the thing it actually
  caps is a *different* on-heap memtable — `system.prepared_statements` via
  eviction tombstones). It's the same constraint name already in the
  On-heap table above (`prepared_statements_cache_size`, true positive at
  `storePreparedStatement`) but a different decision point with the
  opposite real effect — a confirmed bypass, not a second standing-pool
  cap. Flagged for `bypass-playbook.md`'s candidate list, not duplicated
  into On-heap here.
- **Several off-heap networking constraints turned out to be the same
  underlying pool** (`internode_application_{receive,send}_queue_capacity`,
  `internode_application_receive_queue_reserve_global_capacity`,
  `native_transport_receive_queue_capacity`,
  `native_transport_max_request_data_in_flight`) — all draw on Netty's
  direct `BufferPoolAllocator`. A future off-heap case combining two of
  these would likely be combining the *same* pool twice, not two
  independent ones — check this before treating them as a genuine 2-way
  combination.
- **`trie_2gb_hard_limit` and `row_overhead_size`** aren't a fixed on-heap
  or off-heap constraint — they follow `memtable_allocation_type`, landing
  in whichever of `memtable_heap_space`/`memtable_offheap_space` is active.
  They're listed under off-heap here (the default/tested-off-heap case) but
  really belong to *both* groups depending on config.
- **`nopcache_capacity` reads as a near-duplicate of `row_cache_size`** —
  same off-heap row-cache-memory family, same measurement (`RssAnon`). Not
  an independent off-heap candidate on its own.
- A handful of index rows are typed `not-a-case` or `mixed` in
  `_INDEX.md`'s "Type (2026-10-29)" column despite reading as config
  true positives here (`virtual_logs_max_rows`, `row_overhead_size`,
  `internode_application_receive_queue_reserve_global_capacity`,
  `memtable_heap_space · adjustMemtableSize`) — re-check the case file's own
  type classification before building on one of these, the index's type
  column and the outcome-class column were updated on different dates.
