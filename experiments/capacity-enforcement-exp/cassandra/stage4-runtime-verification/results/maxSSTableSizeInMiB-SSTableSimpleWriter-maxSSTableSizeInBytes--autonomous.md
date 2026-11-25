# maxSSTableSizeInMiB-SSTableSimpleWriter-maxSSTableSizeInBytes--autonomous — stage-4 results

> **Case:** [`maxSSTableSizeInMiB-SSTableSimpleWriter-maxSSTableSizeInBytes--autonomous`](../../stage3-ai-deep-read/cases/maxSSTableSizeInMiB-SSTableSimpleWriter-maxSSTableSizeInBytes--autonomous.md) (extension set, order 117, band B)
>
> **Status:** verdict filed (outside the repo; not committed) — run 1 done, self-checked, no run 2
>
> **Outcome class:** **true positive** — estimate `positive`; effect `caps` on both tiers (per-SSTable `Data.db`, with the expected single-partition bypass)
>
> **Agent:** autonomous. "§9a" below means B2f/B2g (unit) and B3f/B3g (cluster); "§9b–§9e" means B2a–B2e / B3a–B3e; the feedback section is D.

Written outside the repository (`/users/jason92/writeup-ext/out/o117/results.md`) by a stage-4 session working as Jingsong, 2026-11-25. Nothing in the repository was edited; the amended case file is `/users/jason92/writeup-ext/out/o117/case-amended.md`.

## 1. Before run 1 — design audit and freeze

| Field | Content |
|---|---|
| **Case-file version** | Filed at repository commit `bef6bc8a6` (sha256 `fd7f916d…d75b3e8`, which already carries the 2026-11-24 audit amendments S1–S5 of the interrupted run). This run adds **S6** (node change, 2026-11-25, before any reading of this run). Frozen version: `/users/jason92/writeup-ext/out/o117/case-amended.md`, sha256 **`ce1471d94448e7d47ef06beb85e0f21e7dc813b052ce51428e728e26cbdbb2ed`** (copy in `harness/freeze/case-frozen.md`). Repository HEAD at the start: `cd9e1cded`. |
| **Harness** | `/users/jason92/writeup-ext/out/o117/harness/` (outside the repo, not committed): `MaxSSTableSizeProbeTest.java` (byte-identical to the case file's B2e probe), `GenSorted.java` (identical to B3a's program), `unit-run.sh`, `cluster-run.sh`, `analyze_unit.py`, `analyze_cluster.py`. Instruments carried over from the interrupted 2026-11-24 attempt were re-reviewed line by line; one defect fixed before run 1 (see §3, D0). |
| **Tiers and values** | Unit (B2): sorted writer M ∈ {1, 4, 16, 0, unset} × {uncompressed, LZ4}, bigpart (M = 1), unsorted control (M = 4); 60,000 × 1,000 B partitions. Cluster (B3): sorted M ∈ {1, 4, 16, unset} + unsorted control M = 4, generated with `CQLSSTableWriter`, imported into a single real node with `nodetool import --copy-data`. |
| **Audit bottom line** | **Ready after amendments** (S1–S5 of 2026-11-24 kept; S6 added) — 2026-11-25 |

### 1.1 Design audit

