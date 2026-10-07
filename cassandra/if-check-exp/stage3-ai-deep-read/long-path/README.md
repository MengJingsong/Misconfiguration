# Stage 3, long path — AI deep read (semantic qualification)

One of stage 3's two paths (see [`../README.md`](../README.md)); the other is
the [short path](../short-path/README.md). **The long path is the one that
decides.** It reads the Cassandra source and
applies the three rules
([`../../README.md` §3.4–§3.6](../../README.md#3-core-concept-the-if-check-case))
to judge whether a line is a real if-check case. Stages 1 and 2 only shrink
and order what stage 3 must read; neither produces a finding. The short path
files no verdict, so a rejection or deferral is always a long-path entry.

For every case that qualifies, stage 3 also **designs the test** that would
confirm or refute it — §9 of the case file, written for
[stage 4](../../stage4-runtime-verification/README.md) to execute. Stage 3 never
runs it and records no measured numbers; see
[`../../README.md` §8](../../README.md#8-designing-a-test-for-a-case) for the method.

**All three enforcement patterns are in scope** as of 2026-09-25
([`../../README.md` §7.5](../../README.md#75-active-scope-decisions-revised-2026-09-25)).
A (b) or (c) row is read and judged like any other.

See [`../../README.md` §7.2](../../README.md#72-discover-and-qualify-candidate-capacity-checks)
for how the three stages relate, and §3.2 for the enforcement patterns.

## 1. Files

| File | Holds |
|---|---|
| [`playbook.md`](playbook.md) | **Start here to run a pass.** How a feed is worked, what to check in order, the pitfalls found so far. |
| [`rejected.md`](rejected.md) | Lines read with the source open and refused, each citing the rule it failed. |
| [`deferred.md`](deferred.md) | Lines left **unjudged**, identified but never read against the rules. Formerly the (b)/(c) parking lot; since those patterns were unparked (2026-09-25) it is a **worklist**, and the cheapest rows to pick up. Not refused. |
| [`cases/`](cases/) | Cases that **qualified and are written up** — the deliverable. Flat; the module is a field, not a folder. |
| [`_INDEX.md`](_INDEX.md) | Master index of those cases. |
| [`pending.md`](pending.md) | Qualified against the three rules but **not yet written up**. Findings, not a queue — rows still awaiting a read live in `../../stage2-ai-preprocessing/bands.md`. |

## 2. Guide: going through the long path for one case

### 2.1 Ground rules

- The long path is written by an **AI session in this repo**; it has no scripts.
- **Read first:** [`../../../../HANDOFF.md`](../../../../HANDOFF.md), `_INDEX.md`, `rejected.md`
  and `deferred.md`. Do not re-judge a line that is already recorded; cite it.
- **Source:** the local Cassandra clone must be at the pinned tag
  (`git describe --tags` prints `cassandra-5.0.9`). Its location varies by machine:
  `$CASSANDRA_SRC`, else a sibling of this repository (`cassandra-src`), else
  `/proj/misconfiguration-PG0/git-repos/cassandra-src` on CloudLab.
- **No isolation rule.** The long path goes first for every case (decided 2026-10-06),
  so there is no short-path file to avoid. Do not write a short-path solution
  yourself: it is made by an isolated process
  ([`../short-path/README.md`](../short-path/README.md)).
- **No human step.** An AI session does this whole path. Draft, verify and file the
  case locally; Jingsong may read and overrule at any time, but nothing waits for
  that. Commit and push only when asked.
- **Run nothing and record no measured number.** Stage 4 executes the test you
  design.

### 2.2 Steps

| # | Step | Where it is spelled out | Result |
|---|---|---|---|
| 1 | Orient | [`playbook.md`](playbook.md) §1 | what exists, what is judged |
| 2 | Pick a row from a feed (`3a` or `3b`) | [`../README.md`](../README.md) §4 | a candidate line |
| 3 | Work the row: seven steps, each can end the judgment early | playbook §2 | a case, or a refusal |
| 4 | Name the file `[constraint]-[function]-[operand].md` | [`../../README.md` §6.1](../../README.md#61-naming) | the stem |
| 5 | Write the case file from `_TEMPLATE.md`, all nine questions, **both tiers in §9** | `_TEMPLATE.md`, section 2.3 below | `cases/<stem>.md` |
| 6 | Verify every `file:line` against the clone; record the feed in the Notes | playbook §4 | a checked case |
| 7 | File it: `_INDEX.md` row, module notes if the module is new; for feed `3a`, note the batch in the stage-2 coverage table | playbook §4 | the case is filed |
| 8 | A refused line goes to `rejected.md`; one that qualifies but is not written up now goes to `pending.md`; a line not yet read stays in `deferred.md` | section 4 below | one place per line |
| 9 | Commit and push (when you ask), then hand off to stage 4 | [`../README.md`](../README.md) §2 | the case is frozen in history |

### 2.3 The two tiers (new cases)

Every **new** case's §9 designs both tiers, or says why one is not possible:

- **Unit tier:** drive the check's classes directly in a JVM test; measure the
  check's own operand. It proves the mechanism.
- **Cluster tier:** a real node with the knob at the boundary; measure the actual
  resource (heap, off-heap or disk). It proves the dose-response claim.

Each tier has its own setup, workload, observables, prediction and conclusions
rows (method: [`../../README.md` §8](../../README.md#8-designing-a-test-for-a-case)). A tier
that cannot be done keeps its place in §9 as `n/a: <reason>`, with what answers
the same question instead; it is not deleted. All 16 filed cases are in the new §9
layout (eight converted 2026-10-06 and the twelfth to sixteenth written in it; those eleven (all but the fifteenth and sixteenth, closed at stage 4 on 2026-10-07) are not yet audited); copy the structure from
`_TEMPLATE.md` and the most recent conversions, not from older prose.

### 2.4 What counts as done

The case file is filed with all nine fields answered and every citation
checked, its `_INDEX.md` row is in, any refused or deferred line is recorded, and
the work is committed. There is no `Status` field: a filed case is complete as
stage-3 evidence, not a verified result.

## 3. The two feeds

Both paths are entered from the same two feeds (3a from `bands.md`, 3b from raw
source); they are described in [`../README.md`](../README.md#4-the-two-feeds).
Record the feed (`3a` or `3b`) on every case and every entry here.

## 4. Filed by the stage that judged, not the stage that surfaced the row

This is the rule that decides where a verdict goes, and it is easy to get
backwards. A row that **stage 2 ranked** and **stage 3 then read and
refused** is a *stage-3* rejection.

| | Stage 2 verdict | Stage 3 verdict |
|---|---|---|
| Evidence | the row alone, source unread | the source, against the three rules |
| Qualified | *(cannot qualify)* | [`cases/`](cases/), or [`pending.md`](pending.md) until written up |
| Rejections | *(none possible — bottom band instead)* | [`rejected.md`](rejected.md) |
| Deferrals | *(none possible — see below)* | [`deferred.md`](deferred.md) — historical; nothing new is deferred by pattern |
| Form | bulk, per-batch, a band and a one-line reason | few, narrative, often deferred-rather-than-refused |

**Stage 2 cannot produce a pattern-(b)/(c) deferral.** Deciding that a line
"would qualify only under (b) or (c)" means tracing where the verdict is read
and whether the branches diverge — which no row shows. All deferrals are
therefore stage-3 judgments and live here, even when stage 2 surfaced the
row. (This is why `deferred.md` moved out of the stage-2 folder on
2026-09-23.)

A line is recorded in exactly one place. If stage 2 reaches a line stage 3
already judged, cite the entry here rather than re-recording it.
