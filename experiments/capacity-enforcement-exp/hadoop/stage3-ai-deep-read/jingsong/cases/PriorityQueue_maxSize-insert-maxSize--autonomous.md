# PriorityQueue_maxSize — verification solution  <!-- file: cases/PriorityQueue_maxSize-insert-maxSize--autonomous.md -->

| Field | Value |
|---|---|
| Entry pointer | [`PriorityQueue.java:74`](https://github.com/apache/hadoop/blob/rel/release-3.4.2/hadoop-common-project/hadoop-common/src/main/java/org/apache/hadoop/util/PriorityQueue.java#L74) — `if (size < maxSize){` in `org.apache.hadoop.util.PriorityQueue.insert(T)` |
| Pinned source | `rel/release-3.4.2` |
| Session / date | autonomous stage-3 agent, 2026-11-24 |
| Estimate | `negative` — the check bounds an element count in a heap array that `initialize(int)` has already allocated at full size, and `insert()` has no caller anywhere in the 3.4.2 tree, so no runtime memory or disk usage follows it. |
| Ground | (1) Dead path: the only two subclasses of `org.apache.hadoop.util.PriorityQueue` (`Merger.MergeQueue`, `SequenceFile.Sorter.MergeQueue`) fill the queue with `put()` after `initialize(segmentsToMerge.size())` and never call `insert()`; no test calls it either. (2) Even when called, the check does not limit allocation: the array of `maxSize+1` references is allocated in `initialize` (`PriorityQueue.java:51`) before any insert; `maxSize` is not a configuration value but the exact number of segments the caller is about to `put()`. The memory-relevant quantity in these merges (open segment readers and their buffers) is bounded by the merge factor at the callers (`Merger.java:667`, `SequenceFile.java:3656`), not by this check. |

Name parts: constraint `PriorityQueue_maxSize` (field `maxSize`, qualified with its class because
`maxSize` is a common field name in the tree), function `insert`, operand `maxSize`.

## A. Constraint trace

**A1. The constraint.**
- Name: the instance field `maxSize` of `org.apache.hadoop.util.PriorityQueue<T>`.
- Kind: hard-coded variable (a per-instance field set by code), not a configuration key, not a JVM
  property.
- First declared: [`PriorityQueue.java:32`](https://github.com/apache/hadoop/blob/rel/release-3.4.2/hadoop-common-project/hadoop-common/src/main/java/org/apache/hadoop/util/PriorityQueue.java#L32)
  (`private int maxSize;`). Its only assignment is in `initialize(int maxSize)`
  (`PriorityQueue.java:48-53`, assignment at `:52`), which also allocates `heap = new Object[maxSize + 1]`
  (`:50-51`).
- No `*-default.xml` entry (not a key).
- Unit: number of elements (references).
- Default: none; `0` until a subclass calls `initialize`. The class Javadoc says "Subclass
  constructors must call this" (`:44`).
- How it is set: only by subclass code. The two subclasses in the tree set it per merge pass to the
  number of segments they will merge:
  - `Merger.MergeQueue.merge(...)`: `initialize(segmentsToMerge.size())` (`Merger.java:676`),
    followed by `put(segment)` for every one of them (`Merger.java:678-680`).
  - `SequenceFile.Sorter.MergeQueue.merge()`: `initialize(segmentsToMerge.size()); clear();`
    (`SequenceFile.java:3664`), followed by `put(...)` for each (`:3665-3667`).
  - The size of `segmentsToMerge` is bounded indirectly by the merge factor, which is user-tunable:
    `mapreduce.task.io.sort.factor` (`MRJobConfig.java:317`, default `10` at `MRJobConfig.java:319`
    and `mapred-default.xml:41-42`; read in `MergeManagerImpl.java:179-180` for the reduce side and
    passed into `Merger.merge`), with in-memory segments added on top in the first pass
    (`Merger.java:633-636`, `factor += inMem`); and `seq.io.sort.factor` (`CommonConfigurationKeysPublic.java:338-340`,
    default `100`, `core-default.xml:4204-4205`), with the deprecated `io.sort.factor` taking precedence
    if set (`SequenceFile.java:2964-2971`). These factors are the "primary" tunables that reach
    `maxSize`, but they reach it only as "how many segments this pass merges", not as a separate cap.
  - Not settable by configuration, `-D`, or any admin command. A change in the factor applies to the
    next job (`mapreduce.task.io.sort.factor` is per-job) or the next `SequenceFile.Sorter`
    construction (`seq.io.sort.factor`); no daemon restart.
- Which process reads it: whichever JVM runs the merge — MapReduce map and reduce task JVMs
  (`Merger`) and any client or task that uses `SequenceFile.Sorter` (e.g. the DistCp client,
  `DistCpUtils.java:469-480`, `CopyListing.java:155`; `CopyCommitter.java:392`; `DistCh.java:488`).

**A2. What it caps.** Nominally the number of elements held in the binary heap array `heap`
(`PriorityQueue.java:30`) when elements are added through `insert()`. The quantity compared is the
current element count `size` (`:31`). The memory of the array itself, `(maxSize+1)` references
(≈ `16 + 4·(maxSize+1)` bytes with compressed oops), is fixed at `initialize` time and is not
affected by the check. The elements are `Segment` / `SegmentDescriptor` objects that the caller
already created and holds in its own `segmentsToMerge` list, so the queue adds only references.
In practice: no memory- or disk-significant resource is capped by this check.

**A3. Mechanism.**
1. A subclass calls `initialize(n)` (`PriorityQueue.java:48-53`): `size = 0`, allocates
   `heap = new Object[n+1]`, sets `maxSize = n`.
2. `insert(element)` (`PriorityQueue.java:73-85`) checks
   [`if (size < maxSize){`](https://github.com/apache/hadoop/blob/rel/release-3.4.2/hadoop-common-project/hadoop-common/src/main/java/org/apache/hadoop/util/PriorityQueue.java#L74):
   - true (room left): `put(element)` (`:75`) → `size++`, `heap[size] = element`, `upHeap()`
     (`:61-65`); returns `true`.
   - false (full), and `size > 0 && !lessThan(element, top())` (`:78`): the new element replaces
     the root `heap[1]` (`:79`) and `adjustTop()` re-heapifies (`:80`); the old root reference is
     dropped; returns `true`. Size does not grow.
   - otherwise: element rejected, returns `false` (`:83-84`).
   So when the limit is reached, `insert` keeps a top-`maxSize` set and does not grow the array.
3. Bypass: `put(T)` (`:61-65`) is public and has no bound check; adding more than `maxSize` elements
   with `put` throws `ArrayIndexOutOfBoundsException` at `heap[size] = element` (`:63`), as the
   Javadoc says (`:57-58`). Both production subclasses use `put`, not `insert`
   (`Merger.java:678-680`, `SequenceFile.java:3665-3667`), and they put exactly `n` elements after
   `initialize(n)`, so neither the check nor the exception is reached.
4. Reachability: `grep` over every `.java` file in the tree finds only three `extends PriorityQueue`
   classes; `Metrics2Util.TopN` (`Metrics2Util.java:20,74`) extends `java.util.PriorityQueue`, not
   this one. Only `SequenceFile.java:49` and `Merger.java:44` import
   `org.apache.hadoop.util.PriorityQueue`; the wildcard `import org.apache.hadoop.util.*` files do
   not mention `PriorityQueue`, and the same-package `LightWeightCache` imports
   `java.util.PriorityQueue` (`LightWeightCache.java:22`). Neither subclass, nor any test, calls
   `insert(`. The check at `:74` is therefore unreachable in a 3.4.2 build (unless third-party code
   on the classpath subclasses this `@InterfaceAudience.Private` class, `:27-28`).

**A4. Other consumers.** The memory a merge really uses is outside this check:
- Each segment in `segmentsToMerge` holds an open reader with its input buffer
  (`Merger.java:648-653`, "Initialize the segment at the last possible moment ... buffers"); how many
  are open at once is bounded by the pass factor (`Merger.java:633-636, 667-668`;
  `SequenceFile.java:3656-3657`), i.e. by `mapreduce.task.io.sort.factor` / `seq.io.sort.factor`
  (plus in-memory segments on the reduce side).
- In-memory map outputs on the reduce side (`MergeManagerImpl`, shuffle buffer keys) and the map-side
  sort buffer (`mapreduce.task.io.sort.mb`).
- Intermediate merge files on local disk (`Merger.java` intermediate pass output via
  `LocalDirAllocator`; `SequenceFile.java:3683-3690`), sized by the data.

**A5. Evidence beyond the source.** The class Javadoc (`PriorityQueue.java:24-26, 43-45, 55-59, 67-72`)
describes `insert` as a bounded top-k insert and `put` as unchecked. Existing tests that drive the
two subclasses: `hadoop-mapreduce-client-core/src/test/java/org/apache/hadoop/mapreduce/task/reduce/TestMerger.java`
and `hadoop-mapreduce-client-jobclient/src/test/java/org/apache/hadoop/io/TestSequenceFileMergeProgress.java`.
The class has been in the public API diff files since 0.17 (`hadoop-common/dev-support/jdiff/hadoop_0.17.0.xml:42013`),
i.e. old code; no JIRA relied on.

## B. Verification solution

**B1. Claim under test.** In Hadoop 3.4.2 no workload reaches `PriorityQueue.insert`, so the
check `size < maxSize` at `PriorityQueue.java:74` is never evaluated, and the memory of a
`PriorityQueue` (its heap array) is set by the `initialize(n)` argument alone: whatever is inserted,
the array length stays `n+1` and no allocation follows the number of inserts. The claim is
refuted if `insert` is reached in any real merge, or if memory held by the queue grows with the
number of elements offered rather than staying at the `initialize` size.

### B2. Unit tier

**B2a. Environment and build.** JDK 8 (HotSpot, 64-bit, `-Xmx512m` so compressed oops are on), Maven
3.3+. Work in a private copy of the tag on local disk, e.g.
`rsync -a ~/hadoop-3.4.2/ /mydata/<run>/src/` (never in the shared tree). Build:
`cd /mydata/<run>/src && mvn -pl hadoop-common-project/hadoop-common,hadoop-mapreduce-project/hadoop-mapreduce-client/hadoop-mapreduce-client-core -am install -DskipTests -Dmaven.javadoc.skip=true`.
New test file (in the copy only):
`hadoop-common-project/hadoop-common/src/test/java/org/apache/hadoop/util/TestPriorityQueueInsertCap.java`.
JVM options for surefire: `-DargLine="-Xmx512m -XX:+UseCompressedOops -XX:-UseTLAB"` (TLAB off
makes `getThreadAllocatedBytes` exact per allocation).

> **Amendment A1 (stage-4 audit, 2026-11-24, before any reading).** Environment as run: private copy
> `/mydata/jingsong-s4/PriorityQueue_maxSize-insert-maxSize-run1/src` made with Jingsong's `copy-source.sh` (tag
> `rel/release-3.4.2`); no `install` build — the 3.4.2 artifacts of every module are in `~/.m2` from the node's base
> build (`environment.md` §3), so `mvn test` runs in each module directly. Surefire JVM options are passed as
> `-Dmaven-surefire-plugin.argLine="..."` (the module poms set `<argLine>${maven-surefire-plugin.argLine} ...`, so a plain
> `-DargLine` is ignored); the same goes for `-Dpqcap.factor=<f>` of `TestSequenceFileSorterMerge`. JDK 8
> `1.8.0_504`, Maven 3.6.3. The harness is `harness/` beside the results file (`unit-run.sh`, `jdbcount.sh`,
> `scan_insert.py`, the two test classes).

**B2b. Knobs.**
- `k` = argument to `initialize` (= `maxSize`): `1, 16, 1024, 65536` — from the degenerate case to a
  size whose array (≈ 256 KiB) is well above measurement noise.
- `N` = elements offered via `insert`: fixed at `200000` (≥ 3·k for every k), plus `N = k/2` for
  `k ≥ 16` (below the limit, so the `true` branch alone is exercised).
- For the reachability part: `mapreduce.task.io.sort.factor` / `seq.io.sort.factor` are not
  directly knobs of `maxSize`; they are varied in the reachability runs as `2` and `100` via the
  test's `Configuration` / `JobConf`.

**B2c. Workload.**
Part 1 (mechanism, direct). Test-only subclass:

```java
static final class LongQ extends PriorityQueue<Long> {
  LongQ(int n) { initialize(n); }
  @Override protected boolean lessThan(Object a, Object b) { return (Long) a < (Long) b; }
}
```

For each k: pre-create `Long[] items` of `N` distinct values `0..N-1` in shuffled order (allocated
before measuring, kept alive throughout). Measure allocation of `new LongQ(k)`, then of a loop
`for (Long x : items) q.insert(x)`. With N = 200000 and k ≤ 65536, the limit `size == k` is reached
after k inserts and the `false` branch of `:74` runs for the remaining `N-k` (≥ 134464) inserts.
Then, positive control, a fresh `LongQ(k)` filled with `put()` for `k+1` elements.

Part 2 (reachability, real callers). Run the existing tests that drive both subclasses through
real merges, with breakpoints on `PriorityQueue.insert` and `PriorityQueue.initialize`:
`TestMerger` (hadoop-mapreduce-client-core) and `TestSequenceFileMergeProgress`
(hadoop-mapreduce-client-jobclient), plus a small added test in the copy,
`TestSequenceFileSorterMerge` (hadoop-common, `org.apache.hadoop.io`), that writes 50 000 random
`IntWritable`→`BytesWritable(100 bytes)` records to a local SequenceFile and runs
`new SequenceFile.Sorter(localFs, IntWritable.class, BytesWritable.class, conf).sort(in, out)` with
`seq.io.sort.mb=1` (run memory limit = 1 MiB / 4 = 256 KiB, `SequenceFile.java:3079`, so ≈ 5.5 MB of
records gives ≈ 20 runs) and `seq.io.sort.factor` ∈ {2, 100}, forcing `mergePass` →
`MergeQueue.merge()` (`SequenceFile.java:3018-3021, 3458-3470, 3623-3667`); with factor 2 there are
multiple intermediate passes.

**B2d. Observables and instruments.**
- `q.size()` after the loop (the check's usage-side operand).
- `heap.length` before and after, via reflection (`Field f = PriorityQueue.class.getDeclaredField("heap"); f.setAccessible(true)`).
- `maxSize` via reflection (the limit operand).
- Bytes allocated by the current thread across (a) the constructor and (b) the insert loop:
  `((com.sun.management.ThreadMXBean) ManagementFactory.getThreadMXBean()).getThreadAllocatedBytes(Thread.currentThread().getId())`
  read before and after each step.
- Count of `insert` returns `true` / `false`.
- Part 2: `jdb` breakpoint-hit counts for `org.apache.hadoop.util.PriorityQueue.insert` and
  `org.apache.hadoop.util.PriorityQueue.initialize`, and the `maxSize` argument at each
  `initialize` hit (`print maxSize` is not needed: `jdb` prints the method entry; add `locals`
  after each `initialize` hit if values are wanted).
- Not observable directly: retained heap of the queue as a whole (no JOL on the classpath); the
  reflection reading of `heap.length` stands in for it.

> **Amendment A2 (stage-4 audit, 2026-11-24, before any reading).** Measurement made exact: (i) `items` is a fixed
> shuffle of `0..N-1` (seed `20261124`); the `N = k/2` rows offer its first `k/2` items. (ii) Before any recorded
> reading, three warm-up passes (`new LongQ(1024)` + 200,000 inserts) load the classes and JIT the paths. (iii) Every
> allocation reading is baseline-subtracted: baseline = median of 21 empty windows (two back-to-back counter reads),
> taken before each (k, N) row. (iv) Instrument known answer before the readings: `new Object[1024]` must read
> 4,112 B (16 + 4·1,024) within +64 B. (v) Part 1 is repeated three times (B2h) in one JVM. (vi) jdb known answer
> before Part 2: `TestPriorityQueueInsertCap#testJdbKnownAnswer` (`-Dpqcap.jdbcheck=true`) under the same debugger
> script must give `insert` = 5 and `initialize` = 1 hits — this shows that a 0 count of `insert` is meaningful.
> (vii) The `initialize` argument values are not recorded (the jdb script prints method entries only; B2d marks them
> optional).

**B2e. Procedure.**
1. Copy and build as in B2a.
2. Write `TestPriorityQueueInsertCap` with one `@Test` per (k, N), printing one line per case:
   `k N size heapLenBefore heapLenAfter allocCtor allocInsertLoop trues falses`, and asserting
   nothing (the readings are judged against B2f). Add a `@Test` for the `put` control that catches
   `ArrayIndexOutOfBoundsException` and prints at which put number it was thrown.
3. Run: `cd /mydata/<run>/src/hadoop-common-project/hadoop-common && mvn test -Dtest=TestPriorityQueueInsertCap -DargLine="-Xmx512m -XX:-UseTLAB" -DfailIfNoTests=false | tee /mydata/<run>/unit-part1.log`.
4. Reachability, per test class (one at a time):
   ```
   cd /mydata/<run>/src/<module>
   mvn test -Dtest=<TestClass> -Dmaven.surefire.debug="-agentlib:jdwp=transport=dt_socket,server=y,suspend=y,address=5005" \
     -D<factor key>=<2|100> > /mydata/<run>/mvn-<TestClass>-<f>.log 2>&1 &
   # wait until the log shows "Listening for transport dt_socket at address: 5005"
   { echo "stop in org.apache.hadoop.util.PriorityQueue.insert";
     echo "stop in org.apache.hadoop.util.PriorityQueue.initialize";
     while sleep 0.05; do echo cont; done; } | jdb -attach localhost:5005 > /mydata/<run>/jdb-<TestClass>-<f>.log 2>&1
   grep -c "Breakpoint hit:.*PriorityQueue.insert" /mydata/<run>/jdb-<TestClass>-<f>.log
   grep -c "Breakpoint hit:.*PriorityQueue.initialize" /mydata/<run>/jdb-<TestClass>-<f>.log
   ```
   (`TestMerger` reads the factor from its own `JobConf`; if it ignores `-D`, run it once as is.
   `TestSequenceFileSorterMerge` sets the factor from a system property passed through
   `-DargLine`.) The pipe ends when `jdb` exits with the test JVM.
5. Static scan of the built module jars for any call site of `insert` on this class or its
   subclasses:
   ```
   for j in $(find /mydata/<run>/src -path '*/target/*.jar' -name 'hadoop-*.jar' ! -name '*tests*' ! -name '*sources*'); do
     unzip -l "$j" | awk '{print $4}' | grep '\.class$' | sed 's/\.class$//' | tr / . > /tmp/cls.$$ ;
     javap -c -p -cp "$j" $(cat /tmp/cls.$$) 2>/dev/null | grep -E 'Method (org/apache/hadoop/util/PriorityQueue|org/apache/hadoop/mapred/Merger\$MergeQueue|org/apache/hadoop/io/SequenceFile\$Sorter\$MergeQueue)\.insert' && echo "HIT in $j";
   done; rm -f /tmp/cls.$$
   ```
   (Use a run-private temp file under `/mydata/<run>/` instead of `/tmp` if preferred.)

> **Amendment A3 (stage-4 audit, 2026-11-24, before any reading).** Step 4: the debugger loop is `jdbcount.sh`
> (waits until the port listens, sets the two breakpoints, resumes every 50 ms until the JVM exits, then counts
> `Breakpoint hit:` lines). `TestMerger` and `TestSequenceFileMergeProgress` build their own `JobConf` and do not read
> a factor from `-D`; each is run once as is (as the note above allows). Step 5: `mvn test` builds no module jar, so
> the static scan reads the compiled `target/classes` of `hadoop-common` and `hadoop-mapreduce-client-core` in the
> copy, plus `hadoop-common`'s `target/test-classes` as the scanner's known answer (`TestPriorityQueueInsertCap` calls
> `insert`, so it must report HITs there and nowhere else). The scanner (`scan_insert.py`) replaces the `javap` loop:
> it finds every subclass of `org.apache.hadoop.util.PriorityQueue` from each class file's superclass entry (not only
> classes named `MergeQueue`), disassembles every class whose constant pool names the class or a subclass, and reports
> each `invoke* <PriorityQueue or subclass>.insert:(Ljava/lang/Object;)Z`. The cluster-tier scan (B3d) uses the same
> scanner over every jar under `hadoop/share`.

**B2f. Predictions.**
- Part 1, every k with N = 200000: `size == k`; `heapLenBefore == heapLenAfter == k+1`;
  `trues + falses == 200000`; `trues ≥ k`; `allocCtor ≈ 24 (object) + 16 + 4·(k+1)` rounded up to
  8 bytes — for k = 65536 about 262 KB, for k = 1024 about 4.2 KB, for k = 1 about 48 B (linear in k);
  `allocInsertLoop` ≤ a few KB (no allocation in `insert`/`put`/`adjustTop`), and the same order for
  every k.
- Part 1, N = k/2: `size == k/2`, `falses == 0`, `heap.length == k+1` (array already full size even
  though only half used — memory follows `initialize`, not inserts).
- Part 1 control: `put()` throws `ArrayIndexOutOfBoundsException` on put number `k+1`.
- Part 2: `insert` hit count = **0** for every test and factor; `initialize` hit count ≥ 1 for every
  test (for the Sorter test with factor 2 and ≈ 20 runs, ≥ 10 hits; with factor 100, exactly 1),
  with each `initialize` argument ≤ factor (+ in-memory segments on the Merger reduce path).
- Part 3 (static scan): no `HIT` lines.

> **Amendment A4 (stage-4 audit, 2026-11-24, before any reading) — predictions in exact numbers.** With compressed
> oops, `LongQ` = 24 B and `Object[k+1]` = align8(16 + 4·(k+1)), so P(k) = 48 / 112 / 4,144 / 262,192 B for
> k = 1 / 16 / 1,024 / 65,536. Every row: baseline-subtracted `allocCtor` ∈ [P(k), P(k) + 64]; `allocInsertLoop`
> ≤ 4,096 B for every k and both N (flat: no row exceeds 4,096 B, so it cannot follow k or N); `heapLenBefore =
> heapLenAfter = k+1`; `maxSize = k`; full rows `size = k`, `trues + falses = 200,000`, `trues ≥ k`; half rows
> `size = k/2`, `falses = 0`. The three repeats differ by < 10 % of P(65,536) at k = 65,536. Control: `put` throws
> `ArrayIndexOutOfBoundsException` at put k+1 for each of the four k. Part 2 counts: `insert` = 0 in all four
> real-caller runs (Sorter f = 2, Sorter f = 100, `TestMerger`, `TestSequenceFileMergeProgress`); `initialize` ≥ 10
> (Sorter f = 2), exactly 1 (Sorter f = 100), ≥ 1 (each of the two existing tests); each run's tests pass. Part 3: no
> HIT in `target/classes` of either module.

**B2g. Readings.**

| Observation | Meaning |
|---|---|
| `insert` hits = 0 in all runs, `initialize` hits > 0, no static `HIT`, and Part 1 shows `heap.length` fixed at k+1 with `allocInsertLoop` flat across k while `allocCtor` scales with k | Claim confirmed: the check is not on any runtime path and memory follows `initialize`, not the check. |
| `insert` hit count > 0 in any real-caller run, or a static `HIT` | Claim refuted on reachability: some caller uses the bounded insert; re-examine which caller and whether its element count is memory-significant. |
| `allocInsertLoop` grows with N or with k, or `heap.length` changes after inserts | Claim refuted on mechanism: the queue's memory follows inserts (usage follows the constraint). |
| `size` ever exceeds k | Check broken (would contradict `:74`); report as a defect, claim refuted. |
| `initialize` hit count = 0 in Part 2 (control did not move) | Not confirmed: the merge path was not exercised; enlarge data / lower `seq.io.sort.mb` and rerun. |
| `allocCtor` does not scale with k (positive control flat) | Not confirmed: the allocation instrument is not working (check `-XX:-UseTLAB`, that the JVM is HotSpot). |

> **Amendment A5 (stage-4 audit, 2026-11-24, before any reading) — verdict words and missing rows.** The claim is
> negative ("does not cap"), so: row 1 → **Confirmed — does not cap** (all of A4 holds, including the controls);
> rows 2 and 3 → **Refuted — caps** (reachability or mechanism); row 4 → **Refuted** (check broken, report as a
> defect); rows 5 and 6 → **Not confirmed**. Added rows: (7) the jdb known answer (A2 vi) or the allocation known
> answer (A2 iv) fails, or the scanner reports no HIT in `TestPriorityQueueInsertCap` → **Invalid** (instrument); fix
> and rerun the tier. (8) A real-caller test fails or the Sorter output is not 50,000 sorted records → **Invalid**
> for that run (the merge did not run as designed). (9) `allocCtor` outside [P(k), P(k)+64] but still linear in k
> (slope 4 B per element ± 1 %) with everything else as row 1 → **Confirmed — does not cap**, with the layout
> difference recorded (the prediction of the array size is not the claim). (10) `allocInsertLoop` > 4,096 B in some
> row but not growing with k or N (spread across rows < 4,096 B of each other) → **Not confirmed** (noise in the
> instrument; rerun with more repeats).

**B2h. Controls.**
- Positive control 1: `allocCtor` vs k — the same instrument shown to move where the bound really
  binds (array allocation in `initialize`).
- Positive control 2: `put` past k throws — the real hard cap is the array length.
- Positive control 3: `initialize` breakpoint hits in Part 2 — proves `jdb` attached and the merge
  code ran, so a zero `insert` count is meaningful.
- Elements pre-allocated before measuring, so element creation is not counted.
- Repeat Part 1 three times; JIT/GC noise must stay below 10 % of `allocCtor` at k = 65536.

### B3. Cluster tier

**B3a. Environment and build.** One Linux host, pseudo-distributed: NameNode, DataNode,
ResourceManager, NodeManager (and optionally the JobHistory server) from a distribution built from
the tag in a private copy: `cd /mydata/<run>/src && mvn package -Pdist -DskipTests -Dtar -Dmaven.javadoc.skip=true`;
unpack `hadoop-dist/target/hadoop-3.4.2.tar.gz` to `/mydata/<run>/hadoop`. JDK 8 (or 11) with `jdb`
(part of the JDK). `etc/hadoop/hadoop-env.sh`: `export JAVA_HOME=...`, `HADOOP_HEAPSIZE_MAX=1g`,
`HADOOP_LOG_DIR=/mydata/<run>/logs`, `HADOOP_PID_DIR=/mydata/<run>/pids`.
- `core-site.xml`: `fs.defaultFS=hdfs://localhost:9000`, `hadoop.tmp.dir=/mydata/<run>/tmp`.
- `hdfs-site.xml`: `dfs.replication=1`, `dfs.namenode.name.dir=/mydata/<run>/nn`,
  `dfs.datanode.data.dir=/mydata/<run>/dn`.
- `yarn-site.xml`: `yarn.nodemanager.aux-services=mapreduce_shuffle`,
  `yarn.nodemanager.resource.memory-mb=6144`, `yarn.scheduler.maximum-allocation-mb=2048`,
  `yarn.nodemanager.local-dirs=/mydata/<run>/nm-local`, `yarn.nodemanager.log-dirs=/mydata/<run>/nm-logs`,
  `yarn.nodemanager.vmem-check-enabled=false`.
- `mapred-site.xml`: `mapreduce.framework.name=yarn`,
  `yarn.app.mapreduce.am.env`/`mapreduce.map.env`/`mapreduce.reduce.env` = `HADOOP_MAPRED_HOME=/mydata/<run>/hadoop`.
- Local disk needed: ≈ 3 GB (200 MB input, shuffle and intermediate merges, output).

**B3b. Knobs.**
- `mapreduce.task.io.sort.factor` ∈ {2, 10 (default), 100}, per job via `-D` — the only user-facing
  value that reaches `maxSize` (through `segmentsToMerge.size()`); 2 forces many multi-pass merges
  (many `initialize` calls), 100 a single pass.
- `seq.io.sort.factor` ∈ {2, 100} for the DistCp client workload, via `-D` on the `hadoop distcp`
  command (the client JVM builds the `Sorter`).
No restart: both are per-job / per-client.

**B3c. Workload.**
- A (MapReduce reduce-side merge, `Merger.MergeQueue`):
  `hadoop jar share/hadoop/mapreduce/hadoop-mapreduce-examples-3.4.2.jar teragen -Dmapreduce.job.maps=4 2000000 /tg`
  (2 000 000 × 100 B = 200 MB), then
  `terasort -Dmapreduce.job.reduces=1 -Dmapreduce.input.fileinputformat.split.maxsize=8388608 -Dmapreduce.task.io.sort.mb=4 -Dmapreduce.task.io.sort.factor=<f> -Dmapreduce.reduce.shuffle.input.buffer.percent=0.05 -Dmapreduce.job.reduce.slowstart.completedmaps=1.0 -Dmapreduce.reduce.speculative=false -Dmapreduce.reduce.maxattempts=1 -Dmapreduce.task.timeout=1800000 -Dmapreduce.reduce.memory.mb=1024 "-Dmapreduce.reduce.java.opts=-Xmx768m -agentlib:jdwp=transport=dt_socket,server=y,suspend=y,address=5005" /tg /ts-<f>`.
  200 MB / 8 MB splits = 25 maps; with a 4 MB sort buffer each map spills ≥ 2–3 times and merges
  them map-side; the reducer receives 25 map outputs, most to disk (small shuffle buffer), so with
  factor 2 it runs many intermediate on-disk merges (`MergeManagerImpl.java:358` triggers at
  `2·factor−1` outputs) and a final multi-pass `Merger.merge`. Duration a few minutes.
- B (client-side `SequenceFile.Sorter`, `SequenceFile.Sorter.MergeQueue`): create 20 000 empty files
  in HDFS (`hdfs dfs -mkdir -p /many/d{000..099}` and a loop of `hdfs dfs -touchz` in batches, or
  a small `hdfs dfs -put` of a local tree), then
  `HADOOP_CLIENT_OPTS="-agentlib:jdwp=transport=dt_socket,server=y,suspend=y,address=5006" hadoop distcp -Dseq.io.sort.mb=1 -Dseq.io.sort.factor=<f> /many /many-copy-<f>`.
  The copy listing has 20 100 entries of a few hundred bytes (several MB) against a 256 KiB run
  limit, so `sortListing` (`CopyListing.java:155`) produces many runs and merges them.

> **Amendment A8 (stage-4 run 1, 2026-11-24 — runbook defect, §9a unchanged; the cluster tier restarts).** Workload B as
> written cannot reach the merge: in the DistCp client JVM the MapReduce deprecation table maps `io.sort.mb` and
> `io.sort.factor` to `mapreduce.task.io.sort.mb` / `mapreduce.task.io.sort.factor` (`ConfigUtil.java:173-176`), which
> `mapred-default.xml` sets (100 MB, 10). `SequenceFile.Sorter` reads `io.sort.mb` / `io.sort.factor` first whenever they
> are non-null (`SequenceFile.java:2957-2971`), so `-Dseq.io.sort.mb=1 -Dseq.io.sort.factor=<f>` is ignored there, the
> ~20,101-entry listing fits in one 25 MiB run, and no merge pass (and no `PriorityQueue` class load) happens — run 1's
> first attempt saw 0 `initialize` and 0 `insert` hits at both f (results §3). Fix: the distcp command also passes
> `-Dmapreduce.task.io.sort.mb=1 -Dmapreduce.task.io.sort.factor=<f>` (the keys the Sorter actually reads in that JVM;
> the copy job is map-only, so its maps do not use them). Claim, predictions and conclusions are unchanged.

**B3d. Observables and instruments.**
- `jdb` hit counts of `PriorityQueue.insert` and `PriorityQueue.initialize` in the reduce task JVM
  (A) and in the DistCp client JVM (B), recorded as in B2e step 4.
- Static scan (B2e step 5) over every jar in the distribution: `find /mydata/<run>/hadoop/share -name '*.jar'`
  (includes third-party jars in `lib/`), to cover callers outside the two modules.
- Reducer task log (`yarn logs -applicationId <id>`): the `Merger` lines "Merging N sorted segments"
  and "Merging N intermediate segments out of a total of M" (`Merger.java:607, 711-713`) as an
  independent count of merge passes, to tie `initialize` hits to real merges.
- Actual resource: the queue's array is at most `16 + 4·(f+inMem+1)` bytes (a few hundred bytes at
  f = 100), far below any RSS or `jstat` noise; it cannot be observed as a resource figure. The
  reduce container's peak RSS (`/proc/<pid>/status` `VmHWM`, sampled at the end of the job, or the
  NM container metrics) may be recorded for completeness; no relation to `maxSize` is predicted.

