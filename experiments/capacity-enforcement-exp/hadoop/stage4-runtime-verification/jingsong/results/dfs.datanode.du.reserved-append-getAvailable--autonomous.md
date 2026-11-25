# dfs.datanode.du.reserved-append-getAvailable--autonomous — stage-4 results (queue order 28)

> **Case:** [`dfs.datanode.du.reserved-append-getAvailable--autonomous`](../../stage3-ai-deep-read/jingsong/cases/dfs.datanode.du.reserved-append-getAvailable--autonomous.md)
>
> **Status:** **verdict filed, 2026-11-25 — Confirmed — caps (unit tier and cluster tier).** Audited ≈10:40 MST before any reading; run 1 10:42–11:18 MST; self-checked; no run 2.
> **Effect on the constraint:** `caps`.
>
> **Outcome class:** **true positive** (stage-3 estimate `positive`; both tiers Confirmed, effect `caps`).
>
> **Agent:** autonomous. "§9a" = B2f/B2g (unit), B3f/B3g (cluster); runbook = B2a–B2e / B3a–B3e; feedback = section D.

Run 1 by a fresh stage-4 agent working as Jingsong, on `pc72`. Node lock `/mydata/s4/NODE-LOCK` taken 2026-11-25 10:37:22 MST
(`jingsong-h28-stage4`). Shell times below are MST; daemon and surefire log timestamps are UTC (MST + 7 h).

## 1. Before run 1 — design audit and freeze (written 2026-11-25 before any reading)

| Field | Content |
|---|---|
| **Case-file version** | `hadoop/stage3-ai-deep-read/jingsong/cases/dfs.datanode.du.reserved-append-getAvailable--autonomous.md`, last commit `cd9e1cded`, repository HEAD `8bd1dfb31`. sha256 at filing `b3179ff4e60336452c247ab65782a6540d890bad87c2fb1861492d07531e48c2` = `_INDEX.md` §4 = the stage-3 copy in this folder. **Frozen (amended) version:** `case-amended.md` with D1-1 … D1-8, sha256 **`74d347aaa36afb36ea5ee17df91816aa61bb2e5aebb5dedf86b6d7289c93a196`**. Frozen text hashes (sha256 of `sed -n '/^\*\*B2f\./,/^\*\*B2h\./p'` and the B3 equivalent, first 16 hex): **B2f–B2h `ed2e6cc40af0dd27`** (filed `4fbbfe621a8c5c76`; changed by D1-3), **B3f–B3h `21da4ff95510fe2c`** (filed `b162d976ab40320c`; changed by D1-7, D1-8). B1 is unchanged. Only section D may change after this point (feedback). **Later versions:** after D2-1 (unit runbook defect, placed in B2c; B2f–B2h hash unchanged) the whole-file sha256 was `c1b5213f6002b49c05f8bcf8ea50da14821461205dd19cf21530fb3b95d55077`, the version both attempt-2 tiers ran against; with the D3-1 note and the stage-4 summary in section D it is now `9dcc07a69a7f2a5ce24bd2fb4dc7b871830b8ac82f715444999cb3158c39d689` (B2f–B2h `ed2e6cc40af0dd27`, B3f–B3h `21da4ff95510fe2c`, unchanged since the freeze). |
| **Harness** | `harness/` in this folder (written in step 1, listed in §2 with md5s); on the node under `$RUN/harness/`. Not committed (output outside the repo). |
| **Tiers and values** | Unit (B2): R = 0 control and `R(δ) = T − D − (B − L) − δ`, δ ∈ {−4 MiB, −256 KiB, +256 KiB, +4 MiB}; client-path variant at δ = ±4 MiB; B = 16 MiB, L = 1 MiB, 2 GiB ext2 image. Cluster (B3): R = 0 calibration/control, boundary δ = ±4 MiB, fills a = 48 MiB and 80 MiB; same image size, pseudo-distributed NN + DN on default ports (free on `pc72`, `ss -ltn`). |
| **Audit bottom line** | **Ready after amendments**, 2026-11-25 |

### 1.1 Design audit

