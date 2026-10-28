# max_space_usable_for_compactions_in_percentage-applysimpleconfig-range--autonomous — stage-4 results  <!-- file: results/max_space_usable_for_compactions_in_percentage-applysimpleconfig-range--autonomous.md -->

> **Case:** [`max_space_usable_for_compactions_in_percentage-applysimpleconfig-range--autonomous`](../../stage3-ai-deep-read/cases/max_space_usable_for_compactions_in_percentage-applysimpleconfig-range--autonomous.md)
>
> **Status:** verdict filed (2026-10-27) — unit **Confirmed — does not cap**, cluster **Confirmed — does not cap**; run 1 + self-check, no run 2
>
> **Outcome class:** true negative (estimate `negative`; effect `does not cap`)
>
> **Agent:** autonomous. "§9a" below means each tier's predictions and conclusions table: B2f and B2g (unit), B3f and B3g (cluster); "§9b–§9e" means B2a–B2e or B3a–B3e; the case file's feedback section is its section D.

## 1. Before run 1 — design audit and freeze

| Field | Content |
|---|---|
| **Case-file version** | Repository HEAD `6e6cf92` (the case file is committed there without the amendments; the amendments are uncommitted). sha256 of the whole file after the audit's amendments U1–U6, C1–C6, C2a: `f4ddda282549c6ffb42ab8e4d0a0793e9d86323ad00daaad61d3ebc41c32c90e` (frozen 2026-10-27, before any cluster reading; copy `run1/case-frozen-2.md`). The unit tier ran under the version before C2a, `e91dabc4471331ddc373dc30a9408a77c6396ed616f36330e6dc70ca3f1b211e` (frozen 2026-10-27 02:18 UTC); C2a does not touch B2, so the unit text is byte-identical. Section D changes after the run and is outside the freeze. |
| **Harness** | `harness/max_space_usable_for_compactions_in_percentage-applysimpleconfig-range--autonomous/`: `MaxSpaceRangeProbe.java`, `unit-run.sh`, `cluster-run.py`, `selfcheck.py` (untracked; the orchestrator commits). The positive control reuses `harness/max_space_usable_for_compactions_in_percentage-hasDiskSpaceForCompactionsAndStreams-availableForCompaction--autonomous/MaxCompactionSpaceOperandTest.java` unchanged. |
| **Tiers and values** | Unit (B2): yaml value −0.01 · 0 · 0.5 · 0.95 · 1 · 1.01 · (no entry), each in a fresh JVM, twice; setter 1.5 and −0.25; closed control `MaxCompactionSpaceOperandTest` (pct 1.0 / 0.95 / 0.5 / 0.0 at usable 1e9 and 1e7). Cluster (B3): one node, 2 GiB ext4 data filesystem, `min_free_space_per_drive 50MiB`, four sstables of 165 MiB, `max_space_usable_for_compactions_in_percentage` 0.95 (default) · 0.10 · 1.0, and 1.5 as a startup test. |
| **Audit bottom line** | **Ready after amendments** — 2026-10-27 |

### 1.1 Design audit

