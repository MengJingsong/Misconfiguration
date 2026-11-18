# OOM agent playbook — phase 2, stages 1 and 2

*Written 2026-11-17 (owner's redesign).* Phase 2 has one agent role, the **OOM agent**, and two stages.
Stage 1 picks a candidate and writes its case file with a design that should lead to OOM; stage 2
follows that design on real nodes and adds the conclusion. Every picked candidate is treated as
**estimated positive** (it will OOM) after stage 1, so stage 2's conclusion is one of three verdicts:

| Verdict | Meaning |
|---|---|
| **true positive** | it leads to OOM: the verification protocol's V1–V7 hold (status `verified-OOM`) |
| **false positive** | it does not lead to OOM: a valid run of the design reached its target load, and the measurements show the endpoint cannot be reached at defaults and an acceptable budget (see "False positive or retry") |
| **retry** | no final conclusion: worth another try with a better design. The case goes to the retry list |

Evidence rules, measurement, budgets and statuses are in [`verification-protocol.md`](verification-protocol.md);
this playbook does not restate them. The protocol's finer statuses stay in the case file as detail
(`verified-gap`, `reproduced-OOM`, `candidate`, `negative`, with `deployment` / `diagnostic`); the verdict
is what counts.

## Inputs

1. **The phase 1 OOM candidate list**, per system:
   `../capacity-enforcement-exp/<system>/stage5-oom-clue-find/phase1-oom-candidates.md`, rows with Status `open`.
2. **The phase 2 retry list**, per system: [`<system>/phase2-retry-list.md`](cassandra/phase2-retry-list.md),
   rows with Status `open`.

Nothing else is a lead source (JIRA OOM history and data-flow tracing were retired as phase-2 sources
on 2026-11-17; JIRA now feeds phase 1's clue patterns).

## Stage 1 — pick and design

1. **Pick.** Read the open rows of both lists. Prefer a candidate that is reachable at shipped defaults,
   names a concrete holder, and whose rough size can reach a deployment budget; prefer a retry whose
   "what to change" is concrete. Before picking, check JIRA for prior art (read only; nothing is posted
   to JIRA or reported upstream): a known-fixed bug is picked only as a positive control. For each row
   you pass over on purpose, write `skipped: <reason>` in its Status (disk-only, needs corrupt input,
   overshoot of one item already capped, small heap-derived cap, duplicate). Rows you simply did not get
   to stay `open`.
2. **Mark it.** Candidate list: Status `picked: <case ID>`. Retry list: Status `picked again: <case ID>`.
3. **Case ID and folder.** The direction prefix of the design (README "ID prefixes": C convergence, B
   bypass, U unprotected accumulation, S stacked combo, R a new attempt at an earlier case with
   `-V` for the re-test at defaults), next free number. Case folder:
   `<system>/cases/<constraint or holder>--<short mechanism>/` (flat; the verdict lives in `_INDEX.md`, not
   in the folder; cases filed before 2026-11-17 stay in their old `convergence/`, `bypass/`,
   `candidates/`, `negatives/` folders); the case file has the same stem.
4. **Write the case file** from [`_TEMPLATE-case.md`](_TEMPLATE-case.md):
   - **§1 Candidate:** its `OC-` or retry row, quoted; the **corresponding phase-1 case file** (link) or
     `none`; the phase-1 stage-4 result if any; JIRA prior art.
   - **§2 Design solution:** the mechanism, the protection map, the configuration and budget audit, the
     workload, instruments, predicted response, stopping budget, controls and intervention, as the
     protocol requires. Use the technique notes (below) for the shape. Freeze it: record the sha256 of §1–§2
     in §2's last line. Stage 2 runs this design; a change after the freeze is a dated amendment with
     its reason.
   - **§3 Runs** and **§4 Conclusion:** `pending`.
5. Stage 1 ends there. It does not run anything.

## Stage 2 — verify

Run by a **fresh** OOM-agent session (not the one that wrote the design), so the design cannot drift to
fit the readings.

1. Read the case file; check the freeze hash; check the nodes (root `HANDOFF.md`, "Nodes and access")
   and what runs on them.
2. Build the harness under `<case folder>/harness/` (scripts, configs, workload drivers), run the design,
   keep logs on the node and small excerpts in `<case folder>/logs/`. Follow the protocol's design and
   execution rules (repetitions, matched controls, intervention, initiating failure, budgets).
3. Fill **§3 Runs**: environment, every run with its readings, deviations from the design.
4. Fill **§4 Conclusion**: the verdict, the protocol status as detail, the one-paragraph reason, and for
   `retry` what a better design should change.
5. **Write back:**
   - the candidate list row (or the retry row): `true positive (<ID>)`, `false positive (<ID>)` or
     `retry (<ID>)`;
   - for `retry`, add a row to the retry list;
   - update the case's row in [`<system>/cases/_INDEX.md`](cassandra/cases/_INDEX.md) (Verdict column);
   - for a `true positive` whose shape no clue pattern covers, add a pattern to
     `../capacity-enforcement-exp/stage5-oom-clue-find/oom-clue-patterns.md` with source
     `phase 2: <case ID>` and the date.
6. Stop every process the run started and say what is left on the nodes.

## False positive or retry

A run that does not reach OOM is a **false positive** only when all of these hold; otherwise it is a
**retry**:

- the design ran as frozen (or with recorded amendments) and reached its target load or multiplicity;
- the claimed holder was measured (U independent of K) and its growth stopped below the budget, or the
  ceiling arithmetic at defaults (sum of every contract capacity plus baseline) cannot reach an acceptable
  budget;
- no realistic fault, multiplicity or overlap named in the design is left untried.

A gap without OOM (`verified-gap`: an overshoot, a leak or service loss) and an OOM only with raised
capacities or a tightened budget (`reproduced-OOM`) are **retry**: the mechanism is real but the design
has not reached OOM at defaults.

## The phase 2 retry list format

`<system>/phase2-retry-list.md`:

```
| Case | Verdict date | Why retry (what was shown, what was missing) | What a better design should change | Status |
|---|---|---|---|---|
| B7 | 2026-11-12 | weighers hold 2.14× / 1.80× their caps (verified-gap), no OOM at defaults 0/3 | stack with another heap pool at 2 GiB; more distinct keys | open |
```

Status: `open` → `picked again: <new case ID>` → closed by that case's verdict.

## Technique notes

The earlier direction playbooks are kept as notes on how to shape a design in §2:
[`custom-convergence-playbook.md`](custom-convergence-playbook.md),
[`default-convergence-playbook.md`](default-convergence-playbook.md), [`combo-playbook.md`](combo-playbook.md)
(multiplicity → stack → accounting gap), [`bypass-playbook.md`](bypass-playbook.md). Their own "pick" and
"queue" steps are superseded by stage 1 above.
