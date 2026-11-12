# commitlog_max_compression_buffers_in_pool-simplecachedbufferpool-bufferpool--autonomous — stage-4 results  <!-- file: results/commitlog_max_compression_buffers_in_pool-simplecachedbufferpool-bufferpool--autonomous.md -->

> **Case:** [`commitlog_max_compression_buffers_in_pool-simplecachedbufferpool-bufferpool--autonomous`](../../stage3-ai-deep-read/cases/commitlog_max_compression_buffers_in_pool-simplecachedbufferpool-bufferpool--autonomous.md)
>
> **Status:** verdict filed (2026-11-11)
>
> **Outcome class:** undetermined (estimate `positive`; unit **Not confirmed (no matching row)**, cluster **Not confirmed (B3g row 4)**; neither tier settles the effect, so no weak class applies)
>
> **Agent:** autonomous (the suffix of the case-file stem). For an autonomous
> file, "§9a" below means each tier's predictions and conclusions table: B2f and B2g
> (unit), B3f and B3g (cluster); "§9b–§9e" means B2a–B2e or B3a–B3e; and the case
> file's feedback section is its section D, not §10. One results file per case file.

Dates: the session date is 2026-11-11 (node-local); log timestamps are UTC (2026-11-12T03:xx).

## Freeze (written before any reading)

- Repository base commit: `f74aade6` (case file untracked there; the coordinator commits it).
- sha256 of the case file as filed: `b0841bfb0865582cd3dbbe1f621cc3c766e4ac13abd485aabcd1a645f72e5aac` (matches `_INDEX.md` §4).
- sha256 of the prediction and conclusions tables as filed (B2f, B2g from `**B2f.` up to `**B2h.`, and B3f, B3g from `**B3f.` up to `**B3h.`, concatenated): `afdd0cfb0fc9c9abdcd4c4c46b08721912f3455b73c58cc6f17a2009c4c6edb5` (copy `run1/freeze-pred-as-filed.txt`). Recorded 2026-11-12T03:24:47Z, before any reading.
- After the audit's amendments M1-M9 (applied before any reading): case-file sha256 `9ef5d9bdafc0a3b90cb13cc06bc589d8b699eedf2e4d7f65466655f9cd00ac6c`; tables hash `af8baf59b26af9804116aba1067e70cc12dd0702352044770aa1d730253f821f` (copy `run1/freeze-pred-amended.txt`). Recorded before any reading.

## 1. Before run 1 — design audit and freeze

| Field | Content |
|---|---|
| **Case-file version** | Repository HEAD `f74aade6` (case file untracked; the coordinator commits it). sha256 after audit amendments M1-M9: `9ef5d9bdafc0a3b90cb13cc06bc589d8b699eedf2e4d7f65466655f9cd00ac6c` (the unit run used this version); after M10 (runbook defect D2, B3a yaml shape; no prediction or conclusion text changed): `d97aac32e463dcf5205930e7752b34a1ee25b562e1195967e3ed0f96c498c262` (the cluster run used this version). The tables hash `af8baf59…f821f` is unchanged from M9 on. Final sha256, with section D filled: `7b3e974e7cd7d0b16ad6e506b7d2b669d6f5ef61d6b5bca1520defd4860a9883`. |
| **Harness** | `harness/commitlog_max_compression_buffers_in_pool-simplecachedbufferpool-bufferpool--autonomous/` (`PoolCapManagerTest.java`, `PoolQueueCapacityTest.java`, `unit-run.sh`, `unit-analyze.py`, `Sampler.java`, `cluster-run.py`, `cluster-analyze.py`, `selfcheck.py`, `README.md`); not committed by this session. |
| **Tiers and values** | Unit (B2): LZ4, 1 MiB segments, sync blocked, N in {3, 5, 8}; class 2 (pool alone) N in {3, 5, 8} plus N = 1. Cluster (B3): one node, Zstd level 19, 64 MiB segments, N in {3, 6, 12, 24}, plus an mmap control (no compression, N = 6). |
| **Audit bottom line** | **Ready after amendments**, 2026-11-11 (M1-M9 before the run; M10 after the first cluster start refused the yaml) |

### 1.1 Design audit

