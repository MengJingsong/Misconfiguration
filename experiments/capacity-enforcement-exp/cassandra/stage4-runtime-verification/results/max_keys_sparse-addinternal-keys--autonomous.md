# max_keys_sparse-addinternal-keys--autonomous — stage-4 results  <!-- file: results/max_keys_sparse-addinternal-keys--autonomous.md -->

> **Case:** [`max_keys_sparse-addinternal-keys--autonomous`](../../stage3-ai-deep-read/cases/max_keys_sparse-addinternal-keys--autonomous.md)
>
> **Status:** verdict filed 2026-10-28 — unit and cluster Confirmed (does not cap); no run 2
>
> **Outcome class:** true negative (stage-3 estimate `negative`, stage-4 effect `does not cap`)
>
> **Agent:** autonomous. "§9a" below means B2f/B2g (unit) and B3f/B3g (cluster); the feedback section is section D.

## 1. Before run 1 — design audit and freeze

| Field | Content |
|---|---|
| **Case-file version** | sha256 after the audit's amendments, taken before any reading: `21670e2e04cfdd22ae1f46fe7dd2349d6a7769d88b08b16b4d83f8b2ccb8f602`. File committed at `b68711e5` (HEAD); the amendments of 2026-10-28 are uncommitted. After run 1, section D (stage-4 feedback) was filled; claim, predictions and rows unchanged: final sha256 `c18c2ded3787ffd6aaaaddd9b4dbf376ada8ea3b3b99630b16dfd7e1a6e1c53f`. |
| **Harness** | `harness/max_keys_sparse-addinternal-keys--autonomous/` (uncommitted; README there) |
| **Tiers and values** | Unit: SPARSE and PREFIX, K = 1, 4, 5, 6, 7, 50 at T = 10 000 and K = 1000 at T = 500; T = 20 000 at K = 4, 6; positive control (8 MiB segmenting rule, T = 20 000 / 40 000 / 80 000). Cluster: one node, N = 60 000 rows, K = 5, 6, 1000, SPARSE and PREFIX tables, plus the `max_compaction_flush_memory_in_mb` 1 vs 64 control. |
| **Audit bottom line** | **Ready after amendments** — 2026-10-28 |

### 1.1 Design audit

| Group | Check | Rating | Note |
|---|---|---|---|
| A | quantity is memory or disk bytes | Met | `OnDiskIndexBuilder` estimated heap bytes and index-file bytes (A2, B2d). |
| A | knob varied (>= 3 values) or other approach | Partly -> Met | The constant is hard-coded (A1). K (keys per term) is the dose, 7 values straddling 5 (B2b); the constant itself cannot change without a rebuild, and the file says so. Amended: the K = 1000 cell uses T = 500 (the T = 10 000 cell is 10^7 adds, about 1.1 GB of estimate, more than `-Xmx512m`). |
| A | real resource measured, not only the counter | Partly | Unit tier: `estimatedMemoryUse()` is a hard-coded formula (the file says so); amended to add exact thread-allocated bytes and the file length. Cluster: whole-node heap is coarse (amended: Byteman reads the builder estimate at every build). Gap stays named. |
| A | driven to the limit and past it | Met | K = 5 (at) and K = 6, 7, 50, 1000 (past) in both tiers. |
| A | positive control (negative claim) | Met | B2h segmenting rule at 8 MiB and B3h `max_compaction_flush_memory_in_mb` 1 vs 64 (a known-binding cap on the same builder memory); amended with numeric predictions. |
| B | steps establish; numeric prediction; rows for every outcome; disallow evidence | Met after amendment | B2f gave formulas (checked: first-term 64+48+4 = 116, per add 108, `OnDiskIndexBuilder.java:182,194`); amended: control numbers and the cluster estimate per K. Disallow evidence = line-599 message in both tiers. |
| B | alternatives and controls | Met | PREFIX mode control, K = 5 accept path, flush-threshold control, repeats. |
| C | human / AI can follow; values exact | Partly -> Met | Amended: constructor argument order (`keyComparator`, `comparator`, mode), `daemonInitialization`, one table per K, log text for the flush path. |
| D | harness exists | Met (listed) | Written in step 1: JUnit probe, run script, node maker, Byteman rule, workload, checker. |
| D | workload reaches the limit | Met | Unit: seconds. Cluster: 60 000 small rows, < 100 MB. 52 GB free on `pc41`. |
| D | citations | Met after correction | `OnDiskIndexBuilder.java:575,596,598-600,182,194,199-202,270,316-318`, `PerSSTableIndexWriter.java:247,268-271,295,327,365-368`, `IndexMode.java:58,185-194`, `DynamicTokenTreeBuilder.java:103` match the pinned source. A3 step 5 says a failed flush build logs "Failed to build index segment" (270); the file's B3d also listed "Failed to flush index" (327), which is the merge path only (amended). A line-number slip of the amendment itself (274 for 276) was fixed before any run. |

