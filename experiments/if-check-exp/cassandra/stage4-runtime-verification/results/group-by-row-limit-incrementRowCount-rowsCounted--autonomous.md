# group-by-row-limit-incrementRowCount-rowsCounted--autonomous — stage-4 results  <!-- file: results/group-by-row-limit-incrementRowCount-rowsCounted--autonomous.md; the stem ends in --guided or --autonomous -->

> **Case:** [`group-by-row-limit-incrementRowCount-rowsCounted--autonomous`](../../stage3-ai-deep-read/cases/group-by-row-limit-incrementRowCount-rowsCounted--autonomous.md)
>
> **Status:** verdict filed (2026-10-27)
>
> **Outcome class:** true positive (estimate `positive`; unit **Confirmed — caps**, cluster **Confirmed — caps**, with a recorded numeric miss in B3f, section 4.2 part 6)
>
> **Agent:** autonomous (the suffix of the case-file stem). "§9a" below means each tier's predictions and conclusions table: B2f and B2g (unit), B3f and B3g (cluster); "§9b–§9e" means B2a–B2e or B3a–B3e; the case file's feedback section is its section D.

## 1. Before run 1 — design audit and freeze

| Field | Content |
|---|---|
| **Case-file version** | Repository HEAD `93d6365` (the case file is untracked there; the orchestrator commits it). sha256 of the whole file after the audit's amendments A1-A12 (2026-10-27, before any run; section D was filled after run 1): `c7de0a0adf7ff078cdb0851545be04edec598526b08d28ebf0a18b3cdcf395f0`. sha256 of the frozen prediction and conclusion tables (text of B2f, B2g, B3f, B3g, from `**B2f.` up to `**B2h.` and from `**B3f.` up to `**B3h.`, concatenated; copy at `~/s4-b11-b78-logs/freeze-pred.txt` on pc07): `240da81c50721a2717a6a994887ada8264b0d7572aef0403626b9b85dee260b2`. Frozen before any reading (2026-10-27 07:25 UTC (the first freeze, 07:21 UTC, hashes 5856bf45... / 012de52c..., was superseded by A10 before any run: the unit shakedown at 2000 rows, an instrument check, showed that p=1 makes a second client page); `~/s4-b11-b78-logs/freeze-time.txt`). The original file (before amendments) is kept at `~/s4-b11-b78-logs/case-original.md`. Section D changes after the run and is outside the table hash. |
| **Harness** | `harness/group-by-row-limit-incrementRowCount-rowsCounted--autonomous/` (files listed in its README; not committed by this session, the orchestrator commits) |
| **Tiers and values** | Unit (B2): CQLTester, 1 partition x 50000 rows x 1 KiB; page size p in {1, 7, 1000, 10000, unset}; control `SELECT *` with `LIMIT p`. Cluster (B3): two nodes (loopback, port slot 8), RF=2, heap 512 MB, tmpfs; 1 partition x 200000 rows x 4 KiB (`ks.t`), fetch size in {100, 1000, 10000, 100000, 1000000, unset}, 3 repetitions; guardrail arm (`page_size_fail_threshold` 20000, ordinary role); controls: plain `SELECT *`, 100-byte rows (`ks.s`), idle baseline, both nodes sampled. |
| **Audit bottom line** | **Ready after amendments** — 2026-10-27 (A1-A12 applied) |

### 1.1 Design audit

