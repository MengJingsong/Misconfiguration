# max-threshold-getEstimatedTasks-l0SstableCount--autonomous — stage-4 results  <!-- file: results/max-threshold-getEstimatedTasks-l0SstableCount--autonomous.md; the stem ends in --guided or --autonomous -->

> **Case:** [`max-threshold-getEstimatedTasks-l0SstableCount--autonomous`](../../stage3-ai-deep-read/cases/max-threshold-getEstimatedTasks-l0SstableCount--autonomous.md)
>
> **Status:** **Closed 2026-10-26 — unit Confirmed — does not cap; cluster Confirmed — does not cap** (estimate negative, matched); run 1 only, self-checked; no run 2
>
> **Outcome class:** true negative — stage-3 estimate (negative) vs the stage-4 effect on the constraint (does not cap the line-655 term; see §8 for the separate phase B finding on the real use of `max_threshold`)
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
| **Case-file version** | **Autonomous file:** sha256 of the whole file after the audit's amendments U1-U4 and C1-C7: `9a97d656f1648c3d7727560dafb4b5bee7f5560f202f09e6396daf44a9af1f1e` (`sha256sum`, 2026-10-26, before any harness code or reading). Frozen prediction and conclusion tables (text from `**B2f. Predictions.**` to before `**B2h.`, then `**B3f. Predictions.**` to before `**B3h.`, UTF-8, concatenated): sha256 `cb7898cf6d3368e3f4e7b39c1d13af867d3274080fe0ad8bd9da6fa6a60a2c57` (2148 bytes). Repository base commit `93d6365` (case file uncommitted; the orchestrator commits). The file is later changed only in section D.|
| **Harness** | `harness/max-threshold-getEstimatedTasks-l0SstableCount--autonomous/` (files listed in its README); written after the freeze; not committed (orchestrator commits). **Post-freeze amendment (2026-10-26, before any accepted cluster reading, runbook defect D3; no prediction or conclusions row changed):** C5 corrected (byte term); sha256 now `9a97d656f1648c3d7727560dafb4b5bee7f5560f202f09e6396daf44a9af1f1e` (the frozen B2f-g/B3f-g text hash `cb7898cf…` is unchanged). |
| **Tiers and values** | Unit (B2): `max_threshold` 4, 32, 128 (+ repeats) on 200 L0 sstables, STCS-in-L0 on and off; positive control `sstable_size_in_mb` 1 vs 160. Cluster (B3): arms mt4, mt32, mt128, mt32b, c64, d32 (amendment C3), about 300 L0 sstables each, phase A (compaction held) and phase B (1 MiB/s). |
| **Audit bottom line** | **Ready after amendments** — 2026-10-26 |

### 1.1 Design audit

The requirements are in the README, "Step 0 — the design audit". One row per
line of each group; cite the case-file section checked.

