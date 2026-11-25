# max_log_size — verification solution  <!-- file: cases/max_log_size-onreleased-bytesinstorefiles--autonomous.md -->

| Field | Value |
|---|---|
| Entry pointer | the given line (the `while` check of the deletion loop), **linked**: [`DeletingArchiver.java:60`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/utils/binlog/DeletingArchiver.java#L60) |
| Pinned source | `cassandra-5.0.9` |
| Session / date | claude-opus-5-5, Claude Code 2.1.330, 2026-11-24 (autonomous agent, unit kind: enforcement) |
| Estimate | `positive`. Each time Chronicle Queue releases a rolled binary-log segment, `DeletingArchiver` deletes the oldest tracked segments until the tracked byte count is at or below `max_log_size`. So the disk used by **rolled** full-query-log or audit-log segments stays at or below `max_log_size`, measured in apparent file lengths at release time. The cap does not cover the segment currently being written, files already in the directory when logging was enabled, or setups where `archive_command` is set. |
| Ground | — |

## A. Constraint trace

**A1. The constraint.**
- **Name:** `max_log_size`, a field of `BinLogOptions`. It is declared once,
  [`BinLogOptions.java:54`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/utils/binlog/BinLogOptions.java#L54),
  as `public long max_log_size = 16L * 1024L * 1024L * 1024L;`. It is inherited by
  `FullQueryLoggerOptions` (`src/java/org/apache/cassandra/fql/FullQueryLoggerOptions.java:25`) and by
  `AuditLogOptions` (`src/java/org/apache/cassandra/audit/AuditLogOptions.java:37`).
- **Kind:** configuration entry (nested yaml key), also settable through nodetool/JMX.
- **Unit:** bytes (a raw `long`, not a `DataStorageSpec`).
- **Default:** 17179869184 (16 GiB). It is a hard-coded literal `16L*1024*1024*1024`, not derived
  from anything. `conf/cassandra.yaml` shows it commented out, under `audit_logging_options`
  (`max_log_size: 17179869184 # 16 GiB`) and under `full_query_logging_options` (the same text).
- **How it is set:**
  - **Full query log (FQL):** `full_query_logging_options.max_log_size` in `cassandra.yaml` (held
    in `Config.full_query_logging_options`, `src/java/org/apache/cassandra/config/Config.java:704`)
    is only a default. FQL starts only with `nodetool enablefullquerylog [--max-log-size <bytes>]`
    (`src/java/org/apache/cassandra/tools/nodetool/EnableFullQueryLog.java:38-39`). That command
    reaches `StorageService.enableFullQueryLogger`. There `--max-log-size` overrides the yaml value
    when it is given (`StorageService.java:7138`), and the call then goes to
    `FullQueryLogger.enableWithoutClean` (`StorageService.java:7145`). A change needs
    `nodetool disablefullquerylog` and then a new enable. No restart is needed.
  - **Audit log:** `audit_logging_options.max_log_size` (`Config.java:703`), applied at startup
    when `enabled: true`, or `nodetool enableauditlog --max-log-size <bytes>`
    (`EnableAuditLog.java:61-62`, `StorageService.java:7018`). A change needs a disable and
    re-enable, or a restart.
  - **Validation:** `BinLog.Builder.maxLogSize` requires `> 0` (`BinLog.java:405-408`), and so does
    `DeletingArchiver`'s constructor (`DeletingArchiver.java:45`).
  - The value is used only when `archive_command` is empty: `BinLog.java:449` picks
    `new DeletingArchiver(maxLogSize)`, otherwise an `ExternalArchiver` that never reads it.

**A2. What it caps.**
- **Resource:** disk. Specifically, the Chronicle Queue segment files (`*.cq4`) of a binary log
  (FQL or audit log) that have already **rolled**.
- **Quantity compared against the limit:** `bytesInStoreFiles`
  (`DeletingArchiver.java:41`). It is the sum of `java.io.File.length()` (apparent size) of every
  segment passed to `onReleased` and not yet deleted, each measured at the moment of release
  (`DeletingArchiver.java:58`).
- **What it is not:** it is not allocated blocks (the source comment at `:57` says the files are
  sparse and the count is "pessimistic"), and it does not include the segment being written.
- **Memory:** none of note. The archiver holds only a `ConcurrentLinkedQueue<File>` of paths
  (`:36`).

**A3. Mechanism.**
1. `BinLog` builds a `SingleChronicleQueue` with the configured roll cycle (`BinLog.java:139-140`)
   and registers the archiver as its `StoreFileListener` (`BinLog.java:144`). `BinLogArchiver`
   extends `StoreFileListener` (`BinLogArchiver.java:25`).
2. A single "Binary Log thread" writes records with `appender.writeDocument` (`BinLog.java:241`).
   When the wall clock crosses a cycle boundary (for example a new minute with `MINUTELY`), the
   next write rolls to a new segment file. After that, Chronicle releases the old store and calls
   `onReleased(cycle, file)`.
3. `DeletingArchiver.onReleased` (synchronized, `:54`) appends the file to the FIFO (`:56`) and
   adds `file.length()` to `bytesInStoreFiles` (`:58`).
4. **The check:**
   [`DeletingArchiver.java:60`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/utils/binlog/DeletingArchiver.java#L60):
   `while (bytesInStoreFiles > maxLogSize & !chronicleStoreFiles.isEmpty())`. The non-short-circuit
   `&` has no side effect here, so it behaves like `&&`.
   - **True:** `poll()` takes the oldest tracked file (`:62`) and reads its *current* length
     (`:63`).
     - If `delete()` succeeds, it subtracts that length (`:72`) and logs at INFO
       `Deleted chronicle store file: ... bytes in store files: <operand> max log size: <limit>`
       (`:73-74`). The loop then re-checks.
     - If `delete()` fails, it logs ERROR (`:66-68`). The file has already been removed from the
       FIFO but the operand is **not** decremented. The loop goes on to delete the next-oldest
       files, and that file's length stays in the operand for good. Every later check therefore
       retains less, and once the stuck length alone exceeds `maxLogSize`, every later segment is
       deleted at release. The failed file stays on disk, untracked.
   - **False:** the method returns and the retained rolled segments total at most `maxLogSize`
     by the tracked count. The newly released file can itself be deleted at once if it alone is
     bigger than the limit (`DeletingArchiverTest.testArchiverBigFile`,
     `test/unit/org/apache/cassandra/utils/binlog/DeletingArchiverTest.java:52-59`).
5. **Bypasses and overshoots:**
   - **(a) Current segment.** The segment being written is never counted. With the default
     `HOURLY` roll cycle it can grow to one hour of log traffic, whatever `max_log_size` is. The
     nodetool help says so: "Might not be respected if a log file hasn't rolled"
     (`EnableFullQueryLog.java:38`).
   - **(b) Files already present at enable.** Both production enable paths build with
     `cleanDirectory=false`: FQL via nodetool (`FullQueryLogger.java:106-117`,
     `BinLog.java:431,450`) and the audit log (`BinAuditLogger.java:45-52`). Segments left by an
     earlier enable, or by a run before a restart, are never offered to the new `DeletingArchiver`
     and are never deleted, so the directory can hold old files plus `max_log_size`. Only
     `nodetool resetfullquerylog` (`FullQueryLogger.reset`, `:189+`) cleans the directory.
   - **(c) `archive_command` set.** `ExternalArchiver` is used instead and `max_log_size` is
     ignored (`BinLog.java:449`; documented in `conf/cassandra.yaml` under
     `audit_logging_options`).
   - **(d) Length drift.** The operand adds the length at release (`:58`) but subtracts the length
     at deletion (`:63,72`). If Chronicle shrinks a sparse, pre-sized segment after release, the
     difference stays in `bytesInStoreFiles` for good. The operand then overstates retained bytes,
     and later releases delete more than needed. This errs on the side of less disk, not more.
     The comment on `BinLogTest.testTruncationReleasesLogSpace`
     (`test/unit/org/apache/cassandra/utils/binlog/BinLogTest.java:423-434`) describes an earlier
     bug of exactly this kind ("files were deleted but the space was not reclaimed when tracking
     so all log segments were incorrectly deleted"). From the source alone I cannot tell whether
     Chronicle 5.23.37 (`.build/parent-pom-template.xml:861-862`) shrinks before or after
     `onReleased`. B2 and B3 measure it.
   - **(e) Delete failure.** See the failed-delete branch above: the failed file stays on disk,
     untracked, but its length stays in the operand, so total disk still stays at or below the
     limit (with less retained afterwards).
   - **(f) Two logs.** FQL and the audit log each have their own `BinLog`, archiver and
     `max_log_size`. They cannot share a path (`BinLog.java:434-438`), so total binlog disk is the
     sum of two independently capped amounts.

**A4. Other consumers.**
- The same node disk also holds data files, the commit log, hints, saved caches, snapshots, other
  logs and `cdc_raw`. None of them is under this constraint.
- The binlog directory also holds Chronicle metadata (`metadata.cq4t` and similar), which is small
  and not counted.
- The in-memory queue in front of the binlog is capped separately by `max_queue_weight`
  (`BinLogOptions.java:49`, `BinLog.java:142`). That is heap, not disk.

**A5. Evidence beyond the source.**
- `doc/modules/cassandra/pages/managing/operating/fqllogging.adoc:130-133` and
  `auditlogging.adoc:273-283`: "sets the maximum size of the rolled files to retain on disk
  before deleting the oldest file … ignored if `archive_command` option is set".
- Existing tests: `DeletingArchiverTest` (synthetic files), `BinLogTest.testCleanupOnOversize` and
  `testTruncationReleasesLogSpace`, the latter citing CASSANDRA-16526
  (https://issues.apache.org/jira/browse/CASSANDRA-16526).
- `CHANGES.txt:1736` (CASSANDRA-14373, custom archive script, which introduced the
  Deleting/External split).

## B. Verification solution

**B1. Claim under test.** While a binary log (FQL) uses the built-in `DeletingArchiver`, the
total apparent size of its rolled `*.cq4` segments stays at or below `max_log_size`. It can exceed
the cap only transiently, by at most one segment that has rolled but not yet been released. It
plateaus at a level that moves with `max_log_size`. Under the same workload with `max_log_size`
effectively unbounded, or with `archive_command` set, rolled bytes grow linearly without limit.
Segments outside the archiver's tracking (the current segment, files present before enable) are
not capped.

### B2. Unit tier

**B2a. Environment and build.**
- **Machine and JDK:** a Linux host with JDK 11 and Ant. Run as a **non-root** user, because
  part A4 below relies on file permissions.
- **Working copy:** copy the tree to local disk and build there:
  `export W=/local/o72-unit && mkdir -p $W && rsync -a ~/cassandra-5.0.9/ $W/src/ && cd $W/src && ant jar`.
  `jar` depends on `build-test` (`build.xml:827-828`).
- **Test source:** create `$W/src/test/unit/org/apache/cassandra/utils/binlog/DeletingArchiverBoundTest.java`.
  It goes in the same package so it can reach the package-private `getBytesInStoreFiles()`
  (`DeletingArchiver.java:80`) and `BinLogTest.record(String)` (`BinLogTest.java:469`).
- *Stage-4 amendment M1 (2026-11-24, audit, before any reading):* node `ms0611` (aarch64, 8 cores,
  62 GiB, run as `jason92`, non-root). `W=/mydata/jingsong-cass-s4/o72/unit`; `$W/src` is a `cp -a`
  of `/mydata/s4/cassandra-base` (a `copy-source.sh` copy of `cassandra-5.0.9`, already built with
  `build-test`), so the `rsync … && ant jar` line is replaced by that copy; `ant testsome` compiles the
  new test class. The test source is kept in the stage-4 harness folder and copied into `$W/src`.

```java
package org.apache.cassandra.utils.binlog;

import java.io.File; // checkstyle: permit this import
import java.lang.reflect.Field;
import java.nio.file.*;
import java.util.*;
import java.util.stream.*;
import org.junit.*;
import org.apache.cassandra.config.DatabaseDescriptor;

public class DeletingArchiverBoundTest
{
    static final long MiB = 1L << 20;

    @BeforeClass public static void init() { DatabaseDescriptor.daemonInitialization(); }

    static long env(String k, long d) { String v = System.getenv(k); return v == null ? d : Long.parseLong(v); }
    static List<Path> cq4(Path dir) throws Exception
    {
        try (Stream<Path> s = Files.list(dir)) { return s.filter(p -> p.toString().endsWith(".cq4")).sorted().collect(Collectors.toList()); }
    }
    static long sum(List<Path> ps) { long t = 0; for (Path p : ps) t += p.toFile().length(); return t; }
    @SuppressWarnings("unchecked")
    static Queue<File> tracked(DeletingArchiver da) throws Exception
    { Field f = DeletingArchiver.class.getDeclaredField("chronicleStoreFiles"); f.setAccessible(true); return (Queue<File>) f.get(da); }

    /** A: synthetic 1 MiB files, three limits. A4: delete-failure branch. */
    @Test public void synthetic() throws Exception
    {
        Path base = Paths.get(System.getenv("O72_DIR"));
        for (long limit : new long[]{ 512 * 1024, 7 * MiB / 2, 10 * MiB })
        {
            Path dir = Files.createDirectories(base.resolve("A-" + limit));
            DeletingArchiver da = new DeletingArchiver(limit);
            for (int i = 0; i < 20; i++)
            {
                Path p = dir.resolve(String.format("f%02d.cq4", i));
                Files.write(p, new byte[(int) MiB]);
                da.onReleased(i, p.toFile());
                List<Path> on = cq4(dir);
                System.out.printf("O72A limit=%d step=%d operand=%d onDisk=%d files=%d%n", limit, i, da.getBytesInStoreFiles(), sum(on), on.size());
            }
        }
        // A4: an undeletable file (its directory read-only) in the middle of the stream
        Path ok = Files.createDirectories(base.resolve("A4-ok")), ro = Files.createDirectories(base.resolve("A4-ro"));
        DeletingArchiver da = new DeletingArchiver(7 * MiB / 2);
        for (int i = 0; i < 12; i++)
        {
            Path d = (i == 0) ? ro : ok;
            Path p = d.resolve(String.format("g%02d.cq4", i));
            Files.write(p, new byte[(int) MiB]);
            if (i == 0) ro.toFile().setWritable(false);
            da.onReleased(i, p.toFile());
            System.out.printf("O72A4 step=%d operand=%d onDiskOk=%d onDiskRo=%d tracked=%d%n", i, da.getBytesInStoreFiles(), sum(cq4(ok)), sum(cq4(ro)), tracked(da).size());
        }
        ro.toFile().setWritable(true);
    }

    /** B: real BinLog with TEST_SECONDLY roll; limit from O72_LIMIT; ~2 MiB/s for O72_SECONDS. */
    @Test public void realBinLog() throws Exception
    {
        long limit = env("O72_LIMIT", 1L << 30);
        long seconds = env("O72_SECONDS", 40);
        Path dir = Files.createDirectories(Paths.get(System.getenv("O72_DIR")).resolve("B-" + limit));
        BinLog bl = new BinLog.Builder().path(dir).rollCycle("TEST_SECONDLY").maxQueueWeight(256 * 1024 * 1024)
                                        .maxLogSize(limit).blocking(true).build(false);
        Field af = BinLog.class.getDeclaredField("archiver"); af.setAccessible(true);
        DeletingArchiver da = (DeletingArchiver) af.get(bl);
        char[] c = new char[64 * 1024]; Arrays.fill(c, 'a'); String payload = new String(c);
        Map<String, Long> firstSeen = new HashMap<>();
        long end = System.currentTimeMillis() + seconds * 1000, maxOperand = 0, maxRolled = 0, maxTotal = 0;
        while (System.currentTimeMillis() < end)
        {
            for (int i = 0; i < 6; i++) bl.put(BinLogTest.record(payload));   // 6 x 64 KiB per 200 ms = ~1.9 MiB/s
            Thread.sleep(200);
            List<Path> on = cq4(dir);
            List<Path> rolled = on.isEmpty() ? on : on.subList(0, on.size() - 1);
            long operand = da.getBytesInStoreFiles(), r = sum(rolled), t = sum(on);
            for (File f : tracked(da)) firstSeen.putIfAbsent(f.getName(), f.length());
            maxOperand = Math.max(maxOperand, operand); maxRolled = Math.max(maxRolled, r); maxTotal = Math.max(maxTotal, t);
            System.out.printf("O72B limit=%d t=%d operand=%d tracked=%d rolledOnDisk=%d totalOnDisk=%d files=%d%n",
                              limit, System.currentTimeMillis(), operand, tracked(da).size(), r, t, on.size());
        }
        for (File f : tracked(da))
            System.out.printf("O72B-LEN file=%s lenAtFirstSeen=%d lenNow=%d%n", f.getName(), firstSeen.getOrDefault(f.getName(), -1L), f.length());
        System.out.printf("O72B-MAX limit=%d maxOperand=%d maxRolled=%d maxTotal=%d%n", limit, maxOperand, maxRolled, maxTotal);
        bl.stop();
    }
}
```

- **JVM options:** the defaults of `ant testsome`. The test reads its knobs from environment
  variables, which the forked JUnit JVM inherits.

**B2b. Knobs.**
- **Test A** (synthetic, `DeletingArchiver` alone): `maxLogSize` = 512 KiB (below one file),
  3.5 MiB (between 3 and 4 files), and 10 MiB (exactly 10 files, to test that `>` is strict).
  These are set in the code.
- **Test B** (real `BinLog`): `O72_LIMIT`.
  - **B0 (calibration and positive control):** 1073741824 (1 GiB, never reached).
  - **B1:** `2.5 × F'`.
  - **B2:** `5.5 × F'`.
  - `F'` is the median `lenAtFirstSeen` from the B0 `O72B-LEN` lines, i.e. the length a
    one-second segment has when it is released. Picking non-integer multiples makes the expected
    retained count `floor(M/F')` (2 and 5) unambiguous.

- *Stage-4 amendment M2 (2026-11-24, audit, before any reading):* **B0 uses `O72_LIMIT=1099511627776`
  (1 TiB) instead of 1 GiB.** Reason, independent of any reading: B2c itself allows `F'` > 30 MiB and
  then 120 s (about 120 releases), which is more than 1 GiB of tracked apparent bytes, so a 1 GiB B0
  would delete and stop being the positive control. B0's prediction (grows, no deletion) is unchanged.
  B0 runs 40 s; B1 and B2 run 40 s, or 120 s if `F'` > 30 MiB (B2c).

**B2c. Workload.**
- **Test A:** 20 synthetic files of 1 MiB each, which is 20 MiB offered, at least twice every
  limit.
- **Test B:** 6 records of 64 KiB every 200 ms, about 1.9 MiB/s. With the `TEST_SECONDLY` roll
  each segment holds about 1.9 MiB of data. 40 s is about 76 MiB written, about 30 segments for
  B1 and about 14 for B2, so the limit is crossed after the 3rd or 6th release.
- If Chronicle pre-sizes segments so that `F'` is much larger than the content (A3(d)), `F'`
  from B0 absorbs that.
  - If `F'` > 30 MiB, raise `O72_SECONDS` to 120 so that at least 6 segments go past `5.5 × F'`
    in content terms. Retention is counted in files, so 40 s still gives about 40 releases.

**B2d. Observables and instruments.**
- **Measured:**
  - the operand `bytesInStoreFiles`, via `getBytesInStoreFiles()`;
  - the tracked FIFO size, via reflection;
  - the apparent bytes of all on-disk `*.cq4`, of the rolled ones (all but the name-newest), and
    of the current segment;
  - per tracked file, the length at first sighting and at the end (shrink detection, A3(d)).
- **Sampling:** every 200 ms, printed as `O72B` lines.
- **Allocated blocks:** during B runs, run `while sleep 1; do du -B1 -s $W/out/B-*; done > $W/du.txt`
  in a second shell.
- **Not observable:** the exact moment Chronicle calls `onReleased` relative to the roll (the
  operand changing is the proxy), and Chronicle's internal file shrinking.

**B2e. Procedure.**
1. `export O72_DIR=$W/out && mkdir -p $O72_DIR && cd $W/src`.
2. Test A: `ant testsome -Dtest.name=org.apache.cassandra.utils.binlog.DeletingArchiverBoundTest -Dtest.methods=synthetic`.
   Collect the `O72A` and `O72A4` lines from
   `build/test/output/TEST-org.apache.cassandra.utils.binlog.DeletingArchiverBoundTest.xml`
   (or the console).
3. B0: `O72_LIMIT=1073741824 ant testsome -Dtest.name=org.apache.cassandra.utils.binlog.DeletingArchiverBoundTest -Dtest.methods=realBinLog`.
   Compute `F'` as the median `lenAtFirstSeen`. Also record `lenNow − lenAtFirstSeen` per file
   (shrink).
4. B1: the same command with `O72_LIMIT=$(( F' * 5 / 2 ))`.
5. B2: the same command with `O72_LIMIT=$(( F' * 11 / 2 ))`.
6. After each run, `rm -rf $O72_DIR/B-*`. At the end, `rm -rf $W/out` and check
   `pgrep -f DeletingArchiverBoundTest` is empty.

- *Stage-4 amendment M3 (2026-11-24, audit, before any reading):* with `-Dtest.methods`, `testsome`
  writes `build/test/output/TEST-<class>-<method>.xml` (`build.xml` `testsome`), not the file named in
  step 2; the readings come from that file. Each `ant testsome` runs under `script`/`tee` with its
  console log kept in `$W/logs/`. The `du` sampler of B2d runs during each B run into
  `$W/du-<run>.txt`.

**B2f. Predictions.**
- **A, 512 KiB:** every step has `operand=0 onDisk=0 files=0`.
- **A, 3.5 MiB:** steps 0–2 have `operand=(i+1) MiB`. From step 3 on, every step has
  `operand=3145728 onDisk=3145728 files=3`.
- **A, 10 MiB:** steps 0–9 grow to `operand=10485760 files=10` (equality does not delete). From
  step 10 on, `operand=10485760 files=10`.
- **A4 (limit 3.5 MiB, file g00 undeletable):**
  - At step 3 the delete of g00 fails and is logged at ERROR, and the operand stays at 4 MiB.
  - The loop then deletes g01 (operand 3 MiB, tracked = 2).
  - From then on, every step has `operand=3145728 tracked=2 onDiskOk=2097152 onDiskRo=1048576`.
    g00's 1 MiB stays in the operand for good, so retention drops from 3 files to 2, and the
    total on disk stays at 3 MiB, still ≤ limit.
- **B0:** the operand and `rolledOnDisk` grow by about `F'` per second with no deletion.
  `maxOperand ≈ (seconds−1) × F'`.
- **B1 and B2, with limit `M`:**
  - every sample has `operand ≤ M`;
  - at plateau, `tracked = floor(M/F')`, which is 2 for B1 and 5 for B2;
  - `rolledOnDisk ≤ M + F'` (at most one rolled-but-unreleased segment);
  - `maxRolled` for B2 is about `2.2 ×` that for B1 (5/2 files plus the same transient);
  - `totalOnDisk ≤ M + 2·F'`.
- **Shrink:** if `lenNow < lenAtFirstSeen`, expect `operand > sum(lengths of tracked files)` and
  `tracked < floor(M/F')` over time (drift, A3(d)), still with `rolledOnDisk ≤ M + F'`.

**B2g. Readings.**

| Observation | Meaning |
|---|---|
| A rows match B2f exactly | the loop at `:60` enforces the tracked sum ≤ limit, strict `>` |
| A 3.5 MiB keeps 4 files or `operand > limit` after a call returns | **claim wrong** (check not enforcing) |
| A4 matches B2f (g00 survives, operand stuck 1 MiB high, 2 files retained) | delete-failure path as traced (A3(e)): over-retains nothing, under-retains thereafter; cap still holds |
| B1/B2 `operand ≤ M` always, `rolledOnDisk` plateaus near `floor(M/F')·F'`, B2 plateau ≈ 2.2× B1, while B0 grows linearly | **claim confirmed** at unit tier |
| B1/B2 `rolledOnDisk` exceeds `M + F'` for ≥ 3 consecutive seconds, or grows like B0 | **claim wrong** |
| B0 does not grow (no rolls) | workload or roll cycle did not work; nothing concluded |
| `lenNow < lenAtFirstSeen` and `tracked` drops toward 0 | drift (A3(d)): the cap over-enforces; claim (upper bound) still holds, report separately |

*Stage-4 amendment M4 (2026-11-24, audit, before any reading): how the B2g rows are read.*
- **A rows:** exact equality with every B2f number (operand, onDisk, files; A4 operand, tracked,
  onDiskOk, onDiskRo, and one ERROR `Failed to delete chronicle store file` line for g00).
- **B, per run with limit `M`** (samples are the `O72B` lines; *steady* = samples from the first one
  whose `tracked` is at least `floor(M/F')` and after the first decrease of the operand, to the end):
  - *bounded*: every sample has `operand ≤ M`, and no run of ≥ 15 consecutive samples (3 s) has
    `rolledOnDisk > M + F'`;
  - *plateau*: the median `rolledOnDisk` over steady samples is in `[floor(M/F')·F', (floor(M/F')+1)·F']`
    (5 % slack on both ends), and the mode of `tracked` over steady samples is `floor(M/F')`;
  - *follows the knob*: median steady `rolledOnDisk` of B2 / that of B1 is in `[1.8, 2.8]`;
  - *B0 grows*: B0's final `rolledOnDisk` ≥ 10·F' and B0's operand never decreases.
- Row 4 (confirmed) needs A rows matched, B0 grows, and both B1 and B2 bounded, at plateau and
  following the knob. Row 5 (wrong) is any B1/B2 sample breaking *bounded*, or B1/B2 growing like B0
  (final `rolledOnDisk` ≥ 0.5 × B0's). Row 6: B0 has fewer than 5 rolled files at the end. Row 7 is
  recorded beside the others when `lenNow < lenAtFirstSeen` for any tracked file. A mix that fits no
  row is "Not confirmed (no matching row)".

**B2h. Controls.**
- **B0 (positive control):** the same workload with an unreachable limit shows that usage grows
  when the cap does not bind.
- **Two limits:** B1 and B2 show the plateau moves with the knob.
- **Test A:** isolates the check from Chronicle's timing.
- **Fresh directories:** each run uses a new directory, so no pre-existing files (A3(b)) are
  involved.

### B3. Cluster tier

**B3a. Environment and build.**
- **Node:** one Linux node with JDK 11 and Ant, at least 30 GiB free on local (non-shared) disk.
  Run as a non-root user.
- **Build:**
  `export RUN=/local/o72-cluster && mkdir -p $RUN && rsync -a ~/cassandra-5.0.9/ $RUN/src/ && cd $RUN/src && ant jar`.
  This builds the server, `tools/bin/cassandra-stress` and `nodetool`.
- **Configuration**, edit `$RUN/src/conf/cassandra.yaml`:
  - `data_file_directories: [$RUN/data]`
  - `commitlog_directory: $RUN/commitlog`
  - `hints_directory: $RUN/hints`
  - `saved_caches_directory: $RUN/saved_caches`
  - `cdc_raw_directory: $RUN/cdc_raw`
  - `auto_snapshot: false`
  - `full_query_logging_options:` with `log_dir: $RUN/fql` and
    `allow_nodetool_archive_command: true` (needed only for control C2)
  - leave `audit_logging_options.enabled: false`

  Write the expanded literal paths, since yaml does not expand `$RUN`. If ports 9042, 7000 or 7199
  are in use on the host, change `native_transport_port`, `storage_port` and JMX
  (`JMX_PORT` in `conf/cassandra-env.sh`) and pass `-p <jmx>` to nodetool.
- **JVM:** `export MAX_HEAP_SIZE=2G HEAP_NEWSIZE=400M CASSANDRA_LOG_DIR=$RUN/logs`.
- **Start:** `bin/cassandra -p $RUN/cassandra.pid`. Wait until `bin/nodetool status` shows `UN`.
- *Stage-4 amendment M5 (2026-11-24, audit, before any reading):* `RUN=/mydata/jingsong-cass-s4/o72/cluster`
  on `ms0611`; `$RUN/src` is a `cp -a` of the built `/mydata/s4/cassandra-base` (no `ant jar`).
  Ports 7000/7199/9042 were free and the node is held by a lock for this run, so the defaults stay.
  `ulimit -n 100000` before `bin/cassandra` (soft limit 1024 on the node). The node is started with
  `bin/cassandra -p $RUN/cassandra.pid` and is up when `nodetool status` shows `UN` and
  `nodetool statusbinary` prints `running`.

**B3b. Knobs.** All are set via
`nodetool enablefullquerylog --path $RUN/fql-<tag> --roll-cycle MINUTELY --blocking true --max-log-size <M>`.
`MINUTELY` is used so that segments roll within the run (the default `HOURLY` would never roll,
A3(a)).

| Run | `--max-log-size` | Other | Why |
|---|---|---|---|
| C1 (positive control / calibration) | 17179869184 (default 16 GiB) | — | never reached; gives the per-minute segment size `F` and growth rate |
| K1 | 314572800 (300 MiB ≈ 2.5·F nominal) | — | expect 2 retained rolled segments |
| K2 | 692060160 (660 MiB ≈ 5.5·F nominal) | — | expect 5 retained; plateau moves with knob |
| C2 (mechanism control) | 314572800 | `--archive-command "/bin/true %path"` | same limit, `ExternalArchiver`: limit should not bind |
| P (pre-existing bypass, optional) | 314572800 | re-enable on K1's path without reset | A3(b) |

If C1's measured `F` differs from 120 MiB by more than 25 %, rescale K1 and K2 to `2.5·F` and
`5.5·F` before running them.

- *Stage-4 amendment M6 (2026-11-24, audit, before any reading):* the rescale rule's `F` is read as
  `F'`, the median `rolled file size` of C1's DEBUG lines (the length the archiver counts, which B3f's
  plateau `floor(M/F')·F'` uses). If it differs from 120 MiB (125829120) by more than 25 %, K1 and K2
  (and C2) use `floor(2.5·F')` and `floor(5.5·F')`; otherwise the table's values.

**B3c. Workload.**
- **Command:**
  `tools/bin/cassandra-stress write n=480000 cl=ONE -col 'size=FIXED(1000)' 'n=FIXED(5)' -rate threads=16 'fixed=400/s' -node 127.0.0.1 -log file=$RUN/stress-<tag>.log`
- **Volume:** 400 prepared writes/s, each logged by FQL with its query string and five 1000-byte
  bound values (`FullQueryLogger.executeSuccess`, `FullQueryLogger.java:324`). That is about
  5.2 KB per record, about 2 MiB/s, about **120 MiB per MINUTELY segment**.
- **Duration:** 480000 ops is 20 minutes, which gives about 20 segments and about 2.4 GiB of FQL,
  about 8× K1 and about 3.6× K2.
- **Other disk:** SSTables add about 2.4 GB per run, removed between runs with truncate.

**B3d. Observables and instruments.**
- **Sampler**, run every 5 s per run, starting before enable:
  `F=$RUN/fql-<tag>; while sleep 5; do L=$(ls $F/*.cq4 2>/dev/null | sort); n=$(echo "$L" | grep -c cq4); r=$(echo "$L" | head -n -1 | xargs -r stat -c %s | awk '{s+=$1}END{print s+0}'); t=$(echo "$L" | xargs -r stat -c %s | awk '{s+=$1}END{print s+0}'); a=$(du -B1 -s $F | cut -f1); echo "$(date +%s) $n $r $t $a"; done > $RUN/sample-<tag>.txt`.
  The columns are epoch, segment count, rolled apparent bytes, total apparent bytes, and
  allocated bytes.
- **Operand:** every deletion logs it in `$RUN/logs/system.log` as
  `Deleted chronicle store file: … bytes in store files: X max log size: M`.
  `grep -c "Deleted chronicle store file"` counts deletions. With
  `nodetool setlogginglevel org.apache.cassandra.utils.binlog.DeletingArchiver DEBUG`,
  `debug.log` also shows each release's `rolled file size`, which is `F'`.
- **Configuration check:** `nodetool getfullquerylog` confirms `max_log_size`, `roll_cycle` and
  `archive_command` per run.
- **Not observable directly:** the in-memory `bytesInStoreFiles` between deletions, and the exact
  release instant.

**B3e. Procedure.**
1. Start the node (B3a).
2. Run `nodetool setlogginglevel org.apache.cassandra.utils.binlog.DeletingArchiver DEBUG`.
3. For each run tag in order C1, K1, K2, C2:
   1. `mkdir -p $RUN/fql-<tag>` and start the sampler in the background.
   2. `bin/nodetool enablefullquerylog --path $RUN/fql-<tag> --roll-cycle MINUTELY --blocking true --max-log-size <M> [--archive-command "/bin/true %path"]`
   3. `bin/nodetool getfullquerylog > $RUN/conf-<tag>.txt`
   4. Run the cassandra-stress command from B3c (20 min).
   5. Wait 70 s with no load, then send one write so the last segment rolls:
      `tools/bin/cassandra-stress write n=1 -node 127.0.0.1`.
   6. Wait 10 s.
   7. `bin/nodetool disablefullquerylog`. Stop the sampler.
   8. `cp $RUN/logs/system.log $RUN/system-<tag>.log`.
   9. `bin/nodetool truncate keyspace1 standard1`.
      *Stage-4 runbook defect D1 (2026-11-24, found at the end of C1):* `nodetool` has no `truncate`
      command in 5.0.9 (`nodetool: Found unexpected parameters: [truncate, keyspace1, standard1]`); use
      `bin/cqlsh -e "TRUNCATE keyspace1.standard1"`. The step only frees SSTable disk between runs and
      touches no B3d observable; predictions and conclusions are unchanged.
   10. Unless it is K1 (kept for P), `rm -rf $RUN/fql-<tag>`.
4. P (optional):
   1. `ls -l $RUN/fql-K1` to record its leftover files.
   2. Re-enable with `--path $RUN/fql-K1 --max-log-size 314572800 --roll-cycle MINUTELY`.
   3. Run the stress command for 10 min (`n=240000`).
   4. Disable FQL.
   5. Compare the K1 leftover files, which should persist unchanged, with the new ones.
5. Cleanup (B4).

- *Stage-4 amendment M7 (2026-11-24, audit, before any reading):* step 3.5's single write uses
  `tools/bin/cassandra-stress write n=1 -rate threads=1 -node 127.0.0.1` (without `-rate` stress
  may step through thread counts). Before each run, `df -h $RUN` must show ≥ 15 GiB free (B4).
  `F'` for a K or C2 run is that run's median DEBUG `rolled file size`. The run order is C1, K1, K2,
  C2; P runs only if the 3 h wall-clock cap leaves time.

**B3f. Predictions** (`F` is about 120 MiB, `F'` the release length from DEBUG lines).
- **C1:** rolled bytes grow by about `F` per minute to about 2.3 GiB at 20 min, and there are zero
  "Deleted chronicle store file" lines.
- **K1:**
  - first deletion at about the 3rd roll (t ≈ 3–4 min);
  - after that, rolled bytes plateau at `floor(M/F')·F'`, which is 2 segments, about 240 MiB;
  - rolled bytes are never above 300 MiB plus one segment in transit;
  - total directory size ≤ 300 MiB + current segment (≤ `F` + Chronicle pre-size);
  - the logged `bytes in store files` is always ≤ 314572800;
  - the number of deletions is about the number of rolls minus 2.
- **K2:**
  - first deletion at about the 6th roll;
  - the plateau is 5 segments, about 600 MiB, ≤ 660 MiB, which is about 2.5× K1's plateau.
- **C2:** grows like C1 (about 2.3 GiB) despite `M = 300 MiB`, with no deletion lines.
- **P:** K1's leftover files remain throughout. The directory total reaches the leftover plus up
  to `M`, i.e. above `M`.
- **Allocated (`du -B1`)** ≤ apparent for every sample.

**B3g. Readings.**

| Observation | Meaning |
|---|---|
| K1/K2 rolled bytes plateau ≤ M (+ ≤ 1 segment transient), K2 ≈ 2.5× K1, while C1 and C2 grow linearly | **claim confirmed**: `max_log_size` governs rolled binlog disk |
| K1 or K2 rolled bytes exceed `M + F'` for ≥ 3 consecutive rolls, or grow like C1 | **claim wrong** |
| K1 plateau ≈ K2 plateau | usage does not follow the knob; **claim wrong** (or both limited by something else; check log lines) |
| C1 does not grow (no rolls, FQL not logging) | workload invalid; nothing concluded |
| C2 bounded like K1 | `archive_command` not honoured or misconfigured; recheck `conf-C2.txt` |
| plateau well below `floor(M/F')·F'` and logged `bytes in store files` > on-disk rolled bytes | drift (A3(d)): over-deletion; upper-bound claim still holds |
| P leftovers persist and total > M | pre-existing-file bypass confirmed (A3(b)) |
| total directory > M only by the current segment | expected: the current segment is outside the cap (A3(a)) |

*Stage-4 amendment M8 (2026-11-24, audit, before any reading): how the B3g rows are read.*
`r` is the sampler's rolled apparent bytes; the *steady window* of a K run is from 60 s after its
first deletion line to the end of stress; its *plateau* is the median `r` in that window.
- *bounded*: every logged `bytes in store files` ≤ M, and no ≥ 3 consecutive minutes (36 samples)
  with `r > M + F'`;
- *plateau*: K plateau in `[floor(M/F')·F', (floor(M/F')+1)·F']` (5 % slack);
- *follows the knob*: K2 plateau / K1 plateau in `[2.0, 3.0]`; ≤ 1.25 is row 3 ("plateau ≈");
- *grows*: C1 and C2 have zero deletion lines and final `r` ≥ 0.8 × (number of rolled segments × F').
- Row 1 (confirmed) needs K1 and K2 bounded, at plateau and following the knob, with C1 and C2
  growing. Row 2 is any K sample run breaking *bounded* or a K run that grows like C1. Row 4: C1 has
  fewer than 5 rolled segments. Row 5: C2 has a deletion line or is bounded like K1. Rows 6-8 are
  recorded beside the matched row. A mix that fits no row is "Not confirmed (no matching row)".

**B3h. Controls.**
- **C1 (positive control):** the same workload with an unreachable limit moves usage, showing the
  workload is capable of exceeding K1 and K2.
- **C2 (mechanism control):** the same limit with the archiver swapped shows the bound comes from
  `DeletingArchiver`.
- **K1 vs K2:** the plateau tracks the knob.
- **Configuration and paths:** `getfullquerylog` output pins the configuration of each run, and a
  fresh path per run excludes pre-existing files except in P.
- **Pacing:** stress is rate-limited, so `F` is stable across runs. Compare each run's stress
  op-rate log to be sure.

**B4. Risks and cleanup.**
- **Disk:**
  - Unit: about 80 MiB per B run plus 20 MiB for A, all under `$W/out`.
  - Cluster: about 2.4 GiB FQL (C1, C2) plus about 2.4 GB SSTables plus a commit log of up to
    8 GiB (`commitlog_total_space` default) per run, all under `$RUN`. Check `df -h $RUN` before
    each run and stop if under 15 GiB free.
- **Never use shared storage:** nothing is written into `~/cassandra-5.0.9` or any NFS path.
- **Cleanup:**
  1. `bin/nodetool disablefullquerylog; bin/nodetool resetfullquerylog`
  2. `kill $(cat $RUN/cassandra.pid)`, then wait until
     `pgrep -u $USER -f CassandraDaemon` returns nothing (`kill -9` after 60 s).
  3. Kill any sampler loops (`pkill -f "sample-"`, or by recorded PID) and any leftover
     `cassandra-stress` or `ant` JVMs (`pgrep -u $USER -f 'cassandra-stress|junit'`).
  4. Remove the work directories: `rm -rf $RUN $W`.
  5. Confirm `pgrep -u $USER java` lists nothing started by these runs.
- **Run as non-root:** A4's read-only-directory trick fails as root, and root would also leave
  root-owned files behind.

## C. Sources read

src/java/org/apache/cassandra/utils/binlog/DeletingArchiver.java
src/java/org/apache/cassandra/utils/binlog/BinLog.java
src/java/org/apache/cassandra/utils/binlog/BinLogOptions.java
src/java/org/apache/cassandra/utils/binlog/BinLogArchiver.java
src/java/org/apache/cassandra/utils/binlog/ExternalArchiver.java
src/java/org/apache/cassandra/fql/FullQueryLogger.java
src/java/org/apache/cassandra/fql/FullQueryLoggerOptions.java
src/java/org/apache/cassandra/audit/BinAuditLogger.java
src/java/org/apache/cassandra/audit/AuditLogOptions.java
src/java/org/apache/cassandra/service/StorageService.java (6983–7023, 7131–7169)
src/java/org/apache/cassandra/tools/nodetool/EnableFullQueryLog.java
src/java/org/apache/cassandra/tools/nodetool/EnableAuditLog.java (grep)
src/java/org/apache/cassandra/config/Config.java (grep, 703–704)
src/java/org/apache/cassandra/utils/concurrent/WeightedQueue.java (grep)
test/unit/org/apache/cassandra/utils/binlog/DeletingArchiverTest.java
test/unit/org/apache/cassandra/utils/binlog/BinLogTest.java
test/unit/org/apache/cassandra/fql/FullQueryLoggerTest.java (grep)
conf/cassandra.yaml (audit_logging_options, full_query_logging_options, directory keys)
doc/modules/cassandra/pages/managing/operating/fqllogging.adoc
doc/modules/cassandra/pages/managing/operating/auditlogging.adoc (grep)
build.xml (targets jar, stress-build, testsome)
.build/parent-pom-template.xml (Chronicle versions)
CHANGES.txt (grep)
https://issues.apache.org/jira/browse/CASSANDRA-16526 (cited from BinLogTest; not fetched)

## D. Stage-4 feedback

none yet
