# commitlog_max_compression_buffers_in_pool-simplecachedbufferpool-usedbuffers--autonomous — stage-4 results  <!-- file: results/commitlog_max_compression_buffers_in_pool-simplecachedbufferpool-usedbuffers--autonomous.md -->

> **Case:** [`commitlog_max_compression_buffers_in_pool-simplecachedbufferpool-usedbuffers--autonomous`](../../stage3-ai-deep-read/cases/commitlog_max_compression_buffers_in_pool-simplecachedbufferpool-usedbuffers--autonomous.md)
>
> **Status:** verdict filed (2026-11-12)
>
> **Outcome class:** undetermined (estimate `positive`; unit **Not confirmed**, cluster **Not confirmed**; effect `undetermined`). Each tier's frozen reading rule matched a "claim wrong" row on direct memory. The self-check rejected that match: the excess over the prediction was not a segment buffer in either tier. Segment-buffer counts and plateaus followed N exactly. Details: §4.2, §8.
>
> **Agent:** autonomous (the suffix of the case-file stem). For an autonomous
> file, "§9a" below means each tier's predictions and conclusions table: B2f and B2g
> (unit), B3f and B3g (cluster); "§9b–§9e" means B2a–B2e or B3a–B3e; and the case
> file's feedback section is its section D, not §10. One results file per case file.

## 1. Before run 1 — design audit and freeze

| Field | Content |
|---|---|
| **Case-file version** | Repository HEAD `f74aade6` (the case file is untracked there; the coordinator commits it). Filing sha256 `fe3507fbfe579d6d0b12b78090e29506a2c8c4beb3296ac5f1fea2c897f58258` (`_INDEX.md` §4). sha256 of the whole file after the audit's amendments (2026-11-11): `a4c9657fea53281dfc094efbd2d4229c33e1f3b80e51698d159acfec5dd420e7`. sha256 of the frozen prediction and conclusions text (B2f, B2g, B3f, B3g: from `**B2f.` up to `**B2h.` and from `**B3f.` up to `**B3h.`, concatenated; copy in `commitlog_max_compression_buffers_in_pool-simplecachedbufferpool-usedbuffers--autonomous/run1/freeze-pred.txt`): `7e9588324b73a04252bc5d4ad37ae60aaf3a6702564586e5872339bafbe80988`. Frozen 2026-11-12T03:43Z UTC (2026-11-11 local), before any reading. None of the four blocks was edited by the audit. After runbook defect D1 (B3a yaml form, found by the cluster shakedown before any cluster reading; §3): `0465923f73cfe58af7c4a376fd0c1f16599a4208d74366d825d34e2b6413a4a6` — the version the cluster run used (the unit run used `a4c9657f…`; D1 does not touch B2). Final version, with section D filled (2026-11-12): `16a8eeae998b1db263deab34d2821e7ed417cd788e486b79cb095d5791c10d3f`. The prediction/conclusion hash re-computed on the final file is unchanged (`7e958832…`). |
| **Harness** | `harness/commitlog_max_compression_buffers_in_pool-simplecachedbufferpool-usedbuffers--autonomous/` (files in its README; not committed by this session) |
| **Tiers and values** | Unit (B2): Test 1 pool alone, N ∈ {1, 2, 3, 6, 12}, 1 MiB buffers; Test 2 manager path, N ∈ {2, 3, 6}, LZ4, 1 MiB segments, sync blocked by Byteman, 60 × 256 KiB mutations; control `CommitLogBufferCapCtlTest` (N=3, no compression, mmap). Cluster (B3): one node, Zstd-19, S = 64 MiB segments, N ∈ {3, 6, 12}; C1 LZ4 N=12; C2 mmap N=3; optional N=1 start. |
| **Audit bottom line** | **Ready after amendments** — 2026-11-11 (M1-M8 applied; runbook and instruments only) |

### 1.1 Design audit

