# Data-volume free-space warning threshold (64 GiB) — verification solution  <!-- file: cases/data-free-space-warn-threshold--autonomous.md -->

| Field | Value |
|---|---|
| Entry pointer | `src/java/org/apache/cassandra/config/DatabaseDescriptor.java:726` |
| Pinned source | `cassandra-5.0.9` |
| Session / date | Claude Sonnet 5.5, Claude Code CLI (Agent SDK), 2026-10-26 |
| Estimate | `negative`: the line only compares summed free bytes to a hard-coded 64 GiB and logs a WARN; nothing is limited, refused or evicted. |
| Ground | The operand is free disk space, which is an input to the check and is not a quantity Cassandra bounds. The only effect is a log line at startup. The threshold is a literal (`64 * ONE_GIB`) with no setting. It is read once in `applyAll()` and never again. Disk usage is governed by other mechanisms (compaction, `auto_snapshot`, `max_hints_file_size`, `commitlog_total_space`, `disk_failure_policy`, `data_disk_usage_max_disk_size`). |

## A. Constraint trace

**A1. The constraint.** Name: the "64 GB free across all data volumes" warning threshold. Kind: constant, a literal in code with no yaml key or property. Declared at `DatabaseDescriptor.java:726` as `64 * ONE_GIB`. `ONE_GIB` is imported at `:143` from `io/util/FileUtils.java:77` (`1024 * ONE_MIB`). Unit: bytes (64 GiB = 68,719,476,736). Default: fixed, there is nothing to derive. How set: not settable (no yaml, no `-D`, no JMX). Changing it needs a source edit and rebuild. The check runs once per JVM start, inside `applySimpleConfig()` (`:478`), which is called from `applyAll()` (`:447`, `:455`) and from `daemonInitialization` (`:245`, `:263`). A parallel constant, `ONE_GIB` for `local_system_data_file_directory`, is at `:741`.

**A2. What it caps.** Nothing. The resource is disk. The quantity compared is `dataFreeBytes`, the saturating sum (`:1654-1659`) of `FileStore.getUnallocatedSpace` over every entry of `data_file_directories` (`:711-725`, via `tryGetSpace` at `:1661-1664` and `PathUtils.tryGetSpace`). It is compared with 64 GiB (`:726`). Note that `getUnallocatedSpace` is the filesystem's free space. It is not Cassandra's data size, and volumes shared by several directories are counted once per directory.

**A3. Mechanism.**
1. `:704-707`: if `data_file_directories` is unset, default to `<cassandra.storagedir>/data`.
2. `:709-725`: for each directory, run the duplicate-path checks (`:713-722`, which throw `ConfigurationException`), then add its unallocated space to `dataFreeBytes`. If the space cannot be read, `tryGetSpace` throws `ConfigurationException` (`:1663`), so startup aborts. That is the only hard failure, and it is not tied to the threshold.
3. `:726-728`: if `dataFreeBytes < 64 * ONE_GIB`, `logger.warn("Only {} free across all data volumes. Consider adding more capacity ... removing obsolete snapshots", FBUtilities.prettyPrintMemory(dataFreeBytes))`. The formatter is `FBUtilities.java:924-935`.
4. Outcomes: at or above the threshold, nothing happens. Below it, one WARN line, and startup continues identically. There is no write rejection, no flush, compaction or snapshot change, and no later re-check.
Bypass or overshoot: the check is not on the write path at all, so disk can be filled to 100% regardless. Free space is read only at startup, so later growth is invisible to it. Summing across volumes can hide one nearly-full volume (for example 1 GiB free plus 100 GiB free gives no warning). Related but separate: `local_system_data_file_directory` has its own 1 GiB warning (`:739-743`).

**A4. Other consumers.** Anything else that writes to the data volume: commit log, hints, saved caches, snapshots, backups, logs, other processes on the host. Cassandra's real disk guards live elsewhere (`DiskUsageMonitor` and `data_disk_usage_max_disk_size`, `disk_failure_policy`, `commitlog_total_space`, `max_hints_file_size`). These were not traced for this case.

**A5. Evidence beyond the source.** None. (The warning text was read directly from the pinned tree; no external docs were relied on.)

## B. Verification solution

