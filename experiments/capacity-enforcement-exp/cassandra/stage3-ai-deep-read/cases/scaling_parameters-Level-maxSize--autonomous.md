# scaling_parameters (UCS level maximum density, `Level.max`) — verification solution  <!-- file: cases/scaling_parameters-Level-maxSize--autonomous.md -->

| Field | Value |
|---|---|
| Entry pointer | the given line (capacity-set), **linked**: [`UnifiedCompactionStrategy.java:564`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/compaction/UnifiedCompactionStrategy.java#L564) — `this.max = maxSize;` in the `Level` constructor |
| Pinned source | `cassandra-5.0.9` |
| Session / date | claude-opus-5-5, Claude Code 2.1.330, 2026-11-24 (autonomous) |
| Estimate | `negative`. `Level.max` is the upper density boundary of a UCS level, derived from the fan factor F of `scaling_parameters` and the flush size. It is only used to sort SSTables into levels. An SSTable at or above it is moved to the next level, and levels are created on demand with no upper limit. Nothing is refused, split or throttled when the boundary is crossed, so it bounds neither disk nor heap. |
| Ground | `max` is read in exactly two places, [`UnifiedCompactionStrategy.java:473`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/compaction/UnifiedCompactionStrategy.java#L473) and `:488`. Both are classification branches (`level.add(candidate)` or open the next level), and the loop at `:482-496` (`while (true)`) always ends by placing the SSTable. UCS also reports `getMaxSSTableBytes() == Long.MAX_VALUE` (`:399-402`). On-disk size follows the data written. The level boundaries only change how SSTables are grouped for compaction. |

## A. Constraint trace

**A1. The constraint.**
- **Name:** `scaling_parameters`, a UCS table compaction option. It is declared as
  [`Controller.java:51`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/compaction/unified/Controller.java#L51)
  (`SCALING_PARAMETERS_OPTION = "scaling_parameters"`). Its default comes from the JVM property
  `unified_compaction.scaling_parameters`, default `"T4"`
  (`Controller.java:52-53`, `src/java/org/apache/cassandra/config/CassandraRelevantProperties.java:612`).
  It sets the per-level scaling parameter W, from which fanout F and threshold T are derived.
  At the given line, F becomes the level's maximum density:
  `this.max = maxSize`, with `maxSize = controller.getMaxLevelDensity(index, minDensity)`
  (`UnifiedCompactionStrategy.java:486-487`, `:467-469`).
- **Kind:** configuration entry, set per table. The default comes from a JVM property. The derived per-level value is computed at runtime.
- **Derivation:**
  - Parsing is in `UnifiedCompactionStrategy.java:116-130`: `N` gives W=0, `Lf` gives W=2-f, `Tf` gives W=f-2, and an integer gives W as written. The regex is at `:73`.
  - F = `2+W` for W≥0 and `2-W` for W<0 (`:106-109`).
  - Level 0: `max = floor(base/coverage · F · o)` (`:467`, `Controller.java:668-671`).
    - `base = max(1 MiB, flushSize) · (1 − 0.9/F)` (`Controller.java:655-666`).
    - `flushSize` is `flush_size_override` if > 0, otherwise the observed `flushSizeOnDisk` metric rounded up to a whole MiB (`Controller.java:379-392`).
    - `coverage = shardManager.localSpaceCoverage()`.
    - `o` is the survival factor, fixed at `unified_compaction.survival_factor` = 1 (`Controller.java:113-118`, `:362-368`).
  - Level i>0: `min = previous max`, `max = floor(min · F_i · o)` (`:485-487`).
- **Unit:** bytes per unit of token-space share (density = `onDiskLength / rangeSpanned`, `ShardManager.java:134-137`).
- **Default:** T4 (F=4), with flush size observed. For example, with a 64 MiB flush: L0 max 208,037,478 B, L1 832,149,912 B, L2 3,328,599,648 B, and so on.
- **How it is set:**
  - `ALTER TABLE … WITH compaction = {'class':'UnifiedCompactionStrategy','scaling_parameters':'T4', …}` (validated by `Controller.validateOptions`, `Controller.java:468-470`).
  - The node-wide default is `-Dunified_compaction.scaling_parameters`, or `default_compaction` in yaml (`conf/cassandra_latest.yaml:1191-1193`).
  - A table ALTER takes effect without a restart because the strategy is rebuilt with a new `Controller.fromOptions` (`Controller.java:408-458`). The JVM-property default needs a restart.

**A2. What it caps.** The intended resource is disk. The quantity compared against `max` is an SSTable's
density (`shardManager.density(candidate)`, `UnifiedCompactionStrategy.java:472`). The comparison does not cap
disk, heap or the SSTable's size: it only chooses which level index an SSTable is grouped in. Compaction
triggering is decided afterwards, per level, by the overlap count vs threshold T (`:671`). The per-pick SSTable
count is decided by fanout and `max_sstables_to_compact` (`:761-800`).

**A3. Mechanism.**
1. `getNextCompactionPick` (`UnifiedCompactionStrategy.java:325-344`) → `chooseCompactionPick` (`:369-390`) → `formLevels(suitable)` (`:461-506`).
2. The SSTables are sorted by density (`:465`). Level 0 is built with `min=0` and `max=getMaxLevelDensity(0, base/coverage)` (`:467-469`). The constructor stores it at the given line [`:564`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/compaction/UnifiedCompactionStrategy.java#L564).
3. For each SSTable, [`if (density < level.max)`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/compaction/UnifiedCompactionStrategy.java#L473) adds it to the current level (`:475`).
4. Otherwise the current level is closed and appended, even when empty (`:479-480`). A `while (true)` loop then opens level `index+1` with `min = old max` and `max = floor(min·F)` (`:482-487`). It stops when [`density < level.max`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/compaction/UnifiedCompactionStrategy.java#L488) holds, then adds the SSTable (`:490`); else it appends another empty level (`:494`).
5. **Outcome when the limit is reached:** the SSTable moves to a higher level. There is no rejection, no split, no throttle, no log and no metric.
6. **Bypass/overshoot:** there is no upper level. `MAX_LEVELS = 32` (`:70`) is only the initial capacity of the `levels` list (`:464`) and is not enforced: with F=2, an SSTable of density 2^62 B forms 43 levels. The only stop is that the loop is unbounded by design. It terminates because `max` grows ×F each step; for F≥2 it always grows.
7. `max` is also printed by `Level.toString` (`:689-700`) via `complete()` at TRACE (`:577-581`).

**A4. Other consumers.** Things that do act on disk or heap in this area, outside `Level.max`:
- `threshold` (`:561`, compared at `:671`) decides whether a level compacts at all, so it governs space amplification of overwritten data and SSTable count.
- `max_sstables_to_compact` and fanout limit the pick size (`:765-800`), and so the transient compaction space.
- `target_sstable_size`, `base_shard_count`, `sstable_growth` and `min_sstable_size` decide output SSTable splitting (`Controller.getNumShards`, `Controller.java:264-355`). This is the only real per-SSTable size bound in UCS.
- Node-wide: `min_free_space_per_drive` and `max_space_usable_for_compactions_in_percentage` (`src/java/org/apache/cassandra/config/Config.java:338-344`).
- The data-disk-usage guardrail (`data_disk_usage_percentage_fail_threshold` / `data_disk_usage_max_disk_size`, `conf/cassandra.yaml:2191-2210`, enforced in `ModificationStatement.java:285-301`).

Heap: each `Level` is a small object. Its SSTable list is pre-sized by `threshold` at `:562` (`new ArrayList<>(threshold)`), the adjacent capacity-set line. That pre-size is not a cap either: the list grows past it. It does scale linearly with W, so an extreme `scaling_parameters` (e.g. `T100000000`) would pre-allocate about 400 MB per `Level` on every pick. That is a separate observation, not tested here.

**A5. Evidence beyond the source.**
- UCS design doc in-tree, `src/java/org/apache/cassandra/db/compaction/UnifiedCompactionStrategy.md:60-75` (level = ⌊log_f(s/m)⌋) and `:139` ("the upper density limit for a level is f times the lower"). It describes levels as a grouping, not a limit.
- Operator docs, `doc/modules/cassandra/pages/managing/operating/compaction/ucs.adoc:150-175` (level table with "Max SSTable size" s_f·f^(L+1)) and `:197-205` (an SSTable is "promoted" to the next level when it reaches the size).
- CEP-26: https://cwiki.apache.org/confluence/display/CASSANDRA/CEP-26%3A+Unified+Compaction+Strategy (cited at `UnifiedCompactionStrategy.java:64`); CASSANDRA-18397 (`CHANGES.txt:473`), https://issues.apache.org/jira/browse/CASSANDRA-18397.
- Existing test `test/unit/org/apache/cassandra/db/compaction/UnifiedCompactionStrategyTest.java:220-299` (`testGetBucketsDifferentWsUniqueArena`). It uses mocked SSTables and checks the level count for given W, which shows levels are formed as needed.

## B. Verification solution

**B1. Claim under test.** `Level.max`, the level maximum density set from `scaling_parameters` at
`UnifiedCompactionStrategy.java:564`, does **not** bound the size, density or total on-disk bytes of a table's SSTables.
An SSTable whose density exceeds a level's max is placed in a higher, on-demand level, with no rejection or split.
Total live bytes follow the data written, independent of F, while a known disk cap (the data-disk-usage guardrail) visibly stops growth under the same workload.

### B2. Unit tier

**B2a. Environment and build.**
- Linux, JDK 11, Ant. Copy the tree to local disk first: `rsync -a <shared>/cassandra-5.0.9/ /local/ucs-unit/cassandra-5.0.9/`. Never build in the shared copy.
- `cd /local/ucs-unit/cassandra-5.0.9 && ant jar build-test` (`ant realclean` first if a stale `build/` was copied).
- Test source: `test/unit/org/apache/cassandra/db/compaction/UCSLevelMaxProbeTest.java` in the local copy. It is in the same package as `Level`, so it can read the package-private `min`/`max`/`index`/`fanout`.
- The test runs under the standard `testsome` JVM options from `build.xml`.

Test source (subclasses the existing test to reuse its `setUp`, `cfs`/`dataTracker` mocks and `mockSSTable`; only the two new methods are run):

```java
package org.apache.cassandra.db.compaction;

import java.nio.ByteBuffer;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;

import org.junit.Test;
import org.mockito.Mockito;

import org.apache.cassandra.db.BufferDecoratedKey;
import org.apache.cassandra.db.DecoratedKey;
import org.apache.cassandra.db.compaction.unified.Controller;
import org.apache.cassandra.dht.IPartitioner;
import org.apache.cassandra.io.sstable.format.SSTableReader;
import org.apache.cassandra.utils.Overlaps;

import static org.mockito.ArgumentMatchers.anyDouble;
import static org.mockito.ArgumentMatchers.anyInt;
import static org.mockito.Mockito.when;

public class UCSLevelMaxProbeTest extends UnifiedCompactionStrategyTest
{
    private Controller controller(int W, int maxToCompact)
    {
        Controller c = Mockito.mock(Controller.class);
        when(c.getScalingParameter(anyInt())).thenReturn(W);
        when(c.getFanout(anyInt())).thenCallRealMethod();
        when(c.getThreshold(anyInt())).thenCallRealMethod();
        when(c.getSurvivalFactor(anyInt())).thenReturn(1.0);
        when(c.getFlushSizeBytes()).thenReturn(1L << 20);                 // flush size 1 MiB
        when(c.getBaseSstableSize(anyInt())).thenCallRealMethod();        // real Controller.java:665
        when(c.getMaxLevelDensity(anyInt(), anyDouble())).thenCallRealMethod(); // real Controller.java:668
        when(c.getNumShards(anyDouble())).thenReturn(1);
        when(c.maxSSTablesToCompact()).thenReturn(maxToCompact);
        when(c.maxConcurrentCompactions()).thenReturn(1000);
        when(c.maxThroughput()).thenReturn(Double.MAX_VALUE);
        when(c.overlapInclusionMethod()).thenReturn(Overlaps.InclusionMethod.TRANSITIVE);
        when(c.random()).thenCallRealMethod();
        return c;
    }

    private DecoratedKey[] fullRange()
    {
        IPartitioner p = cfs.getPartitioner();
        return new DecoratedKey[]{ new BufferDecoratedKey(p.getMinimumToken(), ByteBuffer.allocate(0)),
                                   new BufferDecoratedKey(p.getMaximumToken(), ByteBuffer.allocate(0)) };
    }

    @Test
    public void probeLevelMax()
    {
        for (int W : new int[]{ 0, 2, 14 })           // F = 2, 4, 16
        {
            setUp(1);
            UnifiedCompactionStrategy s = new UnifiedCompactionStrategy(cfs, new HashMap<>(), controller(W, 1000));
            DecoratedKey[] r = fullRange();
            List<SSTableReader> in = new ArrayList<>();
            double inBytes = 0;
            for (int k = 0; k <= 62; k++)             // sizes 1 B .. 2^62 B (4 EiB), one SSTable each
            {
                long size = 1L << k;
                in.add(mockSSTable(size, 1000L + k, r[0], r[1]));
                inBytes += size;
            }
            s.addSSTables(in);
            dataTracker.addInitialSSTables(in);

            List<UnifiedCompactionStrategy.Level> levels = s.getLevels();
            int placed = 0, violations = 0;
            double placedBytes = 0, maxDensity = 0;
            for (UnifiedCompactionStrategy.Level l : levels)
            {
                for (SSTableReader x : l.getSSTables())
                {
                    double d = s.getShardManager().density(x);
                    if (!(d >= l.min && d < l.max)) violations++;
                    placed++; placedBytes += x.onDiskLength(); maxDensity = Math.max(maxDensity, d);
                }
                System.out.printf("PROBE W=%d F=%d T=%d level=%d min=%.0f max=%.0f n=%d%n",
                                  W, l.fanout, l.threshold, l.index, l.min, l.max, l.getSSTables().size());
            }
            UnifiedCompactionStrategy.Level top = levels.get(levels.size() - 1);
            System.out.printf("PROBE-SUM W=%d levels=%d placed=%d/%d bytes=%.0f/%.0f violations=%d maxDensity=%.0f topMin=%.0f topMax=%.0f%n",
                              W, levels.size(), placed, in.size(), placedBytes, inBytes, violations, maxDensity, top.min, top.max);
        }
    }

    @Test
    public void controlPickCap()
    {
        for (int cap : new int[]{ 1000, 8 })
        {
            setUp(1);
            UnifiedCompactionStrategy s = new UnifiedCompactionStrategy(cfs, new HashMap<>(), controller(2, cap)); // F=T=4
            DecoratedKey[] r = fullRange();
            List<SSTableReader> in = new ArrayList<>();
            for (int i = 0; i < 12; i++)
                in.add(mockSSTable(1L << 20, 1000L + i, r[0], r[1]));                 // 12 x 1 MiB, all overlapping, L0
            s.addSSTables(in);
            dataTracker.addInitialSSTables(in);
            UnifiedCompactionStrategy.Level l0 = s.getLevels().get(0);
            UnifiedCompactionStrategy.CompactionPick pick =
                l0.getCompactionPick(new UnifiedCompactionStrategy.SelectionContext(s.getController()));
            System.out.printf("CONTROL cap=%d l0n=%d l0max=%.0f pick=%d%n",
                              cap, l0.getSSTables().size(), l0.max, pick == null ? 0 : pick.size());
        }
    }
}
```

**B2b. Knobs.**
- W ∈ {0, 2, 14}, i.e. `N`, `T4` and `T16`, F = 2, 4, 16. These cover the minimum fanout, the default, and a wide one. Each changes every level max by a different factor.
- Set them through the mocked `Controller.getScalingParameter`, with the real `getFanout`, `getThreshold`, `getBaseSstableSize` and `getMaxLevelDensity`.
- Flush size is fixed at 1 MiB so the arithmetic is exact.
- Control: `max_sstables_to_compact` ∈ {1000, 8}.

**B2c. Workload.** 63 mocked SSTables of sizes 2^0 … 2^62 B, all spanning the full token range, so density = size and `rangeSpanned`≈1 (`ShardManager.java:104-120`).
- L0 max = floor(1 MiB·(1−0.9/F)·F): 1,153,433 (F=2), 3,250,585 (F=4), 15,833,497 (F=16).
- The largest SSTable (2^62 ≈ 4.61e18 B) exceeds L0 max by a factor of about 4e12. That forces log_F(4e12) further levels: 42 above L0 for F=2, past `MAX_LEVELS`=32.
- Total input is 2^63−1 B (summed as a double).
- Control: 12 overlapping 1 MiB SSTables (all below the F=4 L0 max of 3,250,585) give overlap 12 ≥ T=4.

**B2d. Observables and instruments.**
- `System.out` lines `PROBE`, `PROBE-SUM` and `CONTROL`. Ant stores them in `build/test/output/TEST-org.apache.cassandra.db.compaction.UCSLevelMaxProbeTest-<methods>.xml` (`<system-out>`).
- The test measures the check's own operand (density from the strategy's own `ShardManager`), each level's `min`/`max`, the placement count and bytes, and the `CompactionPick` size.
- Not observable: real disk. Heap is not measured because `Level` objects are negligible.

**B2e. Procedure.**
1. Copy the tree and build as in B2a.
2. Write the file above into the local copy's `test/unit/org/apache/cassandra/db/compaction/`.
3. Run `ant testsome -Dtest.name=org.apache.cassandra.db.compaction.UCSLevelMaxProbeTest -Dtest.methods=probeLevelMax,controlPickCap`.
4. Extract the results with `grep -oE '(PROBE|PROBE-SUM|CONTROL)[^<]*' build/test/output/TEST-org.apache.cassandra.db.compaction.UCSLevelMaxProbeTest-*.xml`.
5. Check that the run started no JVM that is still alive: `pgrep -f UCSLevelMaxProbeTest` must print nothing.

**B2f. Predictions** (computed from the formulas in A1 before any run):

| W (F) | L0 max | levels.size() | SSTables per level | top level min / max |
|---|---|---|---|---|
| 0 (2) | 1,153,433 | 43 | L0: 21 (2^0..2^20); L1..L42: 1 each | 2,536,425,990,721,110,016 / 5,072,851,981,442,220,032 |
| 2 (4) | 3,250,585 | 22 | L0: 22 (2^0..2^21); L1..L20: 2 each; L21: 1 | 3,574,056,004,574,248,960 / 14,296,224,018,296,995,840 |
| 14 (16) | 15,833,497 | 11 | L0: 24 (2^0..2^23); L1..L9: 4 each; L10: 3 | 1,088,069,628,741,025,792 / 17,409,114,059,856,412,672 |

- For all W: `placed=63/63`, `bytes` equal to the input (≈9.223e18), and `violations=0`.
- `maxDensity` = 4,611,686,018,427,387,904 (2^62) in every case. It is larger than every level max except the top one, which was created on demand.
- The level count follows ⌈log_F(2^62 / L0max)⌉+1.
- Control: `cap=1000 → pick=12`; `cap=8 → pick=8`. With 12 > F=4 and 12 ≤ F·F=16, the cap applies at `:782-785`.
- Small (±1) differences in level maxes from double rounding are acceptable. A different placement count is not.

**B2g. Readings.**

| Observation | Meaning |
|---|---|
| `placed`=63 and bytes equal to the input for all W; levels count as predicted (43/22/11, including >32); `violations=0`; control pick 12 vs 8 | Claim confirmed at unit level: `max` only classifies, and the instrument does see a binding cap (`max_sstables_to_compact`) |
| Any SSTable missing from the levels, an exception or loop cap when density exceeds a max, or `levels.size()` stuck at 32 for F=2 | Claim refuted: the level max (or `MAX_LEVELS`) acts as a limit |
| Placed bytes differ by W | Claim refuted: the boundary drops or alters data accounting |
| `violations>0` | Trace wrong (the operand differs from `onDiskLength/span`); re-derive density before concluding |
| Control pick = 12 for both caps | Not confirmed: the harness does not exercise a binding limit, so the reading is inconclusive |
| `maxDensity` never above L0 max (workload did not reach the boundary) | Not confirmed: the limit was never reached |

**B2h. Controls.**
- The same SSTables are used across three F values. The level maxes change, but placement count and bytes must not.
- The positive control (`max_sstables_to_compact`) uses the same harness, mocks and strategy instance type, so a harness that cannot show a cap is detected.
- The full-range keys make density = size, so the boundary arithmetic can be checked by hand.
- The real `getMaxLevelDensity` and `getBaseSstableSize` are used (not stubs), so the tested `max` is the production value.

### B3. Cluster tier

**B3a. Environment and build.**
- Nodes and build:
  - One Linux node, JDK 11, Ant, with at least 15 GiB free on a local disk (`$RUN=/local/ucs-run`). Nothing goes on shared storage.
  - Build from a local copy: `rsync -a <shared>/cassandra-5.0.9/ $RUN/cassandra-5.0.9/ && cd $RUN/cassandra-5.0.9 && ant jar` (cassandra-stress is built by `ant jar`; if `tools/bin/cassandra-stress` fails, run `ant stress-build`).
- `conf/cassandra.yaml` (local copy):
  - `cluster_name: ucs-levelmax`, `num_tokens: 16`, listen/rpc on `127.0.0.1`.
  - `data_file_directories: [$RUN/data]`, `commitlog_directory: $RUN/commitlog`, `hints_directory: $RUN/hints`, `saved_caches_directory: $RUN/saved_caches`, `cdc_raw_directory: $RUN/cdc`.
  - `commitlog_total_space: 1024MiB`, `memtable_heap_space: 256MiB`, `concurrent_compactors: 2`, `compaction_throughput: 0MiB/s` (unthrottled, for short runs).
- `conf/jvm11-server.options` / env: `-Xms2G -Xmx2G`. JMX stays local on 7199.

**B3b. Knobs.**
- Run A: `scaling_parameters` = `T4` (F=4). Run B: `T16` (F=16). Each run starts on a fresh data directory.
- Common table options:
  - `'flush_size_override':'64MiB'` fixes the level base, so the level maxes are deterministic.
  - `'base_shard_count':'1'` and `'sstable_growth':'1'` give fixed one-shard mode (`Controller.java:291-298`), so no output splitting interferes.
  - `compression = {'enabled':'false'}`.
- Resulting level maxes:
  - T4: L0 208,037,478; L1 832,149,912; L2 3,328,599,648; L3 13,314,398,592 B.
  - T16: L0 1,013,343,846; L1 16,213,501,536 B.
- Positive-control run P: `T4` as in A, plus the guardrail:
  - `data_disk_usage_max_disk_size: 2GiB`, `data_disk_usage_percentage_warn_threshold: 40`, `data_disk_usage_percentage_fail_threshold: 50`.
  - `authenticator: PasswordAuthenticator`, and a non-superuser role. The guardrail is skipped for superusers and for AllowAll auth: `Guardrail.java:93-96`, `ClientState.java:594-605`.
  - JVM option `-Dcassandra.disk_usage.monitor_interval_ms=1000` (`CassandraRelevantProperties.java:200`).

**B3c. Workload.**
- `cassandra-stress` unique-key writes: one 1024-B value per row, about 1.06 KB on disk per row uncompressed. No overwrites, so the live bytes equal the data written.
- Checkpoints at 1 M, 2 M and 4 M rows give about 1.05, 2.1 and 4.2 GB.
- 4.2 GB exceeds T4's L2 max (3.33 GB) and T16's L0 max (1.01 GB), so after major compaction the single SSTable must sit above those boundaries.
- Duration: about 10–20 min of writes per run plus compaction.

**B3d. Observables and instruments.**
- Disk:
  - `nodetool tablestats keyspace1.standard1`: "Space used (live)", "Space used (total)", "SSTable count".
  - `du -sb $RUN/data/keyspace1`.
  - Per-SSTable sizes: `ls -l $RUN/data/keyspace1/standard1-*/*-Data.db`.
- Levels: `nodetool setlogginglevel org.apache.cassandra.db.compaction.UnifiedCompactionStrategy TRACE`, then grep `logs/debug.log` and `logs/system.log` for `Level: W:` lines. They give index, min, max and SSTable count per level (`UnifiedCompactionStrategy.java:577-581`, `:689-700`).
- Write outcome: stress summary "Total errors" and the op rate.
- Sampling: the readings at each checkpoint after quiescence (`nodetool compactionstats` shows 0 pending, polled every 10 s), plus `du` every 30 s during writes, in a background loop that is killed at the end.
- Not directly observable: in-memory level objects (only through the TRACE log). Exact density uses span≈1 because the SSTables cover the whole ring on a single node.

**B3e. Procedure (run A, then B with `T16`).**
1. `export RUN=/local/ucs-run; mkdir -p $RUN/{data,commitlog,hints,saved_caches,cdc}`. Edit the yaml as in B3a. Start the node with `cd $RUN/cassandra-5.0.9 && bin/cassandra -p $RUN/c.pid`, then wait for `bin/nodetool status` to show `UN`.
2. Create the schema with `tools/bin/cassandra-stress write n=1 cl=ONE -col n=FIXED\(1\) size=FIXED\(1024\) -schema replication\(factor=1\) -rate threads=1`.
3. Configure the table with `bin/cqlsh -e "ALTER TABLE keyspace1.standard1 WITH compression = {'enabled':'false'} AND compaction = {'class':'UnifiedCompactionStrategy','scaling_parameters':'T4','flush_size_override':'64MiB','base_shard_count':'1','sstable_growth':'1'}; TRUNCATE keyspace1.standard1;"`
4. Turn on level logging with `bin/nodetool setlogginglevel org.apache.cassandra.db.compaction.UnifiedCompactionStrategy TRACE`. Start `(while true; do date +%s; du -sb $RUN/data/keyspace1; sleep 30; done) > $RUN/du.log & echo $! > $RUN/du.pid`.
5. For each range `1..1000000`, `1000001..2000000` and `2000001..4000000`:
   1. Run `tools/bin/cassandra-stress write n=<count> cl=ONE -pop seq=<range> -col n=FIXED\(1\) size=FIXED\(1024\) -rate threads=32 -errors ignore`, then `bin/nodetool flush keyspace1 standard1`.
   2. Poll `bin/nodetool compactionstats` until there are 0 pending tasks.
   3. Record `tablestats`, the `ls -l *-Data.db` listing, and the last `Level: W:` block from the log.
6. Run `bin/nodetool compact keyspace1 standard1`, wait for it to finish, then record the same readings again (expect one Data.db).
7. Clean up:
   - `kill $(cat $RUN/du.pid)` and `bin/nodetool stopdaemon`.
   - Confirm that `pgrep -f CassandraDaemon` and `pgrep -f cassandra-stress` print nothing.
   - Run `rm -rf $RUN/{data,commitlog,hints,saved_caches,cdc}/*`.
8. Run B: repeat steps 1–7 with `'scaling_parameters':'T16'`.
9. Positive control P:
   1. Use the yaml of run A plus the B3b guardrail and auth settings and the JVM option. Start on a fresh data directory and wait about 15 s for the default `cassandra` role.
   2. Run `bin/cqlsh -u cassandra -p cassandra -e "CREATE ROLE stressuser WITH PASSWORD='stress' AND LOGIN=true;"`.
   3. Do steps 2–3 with `-mode native cql3 user=cassandra password=cassandra` for the schema step only.
   4. Run one stress write of `n=4000000 -pop seq=1..4000000` with `-mode native cql3 user=stressuser password=stress -errors ignore`.
   5. Record the readings and clean up as in step 7.

**B3f. Predictions.**
- **Runs A and B:**
  - Stress "Total errors" = 0 in every phase.
  - "Space used (live)" ≈ 1.0–1.15, 2.0–2.3 and 4.0–4.6 GB at the three checkpoints. The ratios are 1:2:4 within ±10%, and A and B agree within ±5% at each checkpoint.
- **After `nodetool compact`:**
  - Exactly one Data.db of 4.0–4.6 GB in both runs.
  - TRACE shows it in `index: 3` (min 3.1 GiB, max 12.4 GiB) for T4, and in `index: 1` (min 966 MiB, max 15.1 GiB) for T16. Lower levels are empty.
  - The SSTable is larger than every lower level's max (T4: L0–L2; T16: L0), and nothing refused it.
- **During writes**, SSTables above L0 max appear in A (> 208 MB) before the 2 M checkpoint, because tiered merges of F=4 L0 SSTables produce them. Peak `du` during compaction may reach up to about 2× live. That is transient compaction space, not governed by `max`.
- **Run P:**
  - Writes by `stressuser` start failing once data-dir usage plus memtables reaches about 1 GiB (50% of 2 GiB), within about 1 s plus one flush. That is around row 0.9–1.1 M.
  - "Total errors" > 0 (about 3 M), and "Space used (live)" plateaus at about 0.9–1.3 GB.
- **What would show the claim wrong:**
  - Write errors, or live bytes plateauing below the data written, in A or B.
  - The major-compaction output split at a size near a level max (for example several SSTables each < 3.33 GB in A).
  - Live bytes that differ between A and B by more than the measurement noise in a way tied to F.

**B3g. Readings.**

| Observation | Meaning |
|---|---|
| A and B: 0 errors, live ≈ 1:2:4 with checkpoints, A≈B; single compacted SSTable above lower level maxes, in level 3 (T4) / 1 (T16); P: errors and plateau near 1 GiB | Claim confirmed: usage does not follow `Level.max`, and the workload moves usage where a cap is known to bind |
| A or B: live bytes plateau at or near a level max while writes are acknowledged, or writes fail when an SSTable crosses a level max | Claim refuted: the level max acts as a disk limit |
| Major compaction output split into pieces each just under a level max, with sharding fixed at 1 | Claim refuted: the boundary bounds SSTable size |
| A and B live bytes differ systematically with F (e.g. > 10%) after quiescence | Claim refuted in part: the level structure changes retained bytes; investigate before concluding |
| Data never exceeded T4 L2 max / T16 L0 max (for example stress wrote less than planned) | Not confirmed: boundary not reached |
| P shows no errors and no plateau | Not confirmed: the positive control did not bind (check role is non-superuser, monitor interval, yaml), so the A/B reading is inconclusive |

**B3h. Controls.**
- The same workload, row count and node config are used in A and B, and only F changes. The level maxes differ by about 5× at L0, while live bytes must not.
- Unique keys, no TTL and no deletes, so compaction cannot shrink the data. Compression is off, so on-disk size equals data size.
- The fixed one-shard mode removes `target_sstable_size` splitting as an alternative explanation for SSTable sizes.
- The positive control P uses the same table and workload under a known binding disk cap, so it shows the instruments detect a cap.
- Fresh data directories per run, and the `du` of system keyspaces is reported separately (`du -sb $RUN/data/system*`) to separate them from table bytes.

**B4. Risks and cleanup.**
- Disk: up to about 9 GB per run in `$RUN` (4.6 GB live + up to 4.6 GB during compaction) plus ≤ 1 GiB of commitlog. Check `df -h $RUN` ≥ 15 GiB before starting. Nothing is written to shared storage.
- Unit tier: writes only `build/` in the local copy. Afterwards, `rm -rf /local/ucs-unit` if it is no longer needed.
- Processes:
  - After each run, `nodetool stopdaemon` (or `kill $(cat $RUN/c.pid)`), kill the `du` loop, and check that `pgrep -f 'CassandraDaemon|cassandra-stress|UCSLevelMaxProbeTest'` is empty.
  - If any remain, `kill` them, then `kill -9` after 30 s.
- At the end, `rm -rf $RUN`.

## C. Sources read

- src/java/org/apache/cassandra/db/compaction/UnifiedCompactionStrategy.java
- src/java/org/apache/cassandra/db/compaction/unified/Controller.java
- src/java/org/apache/cassandra/db/compaction/ShardManager.java
- src/java/org/apache/cassandra/db/compaction/ShardManagerNoDisks.java
- src/java/org/apache/cassandra/db/compaction/ShardManagerDiskAware.java
- src/java/org/apache/cassandra/config/CassandraRelevantProperties.java
- src/java/org/apache/cassandra/config/Config.java
- src/java/org/apache/cassandra/service/disk/usage/DiskUsageMonitor.java
- src/java/org/apache/cassandra/service/disk/usage/DiskUsageBroadcaster.java
- src/java/org/apache/cassandra/db/guardrails/Guardrails.java
- src/java/org/apache/cassandra/db/guardrails/Guardrail.java
- src/java/org/apache/cassandra/cql3/statements/ModificationStatement.java
- src/java/org/apache/cassandra/service/ClientState.java
- src/java/org/apache/cassandra/service/StorageService.java (line 1236 only)
- src/java/org/apache/cassandra/db/compaction/UnifiedCompactionStrategy.md
- doc/modules/cassandra/pages/managing/operating/compaction/ucs.adoc
- conf/cassandra.yaml
- conf/cassandra_latest.yaml
- CHANGES.txt
- build.xml (testsome target)
- test/unit/org/apache/cassandra/db/compaction/UnifiedCompactionStrategyTest.java
- tools/stress/src/org/apache/cassandra/stress/settings/SettingsSchema.java
- https://cwiki.apache.org/confluence/display/CASSANDRA/CEP-26%3A+Unified+Compaction+Strategy (cited, not fetched)
- https://issues.apache.org/jira/browse/CASSANDRA-18397 (cited, not fetched)

## D. Stage-4 feedback

none yet
