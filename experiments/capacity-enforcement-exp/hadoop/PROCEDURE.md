# Hadoop capacity-enforcement-exp — stage 3 and 4 procedure (per person)

Two people, two disjoint queues, one method. Created 2026-11-06.

| | Queue | Units |
|---|---|---|
| **Jingsong** | [`stage3-ai-deep-read/jingsong/queue.csv`](stage3-ai-deep-read/jingsong/queue.csv), bands A, B, C in that order | 749 |
| **Yang** | [`stage3-ai-deep-read/yang/queue.csv`](stage3-ai-deep-read/yang/queue.csv), band D, ordered by the triage rule below | 8,935 |

Each person writes only in their own `stage3-ai-deep-read/<name>/` and `stage4-runtime-verification/<name>/`.
Source: `systems/hadoop/source/` (`rel/release-3.4.2`). Method docs: `../stage3-ai-deep-read/`,
`../stage4-runtime-verification/`. Cassandra paths in older handoff text do not apply here.
**Stage 3 autonomous agent (Hadoop, shared by both people, 2026-11-06):**
[`stage3-ai-deep-read/playbook-autonomous.md`](stage3-ai-deep-read/playbook-autonomous.md) and
[`stage3-ai-deep-read/_TEMPLATE-autonomous.md`](stage3-ai-deep-read/_TEMPLATE-autonomous.md): the
Cassandra method docs with the system-specific parts (tag, permalinks, configuration keys, JDK 8 +
Maven build, daemons, naming of keys with hyphens/placeholders) rewritten for Hadoop.

## "Start the next batch of N" (what the AI does)

1. Read `queue.csv`; take the next **N** units with the first status column empty (Jingsong: `case_file`,
   skipping `anchor=yes` rows; Yang: `recheck`, tiers 1, 2, then 3-sample, in `order`). If the next
   rows are not N, say so. Never skip or reorder rows.
2. **Source copy outside the repo** (so agents cannot read other cases):
   `rsync -a systems/hadoop/source/ ~/hadoop-3.4.2/` (once).
3. **Stage 3, one fresh agent per unit**, working in that copy, one at a time or in parallel:
   - *Jingsong's units:* give the agent the **Hadoop** `stage3-ai-deep-read/playbook-autonomous.md`,
     `stage3-ai-deep-read/_TEMPLATE-autonomous.md` (copied outside the repo) and the
     target as `file:line` only (a helper unit: the helper method and its comparison line, found with
     `grep -n`). Output `cases/<stem>--autonomous.md`; stem `<constraint>-<method>-<operand>`,
     `-2` if taken. Add the `_INDEX.md` row and sha256, fill `case_file` and `estimate`.
   - *Yang's units (recheck):* give the agent only the target `file:line` and this question: "Does
     this comparison bound or guard memory, disk, a queue, a buffer or another resource? Re-read
     the source and answer `D` (confirmed, no bound) or `A`/`B`/`C` (promote), with a one-line
     reason." No stage-2 reason, no score. Record the answer in `recheck` (`D` or the band) and
     the reason in `recheck_note` if you add the column. **A promoted unit then gets the
     Jingsong procedure above** (autonomous case file); fill `promoted_band`, `case_file`.
