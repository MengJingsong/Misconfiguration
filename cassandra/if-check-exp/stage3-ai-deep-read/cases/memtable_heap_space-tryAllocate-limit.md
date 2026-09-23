# memtable_heap_space — bytebuffer

> **Index:** [../_INDEX.md](../_INDEX.md)
>
> **Source:** apache/cassandra @ tag `cassandra-5.0.9`

## 1. Location

| Field | Content |
|-------|---------|
| **Case ID** | MEMTABLE_HEAP_SPACE-TRYALLOCATE-LIMIT |
| **Constraint** | `memtable_heap_space` — configuration entry (`Config.java`) |
| **Enforcement pattern** | (b) — the capacity check returns a boolean verdict to its caller |
| **Capacity check** | [`MemtablePool.SubPool.tryAllocate():156`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/utils/memory/MemtablePool.java#L156) |
| **Decision point** | [`MemtableAllocator.SubAllocator.allocate():169-197`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/utils/memory/MemtableAllocator.java#L169-L197) — on a `false` verdict, parks the caller on `SubPool.hasRoom`, or forces the allocation through if the caller's `OpOrder.Group` is already marked blocking |
| **Allocation site** | [`HeapPool.Allocator.allocate():52-55`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/utils/memory/HeapPool.java#L52-L55) → `ByteBuffer.allocate(size)` |
| **Related cases** | [`memtable_offheap_space-tryAllocate-limit`](memtable_offheap_space-tryAllocate-limit.md) (off-heap sibling; same check code) |

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

## 2. Context

Cassandra buffers newly-written data in memory (a "memtable") before it is
flushed to disk as an immutable SSTable file — this avoids a disk write on
every single client write, at the cost of holding recent writes in JVM heap.
Without a cap, a burst of writes arriving faster than flushes can drain them
would grow this in-memory buffer without bound, risking an out-of-memory
condition. This if-check is the admission gate for that buffer: every write
that wants to add bytes to a memtable first asks a shared pool "is there
room for `size` more bytes under the configured ceiling?" — if yes, the
write's bytes are counted against the ceiling and the write proceeds; if
no, the write is (usually) made to wait until other memtables are flushed
and release their share back to the pool.

## 3. Module

| Field | Content |
|-------|---------|
| **Module** | Storage engine — memtable memory allocation (`utils/memory`, `db/memtable`) |
| **One-line role** | Tracks and bounds the JVM heap / off-heap bytes used by in-memory memtables (the write-path buffer before data is flushed to disk as SSTables). |

## 4. Capacity check & limit

| Field | Content |
|-------|---------|
| **Is this a capacity check?** | Yes — a running-total counter (`allocated`) plus a requested increment (`size`) compared against a fixed ceiling (`limit`). |
| **Usage-side operand** | `allocated` — `volatile long` on `SubPool`, the running total of bytes currently allocated from this pool. |
| **Limit-side operand** | `limit` — `final long` on `SubPool`, set once at construction. |
| **Limit type** | Configuration (`memtable_heap_space`), with an auto-sized default. |

**Limit initialization path** (declare → configure/derive → store → read at the check):

1. [`Config.java:186-187`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/Config.java#L186-L187) — declared: `memtable_heap_space` (`DataStorageSpec.IntMebibytesBound`).
2. [`DatabaseDescriptor.java:586-590`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/DatabaseDescriptor.java#L586-L590) — configured/derived: if unset, auto-sized to `Runtime.getRuntime().maxMemory() / 4`; validated `> 0`.
3. [`DatabaseDescriptor.java:4057`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/DatabaseDescriptor.java#L4057) — exposed via `getMemtableHeapSpaceInMiB()`.
4. [`AbstractAllocatorMemtable.java:81`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/memtable/AbstractAllocatorMemtable.java#L81) — read and converted to bytes: `heapLimit = getMemtableHeapSpaceInMiB() << 20`.
5. [`MemtablePool.java:55-60`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/utils/memory/MemtablePool.java#L55-L60) & [`MemtablePool.java:117-121`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/utils/memory/MemtablePool.java#L117-L121) — stored: `MemtablePool` constructor passes `maxOnHeapMemory` into `getSubPool(limit, cleanThreshold)`, which sets `SubPool.limit` — this is what `tryAllocate()` reads at the check.

## 5. Decision point & branch semantics

| Field | Content |
|-------|---------|
| **Decision point** | [`MemtableAllocator.SubAllocator.allocate():169-197`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/utils/memory/MemtableAllocator.java#L169-L197) — on a `false` verdict, parks the caller on `SubPool.hasRoom`, or forces the allocation through if the caller's `OpOrder.Group` is already marked blocking |
| **Verdict** | boolean return of `SubPool.tryAllocate()` (set at the check, `MemtablePool.java:156`), read by `SubAllocator.allocate()` (the decision point above). |

| Branch | Condition | Effect |
|--------|-----------|--------|
| **Allow** | `allocated + size <= limit` (the `if` is false, so the CAS is attempted) | CAS updates `allocated`; on success returns `true` — caller proceeds to allocate the object. |
| **Disallow** | `allocated + size > limit` | Returns `false` immediately, no state change — caller does not allocate through this path. |

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

1. [`MemtablePool.java:156-160`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/utils/memory/MemtablePool.java#L156-L160) — allow branch taken, `allocated` bumped via CAS, returns `true`.
2. [`MemtableAllocator.java:175-177`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/utils/memory/MemtableAllocator.java#L175-L177) — `SubAllocator.allocate()`: `if (parent.tryAllocate(size)) { acquired(size); return; }` — caller sees success, marks the memory acquired, returns normally.
3. [`HeapPool.java:52-55`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/utils/memory/HeapPool.java#L52-L55) — `HeapPool.Allocator.allocate(int size, OpOrder.Group opGroup)`: calls `super.onHeap().allocate(size, opGroup)` (steps 1-2 above), then **object creation**: `return ByteBuffer.allocate(size);`.

**Note — accounting and object creation are decoupled (same as the off-heap
sibling case):** step 3's `ByteBuffer.allocate(size)` runs unconditionally
after `onHeap().allocate(size, opGroup)` *returns*, regardless of how it
returned — see 6b for what the disallow branch actually does.

### 6b. Disallow branch effect

The full disallow-branch behavior lives in
[`MemtableAllocator.java:169-197`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/utils/memory/MemtableAllocator.java#L169-L197)
(`SubAllocator.allocate()`), which 6a's step 2 only shows the allow-branch
half of:

```java
public void allocate(long size, OpOrder.Group opGroup)
{
    assert size >= 0;
    while (true)
    {
        if (parent.tryAllocate(size))          // <- the if-check (MemtablePool.java:156)
        {
            acquired(size);
            return;
        }
        if (opGroup.isBlocking())               // escape hatch: force through, no wait
        {
            allocated(size);                    // bypasses the limit entirely
            return;
        }
        WaitQueue.Signal signal = parent.hasRoom().register(parent.blockedTimerContext(), Timer.Context::stop);
        opGroup.notifyIfBlocking(signal);       // re-check in case opGroup becomes blocking while we wait
        boolean allocated = parent.tryAllocate(size);
        if (allocated)
        {
            signal.cancel();
            acquired(size);
            return;
        }
        else
            signal.awaitThrowUncheckedOnInterrupt();   // parks here until hasRoom.signalAll() or markBlocking()
    }
}
```

So when the if-check disallows (`tryAllocate()` returns `false`), one of two
things happens, and neither is a rejected/failed write:

- **Normal case — the calling thread blocks.** If `opGroup` is not already
  marked "blocking," the thread registers on `SubPool.hasRoom` and parks in
  `signal.awaitThrowUncheckedOnInterrupt()` until either (a) some allocator
  calls `SubPool.released()` (`MemtablePool.java:192-197`), which calls
  `hasRoom.signalAll()`, waking every waiter to retry `tryAllocate()`; or
  (b) a flush barrier later calls `OpOrder.Barrier.markBlocking()` on a
  barrier this `opGroup` precedes, which signals this specific wait via
  `opGroup`'s own `blocking` queue (`OpOrder.java:319-336`) — after which the
  loop retries `tryAllocate()` again, and if it *still* fails, falls into the
  escape hatch below on that next iteration.
- **Escape hatch — the limit is silently overshot.** If `opGroup.isBlocking()`
  is already `true` (set by `ColumnFamilyStore.markBlocking()` at
  `ColumnFamilyStore.java:1238`, done for in-flight writes a flush barrier
  must wait out rather than deadlock on), the disallow branch does not
  block at all — `allocated(size)` unconditionally adds `size` to
  `SubPool.allocated`, pushing it **past** `limit`. This is intentional (it
  prevents a flush from deadlocking on the very memory it's trying to free)
  but it means the if-check does not actually stop this class of caller from
  allocating — worth flagging for Target 3 (bypass analysis), not pursued
  further in this Target 1+2 case.

## 7. Object & resource

| Field | Content |
|-------|---------|
| **Object created** | `java.nio.ByteBuffer` — the buffer backing a memtable cell/row write. |
| **Resource consumed** | JVM heap bytes — exactly `size` bytes per call, the caller-supplied write size. |
| **Rough sizing** | Equal to the `size` parameter threaded in from the write path (cell/row serialized size) — no fixed struct size; scales with write payload. |
| **Lifetime / release** | Released via `SubPool.released(size)` (`MemtablePool.java:192-197`) when the owning `SubAllocator` is discarded (memtable flushed/discarded) — signals `hasRoom` to unblock any waiters. |

## 8. Maximum memory bound

Raising `memtable_heap_space` raises the total on-heap bytes the single
JVM-wide `MEMORY_POOL` ([`AbstractAllocatorMemtable.java:59`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/memtable/AbstractAllocatorMemtable.java#L59),
one instance for the whole node, shared by every table's memtable — not
per-table or per-keyspace) will admit through this if-check before making
writers wait; lowering it makes writers wait sooner, at a smaller total.
Under normal operation the ceiling is exactly `limit` bytes (the configured
value, auto-sized to `Runtime.getRuntime().maxMemory() / 4` if unset). **This
is not a hard ceiling**, though: per 6b, a write already marked "blocking"
(an in-flight write a flush barrier must wait out,
`ColumnFamilyStore.java:1238`) bypasses the check's enforcement entirely and
pushes `allocated` past `limit` with no ceiling of its own — so the true
worst case is `limit` plus however much blocking-marked write volume is
in flight at once during a flush barrier wait, not simply "`memtable_heap_space`
MiB." Flagged for Target 3 (bypass analysis).

## 9. Provenance

| Field | Content |
|--------|---------|
| **Stage-3 feed** | `3b` — established by deep-reading the source; no stage-1/2 row led here. |
| **Line numbers checked** | 2026-09-22 against the local `cassandra-5.0.9` clone (`git describe --tags`). |
| **Escape hatch / Target-3 note** | `markBlocking()`-marked `OpOrder.Group` silently forces the allocation past `limit` instead of parking (`MemtableAllocator.SubAllocator.allocate():169-197`); see §6b. |

---

## 10. Notes

- The escape hatch (`opGroup.isBlocking()` forcing `allocated(size)` through
  regardless of `limit`) is shared code between this case and
  `memtable_offheap_space-tryAllocate-limit` — it lives in `MemtableAllocator.java`,
  not in either allocator subclass. Any future case touching
  `SubPool.tryAllocate()` (there may be others besides the two memtable
  pools) should check whether it goes through this same
  `MemtableAllocator.SubAllocator.allocate()` path before assuming the
  if-check behaves as a clean reject.
