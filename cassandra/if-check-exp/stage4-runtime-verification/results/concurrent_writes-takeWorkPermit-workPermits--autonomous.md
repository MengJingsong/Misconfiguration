# concurrent_writes-takeWorkPermit-workPermits--autonomous — stage-4 results  <!-- file: results/concurrent_writes-takeWorkPermit-workPermits--autonomous.md; the stem ends in --guided or --autonomous -->
> **Case:** [`concurrent_writes-takeWorkPermit-workPermits--autonomous`](../../stage3-ai-deep-read/cases/concurrent_writes-takeWorkPermit-workPermits--autonomous.md)
>
> **Status:** **Closed 2026-10-21 — unit Confirmed, cluster Confirmed — does not cap** (estimate negative, matched). Two sub-predictions missed on the cluster tier: each queued mutation holds about 2 × its value (887.5 MiB of queue heap instead of ≈ 480 MiB), and the PC throughput drop is only 1.4 %. No run 2.
> 
> **Outcome class:** true negative — stage-3 estimate vs the stage-4 effect on the constraint
>
> **Agent:** autonomous (the suffix of the case-file stem). For an autonomous
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
| **Case-file version** | Autonomous file. As filed (untracked, 2026-10-21): sha256 `559d1f85512a403b6cff0ee56fbf8e867ae4f9f4e9121416f2578a00d26076f8`. After the step-0 audit amendments R1–R6: `af2af2e5a979c7073fcb6df22cabb0900b032f28294fc8928659517b6d59c454` (the audit freeze). After runbook fixes D1–D2 (found by the cluster instrument check, before any run-1 cluster reading; B1 and B2f–B3g unchanged): **`12fb743b3319bcccb80eb317b87fbae1a1162f9b22f69fd2e087b7a11ba896b2`, the version run 1 used** (the unit tier ran on `af2af2e5…`; D1–D2 touch only B3). The file is not committed; the repo HEAD was `1f5fda1`. |
| **Harness** | [`harness/concurrent_writes-takeWorkPermit-workPermits--autonomous/`](../harness/concurrent_writes-takeWorkPermit-workPermits--autonomous/README.md), written 2026-10-21 (not committed): `SEPQueueHeapProbeTest.java` (the filed B2a test verbatim plus one supplementary method), `unit-run.sh`, `unit-analyze.py` (B2), `make-node-yaml.sh`, `Jmx.java`, `cluster-run.py` (B3), `selfcheck.py`. **Instrument checks (not readings):** `javac` of the test against the clone; unit shakedown1 (M = 400; found H1); cluster shakedown2 (found H2) and shakedown3 (20–30 s arms; found D1). md5 of the node copy in `~/stage4-harness-run/sep.md5`, equal to the repo files. |
| **Tiers and values** | Unit (B2): `maximumPoolSize` N = 0 · 2 · 32 · 128 with M = 4000 (twice) and 8000 tasks of 64 KiB; positive control `ResourceLimits.Concurrent` 16 · 64 MiB at N = 2 · 128. Cluster (B3): R0 (`MutationStage` pool 0 at runtime for 120 s, then 32), R32 · R2 · R128 (`concurrent_writes` in the yaml, 400 writes/s of 64 KiB for 120 s), PC0 · PC (unthrottled 60 s, receive queue 0B, per-IP in-flight 256 MiB vs 4 MiB). |
| **Audit bottom line** | **Ready after amendments** — 2026-10-21 |

### 1.1 Design audit

The requirements are in the README, "Step 0 — the design audit". One row per
line of each group; cite the case-file section checked.