4. Stage 3 never changes `bands.csv` (stage 2's record). A promotion is recorded in the queue only.
5. **Stage 4** for each case file written in this batch, per
   `../stage4-runtime-verification/README.md` ("The run protocol"): audit, frozen predictions,
   harness, run 1 at both tiers, results file, outcome class. One fresh agent per case, using that
   person's `stage4-runtime-verification/<name>/environment.md`; it writes only that person's folders,
   keeps run data on local disk and leaves no Hadoop process running. **Needs that person's
   environment** (see below): if it is not there, stop after stage 3 and say stage 4 is waiting.
6. Report: units processed, case files created, promotions (Yang), stage 4 status, what is next.
   Then **commit and push to `main` automatically** (only this work's files; `git pull --rebase
   --autostash origin main` first) and report the commit hash.

## "Summarize the result status" (what the AI does)

Run `experiments/capacity-enforcement-exp/hadoop/status.py <name>` and report its output verbatim, then
add: the latest case files and promotions since the last commit (`git log`), anything blocked,
and the next queue position. Numbers come from the queue CSV and the folders, not from memory.
Example (Yang, nothing done yet):

```
yang: 8935 units in queue
  tier 1             223  rechecked     0  promoted    0
  tier 2            1019  rechecked     0  promoted    0
  tier 3-reserve    7308  rechecked     0  promoted    0
  tier 3-sample      385  rechecked     0  promoted    0
  next unrechecked order: 1
case files: 0  (cases/ has 0 files)
stage 4: outcome classes {}  results/ has 0
```

## Yang's band-D triage rule (proposed 2026-11-06)

Band D is "no resource-bound semantics"; reading 8,935 as cases is not feasible, and most are
correctly D. So Yang's job is a **second, independent reading of D to find stage-2 misses**,
prioritised by how likely a unit is to be a miss.

- **Score** (`make-d-queue.py`, deterministic, heuristic only): +3..4 for resource words in the
  operands or method (max, limit, capacity, quota, threshold, bytes, buffer, memory, queue, pending,
  retention...), +1..2 for weaker ones (size, length, count, total, remaining...), +1 magnitude
  operator, +1 right side not a literal, +2 config operand, −2 for id/version/time/index words with
  no resource word, +1 helper. Tier 1 = score ≥ 6, tier 2 = 4–5, tier 3 = the rest.
- **Order:** tier 1 (223), tier 2 (1,019), then a fixed random **5% sample of tier 3** (385, seed in
  the script). The remaining 7,308 tier-3 units are `3-reserve`: not read unless triggered.
- **Stop / extend rule:** read tiers 1 and 2 fully. Read the tier-3 sample. If the sample promotes
  **≥ 1%** (4 or more units), pull the next 1,000 reserve units in `order` and repeat the test on
  that chunk; if under 1%, stop and report the miss rate with the unread count. Record each decision
  in `HANDOFF-Yang.md`.
- **Report the miss rate** per tier (promoted / read). It is the evidence for how reliable the D band
  is, whatever the case results are. The 98.9% stage-2 agreement and the 40-row spot check are the
  prior.
- Nothing is dropped or promoted because of the score; only the reading order depends on it.

## Hadoop stage 4 environment and harness

Per person, written by an AI session **with a human supplying the nodes**.

| Person | Environment | State |
|---|---|---|
| **Yang** | [`stage4-runtime-verification/yang/environment.md`](stage4-runtime-verification/yang/environment.md), [`copy-source.sh`](stage4-runtime-verification/yang/copy-source.sh), [`case-notes.md`](stage4-runtime-verification/yang/case-notes.md) | **Ready** (2026-11-06): local node `node0.jason92-323989`, JDK 8 + Maven, built distribution in `/mydata/yang-s4/hadoop-base`. First case closed (true negative). |
| **Jingsong** | [`stage4-runtime-verification/jingsong/environment.md`](stage4-runtime-verification/jingsong/environment.md), [`setup-node.sh`](stage4-runtime-verification/jingsong/setup-node.sh), [`copy-source.sh`](stage4-runtime-verification/jingsong/copy-source.sh), [`case-notes.md`](stage4-runtime-verification/jingsong/case-notes.md) | **Ready** (2026-11-06): nodes `pc41` (shared with Yang), `pc39`, `pc29`; JDK 8 + Maven, built distribution in `/mydata/jingsong-s4/hadoop-base` on each. Batch 1 (orders 1–5) closed. |

A per-case harness goes in `stage4-runtime-verification/<name>/harness/<stem>/`; the stage-4 protocol is
[`../stage4-runtime-verification/README.md`](../stage4-runtime-verification/README.md), results from its `_TEMPLATE.md`.
