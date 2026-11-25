# DUMP_WRITE_WATER_MARK-run-DUMP_WRITE_WATER_MARK-2--autonomous — stage-4 results  <!-- file: results/DUMP_WRITE_WATER_MARK-run-DUMP_WRITE_WATER_MARK-2--autonomous.md -->

> **Case:** [`DUMP_WRITE_WATER_MARK-run-DUMP_WRITE_WATER_MARK-2--autonomous`](../../../stage3-ai-deep-read/jingsong/cases/DUMP_WRITE_WATER_MARK-run-DUMP_WRITE_WATER_MARK-2--autonomous.md) (queue order 17; check `OpenFileCtx.java:383`, `Dumper.run`)
>
> **Status:** verdict filed (run 1 + self-check; no run 2) — 2026-11-25
>
> **Outcome class:** **true positive** — estimate `positive`, effect `caps` in both tiers (the dump-file-failure path hangs the writer, as the estimate says; recorded, not a growth bypass).
>
> **Agent:** autonomous. "§9a" below means B2f/B2g (unit) and B3f/B3g (cluster); "§9b–§9e" means B2a–B2e / B3a–B3e; the feedback section is D.

Drafted outside the repository (`~/writeup-hadoop/out/o17/`); paths below marked `run1/…` are relative to that folder.
Harness: `~/writeup-hadoop/out/o17/harness/` (staged for `harness/DUMP_WRITE_WATER_MARK-run-DUMP_WRITE_WATER_MARK-2--autonomous/`; not committed, no commit asked for).
Amended case file: `~/writeup-hadoop/out/o17/case-amended.md`. The repository was not edited.

## 1. Before run 1 — design audit and freeze

| Field | Content |
|---|---|
| **Case-file version** | Repository file at commit `bef6bc8a` (sha256 `4046f0dc…c76851`, as in `_INDEX.md` §4). After the audit's two dated amendments (2026-11-25, before any reading): sha256 **`61484582363480c81a4d7ef9716f518cf1f7daa6be1c0da7484283ac6a56b0ca`**. After the run-1 runbook-defect amendment D1 (cluster tier restarted from P1): sha256 **`c01a4e5e07bbce869a1aae58a6266f5ffa0aa537b24cf3abdd790b4ba9c0fed3`** (`run1/frozen-sha256.txt`). Section D feedback was added after the verdict and is not part of a frozen version. |
| **Harness** | `TestDumpWaterMark.java`, `log4j.properties` (test resource), `unit-run.sh`, `check-unit.py`, `cluster-run.sh`, `ooo.py` |
| **Instrument checks** | Test compiled offline before run 1 (`--compile-only`, BUILD SUCCESS, `run1/unit/unit-run.log`); line 73/379/383 text asserted by `unit-run.sh` before copying the test; constant in each gateway jar checked with `javap` (1048576 / 4194304 / 1073741824, `run1/cluster/javap-*.txt`, and per point `P*/jar-const.txt`); `ooo.py`/`cluster-run.sh` syntax-checked |
| **Tiers and values** | Unit: mark 256 KiB / 1 MiB (default) / 4 MiB at w = 64 KiB; 1 MiB at w = 1 MiB and 96 KiB; dump disabled (positive control); dump path broken. Cluster: stock 1 MiB (wsize 1 MiB, G 64 MiB and 512 KiB; wsize 64 KiB, G 64 MiB), patched 4 MiB, patched 1 GiB (positive control) |
| **Audit bottom line** | **Ready after amendments** — 2026-11-25 |

### 1.1 Design audit

