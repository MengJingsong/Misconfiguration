# group-per-partition-limit-isdoneforpartition-groupinCurrentPartition--autonomous — stage-4 results

> **Case:** [`group-per-partition-limit-isdoneforpartition-groupinCurrentPartition--autonomous`](../../stage3-ai-deep-read/cases/group-per-partition-limit-isdoneforpartition-groupinCurrentPartition--autonomous.md)
>
> **Status:** verdict filed (run 1 done and self-checked, 2026-10-27; no run 2)
>
> **Outcome class:** undetermined — stage-3 estimate `negative`; unit tier Confirmed (does not cap), cluster tier Not confirmed (no matching row), so the effect on the constraint is settled by one tier only (details in section 8)
>
> **Agent:** autonomous (tag g73, node pc07, port slot 3). "§9a" = B2f/B2g (unit) and B3f/B3g (cluster); feedback goes to the case file's section D.

## 1. Before run 1 — design audit and freeze

| Field | Content |
|---|---|
| **Case-file version** | repository HEAD at the audit `93d6365` plus the uncommitted case file (the orchestrator commits). sha256 of the whole file after the audit's amendments: `9498eed7fc73323a5ba0b8f84b927773cbd375dbd5860dbd0f708de197e66683`. Frozen before any reading, prediction and conclusion tables: sha256 of the text from `**B2f.` to before `**B2h.` (B2f-g) `6e162b51553ecbd5bd774a92b3414eb7d52ebc52318f7549158d8d93f7cdc5f3`; of `**B3f.` to before `**B3h.` (B3f-g) `1614570c5ccdac9371677e08258873776e5000caff156df9d8ccd7869f0a25c3`. |
| **Harness** | `harness/group-per-partition-limit-isdoneforpartition-groupinCurrentPartition--autonomous/` (uncommitted until the orchestrator commits) |
| **Tiers and values** | unit: N in {1, 10, 100, 1000, NO_LIMIT}, R=100000 rows in one partition; cluster: N in {1, 100, 10000, absent} at P=1000 plus the page-size control, 10 partitions x 200000 rows, one node, 1 GiB G1 heap |
| **Audit bottom line** | Ready after amendments — 2026-10-27 |

**Note (after run 1):** filling section D (feedback) changed the whole-file sha256 to `2e22ebfd58247437c3cc5bccb13d6d2dc768cddb8e23b141f348622159b3c18a`; the B2f-g and B3f-g hashes above are unchanged (checked), and no other part of the file changed after the freeze.

### 1.1 Design audit