| Group | Check | Rating | Note (section checked) |
|---|---|---|---|
| A. Core question | constrained quantity is memory or disk bytes | Partly | A2/B1: the check bounds the option's range; the option is a fraction of free disk applied downstream (`Directories.java:563-569`). Accepted as disk bytes through the budget; the check itself holds nothing (named). |
| A. Core question | knob varied, ≥ 3 values incl. default | Met | B2b six values (default via no entry added, U2); B3b 0.95 · 0.10 · 1.0 and 1.5. |
| A. Core question | real resource measured, not only the counter (gap named) | Partly → Met | B2d said heap and disk "cannot be observed"; U3 adds heap used after GC and FileStore usable space before/after; B3d samples real filesystem bytes (`statvfs`, every 0.5 s) and heap (`jcmd`). |
| A. Core question | usage driven to the limit and past it | Partly → Met | B3c's "about 600 MiB" was loose and the 0.10 case needs every single sstable above the budget; C2 gives four sstables ≥ 160 MiB (measured 165 MiB each) against budgets of 122 MB (0.10) and 1.16 GB (0.95). |
| A. Core question | positive control (negative file) | Partly → Met | B2g/B3g name one, but B2 had no concrete instrument; U1 reuses the closed Confirmed case for the same knob (its unit test unchanged); B3 uses 0.10 vs 0.95/1.0 on the same data (B3g row 2, C5). |
| B. Logic | each step says what it establishes | Met | B2e/B3e. |
| B. Logic | prediction stated in numbers or a clear relation | Partly → Met | B3f's "refused with the warning, disk flat" and "2x" lacked thresholds and the sstable layout that makes "refused" true (the reduce-scope loop, `CompactionTask.java:395-440`, drops sstables first): C4. |
| B. Logic | every plausible outcome has a conclusions row | Partly → Met | Added: check-not-as-read rows (U5, C5), a row for the 0.95/1.0 arms failing on arithmetic (C5), a row for a usage figure depending on the value (U5). |
| B. Logic | confirmation needs ceiling-follows-knob and direct disallow evidence | Met | for a negative claim: the rejection message at 1.5 / 1.01 and the control that moves. |
| B. Logic | alternative explanations and controls | Met | B2h/B3h; drift read twice. |
| C. Specific | a human can follow it from the intro and §9a | Met | A1–A3, B1. |
| C. Specific | an AI can run it without re-deriving the code path | Partly → Met | "fresh JVM or reset", the test form, the loop device, the stress table and chunk sizes: U1–U3, C1–C3. |
| C. Specific | knob, values, workload, commands, observables exact | Partly → Met | filled by U2–U4, C2–C4. |
| D. Runnable | harness and prerequisites exist or are listed | Met | JDK 11, Ant, built clones on `pc32`; probe, scripts are step-1 work. |
| D. Runnable | workload arithmetic reaches the limit | Partly → Met | see A (driven past the limit); the filesystem is 2.04 GB, the table 0.69 GB, free space 1.27 GB. |
| D. Runnable | citations spot-checked against the pinned source | Met | `DatabaseDescriptor.java:1016-1017`, `:2579-2587`; `Config.java:344`; `Directories.java:545-569`; `CompactionTask.java:395-446`: all as cited. |

| # | Recommendation | Applied? | Why |
|---|---|---|---|
| U1–U6 | unit tier concretised: probe program per yaml value, positive control = closed unit test, usage figures, extra prediction details, extra rows, verdict wording | applied 2026-10-27 (case file, next to B2a–B2h) | runnable, contradictable |
| C1–C6 | cluster tier concretised: ext4 loop with sudo, four sstables ≥ 160 MiB, restore per setting, numbers for the prediction, extra rows, verdict wording | applied 2026-10-27 (next to B3a–B3h) | the 0.10 refusal needs every sstable above the budget |
| C2a | seed node with big memtable pools | applied 2026-10-27 after runbook defect D1 | the first seed gave 20 sstables |
| left | A5's remark "No docs under `doc/` mention the option" and A4's wording | left for stage 3 | no effect on the run |

**Agreement criteria** — run 2 not chosen (see 5.2).

## 2. Environment

| Field | Run 1 |
|---|---|
| Date | 2026-10-27 (node clock MDT; unit 20:18 MDT, cluster chain 20:24–20:31 MDT) |
| Node | `pc32` (`node2.jason92-321705.misconfiguration-pg0.cloudlab.umass.edu`), 40 cores, 251 GiB |
| OS and kernel | Ubuntu 22.04, `5.15.0-198-generic` |
| JDK | openjdk 11.0.32.1 2026-08-18 |
| Ant | Apache Ant 1.10.12 |
| Local source copy | unit: `~/cassandra-run4` (`copy-source.sh` from repository commit `6e6cf92`, `git describe`: `cassandra-5.0.9`, `ant build-test`); cluster: `~/cassandra-run1` (the built, unmodified 5.0.9 copy) |
| Case-file commit / harness commit | `6e6cf92` plus the uncommitted amendments (sha256 in section 1) / harness untracked |
| Storage for node data | cluster: a 2 GiB ext4 image (`mkfs.ext4 -m 0`, loop device mounted with `sudo`) in `~/s4b-mu/fs.img` on local `/dev/sda3`, fresh for every label; commit log, hints, logs on local `/`; never under `/proj`. The seed data copy (750 MB) was removed after the run |
| Full logs | `pc32:~/s4b-logs/msu/` (`unit/`, `cluster/<label>/{summary.txt,session.log,samples-*.csv,result-*.json,budget-lines-*.txt}`, `chain.out`, `case-frozen*.md`); first (discarded) cluster attempt in `cluster-attempt1/`; the instrument-check run of the probe in `unit-shake1/` |

