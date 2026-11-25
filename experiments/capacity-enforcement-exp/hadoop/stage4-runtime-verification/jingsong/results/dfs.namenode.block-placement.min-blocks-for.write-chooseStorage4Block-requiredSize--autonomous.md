# dfs.namenode.block-placement.min-blocks-for.write-chooseStorage4Block-requiredSize--autonomous — stage-4 results  <!-- file: results/dfs.namenode.block-placement.min-blocks-for.write-chooseStorage4Block-requiredSize--autonomous.md -->

> **Case:** [`dfs.namenode.block-placement.min-blocks-for.write-chooseStorage4Block-requiredSize--autonomous`](../../../stage3-ai-deep-read/jingsong/cases/dfs.namenode.block-placement.min-blocks-for.write-chooseStorage4Block-requiredSize--autonomous.md) (queue order 24)
>
> **Status:** verdict filed (run 1 + self-check; no run 2), 2026-11-25
>
> **Outcome class:** true positive — estimate `positive`, effect `caps` in both tiers
>
> **Agent:** autonomous. "§9a" below means B2f/B2g (unit) and B3f/B3g (cluster); "§9b–§9e" means B2a–B2e / B3a–B3e; the feedback section is section D.

Written outside the repository (`~/writeup-hadoop/out/o24/`); paths below are relative to that folder. The amended case file is `case-amended.md`; the harness is `harness/`; run evidence is `run1/`.

## 1. Before run 1 — design audit and freeze

| Field | Content |
|---|---|
| **Case-file version** | Repository commit `bef6bc8a6` (repo HEAD `cd9e1cded`), filed sha256 `4a9fe2e6e2e939d011755e37a59ded9ed6d7cb4041f3918f72bc11f765079555`. After the audit's amendments: unit tier frozen at `3d08879e09840d50c2e20dd971bbe71de0586e57aa8e153424bd4f13adafb7ed` (B2 amendments + first B3a amendment); cluster tier frozen at `e367e1f88ee402a2024fef14bd358b3cc1f054f59d72fad5283576185a549218` (adds the ext2 correction to B3a and the B3d/B3g amendment; B2 text identical). With section D filled, the file's sha256 is `45001735a79122e3…` (`sha256sum case-amended.md`). For `_INDEX.md` §4: the hash of the file as committed after D is filled. |
| **Harness** | `harness/TestMinBlocksForWriteCap.java`, `harness/unit-run.sh`, `harness/cluster-run.sh` (outside the repo; not committed — the task forbids repo edits). Destination if adopted: `hadoop/stage4-runtime-verification/jingsong/harness/<stem>/`. |
| **Tiers and values** | Unit: U1 (B = 1024, N = 4, r and k sweeps), U2 N ∈ {1, 4, 8, 16} with C = 32 MiB, B = 1 MiB; u2Reconfigure 16 → 1; DataNode-side control. Cluster: N ∈ {1, 8, 16, 32} with capacity 256 MiB, B = 4 MiB; step 5 (32 → 1); step 6 (DataNode-side control). |
| **Audit bottom line** | **Ready after amendments** — 2026-11-25 |

### 1.1 Design audit

