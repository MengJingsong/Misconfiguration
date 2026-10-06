# [case-file stem] — the two paths side by side  <!-- file: comparison/[case-file stem].md -->

> **Long path:** [`long-path/results/[case-file stem].md`](../long-path/results/[case-file stem].md)
>
> **Short path:** [`short-path/results/[case-file stem].md`](../short-path/results/[case-file stem].md)

Written at the end by the session that finished the last run of the case. The
rules are in the README's [Two paths, two tiers each](../README.md#two-paths-two-tiers-each).
It edits neither solution nor any results file, and **rates nothing**: it reports. Its one edit elsewhere: the
`Comparison` cell of the case's row in [`../../stage3-ai-deep-read/short-path/_INDEX.md`](../../stage3-ai-deep-read/short-path/_INDEX.md)
changes from `pending` to a link to this file (the row's hash and the solution are not touched), and a line is added to
[`_INDEX.md`](_INDEX.md).

## 1. Verdicts

| Path | Tier | Verdict (row of that path's own table) | Results file | Date |
|---|---|---|---|---|
| Long | Unit | | | |
| Long | Cluster | | | |
| Short | Unit | | | |
| Short | Cluster | | | |

A tier a solution declared `n/a`, or that was not run, says so and why.

## 2. Do the conclusions agree?

In plain text: the claim each path ended with, whether they agree, and if they
do not, the point where the designs differ (a different constraint, mechanism,
knob range, observable). Neither path is overruled by the other; the readings
decided each path's own prediction.

## 3. What only one path's design produced

Findings, observables, arms, or bypasses that one design surfaced and the other
did not, or `none`. Name the design element that produced each (for example a
second knob, an allocation trace, a particular workload size).

## 4. Runbook defects

By path: the step that could not run as written, the cause, the fix (counts and
one line each; the detail is in each results file's §3).

## 5. Cost

By path and tier: runs, JVMs or nodes, and wall-clock time.