| Group | Check | Rating (Met / Partly / Not met) | Note (section checked) |
|---|---|---|---|
| A. Core question | constrained quantity is memory or disk bytes | Met | A1/A2: a count of buffers, each `commitlog_segment_size` bytes (off-heap for LZ4/Zstd), so bytes = N × S. |
| A. Core question | knob varied, ≥ 3 values incl. default — or another approach, with the reason | Met | B2b N ∈ {2, 3, 6} (3 = default); B3b N ∈ {3, 6, 12}. |
| A. Core question | real resource measured, not only the counter (gap named) | Met | B2d/B3d: direct `BufferPoolMXBean.MemoryUsed` beside `usedBuffers`; B3d names that `usedBuffers` is not on JMX and the thread-local Zstd buffer and Netty/chunk-cache share as gaps. |
| A. Core question | usage driven to the limit and past it | Met after M5 | Unit: 15 MiB into 1 MiB segments with sync blocked (≥ 15 segments vs N ≤ 6). Cluster: Zstd-19 sync lag; the periodic-sync lag block (15 s) could stop writers first, so M5 lifts it. |
| B. Logic | each step says what it establishes | Met | B2c/B2h, B3b/B3h name the purpose of each test and control. |
| B. Logic | prediction stated in numbers or a clear relation | Met | B2f exact counts and ±0.1/0.2 MiB; B3f ceilings, plateau floors, slopes ± 64 MiB. |
| B. Logic | every plausible outcome has a conclusions row with its evidence | Partly → Met after M7, M8 | B2g/B3g cover above-limit, flat, never reached, control anomalies. The rows used "≈", "tracks", "near" without numbers; M7 (unit) and M8 (cluster) fix the windows and thresholds without changing the rows. No row covers a mixed outcome (some N bound, some not): pre-registered as "Not confirmed (no matching row)". |
| B. Logic | confirmation needs ceiling-follows-knob and direct disallow evidence | Partly → Met after M6 | Unit: `atLimit`/`usedBuffers` and active-segment plateau. Cluster: B3d's `jstack` of the allocator in `waitOnCondition` is not by itself the disallow state (the allocator also parks there when a reserve is ready, `AbstractCommitLogSegmentManager.java:108`, `:225`); M6 requires a writer in `awaitAvailableSegment` in the same dump. |
| B. Logic | alternative explanations and their controls | Met | Unit mmap control (uncapped path exceeds N); cluster C1 (fast sync: lag, not a fixed pattern), C2 (no pool), N sweep (same workload exceeds the lower caps' ceilings under a higher N: the positive control). |
| C. Specific | a human can follow it from the intro and §9a | Met | Estimate line, A3 and B1. |
| C. Specific | an AI can run §9b–§9e without re-deriving the code path | Partly → Met after M2 | The control class (B2h) and the print points were described, not specified (M2). |
| C. Specific | knob, values, workload, commands, observables, sampling, stop conditions exact | Partly → Met after M1-M4, M6 | Paths and ports for the shared node, heap/direct setting (cassandra-env.sh overrides jvm options), stress ports, JMX port. |
| D. Runnable | harness and environment prerequisites exist or are listed | Met | JDK 11, Ant, `build-test`; test classes generated by sed (B2c). |
| D. Runnable | workload arithmetic reaches the limit (data, time, disk, memory) | Partly → Met after M4, M5 | Memory: 4 GiB heap + ≤ 1 GiB direct + stress client fits ~14 GiB. Disk ≤ 8 GiB commit log + sstables on 1.6 TB. Write timeouts (2 s server, 12 s client) shorter than a wait on the cap (M4, M5). |
| D. Runnable | load-bearing citations spot-checked against the pinned source | Met | `SimpleCachedBufferPool.java:43, 58-66, 68-78, 85-96, 117-120`; `AbstractCommitLogSegmentManager.java:108, 150-161, 185-201, 225, 241-244, 296-348, 406-414, 640-657`; `CompressedSegment.java:60-68, 113-118`; `MemoryMappedSegment.java:130-133`; `FileDirectSegment.java:58-68`; `CommitLogSegment.java:303-368, 430-436`; `DatabaseDescriptor.java:2813-2825`; `Config.java:400`; `ZstdCompressor.java:208-210`; jctools-core 3.1.0 (`.build/parent-pom-template.xml:1074-1076`). All as cited. |

| # | Recommendation | Applied? | Why |
|---|---|---|---|
| M1 | Node `apt138`, paths under `/mydata/jingsong-cass-s4/o45/`, tree from `copy-source.sh`, `ant build-test` (B2a) | applied 2026-11-11 (case file untracked; no commit) | runnable on the assigned shared node |
| M2 | Print points (`pre-writer`, `plateau1`, `after-sleep`, `plateau2`, `final`) and the control class `CommitLogBufferCapCtlTest` specified (B2c) | applied 2026-11-11 | B2h described the control but not how to build it; a failed spin assertion must still leave a reading |
| M3 | BMUnit agent port 9391, stdout location, process check (B2e) | applied 2026-11-11 | shared node; known output location |
| M4 | Node tree separate from the build tree; heap/direct via `MAX_HEAP_SIZE`/`HEAP_NEWSIZE`/`MAX_DIRECT_MEMORY_SIZE`; ports 7300/7301/9342/7499; stress `-port` (B3a, B3c) | applied 2026-11-11 | cassandra-env.sh sets `-Xmx` and `MaxDirectMemorySize` itself; shared node |
| M5 | `periodic_commitlog_sync_lag_block: 600000ms`, `write_request_timeout`/`native_transport_timeout: 600000ms`, stress `-errors ignore` (B3a, B3c) | applied 2026-11-11 | a second, earlier back-pressure (15 s sync lag) and request timeouts could stop the workload before the cap is reached (D. workload arithmetic) |
| M6 | One JMX poller at 1 s instead of `nodetool sjk mx` calls; full `jstack` dumps; disallow state = allocator in `waitOnCondition` + writer in `awaitAvailableSegment` (B3d) | applied 2026-11-11 | cadence; direct disallow evidence |
| M7 | How B2g rows are read (thresholds from B2f) | applied 2026-11-11 | unambiguous matching |
| M8 | Cluster windows (B0 median of 30 s idle, P max in stress window), "writers blocked", numeric reading of each B3g row; mixed outcome = no matching row (B3e) | applied 2026-11-11 | unambiguous matching; fixed before any reading |
| R1 | B3f's 64 MiB noise allowance may be small: `networking_cache_size` and `file_cache_size` (64 MiB each) fill during stress, not at idle, so B0 can miss up to 128 MiB of non-segment direct memory | left for stage 3 (M6 adds the `BufferPool` `Size` gauges as context) | changing the ceiling would change B3f |
| R2 | B3d: the allocator parked in `waitOnCondition` is also its normal state | left for stage 3 (handled by M6 for this run) | wording of B3d |
| R3 | B2b says 2 is "the JCTools minimum"; that is a prediction (A1), checked by Test 1 | left for stage 3 | wording |

**Agreement criteria** — not applicable (run 2 not planned).

### 1.2 Pre-registered analysis (copied from amendments M7, M8; fixed before any reading)

- Unit: B2g row 1 = for each N ∈ {2, 3, 6}: `active` = `usedBuffers` = N at `plateau1`, `after-sleep`, `plateau2`; `directUsed(plateau1) − directUsed(pre-writer)` ∈ (N−2) MiB ± 0.2 MiB; `directUsed(plateau2) − directUsed(plateau1)` ∈ ± 0.2 MiB. Row 2 = any `active`/`usedBuffers` > N or direct delta > (N−2) MiB + 0.2 MiB. Row 3 = equal plateaus. Row 4 = `active` < N at `plateau1`. Control must show `active` > 3 at `ctl-5s`, else Not confirmed.
- Cluster: S = 64 MiB; B0 = median direct `MemoryUsed` over the 30 s idle window ending at stress start; P = max direct `MemoryUsed` inside the stress window. Writers blocked = Δ`WaitingOnSegmentAllocation.Count` ≥ 1 over the stress window and ≥ 1 `jstack` dump in the window with `COMMIT-LOG-ALLOCATOR` in `WaitQueue.waitOnCondition` and ≥ 1 thread in `awaitAvailableSegment`. Row 1 = for each N: (N−3)·S ≤ P−B0 ≤ (N−1)·S + 64 MiB, |P(6)−P(3)−192 MiB| ≤ 64 MiB, |P(12)−P(6)−384 MiB| ≤ 64 MiB, writers blocked in all three. Row 2 = P−B0 > (N−1)·S + 64 MiB for any N. Row 3 = max−min P ≤ 64 MiB with all blocked. Row 4 = none blocked and P−B0 < (N−3)·S for all. Row 5 = C1 P−B0 ≥ 576 MiB. Row 6 = C2 P−B0 ≥ 64 MiB. C1 in (3·S, 9·S) or C1 blocked = missed C1 prediction, cluster verdict at most Partial. Anything else: Not confirmed (no matching row).

## 2. Environment

| Field | Run 1 | Run 2 (fresh AI session, if done) |
|---|---|---|
| Date | unit 2026-11-12 03:46-03:48 UTC; cluster 03:54-04:29 UTC (shakedowns 03:50 and 03:51-03:54 UTC) | not done |
| Node (CloudLab name and type) | `apt138` (`node2.jason92-325433…apt.emulab.net`), 16 cores, 15.9 GiB RAM (15.0 GiB available at start), shared with another project (ports 7300/7301/9342/7499, BMUnit 9391) | |
| OS and kernel (`uname -r`) | Ubuntu 22.04.2 LTS, `5.15.0-198-generic` | |
| JDK (`java -version`) | openjdk 11.0.33 (2026-10-20) | |
| Ant (`ant -version`) | Apache Ant 1.10.12 | |
| Local source copy | `copy-source.sh` copy made at repository HEAD `f74aade6` (`/mydata/jingsong-cass-s4/o45-src` on the local machine), rsynced to `/mydata/jingsong-cass-s4/o45/src` on apt138 (`git describe`: `cassandra-5.0.9`); `ant build-test` 1 min 42 s, `BUILD SUCCESSFUL`; node tree `/mydata/jingsong-cass-s4/o45/node` is a copy of the built tree | |
| Case-file commit / harness commit | both untracked at HEAD `f74aade6` (the coordinator commits); case-file sha256s in §1 and §8; harness md5s in `run1/unit-summary.txt` and `run1/cluster-sessions.txt` | |
| Storage for node data | `/mydata` (LVM, 1.8 TB, 1.6 TB free), `/mydata/jingsong-cass-s4/o45/data`, removed before each configuration | |
| Full logs (path, outside the repo) | apt138 `/mydata/jingsong-cass-s4/o45/run1/{unit,N3,N6,N12,C1,C2,N1}/` (samples.csv, ctx.csv, jstack/, logs/system.log, gc.log, stress.out), `/mydata/jingsong-cass-s4/o45/logs/` (build, setup, driver output) | |

## 3. Runbook defects

| # | Run | Step (§9b–§9e) | Problem | Fix | Decision (date) | Case-file commit with the fix |
|---|---|---|---|---|---|---|
| D1 | cluster shakedown (before run 1) | B3a | The `commitlog_compression` block as written (`parameters:` followed by a mapping) does not load. `ParameterizedClass(Map)` casts `parameters` to a `List` (`ParameterizedClass.java:62-66`), so the node refused the yaml at start (`ClassCastException: ConcurrentHashMap cannot be cast to List`; `/mydata/jingsong-cass-s4/o45/shakedown-a-yamlfail/`) | `parameters:` / `- compression_level: "19"`; dated fix in B3a; predictions and conclusions unchanged; no cluster reading existed yet | 2026-11-11 | untracked file (no commit) |

**Deviations (not defects).**
- (a) **Session interruption.** The session that drove run 1 was stopped (API rate limit) while the cluster tier was running. The coordinator asked for the cluster tier to be restarted, on the premise that it had been interrupted midway. That premise did not hold. The node-side driver had been started detached (`setsid nohup`, `logs/cluster-run1.out`) and ran every configuration to completion without interruption: N3 03:54-04:01, N6 04:01-04:08, N12 04:08-04:16, C1 04:16-04:22, C2 04:22-04:29, N1 04:29 UTC. Each configuration ended with node up, stress rc=0, drain rc=0 and "CassandraDaemon processes of this tree left: 0" (`run1/cluster-sessions.txt`). No cluster reading had been opened before this check (2026-11-12 07:00 UTC). Run 1 is complete and is the only cluster run, so the tier was not run a second time: a second full run would only add a dataset to choose between. The coordinator may overrule this and order a rerun.
- (b) The unit run log's "CAP/POOL lines: 0" counts are a cosmetic harness bug (anchored grep). The analyzer and the self-check read the lines.
- (c) Two cluster shakedowns, 20 s of stress at N3 (instrument check, not used): `/mydata/jingsong-cass-s4/o45/shakedown{,-a-yamlfail}/`.

## 4. Run 1

**Scope:** unit tier B2 complete (Test 1 N ∈ {1, 2, 3, 6, 12}; Test 2 N ∈ {2, 3, 6}; control). Cluster tier B3 complete: N3, N6, N12 (Zstd-19), C1 (LZ4, N=12), C2 (mmap, N=3), N1 (start-up only). **Command log:** `commitlog_max_compression_buffers_in_pool-simplecachedbufferpool-usedbuffers--autonomous/run1/unit-summary.txt`, `run1/cluster-sessions.txt`. Readings: `run1/unit-readings.txt`, `run1/cluster-analysis.txt`, `run1/cluster-direct-5s.txt` (direct memory every 5 s), `run1/cluster-N12-jstack-excerpt.txt`, `run1/cluster-N1-excerpt.txt`. Self-check: `run1/selfcheck.txt`.

### 4.1 Readings

**Unit tier** (analyzer: 29 PASS, 6 FAIL, `run1/unit-summary.txt`)

| Test or assertion | Result | Evidence (file) |
|---|---|---|
| Test 1, N=1 | `IllegalArgumentException: capacity: 1 (expected: >= 2)` at construction | `run1/unit-readings.txt` |
| Test 1, N = 2, 3, 6, 12: `atLimit`, `usedBuffers`, direct | `atLimit` false for k < N and true for k ≥ N; `usedBuffers` = k up to 2N (the class does not refuse); direct delta = k MiB exactly | same |
| Test 1, retained after releasing 2N | 2 / 4 / 8 / 16 MiB for N = 2 / 3 / 6 / 12 (= roundUpPow2(N)); re-taking N leaves it unchanged | same |
| Test 2, N = 2, 3, 6: `pre-writer` | `usedBuffers` = 2 (first segment + reserve), active = 1 | same |
| Test 2: `active` / `usedBuffers` at `plateau1`, `after-sleep`, `plateau2`, `final` | exactly N / N at every point for N = 2, 3, 6; junit: 1 test, 0 failures per class | same, junit XML on the node |
| Test 2: direct(plateau1) − direct(pre-writer) | 524,388 B / 1,572,961 B / 4,718,689 B = (N−2) MiB + 524,388 B (+524,385 B) for N = 2 / 3 / 6. Predicted (N−2) MiB ± 0.2 MiB: missed by 0.50 MiB in every N | `run1/selfcheck.txt` |
| Test 2: direct(plateau2) − direct(plateau1) | +792,121 B for every N. Predicted flat ± 0.2 MiB: missed | same |
| Control (N=3, no compression, mmap) | active 20 at `ctl-5s` and `ctl-6s` (moved; > 3); pool `null`; direct delta +524,388 B, the same bytes as the compressed classes | same |
| Control vs compressed `pre-writer` | 266,885 B vs 2,364,037 B: difference exactly 2,097,152 B = the two 1 MiB start-up segment buffers | `run1/unit-readings.txt` |

**Cluster tier** (S = 64 MiB; analyzer: 10 PASS, 4 FAIL, `run1/cluster-analysis.txt`)

| Capacity value | Run | Observable (B3d) | Reading | Evidence (file) |
|---|---|---|---|---|
| N=3 | Zstd-19 | B0; P; P − B0 | 203.4; 341.2; 137.8 MiB (2.15 S); ≥ 95 % of the peak from +11 s | `run1/cluster-analysis.txt`, `run1/cluster-direct-5s.txt` |
| N=6 | Zstd-19 | B0; P; P − B0 | 203.4; 533.2; 329.8 MiB (5.15 S); from +13 s | same |
| N=12 | Zstd-19 | B0; P; P − B0 | 203.4; 981.8; 778.4 MiB (12.16 S). Plateau 917.2 MiB (P − B0 = 713.8 MiB = 11.15 S) from +20 s to +50 s; a step of +64.2 MiB at +51 s, then flat at 981.2-981.8 MiB until the end | same |
| N=3 / 6 / 12 | Zstd-19 | ΔWaitingOnSegmentAllocation; blocked-state jstack dumps (allocator in `waitOnCondition` + writers in `awaitAvailableSegment`) | 449 / 449 / 224; 24 / 24 / 12 of 26 dumps; up to 32-33 writers parked | `run1/cluster-analysis.txt`, `run1/selfcheck.txt` |
| slopes | | P(6) − P(3); P(12) − P(6) | 192.0 MiB (predicted 192 ± 64); 448.6 MiB (predicted 384 ± 64: missed). Measured on the N=12 pre-step plateau: 384.0 MiB (context only, not the frozen rule) | same; `run1/cluster-direct-5s.txt` |
| N=12 | Zstd-19 | threads compressing commit-log data (jstack, stress window) | `PERIODIC-COMMIT-LOG-SYNCER` in every dump. `MemtablePostFlush:1` too, in the +52 s and +62 s dumps, inside `CompressedSegment.write` ← `CommitLogSegment.sync` ← `CommitLogSegment.close` ← `CommitLogSegmentManagerStandard.discard` ← `archiveAndDiscard` ← `CommitLog.discardCompletedSegments`. Not seen for N=3 or N=6 | `run1/cluster-N12-jstack-excerpt.txt` |
| C1 (LZ4, N=12) | control | P − B0; blocked | 714.1 MiB (11.16 S); ΔWOSA 1056, 8 blocked-state dumps: the cap bound. Stress 3,317 op/s, against 513 / 605 / 757 op/s for Zstd N = 3 / 6 / 12 | `run1/cluster-analysis.txt`, `run1/cluster-sessions.txt` |
| C2 (mmap, N=3) | control | P − B0; mapped | 10.1 MiB (< 64 MiB); mapped 128 → 968 MiB; ΔWOSA 0 | `run1/cluster-analysis.txt` |
| N=1 | start-up | system.log | start-up fails: `IllegalArgumentException: capacity: 1 (expected: >= 2)` at `MpmcArrayQueue.<init>` ← `SimpleCachedBufferPool.<init>(:61)` ← `CompressedSegment$CompressedSegmentBuilder.createBufferPool` | `run1/cluster-N1-excerpt.txt` |
| all | health | `^ERROR` lines; stress errors | 0 for N3-C2 (N1: the one start-up error); stress `Total errors: 0`. The single "OutOfMemoryError" hit per log is the JVM option echo (`-XX:+HeapDumpOnOutOfMemoryError`) | `run1/selfcheck.txt` |

### 4.2 Conclusion and logic

1. **Validity.** Valid for both tiers.
   - Unit: the limit was reached in every compressed class (`active` = `usedBuffers` = N), the control moved (20 > 3), and Test 1 shows the instrument sees every 1 MiB buffer [observed: `run1/unit-readings.txt`].
   - Cluster: writers were blocked on the cap in every Zstd run (ΔWOSA ≥ 224; 12-24 blocked-state dumps), and each configuration ran its full 240 s with 0 errors. The config echo shows the intended N and compressor [observed: `run1/selfcheck.txt`, `run1/cluster-sessions.txt`].
2. **Readings.**
   - (a) Unit: a constant +524,388 B appears on the writer path in every class, the no-pool control included. A further +792,121 B appears after `archiveAndDiscard` in the compressed classes only [observed].
   - (b) Cluster N=12: a +64.2 MiB step at +51 s, coinciding with `MemtablePostFlush:1` compressing a segment through `discard → close() → sync()` [observed: `run1/cluster-direct-5s.txt`, `run1/cluster-N12-jstack-excerpt.txt`].
   - (c) C1 bound at N=12 although LZ4 compresses fast: stress ran 4-6 × faster than under Zstd-19 [observed].
3. **Matched row.** Applying the frozen reading rules mechanically gives:
   - Unit, M7: **B2g row 2** ("direct grows past N MiB with sync blocked … claim wrong: the check is bypassed or racy"). Direct − pre-writer = (N−2) MiB + 0.50 MiB > (N−2) MiB + 0.2 MiB [observed].
   - Cluster, M8: **B3g row 2** ("P(N) − B0 > (N−1)·S + 64 MiB … claim wrong: buffers escape the cap"). N=12: 778.4 > 768 MiB, by 10.4 MiB [observed]. **B3g row 5** also holds (C1 = 11.16 S ≥ 9 S: "re-examine") [observed].

   The self-check (§5) finds that these matches do not follow the audited logic, so both tiers are downgraded to **Not confirmed**.
4. **Excluded rows.**
   - Unit row 1 fails on direct memory (±0.2 MiB missed; its count parts hold). Row 3: the plateaus are 2 / 3 / 6, not identical. Row 4: no plateau below N.
   - Cluster row 1 fails (N=12 ceiling missed by 10.4 MiB; slope 2 at 448.6 vs 384 ± 64). Row 3: P spans 341-982 MiB. Row 4: writers were blocked in every run. Row 6: C2 = 10.1 MiB < 64 MiB.
5. **Observed vs. inferred.**
   - (i) The unit +524,388 B is the writer thread's `DataOutputBuffer.scratchBuffer`, used to serialize each 256 KiB mutation (`CommitLog.java:306`; a direct allocation if `ALLOCATION_TYPE` is `DIRECT`, `DataOutputBuffer.java:84-88`). [inferred: identical bytes with and without a pool; not a 1 MiB multiple; the writer path is the only activity between the two prints.]
   - (ii) The unit +792,121 B after discard is the test thread's thread-local LZ4 output buffer, allocated when `close()` syncs the discarded segment (`CommitLogSegment.close` → `sync` → `CompressedSegment.write:68`). [inferred: compressed classes only; size ≈ LZ4 bound of a 3 × 256 KiB section; the same for every N.]
   - (iii) The N=12 +64.2 MiB step is `MemtablePostFlush:1`'s own thread-local Zstd output buffer (`compressBound(section)` ≤ about 1 S). It is allocated when a clean but still unsynced segment is discarded and synced on that thread. It is outside `usedBuffers` (A3 8d), and the case counted only one such buffer. [observed: the thread in `CompressedSegment.write` via `discard`; inferred: that the step is that thread's buffer, from timing (+51 s step, +52 s dump) and size (64.2 MiB ≈ 1 S).]
   - (iv) The N=12 pre-step plateau (713.8 MiB = 10 S + 1 S + 0.15 S), N=3 (1 S + 1 S + 0.15 S) and N=6 (4 S + 1 S + 0.15 S) read as (N−2) segment buffers + one thread-local buffer + 0.15 S of other direct memory. [inferred: `usedBuffers` is not on JMX.]
   - (v) C1 binds because a segment's buffer is released only after the periodic sync (every 10 s) has written the whole segment. At the C1 write rate the 10 s window and the sync backlog fill the 12 buffers. [inferred: sync cadence `AbstractCommitLogService.java:176-200`; the design assumed release follows compression speed.]
