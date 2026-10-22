# memtable_heap_space-needsCleaning-nextClean--autonomous — stage-4 results  <!-- file: results/memtable_heap_space-needsCleaning-nextClean--autonomous.md -->

> **Case:** [`memtable_heap_space-needsCleaning-nextClean--autonomous`](../../stage3-ai-deep-read/cases/memtable_heap_space-needsCleaning-nextClean--autonomous.md)
>
> **Status:** verdict filed 2026-10-22. **Unit Confirmed — caps; cluster Confirmed — caps** (soft trigger at exactly `L·t`; two sub-predictions missed, the hard cap not reached on the node). Run 1 only.
> 
> **Outcome class:** true positive — stage-3 estimate vs the stage-4 effect on the constraint
>
> **Agent:** autonomous. "§9a" below means B2f/B2g (unit) and B3f/B3g (cluster); "§9b–§9e" means B2a–B2e / B3a–B3e; the feedback section is the case file's section D.

## 1. Before run 1 — design audit and freeze

| Field | Content |
|---|---|
| **Case-file version** | Not committed (the file is untracked in the repo, as filed by stage 3). sha256 before the audit `ed2d18f332d25b6182e92e8fc58c4719647fd0067da682744bea4e6959bbaf1f`; **frozen after the audit's amendments: `0378bf7d45276199e3bb3971324e5b5224cd7fc636c2927a11fd676289500bad`**. Section D was filled after run 1 (new sha256 in §8). |
| **Harness** | `../harness/memtable_heap_space-needsCleaning-nextClean--autonomous/`: `NextCleanBoundaryTest.java`, `unit-run.sh` (unit); `ncl.btm`, `cluster-run.sh`, `all-runs.sh`, `analyze.py`, `README.md` (cluster). Not committed (no commit was asked for). The copies actually run are in `pc07:~/stage4-harness-run/ncl/` (unit) and `pc07:~/stage4-harness-run/ncl/attempt4/` (cluster), each with `SHA256SUMS`. Three harness fixes were made during run 1 (§3); `analyze.py`'s column fix was made after R1 (analysis only). |
| **Tiers and values** | Unit (B2): pool limit L = 64 MiB at t = 0.10 / 0.25 / 0.33333334 / 0.50 / 0.90, plus L = 32 and 128 MiB at t = 0.25; Parts A, B, C. Cluster (B3): R1 128 MiB, R2 512 MiB, R3 1024 MiB (= default for `-Xmx4G`) at t = 1/3 (default), R4 512 MiB at t = 0.15, R5 512 MiB at t = 0.66; 3,000,000 × 1 KiB rows at 10,000 rows/s each. |
| **Audit bottom line** | **Ready after amendments** — 2026-10-21 |

**What this file tests beyond the closed `tryAllocate` cases.** `memtable_heap_space-tryAllocate-limit--guided` and `--autonomous` test the **hard** check (`MemtablePool.java:156`): an allocation blocks at `allocated + size > limit`, the discarding overshoot, and on the node a dose-response of flush count with two (autonomous) values of L. This file tests the **soft** trigger at line 128: that the first flush fires exactly when the non-flushing bytes exceed `(long)(limit × cleanThreshold)` (strict `>`), that `reclaiming` offsets it, that it follows both L and t independently, and on the node that the trigger, the pool usage including flushing memtables and the forced-GC live heap all follow L (three values incl. the default) and t (three values). Overlap: Part C of the unit tier and R5 re-test the hard check (noted in section D).

### 1.1 Design audit

