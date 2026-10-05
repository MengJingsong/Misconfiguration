# Stage 3, short path — verification solutions without the human method

**An experiment, decided 2026-10-02.** The short path is stage 3's second path
(see [`../README.md`](../README.md)); the established one is the
[long path](../long-path/README.md). No solution is filed yet; the pilot on
the three closed cases was skipped by decision, so the first real comparison
happens when a case gets both solutions and reaches stage 4.

## What it is

For a candidate code location, an AI does **two things**:

1. **Trace the constraint** — find where the limit is declared, its unit and
   default, how it is set, which resource it bounds, and the mechanism that
   enforces it.
2. **Design a verification solution** — the test stage 4 would run — from
   whatever the AI itself collects from the sources, and its own decisions.

It applies **none of the long path's method**: not the three rules (§3.4–§3.6
of the experiment README), not the three enforcement patterns (§3.2), not the
test-design rules (§8), not the case template, not the playbook. The reason is
to find out whether that method helps the AI or limits it. If the two
solutions come out the same, the method costs nothing; if the short one is
better, the method is holding the AI back; if worse, the method is earning its
keep.

**The short path files no verdict.** It does not say whether the line is "a
case worth testing". It states the claim its own solution tests and designs
that test. Whether the two solutions agree, and how many tests they need, is
decided in stage 4 ([comparison](../../stage4-runtime-verification/README.md#solution-comparison)).

## What stays, and what goes

| Kept — objective and safety, not method | Dropped — method |
|---|---|
| The goal: does the constraint cap the node's memory or disk usage? | The three rules and three patterns |
| The pinned `cassandra-5.0.9` source | The six test-design rules and the §9 layout |
| Shared-infrastructure safety rules for stage 4 | The case template and the playbook |
| A minimal output skeleton ([`_TEMPLATE.md`](_TEMPLATE.md)), so the pair can be compared | Every filed case, every results file, `HANDOFF.md` |

**Scope: memory and disk.** CPU constraints are out of scope for now, matching
the experiment's resource scope (§3.3 of its README). Revisit if the
comparison shows the long path's Rule 2 excluded something real.

## Files

| File | Holds |
|---|---|
| [`BRIEF.md`](BRIEF.md) | The whole prompt the isolated agent receives, together with `_TEMPLATE.md`. Self-contained: it links to nothing in this repo. |
| [`_TEMPLATE.md`](_TEMPLATE.md) | The output skeleton: A. constraint trace, B. verification solution, C. paths read. No verdict field. |
| [`_INDEX.md`](_INDEX.md) | One row per filed solution: stem, entry pointer, filing date, sha256, isolation, leakage audit, comparison link. |
| [`cases/`](cases/) | The solutions, one file per case, named by the same stem as the long-path file. |

## Producing a solution

1. **Choose the case and its entry pointer** — a `file:line` in the pinned
   source, the same kind of pointer stage 1/2 gives the long path (feed `3a`),
   or one the session found itself (feed `3b`). Nothing else about the case is
   given: no constraint name, no verdict, no measured number.
2. **Build the prompt:** `BRIEF.md`, then `_TEMPLATE.md`, then one line,
   `Entry pointer: <file>:<line>`. Nothing else goes in.
3. **Run it in isolation.**
   - *Preferred:* a separate Claude Code session started with the Cassandra
     clone as its working directory and settings that deny reads of this
     repository. Check that the deny rule really blocks a read before relying
     on it.
   - *Fallback:* a subagent given only the prompt. Isolation is then by
     instruction alone, so step 4 is mandatory.
4. **Leakage audit.** From the session's tool-call log, confirm it read nothing
   under this repository, and that the solution names no long-path file and
   quotes no measured number from stage 4. Record the result in `_INDEX.md`.
   A solution that fails the audit is discarded and re-run, not edited.
5. **File it** as `cases/<stem>.md`. The stem is the long-path file's stem when
   the case has one; otherwise it follows the experiment README's §6.1 naming
   from the entry pointer. The agent never names the file.
6. **Freeze it:** `sha256sum cases/<stem>.md` into `_INDEX.md`. A short
   solution is **never amended** after filing — it has no feedback field. What
   stage 4 learns goes in the comparison and results files.

**Blind both ways.** Whoever writes a case's short solution does not open that
case's long-path file, and whoever writes the long-path file does not open the
short one. Only the stage-4 comparator reads both. For the 11 cases already
filed, the long files exist, so the short-path agent must be a fresh session
that never saw them (an agent that has read this repo cannot be one).

**Noise check (optional).** Running the short path twice on a case, filed as
`cases/<stem>--r2.md`, measures run-to-run variation, so a disagreement with the
long path is not mistaken for a difference between the paths.