6. **Deviations and gaps.**
   - Amendments M1-M8 and defect D1 (§1, §3); the session interruption (§3 a).
   - Not observed: `usedBuffers` in the cluster (the B3d gap), the size of each thread-local buffer, and the scratch buffer's allocation type.
   - Readings (i)-(iv) carry the self-check's rejection of row 2. They are supported, but inferred.
   - The B3f noise allowance (64 MiB) is smaller than a second thread-local buffer (R1 already flagged the noise allowance as small).
7. **Core question.** Did usage follow the constraint?
   - **Segment buffers: yes.** In the unit tier `active` = `usedBuffers` = N exactly, with the allocator stopped (parts 1, 3). In the cluster the plateau moved by exactly 192.0 MiB from N=3 to N=6 (= 3 S), and by 384.0 MiB from N=6 to the N=12 pre-step plateau, with writers parked on the cap in every run (parts 1, 2). That is the "ceiling follows the knob" step plus direct disallow evidence.
   - **Commit-log direct memory: not by N alone.** The real resource also holds one thread-local compression buffer per thread that compresses. At N=12 a memtable-flush thread added a second one of about 1 S (part 2 b), and N does not govern these buffers.
   - Each tier's frozen reading rule matched the "claim wrong" row on direct memory. Its meaning (segment buffers escape the cap) is contradicted by the counts and the mechanism, so neither tier reaches Confirmed or Refuted.