| # | Recommendation | Applied? | Why |
|---|---|---|---|
| R1 | Fit the K = 1000 cell in the heap (T = 500), constructor argument order, test bootstrap | Applied (B2c amendment 2026-10-28) | Group C/D |
| R2 | Numeric positive control (segments = floor(E / 8 MiB) +-1) | Applied (B2g amendment) | Group A/B |
| R3 | Cluster: exact builder estimate from Byteman, one table per K, failing-build log text, partial-file note, control segments evidence | Applied (B3e/B3g amendments) | Group A/B/C |
| R4 | In SPARSE mode the base SSTable is unaffected (A3 step 5 says "not verified") | Left for stage 3; the cluster tier reads the SSTable after the failed index build | Understanding |

## 2. Environment

| Field | Run 1 |
|---|---|
| Date | 2026-10-28 (unit 17:47 MDT; cluster node start 17:58 MDT, finished about 18:07 MDT) |
| Node | `pc41` (`node4.jason92-321705.misconfiguration-pg0.cloudlab.umass.edu`) |
| OS / kernel | Ubuntu 22.04, `5.15.0-198-generic` |
| JDK / Ant | OpenJDK 11.0.32.1 / Apache Ant 1.10.12 |
| Local source | `~/s4-b34/src` (`copy-source.sh` of `cassandra/cassandra-5.0.9/` at repository commit `b68711e5`, `ant build-test` 1 min 10 s; the copy is shared with the two sibling cases and was never edited except for the copied probe test classes) |
| Case-file / harness commit | `b68711e5` with the uncommitted amendments (sha256 in §1) / uncommitted |
| Node data | local disk `~/stage4-tmp/b34/mks/node` (recreated at each node start; `/` had 52 GB free) |
| Full logs | `pc41:~/s4-b34/logs/max_keys_sparse/run1/` (`unit/`, `cluster/main/`, `selfcheck.out`); earlier attempts beside it (`attempt0-…`, `attempt1-…`, `attempt2-…`) |

**Attempts before the run 1 recorded here** (all after the freeze; none edited the case file; the readings they produced were visible to the session, which is disclosed here because it could in principle tune later wording): attempt 0, unit tier: `ant testsome` failed to start the JVM ("Multiple garbage collectors selected": B2a's `-XX:+UseSerialGC` conflicts with the CMS flag in `build.xml`'s test JVM) — defect 1. Attempt 1, unit tier: ran completely, its numbers equal run 1's; one of the harness's own sanity checks (a total-estimate conservation check that ignored that a term split across two segments is charged again) was wrong — defect 2, fixed in the probe, then the unit tier was run again as run 1. Attempt 2, cluster tier: ran completely and showed the same failures and index files as run 1, but the Byteman rule did not match (`finish(sstable.Descriptor, File)` is really `finish(sasi.disk.Descriptor, File)`), so there was no builder-estimate line — defect 3, fixed and parse-checked with `org.jboss.byteman.check.TestScript`, a fail-fast check added to the script, then the cluster tier was run again as run 1.

## 3. Runbook defects

| # | Run | Step | Problem | Fix | Decision | Case-file commit |
|---|---|---|---|---|---|---|
| 1 | attempt 0 | B2a | `-XX:+UseSerialGC` with `ant testsome` aborts the JVM: the test JVM already selects CMS | the probe runs with the build's GC (`-Xmx512m -Xms512m` only); the allocation instrument (thread-allocated bytes) does not depend on the GC | harness-only; B2a's GC flag was for quieter heap deltas, which the exact instrument replaces | none |
| 2 | attempt 1 | harness | own conservation check wrong (see §2) | check changed to `E <= sum + remainder <= E + 116 x closed` | harness-only | none |
| 3 | attempt 2 | B3d amendment (iii) | Byteman rule named the wrong `Descriptor` class | corrected; fail-fast added | harness-only | none |
| 4 | run 1 | B3g (c) / amendment (v) numbers | the positive-control numbers (7 +-1 closed segments, about 8 "Flushed index segment" lines for 1 MiB) were derived as if a term is charged once per builder; in a compaction the rows arrive in token order, not term order, so nearly every add opens a new term in its segment (116 B again) | none: a frozen prediction is not edited; the miss is recorded in §4.2 and the case-file feedback | prediction missed, qualitative row met | none |
| 5 | run 1 | log reading | the node's `system.log` rolled at UTC midnight during the run (zip archive); the K = 6 failure lines were in the archive | the archive was copied to the run directory and the checker reads `system.log`, the archive and `stdout.txt` | harness-only | none |

