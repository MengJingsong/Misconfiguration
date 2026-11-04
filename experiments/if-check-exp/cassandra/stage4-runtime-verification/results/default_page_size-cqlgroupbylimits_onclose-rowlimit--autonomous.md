# default_page_size-cqlgroupbylimits_onclose-rowlimit--autonomous — stage-4 results  <!-- file: results/default_page_size-cqlgroupbylimits_onclose-rowlimit--autonomous.md -->

> **Case:** [`default_page_size-cqlgroupbylimits_onclose-rowlimit--autonomous`](../../stage3-ai-deep-read/cases/default_page_size-cqlgroupbylimits_onclose-rowlimit--autonomous.md)
>
> **Status:** verdict filed (2026-10-27)
>
> **Outcome class:** true positive (estimate `positive`; unit **Confirmed — caps**, cluster **Confirmed — caps**, with recorded numeric misses in B3f and the plain-aggregate bypass as filed)
>
> **Agent:** autonomous. "§9a" below means each tier's predictions and conclusions table: B2f and B2g (unit), B3f and B3g (cluster); "§9b–§9e" means B2a–B2e or B3a–B3e; the case file's feedback section is its section D.

## 1. Before run 1 — design audit and freeze

| Field | Content |
|---|---|
| **Case-file version** | Repository HEAD `68f9c3c` (the case file is untracked there; the orchestrator commits it). sha256 of the whole file after the audit's amendments U1-U5, C1-C4, R1-R5 (2026-10-27, before any reading): `163a23eae52b98779f139ae4983f0db096768a98cb262ca7bc75a67dc260dd63`. sha256 of the frozen prediction and conclusion tables (text from `**B2f.` up to `**B2h.` plus from `**B3f.` up to `**B3h.`, concatenated): `a7a5a1f298ca400e868d4d1a6fbc0ac5bb7f80438fed7169b83158dbb8b491af`. Frozen 2026-10-27 21:25 UTC, before the unit run (copies at `~/s4-dps-logs/run1/{case-frozen.md,freeze-pred.txt,case-original.md}` on pc39). Section D changes after the run and is outside the hash. |
| **Harness** | `harness/default_page_size-cqlgroupbylimits_onclose-rowlimit--autonomous/` (README lists the files; untracked, the orchestrator commits) |
| **Tiers and values** | Unit (B2): CQLTester, 1 partition x 200000 rows x 1 KiB, 10 groups; `DEFAULT_PAGE_SIZE` = 100 / 1000 / 10000 / 50000 (one `ant testsome` each), client page size unset and 250, plain aggregate as negative control. Cluster (B3): one node (RF 1), 512 MB heap, local disk, 1 partition x 2,000,000 rows x 1 KiB, `DEFAULT_PAGE_SIZE` = 500 / 10000 (stock) / 200000 (three builds), client page size unset, 3 repetitions; controls: plain `count(payload)`, client fetch 500 and 200000 on the stock build, guardrail arm (`page_size_fail_threshold` 10000, ordinary role). |
| **Audit bottom line** | **Ready after amendments** — 2026-10-27 |

### 1.1 Design audit

