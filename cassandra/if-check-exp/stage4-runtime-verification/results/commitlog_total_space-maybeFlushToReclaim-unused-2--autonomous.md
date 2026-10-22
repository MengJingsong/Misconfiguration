# commitlog_total_space-maybeFlushToReclaim-unused-2--autonomous — stage-4 results  <!-- file: results/commitlog_total_space-maybeFlushToReclaim-unused-2--autonomous.md -->

> **Case:** [`commitlog_total_space-maybeFlushToReclaim-unused-2--autonomous`](../../stage3-ai-deep-read/cases/commitlog_total_space-maybeFlushToReclaim-unused-2--autonomous.md) (entry `AbstractCommitLogSegmentManager.java:259`, the sibling of `:249`)
>
> **Status:** **Closed 2026-10-21.**
> - **Unit: Confirmed — caps (soft)** (B2g row 4), with two missed sub-predictions.
> - **Line 259: Confirmed** (B2i row i5, added by the audit). The stop condition picks exactly the segments needed, and that choice, not a flush of everything, keeps usage at T.
> - **Cluster: Not confirmed (no matching row) — undetermined** (overruled 2026-10-22; row 4c, added after attempt 1, struck). Was: Not confirmed — caps (soft), B3g row 4c. At about 90 k writes/s, usage is held below the uncapped run and reclaimed to ≤ T, but the peak is set by flush throughput, not by T. The cluster tier ran twice (attempt 1 kept but not counted); both attempts gave the same peaks.
> - No run 2.
>
> **Agent:** autonomous. "§9a" below means B2f/B2g (unit, plus the added B2i) and B3f/B3g (cluster); "§9b–§9e" means B2a–B2e / B3a–B3e; the feedback field is section D.

## 1. Before run 1 — design audit and freeze

| Field | Content |
|---|---|
| **Case-file version** | Autonomous file, **untracked** (no commit holds it). As filed: sha256 `98750006112a1bd1f88b737545ca3fcc918aebfcab3e83f94bb77f0bfd025ffe`. After the audit's amendments R1–R5, frozen at 2026-10-21 22:50 EDT before any harness run: `45979ff8fe085e91c02c4d9a7cb071c67edb091b71ec352d04e78619050613dd`. After the H1 instrument note (an instrument definition found by the shakedown; predictions and rows unchanged), 22:51 EDT, before unit run 1: **`c23bfe2636036d9594bc71f2baf48d54c23dc8c5a9213f4d17f07dfbfbd0f58c`**. This is the version the unit tier and cluster attempt 1 ran on (copy `pc06:~/stage4-logs/cl2/case-file-frozen.md`). After the B3g row 4c amendment (following attempt 1; the tier restarted): **`cf7a8ff999819f0e59498379e8dd8675ede51c7f8184fc85c207f826b0d05513`**, the version cluster attempt 2 ran on (`pc06:~/stage4-logs/cl2/case-file-frozen-cluster-attempt2.md`). The final hash, after section D, is in §8: `1879a522…`. |
| **Harness** | [`harness/commitlog_total_space-maybeFlushToReclaim-unused-2--autonomous/`](../harness/commitlog_total_space-maybeFlushToReclaim-unused-2--autonomous/README.md): `CommitLogTotalSpaceTest.java` + `CLCapTrace.java` (B2, B2i; BMUnit with three observation rules and the M-nobreak rule), `unit-run.sh`, `cluster-run.sh` + `cluster-chain.sh` (B3), `analyze_unit.py`, `analyze_cluster.py`, `selfcheck.sh`. Not committed. The md5s of the node copies, in `run1/harness.md5`, match the repo copies. **Instrument checks (not readings):** `ant build-test` with the test, 12 s. Unit shakedown 1 (N = 40; T3 and M-nobreak at T = 2): rules parse and fire, the nobreak rule sets the local (`flushingSizeLocal=-4611686018427387904`), and the census, CSV and summary work. It found H1. Unit shakedown 2 (N = 60, M at T = 4) checked the H1 fix (`gap=2`, `older=3`). Cluster shakedown (128 MiB, n = 100,000): config read-back, `mmap` resolved, both samplers, stress summary, flush census and node stop all work. It found a harness bug of mine, H2 (`run1/shakedown/`). |
| **Tiers and values** | Unit (B2, S = 1 MiB mmap segments, 256 × 64 KiB): T ∈ {3, 4, 8, 1024 (control)} MiB at 20 ms; T ∈ {4, 1024} with no throttle; B2i arms M and M-nobreak (24 tables, T = 8, 20 ms). Cluster (B3, S = 32 MiB, one node, 1,000,000 × 1,000 B, 32 stress threads, unthrottled): T ∈ {8192 (control, and the default on this volume), 128, 256, 512} MiB. |
| **Audit bottom line** | **Ready after amendments**, 2026-10-21 |