| Group | Check | Rating | Note (section checked) |
|---|---|---|---|
| A | constrained quantity is disk bytes | Met | A2/B1: HDFS bytes on one volume; the operand `getAvailable()` = `T − R − dfsUsed − reservedForReplicas` (A2), real usage by `du -sb dn` and `df` (B3d). |
| A | knob varied, ≥ 3 values incl. default | Met | Unit: R = 0 (default) + four R values; cluster: R = 0 + two boundary + two fill values (B2b, B3b). R is positioned relative to usage (T − D − …), which is the only way to reach the boundary on a fixed image. |
| A | real resource measured | Partly → Met | Unit tier reads the operand, outcome, reservation and replica dir (the mechanism level), not disk bytes; the cluster tier measures `du -sb dn` and `df` per append (B3d). Gap named: acked-but-unfinalized bytes are not observable (B3d), zero between sequential appends. |
| A | usage driven to the limit and past it | Met | Fills (B3c) append until the first refusal; boundary pairs straddle it. Workload count too small for both fills as written → D1-4. |
| B | each step says what it establishes | Met | B2h/B3h say what each control and run establishes. |
| B | prediction in numbers / relation | Partly → Met | B2f table and B3f numbers. B3f's "differ by ≈ 32 MiB (the R difference)" contradicts step 7 (R_F(80) is computed after fill 48's appends, so the R difference is ≈ 65 MiB): arithmetic error, D1-7 keeps the stated rule ("the R difference") with the right number. "One 'Insufficient space' line" does not match the DataNode's logging (INFO + ERROR line per refusal): D1-6. |
| B | every plausible outcome has a row | Partly → Met | Missing: unit R = 0 control failure (D1-3 row), fill that never refuses (D1-8 row). Exceeds-limit (`du > T − R_F`), flat-across-R, other-check-fired, invalid setup rows exist (B2g, B3g). |
| B | confirmation needs ceiling-follows-knob and disallow evidence | Met | B3g "boundary and fill predictions hold" needs the stop to move with R and the "Insufficient space for appending to" message (B3f, B3h); unit tier asserts the `DiskOutOfSpaceException` per δ. |
| B | alternatives and their controls | Met | NN placement / volume choosing (other checks) ruled out by the message (B3h); outside writers by a dedicated image; double count (A3b) by the 6 s sleep and its own B3g row. |
| C | a human can follow it | Met | B1 + B2f/B3f tables. |
| C | an AI can run it without re-deriving | Partly → Met | Fill calibration (when to read `D_F`, re-check) under-specified → D1-5; client-path outcome and replica-dir observation under-specified → D1-3. |
| C | knob, values, workload, commands, observables exact | Met | B2b–B2d, B3b–B3d give exact values and commands. |
| D | prerequisites exist or are listed | Partly → Met | sudo, loop mount, rsync, curl, python3 present on `pc72`; JDK 8, Maven 3.6.3, built 3.4.2 distribution at `/mydata/jingsong-s4/hadoop-base` (node table row `pc72`). ext4 `-m 0` image: `stat -f` Free 514516 vs Available 510420 (ext4 reserved clusters), so the design's own requirement fails → ext2 `-m 0` (Free 515284 = Available 515284), D1-1. Build/`install` into shared `~/.m2` replaced by offline module test, D1-2. |
| D | workload arithmetic reaches the limit | Partly → Met | Unit: R ≈ 2 GiB on a 2 GiB image, A aimed at 15 MiB ± δ. Cluster: 33 + 65 appends need ≈ 100 files, 80 seeded → 120 (D1-4); ≈ 125 MiB of data on a 2 GiB image; ≈ 100 appends × (6 s + client) ≈ 15–20 min. |
| D | load-bearing citations spot-checked | Met | Against `systems/hadoop/source` (clean, `rel/release-3.4.2`): `FsVolumeImpl.java:1262-1296` (`bytesReserved = estimateBlockLen − numBytes`, check at 1265, reserve at 1295), `:474-482` (`getAvailable`), `:434-455` (`getCapacity`), `:514-521` (`getRemainingReserved`), `:538-545` (`getDfAvailable` pkg-private, `getReservedForReplicas` public), `:556-558` (`getReserved` pkg-private); `FsDatasetImpl.java:1379-1410` (length check against `expectedBlockLen`, then `b.getNumBytes()` as estimate), `:867-879` (`getReplicaInfo` by id + GS), `:3297-3325` (VolumeInfo `freeSpace` = `getAvailable()`); `DataStreamer.java:1917-1918` (`blockCopy.setNumBytes(stat.getBlockSize())`); `BlockReceiver.java:233-234, 282-284`; `BlockPoolSlice.java:338-382` (check interval 0 → `du` at start), `:445-454` (`incDfsUsed(full length + meta)`: the A3b double count); `DF.java:85-97`; `MiniDFSCluster.java:243-258` (Builder with base dir). As cited. |

