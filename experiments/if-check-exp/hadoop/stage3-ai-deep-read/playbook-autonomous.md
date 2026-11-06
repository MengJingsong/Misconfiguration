# Stage 3 autonomous-agent playbook — Hadoop

> **What this is.** The Hadoop version of the shared method doc
> [`../../stage3-ai-deep-read/playbook-autonomous.md`](../../stage3-ai-deep-read/playbook-autonomous.md)
> (written for Cassandra). Same method, same output format; only the system-specific parts
> (version, tag, permalinks, configuration, build, environment, naming) are changed. Written
> 2026-11-06 for both Hadoop shares (Jingsong A/B/C, Yang D promotions); see
> [`../PROCEDURE.md`](../PROCEDURE.md). Template: [`_TEMPLATE-autonomous.md`](_TEMPLATE-autonomous.md)
> in this folder. Per-person output (`cases/`, `_INDEX.md`) lives in `jingsong/` or `yang/` here.

**This is the autonomous agent's whole instruction.** It gets the target and nothing
else: no rules, no patterns, no design method, no stage-2 band or reason.
**Do not access, open or read any guided playbook (`playbook-guided.md`).** The agent fills the
template, and [stage 4](../../stage4-runtime-verification/README.md) runs whatever solution the
case file holds.

**How to run it.** Make a copy of the Hadoop source at tag `rel/release-3.4.2` **outside this
repository**, once per machine: `rsync -a systems/hadoop/source/ ~/hadoop-3.4.2/`, so the agent
cannot read other case and results files. Start a fresh agent with its working directory in that
copy. Give it this file, `_TEMPLATE-autonomous.md` (both may be copied next to it, outside the
repository) and the target as a code location (`file:line`, relative to the source root). For a
helper unit, the target is the comparison line inside the helper method (found with `grep -n`).
Nothing else about the case. Tell it where to write the output file (outside the repository); the
session that started it files the result.

You are helping verify a claim about **Apache Hadoop 3.4.2**.

## The goal

Hadoop has resource constraints — configuration keys, JVM system properties, constants, or
limits queried at runtime — whose job is to cap how much **memory or disk** is used. In Hadoop
that covers both what a daemon (NameNode, DataNode, ResourceManager, NodeManager, JobHistory
server, a client or a task JVM) holds itself — heap, off-heap, local disk, logs — and what Hadoop
hands out or stores on a host on others' behalf: memory allocated to YARN containers, HDFS block
storage on DataNode volumes, NodeManager local and log directories. Starting from the code location
you were given as the target, work out:

1. **Which constraint is involved**, tracing it back to where it is first declared, and what it
   caps.
2. **How to verify, by running Hadoop, whether that constraint really caps the resource usage.**
   Design a verification solution that a separate engineer or AI session can execute without
   re-deriving the code path. It has **two tiers**, each a complete procedure of its own (see the
   next section).

If the constraint caps some other resource (vcores, a count of objects with no memory/disk
significance, a logical scheduler share that does not translate into memory or disk, threads,
connections, time), say so plainly and estimate accordingly (see "Estimate the line").

## The two tiers

- **Unit tier.** Drive the relevant Hadoop classes directly in one JVM, from a JUnit test or a
  small program built from a local copy of the tree: no Hadoop daemon process started from a
  distribution. Hadoop's in-JVM test infrastructure is allowed here (for example `MockRM`/`MockNM`,
  `MiniDFSCluster`, `MiniYARNCluster`, `MiniMRYarnCluster`), as long as it runs inside the test JVM.
  It measures the check's own usage-side value (the quantity the code compares against the limit),
  so it shows whether the mechanism works as you traced it.
- **Cluster tier.** Real Hadoop daemons started from a distribution built from the tag
  (pseudo-distributed on one host, or a small cluster of two to three), with the configuration
  pushed to the boundary and a workload driven through the normal client path (`hdfs dfs`,
  `yarn jar`, MapReduce examples, distributed shell, the REST/RPC clients). It measures the
  **actual resource** (daemon heap or off-heap, container resident memory, bytes on disk), so it
  shows whether the limit governs what is really used.

Each tier gets its own setup, knobs, workload, instruments, procedure, predictions, readings table
and controls. If a tier cannot be done for this constraint (for example the limit cannot be set at
all, or nothing can be driven without a daemon), write `n/a: <reason>` for that tier and say what
you would do instead to answer the same question.

## Sources

- The Hadoop source tree at tag `rel/release-3.4.2` (commit `84e8b89`), which is your working
  directory: code, `*-default.xml` files, docs under `src/site/`, tests. (The copy may have no git
  history; do not rely on it.)
- Public documentation you find useful: the JDK and library documentation, the Hadoop 3.4.2 docs
  (`https://hadoop.apache.org/docs/r3.4.2/`), the Apache JIRA projects HADOOP, HDFS, YARN and
  MAPREDUCE (`https://issues.apache.org/jira/`). Cite anything you rely on.

Where Hadoop configuration lives, as a starting point only: keys and defaults are usually declared
as constants in classes such as `CommonConfigurationKeys(Public)`, `DFSConfigKeys`,
`HdfsClientConfigKeys`, `YarnConfiguration`, `MRJobConfig`/`MRConfig`, and
`CapacitySchedulerConfiguration`, with documented defaults in `core-default.xml`,
`hdfs-default.xml`, `yarn-default.xml` and `mapred-default.xml`. A constant's default and the
`*-default.xml` value can differ; when they do, say which one wins at runtime and why.

