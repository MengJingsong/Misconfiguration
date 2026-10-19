# [constraint] — verification solution  <!-- file: cases/[stem]--autonomous.md -->

| Field | Value |
|---|---|
| Entry pointer | `file:line` as given |
| Pinned source | `cassandra-5.0.9` |
| Session / date | model, CLI version, date (filled by the agent) |
| Judgment | `qualifies` / `does not cap` / `unsure`, with the reason in one or two sentences |

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

**B1. Claim under test.** One or two falsifiable sentences, shared by both tiers.
For a `does not cap` judgment, the claim is that usage does not follow the constraint.

### B2. Unit tier

Drive the relevant classes directly; measure the check's own operand. Write
`n/a: <reason>` and an alternative if this tier cannot be done.

**B2a. Environment and build.** JDK, build commands, test source location, JVM
options.

**B2b. Knobs.** Which value to vary, the values and why those, how each is set.

**B2c. Workload.** What drives the operand to the limit and past it; sizes and
the arithmetic showing the limit is reached.

**B2d. Observables and instruments.** What is measured, with what, sampled how;
and what cannot be observed directly.

**B2e. Procedure.** Ordered steps with commands.

**B2f. Predictions.** Per knob value, in numbers or a clear relation, stated
before any run.

**B2g. Readings.** A table of observation → what it would mean, including the
observation that would show the claim wrong. For a `does not cap` judgment the table
also needs: usage follows the knob (claim refuted); usage flat while the positive control
moves (claim confirmed); the limit never reached or the control did not move (not confirmed).

**B2h. Controls.** What rules out other explanations.

### B3. Cluster tier

A real node (or small cluster) with the configuration at the boundary; measure
the actual resource. Write `n/a: <reason>` and an alternative if this tier
cannot be done.

**B3a. Environment and build.** Nodes, JVM options, configuration changes, build
commands.

**B3b. Knobs.** Which to vary, the values and why those, how each is set.

**B3c. Workload.** What drives usage to the limit and past it; sizes and the
arithmetic showing the limit is reachable; duration.

**B3d. Observables and instruments.** What is measured, with what tool, sampled
how; and what cannot be observed directly.

**B3e. Procedure.** Ordered steps with commands.

**B3f. Predictions.** Per knob value, in numbers or a clear relation, stated
before any run.

**B3g. Readings.** A table of observation → what it would mean, including the
observation that would show the claim wrong. For a `does not cap` judgment, same extra
rows as B2g, with a positive control: the same workload shown to move usage where a cap is known to bind.

**B3h. Controls.** What rules out other explanations.

**B4. Risks and cleanup.** For both tiers: disk, shared storage, leftover
processes, how to clean up.

## C. Sources read

Every file and URL read, one per line.

## D. Stage-4 feedback

`none yet` until stage 4 reports. Then: a link to its results file, and, if the
design audit amended anything above, which section was amended and when (dated
amendments, as in a guided case's §10). Measured numbers stay in the results file.
