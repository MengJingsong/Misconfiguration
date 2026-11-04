# group-limit-isdone-groupcounted--autonomous — stage-4 results  <!-- file: results/group-limit-isdone-groupcounted--autonomous.md; the stem ends in --guided or --autonomous -->

> **Case:** [`group-limit-isdone-groupcounted--autonomous`](../../stage3-ai-deep-read/cases/group-limit-isdone-groupcounted--autonomous.md)
>
> **Status:** verdict filed (2026-10-27)
>
> **Outcome class:** true negative (estimate `negative`; unit **Confirmed — does not cap**, cluster **Confirmed — does not cap**)
>
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
| **Case-file version** | Repository HEAD `93d6365` (the case file is still untracked there; the orchestrator commits it). sha256 of the whole file after the audit's amendments A1-A10 (2026-10-27): `95f8238e8a86bda97ab69586833f2051e660aa74658b7dc6c243060fa1ee249a` (version used for the unit run and for the first, aborted, cluster attempt); after amendment A11 (runbook defect D1, section 3; request timeouts in B3a, no prediction or conclusion text changed): `6f104db52c72e566c657d19cbe6ff283083687e95e8398dd759f26ea2e5b2ba2` (the version the cluster run 1 used). sha256 of the frozen prediction and conclusion tables (text of B2f, B2g, B3f, B3g, from `**B2f.` up to `**B2h.` and from `**B3f.` up to `**B3h.`, concatenated; copy kept at `~/s4-b11-g72-logs/freeze-pred.txt` on pc07): `17df005a23b7c89285258f6834bcd02b030617f40fd518563b4f3bf589f903ea`. Frozen 2026-10-27 06:3x UTC, before any reading. Section D (feedback) is outside the table hash and changes after the run. |
| **Harness** | `harness/group-limit-isdone-groupcounted--autonomous/` (files listed in its README; not committed by this session, the orchestrator commits) |
| **Tiers and values** | Unit (B2): CQLTester, 1 partition x 20000 rows x 1 KB and 20000 partitions x 1 row x 1 KB; L (CQL LIMIT) in {1, 1000, 100000, none}; P (page size = `rowLimit`) in {100, 1000, 10000}; control SELECT * LIMIT. Cluster (B3): one node on tmpfs, heap 512 MB, 1 partition x 500000 rows x 1 KB; L in {1, 100000, none}, P in {100, 10000}; many-groups variant (amendment A7); control SELECT * LIMIT in {1000, 10000, 50000}. |
| **Audit bottom line** | **Ready after amendments** — 2026-10-27 (A1-A10 applied) |

### 1.1 Design audit

The requirements are in the README, "Step 0 — the design audit". One row per
line of each group; cite the case-file section checked.

