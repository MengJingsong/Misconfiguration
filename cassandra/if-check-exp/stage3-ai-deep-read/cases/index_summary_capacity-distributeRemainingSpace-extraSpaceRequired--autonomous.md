# index_summary_capacity — verification solution  <!-- file: cases/index_summary_capacity-distributeRemainingSpace-extraSpaceRequired--autonomous.md -->

| Field | Value |
|---|---|
| Entry pointer | `src/java/org/apache/cassandra/io/sstable/indexsummary/IndexSummaryRedistribution.java:341` |
| Pinned source | `cassandra-5.0.9` |
| Session / date | Claude Opus 5.5 (`claude-opus-5-5`), Claude Code 2.1.305, 2026-10-21 |
| Estimate | `positive`: when the resize task runs, the total off-heap size of BIG-format index summaries is brought to at or below `index_summary_capacity`. The cap only holds down to a floor set by each table's `max_index_interval`, and it is best effort: usage can overshoot between runs, and in a few edge cases inside a run. |
| Ground | — |

## A. Constraint trace

**A1. The constraint.**
- Name: `index_summary_capacity` (old name `index_summary_capacity_in_mb`, deprecated).
- Kind: configuration entry, also settable at runtime through JMX.
- Declared at `src/java/org/apache/cassandra/config/Config.java:539-540` (`public volatile DataStorageSpec.LongMebibytesBound index_summary_capacity;`, default `null`).
- Unit: MiB. `LongMebibytesBound` keeps a MiB value. The yaml comment says "Min unit: KiB" (`conf/cassandra.yaml:938`), but the value is converted with `toMebibytes()`.
- Default: empty or `null` means 5% of the heap. `DatabaseDescriptor.java:867-869` sets `indexSummaryCapacityInMiB = max(1, (int)(Runtime.totalMemory()*0.05/1024/1024))`. Note that this uses `totalMemory()` (the committed heap) rather than `maxMemory()`. With `-Xms`=`-Xmx` the two are the same.
- Validation: a negative value is rejected (`DatabaseDescriptor.java:871-873`). `0` is accepted.
- How to set it:
  - yaml `index_summary_capacity: <n>MiB` (`conf/cassandra.yaml:939`). This is read once at startup, so a restart is needed.
  - JMX at runtime: MBean `org.apache.cassandra.db:type=IndexSummaries`, attribute `MemoryPoolCapacityInMB` (`IndexSummaryManagerMBean.java:25-26`, `IndexSummaryManager.java:184-187`). It takes effect at the next redistribution.
- How it gets into the check: the manager constructor copies it into `memoryPoolBytes` (`IndexSummaryManager.java:103,108`). Each run passes it to `new IndexSummaryRedistribution(..., this.memoryPoolBytes)` (`IndexSummaryManager.java:248-250`).
- Companion knob: `index_summary_resize_interval`, default `60m` (`Config.java:543`, `conf/cassandra.yaml:947`). `null` or `-1` disables the periodic run (`IndexSummaryManager.java:135-147`).

**A2. What it caps.**
- Resource: native (off-heap) memory used by index summaries of sstables in a format that has an index summary. That is BIG, the default `selected_format` (`Config.java:373`). BTI sstables are filtered out and cancelled (`IndexSummaryRedistribution.java:85-98`).
- Summary memory is allocated with `Memory.allocate`, then `MemoryUtil.allocate`, then JNA `Native.malloc` (`IndexSummary.java:444-445`, `IndexSummaryBuilder.java:352-353`, `Memory.java:65,80`, `MemoryUtil.java:81-84`). It is plain libc malloc, so the JVM's NMT does not see it.
- Quantity compared: `IndexSummary.getOffHeapSize() = offsetCount*4 + entriesLength` (`IndexSummary.java:259-262`), summed over sstables. The pool budget is `remainingSpace`, which starts at `memoryPoolBytes - nonRedistributingOffHeapSize` (`IndexSummaryRedistribution.java:138,173`).
- At line 341 the operands are:
  - `extraSpaceRequired`: the bytes one sstable would keep if it were not downsampled, i.e. its current size minus its planned downsampled size (`:339`).
  - `remainingSpace`: the unspent pool after every sstable's planned size has been charged.

**A3. Mechanism.**
1. Scheduling. `IndexSummaryManager.setResizeIntervalInMinutes` schedules `redistributeSummaries()` with fixed delay. The first run comes one full interval after startup (`IndexSummaryManager.java:117-148`). The run is skipped if global compaction is paused (`:241-242`). It can also be triggered over JMX (`IndexSummaryManagerMBean.java:41`).
2. Selecting sstables. Every live CANONICAL sstable that is not compacting is marked in an `INDEX_SUMMARY` transaction. Summaries of compacting sstables are summed into `nonRedistributingOffHeapSize`, which is charged against the pool but cannot be shrunk (`IndexSummaryManager.java:208-237`).
3. Ordering. `redistributeSummaries` sorts sstables from coldest to hottest by 15-minute read rate (`IndexSummaryRedistribution.java:118-136`). The budget is `memoryPoolBytes - nonRedistributingOffHeapSize` (`:138`).
4. Per-sstable decision in `adjustSamplingLevels` (`:174-256`):
   - Ideal space is `idealSpace = remainingSpace * readsPerSec/totalReadsPerSec` (`:183`). That gives a target entry count (`:188`) and a new sampling level, clamped to `[effectiveMinSamplingLevel, 128]` (`IndexSummaryBuilder.java:299-314`).
   - `effectiveMinSamplingLevel = max(1, ceil(128*min_index_interval/max_index_interval))` (`IndexSummaryBuilder.java:304`). This is the floor below which the cap cannot push.
   - Each sstable goes to one of five outcomes:
     - force-resample: a `min_index_interval` change (`:215-223`);
     - force-upsample: `max_index_interval` was lowered (`:224-234`);
     - upsample: target at least 1.5x current (`:235-240`);
     - downsample: target below 0.75x current (`:241-246`);
     - keep current (`:247-254`), which charges its current size.
   - `remainingSpace` is reduced by each sstable's planned size.
   - Zero read rates: if every rate is 0 (no reads, or system tables whose `readMeter` is `null`, `SSTableReader.java:1640-1645`), then `readsPerSec/totalReadsPerSec` is `0/0 = NaN`. `Math.round(NaN) = 0`, so the target is 1 entry and every sstable above the floor goes to `toDownsample` at the floor level.
