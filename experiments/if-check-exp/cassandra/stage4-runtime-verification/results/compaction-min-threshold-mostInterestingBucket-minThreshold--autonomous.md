# compaction-min-threshold-mostInterestingBucket-minThreshold--autonomous — stage-4 results  <!-- file: results/compaction-min-threshold-mostInterestingBucket-minThreshold--autonomous.md; the stem ends in --guided or --autonomous -->

> **Case:** [`compaction-min-threshold-mostInterestingBucket-minThreshold--autonomous`](../../stage3-ai-deep-read/cases/compaction-min-threshold-mostInterestingBucket-minThreshold--autonomous.md)
>
> **Status:** self-checked (2026-10-26); verdict filed; no run 2
>
> **Outcome class:** true negative (estimate `negative`; effect found: does not cap, in both tiers)
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
| **Case-file version** | Autonomous file, sha256 of the whole file after the audit's amendments (A1, U1-U3, C1-C5): `3e688f7b8ad8a7463f67df23602b4fa4fc30506a0f64b739f1bd4551e0727cea` (`sha256sum`, 2026-10-27 01:33 UTC = 2026-10-26 evening, before any harness run's reading; one wording fix to C2 (the invalid `seed=i`) was made after the first cluster shakedown, which failed at its first stress call and produced no reading; the first hash given, `6bdb5f91...`, preceded that fix). Frozen tables (text of B2f through B2g, from `**B2f.` to the line before `**B2h.`): sha256 `5236d82cc404c337ceb494e0d9d76168dfa49b77e36e1be743827148be5d31cb`; (B3f through B3g, to the line before `**B3h.`): `3b4f3a186e2cde2fd1f8f8f317e765a9d6caa136b10686930a25a74ae3b32500`. These tables are unchanged by the amendments (U2 and C5 add precision beside them, as stated in the case file). After run 1 only section D (the feedback field) changed; the file's sha256 with that feedback is `55598eb890a548274388f00bf570a4a3791c9d67d299311034c3603c16120dd8`. Repository commit holding the file: not committed (the orchestrator commits); base commit `93d6365`. |
| **Harness** | `harness/compaction-min-threshold-mostInterestingBucket-minThreshold--autonomous/`: `StcsMinThresholdProbeTest.java`, `unit-run.sh`, `unit-analyze.py`, `cluster-run.py`, `cluster-chain.sh`, `cluster-analyze.py`, `selfcheck.py`, `README.md`. Not committed (the orchestrator commits); base commit `93d6365`. Instrument checks: the test class compiled (`ant build-test`, exit 0, `unit-compile`); a 3-chunk shakedown of the m4 arm on 2026-10-26 19:36-19:41 MDT (not a reading) failed at its first stress call on the invalid `-pop seed=1` (the defect in section 3), and after the fix passed every `EXPECTED:` line (thresholds, autocompaction running, chunk 1 size 22.9 MB in the bucket range, TRACE lines in `debug.log`, tablestats count equal to the Data.db files). |
| **Tiers and values** | Unit (B2): N {3, 7, 15, 31, 40} x min_threshold {2, 4, 8, 16, 32} (max 32), through the static call and the real strategy path; overwrite table (M 4 and 8); max_threshold sweep {4, 8, 32} at N 7 and 40. Cluster (B3): min_threshold {2, 4, 16, 32} (max 32) on 20 flushes, the runtime flip 32 to 4 on the M = 32 arm, and the min 4 / max 4 arm. |
| **Audit bottom line** | **Ready after amendments** — 2026-10-26 |

### 1.1 Design audit

The requirements are in the README, "Step 0 — the design audit". One row per
line of each group; cite the case-file section checked.

