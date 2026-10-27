# per-partition-limit-incrementRowCount-rowsincurrentpartition--autonomous — stage-4 results  <!-- file: results/per-partition-limit-incrementRowCount-rowsincurrentpartition--autonomous.md; the stem ends in --guided or --autonomous -->

> **Case:** [`per-partition-limit-incrementRowCount-rowsincurrentpartition--autonomous`](../../stage3-ai-deep-read/cases/per-partition-limit-incrementRowCount-rowsincurrentpartition--autonomous.md)
>
> **Status:** verdict filed (2026-10-27); run 1 done and self-checked; no run 2
>
> **Outcome class:** true negative (estimate `negative`, effect `does not cap` in both tiers) ([definition](../README.md#outcome-class))
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
| **Case-file version** | Repository HEAD at audit `93d6365` (the case file and this results file are uncommitted; the orchestrator commits). sha256 of the whole file after the audit's amendments: `4af2f00aefcab9ca1d70ba9090b6bb8f5c5cd7c9118305dd109ba511ca5af9eb`. **Frozen before any reading (2026-10-27):** sha256 of the text of B2f and B2g (from `**B2f. Predictions.**` to just before `**B2h. Controls.**`; recomputed at audit after the n >= 10 wording of the monotone-in-n line in B3f, before any reading) `8850a824717c98e04c3920b7a18c7bb9f284ec5567112f251a02d2f2d58aa7c1`; sha256 of B3f and B3g (to just before `**B3h. Controls.**`) `5e696d66029039690a6081ac169034ad6b95df5f715cf5dcd1305adb5caf779f`. After defect 1 (a one-sentence B2a amendment, `-XX:-UseTLAB`) the whole-file hash is `3743a461c506a1f689cafbd70d730339fc04d38b054eb1d0e7b818df031cdc69`; the cluster tier ran on the first hash, unit attempt 2 on the second; the two table hashes are the same in both. After section D took the feedback the whole-file hash is `a16e505c062ac87fd11b0095cf9a13b8782cc01b68128b0426fe66fea2cad270`; the table hashes did not change. |
| **Harness** | `harness/per-partition-limit-incrementRowCount-rowsincurrentpartition--autonomous/`, written before run 1 and uncommitted (orchestrator commits): `PerPartitionLimitProbeTest.java`, `unit-run.sh`, `analyze_unit.py`, `mk-known-answer.py`, `loader.py`, `cluster-run.py`, `analyze_cluster.py`, `Jmx.java`, `run1-chain.sh`, `shake-cluster.sh`. **Instrument checks (not readings):** (a) `mk-known-answer.py good` gives 0 mismatches and `bad` (retained heap independent of width) gives 6; (b) unit shakedowns on a 5,000-row source (1 rep) and on the full 20,000-row source (3 reps), logs `~/s4-b11-q77-logs/shake-unit*`: they found that the byte-stop control could not reach 8 MiB with 16 B rows on a 20,000-row source (20,000 x 304 B = 6.1 MB), so the control source was set to 100,000 rows (B2c/B2h amended, B2f/B2g text unchanged and the two table hashes unchanged); (c) cluster shakedown at small scale (`t_small` 4 x 3,000 rows), logs `~/s4-b11-q77-logs/shake-cluster`: both first-trigger checks passed (U: 400 rows, 187 MB allocated; C: ReadFailure with the read-size abort), the query driver, JMX sampler, disk check and analyzer ran end to end. Its mismatches were artefacts of the shrunken table (the analyzer expects 30,000 rows per partition) and are not readings. |
| **Tiers and values** | Unit: n in {1,10,100,1000,10000} x width {16 B, 1 KiB, 64 KiB} (64 KiB to n = 1000) + NONE + dead-row, many-partition and byte-stop series, 20,000-row source. Cluster: 3 tables x 4 partitions (100 B x 30,000; 10 KiB x 300; 100 KiB x 300), PER PARTITION LIMIT n in {1,10,100,1000,10000,none}, two node lifetimes (U uncapped, C with `local_read_size_fail_threshold` 20 MiB), 2 GiB heap, tmpfs data. |
| **Audit bottom line** | **Ready after amendments** (2026-10-27): B2, B3 and B4 rewritten, Ground corrected (case file section D, amendments 1 to 5). Claim B1 unchanged. |

### 1.1 Design audit

The requirements are in the README, "Step 0 — the design audit". One row per
line of each group; cite the case-file section checked.

| Group | Check | Rating (Met / Partly / Not met) | Note (section checked) |
|---|---|---|---|
| A. Core question | constrained quantity is memory or disk bytes | Partly | B1/A2: the constraint is a row count per partition; its byte effect is `rows x width` (derivable). The design measures bytes (heap), so Met for the byte link; the unit itself is rows. |
| A. Core question | knob varied, >= 3 values incl. default | Met | B2b/B3b: n in {1,10,100,1000,10000} and none (the default, `NO_LIMIT`). |
| A. Core question | real resource measured, not only the counter (gap named) | Partly | Original B2d/B3d used allocated bytes and `jstat` EU deltas (garbage included). Amended: retained heap (unit), allocated bytes over JMX with the gap named (cluster). |
| A. Core question | usage driven to the limit and past it | Partly | Original B2c source 10,000 rows = largest class; original B3 had no 64 KiB table. Amended: 20,000-row source, n < source for every pair run; cluster tables hold more rows per partition than every n except `none`. |
| B. Logic | each step says what it establishes | Met | B2e/B3e (as amended) state the first-trigger point, the series and the controls. |
| B. Logic | prediction stated in numbers or a clear relation | Not met | Original "roughly linearly", "about 100 times", "about 160 KiB" were not decidable; amended to numeric relations (B2f/B3f). |
| B. Logic | every plausible outcome has a conclusions row with its evidence | Partly | Original B2g/B3g had no row for the rows-out > n mechanism failure at cluster tier and none for a control that does not bind. Amended rows added. |
| B. Logic | confirmation needs ceiling-follows-knob and direct disallow evidence | Partly | For a negative claim: bytes follow count x width, and a byte cap on the same reads binds (control). Original control (`fetch_size`) is a row count; replaced by a byte guardrail and the byte-stop (unit). |
| B. Logic | alternative explanations and their controls | Met | Dead rows, many partitions with a global-limit control, `NONE` upper bound, paging as a second count bound. |
| C. Specific | a human can follow it from the intro and B2f/B3f | Met | After amendment; original B3 numbers (160 KiB, 1.6 MiB) did not follow from its workload. |
| C. Specific | an AI can run B2/B3 without re-deriving the code path | Met | Entry call `cqlLimits(NO_LIMIT, n)` and counter calls are given; sibling harness reused. |
| C. Specific | knob, values, workload, commands, observables, sampling, stop conditions exact | Partly | Original lacked sampling interval, the 64 KiB table, a stop condition. Amended. |
| D. Runnable | harness and environment prerequisites exist or are listed | Met | Step 1 work: test class, JMX sampler, driver scripts (harness dir); JDK 11, Ant, driver zip present on pc07. |
| D. Runnable | workload arithmetic reaches the limit (data, time, disk, memory) | Not met | Original: 20 x 5,000 x 64 KiB = 6 GiB, and an 800 MiB unpaged read on a 2 GiB heap. Amended to <= 123 MB per answer, tmpfs. |
| D. Runnable | load-bearing citations spot-checked against the pinned source | Met | All hold (case file section D, amendment 5). One prose error: Ground says "ignored for aggregates"; the parser rejects it (`SelectStatement.java:1247-1248`); corrected. |

| # | Recommendation | Applied? (amendment date and commit, or "left for stage 3") | Why |
|---|---|---|---|
| 1 | Rewrite B2 (numeric predictions, 20,000-row source, wider grid, retained heap, extra series, byte-stop control) | Applied 2026-10-27, before any reading | Original predictions not decidable; source equal to the largest limit class |
| 2 | Rewrite B3 (three single-width tables, 4 partitions, driver client, JMX allocation counter, byte-guardrail control, disk-flat check) | Applied 2026-10-27 | Original 64 KiB table missing; 800 MiB unpaged read; `fetch_size` control is a row count |
| 3 | Correct "ignored for aggregates" to "rejected" in Ground | Applied 2026-10-27 | `SelectStatement.java:1247-1248` |
| 4 | Rewrite B4 to the new paths and sizes | Applied 2026-10-27 | consistency |
| 5 | Drop the "clustering rows per partition {100, 5000}" dimension | Applied (in B3 reasons) | adds no count the counter touches |
| 6 | Stage 3: state a numeric prediction and the workload arithmetic when proposing a cluster tier; do not use a row-count control (paging) against a row-count claim | Left for stage 3 | pattern seen in this and the sibling `cql-row-limit-*` cases |

**Agreement criteria** — only if run 2 is chosen; filled before run 2 starts.
One row per observable in the case's §9d:

| Observable | Must match | Tolerance |
|---|---|---|
| `<observable>` | exactly / in shape | `<what counts as the same>` |

## 2. Environment

| Field | Run 1 | Run 2 (fresh AI session, if done) |
|---|---|---|
| Date | 2026-10-27 (unit attempt 1 03:37 EDT, cluster (load and both lifetimes) 03:38 to 03:54 EDT, unit attempt 2 03:54 to 03:56 EDT; the node's clock) | not done |
| Node (CloudLab name and type) | `pc07` (`node0.jason92-320876.misconfiguration-pg0.cloudlab.umass.edu`), 40 cores, 251 GiB; port slot 7: 127.0.7.1, JMX 7170, Byteman 19170 | |
| OS and kernel (`uname -r`) | Ubuntu 22.04, `5.15.0-187-generic` | |
| JDK (`java -version`) | openjdk 11.0.32.1 | |
| Ant (`ant -version`) | Apache Ant 1.10.12 | |
| Local source copy (from `cassandra/cassandra-5.0.9/` at repository commit `93d6365`) | `~/s4-b11-q77` (unit tier, `ant build-test`, local head `8d09f56`) and `~/s4-b11-q77-n` (node, `ant jar`, local head `da5f54b`), both by `copy-source.sh`; `git status` of the source was empty (`~/s4-b11-q77-logs/srcstatus.txt`) | |
| Case-file commit / harness commit | uncommitted (orchestrator commits); case-file hashes in section 1 | |
| Storage for node data | tmpfs `/dev/shm/s4-b11-q77` (data, commitlog, hints, saved caches, logs); unit tier writes only inside the copy | |
| Full logs (path, outside the repo) | `~/s4-b11-q77-logs/run1/{unit,cluster}` (cluster: `U/alloc.csv`, `C/alloc.csv`, `session.log`, node `system.log` segments); unit attempt 1 in `~/s4-b11-q77-logs/run1-unit-attempt1-g1`; shakedowns in `~/s4-b11-q77-logs/shake-*` | |

## 3. Runbook defects

| # | Run | Step (B2a-B2e / B3a-B3e) | Problem | Fix | Decision (date) | Case-file commit with the fix |
|---|---|---|---|---|---|---|
| 1 | unit attempt 1 | B2d (retained heap reading) | With the default G1 and thread-local allocation buffers, the used-heap reading after `System.gc()` is noisy by several hundred KB. Attempt 1 read m(16) = -0.9 B per row (retained heap flat from n = 100 to n = 1,000) while the exact `Row.unsharedHeapSize()` sum read 304 B per row; three lines mismatched (slope w = 1024, ratio m(65536)/m(16), linearity at w = 16), all from the 16 B readings. The same instrument gave 309.9 in a 3-repetition shakedown, so it was noise, not a property of the claim. | `-XX:-UseTLAB` for the test JVM (`-Dtest.jvm.args`); `-XX:+UseSerialGC` was tried first and the build refuses it next to the G1 flag Ant already sets. B2a amended (dated), B2f and B2g unchanged; unit tier restarted from its start. A 3-repetition shakedown with the flag then gave m(16) = 309.0. Attempt 1's summary and raw keys are kept in `run1/unit-attempt1-g1/`. | 2026-10-27, made after reading attempt 1's summary. It is a defect of the instrument, not a change of prediction: no threshold, grid or row was touched, and it is recorded here so the reader can judge it. | uncommitted |

## 4. Run 1

**Scope:** unit tier (attempt 2, 5 repetitions of every point) and cluster tier (two node lifetimes U and C, 3 repeats of every shape). **Command log:** `per-partition-limit-incrementRowCount-rowsincurrentpartition--autonomous/run1/unit/session.log`, `run1/cluster/session-filtered.log` (the `jcmd` lines removed; the full one is on the node).

### 4.1 Readings

**Unit tier** (`run1/unit/summary.txt`, `run1/unit/unit.txt`; harness `analyze_unit.py`; 0 mismatches)

| Test or assertion | Result | Evidence (file) |
|---|---|---|
| First trigger (warm, n = 100, 16 B): rowsCounted 100, inPart 100, out 100, isDone false | ok | `unit/summary.txt` line 1 |
| 70 single-partition points (14 pairs x 5): rowsCounted == inPart == out == n, isDone false; `NONE` out = 20,000 | ok, no point emits more than n | `unit/summary.txt`, `selfcheck.txt` |
| m(w) retained heap, bytes per extra row between n = 100 and 1,000 | 309.2 (16 B), 1,316.9 (1 KiB), 65,829.0 (64 KiB); unshared sum 304 / 1,312 / 65,824 | `unit/summary.txt` |
| Slopes: m(1024) - m(16) in [958, 1172.8]; m(65536) - m(16) in [62,244, 72,136]; ratio >= 50 | 1,007.7; 65,519.8; 212.9 (retained). 1,008; 65,520; 216.5 (unshared) | `unit/summary.txt` |
| Linear in n at w = 16 and 1 KiB | ratios 1.002 (16 B) and 1.001 (1 KiB), bound 0.9 to 1.1 | `unit/summary.txt` |
| Dead rows (n = 1, 100, 1,000; 90 % deleted-row markers) | rowsCounted == live out == n, pulled in [10n - 9, 10n + 1], ok | `unit/summary.txt` |
| Many partitions (20 x 5,000), `cqlLimits(NO_LIMIT, n)`, n = 1, 10, 100 | out == rowsCounted == 20n, 20 partitions started, pulled in [20n, 20n + 20], ok | `unit/summary.txt` |
| Global `cqlLimits(10)` on the same source | out == rowsCounted == 10, one partition started, ok | `unit/summary.txt` |
| Byte stop at 8 MiB (positive control), `NONE`, 100,000-row source | rows at stop 27,595 / 6,394 / 128 (16 B / 1 KiB / 64 KiB); unshared sum in [8 MiB, 8 MiB + one row); retained 8.52 / 8.43 / 8.49 MB, flat across widths | `unit/summary.txt`, `selfcheck.txt` |

**Cluster tier** (`run1/cluster/summary.txt`, `run1/cluster/{U,C}/queries.jsonl`; harness `analyze_cluster.py`; 0 mismatches). A = allocated bytes per query (MB, median of 3 repeats; the three repeats lie within 1 % of each other except where noted); rows returned; all unpaged unless the fetch size is stated.

| Capacity value (table, n) | Run | Observable | Reading | Evidence |
|---|---|---|---|---|
| t_small (100 B), n = 1 / 10 / 100 / 1,000 / 10,000 / none | U | rows; A | 4 / 40 / 400 / 4,000 / 40,000 / 120,000; 0.14 / 0.20 / 0.68 / 5.30 / 58.11 / 157.5 MB | `cluster/summary.txt` |
| t_med (10 KiB), n = 1 / 10 / 100 / none | U | rows; A | 4 / 40 / 400 / 1,200; 0.36 / 2.29 / 19.16 / 67.72 MB | same |
| t_big (100 KiB), n = 1 / 10 / 100 / none | U | rows; A | 4 / 40 / 400 / 1,200; 2.43 / 21.32 / 187.2 / 614.2 MB | same |
| t_big n = 100, fetch 100 | U | rows, pages; total A; largest page A | 400, 5 pages; 187.2 MB (unpaged 187.2); largest page 85.0 MB | same |
| t_small n = 10,000, fetch 5,000 | U | rows, pages; A | 40,000, 9 pages; 58.9 MB (not in the frozen predictions; recorded) | `cluster/U/queries.jsonl` |
| a(t) = (A(100) - A(10)) / 360 | U | bytes per extra row | 1,350 (100 B); 46,856 (10 KiB); 460,837 (100 KiB) B | `cluster/summary.txt` |
| du -sb of the data directory | U | bytes | 149,089,845 before and after the 49 recorded queries | `cluster/U/du.txt` |
| t_big n = 100 and none | C (20 MiB read-size abort) | outcome; A | all 3 repeats of each failed with ReadFailure code 1300; A = 73.58 / 73.57 MB | `cluster/C/queries.jsonl` |
| t_big n = 10, t_med none, t_small n = 10,000 | C | rows; A | full answers (40 / 1,200 / 40,000 rows); A 21.33 / 67.73 / 58.12 MB, within 0.1 % of lifetime U (t_med none: one repeat read 169.8 MB, the median is 67.73) | same |

### 4.2 Conclusion and logic

1. **Validity.** [observed: `unit/summary.txt`] The first-trigger point stopped at 100 rows with the row limit unset (`isDone` false, `inPart` 100) and 70 of 70 points have `rowsCounted == out == n`. [observed: `cluster/session-filtered.log`] Both cluster first-trigger checks passed (U: 400 rows, 187 MB allocated, at least 40 MB; C: ReadFailure at the read-size abort). [observed: `cluster/cassandra.yaml.U`, `.C`] Row cache 0, key cache 100 MiB, `read_thresholds_enabled` false in U and true with `local_read_size_fail_threshold: 20MiB` in C; heap 2 GiB; data on tmpfs. [observed: `selfcheck.txt`] No `ERROR` line and no `java.lang.OutOfMemoryError` in either node log segment; the largest sample gap was 113 ms against a 25 ms interval. The limit was reached in every pair (source 20,000 rows; 300 or 30,000 rows per partition against n up to 100 or 10,000). The run is valid for both tiers, after defect 1 for the unit tier.
2. **Readings.** [observed: `unit/summary.txt`] The 16 B retained-heap slope (309 B) sits 5 B above the exact 304 B; the larger widths sit 5 B above theirs. [observed: `cluster/C/queries.jsonl`] One repeat of `t_med` none in lifetime C read 169.8 MB against 67.7 MB for the other two; it does not move the median and no prediction depends on it. [observed: `cluster/summary.txt`] A for the cluster point `t_big` n = 100 (187 MB) is 4.6 times its payload (41 MB), the same factor as the slope above the width difference (4.49).
3. **Matched row.** Unit (B2g row 1): "The first-trigger point holds, retained bytes at fixed n grow with width (m(65536) / m(16) >= 50 and the slope bounds of B2f hold), `rowsCounted` equals n, and the byte-stop control stays at about 8 MiB for all widths". [observed: `unit/summary.txt`] m(65536)/m(16) = 212.9, slopes 1,007.7 and 65,519.8, `rowsCounted == n`, byte-stop retained 8.43 to 8.52 MB at 27,595, 6,394 and 128 rows. Cluster (B3g row 1): "The first-trigger checks hold, the width and control predictions of B3f hold, disk is flat". [observed: `cluster/summary.txt`] d1 = a(t_med) - a(t_small) = 45,506 = 4.49 x 10,140 (bound 1 to 10 x); d2 = 413,981 = 4.49 x 92,160; A(small, 100) < A(med, 100) < A(big, 100) = 0.68 < 19.16 < 187.2 MB (>= 40 MB); A rises with n for every table; marginal bytes per row agree within 0.5 to 2 x (1.14 for t_small, 1.30 for t_med, 1.16 for t_big); A(t_big, none) = 614 MB > 187 MB; paging gives 400 rows in 5 pages with total A equal to the unpaged value and the largest page at 85.0 MB, 0.45 x the unpaged A (bound 0.5); disk bytes identical; control: 3 of 3 aborts for n = 100 and none, three below-cap shapes unchanged (ratio 1.00), A_C(100) = 73.6 MB = 0.39 x A_U(100) (bound 0.5) and 1.00 x A_C(none).
4. **Excluded rows.** Unit: [observed: `unit/summary.txt`] the refuting row (m(65536) - m(16) < 0.1 x 65520) is excluded: it is 65,519.8, and `INFO flat-across-widths ... False`. The mechanism-failure row (rows out > n or rowsCounted != n) is excluded: 70 of 70 points, and the many-partition and global-limit series match their rows. Dead rows are not counted (rowsCounted == n, pulled 10n - 9 to 10n + 1). The control row "does not hold retained bytes about 8 MiB" is excluded. Cluster: [observed: `cluster/summary.txt`] the refuting row (flat across widths with the control moving) is excluded: d1 and d2 are 4.49 x the width difference, `INFO refuting condition ... False`; the "partial" row (slopes between 0.1 and 1.0 x, or above 10 x the width difference) is excluded: both are 4.49 x; the control row "does not abort or does not cap A" is excluded: it aborted 6 of 6 and capped A to 0.39 x; rows returned never exceed 4n; disk did not change.
5. **Observed vs. inferred.** [inferred: allocated bytes are a proxy for memory pressure] A counts garbage as well as live bytes (B3d names the gap). The steps from A to "usage" rest on this and on the unit tier's exact retained heap, which shows the same per-row bytes (1,317 B per extra 1 KiB-wide row, 65,829 B per 64 KiB-wide row). [inferred: the cap on bytes that the control shows binds the same reads] The 20 MiB guardrail aborts the same range reads that PER PARTITION LIMIT does not bound; the abort message is client-visible code 1300 and the node log names the threshold (`selfcheck.txt`). [inferred: the single-node, RF = 1, one-range setting stands for the coordinator and replica paths of a larger cluster] it is the same code path per replica.
6. **Deviations and gaps.** Defect 1 (section 3). The shakedowns and unit attempt 1 are not readings. The heap peak H is recorded in `summary.txt` but not used (a 25 ms sampler and G1 make it coarse; it is zero for several short queries). Live retained memory of a single cluster query is not directly observable (B3d); the unit tier covers it. The "clustering rows per partition" dimension of the original design was dropped in the audit. No measurement of off-heap memory was made.
7. **Core question.** The per-partition limit counts live rows per partition: rows out are exactly n per partition (4n in the cluster, 20n in the many-partition unit series, 10 in total only under the global limit), and tombstones are read without being counted. Memory follows the limit only through count x width: at the same n the marginal bytes per row rise 340-fold from 100 B to 100 KiB values in the cluster (1,350 to 460,837 B per row) and 213-fold from 16 B to 64 KiB in the unit tier, so the same n = 100 costs 0.68 MB or 187 MB. A byte cap on the same read (20 MiB) aborts it and cuts A to 0.39 x, and disk does not move with n. So the limit does not cap memory or disk usage.

**Conclusion (one line):** Unit: B2g row 1 (claim confirmed, does not cap). Cluster: B3g row 1 (claim confirmed, does not cap).

## 5. Self-check of run 1 — AI

### 5.1 Check of run 1's conclusion

`harness/per-partition-limit-incrementRowCount-rowsincurrentpartition--autonomous/selfcheck.py` does not import the analyzers; it re-parses `unit.txt`, `alloc.csv`, `queries.jsonl`, the node log segments and `du.txt` (output `run1/selfcheck.txt`, 0 of 15 checks not holding). Its first run flagged the per-query A comparison at a tolerance of 1e-6; the analyzer prints truncated integers, the worst difference was 7.4e-6, and the tolerance was set to 1e-4 and the check re-run (holds).

| Part | Holds? (yes / no) | Note (file re-read) |
|---|---|---|
| 1. Validity | yes | `session-filtered.log`: both first-trigger checks ok; `selfcheck.txt`: no ERROR or OutOfMemoryError, sample gaps <= 113 ms; the yaml files carry the stated settings. |
| 2. Readings | yes | `unit.txt`: 309.2 vs 304 B per row confirmed by an own median; `queries.jsonl`: the 169.8 MB repeat is the third of `t_med` none in C, the other two are 67.7 MB. |
| 3. Matched row | yes | Own recomputation of the slopes, control medians, a(t) (1,350 / 46,856 / 460,837), row counts, abort count (7 queries with code=1300 including the first-trigger), disk bytes: all fall inside the quoted bounds. |
| 4. Excluded rows | yes | Refuting conditions evaluated from the raw numbers: the slopes are 4.49 x (cluster) and 213 x (unit) the width difference; nothing near 0.1. |
| 5. Observed vs. inferred | yes | The inferred statements (proxy; same-read byte cap; single node) are the ones listed; the node log of lifetime C names `local_read_size_fail_threshold` (checked). |
| 6. Deviations and gaps | yes | Defect 1 is recorded with the attempt-1 files kept; no other gap found on re-reading the logs. |
| 7. Core question — the steps from reading to answer follow the audited logic | yes | B1 -> width slope (steps) -> byte cap control -> disk flat; matches the "How this verifies" mapping of the audit (B1, B2b-e, B2f/g and B3b-e, B3f/g). |

### 5.2 Run 2?

**No** (2026-10-27). The cluster conclusion rests on a factor of 4.49 against a refuting bound of 0.1 and the unit conclusion on a factor of 213 against 0.1, both measured twice in independent ways (allocation and exact retained heap), the control moved as predicted, the claim does not refute the case or confirm a bypass, and a run 2 would not change a reading by an order of magnitude. The one defect (heap noise) was found and fixed within run 1.

## 6. Run 2 — fresh AI session (optional)

Not done (section 5.2).

## 8. Verdict — AI

Jingsong may overrule any verdict at any time; record an override here with its date and reason.

**Stage-3 estimate:** negative. **Outcome class:** true negative (negative, does not cap).

**Claim tested (B1):** Node memory and disk use during a read do not follow `PER PARTITION LIMIT` as a cap: the counter stops at n live rows per partition (the mechanism works), but it is a query-supplied row count, not a resource cap; it does not bound bytes (wide cells), tombstones scanned, or unlimited queries (the default). "Confirmed" below always means this claim held.

| Tier | Verdict (B2g / B3g row) | Effect on the constraint | Basis | Date |
|---|---|---|---|---|
| Unit | **Confirmed** (B2g row 1) | does not cap | run 1 (attempt 2) + self-check | 2026-10-27 |
| Cluster | **Confirmed** (B3g row 1) | does not cap | run 1 + self-check | 2026-10-27 |

**Positive control:** a byte bound moved usage where the row count did not. Unit: the byte stop at 8 MiB of `Row.unsharedHeapSize()` held retained heap at 8.43 to 8.52 MB for all three widths (27,595, 6,394 and 128 rows) while the per-partition-limit series at n = 100 held 31 KB, 132 KB and 6.58 MB. Cluster: `local_read_size_fail_threshold` 20 MiB aborted `t_big` n = 100 and none (6 of 6) and held A to 73.6 MB against 187 MB and 614 MB uncapped. Paging (fetch size 100) is a count too: total A unchanged, largest page 85 MB.

**Feedback filed:** the case file's section D "Stage-4 feedback" updated (uncommitted; the orchestrator commits), with the audit amendments (items 1 to 6). Candidates for upstream or documentation: the CQL documentation for `PER PARTITION LIMIT` could say that it is a row count and bounds bytes only through row width; no code change is suggested, since byte-based protection (`local_read_size_*`, `coordinator_read_size_*`) already exists and is off by default.

**Leftovers on the node (pc07):** no process of this tree is running (checked with `ps` for `java.*s4-b11-q77`); the tmpfs data dir `/dev/shm/s4-b11-q77` and the shakedown one were removed (`ls /dev/shm` shows no q77 entry); the trees `~/s4-b11-q77`, `~/s4-b11-q77-n`, `~/s4-b11-q77-drv`, the logs `~/s4-b11-q77-logs` and `~/s4-b11-q77-w`, `~/s4-b11-q77-setup.sh` are left in the home directory for the orchestrator.
