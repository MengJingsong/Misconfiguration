# Rules for work under `experiments/`

## Keep `FLOWCHART.md` current: design and result numbers (rule, owner; 2026-11-17, widened 2026-11-23)

[`FLOWCHART.md`](FLOWCHART.md) is the map of what `capacity-enforcement-exp` (phase 1) and `OOM-exp`
(phase 2) do, how they hand work to each other, and **what each step has produced so far**. It applies to **both
experiments and both systems** (Cassandra, Hadoop), whoever does the work (owner, Yang, Jingsong, any agent or
workflow). **Whenever a commit under `experiments/` changes the design or changes a result number, update
`FLOWCHART.md` in the same commit.**

**1. Design change** → update the affected rows in sections 2–4, the Mermaid chart in section 5 (nodes and arrows;
**step name** in each chart node, plus, where work is left at that step, one second line `left: …` after `<br/>` with the open count as Cassandra/Hadoop, taken from the 5.1 "+ left" terms and never an in-progress count (owner, 2026-11-24); descriptions go in sections 2–4), and add one dated line to the change log
(section 6).
- *Counts as a design change:* a step, stage, agent, playbook, template section, mode, option or rule added,
  removed, renamed or rerouted; a list or table that one step writes and another reads (lead lists, queues, link
  tables, indexes); a status or label vocabulary; who decides or who queues; a hand-off between the experiments; a
  lead source.
- *Does not count:* typo or wording fixes that leave the method the same.

**2. Result-number change** → refresh the affected arrow labels and box `left:` lines in the chart, the results snapshot (section 5.1) and the open work (section 5.2),
with the "as of" date. No change-log line is needed.
- *Counts:* anything the chart or 5.1 counts — new case files or verdicts at any stage (phase-1 stages 1–5, a
  Yang/Jingsong batch, a phase-2 wave, stage 3-a/3-b labels), stage-4 outcome classes, candidate or retry-list status
  counts, JIRA report or clue-pattern counts.
- *How:* recompute from the data files (`_INDEX.md`, set CSVs, `bands.csv`, `coverage.csv`, candidate and retry lists,
  `hadoop/status.py`), not from READMEs or handoffs. Arrow labels are written **Cassandra/Hadoop** (`–` = not
  started).

If nothing in the page needs to change, say so in the commit message. After editing the chart, check that it still
parses (every node ID defined once, labels quoted, no `<`/`>` in labels except the `<br/>` before a box's `left:` line, arrows use `-->`, `-.->` or `-->|label|`).
