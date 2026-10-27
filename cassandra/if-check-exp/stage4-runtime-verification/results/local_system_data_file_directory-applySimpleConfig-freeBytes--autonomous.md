# local_system_data_file_directory-applySimpleConfig-freeBytes--autonomous — stage-4 results  <!-- file: results/local_system_data_file_directory-applySimpleConfig-freeBytes--autonomous.md; the stem ends in --guided or --autonomous -->

> **Case:** [`local_system_data_file_directory-applySimpleConfig-freeBytes--autonomous`](../../stage3-ai-deep-read/cases/local_system_data_file_directory-applySimpleConfig-freeBytes--autonomous.md)
>
> **Status:** verdict filed 2026-10-26 (run 1 + self-check; no run 2). Unit **Confirmed** — does not cap; cluster **Confirmed** — does not cap.
>
> **Outcome class:** true negative (estimate `negative`, effect `does not cap`)
>
> **Agent:** autonomous (the suffix of the case-file stem). For an autonomous
> file, "§9a" below means each tier's predictions and conclusions table: B2f and B2g
> (unit), B3f and B3g (cluster); "§9b–§9e" means B2a–B2e or B3a–B3e; and the case
> file's feedback section is its section D, not §10. One results file per case file.

**Relative links in this template** are written for where a *copy* of it lives
— inside `results/` — not for the template's own location one level up.

