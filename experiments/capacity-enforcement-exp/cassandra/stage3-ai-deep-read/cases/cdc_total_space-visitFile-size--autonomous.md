# cdc_total_space — verification solution  <!-- file: cases/cdc_total_space-visitFile-size--autonomous.md -->

| Field | Value |
|---|---|
| Entry pointer | the given line, **linked**: [`DirectorySizeCalculator.java:47`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/utils/DirectorySizeCalculator.java#L47) (`if (isAcceptable(file)) size += attrs.size();`) |
| Pinned source | `cassandra-5.0.9` |
| Session / date | claude-opus-5-5, Claude Code 2.1.330, 2026-11-24 (autonomous, stage 3; re-checked 2026-11-24: citations verified, unit-tier `SEG` initialisation moved into `setUpClass`) |
| Estimate | `positive`. The line is the file filter of the directory walk whose sum (`size`) becomes `CDCSizeTracker.sizeInProgress`, the usage-side operand that `cdc_total_space` is checked against before each new commit-log segment may take CDC data. With `cdc_block_writes: true` (default), CDC mutations are rejected once the sum plus one segment would exceed the limit, so `cdc_raw` disk usage should plateau at the limit, within about one segment. The walk counts apparent file sizes and every file in `cdc_raw`, so it over-counts rather than under-counts. The one exception is files it cannot stat or directories it cannot open: those are silently skipped. |
| Ground | — |

> The class `DirectorySizeCalculator` has three subclasses. Only one of them, `CDCSizeTracker`, feeds a limit. The
> other two (`Directories.SSTableSizeSummer` and `TableSnapshot.SnapshotTrueSizeCalculator`) feed only
> snapshot-size reporting (A4). This case follows the limit path: `cdc_total_space`.

## A. Constraint trace

**A1. The constraint.**
- Name: `cdc_total_space`. Its old name was `cdc_total_space_in_mb`, still accepted through `@Replaces` and deprecated.
- Kind: configuration entry (cassandra.yaml).
- Declared at [`Config.java:419`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/Config.java#L419): `public DataStorageSpec.IntMebibytesBound cdc_total_space = new DataStorageSpec.IntMebibytesBound("0MiB");`.
- Unit: MiB in yaml. It is read in bytes by `DatabaseDescriptor.getCDCTotalSpace()` (`DatabaseDescriptor.java:4370-4373`, `toBytesInLong()`).
- Default: `0MiB` means "derive". When `cdc_enabled: true` and the value is 0, `DatabaseDescriptor.java:684-695` sets it to `min(4096 MiB, totalSpace(cdc_raw_directory)/8)` (`calculateDefaultSpaceInMiB`, `DatabaseDescriptor.java:1147-1162`, numerator 1, denominator 8). `conf/cassandra.yaml:912-923` documents the same rule.
- How to set it: yaml `cdc_total_space: <N>MiB`, which needs a restart. It has no JMX or nodetool setter. `DatabaseDescriptor.setCDCTotalSpaceInMiB` (`DatabaseDescriptor.java:4376-4379`) is `@VisibleForTesting` only.
- Companion knobs:
  - `cdc_enabled` (`Config.java:410`, default false). Without it there is no CDC segment manager and no limit.
  - `cdc_block_writes` (`Config.java:413`, default true). It can be changed at runtime through JMX `CommitLogMBean.setCDCBlockWrites` (`CommitLog.java:460-470`).
  - `cdc_free_space_check_interval` (`Config.java:421`, default 250ms). It rate-limits the directory re-walk.
  - `cdc_raw_directory` (`Config.java:417`, default `<storagedir>/cdc_raw`).
  - `commitlog_segment_size` (`Config.java:397`, default 32MiB). This is the granularity of the check.

**A2. What it caps.**
- Resource: **disk**, namely the bytes held in `cdc_raw_directory`. That directory holds hard links to commit-log segments that contained CDC mutations, plus a `<segment>_cdc.idx` file per segment. While a segment is live, its hard link shares blocks with the commit-log file. Once the segment is discarded with CDC data, the commit-log name is deleted (`CommitLogSegmentManagerCDC.java:73-74`) and the `cdc_raw` link becomes the only owner of the blocks until a CDC consumer deletes it.
- Compared quantity: `CDCSizeTracker.sizeInProgress` (`CommitLogSegmentManagerCDC.java:292`).
  - It is periodically **reset to the directory walk's sum**, `getAllocatedSize()` (`CommitLogSegmentManagerCDC.java:411-413`). That sum is the `size` field accumulated at the given line, `DirectorySizeCalculator.java:47-48`: the sum of `BasicFileAttributes.size()` (**apparent** size) over every file the walk visits and accepts.
  - Between walks it is moved by `addSize(±segmentSize)` estimates (`:341`, `:372`, `:378`, `:207`) and by the replay path (`CommitLogReplayer.java:219`).
  - The comparison is `segmentSize + sizeInProgress > cdc_total_space` (`:335`).

**A3. Mechanism.**
1. Size operand: the walk.
   - `CDCSizeTracker extends DirectorySizeCalculator` (`CommitLogSegmentManagerCDC.java:286`) and does **not** override `isAcceptable`, which therefore returns `true` (`DirectorySizeCalculator.java:39-42`).
   - So at the given line [`DirectorySizeCalculator.java:47`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/utils/DirectorySizeCalculator.java#L47) every regular file reached under `cdc_raw` adds `attrs.size()` to `size` (`:48`). That includes segment links, `_cdc.idx` files, and any foreign file a consumer or operator leaves there, in any sub-directory.
   - `visitFileFailed` returns `CONTINUE` without adding anything (`:52-56`). A file that vanishes mid-walk, or a sub-directory that cannot be opened (no permission), is skipped and contributes 0.
2. When the walk runs.
   - `calculateSize()` (`CommitLogSegmentManagerCDC.java:407-419`) calls `resetSize()`, then `Files.walkFileTree(cdc_raw, this)`, then `sizeInProgress.getAndSet(getAllocatedSize())`.
   - It runs on a single-thread executor with queue limit 0 and a discard policy (`:309-313`), behind a `RateLimiter` of `1000/cdc_free_space_check_interval` permits per second (`:288`, `:390`).
   - It is submitted on every new segment (`:357`), every discarded segment (`:382`) and every rejected CDC mutation (`:216`).
3. The check at segment creation.
   - `createSegment()` (`:237-249`) calls `processNewSegment` (`:326-358`). Inside it, [`CommitLogSegmentManagerCDC.java:335-337`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/commitlog/CommitLogSegmentManagerCDC.java#L335-L337) does `setCDCState(blocking && segmentSize + sizeInProgress.get() > allowance ? FORBIDDEN : PERMITTED)`.
   - A PERMITTED segment adds `segmentSize` to the operand (`:340-341`) and is hard-linked into `cdc_raw` right away (`:243-247`).
   - Segments are created ahead of use: the reserve `availableSegment` (`AbstractCommitLogSegmentManager.java:189`).
4. The check at allocation, in `allocate()` (`:169-190`).
   - `permitSegmentMaybe` ([`:200-201`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/commitlog/CommitLogSegmentManagerCDC.java#L200-L201)) re-permits a FORBIDDEN segment if `sizeInProgress + segmentSize < allowance`. This is how space freed by a consumer is noticed.
   - `throwIfForbidden` (`:212-228`): a mutation with `trackedByCDC()` on a FORBIDDEN segment throws `CDCWriteException`. The client receives error code `CDC_WRITE_FAILURE` (0x1600, `ExceptionCode.java:49`; `ErrorMessage.java:172-173`). Non-CDC mutations are never rejected.
5. Outcome at the limit:
   - **blocking** (`cdc_block_writes: true`): CDC writes fail, non-CDC writes continue, and `cdc_raw` stops growing until files are removed.
   - **non-blocking**: the segment is PERMITTED, and if `sizeInProgress > allowance`, `deleteOldLinkedCDCCommitLogSegment(bytesToFree)` (`:91-131`) deletes the oldest links. It stops at the current allocating segment, so it can stop short of the target. `sizeInProgress` is then set to the remaining size (`:345-354`).
6. Bypasses and overshoot:
   - (a) Race between walk and estimate. `processNewSegment` adds `segmentSize` and then `createSegment` creates the link (`:241`, `:246`). A walk that lists `cdc_raw` before the link exists, and finishes after the `addSize`, overwrites `sizeInProgress` (`getAndSet`, `:413`) with a value that misses that segment. That allows up to about one extra segment until the next walk.
   - (b) Commit-log replay at startup hard-links every replayed segment that saw CDC data, with no limit check (`CommitLogReplayer.java:217-224`). It only adds its size.
   - (c) Unreadable sub-directories and files that fail to stat are uncounted (point 1).
   - (d) The operand uses apparent size. A sparse or preallocated file counts at its logical length. Memory-mapped segments are mapped at the full `commitlog_segment_size` (`MemoryMappedSegment.java:62`, `onDiskSize()` = segment size `:103-106`). This over-counts allocated blocks, which is conservative.
   - (e) The resolution is one segment: the operand can sit anywhere in `(allowance − segmentSize, allowance]` when blocking starts.

**A4. Other consumers.**
- The same disk also holds the live commit log, governed separately by `commitlog_total_space`. `cdc_raw` links of live segments share its blocks.
- If `cdc_raw` is on the data volume, it also shares space with sstables, snapshots and hints.
- The other users of `DirectorySizeCalculator` do not enforce anything:
  - `Directories.SSTableSizeSummer` (`Directories.java:1433-1452`) feeds `trueSnapshotsSize()` (`Directories.java:1305-1316`), which is exposed as the `SnapshotsSize` table metric (`TableMetrics.java:799`) and in `nodetool listsnapshots` (`ListSnapshots.java:67-91`).
  - `TableSnapshot.SnapshotTrueSizeCalculator` (`TableSnapshot.java:150-167`, `:297-308`) is reporting only.

**A5. Evidence beyond the source.**
- `test/unit/org/apache/cassandra/db/commitlog/CommitLogSegmentManagerCDCTest.java`:
  - `testCDCWriteFailure` expects `CDCWriteException` at a 32 MiB limit.
  - `testNonblockingShouldMaintainSteadyDiskUsage` asserts only `actualSize <= limit * 3`, a loose bound in non-blocking mode.
  - The class uses `updateCDCTotalSize()` (`CommitLogSegmentManagerCDC.java:438-451`) as the read of the walk sum.
- `test/microbench/.../DirectorySizerBench.java` benchmarks the walk.
- `conf/cassandra.yaml:410-431` and `:912-929` document the setting.
- JDK `Files.walkFileTree` javadoc: when a directory cannot be opened, `visitFileFailed` is invoked and the walk continues at the next sibling (https://docs.oracle.com/en/java/javase/11/docs/api/java.base/java/nio/file/Files.html#walkFileTree(java.nio.file.Path,java.util.Set,int,java.nio.file.FileVisitor)).
- JIRA CASSANDRA-8844 (CDC design) and CASSANDRA-17001 (non-blocking `cdc_block_writes`) are cited for background only; nothing here depends on them.

## B. Verification solution

**B1. Claim under test.**
- With `cdc_enabled: true` and `cdc_block_writes: true`, the bytes held in `cdc_raw_directory` (apparent size of segment links, which is ≥ allocated blocks) stop growing at or below `cdc_total_space + commitlog_segment_size`.
- CDC writes are refused with `CDC_WRITE_FAILURE` from that point on, and the plateau scales with `cdc_total_space`.
- At the given line, the walk counts every readable file in `cdc_raw` at its apparent size and skips unreadable sub-trees.

### B2. Unit tier

**B2a. Environment and build.**
1. Make a private copy of the tag on local disk, then build:
   ```
   rsync -a <source-copy>/ $U/cassandra/
   cd $U/cassandra
   ant build-test
   ```
   `$U` is a local scratch directory, for example `/local/$USER/cdc-unit`, with at least 5 GiB free.
2. Use JDK 11 (`java -version` must print 11) and Ant ≥ 1.10.
3. The test config `test/conf/cassandra.yaml` already has `commitlog_segment_size: 5MiB` (line 10) and `cdc_raw_directory: build/test/cassandra/cdc_raw` (line 15). The test sets `cdc_enabled` programmatically.
4. Run the tests as a **non-root** user. U4 depends on file permissions.
5. Add the file `$U/cassandra/test/unit/org/apache/cassandra/db/commitlog/CDCCapProbeTest.java`. Its imports are the same as `CommitLogSegmentManagerCDCTest.java:20-47`, plus `java.io.RandomAccessFile`, `java.nio.file.attribute.PosixFilePermissions` and `org.apache.cassandra.utils.DirectorySizeCalculator`.

```java
public class CDCCapProbeTest extends CQLTester
{
    static int SEG; // set after daemonInitialization; 5 MiB in test conf (a static initializer would NPE: conf is null at class load)
    @BeforeClass public static void setUpClass()
    { ServerTestUtils.daemonInitialization(); SEG = DatabaseDescriptor.getCommitLogSegmentSize(); DatabaseDescriptor.setCDCEnabled(true);
      DatabaseDescriptor.setCDCTotalSpaceInMiB(1024); CQLTester.setUpClass(); }
    @Before public void before() throws Throwable
    { CommitLog.instance.start(); super.beforeTest(); mgr().updateCDCTotalSize(); }
    @After public void after() throws Throwable
    { super.afterTest(); CommitLog.instance.stopUnsafe(true);
      for (File f : raw().tryList()) { if (f.isDirectory()) { f.toJavaIOFile().setReadable(true); f.toJavaIOFile().setExecutable(true); f.deleteRecursive(); } else f.deleteIfExists(); } }

    static CommitLogSegmentManagerCDC mgr() { return (CommitLogSegmentManagerCDC) CommitLog.instance.segmentManager; }
    static File raw() { return new File(DatabaseDescriptor.getCDCLogLocation()); }
    static long apparent() throws IOException   // independent sum, regular files only, readable tree
    { try (java.util.stream.Stream<Path> s = Files.walk(raw().toPath())) {
        return s.filter(Files::isRegularFile).mapToLong(p -> { try { return Files.size(p);} catch (IOException e) { return 0; } }).sum(); } }

    /** writes 1/3-segment CDC mutations until rejected or 1000 tries; prints one result line */
    void fill(String label, int limitMiB) throws Throwable
    {
        DatabaseDescriptor.setCDCTotalSpaceInMiB(limitMiB);
        mgr().updateCDCTotalSize();
        String t = createTable("CREATE TABLE %s (idx int, data text, primary key(idx)) WITH cdc=true;");
        TableMetadata m = Keyspace.open(keyspace()).getColumnFamilyStore(t).metadata();
        int accepted = 0; boolean rejected = false;
        try { for (int i = 0; i < 1000; i++) {
                byte[] b = new byte[SEG / 3]; new Random(i).nextBytes(b);
                new RowUpdateBuilder(m, 0, i).add("data", ByteBuffer.wrap(b)).build().applyFuture().get(); accepted++; } }
        catch (CDCWriteException e) { rejected = true; }
        long walked = mgr().updateCDCTotalSize();          // = getAllocatedSize(), the sum built at line 47-48
        long links = Arrays.stream(raw().tryList()).filter(f -> f.name().endsWith(".log")).count();
        System.out.printf("PROBE %s limitMiB=%d accepted=%d rejected=%b walked=%d apparent=%d logLinks=%d state=%s%n",
                          label, limitMiB, accepted, rejected, walked, apparent(), links,
                          CommitLog.instance.segmentManager.allocatingFrom().getCDCState());
    }

    @Test public void u1_limit20() throws Throwable { fill("U1", 20); }
    @Test public void u1_limit40() throws Throwable { fill("U1", 40); }
    @Test public void u1_limit80() throws Throwable { fill("U1", 80); }
    @Test public void u1_limit1024_uncapped() throws Throwable { fill("U1ctl", 1024); }

    @Test public void u2_foreignDenseFile() throws Throwable
    { byte[] z = new byte[1 << 20]; try (java.io.FileOutputStream o = new java.io.FileOutputStream(new java.io.File(raw().toJavaIOFile(), "junk.bin")))
      { for (int i = 0; i < 30; i++) o.write(z); } fill("U2", 80); }

    @Test public void u3_foreignSparseFile() throws Throwable
    { try (RandomAccessFile r = new RandomAccessFile(new java.io.File(raw().toJavaIOFile(), "sparse.bin"), "rw")) { r.setLength(1L << 30); }
      fill("U3", 80); }

    @Test public void u4_unreadableSubdir() throws Throwable
    { java.io.File d = new java.io.File(raw().toJavaIOFile(), "hidden"); d.mkdir();
      byte[] z = new byte[1 << 20]; try (java.io.FileOutputStream o = new java.io.FileOutputStream(new java.io.File(d, "h.bin"))) { for (int i = 0; i < 30; i++) o.write(z); }
      Files.setPosixFilePermissions(d.toPath(), PosixFilePermissions.fromString("---------"));
      fill("U4", 80); }

    @Test public void u5_bareCalculator() throws Throwable
    { Path tmp = Files.createTempDirectory(java.nio.file.Paths.get(System.getProperty("java.io.tmpdir")), "dsc");
      long want = 0; for (int k = 1; k <= 3; k++) { byte[] b = new byte[k << 20]; Files.write(tmp.resolve("f" + k), b); want += b.length; }
      try (RandomAccessFile r = new RandomAccessFile(tmp.resolve("sp").toFile(), "rw")) { r.setLength(64L << 20); } want += 64L << 20;
      DirectorySizeCalculator c = new DirectorySizeCalculator(); Files.walkFileTree(tmp, c);
      System.out.printf("PROBE U5 walked=%d expectedApparent=%d%n", c.getAllocatedSize(), want);
      Assert.assertEquals(want, c.getAllocatedSize()); }
}
```
(`File.deleteRecursive`, `tryList`, `toJavaIOFile` and `name` are methods of `org.apache.cassandra.io.util.File` in 5.0. If one is missing in the copy, use the `java.io.File` equivalent. Fixing API names is not a design change.)

JVM options: the `testsome` defaults. The test directory `build/test/cassandra` is inside `$U`, which is local.

**B2b. Knobs.**
- `cdc_total_space`, set through `setCDCTotalSpaceInMiB` before each fill. Values:
  - 20, 40, 80 MiB, which is 4, 8 and 16 segments of 5 MiB. A doubling series, so the dose-response is visible.
  - 1024 MiB as the loosely capped control. 1000 mutations × 1.67 MiB ≈ 1.63 GiB is more than 1024 MiB, so this run may still reject near the end. Read U1ctl as "accepted ≫ the capped runs" (≥ 500), not as "never rejected".
- Contents of `cdc_raw` at the start, which is the line-47 knob:
  - none (U1);
  - a dense 30 MiB foreign file (U2);
  - a 1 GiB sparse foreign file (U3);
  - an unreadable sub-directory holding 30 MiB (U4).
- U5 runs the bare class against a temp directory of known sizes.

**B2c. Workload.**
- Each `fill` writes 1000 mutations of `SEG/3` ≈ 1.67 MiB, about 1.63 GiB of commit-log payload.
- About 3 mutations fit in a 5 MiB segment, so the workload needs up to about 330 segments, against 4 to 16 allowed. The limit is crossed after about 12 to 48 mutations.

**B2d. Observables and instruments.**
- `walked`: the return of `updateCDCTotalSize()`, which is `getAllocatedSize()`, the sum accumulated at lines 47 and 48. It is read after a forced, rate-limited re-walk.
- `apparent`: an independent `Files.walk` sum of the sizes of readable regular files.
- `accepted`: mutations before the first `CDCWriteException`.
- `rejected` (boolean) and `logLinks` (count of `.log` links).
- `state`: the CDC state of the current allocating segment.
- Allocated blocks are not visible from the JVM. After a run, `du -sB1 $U/cassandra/build/test/cassandra/cdc_raw` could be read, but `after()` deletes the directory, so allocated blocks are left to the cluster tier.
- U4 cannot show the hidden bytes through `apparent()`, because that walk also cannot open the directory. The 30 MiB is known by construction.

**B2e. Procedure.**
```
cd $U/cassandra
ant testsome -Dtest.name=org.apache.cassandra.db.commitlog.CDCCapProbeTest
grep -h '^PROBE\|PROBE ' build/test/output/TEST-org.apache.cassandra.db.commitlog.CDCCapProbeTest*.xml build/test/logs/*.log 2>/dev/null | sort -u
```
If the U4 assumption is in doubt, run U4 by itself:
```
ant testsome -Dtest.name=org.apache.cassandra.db.commitlog.CDCCapProbeTest -Dtest.methods=u4_unreadableSubdir
```
Afterwards: `ls -la build/test/cassandra/cdc_raw`. It must be empty. Then `pgrep -f CDCCapProbeTest` must print nothing.

**B2f. Predictions** (SEG = 5 MiB = 5,242,880 B; idx files are about 10 B each).

| Run | limit | accepted | walked | logLinks | rejected / state |
|---|---|---|---|---|---|
| U1 | 20 MiB | ≤ 12 | in (15 MiB, 20 MiB + 1 KiB]: expected 4·SEG + idx = 20,971,520 + ≤ 100 B | ≤ 4 | true / FORBIDDEN |
| U1 | 40 MiB | ≤ 24, about 2× the 20 MiB run | in (35 MiB, 40 MiB + 1 KiB] | ≤ 8 | true / FORBIDDEN |
| U1 | 80 MiB | ≤ 48, about 4× the 20 MiB run | in (75 MiB, 80 MiB + 1 KiB] | ≤ 16 | true / FORBIDDEN |
| U1ctl | 1024 MiB | ≥ 500 | ≤ 1024 MiB + 1 KiB | ≤ 204 | either |
| U2 | 80 MiB + 30 MiB dense | about 10/16 of the U1-80 count (≤ 30) | in (75, 80 MiB + 1 KiB], including the 31,457,280 B junk file | ≤ 10 | true |
| U3 | 80 MiB + 1 GiB sparse | 0 to 6 (only segments permitted before the first re-walk) | ≥ 1,073,741,824 | ≤ 2 | true |
| U4 | 80 MiB + 30 MiB hidden | about the U1-80 count (not reduced) | in (75, 80 MiB + 1 KiB], the hidden 30 MiB **not** counted | ≤ 16 | true |
| U5 | — | — | = 3 MiB + 2 MiB + 1 MiB + 64 MiB = 73,400,320 exactly (sparse file at apparent length) | — | — |

Other predicted relations:
- In every U1 run, `walked == apparent ± 0`. The two walks see the same readable tree.
- `walked ≤ limit + SEG` always, even allowing for the A3-6(a) race.

**B2g. Readings.**

| Observation | Meaning |
|---|---|
| U1 `walked` ≤ limit + 1 KiB, `rejected=true`, accepted doubling with the limit | The mechanism caps the operand as traced. Claim holds at unit level. |
| U1 `walked` in (limit, limit + SEG] | The A3-6(a) race overshot by one segment. Still consistent; note it. |
| U1 `walked` > limit + SEG, or no rejection with `walked` > limit at 20/40/80 | **Claim wrong**: the check does not bound the walked operand. |
| `walked ≠ apparent` in U1 | The walk at line 47 counts something other than readable files' apparent size. The trace is wrong. |
| U2 accepted ≈ U1-80 accepted (foreign file ignored) | Line 47 is not "accept all". The trace is wrong. |
| U3 walked ≈ 1 GiB and immediate rejection | The operand is apparent size, a conservative over-count. As predicted. |
| U3 accepted ≈ U1-80 | Sparse length not counted. The A3-6(d) prediction is wrong. |
| U4 accepted ≈ U1-80 | Unreadable sub-trees are skipped, so cdc_raw can hold limit + hidden bytes (A3-6(c) bypass confirmed). |
| U4 accepted ≈ U2 | The hidden directory was counted. Either the run was as root or the bypass is refuted. Check `id -u`. |
| U1ctl accepted not ≫ U1-80 | The workload or limit setting is ineffective. The run is inconclusive. |
| U5 ≠ 73,400,320 | The base class does not sum apparent sizes. |

**B2h. Controls.**
- U1ctl is the uncapped positive control. The same workload goes far past the small limits.
- U5 isolates the class from Cassandra state.
- `apparent()` is an independent instrument for `walked`.
- The non-CDC path is not used here; the cluster tier covers it.
- Each method starts from an empty `cdc_raw` (`after()`) and a fresh commit log (`before()`). The limit is set before the table is created, and `updateCDCTotalSize()` first flushes in-flight walks (`CommitLogSegmentManagerCDC.java:441-446`).

### B3. Cluster tier

**B3a. Environment and build.**
- One Linux node. Commit log, CDC and data go on local disk of known size: `$R=/local/$USER/cdc-run` with at least 20 GiB free (check with `df -B1 $R`).
- JDK 11.
- Build:
  ```
  rsync -a <source-copy>/ $R/cassandra/
  cd $R/cassandra
  ant jar
  ```
  This also builds `tools/bin/cassandra-stress`. If it does not, run `ant stress-build`.
- Settings in `$R/cassandra/conf/cassandra.yaml`, changed or added:
  ```
  cdc_enabled: true
  cdc_block_writes: true
  cdc_total_space: <T>MiB
  cdc_free_space_check_interval: 250ms
  commitlog_segment_size: 8MiB
  commitlog_total_space: 2048MiB
  cdc_raw_directory: <R>/cdc_raw
  commitlog_directory: <R>/commitlog
  data_file_directories: [<R>/data]
  hints_directory: <R>/hints
  saved_caches_directory: <R>/saved_caches
  ```
  Leave `max_mutation_size` unset, so it derives to 4 MiB.
- `conf/jvm-server.options`: leave as is. Heap goes through the environment: `MAX_HEAP_SIZE=2G HEAP_NEWSIZE=400M`.
- If the default ports (7000, 9042, 7199) are taken on the shared machine, change `native_transport_port` and `storage_port` and set `JMX_PORT` in `conf/cassandra-env.sh`. Pass the same port to `cqlsh`, `nodetool -p` and `cassandra-stress -port native=`.

**B3b. Knobs.**
- `cdc_total_space` T ∈ {64, 128, 256} MiB. These are 8, 16 and 32 segments of 8 MiB, a doubling series.
- Uncapped control: T = 4096 MiB, larger than the workload.
- Mode run: T = 64 MiB with `cdc_block_writes: false`.
- Line-47 run: T = 128 MiB with a sparse 1 GiB file `truncate -s 1G $R/cdc_raw/sparse.bin` created before start.
- Each value is a yaml edit plus a restart from wiped `$R/{data,commitlog,cdc_raw,hints,saved_caches}`.

**B3c. Workload.**
`$R/cdc-profile.yaml`:
```yaml
keyspace: cdcks
keyspace_definition: |
  CREATE KEYSPACE cdcks WITH replication = {'class': 'SimpleStrategy', 'replication_factor': 1};
table: t
table_definition: |
  CREATE TABLE t (k bigint PRIMARY KEY, v blob) WITH cdc = true;
columnspec:
  - name: k
    population: seq(1..300000)
  - name: v
    size: fixed(4096)
insert:
  partitions: fixed(1)
  batchtype: UNLOGGED
```
- Load: 300,000 inserts × about 4.1 KiB ≈ 1.2 GiB of commit-log payload. That is about 150 segments of 8 MiB, at least 4.6 times the largest capped T.
- Command:
  ```
  tools/bin/cassandra-stress user profile=$R/cdc-profile.yaml "ops(insert=1)" n=300000 no-warmup -rate threads=16 -errors ignore retries=0 -node 127.0.0.1 -log interval=2 file=$R/stress-$T.log
  ```
- Duration: a few minutes per run.
- Non-CDC control table:
  ```
  cqlsh -e "CREATE TABLE cdcks.plain (k int PRIMARY KEY, v text) WITH cdc=false"
  ```
  Create it after stress creates the keyspace, or create the keyspace first with cqlsh.

**B3d. Observables and instruments.**
A sampler runs every 2 s and appends to `$R/samples-$T.txt`. Each row records:
1. `t`.
2. `A`: the apparent bytes in cdc_raw, `find $R/cdc_raw -type f -printf '%s\n' | awk '{s+=$1}END{print s+0}'`. This is the same quantity the walk computes.
3. `D`: the allocated bytes of cdc_raw, `du -sB1 $R/cdc_raw | cut -f1`.
4. `J`: the joint allocated bytes, `du -sB1 $R/commitlog $R/cdc_raw | awk '{s+=$1}END{print s}'`. GNU du counts hard-linked inodes once across its arguments.
5. `N`: the number of `.log` links in cdc_raw.
6. `P`: the CDC probe result, `cqlsh -e "INSERT INTO cdcks.t (k,v) VALUES (-1, 0x00)"`. Record 1 for ok, 0 for an error containing `CDC` or `Rejecting mutation`.
7. `Q`: the non-CDC probe, `cqlsh -e "INSERT INTO cdcks.plain (k,v) VALUES (1,'x')"`. 1 for ok.
8. `L`: `grep -c 'Rejecting mutation' $R/cassandra/logs/system.log`. This is a lower bound, because NoSpamLogger logs at most every 10 s.

What cannot be observed:
- `sizeInProgress` directly. No metric or JMX exposes it.
- Which segment the A3-6(a) race affected.
- `A` is the proxy for the operand.

**B3e. Procedure** (per T; one run at a time).
1. Wipe the run directories: `rm -rf $R/{data,commitlog,cdc_raw,hints,saved_caches} $R/samples-$T.txt`, then `mkdir -p` the same directories. For the line-47 run, create the sparse file now.
2. Set T in the yaml. Start the node with `MAX_HEAP_SIZE=2G HEAP_NEWSIZE=400M $R/cassandra/bin/cassandra -p $R/pid`. Wait until `bin/nodetool status` shows `UN`, and check `grep 'cdc_enabled is true' logs/system.log`.
3. Create the keyspace and table: run `cqlsh -f` with the two CREATE statements from the profile plus `cdcks.plain`.
4. Start the sampler in the background, saving its PID. It runs the 2 s loop from B3d, writing one line per sample.
5. Run stress (B3c) to completion.
6. Keep sampling for 30 s more. Then run `bin/nodetool flush` and sample for 60 s more. Flushed segments are discarded, their commit-log names are deleted, and `D` becomes exclusive cdc_raw usage.
7. Release control, capped blocking runs only:
   - delete every `*.log` and `*_cdc.idx` in `$R/cdc_raw`, which simulates a consumer;
   - wait 5 s, then probe `P` 5 times, 1 s apart.
8. Stop: `kill $(cat $R/pid)`, wait for exit, kill the sampler, then `pgrep -u $USER -f 'CassandraDaemon|cassandra-stress'` must print nothing.

**B3f. Predictions** (S = 8 MiB = 8,388,608 B).

| Run | plateau of `A` (bytes) | `N` max | `P` after plateau | `Q` | `L` | `D` after flush |
|---|---|---|---|---|---|---|
| T=64 MiB, blocking | in (56 MiB, 64 MiB + 64 KiB]; never above 72 MiB (T + S) | ≤ 8 (9 only with the race) | 0 | always 1 | ≥ 1 | ≤ A |
| T=128 MiB, blocking | in (120 MiB, 128 MiB + 64 KiB], about 2× the T=64 plateau; never above 136 MiB | ≤ 16 | 0 | 1 | ≥ 1 | ≤ A |
| T=256 MiB, blocking | in (248 MiB, 256 MiB + 64 KiB], about 4× the T=64 plateau; never above 264 MiB | ≤ 32 | 0 | 1 | ≥ 1 | ≤ A |
| T=4096 MiB (uncapped) | no plateau: rises roughly linearly to about 1.1 to 1.3 GiB | about 140 to 160 | 1 | 1 | 0 | ≈ A |
| T=64, non-blocking | stays ≤ 72 MiB (T + S) once past T; oldest links deleted | ≤ 9 | 1 | 1 | 0 | ≤ A |
| T=128 + 1 GiB sparse | `A` ≥ 1 GiB from the start; at most 1 to 2 segment links | ≤ 2 | 0 from about the first segment roll | 1 | ≥ 1 | ≈ 0 + segments (sparse file uses no blocks) |

Release control: `P` returns to 1 within 5 s after cdc_raw is emptied. The check interval is 250 ms, and the next allocation re-permits the segment (A3-4).

The claim is **wrong** if any of the following holds:
- in a blocking run, `A` or `D` exceeds T + S, while `P` = 1 and stress inserts are still succeeding;
- the plateau does not scale with T;
- `P` stays 1 throughout a capped blocking run.

**B3g. Readings.**

| Observation | Meaning |
|---|---|
| Plateaus at about T for 64/128/256, `P` → 0, `Q` = 1 | `cdc_total_space` governs cdc_raw disk in blocking mode. Claim confirmed. |
| Plateau in (T, T+S] | One-segment overshoot from the walk/estimate race (A3-6a). Still within the claim. |
| `A` or `D` > T + S with writes still succeeding | **Claim refuted**: the cap does not bind actual disk. |
| Uncapped run does not exceed 256 MiB | The workload is too small to test the cap. Inconclusive; raise n. |
| `D` > `A` after flush | Allocated blocks exceed apparent size, which is not expected for these files. The operand under-counts real disk. |
| Non-blocking `A` > T + S persistently | Deletion stops at the allocating segment (A3-5). The weaker non-blocking bound holds only as in the upstream test (≤ 3T). |
| Sparse run rejects CDC with near-zero `D` | The operand is apparent size. The cap over-binds, which is conservative and as predicted for line 47. |
| Release control: `P` stays 0 | Freed space is not noticed. The mechanism in A3-4 is wrong. |

**B3h. Controls.**
- The uncapped T=4096 run is the positive control: the same workload grows cdc_raw well past every small cap.
- `Q` shows the rejection is CDC-specific, not a dead node or a full disk. Also check `df` stays far from full.
- The doubling series rules out a coincidental plateau, for example from a stress stall.
- `J` versus `D` separates bytes shared with the live commit log from bytes exclusively in cdc_raw.
- Every run starts from wiped directories, so no replay (A3-6b) adds untracked size.

**B4. Risks and cleanup.**
- All bytes stay under `$U` and `$R` on local disk:
  - The unit tier peaks at about 1.7 GiB of commit log; the test deletes it in `after()`.
  - The cluster tier peaks at about 1.3 GiB of cdc_raw plus about 2 GiB of commit log and data.
- Nothing is written to the shared source tree.
- Restore permissions on `hidden` (U4) if a test aborts: `chmod -R u+rwx $U/cassandra/build/test/cassandra/cdc_raw`.
- After each run, run `pgrep -u $USER -f 'CassandraDaemon|cassandra-stress|CDCCapProbeTest|junit'` and kill whatever it prints.
- When done, run `rm -rf $U $R`.

## C. Sources read

- src/java/org/apache/cassandra/utils/DirectorySizeCalculator.java
- src/java/org/apache/cassandra/db/commitlog/CommitLogSegmentManagerCDC.java
- src/java/org/apache/cassandra/db/commitlog/CommitLog.java (100-125, 455-492)
- src/java/org/apache/cassandra/db/commitlog/CommitLogSegment.java (360-400, 455-480)
- src/java/org/apache/cassandra/db/commitlog/CommitLogReplayer.java (195-230)
- src/java/org/apache/cassandra/db/commitlog/MemoryMappedSegment.java (55-110)
- src/java/org/apache/cassandra/db/commitlog/AbstractCommitLogSegmentManager.java (grep: availableSegment, createSegment)
- src/java/org/apache/cassandra/config/Config.java (397-421)
- src/java/org/apache/cassandra/config/DatabaseDescriptor.java (670-700, 898-900, 1147-1162, 4340-4390)
- src/java/org/apache/cassandra/db/Directories.java (1300-1345, 1400-1452)
- src/java/org/apache/cassandra/service/snapshot/TableSnapshot.java (140-170, 290-320)
- src/java/org/apache/cassandra/io/util/FileUtils.java (497-510)
- src/java/org/apache/cassandra/transport/messages/ErrorMessage.java (165-176)
- src/java/org/apache/cassandra/exceptions/ExceptionCode.java (49)
- tools/stress/src/org/apache/cassandra/stress/settings/SettingsErrors.java (34-62)
- conf/cassandra.yaml (400-432, 650-660, 910-932)
- test/conf/cassandra.yaml (grep: commitlog_segment_size, cdc)
- test/unit/org/apache/cassandra/db/commitlog/CommitLogSegmentManagerCDCTest.java
- build.xml (testsome target, 1382-1386)
- https://docs.oracle.com/en/java/javase/11/docs/api/java.base/java/nio/file/Files.html (walkFileTree)

## D. Stage-4 feedback

none yet
