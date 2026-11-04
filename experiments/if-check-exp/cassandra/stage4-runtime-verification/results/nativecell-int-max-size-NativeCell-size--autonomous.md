# nativecell-int-max-size-NativeCell-size--autonomous — stage-4 results  <!-- file: results/nativecell-int-max-size-NativeCell-size--autonomous.md -->

> **Case:** [`nativecell-int-max-size-NativeCell-size--autonomous`](../../stage3-ai-deep-read/cases/nativecell-int-max-size-NativeCell-size--autonomous.md)
>
> **Status:** verdict filed (2026-10-25) — run 1 done at both tiers, self-checked, no run 2
>
> **Outcome class:** **true negative** (estimate `negative`, effect `does not cap`) — [definition](../README.md#outcome-class)
>
> **Agent:** autonomous. "§9a" below means B2f/B2g (unit) and B3f/B3g (cluster); "§9b–§9e" means B2a–B2e / B3a–B3e; the feedback section is section D.

## 1. Before run 1 — design audit and freeze

| Field | Content |
|---|---|
| **Case-file version** | Base repository commit `25b4a70`; the case file is **untracked** (no commit holds it). **sha256 of the whole file after the audit's amendments (B2i, B3i, dated 2026-10-25): `99af8c54c88076d76e80055ea00fcc0e02684df33528b1d448ed57b4e40a1a72`**, (a first draft with hash `f0931b40...` was corrected before the harness existed, see B2i.5(e)) written to `~/s4-nc/logs/freeze.sha` and to this file at 2026-10-25T17:56:44Z, before the harness existed and before any reading. B2f, B2g, B3f, B3g (with B2i, B3i) are frozen at this hash. Section D (the feedback) is filled afterwards; the hash with D filled is in section 8. |
| **Harness** | `harness/nativecell-int-max-size-NativeCell-size--autonomous/`: `NativeCellGuardTest.java`, `unit-run.sh`, `analyze_unit.py`, `JmxSampler.java`, `cluster-run.py`, `analyze_cluster.py`, `selfcheck.py`, `README.md`; written after the freeze; not committed (md5s at the start of run 1 and at the end are identical: `nativecell-int-max-size-NativeCell-size--autonomous/run1/harness.md5.{unit-start,final}`). Instrument checks: see the harness README. |
| **Tiers and values** | **Unit (B2 + B2i):** arms S, G1, G2, P (limits 8/16/32 MiB), O, H, R. **Cluster (B3 + B3i):** arms A, A2, B, K64/K128/K256/K512, hb. |
| **Audit bottom line** | **Ready after amendments** — 2026-10-25 |

### 1.1 Design audit

Estimate: **negative** (the line-100 constant bounds one cell, not the memtable's total). Audited against `cassandra/cassandra-5.0.9/` (clean; `build.xml` base.version 5.0.9). Citations re-read: `NativeCell.java:36-125,185-205`, `NativeAllocator.java:40-205`, `MemtableAllocator.java:160-300`, `MemtablePool.java:120-165`, `Mutation.java:160-178`, `SingleTableUpdatesCollector.java:105-114`, `BatchUpdatesCollector.java:144-152`, `DatabaseDescriptor.java:583-590,640-660,753-770,862-925,943-948,3237-3245`, `Config.java` knob lines, `Envelope.java:197,484`, `CQLMessageHandler.java:551`, `build.xml` junit fork (maxmemory 1024m, `test.jvm.args`).

| Group | Check | Rating | Note (section checked) |
|---|---|---|---|
| A. Core question | constrained quantity is memory or disk bytes | Met | A2: off-heap native bytes of one cell / the memtable pool. |
| A. Core question | knob varied, ≥ 3 values incl. default — or another approach, with the reason | Met | The line-100 constant has no knob (A1). Unit: the guard is driven at 2^31-21, 2^31-1, 2^31 and the pool limit varied 8/16/32 MiB; cluster: `memtable_offheap_space` 64/128/256/512 MiB (512 = default at 2 GiB heap, absent from the filed design; B3i.3). |
| A. Core question | real resource measured, not only the counter (gap named) | Partly → Met | B2d/B3d name `owns()`/`MemtableOffHeapSize` plus RSS/NMT; amended to `RssAnon` with pre-touched heap, malloc env (B2i.3, B3i.3). Gap: allocator headers and page rounding. |
| A. Core question | usage driven to the limit and past it | Partly → Met | The guard is driven to and past 2^31-1 (B2i.2, G1/G2); the pool limit is crossed at all three unit limits and every K arm (800 MiB written against ≤ 512 MiB). The filed pool in B2c (64 MiB, 400 cells of 200 KiB) is kept only as arm S/R scale. |
| A. Core question | positive control for a negative estimate | Met | The pool limit is the known-binding cap on the same resource: arm P (unit), K arms (cluster); the heap control H/hb shows the cell path is the source. |
| B. Logic | each step says what it establishes | Met | B2e/B3e. |
| B. Logic | prediction stated in numbers or a clear relation | Partly → Met | B2f/B3f gave only relations; numbers added in B2i.5 and B3i.4 from source arithmetic. |
| B. Logic | every plausible outcome has a conclusions row with its evidence | Partly → Met | Rows added: B2i.6, B3i.5 (guard misplaced, limit never reached, resource/counter divergence, no row fits). |
| B. Logic | confirmation needs ceiling-follows-knob and direct disallow evidence | Met | For a "does not cap" claim: usage follows the pool knob (K, P) and not the guard; the guard's own firing is read directly at 2^31 (G1/G2, exception and frame). |
| B. Logic | alternative explanations and their controls | Met | B2h/B3h + H/hb; repeat arm R. |
| C. Specific | a human can follow it from the intro and B1 | Met | A3, B1. |
| C. Specific | an AI can run B2/B3 without re-deriving the code path | Partly → Met | How to build a 2 GiB value without a mock, the blocking group, the package for `released()`, JMX sampler, tables, protocol: B2i.2-4, B3i.1-3. |
| C. Specific | knob, values, workload, commands, observables, sampling, stop conditions exact | Partly → Met | Filed paths `/local/c509` do not exist here; sampling interval, rows and arms fixed in B2i/B3i. |
| D. Runnable | harness and environment prerequisites exist or are listed | Met | Test class, driver, sampler, analysers are step-1 work; tree via `copy-source.sh`. |
| D. Runnable | workload arithmetic reaches the limit (data, time, disk, memory) | Met | Unit peak about 5 GiB RSS on a 251 GiB node. Cluster 800 MiB per K arm exceeds every pool limit; ≤ 3 GB per arm on 44 GB free local disk. The filed 17 MiB at default reaches the wire limit, not `validateSize` (B3i.1) — fixed by arm A2. |
| D. Runnable | load-bearing citations spot-checked against the pinned source | Partly → Met | All hold except: two filed workload arithmetic errors (L = MAX-20 gives size 2^31, not 2^31-1; B2i.1), the claim in A3.5 that raising `max_mutation_size` and `max_value_size` makes line 100 reachable (it cannot: the segment is < 2048 MiB and ≥ 2 x the mutation limit, so a mutation is < 1 GiB; B2i.7), and the 17 MiB refusal path under protocol v4 / the in-flight default of 51 MiB at -Xmx2g (B3i.1-2). |

| # | Recommendation | Applied? | Why |
|---|---|---|---|
| 1 | L values for the guard probe: MAX-21 passes, MAX-20 throws | Applied, B2i.1 (2026-10-25) | Off-by-one in the filed arithmetic. |
| 2 | Real 2 GiB direct buffer instead of a mock; unit class in package `utils.memory` | Applied, B2i.2 | `ByteBuffer` cannot be subclassed; `released()` is package-private. |
| 3 | Pool-limit positive control with a non-blocking and a blocking group; overshoot cell | Applied, B2i.4-5 | The filed control was not specific about how to block or count. |
| 4 | `RssAnon` and malloc env as the real-resource reading | Applied, B2i.3 / B3i.3 | `VmRSS` includes the heap and file pages. |
| 5 | Numeric predictions and extra conclusion rows | Applied, B2i.5-6, B3i.4-5 | Relations alone cannot be contradicted. |
| 6 | Protocol v4, frame limit as the request limit, in-flight limits fixed, arm A2 for `validateSize` | Applied, B3i.1-3 | Filed path for the 17 MiB refusal is not what happens on v4. |
| 7 | `memtable_offheap_space` 512 (default at 2 GiB heap) added | Applied, B3i.3 | Three or more values including the default. |
| 8 | A3.5 sentence "guard becomes reachable" is wrong; the cluster tier cannot reach line 100 | Recorded B2i.7, B3i.6; A3.5 left as filed text for stage 3 | Source fact, independent of readings. |
| 9 | Path term (line 97) not probed; 2.1 GiB cluster arms not run | Declared, B2i.2 / B3i.6 | Not reachable / not needed. |

**Agreement criteria** — not applicable (no run 2 chosen before run 1).

## 2. Environment

| Field | Run 1 |
|---|---|
| Date | 2026-10-25 |
| Node | `pc07` (`node0.jason92-320876.misconfiguration-pg0.cloudlab.umass.edu`), 40 cores, 251 GiB; other agents ran on the same node (tags st, bt) |
| OS and kernel | Ubuntu 22.04, `5.15.0-187-generic` |
| JDK / Ant | OpenJDK 11.0.32.1 / Ant 1.10.12 |
| Local source copies | `~/s4-nc/cassandra` (unit tier; `ant build-test`, 1 min 18 s) and `~/s4-nc/nodetree` (node; `ant jar`, 1 min 12 s), both from `copy-source.sh` of `cassandra/cassandra-5.0.9/` at repository commit `25b4a70`; the node tree was never built in after the node started |
| Case-file commit / harness commit | none (both untracked) / none; sha256 in section 1 |
| Storage for node data | local `/dev/sda3` (ext3, 43 GB free), `~/s4-nc/node`, emptied between arms |
| Node settings | one node, 127.0.0.31, ports 7031/9031/7331; `-Xms2G -Xmx2G -XX:+AlwaysPreTouch -XX:MaxDirectMemorySize=1g`; `MALLOC_ARENA_MAX=1 MALLOC_MMAP_THRESHOLD_=65536 MALLOC_TRIM_THRESHOLD_=0`; protocol v4; autocompaction disabled |
| Full logs (outside the repo) | unit: `~/s4-nc/run1-unit/{ant.log,session.log,raw/results.csv}`; cluster: `~/s4-nc/run1-cluster/<arm>/{system.log,samples.csv,rows.jsonl,arm.json}` and `session.log` |

## 3. Runbook defects

None stopped a run. The audit's findings (section 1.1: off-by-one probe lengths, A3.5's reachability claim, the v4 frame limit as the 17 MiB refusal, in-flight limits at a 2 GiB heap) were applied as amendments before the freeze (B2i, B3i). One harness bug (an `int` loop overflowing for the 2 GiB buffer) was found by the unit shakedown and fixed before run 1; no reading was taken from a shakedown.

## 4. Run 1

**Scope:** unit tier, all arms of B2i.4 (S for four sizes, R, P at 8/16/32 MiB, O, H, G1, G2), one JUnit test (`Tests run: 1, Failures: 0, Errors: 0`, `run1/unit-junit.txt`); cluster tier, all eight arms of B3i.3. **Command log:** `run1/unit-session.log`, `run1/cluster-session.log`. Analyser output (PASS/FAIL per frozen numeric prediction): `run1/unit-analysis.txt` (47 of 47 PASS), `run1/cluster-analysis.txt` (33 of 33 PASS).

### 4.1 Readings

**Unit tier** (`run1/unit-results.csv`)

| Test or assertion | Result | Evidence |
|---|---|---|
| S: 10 cells each of L = 1 KiB, 200 KiB, 16 MiB, 255 MiB; `offHeapSize()` and `owns()` delta per cell | all 40 cells exactly L + 21 (1045; 204,821; 16,777,237; 267,386,901); no exception; sum = `owns()` = 10 x (L + 21) | `unit-results.csv` arms S_* |
| S: `RssAnon` rise over the ten cells / expected | 16 MiB: 0.999; 255 MiB: 1.002 (2,679,709,696 B); after `setDiscarded()` 0.1 and 5.7 MiB; `owns()` 0 | S_16MiB, S_255MiB |
| R: 200 KiB cells twice | identical counters both times | R_200KiB_a/b |
| G1 (pool 8 GiB, non-blocking), throwing probe L = MAX-20 (size 2^31) | `IllegalStateException`, message null, top frame `NativeCell.<init>:101`, `owns()` delta 0, RssAnon +24 KiB | G1 |
| G1 passing probe L = MAX-21 (size 2^31-1) | accepted; `offHeapSize()` 2,147,483,647 = `owns()` delta; RssAnon +2.0 GiB (2,147,598,336 B); freed on discard | G1 |
| G2 (pool 8 MiB, blocking group), same two probes | throw as G1 (delta 0); pass accepted, `owns()` +2,147,483,647 = 256 x the 8 MiB pool limit | G2 |
| P (positive control, pool limit), 1 MiB cells, non-blocking group | cells admitted before the next one blocks: 7, 15, 31 at 8, 16, 32 MiB (= `floor(P / (1 MiB + 21))`); `owns()` at the block = admitted x (1 MiB + 21); blocked cell completed 5 to 6 ms after `released()` | P8, P16, P32 |
| P, blocking group | cells return in at most 7 ms; `owns()` 10,485,970 / 18,874,746 / 35,652,298 > limit | P8..P32 |
| O: one 16 MiB cell, 8 MiB pool, blocking group | accepted, `owns()` 16,777,237 = 2.0000025 x the limit | O |
| H: heap `BufferCell` of 16 MiB | `owns()` 0 before and after | H |

**Cluster tier** (`run1/cluster-<arm>/`; `AllMemtablesOffHeapSize` peaks from `samples-500ms.csv` / the 100 ms originals)

| Arm (config) | Block | Observable | Reading | Evidence |
|---|---|---|---|---|
| A (offheap_objects, 256 MiB, frame 16 MiB) | 1, 8, 15 MiB x 100 | inserts ok / errors; log | 100/0 each; `IllegalStateException` 0, `NativeCell` 0 in `system.log` | cluster-A/arm.json |
| A | 17 MiB x 1 | client error; counter; gauge | "Request is too big: length 17825848 exceeds maximum allowed length 16777216."; `OverSizedMutations` 0; gauge rise 0.00 MiB | arm.json, rows.jsonl |
| A2 (frame 64 MiB) | 17 MiB x 1 | client error; counter | "Rejected an oversized mutation (17825848/16777216) for keyspace: ks."; `OverSizedMutations` Count 1 | cluster-A2 |
| B (mutation 64 MiB, segment 128 MiB, frame 128 MiB) | 17 MiB x 5, 60 MiB x 5 | inserts | 10 of 10 ok; `IllegalStateException` 0; peak gauge 85 MiB (A shows the same 85 MiB) | cluster-B |
| K64 / K128 / K256 / K512 | 8 MiB x 100 | peak `AllMemtablesOffHeapSize` | 16 / 40 / 80 / 168 MiB (0.25 / 0.31 / 0.31 / 0.33 x limit); all 400 inserts ok | cluster-K*/samples |
| K256 | 8 MiB x 100 | `RssAnon` peak minus idle baseline | 140.0 MiB (1.75 x the 80 MiB gauge) | cluster-K256/samples |
| hb (heap_buffers) | 8 MiB x 100 | gauge; RssAnon | gauge 0 throughout; RssAnon rise 41.9 MiB (K256: 140.0 MiB) | cluster-hb |

### 4.2 Conclusion and logic

1. **Validity.** The pool limit was reached at every unit limit (the next cell blocked) and every K arm crossed its flush trigger many times (800 MiB written against 64 to 512 MiB limits) **[observed: unit-results.csv P*, cluster-K*/samples-500ms.csv sawtooth]**. The held-fixed settings are in the arms' `yaml-keys.txt` and `cmdline.txt` (allocation type, off-heap space, frame limit, mutation/segment sizes, `-Xmx2G`, `AlwaysPreTouch`) and the startup line "Global memtable off-heap threshold is enabled at <k>MiB" in each `system.log` **[observed]**. The guard itself was driven to and one byte past 2^31-1 with a real 2 GiB buffer **[observed: G1, G2]**. Valid.
2. **Readings.** Cluster gauge peaks are multiples of 8 MiB and come from a 100 ms sampler on a roughly 300 ms sawtooth (0, 8, 16, 0 MiB at K64), so each peak is a lower bound by at most one cell **[observed: samples; inferred: the missed state]**. K64's 16 MiB is below its trigger of 21.3 MiB for that reason. The 200 KiB x 10 `RssAnon` rise was 0 (a 2 MB signal under the JVM's noise); the frozen RSS band applied only to 16 and 255 MiB **[observed: S_200KiB]**. The `A2` `system.log` does not carry the rejection text; the client error and the counter do **[observed]**.
3. **Matched rows.** Unit **B2g row 1**: "`owns()` and `offHeapSize()` equal L+21 for all L; guard throws only at size >= 2^31": all 40 cells, throw only at 2^31 **[observed: S_*, G1, G2]**; and the pool row: "total tracks N x (L+21) and is limited only by the pool limit (blocking)": P arm **[observed]**. Cluster **B3g row 1**: "No line-100 exception anywhere; 17 MiB refused by mutation limit; peak off-heap tracks `memtable_offheap_space`", with the refusal point corrected by B3i.1 (frame limit at defaults, `validateSize` with a larger frame limit) **[observed: A, A2, B, K*]**; and **B3g row 4**: "Peak off-heap use halves with the pool knob and per-cell acceptance does not change": 16, 40, 80, 168 MiB and 15 to 60 MiB accepted in every arm that allows them **[observed]**.
4. **Excluded rows.** Refuted (a throw at line 101 for L <= 255 MiB or <= 60 MiB): none, and `NativeCell` count 0 in all eight logs **[observed]**; admitted counts equal the formula, so the pool does bind **[observed]**. "Probe not constructible / positive control did not move": the 2 GiB buffer was built and P and K moved **[observed]**. "Peak flat when the knob is halved": it halved or better at every step **[observed]**. "RSS far beyond pool + heap": K512 RssAnon rise 246 MiB against a 168 MiB gauge **[observed]**. "Peak above k + 16 MiB": none **[observed]**.
5. **Observed vs inferred.** Inferred: that the true cluster peak is within one cell of the sampled one (sampler resolution vs sawtooth); that the guard is unreachable by a production write (source reading of `DatabaseDescriptor.java:890-901`, not run); that the cluster tier's 15 to 60 MiB range stands for "practical" (the largest cell an operator-reachable configuration admits is under 1 GiB, untested between 60 MiB and 1 GiB).
6. **Deviations and gaps.** The path term (line 97) is arithmetic only. No cluster arm above 60 MiB; no second node; no NMT run (`RssAnon` was used instead, B2i.3). Each K arm ran once (no run 2). The A3.5 text is left as filed in the case file; the correction is in B2i.7.
7. **Core question.** Usage did not follow the line-100 constant: it is inert in the whole practical range and fires only at size 2^31, a value no production write can produce, while usage followed the pool knob (unit P: 7/15/31 cells; cluster K: 16/40/80/168 MiB) and the per-cell cap came from the wire/mutation limits (steps 1 to 4). So the constraint does not cap usage.

