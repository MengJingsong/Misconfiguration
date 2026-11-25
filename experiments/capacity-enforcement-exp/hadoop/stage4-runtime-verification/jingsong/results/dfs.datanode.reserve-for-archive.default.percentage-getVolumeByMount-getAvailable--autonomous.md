# dfs.datanode.reserve-for-archive.default.percentage-getVolumeByMount-getAvailable--autonomous — stage-4 results (queue order 29)

> **Case:** [`dfs.datanode.reserve-for-archive.default.percentage-getVolumeByMount-getAvailable--autonomous`](../../stage3-ai-deep-read/jingsong/cases/dfs.datanode.reserve-for-archive.default.percentage-getVolumeByMount-getAvailable--autonomous.md)
>
> **Status:** **done, 2026-11-25 — unit tier Confirmed, cluster tier Confirmed — caps.**
> Claim tested (B1): with same-disk tiering on and DISK+ARCHIVE volumes on one mount of effective capacity C, serial
> same-host DISK→ARCHIVE moves succeed exactly while the ARCHIVE volume's `getAvailable()` exceeds the block size, so the
> HDFS bytes on ARCHIVE stay ≤ floor(C × r), and the number of blocks moved scales with r.
> **Effect on the constraint:** `caps` (a soft cap: concurrent moves overshoot by up to T − 1 blocks, observed in the unit tier).
>
> **Outcome class:** **true positive** (stage-3 estimate `positive`; both tiers Confirmed, effect `caps`).
>
> **Agent:** autonomous. "§9a" = B2f/B2g (unit) and B3f/B3g (cluster); runbook = B2a–B2e / B3a–B3e; feedback = section D.

Run 1 by a fresh stage-4 agent working as Jingsong, on `pc91`, 2026-11-25 10:46–11:11 MST (node lock
`/mydata/s4/NODE-LOCK` held by `jingsong-h29-stage4` from 10:46:00 MST, released at the end). No run 2. Raw excerpts
are under `run1/` beside this file (copied from the node's `<run>/logs/`, which is kept; `<run>` =
`/mydata/jingsong-s4/dfs.datanode.reserve-for-archive.default.percentage-getVolumeByMount-getAvailable-run1`).
Daemon log times are UTC; script times are MST.

## 1. Before run 1 — design audit and freeze (written 2026-11-25 12:51 EST, before any reading)

| Field | Content |
|---|---|
| **Case-file version** | `hadoop/stage3-ai-deep-read/jingsong/cases/dfs.datanode.reserve-for-archive.default.percentage-getVolumeByMount-getAvailable--autonomous.md`, last commit `cd9e1cded`, repository HEAD `8bd1dfb31`; sha256 at filing `7643bd02d7a9f9ada4d226cde30ff06bd63412c5d59aabf27a5b1c979d9067a7` (= `_INDEX.md` §4 and the stage-3 copy in this folder). **Frozen version:** `case-amended.md` in this folder with audit amendments D1-1 to D1-7, sha256 **`0912dde9899ebba56570ae05d6a60e9e7905453f8ce501e2a1ec844ee3de44bc`**. Frozen text hashes (sha256, first 16 hex) — unit predictions and conclusions (`sed -n '/^\*\*B2f\./,/^### B3\./p'`): **`5a959a71622b5099`** (filed `2c0e2d2f48d745bd`); cluster predictions and conclusions (`sed -n '/^\*\*B3f\./,/^\*\*B4\./p'`): **`5db0e66a6fae5cf5`** (filed `53623a64be9f1256`). B1 and every predicted number of B2f/B3f are unchanged by the amendments. |
| **Harness** | `harness/` in this folder: `TestArchiveSameMountCap.java` (B2e with D1-2), `unit-run.sh`, `loop.sh`, `cluster-run.sh` (B3e with D1-5, D1-6); md5 after the run `e39903ad` / `c246a8f5` / `9d394564` / `ce3bb4b8` (cluster script as fixed after defect 2, §3); the node copies are identical. Instrument checks: `unit-run.sh … compile` → BUILD SUCCESS (`run1/unit/compile.log`), `bash -n` on the scripts, ports 19000/19864–19870 and loop devices free on `pc91` before the run. Not committed (output stays outside the repository). Checks recorded in §3/§4. |
| **Tiers and values** | Unit: r ∈ {0.0, 0.1, 0.25, 0.5} serial, control (tiering off, r = 0.1), concurrent r = 0.1 with T = 8; C = 128 MiB per volume, B = 1 MiB, N = 40. Cluster: r ∈ {0.0, 0.1, 0.25, 0.5} serial (Mover concurrency 1), concurrent r = 0.1 and 0.25 (Mover default 100), control (tiering off, r = 0.1); C = 8 GiB by `du.reserved` on a 12 GiB loop filesystem, B = 64 MiB, 32 blocks. |
| **Audit bottom line** | **Ready after amendments**, 2026-11-25 |

