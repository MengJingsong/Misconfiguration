# block_packed_max_block_size-checkblocksize-blocksize--autonomous — stage-4 results  <!-- file: results/block_packed_max_block_size-checkblocksize-blocksize--autonomous.md; the stem ends in --guided or --autonomous -->

> **Case:** [`block_packed_max_block_size-checkblocksize-blocksize--autonomous`](../../stage3-ai-deep-read/cases/block_packed_max_block_size-checkblocksize-blocksize--autonomous.md)
>
> **Status:** verdict filed 2026-10-28 — unit and cluster Confirmed (does not cap); no run 2
>
> **Outcome class:** true negative (stage-3 estimate `negative`, stage-4 effect `does not cap`)
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
| **Case-file version** | sha256 before the audit: `17a6ad1b23438e070dad83b280e0cee30ec1396f871822dfc6d4697d38906c1b`. **Frozen version (after the audit's amendments B5.1-B5.7 of 2026-10-28, taken before any reading): `90ea9f2c57e9c3562fc36bbf3453dee753a123fa77941f3beb282a3f66676d94`.** After the post-freeze correction B5.8 (control condition (iii), made after the first cluster arm; no change to claim, predictions or rows): `f881da6aa28a5cc4a87ef717921bb70e4d104e5699281241d08538b265a1634f`. **Final, after section D (stage-4 feedback): `b167723c5e5b1ccaad7b11271e6eb27d1b5de5e3aad5e0c98da61b0f3dccac7e`.** File committed at `b68711e5` (HEAD); the amendments and feedback are uncommitted. |
| **Harness** | `harness/block_packed_max_block_size-checkblocksize-blocksize--autonomous/` (uncommitted; README there) |
| **Tiers and values** | Unit: sizes 32, 96, 64, 128, 16384, 2^20, 2^26, 2^27, 2^28 on the stock build; 128, 16384 (and 2^28) on a MAX_BLOCK_SIZE = 2^28 build; forged-reader cases. Cluster: builds stock, max1m (2^20), max8k (2^13) with row counts 750k / 1.5M / 3M on stock; segment buffer control. |
| **Audit bottom line** | **Ready after amendments** — 2026-10-28 |

### 1.1 Design audit

The requirements are in the README, "Step 0 — the design audit". One row per
line of each group; cite the case-file section checked.

| Group | Check | Rating (Met / Partly / Not met) | Note (section checked) |
|---|---|---|---|
| A. Core question | constrained quantity is memory or disk bytes | Met | A2: heap bytes of the fixed scratch array(s) (a count of longs with a derivable byte size) and the on-disk component bytes. |
| A. Core question | knob varied, >= 3 values incl. default — or another approach, with the reason | Met | B2b has nine sizes straddling both branches of the check; B3b three builds of the constant plus row counts. The constant is hard-coded (A1), so rebuilds are the only way to vary it (stated). |
| A. Core question | real resource measured, not only the counter (gap named) | Partly -> Met | Unit: thread-allocated bytes and heap histograms; cluster: a Byteman ledger of the exact array lengths, JMX heap/RSS samples (noisy, named as such) and component file bytes (B5). |
| A. Core question | usage driven to the limit and past it | Met | The check fires many times per run (arithmetic in B2c/B3c and B5); a hard-coded constant has no limit to exceed beyond that. |
| A. Core question | positive control (negative estimate) | Partly -> Met | Unit: 2^27 accepted / 2^28 rejected pair (the bound binds on what is accepted) and the stock-vs-patched-bound comparison. Cluster: segment buffer control (replaces the memtable_heap_space control, which does not apply to the index-build path) and rows 1 : 2 : 4. |
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
| D. Runnable | load-bearing citations spot-checked against the pinned source | Met after corrections | `SAICodecUtils.java:127-144`, `AbstractBlockPackedWriter.java:34-35, 49-52`, `BlockPackedReader.java:55`, `MonotonicBlockPackedReader.java:53`, `NumericValuesWriter.java:34-35, 49` match the pinned source. Slip: messages at `:133`/`:142` (amended). The Ground/A2 claim "check precedes allocation" holds (`:49` before `:51-52`). |

| # | Recommendation | Applied? (amendment date and commit, or "left for stage 3") | Why |
|---|---|---|---|
| 1 | B2a: `java -cp` run form; -Xmx6g for the 2^28 patched arm | Applied (B5.1) | 2^28 longs = 2 GiB |
| 2 | B2c: forged reader metadata procedure; report not run if impossible | Applied (B5.3) | unspecified |
| 3 | B3: 750k/1.5M/3M rows, seed + CREATE INDEX, memtable control replaced by segment-buffer control, ledger | Applied (B5.4-B5.6) | memtable_heap_space does not act on the index-build path; proportion |
| 4 | B3: monotonic 16384 vs 8192 expectation as the disallow evidence | Left as filed | row 5 of B3g already states it |

Run 2 is not planned, so the agreement criteria are not filled.

## 2. Environment

| Field | Run 1 |
|---|---|
| Date | 2026-10-28 (unit 17:48 MDT; cluster 18:37 to 19:14 MDT) |
| Node | `pc39` (`node1.jason92-321705.misconfiguration-pg0.cloudlab.umass.edu`), 40 cores, 251 GiB |
| OS / kernel | Ubuntu 22.04.2 LTS, `5.15.0-198-generic` |
| JDK / Ant | OpenJDK 11.0.32.1 / Apache Ant 1.10.12 |
| Local source | `~/s4-b34/base` (`copy-source.sh` copy of `cassandra/cassandra-5.0.9/` at repository commit `b68711e5`, `ant build-test`, `ant jar`); variants `~/s4-b34/v-max28`, `v-max1m`, `v-max8k` (`AbstractBlockPackedWriter.java:35` edited by `sed`, `AbstractBlockPackedWriter.java`, `BlockPackedReader.java`, `MonotonicBlockPackedReader.java` touched, patches in `run1/build-patches/`, `ant jar`; `javap -constants` shows `MAX_BLOCK_SIZE = 8192` in the 2^13 build and the readers recompiled) |
| Case-file / harness commit | `b68711e5` with uncommitted amendments (sha256 in section 1) / uncommitted |
| Storage for node data | local disk `~/s4-b34/cl/maxblock/node`; seeds `~/s4-b34/seeds/sai-{750000,1500000,3000000}` |
| Full logs | `pc39:~/s4-b34/logs/maxblock/` (`unit/run1/`, `cluster/<arm>/`) |

**Instrument checks before run 1:** the first version of the unit launcher was started once and stopped after about 12 cells (it showed a 566,096-byte allocation for the first rejected range-message construction, i.e. exception-message class loading; the range message path is now warmed up in the probe; the 12 cells were discarded, none was a reading used later). The cluster engine was shaken down in the sibling case's folder (disclosed there).

## 3. Runbook defects

| # | Run | Step | Problem | Fix | Decision | Case-file commit |
|---|---|---|---|---|---|---|
| 1 | cluster, first attempt (no reading) | B3a / engine | the 1.5M seed was being built by this case's engine under cluster name `stage4-maxblock` while the other seeds carried `stage4-blockindex` (a start-up check refuses a data directory of another cluster name); I stopped the chain, removed the half-built seed and moved the failed attempt's logs to `~/s4-b34/logs/failed-attempt-clustername/`; one cluster name per kind of seed in `cluster-run.py` | tier restarted from its beginning | AI, 2026-10-28 | none |
| 2 | cluster, before this case's first arm | B5.5 control (iii) | as in the sibling case: the default arm reaches its 1024 MiB limit at 3M rows (8 `Global limit` lines), so "only in the 16 MiB arm" cannot hold | B5.8 (dated 2026-10-28): (iii) = more `Global limit` lines in the 16 MiB arm (848) than in the default arm (8) | AI, 2026-10-28 | none |
| 3 | cluster, arm M8k-750k | engine wait loop | the build can never complete in the 2^13 build (the writer throws), and the engine waited its full 1,500 s for the index to appear in `IndexInfo` (reported as "INDEX build NOT complete after 1508 s") | none needed for the verdict (the arm ended normally, the node stayed up, `rebuild_index` returned rc 2, the queries failed with `INDEX_NOT_AVAILABLE`); recommendation: wait for the first `Unable to build indexes` line in the arm that expects the failure | AI, 2026-10-28 | none |
| 4 | unit analysis | `analyze_unit.py` | thresholds fixed after seeing the instrument: "rejected before any numBlocks array" uses < 1 MB (the rejection itself allocates 226 KB for the exception), the forged mono reader at bs 64 allocates 78 MB (not "> 100 MB"; 15.6M blocks x 5 B), and stock vs patched total allocation is compared within 1 % (JIT noise of about 1 KB between repetitions of one arm) while `ctorAlloc` is compared exactly | thresholds recorded in the script; they do not touch a prediction | AI, 2026-10-28 | none |
| 5 | B3f detail | B3f "the other writers (128) still construct" | in the 2^13 build the `SSTableComponentsWriter` constructor aborts at its second writer (`:59`, the first monotonic one), so only the first 128-writer (`:58`) is constructed per attempt (4 attempts: 4 `BPW 128` ledger lines), not all the plain ones | none; the B3g row is about the throw, which occurred | AI, 2026-10-28 | none |

## 4. Run 1

**Scope:** unit tier: 210 JVMs (arms `stock` -Xmx3g and `patched` (MAX_BLOCK_SIZE = 2^28) -Xmx6g, 3 repetitions each of 18 writer cells, 7 `checkBlockSize` cells and 10 reader cells) and the upstream `SAICodecUtilsTest`; cluster tier: six node starts (S-750k, S-1500k, S-3M, M1m-3M, M8k-750k, ctl-seg16). **Command log:** `block_packed_max_block_size-checkblocksize-blocksize--autonomous/run1/unit/summary.txt`, `run1/cluster/summary.txt`; checkers `analyze_unit.py`, `analyze_cluster.py` (outputs `run1/analyze-unit.txt`, `run1/analyze-cluster.txt`) and the independent `selfcheck.py` (`run1/selfcheck.out`).

### 4.1 Readings

**Unit tier** (`run1/unit/<arm>-r<rep>-<mode>_<kind>_<size>_<arm>.out`; the three repetitions agree in every `ctorAlloc` and flush count):

| Size (power of two unless stated) | Stock build (bound 2^27) | `ctorAlloc` / `blockValues.length` | Patched build (bound 2^28) |
|---|---|---|---|
| 32 | rejected: "blockSize must be >= 64 and <= 134217728, got 32" | 904 B (no array) | rejected (bound `64..268435456`) |
| 96 (not a power of two) | rejected: "blockSize must be a power of two, got 96" | 888 B | rejected |
| 64 | accepted, shift 6 | 936 B / 64 | accepted |
| 128 | accepted, shift 7 | 1,448 B / 128 | same 1,448 B |
| 16384 | accepted, shift 14 | 131,496 B / 16,384 | same 131,496 B |
| 2^20 | accepted, shift 20 | 8,389,032 B | accepted |
| 2^26 | accepted, shift 26 | 536,871,336 B (0.5 GiB) | accepted |
| 2^27 | accepted, shift 27 | 1,073,742,248 B (1 GiB) | accepted |
| 2^28 | **rejected** ("... <= 134217728, got 268435456") | 904 B (no array) | **accepted**: 2,147,484,072 B (2 GiB) / 268,435,456 |

Writing 3 x bs values (capped at 2^22) then `finish()` in the cells with bs <= 2^21: 3 flushes in every cell, total allocation 858,632 B (bs 128) and 988,880 B (bs 16384) in the stock build against 859,048 B and 990,080 B in the patched build (within 0.2 %; `ctorAlloc` identical). Readers (`NumericValuesMeta` forged, `valueCount` = 10^9, null `FileHandle`): forged 99 and 2^28 (stock) rejected with `IllegalArgumentException` after 226,192 / 226,224 B (the exception only); forged 64 passes the check and allocates the `numBlocks`-sized arrays (15.6M blocks): plain reader 265,631,160 B, monotonic reader 78,136,008 B, forged 128: 132,818,664 B, each then ends in `NullPointerException` from `file.createReader()` (the null handle); in the patched build forged 2^28 passes the check (4 blocks, 6,232 B). Upstream `SAICodecUtilsTest`: 16 tests, 0 failures. 202 `EXPECTED` lines OK, 0 MISMATCH (`run1/analyze-unit.txt`).

**Cluster tier** (`run1/cluster/<arm>/`; heap = largest of 150 to 275 JMX samples at 500 ms; the `BPW` ledger has 15 lines per arm (3 sets of five writers) except where stated):

| Arm (build, rows) | `MAX_BLOCK_SIZE` seen by `checkBlockSize` | Ledger lengths | Total SAI bytes | Heap peak (MiB) | Seg-buffer gauge peak | `Global limit` lines | count queries |
|---|---|---|---|---|---|---|---|
| S-750k (stock, 750,000) | 134,217,728 | 128 x6, 16,384 x9 | 12,310,642 | 2,969 | 1,073,743,944 | 2 | 750,000 / 7,500 x3 OK |
| S-1500k (stock, 1,500,000) | 134,217,728 | same | 24,775,184 | 3,853 | 1,073,743,528 | 4 | 1,500,000 / 15,000 x3 OK |
| S-3M (stock, 3,000,000) | 134,217,728 | same | 49,133,244 | 3,945 | 1,073,743,912 | 8 | 3,000,000 / 30,000 x3 OK |
| M1m-3M (`MAX_BLOCK_SIZE` 2^20) | 1,048,576 | same | 49,133,244 (all 17 files byte-identical to S-3M) | 4,029 | 1,073,743,912 | 8 | OK |
| M8k-750k (`MAX_BLOCK_SIZE` 2^13) | 8,192 | 128 x4 only (12 lines: 4 `BPW`, 8 `CHK`) | 0 (3 partial files, 0 bytes) | 2,034 (until stopped) | 0 | 0 | failed: `INDEX_NOT_AVAILABLE` |
| ctl-seg16 (stock, 3M, 16 MiB) | 134,217,728 | same | 47,832,094 | 2,507 | 16,779,568 | 848 | OK |

M8k-750k in detail (`run1/cluster/M8k-750k/`): `java.lang.IllegalArgumentException: blockSize must be >= 64 and <= 8192, got 16384` from `SAICodecUtils.checkBlockSize(:142)` <- `AbstractBlockPackedWriter.<init>(:49)` <- `MonotonicBlockPackedWriter.<init>(:40)` <- `NumericValuesWriter.<init>(:61, :49)` <- `SSTableComponentsWriter.<init>(:59)`; "Unable to build indexes [sai.v_idx]" and "[sai.txt_idx] on SSTable" at `StorageAttachedIndexBuilder.java:229`, "Index build of v_idx failed. Please run full index rebuild to fix it." (`SecondaryIndexManager.java:844`); the 8 `CHK` lines are four attempts of `checkBlockSize(128)` and `checkBlockSize(16384)`; the node stayed up, `nodetool rebuild_index` returned rc 2 (same exception), count queries returned `INDEX_NOT_AVAILABLE` (`stdout-trace.txt`, `errors.txt`, `summary.txt`). Ratios S-1500k / S-750k = 2.01, S-3M / S-750k = 3.99 (total) and 3.89 (numeric files). `analyze_cluster.py`: 0 MISMATCH.

### 4.2 Conclusion and logic

1. **Validity.** The bound really differed between builds: the ledger's `CHK` lines show the third argument 134,217,728 (stock), 1,048,576 (M1m), 8,192 (M8k) [observed: `run1/cluster/<arm>/ledger.txt`]; the unit probe read the bound from the loaded class and printed `64..134217728` and `64..268435456` [observed: `run1/unit`]. Production sizes only reached the writers: the ledger of S, M1m and ctl arms has only 128 and 16,384 [observed]. The row-count variable worked (1 : 2 : 4) and all non-failing arms answered their count queries without `ERROR` lines [observed]. The segment-buffer cap was driven (8 limit flushes in S-3M at 1,024 MiB; 848 at 16 MiB) [observed: `flush-lines.txt`].
2. **Readings.** (a) Allocation at the production sizes is identical between the 2^27 and 2^28 builds to the byte (`ctorAlloc`) and within 0.2 % in total, and linear in blockSize (8 bs + 16 + about 0.5 KB of objects for 2^14 and above) [observed]. (b) M1m-3M and S-3M are byte-identical in all 17 SAI files, while heap peaks differ by 83.5 MiB, which is inside the 293 MiB spread between two identical arms seen in the sibling case with the same heap [observed; the comparison of peaks across cases is inferred]. (c) The monotonic reader at bs 64 allocates 78 MB where the plain one allocates 266 MB for the same 15.6M blocks [observed]; unrelated to the claim.
3. **Matched row.**
   Unit B2g row 1, "allocation at 128 / 16384 identical in stock and patched-bound builds, linear in blockSize for accepted sizes": `ctorAlloc` 1,448 / 131,496 in both builds, 8 bs + 16 +  small for all accepted sizes [observed]. Row 3, "2^27 accepted and about 1 GiB allocated; 2^28 rejected with no large allocation (positive control)": 1,073,742,248 B and a 904-byte rejection; and in the patched build 2^28 accepted with 2 GiB [observed]. Row 6's check ("forged reader size allocates `numBlocks` arrays before failing"): the reader rejected 99 and 2^28 after 226 KB and allocated 266 MB only for an accepted size, so the check precedes the arrays [observed].
   Cluster B3g row 1, "stock and `1 << 20` give the same component sizes; both scale with rows": S-3M and M1m-3M are byte-identical in every component; stock sizes grow 1 : 2.01 : 3.99 for 1 : 2 : 4 rows; the positive control (segment buffer, replacing the `memtable_heap_space` control as amended) moved: 16.0 MiB against 1,024 MiB, 848 against 8 limit flushes, heap peak 2,507 against 3,945 MiB [observed]. Row 5, "`1 << 13` build throws as predicted": the `IllegalArgumentException` from the first `MonotonicBlockPackedWriter` (16,384 > 8,192) and a failed index build [observed].
4. **Excluded rows.** Unit "allocation differs between stock and patched-bound builds": identical [observed]. "2^27 not accepted or 2^28 accepted (stock)": 2^27 accepted, 2^28 rejected [observed]. "Allocation not linear or OOM": linear up to 2 GiB with -Xmx3g / -Xmx6g, no OOM [observed]. Cluster "sizes or heap differ between stock and 1<<20": sizes identical, heap peaks differ by 83.5 MiB, inside the noise seen between identical arms in the sibling case [observed; noise carried over, inferred]. "Positive control shows no change / indexes never run": the control moved and the ledger shows the writers ran [observed]. "1<<13 does not throw": it threw [observed].
5. **Observed vs. inferred.** Inferred: that the heap-peak noise of the sibling case (4 GiB, same engine) applies here (this case has no repeated identical arm); that the build and flush paths are the same writers (the ledger shows the writers in the build path). The verdict depends on the byte-identical files and the exact allocation numbers, not on either.
6. **Deviations and gaps.** The memtable control of B3e step 6 was replaced by the segment-buffer control (B5.5, as amended, B5.8); the flush load by seed + `CREATE INDEX`; 1M / 4M / 16M rows by 0.75 / 1.5 / 3M (B5.4); the failing-build wait loop ran its full 1,500 s (defect 3); one run per arm; the 2^28 writer was not driven with adds (construction only) because of its 2 GiB buffer; no native-memory reading beyond RSS (5.1 to 5.2 GiB at every arm, dominated by the 4 GiB heap).
7. **Core question.** Usage followed the block size actually used (8 bs bytes per writer), not the bound: moving the bound from 2^27 to 2^28 (unit) or to 2^20 (cluster) changed nothing the node holds or writes (byte-identical files), the only effect of the bound was to reject sizes nobody passes (2^28 in the stock build, 16,384 in the 2^13 build, where the index build fails by exception instead of capping any usage). Memory and disk scaled with the rows (1 : 2.01 : 3.99), and the real cap, the segment buffer, bound the build (16.0 MiB gauge, 848 flushes). So `MAX_BLOCK_SIZE` caps nothing a running node uses.

**Conclusion (one line):** unit B2g rows 1, 3 (and the check-ordering row) and cluster B3g rows 1 and 5 - Confirmed (does not cap; positive control moved).

## 5. Self-check of run 1 — AI

### 5.1 Check of run 1's conclusion

`harness/.../selfcheck.py` re-parses the 210 unit outputs, `summary.txt`, the ledger, `files-*.txt`, `gauges-*.csv`, `flush-lines.txt` and the M8k trace/errors with its own regexes: 248 PASS, 0 FAIL (`run1/selfcheck.out`), including byte-identity of S-3M and M1m-3M, the `CHK 16384 64 8192` line and the range message in the M8k arm, and the 1 : 2 : 4 ratios.

| Part | Holds? | Note |
|---|---|---|
| 1. Validity | yes | Bounds in the ledger, ledger lengths, count queries, daemon stopped after each arm re-read. |
| 2. Readings | yes | Allocation equality re-computed from the `.out` files; the 83.5 MiB heap difference is reported, not used. |
| 3. Matched row | yes | Unit rows by the 3 x 2 x 18 writer cells; cluster rows by the identical files and the M8k trace. |
| 4. Excluded rows | yes | Same script. |
| 5. Observed vs. inferred | yes | The heap noise is inferred from the sibling case; not needed for the verdict. |
| 6. Deviations and gaps | yes | As listed. |
| 7. Core question | yes | Follows B1: the bound only rejects out-of-range sizes; usage depends on the size in use and on rows. |

### 5.2 Run 2?

No — 2026-10-28. The unit numbers are exact over three repetitions and the cluster files are byte-identical or deterministic; a second run would not change the matched rows.

## 6. Run 2 — optional

Not done.

## 7. Comparison

Not done.

## 8. Verdict — AI

**Stage-3 estimate:** negative. **Outcome class:** true negative (estimate `negative`, effect `does not cap`).

**Claim tested:** usage does not follow this constraint: raising or lowering the value of `MAX_BLOCK_SIZE` (or the accepted block size) within the range actually used does not change heap or disk used by SAI numeric-values components, which instead track row count and the fixed block sizes 128 / 16384; the constraint only rejects out-of-range sizes, and the 2^27 bound is never approached by a running node. Refuted if the node's heap or disk for these components moves with the bound, or if a production path ever allocates near `MAX_BLOCK_SIZE`.

| Tier | Verdict (B2g / B3g row) | Effect on the constraint | Basis | Date |
|---|---|---|---|---|
| Unit | Confirmed (B2g rows 1 and 3: identical allocation in stock and 2^28 builds; 2^27 accepted at 1 GiB, 2^28 rejected with no array, and accepted with 2 GiB when the bound is raised) | does not cap | run 1 + self-check | 2026-10-28 |
| Cluster | Confirmed (B3g rows 1 and 5: stock and 2^20 builds byte-identical; sizes 1 : 2.01 : 3.99 with rows; the 2^13 build throws as predicted; control moved) | does not cap | run 1 + self-check | 2026-10-28 |

**Positive control:** unit: the 2^27 / 2^28 pair (1 GiB accepted, 2^28 rejected with a 904-byte rejection) shows the bound binds on what is accepted. Cluster: `segment_write_buffer_size` 16 MiB against 1024 MiB (gauge 16.0 against 1,024 MiB, 848 against 8 limit flushes, heap peak 2,507 against 3,945 MiB), and the `1 << 13` build that makes the monotonic writer fail (the bound binds, but only on a size the code uses, and by exception).

**Feedback filed:** section D of the case file (dated 2026-10-28, uncommitted); B5 (items 1 to 7) and the post-freeze B5.8 are in the case file; final sha256 in section 1 and the final report.