**Conclusion (one line):** unit B2g row 1 and cluster B3g rows 1 and 4 — claim confirmed (the guard does not cap off-heap usage).

## 5. Self-check of run 1 — AI

### 5.1 Check of run 1's conclusion

`harness/.../selfcheck.py` re-parsed the unit `ant.log` RESULT lines (not `results.csv`) and the cluster `samples.csv`, `rows.jsonl`, `arm.json` and `system.log` with its own code; output `run1/selfcheck.out`. It reproduced the analysers' headline numbers (cells L+21, the 1.002 RSS ratio, the 2^31-1 and 2^31 probes, 7/15/31 admitted, 16/40/80/168 MiB peaks, 0 `IllegalStateException`/`NativeCell`, 85 MiB for A and B). I also re-read the node `cmdline.txt` (`-Xms2G -Xmx2G`, `AlwaysPreTouch`, `MaxDirectMemorySize=1g` last), `yaml-keys.txt` of K256, B and hb, and the startup log lines.

| Part | Holds? | Note (file re-read) |
|---|---|---|
| 1. Validity | yes | `P*` blocking counts, K sawtooth, `yaml-keys.txt`, `cmdline.txt`, G1/G2 in `ant.log` |
| 2. Readings | yes | sampler resolution caveat stated; the 200 KiB RSS zero and the A2 log gap are recorded, neither is used |
| 3. Matched row | yes | B2g row 1 and pool row; B3g rows 1 and 4, `selfcheck.out` |
| 4. Excluded rows | yes | no `NativeCell` in any of eight `system.log` files; peaks within k + 16 MiB |
| 5. Observed vs inferred | yes | the inferred items rest on source (`DatabaseDescriptor`) and sampling arithmetic, listed |
| 6. Deviations and gaps | yes | stated; they limit the claim to the practical range and to the unit probe for the guard itself |
| 7. Core question | yes | the steps follow the audited logic: guard inert (S, G, A, B) then pool binds (P, K) then positive control moved |

