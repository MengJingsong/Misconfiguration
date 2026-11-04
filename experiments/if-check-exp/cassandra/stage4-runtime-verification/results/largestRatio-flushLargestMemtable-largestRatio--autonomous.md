# largestRatio-flushLargestMemtable-largestRatio--autonomous — stage-4 results  <!-- file: results/largestRatio-flushLargestMemtable-largestRatio--autonomous.md; the stem ends in --guided or --autonomous -->

> **Case:** [`largestRatio-flushLargestMemtable-largestRatio--autonomous`](../../stage3-ai-deep-read/cases/largestRatio-flushLargestMemtable-largestRatio--autonomous.md)
>
> **Status:** **Closed 2026-10-21 — unit Refuted — does not cap; cluster Confirmed — does not cap** (estimate negative). Line 274 never let accounted memtable usage pass `memtable_heap_space`; that ceiling followed the knob (positive control 3.35–4.26×), and disabling the selection (M-never) only stopped writes at exactly L. The unit tier is Refuted on the claim's "same peak/L" part: at L = 128 MiB, below the cap, the skewed selection held 0.58 L and the even one 0.42 L. Supplementary: the M-first mutant kept the accounted pool ≤ L but filled a 1 GiB test heap (OOM). No run 2.
> 
> **Outcome class:** undetermined — stage-3 estimate vs the stage-4 effect on the constraint
>
> **Agent:** autonomous (the suffix of the case-file stem). For an autonomous
> file, "§9a" below means each tier's predictions and conclusions table: B2f and B2g
> (unit), B3f and B3g (cluster); "§9b–§9e" means B2a–B2e or B3a–B3e; and the case
> file's feedback section is its section D, not §10. One results file per case file.

**Relative links in this template** are written for where a *copy* of it lives
— inside `results/` — not for the template's own location one level up.

