# group-by-limit-incrementGroupCount-groupLimit--autonomous — stage-4 results  <!-- file: results/group-by-limit-incrementGroupCount-groupLimit--autonomous.md; the stem ends in --guided or --autonomous -->

> **Case:** [`group-by-limit-incrementGroupCount-groupLimit--autonomous`](../../stage3-ai-deep-read/cases/group-by-limit-incrementGroupCount-groupLimit--autonomous.md)
>
> **Status:** verdict filed (2026-10-27)
>
> **Outcome class:** true negative (estimate `negative`; unit **Confirmed — does not cap**, cluster **Confirmed — does not cap**)
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
| **Case-file version** | Repository HEAD `93d6365` (the case file is untracked there; the orchestrator commits it). sha256 of the whole file after the audit's amendments A1-A14 (2026-10-27): `64e954f416ab47f4e1ed1140f510f7c7f1e9f7ec727078596e434d7a3245b184`. sha256 of the frozen prediction and conclusion tables (text of B2f, B2g, B3f, B3g including their amendment notes, from `**B2f.` up to `**B2h.` and from `**B3f.` up to `**B3h.`, concatenated; copy at `~/s4-b11-l79-logs/freeze-pred.txt` on pc12): `5bc40010347d29d0e07351c7c6d557e82ed036bdcb5549f9a413cd6e4ad4c0b9`. Frozen 2026-10-27 before any reading. Section D (feedback) is outside the table hash and changes after the run. |
| **Harness** | `harness/group-by-limit-incrementGroupCount-groupLimit--autonomous/` (files listed in its README; not committed by this session) |
| **Tiers and values** | Unit (B2): CQLTester; table S = 1 partition x 1,000,000 rows x 100 B read as slices r in {1000, 100000, 1000000}, table M = 1000 partitions x 1000 rows x 100 B; g in {1, 10, 1000}, p in {100, 10000}; control `SELECT * ... LIMIT n`. Cluster (B3): one node on tmpfs, heap 1 GB, `ks.t` 1 partition x 1,000,000 rows x 1 KiB, `ks.g` 3000 partitions x 300 rows x 1 KiB; g in {1, 100, 100000}, p in {100, 10000}; control n in {1000, 10000, 100000}. |
| **Audit bottom line** | **Ready after amendments** — 2026-10-27 (A1-A14 applied) |

### 1.1 Design audit

| Group | Check | Rating (Met / Partly / Not met) | Note (section checked) |
|---|---|---|---|
| A. Core question | constrained quantity is memory or disk bytes | Partly | A2: the quantity is a count of groups (an integer), not bytes; its byte size is derivable (rows of 100 B or 1 KiB) and the claim (B1) is about heap and bytes read, so it is accepted as a count with a derivable size. |
| A. Core question | knob varied, ≥ 3 values incl. default — or another approach, with the reason | Met | B2b: g = 1, 10, 1000 (default: none); B3b: g = 1, 100, 100000; r and p varied too. |
| A. Core question | real resource measured, not only the counter (gap named) | Met after A4, A11 | B2d names thread allocation and pool peaks; B3d heap, GC log and bytes read. Live heap per query is named as not observable; A4/A11 specify the proxies (allocation, summed pool peaks, `rchar` on tmpfs). |
| A. Core question | usage driven to the limit and past it | Met | The many-small-groups tables reach the limit (g = 1, 10 on M; g = 1, 100 on `ks.g`) and g = 1000 / 100000 reach or pass the group count; the single huge group never reaches it by design (B2c, B3c). |
| B. Logic | each step says what it establishes | Met | B1, B2e/B3e steps name data, grid, control. |
| B. Logic | prediction stated in numbers or a clear relation | Met after A6, A13 | "about 1000*g", "flat within 10%" had no bounds for the peak-heap proxy and the disk observable; A6/A13 give exact counts and bands. |
| B. Logic | every plausible outcome has a conclusions row with its evidence | Met after A7, A14 | Rows: confirmed, mechanism-only nuance, early stop (claim wrong), linear in g (refuted), control moved, control flat / limit not reached. A7/A14 scope the last row. No-match = "Not confirmed (no matching row)". |
| B. Logic | confirmation needs ceiling-follows-knob and direct disallow evidence | Met after A12 | The direct evidence for this negative claim is the counter state: isDone() false while rows stream (white-box, trace) and isDone() true when a small group closes (first-trigger check A12, M and `ks.g` cells). |
| B. Logic | alternative explanations and their controls | Met | rowLimit (the p sweep) is the competing bound; the non-GROUP BY `LIMIT n` is the positive control (B2h, B3h). |
| C. Specific | a human can follow it from the intro and §9a | Met | Header table, A1-A3 and B1. |
| C. Specific | an AI can run §9b–§9e without re-deriving the code path | Partly | "rows pulled" and "spy" instruments were described, not specified; A4 and A11 specify them, and the harness implements them. |
| C. Specific | knob, values, workload, commands, observables, sampling, stop conditions exact | Partly | Gaps filled by A2 (r sweep), A3 (table layouts), A5 (repetitions), A9-A10 (sizes, client), A12 (order). |
| D. Runnable | harness and environment prerequisites exist or are listed | Met | JDK 11, Ant, `copy-source.sh`; test class, run scripts and Byteman rule are step-1 work (harness folder). |
| D. Runnable | workload arithmetic reaches the limit (data, time, disk, memory) | Met after A8, A9 | Case-file B3c asked for 3 GB + 3 GB (3,000,000 rows) with 5 reps of 30 cells (about 3 GB scanned per query, at p = 100 30,001 sub-pages per query): too long for one session; A9 uses 1 GB and 0.9 GB on tmpfs (126 GB free), heap 1 GB, 1 warm-up + 3 timed. A group of 1e6 rows is 100x the 10,000-row page. |
| D. Runnable | load-bearing citations spot-checked against the pinned source | Met after A1 | `DataLimits.java` :658 (field), :990-995, :1011-1013, :1033-1046; `SelectStatement` :881, :895, :902, :911, :517; `AggregationQueryPager` :273-274. A1 corrects the `SelectStatement` lines (were 893-896, 901-902). The trace of A3 (a group is counted when closed; the new-group row is dropped at `isDoneForPartition()`) holds as written. |

