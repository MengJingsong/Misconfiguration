# Stage 5 wave 1 — full candidate text (2026-11-17)

Full clue and `file:line` for each `OC-` row filed from wave 1 (workflow `wf_ac0e5de7-ac6`). The candidate list row holds the first sentence.

## OC-63

**Case file:** `column_index_cache_size-indexSamples-cacheSizeThreshold--guided` · **Agent:** autonomous · **Patterns:** —

Write path keeps the whole row index of the partition on the heap, and column_index_cache_size does not limit it. Once the samples pass the 2 KiB threshold, BigFormatPartitionWriter switches to a DataOutputBuffer. From then on it serializes the IndexInfo of every 64 KiB block of the partition into that buffer, and the buffer grows by doubling. The int[] indexOffsets also grows, but only by 10 slots at a time, so a wide partition causes many copies; offsets() makes one more full copy. Nothing caps any of this except partition width. reset() keeps the grown buffer as reusableBuffer for the rest of the writer's life, so one wide partition pins its peak buffer for the whole flush or compaction. Rough size: one block per 64 KiB (DEFAULT_GRANULARITY; column_index_size is unset in the shipped yaml), and each block's IndexInfo holds the first and last clustering of that block. With about 100 B clusterings that is roughly 200 B per block, about 0.3% of the partition: about 30 MB for a 10 GiB partition, and up to 2x that while the buffer doubles. With large clustering keys (KiB-sized) it reaches tens of percent of the partition, for example several hundred MB to GBs for a 1 to 10 GiB partition. Multiply by the number of concurrent flush and compaction writers, against a heap of 8 GiB at most at defaults.

**Where:** src/java/org/apache/cassandra/io/sstable/format/big/BigFormatPartitionWriter.java:48,73 (64 KiB granularity), :93-98 (reset keeps reusableBuffer), :142-144 (indexOffsets grows by +10), :164-186 (switch to buffer mode, serialize every block), :193-205 (reuseOrAllocateBuffer), :119-124 (offsets() copy), :234-237 (offsets appended to buffer); BigTableWriter.java:102-114 (buffer handed to indexWriter.append)

## OC-64

**Case file:** `internode_application_receive_queue_capacity-acquireCapacity-queueCapacity--guided` · **Agent:** autonomous · **Patterns:** —

Inbound queue capacity and reserves are counted in serialized wire bytes, but small messages (64 KiB or less) are fully deserialized on the event loop before they are queued. Each one stays on the heap until its MUTATION-stage handler finishes, and the deserialized objects are much larger than the wire bytes. When the write stage stalls, for example when all 32 MutationStage threads are parked on the memtable allocator or the hints pool, the node keeps accepting and deserializing until the 512 MiB global reserve plus P peers x 4 MiB per connection is used. Nothing in the path bounds the real heap of these objects. Each cell becomes an ArrayCell (about 40 B object plus a byte[] of 16+n B); its serialized form is about 2-5 B. Rows add a BTreeRow and an Object[] btree on top. So a mutation of many small cells inflates about 10-20x. Rough size: 512 MiB global reserve plus 50 peers x 4 MiB = about 700 MiB wire, which is about 7-14 GiB of heap, above the default maximum heap of 8 GiB. Stage 4 confirmed that the queued small messages are live deserialized Mutations (159 held, all on heap).

**Where:** src/java/org/apache/cassandra/net/InboundMessageHandler.java:128,140 (size = inferred wire size, acquireCapacity), :148-149, :163-170 (deserialize before queueing), :190 (dispatch), :435-440 (release only after handler runs); net/AbstractMessageHandler.java:419-436 (counts bytes only); config/Config.java:257-261 (4 MiB / 128 MiB / 512 MiB); db/rows/UnfilteredSerializer.java:652 (ArrayCell per cell); db/rows/ArrayCell.java:35

## OC-65

**Case file:** `MAX_HINT_BUFFERS-switchCurrentBuffer-MAX_ALLOCATED_BUFFERS--guided` · **Agent:** autonomous · **Patterns:** —

At the buffer cap, the hint writer parks in reserveBuffers.take() while it holds the HintsBufferPool monitor, so every other MutationStage thread that writes a hint blocks on the monitor (stage 4: 1 parked and 31 blocked). Meanwhile HintRunnables keep queueing on Stage.MUTATION. Each one retains a whole Mutation until it runs. The only limit on queued hints is a count, not bytes: maxHintsInProgress = 128 x cores. checkHintOverload uses '>' and only rejects for a destination that already has hints in progress. It is called only on the coordinator write paths; the hint-on-failure and timeout path (AbstractWriteResponseHandler.onFailure -> submitHint) skips it, so the count can overshoot. Rough size: 16 cores gives 2,048 in-flight hints x mutation size. At 1 MiB mutations that is about 2 GiB of heap. The default max_mutation_size is commitlog_segment_size/2 = 16 MiB, so the count cap allows up to about 32 GiB, against a default heap of 8 GiB at most.

**Where:** src/java/org/apache/cassandra/hints/HintsBufferPool.java:113-118 (synchronized take at cap); service/StorageProxy.java:202 (maxHintsInProgress = 128*cores), :1585-1598 (count-only check), :2811 (Hint.create(mutation) on stage), :2821-2826 (submitHint queues on Stage.MUTATION); service/AbstractWriteResponseHandler.java:309-310 (hint on failure, no overload check)

## OC-66

**Case file:** `memtable_heap_space-tryAllocate-limit--guided` · **Agent:** autonomous · **Patterns:** —

With the default heap_buffers (SlabPool), the memtable pool is charged only each value's size. The 1 MiB on-heap slab Region that holds the value is not charged. Every memtable's SlabAllocator owns its own current region, so each table or index with a live memtable pins up to 1 MiB of heap beyond its accounted bytes (twice that while a flushing memtable and its replacement coexist). In addition, when a value (up to 128 KiB) does not fit in a region's tail, the tail is abandoned, so up to about 12.5% of each region is unaccounted waste. Rough size: about 1 MiB per active memtable x number of tables and secondary indexes (no table-count guardrail at defaults), plus up to about 12% of memtable_heap_space (heap/4, so about 256 MiB at an 8 GiB heap). For example, 1,000 tables with light writes gives about 1-2 GiB of heap not seen by the limit. Stage 4 checked accounted against real heap with one table only.

**Where:** src/java/org/apache/cassandra/utils/memory/SlabAllocator.java:50-51 (REGION_SIZE 1 MiB, MAX_CLONED_SIZE 128 KiB), :89 (pool charged size only), :103-110 (abandon region tail when slice does not fit), :120-123 (new 1 MiB region, uncharged), :58 (per-allocator currentRegion); db/memtable/AbstractAllocatorMemtable.java:100-102 (heap_buffers -> SlabPool); conf/cassandra.yaml:825

## OC-67

**Case file:** `memtable_offheap_space-tryAllocate-limit--guided` · **Agent:** autonomous · **Patterns:** —

Caveat: this needs memtable_allocation_type: offheap_objects. The shipped yaml uses heap_buffers, so at fully default settings this path is not reached. In that mode, memtable regions are glibc malloc blocks (JNA Native.malloc): 8 KiB to 1 MiB regions, and every cell larger than 128 KiB gets its own exact-size malloc. They are outside -XX:MaxDirectMemorySize and invisible to NMT. Freeing them on discard returns the memory to glibc, not to the OS, so with large cells the process RSS grows beyond memtable_offheap_space because of fragmentation and retention across the per-thread arenas. No limit covers it. Rough size: stage 4 measured RSS 332 MiB above the bound at the default limit (heap/4 = 1 GiB with a 4 GiB heap) and 46 MiB above at 512 MiB, with 192 KiB cells. It grows with the limit and with the number of glibc arenas (up to 8 x cores by default), so a container or host memory limit sized from the configured caps can be exceeded and the process OOM-killed.

**Where:** src/java/org/apache/cassandra/utils/memory/NativeAllocator.java:144-145 (cells >128 KiB to oversize), :186-190 (per-cell MemoryUtil.allocate), :171-183 (regions via malloc, race-loser free), :200-206 (free on discard); utils/memory/MemoryUtil.java:81-84 (Native.malloc)

## OC-68

**Case file:** `native_transport_receive_queue_capacity-acquireCapacity-queueCapacity--guided` · **Agent:** autonomous · **Patterns:** —

With the default native_transport_throw_on_overload=false, a single-frame (small) CQL request whose acquireCapacity is refused is still decoded and dispatched; it is processed with an overload flag and the connection pauses. When its response is flushed, release() calls releaseCapacity(bytes) for bytes that were never acquired. So queueSize drops by one request per refusal and that connection's allowance grows permanently. If queueSize was above capacity at that moment, the release also frees endpoint and global reserve capacity that other requests had taken. Neither native_transport_receive_queue_capacity nor native_transport_max_request_data_in_flight (heap/10) then bounds the decoded requests the node holds. Stage 4 measured this: decoded bytes ran to the client's full window (83 MB, 15x the bound) at every capacity, and every handler ended at -k x M. Rough size: protocol v5 allows up to 32,768 streams per connection with single frames up to 128 KiB, so one connection can hold about 4 GiB of decoded requests and their heap copies of values. A few connections exceed the default heap (8 GiB at most); the NTR stage queue is unbounded and the rate and queue-time limits are off by default.

**Where:** src/java/org/apache/cassandra/transport/CQLMessageHandler.java:217-256 (default path: refused request still processed), :265-271 (processRequestAndUpdateMetrics), :507-511 (release subtracts unacquired bytes); net/AbstractMessageHandler.java:461-473 (releaseCapacity, also frees reserves when above capacity), :396-410 (acquire with ticket); config/Config.java:1393 (throw_on_overload=false default), :296-302

## OC-69

**Case file:** `memtable_heap_space-tryAllocate-limit--guided` · **Agent:** guided · **Patterns:** CP-1, CP-7

Holder: the 1 MiB on-heap slab regions of the default `heap_buffers` allocator (SlabAllocator), one current region per memtable allocator, so one per table (and per legacy 2i table, live plus flushing memtable) that has taken a write since its last flush. Why nothing stops it: the pool charges only the requested cell `size` (SlabAllocator.java:89), never the region (ByteBuffer.allocate(REGION_SIZE), :139). The unused tail of the current region, and of each region dropped when a cell does not fit (up to <128 KiB each), is never counted. Table count has no cap at defaults (tables_warn/fail_threshold = -1). Because the counted usage stays tiny, no MEMTABLE_LIMIT flush fires; only a commit-log-dirty or periodic flush frees the regions. Rough size at defaults: about 1 MiB of uncounted heap per written table, up to 2 MiB during a flush. 1,000 lightly written tables come to about 1 GiB over a memtable_heap_space of heap/4 (1-2 GiB at a 4-8 GiB heap). Stage 4 measured only the unslabbed path, so this slab gap is unmeasured.

**Where:** src/java/org/apache/cassandra/utils/memory/SlabAllocator.java:89 (charge), :139 (1 MiB region allocate), :111-112 (region abandoned with its tail); src/java/org/apache/cassandra/config/Config.java:865-866 (no table cap); AbstractAllocatorMemtable.java:100-102 (default heap_buffers builds SlabPool)

## OC-70

**Case file:** `memtable_offheap_space-tryAllocate-limit--guided` · **Agent:** guided · **Patterns:** CP-9, CP-14

Holder: native memtable regions from JNA malloc (MemoryUtil.allocate), freed with MemoryUtil.free at memtable discard. Why nothing stops it: the pool's counter is released when regions are freed, but glibc keeps the freed memory in its arenas. Oversize cells (>128 KiB) each get an exact-size malloc, and per-thread arenas fragment, so process RSS does not fall at a flush. No limit sees this memory: it is outside -Xmx, outside -XX:MaxDirectMemorySize and invisible to NMT. bin/cassandra preloads jemalloc only if one is installed. Rough size at defaults (offheap_objects, as in cassandra_latest.yaml): stage 4 measured RssAnon 46 MiB and 332 MiB beyond the bound with 192 KiB cells, at 512 MiB and at the default limit. The retained native memory grows past memtable_offheap_space (heap/4) with nothing to cap it but the container.

**Where:** src/java/org/apache/cassandra/utils/memory/NativeAllocator.java:176 (region malloc), :190 (oversize malloc), :200-206 (free at discard); src/java/org/apache/cassandra/utils/memory/MemoryUtil.java:81-84 (JNA malloc); bin/cassandra:122-159 (jemalloc only if found)

## OC-71

**Case file:** `memtable_offheap_space-tryAllocate-limit--guided` · **Agent:** guided · **Patterns:** CP-8, CP-9

Holder: with offheap_objects, the off-heap memtable pool (heap/4 when unset, JNA malloc outside the direct cap) stacks with the direct pools: chunk cache min(512 MiB, heap/4), networking pool min(128 MiB, heap/16), plus the heap and the JVM's own non-heap. Why nothing stops it: each pool stays under its own cap, and no code compares their sum with RAM or the container. cassandra-env.sh sizes the heap at RAM/2 and MaxDirectMemorySize at RAM/4. This limit (RAM/8) sits outside the direct cap, so the three caps already commit 7/8 of RAM, leaving RAM/8 for metaspace, code cache and thread stacks. Rough size at defaults: at heap H <= 2 GiB the off-heap total is about 9H/16, so a 2H budget is exceeded at small heaps. Arithmetic at L = 1536 MiB: 768 + 192 + 192 + 48 + about 370 idle non-heap is about 1570 MiB, above L. This is the R1-V mechanism, as the case's own recheck records.

**Where:** src/java/org/apache/cassandra/config/DatabaseDescriptor.java:573-577 (pool defaults), :583-584 (memtable_offheap_space = maxMemory/4); conf/cassandra-env.sh:58-66 (heap RAM/2, direct RAM/4); src/java/org/apache/cassandra/db/memtable/AbstractAllocatorMemtable.java:106-108

## OC-72

**Case file:** `internode_application_receive_queue_capacity-acquireCapacity-queueCapacity--guided` · **Agent:** guided · **Patterns:** CP-1

Holder: small inbound messages (<=64 KiB), deserialized on the event loop right after acquireCapacity and held as heap objects until their stage runs the verb handler. Why nothing stops it: the check charges inferMessageSize, the on-wire bytes; the class Javadoc calls this 'a good enough proxy'. A deserialized Mutation of tiny cells holds about 15-17x its on-wire size (about 2.2x for blobs). Rough size at defaults: the 512 MiB global reserve plus 4 MiB per connection, spent on tiny-cell mutations, is about 8-9 GiB of heap, above typical heaps. This is the B6 mechanism.

**Where:** src/java/org/apache/cassandra/net/InboundMessageHandler.java:128 (inferMessageSize), :166 (deserialize on event loop); src/java/org/apache/cassandra/net/AbstractMessageHandler.java:419-438 (charge)

## OC-73

**Case file:** `internode_application_receive_queue_capacity-acquireCapacity-queueCapacity--guided` · **Agent:** guided · **Patterns:** CP-7, CP-8, CP-6

Holder: inbound large-message frames held as direct buffers from the networking BufferPool, which falls back to plain allocateDirect when full. Why nothing stops it: Q (4 MiB) applies per connection-type handler per peer and sits outside the global reserve G. E (128 MiB) applies per peer. The number of sending peers N is unbounded, and no code compares N*3*Q + min(G, N*E) with MaxDirectMemorySize (RAM/4 from cassandra-env.sh). The BufferPool overflow path does not refuse either. Rough size at defaults: 528-544 MiB at 4-8 peers, plus the 128 MiB networking pool and the other direct pools. This exceeds MaxDirectMemorySize on hosts of 2.5 GiB RAM or less, giving 'OutOfMemoryError: Direct buffer memory' while every counter stays within its contract. This is the C1 mechanism.

**Where:** src/java/org/apache/cassandra/net/InboundMessageHandlers.java:135-150 (handler per type per peer); src/java/org/apache/cassandra/net/MessagingService.java:676-680, :309-310; src/java/org/apache/cassandra/utils/memory/BufferPool.java:233-238 (overflow allocateDirect)

## OC-74

**Case file:** `native_transport_receive_queue_capacity-acquireCapacity-queueCapacity--guided` · **Agent:** guided · **Patterns:** CP-6, CP-3, CP-7

Holder: decoded CQL Message.Request objects plus their heap copies of bound values, held until the response is flushed. Why nothing stops it: in the default mode (throw_on_overload=false) a one-frame request (<128 KiB) refused for capacity is decoded and dispatched anyway, without being charged to queueSize or the reserves. Its release after the response then subtracts it unconditionally, so each refusal permanently lowers the connection's queueSize and enlarges its allowance. Connections are uncapped (native_transport_max_concurrent_connections = -1), and a v5 connection can hold about 32K stream ids. Rough size at defaults: stage-4 recheck at a 2 GiB heap measured 312, 468 and 625 MB decoded for 20, 30 and 40 connections. That is 1.45-2.91x the heap/10 global reserve, linear in connections, held on the heap while the counters reported the bound. About 70 such connections reach the 2 GiB heap.

**Where:** src/java/org/apache/cassandra/transport/CQLMessageHandler.java:223-260 (decode on refusal), :507-510 (unconditional release); src/java/org/apache/cassandra/net/AbstractMessageHandler.java:428-436 (refusal returns before charge), :461-475 (release); src/java/org/apache/cassandra/config/Config.java:289

## OC-75

**Case file:** `native_transport_receive_queue_capacity-acquireCapacity-queueCapacity--guided` · **Agent:** guided · **Patterns:** CP-1

Holder: the decoded request's bound values, each copied onto the heap as ByteBuffer.wrap(byte[]) (CBUtil.readValue), plus per-statement objects in BATCH and EXECUTE requests. Why nothing stops it: every limit (queue capacity, per-IP heap/40, global heap/10) charges header.bodySizeInBytes, the on-wire body. A value of n bytes costs 4+n on the wire but about 64+n on the heap (ByteBuffer object, byte[] header, list slot). Rough size at defaults: requests with many 1-8 byte values expand about 7-14x. The heap/10 global reserve then admits roughly 0.7-1.4x the heap in decoded requests, before the drift above.

**Where:** src/java/org/apache/cassandra/transport/CBUtil.java:443-450 (readValue copies to heap); src/java/org/apache/cassandra/transport/CQLMessageHandler.java:509 (charge = bodySizeInBytes), :390 (decode)

## OC-76

**Case file:** `native_transport_receive_queue_capacity-acquireCapacity-queueCapacity--guided` · **Agent:** guided · **Patterns:** CP-1, CP-6

Holder: JVM direct memory during default-mode multi-frame (>128 KiB) requests. Why nothing stops it: in the stage-4 L20 control (20 connections, a window of 60 x 262 KB, about 314 MB) the counters stayed at or below K_20 (about 74 MB). Even so, direct MemoryUsed rose from 144 MB to 1.34 GB (up to 9,073 buffers) and fell again. That is about 18x what the limits count, against a 2 GiB MaxDirectMemorySize. Cause not established. Candidates are the frames held by LargeMessage while the connection waits on a reserve, and BufferPool overflow allocations. The pool's UsedSize/OverflowSize gauges also reached 4.8-16.5 GB and never fell, so they are unreliable. Rough size at defaults: about 67 MB of direct memory per multi-frame connection at a 60-request window, so roughly 30 such connections would exhaust a 2 GiB direct budget.

**Where:** src/java/org/apache/cassandra/transport/CQLMessageHandler.java:516-660 (processFirstFrameOfLargeMessage), :762-771 (assembleFrame), :797-805 (onIntactFrame keeps frames); src/java/org/apache/cassandra/utils/memory/BufferPool.java:233-238

## OC-77

**Case file:** `MAX_HINT_BUFFERS-switchCurrentBuffer-MAX_ALLOCATED_BUFFERS--guided` · **Agent:** guided · **Patterns:** CP-5, CP-2, CP-10, CP-4

Holder: whole mutations on the heap inside hint tasks queued on MutationStage, plus local writes queued behind them. Why nothing stops it: at the 3-slab cap the writer parks in reserveBuffers.take() while holding the synchronized switchCurrentBuffer monitor. Every other hint writer blocks on the monitor while holding a MutationStage thread, so a stalled hint flush (for example a slow hints disk) freezes the stage while tasks keep queueing without a bound. The only backstop, checkHintOverload, counts hints, not bytes: 128 x cores. It runs only at write admission and only for destinations that already have hints in flight. Several submitHint paths skip it: hint-on-failure in AbstractWriteResponseHandler:310, the expired local mutation at StorageProxy:2654, PaxosCommit:231 and hintMutation:988. Rough size at defaults: on 32 cores, 4,096 hints x a mutation of up to max_mutation_size (16 MiB) is up to 64 GiB. With 1 MiB mutations it is about 4 GiB of heap, while the direct pool stays at 96 MiB.

**Where:** src/java/org/apache/cassandra/hints/HintsBufferPool.java:107-118 (park inside synchronized); src/java/org/apache/cassandra/service/StorageProxy.java:2822-2827 (hint task on MUTATION stage), :1585-1598 (checkHintOverload, count only), :202 (128 x cores); src/java/org/apache/cassandra/service/AbstractWriteResponseHandler.java:310

## OC-78

**Case file:** `MAX_HINT_BUFFERS-switchCurrentBuffer-MAX_ALLOCATED_BUFFERS--guided` · **Agent:** guided · **Patterns:** CP-8, CP-14

Holder: 3 x 32 MiB = 96 MiB of direct hint slabs. allocatedBuffers is never decremented, slabs are recycled rather than freed, and close() frees only the current one. Why nothing stops it: the memory is held for the process's life after the first burst. It stacks in the same direct budget with the networking pool (min(128 MiB, heap/16)), the chunk-cache pool (min(512 MiB, heap/4)), the internode receive reserves (up to 512 MiB global plus per-connection) and DataOutputBuffer scratch, and no code compares the sum with MaxDirectMemorySize (RAM/4). Rough size at defaults: the counted caps alone come to about 1.28 GiB against a 1 GiB direct budget at a 2 GiB heap. This is the S1 mechanism.

**Where:** src/java/org/apache/cassandra/hints/HintsBufferPool.java:113, :130-138; src/java/org/apache/cassandra/hints/HintsBuffer.java:77 (allocateDirect slab); src/java/org/apache/cassandra/hints/HintsService.java:79, :110; src/java/org/apache/cassandra/config/DatabaseDescriptor.java:573-577

## OC-79

**Case file:** `max_space_usable_for_compactions_in_percentage-hasDiskSpaceForCompactionsAndStreams-availableForCompaction--guided` · **Agent:** guided · **Patterns:** CP-7, CP-9

Holder: per-SSTable memory that grows with the SSTable count: off-heap bloom filters (OffHeapBitSet via Memory.allocate, JNA, outside the direct cap), per-reader heap metadata, and per-read reader buffers for each overlapping SSTable. Why nothing stops it: when disk is short, the check sheds the largest inputs one by one and finally aborts the compaction. Flushes keep producing SSTables while overlapping copies of the same partitions stay uncompacted. No limit caps the SSTable count or the bloom-filter total. Rough size at defaults: bloom_filter_fp_chance 0.01 is about 1.2 B per partition per SSTable copy, so 1e9 partitions held in about 5 uncompacted copies is about 6 GB of native memory. This is speculative, an indirect effect of the disk guard, and not measured.

**Where:** src/java/org/apache/cassandra/db/compaction/CompactionTask.java:421 (reduce scope), :441-442 (abort); src/java/org/apache/cassandra/utils/obs/OffHeapBitSet.java:48 (bloom filter Memory.allocate)

## OC-80

**Case file:** `CACHEABLE_MUTATION_SIZE_LIMIT-serialization-CACHEABLE_MUTATION_SIZE_LIMIT--guided` · **Agent:** autonomous · **Patterns:** —

Holder: each live Mutation's cachedSerializations slot, which keeps a heap byte[] copy of the serialized mutation (up to 999,999 B at the 1,000,000 B default) beside the PartitionUpdate objects. A coordinator write handler keeps the mutation through hintOnFailure and is registered with an expiry, so a mutation and its copy stay reachable until every replica answers or write_request_timeout runs out. That holds even after a CL ONE client reply has released the native in-flight byte caps. Why nothing stops it: nothing ever clears the copy (Mutation.java:75-77). No in-flight, queue or memtable cap counts it, and the property caps each copy, not their number. Rough size at defaults: about 2x the mutation's serialized bytes per live mutation, for example 1,000 live 1 MB writes held for a slow replica = about 1 GB of copies on top of the mutations themselves. During replay, up to 1,024 outstanding mutations (64 MiB counted by serialized size) each carry their copy too.

**Where:** Mutation.java:75-78, :451-463, :519, :158-161; AbstractWriteResponseHandler.java:81, :107, :309-310; RequestCallbacks.java:104; CommitLogReplayer.java:75-79, :284-326

## OC-81

**Case file:** `file_cache_size-allocateMoreChunks-memoryUsageThreshold--guided` · **Agent:** autonomous · **Patterns:** —

Holder: direct ByteBuffers handed to readers once the chunk-cache BufferPool reaches file_cache_size. Why nothing stops it: LocalPool.get() falls back to allocate(size, OFF_HEAP), an unpooled ByteBuffer.allocateDirect that only bumps overflowMemoryUsage, which has no ceiling. Every open data-file reader holds one buffer of chunk size (BufferManagingRebufferer), so demand is concurrent reads plus compaction scanners, times SSTables per read, times chunk size. Nothing caps the SSTables touched per read. On top of that, the pool's macro chunks are never freed: because partially freed chunks are queued behind new macro chunks, the pool fills to the full 512 MiB under churn even when demand is lower (stage 4: 512 MiB reserved for a 250 MiB demand). Rough size at defaults: 512 MiB permanent pool, plus overflow of 32 reads x (SSTables per read, e.g. 500 during a compaction backlog) x 64 KiB = about 1 GiB, plus compaction readers. The only backstop is MaxDirectMemorySize, which defaults to the heap size, and Netty's arenas share it (stage 4 saw +816 MiB).

**Where:** BufferPool.java:443-449, :417-431, :904-923, :233-238, :1244-1245, :1272-1281; BufferManagingRebufferer.java:45; BufferPools.java:38-39

## OC-82

**Case file:** `internode_application_send_queue_capacity-acquireCapacity-pendingCapacityInBytes--guided` · **Agent:** autonomous · **Patterns:** —

Holder: the Message/Mutation objects pinned by outbound queues. Why nothing stops it: acquireCapacity() counts canonicalSize, the serialized size at the current version, but the queue retains the deserialized in-memory form (PartitionUpdate BTree, cell objects, several times the serialized bytes for small cells), plus the CachedSerialization byte[] copy for any mutation under 1 MB. Expiry of queued messages is lazy while the link is connected and not draining, so the time bound does not reclaim them. Rough size at defaults: the counted ceiling is 3*P*4 MiB + min(P*128 MiB, 512 MiB) = 632 MiB for 10 peers (1.1 GiB for 50). At about 2-4x heap per counted byte (object plus copy) that is roughly 1.3-2.5+ GB of heap pinned by unsent messages to slow peers, none of it counted against the heap.

**Where:** OutboundConnection.java:330, :335-349, :398-433, :1045-1048; OutboundMessageQueue.java:209-220; StorageProxy.java:1517-1523; Mutation.java:451-456

## OC-83

**Case file:** `local_read_size_fail_threshold-addSize-failBytes--guided` · **Agent:** autonomous · **Patterns:** —

Holder: the replica's heap DataOutputBuffer in ReadResponse.LocalDataResponse.build(), into which every row of one read command is serialized before the response is sent. Why nothing stops it: the guard is off at defaults (local_read_size_fail_threshold null, read_thresholds_enabled false, so shouldTrackSize() is false and nothing is counted). Paging limits rows, not bytes, so one page of a wide partition (driver default 5,000 rows) is built whole. The buffer grows by doubling (x1.5 above the doubling threshold), and old and new arrays coexist during each copy. internode_max_message_size refuses the send only after the buffer exists. Rough size at defaults: 5,000 rows x 100 KiB = about 500 MB content, up to about 1-1.5 GB transient per command. With concurrent_reads = 32 such commands, that is far past any default heap.

**Where:** ReadCommand.java:656-661, :666-670; ReadResponse.java:197-203; DataOutputBuffer.java:158-182; Config.java:526, :530

## OC-84

**Case file:** `max_mutation_size-validateSize-MAX_MUTATION_SIZE--guided` · **Agent:** autonomous · **Patterns:** —

Holder: the per-thread direct scratch DataOutputBuffer that CommitLog.add() serializes every admitted mutation into. Why nothing stops it: max_mutation_size caps each entry at 16 MiB, but the buffer grows by doubling or by capacity+count to between T and about 2T. During expandToFit the old and new direct buffers coexist, and buffers over 1 MiB are freed only at close. No pool or direct-memory cap counts these buffers, and the per-thread count is set only by stage sizes: MutationStage concurrent_writes = 32, plus counter, view, hint and batchlog writers. Separately, every scratch buffer of 1 MiB or less is kept for good on each thread that used it. Rough size at defaults: 32 concurrent 16 MiB writes (reachable under native_transport_max_request_data_in_flight = heap/10) x up to 32-48 MiB = about 1-1.5 GiB of transient direct memory. That sits on top of the 16 MiB heap mutations, and MaxDirectMemorySize defaults to the heap size.