| Group | Check | Rating | Note (section checked) |
|---|---|---|---|
| A | constrained quantity is disk bytes | Met | A2, B1: HDFS block bytes on the DataNode volume; `du -sb` / volume-dir bytes measured (B2d, B3d). |
| A | knob varied, ≥ 3 values incl. default | Met | B2b {1,4,8,16}, B3b {1,8,16,32}; default 1 included; live reconfiguration as a second lever. |
| A | real resource measured, not only the counter | Met | Real bytes in the volume directory / `du -sb` and block-file counts, besides `getRemaining`/`DfsUsed`. |
| A | usage driven to the limit and past it | Met | Fill loops run until refusal (B2c, B3c). |
| B | each step says what it establishes | Met | B2g/B3g rows; B2h/B3h controls. |
| B | prediction in numbers | Met | B2f K = 31/28/24/16; B3f K = 63/56/48/32 with remaining bands and `du`. |
| B | every plausible outcome has a row | Partly | B2g/B3g cover follows / flat / not one-for-one / DataNode bound / overshoot. "Counter capped, real resource grows" is covered implicitly by the `du` column only. Left for stage 3. |
| B | confirmation needs ceiling-follows-knob and direct disallow evidence | Partly → Met after amendment | B3d named `NOT_ENOUGH_STORAGE_SPACE`, which is never logged for a writer on the DataNode's host (§3 defect 4). Amended to the DEBUG line of `DatanodeDescriptor.java:834`. |
| B | alternatives and controls | Met | considerLoad off, additional-available-space 0, heartbeat sync, reconfigure control, DataNode-side control. |
| C | human can follow from intro and B1 | Met | Estimate row + B1. |
| C | AI can run without re-deriving | Partly | B2c's storage object and MiniDFSCluster's override of additional-available-space needed source reading (§3 defects 1–3). |
| C | exact values, commands, stop conditions | Met | B2b/B3a/B3c exact; stop at first IOException / put failure. |
| D | harness and prerequisites listed | Met | B2a/B3a; built dist on `pc91`. |
| D | workload arithmetic reaches the limit | Partly → Met after amendment | Arithmetic correct for capacity 256 MiB, but the du.reserved method gives remaining = 0 on a root-reserved ext4 `/mydata` (§3 defect 5). |
| D | citations spot-checked | Met | `DatanodeDescriptor.java:816-841`, `DFSConfigKeys.java:1299-1302`, `BlockPlacementPolicyDefault.java:963-975`, `BlockManager.java:2469-2476`, `FsVolumeImpl.java:434-482, 513-521`, `RoundRobinVolumeChoosingPolicy.java:110-111`, `DF.java:85-97` read in the pinned source. |

| # | Recommendation | Applied? | Why |
|---|---|---|---|
| 1 | Call `reconfigureProperty` (public) instead of `reconfigurePropertyImpl` (protected, `NameNode.java:2338`) | Applied, B2b/B2e amendment 2026-11-25 (before run 1) | Not callable from the test's package. |
| 2 | Add the B2h DataNode-side control as a test, and a U1d variant with the values swapped | Applied, B2e amendment 2026-11-25 | Runs the control the design lists; the U1d variant shows bypass (d) as a reading only. |
| 3 | Cluster disk: loop filesystem without reserves instead of du.reserved on `/mydata` | Applied, B3a amendment 2026-11-25 (before cluster run 1) | du.reserved alone gives remaining = 0 on `/mydata` (5 % root reserve, ~41 GB on `pc91`); ext4 `-m 0` still keeps 10735616 B of delalloc reserve; ext2 `-m 0` gives remaining = 256 MiB − dfsUsed exactly. |
| 4 | Disallow evidence: DEBUG line at `DatanodeDescriptor.java:834`, DEBUG logging required | Applied, B3d/B3g amendment 2026-11-25 (before cluster run 1) | Source reason, below (§3 defect 4). |
| 5 | B2c: set utilization on `dn.getStorageInfo("s1")`; note MiniDFSCluster's additional-available-space = 0 override | Harness fix; left for stage 3 as wording | §3 defects 1 and 3. |
| 6 | Add an explicit "counter capped, real resource grows" row | Left for stage 3 | Covered by `du` column; not needed for this run. |

**Agreement criteria** — not applicable (no run 2).

## 2. Environment

