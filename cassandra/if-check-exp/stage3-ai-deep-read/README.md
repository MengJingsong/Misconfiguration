# Stage 3 — AI deep read

Stage 3 reads the Cassandra source. For every case it produces **two
independent verification solutions**, one from each path.

## 1. The two paths

| | [Long path](long-path/README.md) | [Short path](short-path/README.md) |
|---|---|---|
| Status | the established method; 11 cases filed | **experiment** (decided 2026-10-02); first solution filed |
| Method | the 7 steps of [`long-path/playbook.md`](long-path/playbook.md): the three rules ([`../README.md` §3.4–§3.6](../README.md#3-core-concept-the-if-check-case)), the three enforcement patterns (§3.2), the test-design method (§8) | two jobs and no rubric: trace the constraint, then design the verification solution from whatever the AI itself collects from the sources |
| Decides | yes — qualifies, rejects or defers a line | **no** — it files no verdict |
| Output | a case file in [`long-path/cases/`](long-path/cases/), or an entry in [`long-path/rejected.md`](long-path/rejected.md) / [`long-path/deferred.md`](long-path/deferred.md) | a solution file in [`short-path/cases/`](short-path/cases/) |

**Why two paths.** The long path carries human method — the rules, the
patterns, the design rules, the template. Nobody has tested whether that
method helps the AI or limits it, because every filed case passed it by
construction. The short path removes the method so the two solutions can be
compared; both are run in
[stage 4](../stage4-runtime-verification/README.md#two-paths-two-tiers-each),
which reports their results side by side, not here.

**Each path designs two tiers.** Every **new** solution, from either path, is a
**unit-tier** procedure (drive the relevant classes directly; measure the
check's own operand) and a **cluster-tier** procedure (a real node; measure the
actual resource), each complete with its own predictions and readings table. A
tier that cannot be done is written as `n/a: <reason>` with what answers the same
question instead. The 11 long-path cases filed before this requirement are not
reworked: several describe one tier or none, and stage 4's audit handles them as
it does today.

**Stage 3 never judges the pair.** The long path judges whether a line is a
real case (its own verdict). Stage 4 runs both paths' solutions, both tiers
each, and files the results side by side; there is no rating of the two
solutions and no scoring across paths.

## 2. Completing stage 3 for a case

### 2.1 Before you start

- **Pick the case and its feed** (`3a` or `3b`, section 4). A case that already
  has a long-path file needs only the short path.
- **Who does what.** The long path is written by an AI session in this repo
  following [`long-path/README.md`](long-path/README.md) §2 and the playbook. The
  short path is run by you (or a runner session) with `run-case.py` in a terminal;
  its writer is a separate, isolated process
  ([`short-path/README.md`](short-path/README.md) §4).
- **Order and blindness.** The two paths can go in either order, or at the same
  time. Whoever writes the long-path file does not open
  `short-path/cases/<stem>.md`, and the short-path runner does not open
  `long-path/cases/<stem>.md`, until both are filed (section 3).

### 2.2 The sequence

| # | Step | Path | Result |
|---|---|---|---|
| 1 | Pick the case and feed | both | a stem and an entry pointer |
| 2 | Write and verify the case file, with both tiers | long | `long-path/cases/<stem>.md` and an `_INDEX.md` row; or an entry in `rejected.md`, `deferred.md` or `pending.md` |
| 3 | Isolation test once, then `run-case.py run`, judge the audit, `file` | short | `short-path/cases/<stem>.md` and an `_INDEX.md` row |
| 4 | Commit and push each filed solution (when you ask) | both | the solution is frozen in history |
| 5 | Hand off to stage 4 | both | up to four runs and a side-by-side |

### 2.3 Done when

Both files are filed and committed, each with its index row. A line the long path
rejects or defers has no long-path solution to pair with; running the short path
on it is optional and is not part of "done" (it would probe for false
rejections, and there is no rule yet for comparing that).

## 3. Rules that hold across both paths

- **Blind both ways.** A session writing one path's solution for a case does
  not open the other path's file for that case. In stage 4, an executor
  reads only its own path's solution; only the session that writes the side-by-side
  reads both paths' results. The short path additionally runs in isolation from this folder's
  guidance (see [`short-path/README.md`](short-path/README.md)).
- **Frozen on filing.** Once a solution is filed, record its sha256 in the
  path's `_INDEX.md`. A short-path solution is never edited; a new version is
  filed with `--supersede` and the old one is renamed `--vN`. A long-path case
  file takes only dated, documentation-only edits, and stage 4 runs the version
  frozen in its results §1.
- **Neither path runs anything or records a measured number.** Both design a
  test; stage 4 executes it ([`../README.md` §7.5](../README.md#75-active-scope-decisions-revised-2026-09-25)).
- **Same pinned source.** Both read `cassandra-5.0.9`
  ([`../README.md` §2](../README.md#2-source-of-truth-version-pinning--read-this-first)).
- **A line is recorded in exactly one place per path.** The long path's
  verdict-filing rule is in [`long-path/README.md`](long-path/README.md).

## 4. The two feeds

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

## 5. Folder map

| Path | Holds |
|---|---|
| [`long-path/`](long-path/README.md) | The long path: playbook, case template, master index, the cases, and the rejected / deferred / pending worklists |
| [`short-path/`](short-path/README.md) | The short path: contract, brief, template, index, and the solutions |