| Group | Check | Rating | Note (section checked) |
|---|---|---|---|
| A | constrained quantity is memory or disk bytes | Met | Per-SSTable `Data.db` bytes on disk (A2, B1). |
| A | knob varied, ≥ 3 values incl. default | Met | M = 1, 4, 16, 0, unset (default −1 = no limit) (B2b, B3b). |
| A | real resource measured, not only the counter | Met | Operand read by reflection **and** the real file lengths on disk; generator side and node side after import (B2d, B3d). Gap named: other components not counted by the operand, reported as `allComponentsBytes`. |
| A | usage driven to the limit and past it | Met | ≈ 61.5 MB per run = 58× L at M = 1, 3.7× at M = 16 (B2c, B3c). |
| B | each step says what it establishes | Met | B2e/B3e steps and B2h/B3h controls. |
| B | prediction stated in numbers | Met | Exact intervals `(L, L+P]`, `(L, L+2·Cmax]` (S2), counts ≈ ceil(T/L), with S3/S5 reading rules. |
| B | every plausible outcome has a row | Met | Exceeds bound, ≤ L, flat across M, limitBytes wrong, disabled path splits, positive control fails, T too small (B2g, B3g); S3(f)/S5 add "no matching row". |
| B | confirmation needs ceiling-follows-knob and direct disallow evidence | Met | Count scales 1/M and operandAtSwitch > L at every switch (the switch branch fired) (B2d, S3). |
| B | alternative explanations and controls | Met | M = 0/unset (no cap), unsorted writer (separate split), uncompressed vs LZ4, fixed seed, fresh dir per run (B2h, B3h). |
| C | a human can follow it | Met | Header Estimate + B1. |
| C | an AI can run B2e/B3e without re-deriving | Met | Full probe and generator source given; S1/S4 fix paths. |
| C | knob, values, workload, commands exact | Met | Yes, with S3/S5 tolerances. |
| D | harness and environment prerequisites | Met | `/mydata/s4/cassandra-base` on pc82 (built, `src/java` and `test/unit` identical to repo `systems/cassandra/source`, checked with `diff -rq`). |
| D | workload arithmetic reaches the limit | Met | Unit ≤ 70 MB per run; cluster < 1 GB; 656 GB free on `/mydata`. |
| D | load-bearing citations spot-checked | Met | Re-read in the repo source: `SSTableSimpleWriter.java:49,70,103-121`; `CQLSSTableWriter.java:133-134,407,675-680,736-740,761-764`; `SSTableTxnWriter.java:74-76`; `SimpleSSTableMultiWriter.java:78-80`; `SortedTableWriter.java:339-341`; `CompressedSequentialWriter.java:128-131,156-203` (chunkOffset += compressedLength + 4); `LZ4Compressor.java:113-116` (4-byte header + maxCompressedLength); `CompressionParams.java:48-49,59-65,187-190`; `CassandraRelevantProperties.java:188` (LZ4 default true). All as cited. |

| # | Recommendation | Applied? | Why |
|---|---|---|---|
| S1–S5 | (from the interrupted 2026-11-24 audit) build/path rules, LZ4 bound `L + 2·Cmax`, reading rules | kept as filed (all dated before any reading) | needed for an unambiguous run |
| S6 | node is pc82 (x86_64), not ms0640 | applied 2026-11-25 in `case-amended.md` | environment record only; claim, prediction and readings rules unchanged |
| R1 | B2e step 3 names `CQLSSTableWriterClientTest` while A5 cites the method in `CQLSSTableWriterTest`; the former is the concrete subclass of the abstract latter (`CQLSSTableWriterClientTest.java:30`) | left for stage 3 (clarity only) | runs as written |
| R2 | B3e step 8 / B4 use `pgrep -f`; the stage-4 safety rules prefer `ps -eo cmd \| grep '[C]assandraDaemon'` | already covered by S4 | — |

## 2. Environment