| Group | Check | Rating (Met / Partly / Not met) | Note (section checked) |
|---|---|---|---|
| A. Core question | constrained quantity is memory or disk bytes | Partly | A2/A5: the constrained quantity is a row count (`rowsCounted` vs `rowLimit`); the byte size is derivable (rows of 1 KiB / 4 KiB) and the file names the byte-size caveat in its Estimate line. Accepted as a count with a derivable byte size. |
| A. Core question | knob varied, ≥ 3 values incl. default — or another approach, with the reason | Met | B2b: p = 1, 7, 1000, 10000, unset (default 10000); B3b: 100, 1000, 10000 (default), 100000, 1000000, unset. |
| A. Core question | real resource measured, not only the counter (gap named) | Partly | B2d: counter plus serialised response size and thread-allocated bytes (heap itself "cannot be observed" in a unit test, named). B3d: peak heap by `jstat`; A7 defines it as post-GC occupancy and adds a JMX poller because sampled `used` holds garbage; the per-request live heap remains unobservable (named gap). |
| A. Core question | usage driven to the limit and past it | Met | B2c/B3c: one group of 50000 / 200000 rows is far above every rowLimit tested; B3 fetch sizes 100000 and 1000000 are meant to exceed the 512 MB heap (B3c arithmetic: 100000 rows x 4 KiB = 400 MB). |
| B. Logic | each step says what it establishes | Met | B2e / B3e steps name data, grid, repeat with paging off, guardrail. |
| B. Logic | prediction stated in numbers or a clear relation | Met after A5, A7, A9 | B2f sub-read counts were wrong (ceil instead of floor+1: `DataLimits.java:1041`), bytes-per-row had no bound, "peak heap" had no definition and "severe GC" no measure; amended before any reading. |
| B. Logic | every plausible outcome has a conclusions row with its evidence | Met after A5, A9 | Rows exist for cap not binding, bytes not scaling, count mismatch, paging-off default, flat peak, 1000000 succeeding low, streaming, OOM-only-at-large; a catch-all "Not confirmed (no matching row)" was added to both tables. |
| B. Logic | confirmation needs ceiling-follows-knob and direct disallow evidence | Met | Ceiling: max rows per sub-read == p (B2g row 1) and heap following fetch size (B3g row 1). Direct evidence that the `:986` branch fired: white-box `rowsCounted == p` with `isDone` false and the Byteman trace `rows=p unfinished=true` per sub-read. |
| B. Logic | alternative explanations and their controls | Met | B2h/B3h: plain `SELECT * LIMIT` (not an artifact of GROUP BY), 100-byte rows (bytes, not rows, drive heap), idle baseline, coordinator vs replica. |
| C. Specific | a human can follow it from the intro and §9a | Met | Intro table, A1-A5, B1. |
| C. Specific | an AI can run §9b–§9e without re-deriving the code path | Partly | The serialised-size instrument was described ("toDebugString or the length of the built buffer") but not specified: A4 specifies it. B3e step 3 "restart the nodes (or force GC)" is two options: the harness forces a full GC before each cell and restarts a node found dead. |
| C. Specific | knob, values, workload, commands, observables, sampling, stop conditions exact | Partly | Gaps filled by amendments: `count(*)` does not select `v`, so the replica would not read the blob (A2, found by reading `ColumnFilter` use in the aggregation path; independent of any reading); guardrail needs a non-superuser (A1, A8); client (A8); timeouts (A6). |
| D. Runnable | harness and environment prerequisites exist or are listed | Met | JDK 11, Ant, build-test as in environment.md; probe, run scripts and analyzers are step-1 work. |
| D. Runnable | workload arithmetic reaches the limit (data, time, disk, memory) | Met | Unit: 50 MB data, 1 GiB test heap. Cluster: 800 MB x 2 replicas on tmpfs (126 GB free); loads 200000 rows x 4 KiB (about 90 s per 500 MB in a sibling run); a P=100 scan is 2001 sub-reads (sibling: 5001 sub-reads in 7.5 s). The 3-repetition grid is about 40 queries per fetch size at most. |
| D. Runnable | load-bearing citations spot-checked against the pinned source | Met | Checked in cassandra-5.0.9: `DataLimits.java` :349, :367, :679, :726-747 (`forPaging`, `forGroupByInternalPaging`), :806-810 (`isExhausted`), :926-957 (`applyToRow`), :983-988 (the target at :986), :1017-1030, :1033-1048 (`:1041`); `SelectStatement.java` :114, :517 (guardrail call), :893-914, :1923 (via grep of `getPageSize`); `AggregationQueryPager.java` :222-250; `Guardrails.java` :236-246; `Config.java` :873-874; `conf/cassandra.yaml` :2089-2090. All as cited. |

