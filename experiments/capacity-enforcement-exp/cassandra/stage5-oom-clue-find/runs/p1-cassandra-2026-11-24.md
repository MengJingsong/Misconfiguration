# Stage 5 phase 1 — Cassandra extension batch 1 (2026-11-24)

Full clue and `file:line` for each `OC-` row filed from the stage-5 runs of the extension set's batch 1 of 2026-11-24 (the two cases whose stage 4 finished: order 122 `rowsize-checkcanread-bytesread--autonomous`, true negative, and order 123 `profileload-capacity-beginsampling-capacity--autonomous`, true positive; one autonomous and one guided agent per case; guided agents used CP-1..CP-16). The candidate list row holds the agent's summary.

## OC-580

**Case file:** `rowsize-checkcanread-bytesread--autonomous` · **Agent:** autonomous · **Patterns:** —

**Summary:** A well-formed row is materialized whole on read and compaction, and is also serialized whole into a heap scratch buffer on write. rowSize is only the row's own length. All row/collection guardrails are off by default, so a non-frozen collection can grow through ~16 MiB appends to a multi-GiB row. At ~4-8 GiB it fills the default heap (min(RAM/2, 15.5 GiB)), e.g. 8 GiB on a 16 GiB host.

What holds the memory: the Row built by deserializeRowBody, i.e. every cell of the row as Cell<byte[]> objects in the Row.Builder BTree. A complex column's cell count is read from the data and looped with no bound: `int count = in.readUnsignedVInt32(); while (--count >= 0) { ... builder.addCell(cell) }`. The row is atomic: paging limits rows, not bytes inside one row, so a SELECT of that row (and every compaction or merge of it) holds the entire row in heap. On the write side (flush and compaction output), the whole row body is first serialized into the thread-local scratch DataOutputBuffer. That buffer grows by doubling (up to 64 MiB, then linear) and only then is copied to the file, so the row is held twice. Buffers larger than 1 MiB are dropped on close.

Why nothing stops it: the per-row limit (TrackedDataInputPlus.limit = rowSize) is not a cap. Its value is the row's own serialized size, read from the data. For well-formed data it always equals what is read, so it never binds. A row can grow without bound because each mutation is capped at max_mutation_size = commitlog_segment_size/2 = 16 MiB, but any number of mutations can append to the same row, e.g. UPDATE t SET m = m + {...}, or set/list appends to a non-frozen collection. Every guardrail that would cap this is disabled by default: partition_size_*, column_value_size_*, collection_size_* (null) and items_per_collection_* (-1).

Rough size at defaults: ~512 appends of 16 MiB give an 8 GiB collection in one row. With per-cell object overhead (Cell + CellPath + byte[] headers), deserializing a 2-4 GiB row already needs several GiB. The coordinator then builds the CQL collection value and the result message, another copy of similar size. A few concurrent reads of such a row (concurrent_reads = 32), or one compaction of it, exceed a default heap of min(RAM/2, 15.5 GiB), which is 8 GiB on a 16 GiB node.

**Where:** UnfilteredSerializer.java:585-587 (rowSize read from data and used as the limit), UnfilteredSerializer.java:614-626 (columns.apply over the whole row), UnfilteredSerializer.java:682-688 (unbounded complex-cell count loop into builder.addCell), UnfilteredSerializer.java:631 (builder.build()), UnfilteredSerializer.java:195-203 (whole row body serialized into DataOutputBuffer.scratchBuffer before writing), DataOutputBuffer.java:63-80 and CassandraRelevantProperties.java:203-204 (64 MiB doubling threshold, 1 MiB recycle cap), DatabaseDescriptor.java:898-899 (max_mutation_size = segment/2 = 16 MiB, per mutation only), Config.java:910-920 (partition/column-value/collection guardrails null or -1 by default), conf/cassandra.yaml:722 (concurrent_reads: 32), conf/cassandra-env.sh:51-66 (default heap min(RAM/2, 15872 MiB)).

## OC-581

**Case file:** `rowsize-checkcanread-bytesread--autonomous` · **Agent:** autonomous · **Patterns:** —

**Summary:** A corrupt cell length allocates new byte[l] (up to max_value_size, 256 MiB) before the rowSize limit can throw. Under the default disk_failure_policy=stop, a CorruptSSTableException does not stop transports, so reads keep hitting it. 32 concurrent reads × 256 MiB = 8 GiB transient humongous heap. Stage 4 measured 200 MiB per read at any L.

