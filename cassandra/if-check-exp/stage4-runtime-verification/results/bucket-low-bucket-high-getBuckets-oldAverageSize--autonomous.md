# bucket-low-bucket-high-getBuckets-oldAverageSize--autonomous — stage-4 results  <!-- file: results/bucket-low-bucket-high-getBuckets-oldAverageSize--autonomous.md; the stem ends in --guided or --autonomous -->

> **Case:** [`bucket-low-bucket-high-getBuckets-oldAverageSize--autonomous`](../../stage3-ai-deep-read/cases/bucket-low-bucket-high-getBuckets-oldAverageSize--autonomous.md)
>
> **Status:** verdict filed (2026-10-26); run 1 and self-check done, no run 2
>
> **Outcome class:** true negative (TN): estimate `negative`, stage-4 effect `does not cap` (both tiers Confirmed)
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
| **Case-file version** | Autonomous file, sha256 of the whole file after the audit's amendments (A1, A2, U1-U3, C1-C4 in the file's section D): `3cdf536c75e6e056ed1b6798d28c8be8aae23afdb9bee7c6878b5945f98bec5e` (`sha256sum`, 2026-10-26, before any harness run). Frozen tables (text from `**B2f.` to the line before `**B2h.`): sha256 `ac268fff767596e6542e4d46b5512e3a0db3b49775efdf6e22256d995ee4b2d9`; (from `**B3f.` to the line before `**B3h.`): `9dde294ee8880ec1c1fe7f401a430fa1d1c0eaf96056132959df4134cb13fca8`. B2f and B3f were replaced by the audit (arithmetic errors, see A2/C2), B2g and B3g are unchanged. Repository commit holding the file: not committed (the orchestrator commits); base commit `93d6365`. |
| **Harness** | `harness/bucket-low-bucket-high-getBuckets-oldAverageSize--autonomous/` (not committed; the orchestrator commits): `model-predict.py` (stand-alone model of `getBuckets` lines 248-292 that produced the frozen numbers; run before any harness run), `StcsBucketProbeTest.java` + `unit-run.sh` + `unit-analyze.py` (unit tier), `cluster-run.py` + `cluster-analyze.py` (one arm per call; EXPECTED: lines stop the arm and stop the node), `run-all.sh` (tier driver, timing lines). Instrument checks before run 1, recorded here as shakedowns, not readings (frozen text unchanged afterwards): (1) the test compiles (`ant build-test`, `BUILD SUCCESSFUL`); (2) one full unit shakedown run (its output was not used to change anything; it matched the analyzer's checks, and the analyzer's model cross-check reproduced the real bucket counts on the measured sizes, which is the known-answer check for the bucket instrument; the executed-task sampler took 173 to 993 samples per task and its peak extra equalled the task's input bytes, the known-answer check for the disk instrument); (3) a toy-scale cluster shakedown (base rows 5,000 instead of 50,000, arms `wc` and `n`; total bytes bound lowered by `SB_MIN_TOTAL`) that exercised start/stop, stress, flush, schema read-back, the sampler, compaction history join and the analyzer's parse (3 compactions of 4 inputs, 17.1 + 9.8 + 5.6 MB, peak extra 0.97 of the largest). Defects found in shakedown and fixed in the harness only: `jstat` cannot attach (Cassandra runs with `PerfDisableSharedMem`), replaced by `jcmd GC.heap_info` (information only); the narrow-arm bucket-listing check. Rows are about 224 bytes (toy: 32.5 MB for 145,000 rows), so the full workload is about 325 MB. |
| **Tiers and values** | Unit (B2): static `getBuckets` on two synthetic lists x (low, high) {(0.9,1.1), (0.5,1.5), (0.01,100)} x minSSTableSize {0, 50 MiB}; real sstables (12 flushes) through the static call and the real strategy path for the three settings, three executed tasks (wide, default, wide with max_threshold 4). Cluster (B3): 4 arms on one local node: narrow, default, wide, wide with max_threshold 4; 12 sstables of 1.15x growing size, about 300 MB. |
| **Audit bottom line** | **Ready after amendments** — 2026-10-26 |

### 1.1 Design audit

The requirements are in the README, "Step 0 — the design audit". One row per
line of each group; cite the case-file section checked.

| Group | Check | Rating (Met / Partly / Not met) | Note (section checked) |
|---|---|---|---|
| A. Core question | constrained quantity is memory or disk bytes | Partly | A2/B1: `bucket_low`/`bucket_high` are dimensionless ratios of sstable bytes to the bucket mean; the resource touched is the disk of a compaction (inputs + output). The case says so and names the heap as not tied. |
| A. Core question | knob varied, ≥ 3 values incl. default — or another approach, with the reason | Met | B2b and B3b: three settings including the default (0.5,1.5); plus `minSSTableSize` 0/50 MiB (unit) and a max_threshold control. |
| A. Core question | real resource measured, not only the counter (gap named) | Partly | B2d reads bucket bytes only (named: no real disk or heap at the unit tier); **U1/U3** add real sstables and sampled Data.db bytes during executed tasks. B3d measures `du`, heap by jstat; **C3/C4** make the peak extra disk and `RssAnon` exact. |
| A. Core question | usage driven to the limit and past it | Partly | There is no limit to reach; the knob is varied to the extremes (never groups / always groups). B3c's workload as filed never reached the claimed groups (see D row below): fixed by **C2**. |
| B. Logic | each step says what it establishes | Met | B2e/B3e state what each step records. |
| B. Logic | prediction stated in numbers or a clear relation | Not met as filed | B2f's numbers were wrong (default 5-8 buckets, 18 GiB, 4.2 GiB largest) and B3f's "some mid-size buckets compact" / 8 GiB peak did not follow from B3c's 12.6 GiB: **A2, C2, C3** replaced B2f/B3f with model-computed numbers (before any reading). |
| B. Logic | every plausible outcome has a conclusions row with its evidence | Met | B2g/B3g cover confirmed, refuted (ceiling), flat/grouping-only, control did not move, heap dependency. A mixed pattern would be "Not confirmed (no matching row)". |
| B. Logic | confirmation needs ceiling-follows-knob and direct disallow evidence | Partly | The claim is that nothing is refused or capped, so the "disallow" evidence is the bucket listing (TRACE "Compaction buckets are" / `getBuckets` output) and the per-compaction input counts; **C1/C3** add them to the cluster tier. |
| B. Logic | alternative explanations and their controls (positive control for a negative file) | Met | B2h/B3h: `max_threshold` is a known-binding count cap on the same resource; **U2** makes the unit control real (`setCompactionThresholds(4,4)`), the cluster control arm is B3b's wide + max 4. |
| C. Specific | a human can follow it from the intro and the prediction/conclusions | Met | A3 walks lines 79-290. |
| C. Specific | an AI can run the runbook without re-deriving the code path | Partly | B2c/B3c did not say real vs mocked sstables, stress options, table name: **U1, C1, C2**. |
| C. Specific | knob, values, workload, commands, observables, sampling, stop conditions exact | Partly | Idle test, sampling periods and the "materially" threshold were open: **C3, C4**. |
| D. Runnable | harness and environment prerequisites exist or are listed | Partly | The sibling harness `compaction-min-threshold-...--autonomous/` supplies the test and cluster runner patterns; the test class, runner and model are step-1 work. |
| D. Runnable | workload arithmetic reaches the limit (data, time, disk, memory) | Not met as filed | B3c: 12 x 50 MiB x 1.5^i = 12.6 GiB (filed as 4 GiB), would not fit a 20 GiB volume with outputs, and at an exact 1.5 ratio the default band would not join neighbours (strict `<`). **C2** rescales to about 300 MB with ratio 1.15 on tmpfs. |
| D. Runnable | load-bearing citations spot-checked against the pinned source | Met (one nit) | `SizeTieredCompactionStrategy.java:76,79,87,116-123,138-152,205-218,241,248-290` and options `:26-31,73,83-89` match; the parse lines are `:40-44` (not 41-44): **A1**. |

| # | Recommendation | Applied? (amendment date and commit, or "left for stage 3") | Why |
|---|---|---|---|
| A1 | Parse citation `:40-44` | Applied 2026-10-26 (case file, section D) | nit |
| A2 | B2 arithmetic and B2f numbers from a model | Applied 2026-10-26 | filed numbers wrong |
| U1 | Unit tier also on real sstables, both the static call and the real strategy path | Applied 2026-10-26 | real resource, and the max_threshold control needs `SSTableReader`s |
| U2 | Real positive control: `setCompactionThresholds(4,4)` on the wide table | Applied 2026-10-26 | B2e step 3 as filed is not executable |
| U3 | Execute the three non-null tasks; sample Data.db bytes every 2 ms for the peak extra | Applied 2026-10-26 | real disk at the unit tier |
| C1 | Node, table, tmpfs, ALTER, TRACE exact | Applied 2026-10-26 | B3a/B3b left them open |
| C2 | B3c replaced: 12 chunks, 50,000 x 1.15^i rows, instrument checks | Applied 2026-10-26 | arithmetic and default-band behaviour |
| C3 | B3f replaced, per-compaction observables, peak extra defined | Applied 2026-10-26 | prediction did not follow from the workload |
| C4 | Heap observable (`RssAnon`) and the "materially" threshold | Applied 2026-10-26 | open term in B3g |
| R1 | A2/B1 "temporary disk" is the task's output, not the table's bytes | left for stage 3 | wording |

**Agreement criteria** — only if run 2 is chosen; filled before run 2 starts.
One row per observable in the case's §9d:

| Observable | Must match | Tolerance |
|---|---|---|
| `<observable>` | exactly / in shape | `<what counts as the same>` |

## 2. Environment

| Field | Run 1 | Run 2 (fresh AI session, if done) |
|---|---|---|
| Date | 2026-10-26 (21:59 to 22:25 local, 2026-10-27 02:xx UTC in logs) | not done |
| Node (CloudLab name and type) | `pc07` = `node0.jason92-320876.misconfiguration-pg0.cloudlab.umass.edu` (40 cores, 251 GiB) | |
| OS and kernel (`uname -r`) | Ubuntu 22.04, `5.15.0-187-generic` | |
| JDK (`java -version`) | OpenJDK 11.0.32.1 | |
| Ant (`ant -version`) | 1.10.12 | |
| Local source copy (from `cassandra/cassandra-5.0.9/` at repository commit …) | `~/s4-b10-sb` by `copy-source.sh` (tag `cassandra-5.0.9`), repository commit `93d6365`; `ant build-test` BUILD SUCCESSFUL in 1 min 12 s; the unit test class was copied into the tree's `test/unit/.../compaction/` by `unit-run.sh` | |
| Case-file commit / harness commit | not committed (orchestrator); case-file sha256 in §1, harness in `harness/bucket-low-bucket-high-getBuckets-oldAverageSize--autonomous/` | |
| Storage for node data | cluster tier: tmpfs `/dev/shm/s4b10sb` (removed after each arm); unit tier: the tree's `build/test/cassandra` on local disk (`/dev/sda3`) | |
| Full logs (path, outside the repo) | `~/s4-b10-sb-logs/run1/{unit,cluster}/` (node logs under `cluster/<arm>/logs/`); toy-scale shakedowns and the first cluster attempt: `~/s4-b10-sb-logs/run1-defect1/`, `unit-shake/` | |

## 3. Runbook defects

| # | Run | Step (§9b–§9e) | Problem | Fix | Decision (date) | Case-file commit with the fix |
|---|---|---|---|---|---|---|
| 1 | cluster, first attempt (arm n) | B3c / C2 (flush after each chunk gives 12 sstables) | At full scale the memtable spilled inside the larger chunks (chunk 10: 11 files, chunk 12: 15 files), so the 12-sstable, 1.15x-ratio shape was lost; the instrument check "12 sstables after the last flush" stopped the arm before any compaction was enabled (no reading of the claim) | Harness only: `memtable_cleanup_threshold: 0.99` in the node's yaml (lesson from set A batch 7); case file, claim, prediction and tables unchanged | 2026-10-26; tier restarted from its beginning | none needed (the case file does not name the memtable setting; recorded here; `run1/defect1-n.out`) |

## 4. Run 1

**Scope:** unit tier (all of B2) and cluster tier (all four arms of B3). **Command log:** `bucket-low-bucket-high-getBuckets-oldAverageSize--autonomous/run1/` (`unit/unit-run.log`, `unit/readings.txt`, `unit/analysis.txt`; `cluster/<arm>/expected-lines.txt`, `cluster/analysis.txt`, `selfcheck.txt`).

### 4.1 Readings

**Unit tier** (`run1/unit/readings.txt`, judged by `run1/unit/analysis.txt`: 36 PASS, 0 FAIL; JUnit XML: 2 tests, 0 failures)

| Test or assertion | Result | Evidence (file) |
|---|---|---|
| Static `getBuckets`, geometric list (32 files, 15,472,761,705 B, largest 3,571,443,917 B), minSize 0: narrow / default / wide | 32 buckets (largest bucket 1 file) / 11 buckets (largest bucket 2 files, 6,318,708,469 B) / 1 bucket of 32 files = 15,472,761,705 B | `readings.txt` `R syn geo.min0.*` |
| Same, minSize 50 MiB | 18 / 7 / 1 buckets (largest bytes as above) | `R syn geo.min50.*` |
| Equal list (32 x 100 MiB), both minSizes, all three settings | 1 bucket of 32 files, 3,355,443,200 B each time | `R syn eq.*` |
| Real sstables (12 flushes, ratios 1.15 between neighbours), static `getBuckets` counts | narrow [1 x 12]; default [6, 6]; wide [12]; each equal to the stand-alone model run on the measured sizes | `R nar/def/wid/ctl static.counts`, analysis |
| Real strategy path, task inputs / input bytes | narrow: no task; default: 6 inputs, 107,707,885 B; wide: 12 inputs, 154,264,933 B (= total); wide with `max_threshold` 4: 4 inputs, 26,558,679 B | `R * real.inputs`, `real.inputBytes` |
| Executed tasks: peak extra Data.db bytes (2 ms sampler, 971 / 993 / 173 samples) | default 107,716,563 (1.000 x input); wide 154,309,665 (1.000 x input); wide/max 4: 26,562,145 (1.000 x input); ordered wide > default > control > 0 (narrow, no task) | `R * real.peakExtra`, `real.samples` |

**Cluster tier** (12 sstables of 1.15x growth, T about 329 MB per arm; `run1/cluster/analysis.txt`; `selfcheck.txt`)

| Capacity value | Run (control / A / B / C) | Observable (§9d) | Reading | Evidence (file) |
|---|---|---|---|---|
| (0.9, 1.1) | A (narrow) | compactions; end sstables; peak extra Data.db | 0; 12; 0 B (0.000 T). TRACE listing: 12 singleton buckets | `n/compactionhistory-ks.txt`, `n/phase-end.json`, `n/compaction-lines-ks.txt` |
| (0.5, 1.5) | B (default) | same | 2 compactions (6 inputs 200.3 MB, 5 inputs 75.9 MB), 3 sstables at the end (buckets were [1, 5, 6], the largest sstable sat alone); peak extra 195.4 MB = 0.593 T = 0.975 x the larger compaction's input | `d/compactionhistory-ks.txt`, `d/compaction-lines-ks.txt`, `d/phase-end.json` |
| (0.01, 100) | C (wide) | same | 1 compaction of 12 inputs, 328.5 MB; 1 sstable at the end; peak extra 330.4 MB = 1.006 T | `w/compactionhistory-ks.txt`, `w/phase-end.json` |
| (0.01, 100), `max_threshold` 4 | control | same | 3 compactions of 4 inputs (56.0, 98.7, 173.9 MB); 3 sstables at the end; peak extra 174.9 MB = 0.532 T | `wc/compactionhistory-ks.txt` |
| all four | heap | peak `RssAnon` in the compaction window | 2.926, 2.907, 2.916, 2.933 GB (n, d, w, wc): spread 0.6% (not monotone). Information: `GC.heap_info` used-heap peaks 0.68, 1.50, 1.25, 1.53 GB (n, d, w, wc): not monotone in the ratio (default above wide) | `analysis.txt`; `phase-end.json` |

### 4.2 Conclusion and logic

1. **Validity** — valid. The knob was set and read back in every arm [observed: `cluster/<arm>/schema-compaction.txt`, EXPECTED line "schema compaction map holds the arm's bucket_low/bucket_high/max_threshold": PASS]; autocompaction was off during the load and on after [observed: `expected-lines.txt`]; each arm had 12 sstables with neighbour ratios 1.139 to 1.157 and T 328 to 329 MB, none compacted during the load [observed: `presizes.json`, EXPECTED lines]; the count cap known to bind (`max_threshold` 4) did move the usage [observed: wc vs w]. Each arm's node was stopped (`exit.txt`: `rc=0 node_stopped=True`). There is no usage limit to reach; the knob values span "never groups" to "always groups", and the extremes were run [observed: narrow 0 compactions, wide 1 compaction of all 12].
2. **Readings** — one prediction detail missed (§4.1, default arm): the buckets were [1, 5, 6], not [6, 6], so 3 sstables remained, not 2. The cause is visible in the TRACE listing: the real neighbour ratios (1.139 to 1.157, not exactly 1.15) put the largest sstable just above 1.5 x the mean of the top bucket [observed: `d/compaction-lines-ks.txt`; the stand-alone model on the idealised row counts is borderline there, a margin of about 1%]. B3f's other default statements held (two compactions, each 4 to 8 inputs; the largest reads 0.608 T, inside 0.5 to 0.85 T; peak extra 0.975 x that). No row of B3g depends on the end count.
3. **Matched row** — B3g row 1, "Peak extra disk tracks the bytes of the chosen bucket (wide ratio highest) and no ratio stops growth → claim confirmed": peak extra 0 (narrow) < 195 MB (default) < 330 MB (wide) [observed: analysis]; each peak equals the input bytes of the largest compaction it ran (0.975 to 1.006) [observed]; nothing refused or stalled in any arm (rc=0, idle reached). Also B3g row 3, "`max_threshold` control lowers the peak below the wide case → positive control worked": 174.9 MB < 330.4 MB, every compaction at most 4 inputs [observed: `wc`]. The unit tier matches B2g row 1 ("largest-bucket byte sum grows with the band width and nothing caps it, while `max_threshold` trimming reduces it": 3.326 / 5.885 / 14.410 GiB largest-bucket bytes; real tasks 0 / 107.7 / 154.3 MB, control 26.6 MB) and row 3 (equal-size list identical at all ratios).
4. **Excluded rows** — B3g row 2 (peak extra the same bounded value for every ratio, or an evident ceiling): peak extra differs by ratio (0, 195, 330 MB) and is not bounded by a constant [observed]; B2g row 2 (some ratio gives a byte-bounded bucket sum irrespective of input): the largest-bucket bytes follow the input at every ratio and the wide setting groups all 14.410 GiB [observed: `R syn geo.min0.wide.largestBytes`]. B3g row 4 / B2g row 4 (limit not reached, control did not move): the wide arm compacted 12 files (more than `min_threshold` 4) and the control lowered the peak [observed]. B3g row 5 (heap differs materially, monotone in the ratio): peak `RssAnon` spread 0.6%; the information-only used-heap peaks are not monotone (default above wide), so the row does not apply under either reading [observed].
5. **Observed vs. inferred** — inferred: that Data.db bytes in the table directory are the disk the compaction needs (the sampler counted Data.db files only; the all-file series, `peakExtra(all)` in `analysis.txt`, is 7 to 8% larger and orders the arms the same way); that peak `RssAnon` is a fair heap observable (it is flat because the heap is pre-sized at 2 GiB; the used-heap series is information only); that the effect on disk of a task is its input bytes, which is the claim's own wording. Everything else is read from the files named.
6. **Deviations and gaps** — the default arm's end count (above); sampling was 0.2 s on the cluster tier (a spike shorter than 0.2 s could be missed; the unit tier's 2 ms sampler saw peak = input bytes exactly, which the cluster values reproduce); the temporary-disk need of a compaction with overwrites or tombstones was not tested (keys were unique) and the claim does not depend on it; heap use by compaction readers and index summaries was not isolated from the baseline (RssAnon/used heap only); a first cluster attempt was stopped by a harness defect (§3).
7. **Core question** — Usage did follow the sstables the compaction picks (inputs, then output), not the ratios: the narrow band picked nothing (no extra disk), the default band picked 5 to 6 files (0.59 T), the wide band all 12 (1.0 T), and the count cap (`max_threshold` 4) was the only setting that lowered the peak below the wide case (steps: parts 3 and 4). `bucket_low`/`bucket_high` therefore do not cap disk (or heap) use; they only change which sstables are grouped.