## 4. Run 1

**Scope:** unit tier (54 cells + 3 control volumes, one JVM); cluster tier (one node start, six index builds + two control tables). **Command log:** `max_keys_sparse-addinternal-keys--autonomous/run1/` (`unit/summary.txt`, `unit/test.out`, `cluster/main/readings.txt`, `cluster/main/mks-build-lines.txt`, `cluster/main/fail-and-segment-lines.txt`, `cluster/main/datalist.txt`); checker `harness/max_keys_sparse-addinternal-keys--autonomous/selfcheck.py`, output `run1/selfcheck.out` (44 PASS, 0 FAIL).

### 4.1 Readings

**Unit tier** (`run1/unit/test.out`; identical `est` and outcome in the 3 repetitions; probe 2 tests and upstream `OnDiskIndexTest` 12 tests pass):

| Mode, K, T | `estimatedMemoryUse()` = T*116 + T*K*108 | finish | PREFIX / SPARSE file length |
|---|---|---|---|
| SPARSE and PREFIX, K=1, T=10 000 | 2 240 000 | both ok | SPARSE 315 728 / PREFIX 999 668 |
| K=4 | 5 480 000 | both ok | 811 832 / 1 458 428 |
| K=5 | 6 560 000 | both ok | 959 432 / 1 573 116 |
| K=6 | 7 640 000 | **SPARSE: `FSWriteError`, "Term - '0' belongs to more than 5 keys in SPARSE mode"** (stub file 35 B); PREFIX ok | PREFIX 1 773 812 |
| K=7 | 8 720 000 | SPARSE fails (same message); PREFIX ok | PREFIX 1 888 500 |
| K=50 | 55 160 000 | SPARSE fails; PREFIX ok | PREFIX 8 839 412 |
| K=1000, T=500 | 54 058 000 | SPARSE fails; PREFIX ok | PREFIX 14 360 620 |
| K=4 / K=6, T=20 000 | 10 960 000 / 15 280 000 (exactly 2 x the T=10 000 cell) | K=4 ok; K=6 SPARSE fails | PREFIX 2 900 436 / 3 543 500 |

Thread-allocated bytes of the add loop are linear in K (168 B per extra key per term, from K=4 to 7) and equal for SPARSE and PREFIX (+-2 %). Control (8 MiB rule, PREFIX, K=6, 764 estimated bytes per term): T = 20 000 / 40 000 / 80 000 closes 1 / 3 / 7 segments (floor(E / 8 MiB) = 1 / 3 / 7), every closed builder's estimate is 8 388 612 to 8 388 620, the largest estimate seen is 8 388 620 (<= 8 MiB + 223) [observed: `unit/summary.txt`].

