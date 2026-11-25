# dfs.datanode.du.reserved-copyBlocks-getAvailable--autonomous — stage-4 results (queue order 26)

> **Case:** [`dfs.datanode.du.reserved-copyBlocks-getAvailable--autonomous`](../../stage3-ai-deep-read/jingsong/cases/dfs.datanode.du.reserved-copyBlocks-getAvailable--autonomous.md)
>
> **Status:** **verdict filed, 2026-11-25 — Confirmed — caps (unit tier and cluster tier).**
> Claim tested (B1): in each disk-balancer work item the destination receives blocks only while its `getAvailable()`
> (with `dfs.datanode.du.reserved` subtracted) exceeds `bytesToCopy`; blocks copied = `min(n_close, max(0, ceil((A0 − B)/c)))`,
> the destination's headroom above the reserve never ends below `B − c` (for B ≥ c), and ΔR moves the copied bytes 1:1 (±1 block).
> **Effect on the constraint:** `caps` (with the predicted bounded overshoot of at most one block when B < c, U4/C4).
>
> **Outcome class:** **true positive** (stage-3 estimate `positive`; both tiers Confirmed, effect `caps`).
>
> **Agent:** autonomous. "§9a" below means B2f/B2g (unit) and B3f/B3g (cluster); "§9b–§9e" means B2a–B2e / B3a–B3e;
> the case file's feedback section is its section D.

## 1. Before run 1 — design audit and freeze (written 2026-11-25 12:27 EST, before any run or reading)

| Field | Content |
|---|---|
| **Case-file version** | *(D2-1 added after cluster attempt 1, see §3: whole-file sha256 then `aa83296f499899be97efdc93341d7d666750db9b6f068d9c2d1de77589f57c22`, the frozen version for cluster attempt 2; the two table hashes below did not change. Only section D changed after the runs: current sha256 `6977914f…8640b3`; sha256 of everything before `## D.` = `7de9360d…a793c9b5`.)* Filed file: `hadoop/stage3-ai-deep-read/jingsong/cases/dfs.datanode.du.reserved-copyBlocks-getAvailable--autonomous.md`, last commit `cd9e1cded`, repository HEAD `8bd1dfb31`; sha256 at filing `a72ff16c073b46edb94b6d8393dea4b7f9e90939727658732d1534b4490706c1` (matches `_INDEX.md` §4 and the stage-3 copy in this folder). **Frozen version** (after audit amendments D1-1 to D1-6): `case-amended.md` in this folder, sha256 **`22b8972bc8eff61eb69601036996dda7561fed3ac2d4faeb9d6202ba3d044294`**. Frozen predictions + conclusions tables: `sed -n '/^\*\*B2f\./,/^\*\*B2h\./p' case-amended.md \| sha256sum` = **`cb47e128dd3dcc4adb94553830d585096b5697fe7d8e7469907aa5d6c092e838`** (unit); `sed -n '/^\*\*B3f\./,/^\*\*B3h\./p'` = **`5c41f7c98dabbb65323b4b12fae7ffa1e2fe8659bb683b05bba37e82718009a3`** (cluster). After this point only section D (feedback) may change. |
| **Harness** | `harness/` in this folder: `TestDiskBalancerDestReserve.java` (md5 `6ead6d87`), `unit-run.sh` (`618ef35c`), `cluster-run.sh` (`5d9388f3`, attempt 2; `cluster-run.attempt1.sh` `556dbd41` and `cluster-run.attempt1-to-2.diff` are the attempt-1 version). Instrument checks: `unit-run.sh … compile` → BUILD SUCCESS, 30 s (`run1/unit/compile.log`, `unit-run.log`); `bash -n cluster-run.sh`; the cluster script checks ports 19000/19864/19866/19867/19868/19870 free and stops at any failed check (knob, 128 fsck blocks, 128/0 blocks at A0, execute rc). |
| **Tiers and values** | Unit: U0 (R = 0, positive control), U1 (A0 ≈ B + 10.5c), U2 (A0 ≈ B + 20.5c), U3 (A0 ≈ B − c), U4 (A0 ≈ 800000, B = 600000, tolerance 100); B = 40 MiB, block 1 MiB, c = 1,056,775. Cluster: C0 (R = 0), C1 (A0 ≈ B + 20.5c), C2 (A0 ≈ B + 40.5c), C3 (A0 ≈ B − c), C4 (A0 ≈ 13,000,000, B = 10,000,000, tolerance 100); B = 1 GiB, block 16 MiB, c = 16,908,295. |
| **Audit bottom line** | **Ready after amendments** — 2026-11-25 |

