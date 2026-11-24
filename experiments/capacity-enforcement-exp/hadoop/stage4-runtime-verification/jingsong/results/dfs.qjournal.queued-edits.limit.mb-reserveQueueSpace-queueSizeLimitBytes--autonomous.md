# dfs.qjournal.queued-edits.limit.mb-reserveQueueSpace-queueSizeLimitBytes--autonomous — stage-4 results  <!-- file: results/dfs.qjournal.queued-edits.limit.mb-reserveQueueSpace-queueSizeLimitBytes--autonomous.md -->

> **Case:** [`dfs.qjournal.queued-edits.limit.mb-reserveQueueSpace-queueSizeLimitBytes--autonomous`](../../../stage3-ai-deep-read/jingsong/cases/dfs.qjournal.queued-edits.limit.mb-reserveQueueSpace-queueSizeLimitBytes--autonomous.md) (order 19; written outside the
> repo at `~/writeup-hadoop/out/o19/dfs.qjournal.queued-edits.limit.mb-reserveQueueSpace-queueSizeLimitBytes--autonomous.md`)
>
> **Status:** verdict filed (2026-11-24) — unit Confirmed — caps; cluster Confirmed — caps
>
> **Outcome class:** true positive
>
> **Agent:** autonomous (the suffix of the case-file stem). "§9a" below means each tier's predictions and conclusions table: B2f and B2g
> (unit), B3f and B3g (cluster); "§9b–§9e" means B2a–B2e or B3a–B3e; and the case file's feedback section is its section D.

**Layout.** Hadoop, Jingsong's share, run by a stage-4 agent working as Jingsong. This file, the harness
(`~/writeup-hadoop/out/o19/harness/`) and small evidence copies (`~/writeup-hadoop/out/o19/run1/`) are outside the repository
(the parent session files them). Protocol: `experiments/capacity-enforcement-exp/stage4-runtime-verification/README.md`
("The run protocol"); environment: `hadoop/stage4-runtime-verification/jingsong/environment.md`. Below, `R` =
`/mydata/jingsong-s4/dfs.qjournal.queued-edits.limit.mb-reserveQueueSpace-queueSizeLimitBytes-run1` on `pc72`.

## 1. Before run 1 — design audit and freeze

| Field | Content |
|---|---|
| **Case-file version** | Autonomous file as written by stage 3 for order 19 (outside the repo). sha256 before the audit: `882377eb683c4530ebf26c6bebb9ca00d509bb87504db931c54a1a7ebc5abe86`. After the audit's amendments A1–A5 and D1, 2026-11-24, before any harness run or reading: whole-file sha256 **`80562b1dcae4afd75ad7f9a6459a472620cec0d5073c5b5af69aab246ec3cfc2`** (frozen version). Frozen predictions and conclusions (`sed -n '/^\*\*B2f\./,/^\*\*B2h\./p' <file> \| sed '$d' \| sha256sum`, B2f + B2g + A3): **`f777e321864263554d8f402ef3c38383a31d6b372c04498afd39c7020993e456`**; the same for B3f … B3h (B3f + B3g + A5): **`91d421251a8774c707f560f63f53d13d47a8b5bd3b9e025530cc4d7f2a080168`**. Both text hashes are unchanged after the run-1 defect fix and the feedback (checked). |
| **Harness** | `~/writeup-hadoop/out/o19/harness/`: `TestQueuedEditsCapProbe.java` (md5 `c05c0cc6…`), `unit-run.sh` (`51b40c65…`, after defect 1), `cluster-run.sh` (`96e4937d…`), `jmxtool.py` (`d65df733…`). Written after the freeze, before run 1; copied to `R/harness/`. Instrument checks: `TestIPCLoggerChannel#testQueueLimiting` (upstream reference) passes, and the probe's L = 1, b = 4096 line reproduces its numbers (256 batches, 1 048 576 B); the NN bean `IPCLoggerChannel-127.0.0.1-8489` was listed before each stop (`bean-L1-start.json`); `NNThroughputBenchmark` loaded with the A4 classpath (no junit jars needed). |
| **Tiers and values** | Unit (B2): L ∈ {0, 1, 4, unset = 10} × b ∈ {4096, 524 288}, blocked run + paced control each; overshoot (L = 1, 3 MiB then 4 KiB). Cluster (B3): L ∈ {1, unset = 10, 64, 512} with JN3 SIGSTOPped during 1 M mkdirs (16 threads), then a no-stop control at L = 64. |
| **Audit bottom line** | **Ready after amendments** — 2026-11-24 |

