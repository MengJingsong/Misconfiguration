# Queuing playbook — from a lead to a campaign row

*Written 2026-11-17 at the owner's request, by merging rules that were scattered over the campaign plan, README,
verification protocol, lead lists, the direction playbooks and HANDOFF (sources listed in §9).* It covers what
happens **between a lead and the start of a run**: where leads come from, how they are screened, the JIRA check,
how a row is written and prioritized, the checks that gate a run, and how a row changes status afterwards. How a
run is designed and executed is in the direction playbooks; how a result is judged is in the
[verification protocol](verification-protocol.md). For Cassandra the queue is
[`cassandra/campaign-plan.md`](cassandra/campaign-plan.md) "Prioritized queue".

Text that was marked **Proposed** filled a gap or resolved a conflict between earlier sources; the owner ruled on
all of it on 2026-11-17 and it is in force (§8 lists the rulings).

## 1. Who does what

| Step | Who |
|---|---|
| Find and screen leads, run the JIRA check, write the row (§2–§5) | the queuing agent (or the researcher) |
| **Decide** to queue a lead, its priority and its batch | **the queuing agent** (owner's ruling, 2026-11-17), after §3–§4; the researcher may reorder, park or drop any row. Rows from 2026-11-11 to 2026-11-16 say "researcher's decision" |
| Design and run a queued row (direction playbook + protocol) | one agent end to end; no approval gate between design and run, except V7 budgets that need review (§6) |
| Change a row's status, record the result | the agent that ran it; a verdict that needs review waits for the researcher |

**Ruling (owner, 2026-11-17): an agent queues rows.** The queuing agent takes leads (§2), screens them (§3), runs
the JIRA check (§4) and adds the row itself (§5), with the screening record, held ÷ counted evidence and ceiling
arithmetic written into the run log (§7.2). A lead it excludes gets the reason in the run log and, for a phase-1
lead, `screened out: <reason>` in the lead list. Inside a queued row the running agent still chooses its arms (the
"one agent picks its own constraints" rule of the direction playbooks).

## 2. Lead intake

A lead is anything that names a memory holder and a reason its control might not hold. Every lead keeps its
**origin**, written later as the row's `source:` label (§5.3).

| Origin | Where it lives | Notes |
|---|---|---|
| Capacity-enforcement inventory (phase 1 case files, stage-4 results; called *if-check inventory* before 2026-11-17) | `../capacity-enforcement-exp/<system>/` | Default origin; a row without `source:` came from here |
| Phase-1 **OOM lead list** (stage-3 cases and rechecks; blind, back-link or new) | `../capacity-enforcement-exp/<system>/stage3-ai-deep-read/oom-lead-list.md` | **The main phase-1 route.** Only `blind` and `new` leads count as phase 1 predicting phase 2 ([`../README.md`](../README.md)); write the status back (§7.3) |
| Phase-1 bypass notes | [`phase1-bypass-leads.md`](phase1-bypass-leads.md) (N-leads) | |
| JIRA OOM history | `<system>/leads/jira-oom-survey.*` ([`jira-mining-playbook.md`](jira-mining-playbook.md)) | Clues for choosing among phase-1 constraints; fixed bugs → positive controls / regression checks (§4) |
| Data-flow tracing | `<system>/leads/dataflow/` ([`dataflow-tracing-playbook.md`](dataflow-tracing-playbook.md)) | Phase-2-only source (owner, 2026-11-17) |
| OOM-pattern lead list | [`pattern-leads.md`](pattern-leads.md) (L-leads) | |
| A side result of another OOM-exp run | that case file / run log | e.g. U1 from R6-V/C3, B9 from U1 |
| A `reproduced-*` result (custom capacity or tightened budget) | `<system>/cases/candidates/` | A lead for a default-capacity test, not a closed direction |

A lead list is not a result: nothing on it has been run, and inclusion does not confirm a bug.

## 3. Screen the lead

Record keep / exclude and the reason, for every lead considered (§7).

**3.1 Exclude:**

| Exclusion | Why |
|---|---|
| Disk-only holders, and the disk-to-memory causal chain | Skipped / deferred for this campaign; do not reopen silently |
| Overshoot bounded by one item that another limit already caps | Not a protection gap |
| Needs corrupt input | Fault injection by corruption; a JIRA positive-control topic at most |
| Small, heap-derived cap whose excess is a few tens of MiB | Cannot threaten a budget |
| "Large input → large memory" with no accumulation of the system's own | Not a finding; an unprotected-accumulation lead must stay within documented guardrails |

**3.2 Classify, don't exclude, a disabled or unlimited guard.** A guard that is off or unlimited at defaults is
an **unprotected configuration**: in scope (C2 was verified on exactly that), labelled separately, never called a
bypass. *This supersedes the "guard off by default" exclusion in the phase1-bypass-leads screening table.*

**3.3 Establish the contract and a control.** Before calling it a bypass, state what the control promises (the
actual cap contract) and show a control applies. A phase-1 case estimated negative supplies no verified cap;
true-positive, weak and undetermined cases supply leads. An intentional pool fallback is not automatically a
broken cap.

**3.4 Prefer the smallest mechanism** that answers an open coverage question; do not combine counters for the same
allocation; a count cap qualifies when count × per-item footprint is memory-significant; look at executor, queue
and connection bounds first.

**3.5 Ask the holder questions** (the guided playbook's E1–E4, the pattern-leads §3 "Ask" lists): what is counted and
for how long; what happens at the limit; per what owner and how many; which budget, shared with what.

**3.6 Measure held ÷ counted before any OOM run** (pattern-leads process rule 5). One histogram or one stage-4
measurement is enough. A phase-1 stage-4 result that already measured the real resource against the counter
(e.g. the 2026-11-17 recheck runs) satisfies this step; cite it.

**3.7 Feasibility (ceiling) check:** Σ contract capacities + baseline against the budget the row would use
(defaults resolved at the planned heap and container). At defaults this is often the deciding screen. If the
ceiling cannot reach the budget, the lead is excluded or rewritten (multiplicity, overlap, a realistic fault),
not queued with raised values.

**3.8 Prefer realistic faults to raised values** (disk stall, slow replica, dead thread), and check the docs: a
behaviour the yaml or docs already warn about is "documented", not "undocumented".

## 4. Prior-art (JIRA) check

Required before a row is added or a lead is picked for a batch (rule 2026-11-16).

1. Start from the survey (`<system>/leads/jira-oom-survey.csv`, `.md` §5, `jira-prior-art-verified-cases.md`);
   search JIRA itself (REST search on `project = CASSANDRA`) where the survey does not cover the mechanism.
2. Record every query with its hit count, and the verdict: **new**, **known-open**, **known-fixed** (→ regression
   check), **by design**, **documented**, **unclear**. No hit is evidence, not proof.
3. Consequence: known-fixed → queue only as a **regression check** or **positive control**; by design → queue only
   if the case can show a broken or misleading documented contract; a reproduced fixed bug is a positive control,
   never a new finding.
4. **Nothing is posted to JIRA** (researcher, 2026-11-17): the check serves to find OOM-exp candidates.
5. Write the result into the row with this block:
   `**JIRA (checked YYYY-MM-DD):** <keys with status/fix version>; queries: \`…\` (n hits), …; verdict: <word>.`

Rows queued before the rule (C5, B2–B4, C4/B5) get the check before they start (ruling 2026-11-17); a lead list
entry that was checked records the same block there (as N13–N16 do).

## 5. Write the row

**5.1 ID.** One prefix per kind; the next free number; IDs are never reused.

| Prefix | Use |
|---|---|
| C | convergence investigation |
| B | bypass investigation |
| U | unprotected-accumulation investigation |
| S | stacked combo case ([combo playbook](combo-playbook.md)) |
| R | recheck of an earlier result (suffix `-V`: re-test at default constraints and an acceptable budget) |

A positive control or regression check takes the direction prefix and the label
`· positive control` or `· regression check` (no new prefix). A shared ID (C4/B5) is used only when one
investigation tests both directions. Explain every prefix the first time it is shown (README "ID prefixes"
rule); L, N, J-patterns, P-patterns and S-patterns are lead or pattern labels, not campaign IDs.

**5.2 Priority** is written after the ID: `B9 / P2`. Criteria (ruled 2026-11-17):

| Level | Criteria |
|---|---|
| **P1** | reachable at shipped defaults with an acceptable budget in sight (§3.7), mechanism measured or source-checked (§3.6), JIRA verdict new or known-open, and one node set can run it |
| **P2** | needs a timing window, a non-default but shipped configuration (e.g. `cassandra_latest.yaml`), or the held ÷ counted measurement is still missing |
| **P3** | low plausibility, expensive, or blocked on another row |

The lead lists' own scales (pattern-leads Priority 1–5, phase1-bypass-leads "OOM plausibility") rank leads, not rows; a
row gets a P-level only when queued. Rows are listed in P order; within a level, newest last.

**5.3 Row format** (`ID / priority | Direction · sub-direction · source | Hypothesis and workload | Decisive
evidence / control`):

- **Direction · sub-direction** from the README (multiplicity, concurrency/surge, replacement-overlap,
  standing-pool; release-defect, accounting mismatch, exempt caller, pool fallback, failed reservation,
  periodic/late enforcement, …); the sub-direction is the hypothesis chosen up front. Tag **mixed** later if the
  evidence crosses directions. Mark `unprotected` for §3.2.
- **`source:`** in backticks, omitted for capacity-enforcement inventory rows. Syntax (ruled 2026-11-17):
  `source: JIRA-<key>[ positive control | regression]`, `source: flow:<flow>`, `source: lead:<N4|L7>`,
  `source: phase1:<case stem> (blind|back-link|new)` (a row of the phase-1 OOM lead list),
  `source: <case ID> side result`.
- **Hypothesis cell**, in order: `**New YYYY-MM-DD, queued by agent (queuing playbook).**` (rows before
  2026-11-17: `researcher's decision`); then status updates (bold, dated,
  newest first, §7); then the hypothesis and planned workload; then the JIRA block (§4).
- **Decisive evidence / control:** the measurement that decides, the matched control, the planned intervention,
  and the budget regime.

**5.4 The queuing record** is the screening record (§3), the held ÷ counted evidence (§3.6) and the ceiling
arithmetic (§3.7), written in the run log entry of the queuing pass (§7.2) next to the row's ID.

## 6. Before the run starts (gate)

A queued row may start only when all of these exist (details in the [protocol](verification-protocol.md)):

1. **Protection map**, one row per allocation domain, comparison scope fixed before the run (phase-1 verdicts are
   leads, not substitutes).
2. **Configuration and budget audit**: capacity regime (default / custom) and budget recorded separately, with
   resolved values (`MaxDirectMemorySize` included; `cassandra-env.sh` sizes it from RAM even with a hand-set heap).
3. **Dated design**: mechanism, predicted response, stopping budget, finite time or attempt limit; reachability
   confirmed at modest load first; workload multiplicity and overlap tried before shrinking the budget.
4. **V7 budget**: a heap or direct budget ≥ 512 MiB needs no review, 2 GiB is ideal, search upward for the
   largest failing budget; a container limit is argued case by case and **reviewed by the researcher before
   readings**.
5. **Node preflight** ([`cassandra/node-requirements.md`](cassandra/node-requirements.md)): inventory, build smoke
   test, frozen budgets, one measured experiment per victim, inactive peers not counted; never mix aarch64 and x86
   nodes in one case's matched arms; check what runs on the node first (available nodes: root `HANDOFF.md`).
6. A design that relies on a guardrail uses a **non-superuser** (the default authenticator makes every client a
   superuser; phase1-bypass-leads N8).

## 7. Row lifecycle and recording

**7.1 Statuses of a row.** Single vocabulary (ruled 2026-11-17), written as the first bold line of the hypothesis cell:

| Row status | Meaning |
|---|---|
| `queued` | decided, not started |
| `running` | a batch has it |
| `result: <case status>` | the case reached a status of the protocol (`verified-OOM`, `verified-gap`, `reproduced-*`, `candidate`, `negative`, each with its label) |
| `parked: <blocker>` | stopped for a named reason; resumable |
| `dropped: <reason>` | the researcher closed it without a result (e.g. screened out after queuing) |
| `superseded by <ID>` | replaced by another row; kept for history |

Rows are never deleted; the original hypothesis text stays below the status lines (as `*Original:*`). If the
mechanism changes mid-run, file a new hypothesis (a new row or ID) instead of claiming the old one reproduced. A
first-batch blocker is recorded and work continues on an independent row.

**7.2 Record every batch** in `<system>/cases/_run-log.md`: candidates considered, picked and skipped (with the
§3 reason), status changes, and the stopping reason; log each survey and traced flow. The campaign
plan's queue, not the run log's 2026-11-06 status tables, governs selection; those tables are history.

**7.3 Back-propagate** to the lead's origin when a row is added or closed: mark the lead-list entry
`queued as <ID>` / `result: …` (phase1-bypass-leads §2–§3, pattern-leads §4, the survey §5), and the
Status column of `oom-lead-list.md` (`lead` → `stage-4 measured` → `queued as <ID>` → `verified` / `negative`,
or `screened out: <reason>`; added 2026-11-17), which is what lets phase 1's hit rate be counted.

**7.4 When a row first reaches `verified-*`,** run [`../backlink-playbook.md`](../backlink-playbook.md) and add
the link row; record whether the lead came from phase 1.

**7.5 Commit only when asked.**

## 8. Owner's rulings (2026-11-17)

The open decisions of the first version, and how they were settled:

1. **Who queues** (§1): **an agent queues rows**; the researcher may reorder, park or drop them.
2. **Priority criteria** (§5.2), **row status vocabulary** (§7.1), **`source:` syntax and ID rules** (§5.1, §5.3):
   accepted as proposed; `source: recheck:` became `source: phase1:` (a phase-1 lead may come from a new case, not
   only a recheck).
3. **Upstream reporting:** **nothing is posted to JIRA** and no upstream report is filed; the JIRA check only
   finds OOM-exp candidates. README and campaign-plan text about upstream reports, and the B1/B7/U1 "upstream"
   next steps, were reworded the same day.
4. **Data-flow F1** no longer blocks new configuration pairs (pattern-leads process rule 1 amended).
5. **Rows queued before the JIRA rule** (C5, B2–B4, C4/B5) get the check before they start.
6. **Stale text corrected** the same day: `_INDEX.md` "V1–V5" (now V1–V7) and its "(none yet)" lines; the run
   log's status tables (history, not selection); HANDOFF's pointer to a combo-playbook "step 5"; the campaign
   plan's "Not yet started" under the lead-source pilots (J1 done); the jira-mining playbook's unconditional "each
   plausible lead becomes a campaign-plan row" (now: through this playbook).

## 9. Sources merged

| Topic | Earlier source(s) |
|---|---|
| Lead sources, origin labels | README "Lead sources"; campaign-plan "Lead-source pilots"; `_INDEX.md` header; direction playbooks' first steps |
| Screening | phase1-bypass-leads §1; protocol "Unprotected results", "Classification by measurement"; custom-convergence "Picking cases"; bypass playbook selection; pattern-leads §3 and process rules |
| JIRA check | campaign-plan "Prioritized queue" rule; jira-mining playbook; survey §5; prior-art file vocabulary; HANDOFF rule |
| IDs, priority, row format | README "ID prefixes"; campaign-plan header and rows; data-flow playbook outputs |
| Pre-run gate | protocol (protection map, configuration and budget audit, design, V6–V7); default-convergence playbook; node-requirements; HANDOFF nodes |
| Lifecycle, recording | protocol statuses and progress statuses; run log; custom-convergence and bypass playbooks' recording steps; back-link playbook |