5. Line 341, `distributeRemainingSpace` (`:327-356`). If `remainingSpace > 0` after the loop (`:258`), the downsample candidates are sorted by ascending regain, `currentSize - newSpaceUsed` (`:331`). Walking that list:
   - while `extraSpaceRequired <= remainingSpace` (`:341`), the sstable is kept at its current level and the regain is charged (`:345-346`);
   - at the first entry that does not fit, the loop stops (`:350`), and that entry and every later one are downsampled.

   Kept sstables have their transaction cancelled (`:263-264`). The rest are rewritten with `cloneWithNewSummarySamplingLevel` (`:272-292`): a downsample copies a subset in memory, an upsample rebuilds from `Index.db`. The new summary is saved to `Summary.db` (`BigTableReader.java:600-620`).

   This line is what keeps the leftover top-up within the pool: whatever it lets survive fits in `remainingSpace`, so total ≤ `memoryPoolBytes` holds whenever `remainingSpace` was ≥ 0 before it ran.
6. Outcome when the limit is reached: summaries are downsampled, which means more index reads per lookup. Nothing is refused or thrown.
7. Paths that bypass or overshoot the cap:
   - (a) Floor. If Σ(floor-level sizes) + non-redistributable > pool, every sstable goes to the floor and the total stays above the pool. `remainingSpace ≤ 0`, so line 341 never runs. The floor is per table: `max_index_interval` default 2048 with `min_index_interval` 128 gives floor level 8/128 = 1/16 of the full size.
   - (b) Between runs. New flushes and compaction outputs get full-level summaries (`BigTableWriter.java:255`, `BASE_SAMPLING_LEVEL`). Nothing checks the pool until the next run (default 60 min, first run 60 min after start). With the interval set to `null`, nothing ever checks it.
   - (c) Compacting sstables are charged but cannot be shrunk (`IndexSummaryManager.java:230-235`).
   - (d) The keep band. An sstable whose target lies in [0.75x, 1.5x) of its current size keeps that size (`:247-251`). The hottest sstables can push `remainingSpace` below 0, at most about 25% of one summary, after which later sstables are forced to the floor.
   - (e) Forced resample or upsample after `min_index_interval` or `max_index_interval` changes. These are charged but never refused (`:215-234`), so lowering `max_index_interval` can force usage far above the pool.
   - (f) Transient overlap. The old summary is freed only when the old reader's refs are released, so during a run old and new summaries coexist.
   - (g) BTI-format sstables have no summary and are outside this cap.

**A4. Other consumers.** Other native memory not governed by this cap:
- bloom filters (`OffHeapBitSet`, also `Memory.allocate`);
- compression offsets;
- the chunk cache / `BufferPool` (`file_cache_size`, `networking_cache_size`);
- off-heap memtables (when `memtable_allocation_type` is offheap_*; the default is `heap_buffers`, `conf/cassandra.yaml:825`);
- Netty direct buffers, metaspace, thread stacks, glibc arena slack;
- file-backed mmaps of Data, Index and commit log (RssFile, not anonymous).

**A5. Evidence beyond the source.**
- `conf/cassandra.yaml:931-939`: the comment calls this "a best-effort process. In extreme conditions Cassandra may need to use more than this amount of memory."
- CHANGES.txt: CASSANDRA-5519 "allocate fixed index summary memory pool and resample cold index summaries to use less memory"; CASSANDRA-6379 (min/max_index_interval); CASSANDRA-10512 (persist upsampled summaries); CASSANDRA-15265; CASSANDRA-17036.
- Existing tests: `test/unit/org/apache/cassandra/io/sstable/indexsummary/IndexSummaryManagerTest.java` (`testRedistributeSummaries`, lines 356-505, drives `IndexSummaryRedistribution` with byte pools).
- https://issues.apache.org/jira/browse/CASSANDRA-5519 (not fetched; cited from CHANGES.txt).

## B. Verification solution

**B1. Claim under test.** After a redistribution run, the total `getOffHeapSize()` of all BIG index summaries, and the node's corresponding native memory, is at most `index_summary_capacity`. This holds whenever the capacity is at or above the floor F, the sum of the summaries at `effectiveMinSamplingLevel`. Below F the total settles at F. The claim is wrong if:
- with capacity ≥ F, the total after a run exceeds the capacity (beyond the keep-band slack in B2f), or
- the total does not fall as the capacity falls.

### B2. Unit tier

**B2a. Environment and build.**
- Use the runner's own clone `~/cassandra-run1` (tag cassandra-5.0.9, `ant build-test` already done), with JDK 11 and Ant. Never touch the shared `/proj/.../cassandra-src`.
- Add one file, `~/cassandra-run1/test/unit/org/apache/cassandra/io/sstable/indexsummary/IndexSummaryCapacityProbeTest.java` (contents in B2e). It uses the standard unit-test harness (`test/conf/cassandra.yaml`, BIG format by default) and default `testsome` JVM options.

**B2b. Knobs.**
- The pool bytes `P` passed to `new IndexSummaryRedistribution(txns, 0, P)`. This is exactly the value `IndexSummaryManager` derives from `index_summary_capacity` (MiB × 2^20). Bytes are used so that tiny tables can reach the boundary exactly.
- Read rates per sstable, via `overrideReadMeter`:
  - all 0 (scenario A): forces the NaN path, so every candidate is decided by line 341;
  - 10, 20, …, 80 (scenario B): the proportional path.
- Table `max_index_interval`: 256 normally, 8 for the floor control.

**B2c. Workload.** One table, `min_index_interval=8`, `max_index_interval=256`, so the floor level is ceil(128·8/256) = 4/128. It has 8 sstables (autocompaction off), each with 2048 distinct 8-character keys.
- Each sstable's full summary has 2048/8 = 256 entries of 8 B key + 8 B position + 4 B offset = 20 B, so s = 5120 B. Total S_full = 40960 B.
- At floor level each sstable has m' = ceil(20 × ceil(4·256/128)) = 160 B, so F = 1280 B.
- Pools from 0 to 2·S_full cross both F and S_full, so the limit is reached and passed in both directions. The test re-measures s, m' and F rather than trusting this arithmetic.

**B2d. Observables and instruments.**
- `T`: Σ `getIndexSummary().getOffHeapSize()` over live sstables after each run. This is the check's own operand.
- Per-sstable `getSamplingLevel()`. Under scenario A, `kept` is the number of sstables still at level 128, which is the count of line-341 successes.
- Printed to stdout with prefix `PROBE`. Ant writes stdout into `~/cassandra-run1/build/test/output/TEST-org.apache.cassandra.io.sstable.indexsummary.IndexSummaryCapacityProbeTest.xml`.
- Not observable here: real RSS. That is the cluster tier's job.

