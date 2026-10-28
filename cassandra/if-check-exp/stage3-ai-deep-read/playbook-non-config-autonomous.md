# Stage 3 non-config autonomous-agent playbook

**This is the non-config autonomous agent's whole instruction.** It gets one target and
nothing else: no rules, no patterns, no design method beyond this file. It is the
[autonomous playbook](playbook-autonomous.md) plus a **type check**: after tracing the
constraint, the agent skips a config-type constraint and writes up only a non-config one.
**Do not access, open or read the guided agent's playbook (`playbook-guided.md`).** Both
agents fill a template, and [stage 4](../stage4-runtime-verification/README.md) runs
whatever solution a case file holds; what stage 3 is, and where results are filed, is in
[`README.md`](README.md).

**How to run it.** One fresh Agent-tool subagent per target, in a copy of the Cassandra
source at tag `cassandra-5.0.9` made **outside this repository**
(`rsync -a cassandra/cassandra-5.0.9/ ~/cassandra-5.0.9/`), so the session cannot read the
other case and results files. Give it this file, `_TEMPLATE-autonomous.md`, and the target
as a code location (`file:line`, relative to the source root). Nothing else about the case.
**The agent writes only to a scratch file it is given. It never edits `_INDEX.md`, the CSVs
or `cases/`; the lead files its output.**

You are helping verify a claim about **Apache Cassandra 5.0.9**.

## The goal

Cassandra has resource constraints (configuration entries, JVM system properties,
constants, or limits queried at runtime) whose job is to cap how much **memory or disk** a
node uses. Starting from the code location you were given as the target:

1. **Trace the constraint back** to where it is first declared, and say what it caps.
2. **Classify it: config-type or non-config type** (next section).
3. **If it is config-type, stop** and return a skip record (below). Do no design work.
4. **If it is non-config type, write the case file**: the estimate, and a verification
   solution that a separate engineer or AI session can execute without re-deriving the
   code path, as the [autonomous playbook](playbook-autonomous.md) describes (two tiers,
   unless the rule for "no constraint" below applies).

## Config-type and non-config type

Classify by where the **value the check compares against** comes from.

- **Config-type:** a yaml entry (`cassandra.yaml`) or a JVM property (`-D`, for example a
  `CassandraRelevantProperties` constant); an operator can set it without changing code.
- **Non-config type:** everything else: a per-table or per-index option, a hard-coded
  constant, a runtime-queried value, a query parameter (CQL `LIMIT` and the like), or **no
  constraint**.

**Constant rule (decided 2026-10-27).** If a constant is involved in the constraint in any
way, the row is **non-config type** and is written up, even when the same check also reads
a yaml entry or a JVM property (for example `x < Math.min(DatabaseDescriptor.getFoo(),
MAX_CONSTANT)`). Say which constant, with a link to its declaration, in A1. A row is
config-type only when the compared value comes **only** from a yaml entry or a JVM
property and no constant takes part.

## Skip record (config-type only)

Return exactly this, and nothing else, as your output:

```
SKIP | <target file:line> | <constraint name> | <yaml entry | JVM property> | <declaration file:line> | <one sentence: why the value comes only from config>
```

Check twice before you skip: read the declaration and every place the compared value is
computed. If any constant takes part, it is not a skip (constant rule).

## A row with no constraint

Some targets have no resource constraint: the check is bookkeeping, a format or
validation test, loop control or an ordering test. The estimate is **`negative`** and no
two-tier verification is needed. Instead the case file must carry a **clear explanation
backed by evidence**:

- **A1** says `no constraint` and names the compared operands, each with its declaration or
  origin (`file:line`, linked per the link rule).
- **A3** gives the enclosing method, what both outcomes of the check do, and who calls it,
  all with `file:line`.
- **A2** says which memory or disk object, if any, the check could bound, and why it
  bounds none (for example it validates a name length that is then stored in a few bytes,
  or it picks an iteration branch and bounds nothing held).
- **A4/A5** record what you searched for (callers, config keys, tests, docs, history) and
  found, so a reader can see the claim "no constraint" was checked rather than assumed.
