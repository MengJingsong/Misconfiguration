# Stage 4 — runtime verification

**The stage that runs the experiment.** Stage 3 reads the source and writes a
test design; stage 4 executes it on a real build or cluster, measures, and
reports back. The two are deliberately separate: stage 3's rule is that
everything it files is decidable from source alone, with no cluster, no build
and no run, and that rule survives only if execution lives elsewhere.

Reserved by decision on 2026-09-23 and **opened on 2026-09-25**, when test
design became part of stage 3 ([`../README.md` §8](../README.md#8-designing-a-test-for-a-case)).
**Every procedure is run twice** (decided 2026-09-28): first by an AI session,
which also draws the conclusion and states its logic; then independently by
Jingsong, who checks that conclusion and owns the verdict.

## The division of labour

| | Stage 3 | Stage 4 |
|---|---|---|
| Evidence | the source, against the three rules | a measured run |
| Produces | a test design — §9 of each case file | numbers, and a verdict on the design's prediction |
| Records numbers? | **never** | yes, here |
| Needs a cluster/build? | no | yes |

Within stage 4:

| | Run 1 — AI session | Run 2 — Jingsong |
|---|---|---|
| Follows | the case's runbook (§9b–§9e), exactly | the same runbook, by hand — not run 1's script |
| Records | raw readings and a full command log | raw readings, **before** opening run 1's |
| Concludes | which §9a row matched, with its logic in a fixed format | which §9a row the readings match; then checks run 1's logic |
| Owns the verdict | no | **yes** |

## What stage 4 consumes

Section 9 of a case file in [`../stage3-ai-deep-read/cases/`](../stage3-ai-deep-read/cases/).
Its intro and §9a are the summary: testability, the claim under test, the
procedure, the prediction, and the conclusions table both runs are judged
against. §9b–§9e are the runbook: setup, workload, observables, and the
scenario steps.

**Read §9a's Testability line first.** A case marked *needs patched build* or
*not settable* is not worth a CloudLab allocation until someone patches the
build; a config-testable one can be run as written.

**Cases still in the old §9 layout** — every case except `memtable_heap_space`,
as of 2026-09-28 — keep Testability in §9's field table, the prediction in
§9d, the conclusions in §9e and §9f, and the controls in §9g. **Convert a case
to the new layout before its first run**: §9a is what both runs are judged
against, so it has to exist and be reviewed first.

If §9 cannot be executed as written, that is itself feedback — record it as a
runbook defect (below) rather than improvising a different experiment, because
a substituted workload no longer tests the traced path.

## The two-run protocol

### Before run 1

1. **Freeze the prediction.** Record the case file's commit in the results
   file. §9a is now fixed: neither run edits it. If §9a turns out to be wrong,
   that is a dated stage-3 amendment to the case file, and both runs start
   again.
2. **Commit the instruments.** Any code a run needs that is not upstream — a
   restored test class, a Byteman rule — goes under `harness/<case-file-stem>/`
   in this folder before run 1, and both runs use those same files. Share
   instruments, not procedure: run 2 follows the runbook by hand.
3. **Agree what "agree" means.** Fill the results file's agreement table: for
   each observable, whether the runs must match exactly (a unit test's
   pass/fail, an exact ceiling) or in shape (a peak that follows the knob), and
   with what tolerance. Jingsong approves it before run 1.

### Run 1 — AI session

- **Scripted and logged.** Every step runs from a script that logs each command
  and its output (`script`, `tee`); the log is the evidence. Long steps run in
  the background and their logs are read, not guessed.
- **Stops at the first step it cannot run as written.** It records a runbook
  defect — the step, the problem, a proposed fix — and waits. Once Jingsong
  approves, the fix is made in the case file (dated) and the affected tier
  restarts from its beginning.
- **Concludes in the fixed format** of the results template: validity,
  readings, matched row, excluded rows, observed vs. inferred, deviations and
  gaps. Every statement cites a raw file.

### Run 2 — Jingsong

- Same case-file commit and harness, following §9b–§9e by hand.
- **Blind:** the readings, and the §9a row they match, are recorded before
  run 1's readings and conclusion are opened. The template keeps those folded.
- Then run 1's conclusion is checked, part by part.

### Compare and decide

| Situation | Action |
|---|---|
| Same §9a row, readings within the agreed tolerance | Verdict: that row. |
| Readings differ beyond tolerance | Find the cause (environment, a deviation, an instrument) and re-run the affected tier. No verdict until they agree. |
| Readings agree, conclusions differ | A reasoning error. Settle it against §9a's table, and record which conclusion was wrong and why. |
| No §9a row fits | Feedback to stage 3: the prediction missed an outcome. Amend §9a (dated); both runs repeat. |

## Running safely on shared infrastructure

| Rule | Why |
|---|---|
| **Never build in, or add files to, the shared `cassandra-src` clone.** Clone it to local disk for each run: `git clone --branch cassandra-5.0.9 /proj/misconfiguration-PG0/git-repos/cassandra-src <local-dir>`. | Stage 3 reads that clone for line numbers. It already holds an untracked `HeapPoolTest.java` and a `build/` directory from earlier work. |
| **Never fill `/proj`.** Node data, commit log and hints go on local disk; a disk-limit case uses a local filesystem of fixed, known size. | `/proj/misconfiguration-PG0` is a shared NFS mount (95 GB). Filling it affects everyone, and its free space moves with other users' files. |
| Both runs use the same node type and the same kind of storage. | Flush and write timings depend on the disk. |
| Stop every process a run starts, and check none is left: `pgrep -f org.apache.cassandra.service.CassandraDaemon`. | A leftover node holds ports and memory and contaminates the next run. |
| Commit small text excerpts under `results/<case-file-stem>/run1/` and `run2/`; keep full logs outside the repo and record their path. | Keeps the repo small without losing the evidence. |

## Environment

Required by `build.xml` at the tag: **JDK 11** (the default) **or 17**, and
**Apache Ant 1.10 or later**. Record, for every run: the node, OS, JDK and Ant
versions, the local clone's commit, the case-file commit, and the harness
commit — the results template has the table.

**Setup steps are not written yet.** The machine used for stage-3 work on
2026-09-28 had no `java`, `jcmd` or `ant` on its PATH. During the first run,
write the steps that worked into `environment.md` here, so run 2 and later
cases use the same ones.

## What stage 4 produces, and where feedback lands

The split follows the repo's standing rule — **a verdict is filed by the stage
that judged it**, so measurements belong here, not in the case file.

| Feedback kind | Lands in |
|---|---|
| Both runs — environment, readings, the AI's conclusion and logic, the check of it, the comparison, and the verdict | a results file, `results/<case-file-stem>.md`, copied from [`_TEMPLATE.md`](_TEMPLATE.md) |
| A refutation of the traced path (a **Refuted** row of §9a) | **amends the case file** — the affected section, dated, citing the results file |
| A bypass confirmed at runtime (the bypass row of §9a) | amends the case's §8 ceiling claim and its Target-3 note; the numbers stay here |
| A runbook defect (a step cannot run as written) | the results file's defect log, plus a dated fix to the case's §9b–§9e, approved by Jingsong |
| A disagreement between the runs that cannot be resolved | the results file; the case stays unverified |

Every case file carries a **Stage-4 feedback** field in §10, reading "none yet"
until a run reports. That field is the index of this relationship; keep it
current, because a case whose §8 claim has been refuted at runtime but still
reads as settled prose is the worst outcome this pipeline can produce.

## Eleven designs queued, nothing run

As of 2026-09-28 **every filed case carries a §9 test design**, so stage 4 is
unblocked and waiting only on execution. Only `memtable_heap_space` is in the
new §9 layout. No results file exists yet and no harness is committed.

**Where to start: unit tiers first.** They test the two-run protocol cheaply
before any cluster run. Four cases are far cheaper than the rest because unit
scaffolding already reaches the check:

| Case | Why it is cheap |
|---|---|
| `memtable_heap_space` | Already in the new layout. Its unit tier is two `ant testsome` commands once `HeapPoolTest` is restored into `harness/` (see "Prior art" below). |
| `cdc_total_space` | `CommitLogSegmentManagerCDCTest` already has a capacity-sweep helper (`testWithCDCSpaceInMb`) plus tests for the write failure, both modes' segment flagging, steady disk usage and mode switching. Very little to write. |
| `MAX_HINT_BUFFERS` | Predicts an **exact** ceiling, `n × bufferSize` (96 MiB at defaults), not a trend — so it is the sharpest falsification in the set. `HintsBufferPoolTest.testBackpressure()` already proves the disallow branch via Byteman. Confirm Byteman resolves as a test dependency first. |
| `max_space_usable_for_compactions_in_percentage` | `DirectoriesTest`, `PartialCompactionsTest` and `CompactionsBytemanTest` between them cover the arithmetic, the injection point and all three disallow outcomes. |

**Two designs need a cluster before they say anything**, because their finding
is a default-mode gap rather than a limit:
`native_transport_receive_queue_capacity` (the whole experiment is a
comparison of `throw_on_overload` true vs. false — a single-mode run correctly
observes nothing) and `DataDirectory_getAvailableSpace` (the guard does not run
under the default partitioner, so the two arms need **separate clusters**).

**Prior art to recover first.** A unit test for the `memtable_heap_space` case,
`HeapPoolTest.java`, was written and run on pc80 in September 2026. It is not
upstream, and the copy in the shared `cassandra-src` clone is untracked, but
its **full source is in this repo's history**:
`git show e90423c^:cassandra/if-check-exp/memtable/memtable_heap_space-tryAllocate-limit.md`.
Restore it into `harness/memtable_heap_space-tryAllocate-limit/` — not into the
shared clone — to re-run it as the control (the case's §9). Earlier per-case
trigger notes are in `git show e7f9963:HANDOFF.md`.
