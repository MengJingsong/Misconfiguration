# Stage 4 — runtime verification

**The stage that runs the experiment.** Stage 3 reads the source and writes a
test design; stage 4 executes it on a real build or cluster, measures, and
reports back. The two are deliberately separate: stage 3's rule is that
everything it files is decidable from source alone, with no cluster, no build
and no run, and that rule survives only if execution lives elsewhere.

Reserved by decision on 2026-09-23 and **opened on 2026-09-25**, when test
design became part of stage 3 ([`../README.md` §8](../README.md#8-designing-a-test-for-a-case)).
Executed by Jingsong, not by an AI session.

## The division of labour

| | Stage 3 | Stage 4 |
|---|---|---|
| Evidence | the source, against the three rules | a measured run |
| Produces | a test design — §9 of each case file | numbers, and a verdict on the design's prediction |
| Records numbers? | **never** | yes, here |
| Needs a cluster/build? | no | yes |

## What stage 4 consumes

Section 9 of a case file in [`../stage3-ai-deep-read/cases/`](../stage3-ai-deep-read/cases/).
It is written to be self-contained: the knob and how to set it, at least three
capacity values, the usage-side observable and its instrument, the workload,
the just-reach and exceed scenarios, the predicted dose-response, an
interpretation table, what would refute the case, and the controls.

**Read §9's "Testability" field first.** A case marked *needs patched build* or
*not settable* is not worth a CloudLab allocation until someone patches the
build; a config-testable one can be run as written.

If §9 cannot be executed as written, that is itself feedback — say so rather
than improvising a different experiment, because a substituted workload no
longer tests the traced path.

## The shape of a run

Per case, per capacity value, in both scenarios:

1. Set the knob to the capacity value.
2. Run the baseline/idle control (§9g) so drift can be separated from effect.
3. Scenario A — bring usage to the limit without crossing. Record the observable.
4. Scenario B — cross the limit. Record the observable **and** the disallow
   effect §6b predicts (rejection count, parked threads, exception type).
5. Compare against §9d's predicted dose-response and classify with §9e.

Peak matters, not final: a disk observable sampled once after the fact has
already been erased by compaction.

## What stage 4 produces, and where feedback lands

The split follows the repo's standing rule — **a verdict is filed by the stage
that judged it**, so measurements belong here, not in the case file.

| Feedback kind | Lands in |
|---|---|
| Measurements — numbers, curves, the run's configuration and commands | a results file here, one per case |
| A refutation of the traced path (§9e row 3, or §9f's refuting observation) | **amends the case file** — the affected section, dated, citing the run here |
| A bypass confirmed at runtime (§9e row 2) | amends the case's §8 ceiling claim and its Target-3 note; the numbers stay here |
| "§9 could not be executed as written" | a note here, plus whatever §9 field needs correcting |

Every case file carries a **Stage-4 feedback** field in §10, reading "none yet"
until a run reports. That field is the index of this relationship; keep it
current, because a case whose §8 claim has been refuted at runtime but still
reads as settled prose is the worst outcome this pipeline can produce.

## Not yet built

No results file exists, no case is queued, and no harness is written. The prior
art is worth recovering before building one: a unit test for the
`memtable_heap_space` case, `HeapPoolTest.java`, was written and run on pc80 in
September 2026 and **is still present in the shared `cassandra-src` clone**;
its designed-trigger notes, and those for the other six filed cases, are in
`git show e7f9963:HANDOFF.md`.
