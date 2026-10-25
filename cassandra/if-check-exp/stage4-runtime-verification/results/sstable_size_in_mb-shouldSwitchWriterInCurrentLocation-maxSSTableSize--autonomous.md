# sstable_size_in_mb-shouldSwitchWriterInCurrentLocation-maxSSTableSize--autonomous — stage-4 results  <!-- file: results/sstable_size_in_mb-shouldSwitchWriterInCurrentLocation-maxSSTableSize--autonomous.md; the stem ends in --guided or --autonomous -->

> **Case:** [`sstable_size_in_mb-shouldSwitchWriterInCurrentLocation-maxSSTableSize--autonomous`](../../stage3-ai-deep-read/cases/sstable_size_in_mb-shouldSwitchWriterInCurrentLocation-maxSSTableSize--autonomous.md)
>
> **Status:** verdict filed (2026-10-24) — run 1 done at both tiers, self-checked, no run 2
>
> **Outcome class:** **true positive** (estimate `positive`, effect `caps`) — [definition](../README.md#outcome-class)
>
> **Agent:** autonomous (the suffix of the case-file stem). "§9a" below means each tier's predictions and conclusions table: B2f and B2g (unit), B3f and B3g (cluster); "§9b–§9e" means B2a–B2e or B3a–B3e; the case file's feedback section is its section D.

## 1. Before run 1 — design audit and freeze

| Field | Content |
|---|---|
| **Case-file version** | Base repository commit `9e6ee79` (the case file is **untracked** in the working tree at this date, so no commit holds it; the human closes the commit). **sha256 of the whole file after the audit's amendments (B2i and B3i, dated 2026-10-24): `56434a6293ee9c6ec2e5acbb10d1c3a46921760e1eb1db471c02b827be1a0d84`.** Recorded 2026-10-24 before any reading; the prediction and conclusions tables (B2f, B2g, B3f, B3g) are frozen at this hash. The hash covers the file as it stood before section D (the stage-4 feedback) was filled; D is the only later change. |
| **Harness** | `harness/sstable_size_in_mb-shouldSwitchWriterInCurrentLocation-maxSSTableSize--autonomous/`: `WriterHarnessBase.java`, `MajorLeveledSizeCapTest.java`, `unit-run.sh`, `analyze_unit.py`, `cluster-run.py`, `loader.py`, `analyze_cluster.py`, `selfcheck.py`, `README.md`; written after the freeze; not committed (final md5s: `sstable_size_in_mb-shouldSwitchWriterInCurrentLocation-maxSSTableSize--autonomous/run1/harness.md5.final`; the md5s taken when the unit run started are `run1/unit/harness.md5`, before the cluster analyzer and `selfcheck.py` existed) |
| **Tiers and values** | **Unit (B2):** `S` ∈ {total/10, total/50, total/200, Long.MAX_VALUE} uncompressed, plus `total/50` compressed (LZ4), plus the wide-partition arm (`S` = 4 MiB, one 12 MiB partition). **Cluster (B3):** `sstable_size_in_mb` ∈ {5, 20, 80, default 160} on 400,000 rows of 1 KiB; controls: STCS table, wide partition (S = 20). |
| **Audit bottom line** | **Ready after amendments** — 2026-10-24 |

### 1.1 Design audit

Estimate: **positive, scoped to one file** (`sstable_size_in_mb` caps each output sstable's Data.db of a major LCS compaction, softly, by up to one partition; it does not claim a cap on total disk). It is not a negative-estimate file, so no positive control is required by group A; B2h/B3h still carry their own negative controls (`Long.MAX_VALUE`, STCS). Audited against `cassandra/cassandra-5.0.9/` (`git status` of it clean at `9e6ee79`; `build.xml` `base.version` 5.0.9). Citations re-read in the pinned source: `MajorLeveledCompactionWriter.java:30-113`, `LeveledCompactionTask.java:31-54`, `LeveledManifest.java:185-193`, `LeveledCompactionStrategy.java:52-56, 60-90, 183-193, 211, 289-292, 570-625`, `CompactionManager.java:985-1013`, `CompactionAwareWriter.java:130-235`, `SSTableWriter.java:205-212`, `SequentialWriter.java:310-318`, `CompressedSequentialWriter.java:120-133`, `MaxSSTableSizeWriter.java:76-79`, `CompactionAwareWriterTest.java:55-300`: all hold at the cited lines.

| Group | Check | Rating (Met / Partly / Not met) | Note (section checked) |
|---|---|---|---|
| A. Core question | constrained quantity is memory or disk bytes | Met | A2/B1: the Data.db bytes of one output sstable (disk); A4 names what it does not bound. |
| A. Core question | knob varied, ≥ 3 values incl. default | Met | B2b: three `S` plus `Long.MAX_VALUE`; B3b: 5, 20, 80 and the default 160. |
| A. Core question | real resource measured, not only the counter | Met | B2d reads file lengths (`onDiskLength()`) and the operand; B3d `stat`/`du` of the real files. The compressed gap (operand is `chunkOffset`) is named in A2/B2d and bounded in B2i.3. |
| A. Core question | usage driven to the limit and past it | Met | B2c/B3c produce 10 to 200 files per run, each closed by the check; the disallow branch (a switch) is recorded per call. |
| B. Logic | each step says what it establishes | Met | B2e/B3e list steps with their purpose. |
| B. Logic | prediction stated in numbers or a clear relation | Met | B2f/B3f give counts and the `(S, S + partition]` relation; B2i.2 sharpens it from the source. |
| B. Logic | every plausible outcome has a conclusions row with its evidence | Met | B2g/B3g cover bound exceeded, `<= S`, count flat, `Long.MAX_VALUE` still splits, data too small, wide-row control. |
| B. Logic | confirmation needs ceiling-follows-knob and direct disallow evidence | Met | Count and size follow `S` (ceiling) and the per-call log records every `true` return (disallow); the strict `>` is tested by the `<= S` row. |
| B. Logic | alternative explanations and their controls | Met | B2h/B3h: `Long.MAX_VALUE`, one fixed input per arm, wide partition, compressed vs not, STCS. |
| C. Specific | a human can follow it from the intro and B1 | Met | A3 and B1 are clear. |
| C. Specific | an AI can run B2/B3 without re-deriving the code path | Partly → Met | How the input is built (the existing `populate` hides size under LZ4), the chunk bound, the wide-partition numbers and the load were not exact; supplied in B2i / B3i. |
| C. Specific | knob, values, workload, commands, observables, sampling, stop conditions exact | Partly → Met | Paths (`/local/work/...`) do not exist here (environment deviation, §2); loader, flush cadence, sampler target supplied in B3i. |
| D. Runnable | harness and environment prerequisites exist or are listed | Met | `ant build-test` tree, bundled Python driver, `nodetool`, `sstablemetadata`; the unit test, loader and run scripts are step-1 work. |
| D. Runnable | workload arithmetic reaches the limit (data, time, disk, memory) | Met | 200 MiB / 400 MiB against `S` of 1 to 80 MiB; `pc12` `/` has about 47 GB free, the largest arm about 1 GB. |
| D. Runnable | load-bearing citations spot-checked | Met | List above. |

| # | Recommendation | Applied? | Why |
|---|---|---|---|
| 1 | Own `populate` (distinct 1 KiB blobs, uncompressed); compressed arm in a second table | Applied, B2i.1, 2026-10-24 (case file untracked; sha256 above) | The existing helper's identical 5,000-byte payload is hidden by LZ4 and is about 1 GB per arm. |
| 2 | State the derivable relations (operand = file length, overshoot ≤ one partition, level histogram for `total/200`) | Applied, B2i.2 | Sharpens B2f without changing its direction. |
| 3 | Compressed bound `S + maxPartition + 2 × 16 KiB + 64 B` | Applied, B2i.3 | B2f says "about one chunk" without a number; the operand is `chunkOffset`. |
| 4 | Exact wide-partition arm (S = 4 MiB, 12 MiB partition) | Applied, B2i.4 | B2h.3 said "for example 3×S" only. |
| 5 | Keep auto-compaction off through `nodetool compact` | Applied, B3i.1 | `getMaximalTask` returns `null` if any sstable is already compacting; re-enabling starts background L0 compaction. |
| 6 | Driver loader, flush cadence, table per arm, `auto_snapshot: false`, `du` on the table directory | Applied, B3i.2, B3i.3, B3i.6 | Unspecified in B3c/B3d; `du` of node-data includes the commit log. |
| 7 | STCS control cannot carry `sstable_size_in_mb` | Applied, B3i.4 | STCS rejects the unknown option. |
| 8 | Paths in B2a/B3a/B4 refer to trees that do not exist here | Left for stage 3 | Cosmetic. |

**Agreement criteria** — not applicable unless run 2 is chosen (§5.2).

## 2. Environment

| Field | Run 1 | Run 2 (fresh AI session, if done) |
|---|---|---|
| Date | 2026-10-24 (unit 11:47–11:49 MDT, cluster 11:50–11:55 MDT) | not done |
| Node (CloudLab name and type) | `pc12` = `node1.jason92-320876.misconfiguration-pg0.cloudlab.umass.edu`, 40 cores, 251 GiB | |
| OS and kernel (`uname -r`) | Ubuntu 22.04.2 LTS, `5.15.0-187-generic` | |
| JDK (`java -version`) | OpenJDK 11.0.32.1 | |
| Ant (`ant -version`) | 1.10.12 | |
| Local source copy (from `cassandra/cassandra-5.0.9/` at repository commit …) | `~/stage4-sml1/tree` made by `copy-source.sh` from repository commit `9e6ee79` (local baseline `368e739`, `git describe` = `cassandra-5.0.9`); `ant build-test` 1 min 10 s; the two harness Java files added under `test/unit/.../compaction/writers/`. The cluster node ran from this tree's `build/`. Nothing built in the repository's `cassandra/cassandra-5.0.9/` (`git status` of it empty after the runs). | |
| Case-file commit / harness commit | case file untracked at `9e6ee79` (sha256 `56434a62…1d84`, §1); harness uncommitted (md5s in `run1/harness.md5.final`) | |
| Storage for node data | `/dev/sda3`, ext3, 63 GB (47 to 51 GB free); node data under `~/stage4-sml1/node` (removed afterwards); unit test data under the tree's `build/test/cassandra` | |
| Full logs (path, outside the repo) | `pc12:~/stage4-sml1/run1/{unit,cluster}/` (full `ant.log`, per-call CSVs, per-arm `system.log.segment`, `sstablemetadata.out`, `cluster.out`); builds in `pc12:~/stage4-sml1/logs/`; excerpts in `sstable_size_in_mb-shouldSwitchWriterInCurrentLocation-maxSSTableSize--autonomous/run1/` | |

**Environment deviations (none changes B1):** (1) the filed paths (`/local/work/...`) do not exist; trees and data are under `~/stage4-sml1/` on local disk. (2) The cluster loader is a Python driver script, not `cassandra-stress` (B3i.2). (3) `MAX_HEAP_SIZE=2G HEAP_NEWSIZE=512M`, `compaction_throughput: 0MiB/s` and `auto_snapshot: false` were set (environment and yaml, `run1/cluster/cassandra.yaml.used`) but not read back from the live node; no reading depends on them (file counts and sizes do not depend on the throughput). (4) A shakedown at `STAGE4_PARTS=400` (unit) and `STAGE4_PER_PHASE=400` (cluster arms `s5 wide20 stcs`) ran before run 1 to check the instruments; its output (`pc12:~/stage4-sml1/shake*`) is not used. (5) `ulimit -n` raised to 100000 inside `cluster-run.py`.

## 3. Runbook defects

| # | Run | Step | Problem | Fix | Decision (date) | Case-file commit with the fix |
|---|---|---|---|---|---|---|
| 1 | audit | B3c, B3e | B3c re-enables auto-compaction before `nodetool compact`; `getMaximalTask` returns `null` when any sstable is already compacting (`LeveledCompactionStrategy.java:183-193`). | Auto-compaction stays off for the whole arm: B3i.1. | 2026-10-24, before the freeze | none (case file untracked) |
| 2 | audit | B3h (1) | The STCS control cannot carry `sstable_size_in_mb` (unknown option for STCS). | Same data in an STCS table without the option: B3i.4. | 2026-10-24, before the freeze | none |
| 3 | audit | B2c | The upstream `populate` writes one identical payload per row, hidden by LZ4. | Own populate, distinct seeded blobs: B2i.1. | 2026-10-24, before the freeze | none |

No defect was found while running; no tier restarted.

## 4. Run 1

**Scope:** unit tier, 6 arms in one JVM (`S` = total/10, total/50, total/200, `Long.MAX_VALUE`, total/50 on a compressed table, wide partition at `S` = 4 MiB); cluster tier, 6 arms in one node lifetime (`sstable_size_in_mb` = 5, 20, 80, default; STCS control; wide-partition control at 20). **Command log:** `sstable_size_in_mb-shouldSwitchWriterInCurrentLocation-maxSSTableSize--autonomous/run1/unit/session.log`, `run1/cluster/session.log`; analyzer output `run1/analyze_unit.out`, `run1/analyze_cluster.out`; independent self-check `run1/selfcheck.out`.

### 4.1 Readings

**Unit tier** (`run1/analyze_unit.out`, `run1/unit/arms.txt`, `run1/unit/files-*.csv`, `run1/unit/switches-*.csv`). Input: 20,000 partitions x 10 rows x 1 KiB, one sstable of about 208.5 MB; the JUnit run ended `BUILD SUCCESSFUL` (`run1/unit/ant-tail.log`).

| Test or assertion | Result | Evidence (file) |
|---|---|---|
| Output count, `S` = total/10, /50, /200, `Long.MAX_VALUE` | 10, 50, 199, 1 (rows preserved: 200,000 in every arm) | `arms.txt` |
| Every non-final output in `(S, S + maxPartition]` (`maxPartition` = 10,428 B, read from the operand deltas) | holds in all arms; largest excess over `S` 10,400 / 10,424 / 10,426 B | `analyze_unit.out` |
| Final output `<= S + maxPartition` | 20,810,726 / 3,888,744 / 969,334 B | `analyze_unit.out` |
| Operand at every `true` return `> S`, at every `false` return `<= S` | holds in all 6 arms (e.g. `S` = 4,170,314: min true 4,170,334, max false 4,170,310) | `analyze_unit.out`, `switches-*.csv` |
| Uncompressed non-final Data.db length == the operand recorded at its switch | holds (no mismatch) in s10, s50, s200, wide | `analyze_unit.out` |
| Levels: s50 | 10 in L1, 40 in L2 | `files-s50.csv` |
| Levels: s10 / s200 | s10: 10 in L1; s200: 10 / 100 / 89 in L1 / L2 / L3 | `files-s10.csv`, `files-s200.csv` |
| `Long.MAX_VALUE` control | 1 output, operand reached 208,432,288 with no switch | `analyze_unit.out` |
| Compressed (LZ4) total/50 | 50 outputs; non-final files 4,191,605 to 4,192,754 B for `S` = 4,181,531 (excess at most 11,223 B; bound `S` + 16,458 + 32,832) | `analyze_unit.out` |
| Wide partition (`S` = 4 MiB, 12 MiB partition) | exactly one output above `S + maxSmallPartition`: 13,352,382 B (>= 12 MiB, <= 12 MiB + `S`) | `analyze_unit.out` |

**Cluster tier** (`run1/analyze_cluster.out`, `run1/cluster/<arm>/`). 400,000 rows (40,000 partitions x 10 x 1 KiB), 8 flushes, so 8 L0 files (about 416.9 MB) as input; major compaction by `nodetool compact`; sampler every 0.25 s on the table directory.

| Capacity value | Run | Observable (B3d) | Reading | Evidence (file) |
|---|---|---|---|---|
| `sstable_size_in_mb` = 5 | A | files; levels; largest file; live bytes; peak table-dir bytes | 80; L1 10 / L2 70; 5,246,908 B (`S` + 4,028); 417,236,864; 836,042,782 (2.01 x input) | `cluster/s5/summary.json`, `files.csv`, `levels.txt`, `du.csv` |
| 20 | A | same | 20; L1 10 / L2 10; 20,976,742 B (`S` + 5,222); 417,234,639; 835,496,752 (2.00 x) | `cluster/s20/` |
| 80 | A | same | 5; L1 5; 83,895,646 B (`S` + 9,566); 417,234,048; 835,476,668 (2.00 x) | `cluster/s80/` |
| default (160) | A | same | 3; L1 3; 167,780,479 B (`S` + 8,319); 417,233,889; 835,486,990 (2.00 x); the option is absent in `system_schema` | `cluster/s160/` |
| STCS control | B | files | 1 file, level 0, 417,232,796 B | `cluster/stcs/` |
| 20 + one 60 MiB partition | C | files; largest | 21; L1 10 / L2 11; largest 75,599,843 B (> `S` = 20 MiB); next largest 20,976,652 B | `cluster/wide20/` |
| every arm | | read-back; ERROR in log; `Compacted` lines | rows read back equal rows written (400,000; 400,060 in the wide arm); no ERROR; exactly one `Compacted` line | `cluster/<arm>/summary.json`, `system.log.compaction-lines` |

### 4.2 Conclusion and logic

1. **Validity** — valid. The limit was reached in every arm: the check returned `true` 9, 49, 198 times (unit) and the cluster outputs were 80, 20, 5 and 3 files [observed: `run1/unit/arms.txt`, `run1/cluster/*/summary.json`]. The hold-fixed settings: the same data and seeds in every arm (input bytes within 0.1 %) [observed: `arms.txt` `inputBytes`, `summary.json` `input_bytes`]; the option actually applied [observed: `summary.json` `compaction_option`, read from `system_schema.tables`]; auto-compaction disabled, one `Compacted` line per arm [observed: `selfcheck.out`]; one data directory, so no disk-boundary split [inferred: single `data_file_directories` entry in `cassandra.yaml.used`]; the major writer was the one used [inferred: no output at L0, and levels start at L1, which only `MajorLeveledCompactionWriter` assigns for a major compaction (`LeveledCompactionTask.java:51-53`)].
2. **Readings** — nothing contradicts another. The unit sizes and the per-call operands agree exactly for uncompressed files (the file length equals the operand at the switch). Peak table-directory bytes are 2.00 to 2.01 x the input in every cluster arm.
3. **Matched row** — unit B2g row 1: "Non-final outputs in `(S, S + maxPartition + granularity]`; output count ~ `total/S` | Claim holds: the operand caps single-file size as traced" [observed: `analyze_unit.out`, all arms]. Cluster B3g row 1: "File count follows ~400/S and non-final files within `S` + one partition | Claim holds on the real node" [observed: counts 80 / 20 / 5 / 3 against live/S = 79.6 / 19.9 / 5.0 / 2.5; largest excess over `S` 4,028 to 9,566 B; `analyze_cluster.out`]. The B3g row "Peak du ~ 2x live regardless of `S` | Expected" also applies [observed: 2.00 to 2.01 x].
4. **Excluded rows** — "any non-final output > `S` + maxPartition + granularity": none, largest excess 10,426 B against `maxPartition` 10,428 B [observed]. "Any non-final output <= `S`": none; the operand at every `true` return was `> S` [observed]. "Output count does not change with `S`": counts moved 10 / 50 / 199 and 80 / 20 / 5 / 3 [observed]. "`S` = `Long.MAX_VALUE` still yields several files": 1 file [observed]. "Only one output for all `S`": no. Cluster "non-final file > `S` + one partition (apart from the wide-row control)": none. "Peak du much lower for small `S`": no, 2.01 x at `S` = 5 MiB. "File count unchanged across `S`": no. "Wide-row control file <= `S`": no, 75.6 MB against 20 MiB (the documented bypass holds). No Refuted row applies.
5. **Observed vs. inferred** — inferred: that the major writer was the code run on the node (the unit tier drives it directly, so only the cluster tier depends on this, and it rests on the L0-absence argument above); and that the cluster node used a single data directory. The operand equalling the file length is observed for uncompressed files, not inferred. Everything else is observed.
6. **Deviations and gaps** — the compressed run's bound is the audited `S + maxPartition + 2 chunks + 64 B`, not "about one chunk"; the observed excess (11,223 B) is below even `maxPartition` alone. Each cluster arm and the unit tier ran once (no repeat, no run 2). Heap and compaction throughput were not read back from the live node (§2). Nothing was skipped.
7. **Core question** — the constraint caps the size of each output file of a major LCS compaction: every non-final file is just above `sstable_size_in_mb` (excess at most one partition, 4 to 10 KiB), and the file count moves inversely with the option (80 / 20 / 5 / 3 files for 5 / 20 / 80 / 160 MiB, each time closed by the check returning `true`), with the control (`Long.MAX_VALUE`, one file) and the STCS table (one file) showing that the check is the cause. The cap is soft by one partition and is bypassed by a partition larger than the limit (one 60 MiB partition gave a 75.6 MB file at 20 MiB); it does not cap total or transient disk (peak 2.0 x input in every arm), as the estimate said.

**Conclusion (one line):** unit B2g row 1 and cluster B3g row 1 (claim holds: the operand caps single-file size, softly, with the wide-partition bypass as recorded) — confirmed.

## 5. Self-check of run 1 — AI

### 5.1 Check of run 1's conclusion

`run1/selfcheck.out` re-derives the numbers by a route independent of `analyze_*.py` (levels from the per-call log, file counts from the switch count, sizes from the operand at each switch; cluster levels re-parsed from `sstablemetadata.out`, the `Compacted` line's output list against the files on disk, peak bytes from `du.csv`): **all checks hold** (unit 6 arms, cluster 6 arms).

| Part | Holds? (yes / no) | Note (file re-read) |
|---|---|---|
| 1. Validity | yes | `selfcheck.out`: one `Compacted` line per arm (auto-compaction off); levels and counts agree with the Compacted line's list; `summary.json` `compaction_option` shows each value |
| 2. Readings | yes | `files-*.csv` against `arms.txt` and the call log: byte sums and counts agree; the `du.csv` peak equals `summary.json` |
| 3. Matched row | yes | `analyze_unit.out`, `analyze_cluster.out`: every check PASS, 0 FAIL |
| 4. Excluded rows | yes | maximum excess 10,426 B (unit) and 4,028 to 9,566 B (cluster) against one partition; `Long.MAX_VALUE` and STCS give 1 file |
| 5. Observed vs. inferred | yes | the one inferred item (major writer on the node) is supported by `levels.txt` (no L0) |
| 6. Deviations and gaps | yes | listed in §2 and §4.2 part 6; none affects a count or a size |
| 7. Core question — the steps from reading to answer follow the audited logic | yes | knob varied, count and size follow it, controls move or stay as predicted; the claim is stated as scoped (per file) |

### 5.2 Run 2?

**No** (2026-10-24). The result is the expected one (a positive estimate confirmed), every prediction matched in both tiers including the exact counts, the independent self-check holds, and the one inferred item is checked by the absence of L0 outputs.

## 6. Run 2 — fresh AI session (optional)

Not done.

## 8. Verdict — AI

Jingsong may overrule any verdict at any time; record an override here with its date and reason.

**Stage-3 estimate:** positive (scoped: per-file size, soft). **Outcome class:** **true positive** (positive, caps).

**Claim tested:** B1: for a major LCS compaction, every output Data.db except the last has size in `(S, S + one partition + granularity]`, where `S = sstable_size_in_mb * 1 MiB`; the number of outputs is about `ceil(total / S)` and moves inversely with `S`. "Confirmed" below means this claim held.

| Tier | Verdict (B2g / B3g row) | Effect on the constraint | Basis | Date |
|---|---|---|---|---|
| Unit | **Confirmed** — B2g row 1 (single-file size capped by the operand; count ~ total/S) | caps (per file, soft by one partition; bypass: a partition larger than the limit is never split) | run 1 + self-check | 2026-10-24 |
| Cluster | **Confirmed** — B3g row 1 (count ~ 400/S, non-final files within `S` + one partition; peak du ~ 2x live regardless of `S`) | caps (per file, soft); does not bound total or transient disk | run 1 + self-check | 2026-10-24 |

**Positive control** (not required for a positive estimate; the negative controls moved as predicted): `Long.MAX_VALUE` gave 1 file (unit); an STCS table gave 1 file and the 60 MiB partition gave a 75.6 MB file (cluster).

**What stays on `pc12`:** `~/stage4-sml1/` (the tree with the copied harness files and `build/`; `run1/` full logs and CSVs; `shake/`, `shake-cluster/`, `shake-cluster.out`; `logs/`), about 480 MB, nothing running. The node data directory was removed. No `CassandraDaemon`, `ant`, loader or sampler process is left (`ps` checked 2026-10-24 about 12:05); ports 7000, 7199, 9042 are free.

**Feedback filed:** the case file's section D is filled (case file untracked, so no commit), together with the dated audit amendments B2i and B3i in the file (sha256 in §1). `_INDEX.md`, the CSV and `predicted-negative.md` are left to the human.
