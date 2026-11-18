# Stage 5 — OOM clue find

> **Paths (multi-system layout).** This is a system-agnostic method doc. The per-system files it names
> (`jira-oom-report.md`, `phase1-oom-candidates.md`, `coverage.csv`) live in
> `experiments/capacity-enforcement-exp/<system>/stage5-oom-clue-find/`, not next to this file.

*Added 2026-11-17 (owner), replacing the OOM-lead machinery of 2026-11-16/17 (guided §3.2 and §8a,
autonomous section E, rechecks, budget ledger, OOM lead list, back-link). That design is in git before
this change.*

Stage 5 is phase 1's last stage. It reads the **filed case files** of stages 3 and 4 and looks for
**clues that could lead to an out-of-memory failure**: memory a constraint does not really bound, a
limit whose only stop is the JVM's own error, and the like. It does not decide anything about the
constraint (stage 3's estimate and stage 4's verdict stand) and it runs nothing. Its only output is
**OOM candidates** for phase 2 ([`../../OOM-exp/`](../../OOM-exp/README.md)).

## Two agents

| | Autonomous agent | Guided agent |
|---|---|---|
| Playbook | [`playbook-autonomous.md`](playbook-autonomous.md) | [`playbook-guided.md`](playbook-guided.md) |
| Gets | one case file (and its stage-4 results file, if any) and the pinned source | the same, **plus** [`oom-clue-patterns.md`](oom-clue-patterns.md) |
| Never opens | `oom-clue-patterns.md`, the JIRA OOM reports, anything under `OOM-exp/`, other case files, the candidate list | anything under `OOM-exp/`, the candidate list |
| Writes | candidate rows (agent `autonomous`) | candidate rows (agent `guided`, with the pattern IDs) |

The autonomous agent is the **control**: it finds clues in its own words. The guided agent shows what
the known patterns add. Each candidate row records its agent, so phase 2's verdicts give each agent's
true-positive rate.

**Neither agent reads phase-2 results**, so a candidate that phase 2 confirms counts as phase 1
predicting an OOM. The patterns file may contain patterns learned from phase-2 results (labelled and
dated); that is the guided agent's only indirect view of phase 2.

## Inputs

- **Case files**: `<system>/stage3-ai-deep-read/cases/*.md` (both agents' files), with
  `<system>/stage4-runtime-verification/results/<stem>.md` when it exists: a measured gap between what a
  limit counts and what the node holds is the strongest clue there is. A case without stage-4 results is
  still read. Sections headed `## Recheck` and a guided file's `§8a` (written 2026-11-16/17 by the
  retired method) are skipped by the autonomous agent; the guided agent may read them.
- **The pinned source** of the system, to check every cited `file:line`.
- **Guided only:** [`oom-clue-patterns.md`](oom-clue-patterns.md), which is built from the JIRA OOM
  reports and from phase-2 true positives.

## Outputs (per system)

| File | Holds |
|---|---|
| `phase1-oom-candidates.md` | **The phase 1 OOM candidate list.** One row per candidate; phase 2 reads it and writes the status back |
| `coverage.csv` | One line per case file and agent read: `case_file,agent,date,candidates` (`0` when none), so a case is not read twice by the same agent |
| `jira-oom-report.md` | The analysis of the system's JIRA OOM reports (method: [`jira-mining.md`](jira-mining.md)); the source of most patterns |

### The candidate list format

```
| ID | Date | Phase-1 case file | Agent | Clue (mechanism, rough magnitude at defaults) | Patterns | Status |
|---|---|---|---|---|---|---|
| OC-001 | 2026-11-20 | `native_transport_max_frame_size-decode-bytesToDiscard--autonomous` | autonomous | each pre-login connection can hold a 16 MiB partial envelope in direct memory; connections unlimited by default (−1); ~256 connections reach 4 GiB | — | open |
```

- **ID:** `OC-<n>` (OOM candidate), numbered per system, never reused; cite it across systems as
  `cassandra:OC-12`.
- **Phase-1 case file:** the stem, or `none` for a candidate that names no single case (a sum across
  constraints).
- **Agent:** `autonomous`, `guided`, or `legacy` (migrated 2026-11-17 from the retired lists; the
  clue cell starts with its old origin, e.g. `[N13, blind recheck]`).
- **Patterns:** guided rows give the pattern IDs (`CP-1, CP-3`); autonomous rows `—`.
- **Status** (written by phase 2, forward only): `open` → `picked: <phase-2 case ID>` → `true positive` /
  `false positive` / `retry` (each with the case ID); or `skipped: <reason>` (the OOM agent looked and
  passed, e.g. disk-only, needs corrupt input), or `duplicate of OC-<n>`.

A candidate is a clue, not a result: name the holder, why the limit does not stop it, `file:line`, and a
rough size at the shipped defaults. An overshoot by one item that another limit caps is not a
candidate.

## The OOM clue patterns

[`oom-clue-patterns.md`](oom-clue-patterns.md) is system-agnostic; each pattern has an ID (`CP-<n>`), a
one-line shape, the question that finds it, examples per system, and its **source**: `JIRA <system>`
(from a JIRA OOM report) or `phase 2: <case ID>` (from a phase-2 true positive), with the date added.
A pattern is added when a JIRA report or a phase-2 true positive shows a shape no pattern covers;
existing candidates are not re-labelled.

## When stage 5 runs

After stage 4 for a case where possible, otherwise on the filed case file. A **sweep** reads every case
file not yet in `coverage.csv` for that agent; when the patterns file gains a pattern, the owner may ask
for a guided re-sweep, recorded as a new coverage line.

## Files

| File | Holds |
|---|---|
| [`playbook-autonomous.md`](playbook-autonomous.md) | The autonomous agent's whole instruction |
| [`playbook-guided.md`](playbook-guided.md) | The guided agent's instruction |
| [`oom-clue-patterns.md`](oom-clue-patterns.md) | Known OOM clue patterns (guided agent only) |
| [`jira-mining.md`](jira-mining.md) | How a system's JIRA OOM report is built (moved here from OOM-exp, 2026-11-17) |
