# dfs.datanode.du.reserved-doChooseVolume-mostAvailableAmongLowVolumes--autonomous — stage-4 results (queue order 27)

> **Case:** [`dfs.datanode.du.reserved-doChooseVolume-mostAvailableAmongLowVolumes--autonomous`](../../stage3-ai-deep-read/jingsong/cases/dfs.datanode.du.reserved-doChooseVolume-mostAvailableAmongLowVolumes--autonomous.md)
>
> **Status:** **verdict filed 2026-11-25 — unit Confirmed, cluster Confirmed — caps** (K1c concurrency sub-test Not confirmed: observable defect)
>
> **Outcome class:** **true positive** (estimate `positive`; both tiers Confirmed, effect `caps`)
>
> **Agent:** autonomous. "§9a" = B2f/B2g (unit) and B3f/B3g (cluster); "§9b–§9e" = B2a–B2e / B3a–B3e; feedback = section D.

Run 1 by a fresh stage-4 agent working as Jingsong, on `pc82`. Node lock `/mydata/s4/NODE-LOCK` taken
2026-11-25 10:26:48 MST (`jingsong-h27-stage4`). Output kept outside the repository in `~/writeup-hadoop/out/o27/`
(this file, `case-amended.md`, `harness/`, `run1/`).

## 1. Before run 1 — design audit and freeze (2026-11-25, before any reading)

