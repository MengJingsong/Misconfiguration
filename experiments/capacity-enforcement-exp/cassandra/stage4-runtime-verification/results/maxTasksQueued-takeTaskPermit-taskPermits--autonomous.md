# maxTasksQueued-takeTaskPermit-taskPermits--autonomous — stage-4 results  <!-- file: results/maxTasksQueued-takeTaskPermit-taskPermits--autonomous.md -->

> **Case:** [`maxTasksQueued-takeTaskPermit-taskPermits--autonomous`](../../stage3-ai-deep-read/cases/maxTasksQueued-takeTaskPermit-taskPermits--autonomous.md)
>
> **Status:** **Closed 2026-10-22. Unit: Confirmed — does not cap. Cluster: Not confirmed (row C4, positive control did not move) — undetermined.** Unit: an `SEPExecutor` took 10^4, 10^5, 10^6 (and 4 x 10^6) queued tasks with its only work permit held, pending == N exactly, `getMaxTasksQueued()` = 2147483647, no rejection, and the retained heap grew linearly (80 B per task at P = 0, 1104 B at P = 1024, 1053 MiB at N = 10^6); the bounded-queue control stopped at 10,000 and held 10.3 MiB. Cluster: MutationStage Pending followed the offered load (1996 at 2000 threads, 252 at 256) and the heap followed it, with Active <= 2 and `MaxTasksQueued` constant; but the 16 MiB in-flight limit of run B, which reached its limit (RequestsSize 15.97 MiB), left Pending (1996) and heap exactly where run A had them, so the file's positive control did not move. No run 2.
> 
> **Outcome class:** undetermined — stage-3 estimate vs the stage-4 effect on the constraint
>
> **Agent:** autonomous (the suffix of the case-file stem). For an autonomous
> file, "§9a" below means each tier's predictions and conclusions table: B2f and B2g
> (unit), B3f and B3g (cluster); "§9b–§9e" means B2a–B2e or B3a–B3e; and the case
> file's feedback section is its section D, not §10. One results file per case file.

## 1. Before run 1 — design audit and freeze

| Field | Content |
|---|---|
| **Case-file version** | Autonomous file, untracked (repo HEAD `00922e0`). As filed: sha256 `58849d2c713b9a5efcb73ab2d1b61416e54eb552bed2503c7d02ef47acafc23b`. After the step-0 amendments R1–R10 and the instrument-check fixes D1–D2 (one dated block "Stage-4 amendments", 2026-10-22, before any run-1 reading): **`eb691cfc516a320bb25fd89e478fa2f11242dc0216e911f08ac5767b8dd654f8`, the frozen version and the version both tiers of run 1 used** (checked unchanged with `sha256sum` after the cluster run, before section D was filled). B1 and the claim are unchanged. |
| **Harness** | [`harness/maxTasksQueued-takeTaskPermit-taskPermits--autonomous/`](../harness/maxTasksQueued-takeTaskPermit-taskPermits--autonomous/README.md), written 2026-10-22, not committed: `SEPQueueBoundProbe.java`, `unit-run.sh`, `unit-analyze.py`, `make-node-yaml.sh`, `Jmx.java`, `cluster-run.py`, `selfcheck.py`. **Instrument checks (not readings of either tier):** `javac` against the clone; unit shakedown (N <= 20,000, `~/stage4-logs/mtt/shakedown1/unit`); cluster shakedown (arm A, 100 s; found D1 and D2). md5 of the node copy in `~/stage4-harness-run/mtt.md5`. |
| **Tiers and values** | Unit (B2): `SEPExecutor` with `maxConcurrency` 1, P = 0 and 1024 bytes per task, N = 10^4 · 10^5 · 10^6 (4 x 10^6 for P = 0), two repetitions, each with the `ArrayBlockingQueue(10000)` control. Cluster (B3): one node, `concurrent_writes` 2, heap 1 GiB, 32 KiB writes; run A (in-flight limits 512 MiB, 2000 threads), run B (16 MiB, 2000 threads, the positive control), run A2 (added: 512 MiB, 256 threads). Optional run C not run. |
| **Audit bottom line** | **Ready after amendments** — 2026-10-22 |

### 1.1 Design audit

