# excess_waste_bytes-updatewastedallocationtracker-wastedbytes-2--autonomous — stage-4 results  <!-- file: results/excess_waste_bytes-updatewastedallocationtracker-wastedbytes-2--autonomous.md -->

> **Case:** [`excess_waste_bytes-updatewastedallocationtracker-wastedbytes-2--autonomous`](../../stage3-ai-deep-read/cases/excess_waste_bytes-updatewastedallocationtracker-wastedbytes-2--autonomous.md)
>
> **Status:** **Self-checked 2026-10-28 -- unit Confirmed (does not cap), cluster Confirmed (does not cap) on WD, the WE cells did not run (runbook defect D2); no run 2**
>
> **Outcome class:** true negative -- stage-3 estimate `negative` against the stage-4 effect `does not cap` ([definition](../README.md#outcome-class))
>
> **Agent:** autonomous (B2 = unit tier, B3 = cluster tier, feedback = section D).

## 1. Before run 1 — design audit and freeze

| Field | Content |
|---|---|
| **Case-file version** | sha256 of the whole file with section D still `none yet`, after the audit amendments B0 (S1 to S6 and the case text, dated 2026-10-28, inserted before B2): **unit tier** run on `dbb8eb6842062980bdec64625acfc18ed1f30a810f0c7edf7e388990ae17e799`; **cluster tier** run on `46eb1bdd4c0b3a8e3ad64d674e8e741aa186ce32c1b6fa9ef724319e661dba34` (differs only by S6: heap 4G raised to 8G on 2026-10-28 before the first cluster cell, after the unit tier and a discarded shakedown showed a thrashing JVM; no prediction or row changed). Repository HEAD of this session `b68711e`; case file, harness and results uncommitted. Frozen before the first reading of either tier. |
| **Harness** | [`harness/excess_waste_bytes-updatewastedallocationtracker-wastedbytes-2--autonomous/`](../harness/excess_waste_bytes-updatewastedallocationtracker-wastedbytes-2--autonomous/README.md), uncommitted: `mkvariant.sh`, `S4Waste.java`, `WasteProbe.java`, `unit-run.sh`, `unit-all.sh` (B2); `LoadGen.java`, `Jmx.java`, `cluster-run.py`, `cells.py`, `chain.sh` (B3); `selfcheck.py`. One code base shared by the four EXCESS_WASTE_* case files (identical copies; the cells each file runs are its own). md5s in `excess_waste_bytes-updatewastedallocationtracker-wastedbytes-2--autonomous/run1/harness.md5`. **Instrument checks (not readings, discarded):** javac of the probe and of the variants; every unit mode run once on `v1m`/`v10m` (an out-of-memory in an oversized contention config was removed from the probe); a 40 s shakedown of `cluster-run.py` (WB, `v10m`) that showed the constant read-back, the counters, the TRACE line and the samplers work. The author saw the output (see B0). |
| **Tiers and values** | B2 builds v1m / v10m / v1g (direct, burst C/8, stream, cont c3, control); B3 WD and WE x v1m / v10m / v1g x 2 repeats, control 128 MiB, single-thread cell. Both tiers kept. |
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
| R6 | the 20 s contention run replaced by a count-bounded run (960 updates) because a full pool blocks writers; citations corrected (S3) | Applied 2026-10-28 (B0) | runnable as written otherwise not |
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
| Full logs (outside the repo) | `pc39:~/stage4-logs/ew/` (`unit-c3/`, `cluster/<tag>/`) |

## 3. Runbook defects

| # | Run | Step | Problem | Fix | Decision (date) |
|---|---|---|---|---|---|
| D1 | cluster shakedown | S6 heap | at `-Xmx4G` the discarded 40 s shakedown showed 26 full collections in 40 s | heap 8 GB in every cell; S6 amended, case-file hash changed (section 1); claim, predictions and rows unchanged | 2026-10-28, before the first cluster cell |
| D2 | cluster | B3c/B3b WE (S_big: 32 threads x 1200 rows x 8 KiB = 9.8 MB per request) | all six WE cells (`c3-WE-<variant>-r<k>`) failed: 69-82 requests succeeded in 120 s, 39,975-48,200 errors `TransportException: Connection has been closed`; 194-406 full collections in 120 s with 8 GB heap, heap after GC 8.0 GB; the node cannot hold 32 requests of this size with the failed attempts' retained clones | none applied: lowering the thread count or the batch would be a different experiment (and the case's own claim about 'just under 10 MiB' also fails: a failed attempt's `heapSize` excludes value bytes, 0.3 MiB per failure measured); the WD cells carry the cluster tier | 2026-10-28 |

## 4. Run 1

**Scope:** every B2 value of B0 (unit) and every B3 cell of B0 (cluster), except the WE cells (D2). **Command log / raw readings:** `excess_waste_bytes-updatewastedallocationtracker-wastedbytes-2--autonomous/run1/` (`unit/*.out` and `unit/analysis.txt`, `cluster-c3.txt`, `cluster/<cell>/{summary.txt,s4waste-head-tail.txt,flush-lines-*.txt,loadgen.txt}`, `selfcheck-c3.txt`, `harness.md5`, `patch-v10m.diff`, `patch-v1.diff`). Full logs: `pc39:~/stage4-logs/ew/` (`unit-c3/`, `cluster/<cell>/`, `chain-all.log`).

### 4.1 Readings

**Unit tier** (`run1/unit/`; `analysis.txt` ends `all checks PASS`; 0 FAIL)

| Test or assertion | Result | Evidence |
|---|---|---|
| `direct`, `burst`, `stream`, builds `v1m`, `v10m`, `v1g`, pristine | boundary at `C-1023` for each constant (1 MiB, 10 MiB, 1 GiB); `C/8` reports lock at the 8th (k = 8, 9, 10 true; 6, 7 false); 1 KiB / 1 ms never locks; 16 KiB / 1 ms locks on `v10m`/`v1m` and not within the cap on `v1g` (excess below its 1 GiB window) | `unit/*-all.out`, `analysis.txt` |
| `cont` c3 (16 threads x 60 updates of one 64 KiB value, pool 1 GiB, 3 runs) | single-thread `owns` 63,188,400 B; contended `v1m` median 262,232,620 (ratio 4.15), `v10m` 220,156,100 (3.48), `v1g` 245,257,912 (3.88); builds differ by up to 42,076,520 B against a repeat spread of 220,738,568 B; `useLock` true in all three `v1m` runs, false in all `v10m` and `v1g` runs | `analysis.txt` |
| `cont` c1 (8 x 1000 small updates) | contended 6.8-7.2 M against single 3.08 M on all builds; `v1g` `useLock` false, `v1m`/`v10m` true | `analysis.txt` |
| `control` | as case 1 | `control` lines |

**Cluster tier** (`run1/cluster-c3.txt`; per flush: `Writing Memtable-t@...` and `Enqueuing flush of ks.t` lines of `debug.log`, first and last flush left out)

| Run | Observable | Reading | Evidence |
|---|---|---|---|
| WD (64 x 1 KiB), `v1m` / `v10m` / `v1g`, 2 runs each | ops per flush medians 15,600 / 15,216 / 16,240 (max/min 1.07); `Enqueuing` on-heap 171.5-171.6 MiB in all six; `flips` 156, 147 / 144, 160 / 0, 0; failed CAS 90-92 percent of attempts in all six (`fails` 398-445 k); allocation 54-60 GB | `cluster/c3-WD-*/` |
| WD, `v10m`, pool 128 vs 512 MiB | `Enqueuing` 43.3 vs 171.6 MiB (3.96); ops per flush 6,528 vs 15,216-15,840 | `c3-ctl128` |
| W1 single thread, `v1m` | 68,785 CAS attempts, `fails` 0, `flips` 0, no TRACE line; ops per flush 137,216 (against 15-17 k with 32 writers: contention, not the constant, changes rows per flush, S2) | `cluster/c3-single/` |
| WE (1200 x 8 KiB), all six cells | **not valid**: 69-82 requests in 120 s, 39,975-48,200 errors (`Connection has been closed`), 194-406 full collections, no usable flush lines (2 flushes) | `cluster/c3-WE-*/` |

### 4.2 Conclusion and logic

1. **Validity.** Unit: every constant was reached in its own build by construction [observed: `direct` rows at `C-1023`]; the loaded constant is read back in each JVM [observed: `config C=... OFFSET=... loadedFrom=.../s4-ew-var/<variant>/` first line of every `.out`]. Cluster: every counted cell passed the S5 validity test (no errors, constant read back from `s4waste.csv`, at least 4 flushes) [observed: `selfcheck-c3.txt` `PASS valid cell`]; the six WE cells did not (D2); no CassandraDaemon left after any cell [observed: `chain-all.log` `left=0`; `ps` 0 after the chain].
2. **Readings.** Anything unusual: the sentinel does not stop failed CAS (S1) [observed: `lockedFails` is 94 percent of locked attempts in the cluster cells]; failed attempts' value bytes are charged to the pool (S2) [observed: unit `fail` excess 1.04 x payload, `cont` 2-5 x single-threaded]; the hot cells' memtable on-heap at `Writing` exceeds the pool limit [observed: `Writing` lines]; no BLOCKED thread in any dump [observed: `cluster-c3.txt` `BLOCKED 0`]. 
3. **Matched row.** Unit B2g row 'owns() ... flat across variants and the control moves' as amended (S2: contended `owns()` 3.5-4.2 x the single-threaded value on every build, not ordered by the constant) -- Confirmed. Cluster B3g row 1 / 3 on WD: per-flush quantities flat across `v1m`/`v10m`/`v1g` (1.00-1.07), `v1m` and `v10m` reach the sentinel (`flips` > 0), `v1g` does not (0), pool control 3.96 x, single-thread cell shows no failure -- Confirmed on WD. The WE (S_big) cells did not run (runbook defect D2): the claim is not tested at that load.
4. **Excluded rows.** *Usage follows the constant (Refuted)*: unit builds' contended `owns` within their repeat spread, cluster flat ratios 1.00-1.07 and no ordering by constant [observed: `selfcheck-c3.txt` NOTE lines]. *Limit never reached / control did not move (Not confirmed)*: the regime flag was reached in the small-constant cells and not in the huge-constant ones, as the constants imply; the pool control moved 3.9-8 x [observed]. Withdrawn rows (BLOCKED threads, lower allocation for a tiny constant) are not used (B0 S1).
5. **Observed vs. inferred.** Inferred: that failed CAS continue in the locked regime because the monitor is the per-call `Updater` (source reading S1; observed consequence: `lockedFails` > 0 and no BLOCKED thread); that the per-flush differences between hot and cold/single cells are due to failed attempts' charged value bytes (S2; observed in the unit `fail` series).
6. **Deviations and gaps.** (1) The numeric tolerances of `analyze_unit.py` (burst +-2 calls + 2 percent, S2 ratio band 0.9-1.5, stream rule) were set at analysis time after seeing the raw lines; two of them were widened once (an off-heap cell header makes the excess 1.32 x the value bytes, and a cap-limited stream must be judged against its window): recorded in the script. The S5 rules (1.3, 3 x, 10 percent) were frozen. (2) The cluster shakedown at 4 GB heap showed a thrashing JVM; the heap was raised to 8 GB before the first cell (case-file hash changed, see section 1; the unit tier had run on the first hash and does not depend on S6). Even at 8 GB the hot cells show 12-18 full collections per 120 s (case 2 WB) and 0-2 (others). (3) `analyze_cluster.py` raised an index error for cell `c2-cold128` (case 2); `selfcheck.py` parsed it and is used. (4) Values are one run per cell where the case file asks for one; spread is known only for the repeated cells. WE untested (D2). One run per cell for the cases that ask for one; spread known only for repeated cells. The unit probe forces contention with a nested write; the cluster tier uses the in-tree driver and not cassandra-stress. Not verified: real-workload behaviour with the shipped 2-4 GB heaps the case files name (8 GB used), other allocation types in the cluster tier, multi-node.
7. **Core question.** On WD the three constants give the same rows per flush (15.2-16.2 k) and accounted size per flush; the regime flag is set for 1 MiB and 10 MiB and not for 1 GiB, with no effect on any of them; the pool limit moves flush size 3.96 x; one writer (no failed CAS) flushes 137 k rows per memtable against 15 k with 32 writers, again contention and not the constant. WE (9.6 MB requests) was not testable on this node.

**Conclusion (one line):** Unit B2g row 'owns() ... flat across variants and the control moves' as amended (S2: contended `owns()` 3.5-4.2 x the single-threaded value on every build, not ordered by the constant) confirmed (does not cap); cluster confirmed (does not cap) on WD (WE not run).

## 5. Self-check of run 1 -- AI

### 5.1 Check of run 1's conclusion

`selfcheck.py 3` re-parsed the raw logs with plain string operations (not the analysis regexes) and re-evaluated the S5 rules: `run1/selfcheck-c3.txt`. Raw files re-opened by hand: `cluster/<cell>/s4waste-head-tail.txt`, `flush-lines-first8.txt`, `loadgen.txt`, `unit/analysis.txt`.

| Part | Holds? | Note (file re-read) |
|---|---|---|
| 1. Validity | yes; WE cells excluded (D2) | `selfcheck-c3.txt` `PASS valid cell` for every counted cell |
| 2. Readings | yes | counters and flush lines agree between `cluster-c3.txt` and `selfcheck-c3.txt` |
| 3. Matched row | yes | ratios and `flips` from `selfcheck-c3.txt` |
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
| Cluster | Confirmed on WD; WE cells invalid (D2) | does not cap | run 1 + self-check | 2026-10-28 |

**Positive control:** unit: pools of 8 and 32 MiB, cleaner first called at 0.500-0.501 x limit, 3.99-4.00 x between the two (`unit/analysis.txt`). Cluster: memtable pool 128 / 512 / 1024 MiB, flush on-heap usage ratio 3.96 (`selfcheck-c3.txt`).

**Feedback filed:** section D of the case file filled (dated 2026-10-28, uncommitted); the case's B0 amendment (dated 2026-10-28) is part of the frozen text; no further section amended. Not re-estimated.
