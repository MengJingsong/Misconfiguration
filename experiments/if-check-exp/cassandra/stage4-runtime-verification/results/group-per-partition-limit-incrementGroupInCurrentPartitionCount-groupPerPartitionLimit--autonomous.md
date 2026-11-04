# group-per-partition-limit-incrementGroupInCurrentPartitionCount-groupPerPartitionLimit--autonomous — stage-4 results

> **Case:** [`group-per-partition-limit-incrementGroupInCurrentPartitionCount-groupPerPartitionLimit--autonomous`](../../stage3-ai-deep-read/cases/group-per-partition-limit-incrementGroupInCurrentPartitionCount-groupPerPartitionLimit--autonomous.md)
>
> **Status:** verdict filed (run 1 done and self-checked, 2026-10-27; no run 2)
>
> **Outcome class:** true negative — stage-3 estimate `negative`; unit tier Confirmed (does not cap), cluster tier Confirmed (does not cap) (details in section 8)
>
> **Agent:** autonomous (tag g80, node pc12, port slot 10). "§9a" = B2f/B2g (unit) and B3f/B3g (cluster); feedback goes to the case file's section D.

## 1. Before run 1 — design audit and freeze

| Field | Content |
|---|---|
| **Case-file version** | repository HEAD at the audit `93d6365` plus the uncommitted case file (the orchestrator commits). sha256 of the whole file after the audit's amendments: `45b251e7dfa1721732bb4a6861cabbf3bdce0d02bd38baa9295da9dd26e9fb5b`. Frozen before any reading, prediction and conclusion tables: sha256 of the text from `**B2f.` to before `**B2h.` (B2f-g) `75ad53841fee9eb9bd9dcc1403f110367d8a0a7b0ae83c7a23dd5133d673497a`; of `**B3f.` to before `**B3h.` (B3f-g) `0ad6331b2c88c10c25229cec699b1318140255e1541324f48a4e871df331640d`. |
| **Harness** | `harness/group-per-partition-limit-incrementGroupInCurrentPartitionCount-groupPerPartitionLimit--autonomous/` (uncommitted until the orchestrator commits) |
| **Tiers and values** | unit: gppl in {1, 10, NO_LIMIT} x rowLimit in {100, 10000, NO_LIMIT} x shape A (20 x 1000 one-row groups) / shape B (4 x 100000 rows, one group each); cluster: L in {1, 100, unset} x fetch size {100, 5000} (+100000 as page-size control) x two GROUP BY shapes, 20 partitions x 200000 rows, one node, 1 GiB G1 heap |
| **Audit bottom line** | Ready after amendments — 2026-10-27 |

### 1.1 Design audit