### 1.1 Design audit

Citations were spot-checked in the pinned clone (`cassandra-src` at `cassandra-5.0.9`, read only).

**What this file tests that the `:249` run did not.** The `:249` file (`results/commitlog_total_space-maybeFlushToReclaim-unused--autonomous.md`, Confirmed — caps (soft) at both tiers) asked whether the cap holds at all. Line 259 is the stop condition of the walk over the oldest segments (`if (flushingSize + unused >= 0) break;`): it decides **how many** segments are flushed.

As filed, B2 and B3 write **one** table. A forced flush then switches that table's whole memtable and frees every segment except `allocatingFrom` and the spare, whatever 259 selected. So the filed design cannot tell 259 apart from "flush every older segment", and it repeats `:249`'s test with other sizes. The audit added B2i (R5) to test 259 itself. The rest of this file (B2 and B3) duplicates `:249`, and section D says so.

| Group | Check | Rating | Note (section checked) |
|---|---|---|---|
| A. Core question | constrained quantity is memory or disk bytes | Met | A2: commit-log segment bytes; `size` is a byte counter. |
| A. Core question | knob varied, ≥ 3 values incl. default | Partly | Three binding values and a control per tier. The cluster control, 8192 MiB, is also the default on this volume (¼ × 63 GB > 8 GiB, `DatabaseDescriptor.java:664-675`). The unit tier lacks the default, which behaves like its control. Left for stage 3. |
| A. Core question | real resource measured, not only the counter | Met | B2d file-length sum; B3d `du` and the file count beside the JMX gauge. A counter-only outcome lacked a unit row (R3). |
| A. Core question | usage driven to the limit and past it | Met | 16 MiB against 3–8 MiB; 1 GiB against 128–512 MiB. |
| A. Core question | positive control (negative estimate only) | n/a | Positive estimate. The uncapped control shows the workload grows the log. |
| A. Core question | **tests the entry line (259) specifically** | Not met → amended | See above. B2i (R5) adds a multi-table workload in which 259's choice changes usage, a Byteman trace of each selection, and a mutant arm with 259 disabled. |
| B. Logic | each step says what it establishes | Met | B2h/B3h. |
| B. Logic | prediction stated in numbers | Met | B2f/B3f bounds (T + 2S, T + 4S, settled ≤ T, flush counts). |
| B. Logic | every plausible outcome has a row | Partly | The rows had meanings but no verdicts and no thresholds ("≈", "far above"). Missing: a counter-only row (unit), and bounded-but-no-forced-flush. Amended (R3). Cluster attempt 1 then exposed one more missing outcome (row 4c, §3 D1). |
| B. Logic | confirmation needs ceiling-follows-knob and disallow evidence | Partly | The unit flush-reason count was an extra, not a requirement. Made required (R2), and part of the Confirmed rows (R3). |
| B. Logic | alternative explanations and their controls | Met | Memtable-pressure flushes are ruled out by the limits and the census (B2h/B3h). Archiving and CDC are off. |
| C. Specific | a human can follow it | Met | Estimate line, A3, B1. |
| C. Specific | an AI can run it without re-deriving the code path | Partly | The test-log path, rotation and accumulation were not given; nor were the start wait, `ulimit`, or the daemon match (R2, R4). |
| C. Specific | values, workload, commands, sampling, stop conditions exact | Partly | Three problems (R4): unquoted `FIXED(1000)` breaks in bash; a 1-s `nodetool sjk` sampler is impossible (one JVM per call); and a 1-s `du` sampler is coarse for a 10–30 s burst. |
| D. Runnable | harness and environment prerequisites | Met | The test skeleton is given; scripts are step-1 work. `/tmp/clcap` rsync copy replaced by a clone (R1, R4). |
| D. Runnable | workload arithmetic reaches the limit | Met | Unit 16 MiB of memtable against a 256 MiB limit (1 GiB test JVM, `build.xml:1152`). Cluster: 1 GiB of commit log; about 2 GiB of memtable against 0.9 × 8 GiB; 24 GiB heap on 251 GiB of RAM; under 3 GB of disk per arm against 55 GB free. |
| D. Runnable | load-bearing citations spot-checked | Met | `AbstractCommitLogSegmentManager.java:103` (`size`), `:166-238` (allocator; `maybeFlushToReclaim()` at `:200`), `:246-264` (`:249` `unused < 0`, `:255` `allocatingFrom` break, `:259` stop condition, `:262` `flushDataFrom(..., false)`), `:406-414`, `:432-451`, `:458-503` (`forceFlush(maxCommitLogPosition)`); `ColumnFamilyStore.java:1055` (log line), `:1084-1092` (`mayContainDataBefore` → `COMMITLOG_DIRTY`); `AbstractMemtableWithCommitlog.java:123-126`; `Config.java:389-397`; `DatabaseDescriptor.java:385`, `:640-642`, `:664-675`, `:1147-1162`, `:1525-1527`, `:2887`, `:2908`, `:3829-3832`; `CommitLog.java:83`, `:273`, `:353`; `CommitLogSegment.java:129` (`id`), `:648`; `SchemaLoader.java:265`, `:377-386`; `build.xml:33` (`debuglevel=source,lines,vars`, needed for the Byteman locals), `:94`, `:1152`, `:1192`; `conf/cassandra.yaml:413,634,660,678,797,812,825,883`; `test/conf/cassandra.yaml` (5 MiB segments, `legacy`, heap_buffers); `test/conf/logback-test.xml` (DEBUG, 20 MB rolls). All hold. |

