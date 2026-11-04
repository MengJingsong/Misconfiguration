# unlogged_batch_across_partitions_warn_threshold-verifyBatchType-keySet--autonomous — stage-4 results  <!-- file: results/unlogged_batch_across_partitions_warn_threshold-verifyBatchType-keySet--autonomous.md; the stem ends in --guided or --autonomous -->

> **Case:** [`unlogged_batch_across_partitions_warn_threshold-verifyBatchType-keySet--autonomous`](../../stage3-ai-deep-read/cases/unlogged_batch_across_partitions_warn_threshold-verifyBatchType-keySet--autonomous.md)
>
> **Status:** run 1 done, self-checked, verdict filed 2026-10-26 (unit and cluster tiers)
>
> **Outcome class:** true negative (estimate `negative`, effect `does not cap`)
>
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
| **Case-file version** | Repository HEAD at audit time `93d6365` (the case file is untracked there; the orchestrator commits it). sha256 of the whole file after the audit's amendments (2026-10-26): `5893db10fb69dc3f7c05f3cc8a51dc5ac6e8609d53fa687d31519bef3e23e2fd`. Frozen prediction and conclusion tables (the text from `**B2f.` to before `**B2h.`, then `**B3f.` to before `**B3h.`, concatenated; B2f-g, B3f-g): sha256 `7ee5c72923601febd0e4343531de9649b1d72b7c82ceb9aa8a8c77d33f0d55e4`, taken before any reading. The file's section D changed after the run (feedback only); sha256 of the file with the feedback: `ba561883bc795ad4fa7be00152f5d569cb45ad3cae5c899e590e3036fcf2e61c`. |
| **Harness** | `harness/unlogged_batch_across_partitions_warn_threshold-verifyBatchType-keySet--autonomous/` (written before run 1; commit by the orchestrator) |
| **Tiers and values** | Unit: `unlogged_batch_across_partitions_warn_threshold` 1, 10, 1000 with N=50, N=5 and LOGGED controls and the size-threshold positive control. Cluster: one node, threshold 1, 10, 100000, a repeat of 10, and the positive control (warn 10KiB, fail 20KiB). |
| **Audit bottom line** | Ready after amendments, 2026-10-26 (A1: positive control could not fire; A2: workload arithmetic; A3: protocol 4) |

### 1.1 Design audit

The requirements are in the README, "Step 0 — the design audit". One row per
line of each group; cite the case-file section checked.