**Conclusion (one line):** unit — Not confirmed (mechanical B2g row 2, rejected by the self-check); cluster — Not confirmed (mechanical B3g rows 2 and 5, rejected by the self-check).

## 5. Self-check of run 1 — AI

`harness/.../selfcheck.py` re-parsed the raw files with its own code (`run1/selfcheck.txt`). Every cited number reproduced: unit bytes, cluster B0/P/P − B0, ΔWOSA and blocked-state dumps. The N=12 step and the `MemtablePostFlush` stack were re-read in `samples.csv` and `jstack/1794456623009.txt` on the node.

| Part | Holds? (yes / no) | Note (file re-read) |
|---|---|---|
| 1. Validity | yes | `run1/unit-readings.txt`: counts = N, control 20; `run1/cluster-sessions.txt`: every configuration complete, 0 stress errors; `run1/selfcheck.txt`: config echo N and compressor as intended. |
| 2. Readings | yes | (a) bytes re-derived (`selfcheck.txt`: 524,388 / 524,385 B and 1,316,506-1,316,509 B after discard in every class); (b) `cluster-direct-5s.txt` +50 s 917.2 → +55 s 981.4 MiB; `cluster-N12-jstack-excerpt.txt` shows the `discard → close → sync → CompressedSegment.write` stack. |
| 3. Matched row | **no** | The mechanical matches (unit B2g row 2, cluster B3g row 2) need "segment buffers escape the cap / check bypassed or racy". The raw files contradict that meaning. Unit: `usedBuffers` = `active` = N at every print, and the identical 524,388 B appears in the no-pool control. Cluster: the excess appears as a single 64.2 MiB step when a second thread compresses, not as growth with load, and the pre-step N=12 plateau (713.8 MiB) is inside the ceiling. Row 1 is also excluded (the direct-memory tolerances and the N=12 slope were missed). No frozen row fits, so both tiers are **downgraded to Not confirmed** (README: "a part that does not hold … downgrades the conclusion to Not confirmed"). Row 5 (C1 "re-examine") points the same way. |
| 4. Excluded rows | yes | Each exclusion cites a number `selfcheck.txt` reproduces. |
| 5. Observed vs. inferred | yes, as recorded | (i)-(v) are labelled inferred. The verdict no longer depends on them being right; they explain why row 2 was not accepted. |
| 6. Deviations and gaps | yes | Session interruption (§3 a) checked against the node-side timestamps; D1 found before any reading. |
| 7. Core question | yes | It answers the core question at the level the evidence supports: the segment-buffer count follows N; total commit-log direct memory has an extra per-thread term. |

