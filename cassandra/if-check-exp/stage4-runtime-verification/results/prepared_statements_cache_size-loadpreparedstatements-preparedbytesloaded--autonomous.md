# prepared_statements_cache_size-loadpreparedstatements-preparedbytesloaded--autonomous — stage-4 results  <!-- file: results/prepared_statements_cache_size-loadpreparedstatements-preparedbytesloaded--autonomous.md; the stem ends in --guided or --autonomous -->

> **Case:** [`prepared_statements_cache_size-loadpreparedstatements-preparedbytesloaded--autonomous`](../../stage3-ai-deep-read/cases/prepared_statements_cache_size-loadpreparedstatements-preparedbytesloaded--autonomous.md)
>
> **Status:** verdict filed 2026-10-27 — unit and cluster both Not confirmed: the cache is not bounded by the check (as claimed), but the check indirectly limits total heap through the eviction tombstones of `system.prepared_statements` (bypass); no run 2
>
> **Outcome class:** false negative (stage-3 estimate `negative`; stage-4 effect `caps only on some paths (bypass)`, which the protocol counts as `caps`) — read the caveat in §8: what the check bounds is a system-table memtable, not the prepared-statement cache
>
> **Agent:** autonomous (the suffix of the case-file stem). "§9a" below means B2f/B2g (unit) and B3f/B3g (cluster); "§9b–§9e" means B2a–B2e or B3a–B3e; the case file's feedback section is its section D.

## 1. Before run 1 — design audit and freeze

| Field | Content |
|---|---|
| **Case-file version** | Autonomous file, sha256 after the audit's amendments: `892c8eb35baca97aa677281ba771219f4003044c7568807173b2e1da7237beea` (`sha256sum`, 2026-10-27 22:16 EDT on the repo clone, before the unit run and before any cluster start). Commit holding the file before the amendments: `6e6cf92` (HEAD of the repository; the amendments and this results file are uncommitted in the working tree, as instructed). Section D was filled after the runs, so the file's final hash differs from the frozen one; only section D changed. |
| **Harness** | `harness/prepared_statements_cache_size-loadpreparedstatements-preparedbytesloaded--autonomous/` (uncommitted, working tree): `PstmtPreloadThresholdTest.java`, `unit-run.sh`, `cluster-run.py`, `chain.sh`, `make-node-yaml.sh`, `prep-load.py`, `drv.py`, `Jmx.java` (the last three copied from the sibling harness `prepared_statements_cache_size-storePreparedStatement-capacityToBytes--autonomous`), `analyze-unit.py`, `analyze-cluster.py`. |
| **Tiers and values** | Unit (B2): caps 1, 4, 10 MiB x arms A (unmodified) and B (`1.1` -> `1000.0`), offered factor f = 3 (3 repetitions) and f = 30 (caps 1 and 10, one run). Cluster (B3): same caps x arms, 20,000 seeded statements, `-Xmx1G`, 8 starts (the 1 MiB pair twice). |
| **Audit bottom line** | **Ready after amendments** — 2026-10-27 |

### 1.1 Design audit