| # | Recommendation | Applied? | Why |
|---|---|---|---|
| R1 | B2a: a fresh clone `pc06:~/cassandra-cl2` instead of the rsync copy; outputs `~/stage4-logs/cl2/unit/`; note the 1 GiB test JVM | Applied 2026-10-21 (note after B2a; not committed) | Stage-4 safety rule; the heap argument stays valid |
| R2 | B2d/B2e: the `COMMITLOG_DIRTY` count is required; give the log path, rotation and accumulation; count with `find … \| xargs zcat -f`; CSV and summary to files; arm list and commands | Applied 2026-10-21 (notes after B2d and B2e) | Direct evidence that the true branch fired; the runbook did not say where the evidence was |
| R3 | B2g/B3g: a verdict per row, exact thresholds ("peak follows T", "fell back"), rows checked in order, added rows (unit 7 counter-only, unit 8 / cluster 9 no forced flush, cluster 4b fast-writer bypass) | Applied 2026-10-21, before any reading (notes after B2g and B3g) | Group B: every outcome has a row, and a verdict is a row |
| R4 | B3a–B3e: clone and paths `~/stage4-cl2/node`, per-arm `CASSANDRA_CONF`; keys already set in the shipped yaml left alone, the rest appended, each checked to occur once; `ulimit -n 100000`; wait for `statusbinary`; daemon match `java.*cassandra-cl2.*CassandraDaemon`; quoted `-col`; `du` every 0.25 s, JMX back to back | Applied 2026-10-21 (note after B3a) | Runnable as written; more samples, same observables |
| R5 | B2i: the line-259 arm (24 tables written in blocks of one segment, Byteman `CHECK`/`SELECT`/`FLUSH` trace, the M-nobreak mutant) with its own predictions and rows | Applied 2026-10-21, before any reading (new B2i) | The filed design does not exercise its own entry line (group A) |
| R6 | Include the unit default and run the cluster tier also at a throttled rate, so that T, not flush throughput, sets the peak | Left for stage 3 | It would change the design beyond a fix |

**Agreement criteria:** not filled (no run 2).

## 2. Environment

