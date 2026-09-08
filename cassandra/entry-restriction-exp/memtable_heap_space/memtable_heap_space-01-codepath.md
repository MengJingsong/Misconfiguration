# memtable_heap_space — Pair 01 · Full Code Path

> **Summary:** [memtable_heap_space-01-summary.md](memtable_heap_space-01-summary.md) · **Index:** [../_INDEX.md](../_INDEX.md)
>
> **Source:** apache/cassandra @ tag `cassandra-5.0.9`

**Entry point:** memtable_heap_space
**Restriction location (this pair):** [`MemtablePool.SubPool.needsCleaning():128`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/utils/memory/MemtablePool.java#L128) → [`maybeClean():131-135`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/utils/memory/MemtablePool.java#L131-L135) (soft cleanup trigger)

## Full Continuous Code Path

Declaration → default/validate → read → convert to bytes → pool build → store as
`SubPool.limit` → threshold calc → usage check → trigger → flush action.

Each `Location` cell links to the pinned source at tag `cassandra-5.0.9`.

| Step | Stage | Location (`Class.method:line`) | What happens | Value / State |
|------|-------|--------------------------------|--------------|---------------|
| 1 | declaration | [`Config.java:187`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/Config.java#L187) | Field `memtable_heap_space` declared (`IntMebibytesBound`) | config MiB |
| 2 | default | [`DatabaseDescriptor.java:586-587`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/DatabaseDescriptor.java#L586-L587) | If null, set to `maxMemory()/(4*1048576)` MiB | ¼ heap (MiB) |
| 3 | validate | [`DatabaseDescriptor.java:588-589`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/DatabaseDescriptor.java#L588-L589) | Reject if `toMebibytes()==0` | MiB > 0 |
| 4 | read / getter | [`DatabaseDescriptor.getMemtableHeapSpaceInMiB():4055-4057`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/DatabaseDescriptor.java#L4055-L4057) | Returns `conf.memtable_heap_space.toMebibytes()` | `long` MiB |
| 5 | convert to bytes | [`AbstractAllocatorMemtable.createMemtableAllocatorPool():81`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/memtable/AbstractAllocatorMemtable.java#L81) | `heapLimit = getMemtableHeapSpaceInMiB() << 20` | `long` bytes |
| 6 | pool build | [`AbstractAllocatorMemtable.createMemtableAllocatorPoolInternal():101-104`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/memtable/AbstractAllocatorMemtable.java#L101-L104) | `heap_buffers` → `new SlabPool(heapLimit, 0, cleanupThreshold, cleaner)` | pool ctor |
| 7 | subpool build | [`MemtablePool.<init>():59`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/utils/memory/MemtablePool.java#L59) | `onHeap = getSubPool(maxOnHeapMemory, cleanThreshold)` | SubPool created |
| 8 | store (limit) | [`MemtablePool.SubPool.<init>():117-121`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/utils/memory/MemtablePool.java#L117-L121) | `this.limit = limit; this.cleanThreshold = cleanThreshold` | `SubPool.limit` = heapLimit |
| 9 | pool published | [`AbstractAllocatorMemtable.java:59`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/memtable/AbstractAllocatorMemtable.java#L59) | `static final MemtablePool MEMORY_POOL = createMemtableAllocatorPool()` | global pool |
| 10 | allocation booked | [`MemtableAllocator.SubAllocator.allocated():204-206`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/utils/memory/MemtableAllocator.java#L204-L206) → [`MemtablePool.SubPool.allocated():177-185`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/utils/memory/MemtablePool.java#L177-L185) | `adjustAllocated(size)` then `maybeClean()` | `allocated += size` |
| 11 | threshold calc | [`SubPool.updateNextClean():137-147`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/utils/memory/MemtablePool.java#L137-L147) | `next = reclaiming + (long)(limit * cleanThreshold)` | `nextClean` |
| 12 | usage check | [`SubPool.needsCleaning():125-129`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/utils/memory/MemtablePool.java#L125-L129) | `used() > nextClean && updateNextClean()` | boolean |
| 13 | trigger | [`SubPool.maybeClean():131-135`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/utils/memory/MemtablePool.java#L131-L135) | If needed, `cleaner.trigger()` | signal cleaner |
| 14 | cleaner wakes | [`MemtableCleanerThread.trigger():131-134`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/utils/memory/MemtableCleanerThread.java#L131-L134) → [`run():71-100`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/utils/memory/MemtableCleanerThread.java#L71-L100) | Re-checks `pool.needsCleaning()`, calls `cleaner.clean()` | scheduled |
| 15 | action on breach | [`AbstractAllocatorMemtable.flushLargestMemtable():249-297`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/memtable/AbstractAllocatorMemtable.java#L249-L297) | Selects largest memtable by ownership ratio; `signalFlushRequired(…, MEMTABLE_LIMIT)` | flush scheduled |
| 16 | reclaim | [`SubPool.reclaiming()/reclaimed():199-214`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/utils/memory/MemtablePool.java#L199-L214) | Flushed bytes tracked as `reclaiming`, then released | heap freed |

## Path Continuity Notes

- Steps 12–13 also reachable via [`SubPool.acquired():187-190`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/utils/memory/MemtablePool.java#L187-L190) (which calls `maybeClean()` directly) and via [`reclaimed():206-214`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/utils/memory/MemtablePool.java#L206-L214) (which re-checks `updateNextClean()` and may re-trigger).
- Step 10 uses `adjustAllocated()` ([`:167-175`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/utils/memory/MemtablePool.java#L167-L175)), which the source comments as “bypassing any limits” — relevant to pair 02, not enforced here.
- Flush completion (step 16) is asynchronous via the returned `Future`; the path from `signalFlushRequired` into `ColumnFamilyStore` flush is out of scope for this pair.
- **Step 10 detail:** `allocated` accrues not just cloned data but metadata charged via `onAllocatedOnHeap → onHeap().adjust()` ([`BTreePartitionUpdater.java:132-182`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/partitions/BTreePartitionUpdater.java#L132-L182)) and post-insert row overhead ([`SkipListMemtable.java:124-125`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/memtable/SkipListMemtable.java#L124-L125)); the trigger check (steps 11-13) runs against this *estimated* total, not measured heap.