## 3. Runbook defects

| # | Run | Step | Problem | Fix | Decision | Case-file commit |
|---|---|---|---|---|---|---|
| D1 | cluster attempt 1 (seed; no reading) | B3c | At the 2 GiB heap a memtable flushed about every 38 MB of Data.db, so a 760,000-row chunk gave several small sstables (20 in all, 16 to 39 MB) instead of one; the "four sstables ≥ 160 MiB" check failed and the tier stopped | The seed node runs with `MAX_HEAP_SIZE=12G` and 6144 MiB memtable pools (C2a); measured nodes keep 2 GiB. The tier restarted from `invalid` | 2026-10-27 | untracked |
| H1 | harness only | chain script | The first chain script expanded its loop variable when written (unquoted heredoc) and ran nothing | rewritten with a quoted heredoc | 2026-10-27 | n/a |
| N1 | unit instrument check (before the freeze) | probe | The probe was first executed once as an instrument check (compile, one JVM per value); its outputs were of the same kind the formal run gave. The formal unit run was repeated after the freeze and is the one read here; the check's directory is `unit-shake1/` | none | 2026-10-27 | n/a |

## 4. Run 1

**Scope:** all unit values (twice) and the closed control; cluster 1.5 (startup), 0.95, 0.10, 1.0, once each. **Command log:** `max_space_usable_for_compactions_in_percentage-applysimpleconfig-range--autonomous/run1/` (`unit-summary.txt`, `unit-probe-lines.txt`, `readings-control.txt`, `cluster-*-summary.txt`, `result-*.json`, `budget-lines-*.txt`, `samples-*.csv`, `compactionhistory-*.txt`, `selfcheck.txt`).

### 4.1 Readings

**Unit tier**

| Test or assertion | Result | Evidence (file) |
|---|---|---|
| Probe, yaml −0.01 and 1.01 (both repetitions) | `result=REJECT`, `ConfigurationException`, message `max_space_usable_for_compactions_in_percentage must be between 0 and 1` | `unit-probe-lines.txt` |
| Probe, yaml 0 · 0.5 · 0.95 · 1 · no entry (both repetitions) | `result=ACCEPT`; getter 0.0 · 0.5 · 0.95 · 1.0 · 0.95 | `unit-probe-lines.txt` |
| Budget of the real `Directories.getAvailableSpaceForCompactions` on the data FileStore | = `round((usable − 52,428,800) × v)` exactly, e.g. v = 0.95: 53,617,366,221; v = 1: 56,439,296,000; v = 0.5: 28,219,559,936; v = 0: 0; usable drift between the two reads 0 B | `unit-probe-lines.txt`, `selfcheck.txt` |
| Real gate at budget − 1 / budget + 1 | true / false for every accepted value (v = 0: budget 0, request 0 admitted) | `unit-probe-lines.txt` |
| Usage figures: heap used after init + GC | 14,892,376 to 14,912,688 B across all accepted values (spread 20 kB; 1.3 MB before init, 14.2 MB after a rejected init) | `unit-probe-lines.txt`, `selfcheck.txt` |
| Setter bypass (no range check) | 1.5 accepted, getter 1.5, budget 84,658,993,152 B = 1.5 × (usable − minFree), above the usable 56.49 GB; −0.25 accepted, budget 0 (`Math.max(0, …)`) | `unit-probe-lines.txt` |
| Positive control: closed `MaxCompactionSpaceOperandTest` re-run | 1 test, 0 failures; 56 `READING OK`, 0 `MISMATCH`; budget 1e9 → 1e9 / 9.5e8 / 5e8 / 0 for pct 1.0 / 0.95 / 0.5 / 0.0 and scaled at usable 1e7 | `readings-control.txt`, `unit-ant-tests.txt` |
| Known answer: upstream `DirectoriesTest` | 42 tests, 0 failures | `unit-ant-tests.txt` |
| `selfcheck.py` on the unit files | all PASS | `selfcheck.txt` |

