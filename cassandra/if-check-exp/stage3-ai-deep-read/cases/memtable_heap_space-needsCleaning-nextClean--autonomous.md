# memtable_heap_space — verification solution  <!-- file: cases/memtable_heap_space-needsCleaning-nextClean--autonomous.md -->

| Field | Value |
|---|---|
| Entry pointer | `src/java/org/apache/cassandra/utils/memory/MemtablePool.java:128` |
| Pinned source | `cassandra-5.0.9` |
| Session / date | Claude Opus 5.5 (`claude-opus-5-5`), Claude Code agent (CLI version not exposed to the agent), 2026-10-21 |
| Estimate | `positive`. Line 128 is the soft flush trigger of the global memtable pool. It fires when the pool's non-flushing bytes exceed `memtable_heap_space × memtable_cleanup_threshold`. Together with the hard check in the same pool (`tryAllocate`, `MemtablePool.java:156`) it keeps memtable heap at roughly the trigger level in steady state and at no more than `memtable_heap_space` (plus small, bounded overshoots). |
| Ground | — |

Case ID: `MEMTABLE_HEAP_SPACE-NEEDSCLEANING-NEXTCLEAN`

Naming note (§6.1). The check at line 128 is `used() > nextClean` inside `SubPool.needsCleaning()`. Its limit-side operand is `nextClean`, which is computed as `reclaiming + (long)(limit * cleanThreshold)` (`MemtablePool.java:143`). `limit` comes from `memtable_heap_space` (or `memtable_offheap_space` for the off-heap sub-pool). `cleanThreshold` comes from `memtable_cleanup_threshold`, which by default is derived from `memtable_flush_writers`. So the operand has several sources. The primary one is `memtable_heap_space`: it is the knob a user tunes, it gives the operand its byte scale, and its yaml comment calls it the total permitted memtable memory. `memtable_cleanup_threshold` is deprecated, and the yaml says its derived default "is the only reasonable choice" (`conf/cassandra.yaml:801-803`). Both secondary sources are still varied in the solution so that effects can be traced to line 128 and not to `tryAllocate`.

## A. Constraint trace

**A1. The constraint.**
- **Name and kind:** `memtable_heap_space`, a configuration entry (yaml), type `DataStorageSpec.IntMebibytesBound`. It is declared at `src/java/org/apache/cassandra/config/Config.java:187`. The old name `memtable_heap_space_in_mb` is still accepted through `@Replaces` (`Config.java:186`).
- **Unit:** MiB (min unit MiB, `conf/cassandra.yaml:796`). It is converted to bytes with `<< 20` at `db/memtable/AbstractAllocatorMemtable.java:81`.
- **Default:** `Runtime.getRuntime().maxMemory() / 4`, i.e. 1/4 of `-Xmx` (`config/DatabaseDescriptor.java:586-587`). A value of 0 is rejected (`:588-589`). The value is logged at startup as `Global memtable on-heap threshold is enabled at …` (`:590`).
- **How to set:** only in `cassandra.yaml` (`memtable_heap_space: <n>MiB`, commented out by default at `conf/cassandra.yaml:797`).
  - There is no setter and no JMX attribute. The only getter is `DatabaseDescriptor.getMemtableHeapSpaceInMiB()` (`DatabaseDescriptor.java:4055-4058`).
  - The value is read once, when the static `AbstractAllocatorMemtable.MEMORY_POOL` is initialised (`AbstractAllocatorMemtable.java:59, 78-86`), and stored in the `final long limit` (`MemtablePool.java:105, 119`).
  - **A change needs a restart.**
- **Co-sources of the operand `nextClean`:**
  - `memtable_cleanup_threshold` (`Config.java:190`, `Float`, default `null`). It is resolved at `DatabaseDescriptor.java:761-775`: if unset it becomes `1/(1+memtable_flush_writers)`, and it must lie in [0.01, 0.99]. If it is set explicitly, a deprecation warning is logged (`:767`).
  - `memtable_flush_writers` defaults to 2 for a single data directory and to 1 otherwise (`DatabaseDescriptor.java:753-756`). The default threshold is therefore **1/3** on a one-data-dir node.
  - `memtable_offheap_space` (`Config.java:189`, default 1/4 heap, `DatabaseDescriptor.java:583-584`) is the `limit` of the off-heap sub-pool.
  - `memtable_allocation_type` decides which pool is built (`AbstractAllocatorMemtable.java:89-111`). The shipped `conf/cassandra.yaml:825` uses `heap_buffers`, which builds `SlabPool(heapLimit, 0, …)` (`:100-102`), so under the shipped config the off-heap sub-pool has `limit = 0`.

**A2. What it caps.**
- **Resource:** JVM heap used by memtables. This covers the cloned cell and key buffers in 1 MiB slab regions, plus the on-heap object overhead that memtables report to the allocator.
- **Quantity compared at line 128:** `SubPool.allocated`, returned by `used()` (`MemtablePool.java:216-219`). This is the total bytes the pool has handed out to all live **and** flushing memtables. It is compared against `nextClean = reclaiming + limit × cleanThreshold`.
- So the condition is "non-flushing (live) memtable bytes `allocated − reclaiming` > `memtable_cleanup_threshold × memtable_heap_space`".
- The companion check `tryAllocate` (`MemtablePool.java:156`) compares `allocated + size > limit`, i.e. the total including flushing memtables against `memtable_heap_space` itself.

**A3. Mechanism.**

1. **Write accounting.** A write calls `SkipListMemtable.put` (`db/memtable/SkipListMemtable.java:108`). It clones key and values through the allocator's cloner. `SlabAllocator.allocate` (`utils/memory/SlabAllocator.java:83-114`) first calls `onHeap().allocate(size, opGroup)` (`:89`, on-heap because `allocateOnHeapOnly = (maxOffHeapMemory == 0)`, `SlabPool.java:28`). Partition overhead is accounted afterwards through `allocator.onHeap().allocate(overhead, …)` (`SkipListMemtable.java:121-125`).
2. **Hard check.** `SubAllocator.allocate` (`utils/memory/MemtableAllocator.java:169-197`) calls `parent.tryAllocate(size)` (`MemtablePool.java:151-161`).
   - On success it calls `acquired(size)`, which reaches `parent.acquired()` and then `maybeClean()` (`MemtablePool.java:187-190, 131-135`).
   - On failure the writer blocks on `hasRoom` (`MemtableAllocator.java:185-195`). It is woken by `released()` → `hasRoom.signalAll()` (`MemtablePool.java:192-197`).
