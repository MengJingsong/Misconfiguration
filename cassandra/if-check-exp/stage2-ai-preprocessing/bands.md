# Bands — every stage-1 row, ranked

*Named `positives.md` until 2026-09-24. Renamed because the file covers all
four bands, 4,387 of them band D: nothing here is a "positive", and stage 2
has nothing to contrast one against since it stopped ruling rows out.*

**Stage 2's output.** Every stage-1 row with the band an AI session gave it and
a one-line reason. Stage 2 rules nothing out (2026-09-23), so a row that looks
impossible sits at the bottom of this list rather than absent from it. This is
a **work queue for stage 3**, not a list of qualified cases: stage 2 works only
from the row and never applies the three rules (see
[`README.md`](README.md)). A row here means "worth reading the source for, in
roughly this order" — nothing more.

**Per-row bands live in [`bands.csv`](bands.csv)**, not in this file. That file
is committed because an AI band is a judgement that cannot be regenerated from
the CSVs the way the old keyword tiers could. Columns: `uid, kind, band,
reason, model, date, batch`. A `uid` is `path:line#n` — the `#n` disambiguates
the 340 lines that carry more than one comparison — or `helper:<fqn>` for a
helper judged once and applied to all its call sites.

## Coverage

**Every stage-1 row has a band.**

| Input | Units | Banded |
|---|---|---|
| `NarrowedIfStatements.csv` | 4,489 rows | **4,489 (100%)** |
| `HelperGuardedIfStatements.csv` | 1,099 rows → 300 distinct helpers | **300 (100%)** |
| **bands.csv** | | **4789** |

## Bands

| Band | The row reads as | Units | Stage-3 order |
|---|---|---|---|
| **A** | A real capacity check — usage compared against a memory or disk limit | 134 | first |
| **B** | Plausibly a resource bound, but the row alone does not settle it | 174 | second |
| **C** | Named operands, nothing resource-shaped — the insurance band | 94 | third |
| **D** | Clearly not one: validation, ordering, loop index, bare literal, serialization | 4387 | last |

## Run

| | |
|---|---|
| Model | `claude-opus-5` |
| Dates | 2026-09-23 / 2026-09-24 |
| Batches | 37 over the un-triaged corpus, then 3 more over the four subtrees triaged in September. **The `batch` column does not identify a batch on its own** — see below. |
| Anchor check | **passed on all 40 batches** — the 8 labelled rows came back A every time |
| Accidental consistency check | 8 helpers fell into both scopes and were judged twice, in unrelated batches. **All 8 agreed.** This is the only cross-batch consistency evidence that exists, since re-judging for consistency was deliberately not done. |

Anchors are the 4 filed cases plus the 4 candidates in
[`../stage3-ai-deep-read/pending.md`](../stage3-ai-deep-read/pending.md),
repeated in every batch so separate batches share one yardstick;
`record-stage2-bands.py` refuses a batch whose anchors do not all come back A.
They also carry their own band-A rows in `bands.csv` (batch `anchors`), so the
band-A list below is complete.

**Batch labels collide across the two runs (found 2026-09-24).**
`make-stage2-batches.py` names its output `batch-NN.txt` starting from 01 in
whatever directory it is given, so the second run — the three `--consumed`
batches over the four triaged subtrees — reused `batch-01`, `batch-02` and
`batch-03`. `bands.csv` therefore holds 38 distinct `batch` values for 40
batches, and for the 703 units under those three labels **only `batch` plus
`date` identifies the run**: `2026-09-23` is the un-triaged corpus,
`2026-09-24` the subtree pass. No verdict is affected — the collision is in
the provenance label, not the judgement — but any query that groups by
`batch` alone will merge two unrelated runs. Group by `(batch, date)`
instead, or relabel the second run if the column is ever needed on its own.

## Band A, grouped by what the limit is

