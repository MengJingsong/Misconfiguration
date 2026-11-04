# cql-row-limit-incrementRowCount-rowsCounted--autonomous — stage-4 results  <!-- file: results/cql-row-limit-incrementRowCount-rowsCounted--autonomous.md; the stem ends in --guided or --autonomous -->

> **Case:** [`cql-row-limit-incrementRowCount-rowsCounted--autonomous`](../../stage3-ai-deep-read/cases/cql-row-limit-incrementRowCount-rowsCounted--autonomous.md)
>
> **Status:** verdict filed (2026-10-27): run 1 done and self-checked; no run 2
>
> **Outcome class:** true negative (estimate `negative`, effect `does not cap` in both tiers; [definition](../README.md#outcome-class))
>
> **Agent:** guided / autonomous (the suffix of the case-file stem). For an autonomous
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
| **Case-file version** | The case file at repository HEAD `93d6365` (untracked there) plus the audit amendments of 2026-10-27 (case file section D items 1-6; the orchestrator commits). sha256 of the unit prediction and conclusions text (`awk` from the line starting `**B2f.` to the line before `**B2h.`): `b70be8d871e66036491a6adecec7e0fce7ff05879dbc0c510ee5b2af0dcb10c5`; of the cluster text (from `**B3f.` to the line before `**B3h.`): `3fe4dd78c3b7597557488124256bf5f77e3579b74ea3935df96f1cf83368ab8d`. sha256 of the whole file after the amendments (frozen before any reading of the final run): `f6bfbdd7d1a25586ef6cce1d5734a2bd3140418e011f9e6e230be52c648c0c56`. The shakedowns (instrument checks on 50 000 rows and on small data, not readings) are listed in section D item 6 of the case file and in the harness README; the prediction text was changed once because of them (the pager and noise points), before this hash. The case file changes after run 1 only in section D (feedback). |
| **Harness** | `harness/cql-row-limit-incrementRowCount-rowsCounted--autonomous/` (written after the audit and before run 1; not committed by this agent; file list in its README). |
| **Tiers and values** | Unit (B2): width 16 B / 1 KiB / 64 KiB x limit {1, 100, 1000, 10000, 1000000} under the 300 MB rule, NONE, dead-row series, byte-stop control. Cluster (B3): two node lifetimes on one node: U (uncapped; unpaged queries on three tables of 100 B / 10 KiB / 100 KiB rows with LIMIT 10 to 100000 and none, two paged queries) and C (`local_read_size_fail_threshold` 20 MiB). |
| **Audit bottom line** | **Ready after amendments** - 2026-10-27 (amendments in the case file's section D; no reading existed when they were made). |

### 1.1 Design audit

The requirements are in the README, "Step 0 — the design audit". One row per
line of each group; cite the case-file section checked.

| Group | Check | Rating (Met / Partly / Not met) | Note (section checked) |
|---|---|---|---|
| A. Core question | constrained quantity is memory or disk bytes | Partly | A2: the limit is a count of CQL rows, not bytes. The claim (B1) is about heap bytes per query as count x width; measured as retained heap (unit) and allocated bytes (cluster). Accepted: a negative-estimate case whose point is that the count does not bound bytes. |
| A. Core question | knob varied, >= 3 values incl. default — or another approach, with the reason | Met | B2b 5 limits plus NONE (the default) and 3 widths; B3b 6 limits incl. no LIMIT and 3 widths. |
| A. Core question | real resource measured, not only the counter (gap named) | Met after amendment | B2d retained heap after GC and `unsharedHeapSize` sum; B3 originally sampled `jstat`, too coarse for small queries; allocation over JMX added as primary, with the gap named (garbage counted, live set of one transient query not observable). |
| A. Core question | usage driven to the limit and past it | Met after amendment | Unit: limits reached on a 1.2 M-row source, pairs capped by the 1 GiB test JVM. Cluster: the original data (up to 1 GB results against a 2 GB heap) could not be answered; rescaled so that every LIMIT is below the partition size and the largest result is 120 MB. |
| B. Logic | each step says what it establishes | Met | B2e / B3e numbered steps and B2g / B3g meanings. |
| B. Logic | prediction stated in numbers or a clear relation | Met after amendment | B2f qualitative lines made numeric. B3f "more than 100x" ignored the per-row overhead (a 100 B row costs about 1 KB to allocate): replaced by a marginal-bytes-per-row slope with bounds. |
| B. Logic | every plausible outcome has a conclusions row with its evidence | Met after amendment | B2g: confirmed, refuted (flat), follows-limit-only, control fails, mechanism mismatch, dead rows. B3g: rewritten, partial slope and "anything else" rows added. |
| B. Logic | confirmation needs ceiling-follows-knob and direct disallow evidence | Met | The "ceiling" is the count; the direct evidence is `rowsCounted == L == output rows` (unit) and rows returned == min(LIMIT, rows) (cluster); the byte cap that does bind is the control. |
| B. Logic | alternative explanations and their controls | Met after amendment | Positive control: unit byte stop at 8 MiB on the same chain (harness-side stand-in); cluster `local_read_size_fail_threshold` 20 MiB (a real byte cap, closed Confirmed case `local_read_size_fail_threshold-addSize-failBytes--guided`). The original cluster control (row cache `rows_per_partition`) compares counts and does not move the same resource: dropped. |
| C. Specific | a human can follow it from the intro and §9a | Met | A1-A3, B1. |
| C. Specific | an AI can run §9b–§9e without re-deriving the code path | Partly, fixed | "Value buffers are reused" (would hide the width), unpaged without `fetch_size=None`, 5 s / 60 s gaps and the sampling interval were unstated; amended. |
| C. Specific | knob, values, workload, commands, observables, sampling, stop conditions exact | Partly, fixed | Amended (B2b-f, B3a-f): grid, row counts, queries, sampling every 25 ms, windows, first-trigger checks. |
| D. Runnable | harness and environment prerequisites exist or are listed | Met | pc12: JDK 11, Ant, `copy-source.sh` trees `~/s4-b11-c76` and `~/s4-b11-c76-n`, driver unzipped from the build's `lib/`; JMX sampler, loader, drivers in the harness. |
| D. Runnable | workload arithmetic reaches the limit (data, time, disk, memory) | Met after amendment | Unit: 15 pairs x 5 reps, each under 300 MB retained. Cluster: 150 MB on tmpfs, 56 + 15 queries of a few seconds. The original 1 GB-class results and 2 000 x 1 MiB rows were not. |
| D. Runnable | load-bearing citations spot-checked against the pinned source | Met | `DataLimits.java:48,50,83,349,365-370,392-395,402-405,466,507-513,535-543` (the target `if (++rowsCounted >= rowLimit) stop();` is `:509-510`); `SelectStatement.java:114,881-920`; `CacheService.java:420`; `RangeCommandIterator.java:253`; `SelectStatement.java:1057-1140` for the coordinator guardrail path. One finding, not a citation error: `DataLimits.filter(UnfilteredRowIterator, ...)` builds a counter with `assumeLiveData=false` (`:210-216`), the `PartitionIterator` variant with `true` (`:224`), so the dead-row series tests `isLive` as written. |

| # | Recommendation | Applied? (amendment date and commit, or "left for stage 3") | Why |
|---|---|---|---|
| 1 | Fresh value buffer per row (the unit source must not share one buffer) | Applied 2026-10-27 (B2c, section D item 2) | A shared buffer makes retained heap independent of width. |
| 2 | Limit grid and 300 MB rule | Applied 2026-10-27 (B2b, item 1) | 1 000 000 x 64 KiB cannot run in a 1 GiB JVM. |
| 3 | B2f/B2g numeric (slope, ratio, pulled-row and control bounds) | Applied 2026-10-27 (B2f, B2g, item 4) | Qualitative predictions. |
| 4 | B3 rescaled; allocation counter; slope prediction; byte-guardrail control; `fetch_size=None` | Applied 2026-10-27 (B3, item 5) | See the audit rows. |
| 5 | Reading noise of the retained heap (about 0.3 MB) found at the instrument check: slopes are taken over the widest pairs, linearity per row only for readings of at least 2 MB | Applied 2026-10-27 (B2f), before any frozen reading | Found by a shakedown on 50 000 rows, not by a reading of the final run. |
| 6 | The case's Estimate / Ground say "heap or off-heap use per query is count x width"; consistent with B1 | No change | Consistent. |

**Agreement criteria** — only if run 2 is chosen; filled before run 2 starts.
One row per observable in the case's §9d:

| Observable | Must match | Tolerance |
|---|---|---|
| `<observable>` | exactly / in shape | `<what counts as the same>` |

## 2. Environment

| Field | Run 1 | Run 2 (fresh AI session, if done) |
|---|---|---|
| Date | 2026-10-27 (unit 01:33-01:35 MDT; cluster 01:35-01:50 MDT) | not done |
| Node (CloudLab name and type) | `pc12` = `node1.jason92-320876.misconfiguration-pg0.cloudlab.umass.edu`, 40 cores, 251 GiB; port slot 6 (127.0.6.1, JMX 7160); other cases ran on the same node | |
| OS and kernel (`uname -r`) | Ubuntu 22.04, `5.15.0-187-generic` | |
| JDK (`java -version`) | OpenJDK 11.0.32.1 | |
| Ant (`ant -version`) | Apache Ant 1.10.12 | |
| Local source copy (from `cassandra/cassandra-5.0.9/` at repository commit …) | `copy-source.sh` copies `~/s4-b11-c76` (unit, `ant build-test`) and `~/s4-b11-c76-n` (node, `ant jar`), tag `cassandra-5.0.9`, source clean (`srcstatus.txt` empty); repository HEAD `93d6365` | |
| Case-file commit / harness commit | case file and harness uncommitted at `93d6365` (the orchestrator commits); md5 of the harness files in `run1/unit/harness.md5` | |
| Storage for node data | tmpfs `/dev/shm/s4-b11-c76` (126 GB free; the data set was 152 MB); the unit tier runs in the tree's `build/test` on local disk | |
| Full logs (path, outside the repo) | `pc12:~/s4-b11-c76-logs/run1/{unit,cluster}/` (3.6 MB incl. `cluster/{U,C}/alloc.csv`, 21 430 and 7 195 samples at 26 ms); shakedowns in `~/s4-b11-c76-logs/shake-*` | |

## 3. Runbook defects

Found at the audit and the instrument checks, before run 1 (case file section D; the tier had not started): (1) shared value buffer in B2c; (2) grid pairs beyond the 1 GiB test JVM; (3) B3 data volumes and the "more than 100x" prediction; (4) the Python driver's default page size makes "unpaged" paged; (5) the retained-heap reading noise (0.3 MB) and the empty final page of a paged query. None changed the claim. No defect during run 1.

| # | Run | Step (§9b–§9e) | Problem | Fix | Decision (date) | Case-file commit with the fix |
|---|---|---|---|---|---|---|
| 1 | audit | B2c | value buffers reused: retained heap would not depend on width | fresh buffer per row | 2026-10-27 | orchestrator commits |
| 2 | audit | B2b | 1 000 000 x 64 KiB and 10 000 x 64 KiB exceed the test JVM | 300 MB rule, grid fixed | 2026-10-27 | orchestrator commits |
| 3 | audit | B3a-B3h | results of 1 GB and 2 GB against a 2 GB heap; ratio prediction ignores row overhead | rescaled, slope prediction, byte control | 2026-10-27 | orchestrator commits |
| 4 | shakedown | B2f | linearity check amplified a 0.3 MB noise 10 x | widest pairs, readings of at least 2 MB | 2026-10-27 | orchestrator commits |
| 5 | shakedown | B3f | pager can end with an empty page; sample-to-sample page windows double count | 10 or 11 pages; interpolated page allocation | 2026-10-27 | orchestrator commits |

## 4. Run 1

**Scope:** both tiers, all values of the frozen design. **Command log:** `cql-row-limit-incrementRowCount-rowsCounted--autonomous/run1/` (`unit/session.log`, `unit/summary.txt`, `unit/unit.txt`, `cluster/session.log`, `cluster/summary.txt`, `cluster/{U,C}/queries.jsonl`, `selfcheck.txt`). The analyzers' EXPECTED lines are in the two `summary.txt` files.

### 4.1 Readings

**Unit tier** (`run1/unit/unit.txt`, medians of 5 repetitions; `run1/unit/summary.txt`)

| Test or assertion | Result | Evidence (file) |
|---|---|---|
| First trigger: w=16, L=100 | `rowsCounted` 100, 100 rows out, `isDone` true | `unit.txt` `warm.*` |
| `rowsCounted == L == output rows` for 12 pairs x 5 reps | all hold (no mismatch) | `summary.txt` line 4 |
| NONE, w=16 | output 1 200 000 rows in all 5 reps, retained 370 MB | `unit.txt` `NONE.*` |
| Retained heap R(w, L), bytes | w=16: L=100 31 312; 1 000 308 976; 10 000 3 019 536; 1 000 000 308 847 184. w=1024: L=1 000 1 317 008; 10 000 13 176 256. w=65536: L=100 6 582 880; 1 000 65 829 008 | `selfcheck.txt` UNIT lines |
| Marginal bytes per extra row m(w) | m(16) 301.2, m(1024) 1 317.7, m(65536) 65 829.0 (retained); 304, 1 312, 65 824 (`unsharedHeapSize`) | `summary.txt` |
| Slope: m(1024) - m(16), m(65536) - m(16) | 1 016.5 (bounds 907 to 1 224) and 65 527.9 (bounds 58 968 to 75 412); `unshared` 1 008 and 65 520 | `summary.txt` |
| Ratio m(65536) / m(16) | 218.6 (>= 50) | `summary.txt` |
| Linear in L | w=16: bytes per row at L=10 000 vs 1 000 000 ratio 1.023; w=65536: L=100 vs 1 000 ratio 1.000 | `summary.txt` |
| Dead rows (90 percent deleted markers), L = 1, 100, 1 000 | `rowsCounted` = L, live output = L, rows pulled 1, 991, 9 991 (bounds 10L-9 to 10L+1) in all 5 reps | `selfcheck.txt` UNIT dead |
| Byte-stop control (8 MiB of `unsharedHeapSize`) | rows kept 27 595 / 6 394 / 128 for w=16 / 1 024 / 65 536; `unshared` sum 8 388 880 / 8 388 928 / 8 425 472; retained heap medians 8 515 912 / 8 427 976 / 8 492 208 (flat across a 4 096 x range of widths); **one of 15 repetitions** (w=16, rep 3) read 3 728 336 | `selfcheck.txt` UNIT ctl; `summary.txt` MISMATCH line |
| OutOfMemoryError | none | `summary.txt` |

**Cluster tier** (`run1/cluster/summary.txt`; A = allocated bytes of the query minus idle drift, median of 3; H = peak heap used minus baseline, median)

| Capacity value | Run (control / A / B / C) | Observable (§9d) | Reading | Evidence (file) |
|---|---|---|---|---|
| width 100 B (`t_small`) | U, unpaged, LIMIT 10 / 100 / 1 000 / 10 000 / 100 000 / none | A (MB) | 0.07 / 0.11 / 1.3 / 14.6 / 136.5 / 157.5 (rows 10 to 120 000) | `summary.txt` ROW lines |
| width 10 KiB (`t_med`) | U, unpaged, LIMIT 10 / 100 / 1 000 / none | A (MB) | 0.6 / 4.8 / 42.4 / 67.7 | same |
| width 100 KiB (`t_big`) | U, unpaged, LIMIT 10 / 100 / 1 000 / none | A (MB) | 5.3 / 46.8 / 415.7 / 614.2 | same |
| marginal allocated bytes per row a(t) | U | [A(1000)-A(10)]/990 | 1 286 / 42 250 / 414 505 for 100 B / 10 KiB / 100 KiB; differences 40 964 (x4.04 of the 10 140 B width difference) and 372 255 (x4.04 of 92 160 B) | `summary.txt` |
| peak heap used H (MB), unpaged LIMIT 1 000 | U | H | t_small 0, t_med 34, t_big 419 (no collection inside the window, so H includes garbage) | `summary.txt` |
| paging `t_big` LIMIT 1 000, fetch 100 | U | rows / pages / total A / largest page A | 1 000 rows, 10 pages, 467.8 MB total (unpaged 415.7), largest page 59.3 MB (0.14 x unpaged) | `summary.txt`, `selfcheck.txt` |
| paging `t_small` LIMIT 100 000, fetch 5 000 | U | rows / pages / A | 100 000 rows, 20 pages, 146.7 MB (unpaged 136.5) | same |
| control: `local_read_size_fail_threshold` 20 MiB | C | `t_big` LIMIT 1 000 and none | read-size abort in 3 of 3 (`loaded over 21036352 bytes ... READ_SIZE`), A 73.6 MB for both (uncapped: 415.7 and 614.2) | `cluster/session.log`, `summary.txt` |
| control | C | `t_big` 100, `t_med` 1 000 | pass, full answer, A 46.8 and 42.4 MB (U: 46.8, 42.4) | same |
| control | C | `t_small` LIMIT 100 000 | **abort in 3 of 3** (A 49.9 MB; U: 136.5 MB, 100 000 rows); B3f predicted a pass | `summary.txt` |
| errors in `system.log` | U, C | ERROR lines, `java.lang.OutOfMemoryError` | 0 and 0 | `cluster/session.log` |

### 4.2 Conclusion and logic

1. **Validity** — Valid. The limit was reached in every pair: `rowsCounted == L` and the output equals L [observed: `unit/summary.txt`]; rows returned equal min(LIMIT, rows) in all 49 recorded queries of lifetime U [observed: `cluster/summary.txt` line 1]. First-trigger checks held: U `t_big` LIMIT 1 000 returned 1 000 rows and allocated 415.7 MB; C aborted with a read-size error [observed: `cluster/session.log`]. Fixed settings: heap 2 GiB [observed: `cluster/U/system-log-grep.txt`], `row_cache_size` 0, guardrails off in U and the 20 MiB local-read threshold only in C [observed: `cluster/{U,C}/cassandra.yaml`], no concurrent load [inferred: one client at a time by construction].
2. **Readings** — (a) one unit control repetition (w=16, rep 3) read 3.7 MB instead of about 8.5 MB; the other 14 and every median agree [observed: `selfcheck.txt`]; cause not found [inferred: a GC-reading artefact]. (b) one allocation window read negative (-75 MB for one of the three `t_small` LIMIT 10 000 repetitions in the independent estimate) because a thread that exits takes its count with it; medians absorb it [observed: `selfcheck.txt`]. (c) In lifetime C the `t_small` LIMIT 100 000 query was aborted although its payload is 12 MB: the local-read size counts row heap, not payload, so it exceeded 20 MiB [inferred from the abort message; not measured separately]. (d) H is quantised to 16 MiB regions and includes uncollected garbage; it is not used for the verdict.
3. **Matched row** — Unit B2g row 1: "Retained bytes at fixed limit grow with width (m(65536) / m(16) >= 50 and the slope bounds of B2f hold) while `rowsCounted` is constant": ratio 218.6, slopes 1 016.5 and 65 527.9 inside the bounds, `rowsCounted` = L for all pairs [observed: `unit/summary.txt`]; the positive-control row also holds on medians (retained about 8.5 MB for every width while the row-limit series reaches 0.3, 1.3 and 65.8 MB at L=1 000) [observed: `selfcheck.txt`]. Cluster B3g row 1: first-trigger checks held; a(t_med)-a(t_small) = 40 964 >= 10 140 and a(t_big)-a(t_med) = 372 255 >= 92 160 (each at most 10 x); the control aborts `t_big` LIMIT 1 000 and none on every repeat and caps A (73.6 MB <= 0.5 x 415.7 MB; 73.6 vs 73.6 MB between LIMIT 1 000 and none) [observed: `cluster/summary.txt`]. **One sub-prediction of B3f's control bullet did not hold** (`t_small` LIMIT 100 000 was meant to pass under the 20 MiB cap and was aborted), and one of the unit control's 15 repetitions is outside its band. Neither is a row of the tables; both are recorded, not tuned.
4. **Excluded rows** — Unit and cluster "flat across widths" (Refuted): m(65536) - m(16) = 65 528 against a refuting bound of 6 552, and a(t_med) - a(t_small) = 40 964 against 1 014 [observed]. "`rowsCounted != rowLimit`" and "rows returned > LIMIT": none [observed]. "Dead rows counted": `rowsCounted` = L with 10L-9 rows pulled [observed]. "Control does not move / limit never reached / OOM": the control moved (abort, A capped), every limit was reached, 0 OOM [observed]. The partial row (slopes between 0.1 and 1.0 times the width difference, or above 10): the slopes are x1.0 (unit) and x4.04 (cluster), inside [1, 10] [observed].
5. **Observed vs. inferred** — Inferred: (i) allocation tracks the memory pressure of the read path, not retained memory (the cluster tier cannot read a single query's live set); the unit tier measures retained heap directly and agrees with the claim; (ii) the 4.04 x amplification (each payload byte allocated about four times across replica read, response, coordinator and client frame) is an inference from the slope, not a traced path; (iii) the C `t_small` abort is due to row-heap accounting; (iv) no concurrent load.
6. **Deviations and gaps** — The cluster tier has no live-set reading; H has 16 MiB resolution and includes garbage. The control is a replica-side guardrail. The `-Xmx4G` and tracing controls were not run (declared in the audit). The unit control is harness-side. A single node: coordinator and replica are one JVM. One unit control repetition and one control sub-prediction missed (parts 2 and 3).

7. **Core question** — Usage does not follow the row-count constraint: at a fixed LIMIT, retained bytes rise with row width in proportion to the width (unit: the bytes per row of a 64 KiB row are 218 x those of a 16 B row; cluster: allocation per row 41 KB at 10 KiB and 415 KB at 100 KiB against 1.3 KB at 100 B), so the counter at the target line bounds the number of rows and not their bytes [parts 1 and 3]. A byte cap on the same workload binds at its threshold regardless of LIMIT (unit: about 8.5 MB for every width; cluster: 73.6 MB at LIMIT 1 000 and at none against 415.7 and 614.2 MB) [part 3], so the workload could have shown a cap and did not show one for the row limit. Paging is a count too and bounds the per-request bytes only as count x width (largest page 0.14 x the unpaged query, for a tenth of the rows) [4.1].

**Conclusion (one line):** Unit B2g row 1 and cluster B3g row 1 — claim confirmed (does not cap), with the two recorded misses of part 3.

## 5. Self-check of run 1 — AI

### 5.1 Check of run 1's conclusion

`harness/cql-row-limit-incrementRowCount-rowsCounted--autonomous/selfcheck.py` re-parsed `unit.txt`, `alloc.csv` and `queries.jsonl` without the analyzers and with a different allocation estimator (interpolated counter at t0 and t1 + 1 s, idle rate of the 1 s before t0); output in `run1/selfcheck.txt`.

| Part | Holds? (yes / no) | Note (file re-read) |
|---|---|---|
| 1. Validity | yes | `unit.txt`: `rowsCounted` and `out` equal L in every pair and rep (`selfcheck.txt` UNIT lines); `queries.jsonl` U: 1 000 rows for `t_big` LIMIT 1 000, no error in the recorded queries; C: aborts as stated; `cassandra.yaml.{U,C}` show the settings; `session.log` shows 0 ERROR and 0 `OutOfMemoryError` lines. |
| 2. Readings | yes | The 3.7 MB control repetition and the negative allocation window are in the raw files as stated; the cause of the first is not known (stated as inferred). |
| 3. Matched row | yes, with the two recorded misses | Independent estimate of the cluster slopes: a(t_med)-a(t_small) = 38 423 (x3.79) and a(t_big)-a(t_med) = 366 534 (x3.98), inside [1, 10] x as before. Independent control: A_C(t_big, 1 000) 68.3 MB <= 0.5 x A_U 406.7 MB, and 68.3 vs 62.2 MB (LIMIT 1 000 vs none). Paging: total 457.6 vs 406.7 MB; largest page 65.8 MB (0.16 x). |
| 4. Excluded rows | yes | The refuting bounds are far from the readings in both estimators. |
| 5. Observed vs. inferred | yes | The inferred list in 4.2 part 5 matches what the files cannot show (live set, accounting of the C abort). |
| 6. Deviations and gaps | yes | As listed; no unlisted deviation found in `session.log`. |
| 7. Core question — the steps from reading to answer follow the audited logic | yes | B1 hypothesis -> test (fixed LIMIT, varied width; byte cap as control) -> prediction (slope bounds) -> reading -> matched row. |

### 5.2 Run 2?

**No** (2026-10-27). The unit tier rests on exact counts and on retained heap, which agrees with the exact `unsharedHeapSize` to within 1 percent; the cluster slopes are repeatable (x4.04 analyzer, x3.8 to x4.0 independent estimator) and sit far from the refuting bound; the result confirms a negative estimate that the code reading already predicted, not a refutation or a bypass. A run 2 would not settle the two recorded misses (control accounting and one harness reading), which are stated in the verdict instead.

## 6. Run 2 — fresh AI session (optional)

Not done (§5.2).

## 7. Comparison — only if run 2 was done

Not applicable.

## 8. Verdict — AI

Jingsong may overrule any verdict at any time; record an override here with its date and reason.

**Stage-3 estimate:** negative. **Outcome class:** true negative (negative, does not cap).

**Claim tested:** (B1) Raising or lowering the CQL row limit does not bound memory by itself. For a fixed LIMIT, the peak memory of a query scales with row width (and with the number of tombstones scanned), so there is no row-count-derived byte bound. "Confirmed" below means this claim held.

| Tier | Verdict (§9a row; for an autonomous file, the B2g / B3g row) | Effect on the constraint | Basis | Date |
|---|---|---|---|---|
| Unit | **Confirmed** (B2g row 1: retained bytes at a fixed limit grow with width, m(65536)/m(16) = 218.6, `rowsCounted` constant); one of 15 control repetitions outside its band (medians hold) | does not cap | run 1 + self-check | 2026-10-27 |
| Cluster | **Confirmed** (B3g row 1: marginal allocated bytes per row grow with width, x4.04; the byte cap binds); one B3f control sub-prediction missed (`t_small` LIMIT 100 000 aborted under 20 MiB) | does not cap | run 1 + self-check | 2026-10-27 |

**Positive control** (a negative-estimate file only): unit, a consumer stop at 8 MiB of `unsharedHeapSize` on the same chain kept about 8.5 MB for widths 16 B, 1 KiB and 64 KiB (flat) while the row-limit series reached 0.3, 1.3 and 65.8 MB at L = 1 000; cluster, `local_read_size_fail_threshold` 20 MiB (a closed Confirmed byte cap) aborted `t_big` LIMIT 1 000 and none and held A at 73.6 MB against 415.7 and 614.2 MB uncapped.

**Feedback filed:** the case file's section D "Stage-4 feedback" updated (uncommitted; the orchestrator commits); no section of the case needs correcting beyond the audit amendments already in D.

**Leftovers on pc12:** no process (checked with `ps`); directories `~/s4-b11-c76`, `~/s4-b11-c76-n`, `~/s4-b11-c76-drv`, `~/s4-b11-c76-logs` (3.6 MB), setup files `~/s4-b11-c76-setup.sh` and `.out`; the tmpfs data `/dev/shm/s4-b11-c76` was deleted after the self-check.
