# Queuing playbook — from a lead to a campaign row

*Written 2026-11-17 at the owner's request, by merging rules that were scattered over the campaign plan, README,
verification protocol, lead lists, the direction playbooks and HANDOFF (sources listed in §9).* It covers what
happens **between a lead and the start of a run**: where leads come from, how they are screened, the JIRA check,
how a row is written and prioritized, the checks that gate a run, and how a row changes status afterwards. How a
run is designed and executed is in the direction playbooks; how a result is judged is in the
[verification protocol](verification-protocol.md). For Cassandra the queue is
[`cassandra/campaign-plan.md`](cassandra/campaign-plan.md) "Prioritized queue".

Text marked **Proposed** fills a gap or resolves a conflict between earlier sources; it applies once the owner
confirms it (§8).

## 1. Who does what

| Step | Who |
|---|---|
| Find and screen leads, run the JIRA check, write the proposal (§2–§5) | an agent or the researcher |
| **Decide** to queue a lead, its priority and its batch | **the researcher** (in practice every row since 2026-11-11 says "researcher's decision") |
| Design and run a queued row (direction playbook + protocol) | one agent end to end; no approval gate between design and run, except V7 budgets that need review (§6) |
| Change a row's status, record the result | the agent that ran it; a verdict that needs review waits for the researcher |

**Proposed:** an agent never adds a queue row on its own; it writes a **proposal** (§5) in its report or in the
batch log, and the row is added when the researcher decides. This replaces "one agent picks its own constraints"
(HANDOFF, custom-convergence and bypass playbooks) for queuing; inside a queued row the agent still chooses its
arms.

## 2. Lead intake

A lead is anything that names a memory holder and a reason its control might not hold. Every lead keeps its
**origin**, written later as the row's `source:` label (§5.3).

| Origin | Where it lives | Notes |
|---|---|---|
| If-check inventory (phase 1 case files, stage-4 results) | `../capacity-enforcement-exp/<system>/` | Default origin; a row without `source:` came from here |
| Phase-1 **recheck flags** (blind or back-link) | `../capacity-enforcement-exp/<system>/stage3-ai-deep-read/recheck-flags.md` | Only blind flags count as phase 1 predicting phase 2 ([`../README.md`](../README.md)) |
| Phase-1 bypass notes | [`capacity-enforcement-bypass-leads.md`](capacity-enforcement-bypass-leads.md) (N-leads) | |
| JIRA OOM history | `<system>/leads/jira-oom-survey.*` ([`jira-mining-playbook.md`](jira-mining-playbook.md)) | Clues for choosing among phase-1 constraints; fixed bugs → positive controls / regression checks (§4) |
| Data-flow tracing | `<system>/leads/dataflow/` ([`dataflow-tracing-playbook.md`](dataflow-tracing-playbook.md)) | Phase-2-only source (owner, 2026-11-17) |
| OOM-pattern lead list | [`OOM-leads.md`](OOM-leads.md) (L-leads) | |
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
bypass. *This supersedes the "guard off by default" exclusion in the bypass-leads screening table.*

**3.3 Establish the contract and a control.** Before calling it a bypass, state what the control promises (the
actual cap contract) and show a control applies. A phase-1 case estimated negative supplies no verified cap;
true-positive, weak and undetermined cases supply leads. An intentional pool fallback is not automatically a
broken cap.

**3.4 Prefer the smallest mechanism** that answers an open coverage question; do not combine counters for the same
allocation; a count cap qualifies when count × per-item footprint is memory-significant; look at executor, queue
and connection bounds first.

