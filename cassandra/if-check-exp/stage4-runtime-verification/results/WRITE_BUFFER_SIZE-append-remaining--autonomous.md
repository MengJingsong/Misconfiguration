# WRITE_BUFFER_SIZE-append-remaining--autonomous — stage-4 results  <!-- file: results/WRITE_BUFFER_SIZE-append-remaining--autonomous.md; the stem ends in --guided or --autonomous -->
> **Case:** [`WRITE_BUFFER_SIZE-append-remaining--autonomous`](../../stage3-ai-deep-read/cases/WRITE_BUFFER_SIZE-append-remaining--autonomous.md)
>
> **Status:** audited 2026-10-20 — estimate negative (hard-coded constant); claim under test: the 256 KiB constant does not cap hint memory or disk; not run
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
| **Case-file version** | Autonomous file, sha256 of the whole file after the audit's amendments: `55bf043e43ebcbb70b926e214b47356edd69ce76a20a9d4aee7d832563bc5ab6` (`sha256sum`, run 2026-10-20 before any harness or run; the new line in `_INDEX.md` §4 is this one). Commit holding the file: `cd7fec5` (the step-0 audit commit on `main`). |
| **Harness** | `harness/WRITE_BUFFER_SIZE-append-remaining--autonomous/` — none yet; to be written in step 1 (list in the recommendations below). |
| **Tiers and values** | Unit (B2): `HintsWriter.Session.append(Hint)` and `append(ByteBuffer)` with hint sizes 1 · 100 · 255 · 257 KiB · 1 · 4 · 15 MiB, the 256 KiB buffer and a 64 KiB variant, positive control `HintsBuffer.allocate` at `capacity/2`. Cluster (B3): node A, B down, 100 KiB · 1 MiB · 8 MiB values (2 GiB each), `MAX_HINT_BUFFERS` 3 · 1, `max_hints_size_per_host` 0 · 64 MiB. |
| **Audit bottom line** | **Ready after amendments** — 2026-10-20 |

### 1.1 Design audit

The requirements are in the README, "Step 0 — the design audit". One row per
line of each group; cite the case-file section checked.

| Group | Check | Rating (Met / Partly / Not met) | Note (section checked) |
|---|---|---|---|
| A. Core question | constrained quantity is memory or disk bytes | Met | B1/A2: heap of the temporary buffer, direct memory and disk bytes of hint writing. |
| A. Core question | knob varied, ≥ 3 values incl. default — or another approach, with the reason | Met | The constant cannot be varied (A1); the design varies the hint size across 255/257 KiB, adds a 64 KiB buffer variant, and varies the governing knobs in B3b. |
| A. Core question | real resource measured, not only the counter (gap named) | Met | B2d thread-allocated bytes, file length, `getBytesWritten`; B3d direct pool, `du`, heap, NMT (the 256 KiB buffer inside the pool total is inferred; named). |
| A. Core question | usage driven to the limit and past it | Met | 15 MiB hints are 64 × the buffer; 2 GiB of hints per run far exceeds the 32 MiB slab and the 128 MiB file size. |
| B. Logic | each step says what it establishes | Met | B2e/B3e steps each state their reading. |
| B. Logic | prediction stated in numbers or a clear relation | Met | B2f exact thresholds (alloc ≥ S+12 above 257 KiB, ≈ 0 for `append(ByteBuffer)`); B3f plateaus in MiB and disk totals. |
| B. Logic | every plausible outcome has a conclusions row with its evidence | Partly | The negative-file rows are present (Refuted when usage follows; Confirmed when flat and the control moves; Not confirmed otherwise) but no row for the memory-side control not moving. **Added** (R1). |
| B. Logic | confirmation needs ceiling-follows-knob and direct disallow evidence | Met | Confirmed needs overshoot written in full plus the control binding (unit allocate guard; cluster per-host limit and `MAX_HINT_BUFFERS=1`). |
| B. Logic | alternative explanations and their controls | Met | B2h/B3h: positive controls on both tiers (a binding guard; `max_hints_size_per_host` for disk, `MAX_HINT_BUFFERS=1` for memory), baseline with B up, repeats. |
| C. Specific | a human can follow it from the intro and the prediction/conclusions | Met | A1-A3 and B1 explain the test-only overload and the production path. |
| C. Specific | an AI can run the runbook without re-deriving the code path | Met | Runnable from B2/B3 plus the amendment block. |
| C. Specific | knob, values, workload, commands, observables, sampling, stop conditions exact | Met | Sizes, counts, rates, sampling and cleanup are exact. |
| D. Runnable | harness and environment prerequisites exist or are listed | Partly | Two-node setup exists; the probe and the writer are step-1 work. |
| D. Runnable | workload arithmetic reaches the limit (data, time, disk, memory) | Met | 2 GiB of hints per run; 5 runs with truncation between (R2) and up to about 25 GiB of other data against 47 GB free. |
| D. Runnable | load-bearing citations spot-checked against the pinned clone | Met | Checked: `HintsWriteExecutor.java:50,60`, `HintsWriter.java:136,184,200,232`, `HintsBuffer.java:148-157`, `StorageMetrics.java:45-46`, `StorageProxy.java:2418` (cited as 2413). |

| # | Recommendation | Applied? (amendment date and commit, or "left for stage 3") | Why |
|---|---|---|---|
| R1 | Add a B3g row for `MAX_HINT_BUFFERS=1` not lowering the direct-pool delta (Not confirmed) | Applied 2026-10-20 (B3g, amendment block) | the memory-side control had no row for failing to move |
| R2 | Truncate the table (or recreate the keyspace) between value-size runs | Applied 2026-10-20 (B3e, amendment block) | `truncatehints` leaves 2 GiB of table data and commit log per run |
| R3 | Live setter is at `StorageProxy.java:2418` | Applied 2026-10-20 (amendment block) | citation off by five lines |
| R4 | Write the unit probe, the hint writer and the 1-s sampler | step 1 (harness) | prerequisites, not design changes |

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
