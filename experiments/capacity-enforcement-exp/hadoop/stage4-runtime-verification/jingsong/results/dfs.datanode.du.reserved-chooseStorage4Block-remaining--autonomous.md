# dfs.datanode.du.reserved-chooseStorage4Block-remaining--autonomous — stage-4 results (queue order 25)

> **Status:** **done, 2026-11-25 — Confirmed — caps (unit tier and cluster tier).**
> Claim tested (B1): with `dfs.datanode.du.reserved = T' − H` on one volume (DataNode extra-space gate off), the
> NameNode stops placing blocks there once `remaining − scheduled·B < k·B`, so HDFS bytes on the volume never exceed H,
> and the write that would exceed it is refused at the NameNode.
> **Effect on the constraint:** `caps`.
>
> **Outcome class:** **true positive** (stage-3 estimate `positive`; both tiers Confirmed, effect `caps`).

Run 1 by a fresh stage-4 agent working as Jingsong, on `pc75`, 2026-11-25 06:05–06:55 MST (node lock held throughout,
released at the end). No run 2. Raw files are under `run1/` beside this file (copied from the node's
`/mydata/jingsong-s4/dfs.datanode.du.reserved-chooseStorage4Block-remaining--autonomous-run1/logs/`, which is kept; the
source copy, test data and cluster data were deleted, leaving 3.4 MB on the node).
## 1. Before run 1: design audit and freeze (done 2026-11-25, before any reading)

| Field | Content |
|---|---|
| Case file | `hadoop/stage3-ai-deep-read/jingsong/cases/dfs.datanode.du.reserved-chooseStorage4Block-remaining--autonomous.md`, last commit `bef6bc8a6`, repository HEAD `cd9e1cded`. The sha256 at filing, `b824c7a9…8e2132f`, matches `_INDEX.md` §4 and the copy in this folder. |
| Amended (frozen) version | `case-amended.md` in this folder. Audit amendments D1-1 to D1-7 (whole-file sha256 at the first freeze `e442d495…f0bb026`); after unit attempt 1, D2-1 (runbook defect, below) gave the frozen version for both tiers, sha256 **`5f9e496e0f42d4597b8256dfea050023aa2cff640a6db144d1c90e17069a4002`**. Only section D changed after that (feedback; current sha256 `aba8d2b9…4005e3e4`). Text hashes (sha256 of the `sed -n` ranges, first 16 hex): `**B2f.`–`**B2h.` `a13a5c9698c705ee` (filed `5ff4cdfabf1bb50c`; D2-1 note in B2f), `**B3f.`–`**B3h.` `c4276133647dbe6e` (filed `dd1fb86e82b46d8c`; D1-6/D1-7 rows). B1 and every predicted number are unchanged. |
| Harness | `harness/`: `TestChooseStorage4BlockReserved.java` (md5 `5ec93907`; U1 truth table, U2 four (H, k) clusters, Controls A and B; DEBUG on `BlockPlacementPolicy` per D2-1), `unit-run.sh` (`f3cae928`), `cluster-run.sh` (`8b3065fd`: B3 with D1-5, D1-6 and D2-1, `--daemon` start/stop, per-run log dirs, readings CSV per put, EXIT trap). Instrument checks: `unit-run.sh … compile` → BUILD SUCCESS (`run1/unit/compile.log`); `bash -n cluster-run.sh`; ports 19000/19864-19867/19870 free on `pc75`; the cluster START line checks the operand before any put (below). |
| Node | `pc75` (`node3.jason92-326665`), `/mydata` ext4 753 GB (≈ 751 GB available at start), JDK `1.8.0_514`, Maven 3.6.3 offline, distribution `/mydata/jingsong-s4/hadoop-base/hadoop-dist/target/hadoop-3.4.2` (`Hadoop 3.4.2`). Run folder `/mydata/jingsong-s4/dfs.datanode.du.reserved-chooseStorage4Block-remaining--autonomous-run1/` (none existed before; nothing partial to remove). Node lock `/mydata/s4/NODE-LOCK` held by `jingsong-o25-stage4` from 06:05:59 MST. |
| Tiers and values | Unit: U1 30 tuples (k ∈ {1,3} × s ∈ {0,1,2} × R ∈ {kB−1, kB, kB+1, (k+1)B, (k+2)B}, B = 1024); U2 H ∈ {32, 64} MiB × k ∈ {1, 3}, B = 4 MiB, real `FsDatasetImpl`, no `storageCapacities`; Control A H = 512 MiB; Control B H = 64 MiB with additional-available-space 1 GiB. Cluster: H ∈ {256, 512, 1024} MiB at k = 1, B = 16 MiB; k = 4 at H = 512 MiB by live reconfig; Control 1 H = 2 GiB (64 puts); Control 2 H = 512 MiB with additional-available-space at its default; Control 3 200 MiB non-HDFS file during H = 512 MiB. |
| Audit bottom line | **Ready after amendments**, 2026-11-25 |