| Group | Check | Rating (Met / Partly / Not met) | Note (section checked) |
|---|---|---|---|
| A. Core question | constrained quantity is memory or disk bytes | Partly | A2: the constrained quantity is a count of groups, not bytes. The byte size is derivable (each group here holds rows of 1 KB), and the claim is about heap use of a read. Accepted as a count with a derivable size (B1, B2c). |
| A. Core question | knob varied, ≥ 3 values incl. default — or another approach, with the reason | Met | B2b: L = 1, 10, 1000, 100000, none (default none); B3b: 1, 100, 100000, none. The competing knob P is varied too. |
| A. Core question | real resource measured, not only the counter (gap named) | Met | B2d: thread-allocated bytes plus counter state; B3d: GC log, heap samples, and (A8) JVM-wide allocated bytes. Peak live heap is named as not observable (B2d, B3d). |
| A. Core question | usage driven to the limit and past it | Met | The limit is the count of groups: the many-groups dataset reaches it (L=1, 1000), the single group never does by design (B2c). A7 adds the many-groups cluster variant. |
| B. Logic | each step says what it establishes | Met | B2e/B3e steps each name their purpose (data, grid, control). |
| B. Logic | prediction stated in numbers or a clear relation | Met after A2, A3, A9 | B2f/B3f give row counts, 10 / 15 percent bands and sub-page counts; the sub-page count was off by one (A2) and the many-groups total rows needed the L >= P case (A3); A9 gave 'about the same' a bound. |
| B. Logic | every plausible outcome has a conclusions row with its evidence | Met after A4, A5 | Rows: flat (Confirmed), early stop (Refuted), follows L (Refuted), mechanism works, control flat (Invalid), limit not reached. A4 defines 'control moved' and A5 scopes the 'limit never reached' row. A reading that matches no row is 'Not confirmed (no matching row)'. |
| B. Logic | confirmation needs ceiling-follows-knob and direct disallow evidence | Met after A7, A8 | For this negative claim the direct evidence is the counter state: isDone() false while rows stream (B2d, A8) and, in the many-groups run, isDone() true at groupCounted == L (B2g row 4, A7). The cluster tier had no many-groups procedure (B3g refers to it): A7 adds it. |
| B. Logic | alternative explanations and their controls | Met after A4, A6 | Competing bound = rowLimit: the P sweep (B2b) is the control; non-GROUP BY LIMIT is the positive control (B2e.6, B3e.4); A6 fixes the cluster control values. |
| C. Specific | a human can follow it from the intro and §9a | Met | Intro table, A1-A3 and B1 explain the claim. |
| C. Specific | an AI can run §9b–§9e without re-deriving the code path | Partly | The unit instrument 'spy on rowsCounted' (B2d) is described, not specified; this session specifies it in the harness (own Counter applied to a raw read, plus a counting pager wrapper). Cluster instruments are specified by A8, A10. |
| C. Specific | knob, values, workload, commands, observables, sampling, stop conditions exact | Partly | Mostly exact. Gaps filled by amendments: control L values (A6), client (A10), instrument (A8). B3c's 'cassandra-stress or driver' is fixed to the driver. |
| D. Runnable | harness and environment prerequisites exist or are listed | Met | JDK 11, Ant, build-test as in environment.md; the test class and run scripts are listed as step-1 work (harness folder). |
| D. Runnable | workload arithmetic reaches the limit (data, time, disk, memory) | Met after A6 | 20 MB (unit) and 500 MB (cluster, tmpfs) against 1 GiB / 512 MB heaps; streaming through sub-pages of P x 1 KB (0.1 to 10 MB). A6 drops L=100000 for the SELECT * control (about 100 MB result against a 512 MB heap). Disk: about 1.5 GB on /dev/shm (126 GB free). |
| D. Runnable | load-bearing citations spot-checked against the pinned source | Met after A1 | Checked in cassandra-5.0.9: DataLimits.java :658 (field), :665-690 (constructors), :717-747 (forPaging, forGroupByInternalPaging), :806-810, :837, :888-894, :917, :933-937, :983-995, :1007, :1011-1013, :1041; SelectStatement :114, :893-914; AggregationQueryPager :284-287. All as cited except the A1 line numbers (fixed). The statement that a group is not counted while rows stream, and the onClose rule, hold as written. |

| # | Recommendation | Applied? (amendment date and commit, or "left for stage 3") | Why |
|---|---|---|---|
| A1 | Correct line numbers in A1 (field :658, constructors :665-690) | applied 2026-10-27 (case file untracked; no commit) | citation accuracy |
| A2 | Sub-page count = floor(N/P)+1, not ceil(N/P) | applied 2026-10-27 | `onClose` counts the trailing group only if `rowsCounted < rowLimit` (:1041) |
| A3 | Many-groups total rows = L for any L below 20000, not only L < P | applied 2026-10-27 | sub-pages add up |
| A4 | Define "positive control moved" | applied 2026-10-27 | B2g row on the control needs a threshold |
| A5 | Scope the "limit never reached" row | applied 2026-10-27 | cells L >= 20000 cannot reach it by construction |
| A6 | Cluster control values 1000, 10000, 50000 | applied 2026-10-27 | instrument noise at L=100; OOM risk at L=100000 |
| A7 | Add a many-groups cluster variant | applied 2026-10-27 | disallow-branch evidence at cluster tier; B3g already refers to it |
| A8 | Byteman rule on `onClose` and a JMX allocation reading instead of cqlsh tracing | applied 2026-10-27 | 5000 sub-pages per query; no direct heap-per-query reading |
| A9 | Bound "about the same" across P (factor 2) and fix sub-page count in B3f | applied 2026-10-27 | prediction must be able to be contradicted |
| A10 | Client = bundled Python driver | applied 2026-10-27 | cqlsh cannot script 30 timed queries |
| A11 | Raise `range_request_timeout`, `read_request_timeout`, `request_timeout` to 600000ms (runbook defect D1, found by cluster attempt 1) | applied 2026-10-27 after attempt 1; cluster tier restarted | the 10 s range deadline spans all 5001 sub-pages of a P=100 full scan |
| R-a | Add a rows-per-sub-page assertion for the P=1000 cell | left for stage 3 | not needed for a valid run |
| R-b | Claim 'heap' vs count: state in A2 that the group count is not a memory setting at all (it is per query) | left for stage 3 | wording only |