### 5.2 Run 2?

**No** (2026-11-12). A rerun of the same frozen design would hit the same N-independent offsets: the unit offsets are deterministic (identical bytes in every class), and the second thread-local buffer depends on flush timing. A design that subtracts the per-thread buffers, or reads `usedBuffers` through a Byteman rule on the node, would settle the cluster tier, but that is a stage-3 redesign (§8).

## 6. Run 2 — fresh AI session (optional)

Not done (§5.2).

## 7. Comparison — only if run 2 was done

Not applicable.

## 8. Verdict — AI

Jingsong may overrule any verdict at any time; record an override here with its date and reason.

**Stage-3 estimate:** positive. **Outcome class:** undetermined. Both tiers are Not confirmed: the frozen direct-memory predictions missed by N-independent amounts (a writer scratch buffer, thread-local compression buffers). The count and plateau parts held.

**Claim tested:** (B1) With a compressed commit log (LZ4/Zstd, off-heap buffers), the number of live commit-log segment buffers never exceeds N = `commitlog_max_compression_buffers_in_pool`. When the sync thread lags, usage plateaus at N × `commitlog_segment_size` and writers block instead of allocating more, so segment-buffer direct memory follows N: about S per unit of N, never above N × S. "Confirmed" below means this claim held.

| Tier | Verdict (B2g / B3g row) | Effect on the constraint | Basis | Date |
|---|---|---|---|---|
| Unit | **Not confirmed**: mechanical B2g row 2 (direct (N−2) MiB + 0.50 MiB, beyond ±0.2), rejected by the self-check. `active` = `usedBuffers` = N exactly for N = 2, 3, 6; the no-pool control shows the same +524,388 B | undetermined (counts follow N exactly) | run 1 + self-check | 2026-11-12 |
| Cluster | **Not confirmed**: mechanical B3g row 2 (N=12 P − B0 = 778.4 > 768 MiB) and row 5 (C1 = 11.16 S), rejected by the self-check. The excess is a 64.2 MiB step when `MemtablePostFlush` compresses a segment through `discard → close → sync`. Plateaus 2.15 / 5.15 / 11.15 S (pre-step) for N = 3 / 6 / 12; writers parked on the cap in every Zstd run | undetermined (segment buffers follow N; per-thread compression buffers are outside N) | run 1 + self-check | 2026-11-12 |