**B3e. Procedure.**
1. Build and unpack (B3a); `hdfs namenode -format`; `start-dfs.sh`; `start-yarn.sh`; `jps` shows
   NameNode, DataNode, SecondaryNameNode, ResourceManager, NodeManager.
2. Static scan over the distribution's jars; record any `HIT`.
3. Run teragen (A) once.
4. For f in 2, 10, 100: launch terasort (A) in the background; poll
   `yarn logs`/`nm-logs/.../stdout` or `ss -ltnp | grep 5005` until the reducer listens; attach `jdb`
   with the scripted breakpoints (B2e step 4, port 5005); when the job finishes, count hits; fetch
   the reducer log and count "Merging" lines; `hdfs dfs -rm -r -skipTrash /ts-<f>`.
5. Create the file tree for B; for f in 2, 100: run distcp with the client debug agent, attach
   `jdb` on 5006, count hits; `hdfs dfs -rm -r -skipTrash /many-copy-<f>`.
6. Clean up (B4).

> **Amendment A6 (stage-4 audit, 2026-11-24, before any reading).** As run (`cluster-run.sh`): B3a — the distribution
> is copied from the node's base build (`/mydata/jingsong-s4/hadoop-base/hadoop-dist/target/hadoop-3.4.2`, same tag;
> no rebuild); configuration in `<run>/conf` with the values of B3a (plus `yarn.nodemanager.resource.cpu-vcores=16`);
> step 1 starts NameNode, DataNode, ResourceManager and NodeManager with `hdfs|yarn --daemon start` (no SSH to
> `localhost`, so no `start-dfs.sh`; no SecondaryNameNode, which no step uses). Step 4: log aggregation is off, so the
> reducer's `syslog` is read from `yarn.nodemanager.log-dirs` (the container whose log names attempt `_r_000000`)
> instead of `yarn logs`. Step 5: the 20,000 empty files are a local tree of 100 directories × 200 files put with one
> `hdfs dfs -put` (the second option of B3c). The log cross-check of B3d/B3h is made exact: every `Merger.merge` call
> logs "Merging N sorted segments" once and calls `initialize` once per pass, and every non-final pass logs "Merging N
> intermediate segments out of a total of M" (`Merger.java:607, 676, 706-713`), so in the reducer JVM `initialize`
> hits = (sorted-segments lines) + (intermediate lines), exactly. The DistCp client has no such log line; its
> positive control is `initialize` hits at f = 2 > f = 100 ≥ 1. RSS is not recorded (B3d: optional, no prediction).

