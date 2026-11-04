# max-compacting-l0-getSTCSInL0CompactionCandidate-l0SstableCount--autonomous — stage-4 results  <!-- file: results/max-compacting-l0-getSTCSInL0CompactionCandidate-l0SstableCount--autonomous.md; the stem ends in --guided or --autonomous -->

> **Case:** [`max-compacting-l0-getSTCSInL0CompactionCandidate-l0SstableCount--autonomous`](../../stage3-ai-deep-read/cases/max-compacting-l0-getSTCSInL0CompactionCandidate-l0SstableCount--autonomous.md)
>
> **Status:** **Closed 2026-10-26 — unit Confirmed, cluster Confirmed — does not cap** (estimate negative, matched); run 1 only, self-checked; no run 2
>
> **Outcome class:** true negative — stage-3 estimate (negative) vs the stage-4 effect on the constraint (does not cap)
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
| **Case-file version** | **Autonomous file:** sha256 of the whole file after the audit amendments A1-A5: `5f0cc41cce7ebf4e5dac7c5137a19206c20edd7ce0caea55711b6a04f7889376` (2026-10-26 20:43 EDT, before any harness code or run; no reading existed); not committed yet (the orchestrator commits). **Frozen prediction and conclusion tables** (B2f, B2g, B3f, B3g, text from `**B2f.` up to `**B2h.` plus `**B3f.` up to `**B3h.`, kept in `harness/max-compacting-l0-getSTCSInL0CompactionCandidate-l0SstableCount--autonomous/frozen-B2f-B2g-B3f-B3g.txt`): sha256 `331941cface76368bc24d666674471bc1d444bee845cecf370ac5bb5a9efb86c`. Later changes to the file are limited to section D (feedback) and dated runbook-defect fixes that leave those four blocks unchanged. 
| **Harness** | `harness/max-compacting-l0-getSTCSInL0CompactionCandidate-l0SstableCount--autonomous/` (README lists the files); not committed yet (the orchestrator commits). Written after the freeze; the four frozen blocks were not touched afterwards. |
| **Tiers and values** | Unit (B2): routes R0/R1/R2 x N {31,32,33,64,200} x flag {false,true} x `max_threshold` {32,8}, 200-flush no-rejection arm, L1 positive control. Cluster (B3): labels A (throttle 1 MiB/s), B (autocompaction off), C (A + `-Dcassandra.disable_stcs_in_l0=true`), D (unthrottled, 4 compactors; positive control); 1.5 M rows each. The constant itself is a literal and is not varied. |
| **Audit bottom line** | **Ready after amendments** — 2026-10-26 |

### 1.1 Design audit

The requirements are in the README, "Step 0 — the design audit". One row per
line of each group; cite the case-file section checked.