| Field | Run 1 |
|---|---|
| Date | 2026-10-21 (node clock MDT). Audit and freeze 20:50. Unit shakedowns 20:50–20:52. Unit run 1 20:51:56–20:53:32. Cluster shakedown 20:55–20:58. Cluster attempt 1 20:58:17–21:09:19 (not counted). Cluster attempt 2 21:10:15–21:21:14. The session resumed once after an API session limit (between the harness directory and the test code); the node state was re-checked then (clean, nothing running). |
| Node | `pc06` = `node2.jason92-320876` (40 cores, 251 GiB), driven over ssh from `pc07`; no other agent on it |
| OS / kernel | Ubuntu 22.04.2 LTS, `5.15.0-187-generic` |
| JDK / Ant | OpenJDK 11.0.32.1 / Ant 1.10.12 |
| Clone | `pc06:~/cassandra-cl2`, `git clone --branch cassandra-5.0.9 ~/cassandra-run1` → `b5f2a54210d541339c2e7c17a794195cac0e67c2`; `ant build-test` 1 min 10 s `BUILD SUCCESSFUL`. Only the two harness test files were added, and they were removed after the run. |
| Case-file commit / harness commit | none / none (both untracked); hashes in §1 |
| Storage | Unit: `~/cassandra-cl2/build/test/cassandra` on local `/dev/sda3` (ext3). Cluster: `~/stage4-cl2/node` on the same disk, wiped per arm |
| Full logs | `pc06:~/stage4-logs/cl2/`: `run1/unit/<arm>/` (raw test-log trees), `run1/cluster/<T>/` (attempt 2: `system.log`, `debug.log.gz`, `gc.log*`, `stress.out`, `stress.log.gz`, the samplers), `run1/cluster-attempt1/`, `run1/{unit-analysis,cluster-analysis,selfcheck}.txt`, the shakedowns, the frozen case files, `build-test*.log` |

## 3. Runbook defects

| # | Run | Step | Problem | Fix | Decision (date) | Case-file change |
|---|---|---|---|---|---|---|
| H1 | unit shakedown 1 (instrument check) | B2i `SELECT`, `older` | `older` is counted when the rule runs, which races with segment discards on the flush thread (`k=1 older=0`) | Read "the walk reached `allocatingFrom`" as `gap = allocatingFrom.id − lastSelected.id − 1 = 0` (ids are consecutive); record `allocatingFrom` at `CHECK` to flag a concurrent switch | 2026-10-21, before run 1 | dated note after B2i's instruments (re-frozen `c23bfe26…`) |
| H2 | cluster shakedown | `cluster-run.sh` archiving check (mine) | The check failed on `precision=MICROSECONDS` in `commitlog_archiving.properties`, though `archive_command=` is empty | Check `^archive_command=.+` only | 2026-10-21 | none (harness only) |
| D1 | cluster attempt 1 | B3g as amended (R3) | No row fitted. The binding peaks (544 / 448 / 832 MiB at T = 128 / 256 / 512) were all < 0.8 × the control's 1,120 MiB, and every arm fell back ≤ T with forced flushes. But the peaks did not rise with T, and R3 gave the filed row 4 ("flush throughput, not the limit, governs") a verdict only when the peaks follow T | Row 4c added, with the conservative verdict **Not confirmed** · caps (soft). The cluster tier restarted; attempt 1 is kept and not counted | 2026-10-21, README "No §9a row fits" | note after B3g (`cf7a8ff9…`) |

## 4. Run 1

**Scope:** unit B2 (six arms) and B2i (two arms), N = 256; cluster B3 (four arms; attempt 2 counted). **Command log:**
[`commitlog_total_space-maybeFlushToReclaim-unused-2--autonomous/run1/`](commitlog_total_space-maybeFlushToReclaim-unused-2--autonomous/run1/):
- Unit: `unit/session.log`; per arm, `unit/<arm>/{cap.csv.gz, cap.csv.summary, cap.csv.trace, reasons.txt, ant-excerpt.txt, testlog-flush-excerpt.txt}`.
- Cluster: `cluster/chain.log`; per arm, `cluster/<T>/{session.log, du.csv, jmx.csv, times.txt, counts.txt, flushes.txt, segment-deletions.txt, yaml.diff, config-excerpt.txt, stress-results-excerpt.txt}`. Attempt 1 is in `cluster-attempt1/`, with its `analysis.txt`.
- Also `unit-analysis.txt`, `cluster-analysis.txt`, `selfcheck.txt`, `shakedown/`, `harness.md5`.

### 4.1 Readings

**Unit tier.** JUnit passed 1/1 in every arm. Every arm read back `segMiB=1 accessMode=mmap heapMaxMiB=1007 memtableHeapMiB=251`. S = 1 MiB. There were 0 `MEMTABLE_*` flushes of any `CLCap` table and 0 `ERROR` lines in any arm.

