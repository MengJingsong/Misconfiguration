# DEFAULT_SMALLEST_SSTABLE_BYTES-shouldSwitchWriterInCurrentLocation-getEstimatedOnDiskBytesWritten--autonomous — stage-4 results  <!-- file: results/DEFAULT_SMALLEST_SSTABLE_BYTES-shouldSwitchWriterInCurrentLocation-getEstimatedOnDiskBytesWritten--autonomous.md; the stem ends in --guided or --autonomous -->

> **Case:** [`DEFAULT_SMALLEST_SSTABLE_BYTES-shouldSwitchWriterInCurrentLocation-getEstimatedOnDiskBytesWritten--autonomous`](../../stage3-ai-deep-read/cases/DEFAULT_SMALLEST_SSTABLE_BYTES-shouldSwitchWriterInCurrentLocation-getEstimatedOnDiskBytesWritten--autonomous.md)
>
> **Status:** verdict filed (2026-10-25) — run 1 done at both tiers, self-checked, no run 2
>
> **Outcome class:** **true negative** (estimate `negative`, effect `does not cap`) — [definition](../README.md#outcome-class)
>
> **Agent:** autonomous (the suffix of the case-file stem). "§9a" below means each tier's predictions and conclusions table: B2f and B2g (unit), B3f and B3g (cluster); "§9b–§9e" means B2a–B2e or B3a–B3e; the case file's feedback section is its section D.

## 1. Before run 1 — design audit and freeze

| Field | Content |
|---|---|
| **Case-file version** | Base repository commit `627b1ec` (the case file is **untracked** in the working tree at this date, so no commit holds it). The file as filed by the stage-3 agent had sha256 `8a38d8546981dd842d72666c79a7b6b2fda52be5789e5e87e1644d6b95c52d01`. **sha256 of the whole file after the audit's amendments (A3 step 8 and C notes, B2i, B3i, inline corrections in B3c, B3f and B3g, all dated 2026-10-25): `85fd62603142696ba3ccd5d5e7f2512dc195fd811c3400e8d0bf82f3a89b455c`.** Recorded 2026-10-25 04:42 UTC, before any reading and before any harness code existed (`run1/frozen.sha256`); the prediction and conclusions tables (B2f, B2g, B3f, B3g) are frozen at this hash. Section D (the stage-4 feedback) is the only later change; the hash covers the file as it stood before D was filled. |
| **Harness** | `harness/DEFAULT_SMALLEST_SSTABLE_BYTES-shouldSwitchWriterInCurrentLocation-getEstimatedOnDiskBytesWritten--autonomous/`: `SplitWriterHarnessBase.java`, `SplittingConstantProbeTest.java`, `unit-run.sh`, `analyze_unit.py`, `cluster-run.py`, `loader.py`, `analyze_cluster.py`, `selfcheck.py`, `README.md`; written after the freeze; not committed (md5s: `run1/harness.md5.final`). |
| **Tiers and values** | **Unit (B2):** `smallestSSTable` (5-argument constructor) in {0, 5e6, 50e6 (the default), 10 x T}, T about 208 MB, uncompressed; plus 50e6 on a compressed table; plus the 39.6 MB input at 50e6; positive control `MaxSSTableSizeWriter` at m = 20e6 and 40e6. **Cluster (B3):** the constant edited in three builds, 5e6 / 50e6 (default) / 500e6, on 2,000,000 rows of 1 KiB (T about 2.085e9); arms: plain `nodetool compact`, `compact -s`, `compact -s` repeated, `compact -s` on a compressed table, small data (T about 92e6) with `-s`, and the positive control LCS `sstable_size_in_mb` = 100 and 50. |
| **Audit bottom line** | **Ready after amendments** — 2026-10-25 |

### 1.1 Design audit

Estimate: **negative** (the constant divides the output of a split STCS major compaction; it does not bound bytes). A negative-estimate file needs a positive control (group A); B2h/B3h supply them (`MaxSSTableSizeWriter`, LCS `sstable_size_in_mb`). Audited against `cassandra/cassandra-5.0.9/` (`git status` of it clean at `627b1ec`; `base.version` 5.0.9). Citations re-read in the pinned source and holding at the cited lines: `SplittingSizeTieredCompactionWriter.java:42, 49-79, 81-92, 94-110`; `CompactionAwareWriter.java:46-80, 170-204 (185), 265-298 (282)`; `SizeTieredCompactionStrategy.java:205-214, 336-367`; `Compact.java:33-62`; `ColumnFamilyStore.java:1698-1703, 2514-2520`; `CompactionStrategyManager.java:1076`; `SequentialWriter.java:310-317`; `CompressedSequentialWriter.java:125-132`; `MaxSSTableSizeWriter.java:36-79`. Newly read for the open caveat: `CompactionTask.java:95-125, 147-153, 375-452, 469-472`, `Directories.java:517-569`, `SSTableReader.java:541-547, 983-986`, `Config.java:338-344`.

| Group | Check | Rating (Met / Partly / Not met) | Note (section checked) |
|---|---|---|---|
| A. Core question | constrained quantity is memory or disk bytes | Met | A2/B1: bytes of each split output sstable (disk); the constant is never compared to bytes (used at line 72 only to count ratios). |
| A. Core question | knob varied, ≥ 3 values incl. default — or another approach, with the reason | Partly → Met | The constant is not settable at runtime; B2b has 0 / default / 10xT and B3b has two jars (5e6 and default). B2i.4 adds 5e6 to the unit tier and B3i.2 adds a third jar (500e6), so cluster values are 5e6 / 50e6 / 500e6 plus the no-`-s` run. |
| A. Core question | real resource measured, not only the counter (gap named) | Met | B2d reads file lengths and the operand (equal for uncompressed files); B3d samples `du` of the real table directory every 0.25 s and `ls` of each output; B3i.6 adds RssAnon and heap as context. The compressed gap (operand is `chunkOffset`) is bounded in B2i.4. |
| A. Core question | usage driven to the limit and past it | Met | Every arm drives the check to `true` (2 to 19 switches per arm) and the last piece runs past its own target; B3i.4 requires the DEBUG "Switching writer" lines as direct evidence. |
| B. Logic | each step says what it establishes | Met | B2e/B3e list steps with purpose. |
| B. Logic | prediction stated in numbers or a clear relation | **Not met → Met** | B3f counted 7 and 10 outputs; the source gives 6 and 9 (the listed ratios themselves are six and the 9th is 0.0019), B3f's small-data bullet contradicts itself. Corrected, with the derivation, in B3i.1 and inline. B2f was consistent; B2i.2-3 sharpen it. |
| B. Logic | every plausible outcome has a conclusions row with its evidence | Partly → Met | B2g/B3g cover sum changes, flat, piece count off, last piece, overshoot. The row "Not enough space at half of D free" cannot occur as worded (the task-level check asks for all of T first); replaced by a row on the bytes the task-level check asks for (B3i.5). |
| B. Logic | confirmation needs ceiling-follows-knob and direct disallow evidence | Met | The knob moves the count (ceiling on piece size) and the per-call log / DEBUG lines record every `true` return of line 84. |
| B. Logic | alternative explanations and their controls | Met | `MaxSSTableSizeWriter` and LCS as binding comparators, unsplit run as baseline, repeat for noise, compressed repeat. |
| C. Specific | a human can follow it from the intro and B1 | Met | A3 and B1 are clear. |
| C. Specific | an AI can run B2/B3 without re-deriving the code path | Partly → Met | The exact input sizes, gates, load, arms, log lines and the control parameters were missing; supplied in B2i/B3i. |
| C. Specific | knob, values, workload, commands, observables, sampling, stop conditions exact | Partly → Met | `/local/$USER/...` paths do not exist here (deviation, §2); `jstat` cannot attach to the node (deviation, §2). |
| D. Runnable | harness and environment prerequisites exist or are listed | Met | `ant build-test` tree, bundled Python driver, `nodetool`, `jcmd`; unit test, loader and drivers are step-1 work. |
| D. Runnable | workload arithmetic reaches the limit (data, time, disk, memory) | Partly → Met | With T about 2.085e9 the default constant yields 6 pieces and the rule has no time or memory problem; peak 2 x T = 4.2 GB against 51 GB free on `pc12`'s `/`. The case's unit sizes reach 3 pieces only if `T >= 200e6` (gate in B2i.1). |
| D. Runnable | load-bearing citations spot-checked | Met | List above. |

| # | Recommendation | Applied? | Why |
|---|---|---|---|
| 1 | Read `CompactionTask`'s own space check; state its effect on the claim (the open caveat) | Applied, A3 step 8 / C / B3i.5, 2026-10-25 (case file untracked; sha256 above) | It asks for the whole input T, independent of the constant; it is a different constraint and does not change B1. |
| 2 | Correct the ratio counts and sizes (6 / 9 outputs, not 7 / 10), the contradictory small-data bullet | Applied, B3i.1 and inline | The case's own listed ratios are six; 2^-9 is the 9th ratio. A source-only error, independent of any reading. |
| 3 | Replace the row "Not enough space at half of D free" | Applied, B3g inline / B3i.5 | The task-level check fires first. |
| 4 | Exact input and validity gates for each tier | Applied, B2i.1, B3i.1 | A run outside the gate cannot reach the predicted piece count; it is Invalid, not Refuted. |
| 5 | Add a third constant value (500e6) and a fifth unit value (5e6) | Applied, B2i.4, B3i.2 | Group A asks for at least three values including the default. |
| 6 | Exact positive controls (`MaxSSTableSizeWriter` 20e6 and 40e6; LCS 100 and 50) | Applied, B2i.5, B3i.3 | Group A: a negative file needs a positive control with the same workload and instruments. |
| 7 | DEBUG "Switching writer" lines as the direct disallow evidence in the cluster tier; they land in `debug.log` | Applied, B3i.4 | `system.log` has an INFO threshold. |
| 8 | Heap and RssAnon as context only, judged against the repeat spread | Applied, B3i.6 | GC noise would make a bare 10% threshold unreliable. |
| 9 | `/local/$USER/...` paths and `jstat` do not apply on the test node | Left for stage 3 (recorded as environment deviations, §2) | Cosmetic. |

**Agreement criteria** — not applicable unless run 2 is chosen (§5.2).

## 2. Environment

| Field | Run 1 | Run 2 (fresh AI session, if done) |
|---|---|---|
| Date | 2026-10-24 MDT = 2026-10-25 UTC (unit 22:53–22:56 MDT, cluster 22:56–23:19 MDT) | not done |
| Node (CloudLab name and type) | `pc12` = `node1.jason92-320876.misconfiguration-pg0.cloudlab.umass.edu`, 40 cores, 251 GiB; shared with another run (tag `cdc`, not touched) | |
| OS and kernel (`uname -r`) | Ubuntu 22.04.2 LTS, `5.15.0-187-generic` | |
| JDK (`java -version`) | OpenJDK 11.0.32.1 | |
| Ant (`ant -version`) | 1.10.12 | |
| Local source copy (from `cassandra/cassandra-5.0.9/` at repository commit …) | `~/s4-ss/treeA`, `treeB`, `treeC`, each made by `copy-source.sh` from repository commit `627b1ec` (local baseline tagged `cassandra-5.0.9`); tree A unmodified (`ant build-test`, 1 min 17 s, unit tier and the default-constant node); tree B has line 42 edited to `5_000_000` and tree C to `500_000_000` (`ant jar`; `~/s4-ss/logs/constants.txt`). Nothing built in the repository's `cassandra/cassandra-5.0.9/` (`git status` of it empty). | |
| Case-file commit / harness commit | case file untracked at `627b1ec` (sha256 `85fd6260…455c`, §1); harness uncommitted (md5s in `run1/harness.md5.final`) | |
| Storage for node data | `/dev/sda3`, ext3, 63 GB (about 51 GB free at the start); node data under `~/s4-ss/node-*` (removed afterwards); unit test data under tree A's `build/test/cassandra` | |
| Full logs (path, outside the repo) | `pc12:~/s4-ss/run1/{unit,cluster}/`; builds in `pc12:~/s4-ss/logs/` | |

**Environment deviations (none changes B1):** (1) the filed `/local/$USER/...` paths do not exist; trees and data are under `~/s4-ss/` on local disk. (2) The node runs on loopback `127.0.0.77` with JMX on `127.0.0.1:7277` and its own tree, data directory and log directory because `pc12` is shared; `nodetool` is called with `-h 127.0.0.1 -p 7277`. (3) The cluster loader is a Python driver script (4 workers, 128 in flight) instead of `cassandra-stress`; data is deterministic. (4) One table per arm on one node lifetime per jar replaces "reload the same data": the same seeded data, input bytes equal within 0.01% across arms. (5) `jstat` cannot attach to the Cassandra JVM (`MonitorException: not found`, shared perf data is disabled), so heap is sampled with `jcmd <pid> GC.heap_info`. (6) `MAX_HEAP_SIZE=2G HEAP_NEWSIZE=512M`, `compaction_throughput: 0MiB/s`, `concurrent_compactors: 1`, `auto_snapshot: false` are set in the environment and `cassandra.yaml.used`. (7) `ulimit -n` is raised to 100000 inside the drivers. (8) The cluster inputs are 24 Data.db files per 2 GB arm (size-triggered memtable flushes of 58 to 96 MiB, about three per 25,000-partition batch), not the 8 files of about 250 MB that B3c describes; the small arms have 8 files. Every 2 GB arm has the same shape, `T` is the sum of the input Data.db lengths either way, and the ratio count depends only on `T`. (9) Shakedowns (instrument checks, not readings) ran before run 1 at reduced scale (`STAGE4_PARTS=400` and `2000`; `STAGE4_PER_PHASE=2000`): their output (`pc12:~/s4-ss/shake*`) is not used.

**Instrument checks (before run 1, not readings).** Unit: the recording subclasses compile and run under `ant testsome`; at 2,000 partitions the analyzer's structural checks passed (line-84 rule on every call, `currentBytesToWrite == round(T * ratio)`, Data.db length equals the operand at the switch, ratio-count rule, the S = 0 piece-count model) and only the scale gates failed, as expected at that size; two analyzer defects were found and fixed (an empty-list `min`, and Python's banker's rounding against `Math.round`). Cluster: a node started from tree A on 127.0.0.77 / JMX 7277, plain / split / small / LCS arms completed at 160k rows, the DEBUG "Switching writer" line and the `checking if we can write Y bytes` line were found in `debug.log` and parsed, `jstat` was found unusable and replaced by `jcmd GC.heap_info`, and the node was stopped with no daemon left.

## 3. Runbook defects

| # | Run | Step | Problem | Fix | Decision (date) | Case-file commit with the fix |
|---|---|---|---|---|---|---|
| 1 | audit | B3c, B3f | 7 and 10 outputs for the 50e6 and 5e6 constants; the arithmetic gives 6 and 9. The small-data bullet contradicts itself. | B3i.1 and inline corrections | 2026-10-25, before the freeze | none (case file untracked) |
| 2 | audit | B3g | "Not enough space at half of D free" is not reachable: the task-level check asks for T first. | B3i.5 and inline replacement | 2026-10-25, before the freeze | none |
| 3 | audit | B3d | the DEBUG line is in `debug.log`, not `system.log` | B3i.4 | 2026-10-25, before the freeze | none |

(Run-time defects: see §4.)

## 4. Run 1

**Scope:** unit tier, 8 arms in one JVM (`smallestSSTable` = 0, 5e6, 50e6 (default), 10 x T, 50e6 on a compressed table, 50e6 on a 39.6 MB input, and `MaxSSTableSizeWriter` at 20e6 and 40e6 as the positive control); cluster tier, 10 arms in three node lifetimes (default-constant jar: plain, split, split again, split on a compressed table, small, LCS 100 MiB, LCS 50 MiB; 5e6 jar: split, small; 500e6 jar: split). **Command log:** `DEFAULT_SMALLEST_SSTABLE_BYTES-shouldSwitchWriterInCurrentLocation-getEstimatedOnDiskBytesWritten--autonomous/run1/unit/session.log`, `run1/cluster/{A,B,C}/session.log`; analyzer output `run1/analyze_unit.out`, `run1/analyze_cluster.out`; independent self-check `run1/selfcheck.out`. Tree A is the default constant (`A`), tree B the 5e6 jar (`B`), tree C the 500e6 jar (`C`).

### 4.1 Readings

**Unit tier** (`run1/analyze_unit.out`, `run1/unit/arms.txt`, `files-*.csv`, `switches-*.csv`). The JUnit run ended `BUILD SUCCESSFUL`, 8 tests (`run1/unit/ant-tail.log`). Input: 20,000 partitions x 10 rows x 1 KiB, one uncompressed sstable `T` of about 208.4 to 208.5 MB (gate `200e6 <= T < 400e6` holds); the largest partition is 10,428 B.

| Test or assertion | Result | Evidence (file) |
|---|---|---|
| `ratios.length` and outputs for `smallestSSTable` = 0 / 5e6 / 50e6 / 10 x T | 20 ratios and 12 outputs / 6 and 6 / 3 and 3 / 1 and 1; switches = outputs - 1 in every arm; rows preserved (200,000) | `arms.txt` |
| Sum of output Data.db across the four values | 208,531,939 / 208,520,005 / 208,452,678 / 208,444,224 B (spread 0.04%; each equals its input bytes exactly) | `analyze_unit.out` (cross) |
| Operand at every `true` return `> currentBytesToWrite` and every `false` `<=` (index < last) | holds on 19,999 calls in each arm | `analyze_unit.out` |
| `currentBytesToWrite` at every call = `round(T * ratio[idx])` | holds in every arm | `analyze_unit.out` |
| Every non-final output i in `(target_i, target_i + maxPartition]` | holds; largest excess over a target 10,386 B (S = 0), 10,388 (5e6), 10,198 (50e6); `maxPartition` = 10,428 B | `analyze_unit.out` |
| Uncompressed non-final Data.db length == operand at its switch | holds in every uncompressed arm | `analyze_unit.out` |
| (T, 50e6): outputs | 3: 104,226,588 / 52,123,368 / 52,102,722 B; last > its own target 26,056,585 and > the 50e6 constant | `files-d50.csv`, `analyze_unit.out` |
| (T, 0): last output | 31,274 B (3 partitions), above its own target T x 2^-20 = 199 B | `files-d0.csv` |
| (T, 10 x T): outputs | 1, 208,444,224 B, no switch | `files-dbig.csv` |
| (39.6 MB, 50e6): outputs | `ratios.length` 1, 1 output of 39,587,890 B, below the 50e6 constant | `files-small.csv` |
| Compressed (LZ4) (T, 50e6) | 3 outputs, same relation within `maxPartition + 2 chunks + 64 B` (largest excess 11,581 B) | `analyze_unit.out` |
| Positive control `MaxSSTableSizeWriter` | m = 20e6: 11 outputs; m = 40e6: 6; non-final outputs in `(m, m + 10,428]` (largest excess 1,595 B) | `analyze_unit.out` |
| MODEL (not a verdict row): S = 0 piece count | model 13, observed 12 | `analyze_unit.out` (MODEL FAIL; see §4.2 part 6) |

**Cluster tier** (`run1/analyze_cluster.out`, `run1/cluster/<tree>/<arm>/summary.json`). 200,000 partitions x 10 rows x 1 KiB (2,000,000 rows), `T` = 2,085,263,611 to 2,085,277,000 B across the 2 GB arms (gate holds for all three constants: `2.0e9 <= T < 2.56e9`); node on 127.0.0.77; DEBUG lines from `debug.log`.

| Capacity value (constant) | Run | Observable (B3d) | Reading | Evidence (file) |
|---|---|---|---|---|
| 50e6 (default, tree A) | plain `compact` (no `-s`) | outputs; bytes; peak table-dir bytes | 1; 2,086,357,597; 4,178,612,310 (2.000 x pre) | `A/plain/summary.json` |
| 50e6 | `compact -s` | outputs; switch lines; sizes; bytes; peak | 6; 5 (521,315,903 / 260,657,951 / 130,328,976 / 65,164,488 / 32,582,244, each = round(T x 2^-(i+2))); 1,042,634,753 / 521,316,836 / 260,658,564 / 130,334,898 / 65,167,111 / **66,241,780** (last above its own target 32,582,244 and above 50e6); 2,086,353,942; 4,178,525,042 | `A/split/summary.json`, `debug.log.segment` |
| 50e6 | `compact -s` again | outputs; bytes; peak | 6; 2,086,355,705; 4,178,497,686 | `A/split2/summary.json` |
| 50e6 | `compact -s`, compressed table | outputs; `T`; peak | 6; 2,092,576,130; 4,193,779,351 | `A/splitz/summary.json` |
| 5e6 (tree B) | `compact -s` | outputs; switch lines; last piece; bytes; peak | 9; 8 (521,317,648 ... 4,072,794); last **9,211,276** (above its own target 4,072,794 and above 5e6); 2,086,357,759; 4,161,082,950 (1.992 x pre) | `B/split/summary.json` |
| 500e6 (tree C) | `compact -s` | outputs; switch lines; last piece; bytes; peak | 3; 2 (521,316,057 / 260,658,028); 1,042,636,215 / 521,317,724 / **522,403,228** (above its own target 260,658,028 and above 500e6); 2,086,357,167; 4,178,570,808 | `C/split/summary.json` |
| 50e6 / 5e6 | small data (`T` = 91.7e6), `compact -s` | outputs | 1 output of 91,782,443 B (above the 50e6 constant) / 5 outputs (45.9e6 / 22.9e6 / 11.5e6 / 5.7e6 / 5.8e6) | `A/small`, `B/small` |
| every arm | task-level space check (`Directories` DEBUG) | bytes asked for | exactly `T` in every arm (one line each), never the half or a ratio share; no "Not enough space" or "insufficient space" line anywhere | `*/summary.json` `space_check_lines`, `debug.log.segment` |
| positive control: LCS `sstable_size_in_mb` = 100 / 50, `compact` | outputs; sizes | 20 / 40; non-final outputs 104,859,684 to 104,860,361 B (S = 104,857,600) / 52,429,672 to 52,430,292 (S = 52,428,800) | `A/lcs100`, `A/lcs50` |
| heap and memory (context) | heap used peak (`jcmd GC.heap_info`, about 1 s); RssAnon peak | split A / A repeat / B / C: 1,471,135 / 1,462,517 / 1,500,575 / 1,390,514 kB (max difference across constants 7.3%, repeat spread 0.6%); RssAnon peak 2.83 to 2.88 GB in every arm (2 GB heap pre-touched) | `analyze_cluster.out`, `*/heap.csv`, `*/rss.csv` |
| every arm | log, read-back | no ERROR; spot check of 40 partitions (10 rows, blobs equal to the seeded bytes) passed; one `Compacted` line per arm | `*/summary.json` |

### 4.2 Conclusion and logic

1. **Validity** — valid at both tiers. The limit was reached: the check returned `true` 2, 5, 11 times (unit: 50e6, 5e6, 0) and 5, 8, 2 times (cluster: 50e6, 5e6, 500e6), and the last piece ran past its own target in every split arm [observed: `analyze_unit.out`, `analyze_cluster.out`, `debug.log.segment`]. The gates hold: unit `T` 208.4 to 209.1 MB, cluster `T` = 2.0853e9 to 2.0926e9, small arms 39.6e6 and 91.7e6 [observed: `arms.txt`, `summary.json` `input_bytes`]. The constant in each tree is the intended one [observed: `cluster/{A,B,C}/session.log` `constant in this tree`]. Hold-fixed: same seeded data in every arm (input bytes equal within 0.01% across the three constants) [observed: `analyze_cluster.out` INFO]; auto-compaction disabled and one `Compacted` line per arm [observed: `summary.json` `compacted_lines`, `selfcheck.out`]; one data directory [observed: `cassandra.yaml.used`]; `nodetool compact -s` used the split writer [observed: the "Switching writer" lines exist only in the `-s` arms, with values `round(T x 2^-(i+2))`].
2. **Readings** — nothing contradicts another. The cluster output total is 1.09 MB (0.052%) above the input `T` in every arm including the unsplit one [observed: `summary.json` `bytes` against `input_bytes`], so each last piece is about 1.09 MB above `T x 2^-(len-1)` (for 5e6 that is 9.21 MB against 8.15 MB, 13% above the "about 8.1 MB" of B3i.1; the relation it was predicted for, above its own target and above the constant, holds). In the S = 0 unit arm the analyzer's piece-count model (uniform 10,428 B partitions) predicts 13 and the writer made 12; the model is not a verdict row, and the observed per-piece partition counts (10,000 / 5,001 / 2,501 / 1,250 / 626 / 313 / 157 / 79 / 40 / 20 / 10 / 3) follow the traced rule `round(T x 2^-(i+1))` exactly, so the model's uniform-size assumption (real partitions are 10,418 to 10,428 B) is what was off [observed: `files-d0.csv`, `switches-d0.csv`]. The 5e6 small arm's sampled peak is 1.5 x, not 2 x, because that compaction lasted 1.5 s and the 0.25 s sampler caught no sample at the end of it; the 4.3 s small arm with the default jar shows 2.000 x [observed: `B/small/du.csv`, `summary.json`]. The 2 GB inputs are 24 files (§2 deviation 8).
3. **Matched row** — unit B2g row 1: "sum(output) is the same (within 2%) for all `smallestSSTable` values while N and `ratios.length` change as predicted | Claim confirmed: the constant partitions the output and does not change the volume" [observed: 208.44 to 208.53 MB for N = 1 / 3 / 6 / 12; `ratios.length` 1 / 3 / 6 / 20 equal to the traced rule]. Also "Last piece size > totalSize x ratios[last] ..." [observed: 52,102,722 > 26,056,585 and > 50e6 for the default; 31,274 > 199 for S = 0] and "positive control moves with its own knob" [observed: `MaxSSTableSizeWriter` 11 then 6 outputs]. Cluster B3g row 1: "Final du and peak du equal across Runs A, B, C (within 2% / 5%), piece count changes with the constant, positive control moves with its knob | Claim confirmed" [observed: final output bytes 2,086,353,942 / 2,086,357,759 / 2,086,357,167 and unsplit 2,086,357,597, spread 0.0002%; peak table-dir bytes 4,178,525,042 / 4,161,082,950 / 4,178,570,808 and unsplit 4,178,612,310, spread 0.42%; pieces 6 / 9 / 3 against the predicted 6 / 9 / 3; LCS 20 then 40 files]. Also "Peak du does not exceed B0 + D" [observed: 2.000 x the pre-compaction directory, 1.992 x for 5e6], "Last piece larger than the 50 MB constant" [observed: 66.2 MB], and the replaced row on the task-level request [observed: exactly `T` in all arms].
4. **Excluded rows** — "sum(output) shrinks or grows with the constant by more than 2%": no, spread 0.04% (unit) and 0.0002% (cluster) [observed]. "A non-final piece larger than target + one partition": none, largest excess 10,386 B against 10,428 B (unit) and 6,575 B against a 10,635 B bound (cluster, uncompressed arms) [observed]. "`ratios.length` differs from the arithmetic": none, all equal [observed]. "N == 1 for (200 MB, 50e6)": N = 3 [observed]. "Positive control does not move": it moves (11 to 6; 20 to 40) [observed]. Cluster: "final or peak du differs between B and C by more than 5%": 0.4% at most; "piece count equal for both jars": 6 / 9 / 3; "LCS count does not change": it doubles; "heap peak differs by more than 10%": 7.3% across constants and a repeat spread of 0.6%, below the rule of B3i.6 [observed]. Not run: "Not enough space at half of D free" (replaced, B3i.5). No Refuted row applies.
5. **Observed vs. inferred** — inferred: that the heap numbers reflect live use (they are `jcmd GC.heap_info` "used", which includes garbage; they are context only and no row depends on them); that the work was done by the split writer at the cluster tier (rests on the "Switching writer" lines, which only that class logs, and on 6 / 9 / 3 outputs matching the ratio rule). Observed: everything else. The "does not cap" reading is observed as byte equality, not inferred.
6. **Deviations and gaps** — listed in §2 (24 input files; loopback address; Python loader; `jcmd` for heap; `debug.log` for the DEBUG lines) and part 2 above. The 5e6 small arm's peak is under-sampled; the S = 0 piece-count model is off by one (non-verdict). One run of each tier and arm (the repeat `split2` agrees with `split`); no run 2; no check at constrained free space (the "Not enough space" path is not exercised); the `CompactionTask` check is shown by the bytes it asks for, not by driving it to fail.
7. **Core question** — usage does not follow the constant. Across constants 0 / 5e6 / 50e6 / 10 x T (unit) and 5e6 / 50e6 / 500e6 (cluster) the piece count moved 12 / 6 / 3 / 1 and 9 / 6 / 3 while the bytes written (0.04% and 0.0002% apart) and the peak table-directory bytes (0.42% apart, always 2 x the input: input kept until commit) did not, and the last piece always exceeded both the constant and its own target. The same workload and instruments registered the binding caps (`MaxSSTableSizeWriter` 11 then 6 outputs; LCS `sstable_size_in_mb` 20 then 40 files), so the null result is not a blind instrument. The disk-space check that does exist on this path (`CompactionTask`) asks for the whole input `T` in every arm and never depends on the constant, so it is a different constraint.

**Conclusion (one line):** unit B2g row 1 and cluster B3g row 1 (the constant partitions the output and does not change the volume) — confirmed; the constant does not cap disk or memory use.

## 5. Self-check of run 1 — AI

### 5.1 Check of run 1's conclusion

`run1/selfcheck.out` re-derives the numbers by a route independent of `analyze_*.py` (unit: ant.log echo against `arms.txt`, line 84 replayed on the logged operands with its own index and target tracking; cluster: `debug.log.segment` switch lines and the task-level request, `tablestats.after` SSTable count, the `Compacted` line's output bytes, peaks recomputed from `du.csv`). **67 of 68 claims hold.** The one that does not is an auxiliary assertion I added that the peak table-dir bytes of every cluster arm lie between 1.8 and 2.1 times the directory before compaction: `B/small` gives 1.499 because the 1.5 s compaction was sampled every 0.25 s and the end of the compaction fell between samples (`B/small/du.csv`: samples 91.9e6, 137.8e6, then 91.98e6 after commit); it is not a prediction of the case and no row depends on it. All 2 GB arms and the 4.3 s small arm give 1.99 to 2.00.

Two analyzer defects were found when the cluster output first ran (`run1/analyze_cluster.first.out`, 9 FAIL of 78) and fixed in the analyzer only, with no change to the case file or its tables: (a) a validity condition of mine that the input must be exactly 8 files (the 24-file input is §2 deviation 8, same in every 2 GB arm); (b) a check I wrote that the single output of the small default-constant arm must be below the 50e6 constant, which misread the case ("below the 100 MB threshold", that is `T < 2 x constant`): the output is 91.78 MB, above the constant, which is itself an instance of the claim. After the fix all 78 analyzer checks pass.

| Part | Holds? (yes / no) | Note (file re-read) |
|---|---|---|
| 1. Validity | yes | `selfcheck.out`: unit echo equals `arms.txt`, 8 tests run; cluster `T` in `debug.log.segment` equals `input_bytes` in every arm; tablestats SSTable count equals outputs; the gates hold |
| 2. Readings | yes | `selfcheck.out`: `Compacted` line bytes within 0.2% of the sum of output sizes; the unit line-84 replay reproduces every return; the one non-holding auxiliary claim is the under-sampled `B/small` peak (explained above) |
| 3. Matched row | yes | `analyze_unit.out` 72 checks and `analyze_cluster.out` 78 checks all PASS; `selfcheck.out` repeats ratio count, switch values `round(T x 2^-(i+2))` and the "each non-final piece above its target" relation for every split arm |
| 4. Excluded rows | yes | maximum excess 10,386 B (unit) and 6,575 B (cluster) against one partition; byte spread 0.04% and 0.0002%; controls move |
| 5. Observed vs. inferred | yes | the inferred items are context only (heap) or backed by the `Switching writer` lines |
| 6. Deviations and gaps | yes | §2 and §4.2 part 6 list them; none changes a count or a byte sum |
| 7. Core question — the steps from reading to answer follow the audited logic | yes | knob varied (4 unit values, 3 jars), usage measured as file bytes and directory bytes, the disallow branch recorded per call and by DEBUG line, positive controls moved, the caveat (task-level check) read and measured |

### 5.2 Run 2?

**No** (2026-10-25). The result is the expected one for a negative estimate, every count matched the traced rule exactly in 18 arms (including exact switch values at both tiers), the byte equality is to 0.04% and finer, the independent self-check holds apart from the one auxiliary under-sampled peak, and nothing in the conclusion rests on an inferred statement.

## 6. Run 2 — fresh AI session (optional)

Not done.

## 8. Verdict — AI

Jingsong may overrule any verdict at any time; record an override here with its date and reason.

**Stage-3 estimate:** negative. **Outcome class:** **true negative** (negative, does not cap).

**Claim tested:** B1: changing the "smallest sstable" threshold changes only the number and sizes of the output pieces of a split STCS major compaction and not the total bytes written to disk (about the input size); it does not stop a piece from exceeding the threshold (the last piece exceeds it by design, the others exceed their targets by up to one partition). Equivalently, the 50 MB constant is not a cap on disk use. "Confirmed" below means this claim held.

| Tier | Verdict (B2g / B3g row) | Effect on the constant's constraint | Basis | Date |
|---|---|---|---|---|
| Unit | **Confirmed** — B2g row 1 (sum(output) the same within 2% while N and `ratios.length` change as predicted; last piece above its own target; positive control moves) | does not cap | run 1 + self-check | 2026-10-25 |
| Cluster | **Confirmed** — B3g row 1 (final and peak du equal across 5e6 / 50e6 / 500e6 and the unsplit run; piece count 9 / 6 / 3; LCS control moves 20 to 40) | does not cap | run 1 + self-check | 2026-10-25 |

**Positive control:** `MaxSSTableSizeWriter` (a per-piece size limit that binds) gave 11 outputs at m = 20e6 and 6 at m = 40e6, each non-final output within one partition above m, with the same instruments and input (unit); LCS `sstable_size_in_mb` = 100 and 50 gave 20 and 40 files of 104.86 MB and 52.43 MB on the same 2 GB load, node and samplers (cluster). So the harness sees a binding size limit when there is one.

**Open caveat resolved:** the write-up agent had not read `CompactionTask`'s own disk-space check. It is read (`CompactionTask.java:147-153, 384-452`; `Directories.java:524-569`): before the writer exists it asks whether `T` (all input bytes, not `totalSize x ratios[0]`) fits within 0.95 of the usable space less 50 MiB, and for `nodetool compact` (not user-defined) it drops the largest input until it fits, else throws. It does not read the 50 MB constant, so it does not change the claim; measured: it asked for exactly `T` in all 10 cluster arms (`checking if we can write <T> bytes`), with 45.6 to 48.5 GB available for compactions (the check's own figure). It does make the stage-3 sentence "the split compaction reserves only half" true for the writer's own check only, and makes the "Not enough space at half of D free" row unreachable (replaced in B3g).

**What stays on `pc12`:** `~/s4-ss/` (about 1.4 GB: `treeA`, `treeB` (constant 5e6, built), `treeC` (constant 500e6, built), `driver/`, `harness/`, `logs/`, `run1/` full logs and CSVs, `shake-unit`, `shake-unit2`, `shake-cl`, `/tmp/ss-*.sh`). The node data directories (`node-A`, `node-B`, `node-C`, shakedown nodes) were removed. No `CassandraDaemon`, `ant`, `jcmd` or loader process of this run is left (`ps` checked 2026-10-24 23:20 MDT; the other processes on `pc12` belong to the `cdc` run); ports on 127.0.0.77 and JMX 7277 are free. The copies in the repository of the harness and `run1/` excerpts are in this repository on `node0`.

**Feedback filed:** the case file's section D is filled (case file untracked, so no commit), together with the dated audit amendments (A3 step 8, C, B2i, B3i and inline corrections; sha256 of the file with section D filled: `e07388dfe1a31581b3f6de02cfd475254b79b9ddd4cb129b638012ab583650f5`). `_INDEX.md`, the CSV and `predicted-negative.md` are left to the human.
