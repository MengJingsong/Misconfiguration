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
| 0. Design audit | Checks the case's §9 against the requirements below; recommends and applies amendments; freezes §9a | results §1 |
| 1. Instruments | Writes, commits and checks the harness; confirms the environment | `harness/`, results §1 |
| 2. Run 1 | Follows the runbook (§9b–§9e) exactly, scripted and logged | raw readings, command log |
| 3. Conclusion | Matches the readings to one §9a row, with its logic in a fixed format | results §4 |
| 4. Self-check | Re-reads every cited raw file against the conclusion and its logic | results §5 |
| 5. Verdict and feedback | Files the verdict, the case's §10 field, any amendment | results §8 |

**Every step runs once per path and per tier.** A case with a short-path solution has up to four runs (long unit, long cluster, short unit, short cluster); see "Two paths, two tiers each" below.
| Run 2 (optional) | A fresh AI session repeats the runbook by hand, not run 1's script | results §6–§7 |

## What stage 4 consumes

Section 9 of a case file in [`../stage3-ai-deep-read/long-path/cases/`](../stage3-ai-deep-read/long-path/cases/).
Its intro and §9a are the summary: testability, the claim under test, the
procedure, the prediction, and the conclusions table every run is judged
against. §9b–§9e are the runbook: setup, workload, observables, and the
scenario steps.

**Read §9a's Testability line first.** A case marked *needs patched build* or
*not settable* is not worth a CloudLab allocation until someone patches the
build; a config-testable one can be run as written.

**Cases still in the old §9 layout** keep Testability in §9's field table, the
prediction in §9d, the conclusions in §9e and §9f, and the controls in §9g.
**Convert a case to the new layout before its first run**: §9a is what every
run is judged against, so it has to exist and be audited first. Which cases
are converted is tracked in [`../../../HANDOFF.md`](../../../HANDOFF.md), not here.

**A short-path solution** ([`../stage3-ai-deep-read/short-path/cases/`](../stage3-ai-deep-read/short-path/cases/))
is what stage 4 consumes for the short path of a case that has one. It is frozen
whole (its sha256 is in
[`../stage3-ai-deep-read/short-path/_INDEX.md`](../stage3-ai-deep-read/short-path/_INDEX.md)),
has no feedback field and is never amended; what a run learns goes into its
results file. Its parts play the roles of §9, per tier; the mapping is in "Two
paths, two tiers each" below.

If §9 cannot be executed as written, that is itself feedback — record it as a
runbook defect (below) rather than improvising a different experiment, because
a substituted workload no longer tests the traced path.

## Two paths, two tiers each

**Applies to a case that has both a long-path case file and a short-path
solution** ([stage 3](../stage3-ai-deep-read/README.md)). A case with only a
long-path file follows the protocol below unchanged, as all 11 filed cases do
today. Each solution has a **unit tier** and a **cluster tier**, so a case has up
to four runs: long unit, long cluster, short unit, short cluster. Stage 4 runs
**all** of them: there is no rating of the two solutions beforehand, no merging
of them into one run, and no scoring across paths. (Decided 2026-10-05; it
replaces the pre-run comparison of 2026-10-02.)

**Each path is its own run, on the same protocol.** Audit, instruments, run 1,
conclusion, self-check, verdict and optional run 2 apply to each path and tier
as written below. The conclusion matches the readings against **that path's own**
prediction and readings table, never the other path's.

| Protocol term | Long path | Short path |
|---|---|---|
| The design that is frozen | §9 of the case file (§9a frozen; hash of §9's text) | the whole solution file (its sha256 in `short-path/_INDEX.md`) |
| Unit tier / cluster tier | the §9 runbook for that tier | B2 / B3 |
| Runbook | §9b–§9e | B2a–B2e / B3a–B3e |
| Prediction | §9a | B2f / B3f |
| Conclusions table (what a reading means) | §9a | B2g / B3g |
| Controls | §9a and the runbook | B2h / B3h |
| Results file | `results/<stem>.md` | `results/<stem>--short.md` |
| Harness | `harness/<stem>/` | `harness/<stem>--short/` |
| Feedback into the case file (§10) | yes | none: the solution is never amended |

A tier a solution declares `n/a: <reason>` is not run; the results file says so
and gives the reason. The short path's own predictions are frozen at the
audit like the long path's (the hash goes in results §1).

**Independence.**
- An executor reads only its own path's solution, the shared files (this README,
  the templates, `environment.md`), and the Cassandra source. It does not open the
  other path's solution, results file, harness or readings before its own results
  are filed.
- Runs on the shared infrastructure follow the safety rules below: a separate
  local clone per run, one run at a time per node, every process stopped and
  checked afterwards. Reusing a build or a node image between paths is fine;
  reusing the other path's harness or readings is not.
- Order: unit tier before cluster tier within a path (the cheap tier tests the
  protocol first); the paths in either order.

