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
| **Allocation site** | [`HeapPool.Allocator.allocate():52-55`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/utils/memory/HeapPool.java#L52-L55) → `ByteBuffer.allocate(size)` — reached only under `memtable_allocation_type: unslabbed_heap_buffers`; the default `heap_buffers` reaches the same check through `SlabAllocator` instead (§11) |
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
> `HeapPoolTest.java` was written for this case, run on CloudLab node pc80
> against the shared `cassandra-src` clone at `b5f2a54` (the `cassandra-5.0.9`
> tag commit), and passed (`Tests run: 2, Failures: 0, Errors: 0`). It is not
> upstream. **It is recoverable from this repo, though:** its full source sat
> in this case file's former "Verification" section from `a78a249` until the
> three-stage restructure (`e90423c`) removed it —
> `git show e90423c^:cassandra/if-check-exp/memtable/memtable_heap_space-tryAllocate-limit.md`.
> The untracked copy in the `cassandra-src` clone is therefore not the only
> one. Its result is prior evidence, not a stage-4 result; stage 4 should
> re-run it as the control. It constructs `HeapPool` directly, so the
> `memtable_allocation_type` correction below does not affect it. The cluster
> tier was never done.

| Field | Content |
|-------|---------|
| **Testability** | **Config-testable, but restart-only.** `Config.memtable_heap_space` is **not** `volatile` and has **no setter** in `DatabaseDescriptor`; `AbstractAllocatorMemtable.MEMORY_POOL` is `static final`, built once at class initialization from the config ([`:59`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/memtable/AbstractAllocatorMemtable.java#L59), [`createMemtableAllocatorPool():78-86`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/memtable/AbstractAllocatorMemtable.java#L78-L86)). Every capacity value therefore costs a node restart. Checked 2026-09-28. |
| **Constraint knob** | `memtable_heap_space` in `cassandra.yaml` (MiB), **with `memtable_allocation_type: unslabbed_heap_buffers`** — the only type that builds a `HeapPool` ([`AbstractAllocatorMemtable.java:97-99`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/memtable/AbstractAllocatorMemtable.java#L97-L99)), and so the only one that reaches this case's allocation site. **Not `heap_buffers`:** that is the default ([`Config.java:524`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/Config.java#L524)) but it builds a `SlabPool` ([`AbstractAllocatorMemtable.java:100-102`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/memtable/AbstractAllocatorMemtable.java#L100-L102)), which reaches the same check through a different allocator (§11). At the unit tier, bypass config entirely: `new HeapPool(limit, cleanThreshold, cleaner)` directly, as `HeapPoolTest` does, or `AbstractAllocatorMemtable.createMemtableAllocatorPoolInternal(unslabbed_heap_buffers, ...)`, which is `@VisibleForTesting public` ([`:88-92`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/memtable/AbstractAllocatorMemtable.java#L88-L92)). |
| **Capacity values to test** | `memtable_heap_space` ∈ {`128MiB`, `256MiB`, `512MiB`, **default**}. The default is *not* a fixed number — when unset it is auto-sized to `maxMemory() / 4` ([`DatabaseDescriptor.java:586-590`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/DatabaseDescriptor.java#L586-L590)) — so **pin `-Xmx` across the whole sweep**. `-Xms4G -Xmx4G` puts the default near `1024MiB` and makes the four arms a doubling series. In every arm, record the resolved value from the startup line `Global memtable on-heap threshold is enabled at …` ([`DatabaseDescriptor.java:590`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/DatabaseDescriptor.java#L590)). |
| **Usage-side observable** | `SubPool.allocated` on the `onHeap` pool — the running total the check compares. It counts cell buffers **and** the memtable's data-structure overhead, which is charged to the same pool through `markExtraOnHeapUsed()` ([`AbstractAllocatorMemtable.java:196`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/memtable/AbstractAllocatorMemtable.java#L196)). |
| **Instrument** | **No gauge exposes the operand** (README §8.3). Four stock read-outs reach it or its effect, and one gauge is a trap; both are set out below this table. Do **not** use process RSS: `-Xms` pre-commits the heap and hides the live set. |
| **Scope of the limit** | **Global — one pool for the whole node.** `MEMORY_POOL` is a single `static final` instance shared by every table's memtable, not per table or per keyspace. So `N = 1` and there is no multiplier; the flip side is that **nothing is isolated**: any other table's writes consume the same budget. Use a dedicated single-node instance with one user table. |
| **Suggested level** | **Both.** Unit: re-run `HeapPoolTest` as the control, restored from git history as above (`ant testsome -Dtest.name=org.apache.cassandra.utils.memory.HeapPoolTest`). Then run the upstream **`MemtableSizeUnslabbedTest`** (`ant testsome -Dtest.name=org.apache.cassandra.db.memtable.MemtableSizeUnslabbedTest`). It sets `unslabbed_heap_buffers`, asserts `MEMORY_POOL` is a `HeapPool` ([`:43`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/test/unit/org/apache/cassandra/db/memtable/MemtableSizeUnslabbedTest.java#L43)), writes 50,000 partitions, and asserts that the accounted `ownsOnHeap` is within 3% of the memtable's jamm-measured deep size ([`MemtableSizeTestBase.java:200`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/test/unit/org/apache/cassandra/db/memtable/MemtableSizeTestBase.java#L200)). That shows the operand tracks real heap, which is the bridge between the two tiers. `NativeAllocatorTest` runs the same shared `SubPool`/`SubAllocator` code through the off-heap sibling's `NativePool`: it is a shared-code control, not this case's path. There is **no `MemtablePoolTest`** at the tag, although an earlier version of this field named one. Cluster: never done, and it is what the dose-response claim in §8 actually needs — the unit tier proves the mechanism, only the cluster tier measures real heap. |

**Instruments, most direct first:**

1. **Unit tier — the operand itself.** `pool.onHeap.used()` and
   `allocator.onHeap().owns()`; `HeapPoolTest` already asserts on both.
2. **Cluster — proof that the disallow branch fired.** The timer
   `org.apache.cassandra.metrics:type=MemtablePool,name=BlockedOnAllocation`
   ([`MemtablePool.java:63`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/utils/memory/MemtablePool.java#L63))
   is started only on the park path
   ([`MemtableAllocator.java:185`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/utils/memory/MemtableAllocator.java#L185))
   and stopped on wake *or* cancel
   ([`WaitQueue.java:463-470`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/utils/concurrent/WaitQueue.java#L463-L470)).
   So its count rises on every non-escape disallow — including those where the
   re-check at `:187` succeeds and nothing actually sleeps — and **never** on
   an escape-hatch force-through. Its duration percentiles are the park times.
   Read it over JMX, e.g.
   `nodetool sjk mx -mg -b 'org.apache.cassandra.metrics:type=MemtablePool,name=BlockedOnAllocation' -f Count`.
   This is the direct evidence README §8.2 rule 5 asks for; a thread dump
   corroborates it (§9c).
3. **Cluster — the operand, event-sampled.** Each time the cleaner fires,
   `flushLargestMemtable()` logs `Flushing largest … Used total: <on>/<off>` at
   INFO, where `<on>` is `MEMORY_POOL.onHeap.usedRatio()`, i.e.
   `allocated / limit`
   ([`AbstractAllocatorMemtable.java:289-295`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/memtable/AbstractAllocatorMemtable.java#L289-L295)).
   This is the real operand, but only at the moments the cleaner fires.
4. **Cluster — each memtable's peak.** `Enqueuing flush of <ks>.<table>,
   Reason: <reason>, Usage: …`
   ([`ColumnFamilyStore.java:1055`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/ColumnFamilyStore.java#L1055))
   is logged just *before* the memtable is switched out
   ([`:1037-1038`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/ColumnFamilyStore.java#L1037-L1038)),
   so `Usage` is that memtable's peak. `Reason: MEMTABLE_LIMIT` marks a
   cleaner-driven flush.

**Trap — `AllMemtablesOnHeapDataSize` cannot see the part of this case that
matters.** Its javadoc
([`TableMetrics.java:92`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/metrics/TableMetrics.java#L92))
says pending-flush memtables are included, but the gauge reads only each
table's *current* memtable
([`:506-512`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/metrics/TableMetrics.java#L506-L512)
→ [`getMemoryUsageWithIndexes():876-882`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/metrics/TableMetrics.java#L876-L882)).
A flush switches the memtable when it is enqueued, so the gauge drops to ≈0.
The switched-out memtable's bytes still count in `allocated` until the flush
completes, and the escape-hatch overshoot lands in exactly that memtable,
since it comes from writes that preceded the flush barrier. The node-wide sum
`type=Table,name=AllMemtablesOnHeapDataSize` (a `GlobalTableGauge`,
[`:1331-1349`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/metrics/TableMetrics.java#L1331-L1349))
matches the pool's scope but has the same blind spot. Use these gauges to
watch the growth phase, never to read a plateau or an overshoot.

**Real heap**, where it is needed: `jcmd <pid> GC.run`, *then*
`jcmd <pid> GC.heap_info`. `GC.heap_info` on its own does not collect. The
shipped `jvm11-server.options` and `jvm17-server.options` select G1 and do not
set `-XX:+DisableExplicitGC`, so `GC.run` performs a full collection.

### 9a. Workload — driving the usage operand

The operand is bytes allocated for memtable cell/row writes, so the workload
is ordinary writes that are not flushed.

- Single node, `memtable_allocation_type: unslabbed_heap_buffers`, one table, `-Xmx` pinned. **Start from `conf/cassandra.yaml`, not `cassandra_latest.yaml`**: the latter switches to `offheap_objects` and the trie memtable. Keep the default memtable (`skiplist`).
- **Set `memtable_cleanup_threshold: 0.99`** — the highest value a node accepts; anything above `0.99` fails startup with a `ConfigurationException` ([`DatabaseDescriptor.java:772-773`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/DatabaseDescriptor.java#L772-L773)). The default, `1 / (1 + memtable_flush_writers)`, is 0.33 with two flush writers, so the cleaner flushes at a third of `limit` and writers park only if they outrun flushing. `HeapPoolTest` can use `1.0f` because the `HeapPool` constructor does not validate — unit tier only. At `0.99` the cleaner still fires, at 99% of `limit`, so expect writers to park **for the length of each flush**, not permanently.
- Leave the table option `memtable_flush_period_in_ms` at its default `0`, and issue no `nodetool flush` during the growth phase (§9c uses one deliberately).
- Write with a fixed payload via `cassandra-stress` at steady concurrency (`-rate threads=`), or a small CQL client when the per-write byte count must be exact. Writes must outpace flush throughput, or nothing parks.
- Create the keyspace with `durable_writes = false`, as `MemtableSizeTestBase` does ([`:120`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/test/unit/org/apache/cassandra/db/memtable/MemtableSizeTestBase.java#L120)), so no commit-log-pressure flush (`Reason: COMMITLOG_DIRTY`) can release capacity mid-run.

**Deterministic single-shot form (the unit tier, and the one already
executed):** set `limit` to a small number of bytes (`HeapPoolTest` uses 100),
allocate exactly to it, then request one more byte. The boundary is hit on the
first attempt with no race against the cleaner. Prefer this to driving a real
node to its ceiling — README §8.2 rule 2.

### 9b. Scenario A — just reach capacity

Bring `allocated` to just under `limit` and stop.

Unit: `allocator.allocate((int) LIMIT, group)` then assert
`pool.onHeap.used() == LIMIT` — already asserted by `HeapPoolTest`. Cluster:
write until the first cleaner-driven flush, and record its
`Enqueuing flush … Reason: MEMTABLE_LIMIT, Usage:` line and the `Used total`
line from the same moment. Both should sit near `0.99 × limit` and move with
`memtable_heap_space` across the four values. `BlockedOnAllocation` should not
have moved yet. Writers should not block and throughput should be steady.

### 9c. Scenario B — try to exceed capacity

Request more once `allocated == limit`. **The disallow branch does not
reject** (§6b) — it parks the caller. On a cluster, keep writing past the first
cleaner flush: while that flush runs, the new memtable fills the last ~1% of
`limit` and the pool stays full until the flush completes.

| Expected | Evidence to capture |
|---|---|
| The allocating thread **blocks** on `SubPool.hasRoom` | Unit: a timed `Future.get()` that must time out (`HeapPoolTest.testBlocksThenUnblocksOnRelease`). Cluster: the `BlockedOnAllocation` count rising (instrument 2), corroborated by a thread dump in which `MutationStage` threads show `org.apache.cassandra.utils.memory.MemtableAllocator$SubAllocator.allocate(MemtableAllocator.java:195)` ([link](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/utils/memory/MemtableAllocator.java#L195)) just below the wait. **Match on that `MemtableAllocator` frame:** the wait frames themselves belong to `Awaitable` (`Awaitable$AbstractAwaitable.awaitThrowUncheckedOnInterrupt`), not to the `WaitQueue$Signal` an earlier version of this row named. Client write timeouts are a symptom, not evidence. |
| Usage **unchanged** while parked | Unit: `pool.onHeap.used()` still equals `LIMIT` — the disallow branch performs no CAS. Cluster: no stock gauge shows this (see the trap above). |
| Releasing capacity **unblocks** the caller | Unit: `released()` → `hasRoom.signalAll()` → the parked call completes, which the existing test asserts. Cluster: the flush completing (`setDiscarded()` → `released()`) ends the park; `BlockedOnAllocation`'s duration percentiles measure it. |
| **The escape hatch overshoots the limit** | Unit: `HeapPoolTest.testForcesThroughWhenOpGroupIsBlocking` already demonstrates this. Cluster: **rare without provocation** at `memtable_cleanup_threshold: 0.99` with one table, because the cleaner starts each flush at 99% of `limit`, before anyone is parked — so `markBlocking()` ([`ColumnFamilyStore.java:1238`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/ColumnFamilyStore.java#L1238)) usually has nobody to force through. To provoke it, issue `nodetool flush <ks> <table>` **while writers are parked**: its barrier marks their op groups blocking, and on retry they are forced past `limit`. This needs a free `MemtableFlushWriter` thread (`memtable_flush_writers ≥ 2`, the single-data-directory default), or the new flush queues behind the running one. **No stock read-out shows the overshoot reliably** — `Used total` can print above `1.00` only if the cleaner happens to fire in that window. The exact instrument is a Byteman rule on `SubAllocator.allocated(long)` ([`MemtableAllocator.java:204`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/utils/memory/MemtableAllocator.java#L204)), which is called only from the escape hatch ([`:182`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/utils/memory/MemtableAllocator.java#L182)); counting calls and summing `size` measures the overshoot. |

### 9d. Expected dose-response

If the traced path is the binding limit, across the four values with `-Xmx`
and payload fixed:

- **The per-cycle peak is linear in `memtable_heap_space`** — the `Usage` on
  each `MEMTABLE_LIMIT` flush, and `Used total` near `0.99`–`1.00`. This is
  the core prediction, **but on its own it does not isolate this check.** The
  cleaner's trigger, `nextClean = reclaiming + limit × cleanThreshold`
  ([`MemtablePool.java:143`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/utils/memory/MemtablePool.java#L143)),
  is derived from the same `limit`, so a peak that tracks the knob would
  appear even if `tryAllocate()` never refused anything. **The curve counts
  only alongside the park evidence:** `BlockedOnAllocation` rising in every
  arm, with its onset at `Used total` ≈ `1.00`.
- **Time-to-first-block falls as the limit falls**, roughly in proportion, at
  constant write rate.
- **But the ceiling is not hard.** §8 predicts overshoot above `limit`
  whenever blocking-marked writes are in flight during a flush barrier. Its
  size should be set by the writers parked when the barrier is marked, not by
  `limit`: at most roughly `concurrent_writes` (default 32) × bytes per
  mutation. That bound is inferred from the `MutationStage` thread count, not
  traced line by line, so treat it as a prediction and test it by varying the
  payload or `concurrent_writes`. A run that sees peak > `limit` has
  **confirmed** the case, not refuted it — which is why §9e's second row is
  worded as it is.

### 9e. Interpretation — what each outcome means

| Observation at scenario B | Reading |
|---|---|
| `BlockedOnAllocation` rises in every arm, threads park at `MemtableAllocator.java:195`, and the per-cycle peak tracks the knob | The check enforces as traced. |
| Usage climbs past `limit` during a flush (Byteman sum > 0, or `Used total` > `1.00`), with parking otherwise | **The documented escape hatch**, exactly as §6b/§8 predict. Record the overshoot magnitude — that number is the Target-3 material and does not exist anywhere yet. Not a refutation. |
| No parking, `BlockedOnAllocation` flat, and every flush is `Reason: MEMTABLE_LIMIT` at a peak well under `limit` | The cleaner is binding before this check (threshold too low, or writes not outpacing flush). Fix the setup (§9a) and re-run; this is a measurement error, not a finding. |
| The peak tracks the knob and `Used total` reaches `1.00`, but `BlockedOnAllocation` never moves | The cleaner governs the ceiling and this check never refuses. §6b's disallow effect is wrong. Re-read, do not re-run. |
| Peak flat across all four values | The traced `limit` is not what governs memtable size. Re-read, do not re-run — but first check that the startup log shows `unslabbed_heap_buffers` and a resolved limit that actually changed. |

### 9f. What would refute this case

The case claims `SubPool.tryAllocate()`'s comparison against `limit` gates
memtable buffer allocation, parking writers once the pool is full, so the
sustained on-heap memtable total is bounded by `memtable_heap_space`. Either
of these refutes it:

- **No park at the limit.** Writes outpace flushing and `Used total` reaches
  `1.00`, yet `BlockedOnAllocation` never moves and no thread is found at
  `MemtableAllocator.java:195`, in any arm.
- **The per-cycle peak does not move** when `memtable_heap_space` is changed
  across the sweep, with the resolved limit confirmed changed in the startup
  log.

A peak that moves with the knob is **not** enough to confirm the case on its
own, because the cleaner's threshold scales with the same `limit` (§9d).

It is **not** refuted by peak usage exceeding `limit` — §8 already says the
ceiling is `limit` plus in-flight blocking-marked volume. A stage-4 run that
reports "the limit was exceeded, therefore the case is wrong" has rediscovered
the escape hatch this case documents.

### 9g. Confounders and controls

- **`memtable_allocation_type`** must be `unslabbed_heap_buffers`. The default `heap_buffers` builds a `SlabPool` and exercises the §11 variant, not this path; `offheap_objects` moves cell data to the sibling case's off-heap pool. Confirm the pool in every arm from the `debug.log` line `Memtables allocating with on-heap buffers` ([`AbstractAllocatorMemtable.java:98`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/memtable/AbstractAllocatorMemtable.java#L98)).
- **`memtable_cleanup_threshold` is the dominant confounder.** It flushes before this check binds, and its trigger scales with the same `limit` (§9d). Hold it at `0.99` across the sweep, and run one control arm at its default to show the difference.
- **`-Xmx`**, because the default `memtable_heap_space` is derived from it. Pin it; record the resolved limit from the startup log for every arm.
- **The pool is node-wide**, so system keyspaces and any other table share it. One user table, no other traffic, and check `nodetool tablestats` for unexpected memtable activity.
- **Memtable implementation.** `trie` reserves buffer space and accounts differently from `skiplist` (see `MemtableSizeTestBase`'s `unusedReservedMemory` adjustment). Keep the default `skiplist` in every arm.
- **Other flush triggers** release capacity and reset the operand: commit-log pressure, the table's `memtable_flush_period_in_ms`, and `nodetool flush`. Use `durable_writes = false`, leave the period at `0`, and read the `Reason:` on every `Enqueuing flush` line. Any reason other than `MEMTABLE_LIMIT`, apart from the deliberate §9c `nodetool flush`, contaminates that cycle.
- **GC timing** masks the live set — measure heap only after `jcmd <pid> GC.run`, never from RSS.
- **Baseline** at the default with a light write load; **idle control** with the node up and no writes, to establish the non-memtable heap floor that must be subtracted.

## 10. Provenance

| Field | Content |
|--------|---------|
| **Stage-3 feed** | `3b` — established by deep-reading the source; no stage-1/2 row led here. |
| **Line numbers checked** | 2026-09-22 against the local `cassandra-5.0.9` clone (`git describe --tags`). Citations added to §1, §9 and §11 on 2026-09-28 checked against a fresh clone of the same tag (`b5f2a54`). |
| **Escape hatch / Target-3 note** | `markBlocking()`-marked `OpOrder.Group` silently forces the allocation past `limit` instead of parking (`MemtableAllocator.SubAllocator.allocate():169-197`); see §6b. |
| **Stage-4 feedback** | none yet |
| **Notes** | §9 revised 2026-09-28, before any stage-4 run: the knob corrected from `heap_buffers` (builds a `SlabPool`) to `unslabbed_heap_buffers`; `memtable_cleanup_threshold` capped at the accepted `0.99`; `AllMemtablesOnHeapDataSize` shown blind to switched-out memtables, and `BlockedOnAllocation`, the cleaner's `Used total` and the flush log added as instruments; the cleaner-trigger confound added to §9d–§9f; the nonexistent `MemtablePoolTest` replaced by `MemtableSizeUnslabbedTest`; `HeapPoolTest` shown recoverable from git history. |

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
- **This case's allocation site is reached only under
  `memtable_allocation_type: unslabbed_heap_buffers`**
  ([`AbstractAllocatorMemtable.java:97-99`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/memtable/AbstractAllocatorMemtable.java#L97-L99)).
  The default, `heap_buffers`
  ([`Config.java:524`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/Config.java#L524),
  and the shipped `conf/cassandra.yaml`), builds `SlabPool(heapLimit, 0, …)`
  ([`:100-102`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/memtable/AbstractAllocatorMemtable.java#L100-L102)).
  That path reaches the **same check** on the same `onHeap` `SubPool`, through
  [`SlabAllocator.allocate():89`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/utils/memory/SlabAllocator.java#L89),
  with the same park-or-force-through decision point. What differs is the
  allocation: cells up to 128 KiB are sliced from 1 MiB on-heap regions
  ([`SlabAllocator.java:139`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/utils/memory/SlabAllocator.java#L139)),
  and larger ones get their own `ByteBuffer.allocate(size)`. So heap is held
  in whole regions while `size` is what gets accounted; `MemtableSizeTestBase`
  allows a 1 MiB `SLAB_OVERHEAD` for the gap. This is a variant of this case
  on the default path, not yet written up — the parallel of the off-heap
  sibling's note on `offheap_buffers`. Found 2026-09-28: an earlier §9, and
  the never-run cluster trigger before it, assumed `heap_buffers` built a
  `HeapPool`.