**B2e. Procedure.**
1. Create the test file:
```java
package org.apache.cassandra.io.sstable.indexsummary;

import java.io.IOException;
import java.nio.ByteBuffer;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;

import com.google.common.collect.ImmutableMap;
import org.junit.Assert;
import org.junit.Assume;
import org.junit.BeforeClass;
import org.junit.Test;

import org.apache.cassandra.SchemaLoader;
import org.apache.cassandra.ServerTestUtils;
import org.apache.cassandra.config.DatabaseDescriptor;
import org.apache.cassandra.db.ColumnFamilyStore;
import org.apache.cassandra.db.Keyspace;
import org.apache.cassandra.db.RowUpdateBuilder;
import org.apache.cassandra.db.compaction.OperationType;
import org.apache.cassandra.db.lifecycle.LifecycleTransaction;
import org.apache.cassandra.io.sstable.format.SSTableReader;
import org.apache.cassandra.metrics.RestorableMeter;
import org.apache.cassandra.schema.CachingParams;
import org.apache.cassandra.schema.KeyspaceParams;
import org.apache.cassandra.schema.SchemaTestUtil;

import static org.apache.cassandra.io.sstable.Downsampling.BASE_SAMPLING_LEVEL;

public class IndexSummaryCapacityProbeTest<R extends SSTableReader & IndexSummarySupport<R>>
{
    static final String KS = "ISCProbe", CF = "Probe";
    static final int NUM_SSTABLES = 8, NUM_PARTITIONS = 2048;

    @BeforeClass
    public static void defineSchema()
    {
        DatabaseDescriptor.daemonInitialization();
        Assume.assumeTrue(IndexSummarySupport.isSupportedBy(DatabaseDescriptor.getSelectedSSTableFormat()));
        SchemaLoader.prepareServer();
        SchemaLoader.createKeyspace(KS, KeyspaceParams.simple(1),
                                    SchemaLoader.standardCFMD(KS, CF).minIndexInterval(8).maxIndexInterval(256)
                                                .caching(CachingParams.CACHE_NOTHING));
        IndexSummaryManager.instance.setResizeIntervalInMinutes(-1); // no background run
    }

    ColumnFamilyStore cfs() { return Keyspace.open(KS).getColumnFamilyStore(CF); }

    List<R> live()
    {
        List<R> l = new ArrayList<>(ServerTestUtils.<R>getLiveIndexSummarySupportingReaders(cfs()));
        l.sort(Comparator.comparing(SSTableReader::getFilename));
        return l;
    }

    static long total(List<? extends IndexSummarySupport<?>> l)
    {
        long t = 0; for (IndexSummarySupport<?> r : l) t += r.getIndexSummary().getOffHeapSize(); return t;
    }

    String levels(List<R> l)
    {
        StringBuilder b = new StringBuilder(); for (R r : l) b.append(r.getIndexSummary().getSamplingLevel()).append(','); return b.toString();
    }

    void rates(double... r) { List<R> l = live(); for (int i = 0; i < l.size(); i++) l.get(i).overrideReadMeter(new RestorableMeter(r[i], r[i])); }

    void redistribute(long pool) throws IOException
    {
        ColumnFamilyStore cfs = cfs();
        try (LifecycleTransaction txn = cfs.getTracker().tryModify(live(), OperationType.UNKNOWN))
        {
            IndexSummaryManager.redistributeSummaries(new IndexSummaryRedistribution(ImmutableMap.of(cfs.metadata.id, txn), 0L, pool));
        }
    }

    void resetToFull(long sFull) throws IOException
    {
        double[] r = new double[NUM_SSTABLES]; java.util.Arrays.fill(r, 100.0); rates(r);
        redistribute(4 * sFull);
        for (R x : live()) Assert.assertEquals(BASE_SAMPLING_LEVEL, x.getIndexSummary().getSamplingLevel());
    }

    @Test
    public void probe() throws IOException
    {
        ColumnFamilyStore cfs = cfs();
        cfs.truncateBlocking(); cfs.disableAutoCompaction();
        ByteBuffer v = ByteBuffer.wrap(new byte[100]);
        for (int s = 0; s < NUM_SSTABLES; s++)
        {
            for (int p = 0; p < NUM_PARTITIONS; p++)
                new RowUpdateBuilder(cfs.metadata(), 0, String.format("%08d", s * NUM_PARTITIONS + p))
                    .clustering("column").add("val", v).build().applyUnsafe();
            cfs.forceBlockingFlush(ColumnFamilyStore.FlushReason.UNIT_TESTS);
        }
        List<R> l = live();
        Assert.assertEquals(NUM_SSTABLES, l.size());
        long sFull = total(l);
        long s = l.get(0).getIndexSummary().getOffHeapSize();
        IndexSummary is = l.get(0).getIndexSummary();
        int effMin = (int) Math.ceil(BASE_SAMPLING_LEVEL * 8 / 256.0);
        long mPred = (long) Math.ceil((s / (double) is.size()) * Math.ceil(effMin * is.getMaxNumberOfEntries() / (double) BASE_SAMPLING_LEVEL));
        long F = NUM_SSTABLES * mPred, d = s - mPred;
        System.out.printf("PROBE setup sFull=%d s=%d mPred=%d F=%d d=%d%n", sFull, s, mPred, F, d);

        // Scenario A: zero read rates -> every keep decision is made at IndexSummaryRedistribution.java:341
        long[] pools = { 0, F - 1, F, F + d - 1, F + d, F + 3 * d - 1, F + 3 * d, F + 7 * d, F + 8 * d - 1, F + 8 * d, 2 * sFull };
        for (long P : pools)
        {
            resetToFull(sFull);
            rates(new double[NUM_SSTABLES]);
            redistribute(P);
            l = live();
            long T = total(l);
            int kept = 0; for (R x : l) if (x.getIndexSummary().getSamplingLevel() == BASE_SAMPLING_LEVEL) kept++;
            long kPred = P <= F ? 0 : Math.min(NUM_SSTABLES, (P - F) / d);
            System.out.printf("PROBE A P=%d T=%d kept=%d kPred=%d Tpred=%d T<=P=%b levels=%s%n",
                              P, T, kept, kPred, F + kPred * d, T <= P, levels(l));
        }

        // Scenario B: proportional read rates
        for (long P : new long[]{ sFull / 2, sFull / 4, sFull / 8, F })
        {
            resetToFull(sFull);
            rates(10, 20, 30, 40, 50, 60, 70, 80);
            redistribute(P);
            l = live();
            long T = total(l);
            System.out.printf("PROBE B P=%d T=%d slackBound=%d T<=P=%b levels=%s%n", P, T, P + s / 4 + F, T <= P, levels(l));
        }

        // Control: floor equals full (max_index_interval == min_index_interval) -> cap cannot bind
        SchemaTestUtil.announceTableUpdate(cfs.metadata().unbuild().maxIndexInterval(8).build());
        resetToFull(sFull);
        rates(new double[NUM_SSTABLES]);
        redistribute(sFull / 4);
        l = live();
        System.out.printf("PROBE C floor P=%d T=%d levels=%s%n", sFull / 4, total(l), levels(l));
        SchemaTestUtil.announceTableUpdate(cfs.metadata().unbuild().maxIndexInterval(256).build());
    }
}
```
2. Run it:
```
cd ~/cassandra-run1 && ant testsome -Dtest.name=org.apache.cassandra.io.sstable.indexsummary.IndexSummaryCapacityProbeTest
```
3. Extract the results:
```
grep -h 'PROBE' build/test/output/TEST-org.apache.cassandra.io.sstable.indexsummary.IndexSummaryCapacityProbeTest*.xml
```
If nothing matches, use `grep -rh PROBE build/test/`.