| Group | Check | Rating (Met / Partly / Not met) | Note (section checked) |
|---|---|---|---|
| A. Core question | constrained quantity is memory or disk bytes | Met | B1/A2: heap held by pending writes; the knob is a count of running tasks, and the file claims it does not bound that heap. |
| A. Core question | knob varied, ≥ 3 values incl. default — or another approach, with the reason | Met | B2b N = 0 · 2 · 32 · 128; B3b 0 (runtime) · 2 · 32 · 128. |
| A. Core question | real resource measured, not only the counter (gap named) | Met | B2d live heap after GC; B3d post-GC heap with `jcmd`, plus tpstats and `RequestsSize`. The queue's own bytes are inferred (heap − baseline), and B3d names that gap. |
| A. Core question | usage driven to the limit and past it | Partly | Unit: M ≫ N everywhere. Cluster: only R0 drives past the limit. In R2/R32/R128 the queue "normally drains" (B3b), so the knob may never bind there; recorded as a limitation, not amended (it is the file's design). |
| A. Core question | positive control (negative-estimate file) | Partly | Unit: a byte cap (`ResourceLimits.Concurrent`) on the same workload and the same heap instrument (Met). Cluster: PC moves only the in-flight counter, not the heap. The heap instrument's sensitivity on the cluster comes from R0 itself (growth with Pending, release at the drain) and from the unit control. R3 adds a PC reference arm. |
| B. Logic | each step says what it establishes | Met | B2e/B3e, B2h/B3h. |
| B. Logic | prediction stated in numbers or a clear relation | Met | B2f exact active/pending and ≈ 250/500 MiB ± 10 %; B3f ≈ 7700 pending, ≈ 480 MiB ± 30 %, within 20 % across N. |
| B. Logic | every plausible outcome has a conclusions row with its evidence | Partly | Missing: unit repeat disagreement; R0 growth that stays below the 256 MiB cap. **Added** (R5, R6). Ambiguous terms ("grows with N", "rises with N", "doubles", which heap statistic) **defined** (R4, R6). |
| B. Logic | confirmation needs ceiling-follows-knob and direct disallow evidence | Met | Unit: line 196's refusal is observed per N (`mei_inline=false`, pending +1). Cluster: Active = 0 with Pending growing at pool 0, plus the node's own resize log. |
| B. Logic | alternative explanations and their controls | Partly | Memtable growth (B3h tablestats), GC noise (repeat), carry-over (fresh pool / fresh lifetime, R2). Not controlled: per-worker thread-local buffers that scale with N (the `concurrent_compactors` "tasks × per-task bytes" path) are far below the 20 % tolerance. Left for stage 3. |
| C. Specific | a human can follow it from the intro and the prediction/conclusions | Met | Header, A3, B1. |
| C. Specific | an AI can run the runbook without re-deriving the code path | Met | B2a is a complete test; B3 commands are given. |
| C. Specific | knob, values, workload, commands, observables, sampling, stop conditions exact | Partly | The stress command runs a 50,000-write unthrottled warm-up (R1). R32 follows R0 in R0's lifetime (R2). The PC has no reference (R3). The heap statistic is undefined (R4). |
| D. Runnable | harness and environment prerequisites exist or are listed | Met | Paths name another user's clone (`/users/jason92/cassandra-s3`, `$LOCAL/c509`) and 127.0.0.1. Run on `~/cassandra-sep` and 127.0.0.11 (E1). |
| D. Runnable | workload arithmetic reaches the limit (data, time, disk, memory) | Met | R0 ≈ 64 writes/s × 110 s ≈ 7000 queued; 3 GiB per steady run; 2 GiB heap. |
| D. Runnable | load-bearing citations spot-checked against the pinned clone | Met | Checked: `SEPExecutor.java:57-60, 68, 102-106, 110-117, 121-143, 188-200, 217-240, 335-350, 368-396`, `Stage.java:46, 229-235, 275-278`, `SharedExecutorPool.java:146-151, 153-167`, `Config.java:180`, `DatabaseDescriptor.java:565, 649-657, 2415-2427`, `StorageService.java:2397-2403`, `SetConcurrency.java:42-52`, `StorageProxy.java:906, 1569, 1646, 1676, 2623-2657, 2822-2828`, `Dispatcher.java:258-261`, `CBUtil.java:443-450`, `CQLMessageHandler.java:497-507`, `jvm-server.options:123`. All as cited, except one trace note (S1). |

| # | Recommendation | Applied? (amendment date and commit, or "left for stage 3") | Why |
|---|---|---|---|
| R1 | Add `no-warmup` to the stress command | Applied 2026-10-21 (amendment block, B3c) | `StressAction.java:105-110`: 50,000 unthrottled 64 KiB writes (3.05 GiB) before every run, outside the throttle and over R0's t = 10 s |
| R2 | One fresh lifetime per steady run, after `TRUNCATE` + `clearsnapshot`; R32 not in R0's lifetime | Applied 2026-10-21 | R0's drained mutations and memtables would inflate R32's heap and bias the across-N comparison |
| R3 | PC0 reference arm (PC without the per-IP cap) | Applied 2026-10-21 | B3f's "compared with ≈ 8 MiB" and "throughput drop" had no reference on the PC workload |
| R4 | Define the heap and Pending statistics and "rises with N" | Applied 2026-10-21 | a 3-point monotone order happens by noise one time in six |
| R5 | B3g row: R0 growth below 256 MiB → Not confirmed | Applied 2026-10-21 | outcome without a row |
| R6 | Run B2e step 2 twice; a B2g row for repeat disagreement; define "grows", "doubles" | Applied 2026-10-21 | B2h's repeat was not in the procedure and had no row |
| S1 | A3 item 2 is incomplete: line 196 also returns false when no task is queued (`taskPermits == 0`), whatever `takeTaskPermit` is. So `maybeExecuteImmediately` runs a task inline only when a task is already queued and a permit is free; on an idle stage it always enqueues. | Left for stage 3 (section D); checked by a supplementary unit test | not load-bearing: B2f's caller-runs check is made with every permit taken |
| S2 | Per-running-task memory that scales with N (e.g. the thread-local `DataOutputBuffer` scratch buffer of each worker) is not measured; the `concurrent_compactors` pattern (usage = tasks × per-task bytes) is untested here | Left for stage 3 | needs a workload where N binds under real load (R2/R32/R128 never reached N) |

**Agreement criteria** — only if run 2 is chosen; not filled (no run 2).

## 2. Environment

| Field | Run 1 | Run 2 (fresh AI session, if done) |
|---|---|---|
| Date | 2026-10-21, EDT: unit shakedown 11:49; unit run 11:50:47–11:52:21; cluster shakedowns 11:53–12:28; cluster run 12:30:14–12:53:03 | not done |
| Node (CloudLab name and type) | `pc07` = `node0.jason92-320876.misconfiguration-pg0.cloudlab.umass.edu` (40 cores, 251 GiB); the session ran on it directly. **Another stage-4 session shared this host** (its own clone `~/cassandra-mhp`, other loopback addresses and ports) and so its CPU and disk; no other `java` process was running when this run ended. **Environment deviation E1:** the node used 127.0.0.11 (listen, rpc, seed) and JMX 7211 instead of B3a's 127.0.0.1 and 7199, and the clone `~/cassandra-sep` instead of B2a/B3a's `$LOCAL/c509`; the design is unchanged. | — |
| OS and kernel (`uname -r`) | Ubuntu 22.04.2 LTS, `5.15.0-187-generic` | — |
| JDK (`java -version`) | openjdk 11.0.32.1 (2026-08-18) | — |
| Ant (`ant -version`) | 1.10.12 | — |
| Local `cassandra-src` clone commit | `~/cassandra-sep` (a copy of `~/cassandra-run1`) at `cassandra-5.0.9` (`b5f2a54210d541339c2e7c17a794195cac0e67c2`), built with `ant build-test`. It also holds untracked harness tests from other cases (they compiled), and now `SEPQueueHeapProbeTest.java`. | — |
| Case-file commit / harness commit | case file untracked (HEAD `1f5fda1`), sha256 `12fb743b…` for the cluster run, `af2af2e5…` for the unit run; harness not committed (md5 in `~/stage4-harness-run/sep.md5`) | — |
| Storage for node data | `~/stage4-sep/node1/` on local `/dev/sda3` (ext, RAID, spinning), 56 GB free at the start; data dirs removed at the end (logs kept, 16 MB) | — |
| Full logs (path, outside the repo) | `pc07:~/stage4-logs/sep/run1/` (`unit/`: ant logs, per-test logs, GC logs, `.probe`; `cluster/`: `session.log`, samplers, `stress-*.out/.log`, `system-/debug-/gc-<lifetime>.log`, class histograms, `phases.json`); shakedowns `~/stage4-logs/sep/shakedown{1,2,3}/` | — |

## 3. Runbook defects

| # | Run | Step (§9b–§9e) | Problem | Fix | Decision (date) | Case-file commit with the fix |
|---|---|---|---|---|---|---|
| H1 | unit shakedown1 (instrument check) | B2e step 4 | The test JVM routes `System.out` through a logger, one printf argument per line (`SubstituteLogger.java:222`), so `grep PROBE` of the junit XML finds nothing. | `unit-run.sh` rebuilds each `PROBE` line by joining the main thread's `SubstituteLogger` fragments in the ant log. The self-check rebuilds them independently from the per-test log. Test unchanged. | 2026-10-21, harness only | — |
| H2 | cluster shakedown2 (instrument check) | B3c | The filed stress command's `-col n=FIXED(1) size=FIXED(65536)` is a `/bin/sh` syntax error when run through a shell (`(` unexpected), so no write ran. | The arguments are quoted (`'n=FIXED(1)' 'size=FIXED(65536)'`); the command is otherwise as filed plus R1. | 2026-10-21, harness only | — |
| H3 | cluster shakedown3 (instrument check) | harness | The node-copy `make-node-yaml.sh` lost its execute bit (HANDOFF lesson). | Called with `bash`. | 2026-10-21 | — |
| D1 | cluster shakedown3 (instrument check, before run 1) | B3b PC, R3 | The per-IP cap could not bind. A CQL connection takes bytes from its own 1 MiB receive queue first (`Config.java:302`) and only the excess from the per-IP/global reserves (`AbstractMessageHandler.java:411-436`). `RequestsSize` reads only the global reserve (`ClientResourceLimits.java:74-76`). Stress's 8 connections (`SettingsMode.java:139`) × 1 MiB absorb its 128 × 64 KiB = 8 MiB, so `RequestsSize` read 0.07 MiB in PC0 and PC alike. Derivable from source; the closed `native_transport_max_concurrent_connections` case found the same. | PC and PC0 set `native_transport_receive_queue_capacity: 0B`; PC keeps per-IP 4 MiB. B3f/B3g unchanged. The cluster tier ran from its beginning with the fix. | 2026-10-21, dated runbook fix D1 in the case file | none (not committed) |
| D2 | cluster shakedown3 (instrument check, before run 1) | B3d/B3h | R0's first 10 s are unthrottled writes at pool 32, which fill the memtable (about 100 MiB) before the pool goes to 0, so "heap − baseline" includes it. | Read the queue's heap as (heap after GC − memtable data size) minus the same at the baseline, which is B3h's memtable separation. Raw rise reported too. B3f numbers unchanged. | 2026-10-21, dated runbook fix D2 | none |

## 4. Run 1

**Scope:** unit tier B2 (N = 0 · 2 · 32 · 128 at M = 4000 twice and at M = 8000, the byte-cap control, one supplementary idle-executor test), cluster tier B3 (R0, R32, R2, R128, PC0, PC, one lifetime each). **Command log:** [`concurrent_writes-takeWorkPermit-workPermits--autonomous/run1/`](concurrent_writes-takeWorkPermit-workPermits--autonomous/run1/) (`chain.log`, `unit/summary.txt` with every `PROBE` line and the 146 `EXPECTED` lines, `cluster/summary.txt`, `phases.json`, samplers, `stress-results.txt`, `concurrency-excerpt.txt`, `histo-excerpt.txt`, `selfcheck.py`, `selfcheck.txt`).

### 4.1 Readings

**Unit tier** (`run1/unit/summary.txt`; 3 × `Tests run: 3, Failures: 0, Errors: 0`; `unit-analyze`: 146 yes, 0 NO)

| Test or assertion | Result | Evidence (file) |
|---|---|---|
| Claim arm, M = 4000 (rep1 / rep2): active, pending, maxPool | N = 0 · 2 · 32 · 128: active 0 · 2 · 32 · 128 = min(N, M); pending 4001 · 3999 · 3969 · 3873 = M − N + 1; maxPool = N; identical in both reps | `unit/rep1.probe`, `rep2.probe` |
| Line 196 on the caller-runs path, every N and M | `mei_inline=false`, pending + 1: the task was queued, not run | same |
| Live heap delta, M = 4000 | rep1 249.8 · 250.3 · 250.1 · 250.2 MiB; rep2 249.8 · 250.2 · 250.0 · 250.2 MiB; payload 250.0 MiB; max/min across N 1.002 | same |
| Live heap delta, M = 8000 | 499.9 · 500.6 · 500.5 · 500.7 MiB (payload 500.0); ratio to M = 4000 2.000–2.002 | `unit/m8000.probe` |
| Positive control (byte cap) | 16 MiB: 256 submitted, liveDelta 15.3–16.0 MiB; 64 MiB: 1024 submitted, 63.6–64.4 MiB; at N = 2 and 128, all three runs | all `.probe` |
| Supplementary: idle executor (N = 2, nothing queued) | 5/5 calls of `maybeExecuteImmediately` ran on a worker thread, none inline (S1) | `unit/summary.txt` (`SUPPL` lines) |

**Cluster tier** (`run1/cluster/summary.txt`, `samples-*.csv`, `phases.json`; run script 25 yes / 2 NO)

| Capacity value | Run | Observable (§9d) | Reading | Evidence (file) |
|---|---|---|---|---|
| 32 → 0 → 32 (runtime) | R0 | pool size | `getconcurrency` 32, 0, 32; the node logs "Resized MutationStage maximum pool size from 32 to 0" 11.6 s and "from 0 to 32" 131.3 s after stress start | `concurrency-excerpt.txt` |
| 0 | R0 | `MutationStage` Active / Pending | Active 0 at all 23 samples after the first 5 s; Pending 172 → 7296, never falling, at 63.7/s while stress ran | `samples-tp.csv` |
| 0 | R0 | heap after GC (queue heap, D2) | baseline 86.4 MiB; heap 357.8 → 1121.9 MB (+≈ 124 MB per 15 s); memtable flat at 96.01 MiB; queue heap 887.5 MiB at Pending 6912 (131.5 KiB per queued mutation; regression 129.5 KiB); raw rise 983.6 MiB | `samples-heap.csv`, `samples-tp.csv` |
| 0 | R0 | `RequestsSize` | max 0.070 MiB over 120 one-second samples | `samples-jmx-1.csv` |
| 0 | R0 | supplementary class histogram at +126 s | 7296 `Mutation`, 7296 `Mutation$CachedSerialization`, 7296 `PartitionUpdate`; `byte[]` 1038.4 MiB against 20.0 MiB at the baseline | `histo-excerpt.txt` |
| 0 | R0 | stress | 25,336 writes, 7,424 errors (WriteTimeout), 209 op/s; no OOM (JVM heap peak 1150 MiB of 2048) | `stress-results.txt`, `samples-jmx-1.csv` |
| 32 (restored) | R0 drain | Pending, completed, dropped | Pending 0 at the first sample (1.2 s after the restore); completed +14,592 = 2 × 7296; dropped `MUTATION_REQ` +7296: every queued mutation expired and was re-run as a hint (A3 item 5); heap after GC 133.2 MiB with memtable 35.6 MiB | `samples-tp.csv`, `samples-heap.csv` |
| 2 / 32 / 128 (yaml) | R2 / R32 / R128 | heap after GC (mean of 8 samples while stress ran) | 240.8 / 241.8 / 237.9 MiB (max 311.3 / 312.8 / 313.1); max/min 1.016 | `samples-heap.csv` |
| 2 / 32 / 128 | R2 / R32 / R128 | Active / Pending max | 1 / 1 / 1 and 1 / 0 / 0: the limit was never reached at 400 writes/s | `samples-tp.csv` |
| 2 / 32 / 128 | R2 / R32 / R128 | stress | 400 / 398 / 399 op/s, 48,129 writes, 0 errors each | `stress-results.txt` |
| per-IP 256 MiB, receive queue 0B | PC0 | `RequestsSize`, op rate | max 8.01 MiB, mean 7.02 MiB; 1,123 op/s (2,176 timeouts) | `samples-jmx-5.csv`, `stress-results.txt` |
| per-IP 4 MiB, receive queue 0B | PC | `RequestsSize`, op rate | max 3.88 MiB, mean 3.24 MiB; 1,107 op/s (1,920 timeouts) | `samples-jmx-6.csv`, `stress-results.txt` |

### 4.2 Conclusion and logic

1. **Validity.**
   - **Unit.** The unit tier ran every N at both M, twice at M = 4000, with fresh pools; maxPool was read back as N [observed: `unit/*.probe`]. Active reached min(N, M) and every later task was queued, so the limit was reached and exceeded by M − N tasks [observed].
   - **Cluster, R0.** The pool was 0 for 119.7 s by the node's own log, and Active stayed 0 [observed: `concurrency-excerpt.txt`, `samples-tp.csv`].
   - **Cluster, yaml and JVM.** Each steady run's `concurrent_writes` was read back with `getconcurrency` (2, 32, 128). Every lifetime ran with `-Xmx2G` and G1 [observed: `concurrency-excerpt.txt`, `summary.txt` `jvm:` lines].
   - **Cluster, stress.** The stress command was the filed one plus R1 (`no-warmup`) and the H2 quoting [observed: `session.log`].
   - Valid. The limit was reached on the cluster only in R0; in R2/R32/R128 Active stayed ≤ 1 (see part 6).
2. **Readings.**
   - (a) Each queued mutation holds 131.5 KiB of heap, about 2.05 × its 64 KiB value [observed: `samples-heap.csv` / `samples-tp.csv`]. The class histogram shows one `Mutation$CachedSerialization` per queued `Mutation` [observed: `histo-excerpt.txt`]. So each mutation keeps its decoded value and a serialized copy. That copy is made when the coordinator checks the size: `SingleTableUpdatesCollector.java:112` → `Mutation.validateSize` → `serializedSize`, which caches a serialization below `CACHEABLE_MUTATION_SIZE_LIMIT` (`Mutation.java:451-456`) [inferred: source plus histogram counts].
   - (b) The first heap sample of the pool-0 window (0.9 s in) reads high (237 MiB of queue heap at Pending 172) [observed]. That is likely garbage or memtable bytes not yet in the data-size figure from the unthrottled first 10 s [inferred]. The later samples are linear.
   - (c) PC's op rate is only 1.4 % below PC0's: the node, not the client, is the bottleneck at this rate [inferred].
3. **Matched rows.**
   - **Unit, B2g row 1:** "active = min(N, M), pending = M − N, liveDelta ≈ M × 64 KiB for every N, and the control's liveDelta tracks its cap". Pending is M − N + 1 including the caller-runs probe, as B2f states. liveDelta is 249.8–250.3 MiB at M = 4000 and 499.9–500.7 at 8000 for every N. The control reads 15.3–16.0 MiB at 16 MiB and 63.6–64.4 MiB at 64 MiB.
   - **Cluster, B3g row 1:** "R0: Pending grows and heap grows ≈ Pending × 64 KiB beyond 256 MiB. R2/R32/R128 heaps are not ordered as smaller N gives less heap. PC clamps RequestsSize to ≤ 4 MiB".
     - Pending grew to 7296 and the queue heap to 887.5 MiB, beyond 256 MiB. It grows linearly with Pending, but at 2.05 × 64 KiB rather than ≈ 1 × (sub-prediction missed, reading 2a).
     - R2/R32/R128 read 240.8 / 241.8 / 237.9 MiB, not ordered.
     - PC holds `RequestsSize` at 3.88 MiB against 8.01 MiB in PC0.
4. **Excluded rows.**
   - **Unit:**
     - "liveDelta grows with N, or pending capped": max/min is 1.002 and pending = M − N + 1 at M = 4000 and 8000.
     - "`mei_inline=true` while active = N": false in all 12 claim rows and all 12 control rows.
     - "active < N after 5 s, or control does not follow": active = min(N, M) everywhere; the control moved 4×.
     - "liveDelta does not double": the ratio is 2.000–2.002.
     - R6 repeat row: the reps differ by ≤ 0.1 MiB.
   - **Cluster:**
     - **Refuted** "heap rises with N, or R0 heap flat while Pending grows": the heaps are flat across N (1.016), and the R0 heap rose 887.5 MiB with Pending.
     - **Refuted** "R0 Pending capped or writes rejected at enqueue": Pending never fell, and grew at the arrival rate (63.7/s) until stress ended.
     - "R0 Pending never grows, or PC does not clamp": both happened.
     - R5 "growth below 256 MiB": 887.5 MiB.
     - "OOM in R0": none (peak 1150 MiB).
   - No Refuted row fits.
5. **Observed vs. inferred.** The inferred statements are:
   - the cause of the 2 × per-mutation heap (the cached serialization; the histogram counts are observed, the code path is read from source);
   - the first-sample offset (2b);
   - the bottleneck behind PC's small throughput drop (2c).
   
   The matched rows rest only on observed readings: the per-sample heap and Pending, the counts and the `RequestsSize` samples.
6. **Deviations and gaps.**
   - Environment and defects: E1 (address, ports, clone; shared host). H1–H3 were harness fixes. D1 (PC receive queue 0B) and D2 (memtable-separated queue heap) were dated runbook fixes before the cluster run.
   - **Missed sub-predictions:**
     - B3f "heap rises by ≈ Pending × 65 KiB ≈ 480 MiB (±30 %)": read 887.5 MiB, 131.5 KiB per mutation. The error is in the direction of more uncapped heap, so it strengthens the claim rather than weakening it.
     - B3f's PC "throughput drop": 1.4 %, which is lower as required but slight.
   - **Gap:** in R2/R32/R128 the 400/s workload never brought Active above 1. The knob did not bind there, so those runs show only that heap is the same whatever N, not what happens when N binds under load. A per-running-task memory that scales with N (S2) is therefore untested. The cluster's positive control moved the in-flight counter, not the heap. The heap instrument's sensitivity is shown by R0's own growth and drain and by the unit tier's byte cap.
7. **Core question.** Usage does not follow `concurrent_writes`. In the unit tier the heap held by M tasks is M × 64 KiB at every pool size, while a byte cap on the same workload holds it at the cap [part 3]. On the node, a pool size of 0 (the smallest possible limit) let the heap grow by 887.5 MiB with 7296 queued mutations and no bound or rejection, far past the 256 MiB in-flight cap. The in-flight counter itself read 0.07 MiB [parts 3, 4]. A lower pool size gives more heap, not less. Line 196 caps only how many mutations run at once.

**Conclusion (one line):** unit B2g row 1, cluster B3g row 1 — **Confirmed** (claim: `concurrent_writes` does not cap the memory held by pending writes). Two sub-predictions missed: the queue heap is about 2 × Pending × 64 KiB, and PC's throughput drop is 1.4 %.

## 5. Self-check of run 1 — AI

### 5.1 Check of run 1's conclusion

[`run1/selfcheck.py`](concurrent_writes-takeWorkPermit-workPermits--autonomous/run1/selfcheck.py) is an independent script. It does not read `summary.txt`, `unit-analyze`'s output or `analysis.json`.
- **Unit:** it rebuilds the unit records from the test JVM's own per-test log, a different file and format from the ant log the run script used. That log is appended by every run in the clone, so it takes each rep's last 8 records.
- **Cluster:** it re-reads the samplers, the stress outputs, the node's `system.log` (the resize lines, used as the pool-0 window instead of the script's timestamps), the `getconcurrency` outputs and the class histograms. It uses `phases.json` only for the time windows.