| Group | Check | Rating | Note (section checked) |
|---|---|---|---|
| A. Core question | constrained quantity is memory or disk bytes | Met | A2/B1: heap of resident prepared statements (Caffeine weight is a byte estimate). Amended to name the cache component and the two side components (memtable, live heap). |
| A. Core question | knob varied, >= 3 values incl. default | Partly -> Met | B2b filed 1, 2, 10 MiB; the control needs a spread, so 1, 4, 10 (10 MiB = auto default at 1 GiB). Cluster filed 1 and 10 only; 4 added. |
| A. Core question | real resource measured, not only the counter | Partly -> Met | B2d named post-GC heap and a histogram. Amended: exact cache weight, `measureDeep`, memtable size of the system table, live heap after GC, thread-allocated bytes; the 1 to 2 MiB noise of the live heap at a 1 MiB cap is stated. |
| A. Core question | usage driven to the limit and past it | **Not met** -> Met | B2c cannot reach the check: every eviction deletes its row (`QueryProcessor.java:132-139`), so PREPARE leaves at most about 1 x cap on disk and the preload never passes 1.1 x cap. Amended: rows written directly (`SystemKeyspace.writePreparedStatement`), seeded node at 64 MiB for the cluster tier, plus a leak-sized backlog (f = 30). |
| A. Core question | positive control (negative claim) | Partly -> Met | B2h names one (cap 1 vs 10 MiB) but on the PREPARE path; amended to the preload path with arm B (check inert) at 1, 4, 10 MiB. |
| B. Logic | each step says what it establishes | Met | B2e / B3e. |
| B. Logic | prediction in numbers or a clear relation | Partly -> Met | B2f gave `1.1 x cap/s + 1` and "difference below one cap"; amended with the exact loaded count, the cache-fill relation, 1:4:10, and the expected memtable behaviour (stated before the run). |
| B. Logic | every plausible outcome has a conclusions row | Partly -> Met | No row for "cache equal but total heap differs". Rows added (cache bound refuted / confirmed / memtable bypass / check not reached). |
| B. Logic | confirmation needs ceiling-follows-knob and direct disallow evidence | Met | WARN line + loaded count (disallow), cache weight vs cap (ceiling). |
| B. Logic | alternative explanations and their controls | Partly -> Met | Eviction-tombstone memtable growth was missing; separated by the memtable gauge and the live-heap difference. |
| C. Specific | a human can follow it from the intro | Met | Intro and A1-A3. |
| C. Specific | an AI can run B2/B3 without re-deriving the path | Partly -> Met | Statement text, how rows get on disk, commands, observables, stop conditions were not exact; amended. |
| C. Specific | knob, values, workload, commands exact | Partly -> Met | As above; `-Dtest.jvm.args` form and yaml edits in the harness. |
| D. Runnable | harness and prerequisites exist or listed | Met | Written in step 1 (list above); builds `~/s4-base`, `~/s4-psc-b` from `copy-source.sh`, `ant build-test` 1 min 20 s / 1 min 16 s. |
| D. Runnable | workload arithmetic reaches the limit | Met after amendment | s = 2696 B (measured in the instrument check), n = ceil(f x cap / s): 1167 rows at 1 MiB f = 3; 116,682 rows at 10 MiB f = 30 (7 min of the run budget, measured 33 s); cluster 20,000 rows = 54 MB on the 35 MB node data dir; 251 GiB RAM, 53 GB free on `/`. |
| D. Runnable | load-bearing citations spot-checked | Met | `SystemKeyspace.java:1899-1935` (loop, threshold at 1907, `if` at 1919, `break`), `QueryProcessor.java:107` (cap), `:113-117` (Caffeine builder), `:132-139` (eviction removes the row), `:171-199` (preload callback, `parseAndPrepare(..., false)` -> `measure` true, so `pstmntSize` is set), `DatabaseDescriptor.java:795-801`, `CassandraDaemon.java:377` all match the pinned 5.0.9 source. |

| # | Recommendation | Applied? | Why |
|---|---|---|---|
| R1 | Write the rows directly; PREPARE-only loading cannot reach the check | Applied (amendment 2026-10-27, B2c, B3c) | Unreachable limit |
| R2 | Name the measured quantity: cache component; report memtable and live heap beside it | Applied (amendment, B1 note, B2d, B3d) | Group A |
| R3 | Add conclusions rows for the memtable/total-heap outcome and for "check not reached" | Applied (amendment, B2g, B3g) | Group B |
| R4 | Add a leak-sized backlog (f = 30) | Applied (amendment, B2c) | The check exists for CASSANDRA-19703-sized backlogs |
| R5 | Positive control on the preload path at three caps | Applied (amendment, B2b/B2f) | Negative-claim rule |
| R6 | Cluster seeding via a 64 MiB-cap node and per-start data copies; CQL cannot write system tables | Applied (amendment, B3c) | Runnable |
| R7 | The filed "heap held by prepared statements" remains undefined for the 1 MiB cap noise | Left for stage 3 | Wording; stage-3 text unchanged |

