# max_log_size — verification solution  <!-- file: cases/max_log_size-DeletingArchiver-maxLogSize--autonomous.md -->

| Field | Value |
|---|---|
| Entry pointer | the given line (capacity-set: the archiver's cap field is assigned), **linked**: [`DeletingArchiver.java:46`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/utils/binlog/DeletingArchiver.java#L46) |
| Pinned source | `cassandra-5.0.9` |
| Session / date | Claude Opus 5.5 (`claude-opus-5-5`), Claude Code 2.1.330, 2026-11-24 |
| Estimate | `positive`. The value set at line 46 is the limit in `onReleased`'s `while (bytesInStoreFiles > maxLogSize ...)` loop, which deletes the oldest rolled Chronicle Queue files until the summed length of the rolled files is at most `max_log_size`. So the disk used by the full-query-log and audit-log directories follows the setting. The bound is soft: the active, not-yet-rolled cycle file is not counted, and files that an earlier BinLog instance left in the directory are never tracked. |
| Ground | — |

## A. Constraint trace

**A1. The constraint.** `max_log_size`, a configuration entry (a field of a nested yaml options
block), first declared at
[`BinLogOptions.java:54`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/utils/binlog/BinLogOptions.java#L54)
as `public long max_log_size = 16L * 1024L * 1024L * 1024L;`.
- Unit: bytes (a plain `long`, not a `DataStorageSpec`, so the yaml value is a bare integer with no unit suffix).
- Default: 17,179,869,184 (16 GiB), the literal product `16·1024·1024·1024`. It is not derived from anything else.
- Inherited by both binlog users: `FullQueryLoggerOptions extends BinLogOptions`
  (`src/java/org/apache/cassandra/fql/FullQueryLoggerOptions.java:25`) and
  `AuditLogOptions extends BinLogOptions` (`src/java/org/apache/cassandra/audit/AuditLogOptions.java:37`). These are
  `Config.full_query_logging_options` and `Config.audit_logging_options`
  (`src/java/org/apache/cassandra/config/Config.java:703-704`).
- How it is set:
  - yaml `full_query_logging_options.max_log_size` and `audit_logging_options.max_log_size`
    (`conf/cassandra.yaml:1907`, `:1922`, both commented out);
  - `nodetool enablefullquerylog --max-log-size <bytes>`
    (`src/java/org/apache/cassandra/tools/nodetool/EnableFullQueryLog.java:38-39`). When omitted, the yaml value is used
    (`src/java/org/apache/cassandra/service/StorageService.java:7138`);
  - `nodetool enableauditlog --max-log-size <bytes>` (`src/java/org/apache/cassandra/tools/nodetool/EnableAuditLog.java:61-62`,
    `src/java/org/apache/cassandra/audit/AuditLogOptions.java:198-203`);
  - the same values through the JMX `StorageServiceMBean.enableFullQueryLogger` / `enableAuditLog`.
- Restart: none needed. The value is read when a `BinLog` is built (`BinLog.java:405-408`, `:449`). A change takes
  effect when the log is disabled and enabled again (nodetool or JMX) or at the next startup. A running BinLog cannot be
  changed in place.
- Validation: the value must be greater than 0 (`BinLog.java:407`, `DeletingArchiver.java:45`).
- It applies only when `archive_command` is empty. Otherwise an `ExternalArchiver` is used instead and `max_log_size` is
  ignored (`BinLog.java:449`; `doc/modules/cassandra/pages/managing/operating/auditlogging.adoc:278`).

**A2. What it caps.** Disk: the bytes of rolled Chronicle Queue cycle files (`*.cq4`) in the FQL `log_dir` or the
audit `audit_logs_dir`. The quantity compared against the limit is `DeletingArchiver.bytesInStoreFiles`. It is the sum of
`File.length()` (apparent size, not allocated blocks) of every rolled file this archiver instance has seen and not yet
deleted. Each length is taken at the moment the file is released (`DeletingArchiver.java:58`).

**A3. Mechanism.**
1. `BinLog.Builder.build` creates `new DeletingArchiver(maxLogSize)` when `archive_command` is null or empty
   (`BinLog.java:449`). The constructor checks `maxLogSize > 0` (`DeletingArchiver.java:45`) and stores it at the given
   line, [`DeletingArchiver.java:46`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/utils/binlog/DeletingArchiver.java#L46).
2. The archiver is registered as the queue's `StoreFileListener` (`BinLog.java:144`). Chronicle calls
   `onReleased(cycle, file)` when a cycle file is released. In practice that is when the single appender rolls to a new
   cycle and when the queue is closed (`BinLog.stop`, `BinLog.java:185-187`).
3. `onReleased` appends the file to a FIFO (`DeletingArchiver.java:56`) and adds `file.length()` to
   `bytesInStoreFiles` (`:58`). The code comment says the value is pessimistic because files are sparse (`:57`).
4. The check is
   [`DeletingArchiver.java:60`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/utils/binlog/DeletingArchiver.java#L60):
   `while (bytesInStoreFiles > maxLogSize & !chronicleStoreFiles.isEmpty())`.
   - **Over the limit:** it polls the oldest file (`:62`), reads its current length (`:63`) and deletes it (`:64`).
     - On success it subtracts that length (`:72`) and logs at INFO (`:73-74`). Note: the INFO line prints `file.getPath()`
       (the file just released), not `toDelete`, so the path in "Deleted chronicle store file" names the wrong file.
       Only its sizes are reliable.
     - On failure it logs an ERROR and keeps the byte count (`:64-69`). The file leaves the FIFO but its bytes stay in
       the counter as a "ghost". The loop then deletes newer files instead. Disk use still stays at or below the limit,
       because the ghost is still on disk.
   - **At or under the limit** (`<=`): nothing is deleted.
   - A single released file larger than the limit deletes itself, including the newest one (unit test
     `test/unit/org/apache/cassandra/utils/binlog/DeletingArchiverTest.java:51-59`).
5. Overshoots and bypasses:
   - **(a) Active file not counted.** The current cycle file is never counted until it rolls. Disk use is at most
     `max_log_size` plus the active file (up to one roll cycle of data, rounded up to Chronicle's block allocation) plus
     the small queue metadata files. The nodetool help text says the same: "Might not be respected if a log file hasn't
     rolled" (`EnableFullQueryLog.java:38`).
   - **(b) Earlier files never tracked.** Each new `BinLog` gets a new, empty archiver. Files left by an earlier
     instance are never tracked or deleted. FQL enabled through nodetool/JMX uses `enableWithoutClean`
     (`StorageService.java:7145`, `FullQueryLogger.java:106-118`, `build(false)`), and so does the audit logger
     (`BinAuditLogger.java:45-52`, `build(false)`). Only `FullQueryLogger.enable` (`:91-104`) builds with
     `cleanDirectory=true`. A disable followed by an enable, or a node restart, can therefore leave up to about
     `max_log_size` of untracked files per earlier instance.
   - **(c) Length can change after release.** The length is read at release (`:58`). Chronicle's
     `QueueFileShrinkManager` may later shrink the file asynchronously
     (`doc/modules/cassandra/pages/managing/operating/auditlogging.adoc:290`). When the file is deleted, the smaller
     length is subtracted (`:63`, `:72`). The counter can only drift upward, so the archiver over-deletes, never
     under-deletes. Apparent size of a released file is at least the default block size (80 MiB per the same doc) even
     when it holds little data.
   - **(d) Archive command replaces the archiver.** With a non-empty `archive_command`, the archiver is replaced and
     there is no cap.

**A4. Other consumers.** In the same directory, outside this cap:
- the active cycle file;
- Chronicle metadata files (`metadata.cq4t`, `directory-listing.cq4t`);
- leftover files from earlier BinLog instances (A3 5b).

On the same volume, but not governed by this cap: commit log, data, hints.

Related memory, governed by a different constraint: before records reach disk they sit in the
`WeightedQueue` bounded by `max_queue_weight` (`BinLog.java:142`, `BinLogOptions.java:49`). That is heap memory.

**A5. Evidence beyond the source.**
- `doc/modules/cassandra/pages/managing/operating/auditlogging.adoc:268-292`: semantics of `max_log_size` and
  `archive_command`, the 80 MiB block size, and asynchronous shrinking.
- `doc/modules/cassandra/pages/managing/operating/fqllogging.adoc:130-133`.
- Unit tests `test/unit/org/apache/cassandra/utils/binlog/DeletingArchiverTest.java:37-88`.
- Chronicle Queue version 5.23.37 (`.build/parent-pom-template.xml:861-862`); `StoreFileListener` documented at
  https://github.com/OpenHFT/Chronicle-Queue (README, "StoreFileListener"), not read in this session.

## B. Verification solution

**B1. Claim under test.** With `archive_command` empty, during the life of one BinLog the summed apparent size of the
rolled `*.cq4` files in the log directory stays at or below `max_log_size` after each roll. The whole directory stays at
or below `max_log_size` plus one active cycle file plus metadata. Retained rolled bytes follow the knob: they plateau at
about `floor(M/S)·S` for release-time file size `S`. Without a binding cap they grow linearly with the workload. Files
from an earlier BinLog instance are outside the cap.

### B2. Unit tier

**B2a. Environment and build.**
- Linux, JDK 11 (`java -version` shows 11), Apache Ant ≥ 1.10.
- Work in a private copy on local disk, never in the shared tree:
  `rsync -a ~/cassandra-5.0.9/ /mydata/$USER-s4/c509/ && cd /mydata/$USER-s4/c509`
  (any local disk with ≥ 10 GB free; called `$W` below).
- Build: `ant jar build-test` (the first build downloads dependencies).
- Add the test file `$W/test/unit/org/apache/cassandra/utils/binlog/MaxLogSizeCapTest.java` (package
  `org.apache.cassandra.utils.binlog`, so it can call package-private `getBytesInStoreFiles()`).
- Run: `ant testsome -Dtest.name=org.apache.cassandra.utils.binlog.MaxLogSizeCapTest`.
- JVM options: the test defaults; DEBUG logging for `org.apache.cassandra.utils.binlog.DeletingArchiver` in
  `test/conf/logback-test.xml` (add `<logger name="org.apache.cassandra.utils.binlog.DeletingArchiver" level="DEBUG"/>`).
- Run as a non-root user.

**B2b. Knobs.** `maxLogSize` M, passed to the constructor (U1) or to `BinLog.Builder.maxLogSize` (U2).
- **U1 (archiver alone, file size F = 1,048,576 B):** M ∈ {1,048,575; 5,242,880; 11,010,048; 104,857,600}.
  - F−1: every file is above the limit, so each deletes itself.
  - 5 MiB: exact multiple; tests the `>` vs `>=` boundary.
  - 10.5 MiB: non-multiple; tests the floor.
  - 100 MiB: never reached; the not-binding control.
- **U2 (real BinLog, `RollCycles.TEST_SECONDLY`):** first a calibration run with M = 2^40 (not binding) to measure the
  release-time length S of each rolled file from the DEBUG line `DeletingArchiver.java:59`. Then M ∈ {S/2, 1.5·S, 3.5·S}
  (rounded to integers).

**B2c. Workload.**
- **U1:** create 20 files of exactly F random bytes with `Files.write` under `Files.createTempDirectory(...)` on `$W`
  (not `/tmp` if that is shared). Call `da.onReleased(1, f.toJavaIOFile())` in order. Total offered: 20 MiB. The limit
  is crossed at file 6 (5 MiB), file 11 (10.5 MiB) and file 1 (F−1), and never at 100 MiB.
- **U2:**
  1. Call `DatabaseDescriptor.daemonInitialization()` (as in `BinLogTest.java:66-70`).
  2. Build the log: `new BinLog.Builder().path(dir).rollCycle("TEST_SECONDLY").blocking(true).maxQueueWeight(64<<20).maxLogSize(M).build(true)`,
     with `dir` a fresh directory on `$W`.
  3. Feed it with one producer thread that `binLog.put(...)`s records whose payload writes 262,144 random bytes
     (`wire.write("p").bytes(byte[])`, `release()` no-op), 40 per second (about 10 MiB/s), for 30 s. That gives about 30
     one-second cycles, so about 29 rolls.
  4. Stop with `binLog.stop()`.

  Each cycle holds about 10 MiB of data, below the 80 MiB block, so S is the same for every file (about one block). With
  29 releases × S against 3.5·S, the limit is crossed at the 4th release.

**B2d. Observables and instruments.**
- U1: after each `onReleased`, record:
  - `C_k = da.getBytesInStoreFiles()`;
  - `D_k` = sum of `Files.size` of the 20 files that still exist;
    *Amended 2026-11-24 (stage-4 runbook defect S4-D1, results file §3): `D_k` = sum of `Files.size` of the files
    released so far (1..k) that still exist. The 20 files are all created before the first release, so the filed
    definition counts files the archiver has not yet seen and cannot equal `C_k` before k = 20, as B2f requires. B2f is
    unchanged; the sum over all 20 files is still printed (`allFilesOnDisk`).*
  - the number of surviving files (of those released).

  Print these as CSV.
- U2: get the archiver by reflection (`Field f = BinLog.class.getDeclaredField("archiver"); f.setAccessible(true)`). A
  sampler thread every 200 ms records:
  - `C(t)`;
  - `R(t)` = sum of `Files.size` over `*.cq4` files whose cycle is older than the newest;
  - `A(t)` = size of the newest `*.cq4`;
  - the count of `*.cq4`.

  In parallel, a shell loop records `du -sB1 --apparent-size $dir; du -sB1 $dir` every 1 s into `du.csv`.
- What cannot be observed directly: the exact moment Chronicle calls `onReleased`. Infer it from the DEBUG line and the
  counter step.

**B2e. Procedure.**
1. Write the test with methods `u1_M1048575`, `u1_M5MiB`, `u1_M10_5MiB`, `u1_M100MiB`, `u2_calibrate`, `u2_half`,
   `u2_1_5`, `u2_3_5`. Each U2 method reads S from a system property `-Dcap.S=<bytes>`.
2. Run `ant testsome -Dtest.name=org.apache.cassandra.utils.binlog.MaxLogSizeCapTest -Dtest.methods=u1_M1048575,u1_M5MiB,u1_M10_5MiB,u1_M100MiB`.
3. Run `-Dtest.methods=u2_calibrate`. Read S from `build/test/logs/` (the "rolled file size" DEBUG lines), and take the
   modal value.
4. Run `u2_half,u2_1_5,u2_3_5` with `-Dcap.S=<S>`. If `testsome` does not pass the property, add it to `test.jvm.args`.
5. Collect the CSVs, then delete every test directory (`rm -rf $W/<test dirs>`).

**B2f. Predictions.**
- U1, final values after 20 releases:

  | M | C_20 = D_20 | Files kept |
  |---|---|---|
  | F−1 | 0 | 0 |
  | 5,242,880 | 5,242,880 | files 16–20 |
  | 11,010,048 | 10,485,760 | 10 |
  | 104,857,600 | 20,971,520 | 20 (cap not reached) |

  Each step k follows `C_k = D_k = F·min(k, floor(M/F))` for M ≥ F. `C_k ≤ M` at every step.
- U2 calibration: `C(t)` and `R(t)` rise by S per second, to about 29·S by the end. Nothing is deleted.
- U2 with M = S/2: `C` = 0 after every release. Rolled files: 0. Directory = active file + metadata.
- U2 with M = 1.5·S: one rolled file kept, so `C` = S.
- U2 with M = 3.5·S: three rolled files kept, so `C` = 3·S.
- In every U2 run, `C(t) ≤ M` at all samples after a release. `R(t) ≤ C(t)` (shrink only lowers sizes). Apparent
  directory size ≤ M + A(t) + metadata.

**B2g. Readings.**

| Observation | Meaning |
|---|---|
| U1 values match B2f exactly; U2 plateaus at floor(M/S)·S | Mechanism works as traced; claim holds at unit level |
| `C_k` or `R(t)` exceeds M after a release completes | Claim wrong: the check does not bound the rolled bytes |
| M = 5 MiB keeps 4 files (or 6) | Boundary is `>=` (or off by one), not `>` as at `:60`; amend A3 |
| U2 rolled count does not change between M = 1.5·S and 3.5·S | Usage does not follow the knob; claim refuted |
| Calibration (2^40) shows no growth, or no rolls | Workload never reached the limit; result inconclusive, so raise the rate or duration |
| Files deleted while `C` stays above M and ERROR "Failed to delete" appears | Delete failure path (A3 4); check permissions and the root user |

**B2h. Controls.**
- The not-binding M (100 MiB in U1, 2^40 in U2) shows the same workload grows usage linearly. This is the positive
  control that the workload moves the operand.
- The F−1 and S/2 values show self-deletion.
- Compare `D_k` (filesystem truth) with `C_k` (operand) to rule out the counter drifting from real files.
- A fresh directory per run rules out leftovers (A3 5b).

**B2-amendments (stage-4 audit, 2026-11-24, before any reading; B1's claim unchanged).**
- **S4-A1 (B2a, paths).** `$W` = `/mydata/jingsong-cass-s4/o57/src`, a `copy-source.sh` copy of the repository's
  `systems/cassandra/source/` (tag `cassandra-5.0.9`) made on the coordinating node and `rsync`ed to the run node, which
  has no `/proj` mount; `ant jar build-test` there. Unit test directories under `$W/build/o57-unit/` (property `cap.base`).
- **S4-A2 (B2e, one JVM per U2 value).** Each U2 method runs in its own `ant testsome` invocation: `BinLog.stop()` calls
  the JVM-global `BackgroundResourceReleaser.stop()` (`BinLog.java:183`), so a second BinLog in the same JVM would release
  its stores differently from the first. U1's four methods share one JVM (no BinLog). `-Dcap.S` is passed with
  `-Dtest.jvm.args="-Dcap.S=<S>"`.
- **S4-A3 (B2d, release lag).** The U2 sampler also reads the archiver's FIFO (`chronicleStoreFiles`, by reflection)
  together with `C(t)` under the archiver's monitor (`onReleased` is `synchronized`, `DeletingArchiver.java:54`). A rolled
  `*.cq4` on disk that is not in the FIFO has rolled but not yet been released, so the archiver cannot have counted it
  (A3 step 2). `R(t) ≤ C(t)` and `R(t) ≤ M` are evaluated at samples with no such untracked rolled file; at other samples
  `R` may exceed `C` by that one file.
- **S4-A4 (B2f/B2g, U2 pass rule).** S = the modal release-time length of the calibration run. If every release-time
  length equals S, B2f's plateau values apply exactly. If lengths vary, U2 passes when (i) `C(t) ≤ M` at every sample,
  (ii) the mean number of tracked rolled files over the write-phase samples after the limit is first crossed is
  `floor(M/S)` ± 0.5, and (iii) that number is 0 for S/2, 1 for 1.5·S and 3 for 3.5·S (so it follows the knob). The B2g
  row "U2 plateaus at floor(M/S)·S" is read with this rule.

### B3. Cluster tier

**B3a. Environment and build.**
- One Linux node with ≥ 40 GB free local disk at `/mydata/$USER-s4/`, JDK 11, the same `$W` build
  (`ant jar`; `tools/bin/cassandra-stress` is built by `ant jar` too, otherwise run `ant stress-build`).
- Make a node directory `$N=/mydata/$USER-s4/node1`. Copy `$W/conf` to `$N/conf`.
- Set in `$N/conf/cassandra.yaml`:
  - `data_file_directories: [$N/data]`
  - `commitlog_directory: $N/commitlog`
  - `saved_caches_directory: $N/saved_caches`
  - `hints_directory: $N/hints`
  - `commitlog_total_space: 1024MiB`
  - `cluster_name: s4-maxlogsize`
  - listen/rpc address `127.0.0.1`, ports default (check they are free with `ss -ltn`)
  - this block:
    ```yaml
    full_query_logging_options:
      log_dir: /mydata/$USER-s4/fql
      roll_cycle: MINUTELY
      block: true
      max_queue_weight: 268435456
      max_log_size: <M>
    ```
    Leave `archive_command` unset.
- Start with:
  `export CASSANDRA_CONF=$N/conf MAX_HEAP_SIZE=4G HEAP_NEWSIZE=800M CASSANDRA_LOG_DIR=$N/logs; $W/bin/cassandra -p $N/pid`.

**B3b. Knobs.** `--max-log-size` on `nodetool enablefullquerylog`, which overrides yaml per enable and needs no restart:
- **K1:** M = 2,147,483,648 (2 GiB). Binding: about 3 cycles of the workload.
- **K2:** M = 1,099,511,627,776 (1 TiB). Not binding; the positive control.
- **K3:** M = 1,073,741,824 (1 GiB). Checks that the plateau follows the knob.
- **K4:** K1 followed by disable and then enable on the same directory, to show bypass A3 5b.

**B3c. Workload.**
- Command:
  `$W/tools/bin/cassandra-stress write duration=12m cl=ONE -pop seq=1..100000 -col size=FIXED(2048) n=FIXED(1) -rate threads=32 fixed=5000/s -mode native cql3 prepared -node 127.0.0.1`
- Each FQL record holds the query string plus about 2 KiB of bound value, about 2.3 KiB in all. At 5000/s that is about
  11.5 MiB/s, so about 690 MiB per MINUTELY file and about 8.1 GiB over 12 minutes.
- With K1, the limit (2 GiB) is crossed at the 4th roll (about minute 4). Without a cap, the directory would reach about
  8 GiB.
- `-pop seq=1..100000` overwrites about 200 MB of keys, so the table data stays small. The commit log is capped at 1 GiB.

**B3d. Observables and instruments.**
- Every 5 s, append to `fql.csv`: epoch, `du -sB1 --apparent-size $FQL`, `du -sB1 $FQL`, `ls $FQL/*.cq4 | wc -l`, and the
  newest file's `stat -c %s`.
- Cassandra `debug.log`/`system.log`:
  - before the run, `nodetool setlogginglevel org.apache.cassandra.utils.binlog.DeletingArchiver DEBUG`;
  - grep "rolled file size" (release-time length S_i) and "Deleted chronicle store file" (deletions; trust only the
    sizes, see A3 4).
- `nodetool getfullquerylog` to confirm `max_log_size` is in effect.
- `df -B1 /mydata` before and after.
- What cannot be observed: the in-memory counter (no metric or JMX). Reconstruct it from the log lines:
  Σ rolled sizes − Σ deleted sizes.

**B3e. Procedure.**
1. Start the node and wait for `nodetool status` to show UN.
2. Prepare the directory: `rm -rf /mydata/$USER-s4/fql && mkdir -p /mydata/$USER-s4/fql`.
3. Enable FQL: `nodetool enablefullquerylog --path /mydata/$USER-s4/fql --roll-cycle MINUTELY --blocking true --max-log-size <M>`.
   Then run `nodetool getfullquerylog`.
4. Start the sampler loop in the background, then run the stress command (12 min).
5. Stop the log with `nodetool disablefullquerylog`. Sample for 30 s more, then stop the sampler.
6. Repeat steps 2–5 for K2 and K3. Each run starts from a cleared directory.
7. K4 (bypass):
   1. Repeat K1 without clearing the directory at the end.
   2. Run `nodetool enablefullquerylog` again with the same path and M = 2 GiB, plus 6 more minutes of stress.
   3. Record which old files persist (`ls -l --time-style=+%s`).
8. Clean up:
   1. `nodetool disablefullquerylog; nodetool stopdaemon` (or `kill $(cat $N/pid)`).
   2. Confirm nothing is left: `pgrep -u $USER -f CassandraDaemon` and `pgrep -f cassandra-stress` print nothing.
   3. `rm -rf /mydata/$USER-s4/fql $N`.

**B3f. Predictions.**
- **K2 (control):** apparent size grows about linearly at about 690 MiB/min and reaches about 8 GiB (≥ 7 GiB) at the end.
  Nothing is deleted. The file count rises by 1 per minute.
- **K1:**
  - Rolled files each S_i ≈ 690–770 MiB (data rounded up to the block).
  - From about minute 4, the directory's rolled `*.cq4` total plateaus at ≤ 2 GiB: two rolled files, about 1.4–1.5 GiB.
  - Total apparent size stays ≤ 2 GiB + one active file (≤ about 0.8 GiB) + metadata, so ≤ about 2.9 GiB at every
    sample.
  - "Deleted" lines appear roughly once per minute after minute 4.
- **K3:** plateau at one rolled file (≤ 1 GiB rolled). Total ≤ about 1.9 GiB. At every time after minute 3, K3 is below K1.
- **K4:** after the re-enable, the 2–3 files left by the first instance (about 1.4–2.2 GiB, including the file released
  at disable) are never deleted. The directory total rises to about old residue + 2 GiB + active, about 4–5 GiB, which
  is above M. The new instance's own rolled files still plateau at ≤ 2 GiB.

**B3g. Readings.**

| Observation | Meaning |
|---|---|
| K1/K3 plateau at ≤ M rolled + one active file, while K2 grows to about 8 GiB | Claim confirmed: the limit governs real disk use |
| K1 rolled total > M after a roll and stays there, with no "Deleted" lines | Claim wrong; the cap is not enforced on a real node |
| K1 and K3 plateaus equal | Usage does not follow the knob; claim refuted |
| K2 does not grow (or FQL is empty) | Workload or FQL not active; inconclusive. Check `getfullquerylog` and stress throughput |
| K4 directory > M with old files persisting | Bypass A3 5b confirmed; the cap is per instance, not per directory |
| K4 old files deleted | Some cleanup tracks earlier files; amend A3 5b |
| Directory > M + one active + metadata within one instance | Overshoot beyond what was traced (for example onReleased not called on roll); claim wrong as stated |

**B3h. Controls.**
- K2 is the same workload with a non-binding cap. It shows the workload moves disk use, so a K1 plateau is due to the
  cap.
- `getfullquerylog` confirms which M is in effect.
- Directories are cleared between runs (except in K4) so leftovers cannot inflate readings.
- The `du` apparent versus allocated pair separates sparse allocation from apparent length.
- Stress throughput (its summary op rate) shows the input rate was the same across K1–K3.

**B3-amendments (stage-4 audit, 2026-11-24, before any reading; B1's claim unchanged).**
- **S4-A5 (B3a, paths and node).** `/mydata/$USER-s4/` = `/mydata/jingsong-cass-s4/o57/` (`node1/`, `fql/`); `$W` as
  S4-A1. The run node had 29 GB free on `/mydata`, below the 40 GB asked; the peak need is about 8 GiB of FQL (K2), 1 GiB
  of commit log and under 1 GiB of table data, so it suffices. `ulimit -n 100000` before start. A 15 s run of the B3c
  stress command with FQL off checks the command and the node's throughput before K1 (instrument check).
- **S4-A6 (B3f/B3g, reading rules fixed before the run).** B3f's file sizes (690–770 MiB) and counts assume the stress
  reaches 5000 op/s; the achieved rate `r` is read from each stress summary. Independent of `r`:
  (i) a sample with rolled total > M (rolled = every `*.cq4` but the newest) counts as "rolled total > M after a roll and
  stays there" only if the next sample (5 s later) is also > M, since a file that just rolled is counted only when it is
  released (A3 step 2);
  (ii) the predicted number of retained rolled files is `floor(M/S_i)` with `S_i` the logged release-time lengths, and
  B3f's "two files" (K1) and "one file" (K3) are read with the measured `S_i`;
  (iii) the K2 control "grows" when its final apparent size is at least twice K1's largest apparent sample; otherwise
  the B3g row "K2 does not grow" applies;
  (iv) "follows the knob" = K3's mean total apparent size over the samples after its first deletion is below K1's over
  the samples after K1's first deletion, and K3's retained rolled count is below K1's.
- **S4-A7 (B3e step 7, K4).** K4 = K4a (K1 again, from a cleared directory, 12 min) then K4b (re-enable on the same path,
  not cleared, M = 2 GiB, 6 min). "Old files" = the `*.cq4` files listed after K4a's disable.

**B4. Risks and cleanup.**
- Disk: the cluster tier writes up to about 8 GiB of FQL (K2), plus small data and a 1 GiB commit log, all under
  `/mydata/$USER-s4/`. Check `df` shows ≥ 40 GB free first. The unit tier writes ≤ 30·S apparent (sparse) in `$W`.
- Nothing goes in the shared source tree or shared storage.
- Processes: Cassandra (pid file `$N/pid`) and cassandra-stress. Kill both and verify with `pgrep`. In the unit tier the
  test JVM exits after `ant testsome`. The BinLog thread is stopped by `binLog.stop()` in `@After`.
- Clean up with `rm -rf /mydata/$USER-s4/fql /mydata/$USER-s4/node1` and the unit test directories. Keep `$W` only if
  stage 4 reuses it.

## C. Sources read

- src/java/org/apache/cassandra/utils/binlog/DeletingArchiver.java
- src/java/org/apache/cassandra/utils/binlog/BinLogOptions.java
- src/java/org/apache/cassandra/utils/binlog/BinLog.java
- src/java/org/apache/cassandra/fql/FullQueryLogger.java
- src/java/org/apache/cassandra/fql/FullQueryLoggerOptions.java (grep)
- src/java/org/apache/cassandra/audit/BinAuditLogger.java
- src/java/org/apache/cassandra/audit/AuditLogOptions.java (grep)
- src/java/org/apache/cassandra/audit/AuditLogManager.java (grep)
- src/java/org/apache/cassandra/service/StorageService.java (6970-7030, 7125-7150)
- src/java/org/apache/cassandra/tools/nodetool/EnableFullQueryLog.java
- src/java/org/apache/cassandra/tools/nodetool/EnableAuditLog.java (grep)
- src/java/org/apache/cassandra/config/Config.java (grep), DatabaseDescriptor.java (grep), CassandraRelevantProperties.java (grep)
- conf/cassandra.yaml (1870-1930)
- doc/modules/cassandra/pages/managing/operating/auditlogging.adoc (268-292)
- doc/modules/cassandra/pages/managing/operating/fqllogging.adoc (125-140)
- test/unit/org/apache/cassandra/utils/binlog/DeletingArchiverTest.java
- test/unit/org/apache/cassandra/utils/binlog/BinLogTest.java (52-118 and grep)
- .build/parent-pom-template.xml (855-915), .build/cassandra-deps-template.xml (180-205)
- build.xml (grep for testsome)
- https://github.com/OpenHFT/Chronicle-Queue (cited for StoreFileListener, not fetched)

## D. Stage-4 feedback

none yet