| Group | Check | Rating (Met / Partly / Not met) | Note (section checked) |
|---|---|---|---|
| A. Core question | constrained quantity is memory or disk bytes | Partly | A1/A2: `max_threshold` is a count of sstables (not bytes) and at line 655 caps nothing; the usage that matters is the L0 sstables' disk bytes and the node's heap/off-heap. The count has a derivable byte size (sstable sizes are measured). Accepted for a negative file. |
| A. Core question | knob varied, ≥ 3 values incl. default — or another approach, with the reason | Met | B2b {4,32,128}, B3b {4,32,128}; 32 is the default (`CompactionParams.java:80`). |
| A. Core question | real resource measured, not only the counter (gap named) | Partly | B2d lists heap and disk but the unit tier measures heap coarsely (U3 sets the tolerance); B3d has `du`, `RssAnon`, heap; NMT is not used (C4 names the gap). |
| A. Core question | usage driven to the limit and past it | Met after C1 | B2c 200 > 128 L0 sstables; B3c as filed (20 GB) did not fit the disk; C1 scales to about 300 sstables, still above 128. |
| B. Logic | each step says what it establishes | Met | B2e/B3e steps state the reading taken; C2 adds the phase A/B split. |
| B. Logic | prediction stated in numbers or a clear relation | Met | B2f: 50/6/1 exact; B3f: L0count/max_threshold and ±10% (made exact by C5, computed from the same snapshot). |
| B. Logic | every plausible outcome has a conclusions row with its evidence | Partly | B2g/B3g cover follow, flat, wrong trace, limit never reached, control not moving. The compaction path's real use of the knob (`:328`, `:548`) can move disk in phase B: C6 states how row 2 is read; no row text changed. |
| B. Logic | confirmation needs ceiling-follows-knob and direct disallow evidence | Met | The claim is negative: the pending-count (the "ceiling" operand) follows `L0/max_threshold` while disk/heap/RSS stay flat, with the disable toggle (B2h/B3h) as direct evidence that the term is the only contribution. |
| B. Logic | alternative explanations and their controls (positive control for a negative file) | Partly | B2h's control ("max_sstable_size_in_mb") named a knob that does not exist and an unobservable effect; U4 names `sstable_size_in_mb` and a measurable binding effect (output file size). B3h's `compaction_throughput` 64 MiB/s control is measurable (C7). |
| C. Specific | a human can follow it from the intro and the prediction/conclusions | Met | A3 and B1. |
| C. Specific | an AI can run the runbook without re-deriving the code path | Partly | B2a named a non-existent copy path and B2c a non-existent method; U1/U2 fix; C1-C4 give the cluster commands. |
| C. Specific | knob, values, workload, commands, observables, sampling, stop conditions exact | Partly | B3c left the workload open ("or a smaller run"), B3e had no sampling cadence or stop conditions; C1-C4 supply them. |
| D. Runnable | harness and environment prerequisites exist or are listed | Partly | Probe class and runner are step-1 work; tools exist (`environment.md`). |
| D. Runnable | workload arithmetic reaches the limit (data, time, disk, memory) | Met after C1 | 800k rows of about 1 KB at 2,500/s is 320 s; 0.8 GB on an 8 GiB tmpfs; L0 count above 128 needs at least 129 flushes, about 300 planned. |
| D. Runnable | load-bearing citations spot-checked against the pinned source | Met | `LeveledManifest.java:62,306,328,548-551,655,657`, `LeveledCompactionStrategy.java:278`, `ColumnFamilyStore.java:3086-3094`, `CompactionParams.java:55,80`, `CompactionManager.java:2353-2358`, `ActiveRepairService.java:639`, `DatabaseDescriptor.java:223` re-read in the pinned tree. Defects: `forceBlockingFlush` and `max_sstable_size_in_mb` do not exist in 5.0.9 (fixed by U2/U4). |

| # | Recommendation | Applied? (amendment date and commit, or "left for stage 3") | Why |
|---|---|---|---|
| U1-U4 | Fix the build path, call names, heap tolerance and the positive control of the unit tier | Applied 2026-10-26 (case file B2 amendments) | non-existent method/knob names; control had no measurable effect |
| C1-C7 | Scale the cluster workload, split phase A (compaction held) and B, name arms, observables, arithmetic and the reading of row 2, and the control criterion | Applied 2026-10-26 (case file B3 amendments) | 20 GB per arm does not fit the disk; compaction confounds the line-655 term; sampling and stop conditions were missing |
| R1 | Stage 3 note: knob name `max_sstable_size_in_mb` appears in B2h/B3g; the 5.0.9 name is `sstable_size_in_mb` | left for stage 3 | naming only |

**Agreement criteria** — only if run 2 is chosen; filled before run 2 starts.
One row per observable in the case's §9d:

| Observable | Must match | Tolerance |
|---|---|---|
| `<observable>` | exactly / in shape | `<what counts as the same>` |

## 2. Environment