| Group | Check | Rating (Met / Partly / Not met) | Note (section checked) |
|---|---|---|---|
| A. Core question | constrained quantity is memory or disk bytes | Met | A1/A2: a count of buffers, each `commitlog_segment_size` bytes (off-heap for LZ4/Zstd), so the byte size follows. |
| A. Core question | knob varied, ≥ 3 values incl. default — or another approach, with the reason | Met | B2b {3, 5, 8}, B3b {3, 6, 12, 24}; 3 is the default. |
| A. Core question | real resource measured, not only the counter (gap named) | Met | B2d/B3d: the direct `BufferPoolMXBean` and NMT, besides `usedBuffers`/active segments; B3d names `usedBuffers` as unobservable at cluster tier. |
| A. Core question | usage driven to the limit and past it | Partly | Unit: 64 × 256 KiB against N ≤ 8 MiB with sync blocked (met). Cluster: the arithmetic in B3c ignores other bounds on in-flight writes (memtable space, `native_transport_max_threads`); not found by the audit, it showed in the reading at N = 24. |
| B. Logic | each step says what it establishes | Met | B2e/B3e plus B2h/B3h. |
| B. Logic | prediction stated in numbers or a clear relation | Met after M2, M3, M9 | Unit: the direct delta did not count the 2 buffers already in use at `d0` (M2); the waits metric counts only finished waits (M3). Cluster: the idle baseline already holds 2 buffers (M9 bands). |
| B. Logic | every plausible outcome has a conclusions row with its evidence | Met after M4, M9 | Rows: supported, overshoot, not reached, memory gap, queue rows; M4/M9 add "no matching row" and exact thresholds. |
| B. Logic | confirmation needs ceiling-follows-knob and direct disallow evidence | Met after M3 | Unit: writer parked in `awaitAvailableSegment` with `atLimit` true (M3). Cluster: `WaitingOnSegmentAllocation` growth. |
| B. Logic | alternative explanations and their controls | Met | N sweep (other direct users cancel), class 2 positive control, N = 24 demand control, mmap control (B2h/B3h). |
| C. Specific | a human can follow it from the intro and §9a | Met | Estimate line, A3 and B1. |
| C. Specific | an AI can run §9b–§9e without re-deriving the code path | Met | Class 1 is close to code; the cluster commands are given. |
| C. Specific | knob, values, workload, commands, observables, sampling, stop conditions exact | Partly | Paths and ports were for another node (M1, M5); the stress port option was ineffective (M6); the drain had no bound (M8); the analysis windows were not fixed (M9). |
| D. Runnable | harness and environment prerequisites exist or are listed | Met | JDK 11, Ant, `build-test`; the two classes and a sampler are listed as step-1 work. |
| D. Runnable | workload arithmetic reaches the limit (data, time, disk, memory) | Partly | Unit yes. Cluster: see A4 above. Disk and memory fit (heap 4 GiB + direct 3 GiB). |
| D. Runnable | load-bearing citations spot-checked against the pinned source | Met | Checked in 5.0.9: `SimpleCachedBufferPool.java:61, 68-78, 85-96, 117-120, 122-131`; `AbstractCommitLogSegmentManager.java:108, 150-161, 189, 225, 241-244, 296-348, 640`; `CompressedSegment.java:113-118`; `ZstdCompressor.java:208-210` (OFF_HEAP); `Config.java:400-403`; `DatabaseDescriptor.java:898-901`; `CommitLogSegmentBackpressureTest.java`. All as cited. `WaitQueue.java:446-468` (timer stopped on signal or cancel) informed M3. |

