# max_queue_weight-acquireWeight-weight--autonomous — stage-4 results  <!-- file: results/max_queue_weight-acquireWeight-weight--autonomous.md -->

> **Case:** [`max_queue_weight-acquireWeight-weight--autonomous`](../../stage3-ai-deep-read/cases/max_queue_weight-acquireWeight-weight--autonomous.md)
>
> **Status:** verdict filed (2026-10-27)
>
> **Outcome class:** true positive — the stage-3 estimate (`positive`) against the effect found in §8 ([definition](../README.md#outcome-class)); filed 2026-11-03 when the advisor's results were merged, from the final tier verdicts in §8.
>
> **Provenance:** advisor-run (the advisor's machine, [`environment-advisor.md`](../environment-advisor.md)); merged into this repository on 2026-11-03. The raw run folders cited as evidence (`run1/`, `run2/`: logs, samples, leak dumps) are held by the advisor and are not part of this repository; the harness is under [`harness/max_queue_weight-acquireWeight-weight--autonomous/`](../harness/max_queue_weight-acquireWeight-weight--autonomous/).
>
> **Agent:** autonomous. "§9a" = B2f/B2g (unit) and B3f/B3g (cluster); runbook = B2a–B2e / B3a–B3e; feedback = section D.
>
> **Session:** Claude Opus 5.5 (claude-opus-5-5[1m]), Claude Code CLI, 2026-10-27, advisor's Mac (`advisor-run`).

## 1. Before run 1 — design audit and freeze

| Field | Content |
|---|---|
| **Case-file version** | Filed `2eb53efcbbb9166ce3255a3c51d9ae81c3ff824978ed0f0896dd7c6db5d2bb67` (repo HEAD `9ed1823` holds it as filed). Frozen after the audit's 11 amendments (U1–U5, C1–C6): `65f57ecb98c01d7bb696fe84e797eecd6fb36ff1785ebc45736beb3a827185fd`. After runbook-defect fixes D1–D3, all found by harness shakedowns before run 1: **`7198059f0048ef7d03ff2a13e84d255d3bfbcb6f5c86f2e70754afee8cc2a747`**. Both tiers of run 1 ran on this version. Both hashes are rows in `_INDEX.md` §4. Not committed yet (uncommitted working tree on `advisor-run`) |
| **Harness** | `harness/max_queue_weight-acquireWeight-weight--autonomous/`: `WeightedQueueCapTest.java`, `BinLogCapTest.java`, `unit-run.sh`, `slow-binlog.btm` (the filed rule, verbatim), `mqw-observe.btm` (observe-only), `make-node-conf.sh`, `cluster-run.sh`; `results/.../run1/selfcheck.py`. Not committed yet. Reused tools: `make-node-conf.sh` was copied from `harness/bloom_filter_fp_chance-getFilter-maxFalsePosProbability--autonomous/` with the clone, node path and cluster name changed. The node mechanics of `cluster-run.sh` (timeout wrapper, start, wait, stop, final check) were adapted from that folder's `cluster-run.sh`. Neither source file was changed. Every value and band was derived again here from source; none was taken from another case file or results file |
| **Instrument checks** | Byteman: `TestScript` type-checked all three node rules (`run1/typecheck-node-rules.txt`, "no errors"). Unit: the test classes compiled in the clone (`ant build-test` exit 0). The unit shakedowns gave the known-answer `w` and showed the D1 instrument problem. Two cluster shakedowns (40,000 ops, 16 MiB, short windows) exercised every step and the self-check end to end: unit self-check 65/65 exit 0 on shake3; cluster self-check 31/33 exit 1 on shake2, where the 5-s plateau start falls before stress begins its operations, a scale artefact (`run1/shake/`) |
| **Tiers and values** | Unit: `WeightedQueue` and `BinLog` with M ∈ {1, 8, 64, 256 (default)} MiB, offering `ceil(2M/w)` records of w = 4,281 B. Overweight run at M = 64 KiB; guard and leak runs at M = 1 MiB; controls with M = `Integer.MAX_VALUE` and a plain `LinkedBlockingQueue`. Cluster: one node, FQL with `--blocking false` and M ∈ {16, 128, 256 (default), 1024} MiB under a 50-ms-per-batch Byteman writer delay. Blocking pass at 128 MiB. Positive control at 1 GiB without Byteman |
| **Audit bottom line** | **Ready after amendments** — 2026-10-27 |

### 1.1 Design audit

| Group | Check | Rating | Note (section checked) |
|---|---|---|---|
| A | constrained quantity is memory or disk bytes | Met | A2/B1: the estimated bytes of queued bin-log records (heap, plus Netty direct memory by default) |
| A | knob varied, ≥ 3 values incl. default | Partly → Met after U2/C2 | Filed: 1/8/64 MiB (unit) and 16/128/1024 MiB (cluster), without the default. U2/C2 add 256 MiB to both tiers |
| A | real resource measured, not only the counter | Partly → Met after U2/C3 | The options buffer is pooled **direct** by default (`CBUtil.java:59-60`, `FullQueryLogger.java:485`), so B2f's "heap delta ≈ W" could not hold. Both tiers now run with `-Dcassandra.netty_use_heap_allocator=true` so the whole record is on the heap. B3d's jstat cannot attach on this host, so it is replaced by `GC.class_histogram` (N_q and live heap); ΔH is measured around `disablefullquerylog`. Gap named: the default pooled direct memory is not measured |
| A | usage driven to the limit and past it | Partly → Met after C2 | Unit: 2 × M offered. Cluster: the filed n = 400,000 with an unthrottled rate might end before the 60-s plateau window. C2 sets the rate to 5,000/s (B3c's own assumption) and n = 500,000, so the 1 GiB cap (about 53 s to fill) is reached inside the window |
| B | each step says what it establishes | Met | B2g/B3g rows; B2h/B3h controls |
| B | prediction in numbers | Partly → Met after U4/C5 | Filed values were "≈". U4/C5 give exact floors and bands derived from source: +16 for the writer batch (`BinLog.java:248-256`) and up to one record per request thread (`Config.java:283`) |
| B | every plausible outcome has a row | Partly → Met after U5/C6 | Invalid and Not-confirmed rows and the order of checking were added |
| B | confirmation needs ceiling-follows-knob and direct branch evidence | Met | Unit: refused offers after the first refusal, and IAEs at the throwing lines. Cluster: "Dropped N binary log samples" lines (`BinLog.java:337-342`) and the op rate collapsing under blocking |
| B | alternative explanations and controls | Met | No-Byteman control (the backlog needs the slow writer); `Integer.MAX_VALUE` and LBQ controls (the workload can move heap) |
| C | a human can follow it | Met | A3 + B1 |
| C | an AI can run it without re-deriving | Partly → Met after U3/C4 | Exact classes, output lines, sequence, gaps, abort conditions |
| C | values, commands, observables exact | Partly → Met after C2/C3 | Stress command, histogram parsing, MQWP/MQWW lines |
| D | prerequisites exist or are listed | Met after U1/C1 | `/local` replaced by `$W`; tracked background process instead of `setsid`; `_JAVA_OPTIONS=-Xmx4g` (`build.xml:1153` sets `maxmemory="1024m"`) |
| D | workload arithmetic | Met | ≤ 1.1 GB queued in a 4 GB heap; 2 GB of stress data per run on 118 GiB free; about 20 min of node time |
| D | citations spot-checked | Met | `WeightedQueue.java:53-60, 72-105, 136-165, 242-252, 264-333`; `BinLog.java:73-74, 133-150, 174-228, 230-292, 295-342, 398-403, 431-474`; `FullQueryLogger.java:91-133, 159-182, 303-371, 468-560`; `CBUtil.java:59-60`; `QueryOptions.java:62-64`; `StorageService.java:7131-7146`; `EnableFullQueryLog.java:25-75`; `BinLogOptions.java:49` |

| # | Recommendation | Applied? | Why |
|---|---|---|---|
| U1 | host clone, build, harness classes, `_JAVA_OPTIONS=-Xmx4g` | applied 2026-10-27 | no `/local`; the test heap is capped at 1 GiB by `build.xml:1153` |
| U2 | default 256 MiB; heap allocator in the test JVM; heap-delta definition; control offer count | applied 2026-10-27 | ≥ 3 values incl. default; B2f's heap delta needs the buffers on the heap |
| U3 | exact procedure and `MQW` lines; guard calls through `offer`, timed `offer` and `put` (reaching both `:283` and `:305`) | applied 2026-10-27 | B2e step 3 reached only `:305` |
| U4 | exact predictions (floors, bands) | applied 2026-10-27 | "≈" values made exact; no filed relation changed |
| U5 | verdict words and order (unit) | applied 2026-10-27 | B2g had no Invalid / Not-confirmed rows |
| C1 | host node, paths, agent line, cleanup | applied 2026-10-27 | host |
| C2 | default 256 MiB; throttled stress n = 500,000; `duration=100s` for the blocking pass | applied 2026-10-27 | reach every cap inside the plateau window |
| C3 | histogram N_q and live heap; heap allocator on the node; ΔH around disable; MQWP/MQWW; drop lines; steady op rate | applied 2026-10-27 | jstat unavailable; the real resource must be visible |
| C4 | exact sequence, 65-s gap (NoSpam window), blocking pass before the control | applied 2026-10-27 | exactness; one restart |
| C5 | exact bands | applied 2026-10-27 | numbers |
| C6 | verdict words and order (cluster) | applied 2026-10-27 | missing outcomes |
| R1 | measure the default pooled direct case (e.g. `CBUtil.allocator.metric()` with small arenas) | left for stage 3 | outside this design |

## 2. Environment

| Field | Run 1 |
|---|---|
| Date | 2026-10-27 (unit 12:58–12:59, cluster 12:59–13:18 EDT) |
| Node | `yangwang-mbp` (advisor's laptop), single host, 10 cores, 32 GiB |
| OS and kernel | macOS 27.0.1 (26A434) / Darwin 27.0.0 arm64 |
| JDK | OpenJDK 11.0.32.1 (Homebrew) |
| Ant | 1.10.18 |
| Clone commit | `$W/cassandra-run62` (`W=~/Library/Caches/stage4`), `b5f2a54210d541339c2e7c17a794195cac0e67c2`, `cassandra-5.0.9`; `ant -Dlocal.repository=$W/m2 build-test` succeeded in 57 s |
| Case-file / harness commit | uncommitted (repo HEAD `9ed1823`); case-file sha256 values in §1 |
| Storage | internal SSD, APFS, 118 GiB free; node dir `$W/node-mqw` (wiped after) |
| Loopback | 127.0.0.1–.3 present (only .1 used) |
| Full logs | `$W/logs/max_queue_weight-acquireWeight-weight--autonomous/` (`unit-shake`, `unit-shake2`, `unit-shake3`, `unit-r1`, `cluster-shake`, `cluster-shake2`, `cluster-r1`; raw class histograms under `cluster-r1/<run>/hist-*.txt`) |

**Machine lessons relied on.**
- Workspace and environment: `$W` and `env.sh`; every ant call with `-Dlocal.repository=$W/m2`; unsandboxed commands.
- Starting the node: there is no setsid, so the node runs as a tracked background process (`nohup … &; disown`).
- Heap measurement: `jstat` cannot attach, so `GC.class_histogram` live totals were used. A full GC runs before each heap reading, and ΔH is taken between two consecutive histograms, not against a drifting baseline.
- Off-heap visibility: Netty pooled direct arenas commit 16 MiB chunks (`maxOrder=11`). Both JVMs therefore ran with `-Dcassandra.netty_use_heap_allocator=true`, which makes the buffers exact-size heap buffers.
- Unit test JVM: `-Dtest.jvm.args` reaches the forked test JVM, and a heap above 1 GiB needs `_JAVA_OPTIONS` (`build.xml:1153`). The CMS test JVM reports `maxMemory` 4,277,534,720 for 4g (not used by any band). Test stdout lands in `build/test/logs/_jdk11/TEST-<class>.log`, and that file is appended across runs (`unit-run.sh` deletes it first).
- Stress: `no-warmup` was given. `nodetool disableautocompaction` does not survive a restart, which is harmless because the control after the restart has no ΔH band.
- Protocol habits: a shakedown before run 1; `selfcheck.py` written before the readings and run end to end on the shakedowns, with the exit status checked; long steps run in the background and polled; the daemon class name kept out of pkill patterns; no `cassandra.logdir_IS_UNDEFINED/` left in the clone.

## 3. Runbook defects

| # | Run | Step | Problem | Fix | Decision (date) | Case-file version with the fix |
|---|---|---|---|---|---|---|
| D1 | unit shakedown (before run 1) | U2(c) heap delta | The heap delta was `Runtime` used bytes read 200 ms after the last `System.gc()`. It also counts what background threads allocated in eden since that GC. The first shakedown read `dH/W = 1.4415` at M = 1 MiB (+465 KB) but 0.996 at 8/64/256 MiB (`run1/shake/unit-shake1and2-CAP-lines.txt`) | Heap = Σ `MemoryPoolMXBean.getCollectionUsage().getUsed()` over the heap pools, read right after the last of three `System.gc()` calls. The test JVM's CMS runs `System.gc()` stop-the-world (`build.xml:231-243`). Bands unchanged | fixed 2026-10-27; unit tier not yet run | `7198059f…` |
| D2 | cluster shakedown (before run 1) | C5 "w_obs = the MQWW values (all equal)" | FQL also logs the driver's metadata queries when stress connects. The first MQWW value was 182 B (`run1/shake/cluster-shake-M16M-mqw-lines.txt`) | w_obs = MQWW values ≥ 4,096 (records that carry the stress value); the others are reported with their count. Bands unchanged | fixed 2026-10-27 | `7198059f…` |
| D3 | cluster shakedown (before run 1) | C5 "samples taken while stress runs" | The stress JVM outlives its last operation by a few seconds. Meanwhile the writer drains the queue: MQWP permits rose while the process was still alive, and the shakedown's last blocking sample read 30,645, below the band (`run1/shake/cluster-shake-B-samples.txt`, `-B-mqwp.txt`) | A plateau sample is one whose histogram ended before stress printed `Results:` (recorded per sample). Bands unchanged | fixed 2026-10-27 | `7198059f…` |

Harness bugs fixed during the shakedowns (no case-file change): the closing `*/` inside a Javadoc path (compile error); `-newer` used on the growing command log (TEST logs not found); TEST logs appended across runs (now deleted before each class); the `MQW` lines are written through the test logger, so they are prefixed, and `grep '^MQW'` became `grep 'MQW '`.

## 4. Run 1

**Command logs:** `max_queue_weight-acquireWeight-weight--autonomous/run1/unit/commands.log`, `run1/cluster/commands.log`.

### 4.1 Readings

**Unit tier** (`run1/unit/summary.txt`, `run1/unit/TEST-*-MQW.txt`). `ant` exit 0 for both classes (5 + 1 tests, 0 failures). Both `MQW ENV` lines show `io.netty.buffer.UnpooledByteBufAllocator useHeap=true`. All records weigh w = 4,281 B (`wmin = wmax`).

| M | floor(M/w) | `WeightedQueue` nAcc | W | M − W | permits | first refusal / accepted after it | dH (B) | dH/W | `BinLog` nAcc (writer blocked, permits before = M) | BinLog drain |
|---|---|---|---|---|---|---|---|---|---|---|
| 1 MiB | 244 | 244 | 1,044,564 | 4,012 | 4,012 | 244 / 0 | 1,040,416 | 0.9960 | 244 | restored (31 ms) |
| 8 MiB | 1,959 | 1,959 | 8,386,479 | 2,129 | 2,129 | 1,959 / 0 | 8,353,176 | 0.9960 | 1,959 | restored (39 ms) |
| 64 MiB | 15,675 | 15,675 | 67,104,675 | 4,189 | 4,189 | 15,675 / 0 | 66,838,200 | 0.9960 | 15,675 | restored (104 ms) |
| 256 MiB | 62,703 | 62,703 | 268,431,543 | 3,913 | 3,913 | 62,703 / 0 | 267,365,488 | 0.9960 | 62,703 | restored (381 ms) |

| Sub-run | Reading |
|---|---|
| Overweight (M = 65,536) | wbig 131,257: first offer `true`, permits 0; small offer (4,281) `false`, permits 0; after polling the big record, permits 65,536 |
| Guards (M = 1,048,576) | weight 0 and −1: `offer` → IAE at `tryAcquireWeight:307`; timed `offer` and `put` → IAE at `acquireWeight:285`; permits 1,048,576 after each of the six |
| Leak (M = 1,048,576) | offer `true`, permits 1,048,571; weight set to 0; `poll()` → IAE at `releaseWeight:326`; permits 1,048,571; next `poll()` `null`, permits 1,048,571 |
| Control `Integer.MAX_VALUE` | 125,408 of 125,408 accepted, W 536,871,648, dH 534,742,168 (0.9960); quarters +133.7 / +133.7 / +133.7 / +133.7 MB |
| Control LBQ | 125,408 records, dH 534,741,176, 4,264.0 B per record (w 4,281) |

**Cluster tier** (`run1/cluster/<run>/samples.txt`, `hist-excerpts.txt`, `mqw-lines.txt`, `drops.txt`, `full-summary.txt`, `empty-summary.txt`, `stress-*.txt`, `summary.txt`). Every stress run: 500,000 writes (the blocking pass ran 100 s), 0 errors, about 4,950 op/s. The node ran G1 with `-Xms4G -Xmx4G` and `-Dcassandra.netty_use_heap_allocator=true`; the Byteman agent was loaded in phase 1 and not in the control (`node/jvm-args.txt`). system.log has 0 `ERROR` lines. w_obs = 4,366 in every Byteman run; one 166-B record appeared in the 16 MiB run (D2). MQWP `maxWeight` = M in every Byteman run.

| Run | M | floor(M/w_obs) | Band | Plateau N_q (9 samples, t ≥ 60 s) | Drop lines | N_q_full | ΔH = H_full − H_empty (B) | ΔH / (N_q_full · w) |
|---|---|---|---|---|---|---|---|---|
| M16777216 | 16 MiB | 3,842 | [3,826, 3,986] | 3,858 ×8, 3,853 | 2 | 1,874 | 8,020,464 | 0.9803 |
| M134217728 | 128 MiB | 30,741 | [30,725, 30,885] | 30,757 ×7, 30,748, 30,752 | 2 | 28,725 | 122,943,904 | 0.9803 |
| M268435456 | 256 MiB (default) | 61,483 | [61,467, 61,627] | 61,499 ×9 | 2 | 59,627 | 255,203,280 | 0.9803 |
| M1073741824 | 1 GiB | 245,932 | [245,916, 246,076] | 245,948 ×9 | 1 | 244,220 | 1,045,262,344 | 0.9803 |
| B134217728 (blocking) | 128 MiB | 30,741 | [30,725, 30,885] | 30,821 ×8, 30,805 | 0 | 28,965 | 123,971,072 | 0.9803 |
| CTRL1073741824 (no Byteman) | 1 GiB | — | N_q ≤ 999 | max 2 over 22 samples | 0 | 0 | — | — |

Median plateau ratios: 30,757 / 3,858 = 7.9723 (×8); 61,499 / 30,757 = 1.9995 (×2); 245,948 / 61,499 = 3.9992 (×4).
Blocking pass steady op rate (interval rows from 30.0 s to 100.6 s): 280.8 ops/s; the total was 58,945 ops in 100 s.
Drop lines read "Dropped 1 binary log samples" at the first refusal, then for example "Dropped 282447 binary log samples" one minute later (`node/binlog-lines.txt`).
In the 16 MiB run, MQWP read 3,044 permits at 91 of 99 writer batches, which is M − 3,842 · 4,366.
The 1 GiB queue was still filling at 55.1 s (235,415) and full by 60.1 s.

### 4.2 Conclusion and logic

1. **Validity.**
   - Unit: both classes ran to the end, all `MQW` lines are present, the allocator is the unpooled heap one, and `writerBlocked = true` at every M [observed: `run1/unit/summary.txt`].
   - Cluster: every stress run had 0 errors; each Byteman run has 9 plateau samples; `maxWeight` = M and w_obs = 4,366 is in [4,200, 4,500]; no abort; the run parameters are the frozen ones [observed: `run1/cluster/summary.txt`, `params.txt`, `<run>/mqw-lines.txt`].
   - The FQL configuration was read back by `getfullquerylog` and by the `Attempting to configure bin log … Max queue weight: M` line [observed: `<run>/getfullquerylog.txt`, `binlog-config.txt`].
   - Valid.
2. **Readings.**
   - Every blocking=false plateau sits exactly 16 records above floor(M/w) (3,858 = 3,842 + 16, and so on). The few lower samples (3,853, 30,748, 30,752) caught producers between a writer batch and the refill [observed: samples]. The +16 is the writer's batch, whose permits were released when the records were taken [inferred: `BinLog.java:254-256`, `WeightedQueue.java:100-105`].
   - Under blocking the plateau is 30,821 = 30,741 + 16 + 64: the 64 stress connections each hold one record in `put()` [inferred: `BinLog.java:221-227`, 64 stress threads].
   - The retained heap per record is 0.980 · w in all five runs (about 4,280 B per record against w = 4,366) [observed]. The weight counts the shared prepared-statement string once per record [inferred: `FullQueryLogger.java:369`].
3. **Matched rows.**
   - Unit: B2g rows 1, 3 and 5, by U5(4) "every U4 value holds" [observed: unit table; self-check 65/65]. W ≤ M and M − W < w at every M; nAcc = floor(M/w), scaling 8.03 / 8.00 / 4.00; dH/W 0.9960; the overweight element was admitted alone; six IAEs at lines 307/285 with permits intact; the leak left permits at M − 5.
   - Cluster: B3g rows 1, 4 and 5, by C6(4) "every C5 band holds" [observed: cluster table; self-check 69/69]. Plateaus are in band and follow M (ratios within 0.4% of ×8/×2/×4); drops appear in every blocking=false run; ΔH ratio 0.980; the control's N_q ≤ 2 with no drops; under blocking N_q is in band, there are 0 drops and the steady rate is 281 ops/s.
4. **Excluded rows.**
   - Unit row 2 (Refuted): W ≤ M everywhere and nAcc changes ×8/×8/×4.
   - Unit row 4 (Refuted, guard missing): all six bad weights threw.
   - Unit row 6 (Not confirmed, heap ≫ W): dH/W = 0.996.
   - Unit Not confirmed (leak absent): permits stayed 1,048,571.
   - Cluster row 2 (Refuted, cap bypassed): no plateau sample above floor + 16 in blocking=false runs, against the band's +144.
   - Cluster row 3 (flat across M): medians span 3,858 to 245,948.
   - Cluster row 6 (native or heap far beyond N_q · w): ΔH ratio 0.980.
   - Cluster Not confirmed (control large): the control maximum was 2.
   - Invalid: §4.2.1.
5. **Inferred statements the conclusion depends on.**
   - (a) The heap-allocator flag moves only where the options buffer lives (`CBUtil.java:59-60`); `WeightedQueue` and `BinLog` are unchanged, so the cap readings apply to the default allocator. The default's direct-memory footprint is not measured (named gap, R1).
   - (b) The `Query` instance count in a live class histogram counts every queued, in-batch and in-construction record. Its agreement with MQWP (permits 3,044 = M − 3,842 · w) supports this.
6. **Deviations and gaps.**
   - D1–D3 were fixed before run 1.
   - The optional NMT step was not run (C3).
   - The blocking pass ran before the control (C4).
   - At the 16 MiB run, 1,874 of about 3,858 records were left by the time of `H_full`, because the writer drains about 320 records/s during the flush. The ratio is computed against `N_q_full` from the same histogram, as C3 defines it.
7. **Core question.**
   - Usage follows the knob: the queued record count, and with it the queued heap, equals floor(M/w) plus the writer's batch of 16 at every M from 1 MiB to 1 GiB. That is exact in the unit tier and within 16 records on the node (parts 3 and 2).
   - The retained heap equals 0.98 × the counted weight (part 3).
   - The disallow branch fired directly: refused offers in the unit tier, drop warnings with about 282,000 drops per minute on the node, and back-pressure to 281 ops/s under blocking (part 3).
   - `max_queue_weight` caps the bin-log queue's memory at M plus a small, bounded overshoot (one overweight element; 16 records in the writer's batch; one record per blocked producer). It does so only while the writer is behind: the no-Byteman control never queues more than 2 records (part 4).
   - The target guards reject weight < 1 on both admission paths (`:283` and `:305`). At `:324` a weight that falls to 0 after admission leaks its permits, so the cap shrinks.

**Conclusion (one line):** unit B2g rows 1, 3, 5 — confirmed; cluster B3g rows 1, 4, 5 — confirmed.

## 5. Self-check of run 1 — AI

`run1/selfcheck.py` was written before run 1 and checked end to end on the shakedowns. It re-parses the raw TEST logs (unit). For the cluster it re-parses every raw class histogram (`hist-*.txt`, `full.txt`, `empty.txt`), comparing each with `samples.txt`, plus the stress outputs, the system.log excerpts and the Byteman lines. It recomputes floors, bands, ratios and the steady op rate on its own and judges against U4/U5 and C5/C6. Results: **unit 65/65 pass, exit 0** (`run1/selfcheck-unit.out`); **cluster 69/69 pass, exit 0** (`run1/selfcheck-cluster.out`).

| Part | Holds? | Note (file re-read) |
|---|---|---|
| 1. Validity | yes | `run1/unit/summary.txt` ENV lines; `run1/cluster/summary.txt` stress lines (0 errors ×7); `params.txt`; `M*/mqw-lines.txt` maxWeight |
| 2. Readings | yes | Re-read `M16777216/samples.txt`: 3,858 with column 7 = 0 from 10.1 s to 100.1 s; 3,853 at 70.1 s. `B134217728/samples.txt`: 30,821 ×8 |
| 3. Matched rows | yes | `M1073741824/hist-excerpts.txt`: `Query` 245,948 from sample 12 on; `full`/`empty` totals give ΔH 1,045,262,344 |
| 4. Excluded rows | yes | No plateau value above floor + 16 (blocking=false); control `samples.txt` max 2 |
| 5. Observed vs inferred | yes | (a) is the named gap R1; (b) checked against the MQWP permits (3,044 = 16,777,216 − 3,842 · 4,366) |
| 6. Deviations and gaps | yes | D1–D3 recorded with evidence under `run1/shake/` |
| 7. Core question | yes | The logic follows B1: the ceiling follows M, the disallow evidence is direct, and the real heap matches the weight |

### 5.2 Run 2?

**No** (2026-10-27). Both tiers rest on exact or near-exact observed equalities: unit floors exact, node plateaus within 16 records, ΔH ratio identical across five runs. The two inferred statements are a named scope gap and an instrument cross-check that a second run with the same instruments would not change. The result neither refutes the case nor confirms a bypass.

## 6. Run 2

Not done.

## 8. Verdict — AI

**Stage-3 estimate:** positive.

**Claim tested (B1):** with the bin-log writer slower than the producers, the estimated weight of records queued in a `BinLog` never exceeds `max_queue_weight` plus one record. The writer's in-flight batch of ≤ 16 comes on top. On a node, the heap retained by the full-query-log backlog grows with `max_queue_weight` and plateaus at about `max_queue_weight`. A weigher result < 1 is rejected (`:283`/`:305`) and, on removal (`:324`), leaks permits.

| Tier | Verdict | Effect on the constraint | Basis | Date |
|---|---|---|---|---|
| Unit | **Confirmed** (B2g rows 1, 3, 5; U5(4)) | caps (nAcc = floor(M/w) exactly; heap 0.996 × W) | run 1 + self-check | 2026-10-27 |
| Cluster | **Confirmed** (B3g rows 1, 4, 5; C6(4)) | caps (queue = floor(M/w) + 16 writer batch; heap 0.98 × weight; drops / back-pressure) | run 1 + self-check | 2026-10-27 |

**Feedback filed:** case file section D updated (2026-10-27, uncommitted). No section was amended by the result; the audit amendments U1–U5 and C1–C6 and the defect fixes D1–D3 are in the case file. In `_INDEX.md`, the §1 Stage 4 column and the §2 rows were filled.