### 1.1 Design audit

| Group | Check | Rating | Note (section checked) |
|---|---|---|---|
| A | constrained quantity is memory or disk bytes | Met | HDFS bytes (block + meta) on the ARCHIVE volume of a shared mount (A2, B1); logical share, the move is a hardlink (A3.6) — named in the estimate. |
| A | knob varied, ≥ 3 values incl. default | Met | r ∈ {0.0 (default), 0.1, 0.25, 0.5} in both tiers (B2b, B3b). |
| A | real resource measured, not only the counter | Partly → Met | Cluster: `find` sums of block+meta files and `df` (B3d). Unit had dfsUsed and a file count only; D1-2b adds the byte sum of the ARCHIVE block files. |
| A | usage driven to the limit and past it | Met | 40 × 1 MiB vs 13.4 / 33.6 MB caps (unit); 32 × 64 MiB vs 0.86 / 2.15 GB (cluster); r = 0.5 beyond. |
| B | each step says what it establishes | Met | B2e/B3e steps with B2d/B3d observables; B2h/B3h controls. |
| B | prediction in numbers | Met | B2f/B3f exact counts and bytes; arithmetic re-checked (unit r = 0.1: k = 11 → 1,797,247 > 1,048,576 admits the 12th, k = 12 → 740,472 refuses; r = 0.25: 31; cluster r = 0.1: 12, r = 0.25: 31). dfsUsed starts at the block-pool `du`, not 0 (source: `BlockPoolSlice.java:218-222, 338-350`): D1-3 states the offset δ and shows the counts do not depend on it. |
| B | every plausible outcome has a row | Partly → Met | Missing: control failure, positive control failure in the unit tier, probe/move disagreement, refusal not from line 148: D1-4c, D1-7b. |
| B | confirmation needs ceiling-follows-knob and direct disallow evidence | Partly → Met | Line 148's decision was only inferred from the SameMount metric. D1-2a adds a direct probe of `getVolumeByMount` before each unit move; D1-6 adds the fallback WARN that carries line 148's operand in the cluster tier; D1-4a/D1-7a require them for Confirmed. |
| B | alternatives and their controls | Met | Tiering-off control (ratio vs capacity C), r = 0.5 positive control, sanity of mount map, serial vs concurrent (B2h, B3h). |
| C | a human can follow it | Met | B1 and the tables. |
| C | an AI can run it without re-deriving | Partly → Met | Build/run commands assume `install`, default ports, `start-dfs.sh`/`jps` and the whole `/mydata` mount; D1-1/D1-5 make them runnable on the node. The B3f Mover column could be read as a count of log lines: D1-6. |
| C | knob, values, workload, commands, observables exact | Met | B2b/B2c, B3b/B3c. |
| D | prerequisites exist or are listed | Met | Built distribution and `~/.m2` on `pc91`; JDK 8; sudo for the loop filesystem. |
| D | workload arithmetic reaches the limit | Met | Unit < 100 MB, cluster ≈ 2.2 GB on a 12 GiB loop fs (`/mydata` 703 GB free). Cluster df term never binding: for ARCHIVE `available_df = C − H_DISK − H_ARCHIVE` (`FsVolumeImpl.java:474-482, 484-521`), above `C·r − H_ARCHIVE` while H_DISK ≤ C(1−r). |
| D | citations spot-checked against `systems/hadoop/source` (clean) | Met | `FsVolumeList.java:140-152` (check at 148), `:177-186`, `:380-389`; `FsVolumeImpl.java:197-205` (mount only with tiering), `:434-456`, `:474-482`, `:514-521`, `:1546-1562` (hardlink, 0 bytes reserved); `MountVolumeInfo.java:43-58, 78-102`; `MountVolumeMap.java:48-67, 69-81`; `FsDatasetImpl.java:1061-1123` (check under the read lock at 1092-1108, metrics 1114-1117), `:1133-1150`; `DataXceiver.java:1198-1205` (same-host move, `Moved {} from StorageType {} to {}`); `RoundRobinVolumeChoosingPolicy.java:107-128`; `Mover.java:165-178, 233-243, 489-542`; `Dispatcher.java:320-325, 444-450, 603-641` (the Mover's target `maxSize2Move` is never checked when scheduling: no Mover-side cap beyond `maxRemaining > 0`); `DataNodeMetrics.java:204-210`; `MiniDFSCluster.java:1890-1903` (`setCapacityForTesting` after DN start). As cited. |

| # | Recommendation | Applied? | Why |
|---|---|---|---|
| 1 | Run on the node's existing build, loop filesystem for the shared mount (unit test data) | D1-1, 2026-11-25 | node rules; no change to B2f/B2g |
| 2 | Direct probe of line 148 and block-file byte sum in the unit tier | D1-2, 2026-11-25 | Group B direct disallow evidence; Group A real resource |
| 3 | State the dfsUsed offset δ from the initial `du` | D1-3, 2026-11-25 | exact dfsUsed predictions would otherwise miss by δ regardless of the cap; source-derived |
| 4 | Unit rows: probe requirement, control and positive-control failure rows | D1-4, 2026-11-25 | Group B |
| 5 | Cluster environment: dist copy, loop fs for data dirs, ports, `--daemon` | D1-5, 2026-11-25 | node rules |
| 6 | Mover column informational; refusal WARN with the operand as evidence; r = 0.0 enforced by the Mover | D1-6, 2026-11-25 | Group B/C |
| 7 | Cluster rows: SameMount + WARN requirement; refusal-not-from-148 and control-failure rows | D1-7, 2026-11-25 | Group B |
| 8 | Physical bytes: the cap is logical; a stage-3 note could say that `du.reserved`/df bound the mount, not the ratio | left for stage 3 | not needed for the run |

## 2. Environment

| Field | Run 1 |
|---|---|
| Date | 2026-11-25, 10:46–11:11 MST (unit 10:53–10:54, cluster 10:57–11:10) |
| Node | `pc91` = `node0.jason92-326665.misconfiguration-pg0.cloudlab.umass.edu`, Ubuntu 22.04, kernel 5.15.0-203-generic, 32 cores |
| JDK / Maven | `/usr/lib/jvm/java-8-openjdk-amd64` (1.8.0_514); Maven 3.6.3 offline, modules from `~/.m2` (node build 2026-11-24) |
| Source copy | `copy-source.sh` from repository HEAD `8bd1dfb31` → `<run>/src` (`run1/copy-source.log`); git baseline clean before the test class was added |
| Distribution | `/mydata/jingsong-s4/hadoop-base/hadoop-dist/target/hadoop-3.4.2` copied to `<run>/cluster/hadoop` |
| Case-file commit / harness | `cd9e1cded`; frozen version §1; harness in `harness/` (not committed) |
| Storage for node data | 12 GiB sparse image `<run>/loop.img`, ext4 `-m 0`, loop-mounted at `<run>/mnt` (`/dev/loop0`, df size 12,573,614,080 B; `run1/loop.log`). Unit: MiniDFSCluster base dir `<run>/mnt/testdata`; cluster: `dn/disk` and `dn/archive` under `<run>/mnt`, `du.reserved` = 3,983,679,488 → C = 8,589,934,592. NameNode dir and staging file on `/mydata`. |
| Full logs | `pc91:<run>/logs/` (4.7 MB: `unit/`, `cluster/<cfg>/`, `cluster-attempt0/`) |

## 3. Runbook defects and attempts

| # | Tier | Step | Problem | Fix | Effect |
|---|---|---|---|---|---|
| 1 | cluster | harness start (10:55) | `cluster-run.sh` was copied to the node before `chmod +x`; the first call failed silently, and a `bash -x … \| head` debug call ended by SIGPIPE before any command ran | `chmod +x`; the empty log folder kept as `run1/cluster-attempt0/` | no daemon started, no reading |
| 2 | cluster | B3e step 4 (r = 0.0, 10:55–10:57) | the harness wrote the staging file with its logging wrapper, so `blk.bin` was 67,108,930 B (the wrapper's two lines appended): each put made a 64 MiB and a 66 B block (64 DISK blocks). Workload not as written. | staging file written without the wrapper and its size checked (`STOP` unless 67,108,864) | cluster tier restarted from its beginning (r = 0.0 again, then the rest); the bad attempt's summary is in `run1/cluster-attempt0/summary.txt` (0 ARCHIVE replicas; Mover "Some blocks can't be moved") |

Neither is a defect of the case's runbook; no case-file change.

## 4. Run 1

**Scope:** unit tier: all six B2 configurations; cluster tier: all seven B3 configurations. Command logs:
`run1/unit/unit-run.log`, `run1/cluster/<cfg>/cluster-run.log`.

### 4.1 Readings

**Unit tier** (`run1/unit/o29-readings.csv`, surefire `Tests run: 6, Failures: 0, Errors: 0`; full output `run1/unit/surefire-output.txt.gz`)

Sanity in every tiering-on configuration (`sanity` rows): both volumes on `<run>/mnt`, `hasMount=true`, ARCHIVE
`getCapacity()` = expected floor(C×r) (0 / 13,421,772 / 33,554,432 / 67,108,864); `archDfsUsed0 = 24,576` = δ (D1-3) in every configuration.

| Config | moved / refused (B2f) | ARCHIVE block+meta bytes (B2f "dfsUsed after") | dfsUsed after (= bytes + δ) | available after (B2f − δ) | SameMount / SameHost | probe mismatches | `availBefore` at successes (min) / refusals (max) |
|---|---|---|---|---|---|---|---|
| r = 0.0 | **0 / 40** (0 / 40) | 0 (0) | 24,576 | 0 (0) | 0 / 0 | 0 (40 × `null`) | — / 0 |
| r = 0.1 | **12 / 28** (12 / 28) | **12,681,300** (12,681,300) | 12,705,876 | 715,896 (740,472 − 24,576) | 12 / 12 | 0 | 1,772,671 / 715,896 |
| r = 0.25 | **31 / 9** (31 / 9) | **32,760,025** (32,760,025) | 32,784,601 | 769,831 (794,407 − 24,576) | 31 / 31 | 0 | 1,826,606 / 769,831 |
| r = 0.5 | **40 / 0** (40 / 0) | **42,271,000** (42,271,000) | 42,295,576 | 24,813,288 (24,837,864 − 24,576) | 40 / 40 | 0 | 25,870,063 / — |
| control, tiering off, r = 0.1 | **40 / 0** (40 / 0) | 42,271,000 | 42,295,576 | 91,922,152 (≈ 91.9 M) | **0** / 40 | n/a | 92,978,927 / — |
| concurrent, r = 0.1, T = 8 | **19 / 21** (12–19) | **20,078,725** (≤ 20,078,725) vs capacity 13,421,772 | 20,103,301 | 0 (clamped) | 19 / 19 | (no probe) | — |

- Every refusal is `DiskOutOfSpaceException: Out of space: The volume with the most available space (=X B) is less than the block size (=1048576 B).` with X = the ARCHIVE `availBefore` (0, 715,896 or 769,831); the DataNode's fallback WARN (`RoundRobinVolumeChoosingPolicy.java:120`) appears once per refusal: 61 × X = 0 (r = 0.0: 40, concurrent: 21), 28 × 715,896, 9 × 769,831 (`run1/unit/fallback-warn-values.txt` counts these plus the harness's own echo of the message; the WARN-only count, 98, is from `surefire-output.txt.gz`).
- Boundary rows (r = 0.1): k = 11 `availBefore=1772671, probe=pass, moved, sameMountDelta=1`; k = 12 `availBefore=715896, probe=null, refused`.
- Every serial success had `availBefore` > 1,048,576 and every serial refusal ≤ 1,048,576 (checked over all 160 serial tiering-on rows, 0 exceptions).

**Cluster tier** (`run1/cluster/<cfg>/cluster-run.log`, `samples.csv`, `dn-move-lines.txt`, `fsck-after.txt`, `mover-tail.txt`)

Every configuration started from a fresh format: DataNode JMX before the Mover showed ARCHIVE `usedSpace` 24,576 (δ),
NameNode ARCHIVE `capacityTotal` = floor(C×r) (0 / 858,993,459 / 2,147,483,648 / 4,294,967,296; control 8,589,934,592),
32 DISK replicas by `fsck` and DISK `find` sum 2,164,261,088 B (= 32 × 67,633,159).

| Run | ARCHIVE capacity | replicas on ARCHIVE (fsck / `find`) (B3f) | ARCHIVE bytes `find` (B3f) | ARCHIVE `freeSpace` after (B3f − δ) | SameMount / SameHost | DN moved / distinct refused | refusal WARN X (count) | `df` used before → max → after the Mover | Mover |
|---|---|---|---|---|---|---|---|---|---|
| r = 0.0 | 0 | **0 / 0** (0) | **0** (0) | 0 | 0 / 0 | 0 / 0 | — | 2,164,518,912 → 2,164,527,104 → 2,164,518,912 | "Some blocks can't be moved", exit 254 |
| r = 0.1 | 858,993,459 | **12 / 12** (12) | **811,597,908** (811,597,908) | 47,370,975 (47,395,551 − 24,576) | 12 / 12 | 12 / 20 | 47,370,975 (20) | 2,164,563,968 → 2,164,588,544 → 2,164,580,352 | one pass, then `MetricsException`, exit 255 |
| r = 0.25 | 2,147,483,648 | **31 / 31** (31) | **2,096,627,929** (2,096,627,929) | 50,831,143 (50,855,719 − 24,576) | 31 / 31 | 31 / 1 | 50,831,143 (1) | 2,164,555,776 → 2,164,580,352 → 2,164,572,160 | same, exit 255 |
| r = 0.5 | 4,294,967,296 | **32 / 32** (32) | **2,164,261,088** (2,164,261,088) | 2,130,681,632 (2,130,706,208 − 24,576) | 32 / 32 | 32 / 0 | — | 2,164,568,064 → 2,164,584,448 → 2,164,584,448 | "Mover Successful", exit 0 |
| control (tiering off, r = 0.1) | 8,589,934,592 | **32 / 32** (32) | 2,164,261,088 | 6,408,871,712 (> 6 GB) | **0** / 32 | 32 / 0 | — | 2,164,551,680 → **2,220,646,400** → 2,164,535,296 | "Mover Successful", exit 0 |
| concurrent r = 0.1 | 858,993,459 | 12 / 12 (≥ 12) | 811,597,908 | 47,370,975 | 12 / 12 | 12 / 20 | 47,370,975 (20) | 2,164,518,912 → 2,164,543,488 → 2,164,535,296 | exit 255 |
| concurrent r = 0.25 | 2,147,483,648 | 31 / 31 (≥ 31) | 2,096,627,929 | 50,831,143 | 31 / 31 | 31 / 1 | 50,831,143 (1) | 2,164,568,064 → 2,164,592,640 → 2,164,584,448 | exit 255 |

- In tiering-on runs `df` used on the mount moved by at most 24,576 B (directory blocks) while up to 2.16 GB changed volume: the moves are hardlinks; `find -links +1` = 0 after every Mover. In the control `df` rose by 56,094,720 B in one sample (a copy in flight) and fell back.
- DataNode refusal lines: `opReplaceBlock …blk_… received exception …DiskOutOfSpaceException: Out of space: The volume with the most available space (=47370975 B) is less than the block size (=67108864 B).` (two log lines per refused block: the INFO line and the exception), each preceded by the fallback WARN on `…/dn/archive/` (`run1/cluster/r010/dn-move-lines.txt`).
- The sampler shows one transient 71 B DISK block in every run (the Mover's id file `/system/mover.id`), never on ARCHIVE.
- **Mover:** every run that refused a block exited 255 at the start of its second iteration with `org.apache.hadoop.metrics2.MetricsException: Metrics source Mover-<bpid> already exists!` (`run1/cluster/*/mover-tail.txt`), so no block was retried (B3f's "after 10 retries" did not happen; informational per D1-6).

### 4.2 Conclusion and logic

1. **Validity.** Both tiers valid. Limits were reached and passed at r = 0.1 and 0.25 in both tiers [observed: `o29-readings.csv` summary rows; cluster `RESULT` lines]. Hold-fixed settings: tiering flag and r in each config [observed: `sanity` rows; `cluster/<cfg>/hdfs-site.xml`]; C = 128 MiB per volume (unit) [observed: `archCapacity`/`diskCapacity` in `sanity` rows] and C = 8 GiB (cluster) [observed: NameNode `capacityTotal`, `report-start.txt` Configured Capacity 8,589,934,591 = DISK + ARCHIVE floors]; same mount [observed: `sameMount=true, hasMount=true`; DN JMX lists both volumes under `<run>/mnt`]; fresh state per configuration [observed: ARCHIVE `usedSpace` 24,576 and 0 ARCHIVE files before each Mover]; serial Mover `-D dfs.datanode.balance.max.concurrent.moves=1` [observed: `cluster-run.log` mover command line].
2. **Readings.** Nothing contradicts another. δ = 24,576 B in every volume, as D1-3 derived [observed]. The concurrent cluster runs did not hit the race (same counts as serial) while the unit concurrent run overshot by 7 blocks [observed]; the cluster Mover dispatches one pass only, then fails on its metrics source [observed: `mover-tail.txt`].
3. **Matched rows.** Unit, B2g row 1 with D1-4a: "Serial rows match B2f (moved count rises 0→12→31→40 with r; dfsUsed ≤ floor(C×r))" — moved 0/12/31/40, dfsUsed 12,705,876 / 32,784,601 / 42,295,576 ≤ 13,421,772 / 33,554,432 / 67,108,864 for r = 0.1 / 0.25 / 0.5 (at r = 0.0 dfsUsed is δ = 24,576 with 0 block files: the clamp `max(…, 0)` gives available 0), probe pass/null on every move with 0 mismatches, SameMount = moved [observed: `o29-readings.csv`]. Also matched: "Control moves all 40 with SameMount = 0" and "Concurrent run moves > 12 and dfsUsed > capacity" (19 moved, 20,078,725 B of block files on a 13,421,772 B volume) [observed]. Cluster, B3g row 1 with D1-7a: "Serial ARCHIVE replica counts 0 / 12 / 31 / 32 and bytes ≤ floor(C×r)" — exact, SameMount = replicas moved, refusal WARN X = 47,370,975 and 50,831,143 ≤ 67,108,864 [observed: `cluster-run.log`, `dn-move-lines.txt`]; also "Control moves all 32 with SameMount 0" [observed].
4. **Excluded rows.** Unit: serial success with `availBefore` ≤ 1,048,576 — none (min 1,772,671); file bytes > floor(C×r) + 8,199 — none; same count for every r — no (0/12/31/40); SameMount = 0 with moves under tiering — no; probe/move disagreement (D1-4c) — 0; control failure — no; r = 0.5 < 40 — no; concurrent > 19 — no (19). Cluster: bytes > floor(C×r) + 524,295 — none; same count for every r — no; moves with SameMount 0 under tiering — no; `df` grows by the moved amount — no (≤ 24,576 B); r = 0.5 < 32 — no; refusal WARN with X > 67,108,864 (D1-7b) — none; control failure — no. "Concurrent runs exceed the serial count" — not observed (B3f allows "≥ 12 / ≥ 31").
5. **Observed vs inferred.** Inferred: that the cluster refusals came from line 148 returning null — from the fallback WARN carrying line 148's operand (X ≤ block size) and from SameMount counting only line-148 passes [inferred: tiering on and empty storage id route every move through line 148 first, `FsDatasetImpl.java:1092-1108`]; the unit probe observes line 148's decision directly with the same operand. Inferred: the 71 B DISK block is the Mover id file [inferred: appears and disappears with each Mover, also at r = 0.0; not on ARCHIVE, so it does not touch the cap].
6. **Deviations and gaps.** D1-1/D1-5 (environment: loop filesystem, ports, existing build). Harness defects 1–2 (§3), cluster tier restarted. The cluster Mover never retried (Mover bug, §4.1), which does not change any frozen row; a retry would face the same `getAvailable()` (47–51 MB < 64 MiB). The cluster tier did not show the concurrency overshoot; the unit tier did.
7. **Core question.** Usage follows the constraint: the ARCHIVE share of the mount filled to 0 / 12 / 31 / all blocks for r = 0 / 0.1 / 0.25 / 0.5 in both tiers, each time stopping within one replica below floor(C×r) (parts 1, 3), and the refusals came from line 148's `getAvailable() > blockSize` (probe null, WARN X ≤ block size; parts 3, 5); with tiering off the same workload moved everything (part 3). The constraint caps HDFS's ARCHIVE bytes on a shared mount, softly: concurrent moves can pass the check together and overshoot by up to T − 1 blocks (unit, part 3). Physical bytes on the mount do not change on these moves (hardlinks; part 2).

**Conclusion (one line):** unit B2g row 1 — **confirmed** (plus the concurrent-overshoot row); cluster B3g row 1 — **confirmed**.

## 5. Self-check of run 1 — AI (2026-11-25, re-read the local copies in `run1/`)

| Part | Holds? | Note (file re-read) |
|---|---|---|
| 1. Validity | yes | `unit/o29-readings.csv` `sanity` rows (mounts equal, capacities as expected); `cluster/r010/report-start.txt` (Configured Capacity 8,589,934,591); `cluster/*/hdfs-site.xml` (tiering flag, r, du.reserved 3,983,679,488). |
| 2. Readings | yes | `summary` rows give δ = 24,576 in all six configs; `cluster/*/samples.csv` max `df` deltas as quoted; `mover-tail.txt` shows the `MetricsException` in the four runs that refused blocks. |
| 3. Matched row | yes | Unit summary rows: moved 0/12/31/40, archBlkBytes 0/12,681,300/32,760,025/42,271,000, sameMountOps = moved, probeMismatch 0; per-move check script found no success with `availBefore` ≤ 1,048,576 and no refusal above it. Cluster `RESULT`/`ACT` lines: 0/12/31/32 replicas, bytes as B3f to the byte, SameMount 0/12/31/32; WARN values 47,370,975 (20) and 50,831,143 (1). |
| 4. Excluded rows | yes | Each excluded by a number quoted in §4.2 part 4; none of the Refuted rows (B2g row 2, B3g row 2) is met: max file bytes per serial run ≤ floor(C×r). |
| 5. Observed vs inferred | yes | The cluster's line-148 attribution rests on two observations (WARN operand, SameMount); the unit probe observes the decision itself and agrees with every outcome. |
| 6. Deviations and gaps | yes | Defects 1–2 had no reading or were rerun from the start; the Mover bug only removes retries. |
| 7. Core question | yes | The cap follows r in both tiers and the refusals come from the traced check; the overshoot under concurrency is bounded by T − 1 as A3.6 derived. |

### 5.2 Run 2?

**No** (2026-11-25). Readings match exact predictions to the byte in both tiers, the disallow branch is observed directly
(unit probe) and through its operand (cluster WARN), and every control behaved as predicted.

## 6–7. Run 2

Not done.

## 8. Verdict — AI

**Stage-3 estimate:** positive. **Outcome class:** **true positive** — estimate `positive`, effect `caps` on both tiers.

**Claim tested (B1):** serial same-mount DISK→ARCHIVE moves succeed exactly while ARCHIVE `getAvailable()` > block size, so ARCHIVE HDFS bytes stay ≤ floor(C × r) and the number moved scales with r.

| Tier | Verdict | Effect on the constraint | Basis | Date |
|---|---|---|---|---|
| Unit | **Confirmed** — B2g row 1 (with D1-4a); also "Concurrent run moves > 12 and dfsUsed > capacity" (overshoot 7 blocks = T − 1) and "Control moves all 40 with SameMount = 0" | caps (soft under concurrency) | run 1 + self-check | 2026-11-25 |
| Cluster | **Confirmed** — B3g row 1 (with D1-7a); also "Control moves all 32 with SameMount 0" | caps | run 1 + self-check | 2026-11-25 |

**Feedback filed:** section D of `case-amended.md` (stage-4 summary, D1 amendments, stage-3 notes). To file in the repository:
copy `case-amended.md` over the case file, this file to
`hadoop/stage4-runtime-verification/jingsong/results/dfs.datanode.reserve-for-archive.default.percentage-getVolumeByMount-getAvailable--autonomous.md`,
`harness/` to `…/harness/dfs.datanode.reserve-for-archive.default.percentage-getVolumeByMount-getAvailable--autonomous/`, `run1/`
to `…/results/<stem>/run1/`; update `_INDEX.md` row 29 (stage 4 `Confirmed — caps (unit + cluster); TP`) and its §4 sha256
(`43407d8d20d23711e6f7a3818e127b55669bb3db1e1710d60918217492951587` after section D; frozen `0912dde9…3de44bc`), and `queue.csv` order 29.

**Findings beyond the verdict.**
- **Mover bug (upstream candidate, check JIRA):** in 3.4.2 `Mover.run` builds a new `Mover` per iteration (`Mover.java:685`) and the constructor registers `MoverMetrics` under `Mover-<bpid>` (`Mover.java:163`, `MoverMetrics.java:47-50`), so any second iteration throws `MetricsException: Metrics source … already exists!` and the Mover exits 255 without retrying.
- The cap is soft: concurrent same-mount moves pass the read-locked check together (no space reservation on the hardlink path); 8 threads overshot a 13.4 MB ARCHIVE share by 7 MiB-blocks (6.66 MB). Not reproduced through the Mover at default concurrency.
- At r = 0.0 the cap is enforced by the Mover (no ARCHIVE target), before the DataNode check.
- No memory holder worth an OOM look: the path holds per-block references only.

**Cleanup.** No NameNode, DataNode, Mover, surefire or Maven process left on `pc91` (checked by `ps … | awk`); the loop
filesystem was unmounted (the loop device auto-detached; `losetup -a` empty) and `loop.img`, `mnt/`, `src/` and
`cluster/` were deleted; no driver PID file was used; ports 19000/19864–19870 free; `/mydata/s4/NODE-LOCK` removed.
**Left on the node:** `<run>/harness/` and `<run>/logs/` (4.9 MB in total).
