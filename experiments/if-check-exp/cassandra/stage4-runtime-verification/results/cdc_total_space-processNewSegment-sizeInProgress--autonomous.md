# cdc_total_space-processNewSegment-sizeInProgress--autonomous — stage-4 results  <!-- file: results/cdc_total_space-processNewSegment-sizeInProgress--autonomous.md -->

> **Case:** [`cdc_total_space-processNewSegment-sizeInProgress--autonomous`](../../stage3-ai-deep-read/cases/cdc_total_space-processNewSegment-sizeInProgress--autonomous.md)
>
> **Status:** verdict filed 2026-10-25 (run 1 of both tiers, self-checked; run 2 not chosen). Nothing is committed.
>
> **Outcome class:** true positive — stage-3 estimate `positive` vs the stage-4 effect `caps` (soft)
>
> **Agent:** autonomous. "§9a" below means B2f/B2g (unit) and B3f/B3g (cluster); "§9b–§9e" means B2a–B2e / B3a–B3e; the feedback field is section D.

## 1. Before run 1 — design audit and freeze

| Field | Content |
|---|---|
| **Case-file version** | The case file is untracked in git (repo HEAD `627b1ec` does not hold it). **sha256 of the whole file after the audit's amendments: `8cf71e6b116796c2ce3b0fcdf25ffc40d7ade516eb51859519468feb4039bb7b`**, frozen 2026-10-25 before the first unit or cluster matrix cell (section D was filled after the runs; the file's final sha256 is `441d64c85acf9ab04d8ebd5f2bffd881cafcbc36a1564a3276753e84aa2557e4`; B and the prediction/conclusion tables are unchanged). **Hash of the prediction and conclusion tables** (the text of B2f, B2g, B3f, B3g concatenated, sha256): `4d8d5fe5027e56fb4147a0a698499bdd5558573ff3a6fe0d72eb45c72dbcd725` (parts: B2f `bcfc878e…`, B2g `3dd66283…`, B3f `871c3d5a…`, B3g `7af701a9…`). Two dated amendment blocks (B2, B3) plus in-place numbered additions, all dated 2026-10-25. |
| **Harness** | `harness/cdc_total_space-processNewSegment-sizeInProgress--autonomous/` (uncommitted; `SHA256SUMS` lists the files that ran). Derived from the harness of the `deleteOldLinkedCDCCommitLogSegment` case on the same constraint. |
| **Tiers and values** | Unit (B2): N = 96, 192 MiB (capped) and 1024 MiB (positive control), both modes, 3 repeats, plus the non-CDC-table control (N = 96, both modes, 2 repeats). Cluster (B3): R1 non-blocking 128, R2 non-blocking 256, R3 non-blocking 4096 (control), R4 blocking 128, R5 blocking 4096 (control), R6 blocking 256 (added), non-CDC-table run (non-blocking 128); repeats: 2 for R1, R2, R4, R6, 1 for R3, R5 and the non-CDC run. The default (derived 4096 MiB here; 63 GB volume / 8 = 7.9 GB, so min is 4096) is the control value, not a driven cap. |
| **Audit bottom line** | **Ready after amendments** — 2026-10-25 |

### 1.1 Design audit

Source checked: `cassandra/cassandra-5.0.9/` (clean per `git status`, repo commit `627b1ec`).