| # | Recommendation | Applied? | Why |
|---|---|---|---|
| A1 | Note that the page_size guardrail skips superusers / internal calls | applied 2026-10-27 (A1; case file untracked, no commit) | B3e.5 would silently not fire under `AllowAllAuthenticator` |
| A2 | `count(v)` instead of `count(*)` in every GROUP BY query | applied 2026-10-27 | `count(*)` selects no regular column: the blob is not returned, so bytes-per-row and heap slope could not follow rows |
| A3 | 3000-group second table has no prediction: not run | applied 2026-10-27 | nothing to compare |
| A4 | Specify the serialised-size instrument | applied 2026-10-27 | B2d was descriptive only |
| A5 | Sub-read counts floor(N/p)+1; bytes-per-row bounds; paging-unset = 6 reads; catch-all row (B2f, B2g) | applied 2026-10-27 | `DataLimits.java:1041`; prediction must be contradictable |
| A6 | Two nodes = two JVMs on loopback (slot 8), tmpfs, timeouts raised | applied 2026-10-27 | shared-node rules; 10 s range deadline spans all sub-reads |
| A7 | Define "peak heap above baseline" (post-GC occupancy) and the instruments | applied 2026-10-27 | sampled `used` includes uncollected garbage |
| A8 | Authenticated ordinary role, Python driver, JMX guardrail setter | applied 2026-10-27 | guardrail arm; cqlsh cannot script the grid |
| A10 | Sub-read count at p=1 is 50002 over two client pages (B2f, B2g) | applied 2026-10-27, after the unit shakedown (an instrument check, not a reading) and before run 1 | top-level page size 1 equals the one group, so the pager is not exhausted and a second client page makes one more empty sub-read |
| A11 | Plain `SELECT *` control bounded to fetch 100, 1000, 10000 (x3) and 100000 (x1, 120 s timeout) (B3h) | applied 2026-10-27, before run 1 | the scale-5 cluster shakedown (an instrument check) showed that a plain page of 100000 rows stalls for 10 minutes and kills a node; outside the frozen tables |
| A12 | Load phase with a 2 GiB heap, measured phase at 512 MB (B3a) | applied 2026-10-27 after cluster attempt 1 (runbook defect D1, section 3); tier restarted | the load killed node 1 at 512 MB; outside the frozen tables |
| A9 | Measurable "severe GC"; comparison basis for "within 20 percent"; catch-all row (B3f, B3g) | applied 2026-10-27 | prediction must be contradictable |
| R-a | State in B1 that `forPaging(pageSize)` also sets `groupLimit` = page size for the first sub-read (`DataLimits.java:716-724`), so for a many-groups table the group limit and `rowLimit` both bind | left for stage 3 | wording only; does not change the traced path |
| R-b | The Estimate line says the cap is on "live rows"; tombstones/shadowed rows are not counted by `:986` | left for stage 3 | already in A3 of the case |

**Agreement criteria** — only if run 2 is chosen; not chosen (see 5.2).


## 2. Environment

