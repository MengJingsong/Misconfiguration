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

**Stage 3 writes this section; stage 3 never runs it** — no measured numbers
and no verdict here; results go to
[`../../stage4-runtime-verification/README.md`](../../stage4-runtime-verification/README.md).
The test changes `memtable_heap_space`, writes faster than flushes free memory,
and checks that writers wait at the limit. **Done so far:** the unit tier's
`HeapPoolTest` was written and passed on 2026-09-16, before stage 4 existed
(CloudLab node pc80, clone at `b5f2a54`, `Tests run: 2, Failures: 0`;
prior evidence, not a stage-4 result). The cluster tier has never been run.

### 9a. Procedure and conclusions

**Testability:** config, **restart-only**. The test must use
`memtable_allocation_type: unslabbed_heap_buffers`: the default,
`heap_buffers`, reaches the same check through a different allocator (§11).

**Claim under test:** `memtable_heap_space` caps the node-wide on-heap memtable
pool. When the pool is full, a writer waits until a flush frees memory; it is
not rejected. One exception: writes that a starting flush is waiting on are
forced past the limit (the escape hatch, §6b).

**Procedure:**

1. **Unit tier** — re-run `HeapPoolTest` (the limit holds, the next writer
   waits, the escape hatch forces through). Run `MemtableSizeUnslabbedTest`
   (the pool's counter matches real heap within 3%).
2. **Cluster tier** — one node, four runs: `memtable_heap_space` = 128, 256,
   512 MiB, and the default (about 1024 MiB with a 4 GiB heap).
3. **At each value:** idle control → **A**, write until the first
   limit-driven flush → **B**, keep writing faster than flushes finish →
   **C**, force a flush while writers are waiting, to trigger the escape hatch.
4. **Compare** with the prediction and read the result below.

**Prediction:**

- **A:** each limit-driven flush starts at about 99% of the limit, so the peak
  is proportional to the knob. No writer has waited yet.
- **B:** writers wait while each flush runs; the wait count rises in every
  run, and the counter does not grow while they wait.
- **C:** the counter goes above the limit, by no more than the bytes forced
  through the escape hatch. The excess should be small — roughly the
  concurrent writers × one write's size (an estimate, not traced line by
  line) — and it disappears when the flush ends.

**Conclusions:**

| Result | Conclusion |
|---|---|
| Writers wait in every run, the peak follows the knob, and outside scenario C the counter never passes the limit | **Confirmed** |
| The counter passes the limit, by no more than the bytes forced through the escape hatch | **Escape hatch as recorded** — expected. Record its size (Target-3 material). |
| The counter passes the limit by more than the escape hatch explains, or with no escape-hatch call at all | **Refuted** — the check does not cap usage. |
| Real heap grows well beyond the counter | **Refuted** — the counter does not track real heap; §8's ceiling claim is wrong. |
| The peak is flat across the four values (and the startup log shows the limit did change) | **Refuted** — not the binding limit. Re-read, do not re-run. |
| The peak follows the knob and the pool reaches 100%, but no writer ever waits | **Not confirmed** — the flush trigger, not this check, sets the ceiling; §6b is wrong. Re-read. |
| No writer waits, and every flush starts well below the limit | **Invalid run** — flushing keeps up with the writes. Fix the setup (9b, 9c) and re-run. |

**Why the peak alone is not enough:** the automatic flush trigger is itself
set at a fraction of the same limit, so the peak would follow the knob even if
this check never refused anything. Only the waits prove the check fired.

### 9b. Setup