| Group | Check | Rating (Met / Partly / Not met) | Note (section checked) |
|---|---|---|---|
| A. Core question | constrained quantity is memory or disk bytes | Partly | A2/B1: the operand is a count of sstables in a bucket; its byte cost is derivable (sstable bytes, bloom filter and index summary memory per sstable). B1 names disk bytes and per-SSTable memory. |
| A. Core question | knob varied, ≥ 3 values incl. default — or another approach, with the reason | Met | B2b {2, 4, 8, 16, 32}, B3b {2, 4, 16, 32}; default 4 included. min_threshold 1 is invalid (A1(a)). |
| A. Core question | real resource measured, not only the counter (gap named) | Partly | B2d reads sstable bytes (a proxy for disk; no heap at the unit tier, named); **U2** adds real live bytes before and after a task. B3d: table-dir bytes, bloom/summary memory; **C3** adds `RssAnon` and live heap. |
| A. Core question | usage driven to the limit and past it | Met | B2c N = minThreshold - 1 and N = minThreshold; B3c 20 sstables against M up to 32 (M = 32 is never reached, M = 2, 4, 16 are). |
| B. Logic | each step says what it establishes | Met | B2e/B3e. |
| B. Logic | prediction stated in numbers or a clear relation | Partly | B3f's M = 16 wording ("at most ~15 or merged after the 16th flush") is vague: **C5** gives the expected 5 without changing the row. Bytes rise with M only with overwrites (B3f says so; B1 states it unqualified): **C2** fixes the duplicate factor (about 8). |
| B. Logic | every plausible outcome has a conclusions row with its evidence | Met | B2g/B3g: confirmed, refuted, flat with control, not confirmed. A non-monotone mix has no row and would be "Not confirmed (no matching row)". |
| B. Logic | confirmation needs ceiling-follows-knob and direct disallow evidence | Partly | The direct disallow evidence (the gate at line 123 held the sstables) was only indirect in B3: **C4(a)** adds the runtime flip 32 to 4 on the same data, and **C1** the trace lines. |
| B. Logic | alternative explanations and their controls (positive control for a negative file) | Partly | B2h/B3h have max_threshold as the second knob; the cluster control (min 4, max 4) is close to the M = 4 arm, so **C4(a)** adds a known-binding change on the same data (the flip), which moves the SSTable count and bytes. |
| C. Specific | a human can follow it from the intro and the prediction/conclusions | Met | A3 walks the code path; B1 is one sentence. |
| C. Specific | an AI can run the runbook without re-deriving the code path | Partly | B3c did not say how stress is chunked, seeded or flushed, nor which table is used (stress makes `keyspace1.standard1`): **C1**, **C2**; B2c did not say real or mocked sstables: **U1**. |
| C. Specific | knob, values, workload, commands, observables, sampling, stop conditions exact | Partly | "5 minutes after the last" and the idle test: **C3**; the unit pair evaluation: **U1**. |
| D. Runnable | harness and environment prerequisites exist or are listed | Partly | Sibling harnesses (`max-threshold-getEstimatedTasks-l0SstableCount--autonomous`) supply the node runner and test pattern; the test class and runner are step-1 work. |
| D. Runnable | workload arithmetic reaches the limit (data, time, disk, memory) | Met | 20 flushes of about 20 MiB = 400 MiB per arm on an 8 GiB tmpfs; 100,000 rows per chunk takes seconds; 5 arms about 5 minutes each. Each flush is under 50 MiB, so the merged output stays in the small bucket. |
| D. Runnable | load-bearing citations spot-checked against the pinned source | Partly | `SizeTieredCompactionStrategy.java:82-83,87,116-131,151,198-200,248-280`, `CompactionParams.java:54,79,87,140,169`, `ColumnFamilyStore.java:314,493,3066,3080` match. Wrong: the validation lines and the estimate claim (**A1**); the note to `AbstractCompactionStrategy.java:221`. |

| # | Recommendation | Applied? (amendment date and commit, or "left for stage 3") | Why |
|---|---|---|---|
| A1 | Fix the validation citations (min >= 2, min <= max) and the estimate claim (uses both thresholds) | Applied 2026-10-26 (case file, audit amendments) | wrong citations; no effect on B1 |
| U1 | Real sstables, 5 x 5 pairs, static call and real strategy path | Applied 2026-10-26 | B2c did not say how the sstables are made |
| U2 | Overwrite table: live bytes before and after an executed task at M 4, and unchanged at M 8 | Applied 2026-10-26 | real disk bytes at the unit tier |
| U3 | max_threshold control at N 7 and 40 through both paths | Applied 2026-10-26 | the filed control had no pass criterion for N = 40 |
| C1 | Table, node, tmpfs and trace logging exact | Applied 2026-10-26 | stress makes its own table; B3a left storage open |
| C2 | 20 chunks of n = 100000, key space 200,000, flush after each (the `seed=i` first written is not a `-pop` option and was dropped before any run, found by the first shakedown) | Applied 2026-10-26 | the filed workload gave no way to flush periodically with duplicates |
| C3 | End-state values after an idle test; peak recorded for information | Applied 2026-10-26 | judged quantity was not defined |
| C4 | Runtime flip 32 to 4 on the M = 32 arm as positive control and disallow evidence | Applied 2026-10-26 | direct evidence that line 123 held the sstables |
| C5 | Precision for M = 2, 4, 16, 32 counts and the bytes ratio | Applied 2026-10-26 | M = 16 wording vague |
| R1 | B1 says more bytes "for the same ingest"; it holds for disk bytes only with overwrites or tombstones (SSTable count and per-SSTable memory differ regardless) | left for stage 3 | wording of the claim |