**Cluster tier** (`run1/cluster/main/readings.txt`; N = 60 000 rows per table, 0 insert errors; `est` = the builder's own counter read by Byteman at the build):

| Table | Terms | Byteman est | Result | Index file | Base SSTable Data.db | `count(*)` / `WHERE v = 3` | Heap max (kB, 1 Hz) |
|---|---|---|---|---|---|---|---|
| `t_sparse_k5` | 12 000 | 7 872 000 | ok | 4 424 840 B | 882 854 B | 60 000 / 5 rows | 484 756 |
| `t_prefix_k5` | 12 000 | 7 872 000 | ok | 1 880 356 B | 893 057 B | 60 000 / 5 | 578 167 |
| `t_sparse_k6` | 10 000 | 7 640 000 | **"Failed to build index segment", cause "Term - '0' belongs to more than 5 keys in SPARSE mode"** | stub, 39 B | 888 968 B | 60 000 / 0 rows | 642 725 |
| `t_prefix_k6` | 10 000 | 7 640 000 | ok | 1 773 812 B | 888 699 B | 60 000 / 6 | 643 471 |
| `t_sparse_k1000` | 60 | 6 486 960 | **fails (same cause)** | stub, 39 B | 829 706 B | 60 000 / 0 | 609 236 |
| `t_prefix_k1000` | 60 | 6 486 960 | ok | 1 732 632 B | 830 158 B | 60 000 / 1000 | 676 936 |

Positive control (PREFIX, K=6, 60 000 rows in two flushes, then `nodetool compact`): `max_compaction_flush_memory_in_mb` = 1: 12 "Flushed index segment" lines, 12 compaction builds of estimate 1 048 592 to 1 048 796 (11 closed) and a last one of 584 428; = 64: 0 segment lines, one build of 7 640 000. The two memtable-flush builds (3 820 000 each, 1 GiB threshold) are the same in both.

### 4.2 Conclusion and logic

1. **Validity.** The limit was reached in both tiers: K = 6, 7, 50 and 1000 exceed 5 and the SPARSE builds failed with the line-599 message [observed: `unit/test.out`, `cluster/main/fail-and-segment-lines.txt`, the archived `system.log`]. "Hold fixed": N = 60 000 rows per table, one flush each with all rows in the memtable (the Byteman builds show exactly 12 000 / 10 000 / 60 terms and one build per table) [observed: `mks-build-lines.txt`]; `sasi_indexes_enabled: true` and a 1 GiB G1 heap [observed: `cluster/main/extra.yaml`, `jvm-extra.txt`; `proc args` in `stdout.txt`]. The positive control moved (below). Valid.
2. **Readings.** (a) The SPARSE builder's estimate at K = 6 and 1000 is exactly the same as PREFIX's, so the failing build had used its full estimated memory before it failed [observed]. (b) After the failed SPARSE build the base SSTable is intact and full-size, the index file is a 39-byte stub, and `WHERE v = 3` returns no rows although PREFIX returns the K matching rows [observed: `readings.txt`]. (c) Heap maxima (484 to 677 MB of a 1 GiB heap) do not follow K or mode; G1 garbage between samples dominates an 8 MB builder, so the heap leg is not diagnostic (the exact leg is the Byteman estimate) [observed; the 1 Hz sampler cannot isolate an 8 MB object]. (d) The control's numeric prediction was missed: 12 segment lines against the frozen "about 8 (7 +-1 closed + remainder)" (defect 4); the qualitative row holds. (e) The K = 6 failure lines are in the archived log (defect 5).
3. **Matched row.** Unit B2g row 1, "(a) linear in T and K across 5; SPARSE fails at K >= 6 only; PREFIX with same K succeeds and its usage keeps growing": estimate = T*116 + T*K*108 in all 54 cells with a constant 1 080 000 step per extra key at T = 10 000 across 4 -> 5 -> 6 -> 7; SPARSE fails exactly at K >= 6 with the line-599 message (all reps); PREFIX succeeds everywhere and its file length keeps growing with K [observed: `selfcheck.out`]. Cluster B3g row 1, "SPARSE fails only for K >= 6 with the line-599 message; PREFIX unaffected; heap peaks track N not K": SPARSE K = 5 ok, K = 6 and 1000 fail with the message, PREFIX ok at all three; the builder estimate equals terms*116 + 60 000*108 for every table and is equal between modes; no step in any reading at 5 -> 6 other than the pass/fail (the heap leg being non-diagnostic, point 2c) [observed]. Cluster B3g control row, "smaller `max_compaction_flush_memory_in_mb` gives more segments / lower per-segment size": 12 segment lines of about 1.05 MB against 0 and one 7.64 MB build [observed].
4. **Excluded rows.** B2g "SPARSE succeeds at K = 6 or 7": it threw at both in every rep [observed]. "(a) or file length stops growing or is capped above 5 in SPARSE": the estimate and (for PREFIX) the file kept growing; the SPARSE file length above 5 is a stub, not a capped value (pass/fail, not a limit) [observed]. "SPARSE fails with a different cause": the cause message is the line-599 text in every failing cell [observed]. "Positive control does not move usage": it moved (1 / 3 / 7 closed segments with volume, each builder <= 8 MiB + 223) [observed]. B3g "heap or disk for SPARSE changes shape exactly at K = 6 in a way that is bounded (not a failure)": the change at K = 6 is the failure itself; the estimate did not change shape [observed]. "SPARSE succeeds at K = 6": it did not. "Positive control shows no change": 12 versus 0. "No flush / limit never reached": all flushes ran and K reached 1000. No Refuted row applies.
5. **Observed vs. inferred.** Inferred: that the 12-segment compaction is explained by token-order arrival and per-segment term overhead **[inferred: a 40-line simulation after the run, 60 000 ids in random order, term = id // 6, 116 B on first sight of a term in a segment and 108 B per add, closing at 1 MiB, gives 11 closed segments and a remainder near 0.59 MB in three shuffles; observed 11 closed and 584 428; not part of the verdict]**; that `estimatedMemoryUse()` tracks real memory **[inferred: the file says the counter is a hard-coded formula; the unit tier's exact thread-allocated bytes are linear in K with the same slope in both modes, which supports it]**.
6. **Deviations and gaps.** The heap leg of B3 is weak (point 2c); real builder memory in the node was not isolated (Byteman reads the counter, not an object size). One run per tier (the unit tier has 3 repetitions per cell). The numeric positive-control prediction was missed (point 2d; frozen text not edited). The merge path (`CombinedTermIterator` producing > 5 keys per term from segments each <= 5, A3 "Bypass or overshoot") was not exercised, as no case row requires it. Whether the base SSTable is "otherwise written" was read: it is (Data.db 888 968 B, `count(*)` 60 000).
7. **Core question.** Usage did not follow the constraint: the builder's memory (counter) and the allocated bytes grew linearly with the number of adds on both sides of 5 and were the same in SPARSE and PREFIX, up to and including the build that then failed; the only effect of crossing 5 is that the SPARSE build throws (index absent, 39-byte stub) while the base data is unaffected. What bounds the builder's memory is the flush threshold (control: 1 MiB option gives 12 segments, 64 MiB none). So `MAX_KEYS_SPARSE` is a validity limit, not a cap on memory or disk used by indexing.

**Conclusion (one line):** unit B2g row 1 and cluster B3g row 1 (with the control row met qualitatively, numerically missed) — Confirmed (does not cap; positive control moved).

## 5. Self-check of run 1 — AI

### 5.1 Check of run 1's conclusion

`harness/.../selfcheck.py` re-parses `unit/test.out`, `cluster/main/stdout.txt` (the Byteman lines), `system.log` with its archive, and `datalist.txt` and re-tests every number of 4.1 (recomputing the formulas): 44 PASS, 0 FAIL (`run1/selfcheck.out`). It does not read the run script's own readings for those checks. Two of its checks were rewritten after the first look at the data because the first versions were wrong about the harness, not about the case (the per-add allocation is not constant because the term overhead amortises; the log reader missed the rolled archive); the case's frozen predictions were not touched.

| Part | Holds? | Note |
|---|---|---|
| 1. Validity | yes | one build per table with the expected term counts; the failing messages are in `stdout.txt` and the archive. |
| 2. Readings | yes | (c) and (d) are flagged in the conclusion, not hidden. |
| 3. Matched row | yes | formulas recomputed; K=5 -> 6 step equals K=4 -> 5 step. |
| 4. Excluded rows | yes | same script. |
| 5. Observed vs. inferred | yes | the token-order explanation is inferred and is not used by the verdict. |
| 6. Deviations and gaps | yes | listed above and in §3. |
| 7. Core question | yes | follows B1: usage per entry has the same shape on both sides of 5; the failure is a validity rule. |

### 5.2 Run 2?

No — 2026-10-28. The unit tier is exact and repeated 3 times; the cluster verdict rests on exact Byteman counters and log lines; the inferred statements do not carry the verdict.

## 6. Run 2 — optional

Not done.

## 7. Comparison

Not done.

## 8. Verdict — AI

**Stage-3 estimate:** negative. **Outcome class:** true negative.

**Claim tested (B1):** raising the number of keys per term across 5 does not change how much memory or disk the SASI index builder uses per entry (usage grows linearly with the amount indexed on both sides of 5); the only effect of crossing 5 in SPARSE mode is that the build of that index fails; usage is bounded by the flush threshold, a different cap.

| Tier | Verdict (B2g / B3g row) | Effect on the constraint | Basis | Date |
|---|---|---|---|---|
| Unit | Confirmed (row 1: estimate linear in T and K across 5, SPARSE fails only at K >= 6, PREFIX succeeds and keeps growing; control moved) | does not cap | run 1 + self-check | 2026-10-28 |
| Cluster | Confirmed (row 1: SPARSE fails only at K >= 6 with the line-599 message, PREFIX unaffected, builder estimate identical between modes; heap leg non-diagnostic; control row met qualitatively, numeric prediction missed) | does not cap | run 1 + self-check | 2026-10-28 |

**Positive control:** unit: the 8 MiB segmenting rule closes 1 / 3 / 7 segments for 15.3 / 30.6 / 61.1 MB of estimate and no builder exceeds 8 MiB + 223 B (a cap that binds on builder memory); cluster: `max_compaction_flush_memory_in_mb` = 1 made a compaction build 12 index segments of about 1.05 MB where 64 built one of 7.64 MB.

**Feedback filed:** section D of the case file (uncommitted); the audit's amendments (B2c, B2g, B3e, B3g; 2026-10-28, uncommitted) are in the case file; the final sha256 is in §1 and in the final report; `_INDEX.md` is for the orchestrator.
