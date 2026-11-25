# dfs.datanode.max.locked.memory-rescanCachedBlockMap-remaining--autonomous — stage-4 results  <!-- file: results/dfs.datanode.max.locked.memory-rescanCachedBlockMap-remaining--autonomous.md -->

> **Case:** [`dfs.datanode.max.locked.memory-rescanCachedBlockMap-remaining--autonomous`](../../../stage3-ai-deep-read/jingsong/cases/dfs.datanode.max.locked.memory-rescanCachedBlockMap-remaining--autonomous.md)
> (stage-3 queue order 22, Jingsong's share; at run time the amended case file is `~/writeup-hadoop/out/o22/case-amended.md`, outside the repository)
>
> **Status:** **verdict filed 2026-11-25** — unit **Confirmed** (caps), cluster **Confirmed** (caps); run on `pc72` (not `pc99`). One run 1 (phase 2 re-run once under A8), no run 2.
>
> **Outcome class:** **true positive** — stage-3 estimate `positive` against the stage-4 effect `caps` at both tiers ([definition](../../../../stage4-runtime-verification/README.md#outcome-class))
>
> **Agent:** autonomous (the suffix of the case-file stem). "§9a" below means each tier's predictions and conclusions table: B2f and B2g
> (unit), B3f and B3g (cluster); "§9b–§9e" means B2a–B2e or B3a–B3e; the case file's feedback section is its section D.

**Layout.** Hadoop, Jingsong's share, run by a fresh autonomous stage-4 agent. **This attempt runs on node `pc72`, not `pc99`:** the
first attempt (2026-11-25, `pc99`) wrote an audit (A1–A8) and a harness but ran nothing, because `pc99`'s node lock was held by a stale
`jingsong-o70-stage4` lock for the whole 60-min poll. Its files are kept unchanged in `~/writeup-hadoop/out/o22/prev-attempt-2026-11-25-pc99/`
(`results-blocked-stub.md`, `audit-draft.md`, `lockpoll.log`, `case-amended.md`, `harness-as-found/`). This retry re-audited that work,
reused what was valid and amended the rest (A9–A12) before any reading. At run time this file, the harness and the raw excerpts are outside
the repository: this file `~/writeup-hadoop/out/o22/results.md`, harness `~/writeup-hadoop/out/o22/harness/`, raw excerpts
`~/writeup-hadoop/out/o22/run1/` (cited below as `run1/...`), amended case file `~/writeup-hadoop/out/o22/case-amended.md`.

## 1. Before run 1 — design audit and freeze

| Field | Content |
|---|---|
| **Case-file version** | Autonomous file, repository commit `bef6bc8a6` (2026-11-24), repository HEAD at the audit `8bd1dfb31`, `systems/hadoop/source` clean; sha256 as filed `d8dac2b8e896a77973e6920b28c0bb9b93106783d43f8b86286b0164b632fd9e` (the copy in the first attempt's folder is byte-identical). First attempt's amendments A1–A8 gave `634aa45b…`. After this retry's amendments A9–A12 (2026-11-25, section D1b, before any reading): whole-file sha256 **`eb8f21a0728056263158c03eebf02cae206e7487b905f1a2f4e4e84552260d53`** (frozen version; copy `run1/case-amended-frozen.md`). |
| **Frozen tables** (sha256 of the text, `sed -n` ranges) | `**B2f.` … `**B2h.` (unit predictions and conclusions): `e5e721e241d975065ee5559a417a2e84e24d227ed7677f80687bcb4819f0cb34`; `**B3f.` … `**B3h.` (cluster): `e15d9f89b21b325fe77d4f4d998106f7c8179c60e102e8c10b40cc1c394d46eb`; `### D1.` to end (amendments A1–A12 with their added predictions and rows): `b947579fff1ca1b3c4c58eb3e663f9553d6026ab204d36b4d26651401cf71795`. Recorded 2026-11-25 12:08 EST / 10:08 MST (node), before any test, daemon or sampler ran. |
| **Harness** | `~/writeup-hadoop/out/o22/harness/` (from the first attempt, revised 2026-11-25 before any run), md5: `TestCrmPendingFit.java` `146f29ef`, `unit-run.sh` `3df87540`, `cluster-run.sh` `405b87a0`, `sampler.py` `0ebecbb8`, `selfcheck.py` `22f469e6`, `lockpoll.sh` `f21c4d72` (first attempt only, not used). Same files on the node in `<run>/harness/`. Not committed (outside the repository). Instrument checks before run 1: `bash -n` of both scripts and `python3` parse of both Python files OK; `unit-run.sh compile` BUILD SUCCESS 53 s (10:06 MST); `cluster-run.sh setup`: native `hadoop-common` BUILD SUCCESS 36 s, `hadoop checknative -a` → `hadoop: true …/cluster/hadoop/lib/native/libhadoop.so.1.0.0` (10:04 MST; `-a` exits 1 because zstd/bzip2/ISA-L/PMDK are absent, which the run does not need); sampler log-time parsing known-answer check (a UTC log stamp of "now" parses to now ± 0 s). Known answers inside the runs: unit `IFCHK,instr` (NoMlock manipulator, page size 4096, DN capacity = C) and the "Scanned" DEBUG count per window (A12); cluster "Starting DataNode with maxLockedMemory = M", NN Configured Cache Capacity = M before each phase, `nnScanLines` (A12). |
| **Tiers and values** | Unit (B2): MiniDFSCluster, 1 DN, 4096-byte blocks, `/f` 32 blocks; Test A C ∈ {16384, 32768, 65536}; Test B C = 65536 with NN cacheUsed U ∈ {0, 16384, 32768, 49152, 65536, 81920} and capacity C' ∈ {65536, 32768, 0}; Test C on the U = 49152 instance; ablation (line 534 disabled) U = 49152. Cluster (B3): pseudo-distributed NN + DN with native mlock, 16-MiB blocks, `/cap/f512` 512 MiB; phase 1 M ∈ {0 (default), 64m, 128m, 256m, 1g}; phase 2 M = 128m with 60-s cache reports. |
| **Audit bottom line** | **Ready after amendments** — 2026-11-25 (A1–A8 of the first attempt reviewed and kept; A9–A12 added) |

### 1.1 Design audit

The first attempt's ratings (`prev-attempt-2026-11-25-pc99/audit-draft.md`) were re-checked against the case file and the pinned source.
Kept where they hold; changed where this review found a gap.

| Group | Check | Rating | Note (section checked) |
|---|---|---|---|
| A. Core question | constrained quantity is memory or disk bytes | Met | A2/B1: mlocked DataNode memory for cached replicas; operand `remaining` = reported `cacheCapacity − cacheUsed`, the NameNode's view of it. |
| A. Core question | knob varied, ≥ 3 values incl. default | Met | B2b C ∈ {16384, 32768, 65536} plus the operand itself (U six values, C' three); B3b M ∈ {0 (default), 64m, 128m, 256m, 1g}. The default 0 is a value at the cluster tier only (unit Test A has no C = 0; the cluster covers it). |
| A. Core question | real resource measured, not only the counter | Met | B3d `VmLck` of the DN process besides JMX `CacheUsed`; B2d names the unit gap (mlock stubbed). |
| A. Core question | usage driven to the limit and past it | Met | Demand 131072 B > every C (B2c); 512 MiB > 64/128/256 MiB (B3c); 1g above demand as control. |
| B. Logic | each step says what it establishes | Met | B2h/B3h: heartbeats off so the NN `cacheUsed` is exactly the knob; ablation isolates 534 from 745; long cache-report interval separates 534 from the `numCached >= neededCached` cleanup. |
| B. Logic | prediction in numbers before the run | Met | B2f P1 = 4096·max(0, ⌊(C−U)/4096⌋) per row, A3 drop-id counts; B3f per-M bytes/blocks/kB; A7 phase-2 counts. |
| B. Logic | every plausible outcome has a row | Partly → Met | A4/A8 (first attempt) added rows. This review: the A4 row "Test A `NumBlocksFailedToCache` > 0 with CacheUsed ≤ C → reserve caught a plan" reads a counter that also counts duplicate cache commands (`FsDatasetCache.java:276-282`), so it could misread normal resends as a refusal → **replaced** (A11) by rows on the DataNode's "could not reserve" lines; B3g had no row for refusals → **added** (A11). |
| B. Logic | confirmation needs ceiling-follows-knob and direct disallow evidence | Met | The line-534 DEBUG message is the disallow evidence at both tiers (A3, B3d); the rows reading its *absence* needed a check that DEBUG is in effect → **added** (A12: "Scanned" DEBUG line per rescan as known answer). |
| B. Logic | alternative explanations and their controls | Met | Another path removing pending (ablation; `numCached >= neededCached` cleanup needs a cache report, held off in Test B by no caching and in phase 2 by the 60-s interval); a DN report overwriting the knob (heartbeats off); page rounding (page-aligned blocks); workload bound (M = 1g); DN reserve backstop (A11 lines). |
| C. Specific | a human can follow it from the intro and §9a | Met | Estimate, A3 steps 1–5, B1. |
| C. Specific | an AI can run §9b–§9e without re-deriving the code path | Partly → Met | A1, A2, A5 (first attempt) made B2a/B3a node-specific for `pc99`; the node and run-folder name change → **amended** (A9). |
| C. Specific | knob, values, workload, commands, observables, sampling, stop conditions exact | Partly → Met | A6/A7 (first attempt) fixed the plateau and the phase-2 window. This review: the unit settle rule "unchanged for 3 s" can settle at 0 blocks before the first rescan + heartbeat delivers `DNA_CACHE` → **amended** (A10: ≥ 10 s and 3 s unchanged, max 30 s). The harness also compared UTC daemon-log stamps with MST sample times (node `/etc/timezone` = UTC, `/etc/localtime` = MST), which would have mis-split phase 2 at the cache report → sampler fixed, noted in A9. |
| D. Runnable | harness and environment prerequisites exist or are listed | Met (after step 1) | `pc72` lacked `cmake`/`zlib1g-dev`/`libssl-dev`/`pkg-config` (installed, A5/A9); native `libhadoop` built in the case copy; `ulimit -l` 16492912 kB, so no `prlimit`. The first attempt's harness wrote to `/mydata/jingsong-s4/<stem>-run1` (with `--autonomous`); changed to the instructed run folder. |
| D. Runnable | workload arithmetic reaches the limit | Met | 512 MiB file, ≤ 512 MiB locked vs 16 GB memlock and 125 GiB RAM, < 2 GiB disk on `/mydata` (706 GB free), ≈ 12 min cluster, ≈ 5 min unit. `-addPool` once (A6). |
| D. Runnable | load-bearing citations spot-checked against the pinned source | Met | `CacheReplicationMonitor.java:205` ("Scanned" DEBUG), `:305-309` (rescan; the resend reset is at 309, the case's A3 step 4 says 308), `:515-543` (loop; `if` at 534, DEBUG 535-537, `it.remove()` 538, decrement 540), `:745` (pendingCapacity check); `FsDatasetCache.java:276-282` (duplicate counted as failure), `:415-422` (reserve, WARN at 419); `BPServiceActor.java:490-498` (cache report, skipped at capacity 0), `:700` (heartbeat gate; IBRs at 741-745 and cache reports at 759-762 are not gated, so Test B's file write completes with heartbeats off); `BPOfferService.java:749-752` (DNA_CACHE INFO line); `DatanodeInfo.java:297-304` (setters); `GenericTestUtils.java:144-150, 474-513` (`setLogLevel`, `LogCapturer`). |

**Recommendations**

| # | Recommendation | Applied? | Why |
|---|---|---|---|
| R1–R8 | First attempt's A1–A8 (node paths, one cluster per K2 value, DEBUG-line evidence, rows, base distribution + native lib, pool once and plateau rule, phase-2 window, cluster rows) | Kept 2026-11-25 (reviewed; A1/A2/A5 re-pointed by A9) | each holds against the source |
| R9 (A9) | Node `pc72`, instructed run-folder name, log time zone | Applied 2026-11-25 | runnable as written on `pc72` |
| R10 (A10) | Unit settle rule ≥ 10 s and 3 s unchanged | Applied 2026-11-25 | 3-s rule can settle before caching starts |
| R11 (A11) | Read reserve refusals from the DataNode's WARN lines, not `NumBlocksFailedToCache`; predict 0; replace the A4 failures row; add a B3g row | Applied 2026-11-25 | the counter also counts duplicate commands |
| R12 (A12) | Count the CRM "Scanned" DEBUG line per window/phase as a known answer for the DEBUG-based rows | Applied 2026-11-25 | case-notes method lesson 5 (a DEBUG level that silently did not apply) |
| R13 | Stage 3: A3 step 4 cites `CacheReplicationMonitor.java:308` for the resend reset; it is at 309 | Left for stage 3 | wrong by one line, no effect on the design |

## 2. Environment

| Field | Run 1 |
|---|---|
| Date | 2026-11-25 (node clock MST) |
| Node | `pc72` = `node2.jason92-326665.misconfiguration-pg0.cloudlab.umass.edu` (in `environment.md`'s Node table), 40 cores, 125 GiB; node lock `/mydata/s4/NODE-LOCK` taken 09:59:17 MST (free at the first try) |
| OS, kernel, limits | Ubuntu 22.04.2 LTS, `5.15.0-203-generic`; `ulimit -l` 16492912 kB |
| JDK | OpenJDK 1.8.0 (`/usr/lib/jvm/java-8-openjdk-amd64`) for build, tests and daemons (default `java` is 11, not used) |
| Build tool | Maven 3.6.3; node `~/.m2` 3.4.2 artifacts from the base build; CMake 3.22.1, `zlib1g-dev`, `libssl-dev`, `pkg-config` installed with apt 10:03 MST (`logs/cluster/apt.log` on the node) |
| Local source copy | `<run>/src` by `copy-source.sh` from `systems/hadoop/source/` (repository HEAD `8bd1dfb31`, source clean), tag `rel/release-3.4.2`; only `TestCrmPendingFit.java` added |
| Run folder | `/mydata/jingsong-s4/dfs.datanode.max.locked.memory-rescanCachedBlockMap-remaining-run1/` (`<run>` below) |
| Unit run | compile 10:05–10:06, test 10:09:37–10:12:34 (surefire 12 run, 0 failures, 0 errors, 134 s), ablation copy `<run>/src-ablate` 10:12–10:13:57 (1 run, 0/0) MST |
| Cluster distribution | copy of `/mydata/jingsong-s4/hadoop-base/hadoop-dist/target/hadoop-3.4.2` (built 2026-11-24 from the same source) + `libhadoop.so.1.0.0` from the case copy; NN and DN `-Xmx1g`; configs `<run>/cluster/conf/` (kept) |
| Cluster run | `run` 10:14:28–10:25:03 MST (format, phase 1 five values, phase 2); `phase2b` 10:27:10–10:30:21 MST (phase 2 re-run, §3) |
| Case-file / harness version | sha256 `eb8f21a0…` (frozen) / md5s in §1; `cluster-run.sh` gained the `phase2b` mode after run 1's phase 2 (md5 `2c149d72`; the file as used for `run` is `run1/cluster-run.sh.as-run-1`, md5 `405b87a0`) |
| Storage | MiniDFSCluster data under `<run>/src*/…/target/test/data`; cluster `<run>/cluster/{nn,dn,tmp,f512}` (≈ 2.1 GB with the distribution copy); nothing on `/proj` |
| Clocks | node shell MST; daemon and test logs UTC (JVM reads `/etc/timezone`); session node EST. Log times below are UTC as printed |
| Full logs | on `pc72`: `<run>/logs/{unit,cluster}/` and `<run>/cluster/logs/` (NN/DN logs), 6.9 MB in all; copies of the cited evidence in `run1/` |

## 3. Runbook defects

| # | Run | Step | Problem | Fix | Decision (date) | Case-file change |
|---|---|---|---|---|---|---|
| D1 | run 1, cluster | B3e step 3 with A7 (phase-2 timing) | A7 says the directive is added 8 s after the first cache report that follows the restart. The harness began polling `CacheReportsNumOps` only after `safemode wait`; by then the DataNode's first report (sent at registration) had been counted, so the poll saw 1 at once and waited 8 s after a report ≈ 30 s old. The window from the directive (landed 17:23:16.218, `run1/cluster/nn-directive-ops.txt`) to the next report (between sample t = 21.4 and 22.4 s after t0 = 17:23:14.332, `samples-P2-M128m.csv`) was 19.5–20.5 s, which cannot be placed on either side of A8's 20-s threshold. | Harness only: new mode `phase2b` waits for the counter to **change** after the poll starts, then 8 s (window ≈ 50 s, as A7 intends). Phase 2 re-run once, as A8's row "window < 20 s → re-run it once" provides; same data, same values. No change to §9a or the design text. | 2026-11-25, before reading phase 2's verdict rows (the readings of the first phase 2 are reported below, not discarded) | none (the case's A7 text was right; the harness did not follow it) |

## 4. Run 1

**Scope:** both tiers, every row of B2f (Tests A, B ×9, C, ablation) and B3f (phase 1 at five M values, phase 2 twice). **Command logs:**
`run1/unit/unit-run.log`, `run1/cluster/cluster-run.log` (includes `phase2b`), `run1/cluster/phase2b.out`.
Raw data: `run1/unit/ifchk.csv` and `run1/unit/ablate/ifchk.csv` (the `IFCHK` lines of the surefire output), `run1/unit/unmutated-drop-lines.txt`
(every line-534 DEBUG line of the unmutated run with the `IFCHK` lines between them), `run1/cluster/samples-<phase>.csv` (1-s samples) and the
`CLCHK` lines in `cluster-run.log` / `phase2b.out`; log excerpts `run1/cluster/{nn-cannot-fit-all,p2-nn-cannot-fit,p2b-nn-cannot-fit}.txt`,
`{dn-dna-cache-all,p2-dn-dna-cache,p2b-dn-dna-cache}.txt`, `dn-maxlocked-excerpt.txt`, `dn-reserve-fail-excerpt.txt` (empty),
`{nn-directive-ops,p2b-nn-directive-ops}.txt`. Script check: `run1/selfcheck.out` (175 PASS, 0 FAIL) and `run1/selfcheck-p2b.out` (11 PASS).

### 4.1 Readings

**Unit tier — Test B (line 534 driven directly; C = 65536, heartbeats off, DN cached nothing in every instance)**

| Knob | P0 bytes/blocks (pred.) | NN remaining after | P1 = P2 bytes/blocks (pred.) | drop lines / distinct ids: pre, w1, w2 (pred. 0, 16 − P1/4096, 0) | "Scanned" lines pre/w1/w2 |
|---|---|---|---|---|---|
| U = 0 | 65536/16 (65536/16) | 65536 | 65536/16 (65536/16) | 0, 0/0, 0 | 3/3/3 |
| U = 16384 | 65536/16 | 49152 | 49152/12 (49152/12) | 0, 4/4, 0 | 3/3/3 |
| U = 32768 | 65536/16 | 32768 | 32768/8 (32768/8) | 0, 8/8, 0 | 3/3/3 |
| U = 49152 | 65536/16 | 16384 | 16384/4 (16384/4) | 0, 12/12, 0 | 3/3/3 |
| U = 65536 | 65536/16 | 0 | 0/0 (0/0) | 0, 16/16, 0 | 3/3/3 |
| U = 81920 | 65536/16 | −16384 | 0/0 (0/0) | 0, 16/16, 0 | 3/3/3 |
| C' = 65536 | 65536/16 | 65536 | 65536/16 (65536/16) | 0, 0/0, 0 | 3/3/3 |
| C' = 32768 | 65536/16 | 32768 | 32768/8 (32768/8) | 0, 8/8, 0 | 3/3/3 |
| C' = 0 | 65536/16 | 0 | 0/0 (0/0) | 0, 16/16, 0 | 3/3/3 |
| **ablation** U = 49152 (line 534 disabled) | 65536/16 | 16384 | **65536/16** (65536/16) | 0, **0/0**, 0 | 4/3/3 |

The drop lines print the `remaining` they compared against: 0 in every row except U = 81920 (−16384) (`run1/unit/unmutated-drop-lines.txt`).
Ablation diff: `run1/unit/ablate.diff` (one line, 534).

**Unit tier — Test A (DataNode caching follows C) and Test C (hand-back)**

| Row | settled / t | DN CacheUsed (pred.) | blocks (pred.) | max CacheUsed | bytesCached | NN pending | `NumBlocksFailedToCache` | "could not reserve" (pred. 0) | drop lines | "Scanned" |
|---|---|---|---|---|---|---|---|---|---|---|
| A, C = 16384 | yes / 10.0 s | 16384 (16384) | 4 (4) | 16384 | 16384 | 0 | 4 | 0 | 4 | 12 |
| A, C = 32768 | yes / 10.0 s | 32768 (32768) | 8 (8) | 32768 | 32768 | 0 | 8 | 0 | 0 | 10 |
| A, C = 65536 | yes / 10.0 s | 65536 (65536) | 16 (16) | 65536 | 65536 | 0 | 16 | 0 | 16 | 10 |
| C (U = 49152 instance) | yes / 10.0 s | 65536 (65536) | 16 | 65536 | 65536 | 0 | 16 | 0 | 0 | 10 |
| C in the ablation copy (no prediction) | yes / 10.0 s | 65536 | 16 | 65536 | 65536 | 0 | 16 | 0 | 0 | 10 |

`IFCHK,instr` in every instance: `NoMlockCacheManipulator`, page size 4096, DN cache capacity = C. Surefire: 12 run / 0 failures / 0 errors,
ablation 1 / 0 / 0 (`run1/unit/surefire-summary.txt`, `run1/unit/ablate/surefire-summary.txt`). In the whole unmutated surefire output:
100 line-534 lines (= 4 + 0 + 16 in Test A + 80 in Test B), 0 "could not reserve" lines, 135 "Scanned" lines.

**Cluster tier — phase 1** (16-MiB blocks, `/cap/f512` = 32 blocks, cache reports every 10 s; every value settled under A6 at 60.4–60.9 s;
`VmLck` baseline 0 kB before every value and back to 0 after every directive removal)

| M | DN start line | CacheUsed final = max (pred.) | NumBlocksCached (pred.) | BYTES_CACHED (pred.) | VmLck − baseline final = max, kB (pred.) | NN Cache Remaining | "could not reserve" | line-534 lines / ids | DNA_CACHE lines (ids each) | `NumBlocksFailedToCache` |
|---|---|---|---|---|---|---|---|---|---|---|
| 0 | `maxLockedMemory = 0` | 0 (0) | 0 (0) | 0 (0) | 0 (≈ 0) | 0 | 0 | 0 / 0 | 0 | 0 |
| 64m | `= 67108864` | 67108864 (67108864) | 4 (4) | 67108864 | 65536 (≈ 65536) | 0 | 0 | 4 / 4 | 2 (4, 4) | 4 |
| 128m | `= 134217728` | 134217728 (134217728) | 8 (8) | 134217728 | 131072 (≈ 131072) | 0 | 0 | 8 / 8 | 2 (8, 8) | 8 |
| 256m | `= 268435456` | 268435456 (268435456) | 16 (16) | 268435456 | 262144 (≈ 262144) | 0 | 0 | 16 / 16 | 2 (16, 16) | 16 |
| 1g (control, above demand) | `= 1073741824` | 536870912 (536870912) | 32 (32) | 536870912 | 524288 (≈ 524288) | 536870912 | 0 | 0 / 0 | 4 (32 each) | 96 |

NN-side Configured Cache Capacity = M and NN Cache Used = DN CacheUsed in every final sample. Every line-534 line in phase 1 reads
"remaining cache size 0" and falls in one rescan per value (17:16:28 ×4, 17:18:00 ×8, 17:19:32 ×16; `run1/cluster/nn-cannot-fit-all.txt`).

**Cluster tier — phase 2** (M = 128m, cache reports every 60 s, both daemons restarted)

| Run | directive landed (NN log, UTC) | next cache report | window | line-534 lines / ids, time after directive | DNA_CACHE lines in window (ids) | DNA_CACHE after the drop | final CacheUsed / VmLck | "could not reserve" | "Scanned" lines |
|---|---|---|---|---|---|---|---|---|---|
| first (`run`, §3 D1) | 17:23:16.218 | 17:23:35.7–36.7 | 19.5–20.5 s | 8 / 8 at 17:23:19.204 (+3.0 s), remaining 0 | 2 at +1.35 s, +2.34 s (the same 8 ids) | 0 | 134217728 / 131072 kB | 0 | 92 |
| **re-run (`phase2b`, decisive)** | 17:28:34.895 | t0 + 51.5–52.5 s = 17:29:24.5–25.5 | 49.6–50.6 s | 8 / 8 at 17:28:37.741 (+2.8 s), remaining 0 | 2 at +1.30 s, +2.30 s (ids 1073741825–1073741832 both times) | 0 (none in the ≈ 48 s to the cache report, none to the end of the 90 s) | 134217728 / 131072 kB | 0 | 92 |

Phase-2 cache reports: `CacheReportsNumOps` 2 → 3 at t = 52.5 s (re-run; t0 = 17:28:32.999 UTC, `samples-P2b-M128m.csv`). The 8 dropped ids are
exactly the 8 commanded ids (`p2b-nn-cannot-fit.txt`, `p2b-dn-dna-cache.txt`). Instrument note: the JMX `FSDatasetState` values lag the real
state by up to 10 s (phase 2: `VmLck` 131072 kB at t = 3.4 s while JMX CacheUsed stayed 0 until t = 10.4 s); the plateau values are unaffected.

| Disallow-branch line (example) | `2026-11-25 17:28:37,741 DEBUG …CacheReplicationMonitor: Block 1073741825: removing from PENDING_CACHED for node 260e9537-… because it cannot fit in remaining cache size 0.` | `run1/cluster/p2b-nn-cannot-fit.txt` |
|---|---|---|

### 4.2 Conclusion and logic

1. **Validity** — valid. Unit: every instance ran with the NoMlock manipulator, page size 4096 and DN capacity = C [observed: `IFCHK,instr`
   lines, `run1/unit/ifchk.csv`]; DEBUG capture in effect in every window (3–12 "Scanned" lines) [observed: same]; heartbeats off held the knob
   (NN `nnUsed` = U, `nnCap` = C' after the change; DN cached nothing in Test B) [observed]; Test A/C settled under A10 [observed: `settled=true`];
   surefire 12/0/0 and 1/0/0 [observed: `surefire-summary.txt`]; the ablation ran on a copy whose line 534 reads `if (false && …)` [observed:
   `ablate.diff`]. Cluster: `hadoop: true` [observed: `cluster-run.log` setup block]; each DataNode started with `maxLockedMemory = M` and the NN
   showed Configured Cache Capacity = M before each directive [observed: `dn-maxlocked-excerpt.txt`, `cluster-run.log`]; every phase-1 value
   settled; NN DEBUG in effect (`nnScanLines` 61–92) [observed: `CLCHK` lines]; demand (512 MiB) exceeded every capped M [observed:
   BYTES_NEEDED 536870912]; phase-2 re-run window ≈ 50 s ≥ 20 s [observed: `p2b-nn-directive-ops.txt`, `samples-P2b-M128m.csv`].
2. **Readings** — every predicted number matched exactly (§4.1). Readings without a prediction: `NumBlocksFailedToCache` 4/8/16/16 (unit) and
   4/8/16/96 (cluster) with 0 refusal lines — the A11 duplicate-command row; line-534 lines in Test A at C = 16384 and 65536 but not at 32768
   (timing of the heartbeat that reports the new CacheUsed against the 1-s cache report; no row depends on it); the first phase-2 window of
   19.5–20.5 s (§3 D1).
3. **Matched rows** — Unit: B2g "Test B P1 equals the table (Σpending ≤ headroom) and P2 = P1 → line 534 enforces the reported headroom; claim (1)
   holds", with A4's confirmation conditions (w1 distinct ids = 16 − P1/4096, each once; pre and w2 = 0) [observed: Test B table]; B2g "Ablation P1 =
   65536 while unpatched P1 = 16384 → the difference is due to line 534 alone" [observed]; B2g "Test A `getCacheUsed()` = C for all C, blocks =
   C/4096 → DataNode caching follows the key; claim (2) holds at the accounting level" [observed]; A11 "`NumBlocksFailedToCache` > 0 with 0
   'could not reserve' lines → duplicate cache commands; no bearing" [observed]. A4: "A unit-tier confirmation needs Test B as in the table and
   the w1 ids and Test A as predicted" — all three hold. Cluster: B3g "CacheUsed and VmLck rise to M and stop, for each capped M, and to
   512 MiB for M = 1g → locked memory follows the key; claim (2) holds" [observed: phase-1 table]; B3g "Phase 2: 'cannot fit' lines appear and
   DNA_CACHE stops after 1–3 commands → line 534 drops pending blocks once headroom is used; claim (1) holds" (re-run: 8 lines, 2 commands, then
   none for ≈ 48 s) [observed: `p2b-*.txt`]. A8's cluster-confirmation condition (phase 1 and phase 2's lines with the DNA_CACHE pattern) holds.
4. **Excluded rows** — *P1 = P0 after U raised* (refuted): P1 < P0 in every U ≥ 16384 and C' ≤ 32768 row [observed]. *P1 below the table by more
   than a block*: equal in all 9 [observed]. *Setup invalid* (P0 ≠ 65536; U = 0/C' = 65536 rows ≠ 65536): no [observed]. *P1 right but no w1
   lines*: w1 lines present with the predicted ids [observed]. *Ids ≠ 16 − P1/4096*: equal [observed]. *P2 ≠ P1 or w2 > 0*: no [observed].
   *Ablation P1 = 16384 too*: 65536 [observed]. *Test A CacheUsed > C*: max = C [observed]. *Test A under-fills*: no. *Test A not settled*: settled.
   *Reserve caught a plan* (A11, unit and cluster): 0 refusal lines everywhere [observed: `ifchk.csv`, `dn-reserve-fail-excerpt.txt` empty,
   `dnCouldNotReserveLines=0`]. *Test C ≠ 65536*: 65536. *DEBUG not in effect* (A12): ≥ 3 "Scanned" lines in every window, 61–92 per phase.
   Cluster: *VmLck or CacheUsed above M* — max equals M (or M/1024 kB) at most [observed: `samples-*.csv`]; *same values for all M* — 0/64/128/256/512
   MiB; *M = 1g ≤ 256 MiB* — 512 MiB; *counter capped, VmLck not* / *CacheUsed = M, VmLck low* — VmLck = CacheUsed/1024 exactly; *M = 0 caches* —
   nothing; *value not settled* — all settled; *phase 2 no 'cannot fit', DNA_CACHE every second* — 8 lines, 2 commands; *more than 8 distinct ids*
   — 8; *window < 20 s* — re-run 49.6–50.6 s (first run borderline, §3); *mixed (lines but > 3 commands)* — 2 commands.
5. **Observed vs. inferred** — (a) The phase-2 stop of `DNA_CACHE` is caused by line 534 [inferred from: the 8 drop lines name exactly the 8
   commanded ids and fall 0.55 s after the second command; no further command in the ≈ 48 s before the cache report, while at M = 1g (no drop, cap not
   binding) the NameNode re-sent all 32 pending ids every second (4 commands at t = 2.3, 3.3, 4.3, 5.3 s; cache report at ≈ 4.4 s; `CLCHK,M1g`); and the unit
   ablation shows nothing else removes pending entries before a cache report]. (b) Non-zero `NumBlocksFailedToCache` counts are duplicates [inferred
   from: `FsDatasetCache.java:276-282`; every count equals ids sent − distinct ids (e.g. 1g: 4 × 32 − 32 = 96, `dn-dna-cache-all.txt`) and no refusal
   WARN exists]. (c) `VmLck` is the cache's mlocked memory [inferred from: 0 kB baseline, = CacheUsed/1024 at every plateau, back to 0 on uncache].
6. **Deviations and gaps** — (i) Phase 2 re-run under A8 because the harness did not follow A7's timing (§3 D1); both phase-2 runs gave the same
   readings. (ii) The NN pending list itself is not observable at the cluster tier (B3d); inferred from the DNA_CACHE pattern as designed.
   (iii) mlock stubbed at the unit tier (B2d); real locked memory only at the cluster tier. (iv) JMX `FSDatasetState` lags up to 10 s; only plateau
   values and `VmLck` (read directly) are used. (v) Test A line-534 counts vary by row (4/0/16) — not predicted, not used. (vi) Unit Test A has no
   C = 0 row; the default 0 is covered at the cluster tier.
7. **Core question** — Usage follows the constraint. The DataNode's real mlocked memory was 0, 65536, 131072, 262144 kB at M = 0, 64, 128, 256 MiB
   with 512 MiB demanded, never above M, and 524288 kB (all demand) when M = 1 GiB did not bind; unit cache accounting showed the same C/4096 staircase.
   The check at line 534 is the NameNode half of that cap: in the unit tier the pending bytes it keeps equal `4096·⌊(C−U)/4096⌋` for every headroom
   (and stay at 65536 when the check is disabled), and in a real cluster it removes the commanded blocks as soon as the heartbeat shows the headroom
   spent, which stops the re-sending of cache commands. So `dfs.datanode.max.locked.memory` caps the DataNode's mlocked cache memory, and line 534
   keeps the NameNode's plan within it.

**Conclusion (one line):** Unit: B2g row 1 (+ A4 conditions), the ablation row and the Test A row — confirmed. Cluster: B3g row 1 and the phase-2
"cannot fit + DNA_CACHE stops" row (re-run under A8) — confirmed.

## 5. Self-check of run 1 — AI

Re-read the raw files, not the tables: the 25 `IFCHK` lines of `run1/unit/ifchk.csv` and the 3 of `run1/unit/ablate/ifchk.csv`; 100 drop lines
in `unmutated-drop-lines.txt` (counted with `grep -c` on the full surefire output on the node: 100 drop, 0 "could not reserve", 135 "Scanned";
ablation output 0 drop lines); the six `CLCHK` lines in `cluster-run.log` and the one in `phase2b.out`; each `samples-*.csv` recomputed with `awk`
(max `VmLck` 0/65536/131072/262144/524288/131072/131072 kB, max CacheUsed 0/64/128/256/512/128/128 MiB, `CacheReportsNumOps` steps 2→3 at t = 52.5 s
in the re-run); the timestamps of the directive (`p2b-nn-directive-ops.txt`), the two DNA_CACHE lines and the 8 drop lines; the ids in both.

### 5.1 Check of run 1's conclusion

| Part | Holds? | Note (file re-read) |
|---|---|---|
| 1. Validity | yes | `IFCHK,instr` ×13 with page 4096, capacity = C; `Tests run: 12, Failures: 0, Errors: 0` and `1, 0, 0`; `hadoop:  true`; six "Starting DataNode with maxLockedMemory" lines = 0, 64m, 128m, 256m, 1g, 128m (`dn-maxlocked-excerpt.txt`); every phase "CacheUsed=0 … VmLck=0 kB (baseline 0)" after removal |
| 2. Readings | yes | all values in §4.1 re-read from the raw lines; `selfcheck.py` agrees (175 + 11 PASS, 0 FAIL) |
| 3. Matched rows | yes | Test B P1 table and drop ids, ablation 65536/0 lines, Test A staircase, phase-1 staircase, phase-2 8 lines + 2 commands — each read from the raw file |
| 4. Excluded rows | yes | every refuted/not-confirmed row has a contradicting raw reading (part 4) |
| 5. Observed vs. inferred | yes | (a) drop ids = commanded ids, drop 0.55 s after the second command, no command afterwards; M = 1g re-sent every second (`dn-dna-cache-all.txt` 17:21 lines); (b) ids sent − distinct = failed in all 4 cluster values and Test A; (c) `VmLck`×1024 = CacheUsed at every plateau |
| 6. Deviations and gaps | yes | §3 D1 timing re-derived from `nn-directive-ops.txt` and `samples-P2-M128m.csv`; the first phase 2 is not used for the verdict but agrees with the re-run |
| 7. Core question | yes | M = 0 and M = 1g bracket the capped values; the ablation and the phase-2 contrast with M = 1g isolate line 534 from line 745 and the cache-report cleanup |

### 5.2 Run 2?

**No** — decided 2026-11-25. The result confirms the estimate (no refutation, no bypass); the inferred statements are backed by direct log
evidence and by the unit ablation; the one deviation (phase-2 timing) was handled by the design's own re-run row and both phase-2 runs agree.

## 6. Run 2 — fresh AI session (optional)

Not done (§5.2).

## 8. Verdict — AI

Jingsong may overrule any verdict at any time; record an override here with its date and reason.

**Stage-3 estimate:** positive. **Outcome class:** **true positive** — estimate `positive`, effect `caps` at the unit and the cluster tier.

**Claim tested:** (B1) (1) After a rescan, the bytes a NameNode keeps pending-cached for a DataNode never exceed that DataNode's reported headroom
`cacheCapacity − cacheUsed`, where `cacheCapacity` is `dfs.datanode.max.locked.memory`; blocks that do not fit are dropped from pending at line 534.
(2) As a result, and enforced again on the DataNode, the bytes the DataNode locks for caching stay ≤ `dfs.datanode.max.locked.memory`, and track it
as the key is varied while the workload exceeds it. "Confirmed" below always means this claim held.

| Tier | Verdict (B2g / B3g row) | Effect on the constraint | Basis | Date |
|---|---|---|---|---|
| Unit | **Confirmed** — B2g row 1 with A4's conditions (P1 = 4096·⌊(C−U)/4096⌋ in all 9 instances, drop ids 0/4/8/12/16/16 and 0/8/16 each once, none before or after), ablation row (line 534 off: P1 = 65536, 0 drops), Test A row (CacheUsed = C, blocks 4/8/16, 0 refusals) | caps | run 1 + self-check | 2026-11-25 |
| Cluster | **Confirmed** — B3g row 1 (VmLck 0/65536/131072/262144 kB = CacheUsed/1024 at M = 0/64m/128m/256m, 524288 kB at 1g, never above M, 0 refusals) and the phase-2 row (re-run under A8: 8 "cannot fit … 0" lines for the 8 commanded ids 2.8 s after the directive, 2 DNA_CACHE, then none for ≈ 48 s) | caps | run 1 + self-check | 2026-11-25 |

**Positive control:** (positive-estimate file; controls anyway) M = 1g cached the whole 512 MiB file (524288 kB locked), and M = 0 cached nothing;
the unit ablation kept 65536 bytes pending where the check kept 16384.

**Feedback filed:** audit amendments A9–A12 (2026-11-25, before any reading, section D1b, inline markers in B2a, B2d–B2g, B3a, B3d, B3f, B3g) and
section D2 "Stage-4 result" in `~/writeup-hadoop/out/o22/case-amended.md` (whole file now sha256 `0c5e62ac…8829`; sections up to D1b unchanged since the
freeze, `eb8f21a0…`). Recommendations for stage 3 (not applied): R13 (§1), and predict reserve-refusal lines rather than `NumBlocksFailedToCache`.
Nothing in the repository was edited (`_INDEX.md`, `queue.csv`, HANDOFF, `environment.md` are left to the parent session).

**Findings beyond the verdict.** No bug or bypass. Observations: (1) at a binding cap the NameNode re-sends a cache command for still-pending blocks
after every rescan, and the DataNode counts each repeat as a "failed to cache" block (`NumBlocksFailedToCache` 96 for 32 blocks at M = 1g) — the
metric overstates failures; line 534 is what cuts these resends short once the heartbeat shows the headroom spent. (2) After a directive is removed,
the DataNode logged `DNA_UNCACHE` about once per second until uncached (`dn-dna-cache-all.txt`), the mirror of (1). (3) JMX `FSDatasetState` lags
`/proc` `VmLck` by up to 10 s. No memory holder worth an OOM look: locked memory never exceeded M.

**Left on the node (`pc72`):** `/mydata/jingsong-s4/dfs.datanode.max.locked.memory-rescanCachedBlockMap-remaining-run1/` (6.9 MB: `harness/`,
`logs/unit/` with surefire output, `logs/cluster/` with samples and run logs, `cluster/logs/` NN + DN daemon logs, `cluster/conf/`). Deleted: the
source copy and ablation copy (with MiniDFSCluster data), the distribution copy, NN/DN data, `tmp`, the 512-MiB input file. apt packages
`cmake`, `zlib1g-dev`, `libssl-dev`, `pkg-config` stay installed on `pc72` (`environment.md` lists them only for `pc75`, `pc91`, `pc82`).
No NameNode, DataNode, sampler, Maven or test JVM left (checked with `ps -u jason92 … | awk` at 10:30 MST), ports 9000/9870/9864/9866/9867 free,
driver PID file removed, node lock released 10:31 MST. Undo: `rm -rf` of that folder.
