# [constraint] — verification solution  <!-- file: cases/[stem]--autonomous.md -->

<!-- Hadoop version of ../../stage3-ai-deep-read/_TEMPLATE-autonomous.md (2026-11-06): same headings;
     tag, permalinks, configuration and build wording changed for Hadoop 3.4.2. -->

| Field | Value |
|---|---|
| Entry pointer | the if statement, as given, **linked**: [`File.java:123`](https://github.com/apache/hadoop/blob/rel/release-3.4.2/hadoop-common-project/hadoop-common/src/main/java/org/apache/hadoop/path/File.java#L123); for a helper unit, also name the helper method |
| Pinned source | `rel/release-3.4.2` |
| Session / date | agent, date (filled by the agent; no model name) |
| Estimate | `positive` (usage follows the constraint) / `negative` (it does not) / `undetermined`, with the reason in one or two sentences |
| Ground | for a negative estimate, why usage should not follow the constraint; otherwise `—` |

> **Link rule.** Two places must be links, not plain `file:line`: **the constraint's
> declaration** (A1) and **the if statement** (the check; the Entry pointer row above and
> A3). Use a permalink at the pinned tag,
> `[`File.java:123`](https://github.com/apache/hadoop/blob/rel/release-3.4.2/<full path under the repository root>#L123)`
> (a range is `#L123-L130`). Check that the line number is the line you mean. Other citations may
> stay plain `file:line`.

## A. Constraint trace

**A1. The constraint.** Name (for a configuration key, the exact key, including any placeholder
such as `<queue-path>`); kind (configuration key, JVM property, constant, runtime-queried); where it
is first declared (**link** to the declaration line, see the link rule above) and, for a key, its
`*-default.xml` entry; unit; default and how the default is derived (say which wins if the Java
constant and the `*-default.xml` value differ); how it can be set (which `*-site.xml` or
`capacity-scheduler.xml`, `-D` option, per-job configuration, admin refresh command, not settable)
and whether a change needs a daemon restart; which daemon or process reads it.

**A2. What it caps.** The resource (daemon heap, off-heap, container memory, disk on which volume
or directory, other) and the quantity the code compares against the limit.

**A3. Mechanism.** How the code enforces it, step by step, with `file:line`; the
**if statement is a link** (link rule above).
What each outcome of the check does when the limit is reached. Any path that
bypasses it or overshoots it.

**A4. Other consumers.** What else uses the same resource outside this
constraint's control.

**A5. Evidence beyond the source.** Docs, JIRA issues, tests, history relied on, with
links; `none` if none.

## B. Verification solution

**B1. Claim under test.** One or two falsifiable sentences, shared by both tiers.
For a negative estimate, the claim is that usage does not follow the constraint.

### B2. Unit tier

Drive the relevant classes directly in one JVM (in-JVM test infrastructure such as `MockRM`,
`MiniDFSCluster`, `MiniYARNCluster` is allowed); measure the check's own operand. Write
`n/a: <reason>` and an alternative if this tier cannot be done.

**B2a. Environment and build.** JDK, Maven module and build commands, test source location, JVM
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
observation that would show the claim wrong. For a negative estimate the table
also needs: usage follows the knob (claim refuted); usage flat while the positive control
moves (claim confirmed); the limit never reached or the control did not move (not confirmed).

**B2h. Controls.** What rules out other explanations.

### B3. Cluster tier

Real daemons from a distribution built from the tag (pseudo-distributed or two to three hosts),
with the configuration at the boundary; measure the actual resource. Write `n/a: <reason>` and an
alternative if this tier cannot be done.

**B3a. Environment and build.** Hosts, daemons and their roles, JVM options (`HADOOP_HEAPSIZE_MAX`,
`*_OPTS`), configuration files and changes, data and log directories (local disk, sizes), build
commands.

**B3b. Knobs.** Which to vary, the values and why those, how each is set (file, restart or refresh).

**B3c. Workload.** What drives usage to the limit and past it; sizes and the arithmetic showing the
limit is reachable; duration.

**B3d. Observables and instruments.** What is measured, with what tool (`jcmd`/`jstat`/NMT, JMX or
`/jmx` servlet metrics, `/proc/<pid>/status`, `du`/`df`, NodeManager container metrics, RM/NN web UI
or REST), sampled how; and what cannot be observed directly.

**B3e. Procedure.** Ordered steps with commands.

**B3f. Predictions.** Per knob value, in numbers or a clear relation, stated
before any run.

**B3g. Readings.** A table of observation → what it would mean, including the
observation that would show the claim wrong. For a negative estimate, same extra
rows as B2g, with a positive control: the same workload shown to move usage where a cap is known to bind.

**B3h. Controls.** What rules out other explanations.

**B4. Risks and cleanup.** For both tiers: disk, shared storage, ports, leftover daemons and
processes (`jps`), how to clean up.

## C. Sources read

Every file and URL read, one per line.

## D. Stage-4 feedback

`none yet` until stage 4 reports. Then: a link to its results file, and, if the
design audit amended anything above, which section was amended and when (dated
amendments). Measured numbers stay in the results file.
