# Negatives — rows read and refused

Rows that stage 2 ruled out **on grounds the row itself fully determines** —
no source reading, and **not** the three rules in
[`../README.md` §3.4–§3.6](../README.md#3-core-concept-the-if-check-case),
which belong to the deep-read pass. Each entry cites the row-level ground so
a later pass doesn't re-derive it. See [`README.md`](README.md) for what
stage 2 is, and [`stage2-playbook.md`](stage2-playbook.md) for the verified
reject rules.

**Rejection here is permanent in practice** — nothing re-reads this file — so
it is reserved for rows that are unambiguously not capacity checks. Anything
merely unpromising belongs in [`positives.md`](positives.md) at a low tier
instead.

**Refused, not merely unjudged.** A row dropped only because patterns (b)/(c)
are currently out of scope is *not* a negative — it goes to
[`deferred.md`](deferred.md).

## Where existing rejections live

Two things to know before adding here:

1. **Method-1 rejections stay in [`../_INDEX.md`](../_INDEX.md)'s "lines
   considered and rejected" section.** Those come from the direct-AI-search
   method and differ in kind — few, narrative, sometimes deferred rather than
   firmly refused (e.g. `ConnectionLimitHandler`). They are not moved here.
2. **Stage-2 rejections made before 2026-09-22 are also in `_INDEX.md`**, because
   this file did not exist yet. They were not migrated: the entries are
   detailed and already cross-referenced from several places, and moving them
   would churn those references for no analytical gain. They cover the
   `concurrent/`, `cache/`, `transport/` and `db/compaction/` batches (see
   `README.md`'s coverage table).

**So: `_INDEX.md` is authoritative for every rejection recorded up to
2026-09-22; this file is authoritative for stage-2 rejections from that date
on.** Either way the rule holds — one line is recorded in exactly one place.
Before adding a row here, check `_INDEX.md` first; if it is already there,
leave it there.

## Rejected rows (from 2026-09-22)

### Batch: P1 tier, corpus-wide — 2026-09-22

Deep read of the 34 P1 rows (capacity word on either side **and** compound
usage side). **22 rows rejected**, grounds below. The other 12: 4 candidates
(`positives.md`), 3 rows deferred as pattern (b)/(c) (`deferred.md`), 5
already covered by existing records.

These are **source-level rejections** — the P1 pass applied the three rules
with the code open, unlike a stage-2 row-level pass.

| Row | Check | Ground |
|---|---|---|
| `NativeAllocator$Region.allocate():273` | `newOffset + size > capacity` | Rule 2, writer-rollover. On failure the caller `trySwapRegion()` allocates a **new** region (`new Region(MemoryUtil.allocate(size), size)`), so total bytes are not bounded — only chunked. The real memtable ceiling is the already-filed `MemtablePool.tryAllocate()`. |
| `SlabAllocator$Region.allocate():201` | `newOffset + size > data.capacity()` | Rule 2, same archetype — returns `null`, caller creates a new region. |
| `MmappedRegions.updateState():208` | `segmentSize + chunk.length + 4 > MAX_SEGMENT_SIZE` | Rule 2, chunking. Starts a new mmap segment at the boundary; the whole file is mapped either way, just in more segments. |
| `BTree$LeafBuilder.copy():2575`, `:2608`, `.prepend():2700`, `$BranchBuilder.prepend():2956`, `.copyPreceding():3185` | `count + length >/<= MAX_KEYS` | Rule 2, node fanout. `MAX_KEYS = BRANCH_FACTOR - 1` is a structural tree parameter; over it the keys spill into an overflow/next node. All data is stored either way. 5 rows, one judgement. |
| `IncrementalTrieWriterPageAware.complete():167` | `nodeSize + branchSize < maxBytesPerPage` | Rule 2, page packing. Decides node placement within pages; everything is written regardless. |
| `DataLimits$CQLCounter.incrementRowCount():509`, `:511`, `$GroupByAwareCounter:986` | `++rowsCounted >= rowLimit`, `>= perPartitionLimit` | Rule 2. CQL query `LIMIT` semantics, not a resource constraint: per-row footprint is not fixed or derivable, and the limit is user-supplied per query rather than a system capacity. |
| `ExpirationDateOverflowHandling.maybeApplyExpirationDateOverflowPolicy():82` | `ttl + nowInSecs > getVersionedMaxDeletiontionTime()` | Rule 2, time-based. A timestamp-overflow guard (CASSANDRA-14092); bounds no bytes. |
| `MutationExceededMaxSizeException.makeTopKeysString():76` | `stringBuilder.length() + key.length() + 2 <= maxLength` | Rule 2, not memory-significant. Truncates the key list inside a diagnostic error message. |
| `ChecksummedDataInput.checkLimit():161` | `getPosition() + length > limit` | Rule 3. A digest-boundary guard that throws; gates no object creation. |
| `VIntCoding.getUnsignedVInt():162`, `:211` | `readerIndex + size > readerLimit` | Rule 3. Bounds reading a vint within a buffer, returning `-1`; nothing is allocated either way. |
| `ContentionStrategy.computeWaitUntilForContention():401` | `minWaitMicros + minDeltaMicros > maxWaitMicros` | Rule 2, time-based. Microsecond back-off arithmetic. |
| `DynamicList.isWellFormed():216` | `i + 1 < maxHeight` | Rule 3. Inside an invariant checker walking skip-list levels; not an allocation gate. |
| `FBUtilities.copy():1291` | `limit < buffer.length + copied` | Rule 3. Clamps the next read size into a fixed 64-byte buffer; no divergence in object creation. |
| `RepairTokenRangeSplitter.getRepairAssignmentsForKeyspace():312` | `currentAssignmentsBytes + tableAssignmentsBytes < maxBytesPerSchedule` | Rule 2/3, bucketing. Chooses whether to merge assignments or add them separately — they are added either way. |
| `RepairTokenRangeSplitter.filterRepairAssignments():360` | `bytesSoFar + getEstimatedBytes() > maxBytesPerSchedule` | Rule 2. Bounds the volume of repair *work* scheduled, not bytes resident or written by an allocation. |

### Batch: helper rows in the four previously-triaged subtrees — 2026-09-22

`HelperGuardedIfStatements.csv` restricted to `transport`, `db/compaction`,
`concurrent`, `cache`: **114 rows from 23 distinct helpers.** Judged per
helper and applied to all its call sites (see
[`stage2-playbook.md`](stage2-playbook.md)).

Outcome: **21 helpers rejected (108 rows)**, 1 cited to an existing entry
(4 rows), 1 promoted to a candidate (2 rows, now in
[`deferred.md`](deferred.md)).

| Helper (rows) | Comparison reported | Rule failed | Why |
|---|---|---|---|
| `ProtocolVersion.isGreaterOrEqualTo()` (33), `.isSmallerThan()` (12), `.isGreaterThan()` (6) | `num >=/</> num` | 1 | Native-protocol version ordering. The compared value is a protocol revision, not a capacity; nothing is bounded by it. Largest single block in the batch — 51 of 114 rows. |
| `AbstractCompactionStrategy.worthDroppingTombstones()` (12) | `... * ... > tombstoneThreshold`, `droppableRatio <= tombstoneThreshold` | 2 | Selection/bucketing archetype: decides whether an SSTable is *worth* compacting for tombstone garbage. `tombstoneThreshold` is a ratio, not a byte bound — changing it alters which SSTables are chosen, not the maximum bytes held or written. |
| `SEPExecutor.takeWorkPermit()` (6) | `taskPermits == 0`, `workPermits <= 0` | 2 | Thread-pool/permit concurrency archetype — bounds parallelism, not bytes. Same reasoning as `concurrent_compactors`. |
| `DiskBoundaries.isOutOfDate()` (6) | `currentDiskVersion != directoriesVersion`, `currentRingVersion != ringVersion` | 1 | Staleness test on cached topology versions. Not a usage-vs-capacity comparison. |
| `CompactionAwareWriter.maybeSwitchLocation()` (6) | `locationIndex < 0`, `compareTo() </> 0`, `prevIdx >= 0` | 1 | Data-directory *selection* by key range: index bookkeeping and partition-position ordering. Worth noting this method is the caller in the filed case `compaction/DataDirectory_getAvailableSpace-getWriteDirectory-availableSpace.md`, where its lack of a space check on the boundary path is recorded as that case's escape hatch — but these comparisons are not themselves capacity checks. |
| `CompactionIterator$GarbageSkippingUnfilteredRowIterator.hasNext()` (4) | `cmp </<=/>=/== 0` | 1 | Comparator-result ordering while merging rows. |
| `NonBlockingRateLimiter.tryReserve()` (3) | `nowNanos < firstAvailable` | 2 | Rate limiter — explicitly rejected by Rule 2. Bounds request *rate*, not resident or written bytes. Also time-based. |
| `TimeUUID.equals()` (4), `CompressionParams.equals()` (2), `MD5Digest.equals()` (2), `Descriptor.equals()` (1) | field-by-field `==`/`!=` | 1 | Value equality inside `equals()` implementations. |
| `SSTableReader.isRepaired()` (2) | `repairedAt != UNREPAIRED_SSTABLE` | 1 | Sentinel comparison against a marker constant. |
| `SSTableReader.mayHaveTombstones()` (1) | `getMinLocalDeletionTime() != NO_DELETION_TIME` | 1 | Sentinel comparison, as above. |
| `StorageService.shouldTraceProbablistically()` (2) | `nextDouble() < traceProbability`, `traceProbability != 0` | 1, 2 | Probabilistic trace sampling. The operand is a probability, and nothing about tracing bounds bytes. |
| `RefCountedMemory.reference()` (2) | `n <= 0` | 1 | Reference counting, not capacity — the established ref-count archetype. |
| `ClientResourceLimits$Allocator.acquire()` (1) | `0 < updateAndGet()` | 1 | Reference counting on the per-endpoint allocator's cache entry (`refCount.updateAndGet(i -> i < 0 ? i : i + 1)`), **not** the byte limit. The byte-level enforcement in this class is the separate `tryAllocate()` / `ResourceLimits.EndpointAndGlobal` path for `native_transport_max_request_data_in_flight`, which this row does not reach — see the note in `_INDEX.md` against `ConnectionLimitHandler` and the native-transport follow-up in `HANDOFF.md`. |
| `AbstractBounds.strictlyWrapsAround()` (1) | `compareTo() <= 0` | 1 | Token-range ordering. |
| `AbstractStrategyHolder$GroupedSSTableContainer.isEmpty()` (1) | `i < length` | 1 | Loop bound inside an emptiness test. |
| `CompactionTask.reduceScopeForLimitedSpace()` (1) | `size() > 1` | 1 | "Is there another SSTable left to drop from the compaction?" — scope-reduction bookkeeping. The genuine space comparison this serves is the candidate recorded in `deferred.md`, not this row. |

**Cited, not re-recorded:** `Dispatcher.hasQueueCapacity()` (4 rows,
`oldestTaskQueueTime() < ... * ...`, `threshold <= 0`) was already rejected —
see `_INDEX.md`'s rejected table (`Dispatcher.java:345`, time-based queue-age
check, fails Rule 2). One line, one place.

### Row-level grounds available to stage 2

These are decidable from the row alone — cite the ground rather than
re-arguing it:

- **Bare literal operand** — `x > 0`, `size() < 2`. An emptiness or sign
  test; a real limit has a name. 602 magnitude rows compare against `0`.
- **Ordering test** — `compareTo()` / `compare()` on either side.
- **Loop / index arithmetic** — both operands index-shaped (`i`, `idx`,
  `pos`, `length`, `size()`).
- **Method name marks it mechanical** — `validate*`, `apply*Config`,
  `serializedSize`, `hashCode`, `equals`, `compareTo`, `toString`.
- **Declaring type marks it mechanical** — `*Spec`, `*Options`, `Config*`
  for startup validation; serializer and comparator types.

### Grounds that need the source (deep-read pass, NOT stage 2)

Listed so they are not mistaken for stage-2 grounds. These are the recurring
archetypes, each a failure of one of the three rules, and they can only be
established by reading the code:

- **Thread-pool / concurrency / permit caps** — Rule 2: bounds parallelism,
  not total bytes. Precedent: `concurrent_compactors`.
- **Rate / throughput limiters** — Rule 2: bounds speed, not the ceiling.
- **Writer-switch-on-full** — Rule 2's writer-rollover edge case: the write
  proceeds either way, just chunked across more files. Precedent:
  `CommitLogSegment.java:242`, `HintsBuffer.java:190`.
- **Config validation / derived arithmetic** — startup-time checks or plain
  math, not a runtime allocation gate.
- **Selection / bucketing logic** — comparisons that choose *which* objects to
  act on, not whether to create one. Precedent: the compaction strategies.
- **Ref-counting and overflow guards** — not a usage-vs-capacity comparison.
- **Non-diverging branches** — Rule 3. Never visible in a row.
