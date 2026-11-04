# last_valid_segment_row_id-exceedssegmentlimit-sstablerowid--autonomous — stage-4 results  <!-- file: results/last_valid_segment_row_id-exceedssegmentlimit-sstablerowid--autonomous.md -->

> **Case:** [`last_valid_segment_row_id-exceedssegmentlimit-sstablerowid--autonomous`](../../stage3-ai-deep-read/cases/last_valid_segment_row_id-exceedssegmentlimit-sstablerowid--autonomous.md)
>
> **Status:** **Self-checked 2026-10-28 — unit Confirmed (does not cap), cluster Confirmed (does not cap); pre-registered segment-count ranges and the exact 500 / 1980 missed (builder bytes per row and the seed's row count were mis-estimated); no run 2**
>
> **Outcome class:** true negative — stage-3 estimate `negative` against the stage-4 effect `does not cap` ([definition](../README.md#outcome-class))
>
> **Agent:** autonomous (B2 = unit tier, B3 = cluster tier, feedback = section D).

## 1. Before run 1 — design audit and freeze

| Field | Content |
|---|---|
| **Case-file version** | sha256 of the whole file after the audit's amendments (U/C items, dated 2026-10-28, inserted after the link rule): unit tier and the discarded first cluster attempt on `c9adb80e71a6542354b0f7cf96449bcb47fcfe413a5a1beee0d680ca39a39553`; unit tier unchanged; cluster tier (restarted after runbook defect D1, a dated fix to amendment C2 that leaves claim, prediction and conclusions unchanged) on `553789af3a20d635887067f985c194934f8e3069a0c2a0cd1d9f47759e5463d4`, unchanged until section D was filed. Repository HEAD `b68711e5`; case file, harness and results uncommitted. Computed before any reading. The frozen text is everything above section D. |
| **Harness** | `harness/last_valid_segment_row_id-exceedssegmentlimit-sstablerowid--autonomous/` (uncommitted; README lists the files). |
| **Tiers and values** | Unit (B2) and cluster (B3), both run. Capacity values: cap -1(default)/1000/100 x byte limit 1/64/1024 MiB (unit); limit 16/256/1024 MiB with the default constant and the 10000 variant (cluster). |
| **Audit bottom line** | **Ready after amendments** — 2026-10-28 |

### 1.1 Design audit

| Group | Check | Rating | Note (section checked) |
|---|---|---|---|
| A | bytes | Met | A2: the constant caps a row-id span; bytes are governed by `segment_write_buffer_size`, which is the byte quantity measured (limiter bytes, heap). |
| A | knob | Partly | Hard-coded; varied through the test hook (unit) and a rebuilt variant (cluster, C1); the byte limit is the second knob (3 values). |
| A | real resource | Partly | unit: limiter bytes with a GC-forced heap cross-check (B2d); cluster: heap after GC, JMX gauge, GC log (B3d). |
| A | driven past limit | Met | cap 1000/100 reached by construction; the default cap cannot be reached by a workload (span 5e6 vs 1.07e9) - the claim's side. |
| B | steps | Met | B2e, B3e numbered. |
| B | prediction numbers | Partly | B2f 'about 200 / about 2000' and 'regardless of L' corrected (200 / 1980; L = 1 MiB binds both); B3f 'no limit lines at 1024 MiB' is an arithmetic slip (5 GB of terms vs a 1 GiB buffer): U2, C3. |
| B | every outcome has a row | Met | B2g/B3g cover default, tiny cap, control flat, limit never reached, boundary. |
| B | confirmation needs ceiling-follows-knob and disallow evidence | Met | byte-limit follows L (segments/peaks) and a flush by the cap is seen only with the tiny cap. |
| B | alternative explanations | Met | separated by the 3 x 3 grid and the gap test. |
| C | human can follow | Met | A1-A3. |
| C | AI can run without re-deriving | Partly | probe set-up copied from `SegmentFlushTest`; key ordering and the META read stated (U1, U2). |
| C | exact values | Partly | cluster data load, snapshot, wait condition and sampler stated (C2). |
| D | harness exists | Partly | written in step 1. |
| D | workload reaches limit | Met | unit: N = 200000 x 1000 B exceeds 1 MiB and 64 MiB, not 1024 MiB; cluster 5M x 1 KB > 1 GiB buffer. |
| D | citations spot-checked | Met | `SegmentBuilder.java:46,47,55,147,175,258-273`; `SSTableIndexWriter.java:65-68,205-262`; `V1OnDiskFormat.java:126-128`; `SegmentFlushTest.java:94,229-260`: match. |

| # | Recommendation | Applied? | Why |
|---|---|---|---|
| R1 | Environment, instruments, corrected arithmetic (U1-U3) | Applied 2026-10-28 | as filed not runnable / arithmetic |
| R2 | Variant via javac overlay and the cluster procedure (C1, C2) | Applied | fill gaps |
| R3 | Predictions in numbers (C3) | Applied | filed wording relational only |

**Pre-run-1 instrument checks** (disclosed; none of them is a reading used in a prediction): see section 3 and the harness README.

**Pre-run-1 instrument checks and shakedowns (disclosed; none edited a prediction):** (1) Two known-answer runs of `SegmentRowCapProbe` before the unit tier (pair at default cap with ids 0 and 1,073,741,822: 1 segment; grid cap 1000, 64 MiB, N = 5000, S = 1000: 5 segments of 1001 rows): they matched `SegmentFlushTest` and the pre-registered 1001-row segments. (2) The first cluster attempt (a seed with `cassandra-stress write -col`, then `CREATE CUSTOM INDEX` on the blob column) failed at once with `Unsupported type: blob` (defect D1 below); no reading was taken. (3) The 200,000-row cluster shakedowns of the sibling cases informed the node helper only.

## 2. Environment

| Field | Run 1 |
|---|---|
| Date | unit 2026-10-28 (node clock UTC 2026-10-28 23:54 to 2026-10-29 00:18); cluster 2026-10-28 (node clock UTC 2026-10-29 from 00:22, the seed, to about 01:50) |
| Node | `pc32` = `node2.jason92-321705.misconfiguration-pg0.cloudlab.umass.edu` (40 cores, 251 GiB); up to six nodes of this session's four cases ran at once |
| OS and kernel | Ubuntu 22.04.2 LTS, `5.15.0-198-generic` |
| JDK / Ant | openjdk 11.0.32.1 (2026-08-18) / Apache Ant 1.10.12 |
| Local source copy | `~/s4-b34` from `cassandra/cassandra-5.0.9/` at repository commit `b68711e5` (`copy-source.sh`), `ant build-test` BUILD SUCCESSFUL; small-constant variant `~/s4-b34-vS`; the variant copies were deleted after the runs (rebuild with the harness `make-variant*.sh`) |
| Case-file / harness commit | uncommitted (working tree of `b68711e5`); unit tier on sha256 `c9adb80e…`, cluster tier on `553789af…` (section 1) |
| Storage for node data | `~/stage4-tmp/b34/c3/<label>` on local `/dev/sda3` (the 4.1 GB seed and about 12 GB per run, removed after each run); nothing under `/proj` except these excerpts |
| Full logs (outside the repo) | `pc32:~/s4-b34-logs/b3/run1/` (`unit/`, `cluster/<label>/` with `heap.csv`, `gc-*.log`, `segbuf.csv`, `segments.txt`, `debug-sai-lines.txt`, `system.log`) |

## 3. Runbook defects

| # | Run | Step | Problem | Fix | Decision (date) |
|---|---|---|---|---|---|
| D1 | cluster attempt 1 | C2 data | `cassandra-stress` native mode creates blob columns; SAI rejects blob ("Unsupported type: blob"); the first seed and the first run S1024 were discarded | the case file's C2 amendment now names a `cassandra-stress user` profile for `ks.t3 (id bigint, c0 text)` (`size: fixed(1000)`), dated; the cluster tier restarted from its beginning (new seed, all five runs again) | 2026-10-28, claim, prediction and table unchanged; case-file sha256 `c9adb80e…` -> `553789af…` |
| D2 | cluster | C2 data | `cassandra-stress user` with `seq(1..5000000)` and `n=5000000` wrote 3,931,031 distinct rows (one sstable of 4.1 GB), not 5,000,000: every segment list sums to 3,931,031 | none; all cluster comparisons use the measured count. The pre-registered "exactly 500 segments" (C3) assumed 5,000,000 rows and is read against the formula `ceil(3,931,031 / 10,001) = 394` as well (post-hoc, labelled) | 2026-10-28 |
| D3 | unit | U2 arithmetic | the pre-registered "exactly 1980" segments at cap 100 is a ceiling error: ceil(200000 / 101) = 1981 | none (recorded as a missed pre-registered number) | 2026-10-28 |
| D4 | cluster attempt 1 | C2 | the first run (S1024 on the blob seed) was stopped by hand after the index creation failed; its node directory, log folder and the blob seed were deleted | none; no reading from it is used | 2026-10-28 |

## 4. Run 1

**Scope:** every B2 and B3 value of section 1. **Command logs:** `last_valid_segment_row_id-exceedssegmentlimit-sstablerowid--autonomous/run1/` (`unit/unit.out`, `cluster/<label>/{readings.txt,segments.txt,debug-sai-lines.txt,analysis.txt,...}`, `selfcheck.txt`).

### 4.1 Readings

**Unit tier** (`run1/unit/unit.out`; N = 200000 rows of 1000 bytes, ids 0..199999; all three repetitions of every cell identical)

| cap | byte limit L | segments | rows per segment (min..max) | peak limiter bytes | 
|---|---|---|---|---|
| default (1,073,741,822) | 1 MiB | 458 | 291..437 | 1,050,108 |
| default | 64 MiB | 8 | 4,006..28,030 | 67,109,408 |
| default | 1024 MiB | 1 | 200,000 | 476,329,976 |
| 1000 | 1 MiB | 458 | 291..437 | 1,050,108 |
| 1000 | 64 MiB | 200 | 801..1,001 | 2,402,156 |
| 1000 | 1024 MiB | 200 | 801..1,001 | 2,402,156 |
| 100 | 1 / 64 / 1024 MiB | 1,981 | 20..101 | 244,412 |

| Test or assertion | Result | Evidence |
|---|---|---|
| boundary pairs | default cap: ids 0 and 1,073,741,822 -> 1 segment; 0 and 1,073,741,823 -> 2; cap 1000: 0 and 1000 -> 1, 0 and 1001 -> 2; ids 0 and 1,073,741,823 (gap) -> 2 segments of 1 row | `P-*` cells |
| repetition | 27 grid JVMs = 9 cells x 3: identical segment counts, rows and peak bytes | `selfcheck.txt` |

**Cluster tier** (`run1/cluster/<label>/analysis.txt`, `readings.txt`; one sstable of 3,931,031 rows, 4.1 GB; 4 GiB heap)

| Run | build | `segment_write_buffer_size` | segments | rows per segment (min..max) | span max | `Global limit` lines | peak SegmentBufferSpaceUsedBytes | heap after GC (peak MB) | index build (s) |
|---|---|---|---|---|---|---|---|---|---|
| S16 | default | 16 MiB | 829 | 1,939..4,746 | 4,745 | 828 | 16,780,736 | 496 | 815 |
| S256a | default | 256 MiB | 52 | 56,243..75,981 | 75,980 | 51 | 268,439,084 | 4,063 | 1,157 |
| S256b (repeat) | default | 256 MiB | 52 | 56,243..75,981 | 75,980 | 51 | 268,439,084 | 4,076 | 650 |
| S1024 | default | 1024 MiB | 13 | 292,558..303,210 | 303,209 | 12 | 1,073,744,644 | 4,067 | 875 |
| V1024 | `LAST_VALID_SEGMENT_ROW_ID = 10000` | 1024 MiB | **394** | 638..10,001 | 10,000 | 0 | 35,310,828 | 533 | 681 |

| Observable | Reading | Evidence |
|---|---|---|
| segments | in every default-constant run `segments - 1` = the `Global limit of ... exceeded` lines (828, 51, 12) and the `Flushed segment with` lines equal the segment count | `debug-sai-lines.txt`, `readings.txt` |
| row-cap split in default runs | none: the widest span is 303,209 against 1,073,741,822 | `segments.txt` |
| small-constant run | first segments 10,001 rows each (ids 0..10000, 10001..20001, ...), 394 segments = ceil(3,931,031 / 10,001); no `Global limit` line | `segments.txt`, `debug-sai-lines.txt` |
| heap used (jcmd sampler) | sampled peaks 2.9 GB (16 MiB and small-constant runs) and 3.9 to 4.0 GB (256 and 1024 MiB runs) | `heap.csv` |
| SAI component bytes on disk | 8.19 to 8.21 GB in every run | `components.txt` |

### 4.2 Conclusion and logic

1. **Validity.** Valid. The byte limit was reached in every default-constant run (Global-limit lines = segments - 1 [observed]); the row-cap hook was driven (cap 1000 and 100 shrink the segments [observed]); the variant jar carries `LAST_VALID_SEGMENT_ROW_ID = 10000l` [observed: `cmdlog.txt` `javap` line of V1024, `1073741822` in the default runs]; the node settings (4 GiB heap, `sai_options.segment_write_buffer_size` per run) are in `cmdlog-head.txt`; no daemon left [observed: `daemons left (this run root): 0`].
2. **Readings.** Pre-registered numbers that missed (`selfcheck.txt`): segments 8 at 64 MiB (3..5) and 458 at 1 MiB (150..400) in the unit tier — the 1000-byte terms cost 2.4 KB of builder bytes per row, not 1.1 KB; cap 100 gave 1981, not 1980 (ceiling arithmetic); in the cluster tier 13 / 52 / 829 segments at 1024 / 256 / 16 MiB against 3..8 / 15..40 / 200..600 (3.5 KB of builder bytes per random 1000-byte text row), and 394 segments for the small constant against the pre-registered 500 (the seed held 3.93 million rows, not 5 million: D2) [observed]. The relations held: strictly fewer segments as the limit rises, `Global limit` lines present at all three limits, peak buffer 16.8 MB / 268 MB / 1074 MB, heap-after-GC difference 3571 MB between 1024 and 16 MiB (pre-registered at least 300 MB) [observed].
3. **Matched row.** Unit B2g row 1 "Default cap: segments and peak bytes change when L changes, no change when cap is left at default -> claim confirmed": 458 / 8 / 1 segments and peaks 1.05 MB / 67.1 MB / 476 MB at L = 1 / 64 / 1024 MiB with the cap at default [observed]; the "positive control moves" row: cap 1000 and 100 give 200 and 1981 segments independent of L (64 and 1024 MiB) with peaks 2.4 MB and 0.24 MB, and the boundary pairs confirm the strict `>` [observed]. Cluster B3g row 1 "With default constant, heap peak and segment count track `segment_write_buffer_size`": 829 > 52 > 13 segments, buffer peaks 16.8 / 268 / 1074 MB, heap-after-GC 496 / 4063 / 4067 MB, and no split near the row cap [observed]; row 3 "small-constant jar produces about N segments and lower peak heap": 394 segments (the cap split the sstable at 10,001 rows) and peak buffer 35.3 MB and heap-after-GC 533 MB at the 1024 MiB limit [observed].
4. **Excluded rows.** "Default cap: a flush occurs at row-id span 200000 with large L": no (1 segment) [observed]. "Cap 1000/100 does not change segment count": no [observed]. "Peak bytes never reaches L at L = 1 MiB": no (1,050,108) [observed]. "Boundary pair yields 2 segments at cap not cap+1": no [observed]. Cluster: "splits near the row cap with the default constant": no (widest span 303,209); "byte limit never exceeded at 16 MiB": no (828 lines); "small-constant jar shows no change": no [observed].
5. **Observed vs. inferred.** Inferred: that the segment-builder bytes (the limiter) stand for the heap the builder holds — the heap-after-GC readings (496 against 4067 MB) support it in the cluster tier but G1's after-GC reading includes floating garbage [inferred]; that the default cap cannot be reached by a workload (span 3.9 million against 1.07 billion) [inferred: arithmetic].
6. **Deviations and gaps.** (a) D1 to D4. (b) Up to six nodes of this session ran at once on `pc32` (the README asks for one run at a time per node); the quantities read do not depend on timing (index-build seconds are listed, not used). (c) 3.93 million rows, not 5,000,000. (d) One run per cell; the 256 MiB limit was repeated (S256b: 52 segments, identical row counts, buffer peak 268,439,084 as S256a). (e) The default constant cannot be changed by an operator; the only controls are the test hook (unit) and the rebuilt jar (cluster). (f) The unit tier's trie buffer holds common-prefix terms (a long run of `x`), so its bytes per row (2.4 KB) differ from the cluster's random text (3.5 KB).
7. **Core question.** With the constant at its default, the builder's usage and the segment boundaries follow the byte limit (1 / 8 / 458 segments in the unit tier, 13 / 52 / 829 in the cluster tier, peaks equal to the limit) and never the row cap (no flush at a span of 303,209 against 1,073,741,822); when the cap is made small (1000, 100 in the unit tier; 10,000 in the cluster tier) it splits segments at its own boundary and holds the builder far below the byte limit, so the cap binds only when set far below its default and the default does not cap memory or disk (parts 3 and 4).

**Conclusion (one line):** Unit B2g row 1 and the control row — confirmed (does not cap); Cluster B3g row 1 and row 3 — confirmed (does not cap), with the pre-registered segment-count ranges (unit 64 and 1 MiB, cap 100; cluster all three limits and the exact 500) missed.

## 5. Self-check of run 1 — AI

### 5.1 Check of run 1's conclusion

Re-opened 2026-10-28: `unit/unit.out` (32 RESULT lines) and the five `cluster/*/{segments.txt,segbuf.csv,heap.csv,gc-*.log,readings.txt,debug-sai-lines.txt}` re-parsed by `harness/.../selfcheck.py` (`run1/selfcheck.txt`: 33 PASS, 8 FAIL; the eight FAIL lines are the pre-registered ranges named in 4.2 part 2), and by hand `cluster/V1024/segments.txt` (first rows), `cluster/V1024/cmdlog-head.txt` (`javap` of the variant jar) and `cluster/S16/debug-sai-lines.txt`.

| Part | Holds? | Note (file re-read) |
|---|---|---|
| 1. Validity | yes | `unit.out`, `cmdlog.txt` `javap` lines, `debug-sai-lines.txt` Global-limit counts. |
| 2. Readings | yes | the missed ranges are the FAIL lines of `selfcheck.txt`; 3.93 million rows from the segment sums. |
| 3. Matched row | yes | segment counts and peaks recomputed from `segments.txt` and `segbuf.csv`. |
| 4. Excluded rows | yes | no row-cap flush with the default constant; the control moved. |
| 5. Observed vs. inferred | yes | GC-reading caveat recorded. |
| 6. Deviations and gaps | yes | D1 to D4 and the shared-node note. |
| 7. Core question — the steps follow the audited logic | yes | default cap never binds (unit and cluster) -> byte limit sets segments and peaks -> tiny cap binds and shrinks usage. |

### 5.2 Run 2?

**No** (2026-10-28). The unit cells repeat to the byte in three fresh JVMs; the cluster tier shows 4- to 60-fold differences in segment counts and a 7-fold difference in heap-after-GC, against a 256 MiB repeat; the misses concern pre-registered magnitudes, not the direction of any reading.

## 6. Run 2 — fresh AI session (optional)

Not done.

## 8. Verdict — AI

**Stage-3 estimate:** negative. **Outcome class:** true negative (negative, does not cap): at its default the row-id cap never splits a segment and the builder's usage is set by `segment_write_buffer_size`; the cap binds only when made tiny.

**Claim tested (B1):** at its default value `LAST_VALID_SEGMENT_ROW_ID` does not govern the heap used by SAI segment building: the heap is governed by `segment_write_buffer_size`, so changing the byte limit moves peak builder bytes and segment count while the row-id cap never triggers a flush on a workload whose row-id span is far below 1073741822.

| Tier | Verdict (B2g / B3g row) | Effect on the constraint | Basis | Date |
|---|---|---|---|---|
| Unit | Confirmed (B2g row 1; control row: cap 1000 / 100 -> 200 / 1981 segments independent of L; boundary pairs); pre-registered segment ranges at 64 and 1 MiB and "exactly 1980" missed | does not cap | run 1 + self-check | 2026-10-28 |
| Cluster | Confirmed (B3g row 1 and row 3: segments 829 > 52 > 13 with the limit, no row-cap split; small constant 394 segments, peak 35 MB); pre-registered counts and the exact 500 missed (builder bytes per row 3.5 KB; 3.93 million rows) | does not cap | run 1 + self-check | 2026-10-28 |

**Positive control:** the row cap at 1000 and 100 (unit) and 10,000 (cluster, rebuilt jar): it splits segments at its own boundary regardless of the byte limit and holds peak builder bytes at 2.4 MB / 0.24 MB / 35.3 MB — it binds only when set far below its default; the hook and the rebuilt jar are the control, not an operator-settable knob and not a closed Confirmed case.

**Feedback filed:** the case file's section D updated (no commit by this session); amendments U1-U4 and C1-C3 dated 2026-10-28, made at the audit before any reading; the C2 data amendment corrected by the dated defect fix D1.