| Group | Check | Rating (Met / Partly / Not met) | Note (section checked) |
|---|---|---|---|
| A. Core question | constrained quantity is memory or disk bytes | Partly | B1/A2: the knob counts partition keys, not bytes; the claim is that it caps nothing, and the byte-valued consumers (memtable data size, heap, disk) are the measured quantities (B2d, B3d). Acceptable for a negative file. |
| A. Core question | knob varied, >= 3 values incl. default | Met | B2b: 1, 10, 1000; B3b: 1, 10, 100000 (default 10 included), restart per value. |
| A. Core question | real resource measured, not only the counter | Met | B2d memtable live size + heap; B3d jstat heap, tablestats memtable, du. Gap named (coordinator-transient allocation not observable). |
| A. Core question | usage driven to the limit and past it | Met | 50 keys vs thresholds 1/10 (past) and 1000 (below); 500 keys vs 1/10 and 100000. The limit is a count, reached by construction. |
| A. Core question | positive control (negative file) | Not met -> Met after A1 | B2h/B3b lowered only batch_size_fail_threshold; `verifyBatchSize` reaches the fail branch only when size > warn threshold (`BatchStatement.java:338-340`, fail branch :349-358), and the cluster yaml kept warn at 1000KiB, so the control would not reject. Amended (A1); a second knob that binds on the same resource (batch bytes). |
| B. Logic | each step says what it establishes | Met | B2c-B2e, B3c-B3e state the purpose of every arm and control. |
| B. Logic | prediction stated in numbers or a clear relation | Met | B2f: count(*)=50, warnings by threshold, memtable within 5%; B3f: 1,000,000 rows, within 10%, WARN lines at most one per minute. |
| B. Logic | every plausible outcome has a conclusions row | Partly | B2g/B3g cover confirm, refute by rejection, refute by usage, control, limit-not-reached. A mixed case (usage differs but control does not move) falls to the last row (Not confirmed) or no row; recorded as "Not confirmed (no matching row)" if it occurs. Not amended: adding rows is allowed only before a reading and changes nothing the readings depend on, but the existing rows suffice. |
| B. Logic | confirmation needs ceiling-follows-knob and direct disallow evidence | Met | For a negative claim the direct evidence is the branch firing (warning present) while rows and usage stay unchanged; B2f/B3f require both. |
| B. Logic | alternative explanations and their controls | Met | B2h/B3h: N=5 and LOGGED negative controls, identical bytes, fresh table, repeat for noise. |
| C. Specific | a human can follow it from the intro and the tables | Met | Intro, A3 and B1 are clear. |
| C. Specific | an AI can run it without re-deriving the code path | Partly | Commands are described, not given; client warnings and the log appender need reading instructions (harness supplies them). NoSpamLogger (1 per minute) would suppress the log line of the second threshold within a minute: the harness clears the wrapped loggers between arms (`NoSpamLogger.clearWrappedLoggersForTest`). |
| C. Specific | knob, values, workload, commands, observables, sampling, stop conditions exact | Partly | Values and sizes exact; sampling of heap is coarse by design; B3c's workload count was wrong (A2). |
| D. Runnable | harness and environment prerequisites exist or listed | Met | B2a/B3a use the copy-source tree, `ant jar`, `ant testsome`, Python driver bundled with the tree; the harness is written in step 1. |
| D. Runnable | workload arithmetic reaches the limit | Not met -> Met after A2 | 8 threads x 2000 batches x 500 = 8,000,000 rows (1.6 GB logical) against the stated 1,000,000 rows (200 MB); set 250 batches per thread. Batch ~115 KB, below fail 1000KiB; above warn 10KiB in the control. |
| D. Runnable | load-bearing citations spot-checked | Met | Checked in the 5.0.9 source: Config.java:334 default 10; DatabaseDescriptor.java:2079-2082 getter, no setter; BatchStatement.java:369-396 (check at :388, NoSpamLogger :390, ClientWarn :393), :422 hasConditions, :425 virtual tables, :439-440 order verifyBatchSize then verifyBatchType, :443 mutate; yaml lines 1847/1826. A5 says line 352-359 for the fail check; the actual is :349-358 (immaterial). |

| # | Recommendation | Applied? (amendment date and commit, or "left for stage 3") | Why |
|---|---|---|---|
| 1 | A1: set `batch_size_warn_threshold` with the fail threshold in B2b/B2h/B3a/B3b; control uses warn < batch size | Applied 2026-10-26 (case file, B2b, B2g, B2h, B3a note, B3b) | The fail branch is inside the `size > warn` branch |
| 2 | A2: 250 batches per thread in B3c | Applied 2026-10-26 | 2000 gave 8,000,000 rows |
| 3 | A3: client protocol 4 | Applied 2026-10-26 | batch ~115 KB is near the 131,071 B large-message threshold |
| 4 | Add a conclusions row for "usage differs but the control does not move" | Left for stage 3 | The existing rows suffice; such an outcome is filed as Not confirmed (no matching row) |
| 5 | Give exact commands in B2e/B3e | Left for stage 3 | The harness fixes them |

**Agreement criteria** — only if run 2 is chosen; filled before run 2 starts.
One row per observable in the case's §9d:

| Observable | Must match | Tolerance |
|---|---|---|
| `<observable>` | exactly / in shape | `<what counts as the same>` |

## 2. Environment

| Field | Run 1 | Run 2 (fresh AI session, if done) |
|---|---|---|
| Date | 2026-10-26 (unit 17:19-17:24 MDT; cluster attempt 1 17:38, restart 17:48-18:00 MDT) | not done |
| Node (CloudLab name and type) | `pc12` (`node1.jason92-320876`), 40 cores, 251 GiB; port slot 4 (127.0.4.1, JMX 7140) | |
| OS and kernel (`uname -r`) | Ubuntu 22.04, `5.15.0-187-generic` | |
| JDK (`java -version`) | OpenJDK 11.0.32.1 (G1 for the node) | |
| Ant (`ant -version`) | 1.10.12 | |
| Local source copy (from `cassandra/cassandra-5.0.9/` at repository commit …) | `copy-source.sh` at repository commit `93d6365`: `~/s4-b9-bu-unit` (`ant build-test`, unit tier) and `~/s4-b9-bu-node` (`ant jar`, cluster tier), tag `cassandra-5.0.9` | |
| Case-file commit / harness commit | case file and harness untracked at run time (the orchestrator commits); sha256 in §1 | |
| Storage for node data | cluster: tmpfs `/dev/shm/s4-b9-bu` (removed afterwards); unit: the test tree `build/test` on local `/` | |
| Full logs (path, outside the repo) | `pc12:~/s4-b9-bu-logs/run1/{unit,cluster,cluster-attempt1}/` (full `system.log` per arm in `cluster/<arm>/`); shakedowns in `~/s4-b9-bu-logs/shake/` (not readings) | |

