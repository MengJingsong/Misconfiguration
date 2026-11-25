# flushhighwatermark-outboundconnectionsettings-flushingbytes--autonomous — stage-4 results  <!-- file: results/flushhighwatermark-outboundconnectionsettings-flushingbytes--autonomous.md; written outside the repo at ~/writeup-ext/out/o125/results.md -->

> **Case:** `flushhighwatermark-outboundconnectionsettings-flushingbytes--autonomous` (stage-3 order 125, extension set, band B; filed case file `experiments/capacity-enforcement-exp/cassandra/stage3-ai-deep-read/cases/flushhighwatermark-outboundconnectionsettings-flushingbytes--autonomous.md`; the amended copy is `~/writeup-ext/out/o125/case-amended.md`, outside the repo)
>
> **Status:** verdict filed (2026-11-25). Run 1 is done at both tiers and self-checked; there is no run 2. §1 was written before any reading. **This attempt ran on `ms0640`** (Utah m400, aarch64).
>
> **Outcome class:** **weak true positive** (estimate `positive`). The unit tier is **Confirmed — caps**. The cluster tier is **Not confirmed — undetermined**, so the class comes from the unit tier alone (rule of 2026-10-29). See the [definition](../../../stage4-runtime-verification/README.md#outcome-class).
>
> **Agent:** autonomous. "§9a" below means B2f/B2g (unit) and B3f/B3g (cluster); "§9b–§9e" means B2a–B2e or B3a–B3e; the feedback section is section D. Run as Jingsong by a fresh stage-4 agent. **This attempt runs on `ms0640`** (Utah m400, aarch64). The first attempt (2026-11-25, `pc99`, x86_64) did the audit and wrote the harness but ran nothing: the `pc99` node lock was held by a stale session (its stub is kept as `results-blocked-pc99-stub.md`). No reading of this case existed before this attempt.

## 1. Before run 1 — design audit and freeze

| Field | Content |
|---|---|
| **Case-file version** | Filed at repo commit `bef6bc8a6`; repo HEAD at this audit `8bd1dfb31`. sha256 as filed: `8dbfc6faf872e72e904f81766e3e2e925a9deb6699ac6814ad22ff84cc4b105e` (matches `_INDEX.md` §4). The first attempt's audit added S4-A1 to S4-A3 (sha256 then `20dc9d15…`, kept as `harness/case-amended-s1-pc99.md`). This review added **S4-A4** (2026-11-25, before any reading). **Frozen sha256: `13af3e1c013cd4c9079684271045e275a8fa097a8276b73f0622534d5072b5cd`** (`harness/freeze-ms0640.sha256`). **Frozen tables** (sha256 of each block's text, `harness/freeze-tables.sha256`): B2f `ea7d8ea0…`, B2g `3c4d6153…`, B3f `2a8aea26…`, B3g `83d87c15…`. All four are byte-identical to the filed file. |
| **Harness** | `~/writeup-ext/out/o125/harness/`, not committed (md5): `FlushWaterMarkTest.java` `384e3f89…` (verbatim from B2e), `Sampler.java` `406d9f01…` (verbatim from B3d), `patch-line103.txt` `c710f0ea…` (verbatim from B3a). As frozen before any reading: `unit.sh` `ce027382…`, `cluster-setup.sh` `b57c956a…`, `cluster-run.sh` `b29db552…`, `cluster-all.sh` `8f4cca07…`, `analyze.py` `cc332e36…`. **As run, after the defect fixes of §3:** `unit.sh` `a15a7082…`, `extract-rows.py` `13cc1a83…` (new, fix 1), `cluster-setup.sh` `f57f0c91…` (fix 2), `cluster-run.sh` `0eef3fea…` (fixes 3–5), `cluster-all.sh` `96a4a15f…`, `analyze.py` `c13fe399…` (reads the rejoined rows), and `supplement.py` `06063e86…` (absolute levels, not a verdict reading). The sha256 of the case file with S4-D1 to S4-D5 is `036e4447d8fbd2872e3bcd263ead581875bba87d8fcd61a3b89c9f69c7acd516`. The tables B2f, B2g, B3f and B3g are unchanged by every amendment and fix. They were reviewed against the frozen file. Changes from the first attempt: cleanup restricted to the run user (S4-A4e); a disk guard (S4-A4b); `$WORK/src` removed before the cluster copy; `cluster-all.sh` stops at the first failed run (README "Run 1": stop at the first step that cannot run as written) and records its PID in `/mydata/s4/DRIVER-jingsong-c125.pid`. Instrument checks run in the scripts: the `setMarks` assertion (unit), the patched-class string check and the `javac` of `Sampler` (cluster setup), and `props.txt` per run. |
| **Tiers and values** | **Unit (B2):** H ∈ {16 384; 65 536 (stock); 262 144; 1 048 576; 8 388 608 (uncapped control)}, L = H/2, N = 3072 × ~1 040 B, three repeats. **Cluster (B3):** node A's H ∈ {65 536 (stock); 1 MiB; 256 MiB (uncapped control)} via the `-D` patch. B is stock. Each value is run twice with B frozen for 20 s, plus one stock no-stall run (7 runs). |
| **Audit bottom line** | **Ready after amendments** (2026-11-25: S4-A1 to S4-A3 by the first attempt, reviewed and kept; S4-A4 by this one) |

