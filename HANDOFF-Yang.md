# If-Check Exp — Handoff for Yang (set B)

> **Paths.** This file is Cassandra `capacity-enforcement-exp` work. Paths starting `cassandra/stage…` are
> relative to `experiments/capacity-enforcement-exp/`. Bare `cases/`, `_INDEX.md` and `writeup-set-*.csv` are in
> `experiments/capacity-enforcement-exp/cassandra/stage3-ai-deep-read/`; bare `harness/`, `results/`,
> `timing/` and `environment.md` are in `experiments/capacity-enforcement-exp/cassandra/stage4-runtime-verification/`.
> Playbooks, templates and stage READMEs are method docs under `experiments/capacity-enforcement-exp/<stage>/`.

## Hadoop (added 2026-11-06)

**Hadoop `capacity-enforcement-exp` stage 3 is split by band.** Stage 2 is done
([`experiments/capacity-enforcement-exp/hadoop/stage2-ai-preprocessing/README.md`](experiments/capacity-enforcement-exp/hadoop/stage2-ai-preprocessing/README.md)):
9,684 units, each with one band in `hadoop/stage2-ai-preprocessing/bands.csv`.

| Person | Bands | Units | Rows | Helpers |
|---|---|---|---|---|
| **Jingsong** | A, B, C | **749** (A 90 incl. 18 anchors, B 170, C 489) | 712 | 37 |
| **Yang** | D | **8,935** | 8,557 | 378 |

Select by the `band` column of `bands.csv`; every unit is in exactly one person's share. The
Cassandra material below this section is unchanged and still applies to the Cassandra work.

