# Stage 5 wave 3 — full candidate text (2026-11-18)

Full clue and `file:line` for each `OC-` row filed from wave 3 (workflow `wf_c3dd052c-d6c`; guided agents used CP-1..CP-16). The candidate list row holds the first sentence.

## OC-413

**Case file:** `no_constraint-doesaggregation-aggregatefactories--autonomous` · **Agent:** autonomous · **Patterns:** —

Holder: the coordinator ResultSet (ResultSetBuilder.resultSet.rows), plus the replica's serialized response buffer. When doesAggregation() is false (no aggregate, so no GroupMaker), every input row becomes one output row. If the client turns paging off (pageSize <= 0), SelectStatement takes the direct execute path with DataLimits.NONE. The whole result is then materialised at once: first in the replica's DataOutputBuffer (LocalDataResponse.build), then in ResultSet.rows, then in the encoded response. Why nothing stops it: the only byte cap on this path is maybeFail (coordinator_read_size_fail_threshold), and it is a no-op at defaults because read_thresholds_enabled=false and every read-size threshold is null. The page_size guardrail is -1. ORDER BY combined with IN on the partition key even forces paging off. Only aggregate queries get folded to one row and paged internally. Rough size: stage 4 measured 124 B per retained row for a 3-int row (12.4 MB at 100k rows). With 1 KiB rows, one unpaged SELECT of a 10M-row partition or table holds about 10 GB in ResultSet.rows, plus about the same again in the replica response buffer. That is far over a default heap (1/4 of RAM, at most 8 GB), and several such requests can be in flight on native_transport threads.

**Where:** src/java/org/apache/cassandra/cql3/statements/SelectStatement.java:338 (pageSize<=0 -> unpaged execute); SelectStatement.java:1003-1021 (process builds full ResultSet); SelectStatement.java:1057-1060 (maybeFail no-op unless thresholds enabled); SelectStatement.java:536-538 (ORDER BY+IN requires paging off); cql3/selection/ResultSetBuilder.java:126-136 (one output row per input row when groupMaker null); db/ReadResponse.java:197-203 (whole local result serialized into one buffer); config/Config.java:526-528, 873-874 (read thresholds disabled/null, page_size guardrail -1)

## OC-414

**Case file:** `no_constraint-iscolumnrange-clustering_restrictions--autonomous` · **Agent:** autonomous · **Patterns:** —

Holder: the cartesian product of the IN lists on clustering columns. MultiCBuilder.MultiClusteringBuilder.elementsList holds it as one ArrayList per composite, then a BTreeSet of ClusteringBound for both START and END (built in makeSlices), then Slices. When isColumnRange() is true (an IN on ck1..ckk with a later clustering column unrestricted or sliced), SelectStatement takes the slice path, ClusteringColumnRestrictions.boundsAsClustering. That method never calls Guardrails.inSelectCartesianProduct. Only the names path (valuesAsClustering, isColumnRange false) has the guard. Even there the guard is disabled at defaults (in_select_cartesian_product_*_threshold = -1), and it runs only after each appendTo has already multiplied elementsList. No IN-list length limit exists for literal values. Rough size: about 150-250 B per composite per bound (ArrayList + Object[] + ClusteringBound + BTree node), times 2 bounds. ck1 IN (1000 values) AND ck2 IN (1000 values) with ck3 unrestricted gives 1e6 composites, about 300-500 MB from one CQL string of about 10 KB. A third IN of 100 values gives 1e8 composites, tens of GB, which is OOM on any default heap (max 8 GB).

**Where:** src/java/org/apache/cassandra/cql3/restrictions/StatementRestrictions.java:974-975 (isColumnRange); cql3/statements/SelectStatement.java:826-832, 846-875 (slice path, start and end bound sets); cql3/restrictions/ClusteringColumnRestrictions.java:121-148 (boundsAsClustering, no cartesian guard) vs :105-118 (names path guard after appendTo); db/MultiCBuilder.java:339-373 (addEachElementToAll multiplies elementsList); db/guardrails/Guardrails.java:294-298; config/Config.java:877-878 (thresholds -1)

## OC-415

**Case file:** `no_constraint-needfiltering-restriction_count--autonomous` · **Agent:** autonomous · **Patterns:** —

Holder: the replica responses buffered at the coordinator for one page of a key-range (ALLOW FILTERING) scan. needFiltering() only gates the query on the client's ALLOW FILTERING opt-in (SelectStatement checkNeedsFiltering). Once the client opts in, RangeCommandIterator sends sub-range commands that each carry the full page limit (command.forSubRange keeps DataLimits). The limit is enforced only globally, after merge ('will honor the command limit for each range, but will not enforce it globally'). A filter that matches nothing in the early ranges makes liveReturned==0, so computeConcurrencyFactor jumps to maxConcurrencyFactor = min(#ranges, 10 x cores). Every concurrent sub-range response is then received in full (ReadCallback/DataResolver), up to pageSize rows each, with no byte cap (read thresholds disabled). Rough size: 6 nodes x num_tokens 16 = 96 ranges, a 16-core coordinator gives concurrency 96, driver page 5000 rows, 1 KiB rows, 2 responses at QUORUM: about 96 x 5000 x 1 KiB x 2 = about 1 GB per page of one query. A few concurrent clients exceed a default heap. If paging is off, each sub-range response holds all matching rows of its range (no limit).

**Where:** src/java/org/apache/cassandra/cql3/restrictions/StatementRestrictions.java:982-993; cql3/statements/SelectStatement.java:1602-1611 (gate bypassed by ALLOW FILTERING); service/reads/range/RangeCommands.java:53, 57-59, 84-96; service/reads/range/RangeCommandIterator.java:159-166 (zero rows -> max concurrency), 188-190 (sub-range keeps full limit), 223-256 (DataLimits.NONE counter, all responses gathered); config/Config.java:526-532 (read-size thresholds off)

## OC-416

**Case file:** `no_constraint-doesaggregation-aggregatefactories--autonomous` · **Agent:** guided · **Patterns:** CP-12, CP-8

Holder: the coordinator's result set (and each replica's response) for an unpaged, non-aggregating SELECT. When the client sends page size <= 0 (or uses IN + ORDER BY, which refuses paging at SelectStatement.java:537), SelectStatement.java:338-341 takes the direct execute() path. The whole result, up to an entire wide partition or a whole range, is built as one ResultSet. Why nothing stops it: aggregate and GROUP BY queries are always paged internally (SelectStatement.java:900-902 forces DEFAULT_PAGE_SIZE 10000), but a non-aggregating query gets cqlLimits(NO_LIMIT). The limits that would refuse it all ship off: read_thresholds_enabled=false, coordinator_read_size_fail_threshold=null and local_read_size_fail_threshold=null (Config.java:526-530), page_size_fail_threshold=-1 (Config.java:874). The pageSize guardrail at SelectStatement.java:517 runs only on the paged path. Rough size at defaults: stage 4 of this case measured the non-aggregate branch holding 12.4 MB for a 100,000-row partition (about 124 B per small row) against 168 B when folded. A 10M-row (about 1 GB on disk) partition read unpaged is therefore more than 1 GB on the coordinator, plus the replica's serialized response. That is multiplied by concurrent such requests (native_transport_max_threads 128) with no total cap, which exceeds a default heap of a few GB.

**Where:** src/java/org/apache/cassandra/cql3/statements/SelectStatement.java:338

## OC-417

**Case file:** `no_constraint-hascomponent-i_nextsize--autonomous` · **Agent:** guided · **Patterns:** CP-13, CP-8