### 1.1 Audit (groups A–D)

| Group | Rating | Note |
|---|---|---|
| A: core question | Partly → Met | The quantity is disk bytes of HDFS block + meta files on one volume (B2d, B3d: finalized-file sums and `du`), compared with the NameNode operand. The knob is varied through H (cluster: three values plus 2 GiB control; unit: two values plus 512 MiB control) and usage is driven past it (160 MiB / 1.25 GiB workloads). The default (`du.reserved = 0`, H = the whole 750 GB disk) is not run: filling `/mydata` is not allowed on the shared node; Controls A and 1 stand in (recommendation, not applied). |
| B: logic | Partly → Met | B1 states claim and refuted-if; B2f/B3f are numeric and the arithmetic checks (e.g. 251,658,240 / 16,908,295 → 15; 20,971,520 / 4,227,079 → 5). Disallow-branch evidence (`NOT_ENOUGH_STORAGE_SPACE`) is required for Confirmed. Control 3 had no reading rule and Control 1/2 failures no row: D1-6, D1-7 add them. |
| C: specific | Partly → Met | U1 as written sets utilization on a storage object the check never iterates (D1-1). `FsVolumeImpl.getReserved()` is package-private (D1-2). The MiniDFSCluster Builder forces additional-available-space = 0, so Control B as written would run with 0 (D1-3). Build/dist steps adapted to the node (D1-4, D1-5; environment only). |
| D: runnable | Met | Disk: ≤ 0.6 GiB unit, ≤ 2.2 GiB cluster on `/mydata` (751 GB free). Spot-checked against `systems/hadoop/source` (clean): `DatanodeDescriptor.java:816-840` (check at 833, DEBUG line 834-837), `:385-400`, `:862-883`; `FsVolumeImpl.java:434-460` (`getCapacity`, `cachedCapacity` only with fixed-volume-size), `:474-482` (`getAvailable`), `:484-521`, `:556` (`getReserved` package-private); `FsDatasetImpl.java:160-184`; `DF.java:85-97` (Java `File` space calls, no caching); `RoundRobinVolumeChoosingPolicy.java:110-126`; `BlockPlacementPolicyDefault.java:89, 919-923` (INFO reason line); `MiniDFSCluster.java:551-553`. As cited. |

## 2. Environment

| Item | Value |
|---|---|
| Node | `pc75` = `node3.jason92-326665.misconfiguration-pg0.cloudlab.umass.edu`, Ubuntu 22.04, 40 cores, 125 GiB |
| Disk for data | `/mydata` ext4, `T' = used + avail = 766,788,698,112` B; `DF.free − DF.usable` (root reserve) `41,114,034,176` B; ≈ 750 GB available during the runs |
| JDK / Maven | `/usr/lib/jvm/java-8-openjdk-amd64` (1.8.0_514); Maven 3.6.3, offline, modules from `~/.m2` (node build 2026-11-24) |
| Source copy | `copy-source.sh` from repository HEAD `cd9e1cded` → `<run>/src` (git baseline `rel/release-3.4.2`, clean before the test class was added; `run1/copy-source.log`) |
| Distribution | `/mydata/jingsong-s4/hadoop-base/hadoop-dist/target/hadoop-3.4.2` copied to `<run>/cluster/hadoop` (`Hadoop 3.4.2`) |
| Case file | commit `bef6bc8a6`; frozen version as in §1 |

