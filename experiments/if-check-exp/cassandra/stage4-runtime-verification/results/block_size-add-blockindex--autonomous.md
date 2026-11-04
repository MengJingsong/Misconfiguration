# block_size-add-blockindex--autonomous — stage-4 results  <!-- file: results/block_size-add-blockindex--autonomous.md; the stem ends in --guided or --autonomous -->

> **Case:** [`block_size-add-blockindex--autonomous`](../../stage3-ai-deep-read/cases/block_size-add-blockindex--autonomous.md)
>
> **Status:** verdict filed 2026-10-28 — unit Confirmed (does not cap); cluster Refuted as frozen on disk (does not cap); no run 2
>
> **Outcome class:** true negative (stage-3 estimate `negative`, stage-4 effect `does not cap`; the cluster row is Refuted as frozen: see section 8) **Index entry (orchestrator, 2026-10-28): undetermined** — README rule: a Not confirmed or Refuted-as-frozen tier makes the class undetermined; the agent filed true negative.
>
> **Agent:** autonomous. For an autonomous
> file, "§9a" below means each tier's predictions and conclusions table: B2f and B2g
> (unit), B3f and B3g (cluster); "§9b–§9e" means B2a–B2e or B3a–B3e; and the case
> file's feedback section is its section D, not §10. One results file per case file.

**Relative links in this template** are written for where a *copy* of it lives
— inside `results/` — not for the template's own location one level up.