### 1.1 Design audit

| Group | Check | Rating | Note (section checked) |
|---|---|---|---|
| A. Core question | constrained quantity is memory or disk bytes | Met | A2/B1: NN heap bytes of `byte[]` edit batches queued per JN channel; operand `queuedEditsSizeBytes`. |
| A. Core question | knob varied, ≥ 3 values incl. default | Met | B2b: 0, 1, 4, unset (10); B3b: 1, unset (10), 64, 512. |
| A. Core question | real resource measured, not only the counter | Met (unit: Partly, gap named) | B3d.2: `jmap -histo:live` `[B` bytes at (a)/(b)/(c). Unit: weak-reference collectibility of the actual arrays (a reachability proxy, not bytes); MemoryMXBean optional and coarse. |
| A. Core question | usage driven to the limit and past it | Met | B2c: N = 2·⌈C/b⌉+4; B3c: W ≈ 100–200 MB ≫ 64 MiB, measured (A4.3). |
| A. Core question | positive control (negative estimate only) | n/a (positive estimate) | Ungoverned contrast L = 512 and the no-stop control are present anyway. |
| B. Logic | each step says what it establishes | Met | B2h/B3h. |
| B. Logic | prediction in numbers or a clear relation | Met | B2f exact table; B3f intervals (C − B, C] and ± tolerances. |
| B. Logic | every plausible outcome has a row with its evidence | Partly → Met | No verdict wording per row; missing "exact numbers off but capped", "refusal by another cause", "heap does not resolve", "W ≤ C", "L = 512 capped by something else". **Amended** (A3, A5). |
| B. Logic | confirmation needs ceiling-follows-knob and disallow evidence | Met | Ceiling vs L plus `LoggerTooFarBehindException` causes (unit) / WARN "is going to exceed limit size" (cluster, `IPCLoggerChannel.java:452-455`). |
| B. Logic | alternative explanations and their controls | Partly → Met | The unit control as written could itself overfill the queue (unpaced). **Amended** (A2.1). |
| C. Specific | a human can follow it from the intro and §9a | Met | Estimate, A3, B1. |
| C. Specific | an AI can run §9b–§9e without re-deriving | Partly → Met | `~/hadoop-3.4.2`, `/mydata/<run>/hadoop-base` absent (A1); JDK 11 `jmap` on PATH, benchmark classpath, W exactness (JN preallocation), sampler, order, stop conditions open (A4); unit output format and harness details (A2). |
| C. Specific | knob, values, workload, commands, observables, stop conditions exact | Partly → Met | as above (A2, A4). |
| D. Runnable | harness and prerequisites exist or are listed | Met | Test class, run scripts, sampler are step-1 work. JDK 8, Maven 3.6.3, 3.4.2 distribution on `pc72` (built 2026-11-24 by `setup-node.sh`, BUILD SUCCESS 33:04 min). |
| D. Runnable | workload arithmetic reaches the limit | Met | Unit ≤ 22 MiB per method. Cluster: ~1.5 × 10⁸ B edits per run, 3 JN copies ≈ 0.5 GB, NN 2 GiB heap; node 125 GiB RAM, 710 GB free on `/mydata`; ports 9000/9870/8480–8489 free. |
| D. Runnable | load-bearing citations spot-checked | Met | `systems/hadoop/source/` (clean, HEAD `8f76f2390`): `IPCLoggerChannel.java:112, 138, 171-173, 243-250, 346-349, 357-410, 448-463, 474-486`; `IPCLoggerChannelMetrics.java:78-110` (bean name, `QueuedEditsSize`); `DFSConfigKeys.java:1477-1478`; `hdfs-default.xml:5765-5770`; `QuorumOutputStream.java:104-113`; `AsyncLoggerSet.java:254-262`; `QuorumJournalManager.java:108, 194, 455-461`; `EditsDoubleBuffer.java:99-101`; `FSEditLog.java:306, 1878`; `core-default.xml:2466-2497`; `TestIPCLoggerChannel.java:65-131`; `TestNNWithQJM.java:66-72`; `NNThroughputBenchmark` (`-fs`, `-baseDirName`, `cleanUp()` deletes the base dir). All as cited. |