> **Amendment 2026-10-21 (stage-4 audit, R1; instrument only, B2f/B2g unchanged).** The test JVM routes `System.out` through a
> logger that writes each `printf` fragment as its own line (lesson H1 of the `concurrent_writes` stage-4 run), so step 3's `grep`
> can return fragments. The stage-4 harness copy of this test
> (`stage4-runtime-verification/harness/index_summary_capacity-distributeRemainingSpace-extraSpaceRequired--autonomous/IndexSummaryCapacityProbeTest.java`)
> is the test above with two instrument-only changes: each `PROBE` line is formatted once with `String.format` and also appended,
> whole, to the file named by `-Dprobe.out`; and `NUM_PARTITIONS` reads `-Dprobe.partitions` (default 2048, used for run 1; a
> smaller value only for the shakedown). Every other line, value and call is as above. Readings are taken from the `probe.out`
> file.

4. Repeat step 2 once to confirm the readings are deterministic.
5. Clean up with `rm test/unit/org/apache/cassandra/io/sstable/indexsummary/IndexSummaryCapacityProbeTest.java`, then `pgrep -f IndexSummaryCapacityProbeTest` to confirm no forked JVM is left.

If `testsome` reports a compile error from a signature mismatch, fix only that call. Every API used was checked in the tree: `ColumnFamilyStore.java:1114,2740,2996`, `ServerTestUtils.java:222`, `RestorableMeter.java:65`, `IndexSummaryManager.java:286`.

**B2f. Predictions.** With the arithmetic from B2c: s=5120, m'=160, F=1280, d=4960, S_full=40960. The setup line confirms these.

Scenario A (0 read rates). `kept` = kPred = 0 if P ≤ F, else min(8, ⌊(P−F)/d⌋). T = F + kept·d exactly.

| P | kept | T | T ≤ P |
|---|---|---|---|
| 0 | 0 | 1280 | false (floor) |
| F−1 = 1279 | 0 | 1280 | false (floor) |
| F = 1280 | 0 | 1280 | true |
| F+d−1 = 6239 | 0 | 1280 | true |
| F+d = 6240 | 1 | 6240 | true (equality at line 341, `<=`) |
| F+3d−1 = 16159 | 2 | 11200 | true |
| F+3d = 16160 | 3 | 16160 | true |
| F+7d = 36000 | 7 | 36000 | true |
| F+8d−1 = 40959 | 7 | 36000 | true |
| F+8d = 40960 | 8 | 40960 | true |
| 2·S_full = 81920 | 8 | 40960 | true |

Scenario B (proportional read rates):
- F ≤ T ≤ P + s/4 + F for every P.
- T ≤ P is expected in most rows.
- Sampling levels are expected to be non-decreasing with read rate. This is expected only, not falsifying.
- T strictly decreases from P = S_full/2 to S_full/8.

Control C: T = S_full = 40960 > P = 10240, and all levels are 128.

**B2g. Readings.**

| Observation | Meaning |
|---|---|
| Scenario A rows match `kept`=kPred and T=F+kPred·d, with T ≤ P for every P ≥ F | Line 341 enforces the pool exactly; claim holds at the unit level |
| T > P for some P ≥ F in A, or T > P + s/4 + F in B | **Claim wrong**: the redistribution does not respect the pool |
| T unchanged as P goes from 2·S_full down to F | **Claim wrong**: the knob does not drive usage |
| T = F > P for P < F | Expected floor, consistent with the best-effort claim |
| `kept` off by one exactly at P = F + k·d | Rounding in `newSpaceUsed` vs the actual downsampled size; check `mPred` against the measured per-sstable floor size; not a refutation if T ≤ P still holds |
| Positive control (2·S_full row) shows T < S_full | The workload is shrunk by something other than pool pressure; the result is invalid |
| Control C shows T < S_full | The floor is not where the trace says; revisit A3 |

> **Amendment 2026-10-21 (stage-4 audit, R2; adds rows and the verdict mapping, no prediction changed).** Two outcomes had no row:
>
> | Observation | Meaning |
> |---|---|
> | The repeat run (B2e step 4) differs from the first in any `T`, `kept` or level string | Not deterministic: **Not confirmed** |
> | Scenario B stays within F ≤ T ≤ P + s/4 + F, but T is not strictly decreasing from S_full/2 to S_full/8 | A missed sub-prediction, recorded; it does not change the verdict |
>
> **Verdict for this tier.** **Confirmed** (the claim B1 held) needs all of: row 1 for every scenario-A row with P ≥ F (or row 5, with
> T ≤ P still true); row 4 for P < F; scenario B within its bound; the positive control (T = S_full at P = 2·S_full); control C
> (T = S_full, all levels 128); and an identical repeat. **Refuted**: row 2 or row 3. **Invalid**: row 6 or row 7 (a control failed).
> **Not confirmed**: the repeat differs, or any reading that no other row covers. Effect on the constraint: Confirmed → `caps`
> (at the redistribution, down to the floor F); Refuted → `does not cap`.

