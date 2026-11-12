# Stage 2 — Hadoop (lexical banding)

Hadoop instance of stage 2. The method, bands and rules are in
[`../../stage2-ai-preprocessing/`](../../stage2-ai-preprocessing/README.md) (README, `playbook.md`,
`bands.md`); this file records the Hadoop run. **Done 2026-11-04.**

| File | What |
|---|---|
| [`bands.csv`](bands.csv) | **Every stage-1 unit with its band** — `uid, kind, band, reason, model, date, batch`. Stage 3's queue: read A, then B, C, D. |
| [`anchors.md`](anchors.md) | The 18 calibration anchors, each read against the source, and the one retired from the gate. |

## Result

Every unit has exactly one band: 9,684 = 9,269 narrowed rows + 415 distinct helpers (1,573 helper
rows), checked against `make-stage2-batches.py`'s unit list (none missing, none extra).

| Band | Units | of which helpers | Stage-3 order |
|---|---|---|---|
| **A** | **90** (72 + the 18 anchors) | 1 | first |
| **B** | 170 | 12 | second |
| **C** | 489 | 24 | third |
| **D** | 8,935 | 378 | last |

The A rate (0.7% without anchors) is well below Cassandra's (2.8%). Most of the difference is the
corpus: Hadoop's rows include large YARN scheduler, web/DAO, protobuf and CLI layers that are
almost all D. Rows the agents found hard are mostly B: flush-when-full buffers, buffer growth
without a visible cap, YARN container memory (memory on other hosts), and app or entity counts
whose per-object size is unclear.

## Extension run (2026-11-11)

The stage-1 extension beyond `if` (`../stage1-codeql-preprocessing/pilot-2026-11-11.md`) was banded
into this `bands.csv` with uids `E:` / `C:` (how to read them: `../../stage2-ai-preprocessing/README.md`,
"Extension rows").

| Kind | A | B | C | D | Units |
|---|---|---|---|---|---|
| `enforcement` | 22 | 96 | 226 | 3,333 | 3,677 |
| `verdict` | 4 | 10 | 43 | 1,137 | 1,194 |
| `capacity-set` | 84 (incl. 2 anchors) | 166 | 346 | 4,523 | 5,119 |
| **Total** | **110** | **272** | **615** | **8,993** | **9,990** |

- **Model and batches:** `claude-opus-5-5`, 2026-11-11, 17 fresh agents. 50 batches (`ext-batch-01` to
  `ext-batch-50`) of 200 units, rows only. Every agent was told to judge each row itself, with no
  scripted default bands.
- **Anchors:** each batch carried 26 anchors: the 18 `if` anchors, 2 Hadoop extension anchors
  (`RawPathHandle.MAX_SIZE`, `SingleFilePerBlockCache.maxBlocksCount`, rows with batch `ext-anchors`)
  and the 6 Cassandra extension anchors as cross-system calibration (uids `X:cassandra:…`, not
  recorded). **All 26 came back A in all 50 batches.**
- **Repeated reasons:** batches 19–24 are almost all method-verdict rows of protobuf `has*()`
  field-presence methods, so one D reason repeats there.
- **Stage 3:** the 997 A–C units were appended to the end of Jingsong's `queue.csv` (orders 750–1746,
  `../stage3-ai-deep-read/jingsong/append-ext-to-queue.py`). The D units stay here unread; Yang's
  queue is unchanged.

## Run

| | |
|---|---|
| Input | `make-stage2-batches.py codeql-queries/results/hadoop <out>`: 49 batches, 200 units each (the last 66) + the 18 anchors |
| Model | `claude-opus-5-5`, 7 parallel subagents with 7 batches each, plus 1 re-run agent; one shared brief (row text only, no source) |
| Date | 2026-11-04 |
| Anchor gate | **passed on all 49 recorded batches**, with `FSDirectory.java:1272#1` exempted (`record-stage2-bands.py --exempt=`); see below |
| Re-run | batches 01–07: the first agent banded `Limits.java:100#1` B, so the gate refused them and they were re-run by a fresh agent. That run passed and is the one recorded |
| Accidental consistency check | batches 01–07 were judged twice by independent agents: **1,385 of 1,400 units agree (98.9%)**; all 15 disagreements are one band apart (D↔C, C↔B), none involves A |
| Anchors in bands.csv | written once, after the batches, as band A, model `source-read`, batch `anchors` |

### What differs from the method, and why

- **One anchor retired from the gate.** `FSDirectory.verifyMaxComponentLength length >
  maxComponentLength` came back B from 3 of the 6 first-run agents that saw it, each time in all
  7 of its batches. A row that sensible readers split on cannot be a yardstick, so it was exempted
  rather than re-running 21 batches. Its source read stands; see [`anchors.md`](anchors.md).
- **Anchors were recognisable.** Every batch carried the same 18 rows, and every agent noticed
  them, even after the re-run gave each batch fresh random ids and order. (Cassandra's batch files
  labelled anchor lines `ANCHOR` outright, so its gate was never blind either.) The gate
  therefore shows each agent was self-consistent and on the expected yardstick for these 18
  rows. It is not a blind test.
- **D reasons are partly templated.** Every agent read every row and chose the A/B/C rows and
  their reasons itself, but filled in most D rows' one-line reason from a small text-pattern
  helper ("comparison against bare literal", "time/retry comparison", "config validation" and so
  on). The **band** of every row is the agent's own judgement; a D row's **reason** may be generic
  or occasionally off-label. A 40-row spot check of D rows whose comparison mentions max, limit,
  capacity, quota, free, memory or bytes found no clear misband.
- **Agents differ in strictness, and the corpus explains most of it.** Stage-1 rows are ordered by
  `opClass` first, so batches 01–20 are equality rows only, 21 is mixed, 22–46 are magnitude rows
  and 47–49 are helpers. The agents on 01–21 found 0–5 non-anchor A per 7 batches; the agents on
  the magnitude batches found 10–23. That is mostly the input, not the agent.