| Field | Content |
|---|---|
| **Case-file version** | Filed file `hadoop/stage3-ai-deep-read/jingsong/cases/dfs.datanode.du.reserved-doChooseVolume-mostAvailableAmongLowVolumes--autonomous.md`, last commit `cd9e1cded`, repository HEAD `8bd1dfb31`; sha256 at filing `7ee9f5a8…5875681`, equal to `_INDEX.md` §4 and to the stage-3 copy in `o27/`. **Frozen version** = `case-amended.md` after the audit's amendments D1-1 to D1-5: sha256 **`ca1a80837d5d07d5d034b6d6e1cff6fe97c2ae625a011436dffa1a3916152d93`** (copy: `run1/case-frozen-ca1a8083.md`). Text hashes (sha256 of the `sed -n` ranges, first 16 hex): `**B2f.`–`### B3.` **`29bea5d3bd69c0c6`** (unchanged from filing); `**B3f.`–`**B4.` **`56ad7c2abe1e1a5a`** (filed `183b6632d40eb7ac`; the only change is the D1-5 row and note). B1 and every predicted number are unchanged. Only section D may change after this point (feedback); after the result was added to section D the file's sha256 is `9e0b66af…b1281`, and sections A–C are byte-identical to the frozen copy (diff checked). |
| **Harness** | `harness/` (not committed; outside the repository): `TestDuReservedAvailableSpacePlacement.java` (the B2d test plus D1-2's two columns), `unit-run.sh`, `cluster-run.sh`, `parse-unit.py`, `selfcheck.py` (see §2 for checks). |
| **Tiers and values** | Unit (B2): R ∈ {0, 512 MiB, 960 MiB, C0−B, C0−B+1} at f = 0.0, T = 1 MiB; R ∈ {0, 512 MiB} at f = 0.75; R = 512 MiB at T = 10 GiB; B = 100 MiB, C0 = 1 GiB, C1 = 3 GiB (mocked DF). Cluster (B3): K1 (b0/b1 = 1 GiB/3 GiB per-dir reserve), K2 (512 MiB/2 GiB), K3 (global reserve, 1 GiB each, T = 10 GiB), K1c (K1 config, 8 concurrent 1000 MiB writers, 3 repetitions); B = 100 MiB, f = 0.0, T = 1 MiB except K3. |
| **Audit bottom line** | **Ready after amendments** — 2026-11-25 |

### 1.1 Design audit

| Group | Check | Rating | Note (section checked) |
|---|---|---|---|
| A. Core question | constrained quantity is memory or disk bytes | Met | Disk bytes of HDFS block + meta files per volume (A2, B3d `find … blk_*` sums); unit tier uses the reservation counter, cluster tier the real files. |
| A. Core question | knob varied, ≥ 3 values incl. default | Met | Unit: R = 0 (default), 512 MiB, 960 MiB plus two boundary values (B2b). Cluster: two per-dir budget pairs (K1, K2) and a global-key run (K3); the default (R = 0) is not run at cluster tier (it would let HDFS fill the volume's whole file system); the unit tier's U-R0 covers it. Recommendation R1 (not applied). |
| A. Core question | real resource measured, not only the counter (gap named) | Met | Unit names the gap (B2d "Not observable: real disk bytes"); cluster measures `blk_*` bytes, block counts and `du -sb`, plus JMX `freeSpace` (B3d). |
| A. Core question | usage driven to the limit and past it | Met | Unit: 100 steps × 100 MiB ≫ any budget (B2c). Cluster: 45 puts (4.5 GiB) against 4 GiB (K1), 2.5 GiB (K2), 2 GiB (K3); K1c 80 blocks vs about 40 (B3c). |
| B. Logic | each step says what it establishes | Met | B2e/B3e steps plus B2h/B3h controls (reserve landed, line 166 removed in `_bal`/K3, routing order irrelevant in `f75`). |
| B. Logic | prediction stated in numbers or a clear relation | Met | B2f gives exact step ranges, exception texts and final values; B3f exact put ranges and byte totals (± 1 MiB on free space). Arithmetic re-done: U-R0 10/30, fail 41 at 75,497,472; U-R512 5/25, fail 31 at 62,914,560; U-R960 0/21, fail 22 at 67,108,864; U-EQ1 0/21, fail 22 at 104,857,599; K1 n0 = 10, n1 = 30 (b1 − 29·S = 156,598,069 > B, b1 − 30·S = 50,921,262); K2 5/20 (b0 − 4·S = 114,163,684); K3 10/10. |
| B. Logic | every plausible outcome has a conclusions row with its evidence | Partly → Met | B2g/B3g cover over-admission, wrong routing, flat usage, knob not landed, early failure, and the line-166-only-routes control. K1c had a gap between the `d0` bound (7·S) and the all-volume bound (8·S) and no overshoot definition: D1-5. Any other unmatched reading is "Not confirmed (no matching row)". |
| B. Logic | confirmation needs ceiling-follows-knob and direct disallow evidence | Met | Unit: counts follow R and the `DiskOutOfSpaceException` text plus "from high" DEBUG lines at each re-route (B2f bullets). Cluster: counts/bytes follow budgets and DEBUG "from high" lines on puts 11–40 (B3f). |
| B. Logic | alternative explanations and their controls | Met | B2h/B3h: DF mock (host noise), `_bal`/K3 (line 166 absent), `f75` (order), JMX `reservedSpace` (knob landed), re-format (carry-over), heartbeat 1 s + 3 s sleep (NameNode staleness). |
| C. Specific | a human can follow it from the intro and §9a | Met | B1 states the claim and the refuted-if clauses; B2f/B3f tables. |
| C. Specific | an AI can run §9b–§9e without re-deriving the code path | Partly → Met | The test source is given in full; B2d asks for `getReservedForReplicas()` but the source omits it (D1-2). The NameNode refusal gate for the first failed put is not stated (D1-4 adds the log needed to see it). |
| C. Specific | knob, values, workload, commands, observables, sampling, stop conditions exact | Met | Keys, byte values, commands, ports and the per-dir key form (B3a/B3b) are exact. |
| D. Runnable | harness and environment prerequisites exist or are listed | Partly → Met | B2a's `~/hadoop-3.4.2` and `install` replaced by the node's copy script and `~/.m2` (D1-1). Node rule: disk-capacity tests on a size-limited volume (D1-3, 12 GiB loop ext4). |
| D. Runnable | workload arithmetic reaches the limit (data, time, disk, memory) | Met | ≤ 4.9 GiB block data on a 12 GiB loop fs (≈ 11.2 GiB usable), 1.1 GiB source files on `/mydata` (705 GB free); 45 puts × ≈ 6 s ≈ 5 min per run; two 1 GiB-heap JVMs on a 125 GiB node. |
| D. Runnable | load-bearing citations spot-checked against the pinned source | Met | `systems/hadoop/source` clean. Checked: `AvailableSpaceVolumeChoosingPolicy.java:108-113` (inner RR with `new`, no `setConf`), `:131-185` (line 166 and DEBUG texts), `:205-264` (low/high grouping, `<=`/`>` threshold); `RoundRobinVolumeChoosingPolicy.java:110-126` (`>` test and exception text); `FsVolumeImpl.java:173-175` (dir = `currentDir.getParent()`), `:434-482` (`getCapacity`, `getAvailable`), `:484-521`, `:556-558` (package-private `getReserved`), `:617-621`, `:1015-1021`, `:1098-1100` (`toString` = volume dir); `ReservedSpaceCalculator.java:112-118` (lookup order); `BlockPoolSlice.java:445-452` (finalize adds block + meta); `FsDatasetImpl.java:167-174, 1639, 3297-3327` (storage report, `getNextVolume`, JMX VolumeInfo); `DataStreamer.java:1917-1918`; `DFSConfigKeys.java:964-965, 1182-1187`; `DatanodeDescriptor.java:816-840` (NameNode counts only storages with remaining ≥ required); test APIs `FsVolumeImplBuilder.setUsage` (package-private), `FsVolumeList(…)` 5-arg ctor, `BlockScanner(DataNode, Configuration)`, `StorageDirectory(StorageLocation)`, `GenericTestUtils.setLogLevel(slf4j Logger, slf4j Level)`, `redirectTestOutputToFile=true`. All as cited. |

| # | Recommendation | Applied? | Why |
|---|---|---|---|
| D1-1 | Source copy with `copy-source.sh`, no `install`, offline `mvn -o`, test data in the run folder | applied 2026-11-25 (case-amended B2a) | environment; needed to run as written on the node |
| D1-2 | Print `getReservedForReplicas()` per step | applied (B2d note; harness) | B2d asks for it; the invariant check "reserved on volume i ≤ C_i − R" needs it |
| D1-3 | `$RUN/dn` on a 12 GiB ext4 loop file system | applied (B3a) | node rule: never fill `/mydata`; the B3a algebra is unchanged |
| D1-4 | NameNode DEBUG for `BlockPlacementPolicy` | applied (B3a) | B3d leaves the refusing gate to "the logs"; without this line it is not visible |
| D1-5 | K1c overshoot definition and a (7·S, 8·S] row for `d0` | applied (B3g) | a plausible outcome had no row; added before any reading |
| R1 | Cluster run at the default R = 0 | left for stage 3 | would fill the volume's file system; the unit U-R0 covers the default |
| R2 | State in B3f which gate refuses the first failed put (the NameNode check, since both storages are below B) | left for stage 3 | predictions do not depend on it; D1-4 makes it observable |
| R3 | *(added after run 1, from runbook defect §3 #1)* K1c: read the overshoot as the maximum finalized blk bytes per volume during the run (or size writers so files complete); every writer fails at the planned demand and `-put` deletes its blocks | left for stage 3 (changes a conclusions observable; back to the audit) | the frozen post-run reading cannot see an overshoot that was deleted |

## 2. Environment

| Field | Run 1 |
|---|---|
| Date | 2026-11-25 |
| Node | `pc82` = `node1.jason92-326665.misconfiguration-pg0.cloudlab.umass.edu`, 40 cores, 125 GiB RAM |
| OS and kernel | Ubuntu 22.04.2 LTS, `5.15.0-203-generic` |
| JDK | `/usr/lib/jvm/java-8-openjdk-amd64`, `1.8.0_514` (default `java` is 11.0.33, not used) |
| Maven | 3.6.3, offline (`-o`), 3.4.2 modules from `~/.m2` (node build 2026-11-24) |
| Local source copy | `copy-source.sh` from `systems/hadoop/source/` at repository HEAD `8bd1dfb31` → `<run>/src` |
| Case-file commit / harness | `cd9e1cded` / not committed (`o27/harness/`) |
| Storage for node data | cluster: 12 GiB ext4 loop file system at `<run>/cluster/dn` (image on `/mydata`); unit: mocked DF |
| Run folder (node) | `/mydata/jingsong-s4/dfs.datanode.du.reserved-doChooseVolume-mostAvailableAmongLowVolumes-run1/` |

## 3. Runbook defects

| # | Run | Step | Problem | Fix | Decision (date) | Case-file change |
|---|---|---|---|---|---|---|
| 1 | run 1, cluster | B3c/B3e step 7 (K1c) and the D1-5 observable "final blk bytes read after the 8 writers end" | Every one of the 8 writers failed in all three repetitions (demand 80 blocks against about 40), and each failed `hdfs dfs -put` deletes its `._COPYING_` file, so the NameNode invalidates all its blocks (45–47 `Deleted BP` lines per repetition in the DataNode log). The on-disk overshoot exists only for a few seconds: the first sample with all writers ended shows it in repetitions 1 and 2 and not in 3, and the `final` sample 5 s later shows 0 bytes on both volumes in all three. The frozen observable therefore cannot tell "no overshoot" from "overshoot then deleted". | Read the overshoot as the **maximum** finalized blk bytes per volume over the run (B3d's 2 s samples), or size the writers so that the files that fit complete. | The fix changes the K1c observable (B3g/D1-5), so per the protocol it goes back to the audit and K1c was **not** restarted; K1c is recorded as *Not confirmed* (below). K1, K2, K3 are unaffected. 2026-11-25 | none (recommendation R3 for stage 3, section D) |

## 4. Run 1

**Scope:** unit tier, all eight B2b tags; cluster tier K1, K2, K3 (45 puts each) and K1c × 3. **Command logs:**
`run1/unit/unit-run.log` (copy, compile, run; node clock MST), `run1/cluster/cluster-run.log`.

### 4.1 Readings

**Unit tier** (2026-11-25 10:33–10:34 MST; surefire `Tests run: 8, Failures: 0, Errors: 0, Skipped: 0`,
`run1/unit/…TestDuReservedAvailableSpacePlacement.txt`). Raw rows: `run1/unit/u-results.csv`; rows and policy log
lines in file order: `run1/unit/u-sequence.txt`; comparison with B2f: `run1/unit/parse-unit.out` (`harness/parse-unit.py`).

| Tag | Steps → d0 / d1 (order; 0 = d0, 1 = d1, X = exception) | Failing step, message | Final avail d0 / d1 | `reserved0/1` = R | B2f |
|---|---|---|---|---|---|
| U-R0 | 10 / 30 (`0000000000` then 30×`1`, `X`) | 41, `(=75497472 B) is less than the block size (=104857600 B)` | 25,165,824 / 75,497,472 | yes (0) | match |
| U-R512 | 5 / 25 (`00000` then 25×`1`) | 31, `(=62914560 B)` | 12,582,912 / 62,914,560 | yes | match |
| U-R960 | 0 / 21 | 22, `(=67108864 B)` | 67,108,864 / 12,582,912 | yes | match |
| U-EQ | 0 / 0 | 1, `(=104857600 B) is less than the block size (=104857600 B)`, while d1 had 2,252,341,248 | 104,857,600 / 2,252,341,248 | yes | match |
| U-EQ1 | 0 / 21 | 22, `(=104857599 B)` | 104,857,599 / 50,331,647 | yes | match |
| U-R0-f75 | 10 / 30 (`1111011101111011110011111101111110101010`) | 41, `(=75497472 B)` | 25,165,824 / 75,497,472 | yes | match |
| U-R512-f75 | 5 / 25 (`111111000010111…`) | 31, `(=62914560 B)` | 12,582,912 / 62,914,560 | yes | match |
| U-R512-bal | 5 / 25 (`0101010101` then 20×`1`) | 31, `(=62914560 B)` | 12,582,912 / 62,914,560 | yes | match |

- B2f bullets, for the four deterministic f = 0.0 tags (U-R0, U-R512, U-R960, U-EQ1): every step routed to `d1` had
  `mostLow < B` and was preceded by the policy's DEBUG "Selecting …/d1 from high available space volumes for write of
  block size 104857600" (0 exceptions to either rule); every step routed to `d0` had `mostLow ≥ B` (e.g. U-R0 step 10:
  `mostLow` 130,023,424, "…/d0 from low available space volumes"; step 11: `mostLow` 25,165,824, "…/d1 from high").
  No step chose a volume whose pre-step `getAvailable()` was ≤ B (0 in all eight tags). `rfr_i ≤ C_i − R` on every row,
  and `n_i·B ≤ C_i − R < (n_i + 1)·B` for every tag except U-EQ (excluded by B2f).
- U-R512-bal: 30 steps with "All volumes are within the configured free space balance threshold" and none with
  "Volumes are imbalanced" (line 166 not reached); totals equal U-R512.
- U-EQ: one WARN "The volume[…/U-EQ/d0] with the available space (=104857600 B) is less than the block size
  (=104857600 B)" and the exception, no "from high" line: the low group was chosen (`mostLow` = B is not < B), and its
  round robin rejected it (`>` test), while `d1` had 2,252,341,248 bytes available.

**Cluster tier** (2026-11-25 10:36–10:52 MST; daemon logs print UTC, 17:36–17:52). Command log
`run1/cluster/cluster-run.log`; per-put readings `run1/cluster/readings-K1.csv`, `-K2.csv`, `-K3.csv` (blk bytes and
counts by `find`, `du -sb`, JMX `VolumeInfo` per volume, the DataNode DEBUG routing line(s) logged during the put, NameNode
refusal lines, loop-fs and `/mydata` free space); K1c 2 s samples `run1/cluster/readings-K1c-{1,2,3}.csv`; daemon-log
excerpts `run1/cluster/daemon-excerpts/`; put errors `run1/cluster/put-errors-*.txt`; comparison with B3f
`run1/cluster/selfcheck.out` (`harness/selfcheck.py`).

Loop file system (D1-3): `TOTAL` = 12,573,614,080, `ROOTRES` = 661,020,672 (ext4 5 %), usable ≈ 11.9 GB at start
(`start-checks.csv`, `cluster-run.log`). Every fresh cluster's start check (B3e step 3): JMX `reservedSpace` = `R_i` to
the byte and `freeSpace` = `b_i − 24,576` (24,576 B = the block-pool directories counted in `dfsUsed`) on both volumes.

| Run | Budgets b0 / b1 | Observable (B3d) | Reading | B3f | Evidence |
|---|---|---|---|---|---|
| K1 | 1 GiB / 3 GiB | accepted puts; routing | **40** (puts 1–40); puts 1–10 → `d0` "from low", 11–40 → `d1` "from high"; puts 41–45 fail | 1–10 d0, 11–40 d1, 41 fails | `readings-K1.csv`, `logs-K1.dn-excerpt.txt` (10 low + 30 high DEBUG lines) |
| K1 | | final blk bytes d0 / d1 | **1,056,768,070 / 3,170,304,210** (= 10·S / 30·S; counts 10/30) | 10·S / 30·S, ≤ b_i | `readings-K1.csv` row 45 |
| K1 | | `freeSpace` from put 11 on (d0); final d0 / d1 | 16,949,178 (constant from put 10); final 16,949,178 / 50,896,686 | ≈ 16,973,754 / ≈ 50,921,262 (± 1 MiB) | `readings-K1.csv` |
| K1 | | refusing gate, puts 41–45 | NameNode: 5 × "does not have enough DISK space (required=104857600, scheduled=0, remaining=0)"; client "could only be written to 0 of the 1 minReplication nodes"; DataNode `Out of space` 0 | (not predicted; D1-4) | `logs-K1.nn-excerpt.txt`, `put-errors-K1.txt` |
| K2 | 512 MiB / 2 GiB | accepted; routing | **25**; 1–5 → `d0` low, 6–25 → `d1` high; 26–45 fail (20 NameNode refusals, 0 DataNode) | 1–5, 6–25, 26 fails | `readings-K2.csv`, `logs-K2.*-excerpt.txt` |
| K2 | | final blk bytes | **528,384,035 / 2,113,536,140** (5·S / 20·S); free 8,462,301 / 33,922,932 | 528,384,035 / 2,113,536,140 | `readings-K2.csv` |
| K3 | 1 GiB each, global key, T = 10 GiB | accepted; routing | **20**; `0101…01` (10 each), all 20 lines "All volumes are within the configured free space balance threshold", 0 "Volumes are imbalanced"; 21–45 fail (25 NameNode refusals) | alternate, 10 each, 21 fails, no imbalanced line | `readings-K3.csv`, `logs-K3.dn-excerpt.txt` |
| K3 | | final blk bytes | **1,056,768,070 / 1,056,768,070** | 10·S each | `readings-K3.csv` |
| K1 vs K2 | | d0 usage ratio | 1,056,768,070 / 528,384,035 = **2.0000** (d1: 1.5000) | ≈ 2 | `selfcheck.out` |
| all sequential | | any put routed to a volume whose prior `freeSpace` < B; blk > b + M | **none; none** | none | `selfcheck.out` |
| K1c-1 | as K1 | writers; final blk bytes (5 s after the last writer) | 8 of 8 writers failed; **0 / 0** (all blocks deleted) | overshoot ≤ 7·S (d0), ≤ 8·S | `readings-K1c-1.csv` row `final`, `put-errors-K1c-1.txt` |
| K1c-1 | | first sample with 0 writers alive; peak | 1,268,121,684 / 3,487,334,631 finalized (12·S / 33·S): over b by 194,379,860 (1.84·S) / 266,109,159 (2.52·S) | | `readings-K1c-1.csv` |
| K1c-2 | | final; first all-ended sample = peak | 0 / 0; 1,373,798,491 / 3,381,657,824 (13·S / 32·S): over by 300,056,667 (2.84·S) / 160,432,352 (1.52·S) | | `readings-K1c-2.csv` |
| K1c-3 | | final; first all-ended sample; peak (1 writer alive) | 0 / 0; 0 / 951,910,470 (no overshoot, deletion under way); peak 1,373,798,491 / 3,593,011,438 (13·S / 34·S): over by 300,056,667 (2.84·S) / 371,785,966 (3.52·S) | | `readings-K1c-3.csv` |
| K1c-1/2/3 | | routing and the DataNode gate | `d0` "from low" 12/13/13, `d1` "from high" 33/32/34; DataNode `opWriteBlock … DiskOutOfSpaceException: Out of space: The volume with the most available space (=0 B) is less than the block size (=104857600 B)` 3/5/2; `Deleted BP` 45/45/47 | | `logs-K1c-*.dn-excerpt.txt` |

### 4.2 Conclusion and logic

**Unit tier**

1. **Validity** — valid. `reserved0`/`reserved1` = R on every row of every tag [observed: `u-results.csv`, awk check 0
   mismatches]; the limit was reached in every tag (an exception ends each one) [observed: `parse-unit.out`]; f, T as
   set [observed: the policy's "initialized" INFO line per test in `u-sequence.txt`].
2. **Readings** — nothing unusual; f = 0.75 orders differ from the f = 0.0 ones, as expected, with equal totals
   [observed: `parse-unit.out`].
3. **Matched row (B2g)** — "Counts and failing steps match B2f; `mostLow < B` on exactly the steps routed to the high
   volume → Mechanism works as traced: usage follows the reserve, line 166 routes around a too-small low volume. Claim
   supported at unit level." All eight tags match B2f in counts, failing step, exception value and final available bytes;
   every `d1` step in the four deterministic tags has `mostLow < B` and a "from high" DEBUG line, every `d0` step
   `mostLow ≥ B` [observed: `parse-unit.out`, `u-sequence.txt`]. Also matched: "U-EQ throws at step 1 → confirms the
   `<`/`>` boundary mismatch, A3(e)" [observed: U-EQ row, `d1` had 2,252,341,248] and "U-R512-bal totals equal U-R512
   → line 166 only routes" [observed: 5/25/31 in both].
4. **Excluded rows** — a volume chosen with pre-step available ≤ B: 0 rows [observed]. `d0` chosen while `mostLow < B`
   (f = 0.0): none. `d1` chosen while `mostLow ≥ B` and `d0` > B: none. `n_0, n_1` equal across R = 0 / 512 / 960 MiB:
   no (10/5/0 and 30/25/21). `reserved0 ≠ R`: no. "U-EQ returns `d1`": no (exception).
5. **Observed vs inferred** — all statements observed; the only inference is that `mostLow` recomputed in the test equals
   the policy's local variable, which the DEBUG "from high/low" lines confirm step by step [observed].
6. **Deviations and gaps** — D1-1, D1-2 (environment, one instrument column). Real disk bytes are not observable at this
   tier (B2d); the cluster tier covers them.
7. **Core question** — the number of 100 MiB replicas each volume accepts follows `C_i − R` exactly (10/30 at R = 0,
   5/25 at 512 MiB, 0/21 at 960 MiB), no volume is given a replica it cannot hold, and when the low volume cannot fit
   the replica line 166 sends it to the high volume (parts 3, 4). The constraint caps the reservation per volume.

**Conclusion (unit, one line):** B2g row 1 "Counts and failing steps match B2f … Claim supported at unit level" —
**confirmed**; plus "U-EQ throws at step 1" (A3(e) boundary failure confirmed) and "U-R512-bal totals equal U-R512"
(line 166 routes, the cap is `getAvailable` + the round-robin `>` test).

**Cluster tier**

1. **Validity** — valid for K1, K2, K3. Knob landed: JMX `reservedSpace` = `R_i` to the byte and `freeSpace` =
   `b_i − 24,576` at each start [observed: `start-checks.csv`, `cluster-run.log` CHECK lines]; the limit was reached
   (45 puts against 40/25/20 that fit) [observed]; hold-fixed settings (threshold 1 MiB / fraction 0.0, heartbeat 1 s,
   3 s sleep, re-format between runs) [observed: `cluster-run.log`, hdfs-site in `logs/cluster/` on the node]. K1c: the
   frozen observable is defective (§3 #1).
2. **Readings** — the first refused put of every sequential run was refused by the NameNode check (`DatanodeDescriptor`,
   storages with remaining < B count 0), not by the DataNode's line 166 / round robin, which logged no `Out of space` in
   K1–K3 [observed: `logs-K*.nn-excerpt.txt`, `logs-K*.dn-excerpt.txt`]. `freeSpace` sits 24,576 B below B3f's figures
   (directory bytes, within the ± 1 MiB).
3. **Matched row (B3g)** — "K1/K2/K3 counts and final blk bytes as predicted, all ≤ `b_i` → Usage follows the reserve on
   real disk; claim supported": 40 / 25 / 20 puts, 10·S/30·S, 5·S/20·S, 10·S/10·S to the byte [observed:
   `readings-K*.csv`]; routing evidence for line 166's true branch: puts 11–40 (K1) and 6–25 (K2) "from high" with
   `freeSpace(d0)` = 16,949,178 / 8,462,301 < B [observed]. Also matched: "K3 per-volume totals equal K1/K2 arithmetic
   for its budgets → the cap is independent of line 166; line 166 only routes" [observed: K3 10/10 with 20 "All volumes
   are within" lines].
4. **Excluded rows** — sequential blk > b + M: no (max 1,056,768,070 ≤ 1,073,741,824 etc.). Put 11 of K1 on `d0`:
   no ("d1 from high"). K1 and K2 same `d0` usage: no (ratio 2.0000). JMX `reservedSpace` ≠ `R_i`: no. Writes failing
   long before the budgets fill with `freeSpace` ≥ B: no (first refusal only when both volumes had < B). K1c rows: see 6.
5. **Observed vs inferred** — K1–K3 statements observed. Inferred: that the NameNode, not the DataNode, refused puts
   41–45 *because* both storages reported < B — the NameNode line prints `remaining=0` (sum over storages with ≥ B) and
   the JMX `freeSpace` values of both volumes were < B [observed both; the causal link is inferred from
   `DatanodeDescriptor.java:826-838`].
6. **Deviations and gaps** — D1-3 (loop fs), D1-4 (NameNode DEBUG). **K1c (secondary, leak A3(b)) is Not confirmed**:
   by the literal `final` reading the overshoot is 0 in all three repetitions, which would match "overshoot = 0 → the leak
   did not show", but the same file's samples show finalized `blk_*` bytes over budget in all three (peak `d0` 12–13
   blocks on a 10-block budget, up to 2.84·S; `d1` 32–34 blocks on 30, up to 3.52·S), deleted seconds later when the
   failed puts cleaned up. The two readings that both fit "after the 8 writers end" point to different rows, so no row is
   matched; the defect is §3 #1. The peak readings are within B3f's bounds (≤ 7·S on `d0`, ≤ 8·S each) and are
   recorded as a finding, not as a verdict.
7. **Core question** — per-volume HDFS bytes follow the reserve on a real file system (d0 10·S vs 5·S when its budget
   halves; d1 30·S vs 20·S), never exceed `b_i` in sequential writes, and line 166 sends replicas to the high volume
   exactly when the low one cannot hold one (parts 3, 4). The constraint caps usage. Under 8 concurrent writers the
   finalized bytes did exceed the budget by up to 3.5 blocks (observed, part 6), consistent with A3(b), but the frozen
   K1c observable could not settle it.

**Conclusion (cluster, one line):** B3g row 1 "K1/K2/K3 counts and final blk bytes as predicted, all ≤ `b_i`" —
**confirmed**; K3 row "cap independent of line 166" confirmed; K1c (secondary) **not confirmed** (observable defect).

## 5. Self-check of run 1 — AI (2026-11-25, raw files re-read with awk/grep, not with the harness parsers)

### 5.1 Check of run 1's conclusion

| Part | Holds? | Note (file re-read) |
|---|---|---|
| 1. Validity | yes | `u-results.csv`: `reserved0/1` ≠ R on 0 rows (awk); `test.log`: "Tests run: 8, Failures: 0, Errors: 0". `start-checks.csv`: K1 R0 = 12,573,614,080 − 661,020,672 − 1,073,741,824 = 10,838,851,584 = JMX value; same for every run and volume. |
| 2. Readings | yes | Awk on raw rows: unit tags 10/30/41, 5/25/31, 0/21/22, 0/0/1, 0/21/22, and f75/bal as U-R0/U-R512. K1 last OK 40 / first fail 41, K2 25/26, K3 20/21; final blk bytes as in §4.1. |
| 3. Matched row | yes | DN excerpts: K1 10 "d0 from low" + 30 "d1 from high", K2 5 + 20, K3 20 "All volumes are within" and 0 imbalanced; K1 row 11 `freeSpace(d0)` 16,949,178 before "d1 from high". |
| 4. Excluded rows | yes | Raw: 0 unit steps with chosen-volume avail ≤ B; 0 DataNode `Out of space` in K1–K3; 5/20/25 NameNode refusals = failed puts 41–45 / 26–45 / 21–45. |
| 5. Observed vs inferred | yes | The one inference (NameNode refused because both storages < B) is consistent with each refusal line's `remaining=0` and the JMX values in the row before it. |
| 6. Deviations and gaps | yes | K1c re-read: `readings-K1c-*.csv` `final` rows 0/0; rows with `writersAlive` 0 (rep 1, 2) show the overshoot; `Deleted BP` 45/45/47 in the DN excerpts explains the drop. K1c kept at Not confirmed. |
| 7. Core question | yes | The answer follows B1's logic: per-volume usage tracks the budget (unit and cluster), the disallow/re-route branch fired at the predicted steps, and the no-166 controls (U-R512-bal, K3) show the cap without line 166. |

### 5.2 Run 2?

**No** (2026-11-25). The verdict-bearing readings are observed and match exact predictions to the byte, and no part of
§5.1 depends on an inference that run 1 cannot settle. K1c is not verdict-bearing; a re-run of it needs the observable
fix (§3 #1) first, which is an audit matter, not a run 2.

## 6–7. Run 2

Not done.

## 8. Verdict — AI

**Stage-3 estimate:** positive. **Outcome class:** **true positive** (estimate `positive`, effect `caps` on both tiers).

**Claim tested (B1):** with `AvailableSpaceVolumeChoosingPolicy`, a replica of declared size B goes only to a volume
whose `getAvailable()` (capacity − `dfs.datanode.du.reserved` − finalized HDFS bytes − reservations) is ≥ B at line 166
and > B at the round-robin re-check; a too-small low group sends it to a high volume; for sequential writes each
volume's HDFS bytes never exceed capacity − reserved by more than one meta file, and per-volume counts follow the reserve.

| Tier | Verdict (row) | Effect on the constraint | Basis | Date |
|---|---|---|---|---|
| Unit | **Confirmed** — B2g "Counts and failing steps match B2f; `mostLow < B` on exactly the steps routed to the high volume" (also: U-EQ boundary row, U-R512-bal "line 166 only routes" row) | caps | run 1 + self-check | 2026-11-25 |
| Cluster | **Confirmed** — B3g "K1/K2/K3 counts and final blk bytes as predicted, all ≤ `b_i`" (also: K3 "cap independent of line 166"); K1c secondary **Not confirmed** (observable defect, §3 #1) | caps (concurrency overshoot observed but not settled by the frozen observable) | run 1 + self-check | 2026-11-25 |

**Findings beyond the verdict**

- **A3(e) boundary bug confirmed at runtime (unit, U-EQ):** when the best low-space volume has exactly `replicaSize`
  bytes available, line 166 (`<`) keeps the low group and its round robin (`>`) rejects it, so `DiskOutOfSpaceException
  … (=104857600 B) is less than the block size (=104857600 B)` is thrown although another volume had 2,252,341,248 bytes
  free. A spurious out-of-space failure (not an overshoot); with the default fraction 0.75 it would hit with probability
  1 − scaledPreference. Upstream candidate (check JIRA first).
- **Concurrent writers overshoot the reserve on disk (cluster, K1c, observed in samples):** with 8 writers, `d0` held 12–13
  finalized 100 MiB blocks on a 10-block budget (up to 300,056,667 B over) and `d1` 32–34 on 30 (up to 371,785,966 B
  over) in 3 of 3 repetitions, and the DataNode's own gate then refused writes with "most available space (=0 B)". This
  is the in-flight acked-bytes leak A3(b); bounded (≤ 3.52·S here), not unbounded.
- In sequential writes the NameNode's `chooseStorage4Block` refuses the first write that would not fit (storages below B
  count 0), so line 166's disallow branch is reached at the DataNode only under concurrency; its routing branch is what
  sequential writes exercise (recommendation R2).
- No memory holder of interest (disk-space case; two 1 GiB-heap daemons, no OOM).

**Feedback filed:** section D of `case-amended.md` (audit amendments D1-1–D1-5 and the stage-4 result, recommendation R3).
Not committed (this agent's brief: no repository edits). To file: copy `case-amended.md` over the case file, this file
to `hadoop/stage4-runtime-verification/jingsong/results/dfs.datanode.du.reserved-doChooseVolume-mostAvailableAmongLowVolumes--autonomous.md`,
`harness/` to `…/harness/dfs.datanode.du.reserved-doChooseVolume-mostAvailableAmongLowVolumes--autonomous/`, `run1/`
excerpts to `…/results/<stem>/run1/`; update `_INDEX.md` row 27 (sha256 of the frozen file `ca1a8083…`) and
`queue.csv` order 27 (`Confirmed — caps (unit + cluster); TP`).

**Cleanup (pc82):** daemons stopped (EXIT trap and teardown; `ps` check: no NameNode/DataNode, no `cluster-run`,
Maven or surefire process), loop file system unmounted and its image deleted (`findmnt`/`losetup -a`: none), ports
19820/19864/19866/19867/19870 free, driver PID file removed, source copy and test data deleted, node lock released
2026-11-25 10:53:45 MST. **Left on the node:** `/mydata/jingsong-s4/dfs.datanode.du.reserved-doChooseVolume-mostAvailableAmongLowVolumes-run1/`
(3.3 MB: `harness/` and `logs/` with unit surefire output, cluster CSVs, daemon logs, driver output). Nothing on this
machine is left running.