**Agreement criteria** — only if run 2 is chosen; filled before run 2 starts.
One row per observable in the case's §9d:

| Observable | Must match | Tolerance |
|---|---|---|
| `<observable>` | exactly / in shape | `<what counts as the same>` |

## 2. Environment

| Field | Run 1 | Run 2 (fresh AI session, if done) |
|---|---|---|
| Date | 2026-10-27 (unit 06:41 UTC; cluster 07:02-07:12 UTC; aborted attempt 06:53-07:01 UTC) | not done |
| Node (CloudLab name and type) | `pc07` (`node0.jason92-320876`), 40 cores, 251 GiB; shared with other cases (this run: loopback 127.0.2.1, JMX 7120, port slot 2) | |
| OS and kernel (`uname -r`) | Ubuntu 22.04, 5.15.0-187-generic | |
| JDK (`java -version`) | openjdk 11.0.32.1 | |
| Ant (`ant -version`) | Apache Ant 1.10.12 | |
| Local source copy (from `cassandra/cassandra-5.0.9/` at repository commit …) | `~/s4-b11-g72` (`ant build-test`, unit) and `~/s4-b11-g72-c` (`ant jar`, cluster), both `copy-source.sh` copies at repository HEAD `93d6365` (tag `cassandra-5.0.9`) | |
| Case-file / harness commit | case file and harness untracked at HEAD `93d6365` (orchestrator commits); case-file sha256 in section 1; harness md5 in `run1/unit-summary.txt` | |
| Storage for node data | unit: build tree on `/dev/sda3` (local); cluster: `/dev/shm` (tmpfs), 512 MB heap, `data on disk after compaction` 544,283,450 bytes (`run1/cluster-session.txt`) | |
| Full logs (path, outside the repo) | `~/s4-b11-g72-logs/run1/{unit,cluster}/` on pc07 (cluster: `g72.trace` 373,572 lines, `heap.csv`, `gc.log`, `system.log`); aborted attempt: `~/s4-b11-g72-logs/run1a-aborted-timeouts/` | |

## 3. Runbook defects

| # | Run | Step (§9b–§9e) | Problem | Fix | Decision (date) | Case-file commit with the fix |
|---|---|---|---|---|---|---|
| D1 | cluster attempt 1 | B3a / B3e.3 | With the default `range_request_timeout` (10 s) every P=100 full scan (5001 sub-pages) failed with `ReadTimeout` / `ReadFailure` after 10 s, because the coordinator's deadline runs from the start of the request and spans every sub-page; all 18 P=100 queries of the S dataset (3 warm-up, 15 timed) errored. The 6 P=10000 cells (about 3 s per query) and the drift cell completed. | B3a also sets `range_request_timeout`, `read_request_timeout`, `request_timeout` = 600000ms (`native_transport_timeout` was already 600s in the harness); case-file amendment A11 (section D, B3a); cluster tier restarted from its beginning as run 1. Prediction and conclusions unchanged. | 2026-10-27 | untracked file (no commit) |
| D2 | unit shakedown | harness | Three instrument faults found in the shakedown (not a reading): a row-counting transformation that never saw rows; one `AggregationQueryPager` reused across client pages (it trips the `assert` in `CQLGroupByPagingLimits.newCounter`, `DataLimits.java:1103`, because the request path builds a new pager per page); lower-case booleans in the analyzer. All fixed in the harness before run 1; `README.md` of the harness lists them. | harness only | 2026-10-27 | n/a |

Not a defect, a calibration: every local sub-page read closes K = 4 `GroupByAwareCounter` instances (replica read and coordinator-side counters), so each sub-page appears 4 times in the Byteman trace; K was calibrated on the first-trigger query (`run1/cluster-analysis.txt`, first line) and every window holds a multiple of 4 lines.

## 4. Run 1