| Group | Check | Rating | Note (section checked) |
|---|---|---|---|
| A. Core question | constrained quantity is memory or disk bytes | Met | A2: JVM heap of memtables; operand `SubPool.allocated`, bytes |
| A. Core question | knob varied, ≥ 3 values incl. default | Met | B3b: L = 128 / 512 / 1024 MiB (1024 = heap/4 default), t = 0.15 / 1/3 (default) / 0.66; B2b five t and three L |
| A. Core question | real resource measured, not only the counter (gap named) | Met | B3d O3 forced-GC live set minus a baseline; gap (memtable bytes are inferred as O3 − B) named in B3d |
| A. Core question | usage driven to the limit and past it | Partly | Unit Part C past L; cluster: workload is 3.6× the largest L so the trigger is crossed many times, but whether the node reaches L itself is left to R5 (B3g has a row for "not reached") |
| B. Logic | each step says what it establishes | Met | B1, B2g, B3g |
| B. Logic | prediction stated in numbers or a clear relation | Met | B2c table (exact chunk indices), B3f bands and ratios |
| B. Logic | every plausible outcome has a conclusions row | Met | B2g / B3g include exceeds-limit, flat, counter-capped-but-heap-grows, control-did-not-move, other flush reasons, R5 cap not reached |
| B. Logic | confirmation needs ceiling-follows-knob and direct disallow evidence | Partly | The disallow branch of line 128 is a flush trigger; on the node the only evidence was the cleaner's log line. Amendment K1 adds a direct trace of line 128 returning true |
| B. Logic | alternative explanations and their controls | Met | B2h, B3h (flush reasons, baseline, commitlog cap, R2/R4/R5 at fixed L) |
| C. Specific | a human can follow it from the intro and B1 | Met | |
| C. Specific | an AI can run B2–B3 without re-deriving the code path | Met | full code and commands given |
| C. Specific | knob, values, workload, commands, observables, sampling, stop conditions exact | Partly | Part C's after-release reading is racy (U2); N_flush grep counts all tables (K4); B2h control not in the code (U1) |
| D. Runnable | harness and environment prerequisites exist or are listed | Met | clone + `ant build-test` (stress included) |
| D. Runnable | workload arithmetic reaches the limit | Met | 3 M × ~1.3 KiB ≈ 3.7 GiB tracked vs t·L ≤ 341 MiB; disk ≤ 12 GB |
| D. Runnable | load-bearing citations spot-checked against the pinned clone | Partly | `MemtablePool.java:125-147, 151-161, 187-214`, `MemtableAllocator.java:169-197, 129-155`, `AbstractAllocatorMemtable.java:293`, `DatabaseDescriptor.java:590, 767`, `ColumnFamilyStore.java:1055` all as cited. **Wrong:** B3d says O1 (`AllMemtablesOnHeapDataSize`) equals `SubPool.used()`; it reads only the current memtable (`TableMetrics.java:876-882`), so it excludes flushing memtables (K1) |

| # | Recommendation | Applied? | Why |
|---|---|---|---|
| U1 | Print and assert B2h's off-heap control (`offHeap.used()==0`, `needsCleaning()==false`) | Applied 2026-10-21, case file after B2h, harness test | the control was described but not in the code |
| U2 | Part C: count the helper's chunks and the released bytes; predict `released/C ± 1` more chunks after release and `used ≤ L` | Applied 2026-10-21, case file after B2f | the original "used falls by the discarded total" cannot be read 200 ms later (the helper refills) |
| K1 | O1 is live-only; read `P_pool` from a Byteman trace of `SubPool.released` entry (O1b), trace line 128 true (O7), refused `tryAllocate` (O5b); add prediction 1b (`nextClean − reclaiming = (long)(L·t)`) | Applied 2026-10-21, case file after B3d | citation error, independent of readings; direct evidence that line 128 fired |
| K3 | O3 cadence 15 s instead of 30 s | Applied 2026-10-21, case file after B3e | 30 s ≈ one R3 sawtooth period; P5 would depend on phase |
| K4 | N_flush counts `keyspace1.standard1` only | Applied 2026-10-21 | the bare grep also counts system tables |
| E1 | Paths `/tmp/s3mhs` → `~/stage4-ncl`, `~/stage4-logs/ncl`; node on 127.0.0.5, JMX 7205, `-port jmx=7205` for stress | Environment deviation, not a case-file change | shared host (another stage-4 node on 127.0.0.4) |
| S1 | B3f's `P_pool` would be clearer stated as "live + flushing"; prediction 2's R5 ≥ 0.85·L rests on flushes being slow, which B3g already doubts | Left for stage 3 | |

## 2. Environment

| Field | Run 1 |
|---|---|
| Date | 2026-10-21 (unit 22:50) – 2026-10-22 00:10 EDT (node clock; log lines are UTC) |
| Node | `pc07` (`node0.jason92-320876`), 40 cores, 251 GiB, **shared with another stage-4 agent's node** (`largestRatio`, 127.0.0.4 / JMX 7204), which ran its own cluster tier during R2–R5 |
| OS and kernel | Ubuntu 22.04.2, `5.15.0-187-generic` |
| JDK | OpenJDK 11.0.32.1 |
| Ant | 1.10.12 |
| Local clone | `~/cassandra-ncl`, `cassandra-5.0.9` = `b5f2a54210d541339c2e7c17a794195cac0e67c2`, `ant build-test` 1 min 10 s, `BUILD SUCCESSFUL`; status clean after the run |
| Case-file commit / harness commit | none (untracked; sha256 in §1) |
| Storage | `/dev/sda3` local ext, data and commit log in `~/stage4-ncl` (≤ 4.1 GB per run, wiped before each run and after the last) |
| Node settings | `MAX_HEAP_SIZE=4G HEAP_NEWSIZE=800M`, G1 (shipped options), `ulimit -n 100000`, Byteman 4.0.20 agent with `ncl.btm` |
| Full logs | `pc07:~/stage4-logs/ncl/` (`unit-*`, `R1`…`R5`, three aborted R1 attempts, `analyze-out.txt`) |

