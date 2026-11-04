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
| **Declaration Location** | [`Config.java:187`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/Config.java#L187) (`DataStorageSpec.IntMebibytesBound memtable_heap_space`) |
| **Default Value** | ¼ of max heap — `Runtime.getRuntime().maxMemory() / (4 * 1048576)` MiB ([`DatabaseDescriptor.java:586-587`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/DatabaseDescriptor.java#L586-L587)) |
| **Value Type / Size** | `int` mebibytes (stored as `IntMebibytesBound`); converted to `long` bytes via `getMemtableHeapSpaceInMiB() << 20` |
| **Description** | Global on-heap memory budget for all memtables. When usage crosses a fraction of this budget, Cassandra flushes to reclaim heap. |
| **Restriction Location** | [`MemtablePool.SubPool.needsCleaning():128`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/utils/memory/MemtablePool.java#L128) → [`maybeClean():131-135`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/utils/memory/MemtablePool.java#L131-L135) (soft cleanup trigger) |
| **Pair** | 01 of 02 |

**Restriction character:** This pair is the *primary intended* restriction — a
**soft threshold** that triggers an asynchronous flush of the largest memtable
to free heap. It does **not** block writes (that is pair 02).

## Key Decision Points

1. **read:** [`DatabaseDescriptor.getMemtableHeapSpaceInMiB():4055`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/DatabaseDescriptor.java#L4055)
2. **store (limit):** [`MemtablePool.SubPool.<init>():119`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/utils/memory/MemtablePool.java#L119) (`this.limit = limit`)
3. **threshold calc:** [`SubPool.updateNextClean():143`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/utils/memory/MemtablePool.java#L143) (`nextClean = reclaiming + (long)(limit * cleanThreshold)`)
4. **check:** [`SubPool.needsCleaning():128`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/utils/memory/MemtablePool.java#L128) (`used() > nextClean`)
5. **trigger:** [`SubPool.maybeClean():133-134`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/utils/memory/MemtablePool.java#L133-L134) (`cleaner.trigger()`)

## Enforcement

| Field | Content |
|-------|---------|
| **Enforcement Point** | [`SubPool.maybeClean():131-135`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/utils/memory/MemtablePool.java#L131-L135), invoked from [`SubPool.allocated():184`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/utils/memory/MemtablePool.java#L184) and [`SubPool.acquired():189`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/utils/memory/MemtablePool.java#L189) |
| **Action on Breach** | [`MemtableCleanerThread.trigger():131`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/utils/memory/MemtableCleanerThread.java#L131) → [`run():71-89`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/utils/memory/MemtableCleanerThread.java#L71-L89) → [`AbstractAllocatorMemtable.flushLargestMemtable():249`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/memtable/AbstractAllocatorMemtable.java#L249) → [`signalFlushRequired(…, MEMTABLE_LIMIT):297`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/memtable/AbstractAllocatorMemtable.java#L297) (flush largest memtable, moving its bytes to `reclaiming`) |

## Failure Mode Analysis

| Mode | Status | Notes |
|------|--------|-------|
| **Proxy Match** | ⚠ | `allocated` is the memtable's **estimated on-heap footprint** — cloned data **+ metadata** charged via `unsharedHeapSize()` / `ROW_OVERHEAD_HEAP_SIZE` ([`BTreePartitionUpdater.onAllocatedOnHeap():175-182`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/partitions/BTreePartitionUpdater.java#L175-L182), [`SkipListMemtable.java:124-125`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/memtable/SkipListMemtable.java#L124-L125)) — not measured JVM heap. Excludes non-memtable heap and slab fragmentation. If those size models under-count real object footprint, actual heap can exceed `allocated` while the counter still reads "within limit." Direct on the *estimated* footprint; proxy for node heap. |
| **Enforcement Point** | ⚠ | Check runs **after** `adjustAllocated(size)` records the bytes ([`allocated():183-184`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/utils/memory/MemtablePool.java#L183-L184)) — memory is already used before the trigger fires. Flush is **asynchronous**; heap keeps growing until the flush completes. |
| **Default State** | ✓ | Enabled by default. `limit` defaults to ¼ heap; `memtable_cleanup_threshold` defaults to `1/(1 + memtable_flush_writers)` ([`DatabaseDescriptor.java:763`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/DatabaseDescriptor.java#L763)). |

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
- **Estimate-fidelity divergence:** because `allocated` counts an *estimated*
  footprint (see Proxy Match), data whose true retained size exceeds its
  `unsharedHeapSize` estimate lets real heap exceed `allocated` while staying
  "under limit" — the proxy-mismatch failure mode. Magnitude is an empirical
  (chaos) question, not a static one.

## Verification

| Field | Content |
|-------|---------|
| **Status** | verified (static trace) |
| **Verified By / Date** | Claude + Jingsong, 2026-09-08 |

## Notes

- Default `memtable_allocation_type = heap_buffers` → `SlabPool(heapLimit, 0, …)`, so `memtable_heap_space` maps to `MEMORY_POOL.onHeap.limit`.
- `used()` returns `allocated` only (does not subtract `reclaiming`), so in-flight flushes still count toward the trigger.
- **What `allocated` measures:** estimated footprint = cloned data bytes (slab/native cloner) **+** structural overhead charged explicitly — partition/row overhead ([`SkipListMemtable.java:124-125`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/memtable/SkipListMemtable.java#L124-L125)) and per-row/column/stats/deletion `unsharedHeapSize*()` estimates via `onAllocatedOnHeap → onHeap().adjust()` ([`BTreePartitionUpdater.java:132-182`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/partitions/BTreePartitionUpdater.java#L132-L182)). The limit governs `Σ estimated_size`, not raw bytes or measured heap.

---

## Correction Log

- 2026-09-10: Verified against local `cassandra-cassandra-5.0.9` clone. One fix: `MemtableCleanerThread.run()` cited as `71-100` in the codepath file but `73-88` here (inconsistent) — `run()` actually starts at line **71**; corrected this file's citation to **71-89** to match the method body and the (already-correct) codepath file. All other citations in this file checked out exactly against the local source.