| Group | Check | Rating | Note (section checked) |
|---|---|---|---|
| A | constrained quantity is memory or disk bytes | Met | A2/B1: gateway heap bytes of out-of-order WRITE payloads per open file (`nonSequentialWriteInMemory`) |
| A | knob varied, ≥ 3 values incl. default | Met | B2b 256 KiB / 1 MiB / 4 MiB by reflection; B3b 1 MiB / 4 MiB / 1 GiB by rebuilt jar. A hard-coded constant (A1), so reflection/jar patch is the stated way |
| A | real resource measured, not only the counter | Met | B2d `inHeap()` (referenced payload) and dump-file length; B3d live `[B` histogram after forced GC, dump-file size |
| A | usage driven to the limit and past it | Met | B2c G = 16 MiB (4–64× mark); B3c G = 64 MiB (16–64× mark) |
| B | "how this verifies" mapped (B1 → B2/B3 → B2f/B3f → B2g/B3g) | Met | rows for leak, flat/not-triggered, threshold-not-moving, control failed, hang, bypass |
| B | prediction in numbers | Met | B2f/B3f exact maxima and dump sizes |
| B | confirmation needs ceiling-follows-knob and disallow evidence | Met | DEBUG `Before dump == M` / `After dump == 0` and dump file per mark |
| B | controls named | Met | disabled-dump (unit) and 1 GiB jar (cluster) positive controls; below-mark point; integrity check |
| C | a human can follow it | Met | B1 + B2f/B3f |
| C | an AI can run it without re-deriving the path | Partly | B2a's `$WORK/hadoop-3.4.2` and `-am install`; module has no test `log4j.properties`; B3a/B3e Hadoop `portmap` + stopping system `rpcbind` conflicts with B4 on a shared node; `start-dfs.sh` needs SSH to localhost |
| C | values, commands, observables exact | Met | |
| D | harness and environment prerequisites | Partly | harness listed as work; environment fixed by amendment |
| D | workload arithmetic | Met | 64 MiB in a 512 MiB gateway heap; ~70 MB disk per point |
| D | load-bearing citations spot-checked | Met | `OpenFileCtx.java:73, 178-179, 211-220, 251, 273-299, 306-373, 376-406 (379, 383-386)`, `checkCommitInternal:840-892` (large-file upload answers a COMMIT with a hole with `COMMIT_SPECIAL_SUCCESS`, so `fsync` with the hole returns) |

| # | Recommendation | Applied? | Why |
|---|---|---|---|
| 1 | B2a/B2d/B2e: `copy-source.sh`, `mvn -o`, create the test `log4j.properties`, log markers through log4j, 30 s per-call wait and a busy sampler | Applied, amendment 2026-11-25 (before B2b) | runbook detail; B2f/B2g unchanged |
| 2 | B3a/B3e/B4: copy built dist, jars built offline in one copy, `hdfs --daemon`, keep system `rpcbind` (gateway as `$USER` registers with it; unregister at teardown), `soft` mount, deterministic data + `cmp` | Applied, amendment 2026-11-25 (before B3b) | runbook would not run as written on a shared node; B3f/B3g unchanged |
| 3 | Stage 3: B3f's Δ`[B` needs a settled baseline (the first post-mount histogram carried ~8.1 MB transient live `[B`) | Partly applied (second baseline added in D1, instrument only); wording left for stage 3 | |

## 2. Environment

| Field | Run 1 |
|---|---|
| Date | 2026-11-25, 04:20–04:40 MST (node clock) |
| Node | `pc82` (`node1.jason92-326665`, CloudLab UMass, 40 cores, 125 GiB RAM); node lock `/mydata/s4/NODE-LOCK` held 04:20–04:40 MST |
| OS / kernel | Ubuntu 22.04.2 LTS / `5.15.0-203-generic` |
| JDK / Maven | OpenJDK `1.8.0_514` (`/usr/lib/jvm/java-8-openjdk-amd64`) / 3.6.3 |
| Local source copy | `copy-source.sh` from `systems/hadoop/source/` at repository commit `cd9e1cde` → `/mydata/jingsong-s4/DUMP_WRITE_WATER_MARK-run-DUMP_WRITE_WATER_MARK-2--autonomous-run1/src` (`rel/release-3.4.2`) |
| Distribution | copy of `/mydata/jingsong-s4/hadoop-base/hadoop-dist/target/hadoop-3.4.2` (node build of 2026-11-24) |
| Storage | `/mydata` local LVM; dump dir, NN/DN data and the mount under the run folder |
| Portmapper | system `rpcbind` (kept running); gateway as `jason92` registered `mountd` 4242 and `nfs` 2049; registrations removed at teardown (`rpcinfo -p` shows only portmapper, `run1/cluster/cluster-run.log`) |
| Full logs | node: `…-run1/logs/` (bulk data deleted; logs kept, 6.7 MB); local copies `run1/` |

## 3. Runbook defects

| # | Run | Step | Problem | Fix | Decision | Commit |
|---|---|---|---|---|---|---|
| 1 | audit | B2a/B2d | no `$WORK` tree; no test `log4j.properties` in the module | `copy-source.sh`, `mvn -o`, create the file | amendment 2026-11-25, before run 1 | not committed |
| 2 | audit | B3a/B3e | `start-dfs.sh` needs SSH to localhost; stopping the node's `rpcbind` conflicts with B4 | `hdfs --daemon`; gateway as `$USER` with system `rpcbind` | amendment 2026-11-25, before run 1 | not committed |
| D1 | run 1 | B3e 3.7 (P1, first attempt) | `hdfs dfs -cat` returned 68 141 056 of 68 157 440 B (prefix identical): the gateway keeps the HDFS stream open and the tail written back after the last COMMIT was not yet visible (`run1/cluster-attempt1/P1/integrity.txt`) | remount and read through the gateway (`cmp mnt/o17-file ref`, which makes the gateway sync), then `hdfs dfs -cat | cmp`; also a second baseline histogram 5 s after the first | dated amendment (B3f/B3g unchanged); cluster tier restarted from setup (reformat) and P1 | not committed |

