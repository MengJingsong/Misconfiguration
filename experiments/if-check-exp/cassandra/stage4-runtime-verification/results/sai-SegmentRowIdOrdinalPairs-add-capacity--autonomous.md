# sai-SegmentRowIdOrdinalPairs-add-capacity--autonomous — stage-4 results  <!-- file: results/sai-SegmentRowIdOrdinalPairs-add-capacity--autonomous.md -->

> **Case:** [`sai-SegmentRowIdOrdinalPairs-add-capacity--autonomous`](../../stage3-ai-deep-read/cases/sai-SegmentRowIdOrdinalPairs-add-capacity--autonomous.md)
>
> **Status:** verdict filed (run 1 + self-check, 2026-10-26)
>
> **Outcome class:** true negative (estimate `negative`, effect `does not cap`; both tiers agree)
>
> **Agent:** autonomous. "§9a" below means B2f and B2g (unit), B3f and B3g (cluster); "§9b–§9e" means B2a–B2e or B3a–B3e; the case file's feedback section is its section D.

## 1. Before run 1 — design audit and freeze

| Field | Content |
|---|---|
| **Case-file version** | Repository HEAD `1ae567d` plus uncommitted changes (the orchestrator commits). sha256 of the whole file **before** the audit: `89fde0ca6817982e94e59945e96a18d75cf330f8bfe3b16dde627682d5597286`; **after the audit's amendments (the frozen version): `111fa2c71b517e05d2cbc45a5c5229c188c269f102687a8a9710fcddd566912b`**; **final sha256 after the later, table-neutral amendments (heap 12g to 16g after the first unit readings; correction of the threshold note after the first cluster readings; section D feedback): `bef23f61eee16264a942c81454ac5b978025d098ddcebecb05d0d710181ddabb`**. The frozen tables hash is unchanged in the final file. Frozen prediction/conclusion tables (the text from `**B2f.` up to `**B2h.` plus `**B3f.` up to `**B3h.`, 35 lines, extracted with `sed -n '/^\*\*B2f\./,/^\*\*B2h\./p'` and the B3 equivalent, last line of each dropped): sha256 `c6394bccda812a569742d722bcefcdcee9b4bda9acf3423a4c28ab45531d689b`, computed 2026-10-26 before any reading. |
| **Harness** | `harness/sai-SegmentRowIdOrdinalPairs-add-capacity--autonomous/`: `SrMem.java`, `unit-run.sh`, `SrHelper.java`, `sr.btm`, `make-node-yaml.sh`, `driver.py`, `srdata.py`, `load.py`, `query.py`, `cluster-run.py`, `instrument-check.sh`. Not yet committed (orchestrator). md5 list in `sr/run1/harness.md5`. |
| **Tiers and values** | Unit: N = 1, 1000, 16000, 100000, 10^6, 10^7, 10^8 (x3 reps; `pairs` and plain `int[2N]`), a no-compressed-oops sweep, boundaries 2^30-2, 2^30-1, 2^30 with `-ea` and `-da`. Cluster: `max_materialized_keys` = 16000 (default), 1000, 64000 x M = 500, 10000, 20000, 50000 (hybrid, LIMIT 10), token-range queries of 100, 1000, 5000, 30000 rows (LIMIT 100) and 30000 rows (LIMIT 10) at the default, plus the unflushed-memtable control. |
| **Audit bottom line** | Ready after amendments — 2026-10-26 |

### 1.1 Design audit

