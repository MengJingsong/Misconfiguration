# maximumPoolSize-takeTaskPermit-workPermits--autonomous — stage-4 results  <!-- file: results/maximumPoolSize-takeTaskPermit-workPermits--autonomous.md -->
> **Case:** [`maximumPoolSize-takeTaskPermit-workPermits--autonomous`](../../stage3-ai-deep-read/cases/maximumPoolSize-takeTaskPermit-workPermits--autonomous.md)
>
> **Status:** **Closed 2026-10-21. Unit: Confirmed — does not cap. Cluster: Not confirmed (R5 row BIND-5) — undetermined.** "Running tasks × per-task bytes" was tested with the pool binding at every value. Large internode mutations (> 64 KiB) hold heap only while *running*: `Mutation` instances = v exactly, and live heap +5.5 / 9.4 / 21.9 / 70.2 MiB at v = 1 / 8 / 32 / 128. The queue waits off heap, bounded by the receive reserve. Small mutations hold a flat ≈ 240–272 MiB on heap. The frozen statistics put both just outside the BIND-2 row: GC.heap_info is non-monotone at 8 → 32 by 3.5 MiB, and the small arm's max/min of live bytes is 1.2001. The filed phases' "H small at v ≥ 8" and drift rows also missed, because of the heap held by the write load itself. No run 2.
>
> **Agent:** autonomous. "§9a" below means B2f/B2g (unit) and B3f/B3g (cluster), "§9b–§9e" means B2a–B2e or B3a–B3e, and the case file's feedback section is its section D.

## 1. Before run 1 — design audit and freeze

| Field | Content |
|---|---|
| **Case-file version** | Autonomous file, untracked. As filed: sha256 `dcfe1d905963f948c74f21d077660e70dfee02de42544d6abd78fe995e68c41e`. After the step-0 audit amendments R1–R5 (2026-10-21), the **frozen version** is `c004650ff618cd601bc3b7dd5def1409f8920f54fc8ba5446dc945c35e89213c`. Runbook fixes D1 (unit) and D2 (R5) followed, made before any reading of the tier they touch, with B1 and every prediction and row unchanged. The **version run 1 used** is `e50549b201956d904e89363d35f5f01beb45d8eee99398dbdd542d0aaee8b0dd`: the unit tier ran with D1 applied, the cluster tier with D1 and D2. The file is untracked (repo HEAD `a74026e`). |
| **Harness** | [`harness/maximumPoolSize-takeTaskPermit-workPermits--autonomous/`](../harness/maximumPoolSize-takeTaskPermit-workPermits--autonomous/README.md), written 2026-10-21, not committed: `SEPMemoryProbeTest.java`, `unit-run.sh`, `unit-analyze.py`, `make-node-yaml.sh`, `Jmx.java`, `hold-mutation.btm`, `cluster-run.py`, `selfcheck.py`. **Instrument checks (not readings):** `javac` of the test; Byteman `TestScript` on the rule (no errors); two bind-arm shakedowns (`~/stage4-logs/mps/shakedown-bind{1,2}/`). md5 of the run copy is in `~/stage4-harness-run/mps.md5`. |
| **Tiers and values** | Unit (B2): n = 1 · 4 · 32 · 128 (Phase 1), shrink 32 → 4 (Phase 2, line 165), byte cap 16 · 64 MiB (Phase 3), working memory per running task at n = 1 · 4 · 32 · 128 (Phase 4, R4), three repetitions. Cluster (B3): B `MutationStage` v = 32 · 8 · 1 · 0 at 20,000 × 1.1 KiB writes/s. Reserve control 16 · 128 · 512 MiB at v = 0. Drift repeat v = 32 · 0 (R3). Bind arm (R5): group commit 5 s on B, v = 1 · 8 · 32 · 128 with S = 32 KiB and L = 256 KiB mutations. |
| **Audit bottom line** | **Ready after amendments** — 2026-10-21 |

### 1.1 Design audit

