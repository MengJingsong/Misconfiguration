# Budget-domain ledger — Cassandra 5.0.9 memory constraints across cases

Written 2026-11-16, blind (phase-1 sources only)

Each phase-1 case file covers one constraint, and the E4 rows that some of them carry
([`playbook-guided.md` §3.2](../../stage3-ai-deep-read/playbook-guided.md)) compare that one
constraint with a few neighbours. No file adds up, per memory domain, everything the shipped
defaults allow. This ledger does that: for the JVM heap, JVM direct memory, other native memory and
the process as a whole, it lists the constraints that cap or reserve memory in the domain, resolves
their shipped defaults at four reference deployments, and says where the defaults together exceed the
domain's own default budget. Sources are the phase-1 case files under [`cases/`](cases/), the
stage-4 results under [`../stage4-runtime-verification/results/`](../stage4-runtime-verification/results/),
and the pinned tree `systems/cassandra/source/` (tag `cassandra-5.0.9`); every `path:line` below was
re-read in that tree on 2026-11-16. Paths without a prefix are under
`systems/cassandra/source/src/java/org/apache/cassandra/`; `conf/…` is `systems/cassandra/source/conf/…`.
Numbers marked *estimate* are arithmetic or JVM/OS behaviour not shown by the source or a stage-4 reading.

---

## 0. Conventions and reference deployments

- **H** = max heap in MiB. Heap-derived defaults use `Runtime.getRuntime().maxMemory()`
  (memtables, pools, in-flight, prepared statements, repair) or `totalMemory()` (key, counter and
  paxos caches, index summaries; `DatabaseDescriptor.java:816`, `:835`, `:851`, `:868`). With
  `-Xms` = `-Xmx` (`conf/cassandra-env.sh:149-151`) both are taken as H (*estimate*: the JVM may
  report slightly less).
- **Hard** = an allocation is refused, blocks or evicts at the limit. **Soft** = the limit only
  triggers a flush, a periodic shrink or a best-effort eviction, so usage can pass it.
  **Node-level** = one instance per process. **Per-owner** = one instance per peer, link,
  connection, thread, validation, request, SSTable …; the multiplier is given at defaults.
- **Direct-memory budget D.** `cassandra-env.sh` computes `CALCULATED_MAX_DIRECT_MEMORY_SIZE` from
  RAM, not from the heap: RAM/4 when RAM/2 ≤ `heap_limit`, else `heap_limit`/2
  (`conf/cassandra-env.sh:58-67`), with `heap_limit` = 31744 MiB under G1 (`:53-57`; G1 is the
  shipped collector, `conf/jvm17-server.options:33`, `conf/jvm11-server.options:63`). It is applied
  whenever `MAX_DIRECT_MEMORY_SIZE` is unset (`:139-141`, `:157-158`), **also when `MAX_HEAP_SIZE`
  was set by hand** (`:131-137` only chooses the heap). The comment in `conf/jvm-server.options:173`
  ("By default, this setting is half of max heap size") holds only at the automatic heap. **D_env**
  below is that formula; **D_jvm** = H is the plain-JVM default when the process is started without
  `cassandra-env.sh` (*estimate*: JVM behaviour, not in the tree).
- **Reference deployments** (MiB). For the hand-set heaps, RAM is taken as a host or container of
  2 × H as seen by `free -m` (`conf/cassandra-env.sh:21`); see §5 for a host that reports more.

| Id | Deployment | H | RAM / container | D_env | D_jvm |
|---|---|---|---|---|---|
| A | heap set to 2 GiB | 2048 | 4096 (2 × H) | 1024 (= RAM/4) | 2048 |
| B | heap set to 8 GiB | 8192 | 16384 (2 × H) | 4096 (= RAM/4) | 8192 |
| C | auto heap, 16 GiB RAM | 8192 (= RAM/2, `:65`) | 16384 | 4096 (`:66`) | 8192 |
| D | auto heap, 64 GiB RAM | 31744 (= `heap_limit`, `:61`) | 65536 | 15872 (`:62`) | 31744 |

B and C resolve to the same numbers; they are kept apart because B's D_env moves with the host, not
with H (§5). `free -m` reports a little less than nominal RAM, so C and D come out slightly lower in
practice (*estimate*).

- **Two shipped profiles.** `conf/cassandra.yaml` (the default): `memtable_allocation_type:
  heap_buffers` (`:825`, `Config.java:524`), SkipList memtable (`conf/cassandra.yaml:789-790`), BIG
  SSTables (`Config.java:373`). `conf/cassandra_latest.yaml`: `offheap_objects` (`:836`), Trie
  memtable (`:801`), BTI SSTables (`:1164-1165`). Unless named, figures are for `cassandra.yaml`.

---

## 1. Domain 1 — JVM heap (budget: H)

### 1.1 Constraints