**Fill the sections in order.** The audit (§1), run 1 (§4) and the self-check
(§5) are required; run 2 (§6) and the comparison (§7) are filled only if §5.2
chooses run 2. No step waits for a human.
The protocol behind each section is in
[`../README.md`](../README.md#the-run-protocol).

## 1. Before run 1 — design audit and freeze

| Field | Content |
|---|---|
| **Case-file version** | sha256 before the audit: `1c81cc0d72bac411522323f2afb9198a1c1a7f60c2d6638918b1de8459451814`. **Frozen version (after the audit's amendments B5.1-B5.7 of 2026-10-28, taken before any reading): `2e4ad670a96ea6f39f3c8eb6109f8393233b2045a93bac2e9cc0305a6f6d1023`.** After the post-freeze correction B5.8 (control condition (iii), made after the first cluster arm; no change to claim, predictions or rows): `ee4dbe6ba03b647bd2c42d58cdfae1f9dd446df02d9a2303ca67a898a96bb42c`. **Final, after section D (stage-4 feedback): `a285bff612bc54d81c1995189344c631997e3fa91e9c9d57881bcb9d397a45cd`.** File committed at `b68711e5` (HEAD); the amendments and feedback are uncommitted. |
| **Harness** | `harness/block_size-add-blockindex--autonomous/` (uncommitted; README there) |
| **Tiers and values** | Unit: BlockPackedWriter and MonotonicBlockPackedWriter at blockSize 32, 64, 100, 128, 16384, 2^20, 2^24 (N = 10 x 2^24) plus an ArrayList control. Cluster: builds stock (128/16384), num64 (64/64), num1m (2^20/2^20) at 3M rows; stock at 750k rows; segment_write_buffer_size 16MiB control. |
| **Audit bottom line** | **Ready after amendments** — 2026-10-28 |

### 1.1 Design audit

The requirements are in the README, "Step 0 — the design audit". One row per
line of each group; cite the case-file section checked.

| Group | Check | Rating (Met / Partly / Not met) | Note (section checked) |
|---|---|---|---|
| A. Core question | constrained quantity is memory or disk bytes | Met | A2: heap bytes of the fixed scratch array(s) (a count of longs with a derivable byte size) and the on-disk component bytes. |
| A. Core question | knob varied, >= 3 values incl. default — or another approach, with the reason | Partly -> Met | B1/B3b: hard-coded (A1); the constructor argument is varied in the unit tier (7 values incl. both production sizes) and three rebuilt constants in the cluster tier; B3b names rows as a data-volume variable only through B5.4. The constant is hard-coded (A1), so rebuilds are the only way to vary it (stated). |
| A. Core question | real resource measured, not only the counter (gap named) | Partly -> Met | Unit: thread-allocated bytes and heap histograms; cluster: a Byteman ledger of the exact array lengths, JMX heap/RSS samples (noisy, named as such) and component file bytes (B5). |
| A. Core question | usage driven to the limit and past it | Met | The check fires many times per run (arithmetic in B2c/B3c and B5); a hard-coded constant has no limit to exceed beyond that. |
| A. Core question | positive control (negative estimate) | Partly -> Met | Unit: `ArrayList<Long>` accumulating the same N shows the histogram sees growth (B2h). Cluster: segment_write_buffer_size 16MiB vs 1024MiB (amended definition) plus stock at 750k vs 3M rows. |
| B. Logic | each step says what it establishes | Met | B1, B2e, B3e. |
| B. Logic | prediction stated in numbers or a clear relation | Partly -> Met | Tolerances added in B5 where the case said "slightly" or "a few percent". |
| B. Logic | every plausible outcome has a conclusions row with its evidence | Met (rows added) | B2g/B3g plus the added rows in B5 (queries fail, workload not driven). |
| B. Logic | confirmation needs ceiling-follows-knob and direct disallow evidence | Met | The claim is negative: the confirmation needs usage flat while the control moves; the direct evidence is the ledger and the readings of the traced check. |
| B. Logic | alternative explanations and their controls | Met | B2h/B3h, B5. |
| C. Specific | a human can follow it from the intro and §9a alone | Met | |
| C. Specific | an AI can run §9b–§9e without re-deriving the code path | Partly -> Met | B5 fixes the run form, load path and sizes. |
| C. Specific | knob, values, workload, commands, observables, sampling, stop conditions exact | Partly -> Met | B5 fixes the row counts, sampling (500 ms JMX, 1 s RSS) and tolerances. |
| D. Runnable | harness and environment prerequisites exist or are listed | Met (with harness) | Written for this run; the eight variant builds exist (`javap -constants`). |
| D. Runnable | workload arithmetic reaches the limit (data, time, disk, memory) | Met (amended) | node pc39: 251 GiB RAM, 40 cores, 48 GB free local disk; 3M rows is a few GB; B5 states it. |
| D. Runnable | load-bearing citations spot-checked against the pinned source | Met after corrections | `AbstractBlockPackedWriter.java:34-35, 49, 51-52, 62, 111-115`, `NumericValuesWriter.java:34-35, 49, 52-62`, `SSTableComponentsWriter.java:58-62, 72`, `SAICodecUtils.java:127-144`, `ResettableByteBuffersIndexOutput.java:45-49` match the pinned source. Slip: invalid-size messages are at `SAICodecUtils.java:133` and `:142`, not `:132`/`:140` (amended). |

| # | Recommendation | Applied? (amendment date and commit, or "left for stage 3") | Why |
|---|---|---|---|
| 1 | B2a/B2d: run form (`java -cp`), `-Xmx1g`, thread-allocation instrument, flush counter | Applied (B5.1) | run form and the unverified metadata-buffer allocation |
| 2 | B2c: counting sink instead of ByteBuffersIndexOutput | Applied (B5.2) | 167M values would not fit the 1 GiB heap if retained |
| 3 | B2f: message line numbers | Applied (B5.3) | citation slip |
| 4 | B3: 3M rows, seed + CREATE INDEX load path, one 750k arm | Applied (B5.4) | 20M rows is not proportionate; the flush path is replaced by the same writers via the index build |
| 5 | B3: control defined (segment buffer gauge), ledger instrument, 40 MiB figure for variant C | Applied (B5.5, B5.6) | the case control "segment_write_buffer_size" had no stated reading; C is 1.0 % of heap, not "well under 1 %" |
| 6 | Disk "changes only slightly" tolerance | Applied (B5.6) | unquantified |

Run 2 is not planned, so the agreement criteria are not filled.

## 2. Environment

| Field | Run 1 |
|---|---|
| Date | 2026-10-28 (unit 17:47 MDT; cluster chain 18:08 to 18:24 MDT) |
| Node | `pc39` (`node1.jason92-321705.misconfiguration-pg0.cloudlab.umass.edu`), 40 cores, 251 GiB |
| OS / kernel | Ubuntu 22.04.2 LTS, `5.15.0-198-generic` |
| JDK / Ant | OpenJDK 11.0.32.1 / Apache Ant 1.10.12 |
| Local source | `~/s4-b34/base` (`copy-source.sh` copy of `cassandra/cassandra-5.0.9/` at repository commit `b68711e5`, `git describe` = `cassandra-5.0.9`, `ant build-test` 1 min 11 s, `ant jar`); variants `~/s4-b34/v-num64` and `v-num1m` (`NumericValuesWriter.java:34-35` edited by `sed`, patches in `run1/build-patches/`, `ant jar`, `javap -constants` confirmed 64 / 64 and, for v-num1m, `1 << 20`) |
| Case-file / harness commit | `b68711e5` with uncommitted amendments (sha256 in section 1) / uncommitted |
| Storage for node data | local disk `~/s4-b34/cl/blockindex/node` (the node's `/` had about 48 GB free); seeds in `~/s4-b34/seeds` |
| Full logs | `pc39:~/s4-b34/logs/blockindex/` (`unit/run1/`, `cluster/<arm>/`, `cluster/summary.txt`); other agents' nodes (`pc32`, `pc29`, `pc41`) were not touched |

**Instrument checks before run 1** (recorded because they produced readings; none was used to tune a prediction): (1) the unit probe was run once for one cell (`mono 128 100000`) and showed class-loading allocation in the first constructor (634,976 B), which led to the warm-up writer now in the probe; (2) the cluster engine was run on a 20,000-row seed with the `v-num64` build (logs `~/s4-b34/logs/shakedown/blockindex-cluster`), which showed that a node started with `-f` has no pidfile until late (the engine now records the child pid), found an orphan node left by the first failed start (stopped; none left) and was repeated; the seed loader was then made multi-process. The harness file `cluster-run.py` was edited after this case's cluster run (cluster name constant `stage4-blockindex` for all SAI cases, which is the name this run already used; seed loading is unchanged), so the md5 in `cluster/summary.txt` (`2dbbd62582b9`) is of the version that ran; behaviour for this case is the same.

## 3. Runbook defects

| # | Run | Step | Problem | Fix | Decision | Case-file commit |
|---|---|---|---|---|---|---|
| 1 | cluster, after arm A-3M | B3h / B5.5 control (iii) | B5.5 assumed the default 1024 MiB arm never reaches its segment-buffer limit. At 3,000,000 rows it does (gauge peak 1,073,743,912 B, 8 `Global limit` flush lines, "Current builder usage is 1.000GiB for 604508 cells"). Condition (iii) "flush lines only in the 16 MiB arm" cannot hold. | B5.8 (dated 2026-10-28, case file): (iii) is "more flush lines in the 16 MiB arm than in the default arm"; (i), (ii) unchanged. Made after seeing arm A-3M's control-related gauge only, before the B / C arms had finished; the claim, the predictions and the build comparison are untouched. Run 1 was **not restarted**: the procedure and raw data are identical, only an evaluation criterion changed. | AI, 2026-10-28 | none (uncommitted) |
| 2 | unit analysis | `analyze_unit.py` | none (first parse passed 185 of 185 checks) | | | |

## 4. Run 1

**Scope:** unit tier: 43 JVMs (2 repetitions of plain / mono x sizes 32 and 100 (invalid), 64, 128, 16384, 2^20, 2^24 with N = 167,772,160 and N = bs - 1 for 128, 16384, 2^20; 3 control sizes); cluster tier: six node starts (A-3M, B-num64, C-num1m, A-750k, A2-3M, ctl-seg16). **Command log:** `block_size-add-blockindex--autonomous/run1/unit/summary.txt`, `run1/cluster/summary.txt`; checkers `harness/.../analyze_unit.py`, `analyze_cluster.py` (outputs `run1/analyze-unit.txt`, `run1/analyze-cluster.txt`) and the independent `selfcheck.py` (`run1/selfcheck.out`).

### 4.1 Readings

**Unit tier** (`run1/unit/<kind>-<bs>-<full|short|invalid>-r<rep>.out`; the two repetitions are identical in every counted figure; `Jdelta` is the growth of `[J` in the class histogram with the writer alive after the adds, `meta` the block-metadata bytes after `finish()`):

| Kind, blockSize | N | Constructor alloc (B) | `blockValues.length` | Max `blockIndex` | Flushes (expected) | `Jdelta` (B) | `meta` (B) |
|---|---|---|---|---|---|---|---|
| plain 128 | 167,772,160 | 1,400 | 128 | 128 | 1,310,720 (1,310,720) | 1,096 | 10,115,968 |
| plain 128 | 127 | 1,400 | 128 | 127 | 1 (1) | 1,096 | 4 |
| mono 16384 | 167,772,160 | 131,448 | 16,384 | 16,384 | 10,240 (10,240) | 131,144 | 99,645 |
| mono 16384 | 16,383 | 131,448 | 16,384 | 16,383 | 1 (1) | 131,144 | 6 |
| plain 2^20 | 167,772,160 | 8,388,984 | 1,048,576 | 1,048,576 | 160 (160) | 8,388,680 | 917 |
| mono 2^24 | 167,772,160 | 134,218,104 | 16,777,216 | 16,777,216 | 10 (10) | 134,217,800 | 131 |
| plain 64 / mono 64 | 167,772,160 | 888 | 64 | 64 | 2,621,440 (2,621,440) | 584 | 20,878,977 / 25,509,843 |
| 100 (both kinds) | 1,000 | 8,992 | - | - | `IllegalArgumentException("blockSize must be a power of two, got 100")` | - | - |
| 32 (both kinds) | 1,000 | 474,112 (exception message formatting; no `long[]`) | - | - | `IllegalArgumentException("blockSize must be >= 64 and <= 134217728, got 32")` | - | - |
| control: growing `long[]` | 1,048,576 / 4,194,304 / 16,777,216 | - | - | - | - | 8,388,656 / 33,554,480 / 134,217,776 (= 8 N + 48) | - |

The same figures for the other sizes are in `run1/analyze-unit.txt` (203 lines, 0 mismatches).

**Cluster tier** (`run1/cluster/<arm>/`; table: after the initial `CREATE INDEX` build; the `nodetool rebuild_index` repeat gave byte-identical files in every arm; `ledger` = `BPW` lines, 3 sets of 5 writers per arm; `numeric` = the five `RowToToken`, `RowToPartition`, `PartitionToSize`, `PartitionKeyBlockOffsets`, `ClusteringKeyBlockOffsets` files; heap = the largest of 150 JMX samples at 500 ms):

| Arm (build, rows, seg buffer) | Ledger `blockValues.length` (per set) | Scratch `long[]` per set | Total SAI bytes | numeric bytes | all other SAI bytes | Heap peak (MiB) | Seg-buffer gauge peak | `Global limit` flush lines | count queries |
|---|---|---|---|---|---|---|---|---|---|
| A-3M (stock, 3M, 1024 MiB) | 128 x2, 16384 x3 | 395,264 | 49,133,244 | 20,839,566 | 28,293,678 | 4,045 | 1,073,743,912 | 8 | 3,000,000 / 30,000 x3 OK |
| A2-3M (stock, repeat) | same | 395,264 | 49,133,244 | 20,839,566 | 28,293,678 | 3,752 | 1,073,743,912 | 8 | OK |
| B-num64 (64 / 64) | 64 x5 | 2,560 | 41,542,421 | 13,248,743 | 28,293,678 | 3,902 | 1,073,743,912 | 8 | OK |
| C-num1m (2^20 / 2^20) | 1,048,576 x5 | 41,943,040 | 52,670,752 | 24,377,074 | 28,293,678 | 3,779 | 1,073,743,912 | 8 | OK |
| A-750k (stock, 750k) | 128 x2, 16384 x3 | 395,264 | 12,310,642 | 5,363,713 | 6,946,929 | 3,300 | 1,073,743,944 | 2 | 750,000 / 7,500 x3 OK |
| ctl-seg16 (stock, 3M, 16 MiB) | same as A | 395,264 | 47,832,094 | 20,839,566 | 26,992,528 | 2,511 | 16,779,844 | 848 | OK |

Per component (bytes), A / B / C: `RowToToken` 20,459,819 / 12,550,591 / 24,000,062; `RowToPartition` 376,987 / 669,434 / 375,052; `PartitionToSize` 728 / 1,430 / 26; `PartitionKeyBlockOffsets` 1,905 / 1,215 / 1,905; `ClusteringKeyBlockOffsets` 127 / 26,073 / 29; every other file (`ClusteringKeyBlocks` 9,750,025, `PartitionKeyBlocks` 125,905, `v_idx` and `txt_idx` files, 28,293,678 bytes in all) is byte-identical in A, A2, B and C. Ratios A-3M / A-750k: total 3.99, numeric 3.89.

### 4.2 Conclusion and logic

1. **Validity.** The constants really changed: the Byteman ledger shows `blockValues` of length 128 (x2) and 16,384 (x3) in A, A2, A-750k and ctl-seg16, 64 (x5) in B and 1,048,576 (x5) in C, in whole sets of five writers [observed: `run1/cluster/<arm>/ledger.txt`, `run1/analyze-cluster.txt`], and the three jars have different md5 [observed: `run1/cluster/<arm>/jar.txt`]. The check at `AbstractBlockPackedWriter.java:62` fired many times in every unit run (flush counts equal ceil(N / bs) down to 10 flushes for bs = 2^24 and 2,621,440 for bs = 64) [observed: `run1/unit`]. The segment-buffer limit was reached in the default arm (gauge 1,073,743,912 B, 8 `Global limit` flush lines at 1.000 GiB; the 750k arm too: 2 lines) [observed: `A-3M/flush-lines.txt`, `summary.txt`]. All six arms built and answered the count queries (3,000,000 and 30,000 for three terms) and had no `ERROR` line [observed: `cluster/summary.txt`, `errors.txt`].
2. **Readings.** (a) Peak heap is not an instrument that separates the arms: two identical stock arms differ by 293 MiB (4,045 and 3,752 MiB), more than B (-143) or C (-266 MiB) differ from A; C holds 40 MiB more scratch than A yet shows a lower peak [observed]. The frozen allowance (ledger difference + 2 % of 4 GiB = 82 and 122 MiB) was smaller than that noise; the B3f heap comparison therefore cannot be met or contradicted by the peak [inferred: from the A vs A2 pair]. (b) The disk figures are exact and repeatable (A = A2, build = rebuild). (b2) `analyze_cluster.py` reports 3 MISMATCH lines against the frozen criteria: total bytes within 10 % (spread 26.8 %), and the two heap allowances for B and C (-142.7 and -266.1 MiB against 82.3 and 121.5 MiB); the other 36 EXPECTED lines are OK. (c) The unit `Jdelta` for the rejected size 32 includes 474 KB of exception-message formatting (first use of that message path), no `long[]`.
3. **Matched row.**
   Unit B2g row 1, "`long[]` size = 8 x blockSize, flat in N; flush count = N / blockSize": `blockValues.length` = bs and `Jdelta` = 8 bs + 16 (+56 of other objects) for every size, identical at N = bs - 1 and N = 167,772,160, flushes = ceil(N / bs) [observed: `run1/unit`]; and rows 3 and 4 ("scales only as 8 x blockSize"; "positive control moves while writer heap is flat vs N"): the control `long[]` follows N (33,554,480 B at 4,194,304 values) while the writer's does not [observed: `ctl-*.out`]. Metadata bytes grow as blocks get smaller (10.1 MB at 128, 69 KB at 16384, 917 B at 2^20 for the plain writer): data-driven accumulation not bounded by blockSize [observed].
   Cluster B3g: **row 1 does not hold** and **row 2 does, for disk**. Row 1 ("peak heap and disk nearly identical across A/B/C; control moves") fails on disk: the total SAI bytes of A / B / C are 49.13 / 41.54 / 52.67 MB (spread 26.8 %, against the frozen 10 %), all of it in the five numeric-values files (B: RowToToken -7.9 MB, C: +3.5 MB; the other 28.3 MB are byte-identical) [observed: `analyze-cluster.txt`]. Row 2 ("peak heap/disk differs between A/B/C by far more than the scratch arrays predict; claim refuted") holds for B: -7.6 MB of disk against a scratch difference of -0.39 MB (20 times), whereas C's +3.5 MB is below its +40 MiB scratch difference; the frozen B3f/B5.6 wording ("claim wrong if disk tracks the variant by more than the scratch arrays predict"; "a difference not explained by blocks x metadata bytes refutes") is therefore met by B [observed numbers; the reading of the row is mine]. The direction is the opposite of "more, smaller blocks = more metadata": smaller blocks make the file smaller, because each block's bit width follows the range of its own values (the tokens are sorted within a partition, so a block of 64 rows spans a smaller range than a block of 2^20) [inferred: from `RowToToken` being the file that moves, from `BlockPackedWriter.java:46-76` computing bits per block, and from the unit output sizes: plain 64 -> 445.6 MB, 128 -> 432.2 MB, 2^24 -> 419.4 MB for the same 167,772,160 values].
4. **Excluded rows.** Unit "writer-held heap grows with N beyond metadata": `Jdelta` is the same for N = 127 and 167,772,160 [observed]. Unit "N never exceeds blockSize / control did not move": N is 160 to 2.6 million blocks and the control moved [observed]. Cluster "control did not move or limit never reached": the control moved (16.0 MiB gauge peak against 1,024 MiB; 848 against 8 limit-flush lines; heap peak 2,511 against 4,045 MiB) and the default arm reached its limit [observed]. Cluster "disk grows only with rows": not the only driver, see 3 [observed]. A heap difference between builds is not claimed in either direction (2a).
5. **Observed vs. inferred.** Inferred: (i) that the heap peak cannot resolve the arms (from one identical pair); (ii) the packing explanation of the disk difference; (iii) that the build and flush paths use the same writers (the ledger shows the writers ran in this path; the flush path itself was not run). The verdict does not depend on (ii) or (iii): it depends on the observed byte counts.
6. **Deviations and gaps.** The flush-and-compact load of B3c was replaced by seed + `CREATE INDEX` + `rebuild_index` and 20M rows by 3M (B5.4); peak heap is a 500 ms sample of the used heap, which includes garbage; one run per arm (plus one repeat of the stock arm); the unit `Jdelta` baseline includes a few hundred bytes of other objects; I did not measure native/direct memory beyond RSS (RSS peak 5.1 to 5.2 GiB in every arm, dominated by the 4 GiB heap); the 40 MiB of scratch in C is real but is hidden by the heap-peak noise. The frozen 10 % bound and the 82 MiB heap allowance were my own quantification of the case's "slightly" at the audit, before any reading.
7. **Core question.** Usage did not follow the constraint as a cap: the array is `blockSize` longs for ever (unit), it is flushed and reused 1.3 million times, and nothing in the data volume, the heap or the disk is bounded by the constant (SAI bytes grew 3.99 x for 4 x the rows in the stock build; the largest effect of changing the constant by a factor of 16,384 was a 27 % change in five numeric-values files through bit packing, while the other 28.3 MB did not change by a byte and the real cap, the segment buffer, bound the build memory (16.0 MiB gauge vs 1,024 MiB)). The constant does change how well five on-disk files are packed, which the frozen "changes only slightly" and "10 %" bounds did not allow for.

**Conclusion (one line):** unit B2g row 1 (with rows 3 and 4) - Confirmed; cluster B3g row 2 (disk of the five numeric-values files follows the constant by more than the scratch arrays predict) - Refuted as frozen, Effect `does not cap` (no bound at any constant; usage scales with rows).

## 5. Self-check of run 1 — AI

### 5.1 Check of run 1's conclusion

`harness/.../selfcheck.py` re-parses the raw `.out`, `ledger.txt`, `files-*.txt`, `gauges-*.csv` and `summary.txt` with its own regexes (it does not import the analysis script): 25 PASS, 0 FAIL (`run1/selfcheck.out`). It also re-derives, independently, the three facts that carry the cluster verdict: the 26.8 % spread, that only the five numeric-values components differ, and that the heap-peak differences lie inside the A vs A2 noise.

| Part | Holds? | Note |
|---|---|---|
| 1. Validity | yes | Ledger lengths, jar md5, count queries, daemon stopped after every arm re-read from the raw files. |
| 2. Readings | yes | A vs A2 heap spread (293 MiB) re-computed from `gauges-*.csv`. |
| 3. Matched row | yes | Unit: array length, flushes, histogram delta. Cluster: the byte counts per component re-parsed; the choice of row 2 for B is my reading of the frozen wording, stated. |
| 4. Excluded rows | yes | Control figures re-read from `gauges-ctl-seg16.csv` and `flush-lines.txt`. |
| 5. Observed vs. inferred | yes | The packing explanation is inferred and is not needed for the verdict. |
| 6. Deviations and gaps | yes | As listed. |
| 7. Core question | yes | Follows B1: (a) fixed array and flush (unit), (b) heap and disk against the constant and against a known cap (cluster). |

### 5.2 Run 2?

No — 2026-10-28. The unit tier is exact in two repetitions, the cluster byte counts are exact (A = A2, build = rebuild), and the only inferred statement that matters (the heap peak cannot resolve the arms) is a statement about an instrument, not about the claim. A second run would not change the matched rows.

## 6. Run 2 — optional

Not done.

## 7. Comparison

Not done.

## 8. Verdict — AI

**Stage-3 estimate:** negative. **Outcome class:** true negative (estimate `negative`, effect `does not cap`).

**Claim tested:** usage does not follow this constraint: (a) the writer's heap buffer is exactly `blockSize` longs regardless of how many values are added, and the check at `:62` flushes rather than limiting; (b) on a real node, heap and disk used by SAI writing do not track `BLOCK_SIZE` / `MONOTONIC_BLOCK_SIZE`, while they do track a known cap (`segment_write_buffer_size`) and the data volume.

| Tier | Verdict (B2g / B3g row) | Effect on the constraint | Basis | Date |
|---|---|---|---|---|
| Unit | Confirmed (B2g row 1, with 3 and 4: array = 8 bs + 16, flat in N; flushes = ceil(N / bs); control moved) | does not cap | run 1 + self-check | 2026-10-28 |
| Cluster | Refuted as frozen (B3g row 2 for disk: the five numeric-values files change by up to 26.8 % in total across a 16,384-fold change of the constants; part (b) "do not track" is too strong); heap not resolvable; control moved | does not cap (no ceiling; SAI bytes scale 3.99 x with rows at every constant; 28.3 of 49.1 MB identical across builds) | run 1 + self-check | 2026-10-28 |

**Positive control:** unit: a growing `long[]` for the same N moves the histogram by 8 N + 48 (8,388,656 / 33,554,480 / 134,217,776 B) while the writer's stays at 8 bs + 16. Cluster: `segment_write_buffer_size` 16 MiB against 1024 MiB: gauge peak 16.0 MiB against 1,024 MiB, 848 against 8 `Global limit` flush lines, heap peak 2,511 against 4,045 MiB; and the stock build at 750,000 against 3,000,000 rows: total SAI bytes 12.3 against 49.1 MB (3.99 x).

**Feedback filed:** section D of the case file (dated 2026-10-28, uncommitted); the audit's amendments B5 (items 1 to 7, 2026-10-28) and the post-freeze correction B5.8 are in the case file; the final sha256 is in section 1 and in the final report. `_INDEX.md`, `HANDOFF.md`, `writeup-set-A.csv` and `hardcoded-batches.md` are for the orchestrator.
