# commitlog_total_space — verification solution  <!-- file: cases/commitlog_total_space-maybeFlushToReclaim-unused-2--autonomous.md -->

| Field | Value |
|---|---|
| Entry pointer | `src/java/org/apache/cassandra/db/commitlog/AbstractCommitLogSegmentManager.java:259` |
| Pinned source | `cassandra-5.0.9` |
| Session / date | Claude Opus 5.5 (`claude-opus-5-5`), Claude Code CLI (version not exposed to the agent), autonomous stage-3, 2026-10-21 |
| Estimate | `positive`, but as a **soft** cap. Once the tracked commit-log size passes `commitlog_total_space`, the allocator thread forces flushes of the tables that are dirty in the oldest segments. The segments are deleted when those flushes finish, so on-disk commit-log size comes back to at most the limit. It can overshoot by the segments written during one flush latency, because writers are never blocked on this limit. |
| Ground | — |

Naming note: the stem `commitlog_total_space-maybeFlushToReclaim-unused` already exists in `cases/`. I did not read that file (blindness rule). Per §6.1 "Collisions", this newcomer takes the `-2` postfix.

## A. Constraint trace

**A1. The constraint.**
- Name: `commitlog_total_space`, a configuration entry (cassandra.yaml).
- First declared: `src/java/org/apache/cassandra/config/Config.java:389-390` (`public DataStorageSpec.IntMebibytesBound commitlog_total_space;`, `@Replaces(oldName = "commitlog_total_space_in_mb")`).
- Unit: MiB (`IntMebibytesBound`). You can give it in any data-storage unit ≥ MiB, e.g. `256MiB`.
- Default: `null` in Config. `DatabaseDescriptor.applySimpleConfig` fills it in at `src/java/org/apache/cassandra/config/DatabaseDescriptor.java:664-675`, as `min(8192 MiB, 1/4 × total space of the commitlog_directory filesystem)` via `calculateDefaultSpaceInMiB` (`DatabaseDescriptor.java:1147-1162`). That method logs a WARN "Small commitlog volume detected" when the 1/4 value wins.
- Shipped yaml: commented out (`conf/cassandra.yaml:874-883`, `# commitlog_total_space: 8192MiB`).
- How to set it: the yaml key only. There is no JMX/nodetool setter and no `-D` property; `grep` finds no setter in `src/java`.
- Read path: `DatabaseDescriptor.getTotalCommitlogSpaceInMiB()` (`DatabaseDescriptor.java:3829-3832`) reads `conf` on every call. A change therefore needs a restart in production. In a unit JVM you can mutate `DatabaseDescriptor.getRawConfig().commitlog_total_space` (`DatabaseDescriptor.java:385-388`) and the next check picks it up.
- Related inputs: `commitlog_segment_size` (`Config.java:396-397`, default 32MiB) is the granularity of both sides of the check. `commitlog_disk_access_mode` decides how a segment's size is accounted (see A3).

**A2. What it caps.**
- Resource: **disk**, i.e. the total size of commit-log segment files in `commitlog_directory`.
- Quantity compared: `AbstractCommitLogSegmentManager.size` (an `AtomicLong`, `AbstractCommitLogSegmentManager.java:103`), exposed as `onDiskSize()` (`:440-443`) and as the metric `org.apache.cassandra.metrics:type=CommitLog,name=TotalCommitLogSize` (`src/java/org/apache/cassandra/metrics/CommitLogMetrics.java`, gauge `totalCommitLogSize` → `segmentManager.onDiskSize()`).
- `unusedCapacity()` = `commitlog_total_space × 2^20 − size` (`:445-451`).
- At the target line 259, the limit-side operand is `unused` (that difference). The usage-side operand is `flushingSize`, the sum of `onDiskSize()` of the oldest segments selected so far.

**A3. Mechanism.**
1. **Size accounting.** Each segment adds its size to `size` through `manager.addSize(...)` (`:432-435`).
   - In mmap mode the full segment size is added when the segment is built (`MemoryMappedSegment.java:62-63`), and `onDiskSize()` is the segment size (`:105`). Mmap is the default for an uncompressed, unencrypted commit log: `legacy` resolves to `mmap` at `DatabaseDescriptor.java:1525-1527`, and the shipped yaml has `commitlog_disk_access_mode: legacy`, `conf/cassandra.yaml:678`.
   - Compressed, encrypted and direct segments add their size as they write.
   - On discard the size is subtracted (`CommitLogSegmentManagerStandard.discard`, `addSize(-segment.onDiskSize())`; `CommitLogSegment.discard` `CommitLogSegment.java:430-436`).
2. **Trigger.** The allocator thread `COMMIT-LOG-ALLOCATOR` (`:157-158`) runs `AllocatorRunnable.run` (`:166-238`). Each time it builds a spare segment (`availableSegment = createSegment()`, `:189`) and writers are not waiting for another one, it calls `maybeFlushToReclaim()` (`:200`). Then it sleeps until a writer consumes the spare (`managerThreadWaitCondition`, `:108`, `:225`). **The check therefore runs once per segment switch, not per write.**
3. **Primary check, `:248-249`.** `unused = unusedCapacity(); if (unused < 0)`: is the tracked size above the limit? The tracked size includes the spare segment just built and the segment currently being written.
4. **Target check, `:253-261`.** Walk `activeSegments` from oldest to newest, stopping before `allocatingFrom` (`:255-256`). Add each segment's `onDiskSize()` to `flushingSize` and add the segment to `segmentsToRecycle`. Stop once `flushingSize + unused >= 0` (`:259-260`), i.e. once the selected segments are enough to bring the size back to ≤ limit. If the walk reaches `allocatingFrom` first, it flushes every older segment and stops.
5. **Action.** `flushDataFrom(segmentsToRecycle, emptyList, false)` (`:262`, body `:458-503`). For each table dirty in those segments it calls `cfs.forceFlush(maxCommitLogPosition)`:
   - `ColumnFamilyStore.java:1084-1092`: if the current memtable may hold data before that position, switch it with `FlushReason.COMMITLOG_DIRTY`. That logs `Enqueuing flush of <ks>.<tbl>, Reason: COMMITLOG_DIRTY` at `ColumnFamilyStore.java:1055`.
   - Otherwise it waits for flushes already in progress.
   - The call is **asynchronous**: the returned future is ignored.