**Scope:** unit tier (B2) all cells as filed; cluster tier (B3) all cells as amended (A6-A11): S = 1 partition x 500000 rows x 1 KB with P in {10000, 100} x L in {1, 100000, none}, 1 warm-up + 5 timed queries per cell, drift cell (L=none, P=10000) at start and end, control `SELECT * LIMIT` L in {1000, 10000, 50000}, many-groups table G (20000 partitions) with P in {100, 10000} x L in {1, 100, 5000, none}. **Command log:** `run1/unit-summary.txt`, `run1/cluster-session.txt`; raw readings `run1/unit-g72-unit.txt`, `run1/cluster-cells.jsonl`, `run1/cluster-per-query.txt`; analyzer output `run1/cluster-analysis.txt`; self-check `run1/selfcheck.txt`.

### 4.1 Readings

**Unit tier** (each number is the mean of the 2 timed repetitions; the analyzer printed every prediction as an `EXPECTED:` line, 80 PASS, 0 FAIL: `run1/unit-summary.txt`)

| Test or assertion | Result | Evidence (file) |
|---|---|---|
| Instrument check (first trigger): many-groups, L=1, P=100, white-box counter | groups=1, rowsCounted=1, isDone=true | `run1/unit-g72-unit.txt` (`G72 W ds=M L=1 P=100`) |
| S (1 group, 20000 rows), every L in {1, 1000, 100000, none} x P in {100, 1000, 10000}: rows read | 20000 in all 12 cells (3 timed reps each) | `run1/unit-g72-unit.txt` (`G72 E ds=S`) |
| S: rows per sub-page; sub-page count | max rows per sub-page = P in every cell; sub-pages 201 / 21 / 3 for P = 100 / 1000 / 10000 (= floor(20000/P)+1, amendment A2) | same |
| S: white-box counter after one sub-page | groups=0, rowsCounted=P, isDone=false in all 12 cells | `G72 W ds=S` |
| S: allocated bytes of the calling thread, max/min across L at fixed P | P=100: 31.68-31.86 MB (1.006); P=1000: 29.637 MB (1.000); P=10000: 29.432 MB (1.000) | `G72 E ds=S`, `run1/selfcheck.txt` |
| M (20000 partitions x 1 row): rows read and groups | = L for L=1 and 1000 at every P; 20000 for L=100000 and none | `G72 E ds=M` |
| M: white-box counter | L=1: groups=1, rowsCounted=1, isDone=true (P = 100, 1000, 10000); L=1000, P=10000: groups=1000, isDone=true; L >= P: stops on `rowLimit` (rowsCounted=P, groups=P-1, isDone=false) | `G72 W ds=M` |
| Control `SELECT * ... LIMIT L` (no GROUP BY) | rows = L = 100 / 1000 / 10000; allocated 152,176 / 1,475,312 / 14,706,184 bytes (ratio 96.6) | `G72 C` |

**Cluster tier** (means over the timed queries of a cell; peak = max of `HeapMemoryUsage.used` sampled every 100 ms inside the query window; alloc = JVM-wide sum of thread-allocated bytes, idle noise median 173 KB/s)