**Agreement criteria** — not needed: no run 2 (section 5.2).

## 2. Environment

| Field | Run 1 | Run 2 |
|---|---|---|
| Date | 2026-10-26 (19:41-20:26 MDT; 01:41-02:26 UTC on 2026-10-27) | not done |
| Node (CloudLab name and type) | `pc12` (`node1.jason92-320876...`, `198.22.255.22`), 40 cores, 251 GiB | |
| OS and kernel (`uname -r`) | Ubuntu 22.04, `5.15.0-187-generic` | |
| JDK (`java -version`) | `openjdk version "11.0.32.1" 2026-08-18` | |
| Ant (`ant -version`) | Apache Ant 1.10.12 | |
| Local source copy (from `cassandra/cassandra-5.0.9/` at repository commit …) | `~/s4-b10-sm` (unit tier, `ant build-test`) and `~/s4-b10-sm-node` (node, a copy of the built tree), from repository commit `93d6365`, `git describe` = `cassandra-5.0.9` | |
| Case-file commit / harness commit | not committed (the orchestrator commits); case-file sha256 as in section 1 | |
| Storage for node data | tmpfs `/dev/shm/s4b10sm` (one fresh directory per arm, removed at the end of each arm); unit tier on the node's local disk (`build/test/cassandra`, 34 GB free) | |
| Full logs (path, outside the repo) | `pc12:~/s4-b10-sm-logs/` (`unit1/`, `cluster1/<arm>/`, `selfcheck1.txt`, `shake/`) | |

Port slot 7: node on `127.0.7.1`, JMX 7170. Other cases ran on the same node at the same time on their own slots.

## 3. Runbook defects

| # | Run | Step (§9b–§9e) | Problem | Fix | Decision (date) | Case-file commit with the fix |
|---|---|---|---|---|---|---|
| 1 | shakedown (no reading) | B3c / amendment C2 | `seed=i` is not a `-pop` option: `cassandra-stress` printed `Invalid parameter seed=1` and exited 1 on chunk 1 | amendment C2 reworded: no seed, same distribution for every chunk | 2026-10-26; B3f/B3g unchanged (the ratio criterion of C5 only had its expected range widened to 8-20 before any run) | not committed (orchestrator) |

## 4. Run 1

**Scope:** unit tier, all of B2/U1-U3 (N x M grid 5 x 5 both ways, max_threshold control, overwrite table); cluster tier, all five arms (M = 32, 2, 4, 16, and min 4 / max 4) with 20 chunks each, plus the runtime flip on the M = 32 arm. **Command log:** `compaction-min-threshold-mostInterestingBucket-minThreshold--autonomous/run1/unit/unit-run.log`, `compaction-min-threshold-mostInterestingBucket-minThreshold--autonomous/run1/cluster/<arm>/checks.txt`, `chain1.out`.

### 4.1 Readings

**Unit tier** (`compaction-min-threshold-mostInterestingBucket-minThreshold--autonomous/run1/unit/`; `analyze.txt` has 144 PASS lines and `SUMMARY ALL PASS`; JUnit: 3 tests, 0 failures)