| # | Recommendation | Applied? | Why |
|---|---|---|---|
| 1 | ext2 `-m 0` image (Free == Available) | D1-1, 2026-11-25 | the design's own precondition fails on ext4 here |
| 2 | copy-source.sh, offline module test, no `install` to shared `~/.m2` | D1-2 | node rules |
| 3 | define replica-dir, `A_after`, client-path outcome; R = 0 failure row | D1-3 | unambiguous reading; missing outcome |
| 4 | seed 120 fill files | D1-4 | workload did not reach the second limit |
| 5 | fill calibration rule | D1-5 | step 6/7 under-specified |
| 6 | "≥ 1 Insufficient-space line per refusal" | D1-6 | DataNode logs each refusal twice |
| 7 | stop-point difference = R difference (≈ 65 MiB) | D1-7 | arithmetic error in B3f, reading-independent |
| 8 | row for a fill that never refuses | D1-8 | missing outcome |
| 9 | concurrent-writer overshoot (A3a/A3c) is not exercised | left for stage 3 | sequential appends only; the bypass claims stay untested |
| 10 | the default R = 0 cap (whole `/mydata`) is not filled | left for stage 3 | not allowed on the shared node; R = 0 is run as a control on the 2 GiB image |

## 2. Environment

| Field | Run 1 |
|---|---|
| Date | 2026-11-25, 10:37–(end below) MST |
| Node | `pc72` = `node2.jason92-326665.misconfiguration-pg0.cloudlab.umass.edu` (matches the environment.md node table), 40 cores, 125 GiB |
| OS and kernel | Ubuntu 22.04, `5.15.0-203-generic` |
| JDK / build tool | `/usr/lib/jvm/java-8-openjdk-amd64`, OpenJDK `1.8.0_514`; Maven 3.6.3 offline, modules from `~/.m2` (node build 2026-11-24). Ant not used (Hadoop). |
| Local source copy | `copy-source.sh` from repository HEAD `8bd1dfb31` → `$RUN/src` (baseline `rel/release-3.4.2`; `git status` shows only the added test class, `run1/unit/unit-run.log`) |
| Distribution (cluster) | `/mydata/jingsong-s4/hadoop-base/hadoop-dist/target/hadoop-3.4.2` copied to `$RUN/cluster/hadoop` |
| Case-file commit / harness | case file `cd9e1cded`, frozen as in §1; harness not committed (in `harness/` here; md5 on the node: `TestAppendDuReservedBoundary.java` `784d6de0`, `unit-run.sh` `c89fa8b2`, `cluster-run.sh` attempt 1 `79f9221d`, attempt 2 `d17ca724`) |
| Storage for node data | 2 GiB sparse image, `mkfs.ext2 -q -F -m 0`, loop-mounted (`stat -f`: Total 515290, Free 515284 = Available 515284 blocks of 4 KiB; `T = 2,110,627,840` B); one fresh image per tier: `$RUN/unit/vol.img`, `$RUN/cluster/vol.img`. NameNode dir, logs and conf off the image. |
| Full logs | `/mydata/jingsong-s4/dfs.datanode.du.reserved-append-getAvailable-run1/logs/` on `pc72` (`$RUN` below) |

## 3. Runbook defects