| Constraint | Default: raw → resolved | Hard / soft | Owner, multiplier at defaults | Source | Phase-1 case(s) |
|---|---|---|---|---|---|
| `memtable_heap_space` | unset → H/4 | hard (writers block), flush from `memtable_cleanup_threshold` = 1/(1 + `memtable_flush_writers`) = 1/3 with one data dir; blocking-marked writes bypass the check | node (one `MEMORY_POOL` for all tables) | `DatabaseDescriptor.java:586-587`, `:753-763`; `conf/cassandra.yaml:797` | [`memtable_heap_space-tryAllocate-limit--guided`](cases/memtable_heap_space-tryAllocate-limit--guided.md), [`…-applySimpleConfig-…--autonomous`](cases/memtable_heap_space-applySimpleConfig-memtable_heap_space--autonomous.md), [`memtable_cleanup_threshold-…`](cases/memtable_cleanup_threshold-applySimpleConfig-memtable_cleanup_threshold--autonomous.md) |
| `key_cache_size` | empty → min(max(1, 5 % H), 100) MiB | hard on the weigher's count; real heap ≈ 2.17 × the weighted size (stage 4) | node | `DatabaseDescriptor.java:815-816`; `conf/cassandra.yaml:525` | [`key_cache_size-applySimpleConfig-…`](cases/key_cache_size-applySimpleConfig-keyCacheSizeInMiB--autonomous.md) ([results](../stage4-runtime-verification/results/key_cache_size-applySimpleConfig-keyCacheSizeInMiB--autonomous.md), status block) |
| `counter_cache_size` | empty → min(max(1, 2.5 % H), 50) MiB | hard on the count; real ≈ 1.77–1.81 × (stage 4) | node (used only with counter tables) | `DatabaseDescriptor.java:834-835`; `conf/cassandra.yaml:595` | [`counter_cache_size-applySimpleConfig-…`](cases/counter_cache_size-applySimpleConfig-counterCacheSizeInMiB--autonomous.md) ([results](../stage4-runtime-verification/results/counter_cache_size-applySimpleConfig-counterCacheSizeInMiB--autonomous.md)) |
| `paxos_cache_size` | null → min(max(1, 1 % H), 50) MiB | hard on the count; case E4 cites a worst factor ≈ 2.2 × | node | `DatabaseDescriptor.java:850-852` | [`paxos_cache_size-close-active`](cases/paxos_cache_size-close-active--autonomous.md), [`…-applySimpleConfig-…`](cases/paxos_cache_size-applySimpleConfig-paxosCacheSizeInMiB--autonomous.md) |
| `prepared_statements_cache_size` | empty → max(10, H/256) MiB | hard (evict) | node | `DatabaseDescriptor.java:796-797`; `conf/cassandra.yaml:508` | [`prepared_statements_cache_size-applySimpleConfig-…`](cases/prepared_statements_cache_size-applySimpleConfig-preparedStatementsCacheSizeInMiB--autonomous.md) |
| `streaming_state_size` | 40 MiB (fixed) | hard (evict); real ≈ 1.54 × the charge | node | `Config.java:949` | [`streaming_state_size-streammanager-states`](cases/streaming_state_size-streammanager-states--autonomous.md) |
| `native_transport_max_request_data_in_flight` | null → H/10 (wire bytes) | hard on admission; counts wire bytes, decoded objects are larger; **split heap/direct** (frames in direct, decoded requests on heap) | node | `DatabaseDescriptor.java:649-651` | [`native-transport-max-request-data-in-flight-set…`](cases/native-transport-max-request-data-in-flight-setNativeTransportConcurrentRequestDataInFlightInBytes-maxRequestDataInFlightInBytes--autonomous.md) |
| `native_transport_max_request_data_in_flight_per_ip` | null → H/40 | hard, inside the global H/10 | per client IP; no extra node term | `DatabaseDescriptor.java:654-656` | [`native_transport_max_request_data_in_flight_per_ip-set…`](cases/native_transport_max_request_data_in_flight_per_ip-setNativeTransportMaxRequestDataInFlightPerIpInBytes-maxRequestDataInFlightInBytes--autonomous.md) |
| `native_transport_receive_queue_capacity` | 1 MiB | not enforced under the default `throwOnOverload=false` (decode proceeds) | per CQL connection × connections (unbounded, below) | `Config.java:302` | [`native_transport_receive_queue_capacity-…--guided`](cases/native_transport_receive_queue_capacity-acquireCapacity-queueCapacity--guided.md) |
| `internode_application_send_queue_*` | 4 MiB per link; 128 MiB per peer; 512 MiB global | hard (accounted serialized bytes); heap held is the queued `Message`s | link: 3 per peer (urgent, small, large, `conf/cassandra.yaml:1375`) → 12P MiB; reserves: min(128P, 512) MiB | `Config.java:250-254`; `conf/cassandra.yaml:1386-1388` | [`internode_application_send_queue_capacity-…--guided`](cases/internode_application_send_queue_capacity-acquireCapacity-pendingCapacityInBytes--guided.md) |
| `internode_application_receive_queue_*` | 4 MiB per connection; 128 MiB per peer; 512 MiB global | hard (accounted); **split heap/direct**: stage 4 found heap flat at `concurrent_writes` × message size and the rest of the queue waiting in the networking pool (direct) | 3 links per peer (the guided case counts up to 4 handlers with legacy) → 12P (16P) MiB; reserves min(128P, 512) MiB | `Config.java:257-261`; `conf/cassandra.yaml:1389-1391` | [`…receive_queue_capacity-…--guided`](cases/internode_application_receive_queue_capacity-acquireCapacity-queueCapacity--guided.md), [`…reserve_global_capacity-…`](cases/internode_application_receive_queue_reserve_global_capacity-acquireCapacity-actualExcess--autonomous.md), [`…releaseCapacity-…`](cases/internode_application_receive_queue_capacity-releaseCapacity-queueCapacity--autonomous.md) ([results](../stage4-runtime-verification/results/internode_application_receive_queue_capacity-releaseCapacity-queueCapacity--autonomous.md), status) |
| SAI `segment_write_buffer_size` | 1024 MiB (fixed, not heap-derived) | soft: a segment flushes only when the global limit is passed and it reaches limit / #building indexes | node; only while SAI segments are built outside memtable flush (compaction, initial build) | `config/StorageAttachedIndexOptions.java:26`, `:35`; `index/sai/disk/v1/V1OnDiskFormat.java:115-128` ("Global limit on heap") | [`segment_write_buffer_size-validate-…`](cases/segment_write_buffer_size-validate-maximum_segment_buffer_mb--autonomous.md) |
| `repair_session_space` | empty → max(1, H/16) MiB | hard per validation (tree depth) | per validation; replica builds trees on heap for `space/RF`; validations at once ≤ `concurrent_validations` = `concurrent_compactors` = 2 with one data dir → 2 × H/(16·RF) | `DatabaseDescriptor.java:609-610`, `:777-778`, `:1071-1075` | [`repair_session_space-split-maxsize--guided`](cases/repair_session_space-split-maxsize--guided.md), [`repair_session_space-initHelper-max`](cases/repair_session_space-initHelper-max--autonomous.md) |
| `commitlog_max_outstanding_replay_bytes` | 64 MiB (JVM property) | hard; backlog heap ≈ 2 × L for large mutations (stage 4) | node, startup replay only | `config/CassandraRelevantProperties.java:114`; `db/commitlog/CommitLogReplayer.java:75` | [`commitlog_max_outstanding_replay_bytes-…`](cases/commitlog_max_outstanding_replay_bytes-handlemutation-pendingmutationbytes--autonomous.md) |
| FQL / audit `max_queue_weight` | 256 MiB each | hard (semaphore) | per BinLog, ≤ 2; both off by default | `utils/binlog/BinLogOptions.java:49` | [`max_queue_weight-acquireWeight-weight`](cases/max_queue_weight-acquireWeight-weight--autonomous.md) |
| Per-item caps | `max_mutation_size` = segment/2 = 16 MiB; `max_value_size` 256 MiB; `native_transport_max_frame_size` 16 MiB; `native_transport_max_message_size` → min(16 MiB, H/10, H/40); `CACHEABLE_MUTATION_SIZE_LIMIT` 1,000,000 B; `column_index_cache_size` 2 KiB; `batch_size_fail_threshold` 50 KiB | hard per item | per item × items in flight: e.g. `concurrent_writes` 32 × 16 MiB = 512 MiB transient mutation heap; not a node total | `DatabaseDescriptor.java:899`, `:3237-3245`; `Config.java:180`, `:285`, `:310`, `:328`; `conf/cassandra.yaml:1844` | [`max_mutation_size-validateSize-…--guided`](cases/max_mutation_size-validateSize-MAX_MUTATION_SIZE--guided.md), [`max_value_size-read-…--guided`](cases/max_value_size-read-maxValueSize--guided.md), [`native_transport_max_message_size-…--guided`](cases/native_transport_max_message_size-processFirstFrameOfLargeMessage-maxMessageSize--guided.md), [`CACHEABLE_MUTATION_SIZE_LIMIT-…--guided`](cases/CACHEABLE_MUTATION_SIZE_LIMIT-serialization-CACHEABLE_MUTATION_SIZE_LIMIT--guided.md), [`column_index_cache_size-…--guided`](cases/column_index_cache_size-indexSamples-cacheSizeThreshold--guided.md), [`batch_size_fail_threshold-…--guided`](cases/batch_size_fail_threshold-verifyBatchSize-failThreshold--guided.md) |
| Read size guardrails (`local_read_size_*`, `coordinator_read_size_*`, `row_index_read_size_*`) | null, master switch `read_thresholds_enabled: false` | **no cap** at defaults | per read command × `concurrent_reads` (32) | `Config.java:526-530`; `conf/cassandra.yaml:2015` | [`local_read_size_fail_threshold-…--guided`](cases/local_read_size_fail_threshold-addSize-failBytes--guided.md), [`coordinator_read_size_fail_threshold-…--guided`](cases/coordinator_read_size_fail_threshold-shouldReject-thresholdBytes--guided.md), [`row_index_read_size_fail_threshold-…--guided`](cases/row_index_read_size_fail_threshold-checkSize-failThreshold--guided.md) |
| Stage task queues (SEP) | `maxTasksQueued` = `Integer.MAX_VALUE`, unbounded `ConcurrentLinkedQueue` | **no cap** | per stage, unbounded | (case file A1) | [`maxTasksQueued-addTask-…`](cases/maxTasksQueued-addTask-taskPermits--autonomous.md), [`maxTasksQueued-takeTaskPermit-…`](cases/maxTasksQueued-takeTaskPermit-taskPermits--autonomous.md) |
| `native_transport_max_concurrent_connections(_per_ip)` | −1 = unlimited | **no cap** at defaults; stage 4: 1,329.6 B heap + 1 fd per idle connection | per connection, unbounded | `Config.java:289-290`; `conf/cassandra.yaml:1046-1052` | [`native_transport_max_concurrent_connections-channelActive-limit--guided`](cases/native_transport_max_concurrent_connections-channelActive-limit--guided.md) ([results](../stage4-runtime-verification/results/native_transport_max_concurrent_connections-channelActive-limit--guided.md)) |