3. **The target check (line 128).** `maybeClean()` evaluates `needsCleaning()`, which is `used() > nextClean && updateNextClean()`.
   - The first conjunct is a cheap filter against the cached `nextClean`.
   - `updateNextClean()` (`:137-147`) recomputes `next = reclaiming + (long)(limit * cleanThreshold)`, CASes it into `nextClean`, and returns `used() > next`.
   - The comparison is strictly greater, so a sub-pool with `limit == 0` never cleans (comment at `:127`). This is the off-heap sub-pool under `heap_buffers`.
   - If the check is true and a cleaner exists, `cleaner.trigger()` wakes the `MemtableCleanerThread`.
4. **Cleaner thread.** `MemtableCleanerThread.Clean.run` (`utils/memory/MemtableCleanerThread.java:71-90`) re-evaluates `pool.needsCleaning()` (which is `onHeap || offHeap`, `MemtablePool.java:86-89`). If it is true, it invokes the cleaner `AbstractAllocatorMemtable::flushLargestMemtable` (`AbstractAllocatorMemtable.java:84`). That method picks the memtable with the largest ownership ratio, logs `Flushing largest … Used total: …, live: …, flushing: …` (`:293-295`), and calls `signalFlushRequired(…, FlushReason.MEMTABLE_LIMIT)` (`:297`, `ColumnFamilyStore.java:1436-1439`). The flush is logged as `Enqueuing flush of …, Reason: MEMTABLE_LIMIT` (`ColumnFamilyStore.java:1055`). If the cleaner's future returns true while the pool still needs cleaning, it is re-signalled (`MemtableCleanerThread.java:97-98`).
5. **Switch.** `switchOut` → `allocator.setDiscarding()` (`AbstractAllocatorMemtable.java:162-166`) → `SubAllocator.updateReclaiming()` → `parent.reclaiming(owns)` (`MemtableAllocator.java:129-134, 266-278`; `MemtablePool.java:199-204`). The flushing memtable's bytes move into `reclaiming`, so the next evaluation of `nextClean` rises by that amount and the live-only condition resets.
6. **Release.** When the flush completes, `discard()` → `setDiscarded()` → `releaseAll()` (`AbstractAllocatorMemtable.java:168-172`, `MemtableAllocator.java:140-155`). This decrements both `allocated` and `reclaiming`, signals `hasRoom`, and `reclaimed()` re-evaluates `updateNextClean()` (`MemtablePool.java:206-214`).

**Outcomes.**
- Line 128 true: a flush of the largest memtable is scheduled asynchronously. Writes are **not** blocked by this check.
- Line 128 false: nothing happens.
- Only `tryAllocate` blocks writers. It does so when `allocated + size > memtable_heap_space`, which in practice happens only when flushing falls behind or when the threshold × (1 + flushing memtables) exceeds 1.

**Bypass and overshoot paths.**
- If the write's `OpOrder.Group` is blocking a pending barrier (a flush is waiting on it), the allocation is recorded with `allocated(size)` **without** `tryAllocate` (`MemtableAllocator.java:180-184`, `MemtablePool.java:177-185`). Usage can then exceed `limit`, as the javadoc at `MemtableAllocator.java:80-82, 125-128` says.
- Partition overhead is allocated "after the fact … means we can overshoot our declared limit" (`SkipListMemtable.java:121-125`).
- Slab regions are 1 MiB (`SlabAllocator.java:51, 139`), but the pool accounts only the bytes requested (`:89`). Up to about 1 MiB of unaccounted slack exists per memtable, plus regions stashed in `RACE_ALLOCATED` (`:55`).
- Values larger than 128 KiB are allocated directly (`:92-99`) but are accounted.
- The trigger is asynchronous. Writers keep allocating between the signal and the switch, so live bytes at the switch exceed `t·L` by however much was written in that time.

**A4. Other consumers.** Heap outside this pool's accounting:
- Transient objects on the write path (mutations, commit-log serialisation, native-transport frames).
- Flush-writer buffers.
- Compaction.
- Key cache (on heap) and SSTable index metadata.
- The `MemtableCleanerThread` itself.
- GC float: flushed memtables that are dead but not yet collected. This shows up in post-young-GC heap readings but not in a forced full-GC live set.

Memtables that are not `AbstractAllocatorMemtable` are skipped by the cleaner (`AbstractAllocatorMemtable.java:261-262`). The shipped default memtable is `SkipListMemtable` (`conf/cassandra.yaml:783-790`), which is an allocator memtable. `TrieMemtable` has its own additional shard-level flush trigger (`db/memtable/TrieMemtable.java:195`). Off-heap memtable memory (`offheap_buffers` / `offheap_objects`) is governed by `memtable_offheap_space` instead, and is not exercised here.

**A5. Evidence beyond the source.**
- `conf/cassandra.yaml:792-812`: "Total permitted memory to use for memtables. Cassandra will stop accepting writes when the limit is exceeded until a flush completes, and will trigger a flush based on memtable_cleanup_threshold". Also: "Ratio of occupied non-flushing memtable size to total permitted size that will trigger a flush of the largest memtable."
- `CHANGES.txt:2581`: "Deprecate memtable_cleanup_threshold and update default for memtable_flush_writers (CASSANDRA-12228)", https://issues.apache.org/jira/browse/CASSANDRA-12228
- `test/unit/org/apache/cassandra/db/memtable/MemtableSizeTestBase.java`: asserts that memtable allocator accounting is within 3% of jamm-measured real usage. This supports using the pool's `used()` as a proxy for actual heap.
- `test/unit/org/apache/cassandra/utils/memory/NativeAllocatorTest.java`: bookkeeping of used and reclaiming, and blocking above the limit. This is the pattern reused in B2.
- `test/unit/org/apache/cassandra/utils/memory/MemtableCleanerThreadTest.java`: cleaner-thread trigger semantics.
- Cassandra 5.0 yaml reference: https://cassandra.apache.org/doc/5.0/cassandra/managing/configuration/cass_yaml_file.html
- JDK 11 `jcmd` `GC.class_histogram` (forces a full GC and reports the live set): https://docs.oracle.com/en/java/javase/11/tools/jcmd.html

## B. Verification solution

**B1. Claim under test.**
1. In the global memtable pool, a flush of the largest memtable is triggered exactly when `allocated − reclaiming` first exceeds `(long)(memtable_heap_space_bytes × memtable_cleanup_threshold)` (strictly greater). As a result, on a real node the heap held by memtables rises and falls with `memtable_heap_space`.
2. The heap held by memtables never exceeds `memtable_heap_space` by more than a small bounded overshoot. Writers block rather than exceed it.

The claim is wrong if any of the following holds:
- The trigger point does not track `limit × threshold`.
- Pool usage or memtable live heap clearly exceeds `memtable_heap_space`.
- Memtable heap does not scale with the knob.

### B2. Unit tier

