# concurrent_compactors-submitBackground-getMaximumPoolSize--guided — stage-4 results  <!-- file: results/concurrent_compactors-submitBackground-getMaximumPoolSize--guided.md; the stem ends in --guided or --autonomous -->
> **Case:** [`concurrent_compactors-submitBackground-getMaximumPoolSize--guided`](../../stage3-ai-deep-read/cases/concurrent_compactors-submitBackground-getMaximumPoolSize--guided.md)
>
> **Status:** audited 2026-10-20 — estimate negative; claim under test: the knob does not bound compaction's disk or memory (source reading predicts Refuted); not run
>
> **Agent:** guided (the suffix of the case-file stem). One results file per case file.

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
| **Case-file version** | Guided file, hash of §9's text after the audit's amendments (`sed -n '/^## 9\. /,/^## 10\. /p' <file> | git hash-object --stdin`): `06caa02b4db6752a1f765de1abf9bdef516334a4`, computed 2026-10-20 before any harness or run. §9a is frozen at this version, including the dated block 9f. Commit holding the file: filled when committed (HEAD before the amendments: `42f9069`). |
| **Harness** | `harness/concurrent_compactors-submitBackground-getMaximumPoolSize--guided/` — none yet; to be written in step 1 (list in the recommendations below). |
| **Tiers and values** | Unit (9c): Byteman-held `CompactionTask.runMayThrow` over 8 tables, pool sizes 1 · 2 · 4 · 8. Cluster (9e): one node, `concurrent_compactors` 1 · 2 (default on a one-directory node) · 4 · 8, 8 tables × 4 SSTables × 256 MiB, throughput 16 MiB/s, positive control at 8 with a lowered `max_space_usable_for_compactions_in_percentage`. |
| **Audit bottom line** | **Ready after amendments** — 2026-10-20 |

### 1.1 Design audit

The requirements are in the README, "Step 0 — the design audit". One row per
line of each group; cite the case-file section checked.