**B1. Claim under test.** The 64 GiB threshold at `:726` does not cap disk (or memory) usage: it only emits a startup WARN, and a node with less than 64 GiB free still accepts writes and grows its data directory until the volume is full, while the same node with more than 64 GiB free is subject to exactly the same growth.

### B2. Unit tier

**B2a. Environment and build.** JDK 11, Ant, on a local-disk copy of the tree (`rsync -a cassandra-5.0.9/ $WORK/c/`; never build in the shared tree). `cd $WORK/c && ant jar -Duse.jdk11=true`. Test source: a small JUnit class `DataFreeSpaceWarnTest` placed in the copy's `test/unit/org/apache/cassandra/config/`, run with `ant testsome -Dtest.name=org.apache.cassandra.config.DataFreeSpaceWarnTest`. JVM options are the defaults of `build.xml` (`-Dcassandra.storagedir=$WORK/storage`, `-Dcassandra.config=file:///$WORK/test.yaml`).

**B2b. Knobs.** (1) Number and location of `data_file_directories` (set in `test.yaml`): one directory on a small tmpfs or loop filesystem of known size (for example 1 GiB), and one on a large local filesystem. (2) For a no-warning case, a filesystem with more than 64 GiB free (the local scratch disk, if large enough). (3) The log appender: attach a Logback `ListAppender` to the `DatabaseDescriptor` logger to capture WARN events. There is no knob for the threshold itself because it is a literal.

**B2c. Workload.** Call `DatabaseDescriptor.daemonInitialization()` (or `DatabaseDescriptor.daemonInitialization(() -> cfg)` with a prepared `Config`) in a fresh JVM per case. Then write data into the configured directory, for example create a 2 GiB file with `fallocate`, and repeat the check in a new JVM. Arithmetic: a 1 GiB tmpfs gives 1 GiB < 64 GiB, so the WARN is expected. Two 40 GiB volumes give a sum of 80 GiB, so no WARN even though each is below 64 GiB. One 1 GiB volume plus one 100 GiB volume gives no WARN, which shows the sum hides the small volume.

**B2d. Observables and instruments.** Captured WARN events whose message starts with "Only ... free across all data volumes"; the formatted number in it; `df -B1` for the expected value; the JVM exit code and whether `daemonInitialization` returns normally. Not observable here: any effect on a later write path (it does not exist in this class).

**B2e. Procedure.**
1. Build the copy; create the test.
2. For each case in B2c, make the filesystems (`mount -t tmpfs -o size=1G tmpfs $WORK/small` or a loop device; needs no shared storage), write `test.yaml` listing the directories, and run the test.
3. Record the WARN count, its text and `df -B1 --output=avail` of each volume.
4. Fill the file system until it is 100% full, then run again to confirm that initialization still returns normally with only the WARN.
5. Unmount, delete `$WORK`.

**B2f. Predictions.** Case 1 volume with 1 GiB free: exactly one WARN, text "Only ~1 GiB free across all data volumes", initialization returns. Case 2 x 40 GiB: no WARN. Case 1 GiB plus 100 GiB: no WARN. Case with 63.9 GiB free: WARN; with 64.1 GiB: no WARN (boundary is strict `<`). The number printed equals the sum of `df` avail values within the filesystem's reserved-block rounding. Initialization never fails because of the value. The claim is wrong if initialization throws or refuses to start solely because free space is below 64 GiB, or if any non-log effect (a changed `Config` field) appears.

**B2g. Readings.**

| Observation | Meaning |
|---|---|
| WARN only, startup completes, `Config` unchanged, below and above 64 GiB | Claim confirmed: the threshold is advisory. |
| WARN count 0 with 1 GiB free | Check not reached or log capture broken; not confirmed, fix the capture. |
| Startup throws when free < 64 GiB (and no other cause) | Claim wrong: the threshold gates startup. |
| Reading is an exact sum of all volumes and hides one small volume | Confirms A3 on the overshoot path. |
| Positive control (see B2h) moves the operand while the threshold does not change behaviour | Confirms the "usage flat" side. |
| Limit never reached (free space always above 64 GiB) | Not confirmed; use a smaller filesystem. |

