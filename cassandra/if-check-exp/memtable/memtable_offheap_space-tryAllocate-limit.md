# memtable_offheap_space — region

> **Index:** [../stage3-ai-deep-read/_INDEX.md](../stage3-ai-deep-read/_INDEX.md)
>
> **Source:** apache/cassandra @ tag `cassandra-5.0.9`

## 1. Location

| Field | Content |
|-------|---------|
| **Case ID** | MEMTABLE_OFFHEAP_SPACE-TRYALLOCATE-LIMIT |
| **Constraint** | `memtable_offheap_space` — configuration entry (`Config.java`) |
| **Enforcement pattern** | (b) — the capacity check returns a boolean verdict to its caller |
| **Capacity check** | [`MemtablePool.SubPool.tryAllocate():156`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/utils/memory/MemtablePool.java#L156) (on the `offHeap` `SubPool`) |
| **Decision point** | [`MemtableAllocator.SubAllocator.allocate():169-197`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/utils/memory/MemtableAllocator.java#L169-L197) — same park-or-force-through decision as the heap case |
| **Allocation site** | [`NativeAllocator.allocate():138-190`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/utils/memory/NativeAllocator.java#L138-L190) → a new `NativeAllocator.Region` via `MemoryUtil.allocate()` |
| **Related cases** | [`memtable_heap_space-tryAllocate-limit`](memtable_heap_space-tryAllocate-limit.md) (on-heap sibling; same check code) |

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

Same method body as [`memtable_heap_space-tryAllocate-limit`](../memtable/memtable_heap_space-tryAllocate-limit.md) —
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

## 4. Capacity check & limit

| Field | Content |
|-------|---------|
| **Is this a capacity check?** | Yes — a running-total counter (`allocated`) plus a requested increment (`size`) compared against a fixed ceiling (`limit`), on the `offHeap` `SubPool` instance. |
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

## 5. Decision point & branch semantics

| Field | Content |
|-------|---------|
| **Decision point** | [`MemtableAllocator.SubAllocator.allocate():169-197`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/utils/memory/MemtableAllocator.java#L169-L197) — same park-or-force-through decision as the heap case |
| **Verdict** | boolean return of `SubPool.tryAllocate()` (set at the check, `MemtablePool.java:156`), read by `SubAllocator.allocate()` (the decision point above). |

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

## 9. Provenance

| Field | Content |
|--------|---------|
| **Stage-3 feed** | `3b` — established by deep-reading the source; no stage-1/2 row led here. |
| **Line numbers checked** | 2026-09-22 against the local `cassandra-5.0.9` clone (`git describe --tags`). |
| **Escape hatch / Target-3 note** | `markBlocking()`/`isBlocking()` forces the allocation through past `limit` instead of parking; see §6b. |

---

## 10. Notes

- `NativePool`/`NativeAllocator` is only reachable when `memtable_allocation_type` is `offheap_objects`; the sibling `offheap_buffers` type uses `SlabPool` (off-heap `ByteBuffer` slabs) instead — a third, not-yet-written variant if the off-heap-buffers path is wanted later.