| # | Recommendation | Applied? (amendment date and commit, or "left for stage 3") | Why |
|---|---|---|---|
| A1 | Correct `SelectStatement` line numbers; note that the fetch size is also the groups per client page | applied 2026-10-27 (case file untracked; no commit) | citation accuracy |
| A2 | Read the three group sizes r as slices `ck < r` of one partition | applied 2026-10-27 | B2b names r in {1000, 100000, 1000000} but B2c loads one table of 1e6 |
| A3 | Pin the layouts of S and M; sub-page count is floor(N/p)+1 | applied 2026-10-27 | `onClose` (:1041 area) counts the trailing group only when `rowsCounted < rowLimit` |
| A4 | Specify the unit instruments (rows leaving the counter, white-box counter, thread allocation, summed pool peaks) | applied 2026-10-27 | B2d described, not specified |
| A5 | Three repetitions, first discarded | applied 2026-10-27 | B2e said "5, medians"; time |
| A6 | Give B2f numbers: exact rows, group count, sub-page count, allocation band 10 percent, pool-peak band 1.5, M rows band, control "moved" | applied 2026-10-27 | prediction must be able to be contradicted |
| A7 | Scope B2g's "limit never reached" row | applied 2026-10-27 | S cannot reach it by design |
| A8 | tmpfs, 1 GB heap, 600 s timeouts | applied 2026-10-27 | `/local/tmp` not guaranteed; a P=100 full scan spans 10,001 sub-pages |
| A9 | Cluster sizes 1e6 x 1 KiB and 3000 x 300 x 1 KiB instead of 3e6 / 3000 x 1000 | applied 2026-10-27 | session time |
| A10 | Python driver client; 1 warm-up + 3 timed | applied 2026-10-27 | cqlsh cannot script timed repetitions |
| A11 | Cluster observables: JMX poller instead of `jstat`; `rchar` instead of `read_bytes`; Byteman rows-pulled trace | applied 2026-10-27 | tmpfs has no `read_bytes`; no per-query rows counter in the yaml/metrics |
| A12 | First-trigger check and order of cells; control values | applied 2026-10-27 | the disallow branch must be shown to fire before cells are read |
| A13 | Give B3f numbers (rows, sub-pages, bands 15 / 25 percent, small-group ratios) | applied 2026-10-27 | prediction must be able to be contradicted |
| A14 | Make B3g's rows decidable | applied 2026-10-27 | "linearly" and "g exceeds the group count" had no thresholds |
| R-a | State in A2 that the group limit is a per-query count and not a setting that is configured for memory | left for stage 3 | wording only |
| R-b | The whole-table scan time at p = 100 depends on the sub-page rate; a doc note on `LIMIT` | left for stage 3 | not needed for a valid run |

