# sasi-max_term_size-PerSSTableIndexWriter-addTerm-termSize--autonomous — stage-4 results  <!-- file: results/sasi-max_term_size-PerSSTableIndexWriter-addTerm-termSize--autonomous.md; the stem ends in --guided or --autonomous -->

> **Case:** [`sasi-max_term_size-PerSSTableIndexWriter-addTerm-termSize--autonomous`](../../stage3-ai-deep-read/cases/sasi-max_term_size-PerSSTableIndexWriter-addTerm-termSize--autonomous.md)
>
> **Status:** self-checked; verdict filed (2026-10-26)
>
> **Outcome class:** true negative — the stage-3 estimate (negative) against the effect found below (does not cap) ([definition](../README.md#outcome-class))
>
> **Agent:** guided / autonomous (the suffix of the case-file stem). For an autonomous
> file, "§9a" below means each tier's predictions and conclusions table: B2f and B2g
> (unit), B3f and B3g (cluster); "§9b–§9e" means B2a–B2e or B3a–B3e; and the case
> file's feedback section is its section D, not §10. One results file per case file.

**Relative links in this template** are written for where a *copy* of it lives
— inside `results/` — not for the template's own location one level up.

**Fill the sections in order.** The audit (§1), run 1 (§4) and the self-check
(§5) are required; run 2 (§6) and the comparison (§7) are filled only if §5.2
chooses run 2. No step waits for a human.
The protocol behind each section is in
[`../README.md`](../README.md#the-run-protocol).

## 1. Before run 1 — design audit and freeze

| Field | Content |
|---|---|
| **Case-file version** | Case file untracked at audit time (committed by the orchestrator). Original sha256 (as filed): `aa39c5d0159925305b2b104d937aa52a83da80e1cb24e8607d3713ce0dc6449e`. **After the audit's amendments (B5, 2026-10-25), frozen version:** `933b47c4085a8a82f7ac2dc91edec5b3244023a321fbffacdf89d1aff3c9bc85`. Frozen tables, hashed before any reading of this case: B2f-g (text from `**B2f.` to before `**B2h.`, UTF-8) sha256 `2caeb8c4716c44dd062706186279be3ff0edb0a43cc6505c7dbcc11ba57424c6`; B3f-g (from `**B3f.` to before `**B3h.`) sha256 `1b9745ea643ed17939f2f7a163ad9d911e7fd681ccbc45ca60d80bbb2d1fe543`. **Final sha256 after the section D feedback (2026-10-26):** `305559f84e73406481c604e43cfe39d5954a2d037e0238d80accd74d7b81084d` (B2f-g and B3f-g hashes re-computed unchanged). |
| **Harness** | `harness/sasi-max_term_size-PerSSTableIndexWriter-addTerm-termSize--autonomous/` (written before run 1; committed by the orchestrator) |
| **Tiers and values** | Unit: writer path (`PerSSTableIndexWriter.Index.add`, COMPACTION) at S = 1022/1023/1024/1025, N = 1k/10k/100k; cap option 1/8/default; FLUSH reference; tokenized 1 MiB value. Cluster: labels `m` (default option, a=1023 B and b=1024 B, 100k then 400k rows), `c1`, `c16` (option 1 and 16 on a, 400k rows), `tc` (tokenized, 2,000 and 8,000 rows). |
| **Audit bottom line** | **Ready after amendments** — 2026-10-25 |

### 1.1 Design audit

| Group | Check | Rating (Met / Partly / Not met) | Note (section checked) |
|---|---|---|---|
| A. Core question | constrained quantity is memory or disk bytes | Met | A2/B1: builder estimate (heap bytes) and `SI_*.db` bytes (disk); estimate formula `OnDiskIndexBuilder.java:182,194` re-read. |
| A. Core question | knob varied, ≥ 3 values incl. default — or another approach, with the reason | Met | A1: constant, not settable; B2b/B3b vary the term size around 1024 (1022-1025; 1023 vs 1024 vs tokenized) and use `max_compaction_flush_memory_in_mb` as the control; B5.9 added a third control value (1/16/default) for the cluster. |
| A. Core question | real resource measured, not only the counter (gap named) | Partly | Disk bytes are real (`SI_*.db` sizes). Heap: unit after-GC delta and live `DynamicTokenTreeBuilder` counts are indicative; the estimate is a jol-derived counter (B2d, B3d name the gap). |
| A. Core question | usage driven to the limit and past it | Met | S=1023 (at) and 1024-1025 (past); caps reached: 844 terms for 1 MiB (B5.2). The 1 GiB flush cap (863,831 terms) is not reached and is not used (B5.10). |
| B. Logic | each step says what it establishes | Met | B2e/B3e steps map to B2g/B3g rows. |
| B. Logic | prediction stated in numbers or a clear relation | Partly -> Met | Old B2f "about 118/15/0" and B3f "1.0-1.3 KB per row" were approximate or wrong (B5.3, B5.6); rewritten with exact formulas before freeze. |
| B. Logic | every plausible outcome has a conclusions row with its evidence | Partly -> Met | Rows for tokenized path and for count mismatch added (B2g, B3g). Rows exist for plateau (refuted), S=1024 accepted, control flat. |
| B. Logic | confirmation needs ceiling-follows-knob and direct disallow evidence | Met | Disallow: rejection lines plus zero-length file at 1024; follows-knob side is the control moving (segment cuts) and growth with N. |
| B. Logic | alternative explanations and their controls | Met | B2h/B3h: S=1024 boundary, FLUSH reference, baseline; heap not used as the decisive reading. |
| B. Logic | positive control for a negative estimate | Met | The cap option moves cut counts (formula-predicted). Same workload and instruments. |
| C. Specific | a human can follow it from the intro and §9a | Met | Header table, A3, B1. |
| C. Specific | an AI can run B2a-B2e / B3a-B3e without re-deriving the code path | Partly | Writer construction not given (`ColumnIndex`, `Descriptor`, `PerSSTableIndexWriter` constructors); the harness supplies it. |
| C. Specific | knob, values, workload, commands, observables, sampling, stop conditions exact | Partly -> Met | Tokenized value, rows, label list, autocompaction off and commands made exact by B5.5, B5.8-B5.10. |
| D. Runnable | harness and environment prerequisites exist or are listed | Met | None exist; listed as step-1 work. |
| D. Runnable | workload arithmetic reaches the limit (data, time, disk, memory) | Partly -> Met | Wrong: 860 terms (is 844), "100-130 MB at 100k" (a lower bound only), column c at 400k rows (280 M postings), CONTAINS (52 GB); fixed (B5.2, B5.6-B5.8). Disk: ~1.4 GB per 400k-row `a` index plus compaction copy, 37 GB free. |
| D. Runnable | load-bearing citations spot-checked against the pinned source | Met | Re-read all: `PerSSTableIndexWriter.java:63-74,121,205-251,254-279,281-347,365-369`, `OnDiskIndexBuilder.java:127-128,143,159,165-197,238-246`, `IndexMode.java:58-60,186-194`, `TrieMemIndex.java:84-92,116-137`, `StandardAnalyzer.java:210`, `ColumnIndex.java:64,80,116`, `Config.java:606`, `conf/cassandra.yaml:1992`, `SASIIndexTest.java:1453-1481`. One wrong cite (`IndexMode.java:60-61`, is `:59-60`). |

| # | Recommendation | Applied? | Why |
|---|---|---|---|
| 1 | Cite `IndexMode.java:59-60` | Applied 2026-10-25 (B5.1) | line 61 blank |
| 2 | Cap thresholds 844 / 6,749 / 13,498 / 129,575 / 863,831 terms | Applied (B5.2) | 1243 B per term |
| 3 | Exact cut counts: floor(N/Cmin) (+1 line for the leftover) | Applied (B5.3) | `:247-250`, `:300-304` |
| 4 | Empty index gives a zero-length file | Applied (B5.4) | `OnDiskIndexBuilder.java:241-246` |
| 5 | Exact tokenized arm, estimate 29,753,344 | Applied (B5.5) | one key, 227 B per new word |
| 6 | Per-row bytes become lower bound and ratio | Applied (B5.6) | 4 KiB blocks |
| 7 | PREFIX only | Applied (B5.7) | CONTAINS needs ~52 GB |
| 8 | Column c in its own table, 2,000 and 8,000 rows | Applied (B5.8) | 280 M postings at 400k rows |
| 9 | Third control value (16 MB) | Applied (B5.9) | group A: three values |
| 10 | Autocompaction off; compaction-window segment lines; 2 GiB heap | Applied (B5.10) | clean attribution |
| 11 | Message at `OnDiskIndexBuilder.java:171` prints `Short.MAX_VALUE` | left for stage 3 | cosmetic |
| 12 | Comment at `PerSSTableIndexWriter.java:367` omits the 0.15 GiB default for compaction | left for stage 3 | cosmetic |

**Agreement criteria** — run 2 not chosen (see 5.2).

## 2. Environment

| Field | Run 1 | Run 2 |
|---|---|---|
| Date | 2026-10-26 UTC (unit 02:18-02:31, cluster 02:32-02:44); the session was interrupted by an API rate limit after the cluster tier had finished and resumed afterwards; no run was cut | not done |
| Node | `pc07` (`node0.jason92-320876...`), 40 cores, 251 GiB; shared with other agents | |
| OS and kernel | Ubuntu 22.04, `5.15.0-187-generic` | |
| JDK / Ant | OpenJDK 11.0.32.1 / Apache Ant 1.10.12 | |
| Local source copy | `~/s4-pw` by `copy-source.sh` at repository commit `1ae567d` (source clean), `ant build-test` 1 min 11 s; the unit tier (`ant testsome`) ran before any node; the node then ran from the tree with no further `ant` | |
| Case-file commit / harness commit | case file and harness untracked at run time (sha256 in section 1; `unit/harness.md5` lists the harness files); orchestrator commits | |
| Storage for node data | local `/dev/sda3` (36 GB free before; peak data dir 4.1 GB), `~/s4-pw-data/<label>`, removed after each label | |
| Full logs (outside the repo) | `pc07:~/stage4-logs/pw/run1/` (unit, cluster), full gzipped node logs `~/stage4-logs/pw/<label>-system.log.gz`; shakedowns `shake-unit`, `shake-cl-m`, `shake-all` are not readings | |

Ports: JMX 7330, native 9352, storage 7030, loopback 127.0.30.1, checked free with `ss -ltn` before every label (by the script); Byteman 9330 unused. Heap `-Xms2G -Xmx2G` (`node-cmdline.txt`).

## 3. Runbook defects

Audit fixes were applied as amendments B5.1-B5.12 before any reading (section 1). Defects of the harness, found while running:

| # | Run | Step | Problem | Fix | Decision (date) | Case-file commit |
|---|---|---|---|---|---|---|
| 1 | shakedown | `cluster-run.py` stop | children were never reaped, so a zombie kept `/proc/<pid>` and the stop waited 90 s then SIGKILLed; gzip target path wrong; no prefix query for kind `a` | fixed before run 1 (`alive()` with `waitpid`; paths; query) | 2026-10-26 | n/a |
| 2 | self-check | `selfcheck.py` first attempt | matched `OutOfMemoryError` in the JVM argument `HeapDumpOnOutOfMemoryError` and expected a space in the log timestamp (`2026-10-26T02:41:29,584`) | fixed; first output kept in `run1/selfcheck-first-attempt.txt` (7 DO NOT HOLD, all from these two script errors) | 2026-10-26 | n/a |
| 3 | run 1 | `analyze_cluster.py` B3f(4), indicative only | the live `DynamicTokenTreeBuilder` guess "< 2 x Cmin" failed for options 1 and 16 (peaks 11,231 and 78,264): the final merge in `complete()` builds the combined index; B3f(4) says "not a decision row" | recorded, no change | 2026-10-26 | n/a |

## 4. Run 1

**Scope:** unit tier (all arms of `WriterProbeTest`); cluster tier labels `m` (a=1023 B and b=1024 B, 100k then 400k rows, default option), `c1` and `c16` (a only, 400k rows, option 1 and 16), `tc` (tokenized, 2,000 then 8,000 rows). **Command log:** `results/sasi-max_term_size-PerSSTableIndexWriter-addTerm-termSize--autonomous/run1/` (`unit/session.log`, `cluster/<label>/summary.json`, `cluster/all.log`).

### 4.1 Readings

**Unit tier** (`run1/unit/writer-results.csv`, `writer-estimates.csv`; `unit/analysis.txt`: ALL PASS, 19 checks)

| Test or assertion | Result | Evidence (file) |
|---|---|---|
| S=1022 / 1023, N=10,000 | all 10,000 reach the builder, 0 rejections, estimate 12,420,000 / 12,430,000 | `unit/writer-results.csv` rows `boundary` |
| S=1024 / 1025, N=10,000 | 0 reach the builder, 10,000 INFO "Rejecting value (size" lines, 0 ERROR, estimate 0, 0 cuts, file length 0 | same |
| S=1023, N=1k/10k/100k | estimate 1,243,000 / 12,430,000 / 124,300,000; file 3,420,092 / 34,184,312 / 341,748,424 bytes (ratios 10.00) | same, `growth` rows |
| Cap control, N=100k, COMPACTION | option 1: 118 cuts, 119 segment lines, estimate at cuts 1,049,092; option 8: 14 cuts, 15 lines, 8,389,007; default: 0 cuts, 0 lines; final file 341,748,424 for all; N=200k default: 1 cut | `writer-results.csv`, `writer-estimates.csv` (`cap`, `cap200k`) |
| FLUSH source, option 1, N=100k | 0 cuts, 0 lines | `flush` row |
| Tokenized 1,048,576-byte value (131,072 words) | 131,072 reach the builder, 0 rejections, estimate 29,753,344; under option 1: 1 cut, 1 line | `token` rows |
| Heap delta after GC (indicative) | 141,054,712 bytes at S=1023, N=100k (estimate 124,300,000) | `growth` row, `heap_delta_bytes` |

**Cluster tier** (2 GiB heap, PREFIX, autocompaction off; `cluster/analysis.txt`: 30 PASS and the 2 indicative B3f(4) FAILs of defect 3)

| Capacity value | Run | Observable | Reading | Evidence (file) |
|---|---|---|---|---|
| default | m, 100k rows | `*SI_t_a_idx.db` bytes; `*SI_t_b_idx.db` bytes | 341,736,224; 0 | `cluster/m/summary.json` `steps[0]` |
| default | m, 400k rows | same | 1,366,977,664 (ratio 4.00; 3,417 B/row); 0 | `steps[1]` |
| default | m | rejection lines | Can't add term b 100,000 + 300,000; writer-path b 100,000 + 300,000 in load+flush windows and 400,000 in the compaction window; a 0; builder ERROR 0; full log totals 400,000 / 800,000 | `summary.json` `log_*`; full log re-count in `run1/selfcheck.txt` C4 |
| default | m | prefix queries (id 12,345) before and after compaction | a: 1 row; b: 0 rows | `summary.json` `queries_*` |
| default | m | segment lines t_a_idx: flush/load windows; compaction window | 0; 4 | `summary.json` |
| 16 MB | c16, 400k | same | 0; 30 | `cluster/c16/summary.json` |
| 1 MB | c1, 400k | same | 0; 474 | `cluster/c1/summary.json`, `flushed-segment-lines.txt` |
| m, c1, c16 | after `nodetool compact` | `t_a_idx` bytes | 1,366,944,324 in all three | `summary.json` `files_after_compact` |
| default | tc, 2,000 / 8,000 rows | index bytes; rejection lines | 23,348,272 / 91,799,160 (ratio 3.93); 0 / 0 (values 5,120 B each) | `cluster/tc/summary.json` |
| all | peak heap used (indicative) | m 1,929 MiB; c1 1,410; c16 1,412; tc 1,468 | `heap.csv` (in the node logs; peaks in `run1/selfcheck.txt` C3) |
| all | peak live `DynamicTokenTreeBuilder` (indicative) | m 169,188; c1 11,231; c16 78,264 | `cluster/*/compaction-histo.csv` |

### 4.2 Conclusion and logic

1. **Validity** - valid. The limit is reached from both sides: 1023-byte terms accepted and 1024-byte terms rejected in the unit tier and in the cluster, in both copies of the check (writer `:218` and memtable `TrieMemIndex`) [observed: `unit/writer-results.csv`, `cluster/m/summary.json`]. The control cap is reached (474 segment lines at 1 MB) [observed: `cluster/c1/summary.json`]. Hold-fixed settings: heap 2 GiB, PREFIX, ports, autocompaction disabled (`compactionstats` text in `summary.json`; zero segment lines outside the compaction windows) [observed]. The 1 GiB flush cap (863,831 terms) was not reached, by design [observed: 0 flush-time segment lines; inferred: 400,000 x 1,243 < 1 GiB].
2. **Readings** - nothing contradicts another reading. Peak heap and live-builder counts are indicative and are not used (defect 3). The final merge in `complete()` (`:320-323`) is the likely reason for the large live counts [inferred: the counts fall to 0 after the compaction, `compaction-histo.csv`].
3. **Matched row** - Unit B2g rows 1, 3, 4 and the tokenized row; cluster B3g rows 1, 2 and the `tc` row. Unit: estimate steps from N x 1243 at 1023 to exactly 0 at 1024 and grows linearly in N (no plateau, file ratios 10.00) [observed]; the segment count falls as the option rises, 118 / 14 / 0 cuts, equal to floor(N / ceil(cap/1243)) with the estimate at each cut in [cap, cap+1243) [observed]; the tokenized value of 1 MiB is accepted and under option 1 is cut once at an estimate of 28.4 x the cap [observed: estimate; inferred: the multiple, from the default-option arm's equal estimate]. Cluster: a's index 4.00 x larger for 4 x the rows, b zero bytes with 1,200,000 rejection lines, the cap option moves compaction segment lines 474 / 30 / 4 while the final bytes are equal in all three [observed].
4. **Excluded rows** - "plateau independent of N and of the option" (Refuted): a's estimate and bytes grow with N at 1023 [observed]. "S=1024 accepted / source trace wrong": 0 accepted, 0 estimate, zero-byte files in both copies of the check [observed]. "Control did not change segment count / threshold never reached": the counts fell 474 > 30 > 4 and 119 > 15 > 0 [observed]. The "counts differ from floor(N/Cmin)" rows: counts matched exactly [observed].
5. **Observed vs. inferred** - inferred: (a) the byte counts of files and the estimate stand for index memory and disk (the estimate formula is jol-derived; heap deltas 141 MB vs 124 MB are consistent but indicative); (b) the 28.4 x overshoot multiple; (c) est-at-cut = estimate before the cutting add + 1,243 (the cut builder is replaced; formula from `OnDiskIndexBuilder.java:182,194`, confirmed by 118 equal values 1,049,092 = 844 x 1,243).
6. **Deviations and gaps** - CONTAINS not run (B5.7); the tokenized arm is in its own table with 2,000 / 8,000 rows (B5.8); the real heap of the builder was not isolated; the cluster has two row counts only in labels `m` and `tc`; the `tc` compaction produced 4 segment lines at the default option (not a frozen number, recorded).
7. **Core question** - Usage did not follow the constraint. The 1024-byte constant drops one term at or above 1024 bytes; below it the builder's estimate (124.3 MB per 100,000 terms) and the index files (341.7 MB per 100k rows, 1.367 GB per 400k, 192 MB for 8,000 tokenized 5 KB rows) are far above any multiple of 1024 and grow with the data, and a 1 MiB tokenized value passes it entirely. What bounded the builder in the same workload was the separate `maxMemorySize` (segment counts fall with `max_compaction_flush_memory_in_mb`), and it bounds the in-memory builder only: final disk bytes were equal at every option.

**Conclusion (one line):** B2g / B3g "limit is a per-term filter only; usage does not follow it" - Confirmed (does not cap), control moving on segment counts.

## 5. Self-check of run 1 — AI

### 5.1 Check of run 1's conclusion

`harness/sasi-max_term_size-PerSSTableIndexWriter-addTerm-termSize--autonomous/selfcheck.py` re-parses the raw CSV files, `ant.log`, `summary.json` entries, `heap.csv`, `node-cmdline.txt`, the filtered log by timestamp and the full gzipped node log (output `run1/selfcheck.txt`: ALL HOLD; first attempt `run1/selfcheck-first-attempt.txt`, script errors only, section 3 defect 2).

| Part | Holds? | Note (file re-read) |
|---|---|---|
| 1. Validity | yes | `node-cmdline.txt` (-Xms2G -Xmx2G, JMX 7330), no OOM, heap peaks under 2 GiB (C3); 1023 / 1024 boundary re-computed from the CSV (U1). |
| 2. Readings | yes | per-index bytes equal the sum of listed files (C2); estimate formula U2. |
| 3. Matched row | yes | compaction-window segment lines re-counted from the filtered log by timestamp: m 4, c1 474, c16 30, tc 0 (C1); cut counts and estimate at cuts recomputed (U3, U4). |
| 4. Excluded rows | yes | rejection totals from the full log: m 400,000 memtable-path and 800,000 writer-path (b), 0 for a; none in c1, c16, tc (C4). |
| 5. Observed vs. inferred | yes | the listed inferences are stated as such. |
| 6. Deviations and gaps | yes | listed. |
| 7. Core question | yes | the steps follow B1's logic. |

### 5.2 Run 2?

**No** (2026-10-26). Both tiers agree; the claim is negative with a moving control; the decisive readings are exact (estimates equal their formulas, segment counts equal their formulas, zero-byte files, full-log rejection totals).

## 6. Run 2 — fresh AI session (optional)

Not done (section 5.2).

**Scope:** the tiers and capacity values actually run. **Command log:**
`sasi-max_term_size-PerSSTableIndexWriter-addTerm-termSize--autonomous/run2/<file>`.

### 6.1 Readings

**Unit tier**

| Test or assertion | Result | Evidence (file) |
|---|---|---|

**Cluster tier**

| Capacity value | Run (control / A / B / C) | Observable (§9d) | Reading | Evidence (file) |
|---|---|---|---|---|

### 6.2 Matched row

The §9a row these readings match, in one line.

## 7. Comparison — only if run 2 was done

| Observable | Run 1 | Run 2 | Criterion (§1) | Agree? |
|---|---|---|---|---|

**Same §9a row?** yes / no. If no, or if a reading disagrees: the cause, and
how it was resolved (see "Compare and decide" in the README).

## 8. Verdict - AI

**Stage-3 estimate:** negative. **Outcome class:** true negative (negative, does not cap).

**Claim tested:** total SASI index memory (builder estimate) and on-disk size do not follow `MAX_TERM_SIZE`: the 1024-byte limit only decides which individual terms are dropped, and `max_compaction_flush_memory_in_mb` moves the flush point (B1). "Confirmed" means this claim held.

| Tier | Verdict (B2g / B3g row) | Effect on the constraint | Basis | Date |
|---|---|---|---|---|
| Unit | Confirmed (B2g rows 1, 3, 4 and the tokenized row) | does not cap | run 1 + self-check | 2026-10-26 |
| Cluster | Confirmed (B3g rows 1, 2 and the `tc` row) | does not cap | run 1 + self-check | 2026-10-26 |

**Positive control:** the index option `max_compaction_flush_memory_in_mb`: unit 118 / 14 / 0 cuts at 1 MB / 8 MB / default for the same 100,000 adds; cluster 474 / 30 / 4 compaction segment lines at 1 MB / 16 MB / default for the same 400,000 rows, with the final index identical (1,366,944,324 bytes).

**Leftovers:** none running (checked `ps` for CassandraDaemon and HeapSampler of this tree, `ss -ltn` for 7330 / 9352 / 7030 / 9330, after the cluster tier and again after the interruption). Removed: `~/s4-pw-data/*` per label and `unit-tmp`. Kept: `~/s4-pw` (tree with `WriterProbeTest.java` untracked in `test/unit/.../sasi/disk/`, built `build/`), `~/stage4-logs/pw/` (logs, gzipped node logs, shakedowns).

**Feedback filed:** the case file's section D (sha256 `305559f84e73406481c604e43cfe39d5954a2d037e0238d80accd74d7b81084d`) and amendments B5.1-B5.12 in B. Upstream notes (left for stage 3): `OnDiskIndexBuilder.java:171` prints `Short.MAX_VALUE`; the comment at `PerSSTableIndexWriter.java:367` omits the 0.15 GiB compaction default.
