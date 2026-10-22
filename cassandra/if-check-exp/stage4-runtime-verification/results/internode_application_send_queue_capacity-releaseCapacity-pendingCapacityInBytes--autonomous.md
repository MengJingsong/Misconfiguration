# internode_application_send_queue_capacity-releaseCapacity-pendingCapacityInBytes--autonomous — stage-4 results  <!-- file: results/internode_application_send_queue_capacity-releaseCapacity-pendingCapacityInBytes--autonomous.md -->

> **Case:** [`internode_application_send_queue_capacity-releaseCapacity-pendingCapacityInBytes--autonomous`](../../stage3-ai-deep-read/cases/internode_application_send_queue_capacity-releaseCapacity-pendingCapacityInBytes--autonomous.md)
>
> **Status:** **Closed 2026-10-21. Unit: Confirmed (B2g row 1). Cluster: B3g row 4 by its trigger, partial (refines the claim).** On the node, the accounting and the release at `:449` are confirmed: the plateau is within one message of C + reserve at C = 4 · 64 · 256 MiB and at the positive control, the reserve held is exactly pending − C, and it returns to 0. The heap clause as worded is refuted: k = ΔH / plateau = 11.6 · 3.91 · 3.44 varies 3.4×. Heap does follow C, but additively, not in proportion: a constant 3.27 heap bytes per counted byte plus a C-independent offset of about 42 MiB. **Effect: caps.** No run 2. Audited 2026-10-21 (estimate positive). Run on `pc13`.
> 
> **Outcome class:** true positive — stage-3 estimate vs the stage-4 effect on the constraint
>
> **Agent:** autonomous. "§9a" below means each tier's predictions and conclusions table: B2f and B2g (unit), B3f and B3g
> (cluster); "§9b–§9e" means B2a–B2e or B3a–B3e; the case file's feedback section is its section D.

## 1. Before run 1 — design audit and freeze

