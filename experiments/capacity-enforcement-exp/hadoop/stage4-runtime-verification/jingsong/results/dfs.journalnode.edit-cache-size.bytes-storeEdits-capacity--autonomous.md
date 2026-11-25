# dfs.journalnode.edit-cache-size.bytes-storeEdits-capacity--autonomous — stage-4 results  <!-- file: results/dfs.journalnode.edit-cache-size.bytes-storeEdits-capacity--autonomous.md -->

> **Case:** `dfs.journalnode.edit-cache-size.bytes-storeEdits-capacity--autonomous` (order 20; the amended case file is
> written outside the repo at `~/writeup-hadoop/out/o20/case-amended.md`)
>
> **Status:** verdict filed (2026-11-25) — unit Confirmed — caps (overflow bypass confirmed); cluster Confirmed — caps
> (attempt 3, after the AM10 "no row fits" amendment); overflow bypass at `capacity` = 2147483647 confirmed at both tiers
>
> **Outcome class:** true positive (estimate `positive`, effect `caps only on some paths (bypass)`, which counts as caps)
>
> **Agent:** autonomous (the suffix of the case-file stem). "§9a" below means each tier's predictions and conclusions
> table: B2f and B2g (unit), B3f and B3g (cluster); "§9b–§9e" means B2a–B2e or B3a–B3e; and the case file's feedback
> section is its section D.

**Layout.** Hadoop, Jingsong's share, run by a fresh stage-4 agent working as Jingsong on node `pc72`. This file, the
harness (`~/writeup-hadoop/out/o20/harness/`), small evidence copies (`~/writeup-hadoop/out/o20/run1/`) and the amended
case file (`~/writeup-hadoop/out/o20/case-amended.md`) are outside the repository; the parent session files them.
Protocol: `experiments/capacity-enforcement-exp/stage4-runtime-verification/README.md` ("The run protocol"); environment:
`hadoop/stage4-runtime-verification/jingsong/environment.md`. Below, `R` =
`/mydata/jingsong-s4/dfs.journalnode.edit-cache-size.bytes-storeEdits-capacity-run1` on `pc72`; N = the JN's capacity
(from its "Enabling the journaled edits cache with a capacity of bytes: N" line); `b` = mean batch from JMX.
A partial draft from the interrupted 2026-11-24 attempt was in `~/writeup-hadoop/out/o20/` and was ignored (moved to
`attic/`); no run folder for this stem existed on `pc72`.

## 1. Before run 1 — design audit and freeze

| Field | Content |
|---|---|
| **Case-file version** | Repository commit `bef6bc8a6` (2026-11-24) holds the stage-3 file; sha256 before the audit `6bccd590bb13c619cb313341b1e448e3a19533eb8dd8687f75ff6ab64bacf9bc` (matches `_INDEX.md` §4). After audit amendments AM1–AM9 (2026-11-25 11:51:54Z, before any harness run or reading): **`fe68112a69026c32e0a7a595e6f7618c39b0b1064e1a8c7561241995a60e9933`** (frozen for the unit tier and cluster attempts 1–2). After the run-1 defect fix D1 (cluster tier): `b82ebd00f16c15e67bf53b0c2187d27328cd656c37ea040442d72123a5e528c9`. After AM10 ("no row fits", 2026-11-25 12:15:51Z, before cluster attempt 3): **`c503253ab50927fdd7a09ff8f2adc2c25331766fab0443d96339767c6ca781bd`** (frozen for cluster attempt 3). Text hashes (`sed -n '/^\*\*B2f\./,/^\*\*B2h\./p' <file> \| sed '$d' \| sha256sum`): B2f+B2g `16209418376485fb32ef0d07a2c2c1bb6b8f05c4b2dd3e24cbe11ff70f305a66`, B3f+B3g `103e1d221c75e47adaa003db14140283bd7028d35221c9ba832dcbf12655b3f9` for attempts 1–2 and `1807c09125ffa36b305d9303fa3d4f7b9a9a1f02e1e59bbf3b9549bbcb89662f` from AM10 on (only the "[AM10]" markers on the B3f/B3g headings changed; the amendment text itself is in the block next to B2). After section D was filled (no other change): whole file `27a10c4de73e2b063f4feca8d832789caf9a147df2970efca0f7501ec755964d`. |
| **Harness** | `~/writeup-hadoop/out/o20/harness/`: `TestJournaledEditsCacheCap.java` (md5 `ff5b4585…`), `unit-run.sh` (`f27ecba9…`), `RoundDriver.java` (`e612be89…`), `sample.py` (`ad1ae4d1…`), `cluster-run.sh` (attempt 1 `f62f106c…`; attempt 2 after D1 `cdce7725…`; attempt 3 after AM10 `4755be65…`), `cluster-all.sh` (`c764ab5d…`), `hprof_cache.py` (`43241bcb…`), `analyze.py` (evaluation only). Also `adhoc-dump-attempt2.sh` (the K4 dump of attempt 2). Copied to `R/harness/`; md5 sums are logged at the top of every run log. Instrument checks (made within run 1, before any reading was used): the upstream `TestJournaledEditsCache` passes (11/11) in the copy; the in-process histogram reproduces U4's held bytes to within 24 B of 2600 × (2²⁰ + 16) (`run1/unit/capu-readings.txt`); `RoundDriver` compiled against the distribution classpath and each round reports path length 7033 and rc 0 (`run1/cluster/attempt3/*/cluster-run.log`, `rounds.log` on the node); `hprof_cache.py` gives a cache sum equal to the reflected `totalSize` field in every dump. |
| **Tiers and values** | Unit (B2): U1 C ∈ {4096, 65536, 1048576}; U2 C ∈ {L, L − 1}, L = 14 892; U3 fraction ∈ {0.1, 0.5}; U4 C ∈ {1 GiB control, 2147483647}. Cluster (B3): K1 65 536; K2 8 MiB; K3 64 MiB; K4 256 MiB; K5 unset (fraction 0.5 → 477 364 224); K0 cache off; K6 control 1 GiB and 2147483647 at JN `-Xmx6g`. K7 not run (AM7). |
| **Audit bottom line** | **Ready after amendments** — 2026-11-25 |