| Group | Check | Rating (Met / Partly / Not met) | Note (section checked) |
|---|---|---|---|
| A. Core question | constrained quantity is memory or disk bytes | Partly | A2/B1: the compared quantity is the L0 sstable COUNT (`LeveledManifest.java:306`); disk bytes follow (each sstable ~10 MB in B3c, derivable). B3d measures file bytes, fds and RssAnon. Count with a derivable byte size: accepted. |
| A. Core question | knob varied, ≥ 3 values incl. default — or another approach, with the reason | Met | A1: the constant is a literal (`:62`), not settable. B2b varies N (31..200), the flag, `max_threshold`; B3b varies compaction speed (1 MiB/s, off, unthrottled) and the flag. Two arms differing in one condition answer the same question. A build with the constant changed is left for stage 3. |
| A. Core question | real resource measured, not only the counter (gap named) | Met | B3d: bytes of the table directory, live bytes, fds, RssAnon next to the L0 count; B2 observes only candidates and says real disk is the cluster tier's job. |
| A. Core question | usage driven to the limit and past it | Met | B2c: N up to 200 (6x). B3c after A4: ~150 flushes (A, B, C), 4-5x the constant; arithmetic made consistent (1.56 GB, 300 s). |
| B. Logic | each step says what it establishes | Met | B2e/B3e steps name the reading; A2/A3 add the missing route and drain steps. |
| B. Logic | prediction stated in numbers or a clear relation | Not met -> Met after A1, A5 | Original B2f predicted STCS for every N > 32 (contradicted by `:270-271`, `:296-299`); original B3f had "single digits to tens" and "STCS log lines" without a definition. Now route-wise exact values and numeric thresholds. |
| B. Logic | every plausible outcome has a conclusions row with its evidence | Partly -> Met | Original B2g/B3g lacked: branch evidence missing, flag-true candidate, control fails, no matching row. Added (A1, A5). |
| B. Logic | confirmation needs ceiling-follows-knob and direct disallow evidence | Partly -> Met | For a negative claim the "branch" evidence is: the check TRUE (debug line in A, none in C; STCS candidate at N=33 and not at 32 in R1/R2). Both are now required for Confirmed. |
| B. Logic | alternative explanations and their controls (positive control for a negative file) | Met after A1, A5 | B2h: L1 at 3x target with the flag true, executed down to target; B3: D (unthrottled) and the L1+ settle check; truncate control. Closed related case `lcs-maxBytesForLevel` already showed caps bind at L1+. |
| C. Specific | a human can follow it from the intro and B2f/B3f | Met | A3 explains the routes (A3 step 6 already named the empty-candidate route, B2f did not use it). |
| C. Specific | an AI can run B2/B3 without re-deriving the code path | Partly -> Met | B2c did not say how to build an L1 or a held sstable; A2 does. B3c used a table stress cannot fill; A4. |
| C. Specific | knob, values, workload, commands, observables, sampling, stop conditions exact | Partly -> Met | A2-A5 give values, sampler periods, drain stop condition, ports; `tablestats` prints `150/4` for L0 over its nominal size (parsed accordingly). |
| D. Runnable | harness and environment prerequisites exist or are listed | Met | Harness is step-1 work; pc12 has JDK 11, Ant, Python 3; sibling harness `lcs-maxBytesForLevel` is the template for the runner. |
| D. Runnable | workload arithmetic reaches the limit (data, time, disk, memory) | Partly -> Met | Original: 20 GB vs 3 GB vs 5 GB cap. After A4: 1.56 GB per run on a 12 GiB tmpfs; pc12 has 251 GiB RAM and 35 GB free on `/`. |
| D. Runnable | load-bearing citations spot-checked against the pinned source | Met | Re-read in `cassandra-5.0.9`: `LeveledManifest.java:62,243,270-271,296-299,304-317,319-329,495-573,667-688`, `getEstimatedTasks` max_threshold use, `SizeTieredCompactionStrategy.mostInterestingBucket:116`, `CassandraRelevantProperties:197`, `DatabaseDescriptor:223,2589-2596`, `CompactionManager:2353-2357`, `CompactionParams:79-80`. Lines match; the A3 sentence on "ahead of them" is imprecise (left for stage 3). |

| # | Recommendation | Applied? (amendment date and commit, or "left for stage 3") | Why |
|---|---|---|---|
| A1 | B2f/B2g/B2h made route-aware (R0/R1/R2) | Applied 2026-10-26 (case file, section D) | the STCS candidate is returned only when a level 1-7 is over score or `getCandidatesFor(0)` is empty |
| A2 | B2 construction details (L1 sstables, held sstable, tables per max_threshold, execute on a fresh arm) | Applied 2026-10-26 | AI could not run B2c as written |
| A3 | B3 environment: slot-4 loopback node, tmpfs, labels, drain and truncate steps | Applied 2026-10-26 | safety rules and a positive control |
| A4 | B3c workload arithmetic | Applied 2026-10-26 | 20 GB vs 3 GB vs 5 GB cap; `ks.t` not writable by stress; flush cadence |
| A5 | B3f/B3g numbers, definitions, missing rows, meaning of the debug line | Applied 2026-10-26 | predictions must be checkable |
| A6 | A dose-response on the constant (patched build, values 8/32/128) | left for stage 3 | stronger than two arms, not needed to answer the question |
| A7 | A3 step 6 wording ("returned ahead of them") | left for stage 3 | no effect on the run |

**Audit bottom line: Ready after amendments** (2026-10-26). The audit examined the proposal, not the three rules; no finding that the claim itself is unsound.

**Agreement criteria** — only if run 2 is chosen; filled before run 2 starts.
One row per observable in the case's §9d:

