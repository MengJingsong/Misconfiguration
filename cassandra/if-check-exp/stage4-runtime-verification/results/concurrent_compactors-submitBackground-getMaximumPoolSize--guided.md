# concurrent_compactors-submitBackground-getMaximumPoolSize--guided — stage-4 results  <!-- file: results/concurrent_compactors-submitBackground-getMaximumPoolSize--guided.md; the stem ends in --guided or --autonomous -->
> **Case:** [`concurrent_compactors-submitBackground-getMaximumPoolSize--guided`](../../stage3-ai-deep-read/cases/concurrent_compactors-submitBackground-getMaximumPoolSize--guided.md)
>
> **Status:** verdict filed 2026-10-20 — cluster Refuted (peak extra disk follows `min(n, 8)` × one compaction's output), unit Refuted at the executor level; the claim "does not cap" is refuted; one runbook defect (the control), fixed; no run 2
> 
> **Outcome class:** false negative — stage-3 estimate vs the stage-4 effect on the constraint
>
> **Agent:** guided (the suffix of the case-file stem). One results file per case file.

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
| **Case-file version** | Guided file, hash of §9's text after the audit's amendments (`sed -n '/^## 9\. /,/^## 10\. /p' <file> | git hash-object --stdin`): `06caa02b4db6752a1f765de1abf9bdef516334a4`, computed 2026-10-20 before any harness or run. §9a is frozen at this version, including the dated block 9f (R1–R5). The R6 amendment of 2026-10-20 (control, after the first control run) changes the hash to `391ccb2aa001c0ae9f59eed6182cb89a9a466503`. Commit holding the file: `cd7fec5` (the step-0 audit commit on `main`, frozen version) and `d54fd3a` (with R6). |
| **Harness** | `harness/concurrent_compactors-submitBackground-getMaximumPoolSize--guided/` — written 2026-10-20 after the freeze and before run 1: `ConcurrentCompactorsProbeTest.java`, `unit-run.sh`, `cluster-run.py`, `run-all.sh`, `Jmx.java`; commit `d54fd3a`. |
| **Tiers and values** | Unit (9c): Byteman-held `CompactionTask.runMayThrow` over 8 tables, pool sizes 1 · 2 · 4 · 8. Cluster (9e): one node, `concurrent_compactors` 1 · 2 (default on a one-directory node) · 4 · 8, 8 tables × 4 SSTables × 256 MiB, throughput 16 MiB/s, positive control at 8 with a lowered `max_space_usable_for_compactions_in_percentage`. |
| **Audit bottom line** | **Ready after amendments** — 2026-10-20. After run 1 the control was amended (R6, §3): the §9 hash became `391ccb2aa001c0ae9f59eed6182cb89a9a466503`; the claim, prediction and conclusions rows are unchanged, so the sweep arms were not repeated. |

### 1.1 Design audit

The requirements are in the README, "Step 0 — the design audit". One row per
line of each group; cite the case-file section checked.

| Group | Check | Rating (Met / Partly / Not met) | Note (section checked) |
|---|---|---|---|
| A. Core question | constrained quantity is memory or disk bytes | Met | 9a Test, 9d: extra on-disk bytes of in-flight compaction output; heap read as a secondary. |
| A. Core question | knob varied, ≥ 3 values incl. default — or another approach, with the reason | Met | 9b values 1, 2 (default: `min(8, max(2, min(32 cores, 1 dir)))` = 2, `DatabaseDescriptor.java:777-778`), 4, 8. |
| A. Core question | real resource measured, not only the counter (gap named) | Met | 9d `du -sb` of the data dir minus baseline is the real resource; the running-task count (the check's operand) is read beside it. |
| A. Core question | usage driven to the limit and past it | Met | 8 tables give 8 eligible compactions, so 1, 2 and 4 are exceeded and 8 is reached; 9a row 4 covers a backlog too small. |
| B. Logic | each step says what it establishes | Met | 9a "How this verifies" block matches the steps, prediction and rows. |
| B. Logic | prediction stated in numbers or a clear relation | Partly | "Within the noise band" had no definition. **Amended** (R4): band = range over three repeats of the default value. |
| B. Logic | every plausible outcome has a conclusions row with its evidence | Met | 9a rows: flat + control moves (Confirmed), rises (Refuted), flat + control flat (Not confirmed), backlog too small (Invalid), partial rise (Refuted). The negative-file minimum is present. |
| B. Logic | confirmation needs ceiling-follows-knob and direct disallow evidence | Met | Confirmed needs the flat peaks, the task count `min(n, 8)` and the control moving; the disallow evidence is the task count reaching the pool size. |
| B. Logic | alternative explanations and their controls | Met | Control: lowered byte budget on the same workload (a closed `Confirmed` case); throughput, strategy, heap and directory held fixed (9b). |
| C. Specific | a human can follow it from the intro and the prediction/conclusions | Met | Intro, 9a and 9b state claim, test, steps and rows without the code path. |
| C. Specific | an AI can run the runbook without re-deriving the code path | Partly | `harness/load_tables.py`, the sampler and the Byteman hold are named but not written (step 1). Compaction throughput is a shared limiter, so the "about a minute" in 9b was wrong beyond *n* = 1: **amended** (R1). |
| C. Specific | knob, values, workload, commands, observables, sampling, stop conditions exact | Partly | "256 MiB" SSTables had no definition of on-disk size; the control's `p` had no calibration or filesystem. **Amended** (R2, R3). |
| D. Runnable | harness and environment prerequisites exist or are listed | Partly | Needs a fixed-size local filesystem for the control (a loopback image, as the `DataDirectory_getAvailableSpace` run used) and the three scripts above: listed as step-1 work; `~/stage4-dds.img` already exists on `pc57`. |
| D. Runnable | workload arithmetic reaches the limit (data, time, disk, memory) | Met | 8 GiB in + up to 8 GiB out = 16 GiB on a 40 GiB filesystem; 8 GiB at 16 MiB/s is about 8.5 min per run; heap 8 GiB of 251 GiB. After R1 the stop condition is defined. |
| D. Runnable | load-bearing citations spot-checked against the pinned clone | Met | Checked in the pinned clone: `submitBackground` guard at `CompactionManager.java:245`, `setConcurrentCompactors` at `:2238` (resizes via `adjustCoreSize`), `StorageService.java:1964`, `CompactionTask.java:412` (`hasDiskSpaceForCompactionsAndStreams`). |

| # | Recommendation | Applied? (amendment date and commit, or "left for stage 3") | Why |
|---|---|---|---|
| R1 | Shared compaction limiter: the run lasts about 8.5 min at every value; sample until no compaction is active, at most 20 min | Applied 2026-10-20 (9b, 9f) | the filed "about a minute" is true only at *n* = 1; an unstated stop would cut the *n* = 8 peak |
| R2 | Define 256 MiB as on-disk bytes: compression off, random values, `du -sb` after the load; ceiling = `min(n, 8)` × measured input | Applied 2026-10-20 (9f) | nominal sizes would mis-state the predicted slope |
| R3 | Calibrate `p` in a dry run on a fixed-size loopback filesystem | Applied 2026-10-20 (9e step 4, 9f) | the control must bind at about two compactions |
| R4 | Define the noise band: range over three repeats of the default value | Applied 2026-10-20 (9a text, 9f) | "flat" and "rises" need a numeric edge, set before any reading |
| R5 | Write `load_tables.py`, the 2-s sampler (`du`, `tpstats`, `compactionstats`) and the unit Byteman hold; reuse `harness/max_space_usable_for_compactions…` for the control | step 1 (harness) | prerequisites, not design changes |

**Agreement criteria** — only if run 2 is chosen; filled before run 2 starts.
One row per observable in the case's runbook observables:

| Observable | Must match | Tolerance |
|---|---|---|
| `<observable>` | exactly / in shape | `<what counts as the same>` |

## 2. Environment

| Field | Run 1 | Run 2 (fresh AI session, if done) |
|---|---|---|
| Date | 2026-10-20 (cluster runs 15:25–17:12 EDT; unit run 1 at 17:14 EDT) | not done |
| Node (CloudLab name and type) | `node0.jason92-319347.misconfiguration-pg0.cloudlab.umass.edu` (`pc57`), 32 cores, 251 GiB | — |
| OS and kernel (`uname -r`) | Ubuntu 22.04, `5.15.0-187-generic` | — |
| JDK (`java -version`) | openjdk 11.0.32.1 | — |
| Ant (`ant -version`) | Apache Ant 1.10.12 | — |
| Local `cassandra-src` clone commit | `~/cassandra-run4` at `cassandra-5.0.9` (`b5f2a54210d541339c2e7c17a794195cac0e67c2`), `ant build-test` successful in 1 min 33 s | — |
| Case-file commit / harness commit | `cd7fec5` (frozen) and `d54fd3a` (R6 amendment) / `d54fd3a` | — |
| Storage for node data | `/dev/loop0`, ext4, 40 GiB (41,956,900,864 B) loop-mounted at `/mnt/stage4-cc` from `~/stage4-cc.img` on `/dev/sda3`; commit log on `/dev/sda3` | — |
| Full logs (path, outside the repo) | `~/stage4-logs/cc/<label>/` (`session.log`, `summary.txt`, `samples.csv`, `system.log`, `debug.log`), `~/stage4-logs/cc/unit-run1/` | — |

Heap 8 GiB (`Heap size: 8.000GiB/8.000GiB`, `system.log`); `compaction_throughput` 16 MiB/s (`nodetool getcompactionthroughput` read-back in every `summary.txt`).

## 3. Runbook defects

| # | Run | Step (§9b–§9e) | Problem | Fix | Decision (date) | Case-file commit with the fix |
|---|---|---|---|---|---|---|
| 1 | idle check (before run 1) | 9b "Reset between runs" / 9c load | `nodetool disableautocompaction` at load time is not persistent: after the restore and restart the node compacted at once (idle run: running 2, ks1 +1 GB) | node yaml `autocompaction_on_startup_enabled: false` for every run (harness only; no case-file change) | 2026-10-20 | none needed |
| 2 | `ctl8` | 9e step 4 (control) | A budget that "fits about two compactions" does not bind: the budget check is made per task when it starts, all eight tasks (n = 8) checked in the same millisecond (`ctl8/budget-lines.txt`: 20:07:52,804), each saw the same budget of 2,419,296,249 B and asked for about 1.07 GB, so all eight were admitted (`CompactionsReduced`, `SSTablesDroppedFromCompaction`, `CompactionsAborted` all 0; peak extra disk 7.98 compactions) | the control is two arms with a budget below one compaction (`ctl8r` 0.8 ×, `ctl8a` 0.45 × one compaction's input): case-file 9f R6 and a note in 9e step 4; claim, prediction and conclusions rows unchanged; the sweep arms are not repeated because they do not depend on step 4 (a departure from "the affected tier restarts", decided here by the AI; may be overruled) | 2026-10-20 | `d54fd3a` |

## 4. Run 1

**Scope:** unit tier, pool sizes 1 · 2 · 4 · 8 (one `ant testsome`); cluster tier, labels `idle`, `n2a` `n2b` `n2c` (default 2, three repeats), `n1`, `n4`, `n8`, and controls `ctl8` (filed, did not bind), `ctl8r`, `ctl8a` (amended). **Command log:** `concurrent_compactors-submitBackground-getMaximumPoolSize--guided/run1/` (`cluster/<label>/summary.txt`, `samples.csv`, `budget-lines.txt`; `cluster/run-all*.out`; `unit/run.out`; `selfcheck.py` and `selfcheck.txt`).

### 4.1 Readings

**Unit tier** (`unit/run.out`; test passed, 1 run, 0 failures; 8 tables × 4 SSTables, every `CompactionTask.runMayThrow` held by Byteman)

| Test or assertion | Result | Evidence (file) |
|---|---|---|
| n = 1: `getMaximumPoolSize`, held tasks, executor active count, held input bytes / one table's input | 1, 1, 1; 1.00 | `unit/run.out` |
| n = 2 | 2, 2, 2; 2.00 | `unit/run.out` |
| n = 4 | 4, 4, 4; 4.00 | `unit/run.out` |
| n = 8 | 8, 8, 8; 8.00 (pending 0) | `unit/run.out` |
| All 8 tables end with one SSTable after release (each n) | yes | `unit/run.out` |

**Cluster tier** — baseline `ks1` bytes 8,596,623,858 in every label; one table's four Data.db = 1,074,250,132 B (*C*); `selfcheck.txt` recomputes every figure from `samples.csv`.

| Capacity value | Run (control / A / B / C) | Observable (§9d) | Reading | Evidence (file) |
|---|---|---|---|---|
| idle | control | extra disk; running tasks; heap used | 0 B; 0; 1.62–1.66 GB | `cluster/idle/summary.txt` |
| 2 (default) | A: `n2a` | running tasks (peak); peak extra disk | 2; 2,125,250,744 B = 1.98 *C* | `cluster/n2a/samples.csv` |
| 2 (default) | A repeats `n2b`, `n2c` | same | 2,141,634,744 (1.99 *C*); 2,129,182,903 (1.98 *C*) | `cluster/n2b`, `n2c` |
| 1 | B: `n1` | same | 1; 1,068,752,988 B = 0.99 *C* | `cluster/n1/samples.csv` |
| 4 | B: `n4` | same | 4; 4,297,957,962 B = 4.00 *C* | `cluster/n4/samples.csv` |
| 8 | B: `n8` | same | 8; 8,561,033,949 B = 7.97 *C* | `cluster/n8/samples.csv` |
| 8, budget 2.42 GB | C filed: `ctl8` | same; `CompactionsReduced/Dropped/Aborted` | 8; 8,574,665,437 B = 7.98 *C*; 0/0/0 (did not bind, §3 defect 2) | `cluster/ctl8/` |
| 8, budget 0.859 GB (0.8 *C*) | C amended: `ctl8r` | same | 8 tasks started; 6,447,019,332 B = 6.00 *C*; Reduced 8, Dropped 8 (each task kept 3 of 4 inputs), Aborted 0; "Not enough space … Reducing scope" ×8 | `cluster/ctl8r/` |
| 8, budget 0.483 GB (0.45 *C*) | C amended: `ctl8a` | same | 2,141,127,389 B = 1.99 *C* (8 single-input rewrites of 256 MiB); Reduced 94, Dropped 282, Aborted 116; the node kept retrying until the 25-min cap | `cluster/ctl8a/` |

Noise band (range of the three default runs): 16,384,000 B = 0.015 *C*; peak at 8 minus peak at 1 = 7,492,280,961 B, far above twice the band (32,768,000 B) (`selfcheck.txt`). Every sweep run ended with one SSTable per table and `ks1` bytes = baseline − 200 KB (output = input).

### 4.2 Conclusion and logic

1. **Validity** — valid. The limit was reached: the running-task count equals `min(n, 8)` at 1, 2, 4, 8 [observed: `selfcheck.txt`, `samples.csv`; unit `run.out`]. Hold-fixed settings: `compaction_throughput` 16 MiB/s [observed: each `summary.txt` READBACK], default `max_space_usable_for_compactions_in_percentage` 0.95 (no key in the yaml; no Reduced/Aborted in `n1`–`n8`, `n2*`) [observed: `summary.txt` counters], STCS 4/4 and the 8 × 4 × 256 MiB layout [observed: `prepare/summary.txt` DATA lines, 256.1 MiB each], one local 40 GiB filesystem [observed: FILESYSTEM line], heap 8 GiB [observed: `system.log`], `getconcurrentcompactors` and `MaxPoolSize` equal to *n* [observed: EXPECTED lines]. The backlog was large enough (8 tables ≥ every *n*).
2. **Readings** — the idle-check defect and the unbound filed control are in §3. `ctl8a` did not drop to about 0 as the amendment expected: with budget below two inputs a single-input rewrite (256 MiB) still fits, so eight such rewrites ran repeatedly [observed: `ctl8a/summary.txt`, `system.log` "Compacted … 1 sstables … 256.121MiB"]; its peak 1.99 *C* is still far below 7.97 *C*.
3. **Matched row** — "Peak extra disk rises with the knob (about `min(n, 8)` × one compaction's output) → **Refuted** — usage follows the constraint, indirectly through the number of tasks": peak extra disk 0.99, 1.98, 4.00, 7.97 *C* at *n* = 1, 2, 4, 8 [observed: `selfcheck.txt`], i.e. slope one compaction's output per pool thread; the task count follows the knob [observed]; the spread of the default repeats is 0.015 *C* [observed].
4. **Excluded rows** — flat across values: ruled out by the 7.49 GB rise from 1 to 8 against a 16 MB band [observed]; "task count never reaches the pool size" (Invalid): ruled out, peak tasks = `min(n, 8)` [observed]; "flat but the control does not move" (Not confirmed): the peak is not flat; "rises but less than proportionally, flattening at a second limit": the rise is proportional to within 1 % at every step (0.99, 1.98, 4.00, 7.97) [observed]; the byte-budget control lowers the peak, as a second limit would, but only when set below one compaction (§4.1).
5. **Observed vs. inferred** — inferred: that the peak extra disk is the in-flight compaction output [inferred: output size = input size, `final_ks1` = baseline − 200 KB, and `ks1` bytes rise about 8.4 MB/s per running task in `samples.csv`]; that the unit tier's held-input bytes equal the extra disk the cluster tier sees [inferred: both scale with the task count].
6. **Deviations and gaps** — the filed control (budget fitting two compactions) did not bind and was replaced by two sub-compaction budgets (§3 defect 2); `ctl8a`'s prediction (about 0) was not met because a one-input rewrite fits; heap (secondary reading) rose with running tasks in `ctl8`/`n8` but was not analysed as a conclusion; no run 2; the sweep arms were not repeated after the §9e step 4 amendment (departure recorded in §3).
7. **Core question** — usage follows the constraint: with 8 equal backlog tables, peak extra disk is `min(n, 8)` × one compaction's output at *n* = 1, 2, 4, 8, so `concurrent_compactors` bounds the disk held by in-flight compaction output indirectly through the pool size; the "does not cap" claim fails. Steps: (1) task count `min(n, 8)` [part 1]; (2) peak extra disk per value [part 3]; (3) a known byte cap moves the peak down (`ctl8r` 6.00 *C*, `ctl8a` 1.99 *C*) so the instrument can see a cap [part 2]; (4) the claim needed flat peaks, which did not occur [part 4].

**Conclusion (one line):** "Peak extra disk rises with the knob (about `min(n, 8)` × one compaction's output)" — **Refuted** (the file's claim fails; usage follows the constraint, indirectly through the number of tasks).

## 5. Self-check of run 1 — AI

### 5.1 Check of run 1's conclusion

Every cited raw file was re-opened on 2026-10-20: `selfcheck.py` re-derives each label's baseline, peak extra bytes and peak running tasks from `samples.csv` alone (`selfcheck.txt`), and the READBACK / EXPECTED / counter lines of each `summary.txt`, the `budget-lines.txt` of the controls and the unit `run.out` were read directly.

| Part | Holds? (yes / no) | Note (file re-read) |
|---|---|---|
| 1. Validity | yes | `samples.csv` max running = `min(n, 8)` in `n1`–`n8`; READBACK throughput 16 MB/s, `getconcurrentcompactors` = *n*, `MaxPoolSize` = *n* in every `summary.txt`; baseline equals 8,596,623,858 in every label (`selfcheck.txt`) |
| 2. Readings | yes | the `ctl8a` retry loop is in `ctl8a/summary.txt` (Reduced 94, Aborted 116) and `system.log` shows 1-sstable "Compacted" lines; `ctl8` budget lines show eight simultaneous checks at 20:07:52,804 against 2,419,296,249 B |
| 3. Matched row | yes | recomputed peaks 0.99 / 1.98 / 4.00 / 7.97 *C* (`selfcheck.txt`) match the rise row; the unit ratios 1.00 / 2.00 / 4.00 / 8.00 match |
| 4. Excluded rows | yes | 7,492,280,961 B rise vs 32,768,000 B (twice the band); proportional steps recomputed |
| 5. Observed vs. inferred | yes | `final_ks1` 8,596,423,151 vs baseline 8,596,623,858 in `n*` summaries; the per-task slope read from consecutive `samples.csv` rows (`n2a`: `ks1` grows about 33.7 MB per 2-s sample with two tasks, about 8.4 MB/s each) |
| 6. Deviations and gaps | yes | the defect, the amended control, `ctl8a`'s missed prediction and the omitted repeat of the sweep are all listed |
| 7. Core question — the steps from reading to answer follow the audited logic | yes | the rise row, not the control, decides the verdict; the control only shows the instrument can see a cap |

### 5.2 Run 2?

**No** (2026-10-20). The readings are exact and repeatable (three default repeats within 0.015 *C*); the conclusion rests on observed peaks, not on inferred statements; the verdict refutes the file's own (negative) claim, but the effect is the plain consequence of the pool size and the numbers agree across the unit and cluster tiers.

## 6. Run 2 — fresh AI session (optional)

Not done.

## 7. Comparison — only if run 2 was done

Not applicable.

## 8. Verdict — AI

Jingsong may overrule any verdict at any time; record an override here with its date and reason.

**Stage-3 estimate:** negative (Rule 2: the limit-side operand is a thread-pool size).

**Claim tested:** `concurrent_compactors` does not bound compaction's disk or memory usage; the peak extra disk held for in-flight compaction output is the same at every value of the knob. "Confirmed" below means this claim held.

| Tier | Verdict (§9a row) | Effect on the constraint | Basis | Date |
|---|---|---|---|---|
| Unit | **Refuted** — held tasks and their summed input bytes equal `min(n, 8)` × one table's input (1.00 / 2.00 / 4.00 / 8.00) | caps (indirectly: the pool size bounds the number of concurrent compaction outputs) | run 1 + self-check | 2026-10-20 |
| Cluster | **Refuted** — peak extra disk 0.99 / 1.98 / 4.00 / 7.97 compactions' output at 1 / 2 / 4 / 8, default repeats within 0.015 | caps (indirectly: peak = `min(n, 8)` × one compaction's output) | run 1 + self-check | 2026-10-20 |

**Positive control** (a negative-estimate file only): a byte budget below one compaction moved usage under the same workload and instrument — `max_space_usable_for_compactions_in_percentage` giving a budget of 0.8 × one compaction cut the peak from 7.97 to 6.00 compactions' output (`ctl8r`: eight tasks each reduced to three inputs), and 0.45 × one compaction cut it to 1.99 (`ctl8a`). The filed control (budget 2.25 GiB) did not bind because the budget is checked per task and all eight tasks checked at once (§3). Because the verdict rests on a rising peak, not on a flat one, the control's role is only to show the instrument can see a cap.

**Feedback filed:** the case file's §10 "Stage-4 feedback" field and Notes updated (commit `d54fd3a`); 9e step 4 and 9f R6 amended (control); `_INDEX.md` Stage 4 cell points at this file; the Rule 2 ground "a thread-pool size is not a byte limit" is too strong for pools whose tasks each hold bytes (the other thread-pool rejections, `SEPExecutor` and `concurrent_reads`, deserve the same re-examination).
