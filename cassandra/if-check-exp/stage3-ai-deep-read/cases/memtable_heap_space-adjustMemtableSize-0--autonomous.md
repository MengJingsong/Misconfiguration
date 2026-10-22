# memtable_heap_space — verification solution  <!-- file: cases/memtable_heap_space-adjustMemtableSize-0--autonomous.md -->

| Field | Value |
|---|---|
| Entry pointer | `src/java/org/apache/cassandra/index/sai/StorageAttachedIndex.java:1006` |
| Pinned source | `cassandra-5.0.9` |
| Session / date | Claude Opus 5.5 (`claude-opus-5-5`), Claude Code 2.1.305, 2026-10-22 |
| Estimate | `positive`. The `if (additionalSpace >= 0)` at line 1006 passes each SAI memtable-index growth estimate to `memtable.markExtraOnHeapUsed`, which charges it to the global on-heap memtable pool whose limit is `memtable_heap_space`. That charge counts toward flush triggering and toward write blocking. So the SAI in-memory index is held to `memtable_heap_space`, but only by a constant factor above 1, because part of what it retains (per-row `PrimaryKey`/`DecoratedKey` objects, trie buffer slack) is never charged. |
| Ground | — |

## A. Constraint trace

**A1. The constraint.** `memtable_heap_space`, a configuration entry (cassandra.yaml).
- Declared at `src/java/org/apache/cassandra/config/Config.java:186-187` (`public DataStorageSpec.IntMebibytesBound memtable_heap_space;`, replacing the old key `memtable_heap_space_in_mb`). Unit: MiB.
- Default: if unset, `Runtime.getRuntime().maxMemory() / 4` in MiB (`src/java/org/apache/cassandra/config/DatabaseDescriptor.java:586-587`). A value of 0 is rejected (`:588-589`). `conf/cassandra.yaml:797` leaves it commented out ("If omitted, Cassandra will set both to 1/4 the size of the heap").
- Read once into the static pool: `AbstractAllocatorMemtable.MEMORY_POOL = createMemtableAllocatorPool()` (`src/java/org/apache/cassandra/db/memtable/AbstractAllocatorMemtable.java:59`) computes `heapLimit = DatabaseDescriptor.getMemtableHeapSpaceInMiB() << 20` (`:80`). The limit is final in `MemtablePool.SubPool.limit` (`src/java/org/apache/cassandra/utils/memory/MemtablePool.java:105`), so changing it needs a restart.
- Two other inputs shape when the cap acts. `memtable_cleanup_threshold` (`Config.java:190`; default `1/(1+memtable_flush_writers)`, `DatabaseDescriptor.java:761-763`; `memtable_flush_writers` defaults to 2 with one data directory, `:752-754`, giving 1/3) sets when a flush is triggered. `memtable_allocation_type` (`conf/cassandra.yaml:825`, default `heap_buffers`) picks the pool class (`AbstractAllocatorMemtable.java:87-109`). For every allocation type, the on-heap sub-pool gets `heapLimit`.
- Can also be set by system property, for tests only: `-Dcassandra.config.allow_system_properties=true -Dcassandra.settings.memtable_heap_space=<N>MiB` (`src/java/org/apache/cassandra/config/YamlConfigurationLoader.java:71,152-168`).

**A2. What it caps.** Heap: the total bytes that live (and flushing) memtables report to the on-heap `MemtablePool.SubPool` (`allocated`, `MemtablePool.java:111`, read by `used()` at `:216-219`). The target line feeds that total a usage-side quantity: `additionalSpace`, the estimated heap growth of the table's SAI in-memory index (`TrieMemoryIndex` / `VectorMemoryIndex`) from indexing one row. The check at line 1006 compares `additionalSpace` with `0`. The real limit comparison is downstream in `SubPool.tryAllocate`: `allocated + size > limit` (`MemtablePool.java:156`).

**A3. Mechanism.**
1. Write path: `ColumnFamilyStore.apply` builds an `UpdateTransaction` for the current memtable and calls `mt.put(update, indexer, opGroup)` (`src/java/org/apache/cassandra/db/ColumnFamilyStore.java:1475-1477`). For SAI, `StorageAttachedIndex.indexerFor` returns `new UpdateIndexer(key, memtable, writeContext)` for UPDATE transactions only (`StorageAttachedIndex.java:563-578`). `key` is `update.partitionKey()`, the mutation's own `DecoratedKey`, not the memtable's clone.
2. `UpdateIndexer.insertRow` / `updateRow` call `memtableIndexManager.index(...)` / `.update(...)` and pass the returned byte count to `adjustMemtableSize` (`StorageAttachedIndex.java:989-1000`).
3. `MemtableIndexManager.index` looks up or creates the per-memtable `MemtableIndex` (`src/java/org/apache/cassandra/index/sai/memory/MemtableIndexManager.java:59-67,69-96`) and sums `MemtableIndex.index(...)`. That method returns `memoryIndex.add(...)` and also adds the value to the `estimatedMemoryUsed` LongAdder (`MemtableIndex.java:90-99`). For non-vector types, `update` just re-indexes the new row (`MemtableIndexManager.java:98-103`), so the value is always ≥ 0.
4. `TrieMemoryIndex.add` returns the growth of `data.sizeOnHeap()` + `data.sizeOffHeap()` + `PrimaryKeysReducer.heapAllocations()` (`TrieMemoryIndex.java:94-127`). `InMemoryTrie.sizeOnHeap()` counts `contentCount` references + chunk-array headers + `allocatedPos` (used bytes, not buffer capacity) (`src/java/org/apache/cassandra/db/tries/InMemoryTrie.java:975-981`). `PrimaryKeysReducer` charges `PrimaryKeys.EMPTY_SIZE` for a new term plus a fixed `SET_ENTRY_OVERHEAD = 36` per key added (`TrieMemoryIndex.java:369-378`, `src/java/org/apache/cassandra/index/sai/utils/PrimaryKeys.java:36-48,65-68`).
5. **Target check** (`StorageAttachedIndex.java:1003-1008`): `if (additionalSpace >= 0) memtable.markExtraOnHeapUsed(additionalSpace, opGroup);`. A negative delta is dropped and never credited back. Only `VectorMemoryIndex.update` can return a negative delta (`VectorMemoryIndex.java:126-146`), so this path over-charges and never under-charges.
6. `AbstractAllocatorMemtable.markExtraOnHeapUsed` → `getAllocator().onHeap().allocate(additionalSpace, opGroup)` (`AbstractAllocatorMemtable.java:194-197`). The SAI bytes always go to the **on-heap** sub-allocator, whatever `memtable_allocation_type` is.
7. `SubAllocator.allocate` (`src/java/org/apache/cassandra/utils/memory/MemtableAllocator.java:169-197`) loops:
   - `parent.tryAllocate(size)`: CAS `allocated += size` only if `allocated + size <= limit` (`MemtablePool.java:151-161`). On success it calls `acquired` → `maybeClean()` (`:187-190`). That triggers the cleaner when `used() > reclaiming + limit*cleanThreshold` (`:125-147`).
   - Otherwise, if `opGroup.isBlocking()`, the allocation is forced through with `allocated(size)` and the limit is ignored (`MemtableAllocator.java:180-184`, `MemtablePool.java:177-185`). **Overshoot path:** writes that a pending flush barrier is waiting on.
   - Otherwise the writer registers on `hasRoom` and blocks until memory is released (`MemtableAllocator.java:185-195`). **Cap outcome:** the write thread stalls (metric `MemtablePool.BlockedOnAllocation`, `MemtablePool.java:63`).