## 3. Runbook defects

| # | Run | Step | Problem | Fix | Decision | Case-file change |
|---|---|---|---|---|---|---|
| 1 | 1 | B3e warm-up stress (harness) | R1 attempt 1: stress started 1 s after `Startup complete` and failed `Cannot connect` | wait 10 s, retry up to 5 times | 2026-10-21; attempt 1 not counted | none (§9a unchanged) |
| 2 | 1 | B3d O1b/O7 (harness) | R1 attempt 2: no Byteman lines after start-up — `CassandraDaemon` closes `System.out` for a background daemon, so `traceln` output is lost | `traceOpen`/`traceln` to the file named by `-Dncl.trace` | 2026-10-21; attempt 2 aborted, not counted | none |
| 3 | 1 | run procedure (harness, operator) | attempt 2's script, killed with `pkill`, was edited while still running and continued to its clean-up, which ran `nodetool stopdaemon` against attempt 3's node 6 s after its start; and the clean-up's bare `wait` waited forever on the `tee` process substitution | run from a frozen copy (`attempt4/`), `trap "exit 1" INT TERM`, wait only for the sampler PIDs | 2026-10-21; attempt 3 not counted; attempt 4 = run 1 | none |
| 4 | 1 | B3e log parsing | logback rolled `system.log` at local midnight during R4, so the offset-based `system-run.log` was empty | R4's `system-run.log` rebuilt from the rolled zip + the current file at the same offset, cut at `Cassandra shutting down` (`run1/R4/postproc.txt`) | 2026-10-22 | none |

The unit tier was started once before the audit's amendments were written into the case file (2026-10-21, before 22:50), then stopped and its output deleted unread; the counted unit run is the one after the freeze.

## 4. Run 1

**Scope:** both tiers, all values. **Command log:** `memtable_heap_space-needsCleaning-nextClean--autonomous/run1/unit-run.log`, `unit-ncb.txt`, `unit-junit.xml`; per cluster run `run1/R<n>/run.log` (+ `trig.txt`, `bm.txt`, `base.txt`, `live.txt`, `pool.txt`, `yaml.diff`, `stress-summary.txt`, `tablestats-excerpt.txt`); `run1/analyze-out.txt`; `run1/aborted-attempts.txt`.

### 4.1 Readings

**Unit tier** (`run1/unit-ncb.txt`, `unit-junit.xml`: `Tests run: 2, Failures: 0, Errors: 0`)

| Test or assertion | Result | Evidence |
|---|---|---|
| Part A, L = 64 MiB, first true of line 128 (`directIdx`) for t = 0.10 / 0.25 / 1/3 / 0.50 / 0.90 | chunk 26 / **65** / 86 / **129** / 231, `directUsed = cleanerUsed` = 6,815,744 / 17,039,360 / 22,544,384 / 33,816,576 / 60,555,264 B; `nextClean` = T = 6,710,886 / 16,777,216 / 22,369,622 / 33,554,432 / 60,397,976; one cleaner invocation each | `unit-ncb.txt` "NCB A" |
| Part A scaling, t = 0.25 | L = 32 MiB: 8,650,752 B (chunk 33); L = 128 MiB: 33,816,576 B (chunk 129) | same |
| Part A off-heap control (U1) | `offHeapUsed=0`, `offHeapNeedsCleaning=false` in all 7 | same |
| Part B, live at each trigger | every snapshot `live = m·C` (6,815,744 / 17,039,360 / 22,544,384 / 33,816,576 / 60,555,264), in (T, T + 2C]; k-th snapshot `used = k·m·C`, `reclaiming = (k−1)·m·C`, `nextClean = reclaiming + T` | "NCB B" |
| Part B, trigger count | 9 / 3 / 2 / 1 / 1 | "NCB B … triggersB" |
| Part C, hard cap | blocked = true at `usedAtBlock` = 67,108,864 = L for every t | "NCB C" |
| Part C, release (U2) | helper completed exactly `released/C` more chunks (234 / 195 / 172 / 129 / 231) and blocked again; `used` = 67,108,864 ≤ L after release | "NCB C … afterRelease" |

