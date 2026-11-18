# Stage 5 wave 2 — full candidate text (2026-11-18)

Full clue and `file:line` for each `OC-` row filed from wave 2 (workflow `wf_f523921e-595`; guided agents used CP-1..CP-16). The candidate list row holds the first sentence.

## OC-256

**Case file:** `max-cloned-size-allocate-size--autonomous` · **Agent:** autonomous · **Patterns:** —

Slab region bytes the memtable pool never charges. SlabAllocator charges the pool only the requested size (:89), but it takes memory in whole 1 MiB regions (:139), both on heap (the default heap_buffers mode) and off heap. Two parts are never charged: the tail of each retired region, which is left behind when Region.allocate fails (:199-203, then :112), and the unused rest of each memtable's current region. Regions that lose the CAS race and sit in the static RACE_ALLOCATED queue (:55, :151) are also uncharged. Nothing bounds the number of regions except the requested bytes, and the flush trigger sees only those requested bytes (MemtablePool.java:151-158). Size at defaults (heap_buffers, memtable_heap_space = heap/4): (a) about 1 MiB per table with a live memtable, even if it holds only a few bytes, so 1000 tables give about 1 GiB of heap that the pool does not see and that will not trigger a flush; (b) tail waste of up to about 12.6% of the pool for values near 114 KiB. Stage 4 measured 12.57-12.67% at S = 116736. On an 8 GiB heap that is about 250 MiB over the 2 GiB pool.

**Where:** src/java/org/apache/cassandra/utils/memory/SlabAllocator.java:89, :102-113, :126-153, :197-206; MemtablePool.java:151-158

## OC-257

**Case file:** `max-cloned-size-allocate-size--autonomous` · **Agent:** autonomous · **Patterns:** —

A flush lets older writes allocate past the memtable limit. The flush marks every write older than its barrier as blocking (ColumnFamilyStore.java:1238). After that, SubAllocator.allocate charges memory with allocated(size) even when tryAllocate fails (MemtableAllocator.java:180-184), so none of those writes wait for room. The overshoot is limited only by how many writes are in flight in the old group and how big they are: about concurrent_writes (32) plus counter writes, times max_mutation_size (default 16 MiB, half a commitlog segment). That is up to about 512 MiB above memtable_heap_space at defaults, held at the same moment the pool is full. Stage 4 saw 16 MiB pass the limit with no parking in the unit probe.

**Where:** src/java/org/apache/cassandra/utils/memory/MemtableAllocator.java:169-197; src/java/org/apache/cassandra/db/ColumnFamilyStore.java:1236-1239

## OC-258

**Case file:** `max-unsigned-short-validate-key-remaining--autonomous` · **Agent:** autonomous · **Patterns:** —

Index summary entries keep whole partition keys, up to the 65535-byte cap, in off-heap memory. A new BIG sstable (BIG is the default format, Config.java:373) builds its summary at full sampling: one entry per min_index_interval = 128 keys (BigTableWriter.java:255). The only limit per sstable is 2 GB (IndexSummaryBuilder.java:106-117, :204). index_summary_capacity (default 5% of heap, DatabaseDescriptor.java:867-869) is applied only by the redistribution task, which runs every 60 min (Config.java:543), and downsampling can shrink a summary by at most 16x (max_index_interval 2048). Size: with 64 KiB keys a summary costs about 512 B per partition. 2M such partitions (about 128 GB of keys) hold about 1 GiB of native summary memory, against a capacity of about 400 MiB on an 8 GiB heap, until the next redistribution.

**Where:** src/java/org/apache/cassandra/io/sstable/indexsummary/IndexSummaryBuilder.java:100-127, :200-209; src/java/org/apache/cassandra/io/sstable/format/big/BigTableWriter.java:255; src/java/org/apache/cassandra/config/Config.java:540-543

## OC-259

**Case file:** `native_transport_max_request_data_in_flight_per_ip-setNativeTransportMaxRequestDataInFlightPerIpInBytes-maxRequestDataInFlightInBytes--autonomous` · **Agent:** autonomous · **Patterns:** —

A refused v5 message is still run, and its release frees permits it never took, so the count drifts. In the default (no throw-on-overload) path, a self-contained message that fails acquireCapacity is still dispatched (CQLMessageHandler.java:223, :244-259 -> processRequestAndUpdateMetrics :267-271). Its permits are never taken: the wait-queue ticket's permits go to the next message. When it completes, release(header) (:507-511) calls releaseCapacity (AbstractMessageHandler.java:461-470), which lowers queueSize and returns endpoint and global permits that belonged to other messages. Every throttle event therefore leaves the connection with one more message's worth of 'free' capacity, and the per-IP and global counters under-count. Over time the real bytes in flight, plus their decoded heap copies, are bounded only by the client's concurrency (up to 32768 streams per v5 connection). Stage 4 (sibling global case) saw the whole offered load, +246 MiB of live heap byte[], held at L = 16 MiB while the counter read L.

**Where:** src/java/org/apache/cassandra/transport/CQLMessageHandler.java:221-262, :267-271, :507-511; src/java/org/apache/cassandra/net/AbstractMessageHandler.java:461-470

## OC-260

**Case file:** `native_transport_max_request_data_in_flight_per_ip-setNativeTransportMaxRequestDataInFlightPerIpInBytes-maxRequestDataInFlightInBytes--autonomous` · **Agent:** autonomous · **Patterns:** —

Buffers of multi-frame v5 requests are never given back to the networking BufferPool. Each frame of a large message (above 131071 B) is kept with share() (AbstractMessageHandler.java:572). LargeMessage.onComplete then dispatches assembleFrame() (CQLMessageHandler.java:762-769, :822-835), which wraps the buffers in an Unpooled CompositeByteBuf. releaseBuffers() is called only on the corrupt and abort paths (:812, :841). So ShareableBytes.release, which is what puts a buffer back (ShareableBytes.java:122-139), never runs for completed requests. The pooled chunks (networking_cache_size = min(128 MiB, heap/16)) stay pinned for good, and later reads overflow to unpooled allocateDirect, which only GC reclaims. Stage 4 measured a direct-memory floor of about 1.5 GiB on this case, and +780-820 MiB of direct memory in 90 s at every limit in the sibling global case. The default MaxDirectMemorySize is the max heap size, so a direct-buffer OOM is reachable.

**Where:** src/java/org/apache/cassandra/transport/CQLMessageHandler.java:762-769, :822-835; src/java/org/apache/cassandra/net/AbstractMessageHandler.java:572, :593-596; src/java/org/apache/cassandra/net/ShareableBytes.java:122-139

## OC-261

**Case file:** `native_transport_max_request_data_in_flight_per_ip-setNativeTransportMaxRequestDataInFlightPerIpInBytes-maxRequestDataInFlightInBytes--autonomous` · **Agent:** autonomous · **Patterns:** —

Each connection gets an allowance that sits outside the per-IP and global limits, and connections are unlimited by default. v5: every connection holds native_transport_receive_queue_capacity (1 MiB, Config.java:302) of request bytes before it touches either reserve (AbstractMessageHandler.java:418-423). v4: each connection force-allocates a request it was refused, plus any requests already decoded from the same read (PreV5Handlers.java:181-186). native_transport_max_concurrent_connections and _per_ip both default to -1, unlimited (Config.java:289-290). Size: 1 MiB per v5 connection, or up to one native_transport_max_message_size (16 MiB at defaults) per v4 connection. 2000 connections from one IP therefore hold about 2 GiB (v5) or up to 32 GiB (v4) of request bytes beyond the per-IP limit of heap/40, before the decoded heap copies are counted.

**Where:** src/java/org/apache/cassandra/net/AbstractMessageHandler.java:411-423; src/java/org/apache/cassandra/transport/PreV5Handlers.java:181-186; src/java/org/apache/cassandra/config/Config.java:289-290, :302

## OC-262

**Case file:** `native-transport-max-request-data-in-flight-setNativeTransportConcurrentRequestDataInFlightInBytes-maxRequestDataInFlightInBytes--autonomous` · **Agent:** autonomous · **Patterns:** —

A refused v5 message is still run, and its release frees permits it never took, so the count drifts. When acquireCapacityAndQueueOnFailure fails in the default mode (CQLMessageHandler.java:223), the self-contained message is dispatched anyway (:244-259, :267-271). The ticket that follows takes permits for the next message, not this one. When this one completes, release(header) (:507-511) calls releaseCapacity (AbstractMessageHandler.java:461-470), which subtracts its size from queueSize and returns global and endpoint permits it never acquired. Each throttle event therefore permanently adds one message (up to 128 KiB) to the connection's free capacity, and GLOBAL_LIMIT.using() under-counts. Under sustained overload, admitted request bytes and their decoded heap copies grow past heap/10 without a bound other than client concurrency. Stage 4: V5/100K arms held the whole offered load (+246 MiB of live heap byte[]) at L = 16 MiB, 64 MiB and the default, while RequestsSize read L.

**Where:** src/java/org/apache/cassandra/transport/CQLMessageHandler.java:221-262, :267-271, :507-511; src/java/org/apache/cassandra/net/AbstractMessageHandler.java:461-470

## OC-263

**Case file:** `native-transport-max-request-data-in-flight-setNativeTransportConcurrentRequestDataInFlightInBytes-maxRequestDataInFlightInBytes--autonomous` · **Agent:** autonomous · **Patterns:** —

Frame buffers of multi-frame v5 requests are never released to BufferPools.forNetworking(). Frames are kept with share() (AbstractMessageHandler.java:572). The completed request is assembled into an Unpooled wrapper (CQLMessageHandler.java:762-769) and dispatched from onComplete (:822-835) without releaseBuffers(), which runs only on the corrupt and abort paths (:812, :841). ShareableBytes therefore never returns the bytes (ShareableBytes.java:122-139). The pooled networking cache (min(128 MiB, heap/16)) stays pinned, and further reads overflow to unpooled allocateDirect, which only GC reclaims. Stage 4: V5/256K requests added 780-820 MiB of direct memory in 90 s at every L, independent of the limit. With the default MaxDirectMemorySize equal to the heap size, a 1 GiB setting would already have hit an OOM.

**Where:** src/java/org/apache/cassandra/transport/CQLMessageHandler.java:762-769, :822-835; src/java/org/apache/cassandra/net/AbstractMessageHandler.java:572; src/java/org/apache/cassandra/net/ShareableBytes.java:122-139

## OC-264

**Case file:** `native-transport-max-request-data-in-flight-setNativeTransportConcurrentRequestDataInFlightInBytes-maxRequestDataInFlightInBytes--autonomous` · **Agent:** autonomous · **Patterns:** —

Each connection gets an allowance outside the global limit, and connections are unlimited by default. v5: every connection holds up to native_transport_receive_queue_capacity (1 MiB) without drawing on the global reserve (AbstractMessageHandler.java:418-423). v4: every refused request is force-allocated per connection, with requests already decoded from the same read (PreV5Handlers.java:181-186). Connection counts default to unlimited (Config.java:289-290). Size: about 1 MiB per v5 connection, or up to a 16 MiB max-size message per v4 connection. 2000 connections add about 2 GiB (v5) to 32 GiB (v4) above heap/10. Stage 4 saw the V4 direct pool grow 2-4x past 1.5 L + 6 MiB.

**Where:** src/java/org/apache/cassandra/net/AbstractMessageHandler.java:411-423; src/java/org/apache/cassandra/transport/PreV5Handlers.java:181-186; src/java/org/apache/cassandra/config/Config.java:289-290, :302

## OC-265

**Case file:** `slab-region-size-region-allocate-capacity--autonomous` · **Agent:** autonomous · **Patterns:** —

Slab regions are allocated in whole 1 MiB REGION_SIZE units, but the pool is charged only the requested bytes (:89). The memory of a region that is not charged stays unaccounted: the tail of each retired region after the failed fit test at :201 (getAndAdd at :199 consumes the tail for good), the unfilled rest of each memtable's live region, and regions parked in the static RACE_ALLOCATED queue (:55, :151). Nothing bounds the number of regions except requested bytes, and the flush trigger sees only those (MemtablePool.java:151-158). Size at defaults (heap_buffers, so byte[] regions on the heap, and memtable_heap_space = heap/4): (a) up to 1 MiB per table or index with a live memtable, whatever it holds, so 1000 tables give about 1 GiB of heap the pool does not see and that will not trigger a flush; (b) for values near 1 MiB/9 (about 116 KiB) the tail waste is about 12.5% of the pool, roughly 250 MiB on an 8 GiB heap.

**Where:** src/java/org/apache/cassandra/utils/memory/SlabAllocator.java:89, :102-113, :126-153, :197-206; src/java/org/apache/cassandra/utils/memory/MemtablePool.java:151-158

## OC-266

**Case file:** `slab-region-size-region-allocate-capacity--autonomous` · **Agent:** autonomous · **Patterns:** —

A flush lets older writes allocate past the memtable limit. The flush calls writeBarrier.markBlocking() (ColumnFamilyStore.java:1238). From then on, every write in the older op group that finds the pool full takes allocated(size) without waiting (MemtableAllocator.java:180-184). The excess is limited only by the writes in flight in that group: about 32 concurrent writes (plus counter writes) times max_mutation_size (16 MiB at defaults), so up to about 512 MiB above memtable_heap_space, at the moment the pool is already full.

**Where:** src/java/org/apache/cassandra/utils/memory/MemtableAllocator.java:169-197; src/java/org/apache/cassandra/db/ColumnFamilyStore.java:1236-1239

## OC-267

**Case file:** `max-cloned-size-allocate-size--autonomous` · **Agent:** guided · **Patterns:** CP-1

Memtable slab tail waste and race-stashed regions are never charged to the memtable pool (also in case slab-region-size-region-allocate-capacity--autonomous; file once, naming both stems). Holder: the SlabAllocator 1 MiB regions. Each clone charges only its requested size to the pool (SlabAllocator.java:89). When the next clone does not fit, the region is dropped (:112), and its unused tail is real heap (default heap_buffers) or direct memory that no counter sees. Regions that lose the CAS race go to the static RACE_ALLOCATED queue, shared by all tables, also uncharged (:55, :151). Why nothing stops it: memtable_heap_space / memtable_offheap_space compare only the summed requested bytes (MemtablePool tryAllocate). Size at defaults: stage 4 measured real memory at 1.125 x accounted at the stall (S = 116,509 to 116,736 B values, 12.6 % waste) and 1.05-1.19 x in the cluster. At the default pool of heap/4, about heap/32 more is held outside the pool (about 256 MiB at an 8 GiB heap). On top of that comes the live-region effect filed under the slab-region stem.

**Where:** src/java/org/apache/cassandra/utils/memory/SlabAllocator.java:89 (charge), :112 and :199-203 (region dropped when full), :55 and :151 (RACE_ALLOCATED)

## OC-268

**Case file:** `slab-region-size-region-allocate-capacity--autonomous` · **Agent:** guided · **Patterns:** CP-1, CP-7, CP-15