**B2h. Controls.**
- Positive control: P ≥ S_full leaves T = S_full, which proves the summaries are big enough to exceed every smaller pool.
- Floor control (C): with the floor at full size, the same P leaves usage unchanged. So any shrinking seen in A and B comes from the cap, not from another mechanism.
- Reset to full before each trial, so trials are independent.
- `setResizeIntervalInMinutes(-1)`, so no background run interferes.
- Repeat run for determinism.

### B3. Cluster tier

**B3a. Environment and build.**
- One node from `~/cassandra-run1` (already built; `tools/bin/cassandra-stress` is built by `build-test`), JDK 11.
- Pick a local, non-NFS directory with at least 20 GiB free:
```
export RUN=/tmp/isc-$USER          # or another local mount
mkdir -p $RUN/{data,commitlog,hints,saved_caches,cdc_raw,logs}
stat -f -c %T $RUN                 # must not be nfs
df -h $RUN
cp -r ~/cassandra-run1/conf $RUN/conf
```
- Edit the config:
```
Y=$RUN/conf/cassandra.yaml
sed -i -e "s/^cluster_name:.*/cluster_name: 'isc-probe'/" \
       -e 's/^storage_port:.*/storage_port: 17000/' -e 's/^ssl_storage_port:.*/ssl_storage_port: 17001/' \
       -e 's/^native_transport_port:.*/native_transport_port: 19042/' \
       -e 's/^listen_address:.*/listen_address: 127.0.0.1/' -e 's/^rpc_address:.*/rpc_address: 127.0.0.1/' \
       -e 's/"127.0.0.1:7000"/"127.0.0.1:17000"/' \
       -e 's/^index_summary_capacity:.*/index_summary_capacity: 4096MiB/' \
       -e 's/^index_summary_resize_interval:.*/index_summary_resize_interval: 1m/' \
       -e 's/^key_cache_size:.*/key_cache_size: 0MiB/' $Y
cat >> $Y <<EOF
data_file_directories:
    - $RUN/data
commitlog_directory: $RUN/commitlog
hints_directory: $RUN/hints
saved_caches_directory: $RUN/saved_caches
cdc_raw_directory: $RUN/cdc_raw
memtable_heap_space: 256MiB
EOF
sed -i 's/^JMX_PORT="7199"/JMX_PORT="17199"/' $RUN/conf/cassandra-env.sh
```
- Environment for every start:
```
export CASSANDRA_CONF=$RUN/conf CASSANDRA_LOG_DIR=$RUN/logs MAX_HEAP_SIZE=8G HEAP_NEWSIZE=2G MALLOC_MMAP_THRESHOLD_=131072
```
`-XX:+AlwaysPreTouch` is already in `conf/jvm-server.options:128`, so the 8 GiB heap is resident from start and constant. A fixed mmap threshold makes every summary larger than 128 KiB its own mmap, which is returned to the OS on free.
- Ports 17000, 17001, 19042 and 17199 must be free (`ss -ltn`).

**B3b. Knobs.** `index_summary_capacity`, set in the yaml with a restart, in descending order: 4096MiB, 400MiB, 100MiB, 0MiB.
- Descending order matters: with zero read rates nothing upsamples (`:235` requires a higher target), so an ascending sequence would not re-grow.
- 4096 is above S_full (positive control); 400 and 100 lie between F and S_full; 0 is below F (floor).
- `index_summary_resize_interval: 1m` makes the real scheduled path run one minute after start and then every minute.

> **Amendment 2026-10-21 (stage-4 audit, R3; adds the default value).** The values did not include the default. The sequence is
> **4096MiB, default, 400MiB, 100MiB, 0MiB**. "Default" is `index_summary_capacity:` left empty, which is 5% of the committed heap
> (`DatabaseDescriptor.java:867-869`): with `-Xms`=`-Xmx`=8G that is 409 MiB, and the node confirms it with "Initializing index
> summary manager with a memory pool size of 409 MB". It lies between F and S_full, so the order stays descending (409 > 400).
> B3f gains the row: default | T ≤ 409 and > 409 − r_max | ≈ T | R4096 − (809 − T) ± σ.

**B3c. Workload.** cassandra-stress user profile `$RUN/isc.yaml`:
```yaml
keyspace: isc
keyspace_definition: |
  CREATE KEYSPACE isc WITH replication = {'class': 'SimpleStrategy', 'replication_factor': 1};
table: t
table_definition: |
  CREATE TABLE t (k blob PRIMARY KEY, v blob)
    WITH min_index_interval = 1 AND max_index_interval = 128
    AND bloom_filter_fp_chance = 1.0
    AND caching = {'keys': 'NONE', 'rows_per_partition': 'NONE'}
    AND compression = {'enabled': 'false'}
    AND compaction = {'class': 'SizeTieredCompactionStrategy', 'enabled': 'false'};
columnspec:
  - name: k
    size: fixed(200)
    population: seq(1..4000000)
  - name: v
    size: fixed(16)
insert:
  partitions: fixed(1)
  batchtype: UNLOGGED
queries:
  read1:
    cql: SELECT v FROM t WHERE k = ?
    fields: samerow
```
Sizing:
- N = 4,000,000 partitions. With `min_index_interval=1` every key is in the summary at 200+8+4 = 212 B, so S_full ≈ 848,000,000 B ≈ 809 MiB.
- Floor level = ceil(128·1/128) = 1/128, so F ≈ 6.3 MiB, plus a few KiB for system tables.
- Disk: Data ≈ 1 GB, Index ≈ 0.9 GB, commit log ≤ 8 GiB cap. Under 12 GiB in total.
- Write time is a few minutes at 64 threads. No reads are issued, so all read rates are 0 and line 341 alone decides what is kept.

> **Runbook fix D1, 2026-10-21 (stage 4, found by the cluster instrument check before run 1; B1 and B3f/B3g unchanged).** The
> `population: seq(1..4000000)` line on `k` does not give 4,000,000 distinct keys. A column's value is drawn from its population
> distribution after `setSeed(seed ^ salt)` (`tools/stress/.../generate/values/Generator.java:51-55`), and `DistributionSequence`
> returns `start + (next % totalCount)` from that scrambled seed (`DistributionSequence.java:41-46, 66-69`), so distinct partition
> seeds collide modulo N. The shakedown wrote 300,000 partitions and got 267,461 summary entries (89 %), which at 4 M would put S_full
> near 721 MiB instead of 809. **Fix:** the `population:` line on `k` is removed. The key identity then defaults to `uniform(1..100B)`
> (`Generator.java:59-62`), and the operation seeds `1..N` (stress's default `-pop seq=1..N`) give N distinct 200-byte keys (about 80
> expected collisions in 4 M draws from 10^11). Step 6's second load uses the same profile with `-pop seq=4000001..5000000` on the
> command line instead of `isc2.yaml`.