**Conclusion (one line):** B2g row 1 (unit) and B3g row 1 with row 3 (cluster) — confirmed (claim: the ratios do not cap usage); one B3f numeric detail (default arm end count) did not hold and is recorded.

## 5. Self-check of run 1 — AI

### 5.1 Check of run 1's conclusion

Re-parsed from the raw files by a different route than the analyzers: `harness/.../selfcheck.py` (output `run1/selfcheck.txt`) reads `system.log` "Compacted" lines for the compaction counts and sizes, its own scan of `samples.jsonl` for the peak, `tablestats-pre.txt` for the live bytes, `exit.txt`, and the JUnit XML.

| Part | Holds? (yes / no) | Note (file re-read) |
|---|---|---|
| 1. Validity | yes | `schema-compaction.txt` of each arm shows the bucket_low/high/max_threshold; `presizes.json` ratios 1.139 to 1.157 and totals 328.5 to 329.4 MB; `exit.txt` rc=0, node stopped (all four); JUnit XML: tests=2, failures=0, errors=0. |
| 2. Readings | yes | selfcheck.txt: n 0 compactions; d (6 inputs 200.3 MB, 5 inputs 75.9 MB), 3 end files; w (12, 328.5 MB), 1 end file; wc (4, 4, 4: 56.0, 98.7, 173.9 MB), 3 end files: equal to the history-based numbers. |
| 3. Matched row | yes | Peak extra by the independent scan: n 0.0, d 195.4, w 330.4, wc 174.9 MB (0.593, 1.006, 0.532 of T); ordered w > d > n and wc < w. |
| 4. Excluded rows | yes | No ceiling (0 / 195 / 330 MB); the wide arm's compaction took 12 files; the control moved the peak; heap spread 0.6% (`analysis.txt`). |
| 5. Observed vs. inferred | yes | Data.db vs all-file peak: `analysis.txt` prints both (209.9 MB vs 195.4 MB for default; 355.2 vs 330.4 for wide); same ordering. |
| 6. Deviations and gaps | yes | The default arm's [1, 5, 6] bucket split confirmed in `d/compaction-lines-ks.txt` (first listing `[[12], [1,2,3,4,5], [6,...,11]]` by sstable generation). The B3f detail "ends with 2 sstables" is recorded as not held rather than edited. |
| 7. Core question — the steps from reading to answer follow the audited logic | yes | B1 -> ratios only group; narrow/default/wide differ in picked bytes, not in a bound; the count-cap control binds; matches the case's block. |

