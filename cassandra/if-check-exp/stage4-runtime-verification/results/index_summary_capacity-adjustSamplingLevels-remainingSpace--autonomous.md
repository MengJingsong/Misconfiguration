# index_summary_capacity-adjustSamplingLevels-remainingSpace--autonomous — stage-4 results  <!-- file: results/index_summary_capacity-adjustSamplingLevels-remainingSpace--autonomous.md -->

> **Case:** [`index_summary_capacity-adjustSamplingLevels-remainingSpace--autonomous`](../../stage3-ai-deep-read/cases/index_summary_capacity-adjustSamplingLevels-remainingSpace--autonomous.md)
>
> **Status:** **Closed 2026-10-21 — unit Confirmed (caps), cluster Confirmed — caps only on some paths (bypass)** (estimate positive
> 
> **Outcome class:** true positive — stage-3 estimate vs the stage-4 effect on the constraint
> with bypasses, matched). The operand of line 258 equals `pool − Σ planned floor` to the byte at both tiers (unit: `P − N·F'` for
> five pools; node: `C·2^20 − ΣF' − 316 B` at six capacities), negative only below the floor sum (C = 8 MiB: −7,439,403 B, branch not
> taken, usage 15.09 MiB). After each run the summaries are 1930.2 / 972.7 / 493.9 / 398.1 / 15.1 / 15.1 MiB at 4096 / 1024 / 512 /
> auto (409) / 64 / 8 MiB, every value of B3f, and RssAnon falls by the same bytes (within 0.3 %). Bypass (a): 1930 MiB under a 64 MiB
> cap with no run. No runbook defect in run 1; self-check 109/109; no run 2.
>
> **Agent:** autonomous. "§9a" below means each tier's predictions and conclusions table: B2f and B2g (unit), B3f and B3g
> (cluster); "§9b–§9e" means B2a–B2e or B3a–B3e; the case file's feedback section is its section D. One results file per case file.

## 1. Before run 1 — design audit and freeze

| Field | Content |
|---|---|
| **Case-file version** | Autonomous file, untracked (repo HEAD `d36d737`). As filed: sha256 `b57c9c6b6804ad8e6d023ddedaebccf9bb5b622494a9b46ebb7944f69a28693c`. After the step-0 audit amendments R1–R8 (dated 2026-10-21, in the file next to the text they change): **`fd6885707e04499847f692c40abd7e537db95b34964aec164fb53c0d1b95c1d1`** — the audit freeze; **both tiers ran on this version**. After section D (run-1 feedback): **`49ad542e67dd2a23729efc24beda729148c5506cdc04b25937e0840ee07b7031`** (for `_INDEX.md` §4). |
| **Harness** | [`harness/index_summary_capacity-adjustSamplingLevels-remainingSpace--autonomous/`](../harness/index_summary_capacity-adjustSamplingLevels-remainingSpace--autonomous/README.md), written 2026-10-21, not committed: `IndexSummaryCapacityProbeTest.java`, `unit-run.sh`, `unit-analyze.py` (B2); `r258.btm.in`, `cluster-run.py`, `cluster-analyze.py` (B3); `selfcheck.py`. md5 of the node copy in `pc12:~/stage4-harness-run/is2.md5`, equal to the repo files. **Instrument checks (not readings):** shakedown1 (unit, 1,000 partitions: test compiles, both operand readers agree, `probe.out` whole; found H1 in the analyzer); shakedown2 (cluster, 20 × 10,000 partitions: `sjk mx -ms/-mg/-mc` forms work, the Byteman rule fires once per run and reads `pool − ΣF'` to the byte, the restore force-upsamples back to full, sampler, analyzer). |
| **Tiers and values** | Unit (B2): pool P0–P4 in bytes (N·F/2, N·F + (S−F)/2, N·F + 3.5(S−F), N·F + 7.5(S−F), N·S + 1024) after a pool-0 run, zero read rates, repeated once. Cluster (B3): `index_summary_capacity` 64 MiB (load and baseline, no run) → 4096 · 1024 · 512 · 64 · 8 MiB over JMX, each followed by a restore; negative control (64, 300 s, no run); auto default (yaml empty → 409 MiB) in a second lifetime. |
| **Audit bottom line** | **Ready after amendments** — 2026-10-21 |

### 1.1 Design audit

Source spot-checks were made in the shared clone read-only (`cassandra-5.0.9`, `b5f2a54210`) and run against the node's fresh clone `pc12:~/cassandra-is2`.