### 1.1 Design audit

| Group | Check | Rating | Note (section checked) |
|---|---|---|---|
| A. Core question | constrained quantity is memory or disk bytes | Met | A2/B1: JN heap held by `JournaledEditsCache.dataMap` (`byte[]` payloads); operand `totalSize` vs `capacity`. |
| A. Core question | knob varied, ≥ 3 values incl. default | Met | B2b: 4 KiB, 64 KiB, 1 MiB, derived default (U3); B3b: 64 KiB, 8, 64, 256 MiB and unset (K5), plus off (K0). |
| A. Core question | real resource measured, not only the counter | Met (gap named) | Unit: reflection counter plus `sumLen` and an in-process histogram (optional). Cluster: `[B` live bytes from a forced-GC histogram; B3d names the attribution gap and offers a heap dump. |
| A. Core question | usage driven to the limit and past it | Met | U1: 10 × C; U4: 2.54 GiB; B3c: 600 MB (≥ 2.3 × K4), 1.25 GB for K5, 3.7 GB for K6. |
| A. Core question | positive control (negative estimate only) | n/a (positive estimate) | K0 (cache off) and K6's 1 GiB control present anyway. |
| B. Logic | each step says what it establishes | Met | B2h, B3h. |
| B. Logic | prediction in numbers or a clear relation | Met | B2f exact; B3f "≈ N, −1 batch, + ≤ 2 MB" (made explicit by AM8). |
| B. Logic | every plausible outcome has a row with its evidence | Partly → Met | Rows had no verdict wording, and "limit not reached", "plateau below N", "JN OOM" were missing. **Amended** (AM9). The outcome actually seen (cache capped, `[B` offset by a retained response copy) was still missing; **amended after attempt 2** (AM10, §3). |
| B. Logic | confirmation needs ceiling-follows-knob and disallow evidence | Met | Unit: `totalSize` ceiling vs C plus U2's WARN and `CacheMissException`; cluster: plateaus vs N plus K1's "too large" WARN count and the nn2 fallbacks. |
| B. Logic | alternative explanations and their controls | Met | K0 (cache off), `TreeMap$Entry` cross-check, JMX `BytesWritten`, K6 control. |
| C. Specific | a human can follow it from the intro and §9a | Met | Estimate line, A3, B1. |
| C. Specific | an AI can run §9b–§9e without re-deriving | Partly → Met | Paths (`~/hadoop-3.4.2`, `/mydata/<you>/s4`), JDK 8 tool paths, `--forcemanual` prompt, the JN's own conf dir, and async edit logging splitting batches (AM1, AM3, AM4). |
| C. Specific | knob, values, workload, commands, observables, stop conditions exact | Partly → Met | Sampling and baseline mechanics (AM6, later D1), tolerances (AM8). |
| D. Runnable | harness and prerequisites exist or are listed | Met | Test class, sampler, driver are step-1 work; JDK 8, Maven 3.6.3, built 3.4.2 distribution on `pc72` (environment.md Node table, 2026-11-24). |
| D. Runnable | workload arithmetic reaches the limit | Met | 30-op deep `mkdirs` ≈ 102 KB per batch (measured 101 954 B mean); 120 rounds ≈ 624 MB > 256 MiB; disk ≤ 4 GB per run against 705 GB free; RAM 125 GiB. Ports 8020/8021/8480/8485/9870/9871 free. |
| D. Runnable | load-bearing citations spot-checked | Met | `systems/hadoop/source/` (clean): `JournaledEditsCache.java:120, 125-140, 278-282, 283-292, 303, 390, 427`; `Journal.java:170, 180-187, 258, 432-434, 746-791`; `DFSConfigKeys.java:1350-1352, 1469-1474`, `:423-425` (async logging default true); `FSEditLogAsync.run` (syncs when its queue runs dry); `QuorumJournalManager.java:77-78` (max-txns 5000), `:527-528` (fallback WARN); `QJMTestUtil.createTxnData`; `hadoop-project/pom.xml:187`. All as cited (the case's `Journal.java` ranges are within a few lines). |

| # | Recommendation | Applied? | Why |
|---|---|---|---|
| AM1 | Node paths, per-case source copy and distribution copy, JDK 8 tools | Applied 2026-11-25 (frozen `fe68112a…`) | filed paths do not exist |
| AM2 | Unit test prints readings, no assertions; in-process histogram; U3 batch size | Applied 2026-11-25 | every reading reaches the log |
| AM3 | `dfs.namenode.edits.asynclogging=false` on both NNs | Applied 2026-11-25 | async logging can split a `mkdirs` into small batches (source), which would break B3c's batch arithmetic and K1's prediction |
| AM4 | JN's own conf dir; exact commands (`-nonInteractive`, no `--forcemanual`, `safemode wait` on nn1) | Applied 2026-11-25 | knob and K0 setting reach only the JN; commands run unattended |
| AM5 | Rounds via `FsShell` in one JVM per 10 rounds | Applied 2026-11-25 | same client code and RPCs; ~1 s per round instead of ~4 s |
| AM6 | Sampler and run order | Applied 2026-11-25 | exact procedure |
| AM7 | K7 not run; K6 if time | Applied 2026-11-25 | 3-hour cap (K6 was run) |
| AM8 | Tolerances explicit | Applied 2026-11-25 | a reading must be able to contradict the prediction |
| AM9 | Verdict wording and missing rows | Applied 2026-11-25 | every outcome needs a row before any reading |
| D1 | Steady baseline (runbook defect, §3) | Applied 2026-11-25, cluster tier restarted | baseline taken too early |
| AM10 | Heap-dump attribution as the primary cluster observable; new rows (§3) | Applied 2026-11-25 after attempt 2, cluster tier restarted | "no row fits" (README, Compare and decide) |
| S1 | B3f's K5 bracket "470–500 MiB" is in MB (0.5 × 954 728 448 B = 477 364 224 B = 455 MiB) | Left for stage 3 | the verdict uses N from the log, as B3b says |
| S2 | B2f's optional U1 histogram prediction should be taken against a baseline in the same state (see §4.2 part 2) | Left for stage 3 | optional instrument, no row uses it |
| S3 | The sampler read `RpcRequestCacheMissAmountNumOps`; the bean names it `RpcRequestCacheMissAmountNumMisses` | Left for stage 3 (values read from the saved final JMX JSON) | B3d naming |

**Agreement criteria** — not needed (no run 2, see 5.2).

## 2. Environment

| Field | Run 1 |
|---|---|
| Date | 2026-11-25 (UTC; node local time MST). Unit 11:52–11:53; cluster attempt 1 (K1 only) 11:53–11:57; attempt 2 (K1–K4) 11:57–12:19; attempt 3 (K1–K5, K0) 12:19–12:55; K6 12:55–13:33 |
| Node | `pc72` (`node2`, CloudLab experiment `jason92-326665`), 40 cores, 125 GiB RAM; node lock `/mydata/s4/NODE-LOCK` held throughout |
| OS and kernel | Ubuntu 22.04.2 LTS, `5.15.0-203-generic` |
| JDK | OpenJDK `1.8.0_514` (`JAVA_HOME=/usr/lib/jvm/java-8-openjdk-amd64`, also for `jcmd`/`jstat`); Maven 3.6.3 |
| Local source copy | `copy-source.sh` → `R/src` from `systems/hadoop/source/` (rel/release-3.4.2) at repository HEAD `cd9e1cded`; distribution copied from `/mydata/jingsong-s4/hadoop-base/hadoop-dist/target/hadoop-3.4.2` to `R/hadoop` (`Hadoop 3.4.2`) |
| Case-file / harness commit | not committed (outside the repo); frozen by sha256 (§1); harness md5 in §1 and in each run log |
| Storage | `/mydata` (local LVM, 753 GB, ~705 GB free); all run data under `R/` |
| Full logs | `R/logs/unit/` (surefire reports, `unit-run.log`), `R/cluster/<K>/` (attempt 3: `cluster-run.log`, gzipped JN/NN logs, `out/` with readings, histograms, JMX, heap attributions), `R/cluster/attempt1/`, `R/cluster/attempt2/`; small copies in `~/writeup-hadoop/out/o20/run1/` |

## 3. Runbook defects

| # | Run | Step | Problem | Fix | Decision (date) | Case-file change |
|---|---|---|---|---|---|---|
| D1 | 1, cluster attempt 1 (K1) | B3e step 6 (baseline) | Taken 5 s after the transition, the baseline held ~7.9 MB of live `byte[]` that were gone by round 10 and never returned (`[B` 10 777 952 → 3 728 592 → 2 858 376 → 2 846 152 B, `run1/cluster/attempt1/K1/readings.csv`). Every `Δ[B` would be offset by about −7.9 MB. | Pre-baseline samples every 30 s; baseline once two consecutive agree within 1 MiB. In every later run this settled at the third pre-sample (10.7 → 3.4 → 2.8 MB, e.g. `run1/cluster/attempt3/K2/cluster-run.log`). | 2026-11-25; cluster tier restarted from K1 (attempt 2); B3f/B3g unchanged | D1 note (dated) in the amendment block |
| D2 | 1, cluster attempt 2 (K1–K4) | B3g, "no row fits" | K2's `Δ[B` plateaued flat at 12.9 MiB = 1.61 × N, but `ΔEntry` = 81–91 ≈ N / `b` = 82, so B3h's cross-check failed. The K3 heap dump (B3d's optional dump) showed the cache at 67 026 460 B ≤ N and one live 5 203 919 B `byte[]` outside it, held by a protobuf `ByteString` (the `getJournaledEdits` response copy, `Journal.java:779-785`). "Plateau well above N → cap does not bound retained heap" contradicts the dump; "claim supported" misses its band. Attempt-2 K4's dump: cache 268 417 895 B, response copy 6 661 053 B (`run1/cluster/attempt2/K3-heap-attribution.txt`, `K4-heap-attribution.txt`). | AM10: a heap dump per run gives the cache payload P (primary); `Δ[B` keeps a band widened by the measured response copy R; new rows. Written from the attempt-2 readings, as the README's "No §9a row fits" path prescribes; it changes the observable and rows, not the claim. | 2026-11-25; attempt 2 stopped after K4; cluster tier restarted from K1 (attempt 3) | AM10 (dated) in the amendment block |

The unit tier ran once without defects. Attempt 3 ran without defects.

## 4. Run 1

**Scope:** unit U1–U4 and the upstream baseline; cluster K1, K2, K3, K4, K5, K0 and K6 (control and 2147483647) on
attempt 3; attempts 1 and 2 are kept as evidence for D1 and D2 and are not used for the verdict. **Command logs:**
`run1/unit/unit-run.log`; `run1/cluster/attempt3/<K>/cluster-run.log`.

### 4.1 Readings

**Unit tier** (`run1/unit/capu-readings.txt`; surefire reports in `run1/unit/u123/`, `u4/`, `baseline/`)

| Test or assertion | Prediction (B2f) | Result | Evidence |
|---|---|---|---|
| U1 C = 4096: max `totalSize`, final, entries | ≤ C; (C − b, C]; ≈ ⌊C/b⌋ | max 3750, final 3750 ∈ (3346, 4096], 5 entries (⌊4096/750⌋ = 5), `b` 731–750 B | `capu-readings.txt` "U1 FINAL C=4096" |
| U1 C = 65536 | same | max 65 531, final 65 360 ∈ (64 776, 65 536], 86 entries (⌊C/bMax⌋ = 86) | "U1 FINAL C=65536" |
| U1 C = 1048576 | same | max 1 048 573, final 1 048 320 ∈ (1 047 796, 1 048 576], 1344 entries (⌊C/bMax⌋ = 1344); 10 485 975 B stored in 13 586 calls | "U1 FINAL C=1048576" |
| U1 `sumLen == totalSize` | always | true at every call (`sumMismatchEver=false`) for all three C | same lines |
| U1 retrieval | lowest ok, txid 1 misses | `retrieveEdits(lowest)` ok (5 txns); `retrieveEdits(1)` → `CacheMissException` "Oldest txn ID available in the cache is …" for all three C | "U1 RETRIEVE" |
| U1 optional histogram at 1 MiB | `[B` ≈ 1 MiB + 16 B × entries above baseline | held − released `[B` = 4 980 960 B; heap used (after GC) held − released = 1 003 312 B; `TreeMap$Entry` +1344, `Long` +1344 | "HISTO U1-…", "HEAPUSED U1-…" (see §4.2 part 2) |
| U2 C = L = 14 892 | stored, then evicted by 201–210 | after 1–200: `totalSize` 14 892, 1 entry; after 201–210: 750, 1 entry, first key 201; no WARN | "U2 CAP=L" |
| U2 C = L − 1 | rejected, WARN, cache empty | `totalSize` 0, 0 entries, WARN "A single batch of edits was too large" captured, `retrieveEdits(1,1)` → `CacheMissException` "Cache is empty" | "U2 CAP=L-1" |
| U3 f = 0.1, 0.5 | `getCapacity() == (int)(maxMemory × f)`; `totalSize` ≤ cap | 205 730 608 and 1 028 653 056 (maxMemory 2 057 306 112), both equal; max `totalSize` 3 376 894 ≤ cap | "U3 f=…" |
| U4 control 1 GiB | 1024 entries, `totalSize` = 2³⁰ from call 1024 | entries 1024 and `totalSize` 1 073 741 824 from call 1024 to 2600; held `[B` 1 074 007 920 B, released 249 688 B | "U4 control1GiB …" |
| U4 `Integer.MAX_VALUE` | 2047 entries at 2047; at 2048 `totalSize` = −2³¹, 2048 entries; 2600 at the end, negative; `[B` ≈ 2.54 GiB | call 2047: 2 146 435 072, 2047 entries; call 2048: **−2 147 483 648**, 2048 entries; call 2600: −1 568 669 696, **2600 entries**, `sumLen` 2 726 297 600; held `[B` 2 726 588 912 B (2.54 GiB) | "U4 max …", "HISTO U4-max-held" |
| Upstream `TestJournaledEditsCache` | passes | 11 run, 0 failures | `run1/unit/baseline/` |

JVMs: U1–U3 `-Xmx2048m` (maxMemory 2 024 275 968 / 2 057 306 112), U4 `-Xmx5g` (4 772 593 664), Parallel GC, JDK 1.8.0_514
(the `ENV` lines).

**Cluster tier, attempt 3** (`run1/cluster/attempt3/<K>/readings.csv`, `heap-attribution.txt`, `cluster-run.log`). Every
run: `b` = 101 954 B (K5 101 981), 6125 batches / 174 245 transactions (K5 12 757 / 363 007), so 624 469 405 B written
(K5 1 300 977 869); nn2 `standby` with `LastAppliedOrWrittenTxId` equal to the JN's `LastWrittenTxId`; no
"out of sync"; no leftover process. `Δ` = final minus the steady baseline (D1).

| Run | N (JN log) | Final `Δ[B` | `ΔEntry` (N/`b`) | Heap dump: cache P, entries, `totalSize` | R (response copy) | Other | Evidence |
|---|---|---|---|---|---|---|---|
| K1 | 65 536 | 880 B | 10 (≈ 0) | not taken (AM10: K2–K6) | — | "too large" WARN **6000** (= 120 × 50 deep batches; first: input length 104 123); "Initializing edits cache" 6000; nn2 fallbacks 42; JMX cache misses 42; 6 txns served via RPC | `K1/cluster-run.log`, `K1/readings.csv`, node `out/histo/K1-final-jmx.json` |
| K2 | 8 388 608 | 13 533 224 B (12.91 MiB) | 91 (82) | **8 326 392 B** (0.9926 N), 82 entries, `totalSize` 8 326 392 | 5 203 936 B | no WARN; nn2 fallbacks 9 | `K2/heap-attribution.txt` |
| K3 | 67 108 864 | 75 576 000 B (72.07 MiB) | 666 (658) | **67 026 460 B** (0.9988 N), 657, same | 8 534 584 B | nn2 fallbacks 0 | `K3/heap-attribution.txt` |
| K4 | 268 435 456 | 273 681 128 B (261.0 MiB) | 2642 (2633) | **268 417 895 B** (0.99993 N), 2633, same | 5 203 936 B | — | `K4/heap-attribution.txt` |
| K5 | 477 364 224 (unset; 0.5 × 954 728 448) | 482 612 120 B (460.3 MiB) | 4689 (4681) | **477 302 902 B** (0.99987 N), 4680, same | 5 203 936 B | — | `K5/heap-attribution.txt`, `K5/jn-capacity-line.txt` |
| K0 | — (no "Enabling" line) | 96 B | 0 | not taken | — | nn2 fallbacks 62 ("The journal edits cache is not enabled") | `K0/cluster-run.log`, `K0/fallback-first3.txt` |
| K6 control | 1 073 741 824, `-Xmx6g` | 1 079 111 560 B (1029 MiB) | 10 536 (10 528) | **1 073 671 081 B** (0.99993 N), 10 527, same | 5 203 936 B | 3 902 933 539 B written in 38 267 batches; plateau 1029–1046 MiB from round 210; nn2 at txid 1 089 019, JN JMX (read 30 s earlier) 1 089 017 | `K6ctl/…` |
| K6 | 2 147 483 647, `-Xmx6g` | 3 909 621 424 B (3729 MiB) | 38 278 (all batches) | **3 902 933 573 B** (1.82 × N; = every byte written), **38 269 entries = every batch written**, `totalSize` **−392 033 723** (= P − 2³²) | 5 828 472 B | 3 902 933 573 B / 38 269 batches written; no eviction, no WARN, no OOM; JN `VmRSS` 5.43 GB; nn2 = JN txid 1 089 019 | `K6/…` |

`Δ[B` series in MiB (every 10 rounds): K2 22.9, 15.0, 14.6, then 12.9–13.2 from round 40 to the end; K3 55.7, then
68.9–72.1 from round 20; K4 54.2, 104.6, 156.7, 204.9, 254.5, then 261.0–264.9 from round 60; K5 rising 56.3 … 453.0
to round 90, then 460.3–462.0 from round 100 (one sample 472.4 at round 160); K0 0.00–0.07 throughout; K1 ≤ 0.30.
Secondary process readings: `VmRSS` final 435 MB (K1), 502 MB (K2), 586 MB (K3), 764 MB (K4), 952 MB (K5), 434 MB (K0);
old-gen used after full GC 12.2, 25.5, 86.0, 279.5, 483.8, 12.2 MB.
K6 control: rising to 1009 MiB at round 200, then 1029–1046 MiB to round 750. K6: 253, 504, 762, 998 (round 200), 1245, 1494, 1742, 1991 (round 400), 2251, 2487, 2736, 2995, 3232, 3481, 3729 MiB (every 50 rounds to 750): linear, no plateau, through 2 GiB (`run1/cluster/attempt3/K6ctl/`, `K6/`).

### 4.2 Conclusion and logic

1. **Validity.** Unit: each method ran to its last reading in the intended JVM (heap, GC from `ENV`) **[observed:
   `capu-readings.txt`]**; the copy is unmodified (upstream test passes) **[observed: `run1/unit/baseline/`]**. Cluster
   attempt 3: the limit was passed in every capped run (624 MB written against at most 256 MiB; 1.30 GB against
   477 MB in K5; K6 3.90 GB against 1 GiB and 2 GiB, with `-Xmx6g`) **[observed: final JMX `BytesWritten`]**; hold-fixed settings confirmed: synchronous edit
   logging ("Edit logging is async:false" in the NN output) **[observed: `cluster-run.log`]**, the knob reached only the
   JN (its capacity line; none in K0) **[observed: `jn-capacity-line.txt`]**, batches ≈ 102 KB **[observed: JMX]**,
   steady baselines (third pre-sample within 1 MiB) **[observed: `cluster-run.log` "pre" lines]**, one journal ID `ns1`.
2. **Readings.** (a) The optional U1 histogram does not match its prediction: held − released `[B` is 4.98 MB against
   ≈ 1.07 MB, while heap-used after GC differs by 1.00 MB and `TreeMap$Entry`/`Long` by exactly the 1344 entries
   **[observed]**. The "held" histogram came right after 136 printed sample lines; the excess is other live `byte[]` at that
   instant, not the cache **[inferred: the cache's arrays are counted exactly by `sumLen` = 1 048 320 and by the entry
   count; U4's same instrument matches to 24 B]**. No B2g row uses this reading. (b) Cluster `Δ[B` exceeds the cache by a
   roughly constant 5–9 MB in K2–K5: one live `getJournaledEdits` response copy R (5.2–8.5 MB) **[observed: heap dumps]**;
   `Δ[B` − P − R is within ±0.03 MB in K2–K5 **[observed: 13 533 224 − 8 326 392 − 5 203 936 = 2 896 B; K3 14 956;
   K4 59 297; K5 105 282]**. (c) K2's first samples reach 22.9 MiB (round 10) before settling at 12.9 MiB **[observed]**:
   larger transient responses while nn2 catches up **[inferred: one response is bounded by 5000 transactions ≈ 17.9 MB
   at 3584 B per transaction, `QuorumJournalManager.java:78`]**. (d) The repeated R = 5 203 936 B across K2/K4/K5 and
   both attempts **[observed]** is the same catch-up response size; why exactly one response stays referenced after the
   RPC is not traced here **[gap]**.
3. **Matched rows.** Unit: **"U1: `maxTotalSize ≤ C` for all three C, and the plateau scales"** (finals 3750, 65 360,
   1 048 320, each within one batch below C) + **"U2: `L` stored at `capacity = L` and rejected at `L − 1`, with the WARN"**
   + U3 equality → AM9 **Confirmed — caps**; and **"U4: `totalSize` goes negative at call 2048 and entries keep rising to
   2600"** (control plateaus at 1024) → **overflow bypass confirmed**. Cluster (AM10): **"P in band for K2–K5 and scaling
   with N, `Δ[B` in its band, K1 with the WARN and no growth, K0 flat → Confirmed — caps"**: P/N = 0.9926, 0.9988,
   0.99993, 0.99987, each in (N − 105 KB, N] and equal to `totalSize`; P scales 8.05×, 32.2×, 57.3× from K2 (N: 8×, 32×,
   56.9×); `Δ[B` within [N − `b_max` − 2 MiB, N + R + 2 MiB] for all four; K1 Δ 880 B with 6000 WARNs; K0 Δ 96 B.
   K6: AM10 "P > 2³¹ − 1 with E rising and the control within its band → overflow bypass confirmed on a real JN" (control P = 0.99993 N; K6 P = 3 902 933 573 B, every batch kept, `totalSize` wrapped to −392 033 723).
4. **Excluded rows.** Unit: "U1 `totalSize > C` or `sumLen ≠ totalSize`" — never (max ≤ C, no mismatch); "plateau far
   below C" — finals ≥ 0.91 C; U2 "stored at L − 1 or no WARN" — rejected with WARN; U3 "≠" — equal; U4 "plateau near
   2047–2048" — 2600 entries; U4 "OOM or control not at 1024" — neither. Cluster (AM10 and AM9): **Refuted** "P > N" —
   P ≤ N in all; "no plateau / growth tracks edits" — flat after N in K2–K5 (series above); "plateaus equal" — 8.3, 67,
   268, 477 MB; Not confirmed "unattributed heap" — `Δ[B` − P − R ≤ 0.11 MB; "P < N − 2 `b_max`" — no; "limit not
   reached" — `BytesWritten` ≥ 1.3 N; "K0 grows like K2–K4" — K0 flat; JN OOM — none; "Refuted (single-batch part)" —
   K1 has 6000 WARNs and no growth. K6 rows: "K6 P ≤ 2³¹ − 1 at the end → overflow analysis wrong" — P = 1.82 × 2³¹; "K6: plateau at ≈ 2 GiB" (B3g) — the series passes 2 GiB at round ~410 without a break; control not plateauing — it plateaus at 1 GiB.
5. **Observed vs. inferred.** The conclusion depends on: (i) P from the heap-dump parser is the cache's payload — checked
   against the reflected `totalSize` field in the same dump (equal in every run) and the JN's own `TreeMap$Entry` count;
   (ii) the R array is the `getJournaledEdits` response copy — it is referenced by a protobuf `ByteString`, and the only
   `ByteString` the JN builds from edits is `Journal.java:779-785`; K1 (no cached data served) and K0 (no RPC serving) have
   no such excess; (iii) the U1 histogram excess is not the cache (part 2a).
6. **Deviations and gaps.** AM1–AM10 and D1 (dated, §1/§3). The cluster verdict rests on attempt 3, run after an
   amendment written from attempt-2 readings (D2): the claim and the prediction "P ≤ N, ≈ N" did not change, only the
   observable (dump instead of `Δ[B` alone) and the rows; attempt 2's own dumps (K3, K4) show the same result. K7 not
   run (per-entry overhead measured only at the unit tier: 1344 `TreeMap$Entry` (40 B) + `Long` (24 B) ≈ 86 KB, plus
   16 B array headers ≈ 21 KB, on a 1 MiB cap, ≈ 10 % with ~780 B batches; with ~102 KB batches ≈ 0.08 %). The sampler's cache-miss column is empty (S3); values come from the
   saved final JMX JSON. The retained response copy (up to ~18 MB at the default `max-txns`, bounded by min(N, one response))
   is JN heap outside the cap: an overshoot named by the case (A3 e), observed here as retained, not only transient.
7. **Core question.** Usage follows the constraint: at the unit tier the cache's bytes sit within one batch below C for
   C from 4 KiB to 1 GiB and a batch above C is refused (parts 3, 4); on a real JournalNode the cache's live payload is
   within one 102 KB batch below N for N = 8, 64, 256 MiB and the derived default 477 MB, scaling with N, while a 64 KiB cap
   refuses every 104 KB batch (parts 1, 3). So the knob caps the cache's heap. It does not cap all JN heap the
   cache path creates (one retained response copy, part 2b), and at `capacity` within one batch of `Integer.MAX_VALUE` the
   int sum overflows and eviction stops (U4; K6: no plateau, 3.63 GiB held, nothing evicted), which is the default on a JN heap above about 4 GiB.

**Conclusion (one line):** unit — "U1 supports + U2 boundary + U3" → **confirmed**, with "U4 overflow bypass confirmed";
cluster — AM10 "P in band for K2–K5 … → Confirmed — caps" → **confirmed**; K6 — overflow bypass confirmed on a real JN.

## 5. Self-check of run 1 — AI

### 5.1 Check of run 1's conclusion

| Part | Holds? | Note (file re-read) |
|---|---|---|
| 1. Validity | yes | Re-read `capu-readings.txt` ENV lines (heap, GC); `run1/unit/baseline/*TestJournaledEditsCache.txt` (11 run, 0 failures); attempt-3 `cluster-run.log` of K1–K5/K0: capacity lines, "async:false", pre-baseline lines, `BytesWritten` in final rows. |
| 2. Readings | yes | U1 histogram lines and HEAPUSED re-read (5 219 072 vs 238 112; 12 970 552 vs 11 967 240). Each `heap-attribution.txt` re-read; P + R vs `Δ[B` recomputed from `readings.csv` baseline/final rows. |
| 3. Matched row | yes | U1/U2/U3/U4 numbers re-read line by line against B2f; cluster P, entries, `totalSize`, bands recomputed by `analyze.py` and by hand for K2 and K5. |
| 4. Excluded rows | yes | Each AM9/AM10 row checked against a named reading; K1 WARN count 6000 and K0 "not enabled" fallbacks re-read in the logs. |
| 5. Observed vs. inferred | yes | (i) `totalSize` == P in every dump; (ii) referrer class `ByteString$LiteralByteString.bytes` in every dump, `Journal.java:779-785` re-read; (iii) holds, and no row depends on it. |
| 6. Deviations and gaps | yes | The D2 restart is the one judgement call: AM10 is dated before attempt 3, attempt 2's dumps agree with attempt 3, and attempt 2's `Δ[B` series (K2 12.9 MiB, K3 68.9, K4 262.4) match attempt 3's. |
| 7. Core question | yes | Ceiling follows the knob (P ≈ N for four N, U1 for three C) and the disallow branch is directly evidenced (K1: 6000 WARNs; U2: WARN + empty cache). |

### 5.2 Run 2?

**No** — 2026-11-25. The conclusion rests on observed readings (exact counters and heap-dump sums); the one inferred
statement it needs (R is the response copy) is supported by the referrer class and by K0/K1. The overflow bypass is
confirmed at the unit tier exactly as traced (call 2048) and on a real JN (K6: every batch kept, `totalSize` wrapped).

## 8. Verdict — AI

Jingsong may overrule any verdict at any time; record an override here with its date and reason.

**Stage-3 estimate:** positive. **Outcome class:** **true positive** — positive estimate, effect `caps only on some
paths (bypass)` (counted as caps): the cache's heap follows the knob and is capped at both tiers; the int-overflow
bypass at `capacity` ≈ `Integer.MAX_VALUE` is confirmed at both tiers (U4, K6).

**Claim tested:** "On a JournalNode with `dfs.ha.tail-edits.in-progress=true`, the heap held by one journal's edits cache
follows `dfs.journalnode.edit-cache-size.bytes` (or `fraction × maxMemory` when the bytes key is unset): the cached
payload never exceeds `capacity`, plateaus at about `capacity` once more is written, and scales with the knob; a single
batch larger than `capacity` leaves the cache empty. Sub-claim: with `capacity = Integer.MAX_VALUE` the cache does not
plateau at 2 GiB." (B1)

| Tier | Verdict | Effect on the constraint | Basis | Date |
|---|---|---|---|---|
| Unit | **Confirmed** — B2g "U1 … supports", "U2 … boundary confirmed", U3 equal (AM9); sub-claim: "U4 … Overflow bypass confirmed" | caps only on some paths (bypass) | run 1 + self-check | 2026-11-25 |
| Cluster | **Confirmed** — AM10 "P in band for K2–K5 and scaling with N, `Δ[B` in its band, K1 with the WARN and no growth, K0 flat"; K6: "overflow bypass confirmed on a real JN" | caps only on some paths (bypass) | run 1 (attempt 3) + self-check | 2026-11-25 |

**Overshoots recorded (not bypasses of the check):** one retained `getJournaledEdits` response copy outside the cap
(5.2–8.5 MB here; bounded by min(N, 5000 transactions)); per-entry `TreeMap$Entry` + `Long` + array header outside
`totalSize` (≈ 10 % at ~780 B batches, ≈ 0.08 % at ~102 KB batches; K7 not run).

**Feedback filed:** the amended case file `~/writeup-hadoop/out/o20/case-amended.md` carries AM1–AM10 and D1 (dated) and
its section D (Stage-4 feedback) is filled; the parent session files it in the repository, with the `_INDEX.md` row and
sha256 `27a10c4de73e2b063f4feca8d832789caf9a147df2970efca0f7501ec755964d` (the file with section D).