| Group | Check | Rating | Note (section checked) |
|---|---|---|---|
| A. Core question | constrained quantity is memory or disk bytes | Met | B1/A2: the heap held by an SEP stage. The knob is a count of running tasks, and the claim is that it does not bound that heap. |
| A. Core question | knob varied, ≥ 3 values incl. default | Met | B2b: n = 1 · 4 · 32 · 128 (32 is the default). B3b: v = 32 · 8 · 1 · 0 at runtime. |
| A. Core question | real resource measured, not only the counter | Met | B2d: heap after GC. B3d: `jmap -histo:live` and `GC.heap_info`. Per-task bytes are inferred, and B3d names that gap. |
| A. Core question | usage driven to the limit and past it | **Partly → amended (R4, R5)** | Unit: M ≫ n, but each payload is allocated at construction, so a component that only *running* tasks hold (the `concurrent_compactors` pattern) cannot show. Cluster: at 20,000 × 1.1 KiB/s B keeps up at v = 32 and 8, so the pool binds only at v = 0 (and perhaps 1). This is the same gap that left "running tasks × per-task bytes" open in `concurrent_writes`. R5 makes every task last seconds (group commit) at a reserve-bound backlog, with two known message sizes on the two inbound paths. R4 adds the matching unit instrument check. |
| A. Core question | positive control (negative estimate) | Met | Unit Phase 3: a byte cap on the same tasks. Cluster: the receive reserve at v = 0 on the same instruments, which the bind arm also uses. |
| B. Logic | each step says what it establishes | Met | B2g/B3g, B2h/B3h. |
| B. Logic | prediction in numbers or a clear relation | Met | B2f exact counts and MiB bands; B3f P and H bands and ratio ≥ 8. |
| B. Logic | every plausible outcome has a row | Partly → amended (R2, R3) | Missing: repeat disagreement (unit) and drift (cluster). Undefined: "≈", "≫", "small", "decreases with v". |
| B. Logic | confirmation needs ceiling-follows-knob and direct disallow evidence | Met | Phase 2 drives `workPermits` to −28 (active 32 > max 4) and observes the exits at line 165. The cluster records Active per sample and the node's resize log. |
| B. Logic | alternative explanations and their controls | Partly | Memtables (flush), GC (three GCs; full GC of the histogram), drift (R3). Per-running-task memory is not controlled in the filed design; R4 and R5 add it. |
| C. Specific | a human can follow it from the intro and §9a | Met | Header, A3, B1. |
| C. Specific | an AI can run §9b–§9e | Met | B2a is a complete test; B3 gives the commands. |
| C. Specific | knob, values, workload, commands, observables, sampling, stop conditions exact | Partly → amended (R1) | The stress warm-up is unthrottled. Paths `/tmp/sep-run` and addresses 127.0.0.1/.2 are run-environment details (E1 below). |
| D. Runnable | harness and environment prerequisites | Met | `~/cassandra-mps` (fresh clone at the tag, `ant build-test` done 2026-10-21 in 1 min 10 s). No Byteman. |
| D. Runnable | workload arithmetic reaches the limit | Met (after R5) | v = 0: the 132 MiB reserve fills in ≈ 6 s at 22 MB/s. R5: B applies ≈ 2v/5 s⁻¹ (≤ 51/s at v = 128) against 400/s (S) and 100/s (L), so the reserve fills in ≈ 12 s. Disk ≤ 2.6 GB per phase per node, truncated between phases; 53 GB free. Heap 8 GiB per node. |
| D. Runnable | load-bearing citations spot-checked | Met | `SEPExecutor.java:50, 59, 68, 102-106, 110-117, 119-145, 165-178, 188-203, 347-350, 368-396`; `SEPWorker.java:134-161`; `SharedExecutorPool.java:141-153`; `ResourceLimits.java:90-130`; `InboundMessageHandler.java:148-151, 157-195, 315-385, 391-441, 481-509`; `Mutation.java:440-520`; `CommitLog.java:300-338`; `GroupCommitLogService.java:34-41`; `DatabaseDescriptor.java:505-527, 560-568`; `Verb.java:116, 134`; `OutboundConnections.java:69`; `build.xml:1153, 1192, 1382-1392`. All as cited. Note: the testsome macro sets `maxmemory="1024m"` (`build.xml:1153`). Whether B2a's `-Xmx2g` wins is read from the test JVM (Phase 4 logs its max heap). |