| # | Recommendation | Applied? | Why |
|---|---|---|---|
| R1 (A1) | Node paths, offline `mvn test` from `~/.m2`, `$H` = per-case copy of the dist | Applied 2026-11-24 (frozen sha256 above); fixed in run 1 (defect 1) | filed paths do not exist |
| R2 (A2) | Paced control; printed IFCHK lines, no assertions; unique channel addresses, `DelayAnswer` returning null, `stubOnly()` mock; overshoot with blocking | Applied 2026-11-24 | unambiguous control and evidence |
| R3 (A3) | B2g verdict wording; rows 8–10 | Applied 2026-11-24 | every outcome needs a row before any reading |
| R4 (A4) | JDK 8 `jmap`/`jcmd`, benchmark classpath, W from JN1 `BytesWritten`, Python sampler, order, `cleanUp()` note, stop conditions, refusal count window | Applied 2026-11-24 | exact procedure |
| R5 (A5) | B3g verdict wording; rows 9–11 | Applied 2026-11-24 | as R3 |
| R6 | B3f assumes batches near 512 KiB (B ≤ ~1 MiB). With async edit logging a sync carries only a few ops on this workload (observed ≤ 2 361 B), so B ≪ C; the intervals still hold but are much wider than needed | Left for stage 3 | does not change any row |

**Agreement criteria** — not needed (no run 2, see 5.2).

## 2. Environment

| Field | Run 1 |
|---|---|
| Date | 2026-11-24 (UTC; node local time 2026-11-23 MST): unit 23:21–23:31 (attempt 2), cluster 23:38–23:55 |
| Node | `pc72` (`node2`, CloudLab experiment `jason92-326665`), 40 cores, 125 GiB RAM — not in `environment.md`'s Node table (set up today by `setup-node.sh`; the parent session updates the table) |
| OS and kernel | Ubuntu 22.04.2 LTS, `5.15.0-203-generic` |
| JDK | OpenJDK `1.8.0_514` (`JAVA_HOME=/usr/lib/jvm/java-8-openjdk-amd64`); Maven 3.6.3 |
| Local source copy | `copy-source.sh` → `R/src` from `systems/hadoop/source/` (rel/release-3.4.2), repository HEAD `8f76f2390`; distribution copied from `/mydata/jingsong-s4/hadoop-base/hadoop-dist/target/hadoop-3.4.2` (built 2026-11-24, `Hadoop 3.4.2`) to `R/hadoop` |
| Case-file / harness commit | not committed (outside the repo); frozen by sha256 (§1); harness md5 in §1 and in `run1/unit/unit-run.log`, `run1/cluster/cluster-run.log` |
| Storage | `/mydata` (local LVM, 753 GB); all run data under `R/` |
| Full logs | `R/logs/unit/`, `R/logs/unit-attempt1/`, `R/cluster/logs/` (NN/JN logs gzipped, histograms, heap infos) on `pc72`; small copies in `~/writeup-hadoop/out/o19/run1/` |

