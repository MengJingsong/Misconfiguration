# JIRA mining — building a system's JIRA OOM report

*Moved 2026-11-17 from `OOM-exp/jira-mining-playbook.md` (a phase-2 lead source until then) to phase 1's
stage 5.* It builds `<system>/stage5-oom-clue-find/jira-oom-report.md`, the analysis of the system's JIRA
OOM reports from which [`oom-clue-patterns.md`](oom-clue-patterns.md) is generated. JIRA is **read only**:
nothing is posted, commented or reported upstream. First done for Cassandra (2026-11-10/16); Hadoop's
report is not built yet.

## Goal

Use the project's own OOM reports to learn **which code shapes lead to real OOMs** (cause patterns), so
the guided stage-5 agent can look for them in phase-1 case files; and to give phase 2's OOM agent prior
art (known-fixed, by design) when it picks a candidate. Reproducing a fixed bug is not a new finding.

## Survey

Query the system's Apache JIRA for resolved issues whose summary, description or
comments report `OutOfMemoryError`, OOM, OOM-kill, heap/direct/native memory
exhaustion, or GC death. Start with fixed bugs; record the query text, date and
hit count, and keep "Won't Fix", "Not a Problem" and duplicates as a separate
set (they show what the project considers by design). Exclude issues that are
only about test, build or tooling memory.

Record one row per issue in `<system>/stage5-oom-clue-find/jira-oom-survey.csv`:

| Column | Content |
|---|---|
| `key`, `title`, `resolution`, `affected`, `fixed` | From JIRA |
| `component`, `flow` | Subsystem and data flow (client intake, coordinator write/read, internode, mutation → memtable → flush, read path and caches, compaction, repair, hints; Hadoop: NameNode RPC, DataNode pipeline, shuffle, RM state, IPC) |
| `budget` | heap / direct / native / cgroup-kernel / unknown |
| `trigger` | workload, configuration, data shape, topology or failure event that caused it |
| `control_before` | the limit that existed before the fix (config, constant, implicit, none) |
| `class` | convergence / bypass (protocol sub-direction) / mixed / unprotected / unknown |
| `fix_kind` | new limit, accounting change, release fix, backpressure, doc/default change, other |
| `config_involved` | yes/no and which entries; whether a misconfiguration was the trigger |
| `repro_cost`, `variant_lead` | rough cost to reproduce; any similar unfixed path in the pinned source |
| `notes` | links to commits/patches; reviewer's confidence in the classification |

Classify from the issue text and the fix diff; mark `unknown` rather than guess. Agents may do the
reading in parallel; a second pass spot-checks a sample of classifications.

## The report

Write `<system>/stage5-oom-clue-find/jira-oom-report.md`: scope and queries (text, date, hit counts), how
issues were classified, counts per `class`, `flow` and `fix_kind`, the share where a misconfiguration was
the trigger, the **cause patterns** found in fixed issues (each with counts and representative keys),
what the project closes as by design, and a last section mapping each cause pattern to an
[`oom-clue-patterns.md`](oom-clue-patterns.md) row (`CP-<n>`). A cause pattern no `CP` row covers becomes
a new row with source `JIRA <system>` and the date.

Variants and incomplete fixes noticed while reading (the same shape on another path of the pinned
version) are not candidates by themselves: they show up when stage 5 reads the matching phase-1 case.

Commit/push only when requested.
