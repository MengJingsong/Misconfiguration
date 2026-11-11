# maximumPoolSize-setMaximumPoolSize-deltaWorkPermits--autonomous — stage-4 results  <!-- file: results/maximumPoolSize-setMaximumPoolSize-deltaWorkPermits--autonomous.md -->

> **Case:** [`maximumPoolSize-setMaximumPoolSize-deltaWorkPermits--autonomous`](../../stage3-ai-deep-read/cases/maximumPoolSize-setMaximumPoolSize-deltaWorkPermits--autonomous.md)
>
> **Status:** **Closed 2026-10-22. Unit: Confirmed — does not cap. Cluster: Not confirmed (no matching row) — undetermined.** Heap after GC in the read phase is 418 / 512 (474 repeat) / 522 MiB at n = 4 / 32 / 256 (max/min 1.249): outside the frozen "about equal" band (1.15) and outside the refuting band (monotone and >= 1.5). RSS is flat (1.022), Active never exceeds n, Pending at n = 4 is 121 against 1 at n = 256, and both controls moved. No run 2.
> 
> **Outcome class:** undetermined — stage-3 estimate vs the stage-4 effect on the constraint
>
> **Agent:** autonomous. "§9a" below means B2f/B2g (unit) and B3f/B3g (cluster), "§9b–§9e" means B2a–B2e or B3a–B3e, and the case file's feedback section is its section D.

## 1. Before run 1 — design audit and freeze