**Cluster tier**

| Capacity value | Run | Observable | Reading | Evidence (file) |
|---|---|---|---|---|
| 1.5 | startup | node start | refused in 3 s with `Exception (…ConfigurationException) encountered during startup: max_space_usable_for_compactions_in_percentage must be between 0 and 1`; no daemon left | `cluster-invalid-summary.txt` |
| — | seed | sstables | 4 Data.db of 173,028,400 · 173,045,995 · 173,048,925 · 174,040,214 B (each ≥ 160 MiB), sum 693,163,534 B | `cluster-seed-summary.txt`, `result-0.95.json` |
| all three | at rest, before any compaction | filesystem used / avail; `du -sb` of the data dir; heap used after `GC.run` | used 751,013,888 B and avail 1,272,582,144 B in all three; du 749,682,566 · …567 · …565 B; heap 74,618,880 · 74,625,024 · 74,624,000 B | `result-*.json`, `selfcheck.txt` |
| 0.95 (default) | `nodetool compact` | budget logged; outcome; filesystem rise | budget 1,159,145,677 B = (1,272,582,144 − 52,428,800) × 0.95; rc 0, 27 s; 4 sstables → 1 (696,149,909 B); no `has only` WARN; peak filesystem used 1,505,046,528 B, rise 754,032,640 B = 1.088 × the table | `cluster-run-0.95-summary.txt`, `budget-lines-0.95.txt`, `samples-0.95.csv` |
| 1.0 | same | same | budget 1,220,153,344 B; rc 0, 25 s; 4 → 1; no WARN; peak 1,505,046,528 B, rise 754,032,640 B | `cluster-run-1.0-summary.txt`, `samples-1.0.csv` |
| 0.10 | same | same | budget 122,015,334 B; rc 2 (`RuntimeException`, `Not enough space for compaction`); 4 `has only 116.36 MiB available, but 661.05 MiB is needed` WARNs and 22 reduce-scope / not-enough lines; the request fell 693,163,534 → 519,123,320 → 346,074,395 → 173,028,400 B and was refused at the last (one sstable left, every sstable > 122,015,334 B); sstables unchanged; filesystem rise 0 B | `cluster-run-0.10-summary.txt`, `budget-lines-0.10.txt`, `result-0.10.json`, `samples-0.10.csv` |
| all | errors | `^ERROR` lines in `system.log` since start | 0 (0.95), 1 (0.10: the thrown refusal), 0 (1.0) | `cluster-run-*-summary.txt` |
| all | cleanup | daemons | `STOPPED: daemons left: none` after each label; `down` label: none | `cluster-run-*-summary.txt`, `chain.out` |

### 4.2 Conclusion and logic