**B2a. Environment and build.**
- Hardware and JDK: one Linux host, JDK 11.0.32.1, Ant 1.10.12. The build needs Maven Central for the first resolve.
- Make a local clone. Never build in the shared tree.
  ```
  mkdir -p /tmp/s3mhs && cd /tmp/s3mhs
  git clone --no-hardlinks /proj/misconfiguration-PG0/git-repos/cassandra-src cassandra
  cd cassandra && git checkout -q cassandra-5.0.9 && git status --short   # expect empty
  ```
  If the shared tree is not a usable git repo, use `rsync -a --exclude test/unit/org/apache/cassandra/utils/memory/HeapPoolTest.java /proj/…/cassandra-src/ /tmp/s3mhs/cassandra/` instead.
- Test source: create `/tmp/s3mhs/cassandra/test/unit/org/apache/cassandra/utils/memory/NextCleanBoundaryTest.java`. It must be in package `org.apache.cassandra.utils.memory` to reach the package-private `needsCleaning()`, `nextClean`, `setDiscarding()` and `setDiscarded()`.
- Build and run: `ant testsome -Dtest.name=org.apache.cassandra.utils.memory.NextCleanBoundaryTest` (builds main and test classes, then runs JUnit with the default test JVM options from `build.xml`). Later reruns: add `-Dno-build-test=true` after compiling with `ant build-test`.
- No `DatabaseDescriptor` initialisation is needed: `NativeAllocatorTest` constructs a pool the same way. If an `ExceptionInInitializerError` appears, add `@BeforeClass public static void init() { org.apache.cassandra.config.DatabaseDescriptor.daemonInitialization(); }`.

**B2b. Knobs.**
- **Pool `limit`, standing in for `memtable_heap_space`:** L = 64 MiB (67,108,864 B) in the main runs. For scaling, L = 32 MiB and 128 MiB at t = 0.25. Powers of two make `limit × float` exact in float arithmetic, so every threshold below is an exact integer.
- **`cleanThreshold` t:** 0.10f, 0.25f, 0.33333334f (the shipped default 1/(1+2)), 0.50f, 0.90f. This spans the yaml-legal range [0.01, 0.99]. 0.25 and 0.50 make `L·t` an exact multiple of the chunk, which tests the strict `>`.
- Both are set as constructor arguments of `new SlabPool(L, 0, t, cleaner)`, which is exactly what `createMemtableAllocatorPoolInternal` does for `heap_buffers` (`AbstractAllocatorMemtable.java:100-102`).

**B2c. Workload.**
- Allocate in chunks of C = 256 KiB (262,144 B) via `SubAllocator.allocate(C, group)` on `pool.onHeap.newAllocator()`, with `group = new OpOrder().start()`, which is never blocking.
- Stop when `used + C > 0.95·L` (243 chunks = 63,700,992 B for L = 64 MiB). The hard cap is never hit in parts A and B. Part C goes past it.
- The threshold T = `(long)(L·t)`:

| t | T (B) | first trigger at chunk m = ⌊T/C⌋+1 | used at first trigger (B) |
|---|---|---|---|
| 0.10 | 6,710,886 | 26 | 6,815,744 |
| 0.25 | 16,777,216 | 65 (T is exactly 64·C; strict `>`) | 17,039,360 |
| 0.33333334 | 22,369,622 | 86 | 22,544,384 |
| 0.50 | 33,554,432 | 129 (T is exactly 128·C) | 33,816,576 |
| 0.90 | 60,397,976 | 231 | 60,555,264 |
| 0.25, L = 32 MiB | 8,388,608 | 33 | 8,650,752 |
| 0.25, L = 128 MiB | 33,554,432 | 129 | 33,816,576 |

All are ≤ 0.95·L, so every threshold is reached.

**B2d. Observables and instruments.**
- **(i)** `pool.onHeap.used()`, `getReclaiming()` and `nextClean`, read directly as fields. Read once in the test thread after each chunk, and once inside the cleaner at each invocation (a snapshot).
- **(ii)** `directIdx`: the first chunk index at which a direct call `pool.onHeap.needsCleaning()` (the line-128 expression) returns true.
- **(iii)** The number of cleaner invocations.
- **(iv)** In part C, whether the allocation thread is blocked (`Future.get` timeout), and the maximum `used()`.
- Printed to stdout and the JUnit XML under `build/test/output/`.
- Not observable: the cleaner thread's scheduling latency. A 20 ms wait after each chunk removes it from the readings.

**B2e. Procedure.** Write the test below, then run `ant testsome -Dtest.name=org.apache.cassandra.utils.memory.NextCleanBoundaryTest`. Collect `build/test/output/TEST-org.apache.cassandra.utils.memory.NextCleanBoundaryTest.xml` and the stdout lines starting with `NCB`.