What holds the memory: ByteArrayAccessor.read does `byte[] b = new byte[length]; in.readFully(b);`. The array sized to the encoded length l is allocated first. Only then does readFully reach TrackedDataInputPlus.checkCanRead, which notices that l exceeds the row size and throws EOFException. The only bound on l is max_value_size, default 256 MiB, checked in AbstractType.read. Stage 4 confirmed the mechanism: one byte[] of V + 16 B per corrupt read (104,857,616 B and 209,715,216 B), identical whether L was 3 or 6 MiB. Three sequential 200 MiB reads pushed a 1 GiB heap to 773M and triggered G1 humongous-allocation pauses.

Why nothing stops repetition or concurrency: the default disk_failure_policy is `stop`. DefaultFSErrorHandler.handleCorruptSSTable stops transports only for `die` and `stop_paranoid`, so under `stop` the node keeps serving and every read of the corrupt row repeats the allocation. Up to concurrent_reads = 32 ReadStage threads can each hold one such array at the same time. Compaction threads and the (non-entire-sstable) stream receiver use the same deserializer and can add to it. The stream receiver gets a sender's corrupt sections through CassandraStreamReader.

Rough size at defaults: 32 × 256 MiB = 8 GiB of live humongous arrays. That equals the whole default heap on a 16 GiB host (min(RAM/2, 15.5 GiB)) and is half of the maximum default heap, before the normal working set is counted. Needs a corrupted length vint whose value is in (rowSize, 256 MiB], e.g. any 4-byte vint (lengths below 2^28). This is corrupt input; it is reachable through bit rot or a corrupt imported or streamed sstable.

**Where:** ByteArrayAccessor.java:100-104 (allocation before readFully), TrackedDataInputPlus.java:184-187 (the limit check, reached only inside readFully), AbstractType.java:582-600 (l bounded only by maxValueSize at :594), Cell.java:331-339 (value read with DatabaseDescriptor.getMaxValueSize()), UnfilteredSerializer.java:585-587 and :652/:685, Config.java:310 (max_value_size 256MiB), conf/cassandra.yaml:471 (disk_failure_policy: stop), DefaultFSErrorHandler.java:43-56 (CorruptSSTableException stops transports only for die/stop_paranoid), conf/cassandra.yaml:722 (concurrent_reads: 32).

## OC-582

**Case file:** `rowsize-checkcanread-bytesread--autonomous` · **Agent:** autonomous · **Patterns:** —

**Summary:** Well-formed cell values of up to max_value_size (256 MiB) are reachable through bulk-loaded sstables (CQLSSTableWriter / sstableloader / nodetool import), which bypass max_mutation_size (16 MiB). Every read allocates the whole value on the replica and copies it again into the response: ~0.5 GiB per read; 16-32 concurrent reads reach 8-16 GiB.

What holds the memory: for a well-formed value, Cell.serializer.deserialize → AbstractType.read → ByteArrayAccessor.read allocates byte[l], where l is the value's full length. The rowSize limit equals the row's size, so it never binds. The value is then serialized into the read response and, at the coordinator, into the CQL result message, giving at least one more full copy. The value is not skipped even when the query does not select it: stage 4 observed that `SELECT k` still allocated the whole value, because the CQL column filter treats the column as queried (DeserializationHelper.canSkipValue false).

Why nothing stops it: on the CQL write path a value is limited by max_mutation_size (commitlog_segment_size/2 = 16 MiB, Mutation.validateSize via CommitLog.java:304) and the 16 MiB native frame. Sstables built offline with CQLSSTableWriter / AbstractSSTableSimpleWriter never pass through the commit log or that check; the writer has no max_value_size or guardrail check. They are then loaded with sstableloader (entire-sstable streaming, no deserialization) or nodetool import. On read, the only bound is max_value_size = 256 MiB, and column_value_size guardrails are off by default.

Rough size at defaults: one read of a 256 MiB value costs ~256 MiB on the replica plus ~256 MiB or more for the response and result copies. 16-32 concurrent reads (concurrent_reads = 32) need 8-16 GiB, against a default heap of min(RAM/2, 15.5 GiB).

**Where:** ByteArrayAccessor.java:100-104, AbstractType.java:582-600 (only max_value_size, :594), Cell.java:331-339 (no skip unless canSkipValue), DeserializationHelper.java:109-112, Config.java:310 (max_value_size 256MiB), Config.java:915-916 (column_value_size_* null), DatabaseDescriptor.java:898-899 and CommitLog.java:304 (16 MiB cap only on the commit-log write path), AbstractSSTableSimpleWriter.java:112 (offline writer builds an sstable header with no size check), conf/cassandra.yaml:722 (concurrent_reads: 32).

## OC-583

**Case file:** `rowsize-checkcanread-bytesread--autonomous` · **Agent:** guided · **Patterns:** CP-13, CP-11, CP-7, CP-6