**The side-by-side.** After the last run of a case, the session that finished it
writes `comparison/<stem>.md` from [`comparison/_TEMPLATE.md`](comparison/_TEMPLATE.md)
and a line in [`comparison/_INDEX.md`](comparison/_INDEX.md). It holds a table of
verdicts by path and tier, whether the conclusions agree (in prose), findings that
only one path's design produced, runbook defects per path, and cost. It edits
neither solution nor any results file, and rates nothing.

**What the two paths' results do.**
- **Long path:** unchanged. A refutation or bypass amends the case file; the
  numbers stay in the results file.
- **Short path:** its results file is the record. Its solution is not amended,
  and its brief and template are not corrected from run feedback (that would put
  human method back into the path under test). Runbook defects go in results §3.
- **Disagreement:** the readings decide each path's own prediction row. If the
  two paths' conclusions differ, record both and the point where the designs
  differ in the side-by-side; neither is overruled by the other. A re-run of that
  point is optional and is a new run of one path on its own protocol.

## Step 0 — the design audit

Before anything runs, the AI session checks the case's §9 against four groups
of requirements. Each line is rated **Met / Partly / Not met** with a one-line
note citing the section it checked. Audit the proposal, not the case: the three
rules were judged in stage 3. The exception is a finding that the claim itself
is unsound, which goes back to stage 3 as feedback.

| Group | The proposal must show |
|---|---|
| **A. It tests the core question** | The constrained quantity is named, and it is memory or disk bytes (or a count with a derivable byte size). The knob is varied — at least three values including the default — and usage is compared across them, so one can see whether usage follows the constraint. If the knob cannot be varied, the design says why and uses another approach that still answers "does it cap usage?". Usage is measured as the real resource (heap, off-heap, disk bytes), not only the check's own counter; if only the counter or a proxy is available, the gap is named. Usage is driven to the limit and past it. |
| **B. The logic runs step by step to a conclusion** | §9a opens with a short "How this verifies the hypothesis" block (hypothesis, test, logic, refuted-if) that matches the steps, prediction and conclusions below it. Each step says what it establishes. The prediction is stated before the run, in numbers or a clear relation (an exact ceiling, proportional, `limit × N`), so a reading can contradict it. Every plausible outcome has a conclusions row naming its evidence, including *usage exceeds the limit*, *flat across values*, *counter capped but the real resource grows* and *limit never reached*. A confirmation needs both the ceiling following the knob and direct evidence that the disallow branch fired. Each alternative explanation names the control that rules it out. |
| **C. It is specific and understandable to a human and an AI** | A human can follow the claim, the steps and the conclusions from the intro and §9a alone. An AI can run §9b–§9e without re-deriving the code path. The knob and how it is set, the values, workload sizes, commands, observables and how to read them, sampling times and stop conditions are exact. Terms are defined and each fact is stated once. |
| **D. It is runnable as written** | The harness and environment prerequisites exist, or are listed as work for step 1. The workload arithmetic reaches the limit: estimate the data volume, time, and disk and memory needed against what the node has. The source citations the prediction depends on (knob wiring, the usage operand, the disallow effect) are spot-checked against the pinned clone. |

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

**Auditing a short-path solution.** Audit it for **runnability and safety
only** — group D, plus the shared-infrastructure rules below, plus a check that
it states its predictions before any run. Do not apply groups A to C to it:
they are the long path's design requirements, and applying them would pull the
short solution into the long path's mold and defeat the purpose of running the two paths independently. Record
what groups A to C *would* have flagged as a side note in results §1, marked as
not applied. Audit each tier the solution defines (B2 and B3). The audit never edits the short file; fixes go to the harness and
the runbook defect log.

## The run protocol

### Before run 1

1. **Audit** (above), then **freeze the prediction.** Record in the results file
   the commit that holds the case file and a hash of §9's text:
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
| **Never build in, or add files to, the shared `cassandra-src` clone.** Clone it to local disk for each run: `git clone --branch cassandra-5.0.9 /proj/misconfiguration-PG0/git-repos/cassandra-src <local-dir>`. | Stage 3 reads that clone for line numbers. It already holds an untracked `HeapPoolTest.java` and a `build/` directory from earlier work. |
| **Never fill `/proj`.** Node data, commit log and hints go on local disk; a disk-limit case uses a local filesystem of fixed, known size. | `/proj/misconfiguration-PG0` is a shared NFS mount (95 GB). Filling it affects everyone, and its free space moves with other users' files. |
| A run 2 uses the same node type and the same kind of storage as run 1. | Flush and write timings depend on the disk. |
| Stop every process a run starts, and check none is left: `pgrep -f org.apache.cassandra.service.CassandraDaemon`. | A leftover node holds ports and memory and contaminates the next run. |
| Commit small text excerpts under `results/<case-file-stem>/run1/` (and `run2/`, if there is one); keep full logs outside the repo and record their path. | Keeps the repo small without losing the evidence. |

## Environment

Required by `build.xml` at the tag: **JDK 11** (the default) **or 17**, and
**Apache Ant 1.10 or later**. Record, for every run: the node, OS, JDK and Ant
versions, the local clone's commit, the case-file commit, and the harness
commit — the results template has the table.

