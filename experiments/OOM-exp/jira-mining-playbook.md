# JIRA mining playbook (lead source)

Read [verification-protocol.md](verification-protocol.md) first. This is a **lead
source**, not a direction (see [README](README.md#lead-sources)): it produces
candidates and positive controls that are then run with the convergence or bypass
playbooks and classified by the common protocol. Method files live here; outputs
live under `<system>/leads/` and `<system>/cases/`. Added 2026-11-10.

## Goal

Use the project's own fixed OOM reports to (1) measure which mechanisms cause real
OOMs and how much of that space convergence, bypass and unprotected accumulation
cover; (2) obtain **positive controls** that show the harness detects and
attributes a known OOM; (3) find **unfixed variants** and **incomplete fixes** in
the pinned version. Reproducing a fixed bug is not a new finding by itself.

## Survey

Query the system's Apache JIRA for resolved issues whose summary, description or
comments report `OutOfMemoryError`, OOM, OOM-kill, heap/direct/native memory
exhaustion, or GC death. Start with fixed bugs; record the query text, date and
hit count, and keep "Won't Fix", "Not a Problem" and duplicates as a separate
set (they show what the project considers by design). Exclude issues that are
only about test, build or tooling memory.

Record one row per issue in `<system>/leads/jira-oom-survey.csv`:

| Column | Content |
|---|---|
| `key`, `title`, `resolution`, `affected`, `fixed` | From JIRA |
| `component`, `flow` | Subsystem and data flow (same flow names as the [data-flow playbook](dataflow-tracing-playbook.md)) |
| `budget` | heap / direct / native / cgroup-kernel / unknown |
| `trigger` | workload, configuration, data shape, topology or failure event that caused it |
| `control_before` | the limit that existed before the fix (config, constant, implicit, none) |
| `class` | convergence / bypass (protocol sub-direction) / mixed / unprotected / unknown |
| `fix_kind` | new limit, accounting change, release fix, backpressure, doc/default change, other |
| `config_involved` | yes/no and which entries; whether a misconfiguration was the trigger |
| `repro_cost`, `variant_lead` | rough cost to reproduce; any similar unfixed path in the pinned source |
| `notes` | links to commits/patches; reviewer's confidence in the classification |

Classify from the issue text and the fix diff; mark `unknown` rather than guess.
Write `<system>/leads/jira-oom-survey.md` with the query, counts per `class`,
`flow` and `fix_kind`, the share where a misconfiguration was the trigger, and
the variant and reproduction shortlists. Agents may do the reading in parallel;
a second pass spot-checks a sample of classifications.

## Positive controls (reproduction)

Pick 3–5 issues covering different classes and flows with low reproduction cost.
Run each on its **affected** version with the protocol's controls: the issue's
trigger on the affected build, the same workload on the fixed build, and the
reported budget or a stated tightened one. File each as a case in the normal
status-first folders with label **source: JIRA-KEY, positive control**. A
failure to reproduce is recorded with its blocker, not discarded.

## Variants and incomplete fixes

For each shortlisted issue, read the fix and ask: does the same pattern exist on
another path, caller, message type or table option in the pinned version, and
does the limit the fix added have its own bypass or convergence exposure? Each
plausible lead becomes a campaign-plan row with its normal C/B ID and
`source: JIRA-KEY variant`. It is then run with the matching playbook; the JIRA
issue is cited in the protection map.

## Output and handoff

- `<system>/leads/jira-oom-survey.csv` and `.md` (survey, counts, shortlists).
- Positive-control cases in `<system>/cases/` with a source label.
- Campaign-plan rows for variants; an entry in `<system>/cases/_run-log.md` per
  survey batch (query, issues read, stopping point).

Before filing an upstream report from a variant, search JIRA for an existing
issue. Commit/push only when requested.