| Group | Check | Rating | Note (section checked) |
|---|---|---|---|
| A. Core question | constrained quantity is memory or disk bytes | Met | A2/B1: heap bytes of one `int[2N]` (16 + 8N). |
| A. Core question | knob varied, ≥ 3 values incl. default — or another approach, with the reason | Met | The class has no knob (A1): the varied quantity is the caller's count N (unit, 11 values) and the upstream gate `max_materialized_keys` x match count M (cluster, 3 x 4 values incl. default 16000). |
| A. Core question | real resource measured, not only the counter (gap named) | Partly | Unit: thread allocated bytes + retained heap. Cluster: B3d relied on JFR allocation events, which cannot see 4–400 KB arrays (in-TLAB objects are not reported per object). **Not applied to the case file as a change to §9a (instrument only):** the harness measures the constructor's allocation with `ThreadMXBean.getThreadAllocatedBytes` read by a Byteman rule (entry/exit) and keeps JFR as a supplementary count; the deviation is recorded in §4.2 part 6. |
| A. Core question | usage driven to the limit and past it | Met | Unit up to 10^8 and the int-overflow boundary; cluster M below and above each `max_materialized_keys` value. |
| B. Logic | each step says what it establishes | Met | B1, B2e, B3e. |
| B. Logic | prediction stated in numbers or a clear relation | Met (amended) | B2f said "within 24 bytes" without saying whether the 24-byte object is counted; amended to delta - (16+8N) in [0, 24]. |
| B. Logic | every plausible outcome has a conclusions row with its evidence | Met | B2g, B3g. |
| B. Logic | confirmation needs ceiling-follows-knob and direct disallow evidence | Met | Claim is negative: B3g needs size = 16+8x(traced count) moving with M and L, plus the control cell moving. The "disallow" is the fallback message in the trace (cells with M > L). |
| B. Logic | alternative explanations and their controls | Met | B2h, B3h (plain `int[2N]`, memtable control, only-one-knob-at-a-time). The "baseline other int[] allocation" control is replaced by the Byteman rule being specific to the constructor (deviation, §4.2). |
| C. Specific | a human can follow it from the intro and §9a alone | Met | |
| C. Specific | an AI can run §9b–§9e without re-deriving the code path | Partly | The case gave no JFR settings file and no load/query scripts; supplied by the harness. |
| C. Specific | knob, values, workload, commands, observables, sampling, stop conditions exact | Partly | Fixed by amendments: 60,000 rows did not equal 500+10000+20000+50000 = 80,500; boundary values at 2^30 were wrong (below). |
| D. Runnable | harness and environment prerequisites exist or are listed | Met (with harness) | Written for this run (see §1 Harness). |
| D. Runnable | workload arithmetic reaches the limit (data, time, disk, memory) | Met (amended) | 80,500 rows x 16 floats: tens of MB. Unit 10^8: 800 MB array; run with `-Xmx6g` (queue at 10^8 needs more than 2 GB). 2^30-2: 8,589,934,576 B, `-Xmx12g`; node has 251 GiB. |
| D. Runnable | load-bearing citations spot-checked against the pinned source | Met after corrections | Details below. |

**Citation and arithmetic findings (checked against `cassandra/cassandra-5.0.9/`).**
- Verified exact: `SegmentRowIdOrdinalPairs.java` `:33` field, `:40-46` constructor (`:42` assert, `:45` `new int[capacity * 2]`), `:53-60` `add` (`:55` check, `:56` throw), `:103,116` queue construction; `VectorIndexSegmentSearcher.java` `:155,156,161,164` (path 1), `:284,288-291,299,307-312` (path 2), `:353-365` with factor `:363` and return `:364`; `IndexWriterConfig.java:39` (16) and `:57`; `StorageAttachedIndex.java:503-504`; `CassandraRelevantProperties.java:476,479`; `QueryController.java:96,441,449-453`; `V1SSTableIndex.java:189-194`; `SegmentBuilder.java:46`; `V1OnDiskFormat.java:126`; `StorageAttachedIndexOptions.java:26,35` (default 1024 MiB).
- Minor cite slips left as filed (not load-bearing): `FORCE_BRUTE_FORCE_ANN` is `:74-77` (annotation at 76, field at 77); `BruteForceRowIdIterator` fields are `:58-59`, constructor `:76-77` (the case cites `:59,77`).
- **Wrong, amended 2026-10-26 (does not depend on any reading):** (1) A1 said `-ea` is not on by default and was unverified: `conf/jvm-server.options:109` has `-ea`, so the `:42` assert is active on a stock node. (2) `Integer.MAX_VALUE / 2` is 1073741823 = 2^30-1 and the assert is a strict `<`, so the largest accepted capacity is 2^30-2, not "1073741823 pairs"; B2e/B2f expected N = 2^30-1 with `-ea` to pass the assert and then need 8.6 GB. It trips the assert instead. (3) With `-da`, N = 2^30-1 gives array length 2^31-2, which HotSpot rejects for any heap (`Requested array size exceeds VM limit`, tried on this JDK with a bare `new int[Integer.MAX_VALUE-1]`: also fails with 12 GB heap, while MAX_INT-2 and below allocate with 12 GB); the largest allocatable is N = 2^30-2 (8,589,934,576 bytes). (4) Load of 60,000 rows is inconsistent with the stated M groups (sum 80,500): amended. (5) The "within 24 bytes" tolerance: made explicit.
- Arithmetic re-done and correct: 16 + 8N for N = 16000 (128,016), 10^7 (80,000,016), 10^8 (800,000,016); hybrid M = 500 / 10000 / 20000 / 50000 gives 4,016 / 80,016 / 160,016 / 400,016 bytes; default `maxBruteForceRows` uses factor 0.25 x 16 = 4 x `expectedNodesVisited` (my own recomputation with graph size 80,500: threshold 322,000 for ranges up to 10,000 rows, 80,364 (LIMIT 100) and 180,820 (LIMIT 1000) for 30,000 rows, 20,088 (LIMIT 10) for 30,000 rows; **wrong**, see §4.2 part 6: the real thresholds were 236,240 to 5.8 million because my calculation omitted the observed-ratio factor, so the added non-brute-force arm did not materialise; prediction rows unchanged).
- Trigger check: path 2 is reached from `QueryController.getTopKRows` (`:392`, `:406-408`) only when `materializeKeysAndCloseSource` returns a list (≤ L keys); `null` takes `getTopKRows(queryExpressionView)` with the full ring, `searchInternalUnrestricted`, which does not construct the class. Path 1 needs a key range that does not cover the ring and does not cover the segment (the early returns in `searchInternal`, before `:155`).