**Positive control:**
- Unit: the mmap control (same workload, no pool) reached 20 active segments against 3 under the cap, and Test 1 shows the direct-memory instrument resolves each 1 MiB buffer.
- Cluster: the same workload exceeded the N=3 and N=6 ceilings when N was larger (N=12 plateau 713.8 MiB). C2 (no pool) shows no direct growth (10.1 MiB) while mapped memory grew 128 → 968 MiB.

**Other predictions:**
- A1 (N=1 fails) held in both tiers: `IllegalArgumentException: capacity: 1 (expected: >= 2)` from JCTools; a node with N=1 does not start.
- A3 (8b) held: a released pool retains roundUpPow2(N) buffers (2/4/8/16), more than N for N = 3, 6, 12.
- A3 (8a) held: the class alone allows 2N.
- A3 (8c) held: no pool in mmap.

**Feedback filed:** case-file section D updated (final case-file sha256 `16a8eeae998b1db263deab34d2821e7ed417cd788e486b79cb095d5791c10d3f`), with amendments M1-M8 and D1 next to the text they change. No section of the trace was refuted. **Recommendations for stage 3:**
- (1) B1 and B3f should count one thread-local compression buffer per compressing thread. The sync thread always has one; a memtable-flush thread that discards a clean, unsynced segment syncs it itself (`CommitLogSegment.close` → `sync`) and allocates a second.
- (2) B2f should allow the writer's `DataOutputBuffer` scratch buffer (about 2 × mutation size) and the closing thread's compression buffer after `archiveAndDiscard`.
- (3) C1 is not a "fast sync" control: buffers are released only by the periodic sync, so a fast compressor still binds at N=12 when writes are fast.
- (4) A cluster design that reads `usedBuffers` directly (Byteman on `SimpleCachedBufferPool.createBuffer` / `releaseBuffer`) would settle the tier.

