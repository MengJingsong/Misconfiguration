# cdc_total_space-deleteOldLinkedCDCCommitLogSegment-bytesToFree--autonomous — stage-4 results  <!-- file: results/cdc_total_space-deleteOldLinkedCDCCommitLogSegment-bytesToFree--autonomous.md -->

> **Case:** [`cdc_total_space-deleteOldLinkedCDCCommitLogSegment-bytesToFree--autonomous`](../../stage3-ai-deep-read/cases/cdc_total_space-deleteOldLinkedCDCCommitLogSegment-bytesToFree--autonomous.md)
>
> **Status:** verdict filed 2026-10-22 (run 1 of both tiers, self-checked; run 2 not chosen). Nothing is committed.
> 
> **Outcome class:** true positive — stage-3 estimate vs the stage-4 effect on the constraint
>
> **Agent:** autonomous. "§9a" below means B2f/B2g (unit) and B3f/B3g (cluster); "§9b–§9e" means B2a–B2e / B3a–B3e; the feedback field is section D.

## 1. Before run 1 — design audit and freeze

| Field | Content |
|---|---|
| **Case-file version** | The file is untracked in git (repo HEAD `00922e0` does not hold it). **sha256 of the whole file after the audit's amendments: `b6296de04cee009b94f49134e057cc8618095703e162fe046d2ec2a2e04af9a2`** (the file as filed carried no recorded hash; an intermediate hash `2200a12894d9…` after the first three amendments was superseded by the B2b note before any matrix cell ran). Frozen 2026-10-22, before the first unit or cluster matrix cell. Four dated amendments, all in the file next to the text they change. |
| **Harness** | `harness/cdc_total_space-deleteOldLinkedCDCCommitLogSegment-bytesToFree--autonomous/` (uncommitted; `SHA256SUMS` lists the files that ran: `CdcCapProbeTest.java 3cb43962…` was replaced twice during the instrument check, see §3; the run used the `SHA256SUMS` in the folder) |
| **Tiers and values** | Unit (B2): blocking and non-blocking, n = 64, 128, 256, 512 MiB, 3 repeats, plus controls. Cluster (B3): n = 128, 256, 512 MiB and the 16 MiB boundary, both modes, 2 repeats, plus controls. Default (4096 MiB on this node) is the positive control, not a driven cap. |
| **Audit bottom line** | **Ready after amendments** — 2026-10-22 |

### 1.1 Design audit