- **B1** states the claim: this check does not cap memory or disk usage.
- **B2 and B3** read `n/a: no constraint, <reason>` with what evidence in A answers the
  question instead. Never leave a section empty.

A constraint that exists but is not a memory or disk cap (for example a count limit on a
bytes-insignificant object) is **not** this case: write it up in full, with the two tiers,
and a negative estimate and its ground.

## The two tiers (a non-config row that has a constraint)

- **Unit tier.** Drive the relevant Cassandra classes directly, in a JVM started from a
  test or a small program built from the tree: no cluster, no running node. It measures
  the check's own usage-side value (the quantity the code compares against the limit).
- **Cluster tier.** A real node (or a small cluster) with the constraint pushed to the
  boundary and a workload driven through the normal client path. It measures the **actual
  resource** (heap, off-heap or disk).

A constant or type bound usually cannot be varied. Say so, and design two arms that differ
in one condition (for example a patched-literal build, as earlier cases did), or write
`n/a: <reason>` for the tier with what answers the same question instead. A per-table or
per-index option is varied through its CQL option. A query parameter is varied through the
client call.

Each tier gets its own setup, knobs, workload, instruments, procedure, predictions,
readings table and controls, as in the template.

## Sources

- The Cassandra source tree at tag `cassandra-5.0.9`, your working directory: code,
  configuration files, docs, tests and git history.
- Public documentation you find useful (JDK and library documentation, Cassandra's issue
  tracker and docs). Cite anything you rely on.

## How to work

There is no prescribed method beyond the steps above. Support every claim about the code
with `file:line` in the pinned tree. Treat the code location you were given as a starting
point only: it may not be the constraint's main enforcement point, or may not constrain
memory or disk at all.

**A helper target.** If the target is a boolean helper method (given as its definition
line, not as a call site), trace the check **inside the helper** and treat the helper's own
comparison as the target. Note in A3 which call sites you read (a list is enough). A helper
is given by its qualified name (an anonymous class or an overload may not name one method).
If the name matches no method, or several methods with different bodies and you cannot tell
which is meant, return `UNRESOLVED | <helper name> | <what you found>` and do no more; the
lead decides. If several overloads share one logic, trace them together and say so.

**Estimate the line.** Say in the template's Estimate field whether usage follows the
constraint: `positive` (the constraint caps memory or disk), `negative` (you traced it and
it does not, or it does not bound a memory- or disk-significant object, or there is no
constraint), or `undetermined`. Give the reason, and for a negative the ground. For a
negative estimate with a constraint, the solution tests the opposite claim (usage does not
follow the constraint) and includes a positive control, as in the template's B2g and B3g
notes.

## What the solution must satisfy

- **Design only.** Do not build or run Cassandra, and do not quote measured numbers from
  anywhere; a solution describes what to run and what should be seen.
- **Target environment:** a Linux node, or a small cluster of two to three, with JDK 11 and
  Ant, building Cassandra from a local copy of the tag. No production data, and no change
  outside the nodes.
- **Executable from the solution alone:** exact knob names, values, commands, workload
  sizes, instruments and sampling.
- **Predictions are stated before any run**, per tier, as numbers or a clear relation.
- **Shared-machine care:** never build in or add files to the shared source tree; never
  fill shared storage; stop every process the run starts and check none is left.

## Output

Either the skip record, or the filled
[`_TEMPLATE-autonomous.md`](_TEMPLATE-autonomous.md), keeping its section headings, written
to the scratch file you are given. Add one line under the field table:
`**Type:** non-config (<per-table/per-index option | hard-coded constant | runtime-queried | query parameter | none>)`,
and, when the constant rule applied to a check that also reads a yaml entry or JVM
property, name both. The lead saves the file as `cases/<stem>--autonomous.md`, where
`<stem>` is `[constraint]-[function]-[operand]` ([`../README.md` §6.1](../README.md#61-naming)),
with `-2` added when the stem is taken, and adds its `_INDEX.md` row and sha256.