| Field | Run 1 | Run 2 (fresh AI session, if done) |
|---|---|---|
| Date | 2026-10-26 (local EDT; UTC 2026-10-27): unit 21:35; cluster 21:47-23:08 (attempt 1, discarded, 21:35-21:46 UTC-4); discarded shakedowns 21:19-21:33 | not done |
| Node (CloudLab name and type) | `pc07` = `node0.jason92-320876.misconfiguration-pg0.cloudlab.umass.edu` (40 cores, 251 GiB); the session ran on it directly; port slot 6 (127.0.6.1, JMX 7160) | n/a |
| OS and kernel (`uname -r`) | Ubuntu 22.04, `5.15.0-187-generic` | n/a |
| JDK (`java -version`) | openjdk 11.0.32.1 (2026-08-18) | n/a |
| Ant (`ant -version`) | Apache Ant 1.10.12 | n/a |
| Local source copy (from `cassandra/cassandra-5.0.9/` at repository commit …) | unit: `~/s4-b10-lm` (`ant build-test`); cluster: `~/s4-b10-lm2` (`ant jar`); both from `copy-source.sh`, repository commit `93d6365` (`cassandra/cassandra-5.0.9` clean), `git describe` = `cassandra-5.0.9` | n/a |
| Case-file commit / harness commit | not committed (orchestrator commits); case file sha256 `9a97d656…1f1e` (see §1); harness = files in `harness/max-threshold-getEstimatedTasks-l0SstableCount--autonomous/` | n/a |
| Storage for node data | cluster: tmpfs `/mnt/s4b10lm` (8 GiB; data, commit log, hints, saved caches; unmounted and removed after the last arm); unit: the copy's `build/test/cassandra` on local `/dev/sda3` | n/a |
| Full logs (path, outside the repo) | unit `~/s4-b10-lm-logs/unit-run1/`; cluster `~/s4-b10-lm-logs/cluster/<arm>/` (full `system.log`, `samples.jsonl`, `stress-write.txt`); discarded attempt 1 `~/s4-b10-lm-logs/cluster-attempt1-discarded/`; shakedowns `~/s4-b10-lm-logs/{unit-shake,shake}` | n/a |

## 3. Runbook defects

| # | Run | Step (§9b–§9e) | Problem | Fix | Decision (date) | Case-file commit with the fix |
|---|---|---|---|---|---|---|
| D1 | shakedown (discarded) | B3e / C2 "no compaction ran" | the executor's `completed` counter in `tpstats` rose (59 to 63) with compaction disabled: it counts empty background submissions | the check is `nodetool compactionhistory` has no `standard1` row and the sstable count equals the L0 count (C2 text edited before the freeze hash was last recomputed) | 2026-10-26 | not committed (orchestrator) |
| D2 | shakedown (discarded) | B3e / C2 "autocompaction disabled" | `nodetool statusautocompaction` prints `not running` for a disabled table, not `false` | harness check reads `not running` | 2026-10-26 | n/a |
| D3 | cluster attempt 1 (mt4, discarded) | B3f / C5 first-trigger check | pending 81, not the 79 the check expected (`floor(317/4)`); my C5 said the byte term of the estimate is 0, but an arm writes 0.9 GB, above the 640 MiB L0 target, so the byte term is 2 (`LeveledManifest.java:648-653`) | C5 rewritten: expected = `floor(L0/max_threshold)` + byte term from the same snapshot's `SSTable bytes in each level`; B3f/B3g text unchanged (B3f already said "plus the byte-based levels' term"); the cluster tier restarted from arm mt4; attempt 1's log kept in `run1/attempt1-discarded/` | 2026-10-26 | not committed (orchestrator) |
| D4 | self-check script | §5 "no compaction before phase B" | the script took the first sample labelled `B` as the boundary; compaction starts 1 s after `enableautocompaction`, before that sample, so 3 arms were flagged | the boundary is the end-of-phase-A record (`phase-A.json` `t`), which precedes `enableautocompaction`; re-run: all hold | 2026-10-26 | n/a |
| D5 | case file | B2h/B3g naming | `max_sstable_size_in_mb` and `forceBlockingFlush` do not exist in 5.0.9 | U2/U4 amendments (audit) | 2026-10-26 | not committed |