| # | Recommendation | Applied? | Why |
|---|---|---|---|
| M1 | Working tree via `copy-source.sh` at `/mydata/jingsong-cass-s4/o44/src`; BMUnit listener on 9491 | applied 2026-11-11 (case file, next to B2a) | shared node; repository rule |
| M2 | Print `u0` at `d0`; direct delta = (N − u0) MiB, tolerance max(±10 %, ±256 KiB) | applied 2026-11-11, before any reading | the commit log is already running at `d0` (`ServerTestUtils.cleanupAndLeaveDirs` → `restartUnsafe`) |
| M3 | `atLimit`, writer stack, `waitsAfter` | applied 2026-11-11, before any reading | the pending wait is not counted until it ends |
| M4 | "no matching row"; row 1 must hold for all three N | applied 2026-11-11 | unambiguous match |
| M5 | Cluster paths, ports 7400/7401/9442/7599, heap and direct memory by env, `native_transport_timeout` 60 s | applied 2026-11-11 | shared node; 5.0.9 `cassandra-env.sh` sets its own MaxDirectMemorySize |
| M6 | Stress `-port native=9442 jmx=7599` instead of `-mode native cql3 port=…` | applied 2026-11-11 (parse check without a server) | as filed, stress used port 9042 |
| M7 | One JMX sampler JVM instead of nodetool sjk per sample | applied 2026-11-11 | same observables, 2 s cadence |
| M8 | Bounded drain/TERM/KILL | applied 2026-11-11 | a drain under Zstd-19 must compress up to N × 64 MiB |
| M9 | Baseline holds 2 buffers: bands (N − 2) × 64 + [0, 160] MiB; windows and thresholds fixed | applied 2026-11-11, before any reading | the filed bands assumed an empty baseline |
| M10 | yaml `parameters` as a list of maps | applied after D2 (no reading existed) | `ParameterizedClass.java:61-65` |
| R-a | Raise the heap or `memtable_heap_space` for N = 24, or replace 24 by a value between 12 and 16 | left for stage 3 | found from the reading (cannot be applied now) |
| R-b | Allow for the writer's direct `DataOutputBuffer` scratch buffer in the unit direct-delta tolerance | left for stage 3 | found from the reading |
| R-c | Replace B3h's absolute NMT agreement by agreement of differences | left for stage 3 | NMT "Other" also holds other `Unsafe` allocations |

## 2. Environment

