# If-Check Exp — Handoff for Jingsong (set A)

Created 2026-10-23. The shared background (what the experiment is, where things live, the
stage-4 lessons, node access) stays in [`HANDOFF.md`](HANDOFF.md); this file holds only
Jingsong's next job. Yang works on set B in parallel ([`HANDOFF-Yang.md`](HANDOFF-Yang.md)).

## The job

Use **fresh autonomous agents** to write up a case file for every target in **set A**, then
verify each case at **stage 4** (audit, run 1 at both tiers, results file, outcome class).

- **The list:** [`cassandra/if-check-exp/stage3-ai-deep-read/writeup-set-A.csv`](cassandra/if-check-exp/stage3-ai-deep-read/writeup-set-A.csv) —
  **159 targets covering 168 stage-2 units** (band A 46, B 64, C 58), every one a negative estimate.
  Mostly `cache/`, `config/`, `cql3/`, `db/`, `hints/` and the first part of `index/` (up to
  `index/sai/disk/v1/vector/`), plus a few `io/`, `utils/` and other lines tied to the same queue rows.
- **Where the list came from (2026-10-23):** the 402 band A/B/C units of
  `stage2-ai-preprocessing/bands.csv`, minus the 65 that are already the target of a case file
  (a guided file's **Capacity check** or an autonomous file's **Entry pointer**), leaves **337**.
  They were split into two sets of near-equal size by source area, keeping every unit of one
  source file and every unit of one `predicted-negative.md` row in the same set, so siblings are
  written up by one person. Set B has 169 units / 161 targets.
- **A target** is one `file:line` (units on the same line, `#1`/`#2`, are merged) or one helper
  method (`helper <class>.<method>()`; give the agent the comparison line inside the helper,
  found with `grep -n` in `cassandra/cassandra-5.0.9/`).
- **CSV columns:** `order` (suggested order), `target`, `units`, `band`, `estimate`,
  `stage3_record` (where stage 3 recorded the line: a `predicted-negative.md` section, or a note),
  `stage2_reason`, and two columns to fill as you go: `case_file` (the stem) and `stage4`
  (the outcome class, or "running").
- **Special rows** (read the `stage3_record` note before writing them up):
  `SystemKeyspace.java:1919` (settled 2026-10-21 as a second check site of
  `prepared_statements_cache_size`, not a case) and `CommitLogSegmentManagerCDC.java:345`
  (an open stage-3 question fed back from stage 4). Decide per row whether a separate case is
  worth it; record the decision in the CSV either way.

## How to do one target

### 1. Write-up (stage 3, autonomous agent)

1. Make a copy of the source **outside the repository**, so the agent cannot read other cases:
   `rsync -a cassandra/cassandra-5.0.9/ ~/cassandra-5.0.9/`.
2. Open a **fresh** Claude Code session in that copy. Give it only
   [`playbook-autonomous.md`](cassandra/if-check-exp/stage3-ai-deep-read/playbook-autonomous.md),
   [`_TEMPLATE-autonomous.md`](cassandra/if-check-exp/stage3-ai-deep-read/_TEMPLATE-autonomous.md)
   and the target as `file:line`. Nothing else about the line (not the stage-3 ground, not the CSV).
3. File the result as `cases/<stem>--autonomous.md`. The stem follows the existing ones:
   `<constraint>-<method>-<operand>`; check `ls cases/` first and add `-2` if the stem is taken.
