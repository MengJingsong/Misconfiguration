# lcs-level-capacity-shouldSwitchWriterInCurrentLocation-totalWrittenInLevel--autonomous — stage-4 results  <!-- file: results/lcs-level-capacity-shouldSwitchWriterInCurrentLocation-totalWrittenInLevel--autonomous.md; the stem ends in --guided or --autonomous -->

> **Case:** [`lcs-level-capacity-shouldSwitchWriterInCurrentLocation-totalWrittenInLevel--autonomous`](../../stage3-ai-deep-read/cases/lcs-level-capacity-shouldSwitchWriterInCurrentLocation-totalWrittenInLevel--autonomous.md)
>
> **Status:** verdict filed (2026-10-24) — run 1 done at both tiers, self-checked, no run 2
>
> **Outcome class:** **true negative** (estimate `negative`, effect `does not cap`) — [definition](../README.md#outcome-class)
>
> **Agent:** autonomous (the suffix of the case-file stem). "§9a" below means each tier's predictions and conclusions table: B2f and B2g (unit), B3f and B3g (cluster); "§9b–§9e" means B2a–B2e or B3a–B3e; the case file's feedback section is its section D.

## 1. Before run 1 — design audit and freeze

| Field | Content |
|---|---|
| **Case-file version** | Base repository commit `9e6ee79` (the case file is **untracked** in the working tree at this date, so no commit holds it; the human closes the commit). **sha256 of the whole file after the audit's amendments (B2i and B3i, dated 2026-10-24): `8796b85bfe4f58ad3aa3aad355fbdb273603f07d515d35371d9f31b192c6829e`.** Recorded 2026-10-24 before any reading; the prediction and conclusions tables (B2f, B2g, B3f, B3g, as amended) are frozen at this hash. The hash covers the file as it stood before section D (the stage-4 feedback) was filled; D is the only later change. |
| **Harness** | `harness/lcs-level-capacity-shouldSwitchWriterInCurrentLocation-totalWrittenInLevel--autonomous/`: `WriterHarnessBase.java`, `LcsFanoutCapacityTest.java`, `unit-run.sh`, `analyze_unit.py`, `cluster-run.py`, `loader.py`, `analyze_cluster.py`, `selfcheck.py`, `README.md`; written after the freeze; not committed (final md5s: `lcs-level-capacity-shouldSwitchWriterInCurrentLocation-totalWrittenInLevel--autonomous/run1/harness.md5.final`; `run1/unit/harness.md5` was taken when the unit run started, before the cluster analyzer and `selfcheck.py` existed) |
| **Tiers and values** | **Unit (B2):** `fanout_size` F ∈ {2, 4, 10, 41} at `S = total/50` (F = 100 withdrawn: B2i.6); positive control `S` ∈ {total/20, total/50, total/100} at F = 10. **Cluster (B3):** F ∈ {2, 10, 31} at `sstable_size_in_mb` = 10 (F = 100 withdrawn: B3i.7) on 600,000 rows of 1 KiB; positive control `sstable_size_in_mb` = 40 at F = 10; F = 10 repeated once. |
| **Audit bottom line** | **Ready after amendments** — 2026-10-24 |

### 1.1 Design audit

Estimate: **negative** (the line-78 comparison only labels levels; usage does not follow the level capacity). Audited against `cassandra/cassandra-5.0.9/` (`git status` of it clean at `9e6ee79`; `build.xml` `base.version` 5.0.9). Citations re-read in the pinned source: `MajorLeveledCompactionWriter.java:30-113`, `LeveledCompactionTask.java:31-54`, `LeveledManifest.java:185-193`, `LeveledCompactionStrategy.java:52-56, 60-90, 183-193, 570-625`, `CompactionStrategyManager.java:325, 640-643`, `ColumnFamilyStore.java:3214-3218`, `CompactionAwareWriter.java:130-235`, `SSTableWriter.java:205-212`, `CompactionAwareWriterTest.java:55-300`: all hold at the cited lines.

| Group | Check | Rating (Met / Partly / Not met) | Note (section checked) |
|---|---|---|---|
| A. Core question | constrained quantity is memory or disk bytes | Met | A2: sstable bytes on disk, as a scheduling target; memory is not touched (A4). |
| A. Core question | knob varied, ≥ 3 values incl. default | Partly → Met | B2b: F = 2, 4, 10 (default), 100; B3b: 2, 10, 100. F = 100 is rejected by `validateOptions` (`LeveledCompactionStrategy.java:608-621`: `fanout^8 × size` must fit a `long`); replaced by 41 (unit) and 31 (cluster) in B2i.6 / B3i.7, still four and three values. |
| A. Core question | real resource measured, not only the counter | Met | B2d/B3d: file lengths, `du`, level counts; the in-writer counter is read by reflection in the unit tier and not claimed on a live node. |
| A. Core question | usage driven to the limit and past it | Met (with a note) | F = 2 and 4 exceed the nominal capacity of levels 1 to 4 many times over (50 and 65 files); the F = 100 arm no longer exists (invalid option, B2i.6); F = 41 exceeds L1 once. |
| A. Core question | **positive control for a negative estimate** | Met | B2h/B3h: the same writer and instruments with `sstableSize` (unit) and `sstable_size_in_mb` (cluster) varied: a knob on the same resource that does move file size and count while total bytes stay flat. |
| B. Logic | each step says what it establishes | Met | B2e/B3e. |
| B. Logic | prediction stated in numbers or a clear relation | Partly → Met | B2f/B3f are numeric, but the cluster F = 2 histogram was wrong for about 65 files (L5 holds 32, the rest go to L6); corrected in B3i.1 from the level rule alone, before any reading. |
| B. Logic | every plausible outcome has a conclusions row with its evidence | Met | B2g/B3g cover constant, monotone, data loss, control moves, control flat, limit never reached. |
| B. Logic | confirmation needs ceiling-follows-knob and direct disallow evidence | Met | For a "does not cap" claim: flat N and B across F with the control moving; the level-increment event is read per call (B2d). |
| B. Logic | alternative explanations and their controls | Met | B2h/B3h: fixed seed and input, same `sstableSize`, `sstableSize` sweep, repeat of F = 10. |
| C. Specific | a human can follow it from the intro and B1 | Met | A3 and B1. |
| C. Specific | an AI can run B2/B3 without re-deriving the code path | Partly → Met | How F reaches the writer, why `populate` cannot build the input on an LCS table, and the level-stamp timing were not stated; supplied in B2i. |
| C. Specific | knob, values, workload, commands, observables, sampling, stop conditions exact | Partly → Met | Loader, flush cadence, arm order, read-back and sampler target supplied in B3i; paths (`/local/work/...`) do not exist here (environment deviation). |
| D. Runnable | harness and environment prerequisites exist or are listed | Met | `ant build-test` tree, bundled Python driver, `nodetool`, `sstablemetadata`; unit test, loader, run scripts are step-1 work. |
| D. Runnable | workload arithmetic reaches the limit (data, time, disk, memory) | Met | 215 MB (unit) and 650 MB (cluster) of data against `S` of 4 MiB and 10 MiB; `pc12` `/` has about 47 GB free; the largest arm about 1.5 GB. |
| D. Runnable | load-bearing citations spot-checked | Met | List above. |

| # | Recommendation | Applied? | Why |
|---|---|---|---|
| 1 | Build the input on an STCS table, then `ALTER` to LCS with F; assert `getLevelFanoutSize() == F` | Applied, B2i.1, 2026-10-24 (case file untracked; sha256 above) | `populate`'s `forceMajorCompaction()` on an LCS table would write about 200 files. |
| 2 | Own `populate` (distinct 1 KiB blobs, uncompressed); "20000 rows" means 20,000 partitions | Applied, B2i.2 | The helper's identical 5,000-byte payload is hidden by LZ4 and is about 1 GB per arm. |
| 3 | State the level-stamp timing; add control histograms | Applied, B2i.3 | Makes the histogram predictions derivable. |
| 4 | Correct the cluster F = 2 histogram (L5 = 32, L6 = remainder) | Applied, B3i.1 (marked on B3f) | Wrong for about 65 files; source-derivable. |
| 5 | Keep auto-compaction off through `nodetool compact` | Applied, B3i.2 | `getMaximalTask` returns `null` if any sstable is already compacting. |
| 6 | Driver loader, flush cadence, table per arm, paged read-back, `du` on the table directory | Applied, B3i.3 to B3i.6 | Unspecified; `SELECT count(*)` would time out at 10 s. |
| 7 | F = 100 is not a valid table option; use F = 41 (unit, 1 MiB) and F = 31 (cluster, 10 MiB) | Applied, B2i.6 and B3i.7 (marked on B2f and B3b), 2026-10-24, before any run or reading | Source-derivable (`validateOptions`); the "all in L1" arm is lost, the other arms still exceed the L1 capacity. |
| 8 | Paths in B2a/B3a/B4 refer to trees that do not exist here | Left for stage 3 | Cosmetic. |

**Agreement criteria** — not applicable unless run 2 is chosen (§5.2).

## 2. Environment

| Field | Run 1 | Run 2 (fresh AI session, if done) |
|---|---|---|
| Date | 2026-10-24 (unit 11:47–11:49 MDT, cluster 11:57–12:02 MDT) | not done |
| Node (CloudLab name and type) | `pc12` = `node1.jason92-320876.misconfiguration-pg0.cloudlab.umass.edu`, 40 cores, 251 GiB | |
| OS and kernel (`uname -r`) | Ubuntu 22.04.2 LTS, `5.15.0-187-generic` | |
| JDK (`java -version`) | OpenJDK 11.0.32.1 | |
| Ant (`ant -version`) | 1.10.12 | |
| Local source copy (from `cassandra/cassandra-5.0.9/` at repository commit …) | `~/stage4-lcl2/tree` made by `copy-source.sh` from repository commit `9e6ee79` (local baseline `d0b7384`, `git describe` = `cassandra-5.0.9`); `ant build-test` 1 min 12 s; the two harness Java files added under `test/unit/.../compaction/writers/`. The cluster node ran from this tree's `build/`. Nothing built in the repository's `cassandra/cassandra-5.0.9/`. | |
| Case-file commit / harness commit | case file untracked at `9e6ee79` (sha256 `8796b85b…829e`, §1); harness uncommitted (md5s in `run1/harness.md5.final`) | |
| Storage for node data | `/dev/sda3`, ext3, 63 GB (47 to 51 GB free); node data under `~/stage4-lcl2/node` (removed afterwards); unit test data under the tree's `build/test/cassandra` | |
| Full logs (path, outside the repo) | `pc12:~/stage4-lcl2/run1/{unit,cluster}/` (full `ant.log`, per-call CSVs, per-arm `system.log.segment`, `sstablemetadata.out`, `cluster.out`); builds in `pc12:~/stage4-lcl2/logs/`; excerpts in `lcs-level-capacity-shouldSwitchWriterInCurrentLocation-totalWrittenInLevel--autonomous/run1/` | |

**Environment deviations (none changes B1):** (1) the filed paths (`/local/work/...`) do not exist; trees and data are under `~/stage4-lcl2/`. (2) The cluster load is a Python driver script, not `cassandra-stress` (B3i.3). (3) `MAX_HEAP_SIZE=2G HEAP_NEWSIZE=512M`, `compaction_throughput: 0MiB/s` and `auto_snapshot: false` were set (`run1/cluster/cassandra.yaml.used`, environment) but not read back from the live node; no reading depends on them. (4) A shakedown at `STAGE4_PARTS=400` ran before run 1 to check the unit instruments; its first version still contained the F = 100 arm and **failed with** `ConfigurationException: At most 9223372036854775807 bytes may be in a compaction level; your maxSSTableSize must be absurdly high to compute 10485760000000000000000` (= 100^8 x 1 MiB), confirming the B2i.6 / B3i.7 finding empirically; that log was overwritten by the repeat shakedown and is quoted here from the session. It is not a reading. (5) `ulimit -n` raised to 100000 inside `cluster-run.py`.

## 3. Runbook defects

| # | Run | Step | Problem | Fix | Decision (date) | Case-file commit with the fix |
|---|---|---|---|---|---|---|
| 1 | audit | B2b, B3b (F = 100) | `fanout_size = 100` is rejected by `validateOptions` for every `sstable_size_in_mb >= 1` (`fanout^8 x size` must fit a `long`, `LeveledCompactionStrategy.java:608-621`); the arm cannot be created. | F = 41 (unit, 1 MiB) and F = 31 (cluster, 10 MiB), the largest valid values: B2i.6, B3i.7. | 2026-10-24, before the freeze | none (case file untracked) |
| 2 | audit | B3f (F = 2 line) | L5 holds 32 files, so the line "L5 = remaining" is wrong for about 65 files. | Corrected prediction: B3i.1. | 2026-10-24, before the freeze | none |
| 3 | audit | B3c, B3e | Re-enabling auto-compaction before `nodetool compact` can make `getMaximalTask` return `null`. | Auto-compaction stays off: B3i.2. | 2026-10-24, before the freeze | none |
| 4 | audit | B2e / B2c | `populate` on an LCS table, and its identical-payload rows. | STCS input, then `ALTER` to LCS; own populate: B2i.1, B2i.2. | 2026-10-24, before the freeze | none |

No defect was found while running; no tier restarted. **One prediction in the frozen text was wrong in a way the audit did not catch** (§4.2 part 6): the data volume.

## 4. Run 1

**Scope:** unit tier, 6 arms in one JVM (F = 2, 4, 10, 41 at `S` = total/50; `S` = total/20 and total/100 at F = 10); cluster tier, 5 arms in one node lifetime (F = 10 (a), 2, 31 at `sstable_size_in_mb` = 10; `sstable_size_in_mb` = 40 at F = 10; F = 10 (b)). **Command log:** `lcs-level-capacity-shouldSwitchWriterInCurrentLocation-totalWrittenInLevel--autonomous/run1/unit/session.log`, `run1/cluster/session.log`; analyzer output `run1/analyze_unit.out`, `run1/analyze_cluster.out`; independent self-check `run1/selfcheck.out`.

### 4.1 Readings

**Unit tier** (`run1/analyze_unit.out`, `run1/unit/arms.txt`, `files-*.csv`, `switches-*.csv`). Input: 20,000 partitions x 10 rows x 1 KiB, one uncompressed sstable of about 208.5 MB, converted to LCS with the F of the arm (`getLevelFanoutSize()` == F asserted before the writer was built); the JUnit run ended `BUILD SUCCESSFUL`.

| Test or assertion | Result | Evidence (file) |
|---|---|---|
| F sweep at `S` = total/50: files N | 50 / 50 / 50 / 50 for F = 2 / 4 / 10 / 41 | `arms.txt` |
| F sweep: total bytes B | 208,516,873 / 208,438,059 / 208,444,678 / 208,439,423 (spread 78,814 B, under one file of 4.2 MB); rows 200,000 and 20,000 partitions in every arm | `arms.txt`, `analyze_unit.out` |
| F sweep: level histogram | F=2: 2 / 4 / 8 / 16 / 20 (L1 to L5); F=4: 4 / 16 / 30; F=10: 10 / 40; F=41: 41 / 9 | `files-f*.csv` |
| Every non-final file in `(S, S + maxPartition]` | holds in all arms (maxPartition 10,428 B) | `analyze_unit.out` |
| No level-0 output; no exception | holds | `analyze_unit.out` |
| Level steps in the call log | each `currentLevel` increment coincides with the reset of `totalWrittenInLevel`, when the cumulative bytes crossed `F^n x S` | `analyze_unit.out`, `selfcheck.out` |
| Control at F = 10, `S` = total/20 / total/50 / total/100 | N = 20 / 50 / 100; B = 208,524,770 / 208,444,678 / 208,449,758; mean non-final file within 1 % of `S` | `analyze_unit.out` |

**Cluster tier** (`run1/analyze_cluster.out`, `run1/cluster/<arm>/`). 600,000 rows of 1 KiB, 6 flushes (6 L0 files), input about 634.55 MB (605 MiB); major compaction by `nodetool compact`; sampler every 0.25 s on the table directory.

| Capacity value | Run | Observable (B3d) | Reading | Evidence (file) |
|---|---|---|---|---|
| F = 10, `sstable_size_in_mb` = 10 (a) | A | files; levels; live bytes; peak table-dir bytes; read-back | 61; L1 10 / L2 51; 634,761,121; 1,273,951,171 (2.01 x input); 600,000 / 600,000 | `cluster/f10a/` |
| F = 2 | A | same | 61; L1 2 / L2 4 / L3 8 / L4 16 / L5 31; 634,758,356; 1,274,533,453 (2.01 x); 600,000 | `cluster/f2/` |
| F = 31 | A | same | 61; L1 31 / L2 30; 634,763,173; 1,271,448,663 (2.00 x); 600,000 | `cluster/f31/` |
| F = 10, `sstable_size_in_mb` = 40 | control | same | 16; L1 10 / L2 6; 634,759,044; 1,282,159,040 (2.02 x); 600,000 | `cluster/s40/` |
| F = 10 (b), the repeat | A | same | 61; L1 10 / L2 51; 634,758,501; 1,287,815,477 (2.03 x); 600,000 | `cluster/f10b/` |
| every arm | | `Compacted` lines; ERROR; largest file | one `Compacted` line, no ERROR; largest file 10,486,3xx B at 10 MiB (`S` + about 0.5 KB) and 41,943,926 B at 40 MiB | `system.log.compaction-lines`, `summary.json` |

### 4.2 Conclusion and logic

1. **Validity** — valid. The check exceeded the nominal capacity of levels many times over: at F = 2 the L1 capacity is 20 MiB (two files) and 605 MiB were written, with 61 files spread over five levels [observed: `cluster/f2/levels.txt`]; the unit F = 41 arm crossed the L1 capacity once [observed: `files-f41.csv`]. F = 100 could not be set (§3 defect 1), so no arm leaves everything in L1. Hold-fixed settings: the same seeds and input in every arm (input bytes 634,548,224 to 634,557,125) [observed: `summary.json`]; the option and F as applied [observed: `compaction_option` from `system_schema.tables`]; auto-compaction disabled, one `Compacted` line per arm [observed: `selfcheck.out`]; `getLevelFanoutSize()` == F in the unit arms [observed: `arms.txt` `fanoutSeenByWriter`]; the major writer was used [inferred: no L0 output and levels from L1, `LeveledCompactionTask.java:51-53`].
2. **Readings** — nothing contradicts another. File count and total bytes are identical across F in both tiers; peak table-directory bytes are 2.00 to 2.03 x the input in all five cluster arms, including the control. One reading **does not match the numbers in the frozen B3f**: 61 files, not "about 65 +- 2" (§6 below).
3. **Matched row** — unit B2g row 1: "N, B constant across F; only level histogram changes as predicted | Claim confirmed: capacity only labels levels, does not bound disk" [observed: N = 50 in all four F arms, B spread 78,814 B, histograms equal the F^n fill rule and the B2f predictions 2/4/8/16/20, 4/16/30, 10/40; F = 41 as amended 41/9]. The control row also holds: "Control (varying `sstableSize`) changes N inversely and per-file bytes track `sstableSize` while B stays flat | Positive control works" [observed: N = 20 / 50 / 100, B flat]. Cluster B3g row 1: "Total/peak bytes and file count constant across F; level histogram changes as predicted | Confirmed: level capacity doesn't cap disk" [observed: N = 61 and B within 4,817 B in the four F = 2 / 10 / 31 / 10 arms, peak ratio 2.00 to 2.03; histograms follow the level rule exactly], with the control row "file size and count follow `sstable_size_in_mb`, total constant" [observed: 16 files of about 40 MiB, B within 4,129 B of the others].
4. **Excluded rows** — "N or B changes monotonically with F" (Refuted): N = 50 / 50 / 50 / 50 and 61 / 61 / 61 / 61, B spread under 79 KB in 208 MB and under 5 KB in 635 MB [observed]. "Rows < 20000 or exception when a level is over capacity" / "data loss or compaction error at over-capacity": 200,000 rows and 600,000 / 600,000 read back, no ERROR in any log segment [observed]. "Control did not move N or file size" (Not confirmed): it moved. "F = 100 leaves everything in L1": withdrawn (amended). "Fewer than ~20 files so F = 2 never exceeds L1 capacity": 50 and 61 files, L1 capacity exceeded [observed].
5. **Observed vs. inferred** — inferred: that the major writer was the code run on the node (the unit tier drives it directly), from the absence of L0 outputs; that the 'fill rule' used by the analyzer is the writer's rule (also checked against the recorded `currentLevel` / `totalWrittenInLevel` steps in the unit call log, so observed). Everything else is observed.
6. **Deviations and gaps** — (a) **The frozen B3f numbers for the cluster tier are off by the data volume**: B3c / B3f assume about 650 MB (65 files at 10 MiB), but 600,000 rows of 1 KiB occupy 605 MiB (634.76 MB), which is 61 files; the F = 2 line (amended in B3i.1 to L5 = 32, L6 = about 3) therefore reads L5 = 31 with no L6 here. The error is arithmetic (decimal vs binary megabytes plus overhead), independent of any reading, but it was not caught in the audit and the prediction was not edited afterwards. The B3g rows that decide the verdict state relations (constant across F, histogram changes as predicted, control moves), and those held; the numeric sub-predictions "about 65 +- 2 files" and "L5 = 32, L6 = the remainder" did not. This is the item to overrule if a stricter reading of "Confirmed" is wanted. (b) F = 100 untested (not a valid option). (c) Each arm ran once, except F = 10 which ran twice with the same result. (d) Heap and throughput not read back (§2). (e) Level labels are read per file; the `nodetool tablestats` per-level line is in `tablestats.after`.
7. **Core question** — usage did not follow the level capacity. Changing `fanout_size` from 2 to 41 (unit) and 2 to 31 (cluster) changed only which level number each output file carried; the number of files and the total bytes written stayed the same (50 files / 208.4 MB, 61 files / 634.76 MB), every row was written and read back, and the compaction never stopped or truncated at a level capacity, even where the capacity of the low levels (20 MiB at F = 2) was exceeded by a factor of about 30. The control shows the workload and instruments can move file size and count: `sstableSize` / `sstable_size_in_mb` changes N (20 / 50 / 100; 16 vs 61) with total bytes flat. Peak disk was about twice the input in every arm, independent of F.

**Conclusion (one line):** unit B2g row 1 and cluster B3g row 1 (capacity only labels levels; does not bound disk; control works) — confirmed, with the cluster tier's numeric count and F = 2 histogram predictions missed for the reason in part 6(a).

## 5. Self-check of run 1 — AI

### 5.1 Check of run 1's conclusion

`run1/selfcheck.out` re-derives the numbers independently of `analyze_*.py` (levels from the per-call log, N from the switch count, level steps against `F^n x S` using `totalWrittenInLevel`; cluster levels re-parsed from `sstablemetadata.out`, the `Compacted` line's output list against the files on disk, peak bytes from `du.csv`): **all checks hold** (unit 6 arms, cluster 5 arms).

| Part | Holds? (yes / no) | Note (file re-read) |
|---|---|---|
| 1. Validity | yes | `selfcheck.out`: one `Compacted` line per arm; `arms.txt` shows `fanoutSeenByWriter` == F; levels cross-checked from the call log |
| 2. Readings | yes | counts, byte sums, level histograms agree between `files-*.csv`, the call log and `sstablemetadata.out`; the one numeric mismatch with B3f is recorded in part 6(a) |
| 3. Matched row | yes | `analyze_unit.out`: all PASS; `analyze_cluster.out`: 37 PASS, 1 FAIL (the numeric N = 65 +- 2 check, part 6(a)); the matched B3g row's relations hold |
| 4. Excluded rows | yes | N and B constant, no data loss, control moved |
| 5. Observed vs. inferred | yes | one inferred item (major writer on the node), supported by no L0 output |
| 6. Deviations and gaps | yes | volume error documented and not hidden; F = 100 invalid |
| 7. Core question — the steps from reading to answer follow the audited logic | yes | knob varied (4 + 3 values), usage compared, control moved, no truncation |

### 5.2 Run 2?

**No** (2026-10-24). The result is the expected one for a negative estimate (a true negative), both tiers agree, the repeat arm (F = 10 b) reproduced the first, and the independent self-check holds. The open point is the strictness of "Confirmed" given the missed numeric prediction (part 6(a)); that is a judgement on the frozen text, not something a second run would change.

## 6. Run 2 — fresh AI session (optional)

Not done.

## 8. Verdict — AI

Jingsong may overrule any verdict at any time; record an override here with its date and reason.

**Stage-3 estimate:** negative. **Outcome class:** **true negative** (negative, does not cap).

**Claim tested:** B1 (negative): total disk occupied by the output of an LCS major compaction does not follow `maxBytesForLevel` (`sstable_size_in_mb` x `fanout_size`^level): changing `fanout_size` changes only the level labels of the output sstables, not their count or total bytes, and data far beyond the nominal capacity of a level is still written. "Confirmed" below means this claim held.

| Tier | Verdict (B2g / B3g row) | Effect on the constraint | Basis | Date |
|---|---|---|---|---|
| Unit | **Confirmed** — B2g row 1 (N, B constant across F; only the histogram changes; positive control works) | does not cap | run 1 + self-check | 2026-10-24 |
| Cluster | **Confirmed** — B3g row 1 (N, B and peak bytes constant across F; histogram follows the level rule; control moves) — with the numeric deviation of §4.2 part 6(a) | does not cap | run 1 + self-check | 2026-10-24 |

**Positive control:** the same writer and instruments moved file count and size when the per-file knob changed: unit `sstableSize` = total/20, /50, /100 gave 20, 50, 100 files with total bytes flat (208,524,770 / 208,444,678 / 208,449,758); cluster `sstable_size_in_mb` = 40 gave 16 files against 61 at 10 MiB with total bytes unchanged (634,759,044 vs 634,761,121). A knob that does bind on the same resource (per-file size) shows up in the readings, so the flat result for `fanout_size` is not a workload that could not show an effect.

**What stays on `pc12`:** `~/stage4-lcl2/` (the tree with the copied harness files and `build/`; `run1/` full logs and CSVs; `shake/`; `logs/`), about 480 MB, nothing running. The node data directory was removed. No `CassandraDaemon`, `ant`, loader or sampler process is left (`ps` checked 2026-10-24 about 12:05); ports 7000, 7199, 9042 are free.

**Feedback filed:** the case file's section D is filled (case file untracked, so no commit), together with the dated audit amendments B2i and B3i in the file (sha256 in §1). `_INDEX.md`, the CSV and `predicted-negative.md` are left to the human.