| Field | Run 1 | Run 2 |
|---|---|---|
| Date | 2026-11-11 (unit 03:31:17-03:32:11Z; cluster 03:34:26-04:04:23Z UTC 2026-11-12) | not done |
| Node (CloudLab name and type) | `node0.jason92-325405` (local node), 32 cores, 125 GiB; shared (other agents' Cassandras on o43 ports and loopback aliases 127.0.0.11-17) | |
| OS and kernel (`uname -r`) | Ubuntu 22.04.2 LTS, 5.15.0-198-generic | |
| JDK (`java -version`) | openjdk 11.0.33 | |
| Ant (`ant -version`) | Apache Ant 1.10.12 | |
| Local source copy | `/mydata/jingsong-cass-s4/o44/src`, `copy-source.sh` copy at repository HEAD `f74aade6` (tag `cassandra-5.0.9`), `ant build-test` | |
| Case-file / harness commit | untracked at `f74aade6` (coordinator commits); sha256 in section 1; harness md5 at the top of `run1/unit-session.log` | |
| Storage for node data | `/mydata` (local LVM volume `/dev/mapper/emulab-node0--bs`, 650 GiB free); node 4 GiB heap, `MaxDirectMemorySize=3G`, NMT summary | |
| Full logs (path, outside the repo) | `/mydata/jingsong-cass-s4/o44/unit/run1/` and `/mydata/jingsong-cass-s4/o44/cluster/run1/` (system/debug logs, yamls, stress logs, incl. a 354 MB `stress-24.log` of client time-outs); failed attempts in `unit/attempt0-compile-fail/` and `cluster/attempt0-yaml-defect/` | |

## 3. Runbook defects

| # | Run | Step | Problem | Fix | Decision (date) | Case-file commit with the fix |
|---|---|---|---|---|---|---|
| D0 | unit, before run 1 | harness | `PoolCapManagerTest.java` missed an import; `ant build-test` failed, no test ran (`run1/unit-attempt0-compile.txt`) | import added; unit run started again | 2026-11-11 | n/a (harness) |
| D1 | unit analysis | harness | `TEST-<class>.log` is appended across `ant testsome` runs, so `unit-analyze.py` read N = 3's lines for every N (`run1/unit-analysis-D1-wrong-selection.txt`) | the analyzer keeps only its own `CAP_N` lines; thresholds unchanged | 2026-11-11 | n/a (harness) |
| D2 | cluster attempt 0 | B3a | yaml `commitlog_compression.parameters` filed as a map; the node dies at start with `ClassCastException: ConcurrentHashMap cannot be cast to List` (`run1/cluster-attempt0-yaml.txt`) | M10: list of maps; cluster tier restarted from its beginning | 2026-11-11 | untracked (amendment M10) |
| D3 | cluster run 1, after N = 12 | harness (B3e.6 stop) | `stop_node()` took the vanished pid file as "stopped"; the N = 12 node was still draining (Zstd-19) and held JMX 7599, so the first N = 24 start failed with "Port already in use: 7599" (read from `start-24.out` at the time; the file was overwritten by the second start; `run1/cluster-session.log` shows `STOP: node died during start`) | killed my N = 12 node (PID 1003493, `kill -9`); `cluster-run.py` now tracks the PID and refuses to start while an o44 node lives; N = 24 and mmap6 were then run in the same run directory. The readings of N = 3, 6, 12 were taken before their stop step, and each later node bound JMX 7599, so no earlier node overlapped a later run's readings. | 2026-11-11 | n/a (harness) |

## 4. Run 1

**Scope:** unit tier as amended (N = 3, 5, 8; class 2 with N = 1); cluster tier as amended (N = 3, 6, 12, 24, mmap6). **Command log:** `run1/unit-session.log`, `run1/cluster-session.log`. Readings: `run1/unit-readings.txt`, `run1/samples-<v>.csv`, `run1/nmt-<v>.txt`, `run1/du-<v>.txt`, `run1/cluster-stress-summary.txt`, `run1/cluster-system-log-excerpt.txt`. Analyzer outputs: `run1/unit-analysis.txt`, `run1/cluster-analysis.txt`. Self-check: `run1/selfcheck.txt`.

### 4.1 Readings

**Unit tier** (`run1/unit-readings.txt`, `run1/unit-analysis.txt`: 34 checks, 33 PASS, 1 FAIL)

| Test or assertion | Result | Evidence (file) |
|---|---|---|
| Config | LZ4, segment 1,048,576 B, maxBuffers = N, mutation 262,195 B; `u0 = 2`, `d0 = 2,886,377` B for every N | `O44 CONFIG`, `O44 BASE` |
| Class 1, N = 3 at 5 s | active 3, usedBuffers 3, atLimit true, direct delta 1,310,771 B (expected 1,048,576 ± 262,144: **FAIL by 51 B**), writer alive and parked in `awaitAvailableSegment`; waitsAfter 20 | `O44 SAMPLE CAP_N=3 t=5s`, `O44 AFTER CAP_N=3` |
| Class 1, N = 5 at 5 s | active 5, usedBuffers 5, atLimit true, direct delta 3,407,923 B (expected 3,145,728 ± 314,572: PASS), writer parked; waitsAfter 17 | `CAP_N=5` lines |
| Class 1, N = 8 at 5 s | active 8, usedBuffers 8, atLimit true, direct delta 6,553,651 B (expected 6,291,456 ± 629,145: PASS), writer parked; waitsAfter 19 | `CAP_N=8` lines |
| Class 1, 3 s vs 5 s | identical in every N (active, used, direct) | `t=3s` / `t=5s` |
| Class 1, direct delta − (N − 2) MiB | 262,195 B in every N (= one serialized mutation) | same |
| Class 2, every N | usedBuffers 10, atLimit true, direct delta 10,485,760 B after creating 10 | `O44 Q … afterCreate` |
| Class 2 idle retained | 4 (N = 3), 8 (N = 5), 8 (N = 8), as predicted; direct after release 4 / 8 / 8 MiB | `retained=`, `afterRelease` |
| Class 2 N = 1 | `java.lang.IllegalArgumentException` | `N1=` |

**Cluster tier** (`run1/cluster-analysis.txt`; MiB = 2^20 B; baseline = median of 15 idle samples; plateau = median of the samples from stress start + 60 s to stress end)

| Capacity value | Run | Observable | Reading | Evidence (file) |
|---|---|---|---|---|
| N = 3 | Zstd-19 | direct MemoryUsed baseline / plateau / net | 206.4 / 343.9 / 137.5 MiB; plateau range 0.1 MiB; peak − baseline 137.5 MiB | `samples-3.csv` |
| N = 3 | | WaitingOnSegmentAllocation Count, stress start → end | +352 (1 → 353) | `samples-3.csv` |
| N = 6 | Zstd-19 | baseline / plateau / net | 206.4 / 536.0 / 329.6 MiB; range 0.3 MiB | `samples-6.csv` |
| N = 6 | | waits | +384 | same |
| N = 12 | Zstd-19 | baseline / plateau / net | 206.4 / 920.0 / 713.6 MiB; range 0.3 MiB | `samples-12.csv` |
| N = 12 | | waits | +192 | same |
| N = 24 | Zstd-19 (positive demand control) | baseline / plateau / net | 206.4 / 1176.1 / 969.7 MiB; range 0.5 MiB; max segment files 17 | `samples-24.csv` |
| N = 24 | | waits | +0 (Count 1 throughout) | same |
| N = 24 | | node state after stress | MutationStage 32 active / 96 pending; Native-Transport-Requests 128 active; client `OperationTimedOutException` (2,952,354 lines) | `cluster-session.log` (tpstats), `cluster-stress-summary.txt` |
| pairwise | | plateau differences | 3→6: 192.0 MiB (1.000 × 192); 6→12: 384.0 MiB (1.000 × 384); 12→24: 256.1 MiB (0.333 × 768) | `cluster-analysis.txt` |
| mmap6 | control | baseline / plateau / net | 78.4 / 87.9 / 9.6 MiB; stress finished 2,000,000 ops | `samples-mmap6.csv`, `cluster-stress-summary.txt` |
| all | | NMT "Other" − MXBean, late stress | 540,689 / 540,690 / 540,576 / 540,691 / 540,700 KB (3 / 6 / 12 / 24 / mmap6); idle about 16 MiB | `nmt-<v>.txt`, `samples-<v>.csv` |
| all | | memtable thresholds | "Global memtable on-heap threshold is enabled at 1024MiB" | `cluster-system-log-excerpt.txt` |

### 4.2 Conclusion and logic

**Unit tier**

1. **Validity.** The limit was reached for every N: active = usedBuffers = N, `atLimit` true, writer parked in `awaitAvailableSegment` [observed: `unit-readings.txt`]. LZ4, 1 MiB segments and N held as set [observed: `O44 CONFIG`]. Valid.
2. **Readings.** Every direct delta exceeds (N − 2) MiB by the same 262,195 B, exactly the serialized mutation size [observed: `unit-readings.txt`]. This is the writer thread's direct `DataOutputBuffer.scratchBuffer`, grown to one mutation and kept [inferred: `CommitLog.java:306-308` serializes into `DataOutputBuffer.scratchBuffer`, which allocates direct by default, `DataOutputBuffer.java:55, 63-90`; the size equality].
3. **Matched row.** None. Row 1 ("active = usedBuffers = N, direct ≈ N MiB, writer blocked, waits ≥ 1"), with "≈" fixed by M2 as (N − u0) MiB ± max(10 %, 256 KiB), holds for N = 5 and 8 in every part. For N = 3 it holds in every part except the direct delta, which misses by 51 B [observed: `unit-analysis.txt`]. M4 requires row 1 for all three N, so no row matches. **Not confirmed (no matching row).**
4. **Excluded rows.** Row 2 (overshoot): active and used never exceed N. Row 3 (not reached): the writer is alive and parked at every N. Row 4 (direct ≫ N MiB): the excess is 0.25 MiB, the same for every N, not a multiple of the buffers. Class-2 rows: retained ≠ N for N = 3 and 5, and usedBuffers = 10, so neither "queue not rounded" nor "pool caps by itself" holds.
5. **Observed vs. inferred.** The identity of the 262,195-B allocation is inferred. The verdict does not depend on it: it depends only on the frozen tolerance.
6. **Deviations and gaps.** Harness faults D0 and D1 (section 3) did not touch readings or thresholds. The plateau is read from two samples (3 s, 5 s), as filed.
7. **Core question.** Usage followed the constraint exactly in this tier. The pool-buffer count stopped at N, and direct memory stepped by 1 MiB per unit of N (2,097,152 B for 3→5, 3,145,728 B for 5→8), while class 2 allocated 10 buffers through the same path without the manager. The frozen row was still not met, because of one non-pool direct buffer that the design did not count.

**Conclusion (one line):** no B2g row matches — **not confirmed** (row 1 met except N = 3's direct delta, over its tolerance by 51 B).

**Cluster tier**

1. **Validity.** Zstd level 19, `commitlog_max_compression_buffers_in_pool` = N, 64 MiB segments, heap 4 GiB and direct 3 GiB were all confirmed in the logs [observed: `cluster-session.log`: `commitlog_compression=ZstdCompressor{compression_level=19}`, `commitlog_max_compression_buffers_in_pool=N`, JVM flags]. The limit was reached for N = 3, 6, 12 (waits grow) but **not for N = 24** (waits +0, net 969.7 MiB < (24 − 2) × 64 = 1408 MiB) [observed: `samples-24.csv`].
2. **Readings.** At N = 24 the node stalled: MutationStage was still 32 active / 96 pending after stress, and the client timed out [observed: `cluster-session.log`, `cluster-stress-summary.txt`]. The plateau equals about 16 buffers (969.7 − 73.5 MiB of non-buffer offset at N = 3 = 896 MiB = 14 × 64, plus the 2 baseline buffers) [inferred: arithmetic from `cluster-analysis.txt`]. This matches the 1024 MiB memtable on-heap threshold (16 × 64 MiB): writes blocked on memtable space before the commit log needed 24 buffers [inferred, not verified: no thread dump was taken].
3. **Matched row.** B3g row 4: "Waits stay 0 and plateau < N × 64 MiB — Limit not reached (sync kept up) — not confirmed". With the M9 definition (waits growth 0 **and** net < (N − 2) × 64 MiB), it holds at N = 24: waits +0, net 969.7 < 1408 MiB [observed]. The row's cause "sync kept up" is not what happened; another bound stopped demand first (2 above). **Not confirmed.**
4. **Excluded rows.** Row 1: requires every N flat, with waits growing and steps within ±15 %. N = 24 has waits +0 and the 12→24 step is 0.333 ×, so it fails. Row 2 (overshoot): peak − baseline ≤ (N + 2) × 64 + 32 MiB at every N (137.5 ≤ 352, 329.7 ≤ 544, 713.7 ≤ 928, 969.8 ≤ 1696). Row 3 (plateau unchanged with N): plateau(24) − plateau(3) = 832.2 MiB ≥ 672 MiB. Row 5 (mmap shows the same N-dependence): mmap net 9.6 MiB < 265.6 MiB.
5. **Observed vs. inferred.** The cause of the N = 24 stall (memtable space) is inferred. The verdict depends only on the observed waits +0 and net 969.7 MiB.
6. **Deviations and gaps.** D2 caused a restart before any reading. D3 meant N = 24 and mmap6 ran in a second invocation into the same directory; the earlier values were unaffected (section 3). The NMT cross-check of B3h ("agree within ~10 %") fails in absolute terms. NMT "Other" exceeds the MXBean by a constant 528 MiB under stress at every value, including mmap: it also counts other `Unsafe` allocations. The cross-N differences agree to < 0.2 MiB [observed: `nmt-<v>.txt`, `samples-<v>.csv`]. The absolute bands of M9 hold for N = 3, 6 and 12 and fail for 24.
7. **Core question.** For N = 3, 6 and 12, commit-log direct memory follows the constraint exactly (steps of 192.0 and 384.0 MiB = ΔN × 64 MiB, flat plateaus, writers waiting on segment allocation), and the mmap control shows the knob has no effect without the pool. N = 24 never reached its limit, so the design's top value, which was also the demand control, could not complete the test, and B3g gives Not confirmed.

**Conclusion (one line):** B3g row 4 (limit not reached at N = 24) — **not confirmed**.

## 5. Self-check of run 1 — AI

### 5.1 Check of run 1's conclusion

| Part | Holds? | Note (file re-read) |
|---|---|---|
| 1. Validity | yes | `cluster-session.log` re-read for the config lines and JVM flags per value; `unit-readings.txt` for CONFIG/BASE. |
| 2. Readings | yes | `selfcheck.txt` (independent re-read): N = 3 direct delta 1,310,771; cluster plateaus 343.8-343.9 / 535.8-536.1 / 919.8-920.1 / 1175.7-1176.2 MiB, waits 1→353 / 1→385 / 1→193 / 1→1. |
| 3. Matched row | yes | Unit: 1,310,771 − 1,048,576 = 262,195 > 262,144 (by 51 B); M4 needs all three N. Cluster: waits 1→1 and net 969.7 < 1408. |
| 4. Excluded rows | yes | Each excluded row was re-checked against `unit-analysis.txt` / `cluster-analysis.txt` numbers. |
| 5. Observed vs. inferred | yes | The two inferred causes (scratch buffer, memtable space) are labelled and not used by the verdict. |
| 6. Deviations and gaps | yes | D0-D3 listed. D3's overlap was checked: N = 12's readings ended at 03:48:56Z, its node was still alive until killed at about 03:51:30Z, and only the first N = 24 start fell in that window. |
| 7. Core question | yes | Both tiers answer "usage followed N where the limit was reached", and both verdicts follow the frozen rows, not that impression. |

### 5.2 Run 2?

**No** (2026-11-11). Neither verdict rests on an inferred statement, and a repeat of the same frozen design would hit the same 51-B miss and the same N = 24 bound. A useful second run needs the design changes R-a and R-b, which only stage 3 can make.

## 6. Run 2 — fresh AI session (optional)

Not done.

## 8. Verdict — AI

**Stage-3 estimate:** positive. **Outcome class:** undetermined. Both tiers are Not confirmed, so neither settles the effect; the weak-class rule needs a unit tier that is Confirmed or Refuted.

**Claim tested:** (B1) With commit-log compression enabled, the number of live commit-log segment buffers never exceeds `commitlog_max_compression_buffers_in_pool` (N), so the memory they occupy is at most N × `commitlog_segment_size` (plus one per-thread compression buffer); when writers outrun sync, they block rather than allocating more.

| Tier | Verdict | Effect on the constraint | Basis | Date |
|---|---|---|---|---|
| Unit | **Not confirmed (no matching row)**: row 1 held in every part for N = 5 and 8, and for N = 3 except the direct delta (+51 B over the frozen ±256 KiB, caused by a non-pool 262,195-B direct buffer) | undetermined (readings: count capped at exactly N; memory +1 MiB per N) | run 1 + self-check | 2026-11-11 |
| Cluster | **Not confirmed**, B3g row 4 (limit not reached at N = 24; another bound, likely memtable space, stopped demand at about 16 buffers) | undetermined (readings: N = 3/6/12 plateaus step by exactly ΔN × 64 MiB with writers waiting) | run 1 + self-check | 2026-11-11 |

**Positive control:** unit class 2 moved: the same pool hands out 10 buffers past every N without the manager. Cluster: the N = 24 run pushed demand to about 16 buffers, beyond the smaller caps, but not to its own cap. The mmap control (no pool) stayed flat (9.6 MiB).

**Why undetermined.** Every value whose limit was reached showed the cap working exactly. The frozen conclusions still do not let either tier be Confirmed: one N = 3 unit cell missed its tolerance by 51 B, and the cluster's top value did not reach its limit. Following the protocol, neither prediction was retuned after the readings.

**Feedback filed:** case file section D (2026-11-11), with audit amendments M1-M9 and the runbook fix M10 next to the text they change; no commit (the coordinator commits). Recommendations R-a to R-c are for stage 3.

**Left on the node:** `/mydata/jingsong-cass-s4/o44/` (source tree `src/` with the two test classes copied into `test/unit/org/apache/cassandra/db/commitlog/`, `unit/`, `cluster/` raw logs incl. a 354 MB stress log, `node/` with the last value's data (mmap control, 9.6 GB), freeze copies), 11 GB in total. No process: no Cassandra, stress, sampler or test JVM of this case is running (checked by `ps -C java` for `o44` after the run).