### 5.2 Run 2?

**No** (2026-10-25). Both tiers are exact or large-margin (47 and 33 PASS, no marginal band), the guard behaviour was read directly, and nothing refutes the estimate. The inferred sampler-resolution point could not change the row.

## 6. Run 2 — fresh AI session (optional)

Not done.

## 8. Verdict — AI

**Stage-3 estimate:** negative. **Outcome class:** **true negative** (negative, does not cap).

**Claim tested (B1):** the `Integer.MAX_VALUE` guard at `NativeCell.java:100` does not bound off-heap memory use in a meaningful way: in any practical setting it is never reached, a cell is limited much earlier, and the aggregate footprint is set by what is written and by `memtable_offheap_space`; the guard only prevents an int overflow for a hypothetical ~2 GiB cell. "Confirmed" means this held.

| Tier | Verdict (row) | Effect on the constraint | Basis | Date |
|---|---|---|---|---|
| Unit | Confirmed — B2g row 1 (counters equal L+21, guard only at size >= 2^31) and the pool row (admission set by the pool limit) | does not cap | run 1 + self-check | 2026-10-25 |
| Cluster | Confirmed — B3g rows 1 and 4 (no line-100 exception, refusals by the wire/mutation limits, peaks 16/40/80/168 MiB follow `memtable_offheap_space`) | does not cap | run 1 + self-check | 2026-10-25 |