**Agreement criteria** — only if run 2 is chosen; filled before run 2 starts.
One row per observable in the case's §9d:

| Observable | Must match | Tolerance |
|---|---|---|
| `<observable>` | exactly / in shape | `<what counts as the same>` |

## 2. Environment

| Field | Run 1 | Run 2 (fresh AI session, if done) |
|---|---|---|
| Date | 2026-10-27 (unit 01:50 MDT = 07:50 UTC; cluster 01:51-02:07 MDT = 07:51-08:07 UTC; shakedowns 01:38-01:49 MDT, not readings) | not done |
| Node (CloudLab name and type) | `pc12` (`node1.jason92-320876`), 40 cores, 251 GiB, shared with other cases (this run: loopback 127.0.9.1, JMX 7190, Byteman agent port 19190 reserved, port slot 9) | |
| OS and kernel (`uname -r`) | Ubuntu 22.04, 5.15.0-187-generic | |
| JDK (`java -version`) | openjdk 11.0.32.1 | |
| Ant (`ant -version`) | Apache Ant 1.10.12 | |
| Local source copy (from `cassandra/cassandra-5.0.9/` at repository commit …) | `~/s4-b11-l79` (`ant build-test`, unit) and `~/s4-b11-l79-c` (`ant jar`, cluster), both `copy-source.sh` copies at repository HEAD `93d6365` (tag `cassandra-5.0.9`; `git status` of the source tree empty) | |
| Case-file commit / harness commit | case file and harness untracked at HEAD `93d6365` (orchestrator commits); case-file sha256 in section 1; harness md5 in `run1/unit-summary.txt` | |
| Storage for node data | unit: build tree on `/dev/sda3` (local); cluster: `/dev/shm` (tmpfs), 1 GB heap; `ks.t` live space 1,041,419,584 bytes after compaction (`run1/cluster-session.txt`) | |
| Full logs (path, outside the repo) | `~/s4-b11-l79-logs/run1/{unit,cluster}/` on pc12 (cluster: `l79.trace` 639,044 lines, `heap.csv`, `gc.log`, `system.log`, `debug.log`; about 51 MB in all); shakedowns `~/s4-b11-l79-logs/shake{1,2,3}` | |

## 3. Runbook defects

| # | Run | Step (§9b–§9e) | Problem | Fix | Decision (date) | Case-file commit with the fix |
|---|---|---|---|---|---|---|
| D1 | cluster shakedown 1 | B3e first-trigger check (A12 as first written) | The first-trigger query was a single-partition read (`WHERE pk = 0`), which closes K = 2 Byteman counters per sub-page, while every cell query is a range read that closes K = 4: the calibration was wrong by a factor 2 (rows read 40,000 for a 20,000-row group). | A12 now names the range query `SELECT pk, count(*) FROM ks.g GROUP BY pk LIMIT 1` (K = 4 on all queries) | 2026-10-27, before the freeze hash and before run 1 | untracked file (no commit) |
| D2 | unit shakedowns 1-2 | harness | `ClassCastException` (a single-partition read query is a `SinglePartitionReadCommand.Group`, not a `ReadCommand`) and `peakPools = 0` (the pool names differ per collector; now every HEAP pool). Instrument faults, not readings. | harness only | 2026-10-27 | n/a |

Not a defect, a calibration: every local range sub-page read closes K = 4 `GroupByAwareCounter` instances, so each sub-page appears 4 times in the Byteman trace; K was calibrated on the first-trigger query (`run1/cluster-analysis.txt`, first line) and every window holds a multiple of 4 lines.

## 4. Run 1

