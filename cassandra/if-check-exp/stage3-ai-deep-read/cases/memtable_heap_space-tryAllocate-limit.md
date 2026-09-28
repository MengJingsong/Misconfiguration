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


## 9. Test design (guidance for stage 4)

**Stage 3 writes this section; stage 3 never runs it.** Method and pitfalls:
[README.md §8](../../README.md#8-designing-a-test-for-a-case). Where stage 4's
numbers go: [`../../stage4-runtime-verification/README.md`](../../stage4-runtime-verification/README.md).

> **Unit tier already executed, 2026-09-16, before stage 4 existed.**
> `test/unit/org/apache/cassandra/utils/memory/HeapPoolTest.java` was written
> for this case, run on CloudLab node pc80, and passed
> (`Tests run: 2, Failures: 0, Errors: 0`). It is still present in the shared
> `cassandra-src` clone. **It is not committed to this repo and not upstream** —
> it exists only as an untracked file in that clone, which is a preservation
> risk worth acting on. Its result is prior evidence, not a stage-4 result;
> stage 4 should re-run it as the control and then do the cluster tier, which
> was never done.

| Field | Content |
|-------|---------|
| **Testability** | **Config-testable, but restart-only.** `Config.memtable_heap_space` is **not** `volatile` and has **no setter** in `DatabaseDescriptor`; `AbstractAllocatorMemtable.MEMORY_POOL` is `static final`, built once at class initialization from the config ([`:59`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/memtable/AbstractAllocatorMemtable.java#L59), [`createMemtableAllocatorPool():78-86`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/memtable/AbstractAllocatorMemtable.java#L78-L86)). Every capacity value therefore costs a node restart. Checked 2026-09-28. |
| **Constraint knob** | `memtable_heap_space` in `cassandra.yaml` (MiB). At the unit tier, bypass config entirely: `new HeapPool(limit, cleanThreshold, cleaner)` directly, as `HeapPoolTest` does, or `AbstractAllocatorMemtable.createMemtableAllocatorPoolInternal(...)` which is `@VisibleForTesting public` ([`:88-92`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/memtable/AbstractAllocatorMemtable.java#L88-L92)). Also set `memtable_allocation_type: heap_buffers` so the on-heap pool is the one under test. |
| **Capacity values to test** | `memtable_heap_space` ∈ {`128MiB`, `256MiB`, `512MiB`, **default**}. The default is *not* a fixed number — when unset it is auto-sized to `maxMemory() / 4` ([`DatabaseDescriptor.java:586-590`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/DatabaseDescriptor.java#L586-L590)) — so **pin `-Xmx` across the whole sweep** and record the resolved value from the startup log, or the default arm is not comparable with the others. |
| **Usage-side observable** | `SubPool.allocated` on the `onHeap` pool — the running total the check compares. |
| **Instrument** | **The real operand is not exposed as a metric.** A grep of `src/java/org/apache/cassandra/metrics/` finds no `MemtablePool` gauge (checked 2026-09-25, recorded in README §8.3). Proxies, in order of directness: (1) at the unit tier, `pool.onHeap.used()` and `allocator.onHeap().owns()` — **this is the operand itself**, and `HeapPoolTest` already asserts on both; (2) `TableMetrics.allMemtablesOnHeapDataSize` ([`TableMetrics.java:93-95`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/metrics/TableMetrics.java#L93-L95)) — a **per-table** proxy for a node-wide counter, so on a single-table node it tracks closely and otherwise does not; (3) heap after a forced full GC, `jcmd <pid> GC.heap_info`. Do **not** use process RSS: `-Xms` pre-commits the heap and hides the live set. |
| **Scope of the limit** | **Global — one pool for the whole node.** `MEMORY_POOL` is a single `static final` instance shared by every table's memtable, not per table or per keyspace. So `N = 1` and there is no multiplier; the flip side is that **nothing is isolated**: any other table's writes consume the same budget. Use a dedicated single-node instance with one user table. |
| **Suggested level** | **Both.** Unit: `ant testsome -Dtest.name=org.apache.cassandra.utils.memory.HeapPoolTest` (re-run as the control), plus `MemtablePoolTest` and `NativeAllocatorTest` in the same package. Cluster: never done, and it is what the dose-response claim in §8 actually needs — the unit tier proves the mechanism, only the cluster tier measures real heap. |

### 9a. Workload — driving the usage operand

The operand is bytes allocated for memtable cell/row writes, so the workload
is ordinary writes that are not flushed.

- Single node, `memtable_allocation_type: heap_buffers`, one table, `-Xmx` pinned.
- **Raise `memtable_cleanup_threshold` toward `1.0`, or the experiment measures the wrong thing.** The soft cleanup threshold triggers a flush of the largest memtable *before* the hard limit is reached, so at the default the node will flush and never park anybody on `hasRoom`. `HeapPoolTest` sets `cleanThreshold = 1.0f` with a no-op cleaner for exactly this reason. On a cluster, set `memtable_cleanup_threshold` high and disable periodic flush (`memtable_flush_period_in_ms = 0`, and no `nodetool flush`).
- Write with a fixed payload size via `cassandra-stress` at steady concurrency (`-rate threads=`), or a small CQL client when the per-write byte count must be exact.

**Deterministic single-shot form (the unit tier, and the one already
executed):** set `limit` to a small number of bytes (`HeapPoolTest` uses 100),
allocate exactly to it, then request one more byte. The boundary is hit on the
first attempt with no race against the cleaner. Prefer this to driving a real
node to its ceiling — README §8.2 rule 2.

### 9b. Scenario A — just reach capacity

Bring `allocated` to just under `limit` and stop.

Unit: `allocator.allocate((int) LIMIT, group)` then assert
`pool.onHeap.used() == LIMIT` — already asserted by `HeapPoolTest`. Cluster:
write until `allMemtablesOnHeapDataSize` plateaus, and confirm the plateau
moves with `memtable_heap_space` across the four values. Writers should not
block and throughput should be steady.

### 9c. Scenario B — try to exceed capacity

Request more once `allocated == limit`. **The disallow branch does not
reject** (§6b) — it parks the caller:

| Expected | Evidence to capture |
|---|---|
| The allocating thread **blocks** on `SubPool.hasRoom` | A timed `Future.get()` that must time out (unit, `HeapPoolTest.testBlocksThenUnblocksOnRelease`), or a **thread dump** showing threads parked in `WaitQueue$Signal.awaitThrowUncheckedOnInterrupt()` at [`MemtableAllocator.java:195`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/utils/memory/MemtableAllocator.java#L195) (cluster). This is the direct evidence README §8.2 rule 5 asks for; write latency alone proves nothing. |
| Usage **unchanged** while parked | `pool.onHeap.used()` still equals `LIMIT` — the disallow branch performs no CAS. |
| Releasing capacity **unblocks** the caller | `released()` → `hasRoom.signalAll()` → the parked call completes. Asserted by the existing test. |
| **The escape hatch overshoots the limit** | With the caller's `OpOrder.Group` marked blocking, `allocated` goes **past** `limit`. `HeapPoolTest.testForcesThroughWhenOpGroupIsBlocking` already demonstrates this; on a cluster it happens naturally during a flush barrier wait ([`ColumnFamilyStore.java:1238`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/ColumnFamilyStore.java#L1238)). |

### 9d. Expected dose-response

If the traced path is the binding limit, across the four values with `-Xmx`
and payload fixed:

- **Plateau usage is linear in `memtable_heap_space`**, and approximately
  equal to it. This is the core prediction.
- **Time-to-first-block falls as the limit falls**, roughly in proportion, at
  constant write rate.
- **But the ceiling is not hard.** §8 predicts overshoot above `limit`
  whenever blocking-marked writes are in flight during a flush barrier. So the
  honest prediction is: the plateau tracks the knob, *with* transient excursions
  above it during flushes, whose size is the in-flight blocking-marked write
  volume and is bounded by nothing here. A run that sees peak > `limit` has
  **confirmed** the case, not refuted it — which is why §9e's second row is
  worded as it is.

### 9e. Interpretation — what each outcome means

| Observation at scenario B | Reading |
|---|---|
| Threads park at `MemtableAllocator.java:195`; usage plateaus at `limit` and the plateau tracks the knob | The check enforces as traced. |
| Usage climbs past `limit` during flushes, with parking otherwise | **The documented escape hatch**, exactly as §6b/§8 predict. Record the overshoot magnitude — that number is the Target-3 material and does not exist anywhere yet. Not a refutation. |
| Usage never reaches `limit`, no parking, flushes instead | `memtable_cleanup_threshold` is binding before this check. Fix the setup (§9a) and re-run; this is a measurement error, not a finding. |
| Plateau flat across all four values | The traced path is not the binding limit. Re-read, do not re-run. |

### 9f. What would refute this case

The case claims `SubPool.tryAllocate()`'s comparison against `limit` gates
memtable buffer allocation, so the sustained on-heap memtable total is bounded
by `memtable_heap_space`. It is refuted if the plateau in
`allMemtablesOnHeapDataSize` (or measured heap) **does not move** when
`memtable_heap_space` is changed across the sweep, while flushing is confirmed
not to be the binding mechanism.

It is **not** refuted by peak usage exceeding `limit` — §8 already says the
ceiling is `limit` plus in-flight blocking-marked volume. A stage-4 run that
reports "the limit was exceeded, therefore the case is wrong" has rediscovered
the escape hatch this case documents.

### 9g. Confounders and controls

- **`memtable_cleanup_threshold` is the dominant confounder** — it flushes before this check binds. Hold it fixed and high across the sweep, and run one control at its default to show the difference.
- **`-Xmx`**, because the default `memtable_heap_space` is derived from it. Pin it; record the resolved limit from the startup log for every arm.
- **The pool is node-wide**, so system keyspaces and any other table share it. One user table, no other traffic, and check `nodetool tablestats` for unexpected memtable activity.
- **GC timing** masks the live set — measure heap only after `jcmd GC.heap_info` forces a full GC, never from RSS.
- **`memtable_allocation_type`** must be `heap_buffers`; `offheap_objects` routes allocations to the sibling case's pool instead.
- **Baseline** at the default with a light write load; **idle control** with the node up and no writes, to establish the non-memtable heap floor that must be subtracted.
- **Flush during measurement** releases capacity and resets the operand. Disable periodic flush and do not issue `nodetool flush` mid-run.

## 10. Provenance

| Field | Content |
|--------|---------|
| **Stage-3 feed** | `3b` — established by deep-reading the source; no stage-1/2 row led here. |
| **Line numbers checked** | 2026-09-22 against the local `cassandra-5.0.9` clone (`git describe --tags`). |
| **Escape hatch / Target-3 note** | `markBlocking()`-marked `OpOrder.Group` silently forces the allocation past `limit` instead of parking (`MemtableAllocator.SubAllocator.allocate():169-197`); see §6b. |
| **Stage-4 feedback** | none yet |

---

## 11. Notes

- The escape hatch (`opGroup.isBlocking()` forcing `allocated(size)` through
  regardless of `limit`) is shared code between this case and
  `memtable_offheap_space-tryAllocate-limit` — it lives in `MemtableAllocator.java`,
  not in either allocator subclass. Any future case touching
  `SubPool.tryAllocate()` (there may be others besides the two memtable
  pools) should check whether it goes through this same
  `MemtableAllocator.SubAllocator.allocate()` path before assuming the
  if-check behaves as a clean reject.
