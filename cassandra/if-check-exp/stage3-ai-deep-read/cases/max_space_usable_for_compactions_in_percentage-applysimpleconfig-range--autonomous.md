# max_space_usable_for_compactions_in_percentage range validation — verification solution  <!-- file: cases/max_space_usable_for_compactions_in_percentage-applysimpleconfig-range--autonomous.md -->

| Field | Value |
|---|---|
| Entry pointer | [`DatabaseDescriptor.java:1016`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/DatabaseDescriptor.java#L1016) |
| Pinned source | `cassandra-5.0.9` |
| Session / date | Claude Sonnet 5.5, Claude Code CLI, 2026-10-27 |
| Estimate | `negative`: the check is a startup range validation (`< 0 \|\| > 1`) that stores nothing and bounds no memory or disk object itself; the option it validates is a separate, real disk cap applied elsewhere (A2). |
| Ground | The check only accepts or rejects the yaml value; it never sizes or limits any held object. Disk used by compaction is bounded downstream by `Directories.getAvailableSpaceForCompactions`, which is a different statement. |

**Type:** non-config (hard-coded constant): the compared yaml entry `max_space_usable_for_compactions_in_percentage` is checked against the numeric literals `0` and `1` (constant rule, widened: a numeric literal counts). Both a yaml entry and literals take part.

## A. Constraint trace

**A1. The constraint.** Operands of the check at [`DatabaseDescriptor.java:1016`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/DatabaseDescriptor.java#L1016): (a) yaml entry `max_space_usable_for_compactions_in_percentage`, declared at [`Config.java:344`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/Config.java#L344) (`public volatile Double ... = .95`), unit: fraction of free disk, default 0.95 (literal in the field initializer; comment at Config.java:343 says "fraction of free disk space available for compaction after min free space is subtracted"); (b) the literals `0` and `1` in the comparison (no named constant). Settable in cassandra.yaml (restart) and at runtime through `DatabaseDescriptor.setMaxSpaceForCompactionsPerDrive` (DatabaseDescriptor.java:2584-2587), which does NOT re-run the range check. No entry in conf/cassandra.yaml (grep over conf/ found none).

**A2. What it caps.** The check itself caps nothing: it rejects values outside [0, 1]. The validated option feeds the disk-space admission test: usable bytes on a FileStore (minus `min_free_space_per_drive`) times the fraction is the disk budget for compactions and streams (Directories.java:563-569). So the option caps disk (other: admission, not an enforced quota), but the statement under test only bounds the option's own legal range.

**A3. Mechanism.** Enclosing method: `DatabaseDescriptor.applySimpleConfig()` (config load, runs once at startup; the `if` at [`DatabaseDescriptor.java:1016`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/DatabaseDescriptor.java#L1016)). True outcome: throws `ConfigurationException` (line 1017), node refuses to start. False outcome: falls through to the heap-dump check (line 1019) and the rest of config application. Downstream use: `getMaxSpaceForCompactionsPerDrive()` (DatabaseDescriptor.java:2579-2582) is read only in `Directories.getAvailableSpaceForCompactions` (Directories.java:563-569: `max(0, round((usable - minFree) * fraction))`), called from `hasDiskSpaceForCompactionsAndStreams` (Directories.java:545-559), whose callers are `CompactionTask.java:412` and `StreamSession.java:937`. Bypass: the runtime setter (2584) skips validation, so an out-of-range value could be set via code; no JMX/nodetool caller was found in src/java (grep). Values in range pass through unchanged; 0 yields a zero budget (compactions refused), 1 uses all usable space above min free.

**A4. Other consumers.** Disk is also used by flushes, commit log, hints, snapshots, and by compaction/streaming already running; none consult this fraction. Line 783 of Directories.java (`getMinFreeSpacePerDriveInBytes`) is a separate floor.

**A5. Evidence beyond the source.** Tests reading the getter: `test/unit/org/apache/cassandra/db/DirectoriesTest.java:905,980,1048`, `test/unit/.../compaction/PartialCompactionsTest.java:222`. No docs under `doc/` mention the option. History not consulted.

## B. Verification solution

**B1. Claim under test.** The range check at line 1016 does not cap memory or disk usage: it only validates the yaml value, and node disk usage is independent of whether the check exists; values inside [0,1] are accepted unchanged, outside are rejected before any resource is allocated.

### B2. Unit tier

**B2a. Environment and build.** JDK 11, Ant, in a private copy of the tag (`ant jar` there; not in the shared tree). Test source: a new JUnit class under the copy's `test/unit/org/apache/cassandra/config/`, run with `ant testsome -Dtest.name=<Class>`; defaults for JVM options.

> **Amendment U1 (2026-10-27, stage-4 audit).** The unit tier is a plain probe program, not a JUnit class: `MaxSpaceRangeProbe` (harness folder), compiled against `build/classes/main` of a local clone built with `ant build-test`, run in **one fresh JVM per value** with `-Dcassandra.config=<yaml>` and calling the real `DatabaseDescriptor.daemonInitialization()` (so the real `applySimpleConfig()` check at line 1016 and the yaml loader run). Reason: `daemonInitialization` runs once per JVM, and a yaml value exercises the true startup path. The positive control is the closed unit test `MaxCompactionSpaceOperandTest` (harness of the closed case `max_space_usable_for_compactions_in_percentage-hasDiskSpaceForCompactionsAndStreams-availableForCompaction--autonomous`, Confirmed 2026-10-19), re-run unchanged in the same clone, plus upstream `DirectoriesTest` as the known answer of the build.

**B2b. Knobs.** `max_space_usable_for_compactions_in_percentage` in a Config object passed to `DatabaseDescriptor.daemonInitialization(() -> conf)`: values -0.01, 0, 0.5, 0.95, 1, 1.01 (boundaries and just outside). Positive control knob: same value fed to `Directories.getAvailableSpaceForCompactions` through the setter.

> **Amendment U2 (2026-10-27).** Values are written to a yaml file (the shipped `conf/cassandra.yaml` plus directory lines plus `max_space_usable_for_compactions_in_percentage: <v>`), not to a `Config` object; a seventh run has no entry (default 0.95). Every value is run **twice** (B2h drift). In the probe the accepted values reach `Directories.getAvailableSpaceForCompactions` on the real `FileStore` of the data directory (not the `FakeFileStore`), so the positive control also runs on the yaml path.

**B2c. Workload.** One initialization per value (each in a fresh JVM or after `DatabaseDescriptor.clientInitialization` reset, as the test base class allows); then for accepted values call `getAvailableSpaceForCompactions(fileStore)` on a FileStore of the temp dir.

> **Amendment U3 (2026-10-27).** "Usage figures" in this tier are: (a) heap used after `System.gc()` x3 after the initialization (the probe prints it before and after), (b) `FileStore.getUsableSpace()` of the data directory read before and after the budget call. For every accepted value, (a) must not depend on the value (spread across the accepted values < 8 MiB) and (b) must not move by more than 4 MiB between the two reads (drift). The probe also calls the real gate `hasDiskSpaceForCompactionsAndStreams` at budget - 1 and budget + 1, and the setter with 1.5 and -0.25 (step 4).

**B2d. Observables and instruments.** Whether `ConfigurationException` with the message at line 1017 is thrown; `getMaxSpaceForCompactionsPerDrive()`; returned bytes of `getAvailableSpaceForCompactions`; `FileStore.getUsableSpace()` at call time. Heap/disk use of the check itself cannot be observed (it is a comparison).

**B2e. Procedure.** 1) Write the test; 2) loop over the six values, record exception or accepted value; 3) for accepted values compute expected `(usable - minFree) * v` and compare to returned bytes; 4) call the setter with 1.5 and observe no exception (bypass).