**Positive control:** the pool limit on the same resource moved usage: unit P admitted 7, 15, 31 cells at 8, 16, 32 MiB and blocked the next; cluster K peaks 16, 40, 80, 168 MiB at 64, 128, 256, 512 MiB, against 0 for `heap_buffers` and no change for the guard.

**Nuance recorded:** the guard does stop a single cell at exactly 2^31-1 bytes (unit tier), so on a path that could reach it the constant would cap one cell; none can (segment size < 2048 MiB and >= 2 x `max_mutation_size`), hence "does not cap".

**Feedback filed:** the case file's section D filled (no commit; the file is untracked); amended sections B2i and B3i (2026-10-25, before run 1; A3.5 left as filed with the correction in B2i.7). The final sha256 of the case file with D filled is `cd4345fab7075e766359ddde4f2cfaf399e9ee61b28b928c7a0b0ebb890007e8`; the frozen version (before D) is the hash in section 1.

**Leftovers on the node:** no process of this run is running (`CassandraDaemon`/`JmxSampler` checked). Files remain under `~/s4-nc/` (two source trees, `driver`, `jmxs`, `logs`, `run1-unit`, `run1-cluster` with the full logs, about 2 GB at most); node data and commit logs were deleted between arms.

## 9. Time spent (UTC, from `/proj/misconfiguration-PG0/git-repos/timing-batch4.log`)