**Summary:** Corrupt sstable value length: each read allocates a byte[] of the encoded length (up to max_value_size, 256 MiB by default) before the per-row limit checks it. Default disk_failure_policy `stop` leaves the node serving, so every read of the bad partition does this again. With 32 concurrent reads that is 32 x 256 MiB = 8 GiB, which is the whole heap on a 16 GiB host. Stage 4 measured 200 MiB per read (G1 humongous pauses at 773M of 1G).

Holder: the cell value array built by `ByteArrayAccessor.read`. `byte[] b = new byte[length]` runs at ByteArrayAccessor.java:102, and only after that does `in.readFully(b)` (:103) reach `TrackedDataInputPlus.checkCanRead` (TrackedDataInputPlus.java:184-187), the per-row limit `limit = rowSize` set at UnfilteredSerializer.java:585-587. The only check that runs before the allocation is the per-value `l > maxValueSize` test (AbstractType.java:594). It is called from Cell.java:339 with `DatabaseDescriptor.getMaxValueSize()`, default 256 MiB (Config.java:310); max_value_size can be set up to 2047 MiB (DatabaseDescriptor.java:944-948).

Why nothing stops it: the row limit is the row's own serialized size. It can only throw EOFException after the array exists. Stage 4 measured exactly this: one byte[] of V + 16 B per corrupt read (104,857,616 B and 209,715,216 B), the same for L = 3 MiB and 6 MiB, with the EOF thrown one line below the allocation. With the default `disk_failure_policy: stop` (conf/cassandra.yaml:471), `DefaultFSErrorHandler.handleCorruptSSTable` stops transports only for `die` and `stop_paranoid` (DefaultFSErrorHandler.java:49-56). The node keeps serving, and each later read of the partition allocates again. No limit covers the readers taken together: each ReadStage thread (concurrent_reads = 32, Config.java:179; conf/cassandra.yaml:722) can hold one such array, and so can each compaction or validation reader of the sstable. Streamed rows also go through the sstable header and the same wrapper and allocation order (CassandraStreamReader.StreamDeserializer, CassandraStreamReader.java:204 onwards), so a peer streaming a corrupt section has the same effect on the receiver.

Size at defaults: 256 MiB per in-flight read of the corrupt value. 32 concurrent reads of a hot partition give about 8 GiB. That is the whole heap at the default sizing of min(1/2 RAM, 15.5 GiB) (conf/cassandra-env.sh:50-66) on a 16 GiB host, and twice the heap on 8 GiB. Stage 4 already showed humongous-allocation GC pauses with the heap at 769-773M of 1024M after three sequential 200 MiB reads. Requires corrupt on-disk or streamed input.

**Where:** ByteArrayAccessor.java:102; TrackedDataInputPlus.java:184; AbstractType.java:594; Cell.java:339; UnfilteredSerializer.java:587; Config.java:179, :310; DefaultFSErrorHandler.java:49-56; conf/cassandra.yaml:471.

## OC-584

**Case file:** `rowsize-checkcanread-bytesread--autonomous` · **Agent:** guided · **Patterns:** CP-12, CP-8, CP-7

**Summary:** One CQL row is built whole on the heap on every read and every compaction. Its limit (rowSize) is just the row's stored size, and nothing caps the total: collection guardrails are off and check only the elements a mutation adds. Appends of about 15 MiB each (under max_mutation_size, 16 MiB) build a row of about 1 GiB in 64 writes. 32 concurrent reads of that row would hold about 32 GiB.

Holder: the Row.Builder BTree of all cells of one row (BTreeRow.Builder, BTreeRow.java:743, :839), filled by `deserializeRowBody` (UnfilteredSerializer.java:564-640). `readComplexColumn` loops over every cell of a collection (`count = in.readUnsignedVInt32()`, :677-683). Each cell value is a separate byte[] of up to max_value_size (Cell.java:339).

Why nothing stops it: the case's limit, `limit = rowSize` (UnfilteredSerializer.java:585-587), is the row's own serialized size as written. It bounds only the bytes consumed from the input for that row, not how large the row may be. Stage 3 and stage 4 agree it caps nothing. A row grows across mutations: each mutation is at most max_mutation_size = commitlog_segment_size/2 = 16 MiB (DatabaseDescriptor.java:898-899; Config.java:397), but list, set and map appends and separate column updates merge into one row in the memtable and in compaction. The collection guardrails check only the elements the current mutation adds (Lists.java:527-540, Maps.java:476-488, with the comment "without considering already existent elements"). They are off by default: `collection_size_*_threshold = null` and `items_per_collection_*_threshold = -1` (Config.java:917-920). The sstable-write check returns at once when both are disabled (SortedTableWriter.java:395-396). `partition_size_*_threshold` is also null (Config.java:910-911). Paging splits a partition by rows or clusterings, never inside a row, so a single row comes back from the sstable whole. Stage 4 saw that even `SELECT k` deserialized the whole value of `v` (results section 4.2, item 6), so a narrow query does not avoid it either.