## 3. Runbook defects

| # | Run | Step (§9b–§9e) | Problem | Fix | Decision (date) | Case-file commit with the fix |
|---|---|---|---|---|---|---|
| A1 | audit | B2b, B2g, B2h, B3a, B3b (positive control) | The size check is reached only when the batch is larger than `batch_size_warn_threshold`; the control lowered only the fail threshold (cluster: warn stayed 1000KiB) | warn threshold set with the fail threshold; control expectation unchanged | amended 2026-10-26 before run 1 | uncommitted (orchestrator) |
| A2 | audit | B3c | 2000 batches x 8 threads x 500 = 8,000,000 rows, not 1,000,000 | 250 batches per thread | amended 2026-10-26 before run 1 | uncommitted |
| A3 | audit | B3c | client protocol unstated; batch ~115 KB is near the 131,071 B large-message threshold | protocol 4 | amended 2026-10-26 before run 1 | uncommitted |
| R1 | run 1, attempt 1 (cluster) | B3d/B3e readback `SELECT count(*)` | `ReadTimeout` on all arms at the default read timeouts (1,000,000-partition scan; `attempt1-count-timeout/readtimeout.txt`); the other readings of attempt 1 matched attempt 2 | the node yaml of every arm sets `range_request_timeout`, `read_request_timeout`, `native_transport_timeout` to 600s (no effect on the batch path); the whole cluster tier restarted from the beginning (attempt 2 is the reading) | 2026-10-26, harness only (§9a unchanged) | harness only |
| R2 | harness | B3d `jstat -gcutil` | `jstat` cannot attach: the node runs with `-XX:+PerfDisableSharedMem` | heap used from `jcmd GC.heap_info` about every 1.3 s (`heap.csv`), GC pause time from `gc.log`, heap after `GC.run` once per arm | found in the shakedown, before run 1 | harness only |

## 4. Run 1

**Scope:** unit tier thresholds 1, 10, 1000 (50-key, 5-key, LOGGED batches, repeat within a minute, size-threshold control); cluster tier thresholds 1, 10, 100000, a repeat of 10, and the size control (warn 10KiB, fail 20KiB); 1,000,000 rows per arm. **Command log:** `unlogged_batch_across_partitions_warn_threshold-verifyBatchType-keySet--autonomous/run1/` (`unit/summary.txt`, `cluster/summary.txt`, `cluster/session.log`, per-arm folders, `selfcheck.txt`).

Instrument checks (before run 1, shakedown `shake`, not readings): the unit test's first-trigger check (threshold 1, 50 keys -> client warning and one log line) and the control (rejection) are assertions that fail the test; the cluster script probes with one 500-key batch per arm and stops the arm if the warning (or rejection, for the control) is absent. The shakedowns found R2 and a WARN-count accounting issue (NoSpamLogger allows one line per minute, so the probe's line is the only one in a 20 s workload; the count starts before the probe).

### 4.1 Readings

**Unit tier** (`run1/unit/summary.txt`, `test.out`; JUnit 1 test, 0 failures; 21 EXPECTED lines, 0 NO)

| Test or assertion | Result | Evidence (file) |
|---|---|---|
| threshold 1: 50 keys | 1 client warning, 1 log line, count 50, memtable live 7,450 B | `unit/test.out` |
| threshold 10: 50 keys | 1 client warning, 1 log line, count 50, memtable 7,450 B | same |
| threshold 1000: 50 keys | 0 warnings, 0 log lines, count 50, memtable 7,450 B | same |
| second 50-key batch within a minute (each threshold) | warning again at 1 and 10, no new log line (NoSpamLogger), 0 at 1000; count 100 | same |
| 5-key batch | warning at 1 only; count 5 | same |
| LOGGED 50-key batch | no unlogged warning at any threshold; count 50 | same |
| memtable live bytes after the first 50-key batch | 7,450 / 7,450 / 7,450 (equal) | same |
| control: warn = fail = 1 KiB, threshold 10, same batch | rejected "Batch too large", count 0, memtable 0 | same |