| Group | Check | Rating | Note (section checked) |
|---|---|---|---|
| A. Core question | constrained quantity is memory or disk bytes | Partly | A2: the limit counts groups (a result cardinality), not bytes; derivable byte size per group is 100 B value plus row overhead. The case says so itself (negative estimate) and measures heap/disk. |
| A. Core question | knob varied, >= 3 values incl. default | Met | B2b {1,10,100,1000,NO_LIMIT}; B3b {1,100,10000,absent}; default is absent/NO_LIMIT. |
| A. Core question | real resource measured, not only the counter | Partly | B2d: unit tier has retained heap after GC and thread allocation, but cannot see node use (named). B3d: heap sampling is a proxy; gap named and sampler made exact by the 2026-10-27 amendment to B3d. |
| A. Core question | usage driven to the limit and past it | Met | B2c, B3c: N <= 100000 < partition size for every finite N; amendment confirms 200000 rows/partition. |
| A. Core question | positive control (negative file) | Not met -> fixed | B3b/B3f named `aggregation_subpage_size_in_kb`, which does not exist in 5.0.9 (`grep -rni subpage src/java conf` finds nothing). Replaced by the page-size control P=1000 vs 300000 (amendment in B3b/B3f/B3h). B2h control (materializing consumer) is sound if rows are cloned; the test clones them. |
| B. Logic | each step says what it establishes | Met | B2c-B2e, B3c-B3e. |
| B. Logic | prediction stated in numbers or a clear relation | Partly -> fixed | B2f exact (groups = min(N,R); rows pulled about N+const; retained heap flat within 5%). B3f "few percent / tens of MB" made numeric: 30 MB and three times the spread (amendment in B3f). |
| B. Logic | every plausible outcome has a conclusions row | Partly | B2g/B3g have confirm, refute, trace wrong, never reached, control failed. Missing: "heap follows N only when the page is larger than N x partitions per page". It is not a row; it is recorded as an exploratory finding (P=300000 arms) and as feedback, and a reading that fits no row is "Not confirmed (no matching row)". |
| B. Logic | confirmation needs ceiling-follows-knob and direct disallow evidence | Met | Groups = N per partition (disallow branch fired) in both B2g and B3g. |
| B. Logic | alternative explanations and their controls | Met after amendment | Page-size control rules out "workload too small to move heap"; the unit materializing control rules out "instrument blind". |
| C. Specific | a human can follow it | Met | B1, B2, B3. |
| C. Specific | an AI can run it without re-deriving | Partly -> fixed | Unit alternative (CQLTester) specified in B2a; amendment adds the iterator construction, one JVM, cloned rows. Cluster sampling specified in the B3d amendment. |
| C. Specific | exact knob/values/workload/commands | Partly -> fixed | Heap instrument and thresholds added; `cqlsh PAGING 1000` replaced in practice by the driver `fetch_size` (same effect, same page). |
| D. Runnable | harness and prerequisites exist | Met | JDK 11, Ant, `copy-source.sh` on pc07; harness written in step 2. |
| D. Runnable | workload arithmetic reaches the limit | Partly -> fixed | B3c said "about 2 GB raw": 2,000,000 x 100 B is 200 MB. Corrected in B3c; tmpfs holds it. |
| D. Runnable | citations spot-checked | Met | `DataLimits.java:1005-1008` (target at 1007), `:842` (field; case said `:839-840`, amended), `:926,:936,:943,:997-1002,:1126`, `SelectStatement.java:130,899-911,944,1274`, `DataLimits.java:48,117-121` all match. |

| # | Recommendation | Applied? | Why |
|---|---|---|---|
| 1 | Replace the non-existent `aggregation_subpage_size_in_kb` control by a page-size control | applied 2026-10-27 (case file B3b, B3f, B3h; uncommitted) | the control could not be set |
| 2 | Correct the data volume (200 MB, not 2 GB) | applied 2026-10-27 (B3c) | arithmetic |
| 3 | Make "tens of MB" numeric and name the heap instruments | applied 2026-10-27 (B3d, B3f) | prediction must be decidable |
| 4 | Unit tier: one JVM, rows cloned in the materializing control | applied 2026-10-27 (B2a) | `ant testsome` form |
| 5 | Citation `:839-840` -> `:842` | applied 2026-10-27 (A3) | line cite |
| 6 | Stage 3: add a conclusions row for "limit shapes a page when N x partitions < page size" | left for stage 3 | outcome missing from B3g |
| 7 | Stage 3: estimate reasoning ("memory per read governed by page size") should say the page size is itself a row cap of the same query (`SelectStatement.java:899-911`) | left for stage 3 | context for the control |

**Agreement criteria:** not applicable (no run 2).

## 2. Environment

| Field | Run 1 |
|---|---|
| Date | 2026-10-27 |
| Node | `pc07` (`node0`), 40 cores, port slot 3 (127.0.3.1, JMX 7130) |
| OS and kernel | Ubuntu 22.04, `5.15.0-187-generic` |
| JDK / Ant | OpenJDK 11.0.32.1 / Ant 1.10.12 |
| Local source copy | `~/s4-b11-g73` (unit, `ant build-test`) and `~/s4-b11-g73-n` (node, `ant jar`), both from `copy-source.sh` of `cassandra/cassandra-5.0.9/` at repository commit `93d6365` (local baseline tagged `cassandra-5.0.9`) |
| Case-file / harness commit | uncommitted at run time (sha256 in section 1); the orchestrator commits |
| Storage for node data | tmpfs `/dev/shm/s4-b11-g73` (228,028,843 B of data, removed after the run) |
| Full logs | `~/s4-b11-g73-logs/run1/` on `pc07` (`unit/`, `cluster/`, `cluster/arms/samples.csv` 100 ms samples); shakedowns in `~/s4-b11-g73-logs/shake-*` |