| Group | Check | Rating | Note (section checked) |
|---|---|---|---|
| A. Core question | constrained quantity is memory or disk bytes | Partly | A2: the limit counts groups (result cardinality), not bytes; the case says so (negative estimate) and measures work/bytes read and heap. |
| A. Core question | knob varied, >= 3 values incl. default | Met | B2b {1,10,NO_LIMIT}, B3b {1,100,unset}; default is unset/NO_LIMIT. |
| A. Core question | real resource measured, not only the counter | Partly | B2d: unit measures rows pulled and thread-allocated bytes (proxy; no disk). B3d: `rchar` bytes read and sampled heap peak; the heap is a sampled proxy (named gap). |
| A. Core question | usage driven to the limit and past it | Met after amendment | B3c: 200000 rows/partition and 2000 groups/partition exceed every finite L; unit shape A has 1000 groups per partition > gppl 1, 10. NO_LIMIT arms are the unconstrained side. |
| A. Core question | positive control (negative file) | Partly -> fixed | B3h named fetch_size 100 vs 5000; 5000 rows x about 2.5 KB is about 12 MB, below the 50 MB floor B3g names, so the control could not register. Replaced by 5000 vs 100000 (amendment in B3b, B3f, B3g, B3h). Unit control (rowLimit) is sound. |
| B. Logic | each step says what it establishes | Met | B2c-B2e, B3c-B3e. |
| B. Logic | prediction stated in numbers or a clear relation | Partly -> fixed | B2f said shape B pulls "about 100000 per partition for every gppl", false once `rowLimit` (100 / 10000) binds (the counter stops the whole iteration at `rowLimit`); and gave no numbers for shape A under a binding `rowLimit`. B3f had no thresholds for "about equal" heap. Both rewritten with numbers. |
| B. Logic | every plausible outcome has a conclusions row | Partly -> fixed | Rows added: refuted-by-drop in bytes, "any other reading" fallback; `rowLimit` = NO_LIMIT added to the knobs so shape B can be seen. |
| B. Logic | confirmation needs ceiling-follows-knob and direct disallow evidence | Met after amendment | Shape A shows the disallow branch (rows returned = G, pulled = gppl+1 per partition); shape B shows the limit not firing. |
| B. Logic | alternative explanations and their controls | Met after amendment | rowLimit / page-size controls; noise arm of unrelated point reads. |
| C. Specific | a human can follow it | Met | B1-B3. |
| C. Specific | an AI can run it without re-deriving | Partly -> fixed | B2a pointed at a placeholder test name and a non-existent method `aggregatePkPrefix` (the method is `aggregatePkPrefixFactory`, `AggregationSpecification.java:112`); `jstat`, `/local/n1`, `drop_caches` replaced (B2a, B2b, B3a, B3d). |
| C. Specific | exact knob/values/workload/commands | Partly -> fixed | Query text, arm list, sampler, `rchar` readings and the page-size control now fixed. |
| D. Runnable | harness and prerequisites exist | Met | JDK 11, Ant, `copy-source.sh` on pc12; sibling harnesses exist to adapt; written in step 2. |
| D. Runnable | workload arithmetic reaches the limit | Partly -> fixed | 50 x 200000 rows would make each unlimited full scan about 3 minutes; reduced to 20 x 200000 (claim is per partition); "1.5 GB raw" corrected (10,000,000 x 100 B = 1 GB; with 20 partitions about 0.5 GB). Unit shape B reduced to 4 x 100000 (insert time, memtable size). |
| D. Runnable | citations spot-checked | Partly -> fixed | `DataLimits.java:1000, 1007, 663, 48, 115-122` match; `:~944-951` and `:~917-920` for the increment sites were wrong: `applyToRow` is `:926-964` with the call at `:936`; other callers are `:895` (applyToPartition, only when `isDone()`), `:1026` and `:1044` (onClose). `SelectStatement.java:130, 942, 1236, 1246-1248` match. `incrementRowCount :983-988` matches. |

New finding from the audit (not a recommendation, affects the reading of the code): under `GROUP BY <partition key>` only, `groupMaker.isNewGroup` is false for every row of a partition, so `incrementGroupInCurrentPartitionCount()` is not called in `applyToRow` and `groupInCurrentPartition` stays 0; the per-partition limit cannot stop such a partition at all (added to A2 and used in B2f).

| # | Recommendation | Applied? | Why |
|---|---|---|---|
| 1 | Replace the unreachable fetch_size 100-vs-5000 control by 5000 vs 100000 | applied 2026-10-27 (B3b, B3f, B3g, B3h; uncommitted) | control could not register |
| 2 | Make B2f/B3f numeric; correct shape B under a binding `rowLimit`; add `rowLimit` = NO_LIMIT | applied 2026-10-27 (B2b, B2f, B2g, B3f, B3g) | prediction must be decidable and true |
| 3 | Correct line cites and the API name | applied 2026-10-27 (A2, B2b) | citations |
| 4 | Scale 50 -> 20 partitions (cluster), 20 -> 4 partitions of 100000 rows (unit shape B); data on tmpfs, JMX sampler, `rchar`, young-generation cap | applied 2026-10-27 (B2c, B3a, B3c, B3d, B3e) | runnable on the shared node |
| 5 | Stage 3: fetch_size and the `rowLimit` of a GROUP BY query are the same number (`SelectStatement.java:908-912`); the estimate's "page size moves heap" is the row cap of the same query, not an independent knob | left for stage 3 | context |