| Group | Check | Rating | Note (section checked) |
|---|---|---|---|
| A. Core question | constrained quantity is memory or disk bytes | Met | A2: the bytes of the files in `cdc_raw`; B2d/B3d measure exactly that (`du -sb`). |
| A. Core question | knob varied, ≥ 3 values incl. default — or another approach | Partly | B2b has four values (64 to 512) and B3b three (128, 256, 512) plus a 16 MiB boundary; the default is not a driven value (it is 4096 MiB here, above the workload), it enters only as the B2h/B3h positive control. Left for stage 3. |
| A. Core question | real resource measured, not only the counter | Met | B2d(2) and B3d: independent `du -sb` / directory walk, with the tracker (B2d(1)) and the log line as the counter; the gap between apparent and allocated bytes is named (B2d last paragraph). |
| A. Core question | usage driven to the limit and past it | Met | B2c / B3c: 3 x the cap, arithmetic stated for 128 MiB; B3 reaches 512 MiB x 3 in 2 minutes at about 13 MB/s, well inside disk and time. |
| B. Logic | each step says what it establishes | Partly | B2e/B3e list steps and observables; "what it establishes" is in B2g/B3g, not per step. Left for stage 3. |
| B. Logic | prediction stated in numbers or a clear relation | Met | B2f, B3f: `n + about 2 segments`, plateaus `128..192` etc., slope near 1. |
| B. Logic | every plausible outcome has a conclusions row | Partly | B2g/B3g cover exceeds-limit, flat, limit-never-reached, no-deletion, no-rejection. No row for "the real resource is bounded by a different amount than the counter" (counter capped but the real resource grows is covered by row 2). Not needed to run. |
| B. Logic | confirmation needs ceiling-follows-knob and direct disallow evidence | Met | B2f/B3f ask for the dose-response and for `CDCWriteException` counts / `Freed up` lines. |
| B. Logic | alternative explanations and their controls | Met | B2h/B3h: 4096 MiB control, `cdc = false` table, `cdc_enabled: false`, 1 s wait. |
| C. Specific | a human can follow it | Met | A and B1 are clear. |
| C. Specific | an AI can run B2/B3 without re-deriving the code path | Partly | B2b said the unit segment size is the 32 MiB default (it is 5 MiB, and `max_mutation_size` follows it); B3a sets `HEAP_NEWSIZE`, which G1 ignores. See §3. |
| C. Specific | knob, values, workload, commands, observables, sampling, stop conditions exact | Partly | B3d samples `du` every 2 s (a segment's creation and a deletion can both fall between samples); the harness adds a 50 ms sampler. The default `memtable_heap_space` vs "large" is not given a number. |
| D. Runnable | harness and environment prerequisites exist or are listed | Partly | No harness existed (A5 reads names only); step 1 built `CdcCapProbeTest`, a rate-controlled stress profile and reused the guided case's sampler and Byteman rules. |
| D. Runnable | workload arithmetic reaches the limit | Met | Checked above; 8 MiB mutations fit `max_mutation_size` (16 MiB) once it is set (§3 defect 1). |
| D. Runnable | load-bearing citations spot-checked against the pinned clone | Met | `deleteOldLinkedCDCCommitLogSegment` `:91-131`, `processNewSegment` `:326-358`, `permitSegmentMaybe` `:195-210`, `createSegment` `:243-249`, `discard` `:66-83`, `calculateSize` all match `cassandra-5.0.9`. The A3 text "the tracker is set to 0 even though files remain" is only true when the method returns 0 at `:93` or on an empty directory; the dead-code path is not shown by any reading. |

| # | Recommendation | Applied? | Why |
|---|---|---|---|
| 1 | B3e step 6: delete **two** oldest links, not one | **Applied 2026-10-22** (case file B3e step 6 and the B3g row) | `permitSegmentMaybe` promotes only on a strict `sizeInProgress + segmentSize < allowance` and a forbidden segment has no link; at an exact multiple of the segment size (128, 256, 512) one deletion leaves `(k-1)S + S + index bytes`, not below the cap, so the writer is correctly not released. A reason from source, independent of any reading. |
| 2 | B2h: the large-cap control's `du` is "at least the volume" (and ≤ volume + slack), not "equal" | **Applied 2026-10-22** (B2h) | Files are whole 32 MiB segments holding at most three 8 MiB mutations. |
| 3 | B3c / B3g: flushing does not remove the link of a segment that held CDC data | **Applied 2026-10-22** (B3c, one B3g row) | `discard` (`:66-83`) deletes the link only when the state is not `CONTAINS`; B4's `commitlog_total_space: 1024MiB` forces flushes at 3 x 512 MiB anyway. The instruction and workload are kept. |
| 4 | B2b: the unit yaml has 5 MiB segments and 2.5 MiB `max_mutation_size`; the harness sets 32 MiB and 16 MiB | **Applied 2026-10-22** (B2b, a runbook-defect fix found in the instrument check, before any reading; B2f/B2g unchanged) | See §3. |
| 5 | B3a: with G1 only `MAX_HEAP_SIZE` takes effect (`cassandra-env.sh:125-127`) | Left for stage 3 | The run used `MAX_HEAP_SIZE=2G`; the heap size is as filed. |
| 6 | Add a per-step "establishes" line; judge a default-value arm | Left for stage 3 | Not needed to run. |

## 2. Environment

| Field | Run 1 |
|---|---|
| Date | 2026-10-22 (unit tier about 12 min for 30 JVMs; cluster tier about 88 min for 22 node starts) |
| Node | `pc12` = `node1.jason92-320876.misconfiguration-pg0.cloudlab.umass.edu`, 40 cores, 251 GiB |
| OS and kernel | Ubuntu 22.04, `5.15.0-187-generic` |
| JDK / Ant | OpenJDK 11.0.32.1 / Apache Ant 1.10.12 |
| Local clone commit | `~/cassandra-cdc` at `cassandra-5.0.9`, `b5f2a54210d541339c2e7c17a794195cac0e67c2`; `ant build-test` 1 min 9 s; only untracked file `CdcCapProbeTest.java` |
| Case-file commit / harness commit | none (both uncommitted) / none; sha256 in §1 and `harness/…/SHA256SUMS` |
| Storage for node data | local `/dev/sda3` (63 GB, ext, home directory), node directories under `~/cdcrun` (wiped after each cell); unit data under `~/cassandra-cdc/build/test/cassandra`. Nothing on `/proj`. Free space never below 52 GB. |
| Full logs | `pc12:~/stage4-logs/cdc2/` (`unit/<cell>/`, `cluster/<cell>/`, `unit-check/`, `instrument-check-cluster-chk-b160/`, `build-test.log`); small excerpts in `results/<stem>/run1/` |
| Settings | Unit: 32 MiB segments, 16 MiB `max_mutation_size`, 8 MiB rows, `cdc_free_space_check_interval` 250 ms, unit JVM 1 GiB. Cluster: one node, `MAX_HEAP_SIZE=2G` (G1), `commitlog_total_space: 1024MiB`, `memtable_heap_space: 1024MiB`, 64 KiB rows via `cassandra-stress` at about 3 x cap per 120 s, no consumer, Byteman observation rules loaded at start. |

## 3. Runbook defects

| # | Run | Step | Problem | Fix | Decision | Case-file commit |
|---|---|---|---|---|---|---|
| 1 | Instrument check (unit, before any reading) | B2b / B2c | B2b says 32 MiB segments are "the test default"; the unit yaml has `commitlog_segment_size: 5MiB`, and `max_mutation_size` is derived once at start-up (2.5 MiB, `DatabaseDescriptor.java:898-899`), so the setter alone leaves B2c's 8 MiB mutations over the limit and the first check JVM failed on it | Harness sets `setCommitLogSegmentSize(32)` and `getRawConfig().max_mutation_size` = 16 MiB; B2b amended with a dated note; B2f/B2g unchanged | AI, 2026-10-22 | uncommitted |
| 2 | Instrument check (unit) | harness | `applyFuture()` throws `CDCWriteException` directly, not wrapped in `ExecutionException`; the first harness version let it escape | Catch it directly (harness only) | AI, 2026-10-22 | n/a |
| 3 | Run 1 unit, `nb256-r3` | harness teardown | `UncheckedIOException` in `afterTest` deleting `cdc_raw` files while the management thread deleted them; raised after the `RESULT` line, so the cell's readings are complete (junit shows one error) | Recorded; no change | AI, 2026-10-22 | n/a |
| 4 | Run 1 cluster | B3a | `HEAP_NEWSIZE=400M` is ignored by G1 | Not set; `MAX_HEAP_SIZE=2G` only | AI, 2026-10-22 | left for stage 3 |
| 5 | Run 1 cluster | B3e step 6 | One deleted link would not release a writer at an exact multiple (see §1.1, recommendation 1) | Applied at the audit, before any reading | AI, 2026-10-22 | uncommitted |

The unit tier was not restarted by defects 1 and 2 (both were found in the instrument check before the matrix ran).

## 4. Run 1

**Scope:** every cell of the two tiers listed in §1. **Command logs:** `run1/unit/summary.txt`, `run1/cluster/<cell>/summary.txt` (full logs on the node).

### 4.1 Readings

**Unit tier** (`run1/unit-readings.md`; MiB; one JVM per cell; `S` = 32 MiB; volume = 3 x n, 8 MiB rows; "du" = bytes of all files in `cdc_raw`, read after the last write plus 3 s):

| Cell(s) | Accepted / rejected rows | Final du (3 repeats) | Peak du (5 ms) | Segments created / forbidden | `deleteOld` calls | Evidence |
|---|---|---|---|---|---|---|
| blocking n = 64 | 6 / 18 | 64, 64, 64 | 64 | 7 / 3 | 0 | `unit/b64-r*/readings.txt`, `cdc-verdict.txt` |
| blocking n = 128 | 12 / 36 | 128, 128, 128 | 128 | 9 / 3 | 0 | `unit/b128-r*` |
| blocking n = 256 | 24, 21, 24 / 72, 75, 72 | 256, 224, 256 | = final | 12–13 / 3 | 0 | `unit/b256-r*` |
| blocking n = 512 | 45, 45, 48 / 147, 147, 144 | 480, 480, 512 | = final | 20–21 / 3 | 0 | `unit/b512-r*` |
| non-blocking n = 64 | 24 / 0 | 64, 96, 64 | 96 | 11 / 0 | 6 | `unit/nb64-r*` |
| non-blocking n = 128 | 48 / 0 | 128, 128, 128 | 160 | 19 / 0 | 8–9 | `unit/nb128-r*` |
| non-blocking n = 256 | 96 / 0 | 256, 256, 288 | 288 | 35 / 0 | 11–14 | `unit/nb256-r*` |
| non-blocking n = 512 | 192 / 0 | 480, 512, 512 | 544 | 67 / 0 | 25–28 | `unit/nb512-r*` |
| control n = 4096, blocking and non-blocking, volume 384 | 48 / 0 | 544, 544 | 544 | 19 / 0 | 0 | `unit/ctl-b4096`, `ctl-nb4096` |
| control `cdc_enabled=false` | 48 / 0 | 0 | 0 | none | 0 | `unit/ctl-cdcoff` |
| control non-CDC table n = 128, blocking / non-blocking | 48 / 0 | 32, 64 | **160** | 20 / 10, 19 / 0 | 0, 11 | `unit/ctl-plain-*` |
| control 1 s wait before each boundary reading, blocking n = 128 | 12 / 36 | 128 | 128 | 9 / 3 | 0 | `unit/ctl-wait1s-b128` |

In every blocking cell the tracker equalled du to the byte after the final walk and du was flat from the first rejection to the end; in every non-blocking cell the oldest links were gone (33 links seen against 8 left at n = 256) and the survivors were the newest created (`run1/selfcheck.txt`). The smallest tracker value after any `deleteOld` was 32 MiB or more in every cell (never 0).

**Cluster tier** (`run1/cluster-readings.md`; MiB; rows 64 KiB; workload = 3 x cap except the 16 MiB and 4096 MiB cells; "W peak" = links plus index files at 50 ms during the 120 s workload):

| Cell | Mode | Write failures / rows | W peak (= end of W) | `Rejecting mutation` WARN | Segments created / forbidden | `deleteOld` (in W) / `Freed up` | Release (2 links deleted) → first CDC write accepted | Live switch → first accepted; links before → after | Evidence |
|---|---|---|---|---|---|---|---|---|---|
| 128, r1/r2 | blocking | 4,612 / 6,144 | **96** (3 links) | 18 | 14 / 4 | 0 (6 after the switch) / 6 | 1,323 / 1,322 ms | 561 / 558 ms; 3 → 4 | `cluster/b128-r*/summary.txt` |
| 256, r1/r2 | blocking | 8,201 / 12,288 | **256** (8 links) | 20 | 18 / 3 | 0 (6) / 6 | 1,317 / 1,326 ms | 554 / 554 ms; 7 → 8 | `cluster/b256-r*` |
| 512, r1/r2 | blocking | 16,401 / 24,576 | **512** (16 links) | 24 | 26 / 3 | 0 (6) / 6 | 1,319 / 1,321 ms | 545 / 556 ms; 15 → 16 | `cluster/b512-r*` |
| 16, r1/r2 | blocking | 6,144 / 6,144 | **0** (no link) | 13 | 9 / 2 | 0 (7) / 7 | skipped (k = 0) | 571 / 590 ms; 0 → 2 | `cluster/b16-r*` |
| 128, r1/r2 | non-blocking | 0 / 6,144 | 128 (4 links) | 0 | 15 / 0 | 8–9 (9–10 total) / 9–10 | n/a | n/a | `cluster/nb128-r*` |
| 256, r1/r2 | non-blocking | 0 / 12,288 | 256 (8 links) | 0 | 27 / 0 | 15–16 (16–17 total) / 16–17 | n/a | n/a | `cluster/nb256-r*` |
| 512, r1/r2 | non-blocking | 0 / 24,576 | 512 (16 links) | 0 | 51 / 0 | 29–30 (30–31) / 30–31 | n/a | n/a | `cluster/nb512-r*` |
| 16, r1/r2 | non-blocking | 0 / 6,144 | **64** (2 links) | 0 | 15 / 0 | 12 (15) / 15 | n/a | n/a | `cluster/nb16-r*` |
| 4096, blocking r1/r2; non-blocking r1 (volume 1,536) | both | 0 / 24,576 | **1,600** (50 links), growing to the end | 0 | 51 / 0 | 0 / 0 | n/a | n/a | `cluster/b4096-r*`, `nb4096-r1` |
| control non-CDC table, cap 128, blocking, r1/r2 | blocking | 0 / 6,144 | **160** (5 links), 64 at the end | 0 | 15 / 8 | 0 / 0 | n/a | n/a | `cluster/plainb128-r*` |
| control `cdc_enabled=false`, cap 128, r1 | n/a | 0 / 6,144 | 0 | 0 | none | none | n/a | n/a | `cluster/cdcoff128-r1` |

Each blocking cell's accepted rows match its plateau (rows accepted x 64 KiB = 95.75, 255.4 and 510.9 MiB against plateaus 96, 256, 512). The two repeats of every cell gave identical plateaus. The commit log directory ended at 256 to 320 MiB in the blocking cells and at 64 MiB in the non-blocking cells, independent of the cap (`cluster-readings.md`, last column). The 2-s `du -sb` samples (`du.txt`) never exceeded the 50-ms peak by more than the cells that were refilled after the workload (blocking cells reach their cap again in step 7).

### 4.2 Conclusion and logic

1. **Validity.** The limit was reached in every capped cell: blocking cells created forbidden segments (3 to 4 per run, 2 at 16 MiB) and rejected two thirds or more of the rows (66.7 to 100 %) [observed: `cluster/b*/summary.txt`, `cluster-readings.md`]; non-blocking cells created 15 to 51 segments and ran 9 to 31 `deleteOld` passes during the workload [observed: `cluster/nb*/cdc-verdict.txt`, `summary.txt`]; the unit cells created 7 to 67 segments, 3 forbidden in every blocking cell [observed: `unit-readings.md`]. Settings took effect (segment 32 MiB, `cdc_total_space`, `cdc_block_writes`, `cdc_enabled`) [observed: `unit/*/readings.txt` `config` lines; `cluster/*/settings.txt`, `yaml.diff`]. The 4096 MiB control wrote 1,536 MiB of CDC data to `cdc_raw` without a cap binding, so the workload could fill the directory [observed: `cluster/b4096-r1/summary.txt`]. Valid.
2. **Readings.** Two sets of readings differ from the filed numbers and are listed in part 6. The blocking plateau sits at k − 1 segments at 128 MiB (3 links) and at k at 256 and 512 MiB; the unit tier shows the same alternation (224 and 480 MiB in 3 of 12 repeats, the rest exactly n) [observed: `unit-readings.md`, `cluster-readings.md`]. Non-blocking peaks at k + 1 links (a transient) in the unit tier and at k in the cluster tier's 50-ms samples [observed].
3. **Matched row.** Unit tier, B2g row 1: "Final and peak `du` within `n + about 2 segments` in both modes, tracker agrees with `du` within one segment | Claim holds at unit level". Final du ≤ n in all 12 blocking cells and ≤ n + 1 segment in all 12 non-blocking cells; peak du ≤ n (blocking) and ≤ n + 1 segment (non-blocking); the tracker equalled du in every cell [observed: `selfcheck.txt`, `unit-readings.md`]. Cluster tier, B3g row 1: "Plateau at about the cap (within 2 segments), scaling with the knob, in both modes | Claim confirmed". Blocking plateaus 96, 256, 512 MiB at caps 128, 256, 512 (within 1 segment below the cap); non-blocking 128, 256, 512 exactly; each pair of plateaus doubles with the knob (256/128 = 2.67 blocking, 2.0 non-blocking; 512/256 = 2.0 in both), identical in the two repeats; the disallow branch fired (rejections: `CDCWriteException` lines 7,280 / 13,428 / 25,724 in `system.log`, WARN entries, forbidden segments; deletions: 9 to 31 `deleteOld` passes with matching `Freed up` DEBUG lines) [observed: `cluster-readings.md`, `cluster/*/cdc-verdict.txt`].
4. **Excluded rows.** B2g row 2 (du grows with the volume past n + 2 segments): du was flat from the first rejection in blocking and held at n to n + 1 segment as the volume tripled in non-blocking (the 4096 control did grow, 544 MiB for 384 MiB written) [observed: `selfcheck.txt`]. Row 3 (blocking, zero rejections while du exceeds n + segment): rejections occurred in every blocking cell and du never exceeded n. Row 4 (non-blocking without `Freed up` while du exceeds n): `deleteOld` ran 6 to 28 times per cell and du did not exceed n + 1 segment. Row 5 (tracker 0 after a `Freed up` line while files remain): the minimum tracker value after any pass was ≥ 32 MiB; the only return of 0 was the 16 MiB cluster cell's first pass, where no link existed yet [observed: `cluster/nb16-r1/cdc-verdict.txt`, `unit-readings.md`]. Row 6 (total written < n): attempted volume was 3 x n. B3g row 2 (du keeps growing): flat during the workload; row 3 (blocking, no failures above cap + 2): failures in every capped blocking cell; row 4 (non-blocking, no deletions): deletions in every cell; row 5 (writes do not resume after the two-link deletion): they resumed (part 6); row 6 (never reaches the cap): reached; row 7 (16 MiB exceeds the cap in non-blocking): expected and observed (64 MiB), not a refutation.
5. **Observed vs. inferred.** Inferred: (a) that `du` of `cdc_raw` (apparent bytes of hard links) is the disk the cap governs — the links share the commit log's inodes, so freeing blocks needs the commit-log copy gone too [inferred: A4, not measured; allocated bytes were smaller than apparent in the unit run, `du` line in `readings.txt`]; (b) that the k − 1 plateau at an exact multiple comes from index-file bytes entering the tracker (`sip` read 33,554,450 in the 48 MiB check cell) [inferred: instrument-check line, not tested at 128]; (c) that the 1.3 s release time is dominated by two `cqlsh` starts (~0.55 s each, from the 0.55 s switch probe) [inferred: `switch` rows]. The conclusion does not depend on (b) or (c).
6. **Deviations and gaps.** (i) **B3f's blocking plateau range `128..192` for a 128 MiB cap was missed**: observed 96 MiB (n − 1 segment) in both repeats; B3g row 1 ("within 2 segments") still holds. (ii) **B3f's 16 MiB non-blocking value "about one segment (about 32 MiB)" was missed**: observed 64 MiB (2 links), steady; B3g row 7 ("exceeds the cap … expected") holds. (iii) **The B2h / B3h control "a non-CDC table must not grow `cdc_raw`" does not hold**: a non-CDC workload made links up to 160 MiB (cap + 1 segment, unit and cluster; 5 links) which were deleted as their segments were discarded (64 MiB at the end in the cluster, 32 to 64 in the unit): `processNewSegment` permits and links every new segment before it knows whether it will hold CDC data. No conclusions row covers this reading: **Not confirmed (no matching row)**. It does not affect the cap (peak ≤ cap + 1 segment), but a non-CDC writer does consume the budget transiently. (iv) The resume time (1.32 s) is measured with a client (`cqlsh`) whose own start-up is ~0.55 s, so B3g row 5's "about 3 walk intervals" (0.75 s) cannot be resolved more finely than that; writes did resume on the second probe in all 6 releases (the 16 MiB cells skip it). (v) The default cap (4096 MiB here) was not driven; 32 MiB segments only (the guided file's second-knob arm is not part of this file). (vi) Unit runs were 3 repeats, cluster 2, the 4096 non-blocking and `cdc_enabled=false` cells 1. (vii) Trace integrity: the DEBUG `Freed up` count equals the Byteman `deleteOld` count in every cluster cell (`summary.txt` `traces:` line), so the trace is not dropping calls. (viii) The 2-s `du -sb` maximum equals the 50-ms sampler's whole-run peak in every cell (`cluster-readings.md`), so the coarse sampling of B3d would have given the same numbers here.
7. **Core question.** Usage followed the constraint: the real bytes in `cdc_raw` stopped at the knob (blocking: at k or k − 1 whole segments, then every CDC write was rejected; non-blocking: at k, with a transient k + 1 in the unit tier, held by 6 to 31 deletions of the oldest links per cell) and the plateau doubled each time the knob doubled, in both tiers and in both repeats (parts 3 and 4; B2 step 4 and B3 step "dose-response"). The control with the cap out of reach grew with the volume (544 and 1,600 MiB), so the plateaus are the cap's doing and not the workload's. The constraint caps the directory, softly (a segment under the cap in blocking mode, one over in non-blocking, 2 segments over for a cap below one segment), and only for the segments the manager has linked: a non-CDC writer also takes budget transiently.

