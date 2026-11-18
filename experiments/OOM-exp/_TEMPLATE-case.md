# <ID> — <constraint or holder>: <short mechanism>  <!-- file: <system>/cases/<stem>/<stem>.md -->

| Field | Value |
|---|---|
| Case ID | `<C/B/U/S/R><n>` (README "ID prefixes") |
| From | `OC-<n>` of the phase 1 OOM candidate list, or a retry of `<case ID>` |
| Phase-1 case file | link to `capacity-enforcement-exp/<system>/stage3-ai-deep-read/cases/<stem>.md`, or `none` |
| System / pinned source | e.g. Cassandra 5.0.9 |
| Stage 1 (design) | agent session, date |
| Stage 2 (verify) | agent session (a fresh one), date |
| Verdict | `pending` → `true positive` / `false positive` / `retry` |

## 1. Candidate

The candidate or retry row, quoted. The phase-1 case's constraint, its check and what stage 4 measured
(if it ran). JIRA prior art: queries, hits, verdict (`new`, `known-open`, `known-fixed` → positive
control only, `by design`, `documented`); nothing is posted to JIRA.

## 2. Design solution (stage 1; frozen)

Everything stage 2 needs to run without re-deriving the mechanism
([`verification-protocol.md`](../../../verification-protocol.md) for each item):

- **Mechanism** in one paragraph, with `file:line`; the direction label (convergence / bypass /
  unprotected accumulation / combo) and the technique note used.
- **Protection map:** one row per allocation domain — holder, counter, limit, what happens at the limit.
- **Configuration and budget audit:** every capacity constraint involved at its shipped default, resolved
  at the planned heap; heap, direct-memory and container budgets (V7: ≥ 512 MiB, 2 GiB ideal).
- **Ceiling arithmetic:** sum of contract capacities plus baseline against the budget.
- **Workload and environment:** nodes, build, client, sizes, multiplicity, any realistic fault.
- **Instruments:** what is measured (U independent of K), how, how often.
- **Predicted response** and stopping budget; finite time or attempt limit.
- **Controls and intervention:** matched control (≥ 3 runs) and the causal intervention (≥ 3 runs).

`sha256 of §1–§2 at freeze: <hash>` · amendments after the freeze: dated, with reason.

## 3. Runs (stage 2)

Harness: `harness/` in this folder; logs on the node (path) and excerpts in `logs/`.

| Run | Arm (test / control / intervention) | Budget | Load reached | Endpoint (OOM type or none) | Key reading (U vs K) |
|---|---|---|---|---|---|

Deviations from the design, and what was left on the nodes.

## 4. Conclusion (stage 2)

- **Verdict:** `true positive` / `false positive` / `retry` ([`oom-agent-playbook.md`](../../../oom-agent-playbook.md)).
- **Protocol status (detail):** e.g. `verified-OOM · deployment`, with V1–V7 met or not.
- **Reason:** one paragraph.
- **For retry:** what a better design should change (copied to the retry list).