| Observable | Must match | Tolerance |
|---|---|---|
| `<observable>` | exactly / in shape | `<what counts as the same>` |

## 2. Environment

| Field | Run 1 | Run 2 (fresh AI session, if done) |
|---|---|---|
| Date | 2026-10-26 (unit 18:51-18:53 MDT; cluster 18:59-19:27 MDT approx.; UTC logs 2026-10-27 00:5x-01:2x) | not done |
| Node (CloudLab name and type) | pc12 (`node1.jason92-320876`, 198.22.255.22), 40 cores, 251 GiB; shared with other batch-10 cases; slot 4 | |
| OS and kernel (`uname -r`) | Ubuntu 22.04, 5.15.0-187-generic | |
| JDK (`java -version`) | OpenJDK 11.0.32.1 | |
| Ant (`ant -version`) | Apache Ant 1.10.12 | |
| Local source copy (from `cassandra/cassandra-5.0.9/` at repository commit …) | two `copy-source.sh` trees from base commit `93d6365` (`~/s4-b10-lz-unit` for the unit tier, `~/s4-b10-lz-node` for the node), both `ant build-test`; deleted after the runs | |
| Case-file commit / harness commit | not committed (orchestrator commits); case-file sha256 in section 1 | |
| Storage for node data | 12 GiB tmpfs `/mnt/s4lz` (unmounted afterwards); unit tier under the tree's `build/test/cassandra` on local disk | |
| Full logs (path, outside the repo) | `pc12:~/s4-b10-lz-logs/` (`unit1/`, `cluster1/{A,B,C,D}/` with `logs/debug.log`, `node.out`, `conf/`); the failed first attempt of the cluster chain is in `cluster1-failed-start/` (defect H2) | |

## 3. Runbook defects

| # | Run | Step (§9b–§9e) | Problem | Fix | Decision (date) | Case-file commit with the fix |
|---|---|---|---|---|---|---|
| H1 | shakedown | harness `cluster-run.py` start check | `nodetool statusbinary` prints `not running`, which contains `running`: the script went on to `cqlsh` before the CQL port was open | compare the whole word (`['1','running']`) | harness fix 2026-10-26; no case-file change | n/a (harness) |
| H2 | cluster attempt 0 (no reading) | harness start check | an extra "no pid file after 60 s" check fired on a slow start (the `-f` foreground start does not write the pid file in time); the chain then went on and started the next labels with the first node still alive | pid check removed (death is detected through the process list); chain stops at the first failed label; stray daemon killed by PID; the four failed attempts produced no data (`cluster1-failed-start/`) | 2026-10-26 | n/a (harness) |
| H3 | unit analysis | `unit-analyze.py`, `selfcheck.py` | Java prints booleans in lower case; the scripts compared with `True`/`False` and reported 7 groups FAIL on correct readings | compare lower case; no reading or prediction changed | 2026-10-26 | n/a (harness) |
| H4 | cluster analysis | `cluster-analyze.py`, `selfcheck.py` B check | the B check demanded the L0 count within 3 of the `nodetool flush` calls (216); 5 calls found nothing dirty and made no sstable. The frozen B3f says "L0 count equals the number of flushes (at least 100)". Now: L0 count = Data.db files on disk (211 = 211) and at most the flush calls | harness criterion corrected, not B3f | 2026-10-26 | n/a (harness) |

No B2/B3 step failed as written; no case-file runbook change after the freeze.

## 4. Run 1

**Scope:** unit tier (routes R0/R1/R2 x tables mt32/mt8 x N {31,32,33,64,200} x flag, 3 reps; execute step; positive control) and cluster tier (labels A, B, C, D, 1.5 M rows each). **Command log:** `max-compacting-l0-getSTCSInL0CompactionCandidate-l0SstableCount--autonomous/run1/` (`unit/`, `cluster/<label>/commands.log`).

### 4.1 Readings

**Unit tier** (`max-compacting-l0-getSTCSInL0CompactionCandidate-l0SstableCount--autonomous/run1/unit/readings.txt`, 1851 lines; `analyze.txt`: ALL PREDICTIONS PASS)