| # | Recommendation | Applied? | Why |
|---|---|---|---|
| R1 | `no-warmup` on every stress command | Applied 2026-10-21 (case-file amendment block) | a 50,000-op unthrottled warm-up precedes every `duration=` run |
| R2 | Define the statistics and terms; add a unit repeat row | Applied 2026-10-21 | B3g's "≫", "small", "decreases" and B2g's "∝ n" were undefined; B2e repeats three times without a row |
| R3 | Drift repeat in a fresh B lifetime with the default reserve; add a row | Applied 2026-10-21 | B3h names the repeat but not its configuration or tolerance |
| R4 | Unit Phase 4: per-running-task working memory (instrument check) | Applied 2026-10-21 | Phase 1 cannot show memory held only by running tasks |
| R5 | Bind arm: group commit on B (long tasks), timeouts raised (reserve-bound backlog), S and L sizes, v = 1 · 8 · 32 · 128, rows BIND-1…5, combining rule | Applied 2026-10-21 | the pool does not bind at v ≥ 8 in the filed workload; "running × per-task bytes" (`concurrent_compactors`) was left open by `concurrent_writes` |
| S1 | The file covers seven SEP executors but runs only `MutationStage` (and synthetic executors in the unit tier). `ReadStage` and `Native-Transport-Requests` hold different per-task bytes. | Left for stage 3 | outside this design |
| S2 | B3e step 2d's TRUNCATE runs on `MutationStage` (`Verb.java:134`). It must follow the restore, as the file says. R5 drains at v = 512 first. | Noted (R5) | — |

**Environment deviation E1 (not an amendment):** the nodes run on 127.0.0.21 (A) and 127.0.0.22 (B), with JMX 7221/7222, instead of B3a's 127.0.0.1/.2 and 7199/7299. Node directories are `~/stage4-mps/{A,B}` instead of `/tmp/sep-run`, and the clone is `~/cassandra-mps` instead of `~/cassandra-run1`. The design is unchanged.

**Agreement criteria** — not filled (no run 2 planned).

## 2. Environment

| Field | Run 1 | Run 2 |
|---|---|---|
| Date | 2026-10-21, EDT. Unit attempts 17:44 and 17:45 (D1); unit run 17:46:43–17:49:23. Cluster attempt 1 17:49–18:23 (D2-i, not counted). Bind shakedowns 18:24–18:44. Cluster run 18:44:47–19:34:34. | not done |
| Node | `pc07` = `node0.jason92-320876` (40 cores, 251 GiB); the session ran on it directly. Other agents' sessions ran on the same host (their Claude processes only; no other `java` at the start or the end). **E1:** A = 127.0.0.21 / JMX 7221, B = 127.0.0.22 / JMX 7222 (B3a: 127.0.0.1/.2, 7199/7299); node directories `~/stage4-mps/{A,B}` (B3a: `/tmp/sep-run`). | — |
| OS and kernel | Ubuntu 22.04.2 LTS, `5.15.0-187-generic` | — |
| JDK / Ant | openjdk 11.0.32.1 (2026-08-18) / Ant 1.10.12 | — |
| Local clone | `~/cassandra-mps` at `cassandra-5.0.9` (`b5f2a54210d541339c2e7c17a794195cac0e67c2`), cloned from the shared clone; `ant build-test` passed in 1 min 10 s. `SEPMemoryProbeTest.java` was removed after the unit tier (`git status` clean). | — |
| Case-file / harness version | case file untracked, sha256 `e50549b2…` for both tiers' run 1; harness not committed (md5 in `~/stage4-harness-run/mps.md5`) | — |
| Storage | `~/stage4-mps/` on local `/dev/sda3` (55 GB free at the start; peak use about 4 GB). Data, commit logs and hints were removed at the end, leaving 48 MB of conf and logs. | — |
| Full logs | `pc07:~/stage4-logs/mps/`: `run1/unit/` (ant and per-test logs, GC logs, `.probe`), `run1/cluster/` (`session.log`, `samples-*`, `histo-*`, `stress-*`, `A<n>-/B<n>-{system,debug,gc}.log`, `phases.json`), `run1/cluster-attempt1-D2/`, `run1-attempt{1,2}-D1/`, `shakedown-bind{1,2}/`, `run1/selfcheck.txt` | — |

## 3. Runbook defects