| Test or assertion | Result | Evidence (file) |
|---|---|---|
| Fixtures: N sstables live and N Data.db files, N in {3, 7, 15, 31, 40}, about 1 MiB each, one bucket | all 5 hold | `readings.txt` (`R grid N*.live`, `.dataFiles`, `.static.buckets` = 1) |
| Static `mostInterestingBucket` returned size, 25 pairs | = `min(N,32)` if `>= M`, else empty, in all 25 (e.g. N=7: M 2,4 -> 7; M 8,16,32 -> empty; N=40: 32 for every M) | `readings.txt` `R grid N*.M*.static.returned` |
| Real path `getNextBackgroundTask` after `setCompactionThresholds(M,32)`, 25 pairs | task null iff static result empty; inputs equal the static size | `R grid N*.M*.real.taskNull`, `.real.inputs` |
| Uncompacted bytes (live minus returned bytes) | non-decreasing in M for each N; N=7: 0 (M 2,4), all 7 sstables for M 8,16,32; N=40: the 8 trimmed sstables for every M | `R grid N*.M*.static.uncompactedBytes` |
| `estimatedRemaining` after the real call (A1(b)) | `ceil(N/32)` when `N >= M`, else 0, in all 25 | `R grid N*.M*.real.estimatedRemaining` |
| Control: max_threshold {4, 8, 32} at M=4, N=7 and 40 | returned = `min(N,max)`: N=7: 4,7,7; N=40: 4,8,32, both ways | `R ctl N*.max*.static.returned`, `.real.inputs` |
| Overwrite table (7 flushes of the same 1,000 keys) | M=8: no task, 7 sstables, 7,435,057 B before and after (ratio 1.0000); M=4: task executed, 7 sstables 7,434,904 B -> 1 sstable 1,063,000 B (ratio 0.1430) | `R ovw M8.*`, `R ovw M4.*` |
| Instrument: truncate empties the table | bytes 0 | `R ovw M*.bytesAfterTruncate` |

**Cluster tier** (`compaction-min-threshold-mostInterestingBucket-minThreshold--autonomous/run1/cluster/<arm>/`; end-state after the idle test of C3, arm `m32` first; live distinct keys 198,927 in every arm)

| Capacity value (min_threshold, max 32) | Run | Observable (§9d) | Reading | Evidence (file) |
|---|---|---|---|---|
| 2 | A | SSTable count / table bytes / bloom + summary off-heap / compaction history rows | 1 / 49,486,453 / 248,664 + 34,386 / 19 | `m2/tablestats-end.txt`, `m2/phase-end.json`, `m2/compactionhistory-end.txt` |
| 4 (default) | B | same | 2 / 72,159,891 / 365,088 + 50,402 / 6 | `m4/...` |
| 16 | C | same | 5 / 139,970,167 / 713,808 + 98,384 / 1 | `m16/...` |
| 32 | D | same | 20 / 452,504,486 / 2,324,232 + 319,836 / 0 | `m32/tablestats-end.txt`, `m32/compactionhistory-end.txt` |
| 32 | D | trace: passes that saw one 20-sstable bucket and started nothing | 5 passes (01:47:42 to 01:50:18 UTC) before the flip | `m32/trace-20bucket-lines.txt` |
| 32 -> 4 at run time (C4a) | D flip | SSTable count / table bytes / history rows | 1 / 49,487,201 / 1 (the compaction of 20 sstables started 01:50:24, 5 s after the flip at 01:50:19) | `m32/tablestats-flip.txt`, `m32/compacted-lines.txt`, `m32/checks.txt` |
| min 4, max 4 (B3e step 6) | E | SSTable count / table bytes / history rows | 2 / 72,101,734 / 6 | `mm4/tablestats-end.txt` |
| all | | peak of table-directory bytes during the arm (information, C3) | m2 114,185,267; m4 163,279,010; m16 408,032,900; m32 489,073,675 (includes the flip compaction); mm4 160,507,938 | `<arm>/peak.txt` |
| all | | `RssAnon` / live heap (class histogram) at end-state | 2.90 to 2.92 GB / 91 to 96 MB in every arm (flat) | `<arm>/phase-end.json` |

### 4.2 Conclusion and logic

