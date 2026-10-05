# [constraint] — short-path solution  <!-- file: cases/[stem].md -->

| Field | Value |
|---|---|
| Entry pointer | `file:line` as given |
| Pinned source | `cassandra-5.0.9` |
| Session / date | |

## A. Constraint trace

**A1. The constraint.** Name; kind (configuration entry, JVM property, constant,
runtime-queried); where it is first declared (`file:line`); unit; default and
how the default is derived; how it can be set (yaml key, `-D` property, JMX,
not settable) and whether a change needs a restart.

**A2. What it caps.** The resource (heap, off-heap, disk, other) and the
quantity the code compares against the limit.

**A3. Mechanism.** How the code enforces it, step by step, with `file:line`.
What each outcome of the check does when the limit is reached. Any path that
bypasses it or overshoots it.

**A4. Other consumers.** What else uses the same resource outside this
constraint's control.

**A5. Evidence beyond the source.** Docs, issues, tests, history relied on, with
links; `none` if none.

## B. Verification solution

**B1. Claim under test.** One or two falsifiable sentences.

**B2. Environment and build.** Nodes, JVM options, configuration changes, build
commands.

**B3. Knobs.** Which to vary, the values and why those, how each is set.

**B4. Workload.** What drives usage to the limit and past it; sizes and the
arithmetic showing the limit is reachable; duration.

**B5. Observables and instruments.** What is measured, with what tool, sampled
how; and what cannot be observed directly.

**B6. Procedure.** Ordered steps with commands.

**B7. Predictions.** Per knob value, in numbers or a clear relation, stated
before any run.

**B8. Readings.** A table of observation → what it would mean, including the
observation that would show the claim wrong.

**B9. Controls.** What rules out other explanations.

**B10. Risks and cleanup.**

## C. Paths read

Every file and URL read, one per line, for the leakage audit.