8. The cleaner (`flushLargestMemtable`, `AbstractAllocatorMemtable.java:250-319`) ranks tables by `ownershipRatio` = `owns/limit`. `owns` includes the SAI charge, so a table's SAI index pushes it toward being chosen. It logs `Flushing largest ... Used total: ...` (`:293`), and `ColumnFamilyStore` logs `Enqueuing flush of <ks>.<t>, Reason: MEMTABLE_LIMIT` (`ColumnFamilyStore.java:1055`).
9. Release: on flush, `switchOut` → `allocator.setDiscarding()` (`AbstractAllocatorMemtable.java:166-170`). After the flush, `discard()` → `setDiscarded()` → `releaseAll()` returns `owns` to the pool and signals waiters (`MemtableAllocator.java:140-155`). SAI drops its `MemtableIndex` on `MemtableDiscardedNotification` (`src/java/org/apache/cassandra/index/sai/StorageAttachedIndexGroup.java:283-285`, `MemtableIndexManager.java:126-129`). The charged bytes and the retained objects are released at the same time.

Bypasses and under-counts (things the cap does not see):
- (a) **Uncharged per-row objects.** Each row creates a `SkinnyPrimaryKey`/`WidePrimaryKey` (a non-static inner class with fields `token`, `partitionKey`, plus the outer `Factory` reference: `src/java/org/apache/cassandra/index/sai/utils/PrimaryKey.java:102-120,169-260`). It also retains the mutation's `DecoratedKey`, `Token` and key `ByteBuffer`/`byte[]`. The memtable keeps a separate clone (`SkipListMemtable` clones the key into its allocator). Only the 36-byte set-entry overhead is charged. Expected uncharged amount is about 24 (PK) + 24 (BufferDecoratedKey) + 24 (LongToken) + 48 (HeapByteBuffer) + 24 (byte[] for an 8-byte key) ≈ 144 B/row with compressed oops (estimate, to be measured).
- (b) **Trie buffer slack.** `InMemoryTrie.allocateBlock` allocates buffers in doubling chunks (`BUF_START_SIZE << leadBit`, `InMemoryTrie.java:143-160`), while only `allocatedPos` is charged. `AtomicReferenceArray` content chunks also double (`:164-176`). Up to about 2× the trie bytes can be resident but uncharged.
- (c) **Off-heap mis-attribution.** With `offheap_buffers`/`offheap_objects`, `TrieMemtable.BUFFER_TYPE` is `OFF_HEAP` (`src/java/org/apache/cassandra/db/memtable/TrieMemtable.java:94`, `src/java/org/apache/cassandra/config/Config.java:1215-1228`). The SAI trie then lives in direct memory but is charged to the heap pool, and `memtable_offheap_space` never sees it.
- (d) Forced allocation when `opGroup.isBlocking()` (step 7).
- (e) Negative vector deltas are dropped (step 5): over-charge, conservative.
- (f) Only `AbstractAllocatorMemtable` implements `markExtraOnHeapUsed` in-tree (grep result). A third-party `Memtable` implementation could ignore it.

**A4. Other consumers.**
- The memtable's own data, charged to the same pool. Other tables' memtables share the global pool. Legacy 2i index memtables are counted in the ranking (`AbstractAllocatorMemtable.java:268-270`). SASI uses the same `markExtraOnHeapUsed` hook (`src/java/org/apache/cassandra/index/sasi/SASIIndex.java:320`).
- SAI structures outside this path: SSTable-attached segment building during flush and compaction (`sai_options.segment_write_buffer_size`, `src/java/org/apache/cassandra/config/StorageAttachedIndexOptions.java:35`), query-time iterators and priority queues (`TrieMemoryIndex.java:326-362`), and index file caches.
- JVM baseline: caches, Netty buffers, compaction, and GC headroom.

**A5. Evidence beyond the source.**
- `doc/modules/cassandra/pages/developing/cql/indexing/sai/sai-read-write-paths.adoc:26-29`: "SAI calculates an estimate of the incremental heap consumption of the new entry. This estimate counts against the heap usage of the underlying Memtable." It also says the estimate is exposed as metrics.
- `test/unit/org/apache/cassandra/index/sai/memory/TrieMemoryIndexTest.java:79-87` (`heapGrowsAsDataIsAddedTest`) checks only that `add` returns > 0.
- `CHANGES.txt` has no entry about SAI memtable accounting.
- The local clone's git history is shallow (one commit at the tag), so it was not used.

## B. Verification solution

**B1. Claim under test.** Every byte that `TrieMemoryIndex.add` reports is charged to the on-heap memtable pool limited by `memtable_heap_space`. As a result:
- the SAI memtable index's reported size, and its actual retained heap, stay bounded by a constant multiple of `memtable_heap_space`, whatever the number of rows written;
- that bound moves with the knob;
- the retained heap exceeds the charge by a factor r > 1, coming from the uncharged per-row key objects and buffer slack. The tiers measure r.

### B2. Unit tier

**B2a. Environment and build.**
- JDK 11.0.32.1 and Ant 1.10.12 on a node with ≥ 10 GB free on local `/`.
- `WORK=/var/tmp/sai-exp`. Check that `df -h /var/tmp` shows the local root fs.
- Clone: `git clone --branch cassandra-5.0.9 file:///proj/misconfiguration-PG0/git-repos/cassandra-src $WORK/cassandra` (detached at the tag; the untracked `HeapPoolTest.java` is not cloned).
- Build in the clone only: `cd $WORK/cassandra && ant jar build-test` (Maven download needs network).
- Test source (new file in the local clone only): `$WORK/cassandra/test/unit/org/apache/cassandra/index/sai/memory/SaiMemtableChargeTest.java`, listed in B2e.
- The test JVM is the standard `testsome` fork: `maxmemory=1024m`, jamm javaagent present (`build.xml:1153-1159`), test config `test/conf/cassandra.yaml` (default memtable = SkipListMemtable, one data dir → 2 flush writers → cleanup threshold 1/3).

**B2b. Knobs.**
- `memtable_heap_space`, set with `-Dtest.jvm.args="-Dcassandra.config.allow_system_properties=true -Dcassandra.settings.memtable_heap_space=<v>"`:
  - **512MiB** for the accounting run (U1/U2): large enough that 100k rows never trigger a flush.
  - **32MiB** and **96MiB** for the cap runs (U3): the limit is crossed many times, and 3× apart shows scaling.
- `memtable_allocation_type=unslabbed_heap_buffers`, set with `-Dcassandra.settings.memtable_allocation_type=unslabbed_heap_buffers`. HeapPool charges exact byte sizes, so the U1 difference is exact. With `heap_buffers`, slab regions charge 1 MiB at a time.