1. **Validity.** The run was valid. The limit side is reached: 20 flushed sstables of about 22.6 MB (under `min_sstable_size`, one bucket, first-flush check passed) against M up to 32 [observed: `m2/checks.txt` etc., `m32/trajectory.json`]; M = 2, 4, 16 pass the gate and compact, M = 32 never does before the flip [observed: history rows 19, 6, 1, 0]. Hold-fixed settings: the arm's thresholds read back with `getcompactionthreshold` [observed: `<arm>/checks.txt`]; compression disabled, same stress command, `concurrent_compactors: 1`, `compaction_throughput: 0`, `auto_snapshot: false`, 2 GiB heap [observed: `<arm>/commands.log` yaml tail]; every arm idle at end-state (three polls clear) [observed: `idle-end.json`]; the live distinct key count is 198,927 in all five arms [observed: `phase-end.json` `keys`], so the arms hold the same data. The tablestats count equals the Data.db files in every arm [observed: `EXPECTED` lines]. No stress errors in 100 chunks [observed: `stress-*.tail.txt`].
2. **Readings.** Nothing contradicts another. The seeds problem of section 3 changed no reading. Bloom and summary memory are the node's own estimates (`tablestats`), and process-level `RssAnon` (2.90 to 2.93 GB) and live heap (91 to 96 MB) do not follow M: the JVM's footprint is dominated by the 2 GiB pre-touched heap, and the per-SSTable structures here are a few MB [observed: `phase-end.json`]. So the memory side is shown by the counters, with that gap named. The file count after the executed unit task shows 8 Data.db files in the directory with 1 live sstable: the 7 inputs are obsolete files not yet deleted (the live set is what is judged) [observed: `R ovw M4.filesAfter 8`, `sstablesAfter 1`].
3. **Matched row.** B2g rows 1 and 3: "Uncompacted bytes grow (or stay equal) as `minThreshold` rises" and "Returned size = `min(N, maxThreshold)` in control while uncompacted bytes under the `minThreshold` sweep do not drop" -> confirmed [observed: grid and ctl readings above]. B3g row 1: "SSTable count, bloom/summary memory and (with overwrites) bytes rise with M" -> confirmed: counts 1, 2, 5, 20; bloom 0.25, 0.37, 0.71, 2.32 MB; summary 34, 50, 98, 320 KB; bytes 49.5, 72.2, 140.0, 452.5 MB for M = 2, 4, 16, 32 (ratio 9.14 between M = 32 and M = 2, within the expected 8 to 20) [observed: `tablestats-end.txt` of each arm]. The direct disallow evidence: five TRACE passes saw a 20-sstable bucket in the M = 32 arm and started nothing, and 5 s after the runtime flip to min 4 the same 20 sstables were merged into 1 (452.5 MB -> 49.5 MB, the live key count unchanged) [observed: `trace-20bucket-lines.txt`, `compacted-lines.txt`, `tablestats-flip.txt`]. Prediction figures: M = 2 and 4 at most 4 (1 and 2), M = 16 = 5 (5), M = 32 = 20 with zero history rows (20, 0), flip <= 5 (1), unit overwrite ratio <= 0.25 (0.143) and 1.0 [observed].
4. **Excluded rows.** B2g "bytes shrink as minThreshold rises": excluded, uncompacted bytes never fell [observed: monotone check in all five N]. B2g/B3g "bucket never formed or control did not move": excluded, the bucket was one in every unit pair, the control returned `min(N,max)`, and the runtime flip and the min 4 / max 4 arm moved the count [observed]. B3g "Bytes and memory fall as M rises" (refuted row): excluded, they rose in all four values [observed]. B3g "flat usage across M with the control lowering the count": excluded, usage was not flat (count 1 to 20, bytes 9.1x) [observed]. B3g "no flushes produced equal-size sstables": excluded, all flushes 22.6 MB [observed: `trajectory.json`].
5. **Observed vs. inferred.** Inferred: (a) the byte growth is caused by duplicate rows kept uncompacted [inferred: the same 20 sstables fell from 452.5 to 49.5 MB at unchanged key count 198,927 when the gate was opened]; (b) per-SSTable memory grows with the sstable count [inferred: bloom and summary totals scale with the count while the key count is the same in all arms]; (c) the unit "uncompacted bytes" is a proxy for disk, backed by the cluster's directory bytes [inferred]; (d) peaks above the end-state come from compaction input plus output [inferred; information only].
6. **Deviations and gaps.** The hold before the end-state record was 120 s, not 5 min (C3, idle confirmed by polls). Memory is shown by `tablestats` counters, not by RSS (flat). One node, one run per arm, no repeats (run 2 not done). The M = 16 and M = 32 end-states were stable by construction; the M = 2 and 4 end-states depend on compaction timing (the filed rows use ranges). The unit-tier task execution used a table of 7 flushes only.
7. **Core question.** Usage did not follow `min_threshold` as a cap: raising it from 2 to 32 raised the sstable count from 1 to 20, the disk bytes from 49.5 to 452.5 MB and the per-sstable bloom/summary memory about 9x, for the same data (steps 1 to 4 of the logic: the gate at line 123 only decides whether a bucket is compacted; the positive control, a runtime change of the same knob and a `max_threshold` change, moved the same observables). The constraint triggers work and bounds nothing in bytes [inferred from the readings above].