| Group | Check | Rating | Note (section checked) |
|---|---|---|---|
| A. Core question | constrained quantity is memory or disk bytes | Met | A2: bytes in `cdc_raw` (plus unflushed CDC segments); `processNewSegment` compares `sizeInProgress` bytes with `getCDCTotalSpace()` (`:326-337`). |
| A. Core question | knob varied, ≥ 3 values incl. default — or another approach | Met | B2b: 96, 192, 1024; B3b: 128, 256, 4096 (4096 is the default on this node). Blocking cluster had one capped value (128); R6 (256) added as a dated amendment so the blocking ceiling can be seen to follow the knob. |
| A. Core question | real resource measured, not only the counter (gap named) | Met | B2d(2) `Files.walk` and `du -sb`; B3d `du -sb`/50 ms sampler; the counter (`sizeInProgress`) is read separately by reflection/log; the apparent-vs-allocated gap and the commit-log inode sharing are named (A4, amendment B3 (4)). |
| A. Core question | usage driven to the limit and past it | Partly → Met after amendment | As filed the unit tier would not reach the limit: the unit yaml has 5 MiB segments (`test/conf/cassandra.yaml:10`), so 96 MiB is 19 segments against a 60 MiB workload. Fixed in amendment B2 (2) (S = 32 MiB set by the harness; 37 mutations, about 18 segments, against 3 / 6 / 32 allowed). Cluster: 2 GiB against 128/256 MiB (16x/8x). |
| B. Logic | each step says what it establishes | Partly | B2e/B3e list steps; "what it establishes" is in B2g/B3g, not per step. Left for stage 3. |
| B. Logic | prediction stated in numbers or a clear relation | Met after amendment | B2f/B3f have numbers. Added the segment-accounting arithmetic (k-1 or k segments, from `:335-337` plus the walk counting index files) and R6, R4 arithmetic. |
| B. Logic | every plausible outcome has a conclusions row with its evidence | Partly → Met after amendment | Rows added for cap-never-reached, tracker/real-bytes gap, the non-CDC control, blocking ceiling following the knob (R4/R6), release after two deletions. |
| B. Logic | confirmation needs ceiling-follows-knob and direct disallow evidence | Met after amendment | Non-blocking: two caps + `deleteOld`/`Freed up`; blocking: R4+R6 and rejections / FORBIDDEN segments. |
| B. Logic | alternative explanations and their controls | Partly → Met after amendment | The `cdc=false` control as filed predicts an empty `cdc_raw`, which the source contradicts (see recommendation 3); re-stated as "retained footprint is CDC-attributable". |
| C. Specific | a human can follow it | Met | A and B1 are clear. |
| C. Specific | an AI can run B2/B3 without re-deriving the code path | Partly → Met after amendment | Wrong paths (`/users/jason92/cassandra-5.0.9`, `/tmp/ca-unit`, `/data/local`), `-R`, `HEAP_NEWSIZE` under G1, "S/3" payload, resume step (1 deletion), per-batch stress key restart: all made exact in the amendment blocks. |
| C. Specific | knob, values, workload, commands, observables, sampling, stop conditions exact | Met after amendment | See the two amendment blocks. |
| D. Runnable | harness and environment prerequisites exist or are listed | Partly | No harness for this case existed; step 1 built one from the sibling case's harness (README in the harness folder). |
| D. Runnable | workload arithmetic reaches the limit (data, time, disk, memory) | Met after amendment | Unit: 37 x 10.7 MiB; cluster: 2 GiB at 200 rows/s = about 165 s, disk about 2 GiB cdc_raw + about 2 GiB sstables + commit log per cell on 49 GiB free, `ulimit -n 100000`. |
| D. Runnable | load-bearing citations spot-checked against the pinned source | Met | Re-read: `processNewSegment` `:326-358` (incl. `:335-337`, `:345-354`), `deleteOldLinkedCDCCommitLogSegment` `:91-131` (`:117`, `:122`), `permitSegmentMaybe` `:195-210`, `throwIfForbidden` `:212-228`, `createSegment` `:237-249`, `discard` `:66-83`, `processDiscardedSegment` `:360-383`, `calculateSize` `:407-419`, `updateCDCTotalSize` `:439-451`; `Config.java:397,410,413,417-421`; `DatabaseDescriptor.java:242,677-695,4370-4376`; `CommitLog.java:460-470`; `cassandra.yaml:918-923`; `CommitLogSegmentManagerCDCTest.java:121-139`; `Mutation.trackedByCDC` and `DirectorySizeCalculator` (sums every file's `attrs.size()`). All match. Trigger reaches the check: every new commit log segment calls `createSegment` -> `processNewSegment`. |

| # | Recommendation | Applied? | Why |
|---|---|---|---|
| 1 | B2b/B2a: unit yaml has 5 MiB segments; harness sets 32 MiB and `max_mutation_size` 16 MiB; paths | **Applied 2026-10-25** (B2 amendment (1), (2)) | Source: `test/conf/cassandra.yaml:10`, `DatabaseDescriptor.java:898-899`; without it the workload cannot reach 96 MiB. |
| 2 | B2c: "S/3" payload = 11,184,810 B, 37 attempts, rejections count as attempts, flush then read | **Applied 2026-10-25** (B2 amendment (3)) | Makes the loop exact; two mutations fit per segment. |
| 3 | B2f/B3f `cdc=false` bullets: replaced by a source-derived prediction (transient links up to N+S, at most 2 left after flush; zero rejections) | **Applied 2026-10-25** (B2f, B3f, B2g and B3g rows) | `createSegment` `:243-247` links every PERMITTED segment; `discard` `:76-83` unlinks only non-CONTAINS ones. Not a reading. |
| 4 | B2f/B3f: k-1 or k segments depending on whether a walk (which counts `_cdc.idx` bytes) ran before the check | **Applied 2026-10-25** | `DirectorySizeCalculator.visitFile` sums all files; `:335-337` is strict `>`. Upper bounds N are unchanged. |
| 5 | B3: add R6 (blocking 256 MiB) | **Applied 2026-10-25** (B3 amendment (2), B3f, B3g) | Group B: blocking claim needs two capped values. |
| 6 | B3e step for R4: delete two links, probe up to 60 s; replace "1 s" by "within 10 s" | **Applied 2026-10-25** (B3 amendment (5)) | `permitSegmentMaybe` strict `<` (`:201`); a forbidden segment has no link (`:243-247`). |
| 7 | B3c: one stress run of 32768 rows with a flush every 10 s | **Applied 2026-10-25** (B3 amendment (3)) | A stress run per batch restarts its key sequence. |
| 8 | B3a: loopback address and JMX port of its own for the node (another agent shares the host) | Harness only (README) | Not case-file text; environment. |
| 9 | Per-step "establishes" line; judge a default-value arm | Left for stage 3 | Not needed to run. |

## 2. Environment

| Field | Run 1 |
|---|---|
| Date | 2026-10-25 |
| Node | `pc12` = `node1.jason92-320876.misconfiguration-pg0.cloudlab.umass.edu`, 40 cores, 251 GiB (shared with an agent tagged `ss`) |
| OS and kernel | Ubuntu 22.04, `5.15.0-187-generic` |
| JDK / Ant | OpenJDK 11.0.32.1 / Apache Ant 1.10.12 |
| Local source copy | `~/s4-cdc/clone`, from `cassandra/cassandra-5.0.9/` at repository commit `627b1ec` via `copy-source.sh` (local tag `cassandra-5.0.9`); `ant build-test` 1 min 11 s; unit tier adds `CdcTotalSpaceProbeTest.java` and one DEBUG logger line in `test/conf/logback-test.xml` |
| Case-file commit / harness commit | none (untracked) / none; sha256 in §1 and `harness/…/SHA256SUMS` |
| Storage for node data | local `/dev/sda3` (63 GB, 49 GiB free at start), node directories under `~/s4-cdc/run` (wiped after each cell), unit data under `~/s4-cdc/clone/build/test/cassandra`. Nothing on `/proj`. |
| Full logs | `pc12:~/s4-cdc/logs/` (`unit/<cell>/`, `cluster/<cell>/`, `build.log`, `unit-check.out`, `cluster-check.out`); small excerpts in `results/<stem>/run1/` |
| Settings | Unit: S = 32 MiB, `max_mutation_size` 16 MiB, S/3 payload, `cdc_free_space_check_interval` 250 ms. Cluster: one node on 127.0.0.37 (JMX 7237), `MAX_HEAP_SIZE=1G` (G1), `commitlog_total_space: 2048MiB`, 64 KiB rows at 200/s via `cassandra-stress`, Byteman observation rules loaded at start (no listener). |

## 3. Runbook defects

| # | Run | Step | Problem | Fix | Decision | Case-file commit |
|---|---|---|---|---|---|---|
| 1 | Audit | B2a / B2b | Unit yaml has 5 MiB segments, not 32; workload cannot reach 96 MiB | Harness sets 32 MiB and `max_mutation_size`; dated amendment | AI, 2026-10-25 (before any reading) | uncommitted |
| 2 | Audit | B2a, B3a | Paths `/users/jason92/cassandra-5.0.9`, `/tmp/ca-unit`, `/data/local/ca-node` do not exist or must not be used; `-R`; `HEAP_NEWSIZE` | Amended | AI, 2026-10-25 | uncommitted |
| 3 | Audit | B2f, B3f | `cdc=false` table predicted to leave `cdc_raw` empty, contradicted by `:243-247` / `:76-83` | Replaced by a source-derived prediction | AI, 2026-10-25 | uncommitted |
| 4 | Audit | B3e (R4) | One deleted link would not release a blocked writer at an exact multiple | Two links; probe up to 60 s | AI, 2026-10-25 | uncommitted |
| 5 | Audit | B3c | Fresh stress run per batch restarts the key sequence | One run, flush every 10 s | AI, 2026-10-25 | uncommitted |
| 6 | Cluster launch (harness only) | cluster-run.sh `all` | The `all` loop called `"$0"`; the script had lost its execute bit on the node, so every cell exited 126 before any node started (`failed.txt` listed 11 cells; no node, no reading) | `bash "$0"`; `SHA256SUMS` regenerated (only `cluster-run.sh` differs from the first copy); the cluster tier was started again from its beginning | AI, 2026-10-25 | n/a |

The unit tier was not restarted by these; all were found in the audit and the instrument checks before any matrix cell ran.

## 4. Run 1

**Scope:** every cell of both tiers listed in §1. **Command logs:** `run1/unit/summary.txt`, `run1/cluster/<cell>/summary.txt` (full logs on the node, §2). Readings tables: `run1/unit-readings.txt`, `run1/cluster-readings.md`; the re-parse is `run1/selfcheck_unit.py`, `run1/selfcheck_cluster.py` (outputs `unit-selfcheck.txt`, `cluster-selfcheck.txt`).

### 4.1 Readings

**Unit tier** (MiB; S = 32 MiB; 37 attempted mutations of 11,184,810 B in every cell; "bytes" = all files in `cdc_raw`, index files add 18 B each; "peak" = the 5 ms sampler and the per-mutation readings; evidence `run1/unit/<cell>/readings-excerpt.txt`, `cdc-verdict.txt`, `freed-up.txt`):

| Cell (3 repeats unless noted) | Accepted / rejected | Peak bytes | Final bytes (after flush) | Segments created / FORBIDDEN | `deleteOld` passes / "Freed up" lines | Tracker vs `Files.walk` at the end |
|---|---|---|---|---|---|---|
| blocking N = 96 | 8, 8, 6 / 29, 29, 31 | 128, 128, 96 | 128, 128, 96 | 8-9 / 3 | 0 / 0 | equal |
| blocking N = 192 | 12 / 25 (all 3) | 192 | 192 | 11 / 3 | 0 / 0 | equal |
| non-blocking N = 96 | 37 / 0 | 128 | 128 | 22-23 / 0 | 10, 13, 14 / same | equal |
| non-blocking N = 192 | 37 / 0 | 192, 224, 224 | 160, 160, 224 | 22-23 / 0 | 12, 10, 8 / same | equal |
| control N = 1024, blocking and non-blocking | 37 / 0 | 640 (20 links) | 640 | 22-23 / 0 | 0 / 0 | equal |
| control non-CDC table N = 96, blocking (2 repeats) | 37 / 0 | 128 | 32 (1 link) | 23 / 14 | 0 / 0 | equal |
| control non-CDC table N = 96, non-blocking (2 repeats) | 37 / 0 | 128 | 64 (2 links) | 23 / 0 | 14 / 14 | equal |

**Cluster tier** (MiB; one node per cell, 2 GiB of 64 KiB rows at 200 rows/s, flush every 10 s; "W peak" = largest `cdc_raw` link bytes at 50 ms from W start to W+33 s; "steady" = time-weighted median over the last 60 s of the workload; evidence `run1/cluster/<cell>/`, table `run1/cluster-readings.md`):

| Run | Cell(s) | W peak | Steady | Final (W+30 s, links) | Stress errors / rows | `Rejecting mutation` WARN | Forbidden segments | `deleteOld` = "Freed up" | Release (2 links deleted) |
|---|---|---|---|---|---|---|---|---|---|
| R1 non-blocking 128 | r1, r2 | 128, 128 | 128, 128 | 128 (4), 96 (3) | 0, 0 / 32,768 | 0 | 0 | 42, 38 | n/a |
| R2 non-blocking 256 | r1, r2 | 256, 256 | 256, 224 (sawtooth 7-8 links) | 256 (8), 224 (7) | 0, 0 | 0 | 0 | 40, 37 | n/a |
| R3 non-blocking 4096 | r1 | 2112 | grows to the end (1760 median) | 2112 (66) | 0 | 0 | 0 | 0 / 0 | n/a |
| R4 blocking 128 | r1, r2 | 128, 128 | 128, 128 (flat) | 128 (4) | 30,725 each | 19, 19 | 3, 3 | 0 / 0 | accepted on probe 2: 1,353 and 1,351 ms |
| R5 blocking 4096 | r1 | 2112 | grows to the end | 2112 (66) | 0 | 0 | 0 | 0 / 0 | n/a |
| R6 blocking 256 | r1, r2 | 224, 224 | 224, 224 (flat) | 224 (7) | 29,192 each | 18, 17 | 2, 2 | 0 / 0 | accepted on probe 2: 1,386 and 1,353 ms |
| non-CDC table, non-blocking 128 | r1 | 160 | 128 | 64 (2) | 0 | 0 | 0 | 9 / 9 | n/a |

The Byteman `deleteOld` count equals the DEBUG "Freed up" count in every non-blocking cell (`traces:` line of each `summary.txt`). The sampler's largest gap was 240 ms (limit 1000 ms). Apparent bytes of `cdc_raw` were larger than allocated bytes in the non-blocking cells (nb128-r1: 134 MB apparent, 71 MB allocated, `du.txt`): mapped segments are sparse until written.

### 4.2 Conclusion and logic

1. **Validity.** Settings took effect: `system_views.settings` read-back shows `cdc_total_space` = the cell's cap, `cdc_block_writes` as set, `commitlog_segment_size` 32MiB [observed: `cluster/*/settings.txt`; unit `config` lines in `unit/*/readings-excerpt.txt`]. The limit was reached in every capped cell: blocking cells created 2 to 3 FORBIDDEN segments and rejected 68 % to 94 % of the writes [observed: `cluster-selfcheck.txt`, `unit-readings.txt`]; non-blocking cells ran 8 to 42 `deleteOld` passes [observed: `traces:` lines]. The control with the cap out of reach (N = 1024 unit, 4096 cluster) wrote 640 MiB and 2112 MiB into `cdc_raw` with no trim and no rejection, so the workload could fill the directory [observed: `unit/b1024-r1`, `cluster/nb4096-r1/summary.txt`, `cluster/b4096-r1/summary.txt`]. Valid.
2. **Readings.** Unit blocking N = 96 is bimodal (96 MiB once, 128 MiB twice, accepted 6 or 8): the trace shows the tracker was at 0 or 32 MiB (not 64) when the 2nd and 3rd segments were created in those JVMs (`pre ... sip=0` lines in `unit/b96-r1/cdc-verdict.txt`), because the test restarts the commit log before each test; the cluster tier has no such restart [inferred: trace lines; not tested separately]. R2 r2's steady median is 224 MiB, the sawtooth between 7 and 8 links (224 and 256) that the 50 ms trace shows in r1 as well [observed: `cluster/nb256-r2/sampler-changes.csv`].
3. **Matched row.** Unit: B2g row 1, "Non-blocking max size <= N + 3S for both N and the trim line logged | Claim confirmed for the mechanism at line 345": non-blocking max 128 MiB (N = 96, limit 192) and 192 to 224 MiB (N = 192, limit 288), 8 to 14 `deleteOld` passes and "Freed up" lines per cell, remaining sizes <= N + S; the two maxima differ by 64 to 96 MiB (about N difference 96 +- S) [observed: `unit-selfcheck.txt`]. B2g row 3, "Blocking: exception raised with size <= N + S | Claim confirmed for blocking mode": rejections 25 to 31 per cell, peak 96 to 128 MiB at N = 96 and 192 MiB at N = 192, no `deleteOld` [observed]. Cluster: B3g row 1, "R1/R2 plateau at about the limit (within +3S), R3 reaches about 2 GiB | Claim confirmed": R1 128 MiB, R2 224 to 256 MiB (limits 224 and 352), R3 2112 MiB with no "Freed up" [observed: `cluster-selfcheck.txt`]; the row added at the audit, "R4 and R6 plateaus (blocking) both at or below cap + S, rejections in both, and R6 - R4 about 128 MiB (+-S)": 128 and 224 MiB, difference 96 MiB, rejections 17 to 19 WARN and about 30,000 failed writes each [observed]; "R4/R6 after two links deleted writes resume within 60 s": 1.35 s in all four [observed]. The row-3 R4 text of B3g, "R4 rejects writes at about the limit and `cdc_raw` is flat": flat from W-60 s to W end in all four blocking cells [observed].
4. **Excluded rows.** B2g "reaches 384 MiB, no trim logged" (refuted): N = 96 and 192 never exceeded 224 MiB against 640 MiB at N = 1024. "Blocking: no exception and size >> N": exceptions in every capped cell, size <= N + S. "N = 1024 control does not exceed 192 MiB (workload too small)": 640 MiB. "Max size > N + 5S": max N + 1 S. "Cap never reached" added row: every capped cell had FORBIDDEN segments or `deleteOld` passes. "Tracker differs from the walk by > S": tracker equals the walk to within the index files in every unit cell. The non-CDC control row: zero rejections, peak <= N + S, <= 2 links after the flush [observed]. B3g "R1/R2 plateau but not scaling": R2 - R1 steady is 128 MiB (r1) and 96 MiB (r2), peaks 256 vs 128. "R1 grows like R3": R1 never above 128 MiB while R3 grew to 2112. "R4 never rejects": rejects. "R3 does not grow past 256": 2112 MiB. "Links removed but data volume grows (inode sharing)": the commit log directory was 336 MB (non-blocking) and 101 MB (blocking) at the end, independent of the cap, and the cap compares with `cdc_raw` bytes only [observed: `summary.txt` `commit log dir`].
5. **Observed vs. inferred.** Inferred: (a) the cap governs the apparent bytes of the hard links, not freed blocks, since a link shares its inode with the commit log copy until that is discarded (A4; allocated bytes were lower than apparent in non-blocking cells) [inferred: source and `du.txt`]; (b) the explanation of the bimodal blocking N = 96 unit cells (part 2) [inferred]; (c) that the S/3 payload fits two per segment (accepted counts 12 for six segments) [inferred: counts]. The conclusion depends on none of them.
6. **Deviations and gaps.** (i) **Sub-predictions missed:** the accounting bullet of B2f for blocking N = 96 ("(k-1)S or kS = 64 or 96 MiB, accepted 4 to 6, never above N") held for N = 192 and for one N = 96 repeat but missed in two (128 MiB, 8 accepted); the headline bound "never exceeds N + S" holds. The R4 accounting (3 or 4 links, <= 160) held (4 links); the R6 accounting "(k-1)S..kS = 224..256" held (224). B3f R2 "steady 256-290" missed in r2 (224, a sawtooth whose top is 256). (ii) Index files add 18 B per segment, so byte totals sit a few dozen bytes above a segment multiple; checks allow 4 KiB. (iii) Run counts: unit 3 repeats (2 for the non-CDC control), cluster 2 repeats for R1, R2, R4, R6 and 1 for R3, R5 and the non-CDC run. (iv) Not driven: the derived default cap (4096 MiB was set explicitly), a consumer deleting files in real time, a second node, commitlog compression. (v) The throttle (200 rows/s) was added at the audit; the cap check is made at segment creation, so a faster writer would still be checked per segment, but this was not run unthrottled. (vi) The cluster tracker (`sizeInProgress`) is not directly observable; the log lines and bytes on disk are. (vii) Stress and rejected-write logging: the blocking cells wrote 29,000 to 31,000 `ERROR` lines to `system.log` (one per rejected write); no effect on the readings.
7. **Core question.** Usage followed the constraint in both tiers: in non-blocking mode `cdc_raw` held at the cap while the trim ran (unit 128 / 192 to 224 MiB at N = 96 / 192; cluster 128 and 224 to 256 MiB at caps 128 and 256), in blocking mode it stopped growing at or just under the cap (unit 96 to 128 and 192; cluster 128 and 224 MiB) while writes to the CDC table were rejected, and with the cap out of reach the same workload filled 640 MiB (unit) and 2112 MiB (cluster). The plateau scales with the knob in each mode (parts 3, 4). The constraint caps the directory, softly: one segment over the cap at times (blocking N = 96 unit, non-CDC table peak 160 at cap 128, sawtooth +1 link in non-blocking), and a non-CDC table consumes budget transiently because every permitted segment is linked at creation.

**Conclusion (one line):** Unit: B2g rows 1 and 3 — Confirmed, claim holds (caps). Cluster: B3g row 1 and the added blocking rows — Confirmed, claim holds (caps).

## 5. Self-check of run 1 — AI

### 5.1 Check of run 1's conclusion

`run1/selfcheck_unit.py` and `run1/selfcheck_cluster.py` re-parse the committed excerpts (not the harness scripts) against every filed sub-prediction: unit 93 PASS, 4 MISS (`unit-selfcheck.txt`; the accounting sub-predictions at blocking N = 96, two repeats); cluster 64 PASS, 1 MISS (`cluster-selfcheck.txt`; R2 r2 steady median). A first version of the cluster script applied the 4 KiB index allowance to a link-byte comparison and reported two false MISS lines for the 224 MiB R6 plateau; it was corrected before this file was written (the plateau 224.0 MiB equals (k-1)S exactly).

| Part | Holds? | Note (file re-read) |
|---|---|---|
| 1. Validity | yes | Re-read `cluster/*/settings.txt` (cap read-back), `unit/*/readings-excerpt.txt` config lines, `summary.txt` `traces:` lines, `cluster/b4096-r1/summary.txt`, `unit/b1024-r1`. |
| 2. Readings | yes | The bimodal N = 96 cells re-read in `unit/b96-r{1,2,3}/readings-excerpt.txt` and `cdc-verdict.txt`; the sawtooth in `cluster/nb256-r2/sampler-changes.csv`. |
| 3. Matched row | yes | Every number in part 3 recomputed in the two selfcheck outputs. |
| 4. Excluded rows | yes | Each has a reading in the selfcheck outputs or `summary.txt`; the inode-sharing row relies on `du.txt` and the `commit log dir` lines. |
| 5. Observed vs. inferred | yes | The three inferred statements are listed; (b) was not tested (the clean explanation would be a separate unit cell without the commit-log restart), the conclusion does not rest on it. |
| 6. Deviations and gaps | yes | The five misses are recorded in part 6 (i); none changes the matched row. |
| 7. Core question | yes | Follows B1: ceiling follows the knob in each mode, disallow branch fired (rejections, FORBIDDEN segments, `deleteOld` and "Freed up"), control grows. |

### 5.2 Run 2?

**No** — decided 2026-10-25. The tiers agree with each other and across repeats (identical plateaus for R4 and R6, near-identical for R1 and R2), the result confirms a positive estimate, and the inferred statements do not carry the conclusion.

## 6. Run 2 — fresh AI session (optional)

Not done.

## 8. Verdict — AI

**Stage-3 estimate:** positive. **Outcome class:** true positive (positive, caps).

**Claim tested:** B1 — with `cdc_enabled: true` and a CDC table, the on-disk size of `cdc_raw` (plus CDC-counted unflushed segments) stays at or below `cdc_total_space` plus a bounded overshoot (about 1 to 3 segments of `commitlog_segment_size`) in non-blocking mode (oldest links deleted at lines 345-354) and in blocking mode (CDC writes rejected), whereas with a much larger `cdc_total_space` the same workload makes it grow well beyond that value. "Confirmed" means this held.

| Tier | Verdict (B2g / B3g row) | Effect on the constraint | Basis | Date |
|---|---|---|---|---|
| Unit | **Confirmed** — B2g rows 1 (non-blocking, <= N + 3S, trim logged) and 3 (blocking, exception, <= N + S); controls moved as predicted; sub-predictions missed: the segment-accounting bullet for blocking N = 96 in 2 of 3 repeats | caps (soft: whole segments, up to one over) | run 1 + self-check | 2026-10-25 |
| Cluster | **Confirmed** — B3g row 1 (plateaus 128 / 224 to 256 MiB non-blocking at caps 128 / 256, R3 2112 MiB) and the added blocking rows (128 / 224 MiB, rejections, resume after two deletions); sub-prediction missed: R2 r2 steady median 224 vs 256 to 290 | caps (soft) | run 1 + self-check | 2026-10-25 |

**Feedback filed:** the case file's section D (uncommitted); amendments dated 2026-10-25 in B2 and B3, all before any reading. `_INDEX.md`, `HANDOFF.md`, `predicted-*.md` and `writeup-set-A.csv` were not edited.

## Leftovers

On `pc12`, no process of this run is running (checked with `ps` after the last cell: no `CassandraDaemon`, `ant` or `cassandra-stress` of this tag; `127.0.0.37` not listening). Files left: `~/s4-cdc/clone` (473 MB, built tree with the copied test class and the DEBUG logger line), `~/s4-cdc/harness`, `~/s4-cdc/logs` (815 MB: `unit/`, `cluster/`, `cluster.chk/` (the first launch's empty folders), check outputs, `build.log`). `~/s4-cdc/run` and the unit test data directories were removed by the scripts. Another agent's node (tag `ss`) was running on the host during the cluster tier and was not touched; this run used its own loopback address and JMX port.