| Field | Run 1 |
|---|---|
| Date | 2026-11-25 (06:45–07:30 UTC, plus diagnosis) |
| Node | `pc82` = `node1.jason92-326665.misconfiguration-pg0.cloudlab.umass.edu` (CloudLab UMass), **x86_64**, 40 cores, 125 GiB |
| OS and kernel | Ubuntu 22.04 / `5.15.0-203-generic` |
| JDK | OpenJDK 11.0.33 (2026-10-20) |
| Ant | 1.10.12 |
| Local source copy | `cp -a /mydata/s4/cassandra-base` (made with `copy-source.sh` from `systems/cassandra/source/`, cassandra-5.0.9, last changed at repo commit `afcc43489`); no `.git` in the copy, so provenance was checked with `diff -rq` of `src/java` and `test/unit` against the repo source over NFS: identical (`run1/unit/unit-run.log`) |
| Case-file commit / harness | case file `bef6bc8a6` + S6, S7 (`case-amended.md`); harness outside the repo, `harness/` (not committed) |
| Storage | local `/mydata` (`/dev/mapper/emulab-node1--bs`, 753 GB, 656 GB free); run data `/mydata/jingsong-cass-s4/o117/` |
| Full logs | `/users/jason92/writeup-ext/out/o117/run1/` (`unit/`, `cluster/`, `cluster-attempt1/`, `node-logs/`); on the node only `/mydata/jingsong-cass-s4/o117/{logs,harness}` remain (1.4 MB) |

Node lock `/mydata/s4/NODE-LOCK` acquired 23:45 MST and released at the end; detached drivers' PIDs were recorded in `/mydata/s4/DRIVER-jingsong-s4-o117.pid` (1205405 unit, 1206023 and 1216348 cluster); each exited by itself and the file was removed.

## 3. Runbook defects

| # | Run | Step | Problem | Fix | Decision (date) | Case-file version with the fix |
|---|---|---|---|---|---|---|
| D0 | before run 1 | harness (S1/S4) | The carried-over scripts ran `git -C $SRC log/status` under `set -euo pipefail`; `/mydata/s4/cassandra-base` has no `.git`, so the script would have stopped at once | provenance check by `diff -rq` against the repo source instead | 2026-11-25, before any reading | harness only |
| D1 | run 1, cluster attempt 1 | B3e step 6 | `nodetool import --copy-data` returned 0 and printed nothing, but every table stayed at 0 SSTables ("No new SSTables were found", `run1/cluster-attempt1/node-system.log`). Byteman trace on the node (`run1/cluster-attempt1/diag-trace3.txt`, `.stack`): `Invalid sstable file oa-2-big-Data.db: incompatible sstable version (oa)`. The client-mode writer forces compatibility mode NONE and writes `oa`; the node with the shipped `storage_compatibility_mode: CASSANDRA_4` accepts only up to `nb`, and the lister drops rejected files silently | yaml also sets `storage_compatibility_mode: NONE` on a fresh node; the script stops if any table has 0 SSTables after import. **Cluster tier restarted from its beginning** (cluster folder deleted, base copied again) | 2026-11-25; §9a (B3f/B3g, S5) unchanged | amendment **S7** in `case-amended.md` (sha256 after S7 `eaef7d64…dafb4b`) |
| D2 | run 1, analysis | `analyze_cluster.py` | the parser read "Old SSTable count: 0" over "SSTable count: N", so node count showed 0 (5 false BAD lines, kept as `run1/cluster/analyze_cluster-v1-parsebug.out`) | match lines that start with `SSTable count`; re-run on the same raw files | 2026-11-25; parser only, no rule changed | harness only |

Cluster attempt 1 had produced generator-side files before it stopped at step 6. Its readings are not used. Attempt 2 regenerated everything from scratch.

## 4. Run 1

**Scope:** unit tier (B2, all 12 runs) and cluster tier (B3, five tables), as frozen. Command logs: `run1/unit/unit-run.log`, `run1/cluster/cluster-run.log`.

### 4.1 Readings

**Unit tier** (`run1/unit/probe-unit.csv`, `run1/unit/analyze_unit.out`; L = M MiB; T = sum of `Data.db`)