The first P1 attempt's readings (`run1/cluster-attempt1/P1/`) agree with the restarted P1 (max 1 048 576, 64 rounds, dump 67 108 864) and are not used for the verdict.

## 4. Run 1

**Scope:** both tiers, all values. **Command logs:** `run1/unit/unit-run.log`, `run1/cluster/cluster-run.log` (restarted tier), `run1/cluster-attempt1/cluster-run-attempt1.log`.

### 4.1 Readings

**Unit tier** (`mvn -o test -Dtest=TestDumpWaterMark`: Tests run 7, Failures 0, Errors 0 — `run1/unit/surefire/org.apache.hadoop.hdfs.nfs.nfs3.TestDumpWaterMark.txt`; per-arm summary `run1/unit/check-unit.txt` from `run1/unit/unit-trace.log`)

| Arm (mark, w, N) | max counter (DEBUG `new value`) | max `ctr()` / `inHeap()` after a return | dump file after G | DUMPED | dump rounds (`Before`→`After`) | `Dumper woke up` | B2f |
|---|---|---|---|---|---|---|---|
| 256 KiB, 64 KiB, 256 | 262 144 | 196 608 / 196 608 | 16 777 216 (grew in 64 steps of 262 144) | 256 | 64 (262 144 → 0) | 63 | as predicted |
| 1 MiB, 64 KiB, 256 | 1 048 576 | 983 040 / 983 040 | 16 777 216 (16 steps of 1 048 576) | 256 | 16 (1 048 576 → 0) | 15 | as predicted |
| 4 MiB, 64 KiB, 256 | 4 194 304 | 4 128 768 / 4 128 768 | 16 777 216 (4 steps of 4 194 304) | 256 | 4 (4 194 304 → 0) | 3 | as predicted |
| 1 MiB, 1 MiB, 16 | 1 048 576 | 0 / 0 | 16 777 216 (16 steps) | 16 | 16 | 15 | as predicted |
| 1 MiB, 96 KiB, 171 | 1 081 344 (= 1 056 KiB ≤ 1 146 879) | 983 040 / 983 040; final 589 824 (6 writes since last dump) | 16 220 160 (15 steps of 1 081 344) | 165 | 15 (1 081 344 → 0) | 14 | as predicted |
| disabled (null path), 1 MiB, 64 KiB | 16 777 216 (linear) | 16 777 216 / 16 777 216 | none | 0 | 0; no dumper thread | 0 | as predicted (control moved) |
| broken (`missing/16386`), 1 MiB, 64 KiB | 1 048 576 | writer `WAITING` at `OpenFileCtx.waitForDump(OpenFileCtx.java:296)` after write 16; ctr 1 048 576 | none (`Got failure when creating dump stream` path; `enabledDump=false`) | 0 | 0; dumper thread exists, not alive | 0 | as predicted (hang) |

In every capped arm: `ctr() == inHeap()` after every return (0 mismatches) and `ctr() + dump length == i·w` (0 mismatches); no row had `ctr() ≥ mark`; the busy sampler's peak equals the DEBUG peak; `cleanup()` deleted every dump file; the mark was restored to 1 048 576 after each test (`DUMPWM RESTORED`).

**Cluster tier** (restarted tier; one file per point; Δ`[B` is live `[B` at GAP-SENT + 10 s minus the baseline, after a forced full GC; files under `run1/cluster/P*/`)