**B2c. Workload.**
- Tables `(pk int PRIMARY KEY, v text)`. SAI on `v`: `CREATE INDEX ON %s(v) USING 'sai'`.
- `v` is a 32-character hex string from a 64-bit mixer, so terms are practically unique with little prefix sharing.
- Writes go through `CQLTester.execute` (internal CQL → `Mutation.apply` → `ColumnFamilyStore.apply(..., updateIndexes=true)`).
- U1/U2: N=100,000 rows into each of `plain` and `sai`. Expected charge of a few hundred B/row → tens of MB, well below 512MiB × 1/3 ≈ 170 MiB, so no flush.
- U3: N=400,000 rows into `sai` (and, as the control, into `plain` in its own method). With an assumed ≥ 300 B/row total charge, that is ≥ 120 MB charged, about 11 flushes at 32MiB (threshold ≈ 10.7 MiB) and about 3–4 at 96MiB.

**B2d. Observables and instruments.** All read in-process and written to CSV (`-Dsai.out`).
- `S` = `idx.memtableIndexManager().estimatedMemIndexMemoryUsed()`. This is Σ`additionalSpace` over live memtables, the target line's operand (all values ≥ 0 for text).
- `W` = `liveMemtableWriteCount()`.
- `O_t` = `((AbstractAllocatorMemtable) cfs.getTracker().getView().getCurrentMemtable()).getAllocator().onHeap().owns()` for each table.
- `P` = `AbstractAllocatorMemtable.MEMORY_POOL.onHeap.used()` (the pool's `allocated`) and `MEMORY_POOL.onHeap.limit`.
- `F` = `cfs.metric.memtableSwitchCount.getCount()`.
- `D` = `ObjectSizes.measureDeep(trie)` and `D2` = `ObjectSizes.measureDeepOmitShared(trie)`, where `trie` is `TrieMemoryIndex.data` read by reflection. This includes the `PrimaryKeys`, the primary keys, the decorated keys and their buffers.
- `K` = `ObjectSizes.measureDeep(idx.keyFactory())`, the shared constant to subtract from D.
- Not observable here: GC-level heap and allocator wait times. Those belong to the cluster tier.

**B2e. Procedure.**
1. Create `$WORK/cassandra/test/unit/org/apache/cassandra/index/sai/memory/SaiMemtableChargeTest.java`:

```java
package org.apache.cassandra.index.sai.memory;

import java.io.FileWriter;
import java.io.PrintWriter;
import java.lang.reflect.Field;

import org.junit.Assume;
import org.junit.Test;

import org.apache.cassandra.config.DatabaseDescriptor;
import org.apache.cassandra.db.ColumnFamilyStore;
import org.apache.cassandra.db.memtable.AbstractAllocatorMemtable;
import org.apache.cassandra.index.sai.SAITester;
import org.apache.cassandra.index.sai.StorageAttachedIndex;
import org.apache.cassandra.index.sai.StorageAttachedIndexGroup;
import org.apache.cassandra.utils.ObjectSizes;

public class SaiMemtableChargeTest extends SAITester
{
    private static final int N = Integer.getInteger("sai.rows", 100_000);
    private static final String OUT = System.getProperty("sai.out", "/var/tmp/sai-exp/unit.csv");

    private static String term(int i)
    {
        long a = (i + 1L) * 0x9E3779B97F4A7C15L, b = (i + 7L) * 0xC2B2AE3D27D4EB4FL;
        return String.format("%016x%016x", a ^ (a >>> 29), b ^ (b >>> 31));
    }
    private static long owns(ColumnFamilyStore c)
    {
        return ((AbstractAllocatorMemtable) c.getTracker().getView().getCurrentMemtable()).getAllocator().onHeap().owns();
    }
    private static StorageAttachedIndex sai(ColumnFamilyStore c)
    {
        return (StorageAttachedIndex) StorageAttachedIndexGroup.getIndexGroup(c).getIndexes().iterator().next();
    }
    private void insert(String table, int i) throws Throwable
    {
        execute("INSERT INTO " + KEYSPACE + '.' + table + " (pk, v) VALUES (?, ?)", i, term(i));
    }

    @Test // U1 + U2: run with memtable_heap_space=512MiB
    public void testChargeAndFootprint() throws Throwable
    {
        Assume.assumeTrue(DatabaseDescriptor.getMemtableHeapSpaceInMiB() >= 512);
        String plain = createTable("CREATE TABLE %s (pk int PRIMARY KEY, v text)");
        String withSai = createTable("CREATE TABLE %s (pk int PRIMARY KEY, v text)");
        createIndex("CREATE INDEX ON %s(v) USING 'sai'");
        disableCompaction(KEYSPACE);
        ColumnFamilyStore cP = getColumnFamilyStore(KEYSPACE, plain), cS = getColumnFamilyStore(KEYSPACE, withSai);
        long p0 = owns(cP), s0 = owns(cS), f0 = cS.metric.memtableSwitchCount.getCount();
        for (int i = 0; i < N; i++) { insert(plain, i); insert(withSai, i); }
        StorageAttachedIndex idx = sai(cS);
        long S = idx.memtableIndexManager().estimatedMemIndexMemoryUsed();
        long W = idx.memtableIndexManager().liveMemtableWriteCount();
        long dP = owns(cP) - p0, dS = owns(cS) - s0;
        MemtableIndex mi = idx.memtableIndexManager().getLiveMemtableIndexesSnapshot().iterator().next();
        Field fm = MemtableIndex.class.getDeclaredField("memoryIndex"); fm.setAccessible(true);
        Field fd = TrieMemoryIndex.class.getDeclaredField("data"); fd.setAccessible(true);
        Object trie = fd.get(fm.get(mi));
        long D = ObjectSizes.measureDeep(trie), D2 = ObjectSizes.measureDeepOmitShared(trie);
        long K = ObjectSizes.measureDeep(idx.keyFactory());
        try (PrintWriter w = new PrintWriter(new FileWriter(OUT, true)))
        {
            w.println("U1U2,N,W,S,dS,dP,dS_minus_dP,D,D2,K,flushes");
            w.printf("U1U2,%d,%d,%d,%d,%d,%d,%d,%d,%d,%d%n", N, W, S, dS, dP, dS - dP, D, D2, K,
                     cS.metric.memtableSwitchCount.getCount() - f0);
        }
    }

    private void capRun(boolean withIndex) throws Throwable
    {
        long L = DatabaseDescriptor.getMemtableHeapSpaceInMiB() << 20;
        Assume.assumeTrue(L <= (128L << 20));
        String t = createTable("CREATE TABLE %s (pk int PRIMARY KEY, v text)");
        if (withIndex) createIndex("CREATE INDEX ON %s(v) USING 'sai'");
        ColumnFamilyStore c = getColumnFamilyStore(KEYSPACE, t);
        StorageAttachedIndex idx = withIndex ? sai(c) : null;
        long maxP = 0, maxS = 0;
        try (PrintWriter w = new PrintWriter(new FileWriter(OUT, true)))
        {
            w.println("U3,withIndex,L,rows,poolUsed,ownsCurrent,S,flushes");
            for (int i = 0; i < N; i++)
            {
                insert(t, i);
                if (i % 5000 == 0 || i == N - 1)
                {
                    long P = AbstractAllocatorMemtable.MEMORY_POOL.onHeap.used();
                    long S = withIndex ? idx.memtableIndexManager().estimatedMemIndexMemoryUsed() : 0;
                    maxP = Math.max(maxP, P); maxS = Math.max(maxS, S);
                    w.printf("U3,%b,%d,%d,%d,%d,%d,%d%n", withIndex, L, i + 1, P, owns(c), S,
                             c.metric.memtableSwitchCount.getCount());
                }
            }
            w.printf("U3MAX,%b,%d,%d,%d,%d%n", withIndex, L, N, maxP, maxS);
        }
    }

    @Test public void testCapBindsSai() throws Throwable   { capRun(true); }
    @Test public void testCapBindsPlain() throws Throwable { capRun(false); }
}
```

2. `mkdir -p $WORK && rm -f $WORK/unit.csv`.
3. U1/U2: `cd $WORK/cassandra && ant testsome -Dno-build-test=true -Dtest.name=org.apache.cassandra.index.sai.memory.SaiMemtableChargeTest -Dtest.methods=testChargeAndFootprint -Dtest.jvm.args="-Dcassandra.config.allow_system_properties=true -Dcassandra.settings.memtable_heap_space=512MiB -Dcassandra.settings.memtable_allocation_type=unslabbed_heap_buffers -Dsai.rows=100000 -Dsai.out=$WORK/unit.csv"` (the first time, run without `-Dno-build-test` so the new test compiles).
4. U3 at 32MiB: same command with `-Dtest.methods=testCapBindsSai,testCapBindsPlain`, `memtable_heap_space=32MiB`, `-Dsai.rows=400000`.
5. U3 at 96MiB: repeat step 4 with `memtable_heap_space=96MiB`.
6. Check the JUnit XML under `$WORK/cassandra/build/test/output/` to confirm that no test was skipped by `Assume` (skipped means the property did not take effect: invalid run). Also grep the test log for `Global memtable on-heap threshold is enabled at` (`DatabaseDescriptor.java:590`) to confirm the value.
7. `rm -rf $WORK/cassandra/build/test/cassandra` (test data) after copying `unit.csv`.

> **Audit amendment 2026-10-22 (stage 4, step 0, before any reading) — A-U1.** Steps 4 and 5 ("same command") keep
> `-Dcassandra.settings.memtable_allocation_type=unslabbed_heap_buffers`, so U3's flush ratio compares the same charge as U1.
> The U3 runs at 32MiB and 96MiB are separate `ant testsome` invocations (one JVM each); the order of the two methods inside
> one JVM is JUnit's and is not controlled.

**B2f. Predictions** (stated before any run).
- U1 (512MiB, unslabbed):
  - `dS − dP == S` exactly: the SAI charge is the only difference between the two tables' memtable ownership.
  - `S > 0`, `W == N`, `flushes == 0`.
  - `S/N` between 100 and 400 B/row.
- U2:
  - `(D − K)/S = r_unit` between 1.2 and 2.5.
  - `(D − K) − S ≥ 100·N`: at least ~100 B/row of uncharged key objects.
  - `D2 ≤ D`.
- U3 (32MiB and 96MiB, with index):
  - At every sample, `poolUsed ≤ L` and `S ≤ L`.
  - `S` is a sawtooth: it drops after each flush, and every peak S ≤ `L/3 + one flush-lag margin` (≤ L/2).
  - `flushes(sai) / flushes(plain)` ≈ `(dS/N)/(dP/N)` from U1 ±25%, which is > 1.
  - `flushes(L=32) / flushes(L=96)` ≈ 3 ±1.
  - `maxS(96)/maxS(32)` between 2 and 4.
- The claim is wrong if any of these holds:
  - `dS − dP ≠ S` (the charge is not applied, or is applied twice);
  - `S` or `poolUsed` exceeds `L` at any sample;
  - `S` grows monotonically with rows across flushes;
  - flush counts with and without the index are equal.

**B2g. Readings.**

| Observation | Meaning |
|---|---|
| `dS − dP == S`, flushes(sai) > flushes(plain), S sawtooth ≤ L, maxS scales with L | Claim holds at operand level: SAI growth is charged to and governed by `memtable_heap_space` |
| `dS − dP == 0` with `S > 0` | Charge not applied (check at 1006 or `markExtraOnHeapUsed` path broken): claim refuted |
| `dS − dP ≈ 2·S` or other multiple | Double or mis-charging: claim partially refuted, report the factor |
| `S` keeps rising across flushes / never resets | MemtableIndex not released with memtable: cap does not bound SAI: claim refuted |
| `poolUsed > L` at a sample | Overshoot path (blocking opGroup) larger than expected: note magnitude; claim holds only approximately |
| `(D−K)/S` > 3 | Uncharged footprint dominates; cap binds only loosely (positive with large r) |
| No flushes at 32MiB, or test skipped | Knob not applied (system-property override failed): run invalid, not confirmed |
| plain control shows no flush at 32MiB | Positive control failed (cap not reached): not confirmed, increase N |

> **Audit amendment 2026-10-22 (stage 4, step 0, before any reading) — A-U2: how B2g decides.** The rows above are kept; this
> block makes each one a numeric test, adds the outcomes the table did not cover (flat across L, a flush during U1, a
> decrease-free S, equal flush counts) and settles the conflict between B2f ("`poolUsed` exceeds `L` at any sample" = wrong)
> and the row "`poolUsed > L` … holds only approximately". Rows are tested in this order; the first that matches is the
> verdict. Qualifiers (Q) are added to it and do not change it.
>
> | # | Test (all from `unit.csv` and the JUnit XML) | Verdict |
> |---|---|---|
> | 1 | a test skipped by `Assume`; the test log's `Global memtable on-heap threshold is enabled at` shows another value; `flushes` ≠ 0 in U1; or the plain table has 0 flushes in U3 at 32MiB | **Invalid** (knob not applied, U1 reset by a flush, or cap not reached) |
> | 2 | `dS − dP == 0` with `S > 0`, or `flushes(sai) ≤ flushes(plain)` at either L | **Refuted** — charge not applied / not governing |
> | 3 | `abs(dS − dP − S) > 0.01·S` | **Refuted** (mis-charge; factor `(dS − dP)/S` reported) |
> | 4 | `S > L` at any U3 sample, or `poolUsed > 1.25·L` at any sample | **Refuted** — usage exceeds the limit |
> | 5 | in a U3 SAI run with ≥ 3 flushes, `S` never decreases between consecutive samples | **Refuted** — index not released with the memtable |
> | 6 | `flushes(sai,32)/flushes(sai,96) < 1.5` **and** `maxS(96)/maxS(32) < 1.5` | **Refuted** — does not follow the knob (flat) |
> | 7 | `abs(dS − dP − S) ≤ 0.01·S`; `flushes(sai) > flushes(plain)` at both L; in each U3 SAI run `S` decreases at least 3 times and `maxS ≤ L/2`; `flushes(sai,32)/flushes(sai,96) ≥ 1.5` and `maxS(96)/maxS(32) ≥ 1.5` | **Confirmed** (row 1) — Effect *caps* |
> | 8 | anything else | **Not confirmed (no matching row)** — Effect undetermined |
> | Qa | `L < poolUsed ≤ 1.25·L` at some sample | "holds only approximately": magnitude reported |
> | Qb | `(D − K)/S > 3` | uncharged footprint dominates (loose bound), r reported |
> | Qc | `(D − K)/S ≤ 1` | B1's third bullet (r > 1) does not hold; reported, the cap verdict is unchanged |
>
> The other numbers in B2f (`S/N` in 100–400, `W == N`, `r_unit` in 1.2–2.5, `(D − K) − S ≥ 100·N`, `D2 ≤ D`, the ±25 % flush
> ratio, `3 ± 1`, `maxS(96)/maxS(32)` in 2–4, peak S ≤ L/2) are sub-predictions: each is reported hit or miss and does not
> change the row. The unit tier compares two binding values (32, 96 MiB) plus a non-binding 512 MiB; the default (heap/4 =
> 256 MiB in the 1 GiB test JVM) is covered by the cluster tier (A-K1).

**B2h. Controls.**
- The `plain` twin table with identical data isolates the SAI charge (U1) and gives the cap-binds positive control with no SAI (U3 plain).
- Two L values separate "follows the knob" from "constant flush cadence".
- The `Assume` guards plus the startup log line confirm that the knob took effect.
- `unslabbed_heap_buffers` removes the 1 MiB slab granularity from the exact equality.
- `K` removes the shared factory and partitioner from `D`.

### B3. Cluster tier

**B3a. Environment and build.**
- One node on 127.0.0.1, built from the same local clone: `cd $WORK/cassandra && ant jar` (builds `bin/` runnable tree). Then `ant stress-build` for `tools/bin/cassandra-stress` (`build.xml:577`).
- Separate config dir per run: `cp -r $WORK/cassandra/conf $WORK/conf-<run>`. In `$WORK/conf-<run>/cassandra.yaml` set:
  - `data_file_directories: [$WORK/node/data]`
  - `commitlog_directory: $WORK/node/commitlog`
  - `hints_directory: $WORK/node/hints`
  - `saved_caches_directory: $WORK/node/saved_caches`
  - `cdc_raw_directory: $WORK/node/cdc_raw`
  - `memtable_heap_space: <L>MiB`
  - `memtable_allocation_type: heap_buffers` (default; stated explicitly)
  - `commitlog_total_space: 8192MiB` (so commit-log pressure does not trigger flushes before the memtable limit)
  - `concurrent_compactors: 2`
  - leave `memtable_cleanup_threshold` and `memtable_flush_writers` unset (→ 1/3).
- Env:
  - `export CASSANDRA_CONF=$WORK/conf-<run> CASSANDRA_LOG_DIR=$WORK/logs-<run> MAX_HEAP_SIZE=4G`
  - G1 (default in `jvm11-server.options:63`); GC log goes automatically to `$CASSANDRA_LOG_DIR/gc.log` (`cassandra-env.sh:81-83`)
  - JMX local on 7199 (default).
- Start: `$WORK/cassandra/bin/cassandra -p $WORK/node.pid`. Wait until `$WORK/cassandra/bin/nodetool status` shows `UN`.

**B3b. Knobs.** `memtable_heap_space`, one fresh node per value. Runs:
- R1: L=64MiB, SAI table.
- R2: L=256MiB, SAI table.
- R3: L=64MiB, plain table (positive control).
- R4: L=256MiB, plain table.
- R5 (optional): L=1024MiB, SAI table.

The 4× spacing makes scaling visible; all values are ≤ 1/4 of the 4 GiB heap. Wipe `$WORK/node` between runs.

> **Audit amendment 2026-10-22 (stage 4, step 0, before any reading) — A-K1.** R5 (L = 1024MiB, SAI table) is **required**,
> not optional: 1024 MiB is the default for `MAX_HEAP_SIZE=4G` (heap/4, `DatabaseDescriptor.java:586-587`), so the SAI runs
> cover three values including the default. **R6** is added: L = 1024MiB, plain table (positive control at the default).
> Run order R1, R2, R3, R4, R5, R6.
>
> **A-K2.** Every run's `cassandra.yaml` also sets `sai_options: segment_write_buffer_size: 16MiB`. Reason (from the source, not
> from any reading): SAI segments built **during compaction** buffer up to `segment_write_buffer_size` of heap
> (default 1024 MiB, `StorageAttachedIndexOptions.java:26`, `V1OnDiskFormat.java:115-128`). That heap is outside the
> memtable pool and exists only in the SAI runs, so with STCS compactions of millions of rows it would enter ΔH(R1) − ΔH(R3)
> and the "ΔH bounded" test. Memtable flush does not use this limiter (`V1OnDiskFormat.java:115`). The gauge
> `org.apache.cassandra.metrics:type=StorageAttachedIndex,name=SegmentBufferSpaceUsedBytes` is sampled (A-K3) to show what is left.

