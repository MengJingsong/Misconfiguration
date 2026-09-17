# memtable_offheap_space — region

> **Index:** [../_INDEX.md](../_INDEX.md)
>
> **Source:** apache/cassandra @ tag `cassandra-5.0.9`

## 1. Location

| Field | Content |
|-------|---------|
| **Case ID** | MEMTABLE_OFFHEAP_SPACE-REGION |
| **If-statement** | [`MemtablePool.SubPool.tryAllocate():156`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/utils/memory/MemtablePool.java#L156) |

```java
boolean tryAllocate(long size)
{
    while (true)
    {
        long cur;
        if ((cur = allocated) + size > limit)
            return false;
        if (allocatedUpdater.compareAndSet(this, cur, cur + size))
            return true;
    }
}
```

Same method body as [`memtable_heap_space-bytebuffer`](../memtable/memtable_heap_space-bytebuffer.md) —
`SubPool.tryAllocate()` is shared code. This case is a **different instance**
of `SubPool`: `MemtablePool.offHeap` rather than `MemtablePool.onHeap`
(see [`MemtablePool.java:48`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/utils/memory/MemtablePool.java#L48)),
constructed with a separately-configured `limit` and reached via a different
allocator (`NativeAllocator` instead of `HeapPool.Allocator`).

## 2. Context

Cassandra buffers newly-written data in memory (a "memtable") before it is
flushed to disk as an immutable SSTable file. When a table is configured to
keep those memtable cells off the JVM heap (to reduce garbage-collector
pressure from a large working set), the buffered bytes instead live in
native/off-heap memory, obtained directly from the OS rather than the JVM
allocator. Off-heap memory isn't garbage-collected, so without a cap a
burst of writes could grow this native allocation without bound just as
easily as its on-heap counterpart. This if-check is the same admission gate
as the on-heap case — "is there room for `size` more bytes under the
configured ceiling?" — applied to a separate off-heap accounting pool.

## 3. Module

| Field | Content |
|-------|---------|
| **Module** | Storage engine — memtable memory allocation (`utils/memory`, `db/memtable`) |
| **One-line role** | Tracks and bounds the off-heap (native) bytes used by in-memory memtables when Cassandra is configured to allocate memtable cells as off-heap objects rather than on-heap `ByteBuffer`s. |

## 4. Capacity-overflow check

| Field | Content |
|-------|---------|
| **Is this a capacity/overflow check?** | Yes — a running-total counter (`allocated`) plus a requested increment (`size`) compared against a fixed ceiling (`limit`), on the `offHeap` `SubPool` instance. |
| **Usage-side operand** | `allocated` — `volatile long` on `SubPool`, running total of off-heap bytes currently allocated from `MemtablePool.offHeap`. |
| **Limit-side operand** | `limit` — `final long` on the `offHeap` `SubPool`, set once at construction from `maxOffHeapMemory`. |
| **Limit type** | Configuration (`memtable_offheap_space`), with an auto-sized default. |

**Limit initialization path** (declare → configure/derive → store → read at the check):

1. [`Config.java:188-189`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/Config.java#L188-L189) — declared: `memtable_offheap_space` (`DataStorageSpec.IntMebibytesBound`).
2. [`DatabaseDescriptor.java:583-584`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/DatabaseDescriptor.java#L583-L584) — configured/derived: if unset, auto-sized to `Runtime.getRuntime().maxMemory() / 4` (same fallback formula as the heap limit); [`DatabaseDescriptor.java:591-594`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/DatabaseDescriptor.java#L591-L594) logs when the resulting threshold is > 0.
3. [`DatabaseDescriptor.java:4060-4062`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/DatabaseDescriptor.java#L4060-L4062) — exposed via `getMemtableOffheapSpaceInMiB()`.
4. [`AbstractAllocatorMemtable.java:82`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/memtable/AbstractAllocatorMemtable.java#L82) — read and converted to bytes: `offHeapLimit = getMemtableOffheapSpaceInMiB() << 20`.
5. [`AbstractAllocatorMemtable.java:85,108`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/memtable/AbstractAllocatorMemtable.java#L85) — passed through `createMemtableAllocatorPoolInternal(...)`; for `Config.MemtableAllocationType.offheap_objects`, routed to `new NativePool(heapLimit, offHeapLimit, ...)` at [line 108](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/memtable/AbstractAllocatorMemtable.java#L108).
6. [`NativePool.java:23-25`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/utils/memory/NativePool.java#L23-L25) — `NativePool` constructor forwards `maxOffHeapMemory` to `super(...)` (`MemtablePool`).
7. [`MemtablePool.java:55-60`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/utils/memory/MemtablePool.java#L55-L60) — stored: `MemtablePool` constructor calls `this.offHeap = getSubPool(maxOffHeapMemory, cleanThreshold)`, which sets `SubPool.limit` on the `offHeap` field ([line 48](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/utils/memory/MemtablePool.java#L48)) — this is what `tryAllocate()` reads at the check when called via `offHeap()`.

## 5. Branch semantics

| Branch | Condition | Effect |
|--------|-----------|--------|
| **Allow** | `allocated + size <= limit` (the `if` is false, so the CAS is attempted) | CAS updates `allocated` on the `offHeap` `SubPool`; on success returns `true` — caller proceeds to slice off-heap memory. |
| **Disallow** | `allocated + size > limit` | Returns `false` immediately, no state change — caller does not allocate through this path (in `NativeAllocator`'s case, this return value is not even checked — see 6b). |

```java
// allow branch (falls through the if, line 158-159)
if (allocatedUpdater.compareAndSet(this, cur, cur + size))
    return true;
```

```java
// disallow branch (line 156-157)
if ((cur = allocated) + size > limit)
    return false;
```

## 6. Code path

### 6a. Allow branch → object creation

1. [`MemtablePool.java:156-160`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/utils/memory/MemtablePool.java#L156-L160) — allow branch taken on the `offHeap` `SubPool`, `allocated` bumped via CAS, returns `true`.
2. [`MemtableAllocator.java:175-177`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/utils/memory/MemtableAllocator.java#L175-L177) — `SubAllocator.allocate()`: `if (parent.tryAllocate(size)) { acquired(size); return; }` — same shared logic as the heap case, called on the `offHeap` `SubAllocator`.
3. [`NativeAllocator.java:138-141`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/utils/memory/NativeAllocator.java#L138-L141) — `NativeAllocator.allocate(int size, OpOrder.Group opGroup)` calls `offHeap().allocate(size, opGroup)` (steps 1-2 above) **for accounting only** — the boolean/blocking result of the tracked allocation is not used to gate what follows; `NativeAllocator` always proceeds to physically allocate (see 6b).
4. [`NativeAllocator.java:144-156`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/utils/memory/NativeAllocator.java#L144-L156) — size routing: allocations `> MAX_CLONED_SIZE` (128 KiB) go to `allocateOversize(size)`; smaller ones are sliced from `currentRegion`, swapping in a new `Region` via `trySwapRegion()` if the current one is full or absent.
5. [`NativeAllocator.java:176`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/utils/memory/NativeAllocator.java#L176) (new region, via `trySwapRegion()`) or [`NativeAllocator.java:190`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/utils/memory/NativeAllocator.java#L190) (oversize path) — **object creation**: `new Region(MemoryUtil.allocate(size), size)` — `MemoryUtil.allocate(size)` is the actual native/off-heap memory allocation (`Unsafe.allocateMemory` under the hood); `Region` wraps the returned peer address for slab-style sub-allocation.

### 6b. Disallow branch effect

**Accounting/allocation are decoupled here:** unlike the heap path
(where `ByteBuffer.allocate()` only runs after `tryAllocate()` returns
`true`, and `HeapPool.Allocator.allocate()` returns nothing if it doesn't),
`NativeAllocator.allocate()` calls `offHeap().allocate()` purely to update
the tracked/blocking accounting (`SubAllocator.allocate()` will block
the caller on `opGroup` if `tryAllocate()` keeps failing and the op isn't
already blocking — see [`MemtableAllocator.java:170-193`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/utils/memory/MemtableAllocator.java#L170-L193)) but does not
use its return value to conditionally skip the physical `MemoryUtil.allocate()`
call in 6a's step 5. The if-check still gates *whether the caller blocks/waits*,
but not *whether the native memory is eventually allocated* — worth flagging
for Target 3 (bypass analysis) even though this case itself is Target 1+2 only.

## 7. Object & resource

| Field | Content |
|-------|---------|
| **Object created** | `NativeAllocator.Region` (private inner class) wrapping a raw native memory address (`long peer`) obtained from `MemoryUtil.allocate(size)`. |
| **Resource consumed** | Off-heap (native) bytes — a `Region` sized `MIN_REGION_SIZE` (8 KiB) to `MAX_REGION_SIZE` (1 MiB), doubling each swap, or exactly `size` bytes for oversize (>128 KiB) allocations. |
| **Rough sizing** | Slab-allocated: region size scales exponentially (8 KiB → 1 MiB) independent of the individual cell's `size`; oversize allocations (`size > MAX_CLONED_SIZE`) get a dedicated `Region` sized exactly to `size`. |
| **Lifetime / release** | Freed via `MemoryUtil.free(region.peer)` in `NativeAllocator.setDiscarded()` ([`NativeAllocator.java:200-206`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/utils/memory/NativeAllocator.java#L200-L206)) when the owning allocator is discarded (memtable flushed/discarded); tracked-accounting side released via `SubPool.released(size)` ([`MemtablePool.java:192-197`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/utils/memory/MemtablePool.java#L192-L197)), same as the heap case. |

## 8. Maximum memory bound

Raising `memtable_offheap_space` raises the total off-heap bytes the
**tracked-accounting** side of the single JVM-wide `MEMORY_POOL`'s `offHeap`
`SubPool` will count before making writers wait; lowering it makes them
wait sooner. But this is doubly non-hard as a true memory ceiling. First,
same as the heap sibling: a write already marked "blocking" bypasses the
check via `markBlocking()` and pushes `allocated` past `limit` with no
ceiling of its own (6b). Second, and unique to this case: per 6b,
`NativeAllocator.allocate()` never conditions the physical
`MemoryUtil.allocate()` call on `tryAllocate()`'s return value at all — not
even via the escape hatch's `isBlocking()` check, it simply never reads the
boolean — so the *physical* off-heap bytes allocated can diverge from the
*accounted* bytes independent of any blocking state. A reader taking
`memtable_offheap_space` as a hard native-memory ceiling would be wrong on
two independent grounds; both flagged for Target 3, not resolved here.

## Verification

Line numbers checked against the local pinned-tag clone. Per
[README.md § Verifying a case](../README.md#verifying-a-case-triggering-the-disallow-branch),
the primary trigger below has been **executed and recorded** (see table below).

- **Unit/programmatic level (primary trigger — executed 2026-09-16):** `test/unit/org/apache/cassandra/utils/memory/NativeAllocatorTest.java`
  already exercises this exact if-check both ways. Its `testBookKeeping()`
  constructs a `NativePool(1, 100, 0.75f, ...)` (off-heap limit = 100 bytes)
  directly, allocates up to the limit, then allocates past it while a
  scheduled task calls `markBlocking()` — demonstrating both (a) the thread
  parking on `SubPool.hasRoom` when the op is not yet blocking, and (b) the
  `allocated(size)` force-through once `opGroup.isBlocking()` becomes true,
  pushing `allocated` past `limit` (see 6b above). Run as-is (no new
  harness needed) via
  `ant testsome -Dtest.name=org.apache.cassandra.utils.memory.NativeAllocatorTest`
  on the `cassandra-src` clone at
  `/proj/misconfiguration-PG0/git-repos/cassandra-src` (JDK 11.0.32, Ant
  1.10.12, already provisioned on this node from the sibling heap case).
  Result: `BUILD SUCCESSFUL`, `Tests run: 1, Failures: 0, Errors: 0`. The
  single `@Test` passing proves both outcomes of the disallow branch at
  `MemtablePool.java:156` on the `offHeap` `SubPool`: (1) `verifyUsedReclaiming(80, 0)`
  after allocating up to the 100-byte limit confirms tracked accounting
  stops exactly at `limit`, and (2) `verifyUsedReclaiming(110, 110)` after
  the subsequent 30-byte allocation — taken only once `markBlocking()` sets
  `opGroup.isBlocking()` — confirms the escape-hatch force-through past
  `limit` (110 > 100), matching 6b that accounting and physical
  allocation are decoupled here.
- **Live-cluster level (secondary, for end-to-end confirmation):** set
  `memtable_allocation_type: offheap_objects` (not the default — required to
  reach `NativeAllocator` at all) and `memtable_offheap_space` below
  `NativeAllocator.MIN_REGION_SIZE` (8 KiB) so the first off-heap allocation
  deterministically fails `tryAllocate()`; raise `memtable_heap_space` so the
  heap limit doesn't trip first. Expect the write to **hang**, not fail —
  `MEMORY_POOL` is a single global static singleton
  (`AbstractAllocatorMemtable.java:59`) shared by all tables, so isolate on a
  dedicated single-node instance rather than a shared/loaded cluster.
  Evidence to capture: the JMX timer
  `org.apache.cassandra.metrics:type=MemtablePool,name=BlockedOnAllocation`
  (`MemtablePool.java:63`) going non-zero, and/or a thread dump of the write
  thread parked in `WaitQueue$Signal.awaitThrowUncheckedOnInterrupt()` called
  from `MemtableAllocator$LifeCycle.allocate()` — not just the hang itself,
  which could have other causes.

| Field | Content |
|--------|---------|
| **Status** | verified |
| **Verified By / Date** | Claude (session) — 2026-09-16; primary trigger run and evidence recorded |
| **Trigger method** | Existing `NativeAllocatorTest.testBookKeeping()`, run via `ant testsome -Dtest.name=org.apache.cassandra.utils.memory.NativeAllocatorTest` against the `cassandra-src` clone at `/proj/misconfiguration-PG0/git-repos/cassandra-src` (tag `cassandra-5.0.9`) |
| **Evidence** | `BUILD SUCCESSFUL`, `Tests run: 1, Failures: 0, Errors: 0`. Test's own assertions (`verifyUsedReclaiming(80, 0)` then `verifyUsedReclaiming(110, 110)`) directly demonstrate the disallow branch's two outcomes at `MemtablePool.java:156` on the `offHeap` `SubPool` — accounting capped at `limit`, then force-through past it once `markBlocking()` fires. |
| **Notes** | Sibling to [`memtable_heap_space-bytebuffer`](../memtable/memtable_heap_space-bytebuffer.md); same if-check code, different `SubPool` instance/limit/allocator. 6b note on decoupled accounting vs. physical allocation (the `isBlocking()` force-through past `limit`) is a candidate for later Target-3 bypass analysis, not addressed here. Secondary live-cluster trigger not run — same rationale as the heap case: the unit test already gives direct evidence for both branches. |

---

## Notes

- `NativePool`/`NativeAllocator` is only reachable when `memtable_allocation_type` is `offheap_objects`; the sibling `offheap_buffers` type uses `SlabPool` (off-heap `ByteBuffer` slabs) instead — a third, not-yet-written variant if the off-heap-buffers path is wanted later.