| Field | Content |
|---|---|
| **Case-file version** | Autonomous file, untracked (repo HEAD `00922e0`). As filed: sha256 `2054f1d98e8f6fa75d3dba0312219fac7bae8fb8c6d865bb5b675473218f7083`. After the step-0 audit amendments U1–U4, C1–C7 (2026-10-22 09:47 EDT): the **frozen version** is `d75be538594cb471519b38d89e005c80b4949f461bb380b576d6bef021a5f22c`. Runbook fixes D1 (thread names, GC cause) and D2 (heap after GC from the class histogram; G1 young-size and IHOP options), both found by cluster instrument checks before any run-1 reading, with B1 and every prediction and row unchanged, give **`c2e4c4939ddcae0d6a1a8d2660dd54a0b38c56de90055f648389d9adec04d8e5`, the version run 1 used** (the unit tier is unaffected by D1 and D2; the unit tier ran 10:56 with the same file apart from them). The case file is untracked. |
| **Harness** | [`harness/maximumPoolSize-setMaximumPoolSize-deltaWorkPermits--autonomous/`](../harness/maximumPoolSize-setMaximumPoolSize-deltaWorkPermits--autonomous/README.md), written 2026-10-22, not committed: `SepCapProbe.java`, `unit-run.sh`, `unit-analyze.py`, `make-node-yaml.sh`, `Jmx.java`, `cluster-run.py`, `selfcheck.py`. **Instrument checks (not readings):** `javac` of the probe; a 3-rep unit shakedown (found that variant A's tasks must release their buffers, and the pool-thread count); a 4-lifetime and an 8-lifetime cluster shakedown at small sizes (`~/stage4-logs/mps2/shakedown*/`; found D1 and D2; three further n = 256 checks compared GC settings). md5 of the run copy is in `~/stage4-harness-run/mps2.md5`. |
| **Tiers and values** | Unit (B2): `SharedExecutorPool.newExecutor` n = 1 · 4 · 32 · 128, variants A (T = 2000, 1 MiB allocated by the running task) and B (T = 600, 1 MiB allocated at submit), byte-queue control (`ThreadPoolExecutor`, queue 64) at n = 4 · 32 · 128, and the resize sequence 4 → 32 → 32 → 32 → 8; three JVM repetitions. Cluster (B3): `concurrent_reads` = `concurrent_writes` = n ∈ {32, 4, 256, 32 again}, write n = 3,000,000 × 1 KiB then 10 min mixed 1:3, 3 min idle, 400 client threads; a runtime lifetime (same value 32, then 8, 64, 32 on both stages); in-flight controls PC0/PC (256 MiB vs 128 KiB); memtable controls M64/M256. |
| **Audit bottom line** | **Ready after amendments** — 2026-10-22 |

### 1.1 Design audit

| Group | Check | Rating | Note (section checked) |
|---|---|---|---|
| A. Core question | constrained quantity is memory or disk bytes | Partly | A2: the quantity is a count (work permits), not bytes. The claim (B1) is that the memory held by queued or running work is not bounded by it, so the measured quantity is heap (after GC), RSS and thread stacks (256 KiB each, `jvm-server.options:123`). That is a count with a derivable byte size (thread stacks) plus the unbounded queue: acceptable for a negative-estimate file. |
| A. Core question | knob varied, ≥ 3 values incl. default | Met | B2b n = 1 · 4 · 32 · 128 (32 is the default) and the resize sequence; B3b n = 4 · 32 · 256 and a runtime path. |
| A. Core question | real resource measured, not only the counter | Met | B2d heap after GC and NMT Thread; B3d heap after GC, RSS, threads. Per-task memory is not separable (named in B3d). |
| A. Core question | usage driven to the limit and past it | Partly → amended | Unit: T ≫ n everywhere (Met). Cluster: 400 client threads against n = 4 and 32; at n = 256 the pool is not expected to bind (B3f). C5 defines "limit reached" as median Pending ≥ 20 at n = 4. |
| A. Core question | positive control (negative estimate) | Partly → amended | Unit: bounded queue (Met). Cluster: B3h's `native_transport_max_request_data_in_flight` of "e.g. 4 MiB" cannot bind at about 0.5 MiB in flight, and the 1 MiB per-connection receive queue absorbs requests first. C7 sets 128 KiB with the receive queue at 0B, plus the memtable control (64/256 MiB) on heap. |
| B. Logic | each step says what it establishes | Met | B2e/B3e, B2g/B3g. |
| B. Logic | prediction in numbers or a clear relation | Partly → amended | Variant A/B bands, Pending ">>", "nearly identical (10–15 %)", "a few tens of MiB" were undefined: U3 and C5 define them without changing a number. |
| B. Logic | every plausible outcome has a conclusions row | Partly → amended | Missing: repeat disagreement (U4a), the shrink reading (U4b), the n = 32 noise (C6a), Active > n (C6b), the changed value without a "Resized" line (C6c), saturation (C6d), the combined rule (C6e). |
| B. Logic | confirmation needs ceiling-follows-knob and direct disallow evidence | Met | Unit: active = min(n, T) with pending = T − n (the refusal at `takeWorkPermit`) and the shrink leaves the running tasks running; cluster: Active ≤ n at 1 s resolution and the node's own "Resized" lines. |
| B. Logic | alternative explanations and their controls | Partly | Memtable growth (the memtable control), GC (full-GC check, C4), noise (the repeat). Per-running-task memory that scales with n is part of the claim (Variant A, "linearly and indirectly") and is read in the unit tier. |
| C. Specific | a human can follow it from the intro and §9a | Met | header, A3, B1. |
| C. Specific | an AI can run B2/B3 without re-deriving the code path | Partly → amended | B3b/B3e used `setconcurrency <stage> 0 <n>`, which the node rejects (C1). B3c's "n=3,000,000" and "10 min" conflict (C3). |
| C. Specific | knob, values, workload, commands, observables, sampling, stop conditions exact | Partly → amended | C2–C4. |
| D. Runnable | harness and environment prerequisites exist or are listed | Met | `~/cassandra-mps2` built with `ant build-test` (1 min 15 s). No Byteman is needed. |
| D. Runnable | workload arithmetic reaches the limit | Partly → amended | B2c's variant B at T = 600 needs 1,200 of 1,024 one-MiB G1 regions at `-Xmx1g` (U1). B3: 3 M × 1.1 KiB ≈ 3.3 GB per lifetime; 50 GB free; ten lifetimes need about 90 min of load. |
| D. Runnable | load-bearing citations spot-checked against the pinned clone | Met | `SEPExecutor.java:50-110, 335-350, 357-360, 368-396` (line 384 is `if (deltaWorkPermits == 0)`, 388 the log, 395 the listener); `Stage.java:259-262, 275-277`; `StorageService.java:2397-2403`; `SetConcurrency.java:46-60`; `SharedExecutorPool.java:67, 96, 141-153`; `SEPWorker.java:58, 125`; `Config.java:179-182, 296-302, 524`; `conf/jvm-server.options:123`. All as cited, except A1's remark that all workers are `SharedPool-Worker` (D1). |

| # | Recommendation | Applied? | Why |
|---|---|---|---|
| U1 | unit JVM `-Xmx2g`, 4 MiB G1 regions, run with `java` | Applied 2026-10-22 09:47 | humongous 1 MiB arrays; testsome forces 1024m + CMS |
| U2–U3 | three JVMs; terms and numbers for the readings | Applied | B2e repeats were not a procedure; "≈" undefined |
| U4 | rows for repeat disagreement, shrink misread, closures not holding | Applied | outcomes without a row |
| C1 | `setconcurrency <stage> <n>` (two arguments) | Applied | the three-argument form throws (`SEPExecutor.java:357-360`) |
| C2 | both knobs set together; order 32, 4, 256, 32; runtime lifetime with same-value call | Applied | B3b/B3e ambiguity |
| C3 | exact stress commands, quoting, paths | Applied | "n=3,000,000" and "10 min" cannot both bound a phase |
| C4 | instruments: GC.run + heap_info, RSS, NMT, JMX, thread counts | Applied (corrected by D1) | `jstat -gc` has no post-GC value |
| C5–C6 | definitions of the statistics and extra rows | Applied | undefined terms, outcomes without a row |
| C7 | control values 128 KiB / receive queue 0B / memtable 64, 256 MiB; the key names verified | Applied | the filed 4 MiB cannot bind at about 0.5 MiB in flight; the key `native_transport_max_request_data_in_flight` (and `_per_ip`) is right (`Config.java:296-298`, `DataStorageSpec.LongBytesBound`, default null, absent from the shipped yaml) |
| S1 | B3 runs only `MutationStage`/`ReadStage`; `Native-Transport-Requests`, `RequestResponseStage` and the other SEP executors are not tested | Left for stage 3 | outside this design |

**Environment deviation E1 (not an amendment):** the node runs on 127.0.0.5 with JMX 7205 (Byteman port 9095 unused), the clone is `~/cassandra-mps2`, node directories are under `~/stage4-mps2/node1`, and the host is shared with another stage-4 agent (127.0.0.4/.7), so CPU and disk are shared (load average 14–15 at the unit shakedown).

**Agreement criteria** — not filled (no run 2).

## 2. Environment

| Field | Run 1 | Run 2 |
|---|---|---|
| Date | 2026-10-22 EDT. Unit 10:56:21–10:58:38. Cluster 11:00–12:26:04 (nine lifetimes, one chain). | not done |
| Node | `pc07` = `node0.jason92-320876` (40 cores, 251 GiB), run directly. **Shared with another stage-4 agent** (its Java processes ran throughout; load average 49.6 / 45.6 / 31.8 at chain start), so CPU and disk were shared: a deviation for every throughput reading. E1: 127.0.0.5, JMX 7205, `~/cassandra-mps2`, `~/stage4-mps2/node1`. | — |
| OS / kernel | Ubuntu 22.04.2 LTS, `5.15.0-187-generic` | — |
| JDK / Ant | openjdk 11.0.32.1 (2026-08-18) / Ant 1.10.12 | — |
| Clone | `~/cassandra-mps2` at `cassandra-5.0.9` (`b5f2a54210d541339c2e7c17a794195cac0e67c2`), `ant build-test` 1 min 15 s; nothing added to it (the probe is compiled into `~/stage4-mps2/probe`) | — |
| Case file / harness | case file untracked, sha256 `c2e4c493…` (run 1), frozen `d75be538…`; harness not committed, md5 in `run1/harness.md5` | — |
| Storage | `~/stage4-mps2/node1` on local `/dev/sda3` (52 GB free, 52.1 at the end); removed after the run | — |
| Full logs | `pc07:~/stage4-logs/mps2/run1/` (`unit/`, `cluster/`: `session.log`, samplers, `stress-*`, `system-/debug-/gc-compact-<lifetime>.log`, `phases.json`); shakedowns `~/stage4-logs/mps2/{shakedown,shakedown2,gctest-*}/` | — |

## 3. Runbook defects

| # | Run | Step | Problem | Fix | Decision | Case-file version |
|---|---|---|---|---|---|---|
| C1 | audit + cluster check | B3b, B3e step 6 | `nodetool setconcurrency <stage> 0 <n>` is rejected: "Unable to set concurrency: Cannot resize core pool size of SEPExecutor", exit 1 (read live on the check node). | two-argument form (amendment C1) | 2026-10-22, §9a unchanged | `d75be538…` |
| D1 | cluster check | B3d | the audit's C4 said SEP workers are all named `SharedPool-Worker-<id>`; `SEPWorker.java:125` renames a running worker to `<executor>-<id>`, so my own thread count returned 0. `jcmd GC.run` is logged as `Pause Full (Diagnostic Command)`. | JMX `ThreadCount` plus `ReadStage-`/`MutationStage-`/`SharedPool-Worker-` counts; the full-GC check excludes that cause | 2026-10-22 | `9f1c742c…` |
| D2 | cluster checks | B3d, B3a/B3h | (a) `GC.run` + `GC.heap_info` read the live set plus the allocation since the GC: 1,456 MiB against 399 MiB for the same state. (b) with the tag's G1 settings, 21 `Pause Full (G1 Evacuation Pause)` in 2.5 min at n = 256. | heap after GC = `GC.class_histogram` Total; `-XX:G1NewSizePercent=20 -XX:G1MaxNewSizePercent=30 -XX:InitiatingHeapOccupancyPercent=30` in every lifetime (first try `G1MaxNewSizePercent=25` alone and the experimental-flag error showed the tag's `G1NewSizePercent=50` wins unless the option is appended to `jvm11-server.options`) | 2026-10-22 | `c2e4c493…` |
| H1 | unit check | B2c | variant A's tasks kept their buffers in the registry after release, so 2,000 × 1 MiB filled the 2 GiB heap (OOM); the pool-thread count by name matched nothing (same renaming). | tasks remove their buffer at release; count by thread group | harness only | — |
| H2 | cluster analysis | C7(i) | the analysis multiplied a KiB figure by 1024. | corrected before run 1 | harness only | — |