**Note (after run 1):** filling section D (feedback) changed the whole-file sha256 to `f6f30ac9f9acf35ba2de4a80937d96d41e962f26b1462da1ddc355b3ace26943`; the B2f-g and B3f-g hashes above are unchanged (re-computed after the edit), and no other part of the file changed after the freeze.

**Agreement criteria:** not applicable (no run 2).

## 2. Environment

| Field | Run 1 |
|---|---|
| Date | 2026-10-27 |
| Node | `pc12` (`node1`), 40 cores, 251 GiB, shared with other cases; port slot 10 (127.0.10.1, JMX 7200) |
| OS and kernel | Ubuntu 22.04, `5.15.0-187-generic` |
| JDK / Ant | OpenJDK 11.0.32.1 / Ant 1.10.12 |
| Local source copy | `~/s4-b11-g80` (unit, `ant build-test`) and `~/s4-b11-g80-n` (node, `ant jar`), both from `copy-source.sh` of `cassandra/cassandra-5.0.9/` at repository commit `93d6365` (local baseline tagged `cassandra-5.0.9`) |
| Case-file / harness commit | uncommitted at run time (sha256 in section 1); the orchestrator commits |
| Storage for node data | tmpfs `/dev/shm/s4-b11-g80` (471,912,063 B of data, 7 sstables, compression off; removed after the run) |
| Unit test heap | `maxMemory` 1,056,309,248 B (build.xml default, not `-Xmx512m`; amended in B2a) |
| Full logs | `~/s4-b11-g80-logs/run1/` on `pc12` (`unit/`, `cluster/`, `cluster/arms/samples.csv` 100 ms samples); load log `~/s4-b11-g80-logs/load/`; shakedowns in `~/s4-b11-g80-logs/shake-*` |

## 3. Runbook defects

| # | Run | Step | Problem | Fix | Decision (date) | Case-file commit |
|---|---|---|---|---|---|---|
| 1 | audit | B3b/B3f/B3h | fetch_size 100 vs 5000 cannot move the heap peak by 50 MB (about 12 MB) | page-size control 5000 vs 100000 | 2026-10-27, before the freeze | uncommitted |
| 2 | audit | B2f | shape B "about 100000 rows pulled for every gppl" is false when `rowLimit` binds | rewritten with rowLimit = NO_LIMIT added | 2026-10-27, before the freeze | uncommitted |
| 3 | audit | B2b | `AggregationSpecification.aggregatePkPrefix` does not exist | `aggregatePkPrefixFactory` | 2026-10-27, before the freeze | uncommitted |
| 4 | shakedown | harness | python driver directory (`cassandra-driver-3.29.0` subfolder); analyzer `rows` check counted the mixed-shape warm-up arm | fixed in `cluster-run.py`, `analyze_cluster.py` | 2026-10-27, before run 1 | harness only |

No defect during run 1.

## 4. Run 1

**Scope:** unit tier (gppl {1,10,NO_LIMIT} x rowLimit {100,10000,NO_LIMIT} x shapes A, B, 5 reps) and cluster tier (one node lifetime: warm-up, 16 forward arms x 3 queries, noise arm, 6 reverse arms x 3 queries; 20 partitions x 200000 rows). **Command log:** `results/group-per-partition-limit-incrementGroupInCurrentPartitionCount-groupPerPartitionLimit--autonomous/run1/` (`unit/`, `cluster/`, `cluster-summary.txt`, `selfcheck.txt`).

### 4.1 Readings

**Unit tier** (`run1/unit/summary.txt`, raw `unit/stage4-lines.txt`)