**B3c. Workload.** cassandra-stress user profile `$WORK/sai-profile.yaml` (for R3/R4, drop `extra_definitions` and use `table: t_plain` / `CREATE TABLE t_plain ...`):

```yaml
keyspace: saiks
keyspace_definition: |
  CREATE KEYSPACE saiks WITH replication = {'class': 'SimpleStrategy', 'replication_factor': 1};
table: t_sai
table_definition: |
  CREATE TABLE t_sai (pk bigint PRIMARY KEY, v text) WITH compaction = {'class':'SizeTieredCompactionStrategy'};
extra_definitions:
  - CREATE INDEX t_sai_v_idx ON saiks.t_sai(v) USING 'sai';
columnspec:
  - name: v
    size: fixed(32)
    population: uniform(1..2000000000)
insert:
  partitions: fixed(1)
  batchtype: UNLOGGED
  select: fixed(1)/1
queries:
  read1:
    cql: select * from t_sai where pk = ?
    fields: samerow
```

> **Runbook-defect fix 2026-10-22 (stage 4, run 1, defect D1; B3f/B3g unchanged).** cassandra-stress runs the profile's
> `extra_definitions` on every invocation, so the load command after B3e step 2's schema run failed at once with
> `InvalidQueryException: Index 't_sai_v_idx' already exists` (R1 attempt 1, no load written). The line reads
> `- CREATE INDEX IF NOT EXISTS t_sai_v_idx ON saiks.t_sai(v) USING 'sai';`. The cluster tier restarts from R1.

