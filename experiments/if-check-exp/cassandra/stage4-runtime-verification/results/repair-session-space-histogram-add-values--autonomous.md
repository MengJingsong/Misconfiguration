# repair-session-space-histogram-add-values--autonomous — stage-4 results  <!-- file: results/repair-session-space-histogram-add-values--autonomous.md; the stem ends in --guided or --autonomous -->

> **Case:** [`repair-session-space-histogram-add-values--autonomous`](../../stage3-ai-deep-read/cases/repair-session-space-histogram-add-values--autonomous.md)
>
> **Status:** self-checked (2026-10-26); verdict filed; no run 2
>
> **Outcome class:** true negative (estimate negative; unit and cluster: Confirmed, does not cap) — open point on the "indirect" dependence, see §8
>
> **Agent:** autonomous (the suffix of the case-file stem). For an autonomous
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
| **Case-file version** | Repository HEAD when audited: `e776524` (case file modified in the working tree; the orchestrator commits it). Sha256 of the whole file after the audit's amendments (2026-10-26, second freeze): `d836ea0c6839efdc65fcb8b41811c94c005ce74eb8ba2b174a0aa109841efc2f`. **Frozen prediction and conclusion tables (B2f-g and B3f-g, the text from `**B2f.` to `**B2h.` plus from `**B3f.` to `**B3h.`): sha256 `b0c1cc09429e1f07b35025459c48dec6d3c5bdbe5172dc3ae9b688e48a062baa`** (script `harness/repair-session-space-histogram-add-values--autonomous/freeze-hash.py`). Recorded before any run or reading; after the feedback was written into section D the whole-file sha256 is `a519f184667e9a35813067127b01695651c2ea3678ad5926292b863c9cc7a581` while the frozen tables hash is unchanged (re-checked 2026-10-26 with `freeze-hash.py`). A first freeze (tables `d801e65b…`, file `e1f9ac05…`) was superseded the same hour, still before any run: reading `ValidationManager.java:62-63` again showed that the budget is computed in `int` arithmetic and wraps for repair_session_space >= 2048 MiB (S = 4096 gives budget 0, depth 1), so B2f's S = 4096 prediction was wrong; B2b/B2f/B2g were amended (S = 2047 and 2048 added, one B2g row added). The other amendments touch runbook text and one denominator in a B3f relation line. |
| **Harness** | `harness/repair-session-space-histogram-add-values--autonomous/` (written before run 1; committed by the orchestrator): `freeze-hash.py`, `HistogramBudgetProbe.java`, `unit-run.sh`, `unit-analyze.py`, `make-node-yaml.sh`, `cluster-run.py`, `jfr-sizes.py`, `cluster-analyze.py`, `selfcheck.py`, `README.md` (the last two were finished between the unit and the cluster run) |
| **Tiers and values** | Unit: S = 1, 8, 64, 512, 4096 MiB with RF 3, D = 20 and 10; RF 1 at S = 4096; direct `HistogramBuilder` sweep n = 10, 11, 20, 21, 2^10, 2^13, 2^17, 2^20, 2^20+1. Cluster: S = 700 / 64 / 8, D = 20, DEBUG; S = 700 INFO; S = 700 with D = 12. Two nodes on pc12 (127.0.2.1, 127.0.2.2). |
| **Audit bottom line** | **Ready after amendments** — 2026-10-26 (seven amendments applied, two recommendations left for stage 3) |

### 1.1 Design audit

The requirements are in the README, "Step 0 — the design audit". One row per
line of each group; cite the case-file section checked.

