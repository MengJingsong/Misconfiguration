# block_size-writeposting-blocksize--autonomous — stage-4 results  <!-- file: results/block_size-writeposting-blocksize--autonomous.md; the stem ends in --guided or --autonomous -->

> **Case:** [`block_size-writeposting-blocksize--autonomous`](../../stage3-ai-deep-read/cases/block_size-writeposting-blocksize--autonomous.md)
>
> **Status:** verdict filed 2026-10-28 — unit Confirmed (does not cap); cluster Not confirmed (no matching row; effect does not cap); no run 2
>
> **Outcome class:** true negative (stage-3 estimate `negative`, stage-4 effect `does not cap`; the cluster row is Not confirmed on the frozen 5 % bound, see section 8) **Index entry (orchestrator, 2026-10-28): undetermined** — README rule: a Not confirmed or Refuted-as-frozen tier makes the class undetermined; the agent filed true negative.
>
> **Agent:** autonomous. For an autonomous
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
| **Case-file version** | sha256 before the audit: `c14c3a24c5b70107465a66a2dcd8849518fd8121e91f05cf8d7a9c2720c1466d`. **Frozen version (after the audit's amendments B5.1-B5.7 of 2026-10-28, taken before any reading): `e560c7fb24078eb8de1c28939d4ec3bc1af35334d3c9aeb29ba9c6af2b074b43`.** After the post-freeze correction B5.8 (control condition (iii), made after the first cluster arm; no change to claim, predictions or rows): `8fdcb9c98697587b1071e84dcab09ce44cc9ee6da0ceacfc0dba52666dfda411`. **Final, after section D (stage-4 feedback): `cb8702d3345461afdbd432a0fb6d5227ba554849f398b4dcf5574667074c8a5f`.** File committed at `b68711e5` (HEAD); the amendments and feedback are uncommitted. |
| **Harness** | `harness/block_size-writeposting-blocksize--autonomous/` (uncommitted; README there) |
| **Tiers and values** | Unit: PostingsWriter at blockSize 16, 128, 1024 x N = 1,000 / 100,000 / 1,000,000 (stride 3) plus M = 1,000 small lists and a wide-stride control. Cluster: builds post32, stock (128), post512 at 3M rows; stock at 750k; segment_write_buffer_size 16MiB control. |
| **Audit bottom line** | **Ready after amendments** — 2026-10-28 |

### 1.1 Design audit

The requirements are in the README, "Step 0 — the design audit". One row per
line of each group; cite the case-file section checked.

| Group | Check | Rating (Met / Partly / Not met) | Note (section checked) |
|---|---|---|---|
| A. Core question | constrained quantity is memory or disk bytes | Met | A2: heap bytes of the fixed scratch array(s) (a count of longs with a derivable byte size) and the on-disk component bytes. |
| A. Core question | knob varied, >= 3 values incl. default — or another approach, with the reason | Met | B2b varies blockSize (16, 128, 1024) and N; B3b varies the constant through three builds (32, 128, 512). The constant is hard-coded (A1), so rebuilds are the only way to vary it (stated). |
| A. Core question | real resource measured, not only the counter (gap named) | Partly -> Met | Unit: thread-allocated bytes and heap histograms; cluster: a Byteman ledger of the exact array lengths, JMX heap/RSS samples (noisy, named as such) and component file bytes (B5). |
| A. Core question | usage driven to the limit and past it | Met | The check fires many times per run (arithmetic in B2c/B3c and B5); a hard-coded constant has no limit to exceed beyond that. |
| A. Core question | positive control (negative estimate) | Partly -> Met | Unit: wide stride (3 vs 1,000,003) must raise bits per value and file size per posting; N below blockSize writes exactly one tail block. Cluster: segment buffer control (amended definition) and stock at 750k vs 3M rows. |
| B. Logic | each step says what it establishes | Met | B1, B2e, B3e. |
| B. Logic | prediction stated in numbers or a clear relation | Partly -> Met | Tolerances added in B5 where the case said "slightly" or "a few percent". |
| B. Logic | every plausible outcome has a conclusions row with its evidence | Met (rows added) | B2g/B3g plus the added rows in B5 (queries fail, workload not driven). |
| B. Logic | confirmation needs ceiling-follows-knob and direct disallow evidence | Met | The claim is negative: the confirmation needs usage flat while the control moves; the direct evidence is the ledger and the readings of the traced check. |
| B. Logic | alternative explanations and their controls | Met | B2h/B3h, B5. |
| C. Specific | a human can follow it from the intro and §9a alone | Met | |
| C. Specific | an AI can run §9b–§9e without re-deriving the code path | Partly -> Met | B5 fixes the run form, load path and sizes. |
| C. Specific | knob, values, workload, commands, observables, sampling, stop conditions exact | Partly -> Met | B5 fixes the row counts, sampling (500 ms JMX, 1 s RSS) and tolerances. |
| D. Runnable | harness and environment prerequisites exist or are listed | Met (with harness) | Written for this run; the eight variant builds exist (`javap -constants`). |
| D. Runnable | workload arithmetic reaches the limit (data, time, disk, memory) | Met (amended) | node pc39: 251 GiB RAM, 40 cores, 48 GB free local disk; 3M rows is a few GB; B5 states it. |
| D. Runnable | load-bearing citations spot-checked against the pinned source | Met after corrections | `PostingsWriter.java:89, 102, 110, 115, 118-129, 205-226, 230-237, 246-301`, `PostingsReader.java:97`, `BlockBalancedTreePostingsWriter.java:135`, `LiteralIndexWriter.java:60` match the pinned source (checked 2026-10-28, with grep and sed). |

| # | Recommendation | Applied? (amendment date and commit, or "left for stage 3") | Why |
|---|---|---|---|
| 1 | B2f: file-size prediction "under a few percent" is wrong at blockSize 16 (about 20 % per-block overhead at 2 bits per delta); replaced by a model with a 2 % tolerance | Applied (B5.2) | arithmetic, independent of any reading |
| 2 | B2a run form (test classes on the classpath) | Applied (B5.1) | package-private constructor |
| 3 | B3: 3M rows, seed + CREATE INDEX, 5 % tolerance, ledger instrument, control definition | Applied (B5.4-B5.6) | proportion and quantification |

Run 2 is not planned, so the agreement criteria are not filled.

## 2. Environment

| Field | Run 1 |
|---|---|
| Date | 2026-10-28 (unit 17:51 MDT; cluster 18:26 to 18:37 MDT) |
| Node | `pc39` (`node1.jason92-321705.misconfiguration-pg0.cloudlab.umass.edu`), 40 cores, 251 GiB |
| OS / kernel | Ubuntu 22.04.2 LTS, `5.15.0-198-generic` |
| JDK / Ant | OpenJDK 11.0.32.1 / Apache Ant 1.10.12 |
| Local source | `~/s4-b34/base` (`copy-source.sh` copy of `cassandra/cassandra-5.0.9/` at repository commit `b68711e5`, `ant build-test`, `ant jar`); variants `~/s4-b34/v-post32` and `v-post512` (`PostingsWriter.java:89` edited by `sed`, patches in `run1/build-patches/`, `ant jar`, `javap -constants` confirmed `BLOCK_SIZE = 32` / `512`) |
| Case-file / harness commit | `b68711e5` with uncommitted amendments (sha256 in section 1) / uncommitted |
| Storage for node data | local disk `~/s4-b34/cl/postings/node`; seeds `~/s4-b34/seeds/sai-{750000,3000000}` (shared with the sibling SAI cases) |
| Full logs | `pc39:~/s4-b34/logs/postings/` (`unit/run1/`, `cluster/<arm>/`) |

**Instrument checks before run 1** (none used to tune a prediction): the cluster engine was shaken down on a 20,000-row seed with the `v-num64` build in the sibling case's folder (disclosed there); the unit probe was run through `unit-run.sh` once as run 1 itself (no separate shakedown).

## 3. Runbook defects

| # | Run | Step | Problem | Fix | Decision | Case-file commit |
|---|---|---|---|---|---|---|
| 1 | cluster, first attempt (no reading) | B3a / engine | the seed data directories were created under the sibling case's cluster name (`stage4-blockindex`); this case's node was started with `cluster_name: stage4-postings` and refused to start ("cluster name" check in `SystemKeyspace.checkHealth`); the 22-second attempt produced no arm (logs moved to `~/s4-b34/logs/failed-attempt-clustername/`) | one cluster name per kind of seed (`CLUSTER_NAME` in `cluster-run.py`); the tier restarted from its beginning | AI, 2026-10-28 | none |
| 2 | cluster, before this case's run | B5.5 control (iii) | the sibling case's first arm showed that the default 1024 MiB arm reaches its limit at 3M rows, so "flush lines only in the 16 MiB arm" cannot hold | B5.8 (dated 2026-10-28) in this case file before the first arm of this case ran: (iii) = more `Global limit` lines in the 16 MiB arm than in the default arm | AI, 2026-10-28 | none |
| 3 | unit analysis | `analyze_unit.py` | the lower bound of the retained-`long[]` window (deltaBuffer 8 bs + 16) was too tight for the M = 1,000 cells, where the class-histogram baseline moves by about 1 KB (J delta 480, -416 and 7,648 B for bs 128, 16 and 1024) | the window's lower bound was relaxed by 2 KiB in the analysis (`analyze_unit.py`, noted in its docstring); no run was repeated; the heap claim needs only "no growth with N beyond the skip-table lists" | AI, 2026-10-28 | none |

## 4. Run 1

**Scope:** unit tier: 30 JVMs (2 repetitions x blockSize 16 / 128 / 1024 x [N = 1,000 / 100,000 / 1,000,000 at stride 3; M = 1,000 lists of 50 at stride 3; N = 100,000 at stride 1,000,003]) and the upstream `PostingsTest`; cluster tier: six node starts (P128-3M, P32-3M, P512-3M, P128-750k, P128b-3M, ctl-seg16). **Command log:** `block_size-writeposting-blocksize--autonomous/run1/unit/summary.txt`, `run1/cluster/summary.txt`; checkers `analyze_unit.py`, `analyze_cluster.py` (outputs `run1/analyze-unit.txt`, `run1/analyze-cluster.txt`) and the independent `selfcheck.py` (`run1/selfcheck.out`).

### 4.1 Readings

**Unit tier** (`run1/unit/bs*.out`, identical in both repetitions; `data` = bytes from the file start (after the 7-byte header) to the summary offset returned by `write()`, summed over the lists; `model` = 1 + blocks x (1 + ceil(bs x 2 / 8)) per list (stride 3 needs 2 bits per delta); `file` = on-disk length including skip tables and footer):

| blockSize | N x lists, stride | Constructor alloc (B) | Blocks per list | `data` (model) | `file` (B) |
|---|---|---|---|---|---|
| 16 | 1,000 x 1, 3 | 2,456 | 63 | 316 (316) | 538 |
| 16 | 100,000 x 1, 3 | 2,456 | 6,250 | 31,251 (31,251) | 59,411 |
| 16 | 1,000,000 x 1, 3 | 2,456 | 62,500 | 312,501 (312,501) | 656,289 |
| 16 | 50 x 1,000, 3 | 2,456 | 4 | 21,000 (21,000) | 38,894 |
| 16 | 100,000 x 1, 1,000,003 | 2,488 | 6,250 | 268,751 (control) | 315,664 |
| 128 | 1,000 / 100,000 / 1,000,000, 3 | 3,368 / 3,368 / 3,392 | 8 / 782 / 7,813 | 265 / 25,807 / 257,830 (all = model) | 317 / 29,362 / 300,840 |
| 128 | 100,000 x 1, 1,000,003 | 3,400 | 782 | 252,587 (control, 9.8 x stride 3) | 258,491 |
| 1024 | 1,000 / 100,000 / 1,000,000, 3 | 10,536 / 10,560 / 10,560 | 1 / 98 / 977 | 258 / 25,187 / 251,090 (all = model) | 293 / 25,663 / 256,501 |
| 1024 | 100,000 x 1, 1,000,003 | 10,568 | 98 | 251,175 (control, 10.0 x stride 3) | 251,948 |

Retained `long[]` after the writes (histogram, writer referenced) minus the probe's own `long[N]` where that was still live: bs 16 N = 1M: 1,137,248 B (two skip-table lists of 62,500 entries, 1,000,000 B, plus capacity); bs 128 N = 1M: 149,808 B (7,813 blocks); bs 1024: 7,232 B (N = 1,000) and 8,816 B (N = 100,000), and 26,816 B (array already collected) for N = 1M; N = 50 x 1,000 lists: about the `deltaBuffer` only (the lists are cleared per list). Upstream `PostingsTest`: 8 tests, 0 failures. All 30 cells and all `EXPECTED` lines (99 OK, 0 MISMATCH) in `run1/analyze-unit.txt`.

**Cluster tier** (`run1/cluster/<arm>/`; "Postings" = `v_idx` + `txt_idx` `PostingLists.db`; heap = largest of 150 JMX samples at 500 ms, heap 2 GiB; `PW` ledger lines = `PostingsWriter` constructions with `deltaBuffer.length`):

| Arm (build, rows, seg buffer) | `PW` ledger (all lines) | Postings bytes (`txt_idx` / `v_idx`) | Total SAI bytes | Heap peak (MiB) | Seg-buffer gauge peak | `Global limit` lines | count queries |
|---|---|---|---|---|---|---|---|
| P128-3M (stock) | 12 x 128 | 10,755,390 (3,169,855 / 7,585,535) | 49,133,244 | 1,918 | 1,073,743,912 | 8 | 3,000,000 / 30,000 x3 OK |
| P128b-3M (stock, repeat) | 12 x 128 | 10,755,390 (identical) | 49,133,244 | 1,902 | 1,073,743,912 | 8 | OK |
| P32-3M (`BLOCK_SIZE = 32`) | 12 x 32 | 11,610,041 (3,645,480 / 7,964,561) = +7.9 % | 49,987,895 (+1.7 %) | 1,892 | 1,073,743,912 | 8 | OK |
| P512-3M (`BLOCK_SIZE = 512`) | 12 x 512 | 11,043,708 (3,062,405 / 7,981,303) = +2.7 % | 49,421,562 (+0.6 %) | 1,915 | 1,073,743,912 | 8 | OK |
| P128-750k (stock) | 6 x 128 | 2,543,946 (791,859 / 1,752,087) | 12,310,642 | 1,929 | 1,073,743,944 | 2 | 750,000 / 7,500 x3 OK |
| ctl-seg16 (stock, 3M, 16 MiB) | 852 x 128 | 6,405,045 (3,169,855 / 3,235,190) | 47,832,094 | 1,280 | 16,779,544 | 848 | OK |

All other SAI files (key blocks, numeric-values files, the `BalancedTree`) are byte-identical in P32, P128 and P512. Ratio Postings 3M / 750k = 4.23, total 3.99.

### 4.2 Conclusion and logic

1. **Validity.** The constant changed: every `PW` ledger line has `deltaBuffer.length` 32 / 128 / 512 in the respective arm [observed: `run1/cluster/<arm>/ledger.txt`]. The unit writer was driven well beyond one block: up to 62,500 blocks per list at bs 16 [observed: `run1/unit`]. The default segment buffer reached its limit at 3M rows (8 `Global limit` lines), the 16 MiB control at 16.0 MiB (848 lines) [observed: `flush-lines.txt`, `gauges-*.csv`]. All six arms built and answered the count queries, no `ERROR` line [observed: `cluster/summary.txt`, `errors.txt`].
2. **Readings.** (a) The unit data model (B5.2) holds to the byte in every stride-3 cell (`dev` 0.0000 %): the per-block overhead is 1 byte + the packed bytes, and the tail block is padded to a full block [observed]; for stride 1,000,003 (20 bits) the block takes 42 bytes (not 41): a 2-byte pad per block, which does not affect any row [observed: 268,751 = 1 + 6,250 x 43]. (b) At bs 16 the 1M-posting list takes 656 KB of file against 301 KB at 128 and 257 KB at 1024: the skip table (two entries of 8 bytes per block, FoR-compressed) is a visible part of the file. (c) In the cluster the Postings bytes are U-shaped in the block size (P32 +7.9 %, P512 +2.7 %): per-block overhead at 32, tail padding of many small lists at 512 [inferred: from the unit model and from the `v_idx` file, whose lists are small]. (d) Heap peaks of the three builds are 1,892 / 1,918 / 1,915 MiB, inside 26 MiB of each other, and the two stock arms differ by 16 MiB [observed]. (e) The 16 MiB segment buffer halves the `v_idx` posting file (3.24 against 7.59 MB), because each segment is flushed with its own lists: the real cap changes the disk figure as well [observed].
3. **Matched row.**
   Unit B2g row 1, "file size and heap grow with N for every blockSize; only the 1 KiB-scale buffer and skip-table counts change with blockSize": `data` grows 10.0 x for 10 x the postings at every size (258 -> 25,187 -> 251,090 at 1024), the constructor allocates 8 bs + 16 plus about 2 KB of objects (144 B + 2.3 KB at 16; 8.2 KB + 2.3 KB at 1024), the retained arrays beyond that are the two skip lists (1.14 MB at bs 16 and N = 1M), no value flattens at a size tied to blockSize [observed: `analyze-unit.txt`, 99 OK]. Also row 4's control: the wide stride raised the file size 9.8 to 10.0 times at the same N [observed].
   Cluster: **no B3g row matches**. Row 1 ("disk and heap unchanged within noise across 32/128/512 while the positive control moves") requires the frozen 5 % bound on the posting files, which P32 misses (+7.9 %); row 2 ("disk or peak heap changes strongly and monotonically with the constant") does not describe a +7.9 % / +2.7 % (U-shaped, +1.7 % / +0.6 % of the total) change with the heap flat. The control did move (row 3 does not apply) [observed: `analyze-cluster.txt`: 1 MISMATCH, the 5 % bound]. The reading is therefore "Not confirmed (no matching row)".
4. **Excluded rows.** Unit "usage flat in N for all blockSize and the control does not move": the control moved (9.8 to 10.0 x) [observed]; "N never exceeds blockSize": only the N = 1,000 / bs 1024 cell has one block, as B2g itself says, and is not used for the conclusion [observed]. Cluster "file size or heap bounded at a value tracking blockSize": not seen at any N or row count [observed]. "Neither the constant nor the control moves anything": the control moved (gauge 16.0 against 1,024 MiB, 848 against 8 limit flushes, heap peak 1,280 against 1,918 MiB, `v_idx` postings 3.2 against 7.6 MB) [observed]. "Disk grows only with row count": the posting files also depend slightly on the constant (above) [observed].
5. **Observed vs. inferred.** Inferred: (i) the U-shape explanation (2c); (ii) that the build path and the flush path use the same `PostingsWriter` (the ledger shows the writer ran in the build path; the flush path was not run). The verdict rests on neither.
6. **Deviations and gaps.** B3c's flush-and-compact load was replaced by seed + `CREATE INDEX` + `rebuild_index`, and 5M rows by 3M (B5.4); peak heap is a 500 ms sample (the two stock arms agree within 16 MiB here, unlike the sibling case with a 4 GiB heap); the unit probe reaches `PostingsWriter` through its private constructor by reflection (same body as the package-private one of `:119`); one run per arm plus one repeat of the stock arm; no native-memory reading beyond RSS (3.0 GiB at every arm). The frozen 5 % bound was my own quantification at the audit of the case's "under a few percent".
7. **Core question.** The writer's `long[blockSize]` and the on-disk size of a posting list do not saturate or flatten at any value tied to the block size: the data grows 10 x with 10 x the postings at every size (unit) and 4.23 x with 4 x the rows (cluster), and a node's heap does not move between 32 and 512 (1,892 to 1,918 MiB). The constant does change the posting files by a few percent (+7.9 % at 32, +2.7 % at 512; +1.7 % of the whole SAI index at most), which is per-block and padding overhead, not a limit; the segment buffer (16 MiB) cuts the build's heap peak by a third (1,280 against 1,918 MiB) and the `v_idx` posting file by more than half. So the block size does not cap memory or disk; the frozen "under 5 %" bound for the posting files was narrowly missed.

**Conclusion (one line):** unit B2g row 1 - Confirmed; cluster - Not confirmed (no matching B3g row; the frozen 5 % bound missed by P32 at +7.9 %), Effect `does not cap`.

## 5. Self-check of run 1 — AI

### 5.1 Check of run 1's conclusion

`harness/.../selfcheck.py` re-parses `unit/bs*.out`, `ledger.txt`, `files-*.txt`, `gauges-*.csv`, `flush-lines.txt` and `summary.txt` with its own regexes: 81 PASS, 0 FAIL (`run1/selfcheck.out`), including the independent re-derivation of the +7.9 % / +2.7 % figures, of the 1.7 % total spread, of the identity of the two stock arms and of the heap spread.

| Part | Holds? | Note |
|---|---|---|
| 1. Validity | yes | Ledger lengths, count queries, control gauge re-read. |
| 2. Readings | yes | Model deviation 0.0000 % re-computed from `dataBytes`, blocks and stride; heap spread re-computed. |
| 3. Matched row | yes | The "no matching row" reading rests on the 5 % bound (re-computed) and on the absence of monotonic strong change. |
| 4. Excluded rows | yes | Control figures re-parsed. |
| 5. Observed vs. inferred | yes | The U-shape explanation is inferred and not needed. |
| 6. Deviations and gaps | yes | As listed. |
| 7. Core question | yes | Follows B1: no saturation in N or rows, heap flat in the constant, the real cap moves. |

### 5.2 Run 2?

No — 2026-10-28. Unit counts are exact and repeated; cluster file sizes are deterministic (the two stock arms are byte-identical). A second run would reproduce the same numbers.

## 6. Run 2 — optional

Not done.

## 7. Comparison

Not done.

## 8. Verdict — AI

**Stage-3 estimate:** negative. **Outcome class:** true negative (estimate `negative`, effect `does not cap`; the cluster row is Not confirmed only on the frozen 5 % bound).

**Claim tested:** memory and disk used by the posting-list writer do not follow `BLOCK_SIZE` as a cap: the writer's heap is a fixed small array regardless of how many postings are written, and the on-disk size of a posting list grows with the number of postings (linearly, with only a small per-block overhead change) rather than saturating at a limit.

| Tier | Verdict (B2g / B3g row) | Effect on the constraint | Basis | Date |
|---|---|---|---|---|
| Unit | Confirmed (B2g row 1; control moved) | does not cap | run 1 + self-check | 2026-10-28 |
| Cluster | Not confirmed (no matching row: Postings bytes +7.9 % at 32 and +2.7 % at 512 against the frozen 5 %; total SAI +1.7 % / +0.6 %; heap flat; control moved) | does not cap (no saturation; 4.23 x for 4 x rows; heap flat in the constant) | run 1 + self-check | 2026-10-28 |

**Positive control:** unit: stride 1,000,003 against 3 raises bytes per posting 9.8 to 10.0 times at the same N and bs; N < bs gives exactly one tail block (258 B at bs 1024). Cluster: `segment_write_buffer_size` 16 MiB against 1024 MiB: gauge 16.0 against 1,024 MiB, 848 against 8 limit flushes, heap peak 1,280 against 1,918 MiB; rows 750k -> 3M: Postings 4.23 x.

**Feedback filed:** section D of the case file (dated 2026-10-28, uncommitted); B5 (items 1 to 7) and the post-freeze B5.8 are in the case file; final sha256 in section 1 and the final report.