| # | Run | Step | Problem | Fix | Decision (date) | Case-file change |
|---|---|---|---|---|---|---|
| 1 | unit attempt 1 (10:42–10:43) | B2c, restart before δ = −4 MiB | `DFSTestUtil.getFirstBlock` threw `BlockMissingException … No live nodes contain current block` before any append: `waitActive()` does not wait for the block report (`run1/unit-attempt1/surefire-summary.txt`). The other 6 rows ran and matched (`run1/unit-attempt1/o28-readings.csv`). | `DFSTestUtil.waitReplication(fs, p, 1)` after each restart | D2-1, 2026-11-25 10:44; B2f/B2g unchanged (hash `ed2e6cc4…` before and after); unit tier restarted (attempt 2, 10:45) | D2-1 in B2c |
| 2 | cluster attempt 1 (10:47–10:58) | B3e step 3 (harness) | The script's DataNode-log counter printed `0` twice when there was no match yet; the arithmetic error aborted the rest of step 3 after the δ = −4 MiB append (rc 1): no readings row, no `fsck`, no lease recovery on `/t/fA`, which the R = 0 control later appends to. The restart wait (`hdfs dfs -cat /t/fA`) also stalled 4.5 min on the open file. (`run1/cluster-attempt1/`) | counter fixed; restart wait = DataNode JMX `BPServiceActorInfo` RUNNING with a block report < 60 s old | D3-1, 2026-11-25 10:59; harness only, no case text changed; cluster tier restarted from the beginning on a fresh image (attempt 2, 10:59) | note in section D |

## 4. Run 1

**Scope:** unit tier, all five B2f rows plus the client-path pair (attempt 2, 10:45–10:46 MST); cluster tier, boundary pair,
R = 0 control and both fills (attempt 2, 10:59–11:18 MST). **Command logs:** `run1/unit/unit-run.log`,
`run1/cluster/cluster-run.log`; readings `run1/unit/o28-readings.csv`, `run1/cluster/readings.csv` (one row per append),
mechanical check of B3f `run1/cluster/analysis.txt` (`harness/analyze-cluster.py`).

### 4.1 Readings