| # | Run | Step | Problem | Fix | Decision (date) | Case-file version |
|---|---|---|---|---|---|---|
| D1 | unit attempts 1–2 | B2e step 3 | (1) `-XX:+UseG1GC` clashes with the testsome JVM's `-XX:+UseConcMarkSweepGC`: "Multiple garbage collectors selected" (`run1-attempt1-D1/unit/ant-rep1.log`). (2) The macro's `maxmemory="1024m"` (`build.xml:1153`) comes after `test.jvm.args`, so `-Xms2g` exceeds `-Xmx1024m` and the JVM does not start (`run1-attempt2-D1/unit/ant-rep1.log`). | `-Dtest.jvm.args="-XX:-UseConcMarkSweepGC -XX:+UseG1GC"`; the test heap is 1 GiB (Phase 4 logs `xmxMiB=1024`). B2f is unchanged: the largest phase holds about 128 MiB. The unit tier restarted. | 2026-10-21 | dated D1 block |
| D2 | cluster attempt 1 (filed phases done, then the hang); bind shakedowns 1–2 | R5 | (i) B restarted under `commitlog_sync: group` hung in `SystemKeyspaceMigrator41.migrate`. The main thread was parked in `GroupCommitLogService.maybeWaitForSync` (jstack taken 18:23 and transcribed in this row; the thread dump was not saved), and B never reached UN. (ii) On a fresh pair, group commit stalled B's Gossip and Migration stages for minutes, so every small mutation was dropped as "incompatible schema" (`shakedown-bind1/cluster/B1-debug.log`). (iii) Group-commit waits were far shorter than 5 s (≈ 40 writes/s at v = 8), so the pool would not bind at v ≥ 32. Also, R5(b)'s `using_bytes + using_reserve_bytes` double-counts (`InboundMessageHandlers.java:321-329`). | B is held by a Byteman rule (`hold-mutation.btm`, 2 s at `MutationVerbHandler.doVerb` entry, after deserialization) with the periodic commit log. R5(b) reads `using_bytes`. Predictions and rows are unchanged. The **cluster tier restarted from its beginning**, and attempt 1's filed readings are not counted. | 2026-10-21 | dated D2 block |
| H1 | unit | B2e step 4 | The test JVM logs `System.out` one printf argument per line, so `grep PROBE` of the XML finds nothing (as in `concurrent_writes`). | Rebuilt from the ant log by the run script and from the per-test log by the self-check. | harness only | — |
| H2 | cluster run 1 | analysis | The filed lifetime-1 baseline and R5's L1 baseline share the label `L1-baseline`. The first analysis found "baseline missing" for v = 32 · 8 · 1 · 0, and the filed baseline **histogram file was overwritten** (its `GC.heap_info` and histogram totals survive in `samples-heap.jsonl`). | `reanalyze` matches baselines by time stamp. The self-check compares the filed L1 phases with the only raw baseline histogram left, R5's L1 baseline (87.1 MiB of live bytes against 83.7 recorded), and says so. | harness only, 2026-10-21 | — |

