# sasi-max_term_size-TrieMemIndex-add-termSize--autonomous — stage-4 results  <!-- file: results/sasi-max_term_size-TrieMemIndex-add-termSize--autonomous.md; the stem ends in --guided or --autonomous -->

> **Case:** [`sasi-max_term_size-TrieMemIndex-add-termSize--autonomous`](../../stage3-ai-deep-read/cases/sasi-max_term_size-TrieMemIndex-add-termSize--autonomous.md)
>
> **Status:** self-checked; verdict filed (2026-10-26)
>
> **Outcome class:** true negative — the stage-3 estimate (negative) against the effect found below (does not cap) ([definition](../README.md#outcome-class))
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
| **Case-file version** | Case file untracked at audit time (committed by the orchestrator). Original sha256 as filed: `a10b48fe3245bb78e3ea1135db3e881e1ac09eb33b80b29c409bd75a0977bd34`. **sha256 after the audit's amendments (frozen, before the section D feedback): `58c8a4fb005364174c5d495ef4bb2b0e82e95072f23f41e7869e9246f67bf157`.**  Final sha256 after the section D feedback (2026-10-26): `be46f7bb565431c48743d2f4403c2e0ccaade568cb0d34beed46be9d5a93ecc5`. Frozen tables, written before any reading: B2f-g (from `**B2f.` to before `**B2h.`) sha256 `749767666922b15b8cd33ad994221b12b71fce780cfa573070e190e95f35b776`; B3f-g (from `**B3f.` to before `**B3h.`) sha256 `018a26051ab89310e524454e7c7d5353ff18ae9311818270d2eaac0c50887bc8` (each by `sed -n '/^\*\*B2f\./,/^\*\*B2h\./{/^\*\*B2h\./!p}' <file> | sha256sum`, and the B3 analogue). The amendments are B5.1 to B5.9 in the case file; the B2f/B3f brackets and flush-point numbers were derived from the source, before any reading. |
| **Harness** | `harness/sasi-max_term_size-TrieMemIndex-add-termSize--autonomous/` (written before run 1; committed by the orchestrator) |
| **Tiers and values** | Unit: PREFIX and CONTAINS, term length {1,100,512,1022,1023,1024,1025,4096} with N per B2c; SkipList (int) control. Cluster: 1024 build CONTAINS at 1023 chars (`memtable_heap_space` 256 and 128 MiB), 1024 chars (rejected), index dropped, PREFIX 1023; 256 build at 255 chars and 4096 build at 4095 chars (CONTAINS); node heap 2 GiB, load to three memtable switches. |
| **Audit bottom line** | **Ready after amendments** — 2026-10-25 |

### 1.1 Design audit

The requirements are in the README, "Step 0 — the design audit". One row per
line of each group; cite the case-file section checked.

| Group | Check | Rating (Met / Partly / Not met) | Note (section checked) |
|---|---|---|---|
| A. Core question | constrained quantity is memory or disk bytes | Met | A2: heap bytes of the SASI memtable index (the estimate returned by `TrieMemIndex.add`, fed to `markExtraOnHeapUsed`, `SASIIndex.java:318-321`, `AbstractAllocatorMemtable.java:194-197`); the compared quantity is bytes of one term (`TrieMemIndex.java:84`). |
| A. Core question | knob varied, ≥ 3 values incl. default — or another approach, with the reason | Met | A1: the constant is a `static final int` (`OnDiskIndexBuilder.java:128`), so it is varied by three builds (256/1024/4096, B3b) and, at the unit tier, by the term length around 1024 (8 values). The edit is made before the first build (B5.5) because `javac` inlines it. |
| A. Core question | real resource measured, not only the counter (gap named) | Partly | B2d(3)/B3d: the estimate is a counter; the real resource is the live heap (`System.gc()` deltas in the unit JVM; `GC.class_histogram` total in the node), compared with the tracked on-heap size; the gap is named in B2d. Instruments made exact in B5.7. |
| A. Core question | usage driven to the limit and past it | Met | B2b/B3b: L=1022, 1023 (at the limit) and 1024, 1025, 4096 (past it); the pool trigger (85.3 MiB) is reached in at most about 260 CONTAINS rows (B3c as amended, B5.4). |
| B. Logic | each step says what it establishes | Met | B2e/B3e with the B2g/B3g rows. |
| B. Logic | prediction stated in numbers or a clear relation | Partly | B2f gave per-term sizes without derivation and a CONTAINS lower end (0.5 MB) below the leaf-edge floor of L x L = 1.05 MB; B3f had no numeric flush point. Fixed by B5.3 and B5.4 (brackets and 85.3 / 42.7 MiB, from `MemtablePool.java:125-149` and `DatabaseDescriptor.java:753-763`). |
| B. Logic | every plausible outcome has a conclusions row with its evidence | Met | B2g/B3g cover confirm, refute by per-term cap, plateau, boundary misread, flat-with-control, limit not reached; counter-capped-but-real-grows is covered by the heap column and the "index dropped" row. |
| B. Logic | confirmation needs ceiling-follows-knob and direct disallow evidence | Met | Negative claim: the disallow branch fires (1024-char rows, the "Can't add term" log, no growth, B3f), growth follows N below it, and the pool trigger is unchanged across the three builds. |
| B. Logic | alternative explanations and their controls | Met | B2h and B3h: fixed seed, `analyzed=false`, index dropped, PREFIX vs CONTAINS, `memtable_heap_space` as the known-binding cap. Positive control: cluster Met (memtable pool); unit Partly (B5.6, no pool in a unit JVM). |
| C. Specific | a human can follow it from the intro and §9a | Met | Header table, A3 steps and B1. |
| C. Specific | an AI can run §9b–§9e without re-deriving the code path | Partly | Unit test construction (a `ColumnIndex` with `IndexMetadata`) is not spelled out; the sibling OnDiskIndexBuilder harness shows it; the search call named in B2d did not exist (B5.8). Supplied by the harness. |
| C. Specific | knob, values, workload, commands, observables, sampling, stop conditions exact | Partly | Row counts and N values were wrong for the 1 GiB unit JVM and for the pool trigger (B5.2, B5.4); loader, sampler and stop condition are supplied by B3c/B3d as amended and the harness. |
| D. Runnable | harness and environment prerequisites exist or are listed | Met | None exist; listed as step-1 work (test class, sampler, loader, run scripts); three trees are copied and built on pc12. |
| D. Runnable | workload arithmetic reaches the limit (data, time, disk, memory) | Partly | Unit N=100 at L=1023 CONTAINS is 100 to 500 MB of estimate in a 1 GiB JVM (B5.2); the cluster "500 to 1000 rows" would give 4 to 20 flushes (B5.4). Disk: three flushes of at most about 45 MB each on the 1024 build (about 0.5 MB per row of CONTAINS suffix terms); 44 GB free on pc12. |
| D. Runnable | load-bearing citations spot-checked against the pinned source | Partly | Re-read and correct: `TrieMemIndex.java:61-67, 74, 84, 86-94, 116, 126, 131, 134-135, 245, 272`, `MemIndex.java:45-47`, `ColumnIndex.java:103-106`, `SASIIndex.java:297, 318-321`, `AbstractAllocatorMemtable.java:194-197`, `OnDiskIndexBuilder.java:128, 167, 171`, `PerSSTableIndexWriter.java:201, 218, 247`, `SkipListMemIndex.java:35`. Wrong: `IndexMemtable.index` "drops values failing validation (lines 49-64)" (method `:45`, null/empty return `:47-48`, drop `:50-63`); `measure` "about `:262-281`" (it is `:266-282`); `IndexMemtable.java:44` (`:45`). Amended (B5.1). |

| # | Recommendation | Applied? (amendment date and commit, or "left for stage 3") | Why |
|---|---|---|---|
| 1 | Cite corrections: `IndexMemtable.java:45`, `:47-48`, `:50-63`; `measure` `:266-282`; comment `:242-244` | Applied 2026-10-25 (B5.1), commit by orchestrator | the write-up's sed showed only 49-52 because the drop is `:50-63` |
| 2 | Unit N sets for CONTAINS L=1023 (N in {1,10,30}); 1 GiB JVM | Applied 2026-10-25 (B5.2) | `build.xml:1512` |
| 3 | PREFIX 3.3-7.5 KB and CONTAINS 1.0-5 MB per-term brackets; ratio and N relations | Applied 2026-10-25 (B5.3) | node arithmetic; old CONTAINS floor below L x L |
| 4 | Replace fixed row counts by a three-switch stop with caps; flush point 85.3 / 42.7 MiB; tolerance of one row's estimate | Applied 2026-10-25 (B5.4) | cleanup threshold 1/3 |
| 5 | Edit the constant before the first build of each tree; the 4096 build may flush | Applied 2026-10-25 (B5.5) | `javac` inlines the constant; 4096 < `Short.MAX_VALUE` |
| 6 | Positive-control statement (pool in the cluster tier; unit control Partly) | Applied 2026-10-25 (B5.6) | negative-estimate rule |
| 7 | Instruments: flush log line, JMX names, histogram timing | Applied 2026-10-25 (B5.7) | real resource vs counter |
| 8 | Search call is `IndexMemtable.search(Expression)` | Applied 2026-10-25 (B5.8) | `ColumnIndex.searchMemtable` does not exist |
| 9 | `OnDiskIndexBuilder.java:171` prints `Short.MAX_VALUE` as the maximum size | left for stage 3 | cosmetic upstream inconsistency |

**Agreement criteria** — only if run 2 is chosen; filled before run 2 starts.
One row per observable in the case's §9d:

| Observable | Must match | Tolerance |
|---|---|---|
| `<observable>` | exactly / in shape | `<what counts as the same>` |

## 2. Environment

| Field | Run 1 | Run 2 (fresh AI session, if done) |
|---|---|---|
| Date | 2026-10-25 (UTC 2026-10-26 02:30 to 04:36; the session was interrupted by an API rate limit between the shakedown and the series and resumed with the node and files re-checked) | not done |
| Node (CloudLab name and type) | `pc12` (`node1.jason92-320876...`), 40 cores, 251 GiB, shared with other agents (another agent's `s4-ec` nodes were running; none of mine were) | |
| OS and kernel (`uname -r`) | Ubuntu 22.04, `5.15.0-187-generic` | |
| JDK (`java -version`) | OpenJDK 11.0.32.1 | |
| Ant (`ant -version`) | Apache Ant 1.10.12 | |
| Local source copy (from `cassandra/cassandra-5.0.9/` at repository commit …) | `~/s4-tm` (`ant build-test` 1 min 9 s; the unit tier ran with `ant testsome` in it, then the 1024 nodes ran from it with no further `ant`); `~/s4-tm-c256` and `~/s4-tm-c4096` (`ant jar`; `MAX_TERM_SIZE` edited to 256 / 4096 before the first build, confirmed in each running jar by `javap`), all by `copy-source.sh` at repository commit `1ae567d` (source clean) | |
| Case-file commit / harness commit | case file untracked at run time (sha256 in section 1); harness uncommitted (orchestrator commits) | |
| Storage for node data | local `/dev/sda3` (44 GB free before), `~/s4-tm-data/<label>` (removed after each label) | |
| Full logs (path, outside the repo) | `pc12:~/stage4-logs/tm/` (`run1-unit/`, `run1-cl/<label>/`; `shake*` and `shake*.out` are instrument checks, not readings) | |

Ports for the node: JMX 7331, native 9353, storage 7031, loopback 127.0.31.1 (checked free with `ss -ltn` before every label by the script); Byteman 9331 not used.

## 3. Runbook defects

Fixes before the frozen readings were audit amendments (case file B5.1 to B5.9). Defects found while building and running:

| # | Run | Step (§9b–§9e) | Problem | Fix | Decision (date) | Case-file commit with the fix |
|---|---|---|---|---|---|---|
| 1 | audit | B2c, B3c | unit N=100 at L=1023 CONTAINS too large for the 1 GiB `testsome` JVM; fixed row counts wrong for the 1/3 flush trigger | B5.2, B5.4 | 2026-10-25, before the freeze | orchestrator |
| 2 | audit | B2f | CONTAINS floor 0.5 MB below the leaf-edge floor 1.05 MB; no numeric flush point | B5.3, B5.4 | 2026-10-25, before the freeze | orchestrator |
| 3 | instrument check | cluster harness | `CREATE INDEX` switches the memtable once (switch count 1 at the start), so "stop at 3 switches" fired at once; the `OutOfMemoryError` count matched a JVM option; zombie PIDs defeated the stop wait | stop on `switch_count - base`, count `java.lang.OutOfMemoryError`, test `/proc/<pid>/stat` for `Z` (harness only; no frozen row involved) | 2026-10-25 | n/a |
| 4 | instrument check | cluster harness | first node start died once with rc 100 (cause not found; the retry-once logic was added); a mid-load histogram needs the loader paused (pause file) | harness only | 2026-10-25 | n/a |
| 5 | run 1 analysis | `analyze_cluster.py` | as written the checker called flush usage "at least H/3" with a tolerance of 0.011 MiB and "rows per flush 8x to 32x" for the 256 build; four FAILs resulted (see 4.1); the as-run output is kept (`run1/cluster/analysis-as-run.txt`) and a 0.05 MiB tolerance rerun is `analysis-tol005.txt` | not a runbook defect: these are readings that differ from the frozen text (section 4.2 part 2) | 2026-10-26 | n/a |

## 4. Run 1

**Scope:** unit tier, all arms of B2c as amended (PREFIX and CONTAINS, 14 + 14 arms, plus the SkipList control). Cluster tier, seven labels in series: A1024c (1024 build, CONTAINS, 1023 chars, 256 MiB pool), A1024c128 (same, 128 MiB), A1024r (1024 chars), A1024n (index dropped), A1024p (PREFIX, 1023 chars), A256c (256 build, 255 chars), A4096c (4096 build, 4095 chars). **Command log:** `results/sasi-max_term_size-TrieMemIndex-add-termSize--autonomous/run1/` (`unit/session.log`, `cluster/all.log`, `cluster/<label>/session.log`).

### 4.1 Readings

**Unit tier** (`run1/unit/unit-results.csv`, `unit-estimates.csv`; `unit/analysis.txt`: 53 of 53 checks PASS; the test run is `Tests run: 1, Failures: 0` in `unit/ant-tail.txt`)

| Test or assertion | Result | Evidence (file) |
|---|---|---|
| L=1022 and 1023, both modes, N up to 100 (30 for CONTAINS at 1023) | all accepted, all found by search, 0 rejection logs | `unit/unit-results.csv` |
| L=1024, 1025, 4096, both modes, N=10 | 0 accepted, estimate 0, not found, 10 `Can't add term` logs each | same |
| PREFIX estimate per term, L=1023 / 512 | 3,669 / 2,136 B (ratio 0.58); N=100 total 463,864 (126x the N=1 figure) | same |
| CONTAINS estimate per term, L=1023 / 512 / 100 | 1,694,447 / 516,108 / 59,626 B (L=512 over L=1023: 0.305); 462x the PREFIX figure at L=1023 | same |
| CONTAINS L=1023 total at N=1 / 10 / 30 | 1.69e6 / 18.4e6 / 47.8e6 (28x at N=30); L=512 N=100 total 48.6e6 | same |
| SkipList (int) control, N=1 / 10 / 100 | 260 / 2,600 / 26,000 | same |
| Heap delta after GC (indicative) | CONTAINS 1023 N=30: 24.6 MB for an estimate of 47.8 MB (ratio 1.95); CONTAINS 512 N=100: 27.8 MB for 48.6 MB (1.75); PREFIX 1023 N=100: 0.15 MB for 0.46 MB (3.2, small-scale noise; outside the "about 2" of B2f) | same |

**Cluster tier** — rows are those the loader inserted; flush usage is the `Usage:` of `Enqueuing flush of ks.t, Reason: MEMTABLE_LIMIT` (`flush-lines.txt`); trigger = `memtable_heap_space`/3 (85.33 MiB at 256, 42.67 at 128). All 29 `analyze_cluster.py` checks: 25 pass, 4 fail (below).

| Capacity value | Run | Observable (§9d) | Reading | Evidence (file) |
|---|---|---|---|---|
| 1024 build, pool 256 MiB | A1024c (1023 chars, CONTAINS) | flush usage MiB; rows at the three flushes; index file | 86.71 / 85.26 / 86.61; 57 / 113 / 170 rows; 174 rows loaded; SI files 73.3 / 69.4 / 72.0 MB; about 1.5 MiB tracked per row | `cluster/A1024c/flush-lines.txt`, `rows.csv`, `summary.json` |
| 1024 build, pool 128 MiB | A1024c128 | same | 42.99 / 42.88 / 42.93; 28 / 56 / 84 rows; 96 rows loaded; SI files 35.3 / 35.3 / 35.4 MB | `cluster/A1024c128/...` |
| 1024 build | A1024r (1024 chars) | `Can't add term` lines; flushes; memtable cells; on-heap | 174 lines for 174 rows; 0 flushes; 174 cells; max on-heap under 2 MiB; data size 186,702 B; read by key 1 row, LIKE 0 hits; no SI file | `cluster/A1024r/` |
| 1024 build | A1024n (no index) | same | 0 lines; 0 flushes; data size 186,528 B (within 0.1% of A1024r) | `cluster/A1024n/` |
| 1024 build, PREFIX | A1024p | flush usage; rows at the flushes | 85.31 / 85.28 / 85.37; 15,000 / 30,000 / 46,000 rows (46,787 loaded); SI files about 52.9 MB each | `cluster/A1024p/` |
| 256 build, 255 chars | A256c | same | 85.41 / 85.41 / 85.28; 478 / 956 / 1,433 rows (1,476 loaded); 8.4x the rows per flush of A1024c | `cluster/A256c/` |
| 4096 build, 4095 chars | A4096c | same | 89.02 / 88.90 / 89.07; 4 / 7 / 11 rows (14 loaded); 1/15 of the rows per flush of A1024c; LIKE found 0 hits (unexplained) | `cluster/A4096c/` |
| all | seven | peak heap used (sampler, MiB), OOM lines | A1024c 1205, A1024c128 1029, A1024r 238, A1024n 206, A1024p 1101, A256c 1147, A4096c 1054 (all under 2048); 0 OOM | `cluster/*/samples.csv`, `summary.json` |
| all | A1024c, A1024c128, A1024p, A256c, A4096c | live heap (class histogram total) rise from base to the mid-load histogram vs tracked memtable on-heap | A1024c 28.7 vs 41.6 MiB (tracked/live 1.45); A1024p 32.5 vs 40.4 (1.24); A256c 38.6 vs 47.1 (1.22); A4096c 60.6 vs 24.5 (0.40: live larger than tracked); A1024c128's mid sample read 0 (histogram not at a full memtable) | `cluster/*/summary.json`, `histogram-*.head.txt` |

The four FAILs of `analysis-as-run.txt` (the tol-0.05 rerun leaves the same four): (a) A1024c, A1024p and A256c flush usage was 85.26, 85.28 and 85.28 MiB, 0.05 to 0.07 MiB (0.08%) below the 85.33 MiB trigger, so "at least 85.3 MiB" is missed by rounding-level amounts (the trigger compares the pool's used bytes, which also counts the other tables' memtables, with the table's own usage); (b) A256c rows per flush was 7.5x (first flush) to 8.4x (mean) of A1024c, below the 8x to 32x bracket's centre of 16x that B3f states ("about 16x more"), because the estimate per row grows with a power of the term length below 2 (unit tier: L=512 over L=1023 is 0.305, not 0.25). 25 other checks pass.

### 4.2 Conclusion and logic

1. **Validity** — valid. The constant's boundary was reached from both sides: 1023 accepted and 1024 rejected in both modes at the unit tier [observed: `unit/unit-results.csv`], and 1024-char rows added no index structure at the cluster tier [observed: `cluster/A1024r/`]. The running jar of each build has the intended constant [observed: `summary.json` `constant_check`, `javap`: 1024 / 256 / 4096]. Hold-fixed settings: heap 2 GiB (`node-cmdline.txt`), `memtable_heap_space` 256 / 128 MiB, default cleanup threshold 1/3 (flush usage near 85.3 and 42.7 MiB shows it) [observed]. The pool trigger, the known-binding cap, was reached three times in every growing arm [observed: `flush-lines.txt`].
2. **Readings** — frozen-prediction misses, none changing a conclusions row: flush usage up to 0.07 MiB below H/3 (rounding-level; pool counts all tables); the 256 build's rows per flush 8x, not about 16x (sub-quadratic growth in term length); the PREFIX heap delta ratio 3.2 outside "about 2" (0.15 MB scale); the A4096c live heap larger than the tracked size (0.40) and its LIKE query finding nothing, unexplained; the 1024 arm's third flush overshoot 1.4 MiB (about 0.9 of a row, below the "one row" bound).
3. **Matched row** — Unit B2g rows 1 and 5: size scales with N with no plateau (CONTAINS 1.69e6 at N=1, 47.8e6 at N=30; PREFIX 126x at N=100) and CONTAINS at L=1023 is 1.7 MB per term against 1,023 bytes of term [observed: `unit-results.csv`]; the usage-versus-knob relation is flat at the cap (1024 rejects, nothing between) while the N dose and SkipList control move [observed]. Cluster B3g rows 1 and 4: flush usage 85.3 to 89.0 MiB for the 256, 1024 and 4096 builds (mean spread 3.6 MiB, under one row of the 4096 build), halved to 42.9 MiB at 128 MiB (0.498), growth per row varies with length and mode (rows per flush 478 / 57 / 4 at 255 / 1023 / 4095 chars; PREFIX 15,000) [observed: `flush-lines.txt`, `rows.csv`].
4. **Excluded rows** — Unit "bounded by about 1 KiB-scale value in CONTAINS" (Refuted): 1.7 MB per term [observed]; "total plateaus as N grows": none, N up to 100 [observed]; "L=1023 rejected or L=1024 accepted": excluded (both modes) [observed]; "limit never reached or control did not move": excluded. Cluster "memtable on-heap or heap plateaus at a value set by the constant" (Refuted): the flush point is the same under 256, 1024 and 4096 [observed]; "1024-byte terms add index structure": excluded, 174 rows added data only (186,702 B vs 186,528 B without the index) [observed]; "flush point does not move when the pool changes / no three flushes": excluded, it halved and every growing arm flushed three times [observed]; "growth with the index dropped is the same": excluded, A1024n never flushed [observed].
5. **Observed vs. inferred** — inferred: (a) that the tracked on-heap size stands for the real index memory (live heap rise is 0.7x to 0.8x of tracked for 1023 and 255 chars and 2.5x of it at 4095, one mid-load sample each, so the estimate is not exact either way); (b) that the 0.07 MiB shortfall below H/3 is other tables' share of the pool (not isolated); (c) the unit heap deltas are indicative.
6. **Deviations and gaps** — B2h "each (mode, L) in its own JVM" not done: one JVM, `System.gc()` twice between arms, 1 GiB; the unit tier has no pool, so its control is the N dose and the SkipList column (B5.6); Byteman was not needed; the 4095-char LIKE miss is unexplained and is not part of a frozen row; the bytes at each flush are read from the log line (rounded to 0.001 MiB) and from the 100 ms sampler; the mid-load histogram for A1024c128 was taken at an empty memtable.
7. **Core question** — Usage did not follow the constraint. Per term the constant admits 1023 and rejects 1024, but below it one term costs 1.7 MB of tracked memory (about 1,600x its length) in CONTAINS mode and 3.7 KB in PREFIX mode, and the total grows with the number of terms with no plateau (unit tier). On the node, the memtable flushes when the pool's used bytes pass `memtable_heap_space`/3 whether the constant is 256, 1024 or 4096 (85.3 to 89.0 MiB), with 478, 57 and 4 rows per flush, and halves with the pool (42.9 MiB at 128 MiB), so the pool, not the constant, caps the index memory [steps 1 to 4 above].

**Conclusion (one line):** B2g rows "size scales with N; CONTAINS >> L bytes" and "flat vs the knob while the control moves", and B3g rows "bytes at flush the same across builds, tied to `memtable_heap_space`" and "pool change moves the flush point" — confirmed (claim: does not cap).

## 5. Self-check of run 1 — AI

### 5.1 Check of run 1's conclusion

`harness/.../selfcheck.py` re-parses the raw per-label files (node log lines by timestamp, `rows.csv`, `tablestats.txt`, `loader.out`, `summary.json`, the unit CSV) without the analyzers or the sampler (output `run1/cluster/selfcheck.txt`: ALL HOLD, 27 of 27).

| Part | Holds? (yes / no) | Note (file re-read) |
|---|---|---|
| 1. Validity | yes | constants in the three jars re-read from `summary.json`; loader totals equal `rows.csv` for all seven labels; flush lines re-timed against `rows.csv` give 57 / 113 / 170 rows (the analyzer's sampler-based 66 / 118 / 172 differ by sampling lag, same conclusion). |
| 2. Readings | yes | the four analyzer FAILs re-derived by hand from `flush-lines.txt` (85.26, 85.28, 85.28 MiB; 7.5x/8.4x); recorded in 4.1 and 4.2 part 2. |
| 3. Matched row | yes | mean flush usage per build 86.19 / 85.37 / 89.00 / 85.32 MiB (spread 3.6, under 4); 128 MiB mean over 256 MiB mean 0.498. |
| 4. Excluded rows | yes | A1024r `cantadd-count.txt` 174 equals rows, no MEMTABLE_LIMIT flush, memtable data size within 0.1% of the no-index arm; unit boundary re-derived from the CSV. |
| 5. Observed vs. inferred | yes, with a gap | live-heap versus tracked ratios rest on one mid-load histogram per label and move from 0.7x to 2.5x; no conclusions row depends on it. |
| 6. Deviations and gaps | yes | listed. |
| 7. Core question — the steps from reading to answer follow the audited logic | yes | |

### 5.2 Run 2?

**No** (2026-10-26). The two tiers agree, the claim is negative with a control that moved (pool 256 to 128 MiB, 0.498), and the decisive readings are exact log lines and counts. The gaps (heap ratios, the 4095-char LIKE miss) are indicative or outside the frozen rows.

## 6. Run 2 — fresh AI session (optional)

Not done (section 5.2).

## 7. Comparison — only if run 2 was done

Not done.

## 8. Verdict — AI

Jingsong may overrule any verdict at any time; record an override here with its date and reason.

**Stage-3 estimate:** negative. **Outcome class:** true negative (negative, does not cap).

**Claim tested:** SASI memtable index memory does not follow `MAX_TERM_SIZE` (B1): the constant only accepts or rejects individual terms (1023 accepted, 1024 rejected), accepted terms cost far more than their byte size in CONTAINS mode, and total usage is governed by the number of terms and the memtable pool. "Confirmed" below means this claim held.

| Tier | Verdict (§9a row; for an autonomous file, the B2g / B3g row) | Effect on the constraint | Basis | Date |
|---|---|---|---|---|
| Unit | Confirmed (B2g rows 1 and 5) | does not cap | run 1 + self-check | 2026-10-26 |
| Cluster | Confirmed (B3g rows 1 and 4) | does not cap | run 1 + self-check | 2026-10-26 |

**Positive control** (a negative-estimate file only): cluster: `memtable_heap_space` 256 to 128 MiB moved the flush usage from 86.2 to 42.9 MiB (ratio 0.498) and rows per flush from 57 to 28 for the same workload, while the constant (256 / 1024 / 4096) did not move it (85.3 to 89.0 MiB). Unit: the N dose (1, 10, 30/100) and the SkipList column move the returned size; the unit tier has no pool, so its control is weaker (audit rating Partly), and the cluster control carries the "a cap could have shown" argument.

**Leftovers:** none running. Removed: `~/s4-tm-data/*`. Kept on pc12: `~/s4-tm`, `~/s4-tm-c256`, `~/s4-tm-c4096` (built trees; `TrieMemIndexSizeTest.java` untracked in `~/s4-tm/test/unit/org/apache/cassandra/index/sasi/memory/`), `~/stage4-logs/tm/` (logs and `shake*` instrument checks). No Byteman or JMX client left. The `s4-ec` processes on pc12 are another agent's.

**Feedback filed:** the case file's section D updated and amendments B5.1 to B5.9 in B (case-file commit by the orchestrator, sha256 in section 1 and below). Upstream note (left for stage 3): `OnDiskIndexBuilder.java:171` prints `Short.MAX_VALUE` as the maximum size.