### 1.1 Design audit

| Group | Check | Rating | Note (section checked) |
|---|---|---|---|
| A | constrained quantity is memory or disk bytes | Met | Bytes written by the disk balancer onto the destination volume: `dfsUsed` (block + meta) and, at cluster tier, `du -sb` of `vol-dst/current` (B2d, B3d). |
| A | knob varied, ≥ 3 values incl. default | Met | R = 0 (default; U0/C0) and three binding values each tier (U1–U3, C1–C3), plus an overshoot probe (U4/C4) (B2b, B3b). R is computed so that A0 hits a target; ΔR maps 1:1 to ΔA0. |
| A | real resource measured, not only the counter | Met (gap named) | Unit tier reads `dfsUsed` (the accounting the check uses) and the pre-move `getAvailable()`; cluster tier adds `du -sb` and `stat -f` (physical). Gap: unit tier has no physical `du` (B2d "Not observable"), covered at cluster tier. |
| A | usage driven to the limit and past it | Met | Source holds more than B (64 MiB > 40 MiB; 2 GiB > 1 GiB); binding runs reach the check's limit; U4/C4 probe one block past the reserve (B2c, B3c). |
| B | each step says what it establishes | Met | B2e/B3e steps and B2h/B3h controls (U0/C0 positive control, U3/C3 edge, reserve assertion, spy, log line). |
| B | prediction stated in numbers | Met | B2f/B3f give exact block counts, Δ`usedSpace` = n·c, H in (B − c, B]; arithmetic re-checked: 36·1.1 MiB < 40 MiB < 37·1.1 MiB → 37; 58·17.6 < 1024 < 59·17.6 MiB → 59; ceil(10.5) = 11, ceil(20.5) = 21, ceil(40.5) = 41; meta 7 + 2048·4 = 8199, 7 + 32768·4 = 131079. |
| B | every plausible outcome has a row | Partly → Met | Rows for refuted (counts like U0/C0; H < B − c; `du` intrusion), knob not applied, control failed, overshoot. Missing: "counts match but the stop is not the check" and a catch-all → added (D1-5, D1-6). |
| B | confirmation needs ceiling-follows-knob and direct disallow evidence | Partly → Met | Disallow evidence was in B2f/B3f's "log" column and B2h/B3h but not in the Confirmed row → D1-5/D1-6 require the line-1148 message in each binding run. |
| B | alternative explanations and controls | Partly → Met | Concurrent writers (none), DU refresh (`fs.du.interval`), knob not applied (reservedSpace assertion), other stops (log lines). Unhandled: small HDFS plan files on vol-src being moved by the balancer (they are valid source blocks) → D1-4. |
| C | a human can follow it from the intro and B1 | Met | B1 states the claim and refuted-if; A3 step 8 derives the bound. |
| C | an AI can run B2e/B3e without re-deriving | Partly → Met | MiniDFSCluster restart on the same base dir needs an explicit `hdfs.minidfs.basedir` (D1-2); node paths/environment (D1-1, D1-3). |
| C | knob, values, workload, commands, observables exact | Met | R formula, B, tolerances, bandwidth, file sizes, JMX query, sampling (1 s), stop condition (`PLAN_DONE`) given. |
| D | harness and environment prerequisites | Met | Test class and cluster script are step-1 work; node `pc91` has JDK 8, Maven, the built distribution and the 3.4.2 modules in `~/.m2`. |
| D | workload arithmetic reaches the limit | Met | Unit < 200 MB; cluster ≤ 6 GB on `/mydata` (≈ 703 GB free) — R only shrinks HDFS's view, nothing fills `/mydata`. |
| D | load-bearing citations spot-checked | Met | Against `systems/hadoop/source` (clean): `DiskBalancer.java:1138` (check), `:1148` (message), `:1110`, `:1121`, `:1102`, `:855-861` (`isLessThanNeeded`), `:882-886` (`isCloseEnough`), `:952-981`, `:784` (public `DiskBalancerMover(FsDatasetSpi, Configuration)`), `:692` (public `VolumePair`), `:603-625` (work item from step); `FsVolumeImpl.java:172-177` (reserve built from conf, dir = parent of `current`), `:434-455` (`getCapacity`), `:474-482` (`getAvailable` = max(min(remaining, available), 0)), `:484-522` (`getRemainingReserved`); `DF.java:85-97` (`getTotalSpace`, total − free, `getUsableSpace`; no caching); `ReservedSpaceCalculator.java:112-118` (per-dir key read with `getLong`); `FsDatasetImpl.java:1164-1300` (`moveBlockAcrossVolumes` → `copyReplicaToVolume`, no space check), `:3319-3333` (`getVolumeInfoMap`); `BlockPoolSlice.java:445-455` (`incDfsUsed(numBytes + meta length)`); `MiniDFSCluster.java:169, 234-241, 2173`; `TestDiskBalancer.java:640-700` (spy pattern); `DiskBalancerTestUtil.java:360-372`; `PlanCommand.java:209-220` (threshold), `Command.java:436-453` (plan IO through the default FS), `ExecuteCommand.java:61-105`. As cited. |

