# scaling_parameters (UCS per-level threshold `t`) — verification solution  <!-- file: cases/scaling_parameters-Level-threshold--autonomous.md -->

| Field | Value |
|---|---|
| Entry pointer | the given line (unit kind capacity-set), **linked**: [`UnifiedCompactionStrategy.java:561`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/compaction/UnifiedCompactionStrategy.java#L561) — `this.threshold = controller.getThreshold(index);`, whose value is used on the next line as the initial capacity of the level's sstable list, `this.sstables = new ArrayList<>(threshold);` ([`:562`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/compaction/UnifiedCompactionStrategy.java#L562)) |
| Pinned source | `cassandra-5.0.9` |
| Session / date | claude-opus-5-5, Claude Code 2.1.330, 2026-11-24 |
| Estimate | `negative`. The threshold set on line 561 is a compaction-trigger count (number of overlapping sstables that makes a level eligible for compaction); on line 562 it is only the *initial* capacity of an `ArrayList` that grows without any check (`Level.add`, :577-580), and nothing compares a byte quantity of heap or disk against it. |
| Ground | (1) Memory: `new ArrayList<>(threshold)` is a pre-sizing hint; `Level.add` appends unconditionally, so the list (and its backing array) grows with the number of sstables in the level, not with `t`; the array is a few dozen bytes at the default and the `Level` objects are transient (rebuilt on every `getNextBackgroundTask`). (2) Disk: `t` only decides *when* a background compaction becomes eligible (`maxOverlap < threshold → return null`, :671-672); writes are never refused or delayed by it, so when compaction lags (throughput cap, `concurrent_compactors`) the number of overlapping sstables and the bytes they occupy exceed any `t`-derived value; with non-overwriting data the bytes on disk are set by the data volume, whatever `t` is. |

> **Link rule.** Two places must be links, not plain `file:line`: **the constraint's
> declaration** (A1) and **the if statement** (the check; the Entry pointer row above and
> A3). For this capacity-set unit, "the if statement" is read as the given line
> ([`UnifiedCompactionStrategy.java:561`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/compaction/UnifiedCompactionStrategy.java#L561)).

## A. Constraint trace

**A1. The constraint.**

- **Name:** UCS `scaling_parameters` (per-level scaling parameter `w`), from which the per-level
  **threshold `t`** used at the target line is derived. Line 561 stores `t` in `Level.threshold`.
- **Kind:** configuration entry — a per-table compaction sub-option
  (`compaction = {'class': 'UnifiedCompactionStrategy', 'scaling_parameters': '...'}`), whose
  default comes from a JVM system property.
- **First declared:** the option name
  [`Controller.java:51`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/compaction/unified/Controller.java#L51)
  (`SCALING_PARAMETERS_OPTION = "scaling_parameters"`); its default
  [`CassandraRelevantProperties.java:612`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/CassandraRelevantProperties.java#L612)
  (`UCS_SCALING_PARAMETER("unified_compaction.scaling_parameters", "T4")`), read into
  `DEFAULT_SCALING_PARAMETERS` at `Controller.java:52-53`.
- **Unit:** dimensionless; `t` is a count of overlapping sstables.
- **Default and derivation:** `"T4"`. `parseScalingParameter` (`UnifiedCompactionStrategy.java:116-130`)
  maps `T<f>` → `w = f − 2`, `L<f>` → `w = 2 − f`, `N` → `0`, or an integer `w` directly
  (`f ≥ 2` enforced at :132-137, `atLeast2`). `thresholdFromScalingParameter(w)` (:111-114) returns `t = 2` for
  `w ≤ 0`, else `t = 2 + w`; `fanoutFromScalingParameter(w)` (:106-109) returns `f = 2 − w` for
  `w < 0`, else `2 + w`. So T4 → `w = 2`, `t = 4`, `f = 4`; L4 → `w = −2`, `t = 2`, `f = 4`;
  T8 → `t = 8`; T16 → `t = 16`. A comma list gives one `w` per level; levels past the list use the
  last entry (`Controller.getScalingParameter`, `Controller.java:221-228`). `Controller.getThreshold(index)`
  (`Controller.java:243-246`) applies this to the level index.
- **How set:** per table with `CREATE/ALTER TABLE ... WITH compaction = {...,'scaling_parameters':'T8'}`
  (parsed in `Controller.fromOptions`, `Controller.java:410`; validated at :468-470). An `ALTER`
  takes effect without restart: the compaction strategy manager reloads the strategy from the new
  schema params (`CompactionStrategyManager.java:478-499`). The default for tables that do not set
  it is `-Dunified_compaction.scaling_parameters=<value>` (no `cassandra.` prefix), read once into a
  `static final` (`Controller.java:52-53`), so changing the default needs a restart.

**A2. What it caps.**

Nothing in heap or disk bytes. The quantity compared against `t` is `Level.maxOverlap`, the largest
number of sstables of that density level that cover a common key (`UnifiedCompactionStrategy.java:667-671`).
`t` gates whether a background compaction is *offered* for the level. The memory-side use at the
given line is the initial capacity of `Level.sstables` (:562), an `ArrayList<SSTableReader>` of
references (heap). Indirectly `t` is a read-/space-amplification knob: at quiescence, an overwrite
workload keeps at most `t − 1` overlapping copies per level (see A3), but this is an eventual target
of a background process, not a limit enforced on usage.

**A3. Mechanism.**

1. `getNextBackgroundTask` (:220-230) → `getNextCompactionPick` (:325-344) → `chooseCompactionPick`
   (:369-387) → `formLevels(suitable)` (:461-507).
2. `formLevels` sorts the candidates by density and creates `Level` objects as it walks them
   (:469, :487). Each construction runs the **given line**
   [`UnifiedCompactionStrategy.java:561`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/compaction/UnifiedCompactionStrategy.java#L561)
   (`this.threshold = controller.getThreshold(index)`), then :562 allocates
   `new ArrayList<>(threshold)` — a backing `Object[t]`.
3. Every sstable whose density falls in the level is appended with `level.add(candidate)`
   (:476/:490 → `Level.add` :577-580, a plain `ArrayList.add`). There is **no check against
   `threshold`**: when the count passes `t` the JDK grows the backing array (≈1.5× per growth step,
   JDK `ArrayList` contract: capacity is "at least as large as the list size" and "grows
   automatically"). The level list therefore holds every sstable of the level; its memory follows the
   sstable count, not `t`.
4. `Level.getCompactionPick` (:597-637) → `getBuckets` (:658-680): computes `maxOverlap` over the
   overlap sets (:665-670); **`if (maxOverlap < threshold) return null;`** (:671-672) — no compaction
   for this level. Otherwise the overlap sets are grouped into buckets (`Overlaps.assignOverlapsIntoBuckets(threshold, ...)`,
   :674-677), one bucket with the highest overlap is chosen (:612-623), and `Bucket.constructPick`
   (:759-801) builds a pick of all of the bucket's sstables if `count ≤ fanout`, otherwise a limited
   one bounded by `max(fanout, max_sstables_to_compact)`.
5. Outcomes at the limit: below `t`, nothing happens; at or above `t`, a compaction *may* be
   scheduled, subject to `concurrent_compactors`, `compaction_throughput` and competing levels/tables.
   Writes and flushes are never blocked by it.
6. **Overshoot/bypass paths.** (a) Flushes keep adding sstables while compactions are queued or
   throttled; the design doc states that under sustained load "compactions always use more sstables
   than the assigned threshold" (`UnifiedCompactionStrategy.md:330-333`). (b) sstables being compacted
   stay live on disk until the compaction finishes, and the output is written beside them (temporary
   extra space; up to 100% for a major compaction, :152-156). (c) Expired-sstable drops and
   user-defined / major compactions (`getMaximalTask`, :150-165; `getUserDefinedTask`, :197-209) ignore `t`.
   (d) The `Level` list is filled from all suitable sstables of the level, whatever their number.

**A4. Other consumers.**

- Heap: `SSTableReader` objects and their metadata (one per live sstable, a count that `t` influences
  only indirectly), memtables, caches, `formLevels`' own `levels` list (`new ArrayList<>(MAX_LEVELS)`,
  :464, 32 references), the `suitable` copy (:513), overlap sets and buckets built per selection.
- Off-heap: per-sstable bloom filters, compression metadata, index summaries / SAI structures —
  proportional to sstable count and size.
- Disk: live sstables of all tables, compaction temporary outputs, commit log, hints, snapshots
  (`auto_snapshot` on DROP/TRUNCATE), saved caches.

**A5. Evidence beyond the source.**

- Design doc in the tree: `src/java/org/apache/cassandra/db/compaction/UnifiedCompactionStrategy.md`
  lines 34-49 (definition of `w`, `f`, `t`: "each level triggering a compaction as soon as it has `t`
  overlapping sstables"), 330-333 (under sustained load compactions use more sstables than the
  threshold), 401-414 (`scaling_parameters` option, default T4).
- CEP-26: https://cwiki.apache.org/confluence/display/CASSANDRA/CEP-26%3A+Unified+Compaction+Strategy (cited in the class Javadoc, :60-64).
- JDK 11 `java.util.ArrayList` Javadoc (initial capacity; automatic growth):
  https://docs.oracle.com/en/java/javase/11/docs/api/java.base/java/util/ArrayList.html
- Existing tests that already drive `Level` with a mocked `Controller`:
  `test/unit/org/apache/cassandra/db/compaction/UnifiedCompactionStrategyTest.java` (e.g. :244-295, :824-878).
- Git history: not available in the provided copy (no `.git`); none used.

## B. Verification solution

**B1. Claim under test.** The UCS threshold `t` set at `UnifiedCompactionStrategy.java:561` does not
cap memory or disk: (a) `Level.sstables` holds every sstable of its level, and its backing array grows
past `t` in proportion to the sstable count; (b) on a running node, while writes outpace compaction the
number of overlapping live sstables and the table's live bytes exceed `t − 1` flush-sized sstables for
every `t`, and for non-overwriting data the converged on-disk size is the same for every `t`.

### B2. Unit tier

**B2a. Environment and build.**

- Linux, JDK 11 (`java -version` → 11.x), Apache Ant ≥ 1.10.
- Copy the tree to local disk, never build in the shared copy:
  `export WORK=/local/$USER/ucs-t; mkdir -p $WORK; rsync -a ~/cassandra-5.0.9/ $WORK/src/; cd $WORK/src`.
- Build: `ant build-test` (compiles main + tests and resolves jars).
- Test source to add (in the copy only):
  `$WORK/src/test/unit/org/apache/cassandra/db/compaction/UcsThresholdCapacityTest.java`, below. It
  extends the existing `UnifiedCompactionStrategyTest` to reuse its mocked `ColumnFamilyStore`,
  dummy `Tracker` and `mockSSTable(...)` helper (same package, package-private access to
  `Level.sstables` and `Level.threshold`).
- JVM options: those of `ant testsome` (it adds the jamm agent `-javaagent:.../jamm-0.4.0.jar` and the
  JDK 11 `--add-opens`; on JDK 11 the reflective read of `ArrayList.elementData` is also allowed by the
  default `--illegal-access=permit`).

```java
package org.apache.cassandra.db.compaction;

import java.lang.reflect.Field;
import java.nio.ByteBuffer;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;

import org.junit.Test;
import org.mockito.Mockito;

import org.apache.cassandra.db.BufferDecoratedKey;
import org.apache.cassandra.db.DecoratedKey;
import org.apache.cassandra.db.compaction.unified.Controller;
import org.apache.cassandra.io.sstable.format.SSTableReader;
import org.apache.cassandra.utils.Overlaps;
import org.github.jamm.MemoryMeter;

import static org.mockito.ArgumentMatchers.anyDouble;
import static org.mockito.ArgumentMatchers.anyInt;
import static org.mockito.Mockito.when;

public class UcsThresholdCapacityTest extends UnifiedCompactionStrategyTest
{
    // L4, T4, T8, T16  ->  t = 2, 4, 8, 16
    static final int[] WS = { -2, 2, 6, 14 };

    @Test
    public void levelListGrowsPastThreshold() throws Exception
    {
        Field elementData = ArrayList.class.getDeclaredField("elementData");
        elementData.setAccessible(true);
        MemoryMeter meter = MemoryMeter.builder().build();
        long base = 2L << 20;   // level-0 base size 2 MiB; sstables are 1 MiB, so all fall in level 0

        System.out.println("RESULT W,t,K,size,capacity,arrayBytes,pickNonNull");
        for (int W : WS)
        {
            int t = UnifiedCompactionStrategy.thresholdFromScalingParameter(W);
            for (int K : new int[]{ 1, Math.max(1, t - 1), t, 4 * t, 2000 })
            {
                Controller c = Mockito.mock(Controller.class);
                when(c.getScalingParameter(anyInt())).thenReturn(W);
                when(c.getFanout(anyInt())).thenCallRealMethod();
                when(c.getThreshold(anyInt())).thenCallRealMethod();
                when(c.getMaxLevelDensity(anyInt(), anyDouble())).thenCallRealMethod();
                when(c.getSurvivalFactor(anyInt())).thenReturn(1.0);
                when(c.getNumShards(anyDouble())).thenReturn(1);
                when(c.getBaseSstableSize(anyInt())).thenReturn((double) base);
                when(c.maxConcurrentCompactions()).thenReturn(1000);
                when(c.maxThroughput()).thenReturn(Double.MAX_VALUE);
                when(c.maxSSTablesToCompact()).thenReturn(1000);
                when(c.overlapInclusionMethod()).thenReturn(Overlaps.InclusionMethod.TRANSITIVE);
                when(c.random()).thenCallRealMethod();

                UnifiedCompactionStrategy s = new UnifiedCompactionStrategy(cfs, new HashMap<>(), c);
                DecoratedKey first = new BufferDecoratedKey(partitioner.getMinimumToken(), ByteBuffer.allocate(0));
                DecoratedKey last  = new BufferDecoratedKey(partitioner.getMaximumToken(), ByteBuffer.allocate(0));
                List<SSTableReader> ss = new ArrayList<>(K);
                for (int i = 0; i < K; i++)
                    ss.add(mockSSTable(1L << 20, System.currentTimeMillis(), first, last)); // all overlap fully

                List<UnifiedCompactionStrategy.Level> levels = s.getLevels(ss, r -> true);
                UnifiedCompactionStrategy.Level l0 = levels.get(0);
                Object[] arr = (Object[]) elementData.get(l0.sstables);
                UnifiedCompactionStrategy.CompactionPick pick =
                    l0.getCompactionPick(new UnifiedCompactionStrategy.SelectionContext(c));
                System.out.printf("RESULT %d,%d,%d,%d,%d,%d,%b%n",
                                  W, l0.threshold, K, l0.getSSTables().size(), arr.length, meter.measure(arr), pick != null);
            }
        }
    }
}
```

**B2b. Knobs.** `w` ∈ {−2, 2, 6, 14} (= L4, T4 default, T8, T16 → `t` = 2, 4, 8, 16), set by stubbing
`Controller.getScalingParameter`; `getThreshold`/`getFanout` run their real code, so `t` is computed
exactly as on line 561. These span the levelled minimum (`t = 2`), the default, and two larger tiered
values. (Cross-check of the string form: `Controller.parseScalingParameters("L4,T4,T8,T16")` returns
`[-2, 2, 6, 14]`.)

**B2c. Workload.** For each `t`, K ∈ {1, t−1, t, 4t, 2000} mock sstables of 1 MiB, each spanning the
whole token range (first = min token, last = max token), so all are in level 0 (density 1 MiB <
level-0 max = floor(2 MiB × f) ≥ 8 MiB) and all overlap pairwise (`maxOverlap = K`). K = t−1 and t
straddle the trigger; 4t and 2000 are well past it.

**B2d. Observables and instruments.** Per (w, K): `l0.threshold` (the value stored by line 561);
`l0.getSSTables().size()`; the backing-array length (`ArrayList.elementData.length`, by reflection);
its shallow size in bytes (`MemoryMeter.measure`, jamm 0.4.0 instrumentation); whether
`getCompactionPick` returns a pick (the threshold's actual effect). Not observed: the retained size of
the referenced `SSTableReader`s (mocks; not part of this list's own footprint).

**B2e. Procedure.**

1. `cd $WORK/src && ant build-test`.
2. Write the test file above at the stated path.
3. `ant testsome -Dtest.name=org.apache.cassandra.db.compaction.UcsThresholdCapacityTest -Dtest.methods=levelListGrowsPastThreshold`
4. Collect the lines: `grep -h '^RESULT' build/test/output/TEST-org.apache.cassandra.db.compaction.UcsThresholdCapacityTest*.xml build/test/output/*.txt 2>/dev/null` (or from the console log of step 3), into `$WORK/unit-results.csv`.
5. Repeat step 3 twice more; the three runs must give identical rows (deterministic).

**B2f. Predictions.** (64-bit JVM with compressed oops: array bytes = align8(16 + 4 × capacity).)

| t | K | size | capacity | array bytes | pick non-null |
|---|---|---|---|---|---|
| 2 | 1 | 1 | 2 | 24 | false |
| 2 | 2 | 2 | 2 | 24 | true |
| 2 | 8 | 8 | 9 | 56 | true |
| 2 | 2000 | 2000 | 2398 | 9608 | true |
| 4 | 1 / 3 | 1 / 3 | 4 | 32 | false |
| 4 | 4 | 4 | 4 | 32 | true |
| 4 | 16 | 16 | 19 | 96 | true |
| 4 | 2000 | 2000 | 2398 | 9608 | true |
| 8 | 1 / 7 | 1 / 7 | 8 | 48 | false |
| 8 | 8 | 8 | 8 | 48 | true |
| 8 | 32 | 32 | 40 | 176 | true |
| 8 | 2000 | 2000 | 2296 | 9200 | true |
| 16 | 1 / 15 | 1 / 15 | 16 | 80 | false |
| 16 | 16 | 16 | 16 | 80 | true |
| 16 | 64 | 64 | 81 | 344 | true |
| 16 | 2000 | 2000 | 2053 | 8232 | true |

General relation: `size = K`
always; `capacity = t` for K ≤ t, and for K > t the first value of the sequence c₀ = t,
cₙ₊₁ = max(cₙ + ⌊cₙ/2⌋, cₙ + 1) that is ≥ K (so capacity ∈ [K, 1.5K]); bytes grow ≈ 4 B per sstable,
independent of `t` once K ≫ t. `pick != null` iff K ≥ t.

**B2g. Readings.**

| Observation | Meaning |
|---|---|
| `size = K` and capacity ≥ K for K > t, bytes rising ≈ linearly with K for all four `t` | usage does not follow the constraint — claim **confirmed** (provided the control row below also holds) |
| `pick` flips from false to true exactly at K = t for every `t` | positive control: the threshold is in force and binds the *trigger* in this same harness |
| `size` or capacity stays ≤ t when K > t (list truncated, exception, or sstables dropped from the level) | the given line caps the list — claim **refuted** |
| array bytes for K = 2000 differ by more than the capacity-rounding differences above across `t` (i.e. scale with `t`) | usage follows the knob — claim **refuted** |
| sstables do not all land in level 0 (`levels.get(0).getSSTables().size() < K`) or `pick` never flips | workload did not reach the limit / control did not move — **not confirmed**; fix base size or mocks and rerun |

**B2h. Controls.**

- Positive control: `pick` toggles at K = t (the same `threshold` value is actually used by `getBuckets`, :671).
- `l0.threshold` printed equals `thresholdFromScalingParameter(w)`, proving line 561 ran with the intended value.
- K = 1 and K = t rows: capacity = t, showing line 562's pre-sizing *is* `t`-dependent while the list is
  small, so a flat result at large K is not due to the field being unused.
- Three identical runs rule out nondeterminism (the only randomness, bucket choice, does not affect
  the measured values).

### B3. Cluster tier

The heap side (`Level` lists, tens of bytes to a few KiB, rebuilt per selection) is below any heap
instrument's resolution on a node; it is covered by B2. The cluster tier tests the disk side of the
claim: whether `t` bounds live sstables / bytes on disk.

**B3a. Environment and build.**

- One Linux node, JDK 11, Ant; ≥ 4 CPU cores, ≥ 8 GiB RAM, a local (non-shared) filesystem with
  ≥ 20 GiB free at `$RUN` (e.g. `export RUN=/local/$USER/ucs-s4`).
- Build in a local copy: `rsync -a ~/cassandra-5.0.9/ $RUN/src/ && cd $RUN/src && ant jar && ant stress-build`.
- `$RUN/src/conf/cassandra.yaml` changes:
  ```
  data_file_directories: [ $RUN/data ]      # write the expanded path
  commitlog_directory: $RUN/commitlog
  saved_caches_directory: $RUN/saved_caches
  hints_directory: $RUN/hints
  cdc_raw_directory: $RUN/cdc_raw
  commitlog_total_space: 2048MiB
  concurrent_compactors: 1
  compaction_throughput: 64MiB/s          # changed at runtime per phase
  auto_snapshot: false
  ```
- Heap: `export MAX_HEAP_SIZE=2G HEAP_NEWSIZE=400M` before start (memtable space 1/4 heap = 512 MiB,
  so a 21 MiB pass never flushes by itself; every sstable comes from an explicit `nodetool flush`).
- Start: `$RUN/src/bin/cassandra -p $RUN/cassandra.pid > $RUN/cassandra.out 2>&1`; wait until
  `$RUN/src/bin/nodetool status` shows `UN`.
- Per-level visibility: `$RUN/src/bin/nodetool setlogginglevel org.apache.cassandra.db.compaction.UnifiedCompactionStrategy DEBUG`
  (enables the "Level {} sstables {} max overlap {} ..." lines, :603 / :628, in `logs/debug.log`).

**B3b. Knobs.** `scaling_parameters` ∈ {`L4`, `T4`, `T8`, `T16`} (t = 2, 4, 8, 16), one fresh keyspace
per value (`ucs_l4`, `ucs_t4`, `ucs_t8`, `ucs_t16`), set at table creation through the stress
`-schema compaction(...)` option. Secondary knob per phase: `nodetool setcompactionthroughput 1`
(lagging compaction) vs `0` (unthrottled).

**B3c. Workload.** `cassandra-stress` predefined `write`, 1 column of 1024 B, 20,000 partitions per
pass (≈ 20,000 × ~1.05 KiB ≈ 21 MiB per flush; values are random bytes, so LZ4 compression changes it
little — the per-flush size `S` is read from the first flush, not assumed).

- Phase A (overwrite, compaction lagging): throughput 1 MiB/s; 32 passes over the *same* keys
  `-pop seq=1..20000`, each followed by `nodetool flush`. At 1 MiB/s a T4 compaction (4 × 21 MiB
  input) takes ≈ 84 s and a T16 one ≈ 336 s, while a pass + flush takes ~10-15 s, so flushes outrun
  compaction for every `t`; 32 flushes exceed `t − 1` for all four values (32 > 15). Duration ≈ 6-8 min.
- Phase B (same data, compaction unthrottled to quiescence): throughput 0; wait until
  `nodetool compactionstats` reports 0 pending and no active compaction for 60 s (cap 30 min).
- Phase C (insert-only, separate keyspaces `ucs_<w>_u`): throughput 0; 32 passes of *distinct* keys,
  pass i uses `-pop seq=$((i*20000+1))..$(((i+1)*20000))`, flush after each; wait to quiescence, then
  `nodetool compact`. Total ≈ 32 × 21 MiB ≈ 670 MiB unique.

Stress command for a pass (keyspace `$KS`, parameter `$P`):
```
$RUN/src/tools/bin/cassandra-stress write n=20000 no-warmup cl=ONE \
  -pop seq=$LO..$HI -col n=FIXED\(1\) size=FIXED\(1024\) -rate threads=16 -node 127.0.0.1 \
  -schema keyspace=$KS "replication(factor=1)" "compaction(strategy=UnifiedCompactionStrategy,scaling_parameters=$P)"
$RUN/src/bin/nodetool flush $KS standard1
```

**B3d. Observables and instruments.** Sampler every 5 s during every phase, appended to
`$RUN/samples-$KS.csv`:
```
while true; do
  ts=$(date +%s)
  st=$($RUN/src/bin/nodetool tablestats $KS.standard1)
  cnt=$(echo "$st" | awk -F: '/SSTable count/{gsub(/ /,"",$2);print $2}')
  live=$(echo "$st" | awk -F: '/Space used \(live\)/{gsub(/ /,"",$2);print $2}')
  du=$(du -sb $RUN/data/$KS 2>/dev/null | cut -f1)
  pend=$($RUN/src/bin/nodetool compactionstats | awk '/pending tasks/{print $3}')
  echo "$ts,$cnt,$live,$du,$pend"
  sleep 5
done >> $RUN/samples-$KS.csv
```
(start with `&`, record its PID, kill it at phase end). Also: `S` = live bytes after the first flush;
per-level counts and `maxOverlap` from `grep 'Level .* sstables .* max overlap' $RUN/src/logs/debug.log`.
Not observable directly: the in-heap `Level` lists (see B2).

**B3e. Procedure.** For each `P` in `L4 T4 T8 T16` (`KS=ucs_$(echo $P|tr A-Z a-z)`):

1. `nodetool setcompactionthroughput 1`; start sampler.
2. Phase A: run the 32 overwrite passes (`LO=1 HI=20000`) with a flush after each; record the time
   of each flush. Stop sampler; save the debug-log level lines for this keyspace.
3. Phase B: start sampler; `nodetool setcompactionthroughput 0`; wait to quiescence; record final
   `SSTable count` and live bytes. Then positive control: `nodetool compact $KS standard1`, wait to
   quiescence, record again. Stop sampler.
4. `cqlsh -e "DROP KEYSPACE $KS"`; confirm `du -sb $RUN/data/$KS` is gone or ~0.
5. Phase C with `KS=${KS}_u`: throughput 0; start sampler; 32 distinct-key passes with flushes; wait to
   quiescence; record; `nodetool compact $KS standard1`; record; stop sampler; drop keyspace.

Finally `nodetool setcompactionthroughput 64`, stop the node (B4).

**B3f. Predictions.** (S ≈ 21 MiB, read from the first flush.)

- Phase A, every `t`: peak `SSTable count` > t − 1; for T16 it reaches ≈ 32 (all flushes live while
  the first 16-input compaction runs); for L4/T4/T8 it exceeds `t` by several (≥ 2t at its peak).
  Peak live bytes ≈ peak count × S (±20%), i.e. well above (t − 1) × S for every `t`. Debug log shows
  level-0 `sstables` and `max overlap` values > t while compactions are queued. No write errors or
  stress throughput drop attributable to `t`.
- Phase B (overwrite, quiescent): per level, overlap ≤ t − 1; live bytes between S and ≈ t × S. This is
  the trigger's eventual target, ordered by `t` (L4 smallest, T16 largest) — expected under the claim,
  because it holds only after compaction catches up. After `nodetool compact` (positive control):
  live bytes ≈ S (±20%) for every `t`.
- Phase C (insert-only): during load, count grows with flushes; at quiescence and again after
  `nodetool compact`, live bytes ≈ 32 × S ≈ 670 MiB, equal across the four `t` within ±10% (after major
  compaction within ±5%).

**B3g. Readings.**

| Observation | Meaning |
|---|---|
| Phase A peak count > t − 1 and peak bytes > (t − 1) × S for all four `t`; Phase C quiescent bytes equal across `t` | usage does not follow the constraint as a cap — claim **confirmed** (with the control row below) |
| `nodetool compact` drops Phase B live bytes from > S to ≈ S, and Phase A bytes rise per flush | positive control moved: the instrument sees disk change where a mechanism (major compaction merging overlapping copies) does bind |
| Phase A count stays ≤ t − 1 throughout (writes/flushes stall, or compaction runs synchronously with flush), or bytes plateau at ≈ (t − 1) × S while passes continue | `t` caps disk — claim **refuted** |
| Phase C quiescent or post-compaction bytes differ across `t` by > 10% in proportion to `t` | disk follows the knob for unique data — claim **refuted** |
| Phase B quiescent bytes ordered by `t` | expected trigger effect (space amplification knob at quiescence), not a cap; does not refute |
| Phase A count never exceeds t − 1 because compaction kept up (e.g. throttle not applied), or `nodetool compact` did not reduce bytes | limit not reached / control did not move — **not confirmed**; check `nodetool getcompactionthroughput`, `concurrent_compactors`, rerun |

**B3h. Controls.**

- Flushes are explicit (heap 2 GiB, 512 MiB memtable space), so sstable count is known per pass.
- `nodetool getcompactionthroughput` recorded at each phase start proves the throttle state.
- Fresh keyspace per `t`, dropped before the next, so no carry-over; `auto_snapshot: false` so drops free space.
- Positive control (`nodetool compact`) on the same data shows the instrument and disk respond to a
  binding mechanism.
- Insert-only Phase C separates data volume from overwrite redundancy.
- Debug-log level lines confirm the `threshold` the strategy used (`Level.toString` prints `T: <t>`, :689-700,
  at TRACE; the DEBUG lines give sstables and max overlap per level).

**B4. Risks and cleanup.**

- Disk: Phase A peak ≈ 32 × 21 MiB ≈ 0.7 GiB plus compaction temporaries; Phase C ≈ 0.7 GiB plus up to
  100% for the major compaction; commit log capped at 2 GiB. Everything is under `$RUN` on local disk;
  never point any directory at shared storage.
- Unit tier: runs inside `ant testsome` in `$WORK/src`; the shared `~/cassandra-5.0.9` is untouched.
- Cleanup: kill the sampler loops (`kill <pid>`); `$RUN/src/bin/nodetool drain; kill $(cat $RUN/cassandra.pid)`;
  verify none left: `pgrep -f CassandraDaemon` and `pgrep -f cassandra-stress` print nothing (only for
  this user's processes: `pgrep -u $USER ...`); `rm -rf $RUN/data $RUN/commitlog $RUN/hints $RUN/saved_caches $RUN/cdc_raw`;
  remove `$WORK` and `$RUN` when results are copied out.

## C. Sources read

- src/java/org/apache/cassandra/db/compaction/UnifiedCompactionStrategy.java
- src/java/org/apache/cassandra/db/compaction/unified/Controller.java
- src/java/org/apache/cassandra/config/CassandraRelevantProperties.java (lines 605-660)
- src/java/org/apache/cassandra/db/compaction/UnifiedCompactionStrategy.md
- src/java/org/apache/cassandra/db/compaction/CompactionStrategyManager.java (grep, :478-499)
- src/java/org/apache/cassandra/db/compaction/ShardManager.java (grep)
- src/java/org/apache/cassandra/utils/Overlaps.java (grep, assignOverlapsIntoBuckets)
- src/java/org/apache/cassandra/utils/ObjectSizes.java (grep, jamm usage)
- src/java/org/apache/cassandra/tools/nodetool/SetCompactionThroughput.java (grep)
- test/unit/org/apache/cassandra/db/compaction/UnifiedCompactionStrategyTest.java
- tools/stress/src/org/apache/cassandra/stress/settings/OptionCompaction.java
- tools/stress/src/org/apache/cassandra/stress/settings/SettingsSchema.java (grep)
- conf/cassandra.yaml (grep), conf/cassandra-env.sh (grep), build.xml (grep)
- https://docs.oracle.com/en/java/javase/11/docs/api/java.base/java/util/ArrayList.html
- https://cwiki.apache.org/confluence/display/CASSANDRA/CEP-26%3A+Unified+Compaction+Strategy

## D. Stage-4 feedback

none yet