Size at defaults: 64 map or list appends of about 15 MiB give a row of about 1 GiB. Each read, and each compaction or validation of that partition, builds it whole: 1 GiB of heap per reader. 32 concurrent reads (concurrent_reads = 32, Config.java:179) of the hot row hold about 32 GiB, against a default heap of at most 15.5 GiB (conf/cassandra-env.sh:50-66). Even a few concurrent readers fill a typical 8 GiB heap.

**Where:** UnfilteredSerializer.java:585-587, :677-683; Cell.java:339; BTreeRow.java:839; Lists.java:527-540; Maps.java:476-488; Config.java:179, :397, :910-911, :917-920; DatabaseDescriptor.java:898-899; SortedTableWriter.java:395-396.

## OC-585

**Case file:** `profileload-capacity-beginsampling-capacity--autonomous` · **Agent:** autonomous · **Patterns:** —

**Summary:** Read-sampler entries (READ_ROW_COUNT, READ_TOMBSTONE_COUNT, READ_SSTABLE_COUNT queues and the READS StreamSummary) keep the partition-key ByteBuffer of reads served from the memtable. With the default heap_buffers this is a slice of a 1 MiB on-heap slab region, so each retained sample keeps its whole 1 MiB region alive after the memtable is flushed. Capacity counts entries, not bytes, and after profileload returns the leftover entries stay until the next beginSampling: up to ~1000 regions (~1 GiB) per table at -s 256, ~4 GiB at -s 1024. The ceiling is the distinct regions of flushed memtables (memtable_heap_space = 1/4 heap each). None of it is counted against memtable_heap_space.

What holds the memory: the samplers keep the partition key's ByteBuffer by reference.
- READ_ROW_COUNT and READ_TOMBSTONE_COUNT sample currentKey.getKey() (src/java/org/apache/cassandra/db/ReadCommand.java:545, 611-615).
- READ_SSTABLE_COUNT and the READS frequency sampler sample merged.partitionKey().getKey() or result.partitionKey().getKey() (src/java/org/apache/cassandra/db/SinglePartitionReadCommand.java:914-917, 1055-1056).
- MaxSampler stores the item as-is in new Sample(item, value, 0) (src/java/org/apache/cassandra/metrics/MaxSampler.java:69). FrequencySampler passes it to StreamSummary.offer (src/java/org/apache/cassandra/metrics/FrequencySampler.java:87).

Why that key is a slice of a 1 MiB slab region:
- The merged iterator takes its key from the first input iterator (src/java/org/apache/cassandra/db/rows/UnfilteredRowIterators.java:134, 411).
- Memtables are queried before sstables (SinglePartitionReadCommand.java:718-720).
- The memtable iterator's key is AbstractBTreePartition.this.partitionKey() (src/java/org/apache/cassandra/db/partitions/AbstractBTreePartition.java:198). That is allocator.ensureOnHeap().applyToPartitionKey(key) (src/java/org/apache/cassandra/db/partitions/AtomicBTreePartition.java:202-204).
- For heap_buffers, the shipped default (conf/cassandra.yaml:825; AbstractAllocatorMemtable.java:100-102), SlabPool gives allocateOnHeap = true (src/java/org/apache/cassandra/utils/memory/SlabPool.java:28, 33). That makes ensureOnHeap a NoOp that returns the same key (src/java/org/apache/cassandra/utils/memory/SlabAllocator.java:70; EnsureOnHeap.java:127-130).
- The memtable key itself is cloned into the slab on insert (src/java/org/apache/cassandra/db/memtable/SkipListMemtable.java:115-118). The clone is data.duplicate().position(..).limit(..) of a ByteBuffer.allocate(1 MiB) region (SlabAllocator.java:51, 139, 197-205; keys up to 128 KiB are slabbed, :52).
- So a retained Sample makes its whole 1 MiB region reachable.