| Test or assertion | Result | Evidence |
|---|---|---|
| first trigger (shape A, gppl=10, rowLimit NO_LIMIT) | 200 rows returned, 220 pulled | `unit/summary.txt` line 1 |
| shape A rows returned (rowLimit NO_LIMIT) | 20 / 200 / 20000 for gppl 1 / 10 / NO_LIMIT; `min(G, rowLimit)` in all 47 shape A lines (9 cells x 5 reps, plus the first-trigger and warm-up lines) | `unit/stage4-lines.txt` |
| shape A rows pulled | 40 / 220 / 20000 (= 20 x (gppl+1), 20000); in [rowLimit, rowLimit+21] when rowLimit binds | same |
| shape B (rowLimit NO_LIMIT), gppl 1 / 10 / NO_LIMIT | returned = pulled = 400,000; `counted` 4; `countedInCurrentPartition` 0 before close, 1 after | same |
| shape B median allocated bytes (rowLimit NO_LIMIT) | 112,268,176 for each of gppl 1, 10, NO_LIMIT (ratio 1.000) | `unit/summary.txt` INFO |
| shape B, rowLimit 100 / 10000 | pulled 100 / 10000 for every gppl; allocation 54,304 / 4,742,544 B | same |
| control (rowLimit): shape B median rows pulled | 100 < 10000 < 400000 | `unit/summary.txt` |

**Cluster tier** (`run1/cluster-summary.txt`; F = fetch size, L = PER PARTITION LIMIT; peak = max sampled heap used minus the post-GC value at arm start; bytes/query = node `rchar` delta over the arm / 3)

| Arm | Reading | Evidence |
|---|---|---|
| rows per query, all 22 arms x 3 queries | exactly as stated: shape A 20 / 2000 / 40000 for L = 1 / 100 / unset, shape B 20 | `cluster-summary.txt`, `cluster/markers.txt` |
| shape A, F=5000, forward: bytes/query for L = 1 / 100 / unset | 5.05 MB / 52.0 MB / 936.6 MB (0.5 % and 5.5 % of unset) | `cluster-summary.txt` |
| shape B, F=5000, forward: bytes/query for L = 1 / 100 / unset | 931,885,655 / 931,883,871 / 931,883,887 (ratio 1.000) | same |
| shape B, F=5000, reverse sweep: bytes/query | 931,883,863 / 931,883,864 / 931,883,887 | same |
| shape B, F=5000: peak heap MB, L = 1 / 100 / unset, forward / reverse | 96.4 / 96.3 / 95.8 and 96.9 / 96.3 / 96.2 | same |
| page-size control, shape B, L unset: peak heap MB at F = 5000 / 100000 | 95.8 / 641.9 (+546.1; spread 16.8) | same |
| shape B, L = 1, F = 100000 | peak 642.9 MB, bytes/query 496.6 MB | same |
| F = 100 (not judged), shape B L = 1 / 100 / unset | bytes/query 22.61 GB for each, peak 65-66 MB | same |
| shape A, L unset, F = 100000 / L = 1, F = 100000 | peak 649.0 MB / 12.6 MB | same |
| noise arm (300 unrelated point reads) | peak 16.8 MB | same |
| data directory before / after | 471,912,063 B both | `cluster/arms.txt` |
| node log segment | 0 ERROR lines; JVM flags as intended (1 GiB, G1, `G1MaxNewSizePercent=2`) | `cluster/vmflags.txt`, `selfcheck.txt` |

### 4.2 Conclusion and logic