| Step | Start | End | Minutes | Remarks |
|---|---|---|---|---|
| audit | 17:51:02 | 17:55:38 | 4.6 | source re-reads, off-by-one and reachability findings, amendments, freeze hash, skeleton |
| harness | 17:55:38 | 18:11:30 | 15.9 | two `ant` builds ran in the background (1m18s, 1m12s); unit shakedown and one fix; cluster shakedown (about 10 min of node start-ups at 60 to 85 s each); first cluster shakedown run at full scale killed by PID and redone at scale 0.05 |
| unit-run | 18:11:30 | 18:12:20 | 0.8 | one `ant testsome`, 37 s build/run |
| cluster-run | 18:12:20 | 18:29:25 | 17.1 | 8 arms, each a node restart (60 to 100 s) plus workload and 12+15 s idle |
| selfcheck | 18:29:37 | 18:30:09 | 0.5 | selfcheck.py plus re-reads of cmdline/yaml/log lines |
| report | 18:30:09 | 18:31:42 | 1.6 | results file, case file section D, run1 excerpts |
| **total wall (audit start to report end)** | 17:51:02 | 18:31:42 | 40.7 | steps sum 40.5; the gaps (about 0.2 min each) are tool turnaround |

No step was redone (no suffixed steps). Waits: builds and node start-ups only.