| Run | limitBytes | SSTables | T (B) | non-last `Data.db` − L | operand at switch | last `Data.db` |
|---|---|---|---|---|---|---|
| sorted M=1, uncompressed | 1,048,576 | 59 | 61,620,000 | +1,018 (all 58) | = `Data.db` (all) | 743,548 |
| sorted M=4, uncompressed | 4,194,304 | 15 | 61,620,000 | +991 (all 14) | = `Data.db` | 2,885,870 |
| sorted M=16, uncompressed | 16,777,216 | 4 | 61,620,000 | +883 (all 3) | = `Data.db` | 11,285,703 |
| sorted M=0 / unset, uncompressed | −1,048,576 / −1,048,576 | 1 / 1 | 61,620,000 | — | — | 61,620,000 |
| sorted M=1, LZ4 | 1,048,576 | 58 | 61,079,987 | +6,966 … +7,302 | L+6,917 … L+7,253; `Data.db` − operand = 49 | 907,090 |
| sorted M=4, LZ4 | 4,194,304 | 15 | 61,075,796 | +11,392 … +12,072 | `Data.db` − operand = 118 | 2,190,697 |
| sorted M=16, LZ4 | 16,777,216 | 4 | 61,074,608 | +13,836 … +14,455 | `Data.db` − operand = 347 | 10,700,232 |
| sorted M=0 / unset, LZ4 | −1,048,576 | 1 / 1 | 61,075,954 / 61,075,952 | — | — | same |
| bigpart M=1, uncompressed | 1,048,576 | 4 | 8,179,980 | first 5,100,007 (= operand); next two +1,018 | = `Data.db` | 980,785 |
| unsorted M=4 (control) | n/a (−2) | 15 | 61,620,000 | 14 × 4,145,999 | n/a | 3,576,014 |
| upstream `testWriteWithSortedAndMaxSize` | — | — | — | — | — | passed (`TEST-…CQLSSTableWriterClientTest-testWriteWithSortedAndMaxSize.xml`, 0 failures) |

P (uncompressed) = T / 60,000 = 1,027.0 B, Pb = 1,043 B; LZ4 P ≈ 1,018 B. `allComponentsBytes` exceed L by 1.1–2.5 % for non-last SSTables (not capped, as predicted). 56 of 57 scripted checks hold. The one that does not, "bigpart later non-last in (L, L+Pb]", uses S3's Pb for bigpart (T / 64,999 rows = 125.85 B → 142 B), which averages the 5,000-row partition into a per-row figure. The two middle bigpart SSTables are each exactly L + 1,018, the same as the plain M = 1 run, i.e. within (L, L + one one-row partition of 1,027 B]. That check is not part of S3(d), the rule that decides the bigpart row (see §4.2 part 2).

**Cluster tier** (`run1/cluster/sizes-gen.txt`, `sizes-node.txt`, `rowcounts.txt`, `analyze_cluster.out`)

| Table | M / writer | generator SSTables | T (B) | non-last `Data.db` − L | last | node `tablestats` count / sizes | Space used (live) vs generator `du -sb` | rows |
|---|---|---|---|---|---|---|---|---|
| `t_m1` | 1 / sorted | 59 | 61,320,000 | +1,018 (all 58) | 443,548 | 59 / identical | 62,387,828 vs 62,408,308 | 60,000 |
| `t_m4` | 4 / sorted | 15 | 61,320,000 | +1,006 (all 14) | 2,585,660 | 15 / identical | 62,181,398 vs 62,185,494 | 60,000 |
| `t_m16` | 16 / sorted | 4 | 61,320,000 | +958 (all 3) | 10,985,478 | 4 / identical | 62,024,504 vs 62,028,600 | 60,000 |
| `t_unset` | unset / sorted | 1 | 61,320,000 | — | 61,320,000 | 1 / identical | 61,999,550 vs 62,003,646 | 60,000 |
| `t_ctl` | 4 / unsorted | 15 | 61,320,000 | 14 × 4,146,254 | 3,272,444 | 15 / identical | 62,181,015 vs 62,185,111 | 60,000 |

