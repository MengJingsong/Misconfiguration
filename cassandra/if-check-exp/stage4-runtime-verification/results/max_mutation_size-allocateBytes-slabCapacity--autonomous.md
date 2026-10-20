# max_mutation_size-allocateBytes-slabCapacity--autonomous — stage-4 results  <!-- file: results/max_mutation_size-allocateBytes-slabCapacity--autonomous.md; the stem ends in --guided or --autonomous -->
> **Case:** [`max_mutation_size-allocateBytes-slabCapacity--autonomous`](../../stage3-ai-deep-read/cases/max_mutation_size-allocateBytes-slabCapacity--autonomous.md)
>
> **Status:** audited 2026-10-20 — estimate positive (caveat: a fixed-size slab allocated up front); claim under test: hint direct memory = slabs × slab size, flat in hint volume; not run
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
| **Case-file version** | Autonomous file, sha256 of the whole file after the audit's amendments: `8ecb18b22d2fe470942b0dbbb77bfb1636fddd9cda4c3f5b0058d467dfe352ca` (`sha256sum`, run 2026-10-20 before any harness or run; the new line in `_INDEX.md` §4 is this one). Commit holding the file: `cd7fec5` (the step-0 audit commit on `main`). |
| **Harness** | `harness/max_mutation_size-allocateBytes-slabCapacity--autonomous/` — none yet; to be written in step 1 (list in the recommendations below). |
| **Tiers and values** | Unit (B2): `HintsBuffer.create(C)` with C = 1 · 4 · 32 MiB, fill to the first null, boundary at `C/2 − 12`, `recycle()`, plus the derived-slab arithmetic. Cluster (B3): node A with `max_mutation_size` unset (16 MiB, slab 32 MiB) · 4096 KiB (floor) · 32768 KiB (slab 64 MiB), and `MAX_HINT_BUFFERS` 3 · 1; node B down. |
| **Audit bottom line** | **Ready after amendments** — 2026-10-20 |

### 1.1 Design audit

The requirements are in the README, "Step 0 — the design audit". One row per
line of each group; cite the case-file section checked.

| Group | Check | Rating (Met / Partly / Not met) | Note (section checked) |
|---|---|---|---|
| A. Core question | constrained quantity is memory or disk bytes | Met | B1/A2: direct (off-heap) memory of the hint slabs. |
| A. Core question | knob varied, ≥ 3 values incl. default — or another approach, with the reason | Met | B2b slabs 1 · 4 · 32 MiB (default 32); B3b `max_mutation_size` default · 4 MiB · 32 MiB and `MAX_HINT_BUFFERS` 3 · 1. |
| A. Core question | real resource measured, not only the counter (gap named) | Met | B3d direct pool deltas and RSS; slab fill is private and inferred (named). |
| A. Core question | usage driven to the limit and past it | Met | About 420 MB offered = 13 slabs of 32 MiB, 6.5 of 64 MiB; B2c fills to the first null. |
| B. Logic | each step says what it establishes | Met | B2e/B3e steps each state their reading. |
| B. Logic | prediction stated in numbers or a clear relation | Met | B2f exact (n = floor(C/(h+12)), growth exactly C, `C/2 − 12` legal); B3f 32–96 MiB plateau, 64–192 MiB at 64 MiB slabs. |
| B. Logic | every plausible outcome has a conclusions row with its evidence | Partly | B3g had no row for `MAX_HINT_BUFFERS=1` and none for a 17 MiB write accepted. **Added** (R1). |
| B. Logic | confirmation needs ceiling-follows-knob and direct disallow evidence | Met | Confirmed needs a plateau at k × slab with k ≤ `MAX_HINT_BUFFERS` that scales with the slab; the disallow evidence is the closed slab and the null allocation. |
| B. Logic | alternative explanations and their controls | Met | B3h: hinted handoff off, noise from a repeat, B down for the whole run; `MAX_HINT_BUFFERS=1` is a second knob that binds. |
| C. Specific | a human can follow it from the intro and the prediction/conclusions | Met | A1-A3 and B1 state claim, derivation and floor. |
| C. Specific | an AI can run the runbook without re-deriving the code path | Met | Runnable from B2/B3 plus the amendment block. |
| C. Specific | knob, values, workload, commands, observables, sampling, stop conditions exact | Partly | `hints_flush_period` was written "3600000ms-style" and the 17 MiB bullet mixed two guards. **Amended** (R2, R3). |
| D. Runnable | harness and environment prerequisites exist or are listed | Partly | Two-node setup exists; the unit probe and the hint writer are step-1 work (`cassandra-stress` or a CQL loop, 8 MiB values). |
| D. Runnable | workload arithmetic reaches the limit (data, time, disk, memory) | Met | Disk under 3 GB per run; heap 2 GiB, `MaxDirectMemorySize` 2 GiB bound the worst case. |
| D. Runnable | load-bearing citations spot-checked against the pinned clone | Met | Checked: `HintsBuffer.java:58,75-96,148-157` (`create`, `isClosed`, `capacity`, `remaining`, `recycle`, `capacity/2` guard), `HintsService.java:79,110`, `DatabaseDescriptor.java:894-901`, `Config.java:444-448` (`hints_flush_period` 10 s). |

| # | Recommendation | Applied? (amendment date and commit, or "left for stage 3") | Why |
|---|---|---|---|
| R1 | Add B3g rows for `MAX_HINT_BUFFERS=1` (plateau at one slab; or equal to the default) and the 17 MiB write accepted | Applied 2026-10-20 (B3g, amendment block) | outcomes the prediction names had no row |
| R2 | The 17 MiB write is refused at the coordinator; the slab's `capacity/2` guard is a unit-tier test only | Applied 2026-10-20 (B3f, amendment block) | two guards were mixed in one bullet |
| R3 | `hints_flush_period: 3600000ms` | Applied 2026-10-20 (B3a, amendment block) | exact value |
| R4 | Write the unit probe and the hint writer | step 1 (harness) | prerequisites, not design changes |

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
