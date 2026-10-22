# Stage 3 — AI deep read

Stage 3 reads the Cassandra source. For every target line it produces a **case
file**: a trace of the constraint, an estimate for the line, and a two-tier
verification solution that [stage 4](../stage4-runtime-verification/README.md) runs.
Stages 1 and 2 only shrink and order what stage 3 must read; neither produces a
finding.

## 1. Two agents, one folder

Two agents write case files. Both write into [`cases/`](cases/), and the file name
says which one wrote it: `<stem>--autonomous.md` or `<stem>--guided.md`
(`<stem>` is `[constraint]-[function]-[operand]`, [`../README.md` §6.1](../README.md#61-naming)).

| | Autonomous agent | Guided agent |
|---|---|---|
| Playbook | [`playbook-autonomous.md`](playbook-autonomous.md): the target only | [`playbook-guided.md`](playbook-guided.md): the target plus human suggestions (the three rules, the enforcement patterns, the test-design method) |
| Template | [`_TEMPLATE-autonomous.md`](_TEMPLATE-autonomous.md) | [`_TEMPLATE-guided.md`](_TEMPLATE-guided.md) |
| Estimates the line | yes (`positive`, `negative`, `undetermined`) | yes (`positive`, `negative`, `undetermined`) |
| Judged after stage 4 | true positive / false positive / true negative / false negative / undetermined, by comparing the estimate with the stage-4 effect ([`../stage4-runtime-verification/README.md`](../stage4-runtime-verification/README.md#outcome-class)) | same |
| Output | `cases/<stem>--autonomous.md` | `cases/<stem>--guided.md` |
| Started by | you, by hand, in a Claude Code session (desktop app) | an AI session in this repo; it asks you whether to read the autonomous file |

**Order for a new case.** Run the autonomous agent first. Run the guided agent only
if needed (you decide, for example when the autonomous file is incomplete or
unsure); otherwise it is skipped. A case may therefore have one file or two. There
is no isolation rule: the guided agent may read the autonomous file, when you say
so (section 3.2).

**Stage 4 does not care which agent wrote a file.** It audits the verification
solution in each case file, runs it, and saves the conclusion in
[`../stage4-runtime-verification/results/`](../stage4-runtime-verification/results/).
There is no comparison step and no scoring across agents.

## 2. Files

| File | Holds |
|---|---|
| [`playbook-autonomous.md`](playbook-autonomous.md) | The autonomous agent's whole instruction. |
| [`playbook-guided.md`](playbook-guided.md) | The guided agent's instruction: how a feed is worked, the seven steps, the pitfalls. |
| [`_TEMPLATE-autonomous.md`](_TEMPLATE-autonomous.md) | A. constraint trace, B. verification solution (B1 claim, B2 unit tier, B3 cluster tier, B4 risks), C. sources read, D. stage-4 feedback. |
| [`_TEMPLATE-guided.md`](_TEMPLATE-guided.md) | The eleven-section case file; §9 is the test design; §10 holds provenance, estimate and stage-4 feedback. |
| [`cases/`](cases/) | The case files of both agents. Flat; the module is a field, not a folder. |
| [`_INDEX.md`](_INDEX.md) | One row per case file, with an Agent column. |
| [`predicted-negative.md`](predicted-negative.md) | Lines read with the source open and refused, each citing the rule it failed. Existing entries have **no case file yet**; each leaves this file when its case file is written (section 4). |
| [`undetermined.md`](undetermined.md) | Lines left **unjudged**; a worklist. No case file for an undetermined line. |
| [`predicted-positive.md`](predicted-positive.md) | Qualified against the three rules but not yet written up. |

## 3. Completing stage 3 for a case

### 3.1 Sequence

| # | Step | Who | Result |
|---|---|---|---|
| 1 | Pick the case and its feed (section 5) | you (or an AI) | a stem and an entry pointer (`file:line`) |
| 2 | Run the autonomous agent with the playbook, the template and the target | you start it by hand | `cases/<stem>--autonomous.md` |
| 3 | Check the file against its template; add its `_INDEX.md` row (with sha256, section 6) | AI | a filed case |
| 4 | Only if needed, run the guided agent | AI session in this repo | `cases/<stem>--guided.md`, or an entry in `undetermined.md` |
| 5 | Commit and push (when you ask) | AI | the file is frozen in history |
| 6 | Hand off to stage 4 | AI | one results file per case file |

### 3.2 The guided agent's first step

Before it starts a case, or a batch of cases, the guided agent asks you whether it
may read the autonomous agent's file for each case. If you say yes, you name the
file and the guided file records it in §10 ("Autonomous reference"). If you say no,
it works from the target and the playbook alone.

### 3.3 Done when

Each case file you want is filed, carries its estimate and ground, and has its `_INDEX.md` row.
A line that only has a `predicted-negative.md` or `undetermined.md` entry is not done.

## 4. Where a line is recorded

Every line has exactly one home, and one rule decides it: **filed by the stage that
judged it, not the stage that surfaced it.**

| Outcome | Home |
|---|---|
| Positive estimate | a case file in [`cases/`](cases/); a guided positive estimate not yet written up waits in [`predicted-positive.md`](predicted-positive.md) |
| Negative estimate (either agent) | **also a case file** in [`cases/`](cases/), with its estimate and ground; its verification solution tests that usage does *not* follow the constraint |
| Undetermined | [`undetermined.md`](undetermined.md), or an `undetermined` estimate in the case file; no prediction yet |
| Existing `predicted-negative.md` entries | stay where they are as a queue; **each one is to be written up as a case file**, and its entry is replaced by a one-line pointer to the file |

Stage 2 cannot produce a (b)/(c) deferral: deciding that a line "would qualify only
under (b) or (c)" means tracing where the verdict is read, which no row shows.
All deferrals are therefore stage-3 judgments. If stage 2 reaches a line stage 3
already judged, cite the entry rather than re-recording it.

## 5. The two feeds

Stage 3 is entered from either of two directions, for either agent. **Both are
required; they cover different blind spots.**

| Feed | What points stage 3 at a line | Coverage | Progress measurable? |
|---|---|---|---|
| **3a — from stage 1/2** | [`../stage2-ai-preprocessing/bands.md`](../stage2-ai-preprocessing/bands.md), band A first | bounded, enumerable (row counts, bands, batch table) | **yes** |
| **3b — from raw source** | the session's own reading of subsystems and call chains | unbounded, opportunistic | **no** — there is no denominator |

- **3a** is the cheap, systematic feed. Stages 1 and 2 exist to shrink and order what stage 3 must read.
- **3b is not optional.** It is the standing insurance against stage 1's *syntactic* blind spot: it found the `cdc_total_space` ternary, which stage 1 cannot surface at all, because the comparison is not in an `if` condition. It plays the same role against that blind spot that band C plays against stage 2's *vocabulary* blind spot. Its weakness is cost: the full source is far more than one session can read.

**Record the feed (`3a` or `3b`) on every case and every entry.** Only 3a has a
denominator; without the field, "stage 3 progress" has no coherent answer.

## 6. Rules that hold for both agents

- **Frozen on filing.** Once an autonomous file is filed, record its sha256 in
  `_INDEX.md` §4. Both kinds of file take dated amendments from stage 4's design
  audit (see its README); an autonomous file's index line then gets the amendment's
  date and new hash, and a guided file's frozen §9 hash is recorded in its stage-4
  results §1. Apart from those, a guided file takes only dated, documentation-only
  edits. Stage 4 runs the version frozen in its results §1.
- **Neither agent runs anything or records a measured number.** Both design a test;
  stage 4 executes it ([`../README.md` §7.5](../README.md#75-active-scope-decisions-revised-2026-09-25)).
- **Same pinned source.** Both read `cassandra-5.0.9`
  ([`../README.md` §2](../README.md#2-source-of-truth-version-pinning--read-this-first)).
- **Both tiers, always.** Every new file designs a unit tier and a cluster tier, or
  writes `n/a: <reason>` for a tier that cannot be done, with what answers the same
  question instead.
- **A file's agent is its name.** `--autonomous` or `--guided`; a file is never
  renamed to the other.