**Cluster tier** (`run1/analyze-out.txt`; MiB = 2^20 B; T = `(long)(L·t)`)

| Run (L, t) | Triggers / N_flush (MEMTABLE_LIMIT, ks1) | median `live` / min `Used total` at trigger | O7 lines; self-consistent; exact | P_pool (O1b) | O1 max (live) | B (baseline) | P_live | Blocked |
|---|---|---|---|---|---|---|---|---|
| R1 (128, 1/3), T = 42.7 | 101 / 101 | 0.33 / 0.33 | 53; 32; 32 | 71.7 (0.56 L) | 42.4 | 82.5 | **42.8** | 0 |
| R2 (512, 1/3), T = 170.7 | 25 / 25 | 0.33 / 0.33 | 26; 18; 18 | 226.2 (0.44 L) | 165.7 | 66.2 | **180.4** | 0 |
| R3 (1024, 1/3), T = 341.3 | 12 / 12 | 0.33 / 0.33 | 10; 10; 10 | 467.5 (0.46 L) | 339.4 | 73.5 | **363.5** | 0 |
| R4 (512, 0.15), T = 76.8 | 56 / 56 | 0.15 / 0.15 | 48; 36; 36 | 114.3 (0.22 L) | 76.4 | 74.7 | **98.0** | 0 |
| R5 (512, 0.66), T = 337.9 | 12 / 12 | 0.66 / 0.66 | 11; 9; 9 | 375.6 (0.73 L) | 337.7 | 77.1 | **344.9** | 0 |

Other evidence per run (`run1/R<n>/run.log`): startup line `Global memtable on-heap threshold is enabled at <L>MiB`; deprecation warning 0 in R1–R3, 1 in R4–R5; stress 3,000,000 partitions, 0 errors, ~9,980–10,000 op/s, 5:00; 0 keyspace1 flushes with another reason; 0 `^ERROR` lines; 0 refused `tryAllocate` (O5b) and `BlockedOnAllocation` Count 0 in every run; every `Flushing largest` line names `keyspace1.standard1`. On self-consistent O7 lines, `live − T` at the moment line 128 returned true was 7 B … 7.8 KiB.

### 4.2 Conclusion and logic

**Unit tier**

1. **Validity** — [observed: `unit-junit.xml`] both tests ran to completion; all thresholds were reached below 0.95·L as B2c computed; Part C pushed past L. Valid.
2. **Readings** — nothing unusual. Every value equals B2c's table exactly. [observed: `unit-ncb.txt`]
3. **Matched row** — B2g row 1: "All Part A values equal the table; Part B live values in (T, T+2C]; Part C blocks at ≤ L — Mechanism works as traced. Line 128 fires at `L·t` above `reclaiming`, and `tryAllocate` caps the total at L." [observed: `unit-ncb.txt` NCB A/B/C lines]
4. **Excluded rows** — `>=` row: t = 0.25 / 0.50 fired at chunks 65 / 129, not 64 / 128 [observed]. Trigger-independent-of-knob row (**Refuted**): the first trigger moved with t (26…231) and with L (33 / 65 / 129 at 32 / 64 / 128 MiB, t = 0.25) [observed]. Reclaiming-not-honoured row: the k-th trigger at `used = k·m·C` with `live = m·C` [observed]. Part C not blocked / `usedAtBlock > L` (**Refuted**): blocked at exactly L [observed]. Cleaner-missing row: `cleanerUsed` = `directUsed` in all 7 [observed].
5. **Observed vs. inferred** — none of the unit conclusion is inferred. The unit tier measures the accounting only; no real heap is allocated by `SubAllocator.allocate` (gap named in the audit; the cluster tier covers heap).
6. **Deviations and gaps** — U1, U2 amendments; the 200 ms after-release reading now uses chunk counts. Path deviation (`~/cassandra-ncl`).
7. **Core question** — line 128 fires exactly when `used − reclaiming > (long)(L·t)` (parts 3, 4), proportional to L at fixed t and to t at fixed L, and the companion check blocks at L. At unit level the operand follows the knob exactly.

**Conclusion (unit, one line):** B2g row 1 — confirmed.

**Cluster tier**