4. Add the `_INDEX.md` §1 row (Agent `autonomous`, the file's own estimate, Stage 4 empty) and its
   sha256 in `_INDEX.md` §4. Put the stem in the CSV's `case_file` column. Leave the line in
   `predicted-negative.md` until stage 4 has closed the case.

### 2. Verification (stage 4, a separate agent)

Protocol: [`stage4-runtime-verification/README.md`](cassandra/if-check-exp/stage4-runtime-verification/README.md)
("The run protocol"); environment: [`environment.md`](cassandra/if-check-exp/stage4-runtime-verification/environment.md).

1. **Step-0 audit** (A–D) against `cassandra/cassandra-5.0.9/`; fixes go in the case file as dated
   amendments (section D). Write the audit and the frozen hash of the predictions and conclusions
   tables (B2f–g, B3f–g) into a new results file from `_TEMPLATE.md` **before any reading**.
2. Harness under `harness/<stem>--autonomous/`; working trees from
   [`copy-source.sh`](cassandra/if-check-exp/stage4-runtime-verification/copy-source.sh), one per case.
3. Run 1, unit tier then cluster tier; independent self-check from the raw logs; fill the results
   file, including the **Outcome class**.
4. Close the case: `_INDEX.md` §1 Stage 4 and Outcome class cells, the new sha256 in §4 if the case
   file was amended, remove the line from `predicted-negative.md`, fill the CSV's `stage4` column.

### Rules that hold for every case

- **No conclusions row or prediction is changed after any reading.** A reading that matches no
  frozen row is "Not confirmed (no matching row)".
- A negative-estimate case needs a **positive control** (a knob or arm that does move usage), so a
  "does not cap" result cannot come from a workload that never reached the check.
- Nothing is left running on a node; each results file lists what stays on the node.
- Commit per closed batch; `git pull --rebase` before every push (Yang commits to the same `main`).

## Suggested batching

- **4–5 targets per batch, one stage-4 agent per node**, as in the four batches of 2026-10-21/22.
- Keep the targets of one `predicted-negative.md` row in one batch (they share a design).
- Order within the CSV is band A → B → C, then by source area. Low-value rows (§14 package surveys,
  §12 emptiness tests, §1 configuration validation) can wait until the rest is done.

## What the earlier write-up batches teach (19 lines tested, 2026-10-21/22)

- "Counts items, not bytes" and "a soft target, not a ceiling" were weak grounds when each item has
  a known size or the target is a configurable byte count: those lines mostly came back **caps**.
  Hard-coded water marks and pool-internal bookkeeping did not.
- The cluster tier is where negative cases go **undetermined** (12 of 58 cases): plan a cluster arm
  that isolates the line (hold `native_transport_max_threads`, throttle the load, add a Byteman
  `AT LINE` mutant) and a positive control that is known to move.
- `cassandra-stress` limits itself to 1,024 requests in flight (raise `connectionsPerHost`); any
  request held longer than 12 s needs `native_transport_timeout` raised; read live heap from the
  `GC.class_histogram` total, not `GC.heap_info` after `GC.run`.
- More in `HANDOFF.md` ("Lessons") and each closed results file's §8.

## Nodes

Split with Yang until agreed otherwise: **Jingsong `pc07` and `pc12`**, Yang `pc06` and `pc13`
(experiment `jason92-320876`; access and state in `environment.md` §7 and `HANDOFF.md`).
Two cases on one node need separate copies, data directories, JMX ports and Byteman ports.

## Progress

| | Targets | Written up | Stage 4 closed |
|---|---|---|---|
| Set A | 159 | 10 | 10 |

**Batch log.** 2026-10-24, batch 1 (CSV rows 4, 5, 6, 8, 9; §6 `RangeTombstoneList` and §4
`CommitLogSegment`): `range_tombstone_list_growth_factor` ×3 true negative (do not cap), `commitlog_segment_size` ×2
true positive (cap per segment; the CSV said negative, the autonomous files estimated positive).
Write-ups were run as headless `claude -p` sessions in `~/cassandra-5.0.9` from `~/writeup-A/`.
Next: rows 1–3 (§14 cache bounds), 10–15 (`CommitLogSegmentManagerCDC.java:345`, `LeveledManifest`, `MajorLeveledCompactionWriter`), with row 7 a decision.

2026-10-24, batch 2 (CSV rows 11–15, §14 `LeveledManifest` and `MajorLeveledCompactionWriter`):
`lcs-maxBytesForLevel`, `sstable_size_in_mb-getCandidatesFor`, `sstable_size_in_mb-getnextlevel`,
`lcs-level-capacity-shouldSwitchWriter…` true negative (do not cap); `sstable_size_in_mb-shouldSwitchWriter…`
true positive (caps each file, soft by one partition). §14 lines have no own row in `predicted-negative.md`
(package survey row only), so nothing was removed there. The `lcs-level-capacity` cluster tier missed two
frozen numeric predictions (data volume 605 MiB, not 650 MB); the agent kept "Confirmed" because the
deciding rows held, a stricter reading is "Not confirmed (no matching row)".
Next: row 10 (`CommitLogSegmentManagerCDC.java:345`), rows 1–3 (§14 cache bounds), then CSV order 16 on.