### 1.1 Design audit

The first attempt's audit (notes in `results-s1-draft.txt`) was re-checked here against the pinned source and against the new node. Its ratings stand except where a note says otherwise.

| Group | Check | Rating | Note (section checked) |
|---|---|---|---|
| A. Core question | constrained quantity is memory or disk bytes | Met | A2/B1: off-heap direct `ByteBuffer`s from the networking `BufferPool`, held for in-flight frames. The operand is `flushingBytes` (canonical bytes). |
| A. Core question | knob varied, ≥ 3 values incl. default — or another approach, with the reason | Met | A1: hard-coded constant. It is varied by reflection in the unit tier (5 values incl. stock 65 536) and by a `-D` patch in the cluster tier (3 values incl. stock). B3a gives the reason. |
| A. Core question | real resource measured, not only the counter (gap named) | Met | Unit: the operand plus the delta of `BufferPools.forNetworking().usedSizeInBytes()`. Re-checked: `memoryInUse` adds each buffer's capacity (`BufferPool.java:282-285, 824, 891, 950`), so the delta is per buffer, not per chunk. Cluster: `netPoolUsed`, `directUsed` and NMT. B3d names the gap: `flushingBytes` cannot be read in the node, and the pool is shared. |
| A. Core question | usage driven to the limit and past it | Met | Unit: W ≈ 3.19 MB against H ≤ 1 MiB. Cluster: a backlog of tens of MiB against 64 KiB / 1 MiB. The cluster backlog depends on the write rate the m400 sustains. S4-A4(d) fixes the remedy before any reading if the backlog stays < 20 MiB. |
| B. Logic | each step says what it establishes | Met | B2h/B3h. |
| B. Logic | prediction stated in numbers or a clear relation | Met | B2f: bands [H, H+65 515) and ceil(H/B)·B. B3f: Δ bands per H. |
| B. Logic | every plausible outcome has a conclusions row with its evidence | Partly → Met | The rows exist, but the filed file gives no verdict labels or precedence. S4-A2/S4-A3 added them, and S4-A4(c) adds a unit catch-all (Not confirmed). |
| B. Logic | confirmation needs ceiling-follows-knob and direct disallow evidence | Partly | Unit: direct (`isWritable = 0`, the branch at `OutboundConnection.java:855-856`). Cluster: no direct disallow evidence; it is inferred from the pool delta against `pendingBytes`. Left for stage 3 (R-a). |
| B. Logic | alternative explanations and their controls | Met | The 8 MiB and 256 MiB uncapped controls, the `setMarks` assertion, `props.txt`, the drain after resume, and the no-stall run. |
| C. Specific | a human can follow it from the intro and §9a | Met | B1 and A3. |
| C. Specific | an AI can run §9b–§9e without re-deriving the code path | Partly → Met | S4-A1 covers paths, `cdc_raw_directory`, duplicate yaml keys, `ulimit`, `statusbinary` and the no-stall timestamps. S4-A4 covers the node, the disk and cleanup. |
| C. Specific | knob, values, workload, commands, observables, sampling, stop conditions exact | Met | B2b–B2e and B3b–B3e. |
| D. Runnable | harness and environment prerequisites exist or are listed | Met | `ms0640`: aarch64, JDK 11.0.33, Ant 1.10.12. The full built `/mydata/s4/cassandra-base` (469 MB) has `src/`, `test/` and `build/test/`, and its 8 load-bearing files md5-match the repo source (`harness/md5-base-ms0640.txt` = `harness/md5-repo.txt`). Netty native epoll for `linux-aarch_64` is in `lib/`. `test.timeout` is 480 s. |
| D. Runnable | workload arithmetic reaches the limit (data, time, disk, memory) | Partly → Met | RAM: two nodes at 2 GiB heap + 1 GiB direct against 62 GiB. Disk: ≈17 GB free (not 695 GB as on `pc99`). The data dirs are cleared each run, `$WORK/src` is removed before the cluster copy, and a run aborts below 3 GiB free (S4-A4b). Time: 7 runs × ~4 min. |
| D. Runnable | load-bearing citations spot-checked against the pinned source | Met | Re-checked in `systems/cassandra/source/` (`git status` clean): `OutboundConnectionSettings.java:87, 103, 145`; `OutboundConnection.java:741-742, 759-760, 766, 782, 840-875, 908-909`; `OutboundConnections.java:62-70`; `BufferPool.java:128, 282-285, 824, 950`; `BufferPoolMetrics.java:62`; `InternodeOutboundMetrics.java:120, 136`; `Config.java:177, 241-246, 271-272, 417, 493-494` (the yaml keys of B3a exist). |

