# commitlog_total_space — verification solution  <!-- file: cases/commitlog_total_space-maybeFlushToReclaim-unused--autonomous.md -->

| Field | Value |
|---|---|
| Entry pointer | `src/java/org/apache/cassandra/db/commitlog/AbstractCommitLogSegmentManager.java:249` (`if (unused < 0)` in `maybeFlushToReclaim()`) |
| Pinned source | `cassandra-5.0.9` (HEAD `b5f2a54 Prepare debian changelog for 5.0.9`) |
| Session / date | Claude Opus 5.5 (`claude-opus-5-5`), Claude Code 2.1.305, 2026-10-21 |
| Estimate | `positive`, but only as a soft cap. When the tracked commit-log size goes over `commitlog_total_space`, the segment-allocator thread forces memtable flushes of the oldest segments. After those flushes the segments are deleted, so commit-log disk use comes back down to about the limit. Writes are never blocked, so the peak overshoots by however much is written while the flush is running. |
| Ground | — |

## A. Constraint trace

**A1. The constraint.**
- Name: `commitlog_total_space`. The old name `commitlog_total_space_in_mb` is still accepted as a deprecated alias.
- Kind: a `cassandra.yaml` configuration entry, read again at run time on every check.
- Declared at `src/java/org/apache/cassandra/config/Config.java:389-390` as `public DataStorageSpec.IntMebibytesBound commitlog_total_space;` with `@Replaces(oldName = "commitlog_total_space_in_mb", ...)`. Its initial value is `null`.
- Unit: MiB (`IntMebibytesBound`). The code compares in bytes: `getTotalCommitlogSpaceInMiB() * 1024 * 1024`, at `AbstractCommitLogSegmentManager.java:447`.
- Default, set in `DatabaseDescriptor.applySimpleConfig`, `DatabaseDescriptor.java:664-675`: if the value is unset, it becomes `calculateDefaultSpaceInMiB("commitlog", commitlog_directory, ..., preferred=8192, totalSpaceOfCommitlogVolume, 1, 4)`. That function is at `DatabaseDescriptor.java:1147-1162` and returns min(8192 MiB, ¼ of the total size of the file store holding `commitlog_directory`). When it picks the smaller value it logs the warning "Small commitlog volume detected". `conf/cassandra.yaml:874-883` documents the same rule, with the entry commented out (`# commitlog_total_space: 8192MiB`).
- Accessor: `DatabaseDescriptor.getTotalCommitlogSpaceInMiB()` at `DatabaseDescriptor.java:3829-3832`.
- How to set it: only through `cassandra.yaml`. There is no setter in `DatabaseDescriptor`, no JMX operation and no nodetool command (grep of `src/java` finds no other reference). A change needs a restart. Unit tests can mutate `DatabaseDescriptor.getRawConfig().commitlog_total_space`, and because the getter reads `conf` on every call, such a change takes effect at once.

**A2. What it caps.**
- Resource: disk, specifically the commit-log segment files in `commitlog_directory`.
- The quantity compared is `AbstractCommitLogSegmentManager.size`, an `AtomicLong` at `AbstractCommitLogSegmentManager.java:103`, returned by `onDiskSize()` at `:440-443`. It is an accounting counter, not a `du` of the directory. It is maintained through `addSize()` at `:432-435`:
  - mmap segments add the full `commitlog_segment_size` when the segment is created and mapped (`MemoryMappedSegment.java:62-63`; `onDiskSize()` is the segment size, `:103-106`). This includes the pre-created reserve segment `availableSegment`.
  - Compressed, encrypted and direct-IO segments add bytes as they are written (`CompressedSegment.java:81`, `EncryptedSegment.java:131,141`, `FileDirectSegment.java:49`, `DirectIOSegment.java:130`).
  - Discard subtracts `onDiskSize()` (`CommitLogSegmentManagerStandard.java:31-37`, `CommitLogSegment.java:430-436`).
- The value is exported as the JMX gauge `org.apache.cassandra.metrics:type=CommitLog,name=TotalCommitLogSize` (`metrics/CommitLogMetrics.java:74-80`) and as `CommitLog.getActiveOnDiskSize()` (`CommitLog.java:439-442`).
- Default mode: `commitlog_disk_access_mode: legacy` (`Config.java:401`, `conf/cassandra.yaml:678`) resolves to `mmap` when there is no compression or encryption (`DatabaseDescriptor.java:1525-1528`). So by default the operand moves in whole-segment steps, 32 MiB each by default (`Config.java:397`).

**A3. Mechanism.**
1. The `COMMIT-LOG-ALLOCATOR` thread runs `AllocatorRunnable.run()` (`AbstractCommitLogSegmentManager.java:163-238`, started at `:150-161`). In state `NORMAL` it creates the next reserve segment (`availableSegment = createSegment()`, `:189`; for mmap this calls `addSize(+segment_size)`) and signals writers (`:191`).
2. If a writer is already waiting for another segment (`availableSegment == null && !atSegmentBufferLimit()`), the thread returns immediately and skips the space check (`:194-196`). Otherwise it calls `maybeFlushToReclaim()` (`:200`).
3. `maybeFlushToReclaim()` (`:246-264`) computes `unused = unusedCapacity()`, which is `commitlog_total_space_bytes - size` (`:445-451`).
4. **Line 249: `if (unused < 0)`**
   - **False** (under the limit): nothing happens.
   - **True** (over the limit): the code walks `activeSegments` from oldest to newest. It stops at `allocatingFrom`, the segment currently being written, which is never chosen (`:255-256`). It collects segments until `flushingSize + unused >= 0`, so only just enough to get back under the limit (`:257-260`). Then it calls `flushDataFrom(segments, emptyList, force=false)` (`:262`).