## How to work

There is no prescribed method. Decide for yourself what to read, what the constraint is, how the
code enforces it, what to measure and how. Support every claim about the code with `file:line` in
the pinned tree. Treat the code location you were given as a starting point only: it may not be the
constraint's main enforcement point, or may not constrain memory or disk at all. State the claim
your solution tests, whatever it turns out to be, including "this does not cap usage" if that is
what you find.

**Estimate the line.** Say in the template's Estimate field whether usage follows the constraint:
`positive` (the constraint caps memory or disk), `negative` (you traced it and it does not, or it
does not bound a memory- or disk-significant object), or `undetermined`. Give the reason, and for a
negative the ground. This is a prediction from the source; stage 4 confirms or refutes it. Either
way, design the verification solution in full: for a negative estimate, the solution tests the
opposite claim, that usage does **not** follow the constraint, so stage 4 can confirm or refute it.
Include a positive control: the same workload shown to move usage where a cap is known to bind (see
the template's B2g and B3g notes).

## What the solution must satisfy

These are practical limits, not a method:

- **Design only.** Do not build or run Hadoop, and do not quote measured numbers from anywhere; a
  solution describes what to run and what should be seen.
- **Target environment:** a Linux host, or a small cluster of two to three, building Hadoop from a
  local copy of the tag with **JDK 8 and Maven 3.3+** (`BUILDING.txt:4-8`; no native code needed
  unless the constraint lives in native code), running on JDK 8 or 11. A distribution comes from
  `mvn package -Pdist -DskipTests -Dtar -Dmaven.javadoc.skip=true` (`BUILDING.txt:364-368`); a unit
  test from `mvn -pl <module> -am install -DskipTests` then `mvn -pl <module> test -Dtest=<Class>#<method>`.
  No production data, no Kerberos unless the constraint needs it, and no change outside the hosts.
- **Executable from the solution alone:** exact configuration keys and the file each goes in
  (`core-site.xml`, `hdfs-site.xml`, `yarn-site.xml`, `mapred-site.xml`, `capacity-scheduler.xml`,
  or `-D` options), values, commands, workload sizes, instruments and sampling. Say whether a change
  needs a daemon restart or can be refreshed (`yarn rmadmin -refreshQueues`,
  `hdfs dfsadmin -reconfig`, ...).
- **Predictions are stated before any run**, per tier, as numbers or a clear relation, so a reading
  can contradict them; say what would show the claim is wrong.
- **Shared-machine care:** never build in or add files to the shared source tree (copy it to local
  disk first); point every data and log location (`hadoop.tmp.dir`, `dfs.namenode.name.dir`,
  `dfs.datanode.data.dir`, `yarn.nodemanager.local-dirs`, `yarn.nodemanager.log-dirs`,
  `HADOOP_LOG_DIR`) at local disk of known size, never at shared storage; keep container and daemon
  memory within what the host has; stop every daemon and process the run starts
  (`stop-yarn.sh`, `stop-dfs.sh`, `mapred --daemon stop historyserver`) and check with `jps` that
  none is left.

## Output

Fill in [`_TEMPLATE-autonomous.md`](_TEMPLATE-autonomous.md). Keep its section headings. Write
`n/a: <reason>` rather than leaving a section empty. You may add sections. Save it as
`<stem>--autonomous.md`, where `<stem>` is `[constraint]-[function]-[operand]`, named as follows.

### Naming

- `[constraint]` — the **resource constraint name**: the variable or key that is *first
  declared/initialized* along the path that sets the limit, verbatim:
  - **Configuration key** → the key string, e.g. `dfs.datanode.du.reserved`,
    `yarn.nodemanager.resource.memory-mb`. A key with a placeholder segment (`<queue-path>`,
    `<user>`, `%s`) is written with the placeholder's brackets or `%` dropped, e.g.
    `yarn.scheduler.capacity.queue-path.capacity` for `yarn.scheduler.capacity.<queue-path>.capacity`
    (characters such as `<>%*` are not portable in file names); give the exact key in A1.
  - **JVM system property** → the property's declaring variable.
  - **Constant / hard-coded variable** → the declaring variable's name, qualified with its class as
    `Class_NAME` only if the bare name is ambiguous.
  - **Runtime-queried limit with no declared variable** → the accessor that supplies it, as
    `Class_method`, e.g. `DF_getAvailable`.
  - **Derived from several sources** → the primary one (the one a user would tune); name the others
    in A1.
- `[function]` — the name of the method that directly encloses the if statement you were given (or
  the main enforcement point if you find a better one; say which), no class prefix, verbatim.
- `[operand]` — the limit-side operand's name exactly as written at that check.
- Join with hyphens: `[constraint]-[function]-[operand]--autonomous.md`. Keep each part's original
  casing. Hadoop keys can contain hyphens themselves (`memory-mb`), so the file name is not parsed
  back into parts; the parts are recorded in the case file.
- Collisions are handled when the file is filed, not by you: if the name is already taken in the
  person's `cases/`, the existing file keeps its name and the new one gets `-2` (then `-3`) before
  `--autonomous`.