**Setup steps:** [`environment.md`](environment.md) (JDK, Ant, clone, build, and the cluster-tier tools). The machine used for stage-3 work had no `java`, `jcmd` or `ant` on its PATH.

## What stage 4 produces, and where feedback lands

The split follows the repo's standing rule — **a verdict is filed by the stage
that judged it**, so measurements belong here, not in the case file.

| Feedback kind | Lands in |
|---|---|
| The design audit, every run, and the self-check — environment, readings, the AI's conclusion and logic, any comparison with run 2, and the verdict | a results file, `results/<case-file-stem>.md`, copied from [`_TEMPLATE.md`](_TEMPLATE.md) |
| A case's two paths side by side — verdicts by path and tier, whether the conclusions agree, findings only one path produced, defects, cost | `comparison/<stem>.md`, copied from [`comparison/_TEMPLATE.md`](comparison/_TEMPLATE.md), and a line in `comparison/_INDEX.md` |
| A short-path result (audit, runs, self-check, verdict, per tier) | `results/<stem>--short.md`; the short solution file is never amended |
| A refutation of the traced path (a **Refuted** row of §9a) | **amends the case file** — the affected section, dated, citing the results file |
| A bypass confirmed at runtime (the bypass row of §9a) | amends the case's §8 ceiling claim and its Target-3 note; the numbers stay here |
| A runbook defect (a step cannot run as written) | the results file's defect log, plus a dated fix to the case's §9b–§9e (only if §9a is unchanged; otherwise back to the audit) |
| A self-check part that does not hold, or a run 2 that disagrees with run 1, and cannot be resolved; or a human override | the results file; the case stays unverified (or follows the override, with its date and reason) |

Every case file carries a **Stage-4 feedback** field in §10, reading "none yet"
until a run reports. That field is the index of this relationship; keep it
current, because a case whose §8 claim has been refuted at runtime but still
reads as settled prose is the worst outcome this pipeline can produce.

## Where to start

Every filed case carries a §9 test design, so stage 4 waits only on execution.
**Which cases have run, and what comes next, is tracked in
[`../../../HANDOFF.md`](../../../HANDOFF.md)**; this README holds the protocol only.
The first case run, `memtable_heap_space`, is the worked example: results in
[`results/memtable_heap_space-tryAllocate-limit.md`](results/memtable_heap_space-tryAllocate-limit.md),
harness in `harness/memtable_heap_space-tryAllocate-limit/`.

**Scripts are per case, not a shared pattern.** Each case's workload, observables
and instruments differ (a unit test, a Byteman rule, a fixed-size filesystem, a
two-mode comparison), so there is no common runner. What every run script must
do is set by the run protocol above: log each command and its output, stop at
the first failed check, write a readings summary, and stop every process it
started. `memtable_heap_space`'s `run1/cluster-run.sh` is one example of that;
borrow what fits, not its structure.

**Where to start: unit tiers first.** They test the run protocol cheaply
before any cluster run. Four cases are far cheaper than the rest because unit
scaffolding already reaches the check:

| Case | Why it is cheap |
|---|---|
| `memtable_heap_space` | Done — the worked example. Its unit tier is two `ant testsome` commands on the restored `HeapPoolTest` (see "Prior art" below). |
| `cdc_total_space` | Done 2026-10-01 (results file in `results/`). `CommitLogSegmentManagerCDCTest` has the scaffolding (`CQLTester`, the CDC setup) but **not** a usable sweep: its `testWithCDCSpaceInMb` is private, and its non-blocking assertion allows three times the limit. The run needed a new harness test (`CdcTotalSpaceCeilingTest`), a Byteman creation trace, a sampler for `cdc_raw`, and a consumer emulator. The unit yaml's `commitlog_segment_size` is 5 MiB, not the node's 32 MiB. |
| `MAX_HINT_BUFFERS` | Predicts an **exact** ceiling, `n × bufferSize` (96 MiB at defaults), not a trend — so it is the sharpest falsification in the set. `HintsBufferPoolTest.testBackpressure()` already proves the disallow branch via Byteman. Confirm Byteman resolves as a test dependency first. |
| `max_space_usable_for_compactions_in_percentage` | `DirectoriesTest`, `PartialCompactionsTest` and `CompactionsBytemanTest` between them cover the arithmetic, the injection point and all three disallow outcomes. |

**Two designs need a cluster before they say anything**, because their finding
is a default-mode gap rather than a limit:
`native_transport_receive_queue_capacity` (the whole experiment is a
comparison of `throw_on_overload` true vs. false — a single-mode run correctly
observes nothing) and `DataDirectory_getAvailableSpace` (the guard does not run
under the default partitioner, so the two arms need **separate clusters**).

**Prior art.** The `memtable_heap_space` unit test, `HeapPoolTest.java`, is restored
under `harness/` (its origin is recorded in that folder's README). Earlier per-case
trigger notes are in `git show e7f9963:HANDOFF.md`.