- **Stage 3 not started.** Your folders (do not write to the other person's):
  stage 3 → `experiments/capacity-enforcement-exp/hadoop/stage3-ai-deep-read/yang/`, stage 4 →
  `experiments/capacity-enforcement-exp/hadoop/stage4-runtime-verification/yang/`. Each has a README listing the
  expected contents (`cases/`, `_INDEX.md`, `writeup.csv`, `predicted-*.md`; `results/`, `harness/`, `case-notes.md`).
- **Procedure, queue and status:** [`experiments/capacity-enforcement-exp/hadoop/PROCEDURE.md`](experiments/capacity-enforcement-exp/hadoop/PROCEDURE.md)
  (what "this is Yang, start the next batch of N" and "summarize the result status" do),
  your `queue.csv`, and `experiments/capacity-enforcement-exp/hadoop/status.py yang`.
- **Method:** shared playbooks and templates in `experiments/capacity-enforcement-exp/stage3-ai-deep-read/`
  (`playbook-autonomous.md`, `playbook-guided.md`, `playbook-non-config-autonomous.md`,
  `_TEMPLATE-*.md`). Citations are pinned to `rel/release-3.4.2` (`systems/hadoop/source/`).
- **Read order inside your share:** A first, then B, C (and for Yang, D in whatever order the
  triage below picks).
- **Yang:** D is the "unlikely to matter" band and is 92% of the corpus. Many D one-line reasons are
  templated by a text-pattern helper (band is the agent's judgement; the reason may be generic), so
  treat D reasons as hints, not evidence. A 40-row spot check of max/limit/capacity/quota/memory/bytes
  D rows found no clear misband. Most D is YARN scheduler, web/DAO, protobuf and CLI code; a sensible
  first pass is a cheap triage of D rows (by `reason` and path) to pull out anything that deserves a
  full read, rather than a case file per row. Record the triage rule you choose here.

Created 2026-10-23. This file holds **Yang's personal handoff only**: set B, its procedure,
progress, nodes and log. The shared background (what the experiment is, state, decisions in force,
working preferences, where things live, stage-4 recipe, lessons, open follow-ups, node access) is in
[`HANDOFF.md`](HANDOFF.md): **read it first**, then
[`experiments/capacity-enforcement-exp/README.md`](experiments/capacity-enforcement-exp/README.md) for the format spec.
Jingsong works on set A in parallel ([`HANDOFF-Jingsong.md`](HANDOFF-Jingsong.md)).

> **Handoff-notes rule (2026-10-23):** a session that starts from this file records **personal**
> notes (progress, batch log, Yang's node state, set-B decisions) **here**. Notes common to both
> people (shared lessons, decisions, follow-ups) go in `HANDOFF.md`. Do not edit
> `HANDOFF-Jingsong.md`.

## Progress

| | Targets | Written up | Stage 4 closed |
|---|---|---|---|
| Set B | 161 | 0 | 0 |

## The job

Use **fresh autonomous agents** to write up a case file for every target in **set B**, then
verify each case at **stage 4** (audit, run 1 at both tiers, results file, outcome class).

- **The list:** [`experiments/capacity-enforcement-exp/cassandra/stage3-ai-deep-read/writeup-set-B.csv`](experiments/capacity-enforcement-exp/cassandra/stage3-ai-deep-read/writeup-set-B.csv) —
  **161 targets covering 169 stage-2 units** (band A 45, B 92, C 32). Mostly `io/`, `net/`,
  `repair/`, `service/`, `streaming/`, `transport/`, `utils/` and the rest of `index/` (from
  `index/sai/disk/v1/vector/` on), plus a few lines elsewhere tied to the same queue rows.
- **Where the list came from (2026-10-23):** the 402 band A/B/C units of
  `cassandra/stage2-ai-preprocessing/bands.csv`, minus the 65 that are already the target of a case file
  (a guided file's **Capacity check** or an autonomous file's **Entry pointer**), leaves **337**.
  They were split into two sets of near-equal size by source area, keeping every unit of one
  source file and every unit of one `predicted-negative.md` row in the same set, so siblings are
  written up by one person. Set A has 168 units / 159 targets.
- **A target** is one `file:line` (units on the same line, `#1`/`#2`, are merged) or one helper
  method (`helper <class>.<method>()`; give the agent the comparison line inside the helper,
  found with `grep -n` in `systems/cassandra/source/`).
- **CSV columns:** `order` (suggested order), `target`, `units`, `band`, `estimate`,
  `stage3_record` (where stage 3 recorded the line: a `predicted-negative.md` section, a
  `predicted-positive.md` item, or a note), `stage2_reason`, and two columns to fill as you go:
  `case_file` (the stem) and `stage4` (the outcome class, or "running").
- **Special rows:**
  - **The two accepted candidates come first** (orders 1–3, positive estimate, from
    `predicted-positive.md`): `native_transport_max_frame_size` (`Envelope.java:429`, with its
    allow side `:441` — one case can cover both) and `cached_rows_fail_threshold`
    (`ReplicaFilteringProtection.java:323`). The queue file names the guided agent for them; write
    them up with the autonomous agent like the rest, and remove them from `predicted-positive.md`
    when their case files land.
  - `ResourceLimits.java:213` (settled 2026-10-21: cited, not a case; the production reserves are
    `Concurrent:138`) and `Dispatcher.java:345` (no queue entry; same method as an existing case's
    target, `:348`). Decide per row whether a separate case is worth it; record the decision in the
    CSV either way.

## How to do one target

### 1. Write-up (stage 3, autonomous agent)

1. Make a copy of the source **outside the repository**, so the agent cannot read other cases:
   `rsync -a systems/cassandra/source/ ~/cassandra-5.0.9/`.
2. Open a **fresh** Claude Code session in that copy. Give it only
   [`playbook-autonomous.md`](experiments/capacity-enforcement-exp/stage3-ai-deep-read/playbook-autonomous.md),
   [`_TEMPLATE-autonomous.md`](experiments/capacity-enforcement-exp/stage3-ai-deep-read/_TEMPLATE-autonomous.md)
   and the target as `file:line`. Nothing else about the line (not the stage-3 ground, not the CSV).
3. File the result as `cases/<stem>--autonomous.md`. The stem follows the existing ones:
   `<constraint>-<method>-<operand>`; check `ls cases/` first and add `-2` if the stem is taken.
4. Add the `_INDEX.md` §1 row (Agent `autonomous`, the file's own estimate, Stage 4 empty) and its
   sha256 in `_INDEX.md` §4. Put the stem in the CSV's `case_file` column. Leave the line in
   `predicted-negative.md` until stage 4 has closed the case.

### 2. Verification (stage 4, a separate agent)

Protocol: [`experiments/capacity-enforcement-exp/stage4-runtime-verification/README.md`](experiments/capacity-enforcement-exp/stage4-runtime-verification/README.md)
("The run protocol"); environment: [`environment.md`](experiments/capacity-enforcement-exp/cassandra/stage4-runtime-verification/environment.md).

1. **Step-0 audit** (A–D) against `systems/cassandra/source/`: re-read every load-bearing
   citation, check the trigger really reaches the check (find the `OperationType` / caller it
   produces), check the predictions have numbers and the workload arithmetic reaches the limit.
   Fixes go in the case file as dated amendments (section D). Write the audit and the frozen hash
   of the predictions and conclusions tables (B2f–g, B3f–g) into a new results file from
   `_TEMPLATE.md` **before any reading**.
2. Harness under `harness/<stem>--autonomous/` (unit test + one run script per case with
   `EXPECTED:` lines, a stop on a failed first-trigger check, node stopped on any exit);
   instrument-check it. Shakedowns are not readings. Working trees from
   [`copy-source.sh`](experiments/capacity-enforcement-exp/cassandra/stage4-runtime-verification/copy-source.sh), one per
   case. Write audit, amendments, freeze hash and harness to the repo before run 1.
3. Run 1, unit tier then each cluster label as a background job; read `summary.txt`, not whole
   logs; pull small excerpts to `results/<stem>/run1/`, full logs stay on the node.
4. **Independent self-check** that re-parses the raw logs; fill the results file, including the
   **Outcome class**, and the case file's feedback section; decide run 2 and say why.
5. Close the case: `_INDEX.md` §1 Stage 4 and Outcome class cells, the new sha256 in §4 if the case
   file was amended, remove the line from `predicted-negative.md` (or `predicted-positive.md`),
   fill the CSV's `stage4` column, update **Progress** above.

### Rules that hold for every case

- **No conclusions row or prediction is changed after any reading.** A reading that matches no
  frozen row is "Not confirmed (no matching row)". Amendments are dated and made before the first
  reading.
- A negative-estimate case needs a **positive control** (a knob or arm that does move usage), so a
  "does not cap" result cannot come from a workload that never reached the check.
- Nothing is left running on a node; each results file lists what stays on the node.
- Commit per closed batch; `git pull --rebase` before every push (Jingsong commits to the same
  `main`). Edit only set-B rows in the shared files (`_INDEX.md`, `predicted-negative.md`,
  `predicted-positive.md`).

## Suggested batching

- **4–5 targets per batch, one stage-4 agent per node**, as in the four batches of 2026-10-21/22.
- Keep the targets of one `predicted-negative.md` row in one batch (they share a design).
- Order within the CSV: the two positive candidates, then band A → B → C by source area.
  Low-value rows (§13 not production code, §12 emptiness tests, §1 configuration validation) can
  wait until the rest is done.

## Nodes

**Yang's nodes: to be announced by Yang** (the earlier suggestion of `pc06`/`pc13` does not hold).
Do not run anything on a node until they are named here. Jingsong uses `pc07` and `pc12`; do not
use those.

Shared node facts (experiment `jason92-320876`, SSH key, `ulimit`, leftover files from closed
cases) are in `HANDOFF.md` "Nodes and access" and `cassandra/stage4-runtime-verification/environment.md` §7.
If Yang's nodes are elsewhere, set them up from `environment.md` and record them here.

## Handoff log

Dated notes from Yang's sessions go here, newest first.

- **2026-11-06 (Hadoop batch 1, stage 4)** — First Hadoop stage-4 environment set up on the local node
  (`node0.jason92-323989`) at Yang's request: `hadoop/stage4-runtime-verification/yang/environment.md` and
  `copy-source.sh`; build in `/mydata/yang-s4/hadoop-base` (JDK 8, needs `YARN_IGNORE_ENGINES=true`). Order 2's case
  run per the stage-4 protocol by a fresh agent: audit Ready after amendments (A1–A8), frozen sha256 `660ebeee…`,
  two runbook defects fixed (A9 unit AM heartbeat, A10 `cp -r`), unit **Confirmed** (u3 41984 MB in all three arms;
  control 25600 MB) and cluster **Confirmed** (u3 7168 MB / ~3648 MiB RSS in all three arms; control 3072 MB /
  1216 MiB) → **Confirmed — does not cap, true negative**. No run 2. Run data in
  `/mydata/yang-s4/<stem>-run1/` (1.5 GB). Batch 1 closed. Next: order 6.
- **2026-11-06 (Hadoop batch 1, orders 1–5, tier 1)** — 5 rechecked by fresh agents (target `file:line` +
  the PROCEDURE question only), source copy `~/hadoop-3.4.2/` on the local node. 4 D (orders 1, 3, 4, 5:
  split-boundary read, three ZooKeeper retry counters), 1 promoted to **A** (order 2,
  `GuaranteedOrZeroCapacityOverTimePolicy.java:719`). Answers in `queue.csv` `recheck`/`recheck_note`
  (new column). Promoted unit's autonomous case file:
  `yarn.scheduler.capacity.queue-path.capacity-getInitialLeafQueueConfiguration-availableCapacity`,
  estimate **negative** (the check gates a leaf's guaranteed floor, not its max-capacity ceiling); new
  Hadoop `_INDEX.md`. The agent got the Cassandra playbook/template plus a Hadoop substitution note (no Hadoop
  playbook yet; written later the same day at `hadoop/stage3-ai-deep-read/playbook-autonomous.md`, used from
  batch 2). Stage 4 not run: no Hadoop environment/harness. Tier-1 miss rate so far 1/5. Next: order 6.

- **2026-10-23** — Node assignment withdrawn pending Yang's choice. File trimmed to personal
  content; shared notes live in `HANDOFF.md` (routing rule added there).