5. `flushDataFrom` (`:458-503`) looks at every table that is dirty in those segments:
   - Dropped tables are marked clean (`:474-479`).
   - Tables whose memtable writes are durable are marked clean (`:485-488`).
   - Every other table gets `cfs.forceFlush(maxCommitLogPosition)` (`:494-496`). That flushes the current memtable with reason `COMMITLOG_DIRTY` if it may hold data from before that position (`ColumnFamilyStore.java:1084-1092`).
   - The returned future is **not awaited**: the check is fire-and-forget.
6. When a flush finishes, `ColumnFamilyStore` calls `CommitLog.discardCompletedSegments` (`ColumnFamilyStore.java:1152`, `CommitLog.java:353`). That marks the segments clean, and `isUnused()` (`CommitLogSegment.java:611-620`) lets `archiveAndDiscard` (`AbstractCommitLogSegmentManager.java:406-414`) delete the file and lower `size`.
7. The thread then waits on `managerThreadWaitCondition` (`:108`, `:225`) until a writer takes the reserve segment. So the check runs **once per segment switch**, not once per write.

Overshoot and bypass paths:
- **Writes are never blocked.** `CommitLogSegmentManagerStandard.allocate` (`:47-60`) has no space check. While the forced flush runs, writers keep filling new segments, so the peak can exceed the limit by (write rate × flush time) plus one active segment and one reserve segment.
- **The check is skipped** when a writer is already waiting (`:194-196`), which happens under heavy write pressure. It then runs again on the next switch.
- **The `allocatingFrom` segment cannot be reclaimed** (`:255`), and the reserve segment is counted in `size`. So with mmap the floor is about 2 segments, even if `commitlog_total_space` is smaller than that.
- **If a flush fails** (for example the data disk is full or the flush writer is stuck), segments are never discarded and the log grows without bound. The check only *requests* flushes.
- **Failed archiving.** With `commitlog_archiving.properties` set and an archive command that fails, `discard(segment, false)` leaves the file on disk but still subtracts it from `size` (`CommitLogSegmentManagerStandard.java:33-36`). The disk then holds files the cap no longer counts.
- **Compressed and encrypted segments** count bytes written, not preallocated file size, so the counter and `du` differ. Not used here.

**A4. Other consumers.**
These use the same disk or volume but are outside this cap:
- CDC: the `cdc_raw` hard links, capped separately by `cdc_total_space` (`CommitLogSegmentManagerCDC`).
- Hints: `hints_directory`, capped by hint settings.
- Data SSTables. The flushes this cap forces actually *increase* data-dir usage.
- Archived segments.
- Commit-log files of a previous run, waiting to be replayed at startup.

Memory side:
- Memtables, heap and off-heap: the cap indirectly *lowers* memtable size by forcing flushes.
- Mapped segment buffers (page cache).
- The compressed/encrypted/direct-IO buffer pool, `SimpleCachedBufferPool`, bounded separately by `atSegmentBufferLimit()` (`:241-244`).