| # | Recommendation | Applied? | Why |
|---|---|---|---|
| 1 | A1: `-ea` is on by default; max capacity 2^30-2 | Applied 2026-10-26 (A1) | source |
| 2 | B2b/B2e/B2f: boundary values and expectations at 2^30-2, 2^30-1, 2^30 (`-ea` / `-da`); `-Xmx12g` for 2^30-2 | Applied 2026-10-26 | JVM array limit + strict `<` |
| 3 | B2f tolerance: delta - (16+8N) in [0, 24] | Applied 2026-10-26 | object is 24 B |
| 4 | B3c/B3e/B4: 80,500 rows | Applied 2026-10-26 | 500+10000+20000+50000 |
| 5 | B3c: added 30,000-row range at LIMIT 10 (non-brute-force arm) | Applied 2026-10-26 (note only) | my recomputation of the threshold |
| 6 | B3d: JFR cannot resolve 4–400 KB in-TLAB arrays; use a Byteman rule + `getThreadAllocatedBytes` | Harness only (deviation recorded) | instrument |
| 7 | Cite slips `FORCE_BRUTE_FORCE_ANN :74-77`, `BruteForceRowIdIterator :58-59/:76-77` | Left for stage 3 | not load-bearing |
| 8 | B2h: the `:42` assert as the unit "positive control" shows a guard on this class, not that the harness can see a cap on usage; the cluster control (`max_materialized_keys`) is the real one | Left for stage 3 | note; both are run |

## 2. Environment

| Field | Run 1 |
|---|---|
| Date | 2026-10-26 (UTC) |
| Node | `pc07` (`node0.jason92-320876`), local; own ports storage 7028, native 9350, JMX 7328, Byteman 9328, loopback 127.0.28.1 |
| OS and kernel | Ubuntu 22.04, `5.15.0-187-generic` |
| JDK | OpenJDK 11.0.32.1 |
| Ant | 1.10.12 |
| Local source copy | `~/s4-sr` (`copy-source.sh`) from `cassandra/cassandra-5.0.9/` at repository HEAD `1ae567d`; `ant jar` BUILD SUCCESSFUL in 1 min 13 s (`~/s4-sr-build.log`). Never built in after the node started. |
| Case-file commit / harness commit | uncommitted (orchestrator); case sha256 `bef23f61...`; harness md5 list `results/.../run1/harness.md5` |
| Storage for node data | `~/s4-sr-run` (local disk, `/`, 38 GB free at start) |
| Full logs | `~/stage4-logs/sr/run1/` on pc07 (`unit/`, `unit-attempt0-12g/`, `default/`, `1000/`, `64000/`, `calib/`, `default-attempt{0,1,2}-*/`); node data `~/s4-sr-run` |