Why nothing stops it:
- The capacity counts entries, not bytes (MaxSampler.java:45-47, 74).
- After the memtable flushes, the region drops out of memtable accounting while staying on heap. The next memtable then fills memtable_heap_space again.
- Retention is not bounded in time. finishSampling polls only count+2 entries and leaves the rest of the queue referenced (MaxSampler.java:52-63). FrequencySampler.finishSampling keeps its summary (FrequencySampler.java:67-78). Both last until the next beginSampling on that sampler (MaxSampler.java:45; FrequencySampler.java:60). After a one-off nodetool profileload, that can be indefinitely.
- Admission is easy. Below capacity every positive value is admitted (MaxSampler.java:74), and any read with live rows qualifies for READ_ROW_COUNT.
- profileload with no keyspace samples every table, system tables included, with all 8 samplers by default (tools/nodetool/ProfileLoad.java:59; StorageService.java:6533-6542; SamplingManager getTables via ColumnFamilyStore.all(), ColumnFamilyStore.java:2584-2592). That multiplies the pinned amount per table.

Rough size at defaults (-s 256):
- Per table, up to 3 MaxSampler queues x 256 + StreamSummary 256 = ~1024 retained keys, i.e. up to ~1024 distinct 1 MiB regions (~1 GiB). With -s 1024, up to ~4096.
- The ceiling is the number of regions in flushed memtables, about memtable_heap_space (1/4 heap) per flushed memtable. On an 8 GiB heap that is 2 GiB = 2048 regions. 1024 keys spread at random over 2048 regions touch ~800 regions, ~800 MiB.
- This is on top of the live memtables' own 1/4 heap.