Instrument check before the freeze: the unit test was run once (arm A, cap 1 MiB, f = 3) as a smoke run, `run1/smoke/run.out`; it showed `pstmntSize` = 2696 populated, the cache empty and rows on disk equal to n, and the WARN seen. That run is not counted in the readings; no prediction was edited afterwards.

## 2. Environment

| Field | Run 1 |
|---|---|
| Date | 2026-10-27 (unit 20:14 to 20:25 MDT, cluster 20:27 to 20:39 MDT) |
| Node | `pc29` (`node3.jason92-321705.misconfiguration-pg0.cloudlab.umass.edu`), 40 cores, 251 GiB |
| OS and kernel | Ubuntu 22.04.2 LTS, `5.15.0-198-generic` |
| JDK | OpenJDK 11.0.32.1 (`11.0.32.1+1-post-1ubuntu1-22.04-Ubuntu`) |
| Ant | Apache Ant 1.10.12 |
| Local source copies | `~/s4-base` (arm A) and `~/s4-psc-b` (arm B), both from `copy-source.sh` of `cassandra/cassandra-5.0.9/` at repository commit `6e6cf92`; arm B differs by one line (`run1/arm-B.patch`) |
| Case-file commit / harness commit | `6e6cf92` (amendments uncommitted) / harness uncommitted |
| Storage for node data | local disk `/dev/sda3` under `~/s4-pthr` (removed after the run); unit tier uses the test tree's `build/test` directories |
| Full logs | `pc29:~/stage4-logs/pthr/` (`unit/`, `smoke/`, `cluster/<start>/`, `chain.status`), builds `pc29:~/stage4-logs/s4b/` |

## 3. Runbook defects

| # | Run | Step | Problem | Fix | Decision | Case-file commit |
|---|---|---|---|---|---|---|
| 1 | audit (before any tier) | B2c, B3c | PREPARE-only loading cannot leave more than about 1 x cap on disk (eviction deletes the row), so the check cannot fire as filed | rows written directly / seeded at 64 MiB (R1, R6) | applied 2026-10-27 before the freeze; the claim, predictions and conclusions rows were extended, not changed | uncommitted |

No defect occurred during the run itself; both tiers ran as amended on the first attempt.

## 4. Run 1

**Scope:** unit and cluster, all values above. **Command log:** `prepared_statements_cache_size-loadpreparedstatements-preparedbytesloaded--autonomous/run1/` (`unit/summary.txt`, `cluster/<start>/summary.txt`).

### 4.1 Readings

**Unit tier** (`run1/unit/run.out`, 22 cells, 132 checks, 0 MISMATCH). Times are for one cell; `liveDelta` is post-GC live heap after minus before; B - A is arm B minus arm A.

| Cell (cap MiB, f, rep) | n rows | loaded A / B | WARN A / B | cache `sumWeights` A / B (cap) | memtable B - A (bytes) | live heap B - A (bytes) | allocated MB A / B |
|---|---|---|---|---|---|---|---|
| 1, 3, r1-r3 | 1167 | 428 / 1167 | yes / no | 1,048,376 / 1,048,376 (1,048,576) | 232,701; 232,617; 238,168 | -190,456; +119,128; -74,216 | 31 / 85, 81 |
| 4, 3, r1-r3 | 4668 | 1712 / 4668 | yes / no | 4,193,504 / 4,193,504 (4,194,304) | 932,920; 949,380; 939,840 | 470,632; 592,104; 470,336 | 116 / 320 |
| 10, 3, r1-r3 | 11,669 | 4279 / 11,669 | yes / no | 10,483,760 / 10,483,760 (10,485,760) | 2,381,675; 2,388,646; 2,334,821 | 1,878,672; 1,978,304; 1,957,728 | 289 / 799 |
| 1, 30, r1 | 11,669 | 428 / 11,669 | yes / no | 1,048,376 / 1,048,376 | 3,563,397 | 2,644,064 (2.52 caps) | 31 / 839 |
| 10, 30, r1 | 116,682 | 4279 / 116,682 | yes / no | 10,483,760 / 10,483,760 | 35,629,656 | 32,171,784 (3.07 caps) | 288 / 7952 |