```java
package org.apache.cassandra.utils.memory;

import java.util.*;
import java.util.concurrent.*;
import java.util.concurrent.atomic.*;
import org.junit.Assert;
import org.junit.Test;
import org.apache.cassandra.utils.concurrent.ImmediateFuture;
import org.apache.cassandra.utils.concurrent.OpOrder;

public class NextCleanBoundaryTest
{
    static final long MiB = 1L << 20, C = 256 * 1024;
    static final float[] TS = { 0.10f, 0.25f, 0.33333334f, 0.50f, 0.90f };

    /** Part A: first trigger, cleaner blocks after its first snapshot (no reclaim). */
    long[] first(long L, float t) throws Exception
    {
        AtomicReference<long[]> snap = new AtomicReference<>();
        CountDownLatch fired = new CountDownLatch(1), release = new CountDownLatch(1);
        AtomicReference<SlabPool> ref = new AtomicReference<>();
        SlabPool pool = new SlabPool(L, 0, t, () -> {
            MemtablePool.SubPool p = ref.get().onHeap;
            if (snap.compareAndSet(null, new long[]{ p.used(), p.getReclaiming(), p.nextClean })) fired.countDown();
            try { release.await(); } catch (InterruptedException e) { return ImmediateFuture.success(false); }
            return ImmediateFuture.success(true);
        });
        ref.set(pool);
        MemtableAllocator.SubAllocator sub = pool.onHeap.newAllocator();
        OpOrder.Group g = new OpOrder().start();
        long directUsed = -1, directIdx = -1, i = 0;
        while (pool.onHeap.used() + C <= (long) (0.95 * L))
        {
            sub.allocate(C, g); i++;
            if (directIdx < 0 && pool.onHeap.needsCleaning()) { directIdx = i; directUsed = pool.onHeap.used(); }
            if (fired.await(20, TimeUnit.MILLISECONDS)) break;
        }
        pool.shutdownAndWait(10, TimeUnit.SECONDS); release.countDown();
        long[] s = snap.get();
        System.out.printf("NCB A L=%d t=%s T=%d directIdx=%d directUsed=%d cleanerUsed=%d cleanerRecl=%d nextClean=%d%n",
                          L, t, (long) (L * t), directIdx, directUsed, s == null ? -1 : s[0], s == null ? -1 : s[1], s == null ? -1 : s[2]);
        return new long[]{ directIdx, directUsed, s == null ? -1 : s[0], s == null ? -1 : s[2] };
    }

    @Test public void partA() throws Exception
    {
        long L = 64 * MiB;
        for (float t : TS)
        {
            long T = (long) (L * t), m = T / C + 1;
            long[] r = first(L, t);
            Assert.assertEquals(m, r[0]);            // line 128 first true at chunk m
            Assert.assertEquals(m * C, r[1]);
            Assert.assertEquals(m * C, r[2]);        // cleaner saw same operand
            Assert.assertEquals(T, r[3]);            // nextClean == 0 + (long)(L*t)
        }
        for (long L2 : new long[]{ 32 * MiB, 128 * MiB })
        {
            long T = (long) (L2 * 0.25f), m = T / C + 1;
            Assert.assertEquals(m * C, first(L2, 0.25f)[1]);
        }
    }

    /** Part B: cleaner simulates a memtable switch (setDiscarding + new allocator);
     *  Part C: then push past the hard limit, check blocking, release. */
    @Test public void partBC() throws Exception
    {
        long L = 64 * MiB;
        for (float t : TS)
        {
            List<long[]> snaps = Collections.synchronizedList(new ArrayList<>());
            List<MemtableAllocator.SubAllocator> discarding = Collections.synchronizedList(new ArrayList<>());
            AtomicReference<SlabPool> ref = new AtomicReference<>();
            AtomicReference<MemtableAllocator.SubAllocator> cur = new AtomicReference<>();
            SlabPool pool = new SlabPool(L, 0, t, () -> {
                MemtablePool.SubPool p = ref.get().onHeap;
                snaps.add(new long[]{ p.used(), p.getReclaiming(), p.nextClean });
                MemtableAllocator.SubAllocator old = cur.getAndSet(p.newAllocator());
                old.setDiscarding(); discarding.add(old);
                return ImmediateFuture.success(true);
            });
            ref.set(pool); cur.set(pool.onHeap.newAllocator());
            OpOrder.Group g = new OpOrder().start();
            long maxUsed = 0;
            while (pool.onHeap.used() + C <= (long) (0.95 * L))
            {
                cur.get().allocate(C, g); maxUsed = Math.max(maxUsed, pool.onHeap.used());
                Thread.sleep(20);
            }
            long T = (long) (L * t);
            for (long[] s : snaps)
            {
                long live = s[0] - s[1];
                System.out.printf("NCB B t=%s used=%d recl=%d live=%d T=%d%n", t, s[0], s[1], live, T);
                Assert.assertTrue(live > T && live <= T + 2 * C);
            }
            // Part C: exceed hard limit
            ExecutorService ex = Executors.newSingleThreadExecutor();
            Future<?> f = ex.submit(() -> { while (true) { cur.get().allocate(C, g); if (Thread.interrupted()) return; } });
            boolean blocked = false;
            try { f.get(2, TimeUnit.SECONDS); } catch (TimeoutException e) { blocked = true; }
            long usedAtBlock = pool.onHeap.used();
            System.out.printf("NCB C t=%s triggers=%d blocked=%s usedAtBlock=%d L=%d maxUsedB=%d%n",
                              t, snaps.size(), blocked, usedAtBlock, L, maxUsed);
            Assert.assertTrue(blocked);
            Assert.assertTrue(usedAtBlock <= L);
            synchronized (discarding) { for (MemtableAllocator.SubAllocator s : discarding) s.setDiscarded(); }
            Thread.sleep(200);
            System.out.printf("NCB C t=%s afterRelease used=%d recl=%d%n", t, pool.onHeap.used(), pool.onHeap.getReclaiming());
            ex.shutdownNow(); pool.shutdownAndWait(10, TimeUnit.SECONDS);
        }
    }
}
```

Part C notes:
- The helper thread keeps allocating after the release. Its log line after release shows that the block was lifted (used drops, then refills).
- `ex.shutdownNow()` interrupts it. `allocate` uses `awaitThrowUncheckedOnInterrupt` (`MemtableAllocator.java:195`), so a blocked allocation ends with an unchecked exception inside the future, which is ignored.

**B2f. Predictions (stated before any run).**
- **Part A (L = 64 MiB):** for every t, `directIdx = m` and `directUsed = cleanerUsed = m·C`, with m and the used values from the B2c table, and `nextClean = T` exactly.
  - At t = 0.25 and t = 0.50, the trigger is at chunk 65 and chunk 129, **not** 64 and 128 (strict `>`).
  - Scaling at t = 0.25: 8,650,752 B (L = 32 MiB) and 33,816,576 B (L = 128 MiB). The trigger point is proportional to L.
- **Part B:** every snapshot satisfies `T < used − reclaiming ≤ T + 2C`. The number of triggers is ⌊243/m⌋ ± 1:

| t | expected triggers |
|---|---|
| 0.10 | 9 |
| 0.25 | 3 |
| 1/3 | 2 |
| 0.50 | 1 |
| 0.90 | 1 |

  The k-th snapshot has `used ≈ k·m·C` and `reclaiming ≈ (k−1)·m·C`.
- **Part C:** for every t the allocating thread is blocked after 2 s with `usedAtBlock ≤ 67,108,864`, and `usedAtBlock > 67,108,864 − C`. After `setDiscarded`, `reclaiming` drops to the live remainder (0 if the current allocator was just switched) and `used` falls by the discarded total.

> **Stage-4 audit amendment U2 (2026-10-21).** The after-release reading above is racy: the helper thread keeps allocating, so 200 ms after `setDiscarded` it has refilled the pool and `used` no longer shows the fall. The harness (`stage4-runtime-verification/harness/memtable_heap_space-needsCleaning-nextClean--autonomous/NextCleanBoundaryTest.java`) therefore counts the helper's completed chunks and sums the discarded allocators' `owns()` before releasing them (`released`). Prediction for the release, replacing the sentence above: after release the helper completes `released / C` more chunks (± 1) and is blocked again, and `used ≤ L` at the after-release reading. The block-at-L prediction is unchanged.

**B2g. Readings.**