**B3f. Predictions.**
- `insert` hits = **0** in every run (A: f = 2, 10, 100; B: f = 2, 100); static scan: no `HIT`.
- `initialize` hits > 0 in every run; more at f = 2 than at f = 100 (A: tens at f = 2 versus a few
  at f = 100; B: ≥ 10 at f = 2 versus 1 at f = 100), matching the number of `Merger`/`Sorter`
  merge passes in the logs.
- No reduce-container memory difference attributable to `maxSize`; any RSS change between f values
  follows the number of simultaneously open segment streams (factor), not the check.

**B3g. Readings.**

| Observation | Meaning |
|---|---|
| `insert` = 0 everywhere, `initialize` > 0 and tracking the merge-pass count, no static `HIT` | Claim confirmed: on a real cluster the check at `:74` is never evaluated, so it caps nothing. |
| `insert` > 0 in any run or any static `HIT` | Claim refuted: a real path reaches the bounded insert; identify the caller and redo the trace. |
| `initialize` hits flat (0) at f = 2 and f = 100 | Not confirmed: workload did not reach the merge (positive control did not move); lower `mapreduce.task.io.sort.mb` / `seq.io.sort.mb` or raise data size. |
| `jdb` could not attach / no breakpoint ever reported | Not confirmed: instrument failure; check the port, `suspend=y`, and the JDK of the task JVM. |
| Reduce RSS changes with f | Expected from open segment streams (A4); not evidence for the check — compare against `initialize` hits, not against `insert`. |