| Test or assertion | Result | Evidence (file) |
|---|---|---|
| R0 (L0 only, nothing held): candidate at every N and flag | normal candidate, `stcs=false`, `maxSSTableBytes` 1,048,576, size at most max_threshold; L0 count N unchanged by the read | `unit/readings.txt` keys `R0.mt*.rep*.N*.flag*` |
| R1 (L1 at 3.04x target), flag false, N 31 and 32 | normal L1 to L2 candidate (`level=2`, input levels 1..1) | `R1.mt*.rep*.N31/N32.flagfalse.*` |
| R1, flag false, N 33, 64, 200 | STCS candidate (`level=0`, `maxSSTableBytes=Long.MAX_VALUE`), size 32 (mt32) and 8 (mt8), input levels 0..0 | `R1.mt32/mt8.rep*.N33..N200.flagfalse.*` |
| R1, flag true | normal L1 to L2 candidate at every N | `R1.*.flagtrue.*` |
| R2 (one L0 sstable held), flag false | N 31, 32: null; N 33, 64, 200: STCS candidate of 32 (8), the held sstable not in it | `R2.*.flagfalse.*`, `containsHeld=false` |
| R2, flag true | null at every N | `R2.*.flagtrue.*` |
| 200 L0 sstables on R0 | built, no exception, no rejection (`error none`, `N200.l0sstables 200`) | `R0.*.N200.*` |
| Execute step (fresh R1 arm, N 33 and 64) | one `LeveledCompactionTask`; L0 count N to N-31 (mt32) / N-7 (mt8) | `exec.*` (12 arms) |
| Positive control (R1, flag true, N 32) | L1 31.86 MB (3.04x of 10.49 MB) to 9.56 MB in 21 tasks, L2 22.3 MB; truncate gives 0 | `ctl.rep1..3` |
| Instrument checks | all L0 sstables mutually overlap (every N); 30 L1 sstables; held count 1; JUnit errors 0, failures 0 | `setup` keys, `unit/junit-header.txt` |

The 60 (route, table, N, flag) cells gave identical candidates in all 3 reps.

**Cluster tier** (`max-compacting-l0-getSTCSInL0CompactionCandidate-l0SstableCount--autonomous/run1/cluster/`; `analyze.txt`: ALL PASS; peak L0 is the largest L0 count in the 20-s `tablestats` samples and the lag-end snapshot)

| Capacity value | Run (control / A / B / C) | Observable (§9d) | Reading | Evidence (file) |
|---|---|---|---|---|
| compaction 1 MiB/s, 1 compactor, flag false | A | peak L0 / lag-end L0 per level / live / file bytes | 211 / [211, 5, 0...] / 1555 MiB / 1772 MiB (1.5 M rows x ~1050 B = 1502 MiB); 217 flush calls | `A/snapshot-lag-end.json`, `A/tablestats-lag-end.txt`, `A/l0-series.csv` |
| same | A | debug line "L0 is too far behind" | 7 (first 00:57:24 UTC during the write, 6 at 01:01:44-56 during the boosted drain) | `A/stcs-lines.txt` |
| same | A | after the drain | L0 0; L1 104.9 MB (nominal 104.9), L2 1040 MB (1048.6), L3 409 MB (top); live 1509 MiB | `A/tablestats-settled-write.txt`, `A/drain-write.json` |
| autocompaction off | B | L0 count at lag-end / Data.db files / live | 211 / 211 / 1557 MiB; 216 flush calls; 0 debug lines | `B/snapshot-lag-end.json`, `B/stcs-lines.txt` |
| compaction 1 MiB/s, flag true (`-Dcassandra.disable_stcs_in_l0=true`) | C | peak L0 / live / file bytes / debug lines | 209 / 1554 MiB / 1770 MiB / 0 | `C/jvm-args.txt`, `C/snapshot-lag-end.json`, `C/stcs-lines.txt` |
| C after the drain | C | per-level bytes | L0 0; L1 95.2 MB, L2 1039 MB, L3 419 MB | `C/tablestats-settled-write.txt` |
| compaction 0 (unthrottled), 4 compactors | D (control) | peak L0 / lag-end per level / debug lines | 2 / [0, 10, 109, 42] / 0 | `D/snapshot-lag-end.json`, `D/l0-series.csv` |
| D after the drain | D | per-level bytes | L1 97.0 MB, L2 1048 MB, L3 409 MB; live 1509 MiB | `D/tablestats-settled-write.txt` |
| all | A-D | stress; truncate control; resources | 0 errors, 1,500,000 partitions at 5000 op/s for 300 s; file bytes after TRUNCATE 0; max fds 1063-1182, max RssAnon 2.78-2.82 GiB (heap 2G) | `*/stress-write-tail.txt`, `*/snapshot-truncated.json`, `*/samples.jsonl` |