| Group | Check | Rating (Met / Partly / Not met) | Note (section checked) |
|---|---|---|---|
| A. Core question | constrained quantity is memory or disk bytes | Met | B1/A2: heap held by tasks queued in an `SEPExecutor`; the "limit" is a count (`getMaxTasksQueued`, a constant), and the file claims it bounds nothing. Bytes per task are derived from the heap (B2d, B3d). |
| A. Core question | knob varied, ≥ 3 values incl. default — or another approach, with the reason | Met | The constant cannot be varied (A1); B2b varies N over 10^4–10^6 and P over 0/1024, and B3b varies the offered load (R8 adds the second load level A2) and the in-flight limit. The approach (usage vs offered load, against two byte caps) is stated in B1/B3b. |
| A. Core question | real resource measured, not only the counter (gap named) | Met | B2d heap after 3 x GC and the class histogram; B3d post-GC heap and histogram. The queue's own bytes are inferred (heap minus baseline minus memtable); B3d names that gap. |
| A. Core question | usage driven to the limit and past it | Partly → amended (R5, R6, D2) | Unit: N goes to 10^6 against a limit nobody can reach (2^31) — a limit never reached is the point of the claim, and the control shows the harness reaches a limit that exists. Cluster: at the default 128 native-transport threads MutationStage Pending cannot exceed about 128 (R5); the 1 MiB per-connection receive queue absorbs the first bytes before the reserve is used (R6); stress limits itself to 1,024 requests in flight (D2). |
| A. Core question | positive control (negative estimate) | Met | Unit: `ArrayBlockingQueue(10000)` with the same blocker and payload. Cluster: the in-flight limit 16 MiB (B3b run B). |
| B. Logic | each step says what it establishes | Met | B2e/B2g/B2h, B3e/B3g/B3h. |
| B. Logic | prediction stated in numbers or a clear relation | Partly → amended (R3, R9) | "about", "≈", "rises with offered load" ("offered load" had a single value), "flat" and the heap statistic were undefined. R3/R9 define them and add A2. |
| B. Logic | every plausible outcome has a conclusions row with its evidence | Partly → amended (R4, R10) | Missing rows: slope/repeat sub-predictions missed, OOM before the largest point, an unmatched pattern (unit); heap not following Pending, OOM, any other pattern (cluster). |
| B. Logic | confirmation needs ceiling-follows-knob and direct disallow evidence | Met | Unit: `getMaxTasksQueued()` read per point, the control's rejection count. Cluster: `RequestsSize` at the in-flight limit shows the byte cap reached, MaxTasksQueued read every second, Active <= 2 shows the stage is saturated. |
| B. Logic | alternative explanations and their controls | Partly | Memtable (B3h: subtracted), GC (heap after `jcmd GC.run`), carry-over (fresh node lifetime per arm). Per-running-task and per-request memory (thread-local buffers, decoded request copies) is not separated from the queue's: the heap statistic is total heap minus baseline minus memtable. Left for stage 3. |
| C. Specific | a human can follow it from the intro and §9a | Met | Header, A3, B1. |
| C. Specific | an AI can run §9b–§9e without re-deriving the code path | Partly → amended (R1, R5–R8, D1, D2) | B2a said `ant`/junit and `-Xmx2g` (testsome overrides it); B3 gave no stress command with a working population, thread limit or yaml. |
| C. Specific | knob, values, workload, commands, observables, sampling, stop conditions exact | Partly → amended | As above; stress `no-warmup` (R7). |
| D. Runnable | harness and environment prerequisites exist or are listed | Met | Fresh clone `~/cassandra-mtt` on `pc13`, `ant build-test` 1 min 7 s. Paths named in B2a/B3a (`/local/scratch`) are replaced by `~/stage4-mtt`, `~/stage4-logs/mtt`. |
| D. Runnable | workload arithmetic reaches the limit (data, time, disk, memory) | Partly → amended (R7) | B4's 64 GB would not fit the 53 GB disk; the population of 4,000 partitions (131 MB) is overwritten; node data stayed below 5 GB. Unit heap 2 GiB holds 1.1 GB (P = 1024, N = 10^6). |
| D. Runnable | load-bearing citations spot-checked against the pinned clone | Met | `SEPExecutor.java:68, 102-106, 119-145, 156-185` (the emptiness test is at `:175`, the task add at `:123`, the permit increment at `:131`, the only `getMaxTasksQueued` at `:103`), `ThreadPoolMetrics.java:70, 93, 105`, `SharedExecutorPool.java:141-152` (the file says `:146`), `Config.java:283, 302`, `DatabaseDescriptor.java:645-660, 905-918`, `Dispatcher.java:58`, `StorageProxy.java:906`, `build.xml:1153`, `StressAction.java:105-110`, `SettingsMode.java:138-139`. All as cited except the `SharedExecutorPool` line (minor). |

