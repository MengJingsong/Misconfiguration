# memtable_heap_space — bytebuffer

> **Index:** [../_INDEX.md](../_INDEX.md)
>
> **Source:** apache/cassandra @ tag `cassandra-5.0.9`

## 1. Location

| Field | Content |
|-------|---------|
| **Case ID** | MEMTABLE_HEAP_SPACE-BYTEBUFFER |
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

## 2. Module

| Field | Content |
|-------|---------|
| **Module** | Storage engine — memtable memory allocation (`utils/memory`, `db/memtable`) |
| **One-line role** | Tracks and bounds the JVM heap / off-heap bytes used by in-memory memtables (the write-path buffer before data is flushed to disk as SSTables). |

## 3. Capacity-overflow check

| Field | Content |
|-------|---------|
| **Is this a capacity/overflow check?** | Yes — a running-total counter (`allocated`) plus a requested increment (`size`) compared against a fixed ceiling (`limit`). |
| **Usage-side operand** | `allocated` — `volatile long` on `SubPool`, the running total of bytes currently allocated from this pool. |
| **Limit-side operand** | `limit` — `final long` on `SubPool`, set once at construction. |
| **Limit type** | Configuration (`memtable_heap_space`), with an auto-sized default. |

**Limit initialization path** (declare → configure/derive → store → read at the check):