P = 1,022.0 B, Pb = 1,038 B. All 28 checks hold. Files are BIG `oa` (`oa-<gen>-big-*`). `nodetool compactionstats`: 0 pending (autocompaction disabled on `s4ks`). No `ERROR` lines in the node's `system.log`.

### 4.2 Conclusion and logic

1. **Validity.** Holds for both tiers. The limit was reached and passed many times: T ≈ 61 MB = 58× L at M = 1 and 3.7× at M = 16 [observed: `analyze_unit.out`, `analyze_cluster.out`]. Positive control passed [observed: TEST xml]. The same seed and data were used for every M: uncompressed T is identical (61,620,000) in all sorted and unsorted unit runs, and 61,320,000 in all five cluster tables [observed]. Each run used a fresh directory and keyspace (probe code; cluster: fresh `$C`) [observed: `cluster-run.log`, `rm -rf $C`]. Autocompaction was disabled before import [observed: `cluster-run.log`].
2. **Readings.** No outliers. One scripted unit check failed for an instrument reason: S3's Pb for bigpart is computed per row over a run with a 5,000-row partition, and the trailing one-row partitions are bigger than that average [observed: `probe-unit.csv` bigpart rows; inferred: arithmetic]. S3(d), which decides the bigpart row, holds. Cluster D2 parse bug was fixed and the script re-run on the same raw files [observed: `analyze_cluster-v1-parsebug.out` vs `analyze_cluster.out`].
3. **Matched rows.**
   - **Unit, B2g row 1** "Counts ≈ 59/15/4 for M = 1/4/16, 1 for M = 0/unset; non-last `Data.db` in (L, L+P] (uncompressed) / (L, L+P+16,388] (LZ4; S2: (L, L+2·Cmax])" → *Claim confirmed*. Counts 59/15/4 and 58/15/4, each within S3(b) of ceil(T/L) (59/15/4), and |c1 − 4·c4| ≤ 2, |c4 − 4·c16| ≤ 2 for both settings [observed]. Uncompressed non-last `Data.db` ∈ (L, L+Pb], operand = `Data.db` [observed]. LZ4 inside S2's bounds, operand in (L, L+Cmax], `Data.db` − operand ≤ Cmax, and also inside the filed L+P+16,388 [observed]. limitBytes correct; M = 0/unset 1 SSTable; positive control passed; T ≥ 40 MB [observed]. **Direct evidence that the switch branch fired:** at every switch the operand read just before the new writer appeared is > L (the `getOnDiskBytesWritten() > maxSSTableSizeInBytes` condition at `SSTableSimpleWriter.java:105`) [observed: operandAtSwitch column].
   - **Unit, bypass row** "bigpart first SSTable ≈ 5.1 MB" → *expected bypass confirmed*: 5,100,007 B > 4.5 MiB with the operand equal, 4 SSTables (S3(d)) [observed].
   - **Unit, B2h control** unsorted M = 4 → 15 SSTables ≥ 2 (S3(e)) [observed].
   - **Cluster, B3g rows 1, 5, 6** "Counts ≈ 59/15/4/1 and non-last `Data.db` within (L, L+P], same on node after import" → *Claim confirmed*; `t_unset` 1 SSTable while `t_m*` split (negative control as expected); `t_ctl` splits (positive control) [observed].