1. **Validity** — Valid. The limit was reached and passed: at 0.10 the budget (122 MB) is below the request (693 MB) and below every sstable, so admission refused; at 0.95 and 1.0 the request is below the budget (1.16 and 1.22 GB) and ran [observed: `result-*.json`, `budget-lines-*.txt`]. Held fixed: the same four sstables restored by `cp -a` into a fresh 2 GiB ext4 each time (used / avail identical to the byte at rest); `min_free_space_per_drive 50MiB` (the budgets equal `(avail − 50 MiB) × pct` to the byte); autocompaction off and no background compaction (`statusautocompaction: not running`; one `compactionhistory` row in the 0.95 and 1.0 runs) [observed: `cluster-run-*-summary.txt`, `compactionhistory-*.txt`]. The unit probe printed the compiled config path each time (one JVM per value).
2. **Readings** — (a) at 0.10 the `nodetool compact` ends with rc 2 and one `ERROR` line (the thrown refusal) — expected, not a fault; (b) the 0.95 and 1.0 runs have identical peak and rise because both budgets exceed the request; (c) the instrument-check run of the probe before the freeze gave the same kind of lines [observed: `unit-probe-lines.txt`; the discarded directory on the node].
3. **Matched rows** — Unit, B2g row 1 and row 2: `-0.01` and `1.01` throw `ConfigurationException` with the line-1017 message, `0 · 0.5 · 0.95 · 1` and the default are accepted and read back exactly, the budget equals `round((usable − minFree) × v)` for each accepted value and no usage figure depends on the value (heap spread 20 kB < 8 MiB, usable drift 0 < 4 MiB) [observed: `unit-probe-lines.txt`, `selfcheck.txt`]; the bytes returned scale with v while the check sets no size [observed: same, and the closed control's 56 OK in `readings-control.txt`]. Cluster, B3g rows 1 and 2: 1.5 rejected at startup with the line-1017 message; in-range values change only compaction admission (0.10 refused, 0.95 and 1.0 admitted) and nothing at rest (used / avail identical, du within 2 B, heap within 6 kB) [observed: `cluster-invalid-summary.txt`, `result-*.json`].
4. **Excluded rows** — B2g "check changes a usage figure for accepted values": heap and usable space do not depend on v (part 3). B2g "accepted values never reach the budget / bytes do not move": they move (part 3). B2g "−0.01 or 1.01 accepted, 0 or 1 rejected" (U5): the opposite was read. B3g "disk or heap at rest differ between in-range settings": they do not. B3g "0.10 does not block compaction, or the compaction never needs more than the budget": 0.10 refused with the WARN and the request (693 MB) is 5.7 times the budget. B3g "0.95 or 1.0 also reduces scope or is refused" (C5): no `has only` WARN, rc 0, 4 → 1.
5. **Observed vs. inferred** — Inferred: (i) that "usage is independent of whether the check exists": the check cannot be removed from a stock build, so it is read from the setter bypass (1.5 and −0.25 stored with no check; they change the budget formula only, `unit-probe-lines.txt`) plus the equal at-rest figures; (ii) the memory side rests on heap used at rest and after init; no heap reading was taken during a compaction; (iii) that the accepted-value control (0.10 vs 0.95) is caused by the knob, since the data and filesystem are otherwise identical (used / avail equal to the byte).
6. **Deviations and gaps** — Loop ext4 with `-m 0` (no reserved blocks); one cluster run per setting (the unit tier ran twice); the 0.5 s sampler can under-read a transient peak by at most one sample step (the rise of 754,032,640 B is 1.088 times the sum of the four Data.db files because the new sstable's other components - index, filter, summary, statistics - grow beside the old ones; not decomposed further); the streaming caller (`StreamSession.java:937`) and the multi-task sum case were not exercised; memory was read at rest only; a first cluster attempt was discarded after runbook defect D1.
7. **Core question** — No: usage does not follow the check at line 1016. The check only accepts or rejects the number (parts 3 and 4, unit and cluster); in range, the value is not a limit of its own but the input of a separate admission formula, whose effect is a soft, per-task cap on compaction output (positive control: the budget scales ×0.5 / ×1.0, 0.10 refused the compaction that 0.95 and 1.0 allowed). The constraint under test, the range validation, **does not cap** memory or disk.

**Conclusion (one line):** unit B2g rows 1 and 2, cluster B3g rows 1 and 2 — claim confirmed: the range check is validation only; the cap is the downstream admission test (effect: does not cap).

## 5. Self-check of run 1 — AI

### 5.1 Check of run 1's conclusion

`harness/.../selfcheck.py` re-parsed the raw unit files (`probe-*.out`), the closed control's readings and the cluster `result-*.json` / logs with its own code: all 98 checks PASS, 0 FAIL (`run1/selfcheck.txt`). By hand I re-opened `cluster-run-0.10-summary.txt`, `budget-lines-0.10.txt` (the 116.36 MiB vs 661.05 MiB WARN, the reduce-scope lines), `samples-0.10.csv` (constant 751,013,888 B used), `compactionhistory-0.95.txt` (one Major compaction, bytes_in 693,163,534, bytes_out 696,149,909), `cluster-invalid-summary.txt` and `unit-probe-lines.txt`.

| Part | Holds? | Note (file re-read) |
|---|---|---|
| 1. Validity | yes | budgets equal `(avail − 50 MiB) × pct` for all three settings (`selfcheck.txt`); at-rest used / avail equal across settings |
| 2. Readings | yes | rc 2 and the single ERROR at 0.10 are the refusal itself (`cluster-run-0.10-summary.txt`) |
| 3. Matched row | yes | each quoted number reproduced in `selfcheck.txt` and the summaries |
| 4. Excluded rows | yes | each cites a number found in the raw files |
| 5. Observed vs. inferred | yes | (i) is the weakest link: the counterfactual is the setter bypass, not a build without the check; it does not change the matched row because every accepted value leaves the at-rest figures unchanged |
| 6. Deviations and gaps | yes | listed as found; D1 and N1 recorded in section 3 |
| 7. Core question | yes | the steps run hypothesis B1 → probe and cluster → predictions → rows, with the control moving (0.10 vs 0.95/1.0; closed control 56 OK) |

### 5.2 Run 2?

**No** (2026-10-27). The unit result is deterministic (twelve probe JVMs, two repetitions agree to the byte on rejection and getter), the cluster contrast (refused vs 4 → 1) is a categorical difference, and the independent re-parse agrees. The inferred statement (i) would not change with a repeat.

## 6. Run 2 — fresh AI session (optional)

Not done (section 5.2).

## 7. Comparison — only if run 2 was done

Not applicable.

## 8. Verdict — AI

**Stage-3 estimate:** negative. **Outcome class:** true negative (negative, does not cap).

**Claim tested:** (B1) The range check at line 1016 does not cap memory or disk usage: it only validates the yaml value, and node disk usage is independent of whether the check exists; values inside [0, 1] are accepted unchanged, outside are rejected before any resource is allocated. "Confirmed" below means this claim held.

| Tier | Verdict (B2g / B3g row) | Effect on the constraint | Basis | Date |
|---|---|---|---|---|
| Unit | B2g rows 1 and 2: **Confirmed** — out-of-range throws, in-range accepted and read back, budget = `round((usable − minFree) × v)`, no usage figure depends on v; setter bypass stores 1.5 and −0.25 | does not cap | run 1 + self-check | 2026-10-27 |
| Cluster | B3g rows 1 and 2: **Confirmed** — 1.5 rejected at startup; in-range values change only admission; at-rest used/avail/du/heap identical across settings; 0.10 refused what 0.95 and 1.0 admitted | does not cap (the downstream admission formula is the soft cap) | run 1 + self-check | 2026-10-27 |

**Positive control:** 0.10 refused (rc 2, 4 `has only` WARNs, 4 sstables unchanged, filesystem rise 0 B) the compaction that 0.95 and 1.0 admitted (4 → 1, rise 754 MB), on identical data; and the closed `MaxCompactionSpaceOperandTest` re-run (56 OK) shows the budget moving with the value.

**Feedback filed:** the case file's section D updated (amendments U1–U6, C1–C6, C2a and these results); no section of the trace was refuted. **Open points:** the per-task nature of the downstream test (it does not bound the sum of simultaneous tasks) was not exercised here; the streaming caller was not exercised; `Config.java:344` stores the value as a boxed `Double`, so a null yaml value would be a different path (not tested). **Leftovers on `pc32`:** no `CassandraDaemon` running (checked with `ps -eo cmd | grep '[C]assandraDaemon'` on the node); the loop filesystem unmounted and its image and the seed copy removed; logs kept in `~/s4b-logs/msu/`; `~/cassandra-run4` kept for the next cases.