Command: `$WORK/cassandra/tools/bin/cassandra-stress user profile=$WORK/sai-profile.yaml "ops(insert=1)" n=10000000 no-warmup cl=ONE -pop seq=1..10000000 -rate threads=64 -node 127.0.0.1 -log file=$WORK/stress-<run>.log`

Arithmetic (to be replaced by measured c values):
- Assume c_t ≈ 250–400 B/row memtable charge and c_s ≈ 150–350 B/row SAI charge. 10M rows then charge ≈ 4–7.5 GB in total. At L=64MiB (flush every ~21 MiB) that is ≈ 190–360 flushes; at 256MiB ≈ 50–90. So the limit is reached many times.
- Duration ≈ 3–10 min at 20–50k ops/s.
- Disk: about 10M × (~60–100 B data + ~50–100 B SAI on disk) ≈ 2–3 GB, ×2 during compaction, plus commit log ≤ 8 GiB. That is well under 50 GB.

**B3d. Observables and instruments.**
- *Charge* (every 2 s, script `sample.sh` looping on the commands below):
  - `nodetool sjk mx -mg -b 'org.apache.cassandra.metrics:type=Table,keyspace=saiks,scope=t_sai,name=MemtableOnHeapDataSize' -f Value`: current memtable `owns`, `TableMetrics.java:493-495`.
  - Same command with `name=AllMemtablesOnHeapDataSize` (includes flushing memtables, `:506-512`).
  - `nodetool sjk mx -mg -b 'org.apache.cassandra.metrics:type=StorageAttachedIndex,keyspace=saiks,table=t_sai,index=t_sai_v_idx,scope=IndexMetrics,name=MemtableIndexBytes' -f Value`: S, the operand (`IndexMetrics.java:58`; mbean name format `AbstractMetrics.java:84-96`).
  - `...name=LiveMemtableIndexWriteCount`.
  - `nodetool sjk mx -mg -b 'org.apache.cassandra.metrics:type=MemtablePool,name=BlockedOnAllocation' -f Count`.
  - Fallback if sjk fails: `tools/bin/jmxtool dump` and grep.