Derived check of the operand (A3 step 3, re-derived from the cited code): with `R ≥ actualNonDfsUsed = (total − free) − dfsUsed`,
the `available` arm is `usable − (R − (total − free − dfsUsed)) − rfr = total − g − R − dfsUsed − rfr` (g = free − usable): other
files on the filesystem cancel out, so running on the shared `/mydata` does not disturb the reading, and R ≥ actualNonDfsUsed
holds while `usable ≥ A`.

| # | Recommendation | Applied? | Why |
|---|---|---|---|
| 1 | Per-case source copy and offline test run, no `~/.m2` install (D1-1) | applied 2026-11-25 (case-amended.md) | environment |
| 2 | Explicit `hdfs.minidfs.basedir` per run for the restart (D1-2) | applied | an unambiguous restart on the same data |
| 3 | Run folder and distribution copy on the node, JDK 8 (D1-3) | applied | environment |
| 4 | No plan file in HDFS during a run; execute from local disk; check numBlocks 128/0 (D1-4) | applied | uncontrolled alternative: a small block on vol-src would be moved first and change `blocksCopied` |
| 5 | Confirmed row requires the line-1148 message per binding run; added "stop not from the check" and catch-all rows (D1-5, D1-6) | applied | group B: direct disallow evidence; every outcome needs a row |
| 6 | A physically filled small filesystem with R = 0 as an extra arm | left for stage 3 | not needed for the question; operand algebra shows other files cancel |

**Agreement criteria:** not applicable unless run 2 is chosen.


## 2. Environment

| Field | Run 1 |
|---|---|
| Date | 2026-11-25; node lock `/mydata/s4/NODE-LOCK` (`jingsong-h26-stage4`) from 10:21:59 MST to the end; unit tier 10:30:31–10:30:41 MST (surefire 10.4 s), cluster attempt 1 10:33–10:36:52, attempt 2 10:38–10:42:07 MST |
| Node | `pc91` = `node0.jason92-326665.misconfiguration-pg0.cloudlab.umass.edu`, Ubuntu 22.04, 32 cores, 125 GiB |
| OS and kernel | `5.15.0-203-generic` |
| JDK | `/usr/lib/jvm/java-8-openjdk-amd64` (1.8.0_514; `run1/unit/unit-run.log`) |
| Build tool | Maven 3.6.3, offline (`-o`), 3.4.2 modules from `~/.m2` (node build 2026-11-24); no install |
| Local source copy | `copy-source.sh` from repository HEAD `8bd1dfb31` (`systems/hadoop/source` clean) → `<run>/src`, baseline tag `rel/release-3.4.2` (`run1/copy-source.log`); only the test class added |
| Distribution | `/mydata/jingsong-s4/hadoop-base/hadoop-dist/target/hadoop-3.4.2` copied to `<run>/cluster/hadoop` (`Hadoop 3.4.2`) |
| Case-file commit / harness | case file `cd9e1cded`, frozen version §1; harness in `harness/` (not committed: the session does not commit) |
| Storage for node data | `/mydata` ext4 (`/dev/mapper/emulab-node0--bs`), total 807,902,732,288 B, root reserve g = 41,114,034,176 B, ≈ 750 GB usable; both volumes of each tier on it; R shrinks HDFS's view only (peak real use ≈ 6 GB) |
| Run folder | `/mydata/jingsong-s4/dfs.datanode.du.reserved-copyBlocks-getAvailable-run1/` (`<run>`) |
| Full logs | `<run>/logs/` on `pc91` (kept, 6.1 MB; see §8) |