**3.5 Ask the holder questions** (the guided playbook's E1–E4, the OOM-leads §3 "Ask" lists): what is counted and
for how long; what happens at the limit; per what owner and how many; which budget, shared with what.

**3.6 Measure held ÷ counted before any OOM run** (OOM-leads process rule 5). One histogram or one stage-4
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

**Proposed:** rows queued before the rule (C5, B2–B4, C4/B5) get the check before they start; a lead list entry
that was checked records the same block there (as N13–N16 do).

## 5. Write the proposal (and, once decided, the row)

**5.1 ID.** One prefix per kind; the next free number; IDs are never reused.

| Prefix | Use |
|---|---|
| C | convergence investigation |
| B | bypass investigation |
| U | unprotected-accumulation investigation |
| S | stacked combo case ([combo playbook](combo-playbook.md)) |
| R | recheck of an earlier result (suffix `-V`: re-test at default constraints and an acceptable budget) |

**Proposed:** a positive control or regression check takes the direction prefix and the label
`· positive control` or `· regression check` (no new prefix). A shared ID (C4/B5) is used only when one
investigation tests both directions. Explain every prefix the first time it is shown (README "ID prefixes"
rule); L, N, J-patterns, P-patterns and S-patterns are lead or pattern labels, not campaign IDs.

**5.2 Priority** is written after the ID: `B9 / P2`. **Proposed criteria** (today only examples exist):

| Level | Criteria |
|---|---|
| **P1** | reachable at shipped defaults with an acceptable budget in sight (§3.7), mechanism measured or source-checked (§3.6), JIRA verdict new or known-open, and one node set can run it |
| **P2** | needs a timing window, a non-default but shipped configuration (e.g. `cassandra_latest.yaml`), or the held ÷ counted measurement is still missing |
| **P3** | low plausibility, expensive, or blocked on another row |

The lead lists' own scales (OOM-leads Priority 1–5, bypass-leads "OOM plausibility") rank leads, not rows; a
row gets a P-level only when queued. Rows are listed in P order; within a level, newest last.

**5.3 Row format** (`ID / priority | Direction · sub-direction · source | Hypothesis and workload | Decisive
evidence / control`):

- **Direction · sub-direction** from the README (multiplicity, concurrency/surge, replacement-overlap,
  standing-pool; release-defect, accounting mismatch, exempt caller, pool fallback, failed reservation,
  periodic/late enforcement, …); the sub-direction is the hypothesis chosen up front. Tag **mixed** later if the
  evidence crosses directions. Mark `unprotected` for §3.2.
- **`source:`** in backticks, omitted for if-check rows. **Proposed** syntax:
  `source: JIRA-<key>[ positive control | regression]`, `source: flow:<flow>`, `source: lead:<N4|L7>`,
  `source: recheck:<case stem> (blind|back-link)`, `source: <case ID> side result`.
- **Hypothesis cell**, in order: `**New YYYY-MM-DD, researcher's decision.**`; then status updates (bold, dated,
  newest first, §7); then the hypothesis and planned workload; then the JIRA block (§4).
- **Decisive evidence / control:** the measurement that decides, the matched control, the planned intervention,
  and the budget regime.

**5.4 A proposal** is the same four cells, plus the screening record (§3), the held ÷ counted evidence (§3.6) and
the ceiling arithmetic (§3.7), handed to the researcher.

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
   superuser; bypass-leads N8).

## 7. Row lifecycle and recording

**7.1 Statuses of a row.** **Proposed** single vocabulary, written as the first bold line of the hypothesis cell:

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
§3 reason), status changes, and the stopping reason; log each survey and traced flow. **Proposed:** the
campaign plan's queue, not the run log's 2026-11-06 status tables, governs selection; those tables are history.

**7.3 Back-propagate** to the lead's origin when a row is added or closed: mark the lead-list entry
`queued as <ID>` / `result: …` (bypass-leads §2–§3, OOM-leads §4, the survey §5), and **Proposed:** a status
column in `recheck-flags.md` (`lead` → `stage-4 measured` → `queued as <ID>` → `verified` / `negative`), which
is what lets phase 1's hit rate be counted.

**7.4 When a row first reaches `verified-*`,** run [`../backlink-playbook.md`](../backlink-playbook.md) and add
the link row; record whether the lead came from phase 1.

**7.5 Commit only when asked.**

## 8. Open decisions for the owner

Conflicts between the earlier sources that this playbook does not settle on its own:

1. **Who queues** (§1): the playbook follows practice (researcher decides); HANDOFF and two direction playbooks
   still say the agent picks.
2. **Priority criteria** (§5.2) and the **row status vocabulary** (§7.1): proposed here, not yet ruled.
3. **Upstream reporting**: "nothing is posted to JIRA" (researcher 2026-11-17) vs README and campaign-plan text
   about upstream reports, and B1/B7/U1 rows that name an upstream next step.
4. **Data-flow F1**: OOM-leads process rule 1 says trace F1 before new configuration pairs; F1 is P1 and not
   started. Does it still block pairs?
5. **Stale text** to correct once this playbook is accepted: `_INDEX.md` "a rerun that meets V1–V5 moves a case
   back" (now V1–V7) and its "(none yet)" lines; the run log's status tables marked as governing selection;
   HANDOFF's pointer to a combo-playbook "step 5" that does not exist; the campaign plan's "Not yet started"
   under the lead-source pilots (J1 is done); the jira-mining playbook's unconditional "each plausible lead
   becomes a campaign-plan row".

## 9. Sources merged

| Topic | Earlier source(s) |
|---|---|
| Lead sources, origin labels | README "Lead sources"; campaign-plan "Lead-source pilots"; `_INDEX.md` header; direction playbooks' first steps |
| Screening | bypass-leads §1; protocol "Unprotected results", "Classification by measurement"; custom-convergence "Picking cases"; bypass playbook selection; OOM-leads §3 and process rules |
| JIRA check | campaign-plan "Prioritized queue" rule; jira-mining playbook; survey §5; prior-art file vocabulary; HANDOFF rule |
| IDs, priority, row format | README "ID prefixes"; campaign-plan header and rows; data-flow playbook outputs |
| Pre-run gate | protocol (protection map, configuration and budget audit, design, V6–V7); default-convergence playbook; node-requirements; HANDOFF nodes |
| Lifecycle, recording | protocol statuses and progress statuses; run log; custom-convergence and bypass playbooks' recording steps; back-link playbook |
