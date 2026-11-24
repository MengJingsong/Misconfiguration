# Rules for work under `experiments/`

## Keep the flowchart current (rule, 2026-11-17, owner)

[`FLOWCHART.md`](FLOWCHART.md) is the map of what `capacity-enforcement-exp` (phase 1) and `OOM-exp`
(phase 2) do and how they hand work to each other. **Whenever a change under `experiments/` modifies
functionality or design**, update `FLOWCHART.md` in the same commit so it matches:

- **Counts as a functionality or design change:** a step, stage, agent, playbook, template section, mode
  or option added, removed, renamed or rerouted; a list or table that one step writes and another reads
  (lead lists, queues, link tables, indexes); a status vocabulary; who decides or who queues; a hand-off
  between the experiments; a lead source.
- **Does not count:** new case files, results, run logs, queue rows, lead rows, status changes of single
  items, typo or wording fixes that leave the method the same.
- **What to update:** the affected rows in sections 2–4, the Mermaid chart in section 5 (nodes and arrows;
  **step names only** in chart nodes, descriptions go in sections 2–4), and one dated line in the change
  log (section 6). If nothing in the page needs to change, say so in the commit message.
- After editing the chart, check that it still parses (every node ID defined once, labels quoted,
  no `<`/`>` in labels, arrows use `-->`, `-.->` or `-->|label|`).

## Keep the flowchart's numbers current (rule, 2026-11-23, owner)

`FLOWCHART.md` shows result numbers as Mermaid arrow labels and in its results snapshot (section 5.1). When a commit
under `experiments/` changes a counted result (a batch's verdicts, stage-3/4/5 counts, candidate or retry-list status
counts, stage-3-a/3-b labels), refresh the affected arrow labels and the 5.1 table in the same commit, with the
"as of" date. Number refreshes need no change-log line. Recompute from the data files, not from READMEs.
