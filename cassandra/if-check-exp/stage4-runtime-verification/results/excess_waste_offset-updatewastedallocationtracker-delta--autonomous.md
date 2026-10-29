# excess_waste_offset-updatewastedallocationtracker-delta--autonomous — stage-4 results  <!-- file: results/excess_waste_offset-updatewastedallocationtracker-delta--autonomous.md -->

> **Case:** [`excess_waste_offset-updatewastedallocationtracker-delta--autonomous`](../../stage3-ai-deep-read/cases/excess_waste_offset-updatewastedallocationtracker-delta--autonomous.md)
>
> **Status:** **Self-checked 2026-10-28 -- unit Confirmed (does not cap), cluster Confirmed (does not cap); no run 2**
>
> **Outcome class:** true negative -- stage-3 estimate `negative` against the stage-4 effect `does not cap` ([definition](../README.md#outcome-class))
>
> **Agent:** autonomous (B2 = unit tier, B3 = cluster tier, feedback = section D).

## 1. Before run 1 — design audit and freeze

| Field | Content |
|---|---|
| **Case-file version** | sha256 of the whole file with section D still `none yet`, after the audit amendments B0 (S1 to S6 and the case text, dated 2026-10-28, inserted before B2): **unit tier** run on `7187f4abcc9354c166810c486899803445a38075420830f05b4adb315ce1259a`; **cluster tier** run on `730546f214e43291d93a0c464dc026a2301cbd2bd216b2fcf1b43684da886753` (differs only by S6: heap 4G raised to 8G on 2026-10-28 before the first cluster cell, after the unit tier and a discarded shakedown showed a thrashing JVM; no prediction or row changed). Repository HEAD of this session `b68711e`; case file, harness and results uncommitted. Frozen before the first reading of either tier. |
| **Harness** | [`harness/excess_waste_offset-updatewastedallocationtracker-delta--autonomous/`](../harness/excess_waste_offset-updatewastedallocationtracker-delta--autonomous/README.md), uncommitted: `mkvariant.sh`, `S4Waste.java`, `WasteProbe.java`, `unit-run.sh`, `unit-all.sh` (B2); `LoadGen.java`, `Jmx.java`, `cluster-run.py`, `cells.py`, `chain.sh` (B3); `selfcheck.py`. One code base shared by the four EXCESS_WASTE_* case files (identical copies; the cells each file runs are its own). md5s in `excess_waste_offset-updatewastedallocationtracker-delta--autonomous/run1/harness.md5`. **Instrument checks (not readings, discarded):** javac of the probe and of the variants; every unit mode run once on `v1m`/`v10m` (an out-of-memory in an oversized contention config was removed from the probe); a 40 s shakedown of `cluster-run.py` (WB, `v10m`) that showed the constant read-back, the counters, the TRACE line and the samplers work. The author saw the output (see B0). |
| **Tiers and values** | B2 builds v10m / v20m (direct, burst with gaps, refill, memo, control); B3 WF hot and WG per-thread partitions x v10m / v1g / v1024, controls 128 / 1024 MiB. Both tiers kept. |
| **Audit bottom line** | **Ready after amendments** — 2026-10-28 |

### 1.1 Design audit

| Group | Check | Rating | Note (section checked) |
|---|---|---|---|
| A. Core question | constrained quantity is memory or disk bytes | Partly | A2: the compared quantity is the `heapSize` bytes of a failed merge attempt (a short-lived on-heap garbage counter), not a memory or disk cap; the design therefore measures the real resource around it (pool ownership, heap, disk) and asks whether any of them follows the constant (B1). |
| A. Core question | knob varied, ≥ 3 values incl. default — or another approach, with the reason | Met | B2b/B3b: a `static final long` cannot be set at run time; three or more recompiled builds including the shipped literal, plus the operand swept at the unit tier (A1, B2b). |
| A. Core question | real resource measured, not only the counter (gap named) | Partly | B3d names the pool gauge, GC log and disk; the gap is that the pool gauge is ownership and not heap (S4 names the alias); the S4 counters were added to see the regime, since `wasteTracker` is private and unmetered. |
| A. Core question | usage driven to the limit and past it | Partly | Unit: operand crosses `C` by construction. Cluster: reaching the waste rate was not demonstrable from source; S6 sets the load and `flips`/TRACE are the evidence the window was passed (and not passed for `1L << 40`). |
| B. Logic | each step says what it establishes | Met | B2e/B3e numbered, B1 states what refutes the claim. |
| B. Logic | prediction stated in numbers or a clear relation | Partly | boundary arithmetic and burst counts are exact; the accounting predictions were wrong by S2 and the allocation/BLOCKED predictions by S1: replaced in B0. |
| B. Logic | every plausible outcome has a conclusions row with its evidence | Partly | no row for "accounted size follows contention but not the constant" (S2) and no numeric rule for "flat" or "follows": added (S5). |
| B. Logic | confirmation needs ceiling-follows-knob and direct disallow evidence | Partly | for a negative estimate the equivalents are flatness across builds plus the regime evidence (`flips`, TRACE) plus the moving control; S1 removes the BLOCKED-thread evidence, S4/S5 replace it. |
| B. Logic | alternative explanations and their controls | Partly | contention versus constant was not separated; the WG/W1/WC cells (no contention) and the forced-failure series separate them (B0). |
| C. Specific | a human can follow it from the intro and B1/B2g/B3g | Met | A1 to A4 and B1. |
| C. Specific | an AI can run B2a-B2e / B3a-B3e without re-deriving the code path | Partly | cluster tools, load shape and node settings were not exact: S6 and the case-specific text. |
| C. Specific | knob, values, workload, commands, observables, sampling, stop conditions exact | Partly | durations (10 min), "cassandra-stress profile" and the unit contention size were not exact: S6, case text. |
| D. Runnable | harness and environment prerequisites exist or are listed | Partly | written in step 1 (this session): see Harness row. |
| D. Runnable | workload arithmetic reaches the limit (data, time, disk, memory) | Partly | the waste rate was an estimate; node 4 GB heap, local disk 54 GB free, payload quota and a free-disk stop in S6; a 9.6 MB request (WE, case 3) is the one cell that may not fit. |
| D. Runnable | load-bearing citations spot-checked against the pinned source | Partly | re-read in `cassandra/cassandra-5.0.9`: `AtomicBTreePartition.java:56-80, 120-186, 231-296`, `BTreePartitionUpdater.java:126-183`, `SlabAllocator.java:89`, `NativeAllocator.java:138-141`, `SkipListMemtable.java:261-266`, `BufferCell.java:156-158`, `TableMetrics.java:493`, `DatabaseDescriptor.java:583-590`, `conf/cassandra.yaml:825`; two statements of the trace are wrong (S1: the monitor is per `Updater`; S2: value bytes of failed attempts are charged); S3 lists line corrections. |

| # | Recommendation | Applied? | Why |
|---|---|---|---|
| R1 | S1: the `synchronized` monitor is the per-call `Updater`: drop BLOCKED-thread and allocation-rate evidence | Applied 2026-10-28 (B0) | `AtomicBTreePartition.java:120-123, 155-162` |
| R2 | S2: value bytes of failed attempts are charged to the pool: replace the `owns()` equality predictions | Applied 2026-10-28 (B0) | `SlabAllocator.java:89`, `NativeAllocator.java:138-141`, `BufferCell.java:156-158` |
| R3 | S3: citation corrections | Applied | line numbers |
| R4 | S4: the counters, the variants, how the constant is read back | Applied | the private tracker has no metric |
| R5 | S5: numeric rules for flat, follows, valid cell and moving control | Applied | none existed |
| R6 | the large-ref pool control replaced by the pool-limit control mode; unit "allocator plateau" row cannot be matched at unit tier (cluster carries it) | Applied 2026-10-28 (B0) | runnable as written otherwise not |
| R7 | For stage 3: the trace for hard-coded constants of this class should check what an allocator-cloned value costs the pool and whether a `synchronized` in an inner per-call object excludes anything | left for stage 3 | S1, S2 |

## 2. Environment

| Field | Run 1 |
|---|---|
| Date | 2026-10-28: unit tier node clock UTC 14:17-14:28, cluster tier 14:28-16:40 (39 cells of the four files, one chain) |
| Node (CloudLab name and type) | `pc39` = `node1.jason92-321705.misconfiguration-pg0.cloudlab.umass.edu` (40 cores, 251 GiB) |
| OS and kernel | Ubuntu 22.04.2 LTS, `5.15.0-198-generic` |
| JDK / Ant | openjdk 11.0.32.1 (2026-08-18) / Apache Ant 1.10.12 |
| Local source copy | `~/s4-ew` from `cassandra/cassandra-5.0.9/` at repository commit `b68711e` (`copy-source.sh`), `ant build-test` BUILD SUCCESSFUL |
| Case-file / harness commit | uncommitted; hashes in section 1 |
| Storage for node data | `~/s4-ew-node` and `~/stage4-tmp/ew` on local `/dev/sda3`, removed after each cell; nothing under `/proj` |
| Full logs (outside the repo) | `pc39:~/stage4-logs/ew/` (`unit-c4/`, `cluster/<tag>/`) |

## 3. Runbook defects

| # | Run | Step | Problem | Fix | Decision (date) |
|---|---|---|---|---|---|
| D1 | cluster shakedown | S6 heap | at `-Xmx4G` the discarded 40 s shakedown showed 26 full collections in 40 s | heap 8 GB in every cell; S6 amended, case-file hash changed (section 1); claim, predictions and rows unchanged | 2026-10-28, before the first cluster cell |

## 4. Run 1

**Scope:** every B2 value of B0 (unit) and every B3 cell of B0 (cluster). **Command log / raw readings:** `excess_waste_offset-updatewastedallocationtracker-delta--autonomous/run1/` (`unit/*.out` and `unit/analysis.txt`, `cluster-c4.txt`, `cluster/<cell>/{summary.txt,s4waste-head-tail.txt,flush-lines-*.txt,loadgen.txt}`, `selfcheck-c4.txt`, `harness.md5`, `patch-v10m.diff`, `patch-v1.diff`). Full logs: `pc39:~/stage4-logs/ew/` (`unit-c4/`, `cluster/<cell>/`, `chain-all.log`).

### 4.1 Readings

**Unit tier** (`run1/unit/`; `analysis.txt` ends `all checks PASS`; 0 FAIL)

| Test or assertion | Result | Evidence |
|---|---|---|
| `direct`, `burst` (gaps 0, 1, 10, 100 ms), builds `v10m`, `v20m`, pristine | boundary at `C-1023` (20 MiB build: `20971520-1023`); back-to-back calls equal `ceil((OFFSET + elapsed ticks) / units)` within 2 (1024-byte: 10258 vs 10257; 1 MiB: 10; 100 KiB: 103); with gaps the budget refills (1 KiB reports never lock at any gap; 1 MiB reports lock after 11, 11 and 37 calls at 1, 10, 100 ms) | `unit/*-all.out`, `analysis.txt` |
| `refill` (`C-1024` twice) | 10 MiB window 1342 ms: second call true after 0 and 500 ms, false after 1500 ms; 20 MiB build (window 2684 ms): true after 1500 ms | `refill` lines |
| `memo` | 3,000,001 reports totalling 1.57 GB: heap used differs by -8.6 kB (`v10m`) and -62.6 kB (`v20m`); `useLock` true at the end | `memo` lines |
| `control` | as case 1 | `control` lines |

**Cluster tier** (`run1/cluster-c4.txt`; per flush: `Writing Memtable-t@...` and `Enqueuing flush of ks.t` lines of `debug.log`, first and last flush left out)

| Run | Observable | Reading | Evidence |
|---|---|---|---|
| WF hot (1 row, 4 KiB), `v10m` / `v1g` / `v1024` | ops per flush 17,095 / 17,168 / 17,374 (max/min 1.02); `Enqueuing` 171.2 MiB in all; `flips` 62 / 0 / 61; failed CAS 60.2-60.8 percent; allocation 33.6-36.8 GB; 4.06-4.15 GiB payload | `cluster/c4-WF-*/` |
| WG (64 partitions, one writer each) same three | ops per flush 40,947 / 40,940 / 40,947 (1.00); `fails` 0, `flips` 0, tracker never called; 35 flushes | `cluster/c4-WG-*/` |
| WF, `v10m`, pool 128 / 512 / 1024 MiB | `Enqueuing` 43.3 / 171.2 / 342.1 MiB (7.90); on-heap at `Writing` 45.9 / 180.3 / 359.3 MB | `c4-ctl128`, `c4-ctl1024` |

### 4.2 Conclusion and logic

1. **Validity.** Unit: every constant was reached in its own build by construction [observed: `direct` rows at `C-1023`]; the loaded constant is read back in each JVM [observed: `config C=... OFFSET=... loadedFrom=.../s4-ew-var/<variant>/` first line of every `.out`]. Cluster: every counted cell passed the S5 validity test (no errors, constant read back from `s4waste.csv`, at least 4 flushes) [observed: `selfcheck-c4.txt` `PASS valid cell`]; no CassandraDaemon left after any cell [observed: `chain-all.log` `left=0`; `ps` 0 after the chain].
2. **Readings.** Anything unusual: the sentinel does not stop failed CAS (S1) [observed: `lockedFails` is 94 percent of locked attempts in the cluster cells]; failed attempts' value bytes are charged to the pool (S2) [observed: unit `fail` excess 1.04 x payload, `cont` 2-5 x single-threaded]; the hot cells' memtable on-heap at `Writing` exceeds the pool limit [observed: `Writing` lines]; no BLOCKED thread in any dump [observed: `cluster-c4.txt` `BLOCKED 0`]. 
3. **Matched row.** Unit B2g row 1 (switch count matches the formula, the tracker is O(1) memory, nothing else changes after the switch) and row 3 (the pool limit, not the tracker, is what the cleaner follows) -- Confirmed. The 'allocator plateaus near 10 MiB' row is not exercised at this tier (B0). Cluster B3g row 1: retained size, flush size and disk flat across `v10m`/`v1g`/`v1024` (1.00-1.02); `flips` > 0 for `v10m` and `v1024`, 0 for `v1g`; WG (no contention) identical in all three; pool control 7.90 x -- Confirmed.
4. **Excluded rows.** *Usage follows the constant (Refuted)*: unit builds' contended `owns` within their repeat spread, cluster flat ratios 1.00-1.07 and no ordering by constant [observed: `selfcheck-c4.txt` NOTE lines]. *Limit never reached / control did not move (Not confirmed)*: the regime flag was reached in the small-constant cells and not in the huge-constant ones, as the constants imply; the pool control moved 3.9-8 x [observed]. Withdrawn rows (BLOCKED threads, lower allocation for a tiny constant) are not used (B0 S1).
5. **Observed vs. inferred.** Inferred: that failed CAS continue in the locked regime because the monitor is the per-call `Updater` (source reading S1; observed consequence: `lockedFails` > 0 and no BLOCKED thread); that the per-flush differences between hot and cold/single cells are due to failed attempts' charged value bytes (S2; observed in the unit `fail` series).
6. **Deviations and gaps.** (1) The numeric tolerances of `analyze_unit.py` (burst +-2 calls + 2 percent, S2 ratio band 0.9-1.5, stream rule) were set at analysis time after seeing the raw lines; two of them were widened once (an off-heap cell header makes the excess 1.32 x the value bytes, and a cap-limited stream must be judged against its window): recorded in the script. The S5 rules (1.3, 3 x, 10 percent) were frozen. (2) The cluster shakedown at 4 GB heap showed a thrashing JVM; the heap was raised to 8 GB before the first cell (case-file hash changed, see section 1; the unit tier had run on the first hash and does not depend on S6). Even at 8 GB the hot cells show 12-18 full collections per 120 s (case 2 WB) and 0-2 (others). (3) `analyze_cluster.py` raised an index error for cell `c2-cold128` (case 2); `selfcheck.py` parsed it and is used. (4) Values are one run per cell where the case file asks for one; spread is known only for the repeated cells. One run per cell for the cases that ask for one; spread known only for repeated cells. The unit probe forces contention with a nested write; the cluster tier uses the in-tree driver and not cassandra-stress. Not verified: real-workload behaviour with the shipped 2-4 GB heaps the case files name (8 GB used), other allocation types in the cluster tier, multi-node.
7. **Core question.** On WF the constants 1 KiB, 10 MiB, 1 GiB give the same rows per flush (17.1-17.4 k) and flush size; `v1024` and `v10m` flip at about 61 partitions, `v1g` never; with one writer per partition (WG) there is no failed CAS and the same 40.9 k rows per flush for all three; the pool moves flush size 7.90 x.

**Conclusion (one line):** Unit B2g row 1 (switch count matches the formula, the tracker is O(1) memory, nothing else changes after the switch) and row 3 (the pool limit, not the tracker, is what the cleaner follows) confirmed (does not cap); cluster confirmed (does not cap).

## 5. Self-check of run 1 -- AI

### 5.1 Check of run 1's conclusion

`selfcheck.py 4` re-parsed the raw logs with plain string operations (not the analysis regexes) and re-evaluated the S5 rules: `run1/selfcheck-c4.txt`. Raw files re-opened by hand: `cluster/<cell>/s4waste-head-tail.txt`, `flush-lines-first8.txt`, `loadgen.txt`, `unit/analysis.txt`.

| Part | Holds? | Note (file re-read) |
|---|---|---|
| 1. Validity | yes | `selfcheck-c4.txt` `PASS valid cell` for every counted cell |
| 2. Readings | yes | counters and flush lines agree between `cluster-c4.txt` and `selfcheck-c4.txt` |
| 3. Matched row | yes | ratios and `flips` from `selfcheck-c4.txt` |
| 4. Excluded rows | yes | same |
| 5. Observed vs. inferred | yes | S1 and S2 are source readings backed by counters |
| 6. Deviations and gaps | yes | listed |
| 7. Core question | yes | constant -> regime flag only; pool limit -> accounted size |

### 5.2 Run 2?

**No** (2026-10-28). The unit readings are exact relations over many cells, and the cluster result is flat to within 1-7 percent with an 8 x control; a negative-estimate Confirmed that agrees with the estimate and does not rest on one inferred statement. Run 2 would add little.

## 6. Run 2 -- fresh AI session (optional)

Not done.

## 8. Verdict -- AI

**Stage-3 estimate:** negative. **Outcome class:** true negative (negative, does not cap).

**Claim tested (B1):** the constant does not change the memory the memtable accounts for or the disk it flushes; it changes only whether contended writers retry lock-free or switch to the locked path (usage flat across constant values while the pool limit moves it).

| Tier | Verdict (B2g / B3g row) | Effect on the constraint | Basis | Date |
|---|---|---|---|---|
| Unit | Confirmed (row as amended by B0) | does not cap | run 1 + self-check | 2026-10-28 |
| Cluster | Confirmed | does not cap | run 1 + self-check | 2026-10-28 |

**Positive control:** unit: pools of 8 and 32 MiB, cleaner first called at 0.500-0.501 x limit, 3.99-4.00 x between the two (`unit/analysis.txt`). Cluster: memtable pool 128 / 512 / 1024 MiB, flush on-heap usage ratio 7.90 (`selfcheck-c4.txt`).

**Feedback filed:** section D of the case file filled (dated 2026-10-28, uncommitted); the case's B0 amendment (dated 2026-10-28) is part of the frozen text; no further section amended. Not re-estimated.
