# commitlog-total-space-calculateDefaultSpaceInMiB-minSizeInMiB--autonomous — stage-4 results  <!-- file: results/commitlog-total-space-calculateDefaultSpaceInMiB-minSizeInMiB--autonomous.md; the stem ends in --guided or --autonomous -->

> **Case:** [`commitlog-total-space-calculateDefaultSpaceInMiB-minSizeInMiB--autonomous`](../../stage3-ai-deep-read/cases/commitlog-total-space-calculateDefaultSpaceInMiB-minSizeInMiB--autonomous.md)
>
> **Status:** verdict filed 2026-10-26 (run 1 self-checked; no run 2)
>
> **Outcome class:** true positive — estimate `positive`, effect `caps` (soft: transient peaks up to 1.9 x the limit) ([definition](../README.md#outcome-class)). Unit: Confirmed; cluster: Confirmed (B3g row 4, larger overshoot).
>
> **Agent:** guided / autonomous (the suffix of the case-file stem). For an autonomous
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
| **Case-file version** | Autonomous file, untracked at audit time (the repository HEAD was `93d6365`; no commit holds it). As filed: no hash recorded. After the audit's amendments R2-R6 (case file B2e, B2g, B3b, B3c, B3d, B3g and section D, all dated 2026-10-26), frozen 2026-10-26 before any harness run and any reading: sha256 **`2a89296f5574f079b18279afa8e5e2851df245b84cdae8afb84c561014c276b5`**. B2f, B2g, B3f, B3g (the predictions and conclusion tables) were frozen at the same moment; their sub-hashes: see `run1/freeze.txt`. |
| **Harness** | `harness/commitlog-total-space-calculateDefaultSpaceInMiB-minSizeInMiB--autonomous/` (written before run 1; not committed by this session) |
| **Tiers and values** | Unit: arithmetic table (B2b/B2c, B2h swap) plus four `DatabaseDescriptor` init arms H/E/V/C. Cluster: one node, `commitlog_total_space` in {unset (derived 1024 MiB on a 4 GiB tmpfs), 256MiB, 128MiB, 8192MiB (control)}, each twice. |
| **Audit bottom line** | **Ready after amendments**, 2026-10-26 |

### 1.1 Design audit

Citations were spot-checked against `cassandra/cassandra-5.0.9` (read only): `DatabaseDescriptor.java:664-675`, `:684-697`, `:1147-1162`, `:3830-3832`, `:4345`; `Config.java:389-390`, `:396-397`, `:410`, `:413`, `:418-419`; `AbstractCommitLogSegmentManager.java:200`, `:246-262`, `:434`, `:445-451`; `CommitLogSegmentManagerCDC.java:199-225`, `:326-340`; `conf/cassandra.yaml:883`, `:923`; `DatabaseDescriptorTest.java:488-507`. All hold. The arithmetic of B2c and the 4 GiB -> 1024 MiB claim of B3b hold (`calculateDefaultSpaceInMiB` truncates `1 * totalMiB / 4`). No claim error, so nothing goes back to stage 3.

| Group | Check | Rating | Note (section checked) |
|---|---|---|---|
| A. Core question | constrained quantity is memory or disk bytes | Met | A2: commit-log segment bytes (and `cdc_raw` bytes for the sibling). |
| A. Core question | knob varied, >= 3 values incl. default | Met | B3b: unset (default, derived), 256, 128 MiB, plus the explicit 8192 control. Unit: the table of volume sizes. |
| A. Core question | real resource measured, not only the counter | Met | B3d: `du -sb` of the directory is the real resource; the JMX gauge is the counter. |
| A. Core question | usage driven to the limit and past it | Partly | As filed 30 GB nominal on a 4 GiB volume, not runnable; amended (R4) to 2.2 M rows, about 2.4 GiB of log: 2.3 x the unset limit, 9.5 x 256 MiB. |
| A. Core question | positive control (negative estimate only) | n/a | Estimate is positive; the 8192 MiB arm is the uncapped control (B3h). |
| B. Logic | each step says what it establishes | Met | B1, B2h, B3h. |
| B. Logic | prediction stated in numbers | Met | B2f exact values; B3f bounds (limit + 2 segments, x1.25, ordering). |
| B. Logic | every plausible outcome has a conclusions row | Partly | No row for WARN-logging mismatch, an invalid run, or a `MEMTABLE_LIMIT` flush. Added (R3, before any run). |
| B. Logic | confirmation needs ceiling-follows-knob and direct disallow evidence | Partly | Ceiling-follows-knob is required (B3g row 1); the direct evidence of the reclaim branch (`COMMITLOG_DIRTY` flush reasons in `system.log`, B3d) is read as an instrument but not required by the row. Left for stage 3; the harness records it and the self-check reports it. |
| B. Logic | alternative explanations and their controls | Partly | `MEMTABLE_LIMIT` flushes are an alternative reclaimer: ruled out by amendment R4(b) (large memtable) and the flush-reason census. |
| C. Specific | a human can follow it | Met | Estimate, A1-A3, B1. |
| C. Specific | an AI can run it without re-deriving the code path | Partly | The unit init arms had no yaml mechanism (R2). |
| C. Specific | knob, values, workload, commands, sampling, stop exact | Not met -> amended | Unquoted `FIXED(1000)`; "20 tables" impossible with `cassandra-stress`; `-Xmx2G` with a 1 GiB memtable hides the cap; non-existent tools (`jmxterm`, `getcommitlogsize`, `nodetool sysigar`) named. Amended R4-R6. |
| D. Runnable | harness and environment prerequisites | Met | Listed as step-1 work: test class, run scripts. tmpfs mount needs `sudo` (available on pc07). |
| D. Runnable | workload arithmetic reaches the limit | Partly -> amended | 2.2 M x about 1.1 KB = 2.4 GiB log; tmpfs 4 GiB, 90 % = 3.7 GiB; data on `/dev/shm`. |
| D. Runnable | load-bearing citations spot-checked | Met | See above. |

| # | Recommendation | Applied? | Why |
|---|---|---|---|
| R1 | Fresh tree `~/s4-b8-cl` from `copy-source.sh`, logs `~/s4-b8-cl-logs` | Applied 2026-10-26 | Safety rule |
| R2 | B2e: yaml and arm per JVM through `-Dtest.jvm.args`; arms H/E/V/C; expected value computed in the test and by `df` | Applied 2026-10-26 (case file note after B2e) | The runbook gave no way to give the JVM another yaml |
| R3 | B2g/B3g: rows for WARN mismatch, invalid run, `MEMTABLE_LIMIT` flush and full volume | Applied 2026-10-26, before any reading | Group B: every outcome has a row |
| R4 | B3a-B3d: tmpfs 4 GiB for the commit log, `/dev/shm` for the rest, 24 GiB heap and large memtable, one table `n=2200000`, quoted `-col`, samplers, ports of slot 2 | Applied 2026-10-26 (notes after B3b, B3c, B3d) | Runnable as written; the filed workload did not fit |
| R5 | Both unit and cluster arms repeated twice (B3h) | Applied (harness) | B3h asks for it |
| R6 | Require the `COMMITLOG_DIRTY` count in a Confirmed row of B3g; and a throttled arm (as in the `:249` case) so that the limit, not flush throughput, sets the peak | Left for stage 3 | Would change the prediction table beyond a fix |

**Agreement criteria** — not applicable (run 2 not chosen at the audit).

## 2. Environment

| Field | Run 1 | Run 2 (fresh AI session, if done) |
|---|---|---|
| Date | 2026-10-26, node clock EDT: audit and freeze 14:55-15:02 (frozen 19:02:24Z); unit run 1 15:06; cluster chain 15:08-15:34 | not done |
| Node | `pc07` (`node0.jason92-320876...`), 40 cores, 251 GiB; loopback slot 2 (`127.0.2.1`, JMX 7120) | |
| OS and kernel | Ubuntu 22.04, `5.15.0-187-generic` | |
| JDK / Ant | OpenJDK 11.0.32.1 / Ant 1.10.12 | |
| Local source copy | `~/s4-b8-cl`, `copy-source.sh` from `cassandra/cassandra-5.0.9/` at repository commit `93d6365` (tag `cassandra-5.0.9`), `ant build-test` BUILD SUCCESSFUL in 1 min 19 s (`~/s4-b8-cl-logs/build-test.log`) | |
| Case-file commit / harness commit | case file untracked, sha256 in section 1 / harness untracked | |
| Storage for node data | commit log on a 4 GiB tmpfs (`~/s4-b8-cl-vol`, `df` 4096 MiB); data, hints, saved caches, cdc_raw on `/dev/shm/s4-b8-cl-node`; node logs in the same directory, copied out | |
| Full logs | `~/s4-b8-cl-logs/` on pc07 (`unit/`, `cluster/<arm>-r<rep>/`, shakedown 1 dirs `unit-shakedown1/`, `cluster-shakedown1/`) | |

## 3. Runbook defects

| # | Run | Step | Problem | Fix | Decision (date) | Case-file commit with the fix |
|---|---|---|---|---|---|---|
| D1 | unit shakedown 1 | B2e step 4 (C and D arms) | the test assumed `getCDCTotalSpace()` returns MiB; it returns bytes (`DatabaseDescriptor.java:4370`) | instrument fix (divide by MiB in the test); the predictions are unchanged | 2026-10-26, before any run-1 reading | harness only |
| D2 | cluster shakedown 1 | B3e step 2 | the startup config dump prints `commitlog_total_space=null` for an unset knob; the derived value appears only in the `Small commitlog volume detected ... setting commitlog_total_space to 1024` WARN | the first-trigger check reads the WARN for the unset arm and the config line for explicit arms | 2026-10-26, before run 1 | harness only |
| D3 | all | harness | `TEST-<arm>.xml` copy path wrong (file not copied) | the ant log's `Tests run:` line is the evidence; the self-check reads it | 2026-10-26 | harness only |

The two shakedowns are not readings: shakedown 1 of the unit tier failed only on the unit mismatch D1; the first cluster attempt stopped at its first-trigger check (D2) before any stress ran.

## 4. Run 1

**Scope:** unit tier (arithmetic table twice per JVM, arms H E V C D, upstream test) and cluster tier (4 knob values x 2 repetitions). **Command log:** `commitlog-total-space-calculateDefaultSpaceInMiB-minSizeInMiB--autonomous/run1/{unit,cluster}/session.log`, `run1/cluster/chain.log`.

### 4.1 Readings

**Unit tier** (`run1/unit/cltest.out`, `run1/unit/session.log`)

| Test or assertion | Result | Evidence |
|---|---|---|
| Upstream `DatabaseDescriptorTest#testCalculateDefaultSpaceInMiB` | passed (1/1) | `unit/ant-existing-excerpt.txt` |
| `CommitlogDefaultSpaceTest` arms H E V C D | 5 JVMs, 357 `PASS`, 0 `FAIL`, 5 `DONE failures=0` | `unit/cltest.out`, `unit/ant-<arm>-excerpt.txt` |
| Helper, commitlog (8192, 1/4): 0 -> 0 (WARN), 999 MiB -> 249, 4 GiB -> 1024 (WARN), 32767 MiB -> 8191 (WARN), 32768 -> 8192 (no WARN), 32769 -> 8192, 1 TiB -> 8192, `Long.MAX_VALUE` -> 8192 | all as B2f, twice in each of 5 JVMs | `unit/cltest.out` (`rep1`/`rep2` lines) |
| Helper, CDC (4096, 1/8): 0 -> 0, 32767 -> 4095, 32768 -> 4096, 1 TiB -> 4096, `Long.MAX_VALUE` -> 4096 | all as B2f | same |
| Branch flip (B2h): 999 MiB, 1/3, preferred 100 -> 100 (no WARN); preferred 667 -> 333 (WARN) | as expected | same |
| Init arm H (key omitted, host volume 63,943 MiB) | `commitlog_total_space` 8192, no WARN | `INIT` line of arm H |
| Init arm E (`64MiB` explicit) | 64, no WARN | arm E |
| Init arm V (key omitted, 4 GiB tmpfs: 4096 MiB) | 1024, 1 WARN | arm V |
| Init arm C (V plus `cdc_enabled`, cdc dir on the tmpfs) | CDC 512 MiB, 1 cdc WARN | arm C |
| Init arm D (host volume, cdc enabled) | CDC 4096 MiB, no WARN | arm D |

**Cluster tier** (`run1/cluster/summary.txt`; peak = max `du -sb --apparent-size` of the commit-log directory, 0.25 s samples; each arm wrote 2,200,000 rows, 0 errors, 107-134 k op/s, 0 `MEMTABLE_LIMIT` flushes)

| Capacity value | Run | Observable | Reading | Evidence |
|---|---|---|---|---|
| unset (derived 1024 MiB, WARN `setting commitlog_total_space to 1024`) | r1 / r2 | peak; `COMMITLOG_DIRTY` flushes of `standard1`; settle at +60 s | 1952 / 1760 MiB (1.91x / 1.72x); 2 / 2; 352 / 352 MiB | `unset-r*/{warnline.txt,session.log,counts.txt,du.csv.gz}` |
| 256MiB | r1 / r2 | same | 448 / 448 MiB (1.75x); 10 / 10; 160 / 128 MiB | `256-r*/...` |
| 128MiB | r1 / r2 | same | 224 / 224 MiB (1.75x); 23 / 23; 128 / 128 MiB | `128-r*/...` |
| 8192MiB explicit (control) | r1 / r2 | same | 2336 / 2336 MiB (73 files, never reclaimed); 0 / 0; 2336 / 2336 MiB | `8192-r*/...` |

Peak ordering 128 < 256 < unset < control holds in both repetitions. The JMX gauge `TotalCommitLogSize` peaks (224, 448, 1824 / 1664, 2336 MiB) track `du` to within one sample. In `unset-r1` the directory first exceeded 1024 MiB at +15.5 s, the first `COMMITLOG_DIRTY` flush was enqueued at +15.7 s (1.335 GiB of on-heap memtable), the second 8 s later, the peak was at +22.9 s, and the directory fell to 352 MiB by the end of the 60 s settle.

### 4.2 Conclusion and logic

1. **Validity.** Valid. Each arm's effective limit matched its knob: unset -> WARN `setting commitlog_total_space to 1024` on the 4096 MiB tmpfs; explicit arms: the yaml line occurs once and no Small-volume WARN [observed: `cluster/<arm>/{warnline.txt,yaml.diff}`]. The limit was reached and passed in all capped arms (peaks above the limit) [observed: `summary.txt`]. Held fixed: 32 MiB segments, `legacy` access, `heap_buffers`, memtable heap 8192 MiB, threshold 0.9, hints off, 24 GiB heap [observed: `yaml.diff`, `session.log`]. No `MEMTABLE_LIMIT` flush in any arm and the tmpfs never passed 90 % (max 2277 MiB of 4096) [observed: `counts.txt`, `du.csv.gz`]. Every node was stopped; no daemon left [observed: `session.log`].
2. **Readings.** Nothing contradictory. `COMMITLOG_DIRTY` counts rise as the limit shrinks (0, 2, 10, 23) [observed]. The `segment-deletions.txt` count (72 in every arm, including the control) includes the deletions at `nodetool drain`, so it is not a cap measure [inferred: the control had no reclaim flush]. The self-check counts 24 `COMMITLOG_DIRTY` flushes in the 128 arms (all tables) against 23 of `standard1`.
3. **Matched row.** Unit: B2g row 1 "Returns match B2f | helper correct; claim part (i) holds", with the init rows (H, E, V, C, D) matching B2f and the logging side matching (WARN iff `min < preferred`). Cluster: B3g row 4 "Overshoot > 2 segments + flush lag but bounded | caps with larger overshoot; note". Row 1 ("Peak `du` <= limit + ~100 MiB for each value and ordered by knob") is not met: only the 128 MiB peak (+96 MiB) is within +100 MiB; 256 MiB peaked at +192 MiB and the unset arm at +736 to +928 MiB. The ordering part holds. The derived-default row ("effective limit != min(8192, vol/4)") does not fire.
4. **Excluded rows.** B2g: no value or WARN mismatch, the explicit value was not overwritten (arm E), no 0 on a tiny volume was tried in the cluster. B3g: peak independent of the knob - excluded: 224 / 448 / 1760-1952 / 2336 MiB follow the knob. Peak grows unbounded - excluded: peaks plateau and fall to 128-352 MiB, while the uncapped control keeps all 2336 MiB. Never reached the limit - excluded. Unset effective limit wrong - excluded (1024 = min(8192, 4096/4)). Row 1 - excluded as stated in part 3.
5. **Observed vs. inferred.** Inferred: that the derived value is what bounded the unset arm (the WARN shows the value; the `COMMITLOG_DIRTY` flushes at +15.7 s, right after the directory passed 1024 MiB, tie them; no arm without the derived value exists on the 4 GiB volume other than the explicit 8192 control); that the overshoot is flush lag (the flush of a 1.3 GiB memtable takes seconds while the write rate is about 110 k op/s, about 110 MiB/s of log) [inferred: peak times and rates].
6. **Deviations and gaps.** The amendments R2-R5 changed the workload shape (one table, 2.2 M rows, not 20 tables / 30 GB) and put the commit log on a tmpfs, not a loop volume; tmpfs `getTotalSpace()` is 4096 MiB exactly. Unthrottled writes (the case's design) make the peak depend on flush throughput; a throttled arm (R6) was not run. B3f's own sub-predictions "<= limit + 2 segments" and "below about 1.25 x limit for the 128 / 256 MiB runs" were missed (1.75x). The "peak scales with the knob" and "flush count rises as the limit shrinks" predictions held. The CDC variant (B3h, optional) was not run; the unit tier covers only its default arithmetic.
7. **Core question.** The limit follows the knob: capped arms peak at 224, 448 and 1760-1952 MiB for limits 128, 256 and 1024, against 2336 MiB with nothing to trigger a reclaim, and usage falls back to 128-352 MiB after the writes [observed: `summary.txt`]. The reclaim branch fired (`COMMITLOG_DIRTY` flushes, 2 to 23, none in the control) [observed: `counts.txt`]. So the limit caps commit-log disk use softly, with a transient overshoot of up to 1.9 x the limit under an unthrottled 110 k op/s load, and the unit tier shows the default of the limit is `min(8192, volume/4)` as traced.

**Conclusion (one line):** Unit B2g row 1 - Confirmed; cluster B3g row 4 - Confirmed, caps with larger overshoot (soft).

## 5. Self-check of run 1 - AI

### 5.1 Check of run 1's conclusion

`harness/<stem>/selfcheck.py` re-parsed the raw files (not `analyze.py`'s output): `cltest.out`, the ant logs, each arm's `system.log`, `debug.log.gz`, `du.csv`, `stress.out`, `session.log`, `times.txt`, `yaml.diff` (`run1/selfcheck.out`: 0 failed; the INFO lines give the peaks and flush reasons again).

| Part | Holds? | Note (file re-read) |
|---|---|---|
| 1. Validity | yes | WARN value and yaml line per arm; stress 2,200,000 rows and 0 errors; sampler gaps <= 2 s; tmpfs below 90 %; 0 `MEMTABLE_LIMIT`; `daemons left: []` in all 8 session logs |
| 2. Readings | yes | `system.log` reasons recounted: COMMITLOG_DIRTY 24 / 10 / 2 / 0 (all tables) for 128 / 256 / unset / control, in both repetitions; peaks recomputed from `du.csv` match `summary.txt`; the 72 deletions in every arm are drain-time (noted) |
| 3. Matched row | yes | row 1 of B3g fails on the numbers (+192 and +736/+928 MiB against +100); row 4 fits (bounded: falls to 128-352 MiB, well under the uncapped 2336 MiB) |
| 4. Excluded rows | yes | peaks 224 < 448 < 1760/1952 < 2336 in both repetitions |
| 5. Observed vs. inferred | yes | the inferred links (derived value bounds the unset arm; overshoot is flush lag) are stated as inferred; no arm contradicts them |
| 6. Deviations and gaps | yes | R6 (throttled arm) and the CDC variant not run |
| 7. Core question | yes | steps follow B1 (i) then (ii) of the audited logic |

### 5.2 Run 2?

**No** (2026-10-26). Both repetitions agree (same peaks for the knob arms, 1952 vs 1760 MiB for the unset arm), the claim is not refuted or a bypass, and the one inferred link (flush lag) does not change the matched row.

## 6. Run 2 - fresh AI session (optional)

Not done.

## 8. Verdict - AI

**Stage-3 estimate:** positive. **Outcome class:** true positive (positive, caps).

**Claim tested (B1):** (i) the helper returns `min(preferred, num*totalMiB/den)` and `commitlog_total_space` takes that value when unset; (ii) the commit-log directory's on-disk size stays within `commitlog_total_space + ~2 segments + flush lag` under sustained writes, i.e. the limit, not just the default, caps disk.

| Tier | Verdict (B2g / B3g row) | Effect on the constraint | Basis | Date |
|---|---|---|---|---|
| Unit | **Confirmed**, B2g row 1: 357 checks pass; 8192 / 8191 / 0 / 4096 / 1024 / 512 as predicted; explicit 64 MiB bypasses the helper; WARN iff `min < preferred` | caps (the default is `min(8192, volume/4)`) | run 1 + self-check | 2026-10-26 |
| Cluster | **Confirmed**, B3g row 4 (caps with larger overshoot): peaks 224 / 448 / 1760-1952 MiB for 128 / 256 / 1024 (unset) against 2336 MiB uncapped; 23 / 10 / 2 / 0 `COMMITLOG_DIRTY` flushes; overshoot 1.72-1.91 x the limit, missing B3f's +2-segment and 1.25 x sub-predictions | caps (soft) | run 1 + self-check | 2026-10-26 |

A tier the solution declares `n/a`: none. **Positive control:** not required (positive estimate); the explicit 8192 MiB arm is the uncapped control.

**Feedback filed:** the case file's section D updated with the audit amendments (not committed); no section's claim refuted; the case file's B3f bounds (limit + 2 segments, 1.25 x) are too tight for unthrottled writes at about 110 k op/s: left for stage 3 (stage-3 note: use a throttled arm or state the bound as `limit + flush-lag`).

**Leftovers on pc07:** `~/s4-b8-cl` (the working tree, with the untracked test class) and `~/s4-b8-cl-logs` (full logs, kept on purpose); the 4 GiB tmpfs was unmounted and `/dev/shm/s4-b8-cl-node` removed; no process of this case is running and ports 7000/9042 on 127.0.2.1 and 7120 are free.