## 3. Runbook defects

| # | Run | Step | Problem | Fix | Decision (date) | Case-file change |
|---|---|---|---|---|---|---|
| 1 | 1, unit attempt 1 | B2e step 3 (A1 command) | `mvn -o` failed before any test ran: `ClassNotFoundException: org.apache.maven.surefire.junit4.JUnit4Provider` (the base build skipped tests, so the provider was never fetched); 0 tests, no reading (`R/logs/unit-attempt1/unit-run.log`) | run `mvn` without `-o` (Maven Central reachable) | 2026-11-24, unit tier restarted; B2f/B2g unchanged | A1 fix note (dated) |

The cluster tier ran once without defects.

## 4. Run 1

**Scope:** unit tier (B2) in full; cluster tier (B3) in full (L = 1, 10, 64, 512, no-stop control). **Command logs:**
`run1/unit/unit-run.log`, `run1/cluster/cluster-run.log`.

### 4.1 Readings

**Unit tier** (`run1/unit/ifchk.csv`; surefire `Tests run: 9, Failures: 0, Errors: 0` for the probe and `1, 0, 0` for
`TestIPCLoggerChannel#testQueueLimiting`). Columns: N sent, A accepted, R refused, first refused batch, maxQueued (B), queue
after drain, accepted arrays cleared by GC / accepted, refused arrays cleared / refused. All refused causes were
`LoggerTooFarBehindException` (`refusedCauseOK=true` on every line).

| L | b | N | A (B2f) | R | first refused | maxQueued (B2f) | after drain | acc. cleared | ref. cleared | control: A / R / final |
|---|---|---|---|---|---|---|---|---|---|---|
| 0 | 4096 | 4 | 1 (1) | 3 | 2 | 4 096 (b) | 0 | 0/1 | 3/3 | 4 / 0 / 0 |
| 0 | 524 288 | 4 | 1 (1) | 3 | 2 | 524 288 (b) | 0 | 0/1 | 3/3 | 4 / 0 / 0 |
| 1 | 4096 | 516 | 256 (256) | 260 | 257 | 1 048 576 (1 048 576) | 0 | 0/256 | 260/260 | 516 / 0 / 0 |
| 1 | 524 288 | 8 | 2 (2) | 6 | 3 | 1 048 576 (1 048 576) | 0 | 0/2 | 6/6 | 8 / 0 / 0 |
| 4 | 4096 | 2052 | 1024 (1024) | 1028 | 1025 | 4 194 304 (4 194 304) | 0 | 0/1024 | 1028/1028 | 2052 / 0 / 0 |
| 4 | 524 288 | 20 | 8 (8) | 12 | 9 | 4 194 304 (4 194 304) | 0 | 0/8 | 12/12 | 20 / 0 / 0 |
| unset | 4096 | 5124 | 2560 (2560) | 2564 | 2561 | 10 485 760 (10 485 760) | 0 | 0/2560 | 2564/2564 | 5124 / 0 / 0 |
| unset | 524 288 | 44 | 20 (20) | 24 | 21 | 10 485 760 (10 485 760) | 0 | 0/20 | 24/24 | 44 / 0 / 0 |
| overshoot L = 1 | 3 MiB, 4 KiB | 2 | 1 (3 MiB accepted) | 1 (4 KiB) | 2 | 3 145 728 (3 145 728) | 0 | 0/1 | 1/1 | — |

Optional heap line (`IFCHK-HEAP`, used heap after GC): coarse, e.g. L = 4, b = 512 KiB: 3.45 → 7.86 → 4.19 MB (+4.4 MB while
queued); L = 1, b = 512 KiB showed +11.9 MB (noise of the same size as the signal). Not used for the verdict (B2d calls it coarse).

**Cluster tier** (`run1/cluster/readings.csv`; raw: `jmx-<label>.csv`, `histo-bytearray-rows.txt`, `cluster-run.log`)

