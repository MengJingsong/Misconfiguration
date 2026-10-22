# OTCP_LARGE_MESSAGE_THRESHOLD-doRun-maxSendBytes--autonomous — stage-4 results  <!-- file: results/OTCP_LARGE_MESSAGE_THRESHOLD-doRun-maxSendBytes--autonomous.md -->

> **Case:** [`OTCP_LARGE_MESSAGE_THRESHOLD-doRun-maxSendBytes--autonomous`](../../stage3-ai-deep-read/cases/OTCP_LARGE_MESSAGE_THRESHOLD-doRun-maxSendBytes--autonomous.md)
>
> **Status:** **verdict filed 2026-10-22. Unit: Not confirmed (B2g row U9, pool band missed) — undetermined. Cluster: Confirmed (B3g row C1) — does not cap.** No run 2. Audited 2026-10-22 (estimate negative). Run on `pc06`.
> 
> **Outcome class:** undetermined — stage-3 estimate vs the stage-4 effect on the constraint
>
> **Agent:** autonomous. "§9a" below means each tier's predictions and conclusions table: B2f and B2g (unit), B3f and B3g
> (cluster); "§9b–§9e" means B2a–B2e or B3a–B3e; the case file's feedback section is its section D.

## 1. Before run 1 — design audit and freeze

| Field | Content |
|---|---|
| **Case-file version** | Autonomous file. It is untracked in the working tree: no commit holds it, and nothing was committed, per the session's instructions. sha256 as filed: `d33cf16717796b29514e1a5231c07e58d59a493396b49a28acafa982ec0d426f`. **After the audit's amendments S4-A1 to S4-A11, before any harness run or reading: `6b3a899e9628ea09f183789915bd073767d8cc00ce0da890dd29df7862a105a3`** (the frozen design). Both tiers ran against this version; no later amendment was made. The final sha256 after section D is in §8. |
| **Harness** | `harness/OTCP_LARGE_MESSAGE_THRESHOLD-doRun-maxSendBytes--autonomous/`, written 2026-10-22 (step 1), not committed. The files are `LargeMessageThresholdFrameTest.java`, `unit-run.sh`, `make-node-yaml.sh`, `Jmx.java` (copied unchanged from the closed send-queue release case), `cluster-run.py` and `run1-chain.sh`. Their md5s are identical in the repo and in `pc06:~/stage4-harness-run/otc/` (`run1/harness-md5-{unit,cluster}.txt`). **Instrument checks:** a compile check of the test (`ant build-test`, BUILD SUCCESSFUL); every unit run asserts `lmt = V − 21`; a cluster shakedown (`shake`: no stall, 20 s of stress at 29,400/s, 0 errors) confirmed that the beans resolve, the daemons carry the property, and the yaml lines are in place. The shakedown found one harness defect (§3, defect 1), fixed before the counted chain. |
| **Tiers and values** | **Unit (B2):** V = 16384 · 65536 (default) · 131072, giving LMT 16363 · 65515 · 131051. C = 4 MiB (twice per JVM) and C = 1 MiB (the positive control), R = 64 KiB. Three `ant` runs per V: 27 readings. **Cluster (B3):** the same three V on both nodes, with C 1 MiB, endpoint 2 MiB (send key and, per S4-A6, receive key) and global 4 MiB. The positive control is C 16 MiB, endpoint 16 MiB and global 32 MiB at V = 65536. Each value was run twice: 8 lifetimes. |
| **Audit bottom line** | **Ready after amendments** — 2026-10-22 |

### 1.1 Design audit

**Checked against.** The pinned clone `/proj/misconfiguration-PG0/git-repos/cassandra-src` (`cassandra-5.0.9`) and the run clone `pc06:~/cassandra-otc` (`b5f2a54`). Re-read in context:
- `OutboundConnection.java`: 375-454 (acquire and release), 735-910 (`EventLoopDelivery.doRun`, the target `:767`, the packing loop, the watermarks, the `finally` release), 1060-1110 (connect retry), 1636-1690 (counters);
- `OutboundConnections.java`: 60-95, 210-230;
- `OutboundConnectionSettings.java`: 100-106, 205, 315-335, 388-396, 470-480;
- `FrameEncoder.java`: 25-110; `FrameEncoderCrc.java`: 30-80;
- `BufferPool.java`: 120-300, 380-480, 810-980, 1394-1410;
- `BufferPools.java`: 44-75; `BufferPoolMetrics.java`: 50-65; `InternodeOutboundMetrics.java`: 120-190;
- `InboundConnectionInitiator.java`: 108, 475-480;
- `DatabaseDescriptor.java`: 960-997, 3025-3040; `MessagingService.java`: 300-330; `Dispatcher.java`: 225-250; `Config.java`: 1399;
- `OutboundDebugCallbacks.java`; `Verb.java`: 214, 345-375;
- `ConnectionTest.java`: 85-265, 340-420;
- `build.xml`: 94, 1153, 1192, 1382-1392;
- `test/conf/cassandra.yaml` (storage port 7012).