## 3. Runbook defects

| # | Run | Step | Problem | Fix | Decision (date) | Case-file version with the fix |
|---|---|---|---|---|---|---|
| 1 | cluster attempt 1 (10:33–10:36 MST) | B3d "physical intrusion" observable | The formula `max(0, (S·b − S·(f−a) − R) − du_dst)` has its sign reversed: it is the headroom between the HDFS allowance and `du` (attempt 1: 1,065,270,733 in C1, 0 in C4). As written, the Refuted row "`du` intrusion > 0 in C1 or C2" would match every non-intruding run, and B3f's own C4 value (intrusion ≈ 3.9 MB with H ≈ −3.9 MB) cannot come out of it. The error is in the text (B3d against B3f), not in a reading; it was noticed when the first readings were printed. | Amendment D2-1: `max(0, du_dst − (S·b − S·(f−a) − R))`. B3f/B3g unchanged (table hash `5c41f7c9…` before and after). Harness: corrected formula; also the `-query -v` parser, which read C3's absent (zero) counters as `NA`. | 2026-11-25 10:37 MST: cluster tier restarted from step 1 (attempt 2, fresh format, new storage IDs). Attempt 1 kept in `run1/cluster-attempt1/`. | `case-amended.md` sha256 `aa83296f…f57c22` |

No unit-tier defect. Minor, not a defect: B3d says JMX `VolumeInfo` is keyed by `<vol>/current`; in 3.4.2 the key is the volume
base dir (`FsVolumeImpl.toString()` = `currentDir.getParent()`, `FsVolumeImpl.java:1098-1100`); the harness matches on the base dir.

## 4. Run 1

**Scope:** unit U0–U4 (one surefire JVM, one test method and two MiniDFSClusters per run); cluster C0–C4 (attempt 2, after D2-1).
**Command logs:** `run1/unit/unit-run.log`, `run1/cluster/cluster-run.log` (attempt 1: `run1/cluster-attempt1/cluster-run.log`).

### 4.1 Readings

**Unit tier** (`run1/unit/o26-readings.txt`: `step5`, `step7`, `move`, `result` lines; stop lines `run1/unit/stop-lines.txt`).
Surefire `Tests run: 5, Failures: 0, Errors: 0, Skipped: 0`. B = 41,943,040, c = 1,056,775, B − c = 40,886,265.

| Run | R (`reservedSpace(dst)` = R?) | A0 measured (target) | blocksCopied (pred n) | Δ usedSpace(dst) (pred n·c) | final H (in (B − c, B]?) | pre-move operand | stop line |
|---|---|---|---|---|---|---|---|
| U0 | 0 (yes) | 754,072,940,544 (≈ usable) | **37** (37) | 39,100,675 (39,100,675) | GBs | > B at all 37 moves | 1110 "Copy from … done" |
| U1 | 766,735,371,990 (yes) | **53,039,178** (53,039,178) | **11** (11) | 11,624,525 (11,624,525) | **41,414,653** (yes) | 53,039,178 → 42,471,428, step exactly c, all > B | **1148** ×1, no 1110/1121/1102 |
| U2 | 766,724,804,240 (yes) | **63,606,928** (63,606,928) | **21** (21) | 22,192,275 (22,192,275) | **41,414,653** (yes) | 63,606,928 → 42,471,428, step exactly c, all > B | **1148** ×1, none other |
| U3 | 766,747,524,903 (yes) | **40,886,265** (40,886,265) | **0** (0) | 0 | 40,886,265 (= A0) | no move | **1148** ×1, none other |
| U4 (B = 600,000, tol 100) | 766,787,611,168 (yes) | 800,000 (800,000) | **1** (1) | 1,056,775 (c) | **−256,775** (`freeSpace` 0) | 800,000 > 600,000 | 1110 on the next pass |