**A5. Evidence beyond the source.**
- `conf/cassandra.yaml:874-883` documents the behaviour: "If space gets above this value, Cassandra will flush every dirty CF in the oldest segment and remove it."
- `doc/modules/cassandra/pages/architecture/storage-engine.adoc:78` lists `commitlog_total_space`.
- `doc/.../configuration.adoc:106` gives the rename from `commitlog_total_space_in_mb`.
- The default-derivation comment refers to CASSANDRA-10013 and CASSANDRA-10199 (https://issues.apache.org/jira/browse/CASSANDRA-10013, https://issues.apache.org/jira/browse/CASSANDRA-10199). I did not consult them beyond the reference.
- No existing unit test exercises this limit. `test/unit/org/apache/cassandra/db/commitlog/CommitLogTest.java` shows the test set-up pattern I reuse (`:155-190`, `:365-398`).

## B. Verification solution

**B1. Claim under test.** With `commitlog_total_space = C`, sustained writes keep commit-log disk use (the `size` operand and the real bytes in `commitlog_directory`) bounded near C: peak ≤ C + a small overshoot, which grows with write rate. Forced `COMMITLOG_DIRTY` flushes produce a sawtooth. With C far above the volume written, the same workload makes commit-log usage grow in step with the bytes written. The claim is wrong if usage under a small C follows the uncapped trajectory, or if no `COMMITLOG_DIRTY` flushes happen.

### B2. Unit tier

**B2a. Environment and build.**
- JDK 11 and Ant, in the runner's own built clone `~/cassandra-run1` (tag `cassandra-5.0.9`, `ant build-test` already done). Never use the shared source tree.
- Add one test file, `~/cassandra-run1/test/unit/org/apache/cassandra/db/commitlog/CommitLogTotalSpaceCapTest.java` (B2e step 1).
- `ant testsome` forks the test JVM with `-Xmx4G` (build.xml macro) and `-Dcassandra.skip_sync=true` (`build.xml:1390`). `test/conf/cassandra.yaml:10-12` sets `commitlog_segment_size: 5MiB` and `commitlog_disk_access_mode: legacy` (resolves to mmap), with the commit log under `build/test/cassandra/commitlog`.
- Ant `-D` values do not reach the forked JVM, so parameters are passed as **environment variables**. The forked JUnit JVM inherits the environment.

> **Amendment 2026-10-21 (stage-4 audit, R1).** `ant testsome` forks the test JVM with **`maxmemory="1024m"`** (`build.xml:1152`, macro `testmacrohelper`); the `-Xmx4G` above is the `testlist` macro (`build.xml:1245-1255`), which `testsome` does not use. So `memtable_heap_space` defaults to heap/4 = **256 MiB** (`DatabaseDescriptor.java:586-587`), below the ~300 MiB the control arm puts in the memtable (test yaml `memtable_allocation_type: heap_buffers`), and the control would see `MEMTABLE_LIMIT` flushes at ≈ 0.99 × 256 MiB. Fix: the test also sets `c.memtable_heap_space = new DataStorageSpec.IntMebibytesBound(768)` next to `memtable_cleanup_threshold`, before `AbstractAllocatorMemtable.MEMORY_POOL` class-loads (it reads the limit at class load, `AbstractAllocatorMemtable.java:59,78-83`). A memtable-limit flush then needs ≈ 760 MiB, far above 300 MiB; ~300 MiB live in a 1 GiB heap is within reach. **Paths:** the run uses its own clone `~/cassandra-cts` (`cassandra-5.0.9`, `ant build-test` done) instead of `~/cassandra-run1`, and writes its outputs to `~/stage4-logs/cts/unit/` instead of `~/clcap-unit`.

**B2b. Knobs.**
- `CLCAP_MIB`, which the test writes into `DatabaseDescriptor.getRawConfig().commitlog_total_space` before the server starts. Values:
  - **15** (3 segments)
  - **25** (5 segments)
  - **50** (10 segments)
  - **100000** (control: effectively unlimited)

  This range runs from near the 2-segment floor up to 10 segments, with the uncapped control at the top.
- `CLCAP_SLEEP_MS` (writer throttle per mutation): **10** for the main arms. **0** for one extra overshoot probe at `CLCAP_MIB=25`.

**B2c. Workload.**
- One table `CLCapKS.t` (skiplist memtable, durable writes). `CLCAP_N=300` mutations, each with a 1 MiB value. That stays under `max_mutation_size` = segment/2 = 2.5 MiB (`DatabaseDescriptor.java:899`).
- Each mutation goes through `Mutation.apply()`, so it hits both the commit log and the memtable.
- Arithmetic: each 1 MiB mutation plus about 0.1 KiB of overhead lands 4 per 5 MiB segment. 300 mutations need about 75 segments, about 375 MiB of commit log. That is 25× the 15 MiB cap and 7.5× the 50 MiB cap, so the limit is crossed many times.
- To keep memtable-pressure flushes out: `memtable_cleanup_threshold = 0.99`, set in the raw config before the memtable pool class loads. `memtable_heap_space` defaults to heap/4 = 1024 MiB (`DatabaseDescriptor.java:586-587`), so a memory-triggered flush needs about 1014 MiB of memtable, far more than 375 MiB. Any memtable flush in the capped arms therefore comes from the commit-log check.
- System keyspaces are made non-durable (`KeyspaceParams.DEFAULT_LOCAL_DURABLE_WRITES = false`, as in `CommitLogTest.java:160`) so they do not add segments.

**B2d. Observables and instruments.** Sampled after every mutation and then once per second for 10 s of settling:
- `CommitLog.instance.segmentManager.onDiskSize()`: the operand at line 249.
- `getActiveSegments().size()`.
- `dirBytes`: the sum of `length()` over files in `DatabaseDescriptor.getCommitLogLocation()`. This is the real apparent size on disk.
- `cfs.metric.memtableSwitchCount.getCount()`: number of flushes of the table.

Results go to the CSV in `CLCAP_OUT`, plus a `SUMMARY` line on stdout and in `build/test/output/TEST-*.xml`. The value of `unused` at the moment of each check, and the flush reason, are not sampled directly. The switch count stands in for them. Optional: grep `build/test/logs` for `Reason: COMMITLOG_DIRTY` (`ColumnFamilyStore.java:1055`).

> **Amendment 2026-10-21 (stage-4 audit, R2).** The flush-reason count is **required**, not optional: it is the direct evidence that the line-249 true branch fired (`flushDataFrom` → `forceFlush(CommitLogPosition)` → `FlushReason.COMMITLOG_DIRTY`, `ColumnFamilyStore.java:1084-1092`; no other caller passes that reason with a position). Count `Enqueuing flush of CLCapKS.t, Reason: <R>` per reason. The test log is `build/test/logs/<testtag>/TEST-<suite>.log` at DEBUG level, rolled to `.log.N.gz` at 20 MB (`test/conf/logback-test.xml:27-38`), and it accumulates across runs in one clone: clear `build/test/logs` before each arm and count with `zgrep` over the whole tree. The test JVM routes `System.out` through a logger that may split one `printf` into pieces, so the test builds the `SUMMARY` line as one string and also appends it to `$CLCAP_OUT.summary`.

**B2e. Procedure.**
1. Create the test file:
```java
package org.apache.cassandra.db.commitlog;

import java.io.FileWriter;
import java.io.PrintWriter;
import java.nio.ByteBuffer;

import org.junit.BeforeClass;
import org.junit.Test;

import org.apache.cassandra.SchemaLoader;
import org.apache.cassandra.config.Config;
import org.apache.cassandra.config.DataStorageSpec;
import org.apache.cassandra.config.DatabaseDescriptor;
import org.apache.cassandra.db.ColumnFamilyStore;
import org.apache.cassandra.db.Keyspace;
import org.apache.cassandra.db.RowUpdateBuilder;
import org.apache.cassandra.db.marshal.AsciiType;
import org.apache.cassandra.db.marshal.BytesType;
import org.apache.cassandra.io.util.File;
import org.apache.cassandra.schema.KeyspaceParams;
import org.apache.cassandra.schema.MemtableParams;

public class CommitLogTotalSpaceCapTest
{
    static final String KS = "CLCapKS", T = "t";
    static int env(String k, int d) { String v = System.getenv(k); return v == null ? d : Integer.parseInt(v); }

    @BeforeClass
    public static void setup()
    {
        KeyspaceParams.DEFAULT_LOCAL_DURABLE_WRITES = false;
        DatabaseDescriptor.daemonInitialization();               // later calls are no-ops (DatabaseDescriptor.java:257-259)
        Config c = DatabaseDescriptor.getRawConfig();
        c.memtable_cleanup_threshold = 0.99f;                     // before MEMORY_POOL class-loads
        c.commitlog_total_space = new DataStorageSpec.IntMebibytesBound(env("CLCAP_MIB", 25));
        SchemaLoader.prepareServer();
        SchemaLoader.createKeyspace(KS, KeyspaceParams.simple(1),
            SchemaLoader.standardCFMD(KS, T, 0, AsciiType.instance, BytesType.instance).memtable(MemtableParams.get("skiplist")));
    }

    static long dirBytes()
    {
        long s = 0;
        for (File f : new File(DatabaseDescriptor.getCommitLogLocation()).tryList()) s += f.length();
        return s;
    }

    @Test
    public void sweep() throws Exception
    {
        ColumnFamilyStore cfs = Keyspace.open(KS).getColumnFamilyStore(T);
        AbstractCommitLogSegmentManager mgr = CommitLog.instance.segmentManager;
        int n = env("CLCAP_N", 300), sleep = env("CLCAP_SLEEP_MS", 10);
        long cap = DatabaseDescriptor.getTotalCommitlogSpaceInMiB() << 20, peak = 0, peakDir = 0;
        String out = System.getenv().getOrDefault("CLCAP_OUT", "build/test/clcap.csv");
        try (PrintWriter w = new PrintWriter(new FileWriter(out, true)))
        {
            w.println("capMiB,phase,i,onDiskSize,activeSegments,dirBytes,memtableSwitches");
            for (int i = 0; i < n + 10; i++)
            {
                String phase = i < n ? "write" : "settle";
                if (i < n)
                {
                    new RowUpdateBuilder(cfs.metadata(), 0, "k" + i).clustering("c")
                        .add("val", ByteBuffer.allocate(1 << 20)).build().apply();
                    if (sleep > 0) Thread.sleep(sleep);
                }
                else Thread.sleep(1000);
                long sz = mgr.onDiskSize(), d = dirBytes();
                peak = Math.max(peak, sz); peakDir = Math.max(peakDir, d);
                w.printf("%d,%s,%d,%d,%d,%d,%d%n", cap >> 20, phase, i, sz, mgr.getActiveSegments().size(), d,
                         cfs.metric.memtableSwitchCount.getCount());
            }
        }
        System.out.printf("SUMMARY capMiB=%d sleepMs=%d peakOnDisk=%d peakDir=%d final=%d switches=%d%n",
                          cap >> 20, sleep, peak, peakDir, mgr.onDiskSize(), cfs.metric.memtableSwitchCount.getCount());
    }
}
```
   If `File.tryList()` does not compile, use `new java.io.File(...).listFiles()`.
2. Compile once: `cd ~/cassandra-run1 && ant build-test`.
3. Run each arm in a fresh JVM, with the test's commit log, data and logs cleared between runs:
```bash
cd ~/cassandra-run1; mkdir -p ~/clcap-unit
for arm in "15 10" "25 10" "50 10" "100000 10" "25 0"; do set -- $arm
  rm -rf build/test/cassandra
  CLCAP_MIB=$1 CLCAP_SLEEP_MS=$2 CLCAP_N=300 CLCAP_OUT=$HOME/clcap-unit/cap$1-s$2.csv \
    ant testsome -Dtest.name=org.apache.cassandra.db.commitlog.CommitLogTotalSpaceCapTest -Dno-build-test=true
  grep -h SUMMARY build/test/output/TEST-org.apache.cassandra.db.commitlog.CommitLogTotalSpaceCapTest*.xml | tee -a ~/clcap-unit/summary.txt
  grep -h "Reason: COMMITLOG_DIRTY" build/test/logs/*.log 2>/dev/null | grep -c CLCapKS >> ~/clcap-unit/summary.txt
done
```
   If the output XML is named differently, find it with `ls build/test/output`.

   > **Amendment 2026-10-21 (stage-4 audit, R1–R2).** Run from `~/cassandra-cts`; before each arm also `rm -rf build/test/logs`; outputs go to `~/stage4-logs/cts/unit/`; the reason counts are `zgrep -rh 'Enqueuing flush of CLCapKS.t, Reason: COMMITLOG_DIRTY' build/test/logs | wc -l` and the same for `MEMTABLE_LIMIT` and for all reasons. The harness script `harness/commitlog_total_space-maybeFlushToReclaim-unused--autonomous/unit-run.sh` does exactly this loop.
4. Clean up as in B4.

**B2f. Predictions.** Units are 5 MiB segments; S = 5 MiB.

| Arm (MiB, sleep ms) | peak `onDiskSize` | final after settle | memtable switches |
|---|---|---|---|
| 15, 10 | ≤ 15 + 4S = 35 MiB | ≤ 15 + S = 20 MiB (floor 2S) | ≥ 15 (≈ 375 / ~15–20) |
| 25, 10 | ≤ 45 MiB | ≤ 30 MiB | ≥ 10 |
| 50, 10 | ≤ 70 MiB | ≤ 55 MiB | ≥ 5 |
| 100000, 10 (control) | ≈ 375–400 MiB, monotonically rising | same as peak | 0 |
| 25, 0 (overshoot probe) | > 45 MiB allowed, but < 150 MiB (still ≪ control) | ≤ 30 MiB | ≥ 5 |

Further predictions:
- `onDiskSize` is always a multiple of 5 MiB.
- `dirBytes` is within ±1 segment of `onDiskSize`.
- In the capped arms the per-sample trace is a sawtooth that jumps down by several segments after each switch.
- Peak and switch count are monotone in C: peak rises with C, switch count falls with C.

**B2g. Readings.**

| Observation | Meaning |
|---|---|
| Capped arms stay within the predicted peaks with a sawtooth; control rises to ~375 MiB with 0 switches | Claim confirmed at the unit tier: the line-249 check bounds the operand |
| Capped arms rise like the control (peak ≥ 0.8 × control) | Claim **refuted**: the check does not reclaim space |
| Switches > 0 but `onDiskSize` does not drop | Flush happens but segments are not discarded (step 6 broken). Claim refuted for disk |
| Capped peak bounded but well above C + 4S at sleep 10 | Cap works but is softer than predicted. Record the overshoot and compare it with the sleep-0 probe |
| Control has switches > 0 | Memtable-pressure flushes leaked in. The run is not conclusive: raise `memtable_cleanup_threshold` or lower N |
| Control does not reach > 3× the largest C | The workload did not exercise the limit. Not confirmed |

> **Amendment 2026-10-21 (stage-4 audit, R3; before any reading). Verdict labels, two missing rows, and "well above" made exact.** This applies to B2g and, with `dirBytes` read as `du -sb` and the 10-ms throttle read as the 20,000/s throttle, to B3g. The tier's verdict comes from the throttled capped arms; the probe arm affects only the Effect field.
> - Row 1 → **Confirmed — caps (soft)**. It needs (a) each throttled capped arm's peak within its B2f/B3f bound, (b) at least one `COMMITLOG_DIRTY` flush of the test table in every capped arm (the direct evidence that the line-249 true branch fired, R2), (c) drops in the trace, and (d) a control with 0 such flushes that rises to its predicted level.
> - Row 2 (peak ≥ 0.8 × control) → **Refuted — does not cap**.
> - Row 3 (flushes but no drop) → **Refuted for disk — does not cap**.
> - Row 4 ("well above" means: peak > C + 4S but < 0.8 × the control's peak, with (b) and (c) holding) → **Confirmed — caps (soft)**, with the overshoot bound recorded as a missed sub-prediction. The same holds for a miss of the "final after settle" bound, the "multiple of S" or "±1 segment" relations, or the monotone ordering, as long as (a)–(d) hold otherwise.
> - Rows 5 and 6 → **Not confirmed (invalid run)**.
> - New row: **`onDiskSize` (the counter) stays bounded but `dirBytes` / `du` (the real bytes) follows the control** (peak ≥ 0.8 × the control's) → **Refuted for disk — the cap holds only on the counter**.
> - New row: **capped peaks bounded, but 0 `COMMITLOG_DIRTY` flushes of the test table** → **Not confirmed**: something other than the line-249 check reclaimed the space, or the reason is not observable.
> - New row: **throttled capped arms Confirmed, but the unthrottled probe's peak ≥ 0.8 × the control's** → **Confirmed** for the throttled rate, with Effect **caps only on some paths (bypass)**: a fast enough writer outruns the forced flush. A probe above its own bound but below 0.8 × control is a missed sub-prediction only.

**B2h. Controls.**
- Control arm C = 100000 with an identical workload. This shows the workload itself grows the log and that nothing else reclaims it.
- `memtable_cleanup_threshold = 0.99` and the 0 switch count in the control rule out memtable-limit flushes.
- Non-durable system keyspaces keep other writers out of the commit log.
- A fresh JVM per arm, with the commit log deleted, means no replayed segments.
- `dirBytes` checks that the counter matches the files on disk.

### B3. Cluster tier

**B3a. Environment and build.**
- One node, run from `~/cassandra-run1`, which is already built. `ant build-test` includes `stress-build` (`build.xml:1017,577`), so `tools/bin/cassandra-stress` is available.
- All node state lives under `RUN=/tmp/clcap`. First check that `df -T /tmp` shows a local filesystem (not nfs or ceph) with ≥ 20 GiB free. If it does not, choose another local mount and set `RUN` to it.
- Check that ports 7000, 7199 and 9042 are free: `ss -ltn | egrep ':(7000|7199|9042)\b'` must print nothing.
- Configuration, per arm:
```bash
RUN=/tmp/clcap; ARM=$1   # 256 | 1024 | 16384
rm -rf $RUN/node; mkdir -p $RUN/node/{data,commitlog,hints,saved_caches,cdc_raw,logs}
cp -r ~/cassandra-run1/conf $RUN/node/conf
Y=$RUN/node/conf/cassandra.yaml
sed -i 's/^memtable_allocation_type:.*/memtable_allocation_type: offheap_objects/' $Y
grep -q '^commitlog_segment_size: 32MiB' $Y   # keep default 32 MiB segments
cat >> $Y <<EOF
data_file_directories:
    - $RUN/node/data
commitlog_directory: $RUN/node/commitlog
hints_directory: $RUN/node/hints
saved_caches_directory: $RUN/node/saved_caches
cdc_raw_directory: $RUN/node/cdc_raw
commitlog_total_space: ${ARM}MiB
memtable_heap_space: 4096MiB
memtable_offheap_space: 8192MiB
memtable_cleanup_threshold: 0.9
EOF
```
  All appended keys are commented out in the stock yaml (`conf/cassandra.yaml:97,395,408,431,611,797,799,812,883`), so there are no duplicate keys. Before starting, check that `grep -c '^commitlog_total_space' $Y` prints 1.
- JVM: `export MAX_HEAP_SIZE=16G` (G1 is the default in `conf/jvm11-server.options:63`; do not set `HEAP_NEWSIZE`), `export CASSANDRA_CONF=$RUN/node/conf CASSANDRA_LOG_DIR=$RUN/node/logs`.

> **Amendment 2026-10-21 (stage-4 audit, R4).** The run uses its own clone `~/cassandra-cts` (`cassandra-5.0.9`, `ant build-test` done) wherever this tier says `~/cassandra-run1`, and keeps its outputs in `~/stage4-logs/cts/cluster/<arm>/` instead of `~/clcap-cluster/`. On `pc06`, `/tmp` is on `/dev/sda3` (local ext3, 55 GB free), so `RUN=/tmp/clcap` stands. The shell that starts the node runs `ulimit -n 100000` first, because the soft limit is 1024. Step 2's wait also needs `nodetool statusbinary` to print `running`, and fails at once if the daemon dies. In steps 7 and B4, check for a leftover node with `ps -eo pid,cmd | grep '[j]ava.*CassandraDaemon'`, not `pgrep -f`, which matches an ssh shell's own command line. The unthrottled probe arm is labelled `256p`.

**B3b. Knobs.** `commitlog_total_space`:
- **256MiB** (8 segments)
- **1024MiB** (32 segments)
- **16384MiB** (control, far above the ~3.2 GiB written)

Restart for each value, wiping the node directory between arms. Everything else is held fixed. The memtable limits are set high so that `MEMTABLE_LIMIT` flushes do not occur before ~7.3 GiB off-heap or ~3.6 GiB on-heap.

There is one extra overshoot-probe arm: 256MiB with an unthrottled workload.

**B3c. Workload.**
```bash
~/cassandra-run1/tools/bin/cassandra-stress write n=3000000 no-warmup cl=ONE \
  -col n=FIXED\(1\) size=FIXED\(1024\) -schema "replication(factor=1)" \
  -rate threads=32 throttle=20000/s -node 127.0.0.1 -log file=$RUN/stress-$ARM.log
```
- Arithmetic: 3,000,000 rows × ~1.1 KiB of commit-log entry (1 KiB value + key + overhead) ≈ 3.2 GiB of commit-log volume. That is 12.5× the 256 MiB arm, 3× the 1024 MiB arm and 0.2× the control.
- At 20,000 rows/s it runs about 150 s at about 22 MiB/s of commit log.
- Memtable: ~3.1 GiB off-heap and ≲1.5 GiB on-heap, so it stays under the 0.9 thresholds. That keeps the control free of flushes.
- Overshoot probe: the same command with `-rate threads=128` and no throttle.

**B3d. Observables and instruments.**
- `du -sb $RUN/node/commitlog` (apparent bytes) and `du -sk` (allocated blocks), sampled every 1 s, plus the file count `ls $RUN/node/commitlog | wc -l`. These are the actual disk resource.
- Optional, every 10 s: JMX gauge `TotalCommitLogSize` via `~/cassandra-run1/bin/nodetool sjk mx -b org.apache.cassandra.metrics:type=CommitLog,name=TotalCommitLogSize -mg -f Value`. If the sjk syntax fails, skip it and rely on `du`.
- Flush events: `grep "Enqueuing flush of keyspace1.standard1, Reason:" $RUN/node/logs/system.log`, counted by reason (`COMMITLOG_DIRTY` vs `MEMTABLE_LIMIT`, etc.).
- `du -sb $RUN/node/data` gives context: the forced flushes move bytes to the data directory.
- Not directly observable: the value of `unused` at each check, and flush latency. The flush log timestamps against the `du` trace stand in for flush latency.

**B3e. Procedure.** Run once per arm (256, 1024, 16384, then the 256 overshoot probe):
1. Write the configuration as in B3a.
2. Start the node: `~/cassandra-run1/bin/cassandra -p $RUN/node/cassandra.pid > $RUN/node/logs/stdout.log 2>&1`. Wait until `~/cassandra-run1/bin/nodetool status` shows `UN` (poll every 5 s, 180 s timeout).
3. Start the sampler:
   `( while :; do echo "$(date +%s),$(du -sb $RUN/node/commitlog|cut -f1),$(du -sk $RUN/node/commitlog|cut -f1),$(ls $RUN/node/commitlog|wc -l)"; sleep 1; done ) > $RUN/du-$ARM.csv & echo $! > $RUN/sampler.pid`
4. Run the workload from B3c.
5. Keep sampling for 60 s after stress ends, then `kill $(cat $RUN/sampler.pid)`.
6. `grep -c "keyspace1.standard1, Reason: COMMITLOG_DIRTY" $RUN/node/logs/system.log`, and do the same for `MEMTABLE_LIMIT`. Save both counts.
7. Stop the node: `kill $(cat $RUN/node/cassandra.pid)`. Wait until `pgrep -u $USER -f CassandraDaemon` is empty (force with `kill -9` after 60 s).
8. Copy the CSVs and logs to `~/clcap-cluster/` and then `rm -rf $RUN/node`.

**B3f. Predictions.** S = 32 MiB; apparent bytes via `du -sb`.

| Arm | peak commit-log dir | level after settle | COMMITLOG_DIRTY flushes (standard1) | MEMTABLE_LIMIT flushes |
|---|---|---|---|---|
| 256MiB | ≤ 256 + 4S = 384 MiB | ≤ 256 + S = 288 MiB | ≥ 8 (≈ 3.2 GiB / 256 MiB ≈ 12) | 0 |
| 1024MiB | ≤ 1024 + 4S = 1152 MiB | ≤ 1056 MiB | ≥ 2 (≈ 3) | 0 |
| 16384MiB (control) | ≥ 2.8 GiB, rising roughly linearly with rows written | ≈ peak | 0 | 0 |
| 256MiB unthrottled probe | > 384 MiB allowed but < 1 GiB (≤ 4 × C) | ≤ 288 MiB | ≥ 8 | 0 |

Further predictions:
- The peak is ordered 256 < 1024 < control.
- The capped arms show a sawtooth whose drops line up with `COMMITLOG_DIRTY` log lines.
- `du -sb` ≈ 32 MiB × file count.

**B3g. Readings.**

| Observation | Meaning |
|---|---|
| Capped arms within predicted peaks, sawtooth aligned with COMMITLOG_DIRTY flushes; control grows to ≥ 2.8 GiB with no flushes | Claim confirmed: `commitlog_total_space` caps real commit-log disk use (soft) |
| A capped arm grows like the control (peak ≥ 0.8 × control) or has no COMMITLOG_DIRTY flushes | Claim **refuted** |
| COMMITLOG_DIRTY flushes logged but `du` does not drop | Flush happens but segments are not freed. Refuted for disk |
| Bounded, but peak well above C + 4S at the throttled rate | Cap holds but overshoot is larger than predicted. Report the overshoot against write rate, using the probe |
| Control shows MEMTABLE_LIMIT flushes or does not exceed 1.5 GiB | A different cap bound the control, or the workload was too small. Not conclusive: raise memtable limits or n |
| Node fails to start or `commitlog_total_space` is missing from the startup config log line | Knob not applied. Rerun |

> **Amendment 2026-10-21 (stage-4 audit, R3).** The labels, the exact meaning of "well above", and the three added rows of the R3 note under B2g apply here too. Read `du -sb` for `dirBytes`, the 20,000/s throttle for the 10-ms one, `keyspace1.standard1` for the test table, and 0.8 × the control's peak `du -sb`. Rows 5 and 6 here (`MEMTABLE_LIMIT` in the control, or the knob not applied) → **Not confirmed (invalid run)**.

**B3h. Controls.**
- The 16384 MiB control with the identical workload is the positive control for the workload: it shows the workload moves commit-log usage when nothing else binds.
- Memtable limits are kept far above the data volume, and the `MEMTABLE_LIMIT` count is checked, to rule out memtable-pressure flushes.
- Single node, RF=1, no hints, no CDC, no archiving. Every commit-log byte comes from this node's own writes.
- Directories are wiped between arms, so there is no replay.
- The startup log line printing the config (`Node configuration:[...commitlog_total_space=...]`) confirms the value used.

**B4. Risks and cleanup.**
- **Disk.** The unit tier writes ≤ ~0.5 GiB under `~/cassandra-run1/build/test`. The cluster tier writes ≤ ~4 GiB of commit log plus ≤ ~4 GiB of data per arm under `$RUN` on a local disk that was checked beforehand. Nothing goes on shared or NFS storage, and nothing is built or written in the repository's `cassandra/cassandra-5.0.9/`.
- **Processes.** Unit tests run in an Ant-forked JVM that exits by itself. After the cluster arms, run `pgrep -u $USER -f 'CassandraDaemon|cassandra-stress'` and kill anything left. Kill the sampler loop by its pid.
- **Cleanup.**
  - `rm -rf /tmp/clcap ~/cassandra-run1/build/test/cassandra`
  - Remove `~/cassandra-run1/test/unit/org/apache/cassandra/db/commitlog/CommitLogTotalSpaceCapTest.java` (and its class under `build/test/classes`), or `git -C ~/cassandra-run1 status` to confirm only this file was added.
  - Keep `~/clcap-unit` and `~/clcap-cluster` as the result artefacts.
- **Ports.** The cluster tier uses the default ports. Do not run it while another Cassandra on the host owns 7000, 7199 or 9042.

## C. Sources read

- /proj/misconfiguration-PG0/git-repos/Misconfiguration/cassandra/if-check-exp/stage3-ai-deep-read/playbook-autonomous.md
- /proj/misconfiguration-PG0/git-repos/Misconfiguration/cassandra/if-check-exp/stage3-ai-deep-read/_TEMPLATE-autonomous.md
- src/java/org/apache/cassandra/db/commitlog/AbstractCommitLogSegmentManager.java
- src/java/org/apache/cassandra/db/commitlog/CommitLogSegmentManagerStandard.java
- src/java/org/apache/cassandra/db/commitlog/CommitLogSegment.java (excerpts: 420-440, 611-620, 648)
- src/java/org/apache/cassandra/db/commitlog/MemoryMappedSegment.java (50-106)
- src/java/org/apache/cassandra/db/commitlog/CommitLog.java (excerpts: 79-148, 353-369, 435-442)
- src/java/org/apache/cassandra/db/commitlog/CommitLogSegmentManagerCDC.java (grep for addSize only)
- src/java/org/apache/cassandra/db/commitlog/{CompressedSegment,EncryptedSegment,FileDirectSegment,DirectIOSegment}.java (grep for addSize only)
- src/java/org/apache/cassandra/metrics/CommitLogMetrics.java (70-80)
- src/java/org/apache/cassandra/config/Config.java (185-190, 385-401)
- src/java/org/apache/cassandra/config/DatabaseDescriptor.java (245-262, 584-594, 655-675, 759-775, 891-901, 1147-1162, 1486-1535, 2875-2910, 3829-3832, 4055-4058, 4124-4127)
- src/java/org/apache/cassandra/db/ColumnFamilyStore.java (1055, 1084-1100, 1152)
- src/java/org/apache/cassandra/db/memtable/AbstractAllocatorMemtable.java (grep: 59, 81-83, 289-295)
- src/java/org/apache/cassandra/tools/nodetool/Sjk.java (grep)
- conf/cassandra.yaml (relevant keys), conf/jvm11-server.options (GC line), conf/cassandra-env.sh (heap comments), bin/cassandra (env vars)
- test/conf/cassandra.yaml
- test/unit/org/apache/cassandra/SchemaLoader.java (80-84), test/unit/org/apache/cassandra/ServerTestUtils.java (66-78)
- test/unit/org/apache/cassandra/db/commitlog/CommitLogTest.java (155-190, 365-434), CommitLogSegmentBackpressureTest.java (header)
- build.xml (test, testsome, build-test, stress-build targets)
- doc/modules/cassandra/pages/architecture/storage-engine.adoc:78; doc/modules/cassandra/pages/managing/configuration/configuration.adoc:106 (grep)
- https://issues.apache.org/jira/browse/CASSANDRA-10013, https://issues.apache.org/jira/browse/CASSANDRA-10199 (cited from source comment; not opened)

## D. Stage-4 feedback

**2026-10-21, run 1: unit Confirmed, cluster Confirmed, caps (soft).** No run 2. Results: [`../../stage4-runtime-verification/results/commitlog_total_space-maybeFlushToReclaim-unused--autonomous.md`](../../stage4-runtime-verification/results/commitlog_total_space-maybeFlushToReclaim-unused--autonomous.md). Node `pc06`, clone `~/cassandra-cts`. The design was frozen at sha256 `6a58e10f…` after audit amendments R1–R4 (dated notes above). The case file is not committed.

- **Unit (B2g row 4, as amended R3).** Peak `onDiskSize` was 30 / 40 / 75 MiB at C = 15 / 25 / 50, against 380 MiB uncapped. Final levels were 15–20 MiB. There were 38 / 18 / 8 `COMMITLOG_DIRTY` flushes, and none in the control. `dirBytes` stayed within one segment of the counter. The unthrottled probe peaked at 100 MiB at C = 25. One sub-prediction was missed: the C = 50 peak was 75 MiB against a 70 MiB bound.
- **Cluster (B3g row 4).** Peak `du -sb` was 352 / 1,184 MiB at C = 256 / 1024, against 3,168 MiB uncapped. After settling it was 256 / 192 MiB. There were 13 / 3 `COMMITLOG_DIRTY` flushes of `standard1`, each followed by segment deletions and a fall of `du`. The control had none, and no arm had a `MEMTABLE_LIMIT` flush. Missed sub-predictions:
  - The C = 1024 peak was one segment over the bound.
  - The unthrottled probe at about 107,000 writes/s peaked at **2,048 MiB = 8 × C** (0.65 × the control), against a bound of < 1 GiB. It rose for the whole 36-s burst although a forced flush was requested every ~1.8 s, and came back below C only after the writes stopped.
- **For stage 3.**
  - (1) A longer unthrottled probe would show whether a fast writer outruns the cap without limit. That is the open question this run leaves.
  - (2) Include the default (8192 MiB here) with a workload above it (R5).
  - (3) `ant testsome` forks a 1 GiB test JVM, not 4 GiB (R1).
  - (4) In the runbook, `zgrep -r` did not recurse on the node, and the test log sits in a `<testtag>` subdirectory (harness fix H1; the observable is unchanged).