**Overlap with the closed cases.**
- From `internode_application_send_queue_capacity-acquireCapacity-…--guided` (Confirmed), this file reuses the positive-control knob and the receive-key wiring finding (S4-A6).
- From `…-releaseCapacity-…--autonomous`, it reuses the SIGSTOP pattern, the JMX poller (`Jmx.java`), the yaml builder's shape and the daemon matcher.
- What is new here is the knob, the per-frame observable and the networking-pool reading. Overlap is noted in section D.

| Group | Check | Rating | Note (section checked) |
|---|---|---|---|
| A. Core question | constrained quantity is memory or disk bytes | Met | A2/B1: off-heap frame-buffer bytes in the networking pool; queued heap bytes (`pendingBytes`) |
| A. Core question | knob varied, ≥ 3 values incl. default | Met | B2b/B3b: 16384 · 65536 (default) · 131072 |
| A. Core question | real resource measured, not only the counter | **Partly** | Unit: the pool's own `usedSizeInBytes` is fine-grained (`memoryInUse`, `BufferPool.java:282-285`), but a 1 ms poller can miss a frame that lives for microseconds. Amended **S4-A2**: also sample inside `onSendSmallFrame`. Cluster: UsedSize and direct `MemoryUsed`, but heap only as an instantaneous G1 sawtooth. Amended **S4-A8**: a live class histogram. Gap named: the cluster's pool is shared with native transport, so no per-link pool figure exists |
| A. Core question | usage driven to the limit and past it | Met | B2c: a ≥ 1 MiB backlog ≫ LMT, so `min` at `:766` picks LMT on every frame but the last. The positive control is the send-queue C, a cap known to bind (closed Confirmed case). Note: the unit pendingPeak is read before delivery runs, so it cannot depend on LMT by construction (R12) |
| B. Logic | each step says what it establishes | Met | B2e/B3e and B2h/B3h |
| B. Logic | prediction stated in numbers or a clear relation | **Partly** | Three errors, each fixed before any reading. (i) B2f's per-reading pool bound left out the 64 KiB flushing allowance and the inbound Netty read buffer (**S4-A3**). (ii) B3f's 3 MiB / 32 MiB plateaus assumed the send-side endpoint key is effective; it is inert on the production path (**S4-A6**). (iii) B3f's "1 MiB macro chunks" is wrong: they are 8 MiB, `BufferPool.java:385` (**S4-A10**) |
| B. Logic | every plausible outcome has a conclusions row | **Not met** | B2g's Confirmed row omitted B1's pool clause. Neither table had a row for a band missed without a refutation. "Mechanism differs" and frame errors had no verdict. B3g's Refuted row omitted direct memory and had no "cap exceeded" row. "Peak" and the aggregation over repeats were undefined. Amended: **S4-A4** (rows U1–U9, in order) and **S4-A9** (rows C1–C7, in order) |
| B. Logic | confirmation needs ceiling-follows-knob and direct disallow evidence | Met | For this negative claim: maxFrame following LMT is direct evidence of the `min(…, LMT)` at `:766`. The binding cap is shown by `overloadedCount` (unit) and by `SmallMessageDroppedBytesDueToOverload` and the `overloaded; dropping` WARN (cluster) |
| B. Logic | alternative explanations and their controls | **Partly** | Two alternatives were not controlled. (i) With `-node 127.0.0.1` the driver routes requests to n2 as coordinator, so threads stall with n2. Amended **S4-A7** (`whitelist`, fixed 30,000/s). (ii) The instrument could miss the frame. Amended S4-A2, with row U8 |
| C. Specific | a human can follow it from the intro and B1 | Met | |
| C. Specific | an AI can run B2e/B3e without re-deriving the code path | **Partly** | `sjk mx` starts one JVM per attribute (S4-A8). Paths and processes on `pc06`: S4-A1, S4-A5, S4-A11 |
| C. Specific | knob, values, workload, commands, observables, sampling, stop conditions exact | **Partly** | Stall window, peak, baseline, per-V aggregation, "reached" and repeats of the control were undefined. Fixed by S4-A3, S4-A6 and S4-A9 |
| D. Runnable | harness and environment prerequisites exist or are listed | Met | `withDebugCallbacks`, `unsafeSet*`, the counters and `ConnectionTest`'s skeleton all exist at the tag |
| D. Runnable | workload arithmetic reaches the limit | **Partly** | Unit: Met (4 MiB backlog, ≥ 32 frames). Cluster: an unthrottled, routed stress could not be relied on to load n1's link (S4-A7). At 30,000/s × ~1.06 KB ≈ 32 MB/s, 3 MiB fills in < 1 s and 32 MiB in ~1–2 s, inside a 20 s stall and under the ~37 s phi-16 conviction. Disk is about 6 GB per lifetime on 55 GB free |
| D. Runnable | load-bearing citations spot-checked | Met | All of A1–A3's citations hold, including `:766-767`, `:782`, `:806-812`, `:838-859`, `FrameEncoder.java:64-67,97-104`, `FrameEncoderCrc.java:71`, `OutboundConnections.java:69-70,215-229`, `OutboundConnectionSettings.java:104` and `BufferPool.java:128-129`. There are two corrections, both applied: the 8 MiB macro chunk (S4-A10) and the receive-key wiring (S4-A6) |