**Unit tier.** Surefire `Tests run: 7, Failures: 0, Errors: 0, Skipped: 0` (`run1/unit/test-summary.txt`). Calibration
(`calib` row): `T = getCapacity()` at R = 0 = **2,110,627,840**, `D = getDfsUsed()` = **1,097,728**, seeded replica
`finalized`, 1,048,576 B; derived non-DFS 2,211,840 B (≪ R). After every restart `dfsUsed` = 1,105,920 = D + 8,192, so every
A is `15 MiB + δ − 8,192` (B2f "± few KiB"; far inside B2g's 64 KiB).

| Row | R | A (B2f expected) | Outcome | `reservedForReplicas` after | `A − A_after` | Replica after | Evidence |
|---|---|---|---|---|---|---|---|
| R = 0 control | 0 | 2,107,305,984 (≈ T − D) | handler returned | 15,728,640 | 15,728,640 | `rbw`, 1,048,576 | `o28-readings.csv` `ctrlR0,post` |
| δ = −4 MiB | 2,097,995,776 | 11,526,144 (≈ 11,534,336) | `DiskOutOfSpaceException: Insufficient space for appending to FinalizedReplica, blk_1073741825_1001, FINALIZED` | 0 | 0 | `finalized`, 1,048,576 | `dM4M,post` |
| δ = −256 KiB | 2,094,063,616 | 15,458,304 (≈ 15,466,496) | same exception | 0 | 0 | `finalized`, 1,048,576 | `dM256K,post` |
| δ = +256 KiB | 2,093,539,328 | 15,982,592 (≈ 15,990,784) | handler returned | 15,728,640 | 15,728,640 | `rbw`, 1,048,576 | `dP256K,post` |
| δ = +4 MiB | 2,089,607,168 | 19,914,752 (≈ 19,922,944) | handler returned | 15,728,640 | 15,728,640 | `rbw`, 1,048,576 | `dP4M,post` |
| client δ = −4 MiB | 2,097,995,776 | 11,526,144 | client `IOException: All datanodes […] are bad. Aborting...`; DataNode `opWriteBlock … DiskOutOfSpaceException: Insufficient space for appending to …` (INFO, DataXceiver:952) + the ERROR stack line; 1 `Appending to` attempt | 0 | — | `finalized`, 1,048,576; file length 1,048,576 | `cliM4M,post`, `run1/unit/dn-append-lines.txt` |
| client δ = +4 MiB | 2,089,607,168 | 19,914,752 | no exception; no `Insufficient` line after 17:45:52 UTC | 0 (finalized) | — | `finalized`, 2,097,152; file length 2,097,152 | `cliP4M,post`, `dn-append-lines.txt` |

Every row: `refused == (A < 15,728,640)` (`match=true`, 7/7). No `Out of space` / `could only be written to` line in the test output (`run1/unit/unit-run.log`).

**Cluster tier** (attempt 2). Calibration: `T` (df size) = **2,110,627,840**, `D` (usedSpace after seeding 122 files) =
**129,966,080**, non-DFS (df used − `du -sb dn`) = 1,034,993 B (`cluster-run.log` CALIB/STATE lines). `s` observed =
**1,056,768** B per append (= 1 MiB + 8 KiB) for both `du -sb dn` and `freeSpace` (before-to-before).

| Run | R | Observable | Reading | Prediction (B3f) | Evidence |
|---|---|---|---|---|---|
| boundary δ = −4 MiB (`/t/fA`) | 1,969,127,424 | freeSpace before | 11,530,240 (target 11,534,336, −4,096) | ≈ 11.0 MiB < 15,728,640 | `readings.csv` row `bM4M` |
| | | exit / DN lines / attempts | rc 1; 2 `Insufficient space for appending to` lines (INFO + ERROR), 1 `Appending to` | non-zero; ≥ 1 line (D1-6) | `bM4M` row; `dn-append-lines.txt` 18:01:11 UTC |
| | | `du -sb dn`, usedSpace, `reservedSpaceForReplicas` | 128,972,070 → 128,972,070; 129,970,176 → 129,970,176; 0 | unchanged (± 4 KiB); 0 | `bM4M` row |
| | | file length | fsck printed nothing (file open for write until `recoverLease`, which succeeded); the later R = 0 append took `/t/fA` to exactly 2,097,152 = L + 1 MiB | 1,048,576 | `cluster-run.log` (after-bM4M, ctrlR0 fsck) |
| boundary δ = +4 MiB (`/t/fB`) | 1,960,734,720 | freeSpace before / exit | 19,922,944 (diff 0) / rc 0, 0 `Insufficient` lines | ≈ 19.0 MiB / success | `bP4M` row |
| | | fsck length; `du` growth | 2,097,152; +1,056,768 | 2,097,152; ≈ 1 MiB + 8 KiB | `bP4M` row, `cluster-run.log` |
| control R = 0 (`/t/fA`) | 0 | exit; length | rc 0; 2,097,152 | success | `ctrlR0` row |
| fill a = 48 MiB | R_F = 1,928,212,480 | successes; first refusal | **33**, at `/t/g034` (2 `Insufficient` lines) | 33 ± 2; the message | `analysis.txt` fill48 |
| | | freeSpace at the stop | 15,458,304 ∈ [14,671,872, 15,728,640) | [15 MiB − s, 15 MiB) | `fill48,/t/g034` row |
| | | `du -sb dn` at the stop | 165,958,950 ∈ [165,638,144, 167,735,296]; max over the fill 165,958,950 ≤ T − R_F = 182,415,360 | ∈ [T − R_F − 16 MiB, T − R_F − 14 MiB] | `analysis.txt` |
| | | df avail at the stop | 1,943,629,824 ≥ R − nonDfs = 1,927,173,414 | ≥ R − nonDfs | `analysis.txt` |
| fill a = 80 MiB | R_F = 1,859,784,704 | successes; first refusal | **65**, at `/t/g100` (2 lines) | 65 ± 2 | `analysis.txt` fill80 |
| | | freeSpace at the stop | 15,196,160 ∈ [14,671,872, 15,728,640) | as above | `fill80,/t/g100` row |
| | | `du -sb dn` at the stop | 234,648,870 ∈ [234,065,920, 236,163,072]; max 234,648,870 ≤ T − R_F = 250,843,136 | as above | `analysis.txt` |
| | | df avail at the stop | 1,874,939,904 ≥ 1,858,745,638 | as above | `analysis.txt` |
| fills compared (D1-7) | | du(stop 80) − du(stop 48) vs R_F(48) − R_F(80) | 68,689,920 vs 68,427,776, diff 262,144 | the R difference ± 2 MiB | `analysis.txt` |
| all 103 appends | | `refused == (freeSpace before < 15,728,640)` | 0 mismatches; every refusal has ≥ 1 `Insufficient` line, no success has one; 1 `Appending to` per append; 0 `Out of space` / `could only be written to` | — | `analysis.txt`, `dn-append-lines.txt`, `append-errors.txt` |

### 4.2 Conclusion and logic

1. **Validity.** Both tiers reached the limit: the unit operand was placed 8 KiB below each target (± 4 MiB and ± 256 KiB on both sides of 15,728,640) [observed: `unit/o28-readings.csv`]; the cluster fills were driven to a refusal and stopped there [observed: `cluster/readings.csv`]. Hold-fixed settings: ext2 image with Free == Available [observed: `unit-run.log`, `cluster-run.log` `stat -f` lines]; R read back as `reserved` / `reservedSpace` equal to the configured value in every start [observed: `pre` rows; `bM4M`…`fill80` rows, column R = VolumeInfo `reservedSpace`]; non-DFS usage 2.2 MB (unit) and 1.0 MB (cluster), ≪ R [observed: `calib` row, CALIB line]; one volume, sequential appends, 6 s du sleep [observed: `cluster-run.log` timestamps]. Valid.
2. **Readings.** Nothing contradicts. Two side observations: every unit A sits 8,192 B below the target (the restarted `du` sees 8 KiB more than the calibration `du`), inside the tolerance [observed]. After each successful cluster append, `usedSpace` rose by 2,113,543 (= the full 2 MiB block + 16,391-byte meta) and `freeSpace` fell by the same amount until the next `du` refresh, after which the step is 1,056,768 [observed: `free_after` vs next `free_before` in `readings.csv`, e.g. g033: 14,401,529 → 15,458,304]: the A3b double count, conservative, absorbed by the 6 s sleep.
3. **Matched rows.** Unit, B2g row 1: "Outcome matches `A < B − L` in all rows, and the table above holds" → **claim confirmed at the mechanism level**: 7/7 outcomes match; A within 8 KiB of B2f; `reservedForReplicas` 15,728,640 after each success and 0 after each refusal; replica `rbw` on success and `finalized` with length L on refusal; `A − A_after` = 15,728,640 / 0 [observed: `unit/o28-readings.csv`]. Cluster, B3g row 1: "Boundary and fill predictions hold" → **Confirmed: du.reserved, through `getAvailable()`, caps HDFS bytes reached by appends**: every B3f item holds (table above), including N = 33 and 65 and the stop-point shift equal to the R difference within 0.25 MiB [observed: `cluster/analysis.txt`, `readings.csv`].
4. **Excluded rows.** Unit: success with A < 15,728,640: none (dP256K at 15,982,592 is the lowest success); failure with A ≥ 15,728,640: none (dM256K at 15,458,304 is the highest refusal); positioning error > 64 KiB: none (8 KiB); A ≈ 0: no; `reservedForReplicas` ≠ B − L after success: no; other message: no `Out of space` / NameNode placement line; R = 0 control fails (D1-3 row): no [observed: `unit/o28-readings.csv`, `unit-run.log`]. Cluster: append succeeds with freeSpace < 15,728,640: 0 of 103; stop not moving with R: moved by 68,689,920 vs R difference 68,427,776; other check fired: 0 `Out of space` / `could only be written to`; N about half (double count): no, N exact; `du` at the stop > T − R_F: no (max 165,958,950 < 182,415,360; 234,648,870 < 250,843,136); freeSpace ≈ 0 regardless of R: no; R = 0 control fails: no; D1-8 (files exhausted): no, both fills refused [observed: `analysis.txt`].
5. **Inferred statements the conclusion depends on.** (a) That the refusal came from `FsVolumeImpl.java:1265` and not another `DiskOutOfSpaceException` site: inferred from the message text `Insufficient space for appending to`, which only that line produces (grep of the pinned source finds the string once) [inferred: source]. (b) That a failed cluster append wrote nothing: `fsck` did not print the open file; inferred from `du`, `usedSpace` unchanged and the later R = 0 append taking `/t/fA` to exactly L + 1 MiB [inferred from observed readings]. (c) In the cluster tier `freeSpace` is read 1 s–6 s before the check; with sequential appends and no other writer nothing changes in between (the unit tier reads A in the same thread just before the call and shows the same rule).
6. **Deviations and gaps.** D1-1 ext2 instead of ext4 (environment); seeding by one `-put` of 122 local copies instead of 122 separate `-put` commands (same files, sizes and block size; `fsck` 1,048,576 B, 1 block); the unit dataset and client-path rows ran in one surefire invocation (B2e steps 2–3 merged); B3d's `find -newer` replica-location check was not scripted (covered by part 5b). Attempt 2's full daemon logs were deleted at cleanup by mistake; the DataNode append/refusal lines (`dn-append-lines.txt`), client errors and per-append readings had been copied first; attempt 1's daemon logs are kept on the node. Not exercised: concurrent writers (A3a, A3c overshoots), RBW recover-append (A3f), the default R = 0 cap on the whole `/mydata`.
7. **Core question.** B1's logic: (i) the check refuses exactly when `getAvailable() < B − L` — unit 7/7 and cluster 103/103 [parts 3, 4]; (ii) `getAvailable()` falls one-for-one with R — unit A = T − R − D' to 8 KiB in every row, cluster freeSpace hit each target within 4 KiB [part 1]; (iii) so appends stop at a ceiling `T − R − ~15 MiB` that moves with R — fills stop with `du` inside the predicted 2 MiB window and the two stop points differ by the R difference [part 3]. Usage follows the constraint and the constraint caps HDFS bytes reached by appends.

**Conclusion (one line):** unit B2g row 1 — **confirmed**; cluster B3g row 1 — **confirmed**.

## 5. Self-check of run 1 — AI

### 5.1 Check of run 1's conclusion (raw files re-opened 2026-11-25 ≈11:25 MST)

| Part | Holds? | Note (file re-read) |
|---|---|---|
| 1. Validity | yes | `stat -f` lines in `unit-run.log` (Free 515284 = Available 515284) and `cluster-run.log`; `reserved=` in each unit `pre` row equals its R; cluster column R is VolumeInfo `reservedSpace` read before each append. |
| 2. Readings | yes | `free_after` (14,401,529) vs next `free_before` (15,458,304) for g033/g034 in `readings.csv` shows the transient double count; it does not affect any refusal decision (every refusal's `free_before` was read after the 6 s sleep). |
| 3. Matched row | yes | `unit/test-summary.txt` 7/0/0/0; 7 `summary` rows `match=true`; `dM4M`/`dP256K` `post` rows re-read (0 vs 15,728,640 reservation, `finalized` vs `rbw`). `readings.csv` rows bM4M, bP4M, ctrlR0, g001, g033, g034, g035, g099, g100 re-read by hand: per-label counts fill48 34 rows / 1 refusal, fill80 66 / 1. |
| 4. Excluded rows | yes | `grep -c 'Out of space\|could only be written'` = 0 in `dn-append-lines.txt` and `append-errors.txt`; max `du` per fill below T − R_F (`analysis.txt`). |
| 5. Observed vs inferred | yes | (a) `grep -rn "Insufficient space for appending to"` in the pinned source: only `FsVolumeImpl.java:1266`. (b) holds from the `bM4M` and `ctrlR0` rows and the ctrlR0 fsck line (2,097,152). |
| 6. Deviations and gaps | yes | listed; none touches a predicted quantity. The deleted daemon logs limit re-checks to the copied excerpts. |
| 7. Core question | yes | the three steps of B1 map to parts 3, 1 and 3; both tiers confirmed. |

### 5.2 Run 2?

**No** (2026-11-25). The conclusion rests on observed readings that match exact or tightly bounded predictions in both tiers, with
the disallow message observed at every refusal; it neither refutes the case nor confirms a bypass.

## 6. Run 2 — fresh AI session (optional)

Not done.

## 8. Verdict — AI

**Stage-3 estimate:** positive. **Outcome class:** **true positive** (estimate `positive`; both tiers Confirmed, effect `caps`).

**Claim tested (B1):** a DataNode refuses an append to a finalized replica exactly when the volume's `getAvailable()` is below
`blockSize − replicaLen`, and `getAvailable()` falls one-for-one as `dfs.datanode.du.reserved` rises, so sequential appends stop
when HDFS bytes reach about `total − R − (blockSize − replicaLen)`, and the stop point moves by −1 byte per byte of R.

| Tier | Verdict | Effect on the constraint | Basis | Date |
|---|---|---|---|---|
| Unit | **Confirmed** (B2g row 1: outcome matches `A < B − L` in all rows, table holds) | caps | run 1 + self-check | 2026-11-25 |
| Cluster | **Confirmed** (B3g row 1: boundary and fill predictions hold) | caps | run 1 + self-check | 2026-11-25 |

**Deciding numbers:** unit refusals at A = 11,526,144 and 15,458,304, successes at 15,982,592 and 19,914,752 (boundary
15,728,640); cluster fills 33 and 65 successes (predicted 33 ± 2, 65 ± 2), stop `freeSpace` 15,458,304 and 15,196,160, stop
`du` 165,958,950 and 234,648,870 (difference 68,689,920 vs R difference 68,427,776).

**Positive control:** not required (positive-estimate file); the R = 0 controls succeeded in both tiers.

**Feedback filed:** section D of `case-amended.md` (D1-1…D1-8, D2-1, D3-1 and the stage-4 summary). To file in the repository:
copy `case-amended.md` over the case file; this file to
`hadoop/stage4-runtime-verification/jingsong/results/dfs.datanode.du.reserved-append-getAvailable--autonomous.md`; `harness/` to
`…/harness/dfs.datanode.du.reserved-append-getAvailable--autonomous/`; `run1/` to `…/results/dfs.datanode.du.reserved-append-getAvailable--autonomous/run1/`;
`_INDEX.md` row 28 (stage 4 `Confirmed — caps (unit + cluster); TP`) and its §4 sha256; `queue.csv` order 28.

**Findings beyond the verdict.**
- A3b double count confirmed at runtime: after each append, `dfsUsed` grows by the whole new block length (+2,113,543 for a 2 MiB block) until the next `du` refresh, so `getAvailable()` is understated by the pre-append length for up to `fs.du.interval` (default 10 min). Appends in that window are refused early (conservative, not a leak); with a 128 MiB block and the default interval this could refuse appends well before the reserve is reached.
- ext4 loop images keep 4096 reserved clusters (16 MiB) even with `-m 0` (Free ≠ Available), which shifts any `DF.getAvailable()`-based operand; ext2 `-m 0` gives Free == Available. Worth a line in `case-notes.md` (environment lessons) for disk-limit cases.
- `MiniDFSCluster.waitActive()` returns before the restarted DataNode's block report; tests that read a file right after a restart need `DFSTestUtil.waitReplication`.
- Not exercised (left for stage 3 / a later design): concurrent-writer overshoot (A3a/A3c) and RBW recover-append without a check (A3f).

**Cleanup and what stays on `pc72`:** no NameNode, DataNode, surefire, Maven or driver process of this run left (checked
11:25 MST with `ps -u jason92 … awk`); ports 9000/9870/9864/9866/9867 free; both loop images unmounted and deleted (no loop
device left); driver PID file removed; source copy, test data and cluster data deleted. Kept:
`/mydata/jingsong-s4/dfs.datanode.du.reserved-append-getAvailable-run1/` (2.1 MB: `logs/` with unit, unit-attempt1,
cluster, cluster-attempt1 incl. its daemon logs, and `harness/`). Node lock released at the end.