| Observation | Meaning |
|---|---|
| All Part A values equal the table; Part B live values in (T, T+2C]; Part C blocks at ≤ L | Mechanism works as traced. Line 128 fires at `L·t` above `reclaiming`, and `tryAllocate` caps the total at L. Claim supported at unit level. |
| First trigger at chunk 64 / 128 for t = 0.25 / 0.50 | The comparison is `>=`, not `>`. Trace wrong in detail. The claim still holds in substance. |
| First trigger independent of t (e.g. always near L) or of L | Line 128 does not follow the knob. **Claim refuted** for the trigger. |
| Part B: later triggers at `used ≈ k·T` fail to appear, or appear with `live ≪ T` | Reclaiming is not honoured in `nextClean`. Trace wrong. |
| Part C not blocked, or `usedAtBlock > L` | The pool does not cap the total at `memtable_heap_space`. **Claim refuted** for the cap. |
| Cleaner snapshot missing (`cleanerUsed = -1`) but `directIdx` matches | Cleaner thread did not run (environment problem). Not confirmed for the end-to-end path. Rerun with a longer wait. |

**B2h. Controls.**
- Cleaner invocation count is 0 while `used ≤ T`: Part A loops below m produce no snapshot, so the snapshot is caused by crossing T and not by timing.
- The direct call and the cleaner-thread snapshot measure the same operand independently.
- Varying L at fixed t (scaling rows) separates L from t.
- Part C uses the same pool and allocator to show the hard cap, so blocking cannot be attributed to the test harness.
- The `heap_buffers` offHeap sub-pool has `limit = 0`. `pool.offHeap.used()` stays 0 throughout, so the `needsCleaning` disjunction (`MemtablePool.java:88`) is driven by on-heap only. Assert this with a print of `pool.offHeap.used()` and `pool.offHeap.needsCleaning()` (expected `0` and `false`).

> **Stage-4 audit amendment U1 (2026-10-21).** The B2e code did not contain this print. The harness copy prints `offHeapUsed` and `offHeapNeedsCleaning` on every Part A line and asserts `0` and `false`.

### B3. Cluster tier

**B3a. Environment and build.**
- **Node:** one node on 127.0.0.1, on the host from B2a. The claim is about a node-local pool, so one node suffices.
- **Port check:** confirm no other Cassandra is running on the host: `ss -ltn | grep -E ':(7000|7199|9042)\b'` must be empty.
- **Disk:** all paths under `/tmp/s3mhs` on the local `/` disk (about 50 GB free). Check with `df -h /tmp`.
- **Build** in the B2a clone: `cd /tmp/s3mhs/cassandra && ant jar && ant stress-build`.
- **JVM:** `MAX_HEAP_SIZE=4G HEAP_NEWSIZE=800M` (both must be set for `cassandra-env.sh`). G1 is the default in `conf/jvm11-server.options:63`. The GC log goes to `$CASSANDRA_LOG_DIR/gc.log` by default (`conf/cassandra-env.sh:83`).
- **Configuration:** copy `conf/` to `/tmp/s3mhs/conf` and set the following with `sed` (per run, see B3e):
  - `cluster_name: 's3mhs'`
  - `data_file_directories: [/tmp/s3mhs/data]` (one directory, so `memtable_flush_writers` defaults to 2 and t defaults to 1/3)
  - `commitlog_directory: /tmp/s3mhs/commitlog`
  - `saved_caches_directory: /tmp/s3mhs/saved_caches`
  - `hints_directory: /tmp/s3mhs/hints`
  - `cdc_raw_directory: /tmp/s3mhs/cdc_raw`
  - `memtable_allocation_type: heap_buffers` (as shipped)
  - `memtable_flush_writers: 2`
  - `commitlog_total_space: 4096MiB`. This is far above the at most about 1 GiB of unflushed data, so no `COMMITLOG_DIRTY` flushes. It also bounds commitlog disk.
  - `memtable_heap_space: <L>MiB`, and in R4/R5 `memtable_cleanup_threshold: <t>`.

**B3b. Knobs.**

| Run | memtable_heap_space L | memtable_cleanup_threshold t | why |
|---|---|---|---|
| R1 | 128MiB | unset (1/3) | tight cap, far below workload volume |
| R2 | 512MiB | unset (1/3) | middle |
| R3 | 1024MiB | unset (1/3) | = default for -Xmx4G (heap/4). Positive control: loose cap, the same workload can hold ≥ 340 MiB of memtables |
| R4 | 512MiB | 0.15 | moves only line 128's operand |
| R5 | 512MiB | 0.66 | trigger near the hard cap: with one flushing memtable, `t·L + t·L > L`, so `tryAllocate` should bind |

`memtable_heap_space` is set in yaml and needs a fresh start; each run uses a fresh node with wiped data.

**B3c. Workload.**
- Command: `cassandra-stress write n=3000000 cl=ONE no-warmup -col 'n=FIXED(1)' 'size=FIXED(1024)' -rate threads=16 'fixed=10000/s' -schema 'replication(strategy=SimpleStrategy,factor=1)' -node 127.0.0.1`. That is 3,000,000 single-cell rows of 1 KiB at a fixed 10,000 rows/s, about 300 s.
- **Tracked bytes per row (estimate):** about 1.03 KiB value + key + clustering/cell/row/BTree overhead + partition overhead, so 1.3 to 1.8 KiB. Total tracked W ≈ 3.7 to 5.1 GiB, which is ≥ 3.6× the largest L. The trigger level `t·L` (43 / 171 / 341 MiB in R1 to R3) is reached about every 3 to 35 s.
- **Disk:** about 3.2 GB raw SSTables (random values, so compression helps little), up to about 2× transiently during compaction, plus at most 4 GiB commitlog. Below 12 GB in total.

**B3d. Observables and instruments.**

| # | What | How | Cadence | Measures |
|---|---|---|---|---|
| O1 | Global pool usage (sum of `owns` over all memtables, live + flushing ≈ `SubPool.used()`) | `bin/nodetool sjk mx -b org.apache.cassandra.metrics:type=Table,name=AllMemtablesOnHeapDataSize -mg -f Value` (gauge `TableMetrics.java:506-512`) | ~2 s (each nodetool call costs about 1 s of JVM start) | operand |
| O2 | Trigger points | `grep 'Flushing largest' system.log`: the `Used total: x/y, live: x/y, flushing: x/y` ratios at each line-128 firing (`AbstractAllocatorMemtable.java:293`); `grep -c 'Reason: MEMTABLE_LIMIT' system.log` | per event | trigger |
| O3 | **Actual heap: live set** | `jcmd $PID GC.class_histogram \| tail -1` (forces a full GC; "Total" bytes = live heap) | every 30 s | actual resource |
| O4 | Heap envelope including garbage | GC log `Pause Young … A->B(C)`: post-GC heap B | per GC | actual resource |
| O5 | Writer blocking | `bin/nodetool sjk mx -b org.apache.cassandra.metrics:type=MemtablePool,name=BlockedOnAllocation -mg -f Count` | at end of run | blocking |
| O6 | Flush count | `nodetool tablestats keyspace1.standard1` and the MemtableSwitchCount line | end of run | flushes |

