# commitlog_total_space-maybeFlushToReclaim-unused--autonomous — stage-4 results  <!-- file: results/commitlog_total_space-maybeFlushToReclaim-unused--autonomous.md; the stem ends in --guided or --autonomous -->
> **Case:** [`commitlog_total_space-maybeFlushToReclaim-unused--autonomous`](../../stage3-ai-deep-read/cases/commitlog_total_space-maybeFlushToReclaim-unused--autonomous.md)
>
> **Status:** **Closed 2026-10-21: unit Confirmed, cluster Confirmed, caps (soft)** (the autonomous estimate, positive soft cap, matched; it contradicts `predicted-negative.md` §9's earlier negative entry). Both tiers match the R3 row 4 ("bounded, overshoot larger than predicted"). Missed sub-predictions: unit C = 50 peaked at 75 MiB against a 70 MiB bound; cluster C = 1024 peaked at 1,184 MiB against 1,152 MiB; the unthrottled cluster probe peaked at 2,048 MiB = 8 × C, against < 1 GiB. No run 2.
>
> **Agent:** autonomous (the suffix of the case-file stem). For an autonomous
> file, "§9a" below means each tier's predictions and conclusions table: B2f and B2g
> (unit), B3f and B3g (cluster); "§9b–§9e" means B2a–B2e or B3a–B3e; and the case
> file's feedback section is its section D, not §10. One results file per case file.

**Relative links in this template** are written for where a *copy* of it lives
— inside `results/` — not for the template's own location one level up.

## 1. Before run 1 — design audit and freeze

| Field | Content |
|---|---|
| **Case-file version** | Autonomous file. As filed: sha256 `3c79fe51604d5153fb70a3953e0117a150b649426f1658e6bf04749d4326f76e`. After the audit's amendments R1–R4 (the frozen version; `sha256sum` at 2026-10-21 13:36 EDT, before any harness run or reading): **`6a58e10faa5efc74f005dbcb4c3aad12aeffd06ca2372c8ee55be15785f78a8d`** (copy `pc06:~/stage4-logs/cts/case-file-frozen.md`). Commit holding the file: **none**, because the case file is untracked in the working tree (filed the same day, not committed). |
| **Harness** | [`harness/commitlog_total_space-maybeFlushToReclaim-unused--autonomous/`](../harness/commitlog_total_space-maybeFlushToReclaim-unused--autonomous/README.md): `CommitLogTotalSpaceCapTest.java` + `unit-run.sh` (B2), `cluster-run.sh` + `cluster-chain.sh` (B3; includes the 1-s `du` sampler and the 10-s JMX sampler), `analyze.py` (`EXPECTED:` lines), `selfcheck.py`. Not committed; md5 of the node copies in `run1/harness.md5` (identical to the repo copies). **Instrument checks (not readings):** test compiled (`ant build-test`, 12 s); unit shakedown 1 (N = 40) found harness defect H1, the flush-reason count; unit shakedown 2 confirmed the fix; cluster shakedown (n = 300,000 at 256 MiB) confirmed config read-back, samplers, stress summary, flush counts and node stop (`run1/*shakedown*`). |
| **Tiers and values** | Unit (B2): `commitlog_total_space` C ∈ {15, 25, 50, 100000 (control)} MiB at a 10-ms throttle, plus a probe at C = 25 with no throttle; 300 × 1 MiB mutations, 5 MiB mmap segments. Cluster (B3): C ∈ {256, 1024, 16384 (control)} MiB at 20,000 writes/s, plus the probe `256p` with no throttle; 3,000,000 × 1 KiB rows, 32 MiB mmap segments, one node. |
| **Audit bottom line** | **Ready after amendments**, 2026-10-21 |

### 1.1 Design audit

Citations spot-checked in the pinned clone (`cassandra-src` at `cassandra-5.0.9`, read-only) and in the run clone `pc06:~/cassandra-cts` (`b5f2a54210`).

| Group | Check | Rating (Met / Partly / Not met) | Note (section checked) |
|---|---|---|---|
| A. Core question | constrained quantity is memory or disk bytes | Met | A2: commit-log segment bytes in `commitlog_directory`; the operand `size` is a byte counter. |
| A. Core question | knob varied, ≥ 3 values incl. default — or another approach, with the reason | Partly | Three or four values per tier, plus an uncapped control. The default, min(8192 MiB, ¼ of the volume) = 8192 MiB on this node, is not among them. Against these workloads (375 MiB and 3.2 GiB) the default behaves like the control. Exercising it needs > 8 GiB of commit log with no memtable-limit flush. Left for stage 3 (R5). |
| A. Core question | real resource measured, not only the counter (gap named) | Met | B2d `dirBytes` (sum of file lengths) beside `onDiskSize`; B3d `du -sb`/`du -sk` and the file count. The counter-vs-real outcome lacked a row (R3). |
| A. Core question | usage driven to the limit and past it | Met | B2c: 375 MiB against 15–50 MiB; B3c: 3.2 GiB against 256 and 1024 MiB. |
| A. Core question | positive control for a negative estimate | n/a | The estimate is positive. The uncapped control shows the workload grows the log. |
| B. Logic | each step says what it establishes | Met | B2h/B3h say what each control rules out. |
| B. Logic | prediction stated in numbers or a clear relation | Met | B2f/B3f bounds C + 4S, C + S, flush counts, and monotone ordering. |
| B. Logic | every plausible outcome has a conclusions row with its evidence | Partly | The rows lacked verdict labels; "well above" was not defined; and there were no rows for *counter bounded but real bytes grow*, *bounded with no `COMMITLOG_DIRTY` flush*, or *probe outruns the cap*. Amended (R3). |
| B. Logic | confirmation needs ceiling-follows-knob and direct disallow evidence | Partly | Unit: the flush-reason grep was "optional", with only the switch count (a proxy) as evidence. Made required (R2), and part of the Confirmed row (R3). Cluster: B3g row 1 already needed aligned `COMMITLOG_DIRTY` flushes. |
| B. Logic | alternative explanations and their controls | Partly | Memtable-limit flushes are ruled out by the cleanup threshold and the control's 0 count. But in the unit tier the control's memtable (~300 MiB) exceeds the real default limit, 256 MiB under the 1 GiB test heap (R1). Amended. |
| C. Specific | a human can follow it from the intro and the prediction/conclusions | Met | Estimate line, A3, B1. |
| C. Specific | an AI can run the runbook without re-deriving the code path | Partly | Test log path and rotation (`build/test/logs/<tag>/…`, DEBUG, 20 MB `.gz` rolls), log accumulation across arms, and `System.out` fragmenting through the logger (R2). The node's `ulimit -n` and the start wait (R4). |
| C. Specific | knob, values, workload, commands, observables, sampling, stop conditions exact | Met | Commands and arithmetic are given in full. Stress syntax checked: `throttle=` accepts `[0-9]+/s` (`SettingsRate.java:87`), and `no-warmup` exists (`SettingsCommand.java:124`). |
| D. Runnable | harness and environment prerequisites exist or are listed | Met | Full test code given. The run scripts and the sampler are step-1 work. |
| D. Runnable | workload arithmetic reaches the limit (data, time, disk, memory) | Partly | Unit heap: the file assumed `-Xmx4G`, but `testsome` forks with `maxmemory="1024m"` (`build.xml:1152`) (R1). Cluster: about 4 GiB of commit log and about 4 GiB of data per arm on `/` (55 GB free); 16 GiB heap on 251 GiB of RAM. |
| D. Runnable | load-bearing citations spot-checked against the pinned clone | Met | `AbstractCommitLogSegmentManager.java:103` (`size`), `:108` (wait condition), `:163-238` (allocator; `createSegment` `:189`, skip `:194-196`, `maybeFlushToReclaim` `:200`), `:246-264` (line 249 `if (unused < 0)`; `allocatingFrom` break `:255`), `:406-414`, `:432-451` (`unusedCapacity` in `long`, no overflow), `:458-503` (`forceFlush(maxCommitLogPosition)` `:496`); `ColumnFamilyStore.java:1055` (log line), `:1084-1092` (`COMMITLOG_DIRTY`), `:1152`; `CommitLog.java:83` (public `segmentManager`), `:353-369`, `:439-442`; `CommitLogSegmentManagerStandard.java:31-60`; `MemoryMappedSegment.java:62-63`, `:103-106`; `CommitLogSegment.java:430-436`, `:611-620`; `CommitLogMetrics.java:74-80`; `Config.java:389-390`, `:397`, `:401`; `DatabaseDescriptor.java:586-587`, `:664-675`, `:761-773` (cleanup threshold ≤ 0.99), `:897-899`, `:1147-1162`, `:1525-1528`, `:3829-3832` (returns `long`); `AbstractAllocatorMemtable.java:59`, `:78-83`; `SchemaLoader.standardCFMD` (`key`, `val`, clustering `name`); `MemtableParams.get`, and `skiplist` in the test yaml; `File.tryList()` (`File.java:514`); `conf/cassandra.yaml:97,395,408,431,611,660,678,797,799,812,825,883`. All hold. |

| # | Recommendation | Applied? (amendment date and commit, or "left for stage 3") | Why |
|---|---|---|---|
| R1 | B2a/B2c: the test JVM heap is 1 GiB (`build.xml:1152`), so the default `memtable_heap_space` is 256 MiB. Set it to 768 MiB in the test before the pool loads. Run from the clone `~/cassandra-cts`, outputs under `~/stage4-logs/cts/unit/` | Applied 2026-10-21 (note after B2a; not committed) | Without it the control would flush on `MEMTABLE_LIMIT` at ≈ 253 MiB, and B2g row 5 would make the unit tier invalid whatever the cap does |
| R2 | B2d/B2e: make the `COMMITLOG_DIRTY` count required; give the log path, its DEBUG rotation and accumulation (clear `build/test/logs` per arm, `zgrep -r`); print `SUMMARY` as one string and also to a file | Applied 2026-10-21 (notes after B2d and B2e step 3) | Direct evidence that the true branch fired; the filed glob `build/test/logs/*.log` matches nothing |
| R3 | B2g/B3g: a verdict label per row; "well above" made exact (C + 4S < peak < 0.8 × control); three new rows (counter-only cap → Refuted for disk; no `COMMITLOG_DIRTY` → Not confirmed; probe ≥ 0.8 × control → bypass) | Applied 2026-10-21 (notes after B2g and B3g; changes the conclusions tables, for reasons independent of any reading, before run 1) | Group B requires every plausible outcome to have a row and a confirmation to rest on the disallow evidence |
| R4 | B3a/B3e/B4: clone `~/cassandra-cts`; outputs `~/stage4-logs/cts/cluster/`; `ulimit -n 100000`; wait for `statusbinary`; check daemons by `ps … '[j]ava.*CassandraDaemon'`; probe label `256p` | Applied 2026-10-21 (note after B3a; not committed) | The peer node's soft fd limit is 1024; `pgrep -f` inside ssh matches its own shell |
| R5 | Include the default (8192 MiB on this volume) as a value, with a workload above 8 GiB of commit log and memtable limits that stay out of the way | Left for stage 3 | Not needed for this positive claim (the cap is shown at three explicit values); the default behaves like the control here |

**Agreement criteria:** not filled (no run 2 chosen yet).

## 2. Environment

| Field | Run 1 | Run 2 (fresh AI session, if done) |
|---|---|---|
| Date | 2026-10-21 (node clock MDT). Audit and freeze 11:36. Unit shakedown 1 11:37–11:38. Pause (API usage limit) until about 15:40. Unit shakedown 2 15:41. Unit run 1 15:41:52–15:43:34. Cluster shakedown 15:43–15:46. Cluster run 1 15:46:17–16:02:53 | not done |
| Node (CloudLab name and type) | `pc06` = `node2.jason92-320876.misconfiguration-pg0.cloudlab.umass.edu` (40 cores, 251 GiB); no other agent on it; the session drove it over ssh from `pc07` | — |
| OS and kernel (`uname -r`) | Ubuntu 22.04.2 LTS, `5.15.0-187-generic` | — |
| JDK (`java -version`) | openjdk 11.0.32.1 (2026-08-18) | — |
| Ant (`ant -version`) | 1.10.12 | — |
| Local `cassandra-src` clone commit | `pc06:~/cassandra-cts`, a fresh clone at `cassandra-5.0.9` (`b5f2a54210d541339c2e7c17a794195cac0e67c2`). `ant build-test` took 1 min 7 s, `BUILD SUCCESSFUL`. Only the harness test was added, and it was removed after the run | — |
| Case-file commit / harness commit | none / none (both untracked); frozen sha256 `6a58e10f…` | — |
| Storage for node data | Unit: `~/cassandra-cts/build/test/cassandra` on local `/dev/sda3` (ext3, spinning disk). Cluster: `RUN=/tmp/clcap` on the same `/dev/sda3` (55 GB free), wiped after each arm | — |
| Full logs (path, outside the repo) | `pc06:~/stage4-logs/cts/`: `run1/unit/<arm>/` (with `ant.log` and the raw DEBUG test-log tree), `run1/cluster/<arm>/` (full `system.log`, `debug.log.gz`, `gc.log*`, `stress.out`, `stress.log.gz`, the samplers), `run1/{analysis,selfcheck}.txt`, the shakedowns, `case-file-frozen.md`, `build-test*.log` (18 MB) | — |

## 3. Runbook defects

| # | Run | Step (§9b–§9e) | Problem | Fix | Decision (date) | Case-file commit with the fix |
|---|---|---|---|---|---|---|
| H1 | unit shakedown 1 (instrument check, before run 1) | B2e step 3 as amended (R2), flush-reason count | `zgrep -rh … build/test/logs` printed 0 although the test log held 4 `COMMITLOG_DIRTY` lines for `CLCapKS.t`: `zgrep -r` does not recurse on this host | `unit-run.sh` reads every file under the log tree, plain or `.gz`, with `find … \| xargs zcat -f`. Checked in shakedown 2. The case file's R2 note names `zgrep` as the method; the observable is unchanged | 2026-10-21, harness only (noted in section D) | none |
| H2 | analysis (after run 1) | `analyze.py`, B3f "`du -sb` ≈ 32 MiB × file count" | The script checked **exact** equality. `du` and `ls` are read a moment apart, so 1–2 samples per arm differ by one segment while a segment is created or deleted. "≈" holds. | `selfcheck.py` checks the B3f relation within one segment (2/214, 1/215, 1/215, 2/95 samples differ, by 32 MiB at most). `analyze.py`'s `NO` on this line is recorded as the script's own strictness, not a missed prediction | 2026-10-21 | — |
| H3 | self-check (after run 1) | `selfcheck.py`, segment deletions | The first version counted `debug.log` segment deletions over the whole node lifetime, including the shutdown flush after the settle window (98 in every arm, including the control). | Deletions are filtered to times ≤ settle end (control 0, capped 91–93). The flush-to-deletion check was correct in both versions | 2026-10-21 | — |

## 4. Run 1

**Scope:** unit B2 (all five arms, N = 300); cluster B3 (256, 1024, 16384, 256p, n = 3,000,000 each). **Command log:**
[`commitlog_total_space-maybeFlushToReclaim-unused--autonomous/run1/`](commitlog_total_space-maybeFlushToReclaim-unused--autonomous/run1/):
- Unit: `unit/session.log`; per arm, `unit/<arm>/{cap.csv,cap.csv.summary,reasons.txt,ant-excerpt.txt,testlog-flush-excerpt.txt,TEST-*.xml}`.
- Cluster: `cluster/chain.log`; per arm, `cluster/<arm>/{session.log,du.csv,jmx.csv,flushes.txt,counts.txt,times.txt,yaml.diff,config-excerpt.txt,segment-deletions.txt,stress-results-excerpt.txt}`.
- Also `analysis.txt`, `selfcheck.py`, `selfcheck.txt`, and the shakedown logs.

### 4.1 Readings

**Unit tier** (`unit/<arm>/cap.csv`, `reasons.txt`, `ant-excerpt.txt`). JUnit passed 1/1 in every arm. Every arm read back `segMiB=5 heapMaxMiB=1007 memtableHeapMiB=768 cleanup=0.99 accessMode=mmap`. S = 5 MiB.

| Test or assertion | Result | Evidence (file) |
|---|---|---|
| C = 15, 10 ms | peak `onDiskSize` 30 MiB (bound 35); final 15 (bound 20); switches 38 (≥ 15); `COMMITLOG_DIRTY` 38, `MEMTABLE_LIMIT` 0; 38 falls in the trace | `unit/cap15-s10/*` |
| C = 25, 10 ms | peak 40 (bound 45); final 20 (bound 30); switches 18 (≥ 10); `COMMITLOG_DIRTY` 18, `MEMTABLE_LIMIT` 0; 21 falls | `unit/cap25-s10/*` |
| C = 50, 10 ms | **peak 75 (bound 70: missed by one segment)**; final 20 (bound 55); switches 8 (≥ 5); `COMMITLOG_DIRTY` 8, `MEMTABLE_LIMIT` 0; 14 falls | `unit/cap50-s10/*` |
| C = 100000 (control) | peak = final = 380 MiB (predicted 375–400), monotone; switches 0; 0 flushes of `CLCapKS.t` for any reason | `unit/cap100000-s10/*` |
| C = 25, no throttle (probe) | peak 100 MiB = 4 × C (predicted 45–150); `dirBytes` peak 95; final 15 (≤ 30); switches 19; `COMMITLOG_DIRTY` 19 | `unit/cap25-s0/*` |
| shape | `onDiskSize` always a multiple of 5 MiB; \|`dirBytes` − `onDiskSize`\| ≤ 5 MiB in every sample; peaks 30 < 40 < 75 < 380; switches 38 > 18 > 8 > 0; switches = number of `COMMITLOG_DIRTY` lines in every arm | `analysis.txt`, `selfcheck.txt` |

**Cluster tier** (`cluster/<arm>/*`). Every arm wrote 3,000,000 partitions with 0 errors. The throttled arms took 157–158 s at 19,9xx op/s; the probe took 36 s at 107,488 op/s. The config read-back in `system.log` matched each arm. S = 32 MiB; `du -sb` includes the directory's own 4,096 B.

| Capacity value | Run (control / A / B / C) | Observable (§9d) | Reading | Evidence (file) |
|---|---|---|---|---|
| 256 MiB | A | peak `du -sb` commit log | **352 MiB** (bound 384) at +63 s; sawtooth between 96 and 352 MiB (mode 256) | `256/du.csv` |
| | | level after 60 s settle | 256 MiB (bound 288) | same |
| | | `standard1` flushes by reason | `COMMITLOG_DIRTY` 13 (≥ 8; predicted ≈ 12), `MEMTABLE_LIMIT` 0; each followed within 60 s by segment deletions and a fall of `du` (13/13) | `256/flushes.txt`, `segment-deletions.txt` |
| | | JMX `TotalCommitLogSize`, 10-s samples | peak 320 MiB | `256/jmx.csv` |
| 1024 MiB | B | peak; settle | **1,184 MiB** (bound 1,152: missed by one segment) at +60 s; 192 MiB (bound 1,056) | `1024/du.csv` |
| | | flushes | `COMMITLOG_DIRTY` 3 (≥ 2; ≈ 3), `MEMTABLE_LIMIT` 0; 3/3 followed by deletion and a fall | `1024/flushes.txt` |
| 16384 MiB | control | peak; settle | 3,168 MiB (≥ 2.8 GiB), rising to the end of the writes (+156 s); settle = peak | `16384/du.csv` |
| | | flushes | 0 `COMMITLOG_DIRTY`, 0 `MEMTABLE_LIMIT`; data dir 0 MiB at settle end; 0 segment deletions before settle end | `16384/flushes.txt`, `segment-deletions.txt` |
| 256 MiB, unthrottled | probe `256p` | peak; settle | **2,048 MiB = 8 × C = 0.646 × control** (predicted < 1 GiB: missed). Rising through the 36-s write to its end (+34 s), then down to 224 MiB within about 22 s | `256p/du.csv` |
| | | flushes | `COMMITLOG_DIRTY` 13, about one every 1.8 s, each of about 220 MiB off-heap; `MEMTABLE_LIMIT` 0; 13/13 followed by deletion and a fall | `256p/flushes.txt` |
| all | — | `du -sb` vs 32 MiB × files | equal within one segment (1–2 samples per arm differ, H2) | `selfcheck.txt` |

Run-script totals (`analysis.txt`): 51 `EXPECTED` yes and 4 no. The four are the unit C = 50 peak, the cluster 1024 peak, the cluster probe peak, and the exact-equality `du` line (H2).

### 4.2 Conclusion and logic

1. **Validity.**
   - Unit: each arm read back its knob, 5 MiB mmap segments, a 768 MiB memtable limit and the 0.99 threshold, and wrote 300 × 1 MiB plus 10 settle rows [observed: `ant-excerpt.txt`, `cap.csv`]. The control reached 380 MiB, more than 3 × the largest C, with 0 flushes [observed]. So B2g rows 5 and 6 do not apply.
   - Cluster: each arm's `commitlog_total_space` was in force [observed: `config-excerpt.txt`, `yaml.diff`] and wrote 3,000,000 rows with no error [observed: `stress-results-excerpt.txt`]. The control reached 3,168 MiB with 0 `MEMTABLE_LIMIT` flushes, so B3g rows 5 and 6 do not apply.
   - The limit was passed many times: 13 forced flushes at 256 MiB.
   - Valid.
2. **Readings.**
   - (a) Every capped peak is a whole number of segments above C: unit +3S, +3S and +5S; cluster +3S and +5S [observed]. A throttled run overshoots by one to five segments, as A3 says (the reserve segment is counted, and writes are not blocked).
   - (b) The unthrottled cluster probe asked for a flush every ~1.8 s, yet usage rose for the whole 36-s burst. The segments were deleted only after the writes stopped [observed: `256p/du.csv`, `flushes.txt`]. The flushes were requested on time but completed too slowly to free segments at ~110 MiB/s of commit log [inferred: flush completion is not logged per flush here; the deletions lag the requests].
   - (c) The unit switch count equals the `COMMITLOG_DIRTY` count in every arm [observed], so every memtable flush of the test table came from the line-249 path.
3. **Matched rows.**
   - Unit, **B2g row 4 as amended (R3)**: "peak > C + 4S but < 0.8 × the control's peak, with (b) COMMITLOG_DIRTY flushes and (c) drops → Confirmed — caps (soft), overshoot bound a missed sub-prediction". C = 50: 75 > 70 and 75 < 304. C = 15 and 25 meet row 1 outright. (b) holds: 38, 18 and 8 flushes. (c) holds: 38, 21 and 14 falls. (d) holds: the control has 0 flushes and is at 380 MiB.
   - Cluster, **B3g row 4 as amended**: C = 1024 peaked at 1,184 > 1,152 and < 0.8 × 3,168 = 2,534. C = 256 meets row 1: 352 ≤ 384, settle 256 ≤ 288, 13 flushes aligned with falls. The control rose to 3,168 MiB with 0 flushes.
   - The probe: 2,048 < 2,534, so it is a missed sub-prediction only, not the bypass row.
4. **Excluded rows.**
   - **Refuted** (capped peak ≥ 0.8 × control): ruled out by the ratios 0.079, 0.105 and 0.197 (unit) and 0.111 and 0.374 (cluster).
   - **Refuted for disk** (flushes but no drop): every flush was followed by deletions and a fall (13/13, 3/3), and every unit arm had falls.
   - **Counter-only cap** (`dirBytes`/`du` follows the control): unit `dirBytes` peaks equal the counter's (95 vs 100 in the probe). The cluster measured `du` directly, and its peaks are bounded.
   - **No `COMMITLOG_DIRTY`**: there were 8–38 per capped arm.
   - **Memtable-pressure leak**: the control had 0 flushes and `MEMTABLE_LIMIT` was 0 everywhere.
   - **Workload too small**: the controls reached 380 MiB (> 150) and 3,168 MiB (> 1.5 GiB).
   - **Knob not applied**: read back in every arm.
   - **Bypass (probe ≥ 0.8 × control)**: 0.263 (unit) and 0.646 (cluster).
5. **Observed vs. inferred.**
   - Inferred: the cause of the probe's climb, slow flush completion (2b). This is not used by the matched rows.
   - Inferred: the reading that each capped flush is "the line-249 branch firing". It rests on the source (`COMMITLOG_DIRTY` with a position is passed only by `flushDataFrom`, audited in §1). It is not a runtime trace of `unused`, which B2d says is not sampled.
6. **Deviations and gaps.**
   - Clone `~/cassandra-cts` and the output paths (R1/R4).
   - H1–H3 (harness only).
   - Three missed sub-predictions: unit C = 50 peak, cluster C = 1024 peak, cluster probe peak.
   - The default value (8192 MiB here) was not run (R5).
   - The probe's trajectory is limited by its 3 GiB workload: a longer unthrottled burst was not run, so whether it would stay below 0.8 × an uncapped run is not settled.
7. **Core question.** Usage follows the constraint.
   - With the same workload, peak commit-log disk use was 30, 40 and 75 MiB at C = 15, 25 and 50, against 380 MiB uncapped (unit). It was 352 and 1,184 MiB at C = 256 and 1024, against 3,168 MiB uncapped (cluster) [part 3].
   - Each time, it came back to about C or below after forced `COMMITLOG_DIRTY` flushes that the uncapped run never had [parts 1, 3, 4].
   - The cap is soft. A throttled writer overshoots it by one to five segments. An unthrottled writer, at about 110 MiB/s, overshot it eightfold during a 36-s burst, and usage came back down only after the burst [part 2].

**Conclusion (one line):** unit B2g row 4, cluster B3g row 4 (as amended R3): **Confirmed — caps (soft)**. Missed sub-predictions: unit C = 50 peak, cluster C = 1024 peak, cluster probe peak.

## 5. Self-check of run 1 — AI

### 5.1 Check of run 1's conclusion

Independent script [`run1/selfcheck.py`](commitlog_total_space-maybeFlushToReclaim-unused--autonomous/run1/selfcheck.py) re-reads the raw files on the node:
- Each `cap.csv`, split by hand.
- Every test-log file, plain or `.gz`, opened by its magic bytes.
- `ant.log`'s `SUMMARY`/`INFO` lines and the JUnit XML attributes.
- For each node, the full `system.log`, with flush timestamps parsed and limited to the settle end, and `debug.log.gz` (segment deletions).
- `du.csv`, `stress.out` and `times.txt`.

It does not read `reasons.txt`, `counts.txt`, `flushes.txt` or `analyze.py` output, and it re-applies B2g/B3g as amended. Output [`run1/selfcheck.txt`](commitlog_total_space-maybeFlushToReclaim-unused--autonomous/run1/selfcheck.txt): **84 ok, 3 FAIL**. The three failures are exactly the missed sub-predictions: unit C = 50 peak 75 > 70; cluster C = 1024 peak 1,184 > 1,152; probe 2,048 ≥ 1,024. Its matched rows: "UNIT ROW: row 4" and "CLUSTER ROW: row 4". Its figures agree with `analyze.py`'s for every arm.

| Part | Holds? (yes / no) | Note (file re-read) |
|---|---|---|
| 1. Validity | yes | Knob, segment size, memtable limit and threshold re-read in all five `ant.log`s; 300 + 10 rows per CSV; one CSV header (one JVM); config line in each `system.log`; 3,000,000 rows and 0 errors in each `stress.out`; sampler coverage with a maximum step ≤ 5 s |
| 2. Readings | yes | Overshoots in whole segments recomputed. The probe's climb to +34 s and the fall after the writes stopped re-read from `256p/du.csv` |
| 3. Matched row | yes | Ratios to the control, flush counts from the raw logs, falls, and flush → deletion → fall within 60 s (13/13 and 3/3) recomputed |
| 4. Excluded rows | yes | Each excluded row's contrary reading recomputed (Refuted ratios ≤ 0.374; control 0 flushes; `dirBytes` within one segment of the counter) |
| 5. Observed vs. inferred | yes | The one inference (the probe's flush completion) is not used by the matched rows |
| 6. Deviations and gaps | yes | H1–H3, R1/R4 paths and the three missed sub-predictions recorded; the default value and a longer probe named as gaps |
| 7. Core question | yes | Follows B1: the peak follows C at three values in each tier, the disallow branch fired (`COMMITLOG_DIRTY`) only when capped, and the real bytes, not only the counter, were bounded |

### 5.2 Run 2?

**No.** Decided 2026-10-21. The matched rows rest on counts and byte totals that the independent self-check re-derived from raw files. The result confirms the file's own estimate, so it neither refutes the case nor confirms a bypass. The open question, a longer unthrottled burst, is a new experiment, not a repeat (finding 2 below).

## 6. Run 2 — fresh AI session (optional)

Not done (§5.2); §7 left out.

## 8. Verdict — AI

Jingsong may overrule any verdict at any time; record an override here with its
date and reason.

**Stage-3 estimate:** positive (soft cap) in this autonomous file. `predicted-negative.md` §9 had earlier listed this line as negative ("the commit log can exceed it"); the run sides with this file, and the two descriptions do not conflict in substance: the cap is a reclaim target that the log exceeds by the writes made during a forced flush.

**Claim tested:** B1. "With `commitlog_total_space = C`, sustained writes keep commit-log disk use (the `size` operand and the real bytes in `commitlog_directory`) bounded near C: peak ≤ C + a small overshoot, which grows with write rate. Forced `COMMITLOG_DIRTY` flushes produce a sawtooth. With C far above the volume written, the same workload makes commit-log usage grow in step with the bytes written." "Confirmed" below means this claim held.

| Tier | Verdict (B2g / B3g row) | Effect on the constraint | Basis | Date |
|---|---|---|---|---|
| Unit | **Confirmed**, B2g row 4 (R3). Peaks 30 / 40 / 75 MiB at C = 15 / 25 / 50 against 380 MiB uncapped; final 15–20 MiB; 38 / 18 / 8 `COMMITLOG_DIRTY` flushes, 0 in the control. Unthrottled probe 100 MiB at C = 25. One sub-prediction missed (C = 50 peak 75 > 70) | caps (soft) | run 1 + self-check | 2026-10-21 |
| Cluster | **Confirmed**, B3g row 4 (R3). Peaks 352 / 1,184 MiB at C = 256 / 1024 against 3,168 MiB uncapped; settle 256 / 192 MiB; 13 / 3 `COMMITLOG_DIRTY` flushes of `standard1`, each followed by segment deletion and a fall of `du`; 0 in the control. Sub-predictions missed: C = 1024 peak (+1 segment) and the unthrottled probe (2,048 MiB = 8 × C) | caps (soft) | run 1 + self-check | 2026-10-21 |

**Findings beyond the claim (no §9a row):**
1. A throttled writer overshoots by one to five segments, so the floor-plus-reserve accounting in A3 holds.
2. **Against an unthrottled writer the cap does not bound usage while the burst lasts.** At about 107,000 writes/s (≈ 110 MiB/s of commit log), the allocator requested a flush every ~1.8 s, yet usage climbed to 8 × C, 0.65 × the uncapped run, until the 36-s burst ended. It came back below C about 20 s later. A longer burst would show whether this crosses the 0.8 × control "bypass" line. That is worth a stage-3 follow-up and a longer probe.
3. The default value (8192 MiB on this volume) was not exercised (R5).
4. The unit test JVM is 1 GiB under `ant testsome`, not 4 GiB (R1). This is relevant to any design that relies on the unit test heap.

**Feedback filed:** the case file's section D was updated on 2026-10-21; only section D changed after the freeze. The case file is not committed. New sha256: `86b89feea68ccd679cf03b2220814165e8da3b5ec3010d391e04fdd32e740328` (frozen `6a58e10f…`, filed `3c79fe51…`). `_INDEX.md`, `HANDOFF.md` and `predicted-negative.md` are left to the main session.