## 3. Runbook defects

| # | Run | Step | Problem | Fix | Decision (date) | Case-file commit with the fix |
|---|---|---|---|---|---|---|
| 1 | 1, unit | B2e step 5 / B2b (2^30-2) | `-Xmx12g` with `-XX:+UseSerialGC` gave `OutOfMemoryError: Java heap space` for the 8.0 GiB array (old generation is 2/3 of the heap), for the plain `int[2N]` control too (`unit-attempt0-12g/summary.txt`) | `-Xmx16g` in B2a/B2b/B2e (B2f's wording is frozen and left; it reads "a heap that fits"); unit tier rerun from its start | 2026-10-26 | uncommitted (orchestrator) |
| 2 | 1, cluster | harness `wait_up` | `'running' in statusbinary` also matches `not running`; the client started before the native port was up (`default-attempt0-notrunning/`) | match `^running` | 2026-10-26 | harness only |
| 3 | 1, cluster | harness `load.py` | `nodetool -h 127.0.28.1` for JMX: JMX (local mode) listens on 127.0.0.1 only (`default-attempt1-load-nodetool-host/`) | `-h 127.0.0.1 -p 7328` | 2026-10-26 | harness only |
| 4 | 1, cluster | harness `SrHelper` / expectations | (a) the caller frame was the Byteman reflection accessor, not the Cassandra frame; (b) the Byteman rule adds a constant K = 1320 bytes between entry and exit, so strict equality with 16+8M failed (`default-attempt2-pre-calibration/`). K measured by `calibrate.sh` (same rules around `SrMem`, no node) and used in the EXPECTED lines | skip reflection frames; EXPECTED compares with 16+8M+K (up to 1 KiB extra) | 2026-10-26 | harness only; the default value was rerun from its start with the corrected harness |

Attempts 0, 1 and 2 of the cluster default value and attempt 0 of the unit tier are kept on the node and are not readings.

## 4. Run 1

**Scope:** unit tier: all N of §1 x 3 reps, the no-compressed-oops sweep, boundaries. Cluster tier: `max_materialized_keys` = default (16000), 1000, 64000 x M = 500 / 10000 / 20000 / 50000; token ranges and the memtable control at the default. **Command log:** `sai-SegmentRowIdOrdinalPairs-add-capacity--autonomous/run1/` (excerpts: `unit/summary.txt`, `cluster/<value>/summary.txt`, `selfcheck.out`, `calib.txt`).

### 4.1 Readings

**Unit tier** (`run1/unit/summary.txt`; `extra` = measured bytes - (16 + 8N); the measurement covers `new` + constructor)

| Test or assertion | Result | Evidence (file) |
|---|---|---|
| `pairs` delta = 16+8N+24 (the 24-byte object) for N = 1, 1000, 16000, 10^5, 10^6, 10^7, 10^8, 3 reps each | extra = 24 in all 21 runs; no plateau (8,000,040 at 10^6; 800,000,040 at 10^8) | `unit/summary.txt`, `selfcheck.out` |
| plain `int[2N]` control | extra = 0 in all 21 runs (exactly 16+8N) | same |
| retained heap (N >= 10^6) | 7,988,040 (10^6), 79,990,896 (10^7), 799,988,040 (10^8), same as the plain control within 12 KB | same |
| (N+1)th `add` | `ArrayIndexOutOfBoundsException: Array index out of range: N`, size stays N, every N <= 10^8 | same |
| `mapToSegmentRowIdScoreHeap` extra allocation | 770,664 (N=1000), 8,763,688 (10^6), 80,763,688 (10^7), 800,763,688 (10^8): >= 8N | same |
| no compressed oops (1 rep) | extra = 40 at N = 10^3, 10^6, 10^7: same slope, a larger fixed header | same |
| N = 2^30-2, `-ea`, 16g | allocated 8,589,934,616 B (= 16+8N+24); plain control 8,589,934,592 | same |
| N = 2^30-1 | `-ea`: `AssertionError: capacity is too large 1073741823`; `-da`: `OutOfMemoryError: Requested array size exceeds VM limit` | same |
| N = 2^30 | `-ea`: `AssertionError`; `-da`: `NegativeArraySizeException: -2147483648` | same |

**Cluster tier** (per cell: 200 queries after 50 warm-up and 1 traced; `alloc` is the minimum over the cell's SR lines, raw, so it includes K = 1320; `run1/selfcheck.out` has the independent recomputation)

| Capacity value | Run | Observable (B3d) | Reading | Evidence (file) |
|---|---|---|---|---|
| `max_materialized_keys` 16000 (default) | hybrid M = 500 | SR lines / cap / alloc / JFR | 200 lines, cap 500, alloc 5336 = 4016+K; JFR int[] of 4016 B | `cluster/default/summary.txt`, `selfcheck.out` |
| 16000 | hybrid M = 10000 | same | 200, cap 10000, alloc 81336 = 80016+K; JFR 80016 | same |
| 16000 | hybrid M = 20000, 50000 | SR lines; trace | 0 lines; trace "WHERE clause generated more than 16000 rows. Switching to ORDER BY then post filter." | `cluster/default/trace-hybrid-g3.json`, `-g4.json` |
| 16000 | memtable control (`ks.mt`, unflushed) | SR lines | 0; trace "...for memtable index with 5000 nodes" | `cluster/default/summary.txt` |
| 16000 | token range 101 / 1001 / 5001 / 30001 rows (LIMIT 100), 30001 (LIMIT 10) | trace `nRows`, SR | each: 200 lines, cap = traced nRows, alloc = 16+8nRows+K (2144, 9344, 41344, 241344), caller `VectorIndexSegmentSearcher.searchInternal:164`; thresholds 3.79M, 945,056 and 236,240 (>= nRows every time) | same; `trace-range-*.json` |
| 1000 | hybrid M = 500 | SR | 200 lines, cap 500, min alloc 5336 (one line 16088) | `cluster/1000/summary.txt` |
| 1000 | hybrid M = 10000, 20000, 50000 | SR; trace | 0 lines; fallback message "more than 1000 rows" | `cluster/1000/trace-hybrid-g2..g4.json` |
| 64000 | hybrid M = 500 / 10000 / 20000 / 50000 | SR | 200 lines each, alloc 5336 / 81336 / 161336 / 401336 = 16+8M+K; caller `orderResultsBy:299`; JFR int[] sizes 80016, 160016, 400016 | `cluster/64000/summary.txt`, `selfcheck.out` |

Fit over all cells (`selfcheck.out`): alloc = 4.0000 x arrlen + 1336 (8 B per pair; 1336 = 16 + K), 8 distinct sizes.

### 4.2 Conclusion and logic

1. **Validity.** The limit was reached in the sense the claim needs: allocation sizes were driven over many orders of magnitude (unit) and across the `max_materialized_keys` gate (cluster) [observed: `unit/summary.txt`, `cluster/*/summary.txt`]. Hold-fixed settings: JVM `-Xmx4G`, G1, `-ea`, Byteman agent present, the property read back as set for 1000 and 64000 and absent for the default [observed: `cluster/*/jvm-args.txt`, `summary.txt` "VM.system_properties"]; one SSTable in `ks.t` [observed: `cluster/default/summary.txt` "SSTable count: 1"]; one SR line per query per cell, so one segment [observed: 200 lines for 200 queries]; same vector and LIMIT 10 in all hybrid cells [observed: `trace-*.json` cql]. Instrument validity: the Byteman offset K is constant (1320 B for N >= 1000, `calib.txt`), the slope is exactly 8 B per pair, and JFR (independent of the rule) shows int[] allocations of exactly 16+8M at the same call sites [observed: `selfcheck.out`]. Valid.
2. **Readings.** Unusual: (a) a few SR lines carry extra bytes (up to +105 KB) in warm-up and the first query of a new shape, and one line per file in the timed window (+10.7 KB at L=1000 M=500; +10.7 KB at L=64000 M=20000; up to +872 B at 30000 rows): upward only, never below 16+8M+K; read as thread-allocation-counter artefacts at TLAB refill and first-use compilation [inferred: the unit tier has no such outliers and the minimum is exact in every cell]. (b) Token ranges select nRows = rows + 1. (c) Brute-force thresholds on the 80,500-node graph were 236,240 to 5.8 million, far above my prediction in §1, so every range tested was brute-force.
3. **Matched row.** Unit B2g: "Delta matches 16 + 8N across N | Claim confirmed" (and "Usage grows with N while `add` check works as above, and the plain `int[2N]` control grows identically"): extra over 16+8N is a constant 24 (the object) for all N, the plain control is exactly 16+8N, the N+1th add throws AIOOBE [observed]. Cluster B3g: "Allocation size = 16 + 8 x (traced count), changing with M and `max_materialized_keys` as predicted | Claim confirmed": every allocating cell has cap = traced count (materialized M, or nRows) and size 16+8cap+K; sizes appear and disappear with L vs M as in B3f [observed]. Positive control row "M = 20000 moves from 0 to about 160 KB when `max_materialized_keys` goes 16000 to 64000": 0 lines at 16000 and 200 lines of 161,336 (= 160,016 + K) at 64000 [observed: `cluster/default/summary.txt` g3, `cluster/64000/summary.txt` g3]; the `:42` assert: N = 2^30-1 and 2^30 allocate nothing, N = 2^30-2 allocates 8.6 GB [observed].
4. **Excluded rows.** "Delta flat or smaller than 8N": no, linear to 10^8 and at 2^30-2. "Plain control fails to grow": it grows. "Usage never reaches the largest N (OOM first)": 2^30-2 reached with 16g; the 12g attempt hit OOM (defect 1) and was rerun. "N = 2^30 behavior differs from B2f": it matches the frozen B2f (AssertionError / NegativeArraySizeException); only the original 2^30-1 expectation was wrong and was amended before any reading. "Allocation independent of the traced count or clamped": no, it equals 16+8 x count (+K) in every allocating cell. "No `SegmentRowIdOrdinalPairs.<init>` events in any cell": there are in every allowed cell. "Events appear but control cell stays flat": the control moved. "Allocation exceeds 8 x size": not observed (size = capacity in every cell, because the matched keys all fall in the segment); the overshoot of A3 item 4 is not exercised.
5. **Observed vs. inferred.** Inferred: (i) the +K offset is rule overhead, not class allocation [calibration shows the same K without a node; JFR shows exact 16+8M]; (ii) outliers are counter artefacts; (iii) "the class does not cap usage" from "usage equals 8 x the caller's count, before any check runs": the unit tier shows the constructor allocation precedes the first `add`, and the cluster tier shows the count is set by the gate, not by the class.
6. **Deviations and gaps.** (a) B3d's JFR-only instrument replaced by Byteman + `getThreadAllocatedBytes`; JFR kept as a cross-check (153 / 5 / 170 allocation events with the class's constructor on top). (b) The "baseline any other int[]" control is replaced by the rule and the JFR filter both being specific to the constructor. (c) Unit N = 10^8 ran with `-Xmx6g` (the queue needs more than 2 GB), the no-compressed-oops sweep with `-Xmx4g`, 2^30-2 with `-Xmx16g`. (d) The over-threshold half of the token-range prediction ("above the threshold: no allocation from this class") was not exercised: the largest possible range (80,500 rows) is below every observed threshold; only a graph of several million rows or the test-only `FORCE_BRUTE_FORCE_ANN` would reach it. (e) The overshoot case (capacity > pairs stored) was not exercised. (f) Run on a shared node; allocation counters are per thread, so unaffected. (g) Single node, single segment, 16-dimension vectors.
7. **Core question.** Usage follows the caller's count, not the line-55 check: the constructor allocates 16+8N bytes before any `add`, and the check only refuses a write past the array (unit); in a node the count is set by upstream gates (`max_materialized_keys` for the hybrid path, the key range for the token-range path) and the allocation moves exactly with them (cluster). So the check does not cap memory. A hard ceiling does exist in the class (the `:42` assert, active on a stock node, at 2^30-2 pairs = 8.6 GB), but it is an int-overflow guard, far above any gate-bounded size.

**Conclusion (one line):** B2g "Delta matches 16 + 8N" and B3g "Allocation size = 16 + 8 x (traced count)" with the positive control moving — confirmed, does not cap.

## 5. Self-check of run 1 — AI

### 5.1 Check of run 1's conclusion

Re-read from the raw files by `harness/.../selfcheck.py` (independent of `cluster-run.py`'s windows and EXPECTED lines: it counts every line of each `sr-trace.out` by cap and caller, fits the slope, and parses the JFR recordings) and by opening the raw files listed.

| Part | Holds? | Note (file re-read) |
|---|---|---|
| 1. Validity | yes | `jvm-args.txt` x3 (`-Xmx4G`, G1, `-ea`, property; the default run's args carry no `max_materialized_keys`), `summary.txt` read-back, `calib.txt` (K = 1320 for N >= 1000), JFR sizes in `selfcheck.out`. |
| 2. Readings | yes | outliers listed by line number from `sr-trace.out`: three warm-up lines per file plus one in the timed window per file; the minima are exact. |
| 3. Matched row | yes | `selfcheck.out` counts: default 251 lines each at cap 500 and 10000 (50 warm + 1 traced + 200), none at 20000 / 50000; L=1000 only cap 500; L=64000 caps 500 / 10000 / 20000 / 50000 at 251 each. Unit rows from `unit/summary.txt`. |
| 4. Excluded rows | yes | 2^30-2 line in `unit/summary.txt` (allocated); `unit/summary.attempt0-12g.txt` shows the OOM at 12g. |
| 5. Observed vs. inferred | yes | (i) `calib.txt` (same K) and JFR sizes exactly 16+8M (4016, 8024, 80016, 160016, 240024, 400016); (ii) outliers only upward and none in the unit tier; (iii) is reasoning from the code and both tiers. |
| 6. Deviations and gaps | yes | listed above; none hides a contradicting reading. |
| 7. Core question | yes | the step from "allocation = 8 x count, set before the check, moved by L and M" to "the check does not cap" follows B1 and the audited steps. |

### 5.2 Run 2?

No (2026-10-26). The conclusion rests on exact numbers on which two instruments (the Byteman counter and JFR) and a node-free calibration agree, the unit tier is deterministic, and the one weighty inferred statement (K is instrument overhead) was checked by calibration. A run 2 would not settle the two gaps (over-threshold range, overshoot), which need a larger graph.

## 6. Run 2 — fresh AI session (optional)

Not done.

## 8. Verdict — AI

**Stage-3 estimate:** negative. **Outcome class:** true negative (negative, does not cap).

**Claim tested:** B1 — heap used by `SegmentRowIdOrdinalPairs` equals 16 + 8 x N bytes, N being the capacity the caller passes, regardless of anything the line-55 check does; in a real query the allocation follows the upstream gates (brute-force threshold, `max_materialized_keys`) and is not bounded by the pairs class.

| Tier | Verdict (B2g / B3g row) | Effect on the constraint | Basis | Date |
|---|---|---|---|---|
| Unit | Confirmed: "Delta matches 16 + 8N across N" (plain control grows identically) | does not cap | run 1 + self-check | 2026-10-26 |
| Cluster | Confirmed: "Allocation size = 16 + 8 x (traced count)", positive control moved | does not cap | run 1 + self-check | 2026-10-26 |

**Positive control:** M = 20000 gives no allocation at `max_materialized_keys` 16000 and 200 allocations of 161,336 B (= 16 + 8 x 20000 + K) at 64000, so the instrument sees a cap that binds (the gate). Unit: the plain `int[2N]` grows exactly as the class does, and the `:42` assert blocks N = 2^30-1 and 2^30 while 2^30-2 allocates 8.6 GB.

**Feedback filed:** the case file's section D (the case file was amended by this session; final sha256 `bef23f61eee16264a942c81454ac5b978025d098ddcebecb05d0d710181ddabb`); A1, B2a, B2b, B2e, B2f (wording additions before any reading), B3c, B3e and B4 amended with dated notes. The frozen tables B2f-g and B3f-g hash to `c6394bcc...` in the final file, as frozen. `_INDEX.md`, the CSV and HANDOFF are left to the orchestrator.

**Leftovers:** nothing running (no `CassandraDaemon` of ours; ports 7028 / 7328 / 9350 / 9328 free). On disk: `~/s4-sr` (tree, 471 MB), `~/s4-sr-run` (node data and logs, 36 MB), `~/s4-sr-build.log`, `~/stage4-logs/sr/`.