- `errMsg=null`, `errorCount=0` in every run; destination `rfr` 0; `srcBlocks0 = 64`, `dstBlocks0 = 0` in every run.
- U2 − U1 = 10 blocks = (63,606,928 − 53,039,178)/c = 10 exactly.
- In U1–U4 the spy's headroom `preH = total − g − R − usedSpace` equals the operand `getAvailable()` at every move (`preH==preAvail`), i.e. the operand is the reserve-adjusted headroom of A3 step 3, and other files on `/mydata` did not enter it.

**Cluster tier** (attempt 2; `run1/cluster/readings.csv`, `cluster-run.log` `KNOB`/`A0`/`RESULT` lines, `stop-lines-C*.txt`,
`dn-C*-diskbalancer-lines.txt`, `query-C*.out`, `jmx-C*.log`). B = 1,073,741,824, c = 16,908,295, B − c = 1,056,833,529.
At every A0: JMX `numBlocks` src 128 / dst 0, fsck 128 blocks, vol-src `reservedSpace` 0; execute accepted; result `PLAN_DONE`.

| Run | R (JMX `reservedSpace(dst)` = R?) | A0 (target) | blocksCopied / bytesCopied (pred) | Δ usedSpace (n·c) | Δ du − Δ usedSpace | final H (in (B − c, B]?) | min sampled `freeSpace` | `du` intrusion (D2-1) | DN stop line |
|---|---|---|---|---|---|---|---|---|---|
| C0 | key absent, 0 (yes) | 748,667,912,192 | **59** / 989,855,744 (59 / 989,855,744) | 997,589,405 (yes) | 8,192 | GBs | 748,652,834,816 | 0 | 1110 "copied 989855744 bytes and 59 blocks" |
| C1 | 765,368,311,664 (yes) | **1,420,361,872** (1,420,361,872) | **21** / 352,321,536 (21) | 355,074,195 (yes) | 8,192 | **1,065,287,677** (yes) | 1,065,287,677 | **0** | **1148** ×1, no other |
| C2 | 765,030,145,764 (yes) | **1,758,527,772** (1,758,527,772) | **41** / 687,865,856 (41) | 693,240,095 (yes) | 12,288 | **1,065,287,677** (yes) | 1,065,287,677 | **0** | **1148** ×1, no other |
| C3 | 765,731,840,007 (yes) | **1,056,833,529** (1,056,833,529) | **0** / 0 (0) | 0 | 0 | 1,056,833,529 (= A0) | 1,056,833,529 | 0 | **1148** ×1 (`Block Size: 16777216`) |
| C4 (B = 10,000,000, tol 100) | 766,775,673,536 (yes) | 13,000,000 (13,000,000) | **1** / 16,777,216 (1) | 16,908,295 (yes) | 12,288 | **−3,908,295** (`freeSpace` 0) | 0 | **3,933,428** | 1110 "copied 16777216 bytes and 1 blocks" |