**Fill the sections in order.** The audit (§1), run 1 (§4) and the self-check
(§5) are required; run 2 (§6) and the comparison (§7) are filled only if §5.2
chooses run 2. No step waits for a human.
The protocol behind each section is in
[`../README.md`](../README.md#the-run-protocol).

## 1. Before run 1 — design audit and freeze

| Field | Content |
|---|---|
| **Case-file version** | AS-FILED sha256 `53ae25c8786ac917863a51e0678def10a560f6d9337210a05e948eefb5cdbed2`. After the audit's amendments R1-R9 (frozen version, 2026-10-26, before any harness run or reading; copy `~/s4-b8-ls-logs/case-file-frozen.md` on pc07): file sha256 **`1b976a2788744c307bb180af38098097ff267bf25b5a616c87e83160b4e97b82`**; sha256 of the prediction and conclusion tables (B2f-B2g and B3f-B3g text, from `**B2f. Predictions.**` to `**B2h. Controls.**` and `**B3f. Predictions.**` to `**B3h. Controls.**`, copy `~/s4-b8-ls-logs/tables-frozen.txt`) **`ac972a4d462e3989888ca58f8e0e3eb319fbb9bf6ec9ed09c8af8400b5911ccc`**. Repository HEAD at the audit: `93d6365` (case file and harness untracked; the orchestrator commits). |
| **Harness** | `harness/local_system_data_file_directory-applySimpleConfig-freeBytes--autonomous/` (not committed; see its README) |
| **Tiers and values** | Unit (B2): free space of `local_system_data_file_directory` = 536870912 / 1073741824 / 1610612736 B (exact tmpfs), unset control, runtime-admission probe, commit-log positive control (32 MiB cap vs uncapped). Cluster (B3): arms `A` (0.5 GiB at start), `B` (1.5 GiB at start), `C` (1.5 GiB then shrunk to 100 MiB after start), `D` (unset directory, control), `P` (commit-log cap 64 MiB) and `U` (uncapped 16384 MiB), one node, port slot 6. |
| **Audit bottom line** | **Ready after amendments**, 2026-10-26 |

### 1.1 Design audit

The requirements are in the README, "Step 0 — the design audit". One row per
line of each group; cite the case-file section checked.

| Group | Check | Rating (Met / Partly / Not met) | Note (section checked) |
|---|---|---|---|
| A. Core question | constrained quantity is memory or disk bytes | Met | A1/A2: unallocated bytes on the file store of the system data directory (disk) against the byte constant `ONE_GIB`. |
| A. Core question | knob varied, ≥ 3 values incl. default — or another approach, with the reason | Partly | The constant cannot be varied (A1); B2b/B3b instead vary the operand (free space) at 0.5 / 1.0 / 1.5 GiB (unit) and 0.5 / 1.5 GiB / shrink (cluster), with the unset directory as the default. Reason given; accepted. |
| A. Core question | real resource measured, not only the counter (gap named) | Met | B2d/B3d read `FileStore.getUnallocatedSpace`, `df -B1` and `du -sb` of the sysdata directory, independent of the check's operand. |
| A. Core question | usage driven to the limit and past it | Partly | B2c/B3c reach the line by exact tmpfs sizes. B3c's `n=200000` stress cannot reach the 64 MiB commit-log cap used as the control (about 50 MB of log): amended (R8). |
| A. Core question | positive control for a negative estimate | Partly | B2h/B3h name the commit-log cap (known to bind); the filed run had no contrast arm (uncapped) and the cluster workload could not reach the cap: contrast arms and sizes added (R5, R8). |
| B. Logic | each step says what it establishes | Met | B2d-B2e, B3d-B3e; the controls say what each rules out (B2h, B3h). |
| B. Logic | prediction stated in numbers or a clear relation | Met | B2f counts warn lines per value (1/0/0); B3f is relations plus a bound for the control, loosened to the closed-case bound C + 4S (R8). |
| B. Logic | every plausible outcome has a conclusions row with its evidence | Partly | No row for a warn at >= 1 GiB or in the unset control, and unit-tier "usage" was undefined (no system data is written there): rows and a definition added (R6, R8). |
| B. Logic | confirmation needs ceiling-follows-knob and direct disallow evidence | Partly | A negative claim: the direct evidence is the absence of any non-log action. The unit tier had no admission reading below the line; added (R4, R6). |
| B. Logic | alternative explanations and their controls | Met | Unset directory (guard `:730`), positive control (commit-log cap), same workload across values (B2h, B3h). |
| C. Specific | a human can follow it from the intro and §9a | Met | Estimate, Ground, A3 and B1 state the claim and its refutation condition. |
| C. Specific | an AI can run §9b–§9e without re-deriving the code path | Partly | Wrong source path, garbled fallback in B2b, no `-D` set for the test, ambiguous "same JVM" for the control (R2, R3, R5). |
| C. Specific | knob, values, workload, commands, observables, sampling, stop conditions exact | Partly | Sizes, commands and sampling are exact; the control's size arithmetic was not (R8); the data-volume WARN sharing the log was not mentioned (R4). |
| D. Runnable | harness and environment prerequisites exist or are listed | Met | Step-1 work: test class, run scripts; `sudo` mounts work on pc07; JDK 11, Ant 1.10.12, trees built. |
| D. Runnable | workload arithmetic reaches the limit (data, time, disk, memory) | Partly | Sysdata arms fine (3 GiB tmpfs is RAM). The commit-log control did not reach the cap (R8). |
| D. Runnable | load-bearing citations spot-checked against the pinned source | Met | Checked: `DatabaseDescriptor.java:726,730-744` (`:741` compare, `:742-743` warn), `:1661-1664`, `:664-675`, `:2743-2751`, `Config.java:383`, `FileUtils.java:77`, `PathUtils.java:809-822`, `AbstractCommitLogSegmentManager.java:246-263,445-451`, `conf/cassandra.yaml:403`. One slip: `:447` is the definition of `applyAll`, the call to `applySimpleConfig()` is `:455` (R1). |

| # | Recommendation | Applied? (amendment date and commit, or "left for stage 3") | Why |
|---|---|---|---|
| R1 | A3: `:447` is `applyAll`'s definition; the call is `:455` | Applied 2026-10-26 (note in A3, not committed) | citation accuracy |
| R2 | B2a: `~/cassandra-5.0.9` does not exist; use copy-source.sh trees, `javac` + `JUnitCore`, test class in `harness/` | Applied 2026-10-26 (note after B2a) | runnable as written |
| R3 | B2b: exact-size tmpfs values, no filler; fallback sentence void | Applied 2026-10-26 (note after B2b) | root is available |
| R4 | B2d: count only `free in the system data volume`; add the runtime-admission probe (`Directories.getWriteableLocation`) on the sysdata directory | Applied 2026-10-26 (note after B2d) | the data-volume WARN shares the log; direct evidence of what binds below the line |
| R5 | B2e step 4: control as separate JVMs with an uncapped contrast arm and a numeric bound | Applied 2026-10-26 (note after step 4; B2f bullet amended) | a control needs contrast |
| R6 | B2f/B2g: added warn-at-or-above-1-GiB row, defined unit-tier "usage unaffected", added admission prediction | Applied 2026-10-26 (before any run; changes the tables for reasons independent of readings) | Group B completeness |
| R7 | B3a: tree, tmpfs layout, address/ports, ulimit, heap | Applied 2026-10-26 (note after B3a) | specificity, shared host |
| R8 | B3c/B3f/B3g: commit-log control as its own pair of arms (n=1,000,000 x 1 KiB, cap 64 MiB vs 16384 MiB), bound 192 MiB, definitions of "by far" / "did not move", warn-at-1.5-GiB row | Applied 2026-10-26 (notes after B3c, B3f, B3g) | `n=200000` is about 50 MB of log, below the 64 MiB cap |
| R9 | B4: daemon check by `ps ... '[j]ava.*CassandraDaemon'`, kill by PID | Applied 2026-10-26 (B4 edit) | other cases share the host |

**Agreement criteria** — only if run 2 is chosen; filled before run 2 starts.
One row per observable in the case's §9d:

| Observable | Must match | Tolerance |
|---|---|---|
| `<observable>` | exactly / in shape | `<what counts as the same>` |

## 2. Environment

| Field | Run 1 | Run 2 (fresh AI session, if done) |
|---|---|---|
| Date | 2026-10-26 (UTC 19:40-20:12). Audit 19:37-19:40; harness 19:40-19:54 (shakedowns included); unit run 1 19:54-19:56; cluster run 1 19:56-20:10 (timings in `timing/set-A-batch-8.log`) | not done |
| Node (CloudLab name and type) | `pc07` = `node0.jason92-320876.misconfiguration-pg0.cloudlab.umass.edu` (40 cores, 251 GiB); run locally; other set-A cases ran on the same host at the same time (own trees, loopback slots, mount dirs) | - |
| OS and kernel (`uname -r`) | Ubuntu 22.04.2 LTS, `5.15.0-187-generic` | - |
| JDK (`java -version`) | openjdk 11.0.32.1 (2026-08-18) | - |
| Ant (`ant -version`) | 1.10.12 | - |
| Local source copy (from `cassandra/cassandra-5.0.9/` at repository commit `93d6365`) | `~/s4-b8-ls-u` (copy-source.sh, `ant build-test` 1 min 14 s) for the unit tier; `~/s4-b8-ls-n` (copy-source.sh, `ant jar` 1 min 16 s) for the node. Only the two harness test classes were added to `-u`. | - |
| Case-file commit / harness commit | none / none (untracked; the orchestrator commits). Frozen file sha256 `1b976a27...` (§1). Harness md5s: `results/local_system_data_file_directory-applySimpleConfig-freeBytes--autonomous/run1/harness.md5` | - |
| Storage for node data | Unit: exact-size tmpfs mounts (`~/s4-b8-ls-mnt/v05, v10, v10m, v15`) for the sysdata directory; the test yaml's other directories on local disk (`~/s4-b8-ls-unitwork/storage`). Cluster: a 24 GiB tmpfs (`~/s4-b8-ls-mnt/node`) for data, commit log, hints and saved caches; a 3 GiB tmpfs (`~/s4-b8-ls-mnt/sys`) for `local_system_data_file_directory` with a `fallocate` filler; node logs in the log directory under the home disk. All mounts unmounted by the scripts. | - |
| Full logs (path, outside the repo) | `pc07:~/s4-b8-ls-logs/`: `unit-run1/` (per-case stdout, config dumps, `cl32/`, `cl100000/` with DEBUG test logs), `cluster-run1/<arm>/` (full `logs/system.log`, `debug.log`, `node.out`, `samples.csv`, stress outputs, churn outputs), `selfcheck-run1.txt`; shakedowns `unit-shake1/`, `cluster-shake1/`, `cluster-shake2/`; `case-file-frozen.md`, `tables-frozen.txt` | - |

## 3. Runbook defects

| # | Run | Step (§9b-§9e) | Problem | Fix | Decision (date) | Case-file commit with the fix |
|---|---|---|---|---|---|---|
| 1 | audit | A3, B2a-B2b, B2d-B2f, B3a-B3g, B4 | wrong source path; garbled fallback sentence; data-volume WARN shares the log; control not run in one JVM and without a contrast arm; cluster control workload (`n=200000`, about 50 MB) below the 64 MiB cap; missing rows | amendments R1-R9 (§1.1), all before any reading | 2026-10-26 | none (untracked) |
| 2 | shakedown | harness (not a case-file step) | the native port accepted connections several seconds after `statusbinary` printed `running`; stress and cqlsh were refused in cluster shakedown 1 | the run script waits for the port (`/dev/tcp`) before the workload | 2026-10-26 | n/a (harness) |

No runbook defect in run 1 itself.

## 4. Run 1

**Scope:** unit tier (all values) and cluster tier (arms A, B, C, D, P, U). **Command log:** `local_system_data_file_directory-applySimpleConfig-freeBytes--autonomous/run1/unit/summary.txt`, `local_system_data_file_directory-applySimpleConfig-freeBytes--autonomous/run1/cluster/<arm>/summary.txt`, `local_system_data_file_directory-applySimpleConfig-freeBytes--autonomous/run1/selfcheck-run1.txt`.

### 4.1 Readings

**Unit tier** (`run1/unit/<case>.stage4`; raw stdout `pc07:~/s4-b8-ls-logs/unit-run1/<case>.out`)

| Test or assertion | Result | Evidence (file) |
|---|---|---|
| 0.5 GiB (tmpfs 536870912 B, `getUnallocatedSpace` 536870912) | initialization returned, no exception; exactly 1 WARN `Only 512.000MiB free in the system data volume. Consider adding more capacity or removing obsolete snapshots` | `unit/s05.stage4` |
| exactly 1 GiB (1073741824 B) | no sys WARN, no exception | `unit/s10.stage4` |
| 1 GiB - 4096 B (extra boundary case) | 1 sys WARN `Only 1023.996MiB ...` | `unit/s10m.stage4` |
| 1.5 GiB (1610612736 B) | no sys WARN, no exception | `unit/s15.stage4` |
| directory unset (default; control) | no sys WARN, no exception | `unit/unset.stage4` |
| Config dump (all fields but the directory lists) | identical at 0.5, 1, 1.5 GiB and unset (447 fields) | `unit/summary.txt` |
| Runtime admission on the sysdata directory (`Directories.getWriteableLocation`) | 0.5 GiB: 300 MiB request returns the directory (available 484442112 B), twice-available request throws `FSDiskFullWriteError`; 1 GiB and 1.5 GiB: the same outcomes | `unit/s05.stage4`, `s10.stage4`, `s15.stage4` |
| Positive control (commit-log cap, `commitlog_total_space` 32 MiB vs uncapped, 300 x 1 MiB) | capped: peak on-disk 47185920 B (45.0 MiB), 14 `COMMITLOG_DIRTY` flushes; uncapped: 398458880 B (380.0 MiB), 0 flushes | `unit/cl32.cap.summary`, `unit/cl100000.cap.summary`, `unit/cl*.reasons.txt` |

**Cluster tier** (`run1/cluster/<arm>/`; free space of the sysdata volume from `df` every 5 s)

| Capacity value | Run (control / A / B / C) | Observable (§9d) | Reading | Evidence (file) |
|---|---|---|---|---|
| 0.5 GiB at start | A | startup sys WARN; node state; stress; churn | exactly one `Only 512.000MiB free in the system data volume` (`DatabaseDescriptor.java:742`) before the node served; `UN`; 2 x 200,000 writes, 0 errors; 3 churn passes rc 0; no WARN after start; sysdata free space 535642112..536301568 B, sysdata directory at most 233,822 B | `cluster/A/summary.txt`, `system-log-excerpt.txt`, `samples.csv`, `churn.log` |
| 1.5 GiB at start | B | same | no sys WARN; same node behaviour, same stress (0 errors) and churn; sysdata directory at most 308,315 B | `cluster/B/` |
| 1.5 GiB, then 100 MiB | C | WARN after the shrink; node; sysdata usage | no sys WARN at start or after the shrink (epoch_ms 1793044931921: free 1609568256 -> 104865792 B); free space stayed 104398848..105054208 B for 12 samples; node `UN` throughout; 0 stress errors; 3 churn passes rc 0; sysdata directory at most 263,668 B | `cluster/C/summary.txt`, `samples.csv` |
| directory unset | D (control) | startup WARN | none, with a 0.5 GiB volume mounted and untouched (536870912 B throughout) | `cluster/D/` |
| commit log 64 MiB | P (positive control) | `du -sb` commit log every 1 s | peak 134217848 B (128 MiB); 56 `COMMITLOG_DIRTY` flush lines; 1,000,000 rows, 0 errors | `cluster/P/` |
| commit log 16384 MiB | U (contrast) | same | peak 1140851408 B (1088 MiB); 0 `COMMITLOG_DIRTY` flushes; 1,000,000 rows, 0 errors | `cluster/U/` |

### 4.2 Conclusion and logic

1. **Validity** - valid. The limit was reached: the free space was below the 1 GiB constant (512 MiB, and 100 MiB after the shrink) and above it (1.5 GiB), each confirmed by an operand read independent of the check: `FileStore.getUnallocatedSpace` in the unit test [observed: `unit/s05.stage4`, `s10`, `s15`] and `df -B1` before the node started [observed: `cluster/A/summary.txt` "sysdata volume avail at start 536870912 (target 536870912)", B and C 1610612736]. The first-trigger check (A: exactly one WARN) held [observed: `cluster/A/summary.txt`]. Held-fixed settings: same tree, same yaml but the sysdata line and filler, same workload per arm [observed: `yaml-effective.txt`]. The positive control moved: capped 128 MiB against uncapped 1088 MiB, with `COMMITLOG_DIRTY` flushes only in the capped arm [observed: `cluster/P/`, `cluster/U/`; `unit/cl*`].
2. **Readings** - nothing unusual. The sysdata directory grew by at most 0.3 MiB in every arm (system keyspaces are small), so no arm drove the sysdata directory itself toward the line; the design's shrink arm C removed the free space with a filler, not with Cassandra data. The data-volume WARN (`:726`) fired in the unit cases and is a different message [observed: `unit/s05.stage4` `data_warn_count=1`].
3. **Matched row** - Unit B2g: "Warn at 0.5 GiB only; no exception at any value | Mechanism as traced; line 741 is warning-only" and the amended row "Usage unaffected ... Confirmed" (warn at 0.5 GiB only; initialization and Config identical across values; the 300 MiB request admitted at 0.5 GiB; capped control peak 45.0 MiB <= 52 MiB against 380.0 MiB uncapped). Cluster B3g: "Warn at 0.5 GiB start only; same throughput and `UN` in both | Check is warn-only (claim confirmed)" and "System data usage unaffected by knob while commit log control stays bounded by `commitlog_total_space` | Confirmed" (capped peak 128 MiB <= 192 MiB and < 0.5 x uncapped 1088 MiB).
4. **Excluded rows** - "Exception or abort at 0.5 GiB" / "Node fails to start": no exception, node `UN` [observed: `unit/s05.stage4`, `cluster/A/summary.txt`]. "Behaviour differs among values in anything but the warn line": Config dump identical, admission outcomes equal [observed: `unit/summary.txt`]. "Writes rejected/throttled at the 1 GiB boundary": stress 0 errors in A, B, C at both phases, op rates 34-51k/s with no step at the boundary [observed: `cluster/*/stress-*.summary`]. "New warn lines after startup when space shrinks": none in C's whole log [observed: `cluster/C/system-log-excerpt.txt`]. "System data usage follows free space or the knob": sysdata directory bytes 0.2-0.3 MiB in A, B, C (free 0.5 GiB, 1.5 GiB, 0.1 GiB) [observed: `samples.csv`]. "No warn at 0.5 GiB / sizes not achieved / control did not exceed": warn present, sizes exact, control moved. "Warn at or above 1 GiB or in the unset control": none (s10, s15, unset, B, C, D).
5. **Observed vs. inferred** - Inferred: (a) the check cannot influence anything beyond the log because nothing else follows it in the traced block (source reading `DatabaseDescriptor.java:739-743`), supported by the equal Config dumps and the equal node behaviour. (b) "Does not cap the sysdata usage" rests on the sysdata directory staying at most 0.3 MiB with the volume at 0.1 GiB free: a negative claim over a workload that never filled the volume, so what is shown is that nothing triggered by the 1 GiB line changed behaviour, not that the volume cannot fill.
6. **Deviations and gaps** - (a) The control is a separate JVM/arm pair, not "the same JVM" (amendment R5). (b) The system keyspaces wrote under 0.4 MiB, so "driving usage past the line" was done by the filler (an external consumer of the same volume), as the filed B3c anticipates ("the filler is enlarged after startup"). (c) Nothing was observed at the volume actually reaching 0 bytes; behaviour there belongs to `disk_failure_policy` and ENOSPC handling, outside this check. (d) Only one run; no run 2.
7. **Core question** - Usage did not follow the constraint. Across free space of 0.5, 1.0 and 1.5 GiB (and 0.1 GiB after startup) the node's startup, the Config, writes, schema changes and the sysdata directory's size were the same except for the single startup log line, while the commit-log cap in the same harness moved usage 128 MiB vs 1088 MiB; so the 1 GiB constant at line 741 does not cap usage of the system data directory (steps 1-3 above).

**Conclusion (one line):** unit B2g "warn at 0.5 GiB only, no exception" with usage unaffected and control moved, and cluster B3g "warn-only, same throughput and UN" with usage unaffected and control bounded - **Confirmed**, effect `does not cap`.

## 5. Self-check of run 1 - AI

### 5.1 Check of run 1's conclusion

`harness/local_system_data_file_directory-applySimpleConfig-freeBytes--autonomous/selfcheck.py run1` re-parses the raw files (case stdout, DEBUG test logs, `cap.csv`, full `system.log`, `samples.csv`, stress outputs, yaml-effective) without the `.stage4` files or the run summaries; output `run1/selfcheck-run1.txt`, 74 EXPECTED lines, 0 FAIL, `SELFCHECK ALL OK` (one earlier false positive in its leftover-daemon test, a self-matching `ps | grep`, was fixed by matching the process name; no reading was affected).

| Part | Holds? (yes / no) | Note (file re-read) |
|---|---|---|
| 1. Validity | yes | Operand sizes re-read from the raw stdout (`unallocated_bytes=` 536870912 / 1073741824 / 1073737728 / 1610612736) and from `samples.csv` (C after the shrink 104398848..105054208 B); the control's peaks re-computed from `cap.csv` (45.0 vs 380.0 MiB) and `samples.csv` (128 vs 1088 MiB). |
| 2. Readings | yes | Whole-`system.log` counts of the WARN: A 1, B 0, C 0, D 0, P 0, U 0 (not only the post-start tail). |
| 3. Matched row | yes | Raw WARN count per unit case 1/0/1/0/0; initialization returned in all; Config dumps byte-identical; admission outcomes equal in s05, s10, s15. |
| 4. Excluded rows | yes | No ERROR / FSWriteError / ENOSPC in any system.log; stress totals 200,000 and 0 errors in both phases of A-D; churn passes all rc 0; the WARN precedes "Starting listening for CQL clients" (startup only). |
| 5. Observed vs. inferred | yes | Inference (b) is kept as a stated limit of the negative claim. |
| 6. Deviations and gaps | yes | Listed; none changes the matched row. |
| 7. Core question - the steps from reading to answer follow the audited logic | yes | Hypothesis B1 (log-only, startup-only, no cap), test B2/B3, prediction B2f/B3f all matched; the control rows needed for a negative claim (moved under a cap that binds) are met. |

### 5.2 Run 2?

**No** (2026-10-26). The effect is read directly from the warn count and equal behaviour at exact, independently read sizes; the control moved by a factor of about 8.5; the self-check re-parsed the raw files. A run 2 would repeat the same deterministic comparison.

## 6. Run 2 - fresh AI session (optional)

Not done.

## 7. Comparison

Not applicable (no run 2).

## 8. Verdict - AI

**Stage-3 estimate:** negative. **Outcome class:** true negative (negative, does not cap).

**Claim tested:** because line 741 only logs, disk usage in the system data directory does not follow `ONE_GIB`: with free space below 1 GiB the node still starts, accepts writes into the volume and does not stop or shed data because of this check, and the warning is emitted only at startup.

| Tier | Verdict (B2g / B3g row) | Effect on the constraint | Basis | Date |
|---|---|---|---|---|
| Unit | **Confirmed**: warn at 0.5 GiB only (and one page below 1 GiB), none at exactly 1 GiB, 1.5 GiB or unset; no exception; usage unaffected; control moved | does not cap | run 1 + self-check | 2026-10-26 |
| Cluster | **Confirmed**: warn-only at the 0.5 GiB start, same `UN`, stress and churn at 0.5 and 1.5 GiB; no new warn when the space fell to 100 MiB; control bounded | does not cap | run 1 + self-check | 2026-10-26 |

**Positive control:** the commit-log cap (`commitlog_total_space`, known to bind, `AbstractCommitLogSegmentManager.java:445-451`) moved usage under the same instruments: unit 45.0 MiB capped (14 `COMMITLOG_DIRTY` flushes) vs 380.0 MiB uncapped (0); cluster 128 MiB capped (56 flushes) vs 1088 MiB uncapped (0).

**Feedback filed:** the case file's section D updated (not committed); amendments R1-R9 (dated 2026-10-26) were made in A3, B2a, B2b, B2d, B2e-B2g, B3a, B3c, B3f-B3g, B4 before run 1.

**Leftovers on the node:** none running. Directories kept for the orchestrator or later cleanup: `~/s4-b8-ls-u`, `~/s4-b8-ls-n` (about 470 MB each), `~/s4-b8-ls-logs/`, `~/s4-b8-ls-nodework/`, `~/s4-b8-ls-unitwork/`, `~/s4-b8-ls-mnt/` (empty mount points). No mounts, no CassandraDaemon, no listeners on 127.0.6.1.
