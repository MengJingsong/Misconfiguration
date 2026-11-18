# Stage 5 guided-agent playbook — OOM clue find

> **Paths.** System-agnostic. Per-system files are under
> `experiments/capacity-enforcement-exp/<system>/`. What stage 5 is: [`README.md`](README.md).

**This is the guided agent.** It gets the same task as the [autonomous agent](playbook-autonomous.md)
plus the known **OOM clue patterns** ([`oom-clue-patterns.md`](oom-clue-patterns.md)), which it checks
one by one against each case. It may run in the repository. **Do not open anything under
`experiments/OOM-exp/`, or the candidate list's existing rows** (so a candidate it finds is a prediction,
not an echo of phase 2).

## Per case file

1. **Read** the case file (`<system>/stage3-ai-deep-read/cases/<stem>.md`, either agent's), its stage-4
   results file (`<system>/stage4-runtime-verification/results/<stem>.md`) if any, and every `file:line` it
   cites for the constraint, its check and what happens at the limit, in the pinned source. A measured
   gap between what the limit counts and what the node held is the strongest clue there is.
2. **Check each pattern** in `oom-clue-patterns.md`: ask its question of this case, answer from the source
   with `file:line`, at the shipped defaults and a reachable workload. Typical questions: what the counter
   charges against what the object really holds, and when each is released; what happens at the limit
   (graceful, or an allocation elsewhere, or only the JVM's own error); per what owner the limit applies
   and how many owners can exist; which memory budget it shares with which other defaults.
3. **Also note anything outside the patterns** that could lead to OOM; give it Patterns `—`.
4. **Write a candidate** for each clue with code to point to and a rough size at defaults: append a row to
   `<system>/stage5-oom-clue-find/phase1-oom-candidates.md` with the next `OC-<n>`, today's date, the case
   stem, Agent `guided`, the clue (holder, why nothing stops it, size), the pattern IDs it matched, Status
   `open`. One row per distinct mechanism; if the same mechanism shows up in two cases, write it once and
   name both stems. An overshoot by one item that another limit caps is not a candidate.
5. **Record coverage**: `case_file,guided,YYYY-MM-DD,<n>` in `coverage.csv`, also when `n` is 0.

Do not edit the case file, do not design or run an OOM test, and do not change the patterns file (a new
pattern comes only from a JIRA report or a phase-2 true positive).

## A sweep

For a batch, take case files in `_INDEX.md` order that have no `guided` line in `coverage.csv` (or, for a
re-sweep after a new pattern, whose last `guided` line is older than that pattern's Added date: check only
the new patterns). One fresh agent per batch of about ten files; report the number of files read and
candidates written.