| # | Recommendation | Applied? | Why |
|---|---|---|---|
| 1 | S4-A1: runnability (WORK, base copy, `cdc_raw_directory`, no duplicate yaml keys, `ulimit`, `statusbinary`, no-stall timestamps) | applied by the first attempt (2026-11-25), kept | needed for a valid run |
| 2 | S4-A2 / S4-A3: verdict labels for B2g / B3g | applied by the first attempt (2026-11-25), kept | B2g/B3g give meanings but no labels |
| 3 | S4-A4: node `ms0640`, disk plan and guard, unit catch-all, the backlog remedy fixed in advance, user-restricted cleanup | applied 2026-11-25 (this session, before any reading) | new node with less disk; an unlabelled outcome would be ambiguous |
| R-a | Cluster tier: add a direct disallow observable (e.g. a Byteman rule counting `isWritable = false` at `OutboundConnection.java:855`, or exposing `flushingBytes`) | left for stage 3 | adds an instrument; not needed for a valid run |
| R-b | Make the mark settable (fix `withNettyBufferBounds`, which ignores its argument, `OutboundConnectionSettings.java:251-258`) | left for stage 3 / upstream | a finding, not a run change |

**Agreement criteria:** not needed (no run 2 planned).

## 2. Environment

| Field | Run 1 |
|---|---|
| Date | 2026-11-25, 10:19–11:36 MST (node lock held for that time) |
| Node (CloudLab name and type) | **`ms0640`** = `node1.jason92-326377.misconfiguration-pg0.utah.cloudlab.us`, Utah m400, **aarch64**, 8 cores, 62 GiB |
| OS and kernel (`uname -r`) | Ubuntu 22.04.1 LTS, `5.15.0-191-generic` |
| JDK (`java -version`) | OpenJDK 11.0.33 (`11.0.33+9-post-1ubuntu1-22.04.1`) |
| Ant (`ant -version`) | 1.10.12 |
| Local source copy | `cp -a /mydata/s4/cassandra-base` (a full `build-test` copy of `cassandra-5.0.9`; 8 load-bearing files md5-match `systems/cassandra/source/` at repo HEAD `8bd1dfb31`). Unit: `$WORK/src`, stock. Cluster: `$WORK/cass`, line 104 patched (B3a, S4-D2), `ant -Dno-checkstyle=true jar` in 36 s. Netty native epoll (`linux-aarch_64`) in use. |
| Case-file commit / harness commit | case file `bef6bc8a6` + amendments outside the repo (sha256 in §1); harness not committed (`~/writeup-ext/out/o125/harness/`) |
| Storage for node data | `/mydata/jingsong-cass-s4/o125` (local LVM volume, ≈17 GB free at start; lowest seen 15 GB) |
| Full logs (path, outside the repo) | on `ms0640`: `/mydata/jingsong-cass-s4/o125/{logs,runs,runs-superseded-defect4,runs-superseded-defect5,runs-defect3-s1-stock,logs-unit-superseded-prefix1}` (9.0 MB in all). Excerpts cited below: `~/writeup-ext/out/o125/run1/` |

## 3. Runbook defects