## 4. Run 1

**Scope:** unit B2: 3 JVMs × (variant A and B × n = 1 · 4 · 32 · 128, control × n = 4 · 32 · 128, the resize sequence). Cluster B3: lifetimes n32, n4, n256, n32b (write 3 M × 1 KiB, mixed 10 min, idle 3 min), RS (runtime changes), PC0, PC, M64, M256. **Excerpts:** [`maximumPoolSize-setMaximumPoolSize-deltaWorkPermits--autonomous/run1/`](maximumPoolSize-setMaximumPoolSize-deltaWorkPermits--autonomous/run1/): `unit/summary.txt` (every `PROBE`/`CTRL`/`RESIZE` line, 129 `EXPECTED`), `cluster/summary.txt` (52 `EXPECTED`, `READING` lines), `phases.json`, `samples-tp.csv`, `samples-mem.csv`, `stress-results.txt`, `resize-lines-RS.txt`, `histo-excerpt.txt`, `selfcheck.py`, `selfcheck.txt`.

### 4.1 Readings

**Unit tier** (`unit/summary.txt`: 129 yes, 0 NO; three reps identical in active/pending/maxPool, heapDelta spread 0.0 MiB)

| Test or assertion | Result | Evidence |
|---|---|---|
| Variant A (T = 2000, 1 MiB allocated by the running task), n = 1 · 4 · 32 · 128 | active = n, pending = 1999 · 1996 · 1968 · 1872, registry = n MiB, heapDelta 2.0 · 4.2 · 32.2 · 128.2 MiB, no submit error, longest `execute` ≤ 14 ms | `unit/rep*.probe` |
| Variant B (T = 600, 1 MiB allocated at submit), same n | active = n, pending = 599 · 596 · 568 · 472, heapDelta **600.1 MiB at every n** | same |
| Pool threads / NMT Thread delta | n + 0..1 pool threads; NMT Thread committed 0.2 · 0.4 · 3.4 · 13.9 MiB at n = 1 · 4 · 32 · 128 | same |
| Control (`ArrayBlockingQueue(64)`, `AbortPolicy`), n = 4 · 32 · 128 | queue 64, accepted 68 · 96 · 192, rejected 532 · 504 · 408, heapDelta 68.0 · 96.0 · 192.1 MiB | same |
| Resize: 4 → 32 | active 4 → 32, pending 596 → 568, 1 listener call, 1 "Resized" line | `RESIZE` lines |
| Resize: 32 → 32 (twice, line 384) | active, pending, listener calls (1) and log lines (1) unchanged | same |
| Resize: 32 → 8 with 32 running | listener 2, log lines 2, **active stays 32**, finished 0; after 4 tasks end: active 28; after 24 end: 8; after 26 end: active 8, started 34 | same |