**B2f. Predictions.** -0.01 and 1.01 throw; 0, 0.5, 0.95, 1 are accepted and the getter returns them exactly. Returned bytes equal `round((usable-minFree)*v)` within filesystem drift between the two reads; 0 yields 0. The setter accepts 1.5.

> **Amendment U4 (2026-10-27), detail only, no change of claim.** The thrown type is `ConfigurationException` with the message `max_space_usable_for_compactions_in_percentage must be between 0 and 1` (line 1017). With no yaml entry the getter returns 0.95. The gate returns true at budget - 1 and false at budget + 1 for every accepted value with budget > 0. The setter also accepts -0.25 and the budget is then 0 (the `Math.max(0, ...)` clamp at `Directories.java:568`). The setter's 1.5 gives a budget of 1.5 x (usable - minFree), above the usable space.

**B2g. Readings.**

| Observation | Meaning |
|---|---|
| Out-of-range throws, in-range accepted, no allocation difference | Claim confirmed: check is validation only |
| Bytes returned scale with v (positive control moves) while the check's accept/reject sets no size | Claim confirmed: cap lives in Directories, not at line 1016 |
| Check changes any usage figure for accepted values | Claim refuted |
| Accepted values never reach `getAvailableSpaceForCompactions`, or returned bytes do not move with v | Not confirmed (control did not move) |
| *(Amendment U5, 2026-10-27)* -0.01 or 1.01 is accepted at startup, or 0 / 1 is rejected | Not confirmed (the traced check is not what the file says; re-trace) |
| *(U5)* A usage figure of U3 depends on the accepted value | Claim refuted |

