# excess_waste_bytes-uselock-wastetracker--autonomous — stage-4 results  <!-- file: results/excess_waste_bytes-uselock-wastetracker--autonomous.md -->

> **Case:** [`excess_waste_bytes-uselock-wastetracker--autonomous`](../../stage3-ai-deep-read/cases/excess_waste_bytes-uselock-wastetracker--autonomous.md)
>
> **Status:** **Self-checked 2026-10-28 -- unit Confirmed (does not cap), cluster Confirmed (does not cap); no run 2**
>
> **Outcome class:** true negative -- stage-3 estimate `negative` against the stage-4 effect `does not cap` ([definition](../README.md#outcome-class))
>
> **Agent:** autonomous (B2 = unit tier, B3 = cluster tier, feedback = section D).

## 1. Before run 1 — design audit and freeze

| Field | Content |
|---|---|
| **Case-file version** | sha256 of the whole file with section D still `none yet`, after the audit amendments B0 (S1 to S6 and the case text, dated 2026-10-28, inserted before B2): **unit tier** run on `ce632648878a7581f9ec9407e77f7b16114fdb3f1b87834deff5b63e3dfafee0`; **cluster tier** run on `44bc6239592515a9789d84c2c9c1511db8dd68dd497dca4a6d18389a17755e44` (differs only by S6: heap 4G raised to 8G on 2026-10-28 before the first cluster cell, after the unit tier and a discarded shakedown showed a thrashing JVM; no prediction or row changed). Repository HEAD of this session `b68711e`; case file, harness and results uncommitted. Frozen before the first reading of either tier. |
| **Harness** | [`harness/excess_waste_bytes-uselock-wastetracker--autonomous/`](../harness/excess_waste_bytes-uselock-wastetracker--autonomous/README.md), uncommitted: `mkvariant.sh`, `S4Waste.java`, `WasteProbe.java`, `unit-run.sh`, `unit-all.sh` (B2); `LoadGen.java`, `Jmx.java`, `cluster-run.py`, `cells.py`, `chain.sh` (B3); `selfcheck.py`. One code base shared by the four EXCESS_WASTE_* case files (identical copies; the cells each file runs are its own). md5s in `excess_waste_bytes-uselock-wastetracker--autonomous/run1/harness.md5`. **Instrument checks (not readings, discarded):** javac of the probe and of the variants; every unit mode run once on `v1m`/`v10m` (an out-of-memory in an oversized contention config was removed from the probe); a 40 s shakedown of `cluster-run.py` (WB, `v10m`) that showed the constant read-back, the counters, the TRACE line and the samplers work. The author saw the output (see B0). |
| **Tiers and values** | B2 builds v10m / v1m / v100m (account, seqc, seqd, sentinel, control); B3 WB hot and WC cold on v10m, controls at 128 MiB, rebuilds v1m and v100m on WB. Both tiers kept. |
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
| R6 | forced-failure hook and calibration made exact (B0 case-2 text); the BLOCKED-thread evidence withdrawn (S1) | Applied 2026-10-28 (B0) | runnable as written otherwise not |
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
| Full logs (outside the repo) | `pc39:~/stage4-logs/ew/` (`unit-c2/`, `cluster/<tag>/`) |

## 3. Runbook defects

| # | Run | Step | Problem | Fix | Decision (date) |
|---|---|---|---|---|---|
| D1 | cluster shakedown | S6 heap | at `-Xmx4G` the discarded 40 s shakedown showed 26 full collections in 40 s | heap 8 GB in every cell; S6 amended, case-file hash changed (section 1); claim, predictions and rows unchanged | 2026-10-28, before the first cluster cell |
| D3 | analysis | `analyze_cluster.py` | index error on one case-2 cell, no effect on raw data | `selfcheck.py` parses the cell independently | 2026-10-28 |

## 4. Run 1

**Scope:** every B2 value of B0 (unit) and every B3 cell of B0 (cluster). **Command log / raw readings:** `excess_waste_bytes-uselock-wastetracker--autonomous/run1/` (`unit/*.out` and `unit/analysis.txt`, `cluster-c2.txt`, `cluster/<cell>/{summary.txt,s4waste-head-tail.txt,flush-lines-*.txt,loadgen.txt}`, `selfcheck-c2.txt`, `harness.md5`, `patch-v10m.diff`, `patch-v1.diff`). Full logs: `pc39:~/stage4-logs/ew/` (`unit-c2/`, `cluster/<cell>/`, `chain-all.log`).

### 4.1 Readings

**Unit tier** (`run1/unit/`; `analysis.txt` ends `all checks PASS`; 0 FAIL)

| Test or assertion | Result | Evidence |
|---|---|---|
| `direct`, `burst` (including `C/8` x k), `refill`, `stream`, builds `v10m`, `v1m`, `v100m`, pristine | boundary at `C-1023` for all three constants; `C/8` reports lock at the 8th (`v10m`, `v1m`); `C-1024` twice locks only with a gap below the window (0 and 500 ms yes, 1500 ms no, window 1342 ms); 1 KiB / 1 ms and 8 KiB / 2 ms never lock, 16 KiB / 1 ms locks | `unit/*-all.out`, `analysis.txt` |
| `account` forced failure (nested write), factor 0.5 and 1.2 of C | one failed CAS each (`fails` 1); sentinel iff measured W >= C-1023; `owns` excess over the failure-free reference = 1.04 x payload of the failed attempt (`heap_buffers`, on-heap), 1.32 x (`offheap_objects`, off-heap: cell header) | `fail` lines |
| `seqc` 12 failures of ~1 MiB back to back (W 1,046,656-1,048,320) | `v10m`: first lock at failure 11 (`heap_buffers`) and 12 (`offheap_objects`); `v1m`: failure 1; `v100m`: none in 12 | `analysis.txt` |
| `seqd` 200 failures of ~8 KiB, 2 ms apart | never locks, both allocation types (456 / 443 ms) | `seqd` lines |
| `nohook`, `sentinel` | tracker stays 0 without failures; sentinel set by hand on an uncontended partition: `owns`, `dataSize`, `heapSize` identical to the unset partition over 1000 updates, both types | `nohook`, `sentinel` lines |
| `control` | as case 1: cleaner at 0.500-0.501 x limit for `heap_buffers`, `offheap_objects` and `unslabbed_heap_buffers` (the case's `HeapPool`), 32/8 ratio 3.99-4.00 | `control` lines |

**Cluster tier** (`run1/cluster-c2.txt`; per flush: `Writing Memtable-t@...` and `Enqueuing flush of ks.t` lines of `debug.log`, first and last flush left out)

| Run | Observable | Reading | Evidence |
|---|---|---|---|
| WB hot, `v10m` | 41 flushes used, ops per flush 186,000, `Enqueuing` 170.8 MiB, `flips` 43, TRACE line 43 of 43 partitions, 93.2 percent of attempts failed | `cluster/c2-hot/` |
| WB hot, `v1m` / `v100m` | ops per flush 188,000 / 188,000; `Enqueuing` 170.8 MiB; `flips` 37 / 43; allocation 69.8 / 86.1 GB (`v10m` 74.4 GB); max/min across the three: ops 1.01, on-heap at `Writing` 1.04, `Enqueuing` 1.00 | `c2-hot-v1m`, `c2-hot-v100m` |
| WC cold, `v10m` | 55 flushes used, 576,000 ops per flush; `fails` 1 of 16,784 attempts; `flips` 0, no TRACE line | `cluster/c2-cold/` |
| Pool 128 vs 512 MiB, hot / cold | `Enqueuing` on-heap 42.8 vs 170.8 MiB (3.99) / 45.8 vs 179.6 MiB (3.92); the memtable on-heap at `Writing` is larger than the limit in the hot cells (328 MiB at 128 MiB, 374 MiB at 512 MiB): failed attempts keep charging while the flush starts | `c2-hot128`, `c2-cold128`, `selfcheck-c2.txt` |
| GC allocation, hot vs cold | 74.4 GB hot against 107.4 GB cold in absolute terms (the cold cell ingests 33 M rows against 8.2 M); per row 9.0 kB against 3.2 kB | `cluster-c2.txt` |

### 4.2 Conclusion and logic

1. **Validity.** Unit: every constant was reached in its own build by construction [observed: `direct` rows at `C-1023`]; the loaded constant is read back in each JVM [observed: `config C=... OFFSET=... loadedFrom=.../s4-ew-var/<variant>/` first line of every `.out`]. Cluster: every counted cell passed the S5 validity test (no errors, constant read back from `s4waste.csv`, at least 4 flushes) [observed: `selfcheck-c2.txt` `PASS valid cell`]; no CassandraDaemon left after any cell [observed: `chain-all.log` `left=0`; `ps` 0 after the chain].
2. **Readings.** Anything unusual: the sentinel does not stop failed CAS (S1) [observed: `lockedFails` is 94 percent of locked attempts in the cluster cells]; failed attempts' value bytes are charged to the pool (S2) [observed: unit `fail` excess 1.04 x payload, `cont` 2-5 x single-threaded]; the hot cells' memtable on-heap at `Writing` exceeds the pool limit [observed: `Writing` lines]; no BLOCKED thread in any dump [observed: `cluster-c2.txt` `BLOCKED 0`]. 
3. **Matched row.** Unit B2g row 'owns() equal in both modes (sentinel vs not) and the positive control rises and triggers the cleaner' as amended (S2: the failed attempts' value bytes add 1.04 x payload; the sentinel itself adds nothing) -- Confirmed. Cluster B3g row 1 (as amended): the three constants give the same per-flush quantities on WB; the 128 vs 512 MiB control moves the flush size 3.99 x; the TRACE line / `flips` appear in WB (43) and not in WC (0) -- Confirmed.
4. **Excluded rows.** *Usage follows the constant (Refuted)*: unit builds' contended `owns` within their repeat spread, cluster flat ratios 1.00-1.07 and no ordering by constant [observed: `selfcheck-c2.txt` NOTE lines]. *Limit never reached / control did not move (Not confirmed)*: the regime flag was reached in the small-constant cells and not in the huge-constant ones, as the constants imply; the pool control moved 3.9-8 x [observed]. Withdrawn rows (BLOCKED threads, lower allocation for a tiny constant) are not used (B0 S1).
5. **Observed vs. inferred.** Inferred: that failed CAS continue in the locked regime because the monitor is the per-call `Updater` (source reading S1; observed consequence: `lockedFails` > 0 and no BLOCKED thread); that the per-flush differences between hot and cold/single cells are due to failed attempts' charged value bytes (S2; observed in the unit `fail` series).
6. **Deviations and gaps.** (1) The numeric tolerances of `analyze_unit.py` (burst +-2 calls + 2 percent, S2 ratio band 0.9-1.5, stream rule) were set at analysis time after seeing the raw lines; two of them were widened once (an off-heap cell header makes the excess 1.32 x the value bytes, and a cap-limited stream must be judged against its window): recorded in the script. The S5 rules (1.3, 3 x, 10 percent) were frozen. (2) The cluster shakedown at 4 GB heap showed a thrashing JVM; the heap was raised to 8 GB before the first cell (case-file hash changed, see section 1; the unit tier had run on the first hash and does not depend on S6). Even at 8 GB the hot cells show 12-18 full collections per 120 s (case 2 WB) and 0-2 (others). (3) `analyze_cluster.py` raised an index error for cell `c2-cold128` (case 2); `selfcheck.py` parsed it and is used. (4) Values are one run per cell where the case file asks for one; spread is known only for the repeated cells. One run per cell for the cases that ask for one; spread known only for repeated cells. The unit probe forces contention with a nested write; the cluster tier uses the in-tree driver and not cassandra-stress. Not verified: real-workload behaviour with the shipped 2-4 GB heaps the case files name (8 GB used), other allocation types in the cluster tier, multi-node.
7. **Core question.** Same pattern on WB: constants 1 MiB, 10 MiB, 100 MiB give the same rows per flush (186-188 k), flush size and allocation; only the S4 counters differ in `flips` (37-43 vs the cold 0) and contention changes the accounted size (hot 25.7 MiB serialized per 170 MiB of owned heap, cold 79.7 MiB). The pool limit moves the flush size 3.99 x.

**Conclusion (one line):** Unit B2g row 'owns() equal in both modes (sentinel vs not) and the positive control rises and triggers the cleaner' as amended (S2: the failed attempts' value bytes add 1.04 x payload; the sentinel itself adds nothing) confirmed (does not cap); cluster confirmed (does not cap).

## 5. Self-check of run 1 -- AI

### 5.1 Check of run 1's conclusion

`selfcheck.py 2` re-parsed the raw logs with plain string operations (not the analysis regexes) and re-evaluated the S5 rules: `run1/selfcheck-c2.txt`. Raw files re-opened by hand: `cluster/<cell>/s4waste-head-tail.txt`, `flush-lines-first8.txt`, `loadgen.txt`, `unit/analysis.txt`.

| Part | Holds? | Note (file re-read) |
|---|---|---|
| 1. Validity | yes | `selfcheck-c2.txt` `PASS valid cell` for every counted cell |
| 2. Readings | yes | counters and flush lines agree between `cluster-c2.txt` and `selfcheck-c2.txt` |
| 3. Matched row | yes | ratios and `flips` from `selfcheck-c2.txt` |
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

**Positive control:** unit: pools of 8 and 32 MiB, cleaner first called at 0.500-0.501 x limit, 3.99-4.00 x between the two (`unit/analysis.txt`). Cluster: memtable pool 128 / 512 / 1024 MiB, flush on-heap usage ratio 3.99 (`selfcheck-c2.txt`).

**Feedback filed:** section D of the case file filled (dated 2026-10-28, uncommitted); the case's B0 amendment (dated 2026-10-28) is part of the frozen text; no further section amended. Not re-estimated.
