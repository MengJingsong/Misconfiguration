# internode_application_receive_queue_capacity-releaseCapacity-queueCapacity--autonomous — stage-4 results  <!-- file: results/internode_application_receive_queue_capacity-releaseCapacity-queueCapacity--autonomous.md; the stem ends in --guided or --autonomous -->
> **Case:** [`internode_application_receive_queue_capacity-releaseCapacity-queueCapacity--autonomous`](../../stage3-ai-deep-read/cases/internode_application_receive_queue_capacity-releaseCapacity-queueCapacity--autonomous.md)
>
> **Status:** audited 2026-10-20 — estimate positive (release half of the per-connection accounting); claim under test: admitted-but-unreleased inbound bytes ≤ Q + reserves, release returns exactly the part above Q, and retained heap tracks it; not run
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
| **Case-file version** | Autonomous file, sha256 of the whole file after the audit's amendments: `b63484779685490d51411d3ac753f84f9cd78c29e146076c69d43940b7ddb631` (`sha256sum`, run 2026-10-20 before any harness or run; the new line in `_INDEX.md` §4 is this one). Commit holding the file: filled when committed (HEAD before the amendments: `42f9069`). |
| **Harness** | `harness/internode_application_receive_queue_capacity-releaseCapacity-queueCapacity--autonomous/` — none yet; to be written in step 1 (list in the recommendations below). |
| **Tiers and values** | Unit (B2): `AbstractMessageHandler` acquire/release script with Q = 1024 · 4096 B and reserves 2048 · 8192 B, boundary cases, a concurrent release, a mutation that must fail (R1). Cluster (B3): B receives from A, Byteman 200 ms stall, 512 KiB blobs, Q = 64 KiB · 4 MiB (default) · 32 MiB, reserves 16 MiB (set 1) and default 128/512 MiB (set 2). |
| **Audit bottom line** | **Ready after amendments** — 2026-10-20 |

### 1.1 Design audit

The requirements are in the README, "Step 0 — the design audit". One row per
line of each group; cite the case-file section checked.

| Group | Check | Rating (Met / Partly / Not met) | Note (section checked) |
|---|---|---|---|
| A. Core question | constrained quantity is memory or disk bytes | Met | B1/A2: accounted wire bytes of inbound messages (a proxy for heap); the heap proxy gap is named. |
| A. Core question | knob varied, ≥ 3 values incl. default — or another approach, with the reason | Met | B2b Q = 1024 · 4096 B and the yaml default check (4 MiB); B3b Q = 64 KiB · 4 MiB (default) · 32 MiB. |
| A. Core question | real resource measured, not only the counter (gap named) | Met | B3d class histogram of `Mutation`/`byte[]` after `GC.run`, `jstat`, native memory; `queueSize` is not exposed by any metric (named) and is traced with Byteman. |
| A. Core question | usage driven to the limit and past it | Partly | The offered window was reasoned for a closed loop; at CL=ONE the backlog is bounded by the send queues and B's limits. **Amended** (R4). |
| B. Logic | each step says what it establishes | Met | B2e/B3e steps each state their reading. |
| B. Logic | prediction stated in numbers or a clear relation | Partly | B3f used 3 × Q (and 2 types); 512 KiB messages use only the large connection, so the allowance term is 1 × Q. **Corrected** (R2). B2f worked sequence checked by hand (176 borrowed, refusal on the third acquire, release 176 then 0). |
| B. Logic | every plausible outcome has a conclusions row with its evidence | Met | B2g/B3g cover invariants, overshoot, leak, over-release, insensitive test, limit never reached, OOM. |
| B. Logic | confirmation needs ceiling-follows-knob and direct disallow evidence | Met | Confirmed needs the invariant at every unit step and, on a node, a rise with Q plus falling `ThrottledCount` (the proof that the cap bound). |
| B. Logic | alternative explanations and their controls | Partly | The `>` → `>=` mutation is equivalent for the reserve counts, so the sensitivity control could not fail. **Replaced** (R1). B3h has the Byteman-off, reserve-lowering, small-message and repeat controls. |
| C. Specific | a human can follow it from the intro and the prediction/conclusions | Met | A1-A3 and B1 state the mechanism and the claim. |
| C. Specific | an AI can run the runbook without re-deriving the code path | Met | Runnable from B2/B3 plus the amendment block. |
| C. Specific | knob, values, workload, commands, observables, sampling, stop conditions exact | Partly | Message expiry (2 s) would have capped the backlog; `write_request_timeout` was not set. **Amended** (R3). |
| D. Runnable | harness and environment prerequisites exist or are listed | Met | The closed sibling `harness/internode_application_receive_queue_capacity-acquireCapacity-queueCapacity--guided/` already has `hold-handler.btm`, `sample-inbound.py`, `Jmx.java`, `make-node-yaml.sh`, `write-load.py`, `unit-run.sh` to reuse; Byteman and `cassandra-stress` are in the build. |
| D. Runnable | workload arithmetic reaches the limit (data, time, disk, memory) | Partly | Backlog and disk arithmetic corrected (R4): up to about 20 GiB per node per run against 47 GB free; 6 runs of about 12 min. |
| D. Runnable | load-bearing citations spot-checked against the pinned clone | Met | Checked: `AbstractMessageHandler.java:461-474`, `InternodeInboundMetrics.java:53,67-68`, `OutboundConnections.java:68-69`, `InboundMessageHandler.java:128-138`, `ResourceLimits.java:159-169`. |

| # | Recommendation | Applied? (amendment date and commit, or "left for stage 3") | Why |
|---|---|---|---|
| R1 | Replace the `>=` mutation by a clamp/guard-removing mutation that must fail | Applied 2026-10-20 (B2e, B2g row 5, amendment block) | `>=` releases `min(0, bytes)` = 0, an equivalent mutant |
| R2 | Prediction ceilings use Q + reserve (large connection only): 16.1 · 20 · 48 MiB for set 1 | Applied 2026-10-20 (B3f, amendment block) | every 512 KiB message exceeds the 64 KiB threshold |
| R3 | `write_request_timeout: 60000ms` on both nodes | Applied 2026-10-20 (B3a, amendment block) | expired inbound messages are skipped before capacity, capping the backlog at the 2 s default |
| R4 | State the CL=ONE open-loop backlog and the disk plan (up to about 20 GiB per node, delete after each run) | Applied 2026-10-20 (B3c, B4, amendment block) | the 200 client threads do not bound the backlog |
| R5 | Reuse the closed sibling's harness (Byteman hold, inbound sampler, node-yaml maker) | step 1 (harness) | prerequisite, not a design change |

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