## 4. Run 1

**Scope:** unit tier (B2): `max_threshold` 4, 32, 128 in the order 4,32,128,32,4,128,32, STCS-in-L0 on and off, on 200 L0 sstables; controls U4a/U4b. Cluster tier (B3): six arms (mt4, mt32, mt128, mt32b, c64, d32), each about 300 L0 sstables / 0.93 GB, phase A (compaction held) and phase B (compaction on). **Command log:** `max-threshold-getEstimatedTasks-l0SstableCount--autonomous/run1/` (`unit/unit-run.log`, `cluster/<arm>/commands.log`, `cluster/chain.log`).

### 4.1 Readings

**Unit tier** (3 tests, 0 failures, `run1/unit/readings.txt`, `TEST-*.xml`, `analysis.txt`)

| Test or assertion | Result | Evidence (file) |
|---|---|---|
| 200 one-row flushes, compaction off | 200 live sstables, all L0; default `max_threshold` 32, `min_threshold` 4 | `readings.txt` `step2` |
| Estimate with STCS-in-L0 on | 50 at 4, 6 at 32, 1 at 128, in all 7 settings in sequence (2 readings at 4, 3 at 32, 2 at 128) | `step3 on.seq*.estimate` |
| Estimate with STCS-in-L0 off | 0 in all 7 | `step3 off.seq*.estimate` |
| Disk at the 14 readings | `sum(onDiskLength)` 27,000 B, `liveDiskSpaceUsed` 1,037,156 B, 200 `Data.db` files: identical in all 14 | `step3 *.sumOnDiskLength`, `.liveDiskSpaceUsed`, `.dataFiles` |
| Heap used after 3 GC | 51.479-51.482 MB in all readings; spread across the three values 1,348 B (on), 16 B (off); noise at 32: 0 B; 5% of the mean is 2.57 MB | `step3 *.heapUsed`, `analysis.txt` |
| Control (a): byte term at `sstable_size_in_mb` 1 vs 160 (200 L0 sstables of about 1 MiB, STCS off) | 199 vs 0 | `ctlA` |
| Control (b): 6 L0 sstables (12.7 MB) compacted once | size 1: 13 outputs, max 1,049,181 B (1.00 MiB); size 160: one output of 12,754,319 B | `ctlB` |
| Instrument: `truncateBlocking` | 0 bytes after, both tables | `ctlB *.bytesAfterTruncate` |

**Cluster tier** — each arm: 800,000 rows (4 x 256 B), 0 stress errors, 253-326 flush calls over 456 s; one table `ks.standard1`; rows are phase A end unless stated (`run1/cluster/analysis.txt`, `phase-A.json`, `phase-B.json`)