**Read A1 first.** Only in A1 is the limit plausibly a *named constraint* under
[`../README.md` §6.1](../README.md#61-naming) — something a user can
misconfigure. A2 and A3 are real usage-vs-capacity comparisons, but their
limits are chosen by the code, so most will fail §6.1 even though the check
itself is genuine. **Stage 2 cannot tell these apart from the row** — the split
below is a reading aid, not a verdict.

### A1 — limit traceable to configuration (65)

| Row | Reason |
|---|---|
| `QueryProcessor.java:825#1` | prepared statement size against the prepared statement cache capacity in bytes |
| `BatchStatement.java:352#1` | batch size in bytes against the configured fail threshold, rejecting the batch |
| `CounterMutation.java:94#1` | counter mutation total size against the max mutation size, rejecting the mutation |
| `Directories.java:453#1` | available disk space against the write size when choosing a write location |
| `Directories.java:551#1` | available compaction space against the amount a compaction requires |
| `Mutation.java:172#1` | mutation total size against the max mutation size, rejecting the mutation |
| `Mutation.java:451#1` | serialized mutation size against the cacheable size limit, gating whether it is cached |
| `ReadCommand.java:715#2` | query size in bytes against the configured fail threshold, aborting the read |
| `SystemKeyspace.java:1919#1` | bytes of prepared statements loaded against the configured load threshold |
| `CommitLogSegment.java:246#1` | commitlog allocation against the end of the segment buffer, gating the allocation |
| `CommitLogSegmentManagerCDC.java:200#1` | un-consumed CDC segment bytes against the configured cdc_total_space |
| `CommitLogSegmentManagerCDC.java:345#1` | CDC size tracker usage against the cdc_total_space allowance |
| `AbstractType.java:594#1` | deserialized value length against the configured max value size, rejecting the value |
| `HintsBuffer.java:152#1` | hint total size against a fraction of the hints buffer |
| `HintsBuffer.java:190#1` | hints buffer allocated bytes plus request against the buffer capacity |
| `HintsWriteExecutor.java:247#1` | hints file position against the configured max hints file size, rolling the file |
| `HintsWriter.java:237#1` | hint total size against the remaining space in the write buffer |
| `OnDiskIndexBuilder.java:167#1` | term size against the max term size, rejecting the term |
| `PerSSTableIndexWriter.java:218#1` | term size against the max term size, rejecting the term |
| `PerSSTableIndexWriter.java:247#1` | estimated index memory use against the configured max memory size, triggering a flush |
| `TrieMemIndex.java:84#1` | term size against the max term size, rejecting the term |
| `SSTableSimpleUnsortedWriter.java:110#1` | buffered size against the configured max sstable size, triggering a sync |
| `BigFormatPartitionWriter.java:113#1` | accumulated column index size against the column index cache threshold |
| `BigFormatPartitionWriter.java:171#1` | accumulated column index size exceeding the column index cache threshold |
| `RowIndexEntry.java:360#1` | row index entry size against the configured column index cache size |
| `RowIndexEntry.java:392#1` | estimated row index memory against a configured byte threshold |
| `RowIndexEntry.java:403#1` | estimated row index memory against a configured byte threshold |
| `IndexSummaryRedistribution.java:341#1` | extra space required against the remaining index summary memory pool |
| `SequentialWriter.java:227#1` | bytes since the last trickle fsync against the configured interval |
| `AbstractMessageHandler.java:464#1` | queue size against the per-connection queue capacity on the release path |
| `Message.java:817#1` | inferred message size against the configured internode max message size |
| `OutboundConnection.java:331#1` | outbound message size against the configured internode max message size |
| `OutboundConnection.java:398#1` | pending bytes against the connection's pending capacity in bytes |
| `OutboundConnection.java:416#1` | unused claimed reserve against the required reserve when acquiring capacity |
| `OutboundConnection.java:449#1` | pending bytes against the connection's pending capacity on the release path |
| `OutboundConnection.java:793#1` | message size against the configured internode max message size |
| `OutboundConnection.java:979#1` | message size against the configured internode max message size |
| `ResourceLimits.java:138#1` | concurrent resource usage against the limit in tryAllocate |
| `ResourceLimits.java:213#1` | allocated plus request against the limit in tryAllocate, the shared reserve mechanism |
| `PartitionDenylist.java:419#1` | denylisted keys against the configured per-table limit, truncating the load |
| `PartitionDenylist.java:445#1` | denylisted keys against the configured per-table limit, truncating the load |
| `StorageProxy.java:1592#2` | hints in progress against the configured maximum, rejecting the write |
| `StorageProxy.java:2492#1` | total hints size on disk against the configured per-host maximum, dropping the hint |
| `HeapUtils.java:115#1` | free disk space against the space a heap dump would require |
| `MerkleTree.java:409#1` | merkle tree size against its maximum before splitting the node |
| helper `hasDiskSpaceForCompactionsAndStreams()` | available compaction space against the amount required, behind a helper |
| helper `isStillAllocating()` | commitlog segment allocation position against the end of the buffer, behind a helper |
| helper `switchCurrentBuffer()` | allocated hint buffers against the max allocated buffers, behind a helper |
| helper `flushInternal()` | hints file position against the configured max hints file size, behind a helper |
| helper `needsCleaning()` | memtable pool used bytes against the next cleaning threshold, behind a helper |
| helper `tryAllocate()` | memtable pool allocated plus request against the pool limit, behind a helper |
| `CompactionAwareWriter.java:282#1` | available disk space against the estimated compaction write size |
| `HintsBufferPool.java:113#1` | allocated off-heap hint buffers against the max allocated buffers cap |
| `QueryController.java:449#1` | materialized key count against the configured max-keys limit |
| `TeeDataInputPlus.java:58#1` | tee buffer position plus length against the configured byte limit |
| `AbstractMessageHandler.java:419#1` | queued bytes plus incoming against the per-connection queue capacity |
| `BufferPool.java:443#1` | pool usage plus request against the memory usage threshold |
| `MemtablePool.java:156#1` | memtable pool usage plus request against the pool limit |
| `LeveledManifest.java:190#1` | level byte budget against the 2GiB type bound |
| `LeveledManifest.java:557#1` | accumulated candidate bytes against the configured max sstable size |
| `LeveledManifest.java:678#3` | accumulated bytes against the configured max sstable size when choosing the next level |
| `MajorLeveledCompactionWriter.java:75#1` | bytes written against the configured max sstable size and the level byte budget, switching writer |
| `MajorLeveledCompactionWriter.java:78#1` | bytes written against the configured max sstable size and the level byte budget, switching writer |
| `SplittingSizeTieredCompactionWriter.java:84#2` | estimated on-disk bytes written against the bytes budgeted for the current writer |
| `CQLMessageHandler.java:551#1` | message size against the configured native transport max message size |

### A2 — limit is a constant or a structural bound (30)

| Row | Reason |
|---|---|
| `BlockingQueues.java:69#1` | blocking queue size equals its capacity, gating whether an element can be enqueued |
| `BlockingQueues.java:81#1` | blocking queue size equals its capacity, gating whether an element can be enqueued |
| `BufferPool.java:1521#1` | buffer pool chunk size equals capacity when releasing the unused portion |
| `NativeCell.java:100#1` | native cell size against the 2GiB type bound, rejecting the cell |
| `IndexSummaryBuilder.java:108#1` | expected index summary entries size against the 2GiB type bound |
| `DataOutputBuffer.java:152#1` | saturated size against the buffer capacity when validating a reallocation |
| `MmappedRegions.java:170#1` | mapped segment size against the maximum segment size |
| `MmappedRegions.java:208#1` | mapped segment size against the maximum segment size |
| `DynamicList.java:113#1` | dynamic list size against its maximum before appending |
| `MerkleTree.java:1103#1` | off-heap buffer remaining against the required merkle tree size |
| `MerkleTree.java:1137#1` | off-heap buffer remaining against the required merkle tree size |
| `MerkleTree.java:1322#1` | off-heap buffer remaining against the required merkle tree size |
| `MerkleTree.java:1420#1` | off-heap buffer remaining against the required merkle tree size |
| `Accumulator.java:60#1` | accumulator insert position against the array length |
| `LightweightRecycler.java:69#1` | recycler pool size against its capacity, gating whether the buffer is retained |
| `BufferPool.java:910#1` | requested buffer size against the normal chunk size, choosing the allocation path |
| `BufferPool.java:940#1` | requested buffer size against the normal chunk size, choosing the allocation path |
| `NativeAllocator.java:144#1` | allocation size against the max cloned size, rejecting the on-heap clone |
| `NativeAllocator.java:273#1` | region offset plus size against the region capacity, gating the allocation |
| `SlabAllocator.java:92#1` | allocation size against the max cloned size, rejecting the on-heap clone |
| `SlabAllocator.java:201#1` | slab region offset plus size against the region capacity, gating the allocation |
| `OffHeapBitSet.java:43#1` | off-heap bitset word count against the 2GiB type bound |
| `StreamingTombstoneHistogramBuilder.java:452#1` | spool size against its capacity, gating whether the point is accumulated |
| helper `offer()` | blocking queue size against its capacity, behind a helper |
| helper `tryAddOrAccumulate()` | spool size against its capacity, behind a helper |
| `IndexSummaryBuilder.java:204#1` | index summary bytes plus entry size against the 2GiB type bound |
| `CaffeineCache.java:65#1` | cache entry weight against the 2GiB type bound |
| `SerializingCache.java:71#1` | cache entry serialized size against the 2GiB type bound |
| `SerializingCache.java:94#1` | cache entry serialized size against the 2GiB type bound |
| `Envelope.java:429#1` | total frame length against the maximum total length, rejecting the frame |

### A3 — grow-when-full before reallocating a buffer or array (39)

These share one argument: `size == capacity` immediately before growing a
growable structure. If stage 3 refuses one on Rule 3 or §6.1, the same
reasoning very likely disposes of the rest — **judge them as a group, not
one at a time.**

| Row | Reason |
|---|---|
| `RangeTombstoneList.java:668#1` | list size equals capacity, the grow-when-full test before reallocation |
| `SegmentRowIdOrdinalPairs.java:55#1` | row-id ordinal array size equals capacity, the grow-when-full test before reallocation |
| `CompressionMetadata.java:366#1` | compression offset count equals max count, the grow-when-full test before reallocation |
| `Walker.java:442#1` | transition byte collector position equals its length, the grow-when-full test |
| `MmappedRegions.java:383#1` | mmapped region array at its length, the grow-when-full test before reallocation |
| `AbstractReplicaCollection.java:109#1` | replica list array at its length, the grow-when-full test before reallocation |
| `PrunableArrayQueue.java:71#1` | array queue full on offer, the prune-or-grow test before reallocation |
| `HistogramBuilder.java:45#1` | histogram sample count equals the array length, the grow-when-full test |
| `BTree.java:1538#1` | btree builder element count equals the array length, the grow-when-full test |
| `ByteSourceInverse.java:424#1` | ensureCapacity: data length equals buffer length before growing the buffer |
| `Accumulator.java:75#1` | accumulator index equals the array length, the grow-when-full test |
| `RangeTombstoneList.java:685#1` | tombstone list capacity against the required new length before growing the arrays |
| `RangeTombstoneList.java:696#1` | tombstone list capacity against the required new length before growing the arrays |
| `CompressedInputStream.java:144#1` | input stream buffer capacity against the chunk length before reallocating |
| `Stack.java:94#1` | transform stack array length against the required new count before growing |
| `InMemoryReadTrie.java:501#1` | backtracking array at its length, the grow-when-full test |
| `InMemoryTrie.java:670#1` | apply-state array at its length, the grow-when-full test |
| `TriePathReconstructor.java:33#1` | trie path reconstructor buffer at its length, the grow-when-full test |
| `TriePathReconstructor.java:41#1` | trie path reconstructor buffer at its length, the grow-when-full test |
| `CompressedChecksummedDataInput.java:118#1` | input and writer buffer capacity against the required size before reallocating |
| `CompressedChecksummedDataInput.java:134#1` | input and writer buffer capacity against the required size before reallocating |
| `CompressedHintsWriter.java:53#1` | input and writer buffer capacity against the required size before reallocating |
| `EncryptedChecksummedDataInput.java:126#1` | input and writer buffer capacity against the required size before reallocating |
| `CompressedSequentialWriter.java:247#1` | writer buffer capacity against the chunk size before reallocating |
| `DataOutputBuffer.java:166#1` | buffer capacity against the growth target when calculating the new size |
| `ThreadLocalByteBufferHolder.java:74#1` | cached thread-local buffer capacity against the requested size, reallocating |
| `FrameDecoder.java:375#1` | frame decoder buffer capacity against the required size before reallocating |
| `FrameDecoder.java:393#1` | frame decoder buffer capacity against the required size before reallocating |
| `EncryptionUtils.java:134#1` | decrypt buffer capacity against the required block header size, reallocating |
| `EncryptionUtils.java:142#1` | decrypt buffer capacity against the required block header size, reallocating |
| `ByteBufferUtil.java:815#1` | buffer capacity against the required output length before reallocating |
| `ByteBufferUtil.java:817#1` | buffer capacity against the required output length before reallocating |
| `LongTimSort.java:821#1` | sort buffer length against the required minimum capacity before growing |
| `BTree.java:1573#1` | btree builder array length against the required size before growing |
| `BTree.java:1600#1` | btree builder array length against the required size before growing |
| `BTreeSet.java:133#1` | btree set array length against the required size before allocating |
| `BTreeSet.java:477#1` | btree range array length against the required size before allocating |
| `CBUtil.java:105#1` | decode buffer capacity against the required size before reallocating |
| `Flusher.java:282#1` | flush buffer remaining against the max framed payload size before allocating |

## Band B (174)

Not listed here row by row — query [`bands.csv`](bands.csv). Recurring themes:
warn-rather-than-fail thresholds (batch size, query size, tombstone count),
count-based guards that proxy for memory, buffer-remaining tests before a typed
read or write, size-based routing decisions (large vs small message, sparse vs
dense block), connection and compaction count limits, and repair byte budgets.

## Where a row goes after stage 3 reads it

Stage 2 hands a row forward; what happens next is recorded by **stage 3**,
not here (verdicts file with the stage that judged them):

| Outcome | Recorded in |
|---|---|
| Qualified, written up | [`../stage3-ai-deep-read/cases/`](../stage3-ai-deep-read/cases/) + [`_INDEX.md`](../stage3-ai-deep-read/_INDEX.md) |
| Qualified, not yet written up | [`../stage3-ai-deep-read/pending.md`](../stage3-ai-deep-read/pending.md) |
| Refused against the three rules | [`../stage3-ai-deep-read/rejected.md`](../stage3-ai-deep-read/rejected.md) |
| Pattern (b)/(c), parked | [`../stage3-ai-deep-read/deferred.md`](../stage3-ai-deep-read/deferred.md) |

**Nothing in this file is a finding.** Some band-A rows are already refused:
`NativeAllocator$Region.allocate():273` and `SlabAllocator$Region.allocate():201`
were read and rejected in the capacity-word pass and are in `rejected.md`. Stage 2 ranked
them high anyway, correctly — the ground for refusing them is Rule 2, which no
row can show. The four subtrees banded last also carry older
verdicts in `../stage3-ai-deep-read/rejected.md`; a band never overrides a
verdict already made with the source open.
