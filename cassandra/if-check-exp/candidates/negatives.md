# Negatives — rows read and refused

Stage-2 AI filtering verdicts for rows that **fail** one of the three rules
([`../README.md` §3.4–§3.6](../README.md#3-core-concept-the-if-check-case)).
Each entry cites the rule it failed, so a later pass doesn't re-derive the
judgment. See [`README.md`](README.md) for how rows are judged and for batch
coverage.

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

Recurring rejection reasons already established (cite these rather than
re-arguing them):

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