| Field | Content |
|---|---|
| **Case-file version** | Autonomous file, untracked in the working tree (no commit holds it; not committed, per the session's instructions). sha256 as filed: `49e904a2b820d8ee83baa9a9cdab3ce66925a6c8d86cf9cd11045a4c6b83bec9`. **After the audit's amendments A1–A9, before any harness or reading: `658ca786eb99ac22c677789f4b233e81b74b06eef0cfafe941b27a3aba3f7f50`** (the frozen design). After runbook defect 2's dated amendment, which leaves B2f/B2g/B3f/B3g unchanged and restarted the unit tier: `b48dd16e50617e76ade68f25651d03f566c658111b9eb15bff33bdcfd6db3479`. The unit tier's counted run and the whole cluster tier ran against this version. The final sha256 after section D is in §8. |
| **Harness** | `harness/internode_application_send_queue_capacity-releaseCapacity-pendingCapacityInBytes--autonomous/`, written 2026-10-21 (step 1), not committed. The md5 of every file is identical in the repo and in `pc13:~/stage4-harness-run/sq2/` (`run1/harness-md5-*.txt`). Instrument checks: compile check, the mutant bytecode printed per mutant (`run1/unit/summary.txt`), and a cluster shakedown (`shake`: stress at 30,000/s, the beans resolve, the vt and histogram parsers work). Harness fixes are in its README and in §3. |
| **Environment deviation (recorded before the cluster tier)** | The file's own layout (A = 127.0.0.1, B = 127.0.0.2 on one host) is used, on `pc13`. Node data, commit logs, hints and caches are on a 40 GiB tmpfs `~/stage4-sq2/nodes`, not on `/local/$USER/s3`: `pc13` has no `/local`, and its disk is a spinning RAID volume (amendment A9). A, B and the stress client share the host's 40 cores. |
| **Tiers and values** | Unit (B2): U1 and U1-stress at C = 64 KiB · 1 MiB · 4 MiB (default), with R_e 256 KiB and R_g 1 MiB; U2 at C = 8 · 32 · 128 MiB plus the M = 0 control, reserves 1 MiB; U3 at C = 8 · 32 MiB; A2's mutants M1 and M2; each probe run three times. Cluster (B3): C = 4 MiB (default) · 64 MiB · 256 MiB with send reserves 1 MiB; the positive control (C 4 MiB, reserves 128 MiB); the negative control (C 64 MiB, B never stopped). |
| **Audit bottom line** | **Ready after amendments** — 2026-10-21 |

### 1.1 Design audit

Checked against the pinned clone `/proj/misconfiguration-PG0/git-repos/cassandra-src` (`git describe --tags` = `cassandra-5.0.9`) and the run clone
`pc13:~/cassandra-sq2` (`b5f2a54`). Re-read in context: `OutboundConnection.java` 115-175 (packing), 255-283 (`Connecting.isFailingToConnect`,
set only with a scheduled retry, `:277`), 300-520 (constructor, `enqueue`, `acquireCapacity`, **`releaseCapacity` 445-454**, `onOverloaded`,
`onExpired`, `onClosed`), 600-700 (`Delivery.run`), 735-800 (`EventLoopDelivery.doRun`), 1082-1110 (retry), 1500-1600 (close), 1740-1778
(test hooks); `ResourceLimits.java` 100-175, 237-290; `OutboundMessageQueue.java` 60-260, 300-420; `DatabaseDescriptor.java` 970-997;
`Dispatcher.java` 225-250; `InternodeOutboundMetrics.java` 30-160; `InternodeOutboundTable.java` 40-135; `OutboundConnections.java` 253-256;
`Message.java` 190-215; `Verb.java` 214, 345-358; `ConnectionTest.java` 225-262; `test/conf/cassandra.yaml` (storage port 7012); `build.xml`
(test timeout 480 s, `maxmemory` 1024m).

**What this file tests beyond the closed acquire-side case** (`…-acquireCapacity-pendingCapacityInBytes--guided`). That case drove `acquireCapacity` through boundary steps U1–U9 and confirmed the plateau `C + F`, the receive-key wiring and the node-wide formula. This file targets the **release** at `:449-452`. It adds four things:

1. The invariant `reserve == max(0, pending − C)` checked after **every** release step, including the step where pending crosses C.
2. A 16-thread acquire/release stress of 200 cycles per value, with the reserves checked at 0 after every cycle (no leak), and two mutants of `:449-452` that the test must detect.
3. U2's real heap per C on a connected link, the hard cap at exactly C on a failing-to-connect link (U3), and release through `onClosed`.
4. On the node, a real peer stalled by SIGSTOP on the **small** link (the acquire case held the large link with Byteman), with the link's reserve read every second through the stall and after the release.

Overlap is noted in section D.

| Group | Check | Rating | Note (section checked) |
|---|---|---|---|
| A. Core question | constrained quantity is memory or disk bytes | Met | B1/A2: a link's pending serialized bytes; the heap they pin is named, and the per-link vs whole-JVM gap is named in B3d |
| A. Core question | knob varied, ≥ 3 values incl. default | Met | B2b U1 64 KiB · 1 MiB · 4 MiB (default); B3b 4 MiB (default) · 64 · 256 MiB |
| A. Core question | real resource measured, not only the counter | **Partly** | U2/U3 heap and B3d histograms are read, but B3f's ΔH(4 MiB) ≈ 8–20 MiB sits inside the node's heap noise with no rule to tell. Amended **A7**: a noise rule and k against the pending bytes at the histogram |
| A. Core question | usage driven to the limit and past it | Met | U1 acquires to the first failure; U2 sends M = 2·(C + R)/P + 100; cluster drops start at the plateau (time to plateau < 10 s, well inside the ~37 s conviction) |
| B. Logic | each step says what it establishes | Met | B2e/B3e and B2h/B3h |
| B. Logic | prediction stated in numbers or a clear relation | **Partly** | U1 is exact (327 / 1310 / 4456 successes, re-derived from `:397-427` and `ResourceLimits:263-273`). "U1-stress does not drift" had no number. Amended **A1** (a band; see §4: it is missed in 1 of 1,800 cycles, a missed sub-prediction) |
| B. Logic | every plausible outcome has a conclusions row | **Partly** | B3g had no row for a leak at the release, for heap below noise, or for expiry. Amended **A8** (three rows); B2g had no row for an insensitive test (**A2**) |
| B. Logic | confirmation needs ceiling-follows-knob and direct disallow evidence | Met | `overloadedCount`, `SmallMessageDroppedTasksDueToOverload` and the `overloaded; dropping` WARN, with the plateau following C |
| B. Logic | alternative explanations and their controls | **Partly** | Two alternatives were not ruled out. First, expiry: B3a's 60 s `write_request_timeout` alone leaves a 12 s expiry (`Dispatcher.java:238-244`; defect 1 of the receive-side twin). Amended **A4**. Second, an insensitive invariant. Amended **A2**: mutants M1 and M2 must fail |
| C. Specific | a human can follow it from the intro and B1 | Met | |
| C. Specific | an AI can run B2e/B3e without re-deriving the code path | **Partly** | U3's failing state needs a scheduled retry (`:277`, `:1104`). Amended **A3** (a dead port and `connectionAttempts ≥ 2`) |
| C. Specific | knob, values, workload, commands, observables, sampling, stop conditions exact | **Partly** | `sjk mx` starts a JVM per attribute, too slow for 8 attributes a second. Amended **A6** (a persistent JMX poller, plus the `internode_outbound` vt for the reserve). The send endpoint key is inert (**A5**). Processes, `ulimit` and storage: **A9** |
| D. Runnable | harness and environment prerequisites exist or are listed | Met | B2e gives the test skeleton; Byteman is not needed; the in-tree driver serves the vt |
| D. Runnable | workload arithmetic reaches the limit | Met | 30,000 × 1,064 B ≈ 32 MB/s: 257 MiB in ≈ 8.5 s, under the ≈ 37 s phi-16 conviction; heap at k ≤ 4: about 1 GiB at 256 MiB on a 4 GiB heap; about 3 GB of data per lifetime on the tmpfs |
| D. Runnable | load-bearing citations spot-checked | Met | All the above. One finding outside this file, from the closed acquire case: `internode_application_send_queue_reserve_endpoint_capacity` is inert, and the per-peer reserve comes from the receive key. Every B3f number still holds because the 1 MiB global reserve binds (**A5**) |

| # | Recommendation | Applied? | Why |
|---|---|---|---|
| A1 | U1-stress "no drift" made exact: every cycle's total in `[C + R_e − 4095, C + R_e]` | applied 2026-10-21 (B2f) | a number was needed. **The band ignores the reserve that a CAS-retrying acquirer holds for a moment (`:415-437`), so concurrent failures can occur below it; missed in 1 of 1,800 counted cycles (§4).** The derivation error was found by a reading, so A1 stays as filed and the miss is recorded |
| A2 | Sensitivity mutants M1 (`:452` releases `bytes`) and M2 (guard removed); B2g row added | applied (B2g, B2h) | nothing showed the invariant could fail if `:449` were wrong |
| A3 | U3 peer = a dead loopback port; `connectionAttempts ≥ 2` before the bulk enqueue | applied (B2c) | `isFailingToConnect` is set only with a scheduled retry |
| A4 | `native_transport_timeout: 60000ms` on both nodes | applied (B3a) | a 12 s expiry would release capacity during the window |
| A5 | Note: the send endpoint key is inert; effective endpoint reserve 128 MiB from the receive key; B3f unchanged | applied (B3a, note) | from the closed acquire case, not from a reading of this file |
| A6 | Persistent JMX poller; `system_views.internode_outbound` for the link's reserve | applied (B3d) | `sjk` is too slow; the reserve is the only node-level view of `:449` |
| A7 | Heap noise rule: N = range of the t = 18 s histogram totals; adjudicate where ΔH > 3N; k against pending at the histogram | applied (B3d) | ΔH(4 MiB) was predicted below the node's noise |
| A8 | B3g rows: leak at the release, heap not adjudicable, expiry in the window | applied (B3g) | README group B |
| A9 | tmpfs storage on `pc13`; process matching; `ulimit -n` | applied (B4) | execution detail |
| R10 | B3f's ΔH = k·plateau has no intercept; the C-independent heap (already-sent messages held by write handlers) should be a term | **left for stage 3** (section D) | found from readings, so not applied |

**Agreement criteria:** not filled (no run 2, §5.2).

## 2. Environment

| Field | Run 1 |
|---|---|
| Date | 2026-10-21 MDT (2026-10-22 UTC). Unit attempt 1 02:53–02:57 UTC; unit tier, counted run, 03:00:51–03:03:47 UTC; cluster shakedown 03:04–03:09; cluster run 1 03:10:07–03:29:01 UTC; self-check after |
| Node | `pc13` = `node3.jason92-320876.misconfiguration-pg0.cloudlab.umass.edu`, 40 cores, 251 GiB, driven over SSH from `pc07`. Cluster: A 127.0.0.1 (JMX 7199), B 127.0.0.2 (JMX 7299) on this one host |
| OS and kernel | Ubuntu 22.04.2, `5.15.0-187-generic` |
| JDK | OpenJDK 11.0.32.1. Unit: the `testsome` JVM, 1 GiB, CMS/ParNew. Cluster: G1, `MAX_HEAP_SIZE=4G`, `HEAP_NEWSIZE=800M` on both nodes |
| Ant | 1.10.12 |
| Local clone | `pc13:~/cassandra-sq2` at `cassandra-5.0.9` (`b5f2a54210d541339c2e7c17a794195cac0e67c2`), cloned from `~/cassandra-run1`, `ant build-test` 1 min 19 s; the test file is copied in and removed after each run. Mutants were built in a throw-away clone `~/cassandra-sq2-mut`, which was removed |
| Case-file commit / harness commit | none (untracked); sha256 in §1; harness md5 in `run1/harness-md5-*.txt` |
| Storage for node data | tmpfs `pc13:~/stage4-sq2/nodes` (40 GiB, RAM), wiped per lifetime, unmounted at the end; node logs and conf in `pc13:~/stage4-sq2/{A,B}/` |
| Full logs | `pc13:~/stage4-logs/sq2/`: `run1/unit/` (ant logs, `probe-{1,2,3}.out`, `histo-{1,2,3}/`, mutant logs), `run1/unit-attempt1/`, `diag-u2/` (the defect-2 diagnostic), `run1/cluster/<label>/` (`jmx.csv`, `vt-out.csv`, `vt-final.csv`, histograms, `stress.log`, both nodes' `system.log`/`debug.log`, yamls, `session.log`), `shakedown1/`, `run1-chain.log`, `selfcheck*.out`. 21 MB. Excerpts in [`run1/`](internode_application_send_queue_capacity-releaseCapacity-pendingCapacityInBytes--autonomous/run1/) |

## 3. Runbook defects

| # | Run | Step | Problem | Fix | Decision (date) | Case-file version with the fix |
|---|---|---|---|---|---|---|
| 1 | run 1, unit attempt 1 | B2e / A2 (mutants) | M1 ran **unmutated** code: no violation, no exception, although its 262nd release at C = 64 KiB must drive the reserve to −536. Ant's javac compares mtimes with a 1 s granularity, and the edited source was only 0.6 s newer than the copied class file, so it was not recompiled. Proof: `javap` of a rebuilt M1 showed `lload 9` (`excess`) at the release. M2 was recompiled (its edit came later) and failed | `unit-run.sh` deletes `OutboundConnection*.class` before each mutant build and prints the bytecode at the release (M1 `lload_3` = `bytes`) | harness only, 2026-10-21; unit tier restarted | — (B2 text unchanged) |
| 2 | run 1, unit attempt 1 | B2c/B2e U2 (blocking method) | Holding the queue lock in the test thread does stop delivery, but `EventLoopDelivery.doRun` registers a `this::execute` callback on every failed `lockOrCallback` (`OutboundConnection.java:777-780`). During the ~2 s hold the event loop registered 8.7–9.9 M `OutboundMessageQueue$Locked` nodes plus their lambdas, ≈ 350–400 MB (test-JVM class histograms, `run1/unit-attempt1/diag-*`). `heapDelta` therefore read 0.23–0.52 GB at every C (ratio 24–36 at 8 MiB), which measures the method, not the queue. The accounting readings were unaffected and identical to the restart | delivery blocked by **parking the link's event-loop thread**; a class histogram at each U2 heap reading | dated amendment next to B2c, 2026-10-21; B2f/B2g unchanged; unit tier restarted | `b48dd16e…` |
| 3 | cluster shakedown (not a reading) | B3e step 7 / A9 (process match) | The daemon's command line names the clone only as `bin/../`, so a match on the clone path missed a starting node. The script declared it dead, and the node was left running until stopped by hand (`nodetool stopdaemon`) | match `java` + `CassandraDaemon` + cwd = the clone (or the run's conf path) | harness only, 2026-10-21, before run 1 | — |

Unit attempt 1's readings are kept in `run1/unit-attempt1/` and are not counted. The cluster tier ran once, as written, with no defect.

## 4. Run 1

**Scope:** unit tier complete (three repetitions of the probe, plus the two mutants); cluster tier complete (five lifetimes, each
`cassandra-stress write duration=90s` at a fixed 30,000/s through A, RF 2, CL ONE, 1,000-byte values). **Command log:**
`run1/unit/summary.txt`, `run1/run1-chain.log`, and per lifetime `run1/cluster/<label>/summary.txt`.

### 4.1 Readings

**Unit tier** (`run1/unit/probe-{1,2,3}.out`, `summary.txt`; the same in all three repetitions unless stated)

| Test or assertion | Result | Evidence |
|---|---|---|
| `ConnectionTest#testAcquireReleaseOutbound,testInsufficientSpace` (B2h) | 2/2 pass | `unit/summary.txt` |
| U1 at C = 64 KiB / 1 MiB / 4 MiB: successes, pending at first failure, endpoint = global | 327 / 1310 / 4456; 327,000 / 1,310,000 / 4,456,000; 261,464 / 261,424 / 261,696, exactly as B2f | `probe-*.out` `PROBE U1-full` |
| U1 release in steps of 1000: `endpoint == max(0, pending − C) == global` after every step | 0 violations; the endpoint first reaches 0 at pending 65,000 / 1,048,000 / 4,194,000 (the first step ≤ C); final (0, 0, 0) | `PROBE U1-released` |
| U1-stress, 16 threads × 200 cycles at each C (1,800 cycles) | barrier invariant: 0 violations; after every cycle (0, 0, 0): 0 violations; totals first ≈ last (e.g. 4,456,316 → 4,456,259) | `PROBE U1-stress` |
| U1-stress A1 band `[C + R_e − 4095, C + R_e]` | missed in 1 cycle (repetition 2, C = 4 MiB, cycle 101, total 4,450,829, 1,524 B below the band) | `probe-2.out` |
| U2 at C = 8 / 32 / 128 MiB (s = 16,403) | pending 9,431,725 / 34,593,927 / 135,261,909, each in (C + 1 MiB − s, C + 1 MiB]; endpoint = global = pending − C (1,043,117 / 1,039,495 / 1,044,181); overloaded = M − accepted (677 / 2,215 / 8,366) | `PROBE U2` |
| U2 heapDelta | 9.06 / 32.83–32.88 / 129.56 MiB; ratio 1.0075 / 0.995–0.997 / 1.0044; heap-vs-pending scaling against 8 MiB 0.989 and 0.997 (B2g band 0.8–1.25). Histograms show only `[B` growing (21.3 / 46.5 / 147.2 MB against 11.9 MB idle) | `PROBE U2`, `unit/histo-*` |
| B2h M = 0 control | heapDelta −1.33 MiB / −2.66 MiB / −784 B (−1,396,720 / −2,792,576 / −784 B) | `PROBE U2-control-M0` |
| U2 after `close(false)` | (0, 0, 0) at every C | `PROBE U2-closed` |
| U3 at C = 8 / 32 MiB (failing to connect, 5 attempts) | pending 8,381,840 / 33,544,168, each in (C − s, C]; reserves 0 / 0; overloaded 613 / 2,151 = M − accepted; heap ratio 1.005–1.039 / 0.993–1.013; after close (0, 0, 0) | `PROBE U3` |
| Mutant M1 (`:452` releases `bytes`; bytecode `lload_3`) | **fails**: `UnrecoverableIllegalStateException … (using=-536)` at the first release whose excess < 1000 | `unit/mut-M1-excerpt.log` |
| Mutant M2 (`:449` → `if (true)`) | **fails**: `AssertionError` in `Concurrent.release` (a negative release) | `unit/mut-M2-excerpt.log` |

**Cluster tier.** s = 1,064 B per message. The plateau is the median of `SmallMessagePendingBytes` over pause + 5…25 s; reserve =
`using_reserve_bytes` of `internode_outbound`. ΔH = the histogram total at pause + 12 s minus `neg`'s at t0 + 32 s (84,950,672 B).
N = 11,138,368 B (the range of the five t0 + 18 s totals: 90,848,296 · 90,062,120 · 91,722,640 · 89,818,776 · 80,584,272), so 3N = 33.4 MB.

| Capacity value | Run | Plateau (C + R; gap) | ≥ C at | Drops (pause+25 s / end) | Reserve at plateau; after SIGCONT + 15 s; final | Histogram total (MB); ΔH (MiB) | k = ΔH / pending | Live `Mutation` vs `PendingTasks` | Stress |
|---|---|---|---|---|---|---|---|---|---|
| 4 MiB (default), R 1 MiB | B stopped | 5,242,328 (5,242,880; 552) | +1.2 s | 744,405 / 888,040 | 1,048,024 = P − C; 0 in 59 samples; 0 | 145.8; 58.1 | **11.61** | 12,773 vs 4,927 | 29,949/s, 0 errors |
| 64 MiB, R 1 MiB | B stopped | 68,156,648 (68,157,440; 792) | +3.2 s | 684,437 / 828,209 | 1,047,784 = P − C; 0 in 60; 0 | 351.3; 254.0 | **3.91** | 72,734 vs 64,057 | 29,871/s, 0 |
| 256 MiB, R 1 MiB | B stopped | 269,483,536 (269,484,032; 496) | +9.2 s | 495,067 / 639,284 | 1,048,080 = P − C; 0 in 60; 0 | 1,010.7; 882.9 | **3.44** | 262,003 vs 253,274 | 29,856/s, 0 |
| 4 MiB, R 128 MiB (positive control) | B stopped | 138,411,504 (138,412,032; 528) | +1.2 s (first drop +5.2 s) | 619,874 / 763,556 | 134,217,200 = P − C; 0 in 60; 0 | 573.4; 465.8 | 3.53 | 137,254 vs 130,086 | 29,908/s, 0 |
| 64 MiB, R 1 MiB (negative control) | B running | max 51,072 (< 1 MiB); median 532 | — | 0 / 0 | 0 throughout | 85.0 (t0 + 32 s) | — | 4 | 29,984/s, 0 |

All stopped lifetimes, re-derived by the self-check:

- **Plateau flat:** inside the window, max = the plateau once it was reached.
- **No expiry:** `SmallMessageDroppedTasksDueToTimeout` 0, `expired_count` 0.
- **B never convicted:** no `is now DOWN`.
- **Small link only:** Urgent and Large pending 0.
- **Clean logs:** no `ERROR`, no `UnrecoverableIllegalStateException` and no `OutOfMemoryError` on either node.
- **The reserve mirrors pending:** `using_reserve_bytes == pending_bytes − C` to the byte in every vt sample at the plateau, and it is 0 in every sample after SIGCONT + 15 s and in the final read.
- **Overload WARN:** each run logged one, e.g. c4m "queue: 4.999MiB local, 1023.461KiB endpoint, 1023.461KiB global"; the positive control reads "131.999MiB local, 127.999MiB endpoint".

**Heap line.** The marginal heap per counted byte is 3.265 (from 4 to 64 MiB) and 3.276 (from 64 to 256 MiB); the intercept is ≈ 41.7 MiB (`selfcheck.out`).
That line predicts the positive control's ΔH as 474.1 MiB against 465.8 MiB measured (−1.8 %).

### 4.2 Conclusion and logic

1. **Validity.** Both tiers are valid.
   - **Unit:** every check ran [observed: `unit/summary.txt`, 72 check lines per repetition]; the mutants compiled [observed: bytecode lines] and failed [observed: mutant excerpts]; U3's link was failing to connect (5 attempts) [observed]. The blocking method is the amended one, and the U2 histograms show no `Locked` growth [observed: `unit/histo-*`].
   - **Cluster:** the limit was reached at every stopped value (overload drops, the WARN) [observed]. The held-fixed settings are in place: knobs, 60 s timeouts, hints off, offheap_objects, phi 16 [observed: `A-yaml.diff`]. The workload was identical across lifetimes (29,856–29,984 writes/s, 0 errors) [observed: `stress-result.txt`]. There was no expiry and no conviction [observed]. Every ΔH clears 3N [observed: `analyze-summary.txt`].
2. **Readings.** Three things are unusual; no reading contradicts another.
   - (i) k is not constant: 11.6 at 4 MiB against 3.4–3.9 at 64 and 256 MiB [observed].
   - (ii) Live `Mutation`s exceed `PendingTasks` by an almost constant 7.2–8.7 k at every C, while `Message` instances ≈ `PendingTasks` (4,866 / 63,996 / 253,213 / 130,024) [observed: histogram heads]. [inferred: these are mutations already flushed into the loopback socket and unanswered. Each write response handler keeps `mutation.hintOnFailure()`, which is the `Mutation` itself (`Mutation.java:158`, `AbstractWriteResponseHandler.java:81`), until a response or the 60 s timeout. Overloaded messages drop their callback (`RequestCallbacks.onOverloaded`), so the extra is set by the socket buffers, not by C. 8.7 k × 1,064 B ≈ 9 MB, which is about what two loopback socket buffers hold.] This C-independent heap is the intercept behind (i).
   - (iii) Unit U2/U3 heap ratios of 0.993–0.997 are just below the predicted floor of 1.0, inside the M = 0 control's ±2.7 MiB noise [observed].
3. **Matched rows.**
   - **Unit: B2g row 1**, "U1/U2 pending plateaus at C+R (±1 message) and moves with C. U3 plateaus at C with zero reserve. Invariant holds and all counters return to 0 → Claim confirmed at the mechanism level". Every clause holds [observed: §4.1 unit table].
   - **Cluster: B3g row 4**, "Plateau scales with C but ΔH does not (k varies > 2× across C) → heap part of the claim wrong". Its trigger holds: k max/min = 3.38 [observed]. Every accounting clause of row 1 also holds: plateau ≈ C + 1 MiB at each C, drops rising after it, the positive control at 132 MiB while run 1 is at 5 MiB [observed]. So does A8's release row in the negative (reserve 0 after release) [observed].
   - **The meaning of row 4 is corrected, as the twin's row 3 was.** ΔH *does* scale with C: it is linear in the plateau with a constant marginal 3.27 (two segments agree within 0.4 %) [observed: `selfcheck.out`]. What fails is B3f's zero-intercept proportionality, because of the C-independent ≈ 42 MiB in (ii). So the cluster row is "partial: refines the claim". The counted bytes govern the heap with a stable marginal factor; the absolute ratio is not stable at small C.
4. **Excluded rows.**
   - **Unit:** the leak row (endpoint > 0 after release, or totals shrinking over cycles) is excluded by 0 non-zero-after-release in 1,800 cycles, first ≈ last totals, and final (0, 0, 0). The single below-band cycle is not a trend: it is isolated (cycle 101), it recovers, and the reserves were 0 before and after it. The over-release row is excluded by 0 barrier violations and no negative counter. pending > C + R + s: never. A plateau independent of C: no. Heap not scaling: 0.989/0.997 against the 0.8–1.25 band. `overloadedCount == 0`: no (613–8,366). The mutant row (A2): both mutants fail.
   - **Cluster:**
     - **Row 1 (Confirmed):** excluded only by its heap clause ("ΔH ∝ plateau with stable k"; k ±25 % fails).
     - **Row 2 (unbounded):** excluded; the plateau is flat at C + R.
     - **Row 3 (flat across C):** excluded; the plateau moves 4 → 64 → 256 MiB.
     - **Positive-control rows:** row 5 (validates) holds, and row 6 (does not move) is excluded.
     - **Row 7 (conviction):** excluded; no `is now DOWN`.
     - **A8 rows:** the leak row is excluded (reserve 0 after SIGCONT and in the final read; no exception); the heap-not-adjudicable row is excluded (all three clear 3N); the expiry row is excluded (0 timeout drops).
5. **Observed vs. inferred.** Three statements are inferred. The conclusion depends only on the third.
   - (a) That the ≈ 42 MiB intercept and the extra ~8 k `Mutation`s are already-sent messages held by write handlers. This rests on the code path and on the constant excess at every C; it was not traced per object.
   - (b) That the U1-stress below-band cycle comes from the transient reserve a CAS-retrying acquirer holds (`:415-437`).
   - (c) That the heap the queue governs equals "ΔH minus a constant". The conclusion uses only the observed linearity, not the attribution in (a).
6. **Deviations and gaps.**
   - Loopback on one host and tmpfs storage (§1). B `auto_bootstrap: false` (an empty ring).
   - A heap histogram once per lifetime (plus t0 + 18 s), so "heap stops rising once the plateau is reached" is read from the pending plateau, not from repeated heap samples.
   - Per-link heap is not observable (B3d): ΔH is whole-JVM against the negative control.
   - Run 1 values only; no run 2.
7. **Core question.** The constraint caps what it counts. A link's queued bytes stop within one message of C + min(reserves) at every C, at both tiers, and messages past it are dropped (parts 1 and 3). The release at `:449-452` returns exactly the bytes above C: the reserve equals pending − C at every unit step and at every plateau sample, returns to 0 after the drain, and two mutants of the line are caught (parts 3 and 4). The node's heap follows C: about 3.3 heap bytes per counted byte at every C, on top of about 42 MiB that does not depend on C (part 3). That constant term makes B3f's proportional k wrong at the default 4 MiB, where it dominates.

**Conclusion (one line):** unit B2g row 1 — confirmed. Cluster B3g row 4 by its trigger: confirmed for the accounting and the release at `:449`, refuted for B3f's proportional heap relation (k 11.6 · 3.9 · 3.4), while the heap follows C linearly (marginal 3.27). Partial; refines the claim.

**Sub-predictions (B2f/B3f/B2h)**:

- **Met:** U1 exact numbers; U2 heapDelta ≈ 9.2 / 33.2 / 129.2 MiB ± 5 % (9.06 / 32.85 / 129.56); U3 overloaded ≈ M − C/s; ΔH run 2 (100–260 MiB: 254.0) and run 3 (390–1030 MiB: 882.9); k ∈ [1.5, 4] at 64 and 256 MiB; the plateau flat; pending ≈ 0 after SIGCONT; the negative control < 1 MiB with 0 drops; drops growing ≈ 30 k/s at 4 MiB (31.3 k/s).
- **Missed:**
  - the A1 band (1 of 1,800 cycles);
  - U2/U3 heap ratio ≥ 1.0 (0.993–0.997 in four readings);
  - B2h M = 0 within ±2 MiB (−2.66 MiB once);
  - ΔH run 1 in 8–20 MiB (58.1) and k ∈ [1.5, 4] at 4 MiB (11.6);
  - "`Mutation` count ≈ `PendingTasks` (± a few thousand)" (+7.2 to +8.7 k);
  - time to plateau "~2 s" and "~8 s" read 3.2 and 9.2 s (1 s sampling), the same shape.

## 5. Self-check of run 1 — AI

[`run1/selfcheck.py`](internode_application_send_queue_capacity-releaseCapacity-pendingCapacityInBytes--autonomous/run1/selfcheck.py) re-parses the raw files on `pc13` with its own code and tests them against B2f/B2g/B3f/B3g, typed in:

- unit: `probe-*.out`, the mutant ant logs, `summary.txt`;
- cluster: `jmx.csv`, `vt-out.csv`, `vt-final.csv`, the histograms, `times.json`, the yaml and `system.log` of A.

**Pass 2: 177 checks, exit 0** ([`run1/selfcheck.out`](internode_application_send_queue_capacity-releaseCapacity-pendingCapacityInBytes--autonomous/run1/selfcheck.out)). The one load-bearing "FAIL" is the deliberate test that row 1's heap clause does *not* hold. The 10 sub-prediction misses are those listed in §4.2.

Pass 1 ([`selfcheck-pass1.out`](internode_application_send_queue_capacity-releaseCapacity-pendingCapacityInBytes--autonomous/run1/selfcheck-pass1.out)) failed four release checks, but the mistake was the self-check's own. It required pending = 0 after SIGCONT + 15 s while stress was still writing (pending ≤ 4,260 B). The corrected test is reserve = max(0, pending − C) = 0 with pending < C, plus the final read (0, 0) after stress stopped.

### 5.1 Check of run 1's conclusion

| Part | Holds? | Note (file re-read) |
|---|---|---|
| 1. Validity | yes | yaml knobs, timeouts and hints re-read per label; timeout drops 0; no DOWN/ERROR/OOM/`UnrecoverableIllegalState`; mutant bytecode lines and exceptions re-read |
| 2. Readings | yes | plateau, s, drops, reserve per vt sample, histogram totals, `Mutation` counts and k re-derived from the raw files and equal to the run's `summary.txt` (e.g. N 11,138,368; k 11.613 / 3.907 / 3.435) |
| 3. Matched row | yes | unit row 1: every clause re-checked in all three repetitions. Cluster row 4: its trigger re-computed (max/min 3.38) and the linearity re-computed (3.265 / 3.276); the corrected meaning rests on observed numbers |
| 4. Excluded rows | yes | each row's excluding reading re-checked; the A8 leak row by 239 vt samples after SIGCONT and four final reads |
| 5. Observed vs. inferred | yes | the three inferred statements are named; the matched rows do not depend on (a) or (b) |
| 6. Deviations and gaps | yes | loopback, tmpfs, one histogram per lifetime, no per-link heap; none reverses a reading |
| 7. Core question | yes | B1's three falsifiers in order: the plateau moves with C; pending never exceeds C + R (gap 496–792 B); the reserve is 0 after release. The heap clause is judged by B3g's own trigger, with its meaning corrected from the readings |

### 5.2 Run 2?

**No**, decided 2026-10-21. The conclusion rests on observed readings. The accounting results are exact and repeated: three unit repetitions, and five lifetimes in which the vt reserve equals pending − C to the byte. The heap result is a linear fit whose two segments agree within 0.4 %, and the positive control falls on the same line (−1.8 %). The closed acquire-side case saw the same accounting on another harness and node.

## 6. Run 2 — fresh AI session (optional)

Not done (§5.2).

## 8. Verdict — AI

**Stage-3 estimate:** positive.

**Claim tested (B1):** "For one outbound link, the bytes held in its send queue plateau at `internode_application_send_queue_capacity + min(endpoint reserve, global reserve)`, and messages beyond that are dropped as overloaded. The release-side check at `OutboundConnection.java:449` returns exactly the bytes above `C` to the reserves, with no leak. As a result, the heap held by an outbound backlog to an unreachable or non-reading peer rises with `C` (by a roughly constant heap/serialized ratio k ≥ 1) and stops rising once that plateau is reached."
"Confirmed" below always means this claim held.

| Tier | Verdict (B2g / B3g row) | Effect on the constraint | Basis | Date |
|---|---|---|---|---|
| Unit | **Confirmed** — B2g row 1. U1 exact at 64 KiB / 1 MiB / 4 MiB; `reserve == max(0, pending − C)` after every release step; 1,800 stress cycles back to (0, 0, 0); U2 plateau C + 1 MiB with heap ratio ≈ 1.0 at 8 / 32 / 128 MiB; U3 capped at C with no reserve; mutants M1/M2 of `:449-452` caught | caps | run 1 + self-check | 2026-10-21 |
| Cluster | **B3g row 4 — partial: refines the claim** (not Confirmed as filed). Accounting and `:449` confirmed on the node: plateau 5,242,328 / 68,156,648 / 269,483,536 B = C + 1 MiB − < 1 message; positive control 138,411,504 B; reserve = pending − C to the byte; 0 after release; drops past the plateau. B3f's proportional heap relation refuted: k = 11.6 / 3.9 / 3.4. Heap follows C linearly (3.27 heap bytes per counted byte, constant) plus ≈ 42 MiB independent of C | caps — the queued bytes exactly; the heap linearly with C (≈ 3.3 × (C + reserve) + a C-independent ≈ 42 MiB of sent-but-unanswered mutations, inferred) | run 1 + self-check | 2026-10-21 |

**Feedback filed:** the case file's section D updated 2026-10-21 (not committed): the verdicts, A1–A9, runbook defects 1–3, the
missed sub-predictions, the corrected meaning of B3g row 4, R10 for stage 3 and the overlap with the acquire-side case. One
section amended besides D: B2c, with the dated defect-2 amendment, applied before the counted unit run. sha256: as filed
`49e904a2…`; after the audit `658ca786…`; after defect 2 `b48dd16e…` (the version run); **after section D: `e3594f1d5431c41672cad5f5f676a0fef16a0b537e4d55c114160a361aff8c42`** (only section D differs from
`b48dd16e…`: replacing D with "none yet" reproduces that hash).