| Field | Run 1 |
|---|---|
| Date | 2026-11-25 (05:45–06:19 MST on the node) |
| Node | `pc91` (`node0.jason92-326665`), 32 cores, 125 GiB RAM |
| OS and kernel | Ubuntu 22.04.2 LTS, `5.15.0-203-generic` |
| JDK | OpenJDK `1.8.0_514` (`/usr/lib/jvm/java-8-openjdk-amd64`) |
| Build tool | Maven 3.6.3 (offline, `-o`); distribution `/mydata/jingsong-s4/hadoop-base/hadoop-dist/target/hadoop-3.4.2` (built 2026-11-24) |
| Local source copy | `copy-source.sh` → `/mydata/jingsong-s4/<stem>-run1/src` from `systems/hadoop/source` at repo `cd9e1cded` (tag `rel/release-3.4.2`) |
| Case-file commit / harness commit | `bef6bc8a6` / not committed (outside the repo) |
| Storage | Unit: `/mydata/jingsong-s4/<stem>-run1/test-data` (MiniDFSCluster, `setCapacityForTesting` 32 MiB). Cluster: 512 MiB loop ext2 (`-m 0`) at `$RUN/dnfs`, `dfs.datanode.du.reserved` = 528044032 − 268435456 = 259608576 → Configured Capacity 268435456 |
| Full logs | `run1/unit/`, `run1/cluster/` (incl. `daemon-logs/`), node copy `/mydata/jingsong-s4/<stem>-run1/logs/` |

## 3. Runbook defects

| # | Run | Step | Problem | Fix | Decision (date) | Case-file change |
|---|---|---|---|---|---|---|
| 1 | unit attempt 1 | B2c U1 | `DFSTestUtil.createDatanodeStorageInfo` returns a second `DatanodeStorageInfo`, not the one in the descriptor's `storageMap`; setting utilization on it leaves the registered storage at remaining 0, so every U1 call returned null (`run1/unit-attempt1/`). | Harness: utilization set on `dn.getStorageInfo("s1")`. | Instrument bug; unit tier restarted from its beginning (2026-11-25) | none (recommendation 5) |
| 2 | unit attempt 1 | B2c U2 | `DFSTestUtil.createFile`'s try-with-resources turns the refusal into `IllegalArgumentException: Self-suppression not permitted`, which escaped the IOException catch (5 test errors). | Harness: own one-block writer that catches IOException. | Instrument bug; unit tier restarted | none |
| 3 | unit attempt 1 | B2h control | `MiniDFSCluster.Builder(conf)` sets additional-available-space = 0 (`MiniDFSCluster.java:551-553`); the DataNode-side control therefore ran with 0 (it gave K = 31, an N = 1 run). | Harness: set the key after creating the Builder. | Instrument bug; unit tier restarted | none |
| 4 | unit attempt 1 (found), cluster (applied) | B3d/B3g | For a writer on the DataNode's host, `chooseLocalStorage` adds the node to `excludedNodes` first (`BlockPlacementPolicyDefault.java:635`); `chooseRandom` clears the reason map (`:835`) and logs `{NO_REQUIRED_STORAGE_TYPE=1}` (`:851`, `:925`). `NOT_ENOUGH_STORAGE_SPACE` never appears; the B3g row would have called every valid run "another check bound". | DEBUG logging for `BlockPlacementPolicy` required; disallow evidence = `does not have enough DISK space` at `DatanodeDescriptor.java:834`. | Amended before cluster run 1 (2026-11-25); B3f unchanged | B3d, B3g |
| 5 | cluster, audit + setup check | B3a | du.reserved on `/mydata`: `DF.getAvailable` = usable space, so `getAvailable` = 256 MiB − root reserve (~41 GB) − dfsUsed → 0. The loop-file alternative with ext4 `-m 0` still read `DFS Remaining` 257675264 instead of 268410880 (ext4 delalloc reserved clusters, 2621 × 4096 B), which would lower every K by ~2.5 (`run1/cluster-setup-attempt1/`; no put had run). | 512 MiB loop **ext2** `-m 0`, du.reserved = size − 256 MiB. Setup check then read Configured Capacity 268435456 and `DFS Remaining` 268410880 = 256 MiB − d0. | Amended before cluster run 1 (2026-11-25); B3f unchanged | B3a, B4 |

## 4. Run 1

**Scope:** unit (all of B2e plus the DataNode-side control) and cluster (B3e steps 1–7, including optional step 6). **Command log:** `run1/unit/unit-run.log`, `run1/cluster/cluster-run.log`, `run1/driver.out`.

### 4.1 Readings

**Unit tier** (`run1/unit/o24-readings.csv`; surefire: Tests run 10, Failures 0, Errors 0)