| Field | Run 1 | Run 2 (fresh AI session, if done) |
|---|---|---|
| Date | 2026-10-27 (unit 03:33 EDT = 07:33 UTC; cluster 04:02-04:45 EDT) | not done |
| Node (CloudLab name and type) | `pc07` (`node0.jason92-320876`), 40 cores, 251 GiB; both cluster nodes are JVMs on this machine (loopback 127.0.8.1 / .2, port slot 8; other cases ran in parallel on the same node) | |
| OS and kernel (`uname -r`) | Ubuntu 22.04, `5.15.0-187-generic` | |
| JDK (`java -version`) | openjdk 11.0.32.1 2026-08-18 | |
| Ant (`ant -version`) | Apache Ant 1.10.12 | |
| Local source copy (from `cassandra/cassandra-5.0.9/` at repository commit …) | `~/s4-b11-b78` (unit; `ant build-test`) and `~/s4-b11-b78-c` (cluster; `ant jar`), both made by `copy-source.sh` from repository commit `93d6365` (`git describe`: `cassandra-5.0.9`, local baseline) | |
| Case-file commit / harness commit | case file untracked at `93d6365` (sha256 in section 1) / harness untracked (the orchestrator commits) | |
| Storage for node data | cluster: `/dev/shm` (tmpfs, 126 GB free), about 850 MB per node after compaction; unit: build directory on local disk `/dev/sda3` | |
| Full logs (path, outside the repo) | `~/s4-b11-b78-logs/run1/{unit,cluster}/` on pc07 (the cluster logs hold both nodes' `gc-n*.log*`, `system-n*.log`, `b78-n*.trace`, `heap-n*.csv`); the aborted first cluster attempt: `~/s4-b11-b78-logs/run1a-aborted-load-oom/`; shakedowns `shake1..3`, `cshake1`, `shake2` | |

## 3. Runbook defects

| # | Run | Step (§9b–§9e) | Problem | Fix | Decision (date) | Case-file commit with the fix |
|---|---|---|---|---|---|---|
| D1 | cluster attempt 1 | B3a / B3c (load) | Loading 200000 rows x 4 KiB into one partition with the filed 512 MB heap killed node 1 (live set 465 MB of 512 MB, a run of `Pause Full ... 465M->465M`, the JVM ended by `-XX:OnOutOfMemoryError="kill -9 %p"` of `cassandra-env.sh`) 61 s into the load, 33816 client errors, before any query. | Amendment A12: load with a 2 GiB heap, restart both nodes at the measured 512 MB heap before the idle baseline; every measurement runs at 512 MB. Prediction and conclusions unchanged; the tier restarted from its beginning as run 1. Attempt 1's logs: `~/s4-b11-b78-logs/run1a-aborted-load-oom/`. | 2026-10-27 | untracked file (no commit) |
| D2 | unit shakedown (2000 rows; not a reading) | harness, B2f | (a) A single-partition `SELECT` yields a `SinglePartitionReadCommand.Group`, not a `ReadCommand` (ClassCastException): harness fixed. (b) At p = 1 the sub-read count was 2002, not 2001: the one group fills the top-level page size 1, so the pager is not exhausted and a second client page makes one more empty sub-read. Prediction (3) amended (A10), frozen tables re-hashed before run 1. | A10 | 2026-10-27 | untracked file |
| D3 | cluster shakedowns (scale 50 and 5; not readings) | harness, B3h | (a) The plain `SELECT *` control at fetch 100000 stalled 10 minutes and killed a node (amendment A11 bounds the control). (b) An `OutOfMemoryError` leaves no line in `system.log` (`kill -9`), so node death is the OOM evidence (analyzer rule, section 4.2 part 5). (c) `system.log` timestamps are UTC, `gc.log` ones local with offset: handled in the analyzer. (d) Post-GC occupancy needs a GC pause inside the window; short rejected queries have none (fallback to sampled `used`, analyzer docstring). | A11; harness only | 2026-10-27 | untracked file |

Not a defect, a calibration: every local sub-read closes K = 2 `GroupByAwareCounter` instances (calibrated on a query with one small sub-read, both nodes), so each sub-read appears twice in the Byteman traces; K is read from the `calibration` row of `cells.jsonl`.

## 4. Run 1

**Scope:** unit tier (B2) all cells as filed; cluster tier (B3) as amended (A6-A12): two nodes at 512 MB, ks.t 200000 rows x 4 KiB in one partition, fetch size 100 / 1000 / 10000 / 100000 / 1000000 / unset x 3 repetitions (GROUP BY), plain `SELECT *` control at 100 / 1000 / 10000 (x3) and 100000 (x1), 100-byte rows (ks.s) at 10000 and 100000, guardrail arm. **Command log:** `run1/unit-summary.txt`, `run1/cluster-session.txt`; raw readings `run1/unit-b78-unit.txt`, `run1/cluster-cells.jsonl`, `run1/cluster-gcrun.jsonl`; analyzer output `run1/cluster-analysis.txt`; node-death evidence `run1/cluster-death-evidence.txt`; self-check `run1/selfcheck.txt`.

### 4.1 Readings

**Unit tier** (the analyzer printed every prediction as an `EXPECTED:` line: 35 PASS, 0 FAIL, `run1/unit-summary.txt`; one group of 50000 rows x 1 KiB, `SELECT pk, count(v) ... GROUP BY pk`; 2 timed repetitions each, identical)

| Test or assertion | Result | Evidence (file) |
|---|---|---|
| White-box counter after the first sub-read, p = 1 / 7 / 1000 / 10000 / unset | rowsCounted = 1 / 7 / 1000 / 10000 / 10000 (never p+1), groups = 0, isDone false | `run1/unit-b78-unit.txt` (`B78 W`) |
| Total rows read | 50000 in every cell | `B78 E` |
| Max rows per sub-read | = p (1, 7, 1000, 10000; unset 10000) | `B78 E` |
| Sub-reads with exactly p rows | floor(50000/p): 50000 / 7142 / 50 / 5 / 5, and at most one other non-empty | `B78 E` (atMax, nonEmpty) |
| Sub-read count | 50002 (two client pages) / 7143 / 51 / 6 / 6 = floor(50000/p)+1 (+1 at p = 1, A10) | same |
| Serialised size of the first sub-read | 1,059 / 7,269 / 1,035,993 / 10,359,994 / 10,359,994 bytes = 1059 / 1038 / 1036.0 / 1036.0 per row; size(10000)/size(1000) = 10.000 | `B78 W` (firstReadBytes) |
| Control `SELECT ... LIMIT p`, page size p | rows = p (7, 1000, 10000); first-read bytes identical to the GROUP BY read's (1036.0 per row) | `B78 C`, `B78 CB` |
| Thread-allocated bytes over the whole drain | 520 / 137 / 73.9 / 73.5 / 73.5 MB for p = 1 / 7 / 1000 / 10000 / unset (total allocation does not follow p; the per-sub-read size does) | `B78 E` |

**Cluster tier** (post-GC peak above baseline = max occupancy after a GC pause inside the query window minus the occupancy after the forced full GC before the cell, node 1; mean of the repetitions; idle `used` 81 MB / 79 MB)

| Capacity value | Run | Observable (B3d) | Reading | Evidence (file) |
|---|---|---|---|---|
| fetch 100 | 3 GROUP BY | rows read, sub-reads, max rows per sub-read; peak above baseline; pause share | 200000, 2001, 100; +2.0 MB (1, 2, 3); 1 percent | `run1/cluster-analysis.txt`, `run1/selfcheck.txt` |
| fetch 1000 | 3 | same | 200000, 201, 1000; +12.3 MB (8, 12, 17); 2 percent | same |
| fetch 10000 | 3 | same | 200000, 21, 10000; +314.3 MB (295, 324, 324); 11-12 percent GC; peak occupancy 395 MB | same |
| unset (paging off) | 3 | same | 200000, 21, 10000; +326.7 MB (328, 360, 292); peak occupancy 409.7 MB (within 3.6 percent of fetch 10000) | same |
| fetch 100000 | 3 | outcome | node 1 killed in 3 of 3 (rep 2 and 3 also node 2); each ending in `Pause Full (G1 Humongous Allocation) X->X` runs; 0 rows returned | `run1/cluster-death-evidence.txt`, `run1/cluster-cells.jsonl` |
| fetch 1000000 | 3 | outcome | both nodes dead after each of 3 queries; 0 rows returned | same |
| plain `SELECT *` control, fetch 100 / 1000 / 10000 | 3 each | peak above baseline | +1.0 / +4.0 / +244 MB; all 200000 rows returned (wall 9.9 s / 7.2 s / 7.0 s) | `run1/cluster-analysis.txt` |
| plain `SELECT *`, fetch 100000 | 1 | outcome | client timeout after 120 s, node 2 found dead | same |
| 100-byte rows (ks.s), GROUP BY fetch 10000 / 100000 | 3 each | outcome; peak above baseline | no error, no death; +4 MB / +112 and +128 MB (two reps had GC pauses in the window; one had none) | same |
| guardrail arm (`page_size_fail_threshold` 20000, role `app`) | fetch 10000 x1; fetch 100000 x3 | outcome; heap | 10000 passes (+345 MB); 100000 rejected in 14 / 4 / 6 ms with "Guardrail page_size violated: Aborting query for table t, page size 100000 exceeds fail threshold of 20000."; sampled `used` growth 0.0 MB | `run1/cluster-session.txt`, `run1/selfcheck.txt` |
| mechanism (Byteman traces, K = 2) | fetch 100 / 1000 / 10000 / unset | rows per sub-read, sub-reads | max rows per line = fetch (10000 for unset), sub-reads floor(200000/fetch)+1 = 2001 / 201 / 21 / 21, node 1 served nearly all of them | `run1/cluster-analysis.txt` |
| node health | whole run | deaths, restarts | restarts after deaths: n1 = 6, n2 = 6 (all in the large-fetch cells); no stray process; tmpfs removed | `run1/cluster-session.txt` |

### 4.2 Conclusion and logic

1. **Validity** — Valid. The limit was reached and passed: the filed arms at fetch 100000 and 1000000 exceed the 512 MB heap and kill the nodes, so the instrument can see the effect [observed: `run1/cluster-death-evidence.txt`, `run1/cluster-cells.jsonl`]. First-trigger check passed: a fetch-1000 GROUP BY leaves 400 trace lines with rows = 1000, groups = 0, unfinished = true, none above 1000 [observed: `run1/cluster-session.txt`]. "Hold fixed": same flushed and compacted data (one SSTable, 827 MB, 1 partition on each node, [observed: session log, `tablestats`]); heap 512 MB at every measurement (A12), full GC and a 3 s settle before each cell, idle baseline 81 / 79 MB before any query [observed]; row cache off. Unit: the first-trigger counter reads rowsCounted = p with isDone false [observed: `run1/unit-b78-unit.txt`].
2. **Readings** — Unusual: (a) at fetch 100000 and 1000000 every repetition ended with a dead node and 0 rows returned, and repetitions 2 and 3 of fetch 100000 and all of fetch 1000000 lasted 147-301 s before the client saw the connection close (the last `Pause Full (G1 Humongous Allocation)` lines of the dead node fall at the end of each window) [observed: `run1/cluster-cells.jsonl`, `run1/cluster-death-evidence.txt`]; (b) node 2 was also found dead after 6 of the 7 large-fetch queries although the client talked only to node 1 (node 2 holds the same data and was ended the same way) [observed: `dead_nodes` in `run1/cluster-cells.jsonl`; why node 2 read at all is not established]; (c) the filed band for fetch 10000 (+100 to 300 MB) was exceeded: +314 MB; (d) 100-byte rows at fetch 100000 sit at +112 to +128 MB, not "about 10 MB x copies" [observed].
3. **Matched row** — Unit, B2g row 1, "max rows per sub-read == p, bytes linear in p: claim supported": max rows per sub-read = p for every p, first-read bytes 1036.0 per row at 1000 and 10000 and size(10000)/size(1000) = 10.000 [observed: `run1/unit-b78-unit.txt`]. Cluster, B3g row 1, "peak heap rises with fetch size and PAGING OFF matches 10000: claim supported": post-GC peak above baseline 2.0 -> 12.3 -> 314.3 MB at fetch 100 -> 1000 -> 10000, unset 326.7 MB (peak occupancy 409.7 vs 395.3 MB) [observed: `run1/cluster-analysis.txt`], together with the last row, "OOM only at the large sizes, none at 100 to 10000: claim supported with boundary": fetch 100 / 1000 / 10000 / unset complete with no node death, fetch 100000 and 1000000 kill the nodes [observed].
4. **Excluded rows** — Unit: any sub-read above p rows (row 2): max = p everywhere [observed]; bytes unchanged with p (row 3): first-read bytes scale 10.000 x for 10 x p [observed]; sub-read count mismatch (row 4): all counts equal floor(rows/p)+1 (+1 at p = 1) [observed]; paging unset gives one 50000-row read (row 5): 6 sub-reads of at most 10000 rows, identical to p = 10000 [observed]. Cluster: unset far above 10000 or OOM (row 2): +326.7 vs +314.3 MB, no node death [observed]; peak identical across 100 and 100000 (row 3): 2.0 MB vs a dead node [observed]; 1000000 succeeds below the 10000 run (row 4): both nodes dead at 1000000 [observed]; 100000 succeeds well below the model (row 5): dead node in 3 of 3 [observed].
5. **Observed vs. inferred** — Inferred: (i) that a node found dead right after a query died of `OutOfMemoryError`: no log line exists (the JVM is ended by `kill -9`), the evidence is the run of `Pause Full (G1 Humongous Allocation) X->X` pauses with no reclaim in `gc.log` right before the end of each death window, the absence of any external kill (only the script stops nodes, and only in cleanup and in the guardrail restart) and the test of the same behaviour at scale 5 in the shakedown [inferred: `run1/cluster-death-evidence.txt`]; (ii) that post-GC occupancy stands for live data attributable to the read (the filed gap: no per-request live heap, B3d); (iii) that K = 2 trace lines per sub-read are two copies of the same read [inferred: every window holds a multiple of 2 lines, sub-read counts equal floor(N/p)+1 after halving, the calibration query leaves exactly 2 lines]; (iv) that the thread-allocated bytes of the calling thread cover the whole local read in the unit tier [inferred: the read runs on the calling thread via `fetchPageInternal`].
6. **Deviations and gaps** — (a) Amendments A1-A12 and defects D1-D3 (sections 1 and 3). (b) Numeric misses of the frozen B3f: at fetch 10000 the post-GC peak above baseline is +314.3 MB, above the filed band +100 to 300 MB by 4.8 percent; the analyzer prints this `EXPECTED:` line as FAIL. No B3g row is about magnitude, the relation (rises with the fetch size, unset like 10000, OOM only at the large sizes) holds, so the row is matched and the miss is recorded, not edited away. The "100-byte rows ... heap about 10 MB x copies" control (B3h 2) read +112 to +128 MB against my analyzer threshold of 100 MB (an interpretation of "x copies", fixed before the run); the control's point (no OOM, no error, while 4 KiB rows at the same fetch size kill the node) holds. (c) The load phase ran with a 2 GiB heap (A12). (d) The plain `SELECT *` control is bounded (A11); its fetch 1000000 and unset arms are not run. (e) Peak live heap per query is not observable; post-GC occupancy and sampled `used` are proxies, and G1 pauses inside a short window are few at small fetch sizes (see the "d1" values for fetch 100, 1000 which rest on 3 to 20 pauses). (f) The unit total allocation (73.5 vs 73.9 MB) does not follow p; only the per-sub-read size does, which is what the claim states.
7. **Core question** — Yes, the row limit `rowLimit` = page size caps the data read per internal sub-read, and with it the heap needed. With one group of 50000 (unit) or 200000 (cluster) rows, every sub-read stops at exactly p rows (steps 1-3: parts 3 and 4), the first sub-read's serialised response is 1036 bytes per row times p, and on the 512 MB heap the post-GC peak above baseline rises 2.0 -> 12.3 -> 314 MB for fetch 100 -> 1000 -> 10000, paging unset behaves like 10000, and fetch 100000 and above, whose sub-read does not fit (400 MB of 4 KiB rows), kills the node. It is a row-count cap, not a byte cap: 100-byte rows at the same fetch size 100000 complete with +112 to +128 MB.

**Conclusion (one line):** Unit B2g row 1, cluster B3g rows 1 and 6 — claim confirmed: the GROUP BY row limit (page size) caps the rows, and with them the heap, per internal read (effect: caps; byte-size caveat as filed).

## 5. Self-check of run 1 — AI

### 5.1 Check of run 1's conclusion

`harness/.../selfcheck.py` re-parses the raw files with its own code (the probe's stdout in `ant.log` against `b78-unit.txt`, `cells.jsonl`, `b78-n*.trace`, `gc-n*.log*`, `heap-n*.csv`, `system-n*.log`); output `run1/selfcheck.txt`. It recomputed the unit numbers (identical to the analyzer's; the `ant.log` copy equals the text file) and, per cluster query, rows, sub-reads, max rows per line, baseline, post-GC peak, delta, pause share and deaths. The deltas recomputed per repetition (fetch 10000: 295 / 324 / 324; fetch 1000: 8 / 12 / 17; fetch 100: 1 / 2 / 3; unset 328 / 360 / 292) give the means the analyzer printed. I also read the GC log lines before the first death by hand (`04:12:11.409` and `04:12:11.566`, `Pause Full (G1 Humongous Allocation) 301M->301M(512M)` twice, then nothing) and the guardrail rejections in the session log. 0 trace lines lie outside a timed window.

| Part | Holds? (yes / no) | Note (file re-read) |
|---|---|---|
| 1. Validity | yes | `cluster-session.txt` (first trigger, loads with 0 errors, 827 MB single SSTable per node), `selfcheck.txt` (K = 2, no unattributed trace lines, node baselines 77-84 MB). |
| 2. Readings | yes | Items (a)-(d) re-read in `selfcheck.txt` and `cluster-death-evidence.txt`; the 300 s waits are the client noticing a closed connection. |
| 3. Matched row | yes | Unit and cluster numbers re-derived independently (`selfcheck.txt`); every part of the quoted rows holds. The magnitude miss at fetch 10000 is not part of any row. |
| 4. Excluded rows | yes | Each exclusion cites a number that `selfcheck.txt` reproduces. |
| 5. Observed vs. inferred | yes | Inferred (i) (death = OOM) rests on the GC log pattern and on no other killer; it is the weakest link and is stated; the verdict for the rising-with-fetch relation (fetch 100-10000, unset) does not depend on it. |
| 6. Deviations and gaps | yes | The 4.8 percent band miss and the B3h 2 figure are recorded as found. |
| 7. Core question — the steps from reading to answer follow the audited logic | yes | Hypothesis B1, test B2/B3, prediction B2f/B3f, rows B2g/B3g, in that order; the controls (plain `SELECT *`, 100-byte rows, guardrail) were run and moved as the logic needs. |

### 5.2 Run 2?

**No** (2026-10-27). Both tiers are cheap and agree; the mechanism (exactly p rows per sub-read) is deterministic in the unit tier, and the cluster relation spans two orders of magnitude (2 -> 314 MB, then node death). The weak link (death read as OOM) is supported by the GC log and would not change the matched row even if the large-fetch arms were read only as "not completed". A rerun at 1 GiB heap would add a boundary point (fetch 100000 fits?) but is a different design.

## 6. Run 2 — fresh AI session (optional)

Not done (section 5.2).

## 7. Comparison — only if run 2 was done

Not applicable.

## 8. Verdict — AI

Jingsong may overrule any verdict at any time; record an override here with its date and reason.

**Stage-3 estimate:** positive. **Outcome class:** true positive (positive, caps).

**Claim tested:** (B1) For a GROUP BY query, the number of live rows read in one internal sub-read equals `min(rowLimit, rows available)`, where `rowLimit` is the client fetch size (10000 when unset). Replica- and coordinator-side heap during the query scales with that value and is bounded when it is small, even if the partition holds far more rows. "Confirmed" below means this claim held.

| Tier | Verdict (§9a row; for an autonomous file, the B2g / B3g row) | Effect on the constraint | Basis | Date |
|---|---|---|---|---|
| Unit | B2g row 1: **Confirmed** — max rows per sub-read = p for p = 1, 7, 1000, 10000, unset (rowsCounted = p, never p+1); first-read bytes 1036 per row, linear in p | caps (a row-count cap; byte size = rows x row size) | run 1 + self-check | 2026-10-27 |
| Cluster | B3g rows 1 and 6: **Confirmed** — post-GC peak above baseline rises with the fetch size (+2 / +12 / +314 MB at 100 / 1000 / 10000), paging unset matches 10000, nodes die only at fetch 100000 and above; fetch-10000 band missed by 4.8 percent (recorded) | caps (soft: the cap is the fetch size, which a client sets; the guardrail `page_size_fail_threshold` rejected 100000 in 4-14 ms with a flat heap) | run 1 + self-check | 2026-10-27 |

**Feedback filed:** the case file's section D updated (amendments A1-A12 and the stage-4 results); no section of the trace was refuted. **Open points for the user:** (1) the +314 MB reading at fetch 10000 against the filed band of 100-300 MB, and the 100-byte control (+112 to +128 MB vs "about 10 MB x copies"); (2) node death at fetch 100000 is read as OOM from the GC log, since the JVM is ended by `kill -9`; (3) the heap for the load had to be 2 GiB (A12); (4) with a client that sets a fetch size of 100000 or more, the 10000 default is the only thing standing between a GROUP BY and heap exhaustion on a 512 MB heap unless `page_size_fail_threshold` is set (it only applies to non-superusers). **Upstream / doc candidates:** none for a bug. Doc note: for GROUP BY the page size is also the internal row limit (`SelectStatement.getDataLimits` passes it in the `rowLimit` slot, default 10000), so it bounds memory per sub-read, and a GROUP BY over one very large partition is read in full in sub-reads of that size. **Leftovers on pc07:** no `CassandraDaemon` or helper of this case running (checked `ps`); tmpfs run directory removed (`/dev/shm/s4-b11-b78-run1` gone); kept on the node: working trees `~/s4-b11-b78`, `~/s4-b11-b78-c`, logs `~/s4-b11-b78-logs/` (11 MB, with the aborted attempt and shakedowns).
