# Back-link playbook — from a verified OOM-exp case back to phase 1

*Added 2026-11-16.* Run once for every OOM-exp case whose status becomes `verified-OOM` or
`verified-gap` (either conditions label), per system. It answers: **did phase 1
(`capacity-enforcement-exp`) hold a clue to this result, and if not, why not?** It reads both
experiments and edits neither; its outputs are one row in the system's link table and a list of
phase-1 case files to recheck. How the experiments relate is in [`README.md`](README.md).

## Inputs

- The OOM-exp case file (`OOM-exp/<system>/cases/{convergence,bypass}/...`), its row in that system's
  `_INDEX.md`, and its **lead source** label (if-check inventory, `JIRA-KEY`, `flow:<name>`).
- Phase 1's per-system data: `capacity-enforcement-exp/<system>/stage3-ai-deep-read/cases/`, its
  `_INDEX.md`, `predicted-negative.md`, `predicted-positive.md`, `undetermined.md`, and the stage-4
  results; `entry-restriction-exp/<system>/` (the phase-1 supplement).
- The pinned source, for checking that a phase-1 file names the same code as the OOM case.

## Steps

1. **Mechanism.** From the OOM case file, write the mechanism in one line, then list the memory
   holders it names and, for each, the constraints and controls of its protection map.
2. **Find the phase-1 case files.** For each constraint, grep `cases/` by constraint name, and by the
   class and method of the holder and of its check. Include files whose constraint differs but whose
   code path is the same. Check `entry-restriction-exp` the same way. Record `none` when nothing
   matches.
3. **As filed before the OOM.** Phase-1 files are amended over time. For each file found, read the
   version committed **before the OOM case's first run** (`git log --follow -- <path>`, then
   `git show <rev>:<path>`; before 2026-11-11 the folder was `if-check-exp`). Note any text about this
   mechanism that was added later, with its date, and judge the class (step 4) on the earlier version.
4. **Classify** the case by the best phase-1 file:

   | Class | Meaning |
   |---|---|
   | `flagged` | The file names the mechanism **and** marks it as a finding: a negative estimate, a stage-4 bypass or does-not-cap verdict, or an escape-hatch / Target-3 note that says how usage gets past the constraint |
   | `recorded-untested` | The mechanism appears (a side note, an A3 bypass remark), but the estimate and stage 4 do not test it |
   | `missed` | A phase-1 file exists for the constraint or the code path, but the mechanism is absent |
   | `no-case` | Within phase 1's scope (a constraint, or a capacity-set place, traces to the holder), but no case file exists |
   | `out-of-scope` | No constraint or capacity applies to the holder: unprotected by phase 1's own definition |

   **Several holders** (a combo or stacked case): classify each holder, then give the case the class
   of the holder its result depends on (the one whose intervention removes the endpoint, or the
   largest term), not the best class among them. When the result needs the holders together, also
   classify the joint mechanism (usually E4) and report it.

   Also record whether the OOM case's lead source **was** that phase-1 file (from its lead-source label
   and history).
5. **Question.** Name the [guided playbook §3.2](capacity-enforcement-exp/stage3-ai-deep-read/playbook-guided.md#32-enforcement-properties-added-2026-11-16)
   question (E1–E4) that would have surfaced the clue, or `none fits`. For `none fits`, propose a new
   question in one line; the owner decides whether it joins §3.2 (dated, with this case named).
6. **Write the row** in `phase-links/<system>.md` and list the phase-1 files to recheck in
   `back-link` mode (guided playbook §5). Do not edit phase-1 files in this playbook.

## Rules

- Classify from the files as they stood, not from what the OOM result now makes obvious. When unsure
  between two classes, take the weaker one (`recorded-untested` over `flagged`, `missed` over
  `recorded-untested`) and say why.
- Cite each phase-1 file by path and the section or row holding the clue, with a short quote.
- A `back-link` recheck answers the questions for one case after the fact. It does not count as
  evidence that phase 1 predicts phase 2; only `blind` rechecks
  (guided playbook §5) do.