**B2h. Controls.** Positive control: an enforced disk cap on the same harness, for example `commitlog_total_space` set to a small value, and a write of more than that amount through `CommitLog`. It shows archiving or flushing activity, which is where a cap binds. Also run the identical write with the free-space volume above and below 64 GiB to show no difference. A control JVM with the same yaml minus `data_file_directories` rules out default-directory effects.

### B3. Cluster tier

**B3a. Environment and build.** One node, JDK 11, built from a local copy (`ant jar`), with `cassandra.storagedir=$WORK/node`. Data, commit log, hints and saved caches on a dedicated local loop-device filesystem of known size (4 GiB, ext4), mounted at `$WORK/node`, so filling it is safe. Heap capped at `-Xms1G -Xmx1G`. `auto_snapshot: false`, `commitlog_total_space: 256MiB`, `disk_failure_policy: stop` (default), and `data_disk_usage_max_disk_size` left unset.

**B3b. Knobs.** Free space at startup: 4 GiB (below 64 GiB) versus a second run on a volume with more than 64 GiB free if available (otherwise a second case is a large sparse loop device, which reports its nominal size to `getUnallocatedSpace`). No yaml or property controls the threshold.

**B3c. Workload.** `cassandra-stress write n=6000000 -col size=FIXED(200) n=FIXED(5) -rate threads=32` (about 6 GB logical at RF 1; arithmetic: 6e6 rows x 5 cols x 200 B = 6 GB > 4 GiB volume) from the same host. Duration: until the volume is near full or a failure policy triggers, 20 to 40 minutes.

**B3d. Observables and instruments.** `system.log` (the WARN line at startup and its value); `df -B1 $WORK/node` every 10 s; `du -sb` of the data directory; `nodetool tablestats`; any `disk_failure_policy` or "no space left" errors; JVM exit status.

**B3e. Procedure.**
1. Create and mount the 4 GiB loop filesystem; copy the build; start the node with the yaml above.
2. `grep "free across all data volumes" system.log` and confirm the WARN.
3. Run the stress workload; sample `df` and `du`.
4. Observe growth until the volume fills or the node reacts.
5. `nodetool drain`; stop the node (`kill`, verify with `pgrep -f CassandraDaemon`); unmount and delete the loop file.
6. Optional second run on a >64 GiB volume to compare growth.

**B3f. Predictions.** At startup the log shows one WARN with about 4 GiB. Writes proceed normally after it, with data directory size growing with ingested data until compaction and the 4 GiB limit dominate. Growth rate and total in the two volume cases are the same within normal noise (compaction timing). The WARN does not appear in the large-volume case. The claim is wrong if writes are refused or throttled at the start only because the threshold was crossed, or if the node refuses to start.

**B3g. Readings.**

| Observation | Meaning |
|---|---|
| WARN at start, writes accepted, disk grows to the volume limit | Claim confirmed: the threshold does not cap usage. |
| Node refuses to start or reject writes because of the 64 GiB value | Claim refuted. |
| No WARN on the 4 GiB volume | Check not reached (wrong directory or log level); not confirmed. |
| Growth identical on the small and large volumes | Confirms no effect from the threshold. |
| Positive control (B3h) stops growth where its cap binds, while the threshold run grows | Confirms usage tracks real caps and not this constant. |
| Volume never fills (workload too small) | Not confirmed; increase `n`. |

**B3h. Controls.** Positive control: the same workload with `commitlog_total_space: 64MiB`; the commit log directory size stays near that value while data directory growth is unaffected, showing a cap that binds. Also compare against a run with `data_file_directories` split across two directories to show the summing behaviour (WARN absent if the sum reaches 64 GiB).

**B4. Risks and cleanup.** Never fill shared storage: all data stays on the loop filesystem of known size under local disk (`$WORK`). Filling it to 100% is intentional only there. Stop the node and any `cassandra-stress` (`pgrep -f 'CassandraDaemon|stress'` must be empty), unmount tmpfs and loop mounts (`mount | grep $WORK` empty), delete `$WORK`, and confirm the shared source tree is unchanged (`git status` clean or checksum compare).

## C. Sources read