| Run | C (B) | W = JN1 `BytesWritten` growth (file Δ) | plateau `QueuedEditsSize` max = value at (b) | samples at plateau | refusal WARNs | `[B` bytes a / b / c | (b) − (c) | drain after CONT |
|---|---|---|---|---|---|---|---|---|
| L = 1 | 1 048 576 | 148 502 742 (147 849 216) | 1 048 569 | 53 of 73; reached when W = 35.9 MB | 129 959 | 11 923 840 / 4 273 952 / 2 950 376 | 1 323 576 (1.26 MiB) | 2 s |
| L unset (10) | 10 485 760 | 149 510 558 (148 897 792) | 10 485 698 | 54 of 73; reached when W = 26.2 MB | 137 436 | 10 816 112 / 13 731 968 / 2 880 008 | 10 851 960 (10.35 MiB) | 13 s |
| L = 64 | 67 108 864 | 149 510 558 (148 897 792) | 67 108 812 | 35 of 99; reached when W = 78.4 MB | 71 020 | 10 797 520 / 71 334 536 / 2 893 808 | 68 440 728 (65.27 MiB) | 52 s |
| L = 512 | 536 870 912 | 150 518 374 (149 946 368) | 150 518 374 (= W) | grew to the end of the benchmark | 0 | 10 774 120 / 157 497 696 / 2 893 448 | 154 604 248 (147.4 MiB) | 131 s |
| control L = 64, no stop | 67 108 864 | 151 526 190 | max 1 356; 0 at (b) | transient | 0 | 10 896 056 / 3 045 752 / 3 002 952 | 42 800 | 0 s |