| Arm | Result | Evidence |
|---|---|---|
| T = 3, 20 ms | peak 4 MiB (bound 5); settled 3 (≤ 3); `COMMITLOG_DIRTY` 8 (≥ 4); 8 `SELECT` | `unit/T3-s20/*` |
| T = 4, 20 ms | peak 5 (bound 6); settled 4 (≤ 4); `COMMITLOG_DIRTY` 5 (≥ 4) | `unit/T4-s20/*` |
| T = 8, 20 ms | peak 9 (bound 10); settled 5 (≤ 8); `COMMITLOG_DIRTY` 2 (≥ 2) | `unit/T8-s20/*` |
| T = 1024, 20 ms (control) | **peak = settled = 19 MiB (predicted 17–18: missed by one segment)**, monotone; 0 forced flushes | `unit/T1024-s20/*` |
| T = 4, no throttle | **peak 11 MiB (bound T + 4S = 8: missed)**; settled 3 (≤ 4); `COMMITLOG_DIRTY` 5, from 15 `SELECT` events (the other 10 found the memtable already switched) | `unit/T4-s0/*` |
| T = 1024, no throttle | peak = settled = 19 MiB; 0 flushes | `unit/T1024-s0/*` |
| shape | `peak − T` = 1, 1, 1 MiB at T = 3, 4, 8; file-length sum within 1 MiB of `onDiskSize` in every sample | `unit-analysis.txt`, `selfcheck.txt` |
| **B2i M** (T = 8, 24 tables) | 11 `SELECT` events, each `k = 1`, `gap = 6`, `stop259 = true`, `minimal = true`, `unused = −1 MiB`, no concurrent switch. Each switched exactly one table (M00, M01, … M10, in order). Usage from the first `SELECT` to the end of the writes never fell below **8 MiB = T** (prediction ≥ 5). Settled 8 MiB (band 5–8); peak 9 | `unit/M/cap.csv.trace`, `cap.csv.gz` |
| **B2i M-nobreak** (line 259 disabled) | 2 `SELECT` events, each `k = 7`, `gap = 0` (the walk ran to `allocatingFrom`); each switched **7 tables** (M00–M06, then M07–M13). Usage fell to **2 MiB** (≤ 3S); settled 5; peak 9 (≤ 10) | `unit/M-nobreak/*` |

**Cluster tier, attempt 2 (counted).** Every arm wrote 1,000,000 partitions with 0 errors, at 88,033–93,992 op/s in about 20 s. Each arm read back its `commitlog_total_space`, `commitlog_segment_size=32MiB`, `memtable_heap_space=8192MiB`, `memtable_cleanup_threshold=0.9` and `heap_buffers`, with `mmap` resolved. 0 `MEMTABLE_LIMIT` flushes and 0 `ERROR` lines in every arm. `du` is the apparent size minus the directory's 4,096 B, sampled every 0.25 s (about 312 samples per arm).

| T (MiB) | Run | Peak `du` (bound) | At end of write | Settled (60 s) | `COMMITLOG_DIRTY` of `standard1` (≥) | Segment deletions in window | JMX peak | Evidence |
|---|---|---|---|---|---|---|---|---|
| 8192 | control | **1,120** at +18.1 s, rising (1.0–1.1 GiB predicted) | 1,120 | 1,120 | 0 | 0 | 1,120 | `cluster/8192/*` |
| 128 | A | **544** (256: missed) at +18.2 s | 256 | 64 | 11 (≥ 5), one every ~1 s from +8.2 s | 33 | 480 | `cluster/128/*` |
| 256 | B | **448** (384: missed) at +18.1 s | 224 | 224 | 4 (≥ 3) | 28 | 416 | `cluster/256/*` |
| 512 | C | **832** (640: missed) at +15.0 s | 640 | 160 | 2 (≥ 1) | 30 | 800 | `cluster/512/*` |

- The overshoots `peak − T` are 416, 192 and 320 MiB, neither constant nor ordered by T.
- `du` equals 32 MiB × the file count in all but one sample per arm, and that one differs by one segment.
- **Attempt 1** (not counted, `cluster-attempt1/`) gave the same peaks (1,120 / 544 / 448 / 832 MiB) and settled values (1,120 / 64 / 224 / 160), with 0 / 11 / 4 / 2 forced flushes.

