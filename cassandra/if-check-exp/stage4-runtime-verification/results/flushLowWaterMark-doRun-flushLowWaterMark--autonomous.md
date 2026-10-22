# flushLowWaterMark-doRun-flushLowWaterMark--autonomous — stage-4 results  <!-- file: results/flushLowWaterMark-doRun-flushLowWaterMark--autonomous.md -->

> **Case:** [`flushLowWaterMark-doRun-flushLowWaterMark--autonomous`](../../stage3-ai-deep-read/cases/flushLowWaterMark-doRun-flushLowWaterMark--autonomous.md)
>
> **Status:** **Verdict filed 2026-10-22, run 1 + self-check, no run 2.**
> - **Unit: Not confirmed (no matching row) — Effect undetermined.**
> - **Cluster: Not confirmed (B3g/A10 row 5) — Effect undetermined.**
>
> At both tiers, every reading of the in-flight bytes and of the pool memory is flat across `flushLowWaterMark`, while the positive control (H) moves them:
> - **Unit:** S spread 22,858 B and U spread 45,056 B over L = 1 KiB … 1016 KiB at H = 1 MiB; the P-set tracks H with ratio 64.1.
> - **Cluster:** D = 116.65 / 116.45 / 116.33 MiB at L = 1 KiB / 32 MiB / 63 MiB, against 7.19 MiB at H = 4 MiB.
>
> The low mark acted as traced at both tiers: every resume level ≤ L, and the knob was read back in the running code. Neither tier reaches the frozen Confirmed row, because one frozen magnitude prediction missed at each tier:
> - **Unit:** the Netty measure N counts 96 B per frame, not bytes. Cassandra installs `NoSizeEstimator`, so the A3 bound N ≥ S fails in 9 of 9 P-set runs.
> - **Cluster:** D is ≈ 1.82 × H, not H + one frame, so every V1–V3 lifetime is outside [64, 70] MiB. Inferred cause: frames of one ~2.1 KiB mutation, each rounded up to whole 2 KiB pool units.
>
> Audited 2026-10-22 (estimate negative). Run on `pc13`.
>
> **Agent:** autonomous. "§9a" below means each tier's predictions and conclusions table: B2f and B2g (unit), B3f and B3g
> (cluster), with the audit's amendments A3/A4 and A9/A10; "§9b–§9e" means B2a–B2e or B3a–B3e; the case file's feedback
> section is its section D.

## 1. Before run 1 — design audit and freeze