| # | Recommendation | Applied? | Why |
|---|---|---|---|
| R1 | Unit probe as a plain `java -Xms2g -Xmx2g` program | Applied 2026-10-22 (amendment block) | `build.xml:1153` `maxmemory="1024m"` overrides B2a's `-Xmx2g`; 10^6 x 1 KiB does not fit 1 GiB |
| R2 | B2e series made exact: cumulative N, P = 0 to 4 x 10^6, control on the same series, two repetitions | Applied | B2e was ambiguous between cumulative and fresh executors; B2b lists 4 x 10^6 |
| R3 | Define "≈", slope bands, "no blocking", "plateau", repeat tolerance | Applied | undefined terms |
| R4 | Rows U7 (sub-prediction missed), U8 (OOM before 10^6), U9 (any other pattern) | Applied | outcomes without a row |
| R5 | `native_transport_max_threads: 4096` in every run | Applied | with 128 threads MutationStage Pending is bounded by about 128 (`StorageProxy.java:906`, `Config.java:283`) |
| R6 | `native_transport_receive_queue_capacity: 0B`; write and native-transport timeouts raised | Applied | the 1 MiB per-connection queue absorbs bytes before the reserve; expired mutations are dropped (`Dispatcher.java:238-245`) |
| R7 | Stress command with `no-warmup`, a 4,000-partition population, `duration=360s`; `commitlog_sync: batch` | Applied | disk arithmetic (B4), warm-up of 50,000 unthrottled writes, B3c's own suggestion |
| R8 | Add arm A2 (256 threads); skip optional run C | Applied | "rises with offered load" needs two load levels |
| R9 | Define Pn, Pmax, Hn, the window, plateau-flat and the sub-predictions | Applied | undefined statistics |
| R10 | Replace B3g by rows C1–C7 (first match) | Applied | outcomes without a row |
| S1 | Per-request memory is not separated from queued memory (the `concurrent_compactors` pattern, usage = tasks x per-task bytes); the claim covers all seven SEP executors but only `MutationStage` and synthetic executors run | Left for stage 3 | outside this design |

**Agreement criteria** — not filled (no run 2).

## 2. Environment

| Field | Run 1 | Run 2 (fresh AI session, if done) |
|---|---|---|
| Date | 2026-10-22, MDT. Unit run 07:59:54–08:01:24; cluster run 08:01:50–08:26:42 (arms A, B, A2 in order). Instrument checks 07:48–07:58. | not done |
| Node (CloudLab name and type) | `pc13` = `node3.jason92-320876.misconfiguration-pg0.cloudlab.umass.edu` (40 cores, 251 GiB). No other agent used it. Node on 127.0.0.1, JMX 7199 (B3a). | — |
| OS and kernel (`uname -r`) | Ubuntu 22.04.2 LTS, `5.15.0-187-generic` | — |
| JDK (`java -version`) | openjdk 11.0.32.1 (2026-08-18) | — |
| Ant (`ant -version`) | 1.10.12 | — |
| Local `cassandra-src` clone commit | `~/cassandra-mtt` at `cassandra-5.0.9` (`b5f2a54210d541339c2e7c17a794195cac0e67c2`), cloned from the shared clone; `ant build-test` BUILD SUCCESSFUL in 1 min 7 s (`~/stage4-logs/mtt/build.log`). The clone itself was not changed (the probe is compiled into the log directory). | — |
| Case-file commit / harness commit | case file untracked, sha256 `eb691cfc…`; harness not committed (md5 in `~/stage4-harness-run/mtt.md5`) | — |
| Storage for node data | `~/stage4-mtt/node1/` on local `/dev/sda3` (rotational, 63 GB, 56 GB free at the start; data up to 4.6 GB and commit log up to 1.8 GB during a run); directories wiped before each arm | — |
| Full logs (path, outside the repo) | `pc13:~/stage4-logs/mtt/`: `run1/unit/` (per-JVM logs, `summary.txt`), `run1/cluster/` (`summary.txt`, `session.log`, `samples-*`, `histo-*`, `stress-*`, `system-/debug-/gc-<arm>.log`, `phases.json`), `run1/selfcheck.txt`, `shakedown1/`, `build.log` (720 MB in all) | — |

