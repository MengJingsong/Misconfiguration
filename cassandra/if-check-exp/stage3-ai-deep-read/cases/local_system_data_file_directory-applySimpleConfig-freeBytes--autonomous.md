# ONE_GIB free-space warning on local_system_data_file_directory — verification solution  <!-- file: cases/local_system_data_file_directory-applySimpleConfig-freeBytes--autonomous.md -->

| Field | Value |
|---|---|
| Entry pointer | `src/java/org/apache/cassandra/config/DatabaseDescriptor.java:741` |
| Pinned source | `cassandra-5.0.9` |
| Session / date | Claude Sonnet 5.5, Claude Code CLI (Agent SDK), 2026-10-26 |
| Estimate | `negative`: line 741 only decides whether to emit a startup `logger.warn`; it neither limits nor reserves any disk or memory. |
| Ground | The comparison `freeBytes < ONE_GIB` is a hard-coded constant check on free space at startup (`DatabaseDescriptor.java:739-743`). Its only outcome is a log line. Nothing is rejected, throttled or deleted, and the check runs once in `applySimpleConfig`, so it cannot track later growth. Writes to the system data directory are limited separately (disk-usage guardrails, `min_free_space_per_drive`, OS ENOSPC). |

## A. Constraint trace

**A1. The constraint.** `ONE_GIB` as a free-space warning threshold for the optional `local_system_data_file_directory`. Kind: constant (threshold) compared against a runtime-queried value (`FileStore.getUnallocatedSpace`). `ONE_GIB` is declared at `src/java/org/apache/cassandra/io/util/FileUtils.java:77` (`1024 * ONE_MIB`), imported at `DatabaseDescriptor.java:143`. Unit: bytes. Default and derivation: 1073741824, fixed in code. Not settable by yaml, `-D` or JMX; changing it needs a source edit and rebuild. The directory it applies to is set by yaml key `local_system_data_file_directory` (`Config.java:383`; commented out in `conf/cassandra.yaml:403`, so null by default and the whole block at 730-744 is skipped); a change needs a restart.

**A2. What it caps.** Nothing. The resource it observes is disk (unallocated bytes on the file store holding the local system keyspaces). The compared quantity is `freeBytes = tryGetSpace(conf.local_system_data_file_directory, FileStore::getUnallocatedSpace)` (`:739`). The sibling check for data directories uses 64 GiB over the saturated sum (`:726`).

**A3. Mechanism.**
1. `applySimpleConfig` runs from `applyAll` (`:447`, called by `daemonInitialization` at `:263`).
   > **Amendment 2026-10-26 (stage-4 audit R1):** `:447` is the definition of `applyAll`; it calls `applySimpleConfig()` at `:455` (`toolInitialization` also calls it, `:307`). The mechanism is unchanged.
2. If `local_system_data_file_directory` is non-null (`:730`), it is checked for equality with commitlog, saved_caches and hints directories (`:732-737`); a match throws `ConfigurationException`. These checks are about directory layout, not size.
3. `tryGetSpace` (`:1661-1664`) calls `PathUtils.tryGetSpace` (`io/util/PathUtils.java:809-812`), which maps a negative (overflowed) size to `Long.MAX_VALUE` (`:819-822`), and throws `ConfigurationException` if the file store cannot be read.
4. `if (freeBytes < ONE_GIB)` (`:741`) then `logger.warn("Only {} free in the system data volume...")` (`:742-743`). If not below, nothing happens.
Bypass/overshoot: the check is a single sample at startup. The system data directory can fill to 100% afterward with no further effect from this line. If the directory is unset, the check never runs.

**A4. Other consumers.** Local system keyspaces (system, system_schema, etc.) written to that directory (`getLocalSystemKeyspacesDataFileLocations`, `DatabaseDescriptor.java:2743-2777`); snapshots, backups and any other process on the same volume; the startup warning for ordinary data directories (`:726`); runtime space gating in `Directories.java:566,783` (uses `getUsableSpace` minus `getMinFreeSpacePerDriveInBytes`) and the `DiskUsageMonitor` (`service/disk/usage/DiskUsageMonitor.java:251`).