- *Flushes:*
  - `grep -c "Enqueuing flush of saiks.t_sai, Reason: MEMTABLE_LIMIT" $CASSANDRA_LOG_DIR/system.log`
  - the `Used total:` ratios from `Flushing largest` lines.
- *Actual heap* (the resource):
  - every 60 s: `jcmd $(cat $WORK/node.pid) GC.class_histogram > $WORK/hist-<run>-<t>.txt`. This forces a full GC, so it gives live bytes. Read the `Total` row, plus the rows for `org.apache.cassandra.index.sai.utils.PrimaryKey$Factory$SkinnyPrimaryKey`, `org.apache.cassandra.index.sai.utils.PrimaryKeys`, `org.apache.cassandra.db.BufferDecoratedKey` and `org.apache.cassandra.dht.Murmur3Partitioner$LongToken`.
  - `gc.log` for post-GC heap occupancy between histograms.
  - Baseline `H0`: the histogram `Total` after schema creation, before load.
  - `ΔH(t) = Total(t) − H0`.
- Not directly observable: which `byte[]` belong to the SAI trie and which to memtable slabs. SAI attribution comes from the R1−R3 difference and from SAI-specific class counts.

> **Audit amendment 2026-10-22 (stage 4, step 0, before any reading) — A-K3: instruments.**
> - The charge sampler is one small JMX client per run (harness `SaiPoll.java`) that reads every 2 s: the table's
>   `MemtableOnHeapDataSize`, `AllMemtablesOnHeapDataSize`, `MemtableColumnsCount` (Value) and `MemtableSwitchCount` (Count);
>   for SAI runs `MemtableIndexBytes` (S) and `LiveMemtableIndexWriteCount` (W); `MemtablePool` `BlockedOnAllocation` (Count);
>   `SegmentBufferSpaceUsedBytes` (A-K2); and `java.lang:type=Memory` `HeapMemoryUsage.used`. Reason: each `nodetool sjk mx`
>   call starts a JVM (about 1 s), so the listed values cannot be read every 2 s with it.
> - `AllMemtablesOnHeapDataSize` reads only the **current** memtables (`TableMetrics.java:506-512` → `getMemoryUsageWithIndexes`),
>   not flushing ones, so it is not `SubPool.used()` (citation error). The pool bound of B3f is read only from the on-heap
>   `Used total` ratio of the `Flushing largest` lines, as B3f already says. `MemtableIndexBytes` and
>   `LiveMemtableIndexWriteCount` cover live **and** flushing memtable indexes until discard (`MemtableIndexManager.java:126-160`).
> - Class histograms every **30 s** instead of 60 s (a 10M-row run lasts about 3–6 min, so 60 s would give 3–6 points for the
>   growth tests). "ΔH at 50 %" is the in-stress histogram nearest the midpoint of the stress run; "ΔH at 100 %" is the last
>   histogram taken while stress was running. Peak ΔH is the maximum over in-stress histograms.
> - Flush counts are taken only from `system.log` lines after the run's start offset, for the run's own table
>   (`saiks.t_sai` or `saiks.t_plain`).

**B3e. Procedure.**
1. `df -h /var/tmp` must show ≥ 30 GB free. Create `$WORK/node`, `$WORK/logs-<run>`, `$WORK/conf-<run>` as in B3a.
2. Start the node (B3a). Create the schema without load: `cassandra-stress user profile=... "ops(insert=1)" n=1 ...`, then `nodetool flush saiks`. Record `H0` with `jcmd GC.class_histogram`. Confirm the log line `Global memtable on-heap threshold is enabled at <L>MiB`.
3. Start `sample.sh` in the background (writes `$WORK/samples-<run>.csv` with timestamp, the five JMX values and the flush-line count). Start the 60 s histogram loop.
4. Run the stress command (B3c). When it finishes, keep sampling for 120 s, then `nodetool flush saiks` and take a last histogram.
5. Stop the samplers. Stop the node with `kill $(cat $WORK/node.pid)` and wait for exit. Verify with `pgrep -f CassandraDaemon` (must be empty) and `pgrep -f cassandra-stress`.
6. Archive `$WORK/logs-<run>`, the samples and the histograms. `rm -rf $WORK/node`. Repeat for R2–R4 (R5 optional).

**B3f. Predictions** (stated before any run).
- For each run with L:
  - max(`AllMemtablesOnHeapDataSize` summed over all tables) ≤ L (sampled; there is no global gauge for `allocated`, so use the `Used total` ratio in `Flushing largest` log lines: every logged on-heap value is ≤ 1.00).
  - `MemtableIndexBytes` (R1, R2) follows a sawtooth with max ≤ L/2, and does not trend upward over the run (max over the last third ≤ 1.2 × max over the first third).
- MEMTABLE_LIMIT flush count:
  - R1/R2 ≈ 4 ±1.5. R3/R4 ≈ 4 ±1.5.
  - R1/R3 ≈ (c_t + c_s)/c_t, using c_s = S/W from samples and c_t = owns/W in R3. Expected 1.3–2.5, and in all cases > 1.1.
- Actual heap:
  - peak ΔH (R1) ≤ 2.5 × L + 200 MiB (JVM noise), and peak ΔH (R2) ≤ 2.5 × 256MiB + 200 MiB;
  - peak ΔH (R2) / peak ΔH (R1) between 2 and 6;
  - ΔH at 50% and at 100% of the run differ by < 0.5 × L (bounded, not growing with rows written).
- SAI class count: the histogram count of `SkinnyPrimaryKey` ≤ 3 × (L/(c_t + c_s)) at every histogram, and never approaches 10M.
- SAI excess: peak ΔH(R1) − peak ΔH(R3) > 0. Its ratio to the SAI share of L, r_cluster = (ΔH_R1 − ΔH_R3)/(peak S), should be within ±30% of r_unit from U2.
- The claim is wrong if any of these holds:
  - the `SkinnyPrimaryKey` count or ΔH grows roughly linearly with rows written (SAI memory escapes the cap);
  - `MemtableIndexBytes` exceeds L;
  - R1 and R3 flush counts are equal within 5%;
  - peak ΔH does not change between L=64 and L=256.