**Where:** CommitLog.java:304-311; DataOutputBuffer.java:63-92, :158-182, :184-187; Config.java:180; IMutation.java:31

## OC-85

**Case file:** `max_value_size-read-maxValueSize--guided` · **Agent:** autonomous · **Patterns:** —

Holder: the full on-heap Row built when any reader or compaction deserializes a row. Every cell of a fetched complex column is deserialized (readComplexColumn loops over all cells, each a new byte[]). Why nothing stops it: max_value_size is per cell, and max_mutation_size is per write. A row grown across many writes (for example a non-frozen map/list/set appended 1 MiB at a time, merged by compaction) has no size cap except its 32-bit serialized row size. Reads, and compaction (merged source rows plus the output row, about 2-3x), materialize it whole. Rough size at defaults: up to about 2 GiB per row, times concurrent_reads (32) plus compaction threads.

**Where:** UnfilteredSerializer.java:662-690, :647-655, :698-700; Cell.java:339; AbstractType.java:594-599

## OC-86

**Case file:** `max_value_size-read-maxValueSize--guided` · **Agent:** autonomous · **Patterns:** —

Holder: heap byte[] sized from an on-disk or wire length field by the unguarded siblings ByteBufferUtil.readWithVIntLength/readWithLength. Why nothing stops it: these paths do not compare the length with max_value_size and allocate new byte[length] before reading any byte (for example the read-response payload, a batchlog entry's encoded mutations, a saved row/key cache key, the StatsMetadata and IndexSummary first/last keys). Rough size at defaults: a corrupt or torn length allocates up to 2 GiB in one array at once.

**Where:** ByteBufferUtil.java:371-389, :444-452; ReadResponse.java:338; Batch.java:157; CacheService.java:408; StatsMetadata.java:648-649

## OC-87

**Case file:** `repair_session_space-split-maxsize--guided` · **Agent:** autonomous · **Patterns:** —

Holder: Merkle trees that the repair coordinator receives and holds per (table, common range) until differencing, plus the replicas' validation trees. Why nothing stops it: repair_session_space (heap/16) is a budget per validation, not per node. concurrent_merkle_tree_requests defaults to 0, so Scheduler.build(0) puts no limit on validation requests in flight. A repair over many tables or vnode ranges, or several concurrent repairs, holds one budget per session in flight; the shipped yaml itself warns this can OOM. Rough size at defaults: about heap/16 per concurrent session on the coordinator (RF trees of space/RF each; off-heap at about 82 B per leaf for Murmur3, on heap for order-preserving partitioners). For example 8-16 concurrent sessions = heap/2 to a full heap equivalent.

**Where:** Config.java:210; RepairCoordinator.java:127; ValidationManager.java:62-80; RepairSession.java:338-343; MerkleTree.java:747-751; conf/cassandra.yaml:842-858

## OC-88

**Case file:** `SAI_VECTOR_SEARCH_MAX_MATERIALIZE_KEYS-materializeKeysAndCloseSource-MAX_MATERIALIZED_KEYS--guided` · **Agent:** autonomous · **Patterns:** —

Holder: ScoreOrderedResultRetriever.processedKeys, a HashSet<PrimaryKey> that gains every key whose row fails the filter on the ANN (disallow) plan. Why nothing stops it: once more than 16,000 keys match, the plan switches and nothing caps the set. Its size depends on how far the matching rows lie from the query vector and is limited only by the rows on the replica and range_request_timeout (10 s). Rough size at defaults: about 200 B per key (about 144 B SkinnyPrimaryKey plus about 48 B hash node). Millions of rejected rows in 10 s = hundreds of MB to over 1 GB per query, times 32 concurrent reads.

**Where:** StorageAttachedIndexSearcher.java:645, :763-825 (adds at :782, :802); QueryController.java:390-398, :449-453

## OC-89

**Case file:** `SAI_VECTOR_SEARCH_MAX_MATERIALIZE_KEYS-materializeKeysAndCloseSource-MAX_MATERIALIZED_KEYS--guided` · **Agent:** autonomous · **Patterns:** —

Holder: the per-segment keysInRange copy and the int[2*M] SegmentRowIdOrdinalPairs built by every SSTable vector segment on the allow plan, retained by the per-segment iterators for the whole command. Why nothing stops it: MAX_MATERIALIZED_KEYS caps M, but a segment's min/max key usually spans the whole ring, so every segment allocates arrays of about M entries. The segment count S (SSTables x segments) is uncapped. Rough size at defaults: S x 16,000 x 12 B, for example 1,000 segments = about 190 MB per query, about 6 GB for 32 concurrent hybrid queries.

**Where:** VectorIndexSegmentSearcher.java:288-299; SegmentRowIdOrdinalPairs.java:40-46; QueryController.java:405-408

## OC-90

**Case file:** `file_cache_size-allocateMoreChunks-memoryUsageThreshold--guided` · **Agent:** guided · **Patterns:** CP-14, CP-8, CP-9

chunk-cache BufferPool fills to its cap whatever the demand and never gives it back. Holder: the static chunk-cache pool's 8 MiB macro chunks, which are never released (comment at :378). Why nothing stops it: getInternal() tries a NEW macro chunk before it takes partiallyFreedChunks, and a partially recycled chunk is not recycled again once it is fully free (tryRecycle :1244 checks EVICTED; tryRecycleFullyOrPartially :1272-1281), so churn grows the pool to the cap. This happens with the chunk cache off (the shipped default), because the pool still serves reader buffers. Size at defaults: min(512 MiB, H/4) of direct memory held for the JVM's life. Stage 4 measured 512 MiB reserved for a 250 MiB demand. That sits beside the networking pool min(128 MiB, H/16), Netty's arenas (+816 MiB at 200 concurrent requests, which Netty counts against its own limit) and, under cassandra_latest.yaml offheap_objects, a JNA-malloc memtable of H/4 that no JVM limit sees. Together with heap H they exceed a RAM = 2H container. This extends R1-V's sum to the cache-off default.

**Where:** src/java/org/apache/cassandra/utils/memory/BufferPool.java:419-431 (never released: :378)

## OC-91

**Case file:** `file_cache_size-allocateMoreChunks-memoryUsageThreshold--guided` · **Agent:** guided · **Patterns:** CP-6, CP-7, CP-8

Past the pool cap, buffers come from an uncapped unpooled path. Holder: LocalPool.get() returns allocate(size, OFF_HEAP) = ByteBuffer.allocateDirect, counted only in overflowMemoryUsage, which has no limit. Why nothing stops it: the refusal at :443-450 only switches the buffer to unpooled allocation. The only stop is -XX:MaxDirectMemorySize (RAM/4 from cassandra-env.sh), and the allocateDirect there has no catch (the OOM catch at :462-468 covers only the slab). Size: concurrent reads × SSTables per read × 64 KiB per buffer. At the default concurrent_reads 32 with 20 SSTables that is about 40 MiB; stage 4 measured about 250 MiB at 200 concurrent reads. It adds to the full pool in the same direct budget.

**Where:** src/java/org/apache/cassandra/utils/memory/BufferPool.java:923 -> :233-238

## OC-92

**Case file:** `max_mutation_size-validateSize-MAX_MUTATION_SIZE--guided` · **Agent:** guided · **Patterns:** CP-1, CP-7, CP-8

The commit-log serialization scratch buffer is uncounted direct memory per writer, and no limit caps the writers' total. Holder: the thread-local DataOutputBuffer.scratchBuffer (DIRECT by default) filled in CommitLog.add(). max_mutation_size (16 MiB) bounds only one entry. The buffer grows to as much as 2(M−13) ≈ 32 MiB, and for a moment 3× while old and new coexist (DataOutputBuffer.java:158-186). It is freed at close only above 1 MiB. Writers: 32 MutationStage, plus 32 CounterMutationStage and 32 ViewMutationStage threads that reach the same site (Config.java:180-182). Size at defaults: about 1 GiB for 32 writers and up to about 3 GiB for 96, against MaxDirectMemorySize = RAM/4 (1 GiB at a 2 GiB heap). That budget is shared with the chunk-cache pool (512 MiB), the networking pool, the 3 × 32 MiB hint slabs and kept DOB scratch. The 32-writer part is S1's mechanism; the counter and view writers are new and not loaded by S1.

**Where:** src/java/org/apache/cassandra/db/commitlog/CommitLog.java:306-308

## OC-93

**Case file:** `max_value_size-read-maxValueSize--guided` · **Agent:** guided · **Patterns:** CP-13, CP-10

Length-prefixed reads that skip the max_value_size check size a heap array from an untrusted length. Holder: ByteBufferUtil.read() does `new byte[length]` before readFully. It is reached from readWithVIntLength/readWithLength (about 29 call sites), which check only for a negative length. Examples: the partition key of every internode mutation and read response (UnfilteredRowIteratorSerializer.java:199), batchlog entries (Batch.java:153-157, which also does `new ArrayList<>(count)` with an unchecked count), the saved row-cache key (CacheService.java:407), and the first/last keys of IndexSummary and StatsMetadata. Why nothing stops it: only the four AbstractType.read() sites compare with max_value_size, and nothing compares the length with the bytes actually remaining. Size: up to 2 GiB per field from one damaged or crafted length from a peer or an on-disk file (ArrayList(count) up to about 8-16 GiB of reference array), allocated before the short read is detected.

**Where:** src/java/org/apache/cassandra/utils/ByteBufferUtil.java:444-452 (via :371-389)

## OC-94

**Case file:** `CACHEABLE_MUTATION_SIZE_LIMIT-serialization-CACHEABLE_MUTATION_SIZE_LIMIT--guided` · **Agent:** guided · **Patterns:** CP-1, CP-3, CP-4

Every live mutation under 1,000,000 B carries an uncounted heap copy of its serialized bytes, kept until the mutation dies. Holder: the CachedSerialization byte[] in the mutation's cachedSerializations slot, built on serialize (Mutation.java:451-456) and on receive (:518-519), and never cleared. Why nothing stops it: the internode queues and native in-flight caps charge on-wire bytes, not this copy. The send-queue charge is released at flush while the coordinator's write handler keeps the Mutation through hintOnFailure (Mutation.java:158-161, AbstractWriteResponseHandler.java:81,107) until the response or write_request_timeout. Size: N live mutations × T. For example, 1,000 live mutations of about 1 MB hold about 1 GB of copies, and blob writes double the heap per charged byte (R ≈ 2.2). This is an amplifier term inside B6 (and B8's replay queue); file it with B6 if it is judged the same mechanism.

**Where:** src/java/org/apache/cassandra/db/Mutation.java:451-456 (receive side :518-519)

## OC-95

**Case file:** `local_read_size_fail_threshold-addSize-failBytes--guided` · **Agent:** guided · **Patterns:** CP-7, CP-1, CP-2

The read size limit is per command, with no aggregate, and the response buffer is not counted. Holder: each ReadCommand's built rows plus its serialized response in a heap DataOutputBuffer (ReadResponse.java:197-203). That buffer's capacity can be up to 2× its content, and its growth copies add garbage. It outlives the command until the reply is sent or consumed. Why nothing stops it: the check is off at defaults (read_thresholds_enabled false, threshold null, Config.java:526,530), so a page is bounded only by row count. Even when enabled, the counter belongs to one command (one page, or one IN partition). Up to 32 ReadStage commands run at once, plus coordinator-local reads on up to 128 native-transport threads. Size: 32 × (page bytes × up to 2). For example, 5,000-row pages of 64 KiB rows are about 312 MiB serialized per command. This is the same mechanism as C2.

**Where:** src/java/org/apache/cassandra/db/ReadResponse.java:197-203 (counter: ReadCommand.java:715)

## OC-96

**Case file:** `local_read_size_fail_threshold-addSize-failBytes--guided` · **Agent:** guided · **Patterns:** CP-10, CP-12, CP-2

Names-filter point reads build every requested row before the size guard sees them. Holder: queryMemtableAndSSTablesInTimestampOrder() collects all requested rows into an ImmutableBTreePartition before withQuerySizeTracking wraps the iterator. Why nothing stops it: on this path the guard is post hoc even when enabled, and the IN cartesian-product guardrail is off by default (Config.java:877-878). Reads without trackWarnings (internal SelectStatement.executeLocally) and system keyspaces are never wrapped at all. Size: requested rows × row size (up to 16 MiB per row under max_mutation_size). For example, `ck IN` 100 values × 16 MiB is about 1.6 GiB in one command, before the serialized response copy.

**Where:** src/java/org/apache/cassandra/db/SinglePartitionReadCommand.java:700-707 -> :951-957

## OC-97

**Case file:** `internode_application_send_queue_capacity-acquireCapacity-pendingCapacityInBytes--guided` · **Agent:** guided · **Patterns:** CP-1, CP-3, CP-4

The send queue charges on-wire bytes and releases the charge at flush, while the mutation stays on the heap until the response or timeout. Holder: the queued Message/Mutation, then the callback (MessagingService.java:424-425) and the write handler's hintOnFailure after flush. Why nothing stops it: releaseCapacity() at flush (:445-454) returns the charge. Expiry of queued messages is lazy, so a full link that is not draining reclaims nothing by itself. Size: about 19.7× heap per charged byte for tiny-cell mutations (2.2× for blobs). The 632 MiB charged ceiling at 10 peers is about 12 GiB of heap, plus write rate × 2 s × about 213 KiB retained after flush. This is B6's mechanism, already measured.

**Where:** src/java/org/apache/cassandra/net/OutboundConnection.java:445-454 (charge: :398, :330)

## OC-98

**Case file:** `internode_application_send_queue_capacity-acquireCapacity-pendingCapacityInBytes--guided` · **Agent:** guided · **Patterns:** CP-8, CP-1

Send and receive queue defaults over-commit one shared heap. Holder: a node that is both coordinator and replica holds outbound queues of 3·P·4 MiB plus a 512 MiB global reserve, and inbound queues of 4 MiB per link, 128 MiB per peer and a 512 MiB global reserve (Config.java:250-261), all charged in on-wire bytes. Why nothing stops it: each side checks only its own reserves, and no default scales with the heap. The send path's per-peer reserve is even read from the receive-side key, so lowering the send-side key changes nothing. Size: at least 1 GiB on-wire from the two global reserves alone, which is about 17-20 GiB of heap at B6's ratio. That exceeds the default heap (min(RAM/2, 31 GiB)) on any host under about 34-40 GiB of RAM. Inferred; B6 loaded each side on separate instances.

**Where:** src/java/org/apache/cassandra/config/Config.java:250-261

## OC-99

**Case file:** `repair_session_space-split-maxsize--guided` · **Agent:** guided · **Patterns:** CP-7, CP-8

repair_session_space is a per-validation budget, and the coordinator holds the Merkle trees of every session at once. Holder: the RF direct-buffer trees per session (ByteBuffer.allocateDirect, MerkleTree.java:747-751; Murmur3 with use_offheap_merkle_trees true), kept until the job compares them. Why nothing stops it: AbstractRepairTask submits a RepairSession for every CommonRange at once, and concurrent_merkle_tree_requests defaults to 0, which gives a NoopScheduler (Config.java:210, Scheduler.java:43-47). The shipped yaml itself warns this 'can produce OOM'. Size at defaults: with num_tokens 16, RF 3 and a full non-`-pr` repair there are about 48 sessions, each holding about heap/16 × 82/200 bytes. That is about 1.2 × heap of direct memory against MaxDirectMemorySize = heap/2, and more with several tables (-j). It is timing-dependent.

**Where:** src/java/org/apache/cassandra/repair/AbstractRepairTask.java:66-69 (scheduler: Scheduler.java:43-47)

## OC-100

**Case file:** `SAI_VECTOR_SEARCH_MAX_MATERIALIZE_KEYS-materializeKeysAndCloseSource-MAX_MATERIALIZED_KEYS--guided` · **Agent:** guided · **Patterns:** CP-6, CP-4

Past the key limit the query switches to an ANN search with post-filtering, and its rejected-key set has no size bound. Holder: the processedKeys HashSet<PrimaryKey> (StorageAttachedIndexSearcher.java:645, adds at :782/:802/:816), which grows with every row that fails the filter until k rows pass. Why nothing stops it: the set is not sized or capped by L. The only stop is the query quota, range_request_timeout (10 s), at queryContext.checkpoint() (:774). Lowering L can raise a query's peak. Size: about 150 B per key × (rows read in 10 s), × 32 concurrent reads. Stage 4 measured about 830 rows/s, about 1.3 MB per query at defaults, which is small. At page-cache read rates the size is unknown: 100k rows/s would be about 150 MB per query, or about 4.8 GB across 32 reads. This is weak until that rate is measured.

**Where:** src/java/org/apache/cassandra/index/sai/plan/StorageAttachedIndexSearcher.java:645 (switch: QueryController.java:393-394)

## OC-101

**Case file:** `Integer_MAX_VALUE-maybeAddEntry-Integer_MAX_VALUE--guided` · **Agent:** guided · **Patterns:** CP-9, CP-11, CP-1

Index summaries are native memory outside every JVM limit, and their total is checked only by an hourly redistribution that counts less than they hold. Holder: the per-SSTable IndexSummary regions, allocated with JNA Native.malloc (outside -Xmx and MaxDirectMemorySize). Why nothing stops it: index_summary_capacity (5% of heap, DatabaseDescriptor.java:867-869) is enforced only by redistribution every 60 min (Config.java:543). That redistribution sums getOffHeapSize(), which leaves out the untrimmed capacity that the rebuild and loading paths keep (BigSSTableReaderLoadingBuilder.java:229-230). New flush, compaction and streaming SSTables are sampled at full density in between. Size: keys/128 × (K+12) per SSTable, plus up to about 2.5× transiently during growth. For example, 2 billion 36-byte keys is about 750 MB of native memory against a 5%-of-heap target of about 400 MB at an 8 GiB heap. The untrimmed reservation is mostly address space rather than RSS.

**Where:** src/java/org/apache/cassandra/io/sstable/format/big/BigSSTableReaderLoadingBuilder.java:229-230 (cap: DatabaseDescriptor.java:867-869; interval: Config.java:543)

## OC-102

**Case file:** `batch_size_fail_threshold-verifyBatchSize-failThreshold--guided` · **Agent:** autonomous · **Patterns:** —

A batch's whole object graph is built on the coordinator heap before batch_size_fail_threshold is checked, and nothing upstream counts those heap bytes. Decode copies every bound value into its own heap byte[] plus a HeapByteBuffer. getMutations then builds every PartitionUpdate, Row and Cell, and each Mutation is serialized once more for max_mutation_size. Only after all that does verifyBatchSize compare dataSize with 50 KiB and throw. The in-flight reserves charge only the batch's wire bytes: heap/10 globally, heap/40 per IP, plus 1 MiB of exclusive queue capacity per connection. Stage 4 measured about 2x the batch's bytes per rejected batch with large values (33.9 MB for a 16 MiB batch). With tiny values (5 wire bytes each), one 16 MiB batch decodes to about 3.3M values at roughly 75 B each, about 250 MB, plus about the same again in Cell/Row objects. At an 8 GiB heap the global reserve (about 819 MiB of wire bytes) admits about 51 such batches at once, which is tens of GB of heap. That is enough for an OOM before any of them is rejected as 'Batch too large'.

**Where:** src/java/org/apache/cassandra/transport/messages/BatchMessage.java:56-73; src/java/org/apache/cassandra/transport/CBUtil.java:480,669-670; src/java/org/apache/cassandra/cql3/statements/BatchStatement.java:428,439,352-358; src/java/org/apache/cassandra/cql3/statements/SingleTableUpdatesCollector.java:112; src/java/org/apache/cassandra/db/Mutation.java:171; src/java/org/apache/cassandra/config/DatabaseDescriptor.java:651,656

## OC-103

**Case file:** `coordinator_read_size_fail_threshold-shouldReject-thresholdBytes--guided` · **Agent:** autonomous · **Patterns:** —

Nothing caps the size of a coordinator's read result at the defaults. read_thresholds_enabled is false and coordinator_read_size_fail_threshold and local_read_size_fail_threshold are both null, so the guard returns at once. Page size counts rows, not bytes, and a client can turn paging off. For an unpaged SELECT of a wide partition (or a page of large rows), the coordinator first serializes the whole local replica answer into one growing heap DataOutputBuffer (doubling growth, so up to 2x while it grows). It then copies every value into a new byte[] in the ResultSet, and finally encodes the whole response into one pooled direct ByteBuf. On a remote replica the same full buffer is built before internode_max_message_size (128 MiB) can refuse it. Stage 4 measured 28 MB allocated on the replica and 11.6 MB on the coordinator for an 8 MB result, about 5x. So a 1 GiB partition read once is several GiB of heap plus 1 GiB of direct memory. Up to 128 Native-Transport-Requests threads can do this at once, and the small request is charged almost nothing against the in-flight limits.

**Where:** src/java/org/apache/cassandra/config/Config.java:526-530; src/java/org/apache/cassandra/cql3/statements/SelectStatement.java:427-429,1059-1061; src/java/org/apache/cassandra/db/ReadResponse.java:197-203; src/java/org/apache/cassandra/cql3/selection/ResultSetBuilder.java:135; src/java/org/apache/cassandra/transport/Message.java:367; src/java/org/apache/cassandra/config/DatabaseDescriptor.java:990-996

## OC-104

**Case file:** `DOB_MAX_RECYCLE_BYTES-close-MAX_RECYCLE_BUFFER_SIZE--guided` · **Agent:** autonomous · **Patterns:** —

When a row is written to an SSTable (memtable flush, compaction, streaming receive, index builds), its whole body is serialized into the thread's scratch DataOutputBuffer. That buffer is direct memory by default and grows to fit the row: doubling up to 64 MiB, then 1.5x. During each growth the old and new buffers coexist, so one row of size R costs up to about 3R of direct memory transiently. DOB_MAX_RECYCLE_BYTES (1 MiB) only decides what is kept after close(), not how big the buffer gets while in use. No limit bounds a row's size at the defaults: max_mutation_size (16 MiB) applies per write, and a row (for example a collection column) can collect cells from any number of writes, with the collection and partition-size guardrails off. A 500 MiB row would take about 1-1.5 GiB of direct memory on one flush or compaction thread. With memtable_flush_writers plus concurrent_compactors (2-8) threads doing this at once, plus the row materialized on heap, this can pass MaxDirectMemorySize (which defaults to the heap size). Above about 2 GiB the buffer throws instead of growing.

**Where:** src/java/org/apache/cassandra/db/rows/UnfilteredSerializer.java:193-203; src/java/org/apache/cassandra/io/util/DataOutputBuffer.java:48,73-80,87,158-182

## OC-105

**Case file:** `native_transport_max_concurrent_connections-channelActive-limit--guided` · **Agent:** autonomous · **Patterns:** —

Each native-v5 connection gets 1 MiB of exclusive receive-queue capacity (native_transport_receive_queue_capacity). Request bytes within it are admitted without touching the endpoint (heap/40) or global (heap/10) in-flight reserves. Stage 4 saw 64 connections hold 64 x 1 MiB requests while the global reserve showed only 4,736 B in use. The connection limit is -1 (off) by default, and the limit handler is not even installed then. So the request bytes a node holds are bounded only by connections x 1 MiB plus heap/10. 4,000 connections each holding a 1 MiB request is about 4 GiB of frame buffers in direct memory, plus decoded heap copies of at least the same size. With 10,000 connections it is about 10 GiB, past an 8 GiB heap or direct limit. Each idle connection also costs about 1.3 KB of heap and one file descriptor, with no cap.

**Where:** src/java/org/apache/cassandra/config/Config.java:289,302; src/java/org/apache/cassandra/net/AbstractMessageHandler.java:418-422; src/java/org/apache/cassandra/transport/PipelineConfigurator.java:240-241; src/java/org/apache/cassandra/config/DatabaseDescriptor.java:651,656

## OC-106

**Case file:** `native_transport_max_message_size-processFirstFrameOfLargeMessage-maxMessageSize--guided` · **Agent:** autonomous · **Patterns:** —

Both native_transport_max_message_size and the in-flight reserves count a request's wire body bytes. But a request is decoded on the event loop before dispatch, and every bound value becomes a new heap byte[] wrapped in a HeapByteBuffer, while the direct frame/envelope is also kept until the response is flushed. For tiny values (a 1-byte value is 5 B on the wire but about 75 B on heap) the heap held is about 15x the counted bytes. A 16 MiB QUERY/EXECUTE/BATCH of 1-byte values is therefore about 250 MB of heap. At an 8 GiB heap the global reserve (heap/10, about 819 MiB of wire bytes) admits about 51 such requests, plus 1 MiB per connection. When the request executor is backlogged that is about 12 GiB of decoded values waiting in the executor queue: OOM.

**Where:** src/java/org/apache/cassandra/transport/CQLMessageHandler.java:534,551,385-391,500-511; src/java/org/apache/cassandra/transport/CBUtil.java:480,669-670; src/java/org/apache/cassandra/transport/messages/BatchMessage.java:56-73; src/java/org/apache/cassandra/config/DatabaseDescriptor.java:651,656

## OC-107

**Case file:** `native_transport_max_message_size-processFirstFrameOfLargeMessage-maxMessageSize--guided` · **Agent:** autonomous · **Patterns:** —

An admitted large v5 request (128 KiB or more) never releases its frame stashes. LargeMessage.onComplete() hands assembleFrame() to processRequest and never calls releaseBuffers(). The envelope wraps the ShareableBytes slices without owning them, so their last reference count is never dropped. Pooled stashes pin their networking-pool slots, and because recyclePartially is false they pin whole 128 KiB chunks for the life of the JVM. Overflow stashes wait for GC and stay counted in OverflowSize forever. In this case's stage 4, OverflowSize stayed at +8,389,184 B after an 8 MiB request. Over time the leak can pin the whole networking pool (128 MiB of direct memory), after which every networking buffer becomes an unpooled allocateDirect freed only by GC.

**Where:** src/java/org/apache/cassandra/transport/CQLMessageHandler.java:762-771,821-835; src/java/org/apache/cassandra/net/AbstractMessageHandler.java:565-579,593-596; src/java/org/apache/cassandra/net/ShareableBytes.java:127-140

## OC-108

**Case file:** `networking_cache_size-allocateMoreChunks-memoryUsageThreshold--guided` · **Agent:** autonomous · **Patterns:** —

The native-protocol response path has no backpressure. Flusher frames every response and writes it with writeAndFlush without checking channel writability. The request's in-flight permits are released once the response is framed, before it is written. So a client that keeps sending SELECTs but stops reading its socket makes the server hold every response frame. The first networking_cache_size (128 MiB) of them sit in the pool, and the rest are overflow allocateDirect buffers with no ceiling. Stage 4 held 192 MiB from one client with 192 requests of 1 MiB responses. The only backstop is -XX:MaxDirectMemorySize (unset, so equal to the heap size), so a few thousand MB-sized responses to a non-reading client reach 'OutOfMemoryError: Direct buffer memory'. v4 responses go through Netty's PooledByteBufAllocator with the same lack of writability checks.

**Where:** src/java/org/apache/cassandra/transport/Flusher.java:163-206,225-250; src/java/org/apache/cassandra/transport/CQLMessageHandler.java:71-72,495-511; src/java/org/apache/cassandra/utils/memory/BufferPool.java:233-239,443-450

## OC-109

**Case file:** `networking_cache_size-allocateMoreChunks-memoryUsageThreshold--guided` · **Agent:** autonomous · **Patterns:** —

Large native-v5 requests leak their frame stashes. CQLMessageHandler.LargeMessage.onComplete() calls processRequest(assembleFrame()) and never releaseBuffers(), so the ShareableBytes stashes are never released. Pooled stashes pin their slots, and with recyclePartially=false their whole 128 KiB chunks, for the life of the JVM. Overflow stashes are freed only by GC and stay in OverflowSize. Stage 4 arm L: 64 one-MB INSERTs left +58.7 MB of OverflowSize and 5.4 MB of pooled slots that were never returned, about 84 KB of pinned pool memory per 1 MB request. About 1,600 large requests pin the whole 128 MiB pool for good, after which all networking buffers fall back to unpooled direct allocations that depend on GC.

**Where:** src/java/org/apache/cassandra/transport/CQLMessageHandler.java:762-771,821-835; src/java/org/apache/cassandra/net/AbstractMessageHandler.java:565-579,593-596; src/java/org/apache/cassandra/utils/memory/BufferPool.java:1240-1265

## OC-110

**Case file:** `networking_cache_size-allocateMoreChunks-memoryUsageThreshold--guided` · **Agent:** guided · **Patterns:** CP-3, CP-5, CP-6, CP-7

Holder: v5 response frames waiting for a slow or stopped client, first in the networking BufferPool and then as unpooled overflow direct buffers. Why nothing stops it: when the pool is full, allocateMoreChunks returns null and LocalPool.get allocates the same bytes with allocate(size, OFF_HEAP), and nothing limits that overflow. Flusher writes and flushes every frame as soon as it is framed, and no class in transport/ checks isWritable. The request's in-flight permits are returned when the response is framed, before it is written. Size: (unlimited connections) x (stream ids outstanding) x (response size), limited only by MaxDirectMemorySize = RAM/4. Stage 4 saw a 192 MiB direct rise from one non-reading client, the same at every networking_cache_size. This is the v5 form of the same hold as coordinator_read_size_fail_threshold (v4).

**Where:** src/java/org/apache/cassandra/utils/memory/BufferPool.java:443-451 (refuse) -> :923 (overflow allocateDirect); transport/Flusher.java:201-206, :249-250; transport/CQLMessageHandler.java:500-510

## OC-111

**Case file:** `networking_cache_size-allocateMoreChunks-memoryUsageThreshold--guided` · **Agent:** guided · **Patterns:** CP-8, CP-6

Holder: JVM direct memory. Several fixed default pools draw on it, and none is compared with the budget: the networking pool min(128 MiB, heap/16), the chunk-cache pool min(512 MiB, heap/4), the internode receive reserves (512 MiB global + 128 MiB per endpoint + 4 MiB per connection), hint slabs (3 x 32 MiB) and per-thread DOB scratch buffers. Why nothing stops it: each pool checks only its own limit, and the pools' overflow paths add more on top. The default MaxDirectMemorySize is RAM/4, i.e. heap/2. Size: at 4 GiB RAM (2 GiB heap, 1 GiB direct), 128 + 512 + 512 = 1,152 MiB exceeds 1,024 MiB before any overflow. The sum stays above the budget below about 4.5 GiB of RAM.

**Where:** src/java/org/apache/cassandra/config/DatabaseDescriptor.java:573-577; config/Config.java:257-261; conf/cassandra-env.sh:59-66

## OC-112

**Case file:** `networking_cache_size-allocateMoreChunks-memoryUsageThreshold--guided` · **Agent:** guided · **Patterns:** CP-14

Holder: the frame stashes (ShareableBytes slices) of large native-v5 requests (128 KiB or more). Why nothing stops it: assembleFrame wraps the buffers without taking ownership, and onComplete processes the request without calling releaseBuffers(); releaseBuffers runs only on abort, corruption or expiry. A pooled stash therefore pins its 128 KiB normal chunk for the JVM's life. Stage 4 arm L confirmed it (OverflowSize +58.7 MB, never subtracted). Size: weak. The pinned real memory is capped by networking_cache_size (128 MiB), which the pool keeps anyway. Overflow stashes are freed only by GC (System.gc from Bits.reserveMemory still works, since DisableExplicitGC is not set). After that the pool is useless and every networking allocation overflows.

**Where:** src/java/org/apache/cassandra/transport/CQLMessageHandler.java:762-771, :821-835; net/AbstractMessageHandler.java:565-579, :593-596

## OC-113

**Case file:** `coordinator_read_size_fail_threshold-shouldReject-thresholdBytes--guided` · **Agent:** guided · **Patterns:** CP-3, CP-5, CP-6, CP-7

Holder: encoded read responses (Message.encode into Netty's pooled direct arenas for v4; networking pool or overflow for v5) waiting in the outbound buffer of clients that read slowly. Why nothing stops it: the read-size guard applies per page only, and is off at defaults. The native in-flight limits charge request bytes and release them when the response is handed to the flusher (v4) or framed (v5). No transport code reads channel writability. Size: connections (unlimited by default) x outstanding stream ids x page response size. For example, 64 connections x 16 outstanding x 3.5 MiB is about 3.5 GiB, against MaxDirectMemorySize = RAM/4. This is the same mechanism as networking_cache_size (v5 form).

**Where:** src/java/org/apache/cassandra/transport/PreV5Handlers.java:99-110; transport/CQLMessageHandler.java:500-510; transport/Flusher.java:201-206

## OC-114

**Case file:** `coordinator_read_size_fail_threshold-shouldReject-thresholdBytes--guided` · **Agent:** guided · **Patterns:** CP-2, CP-12

Holder: one page's result, which the replica builds whole, the coordinator copies into a ResultSet, and the response then encodes again as one frame. Why nothing stops it: read_thresholds_enabled=false and coordinator/local_read_size_* are null at defaults, so maybeFail returns at once. In 5.0 a CQL page is sized in rows, not bytes; the driver default is 5,000 rows. Size: 5,000 rows x 100 KiB is about 500 MB of value bytes per request, held once or more on heap plus the encoded frame. Up to native_transport_max_threads (128) such pages can be built at once.

**Where:** src/java/org/apache/cassandra/cql3/statements/SelectStatement.java:1059-1060; config/Config.java:526-530

## OC-115

**Case file:** `coordinator_read_size_fail_threshold-shouldReject-thresholdBytes--guided` · **Agent:** guided · **Patterns:** CP-1, CP-11

Holder: the coordinator ResultSet and the replica response buffers. Why nothing stops it: even when enabled, the guard counts only value bytes (ResultSetBuilder.addSize sums remaining()), not the per-value ByteBuffer, byte[] and list-slot overhead (about 60-80 B per value). It also runs after the replica answers are already resident. A range read sends up to cores x 10 sub-range requests at once (MAX_CONCURRENT_RANGE_REQUESTS), each answered in full before the first check. Size: rows of tiny values hold several times the threshold, and the replica answers come on top of it.

**Where:** src/java/org/apache/cassandra/cql3/selection/ResultSetBuilder.java:76-83; service/reads/range/RangeCommands.java:54, :84-96

## OC-116

**Case file:** `repair_disk_headroom_reject_ratio-verifyDiskHeadroomThreshold-rejectRatio--guided` · **Agent:** guided · **Patterns:** CP-7, CP-8

Holder: Merkle trees on the repair coordinator. Why nothing stops it: the only prepare-time gates on a repair are disk headroom and pending compactions, and nothing checks memory. concurrent_merkle_tree_requests defaults to 0, so the validation Scheduler has no limit. Each table's validation is sized to repair_session_space/RF per replica, and the coordinator holds RF of them, so about heap/16 per table, multiplied by the tables and vnode ranges of one command and by concurrent repair commands. The yaml itself says this 'can produce OOM'. Size: heap/16 per table; a repair over 16 or more tables at once can reach the whole heap.

**Where:** src/java/org/apache/cassandra/repair/ValidationManager.java:62-63; repair/RepairCoordinator.java:127; config/Config.java:210; service/ActiveRepairService.java:650-662

## OC-117

**Case file:** `DOB_MAX_RECYCLE_BYTES-close-MAX_RECYCLE_BUFFER_SIZE--guided` · **Agent:** guided · **Patterns:** CP-11, CP-7, CP-6, CP-4, CP-8

Holder: per-thread direct scratch buffers while in use in CommitLog.add() on MutationStage, CounterMutationStage and ViewMutationStage threads. Why nothing stops it: the recycle limit is checked only at close(), and expandToFit grows the buffer with no capacity check, allocating the new buffer before freeing the old. The buffer is held across segmentManager.allocate, so a stalled commit-log disk keeps every writer's buffer. The upstream in-flight limits count on-wire bytes. Size: a mutation of S bytes holds 2(S-1), and 3(S-1) for a moment. At max_mutation_size 16 MiB that is about 32 MiB per thread (48 MiB transient). 32 mutation threads = 1 GiB (1.5 GiB transient); with counter and view writers (96 threads) about 3 GiB. MaxDirectMemorySize is RAM/4, i.e. 1 GiB at a 2 GiB heap.

**Where:** src/java/org/apache/cassandra/io/util/DataOutputBuffer.java:73, :175-181; db/commitlog/CommitLog.java:306-311

## OC-118

**Case file:** `DOB_MAX_RECYCLE_BYTES-close-MAX_RECYCLE_BUFFER_SIZE--guided` · **Agent:** guided · **Patterns:** CP-12, CP-11

Holder: the scratch buffer used for an SSTable row body during flush and compaction. Why nothing stops it: serializeRowBody writes one whole row into the thread's scratch buffer. Nothing limits a row's size, for example a non-frozen collection built up by many writes. Above 64 MiB the buffer grows by half instead of doubling, and it is only trimmed at close. Size: about 2 x the largest row (3x for a moment) on each flush writer and compaction thread at once (2 flush writers + 2-8 compactors).

**Where:** src/java/org/apache/cassandra/db/rows/UnfilteredSerializer.java:192-203; io/util/DataOutputBuffer.java:158-181

## OC-119

**Case file:** `DOB_MAX_RECYCLE_BYTES-close-MAX_RECYCLE_BUFFER_SIZE--guided` · **Agent:** guided · **Patterns:** CP-14, CP-7, CP-8

Holder: idle per-thread scratch buffers of up to the limit L (1 MiB) each. Why nothing stops it: shared-pool workers never time out, and nothing calls scratchBuffer.remove(). A burst of writes just under L leaves L on every worker it touched, for the life of the process. Size: T x 1 MiB, where T is up to about 292 threads on 32 cores (sum of the concurrent_* stages + 128 native + 4 auth + cores), so about 292 MiB of direct memory added to the default pools' total.

**Where:** src/java/org/apache/cassandra/io/util/DataOutputBuffer.java:63-80; concurrent/SEPWorker.java:102-118

## OC-120

**Case file:** `memtable_heap_space-tryAllocate-limit--autonomous` · **Agent:** guided · **Patterns:** CP-1, CP-11

Holder: the object overhead (rows, cells, BTree arrays, ByteBuffer wrappers, partition entry) of each partition update being merged into a memtable. Why nothing stops it: this overhead is an ObjectSizes estimate charged to the pool only after the whole update is merged (reportAllocatedMemory in finally). New-partition overhead is likewise allocated 'after the fact ... can overshoot'. A writer that blocks at the limit already holds its update, uncounted. Slab region tails go uncounted too. Size: one uncounted update per writer: 32 MutationStage + 32 counter + 32 view threads, each update up to max_mutation_size 16 MiB serialized. Tiny-cell rows are about 20x larger on heap, so 1 MiB updates give about 0.6 GB beyond heap/4, and 16 MiB updates several GB.

**Where:** src/java/org/apache/cassandra/db/partitions/AtomicBTreePartition.java:146-176; db/memtable/SkipListMemtable.java:121-125; utils/memory/SlabAllocator.java:83-96

## OC-121

**Case file:** `memtable_heap_space-tryAllocate-limit--autonomous` · **Agent:** guided · **Patterns:** CP-4, CP-5, CP-1

Holder: deserialized mutations of writers blocked on hasRoom, plus mutation tasks queued behind them. Why nothing stops it: at the limit, writers wait until a flush releases space, and the pool counts flushing memtables as allocated. So a slow or stalled flush (disk stall) keeps them waiting, and the MutationStage queue (SEPExecutor, unbounded ConcurrentLinkedQueue, getMaxTasksQueued = Integer.MAX_VALUE) keeps accepting. The only upstream bounds count serialized bytes: native heap/10, internode 512 MiB global + 128 MiB per endpoint. Size: those wire-byte reserves x the heap expansion of the mutations (about 2x for large values, about 20x for tiny cells), on top of the heap/4 memtable pool.

**Where:** src/java/org/apache/cassandra/utils/memory/MemtableAllocator.java:180-196; concurrent/SEPExecutor.java:68, :102-105

## OC-122

**Case file:** `concurrent_compactors-submitBackground-getMaximumPoolSize--guided` · **Agent:** guided · **Patterns:** CP-12, CP-7

Holder: the BIG-format per-partition row-index buffer (heap DataOutputBuffer) of every SSTable writer: compaction tasks, flush writers, and the separate validation, index-build, view-build and cleanup executors that the compaction thread limit does not count. Why nothing stops it: one IndexInfo (first and last clustering + offsets) is appended for each 64 KiB block of the partition being written. Neither partition size nor clustering-key size (up to 64 KiB) is limited, and indexOffsets grows linearly too. The reusable buffer keeps its capacity for the writer's life. Size: about (2 x clustering size + ~20 B) per 64 KiB of partition. That is about 0.1% of the partition for small keys, but up to about 2x the partition (plus doubling slack) when clustering keys are tens of KiB. A 1 GiB partition with such keys gives about 2-3 GiB of heap per writer, x min(8, cores) compactors + flush writers.

**Where:** src/java/org/apache/cassandra/io/sstable/format/big/BigFormatPartitionWriter.java:140-185; db/compaction/CompactionManager.java:244-249

## OC-123

**Case file:** `batch_size_fail_threshold-verifyBatchSize-failThreshold--guided` · **Agent:** guided · **Patterns:** CP-1, CP-11, CP-12

Holder: a BATCH's decoded bound values and the mutations built from them on the coordinator. Why nothing stops it: decode copies every bound value into its own heap byte[] wrapped in a HeapByteBuffer. getMutations then builds every mutation, plus a cached serialized copy under 1 MB, before verifyBatchSize runs. Batches of a single mutation and conditional batches skip the check entirely. The only node-wide limit is native_transport_max_request_data_in_flight (heap/10; heap/40 per IP), which charges on-wire body bytes. Size: stage 4 measured 2.1-2.5x the batch's bytes for large values. For tiny values a 5-byte wire value is about 75 B on heap (about 15x) before mutation objects are built. So heap/10 of wire bytes can be 1.5-2x the heap (for example about 12 GB at an 8 GiB heap) while 128 request threads build mutations. This is the same expansion as native_transport_max_message_size.

**Where:** src/java/org/apache/cassandra/transport/CBUtil.java:480, :669-670; transport/messages/BatchMessage.java:56-73; cql3/statements/BatchStatement.java:332-334, :428-439; config/DatabaseDescriptor.java:649-656

## OC-124

**Case file:** `native_transport_max_message_size-processFirstFrameOfLargeMessage-maxMessageSize--guided` · **Agent:** guided · **Patterns:** CP-1, CP-7

Holder: a request's decoded heap copies, alongside its direct frame envelope, which is kept until the response is flushed. Why nothing stops it: the message-size limit and the in-flight reserves (heap/10 global, heap/40 per IP) both count on-wire body bytes. Decode on the event loop (processRequest) copies every bound value into a new heap byte[] before any execution-time check. Size: at least 2x the wire bytes, and about 15x for 1-byte values. A 16 MiB BATCH of tiny values is about 250 MB of heap. The global reserve admits about 51 such requests at an 8 GiB heap, so decoded heap can reach about 1.5x the heap when the executor is backlogged. This is the same mechanism as batch_size_fail_threshold.

**Where:** src/java/org/apache/cassandra/transport/CQLMessageHandler.java:386-391, :534-551; transport/CBUtil.java:480, :669-670

## OC-125

**Case file:** `native_transport_max_concurrent_connections-channelActive-limit--guided` · **Agent:** guided · **Patterns:** CP-7, CP-8, CP-1

Holder: request bytes admitted against each connection's own native_transport_receive_queue_capacity (1 MiB), plus their decoded heap copies. Why nothing stops it: acquireCapacity succeeds against the per-connection capacity before it touches the endpoint or global reserve, so these bytes are outside heap/10. The connection limits default to -1, and ConnectionLimitHandler is not even installed. Size: connections x 1 MiB (x the decode expansion). Stage 4 saw 64 held 1 MiB requests with only 4,736 B charged to the reserve and +76 MB of heap. 2,000 connections would be about 2 GiB of heap beyond the 0.8 GiB reserve at an 8 GiB heap.

**Where:** src/java/org/apache/cassandra/net/AbstractMessageHandler.java:419-428; config/Config.java:289-290, :302; transport/PipelineConfigurator.java:240-244, :306

## OC-126

**Case file:** `native_transport_max_concurrent_connections-channelActive-limit--guided` · **Agent:** guided · **Patterns:** CP-6, CP-7

Holder: a v4 (pre-v5) request that arrives when the in-flight reserve is exhausted. Why nothing stops it: in the default backpressure mode (throwOnOverload false), a failed tryAllocate is followed by a forced endpointPayloadTracker.allocate. The connection is paused, but the request is still processed, so each connection can push one request past the reserve. Frames already buffered may also still be decoded. Connections are unlimited at defaults. Size: connections x up to native_transport_max_frame_size (16 MiB) of wire bytes, x2 or more decoded, beyond heap/10. 100 connections would be about 1.6-3 GiB.

**Where:** src/java/org/apache/cassandra/transport/PreV5Handlers.java:176-186; config/Config.java:285, :289-290

## OC-127

**Case file:** `concurrent_writes-takeWorkPermit-workPermits--autonomous` · **Agent:** autonomous · **Patterns:** —

Holder: the coordinator's own replica write. It is a LocalMutationRunnable that holds the decoded Mutation and its cached serialized copy, about 2x the value (stage 4 measured 131.5 KiB per 64 KiB value). Why nothing stops it: when no work permit is free (or nothing is queued yet), maybeExecuteImmediately puts it on MutationStage's unbounded ConcurrentLinkedQueue (getMaxTasksQueued = Integer.MAX_VALUE). At RF>=2 and CL=ONE, a peer's ack completes the handler. That frees the request thread blocked in responseHandler.get() and, on response flush, releases the native-transport in-flight bytes, so no counter covers the queued local write. When a worker reaches it after its deadline, it is not dropped: it is resubmitted as a HintRunnable on the same stage and applied anyway. Rough size at defaults (32 permits, heap = RAM/2): (client write rate - local apply rate) x ~2x mutation size. For example, an excess of 10k writes/s x 2 KiB is about 20 MB/s, so a 4-8 GiB heap fills in minutes while the local stage is slow (flush or GC stall, disk).

**Where:** src/java/org/apache/cassandra/concurrent/SEPExecutor.java:68, :102-106, :121-123, :217-224; src/java/org/apache/cassandra/service/StorageProxy.java:1569, :1676, :906, :2640-2654; src/java/org/apache/cassandra/service/WriteResponseHandler.java:58-61

## OC-128

**Case file:** `internode_application_receive_queue_capacity-releaseCapacity-queueCapacity--autonomous` · **Agent:** autonomous · **Patterns:** —

Holder: inbound small internode messages (<= 64 KiB, the large-message threshold). They are charged their on-wire size against queueCapacity and the reserves, but they are deserialized right away on the event loop. They then wait on the target stage as Message/Mutation objects until the verb handler runs, and only then is the capacity released. Why nothing stops it: the counter is in wire bytes, while the heap held per wire byte depends on the payload. Stage 4 measured 2.17x for 1 KiB blobs; tiny-cell mutations expand far more. No limit compares the deserialized size with the heap. Rough size at defaults: the counted total is N_peers x 3 x 4 MiB + min(512 MiB global, N x 128 MiB endpoint). Times about 2x that is about 1.1 GiB for blobs; times about 15-17x for tiny cells it is about 8 GiB, more than the default heap (RAM/2) on any host under about 16 GB of RAM, before memtables (heap/4).

**Where:** src/java/org/apache/cassandra/net/InboundMessageHandler.java:128, :140, :148-149, :157-195, :420-442; src/java/org/apache/cassandra/net/AbstractMessageHandler.java:411-438, :461-472; src/java/org/apache/cassandra/config/Config.java:257-261

## OC-129

**Case file:** `internode_application_receive_queue_capacity-releaseCapacity-queueCapacity--autonomous` · **Agent:** autonomous · **Patterns:** —

Holder: frames of queued large inbound messages (> 64 KiB). They sit in networking BufferPool direct buffers (overflow beyond the 128 MiB pool is plain direct allocation) until a MutationStage worker deserializes them. Why nothing stops it: the admitted total is N_peers x Q + min(G, N x E), up to 512 MiB + N x 4 MiB per node. Startup checks only internode_max_message_size against the reserves; nothing reconciles the total with MaxDirectMemorySize, which other direct users share. Rough size at defaults on a 4 GiB host: direct budget RAM/4 = 1 GiB. Inbound queue up to ~528 MiB, plus the chunk cache min(512 MiB, heap/4) = 512 MiB, plus the networking pool min(128 MiB, heap/16) = 128 MiB, plus hint slabs up to 96 MiB, comes to about 1.26 GiB > 1 GiB. The result is OutOfMemoryError: Direct buffer memory.

**Where:** src/java/org/apache/cassandra/net/BufferPoolAllocator.java:70-75, :134-137; src/java/org/apache/cassandra/net/InboundMessageHandler.java:198-201, :217, :357-381; src/java/org/apache/cassandra/config/DatabaseDescriptor.java:573-577, :974-997; conf/cassandra-env.sh:62-66, :139-158

## OC-130

**Case file:** `internode_max_message_size-enqueue-getInternodeMaxMessageSizeInBytes--autonomous` · **Agent:** autonomous · **Patterns:** —

Holder: the coordinator's outbound Mutation for each remote replica. sendWriteWithCallback registers it in the callback map (CallbackInfo holds the Message) before enqueue. It stays there until the replica responds or the write deadline passes. Why nothing stops it: the per-message check and the send-queue charge count serialized (wire) bytes, and that charge is released when the message is flushed to the socket. Messages already flushed, sitting in socket buffers, admitted by the replica's receive reserves, or queued on the replica's MutationStage are still held on the coordinator, with no counter. At CL=ONE the first ack has also released the client's in-flight bytes. Rough size at defaults: per peer, up to the replica's admitted bytes (3 x 4 MiB + 128 MiB endpoint reserve) plus socket buffers, times the heap-per-wire-byte ratio of the Mutation (about 2x for blobs, about 20x for tiny cells). For example, 3 slow peers x ~140 MiB x 20 is about 8 GiB, more than the default heap; in general it is write rate x 2 s deadline x heap per mutation.

**Where:** src/java/org/apache/cassandra/net/MessagingService.java:421-426; src/java/org/apache/cassandra/net/RequestCallbacks.java:104-108, :239; src/java/org/apache/cassandra/net/OutboundConnection.java:330-348, :861-866

## OC-131

**Case file:** `internode_max_message_size-inferMessageSize-size--autonomous` · **Agent:** autonomous · **Patterns:** —

Holder: admitted small internode messages (<= 64 KiB). inferMessageSize bounds only one message's wire size; the message is then deserialized on arrival and held on the heap until a stage thread runs it. Why nothing stops it: no limit counts the deserialized size, and the receive reserves count wire bytes only. Rough size at defaults: up to 512 MiB global (+ 3 x 4 MiB per peer) of wire bytes, times the expansion (about 2x for blobs, about 15-20x for tiny-cell mutations). That is roughly 1-9 GiB, against a default heap of RAM/2.

**Where:** src/java/org/apache/cassandra/net/Message.java:814-818; src/java/org/apache/cassandra/net/InboundMessageHandler.java:128, :140, :148-149, :163-166, :193; src/java/org/apache/cassandra/config/Config.java:257-261

## OC-132

**Case file:** `internode_max_message_size-inferMessageSize-size--autonomous` · **Agent:** autonomous · **Patterns:** —

Holder: large internode mutations, up to 16 MiB on the wire at the default max_mutation_size, below the 128 MiB limit. They are expanded on the heap just in time, on each busy MutationStage worker. Why nothing stops it: per-message and reserve checks count wire bytes. The number expanded at once is bounded only by concurrent_writes, and no byte budget covers the deserialized form. Rough size at defaults: 32 workers x 16 MiB x expansion. With blobs (about 2x) that is about 1 GiB; with tiny cells (about 17x) it is about 8.7 GiB, beside memtables at heap/4.

**Where:** src/java/org/apache/cassandra/net/InboundMessageHandler.java:357-365, :403-430; src/java/org/apache/cassandra/config/Config.java:180; src/java/org/apache/cassandra/config/DatabaseDescriptor.java:898-899

## OC-133

**Case file:** `maxHintsInProgress-checkHintOverload-totalHintsInProgress--autonomous` · **Agent:** autonomous · **Patterns:** —

Holder: HintRunnables on MutationStage, each holding its Mutation until HintsService.write runs. Why nothing stops it: checkHintOverload is dead code. hintsInProgress is a bare CacheLoader, so getHintsInProgressFor returns a new AtomicInteger(0) on every call; the per-destination clause is always false and the throw never fires. Several hint producers skip the check altogether: write timeouts (AbstractWriteResponseHandler.onFailure), expired local writes re-queued as self-hints (shouldHint(self) is false anyway), and Paxos v2. The stage queue is unbounded. When the single hint flush thread lags, all hint writers block in HintsBufferPool.take() (3 x 32 MiB slabs), so MutationStage stops draining while writes keep arriving at CL=ONE from the live replicas. Rough size at defaults: one queued Mutation (~1-2x value) per write to the down or slow replica, x (write rate - hint write rate) x outage time. For example, 20k writes/s x 2 KiB is about 40 MB/s, which reaches several GiB in minutes, against the nominal 128 x cores limit.

**Where:** src/java/org/apache/cassandra/service/StorageProxy.java:202-209, :1505, :1592-1593, :2446, :2640-2654, :2768, :2811, :2822-2828; src/java/org/apache/cassandra/service/AbstractWriteResponseHandler.java:309-310; src/java/org/apache/cassandra/hints/HintsBufferPool.java:107-124; src/java/org/apache/cassandra/concurrent/SEPExecutor.java:68

## OC-134

**Case file:** `maximumPoolSize-takeTaskPermit-workPermits--autonomous` · **Agent:** autonomous · **Patterns:** —

Holder: coordinator-local writes (LocalMutationRunnable holding the Mutation plus its cached serialization). They find no MutationStage work permit and are queued. Why nothing stops it: the work-permit check at line 165/196 counts running tasks only. addTask always appends to the unbounded ConcurrentLinkedQueue. The local path never crosses the internode receive reserves, and at CL ONE/QUORUM met by other replicas the native-transport bytes are released when the response is flushed. Expired entries are re-queued as hints instead of being shed. Rough size at defaults: (client write rate - local apply rate) x ~2x mutation size, for example 10k/s x 1-2 KiB, which is 10-20 MB/s. That reaches GiB in minutes while the local stage is stalled (flush or allocation), with no limit before -Xmx.

**Where:** src/java/org/apache/cassandra/concurrent/SEPExecutor.java:68, :102-106, :119-133, :165, :217-224; src/java/org/apache/cassandra/service/StorageProxy.java:1569, :1676, :2640-2654; src/java/org/apache/cassandra/transport/CQLMessageHandler.java:500-510

## OC-135

**Case file:** `max_mutation_size-allocateBytes-slabCapacity--autonomous` · **Agent:** autonomous · **Patterns:** —

Holder: hint Mutations waiting upstream of the slab pool, as HintRunnables on MutationStage. Why nothing stops it: the slab check bounds hint direct memory at 3 x 32 MiB. When all slabs are full and the single HintsWriteExecutor flush thread lags (slow disk), every hint writer blocks in reserveBuffers.take() while holding the pool monitor. The 32 MutationStage threads stall, but MutationStage's queue is unbounded and maxHintsInProgress never fires. Hint tasks and ordinary local writes therefore pile up on the heap instead of being refused. Rough size at defaults: write rate to the down replica x mutation size (~1-2x value on heap) x time the flush lags. For example, 20k/s x 2 KiB for 2 minutes is about 4.8 GB, more than the default heap.

**Where:** src/java/org/apache/cassandra/hints/HintsBufferPool.java:69-83, :107-124; src/java/org/apache/cassandra/hints/HintsService.java:79, :110-111; src/java/org/apache/cassandra/service/StorageProxy.java:2811, :2822-2828; src/java/org/apache/cassandra/concurrent/SEPExecutor.java:68, :121-123

## OC-136

**Case file:** `native_transport_queue_max_item_age_threshold-hasQueueCapacity-oldestTaskQueueTime--guided` · **Agent:** autonomous · **Patterns:** —

Holder: decoded client requests (heap copies of bound values) queued on the Native-Transport-Requests executor. Why nothing stops it: the queue-age check is off by default (threshold Double.MAX_VALUE), and native_transport_throw_on_overload defaults to false. In that default mode, a self-contained request (< ~128 KiB framed payload) whose acquireCapacity fails is still processed (processRequestAndUpdateMetrics) without being charged. Its bytes are then released at response flush through release(header) -> releaseCapacity(bodySize), which drives the connection's queueSize below the bytes it really holds, permanently. The large-message path avoids this ('we haven't acquired a capacity'), but the small path does not. Each bytes-in-flight backpressure event therefore widens that connection's uncharged allowance by one request, so the per-IP (heap/40) and global (heap/10) in-flight limits erode under sustained overload. Rough size at defaults: allowance = 1 MiB + K x request size per connection. For example, 10,000 overload events x 64 KiB is about 625 MiB per connection, already more than heap/10 at an 8 GiB heap, and it keeps growing with K.

**Where:** src/java/org/apache/cassandra/transport/CQLMessageHandler.java:221-247, :267-271, :500-510, :638-647; src/java/org/apache/cassandra/net/AbstractMessageHandler.java:396-407, :461-472; src/java/org/apache/cassandra/config/Config.java:1393-1394

## OC-137

**Case file:** `native_transport_queue_max_item_age_threshold-hasQueueCapacity-oldestTaskQueueTime--guided` · **Agent:** autonomous · **Patterns:** —

Holder: per-connection native receive queues. Each connection gets an exclusive 1 MiB native_transport_receive_queue_capacity that is outside the global heap/10 and per-IP heap/40 reserves; requests are decoded onto the heap and wait in the unbounded request executor queue. Why nothing stops it: native_transport_max_concurrent_connections (and per-IP) default to -1, unlimited, and the queue-age check that could shed is off by default. Rough size at defaults: N_connections x 1 MiB + heap/10. For example, 3,000 client connections give about 3 GiB + heap/10 of queued request heap, more than a 4 GiB default heap (8 GiB host) once memtables (heap/4) are counted.

**Where:** src/java/org/apache/cassandra/config/Config.java:289-290, :297-302, :1394; src/java/org/apache/cassandra/config/DatabaseDescriptor.java:649-657; src/java/org/apache/cassandra/net/AbstractMessageHandler.java:411-438; src/java/org/apache/cassandra/transport/Dispatcher.java:345-349

## OC-138

**Case file:** `native_transport_queue_max_item_age_threshold-hasQueueCapacity-oldestTaskQueueTime--guided` · **Agent:** guided · **Patterns:** CP-6, CP-5, CP-4

Holder: decoded CQL requests waiting in the Native-Transport-Requests SEP queue (unbounded ConcurrentLinkedQueue, getMaxTasksQueued = Integer.MAX_VALUE). Why nothing stops it: at defaults the age check is off (threshold Double.MAX_VALUE, Config.java:1394). native_transport_throw_on_overload is false by default (Config.java:1393), so even with the check on, a refusal for queue age or bytes only pauses the connection and the refused request is still decoded and dispatched (CQLMessageHandler.java:237-256). A byte refusal is dispatched uncharged, but its release on flush subtracts the full size (CQLMessageHandler.java:500-511 -> AbstractMessageHandler.java:461-475). That drives the connection's queueSize negative, so the connection later admits locally past its own capacity without touching the reserves (AbstractMessageHandler.java:419-423). Queued requests are never expired while they wait: the native_transport_timeout check runs only at dequeue (Dispatcher.java:364-368). Rough size at defaults: decoded bytes ≈ connections × client in-flight window × request size, with no server cap. The 2026-11-17 recheck of the receive-queue case measured 312-625 MB for 20-40 connections on a 2 GiB heap (1.45-2.91× heap/10), linear in connections. Same mechanism as native_transport_receive_queue_capacity-acquireCapacity-queueCapacity--guided: file once, naming both stems.

**Where:** src/java/org/apache/cassandra/transport/CQLMessageHandler.java:237-256 (with :500-511; AbstractMessageHandler.java:419-423, :461-475; Dispatcher.java:364-368; Config.java:1393-1394)

## OC-139

**Case file:** `native_transport_queue_max_item_age_threshold-hasQueueCapacity-oldestTaskQueueTime--guided` · **Agent:** guided · **Patterns:** CP-7, CP-8

Holder: each CQL connection's private receive allowance, native_transport_receive_queue_capacity = 1 MiB (Config.java:302). Why nothing stops it: acquireCapacity admits up to queueCapacity without touching the per-IP (heap/40) or global (heap/10) reserve (AbstractMessageHandler.java:419-423). So the node-wide total is heap/10 + N × 1 MiB, and N is uncapped at defaults (native_transport_max_concurrent_connections = -1, Config.java:289). The per-IP reserve does not bound the 1 MiB parts either. Rough size at defaults: 1,000 client connections add about 1 GiB of admitted request bytes beyond heap/10. Held as decoded heap objects, about 1× the wire size for blob values and more for many small bind values.

**Where:** src/java/org/apache/cassandra/net/AbstractMessageHandler.java:419-423 (Config.java:289, :302; DatabaseDescriptor.java:649-656)

## OC-140

**Case file:** `prepared_statements_cache_size-storePreparedStatement-capacityToBytes--autonomous` · **Agent:** guided · **Patterns:** CP-11, CP-12, CP-1

Holder: the parsed and prepared statement graph of a PREPARE (CQL text, AST, terms and selectors), plus jamm's visited-object tracking during ObjectSizes.measureDeep. Why nothing stops it: the cache-size guard runs only after the statement has been fully parsed, prepared, validated and deep-measured (QueryProcessor.prepare -> parseAndPrepare :441-471, measurePstmnt :947-949, guard :825). On the way in, the request is charged only its wire bytes against the in-flight reserves. Nothing bounds the number of literal terms: the 65,535 limit at :757-758 counts bind markers only. Rough size at defaults: native_transport_max_message_size = min(max_mutation_size 16 MiB, heap/10, heap/40) = 16 MiB (DatabaseDescriptor.java:3237-3244). A 16 MiB statement of literals (for example an IN list of about 8M short literals) could expand about 10-30× on the heap (estimate, not measured), so 160-500 MB per request. The global reserve admits heap/10 ÷ 16 MiB of these at once, about 51 on an 8 GiB heap, which is several GB together. The QUERY (unprepared) path parses the same text with no cache guard at all.

**Where:** src/java/org/apache/cassandra/cql3/QueryProcessor.java:825 (parse at :754 -> :441-471; measure at :947-949)

## OC-141

**Case file:** `internode_max_message_size-inferMessageSize-size--autonomous` · **Agent:** guided · **Patterns:** CP-1

Holder: inbound small internode messages (64 KiB or less), deserialized on the netty thread at arrival and held as heap objects until a stage thread runs them. Why nothing stops it: the per-message limit and the receive queues (4 MiB per link, 128 MiB per peer, 512 MiB global) all count on-wire bytes (Message.java:817; InboundMessageHandler.java:128, :140). A tiny-cell mutation holds about 17-20× its wire size on the heap (phase 2 B6). Rough size at defaults: about 528 MiB on-wire admitted ≈ 9 GiB of heap, more than the default heap of any host with less than about 18 GiB of RAM. Same mechanism as phase 2 B6, also present in internode_application_receive_queue_capacity-releaseCapacity-queueCapacity--autonomous: file once, naming both stems.

**Where:** src/java/org/apache/cassandra/net/InboundMessageHandler.java:148-149, :156-166 (limit at Message.java:817)

## OC-142

**Case file:** `internode_max_message_size-inferMessageSize-size--autonomous` · **Agent:** guided · **Patterns:** CP-1, CP-7, CP-11

Holder: large inbound messages (over 64 KiB, mutations up to max_mutation_size 16 MiB at defaults). They wait as raw frames and are deserialized just in time on the stage thread (InboundMessageHandler.java:358-381). Why nothing stops it: the charge is the 16 MiB wire size, but deserialization expands it about 17× for tiny cells. Mutation.validateSize on the replica runs only after deserialization (MutationVerbHandler.doVerb -> Mutation.java:169-176). Every MutationStage thread can be expanding one at the same time. Rough size at defaults: 32 MutationStage threads (Config.java:180) × 16 MiB × about 17 ≈ 8.7 GiB of transient heap, against 512 MiB of charged bytes. Inferred, not run (B6 used 10.8 KiB messages).

**Where:** src/java/org/apache/cassandra/net/InboundMessageHandler.java:358-381 (branch at :148-151; Config.java:180)

## OC-143

**Case file:** `internode_max_message_size-enqueue-getInternodeMaxMessageSizeInBytes--autonomous` · **Agent:** guided · **Patterns:** CP-12, CP-2, CP-11

Holder: a replica's whole serialized read response, built in one DataOutputBuffer before any size check (ReadCommandVerbHandler.java:93-95 -> ReadResponse.java:197-201). Why nothing stops it: the 128 MiB internode limit is checked only at enqueue, after the response exists (OutboundConnection.java:330-332). Paging limits rows, not bytes. read_thresholds_enabled is false by default (Config.java:526), so local_read_size_fail_threshold is off. A coordinator-local read never reaches the internode check at all. Rough size at defaults: a 5,000-row page of 1 MiB blobs is about 5 GB, capped only by DataOutputBuffer's 2 GiB array limit (DataOutputBuffer.java:118-131) plus transient growth copies. 32 concurrent_reads (Config.java:179) can each build one.

**Where:** src/java/org/apache/cassandra/db/ReadResponse.java:197-201 (check at OutboundConnection.java:330-332)

## OC-144

**Case file:** `internode_max_message_size-enqueue-getInternodeMaxMessageSizeInBytes--autonomous` · **Agent:** guided · **Patterns:** CP-1, CP-3, CP-4

Holder: the coordinator's Mutation and its write callback. Why nothing stops it: the send queue charges canonicalSize, the serialized bytes (OutboundConnection.java:330, :335). That charge is released at flush (:866, :903), but the callback registered before send (MessagingService.java:421-425) keeps the Mutation until a response arrives or the write expires. The coordinator holds about 20× the serialized size for tiny-cell mutations. Rough size at defaults: retained mutations ≈ write rate × write timeout (2 s) × heap per mutation, with no counter after flush; send reserves of 128 MiB per peer and 512 MiB global ≈ 10 GiB of heap even before flush. Same mechanism as phase 2 B6 (send side).

**Where:** src/java/org/apache/cassandra/net/OutboundConnection.java:330-335, :866, :903 (MessagingService.java:421-425)

## OC-145

**Case file:** `max_mutation_size-allocateBytes-slabCapacity--autonomous` · **Agent:** guided · **Patterns:** CP-4, CP-5

Holder: the MutationStage queue: local writes, replica mutations and HintRunnables, each holding a Mutation. Why nothing stops it: when the hints disk stalls, flushes stop recycling slabs. Once 3 slabs (3 × 32 MiB) are in flight, a hint writer parks in reserveBuffers.take() while holding the pool monitor (HintsBufferPool.java:99-118), and every other hint writer blocks on that monitor. HintRunnables run on Stage.MUTATION (StorageProxy.java:2822-2827), so the 32 MutationStage threads block too. Stage 4 at MAX_HINT_BUFFERS=1 saw 32 active and 41,483 pending. The SEP queue behind them is unbounded, coordinator-local writes are uncharged, and the hint overload check never fires (see maxHintsInProgress). Rough size at defaults: offered write rate × stall time × heap per mutation, for example 10k writes/s × 1-2 KiB ≈ 0.6-1.2 GB per minute of stall. Replica mutations are bounded only by the 512 MiB wire receive reserve (≈ GBs of heap).

**Where:** src/java/org/apache/cassandra/hints/HintsBufferPool.java:99-118 (writer path :68-84; StorageProxy.java:2822-2827)

## OC-146

**Case file:** `internode_application_receive_queue_capacity-releaseCapacity-queueCapacity--autonomous` · **Agent:** guided · **Patterns:** CP-7, CP-8, CP-6

Holder: frames of inbound internode messages admitted under each link's private queue capacity Q = 4 MiB (Config.java:257). Large messages sit in direct memory from the networking pool; small ones are deserialized on the heap. Why nothing stops it: Q is admitted without touching the per-peer (128 MiB) or global (512 MiB) reserve (AbstractMessageHandler.java:419-423), so the node total is N_peers × 3 links × 4 MiB + 512 MiB, and the peer count is unlimited. None of these is reconciled with MaxDirectMemorySize (about RAM/4), which the chunk cache (up to 512 MiB), the networking pool (up to 128 MiB) and the hint slabs (96 MiB) also share. Rough size at defaults: phase 2 C1 got OutOfMemoryError: Direct buffer memory at 528-544 MiB admitted with every counter within its contract. Same mechanism as phase 2 C1. The small-message heap gap (phase 2 B6) also applies to this stem; it is filed under internode_max_message_size-inferMessageSize-size--autonomous.

**Where:** src/java/org/apache/cassandra/net/AbstractMessageHandler.java:419-423, :461-475 (Config.java:256-261; MessagingService.java:308-310, :675-681)

## OC-147

**Case file:** `maxHintsInProgress-checkHintOverload-totalHintsInProgress--autonomous` · **Agent:** guided · **Patterns:** CP-6, CP-2, CP-5

Holder: HintRunnables queued on the unbounded MutationStage, each holding its Mutation. Why nothing stops it: hintsInProgress is a bare Guava CacheLoader, not a LoadingCache. load() returns a new AtomicInteger(0) on every call (StorageProxy.java:203-209, :2766-2768), so the per-destination term in checkHintOverload is always 0 and the && short-circuits: the overload exception can never be thrown (:1592-1593). Even if fixed, the limit counts tasks, not bytes: 128 × cores (:202) × up to 16 MiB per mutation. Rough size at defaults: stage 4 saw 0 refusals at limits 1, 128 and MAX, with 1.15 GB of hints written. A fixed counter at 16 cores would still allow 2,048 × 16 MiB ≈ 32 GiB.

**Where:** src/java/org/apache/cassandra/service/StorageProxy.java:1592-1593 (:202-209, :2766-2768, :2822-2827)

## OC-148

**Case file:** `maxHintsInProgress-checkHintOverload-totalHintsInProgress--autonomous` · **Agent:** guided · **Patterns:** CP-10, CP-4

Holder: hints created off the write-entry path, each a Mutation queued on MutationStage. Why nothing stops it: checkHintOverload runs only at write entry and in Paxos (StorageProxy.java:1505, :796). Hints from write failure or expiry (AbstractWriteResponseHandler.java:309-310), from expired local writes requeued as self-targeted HintRunnables (StorageProxy.java:2634-2656; enforce_native_deadline_for_hints false, Config.java:1400), from hintMutation (:977-988) and from PaxosCommit (PaxosCommit.java:231) never pass the check. Self-targets are excluded from it anyway (shouldHint(self) is false, :2442-2447). So even a fixed limit would not shed the backlog that drives the total up. Rough size at defaults: phase 2 S2 reached about 61,500 queued mutations and a Java heap OOM at 2 GiB.

**Where:** src/java/org/apache/cassandra/service/AbstractWriteResponseHandler.java:309-310 (StorageProxy.java:2645-2654, :977-988, :2442-2447; PaxosCommit.java:231)

## OC-149

**Case file:** `concurrent_writes-takeWorkPermit-workPermits--autonomous` · **Agent:** guided · **Patterns:** CP-3, CP-5, CP-4, CP-1

Holder: coordinator-local writes (LocalMutationRunnable holding the Mutation, its response handler and a cached serialized copy up to 1,000,000 B) queued on the MutationStage's unbounded ConcurrentLinkedQueue (SEPExecutor.java:68, :102-106, :218-224). Why nothing stops it: at RF >= 2 with CL=ONE/QUORUM met by peers, the first ack releases the request thread, the client slot and the native in-flight charge (CQLMessageHandler.java:500-510) while the local write still waits. An expired local write is not shed; it is requeued as a hint and applied (StorageProxy.java:2634-2656, enforce_native_deadline_for_hints false at Config.java:1400). Nothing between the 32 permits and -Xmx counts it. Held/charged ≈ 2-2.8× from the cached serialization (StorageProxy.java:1501, Mutation.java:445-456). Rough size at defaults: (client rate − local apply rate) × heap per mutation, for example 10k/s × 1-2 KiB ≈ 10-20 MB/s. Stage 4 saw 887.5 MiB queued against RequestsSize ≤ 0.07 MiB; phase 2 S2 got a Java heap OOM at 2 GiB 3/3. Same mechanism as phase 2 S2 and as maximumPoolSize-takeTaskPermit-workPermits--autonomous: file once, naming both stems.

**Where:** src/java/org/apache/cassandra/service/StorageProxy.java:1566-1569, :1674-1676 (SEPExecutor.java:68, :218-224; StorageProxy.java:2634-2656)

## OC-150

**Case file:** `maximumPoolSize-takeTaskPermit-workPermits--autonomous` · **Agent:** guided · **Patterns:** CP-5, CP-3

DUPLICATE: same mechanism as the candidate under concurrent_writes-takeWorkPermit-workPermits--autonomous (phase 2 S2); file once, naming both stems. Holder: coordinator-local writes queued on the SEP MutationStage queue behind the work permits, unbounded and uncharged once the client response is flushed. Why nothing stops it: addTask always adds; nothing caps the queue's bytes or count. Rough size at defaults: write rate × residence × heap per mutation, GB in minutes when the local stage is slow.

**Where:** src/java/org/apache/cassandra/concurrent/SEPExecutor.java:165, :218-224 (StorageProxy.java:1674-1676)

## OC-151

**Case file:** `index_summary_capacity-adjustSamplingLevels-remainingSpace--autonomous` · **Agent:** autonomous · **Patterns:** —

Holder: off-heap (JNA malloc, outside heap/NMT/MaxDirectMemorySize) index summaries of BIG sstables (the default format). Why nothing stops it: every flush and compaction output gets a full-level summary (BASE_SAMPLING_LEVEL) with no check against index_summary_capacity. The cap is only applied by the periodic redistribution, which runs every 60 min by default (the first run is 60 min after start-up), is skipped while compaction is paused, and cannot shrink sstables that are compacting. During a compaction the input summaries and the output's builder buffers exist at the same time. Rough size at defaults: a full summary is about partitions/128 x (key bytes + 12 B). For 2e9 partitions with 32 B keys that is about 15.6 M entries x 44 B, about 690 MB of native memory, against a default cap of 5% of heap (about 409 MB at an 8 GB heap). A major compaction can put the whole table at full level for up to an hour. Stage 4 measured 1930 MiB under a 64 MiB cap with no run, and +202 MiB over a 100 MiB cap from new data alone.

**Where:** src/java/org/apache/cassandra/io/sstable/format/big/BigTableWriter.java:254; src/java/org/apache/cassandra/io/sstable/indexsummary/IndexSummaryBuilder.java:126-127; src/java/org/apache/cassandra/io/sstable/indexsummary/IndexSummaryManager.java:141-147,241-242; src/java/org/apache/cassandra/config/DatabaseDescriptor.java:867-869; src/java/org/apache/cassandra/io/util/Memory.java:65,80

## OC-152

**Case file:** `index_summary_capacity-adjustSamplingLevels-remainingSpace--autonomous` · **Agent:** autonomous · **Patterns:** —

Holder: the same native summary memory. Why nothing stops it: redistribution cannot go below the floor ceil(128*min_index_interval/max_index_interval)/128, which is 1/16 of full size at the defaults (128/2048). When the floor sum is above the pool, remainingSpace is <= 0, line 258 is false, and usage stays above the cap indefinitely (stage 4 measured 15.1 MiB at an 8 MiB cap). Rough size at defaults: the floor is about partitions/2048 x (key + 12 B). With about 2e10 partitions of 32 B keys on a node, or 1e9 partitions with 1 KB keys, the floor alone is about 430-500 MB of native memory, permanently above the 5%-of-heap cap.

**Where:** src/java/org/apache/cassandra/io/sstable/indexsummary/IndexSummaryBuilder.java:304; src/java/org/apache/cassandra/io/sstable/indexsummary/IndexSummaryRedistribution.java:258

## OC-153

**Case file:** `index_summary_capacity-distributeRemainingSpace-extraSpaceRequired--autonomous` · **Agent:** autonomous · **Patterns:** —

Holder: off-heap (JNA malloc) BIG index summaries. Why nothing stops it: flush and compaction outputs are built at full sampling level with no capacity check. Only the periodic run (default every 60 min, first run 60 min after start, skipped while compaction is paused, never touching compacting sstables) enforces index_summary_capacity, so between runs usage grows with the data written or compacted. Rough size at defaults: about partitions/128 x (key + 12 B) per table at full level. For 2e9 partitions with 32 B keys that is about 690 MB native, against a default cap of 5% of heap (about 409 MB at an 8 GB heap). Stage 4: 1 M new partitions took usage from 82.6 to 284.8 MiB over a 100 MiB cap with no run.

**Where:** src/java/org/apache/cassandra/io/sstable/format/big/BigTableWriter.java:254; src/java/org/apache/cassandra/io/sstable/indexsummary/IndexSummaryManager.java:141-147,230-242; src/java/org/apache/cassandra/io/sstable/indexsummary/IndexSummaryBuilder.java:126-127; src/java/org/apache/cassandra/io/util/Memory.java:65,80

## OC-154

**Case file:** `index_summary_capacity-distributeRemainingSpace-extraSpaceRequired--autonomous` · **Agent:** autonomous · **Patterns:** —

Holder: native summaries held at the floor or forced up. Why nothing stops it: the floor (1/16 of full at min/max interval 128/2048) is never undercut, so when the floor sum is above the pool, line 341 never runs and usage stays above the cap. Force-resample and force-upsample after interval changes are charged but never refused (stage 4: 808.7 MiB at a 0 MiB cap). Rough size at defaults: floor about partitions/2048 x (key + 12 B). About 430-500 MB at 2e10 small-key or 1e9 1-KB-key partitions, permanently above the 5%-of-heap cap.

**Where:** src/java/org/apache/cassandra/io/sstable/indexsummary/IndexSummaryBuilder.java:304; src/java/org/apache/cassandra/io/sstable/indexsummary/IndexSummaryRedistribution.java:215-234,258,341

## OC-155

**Case file:** `internode_application_send_queue_capacity-releaseCapacity-pendingCapacityInBytes--autonomous` · **Agent:** autonomous · **Patterns:** —

Holder: heap Message/Mutation objects queued on outbound links to slow or non-reading peers (connected but stalled, for example in a GC pause; the link is not failing to connect). Why nothing stops it: the limits count serialized bytes (canonicalSize), not heap. Stage 4 measured about 3.3 heap bytes per counted byte, plus about 42 MiB of already-sent mutations retained by write handlers until timeout. The OTCP case's control saw about 8x (33.5 MB counted, +272.7 MB heap). The per-link 4 MiB is also outside the 512 MiB global reserve, so node-wide counted bytes are 3*N*4 MiB + 512 MiB for N peers. Rough size at defaults: 512 MiB x 3.3 is about 1.7 GB heap from the global reserve alone, plus about 40 MiB heap per stalled peer (100 peers is about 4 GB). That exceeds the default heap of cassandra-env.sh on small and medium hosts (for example 4 GB on a 16 GB host, a quarter of it already given to memtables).

**Where:** src/java/org/apache/cassandra/net/OutboundConnection.java:397,415,1045-1048; src/java/org/apache/cassandra/config/Config.java:250-254; src/java/org/apache/cassandra/net/OutboundConnections.java:84-88; src/java/org/apache/cassandra/service/AbstractWriteResponseHandler.java:81

## OC-156

**Case file:** `largestRatio-flushLargestMemtable-largestRatio--autonomous` · **Agent:** autonomous · **Patterns:** —

Holder: 1 MiB on-heap slab regions, at least one per memtable that has had any write (each table and each 2i memtable) under the default heap_buffers. Why nothing stops it: the pool (memtable_heap_space) counts only the bytes requested, not the 1 MiB region allocated. The largest-first selection at :274 never picks a tiny memtable, so lightly written tables keep their region until some other trigger flushes them (the commit-log total-space reclaim at 8 GiB by default; the flush period defaults to 0). The table-count guardrail is disabled by default. Rough size at defaults: about 1 MiB x the number of written tables and indexes, outside the 1/4-heap memtable budget. 500-1000 tables is about 0.5-1 GiB of extra heap. Stage 4: about 1000 tiny memtables ran a 1 GiB JVM out of heap (about 0.9 GB of live byte[]) while the pool stayed at or below 128 MiB.

**Where:** src/java/org/apache/cassandra/utils/memory/SlabAllocator.java:51,89,139; src/java/org/apache/cassandra/utils/memory/MemtablePool.java:156; src/java/org/apache/cassandra/db/memtable/AbstractAllocatorMemtable.java:258,274; src/java/org/apache/cassandra/config/Config.java:524,865-866

## OC-157

**Case file:** `memtable_heap_space-needsCleaning-nextClean--autonomous` · **Agent:** autonomous · **Patterns:** —

Holder: on-heap 1 MiB slab regions (SlabAllocator, default heap_buffers), one or more per live or flushing memtable. Why nothing stops it: line 128 and tryAllocate compare SubPool.allocated, which counts only the bytes requested (:89), not the 1 MiB region taken from the heap (:139). Every table or 2i memtable with at least one write therefore holds up to about 1 MiB that memtable_heap_space never sees. The cleaner flushes only the largest memtable, so small memtables keep their regions, and the table-count guardrail is off by default. Rough size at defaults: about 1 MiB x the number of written tables and indexes, on top of the 1/4-heap budget. 1000 tables is about 1 GiB of unaccounted heap, which on a 4 GB default heap (16 GB host) is a further 25% beyond memtable_heap_space.

**Where:** src/java/org/apache/cassandra/utils/memory/SlabAllocator.java:51,89,139; src/java/org/apache/cassandra/utils/memory/MemtablePool.java:128,156; src/java/org/apache/cassandra/db/memtable/AbstractAllocatorMemtable.java:274; src/java/org/apache/cassandra/config/Config.java:865-866

## OC-158

**Case file:** `tombstone_failure_threshold-countTombstone-tombstones--autonomous` · **Agent:** autonomous · **Patterns:** —

Holder: the replica's on-heap response DataOutputBuffer (and the coordinator's copies of the RF responses), one per concurrent data read. Why nothing stops it: the threshold counts tombstones, not bytes, so tombstone size (clustering size) is unbounded. It applies per read command, not per node. The byte-based local_read_size_fail_threshold is off by default (read_thresholds_enabled=false). Each growth step copies the buffer (old and new live together, x2 below 64 MiB, then x1.5). Rough size at defaults: T=100,000 x 1 KB tombstones is about 100 MB, peaking at 144-216 MiB per read (stage 4). With concurrent_reads=32 that is about 4.6-7 GB live, while stage 4 saw 4-6 GB of old generation filled with humongous buffers by 8 readers. With 64 KiB clusterings a single read can reach the about 2 GB array cap, about 3 GB with the copy.

**Where:** src/java/org/apache/cassandra/db/ReadCommand.java:591; src/java/org/apache/cassandra/db/ReadResponse.java:199-201; src/java/org/apache/cassandra/io/util/DataOutputBuffer.java:158-181; src/java/org/apache/cassandra/config/Config.java:179,526,535

## OC-159

**Case file:** `index_summary_capacity-distributeRemainingSpace-extraSpaceRequired--autonomous` · **Agent:** guided · **Patterns:** CP-11, CP-10, CP-9

Holder: index summaries of new BIG sstables (flush, compaction and streaming outputs), malloc'd through JNA. Why nothing stops it: the writer builds every summary at full sampling (BASE_SAMPLING_LEVEL) with no check against index_summary_capacity. The cap is applied only by the resize task, every 60 min by default (first run one interval after start-up), and it is never applied when the interval is null or -1. Compaction inputs keep their summaries until the compaction ends, so input and output summaries exist side by side. The memory is outside -Xmx, outside MaxDirectMemorySize and outside NMT, so only the container or kernel bounds it. Rough size at defaults: the cap is 5% of heap, about 409 MiB at an 8 GiB heap. Between runs the excess is the full-level summaries of everything written in the last hour: keys/128 x (key + 12 B). A major compaction of a table with 2e9 partitions of 16-byte keys builds about 440 MB, roughly 1-2x the cap, held for up to 60 min. Stage 4 measured +202 MiB over a 100 MiB cap with no run, and 1930 MiB at a 64 MiB cap before a run. Same mechanism as index_summary_capacity-adjustSamplingLevels-remainingSpace--autonomous; file it once and name both stems.

**Where:** src/java/org/apache/cassandra/io/sstable/format/big/BigTableWriter.java:255 (summary = new IndexSummaryBuilder(..., BASE_SAMPLING_LEVEL)); src/java/org/apache/cassandra/io/sstable/indexsummary/IndexSummaryManager.java:141-147 (periodic-only enforcement); src/java/org/apache/cassandra/io/util/Memory.java:60-65

## OC-160

**Case file:** `index_summary_capacity-distributeRemainingSpace-extraSpaceRequired--autonomous` · **Agent:** guided · **Patterns:** CP-9, CP-8

Holder: bloom filters (OffHeapBitSet), the native neighbour of index summaries. Why nothing stops it: no cap of any kind, sized per sstable from the estimated key count, malloc'd outside every JVM limit, and not counted in index_summary_capacity or any other pool. During compaction the output filter is sized from the inputs' summed key estimate (an overestimate when keys overlap) and coexists with the input filters. Rough size at defaults: bloom_filter_fp_chance 0.01 is about 1.2 B per partition, so 1e9 partitions per node is about 1.1 GiB of native memory, about 2x that during a major compaction. The container is usually sized as heap plus headroom with no budget for it.

**Where:** src/java/org/apache/cassandra/utils/obs/OffHeapBitSet.java:48 (Memory.allocate(byteCount)); src/java/org/apache/cassandra/io/util/Memory.java:60-65

## OC-161

**Case file:** `tombstone_failure_threshold-countTombstone-tombstones--autonomous` · **Agent:** guided · **Patterns:** CP-2, CP-7, CP-12, CP-8

Holder: the replica's on-heap response buffer (DataOutputBuffer in LocalDataResponse.build), one per executing read command. Why nothing stops it: tombstone_failure_threshold counts tombstones, not bytes. One tombstone's size is bounded only by its clustering values (up to 64 KiB per component). The count is per command and per replica, and nothing sums it across the 32 concurrent ReadStage threads (concurrent_reads). The only byte guard, local_read_size_fail_threshold, is off by default (read_thresholds_enabled=false). The buffer grows by 2x up to 64 MiB and by 1.5x beyond, with a full copy each time, so old and new arrays are live together. Rough size at defaults: T = 100,000 x about 1 KB tombstones is about 144 MiB per read (measured in stage 4), so 32 concurrent reads hold about 4.5 GiB, up to about 7.5 GiB during growth copies, against an 8 GiB heap that also holds memtables (heap/4). Stage 4 saw the old generation reach about 6 GB with only 8 concurrent readers.

**Where:** src/java/org/apache/cassandra/db/ReadCommand.java:590-602 (countTombstone, item count); src/java/org/apache/cassandra/db/ReadResponse.java:197-201 (new DataOutputBuffer per response); src/java/org/apache/cassandra/io/util/DataOutputBuffer.java:158-182 (growth copy); src/java/org/apache/cassandra/config/Config.java:179 (concurrent_reads = 32), :526 (read_thresholds_enabled = false)

## OC-162

**Case file:** `tombstone_failure_threshold-countTombstone-tombstones--autonomous` · **Agent:** guided · **Patterns:** CP-7, CP-2, CP-12

Holder: the coordinator, which keeps each replica's serialized data response (RemoteDataResponse ByteBuffer) until all expected responses arrive and are merged. Why nothing stops it: the tombstone cap acts on each replica separately. The coordinator's in-flight request limit counts request bytes, not responses. Concurrent reads per coordinator are bounded only by native_transport_max_threads (128), not by any byte limit. A digest mismatch at QUORUM fetches full data from every contacted replica. A remote response can be up to internode_max_message_size (128 MiB by default) and a local one is unbounded. Rough size at defaults: 128 concurrent tombstone-heavy reads x 1-2 responses x up to 128 MiB is many GiB, far above an 8 GiB heap. Even 16 such reads with about 144 MiB responses is about 2.3 GiB. This is plausible from the source only; stage 4 did not measure the coordinator.

**Where:** src/java/org/apache/cassandra/db/ReadResponse.java:213-221 (RemoteDataResponse holds the ByteBuffer); src/java/org/apache/cassandra/config/Config.java:283 (native_transport_max_threads = 128); src/java/org/apache/cassandra/config/DatabaseDescriptor.java:990-995 (default internode_max_message_size = 128 MiB)

## OC-163

**Case file:** `index_summary_capacity-adjustSamplingLevels-remainingSpace--autonomous` · **Agent:** guided · **Patterns:** CP-11, CP-10, CP-9

Same mechanism as index_summary_capacity-distributeRemainingSpace-extraSpaceRequired--autonomous; file it once and name both stems. Holder: index summaries built at full sampling by every new BIG sstable writer, plus the writer's up-front SafeMemoryWriter sizing from the expected key count. Why nothing stops it: there is no capacity check on the write path. The cap is enforced only by the hourly resize task, or never when the interval is null or -1. Compaction outputs coexist with their inputs' summaries until the compaction ends. The memory is JNA malloc, outside -Xmx and MaxDirectMemorySize. Raising the capacity never re-grows unread summaries; lowering it acts only at the next run. Rough size at defaults: against a cap of about 409 MiB at an 8 GiB heap, the excess is the full-level summaries written in up to 60 min; a major compaction of a dense table (2e9 x 16-byte keys) builds about 440 MB. Stage 4 measured 1930 MiB of summaries at a 64 MiB cap before a run.

**Where:** src/java/org/apache/cassandra/io/sstable/format/big/BigTableWriter.java:255; src/java/org/apache/cassandra/io/sstable/indexsummary/IndexSummaryBuilder.java:105-127 (pre-allocation from expected keys); src/java/org/apache/cassandra/io/sstable/indexsummary/IndexSummaryRedistribution.java:258 (enforcement only inside a run)

## OC-164

**Case file:** `internode_application_send_queue_capacity-releaseCapacity-pendingCapacityInBytes--autonomous` · **Agent:** guided · **Patterns:** CP-1, CP-3, CP-4

Holder: queued and sent Message<Mutation> objects on the coordinator. Why nothing stops it, part 1: the send queue charges canonicalSize (on-wire serializedSize), not heap. Stage 4 measured 3.27 heap bytes per counted byte for blob mutations; small-cell mutations are several times more. Why nothing stops it, part 2: the charge is released when the flush completes, but the write handler keeps the same Mutation as hintOnFailure until a response or the write timeout. That after-flush copy is charged to no counter. A slow or paused replica, at the default 2 s write timeout, keeps arrival rate x timeout x mutation heap live. Rough size at defaults: 4 MiB per link + 128 MiB endpoint reserve + 512 MiB global reserve, all on-wire. At k = 3.3 the global reserve alone is about 1.7 GiB of heap; at k of about 15-20 it is about 8-10 GiB. Stage 4 also measured a C-independent intercept of about 42 MiB from unanswered sent mutations.

**Where:** src/java/org/apache/cassandra/net/OutboundConnection.java:1045-1048 (canonicalSize = serializedSize); :860-866 and :445-454 (release at flush completion); src/java/org/apache/cassandra/db/Mutation.java:158-161 (hintOnFailure returns this); src/java/org/apache/cassandra/service/AbstractWriteResponseHandler.java:81

## OC-165

**Case file:** `internode_application_send_queue_capacity-releaseCapacity-pendingCapacityInBytes--autonomous` · **Agent:** guided · **Patterns:** CP-7, CP-8

Holder: the node-wide outbound backlog across all peers. Why nothing stops it: the per-link capacity C (4 MiB) sits outside both reserves, so the on-wire ceiling is 3 links x N peers x 4 MiB + the 512 MiB global reserve. N is not limited, and the defaults are fixed literals that do not scale with heap; Config.java itself carries 'TODO: derive defaults from system memory settings?'. The inbound receive reserves have the same fixed defaults and share the same heap. Rough size at defaults: 100 peers is about 1.2 GiB + 512 MiB on-wire; at about 3.3 heap bytes per counted byte that is over 5 GiB of heap. On a 2-4 GiB heap, after memtables (heap/4) and the native in-flight reserve (heap/10), any heap factor above about 2.6 on the 512 MiB reserve alone exceeds what is left.

**Where:** src/java/org/apache/cassandra/config/Config.java:248-254 (fixed 4 MiB / 128 MiB / 512 MiB defaults with the TODO); src/java/org/apache/cassandra/net/OutboundConnection.java:397-406 (per-link bytes admitted with no reserve)

## OC-166

**Case file:** `memtable_heap_space-needsCleaning-nextClean--autonomous` · **Agent:** guided · **Patterns:** CP-1, CP-7

Holder: 1 MiB on-heap slab regions, one current region per memtable allocator (one allocator per memtable, including 2i and system tables, live and flushing). Why nothing stops it: the pool charges only the requested bytes (SlabAllocator.java:89), never the region, so a memtable with a few writes holds at least 1 MiB of byte[] while the pool and its cleaner see only KB. The cleaner flushes the largest memtable by counted ratio, so tiny memtables are never chosen. Nothing flushes by age (memtable_flush_period_in_ms 0) and the table count is not limited (tables_fail_threshold -1); only commitlog_total_space eventually flushes them. Rough size at defaults: T written tables x 1 MiB beyond memtable_heap_space (heap/4). 1000 tables is about 1 GiB, 12% of an 8 GiB heap or 50% of a 2 GiB heap, on top of a pool that can still fill to its limit. Stage 4 (largestRatio case, M-first mutant) filled a 1 GiB test heap with about 0.9 GB of live byte[] from about 1000 tiny memtables while the accounted pool stayed at or below L. Same mechanism as largestRatio-flushLargestMemtable-largestRatio--autonomous; file it once and name both stems.

**Where:** src/java/org/apache/cassandra/utils/memory/SlabAllocator.java:89 (charge requested size) and :136-139 (new 1 MiB region, uncounted); src/java/org/apache/cassandra/utils/memory/SlabPool.java:31-33; src/java/org/apache/cassandra/db/memtable/AbstractAllocatorMemtable.java:118; src/java/org/apache/cassandra/config/Config.java:865-866

## OC-167

**Case file:** `largestRatio-flushLargestMemtable-largestRatio--autonomous` · **Agent:** guided · **Patterns:** CP-1, CP-7, CP-14

Same mechanism as memtable_heap_space-needsCleaning-nextClean--autonomous (file it once, name both stems), seen from the selection side. Holder: uncounted 1 MiB slab regions of many small memtables. Why nothing stops it: flushLargestMemtable ranks memtables only by counted ownership ratio. Small but region-holding memtables never win the ratio > largestRatio test, so the pool's cleaner never releases their regions. The hard cap tryAllocate compares counted bytes only, and nothing flushes by age or region count. Rough size at defaults: about 1 MiB x number of tables with any write since their last flush (unbounded table count), on top of memtable_heap_space = heap/4. Stage 4 measured an OOM of a 1 GiB test JVM (about 0.9 GB of live byte[]) with about 1000 tiny memtables while the accounted pool stayed at or below 128 MiB.

**Where:** src/java/org/apache/cassandra/db/memtable/AbstractAllocatorMemtable.java:274 (ratio > largestRatio on counted bytes only); src/java/org/apache/cassandra/utils/memory/SlabAllocator.java:89, :139

## OC-168

**Case file:** `flushLowWaterMark-doRun-flushLowWaterMark--autonomous` · **Agent:** autonomous · **Patterns:** —

Holder: the outbound application send queues. They hold Message objects on the heap, from enqueue until the write completes. Why nothing stops it: each OutboundConnection gets its own 4 MiB pendingCapacityInBytes, and it uses that before it touches the shared reserves (128 MiB per endpoint, 512 MiB global). Each peer has three such connections (urgent, small, large), and nothing limits the peer count. So the node-wide total is about N_peers x 12 MiB + 512 MiB, counted in serialized canonicalSize bytes, plus whatever the deserialized objects add on the heap. The flush water marks (32/64 KiB) only control handing frames to Netty, about 117 KiB per connection in stage 4. Messages that stop at the water marks pile up in this queue. Rough size at defaults: when many peers are slow or partitioned (each queue fills to 4 MiB before isFailingToConnect refuses more), 100 peers give about 1.2 GiB + 512 MiB, about 1.7 GiB, held until expiry. A sustained write load refills the queues.

**Where:** src/java/org/apache/cassandra/net/OutboundConnection.java:311, :325-349, :383-441; src/java/org/apache/cassandra/net/OutboundConnections.java:84-88; src/java/org/apache/cassandra/config/Config.java:250-254; src/java/org/apache/cassandra/net/ConnectionType.java:32

## OC-169

**Case file:** `internode_application_receive_queue_reserve_global_capacity-acquireCapacity-actualExcess--autonomous` · **Agent:** autonomous · **Patterns:** —

Holder: small inbound messages (64 KiB or less). They are deserialized on the event loop as soon as permits are acquired, and the deserialized Mutation objects sit on the heap in the verb stage queue until the handler finishes. Why nothing stops it: permits count serialized on-wire bytes, one per byte, and the class javadoc admits that the on-heap footprint is larger. No check compares heap use with the reserve. Rough size at defaults: the 512 MiB global reserve plus the per-connection allowances, all filled with mutations of many tiny cells. These can take several times their serialized size on the heap (for example 5-15x for small cells), which gives several GiB of heap. That is beside memtables at heap/4.

**Where:** src/java/org/apache/cassandra/net/AbstractMessageHandler.java:131-132, :411-439; src/java/org/apache/cassandra/net/InboundMessageHandler.java:127-149, :155-166, :425-440

## OC-170

**Case file:** `internode_application_receive_queue_reserve_global_capacity-acquireCapacity-actualExcess--autonomous` · **Agent:** autonomous · **Patterns:** —

Holder: the per-connection exclusive queueCapacity (internode_application_receive_queue_capacity, 4 MiB). It lies outside both reserves, and each peer uses three inbound handlers (urgent, small, large). Why nothing stops it: the global 512 MiB limit caps only the excess part (acquireCapacity takes from the reserves only above queueCapacity), and nothing limits the peer count. Rough size at defaults: N x 3 x 4 MiB + 512 MiB. With 100 loaded peers that is about 1.7 GiB of serialized bytes, before the heap inflation above.

**Where:** src/java/org/apache/cassandra/net/AbstractMessageHandler.java:419-436; src/java/org/apache/cassandra/net/MessagingService.java:309-310; src/java/org/apache/cassandra/config/Config.java:256-261

## OC-171

**Case file:** `internode_application_receive_queue_reserve_global_capacity-acquireCapacity-actualExcess--autonomous` · **Agent:** autonomous · **Patterns:** —

Holder: large inbound messages (over 64 KiB). They wait as networking-pool frames in direct memory (LargeMessage buffers) until the handler runs. Stage 4 measured the pool at 1.4-1.5x the accounted bytes. Why nothing stops it: G is a fixed 512 MiB literal and is never compared with MaxDirectMemorySize. cassandra-env sets that to a quarter of RAM (half the heap when auto-sized). Rough size at defaults: 512 MiB x 1.5, about 770 MiB direct, plus N x Q outside the reserve. That is most of a 1-2 GiB direct budget (4-8 GiB RAM hosts), before the networking cache (min(128 MiB, heap/16)) and other direct users.

**Where:** src/java/org/apache/cassandra/net/AbstractMessageHandler.java:522-572; src/java/org/apache/cassandra/net/InboundMessageHandler.java:425-440; conf/cassandra-env.sh:58-67, :158; src/java/org/apache/cassandra/config/DatabaseDescriptor.java:573-574

## OC-172

**Case file:** `maximumPoolSize-setMaximumPoolSize-deltaWorkPermits--autonomous` · **Agent:** autonomous · **Patterns:** —

Holder: the unbounded ConcurrentLinkedQueue of the MutationStage SEPExecutor. Each queued LocalMutationRunnable captures a coordinator-local Mutation. Why nothing stops it: maximumPoolSize (concurrent_writes, 32) only limits workers, and addTask never rejects. The client's native in-flight permit is released when the response is flushed. That happens once the consistency level is met by other replicas, or at the 2 s write timeout. The local task stays queued anyway, and it checks its deadline only after a worker dequeues it. So queued local mutations are counted by no limit. Lowering concurrency at runtime (setconcurrency) makes this worse. Rough size at defaults: backlog of about the local write rate x the time the local stage lags (at least the 2 s timeout). For example, CL=ONE at 5k writes/s of 64 KiB values with this replica lagging gives about 10k tasks x about 70 KiB, about 700 MiB. With 1 MiB values (max_mutation_size 16 MiB) it reaches several GiB. Stage 4 (unit) kept 600 MiB for 600 queued 1 MiB tasks at every n.

**Where:** src/java/org/apache/cassandra/concurrent/SEPExecutor.java:68, :119-145; src/java/org/apache/cassandra/service/StorageProxy.java:1566-1569, :1674-1676, :2636-2655; src/java/org/apache/cassandra/transport/CQLMessageHandler.java:71, :500-509

## OC-173

**Case file:** `maxTasksQueued-addTask-taskPermits--autonomous` · **Agent:** autonomous · **Patterns:** —

Holder: the SEPExecutor tasks queue, an unbounded ConcurrentLinkedQueue. addTask increments the task permits with no comparison, and getMaxTasksQueued is Integer.MAX_VALUE and is never checked. On MutationStage the queue holds coordinator-local LocalMutationRunnables, each with its Mutation. Why nothing stops it: the admission limits only hold while the client request is in flight. The native permit is released when the response is flushed: when the consistency level is met by remote replicas, or at the 2 s write timeout. The queued local task is dropped only when it is dequeued after its deadline. Rough size at defaults: queue depth of about the local write rate x the lag (at least the 2 s timeout). For example, 5k writes/s x 2 s x about 70 KiB (64 KiB values) is about 700 MiB, and several GiB with large values. Stage 4 (unit) measured 88 B + payload per queued task with no cap: the heap ran out at 1.91 M tasks of 1 KiB.

**Where:** src/java/org/apache/cassandra/concurrent/SEPExecutor.java:68, :102-106, :119-145; src/java/org/apache/cassandra/service/StorageProxy.java:1566-1569, :1674-1676, :2636-2655; src/java/org/apache/cassandra/transport/CQLMessageHandler.java:500-509

## OC-174

**Case file:** `maxTasksQueued-takeTaskPermit-taskPermits--autonomous` · **Agent:** autonomous · **Patterns:** —

Holder: the queued tasks of an SEPExecutor. The queue is an unbounded ConcurrentLinkedQueue, and takeTaskPermit only guards against underflow (taskPermits == 0); there is no maximum. On MutationStage each task holds a Mutation (stage 4 cluster: about 157-212 KiB of heap per queued mutation). Why nothing stops it: the native in-flight limit counts only the bytes of requests whose response is not yet flushed. Coordinator-local mutation tasks outlive their request once the consistency level is met elsewhere or the write times out. Expired tasks are discarded only when dequeued. Stage 4 saw the in-flight counter pinned at its 16 MiB cap while 1,996 mutations (about 300 MiB of heap) stayed queued, so the counted bytes are not the queued memory. Rough size at defaults: about the write rate x the lag x the heap per mutation, for example 10k x 70 KiB, about 700 MiB, and far more with large values.

**Where:** src/java/org/apache/cassandra/concurrent/SEPExecutor.java:68, :119-145, :156-185; src/java/org/apache/cassandra/service/StorageProxy.java:1566-1569, :1674-1676, :2636-2655; src/java/org/apache/cassandra/transport/CQLMessageHandler.java:71, :500-509

## OC-175

**Case file:** `memtable_heap_space-adjustMemtableSize-0--autonomous` · **Agent:** autonomous · **Patterns:** —

Holder: the SAI in-memory index of each live or flushing memtable: the trie, PrimaryKey objects, the retained DecoratedKey, Token and key buffers, and doubling trie buffer chunks. Why nothing stops it: only the estimate from TrieMemoryIndex.add is charged to the memtable_heap_space pool (trie allocatedPos plus a 36 B set-entry overhead per key). The per-row key objects and the unused capacity of the doubled buffers are never charged, so the pool can sit at its limit while more heap is held. Rough size at defaults: stage 4 measured about 130 B/row charged and about 323 B/row more held (3.5x, cluster 5.2x). At L = 1024 MiB the peak heap was 1,503 MiB with SAI against 562 MiB without. At the default L = heap/4, memtables with SAI can hold about L plus up to about 1 L uncharged, for example about 2 GiB more on an 8 GiB heap.

**Where:** src/java/org/apache/cassandra/index/sai/StorageAttachedIndex.java:989-1008; src/java/org/apache/cassandra/index/sai/memory/TrieMemoryIndex.java:94-127, :369-378; src/java/org/apache/cassandra/db/tries/InMemoryTrie.java:143-176, :975-981; src/java/org/apache/cassandra/index/sai/utils/PrimaryKey.java:102-120

## OC-176

**Case file:** `memtable_heap_space-adjustMemtableSize-0--autonomous` · **Agent:** autonomous · **Patterns:** —

Holder: SAI segment builders during compaction and index builds, outside the memtable pool. Why nothing stops it: SEGMENT_BUILD_MEMORY_LIMIT is the fixed segment_write_buffer_size literal (1024 MiB) and is not derived from the heap. It is also soft: a builder flushes only once usage exceeds the limit and the builder has reached limit / active builders. Rough size at defaults: up to about 1 GiB of heap on top of memtables (heap/4). That is 25-50% of an auto-sized 2-4 GiB heap (4-8 GiB RAM) during compaction of SAI-indexed tables.

**Where:** src/java/org/apache/cassandra/config/StorageAttachedIndexOptions.java:26, :35; src/java/org/apache/cassandra/index/sai/disk/v1/V1OnDiskFormat.java:126-128, :176; src/java/org/apache/cassandra/index/sai/disk/v1/SSTableIndexWriter.java:225, :245-261; src/java/org/apache/cassandra/index/sai/disk/v1/segment/SegmentBuilder.java:149, :211-214

## OC-177

**Case file:** `native_transport_max_request_data_in_flight-releaseItem-globalInFlightBytesBelowLimit--autonomous` · **Agent:** autonomous · **Patterns:** —

Holder: pooled direct ByteBufs (the frame body slice and the cumulation buffer it pins) of pre-V5 requests rejected on a THROW_ON_OVERLOAD connection. Why nothing stops it: discardAndThrow throws without request.getSource().release(). SimpleChannelInboundHandler cannot release a Message.Request, and ProtocolDecoder releases the source only when decoding fails. So every rejected request leaks its retained slice, and the rejections are not counted against any limit. Rough size at defaults: at least the body size per rejection, with frames up to 16 MiB. Stage 4 saw +3,182 MiB of direct memory after 929 rejections of 1 MiB, still +3,040 MiB with the counter at 0. This grows without bound under sustained overload until direct memory (a quarter of RAM) runs out.

**Where:** src/java/org/apache/cassandra/transport/PreV5Handlers.java:155-160, :239-252, :278-296; src/java/org/apache/cassandra/transport/Envelope.java:448-449

## OC-178

**Case file:** `native_transport_max_request_data_in_flight-releaseItem-globalInFlightBytesBelowLimit--autonomous` · **Agent:** autonomous · **Patterns:** —

Holder: pre-V5 request bodies in pooled direct memory on default (non-throw) connections. Why nothing stops it: when tryAllocate fails, the request is force-allocated and still dispatched (one per connection, plus frames already decoded from the same read). The connection also resumes as soon as its own in-flight bytes reach 0, whatever the global usage. native_transport_max_concurrent_connections is -1. Only bodySizeInBytes is counted, while each slice pins its whole cumulation buffer. Rough size at defaults: heap/10 + C x up to 16 MiB (for example 200 connections, about 3.2 GiB). Real direct use measured about 1.2 GiB + 2.1x the accounted bytes, so the default L = heap/10 (820 MiB at an 8 GiB heap) already used about 3 GiB of direct memory. A 16 GiB-RAM host with an auto-sized heap gets only 4 GiB of direct memory.

**Where:** src/java/org/apache/cassandra/transport/PreV5Handlers.java:82-88, :100-129, :176-186; src/java/org/apache/cassandra/config/Config.java:285, :289; src/java/org/apache/cassandra/transport/Envelope.java:448-449; conf/cassandra-env.sh:58-67

## OC-179

**Case file:** `native_transport_max_request_data_in_flight-releaseItem-globalInFlightBytesBelowLimit--autonomous` · **Agent:** autonomous · **Patterns:** —

Holder: the per-connection exclusive queue of the V5 CQLMessageHandler (native_transport_receive_queue_capacity, 1 MiB). Why nothing stops it: on the default non-throw path, a contained message whose acquireCapacityAndQueueOnFailure fails is still processed (processRequestAndUpdateMetrics at :247) without being charged. After its response, release(header) still calls releaseCapacity(bodySize), which subtracts bytes that were never added. So queueSize drifts below zero by one message per backpressure pause. The connection's exclusive allowance, which lies outside the global and per-IP limits, grows permanently. Rough size at defaults: each pause adds up to one frame-sized message (about 128 KiB or less). Under sustained overload, about 1,000 pauses per connection give about 128 MiB of extra allowance per connection, unbounded over time and across connections. Stage 4 of the sibling case saw RequestsSize pinned at a 16 MiB cap while about 300 MiB of mutations stayed queued (inferred link).

**Where:** src/java/org/apache/cassandra/transport/CQLMessageHandler.java:221-260, :500-510, :693-698; src/java/org/apache/cassandra/net/AbstractMessageHandler.java:146, :411-421, :461-474

## OC-180

**Case file:** `flushLowWaterMark-doRun-flushLowWaterMark--autonomous` · **Agent:** guided · **Patterns:** CP-1, CP-7

Holder: networking BufferPool frames handed to Netty on the small and urgent outbound links. flushingBytes charges canonical message bytes, but a frame that carries one ~2.1 KiB mutation keeps whole 2 KiB pool units, about 4 KiB. Stage 4 measured the pool at about 1.82x the counted in-flight bytes (116 MiB at H=64 MiB). Nothing reconciles the pool with the count, and Netty's own accounting is blind because NoSizeEstimator is installed (OutboundConnectionInitiator.java:197). Size at defaults is small: H=64 KiB per link, so about +60 KiB per link, about 2 links per peer, roughly 25 MiB of direct memory at 100 peers. These bytes are inside the send-queue cap, so this is a minor multiplier and an OOM alone is unlikely. The low mark itself counts nothing.

**Where:** src/java/org/apache/cassandra/net/OutboundConnection.java:851 (charge), :854 (high-mark stop), :782/:810 (pool allocation)

## OC-181

**Case file:** `native_transport_max_request_data_in_flight-releaseItem-globalInFlightBytesBelowLimit--autonomous` · **Agent:** guided · **Patterns:** CP-14, CP-6

Holder: the retained request Envelope body slice (pooled direct ByteBuf) of a request refused on a THROW_ON_OVERLOAD connection. discardAndThrow throws OverloadedException without request.getSource().release(), and SimpleChannelInboundHandler cannot release a non-refcounted Message.Request, so the slice and the cumulation buffer it pins are never returned. The same path runs for the rate-limit and queue-time refusals on these connections. Nothing bounds the leak; it grows with every refusal until MaxDirectMemorySize (default about 1/4 RAM). Stage 4 measured +3,182 MiB of direct memory during the run and +3,040 MiB still held after RequestsSize returned to 0, from 929 refused 1 MiB requests.

**Where:** src/java/org/apache/cassandra/transport/PreV5Handlers.java:155-160, :167-171, :239-252

## OC-182

**Case file:** `native_transport_max_request_data_in_flight-releaseItem-globalInFlightBytesBelowLimit--autonomous` · **Agent:** guided · **Patterns:** CP-1, CP-8

Holder: pre-V5 request memory in pooled direct buffers. The counter charges header.bodySizeInBytes, but the retained slice pins its whole Netty cumulation buffer (Envelope.java:448-449). Pool arena slack and decoded heap copies are also uncounted. Stage 4 measured direct memory at about 1.2 GiB + 2.1x the counted bytes: 3,010 MiB at the default limit of 820 MiB. The default limit is heap/10 (DatabaseDescriptor.java:649-652) while the default direct budget is about heap/2, and nothing compares the two. At the default limit, request buffers alone take about 3/4 of the direct budget of an auto-sized 8 GiB heap, before the networking, chunk-cache and internode pools.

**Where:** src/java/org/apache/cassandra/transport/Envelope.java:448-449; src/java/org/apache/cassandra/config/DatabaseDescriptor.java:649-652

## OC-183

**Case file:** `native_transport_max_request_data_in_flight-releaseItem-globalInFlightBytesBelowLimit--autonomous` · **Agent:** guided · **Patterns:** CP-7, CP-6

Holder: requests force-admitted past the global and per-IP limits. On a default (non-throw) connection the crossing request is force-allocated and dispatched, and so is every frame already decoded in the same read batch. :127 also unpauses a connection as soon as its own in-flight bytes reach 0, even while the global count is above the limit, so every connection can always hold at least one request. Connections are unlimited (native_transport_max_concurrent_connections=-1, Config.java:289) and a frame may be 16 MiB (Config.java:285). The overshoot is therefore about C x (16 MiB + one 64 KiB read) above the limit: 3.2 GiB at 200 connections with 16 MiB frames, plus the 2x direct factor above. Stage 4 confirmed L + C*S exactly at C = 1/8/64 (unit) and 95*S at C = 32 (cluster).

**Where:** src/java/org/apache/cassandra/transport/PreV5Handlers.java:127, :179-185

## OC-184

**Case file:** `native_transport_max_request_data_in_flight-releaseItem-globalInFlightBytesBelowLimit--autonomous` · **Agent:** guided · **Patterns:** CP-3, CP-5, CP-6

Already a phase-2 true positive (C2 and S2), recorded here only so the session can map it. The charge is released in releaseItem when the Flusher hands the response to the channel, not when the socket sends it. V4 response buffers are never charged, and there is no isWritable() check in transport/. At CL=ONE the charge is also released at the first replica ack while the coordinator's own write is still queued on MutationStage.

**Where:** src/java/org/apache/cassandra/transport/PreV5Handlers.java:91-110

## OC-185

**Case file:** `memtable_heap_space-adjustMemtableSize-0--autonomous` · **Agent:** guided · **Patterns:** CP-1, CP-8

Holder: the SAI in-memory index (TrieMemoryIndex) of each live and flushing memtable. TrieMemoryIndex.add charges only the trie bytes in use plus a 36 B set-entry overhead per key. The per-row PrimaryKey, the DecoratedKey/Token/key ByteBuffer it retains, and the trie's doubling buffer slack are never charged, so the memtable_heap_space pool sees only part of the index. Stage 4 measured 129.8 B/row charged and about 323 B/row uncharged (r = 3.5 unit, 5.2 cluster). At the default memtable_heap_space (heap/4; 1 GiB for a 4 GiB heap), peak heap growth was 1.5 GiB with SAI against 0.56 GiB plain. Several SAI indexes per table multiply the uncharged per-row objects.

**Where:** src/java/org/apache/cassandra/index/sai/memory/TrieMemoryIndex.java:94-127; src/java/org/apache/cassandra/index/sai/StorageAttachedIndex.java:1003-1008

## OC-186

**Case file:** `memtable_heap_space-adjustMemtableSize-0--autonomous` · **Agent:** guided · **Patterns:** CP-1, CP-9, CP-8

Holder: the SAI trie buffers under memtable_allocation_type offheap_buffers/offheap_objects. The index trie uses TrieMemtable.BUFFER_TYPE, so it is allocated off heap, but its growth is always charged to the on-heap sub-pool (markExtraOnHeapUsed -> onHeap().allocate). memtable_offheap_space and the direct-memory domain therefore never see it. Direct memory is then the off-heap memtable pool (heap/4) plus up to about heap/4 of charged SAI trie (up to 2x that with buffer slack), plus networking, chunk-cache and request pools, against a direct budget of about heap/2. This applies only in a non-default allocation mode.

**Where:** src/java/org/apache/cassandra/index/sai/memory/TrieMemoryIndex.java:81; src/java/org/apache/cassandra/db/memtable/TrieMemtable.java:94; src/java/org/apache/cassandra/db/memtable/AbstractAllocatorMemtable.java:194-197

## OC-187

**Case file:** `memtable_heap_space-adjustMemtableSize-0--autonomous` · **Agent:** guided · **Patterns:** CP-8, CP-11

Holder: SAI compaction and initial-build segment builders (heap). The global NamedMemoryLimiter default is a fixed 1 GiB (segment_write_buffer_size) and does not scale with the heap. Usage is incremented after each add (SSTableIndexWriter.java:225), and a builder flushes only when global usage already exceeds the limit and the builder has reached limit / active builders (shouldFlush :245-248). That is 1 GiB on top of memtable_heap_space (heap/4) and the other heap pools: on a 4 GiB heap, SAI build buffers plus memtables can take about half the heap during a compaction or index build.

**Where:** src/java/org/apache/cassandra/config/StorageAttachedIndexOptions.java:27,35; src/java/org/apache/cassandra/index/sai/disk/v1/SSTableIndexWriter.java:225, :245-248

## OC-188

**Case file:** `internode_application_receive_queue_reserve_global_capacity-acquireCapacity-actualExcess--autonomous` · **Agent:** guided · **Patterns:** CP-7, CP-8

Already a phase-2 true positive (C1); listed so the session can map it. Each inbound handler's 4 MiB queue capacity (3 handlers per peer) is outside the global reserve G, and G is a literal 512 MiB that nothing compares with MaxDirectMemorySize (about heap/2). Large-message frames sit in the networking pool at 1.4-1.5x the count (stage 4). The node total is N*3*Q + G, which reaches 528-544 MiB at 4-8 loaded peers, equal to the whole direct budget on small hosts.

**Where:** src/java/org/apache/cassandra/net/AbstractMessageHandler.java:419-429; src/java/org/apache/cassandra/net/MessagingService.java:309-310; src/java/org/apache/cassandra/config/Config.java:256-261

## OC-189

**Case file:** `internode_application_receive_queue_reserve_global_capacity-acquireCapacity-actualExcess--autonomous` · **Agent:** guided · **Patterns:** CP-1

Already a phase-2 true positive (B6); listed for mapping. Permits count on-wire bytes, but small messages (64 KiB or less) are deserialized on arrival and held on the heap at about 17x the count for tiny-cell mutations (about 2.2x for blobs), until the verb handler finishes. A 512 MiB reserve can therefore stand for about 8 GiB of heap.

**Where:** src/java/org/apache/cassandra/net/AbstractMessageHandler.java:426; src/java/org/apache/cassandra/net/InboundMessageHandler.java:127, :148-149, :435-442

## OC-190

**Case file:** `maxTasksQueued-takeTaskPermit-taskPermits--autonomous` · **Agent:** guided · **Patterns:** CP-5, CP-2

Holder: the queues of the SEPExecutor stages (MutationStage, ReadStage, CounterMutation, ViewMutation, RequestResponse, Native-Transport-Requests). addTask appends to an unbounded ConcurrentLinkedQueue and increments the task count with no comparison. getMaxTasksQueued() is Integer.MAX_VALUE and is never checked, and the 'block after the fact' comment describes code that is gone. Queue memory is offered rate x residence time x task size. Stage 4 (unit) measured 1,053 MiB at 10^6 1 KiB tasks, and heap OOM at 1.91M tasks on a 2 GiB heap. This is the mechanism behind phase-2 S2. Same mechanism in maxTasksQueued-addTask-taskPermits--autonomous and maximumPoolSize-setMaximumPoolSize-deltaWorkPermits--autonomous; write it once.

**Where:** src/java/org/apache/cassandra/concurrent/SEPExecutor.java:68, :102-106, :119-145

## OC-191

**Case file:** `maxTasksQueued-takeTaskPermit-taskPermits--autonomous` · **Agent:** guided · **Patterns:** CP-3, CP-4, CP-5

Holder: coordinator-local writes (LocalMutationRunnable holding the Mutation) on MutationStage after the request's in-flight charge has been returned. In stage 4 run B at RF=1, RequestsSize was capped at 16 MiB, yet 1,996 mutations stayed queued (about 413 MiB heap, about 26x the cap). This RF=1 case is not S2's first-ack release. Inferred mechanism: the write times out at write_request_timeout (2 s), the error response is flushed and releases the charge, and the task stays queued. When it is finally dequeued past its deadline it is not dropped: it is resubmitted to the MutationStage tail as a HintRunnable holding the same Mutation (enforce_native_deadline_for_hints=false). Client retries keep adding new requests. The only gate is maxHintsInProgress = 128 x cores (StorageProxy.java:202, :1592), which applies only to new writes to a hinted destination. Size: rate x residence, unbounded by any byte limit; 26x the in-flight cap was measured.

**Where:** src/java/org/apache/cassandra/service/StorageProxy.java:2638-2654, :2820-2827

## OC-192

**Case file:** `maxTasksQueued-addTask-taskPermits--autonomous` · **Agent:** guided · **Patterns:** CP-5, CP-2

Same mechanism as the SEPExecutor unbounded-queue candidate under maxTasksQueued-takeTaskPermit-taskPermits--autonomous; write it once and name both stems. Here addTask:131-135 increments with no limit and :135 only decides whether to wake a spinning worker. Stage 4 extra: at RF=1 the queue depth followed multiples of native_transport_max_threads (128), not the in-flight byte cap. Heap net of the memtable was 0.9-1.1 GiB in every arm, including the 32 MiB cap, so per-request memory is largely outside the counted bytes (unexplained, no code pointer).

**Where:** src/java/org/apache/cassandra/concurrent/SEPExecutor.java:123-135

## OC-193

**Case file:** `maximumPoolSize-setMaximumPoolSize-deltaWorkPermits--autonomous` · **Agent:** guided · **Patterns:** CP-7, CP-14

Holder: per-thread state kept by SEP worker threads. Workers that stop spinning are parked, not terminated (SEPWorker.java:118), so their FastThreadLocal scratch survives. DataOutputBuffer.scratchBuffer is recycled at up to 1 MiB per thread (DOB_MAX_RECYCLE_BYTES), and the per-thread BufferPool local pools persist the same way. The thread count is the sum of all SEP stages' maximum pool sizes (4 x 32 concurrent_* + RequestResponse cores + 128 native-transport threads, about 300 at defaults) and grows with setconcurrency or yaml raises. Nothing caps the total, and a shrink keeps the threads already created. Roughly up to 300 MiB of heap retained at defaults; it scales with concurrent_* (for example about 1 GiB at 256 per stage). Related to phase-2 S1 (DOB scratch); the new part is per-thread x thread count.

**Where:** src/java/org/apache/cassandra/io/util/DataOutputBuffer.java:63-73; src/java/org/apache/cassandra/concurrent/SEPWorker.java:118; src/java/org/apache/cassandra/concurrent/SEPExecutor.java:368-396

## OC-194

**Case file:** `maximumPoolSize-setMaximumPoolSize-deltaWorkPermits--autonomous` · **Agent:** guided · **Patterns:** CP-5

Same mechanism as the SEPExecutor unbounded-queue candidate under maxTasksQueued-takeTaskPermit-taskPermits--autonomous; write it once and name this stem too. Lowering maximumPoolSize grows the queue: stage 4 saw Pending 121 at n=4 against 1 at n=256.

**Where:** src/java/org/apache/cassandra/concurrent/SEPExecutor.java:68

## OC-195

**Case file:** `commitlog_segment_size-allocate-endOfBuffer--autonomous` · **Agent:** guided · **Patterns:** CP-8, CP-14

Holder: commit-log segment staging buffers in compressed or encrypted mode. Up to commitlog_max_compression_buffers_in_pool (3) segment-size buffers are in use; creation is gated by atSegmentBufferLimit, and createBuffer itself allocates past the pool when it is empty. On top of that the sync thread keeps a ThreadLocalByteBufferHolder buffer that grows to the needed size (a full segment for encryption) and is never shrunk. The buffers are direct for LZ4 and are not compared with the direct budget. Size: about 4 x 32 MiB = 128 MiB at the default segment size, up to about 8 GiB at the 2047 MiB maximum segment size. Compression and encryption are off by default, so this is small at defaults. Same in commitlog_segment_size-isStillAllocating-endOfBuffer--autonomous.

**Where:** src/java/org/apache/cassandra/io/util/SimpleCachedBufferPool.java (createBuffer); src/java/org/apache/cassandra/io/util/ThreadLocalByteBufferHolder.java:71-77; src/java/org/apache/cassandra/db/commitlog/EncryptedSegment.java:112; src/java/org/apache/cassandra/db/commitlog/CompressedSegment.java:67-68

## OC-196

**Case file:** `commitlog_segment_size-allocate-endOfBuffer--autonomous` · **Agent:** guided · **Patterns:** CP-4, CP-5

Holder: writes queued behind a stalled commit log. When a segment fills, allocate loops into advanceAllocatingFrom/awaitAvailableSegment. In periodic mode writers also block in maybeWaitForSync once the sync lags. A disk stall on the commit-log volume therefore blocks every MutationStage worker, and new writes pile into the unbounded SEP queue (see the SEP candidate). The only bound is rate x stall time x mutation size; a 10 s stall at 50k writes/s of 1 KiB is about 0.5 GiB plus object overhead. Same in commitlog_segment_size-isStillAllocating-endOfBuffer--autonomous.

**Where:** src/java/org/apache/cassandra/db/commitlog/CommitLogSegmentManagerStandard.java:47-60; src/java/org/apache/cassandra/db/commitlog/AbstractCommitLogSegmentManager.java:317, :337; src/java/org/apache/cassandra/db/commitlog/PeriodicCommitLogService.java:36-38

## OC-197

**Case file:** `commitlog_segment_size-isStillAllocating-endOfBuffer--autonomous` · **Agent:** guided · **Patterns:** CP-8, CP-14

Same mechanism as the compressed/encrypted commit-log buffer candidate under commitlog_segment_size-allocate-endOfBuffer--autonomous: up to 3 pooled segment-size buffers plus a never-shrunk per-thread reusable buffer, outside any direct-budget check; about 128 MiB at 32 MiB segments and up to about 8 GiB at 2047 MiB. Write it once and name both stems.

**Where:** src/java/org/apache/cassandra/db/commitlog/CompressedSegment.java:67-68, :113-117; src/java/org/apache/cassandra/db/commitlog/AbstractCommitLogSegmentManager.java:241-244

## OC-198

**Case file:** `commitlog_segment_size-isStillAllocating-endOfBuffer--autonomous` · **Agent:** guided · **Patterns:** CP-4, CP-5

Same mechanism as the commit-log-stall write backlog candidate under commitlog_segment_size-allocate-endOfBuffer--autonomous: writers blocked on segment allocation or sync lag while the SEP queue grows. Write it once and name both stems.

**Where:** src/java/org/apache/cassandra/db/commitlog/AbstractCommitLogSegmentManager.java:337

## OC-199

**Case file:** `key_cache_size-create-size--autonomous` · **Agent:** autonomous · **Patterns:** —

The key cache (and the counter cache, which is built the same way) holds more heap than key_cache_size. The weigher counts only key.unsharedHeapSize() + value.unsharedHeapSize(). Nothing counts Caffeine's own per-entry structures: the node, the ConcurrentHashMap$Node (32 B), the table slot and the frequency-sketch slot, about 90 B per entry. maximumWeight therefore bounds the counted weight but not the real heap. Stage 4 measured 96 B of weight per entry (24-byte key) and a whole-heap increase of 1.9 to 2.0 x Size. Rough size at defaults: key cache = min(5% of heap, 100 MiB), so it really holds about 190 to 214 MiB on a heap of 2 GiB or more. The counter cache (min(2.5%, 50 MiB)) holds about 1.8 x its size. Together that is roughly 100 to 150 MiB above what the two configured sizes promise. This overshoot is bounded and proportional to the cap. A further, smaller effect: after setcachecapacity lowers the cap, Caffeine's tables and sketch stay at the old size (stage 4: 17.3 MB above a fresh run at the new cap).

**Where:** src/java/org/apache/cassandra/cache/CaffeineCache.java:53-57,63-69; src/java/org/apache/cassandra/service/CacheService.java:123,128,176,179; src/java/org/apache/cassandra/config/DatabaseDescriptor.java:815-817,834-836; src/java/org/apache/cassandra/cache/KeyCacheKey.java:59-62

## OC-200

**Case file:** `range_tombstone_list_growth_factor-addInternal-capacity--autonomous` · **Agent:** autonomous · **Patterns:** —

Every range-delete write into a memtable partition that already holds N range tombstones copies the partition's whole RangeTombstoneList. existing.mutableCopy() calls ranges.copy(), which trims all four arrays to size. The add then finds the list full, and growToFree reallocates all four arrays at ceil(N x 1.5). That is about 20 B x N for the copy plus about 30 B x N for the growth, all transient. Only the size delta is charged to the memtable (onAllocatedOnHeap(new - existing)), so nothing bounds these copies. Each optimistic CAS attempt in AtomicBTreePartition repeats the copy; it switches to locking only after 10 MiB of waste, so up to concurrent_writes (32) attempts can each hold a copy. Rough size at defaults: an 8 GiB heap has memtable_heap_space 2 GiB and flushes at about 1/3 of that. At about 500 accounted B per tombstone, one partition can reach about 1.3 M tombstones, so each write allocates about 65 MB, including several multi-MB humongous arrays such as a ClusteringBound[] of about 5 MB. 32 writers in flight would be about 2 GB of transient heap. Even with a single writer, steady writes to that partition generate garbage at about 65 MB x write rate.

**Where:** src/java/org/apache/cassandra/db/partitions/BTreePartitionUpdater.java:120-121; src/java/org/apache/cassandra/db/MutableDeletionInfo.java:83; src/java/org/apache/cassandra/db/RangeTombstoneList.java:105-113,664-689,700-739; src/java/org/apache/cassandra/db/partitions/AtomicBTreePartition.java:63,258-293

## OC-201

**Case file:** `range_tombstone_list_growth_factor-grow-newLength--autonomous` · **Agent:** autonomous · **Patterns:** —

This is the same memtable merge path as in the sibling RTL cases (the target line, grow(int) from copyArrays, does not read the factor). Each write to a memtable partition that holds N range tombstones copies its RangeTombstoneList, trimmed to size, and then grows it by the factor (default 1.5). That is about 50 B x N of transient arrays per write. Only the size delta is charged to the memtable (onAllocatedOnHeap(newInfo - existing)). Contended writers each make their own copy until AtomicBTreePartition's 10 MiB waste tracker switches to locking. Rough size at defaults: on an 8 GiB heap a partition can reach about 1.3 M tombstones before the memtable flushes (about 500 accounted B per tombstone against about 680 MiB), so each write allocates about 65 MB, mostly in humongous arrays. With up to 32 concurrent writes, that is about 2 GB of transient heap that no limit counts.

**Where:** src/java/org/apache/cassandra/db/partitions/BTreePartitionUpdater.java:120-121; src/java/org/apache/cassandra/db/MutableDeletionInfo.java:83; src/java/org/apache/cassandra/db/RangeTombstoneList.java:105-113,680-689,700-739; src/java/org/apache/cassandra/db/partitions/AtomicBTreePartition.java:63,258-293

## OC-202

**Case file:** `range_tombstone_list_growth_factor-growToFree-newLength--autonomous` · **Agent:** autonomous · **Patterns:** —

Each write into a memtable partition with N range tombstones copies the partition's RangeTombstoneList. mutableCopy calls copy(), which trims the arrays to exactly size, so the add then always triggers growToFree to ceil(N x factor). At the default 1.5 that is about 50 B x N of transient allocation per write. It is outside memtable accounting, which charges only the delta, and it is repeated by each contended CAS attempt until the 10 MiB waste tracker forces locking. Rough size at defaults: on an 8 GiB heap a partition can reach about 1.3 M tombstones before the flush (1/3 of memtable_heap_space at about 500 accounted B per tombstone). That gives about 65 MB per write, in multi-MB humongous arrays, and about 2 GB transient with 32 concurrent writes.

**Where:** src/java/org/apache/cassandra/db/partitions/BTreePartitionUpdater.java:120-121; src/java/org/apache/cassandra/db/MutableDeletionInfo.java:83; src/java/org/apache/cassandra/db/RangeTombstoneList.java:105-113,680-689,700-739; src/java/org/apache/cassandra/db/partitions/AtomicBTreePartition.java:63,258-293

## OC-203

**Case file:** `row_cache_size-create-serialized_size--autonomous` · **Agent:** autonomous · **Patterns:** —

With SerializingCacheProvider, clear() (reached from nodetool invalidaterowcache via CacheService.invalidateRowCache) calls invalidateAll(). Its removal cause is EXPLICIT, and the removal listener calls mem.unreference() only when cause.wasEvicted(). So the native RefCountedMemory blocks of every cached entry are never freed, while weightedSize drops to 0. Each invalidate therefore leaks up to row_cache_size of native memory, and repeated calls grow it without bound. Stage 4 saw a second fill peak at 2.36 to 2.48 x C. Not reachable at shipped defaults: row_cache_size is 0MiB and the provider is OHCProvider. It needs row_cache_size > 0 and row_cache_class_name=SerializingCacheProvider.

**Where:** src/java/org/apache/cassandra/cache/SerializingCache.java:54-58,144-147; src/java/org/apache/cassandra/service/CacheService.java:292-294

## OC-204

**Case file:** `row_cache_size-create-serialized_size--autonomous` · **Agent:** autonomous · **Patterns:** —

SerializingCache.put/putIfAbsent/replace mallocs the full serialized partition before Caffeine can evict. With concurrent writers the entries present exceed maximumWeight: stage 4 measured 1.5 to 3.3 x C with 16 writers, and RssAnon at 2.8 to 31 x C including glibc-retained memory. The in-flight overshoot is bounded only by the number of writers times the entry size, and an entry can be up to 2 GiB. Not at defaults (row cache off, OHC provider).

**Where:** src/java/org/apache/cassandra/cache/SerializingCache.java:91-117,166-185,187-207

## OC-205

**Case file:** `row_cache_size-create-serialized_size--autonomous` · **Agent:** autonomous · **Patterns:** —

When a table's caching uses rows_per_partition ALL, a row-cache miss reads the whole partition into an on-heap CachedBTreePartition. That read is not limited by the query's limit, by row_cache_size or by the paging size. On OHC, every later hit also deserializes the whole cached partition onto the heap. Heap per read is therefore about the full partition size, multiplied by concurrent_reads (32). Rough size: 32 x 100 MB partitions is about 3.2 GB. Not at defaults: row_cache_size is 0 and tables default to rows_per_partition NONE.

**Where:** src/java/org/apache/cassandra/db/SinglePartitionReadCommand.java:547-569,604-608; src/java/org/apache/cassandra/cache/SerializingCache.java:149-164

## OC-206

**Case file:** `range_tombstone_list_growth_factor-addInternal-capacity--autonomous` · **Agent:** guided · **Patterns:** CP-1, CP-7

Holder: the full RangeTombstoneList copy that every memtable merge into a partition with range tombstones makes. BTreePartitionUpdater.merge calls existing.mutableCopy(), which runs RangeTombstoneList.copy() and copies all four arrays at size n. add() then grows the copy by the factor. Only the delta newInfo.unsharedHeapSize() - existing.unsharedHeapSize() is charged to the memtable, so the old list and each in-flight copy are never counted. Nothing bounds how many copies exist at once except the writers in flight on that partition: up to concurrent_writes = 32, and more under AtomicBTreePartition CAS retries before the waste tracker forces pessimistic locking. The retained part is over-counted (stage 4: about 504 B counted vs about 275 B live per tombstone), so the memtable flushes at about half the real volume, but the transient part is outside every limit. Rough size at defaults: with an 8 GiB heap, memtable_heap_space is 2 GiB and the flush trigger is about 1/3 of that. One hot partition can hold about 1.3 M range tombstones before a flush. Each in-flight write then holds about (1 + 1.5) x 1.3 M x 20 B = about 65 MB of uncounted young-gen arrays, so 32 concurrent writers hold about 2 GB. Each write also costs O(n) copying (O(n^2) over a fill). The same mechanism shows up in range_tombstone_list_growth_factor-growToFree-newLength--autonomous and range_tombstone_list_growth_factor-grow-newLength--autonomous; file it once.

**Where:** src/java/org/apache/cassandra/db/partitions/BTreePartitionUpdater.java:120-121; src/java/org/apache/cassandra/db/MutableDeletionInfo.java:83; src/java/org/apache/cassandra/db/RangeTombstoneList.java:106-114, :683; src/java/org/apache/cassandra/db/partitions/AtomicBTreePartition.java:153, :239-294; conf/cassandra.yaml:723

## OC-207

**Case file:** `lcs-maxBytesForLevel-fanoutXsstableSize--autonomous` · **Agent:** guided · **Patterns:** CP-7, CP-6

Holder: one open reader per L0 sstable, multiplied by an L0 sstable count that nothing caps. maxBytesForLevel is only a score, and L0 has no byte or count limit. A writer that outpaces LCS builds an L0 backlog: stage 4 saw 46.8x the L0 target in this case and 71-92x in the sibling sstable_size_in_mb cases, with no write refused. Every path that reads L0 opens a separate reader for each L0 sstable at once. LeveledCompactionStrategy.getScanners creates one direct scanner per L0 sstable (L1+ use a LeveledScanner that opens one file at a time). getMaximalTask (nodetool compact on LCS) puts every sstable into one task, and repair validation also goes through getScanners. A single-partition read opens an iterator for every L0 sstable whose bloom filter matches, with no count limit. Each open reader takes a chunk buffer (16 KiB default chunk_length) from the chunk-cache BufferPool. When the pool's file_cache_size (512 MiB) is exhausted, BufferPool.allocate makes direct buffers outside the pool, bounded only by MaxDirectMemorySize. Rough size at defaults: with an overwrite-heavy key present in 1,000 backlogged L0 sstables, 32 concurrent_reads x 1,000 x 16-32 KiB = 0.5-1 GiB of read buffers. That fills the 512 MiB pool and overflows into direct memory. A major compaction or validation over 1,000 L0 files holds about 16-64 MiB per task, plus per-input merge state. The same mechanism applies to sstable_size_in_mb-getCandidatesFor-maxSSTableSizeInBytes--autonomous and sstable_size_in_mb-getnextlevel-candidate-total-bytes--autonomous (L0 backlog), and to sstable_size_in_mb-shouldSwitchWriterInCurrentLocation-maxSSTableSize--autonomous and lcs-level-capacity-shouldSwitchWriterInCurrentLocation-totalWrittenInLevel--autonomous (major LCS compaction opens all L0 scanners at once); file it once.

**Where:** src/java/org/apache/cassandra/db/compaction/LeveledManifest.java:185-193, :258-267, :304-316; src/java/org/apache/cassandra/db/compaction/LeveledCompactionStrategy.java:183-193, :299-331; src/java/org/apache/cassandra/db/SinglePartitionReadCommand.java:757-792; src/java/org/apache/cassandra/io/util/BufferManagingRebufferer.java:45; src/java/org/apache/cassandra/utils/memory/BufferPool.java:233-238, :443-460; src/java/org/apache/cassandra/schema/CompressionParams.java:48

## OC-208

**Case file:** `key_cache_size-create-size--autonomous` · **Agent:** guided · **Patterns:** CP-1

Holder: the key cache's Caffeine BoundedLocalCache, and the counter cache through the same create(long). The weigher charges only key.unsharedHeapSize() + value.unsharedHeapSize(). Per entry it leaves out the Caffeine node (about 40 B), the ConcurrentHashMap$Node (32 B), the table slot and the frequency-sketch slot, about 90 B in all, plus an IndexedEntry's int[] offsets. Eviction keeps the counted weight at C, so nothing stops the real heap from sitting above C. A full cache holds about 2.14 x C at the smallest entries (80 B weight), about 1.65 x C at 64 B keys and about 1.15 x C at 512 B keys. The counter cache holds about 1.80 x C. Rough size at defaults: key_cache_size auto = min(5% of totalMemory, 100 MiB), so about 214 MiB real at the 100 MiB cap (+114 MiB). counter_cache_size auto = min(2.5%, 50 MiB), so about 90 MiB real. The overshoot is bounded and proportional to C, about 7.5% of the heap above contract at defaults. This is the same mechanism as phase-2 B7, which the case file's recheck back-links; it is a confirmation, not a new prediction.

**Where:** src/java/org/apache/cassandra/cache/CaffeineCache.java:53-69; src/java/org/apache/cassandra/cache/KeyCacheKey.java:59-62; src/java/org/apache/cassandra/io/sstable/format/big/RowIndexEntry.java:200-203, :613-621; src/java/org/apache/cassandra/service/CacheService.java:123-128, :176-179; src/java/org/apache/cassandra/config/DatabaseDescriptor.java:814-817, :834-836

## OC-209

**Case file:** `key_cache_size-create-size--autonomous` · **Agent:** guided · **Patterns:** CP-14

Holder: Caffeine's internal hash table and frequency sketch, which are sized for the largest maximum the cache has had. setCapacity (nodetool setcachecapacity, or JMX setKeyCacheCapacityInMB) only calls policy.setMaximum. That evicts down to the new weight, but nothing trims the map table or the sketch, and invalidation does not trim them either. Stage 4 measured this: after a runtime shrink from 64 to 16 MiB, the live heap stayed 17.3 MB above a fresh run at 16 MiB (larger int[], long[] and ConcurrentHashMap$Node[] rows). The case recheck notes about 24 MiB kept at a 100 MiB cache after invalidation. Rough size at defaults: tens of MiB per node, bounded by the largest capacity ever set. An operator who temporarily raises the key or counter cache and then lowers it keeps the larger structures until restart.

**Where:** src/java/org/apache/cassandra/cache/CaffeineCache.java:77-80; src/java/org/apache/cassandra/service/CacheService.java:336-350

## OC-210

**Case file:** `row_cache_size-create-serialized_size--autonomous` · **Agent:** guided · **Patterns:** CP-12, CP-11, CP-10

Holder: a row-cache miss builds the whole partition on heap before any read limit applies. getThroughCache, used when a table has caching rows_per_partition: ALL (or a table without clustering columns has any positive value), runs fullPartitionRead(...).queryMemtableAndDisk. CachedBTreePartition.create then builds every row, range tombstone and cell in memory, whatever the query's LIMIT or slice. This happens inside queryStorage (ReadCommand.java:452), before withMetricsRecording (:461) wraps the result. So tombstone_failure_threshold (100,000) and the paging limits run only after the whole partition is already on heap, and its range tombstones land in a RangeTombstoneList through the build. With SerializingCacheProvider, the partition is then serialized into a malloc block of the full size before Caffeine can evict an entry heavier than the cache. Nothing bounds the partition size except the data. Rough size: not reachable at shipped defaults (row_cache_size = 0 selects NopCacheProvider). With any row cache on and caching ALL, one read of a 1 GB on-disk partition builds several GB of objects, and 32 concurrent_reads can each build one.

**Where:** src/java/org/apache/cassandra/db/SinglePartitionReadCommand.java:506, :547-549, :569, :604; src/java/org/apache/cassandra/db/ReadCommand.java:452, :461, :525-601; src/java/org/apache/cassandra/db/partitions/CachedBTreePartition.java:82-84; src/java/org/apache/cassandra/cache/SerializingCache.java:166-170

## OC-211

**Case file:** `row_cache_size-create-serialized_size--autonomous` · **Agent:** guided · **Patterns:** CP-14, CP-9

Holder: native malloc blocks of SerializingCache entries left alive after clear(). clear() calls cache.invalidateAll(). The removal cause is EXPLICIT, so cause.wasEvicted() is false and the listener never calls mem.unreference(). weightedSize drops to 0 while every native block stays allocated. Each nodetool invalidaterowcache therefore leaks up to row_cache_size of native memory outside both JVM limits. Stage 4 confirmed it: a second fill after clear() peaked at 2.36-2.48 x C in 3 reps. Rough size: 0 at shipped defaults (row_cache_size 0, provider OHCProvider). With row_cache_class_name SerializingCacheProvider and size C, each invalidate leaks C, cumulatively until restart.

**Where:** src/java/org/apache/cassandra/cache/SerializingCache.java:54-58, :144-147

## OC-212

**Case file:** `row_cache_size-create-serialized_size--autonomous` · **Agent:** guided · **Patterns:** CP-11, CP-9

Holder: in-flight and freed-but-retained native memory of SerializingCache. put() mallocs the serialized partition before insertion, and putIfAbsent and replace allocate before checking. Eviction maintenance runs behind concurrent writers, so the cap is enforced after the allocation. Stage 4 saw 1.5-3.3 x C of entries present with 16 writers at C = 64 MiB. The freed blocks stay in glibc arenas: RssAnon peaked at 2.8-31 x C, and was still 1.0-2.0 x C after malloc_trim. Lowering capacity at runtime evicts at once but does not lower RSS. Stage 4 got 853 MiB back only through malloc_trim. All of this is native memory that only the container or kernel limit bounds. Rough size: 0 at shipped defaults (row cache off, OHC provider). With SerializingCacheProvider at C = 1 GiB, several GiB of RSS above the configured cap.

**Where:** src/java/org/apache/cassandra/cache/SerializingCache.java:50-53, :91-117, :166-185, :187-207

## OC-213

**Case file:** `chunk_length_in_kb-loadNextChunk-compressedChunk--autonomous` · **Agent:** autonomous · **Patterns:** —

Per-file streaming chunk metadata held on the heap, with no cap. This path runs at defaults for any compressed SSTable that is only partly inside the streamed ranges (repair, partial bootstrap, decommission). The receiver reads chunkCount from the wire and allocates new Chunk[chunkCount] plus one Chunk object (offset long + length int) per chunk. It keeps them for the whole file transfer. On the sender, getChunksForSections builds a TreeSet of every chunk in the sections and then an array. The lazy CompressionInfo holds that array until the file is acked. Nothing limits chunkCount except section length / chunk_length_in_kb. Rough size at the default 16 KiB chunks: about 28 B per chunk on the receiver (24 B Chunk + 4 B slot). The sender's TreeSet costs about 64-70 B per chunk while it is built. A 256 GiB uncompressed section (a large STCS SSTable) has about 16.7M chunks: about 470 MB held on the receiver and about 1.1 GB transient on the sender, per file. This is multiplied by concurrent sessions (several peers in repair or bootstrap) against a default heap of at most 8 GB.

**Where:** src/java/org/apache/cassandra/db/streaming/CompressionInfo.java (CompressionInfoSerializer.deserialize: `new CompressionMetadata.Chunk[chunkCount]`; newLazyInstance caches `chunks`); src/java/org/apache/cassandra/io/compress/CompressionMetadata.java:314-338 (getChunksForSections TreeSet), :564 (Chunk deserialize); src/java/org/apache/cassandra/db/streaming/CassandraOutgoingFile.java:79-80; src/java/org/apache/cassandra/db/streaming/CassandraStreamHeader.java:212; src/java/org/apache/cassandra/streaming/StreamTransferTask.java:89 (released only on ack)

## OC-214

**Case file:** `chunk_length_in_kb-loadNextChunk-compressedChunk--autonomous` · **Agent:** autonomous · **Patterns:** —

The receive-side direct buffer `compressedChunk` is regrown to whatever chunk length the stream header declares. There is no ceiling apart from MaxDirectMemorySize. The old buffer is freed and allocateDirect(max(1.5*cap, chunkLength)) runs before the chunk is read or its CRC is checked. With the default min_compress_ratio 0, maxCompressedLength is Integer.MAX_VALUE, so every declared length takes this branch. An honest sender gives only 1.5x the chunk (24 KiB at defaults). A bad offset in the sender's -CompressionInfo.db (chunk length = nextOffset - offset - 4), or a bad peer header, makes one stream allocate up to about 2 GiB of direct memory. Stage 4 showed a declared 128 MiB chunk under a 16 KiB option making a 128 MiB buffer. Each concurrent incoming stream can do this.

**Where:** src/java/org/apache/cassandra/db/streaming/CompressedInputStream.java:135,142-150; src/java/org/apache/cassandra/io/compress/CompressionMetadata.java:334,564

## OC-215

**Case file:** `entry-size-limit-serialize-serializedSize--autonomous` · **Agent:** guided · **Patterns:** CP-14, CP-3, CP-9

Holder: the native (malloc) blocks of a SerializingCache row cache. clear(), which is how `nodetool invalidaterowcache` / CacheServiceMBean.invalidateRowCache reach it (CacheService.java:292-294), calls Caffeine invalidateAll() (removal cause EXPLICIT). The removal listener frees memory only when cause.wasEvicted(), so the weight goes to 0 while every RefCountedMemory stays allocated and is never freed. Nothing stops it: the cache then refills up to row_cache_size again, and each invalidation leaks up to one full row_cache_size of native memory outside -Xmx, MaxDirectMemorySize and NMT. Stage 4 found it in a unit probe: size()/weightedSize() 0 after clear() on a 64 MiB cache, RssAnon still +57 MiB. Size: row_cache_size per invalidation, unbounded over repeated invalidations. NOT at shipped defaults: it needs row_cache_class_name: SerializingCacheProvider and row_cache_size > 0 (the defaults are OHCProvider and 0MiB).

**Where:** src/java/org/apache/cassandra/cache/SerializingCache.java:144-147 (clear -> invalidateAll), :53-58 (listener frees only on eviction); src/java/org/apache/cassandra/service/CacheService.java:292-294

## OC-216

**Case file:** `entry-size-limit-serialize-serializedSize--autonomous` · **Agent:** guided · **Patterns:** CP-11, CP-6, CP-9

Holder: the RefCountedMemory that serialize() mallocs for each row-cache put/replace. The full serialized partition is malloc'd before the entry is admitted to Caffeine and weighed, so in-flight entries are charged nowhere. An entry larger than the capacity is allocated in full and only then evicted. Nothing bounds the in-flight total except the 2 GiB per-entry guard: one entry per concurrent caching read (concurrent_reads 32), each the cached partition's serialized size, on top of the same partition already built on heap. Stage 4 measured 4,058 MiB native in flight at C = 64 MiB (8 x 512 MiB entries) and 263-422 MiB on a node with Size 0. Size: up to 32 x the largest cached partition. NOT at shipped defaults (SerializingCacheProvider and a non-zero row_cache_size are required).

**Where:** src/java/org/apache/cassandra/cache/SerializingCache.java:100 (malloc before admission), :175/:196/:236 (insert after allocation); src/java/org/apache/cassandra/db/SinglePartitionReadCommand.java:561-608

## OC-217

**Case file:** `chunk_length_in_kb-loadNextChunk-compressedChunk--autonomous` · **Agent:** guided · **Patterns:** CP-12, CP-7

Holder: the streaming chunk index, built whole on heap per streamed compressed SSTable section and charged to no budget. The sender builds a TreeSet<Chunk> of every chunk of the requested sections (about 64 B per chunk: a TreeMap.Entry plus a 24 B Chunk), then a Chunk[]. The array is cached in the lazy CompressionInfo of the outgoing file's header until the file completes. The receiver deserializes the same Chunk[] (about 28 B per chunk) and holds it while it reads the file. Nothing stops it: there is no limit on the section size or chunk count, and the default chunk_length_in_kb is 16. Partial-range streaming (repair, bootstrap with vnodes) uses this path even with stream_entire_sstables: true. Size at defaults: about 28 B per 16 KiB of uncompressed data on the receiver, about 64-92 B per 16 KiB transiently on the sender. A 100 GiB section gives about 175 MiB receiver heap and about 420 MiB + 175 MiB on the sender. This is multiplied by the concurrent inbound or outbound files (one per peer session) and no limit caps the sum.

**Where:** src/java/org/apache/cassandra/io/compress/CompressionMetadata.java:317-338 (sender TreeSet + toArray); src/java/org/apache/cassandra/db/streaming/CompressionInfo.java:139-144 (lazy cache), :188-193 (receiver Chunk[]); src/java/org/apache/cassandra/db/streaming/CassandraOutgoingFile.java:79-81

## OC-218

**Case file:** `chunk_length_in_kb-loadNextChunk-compressedChunk--autonomous` · **Agent:** guided · **Patterns:** CP-13, CP-6

Holder: heap and direct allocations sized from peer-supplied stream header fields before any validation. CompressionInfo deserialize reads chunkCount with a bare readInt and allocates new Chunk[chunkCount] at once: up to 2^31-1 references, about 8 GiB of heap with compressed oops, before any chunk is read. Each chunk length (also a bare readInt) regrows the direct compressedChunk buffer to max(1.5 x capacity, length) with no ceiling, up to about 2 GiB per stream, before the CRC is checked. Nothing stops it except the JVM heap and direct limits, so the enforcement is OutOfMemoryError, which JVMStabilityInspector rethrows. Reachable by any internode peer, or by a corrupt or malicious stream (the default internode_authenticator allows all). Size: up to about 8 GiB heap per header and about 2 GiB direct per stream.

**Where:** src/java/org/apache/cassandra/db/streaming/CompressionInfo.java:188-192; src/java/org/apache/cassandra/db/streaming/CompressedInputStream.java:135,144-150

## OC-219

**Case file:** `file_cache_size-CompressedChecksummedDataInput-readBuffer-compressedBuffer--autonomous` · **Agent:** guided · **Patterns:** CP-13, CP-6, CP-10

Holder: the compressed and decompressed hint read buffers. readBuffer() takes uncompressedSize and compressedSize straight from each block's 8-byte on-disk header and allocates compressedSize*1.05 and uncompressedSize*1.05 from the chunk-cache BufferPool. Requests above 128 KiB go straight to allocateDirect or a heap array, outside file_cache_size. Nothing checks the sizes against max_mutation_size or the file length before allocating; the data checksum is verified only after the read. So a corrupt or torn block header in a hints file (crash, bit rot) asks for up to about 2 GiB direct, plus 2 GiB for the decompressed buffer. Nothing stops it before the JVM's 'Direct buffer memory' OutOfMemoryError, which JVMStabilityInspector rethrows. Values above about 2.04e9 overflow the int and fail differently. Size: up to about 4 GiB per hint reader, max_hints_delivery_threads (2) readers at once. Only with hints_compression set (commented out in the shipped yaml); the honest worst case is about 2 x 17 MiB per reader.

**Where:** src/java/org/apache/cassandra/hints/CompressedChecksummedDataInput.java:115-125 (compressed buffer sized from header), :134-138 (decompressed buffer); src/java/org/apache/cassandra/utils/memory/BufferPool.java:206-211,233-238 (overflow path, no threshold check)

## OC-220

**Case file:** `hints-HintsBuffer-put-slabCapacity--autonomous` · **Agent:** autonomous · **Patterns:** —

Heap backlog in front of the capped slab pool. Each hint is a HintRunnable on the unbounded MUTATION stage queue, and it pins its whole Mutation until HintsBufferPool.write returns. When all 3 slabs are in flight, the writing threads park in reserveBuffers.take(), so the runnables and their mutations pile up on the heap. The 96 MiB slab cap only bounds direct memory. The only upstream gate, checkHintOverload, counts hints, not bytes (maxHintsInProgress = 128 x cores). It applies only to new coordinator writes to a destination that already has hints in progress. Hints submitted on write failure or timeout, local-mutation timeout hints, batchlog/hintMutation and Paxos commit hints skip it. Rough size at defaults: 128 x cores x mutation size, so 2,048 pinned mutations on a 16-core node. That is about 2 GiB at 1 MiB mutations and up to 32 GiB at the 16 MiB max_mutation_size, against an auto heap of RAM/2.

**Where:** service/StorageProxy.java:202, :1585-1598, :2822-2826, :2640-2655, :975-988; service/AbstractWriteResponseHandler.java:309-310; hints/HintsBufferPool.java:59-66, :113-118; hints/HintsService.java:161-170

## OC-221

**Case file:** `hints-CompressedHintsWriter-compressionBuffer-capacity--autonomous` · **Agent:** autonomous · **Patterns:** —

Needs hints_compression on (it is off by default). Every open CompressedHintsWriter keeps a grow-only direct compressionBuffer sized to the largest block it has compressed. No hints knob bounds it, and it is never freed while the writer is open. There is one writer per peer with pending hints. Writers for down peers stay open until the file reaches max_hints_file_size (128 MiB), because HintsDispatchTrigger closes writers only for live stores. Rough size at defaults: up to 16,843,037 B (about 16.06 MiB) per down peer that has received a hint over 256 KiB. That is about 1.6 GiB for 100 down peers (for example a remote-DC outage), stacked on the 96 MiB of slabs, against a direct budget of RAM/4. Replaced buffers are left for GC to free, so peaks are higher (stage 4 saw 362 MiB with file churn).

**Where:** hints/CompressedHintsWriter.java:39, :48-56; hints/HintsStore.java:295-300, :322-330; hints/HintsDispatchTrigger.java:57-70; hints/HintsWriteExecutor.java:222-229; hints/HintsWriter.java:205-221

## OC-222

**Case file:** `hints-CompressedChecksummedDataInput-readBuffer-uncompressedSize--autonomous` · **Agent:** autonomous · **Patterns:** —

Needs hints_compression on (off by default) and a corrupt hints file. The 8-byte block header (uncompressedSize, compressedSize) has no checksum and is never validated. Both values go straight into bufferPool.get(size x 1.05). Anything over 128 KiB bypasses the file_cache_size pool and becomes an unpooled allocateDirect with no threshold check. One bit-flipped or torn header can therefore ask for up to about 2.1 GB for compressedBuffer plus about 2.1 GB for the output buffer, roughly 4.3 GB of direct memory. That exceeds the default MaxDirectMemorySize (RAM/4, for example 4 GiB on a 16 GB node), so the dispatch thread gets OutOfMemoryError: Direct buffer memory and the corrupt file is not handled. Stage 4 read a forged 512 MiB header and allocated 563,714,457 B with no error.

**Where:** hints/CompressedChecksummedDataInput.java:110-139; utils/memory/BufferPool.java:233-239, :263, :940-943

## OC-223

**Case file:** `sai-SegmentRowIdOrdinalPairs-add-capacity--autonomous` · **Agent:** autonomous · **Patterns:** —

Weak lead. A key-range-restricted ANN search takes the brute-force path whenever nRows <= maxBruteForceRows, and that threshold grows with graph size and LIMIT. It then allocates int[2 x nRows] up front, plus a NeighborQueue of the same count (mapToSegmentRowIdScoreHeap). Both stay live in the returned iterator until the query is consumed, one set per segment per sstable. No byte budget applies, only the cost-model threshold. Rough size at defaults: about 16 B per row in range. Computed from the threshold formula, the largest brute-force range is about 394k rows (about 6.3 MB) for a 1M-node segment and about 2.3M rows (about 37 MB) for a 10M-node segment at LIMIT 1000. This is summed over all sstables a query touches and multiplied by concurrent_reads 32, so about 2 GB for 32 queries over 10 x 1M-row sstables.

**Where:** index/sai/disk/v1/segment/VectorIndexSegmentSearcher.java:155-175, :239-255, :353-365; index/sai/disk/v1/vector/SegmentRowIdOrdinalPairs.java:40-46, :100-107; index/sai/memory/VectorMemoryIndex.java:275-286

## OC-224

**Case file:** `sasi-max_compaction_flush_memory-PerSSTableIndexWriter-estimatedMemoryUse--autonomous` · **Agent:** autonomous · **Patterns:** —

Needs sasi_indexes_enabled: true (off by default); the index options are left at their defaults. In CONTAINS mode, OnDiskIndexBuilder.finish builds a SuffixSA. It decodes every term into a CharBuffer (2 B/char), allocates long[charCount] (8 B/char) and TimSorts it (up to 4 B/char of scratch). None of this is in estimatedMemoryUse, which charges only term bytes + 112 + 108 per posting. With 1023-byte terms and the default 0.15 GiB compaction cut (about 129,575 terms, 132.5M chars), one segment finish needs about 1.06 GB of long[], about 265 MB of chars and up to about 530 MB of sort scratch. That is about 1.9 GB, roughly 12x the 153.6 MiB cap. Up to 8 finishes can run at once on SASI-General.

**Where:** index/sasi/disk/OnDiskIndexBuilder.java:182, :194, :253-260; index/sasi/sa/SA.java:47-53; index/sasi/sa/SuffixSA.java:41, :64, :84; index/sasi/disk/PerSSTableIndexWriter.java:63-73, :247-250

## OC-225

**Case file:** `sasi-max_compaction_flush_memory-PerSSTableIndexWriter-estimatedMemoryUse--autonomous` · **Agent:** autonomous · **Patterns:** —

Needs SASI enabled. Builders that reach the cap are handed to the 8-thread SASI-Memtable or SASI-General pool, whose queue is unbounded. The writer never waits (segments.add(submit)) and immediately starts a new builder, so full builders pile up whenever finish is slower than the data feed. On flush the cut is a hard-coded 1 GiB estimate that ignores max_compaction_flush_memory_in_mb. Real heap is about 1.8x the estimate (stage 4: about 400 B/entry vs 224), and stage 4 saw 4-5 builders live at once. Rough size at defaults: about 280 MB real per builder at the compaction cut, and up to about 1.8 GB per builder at the flush cut. Multiply by indexed columns, concurrent compactions and the 2 flush writers.

**Where:** index/sasi/disk/PerSSTableIndexWriter.java:63-73, :247-250, :254-257, :349-352, :365-369; index/sasi/conf/IndexMode.java:59-60

## OC-226

**Case file:** `sasi-max_term_size-OnDiskIndexBuilder-add-termSize--autonomous` · **Agent:** autonomous · **Patterns:** —

Needs SASI enabled. MAX_TERM_SIZE lets 1023-byte terms through, and in CONTAINS mode their memory cost at finish is per character and goes uncounted by estimatedBytes. The term map charges 1023 + 112 + 108 = 1,243 B per term. SuffixSA then needs about 14 B per char (UTF-8 to CharBuffer copy, long[charCount], TimSort scratch), about 14.3 KB per 1023-byte term, roughly 11.5x the estimate. Rough size at the default 0.15 GiB compaction cut: about 1.9 GB per segment finish, with up to 8 finishes in parallel on SASI-General.

**Where:** index/sasi/disk/OnDiskIndexBuilder.java:128, :167-194, :253-260; index/sasi/sa/SuffixSA.java:41, :64, :84; index/sasi/sa/SA.java:47-53

## OC-227

**Case file:** `sasi-max_term_size-OnDiskIndexBuilder-add-termSize--autonomous` · **Agent:** autonomous · **Patterns:** —

Needs SASI enabled. The term-size check is per token, and the builder's size check runs only after a whole value has been added. A tokenized value of any size is therefore added in full first, and the size of a value is bounded only by max_mutation_size (16 MiB). Rough size at defaults: one 16 MiB value of distinct 7-byte words is about 2.1M terms x 227 B, about 476 MB of estimate and about 860 MB real (1.8x). That is about 3x the 153.6 MiB compaction cap, per index per writer (stage 4: a 1 MiB value made a cut at 28.4x a 1 MiB cap).

**Where:** index/sasi/disk/PerSSTableIndexWriter.java:212-250; index/sasi/disk/OnDiskIndexBuilder.java:175-194

## OC-228

**Case file:** `sasi-max_term_size-PerSSTableIndexWriter-addTerm-termSize--autonomous` · **Agent:** autonomous · **Patterns:** —

Needs SASI enabled. MAX_TERM_SIZE caps each token, but the number of tokens per value is unbounded, and the estimatedMemoryUse check at :247 runs only after every token of the value has been added to the builder. One value from a tokenizing analyzer can push the builder far past maxMemorySize. Rough size at defaults: a 16 MiB value (the max_mutation_size default) of distinct 7-byte words is about 2.1M terms x 227 B, about 476 MB of estimate and about 860 MB real heap, per index per sstable writer. Several can be in flight across concurrent compactions and the 2 flush writers.

**Where:** index/sasi/disk/PerSSTableIndexWriter.java:205-250; index/sasi/disk/OnDiskIndexBuilder.java:175-194

## OC-229

**Case file:** `sasi-max_term_size-PerSSTableIndexWriter-addTerm-termSize--autonomous` · **Agent:** autonomous · **Patterns:** —

Needs SASI enabled. In CONTAINS mode, terms of up to 1023 bytes that pass this check are expanded at segment finish into a suffix array (long[charCount] + CharBuffer copies + TimSort scratch, about 14 B/char). The estimate does not count it. About 1.9 GB per segment at the default 0.15 GiB compaction cut with 1023-byte terms, and up to 8 in parallel.

**Where:** index/sasi/disk/OnDiskIndexBuilder.java:253-260; index/sasi/sa/SuffixSA.java:41, :64, :84

## OC-230

**Case file:** `sasi-max_term_size-TrieMemIndex-add-termSize--autonomous` · **Agent:** autonomous · **Patterns:** —

Needs SASI enabled. In CONTAINS mode with a tokenizing analyzer, TrieMemIndex.add puts every suffix of every token (up to 255 chars with StandardAnalyzer, under 1024 bytes) into the ConcurrentSuffixTrie. All tokens of the value go in before any accounting. The size is reported to the memtable only afterwards (adjustMemtableSize, then markExtraOnHeapUsed), so neither memtable_heap_space nor a flush can stop one write's growth. The cost per term grows by about L^1.7: 1.69 MB of estimate at 1023 chars, so about 157 KB of estimate (about 80 KB real) per distinct 255-char token. Rough size at defaults: a 1 MiB value of distinct 255-char tokens is about 4,096 tokens, about 330 MB of real heap per write. A 16 MiB value (max_mutation_size) is about 5 GB. concurrent_writes is 32.

**Where:** index/sasi/memory/TrieMemIndex.java:59-63, :74-97, :116-137; index/sasi/SASIIndex.java:297-321; db/memtable/AbstractAllocatorMemtable.java:194-197; index/sasi/analyzer/StandardTokenizerOptions.java:35

## OC-231

**Case file:** `hints-CompressedChecksummedDataInput-readBuffer-uncompressedSize--autonomous` · **Agent:** guided · **Patterns:** CP-13, CP-6

Holder: the hint dispatch reader's decompression and compressed buffers (one reader per dispatched file, max_hints_delivery_threads=2). Each block's 8-byte header gives uncompressedSize and compressedSize (:115-116). Both values go straight to bufferPool.get(size + size/20) (:125, :138). No check runs before the allocation: per-hint CRCs are checked only after decompression, and there is no upper bound on the header values. Requests above 128 KiB bypass the chunk-cache pool as a plain allocateDirect. That allocation is counted only in overflowMemoryUsage and no threshold applies (BufferPool.java:233-239, :940-943), so the only stop is -XX:MaxDirectMemorySize. A corrupt or forged hint file (torn write, disk fault, copied file) sizes the allocation from garbage. Rough size: stage 4 measured 563,714,457 B direct allocated, without error, from a 512 MiB header over a 2 KiB block. Up to about 2.2 GB per header field per reader. Legitimate files: about 2 x 1.05 x 16 MiB = about 35 MB per reader. Reachable only with hints_compression set (non-default). Same unvalidated-header mechanism as the encrypted reader (hints-EncryptedChecksummedDataInput-reusableBuffers-decryptBuffer--autonomous).

**Where:** src/java/org/apache/cassandra/hints/CompressedChecksummedDataInput.java:115-138; src/java/org/apache/cassandra/utils/memory/BufferPool.java:233-239,940-943

## OC-232

**Case file:** `hints-CompressedChecksummedDataInput-readBuffer-uncompressedSize--autonomous` · **Agent:** guided · **Patterns:** CP-14, CP-8, CP-6

Holder: the chunk-cache BufferPool (file_cache_size, default min(512 MiB, heap/4)). close() returns only compressedBuffer (:157). The reader's own buffer goes to FileUtils.clean (ChecksummedDataInput.java:244), which does nothing for a pooled slice because the slice has no cleaner. Each hint file whose largest block is at most 124,831 B gets its reader buffer (at most 128 KiB) served from the pool. Every open/close of such a file, including each dispatch retry, therefore leaks one pool slot and pins its chunk. Nothing returns it, and the leak continues until the pool reaches its threshold. After that the chunk cache and the other pooled readers fall back to unbounded overflow allocateDirect, so direct memory runs past the file_cache_size budget. Rough size: up to 128 KiB per small-file read; about 4,096 such reads (low hint rate, flapping peer, retries every 10 s) pin all 512 MiB. Stage 4 found the slot not returned on close but did not run the accumulation. Non-default (hints_compression).

**Where:** src/java/org/apache/cassandra/hints/CompressedChecksummedDataInput.java:134-138,155-158; src/java/org/apache/cassandra/hints/ChecksummedDataInput.java:242-245; src/java/org/apache/cassandra/utils/memory/BufferPool.java:443

## OC-233

**Case file:** `hints-CompressedHintsWriter-compressionBuffer-capacity--autonomous` · **Agent:** guided · **Patterns:** CP-7, CP-14, CP-8

Holder: CompressedHintsWriter.compressionBuffer, an off-heap LZ4 buffer, one per open hints writer, i.e. one per peer with pending hints (HintsStore.getOrOpenWriter). It grows to the largest block ever compressed and never shrinks (:53-56). It is held as long as the writer stays open: until the file reaches max_hints_file_size (128 MiB) or dispatch/shutdown closes it, which for a peer down for hours with a trickle of hints is a long time. No limit caps the sum over peers. The buffer is outside the file_cache_size pool and outside the 3 x 32 MiB hint-slab cap, and max_hints_size_per_host does not bound it (stage 4, H1). Rough size: up to 16,843,037 B (16.06 MiB) per peer that ever received a hint of about 16 MiB. Stage 4 measured 16.07 MiB for two peers. With 50 down peers (DC outage) about 800 MiB of direct memory, against MaxDirectMemorySize. A small max_hints_file_size also churns these buffers: stage 4 saw a 362 MiB peak of unreferenced direct buffers waiting for GC. Non-default (hints_compression).

**Where:** src/java/org/apache/cassandra/hints/CompressedHintsWriter.java:51-56; src/java/org/apache/cassandra/hints/HintsStore.java:295-300,322-330

## OC-234

**Case file:** `hints-EncryptedChecksummedDataInput-reusableBuffers-decryptBuffer--autonomous` · **Agent:** guided · **Patterns:** CP-9, CP-13, CP-14

Holder: the HintsDispatcher thread. EncryptionUtils.decrypt sizes a heap ByteBuffer from the unvalidated block header, max(encryptedLength, plainTextLength) (:148). It then reads into it through a FileChannel (:150), so the JDK allocates a temporary direct buffer of the same size and caches it per thread. jdk.nio.maxCachedBufferSize is not set in conf/jvm*-server.options, so this cache is bounded by neither the heap limit nor any Cassandra pool. After a complete read the heap buffer is also kept in the FastThreadLocal reusableBuffers (EncryptedChecksummedDataInput.java:126-127) until the thread's 1-minute keep-alive ends. Rough size: stage 4 measured, from a forged 512 MiB header, 537 MB of heap garbage plus about 537 MB of direct memory cached on the dispatcher thread, followed by FSReadError and a gossiper/transport stop. A header up to 2 GiB is possible. Legitimate blocks: at most about 16 MiB heap plus 16 MiB cached direct per dispatcher thread (2 threads). Not reachable on a stock 5.0.9 node: encrypted hints are never written, and TDE enabled:true does not start. The unvalidated-header part matches the compressed-reader candidate.

**Where:** src/java/org/apache/cassandra/security/EncryptionUtils.java:144-150; src/java/org/apache/cassandra/hints/EncryptedChecksummedDataInput.java:35-41,122-127

## OC-235

**Case file:** `hints-HintsBuffer-put-slabCapacity--autonomous` · **Agent:** guided · **Patterns:** CP-4, CP-5, CP-2

Holder: the MUTATION stage threads and their queue. Hint writes run as tasks on Stage.MUTATION (StorageProxy.java:2827). When all 3 slabs are in flight, HintsBufferPool.switchCurrentBuffer, which is synchronized, blocks on reserveBuffers.take() (HintsBufferPool.java:107-118). A slab returns only after the single HintsWriteExecutor thread has written it to disk (HintsWriteExecutor.java:145-153), so a stalled or slow hints disk blocks every MUTATION thread (concurrent_writes 32). Local and replica writes then pile up deserialized in the stage queue. The only guard is maxHintsInProgress = 128 x cores. It counts hints, not bytes, and rejects only coordinator writes to destinations that already have hints in progress (StorageProxy.java:202,1592-1596). Rough size: 128 x cores queued hint tasks, each pinning its mutation (up to 16 MiB). For example 2,048 x 10 KB = 20 MB typical, up to GBs with large mutations. On top of that comes the blocked stage's backlog of replica mutations, bounded only by the inbound reserve, which counts serialized bytes.

**Where:** src/java/org/apache/cassandra/hints/HintsBufferPool.java:107-118; src/java/org/apache/cassandra/service/StorageProxy.java:202,1592-1596,2822-2827; src/java/org/apache/cassandra/hints/HintsWriteExecutor.java:145-153

## OC-236

**Case file:** `sai-SegmentRowIdOrdinalPairs-add-capacity--autonomous` · **Agent:** guided · **Patterns:** CP-2, CP-7

Holder: one hybrid (filtered) vector query. materializeKeysAndCloseSource collects up to cassandra.sai.vector_search.max_materialized_keys = 16,000 PrimaryKeys in an ArrayList. The limit counts keys, not bytes, and each sstable key carries a freshly read DecoratedKey and clustering (SkinnyPrimaryKeyMap.readPartitionKey). The list is then handed to every memtable index and every sstable segment. Each segment allocates a SegmentRowIdOrdinalPairs int[2 x keysInRange] up front, sized to all keys in its key range rather than the pairs actually stored (VectorIndexSegmentSearcher.java:299). The bound is per query, and nothing caps the total over concurrent queries. Rough size: 16,000 x (about 150 B + key bytes), i.e. about 3-20 MB per query for 0.1-1 KiB keys and up to about 1 GiB per query with 64 KiB partition keys. Plus up to 128 KB per segment per sstable. Multiplied by concurrent reads (32).

**Where:** src/java/org/apache/cassandra/index/sai/plan/QueryController.java:96,427-456; src/java/org/apache/cassandra/index/sai/disk/v1/vector/VectorIndexSegmentSearcher.java:284-299

## OC-237

**Case file:** `sasi-max_term_size-OnDiskIndexBuilder-add-termSize--autonomous` · **Agent:** guided · **Patterns:** CP-1, CP-11

Holder: OnDiskIndexBuilder.finish() for a CONTAINS-mode text index. The flush/compaction cap compares estimatedBytes, which charges a term only 112 + its byte length (:182). At finish, SuffixSA decodes every distinct term into a UTF-16 CharBuffer at 2 B/char (SuffixSA.java:41) and allocates suffixes = new long[charCount] at 8 B/char (SuffixSA.java:64). The builder's TreeMap is still live while this happens. None of that memory is in the estimate, and finish runs after the cap check, on up to 8 SASI-General/SASI-Memtable threads at once. Rough size: about 10 B per char of distinct terms beyond the estimate. With long distinct terms (for example 1,000-byte URLs) a builder cut at the default 153.6 MiB compaction cap needs about 1.4 GB more at finish, and one at the 1 GiB flush cap about 9 GB. Unmeasured: the stage-4 runs used PREFIX/SPARSE. SASI is off by default (sasi_indexes_enabled: false).

**Where:** src/java/org/apache/cassandra/index/sasi/disk/OnDiskIndexBuilder.java:175-194,244-260; src/java/org/apache/cassandra/index/sasi/sa/SuffixSA.java:39-42,60-70; src/java/org/apache/cassandra/index/sasi/sa/SA.java:48-53

## OC-238

**Case file:** `sasi-max_term_size-PerSSTableIndexWriter-addTerm-termSize--autonomous` · **Agent:** guided · **Patterns:** CP-11, CP-12

Holder: the current OnDiskIndexBuilder of one indexed column in one flush or compaction writer. Index.add adds every token of a value before it checks estimatedMemoryUse() < maxMemorySize (:247). With a tokenizing analyzer, one value is materialized whole into the builder whatever the cap: the 1024-byte term limit bounds each token, not the number of tokens. Rough size: stage 4 measured one 1 MiB tokenized value cut only at 28.4 x a 1 MiB cap. A text value up to max_mutation_size (16 MiB) gives about 2-3M tokens, so an estimate of about 300 MB and about 0.5 GB of real heap (real is about 1.8x the estimate) for a single value. This is per column, per writer. SASI is off by default.

**Where:** src/java/org/apache/cassandra/index/sasi/disk/PerSSTableIndexWriter.java:205-250

## OC-239

**Case file:** `sasi-max_compaction_flush_memory-PerSSTableIndexWriter-estimatedMemoryUse--autonomous` · **Agent:** guided · **Patterns:** CP-1, CP-11, CP-5, CP-7

Holder: SASI index builders during compaction or index build. The cap counts an estimate (224 B per entry), but stage 4 measured about 400 B real per entry, about 1.8x. When the cap is reached, scheduleSegmentFlush swaps in a fresh builder and submits the full one to SASI-General (8 threads, unbounded queue) without waiting (:250, :254-266). Several capped builders therefore live at once: stage 4 counted 4-5 instances. The cap applies per indexed column per writer, and nothing caps the total across columns or across concurrent compactions. Rough size: stage 4 measured 1,171 MB of peak live heap at the default 153.6 MiB cap, from a single 54 MB sstable and one column (about 7.6x the cap). Multiply by SASI columns x concurrent_compactors. SASI is off by default.

**Where:** src/java/org/apache/cassandra/index/sasi/disk/PerSSTableIndexWriter.java:63-74,247-266; src/java/org/apache/cassandra/index/sasi/conf/IndexMode.java:59-60; src/java/org/apache/cassandra/index/sasi/disk/OnDiskIndexBuilder.java:182,194

## OC-240

**Case file:** `sasi-max_compaction_flush_memory-PerSSTableIndexWriter-estimatedMemoryUse--autonomous` · **Agent:** guided · **Patterns:** CP-8, CP-10

Holder: the memtable-flush SASI builder. On the FLUSH path maxMemorySize is a hard-coded 1 GiB estimate (:365-369). The index option is ignored there, and the value does not scale with the heap. The builder is not charged to the memtable pool. During the flush it lives alongside the flushing memtable and its SASI trie, both kept in pendingFlush until the discard notification (ColumnIndex.java:116-119), and the pool counts only those two. Rough size: up to 1 GiB estimate, about 1.8 GiB real, per indexed column per flush. A tokenized column's builder is about 1.5x the memtable's SASI share. Memtable_flush_writers (2) can flush at once, with 8 SASI-Memtable threads. On a 4-8 GiB heap this is the same order as the whole memtable budget. Not reached on a node in stage 4. SASI is off by default.

**Where:** src/java/org/apache/cassandra/index/sasi/disk/PerSSTableIndexWriter.java:365-369; src/java/org/apache/cassandra/index/sasi/conf/ColumnIndex.java:116-124

## OC-241

**Case file:** `sasi-max_term_size-TrieMemIndex-add-termSize--autonomous` · **Agent:** guided · **Patterns:** CP-1

Holder: the SASI memtable index's per-term ConcurrentSkipListSet<DecoratedKey>. Each add is charged a flat CSLM_OVERHEAD of 128 B plus trie nodes, on the comment's assumption that 'DKs are shared' (SkipListMemIndex.java:35,47; TrieMemIndex.java:116-137). In fact the indexer receives update.partitionKey() (SecondaryIndexManager.java:1455-1457), not the memtable's cloned key (SkipListMemtable.java:115). Each term's set therefore keeps the DecoratedKey (key bytes, about 100 B of objects) of whichever update first added that partition to that term, and nothing charges for it. Distinct updates to the same partition can leave one key copy per (term, partition). Rough size: about key length + 100 B uncharged per (term, partition) pair, against 128 B charged. That is about 1.5x for 36 B keys and about 10x for 1 KiB keys, so a memtable with 1M such pairs of 1 KiB keys holds about 1 GiB uncounted by memtable_heap_space. Stage 4 saw live heap up to 2.5x tracked in one arm, unexplained. SASI is off by default.

**Where:** src/java/org/apache/cassandra/index/sasi/memory/TrieMemIndex.java:116-137; src/java/org/apache/cassandra/index/sasi/memory/SkipListMemIndex.java:35,47; src/java/org/apache/cassandra/index/SecondaryIndexManager.java:1455-1457; src/java/org/apache/cassandra/db/memtable/SkipListMemtable.java:115

## OC-242

**Case file:** `compression-metadata-writer-addOffset-maxCount--autonomous` · **Agent:** autonomous · **Patterns:** —

Reader-side chunk-offset tables. Every open compressed SSTable keeps a CompressionMetadata whose chunkOffsets is a native Memory block of chunkCount x 8 B. It is malloc'd through Memory.allocate (Unsafe/JNA), so it counts against neither the heap nor -XX:MaxDirectMemorySize. No configuration entry or limit caps the sum across SSTables: it grows with the uncompressed data on the node divided by chunk_length_in_kb, and old and new SSTables are both open during compaction. Rough size at defaults (LZ4, 16 KiB chunks): 8 B per 16 KiB, about 0.05% of uncompressed data. 2 TiB of data is about 1 GiB of native memory and 10 TiB is about 5 GiB. Only the TableMetrics gauge reports it, and nothing ever refuses it. On a dense node in a container whose memory limit is sized for heap plus direct memory, this can end in a native or container OOM kill.

**Where:** src/java/org/apache/cassandra/io/compress/CompressionMetadata.java:193,202 (readChunkOffsets: chunkCount from the file, Memory.allocate(chunkCount * 8L)); CompressionMetadata.java:163-166 (offHeapSize, the only accounting); schema/CompressionParams.java:48 (DEFAULT_CHUNK_LENGTH 16 KiB); writer side CompressionMetadata.java:366-372 (addOffset doubling with no cap)

## OC-243

**Case file:** `max-region-size-region-allocate-capacity--autonomous` · **Agent:** autonomous · **Patterns:** —

On the default memtable path (memtable_allocation_type: heap_buffers, which uses SlabPool and SlabAllocator, not NativeAllocator), the slab constant is a fixed REGION_SIZE of 1 MiB. Each memtable allocates a full 1 MiB on-heap region on its first write, but only the requested bytes are charged to the memtable_heap_space pool. The unused rest of the current region, and the unused tail of every abandoned region (up to just under 128 KiB, about 11% for values a little over 1 MiB/9), are never charged. So the pool neither sees this memory nor triggers a flush for it. Nothing limits the number of memtables: tables_warn/fail_threshold default to -1, every secondary-index table has its own memtable, and memtable_flush_period defaults to 0. The static RACE_ALLOCATED queue of losing regions is also unbounded and uncharged. Rough size at defaults: about 1 MiB of heap per table that has taken a write since its last flush, so 1,000 lightly written tables hold about 1 GiB uncharged. On top of that comes up to about 11% of memtable_heap_space (heap/4, 2 GiB at an 8 GiB heap, so about 225 MiB) in region tails.

**Where:** src/java/org/apache/cassandra/utils/memory/SlabAllocator.java:51 (REGION_SIZE 1 MiB), :89 (only size charged), :137-151 (new 1 MiB region per memtable, unbounded RACE_ALLOCATED queue at :55,:151), :199-202 (tail abandoned); db/memtable/AbstractAllocatorMemtable.java:100-102 (heap_buffers -> SlabPool); conf/cassandra.yaml:825 (default heap_buffers); config/Config.java:865-866 (tables thresholds -1); NativeAllocator.java:46,163-168 (non-default path, regions start at 8 KiB)

## OC-244

**Case file:** `partition-key-max-size-descend-data-length--autonomous` · **Agent:** autonomous · **Patterns:** —

In a trie memtable (the shipped 'trie' configuration, opted into per table with memtable = 'trie'), each shard's InMemoryTrie keeps an ApplyState.data int[] scratch stack. The stack doubles with key depth for keys of 128 bytes or more and is never shrunk. sizeOnHeap() counts only the initial 80-int array (EMPTY_SIZE_ON_HEAP), so the growth is never charged to memtable_heap_space and never triggers a flush. Keys up to 65535 B are legal, and nothing bounds the number of shards or tables. Rough size at defaults: up to about 2.6 MB per shard (655,360 ints at a 65535-byte key, measured in stage 4). The shard count defaults to the number of available processors, so a 32-core node holds about 84 MB per trie table that has seen one maximum-size key. That memory stays until the memtable is discarded, and 50 such tables hold about 4 GB of uncharged heap.

**Where:** src/java/org/apache/cassandra/db/tries/InMemoryTrie.java:577 (int[16*5]), :670-671 (Arrays.copyOf doubling, no shrink), :975-981 (sizeOnHeap omits it); db/memtable/TrieMemtable.java:98,479-485 (apply path for keys >= 128 B; charge = sizeOnHeap delta); db/memtable/AbstractShardedMemtable.java:46 (default shards = processors)

## OC-245

**Case file:** `repair-session-space-histogram-add-values--autonomous` · **Agent:** autonomous · **Patterns:** —

repair_session_space bounds only one validation: one table and one set of common ranges, with space/RF per replica tree. The repair coordinator holds the Merkle trees of every table job of a session, and of every session of a command, at the same time. RepairSession submits one RepairJob per table, and the validation scheduler is built from concurrent_merkle_tree_requests, which defaults to 0 (no limit). The yaml itself says this 'can produce OOM for commands repairing multiple tables or multiple virtual nodes'. Rough size at defaults: an 8 GiB heap gives repair_session_space = 512 MiB, about 170 MiB per replica. A table with 2^19 or more partitions per range gives a depth-19 tree of about 55 MB (stage 4: about 109 MB at depth 20), so about 165 MB for RF 3 per table job. A keyspace repair of 20 such tables holds about 3.3 GB, and more with several vnode sessions in flight, against an 8 GiB heap. Nothing refuses it.

**Where:** src/java/org/apache/cassandra/repair/ValidationManager.java:62-63,71-80 (per-validation budget space/RF); config/Config.java:210 (concurrent_merkle_tree_requests = 0); repair/RepairCoordinator.java:127 (Scheduler.build(0) = unlimited); repair/RepairSession.java:338-345 (one RepairJob per table submitted together); repair/RepairJob.java:240-254,283-345 (TreeResponses from all endpoints held for differencing); conf/cassandra.yaml:826-856

## OC-246

**Case file:** `sasi-compaction-flush-memory-ensurecapacity-tmp--autonomous` · **Agent:** autonomous · **Patterns:** —

SASI CONTAINS-mode segment flush (needs sasi_indexes_enabled: true, default false, or a SASI index carried over from an older version; the index options are at their defaults). The segment limit checks only OnDiskIndexBuilder.estimatedBytes, about 220 B plus 1 B per character of each term. After the check, finish() builds SuffixSA, which allocates a long[charCount] holding one 8-byte slot per character of every term. LongTimSort then adds a tmp buffer of up to charCount/2 longs, and every CharTerm holds a CharBuffer of 2 B per character. None of this is charged. Up to 8 segments flush at once in each SASI pool (POOL_SIZE 8). Rough size at defaults: up to about 14 B per indexed character against 1 B estimated. Stage 4 measured a live increment of 11.6 x M at L=1000, and a 512 MiB heap died of OutOfMemoryError at M=32. For compaction, M defaults to 0.15 GiB (161 MB), so one segment of long terms is about 1.9 GB and 8 parallel segments are several GB. For memtable flush the limit is a hard-coded 1 GiB estimate, so the only effective bound is the memtable size. A memtable holding 1 GiB of indexed text would need about 14 GiB.

**Where:** src/java/org/apache/cassandra/index/sasi/sa/SuffixSA.java:64 (new long[charCount]), :84 (LongTimSort.sort); utils/LongTimSort.java:820-836 (tmp up to a.length>>>1); index/sasi/disk/OnDiskIndexBuilder.java:182,194 (estimate per term/key), :255 (SuffixSA built in finish after the check); index/sasi/disk/PerSSTableIndexWriter.java:63-73 (POOL_SIZE 8), :247-250 (check then submit), :365-369 (1 GiB for FLUSH); index/sasi/conf/IndexMode.java:59-60 (default 0.15 GiB); conf/cassandra.yaml:1992

## OC-247

**Case file:** `compression-metadata-writer-addOffset-maxCount--autonomous` · **Agent:** guided · **Patterns:** CP-13

Holder: the off-heap chunk-offset table read when an SSTable is opened (CompressionMetadata.readChunkOffsets). The chunk count is an int read straight from -CompressionInfo.db. It is checked only for <= 0, never against the file's length or the data length, before Memory.allocate(chunkCount * 8L) mallocs the region (Memory.java:60-65 throws OutOfMemoryError when malloc returns 0). The same unchecked length appears in the streaming header: CompressionInfo.serializer.deserialize does `new Chunk[chunkCount]` from a peer-supplied int (db/streaming/CompressionInfo.java:188-192), and CassandraStreamHeader.deserialize does `new ArrayList<>(count)` for the sections (CassandraStreamHeader.java:208-210). Nothing bounds these before the allocation. Rough size: a corrupt or hostile count up to 2^31-1 asks for 16 GiB of native memory at sstable open (startup, import, or the receive side of entire-SSTable streaming), or about 8-16 GiB of heap for the Chunk[] from one stream header. A failed malloc surfaces as a JVM OutOfMemoryError at open.

**Where:** src/java/org/apache/cassandra/io/compress/CompressionMetadata.java:192-201; src/java/org/apache/cassandra/db/streaming/CompressionInfo.java:188-192

## OC-248

**Case file:** `compression-metadata-writer-addOffset-maxCount--autonomous` · **Agent:** guided · **Patterns:** CP-12, CP-1, CP-7

Holder: the receive side of a stream (CassandraStreamHeader, then CompressionInfo). Each incoming file's header carries one CompressionMetadata.Chunk object per 16 KiB chunk of the streamed sections, about 28 B of heap each (object plus reference) against 8 B per chunk on disk or native. The whole array is built before any data arrives and is kept while that file is received. The sender builds the same array when it serializes (CassandraOutgoingFile.java:79-81, newLazyInstance). Nothing counts this heap, and no limit caps it per file or per session. Rough size at defaults (16 KiB chunks): about 1.75 MB of heap per GiB of uncompressed data streamed in one file. A 100 GiB SSTable is about 6.5M chunks, or about 180 MB of heap per header. That is multiplied by the files in flight across peers during bootstrap, rebuild or repair streaming.

**Where:** src/java/org/apache/cassandra/db/streaming/CompressionInfo.java:185-198; src/java/org/apache/cassandra/db/streaming/CassandraStreamHeader.java:211

## OC-249

**Case file:** `compression-metadata-writer-addOffset-maxCount--autonomous` · **Agent:** guided · **Patterns:** CP-9, CP-8, CP-7

Holder: per-SSTable chunk-offset tables. The writer side grows by doubling (CompressionMetadata.java:366-370). The reader side holds chunkCount*8 for the life of the SSTable (:202). Both are allocated with JNA Native.malloc (MemoryUtil.java:81-84), so they are outside -Xmx, outside MaxDirectMemorySize and outside NMT. No Cassandra budget counts them; they show only in the CompressionMetadataOffHeapMemoryUsed gauge. At the default 16 KiB chunk this is 1/2048 of uncompressed live data: about 0.5 GiB of native memory per TiB on the node, plus up to 3x the current table during a doubling for each SSTable being written. It shares the container's native budget with off-heap bloom filters, index summaries and memtables, and nothing relates them.

**Where:** src/java/org/apache/cassandra/io/compress/CompressionMetadata.java:202,366-370

## OC-250

**Case file:** `partition-key-max-size-descend-data-length--autonomous` · **Agent:** guided · **Patterns:** CP-1, CP-7, CP-14

Holder: InMemoryTrie.ApplyState.data, an int[] scratch stack, one per trie memtable shard. It is doubled in descend() whenever the key depth exceeds its length (InMemoryTrie.java:669-671). It is never shrunk: reset() only sets the depth to -1. sizeOnHeap() (:974-981) has no term for it, and the static EMPTY_SIZE_ON_HEAP includes only the initial 80-int array. So the memtable allocator is charged 0 B for it (TrieMemtable.java:484-485), and memtable_heap_space never flushes because of it. It is reached for keys of 128 B or more (TrieMemtable.java:98). Shards default to the processor count (AbstractShardedMemtable.java:46,63-65). Nothing caps the total across shards, tables and memtable generations. Rough size: stage 4 measured 2.62 MB per shard after one 65535-byte key. A 40-core node is about 105 MB per trie table per memtable generation (doubled while a flushing memtable is live). That is reached by about 40 long-key writes (about 2.6 MB written), and is multiplied by every table using the trie memtable. The trie memtable is the default in cassandra_latest.yaml, not in cassandra.yaml.

**Where:** src/java/org/apache/cassandra/db/tries/InMemoryTrie.java:577,669-671,974-981

## OC-251

**Case file:** `transition-bytes-collector-add-buffer-length--autonomous` · **Agent:** guided · **Patterns:** CP-10

Holder: every guardrail checked with a client's ClientState. Guardrail.enabled(state) requires state.isOrdinaryUser() (Guardrail.java:93-96). ClientState.isSuper() returns true whenever the authenticator does not require authentication (ClientState.java:602-605), and the shipped authenticator is AllowAllAuthenticator (conf/cassandra.yaml:198). So on a default install no client mutation or query is ever checked by a guardrail. Stage 4 observed this here (the SAI term-size guardrail never fired under AllowAllAuthenticator) and in maximum_replication_factor-ReplicaList.add-newSize--autonomous and initial-buffer-capacity-ensurecapacity-datalengthinbytes--autonomous. The memory-relevant guardrail that is on by default is the SAI term size (warn 1 KiB, fail 8 KiB). Under the bypass, index terms up to max_mutation_size (commitlog_segment_size/2 = 16 MiB) enter the SAI memtable index (StorageAttachedIndex.validateTermSize, :813-818, with isClientMutation). That index memory is charged to the memtable (StorageAttachedIndex.java:1007), so the memtable pool, not the guardrail, is the only bound. Every guardrail an operator enables for memory (collection size, column value size, page size, IN cartesian product, partition size) is likewise void unless authentication is turned on. Rough size: about 2000x the 8 KiB term cap per term at defaults.

**Where:** src/java/org/apache/cassandra/service/ClientState.java:602-605; src/java/org/apache/cassandra/db/guardrails/Guardrail.java:93-96; conf/cassandra.yaml:198

## OC-252

**Case file:** `repair-session-space-histogram-add-values--autonomous` · **Agent:** guided · **Patterns:** CP-7, CP-8, CP-1

Holder: Merkle trees of one repair command. repair_session_space (default heap/16, DatabaseDescriptor.java:609-610) bounds one validation, that is, one table x one common range, divided by RF (ValidationManager.java:62-80). With the default concurrent_merkle_tree_requests: 0 (Config.java:210), the scheduler is a NoopScheduler (Scheduler.java:43-47). Every common range's session is submitted at once (AbstractRepairTask.java:66-86), and every table's RepairJob is executed at once within a session (RepairSession.java:338-344). So the coordinator holds up to RF trees per job for all jobs together. The received trees are deserialized off-heap by default (use_offheap_merkle_trees true, Config.java:212; allocateDirect at MerkleTree.java:751), into direct memory whose default limit is shared with the chunk cache and networking pools. The yaml itself says the default can produce OOM (conf/cassandra.yaml:843-861). On top of this, the DEBUG-only histogram long[] is uncounted (about 10 B per leaf, peak about 15.7 MB per builder at 2^20 leaves, HistogramBuilder.java:45-47), and DEBUG is the shipped level for org.apache.cassandra. Rough size: (common ranges x tables) x heap/16. For example, 4 ranges x 10 tables is about 2.5x heap across heap and direct memory, bounded only by depth 20 (about 110 MB of heap per tree, measured in stage 4) and by data volume.

**Where:** src/java/org/apache/cassandra/repair/ValidationManager.java:62-80; src/java/org/apache/cassandra/repair/RepairSession.java:338-344; src/java/org/apache/cassandra/config/Config.java:210

## OC-253

**Case file:** `sasi-compaction-flush-memory-ensurecapacity-tmp--autonomous` · **Agent:** guided · **Patterns:** CP-1, CP-11, CP-7

Holder: the SASI CONTAINS-mode segment flush (OnDiskIndexBuilder.finish, which builds SuffixSA). max_compaction_flush_memory_in_mb (default 0.15 GiB, about 161 MB, IndexMode.java:59-60) is compared with estimatedMemoryUse() (PerSSTableIndexWriter.java:247). That estimate counts per term 64+48+len and per key 108 B (OnDiskIndexBuilder.java:182,194). After the check, finish() allocates long[charCount], 8 B per character of every term (SuffixSA.java:64). It adds the LongTimSort tmp (up to 4 B per character, LongTimSort.java:820-836), a 2 B per character CharBuffer per term, and two comparator buffers per comparison. None of this is charged. Up to 8 segments flush at once on the SASI pool (PerSSTableIndexWriter.java:63,70). Memtable flushes use a hard-coded 1 GiB estimate limit instead (:365-369), so a CONTAINS flush of a large memtable gets a suffix array of about 8-14 B per indexed character. Stage 4 measured a live increment of 1.3-11.6x M per segment (unit test) and 19-92x M per node (cluster). A 512 MiB-heap node died of OutOfMemoryError at M = 32 MiB. Rough size at the default M: up to about 1.8 GB per segment (L = 1000 chars) x up to 8 concurrent segments. SASI needs sasi_indexes_enabled: true (default false).

**Where:** src/java/org/apache/cassandra/index/sasi/sa/SuffixSA.java:64; src/java/org/apache/cassandra/index/sasi/disk/PerSSTableIndexWriter.java:247,365-369; src/java/org/apache/cassandra/index/sasi/disk/OnDiskIndexBuilder.java:182,194

## OC-254

**Case file:** `memtable-offheap-space-allocate-size--autonomous` · **Agent:** guided · **Patterns:** CP-1, CP-11, CP-7, CP-8

Holder: trie memtable buffers. This is the default memtable in cassandra_latest.yaml, which also ships offheap_objects. InMemoryTrie.allocateBlock allocates each new buffer with bufferType.allocate(BUF_START_SIZE << leadBit) (InMemoryTrie.java:148-151), which is a direct ByteBuffer for off-heap types. Buffer sizes double up to 1 GiB (:90). The pool is charged only afterwards, by the change in the used position allocatedPos (sizeOffHeap, :968-971), through allocator.offHeap().adjust after the put (TrieMemtable.java:484). So the unused part of the newest buffer, up to about the size of everything used before it, is held but not counted. The charge comes after the allocation, so a writer parks only after the buffer already exists. This happens per shard (shards default to the CPU count) per table, and nothing caps the sum. With heap_buffers the same tail is on heap and outside memtable_heap_space. Rough size: allocated buffers can reach about 2x the charged trie bytes. The real memtable footprint can approach about 2x memtable_offheap_space (heap/4), in direct memory shared with the chunk-cache and networking pools under MaxDirectMemorySize.

**Where:** src/java/org/apache/cassandra/db/tries/InMemoryTrie.java:148-151,968-971; src/java/org/apache/cassandra/db/memtable/TrieMemtable.java:484

## OC-255

**Case file:** `memtable-offheap-space-allocate-size--autonomous` · **Agent:** guided · **Patterns:** CP-8, CP-9

Holder: the memtable off-heap pool together with the other off-heap defaults. Under offheap_objects, memtable_offheap_space defaults to heap/4 (DatabaseDescriptor.java:583-584) and is JNA-malloced (MemoryUtil.java:81-84). That is outside MaxDirectMemorySize and invisible to NMT (stage 4). On top of it come the chunk-cache pool min(512 MiB, heap/4) and the networking pool min(128 MiB, heap/16) (DatabaseDescriptor.java:573-577), plus the heap and JVM baseline. No check relates their sum to the container, which gives about 9H/16 of off-heap at small heaps. Stage 4 saw about 150 MiB of other-consumer growth under load. The case file's back-link recheck already ties this to phase-2 R1-V, so the session should dedupe against it. Rough size: H + 9H/16 + baseline exceeds a RAM = 2H container at H <= 2 GiB.

**Where:** src/java/org/apache/cassandra/config/DatabaseDescriptor.java:573-584; src/java/org/apache/cassandra/utils/memory/NativeAllocator.java:141,176