**A5. Evidence beyond the source.** none (conf/cassandra.yaml comment at line 400-403 read for the key's purpose).

## B. Verification solution

**B1. Claim under test.** Because line 741 only logs, disk usage in the system data directory does not follow `ONE_GIB`: with free space below 1 GiB the node still starts, accepts writes into the volume and does not stop or shed data because of this check, and the warning is emitted only at startup. (Claim of "not capping"; refuted if startup fails, or writes are refused or throttled specifically at the 1 GiB boundary.)

### B2. Unit tier

**B2a. Environment and build.** JDK 11, Ant. Copy the tree to local disk (`cp -r ~/cassandra-5.0.9 /local/c509-unit`), `cd /local/c509-unit && ant jar` (or `ant build-test`). Test class in the copy only: `test/unit/org/apache/cassandra/config/SystemDirFreeSpaceWarnTest.java`. JVM options: the test defaults (`-Dcassandra.config=file:///.../test/conf/cassandra.yaml`). Run `ant testsome -Dtest.name=SystemDirFreeSpaceWarnTest`.

> **Amendment 2026-10-26 (stage-4 audit R2):** `~/cassandra-5.0.9` does not exist; the tree is made with `stage4-runtime-verification/copy-source.sh` (`~/s4-b8-ls-u`, `ant build-test`; node tree `~/s4-b8-ls-n`, `ant jar`). The test class lives in `harness/<stem>/` (package `org.apache.cassandra.config`) and each case runs in its own JVM via `javac` + `JUnitCore` (`-Dcassandra.config` = a copy of `test/conf/cassandra.yaml`). The sentence about a reflective copy in B2b is void: `sudo` works on the node, so every value is an exact-size tmpfs.

**B2b. Knobs.** Free space reported for the system data directory, with three values: 0.5 GiB, exactly 1 GiB, 1.5 GiB.

> **Amendment 2026-10-26 (stage-4 audit R3):** each value is a tmpfs mounted with `size=` 536870912 / 1073741824 / 1610612736 bytes and left empty (a directory on tmpfs uses no blocks), so `getUnallocatedSpace` equals the size; the test reads it independently with `FileStore.getUnallocatedSpace` and prints it. No filler file is needed in the unit tier.

Set with a tiny loop-mounted/tmpfs filesystem of the corresponding unallocated size (tmpfs `size=` mount with a filler file, needs root), or, without root, by calling the real `DatabaseDescriptor` with a `local_system_data_file_directory` on a small tmpfs under `/dev/shm`-style local mount. Fallback if no mount rights: bytecode-free simulation by invoking `FileUtils.ONE_GIB` comparison via a reflective copy is not allowed; instead test is `n/a` for the exact-boundary value and runs only with whatever real filesystems are available (state which).

**B2c. Workload.** Build a `Config` via `DatabaseDescriptor.daemonInitialization(() -> cfg)` where `cfg.local_system_data_file_directory` points to a directory on the sized filesystem, other directories on distinct paths. Fill the sized filesystem until unallocated = target (e.g. tmpfs 2 GiB, write a filler file of 2 GiB - target). Arithmetic: 0.5 GiB = 536870912 B, 1 GiB = 1073741824 B, 1.5 GiB = 1610612736 B; `freeBytes < 1073741824` is true only for the first (and false at exactly 1 GiB).

**B2d. Observables and instruments.** (1) Whether `daemonInitialization` throws; (2) presence of the `Only ... free in the system data volume` message, captured with a logback `ListAppender` on `org.apache.cassandra.config.DatabaseDescriptor`; (3) `df -B1 <dir>` / `Files.getFileStore(p).getUnallocatedSpace()` before and after to record the operand. Not observable: what happens to the node afterward (that is B3).

> **Amendment 2026-10-26 (stage-4 audit R4):** `data_file_directories` of the test yaml are on local disk with less than 64 GiB free, so the sibling WARN `Only ... free across all data volumes` (`:726`) also fires. Only messages containing `free in the system data volume` are counted. In addition the test reads, after initialization, `DataDirectory(sysdata).getAvailableSpace()` and calls `Directories.getWriteableLocation(r)` for a 300 MiB request (and a request of twice the available space) on that directory: this is the runtime space check that does bind (`Directories.java:566`, `:783`), used to show that admission below the 1 GiB line follows real free space, not the constant.

**B2e. Procedure.**
1. Mount tmpfs at `/local/mnt/sysdata` with size 2 GiB; create filler so unallocated = 0.5 GiB.
2. Run the test; record exception/no exception, warn count, `df` value.
3. Remove part of the filler to reach 1 GiB exactly; repeat; then 1.5 GiB; repeat.
4. Positive control (see B2h): set `commitlog_total_space` small and observe its enforcement in `AbstractCommitLogSegmentManager.unusedCapacity()` (`:445-451`) by writing mutations to a `CommitLog` in the same JVM.
   > **Amendment 2026-10-26 (stage-4 audit R5):** the control runs as its own two JVMs (not inside the sysdata test JVM) with the closed case's `CommitLogTotalSpaceCapTest` (harness copy): `commitlog_total_space` 32 MiB and an uncapped arm (100000 MiB), 300 x 1 MiB mutations, 10 ms apart, 5 MiB segments (test yaml). A control needs a contrast to "move": the capped arm's peak on-disk size is predicted at most 32 + 4 x 5 = 52 MiB, the uncapped arm's above 300 MiB, and `COMMITLOG_DIRTY` flushes occur in the capped arm and not in the uncapped one.
5. Unmount, delete `/local/c509-unit`.

**B2f. Predictions.**
- 0.5 GiB: initialization succeeds; exactly one `Only 512.000MiB free in the system data volume` style warning; no exception.
- 1 GiB: no warning (strict `<`); no exception.
- 1.5 GiB: no warning; no exception.
- Positive control: with `commitlog_total_space: 32MiB`, `unusedCapacity()` goes negative once the log exceeds 32 MiB and `maybeFlushToReclaim` (`:246-263`) flushes and recycles segments (amended 2026-10-26 R5: peak on-disk size at most 52 MiB in the capped arm, above 300 MiB uncapped).
- (Added 2026-10-26, R6, independent of any reading.) Runtime admission on the sysdata directory: at 0.5 GiB free the 300 MiB request returns the directory (below the 1 GiB line, so the constant does not gate it) and the twice-available request throws `FSDiskFullWriteError`; at 1.5 GiB both behave the same way.
Claim is wrong if initialization throws or any other action (not a log line) differs between the three free-space values.

**B2g. Readings.**

| Observation | Meaning |
|---|---|
| Warn at 0.5 GiB only; no exception at any value | Mechanism as traced; line 741 is warning-only |
| Exception or abort at 0.5 GiB | Claim refuted: check does more than log |
| Behaviour differs among values in anything but the warn line | Claim refuted |
| Usage (filler/system data) unaffected by knob while the commit log control stays near `commitlog_total_space` | Claim confirmed (usage flat while positive control moves) |
| No warn at 0.5 GiB, or filesystem sizes not achieved, or control commit log did not exceed 32 MiB | Not confirmed (limit not reached / control did not move) |
| (Added 2026-10-26, R6.) A warn at exactly 1 GiB or 1.5 GiB, or a warn in the unset control | Not confirmed (the traced comparison is not as described); recorded in feedback |
| (Added 2026-10-26, R6.) "Usage unaffected" in this tier means: initialization outcome and every action other than the warn line identical across the three values, and the 300 MiB request admitted at 0.5 GiB; the Confirmed row above needs this, the warn at 0.5 GiB only, and the capped control peak <= 52 MiB against > 300 MiB uncapped | Confirmed |

**B2h. Controls.** Same JVM, same config with `local_system_data_file_directory` unset: no warn at any size (confirms the guard at `:730`). Positive control is the commit log cap described in B2e step 4, which is known to bind (`DatabaseDescriptor.java:664-675`, `AbstractCommitLogSegmentManager.java:445-451`).

### B3. Cluster tier

**B3a. Environment and build.** One node on Linux, JDK 11, Ant. Local copy: `cp -r ~/cassandra-5.0.9 /local/c509-node && cd /local/c509-node && ant jar`. Local disks of known size: a 3 GiB loop/tmpfs mount at `/local/mnt/sysdata` for `local_system_data_file_directory`; data, commitlog, hints, saved_caches on a separate local directory with at least 10 GiB free. `cassandra.yaml` changes: `local_system_data_file_directory: /local/mnt/sysdata/system`, other directories distinct and local, `commitlog_total_space: 64MiB` kept explicit for the control. JVM: default `-Xmx2G`.

> **Amendment 2026-10-26 (stage-4 audit R7):** the node tree is `~/s4-b8-ls-n` (copy-source.sh, `ant jar`); the sysdata volume is a 3 GiB tmpfs with a filler file (`fallocate`) leaving the target; data, commitlog, hints, saved_caches and the logs of every arm are on a separate 24 GiB tmpfs (the lesson from earlier cases: several writers on the spinning disk stall). Node address 127.0.6.1, JMX 7160, `ulimit -n 100000`, `-Xmx1G` for the sysdata arms (the load is small) and `MAX_HEAP_SIZE=8G` for the commit-log control arms.

**B3b. Knobs.** Free space on the sysdata mount at startup: 0.5 GiB, 1.5 GiB (filler file sets this). Set before each start; changing needs restart. A third run lets free space fall to near zero after startup (to show the check is startup-only).

**B3c. Workload.** `cassandra-stress write n=200000 -rate threads=16` (normal client path) against a user keyspace on the data directory; plus schema churn (create/drop 200 tables with `cqlsh`) to produce writes to system keyspaces (stored in the sysdata mount). Run 5 minutes per knob value.

> **Amendment 2026-10-26 (stage-4 audit R8):** the stress of `n=200000` writes about 40-60 MB of commit log, less than the 64 MiB cap, so it cannot test the control. The commit-log control is therefore its own pair of arms (no sysdata directory): `cassandra-stress write n=1000000 -col size=FIXED(1024) n=FIXED(1)` unthrottled, `commitlog_total_space` 64MiB (capped) and 16384MiB (uncapped), memtable limits raised (`memtable_heap_space 2048MiB`, `memtable_offheap_space 4096MiB`, `memtable_cleanup_threshold 0.9`, offheap_objects) so that memtable pressure does not flush first. The sysdata arms use the filed `n=200000` plus schema churn. Arithmetic: system keyspace writes are small (MiB-scale), so to drive the sysdata volume toward zero the filler is enlarged after startup to leave 100 MiB.

**B3d. Observables and instruments.** `grep "free in the system data volume" system.log`; `df -B1 /local/mnt/sysdata` every 5 s; `nodetool status`/`nodetool info`; `ls -l` sizes under the sysdata directory; `nodetool tablestats system_schema` for live disk space; commit log size for the control with `du -sb commitlog` every 5 s. Not observable: internal comparison; only its logged effect.

**B3e. Procedure.**
1. Create mounts; create filler leaving 0.5 GiB; start node (`bin/cassandra -f` from the local copy, output to a log).
2. Record presence/absence of the warn line, node state `UN`.
3. Run workload and schema churn; sample `df`, node state, log errors.
4. Stop node (`nodetool drain`, kill, check `pgrep -f CassandraDaemon` empty).
5. Repeat with 1.5 GiB free (expected no warn).
6. Repeat starting at 1.5 GiB and after startup grow filler to leave 100 MiB; keep running the schema churn.
7. Control run: commit-log pressure with `commitlog_total_space: 64MiB` and the stress write; sample `du -sb` of commitlog.
8. Clean up (B4).

**B3f. Predictions.**
- 0.5 GiB at start: node starts and reaches `UN`; one warn line at startup; stress writes succeed; no error attributable to the check.
- 1.5 GiB at start: no warn line; same behaviour.
- Post-startup shrink to 100 MiB: no new warn line, no mention of the 1 GiB check; any failure comes from the filesystem/disk-failure policy, not this line.
- Control: commit log directory size stays within about 64 MiB plus one segment (32 MiB default segment) under sustained writes (amended 2026-10-26 R8: peak at most 64 + 4 x 32 = 192 MiB, the overshoot bound the closed commitlog_total_space case audited, and below half of the uncapped arm's peak, which is predicted above 800 MiB).
Claim is wrong if the node refuses to start, stops accepting writes, or throttles at the 0.5 GiB start but not at 1.5 GiB.

**B3g. Readings.**

| Observation | Meaning |
|---|---|
| Warn at 0.5 GiB start only; same throughput and `UN` in both | Check is warn-only (claim confirmed) |
| Node fails to start or errors out only at 0.5 GiB | Claim refuted |
| Writes rejected/throttled at the 1 GiB boundary specifically | Claim refuted |
| New warn lines after startup when space shrinks | Check re-runs (trace wrong) |
| System data usage follows free space or the knob while the commit log control stays at its cap | Usage follows the constraint (refuted) |
| System data usage unaffected by knob while commit log control stays bounded by `commitlog_total_space` | Confirmed |
| Control commit log exceeds its cap by far, or free space never reached target | Not confirmed |
| (Added 2026-10-26, R8.) A warn at the 1.5 GiB start, or in the unset-directory control | Not confirmed (the traced comparison is not as described); recorded in feedback |
| (Added 2026-10-26, R8.) "Exceeds its cap by far" means capped peak > 192 MiB or >= 0.5 x the uncapped arm's peak; "control did not move" means the uncapped arm's peak is below 400 MiB | (definition of the two Not confirmed rows) |

**B3h. Controls.** Run with `local_system_data_file_directory` unset (default): no warn irrespective of data volume free space. Positive control: commit log under `commitlog_total_space`, known to bind (`AbstractCommitLogSegmentManager.java:445-451`). Same workload and hardware across knob values.

**B4. Risks and cleanup.** Disk: only local mounts of known size (3 GiB tmpfs/loop, 10 GiB data dir); never use shared storage or the shared source tree. Stop Cassandra and cassandra-stress, then `pgrep -fl 'CassandraDaemon|cassandra-stress'` must be empty (amended 2026-10-26 R9: match by `ps -eo pid,cmd | grep '[j]ava.*CassandraDaemon'` and kill by PID, because other cases run on the same host). Unmount `/local/mnt/sysdata`, remove filler files, `/local/c509-unit`, `/local/c509-node` and data directories. Mounting needs root; if unavailable use whatever small local filesystem is available and report the sizes used.

## C. Sources read

- `/users/jason92/writeup-A/playbook-autonomous.md`
- `/users/jason92/writeup-A/_TEMPLATE-autonomous.md`
- `src/java/org/apache/cassandra/config/DatabaseDescriptor.java` (lines 660-680, 700-789, greps of 1661, 2737-2777)
- `src/java/org/apache/cassandra/io/util/FileUtils.java` (line 77, by grep)
- `src/java/org/apache/cassandra/io/util/PathUtils.java` (lines 804-822)
- `src/java/org/apache/cassandra/db/commitlog/AbstractCommitLogSegmentManager.java` (lines 240-265, 445-456)
- `src/java/org/apache/cassandra/config/Config.java` (line 383, by grep)
- `conf/cassandra.yaml` (lines 400-403, 883, by grep)

## D. Stage-4 feedback

2026-10-26, results [`results/local_system_data_file_directory-applySimpleConfig-freeBytes--autonomous.md`](../../stage4-runtime-verification/results/local_system_data_file_directory-applySimpleConfig-freeBytes--autonomous.md). Design audit: Ready after amendments R1-R9 (dated notes in A3, B2a-B2g, B3a-B3g, B4; frozen file sha256 `1b976a2788744c307bb180af38098097ff267bf25b5a616c87e83160b4e97b82`). Run 1 and self-check, no run 2.

- **Unit: Confirmed, does not cap.** Exact-size tmpfs at 0.5 GiB, 1 GiB, 1.5 GiB and the directory unset: one WARN `Only 512.000MiB free in the system data volume` at 0.5 GiB only (also one page below 1 GiB; none at exactly 1 GiB: the comparison is strict); initialization, Config and the runtime admission outcomes identical across values; positive control (commit-log cap 32 MiB) 45.0 MiB capped vs 380.0 MiB uncapped.
- **Cluster: Confirmed, does not cap.** One node: the WARN once at the 0.5 GiB start, none at 1.5 GiB, none in the unset control, none after the volume was reduced to 100 MiB; `UN`, 2 x 200,000 stress writes (0 errors) and schema churn unchanged; positive control 128 MiB (cap 64 MiB) vs 1088 MiB uncapped.
- **Estimate vs effect:** `negative` vs `does not cap`: true negative. The trace (A3) held; the only correction was the citation `:447` (definition of `applyAll`; the call is `:455`).
- **Limit of the negative claim:** the system keyspaces wrote at most 0.3 MiB, so the volume was reduced by an external filler, not filled by Cassandra; what was shown is that nothing keyed to the 1 GiB line changed behaviour.