**Cluster tier** (attempt 2; `run1/cluster/summary.txt`, `<arm>/results.json`)

| Capacity value | Run | Observable (B3d) | Reading | Evidence (file) |
|---|---|---|---|---|
| threshold 1 | t1 | rows acked / count(*) | 1,000,000 / 1,000,000 (2000 batches ok, 0 failed) | `t1/summary.txt`, `t1/count.txt` |
| | | client warnings; WARN log lines | 2000 of 2000 batches; 1 (the probe's; NoSpamLogger) | `t1/summary.txt`, `t1/warn-lines.txt` |
| | | heap peak (jcmd, 32 samples) / heap after load + GC.run / GC pause total | 1.508 GB / 0.227 GB / 0.514 s | `t1/results.json`, `t1/heap.csv` |
| | | memtable data size after load / space live after flush / data dir bytes | 59.44 MB / 27.39 MB / 27.28 MB | `t1/results.json` |
| threshold 10 | t10 | count(*) / warnings / WARN lines | 1,000,000 / 2000 / 1 | `t10/summary.txt` |
| | | heap peak / after GC / GC pause | 1.421 GB / 0.227 GB / 0.441 s | `t10/results.json` |
| | | memtable / space live / data dir | 59.39 MB / 27.37 MB / 27.31 MB | same |
| threshold 100000 | t100000 | count(*) / warnings / WARN lines | 1,000,000 / 0 / 0 | `t100000/summary.txt` |
| | | heap peak / after GC / GC pause | 1.520 GB / 0.234 GB / 0.477 s | `t100000/results.json` |
| | | memtable / space live / data dir | 59.37 MB / 27.39 MB / 27.34 MB | same |
| threshold 10, repeat | t10r | count(*) / warnings / WARN lines | 1,000,000 / 2000 / 1 | `t10r/summary.txt` |
| | | heap peak / after GC / GC pause | 1.479 GB / 0.230 GB / 0.474 s | `t10r/results.json` |
| | | memtable / space live / data dir | 59.24 MB / 27.40 MB / 27.29 MB | same |
| control (threshold 10, warn 10KiB, fail 20KiB) | ctl | rows acked / count(*) / batches failed | 0 / 0 / 2000 of 2000 ("Batch too large") | `ctl/summary.txt`, `ctl/count.txt` |
| | | ERROR log lines "exceeding specified threshold" | 2001 (probe + 2000) | `ctl/error-lines.txt`, `selfcheck.txt` |
| | | heap peak / after GC; data dir | 1.120 GB / 0.071 GB; 0.115 MB (schema only) | `ctl/results.json` |

Cross-arm ratios (max/min over t1, t10, t100000, t10r): heap peak 1.070, space live after flush 1.001, data dir 1.002, memtable data size after load 1.003, heap after GC.run 1.033, GC pause total 1.166 (0.441 to 0.514 s; the two threshold-10 arms differ by 7.5%), load seconds 1.101 (`cluster/summary.txt`).

### 4.2 Conclusion and logic

1. **Validity** — valid. The warning branch fired where predicted (unit threshold 1 and 10 with 50 keys, cluster 500 keys at 1 and 10) and did not fire at 1000 / 100000 **[observed: unit/test.out, cluster/summary.txt probe and load lines]**. The hold-fixed settings were confirmed per arm: heap -Xms2G -Xmx2G and G1, `batch_size_warn/fail` 1000KiB (10KiB / 20KiB in the control), the knob read from the yaml by the node's Config echo **[observed: cluster/summary.txt EXPECTED and Config echo lines]**. Fresh data directory per arm **[observed: cluster-run.py wipes; each arm starts at 0 rows, probe key range separate]**. The positive control moved usage: with warn/fail lowered the same batch was rejected (unit: count 0; cluster: 2000 of 2000 rejected, data dir 0.4% of t10, no memtable) **[observed: unit/test.out, ctl/summary.txt]**.
2. **Readings** — the first cluster attempt's `count(*)` failed with ReadTimeout (R1); the tier was restarted and attempt 2 is the reading. The 15-second memtable sampler (`tablestats.csv`) catches a flush sawtooth at different phases (16 to 32 MB between arms) and is not a usage reading; the comparable memtable reading is the one taken right after the load (59.2 to 59.4 MB, ratio 1.003). The commit log directory holds pre-allocated segments (134,217,728 B in every non-control arm) and is not a usage reading. `data dir` sampled at the end (27.3 MB) is after the flush; heap peak is a sample about every 1.3 s over a ~20 s run **[observed: results.json, tablestats.csv, dirsize.csv]**.
3. **Matched row** — B2g rows 1 and 4, B3g rows 1 and 3: "Warning appears only when keys > threshold, count(*) = 50 in all cases, memtable size equal across thresholds" and "Usage flat while the positive control moves" (unit); "Heap, memtable and disk the same across thresholds (within 10%), all rows written, warnings differ" and "Usage flat while the size-threshold control moves (rows 0, writes rejected, lower disk)" (cluster). Unit: warnings 1/1/0, count 50 all, memtable 7,450 B all, control count 0 **[observed]**. Cluster: all 1,000,000 rows at 1, 10, 100000; warnings 2000/2000/0 per batch; heap peak, space live, data dir and memtable within 7% (0.3% for disk and memtable); control 0 rows **[observed]**.
4. **Excluded rows** — Refuted rows (batch rejected or truncated when keys > threshold; usage lower or different with the threshold): excluded, every non-control batch was accepted and written in full at threshold 1 (500 keys against 1) with count = rows sent, and usage did not move with the threshold (ratios above). "No warning at thresholds below the key count, or the control does not reject": excluded, warnings were present at 1 and 10 and the control rejected. GC pause total (ratio 1.166) is the one figure outside 10%; it does not order by threshold (t1 0.514, t10 0.441, t100000 0.477, t10r 0.474) and the same-setting pair differs by 7.5%, so it is run-to-run noise, not a trend **[inferred: from four arms; the repeat measures the noise]**.
5. **Observed vs. inferred** — inferred: (a) unit "heap" is not a criterion (coarse; recorded in `test.out`), the memtable live data size stands for coordinator-side usage; (b) the claim that the absence of an effect at 1,000,000 rows holds for larger batches or counts is not tested; (c) the GC-time spread is noise (above); (d) coordinator-transient allocation per request was not measured (named in B2d/B3d); the heap peak and heap-after-GC stand for it.
6. **Deviations and gaps** — R1 (restart of the cluster tier), R2 (heap by `jcmd`, not `jstat`); the raw `gc.log` of each arm was not kept (the pause sums are in `results.json`); the unit heap reading is coarse by design; the WARN count includes the probe's line. The cluster tier ran 20 s per arm, not the 5 to 10 minutes B3c estimated (the Python client sustained about 50,000 rows/s); the count of rows and the bytes are what the prediction fixes, not the duration.
7. **Core question** — Usage did not follow the constraint: raising the threshold from 1 to 100000 changed only whether the warning was emitted (steps 1 and 3), the same 1,000,000 rows were written and the same bytes reached memory (59 MB memtable data), disk (27.3 MB) and heap (peak within 7%, after-GC within 3%). The same workload and instruments did show usage collapse to zero under a binding cap (the batch size thresholds, positive control), so the flat result is not an artifact of the harness. The unlogged-batch partition-count threshold does not cap memory or disk use; only the separate size thresholds do.

**Conclusion (one line):** B2g "warn-only, no cap" with positive control, and B3g "usage flat while the size-threshold control moves" — confirmed (does not cap).

## 5. Self-check of run 1 — AI

### 5.1 Check of run 1's conclusion

`harness/unlogged_batch_across_partitions_warn_threshold-verifyBatchType-keySet--autonomous/selfcheck.py` re-parsed `test.out`, the JUnit XML and, per arm, `system.log`, `heap.csv`, `dirsize.csv`, `tablestats.csv`, the probe/load lines and `count.txt` content (not `results.json` and not the script's EXPECTED lines): 30 CHECK lines, all ok, "SELFCHECK ALL OK" (`run1/selfcheck.txt`). Its own recomputation of the heap peak matched the script's to the byte; the independent WARN-line count from `system.log` was 1/1/0/1 and 2001 "exceeding specified threshold" ERROR lines in the control.

| Part | Holds? (yes / no) | Note (file re-read) |
|---|---|---|
| 1. Validity | yes | `unit/summary.txt`, `cluster/summary.txt` first-trigger and Config echo lines; per-arm `system.log` shows the knob in the Config echo line |
| 2. Readings | yes | `selfcheck.txt`: acked rows, count, warned batches, WARN counts agree with the arm summaries; `memtable_max` from the 15 s sampler (ratio 1.93) confirms it is not a usage reading, `pre_memtable` ratio 1.003 is |
| 3. Matched row | yes | unit and cluster numbers in `selfcheck.txt` satisfy each part of the rows quoted in 4.2 |
| 4. Excluded rows | yes | no rejection or truncation outside the control (0 ERROR lines in t1/t10/t100000/t10r); GC-time spread addressed |
| 5. Observed vs. inferred | yes | the inferred items do not change the answer; (b) bounds the claim to the tested size |
| 6. Deviations and gaps | yes | R1/R2 recorded; attempt-1 readings (same shape) kept in `attempt1-count-timeout/summary.txt` |
| 7. Core question — the steps from reading to answer follow the audited logic | yes | steps: knob varied (1/10/100000), branch fired (warnings) and rows/bytes unchanged, control moved |

### 5.2 Run 2?

**No** (2026-10-26). The run is repeatable evidence in itself (the middle setting ran twice in the cluster tier, ratios 1.00 to 1.07; the unit tier is deterministic), the result does not refute the case or confirm a bypass, and the claim rests on direct counts rather than inferred statements.

## 6. Run 2 — fresh AI session (optional)

Not done.

## 8. Verdict — AI

**Stage-3 estimate:** negative. **Outcome class:** true negative (negative, does not cap).

**Claim tested:** B1: raising or lowering `unlogged_batch_across_partitions_warn_threshold` changes only whether a warning is emitted; it does not change the coordinator heap or disk used by an unlogged batch, and a batch with more partitions than the threshold is still accepted and written in full (subject to the size fail threshold). "Confirmed" below means this claim held.

| Tier | Verdict (B2g / B3g row) | Effect on the constraint | Basis | Date |
|---|---|---|---|---|
| Unit | Confirmed (B2g: warning only above the threshold, count 50 and memtable equal; usage flat while the size control rejects) | does not cap | run 1 + self-check | 2026-10-26 |
| Cluster | Confirmed (B3g: heap, memtable and disk within 10% across thresholds, all 1,000,000 rows written; flat while the size control rejects) | does not cap | run 1 (attempt 2) + self-check | 2026-10-26 |

**Positive control:** `batch_size_warn_threshold` and `batch_size_fail_threshold` lowered (unit 1KiB/1KiB; cluster 10KiB/20KiB) with the same workload and instruments: unit batch rejected "Batch too large", count 0, memtable 0; cluster 2000 of 2000 batches rejected, 0 rows, data directory 115 KB against 27.3 MB, heap after GC 71 MB against 227 MB (`unit/test.out`, `cluster/ctl/summary.txt`, `cluster/ctl/results.json`). Without lowering the warn threshold the control would not have fired (A1).

**Feedback filed:** the case file's section D "Stage-4 feedback" updated; amendments A1 to A3 (dated 2026-10-26, before run 1) are in B2b, B2g, B2h, B3a, B3b, B3c and listed in section D. The case file and harness are uncommitted; the orchestrator commits.

**Open points / candidates.** (1) The warning is rate-limited by `NoSpamLogger` (one log line per minute) while the client warning fires on every batch. (2) Stage 3's A5 cites the fail check at `BatchStatement.java:352-359`; it is :349-358 (immaterial). (3) Upstream/doc candidate: the yaml comment for `batch_size_fail_threshold` implies it is always enforced; the check runs only above `batch_size_warn_threshold`, so a warn threshold set above the fail threshold disables the fail threshold (`BatchStatement.java:338-340`, :349) — worth a JIRA check.

**Leftovers on pc12:** none running (no CassandraDaemon, ports free, `/dev/shm/s4-b9-bu` removed). Directories kept: `~/s4-b9-bu-unit`, `~/s4-b9-bu-node` (471 MB each, source copies), `~/s4-b9-bu-logs` (4.7 MB, includes the shakedowns).