Contrast: stage 4 measured 116 B per entry only because its writes and keys were not memtable-sourced (WRITE_SIZE uses the incoming update's own key, ColumnFamilyStore.java:1481-1482).

## OC-586

**Case file:** `profileload-capacity-beginsampling-capacity--autonomous` · **Agent:** autonomous · **Patterns:** —

**Summary:** The capacity has no server-side maximum on the blocking JMX paths (ColumnFamilyStoreMBean.beginLocalSampling, StorageServiceMBean.samplePartitions). A JMX caller can pass e.g. Integer.MAX_VALUE, and then every positive sample is kept for the whole duration (int ms, up to ~24.8 days). At ~116 B per entry (measured), 10k writes/s for 1 h keeps ~36M entries, ~4.2 GB for WRITE_SIZE alone on one table. The other samplers and tables add to that. The 1024 limit is enforced only in nodetool and in the scheduled path.

Where the limit is enforced:
- nodetool rejects -s > 1024 on the client side (src/java/org/apache/cassandra/tools/nodetool/ProfileLoad.java:79).
- Server side, only startSamplingPartitions checks 0 < capacity <= 1024 (src/java/org/apache/cassandra/service/StorageService.java:6577-6583).

The paths that accept any int:
- ColumnFamilyStore.beginLocalSampling passes the JMX argument straight through (src/java/org/apache/cassandra/db/ColumnFamilyStore.java:2056-2059).
- StorageService.samplePartitions does the same for every table (StorageService.java:6533-6542).
- MaxSampler.beginSampling then builds maximumSize(Math.max(1, capacity)) (src/java/org/apache/cassandra/metrics/MaxSampler.java:45-47), and permitsValue admits whenever queue.size() < capacity (MaxSampler.java:74). With a huge capacity, every sample with value > 0 is added (MaxSampler.java:66-70).
- WRITE_SIZE offers one sample per write with value update.dataSize() > 0 (ColumnFamilyStore.java:1481-1482).
- FrequencySampler builds new StreamSummary(capacity) with the same value (src/java/org/apache/cassandra/metrics/FrequencySampler.java:60). It keeps one counter per distinct key, without bound.
- The duration is an int in ms (ColumnFamilyStore.java:2056), so up to ~24.8 days.

Stage 4 evidence:
- JMX accepted capacity 2,000,000.
- One table's WRITE_SIZE kept all 1,000,000 samples = 116.5 MB of heap, i.e. 116 B per entry.

Rough size:
- 10k writes/s x 3600 s = 36M entries x 116 B = ~4.2 GB for one sampler on one table.
- READ_ROW_COUNT, READ_SSTABLE_COUNT, LOCAL_READ_TIME and the frequency samplers add their own entries.
- samplePartitions with keyspace null multiplies this across all tables (StorageService.java:6533-6542).
- Nothing evicts until finishSampling or the end of the window, and after finish the leftover queue stays referenced (MaxSampler.java:52-63).

## OC-587

**Case file:** `profileload-capacity-beginsampling-capacity--autonomous` · **Agent:** autonomous · **Patterns:** —

**Summary:** LOCAL_READ_TIME entries are full CQL strings from command.toCQLString(). They include the hex-rendered partition key (up to 64 KiB key, ~128 KiB of chars) and every clustering value of the filter (IN lists). The capacity limits only the number of strings, not their size, and the sampler keeps the slowest reads, which tend to be the largest queries. Example: a 500-value IN of 200-byte blob clusterings is ~200 KB per string, so ~50 MB per table at -s 256 and ~200 MB at -s 1024; profiling all tables multiplies that.

What holds the memory:
- When LOCAL_READ_TIME is enabled, every local read builds String cql = command.toCQLString() and samples it with its latency in microseconds (src/java/org/apache/cassandra/db/ReadExecutionController.java:134, 210-211, 236-242).
- The string contains the WHERE clause: the partition key rendered as CQL (src/java/org/apache/cassandra/db/SinglePartitionReadCommand.java:1228) plus clusteringIndexFilter().toCQLString(...) (SinglePartitionReadCommand.java:1230). For a names filter that lists every selected clustering value.
- The topLocalReadQueryTime MaxSampler<String> stores these strings (src/java/org/apache/cassandra/metrics/TableMetrics.java:447).

Why nothing stops it:
- The bound is maximumSize(max(1, capacity)) entries (src/java/org/apache/cassandra/metrics/MaxSampler.java:45-47), with no byte limit.
- The queue keeps the largest values, here the slowest reads (MaxSampler.java:37, 74). Slow reads correlate with long IN lists or large keys, so the retained set is biased toward the biggest strings.
- Retention continues after finishSampling: only count+2 entries are polled (MaxSampler.java:52-63).
- Up to 1000 pending insert tasks in samplerExecutor can each hold one such string, outside the cap (src/java/org/apache/cassandra/metrics/Sampler.java:100-113).

Rough size:
- A blob key renders as hex, 2 chars per byte. A partition key of up to 65535 bytes gives a string of ~128 KiB.
- A clustering IN of 500 blob values x 200 B gives ~200 KB per string. The whole list stays in the string because the single-partition names-filter command keeps all clusterings.
- At -s 256: 256 x 200 KB = ~50 MB per table. At -s 1024: ~200 MB per table.
- nodetool profileload with no table samples all tables with all samplers by default (tools/nodetool/ProfileLoad.java:59; StorageService.java:6533-6542), which multiplies this per table with such reads.

## OC-588

**Case file:** `profileload-capacity-beginsampling-capacity--autonomous` · **Agent:** guided · **Patterns:** CP-1, CP-3, CP-14, CP-7, CP-8

**Summary:** read-path samplers (READS, READ_ROW_COUNT, READ_TOMBSTONE_COUNT, READ_SSTABLE_COUNT) keep the memtable's partition-key ByteBuffer, which under the default memtable_allocation_type heap_buffers is a slice of a 1 MiB on-heap slab region; each counted sample (~116 B) can pin a whole 1 MiB region after the memtable is flushed and outside memtable_heap_space, and the samples stay after finishSampling; at the nodetool default -s 256, up to ~256 MiB per hot table (1 GiB at -s 1024), times the hot tables in an all-tables profileload

Holder: the Sample.value ByteBuffers kept in MaxSampler.queue (MinMaxPriorityQueue) and in FrequencySampler.summary (StreamSummary) of the read-side samplers, plus up to 1000 pending samplerExecutor tasks that reference the same buffers.

Why the limit does not bound it: the capacity counts samples. Stage 4 measured each sample at ~116 B, but on the write path only, where the key is an exact copy (CBUtil.readBoundValue / ByteBufferUtil.read copy the bytes). On the read path the sampled key comes from the memtable. SkipListMemtable clones a partition's key into the memtable allocator. With the default heap_buffers allocator that is a SlabAllocator region: Region.allocate returns data.duplicate().position(off).limit(off+size) of a 1 MiB heap ByteBuffer. AtomicBTreePartition.partitionKey() goes through allocator.ensureOnHeap(), which is EnsureOnHeap.NoOp for on-heap slabs, so the slice is returned as is. A read adds the memtable iterators first, and the merged iterator's partitionKey() is the first iterator's. So for every read that hits a partition still in a memtable, the key handed to addSample is the slab slice. The samplers store it unchanged (new Sample(item, ...), summary.offer(item, ...)), so each retained sample pins its region's whole 1 MiB byte[]. The code already knows keys can be slices: TopPartitionTracker calls key.retainable() (DecoratedKey.retainable copies when ByteBufferUtil.canMinimize) before keeping a key. The samplers do not.

When the memtable flushes, the allocator is discarded and its regions leave the memtable_heap_space accounting (1/4 of the heap by default). The pinned regions stay reachable, outside every budget, while the next memtable fills that budget again (CP-3, CP-8). After the session, MaxSampler.finishSampling only polls count+2 entries and never clears the queue; FrequencySampler.finishSampling keeps summary. The remaining entries (about 256 - 10 - 2 at the defaults, all 256 in the StreamSummary) and their regions stay referenced until the next beginSampling on that sampler and table, which may never come (CP-14).

Rough size at defaults: with -s 256 and -k 10, a hot table whose memtable spans hundreds of 1 MiB regions (a flush at about 1/3 of a 2 GiB memtable space on an 8 GiB heap is roughly 680 regions) can pin about 200-256 distinct regions, i.e. ~200-256 MiB per table. Up to 1 GiB per table at -s 1024 (bounded by the regions that table's memtables used during the window). `nodetool profileload` with no arguments samples every table with every sampler (SamplingManager.getTables(null, null) returns ColumnFamilyStore.all()), so this multiplies by the number of hot tables (CP-7). Counted ~116 B against held ~1 MiB per sample is up to ~9000x (CP-1). The 1000-task samplerExecutor queue (a count limit, not bytes) can transiently pin up to ~1000 more regions.

**Where:** conf/cassandra.yaml:825 (memtable_allocation_type: heap_buffers); db/memtable/AbstractAllocatorMemtable.java:100-102 (heap_buffers -> SlabPool on heap); utils/memory/SlabAllocator.java:51 (REGION_SIZE 1 MiB), :52 and :92 (only clones > 128 KiB skip the region; keys are <= 64 KiB), :70 (NoOp ensureOnHeap when on-heap only), :139 (ByteBuffer.allocate(REGION_SIZE)), :197-205 (Region.allocate returns a duplicate slice); db/memtable/SkipListMemtable.java:115-116 (cloneKey = cloner.clone(update.partitionKey())); utils/memory/ByteBufferCloner.java:44-47; db/partitions/AtomicBTreePartition.java:202-205; utils/memory/EnsureOnHeap.java:127-130 (NoOp returns the key); db/SinglePartitionReadCommand.java:718-731 (memtable iterators added first), :913-917 (merged.partitionKey() sampled into READS and READ_SSTABLE_COUNT), :959-970 and :1054-1056 (timestamp-order path, result built from the memtable iterator first); db/ReadCommand.java:545, :612, :615 (READ_ROW_COUNT and READ_TOMBSTONE_COUNT sample currentKey = iter.partitionKey()), :986-989; db/rows/UnfilteredRowIterators.java:411 (merged key = iterators.get(0).partitionKey()); metrics/MaxSampler.java:52-63 (queue not cleared), :69 (stores item as is); metrics/FrequencySampler.java:59-61, :81-87 (summary kept; item stored as is); metrics/Sampler.java:100-113 (1000-task executor queue); metrics/TopPartitionTracker.java:240 and db/DecoratedKey.java:202-207 (the retainable() copy the samplers skip); metrics/SamplingManager.java:80-84 (all tables).

## OC-589

**Case file:** `profileload-capacity-beginsampling-capacity--autonomous` · **Agent:** guided · **Patterns:** CP-16, CP-10, CP-6, CP-7

**Summary:** the JMX operations beginLocalSampling / samplePartitions accept any int capacity (the 1024 maximum is checked only in nodetool and startSamplingPartitions); MaxSampler adds one Sample per positive sampled operation with no per-key dedupe, so above the cap the only stop is the heap; stage 4 measured 116.5 MB for 1,000,000 writes with C = 2,000,000 accepted over JMX, about 4 GB per hour at 10k writes/s per sampler and table, for a duration of up to ~24.8 days

Holder: the MaxSampler queue (Sample, key HeapByteBuffer, key byte[], queue slot, about 116 B per entry as measured in stage 4) and, for the frequency samplers, StreamSummary(capacity) with one counter per distinct key.

Why nothing stops it: the capacity goes straight into MinMaxPriorityQueue.maximumSize(Math.max(1, capacity)) and into new StreamSummary<>(capacity). Only the scheduled path (StorageService.startSamplingPartitions: 0 < capacity <= 1024) and nodetool (ProfileLoad: capacity <= 1024) check an upper bound. ColumnFamilyStoreMBean.beginLocalSampling (ColumnFamilyStore.beginLocalSampling) and StorageService.samplePartitions pass any int through (CP-16, CP-10). The stage-4 cluster tier showed this: JMX accepted C = 2,000,000, and after 1,000,000 writes 1,000,000 live Sampler$Sample objects held 116.5 MB, released only when the queue was replaced.

The container does not dedupe by key, so its growth follows the sampled-operation count, not the key count. permitsValue admits every positive value while queue.size() < capacity, so with a huge capacity every write (WRITE_SIZE), every read with rows or tombstones, and every memtable or sstable read is kept. Nothing refuses short of the JVM's OutOfMemoryError (CP-6). The duration is an int in ms (up to ~24.8 days), and a session whose duration expires without finishSampling keeps its queue. samplePartitions with no keyspace starts this on every table for each named sampler (CP-7). The JMX defaults are LOCAL_JMX=yes with no auth on 127.0.0.1:7199, so a local tool or script can start it.

Rough size at defaults: about 116 B per write-path sample (measured), so 10k writes/s gives ~1.2 MB/s, about 4 GB/hour for one WRITE_SIZE sampler on one table. That is enough to fill an auto-sized heap (at most 8 GB) in about 2 hours, sooner with several tables or samplers. On read samplers each entry can also pin a 1 MiB slab region (the heap_buffers candidate above), so the bound is far lower.

**Where:** metrics/MaxSampler.java:40-49 (maximumSize(Math.max(1, capacity)), no upper bound), :66-75 (insert and permitsValue; one new Sample per admitted value); metrics/FrequencySampler.java:55-61 (new StreamSummary<>(capacity)); db/ColumnFamilyStore.java:2055-2059 (beginLocalSampling, no check); db/ColumnFamilyStoreMBean.java:302; service/StorageService.java:6533-6542 (samplePartitions, no check) vs :6577-6583 (the only server-side 1024 check, scheduled path); tools/nodetool/ProfileLoad.java:76-79 (client-side 1024 check); metrics/SamplingManager.java:80-84 (null keyspace = all tables); stage-4 results section 4.1 cluster table (C = 2,000,000: 1,000,000 samples, 116.5 MB).

## OC-590

**Case file:** `profileload-capacity-beginsampling-capacity--autonomous` · **Agent:** guided · **Patterns:** CP-2, CP-12, CP-14, CP-5

**Summary:** LOCAL_READ_TIME MaxSampler keeps the full CQL string of each of the slowest reads (capacity counts queries, not bytes) and the string is rendered on the request thread for every read while sampling is on; a read with a large clustering IN list (the IN guardrail ships off) renders to MBs, and slow reads tend to be the large ones; e.g. a 10,000-value IN list of 100-byte blobs is ~2 MB per string, ~512 MB per table at the default -s 256 (kept after finishSampling), with up to 1000 queued tasks holding more

Holder: the String values of the LOCAL_READ_TIME MaxSampler queue, and the strings captured by the pending samplerExecutor tasks.

Why the limit does not bound it: while topLocalReadQueryTime is enabled, ReadExecutionController records createdAtNanos for every local read and, on close, calls command.toCQLString() and addSample(cql, timeMicros). The string is the whole WHERE clause: the partition key rendered as a CQL literal (DecoratedKey.toCQLString, about 2 characters per byte for blobs) and every clustering of a names filter (ClusteringIndexNamesFilter.toCQLString appends each clustering of the IN list), plus the row filter. The sampler capacity counts queries (CP-2), and the sampler is ranked by elapsed time, so it keeps the slowest reads, which are typically those with the biggest IN lists. Nothing bounds the string size: in_select_cartesian_product_warn/fail_threshold ship as -1, so only the native frame (16 MiB) limits the request. Each string is built whole in memory, with StringBuilder growth copies (CP-12). The samplerExecutor queue limit is 1000 tasks, not bytes, and each task captures its string. As in the other candidates, MaxSampler.finishSampling leaves capacity - count - 2 strings in the queue until the next session on that table (CP-14). The same command also runs on every replica that serves the read.

Rough size at defaults: a single-partition read with IN (10,000 x 100-byte blob clusterings) is ~1 MB on the wire and renders to ~2 MB of characters. The 256 slowest such reads kept per table is ~512 MB (2 GB at -s 1024). The 1000-task queue could transiently hold up to ~2 GB more if the single sampler thread falls behind. An all-tables profileload repeats this per table.

**Where:** db/ReadExecutionController.java:134 (createdAtNanos only when topLocalReadQueryTime.isEnabled()), :210-211, :236-243 (toCQLString per read, addSample); db/SinglePartitionReadCommand.java:1226-1236 (appendCQLWhereClause: key and filter); db/DecoratedKey.java:169-188; db/filter/ClusteringIndexNamesFilter.java:166-198 (renders every clustering of the IN list); metrics/TableMetrics.java (topLocalReadQueryTime = new MaxSampler<String>, value kept as is); metrics/MaxSampler.java:52-63, :66-75; metrics/Sampler.java:100-113 (withQueueLimit(1000)); conf/cassandra.yaml:2104-2105 (IN guardrail -1), :1044 (16 MiB frame).