6. **Reclaim.** When a memtable flush completes, `CommitLog.discardCompletedSegments` (`CommitLog.java:353-383`) marks the table clean in each segment. Segments that become unused (full, `isStillAllocating()==false`, and no dirty table; `CommitLogSegment.java:611-619`) are passed to `archiveAndDiscard` (`AbstractCommitLogSegmentManager.java:406-414`), which deletes the file and subtracts its size.
7. **Outcome when the limit is reached.** Writes are **not** blocked, refused or slowed by this limit; the only effect is forced flushes. Usage below the limit gives no action.

Bypass and overshoot paths:
- (a) Writers keep filling new segments while the forced flushes run. Overshoot ≈ write rate × (flush latency + discard delay), in whole segments. Nothing bounds it if flushing stalls (slow or full data disk, failed flush, flush writers saturated).
- (b) A table whose memtable is not flushed (e.g. a flush that errors) pins its segments indefinitely.
- (c) If an `archive_command` (commitlog_archiving.properties) fails, `discard(segment, false)` leaves the file on disk but still subtracts its size (`CommitLogSegmentManagerStandard.discard`; `:413`). Tracked size and real disk then diverge, and real disk grows past the limit.
- (d) Segments found at startup and replayed are deleted without ever being counted (`:421-426`).
- (e) A limit smaller than about 2 segments can never be met, because `allocatingFrom` and the spare are always counted but never selected. Each switch then flushes everything older.
- (f) No validation ties the limit to `commitlog_segment_size`.

**A4. Other consumers.**
- Disk of the same volume: sstables produced by the forced flushes (data directories, usually a different path), hints, saved caches, CDC (`cdc_raw` hard links, under the separate `cdc_total_space`), and archive copies made by `archive_command`.
- Memory: compressed and encrypted segment buffers come from `SimpleCachedBufferPool` (`commitlog_max_compression_buffers_in_pool`); mmap segments map 32MiB each into the address space (page cache).
- Memtables are bounded independently by `memtable_heap_space` / `memtable_offheap_space` / `memtable_cleanup_threshold`, which also trigger flushes and so also shrink the commit log. That is a confound for the tests below.