Benchmarks: rc 0, 1 000 000 mkdirs each, 110–125 s with the stop, 73 s without. NN up throughout (each run ended with a clean
`--daemon stop`; the next start recovered and opened a new segment). Every WARN names the run's own limit (`limit size:
1048576` ×129 959, `10485760` ×137 436, `67108864` ×71 020); largest refused batch 2 361 B.

### 4.2 Conclusion and logic

1. **Validity** — Unit: the `DelayAnswer` blocked (no future done before `proceed()`, `doneOkBeforeProceed=0`), the limit was
   crossed (R > 0 for every pair), the paced control had R = 0 [observed: `ifchk.csv`]. The probe reproduces the upstream test
   (L = 1, b = 4096: 256 / 1 048 576) [observed]. Cluster: the key reached the NN (plateau and WARN `limit size` differ per run
   as set) [observed: `jmx-*.csv`, NN log]; the window was held open (queue rose and stayed while JN3 was stopped) [observed];
   W ≈ 149.5 MB > C for every L ∈ {1, 10, 64} [observed: JN1 `BytesWritten`]; no quorum error, NN up [observed:
   `cluster-run.log`]. Valid.
2. **Readings** — (a) Batches were ~1–2 KB, not ~512 KiB: with async edit logging each sync carries a few ops, so the plateau
   sits within 7–64 bytes of C [observed: WARN `drop N bytes`, max 2 361]. (b) Snapshot (a) has ~8 MB more `byte[]` than (c) in
   every run (start-up buffers); (a) is not used by any row. (c) The `IsOutOfSync` column read `NA`: it is a JMX tag
   (`tag.IsOutOfSync`, `bean-L1-start.json`), not an attribute [observed]; no row depends on it.
3. **Matched row** — Unit: B2g row 1 (A3: Confirmed — caps): maxQueued = ⌊C/b⌋·b for L ∈ {1, 4, 10}, refusals start exactly at
   ⌊C/b⌋+1, all B2f values exact, refused arrays all collected and accepted arrays none, control R = 0, overshoot as row 5
   [observed: `ifchk.csv`]. Cluster: B3g row 1 (A5: Confirmed — caps): plateau ≈ C (1 048 569 / 10 485 698 / 67 108 812 ≤ C, each
   within one batch of C), heap (b) − (c) ≈ C (1.26 / 10.35 / 65.27 MiB, within the B3f ± 1 / ± 1 / ± 2 MiB), refusals logged,
   W ≫ C; plus row 2: L = 512 plateau = W and heap (b) − (c) ≈ W (147.4 MiB vs 143.5 MiB) [observed: `readings.csv`,
   `histo-bytearray-rows.txt`, NN log].
4. **Excluded rows** — Unit: row 2 (maxQueued > C without a big batch) — never; row 3 (same for every L) — 1, 4, 10 MiB differ;
   row 4 (refused not collectible / accepted collectible) — 0 of each; row 6 (control R > 0) — 0; row 7 (no block) — blocked;
   row 8 (numbers off) — exact; row 9 (no drain) — 0 after drain everywhere; row 10 (other cause) — all
   `LoggerTooFarBehindException`. Cluster: row 3 (heap ≈ W under a capped counter) — (b) − (c) ≈ C, not W; row 4 (plateau >
   C + B) — all ≤ C; row 5 (10 = 64) — 10.0 vs 64.0 MiB; row 6 (never rises) — rose; row 7 (quorum abort) — none; row 8 (control
   ≫ 0) — max 1 356 B; row 9 (heap does not resolve) — within tolerance; row 10 (W ≤ C) — W ≫ C; row 11 (L = 512 capped
   elsewhere) — plateau = W.
5. **Observed vs. inferred** — The conclusion rests on observed counts only. Inferred: that the (b) − (c) `byte[]` difference
   is the queued edit arrays — supported by its tracking the plateau (1.26 / 10.35 / 65.27 / 147.4 MiB vs 1 / 10 / 64 /
   143.5 MiB) and by the `[B` instance counts at (b) (64 663 at L = 64, 203 468 at L = 512, vs ~5 300 at (c)), and by the
   control's 42 800 B.
6. **Deviations and gaps** — Defect 1 (unit `-o`); `IsOutOfSync` not sampled (tag, 2b); heap (b) − (c) runs 0.26–1.27 MiB
   above the plateau (other per-op garbage-free buffers, e.g. IPC/protobuf copies; within tolerance); MemoryMXBean heap lines
   noisy (not decisive). The A4.5 order put L = 512 last among the stopped runs; namespace growth is common to (b) and (c).
7. **Core question** — Usage followed the constraint: the per-JN queued edit bytes, and the NN heap they pin, settled at the
   limit (1, 10, 64 MiB) while the healthy JNs received ~149.5 MB, and grew with the workload (≈ W) when the limit did not bind
   (512 MiB) (parts 1, 3). The disallow branch is what held it there: every further batch was refused with
   `LoggerTooFarBehindException` / the "will silently drop" WARN (parts 3, 4). The only overshoot is one batch into an empty
   queue (unit: 3 MiB at L = 1), as B1 states.

**Conclusion (one line):** unit B2g row 1 — confirmed; cluster B3g rows 1 and 2 — confirmed.

## 5. Self-check of run 1 — AI

### 5.1 Check of run 1's conclusion

Re-parsed from the raw files on `pc72` (not from `readings.csv`): each `jmx-<label>.csv` (max, samples at max, JN1 growth at the
first max sample), each `histo-<label>-<point>.txt` `[B` row, and the NN log (WARN count and the limits named in it).

| Part | Holds? | Note (file re-read) |
|---|---|---|
| 1. Validity | yes | `jmx-L1.csv`: queue 0 before the stop, 1 048 443 at the first sample after, then flat; JN1 grew 35.9 → 148.5 MB meanwhile. `ifchk.csv`: `doneOkBeforeProceed=0` on every blocked line. |
| 2. Readings | yes | `histo-*`: `[B` rows equal to `readings.csv` for all 15 snapshots. NN log: 338 415 WARNs = 129 959 + 137 436 + 71 020, each with its run's limit. |
| 3. Matched row | yes | All nine unit lines against the B2f table; cluster plateaus ≤ C and > C − 2 361 B; (b) − (c) within B3f tolerance; L = 512 plateau = W exactly. |
| 4. Excluded rows | yes | as 4.2.4; control max 1 356 B. |
| 5. Observed vs. inferred | yes | the one inference (heap diff = queued arrays) is consistent across five runs and the instance counts. |
| 6. Deviations and gaps | yes | none changes a decisive reading. |
| 7. Core question | yes | ceiling follows the knob in both tiers, the ungoverned contrast follows the workload, disallow branch observed. |

### 5.2 Run 2?

**No** — 2026-11-24. The conclusion rests on observed values that match exact predictions (unit) and tight intervals (cluster);
both tiers agree; no refutation or bypass beyond the one B1 states.

## 6. Run 2 — fresh AI session (optional)

Not done.

## 8. Verdict — AI

Jingsong may overrule any verdict at any time; record an override here with its date and reason.

**Stage-3 estimate:** positive. **Outcome class:** **true positive** (estimate `positive`, effect `caps` in both tiers; the
documented one-batch overshoot into an empty queue still counts as `caps`).

**Claim tested (B1):** for one JournalNode that stops acknowledging while the others keep up, the NameNode's
`queuedEditsSizeBytes` for that channel, and the heap it pins, rises to L·2^20 bytes and stops there (within one batch), with
later batches refused with `LoggerTooFarBehindException`; the only overshoot is a single batch larger than L into an empty
queue; with L above what the workload produces, the queue follows the workload. "Confirmed" means this claim held.

| Tier | Verdict (B2g / B3g row) | Effect on the constraint | Basis | Date |
|---|---|---|---|---|
| Unit | Confirmed — B2g row 1 (exact B2f values for L ∈ {0, 1, 4, 10} × b ∈ {4 KiB, 512 KiB}; refused arrays collectible; overshoot as row 5; control R = 0) | caps | run 1 + self-check | 2026-11-24 |
| Cluster | Confirmed — B3g rows 1 and 2 (plateau 1.0 / 10.0 / 64.0 MiB, heap (b) − (c) 1.26 / 10.35 / 65.27 MiB, W ≈ 149.5 MB, refusals logged; L = 512 plateau = W) | caps | run 1 + self-check | 2026-11-24 |

**Findings beyond the verdict.** (1) On this workload a QJM batch is ~1–2 KB (async edit logging syncs a few ops at a time),
not ~512 KiB as B3f assumed; the cap therefore lands within bytes of C. (2) The refused batches are dropped silently for that
JN ("will silently drop N bytes of edits!"), so a capped channel loses edits until the next segment; JN3 was resynchronised by
segment recovery at the next NN start. (3) `IsOutOfSync` is a metrics tag (`tag.IsOutOfSync`), not a JMX attribute.

**Feedback filed:** the case file's section D (D1 audit, D2 verdict) and the A1 defect note. Case-file sha256 after the
feedback: `bc5a09c858a49caa70a6dd8e748c031c989269120f55f26c7aad7ffc67cf9db8` (prediction/conclusion text hashes unchanged:
`f777e321…`, `91d42125…`).

## 9. What stays on the node

`pc72:R` (11 MB): `logs/` (unit, unit-attempt1, nohup outputs), `cluster/logs/` (cluster-run log, readings, JMX CSVs,
benchmark logs, heap histograms and heap infos, gzipped NN/JN logs), `harness/`. Removed after the run: the source copy, the
distribution copy, NN/JN data and configs, tmp. No NameNode, JournalNode, benchmark, sampler or test JVM of this run is left
(checked with `ps` and `jps` after the teardown; ports 9000/9870/8480–8489 free). Undo: `rm -rf R`.