## 3. Runbook defects

| # | Run | Step (§9b–§9e) | Problem | Fix | Decision (date) | Case-file commit with the fix |
|---|---|---|---|---|---|---|
| D1 | cluster shakedown (instrument check) | B3c | The node would not start: "Invalid yaml. Please remove properties [commitlog_sync_batch_window_in_ms]". 5.0.9 has no such key (`batch` syncs on every write; the node log shows `commitlog_sync_group_window=0ms`). | `commitlog_sync: batch` alone, `commitlog_sync_period` removed. B3f/B3g unchanged. | 2026-10-22, dated block D1 | none (file untracked) |
| D2 | cluster shakedown (instrument check) | B3c | `cassandra-stress` keeps at most 128 pending requests on each of 8 connections (`SettingsMode.java:138-139`), so 2000 threads kept 1,022 requests in flight and the rest failed with `BusyPoolException` (1.2 M errors in 100 s). | `connectionsPerHost=16` (2,048). B3f/B3g unchanged. | 2026-10-22, dated block D2 | none |
| D3 | unit | B2 analysis | The first `unit-analyze.py` demanded a "first reject" record at N = 10,000, where the control has not yet rejected anything (`firstReject=none`, `rejected=0`). It reported 4 NO that restate the amended definition correctly met at every later N. | The check accepts `none` at N = 10,000. The tier was not re-run; the same logs were re-analysed (`unit/analysis-reanalyze.txt`). | harness only, 2026-10-22 | — |
| D4 | self-check | analysis | `grep OutOfMemoryError` matches the JVM flag `-XX:+HeapDumpOnOutOfMemoryError` in the node log's configuration dump (the HANDOFF lesson, repeated). | `grep 'OutOfMemoryError: '`; 0 hits in all three node logs. | harness only | — |

## 4. Run 1

**Scope:** unit B2 (P = 0 and 1024, sep and control, two repetitions each); cluster B3 (runs A, B, A2, one 360-s stress each). **Command log and excerpts:** [`maxTasksQueued-takeTaskPermit-taskPermits--autonomous/run1/`](maxTasksQueued-takeTaskPermit-taskPermits--autonomous/run1/): `unit/summary.txt` (every `PROBE` line and the `EXPECTED` lines), `unit/analysis-reanalyze.txt`, `unit/*.log`, `cluster/summary.txt`, `phases.json`, `samples-tp.csv`, `samples-heap.csv`, `samples-jmx-{1,2,3}.csv`, `stress-results.txt`, `config-excerpt.txt`, `histo-excerpt-*.txt`, `selfcheck.py`, `selfcheck.txt`.

### 4.1 Readings

**Unit tier** (`unit/summary.txt`: 8 JVMs, exit 0, no OutOfMemoryError; `unit-analyze`: 104 yes, 2 NO — both the 4 x 10^6 timing criterion)

| Test or assertion | Result | Evidence (file) |
|---|---|---|
| Executor, P = 0, N = 10^4 · 10^5 · 10^6 · 4 x 10^6, both reps | active = 1 (the blocker); pending = N exactly; `maxQueued` 2147483647; no exception; heap delta 0.79 · 7.66 · 76.32 · 305.20 MiB = 82.9 · 80.3 · 80.0 · 80.0 B per task (identical in rep1 and rep2) | `unit/sep-P0-rep*.log` |
| Executor, P = 1024, N = 10^4 · 10^5 · 10^6, both reps | pending = N; `maxQueued` 2147483647; heap delta 10.56 · 105.31 · 1052.89 MiB = 1106.9 · 1104.3 · 1104.0 B per task; P = 1024 minus P = 0 at 10^6: 1024.0 B | `unit/sep-P1024-rep*.log` |
| Timing | mean wall time per `execute` call 0.2–2 µs; slowest single call 819 µs (10^4), 22–41 µs (10^5), 13–24 µs (10^6, P = 0), 140 ms (10^6, P = 1024), **1.70–1.76 s at 4 x 10^6 (P = 0)** | same (`maxCallUs`) |
| Class histogram at the last point | `ConcurrentLinkedQueue$Node` count = N + 1 at the last point; drain: pending 0, completed = N + 1 | same |
| Control `ThreadPoolExecutor(1,1,0,ms,ArrayBlockingQueue(10000),AbortPolicy)`, P = 0 and 1024, both reps | accepted 10,000 at every N, rejected = N − 10,000, first rejection after 10,000 accepted, queued 10,000; heap delta 10.14 → 10.26 MiB (P = 1024), 0.37 → 0.49 MiB (P = 0); the executor at N = 10^6, P = 1024 holds 1052.9 MiB (ratio 103) | `unit/control-P*-rep*.log` |
| Repeats | the two repetitions agree to 0.0 MiB at every point | `unit/analysis-reanalyze.txt` |

