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

## Files

| File | Holds |
|---|---|
| [`playbook.md`](playbook.md) | **Start here to run a pass.** How a feed is worked, what to check in order, the pitfalls found so far. |
| [`rejected.md`](rejected.md) | Lines read with the source open and refused, each citing the rule it failed. |
| [`deferred.md`](deferred.md) | Lines left **unjudged**, identified but never read against the rules. Formerly the (b)/(c) parking lot; since those patterns were unparked (2026-09-25) it is a **worklist**, and the cheapest rows to pick up. Not refused. |
| [`cases/`](cases/) | Cases that **qualified and are written up** — the deliverable. Flat; the module is a field, not a folder. |
| [`_INDEX.md`](_INDEX.md) | Master index of those cases. |
| [`pending.md`](pending.md) | Qualified against the three rules but **not yet written up**. Findings, not a queue — rows still awaiting a read live in `../../stage2-ai-preprocessing/bands.md`. |

## The two feeds

Both paths are entered from the same two feeds (3a from `bands.md`, 3b from raw
source); they are described in [`../README.md`](../README.md#the-two-feeds).
Record the feed (`3a` or `3b`) on every case and every entry here.

## Filed by the stage that judged, not the stage that surfaced the row

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