| Capacity value | Run | Observable (B3d) | Reading | Evidence (file) |
|---|---|---|---|---|
| S, P=10000, L = 1 / 100000 / none | 5 / 5 / 5 (+11 for none incl. drift) | rows read (Byteman trace / 4), sub-pages, max rows per sub-page | 500000 in every query; 51 sub-pages (= floor(500000/10000)+1); max 10000 | `run1/cluster-analysis.txt`, `run1/cluster-per-query.txt` |
| same | | alloc per query; peak used | 3.020 / 3.086 / 3.088 GB (max/min 1.023); peak used 405 / 402 / 411 MiB | same |
| S, P=100, L = 1 / 100000 / none | 5 / 5 / 5 | rows read, sub-pages, max rows per sub-page | 500000 in every query; 5001 sub-pages; max 100 | same |
| same | | alloc per query; peak used | 2.875 / 2.874 / 2.873 GB (max/min 1.001); peak used 474 / 461 / 458 MiB | same |
| S, L=none, P=10000 vs P=100 | | total alloc; alloc per sub-page | total 3.088 vs 2.873 GB (ratio 1.07); per sub-page 60.6 MB vs 0.574 MB (105 x) | same |
| S, isDone in the trace | all queries | `done` flag per sub-page | false in every sub-page but the last; at L=1 the last (empty) sub-page reads rows=0, groups=1, done=true | `run1/cluster-analysis.txt` |
| drift: S, L=none, P=10000, start vs end | 3 + 3 | alloc | 3.0887 GB vs 3.0879 GB | same |
| G (20000 partitions), P in {100, 10000}, L = 1 / 100 / 5000 | 3 each | rows read (trace), client rows, groups, last sub-page | rows read = L, client rows = L, groups = L, last sub-page `done=true` in all 6 cells | same |
| G, L=none | 3 each | rows read | 20000 at both P; limit not reached (as predicted) | same |
| control `SELECT * ... LIMIT` L = 1000 / 10000 / 50000, paging off | 3 each | rows, alloc, peak used | rows = L; alloc 5.16 MB / 63.4 MB / 282 MB (ratio 54.6); peak used 279 / 321 / 444 MiB | same |
| node health | whole run | `system.log`, GC log | 0 `ERROR` lines, no `OutOfMemoryError` (the 3 hits of "OutOfMemory" are the JVM option `-XX:+HeapDumpOnOutOfMemoryError` in the argument echo); baseline live set after a `jcmd GC.run` full GC 266-268 MB (52 percent of 512 MB); during P=100 cells 64-67 full GCs per 5 queries, identical for every L, live set after each 266-268 MB | `run1/selfcheck.txt`, `gc.log` on the node |

### 4.2 Conclusion and logic