**A5. Evidence beyond the source.**
- `conf/cassandra.yaml:874-883` and `doc/modules/cassandra/pages/architecture/storage-engine.adoc:78-84`: "If space gets above this value, Cassandra will flush every dirty table in the oldest segment and remove it." This matches the mechanism, but the code flushes enough oldest segments to get back under the limit, not just one.
- CASSANDRA-10013 and CASSANDRA-10199 (cited at `DatabaseDescriptor.java:667`, https://issues.apache.org/jira/browse/CASSANDRA-10013, https://issues.apache.org/jira/browse/CASSANDRA-10199) introduced the 1/4-of-volume default.
- No unit test in `test/unit` exercises `maybeFlushToReclaim` or `commitlog_total_space`. Only YAML parsing tests do (`test/unit/org/apache/cassandra/config/ParseAndConvertUnitsTest.java`, `LoadOldYAMLBackwardCompatibilityTest.java`).
- `test/unit/org/apache/cassandra/db/commitlog/CommitLogSegmentBackpressureTest.java` is the pattern followed for unit-tier setup.

## B. Verification solution

**B1. Claim under test.**
- Writes alone push the tracked commit-log size (`onDiskSize()` / `TotalCommitLogSize`) and the real file size in `commitlog_directory` above `commitlog_total_space` = T. The node then issues `COMMITLOG_DIRTY` flushes and deletes the oldest segments.
- Peak usage is T plus a small overshoot that does not depend on T (a few segments).
- After writes stop and flushes finish, usage settles at ≤ T.
- With T large (the control), the same workload makes usage grow to the full volume written, with no `COMMITLOG_DIRTY` flush.
- The claim is **wrong** if peak or settled usage does not follow T, or if it grows unbounded under a sustained workload that flushes keep up with.

### B2. Unit tier

**B2a. Environment and build.**
- JDK 11.0.32.1, Ant 1.10.12.
- Copy the tree to local disk. Never build in the shared clone.
  `mkdir -p /tmp/clcap && <repo>/cassandra/if-check-exp/stage4-runtime-verification/copy-source.sh /tmp/clcap/cassandra`
- Build in the copy: `cd /tmp/clcap/cassandra && ant jar build-test` (`build-test`, `build.xml:1017`).
- New test file, in the copy only: `/tmp/clcap/cassandra/test/unit/org/apache/cassandra/db/commitlog/CommitLogTotalSpaceTest.java`.
- The test conf (`test/conf/cassandra.yaml:8-12`) sets periodic sync, `commitlog_disk_access_mode: legacy` (→ mmap on 64-bit), and `commitlog_directory: build/test/cassandra/commitlog`. That directory is inside the copy, on local disk.
- Test JVM uses the default heap from build.xml. Pass the knob with `-Dtest.jvm.args=...` (`build.xml:94`, `:1192`).

> **Stage-4 audit amendment (2026-10-21, R1: clone, paths, heap).** The run uses a fresh `git clone --branch cassandra-5.0.9` at
> `pc06:~/cassandra-cl2` (`b5f2a54210`), built with `ant build-test`, instead of the rsync copy under `/tmp/clcap`. The stage-4
> safety rule asks for a clone per run. The test file is copied into that clone, and the outputs go to
> `pc06:~/stage4-logs/cl2/unit/<arm>/`. `ant testsome` forks the test JVM with `maxmemory="1024m"` (`build.xml:1152`), so
> the default `memtable_heap_space` there is 256 MiB. The 16 MiB workload stays far below it, so B2c's memtable argument holds
> unchanged. `-Dtest.jvm.args` reaches the forked JVM (`build.xml:1192`, inside the `testsome` macro), so B2e step 2 passes
> the knob as written. The test also takes `-Dclcap.out=<arm dir>/cap.csv` (R2) and, for B2i, `-Dclcap.mode` and
> `-Dclcap.nobreak` (R5).

**B2b. Knobs.**
- `T` (MiB) is set in the test with `DatabaseDescriptor.getRawConfig().commitlog_total_space = new DataStorageSpec.IntMebibytesBound(T)`, from system property `clcap.totalMiB`.
- Values: **3, 4, 8** (binding; 3 is the smallest value ≥ 2 segments + 1, see A3(e)) and **1024** (control, never reached).
- Segment size is fixed at 1 MiB with `DatabaseDescriptor.setCommitLogSegmentSize(1)`, so T is 3, 4 and 8 segments.
- Throttle: `clcap.sleepMs` = **20** (main run) and **0** (stress run, to expose overshoot).

**B2c. Workload.**
- One table `CLCap.Standard1` (`SchemaLoader.standardCFMD`), auto-compaction disabled.
- 256 mutations, each to a distinct key, each with a 64 KiB random `val` blob: about 16.1 MiB of commit-log data, i.e. at least 16 segment switches at 1 MiB/segment. That is ≥ 2× the largest binding T (8 MiB) and well under the control (1024 MiB).
- Mutations go through `CommitLog.instance.add` by `mutation.apply()`, which also fills the memtable so flushes have real data.
- Memtable footprint is about 16 MiB on heap. That is far below the default `memtable_heap_space` = heap/4, so memtable-pressure flushes do not occur (checked in B2h).

**B2d. Observables and instruments.**
- The check's usage-side operand is `clsm.onDiskSize()` (`clsm = CommitLog.instance.segmentManager`). A daemon sampler thread reads it every 1 ms and records the max and a time series (CSV: ms, onDiskSize, activeSegments.size()).
- Settled size: `onDiskSize()` after the writer ends and `Util.spinAssert`-style waits up to 10 s, until `cfs.metric.pendingFlushes` is 0 and the size is unchanged for 500 ms.
- Real files: sum of `File.length()` over `*.log` in `DatabaseDescriptor.getCommitLogLocation()`, sampled at the same points.
- Flush count: `cfs.metric.memtableSwitchCount.getCount()` before and after, plus `grep -c "Reason: COMMITLOG_DIRTY" build/test/logs/...` (the unit test log under `build/test/logs/`).
- Not directly observable: the `unused` value at each check instant (it is computed and discarded). It is inferred as `T·2^20 − onDiskSize`. If needed, enable TRACE for `org.apache.cassandra.db.commitlog.AbstractCommitLogSegmentManager` (`:449`) in `test/conf/logback-test.xml` of the copy; that logs each `unusedCapacity()` evaluation.

> **Stage-4 audit amendment (2026-10-21, R2: flush-reason count and outputs).**
> - The `COMMITLOG_DIRTY` count of `CLCap.Standard1` is **required**. It is the direct evidence that the true branch at `:249` fired and that the segments chosen at `:259` were flushed.
> - The test log is `build/test/logs/<testtag>/TEST-org.apache.cassandra.db.commitlog.CommitLogTotalSpaceTest.log`. It is written at DEBUG, rolls to `.log.N.gz` at 20 MB (`test/conf/logback-test.xml`), and accumulates across runs. So before each arm, clear `build/test/logs` and `build/test/cassandra`, and after it, keep the arm's whole log tree. Count with `find <tree> -type f | xargs zcat -f | grep -c 'Enqueuing flush of CLCap.Standard1, Reason: COMMITLOG_DIRTY'` (`zgrep -r` does not recurse on these nodes), and the same for `MEMTABLE_LIMIT` and `MEMTABLE_PERIOD_EXPIRED`.
> - The 1-ms sampler writes `tMs,phase,onDiskSize,activeSegments,dirBytes,memtableSwitches` to `<clcap.out>`. The SUMMARY line goes to `<clcap.out>.summary` as well as stdout, because stdout reaches the log through the logger in fragments.
> - With B2i's Byteman trace on, the `unused` value at each over-limit check **is** observed (`SELECT` lines). For the single-table arms it is still only needed as a cross-check.

**B2e. Procedure.**
1. Write the test. Its skeleton follows `CommitLogSegmentBackpressureTest`:
   ```java
   @Test public void totalSpace() throws Throwable {
     DatabaseDescriptor.daemonInitialization();
     DatabaseDescriptor.setCommitLogSegmentSize(1);
     DatabaseDescriptor.getRawConfig().commitlog_total_space =
         new DataStorageSpec.IntMebibytesBound(Integer.getInteger("clcap.totalMiB", 4));
     DatabaseDescriptor.initializeCommitLogDiskAccessMode();
     SchemaLoader.prepareServer();
     SchemaLoader.createKeyspace("CLCap", KeyspaceParams.simple(1),
         SchemaLoader.standardCFMD("CLCap", "Standard1", 0, AsciiType.instance, BytesType.instance));
     CompactionManager.instance.disableAutoCompaction();
     ColumnFamilyStore cfs = Keyspace.open("CLCap").getColumnFamilyStore("Standard1");
     Util.flush(Keyspace.open("system")); Util.flush(Keyspace.open("system_schema"));
     CommitLog.instance.forceRecycleAllSegments();          // start from 1 active segment
     AbstractCommitLogSegmentManager clsm = CommitLog.instance.segmentManager;
     long switches0 = cfs.metric.memtableSwitchCount.getCount();
     // start sampler thread recording max(clsm.onDiskSize()) and a CSV every 1 ms
     int sleep = Integer.getInteger("clcap.sleepMs", 20);
     byte[] v = new byte[64 * 1024];
     for (int i = 0; i < 256; i++) {
       new Random(i).nextBytes(v);
       new RowUpdateBuilder(cfs.metadata(), 0, "k" + i).clustering("c")
           .add("val", ByteBuffer.wrap(v)).build().apply();
       if (sleep > 0) Thread.sleep(sleep);
     }
     // wait for pendingFlushes==0 and stable size, then print:
     // T, peak onDiskSize, settled onDiskSize, files bytes, switches-switches0
   }
   ```
2. Run each value in its own JVM, so state never leaks between runs:
   `for T in 3 4 8 1024; do ant testsome -Dtest.name=org.apache.cassandra.db.commitlog.CommitLogTotalSpaceTest -Dtest.jvm.args="-Dclcap.totalMiB=$T -Dclcap.sleepMs=20"; cp build/test/output/TEST-*CommitLogTotalSpaceTest*.xml /tmp/clcap/unit-T$T.xml; done`
3. Repeat T=4 and T=1024 with `-Dclcap.sleepMs=0`.
4. Collect the printed lines from the saved XML (system-out) and the `COMMITLOG_DIRTY` counts from the test log.

> **Stage-4 audit amendment (2026-10-21, R2/R5: arms and commands).** Run by `harness/<this stem>/unit-run.sh`. Each arm is one
> `ant testsome -Dtest.name=org.apache.cassandra.db.commitlog.CommitLogTotalSpaceTest -Dno-build-test=true
> -Dtest.jvm.args="-Dclcap.totalMiB=<T> -Dclcap.sleepMs=<ms> -Dclcap.mode=<single|M> -Dclcap.nobreak=<false|true> -Dclcap.out=<arm>/cap.csv"`,
> in a fresh JVM with `build/test/cassandra` and `build/test/logs` cleared first. The arms are, in order: `3:20`, `4:20`, `8:20`, `1024:20`
> (step 2); `4:0`, `1024:0` (step 3); then B2i's `M` (T = 8, 20 ms) and `M-nobreak` (T = 8, 20 ms). The arm directory keeps the JUnit
> XML, `ant.log`, the CSV, the summary, the Byteman trace and the raw test-log tree.

**B2f. Predictions (S = 1 MiB segment, 20 ms throttle).**

| T | peak `onDiskSize` | settled `onDiskSize` | `COMMITLOG_DIRTY` flushes on Standard1 |
|---|---|---|---|
| 3 MiB | ≤ 5 MiB (T + 2S) | ≤ 3 MiB | ≥ 4 |
| 4 MiB | ≤ 6 MiB | ≤ 4 MiB | ≥ 4 |
| 8 MiB | ≤ 10 MiB | ≤ 8 MiB | ≥ 2 |
| 1024 MiB (control) | ≈ 17–18 MiB: grows monotonically to bytes written + 1–2 spare segments | same as peak, no decrease | 0 |

- `peak − T` is roughly the same across 3, 4 and 8 (overshoot independent of T).
- File-length sum matches `onDiskSize` within ±1 segment (mmap files are pre-sized to S).
- Unthrottled (sleep 0): peak ≤ T + 4S for T=4, and settled ≤ T still holds.

**B2g. Readings.**

| Observation | Meaning |
|---|---|
| Peak ≈ T + small constant for T = 3, 4, 8; settled ≤ T; COMMITLOG_DIRTY flushes > 0; control grows to ≈ 17 MiB with 0 such flushes | Claim confirmed: the check bounds the operand at T plus a flush-latency overshoot |
| Peak or settled size the same for T = 3, 4, 8 as for the control (≈ 17 MiB), or no COMMITLOG_DIRTY flush at T = 3 | Claim wrong: the limit does not govern the operand |
| COMMITLOG_DIRTY flushes occur but settled size > T + S | Flushes do not free segments (pinning, e.g. another dirty table): mechanism differs from A3 step 6 |
| Peak − T grows with T, or overshoot > 4S with throttle | Overshoot not bounded as traced; report the series |
| Control never exceeds 8 MiB | Workload did not reach the limit: not confirmed, check write path / segment size |
| Flushes with another reason (MEMTABLE_LIMIT etc.) present | Confounded, see B2h; rerun with a larger heap |

> **Stage-4 audit amendment (2026-10-21, R3: a verdict per row, exact thresholds, two added rows).** This is made before any
> reading. The rows above gave a meaning but no verdict, and "≈" and "the same as" had no threshold. Definitions (S = 1 MiB, throttled
> arms unless stated):
> - "**Peak follows T**": the binding peaks are non-decreasing in T (3 ≤ 4 ≤ 8), and each is < 0.8 × the control's peak.
> - Rows are checked in this order. The first that applies is the verdict for the unit tier.
>
> | # | Row (as filed, made exact) | Verdict · Effect |
> |---|---|---|
> | 5 | The control's peak is ≤ 8 MiB | **Invalid** (the limit was not reached) |
> | 6 | Any `MEMTABLE_LIMIT` / `MEMTABLE_PERIOD_EXPIRED` flush of `CLCap.Standard1` | **Invalid** (confounded; rerun as B2h says) |
> | 7 (added) | In a binding arm, the file-length sum peaks > 2S above the `onDiskSize` peak, or settles > T + S while `onDiskSize` ≤ T | **Refuted for disk** · does not cap (only the counter is capped) |
> | 2 | Any binding peak ≥ 0.8 × the control's peak; or 0 `COMMITLOG_DIRTY` flushes at T = 3 together with a peak ≥ 0.8 × the control's | **Refuted** · does not cap |
> | 3 | `COMMITLOG_DIRTY` flushes occur, but settled `onDiskSize` > T + S in a binding arm | **Refuted** (B1 "settles at ≤ T" fails) · caps (soft) if the peak follows T, else does not cap |
> | 8 (added) | The peak follows T and settles ≤ T, but some binding arm has 0 `COMMITLOG_DIRTY` flushes of `Standard1` | **Not confirmed** (the cap's own action is not shown) · undetermined |
> | 1 | The peak follows T, every binding peak ≤ T + 2S, every binding arm settles ≤ T with ≥ 1 `COMMITLOG_DIRTY` flush, and the control has 0 | **Confirmed** · caps (soft) |
> | 4 | As row 1, except that a binding peak is > T + 2S, or `peak − T` rises with T, or the unthrottled T = 4 peak is > T + 4S | **Confirmed** · caps (soft); each exceeded bound is a missed sub-prediction. B1's own refuted-if counts only a peak or settled value that does not follow T |

**B2h. Controls.**
- T=1024 with an identical workload is the positive control: the workload moves usage when the cap cannot bind.
- Flush-reason check: only `COMMITLOG_DIRTY` flushes of `CLCap.Standard1` may appear during the write phase. Any `MEMTABLE_LIMIT` / `MEMTABLE_PERIOD_EXPIRED` entry invalidates the run.
- System tables are flushed and segments recycled before the write phase, so pre-existing dirty segments do not pin.
- File-size sum cross-checks the in-memory counter.
- One JVM per value.

**B2i. The line-259 arm (added by the stage-4 audit, 2026-10-21, R5).**

*Why.* Line 259 decides how many of the oldest segments are flushed: it stops the walk once `flushingSize + unused >= 0` (A3
step 4). The workloads of B2c and B3c write **one** table. There, any forced flush switches that table's whole memtable and frees
every segment except `allocatingFrom` and the spare, whatever 259 selected. So B2/B3 as filed cannot tell 259's stop condition
apart from "flush every older segment" (259 deleted). They repeat the test of the sibling line `:249`, which has already run
(`results/commitlog_total_space-maybeFlushToReclaim-unused--autonomous.md`). This arm makes 259's choice observable and
compares it with the same run with 259 disabled. It is added to the unit tier. It does not change B1, B2f or B2g. Its rows report
on A3 step 4 ("stop once the selected segments are enough to bring the size back to ≤ limit").

*Workload M* (`-Dclcap.mode=M`).
- T = 8 MiB, S = 1 MiB, 20 ms throttle, one JVM, the B2e setup.
- Instead of `Standard1`, 24 tables `CLCap.M00`…`M23` (the same `standardCFMD`), created with the keyspace.
- Mutation i (i = 0…255, 64 KiB random `val`, distinct key) goes to table `M⌊i/15⌋`. 15 such mutations fill one 1 MiB segment (16 × 64 KiB plus headers > 1 MiB). So each of `M00`…`M17` is written in about one segment, and no table is written again later.

*Arm M-nobreak* (`-Dclcap.nobreak=true`, the same workload). A Byteman rule `AT LINE 259` of `maybeFlushToReclaim` sets
`flushingSize = −2^62` before the comparison runs, so the comparison is never true. The walk then takes every segment older than
`allocatingFrom`, which is the behaviour without line 259. This is the negative control for the observables below: it shows they
can tell the two behaviours apart.

*Instruments.* Byteman through `BMUnitRunner`, as in `CommitLogSegmentBackpressureTest`. The rules are observation-only except
the M-nobreak rule. They write to `<clcap.out>.trace` from a helper class in the test, and they are active in every arm.
- `CHECK`: entry of `maybeFlushToReclaim`; counts the checks.
- `SELECT`: at the call to `flushDataFrom` (reached only when `unused < 0`). It records `unused`, `flushingSize`,
  `k = segmentsToRecycle.size()`, `older` (the active segments ahead of `allocatingFrom`), `stop259 = flushingSize + unused >= 0`,
  and `minimal = flushingSize − onDiskSize(last selected) + unused < 0`. Under M-nobreak the recorded `flushingSize` is the
  true sum of the selected segments' sizes.
- `FLUSH`: entry of `ColumnFamilyStore.forceFlush(CommitLogPosition)` when called from `flushDataFrom`. It records the table and
  whether its memtable will switch (`mayContainDataBefore`), tagged with the number of the last `SELECT`.
- The 1-ms `onDiskSize` series of B2d.

> **Stage-4 instrument note (2026-10-21, H1, from the instrument shakedown before run 1; predictions and rows unchanged).**
> Counting `older` when the rule runs races with segment discards on the flush thread: the shakedown logged `k=1 older=0`. So
> "`k = older`" (the walk ended at `allocatingFrom`) is read as **`gap = 0`**, and "`k < older`" (older segments left unselected) as
> **`gap > 0`**, where `gap = allocatingFrom.id − lastSelected.id − 1`. Segment ids are consecutive, so this is free of the race.
> `allocatingFrom` is also recorded at `CHECK`; a `SELECT` whose `allocId` differs from it had a concurrent switch and is
> reported, not used for prediction 2.

*Predictions (arm M, T = 8 MiB).*
1. At least 4 `SELECT` events (about 16 MiB is written against an 8 MiB cap).
2. Every `SELECT` has either `stop259` and `minimal` (exactly ⌈−unused/S⌉ segments), or `k = older` (the walk ended at `allocatingFrom`). At least one has `stop259` with `k < older`, which means the break fired while older segments were left unselected.
3. The `CLCap.M*` tables that switch per `SELECT` number ≤ k + 1, never all the dirty `M*` tables at once when k < older.
4. From the first `SELECT` to the end of the write phase, `onDiskSize` ≥ T − 3S = 5 MiB in every sample. The settled `onDiskSize` is between T − 3S and T.

*Predictions (arm M-nobreak).*
- Every `SELECT` has `k = older`.
- At least one `SELECT` switches ≥ 3 `M*` tables.
- `onDiskSize` falls to ≤ 3S after at least one event.
- The peak is still ≤ T + 2S.

*Rows (checked in order; reported beside the unit tier's B2g verdict, as the line-259 finding).*

| # | Observation | Meaning |
|---|---|---|
| i1 | Fewer than 2 `SELECT` events in M | **Invalid** (the limit was not reached) |
| i2 | M-nobreak has an event with `k < older`, or its trough stays > 3S | **Invalid** (the mutant rule did not act, or the observable cannot tell the two behaviours apart) |
| i3 | In M, some `SELECT` with `k < older` is not `minimal` (more segments than needed), or stops with `flushingSize + unused < 0` | **Refuted** (line 259): the stop condition does not pick just enough segments |
| i4 | Predictions 1–2 hold in M, but the trough falls to ≤ 3S, as in M-nobreak | **Not confirmed** (line 259): the selection is minimal, but the flushes free more than it selected, so 259 does not set how far usage falls |
| i5 | Predictions 1–4 hold in M, and M-nobreak meets its predictions | **Confirmed** (line 259): the stop condition picks just enough of the oldest segments, and that choice (not a flush of everything) keeps reclaim at about T |
| i6 | As i5, but prediction 3 or the settled band of prediction 4 is missed while the trough holds | **Confirmed** (line 259), with a missed sub-prediction |

### B3. Cluster tier

**B3a. Environment and build.**
- One node, using 127.0.0.1 on one host. A second node adds nothing, since the limit is per node.
- Build in the B2a copy: `cd /tmp/clcap/cassandra && ant jar stress-build` (`build.xml:577`).
- All node state goes under `/tmp/clcap/node` (local `/`, about 50 GB free; this run uses < 3 GB).
- Edit `/tmp/clcap/cassandra/conf/cassandra.yaml`:
  - `data_file_directories: [/tmp/clcap/node/data]`, `commitlog_directory: /tmp/clcap/node/commitlog`, `hints_directory: /tmp/clcap/node/hints`, `saved_caches_directory: /tmp/clcap/node/saved_caches`, `cdc_raw_directory: /tmp/clcap/node/cdc_raw`
  - `commitlog_segment_size: 32MiB` (default), `commitlog_disk_access_mode: legacy` (→ mmap; check the startup log line `commitlog_disk_access_mode resolved to: mmap`, `DatabaseDescriptor.java:642`), `commitlog_sync: periodic`
  - `commitlog_total_space: <T>` (B3b)
  - `memtable_heap_space: 8192MiB` and `memtable_cleanup_threshold: 0.9`, so that memtable pressure does not flush before about 7 GiB of memtable
  - `cdc_enabled: false`
  - leave `conf/commitlog_archiving.properties` empty
- Heap: `export MAX_HEAP_SIZE=24G HEAP_NEWSIZE=4G` before `bin/cassandra`.
- Ports 9042, 7000 and 7199 must be free: `ss -ltn | egrep ':(9042|7000|7199)\b'` must print nothing. Otherwise change `native_transport_port` / `storage_port` / `JMX_PORT` consistently.

> **Stage-4 audit amendment (2026-10-21, R4: clone, paths, yaml, start, sampling).** These change how the runbook runs, not the
> prediction.
> - **Clone and paths.** The clone is `pc06:~/cassandra-cl2` (R1); the node is built with `build-test`, which includes `stress-build`. Every `/tmp/clcap/node/...` path becomes `pc06:~/stage4-cl2/node/...` (local `/dev/sda3`, 55 GB free). The conf is copied per arm to `~/stage4-cl2/node/conf` and used through `CASSANDRA_CONF`, and the logs go to `CASSANDRA_LOG_DIR=~/stage4-cl2/node/logs`. Per-arm outputs are kept in `~/stage4-logs/cl2/cluster/<T>/`, and the node directory is wiped between arms (B3e step 1).
> - **yaml.** `cdc_enabled: false`, `commitlog_sync: periodic`, `commitlog_segment_size: 32MiB` and `commitlog_disk_access_mode: legacy` are already set, uncommented, in the shipped yaml (`conf/cassandra.yaml:413,634,660,678`). They are checked and left alone. Only the commented keys are appended (the directories, `commitlog_total_space`, `memtable_heap_space`, `memtable_cleanup_threshold`). Each key must then occur exactly once uncommented, so there are no duplicate yaml keys. `memtable_allocation_type` stays `heap_buffers` (`:825`), so `memtable_heap_space` is the binding memtable limit, as B3a assumes.
> - **Start.** `ulimit -n 100000` before `bin/cassandra`, because the peer's soft limit is 1024. Wait for `nodetool status` to show `UN` **and** for `nodetool statusbinary` to print `running`. Fail at once if the daemon dies. Find our daemon only with `ps -eo pid,args | grep '[j]ava.*cassandra-cl2.*CassandraDaemon'`, never with `pgrep -f`/`pkill -f`, which can match other processes and ssh shells. Stop it by its pid file.
> - **Stress.** The `-col` arguments are quoted (`-col 'size=FIXED(1000)' 'n=FIXED(1)'`), because bash rejects unquoted parentheses. The schema-creating `write n=1` (step 4) uses the same `-col` and `-rate threads=32`.
> - **Sampling (B3d).** `nodetool sjk mx` starts a JVM per call (about 1–2 s), so (i) is sampled back to back with an epoch-ms timestamp, not every 1 s. Because the unthrottled 1 GiB write may last only 10–30 s, (ii) and (iii) are sampled every **0.25 s**. Both changes give more samples; neither changes an observable.
> - **Flush census.** Taken over this lifetime's whole `system.log` (the node is new for each arm), up to the end of the settle window. Segment deletions are counted from `debug.log` (`Segment … is no longer active and will be deleted`).

**B3b. Knobs.**
- `commitlog_total_space` = **128MiB** (4 segments, binding), **256MiB** (8), **512MiB** (16), and **8192MiB** (control, also the default on this host since 1/4 × disk > 8 GiB).
- Set each in the yaml, then do a fresh start with wiped state.

**B3c. Workload.**
- `tools/bin/cassandra-stress write n=1000000 cl=ONE -col size=FIXED(1000) n=FIXED(1) -rate threads=32 -mode native cql3 -node 127.0.0.1 -log file=/tmp/clcap/stress-T<T>.log`
- Size: 10^6 rows × about 1.05 KB per serialized mutation ≈ 1.0 GiB of commit log, i.e. about 32 segment switches.
- That is ≥ 2× the largest binding T (512 MiB) and 8× T=128, but < 1/7 of the control 8192 MiB.
- Memtable on heap for 1 GiB of 1 KB values is roughly 1.5–2.5 GiB, below 0.9 × 8 GiB, so no memtable-pressure flush.
- Duration: a few minutes per run at stress default throughput; after it ends, a 60 s settle window.

**B3d. Observables and instruments.**
Run a sampler every 1 s during the stress run and the settle window, writing CSV to `/tmp/clcap/samples-T<T>.csv`:
- (i) `TotalCommitLogSize` via `bin/nodetool sjk mx -mg -b "org.apache.cassandra.metrics:type=CommitLog,name=TotalCommitLogSize" -f Value`
- (ii) real disk: `du -s -B1 --apparent-size /tmp/clcap/node/commitlog` and `ls /tmp/clcap/node/commitlog/*.log | wc -l` (× 32 MiB)
- (iii) `du -s -B1 /tmp/clcap/node/data/keyspace1` (sstables produced)

Also collect:
- Flush reasons: `grep -c "keyspace1.standard1, Reason: COMMITLOG_DIRTY" /tmp/clcap/cassandra/logs/system.log`, and the same grep for `MEMTABLE_LIMIT`.
- Pending flushes: `bin/nodetool tpstats | grep MemtableFlushWriter`.

Not observable directly: the per-switch `unused` value. It is inferred from (i) and T.

**B3e. Procedure (per T, starting with the control).**
1. `pkill -f CassandraDaemon` must find nothing of ours. `rm -rf /tmp/clcap/node /tmp/clcap/cassandra/logs; mkdir -p /tmp/clcap/node`
2. Set `commitlog_total_space: <T>` in the yaml.
3. Start: `cd /tmp/clcap/cassandra && MAX_HEAP_SIZE=24G HEAP_NEWSIZE=4G bin/cassandra -p /tmp/clcap/cassandra.pid`. Wait until `bin/nodetool status` shows `UN 127.0.0.1`.
4. Pre-create schema: `tools/bin/cassandra-stress write n=1 -node 127.0.0.1`. Then `bin/nodetool flush` and wait 10 s, so the baseline is a minimal commit log.
5. Start the sampler loop in the background. Run the stress command (B3c). Keep sampling 60 s after stress exits.
6. Record the peak and settled values of (i) and (ii), and the flush-reason counts.
7. `bin/nodetool drain; kill $(cat /tmp/clcap/cassandra.pid)`. Wait for exit and confirm with `pgrep -f CassandraDaemon`.
8. Repeat for the next T.

**B3f. Predictions (S = 32 MiB).**

| T | peak TotalCommitLogSize / du | settled (60 s after stress) | COMMITLOG_DIRTY flushes of keyspace1.standard1 |
|---|---|---|---|
| 128 MiB | ≤ 256 MiB (T + 4S) | ≤ 128 MiB | ≥ 5 |
| 256 MiB | ≤ 384 MiB | ≤ 256 MiB | ≥ 3 |
| 512 MiB | ≤ 640 MiB | ≤ 512 MiB | ≥ 1 |
| 8192 MiB (control) | ≈ 1.0–1.1 GiB, monotonically rising during stress | ≈ peak (no reclaim) | 0 |

- `peak − T` is about the same across 128, 256 and 512.
- The `du` apparent size tracks the metric within ±1 segment.
- 0 `MEMTABLE_LIMIT` flushes in every run.

**B3g. Readings.**

| Observation | Meaning |
|---|---|
| Sawtooth below T + 4S, settled ≤ T for each binding T; control rises to about 1 GiB with no COMMITLOG_DIRTY flush | Confirmed: the limit governs real commit-log disk, as a soft cap |
| Binding runs reach about 1 GiB like the control | Wrong: the limit does not cap disk |
| Metric ≤ T but `du` / file count far above T | Tracked size diverges from disk (A3 bypass c/d): cap on the counter only; claim refuted for the real resource |
| Overshoot grows with T, or keeps growing during stress while flushes are pending | Flush throughput, not the limit, governs; report MemtableFlushWriter pending |
| Control stays < 512 MiB | Workload too small or another flush trigger present: not confirmed |
| Any MEMTABLE_LIMIT flush | Confounded; raise `memtable_heap_space` / lower n and rerun |

> **Stage-4 audit amendment (2026-10-21, R3 for the cluster tier: a verdict per row, exact thresholds, one added row, rows
> checked in order).** Made before any reading. "Peak" is the `du --apparent-size` maximum during stress and settle. "**Peak follows
> T**" means the binding peaks are non-decreasing in T (128 ≤ 256 ≤ 512) and each is < 0.8 × the control's peak. "Fell back" means
> the commit log is ≤ T + S at the end of the 60 s settle.
>
> | # | Row (as filed, made exact) | Verdict · Effect |
> |---|---|---|
> | 5 | The control peaks < 512 MiB | **Invalid** (workload too small) |
> | 6 | Any `MEMTABLE_LIMIT` flush of `keyspace1.standard1` | **Invalid** (confounded; rerun as filed) |
> | 3 | The metric peak is ≤ T + 4S in a binding arm while the `du` peak exceeds it by > 2S, or `du` does not fall back while the metric does | **Refuted for disk** · does not cap (counter only) |
> | 2 | Some binding peak ≥ 0.8 × the control's, and that arm either had no `COMMITLOG_DIRTY` flush of `standard1` before its peak or did not fall back | **Refuted** · does not cap |
> | 4b | Some binding peak ≥ 0.8 × the control's, while that arm requested `COMMITLOG_DIRTY` flushes during the write and fell back within the settle | **Not confirmed** · caps only on some paths (bypass): a write rate above flush throughput outruns the cap while it lasts. B1's refuted-if excludes "a workload that flushes [do not] keep up with" |
> | 9 (added) | The peak follows T and every arm falls back, but some binding arm has 0 `COMMITLOG_DIRTY` flushes of `standard1` | **Not confirmed** · undetermined |
> | 1 | The peak follows T, every binding peak ≤ T + 4S, every binding arm settles ≤ T with ≥ 1 `COMMITLOG_DIRTY` flush, and the control has 0 | **Confirmed** · caps (soft) |
> | 4a | As row 1, except that a binding peak is > T + 4S, or the overshoot rises with T, or usage kept rising during stress while flushes were pending | **Confirmed** · caps (soft); each exceeded bound is a missed sub-prediction, and the flush-throughput series is reported |
>
> The flush counts and the `du`-vs-metric (± 1 segment) lines of B3f are sub-predictions. Missing one does not change the row
> unless the row names it.

> **Stage-4 amendment after cluster attempt 1 (2026-10-21; README "No §9a row fits"; the cluster tier restarts, and attempt 1 is
> kept but not counted).** Attempt 1 matched no row of the table above. Every binding peak was < 0.8 × the control's, every arm fell
> back to ≤ T with `COMMITLOG_DIRTY` flushes, but the binding peaks were **not** non-decreasing in T. Row 4 as filed ("Flush
> throughput, not the limit, governs") names this outcome, but R3 gave it a verdict only when the peak follows T. Added, checked
> just before row 1:
>
> | # | Row | Verdict · Effect |
> |---|---|---|
> | ~~4c~~ (struck 2026-10-22 by Jingsong's override: added after a reading) | Every binding peak < 0.8 × the control's, every binding arm falls back to ≤ T with ≥ 1 `COMMITLOG_DIRTY` flush, the control has 0, **but** the binding peaks are not non-decreasing in T (the overshoot, set by flush throughput, outweighs the differences in T) | **Not confirmed** (B1's "peak = T + a small overshoot independent of T" fails at this write rate) · caps (soft): usage is held below the uncapped run and reclaimed to ≤ T, but T does not set the peak |
>
> The verdict is the conservative one, so that a reading-driven amendment cannot move the file towards its own claim.

**B3h. Controls.**
- The control run (T = 8192 MiB) uses the same workload; it shows the workload moves disk usage where the cap cannot bind.
- Flush-reason census rules out memtable-pressure or periodic flushes (table default `memtable_flush_period_in_ms = 0`).
- Fresh state per run and a schema-only baseline.
- Two independent instruments (JMX metric and `du`).
- No `archive_command` and CDC off, which removes bypasses (c) and the CDC manager.

**B4. Risks and cleanup.**
- Disk:
  - Unit runs write < 50 MiB under `/tmp/clcap/cassandra/build/test`.
  - Cluster runs write ≤ about 1.2 GiB of commit log plus about 1.5 GiB of sstables per run, wiped between runs.
  - Never point any directory at `/proj` (shared).
  - Check `df -h /tmp` before each run and keep ≥ 10 GB free.
- Processes: after each tier, `pgrep -fa 'CassandraDaemon|cassandra-stress|junit'` must show nothing started by this run. Kill leftovers by PID.
- Final cleanup: `rm -rf /tmp/clcap`. The repository's `cassandra/cassandra-5.0.9/` is never modified.

## C. Sources read

- /proj/misconfiguration-PG0/git-repos/Misconfiguration/cassandra/if-check-exp/stage3-ai-deep-read/playbook-autonomous.md
- /proj/misconfiguration-PG0/git-repos/Misconfiguration/cassandra/if-check-exp/stage3-ai-deep-read/_TEMPLATE-autonomous.md
- /proj/misconfiguration-PG0/git-repos/Misconfiguration/cassandra/if-check-exp/README.md (§6.1 only)
- src/java/org/apache/cassandra/db/commitlog/AbstractCommitLogSegmentManager.java
- src/java/org/apache/cassandra/db/commitlog/CommitLogSegmentManagerStandard.java
- src/java/org/apache/cassandra/db/commitlog/CommitLogSegment.java (discard, isUnused)
- src/java/org/apache/cassandra/db/commitlog/CommitLog.java (discardCompletedSegments, method signatures)
- src/java/org/apache/cassandra/db/commitlog/MemoryMappedSegment.java (grep hits)
- src/java/org/apache/cassandra/metrics/CommitLogMetrics.java
- src/java/org/apache/cassandra/config/Config.java (commit log and memtable fields)
- src/java/org/apache/cassandra/config/DatabaseDescriptor.java (default derivation, getters, disk access mode resolution)
- src/java/org/apache/cassandra/db/ColumnFamilyStore.java (forceFlush, flush log line)
- conf/cassandra.yaml, conf/cassandra_latest.yaml (commit log sections)
- doc/modules/cassandra/pages/architecture/storage-engine.adoc
- test/conf/cassandra.yaml
- test/unit/org/apache/cassandra/db/commitlog/CommitLogSegmentBackpressureTest.java
- build.xml (targets, test.jvm.args)
- https://issues.apache.org/jira/browse/CASSANDRA-10013 , https://issues.apache.org/jira/browse/CASSANDRA-10199 (cited from source; not fetched)

## D. Stage-4 feedback

**2026-10-21, run 1 (no run 2)** — results: [`../../stage4-runtime-verification/results/commitlog_total_space-maybeFlushToReclaim-unused-2--autonomous.md`](../../stage4-runtime-verification/results/commitlog_total_space-maybeFlushToReclaim-unused-2--autonomous.md). Not committed. Frozen sha256 `c23bfe26…` (unit) and `cf7a8ff9…` (cluster, after D1); as filed `98750006…`.

- **Unit: Confirmed — caps (soft)** (B2g row 4, R3).
  - Peaks were 4, 5 and 9 MiB at T = 3, 4 and 8 (T + one segment each), against 19 MiB uncapped. Every arm settled ≤ T, after 8, 5 and 2 `COMMITLOG_DIRTY` flushes; the control had none.
  - Missed sub-predictions: the unthrottled T = 4 peak was 11 MiB (> T + 4S); the control reached 19 MiB (predicted 17–18).
- **Line 259 (B2i, added by the audit, R5): Confirmed** (row i5).
  - With 24 tables written one segment each, all 11 over-limit checks selected exactly ⌈−unused/S⌉ = 1 oldest segment and left 6 older segments unselected. Each flushed one table, and usage never fell below T = 8 MiB.
  - With line 259 disabled by a Byteman rule (M-nobreak), each check took all 7 older segments and flushed 7 tables, and usage fell to 2 MiB.
  - So the stop condition picks just enough segments, and that choice sets the reclaim level.
- **Cluster: Not confirmed — caps (soft)** (B3g row 4c, added after attempt 1 matched no row; the tier restarted, and attempt 1 is kept but not counted).
  - **Overruled by Jingsong, 2026-10-22:** row 4c was added after a reading, so it is struck; the cluster tier matched no row of the frozen B3g — **Not confirmed (no matching row), Effect undetermined**. A rerun needs a B3g with a "peaks not ordered by T" row frozen before any reading (and a throttled arm).
  - The workload was stress's unthrottled ~90 k writes/s. Peaks were 544, 448 and 832 MiB at T = 128, 256 and 512, against 1,120 MiB uncapped (also the default here). Usage settled at 64, 224 and 160 MiB (≤ T) after 11, 4 and 2 forced flushes; the control had none.
  - B3f's peak bounds (T + 4S) were missed at all three T, and the peaks were not ordered by T, identically in both attempts. The overshoot of 192–416 MiB is set by flush completion, not by T. So B1's "small overshoot independent of T" fails at this rate.
- **Duplication with `:249`.** B2 and B3 write a single table. There, every forced flush frees all but the two reserved segments, whatever line 259 selected, so these arms repeat the `:249` case's test (`results/commitlog_total_space-maybeFlushToReclaim-unused--autonomous.md`). Only B2i tests line 259.
- **Runbook amendments** (dated, above): R1 clone and paths; R2 flush census and outputs; R3 verdicts and thresholds per row; R4 cluster yaml, start, quoting and sampling; R5 B2i; the H1 instrument note; the D1 row 4c.
- **Left for stage 3:** run the unit default value. A throttled cluster arm would test whether T, rather than flush throughput, sets the node's peak at a moderate write rate. `:249`'s 20 k/s run suggests that it does.