**Conclusion (one line):** Unit: B2g row 1 — Confirmed, claim holds (caps). Cluster: B3g row 1 — Confirmed, claim holds (caps).

## 5. Self-check of run 1 — AI

### 5.1 Check of run 1's conclusion

`run1/selfcheck.py` re-parses the committed excerpts (not the harness scripts) against every filed sub-prediction: 221 PASS, 10 MISS (`run1/selfcheck.txt`); the MISS lines are exactly the three gaps in §4.2 part 6 (i) to (iii).

| Part | Holds? | Note (file re-read) |
|---|---|---|
| 1. Validity | yes | Re-read `unit/*/readings.txt` (`config`, `writesDone`) and `cluster/*/summary.txt`: forbidden segments, WARN, `deleteOld` and `Freed up` counts as stated; `b4096-r1/summary.txt` shows 1,600 MiB. |
| 2. Readings | yes | The k − 1 / k alternation reproduced from the table rows; the 16 MiB and non-CDC readings re-read in `nb16-r1/summary.txt` (`final listing`) and `plainb128-r1/summary.txt`. |
| 3. Matched row | yes | Every number in part 3 recomputed in `selfcheck.txt`. The doubling ratio for blocking 128 → 256 is 2.67 because 128 sits at 96, so "doubles" is within one segment, not exact; stated. |
| 4. Excluded rows | yes | Each excluded row has a reading in `selfcheck.txt` or `cdc-verdict.txt`; the tracker-0 row was checked for all 21 traced cluster cells (one return of 0, the first pass at 16 MiB, with no link on disk yet). |
| 5. Observed vs. inferred | yes | (a) is the largest: the cap governs apparent link bytes; the inode sharing is read from the source, not measured. The conclusion states it as the quantity measured, not as freed blocks. |
| 6. Deviations and gaps | yes | The three misses and the resume-time resolution are recorded; none changes the matched row. |
| 7. Core question | yes | The logic follows B1: ceiling follows the knob (parts 3), disallow branch fired (parts 1, 3), the control grows (part 1, 7). |