| Group | Check | Rating (Met / Partly / Not met) | Note (section checked) |
|---|---|---|---|
| A. Core question | constrained quantity is memory or disk bytes | Met | 9a Test, 9d: extra on-disk bytes of in-flight compaction output; heap read as a secondary. |
| A. Core question | knob varied, ≥ 3 values incl. default — or another approach, with the reason | Met | 9b values 1, 2 (default: `min(8, max(2, min(32 cores, 1 dir)))` = 2, `DatabaseDescriptor.java:777-778`), 4, 8. |
| A. Core question | real resource measured, not only the counter (gap named) | Met | 9d `du -sb` of the data dir minus baseline is the real resource; the running-task count (the check's operand) is read beside it. |
| A. Core question | usage driven to the limit and past it | Met | 8 tables give 8 eligible compactions, so 1, 2 and 4 are exceeded and 8 is reached; 9a row 4 covers a backlog too small. |
| B. Logic | each step says what it establishes | Met | 9a "How this verifies" block matches the steps, prediction and rows. |
| B. Logic | prediction stated in numbers or a clear relation | Partly | "Within the noise band" had no definition. **Amended** (R4): band = range over three repeats of the default value. |
| B. Logic | every plausible outcome has a conclusions row with its evidence | Met | 9a rows: flat + control moves (Confirmed), rises (Refuted), flat + control flat (Not confirmed), backlog too small (Invalid), partial rise (Refuted). The negative-file minimum is present. |
| B. Logic | confirmation needs ceiling-follows-knob and direct disallow evidence | Met | Confirmed needs the flat peaks, the task count `min(n, 8)` and the control moving; the disallow evidence is the task count reaching the pool size. |
| B. Logic | alternative explanations and their controls | Met | Control: lowered byte budget on the same workload (a closed `Confirmed` case); throughput, strategy, heap and directory held fixed (9b). |
| C. Specific | a human can follow it from the intro and the prediction/conclusions | Met | Intro, 9a and 9b state claim, test, steps and rows without the code path. |
| C. Specific | an AI can run the runbook without re-deriving the code path | Partly | `harness/load_tables.py`, the sampler and the Byteman hold are named but not written (step 1). Compaction throughput is a shared limiter, so the "about a minute" in 9b was wrong beyond *n* = 1: **amended** (R1). |
| C. Specific | knob, values, workload, commands, observables, sampling, stop conditions exact | Partly | "256 MiB" SSTables had no definition of on-disk size; the control's `p` had no calibration or filesystem. **Amended** (R2, R3). |
| D. Runnable | harness and environment prerequisites exist or are listed | Partly | Needs a fixed-size local filesystem for the control (a loopback image, as the `DataDirectory_getAvailableSpace` run used) and the three scripts above: listed as step-1 work; `~/stage4-dds.img` already exists on `pc57`. |
| D. Runnable | workload arithmetic reaches the limit (data, time, disk, memory) | Met | 8 GiB in + up to 8 GiB out = 16 GiB on a 40 GiB filesystem; 8 GiB at 16 MiB/s is about 8.5 min per run; heap 8 GiB of 251 GiB. After R1 the stop condition is defined. |
| D. Runnable | load-bearing citations spot-checked against the pinned clone | Met | Checked in the pinned clone: `submitBackground` guard at `CompactionManager.java:245`, `setConcurrentCompactors` at `:2238` (resizes via `adjustCoreSize`), `StorageService.java:1964`, `CompactionTask.java:412` (`hasDiskSpaceForCompactionsAndStreams`). |

| # | Recommendation | Applied? (amendment date and commit, or "left for stage 3") | Why |
|---|---|---|---|
| R1 | Shared compaction limiter: the run lasts about 8.5 min at every value; sample until no compaction is active, at most 20 min | Applied 2026-10-20 (9b, 9f) | the filed "about a minute" is true only at *n* = 1; an unstated stop would cut the *n* = 8 peak |
| R2 | Define 256 MiB as on-disk bytes: compression off, random values, `du -sb` after the load; ceiling = `min(n, 8)` × measured input | Applied 2026-10-20 (9f) | nominal sizes would mis-state the predicted slope |
| R3 | Calibrate `p` in a dry run on a fixed-size loopback filesystem | Applied 2026-10-20 (9e step 4, 9f) | the control must bind at about two compactions |
| R4 | Define the noise band: range over three repeats of the default value | Applied 2026-10-20 (9a text, 9f) | "flat" and "rises" need a numeric edge, set before any reading |
| R5 | Write `load_tables.py`, the 2-s sampler (`du`, `tpstats`, `compactionstats`) and the unit Byteman hold; reuse `harness/max_space_usable_for_compactions…` for the control | step 1 (harness) | prerequisites, not design changes |

**Agreement criteria** — only if run 2 is chosen; filled before run 2 starts.
One row per observable in the case's runbook observables:

| Observable | Must match | Tolerance |
|---|---|---|
| `<observable>` | exactly / in shape | `<what counts as the same>` |

## 2. Environment

| Field | Run 1 | Run 2 (fresh AI session, if done) |
|---|---|---|
| Date | | |
| Node (CloudLab name and type) | | |
| OS and kernel (`uname -r`) | | |
| JDK (`java -version`) | | |
| Ant (`ant -version`) | | |
| Local `cassandra-src` clone commit | | |
| Case-file commit / harness commit | | |
| Storage for node data | | |
| Full logs (path, outside the repo) | | |

## 3. Runbook defects

Every step a run could not execute as written. The run stops at the
defect; the fix is made in the case file (dated) if it leaves §9a unchanged,
and the affected tier restarts from its beginning. If the fix would change
§9a, the case goes back to the audit. "None" if there were none.

| # | Run | Step (§9b–§9e) | Problem | Fix | Decision (date) | Case-file commit with the fix |
|---|---|---|---|---|---|---|

## 4. Run 1

**Scope:** the tiers and capacity values actually run. **Command log:**
`[case-file stem]/run1/<file>`.

### 4.1 Readings

**Unit tier**

| Test or assertion | Result | Evidence (file) |
|---|---|---|

**Cluster tier** — one row per capacity value, scenario and observable:

| Capacity value | Run (control / A / B / C) | Observable (§9d) | Reading | Evidence (file) |
|---|---|---|---|---|

### 4.2 Conclusion and logic

Tag every statement in parts 1–4 as **[observed: `<file>`]** or
**[inferred: `<reason>`]**. An untagged statement is not part of the
argument.

1. **Validity** — was the run valid? The limit was reached; each §9b "hold
   fixed" setting is confirmed, with its evidence. If not valid, stop here: the
   conclusion is "invalid run".
2. **Readings** — anything unusual in §4.1: a gap, an outlier, a reading that
   contradicts another.
3. **Matched row** — the §9a row, quoted, and the reading that satisfies each
   part of it.
4. **Excluded rows** — for every other §9a row, the reading that rules it out.
   Every **Refuted** row must be addressed.
5. **Observed vs. inferred** — list the inferred statements that the
   conclusion depends on. These are what the self-check most needs to check.
6. **Deviations and gaps** — anything skipped, changed or not observable, and
   how it limits the conclusion.

7. **Core question** — in two or three sentences: did usage follow the
   constraint, and does the constraint cap usage? Follow the "Logic" steps of the
   case's "How this verifies the hypothesis" block (§9a), and cite for each step
   the part above that supports it.

**Conclusion (one line):** `<§9a row>` — confirmed / bypass as recorded /
refuted / not confirmed / invalid run.

## 5. Self-check of run 1 — AI

### 5.1 Check of run 1's conclusion

Re-open every raw file the conclusion cites and confirm it says what the
conclusion says. A part that does not hold is fixed, or the conclusion is
downgraded to *Not confirmed*.

| Part | Holds? (yes / no) | Note (file re-read) |
|---|---|---|
| 1. Validity | | |
| 2. Readings | | |
| 3. Matched row | | |
| 4. Excluded rows | | |
| 5. Observed vs. inferred | | |
| 6. Deviations and gaps | | |
| 7. Core question — the steps from reading to answer follow the audited logic | | |

### 5.2 Run 2?

**Yes / no** — the reason, and the date decided. Choose yes when the conclusion rests on inferred statements, a part of §5.1 cannot be settled from run 1's evidence, or the result refutes the case or confirms a bypass.

## 6. Run 2 — fresh AI session (optional)

"Not done" if §5.2 says no, and §7 is left out.

**Scope:** the tiers and capacity values actually run. **Command log:**
`[case-file stem]/run2/<file>`.

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

**Stage-3 estimate:** positive / negative / undetermined (from the case file; the Effect column below is what the run found, and a mismatch is the result).

**Claim tested:** (copy it from §9a or B1; for a negative-estimate file it says usage does **not** follow the constraint.)
"Confirmed" below always means this claim held.

| Tier | Verdict (§9a row; for an autonomous file, the B2g / B3g row) | Effect on the constraint | Basis | Date |
|---|---|---|---|---|
| Unit | | caps / does not cap / caps only on some paths (bypass) / undetermined | run 1 + self-check / run 1 + run 2 | |
| Cluster | | caps / does not cap / caps only on some paths (bypass) / undetermined | run 1 + self-check / run 1 + run 2 | |

**Positive control** (a negative-estimate file only): what moved usage under a known-binding condition, with the
reading — or why none was possible (then no tier of this file can be Confirmed).

A tier the solution declares `n/a` gets a row saying `not run: <reason>`.

**Feedback filed:** the case file's §10 "Stage-4 feedback" field updated
(commit), and any section amended (which one, commit) — or "none needed".