1. **Validity.** The limit was reached and passed: shape A returned exactly `20 x L` groups (L = 1, 100) of 2000 available per partition, in 66 measured queries [observed: `cluster/markers.txt`; unit `stage4-lines.txt`: rows returned = G]. Heap 1 GiB G1, young generation cap, compression off and autocompaction disabled held in all arms [observed: `cluster/vmflags.txt`, `cluster/session-excerpt.txt`]. The unit control (rowLimit) moved rows pulled from 100 to 400,000 and the cluster page-size control moved the peak by 546 MB against a 16.8 MB spread [observed: `unit/summary.txt`, `cluster-summary.txt`]. Valid.
2. **Readings.** F = 100 reads 24 times more bytes than F = 5000 for a full scan (22.6 GB against 0.93 GB), for every L in shape B [observed: `cluster-summary.txt`]; that is per-page re-reading overhead, it does not depend on L, and it is outside the judged rules. At F = 100000 the bytes read fall to 0.50 GB.
3. **Matched row.** Unit tier: B2g row 1 — shape A matches B2f (returned = G or rowLimit, pulled = 20 x (gppl+1) / 20000), shape B at rowLimit NO_LIMIT pulls 400,000 rows with identical median allocation for gppl 1, 10, NO_LIMIT, and the control moves (100, 10000, 400000) [observed]. Cluster tier: B3g row 1 — row counts as stated, shape B bytes read ratio 1.000 and peak-heap spread 0.5 MB (forward) and 0.6 MB (reverse), the page-size control moves the peak by 546 MB (> 50 MB and > 3 x 16.8), disk unchanged [observed]. Shape A bytes scale with L (0.5 %, 5.5 %, 100 %) [observed].
4. **Excluded rows.** B2g row 2 (shape B drops at gppl = 1): rows pulled and allocation identical to NO_LIMIT. Row 3 (control does not move): control moved. Row 4 (limit never reached / first trigger): first trigger OK, shape A returned G. B3g row 2 (bytes drop at L = 1): ratio 1.000. Row 3 (control does not move): +546 MB. Row 4 (count differs or noise too large): counts exact, spread 0.5 MB, noise arm 16.8 MB. Row 5 (any other reading): all judged rules matched [observed].
5. **Observed vs. inferred.** Inferred: that the 96 MB shape B peak at F = 5000 is page content of the read path and not an artefact of the sampler (it is the same at L = 1, 100 and unset, in both sweeps, and 642 MB at F = 100000, so it follows F) [inferred: from the equality across L and the proportion to F]. Inferred: that the node's `rchar` delta is the bytes the read path asked of the sstable files (compression off, `file_cache_enabled` off); not cross-checked against `/proc/<pid>/io` `read_bytes` (zero on tmpfs).
6. **Deviations and gaps.** (a) Unit tier: one JVM for all values; shape B 4 x 100000 rows; allocated bytes (thread) are the real-resource proxy, no disk. (b) Cluster: 20 partitions instead of 50; no node restart between sweeps (the freshly restarted-node repeat of B3h is not done; the node has no data cache enabled and `rchar` does not see the OS page cache). (c) Heap is a sampled proxy (100 ms, `HeapMemoryUsage.used`, young generation about 20 MB). (d) Three queries per arm, no confidence interval; the forward and reverse sweeps agree to 4.2 MB at most for any arm (judged by the spread of 16.8 MB). (e) Only one data shape (100-byte values, 100 rows per ck1 value).
7. **Core question.** Unit tier: the limit stops a partition after gppl one-row groups (gppl+1 rows pulled), but under `GROUP BY <partition key>` it never fires and the same 400,000 rows are pulled and allocated at gppl = 1 as unlimited; the row limit does move the work. Cluster tier: with one group per partition `PER PARTITION LIMIT 1` reads the same 932 MB and peaks at the same 96 MB heap as no limit, while the page size moves the peak by 546 MB. So usage does not follow the constraint, and the constraint does not cap memory or disk read; it caps the number of groups returned, which in shape A reduces reads only because the data is read lazily until the groups are complete [observed for both tiers].

**Conclusion (one line):** unit tier B2g row 1 — confirmed; cluster tier B3g row 1 — confirmed.

## 5. Self-check of run 1 — AI

### 5.1 Check of run 1's conclusion