| Test | Result | Prediction | Evidence |
|---|---|---|---|
| U1a (B = 1024, N = 4) | r = 4095 → null; 4096, 4097, 8192 → s1 | same | `o24-readings.csv` U1a; DEBUG `required=4096, scheduled=0, remaining=0` for r = 4095 (`evidence-excerpt.txt`) |
| U1b (r = 8192) | k = 0..4 → s1; k = 5 → null | same | U1b rows; DEBUG `scheduled=5120, remaining=8192` |
| U1c (two storages r = 3072 each) | null | null | U1c row |
| U1d(a) (s1 r = 4096 first, s2 r = 1000) | s1 | s1 | U1da row |
| U1d(b) supplementary (s1 r = 1000 first, s2 r = 4096) | s1 (the storage that failed line 828) | — (reading only) | U1db row |
| U2 N = 1 | K = 31; nnRemaining at refusal 769831 B; vol dir 32760606 B, 31 blk files | 31; [−8199, 1048576) | `U2N1` rows |
| U2 N = 4 | K = 28; 3940156 B; 29590281 B, 28 files | 28; [3137529, 4194304) | `U2N4` |
| U2 N = 8 | K = 24; 8167256 B; 25363182 B, 24 files | 24; [7331833, 8388608) | `U2N8` |
| U2 N = 16 | K = 16; 16621456 B; 16908982 B, 16 files | 16; [15720441, 16777216) | `U2N16` |
| u2Reconfigure | 16 at N = 16, refused; `reconfigureProperty` → policy N = 1; 15 more, total 31; vol dir 32760606 B | 16 + 15 = 31 | `U2R` rows; `ReconfigurableBase ... changing property ... to 1` |
| DataNode-side control (1 GiB headroom, N = 1) | K = 0; DataNode `DiskOutOfSpaceException: Out of space ... (=33529856 B) is less than the block size`; no `:834` DEBUG line | K = 0 | `U2DN` rows; output lines 317–319 |
| Every U2 refusal | client message `could only be written to 0 of the 1 minReplication nodes ... 1 node(s) are excluded`; NN DEBUG `:834` line with required = N·B, remaining = 0; INFO reason `NO_REQUIRED_STORAGE_TYPE`; no DataNode out-of-space line outside U2DN | NN refusal | `evidence-excerpt.txt` |

d0 (initial dfsUsed) = 24576 B in every U2 cluster; blocks scheduled at refusal = 0.

**Cluster tier** (capacity 268435456 B, B = 4194304; `run1/cluster/`)

| N | Run | K (files before refusal) | `DFS Remaining` at refusal | `du -sb dn` / blk files | NN `:834` DEBUG at refusal | DN out-of-space | Prediction |
|---|---|---|---|---|---|---|---|
| 1 | A | **63** | 2104903 (2.01 MB) | 266343448 / 63 | 13:02:57 `required=4194304, remaining=0` | 0 | 63; [0, 4 MiB); ≈ 266 MB |
| 8 | A | **56** | 31281103 (29.83 MB) | 236753895 / 56 | 13:07:46 `required=33554432` | 0 | 56; [28, 32) MiB; ≈ 237 MB |
| 16 | A | **48** | 65097735 (62.08 MB) | 202937263 / 48 | 13:11:56 `required=67108864` | 0 | 48; [60, 64) MiB; ≈ 203 MB |
| 32 | A | **32** | 132730999 (126.58 MB) | 135303999 / 32 | 13:14:49 `required=134217728` | 0 | 32; [124, 128) MiB; ≈ 135 MB |
| 32 → 1 | step 5 control | **+31 → 63** | 1576960 (`dfsadmin`) / 1691550 (DN JMX) | 266343448 / 63 | 13:17:26 `required=4194304` | 0 | +31 → 63; ≈ 266 MB |
| 1, headroom 1 GiB | step 6 control | **0** | 267882937 | 37494 / 0 | none (NN accepted) | 3 lines, 13:17:50: `Out of space: ... (=267882937 B) is less than the block size (=4194304 B)` | K = 0, DN-side refusal |