## 3. Runbook defects

| # | Run | Step | Problem | Fix | Decision (date) | Case-file commit |
|---|---|---|---|---|---|---|
| 1 | audit | B3b/B3f | `aggregation_subpage_size_in_kb` does not exist in 5.0.9 | page-size control | 2026-10-27, before the freeze | uncommitted |
| 2 | shakedown | B3d | with Cassandra's G1 settings (young generation floored at 50 % of the heap) a sampled peak measures garbage | node JVM given `G1NewSizePercent=1`, `G1MaxNewSizePercent=2`, `G1HeapRegionSize=4m` (harness, README item 3); the pools' collection usage was dropped as the decision metric | 2026-10-27, before run 1 | harness only |

No defect during run 1.

## 4. Run 1

**Scope:** unit tier (R=100000, N in {1,10,100,1000,NO_LIMIT}, 5 reps, plus the cloning control) and cluster tier (one node lifetime, 12 measured arms x 100 queries, 10 partitions x 10 reps). **Command log:** `results/group-per-partition-limit-isdoneforpartition-groupinCurrentPartition--autonomous/run1/` (`unit/`, `cluster/`, `cluster-summary.txt`, `selfcheck.txt`, `diag-drift.txt`).

### 4.1 Readings

**Unit tier** (`run1/unit/summary.txt`, raw `unit/stage4-lines.txt`)

| Test or assertion | Result | Evidence |
|---|---|---|
| first trigger N=10 | 10 groups, 11 rows pulled | `unit/summary.txt` line 1 |
| groups returned = min(N,R) | 1, 10, 100, 1000, 100000 in all 5 reps | `unit/stage4-lines.txt` |
| rows pulled | N+1 for N<R (2, 11, 101, 1001), R for NO_LIMIT | same |
| retained heap after GC (median, bytes) | 78,690,872 / 78,691,088 / 78,757,264 / 78,757,736 / 78,756,192 (N=1..NO_LIMIT): spread 0.08 % | same |
| allocated bytes (median) | 2,184 / 2,976 / 10,896 / 90,112 / 7,202,008; 72-108 B per pulled row for N>=100 | same |
| positive control (rows cloned and kept), retained delta | 1.8 kB / 5.3 kB / 41 kB / 398 kB / 39.6 MB; no-query noise swing at most 76.7 kB | same |

**Cluster tier** (`run1/cluster-summary.txt`; P = page size, peak = max sampled heap used minus the post-GC value at arm start)

| Arm | Reading | Evidence |
|---|---|---|
| rows per query, all 12 arms x 100 queries | exactly min(N, 200000): 1, 100, 10000, 200000 | `cluster/markers.txt`, `cluster-summary.txt` |
| P=1000, forward N=1 / 100 / 10000 / absent: peak MB | 8.4 / 16.8 / 15.0 / 54.9 | `cluster-summary.txt` |
| P=1000, reverse N=absent / 10000 / 100 / 1: peak MB | 54.0 / 16.8 / 12.6 / 8.4 | same |
| allocation per arm (forward, MB) | 7 / 17 / 1,415 / 28,338 | same |
| unrelated point reads (noise arm) | peak 8.4 MB | same |
| page-size control P=300000, N absent | peak 792.2 MB (737 MB above the P=1000 arm) | same |
| exploratory P=300000, N=1 / 100 / 10000 | peak 8.4 / 12.6 / 22.8 MB | same |
| data directory before / after | 228,028,843 B both | `cluster/arms.txt` |
| node log segment | 0 ERROR lines; JVM flags as intended (1 GiB, G1, `MaxNewSize=20971520`) | `cluster/vmflags.txt`, selfcheck |

### 4.2 Conclusion and logic