What cannot be observed directly:
- Memtable bytes as a subset of the live heap. They are inferred as O3 minus a pre-run baseline B.
- The O1 gauge sums ownership across memtables. It equals `SubPool.used()` up to timing, but `nextClean` itself is not exposed.

> **Stage-4 audit amendment K1 (2026-10-21), a citation error found before any reading.** O1 does **not** include flushing memtables: the gauge sums `getMemoryUsageWithIndexes(cfs)`, which reads only `getCurrentMemtable()` (`metrics/TableMetrics.java:876-882`). O1 therefore measures the **live** (current) memtable bytes, about `used − reclaiming`, not `SubPool.used()`. To read the operand directly, the run adds a Byteman observation script (`harness/memtable_heap_space-needsCleaning-nextClean--autonomous/ncl.btm`, on the node with `-javaagent`; it changes no control flow, on-heap sub-pool only):
> - **O1b, pool usage `SubPool.used()`:** at entry of every `SubPool.released(size ≥ 64 KiB)` it logs `allocated`. `allocated` only falls in `released`, so the maximum of these values over the workload period is the peak of `used()` (up to releases below 64 KiB). **`P_pool` in B3e/B3f is read from O1b**, not from O1.
> - **O7, line 128 true:** at exit of `needsCleaning()` when it returns true, one line per distinct `reclaiming` value with `used`, `reclaiming`, `nextClean`, `limit`, `cleanThreshold`. This is direct evidence that the line-128 branch fired on the node and of its operand.
> - **O5b:** the first and every 1000th refused `tryAllocate` (the hard check), as a cross-check of O5.
>
> Added prediction **1b** (B3f): in at least 95 % of O7 lines `nextClean − reclaiming = (long)(L·2^20 · t)` exactly (t as a float: 1/3 → 0.33333334), i.e. the soft threshold on the node is exactly `memtable_heap_space × memtable_cleanup_threshold` above the flushing bytes. O1 (live) must stay ≤ L in every run.

**B3e. Procedure** (repeat for each run R ∈ {R1..R5} with its L and t).
```
export C=/tmp/s3mhs/cassandra CASSANDRA_CONF=/tmp/s3mhs/conf CASSANDRA_LOG_DIR=/tmp/s3mhs/logs-$R
export MAX_HEAP_SIZE=4G HEAP_NEWSIZE=800M
rm -rf /tmp/s3mhs/{data,commitlog,saved_caches,hints,cdc_raw} /tmp/s3mhs/conf; cp -r $C/conf /tmp/s3mhs/conf
Y=/tmp/s3mhs/conf/cassandra.yaml
sed -i -e "s|^cluster_name:.*|cluster_name: 's3mhs'|" \
  -e "s|^# data_file_directories:.*|data_file_directories: [/tmp/s3mhs/data]|" \
  -e "s|^# commitlog_directory:.*|commitlog_directory: /tmp/s3mhs/commitlog|" \
  -e "s|^# saved_caches_directory:.*|saved_caches_directory: /tmp/s3mhs/saved_caches|" \
  -e "s|^# hints_directory:.*|hints_directory: /tmp/s3mhs/hints|" \
  -e "s|^# cdc_raw_directory:.*|cdc_raw_directory: /tmp/s3mhs/cdc_raw|" \
  -e "s|^# commitlog_total_space:.*|commitlog_total_space: 4096MiB|" \
  -e "s|^# memtable_flush_writers:.*|memtable_flush_writers: 2|" \
  -e "s|^# memtable_heap_space:.*|memtable_heap_space: ${L}MiB|" $Y
[ -n "$T" ] && sed -i "s|^# memtable_cleanup_threshold: 0.11|memtable_cleanup_threshold: $T|" $Y
grep -nE '^(data_file_directories|commitlog_directory|memtable_heap_space|memtable_cleanup_threshold|memtable_flush_writers|commitlog_total_space|memtable_allocation_type):' $Y
$C/bin/cassandra -p /tmp/s3mhs/cassandra.pid > /tmp/s3mhs/out-$R.log 2>&1
until $C/bin/nodetool status 2>/dev/null | grep -q '^UN'; do sleep 5; done
PID=$(cat /tmp/s3mhs/cassandra.pid)
grep 'Global memtable on-heap threshold' $CASSANDRA_LOG_DIR/system.log      # must show ${L}MiB
grep -c 'memtable_cleanup_threshold has been deprecated' $CASSANDRA_LOG_DIR/system.log   # 1 in R4/R5, 0 otherwise
# schema + warm-up (tiny)
$C/tools/bin/cassandra-stress write n=1000 cl=ONE -col 'n=FIXED(1)' 'size=FIXED(1024)' -schema 'replication(strategy=SimpleStrategy,factor=1)' -node 127.0.0.1
$C/bin/nodetool flush
# baseline B: 3 live-set samples, 30 s apart
for i in 1 2 3; do jcmd $PID GC.class_histogram | tail -1 >> /tmp/s3mhs/base-$R.txt; sleep 30; done
# samplers
( while kill -0 $PID 2>/dev/null && [ ! -f /tmp/s3mhs/stop ]; do
    echo "$(date +%s) $($C/bin/nodetool sjk mx -b org.apache.cassandra.metrics:type=Table,name=AllMemtablesOnHeapDataSize -mg -f Value 2>/dev/null | tail -1)"; sleep 1; done ) > /tmp/s3mhs/pool-$R.txt &
( while kill -0 $PID 2>/dev/null && [ ! -f /tmp/s3mhs/stop ]; do
    echo "$(date +%s) $(jcmd $PID GC.class_histogram | tail -1)"; sleep 15; done ) > /tmp/s3mhs/live-$R.txt &   # 15 s: amendment K3
# main workload
$C/tools/bin/cassandra-stress write n=3000000 cl=ONE no-warmup -col 'n=FIXED(1)' 'size=FIXED(1024)' \
   -rate threads=16 'fixed=10000/s' -schema 'replication(strategy=SimpleStrategy,factor=1)' -node 127.0.0.1 \
   -log file=/tmp/s3mhs/stress-$R.log
sleep 30; touch /tmp/s3mhs/stop; wait
grep 'Flushing largest' $CASSANDRA_LOG_DIR/system.log > /tmp/s3mhs/trig-$R.txt
grep -c 'Reason: MEMTABLE_LIMIT' $CASSANDRA_LOG_DIR/system.log; grep 'Reason:' $CASSANDRA_LOG_DIR/system.log | grep -v MEMTABLE_LIMIT | grep -c keyspace1
$C/bin/nodetool sjk mx -b org.apache.cassandra.metrics:type=MemtablePool,name=BlockedOnAllocation -mg -f Count
$C/bin/nodetool tablestats keyspace1.standard1 > /tmp/s3mhs/tablestats-$R.txt
cp $CASSANDRA_LOG_DIR/gc.log* /tmp/s3mhs/ 2>/dev/null
$C/bin/nodetool stopdaemon || kill $PID; sleep 10; kill -0 $PID 2>/dev/null && kill -9 $PID
rm -f /tmp/s3mhs/stop; pgrep -f CassandraDaemon && echo LEFTOVER
```