Every reconfiguration reported `SUCCESS: Changed property dfs.namenode.block-placement.min-blocks-for.write From: "<old>"` (`driver.out`). Every refusal text: `could only be written to 0 of the 1 minReplication nodes. There are 1 datanode(s) running and 1 node(s) are excluded in this operation.` (`put-*.err`). NN INFO reason at each refusal: `{NO_REQUIRED_STORAGE_TYPE=1}` (expected for a local writer, §3 defect 4). Configured Capacity 268435456 throughout. d0 after emptying: 24576 B for N = 1 and 8, 437929 B for N = 16 and 32 (`driver.out` "after empty").

### 4.2 Conclusion and logic

1. **Validity.** Both tiers reached the limit and refused [observed: `o24-readings.csv` REFUSED rows; `samples-*.csv` one non-zero rc each]. Fixed settings held: replication 1, B = 1 MiB / 4 MiB, considerLoad false, heartbeat 1 s, additional-available-space 0 [observed: `run1/cluster/conf/hdfs-site.xml`; U2 `start` rows `additionalAvailableSpace=0`]; cluster capacity 268435456 [observed: `cluster-run.log` "CAPACITY CHECK: OK"]; blocks scheduled 0 at every unit refusal [observed: `o24-readings.csv`]. The DataNode-side check did not bind in any N run [observed: 0 DataNode out-of-space lines before 13:17:50 in the DN log; unit lines only inside U2DN]. Valid.
2. **Readings.** No gaps. The per-put JMX samples lag one heartbeat behind (e.g. N1 last OK row shows 62 files' DfsUsed) [observed: `samples-N1.csv`]; the refusal-time records (`dfsadmin -report` and JMX after the loop) are used for the bands. d0 rose to 437929 B after the second emptying [observed: `driver.out`]; it is < 1 block and does not change any K.
3. **Matched row.** B2g "K(N) = 31, 28, 24, 16 (±1) and refusal-time remaining in [(N−1)B, NB)" — K exactly 31/28/24/16 and every remaining in band [observed: U2 rows]; with "u2Reconfigure: resumes to 31 total" [observed: U2R]. B3g "K ≈ 64 − N, refusal-time remaining in [(N−1)B, NB), du falling about 4.2 MB per +1 N" — K 63/56/48/32 exactly; remaining in band; `du` falls 29.6 MB from N 1→8 (7 × 4.23 MB), 33.8 MB 8→16, 67.6 MB 16→32 [observed: cluster records]; with "Step 5 resumes to about 63" [observed: S5 = 31 more, 63 total]. Direct disallow evidence: the `:834` DEBUG line with `required = N·B` and `remaining = 0` at each refusal [observed: NN log lines 368, 612, 831, 1001, 1167; `evidence-excerpt.txt`].
4. **Excluded rows.** K the same for every N — excluded, K spans 16–31 (unit) and 32–63 (cluster). K falls but not one-for-one — excluded, K(N) = K(1) − (N−1) exactly. DataNode refusal / no NN evidence — excluded: DN out-of-space only in the controls; `:834` line at every N refusal. U1a accepts 4095 or U1c accepts — excluded (null both). u2Reconfigure / step 5 no writes after reconfiguring — excluded (15 / 31 more). Overshoot of several blocks — excluded (exact K). Configured Capacity ≠ 256 MiB — excluded (268435456).
5. **Observed vs. inferred.** Inferred: (i) the refusals are caused by lines 828/833 and not by another NameNode check — supported by the `:834` DEBUG line (which is only logged on that branch) at the same timestamp as each refusal, and by the reconfigure controls that change only N; (ii) the INFO reason `NO_REQUIRED_STORAGE_TYPE` is the local-writer artefact of `BlockPlacementPolicyDefault.java:635/835/851` [inferred: source reading], not a different check.
6. **Deviations and gaps.** Audit amendments (§1, §3 defects 4–5) changed the cluster disk method and the evidence string, not the predictions. The unit tier restarted once after three instrument bugs (§3 defects 1–3). Appends (A3 c) and concurrent-write overshoot (A3 a, the `sleep 0` variant) were not run; the claim is about sequential full-block writes. Harness not committed to the repo (task scope).
7. **Core question.** Usage followed the constraint: stored HDFS bytes on the DataNode stopped at capacity − about N·B in both tiers, one block fewer per +1 in N (parts 1, 3), the refusal came from the `chooseStorage4Block` disallow branch (parts 3, 5), and changing only N on the same running cluster moved the stopping point (step 5, u2Reconfigure). `min-blocks-for.write` caps DataNode disk use for new blocks.

**Conclusion (one line):** B2g row 1 + u2Reconfigure positive control, and B3g row 1 + step 5 positive control — **confirmed** (both tiers).

## 5. Self-check of run 1 — AI

### 5.1 Check of run 1's conclusion

| Part | Holds? | Note (file re-read) |
|---|---|---|
| 1. Validity | yes | Re-read `run1/cluster/conf/hdfs-site.xml` (additional-available-space 0, du.reserved 259608576), `cluster-run.log` capacity check, U2 `start` rows. |
| 2. Readings | yes | `samples-*.csv`: ok counts 63/56/48/32/31/0, one failure each. |
| 3. Matched row | yes | `o24-readings.csv` `end` rows K = 31/28/24/16/31/0; NN daemon log has exactly 5 `does not have enough` lines (N1, N8, N16, N32, S5) and none for S6. |
| 4. Excluded rows | yes | DN daemon log: 3 out-of-space lines, all at 13:17:50 (step 6); unit output: only lines 317–319, inside U2DN (lines 312–437). |
| 5. Observed vs. inferred | yes | Source re-read: `BlockPlacementPolicyDefault.java:635` (local node added to `excludedNodes`), `:835` (reasons cleared), `:851` (`NO_REQUIRED_STORAGE_TYPE`). |
| 6. Deviations and gaps | yes | Amendments dated and placed before the affected tier's run 1; attempt-1 logs kept (`run1/unit-attempt1/`, `run1/cluster-setup-attempt1/`). |
| 7. Core question | yes | Both tiers: K(N) = K(1) − (N−1), real bytes (`du`, volume dir) follow, disallow branch logged, live-reconfigure controls move the cap. |

### 5.2 Run 2?

**No** — 2026-11-25. Every reading matches the prediction exactly, the conclusion rests on observed lines (the `:834` DEBUG line, block counts, `du`), the result confirms rather than refutes, and no bypass is claimed beyond the supplementary U1d(b) reading.

## 6. Run 2 — not done

## 8. Verdict — AI

**Stage-3 estimate:** positive. **Outcome class:** true positive (positive, caps).

**Claim tested:** For a DataNode receiving sequential full-block writes, the NameNode stops placing new replicas on it once its reported remaining space falls below `N × blockSize` (N = `dfs.namenode.block-placement.min-blocks-for.write`); K(N) ≈ K(1) − (N − 1), free space at refusal in `[(N−1)·B, N·B)`, and raising or lowering N at runtime moves the stopping point the same way (B1).

| Tier | Verdict | Effect on the constraint | Basis | Date |
|---|---|---|---|---|
| Unit | Confirmed — B2g "K(N) = 31, 28, 24, 16 (±1) and refusal-time remaining in [(N−1)B, NB)"; u2Reconfigure positive control resumes to 31 | caps | run 1 + self-check | 2026-11-25 |
| Cluster | Confirmed — B3g "K ≈ 64 − N, refusal-time remaining in [(N−1)B, NB), du falling about 4.2 MB per +1 N"; step 5 resumes to 63 | caps | run 1 + self-check | 2026-11-25 |

Note on scope (from A3, not tested here): the cap is NameNode admission for new blocks; appends to an existing last block and concurrent writes inside a heartbeat window are outside it. U1d(b) shows that with several storages of one type the returned storage can be one that failed line 828 (bypass (d)); the DataNode then picks the real volume.

**Feedback filed:** section D of the case file (in `case-amended.md`, with the dated amendments to B2b, B2e, B3a, B3d, B3g, B4). Not committed: this session writes outside the repo only.