> **Audit amendment 2026-10-22 (stage 4, step 0, before any reading) — A-K4.**
> - **c_t and c_s.** "c_t = owns/W in R3" cannot be computed (R3 has no SAI index, so no W). Defined instead per row of the
>   current memtable: c_t = median over R3 samples with `MemtableColumnsCount` ≥ 10,000 of
>   `MemtableOnHeapDataSize / MemtableColumnsCount` (one operation per inserted row); c_t + c_s = the same statistic over R1
>   samples. The predicted R1/R3 flush ratio is (c_t + c_s)/c_t from these; the SkinnyPrimaryKey bound uses R1's c_t + c_s
>   for every SAI run.
> - **R5 and R6 (A-K1)** take the same formulas: max `MemtableIndexBytes`(R5) ≤ 512 MiB; R2/R5 and R4/R6 MEMTABLE_LIMIT
>   flush ratios ≈ 4 ± 1.5; peak ΔH(R5) ≤ 2.5 × 1024 MiB + 200 MiB; peak ΔH(R5)/peak ΔH(R2) between 2 and 6. "R1/R2 ≈ 4 ±1.5"
>   and "R3/R4 ≈ 4 ±1.5" above are ratios of MEMTABLE_LIMIT flush counts.

**B3g. Readings.**

| Observation | Meaning |
|---|---|
| R1 flushes > R3 flushes, S sawtooth ≤ L/2, ΔH bounded and ∝ L, SkinnyPrimaryKey count bounded | Claim confirmed: `memtable_heap_space` governs SAI memtable heap, with factor r_cluster |
| R1 flushes ≈ R3 flushes while S > 0 | SAI charge not reaching the pool: claim refuted |
| SkinnyPrimaryKey count / ΔH grows linearly with rows in R1 but not R3 | SAI index retained beyond memtable lifetime: claim refuted (leak outside cap) |
| ΔH(R2)/ΔH(R1) ≈ 1 while flush counts follow 1/L | Heap dominated by something else (caches, compaction); cap governs charge but not observed heap: undetermined, inspect histograms |
| r_cluster ≫ r_unit (e.g. > 2× r_unit) | Extra uncharged retention in the real write path (e.g. key buffers sharing larger arrays); cap binds only loosely, report r |
| BlockedOnAllocation Count > 0 with flushes keeping up | Cap reached and blocking writers as designed (supports claim) |
| R3/R4 flush count does not scale with 1/L or ΔH not ∝ L | Positive control failed (memtable cap not binding under this workload): not confirmed |
| OOM / node crash in R1 but not R3 | SAI heap escapes the cap: claim refuted |

> **Audit amendment 2026-10-22 (stage 4, step 0, before any reading) — A-K5: how B3g decides.** The rows above are kept; this
> block makes each a numeric test and adds the outcomes the table did not cover (knob not applied, usage exceeds the limit,
> flat across the knob, heap growth in both arms). ΔH, peak ΔH and the 50 %/100 % points are as in A-K3; "flushes" are
> MEMTABLE_LIMIT flushes of the run's table. Rows are tested in this order; the first that matches is the verdict.
>
> | # | Test | Verdict |
> |---|---|---|
> | 1 | a run's `Global memtable on-heap threshold is enabled at` line shows another L; a run has 0 MEMTABLE_LIMIT flushes of its table; or stress did not complete for a reason other than an OOM/crash (or > 1 % errors) | **Invalid** (knob not applied or limit not reached) |
> | 2 | OOM or node crash in an SAI run (R1/R2/R5) but not in its plain twin at the same L (R3/R4/R6) | **Refuted** — SAI heap escapes the cap |
> | 3 | `MemtableIndexBytes` > L at any sample, or an on-heap `Used total` ratio > 1.00 in any `Flushing largest` line of an SAI run | **Refuted** — usage exceeds the limit |
> | 4 | flushes(R1)/flushes(R3) ≤ 1.05 | **Refuted** — SAI charge not reaching the pool |
> | 5 | in R1: the `SkinnyPrimaryKey` count at the last in-stress histogram > 3 × L/(c_t + c_s) and higher than at every earlier histogram; or ΔH(100 %) − ΔH(50 %) ≥ 0.5·L in R1 but < 0.5·L in R3 | **Refuted** — SAI index retained outside the cap |
> | 6 | flushes(R3)/flushes(R4) < 2 or flushes(R4)/flushes(R6) < 2 | **Not confirmed** — positive control failed |
> | 7 | flushes(R1)/flushes(R2) < 1.5 **and** peak ΔH(R2)/peak ΔH(R1) < 1.25 | **Refuted** — does not follow the knob (flat) |
> | 8 | peak ΔH(R2)/peak ΔH(R1) < 1.25 while flushes(R1)/flushes(R2) ≥ 1.5; or ΔH(100 %) − ΔH(50 %) ≥ 0.5·L in both R1 and R3 | **Not confirmed** — heap dominated by something else; Effect undetermined |
> | 9 | flushes(R1)/flushes(R3) > 1.05; in R1, R2 and R5: max S ≤ L/2, S falls by > 25 % between consecutive samples at least 3 times, ΔH(100 %) − ΔH(50 %) < 0.5·L, and the `SkinnyPrimaryKey` count ≤ 3 × L/(c_t + c_s) at every in-stress histogram; peak ΔH(R2)/peak ΔH(R1) ≥ 1.25 and peak ΔH(R5) > peak ΔH(R2); flushes(R1)/flushes(R2) ≥ 2 and flushes(R2)/flushes(R5) ≥ 2 | **Confirmed** (row 1) — Effect *caps* |
> | 10 | anything else | **Not confirmed (no matching row)** — Effect undetermined |
> | Qa | r_cluster > 2 × r_unit | cap binds only loosely; r reported (row 5 above) |
> | Qb | `BlockedOnAllocation` Count > 0 in a run that completed | writers blocked at the cap as designed (row 6 above) |
>
> The other numbers in B3f (flush ratios 4 ± 1.5, R1/R3 in 1.3–2.5, peak ΔH ≤ 2.5·L + 200 MiB, ΔH ratios 2–6, last-third
> max S ≤ 1.2 × first-third max, r_cluster within ±30 % of r_unit) are sub-predictions: each is reported hit or miss and does
> not change the row.

**B3h. Controls.**
- R3/R4 (no SAI, same rows) are the positive control: they show the memtable cap binding on the same workload and give c_t and the baseline ΔH.
- Two or three L values separate cap-following from constant overhead.
- `H0` removes the JVM baseline.
- The SAI-specific class counts attribute heap to SAI without depending on the cap.
- `commitlog_total_space: 8192MiB` and `memtable_flush_period_in_ms` = 0 (table default) rule out other flush causes. Check that every counted flush reason is `MEMTABLE_LIMIT`.
- A single node with RF=1 avoids hints and replica traffic.
- STCS, and compaction concurrency fixed across runs.

**B4. Risks and cleanup.**
- Never build in, or add files to, `/proj/.../cassandra-src`. All builds, the test file, data, commit logs and logs live under `$WORK=/var/tmp/sai-exp` on local `/`.
- Disk: the unit tier uses < 2 GB (test data under `$WORK/cassandra/build/test`). The cluster tier peaks at ≤ 15 GB per run (data + compaction + ≤ 8 GiB commit log); wipe `$WORK/node` between runs. Abort if `df /var/tmp` drops below 10 GB free.
- Histograms force full GCs: at most one per 60 s, and they perturb throughput but not the bound.
- Processes:
  - After each run: `kill $(cat $WORK/node.pid)`, then `pgrep -f CassandraDaemon`, `pgrep -f cassandra-stress`, `pgrep -f sample.sh` and `pgrep -f "org.apache.tools.ant"` must all be empty. Kill any leftovers with `kill`, then `kill -9` after 30 s.
  - Ports 7000/7199/9042 on 127.0.0.1 must be free at the end (`ss -ltnp | grep -E '7000|7199|9042'`).