> **Amendment A7 (stage-4 audit, 2026-11-24, before any reading) — verdict words.** Row 1 → **Confirmed — does not
> cap**, and it requires, besides `insert` = 0 in all five runs and no static HIT: `initialize` > 0 in every run,
> reducer `initialize` = log pass count (A6) at each f, f = 2 > f = 100 in both workloads, and every job successful.
> Row 2 → **Refuted — caps**. Rows 3 and 4 → **Not confirmed**. Added: reducer `initialize` ≠ log pass count, or a
> job failed → **Not confirmed** (the debugged JVM and the logged merges cannot be tied); row 5 is not a verdict row.

**B3h. Controls.**
- Positive control: the same workload moves the `initialize` hit count with the factor (the
  sibling bound that does bind is the merge factor / array allocation).
- Log cross-check of merge passes against `initialize` hits rules out a detached or misconfigured
  debugger.
- Static scan covers code paths the two workloads do not exercise (map-side merges, other tools).
- `mapreduce.reduce.maxattempts=1` and speculation off so exactly one reduce JVM is debugged.

**B4. Risks and cleanup.**
- Disk: ≈ 3 GB on `/mydata/<run>`; check `df -h /mydata` first; nothing on shared storage.
- Ports 5005/5006 (jdwp), 9000, 9870, 8088, 8042 etc.; ensure free (`ss -ltn`). `suspend=y` JVMs
  wait forever if `jdb` never attaches: kill them (`yarn application -kill <id>`, or `kill` the
  client) if a run is abandoned. Never leave a jdwp port open after the run.