## 3. Runbook defects and attempts

| # | Tier | Step | Problem | Fix | Effect |
|---|---|---|---|---|---|
| 1 | unit | B2f/B2g evidence of the disallow branch (attempt 1, 06:10–06:15) | Counts matched, but the NameNode's INFO reason was `{NO_REQUIRED_STORAGE_TYPE=1}`, never `NOT_ENOUGH_STORAGE_SPACE`. Source: with the writer on the DataNode's host, `chooseLocalStorage` calls the check first (`BlockPlacementPolicyDefault.java:630-655`); the fallback `chooseRandom` clears the reason map (`:835`) and, the only node being excluded, records `NO_REQUIRED_STORAGE_TYPE` (`:845-852`). | Amendment D2-1: evidence = the check's own DEBUG line (`DatanodeDescriptor.java:834-837`) from a NameNode IPC thread; DEBUG enabled for `BlockPlacementPolicy` in both tiers. Numbers unchanged. | unit tier restarted from the beginning (attempt 2, 06:17–06:22); attempt 1 kept in `run1/unit-attempt1/` (its counts are the same as attempt 2's) |
| 2 | cluster | harness (attempt 1, 06:23) | The `dfsadmin -report` parser also matched `DFS Remaining%:`, and a bash arithmetic error ended the script after the first cluster's start, before any put; NameNode and DataNode were left running. | parser `^DFS Remaining:`; EXIT trap that stops the daemons; daemons stopped by `cluster-run.sh stop` (`run1/cluster-attempt1/`), run folder wiped | cluster tier started again from the beginning (attempt 2, 06:23–06:54). No put had run. |

## 4. Run 1 — readings and conclusion

### 4.1 Unit tier (attempt 2; `run1/unit/`)

Surefire: `Tests run: 7, Failures: 0, Errors: 0, Skipped: 0` (`run1/unit/test.log`). Readings in `run1/unit/o25-readings.csv`.

**U1** (`U1,…` rows): 30 tuples, 0 mismatches against `null ⇔ k·B > R − s·B`; 16 null, 14 non-null. Boundary rows: k = 1, s = 0: R = 1023 null, R = 1024 storage; k = 1, s = 1: R = 2048 storage, R = 1025 null. The returned storage object is never the registered one (`registeredIsReturned=false` on every row), which is why D1-1 was needed.

