# scaling_parameters (UCS per-level overlap threshold t) — verification solution  <!-- file: cases/scaling_parameters-getBuckets-maxOverlap--autonomous.md -->

| Field | Value |
|---|---|
| Entry pointer | the given line (capacity-set place), **linked**: [`UnifiedCompactionStrategy.java:552`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/compaction/UnifiedCompactionStrategy.java#L552), `int maxOverlap = -1;`, the per-level operand that the check at [`UnifiedCompactionStrategy.java:671`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/compaction/UnifiedCompactionStrategy.java#L671) compares against the threshold |
| Pinned source | `cassandra-5.0.9` |
| Session / date | claude-opus-5-5, Claude Code 2.1.330, 2026-11-24 |
| Estimate | `negative`. The value set at line 552 and compared at line 671 is a **count of overlapping SSTables** on one density level, checked against t, which is derived from the `scaling_parameters` table option. It decides only *whether* a compaction is started. It caps read amplification, not bytes. No byte quantity takes part in the decision, and the count is not a hard limit either. |
| Ground | (1) The check `maxOverlap < threshold` (line 671) compares two SSTable counts. SSTable sizes, the bytes in the level and heap or off-heap usage are never read on this path (`getBuckets`, lines 658-675). (2) SSTables that do not overlap never raise `maxOverlap` (`Overlaps.constructOverlapSets`), so a level can hold any number of SSTables and any number of bytes without a trigger. (3) For data with unique keys, disk bytes and the per-key off-heap structures (bloom filter, index summary) grow with the data written, whatever t is. t changes how the same bytes are spread across SSTables. (4) Even as a count the check can be exceeded. SSTables already being compacted are left out of the count (line 516), throttled compaction lets overlap grow past t, and with different thresholds per level, `chooseCompactionPick` (lines 369-389) can suppress a lower level's due compaction. With overwrites, t does change how many superseded copies stay on disk. That is a space-amplification ratio that scales with the data. It is not a byte cap (arm C in B3 tests this). |

## A. Constraint trace

**A1. The constraint.**
- **Name:** `scaling_parameters`, the Unified Compaction Strategy (UCS) table compaction option. It holds the per-level scaling parameter w, from which the per-level **threshold t** is derived: t = 2 for w ≤ 0 and t = 2 + w for w > 0. The fan factor is f = 2 + |w|.
- **Kind:** a per-table configuration entry (a compaction sub-option), with a JVM-property default.
- **Declaration:** the option name [`Controller.java:51`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/compaction/unified/Controller.java#L51) (`SCALING_PARAMETERS_OPTION = "scaling_parameters"`). The default is at `Controller.java:52-53` (`DEFAULT_SCALING_PARAMETERS = CassandraRelevantProperties.UCS_SCALING_PARAMETER.getString()`), and `CassandraRelevantProperties.java:612` declares `UCS_SCALING_PARAMETER("unified_compaction.scaling_parameters", "T4")`.
- **How t comes from it:**
  - `Controller.fromOptions` parses the string (`Controller.java:410`) through `parseScalingParameters` (`Controller.java:720-732`) and `UnifiedCompactionStrategy.parseScalingParameter` (`UnifiedCompactionStrategy.java:116-130`). `Tn` → w = n−2, `Ln` → w = 2−n, `N` → 0, or an integer w. `Tn`/`Ln` reject n < 2.
  - `Controller.getThreshold(index)` (`Controller.java:243-246`) calls `thresholdFromScalingParameter` (`UnifiedCompactionStrategy.java:111-114`).
  - Per level, `Level.<init>` stores it in `this.threshold` (`UnifiedCompactionStrategy.java:561`). It also pre-sizes `sstables = new ArrayList<>(threshold)` (line 562), which is only a capacity hint for the list.
  - The list's last value applies to all higher levels (`Controller.getScalingParameter`, `Controller.java:221-227`).
- **Unit:** a dimensionless count of SSTables that overlap at some key within one density level.
- **Default:** `T4` → w = 2, t = 4, f = 4 for every level. You can override it with JVM property `-Dunified_compaction.scaling_parameters=...` (node-wide default) or per table with `ALTER TABLE ... WITH compaction = {'class':'UnifiedCompactionStrategy','scaling_parameters':'T8'}`.
- **Restart needed?** No. A schema change rebuilds the strategy, and the new t is used on the next `getNextBackgroundTask`.

**A2. What it caps.**
- **Operand:** `Level.maxOverlap`, set up at line 552 and filled at line 670. It is the size of the largest *overlap set*, the most SSTables of one level whose key ranges all cover a common key.
- **What the threshold caps:** read amplification per level, i.e. how many SSTables of that level a read of one key has to consult. `UnifiedCompactionStrategy.md` lines 291-294 state this: "the read amplification that our trigger t aims to control".
- **What it does not cap:** no memory or disk quantity is compared. The resource it relates to is "number of overlapping SSTables". Disk bytes and per-SSTable memory are side effects of data volume, sharding (`target_sstable_size`, `base_shard_count`, `sstable_growth`, `min_sstable_size`) and overwrites.
- **Same operand, other compare:** `maxOverlap` is also compared with `max_sstables_to_compact` in `Bucket.constructPick` (lines 765-799, `selectPickSize` 803-826). That comparison limits how many SSTables one compaction takes. In 5.0.9 that option defaults to unlimited: `"0"` → `Integer.MAX_VALUE` at `Controller.java:202-203`, although the javadoc at `Controller.java:120-127` says "default is 32". It is never below f (line 765).

**A3. Mechanism.**
1. `CompactionStrategyManager.getNextBackgroundTask` → `UnifiedCompactionStrategy.getNextBackgroundTask` (line 220) → `getNextCompactionPick` (line 325).
2. `getCompactableSSTables` (lines 509-520) keeps only SSTables that are suitable and **not currently compacting** (line 516). SSTables in a running compaction are therefore not counted.
3. `formLevels` (lines 461-506) sorts the SSTables by density (size ÷ token span) and assigns each to a level whose density bounds are `[m·∏f_i, m·∏f_i·f_n)`. Each `Level` is built with t from the controller (lines 555-565). `maxOverlap` starts at −1 (**line 552**).
4. `chooseCompactionPick` (lines 369-389) calls `level.getCompactionPick` (line 597) on every level. That calls `getBuckets` (line 658):
   - `Overlaps.constructOverlapSets` (`Overlaps.java:58`) builds the overlap sets, and `maxOverlap = max(|set|)` (line 670).
   - **The check:** [`UnifiedCompactionStrategy.java:671`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/compaction/UnifiedCompactionStrategy.java#L671) `if (maxOverlap < threshold) return null;`.
   - **Below t:** no bucket and no compaction for this level. Nothing else happens, and writes and flushes go on.
   - **At or above t:** `Overlaps.assignOverlapsIntoBuckets(threshold, inclusionMethod, ...)` (line 674, `Overlaps.java:118-164`) builds buckets from the sets of size ≥ t, extended transitively by default. One bucket with the highest `maxOverlap` is picked at random (lines 612-623), and `constructPick` (line 759) returns:
     - all of the bucket if count ≤ f (line 768);
     - up to `max(f, max_sstables_to_compact)` oldest if count ≤ f·f_next (line 778);
     - otherwise a "layout" pick of f^k SSTables (`selectPickSize`, lines 803-826).
5. Across levels, the pick from the level with the highest `maxOverlap` wins (line 379).
6. The pick becomes a `UnifiedCompactionTask` (`createCompactionTask`, line 233 ff.). Background compactions run on `concurrent_compactors` threads at the rate `compaction_throughput` allows.

**Ways past the limit, or over it:**
- **Not a hard cap.** Flushes keep adding SSTables while compaction is busy or throttled. Overlap then exceeds t until compaction catches up, and the UCS doc (lines 330-333) describes the steady state "where compactions always use more sstables than the assigned threshold".
- **Running compactions are not counted.** SSTables in a running compaction are excluded at line 516, so the read path can see `maxOverlap(non-compacting) + compacting inputs` SSTables.
- **Selection quirk.** In `chooseCompactionPick`, a higher level with a larger `maxOverlap` that is still *below its own* threshold sets `selected` to its `null` pick (lines 379-382). A due compaction on a lower level is then dropped, but only when thresholds differ per level (e.g. `T4,T16`). The lower level's overlap can then grow past its t until it is at least equal to the higher level's overlap. Ties keep the lower level, because the comparison is strict.
- **Non-overlapping SSTables never trigger.** A level can hold unbounded numbers and bytes of them (e.g. after streaming or repair).
- **Bypassed entirely** by `nodetool disableautocompaction`, by `'enabled':'false'` in the compaction options, and by expired-SSTable handling, which is a separate path (`maybeGetExpiredSSTables`, lines 346-366).

**A4. Other consumers.**
Other things use the same resources, disk and per-SSTable memory, outside this check:
- **Data volume:** the bytes written, the bytes overwritten (superseded copies), and tombstones.
- **Transient compaction space:** inputs and outputs coexist until the transaction commits. The largest compaction, often at the top level, sets the peak.
- **Commit log and hints:** outside this check.
- **Snapshots:** `auto_snapshot` on drop or truncate.
- **SSTable count and size:** these come from `target_sstable_size` and the other sharding knobs (`Controller.getNumShards`, `Controller.java:264-356`).
- **Per-SSTable memory:**
  - bloom filters, sized from key count × `bloom_filter_fp_chance` (`FilterFactory.java:43-66`);
  - index summary (BIG format) and compression metadata, which scale with keys or bytes, not with the SSTable count;
  - `SSTableReader` objects and file handles, a small fixed cost per SSTable.
- **Other limits on the same compactions:** `max_sstables_to_compact` and `concurrent_compactors` / `compaction_throughput` also govern them.

**A5. Evidence beyond the source.**
- `src/java/org/apache/cassandra/db/compaction/UnifiedCompactionStrategy.md` (in tree): "Choosing sstables to compact" says t controls read amplification. "Selecting the compaction to run" describes overshoot under load. "Configuration" describes `scaling_parameters`, and it ties memory pressure to the *number* of SSTables, controlled by `target_sstable_size` and `sstable_growth`, not by t.
- `doc/modules/cassandra/pages/managing/operating/compaction/ucs.adoc` lines 484, 638, 675-681 (in tree). The `max_sstables_to_compact` entry says "Default: none (although 32 is a good choice)".
- `NEWS.txt:173-175`: UCS is introduced with "low space overhead", with no claim that t caps space.
- CEP-26: https://cwiki.apache.org/confluence/display/CASSANDRA/CEP-26%3A+Unified+Compaction+Strategy (linked from the class javadoc, line 63; I did not fetch it).
- Existing tests: `test/unit/org/apache/cassandra/db/compaction/UnifiedCompactionStrategyTest.java` (`testGetBucketsOneArena`, line 242 ff., asserts `pick != null` iff the level's SSTable count ≥ t for fully overlapping SSTables; `testLayout`, line 363 ff.).
- Git history is not available in this copy (no `.git`).

## B. Verification solution

**B1. Claim under test.**
The per-level threshold t from `scaling_parameters`, enforced through `Level.maxOverlap` at line 671, decides only on a count of overlapping SSTables. It does not bound disk or memory bytes.
- **Unit tier:** the trigger decision is the same whatever the SSTable bytes are, and non-overlapping SSTables never trigger.
- **Cluster tier:** for the same unique-key workload, live disk usage and per-SSTable off-heap memory after compaction settles are the same, within ±10%, for T2, T4 and T16. Only SSTable count and SSTables-per-read follow t.

### B2. Unit tier

**B2a. Environment and build.**
- Linux, JDK 11 (`java -version` shows 11.x), Apache Ant ≥ 1.10.
- Copy the source to local disk, never into a shared tree. Use `WORK=/mydata/$USER/ucs-t` (any local disk with ≥ 25 GiB free):
  `mkdir -p $WORK && rsync -a ~/cassandra-5.0.9/ $WORK/cassandra-5.0.9/`
- Build: `cd $WORK/cassandra-5.0.9 && ant jar` (also builds the tests and stress).
- Test source: create `test/unit/org/apache/cassandra/db/compaction/UcsMaxOverlapProbeTest.java` **in the copy** with the content below. It subclasses the existing test so that it reuses its mocked `ColumnFamilyStore`, its `Tracker`, `mockSSTable` and `mockNonOverlappingSSTables`. It is in the same package, so the package-private `Level.maxOverlap`, `threshold`, `fanout` and `getLevels()` are accessible.
- JVM options: the ones `testsome` sets. No extra options.

```java
package org.apache.cassandra.db.compaction;

import java.nio.ByteBuffer;
import java.util.*;
import org.junit.Test;
import org.mockito.Mockito;
import org.apache.cassandra.db.BufferDecoratedKey;
import org.apache.cassandra.db.DecoratedKey;
import org.apache.cassandra.db.compaction.unified.Controller;
import org.apache.cassandra.io.sstable.format.SSTableReader;
import org.apache.cassandra.utils.Overlaps;
import static org.mockito.ArgumentMatchers.anyDouble;
import static org.mockito.ArgumentMatchers.anyInt;
import static org.mockito.Mockito.when;

public class UcsMaxOverlapProbeTest extends UnifiedCompactionStrategyTest
{
    static final long MiB = 1L << 20;

    private Controller controller(int[] ws, int maxToCompact)
    {
        Controller c = Mockito.mock(Controller.class);
        when(c.getNumShards(anyDouble())).thenReturn(1);
        when(c.getBaseSstableSize(anyInt())).thenReturn((double) (512 * MiB)); // L0 upper bound = 512MiB*f
        when(c.maxSSTablesToCompact()).thenReturn(maxToCompact);
        when(c.getScalingParameter(anyInt())).thenAnswer(a -> { int i = a.getArgument(0); return ws[Math.min(i, ws.length - 1)]; });
        when(c.getFanout(anyInt())).thenCallRealMethod();
        when(c.getThreshold(anyInt())).thenCallRealMethod();
        when(c.getMaxLevelDensity(anyInt(), anyDouble())).thenCallRealMethod();
        when(c.getSurvivalFactor(anyInt())).thenReturn(1.0);
        when(c.random()).thenCallRealMethod();
        when(c.overlapInclusionMethod()).thenReturn(Overlaps.InclusionMethod.TRANSITIVE);
        return c;
    }

    private void report(String arm, int w, int mtc, long size, int n, UnifiedCompactionStrategy s, Controller c)
    {
        for (UnifiedCompactionStrategy.Level l : s.getLevels())
        {
            if (l.getSSTables().isEmpty()) continue;
            UnifiedCompactionStrategy.CompactionPick p = l.getCompactionPick(new UnifiedCompactionStrategy.SelectionContext(c));
            long bytes = 0; for (SSTableReader r : l.getSSTables()) bytes += r.onDiskLength();
            System.out.printf("PROBE arm=%s w=%d t=%d f=%d mtc=%d size=%d n=%d level=%d count=%d levelBytes=%d maxOverlap=%d pick=%s pickSize=%d%n",
                              arm, w, l.threshold, l.fanout, mtc, size, n, l.getIndex(), l.getSSTables().size(), bytes,
                              l.maxOverlap, p != null, p == null ? 0 : p.size());
        }
    }

    @Test
    public void probeMaxOverlap()
    {
        int[] ws = { 0, 2, 6, 14, -8 };                  // T2, T4, T8, T16, L10
        long[] sizes = { 1 * MiB, 64 * MiB };
        int[] mtcs = { Integer.MAX_VALUE, 32 };
        for (int w : ws) for (long size : sizes) for (int mtc : mtcs)
        {
            // Arm A: n fully overlapping SSTables (full token range), same level
            for (int n = 1; n <= 40; n++)
            {
                setUp();
                Controller c = controller(new int[]{ w }, mtc);
                UnifiedCompactionStrategy s = new UnifiedCompactionStrategy(cfs, new HashMap<>(), c);
                DecoratedKey first = new BufferDecoratedKey(partitioner.getMinimumToken(), ByteBuffer.allocate(0));
                DecoratedKey last = new BufferDecoratedKey(partitioner.getMaximumToken(), ByteBuffer.allocate(0));
                List<SSTableReader> l = new ArrayList<>();
                long ts = System.currentTimeMillis();
                for (int i = 0; i < n; i++) l.add(mockSSTable(0, size, ts + i, 0, first, last));
                s.addSSTables(l); dataTracker.addInitialSSTables(l);
                report("A", w, mtc, size, n, s, c);
            }
        }
        // Arm B: n pairwise non-overlapping SSTables (equal density, one level)
        for (int w : ws) for (int n : new int[]{ 1, 10, 100, 1000 })
        {
            setUp();
            Controller c = controller(new int[]{ w }, Integer.MAX_VALUE);
            UnifiedCompactionStrategy s = new UnifiedCompactionStrategy(cfs, new HashMap<>(), c);
            List<SSTableReader> l = mockNonOverlappingSSTables(n, 0, 64 * MiB);
            s.addSSTables(l); dataTracker.addInitialSSTables(l);
            report("B", w, Integer.MAX_VALUE, 64 * MiB, n, s, c);
        }
        // Arm Q: per-level thresholds T4,T16. L0 gets n overlapping 64MiB, L1 gets 10 overlapping 4GiB SSTables
        for (int n = 1; n <= 14; n++)
        {
            setUp();
            Controller c = controller(new int[]{ 2, 14 }, Integer.MAX_VALUE);
            UnifiedCompactionStrategy s = new UnifiedCompactionStrategy(cfs, new HashMap<>(), c);
            DecoratedKey first = new BufferDecoratedKey(partitioner.getMinimumToken(), ByteBuffer.allocate(0));
            DecoratedKey last = new BufferDecoratedKey(partitioner.getMaximumToken(), ByteBuffer.allocate(0));
            List<SSTableReader> l = new ArrayList<>();
            long ts = System.currentTimeMillis();
            for (int i = 0; i < 10; i++) l.add(mockSSTable(0, 4096 * MiB, ts - 1000 + i, 0, first, last));
            for (int i = 0; i < n; i++) l.add(mockSSTable(0, 64 * MiB, ts + i, 0, first, last));
            s.addSSTables(l); dataTracker.addInitialSSTables(l);
            UnifiedCompactionStrategy.CompactionPick p = s.getNextCompactionPick(0);
            System.out.printf("PROBE arm=Q n=%d strategyPick=%s pickLevel=%d pickSize=%d%n",
                              n, p != null, p == null ? -1 : p.level, p == null ? 0 : p.size());
            report("Q", 2, Integer.MAX_VALUE, 64 * MiB, n, s, c);
        }
    }
}
```

**B2b. Knobs.**
- **w (the constraint):** {0, 2, 6, 14, −8}, i.e. T2, T4, T8, T16, L10, giving t = {2, 4, 8, 16, 2} and f = {2, 4, 8, 16, 10}. This covers the minimum, the default, two larger tiered values and one levelled value. It is set through the mocked `Controller.getScalingParameter`. The real `getThreshold`/`getFanout` are called, so the production formula is used.
- **SSTable size s:** {1 MiB, 64 MiB}, a 64× change in bytes at an equal count. This tests whether bytes influence the decision.
- **`max_sstables_to_compact`:** {unset (`Integer.MAX_VALUE`, the real default after line 203), 32}. This is the secondary compare on the same operand.
- **Arm Q:** per-level Ws `{2, 14}` (`T4,T16`) for the cross-level selection quirk.
- **L0 bound:** `getBaseSstableSize` is fixed at 512 MiB, so every arm-A SSTable is in level 0: its upper bound is `floor(512 MiB·f) ≥ 1 GiB > 64 MiB`. In arm Q the 4 GiB SSTables fall in level 1, between 2 GiB and 32 GiB.

**B2c. Workload.**
- **Arm A:** n = 1…40 SSTables spanning the full token range, all overlapping. The overlap is exactly n, which crosses every t ∈ {2, 4, 8, 16} and, for f·f_next = 4, 16, 64, 256, 100, reaches the "late" branches of `constructPick`. The bytes in the level reach n·s ≤ 40 × 64 MiB = 2.5 GiB.
- **Arm B:** n ∈ {1, 10, 100, 1000} pairwise-disjoint SSTables of 64 MiB each, through `mockNonOverlappingSSTables`. Each has density 64 MiB·n, all in one level. The bytes in that level reach up to 64 GiB.
- **Arm Q:** level 1 holds 10 overlapping 4 GiB SSTables (overlap 10 < 16, so no pick there). Level 0 holds n = 1…14 overlapping 64 MiB SSTables (t₀ = 4).

**B2d. Observables and instruments.**
- One `PROBE` line per level per case on stdout, captured in `build/test/output/TEST-org.apache.cassandra.db.compaction.UcsMaxOverlapProbeTest-probeMaxOverlap.xml` (system-out) and in the console. Fields: `maxOverlap` (the operand of line 552/670), `t`, `pick` (outcome of line 671), `pickSize`, `count`, `levelBytes` (sum of `onDiskLength`).
- Arm Q also prints the strategy-wide pick (`getNextCompactionPick`).
- Not observable here: real heap or disk use. The mocks have no bytes behind them, so this tier only shows what the check decides on.

**B2e. Procedure.**
1. `cd $WORK/cassandra-5.0.9`, then create the test file above.
2. `ant testsome -Dtest.name=org.apache.cassandra.db.compaction.UcsMaxOverlapProbeTest -Dtest.methods=probeMaxOverlap 2>&1 | tee $WORK/unit.log`
3. Extract the lines: `grep -h -o 'PROBE .*' $WORK/unit.log build/test/output/TEST-*UcsMaxOverlapProbeTest*.xml | sort -u > $WORK/probe.txt`
4. Check the arm-A decision is independent of size. This must print nothing: `grep 'arm=A' $WORK/probe.txt | sed 's/size=[0-9]* //;s/levelBytes=[0-9]* //' | sort | uniq -c | awk '$1!=2'`. It prints any (w, mtc, n) line whose two size variants differ.
5. Inspect arms B and Q: `grep -E 'arm=(B|Q)' $WORK/probe.txt`.

**B2f. Predictions.**
- **Arm A, overlap:** `maxOverlap = n` for every w, s and mtc.
- **Arm A, trigger:** `pick=true` ⇔ n ≥ t. T2 and L10 trigger from n = 2, T4 from 4, T8 from 8, T16 from 16.
- **Arm A, bytes don't matter:** the `pick` and `pickSize` sequences are identical for s = 1 MiB and s = 64 MiB. At the first trigger, levelBytes is t·1 MiB in one run and t·64 MiB in the other.
- **Arm A, `pickSize` with mtc unset:**
  - n ≤ f gives n.
  - f < n ≤ f·f_next gives n.
  - Beyond that, T2 gives the largest power of 2 ≤ n (e.g. n = 5 → 4, n = 40 → 32), T4 gives 16 for 17 ≤ n ≤ 40, and L10 with n ≤ 40 stays at n.
  - T8 and T16 never reach the late branch for n ≤ 40.
- **Arm A, `pickSize` with mtc = 32:** the same except where n > max(f, 32) in the middle branch. Examples: L10 n = 33…40 → 32, T8 n = 33…40 → 32, T16 n = 33…40 → 32.
- **Arm B:** `maxOverlap = 1` and `pick=false` for every w and every n, up to 1000 SSTables and 64 GiB in the level.
- **Arm Q:**
  - For n = 1…9, `strategyPick=false` even when n ≥ 4, i.e. for n = 4…9, although the level-0 `pick` printed by `report` is `true`.
  - For n ≥ 10, level 1's overlap of 10 is no longer strictly greater, so `strategyPick=true`, at `pickLevel=0`.
  - So level 0's overlap reaches 10 against t₀ = 4.

**B2g. Readings.**

| Observation | Meaning |
|---|---|
| A: `pick` flips at n = t for each w, and the size variants are identical | Mechanism as traced. The check counts SSTables and ignores bytes, which **supports the claim** (count only, no byte bound) |
| A: for some (w, n) the decision or `pickSize` differs between 1 MiB and 64 MiB | Bytes do influence the trigger. **Claim refuted** at mechanism level, so re-trace |
| A: `maxOverlap ≠ n` for fully overlapping SSTables | Wrong trace of `constructOverlapSets`. The unit result is not interpretable |
| B: `pick=false` for all n, `levelBytes` up to 64 GiB | Usage does not follow t; level bytes grow with no trigger, which **confirms the claim** |
| B: some n triggers a pick | Something else in the path counts SSTables or bytes. **Claim refuted** for this path |
| Q: `strategyPick=false` for 4 ≤ n ≤ 9 | The cross-level quirk is real. The count itself can exceed t (A3) |
| Q: `strategyPick=true` at n = 4 | No quirk. The bypass claim in A3 is wrong, but the main claim is unaffected |
| Positive control (B2h) fails | The harness does not drive the check. **Not confirmed** |

**B2h. Controls.**
- **Positive control:** arm A itself. The same harness shows `pick` moving from false to true exactly at t when overlap increases, so the check does bind on its own operand.
- **Instrument sanity:** the existing `ant testsome -Dtest.name=org.apache.cassandra.db.compaction.UnifiedCompactionStrategyTest -Dtest.methods=testGetBucketsSameWUniqueArena` must pass in the same copy.
- **Fixed inputs:** randomness enters only through `controller.random()` when it chooses between buckets of equal overlap, and arm A has one bucket per level. Timestamps increase within each case so the oldest-first selection is deterministic.

### B3. Cluster tier

**B3a. Environment and build.**
- **Node and disk:** one Linux node, JDK 11, using the build from B2a in `$WORK/cassandra-5.0.9`. All node directories go under `$WORK/node` on local disk with ≥ 25 GiB free; check with `df -h $WORK`.
- **Configuration:** edit `$WORK/cassandra-5.0.9/conf/cassandra.yaml` in the copy:
  ```
  data_file_directories: [ $WORK/node/data ]      # write the literal path
  commitlog_directory: $WORK/node/commitlog
  saved_caches_directory: $WORK/node/saved_caches
  hints_directory: $WORK/node/hints
  cdc_raw_directory: $WORK/node/cdc_raw
  auto_snapshot: false
  concurrent_compactors: 2
  compaction_throughput: 0MiB/s          # unthrottled (arms A, C, controls); arm L changes it via nodetool
  listen_address: 127.0.0.1
  rpc_address: 127.0.0.1
  seed_provider: ... seeds: "127.0.0.1:7000"
  ```
- **Heap and logs:**
  ```
  export MAX_HEAP_SIZE=2G HEAP_NEWSIZE=400M
  export CASSANDRA_LOG_DIR=$WORK/node/logs
  ```
- **Start:** `cd $WORK/cassandra-5.0.9 && bin/cassandra -p $WORK/node/cassandra.pid`, then wait until `bin/nodetool status` shows `UN`.
- **Logging:** `bin/nodetool setlogginglevel org.apache.cassandra.db.compaction.UnifiedCompactionStrategy DEBUG` makes the "Level … max overlap …" lines from lines 603-604 and 628-629 appear in `$WORK/node/logs/debug.log`.

**B3b. Knobs.**

| Arm | Keyspace | `scaling_parameters` | Notes |
|---|---|---|---|
| A (claim) | `ks_t2` | `T2` (t = 2) | |
| A (claim) | `ks_t4` | `T4` (t = 4, the default) | |
| A (claim) | `ks_t16` | `T16` (t = 16) | |
| L (lag, count overshoot) | `ks_lag` | `T4` | `nodetool setcompactionthroughput 1` during the load, `0` afterwards |
| C (informative, overwrites) | `ks_ow2`, `ks_ow16` | `T2`, `T16` | the same 64 Ki keys rewritten every batch |
| PC (positive controls) | `ks_bf` | `T4` | `bloom_filter_fp_chance = 0.1`, against `ks_t4` at 0.01 |
| PC (positive controls) | `ks_t4x2` | `T4` | 80 batches instead of 40 |

- **Table, the same for every arm** (cassandra-stress default columns):
  ```
  CREATE KEYSPACE <ks> WITH replication = {'class':'SimpleStrategy','replication_factor':1};
  CREATE TABLE <ks>.standard1 (key blob PRIMARY KEY, "C0" blob, "C1" blob, "C2" blob, "C3" blob, "C4" blob)
    WITH compaction = {'class':'UnifiedCompactionStrategy','scaling_parameters':'<T>'}
    AND compression = {'enabled':'false'} AND bloom_filter_fp_chance = <0.01|0.1>;
  ```
- **Run order:** one keyspace at a time. Each keyspace is dropped after it is measured; with `auto_snapshot: false` no snapshot is kept.

**B3c. Workload.**
- **One batch:** 65,536 unique rows, flushed explicitly:
  `tools/bin/cassandra-stress write n=65536 no-warmup cl=ONE -pop seq=$((i*65536+1))..$(((i+1)*65536)) -col n=FIXED\(5\) size=FIXED\(200\) -schema keyspace=<ks> -rate threads=32 -node 127.0.0.1`
  followed by `bin/nodetool flush <ks> standard1`.
- **Batch size:** 1,000 B of incompressible values per row plus about 60 B of overhead ≈ 1.06 KB/row, so ≈ 66 MiB per flushed SSTable (φ). That is below `min_sstable_size` 100 MiB, so each flush gives one full-range SSTable.
- **40 batches** give ≈ 2.6 GiB of live data. That count is chosen as 32 + 8 so the end state differs by t: compaction reaches t in L0 for all three arms, and the arithmetic in B3f follows from `formLevels` and `getNumShards`.
- **Arm C:** the same, but with `-pop seq=1..65536` in every batch, so there are 40 overwrites of the same keys.
- **Arm C variant:** `size=FIXED(400)` to check that bytes scale with the data, not with any cap.
- **Duration:** about 20-40 s per batch, so 15-30 min per arm, plus settling.
- **Read phase**, after settling, to populate SSTables-per-read:
  `tools/bin/cassandra-stress read n=200000 no-warmup cl=ONE -pop dist=UNIFORM\(1..2621440\) -col n=FIXED\(5\) size=FIXED\(200\) -schema keyspace=<ks> -rate threads=32 -node 127.0.0.1`
  (for arm C use `UNIFORM(1..65536)`).

**B3d. Observables and instruments.**
- **Live and total disk:** `bin/nodetool tablestats <ks>.standard1`, fields `Space used (live)` and `Space used (total)`, plus `du -sb $WORK/node/data/<ks>`.
- **Peak disk during the run:** a sampler, `while sleep 2; do echo "$(date +%s) $(du -sb $WORK/node/data/<ks> | cut -f1)"; done > $WORK/<ks>.du &`. Record the maximum.
- **SSTable count:** the `SSTable count` field.
- **Off-heap per-SSTable memory:** `Bloom filter off heap memory used`, `Index summary off heap memory used`, `Compression metadata off heap memory used` and `Off heap memory used (total)` from `tablestats`.
- **Per-SSTable on-heap objects:** `jmap -histo:live $(cat $WORK/node/cassandra.pid) | grep -E 'BigTableReader|BtiTableReader|SSTableReader'` (instance count and shallow bytes).
- **Read amplification:** `bin/nodetool tablehistograms <ks> standard1`, the `SSTables` column at the 50/95/99/Max percentiles, after the read phase.
- **The operand itself:** `grep 'max overlap' $WORK/node/logs/debug.log` gives per-level `sstables` and `max overlap` at every selection. Report the max per level during the load and the last value after settling.
- **Settled state:** `bin/nodetool compactionstats` shows `pending tasks: 0` and no active compaction for 60 s.
- **Not directly observable:** the exact per-SSTable heap retained size, since jmap shallow sizes understate it. The per-key off-heap figures cover the significant part.

**B3e. Procedure.**
For each arm keyspace, one at a time:
1. Start the node, if it is not running, per B3a. Run `nodetool setlogginglevel ...UnifiedCompactionStrategy DEBUG`.
2. `bin/cqlsh 127.0.0.1 -e "<CREATE KEYSPACE ...; CREATE TABLE ...>"` per B3b.
3. Start the du sampler (B3d).
4. Arm L only: `bin/nodetool setcompactionthroughput 1`.
5. `for i in $(seq 0 39); do <stress write batch i>; bin/nodetool flush <ks> standard1; done`. For `ks_t4x2` use `seq 0 79`. For arm C use the fixed `-pop`.
6. Arm L only: record `tablestats` SSTable count and the latest `max overlap` lines (the "during load" reading), then `bin/nodetool setcompactionthroughput 0`.
7. Wait for settling: `until bin/nodetool compactionstats | grep -q 'pending tasks: 0' && ! bin/nodetool compactionstats | grep -q 'Compaction'; do sleep 10; done; sleep 60`.
8. Record `tablestats` and `jmap -histo:live`, and grep the last `max overlap` lines for this keyspace.
9. Run the read phase, then `tablehistograms`.
10. Stop the sampler (`kill %1`), then record the max of the du column.
11. `bin/cqlsh 127.0.0.1 -e "DROP KEYSPACE <ks>;"`, then confirm `du -sb $WORK/node/data/<ks>*` is gone or empty.

**B3f. Predictions.**
These use φ ≈ 66 MiB and the defaults `min_sstable_size` 100 MiB, `base_shard_count` 4, `target_sstable_size` 1 GiB and `sstable_growth` 0.333, and are stated before any run.

Arm A after settling (40 unique-key batches):

| | T2 | T4 | T16 |
|---|---|---|---|
| `Space used (live)` | ≈ 2.6 GiB | ≈ 2.6 GiB | ≈ 2.6 GiB |
| SSTable count | ≈ 8 | ≈ 12 | ≈ 16 |
| SSTables/read max | ≤ 2 | ≤ 4 | ≤ 10 |
| Max overlap in L0 during the load | ≤ 2 | ≤ 4 | ≤ 16 |
| Bloom filter off-heap total | B | B | B |

- **Live disk:** the three values are equal within ±10% (the claim).
- **SSTable count, T2:** one top run of 4 × ≈ 660 MiB plus one run of 528 MiB in 4 shards.
- **SSTable count, T4:** two L2 runs × 4, plus two L1 runs × 2.
- **SSTable count, T16:** two L1 runs × 4, plus 8 flush SSTables in L0.
- **Bloom filter:** B is about 2.6 M keys × ~10 bits ≈ 3.3 MB. All three are equal within ±10%. The index summary and compression metadata are also equal within ±10%.
- **Peak disk:** not ordered by t. T2's peak includes the top merge at batch 32 (2 × 1056 MiB inputs + 2112 MiB output), so it is ≈ 2× live. T16's peak is ≈ live + 1 GiB. So peak(T2) ≥ peak(T16) is predicted, the opposite of "a smaller t caps disk tighter".

Arm L, during the load, with throughput at 1 MiB/s:
- L0 `max overlap` in debug.log rises **above 4**, to ≥ 8.
- The SSTable count exceeds the settled T4 value.

Arm L after unthrottling and settling:
- The values return to the arm-A T4 values within ±10% (count ±2).

Arm C (informative), settled:
- live(T16) > live(T2), ratio ≥ 2.
- With `size=FIXED(400)` the live disk roughly doubles, by 1.8-2.2×, for the same t. So t sets a multiple of the dataset size, not a byte limit.

Positive controls:
- **Bloom filter:** BF off-heap(`ks_bf`, 0.1) / BF off-heap(`ks_t4`, 0.01) = 0.4-0.6.
- **Data volume:** live(`ks_t4x2`) / live(`ks_t4`) = 1.9-2.1.

**What would show the claim wrong:** in arm A, settled live disk or bloom-filter off-heap memory differs by more than 10% between T2, T4 and T16 and falls in the order of t (T2 < T4 < T16) while the positive controls move as predicted.

**B3g. Readings.**

| Observation | Meaning |
|---|---|
| A: live disk and BF/index off-heap equal within ±10% across T2/T4/T16; SSTable count and SSTables/read follow t; PC moves as predicted | Usage is flat while the control moves. **Claim confirmed** (t bounds a count, not bytes) |
| A: live disk or off-heap memory differ by more than 10% and are ordered by t (smaller t → less usage), PC as predicted | Usage follows the knob. **Claim refuted**; t does bound bytes on this workload |
| A: SSTables/read and `max overlap` do not differ between T2 and T16 | The limit never took effect (e.g. compaction disabled or the table not using UCS). **Not confirmed**, so check `DESCRIBE TABLE` and debug.log |
| PC: BF ratio outside 0.4-0.6 or volume ratio outside 1.9-2.1 | The instruments or workload do not register usage changes. **Not confirmed** |
| L: L0 `max overlap` > 4 during the throttled load | The count is a trigger, not a cap. This supports the Ground (4) |
| L: `max overlap` never exceeds 4 even when throttled | Overshoot claim wrong; the main claim is unaffected |
| C: live(T16)/live(T2) ≥ 2 and live scales about 2× with value size | t controls the overwrite space-amplification *ratio*, not bytes. This is consistent with the negative estimate |
| C: live disk stays at a fixed byte level regardless of value size | A byte bound exists. **Claim refuted**; re-trace |

**B3h. Controls.**
- **Same everything except t:** same build, node, heap, schema, compression (off), key sets, flush points and read distribution. Arms run one at a time on the same node, so other tables' compactions do not compete.
- **Two positive controls:** `bloom_filter_fp_chance` is a knob known to size the bloom filter, and doubling the data is known to double disk. They show the instruments and workload register usage changes of the predicted size.
- **Settling criterion:** avoids comparing in-flight compaction states.
- **Incompressible values with compression off:** stress values are random, so on-disk bytes track logical bytes.
- **Table checks:** `DESCRIBE TABLE <ks>.standard1` confirms that `scaling_parameters` took effect. debug.log `Level ... max overlap` lines confirm that UCS, not another strategy, is selecting.
- **System tables:** they use their own compaction settings and are excluded by measuring only `<ks>.standard1`.

**B4. Risks and cleanup.**
- **Disk:** at most ≈ 5.5 GiB under `$WORK/node` at the T2 top merge, plus ≈ 2.6 GiB from `ks_t4x2` (peak ≈ 11 GiB). The commit log is capped by the default `commitlog_total_space`. Everything is on local disk under `$WORK`, nothing on shared storage. `auto_snapshot: false` prevents drop snapshots, and `nodetool clearsnapshot --all` at the end is a safety net.
- **Unit tier:** writes only under `$WORK/cassandra-5.0.9/build`. Nothing is added to `~/cassandra-5.0.9`, the shared copy.
- **Processes:**
  - After the last arm, run `bin/nodetool stopdaemon`, or `kill $(cat $WORK/node/cassandra.pid)`.
  - Stop any du sampler (`jobs -p | xargs -r kill`).
  - Check `pgrep -u $USER -f CassandraDaemon` and `pgrep -u $USER -f cassandra-stress` both print nothing.
  - Check `pgrep -u $USER -f 'org.apache.tools.ant'` prints nothing after the unit tier.
- **Cleanup:** `rm -rf $WORK/node` once the readings have been copied out. Remove `$WORK/cassandra-5.0.9` if it is no longer needed.

## C. Sources read

- src/java/org/apache/cassandra/db/compaction/UnifiedCompactionStrategy.java
- src/java/org/apache/cassandra/db/compaction/unified/Controller.java
- src/java/org/apache/cassandra/utils/Overlaps.java
- src/java/org/apache/cassandra/db/compaction/ShardManager.java (density, create)
- src/java/org/apache/cassandra/config/CassandraRelevantProperties.java (UCS_* properties, getString)
- src/java/org/apache/cassandra/utils/FilterFactory.java (grep only)
- src/java/org/apache/cassandra/db/compaction/UnifiedCompactionStrategy.md
- doc/modules/cassandra/pages/managing/operating/compaction/ucs.adoc
- NEWS.txt (lines 168-180)
- conf/cassandra.yaml (default_compaction, auto_snapshot, compaction_throughput, concurrent_compactors)
- conf/cassandra_latest.yaml (max_sstables_to_compact, grep only)
- conf/logback.xml
- build.xml (jar, testsome targets)
- test/unit/org/apache/cassandra/db/compaction/UnifiedCompactionStrategyTest.java
- tools/stress/src/org/apache/cassandra/stress/settings/SettingsSchema.java
- tools/stress/src/org/apache/cassandra/stress/settings/OptionCompaction.java
- https://cwiki.apache.org/confluence/display/CASSANDRA/CEP-26%3A+Unified+Compaction+Strategy (cited from the source; not fetched)

## D. Stage-4 feedback

none yet
