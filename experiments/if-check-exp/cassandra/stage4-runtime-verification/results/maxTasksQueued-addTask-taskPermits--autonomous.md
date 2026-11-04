# maxTasksQueued-addTask-taskPermits--autonomous — stage-4 results  <!-- file: results/maxTasksQueued-addTask-taskPermits--autonomous.md; the stem ends in --guided or --autonomous -->
> **Case:** [`maxTasksQueued-addTask-taskPermits--autonomous`](../../stage3-ai-deep-read/cases/maxTasksQueued-addTask-taskPermits--autonomous.md)
>
> **Status:** **Closed 2026-10-22. Unit: Confirmed — does not cap (one sub-criterion missed). Cluster: Not confirmed (no matching row) — undetermined.** Unit: `getMaxTasksQueued()` is 2147483647 in all 16 configurations; `execute` never rejected or blocked on the executor; pending equals the submitted count exactly up to 4,000,000 tasks and, at 1 KiB, until the JVM ran out of heap at 1.91 M tasks; queued heap is 88 B + P per task for c = 1 and c = 8 alike; the byte-bounded control stopped at 1000. Cluster: the gauge stayed 2147483647 and the executor refused nothing, but peak `PendingTasks` did **not** follow the in-flight cap (383 at 256 MiB and 383 at 32 MiB with one worker; 1289 and 376 with eight) while `RequestsSize` followed it exactly (255.98 / 31.97 MiB); the frozen statistics fit none of the filed or added rows. No run 2.
> 
> **Outcome class:** undetermined — stage-3 estimate vs the stage-4 effect on the constraint
>
> **Agent:** autonomous. "§9a" below means B2f/B2g (unit) and B3f/B3g (cluster), "§9b–§9e" means B2a–B2e or B3a–B3e, and the case file's feedback section is its section D.

## 1. Before run 1 — design audit and freeze

| Field | Content |
|---|---|
| **Case-file version** | Autonomous file, untracked (repo HEAD `00922e0`). As filed: sha256 `5b59741e499db23c12aabfeaefb8a4d268739bed8dd624031430b91a2eca28b3` (copy `pc07:~/stage4-logs/mta/case-as-filed.md`). After the step-0 audit amendments E1–E3, U1–U4, C1–C7 (2026-10-22): **frozen version `e8ac528c66a7be57c361ff5c6fa7016bbe1e2e0808aa83a6601d3fc09c824112`**. Runbook fix D1 (cluster instrument check, before any cluster reading; touches only B3b/B3e) gives `5b27ef305e261689c5fdcefb8588e0cddf7fb956d402087e4cd6564c8673bc84`, the version the cluster tier ran. The unit tier ran on the frozen version. B1, B2f, B3f and every filed row unchanged. |
| **Harness** | [`harness/maxTasksQueued-addTask-taskPermits--autonomous/`](../harness/maxTasksQueued-addTask-taskPermits--autonomous/README.md), written 2026-10-22, not committed: `SepQueueProbe.java`, `unit-run.sh`, `unit-analyze.py`, `make-node-yaml.sh`, `Jmx.java`, `cluster-run.py`, `selfcheck.py`. **Instrument checks (not readings):** `javac` of the probe; unit quick pass (N ≤ 1e5); cluster shakedown 1 (found D1) and shakedown 2 (arm A, 60 s: confirmed that 6000 stress threads reach the 256 MiB cap, `RequestsSize` 255.98 MiB). md5 of the node copy in `~/stage4-harness-run/mta.md5`, equal to the repo files. |
| **Tiers and values** | Unit (B2): sep c = 1 · 8 × P = 64 · 1024 × N = 1e4 · 1e5 · 1e6 · 4e6 (16 JVMs, 2 GiB heap), control `ThreadPoolExecutor(ArrayBlockingQueue(1000))` c = 1 · 8, P = 1024, N = 1e6. Cluster (B3): arms A = 256 MiB / `concurrent_writes` 1, B = 32 MiB / 1, C = 256 MiB / 8, D = 32 MiB / 8; 6000 stress threads of 64 KiB, 150 s, window t = 30 s to end. |
| **Audit bottom line** | **Ready after amendments** — 2026-10-22 |

