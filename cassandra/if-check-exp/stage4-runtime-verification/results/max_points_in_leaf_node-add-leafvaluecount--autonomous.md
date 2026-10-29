# max_points_in_leaf_node-add-leafvaluecount--autonomous — stage-4 results  <!-- file: results/max_points_in_leaf_node-add-leafvaluecount--autonomous.md -->

> **Case:** [`max_points_in_leaf_node-add-leafvaluecount--autonomous`](../../stage3-ai-deep-read/cases/max_points_in_leaf_node-add-leafvaluecount--autonomous.md)
>
> **Status:** **Self-checked 2026-10-28 — unit Confirmed (does not cap), cluster Confirmed (does not cap); sub-predictions missed: postings-length ratios and spread, per-leaf retained bands, C5 tree/postings spread across variants and variant C's tree ratio; no run 2**
>
> **Outcome class:** true negative — stage-3 estimate `negative` against the stage-4 effect `does not cap` ([definition](../README.md#outcome-class))
>
> **Agent:** autonomous (B2 = unit tier, B3 = cluster tier, feedback = section D).

## 1. Before run 1 — design audit and freeze

| Field | Content |
|---|---|
| **Case-file version** | sha256 of the whole file after the audit's amendments (U/C items, dated 2026-10-28, inserted after the link rule): `b08bf27e6adf865991fd0601d00b90530583bb4f1a689edf1a2ab7cdccc950fb`. Repository HEAD `b68711e5`; case file, harness and results uncommitted. Computed before any reading and unchanged through both tiers (`sha256sum` re-checked 2026-10-28). The frozen text is everything above section D. |
| **Harness** | `harness/max_points_in_leaf_node-add-leafvaluecount--autonomous/` (uncommitted; README lists the files). |
| **Tiers and values** | Unit (B2) and cluster (B3), both run. Capacity values: M in 16/128/1024/8192/65536 (unit); constant 128/1024/16384 (cluster). |
| **Audit bottom line** | **Ready after amendments** — 2026-10-28 |

### 1.1 Design audit

| Group | Check | Rating | Note (section checked) |
|---|---|---|---|
| A | bytes | Met | A2: bytes of the per-writer scratch arrays and per-leaf structures; B1 names heap of one flush and bytes written. |
| A | knob | Partly | Hard-coded; B2b varies M (16..65536) through the `@VisibleForTesting` 4-argument constructor; the cluster tier needs rebuilt variants (C1). Reason stated in A1. |
| A | real resource | Partly | B2d allocation, retained scratch and file lengths; B3d heap and `du`. Thread-allocated bytes are a flow, not a footprint: retained `SCRATCH` and `LEAFPOST` added (U3). |
| A | driven past limit | Met | B2c: every full leaf hits `leafValueCount == maxPointsInLeafNode` (977 to 3907 leaves at the defaults). |
| B | steps | Met | B2e, B3e numbered. |
| B | prediction numbers | Partly | B2f(c) 'few percent' unsupported by the per-leaf `PackedLongValues` builder (`NumericIndexWriter.java:94`); numeric ranges added (U4, C5). |
| B | every outcome has a row | Partly | no row for allocation falling as M rises: added (U4). |
| B | confirmation needs ceiling-follows-knob and disallow evidence | Partly | there is no disallow branch (the check flushes a leaf); N-growth plus non-proportionality to M stands for it (B2g). |
| B | alternative explanations | Partly | noise (repeats), JIT (warm-up), GC (forced GC before reads); the segment-buffer limiter as the binding cap on the build path (C4 control). |
| C | human can follow | Met | A1-A4, B1. |
| C | AI can run without re-deriving | Partly | launcher, paths, writer workload, instruments (U1-U3, C1-C3). |
| C | exact values | Partly | 'say 20 GiB' and the 2 GiB heap replaced (C2); repeat counts (C4). |
| D | harness exists | Partly | written in step 1 (this session). |
| D | workload reaches limit | Met | unit: leaf flush every M values by construction; cluster 8e6 rows -> 7813 leaves at 1024 in one flush with the 8 GiB heap (C2). |
| D | citations spot-checked | Met | `BlockBalancedTreeWriter.java:96,106-112,486-489,505-508,528-532,565-568,630,649-654`; `NumericIndexWriter.java:49,61,64-73,82-101,127-130`: all match 5.0.9 in `cassandra/cassandra-5.0.9`. |

| # | Recommendation | Applied? | Why |
|---|---|---|---|
| R1 | Environment, driver, grid, instruments (U1-U3) | Applied 2026-10-28 | filed paths and runner not runnable here |
| R2 | Replace the 'few percent' claim with pre-registered ranges (U4) | Applied | per-leaf Lucene builder makes allocation fall with M |
| R3 | Control wording (U5) | Applied | no resource-capping control exists for a constant |
| R4 | Cluster: variants by javac overlay, 8 GiB heap, workload, instruments, repeats (C1-C5) | Applied | 2 GiB heap cannot hold 8e6 rows in one memtable |
| R5 | The Estimate/Ground text is left as filed | left for stage 3 | not wrong |

**Pre-run-1 instrument checks** (disclosed; none of them is a reading used in a prediction): see section 3 and the harness README.

**Pre-run-1 instrument checks and shakedowns (disclosed; none edited a prediction):** (1) `javac` of `LeafProbe` and two known-answer cells before the unit tier (M = 1024 and 16, N = 1e5, B = 4): they showed `num_leaves` = ceil(N/M), a `SCRATCH/M` of 47.7 at M = 1024, and `LEAFPOST` of 172.6 and 139.9 bytes per leaf at M = 1024 and 16 — the latter is below the pre-registered 150 to 600 band (e) and was left as filed (the unit tier below reproduces it). (2) Cluster shakedowns, 200,000 rows, one node each, variants B and A, discarded: they exposed that the node runs from the jar, not from `build/classes/main` (the Byteman helper was not found; `make-variants.sh` now updates the jar) and that `system_views.sai_column_indexes` has no `queryable` column (`is_queryable`). Variant A's rule lines showed `M=128`, `num_leaves` = ceil(values/128). No shakedown reading entered a prediction.

## 2. Environment

| Field | Run 1 |
|---|---|
| Date | unit 2026-10-28 (node clock UTC 2026-10-28 23:54 to 2026-10-29 00:22); cluster 2026-10-28 (node clock UTC 2026-10-29 00:05 to 01:03) |
| Node | `pc32` = `node2.jason92-321705.misconfiguration-pg0.cloudlab.umass.edu` (40 cores, 251 GiB); the cluster runs shared the host with the other three cases' runs of this session (see 4.2 part 6) |
| OS and kernel | Ubuntu 22.04.2 LTS, `5.15.0-198-generic` |
| JDK / Ant | openjdk 11.0.32.1 (2026-08-18) / Apache Ant 1.10.12 |
| Local source copy | `~/s4-b34` from `cassandra/cassandra-5.0.9/` at repository commit `b68711e5` (`copy-source.sh`), `ant build-test` BUILD SUCCESSFUL; cluster variants `~/s4-b34-vA/vB/vC`; the variant copies were deleted after the runs (rebuild with the harness `make-variant*.sh`) |
| Case-file / harness commit | uncommitted (working tree of `b68711e5`); case-file sha256 in section 1 |
| Storage for node data | `~/stage4-tmp/b34/c1/<label>` on local `/dev/sda3` (63 GB), removed after each run; unit index files under `~/stage4-tmp/b34/tmp1`; nothing under `/proj` except these excerpts |
| Full logs (outside the repo) | `pc32:~/s4-b34-logs/b1/run1/` (`unit/`, `unit-attempt1-N0-crash/`, `cluster/<label>/` with `heap.csv`, `gc-*.log`, `system.log`, `stdout.txt` excerpts, `segbuf.csv`) |

## 3. Runbook defects

| # | Run | Step | Problem | Fix | Decision (date) |
|---|---|---|---|---|---|
| D1 | unit attempt 1 | B2e, N = 0 cells | `ComponentMetadataMap.get` throws `IllegalArgumentException` ("BALANCED_TREE ComponentMetadata not found") when nothing was written; the three N = 0 cells ended with rc 1 | probe catches it (`LeafProbe.java`); unit tier run again from its beginning; the first attempt's `unit.out` is kept in `run1/unit-attempt1/` | 2026-10-28, claim, prediction and table unchanged |
| D2 | cluster | C2 "memtable of 5 GiB holds 8e6 rows in one flush" | with one flush writer `memtable_cleanup_threshold` defaults to 0.5, so a `MEMTABLE_LIMIT` flush happened at 2.5 GiB (`AUTO_FLUSHES_DURING_LOAD 1` in every 8e6 run, none in the 2e6 runs); the flush path wrote 2 segments, not 1, at N = 8e6 | none made; the readings sum over segments (`leavesSum`, `treeLenSum`); recorded as a deviation | 2026-10-28 |
| D3 | cluster | C4 control | the `SegmentBufferSpaceUsedBytes` JMX poll was added to `cluster-run.py` while the chain ran: runs B2, B8a and A2 have no `segbuf.csv`; the control compares B8b and B8c (1024 MiB) with B8ctl16 | none needed | 2026-10-28 |
| D4 | cluster | C3 workload | `cassandra-stress` writes fewer distinct partitions than `n`: 1,880,146 values for n = 2e6 and about 6.97e6 for n = 8e6 (the same count in every variant of one N) | none; all comparisons use the measured value counts | 2026-10-28 |

## 4. Run 1

**Scope:** every B2 and B3 value of section 1. **Command logs:** `max_points_in_leaf_node-add-leafvaluecount--autonomous/run1/` (`unit/unit.out`, `cluster/<label>/{readings.txt,wcs.txt,analysis.txt,cmdlog-head.txt,...}`, `selfcheck.txt`).

### 4.1 Readings

**Unit tier** (`run1/unit/unit.out`; one JVM per cell; ALLOC = thread-allocated bytes of `writeCompleteSegment`; tree/post = component lengths)

| M \ N (B = 4) | num_leaves (1e5 / 1e6 / 4e6) | ALLOC MB (1e5 / 1e6 / 4e6) | tree bytes (1e6 / 4e6) | postings bytes (1e6 / 4e6) |
|---|---|---|---|---|
| 16 | 6250 / 62500 / 250000 | 143.8 / 1586 / 6981 | 3,079,393 / 12,317,467 | 3,165,278 / 13,552,849 |
| 128 | 782 / 7813 / 31250 | 24.7 / 274.0 / 1206 | 3,098,189 / 12,392,640 | 677,621 / 3,491,893 |
| 1024 | 98 / 977 / 3907 | 11.5 / 126.6 / 552.7 | 2,528,150 / 10,112,734 | 361,986 / 2,194,636 |
| 8192 | 13 / 123 / 489 | 10.7 / 103.4 / 450.0 | 3,017,447 / 12,069,646 | 172,507 / 1,415,640 |
| 65536 | 2 / 16 / 62 | 14.0 / 106.2 / 410.4 | 3,015,909 / 12,063,501 | 170,454 / 698,589 |

| Test or assertion | Result | Evidence |
|---|---|---|
| `num_leaves` | = ceil(N/M) in all 15 grid cells, the 5 B = 16 cells and the repeats; `max_points_in_leaf_node` = M | `unit.out` `CELL` lines |
| `SCRATCH` (retained heap of a held `LeafWriter`) | 4,760 / 9,688 / 49,112 / 364,504 / 2,885,696 bytes for M = 16 ... 65536 (B = 4), i.e. 44 to 48 bytes per M for M >= 1024; with B = 16: 4,968 / 11,240 / 61,416 / 462,824 / 3,672,144 (difference from B = 4 = 12 x M within 1.5 percent); the same at N = 0 (4,760 / 49,112 / 2,887,640 for M = 16 / 1024 / 65536) | `SCRATCH` lines; `Z-M*` cells |
| ALLOC against N | ratio N = 4e6 / N = 1e5: 48.5, 48.8, 47.9, 42.2, 29.3 for the five M | `CELL` `alloc` |
| ALLOC against M (N = 1e6, B = 4) | 1586 / 274 / 126.6 / 103.4 / 106.2 MB: falls as M rises; log-log slope -0.33; ALLOC(16)/ALLOC(1024) = 12.5; ALLOC(65536)/ALLOC(1024) = 0.84 | same |
| tree length | = 40.0 x (4e6 over 1e5) for every M; at N = 1e6 the five M differ by at most 1.23 x | `treeLen` |
| postings length | N ratio 48.4 / 75.4 / 122.0 / 84.8 / 42.0 for M = 16 ... 65536; at N = 1e6 the five M differ by 18.6 x (3.17 MB at M = 16, 0.17 MB at M = 65536) | `postLen` |
| `LEAFPOST` (retained by the real `LeafCallback`, N = 1e6) | 8.77 MB / 1.10 MB / 219 KB / 132 KB / 122 KB: 140 / 141 / 224 / 1072 / 7620 bytes per leaf; at M = 16, N = 4e6 the reading is negative (-53,950,320; attempt 1 -67,342,560): a GC-baseline artefact of the probe | `LEAFPOST` lines |
| repeats (1024, 1e6, 4) x3 | same leaves, tree, postings; ALLOC 126,615,456 / 126,614,400 / 126,614,272 | `unit.out` |
| controls | `new long[k]`: 8,016 and 8,000,016 bytes for k = 1e3 and 1e6; the constructor rejects M = 0 and M = 2,147,483,632 (MAX_ARRAY_LENGTH + 1; MAX_ARRAY_LENGTH = 2,147,483,631) | `REJECT`, `ALLOCCTL` lines |

**Cluster tier** (`run1/cluster/<label>/analysis.txt`, `readings.txt`; flush = `nodetool flush`, rebuild = `nodetool rebuild_index`; sums over all segment writes of the window; 64 stress threads, 8 GiB heap)

| Run | rows | M | flush segs / values / leaves | flush tree + postings bytes | flush ALLOC | rebuild segs / leaves | rebuild tree + postings bytes | rebuild ALLOC |
|---|---|---|---|---|---|---|---|---|
| A2 | 2e6 | 128 | 1 / 1,880,146 / 14,689 | 5,915,653 + 11,260,450 | 1.04 GB | 5 / 14,693 | 6,204,948 + 7,724,107 | 4.67 GB |
| B2 | 2e6 | 1024 | 1 / 1,880,146 / 1,837 | 6,787,147 + 7,311,870 | 0.89 GB | 5 / 1,841 | 7,387,353 + 4,496,379 | 4.40 GB |
| C2 | 2e6 | 16384 | 1 / 1,880,146 / 115 | 9,417,431 + 2,937,349 | 0.76 GB | 5 / 119 | 9,417,984 + 1,982,661 | 4.36 GB |
| A8 | 8e6 | 128 | 2 / 6,974,346 / 54,488 | 22,293,204 + 43,934,090 | 4.16 GB | 17 / 54,501 | 22,923,875 + 28,970,939 | 17.34 GB |
| B8a / b / c | 8e6 | 1024 | 2 / 6,974,345 / 6,811 (6,814; 6,812) | 24,875,091 + 28,468,117 (24,878,509 + 28,477,157; 24,875,146 + 28,469,904) | 3.17 / 2.99 / 3.14 GB | 17 / 6,826 | 27,295,969 + 16,835,660 | 16.32 GB |
| C8 | 8e6 | 16384 | 2 / 6,975,893 / 427 | 31,883,374 + 15,160,536 | 3.03 GB | 17 / 442 | 34,943,288 + 7,364,055 | 16.16 GB |
| B8ctl16 (buffer 16 MiB) | 8e6 | 1024 | 2 / 6,973,699 / 6,811 | 24,870,803 + 28,463,735 | 3.08 GB | **1002** / 7,011 | 31,762,150 + 7,499,221 | 16.32 GB |

| Observable | Reading | Evidence |
|---|---|---|
| `too many nodes` in `system.log` | 0 in all nine runs | `readings.txt` `TOO_MANY_NODES_LINES 0` |
| largest `num_leaves` of one segment | 54,488 for variant A at 8e6 (flush; 3,457 per segment in the rebuild) | `analysis.txt` |
| peak `SegmentBufferSpaceUsedBytes` (control) | B8b 1,073,743,992; B8c 1,073,744,164 (1024 MiB); B8ctl16 16,779,592 (16 MiB) | `segbuf.csv` |
| heap used (jcmd sampler) | peaks 5.1 to 8.2 GB in all runs of the 8 GiB heap (G1 fills the heap before collecting); does not separate variants | `heap.csv` |
| 8e6 load | 89 to 167 s (four to five other nodes were running) | `readings.txt` |

### 4.2 Conclusion and logic

1. **Validity.** Valid for both tiers. Every cell reached the check (a full leaf is written 62 to 250,000 times per cell) [observed: `num_leaves` = ceil(N/M)]. The constant of each variant is the intended one [observed: `WCS_ENTER ... M=128 / 1024 / 16384` in `wcs.txt`, and `javap` of the variant jars in `cmdlog-head.txt`]. Held-fixed settings: heap 8 GiB, `memtable_heap_space` 5 GiB, `sai_options.segment_write_buffer_size` 1024 MiB except in the control [observed: `jvm-extra.txt`, the stage-4 yaml lines in `cmdlog-head.txt`]; no daemon left [observed: `daemons left (this run root): 0` in each `cmdlog`; `ps` after the chains shows none of this case's].
2. **Readings.** Several pre-registered sub-ranges missed (listed in `selfcheck.txt`): postings lengths grow by more than 60 x from N = 1e5 to 4e6 at M = 128, 1024, 8192 (75, 122, 85) and differ by 18.6 x across M at N = 1e6 (U4(d)); `LEAFPOST` per leaf is 140 and 141 at M = 16 and 128 (below 150) and 1072 and 7620 at M = 8192 and 65536 (above 600): the retained per-leaf structure holds the leaf's values, so it grows with M while the total falls (U4(e)); at N = 8e6 the BALANCED_TREE length of variant C grows 3.39 x for 3.71 x the values (C5 range 3.5 to 4.2) and the across-variant spread is 1.43 (BALANCED_TREE; bound 1.3) and 2.90 (POSTING_LISTS; bound 2) (C5). The LEAFPOST pass of the cell M = 16, N = 4e6 is invalid (negative). The 8e6 runs flushed twice (D2). [observed: `selfcheck.txt`]
3. **Matched row.** Unit B2g row 1 as read by the U4 amendment: ALLOC and file lengths grow with N at fixed M (ALLOC x 29 to 49 for x 40 rows; tree length x 40.0), SCRATCH is N-independent and proportional to M and B (44 to 48 bytes per M), and ALLOC and file lengths at fixed N are not proportional to M (ALLOC slope -0.33, falling 15-fold from M = 16 to 65536; postings fall 18.6 x; tree within 1.23 x) [observed: tables above]. Cluster B3g row 1: disk and ALLOC grow with N in every variant (tree x 3.4 to 3.8 and ALLOC x 3.6 to 4.0 for x 3.7 values), and across variants at N = 8e6 ALLOC(A)/ALLOC(B) = 1.31 and ALLOC(C)/ALLOC(B) = 0.96 while the constant spans 128 x; B3g row 4 (control moves, the constant does not): at 16 MiB the rebuild wrote 1002 segments against 17 and the peak segment buffer was 16.0 MiB against 1024 MiB, while the same 128-fold change of the constant moved no peak and no segment count in that way [observed: `analysis.txt`, `segbuf.csv`].
4. **Excluded rows.** "Usage at fixed N rises or falls roughly in proportion to the constant": no (ALLOC falls and by far less than the constant's range; postings fall 2.9 x across 128 x; tree 1.43 x) [observed]. "Usage flat while N quadruples": no [observed: ratios above]. "Flush errors with too many nodes": no [observed: 0 lines]. "Control does not move": no [observed]. "Heap too noisy to separate variants": the sampled heap peaks do not separate variants (G1 reaches the 8 GiB maximum), so the cluster tier rests on thread-allocated bytes and file lengths, the alternative the B3h text names; run-to-run noise of ALLOC for B/8e6 is 5.9 percent (2.99 to 3.17 GB), of the tree length 0.01 percent [observed: `selfcheck.txt`].
5. **Observed vs. inferred.** Inferred: that allocated bytes and file lengths stand for the memory and disk a flush uses (the cluster tier has no retained-heap reading; the unit tier reads retained `SCRATCH` and `LEAFPOST` directly) [inferred: thread-allocated bytes are a flow, retained bytes are a footprint]; that the per-leaf cost behind the falling ALLOC is the per-leaf `PackedLongValues` builder [inferred: Lucene's page allocation, not read in the jar here]. The verdict rests on observed ratios and the control.
6. **Deviations and gaps.** (a) D2 (two flush segments at 8e6), D3, D4. (b) Up to five nodes (127.0.0.1 to .6, own JMX ports) of this session ran at once on `pc32` (the README asks for one run at a time per node); the quantities read (allocated bytes, file lengths, segment counts, buffer gauge) do not depend on timing, the load times do and are not used. (c) Each cluster cell was run once, B/8e6 three times; the A and C variants were not repeated. (d) The cluster tier does not exercise the constructor's `> MAX_ARRAY_LENGTH` rejection or the `checkMaxLeafNodeCount` throw (it needs about 9e10 points at B = 24 and M = 1024). (e) The control is a segment-buffer limiter on the rebuild path; the flush path has no byte limiter, so no resource-capping control exists for the flush path.
7. **Core question.** The constant sizes the per-writer scratch arrays (proportional to M, N-independent) and sets the leaf count, through which a per-leaf cost makes allocation and postings fall, not rise, as M grows; at every M, allocation and file lengths grow with the rows (x 29 to 49 for 40 x the rows in the unit tier, x 3.6 to 4.0 for 3.7 x the rows in the cluster tier), and nothing bounds them. So usage follows N, not the constant, and the constant does not cap it; a real cap (the segment-buffer limit) moves segment counts by 59 x and the buffer peak from 1024 to 16 MiB in the same harness (parts 3 and 4).

**Conclusion (one line):** Unit B2g row 1 (as amended U4) — confirmed (does not cap); Cluster B3g row 1/row 4 — confirmed (does not cap), with the pre-registered sub-ranges U4(d), U4(e) and C5 (tree and postings spread, variant C tree ratio) missed.

## 5. Self-check of run 1 — AI

### 5.1 Check of run 1's conclusion

Re-opened 2026-10-28: `unit/unit.out` and the nine `cluster/*/{wcs.txt,readings.txt,segbuf.csv,components-*.txt}` re-parsed by `harness/.../selfcheck.py` (`run1/selfcheck.txt`: 46 PASS, 11 FAIL; the 11 FAIL lines are the sub-prediction misses in 4.2 part 2, not unmatched pass criteria of the matched rows), and by hand `unit-attempt1/unit.out` (the N = 0 crash), `cluster/B8a/system.log` (the `MEMTABLE_LIMIT` flush at 2.5 GiB) and `cluster/B8ctl16/analysis.txt`.

| Part | Holds? | Note (file re-read) |
|---|---|---|
| 1. Validity | yes | `wcs.txt` `M=` per variant; `readings.txt` `TOO_MANY_NODES_LINES 0`; `cmdlog` `daemons left 0`. |
| 2. Readings | yes | `selfcheck.txt` FAIL lines are the ones listed; the negative LEAFPOST is in `unit.out`. |
| 3. Matched row | yes | ratios recomputed from `unit.out` and `analysis.txt`; control from `segbuf.csv`. |
| 4. Excluded rows | yes | no run shows ALLOC or lengths rising with M; the slope is negative. |
| 5. Observed vs. inferred | yes | the allocation-as-usage inference is the stated limit; it does not change the sign of any ratio. |
| 6. Deviations and gaps | yes | D2 to D4 and the shared-node note are in 4.2. |
| 7. Core question — the steps follow the audited logic | yes | scratch (unit) -> N-growth at every M -> non-proportionality to M -> variants (cluster) -> control moves while the constant does not. |

### 5.2 Run 2?

**No** (2026-10-28). The unit readings are exact counts and byte lengths repeated in the three (1024, 1e6) runs to 0.001 percent, the cluster ratios are 3- to 50-fold effects against 6 percent noise, and the sub-prediction misses are about secondary bounds, not about the sign of any ratio.

## 6. Run 2 — fresh AI session (optional)

Not done.

## 8. Verdict — AI

**Stage-3 estimate:** negative. **Outcome class:** true negative (negative, does not cap): the constant sets the leaf size and the scratch arrays, not a limit on allocation, file size or flush heap, which follow the number of rows.

**Claim tested (B1):** changing `maxPointsInLeafNode` (default 1024) changes only the fixed per-writer scratch arrays and the leaf count; the heap used by one numeric-index flush and the bytes written still scale with the number of rows, and no value of the constant caps either.

| Tier | Verdict (B2g / B3g row) | Effect on the constraint | Basis | Date |
|---|---|---|---|---|
| Unit | Confirmed (B2g row 1 as amended by U4: usage grows with N at every M; scratch proportional to M and N-independent; not proportional to M at fixed N); sub-predictions U4(d) postings ratios and spread and U4(e) per-leaf bands missed | does not cap | run 1 + self-check | 2026-10-28 |
| Cluster | Confirmed (B3g row 1 and row 4: disk and allocation grow with N in all three variants; the segment-buffer control moves segments 17 -> 1002 and the buffer peak 1024 -> 16 MiB; the constant, varied 128-fold, moves no usage in proportion); C5 spread bounds and the variant-C tree ratio missed; heap samples do not separate variants | does not cap | run 1 + self-check | 2026-10-28 |

**Positive control:** the sensitivity control `new long[k]` moved ALLOC by 8 x (1e6 - 1e3) bytes (unit), and `segment_write_buffer_size` at 16 MiB against 1024 MiB moved the rebuild path's segment count from 17 to 1002 and the peak buffer from 1024 MiB to 16 MiB (cluster). Neither is a closed Confirmed case and no resource-capping control exists for the flush path, so the confirmation is of the claim "usage follows rows, not the constant" and not of a measured cap elsewhere on the same path.

**Feedback filed:** the case file's section D updated (no commit by this session); amendments U1-U5 and C1-C5 dated 2026-10-28, made at the audit before any reading.