| # | Run | Step | Problem | Fix | Decision (date) | Case-file version with the fix |
|---|---|---|---|---|---|---|
| 1 | unit | B2e step 3 | `grep '^FHWM'` finds no data rows. The test's `printf` reaches the `ant` log through `SubstituteLogger` one write at a time, so each row is split over ~22 log lines (`run1/defects/defect1-split-rows.log`). | Rejoin the tokens after each "FHWM," (`harness/extract-rows.py`). The test is unchanged. The unit tier restarted (three new repeats). The first three repeats are kept apart (`logs-unit-superseded-prefix1/` on the node), and their rows were not read. | 2026-11-25 | S4-D1 |
| 2 | cluster | B3a | "Replace line 103": at `cassandra-5.0.9` the literal call is on **line 104**, and line 103 is `{` (`run1/defects/defect2-patch-line.log`). A1's `:103` is off by one in the same way. | Patch the single line holding the stock call (line 104), with B3a's text unchanged. Nothing had run. | 2026-11-25 | S4-D2 |
| 3 | cluster | B3e step 2 | B was started first, but the only seed is A. B exited during start-up: "Didn't receive schemas for all known versions within the PT30S". It also logged a 41 s local pause (`run1/defects/defect3-*`). | Start A, wait for `UN` + binary running, then start B and wait for both. A node that dies while waiting stops the run. No workload had started. The tier restarted. | 2026-11-25 | S4-D3 |
| 4 | cluster | B3e step 9 (harness) | The second run stopped at the port check: `127.0.0.1:7199` was still listening just after the previous node had left `ps` (`run1/defects/defect4-s1-1m-ports.log`). | Wait up to 90 s for the ports, at the end of a run and before the next one. The tier restarted. The one complete run before the fix is superseded and not used. | 2026-11-25 | S4-D4 |
| 5 | cluster | B3e step 5 | On the loaded m400, the sampler launched at t = 20 s as `java Sampler.java` gave its first sample only at the STOP (+0.0 s and +0.6 s; `run1/defects/defect5-sampler-late.txt`). Step 10's 10 s baseline was therefore empty, and `analyze.py` silently used a baseline of 0. | The unchanged `Sampler.java` is compiled with `javac` and started at t = 5 s with 210 samples (it covers t = 5–110 s as before). A run stops if its first sample is later than STOP − 10 s. In every final run the first sample came 33 s before the STOP. The tier restarted. The superseded runs are not used. | 2026-11-25 | S4-D5 |

No fix changes B1, B2f, B2g, B3f or B3g. The readings in §4 come only from the final unit tier (after fix 1) and the final cluster tier (after fix 5).

## 4. Run 1

**Scope:** unit tier with all 5 values × 3 repeats; cluster tier with all 3 values × 2 repetitions plus 1 stock no-stall run. **Command logs:** `run1/unit/unit-driver.log`, `run1/cluster/<run>/driver-excerpt.log` (full: `logs/` and `runs/` on the node).

### 4.1 Readings

**Unit tier** (`run1/unit/unit-r{1,2,3}.rows`, checked by `run1/unit/analyze-unit.txt`; s = 1 039 B (1 038 in the first H of each JVM), N = 3 072, W = 3 191 808 B (3 188 736 at H = 16 384))

| H (L = H/2) | `flushingBytes` r1 / r2 / r3 | band [H, H+65 515) | `isWritable` | `pendingBytes` | `poolDelta` r1 / r2 / r3 | received / `flushingAfterResume` |
|---|---|---|---|---|---|---|
| 16 384 | 50 862 / 50 862 / 63 318 | in, ×3 | 0, 0, 0 | 3 189 607 / 3 189 607 / 3 188 569 | 55 296 / 55 296 / 67 584 | 3 072 / 0, ×3 |
| 65 536 (stock) | 83 120 / 83 120 / 83 120 | in, ×3 | 0, 0, 0 | 3 191 808, ×3 | 102 400, ×3 | 3 072 / 0, ×3 |
| 262 144 | 291 959 / 281 569 / 277 413 | in, ×3 | 0, 0, 0 | 3 191 808, ×3 | 323 584 / 303 104 / 294 912 | 3 072 / 0, ×3 |
| 1 048 576 | 1 069 131 / 1 077 443 / 1 067 053 | in, ×3 | 0, 0, 0 | 3 191 808, ×3 | 1 093 632 / 1 110 016 / 1 089 536 | 3 072 / 0, ×3 |
| 8 388 608 (control, > W) | 3 191 808 (= W), ×3 | (control: ≥ W − 32 KiB) met, ×3 | 1, 1, 1 | 3 191 808, ×3 | 3 227 648 / 3 260 416 / 3 244 032 | 3 072 / 0, ×3 |

Each JVM ran `Tests run: 1, Failures: 0, Errors: 0` (about 14.3 s), so the `setMarks` reflection assertion held for every H (`run1/unit/unit-driver.log`, `unit-r*-excerpt.log`). No `FlushWaterMarkTest` process was left.

**Cluster tier.** Step 10 readings, from `run1/cluster/analyze-cluster.txt` (window [STOP+5 s, STOP+20 s], baseline = mean over the 10 s before the STOP; 29–30 samples in each window; B never marked DOWN; `props.txt` as listed):

