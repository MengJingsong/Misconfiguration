# memtable_heap_space — Pair 01 · Summary

> **Codepath:** [memtable_heap_space-01-codepath.md](memtable_heap_space-01-codepath.md) · **Index:** [../_INDEX.md](../_INDEX.md)
>
> **Source:** apache/cassandra @ tag `cassandra-5.0.9`

## Identity

| Field | Content |
|-------|---------|
| **Entry Point ID** | MEMTABLE_HEAP_SPACE |
| **Name** | memtable_heap_space |
| **Type** | Configuration (`cassandra.yaml`) |
| **Declaration Location** | `Config.java:187` (`DataStorageSpec.IntMebibytesBound memtable_heap_space`) |
| **Default Value** | ¼ of max heap — `Runtime.getRuntime().maxMemory() / (4 * 1048576)` MiB (`DatabaseDescriptor.java:586-587`) |
| **Value Type / Size** | `int` mebibytes (stored as `IntMebibytesBound`); converted to `long` bytes via `getMemtableHeapSpaceInMiB() << 20` |
| **Description** | Global on-heap memory budget for all memtables. When usage crosses a fraction of this budget, Cassandra flushes to reclaim heap. |
| **Restriction Location** | `MemtablePool.SubPool.needsCleaning():128` → `maybeClean():131-135` (soft cleanup trigger) |
| **Pair** | 01 of 02 |

**Restriction character:** This pair is the *primary intended* restriction — a
**soft threshold** that triggers an asynchronous flush of the largest memtable
to free heap. It does **not** block writes (that is pair 02).

## Key Decision Points

1. **read:** `DatabaseDescriptor.getMemtableHeapSpaceInMiB():4055`
2. **store (limit):** `MemtablePool.SubPool.<init>():119` (`this.limit = limit`)
3. **threshold calc:** `SubPool.updateNextClean():143` (`nextClean = reclaiming + (long)(limit * cleanThreshold)`)
4. **check:** `SubPool.needsCleaning():128` (`used() > nextClean`)
5. **trigger:** `SubPool.maybeClean():133-134` (`cleaner.trigger()`)

## Enforcement

| Field | Content |
|-------|---------|
| **Enforcement Point** | `SubPool.maybeClean():131-135`, invoked from `SubPool.allocated():184` and `SubPool.acquired():189` |
| **Action on Breach** | `MemtableCleanerThread.trigger():131` → `run():73-88` → `AbstractAllocatorMemtable.flushLargestMemtable():249` → `signalFlushRequired(…, MEMTABLE_LIMIT):297` (flush largest memtable, moving its bytes to `reclaiming`) |

## Failure Mode Analysis

| Mode | Status | Notes |
|------|--------|-------|
| **Proxy Match** | ⚠ | Tracks bytes handed out by the memtable allocator (slab/heap), not actual JVM heap. Excludes non-memtable heap, slab fragmentation, and objects retained after switch. Correlated but not exact. |
| **Enforcement Point** | ⚠ | Check runs **after** `adjustAllocated(size)` records the bytes (`allocated():183-184`) — memory is already used before the trigger fires. Flush is **asynchronous**; heap keeps growing until the flush completes. |
| **Default State** | ✓ | Enabled by default. `limit` defaults to ¼ heap; `memtable_cleanup_threshold` defaults to `1/(1 + memtable_flush_writers)` (`DatabaseDescriptor.java:763`). |

## Related / Dependent Constraints

- `memtable_cleanup_threshold` — sets the fraction of `limit` at which cleaning triggers (`SubPool.cleanThreshold`).
- `memtable_flush_writers` — feeds the default cleanup threshold.
- `memtable_offheap_space` — sibling `offHeap` SubPool (separate pair scope).
- `memtable_allocation_type` — selects pool impl (SlabPool/HeapPool/NativePool); all route `heapLimit` to the on-heap SubPool.

## Bypass Potential (Target 3 seed)

- **Flush lag / throughput mismatch:** trigger only schedules a flush of the
  **single largest** memtable per cycle. If write ingest > flush throughput,
  on-heap usage grows past `limit` while flushes lag — the soft trigger cannot
  cap peak heap.
- **Post-hoc accounting:** because `maybeClean()` runs after the allocation is
  booked, a burst can overshoot before any flush is scheduled.

## Verification

| Field | Content |
|-------|---------|
| **Status** | verified (static trace) |
| **CodeQL Pattern** | n/a (manual trace; candidate for if-check pattern on `needsCleaning`) |
| **Verified By / Date** | Claude + Jingsong, 2026-09-08 |

## Notes

- Default `memtable_allocation_type = heap_buffers` → `SlabPool(heapLimit, 0, …)`, so `memtable_heap_space` maps to `MEMORY_POOL.onHeap.limit`.
- `used()` returns `allocated` only (does not subtract `reclaiming`), so in-flight flushes still count toward the trigger.