`harness/.../selfcheck.py` re-parses `unit/ant.log` (the echoed `STAGE4` lines, not the analyzer's file), and the cluster `markers.txt`, `arms.txt`, `samples.csv`, `vmflags.txt` and `system.log.segment` with its own windowing and per-query arithmetic (output `run1/selfcheck.txt`): 21 checks, `SELFCHECK ALL HOLD`.

| Part | Holds? | Note (file re-read) |
|---|---|---|
| 1. Validity | yes | `selfcheck.txt`: 66 queries all exact, 3 queries per arm, JVM flags, no ERROR / OOM, data unchanged |
| 2. Readings | yes | `cluster-summary.txt` and the selfcheck's own `bisect` windows give the same 96.4 / 96.3 / 95.8 MB and the same bytes per query |
| 3. Matched row | yes | both tiers' rules re-applied by the selfcheck without the analyzers |
| 4. Excluded rows | yes | identical pulled / allocation at gppl = 1; ratio 1.000; control +546.1 MB |
| 5. Observed vs. inferred | yes | the two inferred statements are tagged; neither enters a judged rule |
| 6. Deviations and gaps | yes | listed above |
| 7. Core question | yes | the steps follow B1: shape A shows the limit firing, shape B shows it not capping, the control shows the instrument can see a cap |

### 5.2 Run 2?

**No** (2026-10-27). Both tiers matched a Confirmed row with margins far from the thresholds (ratio 1.000 against 1.10; spread 0.5 MB against 30 MB; control +546 MB against 50 MB), the forward and reverse sweeps agree, and the result does not refute the estimate or confirm a bypass.

## 6. Run 2

Not done.

## 7. Comparison

Not applicable.

## 8. Verdict — AI

**Stage-3 estimate:** negative. **Outcome class:** true negative (negative, does not cap).

**Claim tested:** memory and disk read by a query with GROUP BY do not follow `groupPerPartitionLimit`: with the limit set to 1 versus a large value, the heap and bytes read for a workload dominated by one large group per partition stay essentially equal, whereas the page size (the row limit) moves them. The limit only changes the number of groups returned per partition.

| Tier | Verdict (B2g / B3g row) | Effect on the constraint | Basis | Date |
|---|---|---|---|---|
| Unit | **Confirmed** — row 1 (shape A follows gppl; shape B pulls 400,000 rows and allocates the same at gppl 1, 10, NO_LIMIT; rowLimit control moves) | does not cap | run 1 + self-check | 2026-10-27 |
| Cluster | **Confirmed** — row 1 (counts exact; shape B bytes read 931.9 MB and peak 96 MB at L = 1, 100, unset; page-size control +546 MB; disk flat) | does not cap | run 1 + self-check | 2026-10-27 |

**Positive control:** unit: `rowLimit` 100 / 10000 / NO_LIMIT moved shape B rows pulled 100 / 10000 / 400,000 (allocation 54 kB / 4.7 MB / 112 MB). Cluster: raising fetch_size from 5000 to 100000 raised the shape B peak from 95.8 to 641.9 MB (spread 16.8 MB).

**Outcome-class reason:** both tiers show that with a one-group-per-partition shape the limit has no effect on rows read, bytes read or heap, and that the group-count limit is a result cardinality; this agrees with the `negative` estimate.

**Open points the user may overrule:** (1) the audit's amendments changed the case's predicted numbers (all before any reading, dated in the case file): the page-size control (5000 vs 100000), 20 instead of 50 partitions, shape B of 4 x 100000 rows in the unit tier; (2) the "restart the node" repeat of B3h was not done.

**Upstream / documentation candidates:** none for a bug. Observation: under `GROUP BY <partition key>`, `PER PARTITION LIMIT n` never stops reading a partition (`groupInCurrentPartition` stays 0 inside a partition), which the CQL documentation does not state; and a smaller `fetch_size` multiplies the bytes read per full scan (22.6 GB at 100 against 0.93 GB at 5000).

**Leftovers on pc12:** no process; `/dev/shm/s4-b11-g80` removed; trees `~/s4-b11-g80` (with the copied test class), `~/s4-b11-g80-n`, driver `~/s4-b11-g80-drv`, logs `~/s4-b11-g80-logs/` kept (2.3 MB).

**Feedback filed:** the case file's section D updated (uncommitted); amendments in A2, B2a-B2h, B3a-B3h (2026-10-27).