Holder: the byte[] allocated for one clustering component during deserialization. Both ClusteringPrefix.Deserializer.deserializeOne (ClusteringPrefix.java:677) and Serializer.deserializeValuesWithoutSize (ClusteringPrefix.java:517) call types.readArray(in, DatabaseDescriptor.getMaxValueSize()). This mechanism also shows up in no_constraint-isempty-header_mask--autonomous and no_constraint-isnull-header_bit--autonomous, which guard the same readArray branch. Why nothing stops it: the length is a vint read from the sstable (or from a peer's message) and is checked only against max_value_size, default 256 MiB (Config.java:310). ByteArrayAccessor.read then allocates new byte[length] before readFully learns whether that many bytes exist (ByteArrayAccessor.java:102-103). For clustering values the legitimate maximum is about 64 KiB, yet the generic 256 MiB bound applies, a fixed default that does not scale with the heap. Rough size at defaults: one corrupt length costs up to 256 MiB per deserialized component. A hot corrupt partition read by concurrent_reads=32 threads, or by compaction at the same time, can request 32 x 256 MiB = 8 GiB, more than the default heap. This is the residual of the JIRA 9530 fix. The companion array new byte[nextSize][] sized by readUnsignedShort (ClusteringPrefix.java:612,620) is at most 65535 refs (about 512 KB) and is not a candidate by itself.

**Where:** src/java/org/apache/cassandra/db/marshal/AbstractType.java:594

## OC-418

**Case file:** `native_transport_max_request_data_in_flight-applysimpleconfig-maxmessagesize--autonomous` · **Agent:** autonomous · **Patterns:** —

Pre-V5 (protocol v4) path: when a decoded request does not fit in the in-flight limit, the handler force-allocates it past the limit (endpointPayloadTracker.allocate), dispatches it, and only then turns off autoRead. Every connection can therefore hold one request over the global limit. A request can be up to native_transport_max_frame_size, which defaults to 16 MiB, and native_transport_max_concurrent_connections defaults to -1 (no limit). Rough size: 500 connections x 16 MiB = about 8 GiB of request buffers (plus their decoded messages) on top of the heap/10 limit, which is about 800 MiB at an 8 GiB heap.

**Where:** PreV5Handlers.java:178-187, Config.java:285, Config.java:289, Envelope.java:197

## OC-419

**Case file:** `native_transport_max_request_data_in_flight-applysimpleconfig-maxmessagesize--autonomous` · **Agent:** autonomous · **Patterns:** —

Pre-V5 frames are buffered in Netty's ByteToMessageDecoder cumulation until the whole frame has arrived (return null while readableBytes < totalLength). In-flight accounting happens only after decode (checkLimits). So a frame that announces up to 16 MiB and is sent slowly sits in direct memory and is not counted against any limit. No connection cap applies by default, and native_transport_idle_timeout defaults to 0ms, so nothing reaps the connection. This works before authentication too, because v4 has no READY check. Rough size: N slow connections x 16 MiB, for example 1000 x 16 MiB = 16 GiB.

**Where:** Envelope.java:425-442, PreV5Handlers.java:151-186, Config.java:139, Config.java:289

## OC-420

**Case file:** `native_transport_max_request_data_in_flight-applysimpleconfig-maxmessagesize--autonomous` · **Agent:** autonomous · **Patterns:** —

V5 path: each connection gets an exclusive receive-queue allowance (native_transport_receive_queue_capacity, default 1 MiB). acquireCapacity grants it without touching the global or per-IP reserves. The global native_transport_max_request_data_in_flight therefore bounds only bytes above 1 MiB per connection, and the connection count is unlimited. In addition, when acquisition fails the contained message is still decoded and dispatched (backpressure only stops further frames), adding up to one 128 KiB frame per connection. Rough size: 10,000 connections x (1 MiB + about 128 KiB) = about 11 GiB beyond the heap/10 limit.

**Where:** AbstractMessageHandler.java:411-422, PipelineConfigurator.java:306, Config.java:302, CQLMessageHandler.java:223-249

## OC-421

**Case file:** `native_transport_max_request_data_in_flight-applysimpleconfig-maxmessagesize--autonomous` · **Agent:** autonomous · **Patterns:** —

Response bytes are not counted at all, and the request's in-flight bytes are released as soon as its response has been handed to channel.flush or writeAndFlush. Nothing checks Channel.isWritable: a write-buffer water mark is set, but nothing consults it. A client that keeps sending small SELECTs and never reads its socket makes response payloads pile up without bound in Netty's ChannelOutboundBuffer (direct memory, from the networking BufferPool and falling back to allocateDirect). Rough size: a 5000-row page of 1 KB rows is about 5 MB per response, so 1000 unread responses on one connection are about 5 GB.

**Where:** Flusher.java:201-205, Flusher.java:226-250, CQLMessageHandler.java:481-503, PipelineConfigurator.java:139

## OC-422

**Case file:** `native_transport_max_request_data_in_flight_per_ip-applysimpleconfig-maxmessagesize--autonomous` · **Agent:** autonomous · **Patterns:** —

Per-IP limit (heap/40) is bypassed per connection on V5. Each connection's first native_transport_receive_queue_capacity bytes (1 MiB default) are granted from an exclusive per-connection queue without charging the endpoint (per-IP) reserve. native_transport_max_concurrent_connections_per_ip defaults to -1, so one IP can open as many connections as it likes. On a failed acquire, a contained message is still dispatched. Rough size: one client IP with 5,000 connections holds about 5 GiB (plus up to one 128 KiB frame each), against a per-IP limit of about 200 MiB at an 8 GiB heap.

**Where:** AbstractMessageHandler.java:411-422, PipelineConfigurator.java:306, Config.java:290, Config.java:302, CQLMessageHandler.java:223-249

## OC-423

**Case file:** `native_transport_max_request_data_in_flight_per_ip-applysimpleconfig-maxmessagesize--autonomous` · **Agent:** autonomous · **Patterns:** —

Pre-V5 (v4): when tryAllocate fails on the per-IP or global tracker, the request is force-allocated past both limits and processed, and only then is the connection paused. Overshoot is one request per connection, up to native_transport_max_frame_size (16 MiB), with no per-IP connection cap. Rough size: 200 connections from one IP x 16 MiB = about 3.2 GiB against the heap/40 limit.

**Where:** PreV5Handlers.java:178-187, Config.java:285, Config.java:290

## OC-424

**Case file:** `native_transport_max_request_data_in_flight_per_ip-applysimpleconfig-maxmessagesize--autonomous` · **Agent:** autonomous · **Patterns:** —

Pre-V5 partial frames (up to 16 MiB each) wait in the Netty cumulation buffer until complete and are not charged to the per-IP tracker until after decode. With unlimited connections per IP and no idle timeout by default, a single slow client IP can park N x 16 MiB of direct memory, for example 1000 x 16 MiB = 16 GiB.

**Where:** Envelope.java:425-442, PreV5Handlers.java:151-186, Config.java:139, Config.java:290

## OC-425

**Case file:** `native_transport_max_request_data_in_flight_per_ip-applysimpleconfig-maxmessagesize--autonomous` · **Agent:** autonomous · **Patterns:** —

Responses are outside both the per-IP and the global accounting. The request's capacity is released when its response is flushed to the channel, and nothing checks writability. A client IP that does not read its socket accumulates unbounded response payloads in the outbound buffer, for example 1000 unread 5 MB pages = 5 GB of direct memory.

**Where:** Flusher.java:226-250, CQLMessageHandler.java:481-503, PipelineConfigurator.java:139

## OC-426

**Case file:** `no_constraint-capacity-newcapacity--autonomous` · **Agent:** autonomous · **Patterns:** —

The networking BufferPool that backs Wrapped/BufferPoolAllocator caps only pooled chunk memory: networking_cache_size, default min(128 MiB, heap/16). Any request over 128 KiB, and any request once the pool cannot add an 8 MiB macro chunk, falls through to ByteBuffer.allocateDirect, and that path only increments a counter (overflowMemoryUsage). Wrapped.capacity growth uses the same getAtLeast path. Network buffers held for a long time therefore grow with nothing but MaxDirectMemorySize to stop them. Examples are V5 response payloads that FrameEncoder allocates from this pool and queues for a client that is not reading, since Flusher never checks writability. Rough size: past the 128 MiB pool, one non-reading client with 1000 queued 5 MB responses = about 5 GB of overflow direct memory.

**Where:** BufferPool.java:906-921, BufferPool.java:233-239, BufferPool.java:441-450, BufferPoolAllocator.java:119-137, FrameEncoder.java:64, Flusher.java:201-205

## OC-427

**Case file:** `no_constraint-resizeto-newcapacity--autonomous` · **Agent:** autonomous · **Patterns:** —

Index-summary builders for new BIG-format sstables (the 5.0 default format) are created at BASE_SAMPLING_LEVEL. They preallocate off-heap SafeMemoryWriter regions of expectedKeys/min_index_interval x (64-byte default key estimate + 8) bytes for entries, plus 4 bytes per entry for offsets. The only cap is 2 GiB per writer. index_summary_capacity (5% of heap) is not consulted while building; it is applied only by the periodic redistribution (index_summary_resize_interval, 60m). trim() at prepareToCommit makes a full copy, and growth past the estimate copies too, so the transient peak is about 2x. Rough size: a compaction or flush writing 2e9 partitions preallocates 2e9/128 x 72 B = about 1.1 GiB, peaking at about 2.2 GiB during trim. With several concurrent compactions plus flushes this is multi-GiB of native memory outside any budget.

**Where:** BigTableWriter.java:255, IndexSummaryBuilder.java:101-130, IndexSummaryBuilder.java:204, IndexSummaryBuilder.java:247-252, SafeMemoryWriter.java:45-65, Config.java:543

## OC-428

**Case file:** `repair_session_space-setrepairsessionspaceinmib-sizeinmib-2--autonomous` · **Agent:** autonomous · **Patterns:** —

repair_session_space (default heap/16) is a budget per validation, meaning one table x one common range, not per node. The coordinator holds RF received trees per (session, table): space/RF each, and off-heap by default (use_offheap_merkle_trees=true, allocateDirect). submitRepairSessions starts one session per common range at once. concurrent_merkle_tree_requests defaults to 0, which builds a NoopScheduler with no limit, and the shipped yaml itself says this 'can produce OOM for commands repairing multiple tables or multiple virtual nodes'. The check at :4096 only warns when a single budget exceeds heap/4. It never compares the multiplied total, and the setter stores values above heap/4 anyway. Rough size: 8 GiB heap gives 512 MiB per (session, table); with num_tokens 16 and 10 tables, 160 (session, table) validations can be in flight, so up to 512 MiB x 160 = 80 GiB in theory. Even at the depth-20 cap (about 86 MiB per tree x RF 3, about 258 MiB per pair) that is about 40 GiB of coordinator direct memory.

**Where:** ValidationManager.java:60-63, Config.java:208-212, conf/cassandra.yaml:827-861, Scheduler.java:43-48, RepairCoordinator.java:127, AbstractRepairTask.java:57-88, MerkleTree.java:745-753, DatabaseDescriptor.java:4091-4100

## OC-429

**Case file:** `repair_session_space-setrepairsessionspaceinmib-sizeinmib--autonomous` · **Agent:** autonomous · **Patterns:** —

Merkle-tree memory is bounded per validation (repair_session_space/RF per replica tree; the coordinator holds RF trees, so repair_session_space per (session, table)), not per node. A repair command submits all common-range sessions at once, and concurrent_merkle_tree_requests defaults to 0, meaning no scheduler limit. The shipped yaml warns this can produce OOM for multi-table or vnode repairs. Received trees are deserialized into direct ByteBuffers by default. Rough size: heap/16 = 512 MiB at an 8 GiB heap per in-flight (session, table); 16 vnode sessions x 10 tables is up to about 160 x 258 MiB (depth-20 cap x RF 3) = about 40 GiB on the coordinator.

**Where:** ValidationManager.java:60-63, Config.java:208-212, conf/cassandra.yaml:827-861, Scheduler.java:43-48, RepairCoordinator.java:127, AbstractRepairTask.java:57-88, MerkleTree.java:745-753

## OC-430

**Case file:** `no_constraint-resizeto-newcapacity--autonomous` · **Agent:** guided · **Patterns:** CP-11, CP-9, CP-1

Holder: index-summary native memory (SafeMemoryWriter -> Memory -> Unsafe malloc) of BIG-format sstables (5.0's default selected_format is big). Each new or compacted sstable's builder allocates up front from the estimated key count at full sampling: entries are keys/128 x (64 B expected key + 8 B), plus offsets 4 B x keys/128, about 0.6 B per key. That memory stays live through the write and then becomes the reader's summary. Why nothing stops it: index_summary_capacity (5% of heap, computed from totalMemory) is only enforced by IndexSummaryManager.redistributeSummaries, which runs every index_summary_resize_interval (60 min). Builders and freshly opened summaries are never checked against it in between. The memory is outside both -Xmx and MaxDirectMemorySize, so only the container or kernel bounds it. trim() also briefly holds capacity + length (stage 4 measured a 2C peak at exact sizes). Rough size at defaults: a node with 1e9 partitions gets about 590 MB of native memory per full-table compaction output. Old summaries stay live until the sstables are swapped, and concurrent_compactors (2-8) compactions can run at once. The budget is about 410 MB at an 8 GB heap, so it only matters on dense nodes (modest).

**Where:** src/java/org/apache/cassandra/io/sstable/indexsummary/IndexSummaryBuilder.java:100-127 (prealloc, used by io/sstable/format/big/BigTableWriter.java:255 at BASE_SAMPLING_LEVEL); io/util/Memory.java:65 (malloc); io/sstable/indexsummary/IndexSummaryManager.java:141-147 (periodic redistribution only); config/DatabaseDescriptor.java:867-869 (5% default)

## OC-431

**Case file:** `native_transport_max_request_data_in_flight-applysimpleconfig-maxmessagesize--autonomous` · **Agent:** guided · **Patterns:** CP-13, CP-1, CP-10

Holder: the decompressed request body of a pre-v5 (protocol v3/v4) connection that negotiated LZ4 or Snappy in STARTUP, which happens before authentication. Envelope.Decompressor runs before the legacy dispatch handler. LZ4Compressor.decompress reads a 4-byte uncompressedLength from the client's payload and calls heapBuffer(uncompressedLength) before anything validates it (Snappy does the same through Snappy.uncompressedLength). Envelope.with() keeps the original header, so the in-flight charge in PreV5Handlers.checkLimits is header.bodySizeInBytes, the compressed size. Why nothing stops it: the only size checks on v4 are native_transport_max_frame_size (16 MiB, applied to the compressed length) and the in-flight limits (heap/10 global, heap/40 per IP), all on compressed bytes. native_transport_max_message_size is checked only on the v5 path. Rough size at defaults: a ~20-byte frame from an unauthenticated client can ask for a heap byte[] of up to 2 GiB (transient, released when the decompressor's length check fails). Several connections doing it at once exceed a default heap. Legitimate traffic: a 16 MiB compressed frame of repetitive data decompresses up to about 255x (capped at 2 GiB) while charged 16 MiB, so heap/10 of charged bytes can hold several heaps' worth of decompressed bodies. This applies equally to the per-IP limit (stem native_transport_max_request_data_in_flight_per_ip-applysimpleconfig-maxmessagesize--autonomous); file it once.

**Where:** src/java/org/apache/cassandra/transport/Compressor.java:175-186 (LZ4) and :91-99 (Snappy); transport/Envelope.java:190-193 (with keeps the compressed header), :429 (frame cap on compressed length); transport/PreV5Handlers.java:153 (charge = header.bodySizeInBytes); transport/PipelineConfigurator.java:391-396 (decompressor before the dispatch handler); transport/messages/StartupMessage.java:88-103

## OC-432

**Case file:** `native_transport_max_request_data_in_flight-applysimpleconfig-maxmessagesize--autonomous` · **Agent:** guided · **Patterns:** CP-1

Holder: the coordinator heap for decoded CQL requests (v5 path). The global (heap/10) and per-IP (heap/40) in-flight limits charge header.bodySizeInBytes, the serialized body. The decoded Message, its bound values and the Mutation/PartitionUpdate objects built from it are not charged, and they are held until the response is flushed (release at :507-510). Why nothing stops it: no limit measures the decoded or deserialized size. Rough size at defaults: for a BATCH or unlogged multi-row insert of tiny cells, deserialized objects are about 10-20x the wire bytes (the same ratio phase 2 measured for internode tiny-cell mutations). heap/10 of wire bytes then holds about 1-2x the heap, at an 8 GB heap with 800 MB charged. The per-IP limit (stem ..._per_ip-...) has the same shape.

**Where:** src/java/org/apache/cassandra/transport/CQLMessageHandler.java:195, :269 (charge = bodySizeInBytes), :507-510 (release after response); config/DatabaseDescriptor.java:649-657 (heap/10, heap/40 defaults)

## OC-433

**Case file:** `native_transport_max_request_data_in_flight_per_ip-applysimpleconfig-maxmessagesize--autonomous` · **Agent:** guided · **Patterns:** CP-7, CP-8

Holder: request payload held per v5 client connection. AbstractMessageHandler.acquireCapacity first takes bytes from the connection's own queueCapacity (native_transport_receive_queue_capacity, 1 MiB) and touches the endpoint (per-IP, heap/40) and global (heap/10) reserves only for the excess. Each connection can therefore hold up to 1 MiB of in-process requests charged to neither in-flight limit, plus their decoded objects. Why nothing stops it: native_transport_max_concurrent_connections and native_transport_max_concurrent_connections_per_ip ship as -1 (unlimited), and no limit caps the sum of per-connection allowances. Rough size at defaults: 1 MiB x connections, outside both in-flight limits. For example, 2,000 connections from one or many IPs give about 2 GiB more than the heap/10 and heap/40 limits allow (before the decoded-object amplification). This is the client-side counterpart of the per-peer receive allowance outside the reserve. It also concerns the global limit (stem native_transport_max_request_data_in_flight-applysimpleconfig-maxmessagesize--autonomous).

**Where:** src/java/org/apache/cassandra/net/AbstractMessageHandler.java:411-421 (per-connection capacity taken first, reserves untouched); transport/PipelineConfigurator.java:306; transport/CQLMessageHandler.java:693-704; config/Config.java:289, :302; conf/cassandra.yaml:1048, :1052 (connection caps -1)

## OC-434

**Case file:** `repair_session_space-setrepairsessionspaceinmib-sizeinmib-2--autonomous` · **Agent:** guided · **Patterns:** CP-7, CP-8, CP-4

Holder: Merkle trees received on the repair coordinator. Each (session, table) validation sizes its trees so that RF replica trees fit in repair_session_space (default heap/16). The coordinator holds all RF trees, in direct memory by default (use_offheap_merkle_trees true), until every replica has answered and the differences are computed. Why nothing stops it: a repair command submits one RepairSession per common range at once (vnodes, num_tokens 16). concurrent_merkle_tree_requests ships as 0, which builds a NoopScheduler (no limit). The budget is per validation, never summed. The 25%-of-heap check only warns and stores the value anyway, at startup and in the JMX setter. A slow replica validation keeps the other replicas' trees held for its whole duration. Rough size at defaults: 8 GB heap gives 512 MiB per in-flight (session, table) on the coordinator. 8-16 sessions in flight is 4-8 GiB of direct memory against a MaxDirectMemorySize that defaults to about the heap size, shared with the networking and chunk-cache pools. The same mechanism applies to the < 1 setter check case (stem repair_session_space-setrepairsessionspaceinmib-sizeinmib--autonomous); file it once.

**Where:** src/java/org/apache/cassandra/repair/ValidationManager.java:60-76 (budget per validation / RF); repair/Scheduler.java:43-47 and repair/RepairCoordinator.java:127 (0 = no limit); repair/AbstractRepairTask.java:66-86 (all sessions submitted at once); config/Config.java:208-212; config/DatabaseDescriptor.java:609-615, :4096-4100 (warn only); conf/cassandra.yaml:42 (num_tokens 16)

## OC-435

**Case file:** `mutation_repair_rows_per_batch-throttledunfilterediterator-maxbatchsize--autonomous` · **Agent:** autonomous · **Patterns:** —

Holder: the PartitionUpdate built for each throttled batch on the streaming write path (CDC-on-repair, MV-on-repair or streamToMemtable tables). Why nothing stops it: the batch cap is a count of Unfiltereds (default 100 rows, ThrottledUnfilteredIterator.withinLimit), not bytes. Each batch is fully materialised on heap by PartitionUpdate.fromIterator before ks.apply, and only then does the commit-log max_mutation_size check reject an oversized batch on CDC tables (stage 4 saw the 426 MB N=0 update built, then rejected). A single row can be up to about 16 MiB (max_mutation_size per client write), and it can grow larger still through many collection or column updates. Rough size at defaults: 100 rows x up to about 16 MiB = about 1.6 GiB per batch on one stream-receiver thread, and several sessions or tables can do this concurrently. Caveat: this path is only taken when CDC, MV-on-repair or a trie streamToMemtable table is enabled, which is not the shipped default.

**Where:** src/java/org/apache/cassandra/db/rows/ThrottledUnfilteredIterator.java:146; src/java/org/apache/cassandra/db/streaming/CassandraStreamReceiver.java:63, 212, 221; src/java/org/apache/cassandra/db/streaming/CassandraStreamReceiver.java:195-200 (requiresWritePath)

## OC-436

**Case file:** `no_constraint-allocateblock-inchunkpointer--autonomous` · **Agent:** autonomous · **Patterns:** —

Holder: the InMemoryTrie buffer chunks that allocateBlock allocates on a chunk start (256 << leadBit bytes in one allocation, on heap under the default memtable_allocation_type heap_buffers). Why nothing stops it: sizeOnHeap() and sizeOffHeap() report allocatedPos (bytes handed out), not the capacity of the buffers allocated. The trie memtable's pool accounting (allocator.onHeap/offHeap().adjust with the size delta) and SAI's memory-index accounting therefore see only +32 B when a whole new doubling chunk is allocated. The real buffer footprint is up to about 2x what is charged (stage 4 measured retained buffers at 2.0-2.7x allocatedPos right after a chunk start). Rough size at defaults: when a shard trie crosses 512 MiB or 1 GiB of allocatedPos, a 512 MiB or 1 GiB chunk is allocated but charged 32 B. Summed over the default shard count (one per CPU), the unaccounted slack can approach the whole memtable_heap_space budget (heap/4, for example 2 GiB at an 8 GiB heap), on top of what the cleaner believes is in use.

**Where:** src/java/org/apache/cassandra/db/tries/InMemoryTrie.java:145-152, 969-981; src/java/org/apache/cassandra/db/memtable/TrieMemtable.java:477-485; src/java/org/apache/cassandra/index/sai/memory/TrieMemoryIndex.java:99-127; src/java/org/apache/cassandra/index/sai/disk/v1/segment/SegmentTrieBuffer.java:59-77

## OC-437

**Case file:** `row_cache_size-isrowcacheenabled-rowcachecapacity--autonomous` · **Agent:** autonomous · **Patterns:** —

Holder: the CachedBTreePartition built on heap on every row-cache miss. Why nothing stops it: when the gate is true and rows_per_partition=ALL (cacheFullPartitions), getThroughCache always reads the whole partition (fullPartitionRead) and materialises it via CachedBTreePartition.create. This ignores the query's LIMIT and paging and ignores row_cache_size: an entry larger than the OHC capacity or segment is built and then dropped. It is also built when the sentinel putIfAbsent failed (sentinelSuccess false), so concurrent misses on the same hot partition each materialise their own copy. Rough size: partition size x concurrent misses. For example, a 200 MB partition x concurrent_reads 32 = about 6.4 GB of heap, which exceeds a default 8 GiB-or-smaller heap. The OHC copy is also serialised off heap with throwOOME(true). Caveat: row_cache_size defaults to 0, so the row cache must be enabled.

**Where:** src/java/org/apache/cassandra/db/SinglePartitionReadCommand.java:547-569, 604; src/java/org/apache/cassandra/db/ColumnFamilyStore.java:3262; src/java/org/apache/cassandra/cache/OHCProvider.java:40-43; conf/cassandra.yaml:722

## OC-438

**Case file:** `row_overhead_size-intrie_init-limitinmb--autonomous` · **Agent:** autonomous · **Patterns:** —

Holder: TrieMemtable shard trie buffers. Why nothing stops it: ALLOCATED_SIZE_THRESHOLD (default 1861 MiB per shard) and the memtable pool both measure allocatedPos, but allocateBlock allocates doubling chunks, so the real buffer bytes run up to about 2x the measured figure. At default, crossing about 1 GiB of allocatedPos allocates a 1 GiB chunk that is charged as 32 B; stage 4 saw the direct pool +2051 MiB at the 1861 MiB signal. The soft threshold is also not a write bound: writes continue past the flip up to the 2 GiB hard limit, and two tries are alive during a flush (stage 4: 131 MiB of direct memory at N=64). The threshold is per shard, so the node total is shards x 1861 MiB (39 x N with 40 shards) and is bounded only by the pool accounting, which undercounts the chunks. Rough size at defaults: up to about 1 GiB unaccounted per busy shard, and about 2 GiB of buffers per shard before the trie signal at 1861 MiB. Under heap_buffers (the default allocation type) this is heap.

**Where:** src/java/org/apache/cassandra/db/tries/InMemoryTrie.java:63-67, 145-152, 951-953, 969-981; src/java/org/apache/cassandra/db/memtable/TrieMemtable.java:192-196, 477-485; src/java/org/apache/cassandra/db/memtable/AbstractShardedMemtable.java:46

## OC-439

**Case file:** `segment_write_buffer_size-validate-maximum_segment_buffer_mb--autonomous` · **Agent:** autonomous · **Patterns:** —

Holder: SAI segment builders' SegmentTrieBuffer tries (plus postings) during compaction and index build. These are on heap under the default memtable_allocation_type heap_buffers. Why nothing stops it: the global limiter (default 1024 MiB, separate from memtable_heap_space) is charged with trie.sizeOnHeap(), which counts allocatedPos and not the doubling buffer chunks. A single builder may grow to the full limit (minimumFlushBytes = limit / active builders), so its trie crosses the 1 GiB-256 B chunk start and allocates a 1 GiB buffer that is charged 32 B. The limit is also checked only at the next addTerm (soft overshoot). Rough size at defaults: about 1 GiB charged but up to about 2 GiB real for one building index, held concurrently with memtables (heap/4) and caches on a default 4-8 GiB heap.

**Where:** src/java/org/apache/cassandra/index/sai/disk/v1/V1OnDiskFormat.java:126-128; src/java/org/apache/cassandra/index/sai/disk/v1/segment/SegmentTrieBuffer.java:48, 59-77; src/java/org/apache/cassandra/index/sai/disk/v1/segment/SegmentBuilder.java:149, 211-213; src/java/org/apache/cassandra/index/sai/disk/v1/SSTableIndexWriter.java:225-248; src/java/org/apache/cassandra/db/tries/InMemoryTrie.java:145-152, 975-981

## OC-440

**Case file:** `segment_write_buffer_size-validate-maximum_segment_buffer_mb--autonomous` · **Agent:** guided · **Patterns:** CP-1, CP-9, CP-7

Holder: the SAI segment builder's term trie (SegmentTrieBuffer -> InMemoryTrie), created with the buffer type of memtable_allocation_type. Why nothing stops it: the limiter is charged with memoryUsed() = trie.sizeOnHeap() + postings. For an OFF_HEAP trie, sizeOnHeap() leaves out allocatedPos (InMemoryTrie.java:969-981), so the term and trie-node bytes in direct ByteBuffers are charged as 0. Only content references and PackedLongValues builders are counted. With offheap_objects or offheap_buffers (offheap_objects is the cassandra_latest.yaml default), segment_write_buffer_size (1024 MiB) therefore does not bound the trie. Each builder grows until its counted postings reach limit/activeBuilders, or until the 2 GiB trie hard limit throws SpaceExhaustedException. Size: up to about 2 GiB of direct memory per active builder (chunk capacities sum to 2^31). Active builders are concurrent compactions or index builds times the SAI indexes on the table, and nothing caps their sum. The budget is MaxDirectMemorySize, which cassandra-env.sh sets to RAM/4 (= heap/2); the chunk cache and trie memtables share it. Long high-cardinality text terms (up to the 8 KiB term fail threshold) push held/counted to many times 1.

**Where:** src/java/org/apache/cassandra/index/sai/disk/v1/segment/SegmentTrieBuffer.java:48,59; src/java/org/apache/cassandra/db/tries/InMemoryTrie.java:151,969-981; src/java/org/apache/cassandra/index/sai/disk/v1/SSTableIndexWriter.java:225-248

## OC-441

**Case file:** `segment_write_buffer_size-validate-maximum_segment_buffer_mb--autonomous` · **Agent:** guided · **Patterns:** CP-8, CP-1

Holder: SAI segment builders on heap, with the default memtable_allocation_type heap_buffers. Why nothing stops it: segment_write_buffer_size defaults to a fixed 1024 MiB (StorageAttachedIndexOptions.java:26) that does not scale with the heap and is never compared with it. cassandra-env.sh sizes the heap at RAM/2. On a 4 GiB-RAM node (2 GiB heap) the SAI build budget alone is half the heap. Other heap defaults stack on top of it: memtable_heap_space heap/4, key cache 5%/100 MiB, counter and paxos caches, prepared statements. The InMemoryTrie buffers also double (256<<i chunks), so held capacity can reach about 2x the counted allocatedPos (stage-4 unit reading on the sibling allocateBlock case: 2.0-2.7x). Size: about 1-2 GiB of build buffers at defaults, plus about 0.75 GiB of other defaults, against a 2 GiB heap during an initial index build or compaction of a large indexed sstable.

**Where:** src/java/org/apache/cassandra/config/StorageAttachedIndexOptions.java:26; src/java/org/apache/cassandra/index/sai/disk/v1/V1OnDiskFormat.java:126-128; conf/cassandra-env.sh:58-66

## OC-442

**Case file:** `segment_write_buffer_size-validate-maximum_segment_buffer_mb--autonomous` · **Agent:** guided · **Patterns:** CP-10, CP-9, CP-1, CP-14

Holder: RowMapping, built on every memtable flush of a table with SAI. It is an InMemoryTrie that is always OFF_HEAP (direct) and holds every primary key of the flushing memtable mapped to its sstable row id. Why nothing stops it: it is outside the segment limiter (the flush path uses MemtableIndexWriter) and is not charged to the memtable pool. discardBuffers() is never called on it, so the direct buffers are freed only when GC runs their cleaners. Size: about key bytes plus trie overhead per row of the memtable (hundreds of MB for a memtable with millions of small rows; up to 2 GiB per flush, where SpaceExhaustedException fails the flush). Multiplied by concurrent flushes (memtable_flush_writers), it draws on the same RAM/4 direct budget.

**Where:** src/java/org/apache/cassandra/index/sai/disk/RowMapping.java:75,86-91; src/java/org/apache/cassandra/index/sai/disk/v1/V1OnDiskFormat.java:170-185

## OC-443

**Case file:** `row_cache_size-isrowcacheenabled-rowcachecapacity--autonomous` · **Agent:** guided · **Patterns:** CP-12, CP-10, CP-1

Holder: the heap copy built on a row-cache miss. When rows_per_partition is ALL (or the table has no clustering columns), any read of the partition, including LIMIT 1 or a single page of a paged query, runs fullPartitionRead(...) and materializes the whole partition as a CachedBTreePartition on heap before OHC serializes it. Why nothing stops it: paging and the read's limits are bypassed on this path. The heap copy is not charged to row_cache_size. If the serialized entry is too large for OHC or gets evicted, every later page repeats the full materialization. Size: one whole partition per concurrent missing read (concurrent_reads = 32), e.g. 32 x a 100 MB partition = 3.2 GB. Requires row_cache_size > 0 and caching rows_per_partition ALL; both are documented options but off by default. A second, smaller gap: OHC charges serialized bytes, and its per-entry and table overhead in native memory is uncounted (amount unknown).

**Where:** src/java/org/apache/cassandra/db/SinglePartitionReadCommand.java:546-569,604; src/java/org/apache/cassandra/cache/OHCProvider.java:40-43

## OC-444

**Case file:** `counter_cache_size-putcachedcounter-capacity--autonomous` · **Agent:** guided · **Patterns:** CP-1

Same mechanism as phase-2 B7; file once. It also applies to the stems counter_cache_size-iscountercacheenabled-capacity--autonomous, counter_cache_size-getcachedcounter-capacity--autonomous and counter_cache_size-processmodifications-capacity--autonomous. Holder: the Caffeine counter cache. Why nothing stops it: the weigher charges only key.unsharedHeapSize() + value.unsharedHeapSize() (about 112-120 B per entry). It omits Caffeine's node, the ConcurrentHashMap node, the table slot and the sketch slot (about 90 B per entry), so the cap bounds the counted weight, not the heap held. Stage 4 measured whole-heap growth of 1.78-2.06 x Size. Size: about 0.8-1 x counter_cache_size extra, i.e. about 40-50 MiB above the 50 MiB auto default. This is a bounded constant factor; the gap matters only when stacked with other heap defaults.

**Where:** src/java/org/apache/cassandra/cache/CaffeineCache.java:54-69; src/java/org/apache/cassandra/service/CacheService.java:172-179

## OC-445

**Case file:** `monitoring_max_operations-operationsqueue_offer-maxoperations--autonomous` · **Agent:** guided · **Patterns:** CP-2, CP-3, CP-12

Holder: MonitoringTask's failed and slow OperationsQueues. Each Operation pins its Monitorable (the whole ReadCommand, with its ClusteringIndexNamesFilter, RowFilter and key) for up to the 5 s report interval after the read completes or times out. Why nothing stops it: the cap counts items (2 x 50 at defaults), not bytes. A command's size is bounded only by the 16 MiB native frame (large clustering IN lists, large partition keys or filter values). The native-transport in-flight request bytes are released when the response is sent, while the command stays reachable from the queue. At drain, name() renders each distinct command to CQL text, and the aggregated map plus log StringBuilder hold another string copy (hex rendering of blobs is about 2x). Slow means just 500 ms (slow_query_log_timeout), so 100 large slow reads within 5 s are reachable. Size: up to 100 x command size held after completion, e.g. 100 x 10 MB = 1 GB (theoretical 1.6 GB at the frame limit), plus the rendered strings.

**Where:** src/java/org/apache/cassandra/db/monitoring/MonitoringTask.java:210,221-225,313,340; src/java/org/apache/cassandra/db/monitoring/MonitorableImpl.java:101,115

## OC-446

**Case file:** `mutation_repair_rows_per_batch-throttledunfilterediterator-maxbatchsize--autonomous` · **Agent:** guided · **Patterns:** CP-2, CP-11, CP-7

Holder: the PartitionUpdate/Mutation built per throttled slice in sendThroughWritePath. Why nothing stops it: the throttle counts unfiltereds (100 by default), not bytes. A single row is bounded in size only by what accumulated over many writes (many columns, growing collections; the collection-size guardrails are off by default). On a CDC table, max_mutation_size (16 MiB) is checked only after the update is materialized (stage 4: MutationExceededMaxSizeException after building 21 MB and 426 MB updates). The bound applies per receiving stream session, and nothing caps the total across concurrent incoming repair streams. Size: 100 x row size per stream session, e.g. 100 x 10 MiB rows = 1 GiB per stream, times the concurrent stream sessions. Reachable only when the write path is required (a CDC table, materialized views on repair, or a memtable that streams to the memtable), so it is off at shipped defaults.

**Where:** src/java/org/apache/cassandra/db/streaming/CassandraStreamReceiver.java:63,195-227; src/java/org/apache/cassandra/db/rows/ThrottledUnfilteredIterator.java:146-149,232-251

## OC-447

**Case file:** `row_overhead_size-intrie_init-limitinmb--autonomous` · **Agent:** guided · **Patterns:** CP-1

Holder: SkipListMemtable heap accounting. Why nothing stops it: one JVM property, cassandra.memtable.row_overhead_size, is read in two units. InMemoryTrie reads it as the trie threshold in MB (valid 1..2047). SkipListMemtable reads it as the per-partition heap overhead in bytes, replacing the measured estimateRowOverhead() whenever the value is > 0. An operator who sets it to tune the trie threshold (e.g. 16 or 64) therefore makes every skip-list table charge only token + 16 or 64 B of overhead per partition instead of the measured skip-list and partition overhead. The undercount applies against memtable_heap_space (heap/4 by default). Size: for small partitions the real memtable heap can run well past memtable_heap_space, roughly 1.5-2x (up to about heap/2), before the memtable flushes. Requires the non-default -D.

**Where:** src/java/org/apache/cassandra/db/memtable/SkipListMemtable.java:72-80,124; src/java/org/apache/cassandra/db/tries/InMemoryTrie.java:63-67

## OC-448

**Case file:** `no_constraint-allocateblock-inchunkpointer--autonomous` · **Agent:** guided · **Patterns:** CP-1, CP-8, CP-9

Holder: InMemoryTrie buffers of TrieMemtable shards (also the SAI TrieMemoryIndex). allocateBlock() allocates each new chunk as a doubling buffer (256<<leadBit, up to a single 1 GiB chunk). TrieMemtable charges the memtable pool only the delta of sizeOffHeap()/sizeOnHeap(), which count allocatedPos, not the buffer capacity. Why nothing stops it: right after a chunk boundary is crossed, the held capacity is about 2x the charged bytes (stage-4 unit reading: 2.0-2.7x), and memtable_heap_space / memtable_offheap_space bound only the charged bytes. Each shard (shard count = number of cores) sits at its own boundary. With offheap_* the buffers are allocateDirect, so they also count against MaxDirectMemorySize. cassandra-env.sh sets that to RAM/4 = heap/2, and the chunk cache (min(512 MiB, heap/4)) and network buffers share it. Size: up to about memtable_offheap_space extra (heap/4) of direct memory, e.g. 1 GiB more than charged at a 4 GiB heap. With heap_buffers and few shards, a single 1 GiB on-heap chunk is allocated in one step while the charge grows by 32 B. Reachable with the trie memtable (the default in cassandra_latest.yaml with offheap_objects; opt-in in cassandra.yaml). The same doubling applies to the SAI SegmentTrieBuffer; see segment_write_buffer_size-validate-maximum_segment_buffer_mb--autonomous.

**Where:** src/java/org/apache/cassandra/db/tries/InMemoryTrie.java:145-158,969-981; src/java/org/apache/cassandra/db/memtable/TrieMemtable.java:477-485; conf/cassandra-env.sh:58-66

## OC-449

**Case file:** `batch_size_fail_threshold-verifyBatchSize-mutations--autonomous` · **Agent:** autonomous · **Patterns:** —

Holder: the coordinator heap, which holds every Mutation/PartitionUpdate/Row of the batch. Why nothing stops it: getMutations builds all mutations before verifyBatchSize runs, so batch_size_fail_threshold (50 KiB) rejects the batch only after the full object graph already exists. Nothing caps the expansion before that. Each statement makes |pk IN| x |ck IN| rows (addUpdates loops over every key and then every clustering). The only guard on that cartesian product is in_select_cartesian_product, and it is disabled by default (-1), so its guard calls never run. The single-mutation exemption at :334 and a plain UPDATE skip the batch check entirely; there max_mutation_size is checked only later, at apply time. Rough size at defaults: one request of about 100-200 KB carrying 10,000 partition keys and 10,000 clustering values in IN lists builds 1e8 rows at about 100 B each, so roughly 10 GB of heap before the 'Batch too large' rejection. Even 3,000 x 3,000 gives about 1 GB per request, and up to 128 native-transport threads can do this at once.

**Where:** BatchStatement.java:428 (getMutations) before BatchStatement.java:439 (verifyBatchSize); ModificationStatement.java:790-818; ClusteringColumnRestrictions.java:112-113; PartitionKeySingleRestrictionSet.java:95-96; Config.java:877-878

## OC-450

**Case file:** `bloom_filter_fp_chance-computeBloomSpec-maxFalsePosProb--autonomous` · **Agent:** autonomous · **Patterns:** —

Holder: one native (off-heap) bloom bitset per SSTable, allocated with Memory.allocate. Why nothing stops it: computeBloomSpec sets bits per key only, so total native bytes grow with partitions x SSTables. No budget or accounting stops it; the only check is the >16 GB-per-filter reject in OffHeapBitSet. Keys repeated across overlapping STCS SSTables are counted again in each one. During compaction the output filter is allocated up front at the full estimated key count (DefaultCompactionWriter passes estimatedTotalKeys) while the input filters stay live, so usage is about 2x for the compacted set, multiplied by concurrent compactors. Rough size at defaults: fp 0.01 (STCS default) gives 10 bits, about 1.25 B per key. A node with 2-5 billion small partitions holds about 2.5-6 GB of native memory, plus the same again for a large compaction. This can exhaust native memory or the container limit outside the Java heap.

**Where:** BloomCalculations.java:140-172; FilterFactory.java:60-75; OffHeapBitSet.java:41-48; SortedTableWriter.java:445; CompactionAwareWriter.java:84,235; DefaultCompactionWriter.java:64

## OC-451

**Case file:** `bloom_filter_fp_chance-getFilter-maxFalsePosProbability--autonomous` · **Agent:** autonomous · **Patterns:** —

Holder: off-heap bloom bitsets, one per SSTable (FilterFactory.createFilter -> new OffHeapBitSet -> Memory.allocate). Why nothing stops it: only fp == 1.0 skips the allocation. Any other fp sizes the filter as keyCount x bits per key with no total budget, so the sum over all SSTables grows without bound with partition count and SSTable overlap. Compaction allocates the output filter at the estimated total key count before the inputs are released, so both exist at once. The only guard is the 16 GB-per-single-filter reject. Rough size at defaults: fp 0.01 gives 10 bits, about 1.25 B per partition key per SSTable. 2-5 billion partitions is about 2.5-6 GB native, and up to about 2x that during large compactions, outside the heap and any Cassandra limit.

**Where:** FilterFactory.java:60-75; OffHeapBitSet.java:41-48; SortedTableWriter.java:445; CompactionAwareWriter.java:84,235

## OC-452

**Case file:** `ExecuteMessage_literal_1000-traceQuery-1000--autonomous` · **Agent:** autonomous · **Patterns:** —

Holder: the transient full CQL literal of each traced bound value on the native-transport thread. Why nothing stops it: toCQLLiteral renders the whole value before the 1000-char check. For a blob, bytesToHex allocates a char[2S] (4S bytes), wraps it in a String (about 2S more), and '0x' + concatenation copies it again, so peak is about 6-8 x S per traced value. Any client can set the tracing flag on its own requests. In-flight limits count only raw request bytes (heap/10 total, heap/40 per IP), not this amplification. Rough size at defaults: max message = min(max_mutation_size 16 MiB, heap/40), so one EXECUTE with a 16 MiB blob costs about 100-128 MiB of transient heap. With an 8 GB heap, about 800 MB of raw requests may be in flight (about 50 such requests on up to 128 threads), which gives about 5-6 GB of transient heap.

**Where:** ExecuteMessage.java:230-232; BytesSerializer.java:67; ByteBufferUtil.java:635-644 / Hex.java:76-86; DatabaseDescriptor.java:649-656,3237-3244

## OC-453

**Case file:** `ExecuteMessage_literal_1000-traceQuery-1000--autonomous` · **Agent:** autonomous · **Patterns:** —

Holder: start-session trace mutations queued on the single-thread TRACING stage. Why nothing stops it: the stage queue is limited by count (1000), not bytes. Each queued mutation carries the uncut 'query' text plus up to B x 1004 chars of bound values. Once the request finishes, those bytes no longer count against the native in-flight limits. Rough size at defaults: a traced EXECUTE with about 30k bind markers whose values each render to more than 1000 chars fits a 16 MiB request but carries about 30 MB of parameters. A traced unprepared QUERY carries its up-to-16 MiB query text. If the one tracing thread falls behind, 1000 x 16-30 MB means about 16-30 GB can queue.

**Where:** ExecuteMessage.java:223-239; TracingImpl.java:53-66; TraceStateImpl.java:104-107; Stage.java:196-202

## OC-454

**Case file:** `MAXIMUM_MAXIMUM_NODE_CONNECTIONS-fromOptions-maximumNodeConnections--autonomous` · **Agent:** autonomous · **Patterns:** —

Holder: the PQ-compressed vectors of every on-disk SAI vector segment, held on heap as byte[][] (jvector CompressedVectors) for as long as the SSTable is open. Why nothing stops it: the M cap bounds graph neighbour slots per vector only. PQ uses dimension/2 subspaces, so each vector keeps dim/2 bytes plus a byte[] header on heap. Nothing caps the total: it is not counted against memtable space or the SAI segment-build limiter, and it grows with every vector on the node. Flush and compaction also build a second full byte[][] of encodings for the segment, outside the limiter's accounting. Rough size at defaults: 1536-dim vectors take about 784 B each, so 2M vectors on a node is about 1.5 GB of heap and 10M vectors is about 7.8 GB, plus a transient copy per segment being compacted.

**Where:** DiskAnn.java:63-70 (CompressedVectors.load); OnHeapGraph.java:371-397 (M = dim/2, encoded byte[][]); jvector-1.0.2 CompressedVectors.compressedVectors byte[][]

## OC-455

**Case file:** `sai_vector_search_max_top_k-validate-limit_count--autonomous` · **Agent:** autonomous · **Patterns:** —

Holder: the coordinator heap, which holds the top-K responses from every contacted node at once. Why nothing stops it: MAX_TOP_K caps rows per replica, not the number of replicas. For top-K queries, ScanAllRangesCommandIterator sends one full-range command to every contacted node and waits for all responses in one ReadCallback/DataResolver before merging. SelectStatement also raises the page size to LIMIT, so the result is not paged. Rough size at defaults: LIMIT 1000 with 1536-dim float vectors (about 6 KiB per row) is about 6 MiB per node. On a 100-node cluster that is about 600 MB for one query, each node's response limited only by internode_max_message_size (128 MiB by default). Several concurrent ANN queries can exhaust the coordinator heap.

**Where:** StorageAttachedIndex.java:503; RangeCommands.java:81-82; ScanAllRangesCommandIterator.java:93-115; SelectStatement.java:322-329; DatabaseDescriptor.java:992-996

## OC-456

**Case file:** `sai_vector_search_max_top_k-validate-limit_count--autonomous` · **Agent:** autonomous · **Patterns:** —

Holder: each replica's eagerly materialized top-K rows, in the TreeMap/TreeSet built by takeTopKThenSortByPrimaryKey, plus the coordinator's InMemoryPartitionIterator. Why nothing stops it: the cap counts rows, not bytes. Non-vector columns of the selected rows (for example text chunks) can be up to max_mutation_size (16 MiB), and byte-based read thresholds are off by default. Rough size at defaults: 1000 rows x 100 KiB is about 100 MB per query per replica, and concurrent_reads 32 such queries is about 3 GB.

**Where:** StorageAttachedIndexSearcher.java:146-148; VectorTopKProcessor.java:168-185; VectorTopKProcessor.java:91-136; Config.java:526

## OC-457

**Case file:** `SelectStatement_DEFAULT_PAGE_SIZE-getDataLimits-pageSize--autonomous` · **Agent:** autonomous · **Patterns:** —

Holder: one read response that holds every scanned row. For a local read, LocalDataResponse serializes the whole result into a single DataOutputBuffer, which grows by doubling. Why nothing stops it: an aggregate without GROUP BY (AGGREGATE_EVERYTHING), with client paging off, gets cqlLimits(NO_LIMIT). AggregationPartitionIterator then uses that as its sub-page size, so the 10000-row DEFAULT_PAGE_SIZE never applies. Read-size thresholds are disabled by default. Remote responses fail above internode_max_message_size, but a local replica response has no cap. Rough size at defaults: SELECT count(*) / sum(...) over 100k 4 KiB rows gives a 411 MB response in a 514 MB array (measured in stage 4). A 1 GB partition gives about 1-2 GB in one request, and a few concurrent requests cause OOM.

**Where:** SelectStatement.java:899-921; SelectStatement.java:338-355; AggregationQueryPager.java:406-443; ReadResponse.java:192-203; Config.java:526

## OC-458

**Case file:** `SelectStatement_DEFAULT_PAGE_SIZE-getDataLimits-pageSize--autonomous` · **Agent:** autonomous · **Patterns:** —

Holder: per-read response and coordinator page, sized by the client page size P. Why nothing stops it: any client page size above 0 replaces DEFAULT_PAGE_SIZE as the GROUP BY rowLimit and as the normal page size. The page_size guardrail is disabled by default (fail threshold -1), so P = Integer.MAX_VALUE removes internal sub-paging. Rough size at defaults: bytes per read follow P (205.7 MB at P = 50,000 x 4 KiB rows in stage 4). P in the millions is unbounded in practice and limited only by partition or table size.

**Where:** SelectStatement.java:899-902; DataLimits.java:116-121; Config.java:873-874

## OC-459

**Case file:** `vector_memory_index_cost_model-orderby-bruteforcerows--autonomous` · **Agent:** autonomous · **Patterns:** —

Holder: the per-query brute-force scored list of a token-range-restricted ANN query. VectorMemoryIndex.orderByBruteForce builds an ArrayList and then a PriorityQueue with one PrimaryKeyWithScore per in-range memtable key. Why nothing stops it: the cutoff is a fitted cost formula, not a memory cap, and brute force is chosen for ranges up to a large share of the memtable graph. At LIMIT 1000 that is about 40% of a 100k graph, about 24% (243k keys) of a 1M graph and about 16% (660k) of a 4M graph. The memtable is bounded only by memtable_heap_space, and orderBy runs eagerly for every memtable index. Rough size at defaults: about 50-60 B retained per key, so about 13-40 MB per memtable per query, times 32 concurrent_reads, gives about 0.4-1.3 GB of transient heap.

**Where:** VectorMemoryIndex.java:182-191; VectorMemoryIndex.java:238-286; VectorMemoryIndex.java:248-261; QueryController.java getTopKRows (memtableIndex.orderBy loop); Config.java:179

## OC-460

**Case file:** `vector_memory_index_cost_model-orderby-bruteforcerows--autonomous` · **Agent:** autonomous · **Patterns:** —

Holder: the disk-segment twin of the same switch. For a range-restricted ANN query, each SSTable segment allocates SegmentRowIdOrdinalPairs(nRows), an int[2*nRows], and then a NeighborQueue holding every pair. That is about 16 B per in-range row, built eagerly for every segment in QueryController.getTopKRows. Why nothing stops it: maxBruteForceRows = max(limit, 0.25 x M(16) x expectedNodesVisited), about 4x the memtable formula, so brute force is chosen for roughly 40% of each segment. Nothing caps the sum across segments: sai_sstable_indexes_per_query_fail_threshold is -1. Rough size at defaults: a node with 100M vectors and a token range covering 30% gives about 30M rows x 16 B, about 480 MB per query, and 32 concurrent reads multiply that.

**Where:** VectorIndexSegmentSearcher.java:152-172; VectorIndexSegmentSearcher.java:239-256; VectorIndexSegmentSearcher.java:351-362; SegmentRowIdOrdinalPairs.java:40-46,98-105; Config.java:940

## OC-461

**Case file:** `vector_memory_index_cost_model-orderresultsby-maxbruteforcerows--autonomous` · **Agent:** autonomous · **Patterns:** —

Holder: per-SSTable-segment copies for hybrid (WHERE + ANN) queries. For each SSTable index, VectorIndexSegmentSearcher.orderResultsBy copies the up-to-16000 materialized keys into keysInRange. It then builds SegmentRowIdOrdinalPairs (int[2n]) and, on the brute-force branch, a NeighborQueue of all n. All of this happens eagerly for every segment in QueryController.getTopKRows before any row is returned. Why nothing stops it: MAX_MATERIALIZED_KEYS (16000) bounds one list, not the number of copies. Overlapping SSTables (STCS) each span the full key range, so each gets all 16000, and the number of SSTable indexes per query has no default fail threshold (-1). Rough size at defaults: about 16000 x (8 + 8 + 16) B, about 0.5 MB per segment. 200 segments is about 100 MB per query, and 32 concurrent reads is about 3 GB.

**Where:** QueryController.java:406-425,436-455; VectorIndexSegmentSearcher.java:283-330; SegmentRowIdOrdinalPairs.java:40-46,98-117; Config.java:939-940

## OC-462

**Case file:** `sai_vector_search_max_top_k-validate-limit_count--autonomous` · **Agent:** guided · **Patterns:** CP-7, CP-2, CP-1

Holder: the coordinator of an ANN top-k query (ReadCallback/DataResolver holding every replica's response). For top-k, RangeCommands sends one full-range command at once to every contacted node (ScanAllRangesCommandIterator) and waits for all of them. Each response can carry up to LIMIT <= MAX_TOP_K = 1000 rows. Why nothing stops it: MAX_TOP_K counts rows per replica, not bytes, and not nodes. Row size is limited only per write (max_mutation_size 16 MiB). Read-size thresholds and column-value guardrails are off by default. The query's own in-flight charge is the tiny SELECT on the wire. Size at defaults: about 1000 x 6 KiB (1536-dim float vectors) = 6 MiB per node, roughly doubled serialized plus deserialized. That is about 360 MiB per query on a 30-node cluster, and 128 native-transport threads can run such queries at once (several GiB). It grows linearly with wider non-vector columns.

**Where:** src/java/org/apache/cassandra/service/reads/range/ScanAllRangesCommandIterator.java:93-103 (fan-out); RangeCommands.java:81-82; StorageAttachedIndex.java:503 (row-count cap); VectorTopKProcessor.java:91,121-123

## OC-463

**Case file:** `ExecuteMessage_literal_1000-traceQuery-1000--autonomous` · **Agent:** guided · **Patterns:** CP-1, CP-12, CP-6

Holder: ExecuteMessage.traceQuery on the coordinator heap. For every bound value of a traced EXECUTE it builds the full CQL literal before the 1000-char cut. For an S-byte blob, Hex.bytesToHex makes a char[2S] (4S bytes), wraps it in a String, and "0x"+... copies it again. That is about 8S allocated and about 6S live per value, and stage 4 saw a 4 MB char[] and 3 allocations of 1 MiB or more per 1 MiB value. Why nothing stops it: the 1000-char cut runs after the rendering. The native-transport in-flight limiter charges only the on-wire bytes (S). Any client can turn tracing on per request with the tracing flag, with no server setting. Only the JVM's own error stops the allocation. Size at defaults: a 16 MiB value gives about 96 MiB live per request. With an 8 GiB heap the in-flight reserve (heap/10, about 819 MiB, heap/40 per IP) admits about 51 such requests from 4 or more client IPs, about 4.8 GiB of transient heap against about 0.8 GiB counted.

**Where:** src/java/org/apache/cassandra/transport/messages/ExecuteMessage.java:230-232; utils/Hex.java:76-86; serializers/BytesSerializer.java:65-68; transport/Message.java:237-241

## OC-464

**Case file:** `SelectStatement_DEFAULT_PAGE_SIZE-getDataLimits-pageSize--autonomous` · **Agent:** guided · **Patterns:** CP-10, CP-12, CP-2, CP-8

Holder: the replica and coordinator read response. A local data response is serialized whole into one heap DataOutputBuffer, which grows x2 and then x1.5. Why nothing stops it: DEFAULT_PAGE_SIZE (10000 rows) sub-pages only GROUP BY queries. An aggregate without GROUP BY (AGGREGATE_EVERYTHING, e.g. SELECT count(*) ... with paging off) gets cqlLimits(NO_LIMIT) and handlePagingOff turns the page into NO_LIMIT. So the whole scanned partition or range comes back as one response, a path that skips the limit. Read-size thresholds are off by default. The only stops are the 5 s read_request_timeout and the array cap of about 2 GiB. A large client page size is not limited either, since the page_size guardrail is off by default. Size at defaults: stage 4 measured 411 MB of response in a 514 MB heap array for 100k x 4 KiB rows. This grows linearly to about 2 GiB per query, times up to concurrent_reads = 32 queries at once.

**Where:** src/java/org/apache/cassandra/cql3/statements/SelectStatement.java:890-920; service/pager/AggregationQueryPager.java:193-198,425-442; db/ReadResponse.java:197-203; io/util/DataOutputBuffer.java:118,158-171

## OC-465

**Case file:** `batch_size_fail_threshold-verifyBatchSize-mutations--autonomous` · **Agent:** guided · **Patterns:** CP-1, CP-11

Holder: the coordinator heap during BatchStatement.execute. getMutations builds every IMutation of the batch (PartitionUpdate BTrees, Row and Cell objects, ByteBuffer slices that keep the request frame alive) before verifyBatchSize runs. The fail threshold compares IMutation.dataSize, which counts cell data and leaves out object overhead. Single-partition, conditional and virtual-table batches are never checked. Why nothing stops it: the check runs after the allocation. The native-transport in-flight limiter charges on-wire bytes, while a batch of many tiny or empty-valued cells (up to 65535 statements, each with many columns) decodes to about 10-25x its wire size: about 4 B on the wire against about 100 B on heap per cell. Size at defaults: one request is capped at 16 MiB on the wire, which gives roughly 160-400 MiB of mutation objects. The global reserve heap/10 (about 819 MiB at an 8 GiB heap) admits about 51 such requests from 4 or more IPs, which puts several GiB of transient heap above what was counted.

**Where:** src/java/org/apache/cassandra/cql3/statements/BatchStatement.java:428-439 (getMutations before verifyBatchSize), :270-324, :334-338; transport/messages/BatchMessage.java:59; config/DatabaseDescriptor.java:651

## OC-466

**Case file:** `bloom_filter_fp_chance-computeBloomSpec-maxFalsePosProb--autonomous` · **Agent:** guided · **Patterns:** CP-9, CP-7, CP-15

Same mechanism in both bloom_filter_fp_chance stems (computeBloomSpec and getFilter); file it once and name both stems. Holder: one OffHeapBitSet per SSTable, allocated whole with JNA Native.malloc. The allocation is outside -Xmx and outside MaxDirectMemorySize, and NMT cannot see it. Why nothing stops it: bloom_filter_fp_chance sets bits per key only. Nothing caps the sum over SSTables or partitions, and no node-level native budget exists. A key present in k overlapping SSTables (STCS) is charged k times. During compaction the input and output filters exist together until the inputs are released. A failed malloc is the only enforcement and becomes a RuntimeException ('Out of native memory'). Size at defaults: fp 0.01 gives 10 bits, about 1.25 B per partition per SSTable holding it. 1e9 partitions is about 1.25 GB, and 1e10 small partitions on a dense node is about 12.5 GB, plus up to about 2x transiently during a major compaction. This is native memory that a container sized for the heap does not reserve.

**Where:** src/java/org/apache/cassandra/utils/FilterFactory.java:70-75; utils/obs/OffHeapBitSet.java:42-53; io/sstable/format/SortedTableWriter.java:445; utils/BloomCalculations.java:146-155

## OC-467

**Case file:** `bloom_filter_fp_chance-getFilter-maxFalsePosProbability--autonomous` · **Agent:** guided · **Patterns:** CP-9, CP-7, CP-15

SAME MECHANISM as the candidate under bloom_filter_fp_chance-computeBloomSpec-maxFalsePosProb--autonomous. File it once, naming both stems; do not add a second row. Holder: one malloc'ed OffHeapBitSet per SSTable, outside every JVM limit. It is about 1.25 B per partition per SSTable at fp 0.01 (getFilter returns no filter only at fp 1.0). The total over SSTables and partitions is uncapped, and input and output filters coexist during compaction.

**Where:** src/java/org/apache/cassandra/utils/FilterFactory.java:60-75; utils/obs/OffHeapBitSet.java:42-53

## OC-468

**Case file:** `bloom_filter_fp_chance-validate-bloomFilterFpChance--autonomous` · **Agent:** autonomous · **Patterns:** —

Holder: the off-heap bloom-filter bitsets of all live SSTables. Each one is a native Memory.allocate of ceil((keys x bitsPerKey + 20)/64) x 8 bytes. The check at TableParams:161 only bounds bits per key (at most 20). Nothing bounds the total: there is no node-wide budget, these bytes are not charged to memtable_offheap_space or any other pool, and the only hard stop is the per-filter guard of 16 GB (wordCount > Integer.MAX_VALUE). Compaction makes it worse. Its writer sizes the new filter from the summed HLL cardinality of all inputs (getApproximateKeyCount) and allocates it in full up front while the input SSTables' filters stay live, so a large compaction briefly holds about twice the filter memory of its inputs. Rough size at defaults (STCS, fp 0.01, 10 bits/key): about 1.25 B per partition per SSTable that holds it. 1e9 partitions on a node take about 1.25 GB native, plus up to about 1.25 GB more while a major compaction runs. At fp 0.0001 (20 bits/key) the figures double. This native memory sits outside -Xmx and MaxDirectMemorySize accounting, so it can exhaust RAM.

**Where:** utils/FilterFactory.java:60-75; utils/obs/OffHeapBitSet.java:39-53; io/sstable/format/SortedTableWriter.java:445; db/compaction/writers/CompactionAwareWriter.java:84,235; utils/BloomCalculations.java:140-189

## OC-469

**Case file:** `cached_rows_fail_threshold-queryProtectedPartitions-i--autonomous` · **Agent:** autonomous · **Patterns:** —

Holder: the coordinator heap in RFP PartitionBuilder.contents/staticRow (ArrayDeque<Unfiltered>), plus the full Message<ReadResponse> payloads of every replica. Why it is not stopped: cached_rows_fail_threshold counts rows (each row version per replica, null versions included), not bytes. The count is per query and is released per partition. The raw replica responses are not counted at all. Many queries can do this at once, up to native_transport_max_threads = 128 coordinator threads. Rough size at defaults: 32,000 rows x row size per query. Rows can be up to max_mutation_size (16 MiB). With 4 KiB rows that is about 128 MiB of cached rows per query plus the replica payloads (stage 4 measured 53 MB of raw responses outside the cap). With tens of concurrent ALLOW FILTERING/index queries at CL > ONE against divergent replicas, this reaches several GiB of heap.

**Where:** service/reads/ReplicaFilteringProtection.java:319-332, 477-492; config/ReplicaFilteringProtectionOptions.java:24-27; service/reads/DataResolver.java:252-258; config/Config.java:283

## OC-470

**Case file:** `cached_rows_fail_threshold-queryProtectedPartitions-i--autonomous` · **Agent:** autonomous · **Patterns:** —

Holder: the second-phase completion fetch (fetchFromSource). When a static-column predicate leaves the static row unresolved, it reads the entire partition from the silent replica with DataLimits.NONE and the command's full clustering filter. handler.awaitResults() then holds that whole response as one materialized payload on the coordinator. The rows fetched are never passed to incrementCachedRows, so cached_rows_fail_threshold does not see them. A remote response is cut off only by internode_max_message_size (128 MiB at defaults), and the replica has already built it in a heap DataOutputBuffer. A local source has no size limit at all. Rough size: one whole partition per protected partition per query (partition size is only warned about), e.g. 100 MiB to 1 GiB for a wide partition, about twice that while the buffer grows, multiplied by concurrent queries.

**Where:** service/reads/ReplicaFilteringProtection.java:162-184, 604-650 (623 unresolvedStatic, 630 DataLimits.NONE); db/ReadResponse.java:193-204

## OC-471

**Case file:** `compressed_read_ahead_buffer_size-applySimpleConfig-compressed_read_ahead_buffer_size--autonomous` · **Agent:** autonomous · **Patterns:** —

Holder: the direct ByteBuffers of the read-ahead buffers, one per (thread, data file), stored in the static FastThreadLocal<Map<path, Block>>. Why it is not stopped: the setting fixes only the size of each buffer. There is no pool, counter or aggregate cap. Each SSTableScanner allocates its buffer in its constructor and keeps it until close. A partition-range read opens a scanner for every intersecting SSTable at once (PartitionRangeReadCommand:331-341), and a compaction opens all k input scanners together. Rough size at defaults (256 KiB, LZ4, disk_access_mode mmap_index_only, file cache off): STCS with 500 SSTables gives 500 x 256 KiB = 125 MiB per range read. With concurrent_reads = 32 that is about 4 GiB direct, plus concurrent compactions (k x 256 KiB each). This can exceed MaxDirectMemorySize (a quarter of RAM under bin/cassandra) and throw an OutOfMemoryError for direct buffer memory.

**Where:** io/util/ThreadLocalReadAheadBuffer.java:41-48, 79-93; io/util/CompressedChunkReader.java:232-247; db/PartitionRangeReadCommand.java:315-341; config/Config.java:179

## OC-472

**Case file:** `compressed_read_ahead_buffer_size-applySimpleConfig-compressed_read_ahead_buffer_size--autonomous` · **Agent:** autonomous · **Patterns:** —

Holder: the per-thread HashMap<String, Block> inside ThreadLocalReadAheadBuffer.blockMap. Why it is not stopped: block() calls computeIfAbsent, which adds an entry keyed by the data-file path the first time a thread scans a file. On release (releaseUnderlyingResources -> deallocateResources -> clear(true)) only the buffer is freed; the map entry stays. The entry is removed only in close(), and close() runs on whichever thread drops the FileHandle, removing from that thread's map only. So the long-lived compaction and ReadStage threads keep one Block plus a path String for every SSTable file they have ever scanned, including files deleted long ago. Rough size: about 300 B per (thread, file). A node that compacts about 100 SSTables an hour leaves about 0.9M entries per compaction thread per year, roughly 250 MB of heap per thread, multiplied by concurrent_compactors and the range-reading threads. It grows without bound until the threads exit.

**Where:** io/util/ThreadLocalReadAheadBuffer.java:90-93, 132-156; io/util/CompressedChunkReader.java:207-222, 248-253, 310-318; io/util/BufferManagingRebufferer.java:50-61

## OC-473

**Case file:** `compressed_read_ahead_buffer_size-setCompressedReadAheadBufferSizeInKb-sizeInKb--autonomous` · **Agent:** autonomous · **Patterns:** —

Holder: the direct read-ahead ByteBuffers, one per (thread, data file) for every open SSTable scanner. Why it is not stopped: the JMX setter enforces only a floor (256 KiB). Its ceiling is about 2 GiB per buffer (Integer.MAX_VALUE - 1 bytes). No aggregate limit exists. A range read opens a scanner, and so a buffer, for every intersecting SSTable at once, and a compaction holds k input scanners. Rough size at the default 256 KiB: 32 concurrent range reads x 500 STCS SSTables x 256 KiB = about 4 GiB direct, plus compactions at k x 256 KiB. After a runtime set to 16 MiB, one 32-SSTable compaction alone holds 512 MiB. Either can exceed MaxDirectMemorySize.

**Where:** config/DatabaseDescriptor.java:2554-2560; io/util/CompressedChunkReader.java:232-247; io/util/ThreadLocalReadAheadBuffer.java:41-48, 79-93; db/PartitionRangeReadCommand.java:315-341

## OC-474

**Case file:** `compressed_read_ahead_buffer_size-setCompressedReadAheadBufferSizeInKb-sizeInKb--autonomous` · **Agent:** autonomous · **Patterns:** —

Holder: the per-thread blockMap entries (Block plus path String). The entry is created by computeIfAbsent, the release path clear(true) frees only the buffer, and remove() runs only in close(), on the thread that closes the FileHandle. So scanning threads keep a stale entry for every SSTable they have ever scanned. Rough size: about 300 B per (thread, file). It grows without bound on long-lived compaction and ReadStage threads, e.g. about 250 MB per compaction thread for about 0.9M files scanned per year.

**Where:** io/util/ThreadLocalReadAheadBuffer.java:90-93, 132-156; io/util/CompressedChunkReader.java:207-222, 248-253, 310-318

## OC-475

**Case file:** `coordinator_read_size_fail_threshold-validateReadThresholds-fail--autonomous` · **Agent:** autonomous · **Patterns:** —

Holder: the replica-side heap DataOutputBuffer into which LocalDataResponse.build serializes a whole read page, plus the value arrays read off the SSTables. Why it is not stopped: at shipped defaults read_thresholds_enabled is false and every *_read_size_fail_threshold is null, so neither the local nor the coordinator size check runs. Pages are limited by row count (driver page size, e.g. 5000), not bytes. The 128 MiB internode_max_message_size is applied only when the finished response is sent, so a remote replica still builds the full buffer, and a local read has no limit at all. The buffer's capacity reaches up to 2 x len + 64 KiB. Rough size: 5000 rows x 64 KiB = about 320 MB serialized, up to about 640 MB of buffer, plus about 320 MB of values, per read. Multiplied by concurrent_reads = 32 ReadStage threads, that is tens of GB of heap. Even with only the coordinator threshold set, this buffer stays page-sized (stage 4: 8.4 / 33.6 MB pages under a 1 MiB coordinator cap).

**Where:** config/Config.java:526-532; service/StorageProxy.java:2207-2212; db/ReadCommandVerbHandler.java:95,109; db/ReadResponse.java:193-204; io/util/DataOutputBuffer.java:158-183; config/Config.java:179

## OC-476

**Case file:** `coordinator_read_size_fail_threshold-validateReadThresholds-fail--autonomous` · **Agent:** autonomous · **Patterns:** —

Holder: the coordinator's ResultSetBuilder plus the replica responses (data and digest/merge) for one page, then the encoded result message. Why it is not stopped: maybeFail/maybeWarn are no-ops unless read_thresholds_enabled (default false). Each page builds a fresh ResultSetBuilder that holds every selected value. native_transport_max_request_data_in_flight limits request bytes, not responses. Rough size: a page of P rows x row bytes (e.g. 5000 x 64 KiB = about 320 MB). It is held about two to three times (replica responses, result set, encoded message), per in-flight query, for up to 128 native-transport threads.

**Where:** cql3/statements/SelectStatement.java:1000-1008, 1057-1092; cql3/selection/ResultSetBuilder.java:76-98; cql3/QueryOptions.java:276-281

## OC-477

**Case file:** `denylist_max_keys_per_table-setDenylistMaxKeysPerTable-value--autonomous` · **Agent:** autonomous · **Patterns:** —

Holder: the partition-denylist Caffeine LoadingCache<TableId, DenylistEntry>, which holds ImmutableSet<ByteBuffer> keys plus a sorted set of tokens. Why it is not stopped: denylist_max_keys_total (10,000) is applied only in the full load (getDenylistForAllTablesFromCQL). The on-demand cache load/reload (refreshAfterWrite) and the refresh after each JMX denylistKey both call getDenylistForTableFromCQL(tid), which uses the per-table limit only, and the cache has no maximumSize. So the total held is perTable x the number of denylisted tables, bypassing the total cap. Each refresh also materializes an unpaged LIMIT perTable+1 result. Rough size, with partition_denylist_enabled set (default false): 1000 keys x up to 64 KiB = about 64 MiB per table. 100 denylisted tables give about 6.4 GiB, against the about 640 MiB that the 10,000-key total is meant to allow.

**Where:** schema/PartitionDenylist.java:181-213, 386-391, 396-455, 494-498, 515-528; config/Config.java:759, 774-780

## OC-478

**Case file:** `bloom_filter_fp_chance-validate-bloomFilterFpChance--autonomous` · **Agent:** guided · **Patterns:** CP-9, CP-15, CP-7, CP-8

Holder: one OffHeapBitSet per live sstable (bloom filter), allocated with Native.malloc through Memory.allocate, so it sits outside both -Xmx and MaxDirectMemorySize. Why nothing stops it: the fp check only bounds bits per key (at most 20). No limit sums filters over sstables or keys. The only stop is a per-filter guard at 16 GB, and the OOM catch just rethrows a RuntimeException. Compaction makes it worse: the output filter is sized up front from the inputs' HLL estimate (it falls back to summing per-sstable counts when Statistics.db cannot be read), while the input filters stay loaded until the swap, so filter memory for the compacted keys doubles for a while. Size at defaults (fp 0.01, 10 bits = 1.25 B per key; LCS 0.1, 0.625 B): 1e9 partitions per node gives about 1.25 GB of native memory, and about 2.5 GB during a major compaction. Only the container or the kernel bounds it, and cassandra-env.sh leaves no room for it.

**Where:** systems/cassandra/source/src/java/org/apache/cassandra/utils/obs/OffHeapBitSet.java:39-53; utils/FilterFactory.java:70-75; utils/memory/MemoryUtil.java:81-84; io/sstable/format/SortedTableWriter.java:445; db/compaction/writers/CompactionAwareWriter.java:84; io/sstable/format/SSTableReader.java:302-347

## OC-479

**Case file:** `cached_rows_fail_threshold-queryProtectedPartitions-i--autonomous` · **Agent:** guided · **Patterns:** CP-2, CP-7, CP-1

Holder: the coordinator's ReplicaFilteringProtection PartitionBuilder.contents (ArrayDeque of rows), plus the raw replica responses. Why nothing stops it: cached_rows_fail_threshold counts row versions (null versions included), not bytes, and applies per query. One RFP is built per filtering or index read at CL above ONE, and nothing caps the sum across the 128 native-transport request threads. The raw Message<ReadResponse> payloads are outside the count. Size at defaults: T = 32,000 versions gives 16,000 held rows at RF 2. At 2 KiB rows that is about 32 MiB held plus a similar amount of raw responses, so about 64 MiB per query. 128 concurrent queries reach about 8 GiB, more than an 8 GiB heap minus its memtable quarter.

**Where:** systems/cassandra/source/src/java/org/apache/cassandra/service/reads/ReplicaFilteringProtection.java:316-332, :477-492; service/reads/DataResolver.java:122-144, :252-258

## OC-480

**Case file:** `cached_rows_fail_threshold-queryProtectedPartitions-i--autonomous` · **Agent:** guided · **Patterns:** CP-10, CP-12

Holder: the second-phase protection fetch, fetchFromSource. When a static-column predicate is unresolved, it reads the entire partition from the silent replica with DataLimits.NONE and RowFilter.none(), outside the cached-rows count. Why nothing stops it: there is no row limit and no paging. The response is materialized whole on the coordinator heap, and only internode_max_message_size (about 128 MiB at defaults) bounds it. Size: up to about 128 MiB per fetch for a wide partition, times concurrent filtering queries and protected partitions.

**Where:** systems/cassandra/source/src/java/org/apache/cassandra/service/reads/ReplicaFilteringProtection.java:603-631

## OC-481

**Case file:** `commitlog_segment_size-applySimpleConfig-commitlog_segment_size--autonomous` · **Agent:** guided · **Patterns:** CP-13, CP-10

Holder: the CompressedSegmenter's heap uncompressedBuffer during commit-log replay (startup) with commitlog_compression on. Why nothing stops it: uncompressedLength is read from the section body with reader.readInt(). The sync-marker CRC covers only id, position and end, not this field. The field sizes new byte[(int)(1.2 * uncompressedLength)] before decompression and with no check against commitlog_segment_size. A torn or corrupt section after a crash can therefore ask for up to about 2 GiB (the cast saturates at Integer.MAX_VALUE) and fail startup with Java heap space instead of a CommitLogReadException. Size: legitimately at most 1.2 × the 32 MiB segment, about 38 MiB; corrupt, up to 2 GiB on a default heap of up to 8 GiB.

**Where:** systems/cassandra/source/src/java/org/apache/cassandra/db/commitlog/CommitLogSegmentReader.java:318-329 (marker CRC only at :174-181)

## OC-482

**Case file:** `compressed_read_ahead_buffer_size-applySimpleConfig-compressed_read_ahead_buffer_size--autonomous` · **Agent:** guided · **Patterns:** CP-7, CP-6, CP-16, CP-14

Holder: one direct ByteBuffer of compressed_read_ahead_buffer_size per (thread, sstable file) in the static FastThreadLocal blockMap. It is allocated in each scanner's constructor for every compressed sstable a range read or compaction opens, and held until the scan closes. Why nothing stops it: it is not drawn from BufferPool and no counter or aggregate cap exists. A range read opens a scanner for every intersecting sstable (all of them under STCS/TWCS), and a compaction holds all of its inputs open. Only MaxDirectMemorySize (a quarter of RAM under bin/cassandra) stops it, as an OutOfMemoryError: Direct buffer memory. The size has no upper sanity bound beyond about 2 GiB (startup checks only > 0 && < 256 KiB). Release looks up the closing thread's map, so a scanner closed on another thread would leave its buffer. Size at defaults (256 KiB): a TWCS table with 1,000 sstables costs about 250 MiB per range-read thread; 32 ReadStage threads plus compactors reach about 8 GiB of direct memory. At 16 MiB, one 32-sstable compaction is 512 MiB (stage 4).

**Where:** systems/cassandra/source/src/java/org/apache/cassandra/io/util/ThreadLocalReadAheadBuffer.java:41-47, :79-91, :132-150; io/util/CompressedChunkReader.java:236-238; db/PartitionRangeReadCommand.java:331-345

## OC-483

**Case file:** `compressed_read_ahead_buffer_size-setCompressedReadAheadBufferSizeInKb-sizeInKb--autonomous` · **Agent:** guided · **Patterns:** CP-16, CP-7, CP-6

This is the same mechanism as the applySimpleConfig stem: direct read-ahead buffers per (thread, sstable) with no aggregate cap, bounded only by MaxDirectMemorySize. What this stem adds: the JMX setter checks only < 256 KiB, so at runtime any value up to about 2 GiB per buffer is accepted with no check against the direct-memory budget, and lowering it does not shrink buffers of readers already built. Size: a set to 64 MiB × 32 sstables in one compaction is 2 GiB direct; × 4 compactors plus range reads exceeds a quarter of RAM on a 32 GiB host.

**Where:** systems/cassandra/source/src/java/org/apache/cassandra/config/DatabaseDescriptor.java:2554-2560; io/util/CompressedChunkReader.java:236-238; io/util/ThreadLocalReadAheadBuffer.java:79-91

## OC-484

**Case file:** `coordinator_read_size_fail_threshold-validateReadThresholds-fail--autonomous` · **Agent:** guided · **Patterns:** CP-1, CP-7, CP-8, CP-12, CP-11

Holder: the replica's on-heap DataOutputBuffer page (LocalDataResponse.build serializes the whole page, and capacity grows up to about 2 × len), plus the coordinator's ResultSet and the encoded client response. Why nothing stops it: all read-size thresholds ship null and read_thresholds_enabled is false. When enabled, the coordinator threshold counts value bytes only after the replica has already built and sent the full page (stage 4: a 1 MiB coordinator cap still let 8.39 / 33.56 MB replica pages be built). Each threshold applies per page or command, with no total across the 128 request threads and 32 ReadStage threads. Size: a 5,000-row page of 8 KiB rows is about 40 MB serialized, about 80 MB buffer capacity, plus deserialized rows. 32 concurrent reads reach about 2.5 to 4 GiB of heap. This is related to the known C2 shape for direct memory.

**Where:** systems/cassandra/source/src/java/org/apache/cassandra/db/ReadResponse.java:193-204; cql3/statements/SelectStatement.java:1057-1083, :1004; config/Config.java:526-532; cql3/QueryOptions.java:276-281

## OC-485

**Case file:** `counter_cache_size-applySimpleConfig-counterCacheSizeInMiB--autonomous` · **Agent:** guided · **Patterns:** CP-1

Holder: the Caffeine counter cache. Why nothing stops it: the weigher charges only CounterCacheKey.unsharedHeapSize() + ClockAndCount.unsharedHeapSize(), while each entry also holds a Caffeine node (about 40 B), a ConcurrentHashMap node (32 B), a table slot and a sketch slot (about 90 B uncounted). A full cache therefore holds about 1.8 × counter_cache_size for small cells. Size at defaults: cap min(2.5% of heap, 50 MiB), real about 90 MiB. Bounded overshoot, shared with the key cache's same shape (which counter_cache_size-setCounterCacheCapacityInMB also shows).

**Where:** systems/cassandra/source/src/java/org/apache/cassandra/cache/CaffeineCache.java:61-69; cache/CounterCacheKey.java:152-157; db/ClockAndCount.java:46-49

## OC-486

**Case file:** `counter_cache_size-setCounterCacheCapacityInMB-capacity--autonomous` · **Agent:** guided · **Patterns:** CP-16, CP-14, CP-1

This is the same weigher mechanism as the applySimpleConfig stem (about 90 B per entry not counted, about 1.8 × C real heap). What this stem adds: the JMX setter rejects only capacity < 0, with no upper bound and no comparison with the heap, so a raised C carries the same 1.8 multiple. After a runtime shrink, policy.setMaximum drops the weight at once but Caffeine's hash table and frequency sketch stay sized for the largest population reached. Size: a counter cache raised to 1 GiB holds about 1.8 GiB; after shrinking back, several MiB to tens of MB of table and sketch are retained (the key cache measured +17.3 MB after 64 → 16 MiB).

**Where:** systems/cassandra/source/src/java/org/apache/cassandra/service/CacheService.java:344-350; cache/CaffeineCache.java:77-80, :61-69

## OC-487

**Case file:** `denylist_max_keys_per_table-setDenylistMaxKeysPerTable-value--autonomous` · **Agent:** guided · **Patterns:** CP-10, CP-7, CP-16, CP-12

Holder: the PartitionDenylist Caffeine LoadingCache (TableId → DenylistEntry of key ByteBuffers and tokens). It has no maximumSize, and each per-table load runs an unpaged SELECT ... LIMIT P+1 that is held serialized and deserialized during the read. Why nothing stops it: denylist_max_keys_total (10,000) is applied only in the full load. Cache-miss load, the timed refresh (every 600 s) and the JMX add/remove refresh use only the per-table limit, so tables cut to empty at load are refilled to P. The JMX setter checks only value <= 0, with no upper bound. Size: off by default and operator-driven. At P = 1000 with keys up to 64 KiB, it is about 64 MiB per table × denylisted tables (not 640 MiB total). A raised P (for example 100,000) makes each refresh materialize an unpaged result of up to P × key size (GBs), and the old entry is kept during the reload.

**Where:** systems/cassandra/source/src/java/org/apache/cassandra/schema/PartitionDenylist.java:184-213, :397-412, :485-499; config/DatabaseDescriptor.java:4813-4818

## OC-488

**Case file:** `denylist_max_keys_total-getDenylistForAllTablesFromCQL-totalProcessed--autonomous` · **Agent:** autonomous · **Patterns:** —

The per-table reload paths ignore the total cap, so the cache grows to (tables with denylist rows) x denylist_max_keys_per_table. Holder: the Caffeine LoadingCache<TableId, DenylistEntry>, which has no maximumSize or weight; each entry is an ImmutableSet<ByteBuffer> of raw keys plus the token set. Three paths reload one table using only the per-table limit (1000 by default) and never look at totalProcessed: the cache-miss load, the refreshAfterWrite reload (every 600 s, on access), and the JMX denylistKey/removeDenylistKey refresh. The JMX path also runs while partition_denylist_enabled=false. Nothing counts total keys or bytes outside a full load(). Rough size: a partition key can be up to 64 KiB, so one table can hold 1000 x 64 KiB = ~64 MiB. With 50 tables that is ~3.2 GiB, against the ~640 MiB the 10000-key total implies. Stage 4 saw 31 MiB grow to 125-158 MiB after refresh with 32 KiB keys.

**Where:** src/java/org/apache/cassandra/schema/PartitionDenylist.java:183-212 (cache-miss load at 190, reload at 201), :388-391 (per-table limit only), :515-527 (refreshTableDenylist put), :448; StorageProxy.java:3129-3139 (denylistKey does not check the enabled flag)

## OC-489

**Case file:** `denylist_max_keys_total-getDenylistForAllTablesFromCQL-totalProcessed--autonomous` · **Agent:** autonomous · **Patterns:** —

The cap counts keys, not bytes. The total cap is applied as a count against totalProcessed, and partition keys can be up to 64 KiB. So even a fully capped load at defaults may hold 10000 x 64 KiB = ~640 MiB of on-heap ByteBuffers, plus the token set. During a load() the old cache stays live until the swap (:224-232), so this can briefly double to ~1.3 GiB. No byte budget exists anywhere on this path.

**Where:** src/java/org/apache/cassandra/schema/PartitionDenylist.java:484-500, :219-232; Config.java:780

## OC-490

**Case file:** `denylist_max_keys_total-setDenylistMaxKeysTotal-value--autonomous` · **Agent:** autonomous · **Patterns:** —

The total set through setDenylistMaxKeysTotal applies only at the next full load(). Holder: the Caffeine denylist cache, which has no size or weight bound. The cache-miss load, the timer reload and the JMX add/remove refresh all reload one table with only denylist_max_keys_per_table (1000) and never consult the total. So after refresh, heap is the sum over tables of min(1000, rows) x key size, whatever the total is set to. Keys can be up to 64 KiB, so this is ~64 MiB per denylisted table: 20 tables is ~1.3 GiB, 100 tables ~6.4 GiB. The JMX denylistKey path works even with partition_denylist_enabled=false.

**Where:** src/java/org/apache/cassandra/schema/PartitionDenylist.java:190-197, :201-211, :388-391, :515-527; StorageProxy.java:3129-3139

## OC-491

**Case file:** `denylist_max_keys_total-setDenylistMaxKeysTotal-value--autonomous` · **Agent:** autonomous · **Patterns:** —

The constraint is a key count with no byte bound. The setter only rejects values <= 0 and has no upper bound. At the default 10000 keys of up to 64 KiB, the cache can hold ~640 MiB of heap after a correct full load, and up to twice that while load() builds the new cache before the old one is collected.

**Where:** src/java/org/apache/cassandra/config/DatabaseDescriptor.java:4825-4830; src/java/org/apache/cassandra/schema/PartitionDenylist.java:219-232, :484-500

## OC-492

**Case file:** `file_cache_size-allocateMoreChunks-memoryUsageThreshold--autonomous` · **Agent:** autonomous · **Patterns:** —

Overflow allocations past the pool threshold have no limit. When allocateMoreChunks refuses a slab (at file_cache_size, default min(512 MiB, heap/4)), and for every request over 128 KiB, LocalPool.get falls back to ByteBuffer.allocateDirect(size). Only the overflowMemoryUsage counter tracks these, and nothing checks it. buffer_pool_use_heap_if_exhausted is declared but never read. At defaults (file_cache_enabled=false, disk_access_mode=mmap_index_only), every data-file reader holds one BufferManagingRebufferer buffer from this pool (chunk size, 16 KiB compressed by default, up to 64 KiB). Once 512 MiB of slabs are taken, further concurrent readers (compactions, reads touching many SSTables) each add an unpooled direct buffer. The only stop is -XX:MaxDirectMemorySize, which is unset in jvm-server.options and so defaults to -Xmx; past it the JVM throws OutOfMemoryError: Direct buffer memory. Rough size: 512 MiB pooled plus open readers x 16-64 KiB of overflow. Stage 4 measured up to 41 MB of overflow under a moderate load.

**Where:** src/java/org/apache/cassandra/utils/memory/BufferPool.java:233-239, :908-924, :938-942, :443-450; io/util/BufferManagingRebufferer.java:45; config/Config.java:122, :499, :514; conf/jvm-server.options:174

## OC-493

**Case file:** `hints_buffer_size-allocateBytes-prev--autonomous` · **Agent:** autonomous · **Patterns:** —

Hints waiting behind a full buffer pool are limited by count, not bytes. HintsBufferPool blocks the writing thread in reserveBuffers.take() once 3 slabs (3 x 32 MiB) are full and not yet flushed. Hint tasks are queued on the MUTATION stage, whose queue is unbounded, and each HintRunnable holds the whole Mutation until it is serialized. The only back-pressure is checkHintOverload: a count of 128 x cores hints in progress, which applies only to destinations that already have hints in progress, is checked before the increment, and is not checked at all on the AbstractWriteResponseHandler and PaxosCommit hint submissions. Rough size: 128 x 8 cores = 1024 queued hints x mutation size, up to max_mutation_size 16 MiB by default. That is ~1 GiB at 1 MiB mutations and up to ~16 GiB at the maximum.

**Where:** src/java/org/apache/cassandra/hints/HintsBufferPool.java:108-120 (take at 118); src/java/org/apache/cassandra/service/StorageProxy.java:202, :1585-1598, :2786-2827 (Stage.MUTATION.submit at 2827); AbstractWriteResponseHandler.java:310; DatabaseDescriptor.java:898-899

## OC-494

**Case file:** `indexing_target_page_size-calculateIndexingPageSize-meanPartitionSize--autonomous` · **Agent:** autonomous · **Patterns:** —

Index build pages have no byte bound in two cases. calculateIndexingPageSize returns a flat 10000 rows with no byte bound for any table with zero regular columns (:1164), and otherwise sizes the page from the table-wide mean row size, so skewed data defeats the 32 MiB target. A table whose mean row is small (many 100 B rows) but which also has partitions of large rows gets pageSize = 10000. indexPartition then materializes each page into an ImmutableBTreePartition on the heap. Rough size: 10000 rows x 100 KiB = ~1 GiB per page, per concurrent build (CREATE INDEX or nodetool rebuild_index). Stage 4 measured ~400 MB per page with 40 KB rows and zero regular columns, against 35 MB on the capped path.

**Where:** src/java/org/apache/cassandra/index/SecondaryIndexManager.java:1149-1170 (:1164 fallback, :1167-1170 mean-based size), :1053-1066; db/ColumnFamilyStore.java:3110-3134

## OC-495

**Case file:** `indexing_target_page_size-calculateIndexingPageSize-meanPartitionSize--autonomous` · **Agent:** autonomous · **Patterns:** —

The BIG-format row index for a wide partition is held on the heap while it is written. BigFormatPartitionWriter keeps every IndexInfo (first and last clustering per 64 KiB block) of the partition being written, first as a list and then in a DataOutputBuffer that grows by doubling. Nothing bounds its size; column_index_cache_size only picks the representation. With large clustering keys the index is about as large as the partition (2 keys per block). Rough size: a 480 MB partition with 40 KB clustering keys needs ~0.5-1 GB of buffer during compaction or flush. Stage 4's defect D1 was exactly this: a node with a 2 GiB heap died of OOM when compaction rewrote those partitions.

**Where:** src/java/org/apache/cassandra/io/sstable/format/big/BigFormatPartitionWriter.java:49, :56, :140-188; io/util/DataOutputBuffer.java:169

## OC-496

**Case file:** `index_summary_capacity-applySimpleConfig-indexSummaryCapacityInMiB--autonomous` · **Agent:** autonomous · **Patterns:** —

Index-summary memory is bounded only softly. The memory is native (malloc'd SafeMemory), so neither the heap limit nor MaxDirectMemorySize covers it, and the pool caps only the counted getOffHeapSize, and only at each hourly redistribution. Between runs, every newly flushed or compacted SSTable gets a full-resolution summary (min_index_interval 128). Redistribution never goes below the max_index_interval floor and is skipped while compaction is paused. A summary rebuilt by upsampling keeps the builder's untrimmed buffer, sized for 64-byte keys and grown by doubling: 1.73x the counted size in stage 4. Rough size at defaults: pool = 5% of heap (e.g. 410 MiB at 8 GiB). A compaction that writes 1e9 partitions of 32 B keys adds a full summary of 1e9/128 x 44 B = ~344 MB before the next redistribution, and upsampled summaries add ~0.7 x the pool uncounted.

**Where:** src/java/org/apache/cassandra/io/sstable/indexsummary/IndexSummaryRedistribution.java:138-145, :224-229; IndexSummaryManager.java:103-109, :193-199, :241-242; io/sstable/format/big/BigTableReader.java:625-640; io/sstable/indexsummary/IndexSummaryBuilder.java:100-128

## OC-497

**Case file:** `items_per_collection-doAdd-elements_size--autonomous` · **Agent:** autonomous · **Patterns:** —

Nothing bounds the size of a stored non-frozen collection, and reads materialize the whole collection on the heap. items_per_collection and collection_size are disabled by default (-1/null). Even when enabled they count only the fragment being written, and superusers and AllowAllAuthenticator, the default, are exempt. The flush-time check only logs. Repeated `s = s + {...}` appends therefore grow one row's set without limit. A SELECT, or a compaction, of that row deserializes every cell into one Row, because paging is by rows, not cells. Read size thresholds are off by default. Rough size: ~150 B of heap per item (stage 4: 1.53 GB held for one SELECT of a 10^7-item set) against ~4 B per item on disk. A few concurrent reads of such a row exhaust a default heap.

**Where:** src/java/org/apache/cassandra/cql3/Sets.java:393-410; db/rows/UnfilteredSerializer.java:619, :662-687; config/Config.java:526-530, :917-920; io/sstable/format/SortedTableWriter.java:393-428; service/ClientState.java:602-605

## OC-498

**Case file:** `denylist_max_keys_total-getDenylistForAllTablesFromCQL-totalProcessed--autonomous` · **Agent:** guided · **Patterns:** CP-2, CP-10, CP-7, CP-1

Holder: the partition-denylist Caffeine cache (PartitionDenylist cache of TableId -> DenylistEntry, an ImmutableSet<ByteBuffer> of keys plus an ImmutableSortedSet<Token>). Why nothing stops it: (1) the total cap counts keys, not bytes (totalProcessed += keys.size()), and each key is a blob clustering value of up to ~64 KiB; (2) the total is applied only inside a full load(). The timer refresh (refreshAfterWrite, denylist_refresh 600 s), the cache-miss load and add/remove -> refreshTableDenylist all reload a table with only the per-table limit, so a table that the total had emptied or truncated grows back to denylist_max_keys_per_table (1000). The class javadoc accepts this. After one refresh interval the cache holds sum over denylisted tables of min(1000, rows), and nothing caps the number of tables. Each refresh also builds the new entry while the old one is still live (2x for one table), and a JMX load builds a whole new cache next to the old one. Size at defaults (feature off by default; once partition_denylist_enabled=true with default limits): the total implies up to 10,000 x 64 KiB = about 640 MiB of heap. After refresh: 50 denylisted tables x 1000 x 64 KiB = about 3.2 GiB, which no heap budget accounts for. Stage 4 measured the bypass at 4-5x the total's level. Reachable only through operator-written denylist rows.

**Where:** src/java/org/apache/cassandra/schema/PartitionDenylist.java:484 (total check, full load only); :388-391 (per-table-only overload used by load/reload/refresh); :183-212 (refreshAfterWrite reload and cache-miss load); :436-446 (keys and tokens materialized per entry); :74-83 (javadoc accepting the bypass); src/java/org/apache/cassandra/config/Config.java:774,780 (1000 per table, 10000 total)

## OC-499

**Case file:** `denylist_max_keys_total-setDenylistMaxKeysTotal-value--autonomous` · **Agent:** guided · **Patterns:** CP-2, CP-10, CP-7, CP-1

Same mechanism as denylist_max_keys_total-getDenylistForAllTablesFromCQL-totalProcessed--autonomous; file it once and name both stems. The total cap (10,000 keys, a count not bytes, up to ~64 KiB per key) is applied only during a full load(). The timer refresh after denylist_refresh (600 s), the cache-miss load and add/remove refresh reload each table with only the per-table limit (1000), so heap grows to denylisted tables x 1000 x key size. Example: 50 tables x 1000 x 64 KiB = about 3.2 GiB, against about 640 MiB that the total implies. The JMX setter at the entry point checks only value <= 0 and does not change this.

**Where:** src/java/org/apache/cassandra/config/DatabaseDescriptor.java:4825-4830 (setter, only <= 0 rejected); src/java/org/apache/cassandra/schema/PartitionDenylist.java:484, :388-391, :201-212

## OC-500

**Case file:** `file_cache_size-allocateMoreChunks-memoryUsageThreshold--autonomous` · **Agent:** guided · **Patterns:** CP-6, CP-9, CP-7

Holder: unpooled direct ByteBuffers that BufferPool hands out when it cannot serve a request (overflowMemoryUsage). Why nothing stops it: once memoryAllocated + one 8 MiB macro chunk would pass the threshold, allocateMoreChunks returns null. LocalPool.get then falls back to ByteBuffer.allocateDirect(size) with no cap; overflowMemoryUsage is only a metric. Every request over 128 KiB (NORMAL_CHUNK_SIZE) always takes this path. buffer_pool_use_heap_if_exhausted is declared but referenced nowhere, so the fallback is always off-heap. The OOM catch around the slab allocation logs that it falls back to on-heap, which the code does not do. The only stop is -XX:MaxDirectMemorySize, which cassandra-env.sh sets to RAM/4 (heap/2) with no room reserved for this overflow. Size at defaults: the pools are capped at min(512 MiB, heap/4) for the chunk cache and min(128 MiB, heap/16) for networking. Overflow is one buffer per open reader (chunk cache is off by default in 5.0, so every RandomAccessReader's BufferManagingRebufferer draws a 4-64 KiB chunk from this pool) or per in-flight network or streaming buffer, times concurrent reads, compaction scanners and connections. That is tens to hundreds of MiB under a reachable load, more with large compression chunk lengths or many sstables per read. Stage 4 saw overflow > 0 in every capped sample.

**Where:** src/java/org/apache/cassandra/utils/memory/BufferPool.java:443-450 (refuse slab, return null); :903-924 (LocalPool.get falls back to allocate(size, OFF_HEAP)); :233-238 (allocateDirect, overflow only counted); :938-942 (>128 KiB never pooled); :462-466 (misleading 'on-heap' message); src/java/org/apache/cassandra/config/Config.java:514 (buffer_pool_use_heap_if_exhausted unused); conf/cassandra-env.sh:62-66

## OC-501

**Case file:** `file_cache_size-allocateMoreChunks-memoryUsageThreshold--autonomous` · **Agent:** guided · **Patterns:** CP-8, CP-9, CP-14

Holder: chunk-cache and networking BufferPool slabs (8 MiB macro chunks). The case file cites R1-V for this mechanism, so it may already be filed. Why nothing stops it: each pool stays within its own cap. But the defaults (file_cache_size min(512, heap/4) plus networking_cache_size min(128, heap/16) = 5H/16 at small heaps) share the direct budget with hints buffers, internode reserves and Netty. Under offheap_objects (shipped in cassandra_latest.yaml) the off-heap memtable takes another heap/4 through JNA malloc, outside MaxDirectMemorySize. Slabs are never returned to the OS (macroChunks keeps the high-water mark). Size at defaults: with RAM = 2H and heap H, about 9H/16 beyond the heap, which can exceed a container limit of 2H.

**Where:** src/java/org/apache/cassandra/config/DatabaseDescriptor.java:573-577 (pool defaults); src/java/org/apache/cassandra/utils/memory/BufferPools.java:38-45; src/java/org/apache/cassandra/utils/memory/BufferPool.java:385,468 (slab size, never freed); conf/cassandra-env.sh:62-66

## OC-502

**Case file:** `hints_buffer_size-allocateBytes-prev--autonomous` · **Agent:** guided · **Patterns:** CP-16, CP-8

Weak, depends on configuration. Holder: hints buffer slabs, each a direct ByteBuffer of B = max(2 x max_mutation_size, 32 MiB) bytes, fully allocated at creation however full it is. Up to MAX_HINT_BUFFERS = 3 slabs are created lazily when the flush executor lags behind hint writers. Why nothing stops it: B comes straight from max_mutation_size, which defaults to commitlog_segment_size/2. The only checks are commitlog_segment_size < 2048 MiB and >= 2 x max_mutation_size; slab size is never compared with MaxDirectMemorySize or the other direct pools. Slabs are recycled, never freed, while the service runs. Size: 3 x 32 MiB = 96 MiB at defaults (not a problem). With a raised commitlog_segment_size (256 MiB to allow larger mutations), 3 x 256 MiB = 768 MiB; near the 2 GiB ceiling, up to about 6 GiB of direct memory after a hint burst. That shares the heap/2 direct budget with the chunk-cache and networking pools.

**Where:** src/java/org/apache/cassandra/hints/HintsService.java:110-111 (bufferSize from max_mutation_size); src/java/org/apache/cassandra/hints/HintsBufferPool.java:107-128,130-134 (up to 3 slabs, never freed); src/java/org/apache/cassandra/hints/HintsBuffer.java:75-78 (allocateDirect(slabSize)); src/java/org/apache/cassandra/config/DatabaseDescriptor.java:891-901 (only bounds)

## OC-503

**Case file:** `index_summary_capacity-applySimpleConfig-indexSummaryCapacityInMiB--autonomous` · **Agent:** guided · **Patterns:** CP-1, CP-11, CP-9, CP-14

Holder: BIG-format index summaries in native memory (two JNA malloc blocks per sstable). Why nothing stops it: (1) the pool counts getOffHeapSize() = 4 x entries + entry bytes. A summary rebuilt by upsampling (buildSummaryAtLevel, when redistribution raises a sampling level or the index intervals change) uses a new IndexSummaryBuilder sized for 64-byte keys and never calls prepareToCommit()/trim(). So it keeps about 76 B per entry against 12 + key bytes counted: 1.73x for 32-B keys, about 3x for 12-B keys. (2) The pool is enforced only by a redistribution every index_summary_resize_interval (60 min), skipped while compaction is paused. New and compacted sstables arrive at full resolution in between. (3) Below the pool there is a floor at max_index_interval (1/16 of full), so the overshoot stays when the floor exceeds the pool. No allocation is ever refused, and the memory is outside both -Xmx and MaxDirectMemorySize. Size at defaults: pool = 5% of heap (about 409 MiB at 8 GiB). Real native memory after upsampling is 1.7-3x that (+300 to +800 MiB), plus up to an hour of uncapped new summaries. Stage 4 measured 1.729x.

**Where:** src/java/org/apache/cassandra/io/sstable/format/big/BigTableReader.java:602-604,625-640 (upsample rebuild, no trim); src/java/org/apache/cassandra/io/sstable/indexsummary/IndexSummaryBuilder.java:100-128 (capacity from 64-B expected key), :246-252 (trim only in prepareToCommit); src/java/org/apache/cassandra/io/sstable/indexsummary/IndexSummary.java:259-262 (counted size); src/java/org/apache/cassandra/io/sstable/indexsummary/IndexSummaryManager.java:239-252 (periodic, skipped when compaction paused); src/java/org/apache/cassandra/config/DatabaseDescriptor.java:866-869

## OC-504

**Case file:** `indexing_target_page_size-calculateIndexingPageSize-meanPartitionSize--autonomous` · **Agent:** guided · **Patterns:** CP-12, CP-2, CP-1

Holder: one secondary-index build page, copied whole into an ImmutableBTreePartition on heap before the indexers run. Why nothing stops it: the 32 MiB target is turned into a row count once per build, from table-wide means of serialized size. The pager then bounds only rows (min(pageSize, remaining)); no bytes are checked. (1) For any table with zero regular columns (:1164), and when cassandra.force_default_indexing_page_size is set, the page is a flat 10,000 rows with no byte bound. (2) A partition whose rows are larger than the table mean gets min(10000, 32 MiB / mean) of its large rows. (3) Heap per row exceeds serialized size. The result is the JVM's OutOfMemoryError in the build thread. Size at defaults: on the :1164 path, 10,000 x clustering-key rows of up to 64 KiB = up to about 640 MiB per page (stage 4: 120-400 MB at 40-60 KB rows). With skew, a table of mean ~10 KB rows and one partition of 1 MiB rows gives about 3.3 GB per page. Times concurrent_index_builders = 2.

**Where:** src/java/org/apache/cassandra/index/SecondaryIndexManager.java:1149-1170 (page size from means; 10000-row fallbacks at :1151,:1156,:1160,:1164); :1053-1066 (page materialized as ImmutableBTreePartition); src/java/org/apache/cassandra/service/pager/AbstractQueryPager.java:95-101 (row count only); src/java/org/apache/cassandra/config/Config.java:350 (2 builders)

## OC-505

**Case file:** `items_per_collection-doAdd-elements_size--autonomous` · **Agent:** guided · **Patterns:** CP-12, CP-2, CP-10, CP-8, CP-11

Holder: a non-frozen collection read whole into one Row on heap (every cell of the complex column goes into one Row.Builder) on the replica, and again on the coordinator after deserialization. Why nothing stops it: the items_per_collection guardrail counts only the fragment being written (elements.size() of the statement), not the stored collection, so appends grow a set without limit. It ships off (warn/fail = -1). With the default AllowAllAuthenticator every client is a superuser, and guardrails skip superusers. The flush-time collection check only logs (state == null). The only read-size limits (read_thresholds_enabled, local/coordinator_read_size_*) ship off, and when enabled they check after the row is built (addSize(row.unsharedHeapSize())). Size at defaults: stage 4 measured about 150 B held and about 340 B allocated per item, against 4 B per item on disk. A set<int> of 10^7 items, reached in ~10 default-size appends (max_mutation_size 16 MiB), holds about 1.5 GB per read of that row. Up to concurrent_reads = 32 such reads at once, against a default heap of RAM/2 capped at 31 GiB.

**Where:** src/java/org/apache/cassandra/cql3/Sets.java:396-399 (guard counts only the added fragment); src/java/org/apache/cassandra/config/Config.java:919-920 (-1 = off), :526-530 (read thresholds off); src/java/org/apache/cassandra/service/ClientState.java:602-605 (no auth -> superuser, exempt); src/java/org/apache/cassandra/db/rows/UnfilteredSerializer.java:635,687 (whole row built); src/java/org/apache/cassandra/db/ReadCommand.java:690-694 (size check after the row is built)

## OC-506

**Case file:** `key_cache_size-applySimpleConfig-keyCacheSizeInMiB--autonomous` · **Agent:** guided · **Patterns:** CP-1, CP-8, CP-16

Holder: the Caffeine key cache (KeyCacheKey -> AbstractRowIndexEntry). The case file links this to phase-2 B7, so it may already be filed. Why nothing stops it: the weigher counts only key.unsharedHeapSize() + value.unsharedHeapSize(). Caffeine's node (40 B), the ConcurrentHashMap node (32 B), the table slot and the frequency-sketch slot (about 90 B per entry) are not counted, so a full cache holds about 2.14x C at small keys (1.65x at 64-B keys). An explicitly set key_cache_size is never compared with the heap: the only check is >= 0. Size at defaults: C = min(5% of heap, 100 MiB), real about 214 MiB from a 2 GiB heap up (about 10.7% of a 2 GiB heap). It is bounded, and grows proportionally with a raised C (a 2 GiB C holds about 4.3 GiB).

**Where:** src/java/org/apache/cassandra/cache/CaffeineCache.java:61-69 (weigher key + value only); src/java/org/apache/cassandra/cache/KeyCacheKey.java:59-62; src/java/org/apache/cassandra/service/CacheService.java:123-128 (stale 'singleton weigher 48' comment); src/java/org/apache/cassandra/config/DatabaseDescriptor.java:815-823 (only the >= 0 check)

## OC-507

**Case file:** `key_cache_size-setKeyCacheCapacityInMB-capacity--autonomous` · **Agent:** guided · **Patterns:** CP-14, CP-16, CP-1

Holder: the Caffeine key cache's hash table and frequency sketch after a runtime capacity change. Why nothing stops it: setKeyCacheCapacityInMB checks only capacity < 0 (no upper bound, no heap check) and calls policy.setMaximum. The weight drops to the new cap at once, but the map table and sketch stay sized for the largest population ever reached, and invalidation does not shrink them either. Raising C at runtime carries the same about 2.14x uncounted multiple as the startup value. Size at defaults: about 24 MiB of table and sketch kept after a full 100 MiB cache; stage 4 measured +17.3 MB after 64 -> 16 MiB. Bounded by the largest size reached. A runtime raise to a large C reaches about 2x C of heap with no check.

**Where:** src/java/org/apache/cassandra/service/CacheService.java:336-342 (only < 0 rejected); src/java/org/apache/cassandra/cache/CaffeineCache.java:77-80 (setMaximum), :61-69 (weigher)

## OC-508

**Case file:** `key_cache_size-setKeyCacheCapacityInMB-capacity--autonomous` · **Agent:** guided · **Patterns:** CP-1

Same weigher mechanism as key_cache_size-applySimpleConfig-keyCacheSizeInMiB--autonomous (Caffeine and map overhead of about 90 B per entry not weighed, about 2.14x C at small keys); file it once and name both stems.

**Where:** src/java/org/apache/cassandra/cache/CaffeineCache.java:61-69

## OC-509

**Case file:** `max_concurrent_range_requests-computeConcurrencyFactor-liveReturned--autonomous` · **Agent:** autonomous · **Patterns:** —

Holder: coordinator heap. Each sub-range response (the serialized `data` ByteBuffer in ReadResponse, kept by the DataResolver/ReadCallback of each SingleRangeResponse) stays on the heap until the batch is iterated or closed. Why nothing stops it: the cap counts requests, not bytes. Each sub-range gets the full command limit (one page of rows, any row size). The `liveReturned == 0` branch, and the initial estimate when the local estimate is low, both jump straight to min(ranges, 10 x cores). At defaults no byte limit applies: read_thresholds_enabled=false and coordinator/local_read_size_* are null. The internode inbound reserve is released once the callback is delivered, so held responses count against nothing. Each query has its own cap with no node-wide total, and up to native_transport_max_threads=128 range queries can run at once (the native in-flight limit counts request bytes, not response bytes). Rough size at defaults: 6 nodes x 16 tokens (RF3) gives about 96 sub-ranges; with 16 cores the cap is 160, so all 96 go out. At QUORUM that is 2 data responses each, x 5,000-row driver page x 1 KiB, about 960 MB per query. Stage 4 measured 166 MB at only C=16 with 10 MB responses. A handful of concurrent scans like this go past a default heap (half of RAM, at most 16 GiB). Top-K (SAI ANN) queries skip the cap entirely through ScanAllRangesCommandIterator.

**Where:** src/java/org/apache/cassandra/service/reads/range/RangeCommandIterator.java:162 (also :230-236, :255); RangeCommands.java:54, :84, :96, :81-82; db/ReadResponse.java:228; config/Config.java:283, :526-530

## OC-510

**Case file:** `max_hints_size_per_host-shouldHint-maxHintsSize--autonomous` · **Agent:** autonomous · **Patterns:** —

Holder: HintRunnable tasks queued on the MUTATION stage, each holding its Mutation on the heap until it is serialized into a hint buffer. Why nothing stops it: the only guard on in-flight hints is checkHintOverload (throws above maxHintsInProgress = 128 x cores; its comment says it exists to 'avoid OOMing due to excess hints'). Only the dead-replica send paths call it (StorageProxy:796, :1505). Hints created when a write times out or fails (AbstractWriteResponseHandler.onFailure -> submitHint) and self-dropped local mutations (LocalMutationRunnable -> submitHint) skip it. The MUTATION stage queue has no size limit. The 3 hint buffers (32 MiB each) block writer threads while HintsWriteExecutor flushes, so when hint disk throughput falls behind the timeout rate, queued HintRunnables pile up. The client's in-flight bytes were already released when the client was answered (CL ONE/QUORUM), so nothing else counts them. max_hints_size_per_host defaults to 0, and in any case only checks the on-disk size. Rough size at defaults: a slow but still alive replica at RF3 gives one hint per write after the 2 s write timeout. 20k writes/s x 1 KiB mutation = about 20 MB/s retained per second of backlog, about 1.2 GB after one minute of hint writer lag.

**Where:** src/java/org/apache/cassandra/service/AbstractWriteResponseHandler.java:309-310; service/StorageProxy.java:1585-1598 (checkHintOverload), :2645-2654, :2822-2827 (submitHint onto Stage.MUTATION), :202; hints/HintsBufferPool.java:113-125

## OC-511

**Case file:** `max_value_size-applySimpleConfig-max_value_size--autonomous` · **Agent:** autonomous · **Patterns:** —

Holder: one byte[] of the declared length, allocated before the value is read (ByteBufferUtil.read does `new byte[length]` and then readFully). Why nothing stops it: the default max_value_size is 256 MiB, 16x the largest value a write can carry at defaults (max_mutation_size = commitlog_segment_size/2 = 16 MiB; the native message limit is the same). A corrupt length between 16 MiB and 256 MiB passes the guard and is allocated at full size on every read that reaches it, including reads that are about to fail. Reads of a corrupt SSTable repeat while the node keeps serving. Rough size at defaults: concurrent_reads = 32 reads hitting the corrupt cell x 256 MiB = 8 GiB of transient allocation, more than a default heap.

**Where:** src/java/org/apache/cassandra/db/marshal/AbstractType.java:594-599; utils/ByteBufferUtil.java:444-451; config/Config.java:309-310; config/DatabaseDescriptor.java:898-899

## OC-512

**Case file:** `max_value_size-applySimpleConfig-max_value_size--autonomous` · **Agent:** autonomous · **Patterns:** —

Holder: the same up-front byte[] allocation, but on value sites that never consult max_value_size. Why nothing stops it: collection cell paths (map keys, set elements, list cell ids) are read with ByteBufferUtil.readWithVIntLength, which only rejects negative lengths. The same is true of partition keys in UnfilteredRowIteratorSerializer (read responses), ReadResponse data/digest and PagingState keys. A corrupt vint length up to Integer.MAX_VALUE is passed straight to `new byte[length]`. Rough size: up to 2 GiB for one allocation per corrupt cell, enough on its own to throw OutOfMemoryError on a default heap of 8 GiB RAM or less (heap = half of RAM).

**Where:** src/java/org/apache/cassandra/db/marshal/CollectionType.java:368-371; utils/ByteBufferUtil.java:382-389, :444-451; db/rows/UnfilteredRowIteratorSerializer.java:199; db/ReadResponse.java:327-338

## OC-513

**Case file:** `memtable_cleanup_threshold-applySimpleConfig-memtable_cleanup_threshold--autonomous` · **Agent:** autonomous · **Patterns:** —

Holder: 1 MiB slab regions. With the default memtable_allocation_type heap_buffers these are on-heap ByteBuffer.allocate(1 MiB), one per live memtable allocator (each table and each index memtable), plus the region of every memtable still flushing. Why nothing stops it: the pool is charged only the bytes actually sliced out of a region (SlabAllocator.allocate charges `size`), never the 1 MiB region or the abandoned tail (up to 128 KiB) of a region that could not fit an allocation. The cleaner that this threshold drives picks the memtable with the largest owned ratio, so tables with small writes are never flushed by it. They keep their full regions until a commit-log-driven flush, invisible to memtable_heap_space and to the cleanup threshold. Rough size: 1,000 lightly written tables (plus about 50 system tables) x 1 MiB = about 1 GiB of heap uncounted, on top of the heap/4 memtable budget (2 GiB on an 8 GiB heap). Up to 12.5% tail waste on busy tables comes on top.

**Where:** src/java/org/apache/cassandra/utils/memory/SlabAllocator.java:51, :88-111, :129-148; db/memtable/AbstractAllocatorMemtable.java:249-278

## OC-514

**Case file:** `memtable_cleanup_threshold-applySimpleConfig-memtable_cleanup_threshold--autonomous` · **Agent:** autonomous · **Patterns:** —

Holder: memtable data allocated past the hard limit. Why nothing stops it: once a flush calls writeBarrier.markBlocking(), every write in the older OpOrder group records its allocation with no limit check. Only the number of writer threads bounds this: concurrent_writes 32 + counter 32 + view 32, each mutation up to max_mutation_size 16 MiB serialized and more as memtable objects. The memtable copy is extra to the mutation bytes already counted by the native and internode limits. Rough size: worst case 32 x 16 MiB = about 512 MiB above memtable_heap_space (heap/4) during each flush barrier.

**Where:** src/java/org/apache/cassandra/utils/memory/MemtableAllocator.java:180-184; db/ColumnFamilyStore.java:1236-1239; utils/memory/MemtablePool.java:151-161

## OC-515

**Case file:** `memtable_heap_space-applySimpleConfig-memtable_heap_space--autonomous` · **Agent:** autonomous · **Patterns:** —

Holder: 1 MiB on-heap slab regions (default heap_buffers). There is one current region per memtable allocator (each table, each index memtable, and each memtable still flushing). Regions that lose the allocation race are also kept in the global RACE_ALLOCATED queue. Why nothing stops it: the on-heap SubPool is charged only the bytes sliced out of a region, never the 1 MiB region or the unused tail (up to 128 KiB) left when a region cannot fit an allocation. memtable_heap_space therefore does not see this memory, and flushLargestMemtable (ranked by owned bytes) never picks tables with small writes, so their regions stay until a commit-log-driven flush. Rough size: 1,000 tables with small writes x 1 MiB = about 1 GiB of uncounted heap beyond the heap/4 cap, plus up to 12.5% region tail waste on busy tables.

**Where:** src/java/org/apache/cassandra/utils/memory/SlabAllocator.java:51-55, :88-111, :129-148; db/memtable/AbstractAllocatorMemtable.java:249-278

## OC-516

**Case file:** `memtable_heap_space-applySimpleConfig-memtable_heap_space--autonomous` · **Agent:** autonomous · **Patterns:** —

Holder: memtable allocations recorded past the limit. Why nothing stops it: SubAllocator.allocate skips tryAllocate when the OpOrder group is blocking. ColumnFamilyStore's flush marks all older writes as blocking (writeBarrier.markBlocking) and comments that they may 'exceed our memory limit'. Only the number of writer threads bounds this: MUTATION 32 + COUNTER_MUTATION 32 + VIEW_MUTATION 32, each mutation up to 16 MiB serialized (default max_mutation_size), and memtable objects add overhead. Rough size: worst case about 32 x 16 MiB = 512 MiB above the heap/4 cap at each flush barrier, with no global ceiling.

**Where:** src/java/org/apache/cassandra/utils/memory/MemtableAllocator.java:180-184; db/ColumnFamilyStore.java:1236-1239; concurrent/Stage.java:46-48

## OC-517

**Case file:** `memtable_heap_space-LeafBuilder-allocated--autonomous` · **Agent:** autonomous · **Patterns:** —

Holder: memtable allocations recorded past memtable_heap_space, including the BTree leaf deltas this case traces, reported through BTreePartitionUpdater.reportAllocatedMemory -> allocator.onHeap().adjust. Why nothing stops it: SubAllocator.allocate skips the limit for writes in a blocking OpOrder group, and every flush marks the older group blocking (ColumnFamilyStore writeBarrier.markBlocking). Only the number of writer threads bounds the overshoot (MUTATION 32 + COUNTER 32 + VIEW 32), each write up to 16 MiB serialized at default max_mutation_size, larger as BTree/row objects. Rough size: worst case about 512 MiB to 1.5 GiB beyond the heap/4 cap during a flush barrier.

**Where:** src/java/org/apache/cassandra/utils/memory/MemtableAllocator.java:160-184; db/partitions/BTreePartitionUpdater.java:180-183; db/ColumnFamilyStore.java:1236-1239

## OC-518

**Case file:** `memtable_heap_space-LeafBuilder-allocated--autonomous` · **Agent:** autonomous · **Patterns:** —

Holder: 1 MiB on-heap slab regions behind the default heap_buffers memtables, one per memtable or index memtable allocator. Why nothing stops it: the pool is charged only the bytes sliced out (SlabAllocator.allocate charges `size`), so whole regions of tables with small writes, and region tails of up to 128 KiB, never count toward memtable_heap_space. flushLargestMemtable ranks by owned bytes, so those tables are not flushed by the cleaner. Rough size: 1 MiB x the number of written tables, e.g. 1,000 tables = about 1 GiB above the heap/4 cap.

**Where:** src/java/org/apache/cassandra/utils/memory/SlabAllocator.java:51, :88-111, :129-148; db/memtable/AbstractAllocatorMemtable.java:249-278

## OC-519

**Case file:** `memtable_offheap_space-applySimpleConfig-memtable_offheap_space--autonomous` · **Agent:** autonomous · **Patterns:** —

Holder: 1 MiB slab regions. They are on heap under the default heap_buffers (memtable_offheap_space is ignored there) and direct ByteBuffers under offheap_buffers; there is one current region per memtable allocator, plus regions that lost the race kept in the global RACE_ALLOCATED queue. Why nothing stops it: the sub-pool (on-heap or off-heap) is charged only the bytes sliced out, not the region or the abandoned tail of up to 128 KiB. Neither memtable_offheap_space nor memtable_heap_space sees whole regions held by tables with small writes, and the cleaner, which ranks by owned bytes, never flushes them. Rough size: 1 MiB x the number of written tables (1,000 tables = about 1 GiB) uncounted. Under offheap_buffers this comes out of MaxDirectMemorySize (default a quarter of RAM), which it shares with the chunk cache and network buffers.

**Where:** src/java/org/apache/cassandra/utils/memory/SlabAllocator.java:51-55, :88-111, :129-148; utils/memory/SlabPool.java:28; db/memtable/AbstractAllocatorMemtable.java:97-110, :249-278

## OC-520

**Case file:** `memtable_offheap_space-applySimpleConfig-memtable_offheap_space--autonomous` · **Agent:** autonomous · **Patterns:** —

Holder: memtable off-heap (or heap) allocations recorded past the sub-pool limit. Why nothing stops it: writes in an OpOrder group marked blocking by a flush barrier call allocated(size) without tryAllocate. Only the number of writer threads bounds this (MUTATION/COUNTER/VIEW stages, 32 each), each write up to 16 MiB serialized at default max_mutation_size. Under offheap_objects the NativeAllocator memory comes from malloc, outside MaxDirectMemorySize, so the overshoot is visible only as process RSS. Rough size: worst case about 32 x 16 MiB = 512 MiB above the heap/4 off-heap limit per flush barrier.

**Where:** src/java/org/apache/cassandra/utils/memory/MemtableAllocator.java:180-184; db/ColumnFamilyStore.java:1236-1239; utils/memory/NativeAllocator.java:138-141

## OC-521

**Case file:** `min_index_interval-validate-minIndexInterval--autonomous` · **Agent:** autonomous · **Patterns:** —

Holder: native (Unsafe) Memory blocks behind BIG index summaries rebuilt at runtime, both the upsample/forced resample done by index-summary redistribution and the load-time rebuild. Why nothing stops it: IndexSummaryBuilder sizes its writers for estimatedKeys/min_index_interval entries x (64-byte default expected key + 8), plus 4 B per offset. Only the SSTableWriter path calls prepareToCommit() to trim them. buildSummaryAtLevel and the loading builder call build() on the untrimmed buffers and keep them via sharedCopy. IndexSummary.getOffHeapSize(), which index_summary_capacity redistribution budgets against, counts only the used bytes (offsetCount x 4 + entriesLength). Rough size at defaults (m=128): with 8-byte keys an entry uses 16+4 B but 72+4 B are reserved, about 3.8x. One sstable with 1e9 keys reserves about 590 MB against 156 MB counted, and summed over all rebuilt sstables the real native footprint can be about 4x the default capacity (5% of heap, e.g. 400 MB at 8 GiB heap -> about 1.5 GB), outside MaxDirectMemorySize.

**Where:** src/java/org/apache/cassandra/io/sstable/format/big/BigTableReader.java:625-640; io/sstable/format/big/BigSSTableReaderLoadingBuilder.java:209-228; io/sstable/indexsummary/IndexSummaryBuilder.java:42, :100-127, :246-251, :255-273; io/sstable/indexsummary/IndexSummary.java:259-262

## OC-522

**Case file:** `max_concurrent_range_requests-computeConcurrencyFactor-liveReturned--autonomous` · **Agent:** guided · **Patterns:** CP-2, CP-7, CP-3, CP-12

Holder: the coordinator heap, in the per-sub-range DataResolver/ReadCallback of one range query. When the first batch returns no rows, the next batch sends min(ranges, 10 x cores) sub-range requests at once. Each one carries the full command limit: the page size, or for an unpaged query the whole CQL LIMIT. The responses stay on the heap until the batch is iterated. Why nothing stops it: the cap counts requests, not bytes, and it applies per query. No node-wide limit covers response bytes across concurrent range queries. The internode receive reserve is released once the response callback has run, so held responses are charged to no counter. read_thresholds and coordinator_read_size are off at defaults. The only limit on concurrent queries is native_transport_max_threads = 128. Size at defaults: 3 nodes x 16 tokens = 48 ranges, which is below the 8-core cap of 80. 48 x 5,000-row page x 1 KiB is about 240 MB per query. Stage 4 measured 166 MB at C = 16 with 10 MB responses. Across up to 128 concurrent range queries that reaches tens of GB, past any default heap. Unpaged scans are worse because each sub-range response can hold the whole range.

**Where:** src/java/org/apache/cassandra/service/reads/range/RangeCommandIterator.java:162 (liveReturned == 0 returns max); RangeCommands.java:54 (10 x cores), :84; RangeCommandIterator.java:190 (forSubRange with full limit), :223-252; net/InboundMessageHandler.java:437-440 (reserve released after processing); config/Config.java:283

## OC-523

**Case file:** `max_hints_size_per_host-shouldHint-maxHintsSize--autonomous` · **Agent:** guided · **Patterns:** CP-2, CP-4, CP-5, CP-10

Holder: HintRunnable tasks queued on the MUTATION stage. Each task captures a full Mutation until the hint is written. Why nothing stops it: the brake (maxHintsInProgress = 128 x cores) counts mutations, not bytes. It is checked only when a write is admitted (performWrite), and only for destinations that already have hints in progress and still pass shouldHint. Hints created on write failure or timeout (AbstractWriteResponseHandler.onFailure, via submitHint) never go through checkHintOverload. So every write admitted before the count trips still produces a hint task later, about write_request_timeout (2 s) x arrival rate. max_hints_size_per_host (off by default) caps disk, not these in-memory tasks. Size at defaults: 16 cores gives 2,048 mutations before the soft brake, up to 16 MiB each (max_mutation_size). That is about 2 GB at 1 MiB mutations and up to about 32 GB at the 16 MiB limit, plus the overshoot from writes already in flight when a replica stalls.

**Where:** src/java/org/apache/cassandra/service/StorageProxy.java:202, :1505, :1585-1598 (checkHintOverload), :2820-2826 (submitHint on Stage.MUTATION); service/AbstractWriteResponseHandler.java:309-310 (unchecked hint on failure/timeout)

## OC-524

**Case file:** `max_hints_size_per_host-shouldHint-maxHintsSize--autonomous` · **Agent:** guided · **Patterns:** CP-5, CP-10, CP-4

Holder: the MUTATION stage queue, which is unbounded (SEPExecutor, concurrent_writes = 32 threads). When a local mutation has already expired by the time its task runs, LocalMutationRunnable does not drop it. It re-submits the same mutation as a HintRunnable to the same MUTATION stage, and that task applies it anyway. This path calls neither shouldHint nor max_hints_size_per_host. Why nothing stops it: when the stage is behind (memtable writers parked on hasRoom, a disk stall), each expired task is re-queued behind the backlog instead of being shed, so the backlog keeps holding the mutations. The only brake is the count-based checkHintOverload at admission of later writes. Size: the write rate x stall time x mutation size. For example, 20k writes/s x 10 s x 1 KiB is about 200 MB. With larger mutations it grows linearly up to 16 MiB each.

**Where:** src/java/org/apache/cassandra/service/StorageProxy.java:2640-2654 (expired LocalMutationRunnable resubmitted as HintRunnable), :2820-2826; concurrent/Stage.java:46

## OC-525

**Case file:** `max_mutation_size-applySimpleConfig-max_mutation_size--autonomous` · **Agent:** guided · **Patterns:** CP-16, CP-8

Holder: the hint buffer pool, up to MAX_HINT_BUFFERS = 3 direct ByteBuffers, each max(2 x max_mutation_size, 32 MiB). They are allocated with ByteBuffer.allocateDirect and kept for the life of the process. Why nothing stops it: the buffer size comes straight from max_mutation_size. When max_mutation_size is unset it is commitlog_segment_size/2. The only check is segment >= 2 x max_mutation_size and segment < 2048 MiB. Nothing relates 3 x buffer size to MaxDirectMemorySize (RAM/4), which these buffers share with the chunk-cache pool (min(512 MiB, H/4)), the networking pool and Netty. Size: 96 MiB at the default 32 MiB segment. Operators commonly raise the segment size to allow larger mutations: at 128 MiB it is 384 MiB, and at 1 GiB it is about 3 GiB of direct memory, allocated the first time hints overflow a buffer (a dead node under write load). That fails with 'Direct buffer memory' on a node with RAM/4 below that.

**Where:** src/java/org/apache/cassandra/hints/HintsService.java:79, :110; hints/HintsBuffer.java:77 (allocateDirect); hints/HintsBufferPool.java:41, :113-130; config/DatabaseDescriptor.java:898-901; config/CassandraRelevantProperties.java:351

## OC-526

**Case file:** `max_queue_weight-acquireWeight-weight--autonomous` · **Agent:** guided · **Patterns:** CP-8, CP-3

Holder: the BinLog WeightedQueue of the full query log and the audit log, one queue each. Each holds up to max_queue_weight of records on the heap, plus bound values in CBUtil direct memory. Why nothing stops it: the default is a fixed 256 MiB per log and does not scale with the heap. Nothing caps the two logs together. Producers blocked in put() each hold one more uncounted record, and up to 16 records the writer has dequeued are also uncounted. This is low confidence: both logs are off by default and are switched on at runtime with nodetool. Size: 2 x 256 MiB = 512 MiB. On a small node (2 GiB RAM, so a 1 GiB heap from cassandra-env.sh) that is 50% of the heap. Added to memtable_heap_space (H/4 = 256 MiB), the in-flight request budget (H/10) and the key cache, it comes to about 0.9 of the heap before any read or compaction garbage. If the writer falls behind (slow disk), both queues fill to their caps.

**Where:** src/java/org/apache/cassandra/utils/binlog/BinLogOptions.java:43, :49; utils/binlog/BinLog.java:221-227, :254-256; config/DatabaseDescriptor.java:586-587; conf/cassandra-env.sh:65

## OC-527

**Case file:** `memtable_offheap_space-applySimpleConfig-memtable_offheap_space--autonomous` · **Agent:** guided · **Patterns:** CP-8, CP-9

Holder: the off-heap memtable pool. Under offheap_objects it is NativeAllocator regions from Native.malloc (JNA), outside both -Xmx and MaxDirectMemorySize. It defaults to H/4 and is shared node-wide. Why nothing stops it: each pool is within its own cap, but nothing at startup or at the limit adds this pool to the heap, the chunk-cache pool (min(512 MiB, H/4)), the networking pool (min(128 MiB, H/16)) and the JVM baseline and compares the sum with RAM or the container. cassandra-env.sh sets the heap to RAM/2 and direct memory to RAM/4, so this pool's RAM/8 takes the caps alone to 7/8 of RAM. This is the R1-V shape. New here: 5.0.9's own conf/cassandra_latest.yaml ships memtable_allocation_type: offheap_objects, so a node started from that file has the pool active at H/4 with no edit. Size: at H <= 2 GiB, the defaults add 9H/16 beyond the heap, so a RAM = 2H container is over-committed once memtables fill and the chunk cache warms.

**Where:** src/java/org/apache/cassandra/config/DatabaseDescriptor.java:573-577, :583-584, :591-594; db/memtable/AbstractAllocatorMemtable.java:59, :106-108; utils/memory/MemoryUtil.java:81-84; conf/cassandra_latest.yaml:836; conf/cassandra-env.sh:65-66

## OC-528

**Case file:** `min_index_interval-validate-minIndexInterval--autonomous` · **Agent:** guided · **Patterns:** CP-16, CP-9, CP-11, CP-10

Holder: BIG-format index summaries, one per sstable. They are allocated with Memory.allocate, which is Native.malloc and outside both -Xmx and MaxDirectMemorySize. At full sampling each summary has ceil(keys/m) entries of 4 + key + 8 bytes. Why nothing stops it: the per-table min_index_interval is checked only for >= 1. A summary is built at full sampling when each sstable is written (flush or compaction). index_summary_capacity (5% of heap) is enforced only by the redistribution that runs every index_summary_resize_interval (60 min), and only best-effort: the floor at max_index_interval, and sstables under compaction are skipped. The builder's 2 GiB guard caps one summary, not the total across sstables. Size: m = 128 (default) is about 0.17 B per key, which is small. After ALTER TABLE ... min_index_interval = 1 it is about 22 B per key, so 1e9 partitions is about 22 GB of native memory, held until the next redistribution. Freshly compacted sstables return to full sampling every time they are rewritten.

**Where:** src/java/org/apache/cassandra/schema/TableParams.java:185; io/sstable/indexsummary/IndexSummaryBuilder.java:100-127; io/util/Memory.java:65; utils/memory/MemoryUtil.java:81-83; config/DatabaseDescriptor.java:867-869; io/sstable/indexsummary/IndexSummaryRedistribution.java:111-113, :181-186

## OC-529

**Case file:** `native_transport_max_concurrent_connections-channelActive-limit--autonomous` · **Agent:** autonomous · **Patterns:** —

Holder: each native connection's ByteToMessageDecoder cumulation buffer (InitialConnectionHandler before STARTUP, Envelope.Decoder on v3/v4 after it). It keeps a partly received envelope until the whole body arrives, up to native_transport_max_frame_size (16 MiB). Why nothing stops it: at defaults native_transport_max_concurrent_connections and _per_ip are both -1, so ConnectionLimitHandler is not even installed. No client byte budget applies before STARTUP: the allocator is first taken when STARTUP is handled. On v4 the in-flight check counts only fully decoded requests. native_transport_idle_timeout defaults to 0ms, so a half-sent envelope is held forever. Size at defaults: N connections x up to 16 MiB of pooled direct memory (CBUtil.allocator). On a 32 GiB host MaxDirectMemorySize is 8 GiB (a quarter of RAM), so about 512 idle, half-sent connections exhaust it (OutOfDirectMemoryError). Stage 4 measured exactly 4 MiB held per connection, linear in N (300 connections = 1.2 GiB).

**Where:** PipelineConfigurator.java:240-245 (handler only if a limit > 0), ConnectionLimitHandler.java:87-93, Envelope.java:197,429,441, InitialConnectionHandler.java:52,111, PreV5Handlers.java:153, CBUtil.java:60, Config.java:139,289, conf/cassandra-env.sh:62-66

## OC-530

**Case file:** `native_transport_max_concurrent_connections-configureInitialPipeline-getNativeTransportMaxConcurrentConnections--autonomous` · **Agent:** autonomous · **Patterns:** —

Holder: the per-connection decoder cumulation (InitialConnectionHandler / Envelope.Decoder), up to native_transport_max_frame_size = 16 MiB of a partly received envelope. Why nothing stops it: at the shipped -1 the gate at :240 installs no handler, so the connection count is unbounded. No ClientResourceLimits budget covers bytes before STARTUP, or v4 bytes before a full envelope is decoded. The idle timeout is 0 (off), and connections opened while the limit was off are never counted, even if a limit is set later. Size at defaults: N x 16 MiB of pooled direct memory. About 512 connections fill the default MaxDirectMemorySize of 8 GiB on a 32 GiB host. Stage 4 saw +4 MiB of NMT 'Other' per held connection, linear in N.

**Where:** PipelineConfigurator.java:240-245,265, Envelope.java:197,429,441, InitialConnectionHandler.java:52,111, CBUtil.java:60, Config.java:139,289, conf/cassandra-env.sh:62-66

## OC-531

**Case file:** `native_transport_max_concurrent_connections_per_ip-channelActive-perIpLimit--autonomous` · **Agent:** autonomous · **Patterns:** —

Holder: the decoder cumulation of each connection's partly received envelope, up to 16 MiB (native_transport_max_frame_size), in direct memory, outside any bytes-in-flight budget before STARTUP or before a v4 envelope completes. Why nothing stops it: the per-IP limit defaults to -1 (with the global limit -1, no handler is installed at all). Even when it is set, the per-IP count caps only one address, so the node total grows with the number of distinct source addresses (IPv6 or many clients). No idle timeout is set (0ms). Size at defaults: N connections x 16 MiB. About 512 connections reach the 8 GiB default MaxDirectMemorySize on a 32 GiB host. Stage 4 measured the node total growing 3.0x from 1 to 3 IPs (4 MiB per connection).

**Where:** ConnectionLimitHandler.java:101-127, PipelineConfigurator.java:240-245, Envelope.java:197,429,441, InitialConnectionHandler.java:52,111, CBUtil.java:60, Config.java:139

## OC-532

**Case file:** `native_transport_max_concurrent_connections_per_ip-configureInitialPipeline-getNativeTransportMaxConcurrentConnectionsPerIp--autonomous` · **Agent:** autonomous · **Patterns:** —

Holder: the per-connection ByteToMessageDecoder cumulation, a partly sent envelope of up to 16 MiB (max_frame_size), in pooled direct memory, uncovered by ClientResourceLimits before STARTUP or before a v4 envelope completes. Why nothing stops it: at the default -1/-1 the gate installs no handler, so the connection count is unbounded. When set, the per-IP limit bounds only one address, so the node total = (#source IPs) x P x 16 MiB. idle_timeout 0 never closes a stalled sender. Size at defaults: N x 16 MiB. About 512 connections exhaust the 8 GiB default direct-memory cap on a 32 GiB host. Stage 4 measured +4 MiB per held connection, and a second IP added its own share.

**Where:** PipelineConfigurator.java:240-245,265, ConnectionLimitHandler.java:101-127, Envelope.java:197,429,441, InitialConnectionHandler.java:111, Config.java:139

## OC-533

**Case file:** `native_transport_max_frame_size-applySimpleConfig-valueInBytes--autonomous` · **Agent:** autonomous · **Patterns:** —

Holder: the heap ByteBuf for a v3/v4 decompressed body. The LZ4 decompressor reads uncompressedLength from the first 4 bytes of the client's body and calls CBUtil.allocator.heapBuffer(uncompressedLength) before any validation. Why nothing stops it: max_frame_size checks only the compressed envelope length (a 13-byte envelope passes). Decompression runs in the Netty pipeline before LegacyDispatchHandler.checkLimits, and checkLimits charges header.bodySizeInBytes, which is the compressed size. Neither max_frame_size nor max_message_size nor the in-flight budget bounds the allocation. Size at defaults: up to 2^31-1 bytes (about 2 GiB) of heap per frame. A few connections on different event loops doing this at once exhaust an 8 GiB heap. Snappy validates the stream first, but a valid 16 MiB frame can still expand about 20x (about 340 MiB per request), also uncharged.

**Where:** Compressor.java:175-184 (LZ4 heapBuffer(uncompressedLength)), Compressor.java:90-98 (Snappy), Envelope.java:520-539 (Decompressor before dispatch), PreV5Handlers.java:153,181 (in-flight charges compressed bodySizeInBytes), Envelope.java:429

## OC-534

**Case file:** `native_transport_max_frame_size-applySimpleConfig-valueInBytes--autonomous` · **Agent:** autonomous · **Patterns:** —

Holder: the per-connection Envelope.Decoder / InitialConnectionHandler cumulation. This key caps it at 16 MiB per connection, but only per connection. Why nothing stops it: the connection count is unlimited at defaults (both connection limits -1, no handler installed), the idle timeout is 0, and no byte budget covers partial envelopes before STARTUP or partial v4 envelopes. Size at defaults: N x 16 MiB of direct memory. About 512 half-sent connections reach the 8 GiB default MaxDirectMemorySize on a 32 GiB host.

**Where:** Envelope.java:197,429,441, InitialConnectionHandler.java:52,111, PipelineConfigurator.java:240-245, CBUtil.java:60, Config.java:139,289

## OC-535

**Case file:** `native_transport_max_frame_size-decode-bytesToDiscard--autonomous` · **Agent:** autonomous · **Patterns:** —

Holder: the heap buffer allocated to decompress a v3/v4 envelope that is within the size limit. LZ4Compressor.decompress allocates heapBuffer(uncompressedLength), where uncompressedLength is the first 4 bytes of the client's body, before checking anything. Why nothing stops it: the discard/size check bounds only the compressed envelope (a tiny frame passes), decompression happens before LegacyDispatchHandler.checkLimits, and the in-flight budget charges the compressed bodySizeInBytes. Size at defaults: about 2 GiB of heap per 13-byte request. Several concurrent connections (one per event loop) can exhaust the default heap (8 GiB max). Snappy: a valid 16 MiB frame expands about 20x, to about 340 MiB per request, also uncharged.

**Where:** Compressor.java:175-184, Compressor.java:90-98, Envelope.java:520-539, PreV5Handlers.java:153,181, Envelope.java:429-441

## OC-536

**Case file:** `native_transport_max_frame_size-decode-bytesToDiscard--autonomous` · **Agent:** autonomous · **Patterns:** —

Holder: the cumulation that the frame limit allows per connection, up to 16 MiB of a frame that is not yet complete and within the limit. Why nothing stops it: the bound is per connection only. The number of connections is unlimited at defaults (both connection limits -1), native_transport_idle_timeout is 0, and no ClientResourceLimits budget covers bytes before an envelope is decoded or before STARTUP. Size at defaults: N x 16 MiB of direct memory (pooled CBUtil.allocator). About 512 stalled connections fill an 8 GiB MaxDirectMemorySize on a 32 GiB host.

**Where:** Envelope.java:197,441, InitialConnectionHandler.java:52,111, PipelineConfigurator.java:240-245,265, Config.java:139

## OC-537

**Case file:** `page_size_fail_threshold-execute-pageSize--autonomous` · **Agent:** autonomous · **Patterns:** —

Holder: the coordinator's full materialized result for a SELECT on the unpaged branch: replica responses, the merged partitions, the ResultSetBuilder rows and the encoded ResultMessage. Why nothing stops it: paging off (pageSize <= 0), LIMIT <= fetch size, or a huge fetch size all route to execute(query, ...), which never calls Guardrails.pageSize. Even on the paged branch the default threshold is -1. The byte guard is off at defaults: read_thresholds_enabled=false, and the coordinator/local read size fail thresholds are null. tombstone_failure_threshold counts tombstones only. Size at defaults: the whole result at once, several copies. Stage 4 measured about 11.5 KiB of coordinator heap per row (100,000 rows = about 1.15 GiB). An unpaged SELECT of about 700k such rows, or a few concurrent ones of about 100k rows on the 128 native-transport threads, exhausts an 8 GiB heap.

**Where:** SelectStatement.java:338-341, SelectStatement.java:417-430, SelectStatement.java:517 (guard only on paged branch), SelectStatement.java:602-608, SelectStatement.java:1004,1057, Config.java:526-530,874

## OC-538

**Case file:** `paxos_cache_size-applySimpleConfig-paxosCacheSizeInMiB--autonomous` · **Agent:** autonomous · **Patterns:** —

Holder: PaxosState.RECENT entries. The weigher charges only accepted/committed update.unsharedHeapSize(). It does not charge the partition key bytes (Key/DecoratedKey), ballots, Snapshot/Committed/PartitionUpdate shells or the Caffeine node. Why nothing stops it: a v1 prepare (a CAS whose condition fails, or a SERIAL read) on a fresh partition stashes a plain Snapshot with Committed.none (empty update). Its weight is only the empty static row, about 50-70 B. Partition keys can be up to 64 KiB. Size at defaults: cap = min(1% heap, 50) MiB = 50 MiB on an 8 GiB heap, about 0.7-1M such entries. Each holds about 0.4-0.5 KiB unweighed plus the key. With 8-16 KiB keys that is about 6-12 GiB of heap against a 50 MiB cap, which exceeds an 8 GiB heap. Stage 4 already saw 2.19x real/weight with 16 B values and small keys.

**Where:** PaxosState.java:72-76 (weigher), PaxosState.java:514-528 (close stashes Snapshot), PaxosState.java:720-746 (legacyPrepare builds plain Snapshot with committed none), Commit.java:188-191, PartitionUpdate.java:101-106,357-361, DatabaseDescriptor.java:849-852

## OC-539

**Case file:** `paxos_cache_size-close-active--autonomous` · **Agent:** autonomous · **Patterns:** —

Holder: Snapshots that close() moves into RECENT when the refcount reaches 0. The weigher counts only update.unsharedHeapSize(), never the partition key (DecoratedKey in Key and in the update) or the fixed shells. Why nothing stops it: an LWT/SERIAL prepare on a partition with no Paxos history leaves Snapshot(promised, committed=Committed.none). Its empty update weighs only about 50-70 B (the empty static row; LIVE deletion is 0), while the key can be up to 64 KiB. Size at defaults: 50 MiB cap (8 GiB heap) / about 60 B = about 0.8M entries. Each holds about 0.4-0.5 KiB of unweighed objects plus the key bytes. With 8-16 KiB keys that is about 6-12 GiB, which exceeds the heap. The stage-4 16 B value run already showed 2.19x overshoot with small keys.

**Where:** PaxosState.java:72-76, PaxosState.java:514-528 (:520 refcount, :525 RECENT.put), PaxosState.java:720-746, PaxosState.java:424-437 (maybeLoad), Commit.java:188-191, PartitionUpdate.java:101-106,357-361

## OC-540

**Case file:** `prepared_statements_cache_size-applySimpleConfig-preparedStatementsCacheSizeInMiB--autonomous` · **Agent:** autonomous · **Patterns:** —

Holder: the transient parse and prepare objects of one PREPARE: the ANTLR CommonTokenStream buffers a token object per lexeme, then the raw AST, the prepared statement, and measureDeep's traversal. Why nothing stops it: the cache cap (QueryProcessor.java:825) and the 65535-marker check (:758) run only after parseAndPrepare has built everything. The only bound on the input is native_transport_max_message_size / max_frame_size, 16 MiB by default (min of max_mutation_size and the in-flight limits). Size at defaults: a 16 MiB query of about 8M short lexemes, e.g. '?,' or IN-list terms, is roughly 50+ bytes of token object per 1-2 input bytes, about 0.5-1 GiB of heap per request. The in-flight budget (heap/10, about 820 MiB on an 8 GiB heap) admits about 50 such requests at once on up to 128 request threads, so a handful in parallel exhausts the heap.

**Where:** QueryProcessor.java:441-469 (parseAndPrepare, measureDeep), QueryProcessor.java:753-759, QueryProcessor.java:823-829, CQLFragmentParser.java:68-71, DatabaseDescriptor.java:649-651,903-905,3237-3244, Config.java:283

## OC-541

**Case file:** `native_transport_max_concurrent_connections-channelActive-limit--autonomous` · **Agent:** guided · **Patterns:** CP-6, CP-7, CP-8, CP-4, CP-10

Pre-STARTUP partial-envelope cumulation per native connection (one mechanism; the same row also covers the stems native_transport_max_concurrent_connections-configureInitialPipeline-..., native_transport_max_concurrent_connections_per_ip-channelActive-..., native_transport_max_concurrent_connections_per_ip-configureInitialPipeline-..., native_transport_max_frame_size-applySimpleConfig-... and native_transport_max_frame_size-decode-bytesToDiscard--autonomous). What holds the memory: the Netty ByteToMessageDecoder cumulation of InitialConnectionHandler's Envelope.Decoder, one per connection, in pooled direct memory (CBUtil.allocator = PooledByteBufAllocator(true)). It keeps a partly received v3/v4 envelope until the declared length arrives, up to native_transport_max_frame_size = 16 MiB. Why nothing stops it: (1) Both connection limits ship at -1, so ConnectionLimitHandler is not installed at all. (2) native_transport_idle_timeout = 0 ms, so no IdleStateHandler is added and a stalled sender is never closed. (3) The 16 MiB frame check bounds only one envelope. (4) The client byte budgets (native_transport_max_request_data_in_flight[_per_ip]) are first set up at STARTUP and are charged only after a whole frame decodes, so partial frames are never charged. (5) This is reachable before authentication, and ClientMetrics/clientstats do not see these connections. (6) Even with the limit set, the cap counts connections, not bytes: L × 16 MiB. Turning it on at runtime misses channels that are already open. The only stop is Netty's direct limit (= MaxDirectMemorySize), which ends in OutOfDirectMemoryError for every direct user on the node. Rough size at defaults: 16 MiB per stalled connection, plus one 16 MiB chunk per arena, up to 2 × cores. About 214-256 connections fill a 4 GiB direct budget (16 GiB host); about 480 fill the 7.75 GiB cap. Stage 4 measured 4 MiB × 300 connections = 1,200 MiB here, and on the decode case's recheck exactly k × 16 MiB at k = 64/256/512 (9 GiB at 512) with nothing refused.

**Where:** src/java/org/apache/cassandra/transport/Envelope.java:441-442 (returns null until the whole frame is buffered); PipelineConfigurator.java:240-245 (handler only if a limit > 0), :247-250 (idle handler only if > 0), :265 (InitialConnectionHandler with Envelope.Decoder); Config.java:139, 285, 289-290; InitialConnectionHandler.java:107-108 (first byte budget at STARTUP); CBUtil.java:60

## OC-542

**Case file:** `native_transport_max_concurrent_connections-configureInitialPipeline-getNativeTransportMaxConcurrentConnections--autonomous` · **Agent:** guided · **Patterns:** CP-6, CP-7, CP-8, CP-4, CP-10

Same mechanism as the candidate filed under native_transport_max_concurrent_connections-channelActive-limit--autonomous (file one row and name this stem too). At the gate at :240, both connection limits default to -1, so no ConnectionLimitHandler is installed. Combined with idle timeout 0 ms, every unauthenticated connection can keep an incomplete envelope of up to 16 MiB in the pooled direct cumulation of InitialConnectionHandler. No in-flight byte budget charges it, because the in-flight budgets charge only decoded frames. The only stop is the direct-memory limit (OutOfDirectMemoryError). This case adds a bypass: enabling the limit at runtime leaves pre-existing channels uncounted (stage 4: 36 open at a limit of 16). Rough size: 16 MiB per stalled connection. About 150-256 connections exhaust a 4 GiB default direct budget (8 GiB heap / 16 GiB host). Stage 4 saw 4 MiB per connection, NMT Other +256 MiB for 64 connections.

**Where:** src/java/org/apache/cassandra/transport/PipelineConfigurator.java:240-245, :265; Envelope.java:197, 441-442; Config.java:139, 289-290; PreV5Handlers.java:178-187 (in-flight charged only after decode); CBUtil.java:60

## OC-543

**Case file:** `native_transport_max_concurrent_connections_per_ip-channelActive-perIpLimit--autonomous` · **Agent:** guided · **Patterns:** CP-7, CP-6, CP-8, CP-4, CP-10

Same mechanism as the candidate filed under native_transport_max_concurrent_connections-channelActive-limit--autonomous (file one row and name this stem too). The pre-STARTUP Envelope.Decoder cumulation holds up to 16 MiB of pooled direct memory per connection, and nothing charges it. Per-IP specifics: the default P = -1 skips the check, and the handler is not installed while the global limit is also -1. Even with P set, the limit applies per source address (CP-7): the node holds P × #client IPs × 16 MiB, and only the global limit (default -1) caps the total. Idle timeout 0 ms keeps stalled senders open. The only stop is Netty's direct limit (OutOfDirectMemoryError). Rough size: about 256 stalled connections from any number of IPs (one included) reach a 4 GiB direct budget on a 16 GiB host. Stage 4 measured min(n, P) × 4 MiB, linear. The race in the unconditional remove at :142-144 (orphaned counter) overshoots by about one connection and is not a candidate.

**Where:** src/java/org/apache/cassandra/transport/ConnectionLimitHandler.java:101-127 (per-IP check), :87-92 (global -1 → Long.MAX_VALUE); PipelineConfigurator.java:240-245, :265; Envelope.java:441-442; Config.java:139, 289-290; CBUtil.java:60

## OC-544

**Case file:** `native_transport_max_concurrent_connections_per_ip-configureInitialPipeline-getNativeTransportMaxConcurrentConnectionsPerIp--autonomous` · **Agent:** guided · **Patterns:** CP-7, CP-6, CP-8, CP-4, CP-10

Same mechanism as the candidate filed under native_transport_max_concurrent_connections-channelActive-limit--autonomous (file one row and name this stem too). At the gate at :240, both limits default to -1, so no handler is installed. Each pre-auth connection can park up to 16 MiB of an incomplete envelope in the pooled direct cumulation. The in-flight limits charge only decoded requests (PreV5Handlers), so this memory is not charged. Idle timeout 0. Even when set, the per-IP knob caps only one address's share (P × 16 MiB), not the node. The only stop is the direct-memory limit (OutOfDirectMemoryError). Rough size: about 256 stalled connections ≈ 4 GiB, enough to fill a default direct budget of 4 GiB (16 GiB host) or a large share of one sized from the heap. Stage 4 measured exactly min(n, P) × 4 MiB.

**Where:** src/java/org/apache/cassandra/transport/PipelineConfigurator.java:240-245, :265; ConnectionLimitHandler.java:112-126; Envelope.java:197, 428-442; PreV5Handlers.java:157, 178-187; Config.java:139, 285, 289-290; CBUtil.java:60

## OC-545

**Case file:** `native_transport_max_frame_size-applySimpleConfig-valueInBytes--autonomous` · **Agent:** guided · **Patterns:** CP-16, CP-7, CP-6, CP-8

Same mechanism as the candidate filed under native_transport_max_concurrent_connections-channelActive-limit--autonomous (file one row and name this stem too). Two points come from this case. (a) The frame size is a per-connection cap only, and the connection count is unbounded at defaults, so the node holds N × MAX_TOTAL_LENGTH of partial envelopes in pooled direct memory before STARTUP and auth, with no idle timeout. (b) The startup check at :620 only rejects values ≥ 2048 MiB, so a plausible raise (for example 256 MiB for large blobs) multiplies what each stalled connection may pin. At 256 MiB, 16 stalled connections hold 4 GiB, which fills a default direct budget. That is the CP-16 shape on top of the same accumulation. At the default 16 MiB, about 256 connections fill a 4 GiB direct budget.

**Where:** src/java/org/apache/cassandra/config/DatabaseDescriptor.java:619-626 (only the range check); Envelope.java:197 (MAX_TOTAL_LENGTH from the setting), :428-442; PipelineConfigurator.java:240-245, :265; Config.java:139, 285, 289

## OC-546

**Case file:** `native_transport_max_frame_size-decode-bytesToDiscard--autonomous` · **Agent:** guided · **Patterns:** CP-6, CP-7, CP-8, CP-4, CP-10, CP-1

Same mechanism as the candidate filed under native_transport_max_concurrent_connections-channelActive-limit--autonomous (file one row and name this stem too). Below the frame limit, Envelope.Decoder returns null until the whole frame has arrived. The cumulation (pooled direct; its capacity grows past the readable bytes, for example 12 MiB for an 8 MiB frame, and one whole 16 MiB chunk at the limit) is held per connection until the frame completes or the connection closes. Nothing charges it: no connection limit, idle timeout 0, in-flight bytes charged only after decode. The recheck run on pc84 confirmed it: 64/256/512 stalled pre-login connections held exactly k × 16 MiB direct (9,216 MiB at 512, 58% of a 15.5 GiB limit), with 0 bytes in flight, 0 clients counted and nothing refused. Size: about 214-254 connections fill a 4 GiB direct budget.

**Where:** src/java/org/apache/cassandra/transport/Envelope.java:428-442; InitialConnectionHandler.java:52, 66-70; PipelineConfigurator.java:240-250, :265; PreV5Handlers.java:178-187; Config.java:139, 285, 289

## OC-547

**Case file:** `native_transport_max_frame_size-decode-bytesToDiscard--autonomous` · **Agent:** guided · **Patterns:** CP-14, CP-8, CP-9

Per-arena pooled chunks are kept after use, sized by cores, not by the heap. What holds the memory: the native-transport PooledByteBufAllocator, which has min(2 × cores, MaxDirect/16 MiB/6) direct arenas and 16 MiB chunks (maxOrder=11). Each arena an event loop touched keeps one 16 MiB chunk after the connections that used it are gone. Why nothing stops it: Netty never frees a chunk that stays in the qInit list, and Cassandra does not trim the pool. Size: on the 32-core pc84 run, 64 arenas held +1,024 MiB of direct memory, both with 512 idle connections and after every held connection was released (ΔO2(R) = +1,024 MiB in each arm). That is a fixed 1 GiB taken from the shared direct budget (chunk cache, networking cache, internode) that scales with cores. Also measured: the scope's memory.current stayed +1.8 to 2.9 GiB above baseline after the held buffers were freed (not returned to the OS by the native allocator). Under a container limit, a past burst therefore keeps RSS high.

**Where:** src/java/org/apache/cassandra/transport/CBUtil.java:60; conf/jvm11-server.options:145 (-Dio.netty.allocator.maxOrder=11); NativeTransportService.java:69 (default event-loop count); stage-4 recheck results native_transport_max_frame_size-decode-bytesToDiscard--autonomous--recheck-2026-11-17.md rows CTRL / release

## OC-548

**Case file:** `page_size_fail_threshold-execute-pageSize--autonomous` · **Agent:** guided · **Patterns:** CP-12, CP-10, CP-2, CP-8

An unpaged SELECT materializes its whole result on the coordinator. What holds the memory: the single ResultMessage.Rows that processResults builds on the coordinator, plus the replica data responses. Why nothing stops it: (1) The selector at :338 sends paging-off queries, queries with LIMIT ≤ fetch size, and TopK queries to the unpaged branch, which never calls Guardrails.pageSize.guard (that call is only at :517 on the paged branch). (2) The guardrail is -1 by default anyway, and it counts rows, not bytes. (3) The byte guards on the same heap (read_thresholds_enabled false, coordinator_/local_read_size_* null) are off by default. (4) Superusers and internal callers are exempt. (5) No limit charges response size, and up to native_transport_max_threads = 128 such queries can run at once. Rough size: stage 4 measured about 1.15 GiB allocated for one 100,000 × 2 KiB-row unpaged query (about 6× the value bytes; at least 200 MB of values retained until encoding) and 688 MiB for LIMIT 50,000. A handful of concurrent such queries exceed an 8 GiB heap. One query over a wide enough partition or table exceeds it alone.

**Where:** src/java/org/apache/cassandra/cql3/statements/SelectStatement.java:338-340 (unpaged selector), :517 (guard only on the paged branch), :561 processResults; :602 (same selector on executeInternal); Config.java:526-530 (read-size thresholds off), :873-874 (page_size thresholds -1); Guardrail.java:93-96 (exemptions)

## OC-549

**Case file:** `paxos_cache_size-applySimpleConfig-paxosCacheSizeInMiB--autonomous` · **Agent:** guided · **Patterns:** CP-1

The PaxosState.RECENT weigher counts only the stored PartitionUpdates (one mechanism; the same row also covers the stem paxos_cache_size-close-active--autonomous). What holds the memory: the Caffeine RECENT map of per-partition Paxos Snapshots. Why nothing stops it: the weight is accepted.update.unsharedHeapSize() + committed.update.unsharedHeapSize() (rows + static row + deletion info). It leaves out the Key/DecoratedKey, Snapshot, ballots, Accepted/Committed and PartitionUpdate shells, and the Caffeine/CHM node, about 430-460 B per entry. Non-applying CAS (StorageProxy :363) and v1 SERIAL reads propose an empty update, so their stashed Snapshot weighs about 64-128 B while holding about 500 B. Rough size at defaults: the cap is min(max(1, 1% of heap), 50) MiB. Over many distinct partitions with empty or tiny updates, that 50 MiB holds about 400-800K entries ≈ 200-350 MB of heap (4-7× the cap). Stage 4 measured 1.06× for 8 KiB values and 2.19× for 16-B values. Modest against a heap of 5 GiB or more; recorded as a CP-1 multiplier.

**Where:** src/java/org/apache/cassandra/service/paxos/PaxosState.java:72-76 (weigher, maximumWeight), :520-525 (stash into RECENT); db/partitions/PartitionUpdate.java:357-361; service/StorageProxy.java:363 (empty update on condition not met), :1933 (SERIAL read empty update); config/DatabaseDescriptor.java:849-852

## OC-550

**Case file:** `paxos_cache_size-close-active--autonomous` · **Agent:** guided · **Patterns:** CP-1

Same mechanism as the candidate filed under paxos_cache_size-applySimpleConfig-paxosCacheSizeInMiB--autonomous (file one row and name this stem too). close() at :520-525 stashes each idle Snapshot into RECENT. The weigher charges only the update payload, not the key, Snapshot, ballots, wrappers or Caffeine node. Per-entry overhead is 1.06× at 8 KiB values and 2.19× at 16-B values (measured), and about 4-7× for empty-update entries (non-applying CAS, v1 SERIAL reads). The default cap of at most 50 MiB can therefore retain about 100-350 MB. ACTIVE (unbounded CHM, :71) holds only partitions with an operation in flight, is bounded by request concurrency, and is not a candidate.

**Where:** src/java/org/apache/cassandra/service/paxos/PaxosState.java:71-76, :514-528

## OC-551

**Case file:** `prepared_statements_cache_size-getSizeOfPreparedStatementForCache-pstmntSize--autonomous` · **Agent:** autonomous · **Patterns:** —

The cache's size check comes too late to prevent the allocation. A PREPARE is lexed, parsed, prepared and measured with measureDeep before its weight is compared with the cap. Nothing caps the transient graph except the CQL message size. By default that size is min(max_mutation_size = 16 MiB, heap/10, heap/40), so 16 MiB per message. A 16 MiB statement with a literal list of millions of items (for example IN (1,2,3,...)) is processed in full: the input is copied to a char[] (about 32 MiB), CommonTokenStream keeps every token (roughly 8M tokens at about 70 B each, about 0.5 GB), and the Raw and prepared Term objects come on top. measureDeep then adds its own visited set over millions of objects. That is roughly 0.5-1 GB of heap per message. The in-flight limits count only the request bytes: heap/10 is about 820 MiB on an 8 GiB heap, which allows about 50 such messages at once (about 12 per client IP at heap/40), and up to 128 NTR threads can parse concurrently. A few concurrent messages exceed an 8 GiB heap before the :825 check rejects any of them.

**Where:** cql3/QueryProcessor.java:754, 436-469 (parseAndPrepare, measurePstmnt at 468-469 and 947-950), 825-829 (size check after the work is done); cql3/CQLFragmentParser.java:67-71 (ANTLRStringStream + CommonTokenStream); config/DatabaseDescriptor.java:649-657, 3237-3244 (default max message and in-flight bytes)

## OC-552

**Case file:** `repair_session_max_tree_depth-applySimpleConfig-repair_session_max_tree_depth--autonomous` · **Agent:** autonomous · **Patterns:** —

The depth cap (default 20) and repair_session_space bound only one validation's trees: one table, one session. On the coordinator, the number of jobs whose trees are held at once is unbounded by default. concurrent_merkle_tree_requests = 0 gives a NoopScheduler. AbstractRepairTask submits a RepairSession for every CommonRange, and each session submits a RepairJob for every table. All of them request trees right away, and the coordinator keeps the RF trees of each job until differencing ends. Size: on an 8 GiB heap, repair_session_space defaults to 512 MiB, so about 170 MiB per replica tree budget, which gives depth about 19. An off-heap Murmur3 tree takes 82*2^d+32 B, about 43 MiB, so about 130 MiB of direct memory per job with RF 3. A keyspace with 20+ large tables (at least ~2^19 partitions per session range), or several vnode sessions or repair commands at once, needs 2.5-8 GiB of direct memory. MaxDirectMemorySize defaults to the heap size and is shared with the chunk cache and networking, so this can end in an OOM. With a non-Murmur3 partitioner the trees are on heap. Each replica also builds trees on heap, up to concurrent_validations (= concurrent_compactors) at a time, each up to heap/48. cassandra.yaml itself says the unlimited default 'can produce OOM'.

**Where:** config/Config.java:210 (concurrent_merkle_tree_requests = 0), :212 (use_offheap_merkle_trees); repair/Scheduler.java:43-47 (0 -> NoopScheduler); repair/RepairCoordinator.java:127; repair/AbstractRepairTask.java:62-87 (all sessions submitted); repair/RepairSession.java:338-343 (a job per table); repair/RepairJob.java:195-197; repair/ValidationManager.java:62-80 (budget per validation, depth = min(...,20)); utils/MerkleTree.java:707, 759-760 (off-heap deserialize); conf/cassandra.yaml:827-861

## OC-553

**Case file:** `repair_session_max_tree_depth-setRepairSessionMaxTreeDepth-depth--autonomous` · **Agent:** autonomous · **Patterns:** —

A tree is capped at 2^min(depth, space-derived depth), but only per tree and per validation. Nothing bounds how many validations' trees the coordinator holds at once: concurrent_merkle_tree_requests defaults to 0, which gives a NoopScheduler, and every CommonRange session and every table's RepairJob requests trees at the same time. Each job keeps RF off-heap trees of 82*2^d+32 B (Murmur3) until differencing ends. At the defaults on an 8 GiB heap (repair_session_space 512 MiB, depth about 19-20), that is about 43-86 MiB per tree, about 130-260 MiB per job with RF 3. 20-60 concurrent jobs (a keyspace with many large tables, vnode sessions, or several repair commands) need 3-15 GiB of direct memory, against a MaxDirectMemorySize that defaults to the heap size. Off-heap trees can be turned off, or a non-Murmur3 partitioner keeps them on heap. A JMX depth above 20 is accepted with only a warning, which raises each tree further when space allows.

**Where:** repair/ValidationManager.java:62-80; config/DatabaseDescriptor.java:4075-4084 (>20 only warns); config/Config.java:210, 212; repair/Scheduler.java:43-47; repair/RepairCoordinator.java:127; repair/AbstractRepairTask.java:62-87; repair/RepairSession.java:338-343; repair/RepairJob.java:195-197; utils/MerkleTree.java:707, 759-760

## OC-554

**Case file:** `repair_session_space-applySimpleConfig-repair_session_space--autonomous` · **Agent:** autonomous · **Patterns:** —

repair_session_space (default heap/16) is a budget per validation, meaning one table and one session, not per node. The coordinator holds RF trees for every concurrent RepairJob. concurrent_merkle_tree_requests = 0 by default gives a NoopScheduler, so every session (one per CommonRange) and every table job requests and holds trees at once, and nothing sums them. On an 8 GiB heap each job's trees come to about 512 MiB of budget, or about 130-260 MiB of off-heap Murmur3 trees (82 B per leaf, depth about 19-20, RF 3). 20-60 concurrent jobs (many large tables, or vnode sessions, or parallel repair commands) need several GiB of direct memory, against a MaxDirectMemorySize that defaults to the heap size, or of heap with on-heap trees. The startup check only warns above heap/4 and puts no limit on the total. cassandra.yaml says the unlimited default 'can produce OOM'.

**Where:** config/DatabaseDescriptor.java:609-615; repair/ValidationManager.java:62-80; config/Config.java:210, 212; repair/Scheduler.java:43-47; repair/RepairCoordinator.java:127; repair/AbstractRepairTask.java:62-87; repair/RepairSession.java:338-343; repair/RepairJob.java:195-197; utils/MerkleTree.java:707, 759-760; conf/cassandra.yaml:827-861

## OC-555

**Case file:** `repair_session_space-initHelper-max--autonomous` · **Agent:** autonomous · **Patterns:** —

The check `depth == max` caps each tree at 2^max leaves, sized from repair_session_space/RF, but only for one validation. Both the replicas and the coordinator multiply it. On the coordinator, concurrent_merkle_tree_requests = 0 by default (NoopScheduler) lets every CommonRange session times every table job run at once, and each job keeps RF trees (moved or deserialized off-heap at 82 B per leaf for Murmur3) until differencing ends. That is about 130-260 MiB of direct memory per job on an 8 GiB heap (space 512 MiB, depth about 19-20). Tens of jobs exceed the default MaxDirectMemorySize (= heap). On each replica, up to concurrent_validations (= concurrent_compactors) on-heap trees of up to space/RF each (about 104 B per leaf plus inner nodes) are built at once, and a locally initiated tree is briefly copied off-heap while the on-heap tree still exists.

**Where:** utils/MerkleTree.java:136-160, 707, 759-760, 769-783; repair/ValidationManager.java:62-80; repair/Validator.java:122-125, 296-301; config/Config.java:210, 212; repair/Scheduler.java:43-47; repair/RepairCoordinator.java:127; repair/AbstractRepairTask.java:62-87; repair/RepairSession.java:338-343; repair/RepairJob.java:195-197

## OC-556

**Case file:** `repair_state_size-setRepairStateSize-size--autonomous` · **Agent:** autonomous · **Patterns:** —

repair_state_size bounds the number of entries, not their bytes, in each of two caches (repairs and participates, default 100,000 each, kept for 3 days). The bytes per entry are unbounded. A CoordinatorState holds a SessionState per CommonRange (with its ranges and endpoints), a JobState per table in each session, the RepairOption and the column-family list. A ParticipateState holds the ranges, the table ids and a Job (with ValidationState and SyncStates) per session and table. A bare entry measured about 1.8 KB. An entry for a keyspace with 20 tables over a few dozen vnode sessions is about 100s of KB, and a subrange or one-table repair is several KB. Scheduled or tooling-driven subrange repairs over 3 days, at 10 KB per entry times 100k times 2 caches, retain about 2 GB of heap on an 8 GiB heap, and larger per-entry states reach the full heap well before the count cap. The setter at :5070 cannot shrink the live caches.

**Where:** service/ActiveRepairService.java:250-260; config/Config.java:957-958; repair/state/CoordinatorState.java:48-54, 79; repair/state/SessionState.java:43-45, 95; repair/state/ParticipateState.java:45-62, 151-156; config/DatabaseDescriptor.java:5068-5075

## OC-557

**Case file:** `sai_vector_search_max_top_k-execute-pageSize--autonomous` · **Agent:** autonomous · **Patterns:** —

MAX_TOP_K (1000) caps rows per response, not the rows the coordinator holds. A top-K range read uses ScanAllRangesCommandIterator: it sends the full-range command to every replica it needs at once (the union of contacts over all ranges, about every node at CL ONE), and each replica returns up to LIMIT rows. The coordinator keeps all those responses until it has reduced them to LIMIT, and the result goes back unpaged. Row bytes are not bounded: the coordinator_read_size thresholds are off by default, and the native in-flight limits count only request bytes. At 1000 rows of about 10 KB (a 1536-dim float vector plus a text chunk) and 30 nodes, that is about 300 MB per query. Up to 128 NTR threads can run such queries concurrently, which gives tens of GB, far past the heap. Tombstones are kept outside the queue and are bounded only by the tombstone failure threshold.

**Where:** service/reads/range/RangeCommands.java:81-82; service/reads/range/ScanAllRangesCommandIterator.java:76-110; index/sai/plan/VectorTopKProcessor.java:91-123; index/sai/StorageAttachedIndex.java:497-505; cql3/statements/SelectStatement.java:322-340

## OC-558

**Case file:** `sep_maximum_pool_size-takeWorkPermit-workPermits--autonomous` · **Agent:** autonomous · **Patterns:** —

The work-permit cap limits only running tasks. The SEP task queue (ConcurrentLinkedQueue) is unbounded, and one source feeding it has no byte bound upstream. On a write at CL ONE or QUORUM, the coordinator queues its own replica's apply as a LocalMutationRunnable on MutationStage (maybeExecuteImmediately) and answers the client as soon as the remote acks arrive. That frees the request's native in-flight bytes while the Mutation (up to max_mutation_size = 16 MiB) stays queued. Internode-fed tasks are held against the receive reserve, but these are not. A task that has waited past the write timeout is dropped only when it reaches the front of the queue, and then also submits a hint. So the queue holds about the ingest rate times (2 s + dequeue lag). At 0.5-1 GB/s of client writes, against a coordinator whose local apply is slower than its peers (GC, disk, compaction), that is 1-2 GB of serialized mutations, several GB as deserialized Mutation objects on heap.

**Where:** concurrent/SEPExecutor.java:68, 103-106, 123-143, 196-197, 221-224; service/StorageProxy.java:1569, 1674-1700, 2634-2657

## OC-559

**Case file:** `repair_session_max_tree_depth-applySimpleConfig-repair_session_max_tree_depth--autonomous` · **Agent:** guided · **Patterns:** CP-7, CP-8

Same mechanism as the candidate filed under repair_session_space-initHelper-max--autonomous; file it once and name all four repair stems. Holder: the Merkle trees the repair coordinator receives, held off-heap. The depth cap is applied per tree, inside the per-validation repair_session_space budget. Nothing caps how many (session x table) tree sets the coordinator holds at once, because concurrent_merkle_tree_requests defaults to 0, which means unlimited. The depth cap does not bind at defaults: depth 20 is above the space-derived depth, and values above 20 are accepted with only a warning.

**Where:** src/java/org/apache/cassandra/repair/ValidationManager.java:62-80; src/java/org/apache/cassandra/config/DatabaseDescriptor.java:4075-4084

## OC-560

**Case file:** `repair_session_max_tree_depth-setRepairSessionMaxTreeDepth-depth--autonomous` · **Agent:** guided · **Patterns:** CP-7, CP-8, CP-6

Same mechanism as the candidate filed under repair_session_space-initHelper-max--autonomous; file it once. Holder: the coordinator's off-heap received trees, 82*2^d+32 B per tree (stage 4: 4 x 117 MB = 470 MB of direct memory at d = 20 for a single job). That size is set per tree. Because concurrent_merkle_tree_requests = 0 (NoopScheduler), every table job of every common-range session sends its validation requests at once. RF trees per job then pile up in direct memory until the slowest replica answers. No total cap exists, and the stop is OutOfMemoryError: Direct buffer memory.

**Where:** src/java/org/apache/cassandra/utils/MerkleTree.java:747-751; src/java/org/apache/cassandra/repair/Scheduler.java:43-46; src/java/org/apache/cassandra/repair/RepairCoordinator.java:127

## OC-561

**Case file:** `repair_session_space-applySimpleConfig-repair_session_space--autonomous` · **Agent:** guided · **Patterns:** CP-7, CP-8

Same mechanism as the candidate filed under repair_session_space-initHelper-max--autonomous; file it once. repair_session_space is a per-validation budget: space/RF per tree, with RF trees per (session, table) job at the coordinator. Startup validation rejects only values below 1 MiB and only warns above heap/4. No node-wide total exists, and the concurrency cap that would supply one, concurrent_merkle_tree_requests, ships at 0 (unlimited). The shipped yaml itself says this can produce OOM. At an 8 GiB heap, s = 512 MiB. Each full-depth job holds about 0.3 x s, roughly 160 MiB of direct memory, against a direct budget of about heap/2 = 4 GiB that the chunk cache and network buffers also use. About 25 concurrent full-depth table jobs exhaust it.

**Where:** src/java/org/apache/cassandra/config/DatabaseDescriptor.java:609-615; src/java/org/apache/cassandra/config/Config.java:210; conf/cassandra.yaml:842-861

## OC-562

**Case file:** `repair_session_space-initHelper-max--autonomous` · **Agent:** guided · **Patterns:** CP-7, CP-8, CP-6, CP-4

Holder: the repair coordinator's received Merkle trees, deserialized into ByteBuffer.allocateDirect (use_offheap_merkle_trees = true). The coordinator's own tree is also moved off-heap. Each tree set is released only after differencing, on the success path (RepairJob.java:355-357). Why nothing stops it: (1) repair_session_space (default heap/16) limits one validation, divided by RF, so it bounds only one (session, table) job, and that job holds about s at the coordinator. (2) RepairSession submits a RepairJob for every table at once, and AbstractRepairTask submits a session for every common range. (3) The only throttle is concurrent_merkle_tree_requests. Its default of 0 builds a NoopScheduler, so every job's validation requests go out at once. Trees that have arrived wait for the slowest replica, with no admission check before allocateDirect. The stop is the JVM's OutOfMemoryError: Direct buffer memory. Size at defaults (8 GiB heap): s = 512 MiB; 82 B per leaf off-heap gives about 0.3 x s, roughly 160 MiB per full-depth job (stage 4: 470 MB for one job's 4 trees at depth 20). The direct budget is about heap/2 = 4 GiB, shared with the chunk cache (up to 512 MiB) and networking buffers. About 25 concurrent full-depth jobs exhaust it: a full repair of a keyspace with that many large tables, or vnode rings with many common ranges times a few tables. The shipped yaml warns of this (CASSANDRA-19336).

**Where:** src/java/org/apache/cassandra/repair/ValidationManager.java:62-63; src/java/org/apache/cassandra/repair/Scheduler.java:43-46; src/java/org/apache/cassandra/repair/RepairCoordinator.java:127; src/java/org/apache/cassandra/repair/RepairSession.java:339-343; src/java/org/apache/cassandra/repair/RepairJob.java:197; src/java/org/apache/cassandra/utils/MerkleTree.java:747-751; src/java/org/apache/cassandra/config/Config.java:210-212; conf/cassandra.yaml:847-849

## OC-563

**Case file:** `repair_state_size-setRepairStateSize-size--autonomous` · **Agent:** guided · **Patterns:** CP-2, CP-15, CP-14

Holder: the two Guava caches of repair state, repairs (CoordinatorState) and participates (ParticipateState). Each is capped at repair_state_size = 100,000 entries and expires entries 3 days after write. Why nothing stops it: the cap counts entries, not bytes, and no setting bounds one entry's size. A CoordinatorState keeps one SessionState per common range, each with a JobState per table, plus RepairOption sets, neighbors and ranges, and the List<ColumnFamilyStore>. A ParticipateState keeps its ranges plus a Job, ValidationState and SyncStates per table per sync pair. Completed and failed repairs stay for 3 days. Size: stage 4 measured 1,768 B for a bare failed entry. A real entry grows with sessions x tables, roughly 1.7 KB + S x T x ~0.25 KB (estimate), so about 15 KB for a 50-table subrange repair and far more for a full vnode repair. At the cap that is about 100,000 x 15 KB = 1.5 GB per cache, about 3 GB for both caches on a node that both coordinates and participates. That is reachable with automated subrange repair (Reaper-style), which issues tens of thousands of commands within the 3-day window. Smaller than the heap at low command rates; the entry size is what is unbounded.

**Where:** src/java/org/apache/cassandra/service/ActiveRepairService.java:250-260; src/java/org/apache/cassandra/config/Config.java:957-958; src/java/org/apache/cassandra/repair/state/CoordinatorState.java:51-54; src/java/org/apache/cassandra/repair/state/SessionState.java:45; src/java/org/apache/cassandra/repair/state/ParticipateState.java:62,155-156

## OC-564

**Case file:** `row_cache_size-setRowCacheCapacityInMB-capacity--autonomous` · **Agent:** guided · **Patterns:** CP-12, CP-2

Holder: the on-heap CachedBTreePartition built on a row-cache miss. When the table caches full partitions (rows_per_partition ALL, or any value on a table without clustering columns), every miss runs fullPartitionRead and materializes the whole partition on heap, whatever the query's LIMIT or slice. Only then does it offer the result to OHC, and OHC may refuse it as too large for a segment. Why nothing stops it: row_cache_size bounds only the off-heap OHC copy. No byte check runs before CachedBTreePartition.create. With rows_per_partition = N the bound is a row count (N rows, each up to max_mutation_size = 16 MiB), not bytes. Size: one wide partition, which is unbounded (compaction only warns at 100 MiB), times the on-heap expansion (about 2-5x serialized), per concurrent miss. concurrent_reads = 32 allows 32 different wide keys at once, so for example 32 x 300 MB ≈ 10 GB from 100 MB partitions. Off at defaults: row_cache_size is 0 and table caching rows is NONE. The path needs an operator to enable the row cache.

**Where:** src/java/org/apache/cassandra/db/SinglePartitionReadCommand.java:545-548,557-569,604; src/java/org/apache/cassandra/db/ColumnFamilyStore.java:3259-3262

## OC-565

**Case file:** `sai_vector_search_max_top_k-execute-pageSize--autonomous` · **Agent:** guided · **Patterns:** CP-2, CP-12, CP-7

Holder: the unpaged Top-K (ANN) result. SelectStatement raises any smaller client page size to LIMIT and runs Top-K queries unpaged, so all LIMIT rows exist at once. They sit in the replica's VectorTopKProcessor priority queue of limit+1 rows (tombstones are kept outside it) and in the coordinator's single ResultMessage.Rows. Why nothing stops it: MAX_TOP_K = 1000 counts rows, not bytes. Read-size thresholds are off by default. No node-wide cap limits concurrent unpaged Top-K responses: native_transport_max_threads = 128, and the in-flight request byte limit counts request bytes, not response bytes. Size: stage 4 measured 48-80 MiB of coordinator heap per LIMIT-1000 query of 8 KiB rows (6-9x the value bytes), so 128 concurrent queries reach about 6-10 GiB, above an 8 GiB default heap. Rows can be up to max_mutation_size (16 MiB), so one query with large rows can reach GBs on its own.

**Where:** src/java/org/apache/cassandra/index/sai/StorageAttachedIndex.java:501-503; src/java/org/apache/cassandra/cql3/statements/SelectStatement.java:322-329,338-340; src/java/org/apache/cassandra/index/sai/plan/VectorTopKProcessor.java:91,108-122; src/java/org/apache/cassandra/config/CassandraRelevantProperties.java:479

## OC-566

**Case file:** `sep_maximum_pool_size-takeWorkPermit-workPermits--autonomous` · **Agent:** guided · **Patterns:** CP-5, CP-3

Holder: tasks queued on SharedPool stages, mainly MutationStage local writes, held as Mutation objects plus their runnables in each SEPExecutor's unbounded ConcurrentLinkedQueue. getMaxTasksQueued() returns Integer.MAX_VALUE, and the blocking after a queue breach was removed (CASSANDRA-16186). Why nothing stops it: the work-permit cap limits only running tasks. The Native-Transport-Requests permit, which limits in-flight CQL requests to 128, is returned when the request completes: at CL=ONE that is the first replica ack. The coordinator's own local write (performLocally) can still be waiting in the MutationStage queue, which holds no permit. When an expired local write is dequeued it is resubmitted as a hint and applied, not dropped. So the backlog grows with offered load x residence time while NTR stays at 128. Size: unbounded. The phase-2 S2 run held about 30,000 queued mutations with no plateau. Heap is shared with memtables (heap/4). This likely duplicates phase-2 S2; the session should check before filing.

**Where:** src/java/org/apache/cassandra/concurrent/SEPExecutor.java:68,103-106,123-133; src/java/org/apache/cassandra/service/StorageProxy.java:1566-1569,2638-2654; src/java/org/apache/cassandra/transport/Dispatcher.java:123-125

## OC-567

**Case file:** `commitlog_max_outstanding_replay_bytes-handlemutation-pendingmutationbytes--autonomous` · **Agent:** autonomous · **Patterns:** —

What holds it: the commit-log replay backlog. These are deserialized Mutation objects the reader has submitted to MUTATION but not yet collected. Why nothing stops it: the byte limit counts serialized entry bytes (pendingMutationBytes += size), not the heap of the deserialized object graph. Each cell's value becomes its own byte[] in a HeapByteBuffer inside a BufferCell, and each mutation under 2 MB also keeps a byte[] copy of its serialized form (cachedSerializations). For tiny cells (an int column, or collection elements of about 5-8 serialized bytes), the heap per cell is about 100-150 B, roughly 15-25 times the serialized size. Stage 4 measured 2x even for 64 KiB blobs. The count cap (1024) does not bind once mutations are 64 KiB or larger (1024 x 64 KiB = 64 MiB). Rough size at defaults: 64 MiB serialized is about 8-13 M tiny cells, or about 1-1.5 GiB of live heap, plus about 64 MiB of cached copies. This is held during startup replay while the same mutations fill memtables (memtable_heap_space = heap/4). With the default heap of RAM/2, an 8 GiB node has a 4 GiB heap, of which 1 GiB is memtables plus up to about 1.5 GiB of backlog. Heap exhaustion at startup is plausible on small or medium nodes after writes of large collection or many-column mutations.

**Where:** CommitLogReplayer.java:517,525-530 (check counts serialized size); CassandraRelevantProperties.java:114-115 (64 MiB / 1024 defaults); Cell.java:307-340 (per-cell value read); ByteBufferUtil.java:444-452 (new byte[] per value); Mutation.java:487-519 (cachedSerializations copy under CACHEABLE_MUTATION_SIZE_LIMIT); conf/cassandra-env.sh:58-66 (heap = RAM/2)

## OC-568

**Case file:** `file_cache_size-chunkcache-cachesize--autonomous` · **Agent:** autonomous · **Patterns:** —

What holds it: the chunk-cache BufferPool also serves the per-reader buffers of uncached readers. With the default file_cache_enabled=false and disk_access_mode=mmap_index_only, every open RandomAccessReader on a compressed data file takes a chunk_length buffer (16 KiB by default) from it, and keeps it until the reader closes. Why nothing stops it: the pool's file_cache_size threshold (default min(512 MiB, heap/4)) only refuses new 1 MiB slabs. Past it, LocalPool.get falls back to an unpooled ByteBuffer.allocateDirect counted only in overflowMemoryUsage, so the limit does not stop the allocation. Nothing caps how many readers are open at once (one per sstable per in-flight read or compaction scanner). Rough size at defaults: the 512 MiB threshold is reached at about 32k open 16 KiB readers. Beyond it, each reader adds 16 KiB of direct memory up to MaxDirectMemorySize (RAM/4, about 4 GiB on a 16 GiB node, shared with the networking pool and Netty). For example, 32 concurrent partition-range reads on a table with about 10k STCS sstables give about 320k readers, or about 5 GiB of direct memory: OutOfMemoryError 'Direct buffer memory'. This needs a large sstable count, so it is a weak clue.

**Where:** BufferManagingRebufferer.java:45 (buffer per reader from forChunkCache); FileHandle.java:421-424,444-447 (uncached compressed reader under default access mode); Config.java:122 (mmap_index_only default); BufferPool.java:441-450 (threshold refuses slabs only); BufferPool.java:904-923 and 233-238 (unpooled allocateDirect overflow); BufferPools.java:37-38 (threshold = file_cache_size); CompressionParams.java:48 (16 KiB chunk); conf/cassandra-env.sh:66 (direct = RAM/4)

## OC-569

**Case file:** `file_cache_size-chunk_cache_eviction-weighted_size--autonomous` · **Agent:** autonomous · **Patterns:** —

What holds it: uncached readers' chunk buffers from the chunk-cache BufferPool. With the cache disabled by default and data files not mmapped (mmap_index_only), each open compressed-file reader holds a 16 KiB direct buffer for its lifetime. Why nothing stops it: the pool threshold (file_cache_size; the 32 MiB reserve is only first-come headroom) refuses new slabs but then falls back to an unpooled ByteBuffer.allocateDirect per request, counted only as overflow. Nothing bounds the number of concurrently open readers (one per sstable per read or compaction scanner). Rough size at defaults: about 32k readers fill the 512 MiB threshold. After that, 16 KiB each up to MaxDirectMemorySize (RAM/4, for example 4 GiB on a 16 GiB node). Example: about 320k open readers (32 range reads x 10k sstables) need about 5 GiB, giving a 'Direct buffer memory' OOM. This needs an extreme sstable count, so it is a weak clue.

**Where:** BufferManagingRebufferer.java:45; FileHandle.java:421-424,444-447; Config.java:122; BufferPool.java:441-450; BufferPool.java:904-923 and 233-238; BufferPools.java:37-38; CompressionParams.java:48; conf/cassandra-env.sh:66

## OC-570

**Case file:** `file_cache_size-chunkcache-weightedsize--autonomous` · **Agent:** autonomous · **Patterns:** —

What holds it: chunk buffers taken from the chunk-cache BufferPool by uncached readers. With file_cache_enabled=false by default and disk_access_mode=mmap_index_only, each open reader on a compressed data file holds one chunk_length (16 KiB) direct buffer until it closes. Why nothing stops it: the pool check against file_cache_size only decides pooled versus unpooled. Past the threshold, each request becomes a fresh ByteBuffer.allocateDirect counted as overflow. Nothing caps the number of concurrently open readers (sstables x in-flight reads and compaction scanners). Rough size at defaults: the threshold is min(512 MiB, heap/4), about 32k readers. Past it, 16 KiB per reader up to MaxDirectMemorySize (RAM/4, for example 4 GiB on 16 GiB). About 320k concurrently open readers (for example 32 range reads over about 10k STCS sstables) need about 5 GiB, giving a 'Direct buffer memory' OOM. It needs a very large sstable count, so it is a weak clue.

**Where:** BufferManagingRebufferer.java:45; FileHandle.java:421-424,444-447; Config.java:122; BufferPool.java:441-450; BufferPool.java:904-923 and 233-238; BufferPools.java:37-38; CompressionParams.java:48; conf/cassandra-env.sh:66

## OC-571

**Case file:** `permissions_cache_max_entries-initcache-entrycount--autonomous` · **Agent:** guided · **Patterns:** CP-2

Holder: PermissionsCache (and RolesCache, same AuthCache builder), Caffeine maximumSize(1000) on (AuthenticatedUser, IResource) keys. The cap counts entries, not bytes. Each key keeps the resource name, and a role name in a statement such as DROP ROLE IF EXISTS on a non-existent role is never length-checked (RoleResource.role keeps the raw String). Each such lookup adds one entry (stage 4: about 4 KB per 4000-character name, linear in name length). Nothing bounds the per-entry size except the CQL message size limit (MiB-scale). The 2 s validity (expireAfterWrite) caps retention at roughly ingest rate x 2 s, up to 1000 x the largest key. Expired entries are only swept on later cache activity. Rough size: 0 at shipped defaults (AllowAllAuthorizer, so no cache). With CassandraAuthorizer and an authenticated client sending MiB-scale role names: about 1 GB per 2 s at 1 GB/s, theoretical ceiling 1000 x message size (GiB). Low priority: it needs an authenticated, hostile client, and the retained amount depends on the ingest rate.

**Where:** src/java/org/apache/cassandra/auth/AuthCache.java:344-347; src/java/org/apache/cassandra/auth/RoleResource.java:86-89; src/java/org/apache/cassandra/config/Config.java:90-91

## OC-572

**Case file:** `file_cache_size-chunkcache-weightedsize--autonomous` · **Agent:** guided · **Patterns:** CP-6, CP-7

Holder: the chunk-cache BufferPool, used even with the chunk cache off (the shipped default). Every open uncached data-file reader (BufferManagingRebufferer) takes one chunk_length buffer from it at construction and keeps it until closeReader. The pool's limit (file_cache_size, default min(512 MiB, heap/4)) is soft. When allocateMoreChunks refuses a new 8 MiB slab, get() falls back to an unpooled ByteBuffer.allocateDirect that is counted only in OverflowSize, so -XX:MaxDirectMemorySize is the only real stop. Owners are open readers: SSTables touched per read x concurrent reads (32 read threads, and range scans open every overlapping SSTable), plus compaction, streaming and repair scanners. No limit caps their sum. Rough size: 16 KiB per reader at defaults, so it needs tens of thousands of open readers to reach the 512 MiB pool (for example 32 concurrent range scans x 1000+ SSTables during an L0/STCS backlog, about 0.5 GiB). Beyond that, each 16 KiB comes straight from direct memory, shared with the networking pool and Netty under MaxDirectMemorySize = heap/2. Stage 4 measured a 16 MiB baseline of reader slabs with the cache off.

**Where:** src/java/org/apache/cassandra/io/util/BufferManagingRebufferer.java:45; src/java/org/apache/cassandra/utils/memory/BufferPool.java:443-451; src/java/org/apache/cassandra/utils/memory/BufferPool.java:923; src/java/org/apache/cassandra/utils/memory/BufferPool.java:233-239

## OC-573

**Case file:** `file_cache_size-chunk_cache_eviction-weighted_size--autonomous` · **Agent:** guided · **Patterns:** CP-6, CP-8, CP-14

Holder: the chunk cache plus its BufferPool (file_cache_enabled: true). The cache weighs each cached buffer's capacity against F - 32 MiB. The pool's memoryAllocated counter (slabs, up to F) is never decremented: slabs stay for the life of the JVM. When the pool is full or fragmented, a load falls back to an unpooled allocateDirect overflow buffer that is still admitted to the cache. Slabs pinned by evicted-but-referenced buffers or partly used chunks (for example tables with mixed 4-64 KiB chunk sizes) then sit beside up to F - 32 MiB of cached overflow buffers. Nothing caps the sum below about 2F. Rough size: about 1 GiB at the default F = 512 MiB, against a direct budget of heap/2 (1 GiB at a 2 GiB heap, also shared with the 128 MiB networking pool). Weak: it needs a non-default cache setting and pool fragmentation, and stage 4 measured overflow 0.

**Where:** src/java/org/apache/cassandra/cache/ChunkCache.java:152-155; src/java/org/apache/cassandra/cache/ChunkCache.java:163; src/java/org/apache/cassandra/utils/memory/BufferPool.java:443-451; src/java/org/apache/cassandra/utils/memory/BufferPool.java:923

## OC-574

**Case file:** `file_cache_size-chunkcache-cachesize--autonomous` · **Agent:** guided · **Patterns:** CP-16, CP-6, CP-7, CP-14

Holder: per-reader uncompressed chunk buffers (BufferManagingRebufferer; ChunkCache.load when the cache is on) and per-thread compressed-input buffers (CompressedChunkReader through ThreadLocalByteBufferHolder). All are sized straight from the table option chunk_length_in_kb, which is only checked to be > 0, a power of 2 and <= Integer.MAX_VALUE/1024 KB. Any value up to 1 GiB is accepted by a CREATE/ALTER TABLE. Buffers above 128 KiB (NORMAL_CHUNK_SIZE) always bypass the pool through unpooled allocateDirect, so neither file_cache_size nor the pool limit bounds them. Each open reader holds one chunk-sized direct buffer. Each reading thread also keeps its largest compressed buffer for life, never shrunk. Rough size: with chunk_length_in_kb = 65536 (64 MiB), 32 read threads plus compaction keep about 40 x 64 MiB = 2.5 GiB of thread-local direct memory, plus 64 MiB per open reader (SSTables x concurrent reads). That is far past the default MaxDirectMemorySize of heap/2. At the default 16 KiB it is negligible.

**Where:** src/java/org/apache/cassandra/schema/CompressionParams.java:352; src/java/org/apache/cassandra/schema/CompressionParams.java:447-451; src/java/org/apache/cassandra/io/util/BufferManagingRebufferer.java:45; src/java/org/apache/cassandra/io/util/CompressedChunkReader.java:138; src/java/org/apache/cassandra/utils/memory/BufferPool.java:908-923

## OC-575

**Case file:** `commitlog_max_outstanding_replay_bytes-handlemutation-pendingmutationbytes--autonomous` · **Agent:** guided · **Patterns:** CP-1, CP-2, CP-8

Holder: the commit-log replay backlog. These are deserialized Mutation objects held by runnables queued on MutationStage until the single reader collects their futures. The bound charges each entry's serialized length (CommitLogReader size, added at :517). The held object is the deserialized graph plus a cached copy of its serialized bytes below 1,000,000 B. That is 2x for single-blob rows (stage 4: 132 KB per 65.6 KB mutation) and about 15x for tiny-cell maps. The count cap (1024) binds below 64 KiB per entry and the byte cap above, so the real ceiling is about 64 MiB x the expansion ratio at any entry size. The fixed 64 MiB/1024 defaults do not scale with the heap and share the start-up heap with the memtables replay refills (heap/4). Rough size: about 0.95 GiB at defaults for tiny-cell data when the appliers stall on memtable flush, equal to a 1 GiB heap. This is the known phase-2 B8 mechanism (listed under CP-1), so file it for completeness and dedupe against B8.

**Where:** src/java/org/apache/cassandra/db/commitlog/CommitLogReplayer.java:517; src/java/org/apache/cassandra/db/commitlog/CommitLogReplayer.java:525-530; src/java/org/apache/cassandra/db/commitlog/CommitLogReader.java:431-433; src/java/org/apache/cassandra/db/Mutation.java:491-519

## OC-576

**Case file:** `commitlog_max_compression_buffers_in_pool-simplecachedbufferpool-bufferpool--autonomous` · **Agent:** guided · **Patterns:** CP-7, CP-14, CP-8

Holder: DataOutputBuffer.scratchBuffer, a FastThreadLocal of direct ByteBuffers (ALLOCATION_TYPE DIRECT by default). Callers are CommitLog.add (every writer thread), Mutation serialization and deserialization caching, UnfilteredSerializer (flush, compaction, streaming writers) and HintsWriter. close() keeps the grown buffer when it is <= dob_max_recycle_bytes (1 MiB), so each thread that once serialized a mutation or row of up to 1 MiB keeps up to 1 MiB of direct memory for life. Larger buffers are dropped as direct garbage that only GC frees. No pool counts this memory, and the commit-log buffer cap N does not include it (stage 4 saw a constant 262,195 B writer scratch buffer outside N). Owners are threads: native_transport_max_threads 128 + concurrent_writes 32 + counter 32 + view 32 + flush, compaction and messaging threads, with no total cap. Rough size: about 250 threads x 1 MiB = about 250 MiB of direct memory at defaults with 0.5-1 MiB mutations. It shares MaxDirectMemorySize = heap/2 with file_cache_size (512 MiB) and networking (128 MiB). At a 2 GiB heap (1 GiB direct) that leaves little room.

**Where:** src/java/org/apache/cassandra/io/util/DataOutputBuffer.java:63-89; src/java/org/apache/cassandra/db/commitlog/CommitLog.java:306; src/java/org/apache/cassandra/db/Mutation.java:491; src/java/org/apache/cassandra/db/rows/UnfilteredSerializer.java:195; src/java/org/apache/cassandra/config/Config.java:180-182,283

## OC-577

**Case file:** `commitlog_max_compression_buffers_in_pool-simplecachedbufferpool-usedbuffers--autonomous` · **Agent:** guided · **Patterns:** CP-14, CP-7

Holder: ThreadLocalByteBufferHolder, a static FastThreadLocal per BufferType shared by commit-log compression/encryption (SimpleCachedBufferPool.getThreadLocalReusableBuffer) and SSTable compressed chunk reads. getBuffer replaces the thread's buffer only when it is too small and never shrinks or clears it. Any thread that compresses a commit-log segment keeps an output buffer of about initialCompressedBufferLength(segment) for life, as does an encrypting thread (one full segment). Those threads are the sync thread and the MemtablePostFlush thread through discard, close and sync (stage 4: a 64.2 MiB step). Any thread reading compressed SSTables keeps its largest compressed chunk. None of this is counted in commitlog_max_compression_buffers_in_pool (N), whose cap covers only segment buffers. Rough size: at defaults (mmap, uncompressed commit log) zero. With LZ4/Zstd at 32 MiB segments about 2 x 32-64 MiB of extra direct memory outside N x segment size. It scales with commitlog_segment_size (up to 2 GiB) and with the number of threads that ever sync a segment.

**Where:** src/java/org/apache/cassandra/io/util/ThreadLocalByteBufferHolder.java:71-80; src/java/org/apache/cassandra/io/util/SimpleCachedBufferPool.java:80-83; src/java/org/apache/cassandra/db/commitlog/CompressedSegment.java:67-68; src/java/org/apache/cassandra/db/commitlog/EncryptedSegment.java:112

