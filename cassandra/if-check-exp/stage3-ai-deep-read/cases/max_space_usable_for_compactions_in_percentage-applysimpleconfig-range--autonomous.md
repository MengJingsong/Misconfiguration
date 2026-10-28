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

**B2b. Knobs.** `max_space_usable_for_compactions_in_percentage` in a Config object passed to `DatabaseDescriptor.daemonInitialization(() -> conf)`: values -0.01, 0, 0.5, 0.95, 1, 1.01 (boundaries and just outside). Positive control knob: same value fed to `Directories.getAvailableSpaceForCompactions` through the setter.

**B2c. Workload.** One initialization per value (each in a fresh JVM or after `DatabaseDescriptor.clientInitialization` reset, as the test base class allows); then for accepted values call `getAvailableSpaceForCompactions(fileStore)` on a FileStore of the temp dir.

**B2d. Observables and instruments.** Whether `ConfigurationException` with the message at line 1017 is thrown; `getMaxSpaceForCompactionsPerDrive()`; returned bytes of `getAvailableSpaceForCompactions`; `FileStore.getUsableSpace()` at call time. Heap/disk use of the check itself cannot be observed (it is a comparison).

**B2e. Procedure.** 1) Write the test; 2) loop over the six values, record exception or accepted value; 3) for accepted values compute expected `(usable - minFree) * v` and compare to returned bytes; 4) call the setter with 1.5 and observe no exception (bypass).

**B2f. Predictions.** -0.01 and 1.01 throw; 0, 0.5, 0.95, 1 are accepted and the getter returns them exactly. Returned bytes equal `round((usable-minFree)*v)` within filesystem drift between the two reads; 0 yields 0. The setter accepts 1.5.

**B2g. Readings.**

| Observation | Meaning |
|---|---|
| Out-of-range throws, in-range accepted, no allocation difference | Claim confirmed: check is validation only |
| Bytes returned scale with v (positive control moves) while the check's accept/reject sets no size | Claim confirmed: cap lives in Directories, not at line 1016 |
| Check changes any usage figure for accepted values | Claim refuted |
| Accepted values never reach `getAvailableSpaceForCompactions`, or returned bytes do not move with v | Not confirmed (control did not move) |

**B2h. Controls.** Same FileStore for all values; read `getUsableSpace` before and after; run twice to see drift.

### B3. Cluster tier

**B3a. Environment and build.** One node, JDK 11, private copy of the tag built with `ant jar`; small dedicated data directory on a loop-mounted or otherwise bounded filesystem (not shared storage), e.g. a 2 GiB filesystem.

**B3b. Knobs.** yaml `max_space_usable_for_compactions_in_percentage`: 0.95 (default), 0.10, 1.0, and an invalid 1.5 (startup test). Fixed: `min_free_space_per_drive: 50MiB`, STCS table.

**B3c. Workload.** Write about 600 MiB of SSTables (e.g. `cassandra-stress write n=...` with compression off) into one table so a major compaction needs about 600 MiB; free space then about 1.3 GiB. With 0.95 the budget is about 1.2 GiB (allowed); with 0.10 about 130 MiB (refused). Run `nodetool compact` once per setting after restart.

**B3d. Observables and instruments.** Node start result (log or exit) for 1.5; `df` on the data filesystem sampled every second during compaction; system.log "has only ... available, but ... is needed" warnings (Directories.java:552); `nodetool compactionstats`.

**B3e. Procedure.** 1) Start with 1.5: expect failure with the line-1017 message. 2) Start with 0.95, load data, `nodetool compact`, record peak `df` usage. 3) Wipe compacted state or reload, repeat with 0.10 and 1.0. 4) Stop the node, unmount and delete the test filesystem.

**B3f. Predictions.** 1.5: node fails to start, message "must be between 0 and 1". 0.95 and 1.0: compaction runs, peak disk about 2x the table size. 0.10: compaction refused with the warning, disk flat. Memory is unaffected by the setting.

**B3g. Readings.**

| Observation | Meaning |
|---|---|
| 1.5 rejected at startup; in-range values change only compaction admission, not disk at rest | Claim confirmed: line 1016 is validation, the downstream use is the cap |
| Positive control: 0.10 blocks the compaction that 0.95 allows | The downstream cap binds (control moved) |
| Disk or heap at rest differ between in-range settings before any compaction | Claim refuted |
| 0.10 does not block compaction, or the compaction never needs more than the budget | Not confirmed (limit never reached) |

**B3h. Controls.** Same data set and filesystem state per run; same JVM options; restart between settings; check no background compaction before the manual one.

**B4. Risks and cleanup.** Use only the private loop filesystem; never fill shared storage; stop the Cassandra process and cassandra-stress, check with `pgrep -f cassandra`; remove data and unmount the loop device.

## C. Sources read

- src/java/org/apache/cassandra/config/DatabaseDescriptor.java (lines 985-1050, 2565-2590)
- src/java/org/apache/cassandra/config/Config.java (338-346)
- src/java/org/apache/cassandra/db/Directories.java (517-600)
- grep results over src/java, conf, test/unit, doc

## D. Stage-4 feedback

`none yet`