| # | Recommendation | Applied? | Why |
|---|---|---|---|
| S4-A1 | Unit paths on `pc06` (`~/cassandra-otc`, harness script, logs) | applied 2026-10-22 (B2a) | execution detail |
| S4-A2 | Pool sample inside `onSendSmallFrame`; RESULT prints `lmt`, `sent`, `errors`; stop if `lmt` ≠ V − 21 | applied (B2d) | a 1 ms poller can miss a µs-lived frame; the property must be proven to reach the test JVM |
| S4-A3 | Corrected per-reading pool bound ≈ 128 KiB + 2(LMT + 2 KiB); poolPeakDelta ≥ maxFrame; `errors` 0 / `sent` = accepted; pendingPeak ∈ (C − S, C] expected (failing to connect); per-V median of six | applied (B2f) | derived from `:854`, `InboundConnectionInitiator.java:108`, `:409-413`; aggregation was undefined |
| S4-A4 | B2g replaced by U1–U9 in a fixed order | applied (B2g) | Confirmed row lacked B1's pool clause; missing rows and verdicts |
| S4-A5 | Cluster: one clone, per-node `CASSANDRA_CONF`/`CASSANDRA_LOG_DIR`, data on local disk, `ulimit`, process matching | applied (B3a) | execution detail |
| S4-A6 | Set `internode_application_receive_queue_reserve_endpoint_capacity` = the send endpoint value (2 / 16 MiB); control run twice | applied (B3b) | the send endpoint key is inert on the production path (closed acquire case U10, c1/c2); without this the plateaus are 5 / 48 MiB, not B3f's 3 / 32 MiB |
| S4-A7 | Stress: `-node whitelist 127.0.0.1`, `fixed=30000/s`, `threads=200` | applied (B3c) | routing to the stopped n2 would stall clients; equal offered load across V |
| S4-A8 | Persistent JMX poller; heap sub-prediction from the live class-histogram total at SIGSTOP + 12 s; NMT at SIGSTOP + 15 s | applied (B3d) | `sjk` too slow; heap-used sawtooth cannot show 29 MB |
| S4-A9 | B3g replaced by C1–C7 in a fixed order, with definitions (window, peak, baseline, per-V mean, 2 KiB for one message) | applied (B3g) | Refuted row lacked direct; no band-missed, cap-exceeded or frame-error verdict |
| S4-A10 | Macro chunk is 8 MiB, not 1 MiB; the direct band means "no step" | applied (B3f note) | factual correction |
| S4-A11 | Cleanup paths and process checks on `pc06` | applied (B4) | execution detail |
| R12 | The unit pendingPeak is read at the end of phase 1, before any delivery, so it cannot depend on LMT by construction. A unit check of "queued usage independent of LMT" would have to read pending while delivery runs (e.g. a paced inbound) | **left for stage 3** (section D) | design strength, not needed for a valid run |
| R13 | B1's pool clause ("< about one LMT per backlogged connection") and B2f's 300 KiB band should count both ends of an in-JVM link and the frames in flight; found from readings (§4), so not applied | **left for stage 3** (section D) | reading-derived; the HARD RULE forbids a post-reading row or band change |

**Agreement criteria:** not filled (no run 2, §5.2).

## 2. Environment

