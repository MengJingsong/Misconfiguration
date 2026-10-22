# Stage 4 — runtime verification

**The stage that runs the experiment.** Stage 3 reads the source and writes a
test design; stage 4 audits that design, executes it on a real build or
cluster, measures, and reports back. The two are deliberately separate: stage
3's rule is that everything it files is decidable from source alone, with no
cluster, no build and no run, and that rule survives only if execution lives
elsewhere.

Reserved by decision on 2026-09-23 and **opened on 2026-09-25**, when test
design became part of stage 3 ([`../README.md` §8](../README.md#8-designing-a-test-for-a-case)).
**No human approval or review is required at any step** (decided 2026-09-30).
An AI session audits the design, runs it, checks its own conclusion against the
raw files, and owns the verdict. Jingsong may read and overrule any verdict at
any time, but nothing waits for that; an override is recorded in the results
file with its date and reason, and the case's §10 is amended.
*Replaces the decision of 2026-09-29, under which Jingsong approved results §1,
reviewed run 1 (required), approved runbook fixes, owned the verdict, and could
run a by-hand run 2.*

## What stage 4 tests

**One question per case: does the constraint cap the resource (memory or disk)
usage?** The common approach is dose-response — vary the constraint, drive usage
to the limit and past it, and check that the measured usage follows the
constraint ([`../README.md` §8.1](../README.md#81-the-shape-of-the-experiment)).
A case whose knob cannot be varied (a hard-coded constant, a type bound) needs a
different approach that still answers the same question, such as two arms that
differ in one condition; the design has to say why and how.

## The division of labour

| | Stage 3 | Stage 4 |
|---|---|---|
| Evidence | the source, against the three rules | a measured run |
| Produces | a test design — §9 of each case file | a design audit, numbers, and a verdict on the design's prediction |
| Records numbers? | **never** | yes, here |
| Needs a cluster/build? | no | yes |

Within stage 4, every step is done by an AI session:

| Step | What it does | Output |
|---|---|---|
| 0. Design audit | Checks the case file's design (§9 of a guided file; section B of an autonomous file) against the requirements below; recommends and applies amendments; freezes the design | results §1 |
| 1. Instruments | Writes, commits and checks the harness; confirms the environment | `harness/<case-file-stem>/`, results §1 |
| 2. Run 1 | Follows the runbook (§9b–§9e) exactly, scripted and logged | raw readings, command log |
| 3. Conclusion | Matches the readings to one §9a row, with its logic in a fixed format | results §4 |
| 4. Self-check | Re-reads every cited raw file against the conclusion and its logic | results §5 |
| 5. Verdict and feedback | Files the verdict, the case file's feedback field (§10 of a guided file, section D of an autonomous file), any amendment | results §8 |
| Run 2 (optional) | A fresh AI session repeats the runbook by hand, not run 1's script | results §6–§7 |

**Every step runs once per case file and per tier.** A case file has up to two runs (unit tier, cluster tier). A case with two files, one from each agent, is two independent sets of runs; stage 4 does not compare them.

## What stage 4 consumes

**Every case file in [`../stage3-ai-deep-read/cases/`](../stage3-ai-deep-read/cases/), whichever agent wrote it.** The suffix of the file name says which:
`<stem>--guided.md` or `<stem>--autonomous.md`. The results file and the harness folder take the same name, so a
case's stem including its suffix is its key everywhere in this stage. A file with a negative estimate
is run like any other: its claim is that usage does **not** follow the constraint, and the conclusion table says what each
outcome means for that claim.

| Protocol term | Guided file | Autonomous file |
|---|---|---|
| The design that is frozen | §9 (§9a frozen; hash of §9's text) | the whole file (sha256 of the file after the audit's amendments) |
| Unit tier / cluster tier | the §9 runbook for that tier | B2 / B3 |
| Runbook | §9b–§9e | B2a–B2e / B3a–B3e |
| Prediction | §9a | B2f / B3f |
| Conclusions table (what a reading means) | §9a | B2g / B3g |
| Controls | §9a and the runbook | B2h / B3h |
| Feedback field in the case file | §10 | section D |
| Results file | `results/<stem>--guided.md` | `results/<stem>--autonomous.md` |
| Harness | `harness/<stem>--guided/` | `harness/<stem>--autonomous/` |

Below, "§9a" means the prediction and conclusions table of the tier being run, and "§9b–§9e" its runbook, in either kind of file.

**Read the Testability line first** (§9a of a guided file; B1 or the head of a tier in an autonomous file). A case marked
*needs patched build* or *not settable* is not worth a CloudLab allocation until someone patches the build; a
config-testable one can be run as written.

**A file written before the two-tier rule** may describe one tier or none. The audit adds the missing tier as a dated
amendment before the freeze (a unit tier: drive the check's classes directly; a cluster tier: a real node with the knob at the
boundary), or records `n/a: <reason>` for it with what answers the same question instead. A tier is never silently dropped.
Which cases are converted is tracked in [`../../../HANDOFF.md`](../../../HANDOFF.md), not here.

A tier a file declares `n/a: <reason>` is not run; the results file says so and gives the reason.

If the design cannot be executed as written, that is itself feedback — record it as a runbook defect (below) rather than
improvising a different experiment, because a substituted workload no longer tests the traced path.

## Order and independence

- **Unit tier before cluster tier** within a case file: the cheap tier tests the protocol first.
- **Each case file is its own run, on the same protocol.** The conclusion matches the readings against **that file's own**
  prediction and readings table, never another file's. If a case has an autonomous and a guided file whose conclusions
  differ, record both in their own results files; neither is overruled by the other. There is no side-by-side file and no
  scoring across agents (decided 2026-10-19; it replaces the 2026-10-05 rule of four runs per case with a comparison).
- **No blind executor.** The session that runs a file is an ordinary AI session in this repository and reads whatever it
  needs. The isolation machinery of the earlier short path (the isolated executor, its blindness check and the prompts around
  it) was removed on 2026-10-19.
- Runs on the shared infrastructure follow the safety rules below: a separate local copy per run, one run at a time per
  node, every process stopped and checked afterwards.

## Step 0 — the design audit

Before anything runs, the AI session checks the case's §9 against four groups
of requirements. Each line is rated **Met / Partly / Not met** with a one-line
note citing the section it checked. Audit the proposal, not the case: the three
rules were judged in stage 3. The exception is a finding that the claim itself
is unsound, which goes back to stage 3 as feedback.

| Group | The proposal must show |
|---|---|
| **A. It tests the core question** | The constrained quantity is named, and it is memory or disk bytes (or a count with a derivable byte size). The knob is varied — at least three values including the default — and usage is compared across them, so one can see whether usage follows the constraint. If the knob cannot be varied, the design says why and uses another approach that still answers "does it cap usage?". Usage is measured as the real resource (heap, off-heap, disk bytes), not only the check's own counter; if only the counter or a proxy is available, the gap is named. Usage is driven to the limit and past it. **For a file whose claim is that the constraint does not cap usage** (negative estimate), the design also needs a **positive control**: the same workload and instruments, shown to move usage under a condition where a cap is known to bind (a closed `Confirmed` case, or a second knob that binds on the same resource). Without one, "flat" cannot be told from "the workload could not have shown an effect", and the file cannot reach Confirmed. |
| **B. The logic runs step by step to a conclusion** | §9a opens with a short "How this verifies the hypothesis" block (hypothesis, test, logic, refuted-if) that matches the steps, prediction and conclusions below it. Each step says what it establishes. The prediction is stated before the run, in numbers or a clear relation (an exact ceiling, proportional, `limit × N`), so a reading can contradict it. Every plausible outcome has a conclusions row naming its evidence, including *usage exceeds the limit*, *flat across values*, *counter capped but the real resource grows* and *limit never reached*. A confirmation needs both the ceiling following the knob and direct evidence that the disallow branch fired. Each alternative explanation names the control that rules it out. |
| **C. It is specific and understandable to a human and an AI** | A human can follow the claim, the steps and the conclusions from the intro and §9a alone. An AI can run §9b–§9e without re-deriving the code path. The knob and how it is set, the values, workload sizes, commands, observables and how to read them, sampling times and stop conditions are exact. Terms are defined and each fact is stated once. |
| **D. It is runnable as written** | The harness and environment prerequisites exist, or are listed as work for step 1. The workload arithmetic reaches the limit: estimate the data volume, time, and disk and memory needed against what the node has. The source citations the prediction depends on (knob wiring, the usage operand, the disallow effect) are spot-checked against the pinned clone. |

**Verdict wording.** One vocabulary for every file. A verdict is a row of the file's conclusions table, and **"Confirmed" always
means the file's own claim held**, whichever way the claim points. Each results file therefore starts its verdict with the
**claim tested** (taken from §9a or B1) and records a second field, **Effect on the constraint**: `caps` / `does not cap` /
`caps only on some paths (bypass)` / `undetermined`. Results, the stage 3 index and HANDOFF show both, for example
"Confirmed — does not cap". A file that claims "does not cap" must have at least these rows: usage follows the constraint
(**Refuted**), usage is flat across the knob values with the positive control moving (**Confirmed**), and the limit was never
reached or the control did not move (**Not confirmed** or **Invalid**, never Confirmed).
**A refuted negative estimate is not re-estimated.** If the readings show usage does follow the constraint, the file's Estimate line is
left as filed; the refutation is recorded in the results file's verdict and Effect field and in the case file's feedback field
(§10, or section D), and `_INDEX.md` keeps the original estimate with a pointer to the results file. Stage 3 does not re-estimate
because of it.

### Outcome class

Once stage 4 has run, a case is classed by comparing its stage-3 estimate with the stage-4 effect on the constraint (stage 4 taken as the truth): **true positive** (estimate `positive`, effect `caps`), **false positive** (`positive`, `does not cap`), **true negative** (`negative`, `does not cap`), **false negative** (`negative`, `caps`), or **undetermined** (the unit and cluster tiers disagree, or a tier could not settle the effect: Not confirmed, partial). `caps` includes soft caps and caps with a recorded bypass. The class is recorded beside the verdict; Confirmed / Refuted and the Effect field keep their meaning, and a refuted estimate is still not re-estimated. Abbreviations in tables: TP, FP, TN, FN.

The results file records it on the line after Status (`Outcome class:`) and §8 gives the one-line reason; the stage-3 index carries it in the Outcome class column.

**Output, in results §1:** the ratings, a list of recommendations, what was done
with each, and a bottom line — **Ready**, **Ready after amendments**, or
**Blocked** (with the reason, and the recommendation for stage 3).

**What the AI does with recommendations.**

- Those needed for a valid, unambiguous run — a missing value, command or stop
  condition, an unstated outcome, a workload too small to reach the limit — are
  **applied to the case file as dated amendments** before the freeze.
- The rest stay listed as recommendations for stage 3 and are not applied.
- A recommendation that changes §9a's claim, prediction or conclusions table is
  allowed only here, before run 1 of that tier, and only for a reason that does
  not depend on any reading.

**Auditing an autonomous file.** Apply groups A to D as for a guided file, reading each group against the file's own sections
instead of §9. Group B's "How this verifies the hypothesis" block is mapped, not added: the hypothesis is B1, the test and
logic are B2b–B2e and B3b–B3e, the prediction is B2f and B3f, and the conclusions table is B2g and B3g (refuted-if is the
row of B2g and B3g that contradicts B1). Amendments are dated, appear in the file next to the text they change, and are
recorded in the stage-3 index (`_INDEX.md` §4) with the new sha256, which is the frozen version in results §1. The file's
feedback goes in its section D.

## The run protocol

### Before run 1

1. **Audit** (above), then **freeze the prediction.** Record in the results file
   the commit that holds the case file and, for a guided file, a hash of §9's text (for an autonomous file, its sha256):
   `sed -n '/^## 9\. /,/^## 10\. /p' <case file> | git hash-object --stdin`.
   The hash covers §9 only, because the file's §10 takes the feedback after every
   run. §9a is now fixed. If §9a turns out to be wrong later, that is a dated
   amendment to the case file and the affected tier starts again — see the rule
   below.
2. **Commit the instruments** — when Jingsong asks for a commit, as always.
   Any code a run needs that is not upstream — a restored test class, a Byteman
   rule — goes under `harness/<case-file-stem>/` in this folder before run 1,
   and run 1 and any run 2 use those same files. Check each instrument before
   run 1 (parse-check a rule, a known-answer run) and record the check. Share
   instruments, not procedure: a run 2 follows the runbook by hand.
3. **Fill results §1** from the template: the audit, the frozen version, the
   harness, the tiers and capacity values. No approval is needed.

**Predictions are not tuned to data.** Once any reading exists, §9a is not edited
to fit it. A reading that contradicts the prediction is the result — a
**Refuted** or **Not confirmed** row — and the feedback goes to the case file
(below). Only a mistake that does not depend on the readings, such as a wrong
line citation, may be amended, and then the tier restarts.

### Run 1

- **Scripted and logged.** Every step runs from a script that logs each command
  and its output (`script`, `tee`); the log is the evidence. Long steps run in
  the background and their logs are read, not guessed.
- **Stops at the first step it cannot run as written.** It records a runbook
  defect — the step, the problem, the fix — in results §3. If the fix leaves
  §9a's claim, prediction and conclusions unchanged, the AI makes it in the case
  file (dated) and the affected tier restarts from its beginning. If it would
  change §9a, the case goes back to the audit.
- **Concludes in the fixed format** of the results template: validity,
  readings, matched row, excluded rows, observed vs. inferred, deviations and
  gaps. Every statement cites a raw file.

### Self-check and verdict

With no human review, the conclusion has to survive the AI's own second look.

- **Re-read, don't recall.** Open each raw file the conclusion cites and confirm
  it says what the conclusion says. Do it part by part, starting with the
  inferred statements the conclusion depends on (part 5).
- **Check the logic, not only the numbers.** The readings must lead to the
  matched §9a row by the audited steps, and the conclusion must answer the core
  question: does the constraint cap usage, and does usage follow it?
- **Record each part** as holds / does not hold, with the note, in results §5.
  A part that does not hold is fixed or it downgrades the conclusion to *Not
  confirmed*; it is never left unrecorded.
- **Then file the verdict**: the results file's §8 and status line, the case
  file's §10 "Stage-4 feedback" (with commits, checked in `git log`), any section
  the result amends, and the state rows in `HANDOFF.md`. The AI says what it
  filled. It does not commit or push unless asked.

### Run 2 — optional, fresh AI session

- **Purpose: insurance.** The only independent check left, since no human
  reviews. Worth its cost when the conclusion rests on inferred statements, the
  self-check cannot settle a part from run 1's evidence, or the result would
  refute the case or confirm a bypass.
- **Independent.** A new session follows §9b–§9e by hand with the same harness
  and the same case-file version, and does not read run 1's conclusion until its
  own is written.
- **Before it starts,** fill the results file's agreement criteria: for each
  observable, whether the runs must match exactly (a unit test's pass/fail, an
  exact ceiling) or in shape (a peak that follows the knob), and with what
  tolerance.

### Compare and decide

| Situation | Action |
|---|---|
| No run 2; the self-check holds | Verdict: run 1's §9a row. |
| No run 2; a part of the self-check does not hold | Fix it against §9a's table and run 1's raw files, or downgrade to *Not confirmed*, or choose run 2. Record which part was wrong and why. |
| Run 2 matches run 1's §9a row, readings within the agreed tolerance | Verdict: that row. |
| Run 2's readings differ beyond tolerance | Find the cause (environment, a deviation, an instrument) and re-run the affected tier. No verdict until they agree. |
| Readings agree, conclusions differ | A reasoning error. Settle it against §9a's table, and record which conclusion was wrong and why. |
| No §9a row fits | Feedback to stage 3: the prediction missed an outcome. Amend §9a (dated) and start the tier again. |

## Running safely on shared infrastructure

| Rule | Why |
|---|---|
| **Never build in, or add files to, the repository's `cassandra/cassandra-5.0.9/`.** Copy it to local disk for each run: [`copy-source.sh`](copy-source.sh) `<local-dir>` ([`environment.md`](environment.md) §2). Runs before 2026-10-22 cloned the separate `cassandra-src` clone instead, which held the same files. | Stage 3 reads that source for line numbers, and a build or a copied test file there would show up as a change to this repository. |
| **Never fill `/proj`.** Node data, commit log and hints go on local disk; a disk-limit case uses a local filesystem of fixed, known size. | `/proj/misconfiguration-PG0` is a shared NFS mount (95 GB). Filling it affects everyone, and its free space moves with other users' files. |
| A run 2 uses the same node type and the same kind of storage as run 1. | Flush and write timings depend on the disk. |
| Stop every process a run starts, and check none is left: `ps -eo cmd | grep '[C]assandraDaemon'` (not `pgrep -f` inside an inline `ssh host '...'` string: it matches its own shell). | A leftover node holds ports and memory and contaminates the next run. |
| Commit small text excerpts under `results/<case-file-stem>/run1/` (and `run2/`, if there is one); keep full logs outside the repo and record their path. | Keeps the repo small without losing the evidence. |

## Environment

Required by `build.xml` at the tag: **JDK 11** (the default) **or 17**, and
**Apache Ant 1.10 or later**. Record, for every run: the node, OS, JDK and Ant
versions, the local copy's source (repository commit), the case-file commit, and the harness
commit — the results template has the table.

**Setup steps:** [`environment.md`](environment.md) (JDK, Ant, copy, build, and the cluster-tier tools). The machine used for stage-3 work had no `java`, `jcmd` or `ant` on its PATH.

## What stage 4 produces, and where feedback lands

The split follows the repo's standing rule — **a verdict is filed by the stage
that judged it**, so measurements belong here, not in the case file.

| Feedback kind | Lands in |
|---|---|
| The design audit, every run, and the self-check — environment, readings, the AI's conclusion and logic, any comparison with run 2, and the verdict | a results file, `results/<case-file-stem>.md`, copied from [`_TEMPLATE.md`](_TEMPLATE.md) |
| A refutation of the traced path (a **Refuted** row of §9a) | **amends the case file** — the affected section, dated, citing the results file |
| A bypass confirmed at runtime (the bypass row of §9a) | amends the case's §8 ceiling claim and its Target-3 note; the numbers stay here |
| A runbook defect (a step cannot run as written) | the results file's defect log, plus a dated fix to the case's §9b–§9e (only if §9a is unchanged; otherwise back to the audit) |
| A self-check part that does not hold, or a run 2 that disagrees with run 1, and cannot be resolved; or a human override | the results file; the case stays unverified (or follows the override, with its date and reason) |

Every case file carries a **Stage-4 feedback** field (§10 of a guided file, section D of an autonomous file), reading "none yet"
until a run reports. That field is the index of this relationship; keep it
current, because a case whose §8 claim has been refuted at runtime but still
reads as settled prose is the worst outcome this pipeline can produce.

## Where to start

Every filed case carries a §9 test design, so stage 4 waits only on execution. **Which cases have run, and what comes next,
is tracked in [`../../../HANDOFF.md`](../../../HANDOFF.md)**; this README holds the protocol only.

- **Any case file:** start with [`case-notes.md`](case-notes.md), which lists what the closed cases teach, which are cheap
  to start with and which need a cluster before they say anything, and the worked examples.
- **Setting up a node:** [`environment.md`](environment.md).

**Scripts are per case, not a shared pattern.** Each case's workload, observables and instruments differ (a unit test, a
Byteman rule, a sampler), so there is no common runner. What every run script must do
is set by the run protocol above: log each command and its output, stop at the first failed check, write a readings
summary, and stop every process it started. **Unit tiers first:** they test the run protocol cheaply before any cluster run.