### 5.2 Run 2?

**No** — decided 2026-10-26. The unit tier is deterministic (a pure function plus a measured task), the cluster tier's four arms agree with the model to within the stated tolerances except one recorded detail, and no inferred statement that the conclusion depends on is untested (the Data.db-vs-all-files choice does not change the order). Not cheap enough to justify and not clearly needed.

## 6. Run 2 — fresh AI session (optional)

Not done (§5.2).

## 7. Comparison — only if run 2 was done

Not applicable.

## 8. Verdict — AI

Jingsong may overrule any verdict at any time; record an override here with its date and reason.

**Stage-3 estimate:** negative. **Outcome class:** true negative (negative, does not cap).

**Claim tested:** (B1) Changing `bucket_low`/`bucket_high` does not bound disk or heap use: it only changes which sstables are grouped, so peak disk during compaction follows the total bytes of the sstables chosen (up to `max_threshold`), not the ratios, and no ratio value makes the node refuse or cap growth. A bound on usage appears only when a different constraint (`max_threshold`) is applied. "Confirmed" below means this claim held.

| Tier | Verdict (§9a row; for an autonomous file, the B2g / B3g row) | Effect on the constraint | Basis | Date |
|---|---|---|---|---|
| Unit | B2g row 1 (with row 3): **Confirmed** | does not cap | run 1 + self-check | 2026-10-26 |
| Cluster | B3g row 1 (with row 3): **Confirmed** (one B3f detail, default-arm end count, did not hold; recorded in §4.2 part 2) | does not cap | run 1 + self-check | 2026-10-26 |

**Positive control** (a negative-estimate file only): `max_threshold` 4 on the wide setting. Unit: task inputs 4 and 26,558,679 B against 12 and 154,264,933 B, executed peak extra 26.6 MB against 154.3 MB. Cluster: every compaction at most 4 inputs, peak extra 174.9 MB (0.532 T) against 330.4 MB (1.006 T). Both moved, so a known cap on the same resource was visible to these instruments.

**Feedback filed:** the case file's section D "Stage-4 feedback" updated (this verdict and the amendments A1, A2, U1-U3, C1-C4 listed there); no section other than B2c/B2f/B3a/B3b/B3c/B3f and the A1 citation was amended (all before any reading). Not committed (the orchestrator commits).

**Leftovers on the node (pc07):** none running (`CassandraDaemon`, `cassandra-stress`, samplers all exited; `/dev/shm/s4b10sb` removed by the harness). Directories kept: `~/s4-b10-sb` (built tree, includes the copied test class and `build/test/cassandra` data), `~/s4-b10-sb-logs/` (`run1/`, `run1-defect1/`, `unit-shake/`). Delete with `rm -rf ~/s4-b10-sb ~/s4-b10-sb-logs` when no longer needed.