| Point | jar mark | wsize | G | max `new value` | dump file at window | dump rounds (`Before`/`After`) | `Dumper woke up` | live `[B`: baseline / baseline2 / window | Δ vs baseline (B3d) / vs baseline2 | `WriteCtx` at window | integrity (NFS read / `hdfs dfs -cat`) |
|---|---|---|---|---|---|---|---|---|---|---|---|
| P1 | 1 MiB | 1 MiB | 64 MiB | 1 048 576 (64 writes of 1 048 576) | 67 108 864 | 64 (1 048 576 / 0) | 63 | 25 255 216 / 17 112 088 / 17 089 240 | −8 165 976 / −22 848 | 64 | identical / identical (68 157 440 B) |
| P2 | 1 MiB | 1 MiB | 512 KiB | 524 288 (1 write) | absent (no `Create dump file`) | 0 | 0 | 25 252 320 / 17 106 720 / 18 129 856 | −7 122 464 / +1 023 136 | 1 | identical / identical (1 572 864 B) |
| P3 | 1 MiB | 64 KiB | 64 MiB | 1 048 576 (1024 writes of 65 536 before the window; 7 more in the fill phase) | 67 108 864 | 64 (1 048 576 / 0) | 63 | 25 258 536 / 17 109 736 / 17 141 024 | −8 117 512 / +31 288 | 1024 | identical / identical |
| P4 | 4 MiB | 1 MiB | 64 MiB | 4 194 304 | 67 108 864 | 16 (4 194 304 / 0) | 15 | 25 260 504 / 17 113 320 / 17 093 792 | −8 166 712 / −19 528 | 64 | identical / identical |
| P5 (control) | 1 GiB | 1 MiB | 64 MiB | 67 108 864 | absent | 0 | 0 | 25 263 736 / 17 115 248 / 84 219 424 | +58 955 688 / **+67 104 176** | 64 | identical / identical |

All points: 0 `OutOfMemoryError`, 0 dump errors (`P*/counter-summary.txt`); mount options as set (`P*/mount.txt`); jar constant per point (`P*/jar-const.txt`); counter increments before/after the window (`run1/cluster/window-split.txt`).

### 4.2 Conclusion and logic

