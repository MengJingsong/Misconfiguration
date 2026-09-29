# [case-file stem] — stage-4 results  <!-- file: results/[case-file stem].md -->

> **Case:** [`[case-file stem]`](../../stage3-ai-deep-read/cases/[case-file stem].md)
>
> **Status:** planned / run 1 done / reviewed / run 2 done / verdict filed

**Relative links in this template** are written for where a *copy* of it lives
— inside `results/` — not for the template's own location one level up.

**Fill the sections in order.** Run 1 (§4) and the review (§5) are required;
run 2 (§6) and the comparison (§7) are filled only if the review chooses run 2.
The protocol behind each section is in
[`../README.md`](../README.md#the-run-protocol).

## 1. Before run 1

| Field | Content |
|---|---|
| **Case-file commit** | the commit whose §9 every run follows; §9a is frozen at this commit |
| **Harness** | committed paths under `../harness/[case-file stem]/`, and their commit — or "none" |
| **Tiers and values** | which tiers (unit / cluster) and capacity values this file covers |
| **Approved by Jingsong** | date — covers this table |

**Agreement criteria** — only if run 2 is chosen; filled before run 2 starts.
One row per observable in the case's §9d:

| Observable | Must match | Tolerance |
|---|---|---|
| `<observable>` | exactly / in shape | `<what counts as the same>` |

## 2. Environment

| Field | Run 1 (AI) | Run 2 (Jingsong, if done) |
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
defect; the fix is approved, made in the case file (dated), and the affected
tier restarts from its beginning. "None" if there were none.

| # | Run | Step (§9b–§9e) | Problem | Fix | Approved (date) | Case-file commit with the fix |
|---|---|---|---|---|---|---|

## 4. Run 1 — AI session

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
   conclusion depends on. These are what the review most needs to check.
6. **Deviations and gaps** — anything skipped, changed or not observable, and
   how it limits the conclusion.

**Conclusion (one line):** `<§9a row>` — confirmed / bypass as recorded /
refuted / not confirmed / invalid run.

## 5. Review of run 1 — Jingsong

### 5.1 Check of run 1's conclusion

| Part | Agree? | Note |
|---|---|---|
| 1. Validity | | |
| 2. Readings | | |
| 3. Matched row | | |
| 4. Excluded rows | | |
| 5. Observed vs. inferred | | |
| 6. Deviations and gaps | | |

### 5.2 Run 2?

**Yes / no** — the reason, and the date decided.

## 6. Run 2 — Jingsong (optional)

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

## 8. Verdict — Jingsong

| Tier | Verdict (§9a row) | Basis | Date |
|---|---|---|---|
| Unit | | run 1 + review / run 1 + run 2 | |
| Cluster | | run 1 + review / run 1 + run 2 | |

**Feedback filed:** the case file's §10 "Stage-4 feedback" field updated
(commit), and any section amended (which one, commit) — or "none needed".
