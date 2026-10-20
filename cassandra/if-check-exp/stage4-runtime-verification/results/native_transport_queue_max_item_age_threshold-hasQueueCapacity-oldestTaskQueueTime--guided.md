# native_transport_queue_max_item_age_threshold-hasQueueCapacity-oldestTaskQueueTime--guided — stage-4 results  <!-- file: results/native_transport_queue_max_item_age_threshold-hasQueueCapacity-oldestTaskQueueTime--guided.md; the stem ends in --guided or --autonomous -->
> **Case:** [`native_transport_queue_max_item_age_threshold-hasQueueCapacity-oldestTaskQueueTime--guided`](../../stage3-ai-deep-read/cases/native_transport_queue_max_item_age_threshold-hasQueueCapacity-oldestTaskQueueTime--guided.md)
>
> **Status:** audited 2026-10-20 — estimate negative; claim under test: queued request bytes do not fall with the age threshold (source predicts Refuted in throwing mode); not run
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
| **Case-file version** | Guided file, hash of §9's text after the audit's amendments (`sed -n '/^## 9\. /,/^## 10\. /p' <file> | git hash-object --stdin`): `dcad2ce895b243c8d9efb09f392df461e142dc89`, computed 2026-10-20 before any harness or run. §9a is frozen at this version, including the dated block 9f. Commit holding the file: `cd7fec5` (the step-0 audit commit on `main`). |
| **Harness** | `harness/native_transport_queue_max_item_age_threshold-hasQueueCapacity-oldestTaskQueueTime--guided/` — none yet; to be written in step 1 (list in the recommendations below). |
| **Tiers and values** | Unit (9a step 1): `Dispatcher` over a held executor, `hasQueueCapacity()` at thresholds above, at and below the head's age. Cluster (9e): one node, `native_transport_max_threads` 4, Byteman stall, 100 × 64 KiB requests/s for 60 s, threshold off · 0.5 · 0.1 · 0.02 (throwing mode; one repeat in default mode at 0.1), positive control with in-flight limit 8 MiB. |
| **Audit bottom line** | **Ready after amendments** — 2026-10-20 |

### 1.1 Design audit

The requirements are in the README, "Step 0 — the design audit". One row per
line of each group; cite the case-file section checked.

| Group | Check | Rating (Met / Partly / Not met) | Note (section checked) |
|---|---|---|---|
| A. Core question | constrained quantity is memory or disk bytes | Met | 9a Claim, 9d: off-heap request bytes queued. |
| A. Core question | knob varied, ≥ 3 values incl. default — or another approach, with the reason | Met | 9b values off (`Double.MAX_VALUE`), 0.5, 0.1, 0.02 (× the 12 s `native_transport_timeout`). |
| A. Core question | real resource measured, not only the counter (gap named) | Partly | The queued-bytes gauge was written as `type=Client,…`. **Amended** (R1): `type=Client,name=RequestsSize` plus the pool `Size` gauge. |
| A. Core question | usage driven to the limit and past it | Met | 375 MiB offered per run (100/s × 64 KiB × 60 s) against ceilings of 1.5 MiB (0.02) to 37.5 MiB (0.5) in throwing mode; the control budget (8 MiB) is far below the offer. |
| B. Logic | each step says what it establishes | Met | 9a block matches steps, prediction and rows. |
| B. Logic | prediction stated in numbers or a clear relation | Partly | "Same at every threshold" had no numeric edge. **Amended** (R4). |
| B. Logic | every plausible outcome has a conclusions row with its evidence | Met | Rows: same + control caps (Confirmed), falls with the threshold (Refuted), falls only in throwing mode (Refuted for that mode), never grows with the check off (Invalid), control does not cap (Not confirmed). |
| B. Logic | confirmation needs ceiling-follows-knob and direct disallow evidence | Met | Confirmed needs equal peaks across thresholds, refusals in the log/client error (queue-time text) and the control capping. |
| B. Logic | alternative explanations and their controls | Met | Control: in-flight budget on the same workload; the age-check-off baseline; both overload modes. |
| C. Specific | a human can follow it from the intro and the prediction/conclusions | Met | Intro explains the time check vs the byte budget and the mode split. |
| C. Specific | an AI can run the runbook without re-deriving the code path | Partly | The stall rule and the mode setting were not exact. **Amended** (R2, R3). |
| C. Specific | knob, values, workload, commands, observables, sampling, stop conditions exact | Partly | Rate, duration, thread count, client timeout exact; stall and mode fixed by R2, R3; `fixed_rate_writer.py` named, not written. |
| D. Runnable | harness and environment prerequisites exist or are listed | Partly | `fixed_rate_writer.py` and the Byteman stall rule are step-1 work. |
| D. Runnable | workload arithmetic reaches the limit (data, time, disk, memory) | Met | 375 MiB per run on a node with 251 GiB RAM and 47 GB disk; 60 s × 8 runs. |
| D. Runnable | load-bearing citations spot-checked against the pinned clone | Met | Checked: `Dispatcher.java:341-348` (`hasQueueCapacity`), `SEPExecutor.java:88-100` (`oldestTaskQueueTime` reads the queue head only), `CQLMessageHandler.java:208,237,585,618`, `PreV5Handlers.java:165,201`, `Config.java:1393-1399`, `StorageService.java:7638`, `ClientMetrics.java:129`. |

| # | Recommendation | Applied? (amendment date and commit, or "left for stage 3") | Why |
|---|---|---|---|
| R1 | Queued bytes gauge = `type=Client,name=RequestsSize` + networking pool `Size` | Applied 2026-10-20 (9d, 9f) | the filed name was a placeholder |
| R2 | Byteman stall at `Dispatcher$RequestProcessor.run` until a flag file; four workers stalled, the rest queue; write and check in step 1 | Applied 2026-10-20 (9b, 9c, 9f) | `oldestTaskQueueTime` reads only queued tasks, so the stall must hold running workers |
| R3 | Mode via `native_transport_throw_on_overload` in the yaml (connection default) | Applied 2026-10-20 (9b, 9f) | `PipelineConfigurator.java:309-313` uses it when the STARTUP option is absent |
| R4 | Numeric edges: noise band = range of three check-off repeats; "falls" = > 50 % below and > 3× the band | Applied 2026-10-20 (9a, 9f) | fixed before any reading |
| R5 | Write `fixed_rate_writer.py` and the stall rule | step 1 (harness) | prerequisites, not design changes |

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