`T` is set only in R4 (`T=0.15`) and R5 (`T=0.66`); in R1 to R3 run `unset T`.

> **Stage-4 audit amendments K3, K4 (2026-10-21).** K3: O3 is sampled every **15 s** instead of 30 s (B3d and the sampler above). At R3 the trigger level (341 MiB) is reached about every 20–25 s, so a 30 s cadence gives about 10 samples per sawtooth-length run and prediction 5 would depend on the sampling phase; 15 s doubles the samples. K4: `N_flush` counts only `Enqueuing flush of keyspace1.standard1, Reason: MEMTABLE_LIMIT`; the bare `grep -c 'Reason: MEMTABLE_LIMIT'` above also counts system tables. The stage-4 run script is `harness/memtable_heap_space-needsCleaning-nextClean--autonomous/cluster-run.sh`, with the Byteman agent of K1 on the node command line.

Derived values:
- **B** = median of the base samples.
- **P_pool** = max of O1 during the main workload.
- **P_live** = max(O3) − B.
- **live_trig** = the on-heap `live` ratio from each `Flushing largest` line in the keyspace1 period.
- **N_flush** = the MEMTABLE_LIMIT count for `keyspace1.standard1`.

**B3f. Predictions (stated before any run).** L in bytes is `L·2^20`, t = 1/3 unless noted.

1. **Trigger tracks L·t.**
   - Median `live_trig` is in [0.30, 0.42] for R1 to R3, in [0.13, 0.22] for R4, and in [0.64, 0.75] for R5.
   - In terms of the `Used total` ratio: R1 to R3 ≥ 0.30 at every trigger.
2. **Pool bounded by L.**
   - `P_pool ≤ L + 8 MiB` in every run.
   - `P_pool ≥ t·L` in every run (the trigger level is reached).
   - In R5, `P_pool ≥ 0.85·L` (near the cap), and BlockedOnAllocation Count > 0 is expected.
   - In R1 to R4, BlockedOnAllocation is 0 or small (flush keeps up at 15 MiB/s inflow).
3. **Flush count scales as 1/(t·L).**
   - `N_flush(R1)/N_flush(R3)` is in [6, 10] (ideal 8).
   - `N_flush(R1)` is roughly 85 to 125, `N_flush(R3)` roughly 11 to 16.
   - `N_flush(R4)/N_flush(R2)` is in [1.7, 2.6] (ideal 2.2).
4. **Actual heap follows the pool.**
   - `P_live ≤ 1.15·P_pool + 64 MiB` in each run. The 15% covers accounting error (≤ 3%, A5) plus slab slack. The 64 MiB covers transient write-path and flush objects.
   - Hence `P_live ≤ 1.15·L + 64 MiB`: ≤ 211 MiB (R1), ≤ 653 MiB (R2), ≤ 1242 MiB (R3).
5. **Actual heap scales with the knob.** `P_live(R3) − P_live(R1) ≥ 250 MiB`. This is roughly t·(1024 − 128) = 299 MiB minus noise.

**The claim is wrong if any of the following holds:**
- `P_pool > 1.1·L` in any run.
- `P_live > 1.15·L + 64 MiB` in R1 or R2.
- `N_flush` does not scale (ratio R1/R3 < 3).
- `live_trig` does not move with t between R4, R2 and R5.
- `P_live(R3) − P_live(R1) < 100 MiB`.

**B3g. Readings.**

| Observation | Meaning |
|---|---|
| Predictions 1–5 hold | `memtable_heap_space` (through line 128 at `t·L`, and through `tryAllocate` at `L`) governs actual memtable heap. **Claim confirmed.** |
| R3 (positive control) shows `P_pool` and `P_live` well above R1's, while R1 stays ≤ 1.15·128 MiB + 64 MiB | Usage moves where the cap is loose and stays flat where it is tight, so R1's flatness is due to the cap and not to the workload. **Confirmed.** |
| R3 `P_pool < 200 MiB` (control did not move) | Workload too light or flushes driven by something else. **Not confirmed**: raise n or rate and recheck flush reasons. |
| `P_pool ≤ L` but `P_live ≫ 1.15·P_pool + 64 MiB` | The pool accounting under-counts actual heap (e.g. slab slack, untracked objects). The constraint caps the operand but **not** the resource. **Claim refuted** for actual heap. |
| `P_pool > 1.1·L` | Overshoot paths (blocking OpOrder, after-the-fact overhead) are significant. **Claim refuted** for the hard bound. |
| `live_trig` the same in R2, R4, R5 | Line 128 does not follow the threshold. **Claim refuted** for the trigger. |
| Many keyspace1 flushes with a reason other than MEMTABLE_LIMIT | Another mechanism (commitlog, period) drives flushing. Readings are not attributable. **Not confirmed.** |
| R5 BlockedOnAllocation = 0 and `P_pool < 0.8·L` | Trigger and flush keep usage below the cap even at t = 0.66. Consistent with the claim, but the hard cap was not exercised on the node. Note it. |

**B3h. Controls.**
- **Baseline.** B is taken per run after schema creation and a flush, so heap from other consumers (A4) is subtracted.
- **Live set.** O3 uses forced full GCs, so dead flushed memtables (GC float) are excluded. O4 is reported only as an envelope.
- **Attribution.**
  - Flush reasons are checked: MEMTABLE_LIMIT only for keyspace1.
  - The startup log confirms the effective L and the deprecation warning for t.
  - `commitlog_total_space` is far above unflushed volume.
  - `memtable_flush_period_in_ms` is 0 by default for stress tables.
- **Same workload, rate and heap** in all runs. Only yaml knobs change.
- **R4 vs R2 vs R5** change only t at fixed L. This separates line 128 from `tryAllocate`.
- **R3 = default** (heap/4) is the reference configuration and the positive control.

