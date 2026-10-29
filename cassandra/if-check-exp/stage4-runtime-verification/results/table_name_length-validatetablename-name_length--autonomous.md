# table_name_length-validatetablename-name_length--autonomous — stage-4 results  <!-- file: results/table_name_length-validatetablename-name_length--autonomous.md; the stem ends in --autonomous -->

> **Case:** [`table_name_length-validatetablename-name_length--autonomous`](../../stage3-ai-deep-read/cases/table_name_length-validatetablename-name_length--autonomous.md)
>
> **Status:** **Closed 2026-10-28 — unit Confirmed (does not cap), cluster Refuted (caps)** (estimate negative; tiers disagree); no run 2
>
> **Outcome class:** undetermined — unit says does not cap, cluster says caps (the README's rule for tiers that disagree); the cluster tier measures the real node and its refutation is attributed below, so this reads as a false negative of the stage-3 estimate
>
> **Agent:** autonomous. "§9a" below means B2f/B2g (unit) and B3f/B3g (cluster); "§9b–§9e" means B2a–B2e or B3a–B3e; the case file's feedback section is its section D.

## 1. Before run 1 — design audit and freeze

| Field | Content |
|---|---|
| **Case-file version** | Autonomous file, sha256 of the whole file after the audit's amendments (block B5, 2026-10-28): `156f4d1695387e416347a94bc527a64565d48954371c554e2ff9316c29353f66` (`sha256sum`, run 2026-10-28 after B5 item 2 was corrected for defect D1 and before any cluster reading; an earlier freeze, `c31bbf85…`, was superseded by D1; the final file, with section D filled after the verdict, has the sha256 in §8). The file before the amendments had sha256 `e7541f0b0f97ada3200b85acc2b8ccb0a4d5e3a717e4ca507fd162724256c910` (in `b68711e5`). The amended file is not committed by this session. |
| **Harness** | [`harness/table_name_length-validatetablename-name_length--autonomous/`](../harness/table_name_length-validatetablename-name_length--autonomous/README.md), written 2026-10-28; not committed by this session. |
| **Tiers and values** | Unit (B2): table-name length L = 1 · 48 · 100 · 221 · 222 · 223 · 255; N = 1000 (36 at L = 1) tables at L and at 222; 50-column control. Cluster (B3): 500 tables x 1000 rows; arms L = 8 and L = 222 (2 repetitions each), 223-character `CREATE TABLE` rejection, control `memtable_heap_space` 64MiB vs 256MiB. |
| **Audit bottom line** | **Ready after amendments** — 2026-10-28 |

### 1.1 Design audit

| Group | Check | Rating | Note (section checked) |
|---|---|---|---|
| A. Core question | constrained quantity is memory or disk bytes | Partly | A2: the operand is a name length in characters, not bytes of memory or disk; its byte effect is the per-name string (tens of bytes), derivable (A1, B2c arithmetic). Counted as a count with a derivable byte size. |
| A. Core question | knob varied, ≥ 3 values incl. default — or another approach, with the reason | Met | A1: a hard-coded constant, not settable. The design varies the input name length across 1, 48, 100, 221, 222, 223, 255 (unit) and 8, 222, 223 (cluster) (B2b/B3b) and compares usage, with the limit at the boundary. |
| A. Core question | real resource measured, not only the counter (gap named) | Met | B2d deep size (unit), B3d heap after GC and `du` on a real node; B3d names what is not observable (per-name string retention). |
| A. Core question | usage driven to the limit and past it | Met | L = 222 (limit), 221 (below) and 223, 255 (past) in the unit tier; 223 at the node. |
| A. Core question | positive control (negative estimate) | Met | 50 extra columns (unit) and `memtable_heap_space` (cluster). |
| B. Logic | each step says what it establishes | Met | B2e/B3e. |
| B. Logic | prediction stated in numbers or a clear relation | Partly → Met after B5 item 7 | "within noise", "comparable", "small" had no threshold; thresholds set before any reading. |
| B. Logic | every plausible outcome has a conclusions row with its evidence | Met | B2g/B3g cover accepted-over-limit, usage follows, usage flat, control not moving. |
| B. Logic | confirmation needs ceiling-follows-knob and direct disallow evidence | Met | The rejection at limit+1 (message text) plus flat usage with a moving control. |
| B. Logic | alternative explanations and their controls | Met | B2h/B3h controls. |
| C. Specific | a human can follow it from the intro and §9a | Met | A1–A3, B1. |
| C. Specific | an AI can run §9b–§9e without re-deriving the code path | Partly → Met after B5 | name generation, N at the shortest length, client, control size were open. |
| C. Specific | knob, values, workload, commands, observables, sampling, stop conditions exact | Partly → Met after B5 | see B5 items. |
| D. Runnable | harness and environment prerequisites exist or are listed | Partly | JDK 11.0.32.1, Ant 1.10.12 on pc29; probe test, node scripts, client are step-1 work. JOL not on classpath: jamm used (B5). |
| D. Runnable | workload arithmetic reaches the limit (data, time, disk, memory) | Met | 500 tables x 1000 x ~100 B = about 50 MB per arm; the 3,000,000-row control is about 300 MB of payload (B5 item 6); 1 GiB heap with 500 tables is checked at run time (B5 item 8). |
| D. Runnable | load-bearing citations spot-checked against the pinned source | Met | Re-read in `cassandra/cassandra-5.0.9/` on 2026-10-28: `SchemaConstants.java:75,80,85,91,105`; `TableMetadata.java:482-484,512-520,638-641,711-719`; `Directories.java:123`; `CreateTableStatement.java:112`. All hold. |

| # | Recommendation | Applied? | Why |
|---|---|---|---|
| R1 | B5 item 1: A5 javadoc issue number verified (CASSANDRA-16956) | Applied 2026-10-28 | was "not verified" |
| R2 | B5 items 2-3: instrument and unique-name generation | Applied | L = 1 cannot give 1000 names |
| R3 | B5 items 4-5: arms, client, readings | Applied | unspecified |
| R4 | B5 item 6: control size (5 GiB to 3,000,000 rows) and observable | Applied | arithmetic; `jstat` cannot see the pool |
| R5 | B5 items 7-8: thresholds, heap contingency | Applied | no numbers |

**Agreement criteria** — run 2 is not planned.

## 2. Environment

| Field | Run 1 |
|---|---|
| Date | 2026-10-28 (node clock, MDT): unit about 13:00 (after the D1 shakedown); cluster 13:41:06–14:42:48; supplementary MBean count about 14:55 |
| Node | `pc29` = `node3.jason92-321705.misconfiguration-pg0.cloudlab.umass.edu` (40 cores, 251 GiB RAM). One Cassandra node on 127.0.0.1 per arm, fresh directories each, heap 1 GiB (G1) |
| OS and kernel | Ubuntu 22.04, `5.15.0-198-generic` |
| JDK | openjdk 11.0.32.1 (2026-08-18) |
| Ant | Apache Ant 1.10.12 |
| Local source copy | `~/s4-b2/base` from `cassandra/cassandra-5.0.9/` at repository commit `b68711e5` by `copy-source.sh` (tag `cassandra-5.0.9`), `ant build-test` (1 min 17 s) |
| Case-file commit / harness commit | `b68711e5` holds the file before amendments (sha256 `e7541f0b0f97ada3200b85acc2b8ccb0a4d5e3a717e4ca507fd162724256c910`); the amended file and the harness are uncommitted |
| Storage for node data | node-local `/dev/sda3` (63 GB, 49 GB free before the run), under `~/s4-b2/run/tbl/<label>/`; nothing on `/proj` |
| Full logs (outside the repo) | `~/s4-b2/logs/table_name_length-validatetablename-name_length--autonomous/run1/{unit,cluster}/` on `pc29` (histograms, `cmd.log`, samples, json); node directories `~/s4-b2/run/tbl/`; supplementary `~/s4-b2/supp/` |

## 3. Runbook defects

| # | Run | Step | Problem | Fix | Decision (date) | Case-file commit |
|---|---|---|---|---|---|---|
| D1 | unit | B2a/B2d (size instrument) | `ObjectSizes.measureDeep` (and jamm's `measureDeep` generally) stops at `@Unmetered` `TableMetadata` and `ColumnMetadata`: the first shakedown measured 4 bytes per table at every L and the 50-column control did not move. | B5 item 2: a reflective walker with jamm's shallow `measure`; `ObjectSizes.measureDeep` printed beside it. B2f/B2g unchanged. | 2026-10-28, tier restarted (shakedown only; no counted reading existed) | uncommitted |
| D2 | cluster | harness shakedown | `nodetool statusbinary` prints `not running` and the harness matched `running` in it; `compactionstats` has no colon after `pending tasks`; two harness slips in the control writer and the json glob. Found in the discarded `shake1` runs. | harness fixed | 2026-10-28 | n/a |
| D3 | cluster | B3a (heap), B4 | Not a defect: 500 tables fit the 1 GiB heap (heap after GC 255–320 MB, no OutOfMemoryError); B5 item 8's contingency was not needed. | none | 2026-10-28 | n/a |

## 4. Run 1

**Scope:** unit tier (all of B2) and cluster tier (all of B3: four arms, the 223-character rejection in both long arms, the memtable control), plus one supplementary count of metric MBeans (not part of the frozen design). **Command log:** `cluster/cmd.log`, `unit/summary.txt` under [`results/table_name_length-validatetablename-name_length--autonomous/run1/`](table_name_length-validatetablename-name_length--autonomous/run1/).

### 4.1 Readings

**Unit tier** (`unit/test.out`, `selfcheck.txt`)

| Test or assertion | Result | Evidence |
|---|---|---|
| `validate()` at L = 1, 48, 100, 221, 222 | pass; directory name length 34 / 81 / 133 / 254 / 255 | `test.out` case lines |
| `validate()` at L = 223, 255 | `ConfigurationException` "Table name must not be more than 222 characters long (got 223 characters for …)"; no assertion failure; directory name would be 256 / 288 | same |
| assertions enabled (`-ea`) | true | `test.out` info line |
| known-answer checks | 11 of 11 ok | `unit/summary.txt` |
| retained size per table, 0 extra columns, L = 2 / 48 / 100 / 221 / 222 | 821.98 / 861.98 / 917.98 / 1037.98 / 1037.98 B (3 repetitions identical; L = 1: 874.89 B at N = 36) | `test.out` size lines |
| L = 2 to 222 | +216.00 B per table (one copy of 220 characters, aligned) | `selfcheck.txt` |
| 50 extra columns at L = 48 (positive control) | +5,127.60 B per table = 24 x the whole name range | `selfcheck.txt` |
| upstream `TableMetadataTest` | 2 tests, 0 failures | `unit/summary.txt` |

**Cluster tier** — arms (500 tables x 1,000 x 100-byte values = 500,000 rows each, one table per directory; heap 1 GiB; settle 60 s after `nodetool flush`; DDL about 560 s per arm):

| Arm | Name length | Histogram Total / heap used after GC (B) | Data dir (B; script / self-check re-walk) | RSS (KB) | Evidence |
|---|---|---|---|---|---|
| A1 | 8 | 257,460,304 / 257,410,600 | 16,400,345 / 16,417,052 | 1,921,752 | `A1.json`, `A1.histo-head.txt` |
| A2 | 8 | 255,192,568 / 255,142,864 | 16,381,077 / 16,381,077 | 1,910,056 | `A2.json` |
| B1 | 222 | 314,574,640 / 314,524,936 | 16,618,349 / 16,623,792 | 1,960,408 | `B1.json` |
| B2 | 222 | 319,508,688 / 319,458,984 | 16,598,949 / 16,615,677 | 1,962,268 | `B2.json` |

Long-arm mean minus short-arm mean: **+60,715,228 B** (histogram Total and heap used alike); spread between repetitions 2,267,736 B (short), 4,934,048 B (long); name-byte budget (B5 item 7) 2,140,000 B. Data dir +217,938 B (script) / +220,670 B (re-walk) = 1.33 % / 1.34 % of 16.4 MB. Longest directory name 63 (system tables) in the short arms and 255 in the long arms. B1 and B2: `CREATE TABLE` with a 223-character name rejected, `ConfigurationException` (code 2300), message `ks.aaa…: Table name must not be more than 222 characters long (got 223 characters for "aaa…")`. No `ERROR` lines and no OutOfMemoryError in any `system.log`.

Where the difference is: the class histograms (`A1.histo.txt` etc., on the node; heads in `run1/cluster/`) differ by +57.3 MB (A1 to B1) and +64.6 MB (A2 to B2) in `byte[]` of a total change of +57.1 MB and +64.3 MB (`supplementary-metrics-mbeans.txt`). Supplementary count on a separate node with 20 tables (not part of the frozen design): 112 metric MBeans per table (2,240 under `org.apache.cassandra.metrics:type=Table,keyspace=ks`), whose names total 209,000 characters at L = 8 and 688,360 at L = 222, +23,968 characters per table = 112 x 214 (one copy of the extra name text per MBean name).

Control (one keyspace `kc`, 3,000,000 x 100-byte rows in three client processes, `memtable_heap_space` set, `heap_buffers`):

| Setting | Peak `AllMemtablesHeapSize` | Flush enqueues (script / self-check) | Evidence |
|---|---|---|---|
| 64MiB | 22,341,192 B | 110 / 117 | `C64.json`, `C64.samples.csv` |
| 256MiB | 89,061,120 B | 49 / 56 | `C256.json`, `C256.samples.csv` |

Ratio 0.25; control moves clearly. Control difference 66.7 MB.

### 4.2 Conclusion and logic

1. **Validity.** The limit was reached at the node: 222-character tables were created (directory names of 255 characters on disk) and a 223-character one was refused [observed: `B1.json`, `B2.json`, `selfcheck.txt`]. Hold-fixed settings: same build, heap, rows and values in all four arms, fresh data directories [observed: `cmd.log`]; no write failed and no `ERROR`/OutOfMemoryError in the logs [observed: `summary.txt`, `selfcheck.txt`]. The control moved [observed]. Valid.
2. **Readings.** The repetitions agree well (short arm within 2.3 MB, long arm within 4.9 MB) and the arms are 55–65 MB apart; every long-arm run is above every short-arm run [observed: `summary.txt`]. The difference sits in `byte[]` (string text), +57.3 MB and +64.6 MB, equal to the whole change in live bytes [observed: histograms]. RSS is also higher in the long arms (+45 MB) [observed: `A1.json`..`B2.json`].
3. **Matched row.** Unit: "Deep size delta small and proportional to L, 50-column delta much larger" -> claim confirmed for the objects measured: 216 B per table across 220 characters against 5,128 B for 50 columns, 223 and 255 refused, 222 accepted with a 255-character directory name [observed: `test.out`]. Cluster: "Arms differ by an amount comparable to the control difference -> claim refuted: name length significantly drives usage": the arms differ by 60.7 MB against a control difference of 66.7 MB (91 %), far above the larger of the 2.1 MB budget and the 4.9 MB repetition spread, and the data dir differs by 1.3 % (above the 1 % threshold) [observed: `summary.txt`, `selfcheck.txt`]. The rejection of 223 with the traced message was also observed [observed], so "223 accepted" and "mechanism not as traced" do not apply.
4. **Excluded rows.** "223 accepted": absent (refused, twice). "Deep size delta comparable to 50-column delta" (unit refutation): absent (216 vs 5,128 B). "Control heap does not change / cap never reached": control peak 22.3 MB vs 89.1 MB, flushes 110 vs 49, and the long name was reached. "Arms differ by far less than the control difference" (cluster confirmation): contradicted by 60.7 MB vs 66.7 MB.
5. **Observed vs. inferred.** Inferred: that the +60.7 MB is the table name text held in per-table metric objects (112 MBeans per table, each name carrying the table name, about 5 retained copies of the text per table: 60.7 MB / 500 tables / 214 characters = about 570 bytes per extra character per table, about 5 copies x 112 names) [inferred: `byte[]` growth in the histograms + the MBean name count of the supplementary node; no heap dump traced the references]. That the same cost applies to the unit tier's missing consumer (the unit probe builds `TableMetadata` objects only, with no metrics registration) [inferred: unit design].
6. **Deviations and gaps.** (a) Size sizer is a reflective walker, not `MemoryMeter.measureDeep` (D1). (b) Arm writers ran as four client processes, the control as three, not one client; rows and values identical across arms. (c) The 5 GiB control was run as 3,000,000 rows (B5 item 6). (d) The B3f prediction (low hundreds of KiB, below 1 % of heap) and the budget in B5 item 7 (about 2.1 MB) assumed about 20 retained copies of the name; the node holds roughly 540 times the name text per table, an amplification the case file's A4 listed as "not verified line by line". The prediction was not tuned to the reading. (e) The supplementary MBean count is on 20 tables on one separate node, not the arms. (f) The unit tier cannot see the dominant consumer; its Confirmed is for schema objects only. (g) No run 2.
7. **Core question.** Usage follows the constraint at the node: raising the table-name length from 8 to the limit of 222 characters raised heap after GC by 60.7 MB for 500 tables (about 121 KB per table, 24 % of a 257 MB heap in use, comparable to the 66.7 MB that a 64 to 256 MiB change of `memtable_heap_space` moves on the same instruments) and the data directory by 1.3 %. The 222-character limit therefore caps this per-table overhead, small per table but not negligible with many tables; the unit tier, which measures only `TableMetadata`, showed 216 B per table and missed it.

**Conclusion (one line):** unit B2g row "deep size delta small and proportional to L, 50-column delta much larger" — Confirmed (does not cap, schema objects only); cluster B3g row "arms differ by an amount comparable to the control difference" — **Refuted** (caps).

## 5. Self-check of run 1 — AI

### 5.1 Check of run 1's conclusion

`run1/selfcheck.py` re-parses the raw files (unit `test.out`; cluster `*.histo.txt`, `*.samples.csv`, node `system.log`, `cmd.log`, the node data directories re-walked) and prints the numbers cited; output in `run1/selfcheck.txt`: `SELFCHECK-RESULT: INTEGRITY OK`; its `[claim …]` lines show the unit claims holding and the cluster arm-difference and data-dir claims **REFUTED**, matching this conclusion. An earlier draft of the check counted the client's truncated stderr echo as a second rejection reading and failed on it; fixed (harness-side).

| Part | Holds? | Note (file re-read) |
|---|---|---|
| 1. Validity | yes | rejection message in both long-arm runs (`cmd.log`, 2 readings); longest directory name 255 in both long arms, 63 in short arms; no ERROR/OutOfMemoryError. |
| 2. Readings | yes | Totals re-read from the four `histo.txt` files equal the json; per-class diff recomputed (`byte[]` +57,301,600 and +64,611,800). |
| 3. Matched row | yes | +60,715,228 B recomputed from the histograms; control difference 66.7 MB from `samples.csv`; ratio 91 %. |
| 4. Excluded rows | yes | the unit confirmation row and the cluster confirmation row are each contradicted/consistent as stated. |
| 5. Observed vs. inferred | yes | the attribution to metric names is inferred and flagged; the refutation itself (arms differ, control comparable) is observed and does not depend on it. |
| 6. Deviations and gaps | yes | listed. The unit/cluster disagreement is explained by the unit probe's scope, not by a reading error. |
| 7. Core question | yes | steps follow the audited logic; no step rests on a missing reading. |

### 5.2 Run 2?

**No** — 2026-10-28. The cluster readings are repeatable (two arms each, spreads 2.3 and 4.9 MB against a 60.7 MB effect), the refutation is large and does not depend on an inferred statement, and the unit tier's different answer is explained by its scope. A heap dump tracing the name copies would be the next step if the mechanism matters; it is not needed for the verdict.

## 6. Run 2 — fresh AI session (optional)

Not done.

## 8. Verdict — AI

**Stage-3 estimate:** negative. **Outcome class:** undetermined (unit: does not cap; cluster: caps). The tiers disagree, which the README classes as undetermined. The cluster tier measured the real node and its effect is large and repeatable, so the estimate looks like a false negative; the unit tier's Confirmed is a statement about `TableMetadata` objects only. The estimate line in the case file is left as filed.

**Claim tested:** (B1) usage of heap, off-heap and disk does not follow `TABLE_NAME_LENGTH`: a name at the limit (222) compared with a short name adds only a per-table amount of order hundreds of bytes, and the limit rejects 223 without any change in node memory or data size. Falsified if raising the length changes node heap or disk by an amount comparable to a binding cap. "Confirmed" means this held.

| Tier | Verdict (B2g / B3g row) | Effect on the constraint | Basis | Date |
|---|---|---|---|---|
| Unit | Confirmed — "deep size delta small and proportional to L, 50-column delta much larger" (216 B vs 5,128 B per table; 223 refused) | does not cap (schema objects only) | run 1 + self-check | 2026-10-28 |
| Cluster | **Refuted** — "arms differ by an amount comparable to the control difference" (+60.7 MB vs 66.7 MB; data dir +1.3 %) | caps | run 1 + self-check | 2026-10-28 |

**Positive control:** unit, 50 extra columns (+5,128 B per table); cluster, `memtable_heap_space` 64MiB vs 256MiB (peak `AllMemtablesHeapSize` 22.3 MB vs 89.1 MB, flushes 110 vs 49). Both moved, so the cluster refutation is not an artefact of an insensitive instrument.

**Final sha256 of the case file (section D filled):** `4447cbc8efb441ba2f7e6c9e570a438b92e8378f844bfe39e48b48782c71b72c`.

**Feedback filed:** the case file's section D filled 2026-10-28 (uncommitted); amendments B5 (items 1-8, dated 2026-10-28) in section B. A refuted negative estimate is not re-estimated: the Estimate line stays `negative`.