| H on A (`props.txt`) | Run | Δ `netPoolUsed` max | Δ `directUsed` max | max `pendingBytes` | `overloadDrops` at window end | NMT "Other" committed (STOP+15 s) | stress op rate |
|---|---|---|---|---|---|---|---|
| stock 65 536 (no `-D`) | s1 | **0.065 MiB** | 0.067 MiB | 62.2 MiB | 0 | 232 180 KB | 6 025 op/s |
| stock | s2 | **0.118 MiB** | 0.063 MiB | 61.3 MiB | 0 | 232 191 KB | 6 141 op/s |
| 1 MiB (`-D…high=1048576`, low 524288) | s1 | **0.311 MiB** | 0.063 MiB | 63.2 MiB | 0 | 232 197 KB | 5 855 op/s |
| 1 MiB | s2 | **0.461 MiB** | 0.065 MiB | 66.8 MiB | 0 | 232 197 KB | 5 788 op/s |
| 256 MiB (`-D…high=268435456`) | s1 | **−67.6 MiB** | 56.8 MiB | 132.0 MiB | 64 635 | 389 422 KB | 6 021 op/s |
| 256 MiB | s2 | **−27.9 MiB** | 64.4 MiB | 132.0 MiB | 51 418 | 389 563 KB | 5 750 op/s |
| stock, no stall | ns | 0.106 MiB | 0.065 MiB | 63.4 MiB | 0 | 232 198 KB | 5 984 op/s |

Stress reported 0 errors in every run (`run1/cluster/<run>/stress-results.txt`). In no run did the node return to baseline within 30 s after CONT (`returned_within_30s False`).

**Supplementary absolute levels** (`run1/cluster/supplement.txt`; not a B3e reading and not used for the verdict):

| Run | mean `pendingBytes`, 10 s before STOP | mean `netPoolUsed`, 10 s before STOP | max `netPoolUsed` in window (absolute) | `netPoolUsed` series max / min | `directUsed` before STOP → window max |
|---|---|---|---|---|---|
| s1 / s2 stock | 46.1 / 45.1 MiB | 76 / 78 KiB | 142 / 198 KiB | 184 / 198 KiB; min 0 | 50.65 → 50.72 MiB |
| s1 / s2 1 MiB | 44.9 / 46.0 MiB | 992 / 860 KiB | 1 310 / 1 332 KiB | 1 576 / 1 440 KiB; min 0 | 50.67 → 50.73 MiB |
| s1 / s2 256 MiB | 72.7 / 66.9 MiB | 95 061 / 87 454 KiB | 25 840 / 58 926 KiB | **126 444 / 127 694 KiB; min −2 178 686 / −2 027 950 KiB** | 147.6 → 204.3 / 140.0 → 204.5 MiB |
| no-stall stock | 47.3 MiB | 51 KiB | 160 KiB | 160 KiB; min 0 | 50.67 → 50.73 MiB |

In both 256 MiB runs `netPoolUsed` peaked at ≈ 123.5 MiB, near `networking_cache_size: 128MiB`, at about the STOP. It then fell steadily while `directUsed` kept rising. It went **negative** 6.9 s / 8.3 s after the STOP and reached −2.08 GiB / −1.93 GiB by the end of sampling (`run1/cluster/s1-256m/samples.csv`, `s2-256m/samples.csv`).

### 4.2 Conclusion and logic

**Unit tier**

1. **Validity** — valid. Each H < W was driven past its mark, since `pendingBytes` ≈ W ≫ H. The control ran with `isWritable = 1`. The relay stall reached Netty: `flushingBytes` > 0 for every H. Reflection took effect (tests passed with the `setMarks` assertion). Every message was delivered after resume (`received = 3 072`, `flushingAfterResume = 0`). [observed: `run1/unit/unit-r*.rows`, `unit-driver.log`]
2. **Readings** — `flushingBytes` sits inside the band every time, but usually **below** the "usually ceil(H/B)·B" figure of B2f (e.g. 83 120 = 80 messages at stock, not ≈ 130 914). The frames in flight were partly filled. B2f allows this ("early partial frames may make it smaller, but never below H"). [observed: `analyze-unit.txt`] [inferred: delivery started while the burst was still being enqueued, so the first frames were short]
3. **Matched row** — B2g row 1, "`flushingBytes` in `[H, H+65 515)` for each H < W, and ≈ W for the 8 MiB control → Claim confirmed". It holds per S4-A2 in all three repeats: each H < W has `flushingBytes` in the band with `isWritable = 0`, the control has `flushingBytes` = W ≥ W − 32 KiB with `isWritable = 1`, and the control's `poolDelta` is 3.23–3.26 MB ≥ 1 MiB. [observed: `analyze-unit.txt`, OK on all 15 rows]
4. **Excluded rows** — row 2 (≥ H + 65 515): the largest overshoot is 46 934 B (63 318 − 16 384, r3), under 65 515. Row 3 (≈ W for all H): only the control is ≈ W, and the rest range from 50 862 to 1 077 443. Row 4 (< H with `isWritable = 0`): none. Row 5 (control stalls near 64–128 KB): the control reached W. Row 6 (all 0): none is 0. Row 7 (`poolDelta` flat): `poolDelta` follows `flushingBytes`, from 55 296 to 3.26 MB (within +1 % to +3 % of it at H ≥ 1 MiB and in the control, and ≤ 512 KiB at H ≤ 64 KiB, as B2f says). Row 8 (losses or a leak): `received = N`, `flushingAfterResume = 0`. [observed: same files]
5. **Observed vs. inferred** — the conclusion rests only on observed values. The one inferred point, why frames were partly filled, does not affect the row.
6. **Deviations and gaps** — fix 1 changed extraction only. `poolDelta` is the shared pool's delta and is per buffer (`BufferPool.java:950`), and it tracks `flushingBytes` closely. The unit tier is the only tier with direct disallow evidence (`isWritable = 0`).
7. **Core question** — yes. The off-heap bytes in flight follow H, at 0.05, 0.08, 0.28, 1.07 MB for H = 16 KiB, 64 KiB, 256 KiB, 1 MiB. They stop at most one partial frame above H. The disallow branch (`isWritable = 0`, `OutboundConnection.java:855`) has fired every time, while the uncapped control serializes the whole 3.19 MB backlog off-heap. The mark caps the serialized off-heap share per small-message connection, not the backlog, which stays at W for every H (parts 1, 3, 4).