- Unit tier: surefire debug fork waits on 5005 until `jdb` attaches; kill the `mvn` process if
  aborted.
- Cleanup: `hdfs dfs -rm -r -skipTrash /tg /ts-* /many /many-copy-*`; `stop-yarn.sh`; `stop-dfs.sh`;
  `mapred --daemon stop historyserver` if started; `jps` shows no Hadoop daemon, no `YarnChild`, no
  `Surefire`/`ForkedBooter`, no `jdb`; `rm -rf /mydata/<run>/{tmp,nn,dn,nm-local,nm-logs}` when
  results are saved.

## C. Sources read

hadoop-common-project/hadoop-common/src/main/java/org/apache/hadoop/util/PriorityQueue.java
hadoop-common-project/hadoop-common/src/main/java/org/apache/hadoop/metrics2/util/Metrics2Util.java
hadoop-common-project/hadoop-common/src/main/java/org/apache/hadoop/util/LightWeightCache.java (imports only)
hadoop-common-project/hadoop-common/src/main/java/org/apache/hadoop/io/SequenceFile.java (2955-2975, 3009-3030, 3079-3080, 3458-3500, 3538, 3552-3606, 3623-3700)
hadoop-mapreduce-project/hadoop-mapreduce-client/hadoop-mapreduce-client-core/src/main/java/org/apache/hadoop/mapred/Merger.java (385-400, 505-590, 600-720, 784-830)
hadoop-mapreduce-project/hadoop-mapreduce-client/hadoop-mapreduce-client-core/src/main/java/org/apache/hadoop/mapreduce/task/reduce/MergeManagerImpl.java (grep: 110, 179-180, 358, 572, 824)
hadoop-mapreduce-project/hadoop-mapreduce-client/hadoop-mapreduce-client-core/src/main/java/org/apache/hadoop/mapreduce/MRJobConfig.java (317-319)
hadoop-mapreduce-project/hadoop-mapreduce-client/hadoop-mapreduce-client-core/src/main/resources/mapred-default.xml (41-44)
hadoop-common-project/hadoop-common/src/main/java/org/apache/hadoop/fs/CommonConfigurationKeysPublic.java (313-340)
hadoop-common-project/hadoop-common/src/main/resources/core-default.xml (4204-4207)
hadoop-tools/hadoop-distcp/src/main/java/org/apache/hadoop/tools/util/DistCpUtils.java (450-480)
hadoop-tools/hadoop-distcp/src/main/java/org/apache/hadoop/tools/CopyListing.java (155, grep)
hadoop-tools/hadoop-distcp/src/main/java/org/apache/hadoop/tools/mapred/CopyCommitter.java (392, grep)
hadoop-tools/hadoop-extras/src/main/java/org/apache/hadoop/tools/DistCh.java (488, grep)
Tree-wide greps: `extends PriorityQueue`, `org.apache.hadoop.util.PriorityQueue`, `import org.apache.hadoop.util.*`, `boolean lessThan(`, `insert(`
hadoop-common-project/hadoop-common/dev-support/jdiff/hadoop_0.17.0.xml (grep hit only)
playbook-autonomous.md, _TEMPLATE-autonomous.md

## D. Stage-4 feedback

none yet