Other columns (`run.out`): rows left in `system.prepared_statements`: arm A 1125 / 4500 / 11,250 (f = 3) and 11,627 / 116,263 (f = 30), arm B 386 / 1544 / 3860 (= cache count) in every cell; `count + evicted == loaded` in every cell; arm A loaded = `floor(1.1 x cap / s) + 1` (s = 2696) in every cell. Positive control (arm B, f = 3, r1): `sumWeights` 1,048,376 : 4,193,504 : 10,483,760 = 1 : 4.00 : 10.00 (`run1/unit/run.out`).

**Cluster tier** (`run1/cluster/<start>/summary.txt`; 20,000 PREPAREd statements seeded at 64 MiB, 20,010 rows incl. 10 hot ones; `run1/cluster/seed/summary.txt`). Knob read-back from the start's log line in every start.

| Start | Preloaded N (ms) | WARN | cache count / evicted | `Prepared` instances after full GC | live bytes (`jmap -histo:live`) | memtable (JMX) | rows left |
|---|---|---|---|---|---|---|---|
| A, 1 MiB, r1 / r2 | 439 (403) / 439 (376) | 1 / 1 | 395 / 44 | 436 | 80,445,992 / 80,443,752 | 13,948 / 13,904 | 19,966 |
| B, 1 MiB, r1 / r2 | 20,010 (4373) / 20,010 (4265) | 0 / 0 | 395 / 19,615 | 436 | 85,876,776 / 85,881,152 | 6,217,955 | 395 |
| A, 4 MiB | 1753 (760) | 1 | 1581 / 172 | 1622 | 83,095,072 | 54,524 | 19,838 |
| B, 4 MiB | 20,010 (4288) | 0 | 1581 / 18,429 | 1622 | 88,149,568 | 5,841,993 | 1581 |
| A, 10 MiB | 4383 (1294) | 1 | 3953 / 430 | 3994 | 88,367,984 | 135,880 | 19,580 |
| B, 10 MiB | 20,010 (4155) | 0 | 3953 / 16,057 | 3994 | 92,701,368 | 5,074,012 | 3953 |

Live heap B - A: 5,430,784 and 5,437,400 B (5.18 and 5.19 caps) at 1 MiB; 5,054,496 B (1.21 caps) at 4 MiB; 4,333,384 B (0.41 cap) at 10 MiB. Memtable B - A: 6.20 MB, 5.79 MB, 4.94 MB. Positive control (arm B): cache count 395 : 1581 : 3953 = 1 : 4.00 : 10.01. The raw start-up lines (`Preloaded ...`, `Detected prepared statement cache filling up ...`, the histogram head, `GC.heap_info`) are in `run1/cluster/<start>/excerpt.txt`.

### 4.2 Conclusion and logic

