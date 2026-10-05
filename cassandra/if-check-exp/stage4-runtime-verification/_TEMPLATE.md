# [case-file stem] — stage-4 results  <!-- file: results/[case-file stem].md -->

> **Case:** [`[case-file stem]`](../../stage3-ai-deep-read/long-path/cases/[case-file stem].md)
>
> **Status:** planned / audited / run 1 done / self-checked / run 2 done / verdict filed
>
> **Path:** long / short. One results file per path. For a `--short` file
> (`results/[case-file stem]--short.md`), the "case file" below is the short-path
> solution, and for each tier "§9a" means that tier's predictions and conclusions
> table: B2f and B2g (unit), B3f and B3g (cluster); "§9b–§9e" means B2a–B2e or
> B3a–B3e. If the case has both paths, see [`comparison/[case-file stem].md`](../comparison/[case-file stem].md)
> for the side-by-side.

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
| **Case-file version** | the commit that holds the case file, and the hash of §9's text (`sed -n '/^## 9\. /,/^## 10\. /p' <case file> \| git hash-object --stdin`), recorded after the audit's amendments; §9a is frozen at this version |
| **Harness** | committed paths under `../harness/[case-file stem]/`, and their commit — or "none" |
| **Tiers and values** | which tiers (unit / cluster) and capacity values this file covers |
| **Audit bottom line** | Ready / Ready after amendments / Blocked — date |
| **Files read** | For both paths' results files: every file opened from this repo during the session, one per line, so the blindness check has a record. For a `--short` file the other path's files (long-path folder, the case's long results and harness, `HANDOFF.md`, `comparison/`) must not appear; the same holds the other way round for a long-path file when the case has a short solution |

### 1.1 Design audit

The requirements are in the README, "Step 0 — the design audit". One row per
line of each group; cite the case-file section checked.

| Group | Check | Rating (Met / Partly / Not met) | Note (section checked) |
|---|---|---|---|
| A. Core question | constrained quantity is memory or disk bytes | | |
| A. Core question | knob varied, ≥ 3 values incl. default — or another approach, with the reason | | |
| A. Core question | real resource measured, not only the counter (gap named) | | |
| A. Core question | usage driven to the limit and past it | | |
| B. Logic | each step says what it establishes | | |
| B. Logic | prediction stated in numbers or a clear relation | | |
| B. Logic | every plausible outcome has a conclusions row with its evidence | | |
| B. Logic | confirmation needs ceiling-follows-knob and direct disallow evidence | | |
| B. Logic | alternative explanations and their controls | | |
| C. Specific | a human can follow it from the intro and §9a | | |
| C. Specific | an AI can run §9b–§9e without re-deriving the code path | | |
| C. Specific | knob, values, workload, commands, observables, sampling, stop conditions exact | | |
| D. Runnable | harness and environment prerequisites exist or are listed | | |
| D. Runnable | workload arithmetic reaches the limit (data, time, disk, memory) | | |
| D. Runnable | load-bearing citations spot-checked against the pinned clone | | |

| # | Recommendation | Applied? (amendment date and commit, or "left for stage 3") | Why |
|---|---|---|---|

**Agreement criteria** — only if run 2 is chosen; filled before run 2 starts.
One row per observable in the case's §9d:

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

| Tier | Verdict (§9a row; for a short-path file, the B2g / B3g row) | Basis | Date |
|---|---|---|---|
| Unit | | run 1 + self-check / run 1 + run 2 | |
| Cluster | | run 1 + self-check / run 1 + run 2 | |

A tier the solution declares `n/a` gets a row saying `not run: <reason>`.

**Feedback filed:** the case file's §10 "Stage-4 feedback" field updated
(commit), and any section amended (which one, commit) — or "none needed".
