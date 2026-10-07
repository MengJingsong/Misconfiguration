# max_space_usable_for_compactions_in_percentage-hasDiskSpaceForCompactionsAndStreams-availableForCompaction — stage-4 results

> **Case:** [`max_space_usable_for_compactions_in_percentage-hasDiskSpaceForCompactionsAndStreams-availableForCompaction`](../../../stage3-ai-deep-read/long-path/cases/max_space_usable_for_compactions_in_percentage-hasDiskSpaceForCompactionsAndStreams-availableForCompaction.md)
>
> **Status:** audited and frozen 2026-10-07; harness written and instrument-checked; **run 1 not started**
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
| Date | not yet run | |
| Node (CloudLab name and type) | `pc66` (`node0.jason92-317394…`), 40 cores, 125 GiB; `pc80` did not answer ssh on 2026-10-07 (connection timed out) | |
| OS and kernel (`uname -r`) | Ubuntu 22.04.2, 5.15.0-187-generic | |
| JDK (`java -version`) | openjdk 11.0.32.1 | |
| Ant (`ant -version`) | Apache Ant 1.10.12 | |
| Local `cassandra-src` clone commit | `~/cassandra-run1` at `b5f2a54210` (`cassandra-5.0.9`) | |
| Case-file commit / harness commit | not committed | |
| Storage for node data | a 4 GiB sparse file `~/stage4-data.img` on the local disk (`/dev/sda3`), loop-mounted ext4 at `/mnt/stage4-data` | |
| Full logs (path, outside the repo) | `pc66:~/stage4-logs/mscp/` | |

## 3. Runbook defects

Instrument checks before run 1 (2026-10-07, `pc66`). They are **not readings of run 1**: their logs are kept under `~/stage4-logs/mscp/unit-instrument*/` and `~/stage4-logs/mscp/<label>.<timestamp>/`, §9a was frozen before the first cluster one, and run 1 repeats the tiers from the beginning.

| # | Run | Step (§9b–§9e) | Problem | Fix | Decision (date) | Case-file commit with the fix |
|---|---|---|---|---|---|---|
| 1 | unit instrument 1 | 9e unit step 3 (`CompactionLadderTest`) | `CompactionManager.instance.disableAutoCompaction()` reaches only the tables that exist when it is called; the test's table is re-created afterwards, so size-tiered compaction merged four of the eight flushes (sizes 1.2 and 4.8 MB, 5 live SSTables) and 18 checks recorded `MISMATCH` from the second value on. The first value (n = 0) matched in full | `cfs.disableAutoCompaction()` on the re-created table and at the start of every value | 2026-10-07; harness only (§9a unchanged); the instrument run was repeated (instrument 2: 0 `MISMATCH`) | with this file |

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

Not started. **Plan:** unit tier (`unit-run.sh`, no suffix) then the six cluster labels in the order `d95`, `f15`, `f08`, `f04`, `f01`, `inflight`, each in the background and each from a fresh filesystem; then the analysis and the self-check below. The shakedown directories on the node are kept; run 1's use the same label names, so the script moves an existing directory aside (`<label>.<timestamp>`) before it starts.

## 5. Self-check of run 1 — AI

Not done (no run 1 yet).

## 6. Run 2 — fresh AI session (optional)

Not done.

## 7. Comparison — only if run 2 was done

Not applicable.

## 8. Verdict — AI

No verdict yet. (The instrument checks above are not a verdict: they were taken to prove the instruments, and they came out as the amended §9a predicts; run 1 repeats the tiers from the beginning on the frozen text.)
