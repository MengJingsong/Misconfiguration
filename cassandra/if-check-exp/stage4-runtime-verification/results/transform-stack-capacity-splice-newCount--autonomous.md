# transform-stack-capacity-splice-newCount--autonomous — stage-4 results  <!-- file: results/transform-stack-capacity-splice-newCount--autonomous.md -->

> **Case:** [`transform-stack-capacity-splice-newCount--autonomous`](../../stage3-ai-deep-read/cases/transform-stack-capacity-splice-newCount--autonomous.md)
>
> **Status:** verdict filed (2026-10-25) — run 1 done at both tiers, self-checked, no run 2
>
> **Outcome class:** **true negative** (estimate `negative`, effect `does not cap`) — [definition](../README.md#outcome-class)
>
> **Agent:** autonomous. "§9a" means B2f/B2g (unit, as amended B2i) and B3f/B3g (cluster, as amended B3i); "§9b-§9e" means B2a-B2e / B3a-B3e; feedback is section D.

## 1. Before run 1 — design audit and freeze

| Field | Content |
|---|---|
| **Case-file version** | Base repository commit `25b4a70`; the case file is untracked in the working tree. **sha256 after the audit's amendments (B2i and B3i, dated 2026-10-25): `e5b12f7415ff7d3f25b50f90134770f01cc4a25096f2279757894cb48ccbf121`**, written to `~/s4-st/logs/freeze.sha` and to this file at 2026-10-25 13:55 EDT, before the harness existed and before any reading. |
| **Harness** | `harness/transform-stack-capacity-splice-newCount--autonomous/`: `StackSpliceCapacityTest.java`, `rules.btm`, `unit-run.sh`, `analyze_unit.py`, `cluster-run.py`, `analyze_cluster.py`, `selfcheck.py`, `README.md`; written after the freeze; not committed. md5s at the start of the unit run, the start of the cluster run and the end: `results/transform-stack-capacity-splice-newCount--autonomous/run1/harness.md5.{unit-start,cluster-start,final}` (identical for the seven files that existed at the unit start; `selfcheck.py` was written during the cluster run and appears only in `final`; none of the run scripts changed between runs). The case file was edited once more after the first freeze hash was written (item U5 `ctl_cap` stack length 6 corrected to 5, before any reading and before the harness); the hash above is the second. Section D was filled afterwards; the sha256 of the file with D filled is `801ac6fa185da30d0db27602fcf5d3d5158df04995f0e1821ae661a093af2f19`. |
| **Tiers and values** | Unit (B2/B2i): K/M/P/Q/R grid, memory and positive-control arms. Cluster (B3/B3i): 2-node loopback ring, short-read arm at L in {10, 2000, 40000}, key-cache positive control. |
| **Audit bottom line** | **Ready after amendments** — 2026-10-25 |

### 1.1 Design audit

Estimate: **negative**. Audited against `cassandra/cassandra-5.0.9/` (clean). Re-read: `Stack.java` (all), `BaseIterator.java:40-180`, `BasePartitions.java`, `Transformation.java:130-206`, `MoreRows/MorePartitions.java`, `ShortReadProtection.java:55-100`, `ShortReadPartitionsProtection.java:84-200`, `DataResolver.java:190-215`, `ReadCommand.java:487-495`, `RepairedDataInfo.java:262-285`, `RTBoundCloser.java`, `ReadResponse.java:248`, `UnfilteredPartitionIterators.java:100-125,350`.

| Group | Check | Rating | Note |
|---|---|---|---|
| A | constrained quantity is memory or disk bytes | Partly | There is no constraint: `keep.length` is an array capacity (A1). The resource is heap pointer arrays, measurable in bytes; stated as a "no-cap-exists" case. |
| A | knob varied, >= 3 values, or other approach with reason | Partly → Met | Not settable (A1); the inputs that set the array size (K, M, P, Q, R) are varied instead (B2b); cluster varies the read size L (B3b, B3i.2). |
| A | real resource measured, not only the counter | Partly → Met | B2d used identity/length (counter) only; B2i.5 adds retained heap vs a same-size `Object[]`; cluster reads live bytes of the array classes and the heap total from `GC.class_histogram`. |
| A | usage driven to the limit and past it | Partly | There is no limit; the grow branch is driven in the unit tier (identity change, up to 100000 entries). On a node the grow branch is probably unreachable (B3i.1); said openly, not forced. |
| A | positive control for a negative estimate | Partly → Met | B2h gave the control; B2i.6 U5 puts numbers and an OOM-bound cap on it; B3i.4 replaces the `key_cache_size` restart with `setcachecapacity` at runtime. |
| B | steps establish something | Met | B2e/B3e. |
| B | prediction in numbers | Not met → Met | B2f contained an arithmetic error (`newCount = P + M`, not `P + K`; the filed 11 should be 6) and was relational; B2i.1/6, B3i.5 give closed forms and thresholds. |
| B | every outcome has a row | Partly → Met | B2i.7, B3i.6 add rows (closed-form mismatch, control not moving, instrument disagreement, no divergence, G above 0). |
| B | confirmation needs knob-follows and direct branch evidence | Met | For this claim "no ceiling": identity change at line 95 plus Byteman counts at lines 94/95 (B2i.4, B3i.3). |
| B | alternatives and controls | Met | B2h/B3h plus B2i.5-6. |
| C | a human can follow it | Met | A1-A3, B1. |
| C | an AI can run it without re-deriving | Partly → Met | Setup, classpath, test class name, rules and ports supplied (B2i.3, B3i.2-3). |
| C | exact values and commands | Partly → Met | Grid, N values, rows, ports, fetch size, sampling interval supplied. |
| D | prerequisites exist | Met | JDK 11, Ant, `ant build-test` tree (built in 1 min 7 s), Byteman jar from the build, bundled Python driver. |
| D | workload arithmetic reaches the limit | Met (unit); n/a (cluster) | Unit: up to 100000-entry stacks and 160000 x 1 KiB rows in a 512 MiB heap. Cluster: 80 MiB of data per node; the grow branch cannot be reached (B3i.1). |
| D | citations spot-checked | Met | Line numbers in A3 hold (`Stack.java:60-101`, `BaseIterator.java:136-171`); B2c's `newCount` arithmetic was wrong. |

| # | Recommendation | Applied? | Why |
|---|---|---|---|
| 1 | Correct `newCount = P + M`; closed forms | Applied, B2i.1/6, 2026-10-25 | The filed example (11) contradicts the code. |
| 2 | Run by `java` on the test classpath, not `ant testsome` | Applied, B2i.3 | testsome's fork heap is fixed at 1 GiB. |
| 3 | Add Byteman counts at lines 94/95 as cross-check | Applied, B2i.4, B3i.3 | Direct evidence the check ran. |
| 4 | Decide the cluster arm: run a 2-node short-read arm that records reach and flatness, with no knob and no claim to reach the limit | Applied, B3i | The filed fallback was hedged ("so short reads can occur"). |
| 5 | Fix B2h `-Xmx512m` OOM wording to the direct-java run | Applied, B2i.5-6 | |

**Agreement criteria** — not applicable (run 2 not planned).

## 2. Environment

| Field | Run 1 |
|---|---|
| Date | 2026-10-25 (unit 14:04 EDT; cluster 14:04 to 14:12 EDT) |
| Node | `pc07` (`node0`), 40 cores, 251 GiB; two other agents share it (tags nc, bt) |
| OS and kernel | Ubuntu 22.04, `5.15.0-187-generic` |
| JDK / Ant | OpenJDK 11.0.32.1 / Apache Ant 1.10.12 |
| Local source copy | `~/s4-st/cassandra` by `copy-source.sh` from `cassandra/cassandra-5.0.9/` at repository commit `25b4a70`; `ant build-test` 1 min 7 s. The node run used `~/s4-st/nodetree`, a `cp -a` of that built tree (never the tree `ant` ran in). |
| Case-file commit / harness commit | none (untracked); sha256 in section 1 / not committed |
| Storage | local disk (`/`, 44 GB free): `~/s4-st/work/node1`, `node2`; 80,000 x 1 KiB rows per node, 1 GiB heap each (`-Xms1G -Xmx1G`, G1) |
| Full logs (outside the repo) | `~/s4-st/run1/{unit-plain,unit-bm,cluster}/`, `~/s4-st/logs/` (node `system.log`s are 6 MB; excerpts under `run1/`) |

## 3. Runbook defects

| # | Run | Step | Problem | Fix | Decision | Case-file commit |
|---|---|---|---|---|---|---|
| 1 | audit | B2c/B2f | `newCount` arithmetic of the filed example is wrong (P + K claimed; code gives P + M) | B2i.1, B2i.6 | applied 2026-10-25 before any reading | untracked |
| 2 | audit | B2i.6 U5 | `ctl_cap` stack length stated as 6, but the source is never exhausted so no refill runs (5) | corrected in place, 2026-10-25, before the harness and before any reading; freeze hash re-written | applied | untracked |
| 3 | harness | `StackSpliceCapacityTest.control` | read `MemoryMXBean` inside the OOM handler; the call itself threw `OutOfMemoryError` | use `Runtime.totalMemory()-freeMemory()` there (instrument bug, found in a shakedown) | fixed in the harness | n/a |

No runbook defect occurred during run 1.

## 4. Run 1

**Scope:** unit tier (two JVMs: plain, and with the Byteman rules for the cross-check) and cluster tier (two loopback nodes). **Command logs:** `run1/unit/session-plain.log`, `session-bm.log`, `run1/cluster/session.log`.

### 4.1 Readings

**Unit tier** (all in `run1/analyze_unit.out`: 58 PASS, 0 FAIL; raw rows in `run1/unit/raw-plain.csv`)

| Test or assertion | Result | Evidence |
|---|---|---|
| U1 build-up, 13 values of K (0 to 100000), `stack.length` | equals cap(K) exactly (5, 10, 20, 40, 80, 1280, 163840 for K = 1 ... 100000) | `raw-plain.csv` rows `buildup` |
| U2 refill grid: 9 rows x R in {1, 10, 1000} = 27 runs | `stack.length` equals the predicted value in all 27: (5,0,6) 5 to 6, (3,0,1) stays 5, (5,0,5) stays 5, (0,5,6) 5 to 11, (40,0,41) 40 to 41, (1000,0,100000) 1280 to exactly 100000; identity changes 1 or 0 as predicted; `moreContents.length` 1 + Q; mc changes Q | `analyze_unit.out`, `raw-plain.csv` |
| U3 R-independence | `stack.length` identical at R = 1, 10, 1000 for every row; reallocations 0 or 1 regardless of R (9099 refills in total) | `analyze_unit.out` |
| U4 heap, K = 1,000,000 (cap 1,310,720) | iterator delta 6,295,608 / 6,291,536 / 6,291,536 B vs `Object[]` delta 6,291,480 B: ratio 1.001, 1.000, 1.000 | `raw-plain.csv` `heapstack` rows |
| U5 control N = 20000 / 80000 / 160000 | heap delta 24.4 / 95.8 / 191.8 MB = 1.19 / 1.17 / 1.17 x N KiB; `stack.length` 6 each | `raw-plain.csv` `control` rows |
| U5 `ctl_cap` (`-Xmx512m`) | `OutOfMemoryError` after 435,532 rows (425 MiB of 1 KiB values; used at OOM 521.6 MB); `stack.length` 5 | same |
| Byteman cross-check (separate JVM) | S lines at line 94 = 18,198 = 2 x 9,099 refills; G lines at line 95 = 21 = 15 stack + 6 moreContents identity changes; raw rows identical to the plain JVM's | `run1/unit/trace-counts.txt`, `raw-byteman.csv`, `selfcheck.out` |

**Cluster tier** (`run1/analyze_cluster.out`: 12 PASS, 0 FAIL)

| Capacity value | Run | Observable | Reading | Evidence |
|---|---|---|---|---|
| L = 10 | scan loop 40 s, 8,404 scans of 10 rows | node-1 S (line 94) / SRP rule / log lines "for short read protection" / G | 50,424 / 25,212 / 25,212 / 0 | `cluster/phases.json`, `session.log` |
| L = 2000 | 235 scans | same | 4,230 / 2,115 / 2,115 / 0 | same |
| L = 40000 | 14 scans of 40,000 rows (mean 3.0 s) | same | 448 / 224 / 224 / 0 | same |
| all L | Byteman | largest `newCount` of any splice | 2 on node 1 (8 on node 2, at start-up) | `node1-trace-linecounts.txt`, `analyze_cluster.out` |
| L = 10 / 2000 / 40000 | `GC.class_histogram` every ~1 s on both nodes (54 / 56 / 56 samples) | max bytes of `Transformation[]` + `Stack$MoreContentsHolder[]` + `Stack$MoreContentsHolder` | 592 / 680 / 592 B (max 0.001% of live total) | `cluster/samples-L*.csv` |
| L = 10 / 2000 / 40000 | same samples, node 1 | max live heap total | 72.6 / 78.6 / 178.2 MiB (L40000 minus L10 = 105.6 MiB) | same |
| key cache 0 vs 64 MiB (control) | 2 passes x 80,000 point reads at CL ALL | `KeyCacheKey` live bytes max / `nodetool info` entries | 0 B and 0 entries vs 2,560,064 B and 80,002 entries (6.1 MiB) | `samples-keycache_*.csv`, `info-keycache_*.txt` |

### 4.2 Conclusion and logic

1. **Validity.** The check was reached: on the nodes `Stack.splice` ran 55,102 times, 27,551 of them as the two calls per short-read refill, tied to 27,551 log lines "Requesting ... extra rows ... for short read protection" **[observed: `cluster/node1-trace-linecounts.txt`, `error-counts.txt`, `analyze_cluster.out`]**. Short reads happened because the nodes were diverged (node 2 kept rows node 1 had deleted, `read_repair = 'NONE'`) **[observed: the same log lines; node 2 shows none because the coordinator was node 1]**. The unit grow branch fired where predicted (21 times) **[observed: `unit/trace-counts.txt`]**. Fixed settings: heap 1 GiB per node and `-Xmx512m` for the unit JVM **[observed: `cluster/evidence-node1/cmdline.txt`, `unit/session-plain.log`]**. Hints off and `read_repair = NONE` **[observed: `cluster/evidence-node1/yaml-keys.txt`; table option set by the driver script]**. Valid.
2. **Readings.** Nothing unusual. The array bytes in the histogram are tiny and nearly constant (592 to 680 B): the histogram is taken after a full GC every second, so it can only catch the arrays of iterators alive at that instant. That is a weak sampler for transient arrays; the Byteman `newCount` figures (largest 2 on the coordinator) are the stronger evidence on the nodes. **[inferred: arrays belong to per-partition iterators that are closed within microseconds]**
3. **Matched row.** Unit: B2g row 1 as amended by B2i.7(a): `stack.length` follows the closed forms exactly (grows only when `newCount > capacity`, to exactly `newCount`, up to 100000), it is R-independent, no fixed ceiling, heap tracks the pointer array only (ratio 1.0), and the positive control (heap ~ N, and a hard 512 MiB cap binding at 425 MiB of rows) moves while `stack.length` stays 5 or 6 **[observed: `analyze_unit.out`]**. Cluster: B3g row (a): C1 to C5 hold and G = 0 **[observed: `analyze_cluster.out`]**.
4. **Excluded rows.** "`stack.length` grows with R" is excluded: 1000 refills give the same length as 1 **[observed: U3]**. "Fixed maximum independent of K, P": 100000 reached exactly **[observed: U2]**. "Heap tracks stack length beyond the array": ratio 1.000 to 1.001 **[observed: U4]**. Cluster "arrays above 1 MiB or growing with L": maximum 680 B **[observed: C3]**. Control did not move: it moved (0 to 2.56 MB, 0 to 80,002 entries) **[observed: C5]**. No divergence: 27,551 short-read log lines **[observed]**. G above 0: none **[observed]**.
5. **Observed vs inferred.** Inferred: (a) the sampler's coverage of transient arrays (item 2); (b) that on a node the grow branch cannot fire because short-read replacement iterators are deserialised plain iterators (audit B3i.1, source reading) **[inferred: supported by G = 0 in 27,551 refills, not proven for every path, e.g. a repaired-data or paged-read refill that this workload did not drive]**; (c) the unit tier's `Transformation.apply` pipeline stands for the read path's use of `Stack` **[inferred: same classes, but not the production pipeline]**.
6. **Deviations and gaps.** The cluster tier cannot drive the check to a limit (there is none) and never reached the grow branch; it shows the check is reached and its disallow-equivalent (growth) did not occur, with negligible array bytes. The positive control on the cluster is the key cache (a different heap consumer with a binding cap), not a Stack-specific one. RSS per node (1.75 to 1.81 GB) is dominated by the pre-touched 1 GiB heap and did not move with L; it is not used. Run 2 not done.
7. **Core question.** There is no constraint on the stack size: `keep.length` is an array capacity, and line 94 only decides when to reallocate. Usage (array size) follows the number of stacked transformations exactly and is independent of the number of refills; the real memory of the arrays equals their pointer size and is negligible on a node, while heap follows data volume (hold 160000 rows, +192 MB; scan 40000 rows, +105 MiB) and a cap that binds elsewhere (`-Xmx512m`, key cache) moves it independently **[observed: items 3 and 4]**. The constraint does not cap usage, and there is nothing for it to cap.

**Conclusion (one line):** unit B2g row 1 and cluster B3g row (a) (as amended) — Confirmed: the claim (no cap, usage does not follow) held.

## 5. Self-check of run 1 — AI

Independent script `harness/.../selfcheck.py` (re-parses the raw files; the unit expectations come from a separate re-implementation of `Stack.add`/`splice`, not from the analyser's closed forms): 14 HOLD, 0 FAIL (`run1/selfcheck.out`). I also re-read `Stack.java:60-101` and `BaseIterator.java:136-171` against the interpretation of S, G and the identity counts.

| Part | Holds? | Note |
|---|---|---|
| 1. Validity | yes | whole-run Byteman trace re-counted: node 1 S = 55,102, SRP rule = 27,551 = log lines, G = 0; unit S = 2 x refills, G = identity changes |
| 2. Readings | yes | every scan returned min(L, 40000) rows; at least 45 samples inside each scan window; sampler weakness noted |
| 3. Matched row | yes | 47 unit rows equal the re-implementation; U4, U5 re-derived from raw rows |
| 4. Excluded rows | yes | nothing in the raw files supports any other row |
| 5. Observed vs inferred | yes | inferred items 5(a) to (c) stated; (b) rests on G = 0 in 27,551 refills |
| 6. Deviations and gaps | yes | listed |
| 7. Core question | yes | steps follow the audited logic (B2i, B3i) |

### 5.2 Run 2?

**No** (2026-10-25). The verdict is exact at the unit tier (closed forms equal to the integer, reproduced in two JVMs, one with an independent counter) and consistent at the cluster tier; it does not refute or confirm a bypass. The inferred statement most open to challenge (5(b)) would need a different workload, not a repeat.

## 6. Run 2 — fresh AI session (optional)

Not done (section 5.2). Sections 6 and 7 omitted.

## 8. Verdict — AI

**Stage-3 estimate:** negative. **Outcome class:** **true negative** (negative, does not cap).

**Claim tested** (B1): the size of the `Stack` arrays and the number of `splice` reallocations at line 94 are determined only by the number of stacked transformations and refills and are not capped by, nor scale with, any configuration limit; process memory under reads does not follow `Stack` capacity (it follows data volume). "Confirmed" means this claim held.

| Tier | Verdict (B2g / B3g row) | Effect on the constraint | Basis | Date |
|---|---|---|---|---|
| Unit | Confirmed (B2g row 1 with B2i.7(a)) | does not cap | run 1 + self-check | 2026-10-25 |
| Cluster | Confirmed (B3g row (a) with B3i.6(a)) | does not cap | run 1 + self-check | 2026-10-25 |

**Positive control:** unit: holding N = 20000 / 80000 / 160000 rows through the same pipeline moved the retained heap 24.4 / 95.8 / 191.8 MB while `stack.length` stayed 6, and holding rows until a 512 MiB heap cap bound gave `OutOfMemoryError` at 435,532 rows with `stack.length` 5. Cluster: `setcachecapacity 0` then `64 0 0` moved `KeyCacheKey` live bytes from 0 to 2,560,064 B (entries 0 to 80,002) under the same sampler. Both moved, so "flat" is not a workload that could not show an effect.

**Feedback filed:** the case file's section D updated (not committed; case file untracked), and the amendments B2i and B3i (dated 2026-10-25) already in B2/B3. `_INDEX.md` and `writeup-set-A.csv` left to the caller (rules of this batch).

**Leftovers:** none running (`ps` shows no `CassandraDaemon` and no listener on 7054/9054/7154/7155 after the run). On disk, outside the repo: `~/s4-st/` (source trees `cassandra` and `nodetree`, `work/node1`, `work/node2` with the run's data, `run1/` full logs, `driver/`, `logs/`).

## Time spent

| Step | Start (UTC) | End (UTC) | Minutes | Remarks |
|---|---|---|---|---|
| audit | 17:50:59 | 17:56:14 | 5.3 | reading protocol and source; `copy-source.sh` and `ant build-test` (1 min 7 s) ran in the background meanwhile; one freeze-hash rewrite |
| harness | 17:56:15 | 18:03:49 | 7.6 | unit test, rules, run scripts, analysers; unit shakedown (and one fix), cluster shakedown (~2 min wait for the 2-node start) |
| unit-run | 18:03:56 | 18:04:17 | 0.4 | two JVMs, about 4 s each plus compile |
| cluster-run | 18:04:17 | 18:12:29 | 8.2 | node starts 37 s each, load 17 s, three scan arms of ~50 s, two control arms of ~80 s; `selfcheck.py` was written during this wait |
| selfcheck | 18:12:30 | 18:12:37 | 0.1 | script already written; run only |
| report | 18:12:37 | 18:14:08 | 1.5 | results file, excerpts, case-file section D |