Each memtable pins a whole 1 MiB slab region that is charged only for the bytes written, and nothing caps how many memtables can hold one (also in case max-cloned-size-allocate-size--autonomous; file once, naming both stems). Holder: one SlabAllocator per memtable (AbstractAllocatorMemtable.java:118). It takes its current region (ByteBuffer.allocate(1 MiB) in the default heap_buffers mode, SlabAllocator.java:139) on the first clone, and the pool is charged only the clone size (:89). Why nothing stops it: memtable_heap_space counts requested bytes, so small memtables look nearly empty. The cleaner flushes the largest memtable first, so small ones keep their region until commit-log pressure. The table-count guardrails ship off (tables_warn/fail_threshold = -1, Config.java:865-866), and secondary-index and system-table memtables count too. Size at defaults: stage 4 (recheck run 1b, 2026-11-17) measured 0.9999 MiB of live [B per written table against 1.49 KiB counted (N = 200: 199.95 MiB vs 0.29 MiB), with the same slope at memtable_heap_space 64, 256 and 2048 MiB. At about 1 MiB per table, 1,000 tables with one small write each hold about 1 GiB of heap outside the memtable pool (heap/4 = 2 GiB at an 8 GiB heap).

**Where:** src/java/org/apache/cassandra/utils/memory/SlabAllocator.java:139 (whole-region allocate), :89 (charge = requested size); src/java/org/apache/cassandra/db/memtable/AbstractAllocatorMemtable.java:118 (allocator per memtable); src/java/org/apache/cassandra/config/Config.java:865-866 (table guardrail off)

## OC-269

**Case file:** `native_transport_max_request_data_in_flight_per_ip-setNativeTransportMaxRequestDataInFlightPerIpInBytes-maxRequestDataInFlightInBytes--autonomous` · **Agent:** guided · **Patterns:** CP-7, CP-1

The native-v5 per-connection receive queue sits outside both the per-IP and the global in-flight limits, and connections are unbounded (also in case native-transport-max-request-data-in-flight-...--autonomous; file once, naming both stems). Holder: each CQL v5 connection's queueCapacity (native_transport_receive_queue_capacity, default 1 MiB, Config.java:302). acquireCapacity takes the request bytes from that queue first and charges only the excess to the global and endpoint reserves (AbstractMessageHandler.java:418-436). Why nothing stops it: native_transport_max_concurrent_connections and native_transport_max_concurrent_connections_per_ip are both -1 (Config.java:289-290), so one IP holds up to C x 1 MiB + heap/40, and the node holds up to C x 1 MiB + heap/10. Size: stage 4 measured the bytes held beyond the limit as exactly C x Q. 1,000 connections give about 1 GiB of request frames (mostly pooled direct memory) beyond the default global heap/10 (about 0.8 GiB at an 8 GiB heap), against a direct budget that defaults to heap/2.

**Where:** src/java/org/apache/cassandra/net/AbstractMessageHandler.java:418-436; src/java/org/apache/cassandra/config/Config.java:289-290, :302

## OC-270

**Case file:** `native_transport_max_request_data_in_flight_per_ip-setNativeTransportMaxRequestDataInFlightPerIpInBytes-maxRequestDataInFlightInBytes--autonomous` · **Agent:** guided · **Patterns:** CP-6, CP-7

In the native-v4 default (backpressure) mode, a request the in-flight limit refuses is force-allocated and dispatched anyway, once per connection (also in the global in-flight case; file once, naming both stems). Holder: LegacyDispatchHandler.checkLimits. On tryAllocate failure it calls endpointPayloadTracker.allocate(requestSize) unconditionally, pauses the connection and still processes the request. Requests already decoded from the same read are also dispatched after the pause. Why nothing stops it: each V4 connection checks independently, connections are unlimited (-1), and older protocols are allowed by default (native_transport_allow_older_protocols = true). The only bound per forced request is native_transport_max_message_size, which defaults to min(max_mutation_size 16 MiB, global, per-IP) (DatabaseDescriptor.java:3237-3244). Size: overshoot up to C x 16 MiB beyond the per-IP or global limit (100 V4 connections give about 1.6 GiB of bodies plus decoded objects on the heap). Stage 4 showed the overshoot is per connection (L + 3 messages in the unit arm).

**Where:** src/java/org/apache/cassandra/transport/PreV5Handlers.java:178-186; src/java/org/apache/cassandra/config/DatabaseDescriptor.java:3237-3244; src/java/org/apache/cassandra/config/Config.java:289-292

## OC-271

**Case file:** `native_transport_max_request_data_in_flight_per_ip-setNativeTransportMaxRequestDataInFlightPerIpInBytes-maxRequestDataInFlightInBytes--autonomous` · **Agent:** guided · **Patterns:** CP-3, CP-5, CP-6

The per-IP (and global) charge is released at response hand-off. The encoded response, held in pooled direct memory until the socket drains, is never charged. For CL=ONE writes the coordinator's own local mutation is still queued on MutationStage after the charge is returned. This is the case's own back-link recheck and matches the existing phase-2 true positives C2 and S2: file only as a cross-reference if those rows do not already name this stem. Size: bounded only by MaxDirectMemorySize (responses) or the heap (queued local writes).

**Where:** src/java/org/apache/cassandra/transport/CQLMessageHandler.java:500-510; src/java/org/apache/cassandra/transport/PreV5Handlers.java:99-110; src/java/org/apache/cassandra/service/StorageProxy.java:1569

## OC-272

**Case file:** `native-transport-max-request-data-in-flight-setNativeTransportConcurrentRequestDataInFlightInBytes-maxRequestDataInFlightInBytes--autonomous` · **Agent:** guided · **Patterns:** CP-6, CP-10, CP-1

Native-v5 small (contained, < 131,071 B) requests are not bounded by the in-flight limit. Holder: CQLMessageHandler.processOneContainedMessage. When acquireCapacityAndQueueOnFailure fails (:223), the request is still dispatched (processRequestAndUpdateMetrics with backpressure, :245-247), and its bytes are not charged until the wait queue grants a ticket. Why nothing stops it: the counter (Client.RequestsSize) plateaus at L, but it bounds admission accounting, not what the connection has read and copied. Size: stage 4 measured the live heap at +246.4-246.6 MiB, the whole offered load (2,560 x 100,000 B), at every L including 16 MiB and the 1 GiB control, while RequestsSize sat at L. Bounded only by what clients send (connections x requests in flight); the exact line that copies the remaining bodies onto the heap was not traced in stage 4.

**Where:** src/java/org/apache/cassandra/transport/CQLMessageHandler.java:223, :245-247 (dispatch despite failed acquire); src/java/org/apache/cassandra/net/AbstractMessageHandler.java:396-409

## OC-273

**Case file:** `native-transport-max-request-data-in-flight-setNativeTransportConcurrentRequestDataInFlightInBytes-maxRequestDataInFlightInBytes--autonomous` · **Agent:** guided · **Patterns:** CP-14, CP-6

Native-v5 large (multi-frame, >= 131,071 B) requests leave direct frame buffers unreturned. Holder: LargeMessage.buffers (ShareableBytes slices of networking-pool frames, AbstractMessageHandler.java:572). assembleFrame wraps them and calls body.retain() (CQLMessageHandler.java:762-769). onComplete dispatches without releasing the buffers (:822-834), and the flush release drops only one reference (:500-504). Why nothing stops it: the in-flight counter is released normally, so it shows nothing. Only MaxDirectMemorySize bounds the residue. Size: stage 4 measured +780-820 MiB of direct memory per 90 s of 256 KiB requests, flat across L (16 MiB to 1 GiB); a shakedown filled 1 GiB of direct memory in under 90 s. Default direct memory is about heap/2, so a sustained stream of large v5 requests reaches OutOfDirectMemoryError in minutes. The leak itself was inferred, not traced to one line.

**Where:** src/java/org/apache/cassandra/transport/CQLMessageHandler.java:762-769 (assembleFrame retain), :822-834 (onComplete, no releaseBuffers), :500-504 (release)

## OC-274

**Case file:** `native-transport-max-request-data-in-flight-setNativeTransportConcurrentRequestDataInFlightInBytes-maxRequestDataInFlightInBytes--autonomous` · **Agent:** guided · **Patterns:** CP-1, CP-14

On the native-v4 path the direct pool grows 2-4 x past the in-flight bound. The counter charges only request body bytes, while the Netty pooled direct chunks that carry v4 frames and responses are retained and grow in 16 MiB steps that do not fall back within the run. Why nothing stops it: no counter covers pool chunks or responses. Size: stage 4 measured a direct delta of 128 / 208 / 320 MiB at L = 16 / 64 / 102 MiB, while the live heap followed L (+16.8 / +64.9 / +103.5 MiB). This is weaker than the v5 findings; the chunk retention was inferred from the 16 MiB granularity.

**Where:** src/java/org/apache/cassandra/transport/PreV5Handlers.java:178-186 (counts bodySizeInBytes only); src/java/org/apache/cassandra/transport/CBUtil.java:60 (pooled allocator)

## OC-275

**Case file:** `max-unsigned-short-validate-key-remaining--autonomous` · **Agent:** guided · **Patterns:** CP-11, CP-9

The index summary stores whole partition keys (up to the 65,535 B this check allows), and its node-wide capacity is enforced only by a periodic redistribution. Holder: the off-heap IndexSummaryBuilder of each new BIG sstable (default format). It writes the full key every min_index_interval (128) partitions (IndexSummaryBuilder.java:204-207), and the only per-sstable cap is 2 GiB (:202). Why nothing stops it: index_summary_capacity (default 5 % of heap, DatabaseDescriptor.java:867-868) is applied by IndexSummaryManager.redistributeSummaries on a fixed delay (IndexSummaryManager.java:141-145) of index_summary_resize_interval = 60 min (Config.java:543), so summaries built by flushes and compactions in between are not checked. Size: with 64 KiB keys a summary costs about 512 B per partition. One compacted sstable of 1M such partitions builds about 512 MiB of native memory, against a 5 % capacity of about 400 MiB at an 8 GiB heap. Several concurrent compactions multiply this. Speculative: it needs very large keys at volume.

**Where:** src/java/org/apache/cassandra/io/sstable/indexsummary/IndexSummaryBuilder.java:200-215; src/java/org/apache/cassandra/io/sstable/indexsummary/IndexSummaryManager.java:141-145; src/java/org/apache/cassandra/config/DatabaseDescriptor.java:867-868; src/java/org/apache/cassandra/config/Config.java:543

## OC-276

**Case file:** `batch_size_warn_threshold-verifyBatchSize-size--autonomous` · **Agent:** autonomous · **Patterns:** —

The batch's mutations are built in full on the coordinator heap before any batch-size check runs, and IN lists make that build far larger than the request. In a batch statement such as `UPDATE t SET v=? WHERE k IN ? AND c IN ?`, addUpdates builds one row for every (partition key x clustering) pair. Nothing caps that product at defaults: the in_select_cartesian_product guardrail on the shared restriction code is -1 (off), and the batch_size_warn and batch_size_fail checks (5 KiB / 50 KiB) and Mutation.validateSize (max_mutation_size 16 MiB) all run only after every PartitionUpdate has been built. Each row is about 150 B of heap (BTreeRow, cell, liveness info, btree array). A bound list of ints costs about 8 B per element, so a 1.6 MB request with 1,000 keys x 100,000 clusterings builds about 1e8 rows, or about 15 GB. That is past any default heap (8 GB at most), from one request well under the 16 MiB message cap.

**Where:** cql3/statements/BatchStatement.java:428,439 (verifyBatchSize after getMutations); BatchStatement.java:312 (addUpdates per statement); cql3/statements/ModificationStatement.java:792,802-816 (row per key x clustering); cql3/restrictions/ClusteringColumnRestrictions.java:112-113 and PartitionKeySingleRestrictionSet.java:95-96 (guardrail only if enabled); config/Config.java:877-878 (default -1); cql3/statements/SingleTableUpdatesCollector.java:112 and db/Mutation.java:169-176 (size check after build)

## OC-277

**Case file:** `max-unsigned-short-ClusteringPrefix-validate-accessor-size--autonomous` · **Agent:** autonomous · **Patterns:** —

The BIG-format partition writer, used for flush and compaction, keeps the whole partition's row index on heap until the partition is finished. Each index block's IndexInfo holds a full copy of both its first and its last clustering, and the default block granularity is 64 KiB (column_index_size unset). Once the index passes column_index_cache_size (2 KiB) it goes into one growing DataOutputBuffer. The 65535-byte limit allows a clustering key as large as a whole block, so every row becomes its own block and the index buffer is about 2x the partition's data (stage 4 measured Index.db at 2.0 x R x K). At defaults nothing limits partition size (partition_size_warn/fail thresholds are null). A 1 GiB partition of 64 KiB-key rows therefore needs a 2 GiB heap buffer, about 3.3 GB at the peak when the buffer grows by 1.5x and copies, before it hits the 2 GiB array limit. That cost applies to each concurrent compactor or flush writer (up to 8).

**Where:** io/sstable/format/big/BigFormatPartitionWriter.java:49,73,130-134,168-188,204,213-214; io/sstable/IndexInfo.java:107-117 (firstName and lastName both serialized); config/DatabaseDescriptor.java:2029-2032; config/Config.java:910-911; io/util/DataOutputBuffer.java:158-171; db/ClusteringPrefix.java:278-287 (allows keys up to 65535 B)

## OC-278

**Case file:** `max-unsigned-short-prepare-boundTerms--autonomous` · **Agent:** autonomous · **Patterns:** —

The 65535-marker check runs only after the whole query string has been lexed, parsed and prepared, so the parser's memory is already spent when the check rejects the statement. CQLFragmentParser keeps every token in an ANTLR CommonTokenStream (about 48 B per CommonToken, and `?,` is 2 tokens for 2 bytes of input). On top of that come the Marker.Raw AST nodes and the per-marker ColumnSpecification and Term objects, which stage 4 measured at 43 B per marker retained. That adds up to roughly 150-200 B of heap per 2 bytes of query text, about 100x. A query string is bounded only by the default native message size, min(max_mutation_size 16 MiB, in-flight limits). A 16 MiB `... IN (?,?,...)` has about 8M markers, which is about 1.2-1.6 GB of transient heap per PREPARE (the same parse happens for a plain QUERY) before it is rejected. The per-IP in-flight limit (heap/40, 200 MB at an 8 GB heap) admits about 12 such requests at once from one client, roughly 15-19 GB.

**Where:** cql3/QueryProcessor.java:754 (parseAndPrepare) before :757-759 (marker check); cql3/QueryProcessor.java:927; cql3/CQLFragmentParser.java:63-71 (CqlLexer + CommonTokenStream); config/DatabaseDescriptor.java:649-656,903-905,3237-3245 (only message-size and in-flight bounds)

## OC-279

**Case file:** `max-unsigned-short-validateKey-keyRemaining--autonomous` · **Agent:** autonomous · **Patterns:** —

The 65535-byte cap still allows partition keys of up to 64 KiB, and the BIG-format index summary (the default format) stores whole key bytes in off-heap native memory (Memory/SafeMemoryWriter, outside -Xmx and MaxDirectMemorySize). It stores one in every min_index_interval (128) keys. Its 2 GiB guard is sized from the default expected key size, not the real one. index_summary_capacity (5% of heap) is enforced only by redistribution every 60 minutes, and that can downsample no further than max_index_interval 2048. When the partitions have 64 KiB keys, each new sstable's summary is about data/128. A node with 500 GB of such partitions holds about 4 GB of native summary after flushes and compactions, and still about 250 MB after downsampling, against a 5%-of-heap budget. Newly compacted sstables restart at 1/128.

**Where:** io/sstable/indexsummary/IndexSummaryBuilder.java:100-127 (sizing by defaultExpectedKeySize), :200-208 (entries.write(key)), :352-353 (Memory.allocate); io/sstable/format/big/BigTableWriter.java:255 (minIndexInterval 128); schema/TableParams.java:365 (max 2048); config/DatabaseDescriptor.java:867-869; config/Config.java:373,543; cql3/Validation.java:51 (allows keys up to 65535 B)

## OC-280

**Case file:** `max-unsigned-short-validate-sum--autonomous` · **Agent:** autonomous · **Patterns:** —

The sum limit allows one clustering key of up to 65535 B, as large as a full 64 KiB row-index block. The BIG partition writer keeps the partition's whole row index on heap for flush and compaction: each IndexInfo holds both its first and last clustering, and the entries go into a growing DataOutputBuffer once they pass the 2 KiB column_index_cache_size. With maximal keys every row is its own block, so the index buffer is about 2x the partition's data (stage 4 measured Index.db at 2.0 x R x S). Partition size is uncapped at defaults (partition_size thresholds null). A 1 GiB partition of such rows needs about 2 GiB of buffer plus a 1.5x growth copy, about 3.3 GB at the peak, for each concurrent compactor or flush writer.

**Where:** io/sstable/format/big/BigFormatPartitionWriter.java:49,130-134,168-188,204,213-214; io/sstable/IndexInfo.java:107-117; config/DatabaseDescriptor.java:2029-2032; config/Config.java:910-911; io/util/DataOutputBuffer.java:158-171; db/ClusteringPrefix.java:282-287

## OC-281

**Case file:** `rows_per_partition-isFilterFullyCoveredBy-rowsPerPartitionToCache--autonomous` · **Agent:** autonomous · **Patterns:** —

This applies only when the row cache is on; row_cache_size defaults to 0. On a row-cache miss, CachedBTreePartition.create builds the cache entry on heap from a full-partition read. That read keeps going until N live rows are found, and it counts only live rows, so every row tombstone or expired row ahead of them is pulled in and kept. With rows_per_partition ALL, or a table with no clustering columns, it pulls in the whole partition. This happens inside queryStorage, before the withMetricsRecording wrapper that enforces tombstone_failure_threshold, so the 100,000-tombstone abort cannot stop it. OHC's capacity is checked only on put, after the build. Each concurrent reader builds its own copy even when another reader holds the sentinel. 1M row tombstones ahead of the first live row, at about 100 B each plus the clustering, is about 100+ MB per read, and concurrent_reads 32 makes that about 3+ GB. With ALL, any large partition is copied to heap in full.

**Where:** db/SinglePartitionReadCommand.java:491-493,558-561,569,583-598,604; db/ReadCommand.java:452 (queryStorage) before :461 (withMetricsRecording); cache/OHCProvider.java:40-43; config/Config.java:179 (concurrent_reads 32)

## OC-282

**Case file:** `tombstone-failure-threshold-withMetricsRecording-failureThreshold--autonomous` · **Agent:** autonomous · **Patterns:** —

The threshold counts tombstones, not bytes. Each counted tombstone (a row deletion or a range-tombstone bound) can carry a clustering of up to 65535 B. Up to 100,000 of them are serialized into the replica's heap DataOutputBuffer for the read response before the abort fires. At defaults no byte limit applies: read_thresholds_enabled is false and the local/coordinator read-size thresholds are null. Paging counts only live rows, not tombstones. Stage 4 measured 145 MiB per read with 1000-character clusterings. With about 64 KiB clusterings the buffer reaches the 2 GiB array limit, about 3.3 GB at the peak with the 1.5x growth copy, in a single read. Even at 1 KB keys, concurrent_reads 32 gives about 4.6 GB.

**Where:** db/ReadCommand.java:588-601 (count-only check), :461; db/ReadResponse.java:197-201 (whole response in DataOutputBuffer); config/Config.java:526-535; io/util/DataOutputBuffer.java:158-171; config/Config.java:179

## OC-283

**Case file:** `tombstone-failure-threshold-withMetricsRecording-failureThreshold--autonomous` · **Agent:** autonomous · **Patterns:** —

Live rows on the same path are not bounded at defaults. The read-size thresholds (withQuerySizeTracking) are off because read_thresholds_enabled is false and the sizes are null. An unpaged single-partition read (paging is set by the client) serializes the whole partition into the replica's heap response buffer, and the coordinator then holds the deserialized responses from each replica. A 1 GiB partition read unpaged needs about 1 GiB plus a 1.5x growth copy per replica read, and concurrent_reads 32 multiplies that.

**Where:** db/ReadCommand.java:457,663 (size tracking only when enabled); config/Config.java:526-530; db/ReadResponse.java:197-201

## OC-284

**Case file:** `unlogged_batch_across_partitions_warn_threshold-verifyBatchType-keySet--autonomous` · **Agent:** autonomous · **Patterns:** —

verifyBatchType (key count, warning only) and verifyBatchSize (bytes) both run only after getMutations has built every mutation on the coordinator heap. An IN list in a batch statement (`WHERE k IN ? AND c IN ?`) multiplies a small request into partitions x clusterings rows. Nothing caps that product at defaults: in_select_cartesian_product is -1 and partition_keys_in_select applies to SELECT only. The batch_size_fail threshold (50 KiB) and the per-mutation max_mutation_size check reject only after the build. At about 150 B per row, 1,000 keys x 100,000 clusterings bound as int lists (about 1.6 MB, under the 16 MiB message cap) is about 1e8 rows, or about 15 GB of heap. 1M partition keys alone add about 0.5-1 KB each in Mutation/PartitionUpdate/DecoratedKey objects, about 0.5-1 GB.

**Where:** cql3/statements/BatchStatement.java:428,439-440,312,373-384; cql3/statements/ModificationStatement.java:746-749,792,802-816; cql3/restrictions/ClusteringColumnRestrictions.java:112-113; cql3/restrictions/PartitionKeySingleRestrictionSet.java:95-96; config/Config.java:875-878; cql3/statements/SingleTableUpdatesCollector.java:112

## OC-285

**Case file:** `max-unsigned-short-prepare-boundTerms--autonomous` · **Agent:** guided · **Patterns:** CP-11, CP-1, CP-12, CP-7

Holder: the coordinator's native-transport request thread during PREPARE (ANTLR token buffer, the parsed and prepared statement, then the jamm measureDeep walk of it). Why nothing stops it: the 65535-marker check runs only after parseAndPrepare has parsed, prepared, validated and measured the whole statement (QueryProcessor.java:754 -> 436-471, measurePstmnt :469/:947-949; check at :757-759). So a query with far more than 65535 markers is built in full before it is rejected. The only bound on its size is the native message or frame size (default 16 MiB = min(max_mutation_size, heap/10, heap/40)). The in-flight limits count wire bytes (heap/10 node-wide), not the parsed size. Rough size at defaults: a 16 MiB 'IN (?,?,...)' string holds about 8M markers. Stage 4 measured 43 B per marker in the prepared statement, so about 350 MB, plus a token buffer of about 16M CommonTokens (about 0.5-1 GB, estimate) and measureDeep's visited set. That is on the order of 1 GB per request, against 16 MiB counted (about 50x), and up to 128 native threads can do it at once. A handful of concurrent requests exhausts an 8 GiB heap.

**Where:** src/java/org/apache/cassandra/cql3/QueryProcessor.java:754-759 (parseAndPrepare :441-471, measurePstmnt :947-949); src/java/org/apache/cassandra/cql3/CQLFragmentParser.java:71

## OC-286

**Case file:** `max-unsigned-short-prepare-boundTerms--autonomous` · **Agent:** guided · **Patterns:** CP-14, CP-6

Holder: the native protocol v5 large-message path on the coordinator (CQLMessageHandler.LargeMessage). A prepare of a 65535-marker statement is about 200 KB, above the 128 KiB v5 frame payload, so it goes through the large-message path. Stage 4 here avoided v5 because 'a large request on v5 leaves unreturned direct buffers'. In the networking_cache_size stage-4 run, 64 one-MB v5 requests left +58.7 MB of BufferPool overflow and 5.4 MB of pooled slots unreturned. Why nothing stops it: the frame stashes are never released after assembleFrame/processRequest, and only MaxDirectMemorySize bounds the leaked direct memory. Rough size: about 0.9 B leaked per request byte, so every large prepare or execute (about 200 KB here) leaks about its own size of direct memory. A driver that re-prepares (for example after cache evictions, which stage 4 saw at every cache size) grows direct memory without bound.

**Where:** src/java/org/apache/cassandra/transport/CQLMessageHandler.java:749-840 (assembleFrame :762-770, onComplete :823-836)

## OC-287

**Case file:** `max-unsigned-short-validateKey-keyRemaining--autonomous` · **Agent:** guided · **Patterns:** CP-9, CP-11, CP-1

Holder: the BIG-format sstable index summaries, in native memory via Memory/MemoryUtil.allocate (Unsafe), outside both -Xmx and MaxDirectMemorySize. Each summary entry stores the full partition key. A new sstable is written at full sampling (min_index_interval 128). The 5%-of-heap index_summary_capacity is enforced only by the IndexSummaryManager redistribution every 60 min, and the yaml calls it 'best-effort'. Why nothing stops it: this check admits partition keys up to 65535 B, the summary charges about key/128 per partition, and nothing caps the total between resamplings. Even fully downsampled (max_index_interval 2048) the summary stays proportional to the key bytes. Rough size: with 64 KiB keys, about 512 B of native memory per partition on disk, or about 5 GB per 10M partitions (655 GB of keys). Fully downsampled it is still about 32 B per partition (about 320 MB). That is far above the 5%-of-heap target, sits outside the JVM limits, and counts against the container. Flushes and compactions keep adding full-sampling summaries until the next resample.

**Where:** src/java/org/apache/cassandra/io/sstable/indexsummary/IndexSummaryBuilder.java:100-127 (entries sized by key, :137-139); src/java/org/apache/cassandra/io/sstable/format/big/BigTableWriter.java:255; src/java/org/apache/cassandra/io/util/Memory.java:60-69; src/java/org/apache/cassandra/config/DatabaseDescriptor.java:867-869; conf/cassandra.yaml:931-947

## OC-288

**Case file:** `batch_size_warn_threshold-verifyBatchSize-size--autonomous` · **Agent:** guided · **Patterns:** CP-1

Holder: the coordinator's batch mutations, their per-replica messages and, for LOGGED batches, the batchlog copy. Why nothing stops it: the batch size checks count IMutation.dataSize, which is the sum of row dataSize (clustering, liveness, cells) only. It leaves out partition-key bytes and all object overhead (PartitionUpdate.java:346-349, BTreeRow.java:522-529). Partition keys of up to 65535 B (validateKey case) are therefore invisible to batch_size_warn and batch_size_fail. Rough size at defaults: a 16 MiB request carrying about 250 partitions with 64 KiB keys and tiny rows counts a few KB, below even the 5 KiB warn value, yet carries about 16 MiB of key bytes. Each key is copied into its Mutation, into each of RF outbound messages, and into the batchlog blob for LOGGED batches, so about 4x16 MiB per request. Per request this is bounded only by the native in-flight wire limit (heap/10). Same mechanism applies to the unlogged_batch_across_partitions case.

**Where:** src/java/org/apache/cassandra/db/IMutation.java:63-72; src/java/org/apache/cassandra/db/partitions/PartitionUpdate.java:346-349; src/java/org/apache/cassandra/cql3/statements/BatchStatement.java:331-365

## OC-289

**Case file:** `batch_size_warn_threshold-verifyBatchSize-size--autonomous` · **Agent:** guided · **Patterns:** CP-11, CP-1, CP-12

Holder: the coordinator heap holding every built mutation of a batch request. Why nothing stops it: getMutations builds the whole batch (BTree rows, cells, keys) before verifyBatchSize runs (BatchStatement.java:428 then :439), so the check cannot stop the allocation, only reject afterwards. The node-wide bound is native_transport_max_request_data_in_flight (heap/10), which counts request wire bytes, while the built mutations hold several times that for small cells. LOGGED batches add a serialized batchlog copy (StorageProxy.java:1294, BatchlogManager.java:139-142). If batch_size_warn_threshold is set above fail, the fail check is skipped entirely (stage 4: 200/200 over-fail batches accepted), so a full 16 MiB batch is applied. Rough size: heap/10 of wire bytes (800 MB at 8 GiB) expands to a multiple on heap. At the B6-style tiny-cell ratio (about 15-20x) that exceeds the heap. Each request is held until its replicas answer or the write timeout fires.

**Where:** src/java/org/apache/cassandra/cql3/statements/BatchStatement.java:428-446 (verifyBatchSize :331-365); src/java/org/apache/cassandra/service/StorageProxy.java:1286-1301

## OC-290

**Case file:** `unlogged_batch_across_partitions_warn_threshold-verifyBatchType-keySet--autonomous` · **Agent:** guided · **Patterns:** CP-2, CP-1, CP-4

Holder: coordinator write fan-out of one unlogged multi-partition batch: one Mutation, write response handler and RF outbound messages per partition (StorageProxy.mutate loop :889-894). These are held until every replica acks or write_request_timeout (2 s) expires. Why nothing stops it: the partition-count threshold (default 10) only warns (BatchStatement.java:388-395). The only rejecting check is batch_size_fail (50 KiB) on dataSize, which excludes partition keys and per-partition overhead. The in-flight limit counts request wire bytes. Rough size at defaults: tiny rows (about 15-20 B of dataSize each) let about 2,500-3,000 partitions through under 50 KiB. Each partition costs roughly 1-3 KB of coordinator heap (Mutation, PartitionUpdate, DecoratedKey, handler, RF=3 messages), so about 5-10 MB per 100 KB request (about 50-100x the counted bytes). With 128 native threads, or more under async dispatch, and a slow replica keeping each alive for the 2 s timeout, that reaches several GB. Partition keys of up to 64 KiB add bytes that no batch check counts (same mechanism as the batch_size_warn case).

**Where:** src/java/org/apache/cassandra/cql3/statements/BatchStatement.java:369-395, :434-446; src/java/org/apache/cassandra/service/StorageProxy.java:878-894; src/java/org/apache/cassandra/db/partitions/PartitionUpdate.java:346-349

## OC-291

**Case file:** `max-unsigned-short-ClusteringPrefix-validate-accessor-size--autonomous` · **Agent:** guided · **Patterns:** CP-14, CP-10, CP-5

Holder: a memtable whose flush failed. Stage 4 found two writes that skip ClusteringPrefix.validate(): a slice DELETE (ModificationStatement.java:762-787, no clustering.validate() on slice bounds) and a conditional write (:573). Either accepts a clustering bound over 65535 B, and the later flush fails in StatsMetadata serialization (ByteBufferUtil.writeWithShortLength assert); the node stays up. Why nothing stops it: on a flush failure, Flush.run only records flushFailure (ColumnFamilyStore.java:1258-1264). replaceFlushed/reclaim (:1378-1379) are skipped, so the memtable stays marked flushing and its pool bytes are never released. Its commit-log segments are not discarded (:1149-1153), and on restart replay re-inserts the bad bound and fails again. Rough size at defaults: each failed flush pins about memtable_cleanup_threshold of the pool, about 1/3 of heap/4 (about 680 MB at 8 GiB). One bad delete per memtable pins the whole pool after about 3 flushes. All writes then block in the allocator, MutationStage threads block, and incoming mutations queue without a bound (JIRA 12689 shape).

**Where:** src/java/org/apache/cassandra/db/ColumnFamilyStore.java:1255-1268, :1314-1325, :1378-1379; src/java/org/apache/cassandra/cql3/statements/ModificationStatement.java:762-787, :573

## OC-292

**Case file:** `max-unsigned-short-validate-sum--autonomous` · **Agent:** guided · **Patterns:** CP-14, CP-10, CP-5

Same mechanism as the ClusteringPrefix-validate-accessor-size stem; stage 4 for this case saw it too. Holder: a memtable whose flush failed. A conditional write (ModificationStatement.java:573) or a slice delete (:762-787) bypasses this sum check, and the flush fails in StatsMetadata writeWithShortLength. Why nothing stops it: Flush.run catches the failure and only sets flushFailure (ColumnFamilyStore.java:1258-1264). The memtable is never replaced or reclaimed (:1378-1379), so its memtable-pool share stays owned, its commit-log segments stay dirty, and replay at restart reproduces the failure. Rough size: about 1/3 of heap/4 pinned per failed flush. After about 3 the pool is exhausted, writes block and MutationStage queues grow without a bound.

**Where:** src/java/org/apache/cassandra/db/ColumnFamilyStore.java:1255-1268, :1378-1379; src/java/org/apache/cassandra/cql3/statements/ModificationStatement.java:573, :762-787

## OC-293

**Case file:** `rows_per_partition-isFilterFullyCoveredBy-rowsPerPartitionToCache--autonomous` · **Agent:** guided · **Patterns:** CP-12, CP-10, CP-2

Holder: the read thread building a row-cache entry on heap (CachedBTreePartition.create). Why nothing stops it: rowsCounted counts only live rows (SinglePartitionReadCommand.java:594-598). With 'ALL', or on a table with no clustering columns, the whole partition is read. This full-partition read (:569) is materialized before executeLocally's withMetricsRecording wraps the result, so neither tombstone_failure_threshold nor the read-size thresholds see it. Every tombstoned or expired row before N live rows is stored too (stage 4: 60 rows stored for N=10). OHC is offered the entry only after it is fully built (throwOOME(true), OHCProvider.java:43). Rough size: off at defaults (row_cache_size 0, rows_per_partition 0). Once enabled, one wide or tombstone-heavy partition is built whole per read, unbounded by any count, times concurrent_reads (32).

**Where:** src/java/org/apache/cassandra/db/SinglePartitionReadCommand.java:547-608

## OC-294

**Case file:** `rows_per_partition-isFilterFullyCoveredBy-rowsPerPartitionToCache--autonomous` · **Agent:** guided · **Patterns:** CP-9, CP-1

Holder: OHC row-cache memory, native via Unsafe/malloc, outside -Xmx and MaxDirectMemorySize. This is a measured gap: stage 4 saw RssAnon rise 0.3-0.7 GB more than the cache's reported Size (n10, n100 and c32 arms with a 256 MiB or 32 MiB cache). Why nothing stops it: row_cache_size charges each entry's serialized size, while the process also holds allocator overhead, fragmentation and transient heap/read buffers that no limit counts. Rough size: off at defaults. When enabled, about 1-3x the configured cache on top of it in RSS, which counts against the container.

**Where:** src/java/org/apache/cassandra/cache/OHCProvider.java:38-46; src/java/org/apache/cassandra/db/partitions/CachedBTreePartition.java:199-211

## OC-295

**Case file:** `tombstone-failure-threshold-withMetricsRecording-failureThreshold--autonomous` · **Agent:** guided · **Patterns:** CP-2, CP-1, CP-7, CP-8, CP-12

Holder: the replica's per-read heap DataOutputBuffer response (ReadResponse.LocalDataResponse.build) plus the scan's allocation. Why nothing stops it: tombstone_failure_threshold counts tombstones (100,000), not bytes, and each range-tombstone marker carries clustering bounds of up to 65535 B. The byte guard on the same reads (local_read_size_*) ships off (read_thresholds_enabled=false, Config.java:526-530). The budget is per read command, with up to concurrent_reads=32 at once and no node-wide total. Rough size: stage 4 measured a 145 MiB buffer for 100,000 markers with 1 KB clusterings at the default threshold, and about 600 B of scan allocation per counted tombstone. With multi-KB to 64 KiB clusterings one read reaches GBs. 32 concurrent reads at 145 MiB are already about 4.6 GiB, beyond an 8 GiB heap's free share. Stage 4 saw eight clients hold about 1.3 GB of a 2 GiB heap.

**Where:** src/java/org/apache/cassandra/db/ReadCommand.java:529-537, :582-601; src/java/org/apache/cassandra/db/ReadResponse.java:197-203; src/java/org/apache/cassandra/config/Config.java:179, :526-530, :535

## OC-296

**Case file:** `commitlog-segment-size-addAdditionalInformationIfPossible-segmentSize--autonomous` · **Agent:** guided · **Patterns:** CP-16, CP-8, CP-14

Holder: commit-log segment buffers (direct or heap per the compressor). In compressed, encrypted and direct-IO modes each active segment holds a buffer of exactly commitlog_segment_size (SimpleCachedBufferPool.createBuffer, CommitLogSegment.java:192-194). Up to commitlog_max_compression_buffers_in_pool=3 more are kept pooled, and atLimit only slows segment creation. Thread-local scratch buffers are also sized from the segment: the compressed sync buffer (CompressedSegment.java:67-68) and EncryptedSegment's buffer of the full segment size (EncryptedSegment.java:112). They are kept and never shrunk. Why nothing stops it: commitlog_segment_size is checked only for >0 and <2048 MiB (DatabaseDescriptor.java:891-896), and nothing ties these buffers to the direct or heap budget. Rough size: about 4-5 x 32 MiB = 150 MiB at defaults in those modes; the default 'legacy' uncompressed mode uses mmap and is unaffected. At an accepted 1-2 GiB segment size that becomes 5-10 GiB of direct memory. The derived max_mutation_size (segment/2, :898-899) rises with it.

**Where:** src/java/org/apache/cassandra/io/util/SimpleCachedBufferPool.java:58-81; src/java/org/apache/cassandra/db/commitlog/CompressedSegment.java:67-68, :114-120; src/java/org/apache/cassandra/db/commitlog/EncryptedSegment.java:112; src/java/org/apache/cassandra/config/DatabaseDescriptor.java:891-899

## OC-297

**Case file:** `cql-row-limit-hasEnoughLiveData-rowLimit--autonomous` · **Agent:** autonomous · **Patterns:** —

Holder: the replica's serialized read response and the coordinator's ResultSet for one page or one unpaged query. The CQL LIMIT and the page size (rowLimit) count rows, not bytes. On the coordinator-local read, the whole page is serialized into one on-heap DataOutputBuffer (LocalDataResponse.build), which grows by doubling up to MAX_ARRAY_SIZE (about 2 GiB). The coordinator then builds a ResultSet holding every output row. What should stop it and does not: at defaults there is no byte bound. read_thresholds_enabled=false and the local/coordinator read-size thresholds are null. The page-size guardrail is -1 and counts rows anyway. With paging off (pageSize<=0, or LIMIT <= pageSize) the query skips the pager entirely. Row size is only loosely limited: max_value_size is 256 MiB, max_mutation_size is 16 MiB per write, and a row can be built from many writes. Rough size at defaults: a driver page of 5000 rows of 1 MiB each is about 4.9 GiB per request. That is capped at about 2 GiB per buffer, plus about 1 GiB of transient copy while the buffer doubles. concurrent_reads=32 such reads exceed the default heap (half of RAM, at most 8 GiB in common setups). Stage 4 saw RssAnon rise with result size: 177-222 MiB at L=100000/none in both the cache-on and cache-off arms.

**Where:** src/java/org/apache/cassandra/db/ReadResponse.java:197-201; src/java/org/apache/cassandra/db/ReadCommand.java:374,383; src/java/org/apache/cassandra/io/util/DataOutputBuffer.java:118,149-153; src/java/org/apache/cassandra/cql3/statements/SelectStatement.java:338-340; src/java/org/apache/cassandra/cql3/selection/ResultSetBuilder.java:135,162; src/java/org/apache/cassandra/config/Config.java:526-530,873-874; src/java/org/apache/cassandra/config/DatabaseDescriptor.java:898-899

## OC-298

**Case file:** `group-limit-isdone-groupcounted--autonomous` · **Agent:** autonomous · **Patterns:** —

Holder: the coordinator's ResultSet for a GROUP BY query run with client paging off. groupLimit is the user LIMIT, which defaults to NO_LIMIT. With pageSize<=0, GroupByPartitionIterator turns the top-level page size into NO_LIMIT (handlePagingOff). isDone(counted == NO_LIMIT) never fires, so the loop keeps fetching internal sub-pages until the table or range is exhausted. Every group's output row is added to one ResultSet, and processResults then encodes all of it as one response. What should stop it and does not: the internal sub-paging that the code says is there 'to avoid OOM' (rowLimit = DEFAULT_PAGE_SIZE 10000) bounds only each replica sub-page. Nothing bounds the number of groups the coordinator accumulates, and the page-size guardrail is disabled (-1) and ignores pageSize<=0. Rough size at defaults: SELECT pk, ck, count(*) ... GROUP BY pk, ck over 50 M rows, with paging off (cqlsh PAGING OFF or driver fetch size 0), gives 50 M result rows. At about 100-200 B of heap each (ArrayList plus ByteBuffers), that is 5-10 GB on the coordinator, more than the default heap. This is before the encoded response is built.

**Where:** src/java/org/apache/cassandra/service/pager/AggregationQueryPager.java:186,193-198,229-246; src/java/org/apache/cassandra/cql3/statements/SelectStatement.java:896-902,546-555,561-570; src/java/org/apache/cassandra/cql3/selection/ResultSetBuilder.java:135,162; src/java/org/apache/cassandra/db/filter/DataLimits.java:1011-1014

## OC-299

**Case file:** `group-per-partition-limit-isdoneforpartition-groupinCurrentPartition--autonomous` · **Agent:** autonomous · **Patterns:** —

Holder: each GROUP BY internal sub-page, serialized whole on the replica into one heap DataOutputBuffer (LocalDataResponse) and then deserialized on the coordinator. groupPerPartitionLimit defaults to NO_LIMIT. The only bound on a sub-page is rowLimit: the client page size, or DEFAULT_PAGE_SIZE = 10000 rows when paging is off. That is a row count with no byte bound. read_thresholds_enabled=false by default, and a row can be large (max_value_size 256 MiB; max_mutation_size 16 MiB per write). Rough size at defaults: GROUP BY pk, ck selecting a 1 MiB blob column (for example max(v) or the first-row value) with paging off reads 10000 rows of about 1 MiB per sub-page, which hits the 2 GiB buffer cap. That means about 2-3 GiB of transient heap per read (doubling copies), times concurrent_reads=32. Stage 4 showed peak heap following page content: 792 MB at P=300000 with 100 B values, about 2.6 KB per row.

**Where:** src/java/org/apache/cassandra/cql3/statements/SelectStatement.java:896-914; src/java/org/apache/cassandra/db/filter/DataLimits.java:983-988,1005-1008; src/java/org/apache/cassandra/db/ReadResponse.java:197-201; src/java/org/apache/cassandra/io/util/DataOutputBuffer.java:118,149-153; src/java/org/apache/cassandra/config/Config.java:526-530

## OC-300

**Case file:** `max-compacting-l0-getSTCSInL0CompactionCandidate-l0SstableCount--autonomous` · **Agent:** autonomous · **Patterns:** —

Holder: direct (off-heap) read-ahead buffers that range reads open, one per L0 sstable. The 32 is only a trigger. Flush into L0 is never blocked (comment at LeveledManifest.java:225-232), so L0 grows with write rate minus compaction speed: stage 4 reached 211 L0 sstables. Every L0 sstable spans the token range, so every range read (PartitionRangeReadCommand.queryStorage) opens a scanner on each of them at once. Range reads do not use LeveledScanner. Each SSTableScanner constructor calls openDataReaderForScan. For the default LZ4-compressed table with default disk_access_mode mmap_index_only, that eagerly allocates a 256 KiB direct ByteBuffer (compressed_read_ahead_buffer_size, LZ4 preferredBufferType OFF_HEAP, ByteBuffer.allocateDirect), plus a 16 KiB chunk buffer. Nothing caps the number of scanners per read or the total read-ahead memory. Rough size at defaults: with the L0 backlog from the code's own comment (988 sstables), about 988 x 272 KiB, roughly 262 MiB of direct memory per range read. With concurrent_reads=32 that is about 8.4 GiB, above the default MaxDirectMemorySize of 1/4 of RAM (8 GiB on a 32 GiB node; cassandra-env.sh). The result is OutOfMemoryError: Direct buffer memory.

**Where:** src/java/org/apache/cassandra/db/compaction/LeveledManifest.java:62,213-232,304-316; src/java/org/apache/cassandra/db/PartitionRangeReadCommand.java:315,331-341; src/java/org/apache/cassandra/io/sstable/format/SSTableScanner.java:78; src/java/org/apache/cassandra/io/util/CompressedChunkReader.java:93-95,162-166,236-244; src/java/org/apache/cassandra/io/util/ThreadLocalReadAheadBuffer.java (getBlock: bufferType.allocate); src/java/org/apache/cassandra/io/compress/BufferType.java:33-35; src/java/org/apache/cassandra/io/compress/LZ4Compressor.java:240-243; src/java/org/apache/cassandra/config/Config.java:122,341; conf/cassandra-env.sh:62-66

## OC-301

**Case file:** `rows-per-partition-hasEnoughLiveData-rowLimit--autonomous` · **Agent:** autonomous · **Patterns:** —

Holder: the on-heap CachedBTreePartition built while populating the row cache. rows_per_partition counts only live rows (rowsCounted++ only when row.hasLiveData). Every row tombstone, range-tombstone marker and expired row before the N-th live row is pulled into ImmutableBTreePartition.build on heap and then stored in OHC. What should stop it and does not: the materialization runs inside queryStorage, before ReadCommand wraps the iterator with query-size tracking and the tombstone_failure_threshold (100000) metrics. The tombstone check therefore fires, at best, after the memory is already held. Prerequisite: the row cache must be on (row_cache_size > 0 and rows_per_partition other than NONE); the shipped row_cache_size is 0. Rough size: a partition with 1 M deleted rows before N=100 live rows means about 1 M x 100+ B, roughly 100+ MB of heap per miss. Writes evict the cached partition (no partial invalidation), so each read after a write repeats the work. Stage 4 TOMB variant: 55 rows cached for 5 live.

**Where:** src/java/org/apache/cassandra/db/SinglePartitionReadCommand.java:566-604; src/java/org/apache/cassandra/db/partitions/CachedBTreePartition.java:82-115; src/java/org/apache/cassandra/db/ReadCommand.java:452-461; src/java/org/apache/cassandra/db/ColumnFamilyStore.java:3259-3265; src/java/org/apache/cassandra/config/Config.java:474

## OC-302

**Case file:** `rows-per-partition-hasEnoughLiveData-rowLimit--autonomous` · **Agent:** autonomous · **Patterns:** —

Holder: the whole partition materialized on heap on a row-cache miss when full partitions are cached. That happens with rows_per_partition='ALL' on a clustered table, or with any positive value on a table without clustering columns (cacheFullPartitions). The code reads the full partition (fullPartitionRead) and builds it entirely in CachedBTreePartition.create before returning anything to the query. This happens even for a LIMIT 1 query. Nothing bounds the bytes: neither the query LIMIT, nor row_cache_size (which caps only what OHC keeps, after the heap copy exists), nor the tombstone and read-size checks, which wrap the iterator only after queryStorage. A partition too large for an OHC segment is never kept, and any write evicts the entry, so each such miss repeats the full materialization. Prerequisite: the row cache must be on (non-default row_cache_size). Rough size: a 500 MB partition is about 1-1.5 GB of on-heap Row/Cell objects per miss. A few concurrent misses on different large partitions (concurrent_reads=32) exceed an 8 GiB heap. Stage 4: ALL stored 22.5 KB per 200-row partition, which scales linearly with partition size.

**Where:** src/java/org/apache/cassandra/db/SinglePartitionReadCommand.java:547-549,569,604-618; src/java/org/apache/cassandra/db/partitions/CachedBTreePartition.java:82-84; src/java/org/apache/cassandra/cache/OHCProvider.java:40-43; src/java/org/apache/cassandra/db/ReadCommand.java:452-461

## OC-303

**Case file:** `max-compacting-l0-getSTCSInL0CompactionCandidate-l0SstableCount--autonomous` · **Agent:** guided · **Patterns:** CP-7, CP-6, CP-8

Per-sstable 256 KiB read-ahead buffer for every open scanner, multiplied by an sstable count that nothing caps. Holder: ThreadLocalReadAheadBuffer.Block.buffer, a plain ByteBuffer.allocateDirect of compressed_read_ahead_buffer_size (default 256 KiB, Config.java:341; LZ4 prefers OFF_HEAP, so it is direct). It is allocated eagerly when a scanner opens (SSTableScanner ctor -> openDataReaderForScan -> CompressedChunkReader.forScan -> allocateResources), and each scanner also takes one 16 KiB chunk from the chunk-cache BufferPool. Why nothing stops it: (1) a partition-range read opens one scanner on every sstable that intersects the range, all at once (PartitionRangeReadCommand.java:331-340). LCS compaction opens all L0 inputs at once, STCS opens up to max_threshold, and a major compaction opens every sstable. (2) The number of sstables has no cap: stage 4 measured 211 L0 sstables (6.5x MAX_COMPACTING_L0) with nothing refused, raising min_threshold lets more sstables pile up, and max_threshold accepts any positive value. (3) The buffer is outside the file_cache_size BufferPool budget, so the only limit is MaxDirectMemorySize, which this memory shares with the chunk-cache pool (512 MiB) and the networking pool (128 MiB). The pinned cassandra-env.sh sets that limit to min(RAM/4, 15.5 GiB), so 8 GiB on a 32 GiB host. Size at defaults: about 272 KiB per intersecting sstable per in-flight range-read page. 211 L0 sstables = 56 MiB per page, and 32 concurrent_reads = 1.8 GiB. A 1 TB LCS table (about 6,400 sstables of 160 MiB) = 1.7 GiB per full-range page, so about 5 concurrent full scans pass an 8 GiB direct limit. If a scanner is opened on one thread and closed on another, the opener's 256 KiB stays referenced in its thread-local map. Also relevant to compaction-min-threshold-mostInterestingBucket-minThreshold--autonomous and max-compaction-threshold-getCandidatesFor-candidatesSize--autonomous (count of simultaneously open scanners).

**Where:** src/java/org/apache/cassandra/io/util/ThreadLocalReadAheadBuffer.java:84; io/util/CompressedChunkReader.java:236-245; io/sstable/format/SSTableScanner.java:78; db/PartitionRangeReadCommand.java:331-340; config/Config.java:341; db/compaction/LeveledManifest.java:306

## OC-304

**Case file:** `max-compacting-l0-getSTCSInL0CompactionCandidate-l0SstableCount--autonomous` · **Agent:** guided · **Patterns:** CP-14, CP-7

Thread-local map entries kept for every sstable a thread ever read. Holder: the FastThreadLocal<Map<String,Block>> blockMap in ThreadLocalReadAheadBuffer. Every readChunk on any thread calls scanReader.allocated() -> hasBuffer() -> block() -> computeIfAbsent(filePath). Plain single-partition reads do this too, so each ReadStage, compaction and validation thread gets one entry per sstable it touches. When a scanner closes, clear(true) only nulls the buffer and keeps the entry. The only removal is close(), which runs when the sstable's tidy runs on ScheduledExecutors.nonPeriodicTasks. It therefore removes the entry only from that thread's map, never from the threads that read the file. Nothing trims the maps when compaction deletes the files, so they grow with the number of sstables ever created × threads until restart. Size: about 70 B per (thread, sstable) (HashMap.Node + Block + table slot), plus about 150 B for the path String it pins. Example: 64 pooled read and compaction threads × 50k sstables a day (LCS churn on a busy node) ≈ 220 MB of heap a day. At 5k sstables a day it is about 0.7 GB a month. Faster with the uncapped L0 churn this case shows. Also relevant to max-compaction-threshold-getCandidatesFor-candidatesSize--autonomous (compaction threads scan every input).

**Where:** src/java/org/apache/cassandra/io/util/ThreadLocalReadAheadBuffer.java:92,132-157; io/util/CompressedChunkReader.java:268; io/sstable/format/SSTableReader.java:1540

## OC-305

**Case file:** `cql-row-limit-hasEnoughLiveData-rowLimit--autonomous` · **Agent:** guided · **Patterns:** CP-12, CP-2, CP-8

Read results are bounded by a row count from the client, or by nothing, and never by bytes at defaults. Holder: the coordinator's processResults ResultSet, plus the replica's serialized response and the encoded native-protocol frame, which are copies of the same rows (at least 3). Why nothing stops it: (1) A non-aggregate SELECT with paging off (or LIMIT <= page size) and no LIMIT runs unpaged (SelectStatement.java:338-341, rowLimit = NO_LIMIT), so the whole result is built at once. (2) GROUP BY and aggregates are 'paged internally to avoid OOM', but the internal page is the client page size in rows, or 10000 when paging is off (SelectStatement.java:899-902). Row width is bounded only by the mutation size (16 MiB) or max_value_size. (3) The byte limits that exist all ship off: read_thresholds_enabled false, coordinator_read_size_*/local_read_size_* unset, page_size_warn/fail_threshold -1 (cassandra.yaml:2015-2026, 2089-2090). Size at defaults: about 3x the result bytes on the coordinator heap per query. An unpaged SELECT over a 1 GiB partition or table ≈ 3 GiB. A 10000-row internal GROUP BY page of 100 KB rows ≈ 1 GB per page × concurrent queries. Also relevant to group-limit-isdone-groupcounted--autonomous (the GROUP BY internal page, rowLimit = page size).

**Where:** src/java/org/apache/cassandra/cql3/statements/SelectStatement.java:338-341,417-430,899-902; db/filter/DataLimits.java:99,349; conf/cassandra.yaml:2015-2026,2089-2090

## OC-306

**Case file:** `rows-per-partition-hasEnoughLiveData-rowLimit--autonomous` · **Agent:** guided · **Patterns:** CP-2, CP-12, CP-10, CP-11

Filling the row cache materializes on the heap an amount that only a count of live rows bounds, and the tombstone limit does not apply on that path. Holder: CachedBTreePartition.create(toCacheIterator), built eagerly inside getThroughCache on a cache miss. The rows_per_partition cap counts only live rows (rowsCounted++ only when hasLiveData). Every tombstone, range-tombstone marker and expired row before the N-th live row is read into the heap BTree. With rows_per_partition 'ALL' (or any positive value on a table with no clustering columns) the whole partition is read and built, whatever the query's LIMIT. Why nothing stops it: queryStorage (which runs getThroughCache) is called before withMetricsRecording wraps the iterator (ReadCommand.java:452 vs :461). So tombstone_failure_threshold (100000) and the read-size thresholds see only what flows out afterwards, after the allocation. The OHC capacity (row_cache_size) is checked only at rowCache.replace, after the partition has been built on the heap. An entry larger than the capacity is dropped and rebuilt on every miss. Concurrent misses on different keys each build their own copy, up to concurrent_reads 32. Size: partition bytes × about 2-5x for the on-heap BTree and cells, plus the serialized copy. Examples: a 1 GiB partition read with LIMIT 1 under 'ALL' ≈ 2-5 GiB per miss. With rows_per_partition 100, 1 M row tombstones before the first live rows ≈ 100+ MB per read, × 32 ≈ 3 GB. Needs row_cache_size > 0 (shipped default 0 MiB, which disables the row cache) and the table option caching.rows_per_partition, which this case covers.

**Where:** src/java/org/apache/cassandra/db/SinglePartitionReadCommand.java:547-549,566-603; db/ReadCommand.java:452-461; db/partitions/CachedBTreePartition.java:65-82; cache/OHCProvider.java:40-43

## OC-307

**Case file:** `cql-row-limit-incrementRowCount-rowsCounted--autonomous` · **Agent:** autonomous · **Patterns:** —

A LIMIT-N read, or one N-row page, is held on the heap in full, twice. The replica serializes every row into one heap DataOutputBuffer, which grows 1.5-2x at a time. The coordinator then builds the whole ResultSet from it, and both copies are live together. Nothing bounds the bytes: rowLimit counts live rows, not bytes; the default is NO_LIMIT; and the byte guardrails are off by default (read_thresholds_enabled false, coordinator/local_read_size_* unset, page_size_* -1). A single write can carry about 16 MiB (max_mutation_size = commitlog_segment_size/2) and a row can grow over many writes. Rough size: 1000 rows of 10 MiB come to about 10 GB of payload per copy, about 20 GB held. That is more than the largest default heap, min(1/2 RAM, 15.5 GiB). Stage 4 measured 2.0-2.4 x N x W held per read.

**Where:** src/java/org/apache/cassandra/db/filter/DataLimits.java:509-510; src/java/org/apache/cassandra/db/ReadResponse.java:197-201; src/java/org/apache/cassandra/io/util/DataOutputBuffer.java:158-171; src/java/org/apache/cassandra/cql3/statements/SelectStatement.java:1014; conf/cassandra.yaml:2015-2026,2089-2090; src/java/org/apache/cassandra/config/DatabaseDescriptor.java:898-899; conf/cassandra-env.sh:51-68

## OC-308

**Case file:** `cql-row-limit-incrementRowCount-rowsCounted--autonomous` · **Agent:** autonomous · **Patterns:** —

With an IN on the partition key plus ORDER BY (post-query ordering), the row limit is turned off: cqlRowLimit stays NO_LIMIT and the user LIMIT is applied only after every row of every listed partition is in the ResultSet. Paging is refused for this query shape, so the client has to run it unpaged. Neither partition size nor IN count is capped at defaults (partition_keys_in_select_* is -1). Rough size: `SELECT * ... WHERE pk IN (a,b) ORDER BY ck LIMIT 10` over two 4 GB partitions holds about 8 GB in the replica buffers plus about 8 GB in the ResultSet, even though only 10 rows are returned.

**Where:** src/java/org/apache/cassandra/cql3/statements/SelectStatement.java:888-896,537-539,1014-1019,1156-1160; conf/cassandra.yaml:2098-2099

## OC-309

**Case file:** `default_page_size-cqlgroupbylimits_onclose-rowlimit--autonomous` · **Agent:** autonomous · **Patterns:** —

A plain aggregate with no GROUP BY (AGGREGATE_EVERYTHING, e.g. `SELECT count(v) FROM t WHERE pk=?`) run with paging off is not paged internally, despite the 'always paged internally to avoid OOM' comment. getDataLimits gives it cqlLimits(NO_LIMIT). AggregationPartitionIterator turns a page size of 0 or less into NO_LIMIT and keeps that sub-page size, so the whole partition (or token range) is read in one command. The replica serializes all of it into one heap DataOutputBuffer. Rough size: about the partition's data, up to 2x for buffer growth (e.g. a 4 GB partition holds 4-8 GB). Partition size has no default cap. Stage 4 saw a 2 GB partition kill a 512 MB node in 1.5 s.

**Where:** src/java/org/apache/cassandra/cql3/statements/SelectStatement.java:888-920,338-356; src/java/org/apache/cassandra/service/pager/AggregationQueryPager.java:193-197,406-443; src/java/org/apache/cassandra/service/pager/SinglePartitionPager.java:63-76; src/java/org/apache/cassandra/db/ReadResponse.java:197-201

## OC-310

**Case file:** `default_page_size-cqlgroupbylimits_onclose-rowlimit--autonomous` · **Agent:** autonomous · **Patterns:** —

DEFAULT_PAGE_SIZE caps each internal GROUP BY sub-read at 10000 rows, not bytes. Each sub-read is serialized in full into one replica buffer and then deserialized at the coordinator. Row width is bounded only by max_mutation_size (16 MiB per write at defaults), and no read-size guardrail is on by default. Rough size: 10000 rows x 1 MiB is about 10 GB per sub-read, plus up to 1.5-2x for buffer growth and the coordinator copy. That is more than the 15.5 GiB maximum default heap. Stage 4 saw +247 MB for 1 KiB rows on a 512 MB heap.

**Where:** src/java/org/apache/cassandra/cql3/statements/SelectStatement.java:114,901-902,908-914; src/java/org/apache/cassandra/db/filter/DataLimits.java:986-987; src/java/org/apache/cassandra/db/ReadResponse.java:197-201

## OC-311

**Case file:** `default_page_size-cqlgroupbylimits_onclose-rowlimit--autonomous` · **Agent:** autonomous · **Patterns:** —

An unpaged GROUP BY keeps every result group on the coordinator. GroupByPartitionIterator turns a page size of 0 or less into NO_LIMIT groups and keeps pulling 10000-row sub-pages until the data ends. ResultSetBuilder adds one output row per group, and the whole ResultSet is built before the reply. With GROUP BY on the full primary key, each row is its own group and non-aggregated selected columns are copied out. Rough size: the coordinator ResultSet is about the size of the scanned data (e.g. a 5 GB table or partition gives about 5 GB), even though reads are chunked.

**Where:** src/java/org/apache/cassandra/service/pager/AggregationQueryPager.java:193-197,224-251; src/java/org/apache/cassandra/cql3/selection/ResultSetBuilder.java:126-169; src/java/org/apache/cassandra/cql3/statements/SelectStatement.java:1003-1014

## OC-312

**Case file:** `group-by-limit-incrementGroupCount-groupLimit--autonomous` · **Agent:** autonomous · **Patterns:** —

groupLimit is NO_LIMIT when the query has no LIMIT. With paging off, the GROUP BY pager also turns the page size into NO_LIMIT groups, so the coordinator keeps one ResultSet row per group for the whole scan. Nothing counts these rows in bytes. With GROUP BY on the full primary key, every row is its own group and selected non-aggregate columns are copied, so the ResultSet grows to about the data scanned (e.g. a 5 GB table gives about 5 GB of heap), even though the read side is chunked into 10000-row sub-reads.

**Where:** src/java/org/apache/cassandra/db/filter/DataLimits.java:990-995; src/java/org/apache/cassandra/service/pager/AggregationQueryPager.java:193-197,224-251; src/java/org/apache/cassandra/cql3/selection/ResultSetBuilder.java:126-169; src/java/org/apache/cassandra/cql3/statements/SelectStatement.java:1014

## OC-313

**Case file:** `group-by-limit-incrementGroupCount-groupLimit--autonomous` · **Agent:** autonomous · **Patterns:** —

The group limit never stops a group in progress. Inside one group, the only stop is rowLimit (the page size, 10000 by default), which counts rows, not bytes. Each sub-read is serialized whole into one replica DataOutputBuffer. At defaults, rows up to the 16 MiB max_mutation_size and no read-size guardrail allow about 10000 x 1 MiB = 10 GB per sub-read (more with buffer growth and the coordinator copy), whatever LIMIT g is.

**Where:** src/java/org/apache/cassandra/db/filter/DataLimits.java:983-988; src/java/org/apache/cassandra/cql3/statements/SelectStatement.java:114,901-902; src/java/org/apache/cassandra/db/ReadResponse.java:197-201

## OC-314

**Case file:** `group-by-row-limit-incrementRowCount-rowsCounted--autonomous` · **Agent:** autonomous · **Patterns:** —

rowLimit is set straight from the client fetch size, with no upper bound by default (page_size_warn/fail_threshold -1, and superusers skip guardrails anyway). It is also the number of groups per page. One internal sub-read therefore materializes F rows x row width in one replica buffer plus the coordinator copy. Rough size: fetch 1,000,000 with 4 KiB rows is about 4 GB per copy; fetch 100,000 with 100 KiB rows is about 10 GB. Stage 4 saw fetch 100,000 x 4 KiB kill 512 MB nodes. Even the 10000 default with 1 MiB rows (allowed under the 16 MiB max_mutation_size) is about 10 GB.

**Where:** src/java/org/apache/cassandra/cql3/statements/SelectStatement.java:291-296,901-914,517; src/java/org/apache/cassandra/db/filter/DataLimits.java:986-987; src/java/org/apache/cassandra/db/ReadResponse.java:197-201; conf/cassandra.yaml:2089-2090

## OC-315

**Case file:** `group-by-row-limit-incrementRowCount-rowsCounted--autonomous` · **Agent:** autonomous · **Patterns:** —

With paging off, the top-level GROUP BY page is NO_LIMIT groups. Sub-reads are chunked at 10000 rows, but every group's output row stays in the coordinator ResultSet until the end. With GROUP BY on the full primary key, the ResultSet is about the size of the data scanned (e.g. 5 GB), with no row or byte cap at defaults.

**Where:** src/java/org/apache/cassandra/service/pager/AggregationQueryPager.java:193-197,224-251; src/java/org/apache/cassandra/cql3/selection/ResultSetBuilder.java:126-169; src/java/org/apache/cassandra/cql3/statements/SelectStatement.java:1014

## OC-316

**Case file:** `group-per-partition-limit-incrementGroupInCurrentPartitionCount-groupPerPartitionLimit--autonomous` · **Agent:** autonomous · **Patterns:** —

groupPerPartitionLimit defaults to NO_LIMIT, and under GROUP BY <partition key> the check at :1000 is never reached. With paging off, the GROUP BY pager then collects NO_LIMIT groups, so the coordinator holds one ResultSet row per group for the whole scan. With GROUP BY pk, ck plus selected columns, that is about the size of the scanned data (e.g. 5 GB of heap for a 5 GB table or partition), with no byte cap at defaults.

**Where:** src/java/org/apache/cassandra/db/filter/DataLimits.java:997-1001; src/java/org/apache/cassandra/service/pager/AggregationQueryPager.java:193-197,224-251; src/java/org/apache/cassandra/cql3/selection/ResultSetBuilder.java:126-169; src/java/org/apache/cassandra/cql3/statements/SelectStatement.java:1014

## OC-317

**Case file:** `group-per-partition-limit-incrementGroupInCurrentPartitionCount-groupPerPartitionLimit--autonomous` · **Agent:** autonomous · **Patterns:** —

A group that spans a whole partition is not capped by this limit. It is read in sub-reads of rowLimit rows (10000 by default, or the client fetch size, which is unbounded at defaults), and each sub-read is serialized whole into one replica buffer. Rough size: 10000 rows x 1 MiB (under the 16 MiB max_mutation_size) is about 10 GB per sub-read, plus the coordinator copy, with no read-size guardrail on.

**Where:** src/java/org/apache/cassandra/db/filter/DataLimits.java:983-988; src/java/org/apache/cassandra/cql3/statements/SelectStatement.java:114,901-914; src/java/org/apache/cassandra/db/ReadResponse.java:197-201

## OC-318

**Case file:** `per-partition-limit-incrementRowCount-rowsincurrentpartition--autonomous` · **Agent:** autonomous · **Patterns:** —

perPartitionLimit counts live rows per partition, not bytes, and defaults to NO_LIMIT. An unpaged read (or one page) is still materialized in full: once in the replica's single heap DataOutputBuffer (1.5-2x growth) and once in the coordinator ResultSet, both live at the same time. No byte guardrail is on at defaults. Rough size: PER PARTITION LIMIT 1000 over 10 partitions of 1 MiB rows is about 10 GB per copy, about 20 GB held, which is more than the 15.5 GiB maximum default heap.

**Where:** src/java/org/apache/cassandra/db/filter/DataLimits.java:509-512; src/java/org/apache/cassandra/db/ReadResponse.java:197-201; src/java/org/apache/cassandra/cql3/statements/SelectStatement.java:1014; conf/cassandra.yaml:2015-2026,2089-2090

## OC-319

**Case file:** `cql-row-limit-incrementRowCount-rowsCounted--autonomous` · **Agent:** guided · **Patterns:** CP-2, CP-12, CP-8, CP-6, CP-7

One LIMIT-N read or one N-row page has no byte bound at defaults. Holder: the replica serializes the whole page into one heap DataOutputBuffer, which grows by doubling with a copy, and the coordinator builds the full ResultSet with copied cell values while the replica buffer is still referenced, so both are live at once. Why nothing stops it: rowLimit counts live rows, not bytes, and every byte guard ships off: read_thresholds_enabled=false, local/coordinator_read_size_*=null, page_size_fail_threshold=-1. The JVM is the only stop. Several queries run at once (concurrent_reads 32 on replicas, native_transport_max_threads 128 on coordinators) and nothing caps their sum. Size: stage 4 measured 2.0-2.4 x N x W held (1241 MiB for 512 x 1 MiB rows) and about 4x the payload allocated. One 5000-row driver page of 1 MiB rows holds about 10-12 GiB, and LIMIT 1000 over about 10 MiB rows (each under the 16 MiB max_mutation_size) holds about 20 GB. Either exceeds the default heap of at most 15.5 GiB. The per-partition-limit stem (per-partition-limit-incrementRowCount-rowsincurrentpartition--autonomous) has the same exposure, because its counter only lowers this row count; file it once, naming both stems.

**Where:** src/java/org/apache/cassandra/db/filter/DataLimits.java:509-512; src/java/org/apache/cassandra/db/ReadResponse.java:196-201; src/java/org/apache/cassandra/cql3/statements/SelectStatement.java:1004-1014; src/java/org/apache/cassandra/config/Config.java:526-530,873-874

## OC-320

**Case file:** `cql-row-limit-incrementRowCount-rowsCounted--autonomous` · **Agent:** guided · **Patterns:** CP-10, CP-12, CP-6

Post-query ordering skips the user LIMIT. With IN on the partition key plus ORDER BY, getDataLimits leaves cqlRowLimit=NO_LIMIT, and paging is rejected for such queries, so every row of every listed partition is read, serialized and built into the ResultSet before the user's LIMIT trims the result. Holder: the replica response buffers and the coordinator ResultSet. Why nothing stops it: the LIMIT is applied only after everything is collected, paging cannot be used, partition_keys_in_select_* is -1 (off), and no read-size threshold is on. Size: the sum of the IN partitions' live data, so `... WHERE pk IN (k1..k100) ORDER BY ck LIMIT 10` over 100 MB partitions materializes about 10 GB (more with the 2x replica-plus-coordinator copy) to return 10 rows.

**Where:** src/java/org/apache/cassandra/cql3/statements/SelectStatement.java:889-896,537-538,1174; src/java/org/apache/cassandra/config/Config.java:875

## OC-321

**Case file:** `group-by-row-limit-incrementRowCount-rowsCounted--autonomous` · **Agent:** guided · **Patterns:** CP-2, CP-12, CP-8, CP-6, CP-7

GROUP BY internal sub-read sized in rows only. Holder: each internal sub-read of a GROUP BY is held whole, as one replica DataOutputBuffer and then a decode-and-merge on the coordinator. Its rowLimit is the client's page size, or DEFAULT_PAGE_SIZE 10000 when the client sends none. Why nothing stops it: the limit counts rows, not bytes. The client can pick any fetch size because page_size_fail_threshold=-1, and the guard is skipped for superusers and never sees the 10000 default. Read-size thresholds are off. Concurrent GROUP BY queries multiply the total (32 replica reads, 128 coordinator threads) with no total cap. Size: stage 4 measured +314 MB post-GC peak per query at the 10000 default with 4 KiB rows (about 8x payload) and +247 MB mean / +367 MB max with 1 KiB rows (about 25x payload). Fetch 100000 (and a 200000 default) killed 512 MB nodes. At 64 KiB rows one 10000-row sub-read is about 640 MB serialized, several GB with the amplification, so a few concurrent unpaged GROUP BY queries exceed a default 8-15.5 GiB heap. The default_page_size stem (default_page_size-cqlgroupbylimits_onclose-rowlimit--autonomous) has the same mechanism. The group-limit and group-per-partition stems also see this exposure, because their counters cannot bound a group's rows. File it once.

**Where:** src/java/org/apache/cassandra/cql3/statements/SelectStatement.java:114,899-914,517; src/java/org/apache/cassandra/db/filter/DataLimits.java:983-988,740-748; src/java/org/apache/cassandra/db/ReadResponse.java:196-201; src/java/org/apache/cassandra/config/Config.java:874

## OC-322

**Case file:** `default_page_size-cqlgroupbylimits_onclose-rowlimit--autonomous` · **Agent:** guided · **Patterns:** CP-10, CP-12, CP-6

A plain aggregate with paging off is not paged internally, although the code comment says aggregation is "always paged internally to avoid OOM". Holder: the replica response buffer and the merge state for one sub-read covering the whole partition, or for a range scan each range's whole response. Why nothing stops it: AGGREGATE_EVERYTHING (count/sum/min/max without GROUP BY) gets cqlLimits(NO_LIMIT). The local DEFAULT_PAGE_SIZE in getDataLimits does not reach the pager. AggregationPartitionIterator turns page size <= 0 into NO_LIMIT and returns it unchanged as the sub-page size. There is no read-size threshold and no partition-size guardrail at defaults. Size: the whole partition's live data in one serialized buffer. Stage 4 killed a 512 MB-heap node in 1.5 s with `SELECT count(payload)` over a 2 GB partition (2,000,000 x 1 KiB) on every build. A multi-GB partition does the same to a default heap. A client reaches this with cqlsh PAGING OFF or fetch_size=None.

**Where:** src/java/org/apache/cassandra/cql3/statements/SelectStatement.java:889-920 (920), 337-338, 899-902; src/java/org/apache/cassandra/service/pager/AggregationQueryPager.java:186,193-197,247,406,439-441; src/java/org/apache/cassandra/db/ReadResponse.java:196-201

## OC-323

**Case file:** `excess_waste_bytes-updatewastedallocationtracker-wastedbytes-2--autonomous` · **Agent:** guided · **Patterns:** CP-6, CP-11, CP-1, CP-8

Under hot-partition write contention the memtable heap pool overshoots its limit. Holder: memtable slab regions (heap_buffers default) holding the cloned values of every failed CAS merge attempt. SlabAllocator charges these at clone time and never refunds them, and they stay until the memtable is discarded. Why nothing stops it: the pessimistic-lock fallback (EXCESS_WASTE_BYTES) does `synchronized (this)` on the per-call Updater, a new object for every addAll, so it excludes no writer. Stage 4 measured about 94% of CAS attempts still failing after the switch. A writer whose OpOrder group is blocking a flush barrier is charged past the pool limit without waiting (SubAllocator.allocate's isBlocking branch), and new-partition overhead is also allocated after the fact. Up to 32 writers (concurrent_writes) keep re-cloning while the flush starts. Size: stage 4 measured memtable on-heap at the `Writing` line of 328 MiB against a 128 MiB pool (2.6x), contended owns() 2-4x the single-writer value, and 2-9x fewer rows per flush. At the default memtable_heap_space of heap/4, a 2-3x overshoot puts 50-75% of the heap in memtables alone, on top of caches, reads and compaction. The two other EXCESS_WASTE_BYTES stems (excess_waste_bytes-updatewastedallocationtracker-wastedbytes--autonomous, excess_waste_bytes-uselock-wastetracker--autonomous) show the same mechanism; file it once, naming all three.

**Where:** src/java/org/apache/cassandra/utils/memory/MemtableAllocator.java:180-183; src/java/org/apache/cassandra/utils/memory/SlabAllocator.java:89; src/java/org/apache/cassandra/db/partitions/AtomicBTreePartition.java:122,137,157,168,293; src/java/org/apache/cassandra/db/memtable/SkipListMemtable.java:122-125

## OC-324

**Case file:** `diagnostic_event_memory_store_max_size-store-keyhead--autonomous` · **Agent:** guided · **Patterns:** CP-2, CP-7

NON-DEFAULT ONLY: needs diagnostic_events_enabled=true plus a JMX enableEventPersistence subscription. Holder: one ConcurrentSkipListMap per persisted event class, each holding the latest 200 events with all their referents. AuditEvent keeps its AuditLogEntry, including the full query text. SchemaEvent keeps the previous and updated KeyspaceMetadata, TableMetadata and diffs, so 200 schema snapshots per class. Why nothing stops it: the cap counts events, not bytes. It applies per class, and the stores map is never trimmed. Concurrent publishers overshoot by about their number (208 of 200 measured). Size: stage 4 measured exactly M x event size (200 x 256 KiB = 51 MiB). Audit statements near the 16 MiB native frame limit give about 3.2 GiB for one class, and large schemas multiply SchemaEvent retention. At defaults the store holds nothing.

**Where:** src/java/org/apache/cassandra/diag/store/DiagnosticEventMemoryStore.java:39,43,50-56; src/java/org/apache/cassandra/diag/DiagnosticEventPersistence.java:149-152; src/java/org/apache/cassandra/audit/AuditEvent.java:33; src/java/org/apache/cassandra/schema/SchemaEvent.java:52-64

## OC-325

**Case file:** `block_size-add-blockindex--autonomous` · **Agent:** autonomous · **Patterns:** —

SAI segment-build heap (SegmentTrieBuffer on heap) is checked against a soft global budget. The default segment_write_buffer_size is a fixed 1024 MiB that does not scale with the heap, and the only validation is <= 32768 MiB. A segment flushes only when the global limit is exceeded AND that builder has reached its own minimumFlushBytes, and that threshold is set once in the constructor as limit / ACTIVE_BUILDER_COUNT at that moment. So builders that start one after another keep thresholds of 1 GiB, 512 MiB, 341 MiB and so on, and their sum can reach about limit x H(k): about 1.5 GiB with 2 indexes and about 2.7 GiB with 8 concurrent builders (compactors x indexes). Accounting is in trie capacity terms; stage 4 measured 1.000 GiB at only 604,508 cells, and the heap peak was 4,045 MiB on a 4 GiB heap with the default against 2,511 MiB at 16 MiB. With the default heap (half of RAM, from cassandra-env.sh), a 2-8 GiB host has a 1-4 GiB heap that this buffer alone can mostly fill, on top of memtable_heap_space (1/4 heap).

**Where:** SegmentBuilder.java:149 (threshold fixed at construction), SegmentBuilder.java:211-214, SSTableIndexWriter.java:245-261 (flush only if usageExceedsLimit && hasReachedMinimumFlushSize), V1OnDiskFormat.java:115-128, StorageAttachedIndexOptions.java:26-45, conf/cassandra-env.sh:51-67

## OC-326

**Case file:** `block_size-add-blockindex--autonomous` · **Agent:** autonomous · **Patterns:** —

Memtable-flush RowMapping is not charged to anything. For every OperationType.FLUSH, StorageAttachedIndexWriter builds an InMemoryTrie<Long> with one entry per flushed row: off-heap node buffers that grow by doubling up to the ~2 GB trie limit, plus a boxed Long and a content-array slot per row on heap. It lives until the index flush completes, alongside the memtable that is still held. It is not charged to the memtable pool, the SAI segment limiter or any other budget. Rough size is about 40-80 B per row (up to 2x from buffer doubling): a flush of 3-10M small rows (a 0.7-2.5 GiB memtable) holds about 0.2-0.8 GB of extra native/heap memory, times memtable_flush_writers concurrent flushes.

**Where:** StorageAttachedIndexWriter.java:86, StorageAttachedIndexWriter.java:280, RowMapping.java:85-89, RowMapping.java:72 (InMemoryTrie OFF_HEAP), InMemoryTrie.java:140-158, InMemoryTrie.java:163-175

## OC-327

**Case file:** `hints_write_buffer_size-append-hint_remaining--autonomous` · **Agent:** autonomous · **Patterns:** —

Hint tasks queued on the MutationStage can pile up without a limit. The in-flight hint check (checkHintOverload, max 128 x cores) runs only on the coordinator send paths (StorageProxy.java:796, :1505). Hints made on write timeout or failure (AbstractWriteResponseHandler.onFailure -> submitHint) and on local mutation expiry (LocalMutationRunnable -> submitHint(runnable)) skip it. Each HintRunnable holds a full Mutation (up to max_mutation_size = commitlog_segment_size/2 = 16 MiB by default) and is put on Stage.MUTATION, a SEPExecutor with an unbounded queue. When the single hint-write thread falls behind (slow disk, many dead hosts), HintsBufferPool stops at MAX_HINT_BUFFERS = 3 slabs and blocks MutationStage threads in reserveBuffers.take(). New timeout hints, and the replica mutations queued behind them, then pile up on heap. Rough size: timeouts x mutation size x stall time, e.g. 10k timeouts/s x 10 KiB for 60 s is about 6 GB. Nothing stops it.

**Where:** AbstractWriteResponseHandler.java:309-310, StorageProxy.java:2640-2654, StorageProxy.java:2816-2824, StorageProxy.java:1585-1599 (check only called at :796, :1505), HintsBufferPool.java:113-118, CassandraRelevantProperties.java:351, SEPExecutor.java:105

## OC-328

**Case file:** `max_array_length-checkmaxleafnodecount-numleaves--autonomous` · **Agent:** autonomous · **Patterns:** —

Memory used while flushing a memtable SAI segment is not charged to anything. The memtable-flush path (MemtableIndexWriter -> NumericIndexWriter/BlockBalancedTreeWriter) writes the whole memtable index as one segment and is not under the segment-build limiter. Alongside it, StorageAttachedIndexWriter fills a RowMapping InMemoryTrie<Long> with one entry per flushed row: off-heap buffers that double up to about 2 GB, plus a boxed Long per row on heap. That memory is charged to neither the memtable pool nor the segment limiter, and it is held until the flush finishes, while the memtable is still live. Rough size is about 40-80 B per row: about 0.2-0.8 GB for a 3-10M-row flush (stage 4 saw an 8e6-row single flush at 2.5 GiB of memtable), per concurrent flush writer. The checkMaxLeafNodeCount guard itself is unreachable (it needs about 9e10 points per segment).

**Where:** MemtableIndexWriter.java:146-151, StorageAttachedIndexWriter.java:86, StorageAttachedIndexWriter.java:280, RowMapping.java:72, RowMapping.java:85-89, InMemoryTrie.java:140-158, V1OnDiskFormat.java:171-188

## OC-329

**Case file:** `max_points_in_leaf_node-add-leafvaluecount--autonomous` · **Agent:** autonomous · **Patterns:** —

Same uncharged flush-time structures on the numeric SAI memtable-flush path. The RowMapping trie (one off-heap trie entry plus one boxed Long per flushed row, doubling buffers up to about 2 GB) is held for the whole flush and charged to neither the memtable pool nor the SAI segment limiter. NumericIndexWriter.LeafCallback also keeps a PackedLongValues per leaf (140-224 B per leaf plus the packed row ids) for the whole segment, and on the flush path that segment is the entire memtable. Rough size is about 40-80 B per row for RowMapping, plus a few bytes per row for leafPostings: about 0.2-0.8 GB per flush of 3-10M rows, per concurrent flush writer.

**Where:** StorageAttachedIndexWriter.java:86, StorageAttachedIndexWriter.java:280, RowMapping.java:72, RowMapping.java:85-89, NumericIndexWriter.java:81-101, NumericIndexWriter.java:105-157, MemtableIndexWriter.java:146-181

## OC-330

**Case file:** `max_region_size-tryswapregion-minsize--autonomous` · **Agent:** autonomous · **Patterns:** —

The default memtable allocator wastes slab space that is never charged. memtable_allocation_type defaults to heap_buffers, which uses SlabPool/SlabAllocator, not NativeAllocator. Every memtable that receives any write gets a fixed 1 MiB on-heap Region (ByteBuffer.allocate(REGION_SIZE)), but only the requested bytes are charged to memtable_heap_space (onHeap().allocate(size)). So a table with a few small writes holds 1 MiB of heap that the pool sees as a few KB, and it never triggers a flush (memtable_flush_period is 0 by default, and tables_warn/fail_threshold is -1). The abandoned tail of each replaced region (up to 128 KiB) and RACE_ALLOCATED regions are also uncharged. Rough size is 1 MiB x the number of tables and index tables with unflushed writes: 1,000-2,000 lightly written tables hold about 1-2 GiB of heap outside the memtable budget, until commit-log pressure forces flushes.

**Where:** AbstractAllocatorMemtable.java:100-102, SlabAllocator.java:51-55, SlabAllocator.java:89, SlabAllocator.java:126-150 (REGION_SIZE alloc at :139), MemtableAllocator.java:169-197, conf/cassandra.yaml:825, conf/cassandra.yaml:2039-2040

## OC-331

**Case file:** `max_unsigned_short-validateindexedvalue-value_remaining--autonomous` · **Agent:** autonomous · **Patterns:** —

Large index keys inflate index summaries. The check lets any number of indexed values up to 65,534 B through, and each value becomes a partition key of the hidden 2i table. With the default BIG format, every min_index_interval-th (128th) key of each new index sstable is copied whole into an off-heap IndexSummary. Entries are up to about 64 KiB each, with up to 2 GB allowed per sstable, and index_summary_capacity (5% of heap) is enforced only by the hourly redistribution, which can downsample at most to 1/2048. Rough size is about 1/256 of the index table's on-disk bytes (Data and Index each hold the key) until redistribution: 100 GB of large-value index data gives about 400 MB off-heap, and 1/16 of that afterwards.

**Where:** CassandraIndex.java:616-627, IndexSummaryBuilder.java:100-127, IndexSummaryBuilder.java:187, conf/cassandra.yaml:939-947

## OC-332

**Case file:** `write_buffer_size-append-hint--autonomous` · **Agent:** autonomous · **Patterns:** —

Hint tasks queued on the MutationStage can pile up without a limit. Hints created on write timeout or failure (AbstractWriteResponseHandler.onFailure) and on local mutation expiry call submitHint without checkHintOverload, which is only called at StorageProxy.java:796 and :1505. Each HintRunnable holds a whole Mutation (up to 16 MiB at default max_mutation_size) on the unbounded MutationStage (SEPExecutor) queue. Once the single hint-write thread falls behind and the pool has its MAX_HINT_BUFFERS = 3 slabs (3 x 32 MiB direct), HintsBufferPool blocks MutationStage threads in reserveBuffers.take(). Queued hints and replica mutations then build up on heap with no bound. Rough size: timeouts/s x mutation size x stall seconds, e.g. 10k/s x 10 KiB for 60 s is about 6 GB.

**Where:** AbstractWriteResponseHandler.java:309-310, StorageProxy.java:2640-2654, StorageProxy.java:2816-2824, StorageProxy.java:1585-1599, HintsBufferPool.java:113-118, CassandraRelevantProperties.java:351, SEPExecutor.java:105

## OC-333

**Case file:** `hints_write_buffer_size-append-hint_remaining--autonomous` · **Agent:** guided · **Patterns:** CP-2, CP-5, CP-10, CP-4

Holder: hint tasks queued on the MUTATION stage (StorageProxy.submitHint), each keeping its whole Mutation on heap until HintsService.write copies it into a slab. Why nothing stops it: (a) the only guard, checkHintOverload, counts hints and not bytes (maxHintsInProgress = 128 x cores), and it fires only when a target already has hints in flight; (b) several paths submit hints and never call the check: hints for expired writes (hintMutation), hintOnFailure in AbstractWriteResponseHandler, PaxosCommit and the expiry of LocalMutationRunnable; (c) when all 3 HintsBuffer slabs are full and the single HintsWriteExecutor stalls on a slow or stalled hints disk, HintsBufferPool.switchCurrentBuffer blocks in reserveBuffers.take(). MUTATION threads then block inside HintRunnable while new hint tasks pile up on the unbounded stage queue. Rough size at defaults: 128 x 16 cores = 2048 hints counted before any refusal. At 1 MiB mutations that is about 2 GiB of serialized bytes, and more once deserialized. max_mutation_size (16 MiB) allows up to 32 GiB. The unchecked paths have no count bound at all, only arrival rate x stall time.

**Where:** src/java/org/apache/cassandra/service/StorageProxy.java:202, :1585-1598 (checkHintOverload), :2781-2827 (submitHint onto Stage.MUTATION), :987-988 (hintMutation, no check), :2647-2654; src/java/org/apache/cassandra/service/AbstractWriteResponseHandler.java:310; src/java/org/apache/cassandra/service/paxos/PaxosCommit.java:231; src/java/org/apache/cassandra/hints/HintsBufferPool.java:107-118 (blocking take at 3 slabs)

## OC-334

**Case file:** `hints_write_buffer_size-append-hint_remaining--autonomous` · **Agent:** guided · **Patterns:** CP-14, CP-7

Holder: the compressionBuffer of each CompressedHintsWriter (and the scratch buffer of EncryptedHintsWriter), one per open per-host hints writer. Why nothing stops it: the buffer is resized to the estimated compressed size of the largest input ever passed to writeBuffer. A hint larger than the 256 KiB aggregation buffer is written through directly at its own size (HintsWriter.java:218-220), so one 16 MiB hint grows the buffer to about 16 MiB. The buffer is never trimmed and stays until that host's writer closes. Nothing caps the total across hosts with open writers. Rough size: up to about max_mutation_size (16 MiB) of off-heap memory per host with an open hints file; 50 down hosts gives about 800 MiB. Applies only with the non-default hints_compression or hints encryption. This mechanism also applies to write_buffer_size-append-hint--autonomous; file it once for both stems.

**Where:** src/java/org/apache/cassandra/hints/CompressedHintsWriter.java:39, :49-55; src/java/org/apache/cassandra/hints/HintsWriter.java:214-221

## OC-335

**Case file:** `logs_virtual_table_default_rows-addtobuffer-messagebuffer_size--autonomous` · **Agent:** guided · **Patterns:** CP-2, CP-12

Holder: LogMessagesTable.buffer, a synchronized BoundedLinkedList of LogMessage objects, each with the fully formatted message string. Why nothing stops it: the bound is a row count (50,000 by default, up to 100,000 through -Dcassandra.virtual.logs.max.rows) and never bytes, so one formatted message can be arbitrarily large (for example a huge warning or exception text). Every SELECT on system_views.system_logs also runs data() under the list lock and builds a SimpleDataSet holding every row, so each concurrent read adds a full per-row copy. Rough size: stage 4 measured about 0.5 GB for 50,000 events at 10 KiB each, plus a row-set copy per concurrent read. Requires the CQLLOG appender, which ships commented out in conf/logback.xml, and its WARN filter must pass the events.

**Where:** src/java/org/apache/cassandra/db/virtual/LogMessagesTable.java:91, :94-125 (data() copies the whole buffer), :129-132, :146-152, :176-197; src/java/org/apache/cassandra/utils/logging/VirtualTableAppender.java:121-127

## OC-336

**Case file:** `max_region_size-tryswapregion-minsize--autonomous` · **Agent:** guided · **Patterns:** CP-1, CP-7, CP-9

Holder: the malloc'd Regions of each NativeAllocator, one allocator per live memtable, including memtables of secondary-index tables and memtables still flushing. Why nothing stops it: the pool charges only the bytes requested (offHeap().allocate(size)). Region capacity is never charged: the unfilled tail of the current region and the abandoned tails of replaced regions sit outside memtable_offheap_space, and so do up to 8 race-stashed regions per size class. Regions are freed only at setDiscarded after flush. The table count is unbounded (tables_fail_threshold = -1). This memory is native malloc, outside both -Xmx and MaxDirectMemorySize. Rough size: stage 4 measured about 0.8 MiB of slack per live memtable (119.9 MB at 150 tables). That is about 0.8 GiB at 1,000 tables, doubled while old memtables flush, all on top of memtable_offheap_space (heap/4). Applies only with memtable_allocation_type: offheap_objects, which conf/cassandra_latest.yaml ships; the default is heap_buffers.

**Where:** src/java/org/apache/cassandra/utils/memory/NativeAllocator.java:141 (charge = requested size), :163-176 (region malloc), :200-206 (freed only on discard), :51-57 and :208-227 (global stash); src/java/org/apache/cassandra/utils/memory/MemtablePool.java:151-160

## OC-337

**Case file:** `max_shard_split-getnumshards-count--autonomous` · **Agent:** guided · **Patterns:** CP-15, CP-16

Holder: per-sstable state (SSTableReader on heap, plus the bloom filter, index summary and compression metadata off heap) for every UCS output sstable. Why nothing stops it: the 2^20 clamp bounds only the shard multiplier. target_sstable_size accepts values down to 1 MiB and is checked only against that floor. Nothing caps the number of sstables a table or node may have, so a small target cuts the data into very many sstables, each with fixed per-sstable memory. Rough size: 1 TiB per node at a 1 MiB target gives about 1M sstables; at a few KiB of per-sstable state that is several GiB. Needs a non-default per-table target_sstable_size (default 1 GiB) and sstable_growth; the default compaction is STCS.

**Where:** src/java/org/apache/cassandra/db/compaction/unified/Controller.java:83 (1 MiB minimum target), :505-510, :304-313; src/java/org/apache/cassandra/db/compaction/ShardedCompactionWriter.java:67-80

## OC-338

**Case file:** `none-checklimit-length--autonomous` · **Agent:** guided · **Patterns:** CP-13

Holder: the byte[size] built for each raw hint in Hint.readBufferIfLive, on hint dispatch. Why nothing stops it: size is the 4-byte length field read from the hints file. The only validation is a CRC over those 4 bytes; no check against max_mutation_size or any other limit runs before new byte[size] (ChecksummedDataInput.limit and checkLimit only frame the reads and run around the allocation, not before it). A hints file that is corrupt or rewritten with a consistent CRC can make the node allocate up to 2 GiB per record during replay, on each of the hints delivery threads (2 by default). The legitimate upper bound is about 16 MiB (max_mutation_size).

**Where:** src/java/org/apache/cassandra/hints/HintsReader.java:213-226, :232-240 (and the buffer iterator at :319-342); src/java/org/apache/cassandra/hints/Hint.java:239

## OC-339

**Case file:** `max_points_in_leaf_node-add-leafvaluecount--autonomous` · **Agent:** guided · **Patterns:** CP-7, CP-11, CP-8, CP-16

Holder: the SAI segment builders (SegmentTrieBuffer) of compactions and index builds, one per SAI column index per sstable being written. Why nothing stops it: SEGMENT_BUILD_MEMORY_LIMITER is a soft limit. A builder flushes only when the global usage exceeds the limit AND its own usage has reached minimumFlushBytes. That minimum is fixed when the builder is created, as limit / (active builders at that moment), so the first builder needs the whole limit, the second half of it, and so on. The sum held before every builder may flush is therefore limit x H(k) (harmonic number), not the limit. The check also runs only before the next term is added. The default limit is a fixed 1024 MiB that does not scale with the heap, and validation accepts up to 32768 MiB without comparing it to -Xmx. Rough size at defaults: 4 concurrent builders hold about 2.1 GiB, 8 about 2.7 GiB, 16 about 3.4 GiB. Stage 4 of block_size-add-blockindex saw a single builder at 1.000 GiB. On a 4-8 GiB default heap this sits on top of memtable_heap_space (heap/4). The same mechanism appears in max_array_length-checkmaxleafnodecount-numleaves--autonomous and block_size-add-blockindex--autonomous; file it once for all three stems.

**Where:** src/java/org/apache/cassandra/index/sai/disk/v1/segment/SegmentBuilder.java:149, :211-214, :234; src/java/org/apache/cassandra/index/sai/disk/v1/SSTableIndexWriter.java:209-216, :245-261; src/java/org/apache/cassandra/config/StorageAttachedIndexOptions.java:26-29, :35, :39-45; src/java/org/apache/cassandra/index/sai/disk/v1/V1OnDiskFormat.java:115-128

## OC-340

**Case file:** `max_points_in_leaf_node-add-leafvaluecount--autonomous` · **Agent:** guided · **Patterns:** CP-1, CP-8

Holder: the InMemoryTrie inside each SegmentTrieBuffer, whose buffer type follows memtable_allocation_type. Why nothing stops it: under offheap_buffers or offheap_objects the trie's node and term-byte blocks are direct buffers. The limiter's charge (SegmentTrieBuffer.add and memoryUsed) counts only trie.sizeOnHeap() plus the postings, and sizeOnHeap() leaves out allocatedPos for an off-heap trie. The off-heap trie therefore grows uncharged until the on-heap part trips the soft limit, up to the 2 GiB per-trie hard limit (then SpaceExhaustedException). This memory shares MaxDirectMemorySize with the chunk cache and network buffers. Rough size: roughly the distinct term bytes plus 32-byte trie blocks per builder, likely hundreds of MiB per 1 GiB charged segment for literal indexes with many distinct terms, multiplied by the concurrent builders. Applies only with an off-heap memtable_allocation_type (conf/cassandra_latest.yaml ships offheap_objects).

**Where:** src/java/org/apache/cassandra/index/sai/disk/v1/segment/SegmentTrieBuffer.java:48, :57-59, :62-77; src/java/org/apache/cassandra/db/tries/InMemoryTrie.java:969-981, :140-151

## OC-341

**Case file:** `max_array_length-checkmaxleafnodecount-numleaves--autonomous` · **Agent:** guided · **Patterns:** CP-1, CP-7, CP-8

Holder: the SAI RowMapping built on every memtable flush of a table with SAI indexes. It is an InMemoryTrie(BufferType.OFF_HEAP) mapping each flushed row's PrimaryKey to an sstable row id, with a boxed Long per row as on-heap content. It is held until the memtable index segments are written. Why nothing stops it: this memory is charged to neither the memtable pool (it is created after the memtable is switched out) nor the SAI segment limiter, which covers only non-flush builds. The only bound is the trie's 2 GiB hard limit, which fails the flush with SpaceExhaustedException. Rough size: about 50-100 B of direct memory plus about 20 B of heap per flushed row. A flushed memtable of a few million small rows gives hundreds of MiB. Concurrent flushes (memtable_flush_writers, default 2, across tables) multiply it, and it shares MaxDirectMemorySize with the chunk cache and network buffers.

**Where:** src/java/org/apache/cassandra/index/sai/disk/RowMapping.java:75, :85-90, :155; src/java/org/apache/cassandra/index/sai/disk/StorageAttachedIndexWriter.java:86; src/java/org/apache/cassandra/index/sai/disk/v1/MemtableIndexWriter.java:147, :212; src/java/org/apache/cassandra/db/tries/InMemoryTrie.java:140-151

## OC-342

**Case file:** `block_size-writeposting-blocksize--autonomous` · **Agent:** autonomous · **Patterns:** —

SAI segment-build heap budget (`sai_options.segment_write_buffer_size`) is the real limit on the PostingsWriter path. It defaults to a fixed 1024 MiB and is not scaled to the heap. The only validation is <= 32768 MiB. The default heap from cassandra-env.sh is half of RAM, so a 4 GiB host gets a 2 GiB heap and SAI compaction/index-build builders alone may hold 50 % of it before anything flushes, on top of memtable_heap_space (1/4 heap) and reads. A builder flushes only when global usage is over the limit AND it has itself reached limit/activeBuilders. It stays charged while it writes its segment, and the writer's own allocations (LiteralIndexWriter/NumericIndexWriter, per-term PackedLongValues.build()) are not charged. Rough size at defaults: ~1 GiB of trie and postings charged plus uncharged flush-time allocations. Stage 4 (3M rows, -Xmx2G) shows the default arm with the gauge at the limit (1,073,743,912 B) and the heap peak at 1,918 of 2,048 MiB, against 1,280 MiB with a 16 MiB buffer.

**Where:** StorageAttachedIndexOptions.java:26,34,38-43; V1OnDiskFormat.java:126-131,174-179; SegmentBuilder.java:52,143-150,232-236; SSTableIndexWriter.java:214-226,245-260,290-296; SegmentTrieBuffer.java:57-60,62-77,98; conf/cassandra-env.sh:57-66

## OC-343

**Case file:** `max_keys_sparse-addinternal-keys--autonomous` · **Agent:** autonomous · **Patterns:** —

SASI segment builders go to unbounded queues. When a builder's estimate reaches maxMemorySize, PerSSTableIndexWriter.Index.add hands the whole builder to an 8-thread executor (SASI-Memtable or SASI-General) and goes on filling a new builder without waiting. The executor queue is Integer.MAX_VALUE long, so every running or queued builder stays live until its finish() ends. On compaction or index build the default limit is 0.15 GiB = 154 MiB per builder, so 8 running builders already hold ~1.2 GiB of estimate per pool, and the queue has no limit. On a memtable flush the limit is a fixed 1 GiB per index, not scaled to the heap (default heap = half of RAM). Analyzed or CONTAINS indexes add one entry per token, so one memtable of 1/4 heap can produce many 1 GiB builders (up to 8 GiB running per pool), times memtable_flush_writers and the number of indexes. The estimate also undercounts: it charges 108 B per add, while a real token is a TreeMap entry plus a boxed Long plus a LongHashSet(2). Stage-4 of sibling cases measured ~400 B real per 236 B estimate per term and ~242 B per token. Needs sasi_indexes_enabled: true.

**Where:** PerSSTableIndexWriter.java:63-73,247-250,254-258,365-369; ThreadPoolExecutorBuilder.java:160-167; IndexMode.java:59-60; OnDiskIndexBuilder.java:175-195; DynamicTokenTreeBuilder.java:32,48-55

## OC-344

**Case file:** `max_keys_sparse-addinternal-keys--autonomous` · **Agent:** autonomous · **Patterns:** —

CONTAINS-mode finish() allocates memory the estimate does not charge. finish() builds a SuffixSA, which decodes every distinct term to a UTF-16 CharBuffer (2 B/char + objects), allocates long[charCount] (8 B per character of all distinct terms) and TimSorts it (up to n/2 longs of temp), while the builder's terms map is still fully live. The estimate charges 1 B per term byte. Rough size at defaults: ~12-14 B per indexed character of transient heap on top of a builder estimated at up to 1 GiB (flush) or 154 MiB (compaction). With mostly-distinct 100-char terms that is ~4x the estimate per finishing builder, times up to 8 concurrent finishes per pool.

**Where:** OnDiskIndexBuilder.java:253-260; SuffixSA.java:39-42,61-88; SA.java:48-52

## OC-345

**Case file:** `max_offset-createentry-offset--autonomous` · **Agent:** autonomous · **Patterns:** —

SASI segment builders whose token trees feed createEntry are queued without a bound. PerSSTableIndexWriter.Index.add submits the full builder to an 8-thread pool and continues with a new builder; the pool has an unbounded (Integer.MAX_VALUE) queue, so every running or queued builder (a terms HashMap plus per-term TreeMap<Long, LongHashSet> of tokens and offsets) stays live until finish() ends. Each builder holds up to 1 GiB of estimate on a memtable flush (fixed, not heap-relative) or 154 MiB on compaction (default 0.15 GiB). Rough size: 8 running x 154 MiB = ~1.2 GiB per compaction pool, 8 x 1 GiB per flush pool, plus the queue. The 108 B/add estimate also undercounts the real per-token objects (~1.7-2x). Needs sasi_indexes_enabled: true.

**Where:** PerSSTableIndexWriter.java:63-73,247-250,254-258,365-369; ThreadPoolExecutorBuilder.java:160-167; OnDiskIndexBuilder.java:175-195; DynamicTokenTreeBuilder.java:32,48-55; IndexMode.java:59-60

## OC-346

**Case file:** `max_offset-createentry-offset--autonomous` · **Agent:** autonomous · **Patterns:** —

CONTAINS-mode finish() makes uncharged suffix-array allocations: UTF-16 copies of all terms plus long[charCount] plus TimSort temp, ~12-14 B per character of distinct terms. They are allocated while the builder (estimate up to 1 GiB on flush) is still live, so they come on top of it.

**Where:** OnDiskIndexBuilder.java:253-260; SuffixSA.java:39-42,61-88

## OC-347

**Case file:** `min_compress_ratio-flushdata-maxcompressedlength-2--autonomous` · **Agent:** autonomous · **Patterns:** —

Chunk offsets of every open compressed SSTable live in native memory with no budget. CompressionMetadata.open reads all chunk offsets into Memory.allocate(chunkCount*8) and keeps them for the reader's lifetime. No memtable, cache or direct-memory budget counts this memory. At the default 16 KiB chunk that is 8 B per 16 KiB = 1/2048 of the uncompressed data on the node: 2 TB of data is ~1 GiB native, 10 TB is ~5 GiB. The writer side (CompressionMetadata.Writer.addOffset) grows a SafeMemory by doubling and copying for each SSTable being written (transient 1.5x of chunkCount*8).

**Where:** CompressionMetadata.java:70-112,188-210,341-372; CompressionInfoComponent.java:53; CompressedSequentialWriter.java:183

## OC-348

**Case file:** `min_compress_ratio-flushdata-maxcompressedlength-2--autonomous` · **Agent:** autonomous · **Patterns:** —

Streaming a compressed SSTable with partial sections (not whole-SSTable streaming, e.g. repair over vnode ranges) materializes the chunks on the heap. CompressionInfo.chunks() calls getChunksForSections, which builds a TreeSet<Chunk> with one Chunk(offset, length) object per 16 KiB chunk in the sections and copies it to a Chunk[]. The CassandraOutgoingFile header keeps that array until the file is acknowledged, and the receiver deserializes the same Chunk[]. Rough size: a 100 GiB section is 6.5M chunks x (24 B Chunk + 40 B TreeMap entry) = ~420 MB transient, then ~180 MB retained per file on each side, multiplied by concurrent stream sessions.

**Where:** CompressionMetadata.java:313-339,504-515; db/streaming/CompressionInfo.java:131-160; CassandraOutgoingFile.java:51,69,79-80; CassandraStreamHeader.java:53,101-107,172,212

## OC-349

**Case file:** `min_compress_ratio-flushdata-maxcompressedlength--autonomous` · **Agent:** autonomous · **Patterns:** —

Chunk offsets of every open compressed SSTable live in native memory with no budget. CompressionMetadata.open reads all chunk offsets into Memory.allocate(chunkCount*8) and keeps them for the reader's lifetime. No memtable, cache or direct-memory budget counts this memory. At the default 16 KiB chunk that is 1/2048 of the uncompressed data on the node: ~1 GiB native per 2 TB, ~5 GiB per 10 TB. The writer's offset buffer also grows by doubling copy for each SSTable (transient 1.5x chunkCount*8).

**Where:** CompressionMetadata.java:70-112,188-210,341-372; CompressionInfoComponent.java:53; CompressedSequentialWriter.java:183

## OC-350

**Case file:** `min_compress_ratio-flushdata-maxcompressedlength--autonomous` · **Agent:** autonomous · **Patterns:** —

Streaming a compressed SSTable with partial sections materializes the chunks on the heap. getChunksForSections builds a TreeSet<Chunk> with one object per 16 KiB chunk in the streamed sections, then a Chunk[]. The outgoing file's header keeps the array until the file is acknowledged, and the receiver deserializes it in full. Rough size: a 100 GiB section is ~6.5M chunks, ~420 MB transient and ~180 MB retained per file, multiplied by concurrent sessions and files.

**Where:** CompressionMetadata.java:313-339,504-515; db/streaming/CompressionInfo.java:131-160; CassandraOutgoingFile.java:51,69,79-80; CassandraStreamHeader.java:53,101-107

## OC-351

**Case file:** `none-queryprocessor-validatekey-key_remaining--autonomous` · **Agent:** autonomous · **Patterns:** —

IN lists on a composite partition key are expanded into their full cartesian product on the heap before any key is validated or counted. MultiCBuilder.addEachElementToAll builds one ArrayList per combination; build() then copies these into a BTreeSet of Clustering objects, and toByteBuffers serializes each one. SelectStatement then clones each key into a DecoratedKey and creates one SinglePartitionReadCommand per key. Both guardrails that could stop this, in_select_cartesian_product and partition_keys_in_select, are -1 (disabled) by default, and partitionKeysInSelect is checked only after the list exists. There is no cap on IN-list length beyond the 16 MiB native frame. Rough size: (a,b) IN 5,000 x 5,000 values (~80 KB request) gives 25M composites. That is ~60-70 B per composite in elementsList, ~80-100 B per BTreeSet Clustering, ~60 B per serialized key and as much again for the clone, ~40 B per DecoratedKey and ~150 B+ per read command: several GB on one coordinator request. 2,000 x 2,000 already gives 4M keys, ~1-2 GB.

**Where:** PartitionKeySingleRestrictionSet.java:60-71,88-101; MultiCBuilder.java:339-372,416-436; SelectStatement.java:716-735; ModificationStatement.java:368-375; Guardrails.java:251,294; conf/cassandra.yaml:2098-2105

## OC-352

**Case file:** `none-validatekey-key_remaining--autonomous` · **Agent:** autonomous · **Patterns:** —

A single UPDATE/DELETE with IN on the partition key and IN on clustering columns builds keys x clusterings rows in memory before max_mutation_size is checked. Both lists are materialized by MultiCBuilder as full cartesian products (in_select_cartesian_product is disabled by default and not applied across pk x ck). ModificationStatement then loops over every key (Validation.validateKey) and every clustering, calling addUpdateForKey into one PartitionUpdate.Builder per key. Mutation.validateSize runs only later, at the commit-log add or the remote MutationVerbHandler, after everything is built. Rough size: pk IN 5,000 x ck IN 5,000 (a ~80 KB request) is 25M rows at ~100-200 B per row and cell, so ~2.5-5 GB on the coordinator heap. A 2-column composite pk IN 5,000 x 5,000 also gives 25M keys at ~60-70 B each in elementsList plus Clustering and ByteBuffer copies.

**Where:** ModificationStatement.java:368-375,776-818; MultiCBuilder.java:339-372,416-436; PartitionKeySingleRestrictionSet.java:88-101; ClusteringColumnRestrictions.java:112-113; Mutation.java:169; CommitLog.java:304; MutationVerbHandler.java:54; conf/cassandra.yaml:2104-2105

## OC-353

**Case file:** `overflow_trailer_capacity-createoverflowentry-overflowcollisions--autonomous` · **Agent:** autonomous · **Patterns:** —

SASI token-tree builders, whose leaves hold the overflow offsets, are held by segment flush tasks on unbounded queues. Each full OnDiskIndexBuilder is submitted to an 8-thread SASI-Memtable or SASI-General pool whose queue is Integer.MAX_VALUE long, and the writer keeps filling a new builder without waiting. Every running or queued builder stays live: its terms map plus a TreeMap<Long, LongHashSet> per term. Per builder that is up to 1 GiB of estimate on a memtable flush (fixed, not heap-relative) or 154 MiB on compaction (default 0.15 GiB). Rough size: 8 x 154 MiB = ~1.2 GiB per compaction pool, 8 x 1 GiB per flush pool, plus the queue. The real heap is ~1.7-2x the 108 B/add estimate. Stage-4 of this case: with the option at 100 MiB the post-collection heap peak was 927 MiB, against 401 MiB at 1 MiB. Needs sasi_indexes_enabled: true.

**Where:** PerSSTableIndexWriter.java:63-73,247-250,254-258,365-369; ThreadPoolExecutorBuilder.java:160-167; OnDiskIndexBuilder.java:175-195; DynamicTokenTreeBuilder.java:32,48-55; IndexMode.java:59-60

## OC-354

**Case file:** `overflow_trailer_capacity-createoverflowentry-overflowcollisions--autonomous` · **Agent:** autonomous · **Patterns:** —

CONTAINS-mode finish() makes uncharged suffix-array allocations (UTF-16 term copies, long[charCount], TimSort temp; ~12-14 B per character of distinct terms) while the builder (up to 1 GiB estimate) is still live.

**Where:** OnDiskIndexBuilder.java:253-260; SuffixSA.java:39-42,61-88

## OC-355

**Case file:** `super_block_size-flushsuperblock-datablockscnt--autonomous` · **Agent:** autonomous · **Patterns:** —

SASI builders, the memory that actually backs the super-block trees, have no hard bound: the threshold is an undercounted estimate and finished builders queue without limit. Each full builder is submitted to an 8-thread pool with an Integer.MAX_VALUE queue, and the writer does not wait, so running and queued builders stay live. Per builder: 1 GiB of estimate on a memtable flush (fixed, independent of heap) or 154 MiB on compaction. The estimate charges 108 B per add, against ~242 B per token measured in stage 4 of this case. Rough size: 8 x 154 MiB est. (~2.5 GiB real) per compaction pool, 8 x 1 GiB est. per flush pool, plus the queue. Stage 4 here shows the post-collection heap peak at 1,941 MiB with the option at 512 MiB, against ~800 MiB at 64. During finish() the per-block combinedIndex trees and the superBlockTree copies (LongHashSet(4) per token) are also allocated on top of the live builder. Needs sasi_indexes_enabled: true.

**Where:** PerSSTableIndexWriter.java:63-73,247-250,254-258,365-369; ThreadPoolExecutorBuilder.java:160-167; OnDiskIndexBuilder.java:175-195,483-505,612; DynamicTokenTreeBuilder.java:48-55,67-77; IndexMode.java:59-60

## OC-356

**Case file:** `super_block_size-flushsuperblock-datablockscnt--autonomous` · **Agent:** autonomous · **Patterns:** —

CONTAINS-mode finish() makes uncharged suffix-array allocations (UTF-16 term copies, long[charCount], TimSort temp; ~12-14 B per indexed character) while the builder is still fully live.

**Where:** OnDiskIndexBuilder.java:253-260; SuffixSA.java:39-42,61-88

## OC-357

**Case file:** `tokens_per_block-add-pos--autonomous` · **Agent:** autonomous · **Patterns:** —

The SASI builders holding the DynamicTokenTreeBuilder TreeMaps are bounded only by an undercounted estimate, and finished builders sit on unbounded queues. The estimate is 236 B per distinct term, but stage 4 here retained ~400 MB for 1M terms (~1.7x). Each builder that reaches maxMemorySize goes to an 8-thread SASI pool with an Integer.MAX_VALUE queue, and the writer starts a new builder without waiting, so running and queued builders all stay live. Per builder: up to 1 GiB of estimate on a memtable flush (fixed, independent of heap) or 154 MiB on compaction (default 0.15 GiB). Rough size: 8 x 154 MiB est. per compaction pool (~2 GiB real), 8 x 1 GiB est. per flush pool, plus the queue. Needs sasi_indexes_enabled: true.

**Where:** PerSSTableIndexWriter.java:63-73,247-250,254-258,365-369; ThreadPoolExecutorBuilder.java:160-167; OnDiskIndexBuilder.java:175-195; DynamicTokenTreeBuilder.java:32,48-55; IndexMode.java:59-60

## OC-358

**Case file:** `tokens_per_block-add-pos--autonomous` · **Agent:** autonomous · **Patterns:** —

CONTAINS-mode finish() allocates the suffix array outside the estimate: it decodes every distinct term to a CharBuffer, allocates long[charCount] and TimSorts it, ~12-14 B per character, while the builder's terms map is still live. The estimate charges 1 B per term byte, so a builder estimated at 1 GiB (flush) of mostly-distinct ~100-char terms needs roughly 4x that transiently, per concurrent finish (up to 8 per pool).

**Where:** OnDiskIndexBuilder.java:253-260; SuffixSA.java:39-42,61-88; SA.java:48-52

## OC-359

**Case file:** `block_size-writeposting-blocksize--autonomous` · **Agent:** guided · **Patterns:** CP-8, CP-11

SAI segment-build heap limit `segment_write_buffer_size` ships at a fixed 1024 MiB (validated only against a 32 GiB maximum) and does not scale with the heap. It is a soft, global limit: a builder flushes only once the global usage is over the limit AND that builder has reached its minimum flush size (limit / active builders). So the overshoot grows with the number of concurrent compactions and index builds, and memtable-flush SAI builds are outside it. Holder: the SegmentBuilders of SAI index builds and compactions (SSTableIndexWriter). Measured in stage 4 at -Xmx2G, 3M rows, stock build: the gauge reached 1,073,743,912 B (the limit), and the heap peaked at 1,892-1,918 MiB of 2,048, against 1,280 MiB with a 16 MiB buffer. Size at defaults: 1 GiB plus the overshoot. That is half of a 2 GiB heap and a quarter of a 4 GiB heap, on top of memtables (1/4 heap) and the caches.

**Where:** src/java/org/apache/cassandra/config/StorageAttachedIndexOptions.java:26 and :35; src/java/org/apache/cassandra/index/sai/disk/v1/V1OnDiskFormat.java:126-129; src/java/org/apache/cassandra/index/sai/disk/v1/SSTableIndexWriter.java:248

## OC-360

**Case file:** `max_offset-createentry-offset--autonomous` · **Agent:** guided · **Patterns:** CP-1, CP-11, CP-12

SASI CONTAINS-mode segment finish allocates outside the builder estimate. OnDiskIndexBuilder.finish decodes every term into a UTF-16 CharBuffer (SuffixSA.getTerm) and allocates long[charCount] for the suffix array, about 10 B per character (2 B CharBuffer + 8 B suffix slot). The flush estimate (estimatedBytes) charged only 1 B per term byte plus fixed overheads, and the check runs only before finish, against that estimate. Merged DynamicTokenTreeBuilder containers for common suffixes add more on top. Holder: the SASI-Memtable / SASI-General pool threads (8 each) running finish. Size: with long text terms (up to MAX_TERM_SIZE 1024 B), finish needs about 8-10x the estimate. A memtable-flush builder (1 GiB estimate) can therefore need about 8 GiB more at finish, and a compaction builder (161 MB estimate) about 1.3 GB more, per running finish, with up to 8 running at once. Needs sasi_indexes_enabled=true (default false). The same finish path is reached from overflow_trailer_capacity-createoverflowentry-overflowcollisions--autonomous and tokens_per_block-add-pos--autonomous (stage 4 there notes that CONTAINS indexes every suffix).

**Where:** src/java/org/apache/cassandra/index/sasi/disk/OnDiskIndexBuilder.java:254-260; src/java/org/apache/cassandra/index/sasi/sa/SuffixSA.java:41 and :64; src/java/org/apache/cassandra/index/sasi/sa/SA.java:48-52

## OC-361

**Case file:** `tokens_per_block-add-pos--autonomous` · **Agent:** guided · **Patterns:** CP-1, CP-7, CP-8

The SASI index builder's heap counter under-counts. On a memtable flush it is compared with a fixed 1 GiB that does not scale with the heap. OnDiskIndexBuilder charges fixed amounts: 64+48+term bytes per new term and 108 B per add. It omits the HashMap node, the ByteBuffer object and the boxed Long / LongHashSet arrays. Stage 4 measured 236 B per distinct term in estimatedMemoryUse() against about 400 MB retained at 1M terms, about 1.7x held over counted. PerSSTableIndexWriter uses maxMemorySize = 1073741824 for OperationType.FLUSH regardless of -Xmx. Compaction uses max_compaction_flush_memory_in_mb, default 161 MB. The limit applies per SASI column index per SSTable writer. With memtable_flush_writers=2 and N SASI indexes on a table, the builders sum to about 2 x N x 1.7 GiB real. They sit on heap beside the memtable being flushed, and with offheap memtables the builders are the only on-heap copy and are not charged anywhere. Size at defaults with SASI enabled: about 1.7 GiB per index per flushing memtable, so 2 indexes x 2 flush writers is about 7 GiB, against the cassandra-env heap cap of 8 GiB. Same mechanism in max_keys_sparse-addinternal-keys--autonomous (stage 4 there gives the estimate T*116 + T*K*108), super_block_size-flushsuperblock-datablockscnt--autonomous, max_offset-createentry-offset--autonomous and overflow_trailer_capacity-createoverflowentry-overflowcollisions--autonomous. Needs sasi_indexes_enabled=true (default false).

**Where:** src/java/org/apache/cassandra/index/sasi/disk/OnDiskIndexBuilder.java:180-182 and :194; src/java/org/apache/cassandra/index/sasi/disk/PerSSTableIndexWriter.java:247 and :365-368; src/java/org/apache/cassandra/index/sasi/conf/IndexMode.java:59-60

## OC-362

**Case file:** `super_block_size-flushsuperblock-datablockscnt--autonomous` · **Agent:** guided · **Patterns:** CP-5, CP-7, CP-11

SASI segment flushes are handed to static 8-thread pools (SASI-Memtable, SASI-General) whose queue is unbounded: ThreadPoolExecutorBuilder uses Integer.MAX_VALUE when no queue limit is set. The writing thread never waits. When currentBuilder.estimatedMemoryUse() reaches maxMemorySize, Index.add swaps in a new builder and submits the full one. The submitted closure keeps the old builder reachable until a pool thread finishes it. So the per-builder limit bounds only one builder, not how many are full and waiting. Nothing pushes back on the flush or compaction feeding rows, and the pools are shared by all tables and all concurrent compactions. Finish is slow in CONTAINS mode (suffix sort), so queued builders accumulate. Holder: the executor queue plus 8 running finishes, plus the Index.segments set (Futures of opened OnDiskIndex parts, kept until complete()). Size: compaction builders of 161 MB estimate (about 270 MB real) x (8 running + queued) is at least 2.2 GB, and unbounded beyond that. Memtable-flush builders are 1 GiB estimate each. Also applies to max_keys_sparse-addinternal-keys--autonomous and tokens_per_block-add-pos--autonomous. Needs sasi_indexes_enabled=true.

**Where:** src/java/org/apache/cassandra/index/sasi/disk/PerSSTableIndexWriter.java:63-73, :247-250, :254-258; src/java/org/apache/cassandra/concurrent/ThreadPoolExecutorBuilder.java:160-167

## OC-363

**Case file:** `min_compress_ratio-flushdata-maxcompressedlength--autonomous` · **Agent:** guided · **Patterns:** CP-16, CP-7, CP-6

The SSTable writer's buffers are sized straight from the per-table schema option chunk_length_in_kb. That option is checked only for > 0, power of two, and <= Integer.MAX_VALUE/1024 KB, so values up to 1 GiB (1048576 KB) are accepted. CompressedSequentialWriter allocates a chunkLength buffer and a compressor.initialCompressedBufferLength(chunkLength) buffer (LZ4: off-heap, about chunk + bound) per SSTable writer. Anyone with ALTER on a table can set it, and no guardrail covers it. Holder: each flush writer (memtable_flush_writers) and compaction writer (concurrent_compactors), for the writer's lifetime. Size: about 2 GiB of direct memory per writer at chunk_length_in_kb=1048576, or 128 MiB per writer at 64 MiB chunks, against the default 16 KiB. Only MaxDirectMemorySize (by default equal to the heap size) refuses it. The sibling min_compress_ratio-flushdata-maxcompressedlength-2--autonomous shares the same option map; the read side is filed there.

**Where:** src/java/org/apache/cassandra/schema/CompressionParams.java:352 and :447-451; src/java/org/apache/cassandra/io/compress/CompressedSequentialWriter.java:90 and :98; src/java/org/apache/cassandra/io/compress/LZ4Compressor.java:113-116

## OC-364

**Case file:** `min_compress_ratio-flushdata-maxcompressedlength-2--autonomous` · **Agent:** guided · **Patterns:** CP-14, CP-16, CP-7

On the read side, compressed-chunk reads go through ThreadLocalByteBufferHolder.getBuffer(chunk.length+4). That is a per-thread FastThreadLocal direct buffer that is replaced by a larger one whenever a bigger chunk is read and is never shrunk or released. Each open reader's rebufferer also takes a chunk-sized buffer from BufferPools.forChunkCache(). Chunk size comes from the unchecked per-table chunk_length_in_kb (accepted up to 1 GiB). So after one read of a large-chunk table, every ReadStage, compaction and streaming thread that touched it keeps a chunk-sized direct buffer for good, and concurrent reads each add a chunk-sized uncompressed buffer. Holder: thread-locals of about concurrent_reads (32) + compaction + other reader threads, plus per-read rebufferer buffers. Size: about 32 x 64 MiB = 2 GiB retained at 64 MiB chunks, and 32 GiB at 1 GiB chunks, against 16 KiB per thread at the default. It is bounded only by MaxDirectMemorySize. Same root option as min_compress_ratio-flushdata-maxcompressedlength--autonomous (write side filed there).

**Where:** src/java/org/apache/cassandra/io/util/ThreadLocalByteBufferHolder.java:74-77; src/java/org/apache/cassandra/io/util/CompressedChunkReader.java:130 and :138; src/java/org/apache/cassandra/io/util/BufferManagingRebufferer.java:45; src/java/org/apache/cassandra/schema/CompressionParams.java:352

## OC-365

**Case file:** `none-queryprocessor-validatekey-key_remaining--autonomous` · **Agent:** guided · **Patterns:** CP-2, CP-8, CP-11, CP-13, CP-1

A SELECT with IN on partition-key columns builds every key, and the cartesian product for composite keys, before any limit applies. Both guardrails, partition_keys_in_select and in_select_cartesian_product, ship off (-1). Even when enabled, they run after the product has been built: MultiCBuilder.addEachElementToAll copies a composite list per combination before PartitionKeySingleRestrictionSet calls guard(builder.buildSize()), and partitionKeysInSelect runs after keys are returned. SelectStatement then clones and decorates each key (ByteBufferUtil.clone + DecoratedKey + token) and creates one SinglePartitionReadCommand per key, all up front, even when paged. The native in-flight limits charge request bytes, not the expansion. Holder: the coordinator's request thread, for the life of the query. Size: about 250-350 B per key. Two IN lists of 3,000 values on a two-column key (about 50 KB request) give 9M keys, about 2.5-3 GB from one request. A single-column IN bound list inside the 16 MiB frame gives about 1.3M keys, about 400 MB, times up to 128 concurrent native requests. The write-side twin is filed under none-validatekey-key_remaining--autonomous.

**Where:** src/java/org/apache/cassandra/cql3/statements/SelectStatement.java:716-736; src/java/org/apache/cassandra/cql3/restrictions/PartitionKeySingleRestrictionSet.java:89-99; src/java/org/apache/cassandra/db/MultiCBuilder.java:339-358; src/java/org/apache/cassandra/config/Config.java:875-878

## OC-366

**Case file:** `none-validatekey-key_remaining--autonomous` · **Agent:** guided · **Patterns:** CP-2, CP-8, CP-11, CP-13, CP-1

An UPDATE or DELETE with IN on partition-key and clustering columns expands to (product of the partition-key IN lists) mutations x (product of the clustering IN lists) rows each. All of it is built in memory before anything is applied. ModificationStatement.getMutations builds every key (buildPartitionKeyNames), loops validateKey / decorateKey per key, adds a row for each clustering in createClustering's set to a PartitionUpdate.Builder per key, and then calls collector.toMutations. No count limit applies: the in_select_cartesian_product guardrail is off (-1) and is checked after the product is built. max_mutation_size bounds each mutation, not their number. The native in-flight limits charge the small request bytes, not the expansion. The mutations then stay referenced until the write completes or times out. Holder: the coordinator heap (mutations, rows and per-replica message copies). Size: bound lists of 10,000 partition keys x 10,000 clusterings (a request of about 200 KB) give 10,000 mutations of about 200 KB each (each under max_mutation_size) and 10^8 row objects, about 10-15 GB of heap from one statement, even with shared tiny values. Same root, the unguarded IN expansion, as none-queryprocessor-validatekey-key_remaining--autonomous (SELECT side).

**Where:** src/java/org/apache/cassandra/cql3/statements/ModificationStatement.java:369-377, :739-750, :796-818; src/java/org/apache/cassandra/cql3/Validation.java:47-51; src/java/org/apache/cassandra/db/MultiCBuilder.java:339-358

## OC-367

**Case file:** `excess_waste_offset-updatewastedallocationtracker-delta--autonomous` · **Agent:** autonomous · **Patterns:** —

Holder: memtable slab regions (heap_buffers, default) filled by failed CAS retries on a hot partition. Each failed merge attempt clones the update's cell values through the memtable allocator, and they are charged and kept in 1 MiB slab regions (values up to 128 KiB). Nothing refunds them when the CAS loses. Why nothing stops it: (a) the 'pessimistic lock' is synchronized on the per-call Updater, so it excludes no one and retries go on after the flip; (b) while a flush barrier has marked the old write OpGroup as blocking, MemtableAllocator.allocate skips the pool limit and charges past memtable_heap_space. So every retry of every old-group writer during a barrier lands on the heap above the pool. Rough size at defaults: there are up to concurrent_writes=32 old-group writers on one partition, and each failure means another writer won, so up to about 32*31/2 ≈ 500 failed attempts × the update size. The update size is bounded only by max mutation size (commitlog_segment_size/2 = 16 MiB). That is ~500 MiB of real retained slab memory past the limit for 1 MiB batches and several GiB for maximum-size mutations, on top of memtable_heap_space = heap/4. Stage 4 measured memtable on-heap at flush start at 2-3x the pool limit in the hot-partition cells.

**Where:** src/java/org/apache/cassandra/utils/memory/MemtableAllocator.java:180-183; src/java/org/apache/cassandra/db/partitions/AtomicBTreePartition.java:120-123,153-170,179-186; src/java/org/apache/cassandra/db/partitions/BTreePartitionUpdater.java:126-132,149-160; src/java/org/apache/cassandra/utils/memory/SlabAllocator.java:89-92,139

## OC-368

**Case file:** `none-addall-size--autonomous` · **Agent:** autonomous · **Patterns:** —

Holder: the transient per-write copy of a memtable partition's whole RangeTombstoneList. Every update that carries range tombstones runs existing.mutableCopy().add(update), which copies all n slots (20 B/slot: two ClusteringBound[], long[], int[] at capacity == size) and then, through addAll, immediately grows the full copy by 1.5x (another 30 B/slot). That is about 50·n bytes of short-lived arrays per write attempt. For n beyond about 100k these are G1 humongous objects. Why nothing stops it: it uses HeapCloner, not the memtable allocator, and only the delta of unsharedHeapSize is charged, so no pool or limit sees the copy. Each CAS retry on a contended partition copies again, and the Updater lock does not exclude. Rough size at defaults: up to concurrent_writes=32 writers each hold one copy. A partition with n = 500k range tombstones in the memtable gives ~25 MB per attempt × 32 ≈ 0.8 GB live at once. A few million tombstones, which the heap/4 memtable pool allows, give several GB, on top of the memtable itself.

**Where:** src/java/org/apache/cassandra/db/partitions/BTreePartitionUpdater.java:120-121; src/java/org/apache/cassandra/db/MutableDeletionInfo.java:81-83,138-141; src/java/org/apache/cassandra/db/RangeTombstoneList.java:106-112,213-232,664-686

## OC-369

**Case file:** `none-compose-buffer_remaining--autonomous` · **Agent:** guided · **Patterns:** CP-12, CP-6

Holder: the UDA state object (UDAggregate aggregate `state`). It is carried across every row the aggregate reads, including across internal aggregation pages, and grows with what the state function keeps (for example a map or list that collects values). Why nothing stops it: (1) the only UDF limit is a per-call CPU-time timeout (warn 500 ms, fail 1500 ms), and a cheap put-into-map call never reaches it; (2) the paging and page size limit rows per page, not the state carried across pages; (3) compose/decompose (UDFDataType.java:177-180, CodecUtils.pack) has no size check from V3 on (the 65535 checks apply only to V1/V2, which the server does not accept). At the end the state is serialized whole: element buffers plus one result ByteBuffer (CodecUtils.java:48-58), so there are at least two copies, then a response. Rough size: rows aggregated x (value + about 100 B of map/box overhead) x about 2-3 copies at decompose. Example: SELECT agg(v) over 10M rows of 100 B gives about 2 GB of state plus about 1 GB serialized, past an 8 GB heap's free room. Reachable only with user_defined_functions_enabled=true (default false, Config.java:588). This is the same mechanism for the codec-path cases native_protocol_v1_v2_collection_size_limit-writesize-size--autonomous and native_protocol_v1_v2_max_element_size-sizeofvalue-elemsize--autonomous, filed once here.

**Where:** src/java/org/apache/cassandra/cql3/functions/UDAggregate.java:198 (state = udf.executeForAggregate across rows), UDAggregate.java:225-231 (decompose whole state), UDFunction.java:486-555 (CPU-time-only timeout), cql3/functions/types/CodecUtils.java:48-58 (pack: element buffers + full result copy, no cap from V3 on)

## OC-370

**Case file:** `name_length-validatecustomindexcolumnname-name--autonomous` · **Agent:** guided · **Patterns:** CP-1, CP-7, CP-15

Holder: the per-memtable SlabAllocator region of every table and index table (each index is a hidden table with its own memtable). With the default memtable_allocation_type heap_buffers (cassandra.yaml:825, which gives SlabPool on-heap, AbstractAllocatorMemtable.java:100-102), the first write to a memtable allocates a whole 1 MiB region (SlabAllocator.java:51, 139). The pool is charged only the bytes cloned (SlabAllocator.java:89); the rest of the region is held but not counted. Why nothing stops it: memtable_heap_space bounds only the charged bytes, and the number of tables and indexes is uncapped at defaults (guardrails tables_* and secondary_indexes_per_table_* = -1, Config.java:865-870). With memtable_flush_period 0, a lightly written table keeps its region until a commit-log-driven flush, and an old and a new memtable both hold a region during a flush. Rough size: about 1 MiB per written table or index, up to 2 MiB while flushing. With 1,000 tables plus indexes, that is about 1-2 GiB of heap outside the memtable pool's accounting, on top of a default heap/4 pool.

**Where:** src/java/org/apache/cassandra/utils/memory/SlabAllocator.java:89 (charges size), :139 (allocates uncharged 1 MiB region), :51; config/Config.java:865-870 (count guardrails off)

## OC-371

**Case file:** `sstable_size_in_mb-leveledcompactionstrategy-configuredmaxsstablesize--autonomous` · **Agent:** guided · **Patterns:** CP-15, CP-7, CP-9

Holder: per-SSTable state (SSTableReader and metadata objects on heap; bloom filter, index summary and compression offsets in native memory; at least one mmap per index file under the default disk_access_mode mmap_index_only, Config.java:122). Why nothing stops it: the per-table file-size option is checked only for >= 1 (LCS sstable_size_in_mb, LeveledCompactionStrategy.java:580-583) and gets only a log warning below 50 (:81-83). The same holds for UCS: target_sstable_size has a 1 MiB floor (Controller.java:504-510), and min_sstable_size 0 disables the size floor (Controller.java:607-609); shards then go up to base_shard_count << 20. Nothing caps the SSTable count per node, so the count is data / file size. Rough size: at 1 MiB files a node with 64 GiB has about 65k SSTables. Their mmaps alone pass the Linux default vm.max_map_count of 65530, and a failed mmap surfaces as 'Map failed' (OutOfMemoryError). At 1 TiB (about 1M SSTables) the per-SSTable heap and native state, several KiB each, comes to several GB. Covers sstable_size_in_mb-leveledcompactionstrategy-configuredmaxsstablesize-2--autonomous and min_sstable_size-validateoptions-sizeinbytes--autonomous as well (same mechanism, filed once).

**Where:** src/java/org/apache/cassandra/db/compaction/LeveledCompactionStrategy.java:580-583 (only >=1), :81-83 (warn only); db/compaction/unified/Controller.java:504-510, :607-609, :264-345; config/Config.java:122

## OC-372

**Case file:** `min_sstable_size-validateoptions-sizeinbytes--autonomous` · **Agent:** guided · **Patterns:** CP-7, CP-16

Holder: ShardedMultiWriter, the UCS flush writer. It allocates an array of one SSTableWriter slot per shard (ShardedMultiWriter.java:95) and opens a new writer at each shard boundary (:142). It keeps every writer open, with its data, index and compression buffers (64 KiB on-heap SequentialWriter buffer by default, SequentialWriterOption.java:106-108, plus chunk and compressed buffers) and its off-heap bloom filter and index-summary builders, until finish() at the end of the flush (:149-158). Why nothing stops it: the shard count comes from getNumShards(flushDensity), and with min_sstable_size=0 (allowed, Controller.java:607-609) and a small target_sstable_size (floor 1 MiB) it is limited only by base_shard_count << 20 and by the partition count. No limit applies to the total of open-writer buffers. Rough size: about 150-250 KiB per open writer. A 1 GiB flush with target 1 MiB and sstable_growth 0 gives about 1k writers, about 200 MB per flushing table, times memtable_flush_writers in parallel. Lower confidence: the flushDensity scaling (shardSetCoverage / localSpaceCoverage, UnifiedCompactionStrategy.java:272) was not resolved.

**Where:** src/java/org/apache/cassandra/db/compaction/unified/ShardedMultiWriter.java:95, :142, :149-158; db/compaction/UnifiedCompactionStrategy.java:272-274; db/compaction/unified/Controller.java:264-345

## OC-373

**Case file:** `excess_waste_offset-updatewastedallocationtracker-delta--autonomous` · **Agent:** guided · **Patterns:** CP-6, CP-11, CP-14

Holder: memtable pool bytes cloned by failed CAS attempts on a hot partition, plus allocation past the pool limit while the write OpOrder group is blocking. Each optimistic attempt clones the update's values through the allocator (BTreePartitionUpdater.java:126-132). The clone is charged at clone time (SlabAllocator.java:89) and never refunded when the CAS fails, and small values stay inside the memtable's slab regions until the memtable is discarded. Why nothing stops it: (1) the 'pessimistic' lock is on a per-call Updater (AtomicBTreePartition.java:120-123, 157), so retries continue without bound (stage 4: 94% of locked attempts failed; contended runs charged 2-5x a single-threaded run; allocation 33.6-36.8 GB for 4.1 GiB payload); (2) once a flush barrier makes the op group blocking, MemtableAllocator.allocate charges with no limit check (MemtableAllocator.java:180-183). Retries in that window are therefore admitted past memtable_heap_space (default heap/4), bounded only by barrier duration x concurrent_writes (32) x retries x update size. Stage 4 saw on-heap at flush above the cleanup threshold but did not measure the overshoot during barriers. Rough size: up to tens to hundreds of MB past the pool per barrier with 16 MiB mutations on a hot partition; not measured.

**Where:** src/java/org/apache/cassandra/utils/memory/MemtableAllocator.java:180-183 (blocking group bypasses limit); db/partitions/AtomicBTreePartition.java:153-170, :157 (per-call lock, retry loop); utils/memory/SlabAllocator.java:89 (charged at clone, not refunded)

## OC-374

**Case file:** `last_valid_segment_row_id-exceedssegmentlimit-sstablerowid--autonomous` · **Agent:** autonomous · **Patterns:** —

SAI segment-build heap budget is a fixed 1024 MiB that does not scale with heap, and the counted bytes run well below real heap. Holder: SegmentBuilder/SegmentTrieBuffer of every SSTableIndexWriter (initial index builds, rebuilds, compactions), all sharing one static NamedMemoryLimiter. Why nothing stops it: the default is a literal 1024 MiB (StorageAttachedIndexOptions DEFAULT_SEGMENT_BUFFER_MB) checked only against the configured maximum of 32768 MiB, never against -Xmx. The limiter only counts (increment/decrement, no blocking) and is checked only at the next addTerm. The row-id cap (about 1.07e9 ids) never binds first. Rough size at defaults: cassandra-env.sh sets heap to RAM/2, so on a 4 GB host (2 GiB heap) the build buffer alone is 50% of heap, and memtable_heap_space (heap/4) brings it to 75% before any accounting slack. Stage-4 cluster evidence on a 4 GiB heap: sampled heap peaks of 3.9-4.0 GB at a 256 MiB or 1024 MiB buffer, against 2.9 GB at 16 MiB. That is about 1 GB more heap for about 250 MB more counted, so real is roughly 3-4x counted. Builder bytes were 2.4-3.5 KB per 1000-byte term.

**Where:** src/java/org/apache/cassandra/config/StorageAttachedIndexOptions.java:26,35,39-45; src/java/org/apache/cassandra/index/sai/disk/v1/V1OnDiskFormat.java:126-129; src/java/org/apache/cassandra/index/sai/disk/v1/SSTableIndexWriter.java:225,235,245-261; src/java/org/apache/cassandra/index/sai/utils/NamedMemoryLimiter.java:53-75; conf/cassandra-env.sh:58-66

## OC-375

**Case file:** `max_compaction_flush_memory_in_mb-getmode-maxmembytes--autonomous` · **Agent:** autonomous · **Patterns:** —

Full SASI OnDiskIndexBuilders pile up in an unbounded flush queue. Holder: each builder swapped out by scheduleSegmentFlush; the closure keeps it until a SASI-General thread finishes builder.finish(). Why nothing stops it: Index.add submits a flush task whenever the estimate crosses the cap and immediately starts a new builder. The executor has 8 threads, is shared JVM-wide by every compaction and index build of every SASI index, and its queue has no bound or back-pressure. The cap bounds each builder, not the sum of queued builders. Rough size at defaults: one builder is about 0.15 GiB of estimate times about 1.8 real/estimate, so about 290 MB. With concurrent_compactors times SASI indexes producers outrunning 8 flushers, every queued builder adds about 290 MB; 10 queued is about 2.9 GB. Stage 4 saw 512 live builders and 503 queued tasks at the 1 MiB cap (939 MB). Requires sasi_indexes_enabled: true, which is off by default.

**Where:** src/java/org/apache/cassandra/index/sasi/disk/PerSSTableIndexWriter.java:63-73,247-250,254-278,349-352; src/java/org/apache/cassandra/index/sasi/disk/OnDiskIndexBuilder.java:177-196

## OC-376

**Case file:** `max_compaction_flush_memory_in_mb-getmode-maxmembytes--autonomous` · **Agent:** autonomous · **Patterns:** —

The memtable-flush path ignores the option and uses a hard-coded 1 GiB estimate per SASI index per flushing SSTable. The flush builders are not charged to the memtable pool. Holder: an OnDiskIndexBuilder per indexed column in the PerSSTableIndexWriter of each memtable flush (and further builders queued on the equally unbounded SASI-Memtable executor). Why nothing stops it: maxMemorySize returns 1073741824L for OperationType.FLUSH regardless of heap or option. The estimate counts 108 B per add plus 112 B + term per new term, about 1.8x under real heap. Nothing charges this to memtable_heap_space. Rough size at defaults: per indexed row and index, about 220 B estimated (about 400 B real), against a memtable row of a similar or smaller size. A table with k SASI indexes can need about k x 2 times the flushing memtable's own size, up to about 1.8 GiB real per index, times memtable_flush_writers (2). For example, 4 indexes on a 680 MB flushing memtable (8 GiB heap) come to several GB. Requires SASI to be enabled.

**Where:** src/java/org/apache/cassandra/index/sasi/disk/PerSSTableIndexWriter.java:72-73,201,365-369; src/java/org/apache/cassandra/index/sasi/disk/OnDiskIndexBuilder.java:177-196

## OC-377

**Case file:** `max_recursive_key_length-addterm-term--autonomous` · **Agent:** autonomous · **Patterns:** —

The SAI memtable index keeps PrimaryKey objects that point at the uncloned partition key and clustering of each incoming update, but charges only 36 B per key to the memtable. Holder: the ConcurrentSkipListSet in PrimaryKeys inside each TrieMemoryIndex, which lives until the memtable is flushed and discarded. The indexer is built from update.partitionKey() and is given the original row (insert), not the memtable's clone, so the PrimaryKey keeps the deserialized DecoratedKey, Token, ByteBuffer and byte[], and for wide tables the Clustering, ByteBuffer[], ByteBuffers and byte[]. These duplicate what the memtable already cloned and charged. Why nothing stops it: TrieMemoryIndex.add returns only trie delta + reducer delta; PrimaryKeys.add returns the constant SET_ENTRY_OVERHEAD (36 B). adjustMemtableSize charges only that, so memtable_heap_space and the cleanup threshold do not see the PrimaryKey (about 32 B per index) or the duplicated key and clustering objects (about 120 B + key bytes per partition, about 120 B + clustering bytes per row). Rough size at defaults: about 250-300 B uncounted per indexed row for a small wide table, against about 200-250 B counted, so real memtable heap is about 2x the heap/4 budget (about heap/2), on top of flushing memtables.

**Where:** src/java/org/apache/cassandra/db/partitions/BTreePartitionUpdater.java:128-129; src/java/org/apache/cassandra/index/SecondaryIndexManager.java:1455-1462; src/java/org/apache/cassandra/index/sai/memory/TrieMemoryIndex.java:94-126,364-378; src/java/org/apache/cassandra/index/sai/utils/PrimaryKeys.java:38,45-48; src/java/org/apache/cassandra/index/sai/StorageAttachedIndex.java:990-1007

## OC-378

**Case file:** `no_constraint-shouldusebruteforce-numrows--autonomous` · **Agent:** autonomous · **Patterns:** —

The brute-force branch of a token-range-restricted ANN search allocates for the whole row range, and the cut-over is a cost heuristic, not a memory budget. Holder: SegmentRowIdOrdinalPairs int[2*nRows] (8 B/row) plus NeighborQueue(size) (about 8 B/row). The two-pass path keeps both in BruteForceRowIdIterator until the result iterator is closed, per segment and per query. Why nothing stops it: shouldBruteForce = nRows <= maxBruteForceRows. maxBruteForceRows is 4 x observedRatio x expectedNodesVisited, which grows with log(limit)^2 and with the adaptive observed/expected ratio (which counts resumed searches) and has no upper bound other than the formula. Rough size at defaults: at LIMIT 1000 (MAX_TOP_K) on a 10M-row segment, ranges up to about 2.5M rows go brute force, so about 40 MB per segment per query. Summed over segments, about 16 B per vector row in the queried range (10M rows is about 160 MB per query), times concurrent_reads 32, can reach GBs.

**Where:** src/java/org/apache/cassandra/index/sai/disk/v1/segment/VectorIndexSegmentSearcher.java:153-172,239-276,353-371; src/java/org/apache/cassandra/index/sai/disk/v1/vector/SegmentRowIdOrdinalPairs.java:41-46,100-118; src/java/org/apache/cassandra/index/sai/memory/VectorMemoryIndex.java:275-286

## OC-379

**Case file:** `no_constraint-shouldusebruteforce-numrows--autonomous` · **Agent:** autonomous · **Patterns:** —

Per-thread, per-segment SparseFixedBitSet cache that is never removed. Holder: the ThreadLocal cachedBitSets on each VectorIndexSegmentSearcher. Each read thread that runs a restricted or hybrid graph search gets a SparseFixedBitSet(graph.size()) per segment. It is only clear()-ed and reused, never remove()-d, not even in close(). Entries stay in each thread's ThreadLocalMap until the ThreadLocal is collected and expunged. Why nothing stops it: no size limit, and no cleanup on segment close. Rough size at defaults: if block arrays are kept after clear() (Lucene's SparseFixedBitSet does this; jvector's copy was not verified), the retained heap per (thread, segment) is up to the bits ever set, up to graph.size()/8 B. With 32 read threads and 100M vectors across open segments that is up to about 400 MB, plus stale entries for compacted-away segments.

**Where:** src/java/org/apache/cassandra/index/sai/disk/v1/segment/VectorIndexSegmentSearcher.java:81,93,228-233,331,389-392

## OC-380

**Case file:** `none-addterm-term_remaining--autonomous` · **Agent:** autonomous · **Patterns:** —

The SAI segment-build limiter is only a counter, so it does not stop allocations that happen while a builder is below its share. Holder: currentBuilder (SegmentTrieBuffer: InMemoryTrie + PackedLongValues builders) for each column index being built. Why nothing stops it: NamedMemoryLimiter.increment never blocks. Flushing is checked only at the next addTerm and only when global usage > limit AND this builder >= limit / ACTIVE_BUILDER_COUNT. minimumFlushBytes is a single static rewritten on each builder creation and release; release uses getAndDecrement, so it divides by the pre-decrement count. Each builder's bytes stay charged until its synchronous flush ends, while flush-time copies (PackedLongValues.build per term, and for vectors the PQ-encoded byte[][] of n x (dim/2+16) B in OnHeapGraph.writePQ) are never counted. Rough size at defaults: the fixed 1 GiB budget (not scaled to heap; 50% of the 2 GiB heap on a 4 GB host) plus uncounted flush-time copies, for example about 120 MB of PQ codes for a 1 GiB 768-dim vector segment.

**Where:** src/java/org/apache/cassandra/index/sai/disk/v1/SSTableIndexWriter.java:205-262,264-295; src/java/org/apache/cassandra/index/sai/disk/v1/segment/SegmentBuilder.java:53,149,211-214,230-237; src/java/org/apache/cassandra/index/sai/utils/NamedMemoryLimiter.java:53-63; src/java/org/apache/cassandra/index/sai/disk/v1/vector/OnHeapGraph.java:370-397

## OC-381

**Case file:** `none-readfully-dest_length--autonomous` · **Agent:** autonomous · **Patterns:** —

PQ-compressed vectors of every open vector segment are loaded fully onto the heap and held for the life of the SSTable index. Holder: the DiskAnn.compressedVectors field, filled by CompressedVectors.load through the RandomAccessReaderAdapter (codebooks via readFully(float[]), codes via readFully(byte[])). The writer encodes one byte[] of M = dimension/2 bytes per vector whenever a segment has >= 1024 vectors. Why nothing stops it: no setting bounds it. It is not charged to any cache or limiter, and DiskAnn.ramBytesUsed() (indexFileCacheSize) reports only the graph cache, not these codes. It grows with the number of indexed vectors on the node, and is doubled transiently while compaction has both input and output SSTables open. Rough size at defaults: about dim/2 + 16 B per vector. A 768-dim vector is about 400 B, so 10M vectors on a node is about 4 GB of heap; 1536-dim is about 7.8 GB.

**Where:** src/java/org/apache/cassandra/index/sai/disk/v1/vector/DiskAnn.java:51,62-71,77-80; src/java/org/apache/cassandra/index/sai/disk/v1/vector/OnHeapGraph.java:72,370-397; src/java/org/apache/cassandra/index/sai/disk/v1/vector/RandomAccessReaderAdapter.java:46-79

## OC-382

**Case file:** `trie_2gb_hard_limit-allocateblock-leadbit--autonomous` · **Agent:** autonomous · **Patterns:** —

InMemoryTrie reports allocatedPos, not the capacity of the buffers it has allocated. Its buffers double, so up to about half of a trie's real memory is never charged. Holder: the on-heap (heap_buffers default) tries of SAI SegmentTrieBuffer (charged to the 1 GiB segment-build limiter) and of TrieMemoryIndex (charged to memtable_heap_space via markExtraOnHeapUsed). Why nothing stops it: allocateBlock allocates a new chunk of 256<<leadBit bytes, equal to everything allocated so far, when allocatedPos enters it, but sizeOnHeap adds only allocatedPos plus an empty-array size per chunk. Content AtomicReferenceArrays (16<<leadBit) are counted as contentCount x refSize. The SAI tries have no soft threshold (only TrieMemtable polls reachedAllocatedSizeThreshold). Rough size at defaults: real is up to about 2x counted per trie. A segment builder whose trie crosses 512 MiB allocates a 512 MiB chunk charged as 32 B, so about 1 GiB real against about 0.5 GiB counted. Across all builders, up to about 1 GiB extra on top of the 1 GiB budget; similarly up to about 2x the SAI share of memtable_heap_space.

**Where:** src/java/org/apache/cassandra/db/tries/InMemoryTrie.java:140-159,162-175,969-982; src/java/org/apache/cassandra/db/tries/InMemoryReadTrie.java:207-234; src/java/org/apache/cassandra/index/sai/disk/v1/segment/SegmentTrieBuffer.java:48,57-78; src/java/org/apache/cassandra/index/sai/memory/TrieMemoryIndex.java:81,108-126

## OC-383

**Case file:** `trie_2gb_hard_limit-allocateblock-leadbit--autonomous` · **Agent:** autonomous · **Patterns:** —

The SAI RowMapping off-heap trie built at every memtable flush of an SAI table is charged to nothing, and its direct buffers are never cleaned explicitly. Holder: RowMapping.rowMapping, an InMemoryTrie<Long>(OFF_HEAP) with one PrimaryKey -> row-id entry for each row written by the flush, plus boxed Long content on heap. Why nothing stops it: no limit or soft guard is applied. Unlike TrieMemtable (discardBuffers at TrieMemtable.java:173), the direct buffers are not freed; they go only when GC collects the DirectByteBuffers. Memory is also counted as allocatedPos while capacity doubles. Rough size at defaults: about 40-60 B off-heap (up to 2x with doubling slack) plus about 20 B heap per flushed row. A 4.5M-row flush (about 680 MB memtable at 8 GiB heap) is about 250-450 MB direct per flushing SSTable, times memtable_flush_writers (2). This counts against MaxDirectMemorySize = RAM/4 (cassandra-env.sh), which is shared with other direct buffers.

**Where:** src/java/org/apache/cassandra/index/sai/disk/RowMapping.java:75,85-90,155-159; src/java/org/apache/cassandra/index/sai/disk/StorageAttachedIndexWriter.java:86,208,280; src/java/org/apache/cassandra/db/tries/InMemoryTrie.java:186-196; conf/cassandra-env.sh:59,66

## OC-384

**Case file:** `trie_2gb_hard_limit-allocateblock-leadbit--autonomous` · **Agent:** guided · **Patterns:** CP-1, CP-8

TrieMemtable charges the memtable pool with the change in InMemoryTrie.allocatedPos (sizeOffHeap/sizeOnHeap), but allocateBlock allocates each buffer whole, and buffers double in size (256 << leadBit). So the pool is charged for the bytes used, not for the buffer capacity held. Just after a power-of-two boundary the trie holds up to about 2x what was charged. Stage 4 measured this: at the 512 MiB threshold the direct pool held 1,073,749,763 B while allocatedPos was about 537 MB, and once allocatedPos passes 1 GiB the trie holds the full 2^31-256 B. There is one trie per shard (shard count defaults to the CPU count) per table, and every one carries this slack. Nothing measures capacity, so memtable_heap_space / memtable_offheap_space (default 1/4 heap each) can be exceeded by up to about 2x in real heap or direct memory. On-heap (heap_buffers) has the same gap, because sizeOnHeap adds allocatedPos, not the buffer length.

**Where:** src/java/org/apache/cassandra/db/tries/InMemoryTrie.java:151 (allocate whole buffer), :969-981 (sizeOffHeap/sizeOnHeap = allocatedPos); src/java/org/apache/cassandra/db/memtable/TrieMemtable.java:484 (pool adjust by allocatedPos delta)

## OC-385

**Case file:** `block_packed_max_block_size-checkblocksize-blocksize--autonomous` · **Agent:** guided · **Patterns:** CP-15, CP-7

Every SSTable with SAI loads its row-to-token BlockPackedReader at open, and that reader keeps three arrays of numBlocks = rows/128 entries on heap (byte + long + long, 17 B per 128 rows). WidePrimaryKeyMap also loads a partition-to-size reader, and KeyLookup loads monotonic readers. This is per-SSTable state with no count or total cap: about 0.13 B per row, so roughly 133 MB of heap at 1e9 indexed rows per node. It is not counted in any SAI memory metric, and only the heap bounds it.

**Where:** src/java/org/apache/cassandra/index/sai/disk/v1/bitpack/BlockPackedReader.java:57-60; src/java/org/apache/cassandra/index/sai/disk/v1/SkinnyPrimaryKeyMap.java:87-89; WidePrimaryKeyMap.java:82

## OC-386

**Case file:** `block_packed_max_block_size-checkblocksize-blocksize--autonomous` · **Agent:** guided · **Patterns:** CP-13

NumericValuesMeta.valueCount is a long read from the on-disk SAI metadata. It sizes three numBlocks-length arrays in BlockPackedReader and MonotonicBlockPackedReader before it is checked against the component's file length. Only blockSize is range-checked, and numBlocks only guards int overflow. A corrupt or mismatched META with blockSize 64 and a large valueCount asks for up to about 2^31 blocks x 17 B (about 36 GiB) when the SSTable index is opened, which ends in OutOfMemoryError, not a rejected component.

**Where:** src/java/org/apache/cassandra/index/sai/disk/v1/bitpack/NumericValuesMeta.java:33; BlockPackedReader.java:57-60; MonotonicBlockPackedReader.java:55-59; SAICodecUtils.java:146-160

## OC-387

**Case file:** `none-addterm-term_remaining--autonomous` · **Agent:** guided · **Patterns:** CP-1, CP-9, CP-7

The SAI segment-build limiter is charged with SegmentTrieBuffer.memoryUsed() = trie.sizeOnHeap() + postings. The trie's BufferType comes from memtable_allocation_type. With offheap_objects or offheap_buffers (conf/cassandra_latest.yaml ships offheap_objects), the trie buffers that hold every term's bytes are direct memory and are not counted at all: sizeOnHeap omits allocatedPos for OFF_HEAP. The limiter then sees only the postings, so a builder for a text index grows its trie until the 2 GB hard limit (SpaceExhaustedException). With heap_buffers it counts allocatedPos, not the doubling buffer capacity, so the trie can hold up to about 2x what was counted (about 2 GiB held at the 1 GiB default). Builders (one per index per concurrent compaction or index build) multiply this: N builders x up to 2 GiB of direct memory (bounded only by MaxDirectMemorySize, which defaults to -Xmx) or heap.

**Where:** src/java/org/apache/cassandra/index/sai/disk/v1/segment/SegmentTrieBuffer.java:48 (BufferType from memtable_allocation_type), :59 (memoryUsed = sizeOnHeap + postings); src/java/org/apache/cassandra/db/tries/InMemoryTrie.java:975-981, :151

## OC-388

**Case file:** `none-addterm-term_remaining--autonomous` · **Agent:** guided · **Patterns:** CP-8, CP-6, CP-11

sai_options.segment_write_buffer_size defaults to a fixed 1024 MiB and does not scale with the heap. It is in addition to memtable_heap_space (1/4 heap) on the same heap. On the default heap sizing of a small node (e.g. 2 GB heap on 8 GB RAM) the SAI build buffer alone is 50% of the heap. The limiter never blocks or refuses: increment only adds. Flushing needs both global usage > limit and the builder >= limit/activeBuilders (a static, last-writer-wins value). The check runs only on the next addTerm, after all analyzer tokens of the current value were added. So the default can be passed before any flush.

**Where:** src/java/org/apache/cassandra/config/StorageAttachedIndexOptions.java:26; src/java/org/apache/cassandra/index/sai/disk/v1/V1OnDiskFormat.java:126-129; src/java/org/apache/cassandra/index/sai/disk/v1/SSTableIndexWriter.java:225-235, :248; src/java/org/apache/cassandra/index/sai/utils/NamedMemoryLimiter.java:58-63; SegmentBuilder.java:149

## OC-389

**Case file:** `last_valid_segment_row_id-exceedssegmentlimit-sstablerowid--autonomous` · **Agent:** guided · **Patterns:** CP-1, CP-8

Measured gap between the SAI segment-build limiter and the heap (stage-4 cluster tier, 4 GiB heap, one 3.93M-row sstable of 1000-byte random text). The limiter peaked at 16.8 MB, 268 MB and 1,074 MB at segment_write_buffer_size 16, 256 and 1024 MiB. Heap after GC peaked at 496 MB, 4,063 MB and 4,067 MB. So already at a 256 MiB setting (268 MB counted) the heap after GC was at the 4 GiB maximum, and the setting did not hold the builder's real heap. Possible holders the limiter does not count: the InMemoryTrie buffer capacity versus allocatedPos (up to 2x), objects not in sizeOnHeap or PackedLongValues.ramBytesUsed, and flush-time writer state (LiteralIndexWriter over segmentTrieBuffer.iterator()). G1 floating garbage is a partial alternative, which stage 4 named. At the 1 GiB default on a 4 GiB heap this is an OOM risk during index build or compaction. Same limiter as none-addterm-term_remaining--autonomous.

**Where:** src/java/org/apache/cassandra/index/sai/disk/v1/segment/SegmentTrieBuffer.java:59-78; SegmentBuilder.java:84, :196; SSTableIndexWriter.java:225, :248; stage-4 results last_valid_segment_row_id-...md section 4.1 cluster table

## OC-390

**Case file:** `no_constraint-shouldusebruteforce-numrows--autonomous` · **Agent:** guided · **Patterns:** CP-2, CP-12

A hybrid (filter + ANN ORDER BY) SAI query materializes up to cassandra.sai.vector_search.max_materialized_keys = 16000 PrimaryKeys into one list before ordering. That cap counts keys, not bytes. Each key eagerly holds its partition key bytes (SkinnyPrimaryKeyMap reads them from disk) and, for wide tables, its clustering. Partition keys can be up to 64 KiB, so one query can hold about 16000 x 64 KiB = 1 GiB, plus a filtered keysInRange copy, int[2n] pairs and NeighborQueue(n) per sstable index. concurrent_reads = 32 such queries can run at once. Typical small keys give only a few MB per query.

**Where:** src/java/org/apache/cassandra/index/sai/plan/QueryController.java:96, :392, :444-452; src/java/org/apache/cassandra/config/CassandraRelevantProperties.java:476; src/java/org/apache/cassandra/index/sai/disk/v1/SkinnyPrimaryKeyMap.java:150; VectorIndexSegmentSearcher.java:288-299

## OC-391

**Case file:** `no_constraint-shouldusebruteforce-numrows--autonomous` · **Agent:** guided · **Patterns:** CP-14, CP-7

Each VectorIndexSegmentSearcher keeps a ThreadLocal SparseFixedBitSet sized to graph.size(). It is reused with clear(), which zeroes the bits but keeps the grown block arrays. A key-range-restricted or filtered ANN query sets bits for every ordinal in range, so each (segment, read thread) pair retains up to graph.size()/8 bytes after the query. For example, a 1M-vector segment retains about 125 KB per thread; x 32 read threads x 100 segments is about 400 MB. No count or byte cap applies, and the memory stays until the searcher (sstable) is released.

**Where:** src/java/org/apache/cassandra/index/sai/disk/v1/segment/VectorIndexSegmentSearcher.java:93, :228-232, :180-191, :331-332

## OC-392

**Case file:** `none-readfully-dest_length--autonomous` · **Agent:** guided · **Patterns:** CP-15, CP-7, CP-1, CP-13

DiskAnn loads every segment's product-quantized vectors fully onto the heap when the SSTable index opens (CompressedVectors.load reads one byte[M] per vector into a byte[][]). OnHeapGraph writes M = dimension/2 subspaces, so each vector holds dim/2 B + about 16 B of array header. Nothing caps the total across sstables and segments. The IndexFileCacheBytes metric (DiskAnn.ramBytesUsed) reports only the graph cache, not these codes. Rough size: 1536-dim vectors give about 784 B each, so 10M vectors per node is about 7.8 GB of heap; 768-dim gives about 4 GB. The vector count in the file is also checked only for >= 0 before the outer array is allocated.

**Where:** src/java/org/apache/cassandra/index/sai/disk/v1/vector/DiskAnn.java:68, :77-80; src/java/org/apache/cassandra/index/sai/disk/v1/vector/OnHeapGraph.java:374; jvector-1.0.2 CompressedVectors.load (anewarray sized by readInt)

## OC-393

**Case file:** `none-readfully-dest_length--autonomous` · **Agent:** guided · **Patterns:** CP-7, CP-15

Each segment's DiskAnn wraps the on-disk graph in a jvector CachingGraphIndex, which calls GraphCache.load(graph, 3) to cache every node within 3 hops of the entry point on the heap. At the default maximum_node_connections 16 that is up to 1+16+256+4096, or about 4.4k nodes, each with its full float vector and neighbor list: about 27 MB per segment at 1536 dimensions. It is held for every SAI vector segment of every sstable, and no count or total cap applies.

**Where:** src/java/org/apache/cassandra/index/sai/disk/v1/vector/DiskAnn.java:60; jvector-1.0.2 CachingGraphIndex.<init> (GraphCache.load(graph, 3))

## OC-394

**Case file:** `none-read-count--autonomous` · **Agent:** guided · **Patterns:** CP-9

SAI always opens its per-sstable and per-index component files with FileHandle.Builder.mmapped(true), whatever disk_access_mode is set to. Every component of every indexed sstable becomes at least one mapping (2 GiB regions). Resident pages sit outside -Xmx and MaxDirectMemorySize, and the container (memcg) charges them. SAI components can be larger than the data: stage 4 of the last_valid_segment_row_id case measured 8.2 GB of SAI components for a 4.1 GB sstable. The mapping count grows with sstables x (per-sstable components + indexes x per-index components) against vm.max_map_count (65530 by default). When it runs out, the next mmap throws 'Map failed' (OutOfMemoryError). An operator who sets disk_access_mode to standard to avoid mmap does not get that for SAI. The same mmap path serves none-readfully-dest_length--autonomous.

**Where:** src/java/org/apache/cassandra/index/sai/disk/format/IndexDescriptor.java:274, :296; src/java/org/apache/cassandra/io/util/MmappedRegions.java:44, :186

## OC-395

**Case file:** `max_recursive_key_length-addterm-term--autonomous` · **Agent:** guided · **Patterns:** CP-1

The SAI memtable index charges the memtable, through markExtraOnHeapUsed, only the change in trie allocatedPos, a PrimaryKeys object header for a new term, and a flat 36 B per added (term, key) set entry. Each entry holds a new PrimaryKey object, which references the token, the DecoratedKey and, for wide tables, the Clustering. These come from the uncloned update row, because BTreePartitionUpdater passes `insert`, not the cloned row. None of that is charged: roughly 100-200 B per indexed row per index against 36 B charged. On top of that, the trie buffers double in capacity beyond allocatedPos (up to 2x). With offheap_objects the trie's direct bytes are charged to the on-heap pool, so the off-heap pool limit never sees them. The stage-4 cluster tier fits this but is not conclusive: with 67 MB MemtableIndexBytes + 47 MB memtable data, heap after GC was 462 MB, against 285 MB for the no-index control holding 122 MB of data. TrieMemoryIndex also has no soft size guard before the 2 GB SpaceExhaustedException.

**Where:** src/java/org/apache/cassandra/index/sai/utils/PrimaryKeys.java:38, :47; src/java/org/apache/cassandra/index/sai/memory/TrieMemoryIndex.java:97, :126; src/java/org/apache/cassandra/index/sai/StorageAttachedIndex.java:1007; src/java/org/apache/cassandra/db/partitions/BTreePartitionUpdater.java:129

## OC-396

**Case file:** `max_compaction_flush_memory_in_mb-getmode-maxmembytes--autonomous` · **Agent:** guided · **Patterns:** CP-5, CP-3

When a SASI compaction or index-build builder reaches its cap, the full builder is handed to the SASI-General executor (8 threads, unbounded queue) and a new builder starts at once. The producer never waits, so queued full builders pile up. Stage 4 measured this at M = 1 MiB on a 3 GiB heap: 512 OnDiskIndexBuilder instances alive, 503 tasks pending, 939 MB live (2.9x the 16 MiB arm). The cap bounds each builder, not the sum of builders waiting to be flushed. (SASI ships disabled: sasi_indexes_enabled: false.)

**Where:** src/java/org/apache/cassandra/index/sasi/disk/PerSSTableIndexWriter.java:63-73, :250, :255-257

## OC-397

**Case file:** `max_compaction_flush_memory_in_mb-getmode-maxmembytes--autonomous` · **Agent:** guided · **Patterns:** CP-1, CP-7, CP-16

The SASI builder limit is compared with estimatedMemoryUse, a sum of fixed constants (64+48+term bytes per new term, 108 per add). Stage-4 unit readings put the real heap at 1.78-2.25x this estimate. So the default 153.6 MiB is about 275-345 MB real per index per writer, and it multiplies by indexed columns x concurrent compactions or index builds. The option itself is accepted up to 100 GiB with no relation to the heap: an arm set to 102400 MiB held 1.5 GB live on a 3 GiB heap.

**Where:** src/java/org/apache/cassandra/index/sasi/disk/OnDiskIndexBuilder.java:182, :194, :199-201; src/java/org/apache/cassandra/index/sasi/disk/PerSSTableIndexWriter.java:247; src/java/org/apache/cassandra/index/sasi/conf/IndexMode.java:186-193

## OC-398

**Case file:** `max_compaction_flush_memory_in_mb-getmode-maxmembytes--autonomous` · **Agent:** guided · **Patterns:** CP-10, CP-8

A memtable flush ignores max_compaction_flush_memory_in_mb and uses a hard-coded 1 GiB estimate per SASI index, which is about 1.8 GiB of real heap at the measured ratio. That holds for each indexed column of each flushing memtable, on the SASI-Memtable executor. A memtable of small rows bounded by memtable_heap_space (1/4 heap) can produce a builder estimate far above its own size, and several indexes or flush writers stack. On default-sized heaps of 2-8 GB a single flush's builders can approach the heap with nothing refusing.

**Where:** src/java/org/apache/cassandra/index/sasi/disk/PerSSTableIndexWriter.java:366-369

## OC-399

**Case file:** `none-allocateoversize-peer--autonomous` · **Agent:** autonomous · **Patterns:** —

NativeAllocator is used only with offheap_objects, which is not the default. The default allocator on the same memtable path is heap_buffers, i.e. SlabAllocator. On the first write to a memtable, SlabAllocator allocates a 1 MiB on-heap region but charges the pool only for the bytes requested. So the pool's used() value, which drives flushing through needsCleaning, does not see the rest of the region. A table that takes one small write holds about 1 MiB of heap, while the pool counts only a few hundred bytes. The cleaner never flushes it, memtable_flush_period_in_ms defaults to 0, and a few tiny writes do not reach commitlog_total_space. The number of tables is not capped at defaults (tables_warn/fail_threshold = -1). Rough size at defaults: N written tables x 1 MiB of hidden region, plus about 0.3 MB of eager per-table metric reservoirs. With the default heap of min(RAM/2, 15.5 GiB), for example 8 GiB on a 16 GB host, about 6,000 tables with one row each would fill the heap, while memtable_heap_space (1/4 heap) still reads near zero.

**Where:** utils/memory/SlabAllocator.java:89 (accounts size only), :139 (new 1 MiB REGION_SIZE region, :51); utils/memory/MemtablePool.java:125-128 (needsCleaning on accounted used()); db/memtable/AbstractAllocatorMemtable.java:100-102 (heap_buffers -> SlabPool); config/Config.java:524 (default heap_buffers), :865-866 (tables thresholds -1)

## OC-400

**Case file:** `schemaconstants_name_length-validatekeyspacename-keyspacename--autonomous` · **Agent:** autonomous · **Patterns:** —

The number of keyspaces and tables is not capped at defaults: keyspaces_* and tables_* guardrails are -1, and CreateTableStatement guards only when the guardrail is enabled. Every table has a fixed heap cost that does not depend on its data. TableMetrics registers about 112 metric MBeans per table, built eagerly. Each DecayingEstimatedHistogramReservoir holds two AtomicLongArrays of 165 x 2 stripes, about 5.3 KB per reservoir. The MBean names keep copies of the keyspace and table names. Stage 4 measured about 210 MB of heap after GC for 200 keyspaces with 1 table each, after flush. Under the default heap_buffers, the first write to each table also pins a 1 MiB slab region that the memtable pool does not count, so no flush releases it. Rough size at defaults: about 0.3 MB per table after flush, or about 1.3 MB per table that has one live row. A client allowed to run DDL (anyone under the default AllowAllAuthenticator) can create about 6,000 to 25,000 tables or keyspaces and fill a default 8 GiB heap. The 48-character name limit bounds none of this.

**Where:** config/Config.java:862-866; cql3/statements/schema/CreateTableStatement.java:138-145; metrics/TableMetrics.java:408; metrics/DecayingEstimatedHistogramReservoir.java:238,454; utils/memory/SlabAllocator.java:89,139; utils/memory/MemtablePool.java:125-128

## OC-401

**Case file:** `table_name_length-validatetablename-name_length--autonomous` · **Agent:** autonomous · **Patterns:** —

The table count is not capped at defaults (tables_warn/fail_threshold = -1, and the guard runs only when enabled). Each table carries a fixed heap cost that no budget counts. Per-table TableMetrics are eager, with about 112 MBeans and reservoirs of about 5.3 KB each. Under the default heap_buffers, the first write pins a 1 MiB SlabAllocator region, but the pool is charged only the requested bytes. needsCleaning and the flush logic therefore see almost nothing, and the region stays. Rough size: about 0.3 to 0.5 MB per table with no live data (stage 4: about 257 MB of heap after GC for 500 tables with 8-character names), plus 1 MiB per table with a live row. That is about 6,000 written tables to fill a default 8 GiB heap.

**Where:** config/Config.java:865-866; cql3/statements/schema/CreateTableStatement.java:138-145; metrics/TableMetrics.java:408; metrics/DecayingEstimatedHistogramReservoir.java:238,454; utils/memory/SlabAllocator.java:51,89,139; utils/memory/MemtablePool.java:125-128

## OC-402

**Case file:** `table_name_length-validatetablename-name_length--autonomous` · **Agent:** autonomous · **Patterns:** —

The table-name text is copied many times on the node. Each of the about 112 per-table metric MBean names (ObjectName and MetricName strings) carries the name, with several retained copies of each. Stage 4 measured +60.7 MB of heap for 500 tables when names went from 8 to 222 characters, about 121 KB per table and about 0.5 KB per name character per table, held in byte[]. The 222-character limit caps the cost per table, but nothing caps the table count. At defaults, 10,000 tables with long names hold about 1.2 GB of name text alone, and this adds to the per-table cost in the previous clue.

**Where:** schema/TableMetadata.java:517 (only per-name cap, 222); metrics/CassandraMetricsRegistry.java:98,123,234-263 (MBean registration with ObjectName); metrics/TableMetrics.java:408; config/Config.java:865-866

## OC-403

**Case file:** `schemaconstants_name_length-validatekeyspacename-keyspacename--autonomous` · **Agent:** guided · **Patterns:** CP-15, CP-7, CP-8

Same mechanism as the per-table metric-name candidate filed under table_name_length-validatetablename-name_length--autonomous. File it once and name both stems. Holder: per-table metric/MBean state. Each table registers about 112 metrics twice, under the Table and ColumnFamily factories, and every metric and ObjectName string embeds the keyspace name and the table name. No limit applies. The keyspace count guardrails ship off (keyspaces_warn/fail_threshold = -1), and so do the table count guardrails. The 48-character keyspace cap bounds only the per-name text. Size: stage 4 here measured +4.2 MB of heap for 200 keyspaces x 1 table when names went from 3 to 48 characters (inside the 17 MB noise band). The sibling case measured about 570 B per name character per table. So the keyspace part costs up to about 27 KB per table at 48 characters, plus the per-table baseline below.

**Where:** src/java/org/apache/cassandra/metrics/TableMetrics.java:410-411, 1290-1302; src/java/org/apache/cassandra/config/Config.java:862-866

## OC-404

**Case file:** `table_name_length-validatetablename-name_length--autonomous` · **Agent:** guided · **Patterns:** CP-15, CP-7, CP-8, CP-1

Holder: per-table heap state, mainly metric and MBean names. TableMetrics builds every metric twice, through `factory` (Table) and `aliasFactory` (ColumnFamily). Each MetricName keeps a 'ks.table' scope and a full mbean-name string, and the registry/JMX ObjectNames keep further copies. Stage 4 measured about 112 MBeans per table and about 570 bytes held per table-name character per table. Why nothing stops it: nothing charges this state to any budget. The table count guardrails ship off (tables_warn_threshold / tables_fail_threshold = -1), and the 222-character cap bounds only one name's length. Size, measured by stage 4 cluster tier (refuted the 'does not cap' estimate): 500 tables gave about 255 MB heap after GC at 8-character names and about 317 MB at 222 characters, i.e. +60.7 MB, about 121 KB per table from name text alone. At 2,000-5,000 long-named tables that is 0.25-0.6 GB of name text on a heap of a few GiB, before the per-table histograms and memtable arena (see none-allocateoversize-peer). Also applies to schemaconstants_name_length-validatekeyspacename-keyspacename--autonomous (keyspace name in the same strings).

**Where:** src/java/org/apache/cassandra/metrics/TableMetrics.java:410-411, 942, 1290-1302; src/java/org/apache/cassandra/metrics/CassandraMetricsRegistry.java:913; src/java/org/apache/cassandra/config/Config.java:865-866

## OC-405

**Case file:** `none-allocateoversize-peer--autonomous` · **Agent:** guided · **Patterns:** CP-1, CP-7, CP-9

Holder: NativeAllocator regions (offheap_objects memtables; shipped in conf/cassandra_latest.yaml:836). The memtable pool is charged the requested `size` per allocation (line 141), but the memory held is whole malloc'd regions. trySwapRegion sizes a new region as highestOneBit(minSize)<<3, capped at 1 MiB. So the first 64-128 KiB cell in a memtable mallocs a 512 KiB-1 MiB region and is charged 64-128 KiB, up to 8x. In steady state each 1 MiB region can strand a tail of up to 128 KiB, and every memtable keeps one partly empty region. Race-lost regions are stashed globally (up to 8 per size, about 16 MiB) and never freed or charged. Why nothing stops it: memtable_offheap_space sees only the requested bytes. The regions come from MemoryUtil.allocate (malloc), outside both -Xmx and MaxDirectMemorySize, and nothing counts per-region waste. Per-memtable regions multiply by tables x (live + flushing memtables), and no table count cap is on by default. Size: up to about 1 MiB uncharged native memory per active memtable. For example, 1,000 tables each taking one ~100 KiB write hold about 520 MiB native against about 100 MiB charged.

**Where:** src/java/org/apache/cassandra/utils/memory/NativeAllocator.java:141, 158-184, 186-198, 209-224

## OC-406

**Case file:** `none-allocateoversize-peer--autonomous` · **Agent:** guided · **Patterns:** CP-1, CP-7, CP-15, CP-8

Holder: SlabAllocator at the default memtable_allocation_type heap_buffers (Config.java:524; heap_buffers -> SlabPool at AbstractAllocatorMemtable.java:100-102). The first non-empty allocation in each memtable allocates a full 1 MiB heap region (ByteBuffer.allocate(REGION_SIZE), line 139), but the pool is charged only the bytes requested (line 89). Why nothing stops it: memtable_heap_space (heap/4) sees only the written bytes, so a lightly written table never reaches the flush threshold. memtable_flush_period_in_ms defaults to 0, so the region lives until a commitlog-driven flush. Region tails of up to 128 KiB per MiB are also never charged. The table count guardrails ship off (-1). Size: about 1 MiB of heap per written table per live memtable, charged near zero. 1,000 tables with a few small writes each hold about 1 GiB of heap invisible to the memtable limit (25% of a 4 GiB heap), and 2x that while a flush overlaps.

**Where:** src/java/org/apache/cassandra/utils/memory/SlabAllocator.java:51, 89, 126-147; src/java/org/apache/cassandra/db/memtable/AbstractAllocatorMemtable.java:100-102

## OC-407

**Case file:** `no_constraint-isallzero-vectorelement--autonomous` · **Agent:** guided · **Patterns:** CP-1, CP-12, CP-8

Holder: the per-element List that VectorType builds when it splits or deserializes a vector cell. split()/deserialize() pre-size `new ArrayList<>(dimension)` and, for variable-length element types, create one ByteBuffer slice (about 48 B) plus a reference per element. An element can be as small as 1 serialized byte (a vint length of 0), so a split holds about 50x the cell's serialized bytes. split() is called for the whole cell in toJSONString (line 282) and asComparableBytes (line 210). Why nothing stops it: the dimension is any positive int (VectorType.java:89), and the vector_dimensions guardrail ships off (vector_dimensions_warn/fail_threshold = -1). The write-side size limits count serialized bytes only. Size: a vector<text, ~16M> cell at the default 16 MiB max mutation size splits to about 16M slices, about 0.8-0.9 GB per materialization, times concurrent reads (32). The similarity-function path itself (composeAsFloat) checks the length before allocating and holds only 4 x dimension bytes per argument. Confidence: plausible; the reachable callers that split a whole stored cell were not traced end to end.

**Where:** src/java/org/apache/cassandra/db/marshal/VectorType.java:89, 210, 282, 587-599, 633-648; src/java/org/apache/cassandra/config/Config.java:924-925

## OC-408

**Case file:** `no_constraint-isempty-size--autonomous` · **Agent:** autonomous · **Patterns:** —

The coordinator buffers an entire unpaged SELECT result in ResultSet.rows. If the client sends page size <= 0 and the query is not an aggregate, SelectStatement takes the unpaged branch. process() then feeds every row of every partition through ResultSetBuilder.newRow into ResultSet.addRow, which appends with no check. trim(userLimit) only applies a user LIMIT, and with no LIMIT the default is NO_LIMIT. Nothing else stops this at defaults: read_thresholds_enabled=false and coordinator_read_size_fail_threshold=null, so maybeWarn/maybeFail return early; the page_size guardrail is -1 and is only checked on the paged branch. Rough size: each cell is a ByteBuffer (about 48 B of header plus the value) and each row adds an ArrayList (about 40 B plus references). So one unpaged SELECT * over a table or wide partition with about 2 GB of data on the node holds about 2+ GB of heap. ResultMessage.Rows encoding then makes another copy of similar size. That is more than a default 4-8 GB heap with 2-3 such queries (native_transport_max_threads=128).

**Where:** cassandra-5.0.9 src/java/org/apache/cassandra/cql3/statements/SelectStatement.java:338 (unpaged branch), :417-430 execute->processResults, :1004-1019 (process loop, build, trim), :1039-1061 maybeWarn/maybeFail gated by isReadThresholdsEnabled; cql3/ResultSet.java:72-75 addRow; cql3/selection/ResultSetBuilder.java:131-136 newRow->addRow; config/Config.java:526 read_thresholds_enabled=false, :528 coordinator_read_size_fail_threshold=null, :873-874 page_size_warn/fail_threshold=-1; SelectStatement.java:517 (page_size guardrail only on the paged path)

## OC-409

**Case file:** `no_constraint-istokenvalid-token_position--autonomous` · **Agent:** autonomous · **Patterns:** —

ErrorCollector.errorMsgs, an unbounded LinkedList<String>, keeps one message per lexer error for the whole parse. Every message stays live until throwFirstSyntaxError, which uses only the first. The ANTLR 3.5.2 Lexer reports every unrecognised character: Lexer.reportError has no errorRecovery suppression, and recover() consumes one char. Cassandra's Lexer.g displayRecognitionError forwards each one to ErrorCollector.syntaxError, which builds 'line 1:<pos> no viable alternative at character '#'' (about 54 chars) and adds it to the list. Only the parser's recover() is a no-op; the lexer's is not. The lexer is pulled lazily, but one nextToken() call loops over a whole run of bad characters before it returns. So a single QUERY whose text is all '#' (no lexer rule matches '#') makes one error per character before parsing fails. Nothing caps the error count; the only bound is the query length. native_transport_max_message_size defaults to min(max_mutation_size=16 MiB, in-flight limits), so about 16 MiB. Rough size: 16.7M errors x (about 72 B byte[] + 24 B String + 24 B LinkedList node) is about 2 GB retained per query. Add 16 MiB for the query String and 32 MiB for the ANTLRStringStream char[]. The in-flight byte limits charge only the 16 MiB frame, not this roughly 120x amplification. So 2-4 concurrent such requests (up to 128 native threads) exceed a default 4-8 GB heap.

**Where:** cassandra-5.0.9 src/java/org/apache/cassandra/cql3/ErrorCollector.java:52 (errorMsgs), :69-81 syntaxError adds builder.toString(), :98-102 throwFirstSyntaxError only after the parse; src/antlr/Lexer.g:51-55 displayRecognitionError -> listener.syntaxError for every lexer error; src/antlr/Parser.g:193-205 (only the parser's recover is a no-op); src/java/org/apache/cassandra/cql3/CQLFragmentParser.java:65-82 (ErrorCollector attached to lexer and parser, throw after parse); cql3/QueryProcessor.java:927 parse of the client query; transport/messages/QueryMessage.java:50 readLongString; config/DatabaseDescriptor.java:903-905, :3237-3244 (default max message size = min(max_mutation_size, in-flight limits))

## OC-410

**Case file:** `no_constraint-istokenvalid-token_position--autonomous` · **Agent:** guided · **Patterns:** CP-1, CP-2, CP-13

Holder: ErrorCollector.errorMsgs, a LinkedList<String> per parse that keeps one message for every lexer and parser syntax error, although only the first is ever used (throwFirstSyntaxError, ErrorCollector.java:100-101). Why nothing stops it: there is no cap on the number of errors. The CQL lexer (ANTLR 3.5.2 Lexer.reportError) reports every character no lexer rule matches ('#', '`', '~' are in no rule) and does not suppress repeats; it consumes one character and goes on. So a QUERY or PREPARE string of Q such characters yields Q messages like "line 1:16777215 no viable alternative at character '#'": about 54 chars, roughly 120 B on heap each with the String, byte[] and list node. The parser path also adds one message per error, with a snippet of up to 13 tokens (FIRST_TOKEN_OFFSET 10 + LAST_TOKEN_OFFSET 2), and runs query.split("\n"), a transient full copy of the query, per error. The only charge is the request's on-wire bytes in native_transport_max_request_data_in_flight. Size at defaults: native_transport_max_message_size = min(max_mutation_size 16 MiB, heap/10, heap/40) = 16 MiB for any heap of 640 MiB or more, so one request of 16 MiB of '#' holds about 16.7M x 120 B, roughly 2 GB, for the whole parse (about 120x the charged bytes). The global in-flight cap (heap/10) still admits about 25-50 such requests at a 4-8 GB heap, and up to 128 Native-Transport-Requests threads parse at once. No authentication at the default AllowAllAuthenticator.

**Where:** src/java/org/apache/cassandra/cql3/ErrorCollector.java:52 (errorMsgs), :81 and :90 (add, unbounded), :100-101 (only first used); src/java/org/apache/cassandra/cql3/CQLFragmentParser.java:66; src/java/org/apache/cassandra/cql3/QueryProcessor.java:927; src/java/org/apache/cassandra/config/DatabaseDescriptor.java:3237-3244 (default max message size)

## OC-411

**Case file:** `no_constraint-isempty-size--autonomous` · **Agent:** guided · **Patterns:** CP-12, CP-8, CP-1

Holder: ResultSet.rows (List<List<ByteBuffer>>) at the coordinator. It is built whole for an unpaged SELECT: addRow appends unconditionally, and SelectStatement takes the unpaged branch whenever page_size <= 0 (or LIMIT <= page size, or top-k). Why nothing stops it: page_size_fail_threshold = -1; coordinator_read_size_fail_threshold, local_read_size_fail_threshold and partition_size_fail_threshold are unset by default. A local (CL=ONE, coordinator is a replica) read is not subject to internode_max_message_size, and the encoded response is not charged against the in-flight limit. The heap holds the raw data plus an ArrayList per row and a ByteBuffer (about 48 B) per value, then the encoded response copy. Size: a partition of N bytes (partition size is not capped by default) gives about N plus 60-100 B per cell, then another N for the encoded response, per concurrent request (up to 128 native transport threads). A 1 GB partition read unpaged by a few clients exceeds an 8 GB heap.

**Where:** src/java/org/apache/cassandra/cql3/ResultSet.java:49 and :72 (rows, addRow unbounded); src/java/org/apache/cassandra/cql3/statements/SelectStatement.java:338 and :602 (unpaged branch); conf/cassandra.yaml:2021-2026, 2089-2090, 2121-2122 (read-size, page-size and partition-size thresholds off)

## OC-412

**Case file:** `no_constraint-handleinfilter-restriction_position--autonomous` · **Agent:** guided · **Patterns:** CP-8, CP-11, CP-12, CP-13

Holder: MultiCBuilder.elementsList, the cartesian product of the IN lists on clustering columns (valuesAsClustering), and likewise on composite partition key columns. Each combination is a new ArrayList copy, and build() then turns them into a NavigableSet<Clustering>. Why nothing stops it: the only cap is the in_select_cartesian_product guardrail, which ships off (-1) and is skipped when disabled. Even when it is enabled, it checks builder.buildSize() only after each column's product has been allocated. The query is only about 16 MiB at most, but the product is multiplicative. Size at defaults: a SELECT with c1 IN (1,000 values) AND c2 IN (100,000 values), a query of about 600 KB, builds 1e8 combinations at about 140 B each (ArrayList + Object[] + Clustering + TreeSet entry), roughly 14 GB, from one request. ArrayList.remove(0) in the loop makes it CPU-heavy (memmoves), but memory still grows to the full product within about a minute. Any user with SELECT can reach it, with no authentication at the default authenticator.

**Where:** src/java/org/apache/cassandra/cql3/restrictions/ClusteringColumnRestrictions.java:105-119 (guard at :112-113, after appendTo); src/java/org/apache/cassandra/db/MultiCBuilder.java:339-370 (addEachElementToAll product); src/java/org/apache/cassandra/cql3/restrictions/PartitionKeySingleRestrictionSet.java:95-96; src/java/org/apache/cassandra/config/Config.java:877-878 (thresholds -1)

