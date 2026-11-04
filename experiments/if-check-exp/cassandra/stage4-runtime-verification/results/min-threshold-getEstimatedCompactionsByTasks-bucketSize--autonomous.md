# min-threshold-getEstimatedCompactionsByTasks-bucketSize--autonomous — stage-4 results  <!-- file: results/min-threshold-getEstimatedCompactionsByTasks-bucketSize--autonomous.md; the stem ends in --guided or --autonomous -->

> **Case:** [`min-threshold-getEstimatedCompactionsByTasks-bucketSize--autonomous`](../../stage3-ai-deep-read/cases/min-threshold-getEstimatedCompactionsByTasks-bucketSize--autonomous.md)
>
> **Status:** **verdict filed 2026-10-27** — unit **Confirmed** (does not cap), cluster **Confirmed** (does not cap; one frozen numeric tolerance, live heap within 5 %, was missed at 5.4 % and is recorded as a deviation). Claim tested: `min_threshold` at this line only changes a pending-compaction count; node disk and memory do not follow it. Run 1 only, no run 2.
>
> **Outcome class:** **true negative** — stage-3 estimate `negative` against the stage-4 effect `does not cap` ([definition](../README.md#outcome-class))
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
| **Case-file version** | FROZEN 2026-10-27, before any reading: repository HEAD `93d6365` plus the uncommitted file (the orchestrator commits); whole-file sha256 after the audit's amendments `6fd011bd783da67787ba606aa6610814d89be500b9429edf70a3b0e9ab805b74`. Prediction and conclusion tables: B2f-B2g (from `**B2f.` up to `**B2h.`) sha256 `1c75c231439abea7140e4c05cfb064beab4d270856caa7a6cc3020dad133c547`; B3f-B3g (up to `**B3h.`) sha256 `2845a9511a218df0734898b6eb3a1270c893dfbf0a5cbb2b4704998c0ffe380d`. Computed with `sed -n '/^\*\*B2f\./,/^\*\*B2h\./p' <file> \| sed '$d' \| sha256sum` (B3 alike). Hashes taken after the amendments and before any reading, shakedowns excepted (plumbing only). Template text for reference: **Guided file:** the commit that holds the case file, and the hash of §9's text (`sed -n '/^## 9\. /,/^## 10\. /p' <case file> \| git hash-object --stdin`), recorded after the audit's amendments; §9a is frozen at this version. **Autonomous file:** the commit that holds the file, and the sha256 of the whole file (`sha256sum`) recorded after the audit's amendments; this hash goes in `_INDEX.md` (column sha256) |
| **Harness** | `harness/min-threshold-getEstimatedCompactionsByTasks-bucketSize--autonomous/` (uncommitted when run 1 starts; the orchestrator commits): `MinThresholdProbeTest.java`, `unit-run.sh`, `analyze-unit.py`, `make-node-yaml.sh`, `cluster-run.py`, `analyze-cluster.py`, `selfcheck.py`, `README.md`. Written after the freeze, before run 1. Template: committed paths and commit |
| **Tiers and values** | Unit: `min_threshold` {2, 4, 8, 9} at 8 SSTables and {2, 4, 9} at 40, forward then reverse sweep, `max_threshold` 32; controls: execute the (4,8) compaction, `max_threshold` 4 vs 32 at 40 SSTables. Cluster: one node, `min_threshold` {2, 4, 16} x 3 repetitions at max 32 with 10 SSTables of ~20 MiB, plus control tables min 4 with max 4 and max 32. |
| **Audit bottom line** | **Ready after amendments** — 2026-10-27 |

### 1.1 Design audit

The requirements are in the README, "Step 0 — the design audit". One row per
line of each group; cite the case-file section checked.

| Group | Check | Rating (Met / Partly / Not met) | Note (section checked) |
|---|---|---|---|
| A. Core question | constrained quantity is memory or disk bytes | Met | A2/B1: the operand is an SSTable count; the claim is that no bytes follow it. The byte quantities are table disk bytes and node heap/RSS (B2d, B3d). A count with a derivable size (SSTable ~1 MiB or ~20 MiB). |
| A. Core question | knob varied, ≥ 3 values incl. default — or another approach, with the reason | Met | B2b four values (default 4), B3b three (2, 4, 16). Amended: 33 -> 9 (min above max=32 cannot be set, `ColumnFamilyStore.java:3097-3100`). |
| A. Core question | real resource measured, not only the counter (gap named) | Met | B2d/B3d read `onDiskLength`, `du`, heap, RssAnon next to the estimate. Gap named: heap attribution to one int is not observable (B3d). |
| A. Core question | usage driven to the limit and past it | Met | B2c/B3c put the bucket on both sides of every threshold (8 vs 2/4/8/9; 10 vs 2/4/16). The 'limit' is the threshold itself; a count can reach it. |
| B. Logic | each step says what it establishes | Met | B2e/B3e numbered, each tied to a B2g/B3g row. |
| B. Logic | prediction stated in numbers or a clear relation | Met | B2f/B3f give exact estimates (ceil(n/32) or 0), equal bytes, heap within noise. B2f heap 'noise < 1 MiB' needs a warm-up call (harness; shakedown showed +2 MiB in the first cell). |
| B. Logic | every plausible outcome has a conclusions row with its evidence | Partly | B2g/B3g cover confirm, refute, estimate not refreshing, control and limit-never-reached. No row for a positive control that fails to move; the README's rule (never Confirmed then) applies. Left for stage 3. |
| B. Logic | confirmation needs ceiling-follows-knob and direct disallow evidence | Met | For a negative file: disk/heap flat across min while the estimate flips (the disallow-branch-absent evidence) and the control moves. |
| B. Logic | alternative explanations and their controls | Met | B2h/B3h: executed compaction and the max_threshold 4 vs 32 width as a known-binding limit; fresh table per setting and 3 repetitions. |
| C. Specific | a human can follow it from the intro and §9a | Met | A3 and B1 are clear. |
| C. Specific | an AI can run §9b–§9e without re-deriving the code path | Not met -> fixed | B3e used `setcompactionthreshold` to refresh the estimate while autocompaction is disabled; `submitBackground` returns at once then (`CompactionManager.java:232`). B2d called the manager, which returns null when disabled (`CompactionStrategyManager.java:203`). Amended. |
| C. Specific | knob, values, workload, commands, observables, sampling, stop conditions exact | Partly -> fixed | Throttle (8 MiB/s), stress as ten disjoint invocations, baseline sample definition and polling added as dated amendments. |
| D. Runnable | harness and environment prerequisites exist or are listed | Met | Unit test, node yaml builder, runner are step-1 work; `ant build-test` and `ant jar` on pc07 trees from `copy-source.sh`. |
| D. Runnable | workload arithmetic reaches the limit (data, time, disk, memory) | Met | ~215 MB per table on tmpfs, 9+2 tables; compaction of 200 MiB at 8 MiB/s ~ 25 s; unit tables 8-40 MiB. |
| D. Runnable | load-bearing citations spot-checked against the pinned source | Met | `SizeTieredCompactionStrategy.java:89-90, 123, 232, 301-302`, `ColumnFamilyStore.java:3066-3103`, `CompactionParams.java:79`, `CompactionMetrics.java:71-83`, `ActiveRepairService.java:637-646` checked. One citation fixed (`:125` -> `:123`). |

| # | Recommendation | Applied? (amendment date and commit, or "left for stage 3") | Why |
|---|---|---|---|
| R1 | B2b/B2f/B2g: replace min 33 by 9 | Applied 2026-10-27 | min > max is rejected by the setter |
| R2 | B2d: call the STCS instance, not the manager | Applied 2026-10-27 | a disabled manager returns null |
| R3 | B3e: refresh by `enableautocompaction`; define the baseline sample (min set, autocompaction disabled); B3a throttle 8 MiB/s | Applied 2026-10-27 | the estimate is stale while disabled; a 200 MiB compaction ends in seconds unthrottled |
| R4 | B3c/B3h clarifications (stress invocations, control tables); B2a build recipe; citation `:125` -> `:123` | Applied 2026-10-27 | runnability |
| R5 | A row for 'positive control did not move' in B2g/B3g | Left for stage 3 | README already says never Confirmed in that case |
| R6 | The repair-reject consumer (`ActiveRepairService.java:637-646`) is a control-plane effect | Left for stage 3 | not tested here |

**Agreement criteria** — only if run 2 is chosen; filled before run 2 starts.
One row per observable in the case's §9d:

| Observable | Must match | Tolerance |
|---|---|---|
| `<observable>` | exactly / in shape | `<what counts as the same>` |

## 2. Environment

| Field | Run 1 | Run 2 (fresh AI session, if done) |
|---|---|---|
| Date | 2026-10-27 | not done |
| Node (CloudLab name and type) | pc07 (`node0.jason92-320876…`), 40 cores, 251 GiB | |
| OS and kernel (`uname -r`) | Ubuntu 22.04, 5.15.0-187-generic | |
| JDK (`java -version`) | openjdk 11.0.32.1 | |
| Ant (`ant -version`) | 1.10.12 | |
| Local source copy (from `cassandra/cassandra-5.0.9/` at repository commit …) | `copy-source.sh` -> `~/s4-b11-m71-u` (`ant build-test`, 1 min 11 s) and `~/s4-b11-m71-n` (`ant jar`, 1 min 18 s), tag `cassandra-5.0.9`, repository commit `93d6365` | |
| Case-file commit / harness commit | uncommitted at run time (HEAD `93d6365` plus the amended file); whole-file sha256 as frozen in §1; harness md5s in `run1/unit/summary.txt` | |
| Storage for node data | unit: the test's own temp dirs; cluster: tmpfs `/dev/shm/s4-b11-m71` (removed afterwards) | |
| Full logs (path, outside the repo) | `~/s4-b11-m71-logs/run1/{unit,cluster}/` and the node's `~/s4-b11-m71-node/logs/system.log` on pc07 | |

## 3. Runbook defects

Every step a run could not execute as written. The run stops at the
defect; the fix is made in the case file (dated) if it leaves §9a unchanged,
and the affected tier restarts from its beginning. If the fix would change
§9a, the case goes back to the audit. "None" if there were none.

| # | Run | Step (§9b–§9e) | Problem | Fix | Decision (date) | Case-file commit with the fix |
|---|---|---|---|---|---|---|
| 1 | audit | B2b | min 33 with max 32 cannot be set (`ColumnFamilyStore.java:3097-3100`) | 33 -> 9 in B2b/B2f/B2g | 2026-10-27, before any reading | uncommitted (orchestrator) |
| 2 | audit | B2d | a disabled manager returns null before any strategy runs (`CompactionStrategyManager.java:203`) | call the STCS instance | 2026-10-27 | uncommitted |
| 3 | audit | B3e | `setcompactionthreshold` cannot refresh the estimate while autocompaction is disabled (`CompactionManager.java:232`) | refresh by `enableautocompaction`; baseline sample defined; throttle 8 MiB/s | 2026-10-27 | uncommitted |
| 4 | shakedown | harness | first unit cell showed +2 MiB heap (first-call allocation) | warm-up table before the recorded sweep (harness only; B2f unchanged) | 2026-10-27 | n/a (harness) |

No step failed to run as written during run 1.

## 4. Run 1

**Scope:** unit tier (all cells) and cluster tier (9 estimate arms, 2 control arms), run 1. **Command log:**
`min-threshold-getEstimatedCompactionsByTasks-bucketSize--autonomous/run1/unit/summary.txt`, `run1/cluster/summary.txt` (full `session.log` stays on pc07).

### 4.1 Readings

**Unit tier**

| Test or assertion | Result | Evidence (file) |
|---|---|---|
| Estimate per (n, min), 14 cells forward + reverse | n=8: min 2/4/8 -> 1, min 9 -> 0; n=40: min 2/4/9 -> 2; strategy, manager sum and `PendingCompactions` gauge equal in every cell; a task is returned exactly when n >= min | `run1/unit/analysis.txt` (P1, P1b, P1c) |
| Disk bytes, live, total vs min | n=8: 8,380,756 B and identical for all min; n=40: 41,906,915 B identical | `run1/unit/test.out`, analysis P2 |
| Heap after `System.gc()` vs min | spread 0.007 MiB (n=8), 0.000 MiB (n=40) | analysis P3 |
| Positive control, execute (4,8) compaction | 8 inputs -> 1 sstable, bytes 8,381,461 -> 8,381,677 | `test.out` `control-exec` |
| Positive control, `max_threshold` 4/32/4 at 40 sstables | task inputs 4/32/4 (input bytes 4.19 MB / 33.5 MB / 4.19 MB), estimate 10/2/10 | `test.out` `control-max` |
| Instrument checks | one bucket (8, 40); min 33 rejected with max 32; estimate varies with min; JUnit 1 test, 0 failures | analysis I1-I3, `TEST-*.xml` |

**Cluster tier** — one row per capacity value, scenario and observable:

| Capacity value | Run (control / A / B / C) | Observable (§9d) | Reading | Evidence (file) |
|---|---|---|---|---|
| min 2 (3 reps) | estimate | `PendingCompactions` polled ~every 1.1 s after `enableautocompaction`: baseline 0, max 1 in all 3 reps, 0 after the compaction | `run1/cluster/series-e{1,2,3}m2.csv` |
| min 4 (3 reps) | estimate | same: max 1 in all 3 reps | `series-e{1,2,3}m4.csv` |
| min 16 (3 reps) | estimate | 0 throughout; no compaction; 10 sstables remain | `series-e{1,2,3}m16.csv`, `summary.txt` |
| all 9 | baseline (min set, autocompaction disabled) disk | Space used total 215,580,849-215,581,037 B, `du` 215,582,489-215,582,677 B (spread < 0.0001 %) | `summary.txt` BASELINE lines |
| all 9 | baseline live heap (class histogram total) | min 2: 79.9 / 88.7 / 85.3 MB (mean 84.6); min 4: 88.4 / 89.6 / 87.2 (88.4); min 16: 87.4 / 90.7 / 89.3 (89.1); spread of means 5.4 % | `summary.txt`, `analysis.txt` P3 |
| all 9 | baseline RssAnon | 2896.5-2915.1 MB; per-min means 2905.5 / 2909.3 / 2911.2 MB, spread 0.2 % | `analysis.txt` P3 |
| min 2, 4 | after the enable | one `Compacted ... 10 sstables` line each (6 of 6), `du` peaks 425-428 MB (baseline + ~210 MB), end with 1 sstable and ~215.7 MB | `compacted-lines.txt`, series CSVs |
| control c4 (min 4, max 4) | first compaction | 4 sstables, peak `du` +84 MB over baseline until it ends; estimate polled up to 3 (ceil(10/4)) | `compacted-lines.txt`, `series-c4.csv` |
| control c32 (min 4, max 32) | first compaction | 10 sstables, peak `du` +209 MB (ratio 2.5) | `series-c32.csv` |
| node | errors | 0 `^ERROR` lines in `system.log` | `summary.txt` |

### 4.2 Conclusion and logic

Tag every statement in parts 1–4 as **[observed: `<file>`]** or
**[inferred: `<reason>`]**. An untagged statement is not part of the
argument.

1. **Validity** — valid. Each hold-fixed setting is confirmed: ten equal SSTables (21.18 MB each, sizes within 0.001 %, below the 50 MB `min_sstable_size`, so one bucket), no compaction during ingest, thresholds read back, 0 pending and 10 sstables at the baseline [observed: `run1/cluster/summary.txt` EXPECTED lines, BASELINE]. The limit is reached on both sides: 10 SSTables >= min 2 and 4, < min 16; 8 >= 2/4/8, < 9 [observed: `unit/analysis.txt`].
2. **Readings** — (a) live heap per-min means spread 5.4 % (84.6 / 88.4 / 89.1 MB), above the frozen 5 % tolerance of B3f; the within-min spread of min 2 alone (79.9-88.7 MB) is larger than the difference between means, and the first-run arm `e1m2` (the first arm after node start) is the low value [observed: `summary.txt`]. (b) RssAnon rises slowly with arm order (2896 -> 2917 MB over the 11 arms) [observed]. (c) The control c4 estimate reached 3, not mentioned in B3f; not a contradiction (ceil(10/4)).
3. **Matched row** — unit B2g row 1, "Estimate flips as predicted, disk bytes and heap constant across min" plus the positive-control row; cluster B3g row 1, "Pending changes with min, disk and memory flat", plus the positive-control row (disk rises during the compaction while the estimate-only change did not move it) and the last row (min 16: 10 < 16, no compaction, 10 files stay, a different line's gate). Per part: estimate 1/1/0 at min 2/4/16 [observed: series CSVs]; disk identical to < 0.0001 % [observed: BASELINE]; memory: RssAnon flat to 0.2 %, live heap flat to 5.4 % (see deviation, part 6).
4. **Excluded rows** — "Disk bytes or heap vary monotonically with min with SSTable set unchanged" (unit): bytes identical, heap 0.007 MiB spread, forward and reverse sweep identical [observed]. "Disk or memory differ by min before any compaction" (cluster): disk identical; RssAnon 0.2 %; live heap means differ 5.4 % but not beyond within-min noise [observed], argued below as not systematic. "Estimate does not change" (not confirmed rows): the estimate flips exactly as predicted [observed].
5. **Observed vs. inferred** — inferred: [inferred: the 5.4 % heap difference is noise and arm-order drift, not a min effect, because (i) the unit tier shows 0.007 MiB spread over the same calls in one JVM, in both sweep directions; (ii) `min_threshold` is read as one int in `getEstimatedCompactionsByTasks` and `mostInterestingBucket`, and the baseline is sampled before the enable; (iii) arms ran in the same order in every rep, so min is confounded with arm position, and RssAnon and heap rise with arm index]. Also inferred: that the claim holds for the repair-reject consumer's control-plane effect (not tested).
6. **Deviations and gaps** — The frozen B3f tolerance "heap/off-heap within +-5 %" was missed on live heap (5.4 %). Arm order was not randomized (min 2, 4, 16 in every rep), so a min effect and an order effect cannot be separated from the cluster tier alone; the unit tier's reversed sweep is the order-free evidence. The poll window shows the gauge at 1 for the whole throttled compaction (about 25 s), as the amended B3e expects. Not tested: the repair-reject consumer (`ActiveRepairService.java:637-646`), STCS only, per-object attribution of heap (named in B3d).
7. **Core question** — Usage did not follow `min_threshold`: with the SSTable set fixed, bytes on disk were identical across min and the live heap and RssAnon showed no min dependence beyond noise, while the estimate flipped exactly with the threshold (unit and cluster). The constraint therefore does not cap memory or disk at this line; the real gate (`mostInterestingBucket`) and `max_threshold` change the work done by a compaction, which the positive controls show (width 4 vs 10 sstables, peak `du` +84 vs +209 MB), but that is a different line.

**Conclusion (one line):** B2g "estimate flips, disk and heap constant" (unit) and B3g "pending changes with min, disk and memory flat" (cluster), each with its positive control — **Confirmed**, does not cap; cluster heap tolerance missed by 0.4 points (recorded).

## 5. Self-check of run 1 — AI

### 5.1 Check of run 1's conclusion

Re-open every raw file the conclusion cites and confirm it says what the
conclusion says. A part that does not hold is fixed, or the conclusion is
downgraded to *Not confirmed*.

| Part | Holds? (yes / no) | Note (file re-read) |
|---|---|---|
| 1. Validity | yes | `cluster/summary.txt` EXPECTED lines and BASELINE re-parsed by `selfcheck.py` C0, C5 (11 baselines, gauge 0, 10 sstables); `unit/` TEST xml U7. |
| 2. Readings | yes | heap miss and order drift are stated; `selfcheck.txt` C4 prints DOES NOT HOLD for the 5 % heap tolerance, which is the recorded deviation, not a contradiction of the claim. |
| 3. Matched row | yes | `selfcheck.txt` U2-U6, C1/C2 (gauge max 1/1/0, `Compacted ... 10 sstables` once per min 2/4 rep, none at 16, read from the node's `system.log`), C3, C6-C8 hold. |
| 4. Excluded rows | yes | U3/U4 (bytes constant, heap < 1 MiB), C3 (disk), C4 rss 0.20 %; the heap row is the one judged by argument, see part 5. |
| 5. Observed vs. inferred | yes, with a stated weakness | the heap-noise inference rests on the unit tier and the arm-order drift; cluster order was not randomized. |
| 6. Deviations and gaps | yes | matches the raw numbers; the heap overrun is 5.36 % computed independently. |
| 7. Core question — the steps from reading to answer follow the audited logic | yes | B1 claim, B2g/B3g rows, positive controls U5/U6/C6/C7 hold. |

### 5.2 Run 2?

**No** (decided 2026-10-27). The only open point is a 0.4-point overrun of a noisy heap tolerance, with the real resource (RssAnon) and the unit-tier heap flat; a rerun of the 55 min cluster tier with randomized order is not cheap, and the conclusion does not rest on it. Template text: Choose yes when the conclusion rests on inferred statements, a part of §5.1 cannot be settled from run 1's evidence, or the result refutes the case or confirms a bypass.

## 6. Run 2 — fresh AI session (optional)

Not done (§5.2 says no); §7 is left out.

**Scope:** the tiers and capacity values actually run. **Command log:**
`min-threshold-getEstimatedCompactionsByTasks-bucketSize--autonomous/run2/<file>`.

### 6.1 Readings

**Unit tier**

| Test or assertion | Result | Evidence (file) |
|---|---|---|

**Cluster tier**

| Capacity value | Run (control / A / B / C) | Observable (§9d) | Reading | Evidence (file) |
|---|---|---|---|---|

### 6.2 Matched row

The §9a row these readings match, in one line.

## 7. Comparison — only if run 2 was done

| Observable | Run 1 | Run 2 | Criterion (§1) | Agree? |
|---|---|---|---|---|

**Same §9a row?** yes / no. If no, or if a reading disagrees: the cause, and
how it was resolved (see "Compare and decide" in the README).

## 8. Verdict — AI

Jingsong may overrule any verdict at any time; record an override here with its
date and reason.

**Stage-3 estimate:** negative. **Outcome class:** **true negative**. Template: positive / negative / undetermined (from the case file; the Effect column below is what the run found). **Outcome class:** true positive (positive, caps) / false positive (positive, does not cap) / true negative (negative, does not cap) / false negative (negative, caps) / undetermined (tiers disagree or a tier could not settle it); a mismatch is the result.

**Claim tested:** B1: changing `min_threshold` changes only the pending-compaction estimate computed at line 301 (a count); the byte usage a node tracks is not a function of this operand (usage does not follow the constraint).
"Confirmed" below always means this claim held.

| Tier | Verdict (§9a row; for an autonomous file, the B2g / B3g row) | Effect on the constraint | Basis | Date |
|---|---|---|---|---|
| Unit | B2g "Estimate flips as predicted, disk bytes and heap constant across min" + positive-control row: **Confirmed** | does not cap | run 1 + self-check | 2026-10-27 |
| Cluster | B3g "Pending changes with min, disk and memory flat" + positive-control row: **Confirmed** (live-heap tolerance of B3f missed, 5.4 % vs 5 %; see 4.2 part 6) | does not cap | run 1 + self-check | 2026-10-27 |

**Positive control** (a negative-estimate file only): unit: executing the (4,8) compaction took 8 sstables to 1 and `max_threshold` 4 vs 32 changed the task from 4 to 32 inputs (4.19 MB vs 33.5 MB); cluster: with min 4 and max 4 the first compaction took 4 sstables and peaked +84 MB of `du`, with max 32 it took 10 and peaked +209 MB (`run1/cluster/series-c4.csv`, `series-c32.csv`, `compacted-lines.txt`); min 2 and 4 compactions raised `du` by ~210 MB after the enable.

A tier the solution declares `n/a` gets a row saying `not run: <reason>`.

**Feedback filed:** the case file's section D "Stage-4 feedback" updated 2026-10-27 (uncommitted; the orchestrator commits). Audit amendments to B2a/B2b/B2d/B2f/B2g/B3a/B3c/B3e/B3f/B3h and the `:125` -> `:123` citation were made before run 1. No section amended after a reading.

**Leftovers on pc07:** no process; `/dev/shm/s4-b11-m71` removed; trees `~/s4-b11-m71-u`, `~/s4-b11-m71-n`, `~/s4-b11-m71-node`, `~/s4-b11-m71-logs` (logs and the node's `system.log`) remain.
