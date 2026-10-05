# Brief

You are helping verify a claim about **Apache Cassandra 5.0.9**.

## The goal

Cassandra has resource constraints — configuration entries, JVM system
properties, constants, or limits queried at runtime — whose job is to cap how
much **memory or disk** a node uses. Starting from the code location given at
the end of this brief, work out:

1. **Which constraint is involved**, tracing it back to where it is first
   declared, and what it caps.
2. **How to verify, by running Cassandra, whether that constraint really caps
   the resource usage.** Design a verification solution that a separate engineer
   or AI session can execute without re-deriving the code path. It has **two
   tiers**, each a complete procedure of its own (see the next section).

## The two tiers

- **Unit tier.** Drive the relevant Cassandra classes directly, in a JVM
  started from a test or a small program built from the tree: no cluster, no
  running node. It measures the check's own usage-side value (the quantity the
  code compares against the limit), so it shows whether the mechanism works as
  you traced it.
- **Cluster tier.** A real node (or a small cluster) with the configuration
  pushed to the boundary and a workload driven through the normal client path.
  It measures the **actual resource** (heap, off-heap or disk), so it shows
  whether the limit governs what the node really uses.

Each tier gets its own setup, knobs, workload, instruments, procedure,
predictions, readings table and controls. If a tier cannot be done for this
constraint (for example the limit cannot be set at all, or nothing can be
driven without a node), write `n/a: <reason>` for that tier and say what you
would do instead to answer the same question.

## Sources

- The Cassandra source tree at tag `cassandra-5.0.9`, which is your working
  directory: code, configuration files, docs, tests and git history.
- Public documentation you find useful: the JDK and library documentation,
  Cassandra's issue tracker and docs. Cite anything you rely on.

Read nothing else. Do not look for, open or search any other repository,
notes, earlier analyses or results about this task, even if you can reach them.

## How to work

There is no prescribed method. Decide for yourself what to read, what the
constraint is, how the code enforces it, what to measure and how. Support every
claim about the code with `file:line` in the pinned tree. Treat the code
location you were given as a starting point only: it may not be the constraint's
main enforcement point, or may not constrain memory or disk at all. State the
claim your solution tests, whatever it turns out to be, including "this does
not cap usage" if that is what you find.

## What the solution must satisfy

These are practical limits, not a method:

- **Design only.** Do not build or run Cassandra, and do not quote measured
  numbers from anywhere; a solution describes what to run and what should be
  seen.
- **Target environment:** a Linux node, or a small cluster of two to three,
  with JDK 11 and Ant, building Cassandra from a local clone of the tag. No
  production data, and no change outside the nodes.
- **Executable from the solution alone:** exact knob names, values, commands,
  workload sizes, instruments and sampling.
- **Predictions are stated before any run**, per tier, as numbers or a clear
  relation, so a reading can contradict them; say what would show the claim is
  wrong.
- **Shared-machine care:** never build in or add files to the shared source
  clone (clone it to local disk); never fill shared storage (node data, commit
  log and hints go on local disk of known size); stop every process the run
  starts and check none is left.

## Output

Fill in the skeleton that follows this brief. Keep its section headings. Write
`n/a: <reason>` rather than leaving a section empty. You may add sections.
