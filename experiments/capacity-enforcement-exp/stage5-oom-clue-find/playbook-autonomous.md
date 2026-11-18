# Stage 5 autonomous-agent playbook — OOM clue find

> **Paths.** System-agnostic. Per-system files are under
> `experiments/capacity-enforcement-exp/<system>/`. What stage 5 is: [`README.md`](README.md).

**This is the autonomous agent's whole instruction.** It gets one filed case file and nothing else
about OOM: no patterns, no examples, no JIRA reports. **Do not open `oom-clue-patterns.md`,
`playbook-guided.md`, any `jira-oom-*` file, anything under `experiments/OOM-exp/`, the candidate list,
or any other case file.**

**How to run it.** Start a fresh agent in a copy of the pinned source made **outside this repository**
(Cassandra: `rsync -a systems/cassandra/source/ ~/cassandra-5.0.9/`; Hadoop:
`rsync -a systems/hadoop/source/ ~/hadoop-3.4.2/`). Give it this file, a copy of one case file, and a
copy of that case's stage-4 results file if one exists. The session that started it files the output:
it gives each candidate the next `OC-<n>` ID in `<system>/stage5-oom-clue-find/phase1-oom-candidates.md`
(Agent `autonomous`, Patterns `—`, Status `open`) and adds a line to `coverage.csv`.

## The goal

The case file describes one resource constraint of the system — a configuration entry, JVM property,
constant or runtime-queried limit meant to cap memory or disk — how the code enforces it, and (when
stage 4 has run) what a real node did. Read it, then the code it cites, and answer:

**Is there anything here that could let the process run out of memory?** Memory that grows past what
this constraint, or anything else on the path, really bounds; a limit that does not stop the allocation;
anything else you judge could end in an out-of-memory failure at the shipped default settings under a
reachable workload.

## How to work

- Read the whole case file and its stage-4 results. **Skip** any section headed `## Recheck` and a
  guided file's `§8a` (they were written by a retired method and would steer you).
- Open every `file:line` the case cites for the constraint, its check and what happens at the limit, in
  the source tree, and follow the code as far as you need. Cite `file:line` for every claim.
- There is no prescribed method. Decide what to read and what matters.
- A clue needs code you can point to and a rough size at defaults (bytes per item × how many can be live
  at once, or a sum against a default budget). An overshoot by one item that another limit already caps
  is not a candidate.
- Do not design or run an OOM test, and do not change the case file.

## Output

Return only this:

```
Case file: <stem>
Candidates: <n>

| # | Clue (what holds the memory, why nothing stops it, rough size at defaults) | Where (file:line) |
|---|---|---|
| 1 | … | … |
```

or `Candidates: 0` with one sentence on why nothing was found.