**Cluster tier** (`cluster/summary.txt`; 50 yes, 2 NO; medians over the read phase R, 10 min; heap after GC = class-histogram live bytes)

| Lifetime | Active max (JMX 1 s) | Pending median R (Read / Mutation) | HEAP R (MiB) | HEAP W | RssAnon R (MiB) | JMX threads R | Mixed op/s |
|---|---|---|---|---|---|---|---|
| n = 4 | 4 | 121 / 0 (max 124) | 418.1 | 600.4 | 2,798.9 | 206 | 58,522 |
| n = 32 | 32 | 5 / 1 (max 101) | 512.2 | 367.8 | 2,861.4 | 262 | 108,381 |
| n = 256 | 128 | 1 / 1 (max 2) | 522.1 | 392.6 | 2,808.5 | 286 | 106,596 |
| n = 32 again | 32 | 4 / 1 (max 102) | 474.0 | 389.0 | 2,818.2 | 260 | 109,112 |
| RS (32 → 8 → 64 → 32) | 64 | — | 467.9 | 540.8 | 2,824.3 | 264 | 107,309 |
| PC0 / PC (write 90 s) | 32 / 32 | — | W 609.0 / 606.5 | — | — | — | 64,010 / 62,105 |
| PC0 / PC `RequestsSize` max | 428.9 / 127.6 KiB | | | | | | |
| M64 / M256 / reference n32 peak `MemtableOnHeapSize` | 20.5 / 80.6 / 170.3 MiB; HEAP W 178.9 / 319.3 / 367.8 | | | | | | |