**Cluster tier** (`cluster/summary.txt`, `samples-*.csv`; window t = 60 s … end of stress; `cluster-run` 23 yes / 3 NO, selfcheck 46 ok / 3 FAIL)

| Capacity value | Run | Observable (§9d) | Reading | Evidence (file) |
|---|---|---|---|---|
| in-flight 512 MiB, 2000 threads | A | MutationStage Pending (tpstats, 5 s) | median 1996, max 1998 (first-half median 1996, second half 1997); Active max 2; `NTR` Pending median 0 | `samples-tp.csv`, `phases.json` |
| in-flight 512 MiB, 2000 threads | A | `RequestsSize` (JMX, 1 s) | max 62.64 MiB (mean 62.06); MaxTasksQueued = 2147483647 at all 437 samples | `samples-jmx-1.csv` |
| in-flight 512 MiB, 2000 threads | A | heap after GC, minus memtable data size, minus baseline (76.7 MiB) | Hn = 413.3 MiB (raw median 509.1 MiB); 212 KiB per queued mutation | `samples-heap.csv` |
| in-flight 512 MiB, 2000 threads | A | class histogram at +181 s | `db.Mutation` 2000; `[B` 218.5 MB (baseline 19.9 MB); `ConcurrentLinkedQueue$Node` 6,448 | `histo-excerpt-A.txt` |
| in-flight 512 MiB, 2000 threads | A | stress | 2,435 op/s, mean latency 818 ms, 0 errors, 878,686 partitions | `stress-results.txt` |
| in-flight **16 MiB**, 2000 threads | B | Pending | median **1996**, max 1998 (min of the tpstats window 460 at the stop); Active max 2 | `samples-tp.csv` |
| in-flight 16 MiB, 2000 threads | B | `RequestsSize` | max **15.97 MiB** (mean 15.69): the byte cap was reached and held | `samples-jmx-2.csv` |
| in-flight 16 MiB, 2000 threads | B | Hn | 417.5 MiB (raw median 521.8 MiB); 214 KiB per queued mutation; Hn(A) − Hn(B) = −4.2 MiB | `samples-heap.csv` |
| in-flight 16 MiB, 2000 threads | B | histogram at +181 s; stress | `db.Mutation` 1998; `[B` 206.8 MB; 2,391 op/s, 0 errors | `histo-excerpt-B.txt`, `stress-results.txt` |
| in-flight 512 MiB, 256 threads | A2 | Pending; `RequestsSize` | median **252**, max 254; Active max 2; RequestsSize max 8.02 MiB | `samples-tp.csv`, `samples-jmx-3.csv` |
| in-flight 512 MiB, 256 threads | A2 | Hn; histogram; stress | Hn = 146.2 MiB (raw median 241.8 MiB); `db.Mutation` 254; `[B` 102.7 MB; 2,750 op/s, mean latency 92.5 ms, 0 errors | `samples-heap.csv`, `histo-excerpt-A2.txt`, `stress-results.txt` |
| all three | A, B, A2 | node configuration (node log) | `concurrent_writes=2`, `commitlog_sync=batch`, `native_transport_max_threads=4096`, `native_transport_receive_queue_capacity=0B`, `native_transport_timeout=120s`, `write_request_timeout=120000ms`, in-flight 512 / 16 / 512 MiB (global and per-IP), `native_transport_throw_on_overload=false`, `memtable_allocation_type=heap_buffers`, JVM MaxHeapSize 1024 MiB with G1 | `config-excerpt.txt`, `summary.txt` |