1. **Validity** — [observed: `R<n>/run.log`] each run started with the yaml's L (startup line) and the deprecation warning only where t was set; 3 M rows written with 0 errors at ~10 k/s; all keyspace1 flushes MEMTABLE_LIMIT (no commitlog or period flushes); the trigger level `t·L` was crossed 12–101 times per run. The hard cap L was **not** reached in any run (P_pool ≤ 0.73 L, 0 refusals). Valid for the trigger claim; the hard-cap part of B1 is not exercised on the node (B3g's R5 row).
2. **Readings** — (a) O7 has fewer lines than triggers: the rule de-duplicates on `reclaiming`, so an episode starting at the same `reclaiming` as the last logged line (typically 0, after a flush completed) is skipped [observed: `bm.txt`; inferred: from the rule text]. (b) 43 of 148 O7 lines carry `used − reclaiming ≤ T`: their fields were read after a concurrent switch, so they are not the snapshot on which `needsCleaning` returned true [inferred: such a line cannot satisfy `used() > nextClean` with its own values]. (c) P_live ≈ T rather than P_pool: the forced-GC live set holds about one memtable's worth above baseline at the sampled instants.
3. **Matched row** — B3g row 1, "Predictions 1–5 hold — `memtable_heap_space` (through line 128 at `t·L` …) governs actual memtable heap. Claim confirmed", with two sub-predictions missed (part 6), and B3g row 2 (positive control): R3's P_pool 467.5 MiB and P_live 363.5 MiB are far above R1's 71.7 / 42.8 MiB, and R1 stays ≤ 1.15·128 + 64 MiB [observed: `analyze-out.txt`]. Prediction by prediction [observed: `analyze-out.txt`, `trig.txt`, `bm.txt`]: **P1** median `live` 0.33 / 0.33 / 0.33 / 0.15 / 0.66, every trigger, all within the bands; **P1b (K1)** missed as stated (exact in 35/53, 20/26, 10/10, 39/48, 10/11 lines, < 95 % in four runs) but **every self-consistent line is exact (105/105)**; **P2** P_pool ≤ L + 8 MiB and ≥ t·L in every run, O1 ≤ L; R5 P_pool ≥ 0.85 L **missed** (0.73 L), Blocked 0 in R1–R4 as predicted; **P3** N_flush 101 (85–125), 12 (11–16), R1/R3 8.42 (6–10), R4/R2 2.24 (1.7–2.6); **P4** P_live ≤ 1.15·P_pool + 64 MiB in every run; **P5** P_live(R3) − P_live(R1) = 320.7 MiB ≥ 250.
   B3g row "R5 BlockedOnAllocation = 0 and P_pool < 0.8·L — consistent with the claim, but the hard cap was not exercised on the node. Note it." also matches [observed: R5 Blocked 0, P_pool 0.73 L].