**Conclusion (one line):** B2g/B3g row "usage rises with `min_threshold` (no cap)" — confirmed (claim: usage does not follow the constraint as a cap).

## 5. Self-check of run 1 — AI

### 5.1 Check of run 1's conclusion

`harness/compaction-min-threshold-mostInterestingBucket-minThreshold--autonomous/selfcheck.py` re-parsed the raw files (ant console log instead of `readings.txt`; raw `tablestats-*.txt`, `compactionhistory-*.txt`, `stress-*.tail.txt`, `debug.log` instead of the phase JSON). Output: `compaction-min-threshold-mostInterestingBucket-minThreshold--autonomous/run1/cluster/selfcheck1.txt`, `SUMMARY ALL PASS`. First run of the script found its own bug (the readings are in `ant.log`, not the JUnit XML); fixed and rerun.

| Part | Holds? (yes / no) | Note (file re-read) |
|---|---|---|
| 1. Validity | yes | thresholds, idle flags, equal key counts (198,927) and 0 stress errors re-read from raw files; 5 TRACE passes with 20-sstable buckets re-counted from `debug.log` (01:47:42 to 01:50:18) |
| 2. Readings | yes | tablestats text re-parsed; `RssAnon`/heap flat in `phase-end.json`; the 5 WARN lines per arm in `system.log` are start-up warnings (jemalloc, JMX, swap, map count, host id), no ERROR |
| 3. Matched row | yes | counts 1/2/5/20, bytes and memory non-decreasing, ratio 9.14, flip 20 -> 1 re-derived from raw text |
| 4. Excluded rows | yes | monotonicity recomputed from `ant.log`; control values `min(N,max)` re-checked |
| 5. Observed vs. inferred | yes | inference (a) rests on the `Compacted (...) 20 sstables` line and equal key counts |
| 6. Deviations and gaps | yes | the 120 s hold and the counters-only memory reading are the limits |
| 7. Core question — the steps from reading to answer follow the audited logic | yes | the chain gate -> count -> bytes/memory -> control moves usage is covered by the readings |

### 5.2 Run 2?

**No** (2026-10-26). The conclusion rests on observed counts, bytes and the compaction history; the inferred statements are about cause, and the runtime flip supports them directly on the same data. The result is the filed estimate (negative), not a refutation or a bypass, and a run costs about 45 minutes of node time for no change in the answer.

## 6. Run 2 — fresh AI session (optional)

Not done (section 5.2).

## 8. Verdict — AI

**Stage-3 estimate:** negative. **Outcome class:** true negative (negative, does not cap). The Effect column is what the run found.

**Claim tested:** (B1) usage does not follow `min_threshold`: with a larger value an STCS table keeps more SSTables and more bytes on disk (and more per-SSTable memory) for the same ingest, so `min_threshold` is not an upper cap on disk or memory.

| Tier | Verdict (§9a row; for an autonomous file, the B2g / B3g row) | Effect on the constraint | Basis | Date |
|---|---|---|---|---|
| Unit | **Confirmed** (B2g rows 1 and 3: uncompacted bytes never fall as `minThreshold` rises; control returns `min(N,max)`) | does not cap | run 1 + self-check | 2026-10-26 |
| Cluster | **Confirmed** (B3g row 1: count, bloom/summary memory and bytes rise with M; flip and `max_threshold` control move usage) | does not cap | run 1 + self-check | 2026-10-26 |

**Positive control:** the runtime flip of `min_threshold` 32 -> 4 on the same data (20 sstables, 452.5 MB -> 1 sstable, 49.5 MB), the min 4 / max 4 arm (2 sstables), and at the unit tier the `max_threshold` sweep (returned = `min(N,max)`) and the executed task on the overwrite table (7.43 MB -> 1.06 MB). Peak bytes also rise with M (114, 163, 408, 489 MB), for information.

**Feedback filed:** the case file's section D updated, and its A1/A3 text corrected by the audit amendment A1 (dated 2026-10-26) — commits are the orchestrator's. Recommendation R1 (B1 wording: disk bytes differ only with overwrites or tombstones) left for stage 3.

**Leftovers on the node:** none running (no `CassandraDaemon` of this case, `/dev/shm/s4b10sm` removed); the trees `~/s4-b10-sm`, `~/s4-b10-sm-node` and the logs `~/s4-b10-sm-logs/` (about 16 MB for the cluster) stay for inspection.
