# commitlog_max_outstanding_replay_bytes-handlemutation-pendingmutationbytes--autonomous — stage-4 results  <!-- file: results/commitlog_max_outstanding_replay_bytes-handlemutation-pendingmutationbytes--autonomous.md -->

> **Case:** [`commitlog_max_outstanding_replay_bytes-handlemutation-pendingmutationbytes--autonomous`](../../stage3-ai-deep-read/cases/commitlog_max_outstanding_replay_bytes-handlemutation-pendingmutationbytes--autonomous.md)
>
> **Status:** verdict filed (2026-11-11)
>
> **Outcome class:** true positive (estimate `positive`; unit **Confirmed — caps**, cluster **Confirmed — caps**)
>
> **Agent:** autonomous (the suffix of the case-file stem). For an autonomous
> file, "§9a" below means each tier's predictions and conclusions table: B2f and B2g
> (unit), B3f and B3g (cluster); "§9b–§9e" means B2a–B2e or B3a–B3e; and the case
> file's feedback section is its section D, not §10. One results file per case file.

**Relative links in this template** are written for where a *copy* of it lives
— inside `results/` — not for the template's own location one level up.

The protocol behind each section is in
[`../../../stage4-runtime-verification/README.md`](../../../stage4-runtime-verification/README.md#the-run-protocol).

## 1. Before run 1 — design audit and freeze

| Field | Content |
|---|---|
| **Case-file version** | Repository HEAD `f74aade6` (the case file is untracked there; the coordinator commits it). Filing sha256 (`_INDEX.md` §4, checked equal before the audit): `bad45de1c6fdf3cc7db01491139239229c00624d94a1950c8b2edcca5168068a`. sha256 of the whole file after the audit's amendments M1-M5 (section D only, 2026-11-11): `c61fb62927ae4dd640d0bd362da1a08d0bcdf5b54ab5319836748265343f1117` — the version frozen before any reading. After amendment M6 (runbook defect D1, found by the unit-tier instrument shakedown before run 1; section D only, no prediction or conclusion text changed): `c366595c5120b290d9d6c01da9aa1a4ac16fd6772a93bbd4af4d2b7e2b47a6be` — the version run 1 (both tiers) used. The stage-4 feedback paragraph added to section D after the run changes the whole-file hash again: final sha256 `59198efc711ccb78639f84722b70cd68176b6f845829508fec6498de5271b95c`; the table hash is unchanged. sha256 of the frozen prediction and conclusion tables (text of B2f, B2g, B3f, B3g, from `**B2f.` up to `**B2h.` and from `**B3f.` up to `**B3h.`, concatenated, 29 lines; identical before and after M1-M5): `7b5a46ff775408c6e9051ef944e8c0d13b26cfe73e1e332745ccff7836e7ce44`. Frozen 2026-11-12 03:2x UTC, before any reading. A reading that matches no frozen row is "Not confirmed (no matching row)". |
| **Harness** | `harness/commitlog_max_outstanding_replay_bytes-handlemutation-pendingmutationbytes--autonomous/` (files and their checks listed in its README; not committed by this session, the coordinator commits) |
| **Tiers and values** | Unit (B2): `MAX_OUTSTANDING_REPLAY_BYTES` = 1 MiB, 4 MiB, 16 MiB, 1 GiB (positive control); 1000 mutations of about 60 KB; probe initiator with a 5 ms single-thread consumer. Cluster (B3): `-Dcassandra.commitlog_max_outstanding_replay_bytes` = 16 MiB, 64 MiB (default), 256 MiB, 4 GiB (positive control), plus the count-cap control (bytes 4 GiB, count 16); 24000 x 64 KiB replayed from one pristine commit log. |
| **Audit bottom line** | **Ready after amendments** — 2026-11-11 (M1-M5 in the case file's section D) |

### 1.1 Design audit

| Group | Check | Rating (Met / Partly / Not met) | Note (section checked) |
|---|---|---|---|
| A. Core question | constrained quantity is memory or disk bytes | Met | A2: serialized bytes of in-flight replay mutations, standing for the heap held by the deserialized `Mutation` graphs (cell values copied out of the reader's reusable buffer). |
| A. Core question | knob varied, ≥ 3 values incl. default — or another approach, with the reason | Met | B3b: 16 / 64 (default) / 256 MiB / 4 GiB; B2b: 1 / 4 / 16 MiB / 1 GiB (the unit tier does not include the default, the cluster tier does). |
| A. Core question | real resource measured, not only the counter (gap named) | Met | B2d reads the operand itself (`pendingMutationBytes`) and the probe's queued count; B3d reads live `Mutation` instance counts and live heap after a full GC; the gap (`pendingMutationBytes` not visible on the node, `byte[]` mixed with memtable) is named in B3d. |
| A. Core question | usage driven to the limit and past it | Met | Unit: 1000 x 60 KB = 60 MB against 1-16 MiB, with a 5 ms consumer (reader far faster); cluster: 1.5 GiB of replay against 16-256 MiB with a 256 MiB memtable pool and two appliers (M2). The "limit never reached" outcome has rows (B2g row 3, B3g row 3). |
| B. Logic | each step says what it establishes | Met | B2e/B3e steps name their purpose; B2h/B3h name the controls. |
| B. Logic | prediction stated in numbers or a clear relation | Met | B2f: `L − s < peakPending ≤ L + s`, `maxQueued ≤ floor(L/s)+1`; B3f: Mutation count ≤ L/s + 1 (+ small), counts 257 / 1024 / 4093, 4 GiB ≥ 4x the 256 MiB run, heap ≥ 200 MB higher at 256 MiB than 16 MiB. |
| B. Logic | every plausible outcome has a conclusions row with its evidence | Partly | Rows cover confirmed, over the limit (refuted), never reached, control failed, workload void. Missing: "counter capped but heap does not follow" as its own row at cluster tier (the confirmed row requires both, so a split reading matches no row and becomes "Not confirmed (no matching row)"). Not amended (would change B3g). |
| B. Logic | confirmation needs ceiling-follows-knob and direct disallow evidence | Met | Unit: `peakPending` above L in the drained run is the direct evidence that the `while` loop drained (the operand cannot stay ≤ L + s while 1000 x s is read unless the reader blocked); `maxQueued` ≈ L/s. Cluster: the Mutation count plateau at L/s with a much larger unbounded count. |
| B. Logic | alternative explanations and their controls | Met | Count cap: 1000 < 1024 (unit), count = 10^8 (cluster); the positive controls 1 GiB / 4 GiB; count-cap = 16 shows the instrument sees a known binding cap; pristine restore for identical input. |
| C. Specific | a human can follow it from the intro and §9a | Met | Estimate line, A3, B1. |
| C. Specific | an AI can run §9b–§9e without re-deriving the code path | Met | Probe and reflection read are specified (B2d); commands are given (B3e). |
| C. Specific | knob, values, workload, commands, observables, sampling, stop conditions exact | Partly | Exact except: `calls` would also count system mutations (M4); ports and paths for a shared node (M1); sampler form (M5). |
| D. Runnable | harness and environment prerequisites exist or are listed | Partly | Two settings cannot run as written, found from the source before any run: `concurrent_writes: 1` is refused (`DatabaseDescriptor.java:565-567`, M2), and the default cleanup threshold (0.33 x 3072 MiB) flushes the 1.5 GiB load and discards segments (M3). |
| D. Runnable | workload arithmetic reaches the limit (data, time, disk, memory) | Met | Unit 60 MB in a 1 GiB test JVM; cluster 1.5 GiB commit log + 1.5 GiB pristine copy + flushed SSTables on a 1.6 TB disk; node heap 6 GiB + stress client on a node with about 14 GiB free; 4 GiB-limit run holds at most about 1.6 GB backlog + 256 MiB memtable. |
| D. Runnable | load-bearing citations spot-checked against the pinned source | Met | Checked in `systems/cassandra/source` (5.0.9): `CommitLogReplayer.java:75` (field), `:79` (count), `:89` (operand), `:189-195`, `:244-272`, `:290-331` (initiator, `Stage.MUTATION.submit(runnable, serializedSize)`), `:512-531` (add at 517, check at 525-530); `CassandraRelevantProperties.java:114-115`; `CommitLogReader.java:429-478`; `CommitLog.java:516-567` (`resetUnsafe`, `restartUnsafe` → `recoverSegmentsOnDisk`); `RecoveryManagerTest.java:129-195`. All as cited. |

| # | Recommendation | Applied? (amendment date and commit, or "left for stage 3") | Why |
|---|---|---|---|
| M1 | Paths under `/mydata/jingsong-cass-s4/o32/`, ports 7300/7301/7499/9342, separate node tree | applied 2026-11-11 (case file untracked; section D) | shared node |
| M2 | `concurrent_writes: 2` for replay | applied 2026-11-11 | `concurrent_writes: 1` refused at start-up |
| M3 | `memtable_cleanup_threshold: 0.99` | applied 2026-11-11 | the load would flush at about 1 GiB and discard segments |
| M4 | `calls` counts `ReplayProbe` mutations; `callsOther` separately | applied 2026-11-11 | system mutations also reach `handleMutation` |
| M5 | Sampler and stop specified | applied 2026-11-11 | B3e.3's shell loop made exact |
| R-a | Add a cluster row for "Mutation count capped but heap does not rise with L" | left for stage 3 | would change B3g |
| R-b | Unit tier: include the 64 MiB default (it would need more than 1000 x 60 KB to bind) | left for stage 3 | the cluster tier covers the default |

## 2. Environment

| Field | Run 1 | Run 2 (fresh AI session, if done) |
|---|---|---|
| Date | 2026-11-12 UTC (2026-11-11 local): unit shakedowns 03:19-03:21, unit run 03:22-03:23; cluster load 03:25-03:27, replay runs 03:27-03:33 | not done |
| Node (CloudLab name and type) | `apt138` (`node2.jason92-325433.misconfiguration-pg0.apt.emulab.net`), 16 cores, 15 GiB RAM (about 14 GiB available), `/mydata` 1.8 TB (1.6 TB free); shared with OOM-exp | |
| OS and kernel (`uname -r`) | Ubuntu 22.04, `5.15.0-198-generic` | |
| JDK (`java -version`) | openjdk 11.0.33 (2026-10-20) | |
| Ant (`ant -version`) | Apache Ant 1.10.12 | |
| Local source copy | `copy-source.sh /mydata/jingsong-cass-s4/o32-src` on the coordinating machine at repository HEAD `f74aade6` (tag `cassandra-5.0.9`), rsynced to `apt138:/mydata/jingsong-cass-s4/o32/src` (`ant build-test`) | |
| Case-file / harness commit | untracked at HEAD `f74aade6`; sha256 in section 1 | |
| Storage for node data | `/mydata` on apt138 (`/dev/mapper/emulab-node2--bs`, local block store, 1.8 TB); unit: the build tree's `build/test/cassandra`; cluster: `/mydata/jingsong-cass-s4/o32/node` (commit log 1,610,616,832 bytes = 48 x 32 MiB segments after the load) and the pristine copy `.../o32/pristine`, both removed after the run (B4) | |
| Full logs (path, outside the repo) | `apt138:/mydata/jingsong-cass-s4/o32/`: `unit-run1/`, `unit-shakedown/`, `unit-shakedown1-applyUnsafe/`, `cluster/{load,b16m,b64m,b256m,b4g,c16}/` (`session.txt`, `samples.jsonl`, `system.log`, `gc.log`, `cassandra.out`; load: `stress.txt`, `tablestats.txt`), `logs/` (build logs) | |

## 3. Runbook defects

| # | Run | Step (§9b–§9e) | Problem | Fix | Decision (date) | Case-file commit with the fix |
|---|---|---|---|---|---|---|
| A-M2 | audit (no run) | B3a | `concurrent_writes: 1` is refused at start-up (`DatabaseDescriptor.java:565-567`, "concurrent_writes must be at least 2"). | `concurrent_writes: 2` for the replay phase (amendment M2). Prediction and conclusions unchanged. | 2026-11-11, before run 1 | untracked (section D, M2) |
| A-M3 | audit (no run) | B3a / B3c | With the default cleanup threshold 1/(1+2) = 0.33, a 3072 MiB pool flushes at about 1 GiB, below the 1.5 GiB load: segments would be discarded and B3c's "SSTable count 0" check would fail. | `memtable_cleanup_threshold: 0.99` in both phases (amendment M3). | 2026-11-11, before run 1 | untracked (section D, M3) |
| D1 | unit shakedown (L = 1 byte, not a frozen value) | B2c / B2e.1b | `Mutation.applyUnsafe()` is `apply(false)` (`Mutation.java:272-275`, durable writes off): the 1000 workload mutations never reach the commit log, so nothing is replayed (`calls=0`, one 91-byte system mutation; raw log `apt138:/mydata/jingsong-cass-s4/o32/unit-shakedown1-applyUnsafe/`). | Durable `...build().apply()` (amendment M6); shakedown repeated: `calls=1000`, `peakPending = s`, `maxQueued = 1` (`run1/unit-shakedown-o32.txt`). Unit tier then run from its beginning. | 2026-11-11, before run 1 | untracked (section D, M6) |

No step of run 1 failed.

## 4. Run 1

**Scope:** unit tier (B2) as amended, all four limits; cluster tier (B3) as amended (M1-M5): one load, five replay runs from the same pristine commit log (16 MiB, 64 MiB, 256 MiB, 4 GiB with count 10^8; count-cap control 4 GiB with count 16). **Command log:** `run1/unit-session-excerpt.txt`, `run1/cluster-load-session.txt`, `run1/cluster-<run>-session.txt`; raw readings `run1/unit-o32.txt`, `run1/cluster-<run>-samples.jsonl`, `run1/cluster-<run>-system-excerpt.txt`; analyzer output `run1/unit-analysis.txt`, `run1/cluster-analysis.txt`; self-check `run1/selfcheck.txt`; frozen tables `run1/freeze-pred.txt`.

**Analyzer thresholds (operationalisation of the frozen words; no row text changed).** Unit, fixed before the unit run (2026-11-12 03:22 UTC): for L = 1 GiB, "≥ 30 MB" is `peakPending ≥ 30,000,000` and "maxQueued ≫ 280" is `maxQueued ≥ 560`. Cluster, fixed at 03:28 UTC after the unit readings and before any cluster reading: s = 65,600 bytes (B3f); "small slack" = 10 instances (the reader's current mutation, the rebuilt `Mutation` of each of the 2 appliers, system mutations); "count ≈ L/s" = max count in [0.5 L/s, L/s + 1 + 10]; count-cap control "≤ ~17" = ≤ 27; "N ≈ 24,000" = N ≥ 23,500; "small and similar (≪ 257)" = the 4 GiB run's max count < 257. Samples used: those whose `jcmd` started before the `Log replay complete` line.

### 4.1 Readings

**Unit tier** (s = 60,050 bytes, the largest `ReplayProbe` entry; smallest 60,048; `run1/unit-o32.txt`)

| Test or assertion | Result | Evidence (file) |
|---|---|---|
| L = 1 MiB (1,048,576) | peakPending 1,080,900 (= L + 32,324; window (988,526, 1,108,626]); maxQueued 18 (bound floor(L/s)+1 = 18); calls 1000, callsOther 1; replay 5,384 ms | `run1/unit-o32.txt`, `run1/unit-analysis.txt` |
| L = 4 MiB (4,194,304) | peakPending 4,203,500 (= L + 9,196); maxQueued 70 (bound 70); calls 1000, callsOther 3 | same |
| L = 16 MiB (16,777,216) | peakPending 16,814,000 (= L + 36,784; window (16,717,166, 16,837,266]); maxQueued **288** (bound 280; L/s = 279.4); calls 1000, callsOther 12 (largest 256 bytes) | same |
| L = 1 GiB (positive control) | peakPending 58,068,283 (97 percent of the 60.05 MB written), reached at call 1003 of 1004; maxQueued 967; the reader read all entries in 195 ms | same |
| JUnit | 1 test, 0 failures, 0 errors (`assertEquals(1000, calls)` held for every L) | `run1/unit-session-excerpt.txt` |
| Known-answer shakedown, L = 1 byte | peakPending 60,050 = s, maxQueued 1, calls 1000 | `run1/unit-shakedown-o32.txt` |

**Cluster tier** (one node, heap 6 GiB G1, replay phase `memtable_heap_space` 256 MiB, `concurrent_writes` 2; each run replays the same 48 segments; samples every about 2.7 s)

| Capacity value | Run | Observable (B3d) | Reading | Evidence (file) |
|---|---|---|---|---|
| load | load | stress 24000 x 64 KiB; SSTables; commit log | 24,000 partitions, 0 errors; `SSTable count: 0`, memtable 24,000 cells, 1,574,040,000 bytes; commit log 1,610,616,832 bytes (48 segments); sampler check on the idle node: ok, Mutation 0 | `run1/cluster-load-session.txt`, `run1/cluster-load-tablestats.txt`, `run1/cluster-load-stress-excerpt.txt` |
| 16 MiB (L/s = 255.8) | A | max live `Mutation` (= `PartitionUpdate`) count; series | **256**; series 0,0,0,0,256,0,256,256,0,256,0,256,0,256,1,0,0,0 | `run1/cluster-b16m-samples.jsonl` |
| 64 MiB, default (L/s = 1023.0) | B | same | **1024**; 1024 in 10 of 13 samples | `run1/cluster-b64m-samples.jsonl` |
| 256 MiB (L/s = 4092.0) | C | same | **4093**; 4093 in 7 of 15 samples (others 2592, 3665, 0) | `run1/cluster-b256m-samples.jsonl` |
| 4 GiB (positive control) | control | same | **19,933** (4.87 x the 256 MiB run); then 15,866, 11,799, 7,732, 3,665, 0: steps of 4,067 mutations, one 256 MiB memtable's worth | `run1/cluster-b4g-samples.jsonl` |
| count cap 16, bytes 4 GiB | count control | same | **17** in all 11 replay-time samples | `run1/cluster-c16-samples.jsonl` |
| all | | max `GC.heap_info` used (B3f "max used heap") | 16 MiB 470.8 MB; 64 MiB 959.0 MB; 256 MiB 1,155.8 MB; 4 GiB 3,002.1 MB; count 16: 390.1 MB | `run1/cluster-analysis.txt` |
| all | | max histogram total (live heap right after the histogram's full GC) | 388.0 / 489.4 / 894.5 / 2,985.3 / 356.5 MB | same |
| all | | `Log replay complete, N replayed mutations in M ms` | N = 24,048 in every run; M = 40,281 / 35,534 / 32,539 / 34,070 / 34,678 ms | `run1/cluster-<run>-system-excerpt.txt` |
| all | | the knob as the running JVM saw it | `-Dcassandra.commitlog_max_outstanding_replay_bytes` and `_count` in each `system.log` JVM arguments line equal the intended values | same (last line of each excerpt) |
| all | | node health | 0 `^ERROR` lines in every run; the 2 "OutOfMemoryError" hits per log are the JVM options `-XX:+HeapDumpOnOutOfMemoryError` and `-XX:OnOutOfMemoryError=kill` | `run1/selfcheck.txt` |

### 4.2 Conclusion and logic

1. **Validity** — Valid. Unit: every replay handed all 1000 workload mutations to `handleMutation` (`calls=1000`) [observed: `run1/unit-o32.txt`]; the count cap could not bind (1000 < 1024, and the largest maxQueued was 967) [observed]; the consumer was slower than the reader (the 1 GiB control piled up 58 MB in 195 ms) [observed]. Cluster: every run replayed the same 24,048 mutations from the same 48 segments [observed: system excerpts]; nothing was flushed during the load (SSTable count 0) [observed: `run1/cluster-load-tablestats.txt`]; the count cap was 10^8 in the four byte runs and 16 in the control, as the JVM's own argument line shows [observed]; each finite limit was reached (plateaus at 256 / 1024 / 4093) [observed]; the count control shows the instrument sees a known binding cap (17) [observed].
2. **Readings** — Unusual: (a) Unit, 16 MiB: maxQueued 288 is 8 above B2f's bound floor(L/s)+1 = 280, while peakPending is inside its window. In that run 12 small non-workload mutations (≤ 256 bytes) also went through the probe; `maxQueued` counts every probe task, so up to 12 of the queued tasks can be these small entries, which add at most 3 KB to the operand [inferred: the probe counts queued tasks for all keyspaces; per-keyspace queued counts were not recorded]. (b) Cluster: many samples show 0 in-flight mutations (16 MiB: 11 of 18): the backlog empties when the appliers catch up between memtable flushes [inferred: the 4 GiB series drains in steps of exactly one 256 MiB memtable]. (c) `GC.heap_info` used is noisier than the histogram total (64 MiB run: 959 MB used vs 489 MB live), because it includes allocation after the histogram's GC; both rise with L.
3. **Matched row** — Unit, B2g row 1: "peakPending ∈ (L − s, L + s] and maxQueued ≈ L/s for each finite L; 1 GiB run much larger" — peakPending in its window for 1, 4 and 16 MiB (overshoot 9-37 KB, under one 60 KB entry); maxQueued 18 / 70 / 288 against L/s = 17.5 / 69.8 / 279.4 (within 3 percent); 1 GiB: 58.1 MB and 967 queued [observed: `run1/unit-o32.txt`]. Cluster, B3g row 1: "Max Mutation count ≈ L/s (within one + system mutations) for each finite L, unbounded run much larger, heap rises with L" — 256 / 1024 / 4093 against L/s = 255.8 / 1023.0 / 4092.0 (each within one); 4 GiB run 19,933 (4.87 x the 256 MiB run, more than the predicted 4 x); max used heap 470.8 → 959.0 → 1,155.8 → 3,002.1 MB, live heap 388.0 → 489.4 → 894.5 → 2,985.3 MB, the 256 MiB run 685 MB (used) or 506 MB (live) above the 16 MiB run (B3f: ≥ 200 MB) [observed: `run1/cluster-analysis.txt`].
4. **Excluded rows** — Unit row 2 (peakPending > L + s): the largest overshoot is 36,784 bytes < s = 60,050 [observed]. Unit row 3 (limit never reached): every finite peak exceeds L, and the 1 GiB run reached 58 MB [observed]. Unit row 4 (calls ≠ 1000): calls = 1000 in all four [observed]. Cluster row 2 (count > L/s + small slack): the largest excess is 1.0 instance (b256m 4093 vs 4092.0) [observed]. Cluster row 3 (all small): 4 GiB run 19,933 [observed]. Cluster row 4 (count control above ~17): 17 [observed]. Cluster row 5 (N ≪ 24,000): N = 24,048 in all [observed].
5. **Observed vs. inferred** — Inferred: (i) that the unit tier's 8 extra queued tasks at 16 MiB are system mutations (part 2a); it affects only the B2f count bound, not the operand bound; (ii) that live `Mutation` instances during replay are the replay backlog (the node serves no clients during start-up; the count control shows 17 = 16 + 1 exactly, and every byte run sits at floor(L/s) or floor(L/s)+1) [inferred, supported by the control]; (iii) that the heap difference between runs is the backlog: memtable pool and every other setting are the same in all runs, and the live-heap difference divided by the Mutation-count difference is the same in two independent pairs (131,919 bytes per in-flight mutation from the 4 GiB run's drain steps; 132,001 bytes between the 256 MiB and 16 MiB runs) [inferred from `run1/cluster-analysis.txt` numbers].
6. **Deviations and gaps** — (a) Amendments M1-M6 (section 1, section 3); `concurrent_writes` 2 instead of 1 (M2) did not stop the backlog from building (the reader still outran the appliers). (b) Samples are about 2.7 s apart (a histogram with a full GC takes about 0.3-0.7 s, plus `heap_info` and the 2 s sleep), so maxima are sampled, not exact; the plateau values repeat in many samples, so a missed higher value would have to be brief. (c) `pendingMutationBytes` is not observable on the node (named in B3d); the unit tier covers it. (d) Heap per in-flight mutation is about 132 KB, 2.0 x its serialized size (s ≈ 65.6 KB), not "roughly its serialized size" as A2 says: deserialization keeps a copy of the serialized bytes of every mutation under `CACHEABLE_MUTATION_SIZE_LIMIT` (2 MB) (`Mutation.java:490-519`, `cachedSerializations`). This does not change the matched rows (B3f's heap prediction is a lower bound) but A2's heap estimate is off by a factor of 2 for this workload (feedback, section D). (e) The B2f bound on maxQueued is missed by 8 at 16 MiB (part 2a); B2g row 1 asks only "≈ L/s", which holds.
7. **Core question** — Usage followed the constraint, and the constraint caps it. The unit tier shows the check bounds its operand: the replayer's `pendingMutationBytes` peaks within one entry above L for each finite L and reaches the whole 58 MB backlog when L is 1 GiB (parts 3 and 4). The cluster tier shows the real resource follows: the number of deserialized, not-yet-applied replay mutations on the heap plateaus at L/s (256, 1024, 4093) for 16, 64 and 256 MiB, grows to 19,933 when the limit is lifted, and live heap rises with L by about 132 KB per in-flight mutation (parts 3 and 6d), while the count-cap control (17) shows the instrument sees a binding cap.

**Conclusion (one line):** Unit B2g row 1, cluster B3g row 1 — claim confirmed: the byte limit caps the commit-log replay backlog (effect: caps; backlog heap ≈ 2 x L for large mutations, not ≈ L).

## 5. Self-check of run 1 — AI

### 5.1 Check of run 1's conclusion

`harness/.../selfcheck.py` re-parsed the raw files with its own code (unit: the log-format `O32` lines of `run1/unit-session-excerpt.txt`; cluster: samples selected by the sampler's own `complete_after` flag instead of log timestamps, N from the raw `system.log`, the `-D` values from the JVM argument line); output `run1/selfcheck.txt`. It reproduced every cited number: unit peaks, overshoots, maxQueued and calls; cluster max Mutation counts 256 / 1024 / 4093 / 19,933 / 17, max used and live heap, N = 24,048, 0 ERROR lines (the selection differs by one sample in two runs, a sample started before and finished after the log line, with no effect on any maximum).

| Part | Holds? (yes / no) | Note (file re-read) |
|---|---|---|
| 1. Validity | yes | `cluster-load-tablestats.txt` (SSTable count 0), `cluster-load-commitlog-ls.txt` (48 segments), each system excerpt (N = 24,048, `-D` values), `unit-o32.txt` (calls 1000). |
| 2. Readings | yes | The 16 MiB maxQueued (288) and callsOther (12) re-read in `unit-o32.txt`; zero samples in `cluster-b16m-samples.jsonl`. |
| 3. Matched row | yes | Every part of both quoted rows re-derived by `selfcheck.txt`; the cluster plateaus are exactly floor(L/s) or floor(L/s)+1. |
| 4. Excluded rows | yes | Each exclusion cites a number `selfcheck.txt` reproduces. |
| 5. Observed vs. inferred | yes | (ii) is supported by the count control (17); (iii) by two independent pairs agreeing within 0.1 percent and by the source (`Mutation.java:490-519`, re-read). (i) stays inferred and affects only B2f's count bound. |
| 6. Deviations and gaps | yes | The B2f count-bound miss is stated, not hidden; the automatic strict match in `unit-analysis.txt` prints "none" for that reason, and the manual match to B2g row 1 rests on its "≈ L/s" wording. |
| 7. Core question — the steps from reading to answer follow the audited logic | yes | B1 → B2b-B2e / B3b-B3e → B2f / B3f → B2g / B3g row 1, with positive controls (1 GiB, 4 GiB) and the count control moving as required. |

### 5.2 Run 2?

**No** (2026-11-11). Both tiers agree, the cluster numbers sit on floor(L/s) exactly with a large control, and the one soft point (the unit maxQueued bound at 16 MiB) is a prediction detail that does not affect either matched row. The result neither refutes the case nor confirms a bypass.

## 6. Run 2 — fresh AI session (optional)

Not done (section 5.2).

## 7. Comparison — only if run 2 was done

Not applicable.

## 8. Verdict — AI

Jingsong may overrule any verdict at any time; record an override here with its date and reason.

**Stage-3 estimate:** positive. **Outcome class:** true positive (positive, caps): both tiers Confirmed with effect `caps`.

**Claim tested:** (B1) During commit-log replay, the serialized bytes of in-flight replay mutations never exceed `cassandra.commitlog_max_outstanding_replay_bytes` plus one mutation, and the live heap held by not-yet-applied replay `Mutation` objects scales with that setting (≈ limit for large-value mutations) when the count cap is not binding and the apply side is slower than the reader. "Confirmed" below means this claim held.

| Tier | Verdict (§9a row; for an autonomous file, the B2g / B3g row) | Effect on the constraint | Basis | Date |
|---|---|---|---|---|
| Unit | B2g row 1: **Confirmed** — peakPending within (L − s, L + s] for 1, 4, 16 MiB; maxQueued 18 / 70 / 288 ≈ L/s; 1 GiB control 58 MB / 967 queued (B2f's count bound missed by 8 at 16 MiB, section 4.2 part 2a) | caps | run 1 + self-check | 2026-11-11 |
| Cluster | B3g row 1: **Confirmed** — live replay `Mutation` count 256 / 1024 / 4093 = L/s for 16 / 64 / 256 MiB, 19,933 unbounded, 17 under count cap 16; live heap 388 → 489 → 895 → 2,985 MB | caps | run 1 + self-check | 2026-11-11 |

**Positive control:** unit — L = 1 GiB: peakPending 58.1 MB, maxQueued 967; cluster — 4 GiB: 19,933 in-flight mutations and 2,985 MB live heap; the count cap 16 binds at 17.

**Feedback filed:** the case file's section D (amendments M1-M6 and the stage-4 feedback paragraph); no section of the trace was refuted. **Open points for the user:** (1) the unit verdict rests on B2g row 1's "≈ L/s" while B2f's strict bound `maxQueued ≤ floor(L/s)+1` was missed by 8 at 16 MiB (system mutations also queued in the probe; inferred); (2) A2/B1 say the backlog heap is about its serialized size; it is about twice that (132 KB per 65.6 KB mutation) because deserialized mutations keep a cached copy of their serialized bytes (`Mutation.java:490-519`). **Doc note:** the replay backlog's heap is about 2 x `commitlog_max_outstanding_replay_bytes` for mutations under 2 MB, plus whatever the count cap allows; a node whose limit is raised far above the default can hold most of its commit log on the heap during start-up (here 1.3 GB of serialized mutations as about 2.7 GB of live heap). **Leftovers on apt138:** nothing running (checked `ps -eo cmd | grep '[C]assandraDaemon'`: none; no java, stress or sampler process of this run); node data and the pristine copy removed (B4); kept under `/mydata/jingsong-cass-s4/o32/`: working trees `src/` (with the copied probe test) and `node-tree/` (469 MB each), `harness/`, `logs/`, `unit-run1/`, `unit-shakedown/`, `unit-shakedown1-applyUnsafe/`, `cluster/` (15 MB). On the coordinating machine: `/mydata/jingsong-cass-s4/o32-src` (the `copy-source.sh` copy).