### 4.2 Conclusion and logic

1. **Validity.** The limit was reached: peak L0 is 211, 211 and 209 in A, B, C (6.5x the constant) [observed: `cluster/A,B,C/tablestats-lag-end.txt`]; the unit tier built 200 L0 sstables [observed: `unit/readings.txt`, `R0.*.N200.l0sstables 200`]. Hold-fixed settings: compaction throughput and compactors in the yaml and live (`*/yaml-changed.txt`, `*/settings-live.txt`), flag only in C (`C/jvm-args.txt`), same 1.5 M rows at 5000/s in all four [observed]. The routes were verified: 30 L1 sstables at 3.04x target, one held sstable, L0 sstables overlapping [observed: setup keys]. Valid.
2. **Readings.** Flush calls (205-217) exceed the sstables made in B (216 vs 211): 5 calls found nothing dirty [inferred: B has no compaction and 211 Data.db files]. File bytes exceed live bytes by 14% in A and C at lag-end (compaction temporary outputs in flight) [inferred]. Nothing contradicts.
3. **Matched rows.** Unit B2g row 1: "R1 and R2 match B2f (boundary exactly between N=32 and N=33, candidate size `max_threshold`), R0 never returns an STCS candidate, flag true removes it, 200 L0 sstables exist with no rejection, and the positive control brings L1 to target" [observed: all five parts, `unit/analyze.txt`]. Cluster B3g row 1: "A, B and C peak L0 at least 100 ... disk tracks the bytes written, at least one debug line in A and none in C, D peak L0 below half of A's, and the L1+ levels settle at or below 1.05 x nominal in A, C and D" [observed: 211/211/209; file bytes within 15% of live (A 1772 vs 1555 MiB = 14%) and live within 4% of 1502 MiB; 7 vs 0 lines; D 2 < 105.5; below-top ratios at most 1.0].
4. **Excluded rows.** Refuted rows: L0 at 40 or below in B (B is 211) and a refused write (0 errors, `error none`) are ruled out. Not-confirmed rows: limit never reached (211 > 32), no STCS candidate at N >= 33 in R1/R2 (present), STCS at N <= 32 or on R0 (absent), flag-true candidate or debug line (none), candidate size not following max_threshold (32 vs 8 followed), control failing (D and the L1 control moved; truncate 0) all ruled out by the readings in 4.1.
5. **Observed vs. inferred.** Inferred: that the debug line marks the check being true, not the candidate being chosen (from `LeveledManifest.java:304-317`); that the 5 unproductive flush calls explain 216 vs 211; that the 14% file-vs-live gap is compaction output in flight. None changes the matched row.
6. **Deviations and gaps.** Sampling of L0 is every 20 s, so the exact moment the count passes 32 is not resolved (the 5-s Data.db count was 40 one second before the first debug line). In the cluster run STCS fired on only 1 of its 7 logged evaluations during the write (one compactor, so a new candidate is requested only when a task ends); whether the STCS candidate was then chosen is not read from a log (the unit tier shows the routes on which it is). The 211 sstables are 10 MB each (about 2.1 GB file bytes), not "hundreds of MB"; memory (heap) was not measured because the claim is about L0 count and disk. The constant itself was not varied (a literal); the design compares arms. A, B, C used throttled compaction only; D is the only unthrottled arm. Harness defects H1-H4 (section 3).
7. **Core question.** The constant 32 is not a cap on L0: with compaction slower than flush, L0 reached 211 sstables (6.5x the constant) and file bytes tracked the 1.5 GB written, with the flag on or off and with compaction off [observed: A, B, C]. What 32 does is make `getSTCSInL0CompactionCandidate()` return an STCS candidate of at most `max_threshold` sstables (debug line in A, none with the flag true; candidate appears exactly from N=33 and has `max_threshold` members), and that candidate is used only when a level 1-7 is over its score or the normal L0 candidate is empty [observed: unit R1/R2 vs R0]. Real caps bind at L1+ (levels settle at or below nominal after the drain in A, C, D; unit control L1 3.04x to 0.91x of target) and compaction speed moves L0 (D peak 2) [observed].