1. **Validity.** The check was reached in every arm A cell: WARN seen and `loaded` = `floor(1.1 x cap / s) + 1` in all 11 unit arm A cells (428, 1712, 4279) **[observed: `run1/unit/run.out`]**, and `Detected prepared statement cache filling up` once per arm A start **[observed: `run1/cluster/A-cap*/excerpt.txt`]**. Arm B never reached it: no WARN, `loaded` = n **[observed: same files]**. `pstmntSize` is populated at the check (calibration 2696 B, rows loaded by the callback add > 0) **[observed: `run1/smoke/run.out`, `run1/unit/run.out` check `pstmntSize-populated`]**. The cap and the arm were read back in every start **[observed: `READBACK` lines, `cluster/*/summary.txt`]**. Each arm's tree is what the table says: `git diff` of `~/s4-psc-b` is the one line in `run1/arm-B.patch`; `~/s4-base` has no diff **[observed: `run1/unit/summary.txt` header lines]**. Valid.
2. **Readings.** Two items. (a) The post-GC live heap moves by about 0.3 MiB between repetitions at the same cell (arm A cap 1 MiB: 1.95 to 2.15 MiB), so differences below about 0.5 MiB are noise **[observed: `run1/unit/run.out`]**. (b) At 1 MiB, f = 30, the memtable difference (3.56 MB) exceeds the live-heap difference (2.64 MB) by 35 %, outside the 25 % attribution rule of the added B2g row; at 10 MiB, f = 30 it is 11 % and in the three cluster pairs 14 to 15 % **[observed: `run1/selfcheck.out`]**. The row is therefore matched on the 10 MiB cell and the cluster, not on the 1 MiB cell alone.
3. **Matched row.** Unit: the added B2g row *"Cache component equal, but the live-heap difference B - A is one cap or more and is explained by the memtable difference ... Verdict Not confirmed, Effect `caps only on some paths (bypass)`"*. Cache component: `sumWeights` equal in arm A and B in all 11 pairs, `<=` cap and within two statements of it **[observed: `run1/unit/run.out`]**. Live heap B - A at f = 30: 2.52 caps (cap 1 MiB) and 3.07 caps (cap 10 MiB) **[observed]**; memtable B - A 3.56 MB and 35.6 MB **[observed]**; at the filed workload (f = 3) the live-heap difference is below one cap in all nine pairs (largest 1.98 MB at cap 10 MiB, 0.19 cap) **[observed]**, which is the *Confirmed* row of the filed B2g. Cluster: the same added B3g row: `Prepared` instance count and cache count equal across arms (436 / 1622 / 3994), live heap B - A 5.18 and 5.19 caps at 1 MiB and 1.21 caps at 4 MiB, memtable B - A within 14 to 15 % of the live-heap difference **[observed: `run1/cluster/*/summary.txt`, `selfcheck.out`]**; at 10 MiB the difference (4.33 MB) is 0.41 cap, below one cap, and has the same size in bytes as at the other caps.
4. **Excluded rows.** *Claim refuted: the check bounds the cache* — excluded: `sumWeights` is equal in both arms and `<=` cap everywhere, arm B at 1 : 4 : 10 MiB moves 1 : 4.00 : 10.00 while arm A and B stay equal at each cap **[observed]**. *Check not reached / pstmntSize unpopulated* — excluded by the WARN and by `loaded` A < B **[observed]**. *Control failed* — excluded: arm B's cache moves with the cap in both tiers **[observed]**. *Pure Confirmed (check bounds work only)* — excluded for f = 30 and for the 1 and 4 MiB cluster starts by the live-heap difference of one cap or more.
5. **Observed vs. inferred.** Inferred: (i) that the extra live heap of arm B is the tombstone memtable of the evictions **[inferred: the memtable gauge difference is within 14 % (cluster, unit 10 MiB f = 30) of the live-heap difference and arm B has 19,615 more deletions than arm A at 1 MiB; no heap dump attributes the bytes]**; (ii) that a real node would keep that memtable until a flush, so the extra heap is transient, not a standing bound **[inferred: memtable flush thresholds were not reached (largest memtable 6.2 MB on a 1 GiB heap); not run to a flush]**; (iii) that the live-heap numbers at a 1 MiB cap resolve one cap **[inferred: repeat spread 0.3 MiB]**.
6. **Deviations and gaps.** The unit f = 30 cells ran once; f = 3 cells three times, cluster 1 MiB pair twice, the others once (B2e asked for three). No flush of the memtable was driven, so how long the extra heap persists is not measured. The statement shape is `SELECT ... WHERE k = ?` with a comment, not the `INSERT ... USING TIMESTAMP` of the filed text (amended, size is what matters; one size in all arms).
7. **Core question.** The cache that holds resident prepared statements is capped by `prepared_statements_cache_size` and not by the threshold (identical cache weight and instance counts with the check on or off; weight follows the cap 1 : 4 : 10; §4.1, parts 3 and 4). The threshold does limit something else: with a backlog of 54 x the cap (cluster) or 30 x (unit), arm B has about 4 to 5 MB (cluster) to 32 MB (unit, cap 10 MiB, 117,000 rows) more live heap than arm A, which matches the memtable of the delete tombstones its evictions write; arm A stops after about 1.1 x cap and writes about 20 times fewer. So the check caps usage on that path only (a bypass of the claim's wording), and the claim "does not bound resident memory" holds for the cache and fails for total heap.

**Conclusion (one line):** unit and cluster: *Cache component equal, live-heap difference of one cap or more explained by the memtable* — Not confirmed (claim holds for the cache, fails for total heap); Effect `caps only on some paths (bypass)`.

## 5. Self-check of run 1 — AI

`run1/selfcheck.py` (output `run1/selfcheck.out`) re-parses the raw files in this folder and tests every statement below; 125 PASS, 0 FAIL, plus the INFO lines quoted in part 2.

| Part | Holds? | Note (file re-read) |
|---|---|---|
| 1. Validity | yes | `run.out`: arm A `loaded` = `floor(1.1 cap/s)+1` and WARN in all arm A cells; arm B `loaded` = n, no WARN; `excerpt.txt` of each start agrees with its `summary.txt` on the `Preloaded N` line; `arm-B.patch` is the one literal. |
| 2. Readings | yes | The 25 % attribution rule fails for the 1 MiB f = 30 cell (0.35): recorded in part 2 and the row is not claimed from that cell alone. |
| 3. Matched row | yes | `sumWeights` equal and `<=` cap in 11 unit pairs; cluster `Prepared` instances and counts equal; live-heap and memtable differences as quoted (`selfcheck.out` INFO lines). |
| 4. Excluded rows | yes | Control moves 1 : 4 : 10 (unit `sumWeights`, cluster count); WARN and `loaded` rule out "not reached". |
| 5. Observed vs. inferred | yes (limits stated) | The tombstone attribution is by the memtable gauge, not a heap dump; a dump-based attribution was not done. This is why the row is the bypass-with-explanation row and not a stronger claim. |
| 6. Deviations and gaps | yes | As listed; none changes the matched row. |
| 7. Core question | yes | The steps follow B1: cache bound unchanged by the check (refuted rows excluded), usage elsewhere follows the check (matched row). |

### 5.2 Run 2?

No — 2026-10-27. The matched row rests on one inferred statement (tombstone attribution) that is consistent in nine measurements across two tiers, and the verdict wording (bypass, Not confirmed) already reflects its limit. A flush-to-disk run would answer the persistence question and is listed in the feedback for stage 3.

## 6. Run 2 — fresh AI session (optional)

Not done.

## 7. Comparison — only if run 2 was done

Not done.

## 8. Verdict — AI

**Stage-3 estimate:** negative. **Outcome class:** false negative (negative, effect `caps only on some paths (bypass)` counts as `caps`). Caveat for readers of the class: the object the check bounds is the memtable of `system.prepared_statements` (tombstones written when the Caffeine cache evicts), a system-table memtable that a flush would write out; the prepared-statement cache itself is not bounded by the check. The stage-3 reasoning about the cache was right.

**Claim tested:** the threshold check does not bound resident prepared-statement heap: heap held after start-up stays at or below the Caffeine cap whether the check is enabled or not, and the check changes only the number of statements loaded and start-up time.

| Tier | Verdict (B2g / B3g row) | Effect on the constraint | Basis | Date |
|---|---|---|---|---|
| Unit | Not confirmed: cache component equal, total live heap differs by one cap or more (f = 30), explained by the memtable | caps only on some paths (bypass) | run 1 + self-check | 2026-10-27 |
| Cluster | Not confirmed: same row (1 and 4 MiB caps; at 10 MiB the difference is 0.41 cap) | caps only on some paths (bypass) | run 1 + self-check | 2026-10-27 |

**Positive control:** arm B (check inert) with the same workload and instruments at 1, 4, 10 MiB: cache weight 1,048,376 : 4,193,504 : 10,483,760 (unit), cache count 395 : 1581 : 3953 (cluster), i.e. 1 : 4 : 10; the instruments see the binding cap. This is the knob of the closed case `prepared_statements_cache_size-storePreparedStatement-capacityToBytes--autonomous`, now on the preload path.

**Feedback filed:** the case file's section D updated (uncommitted); amendments 2026-10-27 in the case file at B1, B2 and B3 (uncommitted). `_INDEX.md` and HANDOFF were not edited (instruction); the new sha256 for `_INDEX.md` §4 is the frozen one in §1.