**B2h. Controls.** Same FileStore for all values; read `getUsableSpace` before and after; run twice to see drift.

> **Amendment U6 (2026-10-27).** Unit-tier verdict wording: all of B2f holds, the closed control passes, and no figure of U3 depends on the value: **Confirmed** (claim: the check is validation only). The knob, once accepted, sets a budget downstream; that is recorded as the positive control, not as a cap at line 1016.

### B3. Cluster tier

**B3a. Environment and build.** One node, JDK 11, private copy of the tag built with `ant jar`; small dedicated data directory on a loop-mounted or otherwise bounded filesystem (not shared storage), e.g. a 2 GiB filesystem.

> **Amendment C1 (2026-10-27).** The data directory is a 2 GiB ext4 filesystem (`mkfs.ext4 -m 0`, no reserved blocks) on a loop device mounted with `sudo` (the node has passwordless sudo), image on local `/`, fresh for every run. Commit log, hints, logs and caches are on local `/` under `~/s4b-mu`. Heap `MAX_HEAP_SIZE=2G`. Clone: `~/cassandra-run1` (`ant jar` is part of its `build-test`), unchanged.

**B3b. Knobs.** yaml `max_space_usable_for_compactions_in_percentage`: 0.95 (default), 0.10, 1.0, and an invalid 1.5 (startup test). Fixed: `min_free_space_per_drive: 50MiB`, STCS table.

**B3c. Workload.** Write about 600 MiB of SSTables (e.g. `cassandra-stress write n=...` with compression off) into one table so a major compaction needs about 600 MiB; free space then about 1.3 GiB. With 0.95 the budget is about 1.2 GiB (allowed); with 0.10 about 130 MiB (refused). Run `nodetool compact` once per setting after restart.

> **Amendment C2 (2026-10-27), workload made exact.** Load: `cassandra-stress write` into `ks.standard1` (`-schema keyspace=ks 'replication(factor=1)'`, default 5 columns, default LZ4, one node, RF 1) in **four chunks of 760,000 distinct keys** (`-pop seq=a..b`), `nodetool flush ks standard1` after each chunk, with `nodetool disableautocompaction ks standard1` before the first chunk and `autocompaction_on_startup_enabled: false` in the yaml. Check after the load: exactly four Data.db files, **each >= 160 MiB** (otherwise the seed is invalid and is rebuilt with a larger chunk). Total about 0.65 to 0.7 GiB. Free space is then about 1.2 to 1.3 GiB, so the budget is `(free - 50 MiB) x pct` (`Directories.java:563-569`; the same formula the closed case found): about 1.1 to 1.2 GiB at 0.95, about 1.2 to 1.3 GiB at 1.0, about 0.12 GiB at 0.10, which is below every single sstable. The original text's "about 600 MiB" and "about 130 MiB" are replaced by these figures.

