# scaling_parameters (UCS overlap threshold t) — verification solution  <!-- file: cases/scaling_parameters-getBuckets-maxOverlap-2--autonomous.md -->

| Field | Value |
|---|---|
| Entry pointer | the given line (capacity-set place), **linked**: [`UnifiedCompactionStrategy.java:670`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/compaction/UnifiedCompactionStrategy.java#L670): `maxOverlap = Math.max(maxOverlap, overlap.size());`. It sets the operand that the next line compares with the threshold: [`UnifiedCompactionStrategy.java:671`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/compaction/UnifiedCompactionStrategy.java#L671) `if (maxOverlap < threshold) return null;` |
| Pinned source | `cassandra-5.0.9` |
| Session / date | Claude Opus 5.5 (`claude-opus-5-5`), Claude Code 2.1.330, 2026-11-24 |
| Estimate | `negative`. The line computes a **count of overlapping sstables** (read amplification) and compares it with the UCS threshold t, which comes from `scaling_parameters`. The comparison only decides whether a compaction is scheduled. Nothing refuses writes or flushes when the count reaches t, so the count and the bytes behind it grow past t whenever flushing outpaces compaction. For non-overwriting data, on-disk bytes depend on the data volume, not on t. |
| Ground | t is a compaction **trigger** on a sstable count, not a limit on bytes. (1) The operand `maxOverlap` is a number of sstables, not memory or disk ([`:552`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/compaction/UnifiedCompactionStrategy.java#L552), `:670`). (2) The only result of `maxOverlap >= t` is that buckets and a `CompactionPick` are built (`:674-678`, `:597-636`). Below t the method returns `null` (`:671-672`). No write or flush path consults it, and the pick itself is **not** capped at t: it takes all `count` sstables, or a size chosen from the fan factor (`:767-800`). (3) Compaction runs only when an executor slot is free (`CompactionManager.java:244-250`) and at `compaction_throughput`, so the overlap grows without bound while compaction lags. (4) Compaction does not shrink non-overwriting data, so the steady-state bytes are set by the data volume. The one byte-level effect is indirect: on a fully overwriting workload where compaction keeps up, steady-state space amplification is about t. This is a scheduling side effect that disappears once compaction lags. It is measured as a secondary reading (R6/R6b) and is not treated as a cap. |

## A. Constraint trace

**A1. The constraint.**
- **Name.** UCS scaling parameter W, set through the per-table compaction subproperty `scaling_parameters`. It is declared at [`Controller.java:51`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/compaction/unified/Controller.java#L51) (`SCALING_PARAMETERS_OPTION = "scaling_parameters"`). The quantity used at the given line is the per-level **threshold t**, the field `Level.threshold` (`UnifiedCompactionStrategy.java:549`, assigned at `:561` from `Controller.getThreshold(index)`, `Controller.java:243-246`). The formula is `UnifiedCompactionStrategy.thresholdFromScalingParameter(w) = w <= 0 ? 2 : 2 + w` (`UnifiedCompactionStrategy.java:111-114`). The fan factor is `f = w < 0 ? 2 - w : 2 + w` (`:106-109`).
- **Kind.** A per-table configuration entry: a CQL table option inside `compaction = {...}`. Its default comes from a JVM system property.
- **Unit.** None. W is an integer, and t is a **count of sstables** that overlap at some key.
- **Default.** `DEFAULT_SCALING_PARAMETERS = CassandraRelevantProperties.UCS_SCALING_PARAMETER.getString()` (`Controller.java:52-53`). The property is `unified_compaction.scaling_parameters`, default `"T4"` (`CassandraRelevantProperties.java:612`). The value is parsed by `parseScalingParameters` (`Controller.java:720-732`), which splits on commas, and `parseScalingParameter` (`UnifiedCompactionStrategy.java:116-130`): `N` gives w=0, `Lf` gives w=2-f, `Tf` gives w=f-2, and an integer is w itself. `f < 2` is rejected (`:132-137`). Default T4 gives w=2, so t=4 and f=4. Per-level lists are allowed. Levels past the end of the list reuse the last value (`Controller.java:221-227`).
- **How to set it.** `ALTER TABLE ks.t WITH compaction = {'class':'UnifiedCompactionStrategy','scaling_parameters':'T16'}` is validated by `Controller.validateOptions` (`Controller.java:468-470`) and read in `Controller.fromOptions` (`:410`). A schema change reloads the strategy at runtime, so no restart is needed. The node-wide default is `-Dunified_compaction.scaling_parameters=...` (`CassandraRelevantProperties.java:612`; the key is used as is, `:669-674`), which needs a restart. There is no `cassandra.yaml` key and no JMX setter.

**A2. What it caps.** Nominally the read amplification of each density level: the number of sstables that may need to be read for one key. The design doc says so (`UnifiedCompactionStrategy.md:286-295`, "the read amplification that our trigger $t$ aims to control"). The usage-side quantity compared with t is `Level.maxOverlap`, the size of the largest overlap set among the level's non-compacting sstables (`UnifiedCompactionStrategy.java:552-553`, `:660-670`). It is an **sstable count**, not bytes, heap or off-heap. Disk bytes come in only indirectly: (a) for overwrites, each overlapping sstable can hold another copy of the same partitions; (b) the size of a compaction pick, which needs that much extra disk for its output, is chosen from `maxOverlap` and f, not from t.

**A3. Mechanism.**
1. A flush or a finished compaction calls `CompactionManager.submitBackground` (`CompactionManager.java:230`). That call does nothing if autocompaction is disabled (`:232-236`), or if this table is already compacting and every executor slot is busy (`:244-250`). Otherwise it runs `getNextBackgroundTask` (`UnifiedCompactionStrategy.java:220-231`).
2. `getNextCompactionPick` (`:325-344`) keeps only the suitable, non-compacting sstables (`:328`, `:509-520`). `formLevels` (`:461-507`) groups them by density into levels, each with its own `threshold` (`:561`).
3. `chooseCompactionPick` (`:369-390`) calls `Level.getCompactionPick` (`:597-637`), which calls `getBuckets` (`:658-679`).
4. `getBuckets` builds overlap sets with `Overlaps.constructOverlapSets` (`Overlaps.java:58-93`, a sweep over first/last keys). At **the given line** [`:669-670`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/compaction/UnifiedCompactionStrategy.java#L669-L670) it sets `maxOverlap` to the largest set size.
5. **The check** [`:671`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/compaction/UnifiedCompactionStrategy.java#L671) is `if (maxOverlap < threshold) return null;`.
   - *Below t:* there are no buckets, the method logs `"Level {} sstables {} max overlap {} buckets with compactions 0 tasks 0"` at DEBUG (`:602-605`), and no compaction runs for that level.
   - *At or above t:* overlap sets are grouped into buckets (`Overlaps.assignOverlapsIntoBuckets`, `Overlaps.java:118`, which skips sets smaller than t at `:130`). One bucket with the highest overlap is chosen (`:612-618`) and logged at DEBUG (`:627-629`). `Bucket.constructPick` (`:759-801`) returns all `count = maxOverlap` sstables if `count <= f` (`:768-777`). If `count <= f*f_next`, it returns up to `max_sstables_to_compact` of them (`:778-786`; the default option value `0` means `Integer.MAX_VALUE`, `Controller.java:202-205`, `:414`). Otherwise it returns a pick sized by `selectPickSize` (`:803-826`). **The pick size never depends on t. It can exceed t by any amount.**
6. Bypass and overshoot. Nothing in the write path (memtable, flush) reads t or `maxOverlap`. While compaction lags (throughput limit, all `concurrent_compactors` busy, autocompaction disabled), new flushes add overlapping sstables with no limit. The overlap is checked again only when the next background check runs. Sstables that are being compacted are excluded from the count (`:512-517`), so the transient disk use of a running compaction (inputs plus output) is not counted at all. Expired-sstable drops bypass the threshold entirely (`:329-343`).

**A4. Other consumers.** These use the same disk outside this constraint's control:
- commit log: `commitlog_total_space`, `cassandra.yaml:883`
- hints
- snapshots: `auto_snapshot`, `cassandra.yaml:1147`
- compaction output space, checked separately by `CompactionTask.buildCompactionCandidatesForAvailableDiskSpace` (`CompactionTask.java:384-425`; `max_space_usable_for_compactions_in_percentage`, `Config.java:344`; `min_free_space_per_drive`, `Config.java:339`)
- the data-disk-usage guardrail: `Config.java:926-928`

On heap, memtables (`memtable_heap_space`) and per-sstable structures (bloom filters, index summaries or BTI partition index) scale with partitions and sstable count. The design doc names `target_sstable_size` and `sstable_growth`, not t, as the levers for per-sstable memory (`UnifiedCompactionStrategy.md:424-440`).

**A5. Evidence beyond the source.**
- Design doc in the tree: `src/java/org/apache/cassandra/db/compaction/UnifiedCompactionStrategy.md` (lines 28-40 and 100-116 on the RA/WA trade-off, 280-333 on overlap sets and the trigger, 403-414 on `scaling_parameters`).
- CEP-26: https://cwiki.apache.org/confluence/display/CASSANDRA/CEP-26%3A+Unified+Compaction+Strategy (cited at `UnifiedCompactionStrategy.java:64`).
- `CHANGES.txt:473`, "Implementation of the Unified Compaction Strategy as described in CEP-26 (CASSANDRA-18397)": https://issues.apache.org/jira/browse/CASSANDRA-18397
- Existing unit test `test/unit/org/apache/cassandra/db/compaction/UnifiedCompactionStrategyTest.java:184-302`. It asserts only that a pick exists when `level.size >= T`, never that overlap is bounded.
- The copy of the tree has no git history, so none was used.

## B. Verification solution

**B1. Claim under test.** The UCS threshold t (from `scaling_parameters`) does not cap disk usage:
1. The operand set at `UnifiedCompactionStrategy.java:670` (`maxOverlap`) equals the actual number of overlapping sstables and is not held at or below t. When flushing outpaces compaction it rises well above t, and writes and flushes go on without refusal or back-pressure.
2. For a non-overwriting workload, the table's settled on-disk bytes are the same, within ±5%, for T4, T16 and L4, while they double when the written volume doubles.

The claim is refuted by either of these:
- `maxOverlap` or the on-disk sstable count is held at about t, with writes or flushes blocked or failed once t is reached.
- Settled bytes for non-overwriting data are ordered by t and differ by more than 10%.

### B2. Unit tier

**B2a. Environment and build.**
- Linux, JDK 11 (`java -version` shows 11), Apache Ant 1.10+.
- Copy the source to local disk. Never build in the shared tree.
  ```
  export SRC=<path to the pinned cassandra-5.0.9 source>
  export RUN=/mydata/o239          # local disk (check: df -hT $RUN shows ext4/xfs, not nfs), >= 10 GiB free
  mkdir -p $RUN && rsync -a $SRC/ $RUN/cassandra/
  cd $RUN/cassandra && ant -Dno-checkstyle=true build-test   # first build downloads dependencies to ~/.m2
  ```
- Add the test file `$RUN/cassandra/test/unit/org/apache/cassandra/db/compaction/UcsMaxOverlapOperandTest.java`. It must be in that package because `Level.getCompactionPick`, `Level.maxOverlap` and `SelectionContext` are package-private. Its content is below; the setup is copied from `UnifiedCompactionStrategyTest.java:110-158` and `:834-878`.
  ```java
  package org.apache.cassandra.db.compaction;

  import java.nio.ByteBuffer;
  import java.util.*;
  import org.junit.*;
  import org.mockito.*;
  import org.apache.cassandra.config.DatabaseDescriptor;
  import org.apache.cassandra.db.*;
  import org.apache.cassandra.db.compaction.unified.Controller;
  import org.apache.cassandra.db.lifecycle.SSTableSet;
  import org.apache.cassandra.db.lifecycle.Tracker;
  import org.apache.cassandra.db.marshal.AsciiType;
  import org.apache.cassandra.dht.*;
  import org.apache.cassandra.io.sstable.format.SSTableReader;
  import org.apache.cassandra.schema.TableMetadata;
  import org.apache.cassandra.utils.*;
  import static org.apache.cassandra.io.sstable.format.SSTableReader.UNIQUE_IDENTIFIER_FACTORY;
  import static org.mockito.ArgumentMatchers.*;
  import static org.mockito.Mockito.*;

  public class UcsMaxOverlapOperandTest
  {
      static final long MiB = 1L << 20, SST = 20 * MiB;
      @Mock(answer = Answers.RETURNS_SMART_NULLS) ColumnFamilyStore cfs;
      @Mock(answer = Answers.RETURNS_SMART_NULLS) CompactionStrategyManager csm;
      Tracker tracker; IPartitioner p;

      @BeforeClass public static void cls()
      { DatabaseDescriptor.daemonInitialization(); DatabaseDescriptor.setPartitionerUnsafe(Murmur3Partitioner.instance); }

      void fresh()
      {
          MockitoAnnotations.initMocks(this);
          TableMetadata md = TableMetadata.builder("ks", "tbl").addPartitionKeyColumn("pk", AsciiType.instance).build();
          tracker = Tracker.newDummyTracker(); p = DatabaseDescriptor.getPartitioner();
          when(cfs.getPartitioner()).thenReturn(p);
          ColumnFamilyStore.VersionedLocalRanges lr = cfs.fullWeightedRange(0, p);
          when(cfs.metadata()).thenReturn(md); when(cfs.getTableName()).thenReturn("tbl");
          when(cfs.localRangesWeighted()).thenReturn(lr); when(cfs.getTracker()).thenReturn(tracker);
          when(cfs.getLiveSSTables()).thenAnswer(r -> tracker.getView().select(SSTableSet.LIVE));
          when(cfs.getSSTables(any())).thenAnswer(r -> tracker.getView().select(r.getArgument(0)));
          when(cfs.getCompactionStrategyManager()).thenReturn(csm);
          when(cfs.getDiskBoundaries()).thenReturn(new DiskBoundaries(cfs, new Directories.DataDirectory[0], 0));
          when(csm.onlyPurgeRepairedTombstones()).thenReturn(false);
      }

      Controller ctl(int W)
      {
          Controller c = mock(Controller.class);
          when(c.getScalingParameter(anyInt())).thenReturn(W);
          when(c.getFanout(anyInt())).thenCallRealMethod();
          when(c.getThreshold(anyInt())).thenCallRealMethod();
          when(c.getSurvivalFactor(anyInt())).thenReturn(1.0);
          when(c.getMaxLevelDensity(anyInt(), anyDouble())).thenCallRealMethod();
          when(c.getBaseSstableSize(anyInt())).thenReturn((double) (64 * MiB)); // L0 holds the 20 MiB full-range sstables
          when(c.getNumShards(anyDouble())).thenReturn(1);
          when(c.maxSSTablesToCompact()).thenReturn(Integer.MAX_VALUE);       // = fromOptions default "0"
          when(c.maxConcurrentCompactions()).thenReturn(1000);
          when(c.maxThroughput()).thenReturn(Double.MAX_VALUE);
          when(c.overlapInclusionMethod()).thenReturn(Overlaps.InclusionMethod.TRANSITIVE);
          when(c.random()).thenCallRealMethod();
          return c;
      }

      SSTableReader sst(long bytes, long ts, DecoratedKey first, DecoratedKey last)
      {
          SSTableReader r = mock(SSTableReader.class, withSettings().stubOnly().defaultAnswer(RETURNS_SMART_NULLS));
          when(r.onDiskLength()).thenReturn(bytes); when(r.uncompressedLength()).thenReturn(bytes);
          when(r.getMaxTimestamp()).thenReturn(ts); when(r.getMinTimestamp()).thenReturn(ts);
          when(r.getFirst()).thenReturn(first); when(r.getLast()).thenReturn(last);
          when(r.getInterval()).thenReturn(new Interval<>(first, last, r));
          when(r.instanceId()).thenReturn(TimeUUID.Generator.nextTimeUUID(UNIQUE_IDENTIFIER_FACTORY));
          when(r.compareTo(any())).thenCallRealMethod();
          when(r.isMarkedSuspect()).thenReturn(false); when(r.isRepaired()).thenReturn(false);
          when(r.getPendingRepair()).thenReturn(null); when(r.isPendingRepair()).thenReturn(false);
          when(r.getColumnFamilyName()).thenReturn("tbl");
          when(r.getMinLocalDeletionTime()).thenReturn(Long.MAX_VALUE); when(r.getMaxLocalDeletionTime()).thenReturn(Long.MAX_VALUE);
          return r;
      }

      void run(String series, int W, int n, boolean disjoint)
      {
          fresh();
          Controller c = ctl(W);
          int t = UnifiedCompactionStrategy.thresholdFromScalingParameter(W);
          UnifiedCompactionStrategy s = new UnifiedCompactionStrategy(cfs, new HashMap<>(), c);
          ByteBuffer e = ByteBuffer.allocate(0);
          List<SSTableReader> l = new ArrayList<>();
          for (int i = 0; i < n; i++)
          {
              DecoratedKey f, la;
              if (!disjoint) { f = new BufferDecoratedKey(p.getMinimumToken(), e); la = new BufferDecoratedKey(p.getMaximumToken(), e); }
              else { f = new BufferDecoratedKey(p.split(p.getMinimumToken(), p.getMaximumToken(), i * 1.0 / n).nextValidToken(), e);
                     la = new BufferDecoratedKey(p.split(p.getMinimumToken(), p.getMaximumToken(), (i + 1) * 1.0 / n), e); }
              l.add(sst(SST, 1000L + i, f, la));
          }
          s.addSSTables(l); tracker.addInitialSSTables(l);
          for (UnifiedCompactionStrategy.Level lv : s.getLevels())
          {
              UnifiedCompactionStrategy.SelectionContext ctx = new UnifiedCompactionStrategy.SelectionContext(c);
              UnifiedCompactionStrategy.CompactionPick pick = lv.getCompactionPick(ctx);
              long bytes = 0; for (SSTableReader r : lv.getSSTables()) bytes += r.onDiskLength();
              long pickBytes = 0; if (pick != null) for (SSTableReader r : pick) pickBytes += r.onDiskLength();
              System.out.printf("RESULT series=%s W=%d t=%d n=%d level=%d levelSSTables=%d maxOverlap=%d levelBytes=%d pick=%s pickBytes=%d tasks=%d%n",
                                series, W, t, n, lv.getIndex(), lv.getSSTables().size(), lv.maxOverlap, bytes,
                                pick == null ? "null" : Integer.toString(pick.size()), pickBytes, ctx.estimatedRemainingTasks);
          }
      }

      @Test public void sweep()
      {
          for (int W : new int[]{ 2, 14, -2 })            // T4 (t=4,f=4), T16 (t=16,f=16), L4 (t=2,f=4)
          {
              int t = UnifiedCompactionStrategy.thresholdFromScalingParameter(W);
              for (int n : new int[]{ 1, Math.max(1, t - 1), t, t + 1, 2 * t, 64 })
                  run("overlap", W, n, false);
              run("disjoint", W, 64, true);               // control: bytes grow, overlap stays 1
          }
      }
  }
  ```
- JVM options are the defaults of the `testsome` target (`build.xml:1382-1392`).

**B2b. Knobs.**
- `W` ∈ {2, 14, -2}, which is T4 (the default, t=4), T16 (t=16) and L4 (t=2, f=4). These are a tiered value, a large tiered value and a levelled value, so t takes three different values, and L4 shares f=4 with T4. That separates t from f.
- The knob is set through the mocked `Controller.getScalingParameter`, which feeds the real `getThreshold` and `getFanout` (`Controller.java:238-246`).
- The usage driver is `n`, the number of mutually overlapping 20 MiB sstables: `n ∈ {1, t-1, t, t+1, 2t, 64}`, which is below, at and above the limit.

**B2c. Workload.** n mocked sstables, each `onDiskLength = 20 MiB` and spanning the whole token range. All of them overlap at every key, so `constructOverlapSets` returns a single set of size n, and line 670 sets `maxOverlap = n`.

Density is 20 MiB / 1.0. The L0 upper bound is `floor(64 MiB × f)`, which is 256 MiB (T4, L4) or 1 GiB (T16), so all n sit in level 0 (`:467-477`). The limit t is reached at n = t and passed at n = t+1, 2t and 64.

The control series uses 64 disjoint sstables (1/64 of the range each), 1280 MiB in total, with overlap 1.

**B2d. Observables and instruments.**
- Per level, the `RESULT` lines printed to the test output (`build/test/output/TEST-...UcsMaxOverlapOperandTest.xml` and stdout): `maxOverlap` (the operand, read straight from the field set at line 670), `levelBytes` (the sum of `onDiskLength`), the pick size and `pickBytes` (the input bytes of the compaction the check releases, which is also about the extra disk the output will need), and `estimatedRemainingTasks`.
- Not observable: real bytes on disk, and real compaction or flush timing. The cluster tier covers those.

**B2e. Procedure.**
1. Do B2a. Create the test file.
2. Run:
   ```
   cd $RUN/cassandra
   ant testsome -Dno-checkstyle=true -Dtest.name=org.apache.cassandra.db.compaction.UcsMaxOverlapOperandTest
   ```
3. Run `grep RESULT build/test/output/TEST-org.apache.cassandra.db.compaction.UcsMaxOverlapOperandTest.xml > $RUN/unit-results.txt`.
4. Compare with B2f. Check that `ps -ef | grep -c '[U]csMaxOverlapOperandTest'` is 0.

**B2f. Predictions.** These are stated before any run. "MiB" means 1,048,576 B, so 20 MiB = 20,971,520 B. For every `overlap` row: `maxOverlap == n`, never clamped to t, and `levelBytes == n × 20 MiB`.

| W (t,f) | n | maxOverlap | pick (sstables) | pickBytes | tasks |
|---|---|---|---|---|---|
| T4 (4,4) | 1 / 3 | 1 / 3 | null / null | 0 | 0 |
| T4 | 4 | 4 | 4 | 80 MiB | 1 |
| T4 | 5 | 5 | 5 | 100 MiB | 1 |
| T4 | 8 | 8 | 8 | 160 MiB | 2 |
| T4 | 64 | 64 | 64 (`selectPickSize`: 4→16→64) | 1280 MiB | 16 |
| T16 (16,16) | 1 / 15 | 1 / 15 | null | 0 | 0 |
| T16 | 16 / 17 / 32 / 64 | 16 / 17 / 32 / 64 | 16 / 17 / 32 / 64 | n × 20 MiB | 1 / 1 / 2 / 4 |
| L4 (2,4) | 1 | 1 | null | 0 | 0 |
| L4 | 2 / 3 / 4 | 2 / 3 / 4 | 2 / 3 / 4 | n × 20 MiB | 1 / 1 / 2 |
| L4 | 64 | 64 | 64 (4→16→64, ×(64/64)) | 1280 MiB | 32 |
| any | `disjoint` 64 | 1 on the populated level (density 1280 MiB, so level 2 for T4/L4 and level 1 for T16); empty lower levels print -1 | null | 0 | 0 |

Relations: `maxOverlap` follows n, not t. Bytes follow n. t only moves the n at which `pick` stops being null.

**B2g. Readings.**

| Observation | Meaning |
|---|---|
| `maxOverlap == n` for every n, including n ≫ t; `levelBytes == n × 20 MiB`; pick size ≥ t whenever non-null, and equal to n for n=64 | The operand and the bytes follow the sstable count, not t. **Claim confirmed** (unit part). |
| Pick null exactly when n < t, for all three W | The positive control moved: t is wired and changes behaviour at the predicted n. Without this row, the rows above say nothing. |
| `disjoint` row: `maxOverlap == 1`, bytes 1280 MiB, no pick | The operand ignores bytes entirely. Confirms. |
| `maxOverlap` capped at t (e.g. `maxOverlap == 4` for T4 with n=64), or pick size ≤ t for every n | Usage-side value follows the knob. **Claim refuted**. |
| Pick null for n ≥ t, or non-null for n < t | The trace in A3 is wrong. Not confirmed; re-read `:671` and `Overlaps.java:130`. |
| All sstables not in one level (level count > 1 for the overlap series) | Setup error (base size). Not confirmed; fix `getBaseSstableSize`. |

**B2h. Controls.**
- The real `getThreshold` and `getFanout` are used. Only W comes from the mock.
- T4 and L4 share f=4 but have different t, so any pick-size difference between them comes from t, and identical sizes at n=64 show the size comes from f.
- The `disjoint` series separates bytes from overlap.
- A fresh tracker and strategy per row, so no state leaks between rows.
- `maxSSTablesToCompact = MAX_VALUE` matches the production default (`Controller.java:202-205`, `:414`).

### B3. Cluster tier

**B3a. Environment and build.**
- One Linux node, JDK 11, Ant, Python 3.8–3.11 for `cqlsh`, ≥ 10 GiB free on local `$RUN`, ≥ 4 GiB RAM.
- Build the copy from B2a:
  ```
  cd $RUN/cassandra && ant -Dno-checkstyle=true jar stress-build
  ```
- Data, commit log, hints and saved caches go under `$CASSANDRA_HOME/data` (`bin/cassandra.in.sh:48`), which is `$RUN/cassandra/data`, on local disk. Logs go to `$RUN/cassandra/logs`.
- Configuration (`$RUN/cassandra/conf/cassandra.yaml`, edited in the copy only):
  ```
  sed -i -E 's/^cluster_name:.*/cluster_name: o239/; s/^auto_snapshot: true/auto_snapshot: false/; s/^# concurrent_compactors: 1/concurrent_compactors: 1/; s/^# commitlog_total_space: 8192MiB/commitlog_total_space: 1024MiB/' conf/cassandra.yaml
  grep -nE '^(cluster_name|auto_snapshot|concurrent_compactors|commitlog_total_space|compaction_throughput):' conf/cassandra.yaml
  ```
  The grep should show `o239`, `false`, `1`, `1024MiB` and `64MiB/s`. A single compactor makes compaction lag deterministic.
- Ports: run `ss -ltn | grep -E ':(7000|7199|9042)\b'`. It must print nothing. Otherwise change `storage_port`, `native_transport_port` and `JMX_PORT` in `conf/cassandra-env.sh`, and pass `-p` to nodetool and `-port native=` to stress.
- JVM: `export MAX_HEAP_SIZE=2G HEAP_NEWSIZE=400M`.

**B3b. Knobs.**
- `scaling_parameters` ∈ {`T4`, `T16`, `L4`}, set per run on the table with `'base_shard_count':'1'`. The node-wide default property is left unset.
- Second knob: `compaction_throughput`, set with `nodetool setcompactionthroughput 64` (unthrottled reference) or `1` (lagging compaction). It makes compaction slower than flushing so the trigger's lack of enforcement shows.
- Workload knobs: mode `insert` (distinct keys per batch) or `overwrite` (the same keys every batch), and the number of batches B (32, or 64 for the volume control).

| Run | scaling_parameters | throughput | mode | B | purpose |
|---|---|---|---|---|---|
| R1 | T4 | 64 | insert | 32 | settled bytes vs t |
| R2 | T16 | 64 | insert | 32 | settled bytes vs t |
| R3 | L4 | 64 | insert | 32 | settled bytes vs t |
| R4 | T4 | 1 → 64 after feed | overwrite | 32 | overlap and bytes past t while lagging |
| R5 | T16 | 1 → 64 after feed | overwrite | 32 | same, larger t |
| R6 | T4 | 64 | overwrite | 32 | keeping-up reference; then `nodetool compact` (positive control) |
| R6b | T16 | 64 | overwrite | 32 | keeping-up reference (indirect space-amp effect) |
| R7 | T4 | 64 | insert | 64 | volume control (bytes ≈ 2 × R1) |

**B3c. Workload.**
- Each batch is one `cassandra-stress` write of 20,000 partitions × 5 columns × 200 B ≈ 1.0–1.1 KiB per row, about 21 MiB uncompressed per flush. It is followed by `nodetool flush`.
- Keys come from `-pop seq`, hashed by Murmur3, so each flushed sstable covers essentially the whole token range. Every L0 sstable therefore overlaps every other, and the L0 overlap equals the number of non-compacting L0 sstables.
- `insert`: batch i uses keys `i*20000+1 .. (i+1)*20000`. 32 batches is about 670 MiB of live data, 64 batches about 1.34 GiB.
- `overwrite`: every batch uses keys `1..20000`, so the live data is about 21 MiB and the rest is superseded copies.
- Reaching the limit:
  - T4 compacts once 4 flushes overlap. At 1 MiB/s, one 4×21 MiB compaction takes about 84 s. One batch (stress JVM start, write, flush) takes about 5–10 s, so 8–16 more flushes pile up during the first compaction. That is 2t–4t for T4.
  - For T16, the first compaction (16×21 MiB) starts at flush 16 and takes about 336 s at 1 MiB/s, so flushes 17–32 pile up behind it.
- Duration: about 5–8 min of feed per run, plus settling, so about 1.5–2 h for all runs.

**B3d. Observables and instruments.**
- **Operand (maxOverlap).** The UCS DEBUG lines `Level <i> sstables <n> max overlap <m> buckets with compactions <b> tasks <k>` (`UnifiedCompactionStrategy.java:603`, `:628`) in `logs/debug.log`. Enable them with `nodetool setlogginglevel org.apache.cassandra.db.compaction.UnifiedCompactionStrategy DEBUG`. Only `keyspace1.standard1` uses UCS (system tables keep their own strategy, and `default_compaction` is unset, `cassandra.yaml:1209`), so every such line belongs to the test table. The line is emitted only when a background check runs (after a flush, or after a compaction ends with a free slot, `CompactionManager.java:244-250`), so the operand is sampled rather than continuous.
- **Disk.**
  - `du -sb` of `$RUN/cassandra/data/data/keyspace1/standard1-*` includes in-progress compaction output and is the actual resource.
  - `ls .../*-Data.db | wc -l` counts sstables on disk.
  - `nodetool tablestats keyspace1.standard1`: `Space used (live)` and `SSTable count`.
  - `nodetool compactionstats`: `pending tasks`.
- **Sampling.**
  - After every batch, the full sample (du, count, tablestats, compactionstats).
  - Every 2 s in the background, du and count only, for the peak.
  - At settle (pending 0 and no active compaction for 3 consecutive 10 s polls).
- **Write health.** Stress output: `Total errors` must be 0 and `op rate` is recorded. `nodetool tpstats`: `MemtableFlushWriter` blocked and `MutationStage` dropped must be 0.
- **Not directly observable.** `maxOverlap` between background checks, and the heap used by per-sstable structures. The heap is not part of the claim.

**B3e. Procedure.** Run everything from `$RUN/cassandra`. `$RID` is the run id.
```
cd $RUN/cassandra; mkdir -p $RUN/out
export MAX_HEAP_SIZE=2G HEAP_NEWSIZE=400M
bin/cassandra -p $RUN/cassandra.pid > $RUN/out/start.log 2>&1
until bin/nodetool status 2>/dev/null | grep -q '^UN'; do sleep 5; done
bin/nodetool setlogginglevel org.apache.cassandra.db.compaction.UnifiedCompactionStrategy DEBUG

mktable() {  # $1 = scaling_parameters
  bin/cqlsh 127.0.0.1 -e "DROP KEYSPACE IF EXISTS keyspace1;
   CREATE KEYSPACE keyspace1 WITH replication = {'class':'SimpleStrategy','replication_factor':1};
   CREATE TABLE keyspace1.standard1 (key blob PRIMARY KEY, \"C0\" blob, \"C1\" blob, \"C2\" blob, \"C3\" blob, \"C4\" blob)
     WITH compression = {'enabled':'false'}
     AND compaction = {'class':'UnifiedCompactionStrategy','scaling_parameters':'$1','base_shard_count':'1'};"
  bin/cqlsh 127.0.0.1 -e "DESCRIBE TABLE keyspace1.standard1" | grep -o "scaling_parameters': '[^']*'"
}
D() { ls -d $RUN/cassandra/data/data/keyspace1/standard1-* ; }
sample() {  # $1 = tag
  echo "$RID,$1,$(date +%s),$(du -sb $(D) | cut -f1),$(ls $(D)/*-Data.db 2>/dev/null | wc -l),$(bin/nodetool tablestats keyspace1.standard1 | awk -F': ' '/Space used \(live\)/{print $2}'),$(bin/nodetool compactionstats | awk '/pending tasks/{print $3}')" >> $RUN/out/samples.csv
}
bgsample() { while :; do echo "$RID,bg,$(date +%s),$(du -sb $(D) 2>/dev/null | cut -f1),$(ls $(D)/*-Data.db 2>/dev/null | wc -l)" >> $RUN/out/bg.csv; sleep 2; done; }
feed() {  # $1 = insert|overwrite, $2 = batches
  for i in $(seq 0 $(($2-1))); do
    if [ "$1" = insert ]; then lo=$((i*20000+1)); hi=$(((i+1)*20000)); else lo=1; hi=20000; fi
    tools/bin/cassandra-stress write n=20000 cl=ONE no-warmup -pop seq=$lo..$hi \
      -col n='FIXED(5)' size='FIXED(200)' -rate threads=8 -node 127.0.0.1 \
      -schema keyspace=keyspace1 > $RUN/out/$RID-stress-$i.txt 2>&1
    bin/nodetool flush keyspace1 standard1
    sample batch$i
  done
}
settle() { n=0; while [ $n -lt 3 ]; do sleep 10;
  if bin/nodetool compactionstats | grep -q 'pending tasks: 0' && ! bin/nodetool compactionstats | grep -q 'Compaction'; then n=$((n+1)); else n=0; fi; done; sample settled; }

run() {  # $1 RID  $2 scaling  $3 throughput  $4 mode  $5 batches
  RID=$1; mktable $2; bin/nodetool setcompactionthroughput $3
  L0=$(wc -l < logs/debug.log); bgsample & BG=$!
  feed $4 $5; sample endfeed
  bin/nodetool setcompactionthroughput 64; settle
  kill $BG; wait $BG 2>/dev/null
  tail -n +$L0 logs/debug.log | grep 'max overlap' > $RUN/out/$RID-overlap.log
}
run R1 T4 64 insert 32
run R2 T16 64 insert 32
run R3 L4 64 insert 32
run R4 T4 1 overwrite 32
run R5 T16 1 overwrite 32
run R6 T4 64 overwrite 32;  RID=R6; bin/nodetool compact keyspace1 standard1; settle   # positive control
run R6b T16 64 overwrite 32
run R7 T4 64 insert 64
grep -h 'Total errors' $RUN/out/*-stress-*.txt | sort | uniq -c      # expect all 0
bin/nodetool tpstats | grep -E 'MemtableFlushWriter|MUTATION'
```
Then, per run:
- Peak operand: `awk '{for(i=1;i<=NF;i++) if($i=="overlap") print $(i+1)}' $RUN/out/$RID-overlap.log | sort -n | tail -1`.
- Peak bytes: the maximum of column 4 in `bg.csv` for `$RID`.
- `endfeed` and `settled` rows from `samples.csv`.

Finally, B4 cleanup.

**B3f. Predictions.** These are stated before any run. Live data per insert batch is about 21 MiB.
- **R1/R2/R3 (insert).**
  - Settled `du` is about 650–720 MiB for each run.
  - `max(R1,R2,R3)/min(R1,R2,R3) ≤ 1.05`, and the result is not ordered by t.
  - Settled sstable counts differ (T16 about 2, T4 about 2, L4 1–3), but bytes do not.
  - Peak operand: about ≤ t+2 in each, because compaction keeps up at 64 MiB/s.
  - Stress errors: 0.
- **R7 (64 insert batches).** Settled `du` = 2 × R1 ± 5%.
- **R4 (T4, throttled overwrite).**
  - Peak logged L0 `max overlap` ≥ 8 (≥ 2t).
  - `Data.db` count at `endfeed` ≥ 10.
  - `du` at `endfeed` ≥ 8 × 21 MiB ≈ 170 MiB.
  - Stress errors 0, every batch completes, no flush blocked.
  - After settle at 64 MiB/s: `du` back to ≤ (t+1) × 21 MiB ≈ 105 MiB.
- **R5 (T16, throttled overwrite).**
  - Peak logged `max overlap` ≥ 16, with `endfeed` `Data.db` ≥ 17.
  - `du` at `endfeed` ≥ 17 × 21 MiB ≈ 360 MiB.
  - Writes unaffected.
- **R6 (T4 overwrite, keeping up).**
  - Every sample ≤ about 5 × 21 MiB ≈ 105 MiB (plus a transient compaction output ≤ 21 MiB).
  - After `nodetool compact`: `du` about 21–23 MiB (positive control).
- **R6b (T16 overwrite, keeping up).** Samples up to about 16–17 × 21 MiB ≈ 340–360 MiB. This is the indirect, scheduling-level dependence on t, expected and not a cap: R4 vs R6 shows the same t gives 2× or more the bytes once compaction lags.

**B3g. Readings.**

| Observation | Meaning |
|---|---|
| R1≈R2≈R3 within 5% while R7 ≈ 2×R1 | Disk does not follow t but does follow volume. **Claim confirmed** (positive control moved). |
| R4/R5 peak `max overlap` > 2t and endfeed bytes ≫ t × 21 MiB, with 0 stress errors and no blocked flushes | t is not enforced. Overlap and bytes run past it. **Claim confirmed**. |
| R6 `nodetool compact` drops bytes to about 21 MiB | The instrument and workload respond to a mechanism that really reduces bytes (positive control). |
| R6 ≤ ~105 MiB but R6b up to ~350 MiB | The expected indirect effect while compaction keeps up. It does not refute the claim if R4/R5 show the bound collapsing when compaction lags. |
| R1/R2/R3 bytes ordered by t and differing > 10% | Usage follows the knob. **Claim refuted** (part 2). |
| R4/R5 overlap and `Data.db` count held at ≤ t+1, or stress errors / blocked flushes appear when the count reaches t | t enforced as a limit. **Claim refuted** (part 1). |
| R7 not ≈ 2×R1, or R6 major compaction does not reduce bytes | The positive control did not move. **Not confirmed**: check the workload (keys, flushes) and the instruments. |
| No `max overlap` lines in the logs, or throttled runs never exceed t because compaction kept up anyway | Limit never stressed. **Not confirmed**: lower throughput further (`setcompactionthroughput 1` is the minimum non-zero; alternatively `nodetool disableautocompaction keyspace1 standard1` during the feed and `enableautocompaction` after) and repeat. |

**B3h. Controls.**
- Same node, binary and workload for every run. Only `scaling_parameters` (R1–R3, R4 vs R5, R6 vs R6b) or the throughput (R4 vs R6) changes.
- Compression is off, so byte counts do not depend on compression ratios.
- `auto_snapshot: false`, and `DROP KEYSPACE` between runs, so earlier runs' data and snapshots do not leak in. Check that `nodetool listsnapshots` is empty.
- `DESCRIBE TABLE` confirms the value of `scaling_parameters` in force. The presence of UCS DEBUG lines confirms UCS is active.
- `base_shard_count=1` keeps one sstable per flush. If `Data.db` grows by more than 1 per flush, the overlap is still the number of flushes, and the DEBUG line is the authority.
- A single compactor removes concurrency noise.
- The volume control (R7) and the major-compaction control (R6) show the instruments are sensitive.

**B4. Risks and cleanup.**
- **Disk.** Peak about 1.4 GiB (R7 insert) plus compaction output (≤ 1×) plus a commit log ≤ 1 GiB, so ≤ 4 GiB, all under `$RUN` on local disk. Abort if `df $RUN` drops below 2 GiB free.
- **Shared storage.** Nothing is written outside `$RUN` except Ant/Maven caches under `~/.m2` and `~/.ant`. If home is shared, set `-Dmaven.repo.local=$RUN/m2`.
- **Processes.** Unit tier: the JUnit JVM exits by itself. Check with `pgrep -f UcsMaxOverlapOperandTest`.
- **Cluster tier cleanup:**
  ```
  kill $(jobs -p) 2>/dev/null                       # background sampler
  bin/nodetool drain; kill $(cat $RUN/cassandra.pid); sleep 10
  pgrep -f "CassandraDaemon.*$RUN" && kill -9 $(pgrep -f "CassandraDaemon.*$RUN")
  pgrep -f cassandra-stress && pkill -f cassandra-stress
  pgrep -fa "$RUN" || echo "nothing left running"
  ```
- Keep `$RUN/out` and `unit-results.txt`, then `rm -rf $RUN/cassandra/data $RUN/cassandra/logs` (or all of `$RUN`) when done.

## C. Sources read

- ~/writeup-ext/playbook-autonomous.md
- ~/writeup-ext/_TEMPLATE-autonomous.md
- src/java/org/apache/cassandra/db/compaction/UnifiedCompactionStrategy.java (whole file)
- src/java/org/apache/cassandra/db/compaction/unified/Controller.java (lines 40-250, 395-480, 640-746)
- src/java/org/apache/cassandra/config/CassandraRelevantProperties.java (lines 48, 609-615, 645-674)
- src/java/org/apache/cassandra/utils/Overlaps.java (lines 53-132)
- src/java/org/apache/cassandra/db/compaction/ShardManager.java (lines 134-142)
- src/java/org/apache/cassandra/db/compaction/CompactionManager.java (lines 230-264)
- src/java/org/apache/cassandra/db/compaction/CompactionTask.java (lines 380-425)
- src/java/org/apache/cassandra/db/compaction/unified/UnifiedCompactionTask.java (line 35)
- src/java/org/apache/cassandra/db/compaction/AbstractCompactionStrategy.java (addSSTables, line 298)
- src/java/org/apache/cassandra/db/compaction/UnifiedCompactionStrategy.md (lines 28-130, 280-333, 395-450)
- src/java/org/apache/cassandra/config/Config.java (lines 338-344, 926-928, 1161)
- src/java/org/apache/cassandra/metrics/TableMetrics.java (lines 554, 678-680)
- test/unit/org/apache/cassandra/db/compaction/UnifiedCompactionStrategyTest.java (lines 19-330, 824-921)
- tools/stress/src/org/apache/cassandra/stress/settings/SettingsSchema.java (lines 120-210)
- tools/stress/src/org/apache/cassandra/stress/settings/SettingsColumn.java (line 127)
- conf/cassandra.yaml (cluster_name, commitlog, auto_snapshot, compaction keys)
- conf/logback.xml (debug.log appender)
- conf/cassandra-env.sh (heap variables)
- bin/cassandra, bin/cassandra.in.sh (storagedir, log dir)
- build.xml (targets jar, stress-build, build-test, testsome)
- CHANGES.txt (UCS entries)
- https://cwiki.apache.org/confluence/display/CASSANDRA/CEP-26%3A+Unified+Compaction+Strategy (cited from the source, not fetched)
- https://issues.apache.org/jira/browse/CASSANDRA-18397 (from CHANGES.txt, not fetched)

## D. Stage-4 feedback

none yet