1. **Validity.** The limit was reached and passed at every finite N (each query returned exactly N groups of 200000 available) [observed: `cluster/markers.txt`; unit `stage4-lines.txt`]. Page size 1000, heap 1 GiB G1 held fixed [observed: `cluster/vmflags.txt`, `cluster/session-excerpt.txt`]. The unit tier's positive control moved retained heap 39.6 MB while the no-query noise was 77 kB [observed: `unit/stage4-lines.txt`]; the cluster page-size control moved the peak by 737 MB against a 8.4 MB spread [observed: `cluster-summary.txt`]. Valid.
2. **Readings.** At P=1000 the N=absent arm shows a 54-55 MB peak against 8-17 MB at the other N, in both sweep orders. The arm ran 375 s and allocated 28 GB; the peak is the highest sample of 3630 [observed: `cluster-summary.txt`].
3. **Matched row.** Unit tier: B2g row 1, "Groups returned = min(N,R); retained heap flat across N; allocated bytes scale with rows pulled" — groups exact, retained heap spread 0.08 %, allocation per pulled row 72-108 B [observed]. Cluster tier: no row. B3g row 1 needs "peak heap flat across N"; the frozen rule (peak at N=absent within 30 MB of N=1 in both sweeps) fails, 46.5 MB forward and 45.6 MB reverse [observed: `cluster-summary.txt`, re-derived in `selfcheck.txt`]. B3g row 2 needs "peak heap tracks N monotonically beyond run-to-run variance"; the frozen rule needs a strictly increasing peak with N in both sweeps, and the forward sweep is 8.4, 16.8, 15.0, 54.9 (N=10000 below N=100) [observed]. Counts equal N and the control moved, so rows 3 and 4 do not apply. The reading is **Not confirmed (no matching row)**.
4. **Excluded rows.** B2g row 2 (retained heap follows N) excluded by the 0.08 % spread; row 3 (groups != min) by exact counts; row 4 (counter never stops) by pulled = N+1; row 5 (control does not move) by 39.6 MB. B3g row 3 (counts differ from N) excluded by 1200 exact queries; row 4 (N not below partition size, or control did not move) by N <= 10000 < 200000 and the 737 MB control.
5. **Observed vs. inferred.** Inferred, not frozen and not used for the row: the 46 MB excess at N=absent is a slow rise of the post-collection heap floor over a 375 s, 28 GB-allocation arm (promoted garbage awaiting a concurrent cycle), not a per-query live set that grows with N. Supporting reading from the post-hoc `diag_drift.py` [observed: `diag-drift.txt`]: the 20 s-window trough rises 0.0 -> 21.0 -> 40.5 MB over the arm; the maximum of the first 157 samples (the sample count of the N=10000 arm) is 14.8 MB, equal to the N=10000 arm's 15.0 MB. The inference depends on a statistic chosen after the reading.
6. **Deviations and gaps.** (a) Unit tier: one JVM for all N instead of a fresh JVM per N (amended in B2a). (b) Cluster heap is a sampled proxy (100 ms, `HeapMemoryUsage.used` with a 20 MB young generation), not exact per-query retained heap; the N=1 and N=100 arms last under 0.5 s and have 3-5 samples. (c) The peak statistic does not remove the drift of a long arm, which is what the shortfall rests on; run 2 would repeat it (the two sweeps agree to 1 MB). (d) JMX heap sampling from the node's own JVM adds a small constant to every arm.
7. **Core question.** Unit tier: the limit stops the read after N groups (N+1 rows pulled), the returned count is exactly N, and neither retained heap (0.08 % spread) nor anything else beyond read work and result size depends on N; a materializing consumer shows the harness can see a cap on retained size [observed]. Cluster tier: result counts follow N exactly, disk is flat, and the page-size control moves the peak by 737 MB, but the frozen peak-heap rule is missed at N=absent by 16 MB (46 vs 30), so the cluster tier does not settle the question under the frozen rules. The exploratory arms show that at P=300000 the peak follows the page content (8 MB at N=1, 23 MB at N=10000, 792 MB at N=absent): the limit shapes a large page, but the case's own page size of 1000 already caps a page far below that.

**Conclusion (one line):** unit tier B2g row 1 — confirmed; cluster tier — Not confirmed (no matching row).

## 5. Self-check of run 1 — AI

### 5.1 Check of run 1's conclusion