**U2** (B = 4 MiB, b' = 4,227,079, ε = 24,576 in every cluster; `start` rows show `volReserved == T' − H`, `nnRemaining == H − ε`, diff 0):

| H | k | predicted N | accepted | `remaining` before the first refusal | finalized bytes at end (≤ H?) | prediction mismatches | check DEBUG lines (NN IPC thread) |
|---|---|---|---|---|---|---|---|
| 32 MiB | 1 | 7 | **7** | 3,940,303 < 4,194,304 | 29,589,553 (yes) | 0 | 2 (both refusals) |
| 32 MiB | 3 | 5 | **5** | 12,394,461 < 12,582,912 | 21,135,395 (yes) | 0 | 2 |
| 64 MiB | 1 | 15 | **15** | 3,678,103 < 4,194,304 | 63,406,185 (yes) | 0 | 2 |
| 64 MiB | 3 | 13 | **13** | 12,132,261 < 12,582,912 | 54,952,027 (yes) | 0 | 2 |
| Control A 512 MiB | 1 | all 40 | **40/40** | — | 169,083,160 | 0 | 0 |
| Control B 64 MiB, 1 GiB headroom | 1 | first write fails at DN | **0** (2 attempts) | 67,084,288 (NN predicts accept) | 0 | 2 (expected: NN accepts, DN refuses) | 0 |

- Per block, the NameNode's `remaining` fell by exactly b' (e.g. 33,529,856 → 29,302,777 → 25,075,698, rows `U2_H32_k1,1-3`), and the value the NameNode used before write i equals the DataNode's `getAvailable()` after write i−1 (heartbeat fresh).
- The 8 DEBUG lines from NameNode `IPC Server handler` threads (`run1/unit/nn-check-debug-lines.txt`) are one per refused write: `does not have enough DISK space (required=4194304|12582912, scheduled=0, remaining=0)` (the per-storage sum is 0 because the storage's own free space is below `required`, `DatanodeDescriptor.java:827-829`). The other 24 DEBUG lines come from the harness's own `pred` calls and from U1 (main thread).
- Each refusal's client error: `File /fill/fN could only be written to 0 of the 1 minReplication nodes. There are 1 datanode(s) running and 1 node(s) are excluded in this operation.`
- Control B: DataNode `DiskOutOfSpaceException: Out of space: The volume with the most available space (=67084288 B) is less than the block size (=4194304 B)` (4 lines), no check DEBUG line in that cluster's window.

**Matched row (B2g):** "U1 truth table matches" and "U2: `remaining ≈ H − ε − i·b'` and successes = N(H,k), failure from the NameNode check (D2-1)" → **claim confirmed**; "N changes with k as predicted" → demand side confirmed.
**Excluded rows:** past N / bytes > H (0 files over H, refusal exactly at N+1); `remaining` not tracking H (diff 0 at start, exact b' steps); DataNode gate bound (no `Out of space` in the main runs; it appears only in Control B); U1 mismatch (0/30).

### 4.2 Cluster tier (attempt 2; `run1/cluster/`)

Every fresh cluster's START check (`cluster-run.log`): `Configured Capacity − (H + DF.free − DF.usable) = 0` and `DFS Remaining − (H − DFS Used) = 0`, i.e. the key set the operand exactly. B = 16 MiB, b' = 16,908,295.

| Run | H | k | predicted N | accepted (of attempted) | finalized bytes after last success (B3f) | `DFS Remaining` at stop | check DEBUG lines in NN log | DN `Out of space` |
|---|---|---|---|---|---|---|---|---|
| H256k1 | 256 MiB | 1 | 15 | **15** (18) | **253,624,425** (253,624,425) | 14,786,455 < 16,777,216 | 3 (one per refused put, `required=16777216`) | 0 |
| H512k1 | 512 MiB | 1 | 31 | **31** (34) | **524,157,145** (524,157,145) | 12,689,191 | 3 | 0 |
| H512k4 (reconfig 1 → 4, `SUCCESS: Changed property`) | 512 MiB | 4 | 28 | **28** (31) | **473,432,260** (473,432,260) | 63,414,076 < 67,108,864 | 3 (`required=67108864`) | 0 |
| H1024k1 | 1 GiB | 1 | 63 | **63** (66) | **1,065,222,585** (1,065,222,585) | 8,494,663 | 3 | 0 |
| Control 1 | 2 GiB | 1 | all 64 | **64/64** | 1,082,130,880 (= 64·b') | 1,065,328,192 | 0 | 0 |
| Control 2 (headroom 1 GiB default) | 512 MiB | 1 | first put fails at DN | **0** (3) | 0 | 536,846,336 | 0 | 6 (+ 9 `less than the block size`) |

- Readings per put: `run1/cluster/readings-<run>.csv` (`finalizedBytes`, `du -sb current`, JMX and report values, `df`). The first refused put of each main run has the same finalized bytes as the last success, and no file under `finalized` ever exceeded H.
- Refused puts: client `could only be written to 0 of the 1 minReplication nodes … 1 node(s) are excluded` (`put-errors-<run>.txt`); NameNode DEBUG `The node 127.0.0.1:19866 does not have enough DISK space (required=…, scheduled=0, remaining=0)` (`daemon-logs/logs-<run>/…namenode….log`; H512k4's lines are in `logs-H512k1`, same NameNode). INFO reason, as D2-1 explains: `{NO_REQUIRED_STORAGE_TYPE=1}`.
- **Control 3** (after put 10 of H512k1): `Remaining` 367,763,386 before, 4 s and 7 s after a 200 MiB `dd … conv=fsync`, while `df used` went from 16,822,644,736 to 17,032,368,128 (+209,723,392 = 200 MiB). The reservation absorbs non-HDFS files, as A2 derives.
- Usage follows the knob: accepted puts 15 / 31 / 63 and finalized bytes 0.254 / 0.524 / 1.065 GB for H = 0.268 / 0.537 / 1.074 GB, each within one block below H; with the cap far away (2 GiB) all 64 puts succeed.

**Matched row (B3g):** "accepted puts = N(H,k) ±1, finalized bytes ≤ H, failure from the NameNode check" (exact, ±0) → **claim confirmed**; "accepted puts and bytes scale with H (15/31/63)"; "k = 4 gives 28 vs 31" → demand side confirmed; D1-6 row "Control 3: `Remaining` unchanged" → reservation algebra holds.
**Excluded rows:** puts past N / bytes > H; `Remaining` ≈ raw `df avail` (it was `H − DfsUsed` to the byte); DataNode gate bound (0 `Out of space` in the main runs); refusal while `DFS Remaining` ≥ k·B (every refusal had `DFS Remaining` < k·B); D1-7 rows (Control 1 never refused; Control 2's first put failed).

### 4.3 Observed vs inferred; deviations and gaps

- Observed: counts, bytes on disk, NameNode operand, the check's DEBUG line at each refusal, the DataNode's `Out of space` only in the two side controls.
- Inferred: that `scheduledSize` was 0 at each cluster refusal (not exported); the DEBUG lines print `scheduled=0`, which observes it at the refusals.
- Deviations: D1-4/D1-5 (environment), D2-1 (evidence signature). The knob's default (0, H ≈ 767 GB) was not run (disk not to be filled); Controls A and 1 stand in.

## 5. Self-check (re-read raw files, 2026-11-25)

| Part | Holds? | Note |
|---|---|---|
| 1. Inferred statements | holds | `scheduled=0` is printed in each NN DEBUG line (re-read `nn-check-debug-lines.txt` and `logs-H256k1` NN log). |
| 2. Unit counts | holds | `summary` rows in `o25-readings.csv`: successes 7/5/15/13 = `N_pred(eps)`; `filesOverH=0`; `predMismatches=0`; U1summary `mismatches=0`. |
| 3. Cluster counts and bytes | holds | `RESULT` lines in `cluster-run.log` and last-OK rows of the readings CSVs; finalized bytes equal B3f's products to the byte. |
| 4. Disallow branch fired (not another gate) | holds | 8 unit / 12 cluster DEBUG lines from the check, one per refusal; 0 DataNode `Out of space` outside Controls B/2; Controls B/2 show the other gate with no check line. |
| 5. Logic answers the core question | holds | The cap follows H (three values plus a far control) and k; HDFS disk bytes stop within one block below H; the refusal comes from the traced check. |

## 6–7. Run 2

Not run. The conclusion rests on observed readings matching exact predictions, with every control behaving as predicted.

## 8. Verdict and feedback

- **Verdict:** unit tier **Confirmed**, cluster tier **Confirmed** — **effect `caps`**. **Outcome class: true positive** (estimate `positive`, stage-4 effect `caps` on both tiers).
- Case-file feedback: section D of `case-amended.md` (D1/D2 amendments and the stage-4 summary). To file: copy `case-amended.md` over the case file, this file to `hadoop/stage4-runtime-verification/jingsong/results/dfs.datanode.du.reserved-chooseStorage4Block-remaining--autonomous.md`, `harness/` to `…/harness/dfs.datanode.du.reserved-chooseStorage4Block-remaining--autonomous/`, small excerpts of `run1/` to `…/results/<stem>/run1/`; update `_INDEX.md` row 25 and `queue.csv` order 25 (`stage4` = `Confirmed — caps (unit + cluster); TP`) and the index sha256.
- For stage 3: predict log evidence from the whole placement path; with a writer co-located with the only DataNode, `NOT_ENOUGH_STORAGE_SPACE` never reaches the INFO reason map.
- Cleanup: no NameNode, DataNode, surefire or Maven process left on `pc75` (checked after teardown); no driver PID file; ports free; `/mydata/s4/NODE-LOCK` removed. Kept on the node: `<run>/harness/` and `<run>/logs/` (3.4 MB).