Off at defaults and left out of the sums: row cache on heap (`SerializingCacheProvider` only),
partition denylist (`Config.java:759`), diagnostic events (`Config.java:708`), FQL/audit.

### 1.2 Sums

Node-level terms, resolved (MiB). "Exclusive" are the terms whose memory is on the heap only.
"Split" are the two request reserves whose counted bytes sit partly on the heap and partly in direct
memory; they are added in full here as the heap's worst case and again in §2 as direct's worst case.

| Term | A (H 2048) | B / C (H 8192) | D (H 31744) |
|---|---|---|---|
| memtable H/4 | 512 | 2048 | 7936 |
| key + counter + paxos + prepared | 100 + 50 + 20 + 10 = 180 | 100 + 50 + 50 + 32 = 232 | 100 + 50 + 50 + 124 = 324 |
| streaming state | 40 | 40 | 40 |
| **S_H exclusive** = H/4 + caches + 40 | **732 (35.7 %)** | **2320 (28.3 %)** | **8300 (26.1 %)** |
| native in-flight H/10 (split) | 204.8 | 819.2 | 3174.4 |
| internode send + receive global reserves (receive split) | 1024 | 1024 | 1024 |
| **S_H all hard** | **1960.8 (95.7 %)** | **4163.2 (50.8 %)** | **12498.4 (39.4 %)** |
| + SAI segment buffer 1024 (soft, with SAI) | 2984.8 (**145.7 %, +936.8 over H**) | 5187.2 (63.3 %) | 13522.4 (42.6 %) |
| + measured weigher under-count of key/counter/paxos (×2.17, ×1.8, ×2.2; *estimate*) | +181 → 2141.8 (**104.6 %, +93.8 over H**) | +217 → 4380.2 (53.5 %) | +217 → 12715.4 (40.1 %) |