**Conclusion (one line):** Unit B2g row 1 and cluster B3g row 1 — confirmed (the constant does not cap L0 usage).

## 5. Self-check of run 1 — AI

### 5.1 Check of run 1's conclusion

`harness/max-compacting-l0-getSTCSInL0CompactionCandidate-l0SstableCount--autonomous/selfcheck.py` re-parsed the raw files (console echo in `ant.log`, JUnit XML, raw `tablestats` text, `stress-write.txt`, `flushes.log`, `debug.log`, `cassandra.yaml`, `jvm-args.txt`, `exit.txt`) with code separate from the analyzers: output `run1/cluster/selfcheck.txt`, last line "SELF-CHECK: ALL HOLD" (after the corrections H3, H4; its first run showed the H3/H4 harness defects, no reading differed).

| Part | Holds? (yes / no) | Note (file re-read) |
|---|---|---|
| 1. Validity | yes | peak L0 211/211/209 re-derived from raw tablestats text; flags in `jvm-args.txt`; yaml throughput; all daemons stopped (`exit.txt`) |
| 2. Readings | yes | B: 211 L0 = 211 Data.db; file vs live bytes within 15% |
| 3. Matched row | yes | candidate table recomputed from the console echo: same 60 cells, STCS exactly from N=33 on R1/R2, never on R0, never with flag true; 12 execute arms; control 3.04x to 0.91x |
| 4. Excluded rows | yes | no refused write, B well above 40, debug lines 7/0/0, D 2 |
| 5. Observed vs. inferred | yes | the first debug line follows a 5-s sample with 40 Data.db files (more than 32) |
| 6. Deviations and gaps | yes | listed in 4.2 part 6 |
| 7. Core question — the steps from reading to answer follow the audited logic | yes | steps: constant not varied, arms differ in one condition; L0 count and bytes measured; branch evidence; control |

### 5.2 Run 2?

**No** (2026-10-26). The conclusion rests on observed counts, not on inferred statements; the unit tier is deterministic (60 cells, 3 reps identical) and the cluster tier has four labels with a positive control; the result confirms the filed estimate rather than refuting it. A run 2 would cost about 30 minutes and add nothing a rerun of the same script would not.

## 6. Run 2 — fresh AI session (optional)

Not done.

## 8. Verdict — AI

Jingsong may overrule any verdict at any time; record an override here with its date and reason.

**Stage-3 estimate:** negative. **Outcome class:** true negative (negative, does not cap).

**Claim tested:** (B1) The number and total bytes of L0 sstables are not bounded by `MAX_COMPACTING_L0 = 32`: when flush rate exceeds compaction rate, L0 count rises well above 32, and the only effect of 32 is to trigger STCS compactions of at most `max_threshold` sstables. "Confirmed" below means this claim held.

| Tier | Verdict (§9a row; for an autonomous file, the B2g / B3g row) | Effect on the constraint | Basis | Date |
|---|---|---|---|---|
| Unit | **Confirmed** — B2g row 1 (as amended A1) | does not cap | run 1 + self-check | 2026-10-26 |
| Cluster | **Confirmed** — B3g row 1 (as amended A5) | does not cap | run 1 + self-check | 2026-10-26 |

**Positive control:** D (compaction unthrottled, 4 compactors) with the same workload and instruments: peak L0 2 against 211 in A, and in A, C, D the levels below the top settle at 0.91-1.0 x nominal after the drain; unit tier: L1 at 3.04x target returned to 0.91x by executing L1 to L2 candidates.

**Feedback filed:** the case file's section D updated (audit amendments A1-A5 already filed; stage-4 feedback with the result below); no section is refuted. Candidates for stage 3: A3 step 6 wording; the B3d wording "marks STCS firing" (corrected by A5); the constant is inlined, so a variable-constant arm needs a patched build (A6).
