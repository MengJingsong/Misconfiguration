# max_space_usable_for_compactions_in_percentage-hasDiskSpaceForCompactionsAndStreams-availableForCompaction — stage-4 results

> **Case:** [`max_space_usable_for_compactions_in_percentage-hasDiskSpaceForCompactionsAndStreams-availableForCompaction`](../../../stage3-ai-deep-read/long-path/cases/max_space_usable_for_compactions_in_percentage-hasDiskSpaceForCompactionsAndStreams-availableForCompaction.md)
>
> **Status:** audited and frozen 2026-10-07; run 1 (unit and cluster tiers) done and self-checked 2026-10-07, no run 2; **Confirmed at both tiers — H1 as predicted, H2 bypass as recorded**
>
> **Path:** long. Unit tier and cluster tier.

## 1. Before run 1 — design audit and freeze

| Field | Content |
|---|---|
| **Case-file version** | Working tree on top of commit `5f83a25` (the audit's amendments are not committed yet). **§9a's hash: `f17dad5a37c09c67cd9b61f61d6de22108f881e4`** (`sed -n '/^### 9a\. /,/^### 9b\. /p' <case file> \| git hash-object --stdin`), recorded 2026-10-07 **before the first cluster shakedown** and unchanged since (re-computed after the instrument checks); §9a is frozen at this text and must not be edited after any reading of run 1. §9's hash (`sed -n '/^## 9\. /,/^## 10\. /p'`): `6b251b9d13a0c2066dd9cfd6342172dd5a24e310` when §9a was recorded, `86dddb531b2f29e2a2a6ac022a0eb6d334cf4384` at the end of the instrument checks (9d and 9e wording was aligned with the script and the `WARN` trap added; documentation only). Later dated documentation-only amendments to 9b–9e change §9's hash but not §9a's. |
| **Harness** | [`../harness/max_space_usable_for_compactions_in_percentage-hasDiskSpaceForCompactionsAndStreams-availableForCompaction/`](../harness/max_space_usable_for_compactions_in_percentage-hasDiskSpaceForCompactionsAndStreams-availableForCompaction/): `CompactionBudgetTest.java`, `CompactionLadderTest.java`, `unit-run.sh`, `cluster-run.py`, `Jmx.java`, `make-node-yaml.sh`, `README.md`; written 2026-10-07, not committed. |
| **Tiers and values** | **Unit:** upstream `DirectoriesTest`, `CompactionsBytemanTest`, `PartialCompactionsTest`; `CompactionBudgetTest` at `pct` 0.95 · 0.5 · 0.1 · 0.01 (U = 1,000,000,000); `CompactionLadderTest` at `B / total` 1.5 · 0.8 · 0.4 · 0.1 (U = 4 GiB). **Cluster:** labels `d95` (default 0.95, scenario A), `f15` (A), `f08` and `f04` (B), `f01` (C, then H1 and H2), `inflight` (I1, I2); one fresh 4 GiB loop-mounted ext4 and two node starts per label. |
| **Audit bottom line** | **Ready after amendments** — 2026-10-07. Nothing blocks the run; eight recommendations were applied to the case file as dated amendments (below), one is left for stage 3. |

### 1.1 Design audit

Checked against the pinned clone `cassandra-5.0.9` (`git describe --tags` on the stage-3 clone and on the node's `~/cassandra-run1`): **every load-bearing citation of 9a/9b was re-read in context** — `Directories.java:517-521, 524-537, 528-536, 544-546, 550, 551, 557, 560, 563-569`; `CompactionTask.java:98-114, 148, 213, 308, 386-390, 409-413, 414-419, 421, 428-431, 441-442, 445-447, 450-454`; `DatabaseDescriptor.java:2567-2570, 2579-2582, 2584-2587`; `Config.java:339, 344`; `ColumnFamilyStore.java:334, 1698-1703, 2088-2091`; `ColumnFamilyStoreMBean.java:317`; `ActiveCompactions.java:59-76`; `CompactionMetrics.java:154-156` — none was wrong. The new citations the amendments rely on were read the same way (listed in the case file's 9a).

| Group | Check | Rating | Note (section checked) |
|---|---|---|---|
| A. Core question | constrained quantity is memory or disk bytes | Met | on-disk bytes of compaction output; the gated figure is the inputs' total, an over-estimate of it (§7, §8) |
| A. Core question | knob varied, ≥ 3 values incl. default — or another approach, with the reason | Met | 0.95 (default), and `B / total` = 1.5 · 0.8 · 0.4 · 0.1 in both tiers (9b); restart-only at the cluster tier, so one start per value (9a Testability) |
| A. Core question | real resource measured, not only the counter (gap named) | Met | the sampler reads `du`/`df`; 9d names that the check's own figure is the inputs' total and that a refusal leaves *more* on disk. Amended: the output's Data.db length is recorded per trigger |
| A. Core question | usage driven to the limit and past it | Met | the budget straddles the 8 inputs' total at 1.5 → 0.1, down to the abort |
| B. Logic | each step says what it establishes | Met | the "How this verifies" block matches 9a; it was extended to the hatch and in-flight additions (amended) |
| B. Logic | prediction stated in numbers or a clear relation | **Partly** | the in-flight bullet had no number and, at its stated sizes, predicted the wrong outcome: a 16-SSTable second table and `B ≈ 8 s + R/2` give `R ≈ 16 s`, every pass fails, the task **aborts** instead of being shed. Amended: three equal tables, `B = R₀ + 3.2 s`, n = 5, with the operand check (rec. 2) |
| B. Logic | every plausible outcome has a conclusions row with its evidence | **Partly** | the hatch rows were wrong for the stated trigger (rec. 1); no row for a stale band or for I2's estimator offset. Amended |
| B. Logic | confirmation needs ceiling-follows-knob and direct disallow evidence | Met | the debug line's `available`/`requested` per pass plus `Reducing scope` and the counters |
| B. Logic | alternative explanations and their controls | **Partly** | no run of the same compaction alone at the in-flight `pct`, no idle check of `debug.log`, no control for the hatch arm. Amended (I1, idle control, H1 as H2's control) |
| C. Specific | a human can follow the claim, the steps and the conclusions from the intro and 9a | Met | |
| C. Specific | an AI can run 9b–9e without re-deriving the code path | **Partly** | the `pct` depends on measured sizes and the knob is restart-only, which 9b's order did not allow; `total` and *s* were not defined; the sampler design (`compactionstats` every 500 ms) could not run. Amended (recs 3 to 7) |
| C. Specific | knob, values, workload, commands, observables, sampling and stop conditions exact | **Partly** | the in-flight stop conditions and the hatch trigger were missing or wrong; the data directory, blob content and the logging default were unstated or wrong. Amended |
| D. Runnable | harness and environment prerequisites exist or are listed | Met | listed in 9c; written and instrument-checked 2026-10-07 (§3) |
| D. Runnable | workload arithmetic reaches the limit (data, time, disk, memory) | Met | 8 × 63.1 MiB per table; free space 3.15 GiB at plan time; the in-flight arm peaks at about 2.2 GiB of it; 3 min 9 s (`f08`), 3 min 34 s (`f01`) and 5 min 17 s (`inflight`) per label in the shakedowns; the old 1 GiB `ks1.big` was not needed |
| D. Runnable | load-bearing citations spot-checked against the pinned clone | Met | see the list above; one factual error found in **9d**, not in a citation: the `debug.log` line is **on** by default at this tag (`conf/logback.xml:132`), not off |

**Two findings that the audit rests on, both from the source, neither from a reading.**

1. **`nodetool compact` cannot reach the escape hatch.** The hatch tests `compactionType == OperationType.COMPACTION` (`CompactionTask.java:386`); `nodetool compact` → `forceMajorCompaction` → `performMaximal` → `submitMaximal(…, OperationType.MAJOR_COMPACTION)` (`CompactionManager.java:993`) and `getMaximalTasks` stamps that type on the task (`CompactionStrategyManager.java:1091`). The case's escape-hatch arm (§6b says the hatch "applies only to `OperationType.COMPACTION`") triggered it with `nodetool compact` and predicted the bypass; it would have shown the ladder and been classed "Not confirmed". A background task keeps the default type (`AbstractCompactionTask.java:50`), and `nodetool enableautocompaction` submits one even on a table created with `'enabled': 'false'` (`CompactionStrategyManager.enable()` sets the flag unconditionally, `:932-939`). The arm is now H1 (still refused) and H2 (runs in full).
2. **The in-flight term depends on when the compaction was admitted, so the arm needs a number.** `R` is the estimator's remaining write of every active compaction, `compressionRatio × (total − completed)` (`CompactionInfo.java:196-205`), and it falls as the slow task runs while `U` falls with it; the arm must name the margin, the timing window and an alone control.

| # | Recommendation | Applied? | Why |
|---|---|---|---|
| 1 | Split the escape-hatch arm into H1 (hatch off + `nodetool compact`: still refused) and H2 (hatch off + `nodetool enableautocompaction ks1 t`: runs in full, info line, no debug line); replace the "Not confirmed" row | **applied** to 9a (procedure 3, prediction, conclusions, "Refuted if"), 9d, 9e, dated 2026-10-07 | `MAJOR_COMPACTION` is not `COMPACTION` (finding 1) |
| 2 | Redo the in-flight arm: tables `t`, `t2`, `slow`; `B = R₀ + 3.2 s`; I1 alone then I2 with `slow` at 4 MiB/s; `R` read from `system_views.sstable_tasks`; tolerance 16 MiB; n = 5 | **applied** to 9a (prediction, conclusions), 9c, 9e | the old sizes abort instead of shedding, and nothing compared the compaction alone with the same compaction in flight |
| 3 | Two node starts per run; define `total` (Σ `*-Data.db` lengths = `onDiskLength()`), *s* and *U* (`df` avail); `pct` computed with the node stopped | **applied** to 9a (procedure 2), 9b | the knob is restart-only and `pct` needs the measured sizes; `tablestats`/`du` count every component |
| 4 | Add the unit step 3, `CompactionLadderTest` (real `CompactionTask`, stub store of known *U*, ladder simulated from the lengths), and steps 2.6 (floor) and 2.7 (the logged lines) of `CompactionBudgetTest` | **applied** to 9a (procedure 1c), 9b, 9c, 9e | `CompactionBudgetTest` drives the check alone; nothing upstream drives the decision point and the counters with real sizes (`PartialCompactionsTest` is one step) |
| 5 | The sampler reads `system_views.sstable_tasks` through a driver session, not `nodetool compactionstats`; `Jmx.java` replaces `nodetool sjk mx`; `cluster-run.py` replaces `build-inputs.sh` and `compaction-sampler.sh` | **applied** to 9c, 9d (documentation) | each `nodetool` call starts a JVM; 500 ms sampling is impossible with it |
| 6 | The `Directories` debug line is on by default (`logback.xml:132`, no discarding `:69`); keep the explicit `setlogginglevel` and read it back; the line names no table, so parse `debug.log` between byte offsets and keep `requested ≥ 1 MiB` | **applied** to 9b, 9d | the old text said it was off by default |
| 7 | Data directory `/mnt/stage4-data/data` (ext4 `lost+found`), `mkfs.ext4 -F`, a fresh filesystem per run; random blobs; the dataset check on Data.db lengths (8 files, largest ≤ 1.10 × smallest, each within 10 % of 64 MiB) | **applied** to 9a (Invalid rows), 9b, 9c, 9e | reproducible baseline; incompressible payload; the check operates on the figure the gate uses |
| 8 | §6b and §8 say the hatch covers only `OperationType.COMPACTION` but not which operations those are: a **major** compaction (`nodetool compact`, `compact -s`) always runs the check; the hatch bypasses background tasks (and user-defined ones, which have no ladder: `partialCompactionsAcceptable()` is false) | **left for stage 3** | the bypass claim in §8 is narrower than it reads; Target-3 note |
| 9 | `PartialCompactionsTest` stays in the unit tier: it is a real one-step ladder test (its wrapped `Directories` overrides this case's `hasDiskSpaceForCompactionsAndStreams` and feeds it a stub store), but 9a's procedure did not name it and 9c/9e did not run it | **applied** (documentation): named in 9a step 1(a), run by `unit-run.sh` and 9e step 1 | it is the only upstream test of the decision point; it was passing before the harness (1 test, instrument run) |

**Agreement criteria** — filled only if run 2 is chosen.

## 2. Environment

| Field | Run 1 | Run 2 (fresh AI session, if done) |
|---|---|---|
| Date | 2026-10-07; unit tier first, then the cluster labels one after another (node clock, MDT): `d95` 19:53:15, `f15` 19:57, `f08` 20:00:57, `f04` 20:05, `f01` 20:08:54, `inflight` 20:12:56 to 20:18:10 | |
| Node (CloudLab name and type) | `pc66` (`node0.jason92-317394…`), 40 cores, 125 GiB; `pc80` did not answer ssh on 2026-10-07 (connection timed out) | |
| OS and kernel (`uname -r`) | Ubuntu 22.04.2, 5.15.0-187-generic | |
| JDK (`java -version`) | openjdk 11.0.32.1 | |
| Ant (`ant -version`) | Apache Ant 1.10.12 | |
| Local `cassandra-src` clone commit | `~/cassandra-run1` at `b5f2a54210` (`cassandra-5.0.9`) | |
| Case-file commit / harness commit | `e504e92` (audit amendments, harness and §1 to §3 of this file, committed together 2026-10-07 14:01). The node's copy of the harness in `~/stage4-harness-run/mscp` is byte-identical to the repo's (`md5sum` of all seven files, checked before run 1). §9a's hash was not re-computed by the run 1 session (the case file was not readable there), so "unchanged since freeze" rests on the commit history | |
| Storage for node data | a 4 GiB sparse file `~/stage4-data.img` on the local disk (`/dev/sda3`), loop-mounted ext4 at `/mnt/stage4-data` | |
| Full logs (path, outside the repo) | `pc66:~/stage4-logs/mscp/{unit,d95,f15,f08,f04,f01,inflight}/` (`debug.log`, `system.log`, `startup-*.log` stay there; small excerpts are in `run1/` next to this file). The shakedown directories were moved aside before the labels that had one: `f08.20261007-114633` and `inflight.20261007-115610` by the script, `f01.shakedown-aside` by hand (see §4.2, deviations) | |

## 3. Runbook defects

Instrument checks before run 1 (2026-10-07, `pc66`). They are **not readings of run 1**: their logs are kept under `~/stage4-logs/mscp/unit-instrument*/` and `~/stage4-logs/mscp/<label>.<timestamp>/`, §9a was frozen before the first cluster one, and run 1 repeats the tiers from the beginning.

| # | Run | Step (§9b–§9e) | Problem | Fix | Decision (date) | Case-file commit with the fix |
|---|---|---|---|---|---|---|
| 1 | unit instrument 1 | 9e unit step 3 (`CompactionLadderTest`) | `CompactionManager.instance.disableAutoCompaction()` reaches only the tables that exist when it is called; the test's table is re-created afterwards, so size-tiered compaction merged four of the eight flushes (sizes 1.2 and 4.8 MB, 5 live SSTables) and 18 checks recorded `MISMATCH` from the second value on. The first value (n = 0) matched in full | `cfs.disableAutoCompaction()` on the re-created table and at the start of every value | 2026-10-07; harness only (§9a unchanged); the instrument run was repeated (instrument 2: 0 `MISMATCH`) | with this file |

**Run 1 (2026-10-07):** no step failed to run as written; no harness file changed between the instrument checks and run 1 (the node's copy is byte-identical to the repo's).

### 3.1 What the instrument checks established (2026-10-07, `pc66`)

Not readings of run 1 (see the note above §3's table). Logs on the node: `~/stage4-logs/mscp/unit-instrument/` and `…/unit-instrument2/` (unit), `…/f08/`, `…/f01/`, `…/inflight/` (cluster); each cluster directory holds `summary.txt`, `passes.csv`, `triggers.csv`, `samples.csv`, `session.log`, `debug.log`, `system.log`, `logs-build/`. The harness files on the node and in the repo are byte-identical (`md5sum`).

| Instrument | Check | Result |
|---|---|---|
| `CompactionBudgetTest` | compiles in the clone; runs | 1 test, 106 checks, 0 `MISMATCH` (`unit-instrument/run.out`) |
| `CompactionLadderTest` | compiles in the clone; runs; the simulation agrees with a real `CompactionTask` | first run: 18 `MISMATCH` from the second value on (defect 1, auto-compaction); after the fix 92 checks, 0 `MISMATCH` — simulated and observed passes equal at `B / total` = 1.5 (1 pass), 0.8 (3, *n* = 2), 0.4 (6, *n* = 5), 0.1 (8, abort) |
| upstream | the three classes run in the clone | `DirectoriesTest` 42 tests, `CompactionsBytemanTest` 6, `PartialCompactionsTest` 1, no failure |
| `cluster-run.py` (`f08`) | two starts, dataset check, plan, idle control, trigger, analysis | 10 `EXPECTED:` lines, none `NO`; first pass `available` = the expected B to the byte; passes, counters (+1 / +2 / 0), warnings and file counts as simulated |
| `cluster-run.py` (`f01`) | C, the JMX `invoke`, H1, H2 | 23 `EXPECTED:` lines, none `NO`; C and H1 identical (8 passes, 7 `Reducing scope`, abort, 0 / 0 / +1, nodetool exit 2, inputs untouched); H2: the info line once, no pass line, 8 → 1 Data.db file; two `ERROR` lines in `system.log` (the two aborts, `CompactionTask.java:442` called from `:148`, the lines the case cites) |
| `cluster-run.py` (`inflight`) | I1, I2, the sampler's `R`, the admission wait | 22 `EXPECTED:` lines, none `NO`; I1 *n* = 0; I2 first pass `requested − 8 s` = 515,567,055 against the sampler's 515,804,253 (0.05 % apart); *n* = 5 (`Reducing scope` ×5, counters +1 / +5 / 0, 6 Data.db files of `ks1.t2`); the slow task showed progress 2.0 s after its `nodetool` started |

Two things the instrument checks showed that the case file did not say, both put into 9d: the `Directories` `WARN` line prints rounded sizes (the unit run printed `has only 451.84 MiB available, but 451.84 MiB is needed` for a refusal by one byte), and the check's `DEBUG` line is on by default at this tag. **What remains for run 1:** the labels `d95`, `f15` and `f04` were not shaken down — they use the same code path as `f08` with another `pct` (for `d95` the entry is left out of the yaml); `pc80` was unreachable, so run 2 (if chosen) needs `pc66` again or another node.

## 4. Run 1

**Scope:** the unit tier (`unit-run.sh`, no suffix), then the six cluster labels in the order `d95`, `f15`, `f08`, `f04`, `f01`, `inflight`, each started in the background by `cluster-run.py <label>` on a fresh 4 GiB loop-mounted ext4 and read only after the process had exited (no node or run process was left behind: `ps` showed none after each label). Every label's own instrument check passed (first pass `available` equals the expected B, difference 0). **Command log and evidence:** `max_space_usable_for_compactions_in_percentage-hasDiskSpaceForCompactionsAndStreams-availableForCompaction/run1/` (below `run1/`: `unit/{summary.txt,run.out}` and `cluster/<label>/{summary.txt,passes.csv,triggers.csv,samples.csv,session.log}`); the full logs stay on the node. No step failed to run as written, so there is no new runbook defect in §3.

### 4.1 Readings

Paths are relative to `run1/`. "Pass" is a `Directories` debug line of the table-size compaction: (`available`, `requested`) in bytes. Counters are the deltas of `CompactionsReduced` / `SSTablesDroppedFromCompaction` / `CompactionsAborted`. U is `df` available of the data filesystem with the node stopped; `total` is Σ `*-Data.db` of the table.

**Unit tier**

| Test or assertion | Result | Evidence (file) |
|---|---|---|
| `DirectoriesTest` (upstream) | 42 tests, 0 failures, 0 errors | `unit/summary.txt` |
| `CompactionsBytemanTest` (upstream) | 6 tests, 0 failures, 0 errors | `unit/summary.txt` |
| `PartialCompactionsTest` (upstream) | 1 test, 0 failures, 0 errors | `unit/summary.txt` |
| `CompactionBudgetTest` (new) | 1 test, 0 failures; `pct` 0.95 · 0.5 · 0.1 · 0.01 | `unit/summary.txt`, `unit/run.out` |
| `CompactionLadderTest` (new) | 1 test, 0 failures; `B / total` 1.5 · 0.8 · 0.4 · 0.1 | `unit/summary.txt`, `unit/run.out` |
| Both new tests' own checks | 198 `STAGE4 check` lines, 0 `MISMATCH`; two `STAGE4 summary mismatches 0` lines | `unit/run.out` |

**Cluster tier** — U and `total` as printed by the plan line of each `summary.txt`; U ≈ 3.38 GB for all labels except `inflight` (2.32 GB, three tables on the filesystem).

| Capacity value | Run | Observable (§9d) | Reading | Evidence (file) |
|---|---|---|---|---|
| `d95`: default `pct` 0.95, B = 5.9697 × total (3,161,109,709) | A | passes | 1: (3161109709, 529529016) | `cluster/d95/summary.txt`, `passes.csv` |
| | A | warnings, counters | `Reducing scope` ×0, abort ×0; counters +0 / +0 / +0 | `cluster/d95/summary.txt` |
| | A | outcome | `nodetool compact` rc 0; Data.db files 8 → 1 (529,539,300 B); idle control: no pass line in 30 s, `df` and `du` unchanged | `cluster/d95/summary.txt` |
| `f15`: B = 1.5000 × total (794,304,044) | A | passes | 1: (794304044, 529530163) | `cluster/f15/summary.txt`, `passes.csv` |
| | A | warnings, counters | ×0; +0 / +0 / +0 | `cluster/f15/summary.txt` |
| | A | outcome | rc 0; files 8 → 1 (529,539,521 B); idle control clean | `cluster/f15/summary.txt` |
| `f08`: B = 0.8000 × total (423,628,673) | B | passes | 3: requested 529529975 → 463337992 → 397146479, `available` 423628673 in each | `cluster/f08/summary.txt`, `passes.csv` |
| | B | warnings, counters | `Reducing scope` ×2, abort ×0; +1 / +2 / +0 | `cluster/f08/summary.txt` |
| | B | outcome | rc 0; files 8 → 3 (output 397,155,314 B against kept inputs 397,146,479 B); idle control clean | `cluster/f08/summary.txt` |
| `f04`: B = 0.4000 × total (211,814,327) | B | passes | 6: requested 529529951 → 463338316 → 397146823 → 330955384 → 264764140 → 198573004, `available` 211814327 in each | `cluster/f04/summary.txt`, `passes.csv` |
| | B | warnings, counters | ×5, abort ×0; +1 / +5 / +0 | `cluster/f04/summary.txt` |
| | B | outcome | rc 0; files 8 → 6 (output 198,577,340 B against kept inputs 198,573,004 B); idle control clean | `cluster/f04/summary.txt` |
| `f01`: B = 0.1000 × total (52,953,514) | C | passes | 8: requested 529529271 → … → 66190626 (every step drops the largest remaining input), `available` 52953514 in each; none ≤ `available` | `cluster/f01/summary.txt`, `passes.csv` |
| | C | warnings, counters | `Reducing scope` ×7, one abort warning; +0 / +0 / +1 | `cluster/f01/summary.txt` |
| | C | outcome | `nodetool compact` rc 2 (the task threw); the 8 inputs untouched (same files and lengths, no output); idle control clean | `cluster/f01/summary.txt` |
| `f01`, hatch off by JMX `compactionDiskSpaceCheck(false)` (invoke rc 0) | H1 | passes, warnings, counters, outcome | identical to C: 8 passes, ×7 + one abort warning, +0 / +0 / +1, rc 2, inputs untouched, no "Compaction space check is disabled" line | `cluster/f01/summary.txt`, `triggers.csv` |
| | H2 (`nodetool enableautocompaction ks1 t`, hatch off) | passes, info line | no pass line; the info line "Compaction space check is disabled" ×1; one `Compacting` line | `cluster/f01/summary.txt` |
| | H2 | counters, outcome | +0 / +0 / +0; rc 0; files 8 → 1 (529,539,178 B against inputs 529,529,271 B) | `cluster/f01/summary.txt` |
| `inflight`: B = 1.4000 × total of `t` = R₀ + 3.2 s (741,352,107) | I1 (`t` alone) | passes, counters, outcome | 1: (741352107, 529527558); +0 / +0 / +0; rc 0; files 8 → 1; idle control clean | `cluster/inflight/summary.txt`, `passes.csv` |
| | I2 (`t2` while `slow` runs at 4 MiB/s) | slow task | seen 1.4 s after its `nodetool` started (progress 2,832,280 of 527,298,120); its own pass (741389648, 529529017) = R₀, so it was admitted whole | `cluster/inflight/summary.txt` |
| | I2 | passes of `t2` | 6: requested 1047682544 → 981490866 → 915299365 → 849107905 → 782916495 → 716725193, `available` 737607424 falling to 737591335 (within 1 MiB of the first) | `cluster/inflight/summary.txt`, `passes.csv` |
| | I2 | in-flight term | first pass requested − total of `t2` (529530251) = R 518,152,293; the sampler's remaining write of `slow` at that line's time 518,272,046.8 (119,754 B apart, 0.02 %); U at the slow task's first progress 2,313,576,448 (B there 740,138,738) | `cluster/inflight/summary.txt`, `samples.csv` |
| | I2 | warnings, counters, outcome | `Reducing scope` ×5, abort ×0; +1 / +5 / +0; rc 0; `t2` 6 Data.db files, `slow` 1, `t` 1 | `cluster/inflight/summary.txt`, `triggers.csv` |

**Run-script expectations.** Each label's `EXPECTED:` lines are the script's encoding of the 9a predictions (simulated ladder, pass figures, counters, files, hatch). All are answered yes: `d95` 10, `f15` 10, `f08` 10, `f04` 10, `f01` 23, `inflight` 22 (none "no"; same counts as the instrument checks). That is the script's check against its own simulation, not the §9a row match, which is §4.2's job.

### 4.2 Conclusion and logic

Tags: **[observed: file]** is a figure or line in a raw file; **[inferred: reason]** is a step from the source or from several readings. File names are relative to `run1/`; `selfcheck.txt` is the output of `selfcheck.py`, which re-derives the figures from the node's raw `debug.log` and `system.log` (section headings `== D95` … `== INFLIGHT` there).

1. **Validity — valid.**
   - *The limit was reached.* At 0.8, 0.4 and 0.1 the check's budget was below the inputs' total (423,628,673 · 211,814,327 · 52,953,514 B against 529.5 MB) and the full set was refused [observed: `cluster/f08|f04|f01/summary.txt`; the raw pass lines in `selfcheck.txt`].
   - *The knob took effect.* Each node's own start-up configuration line shows the resolved `pct` (0.95 · 0.238710108666 · 0.127312012756 · 0.063656081852 · 0.015913941258 · 0.327328796478) [observed: raw `system.log`, "Node configuration"; first line of each label in `selfcheck.txt`], and every first pass's `available` equals `round((U − 50 MiB) × pct)` from the `df` read before the trigger, to the byte; in I2, where U falls while `slow` writes, 6,372 B from the value recomputed at the sampler's U [observed: `selfcheck.txt`].
   - *Hold fixed (9b).* Tables `STCS`, `'enabled': 'false'`, `pk int PRIMARY KEY, v blob`, default compression [observed: `cluster-run.py:548-550` in the harness, which the run script executed]; no automatic compaction ran (the only `Compacting` lines of `ks1` in each `system.log` are those of the compactions the run triggered: 1 · 1 · 1 · 1 · 1 (H2; the two aborts print none) · 3) [observed: `selfcheck.txt`]. Random 5,120 B blobs, not compressed [observed: every Data.db is at least 12,800 × 5,120 B]. `compaction_throughput` 64MiB/s and `concurrent_compactors` default [observed: the configuration line of the six `system.log`s]; 4 MiB/s only for `slow` in `inflight` (set 20:17:43, back to 64 at 20:17:48) [observed: `cluster/inflight/session.log`]. No other tables [observed: the raw `inflight` `debug.log` holds exactly 8 pass lines of at least 1 MiB, I1's, `slow`'s and I2's; in the other labels only the triggers' own bursts: one each, two in `f01`]. `-Xms4G -Xmx4G` [observed: JVM Arguments line]. `DEBUG` on `Directories` read back [observed: `LOGGING … DEBUG` in each `summary.txt`]. The data directory on the dedicated filesystem [observed: every pass line names `/mnt/stage4-data (/dev/loop0)`].
   - *Controls.* Idle control (30 s: `df`, `du` and the pass-line count unchanged) in all six labels [observed: `summary.txt`, IDLE line]; the default arm `d95`; C is H1's control and H1 is H2's; I1 is I2's alone control [observed].
   - *9a's Invalid rows.* Dataset: 8 Data.db files per table, the largest at most 1.00002 times the smallest (limit 1.10), each 1.4 % below 64 MiB (limit 10 %) [observed: `selfcheck.txt`]. Band: the ladder simulated from the lengths, with the debug line's own `available`, gives the planned 0 · 0 · 2 · 5 · abort · 0 · 5 [observed]. Drift: first-pass `available` equals the expected B in every arm but I2 (above) [observed].

2. **Readings — nothing contradicts another; five things to know.** (a) The output SSTable is slightly **larger** than the kept inputs' Data.db total (529,539,300 B against 529,529,016 B at the default; +0.002 % to +0.003 % in every completed arm) [observed: the `INFO … output length … against the kept inputs` line of each `cluster/<label>/summary.txt`]: the inputs here are disjoint and incompressible, so the merge removes nothing. (b) Peak-minus-baseline of `ks1.t` is 1.0021 to 1.0022 × the kept inputs in three labels and 0.9877 in `f04` [observed: `selfcheck.txt`]: the 500 ms sampler misses the last part of a short write. (c) The final disk use sits within 16 KB of the baseline in every label (below). (d) The counters are the run script's JMX reads; only their deltas were kept [observed: `triggers.csv`]. (e) The abort's `ERROR` line is `JVMStabilityInspector … Exception in thread …` with the `RuntimeException` on the next line (the checker's first run missed that; fixed, §5).

3. **Matched row — the first row of 9a's Conclusions table, quoted:** *"The ladder follows the arithmetic at each value (n = 0, 2, 5, abort at 0.1); the debug line shows `available = B` and `requested` as predicted; the in-flight arm sheds what the alone arm admitted whole (n = 5 against 0); H1 is refused and H2 runs in full"* → **Confirmed**. Each part:
   - *n = 0 · 0 · 2 · 5 · abort:* default 5.97 × total and 1.5 × → one pass, n = 0; 0.8 × → 3 passes (529,529,975 → 463,337,992 → 397,146,479), n = 2; 0.4 × → 6 passes down to 198,573,004, n = 5; 0.1 × → 8 passes down to 66,190,626 (still above 52,953,514), seven `Reducing scope` and one abort [observed: `cluster/<label>/passes.csv`, raw `debug.log` and `system.log` in `selfcheck.txt`]. Each pass lowers `requested` by the then-largest input's Data.db length, so the dropped input is the largest [observed: the sequences equal the simulation that drops the largest].
   - *`available = B`, `requested` as predicted:* `available` is the same in every pass of an arm and equal to `round((U − 50 MiB) × pct)`; `requested` equals the simulated sums to the byte, in all 7 arms [observed: `selfcheck.txt`].
   - *Counters:* `CompactionsReduced` +1 and `SSTablesDroppedFromCompaction` +2 (0.8) and +5 (0.4), `CompactionsAborted` +1 at 0.1 with the other two unchanged [observed: `triggers.csv`; the script's JMX read, matched by the `Reducing scope` and abort lines in `system.log`].
   - *In flight:* I1 (`ks1.t` alone, B = 741,352,107) one pass, n = 0; I2 (`ks1.t2` while `ks1.slow` ran) six passes from `requested` 1,047,682,544 to 716,725,193 against `available` ≈ 737.6 MB, n = 5, three inputs kept, `Reducing scope` ×5 [observed: `cluster/inflight/passes.csv`, `selfcheck.txt`]. The first pass's `requested` minus `t2`'s total is 518,152,293 B and the slow task's remaining write, read from `sstable_tasks` and interpolated to that line's time, is 518,273,295 B: 0.02 % apart, within the 16 MiB of the row on the estimator [observed: `cluster/inflight/samples.csv`, `selfcheck.txt`].
   - *H1 refused, H2 in full:* with `compactionDiskSpaceCheck(false)` invoked (rc 0), H1 (`nodetool compact`) repeated C's eight passes, seven warnings and abort, rc 2, nothing written; H2 (`nodetool enableautocompaction ks1 t`) printed the info line once (`system.log:288`, one ms before its `Compacting` line), no pass line (the raw `debug.log` holds only C's and H1's 16 lines of at least 1 MiB), and wrote 529,539,178 B in one file, 10.0 × the budget [observed: `cluster/f01/summary.txt`, `selfcheck.txt`]. The H1 row ("As predicted") and the H2 row ("Bypass as recorded") of 9a both apply.

4. **Excluded rows.**
   - *Confirmed, with an estimator offset:* every arm's n equals the planned n and the simulation from the Data.db lengths, with `requested` equal to the sums to the byte: no off-by-one [observed: `selfcheck.txt`].
   - *Refuted (a compaction runs unreduced with inputs above B while the check ran):* the unreduced runs are `d95` (B 3.16 GB), `f15` (794 MB), I1 (741 MB) and the `slow` task (741 MB), all with inputs below B; wherever the inputs exceeded B the compaction was shed or aborted. H2 ran unreduced with the check **not** evaluated (no pass line) [observed].
   - *Not confirmed (full runs at every pct with no `Reducing scope` and no debug line):* `Reducing scope` ×2, ×5, ×7, ×5 and pass lines in every arm but H2, whose info line explains it [observed].
   - *Refuted (n unchanged between 0.8 and 0.4 while `available` changes):* n = 2 and 5 while `available` fell from 423,628,673 to 211,814,327 [observed].
   - *Refuted (I2 admits `ks1.t2` whole):* I2's first pass `requested` 1,047,682,544 exceeds `available` 737,607,424; `slow` was running (its `sstable_tasks` row at the line's time) [observed].
   - *Not confirmed (`requested − total` differs from R by more than 16 MiB):* 121,002 B apart [observed].
   - *Not confirmed (final disk use lower at lower pct):* final minus baseline is −9,387 (default), −10,335 (1.5), −15,926 (0.8), −15,464 (0.4) and 0 B (the abort at 0.1): all within 0.003 % of 531 MB, no trend in `pct` [observed: `triggers.csv`, `samples.csv`]. The finals of 0.8 and 0.4 are 5.1 to 5.6 KB below the default's [inferred: the small components of one merged output against eight, not reclaimed data, because these inputs do not shrink]. The row's concern, an abort deleting inputs, did not happen: the abort's final equals its baseline to the byte [observed].
   - *Refuted (H1 runs in full):* H1 equals C [observed].
   - *Not confirmed (H2 still shows the ladder):* no pass line from H2's task [observed].
   - *Invalid (drift / dataset / band):* the three checks of part 1 [observed].

5. **Observed vs. inferred — the inferred statements the conclusion depends on.**
   - That the pass lines belong to the compaction under test [inferred: the 1 MiB filter, one burst per trigger in the raw `debug.log`, and `requested` equal to the table's Data.db total; no other task of that size ran].
   - That the in-flight term is what shed I2 [inferred: I1 and I2 differ only by `slow` running; `requested − total(t2)` equals the slow task's remaining write to 0.02 %, and the source ties that term to the estimator, `CompactionInfo.java:196-205`, `ActiveCompactions.java:59-76`; `available` is B alone and was recomputed at the sampler's U].
   - That H1 is refused because `MAJOR_COMPACTION` is not `COMPACTION` [inferred from the source, `CompactionTask.java:386`, `CompactionManager.java:993`, `CompactionStrategyManager.java:1091`; observed is the contrast: the same flag state, H1 checked, H2 not]. That the flag was off for H1 [inferred: the invoke returned rc 0 two seconds before H1, and H2's info line, which the code prints only for a disabled check, appeared 12 s after the invoke on the same table; nothing switched the flag in between].
   - That the counters moved as read [inferred: raw JMX values were not kept; the lines the counters count agree].
   - That "a refusal leaves more on disk" [inferred; not observed in bytes: the data does not shrink, so a full compaction would not have freed anything either].
   - That the gate's figure over-estimates the output [not exercised: here it under-counts by 0.002 %, part 2a].

6. **Deviations and gaps.**
   - The `f01` shakedown directory was moved aside by hand before that label started (the script would have done it); the ssh launcher of the first two labels stayed attached until the run exited, with no effect on the run; three labels (`d95`, `f15`, `f04`) were not shaken down before run 1 and passed at once.
   - Raw JMX counter values were not saved (only deltas).
   - One node, one device: the per-store split (`Directories.java:528-536`) and the second knob `min_free_space_per_drive` were exercised at the unit tier only (the second knob in `CompactionBudgetTest` step 2.5).
   - Not exercised: user-defined compactions (derived only), the fail-open `catch` at `CompactionTask.java:414-419`, the expired-SSTable branch (§6b step 3), overlapping or compressible inputs (where the over-estimate of §7 would show).
   - The 500 ms sampler can read a peak up to about 1.2 % below the written size (part 2b).
   - The idle controls are 30 s each.

7. **Core question.** Usage followed the constraint and the constraint capped it, with a precise meaning. Before anything was written the node cut the compaction's committed size (the inputs' total plus every compaction in flight) to the budget `(U − 50 MiB) × pct`: it kept 6 of 8 inputs at 0.8, 3 at 0.4 and refused all at 0.1, and the output it then wrote equals the kept inputs' total (397.2 MB and 198.6 MB, below the budgets of 423.6 and 211.8 MB; in I2 198.6 MB below `available − R` = 219.4 MB) — steps (1) to (4) of 9a's Logic, parts 3 and 4. A compaction already in flight uses up the same budget: the compaction admitted whole alone was shed to 3 inputs beside it — step (5), part 3. The cap is on the new output at admission: the inputs stay on disk (the table's transient peak above its baseline fell with `pct`: +530.7, +398.0, +196.1 and +0 MB, step (6)), and it does not apply to a background compaction once the table's check is switched off over JMX (H2 wrote 10 × the budget), while a major compaction is always checked (H1).

**Conclusion (one line):** the first row of 9a's Conclusions table — **Confirmed** (ladder n = 0 · 0 · 2 · 5 · abort, in-flight n = 5 against 0), with **H1 as predicted** (the hatch does not cover `nodetool compact`) and **H2 bypass as recorded** (529,539,178 B written against a budget of 52,953,514 B).

## 5. Self-check of run 1 — AI

### 5.1 Check of run 1's conclusion

Method: the figures of §4.2 were not read back from the run script's `summary.txt`. `selfcheck.py` re-parses the node's raw `debug.log` and `system.log` of all six labels and the excerpts (`unit/`, `cluster/<label>/`), recomputes `B = round((U − 50 MiB) × pct)` from the config line and the `df` read, re-runs the ladder from the Data.db lengths, and compares both with the pass lines, the `Reducing scope`, `has only`, abort and info lines, the `Compacting` and `Compacted` lines, and the sampler's disk and `sstable_tasks` series; the expected values in it are typed from 9a. Output: `selfcheck.txt`, **134 checks, all hold**. Its first execution had 2 that did not (the abort's `ERROR` count in `f01` C and H1): the checker looked for the message on the `ERROR` line, where it is on the next one (`system.log:233` and `:272` show it); the parser was corrected and the whole script re-run, and the run's data were not touched. By eye I also re-read, in the raw logs: `f01` `system.log` lines 288, 289 and 291 (the info line, `Compacting`, `Compacted … 8 sstables`) and 231-238 (the abort), and the eight `inflight` pass lines in the raw `debug.log` (numeric filter; an earlier ad hoc string-comparison `awk` dropped one and was discarded).

| Part | Holds? (yes / no) | Note (file re-read) |
|---|---|---|
| 1. Validity | yes | the config line, JVM line, dataset lengths and `compaction_throughput` re-read in each label's raw `system.log` and `summary.txt`; `available` recomputed to the byte (I2: 6,372 B at the sampler's U); the schema only from the harness source, not from a log (the tables' options cannot be read back from the logs) |
| 2. Readings | yes | the five items of part 2 re-derived: output +0.002 %, sampler ratios 1.0021 and 0.9877, finals within 16 KB of the baseline, counters from `triggers.csv` |
| 3. Matched row | yes | each clause re-read against raw lines: passes, counters (script read, matched by log lines), the 0.02 % agreement of R (re-interpolated from `samples.csv`: 518,273,295 against the script's 518,272,047), H1 = C, H2's info line at `f01/system.log:288` with no pass line after it |
| 4. Excluded rows | yes | every row of 9a's table is answered; row 8 is read as "no trend, equal within 0.003 %" and the 5.5 KB difference between labels is marked inferred, not hidden |
| 5. Observed vs. inferred | yes | the matched row names outcomes (passes, counters, the info line, the output size), and each is observed; the inferred statements carry the explanations ("as traced": the in-flight term, the `MAJOR_COMPACTION` reason, the flag state), so the wording "the check enforces as traced" leans on them and the outcomes alone do not need them |
| 6. Deviations and gaps | yes | the manual `mv` is in the node's directory listing (`f01.shakedown-aside`); the unsaved JMX values and the unexercised branches are named |
| 7. Core question — the steps from reading to answer follow the audited logic | yes | 9a's Logic steps (1) to (6) map to parts 3 and 4 as written in part 7; the answer says what the cap is (new output at admission, inputs stay, hatch for background tasks) and does not claim more than the readings show |

### 5.2 Run 2?

**No** (2026-10-07). The matched row rests on observed outcomes only, not on a statement §4.2 part 5 marks inferred; the figures are exact equalities with an independent simulation (to the byte, in seven arms, re-derived from the raw logs, not from the run script's output); the abort was reproduced twice in the same run (C and H1 are identical); and the one bypass, H2, is a switch the case traced from the source, read off the code's own info line and an output 10 × the budget, with its control H1 beside it. The README lists "confirms a bypass" as a reason for run 2, so this was weighed: H2 was seen once, at one `pct` (0.1); the same arm came out the same way in the 2026-10-07 shakedown, which is not counted as evidence here. If the verdict is to be challenged, the cheapest independent check is H2 and H1 again by a fresh session with `cluster-run.py f01`.

## 6. Run 2 — fresh AI session (optional)

Not done (§5.2).

## 7. Comparison — only if run 2 was done

Not applicable.

## 8. Verdict — AI

| Tier | Verdict | Basis | Date |
|---|---|---|---|
| Unit | **Confirmed** — the check's arithmetic exact at `pct` 0.95 · 0.5 · 0.1 · 0.01 and the ladder 1 · 3 · 6 · 8 passes (n = 0 · 2 · 5 · abort) at `B / total` 1.5 · 0.8 · 0.4 · 0.1; upstream `DirectoriesTest`, `CompactionsBytemanTest`, `PartialCompactionsTest` pass | run 1 + self-check | 2026-10-07 |
| Cluster | **Confirmed** — n = 0 · 0 · 2 · 5 · abort at 0.95 · 1.5 · 0.8 · 0.4 · 0.1 and the in-flight arm n = 5 against 0; **H1 as predicted** (the hatch does not cover `nodetool compact`); **H2 bypass as recorded** (a background compaction wrote 10 × the budget with the check off) | run 1 + self-check | 2026-10-07 |

§9a's hash at the freeze: `f17dad5a37c09c67cd9b61f61d6de22108f881e4`; re-computed after run 1 and after the case file's edits of this session: identical. §9's hash moved from `86dddb531b2f29e2a2a6ac022a0eb6d334cf4384` to `1937f1366fb64fbfd83ba0860fdf653b099d5836` by the documentation-only edit of its "Run so far" line. **Feedback filed:** the case file's §10 "Stage-4 feedback" (with the run's figures), a dated amendment at the end of §8 (the hatch's reach, observed) and a note in the Target-3 field, the "Run so far" line of §9, and §10 Notes (the over-estimate and the `ERROR` line format); recommendation 8 of the audit is settled by these observations and §6b is not changed; the state rows of `HANDOFF.md`. Not committed.