- Final cleanup: `rm -rf $WORK` after copying the CSVs, samples, histograms and logs to the results location.

## C. Sources read

- /proj/misconfiguration-PG0/git-repos/Misconfiguration/cassandra/if-check-exp/stage3-ai-deep-read/playbook-autonomous.md
- /proj/misconfiguration-PG0/git-repos/Misconfiguration/cassandra/if-check-exp/stage3-ai-deep-read/_TEMPLATE-autonomous.md
- /proj/misconfiguration-PG0/git-repos/Misconfiguration/cassandra/if-check-exp/README.md (§6.1 only)
- src/java/org/apache/cassandra/index/sai/StorageAttachedIndex.java
- src/java/org/apache/cassandra/index/sai/memory/MemtableIndexManager.java
- src/java/org/apache/cassandra/index/sai/memory/MemtableIndex.java
- src/java/org/apache/cassandra/index/sai/memory/TrieMemoryIndex.java
- src/java/org/apache/cassandra/index/sai/memory/VectorMemoryIndex.java (grep)
- src/java/org/apache/cassandra/index/sai/utils/PrimaryKeys.java
- src/java/org/apache/cassandra/index/sai/utils/PrimaryKey.java
- src/java/org/apache/cassandra/index/sai/StorageAttachedIndexGroup.java (grep)
- src/java/org/apache/cassandra/index/sai/metrics/IndexMetrics.java
- src/java/org/apache/cassandra/index/sai/metrics/AbstractMetrics.java
- src/java/org/apache/cassandra/index/sasi/SASIIndex.java (grep)
- src/java/org/apache/cassandra/db/memtable/Memtable.java
- src/java/org/apache/cassandra/db/memtable/AbstractAllocatorMemtable.java
- src/java/org/apache/cassandra/db/memtable/TrieMemtable.java (grep)
- src/java/org/apache/cassandra/db/memtable/SkipListMemtable.java (grep)
- src/java/org/apache/cassandra/db/memtable/AbstractShardedMemtable.java (grep)
- src/java/org/apache/cassandra/db/tries/InMemoryTrie.java
- src/java/org/apache/cassandra/db/tries/InMemoryReadTrie.java (grep)
- src/java/org/apache/cassandra/utils/memory/MemtableAllocator.java
- src/java/org/apache/cassandra/utils/memory/MemtablePool.java
- src/java/org/apache/cassandra/utils/memory/SlabAllocator.java (grep)
- src/java/org/apache/cassandra/utils/ObjectSizes.java
- src/java/org/apache/cassandra/db/ColumnFamilyStore.java
- src/java/org/apache/cassandra/index/SecondaryIndexManager.java
- src/java/org/apache/cassandra/metrics/TableMetrics.java
- src/java/org/apache/cassandra/config/Config.java
- src/java/org/apache/cassandra/config/DatabaseDescriptor.java
- src/java/org/apache/cassandra/config/YamlConfigurationLoader.java
- src/java/org/apache/cassandra/config/StorageAttachedIndexOptions.java (grep)
- src/java/org/apache/cassandra/transport/CBUtil.java
- conf/cassandra.yaml
- conf/cassandra-env.sh
- conf/jvm11-server.options
- test/conf/cassandra.yaml
- test/unit/org/apache/cassandra/index/sai/memory/TrieMemoryIndexTest.java
- test/unit/org/apache/cassandra/index/sai/SAITester.java (grep)
- test/unit/org/apache/cassandra/cql3/CQLTester.java (grep)
- test/unit/org/apache/cassandra/config/YamlConfigurationLoaderTest.java
- tools/stress/src/org/apache/cassandra/stress/StressProfile.java
- tools/cqlstress-example.yaml
- build.xml
- bin/cassandra
- doc/modules/cassandra/pages/developing/cql/indexing/sai/sai-read-write-paths.adoc
- CHANGES.txt (grep)

## D. Stage-4 feedback

**2026-10-22, run 1 (stage 4, `pc07`, clone `~/cassandra-sai` at `cassandra-5.0.9`).** Results:
`stage4-runtime-verification/results/memtable_heap_space-adjustMemtableSize-0--autonomous.md` (not committed). Audit: Ready after
amendments A-U1, A-U2, A-K1–A-K5 (dated above, all before any reading); defect D1 fixed in B3c (cluster tier restarted).

- **Unit tier: Confirmed — caps** (A-U2 row 7 = B2g row 1). `dS − dP = S` = 12,979,488 B exactly at N = 100,000 (129.8 B/row);
  U3 flushes SAI/plain 25/20 at 32 MiB and 8/6 at 96 MiB; peak S 0.13 L and 0.115 L; ratios 3.1 (flushes) and 2.6 (peak S).
  Qualifier Qb: `(D − K)/S` = 3.49, above B2f's 1.2–2.5 band — the trie, keys and key objects hold about 323 B/row that is never
  charged, so the cap is loose.
- **Cluster tier: Not confirmed (no matching row) — Effect undetermined** (A-K5 row 10). Row 9 failed on one condition only:
  "S falls by > 25 % between consecutive 2 s samples at least 3 times" in R1, R2 and R5 (counts 2, 2, 3). With 100–170 k rows/s
  the pool flushed every 0.3 s (64 MiB) or 1.2 s (256 MiB), so each sample sums several live and flushing memtable indexes and S
  oscillates in a band (R1 8.5–13.1 MiB) instead of sawing to zero. Every other condition of row 9 held: flushes 289 / 74 / 18 (SAI)
  vs 230 / 57 / 14 (plain) at 64 / 256 / 1024 MiB (R1/R3 = 1.257, predicted from the measured charges 1.261); max S ≤ 0.23 L;
  peak ΔH 125 / 422 / 1,503 MiB (SAI) vs 56 / 137 / 562 MiB (plain); SkinnyPrimaryKey counts bounded; R1 at the hard cap
  (`Used total` 1.00 on 113 of 289 triggers, 9,339 blocked allocations). Sub-predictions missed: R1/R3 band 1.3–2.5 (1.257),
  r_unit band, r_cluster within ±30 % of r_unit (5.22 vs 3.49).
- **For stage 3 / a next design:** (1) the sawtooth test needs a resolution finer than the flush interval (sample ≤ 0.1 s, or
  trace the index's discard with Byteman, or throttle the load so a flush is rarer than a sample); the stage-4 audit wrote the
  failing condition, not stage 3. (2) The node wrote 100–170 k rows/s, not 20–50 k: 10M rows lasted 1–2 min and gave only 2–3
  class histograms per run; size the load by time or throttle it. (3) B3c's profile needs `CREATE INDEX IF NOT EXISTS` (D1).
  (4) `AllMemtablesOnHeapDataSize` reads only current memtables. (5) Compaction-time SAI segment buffers
  (`segment_write_buffer_size`, default 1 GiB) are outside the pool; this run held them at 16 MiB (A-K2).
- **Overlap:** the pool mechanics (trigger at L·t, block at L) re-observed here are the subjects of
  `memtable_heap_space-needsCleaning-nextClean--autonomous` and `memtable_heap_space-tryAllocate-limit--guided/--autonomous`;
  this file's own finding is the SAI charge entering that pool.