> **Amendment C2a (2026-10-27, runbook defect D1, cluster seed only; found before any cluster reading).** At the 2 GiB heap a memtable flushes about every 38 MB of Data.db (the first seed attempt gave 20 sstables of 16 to 39 MB, not four), so one chunk does not make one sstable. The seed node is therefore started with `MAX_HEAP_SIZE=12G`, `memtable_heap_space: 6144MiB` and `memtable_offheap_space: 6144MiB` (one 760,000-row chunk is about 185 MB of Data.db, so one flush per chunk). The measured nodes (all `run-<pct>` labels) keep `MAX_HEAP_SIZE=2G` and default memtable settings; they only read and compact the restored sstables. The C2 arithmetic is unchanged. The unit tier ran under the file version before this amendment; B2 is byte-identical.
>
> **Amendment C3 (2026-10-27).** The data is built once (the `seed` label), copied to local disk, and restored by `cp -a` onto a fresh filesystem before each setting, so every setting starts from the same four sstables. Settings run in the order 0.95, 0.10, 1.0, each with a node restart; the invalid value 1.5 is a separate start on an empty filesystem. The yaml carries `min_free_space_per_drive: 50MiB` and `max_space_usable_for_compactions_in_percentage: <v>`.

**B3d. Observables and instruments.** Node start result (log or exit) for 1.5; `df` on the data filesystem sampled every second during compaction; system.log "has only ... available, but ... is needed" warnings (Directories.java:552); `nodetool compactionstats`.

**B3e. Procedure.** 1) Start with 1.5: expect failure with the line-1017 message. 2) Start with 0.95, load data, `nodetool compact`, record peak `df` usage. 3) Wipe compacted state or reload, repeat with 0.10 and 1.0. 4) Stop the node, unmount and delete the test filesystem.

**B3f. Predictions.** 1.5: node fails to start, message "must be between 0 and 1". 0.95 and 1.0: compaction runs, peak disk about 2x the table size. 0.10: compaction refused with the warning, disk flat. Memory is unaffected by the setting.

> **Amendment C4 (2026-10-27), numbers for the prediction (no change of claim).** 0.95 and 1.0: `nodetool compact` returns 0, the four sstables become one, no `has only ... available` WARN, and the filesystem's used bytes rise during the compaction by 0.7 to 1.2 times the sum of the four Data.db sizes ("about 2x the table size" peak: used at rest plus the new output; the inputs are deleted at the end). 0.10: every sstable is larger than the budget, so `CompactionTask` (lines 395-440) drops the largest sstable repeatedly (`Not enough space for compaction ..., Reducing scope`, a WARN) until one is left and then throws `Not enough space for compaction (...)` (WARN, line 435): `nodetool compact` reports an error, the sstable count stays 4, the `has only ... available, but ... is needed` WARN appears, and the filesystem's used bytes rise by less than 16 MiB during the window. At rest, before any compaction, for every accepted setting: data-directory bytes (`du -sb`) differ by less than 8 MiB across settings, and heap used after a forced GC (`jcmd GC.run`, `GC.heap_info`) differs by less than 32 MiB.

**B3g. Readings.**

| Observation | Meaning |
|---|---|
| 1.5 rejected at startup; in-range values change only compaction admission, not disk at rest | Claim confirmed: line 1016 is validation, the downstream use is the cap |
| Positive control: 0.10 blocks the compaction that 0.95 allows | The downstream cap binds (control moved) |
| Disk or heap at rest differ between in-range settings before any compaction | Claim refuted |
| 0.10 does not block compaction, or the compaction never needs more than the budget | Not confirmed (limit never reached) |
| *(Amendment C5, 2026-10-27)* 0.95 or 1.0 also reduces scope or is refused (the budget arithmetic did not leave room) | Not confirmed (the control cannot separate the settings; the workload is amended and the tier restarted if this is a runbook defect) |
| *(C5)* 1.5 starts the node, or 0.95 / 1.0 fails to start | Not confirmed (the traced check is not what the file says) |