| Group | Check | Rating | Note (section checked) |
|---|---|---|---|
| A. Core question | constrained quantity is memory or disk bytes | Partly | A2/B1: a row count (`rowsCounted` vs `rowLimit`) with derivable byte size (rows x 1 KiB); the Estimate line names the byte caveat. Accepted as a count with a derivable byte size. |
| A. Core question | knob varied, ≥ 3 values incl. default | Met | B2b: 100 / 1000 / 10000 / 50000; B3b: 500 / 10000 / 200000. The knob is a compile-time constant, so each value is a rebuild (the file says so). |
| A. Core question | real resource measured, not only the counter (gap named) | Partly | B2d: counter plus allocated bytes and serialised size; B3d: `gc.log` and a heap poller; per-query live heap is not observable (named). C2 defines the post-GC peak. |
| A. Core question | usage driven to the limit and past it | Met | N = 200000 / 2,000,000 exceeds every constant; 200000 x 1 KiB is 200 MB against a 512 MB heap. |
| B. Logic | each step says what it establishes | Met | B2e / B3e. |
| B. Logic | prediction stated in numbers or a clear relation | Met after U2, U3, C2 | B2f's `ceil` sub-read counts were wrong (`DataLimits.java:986`, `:1041`: N divides every limit, so one more empty read follows: floor+1); "ratio near 500" and "several times", "visibly more GC" had no measure. |
| B. Logic | every plausible outcome has a conclusions row | Partly | Rows exist for flat, exceeds, trace wrong, never reached; no row for node death at the large constant (C2 says it counts as "rises") and none for a plain aggregate that is unbounded; the latter is recorded in the results, not added to the table. |
| B. Logic | confirmation needs ceiling-follows-knob and direct disallow evidence | Met | Rows per read from the Byteman trace and the white-box counter (`rowsCounted == constant`, `isDone` false at the first read) are the direct evidence of the `:986` branch. |
| B. Logic | alternative explanations and controls | Met | B2h/B3h: client page size path, plain aggregate, guardrail arm. |
| C. Specific | a human can follow it from the intro and §9a | Met | A1-A5, B1. |
| C. Specific | an AI can run it without re-deriving the code path | Partly | `count(*)` vs the blob, the unset-page-size client, timeouts, heap for the load, role for the guardrail: C1, C3, R1-R2. |
| C. Specific | knob, values, workload, commands, observables exact | Partly | Filled by U1-U5, C1-C4, R1-R5. |
| D. Runnable | harness and prerequisites exist or are listed | Met | JDK 11, Ant, `ant build-test` done on pc39; probe and scripts are step-1 work. |
| D. Runnable | workload arithmetic reaches the limit | Met | 2.09 GB sstable on local disk (55 GB free), 447 s load, 4001 reads about 13 s; 200000 x 1 KiB per read exceeds the 512 MB heap's usable space. |
| D. Runnable | citations spot-checked against the pinned source | Met | `SelectStatement.java` 114, 286-298, 338, 899-914, 517; `DataLimits.java` 116-121, 547-561, 676-682, 740-748, 779-802, 982-990, 1033-1048; `AggregationQueryPager.java` 44-64, 190-200, 268-276. All as cited (a few line numbers 1-2 off in the file's AggregationQueryPager cites, not load-bearing). |

| # | Recommendation | Applied? | Why |
|---|---|---|---|
| U1 | `count(v)` in place of `count(*)` | applied 2026-10-27 (reworded after the unit shakedown: `count(*)` serialises the same) | safeguard that the value is read |
| U2 | sub-read counts floor+1 | applied | `:986`, `:1041` |
| U3 | measurable allocation ratio [100, 550] | applied | prediction must be contradictable |
| U4/U5 | limits strings, reflection, knob mechanics | applied | make the compiled value observable |
| C1-C4 | query, definitions of peak/"several times"/death = OOM, instruments, arm counts (3 reps, not 20) | applied | |
| R1-R5 | one node, 2 GiB load heap, builds, data reuse, cleanup | applied | sibling's load defect; shared data directory |
| left | the claim sentence "the guard never sees the default" and the `count(*)` comment in A5 are stage-3 wording | left for stage 3 | no effect on the run |

**Agreement criteria** — run 2 not chosen (see 5.2).

## 2. Environment

| Field | Run 1 |
|---|---|
| Date | 2026-10-27 (unit 15:3x-15:4x local MDT; cluster 15:27-16:02 MDT; shakedowns 15:11-15:25) |
| Node | `pc39` (`node1.jason92-321705.misconfiguration-pg0.cloudlab.umass.edu`), 40 cores, 251 GiB |
| OS and kernel | Ubuntu 22.04, `5.15.0-198-generic` |
| JDK | openjdk 11.0.32.1 2026-08-18 |
| Ant | Apache Ant 1.10.12 |
| Local source copy | unit: `~/cassandra-run1` (`ant build-test`); cluster: `~/s4-dps-v10000`, `~/s4-dps-v500`, `~/s4-dps-v200000` (`ant jar`), all from `copy-source.sh` at repository commit `68f9c3c` (`git describe`: `cassandra-5.0.9`) with only line 114 of `SelectStatement.java` changed |
| Case-file commit / harness commit | case file untracked at `68f9c3c` (sha256 in section 1) / harness untracked |
| Storage for node data | cluster: `~/s4-dps-run/` on `/dev/sda3` (local, 51 GB free after the load); never under /proj; removed after the run |
| Full logs | `~/s4-dps-logs/run1/{unit-*,cluster}/` on pc39 (cluster: `cells.jsonl`, `gcrun.jsonl`, `session.log`, `sstables-*.txt`, and per variant `heap.csv`, `dps.trace`, `gc.log*`, `system.log`, `start.out`); shakedowns `~/s4-dps-logs/shake`, `cshake` |

## 3. Runbook defects

| # | Run | Step | Problem | Fix | Decision | Case-file commit |
|---|---|---|---|---|---|---|
| D1 | unit shakedown (4000 rows; not a reading) | U1 | The premise that `count(*)` reads no value is false here: first-read serialised sizes of `count(*)` and `count(v)` GROUP BY are identical (1039999 bytes at 1000 rows). | U1 reworded (`count(v)` kept as a safeguard); prediction and tables unchanged | 2026-10-27 | untracked |
| D2 | cluster run | B3 plain-aggregate control | The plain `count(payload)` kills the 512 MB node (see 4.1), so the analyzer expectation "no death" is a prediction miss, not a runbook defect; recorded in 4.2 part 6. | none (harness unchanged) | 2026-10-27 | n/a |

No step failed to run as written in run 1; nothing was restarted. The cluster shakedown (scale 100) and the unit shakedown were instrument checks.

## 4. Run 1

**Scope:** all unit cells as filed (4 constants x page size unset / 250, plain aggregate); all cluster cells as amended (3 variants x 3 GROUP BY + 3 plain; stock fetch 500 / 200000 x 3; guardrail arm). **Command log:** `default_page_size-cqlgroupbylimits_onclose-rowlimit--autonomous/run1/{unit-summary-*.txt, cluster-session.txt}`; readings `unit-dps-*.txt`, `cluster-cells.jsonl`, `cluster-gcrun.jsonl`; analyzers `unit-analysis.txt`, `cluster-analysis.txt`; self-check `selfcheck.txt`.

### 4.1 Readings

**Unit tier** (analyzer: all `EXPECTED:` lines PASS, `unit-analysis.txt`; 200000 rows x 1 KiB, 2 timed repetitions each, identical)

| Test or assertion | Result | Evidence (file) |
|---|---|---|
| Compiled constant (reflection) and limits string, page size unset | `LIMIT 100 / 1000 / 10000 / 50000`; with page size 250 `LIMIT 250` for every constant; plain aggregate `''` | `unit-dps-*.txt` (`DPS L`) |
| White-box counter after the first sub-read | rowsCounted = 100 / 1000 / 10000 / 50000 (never +1), isDone false | `DPS W` |
| Max rows per sub-read; total rows | = constant; 200000 in every cell | `DPS E` |
| Sub-read count | 2001 / 201 / 21 / 5 = floor(200000/K)+1; 801 at page size 250 for every K | `DPS E` |
| Sub-reads with exactly the limit | 2000 / 200 / 20 / 4 | `DPS E` (atMax) |
| First-read serialised bytes | 104001 / 1040001 / 10400003 / 52020414 = 1040 per row; size(10000)/size(1000) = 10.000 | `DPS W` |
| Mean allocated bytes per full sub-read | 161,790 / 1,519,804 / 15,101,218 / 75,463,394 B; ratio(50000)/ratio(100) = 466.4 (filed band 100-550) | `unit-analysis.txt` |
| Plain aggregate (negative control) | no LIMIT, one raw read of all 200000 rows, for every constant and page size | `DPS P` |

**Cluster tier** (post-GC peak above baseline = max occupancy after a GC pause in the query window minus occupancy after the forced full GC before it; 512 MB heap; idle `used` about 75-80 MB; all in `cluster-analysis.txt`)

| Capacity value | Run | Observable | Reading | Evidence (file) |
|---|---|---|---|---|
| 500 | 3 GROUP BY, page size unset | rows read, reads, max rows/read; peak above baseline; wall | 2,000,000; 4001; 500; +2.0 / +2.0 / +2.0 MB; 13-14 s; 1 percent GC | `cluster-analysis.txt`, `selfcheck.txt` |
| 10000 (stock) | same | same | 2,000,000; 201; 10000; +367 / +192 / +183 MB (mean +247; mean peak occupancy 322 MB); 11-15 percent GC; 13 s | same |
| 200000 | same | outcome | node dead in 3 of 3 (0 reads completed in 2 of 3; one 200000-row read completed in rep 2); last GC lines `Pause Full (G1 Humongous Allocation)` with no reclaim; wall 0.9-2.2 s | `selfcheck.txt`, `cluster-cells.jsonl` |
| stock, client fetch 500 | 3 | reads; peak | 4001; 500; +3 / +2 / +2 MB | same |
| stock, client fetch 200000 | 3 | outcome | node dead 3 of 3, one 200000-row read in the trace each, `Pause Full` runs 459M->379M->379M | same |
| plain `count(payload)`, all three builds | 3 each | outcome | node dead in 9 of 9 after 1.5-1.6 s; no GROUP BY counter lines; `Pause Full (G1 Humongous Allocation) 299M->299M` runs | same |
| guardrail arm (`page_size_fail_threshold` 10000, role `app`) | fetch 500 x1; fetch 200000 x3 | outcome | 500 passes; 200000 rejected in 16 / 4 / 5 ms with "Guardrail page_size violated" | `cluster-analysis.txt`, `cluster-session.txt` |
| disk | every query | size of `ks` data dir before/after | 2,091,979,751 B both; sstable lists before and after identical | `cluster-cells.jsonl`, `sstables-*.txt` (pc39) |
| node health | whole run | deaths, restarts | 15 restarts after deaths (all in the 200000-constant, fetch-200000 and plain-count cells); no stray process afterwards | `cluster-session.txt` |

### 4.2 Conclusion and logic

1. **Validity** — Valid. The limit was reached and passed: the 200000 builds (and a 200000 client fetch on stock) exceed the 512 MB heap [observed: `cluster-cells.jsonl`, `selfcheck.txt`]. First-trigger check passed on all three builds (4002 trace lines, 3982 with rows = 1000 groups = 0 unfinished = true, none above 1000) [observed: `cluster-session.txt`]. Held fixed: one 2.09 GB single-sstable partition, identical before and after (`sstables-*.txt`); 512 MB heap for every measurement; forced full GC and a 3 s settle before each query; row cache off [observed]. The compiled constant of each build was logged before loading [observed: `cluster-session.txt`, `build ...` lines]; unit: reflection value printed in `DPS START`.
2. **Readings** — (a) at 10000 the first repetition (+367 MB) was higher than the next two (+192, +183): the first query after the fetch-1000 warm-up; (b) at 200000 two of three repetitions died before any read finished, one after a completed 200000-row read; (c) the plain aggregate kills the node on every build.
3. **Matched row** — Unit, B2g row 1: rows per sub-page = constant (white-box `rowsCounted` = K; max rows per sub-read = K), sub-page count = floor(200000/K)+1, allocation per sub-read scales (ratio 466) [observed: `unit-dps-*.txt`, `unit-analysis.txt`]. Cluster, B3g row 1 with row 2: peak above baseline rises with the constant, +2.0 MB at 500, +247 MB at 10000, node death at 200000 [observed: `cluster-analysis.txt`], and reads per query = 2,000,000/K + 1 (4001 / 201) with at most K rows per read [observed: `selfcheck.txt`]; the guardrail row (positive control for the client-value path) also holds [observed].
4. **Excluded rows** — Unit: rows above the constant (row 2): max = K everywhere; limits string unchanged (row 3): it follows K; allocation flat (row 4): ratio 466; plain aggregate shows a limit (row 5): empty string; N < K (row 6): no, N = 200000 exceeds all. Cluster: flat peak (row 3): 2 -> 247 MB -> death; per-read rows exceed constant (row 4): max rows per line = K (500, 10000, 200000); plain heap changes with the constant (row 5): the plain aggregate kills the node on all three builds identically, so it does not follow the constant; 200000 shows no more heap than 500 (row 6): the node dies.
5. **Observed vs. inferred** — Inferred: (i) a node found dead died of `OutOfMemoryError`: no log line exists (`kill -9`), the evidence is the run of `Pause Full (G1 Humongous Allocation) X->X` with no reclaim at the end of every dead window and no external killer [inferred: `selfcheck.txt`]; (ii) post-GC occupancy stands for the live data of the read (no per-request live heap); (iii) K = 2 trace lines per read [inferred: every window holds an even number of lines; the calibration query leaves exactly 2]; (iv) the unit allocation counter covers the whole local read on the calling thread.
6. **Deviations and gaps** — (a) Numeric misses of the frozen B3f: the claim "500 and 10000 stay well below the heap" (my filed measure: at most 256 MB above baseline) fails at 10000: mean +247 MB, one repetition +367 MB, mean peak occupancy 322 MB of 512 MB (`cluster-analysis.txt` prints this expectation as FAIL); the relation (rises with the constant, 200000 does not fit) holds and no B3g row is about magnitude. (b) The plain-aggregate prediction "heap profile not affected by the constant" holds as a relation (identical death on all builds) but my filed measure "no death" fails: a plain `count(payload)` over the 2 GB partition with the page size unset is not streamed; it exhausts a 512 MB heap in 1.5 s (this is the filed non-cap path, now measured). (c) 3 measured repetitions per cell instead of 20 (C4). (d) The 200000 variants cannot show a completed query, so the per-read cell count there rests on the 1 completed read in rep 2 and the three stock fetch-200000 reads. (e) The unit tier measures allocation, not live heap.
7. **Core question** — Yes. With the client page size unset, the compile-time `DEFAULT_PAGE_SIZE` is the row limit of every internal read of a GROUP BY: exactly that many rows per read (unit steps and trace: parts 3-4), 2,000,000/K + 1 reads per query, and heap that rises with it (+2 MB, +247 MB, death on a 512 MB heap for K = 500, 10000, 200000) and equals the client-fetch path at the same value (fetch 500 matches the 500 build; fetch 200000 and the 200000 build both kill the node). It caps rows, not bytes, and not plain aggregates (unbounded, measured).

**Conclusion (one line):** unit B2g row 1, cluster B3g rows 1 and 2 (guardrail row holds) — claim confirmed: the default page size caps the rows, and with them the heap, per internal read of an unpaged GROUP BY (effect: caps; byte-size caveat and the plain-aggregate non-cap as filed).

## 5. Self-check of run 1 — AI

### 5.1 Check of run 1's conclusion

`harness/.../selfcheck.py` re-parsed the cluster raw files with its own code (`cells.jsonl`, `dps.trace`, `gc.log*`), output `run1/selfcheck.txt`: reads, rows and max rows per line for every query and the last three GC pauses before each death; the reads per query (201, 4001, 1 with 200000 rows) and the death evidence agree with the analyzer. I re-read the `unit-dps-*.txt` lines by hand against `unit-analysis.txt` (e.g. `DPS E p=unset rep=2 rows=200000 subpages=21 maxRowsPerSubpage=10000` at K = 10000) and the sstable lists before and after (identical).

| Part | Holds? | Note (file re-read) |
|---|---|---|
| 1. Validity | yes | `cluster-session.txt` (first-trigger, build lines, load 2,000,000 rows 0 errors), `selfcheck.txt` |
| 2. Readings | yes | the 367 / 192 / 183 spread is in `cluster-analysis.txt`; deaths in `selfcheck.txt` |
| 3. Matched row | yes | every quoted number reproduced in `selfcheck.txt` / `unit-dps-*.txt` |
| 4. Excluded rows | yes | each cites a number found in the raw files |
| 5. Observed vs. inferred | yes | (i) death = OOM is the weakest link; the 500 / 10000 rise (+2 vs +247 MB) does not depend on it |
| 6. Deviations and gaps | yes | the two FAIL expectations are reported as found |
| 7. Core question | yes | hypothesis B1 -> unit/cluster tests -> predictions -> rows, in that order; controls moved as the logic needs |

### 5.2 Run 2?

**No** (2026-10-27). The unit mechanism is deterministic (exact counts for four constants), the cluster relation spans 2 MB -> 247 MB -> death, and the closest sibling case (`group-by-row-limit-incrementRowCount-rowsCounted--autonomous`) found the same shape through the page-size route. The weak link (death read as OOM) would not change the matched row.

## 6. Run 2 — fresh AI session (optional)

Not done (section 5.2).

## 7. Comparison — only if run 2 was done

Not applicable.

## 8. Verdict — AI

**Stage-3 estimate:** positive. **Outcome class:** true positive (positive, caps).

**Claim tested:** (B1) For a GROUP BY query with no client page size, the number of live rows read per internal sub-read is capped by `SelectStatement.DEFAULT_PAGE_SIZE` (so peak transient heap on the read path grows roughly in proportion to it and not to the partition size), and the cap does not apply to a plain aggregate. "Confirmed" means this claim held.

| Tier | Verdict (B2g / B3g row) | Effect on the constraint | Basis | Date |
|---|---|---|---|---|
| Unit | B2g row 1: **Confirmed** — rows per sub-read = K for K = 100 / 1000 / 10000 / 50000 (white-box `rowsCounted` = K, never K+1), sub-reads floor(200000/K)+1, first read 1040 bytes per row, allocation ratio 466; plain aggregate has no limit | caps (row-count cap; bytes = rows x row size) | run 1 + self-check | 2026-10-27 |
| Cluster | B3g rows 1 and 2: **Confirmed** — +2 MB at 500, +247 MB (mean; peak occupancy 322 MB) at 10000, node death at 200000; reads 4001 / 201; client fetch 500 / 200000 on stock behave like the 500 / 200000 builds; guardrail rejected fetch 200000 in 4-16 ms. Misses recorded: 10000 not "well below the heap" at 512 MB; plain aggregate kills the node | caps (soft: the cap is a compile-time constant; plain aggregates are unbounded as filed) | run 1 + self-check | 2026-10-27 |

**Feedback filed:** the case file's section D updated (amendments U1-U5, C1-C4, R1-R5 and these results); no section of the trace was refuted. **Open points:** (1) the 10000 default is itself heavy on a 512 MB heap with 1 KiB rows (+247 MB, 11-15 percent GC); (2) a plain aggregate over one huge partition is unbounded: 1.5 s to kill a 512 MB node; (3) death read as OOM from the GC log. **Leftovers on pc39:** no `CassandraDaemon` running (checked `ps`); `~/s4-dps-run` removed; build trees removed; logs kept at `~/s4-dps-logs/`.