Why these settings:
- Bloom filters off (fp 1.0) and compression off remove two other native consumers.
- `memtable_heap_space: 256MiB` gives tens of sstables, so the cap has fine granularity.

**B3d. Observables and instruments.**
1. Operand total T:
   - the system.log line "Completed resizing of index summaries; current approximate memory used: X MiB", including the line before it ("index summaries: downsample: …");
   - `nodetool -p 17199 tablestats isc.t | grep 'Index summary off heap memory used'` (bytes).
   - Optional: `nodetool -p 17199 sjk mx -b org.apache.cassandra.db:type=IndexSummaries -mg -f MemoryPoolSizeInMB`.
2. Actual resource: `RssAnon` from `/proc/$PID/status`, sampled 5 times at 10 s intervals after the resize; take the median. Summaries are anonymous malloc/mmap memory. The heap is pre-touched and fixed, and file mmaps count as RssFile.
3. Disk proxy for the persisted level: `du -cb $RUN/data/isc/t-*/*-Summary.db | tail -1`.
4. Per-sstable full summary sizes at the 4096 state (`ls -l …Summary.db`), giving r_max = the largest single Summary.db.

What cannot be observed directly: per-allocation native memory. NMT does not see JNA malloc, so ΔRssAnon between runs is the actual-resource reading. Noise is measured by repeating one run (B3h).

> **Amendment 2026-10-21 (stage-4 audit, R4; adds instruments, no prediction changed).**
> 5. **RssAnon every 2 s** for the whole of each node lifetime (`/proc/$PID/status`). Besides item 2's five post-resize samples
>    (the filed observable), this gives the **within-lifetime fall** ΔR_w = median RssAnon over the 20 s before the lifetime's first
>    "Redistributing index summaries" line − the median of item 2's five samples. Its expected value is T_before − T_after, the
>    "current spaced used" of the "Beginning redistribution" line minus T. Supplementary: it is read against B3g's RSS rows as a second
>    reading of the same quantity (R5).
> 6. **Direct evidence of line 341.** The node's `logback.xml` gets one extra appender: logger
>    `org.apache.cassandra.io.sstable.indexsummary.IndexSummaryRedistribution` at TRACE into its own file `logs/isr-trace.log`
>    (additivity on, so `system.log` keeps its INFO lines; `debug.log`, which has no threshold filter, also receives the TRACE lines). Per sstable it records "Using leftover space to keep …" (line 341
>    true, `:343`) and "Re-sampling index summary for … from a/128 to b/128" (downsampled, `:278`). Under zero read rates every `isc.t`
>    sstable is in `toDownsample`, so the keep lines are line 341's successes and the re-sample lines its failures and every later entry.
> 7. Each lifetime's `system.log` is read from the byte offset taken when that lifetime starts, since the log accumulates.

**B3e. Procedure.**
1. Start the node (env from B3a), then wait for `nc -z 127.0.0.1 19042`:
```
~/cassandra-run1/bin/cassandra -p $RUN/cassandra.pid > $RUN/logs/stdout.txt 2>&1
```
2. Load the data:
```
~/cassandra-run1/tools/bin/cassandra-stress user profile=$RUN/isc.yaml "ops(insert=1)" n=4000000 no-warmup cl=ONE -rate threads=64 -node 127.0.0.1 -port native=19042 jmx=17199 -mode native cql3
```
Then `nodetool -p 17199 flush isc t`. Record the sstable count with `ls $RUN/data/isc/t-*/*-Data.db | wc -l`.
3. For each capacity X in [4096, 400, 100, 0] (MiB):
   - a. Stop the node: `nodetool -p 17199 drain; kill $(cat $RUN/cassandra.pid)`, then wait until `pgrep -f "$RUN/conf"` is empty.
   - b. Set the capacity: `sed -i "s/^index_summary_capacity:.*/index_summary_capacity: ${X}MiB/" $RUN/conf/cassandra.yaml`.
   - c. Start the node as in step 1. Wait for "Initializing index summary manager with a memory pool size of X MB" in `$RUN/logs/system.log`.
   - d. Wait for the first "Completed resizing of index summaries" after this start (about 60–90 s), then 30 s more.
   - e. Record T (log line and tablestats), RssAnon (5 samples), the Summary.db total, and the per-sstable levels via `nodetool -p 17199 sjk mx -b org.apache.cassandra.db:type=IndexSummaries -mg -f IndexIntervals` (optional).
4. Noise check: repeat step 3 for X = 0 a second time. That gives the same state, so the RssAnon difference is the noise σ.
5. Floor/override control, at X = 0, on the running node:
   - run `cqlsh 127.0.0.1 19042 -e "ALTER TABLE isc.t WITH max_index_interval = 1"` (`~/cassandra-run1/bin/cqlsh`);
   > **Runbook fix D2, 2026-10-21 (stage 4, found by the cluster instrument check before run 1; B3f/B3g unchanged).** The node
   > refuses this ALTER: "ConfigurationException: max_index_interval must be greater than or equal to min_index_interval (128) (got
   > 1)". An ALTER that names only `max_index_interval` is validated against the default `min_index_interval` (128), not the table's
   > 1. **Fix:** `ALTER TABLE isc.t WITH min_index_interval = 1 AND max_index_interval = 1` (min stays 1, so no forced resample);
   > step 6 restores with `min_index_interval = 1 AND max_index_interval = 128`.
   - wait for the next "Completed resizing" (≤ 2 min) plus 30 s;
   - record T and RssAnon.
6. ~~Optional,~~ **Required (amendment 2026-10-21, R6: it tests A3 7b, part of the estimate; about 5 minutes)**, for the between-runs bypass (A3 7b):
   - restore `max_index_interval = 128`;
   - set X = 100 and `index_summary_resize_interval: null`, then restart;
   - trigger one run with `nodetool -p 17199 sjk mx -b org.apache.cassandra.db:type=IndexSummaries -mc -op redistributeSummaries`;
   - write 1,000,000 more partitions (`population: seq(4000001..5000000)`) and flush;
   - record T. It should exceed 100 MiB with no run to bring it back.

   > **Amendment 2026-10-21 (R6, details).** After the manual run, record its "Completed resizing" T (T_trig, expected ≤ 100). Load
   > the extra partitions with a second profile `isc2.yaml` (B3c's profile with `population: seq(4000001..5000000)`, same
   > `cassandra-stress` command with `n=1000000`), then `nodetool flush isc t`, then wait 120 s. Record T_after as
   > `MemoryPoolSizeInMB` over JMX and `tablestats`; confirm that no "Completed resizing" line appeared after the manual run.
   > Expected: T_after ≈ T_trig + 1,000,000 × 212 B ≈ T_trig + 202 MiB, above 100 MiB. If `sjk mx -mc` cannot invoke the operation,
   > any JMX client may invoke `redistributeSummaries` on the same MBean.