### 1.1 Design audit

| Group | Check | Rating | Note (section checked) |
|---|---|---|---|
| A. Core question | constrained quantity is memory or disk bytes | Met | A2/B1: heap held by queued tasks; the "limit" is a constant count (A1). |
| A. Core question | knob varied, ≥ 3 values incl. default — or another approach, with the reason | Met | The constant cannot be set (A1); the design varies N (the load past any bound), P, c, and for the cluster the upstream in-flight cap and the pool size (B2b, B3b). |
| A. Core question | real resource measured, not only the counter (gap named) | Met | B2d live heap after GC and a class histogram; B3d post-GC heap with `jcmd`; the queue's own bytes inferred (heap − memtable), gap named in B3d and C5. |
| A. Core question | usage driven to the limit and past it | Partly | The limit is `Integer.MAX_VALUE` (2^31 tasks), unreachable before heap exhaustion; B2c's 4e6 × 1 KiB drives to the heap instead. Recorded as the design's limit. |
| A. Core question | positive control (negative-estimate file) | Met | Unit: a bounded `ArrayBlockingQueue` on the same workload and heap instrument (B2h). Cluster: the in-flight cap, whose binding is read as `RequestsSize` (C6). |
| B. Logic | each step says what it establishes | Met | B2e/B3e, B2h/B3h. |
| B. Logic | prediction stated in numbers or a clear relation | Partly | B2f exact counts; B3f "≈ 512 / 4096 requests, 8×" needs offered load above the cap (C3). Heap statistic and "linear" undefined: defined by U3, C5, C6. |
| B. Logic | every plausible outcome has a conclusions row with its evidence | Partly | Missing: the OOM arm (U-a, U-b, U-c, U-d), and a queue that outlives its admission charge (C-a). Added before the run. |
| B. Logic | confirmation needs ceiling-follows-knob and direct disallow evidence | Met | Unit: pending == N and `getMaxTasksQueued`; cluster: the gauge, `RequestsSize` at the cap, and Pending. |
| B. Logic | alternative explanations and their controls | Partly | Pool size is a control (c, w); memtable growth is separated by C5; thread-local per-worker buffers (the `concurrent_compactors` pattern) are not measured. Left for stage 3. |
| C. Specific | a human can follow it from the intro and §9a | Met | A3, B1. |
| C. Specific | an AI can run §9b–§9e without re-deriving the code path | Partly | B3c's stress command was missing the client capacity (C3); the paths named /tmp/c509 (E1). |
| C. Specific | knob, values, workload, commands, observables, sampling, stop conditions exact | Partly | Fixed by U1–U4, C1–C6. |
| D. Runnable | harness and environment prerequisites exist or are listed | Met | Built here from the sibling harness. |
| D. Runnable | workload arithmetic reaches the limit (data, time, disk, memory) | Partly | `threads=1024` offers 64 MiB, below the 256 MiB cap (C3); 1 GiB heap cannot hold 256 MiB of admitted requests (C1); the per-IP default 51 MiB would bind first (C2). Fixed. |
| D. Runnable | load-bearing citations spot-checked against the pinned clone | Met | Checked as cited: `SEPExecutor.java:68, 103-106, 119-145 (135 `if (taskPermits == 0)`), 217-240, 398-401`, `ThreadPoolMetrics.java:42, 93, 105`, `DatabaseDescriptor.java:649-657`, `Config.java:150-151, 296-302, 1399`, `SettingsMode.java:138-139`, `Mutation.java:440-460`, `SetConcurrency.java:42-52`. One new finding: the yaml refuses `concurrent_writes: 1` (D1). |