| Group | Check | Rating (Met / Partly / Not met) | Note (section checked) |
|---|---|---|---|
| A. Core question | constrained quantity is memory or disk bytes | Met | B1/A2: heap bytes of one `long[]` (8 B per leaf, 10*2^k longs); byte size derived exactly (16 + 8*len). |
| A. Core question | knob varied, ≥ 3 values incl. default — or another approach, with the reason | Met | B2b S = 1, 8, 64, 512, 4096 (default is 1/16 heap, set by the node's heap); B3b S = 8, 64, 700 and D = 20 / 12. The array's own size has no knob; the design says so (direct n sweep) and uses S/D through the leaf count. |
| A. Core question | real resource measured, not only the counter (gap named) | Partly | B2d thread-allocated bytes and `values.length` are real heap allocations; B3d JFR allocation events are the real sizes. Gap: the cluster tree 'bytes' is serialized size, not heap (amended B3f: judged against measureDeep per leaf); live peak of old+new array is computed from two events, not sampled. |
| A. Core question | usage driven to the limit and past it | Met | B2c reaches depth 20 (2^20 leaves, the depth cap) and S up to 4096; B3c 2M partitions on a 2-node ring reach 2^20 leaves per primary range (amended to `-pr`, see rec. 3). Past the cap: S=4096 at the unit tier. |
| B. Logic | each step says what it establishes | Met | B2e/B3e steps each name their output; B2g/B3g say what each reading means. |
| B. Logic | prediction stated in numbers or a clear relation | Met | B2f exact formula 10*2^ceil(log2(n/10)) (checked: 2^13 gives 10,240; 2^17 gives 163,840; 2^20 gives 1,310,720); B3f exact byte sizes 16+8*10*2^k. |
| B. Logic | every plausible outcome has a conclusions row with its evidence | Partly | B2g/B3g cover flat, follows, never reached, DEBUG-off allocation, shrink. Missing in B3g: a row for JFR showing no event at all with DEBUG on (instrument failed); it falls to 'Not confirmed (no matching row)' by the README rule, and the harness has an instrument check for it. |
| B. Logic | confirmation needs ceiling-follows-knob and direct disallow evidence | Met | Negative claim 'array not governed by S': confirmation needs array saturating at the depth cap while the control (tree) moves with S below the cap, plus INFO run with zero events as the 'branch fired only under DEBUG' evidence (B3g rows 1, 2, 8). |
| B. Logic | alternative explanations and their controls | Met | B2h/B3h: positive control (tree footprint vs S), negative control (INFO), direct builder sweep, fixed heap. |
| C. Specific | a human can follow it from the intro and §9a | Met | Claim B1, ground and traces are readable; arithmetic stated. |
| C. Specific | an AI can run §9b–§9e without re-deriving the code path | Partly | B2a/B2c/B3a/B3c/B3e had wrong or missing paths (rsync of ~/cassandra-5.0.9, `ks.t` vs stress's `keyspace1.standard1`, `-pr`, loopback addresses, tmpfs) — applied as amendments, section D. |
| C. Specific | knob, values, workload, commands, observables, sampling, stop conditions exact | Partly | Mostly exact. Not exact: how JFR sees arrays below the TLAB size (amended: fixed small TLAB), and the repair range count (amended: `-pr`). B2 'thread-allocated bytes below ~120 MB' is a loose upper bound, kept as filed. |
| D. Runnable | harness and environment prerequisites exist or are listed | Met | Listed in B2a/B3a (JDK 11, Ant, JFR in JDK 11, stress, jamm in build/lib/jars); harness is step-1 work (`harness/repair-session-space-histogram-add-values--autonomous/`). |
| D. Runnable | workload arithmetic reaches the limit (data, time, disk, memory) | Met | 2M rows (~0.5-1 GB per node) on tmpfs 126 GB; 3 GB heaps; depth 20 needs 2^19+1 partitions in the range (about 1M with the 50/50 tokens) and a budget of about 2^20 * (leaf+inner bytes) (S=700, RF 2 gives 367 MB, to be confirmed by the unit tier's measureDeep, which comes before the cluster tier). Without `-pr` the budget would be halved: amended. |
| D. Runnable | load-bearing citations spot-checked against the pinned source | Met | Checked in cassandra-5.0.9: HistogramBuilder.java:40-48, MerkleTree.java:139-148, 464-487, 1520-1541, ValidationManager.java:62-84, Validator.java:226-233, DatabaseDescriptor.java:596-616/4080-4101, logback.xml:132. Only callers of `HistogramBuilder` are the two MerkleTree methods (grep). One mismatch: B2c passed hashdepth=depth to `MerkleTree`; production passes RECOMMENDED_DEPTH=126 (`MerkleTree.java:89`, `MerkleTrees.java:110`): amended. |

| # | Recommendation | Applied? (amendment date and commit, or "left for stage 3") | Why |
|---|---|---|---|
| 1 | Run the unit tier as a standalone probe (javac against build/classes/main + jamm agent), not `ant testsome` | Applied, B2a, 2026-10-26 | `testsome` forks a 1 GiB JVM; `measureDeep` needs the jamm agent |
| 2 | Build the unit-tier tree through `MerkleTrees.addMerkleTree(1<<depth, range)` and `init()` like production; read back `tree.size()` | Applied, B2c, 2026-10-26 | hashdepth 126 in production; B2c passed `depth` |
| 3 | Cluster: `repair -full -pr keyspace1 standard1`, tokens +-2^62, `auto_bootstrap: false` | Applied, B3a/B3c/B3e, 2026-10-26 | stress creates `keyspace1.standard1`; without `-pr` each tree gets half the budget and S=700 sits at the depth-19/20 edge |
| 4 | Two nodes on one host: 127.0.2.1 and 127.0.2.2, JMX 7120/7121, native only on node 1, data on /dev/shm | Applied, B3a, 2026-10-26 | node assignment of this batch; recorded as an environment deviation (design wanted two hosts) |
| 5 | JFR sees small arrays: `-XX:-ResizeTLAB -XX:TLABSize=16k` on both nodes, instrument check on a known-answer driver before run 1 | Applied, B3a, 2026-10-26 | arrays below the TLAB size are allocated in TLABs and not reported one by one |
| 6 | B3f relation line: judge against `measureDeep` heap bytes per leaf, not the serialized 'bytes' line | Applied, B3f, 2026-10-26 | serialized size is not heap; reason independent of any reading |
| 7 | B2f/B2g: S=4096 prediction replaced; S = 2047, 2048 added; B2g row for the `int` wrap (`ValidationManager.java:62-63`) | Applied, B2b/B2f/B2g, 2026-10-26 (re-freeze) | source reading error found in the audit, no reading involved |
| 8 | Add a B3g row for 'JFR shows no `HistogramBuilder.add` event at all with DEBUG on' | Left for stage 3 | would change the conclusions table after the freeze point; the README's 'Not confirmed (no matching row)' covers it |
| 9 | B2f 'thread-allocated bytes below ~120 MB' bound is loose (iterator garbage per leaf is not measured before the run) | Left for stage 3 | kept as filed; the control run without the histogram call (B2h last bullet) subtracts it |

**Agreement criteria** — only if run 2 is chosen; filled before run 2 starts. (Not applicable: no run 2 is planned.)
One row per observable in the case's §9d:

| Observable | Must match | Tolerance |
|---|---|---|
| `<observable>` | exactly / in shape | `<what counts as the same>` |

## 2. Environment

| Field | Run 1 | Run 2 (fresh AI session, if done) |
|---|---|---|
| Date | 2026-10-26 | not done |
| Node (CloudLab name and type) | pc12 (`node1.jason92-320876…`, 40 cores, 251 GiB). **Environment deviation:** the cluster tier wants two nodes; both ran on pc12 at 127.0.2.1 and 127.0.2.2 (port slot 2; JMX 7120/7121; native 9042 on node 1 only). Other cases ran on pc12 at the same time. | |
| OS and kernel (`uname -r`) | Ubuntu 22.04, 5.15.0-187-generic | |
| JDK (`java -version`) | OpenJDK 11.0.32.1 | |
| Ant (`ant -version`) | Apache Ant 1.10.12 | |
| Local source copy (from `cassandra/cassandra-5.0.9/` at repository commit …) | `~/s4-b7-hv/c509` by `copy-source.sh` from repository commit `e776524` (`git describe`: cassandra-5.0.9), `ant build-test` (1 min 14 s) | |
| Case-file commit / harness commit | case file: working-tree version with sha256 `d836ea0c…` (uncommitted; the orchestrator commits); harness: uncommitted files under `harness/repair-session-space-histogram-add-values--autonomous/` | |
| Storage for node data | `/dev/shm/s4-b7-hv` (tmpfs, 126 GB), removed after the run; unit-tier scratch on `/dev/shm` too | |
| Full logs (path, outside the repo) | pc12 `~/s4-b7-hv-logs/` (unit: `unit/run1/`; cluster: `cluster/run1/<label>/` with the `.jfr` recordings, `cluster/run1/nodes/n{1,2}/` copies of debug.log, system.log, gc.log; `selfcheck.out`) | |

## 3. Runbook defects

| # | Run | Step (§9b–§9e) | Problem | Fix | Decision (date) | Case-file commit with the fix |
|---|---|---|---|---|---|---|
| 1 | audit | B2f (S = 4096) | Prediction said S = 4096 keeps 1,310,720: the budget `getRepairSessionSpaceInMiB() * 1048576 / RF` is `int` arithmetic and wraps for S >= 2048 (S = 4096 gives 0, depth 1) | B2b/B2f/B2g amended, S = 2047, 2048 added; re-frozen before any run | 2026-10-26 | not committed (orchestrator) |
| 2 | audit | B3a, B3c, B3e | `rsync` source path, `ks.t` vs stress's `keyspace1.standard1`, no `-pr`, no loopback/port/storage plan, JFR TLAB blind spot | amended (see section D of the case file) | 2026-10-26 | not committed |
| 3 | unit, first execution | `unit-run.sh` | the shell loop variable `S` overwrote the summary-file variable, so the `tree` rows were written to files named `1`, `8`, `64` … in the home directory | variable renamed; the stray files moved to `~/s4-b7-hv-logs/unit/run0-defective/`; whole unit tier re-run (deterministic; same values as the defective execution's `unit.log`) | 2026-10-26 | harness only |
| 4 | cluster, first execution | `cluster-run.py` | wrong MBean name (`type=ActiveRepairService`; the bean is `org.apache.cassandra.db:type=RepairService`); the run stopped before any repair | fixed; `start`/`resume` subcommands added | 2026-10-26 | harness only |
| 5 | cluster, first r1 (shakedown) | B3d JFR | with default JFR buffers some allocation events were missing (e.g. one 5,242,896 B array of the second call); `FlightRecorderOptions` buffers enlarged on both nodes; the first r1 is kept only as `run1/shakedowns/`, and the whole sequence r1..r1b was re-run on the same data | instrument change, not a prediction change | 2026-10-26 | harness only |
| 6 | cluster | B3d / B3f ("the debug.log shows a tree of 2^20 leaves") | not observable: `ValidationManager.java:83-84` logs `trees.size()` before `init()`, so every run printed "Created 1 merkle trees with merkle trees size 1, 1000064 partitions, 92 bytes". The frozen sentence cannot be satisfied | not amended (the sentence is in the frozen B3f); the leaf count is taken from the sum of the "Partitions per leaf" bucket counts printed by `Validator.complete()` (2^depth + 1 values) and from the array sizes themselves | 2026-10-26 | none |
| 7 | cluster | B3d heap sampling | `jstat -gc` wrote empty files (the JVM runs without the shared perf memory); heap was not sampled during validation | not fixed; the B3g row "heap shows no visible bump" is recorded as not observed (the GC log's pre-pause heap is dominated by garbage and is not an array signal) | 2026-10-26 | none |

## 4. Run 1

**Scope:** unit tier S = 1, 8, 64, 512, 2047, 2048, 4096 (RF 3, D 20 and 10), RF 1 (S = 2047, 4096), RF 2 (S = 700, 64, 8, and D = 12 at S = 700), direct sweep n = 10 … 2^20+1; cluster tier r1 (S 700, D 20, DEBUG), r2 (INFO), r3 (S 64), r4 (S 8), r5 (D 12), r1b (repeat of r1). **Command log:** `repair-session-space-histogram-add-values--autonomous/run1/` (`unit/summary.txt`, `unit/analyze.txt`, `cluster/<label>/summary.txt`, `cluster/analyze.txt`, `selfcheck.out`); full logs in §2.

### 4.1 Readings

**Unit tier** (`run1/unit/summary.txt`; every row is also in `~/s4-b7-hv-logs/unit/run1/unit.log`)

| Test or assertion | Result | Evidence (file) |
|---|---|---|
| direct n = 10, 11, 20, 21, 1024, 8192, 2^17, 2^20, 2^20+1: `values.length` | 10, 20, 20, 40, 1,280, 10,240, 163,840, 1,310,720, 1,310,720 = 10*2^ceil(log2(n/10)) | unit/summary.txt |
| tree, RF 3, D 20: S = 1, 8, 64, 512, 2047 | depth 10, 13, 16, 19, 20; leaves 1,024 … 1,048,576; `values.length` 1,280, 10,240, 81,920, 655,360, 1,310,720 | unit/summary.txt |
| tree, RF 3: S = 2048 and 4096 | `availableBytes` -715,827,882 and 0; `rangeAvailableBytes` 1; depth 1; leaves 2; `values.length` 10 (also RF 1, S = 4096) | unit/summary.txt |
| tree, RF 3, D 10: S = 1 … 2047 | depth 10, leaves 1,024, `values.length` 1,280 for all S | unit/summary.txt |
| tree, RF 1, S = 2047, D 20 | depth 20, `values.length` 1,310,720 | unit/summary.txt |
| tree, RF 2: S = 700 / 64 / 8 (D 20); S = 700 (D 12) | depth 20 / 17 / 14 / 12; `values.length` 1,310,720 / 163,840 / 20,480 / 5,120 (array 10,485,776 / 1,310,736 / 163,856 / 40,976 B) | unit/summary.txt |
| positive control `measureDeep(tree)` (RF 3, D 20) | 106,632 / 852,104 / 6,815,880 / 54,526,088 / 109,052,040 B for S = 1 / 8 / 64 / 512 / 2047; 104 B per leaf unhashed (a 32-byte hash array measures 48 B) | unit/summary.txt |
| thread-allocated bytes of `histogramOfRowCountPerLeaf()` at depth 20 | 88,081,344 B (median of 3, after one warm-up); iteration only 67,109,416 B | unit/summary.txt |
| array bytes per leaf; array / `measureDeep(tree)` | 10.0 B; 0.096 unhashed, about 0.05 with leaf and inner hash arrays added | unit/analyze.txt |
| `unit-analyze.py` | every EXPECTED line "yes" except one: "S = 512 (RF 3): depth 20 …" is "NO" because depth 19 was reached (B2f made it conditional, "if reached") | unit/analyze.txt |

**Cluster tier** (two nodes, RF 2, 1.97 M partitions each, `repair -full -pr keyspace1 standard1`; each node validates the same range, so the rows are per node; `run1/cluster/<label>/jfr-sizes-n*.txt`, `debuglog-n*.txt`)

| Capacity value | Run (control / A / B / C) | Observable (§9d) | Reading | Evidence (file) |
|---|---|---|---|---|
| S = 700, D 20, DEBUG | r1 | largest `HistogramBuilder.add` array, node 1 / node 2 | 10,485,776 B / 10,485,776 B, each size twice (count and size call); 5,242,896 B before it | cluster/r1/jfr-sizes-n1.txt, -n2.txt |
| same | r1 | "Partitions per leaf" bucket sum | 1,048,577 on both nodes | cluster/r1/debuglog-n*.txt |
| same | r1 | "Created ... merkle trees" line | "merkle trees size 1, 1000064 partitions, 92 bytes" (pre-init; defect 6) | cluster/r1/debuglog-n1.txt |
| S = 700, D 20, **INFO** | r2 (negative control) | array events, "Partitions per leaf" lines | zero events, zero lines, both nodes | cluster/r2/jfr-sizes-n*.txt, debuglog-n*.txt |
| S = 64 | r3 | largest array; bucket sum | 1,310,736 B on both; 131,073 | cluster/r3/ |
| S = 8 | r4 | largest array; bucket sum | 163,856 B on both; 16,385 | cluster/r4/ |
| S = 700, D 12 | r5 | largest array; bucket sum | 40,976 B on both; 4,097 | cluster/r5/ |
| S = 700, D 20 | r1b (repeat) | largest array | 10,485,776 B on both nodes, same as r1 | cluster/r1b/ |
| all | all | repair result | rc 0, "Repair completed successfully", 7.8 to 10.8 s | cluster/<label>/summary.txt |
| all | all | heap during validation | not sampled (defect 7) | n/a |

### 4.2 Conclusion and logic

1. **Validity.** The limit was reached: depth 20 (1,048,577 values in the first histogram) at S = 700 on both nodes [observed: cluster/r1/debuglog-n1.txt, selfcheck.out]; depth 20 in the unit tier at S = 2047 (RF 3 and RF 1) and S = 700 (RF 2) [observed: unit/summary.txt]. Held fixed: heap 3 GiB on both nodes [observed: node system.log "Heap size: 3.000GiB/3.000GiB"], the same data for all runs (one SSTable per node, 1,972,278 partitions estimated, compacted before r1) [observed: cluster/tablestats-n1.txt, -n2.txt], knobs read back from both nodes before each repair [observed: cluster/<label>/summary.txt, "read back -- yes"], JFR TLAB option on both nodes [observed: harness README instrument check]. Valid.
2. **Readings.** The `jstat` samples are empty (defect 7). The "Created" line cannot show the leaf count (defect 6). JFR omits some small (< 15 KB) and an occasional mid-size allocation event (e.g. one 327,696 B event on r3 node 2); the largest arrays and every size from 20,496 B up appear twice on all runs except that one, so no conclusion rests on a missing event [observed: selfcheck.out]. The first-histogram value count is 2^depth + 1, one more than `tree.size()` [observed: bucket sums]; the capacity formula gives the same array for n and n+1 at all sizes read.
3. **Matched row.** Unit: B2g rows "values.length follows the formula and is identical across S at equal n" and "n and values.length rise with S until depth 20, then stay constant at 1,310,720 (claim holds: the cap that binds is the depth cap)", plus the row added for S = 2048 / 4096 (budget wraps, depth 1, `values.length` 10) [observed: unit/summary.txt, unit/analyze.txt]. Cluster: B3g rows "No `HistogramBuilder.add` allocations with INFO, allocations with DEBUG" (r2 against r1, r3, r4, r5, r1b) and "Largest array falls with S at S = 8, 64 (below the cap): dependence only through leaf count (indirect); claim still holds", with the largest array at S = 700, D 20 equal to the unit tier's RF 2 prediction 10,485,776 B [observed: cluster/analyze.txt].
4. **Excluded rows.** "Builder array shrinks or is truncated when S is small at equal n": at equal n the array is the same size for every S and RF (one `values.length` per n over all 29 unit rows) [observed: unit/analyze.txt]. "n = 2^20+1 exceeds 1,310,720": 1,310,720 at n = 1,048,577 (direct and cluster bucket sum) [observed]. "Array allocated with DEBUG off": none in r2, both nodes [observed: cluster/r2/jfr-sizes-n*.txt]. "Largest array still 10,485,776 B at S = 8": it is 163,856 B [observed: cluster/r4]. "Array exceeds the tree size per leaf": the array is 10 B per leaf against 104 B (unhashed) to about 200 B (with hashes) of tree heap per leaf, a ratio of 0.05 to 0.10 [observed: unit/analyze.txt; the hashed figure is [inferred: two 48 B hash arrays added by hand to the unhashed `measureDeep`]]. "Depth 20 never reached / control flat": depth 20 was reached and the control moved.
5. **Observed vs. inferred.** Inferred: (a) the unit tier's `values.length` for a tree is computed from `tree.size()` with a separately built `HistogramBuilder`, not read from the builder inside `histogramOfRowCountPerLeaf()` [inferred: capacity formula applied to `tree.size()`, cross-checked by the cluster arrays]; (b) the unit tier's positive control is an unhashed tree [inferred: real trees add hash arrays]; (c) the effect of the `int` wrap in a running node was not run; the probe reproduces the arithmetic of `ValidationManager.java:62-63` in the same JVM types [inferred]; (d) the cluster tier's tree size is taken from the histogram bucket sums, which come from the code under test [inferred: the number of leaves visited]; (e) "the array is outside the repair_session_space budget" rests on the source (`MerkleTree.java:1534-1539` counts only node and hash bytes) [inferred: source reading, spot-checked].
6. **Deviations and gaps.** Two nodes on one host (loopback); other cases ran on the host at the same time; S above 700 was not run in the cluster tier (the plateau across S rests on the unit tier: RF 3 / S = 2047, RF 1 / S = 2047, RF 2 / S = 700 all give 1,310,720); no heap sampling; the frozen B3f sentence about the "Created" line could not be checked; the 5 to 20 percent relation was judged on `measureDeep` (amended) and gave 5 to 10 percent; one first-r1 shakedown with default JFR buffers was discarded (defect 5).
7. **Core question.** The `long[]` that `HistogramBuilder.add` grows is not budgeted: its size is a function of the number of values (10*2^ceil(log2(n/10)) longs, identical across S at equal n), n is the leaf count of a tree whose size the budget limits (depth 10 to 20 as S goes 1 to 2047 MiB), it stops growing at the depth cap (1,310,720 longs, 10,485,776 B) and falls to 10 longs when the `int` budget wraps at S >= 2048 [steps 1, 3, 4 above]. It exists only when DEBUG is on (r2 against the others). So the constraint does not cap this allocation as an object of its own; it moves with S only through the tree's leaf count, adds about 5 to 10 percent of the tree's heap per leaf on top of the budget during the DEBUG-only logging, and is never charged to the budget.

**Conclusion (one line):** unit: B2g "values.length follows the formula; identical across S at equal n" and "rise with S until depth 20 then constant", plus the S >= 2048 wrap row — confirmed (claim holds). Cluster: B3g "no allocations with INFO, allocations with DEBUG" and "largest array falls with S below the cap (indirect)" — confirmed (claim holds), with defects 6 and 7 recorded.

## 5. Self-check of run 1 — AI

### 5.1 Check of run 1's conclusion

Re-parsed by `selfcheck.py` (own code, run with `python3 -I`, does not import the run or analysis scripts) from the raw `.jfr` recordings, the node debug.log copies and the unit logs (`run1/selfcheck.out`).

| Part | Holds? (yes / no) | Note (file re-read) |
|---|---|---|
| 1. Validity | yes | `selfcheck.out`: depth 20 at S = 2047 / 700 (unit) and bucket sums 1,048,577 on both nodes in r1 and r1b; knobs read back "yes" in every `cluster/<label>/summary.txt`; heap line in system.log |
| 2. Readings | yes | `selfcheck.out`: 29 unit rows identical in summary.txt and unit.log, availableBytes recomputed in Python with the int32 wrap for every row (all "match True"), the formula holds on every row; JFR re-read: all `HistogramBuilder.add` sizes are 16+80*2^k; no other `long[]` over 1 MB allocated outside the TLAB in any window (0 on all 12 recordings) |
| 3. Matched row | yes | the sizes 10,485,776 / 1,310,736 / 163,856 / 40,976 B for r1 / r3 / r4 / r5 are the maxima in each recording on both nodes (`selfcheck.out`); r1b equals r1 |
| 4. Excluded rows | yes | r2 recordings contain no event with `HistogramBuilder.add` in the stack and the window of debug.log has 0 "Partitions per leaf" lines (`selfcheck.out`, r2 lines) |
| 5. Observed vs. inferred | yes | the inferred items (a) to (e) are listed in 4.2 part 5; none changes a matched row: (a) is cross-checked by the cluster arrays, (d) by the unit tier's leaf counts |
| 6. Deviations and gaps | yes | defects 6 and 7 are the only frozen-prediction parts not observed; neither contradicts a row |
| 7. Core question — the steps from reading to answer follow the audited logic | yes, with an open point | the claim "not governed by S" is read, as B2g/B3g word it, as "the array is a function of the leaf count, which depends on S only through the tree budget": confirmed. A reader who takes "the array follows S through the leaf count" as a cap would class the case differently (see §8 open point) |

### 5.2 Run 2?

**No** — decided 2026-10-26. The unit tier is deterministic (same values in the defective and the final execution), the cluster tier repeated r1 as r1b with identical largest arrays on both nodes, and the self-check re-parsed the raw recordings. Nothing in the conclusion depends on a reading that only one run could give.

## 6. Run 2 — fresh AI session (optional)

Not done.

## 7. Comparison — only if run 2 was done

Not done.

## 8. Verdict — AI

Jingsong may overrule any verdict at any time; record an override here with its date and reason.

**Stage-3 estimate:** negative. **Outcome class:** true negative (negative, does not cap).

**Claim tested:** the `long[]` that `HistogramBuilder.add` grows is not governed by `repair_session_space`: it is allocated on top of the Merkle-tree budget, depends on the leaf count (flat once the tree hits the depth cap of 20), and exists only when DEBUG logging is on. "Confirmed" below means this held.

| Tier | Verdict (§9a row; for an autonomous file, the B2g / B3g row) | Effect on the constraint | Basis | Date |
|---|---|---|---|---|
| Unit | Confirmed — B2g "values.length follows the formula, identical across S at equal n" and "rise with S until depth 20, then constant" (+ the 2026-10-26 wrap row) | does not cap | run 1 + self-check | 2026-10-26 |
| Cluster | Confirmed — B3g "no allocations with INFO, allocations with DEBUG" and "largest array falls with S below the cap (indirect)" | does not cap | run 1 + self-check | 2026-10-26 |

**Positive control** (a negative-estimate file only): the tree footprint the budget does bind moved with S: `measureDeep(tree)` 106,632 B at S = 1 to 109,052,040 B at S = 2047 (unit tier), and the leaf count (bucket sum) 16,385 / 131,073 / 1,048,577 at S = 8 / 64 / 700 (cluster). The array moved with it at 8 to 16 B per leaf and stopped at the depth cap; it never exceeded the tree. **Open point for the user to overrule:** because the array's size rises with S through the leaf count (up to the depth cap), a reader can class it as an indirect, loose cap (5 to 10 percent of the tree) and the case as a false negative; this file follows its own B2g/B3g wording ("indirect; claim still holds as not an independently budgeted object") and classes it a true negative.

**Feedback filed:** the case file's section D "Stage-4 feedback" updated (uncommitted; the orchestrator commits); amended sections B2a, B2b, B2c, B2f, B2g, B3a, B3c, B3e, B3f (dated 2026-10-26, before any run). Source findings: (1) `ValidationManager.java:62-63` multiplies `int * int` before the division, so `repair_session_space` >= 2048 MiB gives a negative or zero budget and one-level (2-leaf) trees; the arithmetic was reproduced in a probe and **not run in a node** (upstream candidate, check JIRA first); (2) the "Created ... merkle trees with merkle trees size N" debug line is logged before `init()` and always reports size 1 with a 92-byte serialized size (`ValidationManager.java:83-84`), which is misleading (upstream candidate); (3) the first histogram receives 2^depth + 1 values.

**Leftovers on pc12:** no process of this case; `/dev/shm` data removed; kept: `~/s4-b7-hv/c509` (build tree) and `~/s4-b7-hv-logs/` (about 100 MB: logs, `.jfr` recordings, `unit/run0-defective/`, `cluster/shakedown-r1/`).