1. **Validity** — Valid. Limit reached: the many-groups runs reach `groupLimit` (unit M, L=1 and L=1000 at P=10000: isDone=true, groups=L [observed: `run1/unit-g72-unit.txt`]; cluster G, L=1/100/5000: groups=L, last sub-page `done=true` [observed: `run1/cluster-analysis.txt`]), so the instrument can see the branch fire. "Hold fixed" settings: heap 512 MB, row cache off, same flushed and compacted data for every cell, 1 warm-up per cell, `jcmd GC.run` and an idle baseline before each cell, drift cell at both ends (3.0887 vs 3.0879 GB) [observed: `run1/cluster-session.txt`, `run1/cluster-analysis.txt`]. Positive control moved (unit: ratio 96.6; cluster: ratio 54.6) [observed]. The first-trigger check passed [observed: `run1/cluster-session.txt`]. One validity caveat is recorded in part 6 (heap tightness at P=100).
2. **Readings** — Unusual: (a) K = 4 trace lines per sub-page (calibrated, section 3). (b) The first warm-up query of the drift cell shows 52 sub-pages / 510000 rows (one extra read of a 10000-row sub-page) [observed: `run1/cluster-per-query.txt`, first S row]; warm-ups are excluded from every statement. (c) The P=100 cells run many full GCs (64-67 per 5 queries) at identical rates for every L [observed: `gc.log`]. (d) The allocation total does not grow with P (unit 29.4 -> 31.7 MB for P 10000 -> 100; cluster ratio 1.07), only the per-sub-page batch does (105 x) [observed].
3. **Matched row** — Unit, B2g row 1: "Single-group dataset: rows read and allocated bytes the same for L=1 and L=100000 (rows read 20000); the per-sub-page row count follows P" — rows 20000 for every L, allocated bytes within 0.6 percent across L, max rows per sub-page = P [observed: `run1/unit-g72-unit.txt`]; with row 4 ("Many-groups ... rows read = L+1 and isDone() true: mechanism works as traced") — rows read = L (rowsCounted = L exactly, not L+1), isDone true at groupCounted == L [observed]. Cluster, B3g row 1: "Heap peak and rows read flat across L at fixed P, while P moves the per-sub-page batch" — peak used within 2.2 percent (P=10000) and 3.7 percent (P=100), allocation within 2.3 and 0.1 percent, rows 500000 in every query, per-sub-page allocation 105 x higher at P=10000 [observed: `run1/cluster-analysis.txt`].
4. **Excluded rows** — Unit: row 2 (rows drop to about 1 at L=1): rows 20000 at L=1 [observed]. Row 3 (alloc grows with L): max/min 1.006 [observed]. Row 5 (control flat): control ratio 96.6 [observed]. Row 6 (limit never reached): reached in the M cells with L=1 and L=1000 [observed]. Cluster: row 2 (L=1 reads less or allocates less than none): rows 500000 and alloc ratio 0.98-1.0 [observed]. Row 3 (peak follows L): no monotone trend; max/min 1.022 and 1.037 [observed]. Row 4 (control flat): ratio 54.6 [observed]. Row 5 (limit never reached in the many-partitions variant): reached at L = 1, 100, 5000 [observed]. Row 6 (OOM or heap above 90 percent for L=none): see part 6.
5. **Observed vs. inferred** — Inferred: (i) that allocation volume and sampled `used` stand for memory use of the read (the filed gap: no per-request live-heap attribution [B3d]); (ii) that the K = 4 lines per sub-page are copies of the same sub-page, not four different reads [inferred: every window holds a multiple of 4 lines, sub-page counts equal floor(N/P)+1 after dividing by 4, and the first-trigger query shows 4 lines for one read]; (iii) that in the unit tier thread-allocated bytes of the calling thread cover the whole local read [inferred: the read runs on the calling thread via `fetchPageInternal`]; (iv) the reading of B3g's last row ("heap above 90 percent") as live heap after a full GC, see part 6.
6. **Deviations and gaps** — (a) Amendments A1-A11 and defect D1 (sections 1 and 3). (b) The cluster client is the Python driver, not cqlsh (A10); tracing replaced by a Byteman rule (A8). (c) Heap tightness: during the P=100 cells the mean of the per-query maxima of sampled `used` was 458-474 MiB (89-93 percent of the 512 MiB heap) and the occupancy after young pauses reached 490 MB (96 percent) and G1 ran full GCs (evacuation failure) at the same rate for every L; the live set after a full GC was 266-268 MB (52 percent) at idle and during the queries [observed: `gc.log`, `run1/selfcheck.txt`], and no `OutOfMemoryError` occurred. B3g's last row ("heap goes above 90 percent for L=none: stop, reduce the dataset") is read here as live heap after GC, because B3d names "the maximum heap occupancy after GC" and `used` includes garbage; under the literal `used` reading the P=100 cells would trigger it. The P=10000 cells (peak used 402-411 MiB, 79-80 percent) satisfy row 1 without this reading, so the verdict does not depend on it; flagged for the user to overrule. (d) Peak live heap per query is not observable; allocation volume and sampled `used` are proxies (named in B2d/B3d). (e) Idle allocation noise (median 173 KB/s) is far below every compared quantity (GB-scale). (f) One tier-2 coverage gap: the unit tier measures one thread, the cluster tier the whole JVM; neither attributes live heap to the query.
7. **Core question** — Usage did not follow the constraint, and `groupLimit` does not cap it. With one group of 500000 rows, L=1, L=100000 and no limit read exactly the same 500000 rows, in the same number of sub-pages, with the same allocation (within 2.3 percent) and the same sampled peak heap (within 4 percent), because a group is counted only when it is closed and `isDone()` stays false while its rows stream (steps 1-3 of the logic: parts 3 and 4, `isDone` false in every sub-page but the last); what bounded each read was `rowLimit` = P (max rows per sub-page = P, per-sub-page allocation 105 x larger at P=10000), while the many-groups variant shows the limit does stop the read when groups are small (rows read = L, `isDone` true), so the limit only bounds the result size.

**Conclusion (one line):** Unit B2g rows 1 and 4, cluster B3g row 1 — claim confirmed: the group limit does not cap memory use (effect: does not cap).

## 5. Self-check of run 1 — AI

### 5.1 Check of run 1's conclusion

`harness/.../selfcheck.py` re-parses the raw files with its own code (junit XML, `g72-unit.txt`, `cells.jsonl`, `g72.trace`, `heap.csv`, `gc.log`, `system.log`); output `run1/selfcheck.txt`. It recomputed every cited number: unit "all cells as predicted"; cluster rows, sub-pages, allocation, peaks, groups and `done` flags identical to the analyzer's; 0 trace lines outside any query window; 0 client errors.