4. **Excluded rows.** Unit: "exceeds the bound" — max overshoot L+1,018 uncompressed (< Pb 1,043), L+14,455 LZ4 (< 2·Cmax 32,944) [observed]. "≤ L" — the minimum non-last is L+883 (L+6,966 LZ4) [observed]. "Count does not change with M" — 59 → 15 → 4 [observed]. "limitBytes ≠ M MiB" — equal [observed]. "M = 0/unset > 1 SSTable" — 1 [observed]. "Positive control fails" — passed. "T far below 61.5 MB" — 61.1–61.6 MB. Cluster: "> L + P" — max L+1,018 < L+1,038 [observed]. "independent of M" — no. "Node-side sizes differ" — identical lists and counts [observed]. "Row counts ≠ 60,000" — all 60,000 [observed].
5. **Observed vs. inferred.** The conclusion depends on one inference: that the operand captured after `addRow(k)` equals the value compared in the check inside `addRow(k+1)` (B2d). Nothing is written between the two calls, and the uncompressed equality operand = final `Data.db` confirms that the captured value is the file length at the switch [inferred from A3, with the equality observed].
6. **Deviations and gaps.** Node pc82 (x86_64) instead of ms0640 (S6). D0, D1 and D2 are as in §3; D1 restarted the cluster tier. The case is a client-side writer: the cluster tier tests the documented bulk-load path, not a node-side mechanism. Heap and total disk are not capped and were not measured, as designed.
7. **Core question.** Yes. Each produced SSTable's data file follows the knob: the count scales about 1/M (59/15/4, with 1 when the knob is off). Every non-full SSTable ends within one partition (uncompressed) or about one compression chunk (LZ4) above the limit, because the switch fires once the operand exceeds the limit (parts 1, 3, 4). The cap is per SSTable `Data.db` only. A partition larger than the limit passes through unsplit (bypass), and total output is not capped (parts 3, 6).

**Conclusion (one line):** Unit: B2g row 1 — **Confirmed — caps** (bypass as recorded: one partition is never split). Cluster: B3g row 1 — **Confirmed — caps**.

## 5. Self-check of run 1 — AI

| Part | Holds? | Note (file re-read) |
|---|---|---|
| 1. Validity | yes | Re-read `probe-unit.csv` (T per run), TEST xmls (0 failures), `cluster-run.log` (fresh `$C`, `disableautocompaction`, `storage_compatibility_mode: NONE`), `rowcounts.txt`. |
| 2. Readings | yes | bigpart rows re-read: 5,100,007 / 1,049,594 / 1,049,594 / 980,785; the failed scripted check is the Pb artifact described. |
| 3. Matched row | yes | Re-read uncompressed M=1 (58 × 1,049,594 with operand equal), M=16 both settings, LZ4 M=1 first rows; cluster `t_m16` 3 × 16,778,174 + 10,985,478, `t_unset` 61,320,000; `sizes-node.txt` counts 59/15/4/1/15. |
| 4. Excluded rows | yes | Bounds recomputed from the raw numbers above. |
| 5. Observed vs. inferred | yes | Only the operand-capture inference, backed by the observed equality. |
| 6. Deviations and gaps | yes | D0–D2 recorded. S7 changes node config only, and generator-side readings decide B3g anyway. |
| 7. Core question | yes | Follows B1: ceiling follows knob plus the switch condition observed. |

**5.2 Run 2?** Not chosen. Both tiers rest on observed readings with exact byte matches, the only inference is backed by an observed equality, and the result neither refutes the case nor turns on a bypass judgement.

## 8. Verdict

- **Claim tested (B1):** with the sorted `CQLSSTableWriter` and `withMaxSSTableSizeInMiB(M)`, every non-last SSTable's `Data.db` lies in (L, L + one partition (+ chunk when compressed)], and the count is ≈ ceil(T/L); with M unset or ≤ 0, one SSTable.
- **Unit tier:** Confirmed — caps (bypass: a single partition larger than L is not split, 5.1 MB at L = 1 MiB).
- **Cluster tier:** Confirmed — caps (same files byte-identical after `nodetool import` into a real node).
- **Effect on the constraint:** `caps` (per-SSTable `Data.db` only; not total disk, other components or heap; single-partition bypass recorded).
- **Outcome class:** **true positive**: estimate `positive`, effect `caps`, and the two tiers agree.
- **Filed:** results here; case feedback in `case-amended.md` section D (with S6, S7). Nothing is in the repository yet: `_INDEX.md`, `writeup-set-ext.csv` and `HANDOFF*.md` rows are left for the filing step.