**Open points for the user:**
- (a) The coordinator asked for the cluster tier to be restarted. It was not restarted, because run 1 had completed on the node (§3 a).
- (b) Both tiers are downgraded from a mechanical "claim wrong" row on inferred evidence (§4.2 part 5). An override to "Confirmed for segment buffers, with per-thread compression buffers outside N" would rest on those inferences.

**Upstream / doc candidates:** doc note: commit-log direct memory is bounded by N × segment size **plus** one compression or encryption output buffer per thread that syncs a segment (the sync thread, and memtable-flush threads through `discardCompletedSegments` → `close`), so `commitlog_max_compression_buffers_in_pool` alone does not bound it. Not a bug.

**Leftovers on apt138:** nothing running (checked 2026-11-12 07:01 UTC: no process with `/mydata/jingsong-cass-s4/o45` in its arguments, no `CassandraDaemon` of this tree, no stress or poller). Kept on the node under `/mydata/jingsong-cass-s4/o45/` (about 1.0 GB): `src` (build tree), `node` (node tree), `harness`, `harness-classes`, `run1/` (61 MB of raw readings), `shakedown/`, `shakedown-a-yamlfail/`, `logs/`, `data/` (the N1 start attempt). Local machine: `/mydata/jingsong-cass-s4/o45-src`.