### 4.2 Conclusion and logic

1. **Validity.**
   - **Unit.** Valid. `maxConcurrency` = 1 was read back by active = 1 with the blocker holding the permit; every N was reached; all JVMs ran with a 2048 MiB heap; the control rejected at exactly its capacity (so a bound that exists is visible to the instrument) [observed: `unit/summary.txt`, `unit/*.log`].
   - **Cluster.** Valid for runs A and A2. The stage was saturated by two workers (Active <= 2, Pending thousands) and the load was held for 300 s with 0 stress errors in all arms [observed: `samples-tp.csv`, `stress-results.txt`]. Every "hold fixed" setting was read back from the node's own log (`config-excerpt.txt`). **Run B reached its byte cap** (RequestsSize 15.97 MiB of 16) [observed: `samples-jmx-2.csv`], so it is a valid run of the control — the control simply did not clip the queue.
2. **Readings.**
   - (a) **Unit timing at the supplementary point.** One `execute` call took 1.70 s (rep1) and 1.76 s (rep2) at N = 4 x 10^6, P = 0, against a mean of 1.2 µs per call over the same batch; no other call above 140 ms in either series [observed: `unit/sep-P0-rep*.log`]. The 2 GiB heap held 305 MiB of queue there, and no GC log was kept; a single GC pause is the likely cause but is not shown [inferred].
   - (b) **Heap per queued mutation** is 212–214 KiB in A and B, 594 KiB in A2, far above the 32 KiB payload [observed: `samples-heap.csv`]. The heap difference between A and A2 is 267.1 MiB for 1,744 more queued mutations = 157 KiB each [observed, computed from the same file]. The cause (decoded `Mutation`, its `CachedSerialization`, request buffers, and state per blocked native-transport thread) is not separated by this design [inferred; histogram counts: 2000 `Mutation` for 1996 Pending].
   - (c) **B equals A.** Pending, heap, `Mutation` count and throughput are the same in A and B (1996 vs 1996; 413.3 vs 417.5 MiB; 2000 vs 1998; 2,435 vs 2,391 op/s), although RequestsSize differs 4-fold (62.6 vs 15.97 MiB) [observed]. So in this workload the bytes the in-flight limit counts are not the bytes that wait in the executor queue: at B the 16 MiB covers 512 requests of 32 KiB but 1996 mutations were queued. Why is not shown by this run [inferred: the counted bytes are released before the mutation leaves the queue; not tested].
3. **Matched rows.**
   - **Unit — B2g row 1:** "Pending == N for all N, no rejection, heap slope about per-task size — Claim confirmed: queue unbounded, usage follows the workload, not any cap", together with the control row "Heap grows in the executor run but the control (bounded queue) is flat after its capacity — Claim confirmed". Pending == N at 10^4 · 10^5 · 10^6 (and 4 x 10^6), no exception, no call above 140 ms up to 10^6; slope 80.0 B (P = 0) and 1104.0 B (P = 1024) inside [P + 32, P + 250]; P = 1024 minus P = 0 = 1024.0 B; the control accepted exactly 10,000 and plateaued at 10.26 MiB against 1052.9 MiB.
   - **Cluster — row C4:** "Not confirmed (control did not move): Pn(B) > 0.5 x Pn(A), or RequestsSize max of B < 14.4 MiB". Pn(B) = 1996 > 0.5 x 1996 = 998. Rows above it do not hold: C1 needs Pn(B) <= 0.5 x Pn(A) and Hn(A) − Hn(B) >= 0.5 x (Pn(A) − Pn(B)) x 32 KiB = 0 (read −4.2 MiB). The other conditions of C1 hold: MaxTasksQueued constant, Active <= 2, Pn(A2) = 252 >= 10, Pn(A) = 1996 >= 2 x 252, Hn(A) − Hn(A2) = 267.1 MiB >= 27.2 MiB, RequestsSize max of B 15.97 >= 14.4.