1. [`Config.java:186-187`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/Config.java#L186-L187) — declared: `memtable_heap_space` (`DataStorageSpec.IntMebibytesBound`).
2. [`DatabaseDescriptor.java:586-590`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/DatabaseDescriptor.java#L586-L590) — configured/derived: if unset, auto-sized to `Runtime.getRuntime().maxMemory() / 4`; validated `> 0`.
3. [`DatabaseDescriptor.java:4057`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/DatabaseDescriptor.java#L4057) — exposed via `getMemtableHeapSpaceInMiB()`.
4. [`AbstractAllocatorMemtable.java:81`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/memtable/AbstractAllocatorMemtable.java#L81) — read and converted to bytes: `heapLimit = getMemtableHeapSpaceInMiB() << 20`.
5. [`MemtablePool.java:55-60`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/utils/memory/MemtablePool.java#L55-L60) & [`MemtablePool.java:117-121`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/utils/memory/MemtablePool.java#L117-L121) — stored: `MemtablePool` constructor passes `maxOnHeapMemory` into `getSubPool(limit, cleanThreshold)`, which sets `SubPool.limit` — this is what `tryAllocate()` reads at the check.

## 4. Branch semantics

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

## 5. Code path: allow-branch → object creation

1. [`MemtablePool.java:156-160`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/utils/memory/MemtablePool.java#L156-L160) — allow branch taken, `allocated` bumped via CAS, returns `true`.
2. [`MemtableAllocator.java:175-177`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/utils/memory/MemtableAllocator.java#L175-L177) — `SubAllocator.allocate()`: `if (parent.tryAllocate(size)) { acquired(size); return; }` — caller sees success, marks the memory acquired, returns normally.
3. [`HeapPool.java:52-55`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/utils/memory/HeapPool.java#L52-L55) — `HeapPool.Allocator.allocate(int size, OpOrder.Group opGroup)`: calls `super.onHeap().allocate(size, opGroup)` (steps 1-2 above), then **object creation**: `return ByteBuffer.allocate(size);`.

**Note — accounting and object creation are decoupled (same as the off-heap
sibling case):** step 3's `ByteBuffer.allocate(size)` runs unconditionally
after `onHeap().allocate(size, opGroup)` *returns*, regardless of how it
returned. The full disallow-branch behavior lives in
[`MemtableAllocator.java:169-197`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/utils/memory/MemtableAllocator.java#L169-L197)
(`SubAllocator.allocate()`), which this case's step 2 only shows the
allow-branch half of:

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

## 6. Object & resource

| Field | Content |
|-------|---------|
| **Object created** | `java.nio.ByteBuffer` — the buffer backing a memtable cell/row write. |
| **Resource consumed** | JVM heap bytes — exactly `size` bytes per call, the caller-supplied write size. |
| **Rough sizing** | Equal to the `size` parameter threaded in from the write path (cell/row serialized size) — no fixed struct size; scales with write payload. |
| **Lifetime / release** | Released via `SubPool.released(size)` (`MemtablePool.java:192-197`) when the owning `SubAllocator` is discarded (memtable flushed/discarded) — signals `hasRoom` to unblock any waiters. |

## Verification

Line numbers checked against the local pinned-tag clone. Per
[README.md § Verifying a case](../README.md#verifying-a-case-triggering-the-disallow-branch),
line-checking alone does not earn `Status: verified` — a designed experiment
must actually drive execution into the disallow branch with recorded
evidence. This section is written to be directly executable: follow it
as-is to run the verification.

### What "hitting the disallow branch" looks like here

Per the §5 note above, there is **no rejected write to look for**. The two
observable outcomes are: (a) the calling thread **blocks** on
`SubPool.hasRoom` until something releases memory, or (b) if the op is
already part of a flush barrier's "blocking" set, the allocation **silently
overshoots** `limit`. The experiment below triggers and captures evidence
of both, at the unit level, which is the primary/preferred trigger per the
README methodology (deterministic, no cluster or flush-timing races needed).
No existing unit test in this codebase covers `HeapPool`'s blocking
behavior directly (checked `test/unit/org/apache/cassandra/utils/memory/` —
only `NativeAllocatorTest.java` exists there, covering the off-heap sibling
case's identical `SubPool.tryAllocate()` code via `NativeAllocator`). The
test below is a new file, structured the same way as
`NativeAllocatorTest.testBookKeeping()` so it fits the existing test style.

### Trigger: unit test (primary — run this)

**Create** `test/unit/org/apache/cassandra/utils/memory/HeapPoolTest.java`
in the local Cassandra clone with the following content:

```java
/*
 * Licensed to the Apache Software Foundation (ASF) under one
 * or more contributor license agreements.  See the NOTICE file
 * distributed with this work for additional information
 * regarding copyright ownership.  The ASF licenses this file
 * to you under the Apache License, Version 2.0 (the
 * "License"); you may not use this file except in compliance
 * with the License.  You may obtain a copy of the License at
 *
 *    http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing,
 * software distributed under the License is distributed on an
 * "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY
 * KIND, either express or implied.  See the License for the
 * specific language governing permissions and limitations
 * under the License.
 */
package org.apache.cassandra.utils.memory;

import java.nio.ByteBuffer;
import java.util.concurrent.Callable;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.TimeoutException;

import org.junit.After;
import org.junit.Assert;
import org.junit.Before;
import org.junit.Test;

import org.apache.cassandra.utils.concurrent.ImmediateFuture;
import org.apache.cassandra.utils.concurrent.OpOrder;

/**
 * Verification experiment for the if-check-exp case
 * memtable/memtable_heap_space-bytebuffer.md: drives execution into the
 * disallow branch of MemtablePool.SubPool.tryAllocate() (MemtablePool.java:156)
 * via the on-heap path (HeapPool.Allocator -> MemtableAllocator.SubAllocator),
 * and captures direct evidence of both disallow-branch outcomes:
 *   1. the calling thread blocking on SubPool.hasRoom (testBlocksThenUnblocksOnRelease)
 *   2. the isBlocking() escape hatch overshooting the limit (testForcesThroughWhenOpGroupIsBlocking)
 */
public class HeapPoolTest
{
    private static final long LIMIT = 100; // bytes - deterministic single-shot trigger

    private ExecutorService exec;
    private OpOrder order;
    private OpOrder.Group group;
    private HeapPool pool;
    private HeapPool.Allocator allocator;

    @Before
    public void setUp()
    {
        exec = Executors.newSingleThreadExecutor();
        order = new OpOrder();
        group = order.start();
        // cleanThreshold=1.0f and a no-op cleaner: we are testing the HARD
        // limit in tryAllocate(), not the soft needsCleaning() threshold, so
        // the cleaner should never need to run in this test.
        pool = new HeapPool(LIMIT, 1.0f, () -> ImmediateFuture.success(true));
        allocator = (HeapPool.Allocator) pool.newAllocator("if_check_exp_heap_pool_test");
    }

    @After
    public void tearDown()
    {
        exec.shutdownNow();
    }

    /**
     * Evidence path 1: fill the pool exactly to LIMIT, then request one more
     * byte. tryAllocate() must return false (100 + 1 > 100) -> the disallow
     * branch -> the calling thread parks in
     * WaitQueue$Signal.awaitThrowUncheckedOnInterrupt() (MemtableAllocator.java:195)
     * because opGroup.isBlocking() is false at this point.
     *
     * We prove the park with a timed Future.get() that must time out. We then
     * release capacity (SubAllocator.released(), MemtableAllocator.java:244-256,
     * which calls SubPool.released() -> hasRoom.signalAll(), MemtablePool.java:192-197)
     * and prove the parked call then completes and returns a correctly-sized
     * ByteBuffer, with pool usage reflecting the net allocation.
     */
    @Test
    public void testBlocksThenUnblocksOnRelease() throws Exception
    {
        // fill exactly to the limit: tryAllocate(100) -> 0 + 100 <= 100 -> allow branch
        ByteBuffer first = allocator.allocate((int) LIMIT, group);
        Assert.assertEquals(LIMIT, first.capacity());
        Assert.assertEquals(LIMIT, pool.onHeap.used());
        Assert.assertEquals(LIMIT, allocator.onHeap().owns());

        // request 1 more byte: tryAllocate(1) -> 100 + 1 > 100 -> DISALLOW BRANCH
        Callable<ByteBuffer> overLimit = () -> allocator.allocate(1, group);
        Future<ByteBuffer> pending = exec.submit(overLimit);

        // EVIDENCE 1: the call must NOT complete - it is parked on hasRoom,
        // not rejected and not silently succeeding.
        boolean timedOut = false;
        try
        {
            pending.get(300, TimeUnit.MILLISECONDS);
        }
        catch (TimeoutException e)
        {
            timedOut = true;
        }
        Assert.assertTrue("expected the over-limit allocate() to block, but it returned instead", timedOut);
        // usage must be unchanged while parked - the disallow branch performed no CAS
        Assert.assertEquals(LIMIT, pool.onHeap.used());

        // release 50 bytes from the first allocation -> SubPool.released(50)
        // -> hasRoom.signalAll() -> wakes the parked thread -> it retries
        // tryAllocate(1): 50 + 1 <= 100 -> now succeeds via the allow branch.
        allocator.onHeap().released(50);

        // EVIDENCE 2: the previously-parked call now completes and returns
        // a correctly-sized ByteBuffer.
        ByteBuffer second = pending.get(5, TimeUnit.SECONDS);
        Assert.assertEquals(1, second.capacity());
        Assert.assertEquals(LIMIT - 50 + 1, pool.onHeap.used());
    }

    /**
     * Evidence path 2: the escape hatch. Fill to the limit as above, then
     * mark this opGroup's barrier "blocking" BEFORE requesting the extra
     * byte, so opGroup.isBlocking() is already true when tryAllocate() fails.
     * Per MemtableAllocator.java:180-184, this takes the force-through path
     * (allocated(size)) instead of parking - proving the if-check's disallow
     * branch does not stop this class of caller, only non-blocking ones.
     */
    @Test
    public void testForcesThroughWhenOpGroupIsBlocking() throws Exception
    {
        ByteBuffer first = allocator.allocate((int) LIMIT, group);
        Assert.assertEquals(LIMIT, pool.onHeap.used());

        // mark this group's in-flight op as "blocking", the same way a flush
        // barrier does for writes it must wait out (ColumnFamilyStore.java:1238)
        OpOrder.Barrier barrier = order.newBarrier();
        barrier.issue();
        barrier.markBlocking();

        // tryAllocate(1) still returns false (100 + 1 > 100), but this time
        // opGroup.isBlocking() is true, so allocate() takes the escape hatch
        // and returns IMMEDIATELY without parking.
        ByteBuffer second = allocator.allocate(1, group);
        Assert.assertEquals(1, second.capacity());

        // EVIDENCE: usage now exceeds LIMIT - the hard cap was overshot.
        Assert.assertEquals(LIMIT + 1, pool.onHeap.used());
        Assert.assertTrue("expected pool usage to exceed the configured limit via the escape hatch",
                           pool.onHeap.used() > LIMIT);
    }
}
```

**Run it** from the root of the local Cassandra clone
(`Downloads\cassandra-cassandra-5.0.9` on `heisenberg-laptop`):

```
ant testsome -Dtest.name=org.apache.cassandra.utils.memory.HeapPoolTest
```

(`build.xml`'s `testsome` target is the same one the codebase's own docs use
to run a single test class, e.g. its usage example at `build.xml:1379`.)

**Expected result and what it proves:**

- Both `@Test` methods pass.
- `testBlocksThenUnblocksOnRelease` passing proves: (1) the disallow branch
  was actually reached — the over-limit call provably did not return within
  300ms (`TimeoutException` caught, asserted) while a non-blocking op was
  pending — ruling out "it just happened to be slow"; (2) it is the *same*
  if-check and *same* release mechanism described in §§3-5 — the call only
  completes after `SubAllocator.released()` is invoked, and completes with
  exactly the expected post-release usage number.
- `testForcesThroughWhenOpGroupIsBlocking` passing proves the escape-hatch
  behavior described in the §5 note: usage ends up strictly greater than
  `LIMIT`, with no parking at all — direct evidence that this if-check does
  not gate a `markBlocking()`-marked caller.
- If either assertion fails, that means real behavior has drifted from this
  case's description (e.g. a Cassandra version where the escape-hatch logic
  changed) — treat that as a finding to update the case with, not a test bug
  to silence.

### Trigger: live-cluster (secondary — optional, for end-to-end confirmation)

Only do this after the unit test above passes; it confirms the same
mechanism is reachable through a real node, per the README's "do this in
addition to, not instead of" guidance.

1. `memtable_allocation_type` defaults to `heap_buffers`
   (`Config.java:524`), so no explicit setting is needed to reach
   `HeapPool`.
2. Set `memtable_heap_space: 1MiB` (or similar, small) in `cassandra.yaml`
   on a **dedicated single-node instance** — `MEMORY_POOL` is a global
   static singleton (`AbstractAllocatorMemtable.java:59`) shared by every
   table, so don't run this against a shared/loaded cluster.
3. Start the node, then issue writes (e.g. via `cqlsh`) whose cumulative
   size approaches the 1MiB cap faster than the periodic/threshold-driven
   flush can reclaim it. Unlike the unit test, there is no clean
   deterministic single-shot trigger here (a single CQL write is much
   smaller than 1MiB), so this will need sustained write pressure — expect
   some raciness against `memtable_cleanup_threshold`-driven flushing.
4. Evidence to capture (do not rely on a hang/slowdown alone — confirm it's
   *this* check): the JMX timer
   `org.apache.cassandra.metrics:type=MemtablePool,name=BlockedOnAllocation`
   (`MemtablePool.java:63`) going non-zero, and/or a thread dump of a write
   thread parked in `WaitQueue$Signal.awaitThrowUncheckedOnInterrupt()`
   called from `MemtableAllocator$LifeCycle.allocate()`.

| Field | Content |
|--------|---------|
| **Status** | in-progress — line numbers verified; unit-level trigger designed and documented above, pending an actual run by Jingsong |
| **Verified By / Date** | Jingsong — line numbers verified against local pinned-tag clone; behavioral trigger pending execution of `HeapPoolTest` |
| **Trigger method** | Unit test `test/unit/org/apache/cassandra/utils/memory/HeapPoolTest.java` (full source above) — run via `ant testsome -Dtest.name=org.apache.cassandra.utils.memory.HeapPoolTest`. Live-cluster trigger documented above as a secondary/optional confirmation. |
| **Evidence** | Pending — will be: (1) `TimeoutException` on the over-limit `Future.get()` in `testBlocksThenUnblocksOnRelease`, plus post-release usage matching the expected value; (2) post-escape-hatch usage exceeding `LIMIT` in `testForcesThroughWhenOpGroupIsBlocking`. Update this field with the actual test output once run. |
| **Notes** | Sibling to [`memtable_offheap_space-region`](memtable_offheap_space-region.md) — same `SubPool.tryAllocate()` if-check, on-heap `SubPool`/`HeapPool.Allocator` instead of off-heap. Same decoupled-accounting / escape-hatch behavior applies (see §5 note); flagged for later Target-3 bypass analysis, not pursued further here. |

---

## Notes

- The escape hatch (`opGroup.isBlocking()` forcing `allocated(size)` through
  regardless of `limit`) is shared code between this case and
  `memtable_offheap_space-region` — it lives in `MemtableAllocator.java`,
  not in either allocator subclass. Any future case touching
  `SubPool.tryAllocate()` (there may be others besides the two memtable
  pools) should check whether it goes through this same
  `MemtableAllocator.SubAllocator.allocate()` path before assuming the
  if-check behaves as a clean reject.