Per-owner terms (formulas, MiB, P = peers, RF = replication factor):

- Internode links: send 3 × 4 × P = 12P, receive 12P (16P counting a legacy handler) → **24P–28P** on
  top of the global reserves (the reserves cap the per-peer 128 MiB borrowings at 512 in total).
  At A the room left after S_H all hard is 87.2 MiB, so **4 peers** (24P > 87.2) take the
  accounted ceiling past H; at B/C about 168 peers, at D about 800.
- Repair, replica side: 2 × H/(16·RF) → H/24 at RF 3 (85.3 / 341.3 / 1322.7 MiB).
- Transient per-item terms: `concurrent_writes` × `max_mutation_size` = 512 MiB (any H); reads
  `concurrent_reads` × (unbounded, read thresholds off).
- Unbounded at defaults: SEP stage queues, CQL connection count (1.33 KB heap each), per-read
  materialization.

**Budget the long-lived terms actually compete for (*estimate*).** `-XX:G1NewSizePercent=50`
(`conf/jvm17-server.options:40`, `conf/jvm11-server.options:70`, commented "Floor the young
generation size to 50% of the heap size") keeps half the heap young, so retained holders
(memtables, caches, queued messages) share roughly H/2. Against H/2, S_H all hard is 191 % at A,
102 % at B/C (+67 MiB) and 79 % at D; it fits H/2 only from H ≈ 8.6 GiB up (with the SAI buffer,
from H ≈ 15.3 GiB up). Whether G1 shrinks the young generation below the floor under pressure is
not settled here.

### 1.3 Verdict

The heap-only defaults use 26–36 % of H at every reference deployment. The two fixed 512 MiB
internode reserves and the H/10 request allowance are what close the gap at small heaps: at **A**
the hard defaults reach 95.7 % of H before any per-peer link, and the defaults exceed H with any
one of: ≥ 4 peers' link allowances, the SAI segment buffer (+936.8 MiB, for any H below ≈ 3.4 GiB),
or the measured cache weigher under-count (+93.8 MiB, *estimate*). At **B/C** and **D** the node-level
defaults stay at 51 % and 39 % of H (63 % / 43 % with SAI). Several heap holders have no cap at
defaults at any H (stage queues, connections, per-read materialization).

---

## 2. Domain 2 — JVM direct memory (budget: `MaxDirectMemorySize`)

### 2.1 Constraints

| Constraint | Default: raw → resolved | Hard / soft | Owner, multiplier at defaults | Source | Phase-1 case(s) |
|---|---|---|---|---|---|
| `file_cache_size` (chunk-cache `BufferPool`) | unset → min(512, H/4) MiB; chunk cache itself off (`file_cache_enabled` false), the pool still serves read buffers | hard on pooled slabs (8 MiB steps), **overflow no cap**: past the limit buffers are direct allocations counted as overflow | node | `DatabaseDescriptor.java:576-577`; `utils/memory/BufferPools.java:38-39`; `utils/memory/BufferPool.java:443`, `:460`, `:923`, `:233-238`; `cache/ChunkCache.java:53-54`; `io/util/BufferManagingRebufferer.java:45`; `Config.java:499` | [`file_cache_size-allocateMoreChunks-…--guided`](cases/file_cache_size-allocateMoreChunks-memoryUsageThreshold--guided.md) (stage 4: at the default the pool filled to 512 MiB for a 250 MiB demand under churn) and 5 autonomous siblings |
| `networking_cache_size` (networking `BufferPool`) | unset → min(128, H/16) MiB | hard on pooled slabs, **overflow no cap**; slabs never released | node | `DatabaseDescriptor.java:573-574`; `utils/memory/BufferPools.java:44-45` | [`networking_cache_size-allocateMoreChunks-…--guided`](cases/networking_cache_size-allocateMoreChunks-memoryUsageThreshold--guided.md) |
| Hint slabs (`MAX_HINT_BUFFERS` × slab) | 3 × max(2 × `max_mutation_size`, 32 MiB) = 3 × 32 = 96 MiB | hard (writers block on recycle) | node, allocated once hints are written, never shrunk | `config/CassandraRelevantProperties.java:351`; `hints/HintsBufferPool.java:41`; `hints/HintsService.java:79`, `:110` | [`MAX_HINT_BUFFERS-…--guided`](cases/MAX_HINT_BUFFERS-switchCurrentBuffer-MAX_ALLOCATED_BUFFERS--guided.md), [`max_mutation_size-allocateBytes-slabCapacity`](cases/max_mutation_size-allocateBytes-slabCapacity--autonomous.md) |
| Hint write buffer | 256 KiB | fixed | node | `hints/HintsWriteExecutor.java:50` | [`WRITE_BUFFER_SIZE-append-remaining`](cases/WRITE_BUFFER_SIZE-append-remaining--autonomous.md), [`hints_write_buffer_size-…`](cases/hints_write_buffer_size-append-hint_remaining--autonomous.md) |
| `DOB_MAX_RECYCLE_BYTES` (per-thread `DataOutputBuffer` scratch) | 1 MiB | hard on **idle** retention per thread; in use a buffer grows to 2(S − 1), transient 3(S − 1), ≤ 2(`max_mutation_size` − 13) ≈ 32 MiB at the commit-log site, unbounded at the SSTable writer | per thread: up to ≈ 260 + cores shared-pool workers at defaults (32 × 4 stage sizes + 128 + 4 + one per core) → 292 MiB idle on 32 cores, plus event-loop, flush, compaction, hint threads | `config/CassandraRelevantProperties.java:204`; `io/util/DataOutputBuffer.java:53`; `Config.java:179-182`, `:283`, `:287` | [`DOB_MAX_RECYCLE_BYTES-close-…--guided`](cases/DOB_MAX_RECYCLE_BYTES-close-MAX_RECYCLE_BUFFER_SIZE--guided.md) (stage 4 confirmed) |
| `memtable_offheap_space` under `offheap_buffers` | unset → H/4 | hard (like the heap pool) | node; **not used** at the default `heap_buffers` (`SlabPool(heapLimit, 0, …)`) | `DatabaseDescriptor.java:583-584`; `db/memtable/AbstractAllocatorMemtable.java:100-105`; `utils/memory/SlabAllocator.java:97`, `:139` | [`max-cloned-size-allocate-size`](cases/max-cloned-size-allocate-size--autonomous.md), [`slab-region-size-region-allocate-capacity`](cases/slab-region-size-region-allocate-capacity--autonomous.md) |
| Native-transport frames (split, §1) | H/10 global, H/40 per IP | hard on admission of request bytes | node | `DatabaseDescriptor.java:649-656` | as §1; stage 4 of the receive-queue case saw `BufferPool` `UsedSize`/`OverflowSize` reach ≈ 4.8 GB in large-request arms and not fall (case §8a E4, cause unknown) |
| Native-v5 responses | — | **no cap**: frames are written without reading channel writability and the in-flight permits return before the write | per slow-reading client | (case §8) | [`networking_cache_size-…--guided`](cases/networking_cache_size-allocateMoreChunks-memoryUsageThreshold--guided.md) |
| Internode receive frames (split, §1) | 512 MiB global + 128 MiB/peer + 12P | hard on accounted bytes | node + per peer | `Config.java:257-261` | as §1 (stage 4: the queue beyond the heap share waits in the networking pool) |
| Netty pooled allocator for CQL channels | `PooledByteBufAllocator(true)` | **no Cassandra cap** (outside `BufferPool` accounting) | per channel / arena | `transport/CBUtil.java:60`; `transport/PipelineConfigurator.java:138` | [`native_transport_max_frame_size-decode-bytesToDiscard`](cases/native_transport_max_frame_size-decode-bytesToDiscard--autonomous.md), [`max_queue_weight-…`](cases/max_queue_weight-acquireWeight-weight--autonomous.md) |
| Coordinator Merkle trees (off-heap) | `use_offheap_merkle_trees: true`; ≈ 82 B/leaf ≈ 0.32 × `repair_session_space` per (table, range) | per tree sized by the sender | per (table, range) compared; `concurrent_merkle_tree_requests` = 0 = **no limit** on jobs | `Config.java:210`, `:212`; `utils/MerkleTree.java:751`; `conf/cassandra.yaml:860-861` | [`repair_session_space-split-maxsize--guided`](cases/repair_session_space-split-maxsize--guided.md), [`repair_session_space-initHelper-max`](cases/repair_session_space-initHelper-max--autonomous.md) |
| `compressed_read_ahead_buffer_size` | 256 KiB | fixed per buffer | per scanner (thread × file) | `Config.java:341` | [`compressed_read_ahead_buffer_size-set…`](cases/compressed_read_ahead_buffer_size-setCompressedReadAheadBufferSizeInKb-sizeInKb--autonomous.md) |
| Inbound streaming chunk buffers (`chunk_length_in_kb`) | start at 16 KiB, regrow to the wire chunk length | **no cap** on the receiver (stage 4: only the JVM limit stops it) | per inbound compressed stream × streams | `Config.java:165` | [`chunk_length_in_kb-loadNextChunk-compressedChunk`](cases/chunk_length_in_kb-loadNextChunk-compressedChunk--autonomous.md) |
| `commitlog_max_compression_buffers_in_pool` | 3 × `commitlog_segment_size` (32 MiB) | hard | node; **not used** at the default `legacy` → mmap, uncompressed | `Config.java:397`, `:400-401` | [`commitlog_max_compression_buffers_in_pool-…-bufferpool`](cases/commitlog_max_compression_buffers_in_pool-simplecachedbufferpool-bufferpool--autonomous.md) |

`buffer_pool_use_heap_if_exhausted` defaults to false (`Config.java:514`), so pool overflow is
direct. When a slab allocation itself fails, the pool logs "Make sure direct memory size
(-XX:MaxDirectMemorySize) is large enough to accommodate off-heap memtables and caches" and the
caller falls back (`utils/memory/BufferPool.java:462-468`).

### 2.2 Sums

S_D core = chunk-cache pool + networking pool + hint slabs + hint write buffer
= min(512, H/4) + min(128, H/16) + 96 + 0.25 MiB. For every H ≥ 2048 this is **736.25 MiB**.

| | A (H 2048) | B / C (H 8192) | D (H 31744) |
|---|---|---|---|
| D_env / D_jvm | 1024 / 2048 | 4096 / 8192 | 15872 / 31744 |
| **S_D core** | 736.25 → **71.9 % / 35.9 %** | 736.25 → 18.0 % / 9.0 % | 736.25 → 4.6 % / 2.3 % |
| + `offheap_buffers` memtable H/4 (non-default) | 1248.25 → **121.9 % (+224.25 over D_env)** / 60.9 % | 2784.25 → 68.0 % / 34.0 % | 8672.25 → 54.6 % / 27.3 % |
| + split reserves (H/10 + 512) | 1453.05 → **141.9 % (+429 over D_env)** / 70.9 % | 2067.45 → 50.5 % / 25.2 % | 4422.65 → 27.9 % / 13.9 % |
| + DOB idle retention, 32 cores (292, *estimate* upper bound) | 1745.05 → **170.4 % (+721 over D_env)** / 85.2 % | 2359.45 → 57.6 % / 28.8 % | 4714.65 → 29.7 % / 14.9 % |

Per-owner terms (formulas): DOB idle 1 MiB × threads that ever wrote (≈ 260 + cores at
defaults), in use up to ≈ 32 MiB × concurrently writing threads (`concurrent_writes` 32 → ≈ 1 GiB
transient, *estimate* upper bound); 256 KiB × open compressed scanners; 2 buffers × inbound
compressed streams (each up to the wire chunk length); ≈ 0.32 × H/16 per (table, range) a repair
coordinator compares (H/50 ≈ 41 / 164 / 635 MiB per job at A / B·C / D), jobs unlimited; Netty
arenas, pool overflow and native-v5 responses unbounded.

### 2.3 Verdict

The pools and hint slabs whose defaults Cassandra sizes are fixed at 736 MiB from H = 2 GiB up, so
they fit D at every reference deployment, tightest at **A** (72 % of D_env). They stop fitting at
**A** once anything else in the domain is counted: the request and internode reserves' frames
(+429 MiB over D_env), the per-thread scratch buffers (+721 MiB with both), or an
`offheap_buffers` memtable (+224 MiB on the pools alone). Against D_jvm = H every sum stays below
the budget. The domain's real bound in all deployments is the JVM limit itself: both pools overflow
without a cap, and Netty arenas, slow-reader responses, inbound stream buffers and coordinator
Merkle trees have no Cassandra limit.

---

## 3. Domain 3 — other native memory (no JVM limit)

### 3.1 Constraints

| Constraint / holder | Default: raw → resolved | Hard / soft | Owner, multiplier at defaults | Source | Phase-1 case(s) |
|---|---|---|---|---|---|
| `memtable_offheap_space` under `offheap_objects` | unset → H/4; JNA `malloc` regions (`NativeAllocator` → `MemoryUtil.allocate` → `Native.malloc`) | hard on accounting, blocking-marked writes bypass; stage 4: freed regions stay with the C allocator (`RssAnon` does not fall), and the process grew past the regions with 192 KiB cells | node; **not used** under `cassandra.yaml` (`heap_buffers`), **used** under `cassandra_latest.yaml:836` | `DatabaseDescriptor.java:583-584`; `db/memtable/AbstractAllocatorMemtable.java:106-108`; `utils/memory/NativeAllocator.java:176`, `:190`; `utils/memory/MemoryUtil.java:81-84` | [`memtable_offheap_space-tryAllocate-limit--guided`](cases/memtable_offheap_space-tryAllocate-limit--guided.md), [`memtable-offheap-space-allocate-size`](cases/memtable-offheap-space-allocate-size--autonomous.md), [`max_region_size-tryswapregion-minsize`](cases/max_region_size-tryswapregion-minsize--autonomous.md), [`none-allocateoversize-peer`](cases/none-allocateoversize-peer--autonomous.md) |
| `row_cache_size` (OHC) | 0 MiB → off (`NopCacheProvider`) | hard per segment when on, plus OHC map overhead outside the capacity | node | `Config.java:472-474`; `cache/OHCProvider.java:40`; `conf/cassandra.yaml:564` | [`row_cache_size-setRowCacheCapacityInMB-capacity`](cases/row_cache_size-setRowCacheCapacityInMB-capacity--autonomous.md) |
| `index_summary_capacity` | empty → max(1, 5 % H) MiB | **soft**: periodic redistribution (60 m), floor on sampling, new SSTables arrive at full size; yaml: "best-effort" | node; BIG format only (default), none under BTI | `DatabaseDescriptor.java:867-869`; `conf/cassandra.yaml:931-939`; `io/util/Memory.java:65` | [`index_summary_capacity-applySimpleConfig-…`](cases/index_summary_capacity-applySimpleConfig-indexSummaryCapacityInMiB--autonomous.md), [`…-adjustSamplingLevels-…`](cases/index_summary_capacity-adjustSamplingLevels-remainingSpace--autonomous.md) |
| Bloom filters (`bloom_filter_fp_chance`) | per table option; sizes bits per key | **no cap** on the total: per SSTable × partition keys | per SSTable | `io/util/Memory.java:65` (allocator) | [`bloom_filter_fp_chance-getFilter-…`](cases/bloom_filter_fp_chance-getFilter-maxFalsePosProbability--autonomous.md), [`…computeBloomSpec-…`](cases/bloom_filter_fp_chance-computeBloomSpec-maxFalsePosProb--autonomous.md) |
| Compression offsets | 8 B per chunk (16 KiB default chunk) ≈ 0.05 % of uncompressed data (*estimate*) | **no cap** | per SSTable | `io/util/Memory.java:65` | [`compression-metadata-writer-addOffset-maxCount`](cases/compression-metadata-writer-addOffset-maxCount--autonomous.md) |
| Other `Memory`-backed structures | — | no cap found | per SSTable / writer | — | [`entry-size-limit-serialize-serializedSize`](cases/entry-size-limit-serialize-serializedSize--autonomous.md) |
| JVM native: thread stacks, metaspace, code cache, GC structures | `-Xss256k`; no `MaxMetaspaceSize` / code-cache option in `conf/*.options`; `MALLOC_ARENA_MAX=4` | **no cap** in the shipped config (not phase-1 constraints) | per thread (thread counts as in §2) | `conf/jvm-server.options:123`; `conf/cassandra-env.sh:143-145` | — |

### 3.2 Sums

| | A (H 2048) | B / C (H 8192) | D (H 31744) |
|---|---|---|---|
| Node-level **hard** defaults, `cassandra.yaml` | 0 | 0 | 0 |
| Soft: index summaries 5 % H | 102 | 409 | 1587 |
| `cassandra_latest.yaml`: off-heap memtable H/4 (no summaries under BTI) | 512 | 2048 | 7936 |
| Per-SSTable, no cap | bloom filters + compression offsets ∝ keys and data held | same | same |

The domain has no budget of its own; its only bound is RAM or the container (§4).

### 3.3 Verdict

Under `cassandra.yaml` no hard default reserves native memory; what is there grows with data
(summaries softly held near 5 % H, bloom filters and compression offsets without a cap). Under
`cassandra_latest.yaml` H/4 of memtable moves here, outside both `-Xmx` and `MaxDirectMemorySize`,
and stage 4 showed the freed part is not returned to the OS.

---

## 4. Domain 4 — process total (budget: RAM or container)

The heap is committed and touched at start (`-Xms` = `-Xmx`, `conf/cassandra-env.sh:149-151`;
`-XX:+AlwaysPreTouch`, `conf/jvm-server.options:128`), so RSS ≥ H from boot. The JVM limits allow
H + D; native memory adds on top without a limit.

| | A (H 2048, container 4096) | B / C (H 8192, 16384) | D (H 31744, RAM 65536; 2 × H = 63488) |
|---|---|---|---|
| H + D_env | 3072 → 75.0 % | 12288 → 75.0 % | 47616 → 72.7 % of RAM, 75.0 % of 2 × H |
| + summaries (`cassandra.yaml`) | 3174 → 77.5 % | 12697 → 77.5 % | 49203 → 75.1 % / 77.5 % |
| + off-heap memtable (`cassandra_latest.yaml`) | 3584 → **87.5 %**, 512 MiB left for metaspace, code cache, thread stacks, GC, bloom filters | 14336 → 87.5 % | 55552 → 84.8 % / 87.5 % |
| H + D_jvm | 4096 → **100 %**: exceeded by every native byte (≥ 102 MiB of summaries) | 16384 → **100 %**: exceeded by ≥ 409 MiB | 63488 → 96.9 % of RAM; + summaries 99.3 %; **+ `cassandra_latest` memtable 109.0 % of RAM (+5888 over)**; 100 % of a 2 × H container |
| H + what the default pools reserve (S_D core) + summaries | 2886 → 70.5 % | 9338 → 57.0 % | 34067 → 52.0 % |

**Verdict.** With `cassandra-env.sh` the JVM limits take 75 % of RAM at the automatic heap
(and of a 2 × H container when `free` reports that container), 87.5 % with the
`cassandra_latest.yaml` memtable, leaving 12.5–25 % for all uncapped native memory (*estimate* of
headroom, no native sum was measured here). Without `cassandra-env.sh` the JVM default direct limit
makes H + D equal a 2 × H container on its own, so any native allocation passes it at every
reference deployment; at D with `cassandra_latest.yaml` the limits pass physical RAM by ≈ 5.75 GiB.

**Hand-set heap on a larger host.** D_env follows the RAM that `free -m` reports, not H: a 2 GiB
heap on a host reporting 64 GiB gets `MaxDirectMemorySize` = 15872 MiB (`conf/cassandra-env.sh:60-62`,
`:139-141`), so H + D = 17920 MiB against a 4 GiB container (4.4 ×). Inside a container `free -m`
typically reports the host's memory, not the cgroup limit (*estimate*: Linux behaviour, not in the
tree), which puts container deployments with a hand-set heap in this case.