Output [`run1/selfcheck.txt`](concurrent_writes-takeWorkPermit-workPermits--autonomous/run1/selfcheck.txt): **89 ok, 1 FAIL**. The FAIL is exactly the missed sub-prediction (131.5 KiB per queued mutation against 65 KiB ± 30 %). Its figures agree with the run script's for every observable.

| Part | Holds? (yes / no) | Note (file re-read) |
|---|---|---|
| 1. Validity | yes | `getconcurrency` sequence 32, 0, 32, 32, 2, 128, 32, 32 and the node's two resize lines re-read; all stress commands carry `no-warmup`; `-Xmx2G`/G1/7211 in all 6 lifetimes |
| 2. Readings | yes | per-mutation heap recomputed by regression (129.5 KiB) and at the last sample (131.5 KiB); histogram counts 7296 = 7296; first-sample offset seen in the per-sample list |
| 3. Matched row | yes | unit rows rebuilt from a different log agree to 0.1 MiB; R0 Pending series, queue heap, `RequestsSize`, steady means and PC/PC0 maxima recomputed |
| 4. Excluded rows | yes | Pending monotone, rate 63.7/s; steady means not ordered (1.016); no OOM line; drain counts 2 × 7296 / 7296 |
| 5. Observed vs. inferred | yes | the three inferences are not used by the matched rows |
| 6. Deviations and gaps | yes | E1, H1–H3, D1–D2, both missed sub-predictions and the "N never bound in R2/R32/R128" gap are recorded |
| 7. Core question | yes | follows B1: concurrency capped (Active ≤ N, line 196 refuses), heap not capped (flat in N; unbounded at N = 0), a byte cap binds where the knob does not |