Other readings: `getconcurrency` read back n in every lifetime; RS: three "Resized" lines per stage (32→8, 8→64, 64→32), none for the same-value call, every `setconcurrency` rc 0 (`resize-lines-RS.txt`); no `Pause Full` other than the harness's own, no OOM in any lifetime; baseline heap 69–84 MiB; stress errors 0–640 write timeouts out of 3 M in the write phases and 0 in every read phase (`stress-results.txt`).

### 4.2 Conclusion and logic

1. **Validity.** Unit: pool and executor read back as n; limit reached and passed (T − n queued) [observed: `unit/rep*.probe`]. Cluster: `getconcurrency` = n for both stages in every fixed lifetime; Active reached n at n = 4 and 32 and Pending at n = 4 was 121 (>= 20), so the limit bound there; at n = 256 Active peaked at 128 (the limit did not bind, as B3f expects) [observed: `summary.txt`, `samples-tp.csv`]. Heap 2 GiB, 400 threads, no full GC, no OOM [observed: `gc-compact-*.log`, `summary.txt`]. Valid, with the shared-host and D1/D2 deviations.
2. **Readings.** (a) HEAP R rises with n: 418 → 512 → 522 MiB [observed]. The n = 4 lifetime also served 54 % of the n = 32 op rate (58.5k vs 108.4k /s), so it allocated and retained less per interval [inferred: op rates; no per-op accounting was made]. (b) HEAP W has one to three samples per lifetime (the write lasts 47 s) and is non-monotone (600 / 368 / 393) [observed]. (c) The n = 32 repeat differs by 8 % [observed], which is the noise level.
3. **Matched row.**
   - **Unit, B2g row 1** ("Variant B heap equal across n; queue unbounded; no rejection"): variant B heapDelta is 600.1 MiB at n = 1 · 4 · 32 · 128 with pending = T − n and no rejection. With the **control row** ("pending plateaus at its bound while SEP pending keeps growing"): the bounded queue plateaus at 64 and rejects, heapDelta = n + 64 MiB. Variant A rises as n MiB, the "expected indirect effect, not a refutation" row.
   - **Cluster: no row matches.** B3g row 1 needs heap and RSS about equal across n (<= 1.15): RSS 1.022 holds, heap 1.249 does not. Row 2 (refuting) needs a linear, monotone trend with max/min >= 1.5: monotone but 1.249, so it does not hold either. Recorded as **Not confirmed (no matching row)**.
