# batch_size_fail_threshold-verifyBatchSize-failThreshold--guided — stage-4 results  <!-- file: results/batch_size_fail_threshold-verifyBatchSize-failThreshold--guided.md; the stem ends in --guided or --autonomous -->
> **Case:** [`batch_size_fail_threshold-verifyBatchSize-failThreshold--guided`](../../stage3-ai-deep-read/cases/batch_size_fail_threshold-verifyBatchSize-failThreshold--guided.md)
>
> **Status:** audited 2026-10-20 — estimate negative; claim under test: coordinator memory for a batch follows the batch size, not the threshold; not run
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
| **Case-file version** | Guided file, hash of §9's text after the audit's amendments (`sed -n '/^## 9\. /,/^## 10\. /p' <file> | git hash-object --stdin`): `ce9fe324dbdb69c9c358b3f8a6df117289f8294d`, computed 2026-10-20 before any harness or run. §9a is frozen at this version, including the dated block 9f. Commit holding the file: `cd7fec5` (the step-0 audit commit on `main`). |
| **Harness** | `harness/batch_size_fail_threshold-verifyBatchSize-failThreshold--guided/` — none yet; to be written in step 1 (list in the recommendations below). |
| **Tiers and values** | Unit (9c): `BatchStatement.execute` under `CQLTester`, thresholds 50 KiB · 500 KiB · 5 MiB. Cluster (9e): one node, `-Xmx4G`, native v5, 64-partition unlogged batches of 1 · 4 · 16 MiB, positive control with `native_transport_max_message_size` 512 KiB. |
| **Audit bottom line** | **Ready after amendments** — 2026-10-20 |

### 1.1 Design audit

The requirements are in the README, "Step 0 — the design audit". One row per
line of each group; cite the case-file section checked.

| Group | Check | Rating (Met / Partly / Not met) | Note (section checked) |
|---|---|---|---|
| A. Core question | constrained quantity is memory or disk bytes | Met | 9a Claim, 9d: heap bytes allocated on the coordinator for one batch. |
| A. Core question | knob varied, ≥ 3 values incl. default — or another approach, with the reason | Met | 9b values 50 KiB (default, `Config.java:332`), 500 KiB, 5 MiB; batch sizes 1, 4, 16 MiB. |
| A. Core question | real resource measured, not only the counter (gap named) | Partly | 9d reads the executing thread's allocation only; netty decode and replica work are outside it (the trap is named). The control would read 0 trivially. **Amended** (R2): also the networking pool `Size` delta and heap high-water. |
| A. Core question | usage driven to the limit and past it | Partly | At 5 MiB the 1 and 4 MiB batches are accepted. The 16 MiB batch also exceeded the transport's 16 MiB default and the filed 256 MiB hold-fixed value would fail at startup with the default in-flight limits. **Amended** (R1, R5). |
| B. Logic | each step says what it establishes | Met | 9a "How this verifies" block matches steps, prediction and rows. |
| B. Logic | prediction stated in numbers or a clear relation | Partly | "Within the noise band" and "falls" were not numeric. **Amended** (R3). |
| B. Logic | every plausible outcome has a conclusions row with its evidence | Met | Rows: tracks the batch size and the control cuts it (Confirmed), falls with the threshold (Refuted), flat in both (Not confirmed), control flat (Not confirmed), no batch reaches it (Invalid). |
| B. Logic | confirmation needs ceiling-follows-knob and direct disallow evidence | Met | Confirmed needs the allocation to track the batch size, the rejection iff size > threshold (client error + log line, `BatchStatement.java:358`) and the control cutting it. |
| B. Logic | alternative explanations and their controls | Met | Control: a transport cap that binds before the build; fixed heap, one batch in flight, batch type fixed (9b). |
| C. Specific | a human can follow it from the intro and the prediction/conclusions | Met | Intro and 9a explain why the check runs after the build and what each row means. |
| C. Specific | an AI can run the runbook without re-deriving the code path | Partly | `send_batches.py` and the Byteman rule are named, not written (step 1); the control's discard needs protocol v5. **Amended** (R4). |
| C. Specific | knob, values, workload, commands, observables, sampling, stop conditions exact | Partly | Transport settings and protocol were not exact (R1, R4); thread-allocation arithmetic is exact. |
| D. Runnable | harness and environment prerequisites exist or are listed | Partly | `send_batches.py`, the Byteman allocation rule and a v5 client are step-1 work; the closed `native_transport_receive_queue_capacity` harness has a `SimpleClient` to reuse. |
| D. Runnable | workload arithmetic reaches the limit (data, time, disk, memory) | Met | 20 batches × (1+4+16 MiB) × 3 thresholds is small against 4 GiB heap and 47 GB disk; with R1 the 16 MiB batch passes the transport. |
| D. Runnable | load-bearing citations spot-checked against the pinned clone | Met | Checked: `BatchStatement.java:340-358` (threshold compare `:352`, throw `:358`), `Config.java:332` default 50 KiB, `DatabaseDescriptor.java:2071`, `:911-915` and the derived default `:3237-3245`. |

| # | Recommendation | Applied? (amendment date and commit, or "left for stage 3") | Why |
|---|---|---|---|
| R1 | Set `native_transport_max_request_data_in_flight` and `…_per_ip` to 256 MiB and `native_transport_max_message_size` to 64 MiB (control: 512 KiB) | Applied 2026-10-20 (9b, 9f) | the filed 256 MiB would refuse to start at `-Xmx4G`; the derived default (16 MiB) would refuse the 16 MiB batch |
| R2 | Control also reads the networking pool `Size` delta and heap high-water | Applied 2026-10-20 (9d, 9f) | a discarded request never reaches `execute`, so the thread reading is trivially 0 |
| R3 | Define "the same" (medians within 10 %) and "falls" (more than 50 % below) | Applied 2026-10-20 (9a, 9f) | numeric edges fixed before any reading |
| R4 | All arms on native protocol v5 via `SimpleClient` | Applied 2026-10-20 (9c, 9f) | the discard branch is the v5 large-message path |
| R5 | Read the prediction on the rejected pairs only; accepted pairs show the build | Applied 2026-10-20 (9a, 9f) | at 5 MiB the 1 and 4 MiB batches are accepted |
| R6 | Write `send_batches.py` and the Byteman allocation rule | step 1 (harness) | prerequisites, not design changes |

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