**Deviation found in the readings, not fixed (R5's premise):** `write_request_timeout: 300000ms` did not stop expiry. In 5.0 a mutation's deadline is min(verb timeout, client request time + `native_transport_timeout` = 12 s) (`transport/Dispatcher.java:238-245, 270`). In every bind phase most queued mutations were dropped as expired when dequeued: dropped `MUTATION_REQ` was 36,059 of 36,065 completed at S1 and 5,407 of 7,550 at L128, with a mean cross-node dropped latency of 14.4 s (`B8-system.log`). The backlog stayed reserve-bound anyway: Pending was flat at 4,087–4,214 (S) and 399–526 (L), and `using_bytes` was 132.0 / 131.8 MiB in every phase. So the queue's contents churned, but its size was the same at every v. The stage-4 lessons already warned about this (client requests held > 12 s need `native_transport_timeout` raised); the audit missed it.

## 4. Run 1

**Scope:** unit B2 Phases 1–4 × 3 repetitions. Cluster: B3e (v = 32 · 8 · 1 · 0), the control (16 · 128 · 512 MiB at v = 0), the R3 repeat, and R5 (S and L × v = 1 · 8 · 32 · 128), in 13 B lifetimes and 2 A lifetimes. **Command log and excerpts:** [`maximumPoolSize-takeTaskPermit-workPermits--autonomous/run1/`](maximumPoolSize-takeTaskPermit-workPermits--autonomous/run1/): `unit/summary.txt`, `unit/rep*.probe`, `cluster/summary.txt`, `cluster/reanalysis.txt` (the figures below), `phases.json`, `samples-tp.csv`, `samples-heap.jsonl`, `histo-excerpt.txt`, `resize-lines.txt`, `stress-results.txt`, `selfcheck.py`, `selfcheck.txt`.

### 4.1 Readings

**Unit tier** (`unit/summary.txt`: 3 × `Tests run: 4, Failures: 0, Errors: 0`; 52 yes / 9 NO; the 9 NO are Phase 4's band)

| Test or assertion | Result | Evidence |
|---|---|---|
| Phase 1, n = 1 · 4 · 32 · 128, M = 2000 × 64 KiB | active = running = peak = n; pending = 1999 · 1996 · 1968 · 1872; heapDelta 125.2 · 125.2 · 125.2 · 125.3 MiB in all three reps | `unit/rep*.probe` |
| Phase 2, shrink 32 → 4 (line 165) | 2a: active 32, pending 200, 14.5 MiB. 2b: max 4, **active 32**, pending 200. 2c: active 4, running 4, pending 196, 12.6 MiB. All three reps. | same |
| Phase 3, byte cap 16 / 64 MiB | accepted 256 / 1024; heapDelta 16.0 / 64.1 MiB | same |
| Phase 4 (R4), 1 MiB per *running* task | active = running = n, pending = 2000 − n; heapDelta 2.1 · 8.1 · 64.2 · 256.2 MiB = 2.0 × n MiB (predicted n × 1 MiB + ≤ 2) | same; JVM max heap 1024 MiB |
| Repeats | Phase 1 identical to 0.0 MiB across reps | `unit/summary.txt` |

**Cluster tier, filed phases** (`cluster/reanalysis.txt`). H = `GC.heap_info` used after the histogram's full GC, minus the lifetime's baseline (R2). Live bytes = the histogram's Total minus the baseline's (self-check).

| Value | Run | P (t ≈ 90 s) | H (MiB) | Live bytes (MiB) | `Mutation` | Other |
|---|---|---|---|---|---|---|
| v = 32 | filed | 0 | 146.3 | 110.9 | 0 | Active max 32; stress 19,882 op/s, 0 errors |
| v = 8 | filed | 0 | 261.4 | 258.0 | 43 | Active max 8 |
| v = 1 | filed | 59 (bursts to 26,689) | 361.7 | 294.3 | 43,024 | `using_bytes` 56 MiB at the sample |
| v = 0 | filed | 134,432 (flat; max/min 1.029 over t = 60–90 s) | 374.9 | 403.5 | 134,432 | Active 0 at every sample; `using_bytes` 140 MiB |
| reserve 16 MiB, v = 0 | control | 26,886 | 101.2 | 85.2 | 26,886 | `using_bytes` 28 MiB |
| reserve 128 MiB, v = 0 | control | 134,432 | 427.7 | 411.7 | 134,432 | 140 MiB |
| reserve 512 MiB, v = 0 | control | 503,162 | 1,515.5 | 1,531.5 | 503,162 | 524 MiB |
| v = 32 again | R3 | 0 | 432.1 | 224.1 | 3 | — |
| v = 0 again | R3 | 134,432 | 335.0 | 415.0 | 134,432 | — |
| resize lines on B | all | — | — | — | — | `Resized MutationStage …` 8, 32, 1, 32, 0, 32, (0, 32) × 4 (`resize-lines.txt`) |

**Cluster tier, R5 bind arm** (fresh B per phase, Byteman 2 s hold, A at 400/s (S) or 100/s (L), sampled at t = 60 s)

| Phase | Active (8 samples, t = 20–60 s) | Pending at plateau | `using_bytes` | H (MiB) | Live bytes (MiB) | `Mutation` | `byte[]` Δ (MiB) | direct Δ (MiB) |
|---|---|---|---|---|---|---|---|---|
| S1 | 1 × 8 | 4,214 | 132.0 | 238.8 | 270.8 | 4,215 | 266.0 | 0.3 |
| S8 | 8 × 8 | 4,207 | 132.0 | 255.3 | 271.3 | 4,215 | 266.0 | 0.4 |
| S32 | 32 × 8 | 4,183 | 132.0 | 258.9 | 226.9 | 3,489 | 221.6 | 1.2 |
| S128 | 128 × 8 | 4,087 | 132.0 | 240.2 | 272.2 | 4,215 | 266.1 | 4.2 |
| L1 | 1 × 8 | 526 | 131.8 | 5.5 | 5.5 | 1 | 2.6 | 222.1 |
| L8 | 8 × 8 | 519 | 131.8 | 57.4 | 9.4 | 8 | 6.1 | 230.1 |
| L32 | 32 × 8 | 495 | 131.8 | 53.9 | 21.9 | 32 | 18.1 | 228.1 |
| L128 | 128 × 8 | 399 | 131.8 | 86.2 | 70.2 | 128 | 66.1 | 239.9 |

The networking `BufferPool` gauges read negative in L1 (`UsedSize` −15.2 MiB, `OverflowSize` −106.3 MiB at t = 60), so R5(d)'s pool comparison is not interpretable. Stress ran 396–399 op/s (S) and 99–100 op/s (L) with 0 errors.

### 4.2 Conclusion and logic

1. **Validity.**
   - **Unit.** Valid. Every n was run three times; M ≫ n; the shrink drove `workPermits` to −28 [observed: `unit/rep*.probe`].
   - **Cluster, filed.** Valid. The pool sizes were set as listed, by `getconcurrency` and by the node's resize lines [observed: `resize-lines.txt`]. At v = 0 the queue reached the reserve and stayed there [observed: `samples-tp.csv`]. Stress held 19,871–19,982 op/s with 0 errors in every phase [observed: `stress-results.txt`].
   - **Cluster, R5.** Valid. The pool bound at every v: Active = v at 8/8 samples per phase, Pending flat, and `using_bytes` 132 MiB everywhere [observed]. Its premise of no expiry did not hold (§3), but the backlog stayed reserve-bound [observed].
2. **Readings.**
   - (a) **Filed phases.** With load running, H at v ≥ 1 includes heap that the write load itself holds after the flush (146–362 MiB at 0–43,024 queued mutations). The reason is inferred: memtables refilling between the flush and the histogram at 22 MB/s, plus in-flight request state. `GC.heap_info` after the histogram also adds up to about 290 MiB over the live bytes (v = 32 repeat: 598 vs 310 MiB) [observed: `samples-heap.jsonl`].
   - (b) **R5, L arm.** `GC.heap_info` carries 30–80 MiB above the live bytes (L8 57.4 vs 9.4) [observed]. The live bytes and the counts are monotone in v: `Mutation` = v exactly, and `byte[]` Δ ≈ 0.5 MiB × v = 2 × 256 KiB per running task [observed: `histo-excerpt.txt`].
   - (c) **R5, S32.** The histogram holds 3,489 `Mutation` against Pending 4,183 (other S phases: 4,215 ≈ Pending + v). This is unexplained.
   - (d) **Unit Phase 4** reads exactly 2.0 MiB per running task. The likely cause is a G1 humongous allocation: a 1 MiB + 16 B array spans two 1 MiB regions at a 1 GiB heap [inferred].
3. **Matched rows.**
   - **Unit.**
     - B2g row 5: "Phase 3 heapDelta tracks 16/64 MiB while Phase 1 stays flat at ≈125 MiB — Negative confirmed against a moving positive control": 16.0 / 64.1 against 125.2–125.3 MiB at every n.
     - Row 1: "Phase 1 heapDelta ≈ 125 MiB for all n, pending = M − n — Claim confirmed at unit level".
     - Row 3: "Phase 2b active = 32 > max = 4, then 2c active = running = 4 — line 165 branch exercised".
     - Phase 4 matches R4's row "does not follow n × 1 MiB — Invalid for R5's purpose; the unit verdict rests on Phases 1–3 only". It does follow n exactly, at twice the predicted slope.
   - **Cluster.** The combining rule makes R5's row the tier verdict, and R5 is **BIND-5** ("any other pattern … Not confirmed: report").
     - (a) holds: the pool bound everywhere.
     - (c) holds: H_S 238.8–258.9, max/min 1.084.
     - BIND-2 needs H_L increasing over 8 < 32 < 128 with H_L(128) − H_L(1) ≥ 40 MiB. H_L(128) − H_L(1) = 80.7, but H_L(8) = 57.4 > H_L(32) = 53.9, so BIND-2 fails on the frozen statistic.
     - On the self-check's independent statistic (live bytes), H_L is monotone (5.5 · 9.4 · 21.9 · 70.2), but H_S max/min is 1.2001, just outside "flat". That is also BIND-5.
     - The filed rows on their own would give R3's drift row ("Not confirmed: drift": H(32) 146.3 vs 432.1 on repeat). Row 1 fails its "H(32), H(8) < 100 MiB" part.
4. **Excluded rows.**
   - **Unit:**
     - Row 2 (**Refuted**, "falls ∝ n"): heapDelta(1) = 125.2 vs heapDelta(128) = 125.3.
     - Row 4 (2c running stays 32): running 4.
     - Row 6 (control does not track): it tracks.
     - R2 repeat row: the reps differ by 0.0.
   - **Cluster:**
     - B3g row 2 (**Refuted**, "H decreases with v"): H is highest at v = 0 (374.9) and lowest at v = 32 (146.3), the reverse; the repeat gives 335.0 vs 432.1, still not decreasing as required (0 < 1 < 8 < 32).
     - Row 3 (flat and control did not move): the control moved 101.2 → 427.7 → 1,515.5 MiB, a ratio of 15.0.
     - Row 4 (no plateau): v = 0 is flat.
     - BIND-1 (both flat): L rises 80.7 MiB.
     - BIND-3 (S also increases): H_S is not monotone (258.9 → 240.2).
     - BIND-4 (did not bind): it bound at 100 %.
     - BIND-2: see part 3.
5. **Observed vs. inferred.** The verdict rests on observed figures only: the R5 table and the rule thresholds. The inferred statements are the cause of the filed-phase load heap (2a), the G1 rounding (2d), and the S32 count (2c, unexplained). None changes the matched rows.
6. **Deviations and gaps.**
   - Deviations and defects: E1, D1, D2, H1, H2, and the expiry deviation (§3).
   - The filed design's heap statistic cannot separate "queue" from "write load" at v ≥ 1 under 20,000 writes/s. R5's frozen statistic (`GC.heap_info` after the histogram) has about 50 MiB of noise against a 64 MiB L effect.
   - The networking-pool gauges went negative.
   - Only `MutationStage` was tested, not `ReadStage` or `Native-Transport-Requests` (S1).
7. **Core question.**
   - **Unit.** The pool size bounds how many tasks run (line 165 shrinks active 32 → 4 lazily), not the heap of queued work, which is 125 MiB at every n while a byte cap holds 16 / 64 MiB.
   - **Node.** The pool size does not cap the stage's queue: v = 0 holds 135 k queued mutations and 375–428 MiB of heap, bounded only by the receive reserve (16 / 128 / 512 MiB → 101 / 428 / 1,516 MiB).
   - **"Running tasks × per-task bytes"** holds on one path. With the pool binding, large internode mutations (> 64 KiB) are on heap only while running (`Mutation` = v; live +5.5 → +70.2 MiB from v = 1 to 128), and their queue waits off heap. On that path a lower pool size means less heap but not less memory: direct +222–240 MiB, flat. Small mutations (32 KiB) hold a flat ≈ 240–270 MiB, set by the reserve.
   - The frozen rules match none of the decisive rows, so the cluster tier is not confirmed.

**Conclusion (one line):** unit B2g rows 1, 3 and 5 — **Confirmed** (does not cap); cluster R5 **BIND-5 — Not confirmed** (the filed phases alone would also be Not confirmed, via the drift row).

## 5. Self-check of run 1 — AI

### 5.1 Check of run 1's conclusion

[`run1/selfcheck.py`](maximumPoolSize-takeTaskPermit-workPermits--autonomous/run1/selfcheck.py) is an independent re-parse. It reads the per-test log (not the ant log), the raw histogram files (live bytes, not `GC.heap_info`), B's resize lines from `system.log`, tpstats, the cqlsh output in `session.log`, and the stress outputs. It does not read `summary.txt`, `analysis.json` or `samples-heap.jsonl`. Output [`run1/selfcheck.txt`](maximumPoolSize-takeTaskPermit-workPermits--autonomous/run1/selfcheck.txt): **35 ok, 6 FAIL.** Each FAIL is a recorded miss:
- Phase 4's n × 1 MiB band, in each of the three reps;
- filed row 1's "H(32), H(8) < 100" on live bytes (110.9, 258.0);
- the drift tolerance on live bytes (110.9 vs 224.1);
- S32's `Mutation` ≈ Pending + v (3,489 vs 4,215).

It computes the R5 row as BIND-5 on live bytes too.

| Part | Holds? | Note (file re-read) |
|---|---|---|
| 1. Validity | yes | The resize sequence on B is exactly 8, 32, 1, 32, 0, 32, (0, 32) × 4, then (1, 512), (8, 512), (512), (128, 512) twice (v = 32 is the default and logs nothing). Active = v at 8/8 samples in all eight R5 phases. Every stress run had 0 errors. |
| 2. Readings | yes | The `GC.heap_info` vs live-bytes gap is re-seen in the histogram totals. The S32 count is re-read (3,489). |
| 3. Matched row | yes | The unit records rebuilt from the per-test log agree to 0.0 MiB. BIND-5 holds on both statistics. H2 is noted: the filed lifetime-1 baseline histogram was overwritten, and the later file differs by 3.4 MiB. |
| 4. Excluded rows | yes | Not decreasing: 403.5 > 294.3 > 258.0 > 110.9 on live bytes, the reverse of the Refuted row. Control ratio on live bytes 18.0. L `Mutation` = v exactly. |
| 5. Observed vs. inferred | yes | The verdict uses no inferred statement. |
| 6. Deviations and gaps | yes | E1, D1, D2, H1, H2, the expiry deviation and the negative gauges are recorded. |
| 7. Core question | yes | It follows B1 and R5: concurrency is capped (line 165 shown), the queue is not capped, and the per-running-task component is shown on the large-message path only, but not under the frozen thresholds. |

### 5.2 Run 2?

**No** — decided 2026-10-21. A repeat with the same frozen statistics would not settle BIND-5 against BIND-2: the noise of `GC.heap_info` is the issue, not the run. The fix belongs in stage 3 (recommendations in §8). The unit verdict rests on observed, repeated readings.

## 6. Run 2 — fresh AI session (optional)

Not done (§5.2); §7 left out.

## 8. Verdict — AI

**Stage-3 estimate:** negative.

**Claim tested (B1):** "Lowering an SEP executor's maximum pool size (the value compared at `SEPExecutor.java:165`; `concurrent_writes`/`MutationStage` in the cluster tier) limits the number of concurrently running tasks but does **not** lower the heap held by that stage … refuted if retained heap decreases monotonically with the pool size at equal offered load and equal queued work." "Confirmed" below means this claim held.

| Tier | Verdict | Effect on the constraint | Basis | Date |
|---|---|---|---|---|
| Unit | **Confirmed** — B2g rows 1, 3, 5. Queued heap 125.2–125.3 MiB at n = 1 · 4 · 32 · 128 in 3 reps. Line 165: active 32 > max 4 after the shrink, then 4. Byte cap 16.0 / 64.1 MiB. (R4 Phase 4: 2.0 × n MiB per running task, band missed, row "invalid for R5's purpose".) | does not cap | run 1 + self-check | 2026-10-21 |
| Cluster | **Not confirmed** — R5 BIND-5. The pool bound at every v. S heap flat (238.8–258.9 MiB). L heap 5.5 · 57.4 · 53.9 · 86.2 MiB (`GC.heap_info`), live 5.5 · 9.4 · 21.9 · 70.2 MiB, `Mutation` = v. The filed phases would give R3's drift row. | undetermined | run 1 + self-check | 2026-10-21 |

**Positive control:**
- **Unit:** the byte cap held 16.0 / 64.1 MiB on the same tasks.
- **Cluster:** the receive reserve 16 / 128 / 512 MiB at v = 0 moved H to 101.2 / 427.7 / 1,515.5 MiB (live 85.2 / 411.7 / 1,531.5) and P to 26,886 / 134,432 / 503,162.

**"Running tasks × per-task bytes" (the `concurrent_compactors` pattern):** tested, with the pool binding (Active = v) at a reserve-bound backlog of 132 MiB.
- **Small internode mutations:** not observed. Heap is flat across v = 1 · 8 · 32 · 128 because the queue holds them on heap.
- **Large internode mutations (> 64 KiB):** observed. Only running tasks hold them on heap (`Mutation` = v; about 2 × 256 KiB each, value plus cached serialization). The queue waits in direct frame buffers (+222–240 MiB, flat). On that path a lower pool size means less heap, but the same total memory, which the receive reserve bounds.
- The frozen rows did not reach BIND-2, so this is a finding, not a verdict.

**Findings beyond the claim:**
1. A node restart with `commitlog_sync: group` hung in `SystemKeyspaceMigrator41`, and group commit delayed schema propagation by minutes on a fresh pair (D2). Worth an upstream look.
2. The 5.0 internode mutation deadline is capped by `native_transport_timeout` (`Dispatcher.java:238-245, 270`), so raising `write_request_timeout` alone does not keep queued mutations alive.
3. Networking `BufferPool` `UsedSize`/`OverflowSize` gauges went negative.
4. testsome's `maxmemory="1024m"` overrides `-Xmx` in `test.jvm.args`.

**Recommendations for stage 3 (not applied):**
- R5's statistic should be the histogram's live bytes, with a tolerance (e.g. ±10 MiB).
- `native_transport_timeout` should be raised with `write_request_timeout`.
- The filed phases should stop the load (or subtract memtable size) before sampling at v ≥ 1.
- `ReadStage` and `Native-Transport-Requests` should get their own designs.

**Feedback filed:** the case file's section D updated 2026-10-21, with the dated amendments R1–R5 and runbook fixes D1–D2 above it (not committed). The new sha256 of the whole case file after section D is `c5ab748a9bcd21985bc419cf7c0e5d3d516407123932d941e952d630b9dc6f11`. It is not a new frozen version; it goes in `_INDEX.md` §4 when the main session integrates.