| Part | Holds? (yes / no) | Note (file re-read) |
|---|---|---|
| 1. Validity | yes | `cluster-session.txt`: first-trigger check passed, loads 500000 + 20000 rows with 0 errors; `selfcheck.txt`: K=4, no unattributed trace lines. The heap caveat is recorded in part 6, not hidden. |
| 2. Readings | yes | Unusual items (a)-(d) re-read in `cluster-per-query.txt` (first S row: 52 sub-pages) and `gc.log`. |
| 3. Matched row | yes | Unit and cluster numbers re-derived independently (`selfcheck.txt`); each part of the quoted rows holds. |
| 4. Excluded rows | yes | Each exclusion cites a number that `selfcheck.txt` reproduces. The one soft spot is B3g's last row (part 6 (c)). |
| 5. Observed vs. inferred | yes | Inferred (ii) is supported by two independent facts (multiples of 4; floor(N/P)+1 after division); (iii) by the pager code path. |
| 6. Deviations and gaps | yes | The heap-tightness reading is stated with both interpretations and the reason the verdict does not depend on it. |
| 7. Core question — the steps from reading to answer follow the audited logic | yes | Hypothesis B1, test B2b-B2e/B3b-B3e, prediction B2f/B3f and rows B2g/B3g, in that order; the positive control (rowLimit sweep and non-GROUP BY LIMIT) moved. |

### 5.2 Run 2?

**No** (2026-10-27). Both tiers are cheap but agree, every prediction held with large margins (allocation within 2.3 percent where 15 percent was allowed), the positive controls moved, and the one inferred point that could change the reading (heap above 90 percent) does not affect the P=10000 cells. A rerun with a 1 GiB heap would remove the ambiguity but is a different design (B3a heap) and is left to the user.

## 6. Run 2 — fresh AI session (optional)

Not done (section 5.2).

## 7. Comparison — only if run 2 was done

Not applicable.

## 8. Verdict — AI

Jingsong may overrule any verdict at any time; record an override here with its date and reason.

**Stage-3 estimate:** negative. **Outcome class:** true negative (negative, does not cap).

**Claim tested:** (B1) The GROUP BY `groupLimit` comparison at `DataLimits.java:1013` does not bound how much memory a read uses. With a fixed row layout, per-read rows pulled and heap allocated stay the same when `groupLimit` (CQL `LIMIT`) varies from 1 to 100000, as long as one group spans many rows. They scale with `rowLimit` (the page size) instead. The comparison only decides when the result stops (number of groups returned). "Confirmed" below means this claim held.

| Tier | Verdict (§9a row; for an autonomous file, the B2g / B3g row) | Effect on the constraint | Basis | Date |
|---|---|---|---|---|
| Unit | B2g rows 1 and 4: **Confirmed** — rows read 20000 and allocation equal across L; per-sub-page rows follow P; many-groups mechanism as traced | does not cap | run 1 + self-check | 2026-10-27 |
| Cluster | B3g row 1: **Confirmed** — rows 500000, allocation and sampled peak heap flat across L at P = 10000 and 100; per-sub-page batch follows P; many-groups limit fires | does not cap | run 1 + self-check | 2026-10-27 |

**Positive control** (a negative-estimate file only): unit — `SELECT * LIMIT L` allocation 152 KB -> 1.48 MB -> 14.7 MB for L = 100 / 1000 / 10000 (ratio 96.6), and the page-size sweep moves rows per sub-page (`run1/unit-g72-unit.txt`); cluster — `SELECT * LIMIT L` allocation 5.2 MB -> 63 MB -> 282 MB for L = 1000 / 10000 / 50000 (ratio 54.6) and the page-size sweep moves the per-sub-page allocation 105 x (`run1/cluster-analysis.txt`).

**Feedback filed:** the case file's section D updated (amendments A1-A11 and the stage-4 feedback); no section of the trace was refuted. **Open points for the user:** (1) B3g's last row ("heap above 90 percent") read as live heap after GC (part 4.2 (6)(c)); (2) the claim is about heap use of a read, but the constraint is a count of groups, not a byte setting (audit rating "Partly" on A, row 1). **Upstream / doc candidates:** none for a bug. Doc note: `LIMIT` on a GROUP BY query bounds the number of result groups, not the rows scanned: a single large group is read in full regardless of `LIMIT`, in sub-pages of `page size` rows (page size is the real bound on per-read memory). **Leftovers on pc07:** none running (checked `ps` for `CassandraDaemon` of this run: none); tmpfs run directory removed; kept on the node: working trees `~/s4-b11-g72`, `~/s4-b11-g72-c`, logs `~/s4-b11-g72-logs/` (about 53 MB in total).