| Capacity value | Run | Observable (§9d) | Reading | Evidence (file) |
|---|---|---|---|---|
| `max_threshold` 4 | mt4 | L0 sstables; pending tasks; table bytes; RssAnon; live heap | 308; 79 (= 77 + byte term 2); 933,619,011 B; 2,928.6 MB; 78.85 MB | `mt4/phase-A.json`, `tablestats-A.txt`, `compactionstats-A.txt` |
| 32 | mt32 | same | 299; 11 (= 9 + 2); 933,588,207 B; 2,917.2 MB; 78.64 MB | `mt32/…` |
| 128 | mt128 | same | 310; 4 (= 2 + 2); 933,628,801 B; 2,943.3 MB; 78.80 MB | `mt128/…` |
| 32 repeat (noise) | mt32b | same | 321; 12 (= 10 + 2); 933,666,313 B; 2,964.4 MB; 79.07 MB | `mt32b/…` |
| 32, STCS-in-L0 off | d32 | same | 318; **2** (byte term only); 933,657,178 B; 2,929.7 MB; 79.02 MB | `d32/…` |
| 32 (control arm, 64 MiB/s in phase B) | c64 | phase A same | 248; 9 (= 7 + 2); 933,676,804 B; 2,989.6 MB; 78.14 MB | `c64/…` |
| phase B, 1 MiB/s, 180 s | mt4 / mt32 / mt128 / mt32b / d32 | L0 at the end; pending; table bytes; peak table bytes during B | L0 299 / 268 / 310 / 290 / 287; pending 77 / 11 / 5 / 12 / 3; end bytes 922.8 / 929.9 / 1,107.9 / 942.3 / 939.2 MB; peak 987.9 / 1,027.9 / 1,106.9 / 1,012.1 / 1,017.3 MB | `phase-B.json`, `samples.slim.jsonl` |
| phase B, 64 MiB/s | c64 | L0 at the end; pending; peak bytes | **1**; 0; peak 1,285.7 MB | `c64/phase-B.json` |
| Instruments | all | no compaction before phase A end; truncate | `compactionhistory` has no `standard1` row, sstable count = L0 in every arm; log has no compaction line for `standard1` before the A end record; bytes after TRUNCATE 0 in 6/6 | `compactionhistory-A.txt`, `compaction-lines.system.log`, `truncate.json` |

### 4.2 Conclusion and logic

1. **Validity** — Valid. Unit: 200 sstables all in L0, 3 tests passed **[observed: `run1/unit/readings.txt` step2, `TEST-*.xml`]**. Cluster: the limit was reached in every arm, L0 holds 248-321 sstables, above 128 (the largest `max_threshold`) **[observed: `cluster/*/tablestats-A.txt`]**; compaction was held through the write and phase A (`compactionhistory` empty for the table, sstables = L0, table bytes constant over the 12 phase-A samples) **[observed: `compactionhistory-A.txt`, `samples.slim.jsonl`, `selfcheck-out.txt`]**; each arm's `max_threshold` and JVM option were read back **[observed: `phase-A.json` `thresholds`, `commands.log`]**. Flush counts differ by arm (253-326), so L0 counts differ by up to 20%; the predictions are computed from each arm's own count.
2. **Readings** — c64 wrote 248 sstables against about 300-320 in the others (the flush loop is paced by `nodetool` start-up), so c64 is compared only through phase B's L0 ratio. An in-flight compaction in phase B makes table bytes rise by up to 54 / 94 / 172 / 352 MB (mt4 / mt32 / mt128 / c64) **[observed: `samples.slim.jsonl`]**.
3. **Matched row** — Unit B2g row 1, "Estimate changes with `max_threshold` as predicted; disk and heap are flat" **[observed: estimate 50/6/1 and identical disk, heap spread 1.3 kB of 51.5 MB; `analysis.txt`]**. Cluster B3g row 1, "Pending tasks scale as L0count / `max_threshold`; disk, heap and RSS flat across values" **[observed: pending - byte term = 77, 9, 2 for L0 308, 299, 310, exactly `floor(L0/mt)`; table bytes spread 0.004%, RssAnon 0.9%, live heap 0.27% of the mean, inside 2 x the mt32/mt32b gap + 2% (`cluster/analysis.txt`)]**.
4. **Excluded rows** — Unit "Disk or heap changes monotonically" (Refuted): disk identical, heap spread 1.3 kB, not monotone **[observed]**. Unit "Estimate does not follow 200/`max_threshold`": it follows in 14/14 readings. Unit "Estimate is 0 when STCS-in-L0 is enabled": 50/6/1, not 0. Unit "positive control did not move": it moved (199 vs 0 tasks; max output 1.0 vs 12.2 MiB). Cluster "Disk or memory scales with `max_threshold`" (Refuted): not in phase A (flat within 0.9%); in phase B the end-of-phase bytes differ by 19% (mt128) but that is the in-flight output of the real use of the knob (see 5 and §8). Cluster "Pending tasks do not change": they changed 79 to 11 to 4. Cluster "positive control does not move": c64's L0 fell to 1 against 268 and 290 **[observed: `cluster/analysis.txt`]**. d32: pending 2 = byte term only, so the L0 term disappears with the toggle **[observed: `d32/compactionstats-A.txt`]**.
5. **Observed vs. inferred** — Inferred: (i) that the 19% rise at the end of phase B in mt128 is the in-flight output of an STCS-in-L0 compaction taking up to `max_threshold` inputs (`LeveledManifest.java:328`, `:548-551`): the logs show the `Compacting` line but the arm was stopped at 180 s with a compaction unfinished, and the table directory bytes include the temporary output **[inferred: sample bytes rise from 935 to 1,107 MB while the L0 count stays at 310 in `mt128/samples.slim.jsonl`]**. (ii) That `RssAnon` and the live-heap histogram stand for "heap and off-heap" without NMT (gap named in C4). (iii) Unit heap is `totalMemory - freeMemory` after 3 GC and says little by itself; the cluster histogram is the better reading.
6. **Deviations and gaps** — The workload is 0.93 GB per arm, not 20 GB (C1). Memory is read at one moment per phase; Native Memory Tracking was not used. Phase B lasted 180 s, so it did not run a backlog to completion. The L0 count differs across arms because the flush loop is not rate-exact. No run 2.
7. **Core question** — Pending-task counts follow `L0count / max_threshold` exactly (unit 50/6/1; cluster 77/9/2 plus a constant byte term of 2), while the L0 sstable bytes, file bytes, `RssAnon` and live heap are the same across 4, 32 and 128 within 1% **[observed]**; turning the L0 term off (d32) leaves only the byte term **[observed]**, and the positive control (a binding cap: `sstable_size_in_mb` in the unit tier, compaction throughput in the cluster tier) moves the usage (output file size 1.0 vs 12.2 MiB; L0 count 1 vs about 280) **[observed]**. So the term at `LeveledManifest.java:655-659` is a counter that does not cap memory or disk use.