**B4. Risks and cleanup.**
- **Unit tier:** builds and runs only in `/tmp/s3mhs/cassandra`, never in the shared tree. Part C's helper thread is interrupted and pools are shut down; the JUnit JVM exits. After the run, `pgrep -f NextCleanBoundaryTest` must be empty.
- **Cluster tier disk:** data, commitlog (≤ 4 GiB), hints, caches and logs all go under `/tmp/s3mhs` on local `/`. The peak is about 12 GB of the about 50 GB free. Check `df -h /tmp` before each run and `du -sh /tmp/s3mhs` after it.
- **Forced GCs:** forced full GCs every 30 s cause pauses of about 1 s on a 4 GiB heap. They do not affect the measured quantities but may add write latency.
- **Process cleanup:** after each run, stop with `nodetool stopdaemon`, falling back to `kill`/`kill -9` on the pidfile. Kill the samplers by creating the stop file and running `wait`. `pgrep -f CassandraDaemon` and `pgrep -f cassandra-stress` must both be empty.
- **Final cleanup:** `rm -rf /tmp/s3mhs` after copying results elsewhere (the results file only). Use no ports other than 7000/7199/9042 on 127.0.0.1, and check they are free beforehand.

## C. Sources read

- /proj/misconfiguration-PG0/git-repos/Misconfiguration/cassandra/if-check-exp/stage3-ai-deep-read/playbook-autonomous.md
- /proj/misconfiguration-PG0/git-repos/Misconfiguration/cassandra/if-check-exp/stage3-ai-deep-read/_TEMPLATE-autonomous.md
- /proj/misconfiguration-PG0/git-repos/Misconfiguration/cassandra/if-check-exp/README.md (§6.1 only)
- src/java/org/apache/cassandra/utils/memory/MemtablePool.java
- src/java/org/apache/cassandra/utils/memory/MemtableAllocator.java
- src/java/org/apache/cassandra/utils/memory/MemtableCleanerThread.java
- src/java/org/apache/cassandra/utils/memory/MemtableCleaner.java
- src/java/org/apache/cassandra/utils/memory/SlabPool.java
- src/java/org/apache/cassandra/utils/memory/SlabAllocator.java
- src/java/org/apache/cassandra/utils/memory/HeapPool.java
- src/java/org/apache/cassandra/db/memtable/AbstractAllocatorMemtable.java
- src/java/org/apache/cassandra/db/memtable/SkipListMemtable.java
- src/java/org/apache/cassandra/db/memtable/TrieMemtable.java (line 195 only)
- src/java/org/apache/cassandra/db/ColumnFamilyStore.java (FlushReason, signalFlushRequired, flush log line)
- src/java/org/apache/cassandra/config/Config.java
- src/java/org/apache/cassandra/config/DatabaseDescriptor.java
- src/java/org/apache/cassandra/config/YamlConfigurationLoader.java (duplicate-key option)
- src/java/org/apache/cassandra/config/CassandraRelevantProperties.java (ALLOW_DUPLICATE_CONFIG_KEYS)
- src/java/org/apache/cassandra/metrics/TableMetrics.java
- src/java/org/apache/cassandra/metrics/CassandraMetricsRegistry.java
- src/java/org/apache/cassandra/tools/nodetool/stats/TableStatsPrinter.java
- conf/cassandra.yaml, conf/cassandra-env.sh, conf/jvm11-server.options, bin/cassandra, build.xml
- test/conf/cassandra.yaml
- test/unit/org/apache/cassandra/utils/memory/NativeAllocatorTest.java
- test/unit/org/apache/cassandra/utils/memory/MemtableCleanerThreadTest.java
- test/unit/org/apache/cassandra/db/memtable/MemtableSizeTestBase.java
- CHANGES.txt (CASSANDRA-12228 entry)
- https://issues.apache.org/jira/browse/CASSANDRA-12228 (cited, not fetched)
- https://cassandra.apache.org/doc/5.0/cassandra/managing/configuration/cass_yaml_file.html (cited, not fetched)
- https://docs.oracle.com/en/java/javase/11/tools/jcmd.html (cited, not fetched)

## D. Stage-4 feedback

**2026-10-22, run 1 (both tiers), results file `stage4-runtime-verification/results/memtable_heap_space-needsCleaning-nextClean--autonomous.md`.** Design audit: Ready after amendments (U1, U2, K1, K3, K4, dated 2026-10-21 next to the text they change; frozen sha256 `0378bf7d45276199e3bb3971324e5b5224cd7fc636c2927a11fd676289500bad`). Not committed.

- **Unit: Confirmed — caps (B2g row 1).** Every B2c value exact: first true of line 128 at chunk 26 / 65 / 86 / 129 / 231 for t = 0.10 / 0.25 / 1/3 / 0.50 / 0.90 at 64 MiB (strict `>`), 33 / 65 / 129 at 32 / 64 / 128 MiB (t = 0.25); `nextClean = reclaiming + (long)(L·t)` at every trigger; 9 / 3 / 2 / 1 / 1 triggers with live = m·C; block at exactly L; after release exactly `released/C` more chunks.
- **Cluster: Confirmed — caps (B3g row 1, with the R3 positive-control row; the R5 "hard cap not exercised" row also applies).** 3 M × 1 KiB at 10 k/s. Trigger `live` 0.33 (R1–R3), 0.15 (R4), 0.66 (R5) at every one of 206 triggers; line 128 traced returning true within 7 B – 7.8 KiB above `(long)(L·t)`; N_flush 101 / 25 / 12 at 128 / 512 / 1024 MiB (R1/R3 = 8.4) and 56 vs 25 at t = 0.15 vs 1/3; pool usage incl. flushing 71.7 / 226.2 / 467.5 MiB; forced-GC memtable live heap 42.8 / 180.4 / 363.5 MiB; never near L (max 0.73 L in R5), 0 writers blocked.
- **Missed sub-predictions:** K1's 1b (≥ 95 % of traced lines exact): the trace rule reads its fields after `needsCleaning` returns, so 43 of 148 lines carry a snapshot taken after a concurrent switch; all 105 self-consistent lines are exact. B3f 2 (R5 P_pool ≥ 0.85 L): 0.73 L, flushes kept up.
- **Design notes for stage 3:** B3d's O1 (`AllMemtablesOnHeapDataSize`) reads only the current memtable (`TableMetrics.java:876-882`), not `SubPool.used()` (fixed by K1 before the run). The B2e code lacked B2h's off-heap print (U1), and Part C's after-release reading is racy (U2).
- **Overlap with the closed `tryAllocate` cases:** Part C and R5 re-test the hard check (`MemtablePool.java:156`); what is new here is the soft trigger at `L·t`, its strict `>`, the `reclaiming` offset, and the dose-response of real memtable heap over three L values (incl. the default) and three t values.
- **Runbook/harness defects (results §3):** stress started 1 s after start-up failed to connect (retry added); Byteman `traceln` is lost after `CassandraDaemon` closes `System.out` (trace file); a killed, edited script stopped the next attempt's node; logback's midnight roll emptied R4's offset-based log (rebuilt). None changed B2f/B3f.
