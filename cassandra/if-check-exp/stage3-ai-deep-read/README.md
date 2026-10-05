# Stage 3 — AI deep read

Stage 3 reads the Cassandra source. For every case it produces **two
independent verification solutions**, one from each path:

| | [Long path](long-path/README.md) | [Short path](short-path/README.md) |
|---|---|---|
| Status | the established method; 11 cases filed | **experiment** (decided 2026-10-02), none filed yet |
| Method | the 7 steps of [`long-path/playbook.md`](long-path/playbook.md): the three rules ([`../README.md` §3.4–§3.6](../README.md#3-core-concept-the-if-check-case)), the three enforcement patterns (§3.2), the test-design method (§8) | two jobs and no rubric: trace the constraint, then design the verification solution from whatever the AI itself collects from the sources |
| Decides | yes — qualifies, rejects or defers a line | **no** — it files no verdict |
| Output | a case file in [`long-path/cases/`](long-path/cases/), or an entry in [`long-path/rejected.md`](long-path/rejected.md) / [`long-path/deferred.md`](long-path/deferred.md) | a solution file in [`short-path/cases/`](short-path/cases/) |

**Why two paths.** The long path carries human method — the rules, the
patterns, the design rules, the template. Nobody has tested whether that
method helps the AI or limits it, because every filed case passed it by
construction. The short path removes the method so the two solutions can be
compared; the comparison is made in
[stage 4](../stage4-runtime-verification/README.md#solution-comparison), not
here.

**Stage 3 never judges the pair.** The long path judges whether a line is a
real case (its own verdict). Whether the short solution's constraint, mechanism
and design agree with the long one, and how many tests that needs, is stage 4's
decision.

## Rules that hold across both paths

- **Blind both ways.** A session writing one path's solution for a case does
  not open the other path's file for that case. Only the stage-4 comparator
  reads both. The short path additionally runs in isolation from this folder's
  guidance (see [`short-path/README.md`](short-path/README.md)).
- **Frozen on filing.** Once a solution is filed, record its sha256 in the
  path's `_INDEX.md`. Later edits are documentation-only and dated; stage 4
  compares against the frozen version.
- **Neither path runs anything or records a measured number.** Both design a
  test; stage 4 executes it ([`../README.md` §7.5](../README.md#75-active-scope-decisions-revised-2026-09-25)).
- **Same pinned source.** Both read `cassandra-5.0.9`
  ([`../README.md` §2](../README.md#2-source-of-truth-version-pinning--read-this-first)).
- **A line is recorded in exactly one place per path.** The long path's
  verdict-filing rule is in [`long-path/README.md`](long-path/README.md).

## The two feeds

Stage 3 is entered from either of two directions, whichever path is being
written. **Both are required; they cover different blind spots.**

| Feed | What points stage 3 at a line | Coverage | Progress measurable? |
|---|---|---|---|
| **3a — from stage 1/2** | [`../stage2-ai-preprocessing/bands.md`](../stage2-ai-preprocessing/bands.md), band A first | bounded, enumerable (row counts, bands, batch table) | **yes** |
| **3b — from raw source** | the session's own reading of subsystems and call chains | unbounded, opportunistic | **no** — there is no denominator |

- **3a** is the cheap, systematic feed. Stages 1 and 2 exist precisely to
  relieve stage 3's burden by shrinking and ordering what must be read.
- **3b is not optional.** It is the standing insurance against stage 1's
  *syntactic* blind spot — it found the `cdc_total_space` ternary, which
  stage 1 cannot surface at all, because the comparison is not in an `if`
  condition. It plays the same role against that blind spot that band C
  plays against stage 2's *vocabulary* blind spot: insurance against a real
  case that the mechanism is built not to see. Its weakness is cost: the full
  source is far more than one session can read.

**Record the feed (`3a` or `3b`) on every case and every entry.** The two have
different coverage properties and only 3a has a denominator; without the
field, "stage 3 progress" has no coherent answer.

## Folder map

| Path | Holds |
|---|---|
| [`long-path/`](long-path/README.md) | The long path: playbook, case template, master index, the cases, and the rejected / deferred / pending worklists |
| [`short-path/`](short-path/README.md) | The short path: contract, brief, template, index, and the solutions |