**Conclusion (unit, one line):** B2g row 1 — **confirmed** (S4-A2 Confirmed in 3/3 repeats).

**Cluster tier**

1. **Validity** — valid as a run. Every stalled run reached max `pendingBytes` ≥ 20 MiB (61–132 MiB). `props.txt` shows the intended `-D` for each value (none for stock). B was never convicted (no DOWN line). Each window had 29–30 samples, and the baseline had ≥ 10 s of samples (the first sample 33 s before the STOP). [observed: `analyze-cluster.txt`, `<run>/props.txt`, `<run>/systemA-excerpt.log`]
2. **Readings** — three readings were unexpected. (a) **The backlog did not need the stall.** At ~6 000 op/s, B on the m400 never kept up: `pendingBytes` was already 45–47 MiB in the 10 s before the STOP in every stock and 1 MiB run, and 47 MiB in the no-stall run. So the mark already bound before the STOP. The H = 1 MiB baseline was 0.86–0.99 MiB of pool in use, and its Δ could only be the last fraction of a megabyte. [observed: `supplement.txt`] (b) **In the 256 MiB control, the pool metric turned negative.** `netPoolUsed` peaked at ≈ 123.5 MiB, near `networking_cache_size` (128 MiB), fell, went negative 7–8 s after the STOP, and reached about −2 GiB. Meanwhile `directUsed` rose from 140–148 to 204 MiB, and NMT "Other" was 389 MB against 232 MB in the stock and 1 MiB runs. [observed: `s1-256m/samples.csv`, `s2-256m/samples.csv`, `nmt.txt`] [inferred: a `BufferPool` accounting bug once the pool overflows (§8 findings)] (c) No run returned to baseline within 30 s of CONT, because B stays behind throughout. [observed: `analyze-cluster.txt`]
3. **Matched row** — B3g row 5: "The 256 MiB control's Δ stays ≤ 3 MiB → The positive control did not move. Either the pool metric does not see these buffers or the stall does not reach Netty (not confirmed). Check `directUsed` and NMT." The control's Δ`netPoolUsed` is −67.6 / −27.9 MiB (≤ 3 MiB). Under S4-A3 this is **Not confirmed** (the control's Δ ≤ 3 MiB; also the H = 1 MiB Δ of 0.311 / 0.461 MiB misses [1, 3] MiB). The row's own check, `directUsed` and NMT, shows that the stall did reach Netty and that real off-heap memory did grow in the control (+56.8 / +64.4 MiB direct in the window; +157 242 KB of NMT "Other" against stock). The metric did not see it. [observed: same files]
4. **Excluded rows** — row 1 (confirmed): the 1 MiB Δ is below 1 MiB and the control's Δ does not follow `pendingBytes`. Row 2 (**refuted**: stock Δ ≥ 8 MiB with `pendingBytes` ≫ 8 MiB): the stock Δ is 0.065 / 0.118 MiB and the absolute max is ≤ 198 KiB, so it is not met. Row 3 (Δ the same for all three H): the stock, 1 MiB and control Δ differ (≈ 0.1, ≈ 0.4, −28…−68 MiB), and the `-D` values took effect (`props.txt`). Row 4 (`pendingBytes` < 20 MiB): every max is ≥ 61 MiB. Row 6 (B DOWN): none. [observed]
5. **Observed vs. inferred** — the matched row rests on observed values. Two things are inferred: that the negative `UsedSize` is a metric bug, not freed memory, and that the pre-STOP backlog comes from B's slowness on the m400. Neither changes the row. The first is supported by `directUsed` and NMT rising while the metric fell. The second is supported by `pendingBytes` 45–47 MiB in the no-stall run.
6. **Deviations and gaps** — fixes 2–5 (§3). The design's assumption that the link is idle without the stall does not hold on this hardware, so the Δ-against-baseline reading cannot show the 1 MiB band. The cluster tier still has no direct disallow observable (R-a).
7. **Core question** — the absolute levels are consistent with a cap. Stock holds ≤ 198 KiB and 1 MiB holds ≤ 1.58 MiB of networking pool, with 45–67 MiB of backlog on the heap. The uncapped control serialized the backlog off-heap: about 124 MiB of pool, then direct memory up to 204 MiB. But the frozen B3e reading (Δ in the window) does not show it. The 1 MiB band is missed because the cap already bound before the STOP. The positive control's metric is broken by the overflow accounting. So by the audited logic, the cluster tier does not settle the question (parts 2, 3).