### 5.2 Run 2?

**No** — decided 2026-10-22. The two tiers agree with each other and across repeats (identical plateaus at every capped value, all 22 cluster cells complete), the conclusion is a confirmation of a positive estimate, and the inferred statements do not carry it.

## 6. Run 2 — fresh AI session (optional)

Not done.

## 8. Verdict — AI

**Stage-3 estimate:** positive.

**Claim tested:** B1 — with CDC enabled, the total bytes in `cdc_raw_directory` stay at most `cdc_total_space` plus a small bounded slack (a few `commitlog_segment_size` segments), in blocking mode (writes rejected) and non-blocking mode (oldest links deleted), with no consumer. "Confirmed" means this held.

| Tier | Verdict (B2g / B3g row) | Effect on the constraint | Basis | Date |
|---|---|---|---|---|
| Unit | **Confirmed** — B2g row 1 (du ≤ n blocking, ≤ n + 1 segment non-blocking, tracker = du); sub-predictions missed: none in the matrix, one control ("non-CDC table leaves `cdc_raw` empty") Not confirmed (no matching row) | caps (soft: whole segments; transient + 1 segment in non-blocking) | run 1 + self-check | 2026-10-22 |
| Cluster | **Confirmed** — B3g row 1 (plateaus 96 / 256 / 512 blocking and 128 / 256 / 512 non-blocking at caps 128 / 256 / 512; 16 MiB boundary 0 and 64 MiB; control 1,600 MiB); sub-predictions missed: the 128 MiB blocking plateau range and the 16 MiB non-blocking size | caps (soft) | run 1 + self-check | 2026-10-22 |

**Feedback filed:** the case file's section D updated (uncommitted); amendments to B2b, B2h, B3c, B3e (step 6), and one B3g row, dated 2026-10-22, all before any reading. `_INDEX.md`, `HANDOFF.md` and `predicted-negative.md` not edited (the coordinator does).