**B3h. Controls.** Same data set and filesystem state per run; same JVM options; restart between settings; check no background compaction before the manual one.

> **Amendment C6 (2026-10-27).** Verdict wording for the cluster tier: 1.5 refused at startup with the line-1017 message, no at-rest figure differs between the accepted settings, and the positive control moves (0.10 refuses what 0.95 and 1.0 admit): **Confirmed - does not cap** (the range check; the downstream admission test is the soft cap, as the claim says). The tier cannot say anything about memory beyond the at-rest heap reading.

**B4. Risks and cleanup.** Use only the private loop filesystem; never fill shared storage; stop the Cassandra process and cassandra-stress, check with `pgrep -f cassandra`; remove data and unmount the loop device.

## C. Sources read

- src/java/org/apache/cassandra/config/DatabaseDescriptor.java (lines 985-1050, 2565-2590)
- src/java/org/apache/cassandra/config/Config.java (338-346)
- src/java/org/apache/cassandra/db/Directories.java (517-600)
- grep results over src/java, conf, test/unit, doc

## D. Stage-4 feedback

**Stage-4 result (2026-10-27, run on `pc32`, repository `6e6cf92`; results `stage4-runtime-verification/results/max_space_usable_for_compactions_in_percentage-applysimpleconfig-range--autonomous.md`).**

- **Verdict:** unit **Confirmed - does not cap**; cluster **Confirmed - does not cap**. Outcome class: **true negative** (estimate `negative`, effect `does not cap`). No run 2.
- **What was measured.** Unit: a probe program, one fresh JVM per yaml value, through the real `DatabaseDescriptor.daemonInitialization()`: -0.01 and 1.01 throw `ConfigurationException` with the line-1017 message; 0, 0.5, 0.95, 1 and no entry are accepted and read back exactly; the real `Directories.getAvailableSpaceForCompactions` returns `round((usable - minFree) x v)` to the byte for each accepted value; heap after init (spread 20 kB) and usable space do not depend on v; the runtime setter stores 1.5 (budget 1.5 x usable) and -0.25 (budget 0) with no check. Positive control: the closed `MaxCompactionSpaceOperandTest` re-run, 56 OK. Cluster: 1.5 refused at startup in 3 s with the same message; on identical data (four sstables of 165 MiB, 2 GiB ext4) 0.95 and 1.0 compacted 4 -> 1 (disk rise 754 MB = 1.09 x the table) and 0.10 (budget 122 MB, below every sstable) refused it (rc 2, 4 `has only 116.36 MiB available, but 661.05 MiB is needed` WARNs, sstables unchanged, rise 0); at-rest used / du / heap equal across settings.
- **Amendments (all dated 2026-10-27, next to the text they change):** U1-U6 (the unit tier as a probe per yaml value plus the closed control; usage figures; extra rows), C1-C6 (ext4 loop with sudo; four sstables >= 160 MiB; restore per setting; thresholds for the prediction; extra rows) and C2a (runbook defect D1: the seed node needs big memtable pools, or a 2 GiB heap flushes every ~38 MB). Frozen sha256 `f4ddda282549c6ffb42ab8e4d0a0793e9d86323ad00daaad61d3ebc41c32c90e`; the unit tier ran under `e91dabc4471331ddc373dc30a9408a77c6396ed616f36330e6dc70ca3f1b211e`, whose B2 text is identical.
- **Notes for stage 3.** (1) B3c's "free space about 1.3 GiB, budget about 130 MiB at 0.10" only holds if every sstable is larger than the budget; the reduce-scope loop in `CompactionTask.java:395-440` otherwise compacts a subset instead of refusing (the closed `...--autonomous` case found the same). (2) The downstream admission test is per task and soft; this run does not bound the sum of simultaneous tasks. (3) The estimate stands as filed.
