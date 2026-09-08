# memtable_heap_space — Pair 02 · Full Code Path

> **Summary:** [memtable_heap_space-02-summary.md](memtable_heap_space-02-summary.md) · **Index:** [../_INDEX.md](../_INDEX.md)
>
> **Source:** apache/cassandra @ tag `cassandra-5.0.9`

**Entry point:** memtable_heap_space
**Restriction location (this pair):** `MemtablePool.SubPool.tryAllocate():151-161` (hard allocation cap)

## Full Continuous Code Path

Steps 1–9 are identical to pair 01 (declaration → `SubPool.limit`); they are
repeated compactly so this file is self-contained, then the path diverges at the
allocation request.

| Step | Stage | Location (`Class.method:line`) | What happens | Value / State |
|------|-------|--------------------------------|--------------|---------------|
| 1 | declaration | `Config.java:187` | Field `memtable_heap_space` declared | config MiB |
| 2 | default | `DatabaseDescriptor.java:586-587` | If null, `maxMemory()/(4*1048576)` MiB | ¼ heap (MiB) |
| 3 | validate | `DatabaseDescriptor.java:588-589` | Reject if `== 0` | MiB > 0 |
| 4 | read / getter | `DatabaseDescriptor.getMemtableHeapSpaceInMiB():4055-4057` | Return MiB | `long` MiB |
| 5 | convert to bytes | `AbstractAllocatorMemtable.createMemtableAllocatorPool():81` | `heapLimit = … << 20` | `long` bytes |
| 6 | pool build | `AbstractAllocatorMemtable.createMemtableAllocatorPoolInternal():101-104` | `SlabPool(heapLimit, 0, …)` | pool ctor |
| 7 | subpool build | `MemtablePool.<init>():59` | `onHeap = getSubPool(heapLimit, …)` | SubPool created |
| 8 | store (limit) | `MemtablePool.SubPool.<init>():117-121` | `this.limit = limit` | `SubPool.limit` = heapLimit |
| 9 | pool published | `AbstractAllocatorMemtable.java:59` | `MEMORY_POOL` static | global pool |
| 10 | write allocates | `MemtableAllocator.SubAllocator.allocate():169-175` | Write path requests `size`; enters CAS loop | request `size` |
| 11 | **hard check** | `MemtablePool.SubPool.tryAllocate():151-161` | `(cur = allocated) + size > limit → return false`; else CAS `allocated += size` | allow / refuse |
| 12a | acquire (fits) | `SubAllocator.allocate():175-179` → `acquired():222-224` | On success, `acquired(size)`, return | booked |
| 12b | **bypass** | `SubAllocator.allocate():180-183` | If `opGroup.isBlocking()` → `allocated(size)` books **over limit** | limit exceeded |
| 13 | register wait | `SubAllocator.allocate():185-186` | `parent.hasRoom().register(…)`; `opGroup.notifyIfBlocking(signal)` | queued |
| 14 | retry | `SubAllocator.allocate():187-193` | Second `tryAllocate`; on success cancel signal + `acquired` | maybe booked |
| 15 | **block** | `SubAllocator.allocate():195` | `signal.awaitThrowUncheckedOnInterrupt()` — writer thread parks | blocked |
| 16 | release wakes | `MemtablePool.SubPool.released():192-197` | On free, `adjustAllocated(-size)` + `hasRoom.signalAll()` | writer resumes |

## Path Continuity Notes

- The `while(true)` loop in `allocate()` (`:173-196`) cycles steps 11–15 until
  the allocation succeeds or the bypass fires.
- Step 12b is the key divergence for Target 3: it books memory through
  `allocated()` → `adjustAllocated()` (`MemtablePool:167-175`), which the source
  comments as “bypassing any limits or constraints.”
- Step 16 signals **all** waiters; the freeing side is driven by flush completion
  (see pair 01, step 16), coupling the two pairs at runtime.