| # | Recommendation | Applied? | Why |
|---|---|---|---|
| E1–E3 | clone `~/cassandra-mta`, 127.0.0.4, JMX 7204, no heap dump | Applied 2026-10-22 | shared host; disk |
| U1–U4 | 16-JVM matrix, exact workload, statistics defined (live, bytes/task, k, "linear", "no blocking"), OOM arm and rows U-a..U-d | Applied 2026-10-22 | outcomes without a row; undefined terms |
| C1 | heap 2 GiB | Applied | arithmetic (256 MiB × 2 for the cached serialization) |
| C2 | per-IP limit = global; receive queue 0B | Applied | the per-IP default and the per-connection queue would bind first |
| C3 | 6000 threads, `connectionsPerHost=16 maxPending=1024` | Applied | 1024 threads offer 64 MiB < 256 MiB; stress default 8 × 128 pending |
| C4–C6 | four arms; P, RS, HQ, MTQ statistics; definitions of the filed rows | Applied | undefined terms |
| C7 | added row (C-a) | Applied | a queued mutation outlives its admission charge (write timeout 2000 ms, `Config.java:150-151`) |
| D1 | `concurrent_writes: 2` in the yaml, `nodetool setconcurrency MutationStage 1` live | Applied 2026-10-22 (runbook fix) | the node refuses 1 at start |
| S1 | the 128-multiple structure of Pending (see 4.2 part 2) and per-worker memory | Left for stage 3 | not tested |

**Agreement criteria** — no run 2.

## 2. Environment

| Field | Run 1 |
|---|---|
| Date | 2026-10-22 (EDT). Unit pass 09:48:49–09:53:20, OOM rerun 09:53:50–09:54:57; cluster shakedowns 09:55–10:00; cluster run 10:01:34–10:21:10 |
| Node | `pc07` = `node0.jason92-320876.misconfiguration-pg0.cloudlab.umass.edu` (40 cores, 251 GiB), session run directly. **Deviation E4: the host was shared with another stage-4 session** (its own clone, ring members on other loopback addresses, `cassandra-stress mixed`); load average 1.3 at the unit pass, 11.5 at the OOM rerun, **69 at the cluster start**. CPU contention can only slow the queue's drain and the stress; it is a confound for P in the cluster tier. |
| OS and kernel | Ubuntu 22.04.2 LTS, `5.15.0-187-generic` |
| JDK / Ant | openjdk 11.0.32.1 (2026-08-18) / Ant 1.10.12 |
| Local clone | `~/cassandra-mta` at `cassandra-5.0.9` (`b5f2a54210d541339c2e7c17a794195cac0e67c2`), `ant build-test` 1 min 9 s |
| Case-file / harness commit | untracked (repo HEAD `00922e0`); sha256 above; harness md5 in `~/stage4-harness-run/mta.md5` |
| Storage | `~/stage4-mta/node1/` on local `/dev/sda3`, 50 GB free at start; data removed after the run |
| Full logs | `pc07:~/stage4-logs/mta/` (`run1/unit/` ant-free per-JVM `out-*`, `gc-*`; `run1/cluster/` samplers, `system-/debug-/gc-<lifetime>.log`, `stress-*.out`; `shake2/`; `case-as-filed.md`) |

## 3. Runbook defects