**Conclusion (one line):** unit B2g row 1 and cluster B3g row 1 — Confirmed: the line-655 term does not cap usage.

## 5. Self-check of run 1 — AI

### 5.1 Check of run 1's conclusion

`harness/…/selfcheck.py` re-derives the inputs from the raw files (JUnit XML, `readings.txt`, raw `tablestats-A.txt` and `compactionstats-A.txt` text with its own regexes and its own ceiling arithmetic, `stress-write.tail.txt`, `samples.jsonl`, `system.log`, `exit.txt`), not from `phase-*.json` verdicts or the analyzers. Output `run1/selfcheck-out.txt`: 67 lines HOLDS, 0 BROKEN (first run: 3 BROKEN from defect D4 in the script's phase boundary; fixed, re-run).

| Part | Holds? (yes / no) | Note (file re-read) |
|---|---|---|
| 1. Validity | yes | raw tablestats-A: L0 = sstable count in 6/6 arms (248-321 > 128); `compactionhistory` has no `standard1` row; no compaction log line before the A end record in 6/6 (`selfcheck-out.txt`); `max = 4/32/128/32/32/32` read back from `getcompactionthreshold`; stress `Total errors : 0` in 6/6. |
| 2. Readings | yes | c64's lower flush count (253) and the phase-B rise are in `commands.log`, `samples.slim.jsonl`; no reading contradicts another. |
| 3. Matched row | yes | raw compactionstats-A pending equals `floor(L0/mt)` + 2 recomputed in the check (byte term from the raw `SSTable bytes in each level` line, 915.4 MB each); unit estimates 50/6/1 and flat disk re-parsed from `readings.txt`. |
| 4. Excluded rows | yes | no row of B2g/B3g other than row 1 is satisfied by the raw numbers; the positive controls re-checked (199 vs 0; 1,049,181 vs 12,754,319 B; L0 1 vs 268/290 from `phase-B.json`). |
| 5. Observed vs. inferred | yes | the only dependent inference is the phase-B bytes explanation; it does not enter the verdict (C6). |
| 6. Deviations and gaps | yes | scale (0.93 GB), no NMT and the flush pacing are recorded in 4.2.6. |
| 7. Core question — the steps from reading to answer follow the audited logic | yes | the chain is: estimate follows `L0/mt` (counter works) -> disk/heap/RSS flat in phase A -> d32 removes the term -> positive control moves; each cited above. |

### 5.2 Run 2?

**No** (2026-10-26). The unit tier is deterministic and the cluster tier has six arms with a noise arm, a positive control and a disable arm; the self-check re-parses the raw files and holds. A run 2 would not change the answer. The one inferred statement (phase B bytes) is not part of the verdict.

## 6. Run 2 — fresh AI session (optional)

Not done (see 5.2); §7 is left out.

## 8. Verdict — AI

Jingsong may overrule any verdict at any time; record an override here with its date and reason.

**Stage-3 estimate:** negative. **Outcome class:** true negative (negative, does not cap).

**Claim tested:** B1: the L0 term at `LeveledManifest.java:655-659` does not limit memory or disk use; changing `max_threshold` changes the reported estimated task count (L0size / max_threshold) but not the heap, off-heap or disk consumed by a node holding the same L0 backlog. "Confirmed" below means this claim held.

| Tier | Verdict (§9a row; for an autonomous file, the B2g / B3g row) | Effect on the constraint | Basis | Date |
|---|---|---|---|---|
| Unit | **Confirmed** — B2g row 1: estimate follows 200 / `max_threshold` (50, 6, 1; 0 with STCS-in-L0 off), disk and heap flat, positive control moved | does not cap | run 1 + self-check | 2026-10-26 |
| Cluster | **Confirmed** — B3g row 1: pending tasks = `floor(L0/mt)` + byte term, table bytes / RssAnon / live heap flat across 4, 32, 128 in phase A (compaction held); positive control (64 MiB/s) moved the L0 backlog | does not cap | run 1 + self-check | 2026-10-26 |

**Positive control** (a negative-estimate file only): unit, `sstable_size_in_mb` 1 vs 160: the byte part of the estimate 199 vs 0 and the largest compaction output file 1.0 MiB vs 12.2 MiB; cluster, compaction throughput 64 vs 1 MiB/s: the L0 count at the end of phase B 1 vs 268-290 (`run1/cluster/analysis.txt`).

**Separate finding (C6, not part of the verdict, for Jingsong to overrule if he reads the claim more widely):** in phase B, where compaction runs, the table directory's peak bytes grew by 54 MB (`max_threshold` 4), 94 MB (32) and 172 MB (128) above the start (mt128 ends 19% above the other arms): the in-flight output of an STCS-in-L0 compaction, whose input count is bounded by `max_threshold` at `LeveledManifest.java:328` and `:548-551`. So the knob does bound a real transient resource, on a different path from line 655. Whether the case's Effect should read "caps only on some paths (bypass)" for the knob as a whole is a judgement the claim (line 655 only) does not require; the Effect field here is for line 655.

**Feedback filed:** the case file's section D "Stage-4 feedback" updated (uncommitted; the orchestrator commits), plus the dated audit amendments U1-U4 and C1-C7 in B2/B3 (incl. the C5 correction of D3).

**Leftovers on pc07 (nothing running):** no `CassandraDaemon`, `cluster-run.py`, `chain.sh` or stress process of this case; tmpfs `/mnt/s4b10lm` unmounted and removed; directories kept for the record: `~/s4-b10-lm` (unit tree), `~/s4-b10-lm2` (cluster tree), `~/s4-b10-lm-logs` (all logs). Final case-file sha256 after section D: see `sha256sum` of the file (the frozen version is in §1).