- C2 − C1 = 20 blocks for (A0_C2 − A0_C1)/c = 20.0, i.e. ΔR = −338,165,900 B moved the copied bytes by 20 blocks.
- Attempt 1 (`run1/cluster-attempt1/readings.csv`) has the same R, A0, blocksCopied, bytesCopied, Δ usedSpace, final H and stop lines
  in every run (only the reversed-formula column and C3's `NA` counters differ).
- Side reading: vol-src `usedSpace` at A0 with 128 blocks was 2,164,286,336 (C0) = 128·c + 24,576, then
  +7,733,661 (C1) = 59 × 131,079, +10,486,320 (C2) = 80 × 131,079, +15,860,559 (C3, C4) = 121 × 131,079 — the cumulative number of
  blocks moved off vol-src times the meta length (§8, findings).

### 4.2 Conclusion and logic

1. **Validity.** The knob reached the destination in every run [observed: `step7` `reservedDst=R`; cluster `KNOB` lines]; the
   measured A0 equals the target to the byte [observed: same lines], so the limit was placed where planned and reached (U1–U3,
   C1–C3 stopped at it; U4/C4 went past it). Hold-fixed settings: `fs.du.interval=3600000` [observed: harness conf, `core-site`
   in `cluster-run.log`], no client writes during the move [observed: single-threaded test; no put/plan upload during execute —
   D1-4], destination `rfr` 0 [observed: `step7`, JMX], only `/data/f`'s 128 blocks present at A0 [observed: `blocks src=128 dst=0`].
   Positive controls moved usage: U0 37 blocks, C0 59 blocks [observed]. **Valid.**
2. **Readings.** No gap or outlier. Δ`du` exceeds Δ`usedSpace` by 8–12 KiB (new `subdir` directories), as B3f allows. Attempt 1
   and attempt 2 agree to the byte. The source-volume `usedSpace` drift (above) is on the source, not the measured destination.
3. **Matched rows.** Unit B2g row 1, "U1 and U2 copy n blocks as predicted; final H in (B − c, B]; U3 copies 0" plus D1-5
   (line-1148 in each of U1–U3, no other stop): 11 = 11, 21 = 21, H = 41,414,653 ∈ (40,886,265, 41,943,040], U3 = 0, one 1148
   line each [observed: `o26-readings.txt`, `stop-lines.txt`] → **Claim confirmed**. Also "U4 copies 1 block and H < 0" →
   **bounded overshoot confirmed** (qualifies, does not refute). Cluster B3g row 1, "C1, C2 and C3 match n; final H in (B − c, B];
   C2 − C1 = 20 blocks" plus D1-6: 21/41/0 = n, H = 1,065,287,677 ∈ (1,056,833,529, 1,073,741,824] twice, 20 blocks, one 1148
   line each [observed: `readings.csv`, `stop-lines-C*.txt`] → **Claim confirmed**; "C4: one block lands with H ≈ −3.9 MB" →
   bounded one-block overshoot confirmed (H = −3,908,295; `du` intrusion 3,933,428).
4. **Excluded rows.** Unit: "U1, U2 or U3 copy 37 like U0" (Refuted) — they copied 11/21/0; "Final H < B − c" (Refuted) —
   41,414,653 > 40,886,265; "operand does not fall by c" — every step exactly 1,056,775; "`reservedSpace ≠ R`" — equal in all;
   "U4 copies 0" — 1; "U0 fewer than 37" — 37; D1-5 "stop not from the check" — 1148 present, 1110/1121/1102 absent in U1–U3.
   Cluster: "C1 or C2 copies 59" (Refuted) — 21/41; "Final H < B − c" (Refuted) — 1,065,287,677 > 1,056,833,529, min sampled
   `freeSpace` never below it; "`du` intrusion > 0 in C1 or C2" (Refuted) — 0 and 0 (D2-1 formula); "`reservedSpace ≠ R`" —
   equal; "C0 fewer than 59 or errors" — 59, errorCount 0; "execute rejected" — accepted, `PLAN_DONE` each; D1-6 rows — 1148
   present, no other stop.
5. **Observed vs inferred.** Inferred: (a) the stop in U1–U3/C1–C3 came from the comparison at `:1138` — supported by the
   1148 message being the only stop line, which the source emits only in the false branch of `:1138`
   [observed: log; inferred: from `DiskBalancer.java:1138-1153`]; (b) at cluster tier the operand at each check equals JMX
   `freeSpace` (the 1 s sampler sees only some values) — the unit tier observes it per move, and the final cluster values equal
   A0 − n·c exactly. Nothing else in the conclusion is inferred.
6. **Deviations and gaps.** D1-1–D1-4 (environment, restart base dir, plan files kept out of HDFS) and D2-1 (formula; cluster
   tier restarted). The R = 0 arms run with the whole `/mydata` available, so the default does not bind (intended: positive
   controls). The unit tier has no physical `du` (B2d); the cluster tier covers it. The overshoot arms use a hand-set
   `tolerancePercent = 100` and a sub-block `bytesToMove`, which the planner does not produce by itself (A3 step 9e).
7. **Core question.** Yes: usage follows the constraint and the constraint caps it. Each binding value of R left the destination
   exactly `n = ceil((A0 − B)/c)` blocks deep and stopped it with headroom in (B − c, B] above the reserve (parts 3, 1), the
   amount moved shifting 1:1 with R (U2 − U1 = 10, C2 − C1 = 20 blocks; part 3), while with R = 0 the same workload moved
   37/59 blocks (part 1); the stop is the check's false branch (parts 3, 5). The reserve is entered only by at most one block
   when `bytesToCopy` < block size (U4/C4).

**Conclusion (one line):** unit B2g row 1 — **confirmed** (plus the bounded-overshoot row); cluster B3g row 1 — **confirmed**
(plus the bounded-overshoot row).

## 5. Self-check of run 1 — AI (2026-11-25 10:43–10:45 MST, local copies of the raw files re-read)

| Part | Holds? | Note (file re-read) |
|---|---|---|
| 1. Validity | yes | `run1/unit/o26-readings.txt` `step7`: `reservedDst=R` and `A0` = target in U1–U4; `run1/cluster/cluster-run.log` `KNOB` and `A0` lines: R matches, A0 = target, `blocks src=128 dst=0` before each run. |
| 2. Readings | yes | `readings.csv`: `dDu − dUsed` 8,192 / 8,192 / 12,288 / 0 / 12,288; attempt-1 `readings.csv` identical in every count and byte column. |
| 3. Matched row | yes | Recomputed from the files: U1 11, U2 21, U3 0, H 41,414,653; C1 21, C2 41, C3 0, H 1,065,287,677 in range; `dUsed = n·c` for all ten runs; 1148 counts 1/1/1 (unit `stop-lines.txt`; `stop-lines-C1..C3.txt`, `Block Size: 16777216`). |
| 4. Excluded rows | yes | Each Refuted row checked against the same files (counts ≠ 37/59, H ≥ B − c, intrusion 0 in C1/C2, min sampled `freeSpace` 1,065,287,677 in `jmx-C1/C2.log` via `readings.csv`). |
| 5. Observed vs inferred | yes | The 1148 message text is in the false branch only (`DiskBalancer.java:1138-1153`, re-read); per-move operand values in `move` lines: all `gtB=true`, steps exactly c (re-computed). |
| 6. Deviations and gaps | yes | D2-1 restart recorded (§3); attempt 1 kept; nothing skipped in attempt 2. |
| 7. Core question | yes | The steps go reading → matched row → "caps" by the audited logic (B1 → B2f/B3f → B2g/B3g). |

### 5.2 Run 2?

**No** (decided 2026-11-25). The conclusion rests on observed readings that match exact predictions to the byte in every run;
the only inferred statements are the stop's location (single log line from the false branch) and the per-check cluster
operand (observed per move at unit tier). It neither refutes the case nor confirms a bypass (the one-block overshoot is the
row the file predicted). The cluster tier was in effect run twice (attempts 1 and 2), with identical readings.

## 6–7. Run 2

Not done.

## 8. Verdict — AI

**Stage-3 estimate:** positive. **Outcome class:** **true positive** (positive, caps; both tiers Confirmed).

**Claim tested (B1):** in each disk-balancer work item, the destination volume receives blocks only while its `getAvailable()`
(with `dfs.datanode.du.reserved` subtracted) exceeds `bytesToCopy`; the number copied is `min(n_close, max(0, ceil((A0 − B)/c)))`,
the destination's headroom above the reserve never ends below `B − c`, and raising R by ΔR lowers the bytes written by ΔR (±1 block).

| Tier | Verdict (B2g / B3g row) | Effect on the constraint | Basis | Date |
|---|---|---|---|---|
| Unit | **Confirmed** — row 1 (U1 11 / U2 21 / U3 0 blocks, H 41,414,653 ∈ (B − c, B], 1148 stop each); bounded-overshoot row (U4: 1 block, H −256,775) | caps | run 1 + self-check | 2026-11-25 |
| Cluster | **Confirmed** — row 1 (C1 21 / C2 41 / C3 0 blocks, H 1,065,287,677 ∈ (B − c, B], C2 − C1 = 20, `du` intrusion 0, 1148 stop each); bounded-overshoot row (C4: 1 block, H −3,908,295, `du` intrusion 3,933,428) | caps | run 1 (attempt 2) + self-check | 2026-11-25 |

**Deciding numbers:** binding runs stop exactly at `n = ceil((A0 − B)/c)` blocks (11/21/0 unit, 21/41/0 cluster) with headroom
B − c/2 above the reserve (41,414,653; 1,065,287,677), against 37/59 blocks with R = 0; overshoot only with B < c, ≤ one block.

**Positive control:** n/a for a positive-estimate file; U0/C0 (R = 0) moved 37/59 blocks with the same workload.

**Feedback filed:** section D of `case-amended.md` (audit D1-1–D1-6, defect D2-1, stage-4 summary). Not committed (this session
does not commit). To file: copy `case-amended.md` over the case file; this file to
`hadoop/stage4-runtime-verification/jingsong/results/dfs.datanode.du.reserved-copyBlocks-getAvailable--autonomous.md`;
`harness/` to `…/harness/dfs.datanode.du.reserved-copyBlocks-getAvailable--autonomous/`; `run1/` to
`…/results/dfs.datanode.du.reserved-copyBlocks-getAvailable--autonomous/run1/`; update `_INDEX.md` row 26 (sha256 of the
filed case file) and `queue.csv` order 26 (`Confirmed — caps (unit + cluster); TP`).

**Findings beyond the verdict (upstream / doc candidates; check JIRA first):**
- **Source-volume `dfsUsed` leak on every disk-balancer move.** `FsDatasetImpl.cleanupReplica` (`:1187-1196`, called from
  `removeOldReplica` `:3507-3530` via `moveBlock` `:1164-1178`) calls `replicaInfo.deleteMetadata()` and then
  `onMetaFileDeletion(bpid, replicaInfo.getMetadataLength())`; `FinalizedReplica.getMetadataLength()` (`:149-153`) falls back to
  `getMetaFile().length()` (`LocalReplica.java:316-318`), which is 0 once the file is gone. Observed: vol-src `usedSpace`
  over-stated by exactly 131,079 B (meta of a 16 MiB block) per block moved off it (59, 80, 121 blocks), across DataNode
  restarts, until a DU refresh. Effect: the source looks fuller than it is (conservative for space checks; skews the planner's
  densities and the NameNode's DFS-used figures). The same path serves `moveBlockAcrossStorage` (Mover).
- **Over-conservative check, observed:** C3 moved nothing with 1,056,833,529 B (≈ 62 blocks) of headroom, because `:1138`
  compares against the whole `bytesToCopy`, not the block (A3 step 10; cf. HDFS-13892). With the planner's own plans
  (bytesToMove from the capacity that already excludes R) this makes the balancer stop early on a nearly full destination.
- **Bounded overshoot:** a plan step with `bytesToMove` below one block and a high `tolerancePercent` lands one block into the
  reserve (U4: 256,775 B; C4: 3,908,295 B by `dfsUsed`, 3,933,428 B by `du`).
- Design (stage 3): B3d's intrusion formula had its sign reversed (D2-1).
- No memory holder worth an OOM look (disk case; `DiskBalancerMover` holds no per-block buffers beyond the copy's small buffer).

**Cleanup and what stays on `pc91`:** no NameNode, DataNode, surefire, Maven, sampler or driver process left (checked with
`ps -u jason92 -o pid=,args= | awk …` after teardown, 10:42 MST); ports 19000/19864/19866/19867/19868/19870 free; driver PID file
`/mydata/s4/DRIVER-jingsong-h26.pid` removed; source copy, test data, `in.bin` (2 GiB), DataNode/NameNode data and the
distribution copy deleted. Kept: `/mydata/jingsong-s4/dfs.datanode.du.reserved-copyBlocks-getAvailable-run1/` (6.1 MB):
`harness/` and `logs/` (`unit/` incl. surefire output 1.3 MB, `cluster/` incl. `daemon-logs/`, `cluster-attempt1/`,
`copy-source.log`, `cluster-driver.out`). Node lock released at the end.