| Field | Content |
|---|---|
| **Case-file version** | Autonomous file, untracked in the working tree (no commit holds it; not committed, per the session's instructions). sha256 **as filed: `16b0da55a6454033fd77d712e0e921f2d331565af0dd9d9f6c6dc538f84295e9`**. **After the audit's amendments A1–A11, before any harness run or reading (the frozen design): `f754e36f8f7ab5edc281986809cf4291722348b29f732ba63c7ed0f7a8bcf69d`**. The unit tier ran against this version. **After runbook defects 1–2** (dated amendments next to B3a and A8, found in step-1 shakedowns before any counted cluster reading; B3f/B3g unchanged): **`b797d658c074694d4e0ed46386f63d414f519fb3f23f87840c1f57c0c864fb98`**. The cluster tier ran against this version. The final sha256 after section D is in §8. |
| **Harness** | [`harness/flushLowWaterMark-doRun-flushLowWaterMark--autonomous/`](../harness/flushLowWaterMark-doRun-flushLowWaterMark--autonomous/), written 2026-10-22 (step 1), not committed. The md5 of every file as run on `pc13` is in `run1/unit/harness-md5.txt` and `run1/cluster/harness-md5-cluster.txt`. **Instrument checks:** the unit `handshake` check (`run1/step1/handshake.txt`); the Byteman `TestScript` type check of both rule versions; the build check of the five jars (`run1/step1/build-variants.log`); and four cluster shakedowns (`run1/shakedown/`), two of which found runbook defects 1 and 2 (§3). |
| **Tiers and values** | **Unit (B2):** S0 (stock H 64 KiB / L 32 KiB, no reflection); L-set at H = 1 MiB with L = 1024 · 32768 (default) · 524288 · 1040384; P-set (positive control) with H = 64 KiB · 1 MiB · 8 MiB and L = H/2. Three repetitions of each, 24 runs. **Cluster (B3):** patched builds V0 (stock 64 KiB / 32 KiB), V1 (H 64 MiB, L 1 KiB), V2 (64 MiB / 32 MiB), V3 (64 MiB / 63 MiB), V4 (positive control, 4 MiB / 2 MiB). Two lifetimes each, interleaved, 10 lifetimes. |
| **Environment deviation** | Paths are `pc13:~/cassandra-flw{,-p1..p4}`, `~/stage4-flw`, `~/stage4-logs/flw` in place of `/tmp/fwm` (A1, A5, A11). Node data is on a 40 GiB tmpfs. Both nodes share `pc13`'s 40 cores with the stress client, as B3a provides. |
| **Audit bottom line** | **Ready after amendments** — 2026-10-22 |

### 1.1 Design audit

Checked against the pinned clone `/proj/misconfiguration-PG0/git-repos/cassandra-src` (`cassandra-5.0.9`) and the run clone
`pc13:~/cassandra-flw` (`b5f2a54`). Read in context:
- `OutboundConnection.java`: 295–320 (constructor, `withDefaults`), 560–730 (`Delivery`: `execute`, `executeAgain`, `promiseToExecuteLater`, `run`), 730–915 (`EventLoopDelivery.doRun` and its listener), 1120–1135 and 1205–1215 (Established settings).
- `OutboundConnectionSettings.java`: 80–150 (line 104's literals), 250–262 (`withNettyBufferBounds`), 440–480 (`withDefaults`).
- `OutboundConnections.java:62–70` (`LARGE_MESSAGE_THRESHOLD` = 65515); `FrameEncoder.java:25–140` (payload allocation, `putUnusedPortion`).
- `BufferPool.java`: 128–132 (units), 195–300 (`usedSizeInBytes` = `memoryInUse` + overflow); `BufferPools.java`; `BufferPoolMetrics.java`.
- `OutboundDebugCallbacks.java`; `StorageService.onDead` → `interruptOutbound` (3884–3890); `InternodeOutboundTable.java` (columns); `InboundConnectionInitiator.java:175, 234–258`.
- `cassandra.in.sh` (the jar on the class path); `build.xml` (`test.timeout` 480000, `test.methods`, `test.jvm.args`, `debuglevel` vars).
- `ProxyHandlerConnectionsTest`, `ConnectionTest` (harness idioms).

| Group | Check | Rating | Note (section checked) |
|---|---|---|---|
| A. Core question | constrained quantity is memory or disk bytes | Met | A2/B1: the Netty-held frame buffers of the networking `BufferPool` (off-heap), compared through `flushingBytes` |
| A. Core question | knob varied, ≥ 3 values incl. default — or another approach | Met | Hard-coded, so reflection in the unit tier and patched builds in the cluster tier, as the file says. Unit: L at 4 values including the default 32 KiB, plus stock S0. Cluster: V0 stock plus V1–V3 |
| A. Core question | real resource measured, not only the counter | Met | U (pool `usedSizeInBytes`) and N (Netty) in the unit tier; `UsedSize` and direct memory in the cluster tier. **Not caught in the audit:** N is blind (`NoSizeEstimator`, §4.2 part 2) |
| A. Core question | usage driven to the limit and past it | Met | B2c E = 2H + 2 MiB > H + frame + kernel. B3c needs only ~30k mutations, but `n=400000` unthrottled could end before the freeze (**A6**) |
| A. Core question | positive control (negative estimate) | Met | P-set (unit) and V4 vs V2 (cluster) move H on the same workload |
| B. Logic | each step says what it establishes | Met | B2h/B3h |
| B. Logic | prediction stated in numbers or a clear relation | **Partly** | Numbers were given, but "no monotone trend", "N and U follow H the same way" and "flat for 5 s" had no rule. Amended **A3** (trend on per-L medians above one frame; N/U bounds for the P-set; S0 is a baseline), **A7** (fixed windows) and **A9** (how D is judged) |
| B. Logic | every plausible outcome has a conclusions row | **Partly** | No verdict words; no rows for an incomplete delivery, a U-only miss, a guard that did not fire, or (cluster) D flat but off-size, D noisy, or a knob read-back mismatch on the node. Amended **A4** and **A10** (rows applied in order, with a final "no matching row") |
| B. Logic | confirmation needs ceiling-follows-knob and direct disallow evidence | **Partly** | Unit: R ≤ L is direct evidence. Cluster: only the jar check, no per-link evidence that the stall was at H or that the resume was at ≤ L. Amended **A8/A9** (Byteman STALL/RESUME with the running knob values) |
| B. Logic | alternative explanations and their controls | Met | `P > S`, template read-back, CRC framing, 10-minute expiry, `pending_bytes`, connection-reset row |
| C. Specific | a human can follow it from the intro and B1 | Met | |
| C. Specific | an AI can run B2e/B3e without re-deriving the code path | **Partly** | The skeleton's R rule misses every flip that happens in the first listener after a stall, which is every flip when H − L < one frame (S0, L = 1040384). Amended **A2**. The proxy-vs-fallback choice is settled in step 1 (**A1**) |
| C. Specific | knob, values, workload, commands, observables, sampling, stop conditions exact | **Partly** | `nodetool sjk` cannot sample every 500 ms (**A7**). The 480 s test timeout is too short for 24 configurations (**A1**). Paths, process matching, tmpfs (**A5**, **A11**) |
| D. Runnable | harness and environment prerequisites exist or are listed | Met | Skeleton given; Byteman and the in-tree driver are available after `ant build-test` |
| D. Runnable | workload arithmetic reaches the limit | Met | Unit: up to 18 MiB per run on a 1 GiB test JVM; the pool threshold is 62 MiB. Cluster: 64 MiB in flight + 132 MiB queue on a 4 GiB heap; the networking pool limit is 128 MiB; about 5 GB of data per lifetime on the tmpfs |
| D. Runnable | load-bearing citations spot-checked | Met | `:766`, `:851`, `:854`, `:857`, `:866–:867`, `:871–:873`, `:881`, `OutboundConnectionSettings.java:104` (the grep pattern matches line 104), `withDefaults` copying the fields, `Established.settings` from `template`. **Not caught:** `OutboundConnectionInitiator.java:197` (`NoSizeEstimator`) |

| # | Recommendation | Applied? | Why |
|---|---|---|---|
| A1 | Clone and paths on `pc13`; `-Dtest.timeout=1800000`; CSV path; proxy-vs-fallback decided in step 1 | applied 2026-10-22 (B2a) | execution detail; 24 configurations exceed 480 s |
| A2 | R instrument: listener detected from the call stack, inferred pre-listener `isWritable`, counters for flips, guard misses and inference errors, resume-send levels | applied (B2d) | the skeleton's rule records no R when H − L < one frame |
| A3 | Spread over 12 runs; trend on per-L medians, counting only ≥ 65536 (S, N) or ≥ 262144 (U); N = S + k·106; P-set N ∈ [S, S + 65536), U ∈ [S, S + 262144]; S0 a baseline | applied (B2f) | the relations had no rule. **The N formula was wrong (found by a reading, §4.2); left as frozen** |
| A4 | Verdict words for B2g's rows, applied in order; rows for an incomplete run, a guard miss, inference errors, S ≥ H + 65536, a U-only miss, and "no matching row" | applied (B2g) | README group B |
| A5 | Variant trees, deleting the class files before `ant jar`, `javap`; tmpfs; per-lifetime conf; `JMX_PORT`; `ulimit`; daemon matching | applied (B3a) | execution detail and lessons |
| A6 | Stress `duration=60s fixed=20000/s` | applied (B3c) | `n=400000` unthrottled can end before t = 15 s |
| A7 | Persistent JMX poller at 500 ms; vt and `ss` every 2 s; fixed pre/plateau windows; D per lifetime and per-variant mean | applied (B3d) | `sjk` too slow; "flat for 5 s" had no rule |
| A8 | Byteman STALL/RESUME observation on A | applied (B3d) | direct per-link and knob read-back evidence (group B) |
| A9 | Predictions for the knob read-back, stall levels and resume levels; how D is judged | applied (B3f) | group B |
| A10 | Verdict words and rows for B3g, applied in order: invalid, never reached / control, refuted, mechanism, **D flat but off-size**, noise, confirmed, no matching row | applied (B3g) | group B |
| A11 | Paths, process check, clean-up | applied (B4) | execution detail |
| R12 | Netty's `totalPendingWriteBytes` cannot measure Cassandra's in-flight bytes (`NoSizeEstimator`, `OutboundConnectionInitiator.java:197`); N should be dropped or predicted as `k × 96` | **left for stage 3** (section D) | found from readings, so not applied (HARD RULE) |
| R13 | B3f's D = H + one frame assumes full 64 KiB frames. Under per-message delivery each ~2.1 KiB mutation is its own frame, in a buffer rounded up to 2 KiB units, so D ≈ 1.8 × H (inferred). Predict D as the pool's rounding of the frames, or measure the frame count | **left for stage 3** (section D) | found from readings, so not applied |

**Agreement criteria:** not filled (no run 2, §5.2).

## 2. Environment

| Field | Run 1 |
|---|---|
| Date | 2026-10-22 UTC. Audit frozen 08:21. Step-1 handshake 08:23. Unit run 1 08:24–08:25:36. Variants built 08:27–08:28. Shakedowns 08:28–08:43 (`shakedown1`, `diag1`, `diag2`, `diag3`). Cluster run 1 08:44:09–09:14:43. Self-check after. |
| Node | `pc13` = `node3.jason92-320876.misconfiguration-pg0.cloudlab.umass.edu`: 40 cores, 251 GiB, driven over SSH from `pc07`. Cluster: A 127.0.0.1 (JMX 7199, Byteman), B 127.0.0.2 (JMX 7299), both on this host |
| OS and kernel | Ubuntu 22.04.2, `5.15.0-187-generic` |
| JDK | OpenJDK 11.0.32.1. Unit: the `testsome` JVM, 1 GiB (networking pool threshold 65,011,712 B). Cluster: G1, `MAX_HEAP_SIZE=4G`, `HEAP_NEWSIZE=800M` |
| Ant | 1.10.12 |
| Local clone | `pc13:~/cassandra-flw`, cloned from `~/cassandra-run1` at `cassandra-5.0.9` (`b5f2a54210d541339c2e7c17a794195cac0e67c2`); `ant build-test` in 1 min 7 s. The test file was copied in and removed afterwards (`git status` clean). V1–V4 were `~/cassandra-flw-p1..p4` (copies plus the line-104 `sed` and `ant jar`), removed after the run |
| Case-file commit / harness commit | none (untracked); sha256 values in §1; harness md5 values in `run1/*/harness-md5*.txt` |
| Storage for node data | tmpfs `pc13:~/stage4-flw/nodes` (40 GiB), wiped per lifetime and unmounted at the end; node conf and logs in `~/stage4-flw/{A,B}/` |
| Full logs | `pc13:~/stage4-logs/flw/` (19 MB): `step1-handshake/`, `run1-unit/`, `build-variants/`, `shakedown1/`, `diag1/`, `diag2/`, `diag3/`, `run1/` (per lifetime: `jmx.csv`, `vt-out.csv`, `ss.txt`, `flw.trace`, `stress.log`, both nodes' `system.log`/`debug.log`, yamls, `session.log`, `summary.txt`, `readings.json`). Excerpts are in [`run1/`](flushLowWaterMark-doRun-flushLowWaterMark--autonomous/run1/) |

## 3. Runbook defects

| # | Run | Step | Problem | Fix | Decision (date) | Case-file version with the fix |
|---|---|---|---|---|---|---|
| 1 | step-1 cluster shakedown (`shakedown1`; V0, 20 s stress, no freeze; not a reading) | B3a (the 4 KiB socket buffers) | A's small link to B drained about 17 KB/s under load: `sent_bytes` +33.5 KB per 2 s, 400k expiries, Small `PendingBytes` held at ≈ 84.7 MB *without any freeze* (`run1/shakedown/shakedown1/excerpt.txt`). B's 4 KiB receive window throttles the sender to zero-window probing. With the link saturated before the freeze, `flushingBytes` would sit at H in the pre window too, and D (plateau − pre) could not show H | drop both 4 KiB buffer lines (kernel defaults). `diag1` (same stress, no freeze): Small `PendingBytes` ≤ 4.2 KB and `UsedSize` ≤ 8 KB | dated amendment next to B3a, 2026-10-22; B3f/B3g unchanged; before any counted cluster reading | `b797d658…` |
| 2 | step-1 cluster shakedown (`shakedown1`, `diag2`; not readings) | B3d/A8 (the STALL rule) | `AT LINE 857` printed STALL levels of 0 and of one frame (63,554), below H, and RESUME levels above L. The `diag2` rules at 854 and 857 printed `canon=0 sending=0`. Byteman injects at the first bytecode whose line is ≥ n; in `doRun` that is the inlined `finally` (line 902, offset 104, an early-return path) (`javap -l`; `run1/shakedown/diag2/`) | `AFTER INVOKE promiseToExecuteLater`: the only call in `doRun` (offset 641), inside the stall branch. `diag3` (V0 with a freeze): 25 STALLs at 67,552–130,882 B, all in [H, H + 65536); every RESUME 0 | dated amendment next to A8, 2026-10-22; B3f/B3g unchanged; before any counted cluster reading | `b797d658…` |

The unit tier ran once, as written, with no defect. The proxy check of step 1 passed, so the fallback was not used. The cluster tier ran once after the two fixes, with no further defect.

## 4. Run 1

**Scope:**
- **Unit tier:** complete, 24 runs in one `testsome` JVM (97 s).
- **Cluster tier:** complete, 10 lifetimes, each with `cassandra-stress write duration=60s` at a fixed 20,000/s through A, RF 2, CL ONE, 2,048-byte values. B was SIGSTOPped at t0 + 15 s and SIGCONTed at t0 + 40 s.

**Command logs:**
- `run1/unit/unit-run.log` and `run1/unit/probe-lines.txt`
- `run1/cluster/run1-chain.log`
- per lifetime, `run1/cluster/<V>-r<rep>/summary.txt`

### 4.1 Readings

**Unit tier** (`run1/unit/unit.csv`; the independent re-parse is `run1/unit/selfcheck-unit.out`)

| Test or assertion | Result | Evidence |
|---|---|---|
| Step-1 handshake through the TCP proxy | delivered; the channel's remote is the proxy port; template and established (H, L) = (65536, 32768); CRC framing | `run1/step1/handshake.txt` |
| Read-back (A4 row 1) | template and established (H, L) equal the set values in 24/24 runs | `unit.csv` cols `templateH..establishedL` |
| Delivery integrity | `failed` 0, handled = enqueued (2,176 / 4,096 / 18,432) in 24/24 runs | `unit.csv` |
| Stall reached | `isWritable` false at the stable point in 24/24 runs; P > S in 24/24 | `unit.csv` |
| **L-set S** (H = 1 MiB) | L = 1024: 1,061,874 · 1,064,975 · 1,081,599. L = 32768: 1,061,874 · 1,069,131 · 1,075,365. L = 524288: 1,061,874 · 1,060,819 · 1,083,677. L = 1040384: 1,068,102 · 1,062,897 · 1,062,897. All in [1,048,576, 1,114,112). Spread over the 12 runs is **22,858 B**. The per-L medians (1,064,975 · 1,069,131 · 1,061,874 · 1,062,897) are not monotone | `unit.csv`, `selfcheck-unit.out` |
| **L-set U** (pool delta) | per-L medians 1,085,440 · 1,093,632 · 1,081,344 · 1,081,344 (not monotone); spread over the 12 runs **45,056 B** (< 262,144) | same |
| L-set N | 1,632 in all 12 runs (spread 0) | same |
| **P-set S** (positive control) | H 64 KiB: 89,354 · 85,198 · 130,914. H 1 MiB: 1,071,209 · 1,070,170 · 1,067,053. H 8 MiB: 8,396,159 · 8,412,783 · 8,401,354. All in [H, H + 65536). Worst-case ratio S(8 MiB)/S(64 KiB) = **64.13** (≥ 64) | same |
| P-set U | U ∈ [S, S + 262144] in 9/9 (e.g. 8,425,472 against S 8,396,159) | same |
| **P-set N** | **192 / 1,632 / 12,384 at H 64 KiB / 1 MiB / 8 MiB, = 2 / 17 / 129 × 96 B, so N < S in 9/9** (the A3 bound N ∈ [S, S + 65536) fails) | same |
| R (flip levels, A2) | L = 1024 and 32768: every R = 0. L = 524288: R = 523,152 or 523,656. L = 1040384: R 980,910 … 981,855, median of medians 981,855 (> 524,288). S0: max R 0 / 5,195 / 0. P-set: max R 11,429 / 15,585 / 0 (H 64 KiB), 523,656 (1 MiB), 4,189,248 (8 MiB). **max R ≤ L in 24/24 runs**; flips 3–25 per run | same |
| Mechanism counters | guard misses 0, inference errors 0, `sendNotWritable` 0; no L/P run with S ≥ H + 65536 | `unit.csv`, `probe-lines.txt` |
| S0 baseline (B2f) | S 130,665 / 95,588 / 103,900 (in [65536, 131072)); U 131,072 / 126,976 / 143,360 (in [S, S + 262144]); P > S; R ≤ 32,768. **N = 192, not in [S, S + 4096]** | same |

**Cluster tier.**
- D = median(`UsedSize`, [pause + 10, pause + 22] s) − median(`UsedSize`, [pause − 11, pause − 1] s), 20 and 24 samples.
- The run's own analysis is in `run1/cluster/analyze/summary.txt`; the independent re-parse is in `run1/cluster/selfcheck-cluster.out`.
- In every lifetime: stress ran at 19.8–19.9 k op/s with 0 errors; `active_connections` = 3 throughout the freeze; there was no `is now DOWN` and no `Interrupted outbound connections`; and A logged 0 `ERROR` lines.

| Variant (H, L) | Lifetime | D | D_direct | STALL lines: (H, L) read back; levels | Small-link STALL in the freeze (level) | RESUME levels (max) | Pending during the freeze (max) |
|---|---|---|---|---|---|---|---|
| V0 (64 KiB, 32 KiB) | r1 | 69,648 B (0.066 MiB) | 0.221 MiB | 32 lines; (65536, 32768); 67,552–130,882 | 1 (67,552) | 32, max 0 | 83.0 MiB |
| V0 | r2 | 69,568 B (0.066 MiB) | 0.223 MiB | 36; same; 67,552–130,882 | 1 (67,552) | 36, max 0 | 81.1 MiB |
| V1 (64 MiB, 1 KiB) | r1 | **116.467 MiB** | 120.279 MiB | 1; (67108864, 1024); 67,110,801 | 1 (67,110,801) at pause + 1.8 s | 1, 0 | 132.0 MiB |
| V1 | r2 | **116.834 MiB** | 120.324 MiB | 1; same; 67,110,801 | 1 (67,110,801) | 1, 0 | 132.0 MiB |
| V2 (64 MiB, 32 MiB) | r1 | **116.221 MiB** | 120.312 MiB | 1; (67108864, 33554432); 67,110,801 | 1 (67,110,801) | 1, 2,233,438 | 132.0 MiB |
| V2 | r2 | **116.684 MiB** | 120.317 MiB | 1; same | 1 (67,110,801) | 1, 2,214,439 | 132.0 MiB |
| V3 (64 MiB, 63 MiB) | r1 | **116.215 MiB** | 120.307 MiB | 1; (67108864, 66060288); 67,110,801 | 1 (67,110,801) | 1, 41,255,273 | 132.0 MiB |
| V3 | r2 | **116.439 MiB** | 120.279 MiB | 1; same | 1 (67,110,801) | 1, 41,039,951 | 132.0 MiB |
| V4 (4 MiB, 2 MiB) | r1 | **7.260 MiB** | 56.304 MiB | 25; (4194304, 2097152); 4,196,668–4,253,665 | 1 (4,196,668) | 25, max 2,028,671 | 88.4 MiB |
| V4 | r2 | **7.111 MiB** | 64.252 MiB | 25; same; 4,198,779–4,253,665 | 1 (4,198,779) | 25, max 1,897,789 | 93.7 MiB |

**Per-variant means:** V0 0.066 · V1 116.650 · V2 116.452 · V3 116.327 · V4 7.186 MiB.
- V1–V3: the largest pairwise difference is **0.323 MiB**. The means fall monotonically with L, but within 4 MiB, so they are not "ordered by L" (A9).
- D(V2) − D(V4) = **109.27 MiB**.
- No V1–V3 lifetime is in [64, 70] MiB; both V4 lifetimes are in [4, 8] MiB; D(V0) < 1 MiB.

**Where the plateau comes from.** V1-r1's `UsedSize` reaches 122,124,288 B by pause + 2.2 s and stays within 4 KB of it until SIGCONT (`run1/cluster/V1-r1/jmx.csv`). That is exactly 59,631 pool units of 2 KiB. Against it:
- the stall level is 67,110,801 canonical bytes;
- the vt's `pending_bytes / pending_count` is 2,111 B per message, so the in-flight bytes are ≈ 31,791 messages;
- the ratio is 1.82, and V4's is 1.80 (7.19 MiB against 4 MiB).

### 4.2 Conclusion and logic

1. **Validity.** Both tiers are valid.
   - **Unit:**
     - The knob was applied: read back from the template and from the established settings in 24/24 runs [observed: `unit.csv`].
     - Every run stalled, with P > S [observed].
     - Every message was delivered after the resume, with no failed frame [observed].
     - The proxy was in the path [observed: `step1/handshake.txt`].
   - **Cluster:**
     - The patched constants are in each jar [observed: `step1/build-variants.log`] and in the running connections (every STALL line's (H, L) is the variant's) [observed: `flw.trace` ×10].
     - The limit was reached: a small-link STALL to 127.0.0.2 at H + one frame inside every freeze, with pending up to 132 MiB [observed].
     - No connection was reset [observed: vt `active_connections`, `A-system.log`].
     - B3a's hold-fixed settings are in the yaml diffs [observed: `A-yaml.diff`, `B-yaml.diff`], minus the 4 KiB buffers (defect 1).
2. **Readings.** Two magnitude readings differ from the frozen predictions.
   - **Unit N.** N = 96 B × (frames in flight) in every run [observed: `unit.csv`, 192 = 2 × 96, 1,632 = 17 × 96, 12,384 = 129 × 96]. Cassandra's outbound bootstrap sets `MESSAGE_SIZE_ESTIMATOR` to `NoSizeEstimator`, whose `size()` returns 0 (`OutboundConnectionInitiator.java:197`, `NoSizeEstimator.java`), so Netty counts only its per-entry overhead [observed: source]. N cannot be ≥ S by construction. A3's P-set bound and the S0 baseline bound on N therefore fail.
   - **Cluster D.** D(V1–V3) ≈ 116.4 MiB ≈ 1.82 × H, not H + one frame [observed]. The stall itself is at H + 1,937 B [observed: STALL 67,110,801]. The inferred cause is pool rounding of small frames: before H is reached, delivery runs once per enqueue, so a frame typically holds one ~2,111 B message (2,121 B with the CRC header and trailer), and `putUnusedPortion` frees only whole 2 KiB units, leaving 4,096 B (or 6,144 B for two messages) per frame. For 31,791 messages, 59,631 units fits ≈ 23,900 one-message and ≈ 3,950 two-message frames [inferred: arithmetic from `jmx.csv`, `vt-out.csv` and `BufferPool` units (`BufferPool.java:128–129`), not observed per frame]. V0's 69,568 B is 34 units for 30 messages (larger frames formed while the kernel buffer filled) [inferred].
   - D_direct for V4 (56–64 MiB) is far above D (7.2 MiB): the pool allocates 1 MiB macro chunks and keeps them [inferred; it is not used by any row].
3. **Matched row.**
   - **Unit: none.** A4's rows are applied in order:
     - Row 1 (invalid): no [observed].
     - Row 2 (never stalled; P-set not tracking; S < H): no [observed].
     - Row 3 (follows L): no; per-L medians are not monotone, and the spreads are 22,858 B (S), 0 (N) and 45,056 B (U), all below the thresholds [observed].
     - Row 4 (mechanism): no; max R ≤ L in 24/24, guard misses 0, inference errors 0, no S ≥ H + 65536 [observed].
     - Row 5 (U-only): no; U's spread is 45,056 B < 262,144 [observed].
     - Row 6 (Confirmed) requires "N and U meeting B2f" with A3's P-set bound N ∈ [S, S + 65536). That fails in 9/9 P-set runs [observed], so row 6 is not met.
     - Row 7 then applies, and names this case as its example: *"Anything else (e.g. row 6 met except a B2f N bound …) → Not confirmed (no matching row), Effect undetermined."*
   - **Cluster: A10 row 5.** *"D(V1-V3) pairwise ≤ 4 MiB and not ordered, but some lifetime's D outside [64 MiB, 70 MiB] while `pending_bytes` > 64 MiB and the STALL levels meet A9 → Not confirmed: the per-link stall is at H as traced, but D does not measure it at the predicted size."* Each part is satisfied:
     - Pairwise 0.323 MiB, not ordered [observed].
     - All six V1–V3 lifetimes are at 116.2–116.8 MiB [observed].
     - `pending_bytes` max 132 MiB > 64 MiB [observed: `vt-out.csv`].
     - A9 is met: knob read-back, stall levels in [H, H + 65536) (with ≥ 1 small-link stall inside each freeze), RESUME ≤ L [observed: `flw.trace`].
4. **Excluded rows.**
   - **Unit:** listed in part 3.
   - **Cluster:**
     - Row 1 (invalid): excluded by no reset and the read-back.
     - Row 2 (limit never reached): excluded because D ≫ 64 MiB and pending is 132 MiB.
     - Row 2 (positive control): not applicable (V2 is not in its range); D(V2) − D(V4) = 109 MiB ≥ 56 anyway.
     - **Row 3 (Refuted — usage follows the low mark): excluded.** The means are monotone in L but span 0.323 MiB, below A9's 4 MiB, and a 1 KiB → 63 MiB change of L moved D by 0.3 MiB, while a 64 → 4 MiB change of H moved it by 109 MiB [observed].
     - Row 4 (mechanism): excluded by 0 out-of-range stalls and 0 RESUME > L.
     - Row 6 (noise): excluded because the means are within 4 MiB.
     - Row 7 (Confirmed): excluded because no V1–V3 lifetime is in [64, 70] MiB.
5. **Observed vs. inferred.** The verdicts rest only on observed readings and on the frozen rows. The inferred statements explain the two misses and are not used to choose a row:
   - (a) NoSizeEstimator makes N blind: observed in source, and N = k × 96 exactly in 24/24 runs.
   - (b) The 1.82 factor is pool rounding of one- and two-message frames: inferred from unit arithmetic.
   - (c) D_direct includes retained macro chunks: inferred.
6. **Deviations and gaps.**
   - The cluster tier ran without the 4 KiB socket buffers (defect 1), and with the STALL rule moved by one line to the call at `:858` (defect 2).
   - Neither change touches B3f/B3g. The kernel buffers hold a few MB more during the freeze, which are outside the pool and therefore outside D.
   - Paths and the tmpfs are deviations recorded in §1.
   - No frame-size observation was made, so 4.2-2's cause stays inferred.
   - The unit N measure was blind by construction; this was not caught in the audit.
7. **Core question.**
   - **Unit:** usage does **not** follow `flushLowWaterMark`. S and the pool's U are flat across L from 1 KiB to 1016 KiB at H = 1 MiB (spreads 22.9 KB and 45.1 KB; parts 1, 3), while the same workload tracks H (S ratio 64.1; part 3). The low mark acted only on the resume level (R ≤ L, with R near L when L is near H; part 3).
   - **Cluster:** the same holds. D is flat in L to 0.3 MiB at 116 MiB, and moves by 109 MiB with H (part 3).
   - The frozen tables still cannot say "Confirmed — does not cap". The unit table required a Netty byte measure that Cassandra disables, and the cluster table required D ≈ H, while frames of one mutation make D ≈ 1.8 × H. By the protocol, both verdicts are **Not confirmed**, with the Effect **undetermined**; the readings point to "does not cap", but no frozen row says so.

**Conclusion (one line):**
- **Unit:** **Not confirmed (no matching row)** — A4 row 7; Effect undetermined.
- **Cluster:** **Not confirmed** — B3g/A10 row 5 (the per-link stall is at H as traced, but D does not measure it at the predicted size); Effect undetermined.

## 5. Self-check of run 1 — AI

### 5.1 Check of run 1's conclusion

I re-opened every raw file and re-parsed it with `run1/selfcheck.py`, which is independent of the harness's analysis and reads `unit.csv`, `jmx.csv`, `vt-out.csv`, `flw.trace`, `times.json` and `A-system.log` directly.

| Part | Holds? | Note (file re-read) |
|---|---|---|
| 1. Validity | yes | `selfcheck-unit.out`: read-back mismatches 0, failed or incomplete 0, never stalled 0, P > S all. `selfcheck-cluster.out`: (H, L) as expected in all 10 lifetimes, `active_connections` min 3, DOWN 0, interrupted 0; `build-variants.log` constants. `A-yaml.diff` shows the B3a lines without the buffers |
| 2. Readings | yes | N = 192 / 1,632 / 12,384, = 96 × 2 / 17 / 129 (`selfcheck-unit.out`, last line). `NoSizeEstimator.size()` returns 0 and is installed at `OutboundConnectionInitiator.java:197` (re-read in the pinned clone). V1-r1's `jmx.csv` plateau is 122,124,288 = 59,631 × 2048; vt bytes per message 2,110.9–2,111.0 (re-computed from `vt-out.csv`) |
| 3. Matched row | yes | Unit: the A4 rows were re-applied in order by the script; only the A3 P-set N clause fails (9 of 9), and row 7's text names that case. Cluster: row 5's four conditions re-derived (pairwise 0.323 MiB; V1–V3 lifetimes not in [64, 70]; pending max 138,411,937 B; 0 out-of-range STALLs, 0 RESUME > L) |
| 4. Excluded rows | yes | Each Refuted row is addressed: unit trend thresholds not met (S medians non-monotone; U non-monotone; N constant); cluster means monotone but 0.32 MiB < 4 MiB |
| 5. Observed vs. inferred | yes | The verdicts use only observed values; the 1.82 factor and the D_direct remark are labelled inferred and choose no row |
| 6. Deviations and gaps | yes | Both runbook defects were fixed before any counted cluster reading (shakedown files under `run1/shakedown/`); the frozen tables were not edited after any reading (sha256 `f754e36f…` → `b797d658…` differ only in the two defect notes next to B3a and A8) |
| 7. Core question | yes | The answer follows the logic of B1 (flat in L, moves with H, L acts on the resume), and the verdict words follow the frozen tables, not the answer |

### 5.2 Run 2?

**No** — decided 2026-10-22. Neither verdict rests on an inferred statement; the self-check settled every part from run 1's files; and the result neither refutes the case nor confirms a bypass. A run 2 under the same frozen tables would land on the same rows, because both misses are systematic (a disabled estimator; a deterministic per-frame rounding), not noise.

## 6. Run 2 — fresh AI session (optional)

Not done (§5.2).

## 8. Verdict — AI

**Stage-3 estimate:** negative.

**Claim tested (B1):** for an event-loop outbound connection whose peer stops reading, the peak bytes held in Netty for that connection (`flushingBytes`, Netty's `totalPendingWriteBytes`, the networking `BufferPool` used size) do **not** follow `flushLowWaterMark`. For every L < H the peak stays in [H, H + one frame). Changing H moves it (the positive control). The low mark only shifts the resume point (≤ L). "Confirmed" below means this claim held.

| Tier | Verdict (B2g / B3g row) | Effect on the constraint | Basis | Date |
|---|---|---|---|---|
| Unit | **Not confirmed (no matching row)** — A4 row 7. Everything in row 6 held except A3's bound on the Netty measure N, which is blind (`NoSizeEstimator`) | **undetermined** | run 1 + self-check | 2026-10-22 |
| Cluster | **Not confirmed** — A10 row 5. D flat in L (0.32 MiB) and moved by H (109 MiB), stall at H as traced, but D ≈ 1.82 × H, outside [64, 70] MiB | **undetermined** | run 1 + self-check | 2026-10-22 |

**Positive control:**
- **Unit:** the P-set on the same workload: S = 85–131 KB at H 64 KiB, 1.07 MB at 1 MiB, 8.40–8.41 MB at 8 MiB (ratio 64.1); U followed.
- **Cluster:** V4 against V2: D 7.19 MiB against 116.45 MiB (difference 109.3 MiB), with per-link STALLs at 4,196,668 against 67,110,801 B.

Both controls moved as predicted, so "flat in L" is not an insensitive measure. The tiers miss Confirmed only on the absolute-size predictions (N; D ≈ H).

**What the readings say beyond the verdict (for the index, not a verdict):**
- In every reading, the in-flight peak is set by `flushHighWaterMark` and is independent of `flushLowWaterMark`.
- The low mark changes only the level at which delivery resumes:
  - unit R = 0 for L ≤ 32 KiB, ≈ 523 KB for L = 512 KiB, ≈ 981 KB for L = 1016 KiB;
  - cluster RESUME 0, ≈ 2.2 MB and ≈ 41 MB for L = 1 KiB, 32 MiB and 63 MiB.
- A side finding: at H = 64 MiB, the pool memory pinned is ≈ 1.8 × H, because frames hold one mutation each.

**Feedback filed:**
- The case file's section D was updated on 2026-10-22 (untracked; no commit).
- Sections amended: dated audit amendments A1–A11 (before any reading) and the two runbook-defect amendments (next to B3a and A8, before any counted cluster reading).
- No prediction or row was changed after a reading.

**sha256 of the case file:**
- as filed `16b0da55a6454033fd77d712e0e921f2d331565af0dd9d9f6c6dc538f84295e9`
- frozen `f754e36f8f7ab5edc281986809cf4291722348b29f732ba63c7ed0f7a8bcf69d`
- after the runbook defects `b797d658c074694d4e0ed46386f63d414f519fb3f23f87840c1f57c0c864fb98`
- final after section D: see the line below.

**Final sha256 (after section D):** `42fbac8c0966f72c848024aae58fde81296b3bc8892600eb1340a6ba881bf119` (2026-10-22, after section D; the file is otherwise as at `b797d658…`)