4. **Excluded rows.** Unit: no heapDelta growth with n in variant B, no pending cap, `mei`/repeat rows clean (reps identical), the shrink reading as predicted (active 32 after 32 → 8). Cluster: the refuting row (not >= 1.5; the n = 256 heap is 1.02 of n = 32's, the rise is between 4 and 32); "Pending near 0 at n = 4" (121); "control did not change usage" (C7 (i) and (ii) both hold: PC `RequestsSize` 127.6 KiB vs 428.9 KiB; peak memtable 20.5 / 80.6 / 170.3 MiB and HEAP W 178.9 < 319.3 < 367.8); "repeated same-value logs Resized" (no); C6a noise (1.081), C6b (Active <= n), C6c (3 lines per stage), C6d (none).
5. **Observed vs. inferred.** Inferred: the reading of the n = 4 heap difference (2a). The matched/unmatched decision rests on observed medians only.
6. **Deviations and gaps.** E1; the shared host; D1, D2 and H1, H2; the missed "about equal" band for heap (1.249 against 1.15) is recorded as a missed sub-claim; the thread-count prediction ("at most the n difference") holds (206 → 286 JMX threads, 80 more for 252 more permits). The sample count in W is 1–3, so HEAP W is weak. The n = 256 pool never bound under real load, so the effect of a bound pool at large n is unobserved. Only `ReadStage` and `MutationStage` were exercised (S1).
7. **Core question.** The knob counts concurrent tasks: Active never exceeded n (4, 32; 64 in RS after the resize) and the unit tier shows the disallow (pending = T − n; a shrink leaves the running tasks running; the equal-value call at line 384 is a no-op). In the unit tier queued memory is T MiB at every n, while a byte cap holds it at its bound. On the node, heap after GC did not follow n proportionally and RSS was flat, but heap rose 25 % between n = 4 and n = 32, which the frozen bands classify as neither "equal" nor "tracks n".

**Conclusion (one line):** unit — B2g row 1 and the control row, **Confirmed — does not cap**; cluster — **Not confirmed (no matching row)** (heap ratio 1.249 between the 1.15 and 1.5 bands; RSS, Active, Pending, resize lines and both controls as predicted).

## 5. Self-check of run 1 — AI

### 5.1 Check of run 1's conclusion

[`run1/selfcheck.py`](maximumPoolSize-setMaximumPoolSize-deltaWorkPermits--autonomous/run1/selfcheck.py) re-parses the raw files with its own code (it does not read `summary.txt`, `unit-analyze.py` or the EXPECTED lines): the `.probe` files, `samples-*.csv`, the node `system-*.log` and `gc-compact-*.log`, the stress outputs and `phases.json` (windows only). Output [`run1/selfcheck.txt`](maximumPoolSize-setMaximumPoolSize-deltaWorkPermits--autonomous/run1/selfcheck.txt): **144 ok, 2 FAIL**; the two FAILs are exactly the two missed heap bands (R 1.249, W 1.633), with figures equal to the run script's.

| Part | Holds? | Note (file re-read) |
|---|---|---|
| 1. Validity | yes | `getconcurrency` n = 4 / 32 / 256 / 32 in phases; Active max 4 / 32 / 128 / 32 re-read from `samples-tp.csv` and the JMX csv; Pending(4) median 121; compact GC logs show no non-diagnostic full GC; `-Xmx2G` etc. in `summary.txt` |
| 2. Readings | yes | heap medians recomputed from `samples-mem.csv`; op rates from the stress outputs |
| 3. Matched row | yes | unit rows rebuilt from the `.probe` lines (106 ok); the cluster ratios 1.249 / 1.022 recomputed, outside the 1.15 and 1.5 bands |
| 4. Excluded rows | yes | RS Resized lines re-read in `system-5.log` (3 per stage); control values recomputed |
| 5. Observed vs. inferred | yes | the one inference (op-rate explanation) is not used by the decision |
| 6. Deviations and gaps | yes | listed in §2–§4 |
| 7. Core question | yes | follows B1; the cluster tier stays undetermined by the frozen bands |

### 5.2 Run 2?

**No** — decided 2026-10-22. The unit result rests on identical reps; the cluster result is a recorded miss of a frozen band, not a refutation or bypass, and a repeat would not change the band (no conclusions row may be added after a reading). Stage 3 could add a band between 1.15 and 1.5 (see §8).

## 6. Run 2 — fresh AI session (optional)

Not done (§5.2); §7 left out.

## 8. Verdict — AI

**Stage-3 estimate:** negative.

**Claim tested (B1):** changing the SEP maximum pool size changes the number of concurrently running tasks but does not bound memory: queued-task memory is unbounded whatever the value, and heap/off-heap use under a fixed load does not plateau at a level set by the knob. "Confirmed" means this claim held.

| Tier | Verdict (B2g / B3g row) | Effect on the constraint | Basis | Date |
|---|---|---|---|---|
| Unit | Confirmed — B2g row 1 and the control row (variant B heap 600.1 MiB at every n; byte-bounded queue plateaus at 64) | does not cap | run 1 + self-check | 2026-10-22 |
| Cluster | Not confirmed (no matching row): heap after GC 418 / 512 / 522 MiB at n = 4 / 32 / 256 (1.249) | undetermined (RSS flat 1.022; Active <= n; no refuting trend) | run 1 + self-check | 2026-10-22 |

**Positive control:** unit — a bounded queue on the same tasks plateaus at 64 pending and 64 + n MiB. Cluster — `native_transport_max_request_data_in_flight` (and per-IP) at 128 KiB with the receive queue at 0B held `RequestsSize` at 127.6 KiB against 428.9 KiB uncapped; `memtable_heap_space` 64 / 256 MiB held peak memtable heap at 20.5 / 80.6 MiB against 170.3 MiB and post-GC heap at 178.9 / 319.3 / 367.8 MiB.

**Feedback filed:** section D of the case file updated (not committed); no section amended (no row Refuted). For stage 3: B3f's "within about 10-15 %" had no band between 1.15 and 1.5, and the n = 4 lifetime's lower throughput changes retained heap by itself; the B3h in-flight control of "4 MiB" cannot bind at about 0.5 MiB in flight.