| Field | Run 1 |
|---|---|
| Date | 2026-10-22 UTC. Unit tier 08:20:24–08:23:17. Cluster shakedown (not counted) 08:24:00–08:26:43. Cluster tier 08:27:23–09:00:16 (eight lifetimes, then `analyze`). Self-check after |
| Node | `pc06` = `node2.jason92-320876.misconfiguration-pg0.cloudlab.umass.edu`, 40 cores, 251 GiB, driven over SSH from `pc07`. For this batch the node was this agent's alone. Cluster: n1 127.0.0.1 (JMX 7199, seed, coordinator; its small link to n2 is measured) and n2 127.0.0.2 (JMX 7299) on the one host |
| OS and kernel | Ubuntu 22.04.2 LTS, `5.15.0-187-generic` |
| JDK | OpenJDK 11.0.32.1. Unit: the `testsome` JVM (1 GiB, `build.xml:1153`). Cluster: `MAX_HEAP_SIZE=4G`, `HEAP_NEWSIZE=800M`, `-XX:NativeMemoryTracking=summary` on both nodes |
| Ant | 1.10.12 |
| Local `cassandra-src` clone commit | `pc06:~/cassandra-otc` at `cassandra-5.0.9` (`b5f2a54210d541339c2e7c17a794195cac0e67c2`), cloned from `~/cassandra-run1`; `ant build-test` in 1 min 10 s. The test file is copied in by `unit-run.sh` and removed after |
| Case-file commit / harness commit | none (untracked); sha256 in §1; harness md5 in `run1/harness-md5-*.txt` |
| Storage for node data | local disk `/dev/sda3` (55 GB free): `pc06:~/stage4-otc/n{1,2}/data`, removed after every lifetime |
| Full logs (path, outside the repo) | `pc06:~/stage4-logs/otc/`: `clone.log`, `build-test.log`, `compile-check.log`; `run1/unit/` (ant logs, JUnit XML, `result-V*-r*.txt`, `all-results.txt`, `unit-run.log`); `run1/cluster/<label>/` (`jmx.csv`, `times.json`, `summary.json`, `stress.log`, histogram, NMT, both nodes' `system.log`/`debug.log`/`gc.log`, yamls and diffs, `session.log`); `run1/cluster/analyze-summary.txt`; `run1-chain.log`; `shake/`; `run1/selfcheck-*.out`. Excerpts are in [`run1/`](OTCP_LARGE_MESSAGE_THRESHOLD-doRun-maxSendBytes--autonomous/run1/) |

## 3. Runbook defects

| # | Run | Step | Problem | Fix | Decision (date) | Case-file version with the fix |
|---|---|---|---|---|---|---|
| 1 | cluster shakedown (not a reading; before any counted lifetime) | B3g row C4 / harness | The orderly stop of n2 at the end of every lifetime makes n1 log `/127.0.0.2:7000 is now DOWN` (shakedown n1 `system.log` line 347). The harness counted every DOWN line, so C4 would have discarded every run | `cluster-run.py` and `selfcheck.py` count only DOWN lines whose UTC time stamp lies inside [SIGSTOP, SIGCONT], which is row C4's own wording ("during a run's stall") | harness only, 2026-10-22, before the counted chain | — (case file unchanged) |

**Not a defect, recorded as a deviation.** The `testsome` JVM's working directory was the harness copy, so the test yaml's relative directories (`build/test/cassandra/…`) were created as `pc06:~/stage4-harness-run/otc/build/` (536 KB, local disk, not `/proj`). They were removed at clean-up.

The unit tier ran once, as written. The cluster tier ran once, as written, after the shakedown fix.

## 4. Run 1

**Scope:**
- **Unit tier:** complete. Three `ant testsome` runs per V, each running `fillAndDrain_C4M_repeat`, `fillAndDrain_C1M` and `fillAndDrain_C4M` (JUnit's order).
- **Cluster tier:** complete. Eight lifetimes in the order v16k-1, v64k-1, v128k-1, ctl-1, v16k-2, v64k-2, v128k-2, ctl-2. Each ran `cassandra-stress write duration=90s` at a fixed 30,000/s through n1 (RF 2, CL ONE, 1,000-byte values). n2 was SIGSTOPped at t0 + 30 s and SIGCONTed at t0 + 50 s.

**Command log:** `run1/unit/unit-run.log`, `run1/run1-chain.log`, and per lifetime `~/stage4-logs/otc/run1/cluster/<label>/session.log` (summaries in `run1/cluster/<label>/summary.json`).

### 4.1 Readings

**Unit tier** (`run1/unit/all-results.txt`, 27 RESULT lines; `lmt = V − 21` in all of them).

| Test or assertion | Result | Evidence |
|---|---|---|
| S = serialized size of one message | 1013 (first method in the JVM) / 1014 | `all-results.txt` |
| maxFrame (C = 4 MiB, all 6 per V) | **16,224 / 64,896 / 130,806** at V = 16384 / 65536 / 131072, which is 16 / 64 / 129 messages × 1014. Every value is in its B2f band [LMT − S, `roundUp(LMT+10,2048) − 10`] = [15,349, 16,374] / [64,501, 65,526] / [130,037, 131,062] | `all-results.txt` |
| Frame-size histogram | V = 16384: 258–262 × "15K" + 1 tail frame; 65536: 64–65 × "63K" + 1; 131072: 32 × "127K" + 1 | `hist=` field |
| frames (C = 4 MiB) | 259–263 / 65–66 / 33 (predicted ~256 / 64 / 32) | `all-results.txt` |
| pendingPeak (C = 4 MiB) | **identical at every V**: 4,259,688 in every `C4M_repeat` line (C + R − 152) and 4,193,904 in every `C4M` line (C − 400). The per-V median is 4,226,796 at all three V | `all-results.txt` |
| Positive control, pendingPeak at C = 1 MiB | 1,048,476 in all 9 lines, 3,178,320 B below the V = 65536 C = 4 MiB median; `overloaded=1` (the cap refused) in every line | `all-results.txt` |
| poolPeakDelta (C = 4 MiB, six per V) | V = 16384: 81,920 · 98,304 · 98,304 · 114,688 · 114,688 · 114,688 (median **106,496**). V = 65536: 196,608 · 5 × 262,144 (median **262,144**). V = 131072: 393,216 · 5 × 458,752 (median **458,752**). Span of the medians **352,256 B = 344 KiB**; max 448 KiB, every value < 1 MiB. poolBaseline = 0 in all lines | `all-results.txt`, `selfcheck-unit.out` |
| poolPeakDelta (C = 1 MiB) | 63,488 – 65,536 / 196,608 – 262,144 / 393,216 – 458,752 | `all-results.txt` |
| overflowDelta | 0 in all 27 lines | `all-results.txt` |
| Delivery | `sent = accepted`, `errors = 0`, `pendingAfter = 0` in all 27 lines; drain 811–1,035 ms | `all-results.txt` |

**Cluster tier.** The stall window holds 20 samples (1 s) and the baseline [t0+10, t0+25 s] holds 15 (`summary.json`; re-derived by `selfcheck-cluster.out`).

| Capacity value | Run | Pending peak (B) | UsedSize peak − base (B) | direct peak − base (B) | Overflow Δ | Live-heap histogram total at stall+12 s (B) | Overload dropped bytes at SIGCONT | Expired (timeout) tasks | DOWN in stall | Stress |
|---|---|---|---|---|---|---|---|---|---|---|
| V 16384 | 1 | 3,145,417 | 84,000 | 206,508 | 0 | 225,042,792 | 624,063,914 | 2,883 | 0 | 29,770/s, 0 errors |
| V 16384 | 2 | 3,145,417 | 127,008 | 215,328 | 0 | 546,609,496 | 644,113,157 | 2,897 | 0 | 29,841/s, 0 |
| V 65536 (default) | 1 | 3,145,417 | 102,784 | 229,098 | 0 | 236,564,528 | 621,683,857 | 2,897 | 0 | 29,875/s, 0 |
| V 65536 | 2 | 3,145,417 | 102,400 | 207,921 | 0 | 226,617,464 | 621,801,850 | 2,897 | 0 | 29,953/s, 0 |
| V 131072 | 1 | 3,145,417 | 94,208 | 203,514 | 0 | 203,804,416 | 622,924,378 | 2,897 | 0 | 29,711/s, 0 |
| V 131072 | 2 | 3,145,417 | 106,496 | 205,612 | 0 | 220,361,960 | 624,657,068 | 2,897 | 0 | 29,971/s, 0 |
| Control (C 16, E 16, G 32 MiB), V 65536 | 1 | **33,553,595** | 122,912 | 231,870 | 0 | 655,113,664 | 561,707,271 | 33,909 | 0 | 29,863/s, 0 |
| Control | 2 | **33,553,595** | 69,600 | 213,934 | 0 | 353,433,528 | 561,951,761 | 31,503 | 0 | 29,670/s, 0 |

"Overload dropped bytes at SIGCONT" is the first `SmallMessageDroppedBytesDueToOverload` sample at or after SIGCONT; "Expired" is `SmallMessageDroppedTasksDueToTimeout` at the end (`summary.json`).

- **Per-V means:**
  - pending: 3,145,417 at every V; span 0 B;
  - UsedSize: 105,504 / 102,592 / 100,352; span **5,152 B**;
  - direct: 210,918 / 218,509.5 / 204,563; span **13,946.5 B**.
- **The cap binds.**
  - In every main run, pending reached ≥ 90 % of 3 MiB within 1.25–1.30 s of SIGSTOP (control 1.25 s) and stayed at 3,145,417 = 3 MiB − 311 B.
  - `SmallMessageDroppedBytesDueToOverload` grew by ≈ 32 MB/s.
  - n1 logged `overloaded; dropping 1.038KiB message (queue: 3.000MiB local, 2.000MiB endpoint …)`.
  - The control plateaued at 32 MiB − 837 B.
- **What did not move.**
  - Pool `Size` stayed at 8,388,608 (one macro chunk) in every sample of every lifetime.
  - Urgent and Large pending stayed at 0.
  - No `ERROR` line, no frame error, and no DOWN inside the stall in n1's log. The only DOWN line in each lifetime is from the orderly stop at its end (§3).
- **Messages expired** (`DroppedTasksDueToTimeout` ≈ 2.9 k) about 10 s into the stall, as `write_request_timeout` 10 s allows. Pending dipped for one sample (e.g. v128k-1: 3,106,086) and refilled, so the peak is not affected.
- **Live-heap histogram:** control 504.3 MB (mean) against 231.6 MB at V = 65536, a difference of +272.7 MB. V = 16384 run 2 read 546.6 MB, an outlier among the main runs (the others are 203.8–236.6 MB).

### 4.2 Conclusion and logic

1. **Validity.**
   - **Unit:** valid.
     - The property reached every test JVM: `lmt = V − 21` [observed: `all-results.txt`].
     - The backlog formed: C or C + R bytes before the drain, and the cap refused with `overloaded=1` [observed].
     - Every frame but the tail was LMT-limited: the histogram's single bucket per V [observed].
     - The drain completed: `sent = accepted`, `errors = 0` [observed].
     - The instrument caught the frames: poolPeakDelta ≥ maxFrame in all 27 lines; there were 263 / 66 / 33 callback samples and about 1,000 poller samples per method [observed].
   - **Cluster:** valid.
     - The yaml knobs are as B3b plus S4-A6 in every lifetime [observed: `n1-yaml.diff`, `selfcheck-cluster.out` "yaml knobs … PASS"].
     - Both daemons carried `-Dcassandra.otcp_large_message_threshold=V` [observed: `times.json` `n1_property_ok`/`n2_property_ok`].
     - The offered load was the same: 29,670–29,971 writes/s, 0 errors [observed: `stress-result.txt`].
     - The cap was reached in every main and control run [observed].
     - n2 was not convicted during any stall [observed: `n1-log-grep.txt`, `summary.json` `n1_down_in_stall` 0].
     - There were no frame errors [observed].
2. **Readings.**
   - (i) **Unit poolPeakDelta rises with V:** medians 106 → 262 → 459 KiB, about 3 × ΔLMT across the range [observed]. At V = 131072 every value except one exceeds S4-A3's per-reading bound of 397,270 B [observed: `selfcheck-unit.out` FAIL line]. [inferred: from the readings alone (not traced object by object), about 3.5 × 128 KiB is held at V = 131072. That fits the sending frame, the receiving frame stash on the in-JVM inbound side, one more frame in flight, and a 64 KiB Netty read buffer. So the pool holds a few frames, each of LMT, per in-JVM link: that is, it follows LMT with a small multiple.]
   - (ii) **Unit pendingPeak depends on the method's position in the JVM, not on V.** The first method held C + R − 152 because its first connect had not yet failed when it filled. The third held C − 400 because the link was failing to connect, so there was no reserve. Both are inside B2f's band. The S4-A3 expectation "≤ C" is missed in the first method [observed].
   - (iii) **Cluster UsedSize is flat at ~85–127 KB in every stalled run**, the control included, and its run-to-run scatter (43 KB at V = 16384) is larger than its across-V span (5 KB) [observed]. [inferred: 1 s samples of a shared pool (native transport included) at this resolution cannot separate one frame of 16 vs 128 KiB. The < 0.5 MiB band is passed by a wide margin, but the tier does not resolve a one-frame effect.]
   - (iv) **The live-heap outlier** v16k-2 (546.6 MB) is unexplained. No row uses heap; the control's sub-prediction holds against the V = 65536 runs used by S4-A8 [observed].
3. **Matched rows.**
   - **Unit: U9**, applied in S4-A4's order.
     - Validity rows: U5 (no maxFrame below its band, `sent = accepted`), U7 (`errors` 0) and U8 (poolPeakDelta ≥ maxFrame) do not hold.
     - Refuted rows: U2 (pendingPeak medians identical) does not hold. U3 does not hold: the medians increase with V, but 458,752 − 106,496 = 352,256 B is not > 1 MiB.
     - U4 (C = 1 MiB is 3.18 MB below) and U6 (no maxFrame above its band) do not hold.
     - **U9 holds:** "The poolPeakDelta medians span ≥ 300 KiB … without U3's condition". The span is 344 KiB ≥ 300 KiB, and U3 is not met [observed: `selfcheck-unit.out` "UNIT VERDICT ROW: U9"].
     - U1 therefore cannot be reached. Its only failing part is "poolPeakDelta medians span < 300 KiB". Its other four parts hold.
   - **Cluster: C1**, applied in S4-A9's order. C4 and C5 hold for no run. C2 holds for no observable (no monotone increase > 1 MiB). C3 and C6 hold for no run. All five bands of C1 hold:
     - every main pending peak is 3,145,417 ∈ [2,831,155, 3,147,776];
     - the pending span is 0 % (< 5 %);
     - the UsedSize span is 5,152 B (< 0.5 MiB);
     - the direct span is 13,946.5 B (< 1 MiB);
     - each control peak is 33,553,595 ∈ [30,198,989, 33,556,480] [observed: `analyze-summary.txt`, `selfcheck-cluster.out` "CLUSTER VERDICT ROW: C1"].
4. **Excluded rows.**
   - **Unit:** listed in part 3, each with its reading. Of the two Refuted rows:
     - U2 is excluded by identical per-V pendingPeak medians (4,226,796);
     - U3 is excluded because the increase is 344 KiB, not > 1 MiB.
   - **Cluster:**
     - **C2 (Refuted):** excluded for pending (span 0), UsedSize (16384 > 65536 > 131072, not increasing; span 5 KB) and direct (not monotone; span 14 KB).
     - **C3:** excluded; the minimum main peak is 3,145,417 ≥ 0.9 × 3 MiB, and the control peak is 33,553,595 ≥ 0.9 × 32 MiB.
     - **C4:** excluded; 0 DOWN lines inside any stall.
     - **C5:** excluded; 0 frame errors.
     - **C6:** excluded; the maxima are 3,145,417 ≤ 3 MiB + 2 KiB and 33,553,595 ≤ 32 MiB + 2 KiB.
     - **C7:** excluded; all bands met.
5. **Observed vs. inferred.**
   - The matched rows depend only on observed numbers.
   - Two inferred statements explain readings but are not used by either row:
     - (2.i) the composition of the ~3.5 frames held at V = 131072;
     - (2.iii) that the cluster's 1 s UsedSize samples cannot resolve a one-frame effect.
6. **Deviations and gaps.**
   - Loopback on one host: n1, n2 and stress share 40 cores.
   - The `testsome` JVM wrote its test data under the harness copy (§3 note).
   - Per-frame sizes and `flushingBytes` are not observable on the node (B3d, as filed).
   - The unit pool reading includes the in-JVM inbound side of the same link.
   - The unit pendingPeak cannot depend on LMT by construction (R12).
   - The heap sub-prediction uses one live histogram per lifetime (S4-A8).
   - Run 1 values only; no run 2.
7. **Core question.**
   - **Cluster tier:** usage does not follow the knob. With LMT varied 8× (16 → 128 KiB), the queued bytes on the stalled link stayed at exactly 3 MiB − 311 B, and the networking pool and direct memory moved by < 14 KB across V. Meanwhile the send-queue cap moved the queue to 32 MiB and the live heap by +273 MB (parts 1, 3, 4). So `OTCP_LARGE_MESSAGE_THRESHOLD` does not cap the node's outbound memory, and the send-queue capacity does.
   - **Unit tier:** the mechanism is confirmed exactly. maxFrame is the largest multiple of S that fits `roundUp(LMT+10, 2048) − 10`, and queued bytes are set only by C (parts 1, 3). But the in-JVM pool peak grew by 344 KiB across V, about 3 frames of LMT rather than the ≤ 300 KiB the frozen table allowed. So the unit tier lands on its "pool band missed" row, not on Confirmed (part 3).

**Conclusion (one line):** unit B2g row U9: **Not confirmed** (pool band missed; the mechanism and the queued-bytes clauses hold). Cluster B3g row C1: **Confirmed** (does not cap).

**Sub-predictions (B2f/B3f, with S4-A3, S4-A8):**
- **Met:**
  - Unit: maxFrame bands; frames ≈ 256/64/32; pendingPeak in [C − S, C + R]; overflowDelta 0; errors 0 and sent = accepted; poolPeakDelta ≥ maxFrame; the S4-A3 pool bound at V = 16384 and 65536.
  - Cluster: pending ≈ 3 MiB at every V with spread < 5 % and drops growing; control ≈ 32 MiB (+29 MiB); live heap +272.7 MB ≥ 29 MB; UsedSize spread < 0.5 MiB; direct spread < 1 MiB (no 8 MiB step); OverflowSize 0.
- **Missed:**
  - the S4-A3 per-reading pool bound at V = 131072 (458,752 > 397,270);
  - the S4-A3 expectation pendingPeak ≤ C, in the first method of each JVM (4,259,688);
  - the filed B2f spread "< about 300 KiB" (344 KiB). This is the U9 trigger.

## 5. Self-check of run 1 — AI

[`run1/selfcheck.py`](OTCP_LARGE_MESSAGE_THRESHOLD-doRun-maxSendBytes--autonomous/run1/selfcheck.py) has its own parser. It does not import the harness's analysis.
- **Unit:** it re-reads the 27 RESULT lines and applies U1–U9 in S4-A4's order.
- **Cluster:** on `pc06` it re-reads every lifetime's raw `jmx.csv`, `times.json`, `n1-cassandra.yaml`, `n1-system.log` and `stress.log`, recomputes the stall window and baseline, and applies C1–C7 in S4-A9's order.

**Results:**
- [`selfcheck-unit.out`](OTCP_LARGE_MESSAGE_THRESHOLD-doRun-maxSendBytes--autonomous/run1/selfcheck-unit.out): 13/15 checks pass, verdict row **U9**. The two FAILs are the recorded sub-prediction misses.
- [`selfcheck-cluster.out`](OTCP_LARGE_MESSAGE_THRESHOLD-doRun-maxSendBytes--autonomous/run1/selfcheck-cluster.out): 2/2 checks pass, verdict row **C1**. Its per-run numbers equal the harness's `summary.json` to the byte.

### 5.1 Check of run 1's conclusion

| Part | Holds? | Note (file re-read) |
|---|---|---|
| 1. Validity | yes | `all-results.txt`: `lmt`, `sent`, `errors`, `overloaded` re-read in all 27 lines. Cluster: the yaml lines re-read per lifetime; `times.json` property flags; `n1-log-grep.txt` shows the single DOWN after SIGCONT/stop time, e.g. v128k-1 08:39:23 UTC against `cont` 08:38:19 |
| 2. Readings | yes | medians and spans recomputed by `selfcheck.py` (352,256 B; 0 / 5,152 / 13,946.5 B); the dip to 3,106,086 and the timeout count re-read in `v128k-1/jmx.csv` |
| 3. Matched row | yes | U9's condition and U3's non-condition recomputed; C1's five bands recomputed |
| 4. Excluded rows | yes | each row's excluding reading recomputed in the row order of S4-A4/S4-A9 |
| 5. Observed vs. inferred | yes | neither matched row uses (2.i) or (2.iii) |
| 6. Deviations and gaps | yes | none reverses a reading; the shared host is recorded |
| 7. Core question | yes | cluster: B1's two falsifiers (pending or pool/direct following LMT by ≫ 2·ΔLMT) are both absent, and the control moved. Unit: the frozen table's own row governs. The pool growth is reported as observed (about 3 frames, < 0.5 MiB), not re-interpreted into a Confirmed |

### 5.2 Run 2?

**No**, decided 2026-10-22. Both verdicts rest on observed readings only.
- **Unit:** the readings are deterministic and repeated three times per V. maxFrame and pendingPeak are identical across repeats, and the pool medians come from six values each.
- **Cluster:** two repeats per value agree, pending to the byte. The result neither refutes the file nor confirms a bypass.

## 6. Run 2 — fresh AI session (optional)

Not done (§5.2).

## 8. Verdict — AI

Jingsong may overrule any verdict at any time; an override is recorded here with its date and reason.

**Stage-3 estimate:** negative.

**Claim tested (B1):** "Varying `cassandra.otcp_large_message_threshold` (16384 / 65536 / 131072) changes the size of each small-connection frame buffer, roughly in proportion to LMT. It does **not** change how much outbound internode memory a node holds:
- peak queued bytes (`pendingBytes`, heap) stay at the send-queue capacity limits;
- peak networking-pool usage (off-heap) differs across those LMT values by less than about one LMT per backlogged connection.

Changing the send-queue capacity, under the same workload, does move both."

"Confirmed" below always means this claim held.

| Tier | Verdict (B2g / B3g row) | Effect on the constraint | Basis | Date |
|---|---|---|---|---|
| Unit | **Not confirmed** — B2g row U9 (S4-A4): pool band missed. These clauses hold: maxFrame = 16,224 / 64,896 / 130,806 B, which follows LMT exactly; pendingPeak per-V medians identical (4,226,796 B); C = 1 MiB 3.18 MB lower. The in-JVM pool peak medians are 106 / 262 / 459 KiB, a span of 344 KiB against the frozen < 300 KiB, with every reading < 0.5 MiB | **undetermined** (observed: queued bytes set by C only; the pool follows LMT by about 3 frames, < 0.5 MiB) | run 1 + self-check | 2026-10-22 |
| Cluster | **Confirmed** — B3g row C1 (S4-A9): pending peak 3,145,417 B at every V in both repeats (span 0); UsedSize Δ span 5,152 B; direct Δ span 13,946.5 B; OverflowSize 0; control 33,553,595 B in both repeats | **does not cap** | run 1 + self-check | 2026-10-22 |

**Positive control:** the send-queue capacity (with S4-A6's endpoint reserve), a cap confirmed binding by the closed acquire case.
- **Unit:** C = 1 MiB gave pendingPeak 1,048,476 B against a 4,226,796 B median at C = 4 MiB, with `overloaded=1` in every line.
- **Cluster:** C 16 / E 16 / G 32 MiB gave 33,553,595 B against 3,145,417 B, and the live heap rose by +272.7 MB.

**Feedback filed:** the case file's section D, updated 2026-10-22 (not committed). It covers the verdicts, S4-A1 to S4-A11, runbook defect 1, the missed sub-predictions, R12 and R13 for stage 3, and the overlap with the send-queue cases. No other section was amended after the freeze. sha256 values:
- as filed: `d33cf167…`;
- after the audit (the version run): `6b3a899e…`;
- **after section D: `f63b40250494cfb25d116e3fab952c0e09064234b3144e75496df307a7929884`**. Only section D differs from `6b3a899e…`: replacing D with "none yet" reproduces that hash.

**Node state after the run:** on `pc06`, no `java` process and no stopped process; ports 7000/7199/7299/9042/7012 are free; node data removed. `~/stage4-otc/n{1,2}/{conf,logs*}` (51 MB) and `~/stage4-logs/otc/` (57 MB) are kept, and `~/cassandra-otc` is clean (`git status` empty).