**Scope:** unit tier (B2) all cells as amended (A2-A7): S slices r in {1000, 100000, 1000000} x p in {100, 10000} x g in {1, 10, 1000}, M (1000 x 1000) p x g, control `SELECT * LIMIT n` in {100, 1000, 10000}; 3 repetitions per cell, the first discarded. Cluster tier (B3) all cells as amended (A8-A14): `ks.t` (1 x 1,000,000 rows x 1 KiB) with p in {10000, 100} x g in {1, 100, 100000}, 1 warm-up + 3 timed queries per cell, drift cell (no LIMIT, p = 10000) at start and end, control `SELECT * LIMIT n` in {1000, 10000, 100000} (paging off), `ks.g` (3000 x 300 rows x 1 KiB) with p x g. **Command log:** `run1/unit-summary.txt`, `run1/cluster-session.txt`; raw readings `run1/unit-l79-unit.txt`, `run1/cluster-cells.jsonl`, `run1/cluster-per-query.txt`; analyzer output `run1/cluster-analysis.txt`; self-check `run1/selfcheck.txt`; GC per cell `run1/cluster-gc-by-cell.txt`.

### 4.1 Readings

**Unit tier** (means of the 2 timed repetitions; the analyzer printed every prediction as an `EXPECTED:` line: 118 PASS, 0 FAIL, `run1/unit-summary.txt`)

| Test or assertion | Result | Evidence (file) |
|---|---|---|
| Instrument check (first trigger): M, g = 1, p = 10000, white-box counter | groups = 1, rowsCounted = 1000, isDone = true; at p = 100 the first sub-page holds 100 of the 1000 rows, isDone = false | `run1/unit-l79-unit.txt` (`L79 W ds=M`) |
| S (1 group), every r x p x g (18 cells): rows read, groups, sub-pages | rows = r in all 18 cells; groups = 1; sub-pages = floor(r/p)+1 (r = 1e6: 10001 at p = 100, 101 at p = 10000); max rows per sub-page = p | `L79 E ds=S` |
| S: white-box after one sub-page (r > p) | groups = 0, rowsCounted = p, isDone = false in every cell | `L79 W ds=S` |
| S: allocated bytes of the calling thread, max/min across g | r = 1e6: p = 100: 586.0 / 585.8 / 585.8 MB (1.0004); p = 10000: 443.26 MB for all g (1.0000); the other four (r, p) pairs 1.0000-1.0009 | `run1/selfcheck.txt` |
| S: summed heap-pool peak (`peakPools`), max/min across g | r = 1e6: p = 100: 271 / 267 / 267 MB (1.015); p = 10000: 272 / 302 / 302 MB (1.107, not monotone: g = 1000 is below g = 10); the other pairs 1.000-1.018 | same |
| M (1000 groups of 1000 rows): rows pulled and groups | rows = 1000, 10000, 1,000,000 and groups = 1, 10, 1000 for g = 1, 10, 1000 at both p | `L79 E ds=M` |
| M: allocation | p = 10000: 0.49 / 4.53 / 449.9 MB for g = 1 / 10 / 1000 (ratio g = 1000 over g = 10: 99.3) | same |
| M: white-box | p = 10000, g = 1: groups = 1, rowsCounted = 1000, isDone = true; g = 10 and 1000: stops on rowLimit (rowsCounted = 10000, groups = 9, isDone = false) | `L79 W ds=M` |
| Control `SELECT * ... WHERE pk = 1 LIMIT n` | rows = n = 100 / 1000 / 10000; allocation 49,976 / 447,800 / 4,422,200 bytes (ratio 88.5) | `L79 C` |

**Cluster tier** (means over the 3 timed queries of a cell; peak = max of `HeapMemoryUsage.used` sampled every 100 ms inside the query window; alloc = JVM-wide sum of thread-allocated bytes (idle noise median 175 KB/s); rchar = delta of `rchar` in `/proc/<pid>/io`; 69 `EXPECTED:` lines, all PASS: `run1/cluster-analysis.txt`)