### 5.2 Run 2?

**No** — decided 2026-10-21. The conclusion rests on observed readings, and the self-check settled every part from run 1's files with an independent parse. The result confirms the file's own negative estimate; it neither refutes the case nor confirms a bypass. The missed magnitude points the same way as the claim.

## 6. Run 2 — fresh AI session (optional)

Not done (§5.2); §7 left out.

## 8. Verdict — AI

Jingsong may overrule any verdict at any time; record an override here with its
date and reason.

**Stage-3 estimate:** negative (the file's Estimate line: line 196 checks a work permit, a concurrency slot; tasks that find none go into an unbounded queue on the heap).

**Claim tested:** B1 — "`concurrent_writes` (`MutationStage` maximum pool size) does **not** cap the memory held by pending writes. It caps only the number of mutations running at once (`activeTasks ≤ N`). Heap held by queued mutations keeps growing with the backlog, whatever N is, and is no lower for smaller N. With N = 0 at runtime it grows past the native-transport in-flight cap." "Confirmed" below means this claim held.

| Tier | Verdict (B2g / B3g row) | Effect on the constraint | Basis | Date |
|---|---|---|---|---|
| Unit | **Confirmed** — B2g row 1 (active = min(N, M), pending = M − N + 1, live heap 249.8–250.3 MiB at M = 4000 and 499.9–500.7 at 8000 for N = 0 · 2 · 32 · 128; line 196 queued the caller-runs task every time; the byte cap held 16 / 64 MiB) | does not cap | run 1 + self-check | 2026-10-21 |
| Cluster | **Confirmed** — B3g row 1 (pool 0: Pending 7296 with Active 0, queue heap 887.5 MiB, `RequestsSize` ≤ 0.07 MiB; pool 2 / 32 / 128: heap 240.8 / 241.8 / 237.9 MiB; PC 3.88 vs PC0 8.01 MiB). Sub-predictions missed: 2 × Pending × 64 KiB, not 1 ×; PC throughput drop 1.4 % | does not cap | run 1 + self-check | 2026-10-21 |

**Positive control:**
- **Unit:** `ResourceLimits.Concurrent` (the native in-flight limit's class) on the same tasks and heap instrument held the live heap at 15.3–16.0 MiB (16 MiB cap) and 63.6–64.4 MiB (64 MiB cap), against 250 MiB uncapped, at N = 2 and 128.
- **Cluster:** `native_transport_max_request_data_in_flight_per_ip` 4 MiB, with the receive queue at 0B (D1), held `RequestsSize` at ≤ 3.88 MiB against 8.01 MiB in PC0. It moved the in-flight counter, not the heap. On the cluster the heap instrument's sensitivity is R0's own growth (+887.5 MiB) and release at the drain.

**Findings beyond the claim (no §9a row):**
1. Each queued mutation holds about 2 × its value on the heap: the decoded value plus the serialization cached by the coordinator's size check (`Mutation.java:451-456`, `SingleTableUpdatesCollector.java:112`; the histogram shows 7296 `Mutation` and 7296 `Mutation$CachedSerialization`).
2. When the pool is restored, every queued mutation is past its deadline. Each is counted as dropped and re-run as a hint on the same stage (completed +2 × 7296, dropped +7296), so none is lost (A3 item 5).
3. Line 196 also refuses when nothing is queued, so `maybeExecuteImmediately` never runs inline on an idle stage (S1, supplementary unit test 5/5).
4. The per-connection receive queue (1 MiB × connections) absorbs the in-flight bytes before the per-IP limit sees them (D1), as in the `native_transport_max_concurrent_connections` case.

**Feedback filed:** the case file's section D updated 2026-10-21. Before that: the dated audit amendments R1–R6 and runbook fixes D1–D2 (only those blocks and section D changed; not committed). New sha256 of the whole case file after section D: `beb9abf09c1103ae11c8a45a9b83847b0bb3712ad269649316db994bc5fe6186` (not a new frozen version; recorded in `_INDEX.md` §4). `predicted-negative.md` §10: `SEPExecutor.java:196` marked verified, the other lines of that row kept.