- `/users/jason92/writeup-A/playbook-autonomous.md`
- `/users/jason92/writeup-A/_TEMPLATE-autonomous.md`
- `src/java/org/apache/cassandra/config/DatabaseDescriptor.java` (lines 690-760, 1134-1150, 1654-1664, plus grep of imports and method names)
- `src/java/org/apache/cassandra/utils/FBUtilities.java` (lines 924-938)
- `src/java/org/apache/cassandra/io/util/FileUtils.java` (grep for `ONE_GIB`)
- `conf/cassandra.yaml` (grep for `data_file_directories`)

## D. Stage-4 feedback

2026-10-26, stage 4 ([results](../../stage4-runtime-verification/results/data-free-space-warn-threshold--autonomous.md)): unit **Confirmed** (WARN only at 1 GiB, 63.9 GiB and 0 B free; none at 64.1 GiB and 100 GiB; startup always completes; Config identical) and cluster **Confirmed** (WARN once at start on the 4 GiB volume, none on 100 GiB; 3.5 GiB of data reached after 30.08 s on 4 GiB, 30.10 s on 100 GiB; the 4 GiB volume then filled; the `commitlog_total_space: 64MiB` control bound at 96 MiB against 224 MiB) — effect: does not cap; outcome class true negative. Noted: free space of several volumes is summed (1 GiB + 100 GiB gives no WARN); on a full tmpfs the JVM died with SIGBUS. Estimate unchanged. The dated amendments below were made at the stage-4 audit.

**Amendments, 2026-10-26 (stage-4 audit, before run 1; none touches B2f, B2g, B3f or B3g, and none depends on a reading).** Citations spot-checked against the pinned tree: `:726` (`dataFreeBytes < 64 * ONE_GIB`), `:709-725`, `:1654-1664`, `FileUtils.java:77`, `FBUtilities.prettyPrintMemory` are correct; `applySimpleConfig` is declared at `:478` and called at `:455` (inside `applyAll`, declared `:447`) and `:307`; `daemonInitialization` is declared at `:245` and calls `applyAll()` at `:263`. `PathUtils.tryGetSpace` maps a negative size to `Long.MAX_VALUE`.
1. *B2a (unit runner).* `ant testsome` forks one JVM per test class, but B2c needs a fresh JVM per case. The test class `DataFreeSpaceWarnTest` is compiled by `ant build-test` and each case is run as its own JVM with `java org.junit.runner.JUnitCore` on the build classpath (cases chosen by `-Dstage4.case=`). Volumes are tmpfs mounts of exact size (`sudo mount -t tmpfs -o size=<bytes>`), mounted under the work dir. The 63.9 / 64.1 GiB cases use sizes of 65433 MiB (63.9 GiB) and 65639 MiB (64.1 GiB) respectively; tmpfs free equals size when empty (the test prints the `FileStore.getUnallocatedSpace` value it compares against).
2. *B2h (unit positive control).* A `CommitLog` write is too heavy for a bare `DatabaseDescriptor` JVM. The positive control is instead `Directories.getWriteableLocation(bytes)` on the same 1 GiB tmpfs: a request larger than the free space (enforced disk guard, a closed Confirmed case) throws `FSWriteError`, a request below it returns a directory; it is run in the same JVM, and with the volume above and below 64 GiB, to show that its binding follows the free space of the volume while the 64 GiB WARN threshold changes nothing.
3. *B3a / B3b (cluster volumes).* The ext4 loop device is replaced by a tmpfs of exact size (the stage-4 lesson: a local node on a spinning disk stalls; a full tmpfs gives the same `ENOSPC`). The small volume is 4 GiB; the large volume is a tmpfs of nominal size 100 GiB (free space reported as 100 GiB, RAM is used only for written data). The node runs on loopback 127.0.3.1, heap `-Xms1G -Xmx1G`.
4. *B3c (stop conditions).* Stress runs until it ends or for at most 15 minutes; sampling every 5 s (`df -B1`, `du -sb` of data and of `commitlog`). The workload is the same on both volumes (same `n`), so growth is compared at equal elapsed rows, not at volume-full.
5. *B3h (cluster positive control).* The control (`commitlog_total_space: 64MiB`) runs on the 100 GiB volume, so that only the cap differs from the large-volume arm. The two-directory summing comparison is covered by the unit tier (B2c) and is not repeated at the cluster tier.
