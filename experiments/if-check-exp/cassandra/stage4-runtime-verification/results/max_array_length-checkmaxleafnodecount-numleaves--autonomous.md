# max_array_length-checkmaxleafnodecount-numleaves--autonomous — stage-4 results  <!-- file: results/max_array_length-checkmaxleafnodecount-numleaves--autonomous.md -->

> **Case:** [`max_array_length-checkmaxleafnodecount-numleaves--autonomous`](../../stage3-ai-deep-read/cases/max_array_length-checkmaxleafnodecount-numleaves--autonomous.md)
>
> **Status:** **Self-checked 2026-10-28 — unit Confirmed (does not cap in practice), cluster Confirmed (does not cap); sub-predictions missed: run-A retained-heap total and per-leaf retained windows; no run 2**
>
> **Outcome class:** true negative — stage-3 estimate `negative` against the stage-4 effect `does not cap` (in practice; see section 8) ([definition](../README.md#outcome-class))
>
> **Agent:** autonomous (B2 = unit tier, B3 = cluster tier, feedback = section D).

## 1. Before run 1 — design audit and freeze

| Field | Content |
|---|---|
| **Case-file version** | sha256 of the whole file after the audit's amendments (U/C items, dated 2026-10-28, inserted after the link rule): `6482c2b5279f47e2a13ded95901740c7892dc6f7b68d0e8b8bb90e3a00512930`. Repository HEAD `b68711e5`; case file, harness and results uncommitted. Computed before any reading and unchanged through both tiers (`sha256sum` re-checked 2026-10-28). The frozen text is everything above section D. |
| **Harness** | `harness/max_array_length-checkmaxleafnodecount-numleaves--autonomous/` (uncommitted; README lists the files). |
| **Tiers and values** | Unit (B2) and cluster (B3), both run. Capacity values: B in 16/24/4096/262144/1048576 with M = 1 or 1024 (unit); 5M/20M/40M rows (cluster). |
| **Audit bottom line** | **Ready after amendments** — 2026-10-28 |

### 1.1 Design audit

| Group | Check | Rating | Note (section checked) |
|---|---|---|---|
| A | bytes | Met | A2: heap of `leafBlockStartValues` and the `splitValues` array, `bytesPerValue * numLeaves` bytes. |
| A | knob | Partly | Library constant (`ArrayUtil.MAX_ARRAY_LENGTH`); not settable. B2b varies B (bytes per value) and M so the product reaches it; cluster varies rows and the buffer. Reason in A1. |
| A | real resource | Partly | B2d heap after GC and histogram; the heap of the lists is observed through a callback hook (U3) because the writer is garbage after `write()`. |
| A | driven past limit | Met | B2c: L = floor(LIMIT/B)+1 leaves reached at B = 1 MiB (2048 leaves). |
| B | steps | Met | B2e numbered. |
| B | prediction numbers | Partly | off-by-one in the throw count (ceil vs floor, U2) and 'tens of MB' (U3) corrected. |
| B | every outcome has a row | Met | B2g has throw/no-throw and control rows. |
| B | confirmation needs ceiling-follows-knob and disallow evidence | Met | the throw at exactly L is the disallow evidence; run A at real widths shows the cluster-scale operand stays far below. |
| B | alternative explanations | Partly | artificial widths are the only way to reach it; M = 1024 vs 1 control (U4). |
| C | human can follow | Met | A1-A3. |
| C | AI can run without re-deriving | Partly | launcher, heap, callback hook (U1-U3). |
| C | exact values | Partly | workload and instruments for the cluster tier made exact (C1). |
| D | harness exists | Partly | written in step 1. |
| D | workload reaches limit | Partly | unit: 2 GiB of start values (+2 GiB splitValues in run C) need 12 GiB, not 6 (U1); cluster cannot reach the limit (needs about 9e10 points) - it tests only the no-throw/usage-growth side. |
| D | citations spot-checked | Met | `BlockBalancedTreeWriter.java:106-110,172-173,486,562-568,649-654`; `IndexTermType.java` widths and `StorageAttachedIndexOptions.java` default were taken from the case file's reading and re-checked by grep where cited. |

| # | Recommendation | Applied? | Why |
|---|---|---|---|
| R1 | Environment, heap, arithmetic fix and callback hook (U1-U4) | Applied 2026-10-28 | not runnable / off by one as filed |
| R2 | Cluster workload, instruments, numbers (C1-C2) | Applied | B3 lacked a writer, a column layout and numbers |
| R3 | A1 'value not verified' is resolved by the probe printing LIMIT | Applied (run time) | jar not in tree |

**Pre-run-1 instrument checks** (disclosed; none of them is a reading used in a prediction): see section 3 and the harness README.

**Pre-run-1 instrument checks and shakedowns (disclosed; none edited a prediction):** (1) Two known-answer runs of `LeafCountProbe` before the unit tier (B = 1 MiB, M = 1, N = L - 1 and N = L): the first completed, the second threw `too many nodes` at 2048 leaves; the retained-heap samples were of the order of B per leaf, and the pre-registered per-leaf window [B + 24, B + 80] was left as filed (the unit tier below shows it is finer than the probe's resolution at large B). (2) One cluster shakedown, 300,000 rows, 32 MiB buffer, discarded: it showed that two WCS_EXIT lines (one per index) appear per flush, that `SELECT index_name, count(*)` without grouping returns one row (the harness now counts rows client-side), and that the JMX bean answers after start-up (the first polls print `ERR`). No prediction was changed.

## 2. Environment

| Field | Run 1 |
|---|---|
| Date | unit 2026-10-28 (node clock UTC 2026-10-28 23:54 to 23:58); cluster 2026-10-28 (node clock UTC 2026-10-29 00:08 to 01:35) |
| Node | `pc32` = `node2.jason92-321705.misconfiguration-pg0.cloudlab.umass.edu` (40 cores, 251 GiB); up to six nodes of this session's four cases ran at once |
| OS and kernel | Ubuntu 22.04.2 LTS, `5.15.0-198-generic` |
| JDK / Ant | openjdk 11.0.32.1 (2026-08-18) / Apache Ant 1.10.12 |
| Local source copy | `~/s4-b34` from `cassandra/cassandra-5.0.9/` at repository commit `b68711e5` (`copy-source.sh`), `ant build-test` BUILD SUCCESSFUL; cluster copy `~/s4-b34-vB` (the same tree plus `stage4.Alloc` in its jar); the variant copies were deleted after the runs (rebuild with the harness `make-variant*.sh`) |
| Case-file / harness commit | uncommitted (working tree of `b68711e5`); case-file sha256 in section 1 |
| Storage for node data | `~/stage4-tmp/b34/c2/<label>` on local `/dev/sda3`, removed after each run (R40 peaked at several GB); nothing under `/proj` except these excerpts |
| Full logs (outside the repo) | `pc32:~/s4-b34-logs/b2/run1/` (`unit/`, `cluster/<label>/` with `heap.csv`, `gc-*.log`, `segbuf.csv`, `debug.log`, `system.log`, `stdout`-derived `wcs.txt`) |

## 3. Runbook defects

| # | Run | Step | Problem | Fix | Decision (date) |
|---|---|---|---|---|---|
| D1 | cluster | C1 order | the filed workload creates 44 to 87 sstables by automatic memtable flushes during the load (4 GiB heap, shipped memtable settings; `AUTO_FLUSHES_DURING_LOAD` 10 / 44 / 43 / 87), so "flush" is the whole load plus the manual flush, not one flush; the harness's first analysis window (the manual flush only) missed them | `analyze_cluster.py` now takes everything before the rebuild as the flush phase; the 40M arm was kept | 2026-10-28, claim, prediction and table unchanged |
| D2 | cluster | launch | the 40M run was started twice by mistake (once from the chain, once by hand, same label and directory); both were stopped and their directory removed before any reading, and R40 was started again alone (slot 5) | none | 2026-10-28 |
| D3 | cluster | C1 | `SELECT index_name, count(*)` aggregated over the whole virtual table; counts are taken client-side from `segments-*.txt` | in `cluster-run.py` before the freeze of run 1's readings (shakedown) | 2026-10-28 |
| D4 | cluster | C1 | `cassandra-stress` user mode writes fewer distinct values than `n`: 4,987,984 / 19,951,573 / 39,903,077 values per index for n = 5M / 20M / 40M | none; all ratios use the measured value counts | 2026-10-28 |

## 4. Run 1

**Scope:** every B2 and B3 value of section 1. **Command logs:** `max_array_length-checkmaxleafnodecount-numleaves--autonomous/run1/` (`unit/unit.out`, `cluster/<label>/{readings.txt,wcs.txt,analysis.txt,segments-*.txt,...}`, `selfcheck.txt`).

### 4.1 Readings

**Unit tier** (`run1/unit/unit.out`; LIMIT = `ArrayUtil.MAX_ARRAY_LENGTH` = 2,147,483,631, printed by the probe)

| Run | B | M | N | result | leaves at the end | B x leaves / LIMIT | retained heap at 1/4, 1/2, E-1 leaves (bytes) |
|---|---|---|---|---|---|---|---|
| A | 24 | 1024 | 50,000,000 | completes | 48,829 | 5.457e-4 | -4,118,808; -3,062,664; -17,856 |
| A' | 16 | 1024 | 50,000,000 | completes | 48,829 | 3.638e-4 | 856,792; 1,806,568; 2,525,984 |
| C (x3) | 1,048,576 | 1 | 2047 = L-1 | completes | 2047 | 0.999512 | 541,079,296; 1,079,030,584; 2,149,419,104 (rep 3) |
| B (x3) | 1,048,576 | 1 | 2048 = L | **throws** `too many nodes; increase maxPointsInLeafNode (currently 1) and reindex` | 2048 (callback called 2047 times, 2048 terms consumed) | 1.00000 | 542,127,808; 1,080,079,096; 2,150,467,616 |
| C5 | 1,048,576 | 1 | 2043 = L-5 | completes | 2043 | 0.997559 | 540,030,208; 1,076,932,880; 2,145,189,760 |
| C / B | 262,144 | 1 | 8191 / 8192 | completes / **throws** | 8191 / 8192 | 0.999878 / 1.0 | last sample 2,147,470,160 / 2,147,731,960 |
| C / B | 4,096 | 1 | 524,287 / 524,288 | completes / **throws** | 524,287 / 524,288 | 0.999998 / 1.0 | last sample 2,171,940,960 / 2,171,945,696 |
| control | 24 | 1024 | 1,000,000 | completes | 977 | 1.09e-5 | 94,960; 136,928; 149,976 |
| control | 24 | 1 | 1,000,000 | completes | 1,000,000 | 0.0112 | 18,872,696; 39,196,160; 73,715,864 |

| Test or assertion | Result | Evidence |
|---|---|---|
| first throwing leaf | floor(LIMIT / B) + 1 = 2048, 8192, 524288 for B = 1 MiB, 256 KiB, 4096; N = L-1 completes with the product under LIMIT | `RESULT` lines |
| repeats of the 1 MiB pair | identical (throw at 2048, completes at 2047) in 3 fresh JVMs | `unit.out` |
| leaf count M = 1 against M = 1024 (B = 24, N = 1e6) | 1,000,000 against 977 (1024 x) | control rows |

**Cluster tier** (`run1/cluster/<label>/analysis.txt`; sums over all segment writes of the phase; 4 GiB heap; `bytes_per_value` 8 = `vb`, 24 = `vd`; flush phase = load plus manual flush, rebuild = `rebuild_index` of both indexes)

| Run | rows | values per index | flush: segments (per index) / leaves / largest leaves of one segment | flush BALANCED_TREE bytes (8 B + 24 B) | flush ALLOC | rebuild segments (vb, vd) / largest leaves | rebuild ALLOC | peak SegmentBufferSpaceUsedBytes |
|---|---|---|---|---|---|---|---|---|
| R5 | 5e6 | 4,987,984 | 11 / 9,760 / 444 | 17,698,423 + 107,946,468 | 4.20 GB | 21, 22 / 441 | 23.5 GB | 1,073,743,912 |
| R20a | 20e6 | 19,951,573 | 45 / 39,014 / 452 | 70,799,984 + 431,784,614 | 16.8 GB | 89, 89 / 441 | 94.0 GB | 1,073,744,148 |
| R20b | 20e6 | 19,951,564 | 44 / 39,034 / 446 | 70,791,456 + 431,778,794 | 16.8 GB | 87, 87 / 441 | 94.0 GB | 1,073,744,104 |
| R40 | 40e6 | 39,903,077 | 88 / 77,992 / 448 | 141,584,123 + 863,553,211 | 33.6 GB | 175, 175 / 441 | 188.1 GB | 1,073,744,204 |
| C32 (32 MiB) | 20e6 | 19,951,601 | 45 / 39,016 / 449 | 70,801,747 + 431,785,900 | 15.5 GB | **1455, 1454** / 14 | 93.8 GB | **33,557,052** |

| Observable | Reading | Evidence |
|---|---|---|
| `too many nodes` in `system.log` | 0 in all five runs | `readings.txt` `TOO_MANY_NODES_LINES 0` |
| largest `num_leaves` of one segment | 452 (flush) and 441 (rebuild): B x leaves / LIMIT = 24 x 452 / 2.147e9 = 5.1e-6 | `analysis.txt` `maxLeavesOneSegment` |
| `Global limit ... exceeded` debug lines | 21 / 88 / 86 / 174 / 2819 (R5 / R20a / R20b / R40 / C32): one per segment boundary on the rebuild path | `readings.txt` |
| heap used (jcmd sampler) | peaks 3.6 to 4.0 GB of the 4 GiB heap in every run (G1 fills the heap before collecting); does not separate rows or buffer sizes | `heap.csv` |
| load | 79 / 292 / 297 / 675 / 372 s | `readings.txt` |

### 4.2 Conclusion and logic

1. **Validity.** Valid. Unit: the throw was reached at exactly the formula's leaf for three widths, and the limit's value was read at run time [observed: `PARAMS` and `RESULT` lines]. Cluster: the Byteman rule saw every segment write [observed: `wcs.txt`; values per index equal to the rebuild's], the buffer settings were 1024 MiB except C32 [observed: stage-4 yaml lines in `cmdlog-head.txt`; peak buffer 1024 MiB / 32 MiB]; no daemon left [observed: `daemons left (this run root): 0`].
2. **Readings.** Pre-registered sub-ranges that missed (`selfcheck.txt`): "retained at the end of run A about 3 to 5 MB" (B = 24: -17,856 bytes, a noise-level reading against a baseline taken before the writer started; B = 16: 2.5 MB), and "retained growth per leaf in [B + 24, B + 80]" (B = 24: 112; B = 1 MiB: 1,047,778; B = 256 KiB: 261,998): the heap-after-GC readings are noisy by about +-4 MB, which is finer than the window at large B and coarser than the retained total at B = 24 [observed]. The controls' per-leaf growth (75 and 73 bytes at B = 24) is inside the window [observed]. Heap sampling of the cluster tier does not separate runs (4 GiB heap full) [observed].
3. **Matched row.** Unit B2g "Run A completes, ratio below 0.1 percent, heap grows with leaf count -> claim confirmed for real widths": ratio 5.46e-4, 48,829 leaves, retained heap rising across the three samples [observed]. "Run B throws at the formula's leaf; run C completes -> mechanism as traced (an array-size guard)": 2048 / 8192 / 524288 exactly [observed]. "Heap at the throw about equal to LIMIT-scale and not lower -> the check does bound the heap of `leafBlockStartValues`, only at the artificial scale": 1.0014 x LIMIT retained at the last sample before the throw [observed]. "Positive control moves while the check's operand stays far below the limit -> usage is governed by other limits": M = 1 against 1024 moves leaves 1024-fold, operand 1.1e-5 against 0.011 of LIMIT [observed]. Cluster B3g row 1 "No `too many nodes` at any row count; sizes grow with rows -> claim confirmed": BALANCED_TREE bytes x 4.00 for 4 x the rows (5M -> 20M) and x 2.00 (20M -> 40M); allocation 27.7 / 110.8 / 221.6 GB (flush + rebuild) for R5 / R20a / R40 [observed]; B3g row 3 (control): the 32 MiB run wrote 1455 + 1454 segments against 89 + 89 at 1024 MiB and held the buffer to 32 MiB against 1024 MiB [observed].
4. **Excluded rows.** "Run A throws": no. "Throw at a count different from the formula": no. "Neither run B throws nor the control moves": no. Cluster: "too many nodes appears": no; "control does not change segment count or heap": no (it did, segments and buffer peak); "plateau in heap or file size unrelated to the buffer": none (sizes are linear in rows) [observed].
5. **Observed vs. inferred.** Inferred: that the segment-write operand stays far below the limit at any real size (the largest observed operand is 5e-6 of LIMIT; reaching the limit needs about 9e10 points per segment at B = 24, M = 1024) [inferred: arithmetic from A3 and the measured 441 to 452 leaves per segment]; that allocation sums stand for usage in the cluster tier (no retained-heap reading; a stated limit) [inferred].
6. **Deviations and gaps.** (a) D1 to D4. (b) Up to six nodes of this session ran at once on `pc32` (the README asks for one run at a time per node); the quantities read (allocated bytes, lengths, segment counts, buffer gauge) do not depend on timing. (c) One run per cell, the 20M arm twice; the repeat agrees with R20a to 0.003 percent (BALANCED_TREE bytes 502,570,250 against 502,584,598). (d) The cluster tier cannot reach the limit; it tests only the no-throw side. (e) At artificial widths the unit tier shows the throw bounds the retained start-value list of one writer at about LIMIT (2 GiB), so the guard is a real ceiling for that list; it is unreachable at real widths.
7. **Core question.** At every real width and size tested the operand `bytesPerValue x numLeaves` stayed at 1e-5 to 5e-4 of the limit (unit A: 5.5e-4 at 50 million points; cluster: at most 5.1e-6 per segment at 40 million rows), usage grew with the rows and with the segment buffer's setting (segment count 175 against 2909 and buffer peak 1024 against 32 MiB), and the check never fired; it fired exactly at `floor(LIMIT / B) + 1` leaves when the width and leaf size were set artificially, bounding that one list at about 2 GiB. So the check does not cap the node's memory or disk in practice; the segment-buffer limit, not this check, moves usage (parts 3 and 4).

**Conclusion (one line):** Unit B2g rows 1, 2, 3 and the control row — confirmed (does not cap in practice; at artificial widths it bounds one writer's start-value list at about LIMIT); Cluster B3g row 1 and row 3 — confirmed (does not cap), with the run-A retained-heap totals and per-leaf windows missed.

## 5. Self-check of run 1 — AI

### 5.1 Check of run 1's conclusion

Re-opened 2026-10-28: `unit/unit.out` and the five `cluster/*/{wcs.txt,readings.txt,segments-*.txt,segbuf.csv}` re-parsed by `harness/.../selfcheck.py` (`run1/selfcheck.txt`: 32 PASS, 5 FAIL; the five FAIL lines are the missed sub-ranges named in 4.2 part 2), and by hand `unit.out` run B lines, `cluster/R40/readings.txt`, `cluster/C32/readings.txt` and `cluster/R5/segments-AFTER_REBUILD.txt`.

| Part | Holds? | Note (file re-read) |
|---|---|---|
| 1. Validity | yes | `PARAMS` LIMIT; `wcs.txt`; `cmdlog-head.txt` yaml lines; `daemons left 0`. |
| 2. Readings | yes | the five FAIL lines; noise discussion matches the sign of the samples in `unit.out`. |
| 3. Matched row | yes | ratios recomputed from `analysis.txt` (tree 4.00 and 2.00 by `components-after-flush.txt` too: 125,644,891; 502,584,598; 1,005,137,334). |
| 4. Excluded rows | yes | no throw outside the artificial runs; control moved. |
| 5. Observed vs. inferred | yes | inferences listed; neither changes a verdict row. |
| 6. Deviations and gaps | yes | D1 to D4 and the shared-node note. |
| 7. Core question — the steps follow the audited logic | yes | formula throw -> real widths far below -> cluster no throw, linear growth -> buffer control moves. |

### 5.2 Run 2?

**No** (2026-10-28). The throw counts are exact and repeat in three fresh JVMs, the cluster ratios are 2- to 4-fold effects with 0.003 percent repeat noise on the tree bytes, and the misses are about the heap probe's resolution.

## 6. Run 2 — fresh AI session (optional)

Not done.

## 8. Verdict — AI

**Stage-3 estimate:** negative. **Outcome class:** true negative (negative, does not cap in practice): the check is an array-size overflow guard; it bounds one writer's start-value list at about 2 GiB only at widths and leaf sizes no real column reaches. (If the 2 GiB ceiling at artificial widths were read as a cap, the class would be false negative; this results file reads the claim as the case file states it, "in practice".)

**Claim tested (B1):** the check at `BlockBalancedTreeWriter.java:651` does not bound the heap or disk a node uses for numeric SAI writes: for every real numeric type and the default leaf size it is never reached, while heap use follows the number of leaves and the segment buffer; it only fires when `bytesPerValue * numLeaves` is made to approach `ArrayUtil.MAX_ARRAY_LENGTH` artificially, and then it is an array-size guard.

| Tier | Verdict (B2g / B3g row) | Effect on the constraint | Basis | Date |
|---|---|---|---|---|
| Unit | Confirmed (B2g: run A completes at 5.5e-4 of LIMIT; run B throws at the formula's leaf, run C completes; heap at the throw about LIMIT; control moves leaf count 1024-fold); retained-heap total and per-leaf windows missed | does not cap (in practice) | run 1 + self-check | 2026-10-28 |
| Cluster | Confirmed (B3g row 1: no throw, sizes linear in rows; control: segments 175 -> 2909 and buffer peak 1024 -> 32 MiB) | does not cap | run 1 + self-check | 2026-10-28 |

**Positive control:** `segment_write_buffer_size` 32 MiB against 1024 MiB at 20M rows: rebuild segments 89 + 89 -> 1455 + 1454, peak buffer 1,073,744,148 -> 33,557,052 bytes while the check's operand stayed at 5e-6 of the limit; and the unit pair M = 1024 vs M = 1 (leaf count x 1024). Neither is a closed Confirmed case; the buffer limiter binds on the rebuild path, not on the flush path.

**Feedback filed:** the case file's section D updated (no commit by this session); amendments U1-U4 and C1-C2 dated 2026-10-28, made at the audit before any reading.