| Capacity value | Run | Observable (B3d) | Reading | Evidence (file) |
|---|---|---|---|---|
| `ks.t`, p = 10000, g = 1 / 100 / 100000 | 3 / 3 / 3 | rows read (Byteman trace / 4), sub-pages, max rows per sub-page | 1,000,000 in every query; 101 sub-pages (= floor(1e6/10000)+1); max 10000 | `run1/cluster-analysis.txt`, `run1/selfcheck.txt` |
| same | | alloc per query; rchar; peak used; wall time | 6.1721 / 6.1719 / 6.1716 GB (1.0000); 1.0572 GB for all three (1.0000); 326 / 329 / 321 MB (1.026); 6157 / 6262 / 5602 ms | same |
| `ks.t`, p = 100, g = 1 / 100 / 100000 | 3 / 3 / 3 | rows read, sub-pages, max rows per sub-page | 1,000,000; 10001 sub-pages; max 100 | same |
| same | | alloc; rchar; peak used; wall time | 5.7424 / 5.7407 / 5.7410 GB (1.0003); 2.6750 GB for all three; 758 / 746 / 752 MB (1.015); 6984 / 7526 / 8082 ms | same |
| `ks.t`, no LIMIT, p = 10000, start vs end | 3 + 3 | alloc | 6.1828 GB vs 6.1715 GB | same |
| `ks.t`, isDone in the trace | all queries | `done` flag per sub-page | false in every sub-page but the last; at g = 1 the last (empty) sub-page reads rows = 0, groups = 1, done = true | same |
| `ks.g`, g = 1 / 100 / 100000 at p = 10000 | 3 each | rows read, groups, last sub-page done | 300 / 30,000 / 900,000 rows (= 300 x min(g, 3000)); groups 1 / 100 / 3000; done = true for g = 1 and 100, not for g = 100000 (limit above the 3000 groups: not reached, as predicted) | same |
| same | | rchar; alloc; wall; peak used | rchar 0.33 MB / 31.7 MB / 950 MB (ratios 97 and 30); alloc 2.0 MB / 186 MB / 5.57 GB; wall 5 / 194 / 5190 ms; peak used 152 / 299 / 329 MB | same |
| `ks.g` at p = 100 | 3 each | rows read, groups; rchar; alloc; wall; peak used | same rows and groups; rchar 0.72 MB / 75.6 MB / 2.27 GB; alloc 1.8 MB / 175 MB / 5.24 GB; wall 6 / 274 / 7847 ms; peak used 152 / 644 / 757 MB | same |
| control `SELECT * ... LIMIT n`, n = 1000 / 10000 / 100000, paging off | 3 each | rows, alloc, rchar, peak used | rows = n; alloc 5.16 MB / 63.5 MB / 684 MB (ratio 132.6); rchar 1.0 / 10.4 / 104 MB; peak used 163 / 212 / 572 MB | same |
| node health | whole run | `system.log`, GC log | 0 `ERROR` lines (only the expected `WARN Aggregation query used without partition key`); no `OutOfMemoryError` (the 3 hits of the word are the JVM-argument echo, line 23); 33 full GCs in the whole run: 13 during the load phase (live set after 201-452 MB), 18 requested by `jcmd GC.run` between cells (live set 143-145 MB), 2 forced by humongous allocation in the first drift cell (live set after 179 and 191 MB); highest occupancy after a young pause inside a query window 916 MB (89 percent, first drift cell's warm-up and first query) | `run1/cluster-gc-by-cell.txt`, `run1/cluster-system-log-warn-error.txt`, `run1/selfcheck.txt` |

### 4.2 Conclusion and logic

1. **Validity** — Valid. The branch can fire: the first-trigger query (`ks.g ... GROUP BY pk LIMIT 1`, p = 10000) left four identical trace lines rows = 300, groups = 1, done = true [observed: `run1/cluster-session.txt`, 02:00:01]; the unit white-box counter shows groups = 1, isDone = true on M at g = 1, p = 10000 [observed: `run1/unit-l79-unit.txt`]; cluster `ks.g` g = 1 and 100 end with done = true [observed: `run1/cluster-analysis.txt`]. "Hold fixed" settings: heap 1 GB, row cache 0, same flushed and compacted data in every cell, 1 warm-up per cell, `jcmd GC.run` and an idle baseline before each cell, drift cell at both ends (6.1828 vs 6.1715 GB) [observed: `run1/cluster-session.txt`, `run1/cluster-analysis.txt`]. The positive control moved (unit ratio 88.5; cluster ratio 132.6) [observed]. The limit was reached where it can be (M, `ks.g` g <= 100) and not reached by construction in the single group and for g = 100000 on `ks.g` (B2g/B3g, amendments A7, A14).
2. **Readings** — Unusual: (a) K = 4 trace lines per range sub-page (calibrated, section 3). (b) Rows read are equal for every g, but `rchar` is 2.5 times larger at p = 100 than at p = 10000 (2.675 vs 1.057 GB) for the same 1e6 rows: the page size, not g, changes how many bytes are asked of the file (each sub-page re-seeks through the index) [observed: `run1/cluster-per-query.txt`]. (c) The sampled peak `used` is higher at p = 100 (750 MB) than at p = 10000 (320 MB), the opposite of what a per-sub-page buffer would give; the allocation per sub-page is 106 x smaller at p = 100 (0.574 vs 61.1 MB), so the sampled peak is a garbage level set by the collector's young-region sizing, not a measure of the buffer [inferred: allocation per sub-page from `run1/cluster-analysis.txt`; the G1 sizing explanation is not tested]. (d) Unit S r = 1e6, p = 10000: `peakPools` 272 / 302 / 302 MB for g = 1 / 10 / 1000 (spread 1.107), not monotone [observed]. (e) The occupancy after young pauses reached 916 MB (89 percent) once, in the first drift cell, and the same cell had 2 full GCs triggered by humongous allocation, after which the live set was 179 and 191 MB [observed: `run1/cluster-gc-by-cell.txt`, `gc.log` at 02:00:08 and 02:00:09].
3. **Matched row** — Unit, B2g row 1: "Huge-group rows pulled = r for all g, allocation and peak heap flat across g" — rows = r in 18/18 cells, allocation max/min <= 1.0009, `peakPools` max/min <= 1.107 (band 1.5), no monotone rise [observed: `run1/selfcheck.txt`]; with row 2 ("Rows pulled grows with g only in the small-group table, peak heap flat") — M rows = 1000 x g, allocation grows 99-fold from g = 10 to g = 1000 [observed]; and row 5 (positive control moves, g does not). Cluster, B3g row 1: "Huge table: bytes read and wall time equal for g = 1 and 100000; heap flat" — rows 1,000,000, alloc spread 1.0000 / 1.0003, rchar spread 1.0000, peak spread 1.026 / 1.015, wall 6157 vs 5602 ms and 6984 vs 8082 ms [observed: `run1/cluster-analysis.txt`]; with row 2 for `ks.g` ("bytes read grows with g, heap not governed by g") — rchar 0.33 / 31.7 / 950 MB for g = 1 / 100 / 100000 [observed]; and row 5 (control moves with n).
4. **Excluded rows** — Unit: row 3 (g = 1 stops after about p rows): rows 1e6 at g = 1, p = 100 and 10000 [observed]. Row 4 (allocation or peak follows g): allocation max/min 1.0009 or less; `peakPools` not monotone [observed]. Row 6 (control flat or limit never reached): control ratio 88.5; limit reached on M at g = 1 and 10 [observed]. Cluster: row 3 (g = 1 reads only about one sub-page): 101 / 10001 sub-pages and 1,000,000 rows at g = 1 [observed]. Row 4 (heap rises linearly with g): peak spread <= 1.026 on `ks.t`, no monotone rise [observed]. Row 6 (control flat; g above the group count): control ratio 132.6; the g = 100000 cell on `ks.g` is the expected "above the group count" cell and is not used for the claim [observed].
5. **Observed vs. inferred** — Inferred: (i) allocation volume, summed pool peaks and sampled `used` stand for the memory use of the read (no live-heap-per-query attribution exists: B2d/B3d name the gap); (ii) `rchar` on tmpfs stands for bytes read from disk (the node would have issued the same read calls on a block device; cache hits are included); (iii) the K = 4 lines per sub-page are copies of one read [inferred: every window holds a multiple of 4 lines, sub-page counts equal floor(N/p)+1 after dividing by 4, the first-trigger query shows 4 identical lines]; (iv) the `ks.g` peak: A13 compares peaks only among cells lasting at least 2 s and only g = 100000 does at either p, so no band test applies; the readings show g = 1 at the background level (152 MB), and g = 100 and 100000 at the same level as the huge table at that p (299 / 329 MB against 321-329 MB at p = 10000; 644 / 757 MB against 746-758 MB at p = 100) [observed], read as "the peak is set by p and the collector, not by g" [inferred]; (v) B3g's "heap" rows are read on sampled `used` (garbage included) and on the live set after full GCs (143-191 MB between and inside the query cells), see part 6.
6. **Deviations and gaps** — (a) Amendments A1-A14 and defects D1, D2 (sections 1 and 3). (b) Cluster sizes 1e6 rows and 3000 x 300 instead of 3e6 and 3000 x 1000, 1 warm-up + 3 timed instead of 5 (A9, A10); the group is still 100 x a 10,000-row page. (c) The data and the node are on tmpfs, so `read_bytes` is not available; `rchar` is used (A11). (d) Heap tightness: the occupancy after young pauses reached 916 MB (89 percent of 1 GB) once, in the first drift cell, with 2 full GCs; every other cell stayed at or below 353 MB after young pauses (the n = 100000 control), 194-199 MB in the p = 10000 cells and 145-148 MB at p = 100; live set after the two humongous-triggered full GCs 179 and 191 MB. B3g's heap row would stop the run "above 90 percent for L=none"; it is read as live heap after GC (as the sibling case did), and the maximum observed occupancy after a young pause (89 percent) is below 90 percent in any case; the verdict does not depend on this cell, because the same flatness holds in the other 11 `ks.t` queries. (e) Peak live heap per query is not observable (proxies named in B2d/B3d). (f) The host was shared with other cases' nodes and tests; the allocation and rows figures are exact counts and unaffected, wall times and sampled peaks may carry interference. (g) The unit tier measures one thread, the cluster tier the whole JVM; neither attributes live heap to the query.
7. **Core question** — Usage did not follow the constraint, and `groupLimit` does not cap it. On a single group of 1,000,000 rows, g = 1, 10, 1000 (unit) and g = 1, 100, 100000 (cluster) read exactly the same 1,000,000 rows in the same number of sub-pages with the same allocation (within 0.1 percent, unit and cluster), the same bytes read (rchar identical) and the same sampled peak heap (within 2.6 percent in the cluster), because a group is counted only when it closes, so `isDone()` stays false while its rows stream and line 993 never fires inside it (steps 1-3 of the logic: parts 3 and 4, `isDone` false in every sub-page but the last). What bounded each read was the page size p (rows per sub-page = p; the per-sub-page allocation is 106 x larger at p = 10000), while the many-small-groups tables show that the limit does stop the read at g groups (rows = 1000 x g or 300 x g, `isDone` true at the close of the last group), so the limit bounds only the size of the result and the work done to produce it when groups are small.

**Conclusion (one line):** Unit B2g rows 1, 2 and 5; cluster B3g rows 1, 2 and 5 — claim confirmed: the group limit does not cap memory or disk use (effect: does not cap).

## 5. Self-check of run 1 — AI

### 5.1 Check of run 1's conclusion

`harness/.../selfcheck.py` re-parses the raw files with its own code (junit XML, `l79-unit.txt`, `cells.jsonl`, `l79.trace`, `heap.csv`, `gc.log`, `system.log`; the per-cell GC table is a second parser, `~/s4-b11-l79-logs/gc-by-cell.py`, restricted to Young and Full pauses because Remark and Cleanup lines do not report occupancy after a collection); output `run1/selfcheck.txt`. It recomputed every cited number: unit "all cells as predicted"; cluster rows, sub-pages, groups, allocation, peaks and `done` flags identical to the analyzer's; 0 trace lines outside any query window; 0 client errors. The first version of the GC reading (selfcheck counting every pause line, 916 MB) is the same maximum as the Young-only parser, which located it in the first drift cell.

| Part | Holds? (yes / no) | Note (file re-read) |
|---|---|---|
| 1. Validity | yes | `cluster-session.txt`: first-trigger check passed, loads 1,000,000 + 900,000 rows with 0 errors; `selfcheck.txt`: K = 4, no unattributed trace lines. The heap caveat is in part 6 (d), not hidden. |
| 2. Readings | yes | Items (a)-(e) re-read in `cluster-per-query.txt` (rchar 2.675 vs 1.057 GB), `cluster-analysis.txt` and `cluster-gc-by-cell.txt`. |
| 3. Matched row | yes | Unit and cluster numbers re-derived independently (`selfcheck.txt`); each part of the quoted rows holds. |
| 4. Excluded rows | yes | Each exclusion cites a number that `selfcheck.txt` reproduces. |
| 5. Observed vs. inferred | yes | (iii) is supported by two independent facts; (iv) is an inference from three cells and is labelled so; (ii) is a proxy named in the filed design. |
| 6. Deviations and gaps | yes | The tmpfs / `rchar` substitution, the scaled sizes, and the single 89 percent reading are stated with both interpretations where they matter. |
| 7. Core question — the steps from reading to answer follow the audited logic | yes | Hypothesis B1, test B2b-B2e/B3b-B3e, prediction B2f/B3f and rows B2g/B3g in that order; the positive control (non-GROUP BY `LIMIT n`) moved, and the page-size sweep moved the per-sub-page allocation. |

### 5.2 Run 2?

**No** (2026-10-27). Both tiers agree, every prediction held with large margins (allocation within 0.1 percent where 10-15 percent was allowed; rchar identical), the positive controls moved by 88x and 133x, and the readings that carry inference (sampled `used`) were not needed for the verdict: the exact counts (rows, sub-pages, allocation, rchar) already decide it. The two soft points (the 89 percent occupancy in one warm-up cell, the uncompared `ks.g` peak) would only be settled by a rerun with a larger heap, a different design.

## 6. Run 2 — fresh AI session (optional)

Not done (section 5.2).

## 7. Comparison — only if run 2 was done

Not applicable.

## 8. Verdict — AI

Jingsong may overrule any verdict at any time; record an override here with its date and reason.

**Stage-3 estimate:** negative. **Outcome class:** true negative (negative, does not cap).

**Claim tested:** (B1) The GROUP BY group limit does not bound memory or disk usage: with the same table, increasing `LIMIT` (the group limit) from 1 to 1000 does not raise peak heap or bytes read beyond what is set by the group size and page size, and a query with `LIMIT 1` over a single enormous group still scans and processes the whole group. "Confirmed" below means this claim held.

| Tier | Verdict (§9a row; for an autonomous file, the B2g / B3g row) | Effect on the constraint | Basis | Date |
|---|---|---|---|---|
| Unit | B2g rows 1, 2, 5: **Confirmed** — rows read = r (up to 1e6) and allocation equal across g; per-sub-page rows follow p; the many-groups table consumes rows with g | does not cap | run 1 + self-check | 2026-10-27 |
| Cluster | B3g rows 1, 2, 5: **Confirmed** — rows 1,000,000, allocation, bytes read (`rchar`) and sampled peak heap flat across g = 1 / 100 / 100000 at p = 10000 and 100; the small-group table reads more with more groups; the limit fires on small groups | does not cap | run 1 + self-check | 2026-10-27 |

**Positive control** (a negative-estimate file only): unit — `SELECT * LIMIT n` allocation 50 KB -> 448 KB -> 4.4 MB for n = 100 / 1000 / 10000 (ratio 88.5), and the page-size sweep moves rows per sub-page; cluster — `SELECT * LIMIT n` allocation 5.2 MB -> 63.5 MB -> 684 MB for n = 1000 / 10000 / 100000 (ratio 132.6), rchar 1.0 -> 104 MB, and the page-size sweep moves the per-sub-page allocation 106 x and the bytes read 2.5 x (`run1/cluster-analysis.txt`, `run1/cluster-per-query.txt`).

**Feedback filed:** the case file's section D updated (amendments A1-A14 and the stage-4 feedback); no section of the trace was refuted. **Open points for the user:** (1) the `ks.g` peak-heap comparison: A13 compares peaks only among queries lasting at least 2 s, so only one cell per page size qualified and the "heap flat" half of B3g row 2 rests on a reading of three cells (part 4.2 (5)(iv)); (2) B3g's "heap above 90 percent" stop rule read as live heap after GC (part 4.2 (6)(d)); the highest occupancy after a young pause was 89 percent, once; (3) the claim is about heap and bytes read by a read, but the constraint is a count of groups, not a byte setting (audit rating "Partly" on A, row 1); (4) `rchar` on tmpfs replaces `read_bytes` (A11). **Upstream / doc candidates:** none for a bug. Doc note, as for the sibling case: `LIMIT` on a GROUP BY query bounds the number of result groups, not the rows scanned; a single large group is read in full whatever the `LIMIT`, in sub-pages of `page size` rows (page size is the real bound on per-sub-page work; at a page size of 100 the same 1e6 rows cost 2.5 x the bytes requested from the file). **Leftovers on pc12:** none running (checked `ps` for `java` with this run's paths and ports: none); the tmpfs run directory `/dev/shm/s4-b11-l79-run1` removed; kept on the node: working trees `~/s4-b11-l79` and `~/s4-b11-l79-c` (471 MB each), logs `~/s4-b11-l79-logs/` (51 MB: shakedowns, run1, the 41 MB Byteman trace, gc.log).