4. **Excluded rows** — R3 control did not move (Not confirmed): R3 P_pool 467.5 ≥ 200 MiB. Counter-capped-but-heap-grows (**Refuted**): P_live ≤ 1.15·P_pool + 64 MiB everywhere (largest ratio R2 180.4 vs 324.1). P_pool > 1.1·L (**Refuted**): max 0.73 L. `live_trig` same in R2/R4/R5 (**Refuted**): 0.33 / 0.15 / 0.66. Other flush reasons (Not confirmed): 0 in every run. Refuted-if list of B3f: none met (N_flush ratio 8.42 ≥ 3; P_live diff 320.7 ≥ 100 MiB).
5. **Observed vs. inferred** — inferred: (i) memtable heap = O3 − B (design's own gap); (ii) the 43 non-self-consistent O7 lines are stale reads (from the values themselves); (iii) R5 did not reach L because flushes of ~338 MiB completed before the next 174 MiB (0.34 L) of inflow — not measured directly.
6. **Deviations and gaps** — shared host (another node and its stress ran during R2–R5) and loopback 127.0.0.5 / JMX 7205; paths under `~/`; Byteman agent on the node (observation only); 3 aborted R1 attempts not counted (§3); R4's logs rebuilt across the midnight roll. Missed sub-predictions: P1b (instrument race, 4 runs) and R5 P_pool ≥ 0.85 L. The hard cap L itself was not reached on the node; it is covered by the unit tier's Part C here and by the closed `tryAllocate` cases.
7. **Core question** — on a real node, line 128 fired each time the non-flushing memtable bytes passed `(long)(L·t)`, within 8 KiB (parts 3, 2), with t read from the yaml (R2/R4/R5) and L from the yaml (R1/R2/R3); the resulting pool usage including flushing memtables (71.7 → 226.2 → 467.5 MiB) and the live heap of memtables (42.8 → 180.4 → 363.5 MiB) rose with L, and flush count scaled as 1/(t·L) (part 3). The knob caps memtable heap through the soft trigger at L·t, well below L at a 10 k/s inflow.

**Conclusion (cluster, one line):** B3g row 1 (with the R3 positive-control row and the R5 "not exercised" row) — confirmed, two sub-predictions missed.

## 5. Self-check of run 1 — AI

### 5.1 Check of run 1's conclusion

| Part | Holds? | Note (file re-read) |
|---|---|---|
| 1. Validity | yes | re-read each `run1/R<n>/run.log`: threshold line shows 128/512/1024/512/512 MiB; deprecation 0,0,0,1,1; `stress-summary.txt` 3,000,000 partitions, 0 errors; `yaml.diff` shows only the listed edits (+ t in R4/R5) |
| 2. Readings | yes | `bm.txt` R1: the line `used=44874032 recl=44872896 nextClean=89611860` is an example of a stale read (used − recl = 1,136 B ≪ T); counts re-derived with `grep -c` |
| 3. Matched row | yes | recomputed independently with `grep`/`sort`/`awk` (not `analyze.py`): N_flush 101/25/12/56/12; `live:` 0.33×101, 0.33×25, 0.33×12, 0.15×56, 0.66×12; max `usedBefore` 75,156,712 / 237,148,865 / 490,162,356 / 119,849,407 / 393,832,160; base median and live max give P_live 44.9 / 189.1 / 381.1 / 102.7 / 361.6 MB — as in §4.1; the max live sample of each run is inside the stress window (20 samples in-window per run) |
| 4. Excluded rows | yes | each Refuted row checked against the same numbers |
| 5. Observed vs. inferred | yes | (ii) holds from the line values; (i), (iii) remain inferences and do not carry the verdict (P2–P5 are read from O1b, the log and O3 directly) |
| 6. Deviations and gaps | yes | the other agent's node ran concurrently (`ps`, 127.0.0.4); does not touch our pool; rate held at ~10 k/s in every run |
| 7. Core question | yes | the chain trigger (O7 + cleaner log) → flush count → pool usage → live heap follows B1's logic; the hard cap part is stated as not exercised |

Unit tier: re-read `unit-ncb.txt` against B2c's table line by line — all 7 Part A lines, 16 Part B lines and 10 Part C lines as in §4.1.

### 5.2 Run 2?

**No** — 2026-10-22. Both conclusions rest on observed readings; the inferences listed do not carry the verdict; nothing refutes the case or confirms a bypass.

## 6. Run 2

Not done.

## 8. Verdict — AI

**Stage-3 estimate:** positive.

**Claim tested (B1):** in the global memtable pool a flush of the largest memtable is triggered exactly when `allocated − reclaiming` first exceeds `(long)(memtable_heap_space × memtable_cleanup_threshold)`, so memtable heap rises and falls with `memtable_heap_space`; and memtable heap never exceeds `memtable_heap_space` by more than a small bounded overshoot (writers block).

| Tier | Verdict | Effect on the constraint | Basis | Date |
|---|---|---|---|---|
| Unit | **Confirmed** — B2g row 1 (all values exact; strict `>`; trigger ∝ L and t; block at exactly L) | caps | run 1 + self-check | 2026-10-22 |
| Cluster | **Confirmed** — B3g row 1 with the R3 positive-control row; the R5 row "hard cap not exercised on the node" also applies. Missed sub-predictions: P1b (95 % exact; 105/105 self-consistent lines exact, 43 stale reads) and R5 P_pool ≥ 0.85 L (0.73 L, Blocked 0) | caps (through the soft trigger at L·t; L itself not reached) | run 1 + self-check | 2026-10-22 |

**Feedback filed:** the case file's section D (2026-10-22) and the dated audit amendments U1, U2, K1, K3, K4 next to the text they change. Case file sha256 after section D: `6ef2f91f872d02496b7003a52c249e5d1a866428686d9c3a017c9a6828daaf04` (for `_INDEX.md` §4, filled by the orchestrator). Not committed.

**Node state after the run:** no `java` process matching `cassandra-ncl`; `~/stage4-ncl` data, commit log and hints removed (376 KB of configuration left); `~/cassandra-ncl` (443 MB, clean, test file removed) and `~/stage4-logs/ncl` (34 MB) kept.