**What this file tests that the `:341` run did not.** The `:341` file
([results](index_summary_capacity-distributeRemainingSpace-extraSpaceRequired--autonomous.md), Confirmed — caps only on some paths)
tested the inner check (`extraSpaceRequired <= remainingSpace`) through kept counts and totals, with node restarts between values.
This file targets the outer gate `if (remainingSpace > 0)` at `:258`: it reads the operand itself (two readers at unit level, a
Byteman line rule on the node), predicts it to the byte, and separates "branch taken, nothing fits" (P1, C = 64) from "branch not
taken" (P0, C = 8); it changes the capacity at run time over JMX in one lifetime, and uses a different geometry (1000-byte text keys,
20 equal sstables of 96.5 MiB, intervals 1/2048; unit 10 × 1,250 entries). The overlap (same constraint, zero-read path, auto default,
floor overshoot, between-runs bypass) is noted in the case file's section D.

| Group | Check | Rating | Note (section checked) |
|---|---|---|---|
| A. Core question | constrained quantity is memory or disk bytes | Met | A2/B1: native (JNA malloc) bytes of BIG index summaries, `IndexSummary.getOffHeapSize()`. |
| A. Core question | knob varied, ≥ 3 values incl. default — or another approach | Met | Unit: five pools in bytes plus 0. Cluster: 4096 / 1024 / 512 / 64 / 8 and the auto default (B3b, B3e step 6). |
| A. Core question | real resource measured, not only the counter (gap named) | Partly → Met | Unit: operand and planned total only (named, B2d). Cluster: B3d used VmRSS, which includes mmapped `Index.db` pages read by every upsample (`disk_access_mode: mmap_index_only`, `Config.java:122`); **R6** reads RssAnon with a 2-s sampler. NMT blindness to JNA named in B3d. |
| A. Core question | usage driven to the limit and past it | Met | Unit pools from N·F/2 to N·S + 1024; cluster 1930 MiB of summaries against caps from 8 to 4096 MiB. |
| A. Core question | positive control (negative-estimate file only) | n/a | Positive estimate; the file still has one (P4 vs P1; C = 4096 vs 64). |
| B. Logic | each step says what it establishes | Met | B2h, B3h. |
| B. Logic | prediction stated in numbers or a clear relation | Partly → Met | B2f/B3f tables in numbers; the operand was "≈" — **R3** makes it exact at unit level (`R = P − N·F'`), **R8** at cluster level (`C·2^20 − ΣF' − ε`, sign per C) and defines every "≈". |
| B. Logic | every plausible outcome has a conclusions row | Partly → Met | Missing: operand readers disagree, repeat differs, restore fails, negative control moves, sstable set changes, operand sign wrong on the node; no verdict words or Effect (**R3**, **R8**). |
| B. Logic | confirmation needs ceiling-follows-knob and direct disallow evidence | Partly → Met | Unit: operand read directly (B2d). Cluster: only aggregate INFO lines; **R6** adds the Byteman operand at `:258` and the TRACE keep / re-sample lines (`:343`, `:278`). |
| B. Logic | alternative explanations and their controls | Met | Positive and negative controls, reset check, same data, no compaction, zero reads, format check (B2h, B3h). |
| C. Specific | a human can follow it from the intro and §9a | Met | Header, A3, B1. |
| C. Specific | an AI can run the runbook without re-deriving the code path | Partly | Two steps cannot run as written, both derivable from source: the unit reset with zero read rates (**R2**) and the cluster restore at cap 8192 (**R7**): with zero reads the target is 1 entry (`:183-188`), an upsample needs `target ≥ 1.5 × current` (`:235`). |
| C. Specific | knob, values, workload, commands, observables, sampling, stop conditions exact | Partly | `seq()` key population repeats keys (**R5**, the `:341` D1); the load lifetime's cap unstated (**R5**: 64 MiB); `sjk` syntax unverified (**R6** item 5, checked in step 1: `-ms -f … -v …`, `-mg -f …`, `-mc -op …` all work); paths, ports, `ulimit` (**R4**); stdout fragmentation (**R1**). |
| D. Runnable | harness and environment prerequisites exist or are listed | Met | Unit test given in outline (written in step 1); cluster run script, sampler and Byteman rule written in step 1. Fresh clone `~/cassandra-is2` built (`ant build-test` 1 min 11 s). |
| D. Runnable | workload arithmetic reaches the limit (data, time, disk, memory) | Met | Unit: S = 1,250 × 20 = 25,000 B, F = 40 × 20 = 800 B. Cluster: 2,000,000 × 1012 B = 1930.2 MiB, floor 782 entries per sstable → ΣF' = 15.1 MiB; disk ≈ 7 GB peak of 55 GB free; memory 8 GiB heap + 2 GiB native of 251 GiB; ≈ 32 min. |
| D. Runnable | load-bearing citations spot-checked against the pinned clone | Met | `IndexSummaryRedistribution.java:69` (`volatile long remainingSpace`), `:138, :145, :163, :173, :183-188, :215-254, :258, :260, :327-356, :360`; `IndexSummaryManager.java:105-109, :184-187, :239-250, :286-289`; `IndexSummaryManagerMBean.java`; `IndexSummaryBuilder.java:294, :299`; `DatabaseDescriptor.java:866-873`; `IndexSummaryManagerTest.java:154-167`; `conf/cassandra.yaml:939, :947`; `cassandra-env.sh:307` (`JVM_EXTRA_OPTS`); stress `Strings.generate` (ASCII). All as cited. |