`harness/.../selfcheck.py` re-parses `ant.log`, `markers.txt`, `arms.txt`, `samples.csv`, `vmflags.txt` and `system.log.segment` with its own windowing (output `run1/selfcheck.txt`). It first failed on two checker defects (a rep count that forgot the first-trigger rep at N=10; a pattern that matched the JVM-arguments line), both fixed before the file here was produced; its remaining FAIL is the 30 MB rule at N=absent, the same finding as the analyzer.

| Part | Holds? | Note (file re-read) |
|---|---|---|
| 1. Validity | yes | `markers.txt`: 1200 queries, all rows exact; `vmflags.txt`: heap 1073741824, G1, MaxNewSize 20971520; `unit/stage4-lines.txt` control 39.6 MB |
| 2. Readings | yes | `cluster-summary.txt`, `samples.csv` windows re-computed by the selfcheck: 54.9/54.0 vs 8.4 MB |
| 3. Matched row | yes | Both tiers' rules re-applied: unit row 1; cluster no row (forward sweep not strictly monotone, excess 46 MB > 30 MB) |
| 4. Excluded rows | yes | counts, spread, control values re-read |
| 5. Observed vs. inferred | yes | the drift explanation is labelled inferred and post-hoc, and is not used for the row |
| 6. Deviations and gaps | yes | listed above |
| 7. Core question | yes | the steps follow B1; the cluster tier is reported as not settled rather than tuned |

### 5.2 Run 2?

**No** (2026-10-27). A repeat under the frozen rules would reproduce the same reading (forward and reverse sweeps agree to 1 MB at N=absent). A different peak statistic (for example the excursion above the local trough) would be a new design after a reading, which the protocol does not allow for this tier; it is left as a recommendation for stage 3 / the user (section 8).

## 6. Run 2

Not done.

## 7. Comparison

Not applicable.

## 8. Verdict — AI

**Stage-3 estimate:** negative. **Outcome class:** undetermined (unit: does not cap; cluster: not settled).

**Claim tested:** heap and disk use of a node do not follow `groupPerPartitionLimit`: changing `PER PARTITION LIMIT` over a wide range changes the number of returned groups exactly, but peak read-path heap (with paging fixed) stays within noise unless the limit cuts the partition's read short, and it never behaves as a bound on node memory or disk.

| Tier | Verdict (B2g / B3g row) | Effect on the constraint | Basis | Date |
|---|---|---|---|---|
| Unit | **Confirmed** — row 1 (groups = min(N,R), retained heap flat, allocation scales with rows pulled, control moves) | does not cap | run 1 + self-check | 2026-10-27 |
| Cluster | **Not confirmed (no matching row)** — counts exact, disk flat, control moves, but peak heap at N=absent is 46 MB above N=1 (rule: 30 MB) and the forward sweep is not strictly monotone | undetermined | run 1 + self-check | 2026-10-27 |

**Positive control:** unit: cloning and keeping every returned row raised retained heap from 1.8 kB (N=1) to 39.6 MB (N=100000) against 77 kB noise. Cluster: raising the page size from 1000 to 300000 raised the peak from 54.9 to 792.2 MB (spread 8.4 MB).

**Outcome-class reason:** the unit tier supports a true negative; the cluster tier could not settle it under its frozen rule, so the class is undetermined. The post-hoc diagnostic (floor drift over a long arm, first 157 samples 14.8 MB) points to a true negative, but a stage-3 / user decision is needed to adopt a drift-corrected statistic and re-run.

**Open points the user may overrule:** (1) accept the cluster tier as "Confirmed — does not cap" on the strength of `diag-drift.txt`; (2) the rule thresholds (30 MB) were mine, set at the audit for "tens of MB".

**Upstream / documentation candidates:** none for a bug. Documentation: `PER PARTITION LIMIT` on a GROUP BY select bounds result size per page only when it is below the page size; nothing in the CQL docs claims otherwise.

**Leftovers on pc07:** no process; `/dev/shm/s4-b11-g73` removed; trees `~/s4-b11-g73`, `~/s4-b11-g73-n` (with the copied test class), driver `~/s4-b11-g73-drv`, logs `~/s4-b11-g73-logs/` kept.

**Feedback filed:** the case file's section D updated (uncommitted); amendments in A3, B2a, B3b, B3c, B3d, B3f, B3h (2026-10-27).