| # | Run | Step | Problem | Fix | Decision | Case-file commit |
|---|---|---|---|---|---|---|
| H1 | unit pass 1 | B2c OOM arm | After the `OutOfMemoryError` the probe's own `printf` hit the full heap (an 8 MiB humongous reserve was not reclaimable without a GC), so the two P = 1 KiB N = 4e6 JVMs died with no `PROBE` line | Reserve as 64 small arrays, `System.gc()` after the catch; only those two configurations were rerun (`unit-run.sh run1 oom`); every other row is from pass 1; the rerun's `summary.txt` replaced pass 1's (kept as `summary-pass1.txt`) | 2026-10-22, harness only; nothing before the OOM changed | — |
| D1 | cluster shakedown 1 | B3b, B3e arms A and B | The node refuses `concurrent_writes: 1` ("must be at least 2") | yaml 2, then `nodetool setconcurrency MutationStage 1` before the load, read back `1`; node log "Resized MutationStage maximum pool size from 2 to 1" | 2026-10-22, dated fix in the case file; B1, B3f, B3g unchanged | none (untracked) |
| H2 | cluster | `system.log` | `system.log` accumulates across lifetimes in one clone (the shakedown's lines appear in `system-1.log`) | parse only from each arm's phase times | — | — |

## 4. Run 1

**Scope:** unit B2 (all 16 sep configurations, 2 control, base), cluster B3 (arms A B C D, one lifetime each). **Command log and excerpts:** [`maxTasksQueued-addTask-taskPermits--autonomous/run1/`](maxTasksQueued-addTask-taskPermits--autonomous/run1/) (`unit/probe-lines.txt`, `unit/summary-*.txt`, `unit/gc-oom-arm-tail.txt`, `cluster/summary.txt`, `phases.json`, `samples-*.csv`, `stress-results.txt`, `commands-excerpt.txt`, `selfcheck.py`, `selfcheck.txt`).

### 4.1 Readings

**Unit tier** (`run1/unit/probe-lines.txt`; `unit-analyze`: 127 yes, 2 NO after the rerun; the NO lines are the two OOM arms' block time)

| Test or assertion | Result | Evidence |
|---|---|---|
| `getMaxTasksQueued()` | 2147483647 in all 16 sep configurations | `probe-lines.txt` |
| pending after N submissions (c blockers active) | = N exactly in the 14 configurations that fit (c = 1, 8 × P = 64: N = 1e4 … 4e6; P = 1024: N = 1e4 … 1e6); `RejectedExecutionException` 0 everywhere | same |
| heap per queued task (bytes/task) | P = 64: 152.4 / 152.0 / 152.0 / 152.0 at N = 1e4 / 1e5 / 1e6 / 4e6; P = 1024: 1112.4 / 1112.0 / 1112.0; k = bytes/task − P = 88.0 (all c); c = 1 over c = 8 ratio 1.000 | same |
| live heap | P = 64: 1.5 / 14.5 / 145.0 / 579.8 MiB; P = 1024: 10.6 / 106.1 / 1060.5 MiB | same |
| class histogram, c = 1 P = 1024 N = 1e6 | 1,000,004 `ExecutionFailure$1` wrappers + 1,000,001 `ConcurrentLinkedQueue$Node` + 1,000,000 lambdas (24 B each) + 1,034,915 `[B` (1,047,609,776 B) | `probe-lines.txt` (HISTO) |
| OOM arm (P = 1024, N = 4e6) | c = 1: `OutOfMemoryError` to the submitter after 1,909,616 submits, pending 1,909,616, rejected 0; c = 8: 1,909,179 / 1,909,179 / 0 | same |
| longest block of 1e5 submits | ≤ 0.73 s in the 14 non-OOM configurations; **19.33 s (c = 1) and 15.52 s (c = 8) in the OOM arms**; GC pauses in those JVMs total 30.3 s and 27.8 s (67 pauses each) against submit loops of 28.1 s and 22.5 s | `probe-lines.txt`, `gc-oom-arm-tail.txt`, `selfcheck.txt` U10 |
| drain after the latch | pending 0 and live heap 0.0 MiB above the baseline in all 16 non-OOM drains (drain 2.5–8.9 s) | same |
| control `ThreadPoolExecutor` | c = 1, 8: pending 1000, 999,000 rejected, live heap 1.0 MiB | same |

**Cluster tier** (`run1/cluster/summary.txt`, `samples-jmx-<n>.csv`, `phases.json`; run script 12 yes / 5 NO)

| Arm (cap, w) | Observable | Reading | Evidence |
|---|---|---|---|
| A (256 MiB, 1) | getconcurrency; MaxTasksQueued; Active max | 1; 2147483647 at 236 samples; 1 | `summary.txt`, `samples-jmx-1.csv` |
| A | P (peak Pending, window) / median Pending / RS peak | **383** / 127 / 255.98 MiB | same |
| B (32 MiB, 1) | P / median / RS | **383** / 127 / 31.97 MiB | `samples-jmx-2.csv` |
| C (256 MiB, 8) | P / median / RS | **1289** (one 1-s sample; next-highest 376) / 120 / 255.98 MiB | `samples-jmx-3.csv` |
| D (32 MiB, 8) | P / median / RS | **376** / 120 / 31.97 MiB | `samples-jmx-4.csv` |
| A B C D | HQ (median post-GC heap − memtable) | 883 / 1080 / 1081 / 911 MiB; baseline 69–105 MiB; heap used max 1897 / 1944 / 1939 / 1936 MiB of 2048 | `samples-heap.csv`, `summary.txt` |
| A B C D | P × 64 KiB ÷ cap | 0.09 / 0.75 / 0.31 / 0.73 | `selfcheck.txt` |
| A B C D | stress | 701 / 635 / 684 / 943 op/s; 4,096 / 3,770 / 6,357 / 6,258 errors (WriteTimeout) | `stress-results.txt` |
| A B C D | smallest nonzero Pending values in the window | A and B: 125, 126, 127, 255, 383 (multiples of 128 minus 1); C and D: 116–120, then 248, 376 | `selfcheck.txt` |
| A B C D | guard (post-GC heap > 1.8 GiB) | not triggered; no OOM; the node finished all four lifetimes | `summary.txt` |

### 4.2 Conclusion and logic

1. **Validity.**
   - **Unit.** Every sep configuration had its c blockers active before the N submissions [observed: `probe-lines.txt`, `activeBefore`]. The limit "N tasks" was reached and exceeded by up to 4e6 tasks, and by heap exhaustion at 1 KiB [observed]. Valid.
   - **Cluster.** Each arm's pool size was read back (1, 1, 8, 8; node log "Resized … from 2 to 1" for A and B) [observed: `summary.txt`, `system-*.log`]. `RequestsSize` reached 100.0 % of the cap in every arm, so the admission cap bound [observed: `samples-jmx-*.csv`]. The yaml carried both in-flight limits equal and receive queue 0B [observed: `summary.txt`]. The stress was the filed one with C3's client capacity [observed: `session.log`]. Valid; the confound is part 6.
2. **Readings.**
   - (a) Unit k = 88 B per queued task is constant across P, N and c: `ExecutionFailure$1` + queue node + lambda at 24 B each, plus the 16 B array header [observed: histogram]. [inferred: 3 × 24 + 16 = 88]
   - (b) The OOM arms' long blocks coincide with the GC: pauses total more than the loop time [observed: `gc-oom-arm-tail.txt`, `selfcheck.txt`]. [inferred: the blocks are G1 full-GC thrash near the heap limit, not the executor.] The frozen "no block ≥ 5 s" clause of U-a is therefore **missed** and recorded as such.
   - (c) Cluster: Pending is quantized in steps of 128 (127 / 255 / 383) in A and B, and sits at 116–120 with rare 248 / 376 in C and D [observed]. 128 is `native_transport_max_threads` (`Config.java:283`). [inferred: the queue depth is set by the request-thread pool, not by the executor and not by the in-flight bytes; not tested.]
   - (d) Heap: HQ is 883–1081 MiB in **every** arm, including the 32 MiB cap, so it does not follow the in-flight cap either [observed]. What holds it is not identified (no histogram taken) [not observed].
   - (e) C's peak 1289 is one 1-s sample; the next-highest value in C is 376. D reads 376. [observed: `samples-jmx-3.csv`]
3. **Matched row.**
   - **Unit, B2g row 1** — "pending == N for all N, no exception/blocking, heap linear in N, same for c=1 and 8; control rejects at its capacity: Claim confirmed". Pending == N and no exception in all 14 fitting configurations; bytes/task within ±10 % of its mean (spread ≤ 0.3 %) and k = 88 in [20, 300]; c = 1 / c = 8 = 1.000; the control rejected 999,000 of 1e6 with queue 1000 and live heap 1.0 MiB. **The OOM arm matches U-a** (`OutOfMemoryError` to the submitter, pending == submitted, rejected 0; B2f's "OOMs rather than being refused") **except its block-time clause (missed)**; U-d holds. This is Confirmed with a recorded miss, not a new row.
   - **Cluster: no row matches.** The frozen statistics (C6): P(A)/P(B) = 1.00 and P(C)/P(D) = 3.43 (row 1 needs both in [4, 12]: **no**); both ratios < 2 (row 2: **no**, 3.43 from C's single sample); P < 20 (row 3: **no**); HQ(w = 8) ≥ 1.3 × HQ(w = 1) at both caps (row 4: **no**, 1.22 and 0.84); P × 64 KiB > 1.25 × cap (row C-a: **no**, maximum 0.75). Recorded **Not confirmed (no matching row)**; no row or prediction is added after the readings.
4. **Excluded rows.**
   - Unit: B2g row 2 (plateau, throw or block: refuted) — pending reached N = 4e6, no throw, no block other than GC; row 3 (heap flat as pending grows) — heap rose linearly, 1.5 → 579.8 MiB; row 4 (heap grows with c) — ratio 1.000; row 5 (control never rejects / drained) — the control rejected at 1000 and every queue drained.
   - Cluster: row 3 (Pending never grows) is excluded by P = 376–1289; row 1 by the ratios; row 4 by 1.22 / 0.84; C-a by 0.09–0.75. **The reading that is closest to the filed row 2** (A and B at the same 383, medians 127 / 127 / 120 / 120, RequestsSize ×8 apart) is not the frozen statistic and is not used to match. [inferred]
5. **Observed vs. inferred.** The inferred statements the conclusion depends on: (i) the OOM-arm block time is GC (part 2b); (ii) Pending is set by the 128 request threads (part 2c; only shapes the "undetermined", not a matched row); (iii) the queue's own bytes are heap − memtable (C5).
6. **Deviations and gaps.** The host was heavily loaded by another session during the cluster tier (load average 69 at the start). Timeouts are the common stress outcome (4–6 k per arm). Heap sat at 1.9 GiB used in every arm, so the node was near its heap limit throughout; GC may have affected Pending. No class histogram on the cluster, so nothing says what the ~1 GiB net heap is. The default 10 % heap in-flight value (B3b) was not run. The pool-size control was w = 1 versus 8 only through `setconcurrency` on a 2-worker yaml (D1). The OOM arms' `System.exit` returned exit code 1 after the `PROBE` line; the line is complete.
7. **Core question.** **Unit:** the executor's queue is unbounded: `getMaxTasksQueued()` is a constant 2147483647 and `execute` accepted 4,000,000 tasks (and 1.91 M × 1 KiB before the JVM heap, not the executor, stopped it), with heap exactly proportional to the count and independent of the pool size, while a bounded queue stopped at 1000 [unit B2 rows above]. So the constraint does not cap usage there. **Cluster:** the gauge stayed 2147483647 and no mutation was refused by the executor in any arm; the admission cap bound exactly (RequestsSize at the cap), yet queue depth did not scale with it, so the predicted mechanism "usage follows the upstream in-flight cap" is not what the readings show, and no frozen row says what they do show; the cluster tier is **undetermined** on the file's own table.

**Conclusion (one line):** **Unit: B2g row 1 (with U-a; its block-time clause missed) — Confirmed, does not cap. Cluster: Not confirmed (no matching row) — undetermined.**

## 5. Self-check of run 1 — AI

### 5.1 Check of run 1's conclusion

Re-read from the raw files by `run1/selfcheck.py` (output `run1/selfcheck.txt`: 31 hold, 1 DOES NOT HOLD (U9, the recorded block-time miss)) and by hand.

| Part | Holds? | Note (file re-read) |
|---|---|---|
| 1. Validity | yes | `activeBefore` = c in 16/16; `getconcurrency` 1, 1, 8, 8; RS at 99.99–100 % of the cap in all four arms; yaml and stress command re-read in `summary.txt` and `session.log` (C1–C7 checks). |
| 2. Readings | yes | `out-*.txt` re-parsed: k = 88.0, ratios 1.000; Pending steps re-read from `samples-jmx-*.csv`; the C-peak is one sample. |
| 3. Matched row | yes (unit), none (cluster) | Unit row 1 re-checked configuration by configuration (U1–U8); U-a's block clause does not hold (U9) and is recorded as a miss. Cluster: C8–C12 recompute each frozen statistic independently and find no row satisfied. |
| 4. Excluded rows | yes | Each excluded row has its reading in parts 3–4; the closest-to-row-2 reading is flagged as post hoc and unused. |
| 5. Observed vs. inferred | yes | The three inferred statements are tagged; (i) is supported by the GC logs (30.3 s and 27.8 s of pauses, U10). (ii) is not independently supported and limits the cluster tier to "undetermined". |
| 6. Deviations and gaps | yes | Shared host load, heap near its limit and the missing cluster histogram are all stated. |
| 7. Core question — the steps from reading to answer follow the audited logic | yes (unit), partial (cluster) | The unit chain "no cap at the executor → heap ∝ count → the control caps" is complete. The cluster chain breaks at the step "Pending follows the upstream cap": it does not, and the table has no row for that. |

### 5.2 Run 2?

**No** — decided 2026-10-22 (the instruction for this batch is run 1 only). The unit conclusion rests on direct counts; the cluster tier would need a new design (a histogram of the ~1 GiB, `native_transport_max_threads` varied), which is a stage-3 amendment, not a repeat.

## 6. Run 2 — fresh AI session (optional)

Not done.

## 7. Comparison — only if run 2 was done

Not done.

## 8. Verdict — AI

**Stage-3 estimate:** negative.

**Claim tested (B1):** a SEPExecutor accepts and holds an arbitrary number of queued tasks; `PendingTasks` rises 1:1 with submissions with no rejection or blocking at `addTask`, `MaxTasksQueued` stays 2147483647, the heap held by the queue grows linearly with the queued count independent of the pool-size knob, and heap growth is stopped only by an upstream limit or the JVM heap, not by the executor. "Confirmed" means this claim held.

| Tier | Verdict (B2g / B3g row) | Effect on the constraint | Basis | Date |
|---|---|---|---|---|
| Unit | B2g row 1 (with U-a, block-time clause missed) — **Confirmed** | does not cap | run 1 + self-check | 2026-10-22 |
| Cluster | **Not confirmed (no matching row)** | undetermined (the executor refused nothing; queue depth did not follow the in-flight cap) | run 1 + self-check | 2026-10-22 |

**Positive control:** unit — `ThreadPoolExecutor(ArrayBlockingQueue(1000))` rejected 999,000 of 1e6 with live heap 1.0 MiB where the SEP queue held all of them. Cluster — the in-flight cap moved `RequestsSize` exactly (255.98 vs 31.97 MiB) while `MaxTasksQueued` did not, so the instrument can see a binding limit; but Pending did not follow it, so the control did not give the file's expected contrast.

**Feedback filed:** the case file's section D (2026-10-22), and the dated amendments and fix D1 in its text. No other section amended. `_INDEX.md`, `HANDOFF.md` and `predicted-negative.md` are left to the coordinator.