7. Clean up as in B4.

> **Amendment 2026-10-21 (stage-4 audit, R7; environment, no design change).** On the stage-4 node (`pc12`): the clone is a fresh
> `~/cassandra-isc` (same tag, `ant build-test`) instead of `~/cassandra-run1`; `RUN=/tmp/isc-jason92` (local `/dev/sda3`); the shell
> that starts the node runs `ulimit -n 100000` first (the node's soft limit is 1024). A node is detected by a `java` process whose
> arguments name `CassandraDaemon` and `$RUN/conf`, not by `pgrep -f`. Step 3 runs for X in 4096, default, 400, 100, 0 (R3).

**B3f. Predictions.** Let S_full ≈ 809 MiB (±2%), F ≈ 6.3 MiB, and r_max = the largest single Summary.db at the 4096 state.

| X (MiB) | T after run | Summary.db total | RssAnon |
|---|---|---|---|
| 4096 | ≈ S_full (≈ 809 MiB) | ≈ S_full | R4096 (baseline) |
| 400 | ≤ 400 and > 400 − r_max | ≈ T | R4096 − (809 − T) ± σ |
| 100 | ≤ 100 and > 100 − r_max | ≈ T | R4096 − (809 − T) ± σ |
| 0 | ≈ F (≈ 6–7 MiB), above the cap | ≈ T | R4096 − ≈ 800 MiB ± σ |
| 0 + `max_index_interval=1` | ≈ S_full again, far above the cap | ≈ T | back to about R4096 |

The ΔRssAnon between 4096 and 0 should be at least 700 MiB.

**B3g. Readings.**

| Observation | Meaning |
|---|---|
| T ≤ X for X ∈ {400, 100}, T ≈ S_full at 4096, and RssAnon falls by ≈ (809 − T) | Claim confirmed: the cap governs real native usage after a run |
| T > X (beyond rounding of a few KiB) for X ≥ F after a completed run with no concurrent compaction | **Claim wrong** |
| T follows X but RssAnon does not fall (Δ < 50% of ΔT, beyond σ) | The operand is capped but freed memory is not returned (allocator retention or leaked refs): the cap does not govern RSS; report as a partial refutation |
| T at 4096 well below 809 MiB | Positive control failed: the workload did not build the expected summaries (check key size, min_index_interval); the run is invalid |
| No "Completed resizing" line | The run never happened (compactions paused, interval not applied); not a result |
| T ≈ F > 0 at X = 0 | Expected floor overshoot; best-effort nature confirmed |
| T ≈ S_full after `max_index_interval=1` at X = 0 | Table params override the cap (force upsample) |
| T > 100 MiB in step 6 | Between-runs bypass confirmed |

> **Amendment 2026-10-21 (stage-4 audit, R5; defines the terms, adds the missing rows and the verdict mapping; no prediction
> changed).**
>
> *Definitions.* T is the "current approximate memory used" of the lifetime's first "Completed resizing" line (all tables).
> "T ≤ X" means T ≤ X + 0.0625 MiB (64 KiB, the "few KiB" of rounding and system tables); `tablestats` for `isc.t` must not exceed T.
> "T at 4096 well below 809 MiB" (row 4) means T4096 < 0.9 × 808.7 = 728 MiB. "T ≈ F at X = 0" means 3 MiB ≤ T0 ≤ 12 MiB.
> "RssAnon falls by ≈ (809 − T)" (row 1) means the across-lifetime fall R4096 − R_X ≥ 0.5 × (T4096 − T_X) for every X in {default,
> 400, 100, 0}, where R is the median of B3d item 2's five samples; row 3 is its complement (fall < 0.5 × ΔT, by more than 3σ).
> σ = |R0b − R0a|, the two X = 0 lifetimes (B3e step 4). B3f's "± σ" is a sub-prediction, |fall − ΔT| ≤ max(3σ, 0.15 × ΔT), recorded
> as hit or miss; it does not choose the row.
>
> | Observation | Meaning |
> |---|---|
> | T(100) > T4096 − 0.1 × T4096 (T does not fall as X falls; B1's second refuted-if) | **Claim wrong** |
> | σ > 0.25 × (T4096 − T0) | RSS too noisy to read: **Not confirmed** (RSS part) |
> | The within-lifetime fall ΔR_w (B3d item 5) and the across-lifetime fall put the same X on different sides of 0.5 × ΔT | The two RSS readings disagree: **Not confirmed** (RSS part) |
> | After `max_index_interval = 1` (step 5), T ≤ 2 × T0 | The floor/override control did not move: **Not confirmed** (control) |
> | Step 6: T_after ≤ 100 MiB with no run in between | The between-runs overshoot (A3 7b) was not seen: a missed sub-prediction of the estimate, recorded |
>
> **Verdict for this tier.** **Confirmed** (the claim B1 held): row 1 for X = default, 400 and 100; T ≈ F at X = 0 (row 6); a
> "Completed resizing" line in every lifetime; positive control valid; σ informative; the two RSS readings agree; the floor control
> moved. **Refuted**: row 2, or the "T does not fall" row. **Refuted (partial)**: row 3 (operand capped, RSS not). **Invalid**: row 4
> or row 5. **Not confirmed**: any other "Not confirmed" row, or a reading no row covers. **Effect on the constraint** (fixed before
> the run): Confirmed with step 6's overshoot seen → `caps only on some paths (bypass)` (it caps at each resize run, down to the
> floor; new sstables bypass it until the next run, and table parameters force it above); Confirmed without the overshoot → `caps`;
> Refuted → `does not cap`; Refuted (partial) → `caps only on some paths (bypass)`.

> **Runbook fix D3, 2026-10-21 (stage 4; a definition error in R5's RSS-agreement row, independent of the readings; B3f and every
> other row unchanged; the cluster tier restarts).** The row compared ΔR_w with "0.5 × ΔT" without saying which ΔT, and a lifetime
> whose run changes nothing (foreseeable for X = 400 right after the default 409) has T_before − T_after = 0, where noise alone decides
> the side. The row now reads: ΔR_w is compared with 0.5 × (T_before − T_after) of its own lifetime, and the across-lifetime fall with
> 0.5 × (T4096 − T_X); the readings disagree when they put that X on different sides of their own line. The comparison is made only
> in lifetimes whose run changed T by at least 16 MiB; in the others ΔR_w is recorded and must lie within 3σ of 0, or the row applies.

**B3h. Controls.**
- Positive control: X = 4096 shows that the same workload holds ≈ 809 MiB of summaries when the cap does not bind.
- Noise: the repeated X = 0 run gives σ.
- Removing other consumers: bloom filters and compression are off; heap is fixed and pre-touched; `file_cache_enabled` defaults to false; there are no reads.
- No compaction runs (it is disabled), so `nonRedistributingOffHeapSize` = 0.
- The Summary.db total cross-checks T independently of JMX and logs.
- The floor control (step 5) shows usage can move above the cap when table params force it, which separates "the cap shrinks it" from "something else does".

**B4. Risks and cleanup.**
- Unit tier: only the one added test file and `build/test` output in `~/cassandra-run1`. Delete the file afterwards and check for leftover JVMs with `pgrep -f IndexSummaryCapacityProbeTest`.
- Cluster tier, disk: everything lives under `$RUN` on local disk; peak is about 12 GiB. Watch it with `df -h $RUN`.
- Cluster tier, memory: the node needs about 8 GiB heap plus about 1.5 GiB native, well within 251 GiB.
- Stop the node: `nodetool -p 17199 stopdaemon || kill $(cat $RUN/cassandra.pid)`. Confirm with `pgrep -f "$RUN/conf"` and `pgrep -f cassandra-stress`; both must be empty, otherwise `kill -9` those PIDs.
- Remove all data: `rm -rf $RUN`.
- Never write in `/proj/...`.
- Use non-default ports to avoid clashing with other runs on a shared node.

## C. Sources read

src/java/org/apache/cassandra/io/sstable/indexsummary/IndexSummaryRedistribution.java
src/java/org/apache/cassandra/io/sstable/indexsummary/IndexSummaryManager.java
src/java/org/apache/cassandra/io/sstable/indexsummary/IndexSummaryManagerMBean.java
src/java/org/apache/cassandra/io/sstable/indexsummary/IndexSummaryBuilder.java
src/java/org/apache/cassandra/io/sstable/indexsummary/IndexSummary.java
src/java/org/apache/cassandra/io/sstable/format/big/BigTableReader.java
src/java/org/apache/cassandra/io/sstable/format/big/BigTableWriter.java
src/java/org/apache/cassandra/io/sstable/format/big/BigSSTableReaderLoadingBuilder.java
src/java/org/apache/cassandra/io/sstable/format/SSTableReader.java
src/java/org/apache/cassandra/io/util/Memory.java
src/java/org/apache/cassandra/utils/memory/MemoryUtil.java
src/java/org/apache/cassandra/config/Config.java
src/java/org/apache/cassandra/config/DatabaseDescriptor.java
src/java/org/apache/cassandra/schema/TableParams.java
src/java/org/apache/cassandra/tools/nodetool/Sjk.java
src/java/org/apache/cassandra/tools/nodetool/stats/TableStatsPrinter.java
src/java/org/apache/cassandra/db/ColumnFamilyStore.java (signatures)
src/java/org/apache/cassandra/metrics/RestorableMeter.java (constructor)
test/unit/org/apache/cassandra/io/sstable/indexsummary/IndexSummaryManagerTest.java
test/unit/org/apache/cassandra/ServerTestUtils.java
test/unit/org/apache/cassandra/SchemaLoader.java (signatures)
conf/cassandra.yaml
conf/cassandra-env.sh
conf/jvm-server.options
conf/jvm11-server.options
bin/cassandra, bin/cassandra.in.sh
build.xml (testsome, build-test, stress-build targets)
tools/cqlstress-example.yaml
CHANGES.txt
https://issues.apache.org/jira/browse/CASSANDRA-5519 (referenced, not fetched)

## D. Stage-4 feedback

**2026-10-21, run 1 on `pc12` — unit Confirmed (caps); cluster Confirmed — caps only on some paths (bypass).** Results:
[`stage4-runtime-verification/results/index_summary_capacity-distributeRemainingSpace-extraSpaceRequired--autonomous.md`](../../stage4-runtime-verification/results/index_summary_capacity-distributeRemainingSpace-extraSpaceRequired--autonomous.md)
(not committed). The step-0 audit (Ready after amendments) added R1–R7 above; the instrument checks and attempt 1 added runbook fixes
D1–D3. None changed B1 or a prediction.

- **Unit (B2):** every scenario-A row equals B2f exactly (kept = 0 · 0 · 0 · 0 · 1 · 2 · 3 · 7 · 7 · 8 · 8; T = F + kept·d ≤ P for
  P ≥ F, T = F below F, equality at P = F + d). Scenario B gives T = P exactly. Both controls hold at S_full, and the repeat is identical.
- **Cluster (B3, attempt 2):** S_full = 808.716 MiB (4 M × 212 B) over 31 sstables. After a run, T = 393.7 MiB at the default (409 MB)
  and at 400, 82.6 at 100 and 6.32 (≈ F) at 0. RssAnon fell 426.6 / 421.8 / 729.1 / 803.9 MiB against ΔT 415.0 / 415.0 / 726.1 / 802.4
  (σ = 22.8), and the within-lifetime falls agree. The TRACE lines show line 341 keeping 15 / 3 sstables and re-sampling the rest.
  Bypasses: `min = max_index_interval = 1` force-upsampled all 31 to 808.7 MiB at a 0 MiB cap. With the interval `null`, 1 M new
  partitions took the total from 82.6 to 284.8 MiB over a 100 MiB cap with no run (A3 7b, 7e).
- **For stage 3 (recommendations, not applied):** S1. A3 item 5's "total ≤ pool" assumes the planned size (`avgEntrySize × entries`)
  equals the real downsampled size; true here (fixed-length keys), not shown for variable-length keys. S2. The keep band (A3 7d) with
  real read rates was not exercised on a node. S3. `BigTableWriter.java:255` is `:254`. Side findings: an ALTER that names only
  `max_index_interval` is validated against the default `min_index_interval` 128, not the table's (D2). Stress's `population: seq(…)`
  on a key column does not give distinct keys (D1).