1. **Validity.** The mark was crossed many times in every capped arm and point (unit 64/16/4/16/15 rounds; cluster 64/64/16 rounds) [observed: `check-unit.txt`, `P*/counter-summary.txt`]. Each gateway ran the intended constant [observed: `P*/jar-const.txt`]; request sizes were as designed (64 × 1 048 576 at wsize 1 MiB, 1024 × 65 536 at wsize 64 KiB before the window) [observed: `counter-summary.txt` `incrementSizes`, `window-split.txt`]; the dump dir was empty at each gateway start [observed: `cluster-run.log` `ls -la …/nfsdump` per point]. Valid.
2. **Readings.** The first histogram after mounting carries ~8.1 MB of transient live `[B` in all five points (baseline 25.25 MB vs 17.11 MB five seconds later), so Δ against it is offset by about −8.1 MB everywhere; against the settled baseline2 the capped points are within ±0.03 MB [observed: `P*/histo-summary.txt`]. P2 (below the mark, 512 KiB held) shows +1.02 MB, about 0.5 MB more than the payload; not explained by the instruments (194 more `[B` instances than baseline2) and not used for the cap conclusion. The 7 extra 64 KiB counter increments in P3 occur in the fill phase after the window (the hole's own later 64 KiB writes arrive ahead of `nextOffset`); max there 327 680 [observed: `window-split.txt`].
3. **Matched rows.** Unit B2g row 1 ("Max counter ≤ mark + w − 1 and dump file ≈ G for every mark; threshold moves with K1"): DEBUG peaks 262 144 / 1 048 576 / 4 194 304 / 1 081 344, dump 16 MiB in steps of the mark [observed: `check-unit.txt`]; row 5 (positive control moved: disabled grows to 16 MiB while enabled ≤ mark) [observed: `SUMMARY,disabled_1m_w64k`]; row 7 (broken: writer hangs) [observed: `DUMPWM BROKEN` line]. Cluster B3g row 1: stock/4 MiB max counter = mark (≤ mark + wsize − 1), dump file 67 108 864 ≈ G, Δ`[B` ≈ 0 (O(mark)); control 1 GiB: Δ`[B` +67.10 MB ≈ G (vs baseline2; +58.96 MB vs the first baseline), no dump [observed: `P1,P3,P4,P5/*`].
4. **Excluded rows.** Unit: counter > mark + w − 1 or `inHeap()` above it with dumping on — no; dump stays 0 while crossing — no; threshold not moving — no (first dump at 256 KiB / 1 MiB / 4 MiB); disabled also ≤ 1 MiB — no; broken writer returns and counter keeps growing — no (WAITING at `:296`) [observed: `check-unit.txt`]. Cluster: stock Δ`[B` ≈ G or counter ≫ mark + wsize — no; dump at 1 MiB with the 4 MiB jar — no (all `Before dump` = 4 194 304); control also small — no; no `Update` lines — no; client hang with dump-file error — no (0 dump errors) [observed: `counter-summary.txt`, `histo-summary.txt`].
5. **Observed vs. inferred.** The cap, the dose-response and the control are observed. Inferred: (a) that the check at `:383` is what releases the blocked writers — supported by `Dumper woke up` appearing exactly rounds − 1 times in every arm/point (that line follows the `wait()` at `:386`, reached only through the true branch of `:383`, which calls `notifyAll()` at `:384`), by `After dump == 0` < mark in every round (the false branch, an immediate re-dump, never needed), and by every WRITE completing (all unit calls returned within 30 s; `ooo.py` finished in every point) [observed: `check-unit.txt`, `counter-summary.txt`, `P*/ooo.log`]; (b) that the window Δ`[B` is the out-of-order payload — supported by the control's +67 104 176 B ≈ 64 × 1 048 576 with 64 `WriteCtx` live.
6. **Deviations and gaps.** Amendments 1–2 (environment), D1 (integrity step; tier restarted). Baseline offset and the unexplained P2 +0.5 MB (part 2). Disk sampling at 1 s cannot resolve 1 MiB dump steps in the cluster; the step size is taken from the dumper's before/after lines and the final size. The gateway's per-file bound is not tested across several files or connections (A3 notes those overshoots; not part of B3).
7. **Core question.** Yes: in-heap out-of-order data per open file rises to the mark and is moved to the uncapped dump file, the ceiling moves with the constant (256 KiB → 1 MiB → 4 MiB in the unit tier; 1 MiB → 4 MiB in the gateway), and with the cap removed (disabled dump / 1 GiB mark) the whole gap stays in heap. The dumper's `:383` branch is what releases the writer after each dump.

**Conclusion (one line):** unit B2g rows 1, 5, 7 — **confirmed**; cluster B3g row 1 — **confirmed**.

## 5. Self-check of run 1 — AI

### 5.1 Check of run 1's conclusion

| Part | Holds? | Note (file re-read) |
|---|---|---|
| 1. Validity | yes | re-read `P*/counter-summary.txt`, `P*/jar-const.txt`, `javap-*.txt`, nfsdump listing per point in `cluster-run.log` |
| 2. Readings | yes | re-read `P*/histo-summary.txt` ×5 (baseline offset uniform); `window-split.txt` (P3 extras after the window) |
| 3. Matched rows | yes | `check-unit.txt` re-generated from `unit-trace.log` (0 mismatch counts); `P*/dump-window.txt` sizes 67 108 864 / 0 / 67 108 864 / 67 108 864 / 0 |
| 4. Excluded rows | yes | each row against `check-unit.txt` and `counter-summary.txt` |
| 5. Observed vs. inferred | yes | `Dumper woke up` = rounds − 1 in all 5 unit arms with dumps and 3 cluster points with dumps; P1 log excerpt `nfs3-dump-excerpt.log` shows `Asking dumper` → `Dumper woke up` alternation |
| 6. Deviations and gaps | yes | amendments dated before the readings they affect (`run1/frozen-sha256.txt`: first freeze before the unit run at 04:24 MST; D1 freeze before the restarted cluster tier at 04:30 MST) |
| 7. Core question | yes | hypothesis → dose (mark) → ceiling + spill → positive control, both tiers |

### 5.2 Run 2?

**No** — 2026-11-25. The conclusion rests on observed readings that equal the predictions to the byte; it confirms the claim and adds no bypass row.

## 6. Run 2 — not done

## 7. Comparison — not applicable

## 8. Verdict — AI

**Stage-3 estimate:** positive. **Outcome class:** **true positive** (positive, caps).

**Claim tested (B1):** for one open file on the NFS gateway with dumping enabled and a writable `nfs.dump.dir`, in-heap out-of-order WRITE data never exceeds `DUMP_WRITE_WATER_MARK + wsize − 1`, the rest goes to `<nfs.dump.dir>/<fileId>`, and moving the mark moves the threshold.

| Tier | Verdict | Effect on the constraint | Basis | Date |
|---|---|---|---|---|
| Unit | **Confirmed** — B2g row 1 (ceiling follows the mark, spill ≈ G), row 5 (control moved), row 7 (broken dump path hangs the writer) | caps (failure path: a dump file that cannot be created leaves the writer blocked with 1 MiB held; growth needs a null dump path) | run 1 + self-check | 2026-11-25 |
| Cluster | **Confirmed** — B3g row 1 (stock and 4 MiB capped, 1 GiB control holds ≈ G) | caps | run 1 + self-check | 2026-11-25 |

**Feedback filed:** section D of the amended case file (`~/writeup-hadoop/out/o17/case-amended.md`); not written to the repository (task rule). For `_INDEX.md` (when filed): order 17, "Confirmed — caps (unit, cluster); TP".