| Field | Content |
|-------|---------|
| **Constraint knob** | `memtable_heap_space` in `cassandra.yaml` (MiB). Restart-only: the `Config` field is not `volatile`, has no setter, and the pool is a `static final` built once at class load ([`AbstractAllocatorMemtable.java:59`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/memtable/AbstractAllocatorMemtable.java#L59), [`:78-86`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/memtable/AbstractAllocatorMemtable.java#L78-L86)). Unit tier: construct `new HeapPool(limit, cleanThreshold, cleaner)` directly, or call the `@VisibleForTesting` `createMemtableAllocatorPoolInternal(unslabbed_heap_buffers, …)` ([`:88-92`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/memtable/AbstractAllocatorMemtable.java#L88-L92)). |
| **Confirm it took effect** | `logs/system.log`: `Global memtable on-heap threshold is enabled at …` ([`DatabaseDescriptor.java:590`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/DatabaseDescriptor.java#L590)). `logs/debug.log`: `Memtables allocating with on-heap buffers` — the only line that proves the `HeapPool` was built ([`AbstractAllocatorMemtable.java:98`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/memtable/AbstractAllocatorMemtable.java#L98)). |
| **Capacity values** | `128MiB`, `256MiB`, `512MiB`, and unset. Unset means `maxMemory() / 4` ([`DatabaseDescriptor.java:586-590`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/DatabaseDescriptor.java#L586-L590)), so the heap size must be pinned for the default to be a fixed number. |
| **Scope** | Global: one pool for the whole node, shared by every table. N = 1, but nothing is isolated — any other table's writes use the same budget. |
| **Level** | Both. Unit: `HeapPoolTest` (not upstream; see 9c), `MemtableSizeUnslabbedTest`. `NativeAllocatorTest` runs the same shared `SubPool` code via the off-heap pool — a shared-code control, not this path. There is no `MemtablePoolTest` at the tag. |

**Hold fixed:**

| Setting | Value | Why |
|---|---|---|
| `memtable_allocation_type` | `unslabbed_heap_buffers` | The only type that builds a `HeapPool` ([`AbstractAllocatorMemtable.java:97-99`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/memtable/AbstractAllocatorMemtable.java#L97-L99)). The default `heap_buffers` ([`Config.java:524`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/Config.java#L524)) builds a `SlabPool` ([`:100-102`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/memtable/AbstractAllocatorMemtable.java#L100-L102)); `offheap_objects` moves cell data to the sibling case's pool. |
| `memtable_cleanup_threshold` | `0.99` | The flush trigger. The default (`1 / (1 + memtable_flush_writers)`, 0.33 with two writers) flushes at a third of the limit, so writers rarely wait. `0.99` is the highest value accepted; above it startup fails ([`DatabaseDescriptor.java:772-773`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/DatabaseDescriptor.java#L772-L773)). |
| JVM heap | `-Xms4G -Xmx4G` | The default limit is derived from the heap size. |
| Memtable implementation | default `skiplist` | `trie` reserves and accounts differently. Start from `conf/cassandra.yaml`, **not** `conf/cassandra_latest.yaml`, which switches to `trie` and `offheap_objects`. |
| Keyspace `durable_writes` | `false` | Stops commit-log-pressure flushes (`Reason: COMMITLOG_DIRTY`) from freeing memory mid-run, as `MemtableSizeTestBase` does ([`:120`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/test/unit/org/apache/cassandra/db/memtable/MemtableSizeTestBase.java#L120)). `cassandra-stress` creates its keyspace with `durable_writes = true`, so pre-create it (9c). |
| Table `memtable_flush_period_in_ms` | `0` (default) | A periodic flush would free memory on its own schedule. |
| `memtable_flush_writers` | ≥ 2 (default with one data directory) | Scenario C's forced flush needs a free flush thread, or it queues behind the running one. |
| `concurrent_writes` | `32` (default) | Sets how many writers can be waiting, and so the expected size of the escape-hatch excess. |
| Traffic | one user table, nothing else | The pool is node-wide; check `bin/nodetool tablestats` for unexpected memtable activity. |

**Controls:**

- **Idle run** — node up, no writes: the non-memtable heap floor to subtract.
- **Cleanup-threshold control** — one run at the default `memtable_cleanup_threshold`, to show the difference the flush trigger makes.

**Reset between runs:** stop the node (`bin/nodetool stopdaemon`), empty the
`data_file_directories`, `commitlog_directory` and `saved_caches_directory`
set in `cassandra.yaml`, edit the knob, start again.

### 9c. Workload

Ordinary writes that are not flushed, faster than flushes can finish. For the
exact boundary, prefer the unit tier: a tiny limit (`HeapPoolTest` uses 100
bytes) lands on the boundary on the first attempt, with no race against the
flush.

```bash
# unit tier — copy the committed harness copy of HeapPoolTest (not upstream)
# into the local clone, then run both tests:
cp <misconfiguration-repo>/cassandra/if-check-exp/stage4-runtime-verification/harness/memtable_heap_space-tryAllocate-limit/HeapPoolTest.java \
   test/unit/org/apache/cassandra/utils/memory/HeapPoolTest.java
ant testsome -Dtest.name=org.apache.cassandra.utils.memory.HeapPoolTest
ant testsome -Dtest.name=org.apache.cassandra.db.memtable.MemtableSizeUnslabbedTest

# cluster tier — pre-create the stress keyspace without durable writes
bin/cqlsh -e "CREATE KEYSPACE keyspace1 WITH replication = {'class': 'SimpleStrategy', 'replication_factor': 1} AND durable_writes = false;"
tools/bin/cassandra-stress write n=<ops> -col 'size=FIXED(<bytes>)' -rate threads=<T>
```

The keyspace is created `IF NOT EXISTS` by `cassandra-stress`, so the
pre-created one is kept. Raise `threads` or `size` until writers wait (9d,
disallow evidence); if they never do, the run is invalid (9a).

### 9d. Observables

| Observable | How to read it | When to sample | Trap |
|---|---|---|---|
| **Usage counter** — `SubPool.allocated` on the `onHeap` pool, which includes the memtable's own overhead ([`AbstractAllocatorMemtable.java:196`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/memtable/AbstractAllocatorMemtable.java#L196)) | Unit: `pool.onHeap.used()`, `allocator.onHeap().owns()`. Cluster: no gauge exposes it. Two log lines do: `Flushing largest … Used total: <on>/<off>`, where `<on>` is `allocated / limit` ([`AbstractAllocatorMemtable.java:289-295`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/memtable/AbstractAllocatorMemtable.java#L289-L295)); and `Enqueuing flush of <ks>.<table>, Reason: <reason>, Usage: …`, logged before the switch, so `Usage` is that memtable's peak ([`ColumnFamilyStore.java:1055`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/ColumnFamilyStore.java#L1055), [`:1037-1038`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/ColumnFamilyStore.java#L1037-L1038)). | Only when a flush fires | **Do not use `AllMemtablesOnHeapDataSize`.** It reads only the current memtable ([`TableMetrics.java:506-512`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/metrics/TableMetrics.java#L506-L512), [`:876-882`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/metrics/TableMetrics.java#L876-L882)) despite its javadoc ([`:92`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/metrics/TableMetrics.java#L92)), so it drops to ≈0 when a flush starts, while the old memtable — where the escape-hatch excess lands — still counts. The node-wide sum ([`:1331-1349`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/metrics/TableMetrics.java#L1331-L1349)) has the same blind spot. Fine for watching growth, never for a peak. Flushes with any `Reason` other than `MEMTABLE_LIMIT` (except scenario C's) contaminate that cycle. |
| **Disallow evidence** — writers waiting | Timer `org.apache.cassandra.metrics:type=MemtablePool,name=BlockedOnAllocation` ([`MemtablePool.java:63`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/utils/memory/MemtablePool.java#L63)): `bin/nodetool sjk mx -mg -b 'org.apache.cassandra.metrics:type=MemtablePool,name=BlockedOnAllocation' -f Count`. Thread dump (`jcmd <pid> Thread.print`): `MutationStage` threads with frame `MemtableAllocator$SubAllocator.allocate(MemtableAllocator.java:195)` ([link](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/utils/memory/MemtableAllocator.java#L195)). | Before and after each scenario; thread dumps during B | The timer starts only on the wait path ([`MemtableAllocator.java:185`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/utils/memory/MemtableAllocator.java#L185)) and stops on wake or cancel ([`WaitQueue.java:463-470`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/utils/concurrent/WaitQueue.java#L463-L470)). So it counts waits whose re-check succeeded too, and **never** counts an escape-hatch force-through. Match the `MemtableAllocator` frame; the wait frames themselves are `Awaitable$AbstractAwaitable…`. Client timeouts are a symptom, not evidence. |
| **Bypass volume** — bytes forced through the escape hatch | Byteman rule on `SubAllocator.allocated(long)` ([`MemtableAllocator.java:204`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/utils/memory/MemtableAllocator.java#L204)), called only from the escape hatch ([`:182`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/utils/memory/MemtableAllocator.java#L182)): count calls, sum `size`. **Not written yet.** | Throughout scenario C | No stock read-out shows the excess reliably: `Used total` goes above `1.00` only if a flush happens to fire in that window. |
| **Real heap** | `jcmd <pid> GC.run`, then `jcmd <pid> GC.heap_info` | Idle control, and end of A and B | `GC.heap_info` alone does not collect. The shipped `jvm11/17-server.options` use G1 without `-XX:+DisableExplicitGC`, so `GC.run` does a full collection. Never use process RSS: `-Xms` pre-commits the heap. |

### 9e. Running the scenarios

**Unit tier:** run the three commands in 9c. Record pass/fail and the
asserted values. `HeapPoolTest` builds the `HeapPool` directly, so the
allocation-type setting does not affect it.

**Cluster tier, for each capacity value:**

1. **Control run** — set the knob, reset (9b), start the node. Grep both
   confirmation lines (9b). With no writes, record real heap (9d).
2. **Scenario A — reach the limit** — pre-create the keyspace and start the
   stress command (9c). Watch `logs/system.log` for the first
   `Reason: MEMTABLE_LIMIT`. Record that `Usage` line, the `Used total` line
   from the same moment, and the `BlockedOnAllocation` count.
3. **Scenario B — try to exceed the limit** — keep writing past the first
   limit-driven flush. Record `BlockedOnAllocation` count and percentiles
   before and after, take two or three thread dumps during flushes, and list
   every `Enqueuing flush` line with its `Reason`.
4. **Scenario C — escape hatch** — with the Byteman rule loaded, wait until
   the `BlockedOnAllocation` count is rising, then run
   `bin/nodetool flush keyspace1 standard1`. Record the Byteman call count
   and byte sum, and any `Used total` above `1.00`.

Stop when each scenario's records are taken; a run where no writer ever
waits is invalid (9a) — fix the workload and repeat it.

**Record for stage 4:** the `cassandra.yaml` diff and JVM options in force,
the exact commands, and every reading above, per capacity value.

## 10. Provenance

| Field | Content |
|--------|---------|
| **Stage-3 feed** | `3b` — established by deep-reading the source; no stage-1/2 row led here. |
| **Line numbers checked** | 2026-09-22 against the local `cassandra-5.0.9` clone (`git describe --tags`). Citations added to §1, §9 and §11 on 2026-09-28 checked against a fresh clone of the same tag (`b5f2a54`). |
| **Escape hatch / Target-3 note** | `markBlocking()`-marked `OpOrder.Group` silently forces the allocation past `limit` instead of parking (`MemtableAllocator.SubAllocator.allocate():169-197`); see §6b. |
| **Stage-4 feedback** | none yet |
| **Notes** | §9 revised 2026-09-28, before any stage-4 run: the knob corrected from `heap_buffers` (builds a `SlabPool`) to `unslabbed_heap_buffers`; `memtable_cleanup_threshold` capped at the accepted `0.99`; `AllMemtablesOnHeapDataSize` shown blind to switched-out memtables, and `BlockedOnAllocation`, the cleaner's `Used total` and the flush log added as instruments; the cleaner-trigger confound added to §9d–§9f; the nonexistent `MemtablePoolTest` replaced by `MemtableSizeUnslabbedTest`; `HeapPoolTest` shown recoverable from git history. Later the same day §9 was restructured to the new template layout (9a summary for review, 9b–9e runbook); the old §9d "time to first wait falls with the limit" prediction was dropped as redundant, and a `cassandra-stress` keyspace step was added because stress creates its keyspace with `durable_writes = true`. §9c amended 2026-09-28 (stage-4 runbook defect #1, approved by Jingsong): the unit tier copies `HeapPoolTest` from the committed stage-4 harness instead of restoring it from git history; the test code is the same. §9a unchanged. |

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
