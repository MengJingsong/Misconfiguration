# NO_COMPACTION_LIMIT — verification solution  <!-- file: cases/NO_COMPACTION_LIMIT-getOverlappingStarvedSSTables-compactionCounter--autonomous.md -->

| Field | Value |
|---|---|
| Entry pointer | the given line (unit kind: capacity-set), **linked**: [`LeveledManifest.java:69`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/compaction/LeveledManifest.java#L69) (`private static final int NO_COMPACTION_LIMIT = 25;`); the check that reads it is [`LeveledManifest.java:359`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/compaction/LeveledManifest.java#L359) |
| Pinned source | `cassandra-5.0.9` |
| Session / date | Claude Opus 5.5 (`claude-opus-5-5`), Claude Code 2.1.330, 2026-11-24 |
| Estimate | `negative`. `NO_COMPACTION_LIMIT` counts LCS compaction rounds, not bytes. Once a level's round counter goes past it, the next compaction into a lower level takes one extra sstable from the highest non-empty level. It sets when stranded top-level data starts to be rewritten. It does not limit how much memory or disk the node uses. |
| Ground | The check compares `compactionCounter[i]` (a number of `getCompactionCandidates()` rounds that did not target level `i`) with 25. No byte, row or object count is compared against the limit ([`LeveledManifest.java:359`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/compaction/LeveledManifest.java#L359)). When the check passes, it adds **at most one** sstable to a compaction (`return withStarvedCandidate` at `LeveledManifest.java:384-385`), whatever the limit's value. The only resource it holds is `int[9]` (`LeveledManifest.java:90`). Its effect on disk goes through a side path: it starts reclaiming shadowed data in starved top-level sstables. The amount reclaimed depends on the workload (the stranded bytes), not on the value 25. With enough rounds, every finite value reaches the same disk usage. |

## A. Constraint trace

**A1. The constraint.** `NO_COMPACTION_LIMIT`, a Java **constant** (`private static final int`), declared at
[`LeveledManifest.java:69`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/compaction/LeveledManifest.java#L69).
- Unit: compaction rounds, i.e. calls to `LeveledManifest.getCompactionCandidates()` that reach the higher-level branch (`LeveledManifest.java:274-281`).
- Default: 25. It is a literal, not derived from anything, and is documented only by the javadoc at `LeveledManifest.java:64-68` ("If we go this many rounds without compacting in the highest level, we start bringing in sstables from that level into lower level compactions").
- How it can be set: **not settable**. There is no yaml key, `-D` property, JMX attribute or table option. It is a compile-time constant, so `javac` inlines it into `LeveledManifest.class` and reflection cannot change it. The only way to change it is to edit line 69 and recompile `LeveledManifest` (a rebuild and a restart).
- Related per-table options that are settable and decide when this code runs: `sstable_size_in_mb` (default 160, `LeveledCompactionStrategy.java:67`), `fanout_size` (default 10) and `single_sstable_uplevel` (`LeveledCompactionStrategy.java:52-55`).

**A2. What it caps.** Nominally nothing in bytes. The quantity compared is `compactionCounter[i]` (`LeveledManifest.java:78`, allocated as `new int[MAX_LEVEL_COUNT]` = 9 at `LeveledManifest.java:90`, `LeveledGenerations.java:57`). It counts how many higher-level compaction-candidate rounds have passed since level `i` was last a compaction target. The resource it can affect indirectly is **disk**: how long fully shadowed or overwritten data in the highest non-empty level ("starved" sstables) stays on disk before it is merged away. There is no heap or off-heap effect beyond the 9-int array.

**A3. Mechanism.**
1. `LeveledCompactionStrategy.getNextBackgroundTask` calls `manifest.getCompactionCandidates()` (`LeveledCompactionStrategy.java:137`).
2. `getCompactionCandidates()` scores each level `i` from the top down: `remainingBytes / maxBytesForLevel(i)` (`LeveledManifest.java:245-258`; `maxBytesForLevel` = `fanout^i × sstable_size`, `LeveledManifest.java:185-193`). For the first level with score > 1.001 (not the maximum level, not pre-empted by STCS in L0), it picks `getCandidatesFor(i)` (`LeveledManifest.java:274`) and the target `nextLevel = getNextLevel(candidates)` (`LeveledManifest.java:277`, usually `i+1`, `LeveledManifest.java:684`). It then calls `getOverlappingStarvedSSTables(nextLevel, candidates)` (`LeveledManifest.java:278`).
   - This is the **only** caller. L0→L1 compactions (`LeveledManifest.java:293-301`), STCS-in-L0 (`LeveledManifest.java:304-317`) and bootstrap STCS (`LeveledManifest.java:203-211`) do not advance the counters.
3. In `getOverlappingStarvedSSTables`:
   - Every level 1..8 counter is incremented, and the target level's counter is reset to 0 (`LeveledManifest.java:346-348`).
   - It then finds the **highest non-empty level** `i` (`LeveledManifest.java:355-357`) and applies the check
     [`LeveledManifest.java:359`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/compaction/LeveledManifest.java#L359): `if (compactionCounter[i] > NO_COMPACTION_LIMIT)`.
4. Outcome **true** (the 26th or later round in which level `i` was not the target):
   - It computes the token span [min first, max last] of the candidates (`LeveledManifest.java:365-373`). If the candidates span a single partition, it returns them unchanged (`LeveledManifest.java:374-375`).
   - Otherwise it scans level `i` for the first sstable whose range is fully contained in that span and is not compacting (`LeveledManifest.java:376-381`). It adds **that one sstable** to the candidate set, logs `INFO "Adding high-level (L{}) {} to candidates"` and returns (`LeveledManifest.java:383-385`).
   - The compaction then writes the merged output into `nextLevel`, which is lower than `i`. Stranded top-level data is moved down and merged with newer versions, so shadowed cells and tombstones can be purged.
   - The counter for `i` is **not** reset by this step. It resets only when `i` itself is a target (`LeveledManifest.java:348`), so every later round keeps adding one sstable while level `i` is non-empty.
5. Outcome **false**: candidates are returned unchanged (`LeveledManifest.java:389`).
6. Bypasses and overshoot:
   - The counter is in-memory only. It resets to 0 at node restart and whenever the strategy is rebuilt, including an `ALTER TABLE ... WITH compaction` (`CompactionStrategyManager.java:478-515` → `setStrategy`, which builds a new manifest at `LeveledManifest.java:81-91`).
   - Rounds are counted per candidate *selection*. If `tryModify` fails and the strategy loops (`LeveledCompactionStrategy.java:158-179`), the counter can advance without a compaction running.
   - If no top-level sstable fits inside the candidate span, nothing is added, even past the limit.
   - The maximum level (L8) is never compacted from (`LeveledManifest.java:262-267`).
   - The size added per round is one sstable. That is ≤ `sstable_size_in_mb` when the sstable was written at the current size, but it can be larger if the table's sstable size was lowered after the data was written.

**A4. Other consumers.** Other things that govern the same disk outside this constant:
- `maxBytesForLevel` (level byte targets via `sstable_size_in_mb`, `fanout_size`), which decides whether rounds happen at all.
- STCS in L0 when L0 has more than `MAX_COMPACTING_L0` = 32 sstables (`LeveledManifest.java:62`, `306`; disabled by `-Dcassandra.disable_stcs_in_l0`).
- `max_threshold` capping L0 candidate count (`LeveledManifest.java:552-556`).
- Tombstone compactions (`LeveledCompactionStrategy.java:140-150`), `gc_grace_seconds`, major compaction (`getMaximalTask`, `LeveledCompactionStrategy.java:182-192`).
- Memtable flushes and commit log, compaction write amplification (temporary output before the originals are deleted), snapshots.

**A5. Evidence beyond the source.**
- `CHANGES.txt:4607` "Make sure high level sstables get compacted (CASSANDRA-7414)", which introduced this mechanism. https://issues.apache.org/jira/browse/CASSANDRA-7414
- `doc/modules/cassandra/pages/managing/operating/compaction/lcs.adoc:37-43` "Starved sstables": "If these starved SSTables are not resolved within a defined number of compaction rounds, they will be included in other compactions. This situation generally occurs if a user lowers the `sstable_size` setting."
- Existing tests: `test/unit/org/apache/cassandra/db/compaction/LeveledCompactionStrategyTest.java:884-910` shows how a `LeveledManifest` is driven directly with `MockSchema` sstables. No existing test exercises the starvation path.

## B. Verification solution

**B1. Claim under test.** `NO_COMPACTION_LIMIT` does not cap memory or disk:
- Changing its value changes only *which round* first adds a starved top-level sstable to a compaction. It does not change *how many bytes* are added: exactly one sstable, of that sstable's own size.
- Among finite values, the table's quiescent on-disk size after enough rounds does not depend on it. It is set by the workload, and moves only between "mechanism active" and "mechanism effectively off".

### B2. Unit tier

**B2a. Environment and build.**
- Linux, JDK 11 (`java -version` shows 11), Apache Ant ≥ 1.10.
- Copy the tree to local disk. Never build in the shared tree.
  ```
  export W=/mydata/ncl-unit        # any local disk with >= 10 GB free
  mkdir -p $W && rsync -a ~/cassandra-5.0.9/ $W/cassandra-5.0.9/
  cd $W/cassandra-5.0.9 && ant realclean && ant build-test
  ```
- The test source goes in the copy at `test/unit/org/apache/cassandra/db/compaction/NoCompactionLimitProbeTest.java`. It must be in the same package because the `LeveledManifest` constructor is package-private.
- JVM options: those of `ant testsome` (unchanged).

**B2b. Knobs.**
1. **K1, `NO_COMPACTION_LIMIT` ∈ {5, 25 (stock), 100}.** Set by editing line 69 of the copy, e.g. `sed -i 's/NO_COMPACTION_LIMIT = 25;/NO_COMPACTION_LIMIT = 5;/' src/java/org/apache/cassandra/db/compaction/LeveledManifest.java`. `ant testsome` recompiles it. Confirm with `grep -n "NO_COMPACTION_LIMIT =" src/java/org/apache/cassandra/db/compaction/LeveledManifest.java`. The values are below, at and above the stock value, so the trigger round moves by a known amount.
2. **K2, starved sstable size `S3` ∈ {1 MiB, 4 MiB, 16 MiB}.** Set as a test parameter. This is the positive control: it shows the bytes added follow the sstable's size, not K1.
3. **K3, L1 total bytes ∈ {11 × 1.1 MiB = 12.1 MiB (over target), 9 × 1.1 MiB = 9.9 MiB (under target)}.** This is a control for the byte cap that does gate rounds (`maxBytesForLevel(1)` = 10 MiB with `sstable_size_in_mb=1`, fanout 10).

**B2c. Workload.**
- Manifest: `new LeveledManifest(cfs, 1 /*MB*/, 10 /*fanout*/, new SizeTieredCompactionStrategyOptions())` on `MockSchema.newCFS()`.
- L1: 11 sstables, each 1,153,433 bytes (1.1 MiB), with non-overlapping token ranges `[100k, 100k+50]` for k = 0..10. Built with `MockSchema.sstable(gen, size, false, first, last, 1, cfs)` (`MockSchema.java:163`). L1 total = 12,687,763 B > 1.001 × 10,485,760 = 10,496,246 B, so L1's score is > 1.001 on every call.
- L2: empty. `getCandidatesFor(1)` therefore returns the single L1 sstable `[0,50]` (`LeveledManifest.java:577-588`), and `getNextLevel` = 2.
- L3: one sstable of size `S3` with tokens `[10,40]`, which is inside the candidate span (0,50] (`Range.contains`, `Range.java:73-86`). L3 score = `S3` / 1000 MiB < 1, so L3 is never a source. L3 is the highest non-empty level.
- Call `getCompactionCandidates()` 200 times. Nothing is marked compacting and `lastCompactedSSTables` does not move, so every call returns the same L1 candidate. `compactionCounter[3]` rises by 1 per call (target level 2 is reset), so the limit is reached at call K1 and passed at call K1+1. 200 > 100+1, so every K1 value is passed.

Test body (sketch, complete enough to type in):
```java
package org.apache.cassandra.db.compaction;
// imports: java.lang.reflect.Field, java.util.*, org.junit.*, org.apache.cassandra.config.DatabaseDescriptor,
// org.apache.cassandra.db.ColumnFamilyStore, org.apache.cassandra.io.sstable.format.SSTableReader,
// org.apache.cassandra.schema.MockSchema
public class NoCompactionLimitProbeTest {
  static final int MB = 1 << 20;
  @BeforeClass public static void setUp() { DatabaseDescriptor.daemonInitialization(); MockSchema.cleanup(); }
  static int[] counters(LeveledManifest lm) throws Exception {
    Field f = LeveledManifest.class.getDeclaredField("compactionCounter"); f.setAccessible(true); return (int[]) f.get(lm); }
  void run(String tag, int l1Count, int s3) throws Exception {
    ColumnFamilyStore cfs = MockSchema.newCFS();
    LeveledManifest lm = new LeveledManifest(cfs, 1, 10, new SizeTieredCompactionStrategyOptions());
    int gen = 1; List<SSTableReader> all = new ArrayList<>();
    for (int k = 0; k < l1Count; k++) all.add(MockSchema.sstable(gen++, (int)(1.1 * MB), false, 100L*k, 100L*k + 50, 1, cfs));
    SSTableReader l3 = MockSchema.sstable(gen++, s3, false, 10, 40, 3, cfs); all.add(l3);
    lm.addSSTables(all);
    for (int call = 1; call <= 200; call++) {
      LeveledManifest.CompactionCandidate c = lm.getCompactionCandidates();
      System.out.printf("PROBE,%s,%d,%d,%s,%d,%d,%d,%b%n", tag, s3, call, c == null ? "null" : String.valueOf(c.level),
        c == null ? 0 : c.sstables.size(), c == null ? 0 : SSTableReader.getTotalBytes(c.sstables),
        counters(lm)[3], c != null && c.sstables.contains(l3));
    }
  }
  @Test public void probe() throws Exception {
    for (int s3 : new int[]{ MB, 4*MB, 16*MB }) run("over", 11, s3);
    run("under", 9, MB);
  }
}
```

**B2d. Observables and instruments.**
- One `PROBE,...` line per call, giving: tag, `S3`, call index, candidate target level, candidate count, candidate bytes (`SSTableReader.getTotalBytes` = sum of `onDiskLength`, `SSTableReader.java:541-547`), `compactionCounter[3]` (via reflection), and whether the L3 sstable is in the candidate.
- Collect them with `grep '^PROBE' build/test/output/TEST-org.apache.cassandra.db.compaction.NoCompactionLimitProbeTest.xml` (or the matching `.log`/`-stdout` file under `build/test/`).
- Not observable here: real disk use. The candidate bytes are the bytes a compaction would read and rewrite, not live usage.

**B2e. Procedure.**
1. `cd $W/cassandra-5.0.9`, create the test file above.
2. For N in 5 25 100:
   - `sed -i -E "s/NO_COMPACTION_LIMIT = [0-9]+;/NO_COMPACTION_LIMIT = $N;/" src/java/org/apache/cassandra/db/compaction/LeveledManifest.java`
   - `grep -n "NO_COMPACTION_LIMIT =" src/java/org/apache/cassandra/db/compaction/LeveledManifest.java`
   - `ant testsome -Dtest.name=org.apache.cassandra.db.compaction.NoCompactionLimitProbeTest`
   - `grep -h '^PROBE' build/test/output/*NoCompactionLimitProbeTest* | sed "s/^/N=$N,/" > $W/probe-N$N.csv`
3. Restore: `sed -i -E 's/NO_COMPACTION_LIMIT = [0-9]+;/NO_COMPACTION_LIMIT = 25;/' ...`.
4. For each CSV, find the first call where `hasL3=true`, and the candidate bytes before and after it.

**B2f. Predictions** (before any run).
- Tag `over`, any N, any S3:
  - Calls 1..N: level 2, 1 sstable, 1,153,433 B, `hasL3=false`, counter3 = call index.
  - Calls N+1..200: level 2, 2 sstables, 1,153,433 + S3 B, `hasL3=true`. Counter3 keeps rising; it is never reset.
  - First `hasL3=true` call: N=5 → 6, N=25 → 26, N=100 → 101.
  - Bytes added at the trigger, for S3 = 1/4/16 MiB: 1,048,576 / 4,194,304 / 16,777,216 B for **every** N. The added count is always exactly 1.
- Tag `under`: L1 is under its byte target and L0 is empty, so `getCompactionCandidates()` returns `null` for all 200 calls (`LeveledManifest.java:291-292`), and counter3 stays 0.

**B2g. Readings.**

| Observation | Meaning |
|---|---|
| Trigger call = N+1 for each N; bytes added = S3 exactly for each N; count added = 1 | Claim confirmed: the limit changes timing, not size. |
| Bytes added or count added changes with N (e.g. more sstables added for small N, or bytes ∝ N) | Claim refuted: the limit bounds a byte quantity. |
| Bytes added tracks S3 (1/4/16 MiB) while staying flat across N | Positive control moved and K1 stayed flat. Claim confirmed. |
| Bytes added does **not** track S3 | Instrument or set-up broken (e.g. `onDiskLength` not honouring the size override). Not confirmed; fix before reading K1. |
| `hasL3` never true for any N | Limit never reached or containment failed (check token ranges). Not confirmed. |
| Trigger call ≠ N+1 | The patch did not take effect (check grep or a stale class) or the counter is advanced elsewhere. Investigate. |
| `under`: candidates non-null or counter3 > 0 | The level-byte gate does not work as traced. A3 step 2 is wrong. |

**B2h. Controls.**
- K2 (S3 sweep) shows that the measured operand moves with bytes.
- K3 (`under`) shows that the byte cap (`maxBytesForLevel`) decides whether rounds happen at all.
- Printing counter3 directly confirms the counted quantity is rounds.
- Re-grepping line 69 before each run rules out a stale build.
- Each `run` uses a fresh `MockSchema.newCFS()` and manifest, so no state carries over.

### B3. Cluster tier

**B3a. Environment and build.**
- One Linux node, JDK 11, Ant. Local disk with ≥ 20 GB free at `$C=/mydata/ncl-cluster`. Do not use shared storage.
  ```
  mkdir -p $C && rsync -a ~/cassandra-5.0.9/ $C/cassandra-5.0.9/ && cd $C/cassandra-5.0.9
  ant realclean && ant jar && ant stress-build
  ```
- `conf/cassandra.yaml` in the copy:
  - `data_file_directories: [$C/data]`, `commitlog_directory: $C/commitlog`, `hints_directory: $C/hints`, `saved_caches_directory: $C/saved_caches`, `cdc_raw_directory: $C/cdc` (write the expanded paths).
  - `listen_address`/`rpc_address: 127.0.0.1`, seeds `127.0.0.1`.
  - `concurrent_compactors: 1`, so rounds are serial and countable.
  - `compaction_throughput: 0MiB/s`, so compaction keeps up.
- `conf/cassandra-env.sh`: `MAX_HEAP_SIZE=2G`, `HEAP_NEWSIZE=400M`.
- `conf/logback.xml`: unchanged. `debug.log` has no threshold, and TRACE for one class is turned on at runtime.

**B3b. Knobs.**
- **K1, `NO_COMPACTION_LIMIT` ∈ {5, 25 (stock), 50, 1000000 ("effectively off")}.** For each arm: patch line 69 in `$C/cassandra-5.0.9` with the `sed` of B2e, `grep` to confirm, `ant jar` (incremental), then start the node on a **wiped** data dir. The 1000000 arm is the positive control for the mechanism itself.
- Fixed table options: `sstable_size_in_mb` 1 → 4 (ALTER between phases), `fanout_size` 10, `single_sstable_uplevel false` (every round is a real, logged compaction), compression off (bytes predictable).

**B3c. Workload.** This creates starvation the way the docs describe (an sstable-size change), with overwrites so stranded data is reclaimable.
1. Schema (cqlsh):
   ```
   CREATE KEYSPACE keyspace1 WITH replication = {'class':'SimpleStrategy','replication_factor':1};
   CREATE TABLE keyspace1.standard1 (key blob PRIMARY KEY, "C0" blob, "C1" blob, "C2" blob, "C3" blob, "C4" blob)
     WITH compression = {'enabled':'false'}
     AND compaction = {'class':'LeveledCompactionStrategy','sstable_size_in_mb':'1','fanout_size':'10','single_sstable_uplevel':'false'};
   ```
2. **Phase 1, fill L1..L3.**
   - `tools/bin/cassandra-stress write n=200000 -pop seq=1..200000 -col n=FIXED\(1\) size=FIXED\(1000\) -rate threads=8 throttle=5000/s -node 127.0.0.1`
   - About 200k × ~1.05 KB ≈ 210 MB. With 1 MiB sstables: L1 target 10 MiB, L2 100 MiB, so L3 receives ≈ 100 MB, i.e. ≈ 90–110 one-MiB sstables.
   - Then `nodetool flush keyspace1 standard1` and wait for `nodetool compactionstats` to show 0 pending.
3. **ALTER**:
   - `ALTER TABLE keyspace1.standard1 WITH compaction = {'class':'LeveledCompactionStrategy','sstable_size_in_mb':'4','fanout_size':'10','single_sstable_uplevel':'false'};`
   - New targets: L1 40 MiB, L2 400 MiB, L3 4 GiB. L3 can no longer be a source, and L2 (≈100 MB) is far from its target, so L3 is only a target if L2 exceeds 400 MiB. This rebuilds the manifest, so the counters restart at 0 (A3 step 6).
4. **Phase 2, five overwrite passes** of the same 200k keys:
   - `for p in 1 2 3 4 5; do tools/bin/cassandra-stress write n=200000 -pop seq=1..200000 -col n=FIXED\(1\) size=FIXED\(1000\) -rate threads=8 throttle=5000/s -node 127.0.0.1; done`
   - That is ≈ 1.05 GB written, about 40 s per pass.
   - L1 fills past 40 MiB and L1→L2 rounds begin. Expected rounds ≈ (1.05 GB − 40 MB) / 4 MiB ≈ 240 (accept 150–350).
   - Each L1 4 MiB sstable spans about 1/10 of the ring, and each L3 1 MiB sstable about 1/100, so about 10 L3 sstables fall inside a typical candidate span. Nearly every round past the limit can add one.
   - Reaching the limit needs N+1 rounds: 6 / 26 / 51 ≪ 240. Draining ≈ 100 L3 sstables needs ≈ 100 more rounds, so all finite arms should drain within the run.
5. Quiesce: `nodetool flush`, wait for 0 pending compactions, then 60 s idle.

**B3d. Observables and instruments.**
- (1) **Actual disk**, sampled every 10 s from phase 1 to the end into `$C/arm-N/disk.csv`:
  - `du -sb $C/data/keyspace1`
  - `nodetool tablestats keyspace1.standard1`: `Space used (live)` and `SSTables in each level` (`TableStatsPrinter.java:94,100`).
- (2) **Rounds and triggers**:
  - `grep -c "to level=2" $C/cassandra-5.0.9/logs/system.log` counts L1→L2 rounds (`CompactionTask.java:274`).
  - `grep -c "to level=3"` should be 0 during phase 2 (validity check).
  - `grep "Adding high-level (L3)" logs/system.log` gives the trigger times and count (`LeveledManifest.java:383`).
- (3) **Counter**:
  - Turn on `nodetool setlogginglevel org.apache.cassandra.db.compaction.LeveledManifest TRACE` right after the ALTER.
  - `grep "CompactionCounter: 3:" logs/debug.log` gives per-round counter values (`LeveledManifest.java:349-353`).
- (4) **Heap**, for completeness: `nodetool info | grep Heap` every 10 s. No difference is expected.
- (5) **End-state floor**: after the reading, `nodetool compact keyspace1 standard1`, then `Space used (live)` again.
- Not directly observable: per-key shadowing inside sstables. It is inferred from the live size and from the before/after major compaction.

**B3e. Procedure** (per arm N, in order 25, 5, 50, 1000000).
1. Patch line 69 to N, `grep` to confirm, `ant jar`.
2. Clean state: `rm -rf $C/data $C/commitlog $C/hints $C/saved_caches $C/cdc logs/*`.
3. `bin/cassandra -p $C/cassandra.pid`. Wait for `nodetool status` to show `UN`.
4. Start the disk sampler in the background (`while true; do ...; sleep 10; done > $C/arm-N/disk.csv &`, saving its PID).
5. Schema, phase 1, quiesce, then record `SSTables in each level` and `Space used (live)` (= **P1**).
6. ALTER, then `setlogginglevel ... TRACE`, then phase 2, then quiesce. Record **Q** (= `Space used (live)`), the L3 sstable count, the rounds `R`, the trigger count `T`, and the first trigger's round index.
7. `nodetool compact keyspace1 standard1`, wait, then record **F** (the floor).
8. Stop: `kill $(cat $C/cassandra.pid)`, kill the sampler, then `pgrep -f CassandraDaemon` and `pgrep -f cassandra-stress` should be empty. Copy `logs/` to `$C/arm-N/`.

**B3f. Predictions** (before any run).
- **P1** is the same across arms within ±5% (≈ 200–230 MB). With no overwrites in phase 1, a triggered pull reclaims nothing.
- Phase 2 `to level=3` count = 0 in every arm. Otherwise the arm is invalid (L3 was targeted normally) and is rerun with 4 passes.
- First "Adding high-level (L3)" happens at L1→L2 round N+1 after the ALTER (TRACE `CompactionCounter: 3:` reaches N+1 there): rounds 6 / 26 / 51. For N = 1000000 there are no triggers.
- Each trigger adds exactly one 1 MiB L3 sstable. `T` ≤ `R − N`.
- End L3 sstable count: ≈ 0 (≤ 5) for N ∈ {5, 25, 50}; ≈ phase-1 L3 count (90–110) for N = 1000000.
- **Q**:
  - Q(5), Q(25), Q(50) are equal within ±5%.
  - Q(1000000) ≥ Q(25) + 50 MB, because ≈ 100 MB of fully shadowed L3 versions are still stranded.
  - No finite-N arm differs from another by more than one L3 sstable's worth per remaining L3 sstable.
- **F** is equal across all four arms within ±5% (≈ 210 MB, one version per key), and F ≤ every Q.
- Heap is not distinguishable across arms.

**B3g. Readings.**

| Observation | Meaning |
|---|---|
| Q(5) ≈ Q(25) ≈ Q(50) (±5%) and Q(1000000) clearly higher; F equal in all arms | Claim confirmed. The limit sets when stranded data is reclaimed; finite values do not cap or set the disk use. The mechanism works (the off arm differs). |
| Q rises steadily with N among finite arms (e.g. Q(50) − Q(5) > 10% with every arm's R > N + L3 count) | Claim refuted: usage follows the limit at practical horizons. |
| Q flat across all four arms including 1000000, while F < Q (reclaimable bytes exist) | The mechanism never acted. Check `T`, the containment, and whether `to level=3` > 0. Not confirmed. |
| Q flat across all arms and F ≈ Q | The workload has nothing to reclaim (the positive control did not move). Not confirmed; raise the overwrite passes. |
| Trigger round ≠ N+1 | Patch not active, or the counter advanced by failed `tryModify` loops (A3 step 6). Note it and recount from the TRACE lines. |
| `to level=3` > 0 in phase 2 | L2 overflowed and L3 was targeted, resetting the counter. Arm invalid; rerun with fewer passes. |
| Heap differs systematically across arms | Unexpected. Investigate; this would contradict A2. |

**B3h. Controls.**
- The positive controls are the N = 1000000 arm (the same workload with the mechanism off moves disk) and the major-compaction floor F (the reclaimable bytes exist, and the instruments see them).
- Each arm has a fresh data dir and the same stress commands and seeds (`-pop seq`), so arms differ only in line 69.
- `concurrent_compactors: 1` and `single_sstable_uplevel false` make rounds countable.
- The `to level=3` check rules out normal L3 targeting.
- The P1 equality check rules out differences in the starting level layout.
- If time allows, run the stock N=25 arm twice to measure the run-to-run spread used for the ±5% band.

**B4. Risks and cleanup.**
- **Disk**: the unit tier uses < 1 GB (mock sstable files under the copy's `build/test`). The cluster tier peaks at about 1.5 GB of data plus commit log under `$C`; a single node with 20 GB local disk is enough. Do not point any directory at shared storage.
- **Shared source**: only the copies under `$W` and `$C` are patched and built. `~/cassandra-5.0.9` is never modified.
- **Processes**: after each arm, kill the Cassandra PID, the sampler and any stress. Then check that `pgrep -f CassandraDaemon`, `pgrep -f cassandra-stress` and `pgrep -f NoCompactionLimitProbeTest` print nothing.
- **Cleanup**: `rm -rf $C/data $C/commitlog $C/hints $C/saved_caches $C/cdc` between arms. At the end, keep `$C/arm-*/` and `$W/probe-*.csv` for the results, then `rm -rf $W $C` once they are copied out.
- **Restore** line 69 to 25 in any copy that is kept.

## C. Sources read

```
src/java/org/apache/cassandra/db/compaction/LeveledManifest.java
src/java/org/apache/cassandra/db/compaction/LeveledCompactionStrategy.java
src/java/org/apache/cassandra/db/compaction/LeveledGenerations.java
src/java/org/apache/cassandra/db/compaction/CompactionStrategyManager.java
src/java/org/apache/cassandra/db/compaction/CompactionTask.java
src/java/org/apache/cassandra/io/sstable/format/SSTableReader.java
src/java/org/apache/cassandra/dht/Range.java
src/java/org/apache/cassandra/tools/nodetool/stats/TableStatsPrinter.java
test/unit/org/apache/cassandra/db/compaction/LeveledCompactionStrategyTest.java
test/unit/org/apache/cassandra/db/compaction/LeveledGenerationsTest.java
test/unit/org/apache/cassandra/schema/MockSchema.java
tools/stress/src/org/apache/cassandra/stress/settings/SettingsSchema.java
doc/modules/cassandra/pages/managing/operating/compaction/lcs.adoc
CHANGES.txt
NEWS.txt
conf/cassandra.yaml
conf/cassandra-env.sh
conf/logback.xml
bin/cassandra.in.sh
build.xml
https://issues.apache.org/jira/browse/CASSANDRA-7414 (cited, not fetched)
```

## D. Stage-4 feedback

none yet