---

## 5. Not settled here

- The heap share actually free for retained data under `G1NewSizePercent=50` (§1.2): a GC reading
  under a full memtable pool and full reserves would settle it.
- Whether Netty's pooled arenas (`transport/CBUtil.java:60`) are counted against the JDK's
  `MaxDirectMemorySize` reservation or tracked separately by Netty: depends on Netty 4.1 internals
  outside the pinned tree.
- Native totals (metaspace, code cache, stacks, GC structures, glibc arenas) were not measured in
  phase 1; §4's headroom figures are budgets, not readings.
- The ≈ 4.8 GB `BufferPool` rise in the native receive-queue case (its §8a E4) has no settled cause.

---

## Flags

One line per case where the shipped defaults of one domain can exceed its budget, or a per-owner
term is unbounded at defaults. Deployment ids as in §0.

1. **Heap** — [`segment_write_buffer_size-validate-…`](cases/segment_write_buffer_size-validate-maximum_segment_buffer_mb--autonomous.md): SAI's fixed 1024 MiB soft segment-build budget, added to memtable H/4, request H/10, the two 512 MiB internode reserves and the caches, exceeds H for every H below ≈ 3.4 GiB (A: +937 MiB) — applies when SAI indexes are built outside memtable flush.
2. **Heap** — [`internode_application_send_queue_capacity-…--guided`](cases/internode_application_send_queue_capacity-acquireCapacity-pendingCapacityInBytes--guided.md), [`internode_application_receive_queue_capacity-…--guided`](cases/internode_application_receive_queue_capacity-acquireCapacity-queueCapacity--guided.md): fixed 2 × 512 MiB global reserves plus 24P–28P MiB of per-link allowance, with memtable H/4 and request H/10, pass H at A from 4 peers; heap-independent reserves make small heaps the exposed case.
3. **Heap** — [`key_cache_size-applySimpleConfig-…`](cases/key_cache_size-applySimpleConfig-keyCacheSizeInMiB--autonomous.md), [`counter_cache_size-applySimpleConfig-…`](cases/counter_cache_size-applySimpleConfig-counterCacheSizeInMiB--autonomous.md), [`paxos_cache_size-close-active`](cases/paxos_cache_size-close-active--autonomous.md): weighers under-count real heap (2.17 ×, 1.8 ×, ≈ 2.2 ×), which takes the hard heap sum at A to ≈ 104.6 % of H with no per-peer term (*estimate*, A only).
4. **Heap** — [`maxTasksQueued-addTask-…`](cases/maxTasksQueued-addTask-taskPermits--autonomous.md): stage task queues are unbounded (`Integer.MAX_VALUE`); per-owner term unbounded at every deployment.
5. **Heap** — [`native_transport_max_concurrent_connections-channelActive-limit--guided`](cases/native_transport_max_concurrent_connections-channelActive-limit--guided.md): connection count unlimited at −1, 1,329.6 B heap + 1 fd per idle connection (stage 4); unbounded at every deployment.
6. **Heap** — [`local_read_size_fail_threshold-…--guided`](cases/local_read_size_fail_threshold-addSize-failBytes--guided.md), [`coordinator_read_size_fail_threshold-…--guided`](cases/coordinator_read_size_fail_threshold-shouldReject-thresholdBytes--guided.md): `read_thresholds_enabled: false`, so per-read materialization × `concurrent_reads` has no cap at defaults; every deployment.
7. **Heap / direct** — [`repair_session_space-split-maxsize--guided`](cases/repair_session_space-split-maxsize--guided.md): the budget is per validation and `concurrent_merkle_tree_requests: 0` sets no limit, so coordinator off-heap trees (≈ 0.32 × H/16 per table-range) grow with jobs; every deployment.
8. **Direct** — [`file_cache_size-allocateMoreChunks-…--guided`](cases/file_cache_size-allocateMoreChunks-memoryUsageThreshold--guided.md), [`networking_cache_size-allocateMoreChunks-…--guided`](cases/networking_cache_size-allocateMoreChunks-memoryUsageThreshold--guided.md): both pools overflow past their limit into uncapped direct allocations, and native-v5 responses to a slow reader have no cap; bounded only by `MaxDirectMemorySize`, every deployment.
9. **Direct** — [`native_transport_receive_queue_capacity-…--guided`](cases/native_transport_receive_queue_capacity-acquireCapacity-queueCapacity--guided.md), [`internode_application_receive_queue_capacity-releaseCapacity-…`](cases/internode_application_receive_queue_capacity-releaseCapacity-queueCapacity--autonomous.md): request (H/10) and internode receive (512 MiB + per peer) bytes wait as frames in the networking pool; with the default pools they exceed D_env at A by ≈ 429 MiB.
10. **Direct** — [`DOB_MAX_RECYCLE_BYTES-close-…--guided`](cases/DOB_MAX_RECYCLE_BYTES-close-MAX_RECYCLE_BUFFER_SIZE--guided.md): 1 MiB idle per thread × ≈ 260 + cores threads, in-use up to ≈ 32 MiB per writing thread; idle retention alone takes A's pools + reserves to ≈ 170 % of D_env (32 cores), and in-use buffers have no node cap at any deployment.
11. **Direct** — [`max-cloned-size-allocate-size`](cases/max-cloned-size-allocate-size--autonomous.md), [`slab-region-size-region-allocate-capacity`](cases/slab-region-size-region-allocate-capacity--autonomous.md): with `memtable_allocation_type: offheap_buffers` the H/4 memtable joins the 736 MiB of pools and exceeds D_env at A by ≈ 224 MiB (non-default allocation type).
12. **Direct** — [`chunk_length_in_kb-loadNextChunk-compressedChunk`](cases/chunk_length_in_kb-loadNextChunk-compressedChunk--autonomous.md): inbound stream buffers regrow to the sender's chunk length with no receiver cap, × concurrent streams; every deployment.
13. **Direct** — [`native_transport_max_frame_size-decode-bytesToDiscard`](cases/native_transport_max_frame_size-decode-bytesToDiscard--autonomous.md), [`max_queue_weight-acquireWeight-weight`](cases/max_queue_weight-acquireWeight-weight--autonomous.md): Netty's `PooledByteBufAllocator` for CQL channels is outside Cassandra's pool accounting and has no Cassandra cap; every deployment.
14. **Native** — [`bloom_filter_fp_chance-getFilter-…`](cases/bloom_filter_fp_chance-getFilter-maxFalsePosProbability--autonomous.md), [`compression-metadata-writer-addOffset-maxCount`](cases/compression-metadata-writer-addOffset-maxCount--autonomous.md), [`index_summary_capacity-applySimpleConfig-…`](cases/index_summary_capacity-applySimpleConfig-indexSummaryCapacityInMiB--autonomous.md): per-SSTable bloom filters and compression offsets have no cap and index summaries only a soft 5 % H; outside both JVM limits, every deployment.
15. **Native** — [`memtable_offheap_space-tryAllocate-limit--guided`](cases/memtable_offheap_space-tryAllocate-limit--guided.md): under `cassandra_latest.yaml` (`offheap_objects`) H/4 of memtable is JNA `malloc` outside `-Xmx` and `MaxDirectMemorySize`, and freed regions are not returned to the OS (stage 4); takes H + D_env + native to 87.5 % of a 2 × H container before metaspace, stacks and GC.
16. **Process** — [`chunk_length_in_kb-loadNextChunk-compressedChunk`](cases/chunk_length_in_kb-loadNextChunk-compressedChunk--autonomous.md) (A4 assumes the JVM default applies): without `cassandra-env.sh`, `MaxDirectMemorySize` = H, so H + D = 2 × H fills a 2 × H container before any native memory; at D with `cassandra_latest.yaml` the limits pass 64 GiB RAM by ≈ 5.75 GiB.
17. **Process** — [`repair_session_space-initHelper-max`](cases/repair_session_space-initHelper-max--autonomous.md), [`WRITE_BUFFER_SIZE-append-remaining`](cases/WRITE_BUFFER_SIZE-append-remaining--autonomous.md) (E4 rows read D as ≈ heap/2): `cassandra-env.sh` sizes `MaxDirectMemorySize` from reported RAM even when the heap is set by hand (`conf/cassandra-env.sh:58-67`, `:139-141`), against `conf/jvm-server.options:173`'s "half of max heap size"; a 2 GiB heap on a host reporting 64 GiB gets 15.5 GiB of direct limit, 4.4 × a 4 GiB container.