| # | Recommendation | Applied? | Why |
|---|---|---|---|
| R1 | Node clone `~/cassandra-is2`; whole `PROBE` lines to `-Dprobe.out`; 5.0.9 flush API; repeat run | Applied 2026-10-21 (B2a) | environment; fragmented test stdout |
| R2 | Unit reset sets read meters to 100 before the large pool, as `resetSummaries` does | Applied 2026-10-21 (B2c) | zero rates cannot upsample (`:183-188`, `:235`) |
| R3 | Exact operand prediction `R = P − N·F'`, k, T; rows for reader disagreement, operand mismatch, repeat; verdict mapping and Effect | Applied 2026-10-21 (B2g) | "≈" not falsifiable; outcomes without rows |
| R4 | `pc12` environment: paths `~/stage4-is2`, ports 17000/17001/19042/17199, heap by `MAX_HEAP_SIZE`, `MALLOC_MMAP_THRESHOLD_`, `ulimit`, node detection | Applied 2026-10-21 (B3a) | node facts, no design change |
| R5 | Remove `population: seq()` from `pk`; stress port options; load-lifetime cap 64 MiB | Applied 2026-10-21 (B3c) | repeated keys (`:341` D1); unstated value |
| R6 | RssAnon (2-s sampler); Byteman operand at `:258`; TRACE keep / re-sample lines; per-run log offsets; `sjk` check | Applied 2026-10-21 (B3d) | VmRSS includes mmapped `Index.db`; direct evidence for the gate |
| R7 | Restore by forced upsample (ALTER min = max = 1, run at 8192, ALTER back to 1/2048), also before the auto restart; fixed order and RSS windows | Applied 2026-10-21 (B3e) | cap 8192 cannot upsample under zero reads |
| R8 | Terms (S, F', "≈", "≤ C", RSS tolerance max(0.15ΔT, 64 MiB)); operand prediction per C; rows; verdict mapping and Effect | Applied 2026-10-21 (B3g) | ambiguous terms; outcomes without rows |
| S1 | Raising `index_summary_capacity` never re-grows the summaries of unread sstables (the same `:235` fact as R7) | Left for stage 3 | a consequence worth stating in A3; from source, not run as an arm |
| S2 | A3's "zero reads → NaN → target 1" holds; but B2c/B3e didn't follow it through to the reset/restore | Left for stage 3 | R2/R7 fixed the runbook |

**Agreement criteria** — only if run 2 is chosen (it was not).

## 2. Environment

| Field | Run 1 | Run 2 |
|---|---|---|
| Date | 2026-10-21 (MDT): unit shakedown 20:49, **unit run 1 20:51–20:52**; cluster shakedown 20:53–21:20; **cluster run 1 21:20:05–21:52** | not done |
| Node | `pc12` = `node1.jason92-320876.misconfiguration-pg0.cloudlab.umass.edu` (40 cores, 251 GiB), used by this session only, driven from `pc07` over ssh; loopback 127.0.0.1 only (no LAN interface); ports 17000/17001/19042/17199 | — |
| OS and kernel | Ubuntu 22.04.2 LTS, `5.15.0-187-generic` | — |
| JDK | openjdk 11.0.32.1 (2026-08-18) | — |
| Ant | 1.10.12 | — |
| Local clone | `pc12:~/cassandra-is2`, fresh clone of `cassandra-5.0.9` (`b5f2a54210d541339c2e7c17a794195cac0e67c2`), `ant build-test` 1 min 11 s; only untracked file during the unit tier: the harness test (removed afterwards) | — |
| Case-file / harness commit | case file untracked (HEAD `d36d737`), both tiers on `fd688570…`; harness not committed (md5 in `pc12:~/stage4-harness-run/is2.md5`) | — |
| Storage for node data | `~/stage4-is2` on local `/dev/sda3` (55 GB free at the start; peak use ≈ 7 GB); data removed after the run | — |
| Node JVM | `MAX_HEAP_SIZE=8G HEAP_NEWSIZE=2G` (`-Xms8G -Xmx8G`), G1, `-XX:+AlwaysPreTouch`, `MALLOC_MMAP_THRESHOLD_=131072`, no jemalloc (0 mappings), Byteman 4.0.20 agent on the node only, `ulimit -n 100000` | — |
| Full logs | `pc12:~/stage4-logs/is2/`: `run1/unit/` (ant logs, junit XML, per-test logs, `rep{1,2}.probe`, `summary.txt`), `run1/cluster/` (`session.log`, `phases.json`, `rss-*.csv`, `system-*.log`, `isr-trace-*.log`, `r258-*.log`, `stress-load*.out`, `summary.txt`, `selfcheck.txt`), `shakedown1/`, `shakedown2/`, `build-test.log`, `clone.log` | — |

## 3. Runbook defects

| # | Run | Step | Problem | Fix | Decision (date) | Case-file commit with the fix |
|---|---|---|---|---|---|---|
| H1 | unit shakedown1 (instrument check) | harness | `unit-analyze.py` required text after `PROBE done` and returned "Invalid (rep1 incomplete)" on a complete run. | Regex accepts a bare tag. | 2026-10-21, harness only | — |

Run 1 met no step it could not execute as written. The design's two unrunnable steps (B2c reset, B3e restore) and the stress key
population were found by the audit from source, before any reading, and fixed as amendments R2, R7 and R5 (§1.1).

## 4. Run 1

**Scope:** unit tier (B2, 10 × 10,000 partitions, rep1 + repeat) and cluster tier (B3, lifetimes L0-main and L1-auto) on case-file
version `fd688570…`. **Command logs:** `index_summary_capacity-adjustSamplingLevels-remainingSpace--autonomous/run1/unit/summary.txt`
and `…/run1/cluster/session-excerpt.txt` (full `session.log` on the node). Excerpts in `run1/`.

### 4.1 Readings

**Unit tier** (`run1/unit/rep1.probe`, `rep2.probe`, `summary.txt`). Setup: S = 25,000 B (1,250 entries × 20 B), F' = F = 800 B
(40 entries), exactly as B2c.

| Test or assertion | Result | Evidence |
|---|---|---|
| junit, both runs | 1 test, 0 failures, 0 errors (18 s, 17 s) | `summary.txt` |
| Pool 0 | R = −8,000 (both readers) = −N·F'; T = 8,000; all levels 4 | `rep1.probe` |
| P0 = 4,000 | R = −4,000 (both readers, = P − N·F'); branch not taken; k = 0; T = 8,000 > P0 (floor overshoot) | `rep1.probe` |
| P1 = 20,100 | R = +12,100; branch taken; k = 0; T = 8,000 ≤ P1 | `rep1.probe` |
| P2 = 92,700 | R = +84,700; k = 3; T = 80,600 ≤ P2 | `rep1.probe` |
| P3 = 189,500 | R = +181,500; k = 7; T = 177,400 ≤ P3 | `rep1.probe` |
| P4 = 251,024 | R = +243,024; k = 10; T = 250,000 = N·S | `rep1.probe` |
| Reset check | every P started at T = 250,000 = N·S (all levels 128) | `rep1.probe` (`tBefore`) |
| Positive control | T(P4) − T(P1) = 242,000 = N·(S − F) | `summary.txt` |
| Repeat | rep2 identical to rep1, byte for byte | `summary.txt` |

**Cluster tier** (`run1/cluster/summary.txt`, `resize-lines.txt`, `r258-*.log`, `phases.json`). S = 101,200,000 B (96.512 MiB) =
100,000 × 1012 B; F' = 791,384 B; ΣF' = 15.094 MiB; system tables' summaries 316 B. T = "Completed resizing" (= JMX
`MemoryPoolSizeInMB`); R_b/R_a = RssAnon median 30 s before the trigger / 30–70 s after the run; R258 = Byteman `remainingSpace` at
`:258`; keep / re-sample = TRACE lines for `isr/t-`.

| Capacity | Observable | Reading | Evidence |
|---|---|---|---|
| load | stress, sstables | 20 × 100,000 partitions, 0 errors; 20 `-big-` sstables; `tablestats` isr 2,024,000,000 B | `session-excerpt.txt`, `phases.json` |
| 64 (yaml), no run | baseline | pool line 64 MB, interval −1; T = 1930.237 MiB; 0 "Completed resizing" lines; RssAnon 11062.2 MiB | `resize-lines.txt`, `phases.json` |
| 4096 | T / R258 / keep | 1930.237 (unchanged); R258 = +4,279,139,300; 20 kept / 0 re-sampled; R_b − R_a = −0.5 MiB | `summary.txt` |
| 1024 | T / R258 / keep / RSS | **972.666** (pred 972.666, k = 10); R258 = +1,057,913,813; 10 / 10; RssAnon fall 957.6 vs ΔT 957.6 | `summary.txt` |
| 512 | same | **493.880** (k = 5); R258 = +521,042,886; 5 / 15; fall 1436.6 vs 1436.4 | `summary.txt` |
| auto (L1, pool line **409 MB**) | same | **398.123** (k = 4); R258 = +413,039,412; 4 / 16; fall 1528.4 vs 1532.1 | `summary.txt` |
| 64 | same | **15.095** (k = 0); R258 = **+51,280,868** (branch taken, nothing fits); 0 / 20; fall 1910.9 vs 1915.1 | `summary.txt`, `r258-L0-main.log` |
| 8 | same | **15.095 > 8** (floor overshoot, 1.9 × C); R258 = **−7,439,403** (branch not taken); 0 / 20; fall 1916.7 vs 1915.1 | `summary.txt`, `r258-L0-main.log` |
| every restore (cap 8192 after ALTER min = max = 1) | T, intervals | 1930.237 MiB, all 20 isr intervals 1; force upsample 0 / 10 / 15 / 20 / 20 | `summary.txt` |
| negative control (cap 64, 300 s, no run) | T / RssAnon | 1930.237 → 1930.237; RssAnon range 0.2 MiB (σ 0.1 MiB); 0 runs; `ResizeIntervalInMinutes` −1 | `summary.txt` |
| positive control | T(4096) − T(64) | 1915.1 MiB (RssAnon 1910.9) vs 20·(S − F') = 1915.1 | `summary.txt` |
| every reading | sstables / compaction | 20 throughout; no compaction other than the redistribution | `summary.txt` |
| every state | Summary.db | total = isr summary bytes + 40,640 B (headers): 2,024,040,640 at full, 1,019,954,480 at 1024, 15,868,320 at 64/8 | `phases.json` |

R258 at every C equals `C·2^20 − ΣF' − 316 B` to within 176 B (`summary.txt`, "pred" column).

### 4.2 Conclusion and logic

1. **Validity.** Unit: both runs passed, setup equals B2c's arithmetic, every pool started from full, operand readers agree [observed:
   `run1/unit/rep1.probe`, `summary.txt`]. Cluster: 20 BIG sstables of exactly 100,000 distinct 1000-byte keys (2,024,000,000 B =
   2 M × 1012), count 20 at every reading, no compaction, zero read traffic, every restore back to 1930.237 MiB with all intervals 1,
   heap fixed and pre-touched, no jemalloc, the Byteman agent loaded on the node only [observed: `run1/cluster/summary.txt`,
   `session-excerpt.txt`, `phases.json`]. The limit was reached and passed: 1930 MiB of summaries against caps 1024 → 8 MiB. Valid.
2. **Readings.** Nothing contradicts. RssAnon was flat to 0.2 MiB with no run, so every fall is far outside noise. The 4096 run changed
   nothing, as predicted (all summaries fit) [observed: `summary.txt`].
3. **Matched row.** Unit B2g row 1, "T ≤ P for P1–P4, k matches `floor(R/(S−F))`, k increases P1<P2<P3<P4 — Claim confirmed", with row 4
   (P0: R < 0, k = 0, T = N·F > P0), the positive control, both operand readers agreeing, R = P − N·F' exactly and an identical repeat:
   **Confirmed** by R3's mapping [observed: `rep1.probe`, `rep2.probe`]. Cluster B3g row 1, "After each run, MemoryPoolSizeInMB ≤ C for
   all C ≥ 64 and ≈ the predicted k-step values; RSS falls by ≈ the same delta": T ≤ C at 4096 / 1024 / 512 / auto / 64, each equal to
   ΣF + k·(S−F) + ε to 0.001 MiB with k = 20 / 10 / 5 / 4 / 0; RssAnon falls within 4.2 MiB of ΔT; plus the C = 8 row (T ≈ 15 MiB > 8),
   the baseline row (1930 MiB > 64 with no run), R258's sign as predicted at every C, positive control 1915 MiB, negative control flat,
   restores holding: **Confirmed** by R8's mapping, Effect `caps only on some paths (bypass)` [observed: `summary.txt`].
4. **Excluded rows.** Unit row 2 (T > P for P ≥ N·F): largest T − P is −1,024 (P4) [observed]. Row 3 (k = 0 at P2/P3 with R > 0): k = 3,
   7. Row 5 (T identical): T takes 3 values. Row 6 (positive control): moved 242,000. R3 rows: readers agree, R exact, rep2 identical.
   Cluster row 2 (T > C + 1 for C ≥ 64): largest T − C is −10.9 MiB (auto). Row 3 (RSS does not follow): every |fall − ΔT| ≤ 4.2 MiB.
   Row 6 ("downsample: 0" everywhere): 10 / 15 / 16 / 20 / 20. Row 7 (positive control): moved. R8 mechanism row (R258 ≤ 0 with a keep,
   R258 > 0 at C = 8, R258 ≥ S − F' with no keep): none — at 4096 / 1024 / 512 / auto R258 ≥ S − F' and keeps = k > 0; at 64 R258 = 48.9 MiB
   < S − F' = 95.8 MiB with no keep; at 8 R258 < 0 with no keep. Restore row: all five restored. Negative-control row: flat. Invalid row:
   count 20, BIG, no compaction. Auto pool line: 409 [observed: `summary.txt`, `r258-*.log`, `resize-lines.txt`].
5. **Observed vs. inferred.** Inferred: (a) that the RssAnon falls are the freed summary memory — [inferred: the falls equal ΔT within
   0.3 % at five capacities, each restore reverses them by the same amount (e.g. +1915.1 MiB → +1912.1 RssAnon), and with no run RssAnon
   moved 0.2 MiB]; (b) that the Byteman line `AT LINE 258` reads the operand at the `if` — [inferred from source: `:258` is
   `if (remainingSpace > 0)`, the field is not written between `:251` and `:258`, and at unit level the same value read after the run
   (the field is not touched after `:258`, `:260` passes a copy) equals `P − N·F'` exactly]; (c) TRACE "Using leftover space to keep"
   lines are the `:341` true branch inside `:258` [inferred from source: message at `:343`].
6. **Deviations and gaps.** Paths, ports, the RSS reading and the restore differ from the file as filed, all by dated amendment before
   any reading. Only the zero-read path is exercised (the file's design): the proportional targets are untested here. One node on
   loopback (single node; no effect). The second RSS reader in the self-check reads the same `/proc` source at different moments, not an
   independent mechanism.
7. **Core question.** The hypothesis (B1): after a redistribution the BIG summaries' total, and the node's native memory, is at most
   `index_summary_capacity` above the floor sum, with line 258 spending exactly the positive leftover. The unit tier shows line 258's
   operand is exactly `pool − planned floor sum`, the branch is skipped only when that is ≤ 0, and the total lands at `N·F + k·(S−F) ≤ P`
   (parts 1, 3). The node shows the same operand to the byte, a total that follows the cap step by step from 1930 to 15 MiB, and RssAnon
   falling by the same bytes (parts 3, 4). It does not cap at write time (1930 MiB under a 64 MiB cap with no run) or below the floor
   sum (15 MiB at 8 MiB) (parts 3, 4). **Usage follows the constraint, and the constraint caps it at each redistribution, down to the floor.**

**Conclusion (one line):** unit B2g row 1 (+ row 4) — **confirmed**; cluster B3g row 1 (+ C = 8 row, baseline row) — **confirmed**,
bypass as recorded (between runs; below the floor).

## 5. Self-check of run 1 — AI

`selfcheck.py` (`run1/selfcheck.py`, output `run1/cluster/selfcheck.txt`) re-parses the raw files: the `PROBE` lines of the ant log
against `probe.out`; the B2b/B2f values typed in from the case file (S = 25,000, F = 800, k = 0/0/3/7/10) rather than taken from the
test; per lifetime, every Beginning / Completed line of `system-<life>.log` in order, the R258 lines, the TRACE file split per run, the
2-s RssAnon csv at the trigger and post-run windows, the 20 stress outputs and `session.log`; and the B3f table's k typed in.
**109 / 109 checks hold.**

| Part | Holds? | Note (file re-read) |
|---|---|---|
| 1. Validity | yes | stress 20 × 100,000, 0 errors; first `tablestats` 2,024,000,000 B = 2 M × 1012 (distinct keys); run order 4096, 8192, 1024, 8192, 512, 8192, 64, 8192, 8, 8192 then 409; pool lines 64 MB and 409 MB; each C run began at the full 1930.237 — `system-*.log`, `stress-load*.out`, `session.log` |
| 2. Readings | yes | every Completed T equals `phases.json`; one R258 line per run with the matching pool; 2-s sampler within 0.1 MiB of the script's R_b/R_a everywhere |
| 3. Matched row | yes | unit: all five P equal B2b, R = P − 8,000 by both readers, k and T equal the typed table; cluster: T ≤ C + 1 for C ≥ 64 from the raw lines, keep(isr) = the B3f table's k at every C, restores back to full |
| 4. Excluded rows | yes | R258 sign per C and no keep line where R258 ≤ 0; every RssAnon fall within max(0.15ΔT, 64) of ΔT by the second reader; negative-control window range 0.2 MiB over 145 samples |
| 5. Observed vs. inferred | yes | (a) restores re-read: each reverses its fall (−957.8 / −1436.9 / −1912.1 / −1916.0 MiB vs ΔT); (b) `:258` text and the field's writes re-read in the pinned source; (c) `:343` message text re-read |
| 6. Deviations and gaps | yes | every deviation is a dated amendment made before the run (sha `fd688570…` recorded before run 1); the second RSS reader's dependence on `/proc` noted |
| 7. Core question | yes | B1 → B2g/B3g → R3/R8 mapping; the Effect follows R8's pre-run rule (Confirmed + baseline bypass + C = 8 overshoot → `caps only on some paths (bypass)`) |

### 5.2 Run 2?

**No** — 2026-10-21. The conclusion rests on observed readings that equal byte-exact predictions at both tiers; the unit tier is
deterministic (identical repeat); the cluster readings were also seen in the shakedown at a tenth of the scale (the same relations, its
C = 8 lying above its smaller floor sum).

## 6. Run 2 — fresh AI session (optional)

Not done.

## 8. Verdict — AI

**Stage-3 estimate:** positive, with qualifications (periodic, best-effort; floor; write-time bypass).

**Claim tested (B1):** for BIG sstables, once a redistribution has completed, the total off-heap index-summary size is ≤
`index_summary_capacity` and rises and falls with it, provided the capacity exceeds the floor sum; line 258 spends exactly the positive
leftover `remainingSpace` on keeping whole summaries at full level; below the floor sum, or before a redistribution, usage is not capped.

| Tier | Verdict | Effect on the constraint | Basis | Date |
|---|---|---|---|---|
| Unit | **Confirmed** — B2g row 1 (+ row 4; R3 rows; controls; identical repeat) | caps | run 1 + self-check | 2026-10-21 |
| Cluster | **Confirmed** — B3g row 1 (+ C = 8 row, baseline row; R8 rows) | **caps only on some paths (bypass)**: caps at each redistribution down to the floor (1930 → 973 / 494 / 398 / 15 MiB at 1024 / 512 / 409 / 64 MiB, RssAnon by the same bytes); new sstables are not capped between runs (1930 MiB under a 64 MiB cap with no run); below the floor sum it overshoots (15.1 MiB at 8 MiB, line 258 false) | run 1 + self-check | 2026-10-21 |

**Feedback filed:** the case file's section D (2026-10-21; not committed); after it the case file's sha256 is
`49ad542e67dd2a23729efc24beda729148c5506cdc04b25937e0840ee07b7031` (for `_INDEX.md` §4). The amendments R1–R8 are dated in the file.
