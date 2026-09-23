# Stage 3 — AI deep read (semantic qualification)

**The only stage that decides.** Stage 3 reads the Cassandra source and
applies the three rules
([`../README.md` §3.4–§3.6](../README.md#3-core-concept-the-if-check-case))
to judge whether a line is a real if-check case. Stages 1 and 2 only shrink
and order what stage 3 must read; neither produces a finding.

See [`../README.md` §7.2](../README.md#72-discover-and-qualify-candidate-capacity-checks)
for how the three stages relate, and §3.2 for the enforcement patterns.

## Files

| File | Holds |
|---|---|
| [`playbook.md`](playbook.md) | **Start here to run a pass.** How a feed is worked, what to check in order, the pitfalls found so far. |
| [`rejected.md`](rejected.md) | Lines read with the source open and refused, each citing the rule it failed. |
| [`deferred.md`](deferred.md) | Lines left **unjudged** — they would qualify only under enforcement pattern (b) or (c), parked by the §7.5 scope decision. Not refused. |
| `cases/*.md` | Cases that **qualified** — the deliverable. Stage 3's positive output is the case file itself, so there is no `positives.md` here. |
| [`_INDEX.md`](_INDEX.md) | Master index of those cases. |

## The two feeds

Stage 3 is entered from either of two directions. **Both are required; they
cover different blind spots.**

| Feed | What points stage 3 at a line | Coverage | Progress measurable? |
|---|---|---|---|
| **3a — from stage 1/2** | [`../stage2-ai-preprocessing/positives.md`](../stage2-ai-preprocessing/positives.md), highest tier first | bounded, enumerable (row counts, tiers, batch table) | **yes** |
| **3b — from raw source** | the session's own reading of subsystems and call chains | unbounded, opportunistic | **no** — there is no denominator |

- **3a** is the cheap, systematic feed. Stages 1 and 2 exist precisely to
  relieve stage 3's burden by shrinking and ordering what must be read.
- **3b is not optional.** It is the standing insurance against stage 1's
  *structural* blind spot — it found the `cdc_total_space` ternary, which
  stage 1 cannot surface at any tier because it is not an `if` condition. It
  plays the same role against stage 1 that the P3 tier plays against
  stage 2's vocabulary. Its weakness is cost: the full source is far more
  than one session can read.

**Record the feed (`3a` or `3b`) on every case and every entry here.** The
two have different coverage properties and only 3a has a denominator; without
the field, "stage 3 progress" has no coherent answer.

## Filed by the stage that judged, not the stage that surfaced the row

This is the rule that decides where a verdict goes, and it is easy to get
backwards. A row that **stage 2 ranked** and **stage 3 then read and
refused** is a *stage-3* rejection.

| | Stage 2 verdict | Stage 3 verdict |
|---|---|---|
| Evidence | the row alone, source unread | the source, against the three rules |
| Rejections | `../stage2-ai-preprocessing/negatives.md` | [`rejected.md`](rejected.md) |
| Deferrals | *(none possible — see below)* | [`deferred.md`](deferred.md) |
| Form | bulk, per-batch, one line citing row-level ground | few, narrative, often deferred-rather-than-refused |

**Stage 2 cannot produce a pattern-(b)/(c) deferral.** Deciding that a line
"would qualify only under (b) or (c)" means tracing where the verdict is read
and whether the branches diverge — which no row shows. All deferrals are
therefore stage-3 judgments and live here, even when stage 2 surfaced the
row. (This is why `deferred.md` moved out of the stage-2 folder on
2026-09-23.)

A line is recorded in exactly one place. If stage 2 reaches a line stage 3
already judged, cite the entry here rather than re-recording it.