**Conclusion (cluster, one line):** B3g row 5 — **not confirmed** (positive control's Δ`netPoolUsed` ≤ 3 MiB; H = 1 MiB band missed).

## 5. Self-check of run 1 — AI

### 5.1 Check of run 1's conclusion

| Part | Holds? | Note (file re-read) |
|---|---|---|
| 1. Validity | yes | `run1/unit/unit-r{1,2,3}.rows`: 15 rows, `received` 3 072 and `flushingAfterResume` 0 in each. `unit-driver.log`: three `Tests run: 1, Failures: 0, Errors: 0`. Cluster: `props.txt` for each of the 7 runs re-read (stock empty; 1 MiB 524288/1048576; 256 MiB 134217728/268435456). `systemA-excerpt.log`: the only UP/DOWN line is B's initial UP. In `driver-excerpt.log` the first sample is 33 s before STOP. |
| 2. Readings | yes | `supplement.txt` recomputed from the copied `samples.csv`: the pre-STOP `pendingBytes` is 45–47 MiB in the stock and 1 MiB runs, the no-stall value 47.3 MiB, the control's series min −2 178 686 / −2 027 950 KiB. The `s1-256m/samples.csv` rows from −2 s to +8 s re-read: peak 129 478 656 B at +0.2 s, first negative (−5 623 992) at +6.9 s, with the first 1 578 drops. |
| 3. Matched row | yes | Unit: `analyze-unit.txt` OK on all 15 rows, against S4-A2's definition re-read in `case-amended.md` D. Cluster: `analyze-cluster.txt` re-read. The control's `dNet_max` is −67.598 / −27.860 MiB (≤ 3 MiB). The 1 MiB values are 0.311 / 0.461 (< 1 MiB). S4-A3 maps this to Not confirmed. The Refuted condition (stock ≥ 8 MiB) is not met: 0.065 / 0.118. |
| 4. Excluded rows | yes | Each B2g and B3g row checked above against the same files. Refuted rows: B2g rows 2 and 3, and B3g rows 2 and 3, are each ruled out by a cited number. |
| 5. Observed vs. inferred | yes | The verdict rows use only observed numbers. The metric-bug explanation is inferred from code (`BufferPool.java:233-239, 249-258, 818-821, 877-886`) and from `directUsed`/NMT. It is labelled as inferred and does not decide the row. |
| 6. Deviations and gaps | yes | Each fix in §3 was made before the readings it affects; the superseded runs are not used. One fix (5) was found from the s1 readings of the superseded set, and that set is not used. The final tier is a full restart, with B3f/B3g byte-identical to the frozen hashes (`harness/freeze-tables.sha256`). |
| 7. Core question | yes | The unit tier answers it directly: the cap follows H, with `isWritable = 0`. The cluster tier cannot answer it under the frozen reading, and the answer says so rather than relying on the absolute levels. |

### 5.2 Run 2?

**No** (2026-11-25). The unit verdict rests on observed readings that agree exactly across three repeats. The cluster verdict is Not confirmed for reasons of hardware and instruments, not reasoning, and a repeat by hand on the same node would hit the same backlog without the stall and the same metric bug. A better cluster run needs a changed design (below), not a run 2.

## 6. Run 2 — fresh AI session (optional)

Not done (§5.2).

## 8. Verdict — AI

**Stage-3 estimate:** positive. **Outcome class:** **weak true positive** — unit Confirmed (caps), cluster Not confirmed (undetermined), so the class is taken from the unit tier alone (rule of 2026-10-29); counted separately from TP.

**Claim tested (B1):** for a small-message `OutboundConnection` whose peer has stopped reading, the off-heap in-flight bytes (`flushingBytes`, and the networking-pool memory behind them) settle at `F` with `H ≤ F < H + 65 515` whenever the backlog exceeds `H`, and `F` follows `H`. With stock `H = 65 536`, the networking off-heap usage for a stalled peer stays within about 128 KiB per connection while the backlog grows to tens of MiB on the heap.

| Tier | Verdict (B2g / B3g row) | Effect on the constraint | Basis | Date |
|---|---|---|---|---|
| Unit | **Confirmed** — B2g row 1 (S4-A2, 3/3 repeats): `flushingBytes` 50 862–63 318 / 83 120 / 277 413–291 959 / 1 067 053–1 077 443 B for H = 16 Ki / 64 Ki / 256 Ki / 1 Mi, `isWritable = 0`; 8 MiB control = W = 3 191 808 B with `isWritable = 1`; `poolDelta` follows | **caps** (the serialized off-heap bytes in flight per small/urgent connection; not the backlog) | run 1 + self-check | 2026-11-25 |
| Cluster | **Not confirmed** — B3g row 5 (S4-A3): the control's Δ`netPoolUsed` −67.6 / −27.9 MiB (≤ 3 MiB, the pool metric went negative); H = 1 MiB Δ 0.311 / 0.461 MiB (band [1, 3] missed: the backlog already existed before the stall); stock Δ 0.065 / 0.118 MiB | **undetermined** | run 1 + self-check | 2026-11-25 |

**Findings for the record:**
- **Bug (metric accounting), `BufferPool` overflow path.** For a buffer allocated outside the pool (overflow), `BufferPool.putUnusedPortion` subtracts the unused portion from `overflowMemoryUsage` (`BufferPool.java:877-886`). The buffer keeps its full capacity, though, and `put` later subtracts the whole capacity again (`:240-246`, `:818-821`). The allocation added only the capacity (`:233-239`). So every trimmed overflow buffer lowers the counter by its unused portion for good. Once the networking pool passes `networking_cache_size`, CQL and internode frames go to overflow, and `BufferPool.networking` `UsedSize` (and `OverflowSize`) drift without bound: −2.08 GiB after ~75 s at ~6 000 op/s, while real direct memory was 204 MiB. Only metrics read these counters (`BufferPoolMetrics.java:56-62`, `BufferPoolAllocator.java:89-97`), so it is a monitoring bug, not a functional one. It hides real off-heap growth exactly when the pool is exhausted. [observed: samples; inferred cause: code reading]
- **Not settable.** `OutboundConnectionSettings.withNettyBufferBounds` ignores its argument (`OutboundConnectionSettings.java:251-258`). The mark can be changed only by a source change (R-b).
- **Memory holders worth an OOM look.** (1) The on-heap send queue per endpoint: with a slow, not stalled, replica on the m400, A held 45–67 MiB, and up to 132 MiB (4 MiB + 128 MiB reserve; global reserve 512 MiB) once stalled, with node A in back-to-back G1 old-generation collections at a 2 GiB heap. This mark keeps that backlog on-heap by design. (2) With the mark raised (as in the control), the same backlog moves off-heap: about 124 MiB of networking pool and then unpooled direct memory, bounded only by the send-queue capacities and `-XX:MaxDirectMemorySize`.
- **Recommendations for stage 3** (left, not applied): (a) measure the cluster tier as absolute levels against a no-stall run at a write rate the peer can keep up with, or throttle stress (e.g. `-rate threads=32 fixed=2000/s` on m400), so the baseline holds nothing in flight; (b) read `directUsed`/NMT as the primary control observable, or sample `BufferPool` `Size` and `OverflowSize`, because `UsedSize` breaks after overflow; (c) R-a, a direct disallow observable; (d) fix A1's `:103` citation to `:104`.

**Feedback filed:** the case file's section D in `~/writeup-ext/out/o125/case-amended.md` (outside the repo; not committed, as instructed): S4-A4 and S4-D1 to S4-D5, plus the stage-4 result paragraph (sha256 with section D filled: `a6781a4a2b7a5b0a9e5c3d617b8c643783d198193166bda526ae8d8d7ec3ba12`). No repo file was edited.

**What stays on the node `ms0640`:** `/mydata/jingsong-cass-s4/o125/` (9.0 MB): `harness/`, `logs/` (unit logs), `logs-unit-superseded-prefix1/`, `runs/` (7 final cluster runs: samples, props, NMT, stress and system logs), `runs-superseded-defect4/`, `runs-superseded-defect5/`, `runs-defect3-s1-stock/`, `confA/`, `confB/`, `sampler/` (compiled class). Deleted: `src/` (unit copy), `cass/` (patched copy and jar), `nodeA/`, `nodeB/` (data). No process of this run is left (checked with `ps -u $(id -un)`, and the ports 7000/7199/7299/9042 are free). The node lock `/mydata/s4/NODE-LOCK` was released at 11:35 MST, and `/mydata/s4/DRIVER-jingsong-c125.pid` is gone.