4. **Excluded rows.**
   - **Unit:** "execute throws/blocks/drops at some N below 10^6" (Refuted): no exception, slowest call below 10^6 = 140 ms, pending == N. "Heap flat while N grows": delta at 10^6 is 1052.9 MiB (P = 1024) and 76.3 MiB (P = 0), against thresholds of 0.5 x N x (P + 32) = 504 and 15 MiB. "Control does not stop at its capacity" (Invalid): it stopped at exactly 10,000. "Pending != N": equal at every point. U7 (slope/difference/repeat missed): none missed. U8 (OOM before 10^6): none.
   - **Cluster:** C2 (Refuted): MaxTasksQueued 2147483647 at all samples; Pn(A)/Pn(A2) = 7.92, far from 1 (Pending follows the offered load, no executor-level clip). C3: Pn(A) and Pn(A2) are 1996 and 252, far above 10. C5, C6, C7: not reached (C4 matches first; no OutOfMemoryError in the three node logs, heap max 953 MiB of 1024). C1 does not hold because of the B conditions above.
5. **Observed vs. inferred.** The inferred statements are 2(a) (a GC pause), 2(b) (what makes up 157–214 KiB per queued mutation), 2(c) (why the in-flight limit does not clip the queue). The matched rows use none of them: the unit row uses the printed probe lines; C4 uses the 5-s tpstats Pending series and the 1-s JMX `RequestsSize`.
6. **Deviations and gaps.**
   - **Sub-predictions missed (recorded, no row change):**
     - Unit B2f "per-call time flat, microseconds": met for N <= 10^6; missed at the supplementary 4 x 10^6 point (one call, 1.70–1.76 s) — no row of B2g or R4 names this (R4 U7 covers slope, difference and repeat only), so this single sub-observation is recorded **Not confirmed (no matching row)** and does not change the tier's matched row.
     - Cluster R9: `Pmax(B) <= 563` (read 1998) and the heap-per-mutation figure (sub-prediction only a lower bound >= 32 KiB, met at 212 KiB; the first draft of an upper bound at 160 KiB was dropped before run 1 after the shakedown showed 208 KiB — the shakedown is an instrument check and its reading is recorded here for transparency).
   - **The positive control for the cluster did not move.** The file's control, an in-flight limit of 16 MiB, bound at RequestsSize but did not reduce queued mutations or heap. A run with a control that does move the queue (for example `native_transport_max_threads` at 128, which bounds Pending by about 128; this was held at 4096 by R5 and is the one value the instrument check showed would do so) was not part of the design and was not run (run 1 only).
   - **Not separated:** per-request memory from queued-task memory (S1); `Native-Transport-Requests` Pending stayed 0 (4096 threads).
   - **Environment:** disk was never an issue (data <= 4.6 GB); the unit probe ran outside `ant testsome` (R1).
7. **Core question.**
   - **Unit.** The queue accepted a million tasks (four million at P = 0) against `getMaxTasksQueued()` = 2^31−1 with no refusal, the heap it held rose with N at the per-task cost, and the same loop against a bounded queue stopped at 10,000 and held 10.3 MiB [parts 3, 4]. So the constant caps nothing at the unit level.
   - **Cluster.** On a node whose two workers were the bottleneck, MutationStage Pending equalled the offered concurrency (1996 at 2000 threads, 252 at 256), and the heap followed it by 157 KiB per extra queued mutation, with `MaxTasksQueued` constant [parts 1–3]. That is what an unbounded queue gives. The design's own positive control, the 16 MiB in-flight limit, did not clip Pending or heap (part 2c), so the cluster cannot say what limits queued memory on this path; the file's claim that the in-flight limit does is not borne out by this workload. The matched row is C4.

**Conclusion (one line):** unit B2g row 1 — **Confirmed** (the bound is not enforced; the bounded control caps); cluster B3g row C4 — **Not confirmed** (control did not move).

## 5. Self-check of run 1 — AI

### 5.1 Check of run 1's conclusion

[`run1/selfcheck.py`](maxTasksQueued-takeTaskPermit-taskPermits--autonomous/run1/selfcheck.py) does not read `summary.txt`, `unit-analyze` output or the `EXPECTED` lines. It re-parses the unit probe logs, and for the cluster the 1-s JMX samples (Pending, RequestsSize, MaxTasksQueued, Active), the heap samples (with memtable size), the class histograms, the stress outputs and each node log's logged configuration; `phases.json` gives the time windows. Output [`run1/selfcheck.txt`](maxTasksQueued-takeTaskPermit-taskPermits--autonomous/run1/selfcheck.txt): **46 ok, 3 FAIL**. The three FAIL are exactly the readings that put the cluster on row C4 and the missed sub-prediction `Pmax(B)` (Pn(B) = 1996 <= 0.5 x Pn(A); Hn(A) − Hn(B) = −4.2 MiB; Pmax(B) = 1998 <= 563), and its figures for Pending, RequestsSize and heap agree with the run script's.