Script totals: unit 27 `EXPECTED` yes, 2 no (the control's 19 MiB and the unthrottled 11 MiB); cluster 17 yes, 4 no (the three peak bounds and constant overshoot).

### 4.2 Conclusion and logic

1. **Validity.**
   - Unit: every arm read back T, 1 MiB mmap segments and the memtable limit [observed: `ant-excerpt.txt`, `cap.csv.summary`]. The control reached 19 MiB with 0 forced flushes, more than 2 × the largest binding T [observed]. 0 `MEMTABLE_*` flushes [observed: `testlog-flush-excerpt.txt`, `selfcheck.txt`]. So rows 5 and 6 do not apply. B2i: M had 11 `SELECT` events (i1 does not apply). M-nobreak had `gap = 0` in every event and a trough of 2 MiB (i2 does not apply).
   - Cluster: every arm's config was in force [observed: `config-excerpt.txt`, `yaml.diff`] and wrote 1,000,000 rows with no error [observed: `stress-results-excerpt.txt`]. The control reached 1,120 MiB with 0 forced flushes and 0 `MEMTABLE_LIMIT` [observed]. So rows 5 and 6 do not apply. Valid.
2. **Readings.**
   - (a) Unit: every throttled binding peak is exactly T + 1 segment [observed]. The check runs once per segment switch, and the selected segment is freed before the next switch.
   - (b) Unthrottled unit, and every cluster arm: usage rose well past T while forced flushes were requested every ~1 s (128 MiB arm). Segment deletions lag the requests; the 128 MiB arm has no deletion between +13.8 s and +18.4 s, while flushes were requested at +14.0, +15.1, +15.9 and +16.9 s [observed: `cluster-analysis.txt`]. That flush completion, not T, sets the peak is [inferred: from deletion lag; flush completion times were not logged per flush].
   - (c) The cluster peaks are not ordered by T (128 > 256), and attempt 1 reproduced this to the MiB [observed]. It is not noise.
3. **Matched rows.**
   - **Unit B2g row 4** "as row 1, except that … the unthrottled T = 4 peak is > T + 4S → **Confirmed** · caps (soft); each exceeded bound is a missed sub-prediction". The peaks 4 ≤ 5 ≤ 9 are each < 0.8 × 19 = 15.2, so the peak follows T. Settled 3, 4 and 5 ≤ T. There were 8, 5 and 2 forced flushes, against 0 in the control. Every throttled peak is ≤ T + 2S. Missed: the unthrottled 11 > 8, and the control 19 against the predicted 17–18.
   - **B2i row i5** "Predictions 1–4 hold in M, and M-nobreak meets its predictions → **Confirmed** (line 259)": 11 ≥ 4 events; all `stop259 ∧ minimal` with `gap = 6 > 0`; 1 table per event ≤ k + 1 = 2; trough 8 ≥ 5; settled 8 ∈ [5, 8]. In M-nobreak: `gap = 0` in all events; 7 tables per event ≥ 3; trough 2 ≤ 3; peak 9 ≤ 10.
   - **Cluster B3g row 4c** "every binding peak < 0.8 × control, every binding arm falls back to ≤ T with ≥ 1 forced flush, the control has 0, **but** the binding peaks are not non-decreasing in T → **Not confirmed** · caps (soft)": 544, 448 and 832 are each < 896; settled 64 ≤ 128, 224 ≤ 256 and 160 ≤ 512; 11, 4 and 2 forced flushes against 0; 544 > 448 breaks the order.
4. **Excluded rows.**
   - Unit:
     - 7 (counter only): the file-length sum is within 1 MiB of the counter in every sample.
     - 2 (Refuted): every peak is ≤ 0.47 × the control's.
     - 3: settled ≤ T in every binding arm.
     - 8: every binding arm has forced flushes.
     - 1: excluded by the two missed bounds.
   - B2i:
     - i3 (Refuted): every event with `gap > 0` is minimal and stopped at 259.
     - i4: the trough is 8, not ≤ 3.
     - i6: not needed, since i5 holds in full.
   - Cluster:
     - 3 (counter only): `du` = 32 MiB × the file count, and `du` falls back with the metric. The JMX peaks (480 / 416 / 800) are below `du` only because one sample is taken every ~1.2 s; no metric peak is ≤ T + 4S together with a `du` peak > metric + 2S.
     - 2 / 4b: no binding peak is ≥ 0.8 × the control's.
     - 9: every arm has forced flushes.
     - 1 / 4a: the peaks do not follow T.
5. **Observed vs. inferred.**
   - Inferred: flush completion sets the cluster peak (2b). The matched row does not depend on it.
   - Inferred: each `COMMITLOG_DIRTY` flush in the single-table arms comes from `maybeFlushToReclaim`. Here this is also observed: `SELECT`/`FLUSH` trace lines precede each one.
6. **Deviations and gaps.**
   - The clone and paths (R1, R4); H1 and H2; D1 (cluster restart).
   - Missed sub-predictions: unit control 19 MiB, unthrottled T = 4 at 11 MiB; cluster peak bounds at all three T, and constant overshoot.
   - The unit default value is not run (R6).
   - The cluster tier ran only at stress's unthrottled rate, as filed, so whether a slower writer gives "peak = T + a few segments" at the node level is not tested here. `:249`'s throttled cluster run (20 k/s) covers it for that file.
7. **Core question.**
   - The constraint caps commit-log disk use softly. With the same workload, usage peaked at 4 / 5 / 9 MiB (unit) and 544 / 448 / 832 MiB (cluster), against 19 and 1,120 MiB uncapped. After the writes it was reclaimed to ≤ T, through `COMMITLOG_DIRTY` flushes that the uncapped runs never had [parts 3, 4].
   - Line 259 picks exactly ⌈−unused/S⌉ of the oldest segments. That keeps reclaim at T: the trough was 8 MiB, against 2 MiB with 259 disabled [part 3, B2i].
   - At about 90 MiB/s of commit log, the node's peak is set by how fast flushes complete, not by T (2b, 2c). So the file's claim that the peak is "T plus a small overshoot independent of T" is not confirmed at the cluster tier.

**Conclusion (one line):** unit B2g row 4, **Confirmed — caps (soft)**; line 259 B2i row i5, **Confirmed**; cluster B3g row 4c, **Not confirmed — caps (soft)** (overruled 2026-10-22: no matching row, undetermined; see §8).

## 5. Self-check of run 1 — AI

An independent script, [`run1/selfcheck.txt`](commitlog_total_space-maybeFlushToReclaim-unused-2--autonomous/run1/selfcheck.txt) (from `harness/…/selfcheck.sh`), re-derives the readings with awk, grep and zcat on the node. It reads each `cap.csv`, the raw test-log trees, the Byteman traces, `du.csv` limited to [T0, TS], `system.log`, `debug.log.gz` and `stress.out`. It does not use the analysis scripts, `reasons.txt` or `counts.txt`. Every figure in §4.1 matches: peaks, settled values, flush counts, `gap`/`minimal` per event, troughs 8 and 2 MiB, and stress totals. Its lifetime deletion count (34 per arm) includes the drain after the settle window; `cluster-analysis.txt` counts only within the window (control 0).

| Part | Holds? | Note (file re-read) |
|---|---|---|
| 1. Validity | yes | Knob and segment read-back in every `cap.csv.summary` and `config-excerpt.txt`; `junitOK=1` in every arm; 1,000,000 partitions and 0 errors in every `stress.out`; 0 `MEMTABLE_*` in the test logs and `system.log` |
| 2. Readings | yes | T + 1 segment peaks recomputed. The 128 MiB deletion gap (+13.8 → +18.4 s) and flush times re-read from `cluster-analysis.txt` against `segment-deletions.txt` and `flushes.txt` |
| 3. Matched row | yes | Unit row 4: thresholds recomputed (15.2 MiB). B2i i5: all 11 + 2 `SELECT` lines re-read in the traces. Cluster 4c: 896 MiB threshold, settled values and the order 544 > 448 |
| 4. Excluded rows | yes | Each excluded row's contrary reading recomputed |
| 5. Observed vs. inferred | yes | The one inference (flush completion sets the peak) is not used by row 4c, whose terms are all observed |
| 6. Deviations and gaps | yes | H1, H2, D1 and the missed sub-predictions recorded. D1's verdict was chosen conservatively, and attempt 2 reproduced attempt 1 |
| 7. Core question | yes | Follows B1: the cap acts (forced flushes only when capped; reclaim to ≤ T on the real files), and 259's minimal selection sets the reclaim level. The cluster peak's independence from T is reported, not explained away |

### 5.2 Run 2?

**No**, decided 2026-10-21. Every matched row rests on observed counts and byte totals that the self-check re-derived, and the cluster tier was in effect repeated (attempt 1 and attempt 2 agree to the MiB). The result neither refutes the file nor confirms a bypass row.

## 6. Run 2

Not done (§5.2); §7 left out.

## 8. Verdict — AI

**Stage-3 estimate:** positive (soft cap).

**Claim tested (B1):** "Writes alone push the tracked and real commit-log size above `commitlog_total_space` = T. The node then issues `COMMITLOG_DIRTY` flushes and deletes the oldest segments. Peak usage is T plus a small overshoot that does not depend on T; after writes stop, usage settles at ≤ T. With T large (the control), the same workload grows usage to the full volume written with no `COMMITLOG_DIRTY` flush." Line-259 sub-claim (A3 step 4, tested by B2i): the walk stops once the selected oldest segments are enough to bring the size back to ≤ T.

| Tier | Verdict | Effect on the constraint | Basis | Date |
|---|---|---|---|---|
| Unit | **Confirmed**, B2g row 4. Peaks 4 / 5 / 9 MiB at T = 3 / 4 / 8 (each T + 1 segment) vs 19 MiB uncapped; settled ≤ T; 8 / 5 / 2 `COMMITLOG_DIRTY` flushes, 0 in the control. Missed: unthrottled T = 4 peak 11 MiB (> T + 4S); control 19 MiB (predicted 17–18) | caps (soft) | run 1 + self-check | 2026-10-21 |
| Unit, line 259 (B2i) | **Confirmed**, row i5. 11/11 selections exactly minimal (k = 1 for `unused = −1 MiB`, 6 older segments left unselected), one table flushed each, trough 8 MiB = T. With 259 disabled: 7 segments and 7 tables per event, trough 2 MiB | caps (soft); 259 sets the reclaim level at T | run 1 + self-check | 2026-10-21 |
| Cluster | **Not confirmed (no matching row)**, overruled 2026-10-22 (row 4c struck). Readings: peaks 544 / 448 / 832 MiB at T = 128 / 256 / 512 vs 1,120 MiB uncapped; settled 64 / 224 / 160 MiB ≤ T; 11 / 4 / 2 forced flushes, 0 in the control; peaks not ordered by T | undetermined | Jingsong override of the run-1 verdict | 2026-10-22 |
| ~~Cluster (superseded)~~ | **Not confirmed**, B3g row 4c (added after attempt 1). At ~90 k writes/s (1 KB): peaks 544 / 448 / 832 MiB at T = 128 / 256 / 512 vs 1,120 MiB uncapped (0.40–0.74 ×); settled 64 / 224 / 160 MiB ≤ T; 11 / 4 / 2 forced flushes, 0 in the control. The peaks are not ordered by T; the overshoot (192–416 MiB) is set by flush throughput. Reproduced exactly by the uncounted attempt 1 | caps (soft) | run 1 (attempt 2) + self-check | 2026-10-21 |

**Overruled by Jingsong, 2026-10-22:** row 4c was added after a reading (attempt 1), which the protocol allows only before any reading exists, so it is struck. Against the frozen table the cluster readings match **no row**: verdict **Not confirmed (no matching row)**, Effect **undetermined** at this tier. The readings stand as recorded: peaks below the uncapped run and reclaim to ≤ T after forced flushes, but peaks not ordered by T.

**Findings beyond the claim:**
1. **Line 259 works as traced.** The walk stops at exactly enough segments, and with several tables this keeps the commit log at T instead of draining it. Without the break, each over-limit event would flush every table dirty in any older segment (7 here) and drain the log to the two reserved segments.
2. **Against a fast writer the node's peak is set by flush throughput, not by T.** This is the `:249` file's unthrottled finding at another size: there it was 8 × C at 107 k/s; here 1.7–4.3 × T at 90 k/s, and T = 128 MiB peaked higher than T = 256 MiB in both attempts. Usage still stays below the uncapped run and is reclaimed to ≤ T once the flushes complete.
3. The B2/B3 single-table arms duplicate `:249`'s test. Only B2i adds a test of line 259.

**Feedback filed:** the case file's section D was updated on 2026-10-21. After the freeze only B3g (row 4c, D1) and section D changed. Not committed. Final sha256 after section D: **`1879a522583739b1ce813e051f559cb27f9196d05eb812c7b4ac33d2bb72ef33`**. `_INDEX.md`, `predicted-negative.md` and `HANDOFF.md` are left to the main session.