**Fill the sections in order.** The audit (§1), run 1 (§4) and the self-check
(§5) are required; run 2 (§6) and the comparison (§7) are filled only if §5.2
chooses run 2. No step waits for a human.
The protocol behind each section is in
[`../README.md`](../README.md#the-run-protocol).

## 1. Before run 1 — design audit and freeze

| Field | Content |
|---|---|
| **Case-file version** | Autonomous file, untracked (repo HEAD `d36d737`). As filed: sha256 `d33bf316c3471b704783e5e2682011f8c69b1b69e88ada1c1c56b1d5c7102c3c`. After the step-0 audit amendments R1–R8: **`60974bb2f52e9e7cf598471e9fcb347e836f3ef1cde9a4fd40b06b64c81e2ab3`** (the audit freeze). After runbook fix D1 (unit, found in the first unit pass; B2f/B2g unchanged): `54e8da0e4277c0946d57ff469a9c15403b51253f6ee47b2f95fa3add0113d03d`, the version the counted unit pass used. After runbook fix D2 (cluster instrument check, before any cluster reading; B3f/B3g unchanged): `45a1ce01d51a0cc1487d368c5465191115ffc8a62efb1b8603f7829f8a6af302`, the version the cluster tier used. After section D (not a frozen version): `91e44954…` (§8). |
| **Harness** | [`harness/largestRatio-flushLargestMemtable-largestRatio--autonomous/`](../harness/largestRatio-flushLargestMemtable-largestRatio--autonomous/README.md), written 2026-10-21, not committed: `FlushLargestSelectionTest.java`, `unit-run.sh`, `unit-analyze.py` (B2); `cluster-run.py`, `cluster-analyze.py`, `Jmx.java` (B3); `diag-first-histo.sh` (supplementary); `selfcheck.py`. **Instrument checks (not readings):** `javac` of the test against the clone; unit shakedown1 (all M-orig methods); cluster shakedown2 (found H3) and shakedown3 (1/20 workload, found D2 and H4). md5 of the run copy: `run1/harness-run.md5`. |
| **Tiers and values** | Unit (B2): U1, U2 at L = 128 MiB; U3 S-skew / S-even at L = 32 and 128 MiB for M-orig and M-first, S-skew at L = 32 MiB for M-never. Cluster (B3): M-orig at L = 256 and 1024 MiB × W-skew / W-even; M-never at L = 256 MiB W-skew (required by R4). |
| **Audit bottom line** | **Ready after amendments** — 2026-10-21 |

### 1.1 Design audit

**On the named constraint (audit note from the orchestrator).** The writer named the local `largestRatio = 0f` (`AbstractAllocatorMemtable.java:251`, compared at `:274`) as "the constraint". It is a running maximum, not a limit: no byte budget is compared against it, and it cannot be set by yaml, `-D` or JMX. The design does test it in the only way a hard-coded value allows (README, "What stage 4 tests"): it varies the operand and the outcome by source mutants (M-never sets the operand to `Float.MAX_VALUE`, so `:274` is never true; M-first changes the comparison) and the outcome by workload (skew vs even), with `memtable_heap_space` as the positive control. So the claim really tests "does line 274's selection change how much memtable memory is held", with `memtable_heap_space` as the binding cap. It does **not** test `memtable_cleanup_threshold` (held at its default 1/3 everywhere) or `memtable_offheap_space` (64 MiB, unused under `heap_buffers`); A1's sentence that these bound memory is untested here (S1).

| Group | Check | Rating (Met / Partly / Not met) | Note (section checked) |
|---|---|---|---|
| A. Core question | constrained quantity is memory or disk bytes | Met | B1: memtable on-heap bytes (pool `allocated`), a fraction of L |
| A. Core question | knob varied, ≥ 3 values incl. default — or another approach, with the reason | Met | A1/B2b: hard-coded, so source mutants (M-orig 0f, M-first, M-never `MAX_VALUE`) and two selection workloads; the reason is given. The cluster tier ran only M-orig as filed (M-never optional), so it would not vary the operand: **R4** makes M-never required. |
| A. Core question | real resource measured, not only the counter (gap named) | Partly | Unit: only the pool counter (gap named in B2d). Cluster: the log's `a`, `AllMemtablesOnHeapDataSize` (live memtables only, so pinned near the cleaning point by construction) and old gen (`jstat`, which cannot attach: R6). |
| A. Core question | usage driven to the limit and past it | Met | U3 writes ≈ 2·L; B3c ≈ 4.6 GiB per run (≥ 13 cleanings); M-never drives to L |
| A. Core question | positive control (negative-estimate file) | Met | `memtable_heap_space` 32 → 128 MiB (unit) and 256 → 1024 MiB (cluster), same workload and instruments |
| B. Logic | each step says what it establishes | Met | B2g/B3g, B2h/B3h |
| B. Logic | prediction stated in numbers or a clear relation | Met | B2f/B3f: ranges, ±0.10, 3–5× |
| B. Logic | every plausible outcome has a conclusions row with its evidence | Partly | B2g's Confirmed row demanded equal `peak/L` for M-orig and M-never, which B2f's own M-never prediction (plateau at L) rules out (**R1**, **R3**). Missing rows: U2 returning true, an M-never arm another flush path released, counter capped but real heap grows, M-never not reaching L (**R3**, **R8**). |
| B. Logic | confirmation needs ceiling-follows-knob and direct disallow evidence | Met | L positive control; M-never plateau with blocked writers; U1's argmax vs actual switch |
| B. Logic | alternative explanations and their controls | Met | B2h/B3h (system tables flushed first, commit log raised, fresh JVM per L, `MEMTABLE_LIMIT` as only flush reason) |
| C. Specific | a human can follow it from the intro and §9a | Met | header, A3, B1 |
| C. Specific | an AI can run §9b–§9e without re-deriving the code path | Partly | U3 row counts, timeout handling and the M-never JVM end were open (**R2**) |
| C. Specific | knob, values, workload, commands, observables, sampling, stop conditions exact | Partly | stress warm-up breaks "same total rows" and unquoted `(` fails in a shell (**R5**); `jstat`/`sjk` period (**R6**); M-never stop and log window (**R7**) |
| D. Runnable | harness and environment prerequisites exist or are listed | Met | everything listed for step 1; paths `/tmp/c509-*` and 127.0.0.1 replaced by `~/cassandra-lrt*`, `~/stage4-lrt`, 127.0.0.4 / JMX 7204 (environment deviation E1) |
| D. Runnable | workload arithmetic reaches the limit (data, time, disk, memory) | Met | ≤ 5.4 GB data + ≤ 1.3 GB commit log per run, wiped between runs (B4); 4 GiB heap ≫ L |
| D. Runnable | load-bearing citations spot-checked against the pinned clone | Met | `AbstractAllocatorMemtable.java:59, 76-84, 160-169, 249-318`; `MemtablePool.java:126-161, 216-240`; `MemtableAllocator.java:140-155, 169-197, 290-296`; `MemtableCleanerThread.java:71-98`; `SlabAllocator.java:51-96`; `ColumnFamilyStore.java:1436-1451`; `TableMetrics.java:504-511`; `Config.java:185-190`; `DatabaseDescriptor.java:586-590, 752-775`; `StressAction.java:104-110`; `jvm-server.options:137`; `jvm11-server.options:63-66`. All as cited. |

| # | Recommendation | Applied? (amendment date and commit, or "left for stage 3") | Why |
|---|---|---|---|
| R1 | "Same `peak/L`" applies to skew vs even under M-orig; for mutants the claim is the ceiling | Applied 2026-10-21 (block after B1), not committed | B1/B2g contradicted B2f: M-never must climb to L (`:310-315`) |
| R2 | Exact U3 workload: 4 tables in both variants, 13,000 × L/32 MiB rows per thread, a thread stops at its first 30-s timeout, force-flush after the window, results to `-Dprobe.out` | Applied 2026-10-21 (block after B2c) | row count, timeouts and JVM end were undefined |
| R3 | B2g rows 3–4 restated per R1; rows added (U2 true; M-never Invalid; counter-only gap); U2 race rule | Applied 2026-10-21 (block after B2g) | outcomes without a row |
| R4 | Cluster M-never required | Applied 2026-10-21 (block before B3c) | otherwise the cluster tier never varies the operand |
| R5 | `no-warmup`, quoted `-col` options, keyspaces created first in W-even | Applied 2026-10-21 (block after B3c) | `StressAction.java:104-110`; `/bin/sh` syntax |
| R6 | One JMX poller per 1 s instead of `sjk` and `jstat`; definitions of the peak and old-gen baseline | Applied 2026-10-21 (block after B3d) | `-XX:+PerfDisableSharedMem`; one JVM per `sjk` call |
| R7 | Log window by byte offsets, M-never 300 s stop, SIGTERM then SIGKILL, disk guard 25 GB | Applied 2026-10-21 (block after B3e) | exact stop conditions on a shared host |
| R8 | B3g rows: M-never Invalid / not reached / counter capped but real heap grows | Applied 2026-10-21 (block after B3g) | outcomes without a row |
| S1 | The named constraint is an argmax accumulator, not a configuration constraint; `memtable_cleanup_threshold` and `memtable_offheap_space` are never varied, so A1's claim that they bound memory is untested | Left for stage 3 (section D) | classification of the `predicted-negative.md` row |
| S2 | `AllMemtablesOnHeapDataSize` counts live memtables only and is pinned near L/3 by the cleaner whatever is selected, so it cannot discriminate selections; `a` is sampled only at selection instants. A pool-occupancy sampler (e.g. a Byteman or JMX hook on `MEMORY_POOL.onHeap.used()`) would make B3f's "peak/L" decisive | Left for stage 3 | instrument weakness; shown by run 1 (§4.2 part 2) |

**Agreement criteria** — not filled (no run 2).

## 2. Environment

| Field | Run 1 | Run 2 (fresh AI session, if done) |
|---|---|---|
| Date | 2026-10-21 (EDT): unit shakedown 22:49; unit attempt 1 22:50–23:18 (not counted, D1); unit counted pass 23:21:33–23:28:08; diagnostic 23:29; cluster shakedowns 23:30–23:33; cluster M-orig 23:33:44–23:48:11; M-never 23:48:28–23:55:58 | not done |
| Node (CloudLab name and type) | `pc07` = `node0.jason92-320876.misconfiguration-pg0.cloudlab.umass.edu` (40 cores, 251 GiB), run locally. **Another stage-4 session shared this host** (another memtable case) and so its CPU and disk. **Environment deviation E1:** node on 127.0.0.4 (listen, rpc, seed; storage 7000, native 9042 on that address), JMX 7204, clones `~/cassandra-lrt` / `~/cassandra-lrt-mut`, data under `~/stage4-lrt/node`, instead of B3a's 127.0.0.1, 7199 and `/tmp/c509-*`. The unit-tier test JVM uses the test yaml's 127.0.0.1:7012 as filed. | — |
| OS and kernel (`uname -r`) | Ubuntu 22.04.2 LTS, `5.15.0-187-generic` | — |
| JDK (`java -version`) | openjdk 11.0.32.1 (2026-08-18) | — |
| Ant (`ant -version`) | 1.10.12 | — |
| Local `cassandra-src` clone commit | `~/cassandra-lrt`: fresh clone of the shared clone, `cassandra-5.0.9` (`b5f2a54210d541339c2e7c17a794195cac0e67c2`), `ant build-test` 1 min 10 s. `~/cassandra-lrt-mut`: a clone of it at the same commit, mutants applied and rebuilt per stage (diffs in `run1/unit/M-*.diff`, `run1/cluster/never/src.diff`; the M-never jar checked with `javap`: `ldc 3.4028235E38f` at the start of `flushLargestMemtable`). | — |
| Case-file commit / harness commit | case file untracked (HEAD `d36d737`); unit pass on `54e8da0e…`, cluster on `45a1ce01…`; harness not committed (md5 in `run1/harness-run.md5`) | — |
| Storage for node data | `~/stage4-lrt/node/` on local `/dev/sda3`, 46–54 GB free during the run (shared); wiped after each arm | — |
| Full logs (path, outside the repo) | `pc07:~/stage4-logs/lrt/` — `run1/unit/<stage>/` (ant log, test log, junit XML, `probe.txt`, `gc.log`), `run1/cluster/<arm>/` (`system.log`, `debug.log`, `gc.log`, `jmx.csv`, `stress-*.out`, `tablestats.txt`, `arm.json`), `run1/selfcheck.txt`; attempt 1 in `run1-attempt1/`; `shakedown1..3/`, `diag-first/` (57 MB in all) | — |

## 3. Runbook defects

| # | Run | Step (§9b–§9e) | Problem | Fix | Decision (date) | Case-file commit with the fix |
|---|---|---|---|---|---|---|
| D1 | run 1, unit attempt 1 | B2c U2 (R3 race rule) | All 3 U2 attempts found background writes (`system.compaction_history`, `sstable_activity(_v2)`, `system_schema`) between the flush and the call, so U2 had no valid attempt. | Up to 20 attempts, each flush-all, 1 s, flush-all; the first attempt with every ratio 0 is the reading. The unit tier restarted from its beginning; attempt 1 kept in `~/stage4-logs/lrt/run1-attempt1/`, not counted. | 2026-10-21, dated fix in the case file | none (not committed) |
| D2 | cluster shakedown3 (instrument check) | B3d (R6) | `G1 Old Gen` `CollectionUsage.used` read 0 under young collections. | Old gen after each collection from `gc.log` (Old + Humongous regions × 16 MiB). B3f/B3g unchanged. | 2026-10-21, dated fix | none |
| H1 | run 1, unit attempt 1 and the counted pass | harness (R2) | The M-never test JVM did not exit after its window, although the forced flush released the writers (the executors terminated); it waited out the 1500 s junit timeout (attempt 1). Its reading was already written. | `unit-run.sh` gives the M-never JVM 240 s; the junit "Timeout occurred" error that follows is expected and recorded. The reading comes from `probe.txt` only (the JVM's log was not flushed). | 2026-10-21, harness only | — |
| H2 | unit attempt 1 and counted pass | harness | A driver thread that hits a non-timeout exception (here `OutOfMemoryError`) dies without stopping the test, so the test passes with fewer rows. | Recorded: `rowsDone` is in every result line; the OOM is read from the ant log. Not changed (it is the reading). | 2026-10-21 | — |
| H3 | cluster shakedown2 | harness | `/bin/sh` has no process substitution (`diff <(…)`). | Diff against a file. | 2026-10-21 | — |
| H4 | cluster shakedown3 | harness | The selection-line regex assumed an owner without spaces (`CFS(Keyspace='ks3', …)`); `OutOfMemory` matched the JVM-arguments line (`-XX:+HeapDumpOnOutOfMemoryError`); `DRAIN` flushes at stop fell inside the parsed log. | Regex fixed; `java.lang.OutOfMemoryError`; log window closed at stress end (R7's offsets). | 2026-10-21 | — |

## 4. Run 1

**Scope:** unit tier B2 (counted pass after D1: M-orig L = 128 all four methods, M-orig L = 32, M-first L = 32 and 128, M-never L = 32) and cluster tier B3 (four M-orig arms, the M-never arm). **Command log:** [`largestRatio-flushLargestMemtable-largestRatio--autonomous/run1/`](largestRatio-flushLargestMemtable-largestRatio--autonomous/run1/) (`unit/cmd-excerpt.log`, `unit/probe-*.txt`, `unit/analysis.txt`, `cluster/session-excerpt.log`, `cluster/<arm>/` with `arm.json`, `flushes.txt`, `jmx.csv`, stress results, `gc-full-excerpt.txt`; `cluster/analysis.txt`; `diag-first/`; `selfcheck.py`, `selfcheck.txt`).

### 4.1 Readings

**Unit tier** (`unit/analysis.txt`: 24 yes, 7 NO)

| Test or assertion | Result | Evidence (file) |
|---|---|---|
| U1 (L = 128 MiB): ratios T1/T2/T3 | 0.01466 / 0.02931 / 0.04397 (6/128 = 0.0469); test argmax T3 | `unit/probe-orig-L128.txt` |
| U1: switched CFS, Future | only T3 switched (+1 sstable); `true`; match = true | same |
| U2: valid attempt | attempt 1 invalid (3 system memtables > 0, returned true for `system.sstable_activity_v2`); attempt 2 all ratios 0 → `false`, nothing switched | same |
| U3 M-orig, peak/L (skew / even) | L = 32: 0.5458 / 0.4985 (diff 0.047). **L = 128: 0.5808 / 0.4174 (diff 0.163)**. No sample over L; `blockedOnAllocating` 0 in all four | `unit/probe-orig-L*.txt` |
| U3 M-orig switches, mean flush | skew 6 switches (7.06 / 28.26 MiB); even 14 (3.04 / 12.10 MiB): 2.33× | same |
| Positive control | peakUsed L128 / L32: skew 74.35 / 17.47 MiB = 4.26×; even 53.42 / 15.95 MiB = 3.35× | same |
| U3 M-first | L = 32: skew 0.5283, even **1.0000** (949 switches, mean 46 KB, `blockedOnAllocating` 2189); L = 128: skew 0.4873, even 0.9550 (515 switches, mean 140 KB) — **this JVM ran out of heap**: 9 `OutOfMemoryError` lines, 149,954 of 208,000 rows written, Full GC 1006 → 987 MiB live in a 1007 MiB heap. Every switch was a test table (all-CFS count = test count) | `unit/probe-first-L*.txt`, `unit/first-L128-oom-excerpt.txt`, `unit/first-L128-gc-full.txt` |
| U3 M-never (L = 32, skew) | peakUsed 33,554,109 B (L − 323 B), 0 switches, all 4 threads timed out after 25,587 rows, `blockedOnAllocating` 0 | `unit/probe-never-L32.txt` |
| Supplementary diagnostic (after run 1): M-first, even, L = 128 alone with a class histogram every 1 s | pool peak 128 MiB (1.0000 L), 1022 switches, mean flush 156 KB, no OOM this time (each histogram is a full GC); live `byte[]` rose 8 → **877 MiB** (snapshot: 919 MB of `byte[]`, 102,175 `BTreeRow`) and fell back to 40 MiB | `diag-first/byte-array-series.txt`, `diag-first/histo-peak-snapshot.txt` |

**Cluster tier** (`cluster/analysis.txt`: 33 yes, 8 NO)

| Capacity value | Run | Observable (§9d) | Reading | Evidence (file) |
|---|---|---|---|---|
| L = 256 | W-skew (M-orig) | `Flushing largest` lines; `a` max / median; `g` median | 66; 0.80 / 0.67; 0.33 | `cluster/L256-skew/flushes.txt` |
| L = 256 | W-even | same | 166; **1.00 / 0.87**; 0.13 | `cluster/L256-even/flushes.txt` |
| L = 1024 | W-skew | same | 16; 0.69 / 0.67; 0.33 | `cluster/L1024-skew/flushes.txt` |
| L = 1024 | W-even | same | 41; **1.00 / 0.86**; 0.13 | `cluster/L1024-even/flushes.txt` |
| all M-orig | — | flush reasons of stress tables in the window | `MEMTABLE_LIMIT` only (66 / 166 / 16 / 41); even/skew 2.52× and 2.56× | `flushes.txt` |
| 256 / 1024 | skew, even | peak `AllMemtablesOnHeapDataSize` | 85.2 MiB (0.333 L), 85.6 (0.334 L); 350.0 (0.342 L), 341.3 (0.333 L) | `cluster/<arm>/jmx.csv` |
| 256 / 1024 | skew, even | `BlockedOnAllocation` count (completed waits) | 1450, 2338; 356, 363 | `jmx.csv` |
| 256 / 1024 | skew, even | stress | 57,026 op/s; 4 × 8.9 k; 66,179; 4 × 14.0 k; 4,000,000 partitions and 0 errors each | `stress-ks*-results.txt` |
| 256 / 1024 | skew, even | old gen after GC (D2), median | 416, 1056; 1472, 1424 MiB. Evacuation failures and Full GCs in three arms; Full-GC live heap 327–343 MiB at 256 (W-even only), 616–1049 MiB at 1024 | `gc-full-excerpt.txt`, `analysis.txt` |
| 256 | M-never W-skew | selections, `MEMTABLE_LIMIT` flushes | 0, 0 | `cluster/never/flushes.txt` |
| 256 | M-never | `AllMemtablesOnHeapDataSize` | 0 → 251 MiB in 9 s, then **256.0 MiB** flat to the end (1.000 L) | `cluster/never/jmx.csv` |
| 256 | M-never | stress | 177,572 writes in the first ≈ 5 s, then 25–39 op/s at ≈ 20 s latency; 10,026 `WriteTimeout` lines; killed at 301 s | `stress-ks1-head.txt`, `stress-ks1-timeouts-excerpt.txt` |
| 256 | M-never | `BlockedOnAllocation`, old gen, OOM | 0 → 0 (no wait ever completed); old gen 320 → 400 MiB after the plateau; no OOM; node needed SIGKILL (drain blocked, as B4 expects) | `jmx.csv`, `analysis.txt`, `session-excerpt.log` |

### 4.2 Conclusion and logic

1. **Validity.**
   - Unit: each JVM read back its L (`L=` in every result line) [observed: `probe-*.txt`]; the mutant diffs were checked before each build [observed: `unit/M-*.diff`, `cmd-excerpt.log`]; U3 wrote ≈ 2·L and every M-orig and M-first run switched memtables (6–949 times), so the cleaning point was reached [observed]. Valid.
   - Cluster: every M-orig arm had 16–166 `MEMTABLE_LIMIT` selections and no other flush reason for the stress tables [observed: `flushes.txt`]; yaml lines as B3a [observed: `yaml-tail.txt`]; 4 GiB G1 heap [observed: `session-excerpt.log`]; M-never ran the mutant jar [observed: `src.diff`; `javap` in §2]. Valid.
2. **Readings.**
   - (a) `a` is sampled only when a selection happens, so its max is not the pool's peak [inferred: B3d says so]. `BlockedOnAllocation` > 0 in **every** M-orig arm (356–2338 completed waits) means a writer found `allocated + size > L` (`MemtablePool.java:156`, `MemtableAllocator.java:186-196`), so the accounted pool touched L in skew too, not only in even [inferred from source plus observed counts]. On the cluster both workloads reach the cap; the `a` difference (max 0.69–0.80 vs 1.00) is a difference at selection instants.
   - (b) `AllMemtablesOnHeapDataSize` counts live memtables only and sits at ≈ L/3 in all four arms because the cleaner switches at L/3 [observed 0.333–0.342 L; inferred why]. It cannot tell selections apart (S2).
   - (c) In the unit tier no M-orig writer ever blocked (`blockedOnAllocating` 0) and the 5-ms sampler is the pool's own `allocated`, so the unit peak difference at L = 128 (0.58 vs 0.42) is a real difference below the cap [observed]. It repeated in three separate JVMs: shakedown 0.545 / 0.398, attempt 1 0.562 / 0.407, counted 0.581 / 0.417 [observed: `~/stage4-logs/lrt/shakedown1`, `run1-attempt1`, `run1`].
   - (d) M-first at L = 128 even: accounted pool ≤ 0.955 L while the 1 GiB JVM ran out of heap [observed]. The diagnostic shows ≈ 0.9 GB of live `byte[]` with ≈ 102 k rows (≈ L of accounted data) [observed]. The cause is most likely the 1 MiB slab regions (`SlabAllocator.java:51`) of ≈ 1000 tiny memtables switched and waiting to flush, each holding a region while owning ≈ 150 KB [inferred: region size × switch count; not traced object by object].
   - (e) The old-gen sub-prediction is noisy: evacuation failures inflate old-region counts after some pauses [observed: `gc-full-excerpt.txt`].
3. **Matched rows.**
   - **Unit — B2g row 4 as amended by R3: "M-orig `peak/L` differs by > 0.10 between S-skew and S-even at the same L → Claim refuted".** At L = 128: 0.5808 vs 0.4174 (0.163). The row's other clause (`peakUsed > L + 1 MiB` under some variant) did **not** occur: every variant stayed ≤ L.
   - **Cluster — B3g row 1: "`a` ≤ ~1.0 and peak/L equal (±0.10) across W-skew/W-even, while `g` and flush counts differ as predicted, and peak scales ~4× with L → Claim confirmed"**, together with **row 2 "M-never plateaus at ≈ L with writes blocked → Confirmed: line 274 governs liveness, not the cap"**. `a` max 1.00 in every arm; peak `AllMemtablesOnHeapDataSize`/L 0.333 vs 0.334 (L = 256) and 0.342 vs 0.333 (L = 1024) — R6's defined peak; `g` 0.33 vs 0.13; flushes 2.52× and 2.56×; peak 4.11× (skew) and 3.99× (even). M-never: 256.0 MiB flat, writes timing out.
4. **Excluded rows.**
   - Unit: row 3 (Confirmed) fails on its M-orig skew/even clause at L = 128. Row "U1 flushed ≠ argmax": match = true. R3 "U2 returns true": the valid attempt returned false. R3 M-never Invalid: 0 switches and 4 timeouts. "Pool never reaches L/3": 6–949 switches. "Positive control does not move": 4.26× and 3.35×. "M-never grows without bound" (Refuted): plateau 323 B under L.
   - Cluster: **Refuted** "Peak/L differs by > 0.10 … or `a` > 1.05": R6's peak differs by ≤ 0.009 and `a` ≤ 1.00; the `a` medians and maxima differ by 0.19–0.31, which B3f predicted ≤ 0.10 (a missed sub-prediction, part 6), but `a` is a selection-instant statistic and the blocking counts show both workloads reached L (part 2a). **Refuted** "M-never grows past 1.05 L or OOM": 1.000 L, no OOM. "No `Flushing largest` lines": 16–166. "Peak does not move with L": 3.99–4.11×. R8 rows: M-never had 0 selections (not Invalid), reached 1.000 L (not "not reached"), old gen +80 MiB after the plateau (not > 1.5 L).
5. **Observed vs. inferred.** The cluster match rests on observed `AllMemtablesOnHeapDataSize`, flush counts, `g` and the M-never plateau; the statement that the skew pool also touched L (2a) is inferred from the blocking counter and the source, and it is what keeps the `a` difference from reading as a refutation. The unit match rests only on observed sampler peaks. The slab-region cause of the M-first heap (2d) is inferred.
6. **Deviations and gaps.**
   - E1 (address, ports, clones, shared host); D1 (unit restart), D2; harness H1–H4.
   - **Missed sub-predictions:** unit — M-first switch counts did not include system tables (all switches were test tables); M-never `blockedOnAllocating` stayed 0 (the timer counts completed waits only, and none completed). Cluster — median `a` in W-even 0.86–0.87 (predicted 0.33–0.7); `a` median/max skew vs even differ by 0.19–0.31 (predicted ≤ 0.10); old-gen baseline L1024 − L256 for skew 1.03 GiB (predicted 0.5 ± 0.3; even 0.36 GiB in range); M-never `BlockedOnAllocation` did not rise (same timer semantics).
   - **Gaps:** the unit tier reads only accounted bytes except where the M-first JVM ran out of heap; the cluster has no direct pool-occupancy sampler (S2). Supplementary M-first diagnostic is outside B2.
7. **Core question.** Line 274 (the `largestRatio` argmax) does not cap memtable memory: in no variant — original, first-non-empty (M-first) or no selection at all (M-never) — did accounted usage pass `memtable_heap_space`, and that ceiling moved with the knob (unit 3.35–4.26×, cluster 3.99–4.11×) [parts 3, 4]. Disabling the selection costs liveness: usage stops at exactly L and writes time out [part 3]. But the selection does change how much is held below the cap: in the unit tier a skewed selection held 0.58 L and an even one 0.42 L at L = 128, which refutes the file's "same peak/L" sub-claim [parts 2c, 3]; on the cluster both workloads ran into the cap, so the same comparison came out equal [parts 2a, 3]. A changed selection (M-first) also let the real heap reach ≈ 7 × L while the counter stayed ≤ L [part 2d].

**Conclusion (one line):** unit B2g row 4 (amended, R3) — **refuted** (the "same peak/L" part; the ceiling part held); cluster B3g rows 1–2 — **confirmed**, with the `a` and old-gen sub-predictions missed.

## 5. Self-check of run 1 — AI

### 5.1 Check of run 1's conclusion

[`run1/selfcheck.py`](largestRatio-flushLargestMemtable-largestRatio--autonomous/run1/selfcheck.py) re-parses the raw files without the analysis scripts' outputs: unit result lines from the ant log (the `System.out` path) compared with `probe.txt`; the GC logs; the cluster `system.log` between `arm.json`'s offsets (not `flushes.txt`), `jmx.csv`, `gc.log` and stress outputs. Output [`run1/selfcheck.txt`](largestRatio-flushLargestMemtable-largestRatio--autonomous/run1/selfcheck.txt): **26 ok, 0 FAIL**.

| Part | Holds? (yes / no) | Note (file re-read) |
|---|---|---|
| 1. Validity | yes | L in every result line; mutant diffs and the `javap` constant; `MEMTABLE_LIMIT`-only flush reasons recomputed from `system.log` |
| 2. Readings | yes | ant-log result lines equal `probe.txt` for 4 of 5 unit JVMs (M-never's log was not flushed: `probe.txt` only, recorded); blocking counts in `jmx.csv` re-read; M-first OOM lines (9) and Full GC 1005 MiB after re-read; diagnostic histogram re-read |
| 3. Matched row | yes | unit skew − even at L = 128 = 0.163 > 0.10, at L = 32 ≤ 0.10; cluster R6 peak/L within 0.10 at both L, PC 3.99/4.11, M-never 256.00 MiB with 0 selections |
| 4. Excluded rows | yes | every variant ≤ L; `a` ≤ 1.02 everywhere; no OOM in any node log |
| 5. Observed vs. inferred | yes | the cluster's reliance on 2a is stated; `a`'s selection-instant nature is in B3d's own text; the blocking condition is `MemtablePool.java:156` / `MemtableAllocator.java:186-196` |
| 6. Deviations and gaps | yes | E1, D1–D2, H1–H4 and all missed sub-predictions listed |
| 7. Core question | yes | follows B1 as amended by R1: ceiling (held, follows L) and same-ratio (failed in the unit tier at L = 128, held on the cluster by R6's peak) |

### 5.2 Run 2?

**No** — decided 2026-10-21. The unit refutation rests on observed sampler peaks and repeated in three separate JVMs (shakedown, attempt 1, counted pass: 0.15–0.16 apart each time), so a by-hand rerun would add little. The cluster's Confirmed rests partly on an inferred statement (2a); a run 2 would be worth it only with a pool-occupancy sampler (S2), which is a design change for stage 3, not a rerun.

## 6. Run 2 — fresh AI session (optional)

Not done (§5.2); §7 left out.

## 8. Verdict — AI

Jingsong may overrule any verdict at any time; record an override here with its
date and reason.

**Stage-3 estimate:** negative (line 274 is an argmax that chooses which memtable to flush; the cap is `memtable_heap_space`).

**Claim tested:** B1 as amended by R1 — with `L = memtable_heap_space` fixed, the peak memtable on-heap footprint stays at or below about L whatever line 274 selects; under the original code it keeps the same `peak/L` for skewed and even selections; mutants change only flush sizes and counts, or write liveness; and the peak moves when L changes. "Confirmed" below means this claim held.

| Tier | Verdict (B2g / B3g row) | Effect on the constraint | Basis | Date |
|---|---|---|---|---|
| Unit | **Refuted** — B2g row 4 as amended (R3): M-orig `peak/L` 0.5808 (skew) vs 0.4174 (even) at L = 128 MiB; at L = 32 0.5458 vs 0.4985. The ceiling part held: no variant above L (M-first 1.0000, M-never L − 323 B); positive control 4.26× / 3.35×; U1 argmax = switched CFS; U2 false | does not cap | run 1 + self-check | 2026-10-21 |
| Cluster | **Confirmed** — B3g rows 1–2: `a` ≤ 1.00; peak `AllMemtablesOnHeapDataSize`/L 0.333 vs 0.334 (256) and 0.342 vs 0.333 (1024); `g` 0.33 vs 0.13; flushes 2.5×; peak 4.11× / 3.99× with L; M-never flat at 256.0 MiB with writes timing out, no OOM. Sub-predictions missed: `a` median/max differ by 0.19–0.31 between skew and even (both workloads blocked on the cap); W-even median `a` 0.86–0.87; skew old-gen difference 1.03 GiB; `BlockedOnAllocation` did not rise in M-never | does not cap | run 1 + self-check | 2026-10-21 |

**Positive control:** `memtable_heap_space` itself. Unit: peak accounted pool 17.47 → 74.35 MiB (skew) and 15.95 → 53.42 MiB (even) from L = 32 to 128 MiB. Cluster: peak `AllMemtablesOnHeapDataSize` 85.2 → 350.0 MiB (skew), 85.6 → 341.3 MiB (even) from 256 to 1024 MiB; Full-GC live heap 327–343 MiB at 256 (W-even; W-skew had no Full GC) vs 616–1049 MiB at 1024.

**Findings beyond the claim (no §9a row):**
1. **A changed selection breaks the real heap while the accounting holds.** M-first (flush the first non-empty memtable) at L = 128 MiB with four tables switched ≈ 500–1000 tiny memtables (mean flush 46–156 KB); the pool stayed ≤ L but the 1 GiB test JVM ran out of heap, and the diagnostic saw ≈ 0.9 GB of live `byte[]`. Most likely each switched memtable holds a 1 MiB slab region (`SlabAllocator.java:51`) that the pool counts only by the bytes used — the "slab region waste" A3 step 6 calls small is not small when memtables are tiny. Under the original selection (largest first) this did not occur.
2. Disabling the selection (M-never) stops writes at exactly L (unit: L − 323 B; cluster: 256.0 MiB) with no flush and no error other than client timeouts; the node then needs SIGKILL because drain blocks.
3. `MemtablePool.blockedOnAllocating` (JMX `BlockedOnAllocation`) is a Timer that counts **completed** waits, so a permanently blocked writer never shows in it.

**Feedback filed:** the case file's section D updated 2026-10-21, after the dated audit amendments R1–R8 and runbook fixes D1–D2 (only those blocks and section D changed; not committed). Section D filed 2026-10-22. New sha256 of the whole case file after section D: `91e44954d85185e2b90992f4cbf1e595660b8bbc73f31ed4b708d8fc35aede67` (not a new frozen version; to be recorded in `_INDEX.md` §4).