| Part | Holds? (yes / no) | Note (file re-read) |
|---|---|---|
| 1. Validity | yes | probe logs: `maxHeapMiB=2048`, active = 1, no OOM; node logs: the nine settings, `MaxHeapSize` 1024 MiB; JMX: MaxTasksQueued 2147483647 at 437/437 samples per arm; Active max 2 |
| 2. Readings | yes | the 1.70/1.76 s calls are in the rep1/rep2 logs; heap-per-mutation and the A − A2 difference recomputed from the heap samples (Hn A 413.28, B 417.50, A2 146.18); pending dips to 0 in the window are the last 2–3 s of each stress (teardown), checked at t = 366–369 s |
| 3. Matched row | yes | slopes and the control rebuilt from the probe logs; Pn, RequestsSize, Hn recomputed from the 1-s JMX and heap series (Pn 1996 / 1996 / 252, RequestsSize max 62.6 / 15.97 / 8.02 MiB) |
| 4. Excluded rows | yes | histogram `Mutation` counts 2000 / 1998 / 254 against Pending; no `OutOfMemoryError: ` in any node log; Pn(A)/Pn(A2) = 7.92 |
| 5. Observed vs. inferred | yes | the three inferred statements are not used by the matched rows |
| 6. Deviations and gaps | yes | D1–D4, the 4 x 10^6 timing miss, the non-moving control, S1 |
| 7. Core question — the steps from reading to answer follow the audited logic | yes | unit: B2g rows 1 and the control; cluster: R10's first-match order reaches C4 because Pn(B) is not below 0.5 x Pn(A) |

### 5.2 Run 2?

**No** — decided 2026-10-22. Run 1 only was asked for. The unit conclusion rests on printed probe lines (identical in two repetitions); the cluster conclusion is a Not confirmed on an observed Pending series, not an inferred one. Run 2 would be worth its cost only with a different control (see 6, "the positive control did not move"), which is a new design, not a repeat.

## 6. Run 2 — fresh AI session (optional)

Not done (§5.2); §7 left out.

## 8. Verdict — AI

**Stage-3 estimate:** negative (usage does not follow the constraint).

**Claim tested:** B1 — "A `SEPExecutor` does not bound its queue: with all workers blocked, it accepts tasks far beyond any count cap (the counter reaches arbitrary N, no rejection or blocking), and the heap held by the queue grows linearly with N. On a real node, the pending-task count of a request stage (e.g. MutationStage) is not limited by `getMaxTasksQueued`; what limits queued memory there is the upstream in-flight byte limit, not the executor." "Confirmed" means this held.

| Tier | Verdict (B2g / B3g row) | Effect on the constraint | Basis | Date |
|---|---|---|---|---|
| Unit | **Confirmed** — B2g row 1 (with the control row) | does not cap | run 1 + self-check | 2026-10-22 |
| Cluster | **Not confirmed** — row C4 (positive control did not move) | undetermined | run 1 + self-check | 2026-10-22 |

**Positive control:** unit — the `ArrayBlockingQueue(10000)` on the same blocker and payload accepted exactly 10,000 and held 10.26 MiB at P = 1024 while the executor held 1052.9 MiB (ratio 103); the harness can see a cap that exists. Cluster — the in-flight limit of 16 MiB reached its limit (RequestsSize 15.97 MiB) but did not move Pending (1996 vs 1996) or heap (417.5 vs 413.3 MiB), so no tier-level Confirmed is possible; the load-dependence evidence (A vs A2, 1996 vs 252 Pending, +267 MiB heap) is consistent with the claim but is not a control.

**Feedback filed:** the case file's section D "Stage-4 feedback" updated (not committed; the file is untracked); amendments inside the file are the dated block "Stage-4 amendments" (2026-10-22). The B1 sentence "what limits queued memory there is the upstream in-flight byte limit" was not supported on this workload (run B).
