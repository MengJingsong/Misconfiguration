# native_transport_receive_queue_capacity-acquireCapacity-queueCapacity — stage-4 results

> **Case:** [`native_transport_receive_queue_capacity-acquireCapacity-queueCapacity`](../../../stage3-ai-deep-read/long-path/cases/native_transport_receive_queue_capacity-acquireCapacity-queueCapacity.md)
>
> **Status:** **Closed 2026-10-15 — unit Confirmed; cluster Confirmed (amended §9a row 1): the capacity bounds decoded requests in the throwing mode at both sizes; in the default mode it bounds large requests (by pausing the connection) and bounds nothing for small ones, whose every refusal also lowers the connection's `queueSize` by one request for good; one sub-prediction missed (`n100` peak band); no run 2.** Run 1 on `pc57`, 01:29–02:10 EDT; independent self-check 613/614 (the one failure = that missed band). Audited 2026-10-15 (**Ready after amendments**), §9a frozen 00:58 EDT `892454c7…` before any harness code or reading, verified unchanged at the end of run 1.
>
> **Path:** long. Unit tier and cluster tier.

## 1. Before run 1 — design audit and freeze

| Field | Content |
|---|---|
| **Case-file version** | Last commit of the case file before the audit: `531c3ba`; the audit's amendments are not committed yet (commit on request). **§9a's hash: `892454c7c3b62c430981323090acba68e983bfff`** (`sed -n '/^### 9a\. /,/^### 9b\. /p' <case file> \| git hash-object --stdin`), recorded 2026-10-15 00:58 EDT after the amendments and **before any harness code or reading existed**; §9a is frozen at this text. §9's hash after the 9b–9e amendments (01:10 EDT): `c0e77a4a7aec1f5195faadb32fa6c8cca9832a16`. Before the amendments (the filed text): §9a `8594a8d542cb8a49edcee608a92dada6ee91dc99`, §9 `2b32dbc4b623b6049c9494f5bf856ae70a70682b`. Later dated amendments to 9b–9e that leave 9a unchanged change §9's hash but not §9a's. |
| **Harness** | written 2026-10-15 after the freeze, described in its `README.md`: `NativeQueueModesTest.java`, `unit-hold.btm`, `ntq-trace.btm`, `hold-request.btm`, `NativeFlood.java`, `flood-logback.xml`, `Jmx.java` (copied), `make-node-yaml.sh`, `cluster-run.py`, `unit-run.sh`, under `../harness/native_transport_receive_queue_capacity-acquireCapacity-queueCapacity/` (uncommitted); the self-check `native_transport_receive_queue_capacity-acquireCapacity-queueCapacity/run1/selfcheck.py` was written before run 1 and tested on the shakedowns' data. **Instrument checks (not readings):** `javac` of both Java files; Byteman `TestScript` type-checks all ten rules of the three `.btm` files; `unit-run.sh instrument` (shakedown, 01:06 EDT) gives every trace line kind (8 `new`, 23 `acq` with 4 `INSUFFICIENT_GLOBAL`, 20 `rel`, 20 `dec` with 1 `BYTES_IN_FLIGHT`, 20 `rls`, 1 `disc`, 1 `ldisc`, 2 `wake`) and the test's 60 checks pass; `Submit -l` lists the 9 node rules at every start. **Shakedowns (not readings), `NTQ_SCALE` 0.15–0.2:** 1 (`c1m`, 01:10–01:23): the client JVM had no JDK 11 module options (`conf/jvm11-clients.options`), so `FileUtils` failed to initialise, buffer frees failed and 5–385 responses per arm were lost (`outstanding` > 0; the node had released every request); fixed in `cluster-run.py` (`client_jvm_opts()`), and an `EXPECTED` line added for prediction 7's "no other overload text in `system.log`", which the script had only grepped. 2 (`c1m`, with the fix): 71/71 `EXPECTED` yes, self-check 134/134. 3 (`nsweep`, `defres`): 29/30 and 8/8; the miss was `n100`'s peak `ΣA` below the (*K* − 2*M*, *K*] band. Predictions are not tuned to shakedowns, so the band was left as frozen (run 1 misses it too, §4.2). |
| **Tiers and values** | **Unit:** upstream `ClientResourceLimitsTest` (control); `NativeQueueModesTest` (amended 9e steps u0–u6). **Cluster** (`pc57`, one node, client on the same host): capacity 128 KiB · 512 KiB · 1 MiB (default) · 4 MiB with both reserves at 4 MiB; per value idle and connected-idle controls, A (small, both modes), B as four arms (throwing small, throwing large, default large, default small); *N* sweep 1 · 10 · 100 at 1 MiB (throwing small); default-reserves control at 512 KiB. |
| **Audit bottom line** | **Ready after amendments** — 2026-10-15. Four defects that would have produced a wrong or unreadable result were found in the source, none from a reading: the cluster workload's 256 KiB requests take a path whose default-mode behaviour is the opposite of what §6b/§8 predict (rec. 1); the observable `D` is not raised on that path (rec. 2); the unit steps as filed would hang (rec. 3); the two modes run together would share the reserves (rec. 4). One source finding becomes a new prediction (the default-mode drift, rec. 1). All are amended in the case file, dated, before the freeze. |

### 1.1 Design audit

Checked against the pinned clone `cassandra-5.0.9` (`/proj/misconfiguration-PG0/git-repos/cassandra-src`, `git describe --tags` = `cassandra-5.0.9`). **Re-read in context:** `CQLMessageHandler.java` 80-160 (fields, constructor, `LARGE_MESSAGE_THRESHOLD`), 160-330 (`processOneContainedMessage`, `processRequestAndUpdateMetrics`, `discardAndThrow`, `buildOverloadedException`), 330-512 (`composeRequest`, `processRequest`, error handling, `toFlushItem`, both `release` methods), 512-720 (`processFirstFrameOfLargeMessage`, wake-up task, both private `acquireCapacity` variants), 720-850 (`LargeMessage`: `markOverloaded`, `onIntactFrame`, `onComplete`, `abort`); `AbstractMessageHandler.java` 200-500 (frame dispatch, reactivation, `UpToOneMessageFrameProcessor`, both `acquireCapacity` overloads, `releaseCapacity`, `channelInactive`), 600-800 (`WaitQueue`, `schedule()`, `ReactivateHandlers`, `Ticket`); `FrameDecoder.java` 190-370 (`activate`, `reactivate`, `processBacklog`, `channelRead`, `deliver`, auto-read off); `ResourceLimits.java` 90-180 (`Concurrent.release` throws below zero); `ClientResourceLimits.java` 38-130 (one allocator per client address, the global limit, runtime setters); `Dispatcher.java` 100-130, 335-470 (`hasQueueCapacity`, the queue-time check, the backpressure warnings, `processRequest`); `PipelineConfigurator.java` 300-335; `DatabaseDescriptor.java` 570-575, 645-660, 905-918, 2376-2385, 3208-3215; `Config.java` 288-302, 1384-1399; `CBUtil.java` 443-460; `ClientMetrics.java` 80-150; `SimpleClient.java` 60-700 (builder, `connect(…, throwOnOverload)`, `execute(List)`, the v5 pipeline, the response queue); upstream tests `NativeProtocolLimitsTestBase.java`, `ClientResourceLimitsTest.java` 50-110.

| Group | Check | Rating | Note (section checked) |
|---|---|---|---|
| A. Core question | constrained quantity is memory or disk bytes | Met | accounted request body bytes per connection; the decoded requests they stand for (§4, §7) |
| A. Core question | knob varied, ≥ 3 values incl. default — or another approach, with the reason | Met | 128 KiB · 512 KiB · 1 MiB (default) · 4 MiB, restart-only (9a Testability, 9b); mode per connection |
| A. Core question | real resource measured, not only the counter (gap named) | **Not met** (as filed) | 9a/9d define the real reading `D` as `channelPayloadBytesInFlight`, raised only in `processRequestAndUpdateMetrics` (`CQLMessageHandler.java:267-271`, the small path) and lowered in every `release(Header)` (`:507-511`): for the design's 256 KiB requests it never rises and goes negative. §9d's memory readings (heap info, direct, pool) are node-wide and cannot be tied to decoded requests. Amended (rec. 2): `D` from a trace of decodes and releases; live `QueryMessage` instances from class histograms (each holds a heap copy of its value, `CBUtil.java:443-450`) |
| A. Core question | usage driven to the limit and past it | Met | 32 × 256 KiB per connection, 10 connections, reserves 4 MiB: past *N*·*C* + *R* at every value |
| B. Logic | each step says what it establishes | Met | the "How this verifies" block matches the procedure and the table |
| B. Logic | prediction stated in numbers or a clear relation | **Partly** | relations without numbers ("D = A ≤ C + share of R"), and the default mode left as two competing readings. Re-derived from the source with numbers per value (*K* = *N*·*C* + *R*), exact count equalities (refusals = `RequestDiscarded` = client overloads; refusals = warned responses) and the drift equality `A_i` = −*k_i*·*M* (rec. 1) |
| B. Logic | every plausible outcome has a conclusions row with its evidence | **Partly** | no row for a mode behaving differently by request size, none for the drift. Rows added (amended table) |
| B. Logic | confirmation needs ceiling-follows-knob and direct disallow evidence | Met | discards, the warning, the trace's `INSUFFICIENT_*` outcomes |
| B. Logic | alternative explanations and their controls | **Partly** | the two modes run together share the reserves of one client address (`ClientResourceLimits.java:50-60`), so each mode's refusals depend on the other's load: run apart (rec. 4). The other-limit control (default reserves) and the other-overload texts were there |
| C. Specific | a human can follow it from the intro and §9a | Met | |
| C. Specific | an AI can run §9b–§9e without re-deriving the code path | **Partly** | `NativeFlood` on `SimpleClient` is named but `SimpleClient.execute(List)` throws on the first error response and leaves the rest in a `SynchronousQueue` (`SimpleClient.java:310-347`, `:666-690`), so it cannot keep a window full through `OverloadedException`s; how a trace line is tied to a mode and an arm was open. Amended (rec. 5) |
| C. Specific | knob, values, workload, commands, observables, sampling, stop conditions exact | **Partly** | the large-path problem (rec. 1); the unit step 2.1–2.2 set the reserves to 600 B under a 4 KiB request, so a default-mode connection's ticket could never be served (rec. 3); 9c's INSERT workload writes up to 64 MiB/s (rec. 5) |
| D. Runnable | harness and environment prerequisites exist or are listed | Met | listed in 9c, none exists (step 1). `pc57`: JDK 11.0.32.1, Ant 1.10.12, `~/cassandra-run1` at `cassandra-5.0.9` (built, test classes built), Byteman 4.0.20 in `build/lib/jars`, 32 cores, 251 GiB, `ulimit -n` 1,048,576 |
| D. Runnable | workload arithmetic reaches the limit (data, time, disk, memory) | **Partly** | (i) The request executor (128 threads, 500 ms hold) completes about 256 requests/s; *N* = 100 × 32 queues about 1,700 accepted requests, 6–7 s, past `read_request_timeout` (5 s, counted from arrival) and close to `native_transport_timeout` (12 s): both raised to 60 s (rec. 5). (ii) Disk: INSERTs of 256 KiB at 256/s are 64 MiB/s, about 4 GB per arm on a spinning disk (the `rqc` lesson): a read of an empty table instead (rec. 5). (iii) Memory: at most about 210 MB of decoded requests (*N* = 100) on a 4 GiB heap |
| D. Runnable | load-bearing citations spot-checked against the pinned clone | Met | §4's wiring chain holds (`PipelineConfigurator.java:306`, `:309-314`, `:317-332`; `DatabaseDescriptor.java:3208-3210`; `Config.java:301-302`); `Config.java:1393` (`native_transport_throw_on_overload = false`); `DatabaseDescriptor.java:649-656`, `:911-915`; `CQLMessageHandler.java:196-261` as quoted in §5 |

**Findings the audit rests on, all from the source.**

1. **The cluster workload takes the large-message path, where the default mode waits.** `LARGE_MESSAGE_THRESHOLD` = `FrameEncoder.Payload.MAX_SIZE − 1` = 131,071 B (`CQLMessageHandler.java:83`, `FrameEncoder.java:41`). A request that does not fit in one frame arrives as a non-self-contained first frame and is handled by `processFirstFrameOfLargeMessage` (`AbstractMessageHandler.java:222-230`; `CQLMessageHandler.java:516-660`). With `throwOnOverload` false, a refused `acquireCapacityAndQueueOnFailure` returns `false` before `this.largeMessage` is set (`:605-649`), so `FrameDecoder.deliver` keeps the unconsumed frame at the head of its backlog and the decoder stays inactive with auto-read off (`FrameDecoder.java:316-331`, `:343-347`); the frame is processed again only from `onReserveCapacityRegained` when the wait queue can lease the whole request from the reserve (`AbstractMessageHandler.java:292-321`, `:702`). The request is decoded only after that acquire succeeds (`LargeMessage.onComplete`, `:822-835`). So for 9c's 256 KiB requests, §6b/§8's "decoded regardless" is wrong, and 9a's "two readings" are both about the small path. The throwing mode on the large path marks the message overloaded, drops its later frames (`:797-803`), and answers once complete (`:827-830`).
2. **On the small path the default mode's release undoes an acquire that never happened.** The refused request is decoded and dispatched (`:236-261`) without `queueSize` having been raised (`AbstractMessageHandler.java:411-431`); its flush calls `release(Header)` → `releaseCapacity(bodySize)` (`CQLMessageHandler.java:480-511`, `AbstractMessageHandler.java:461-475`). So each refusal lowers the connection's `queueSize` by one request permanently; the connection's own allowance becomes *C* + *k*·*M* after *k* refusals. The reserves are not corrupted (a release returns only what `queueSize` holds above *C*, all of it borrowed), so `ResourceLimits.Concurrent.release` never goes below zero (`ResourceLimits.java:156-173`). The throwing mode's discard does not release (`:274-292`). This is new: §8 says the default mode bounds nothing *per refusal*; the source says it also widens the per-connection bound for the rest of the connection's life. Added as prediction 3 with an exact equality.
3. **`channelPayloadBytesInFlight` is not a reading on the large path** (finding above, group A).
4. **Unit steps as filed cannot complete.** 9e 2.2 sends a 4 KiB request on a default connection with reserves of 600 B: the request is refused, decoded, and the connection paused with a ticket for 4,096 B that a 600-B reserve can never lease (`AbstractMessageHandler.java:702`); the next request on that connection would never be processed. 9e 2.4's "held requests" on one connection would hang the same way. In production, `native_transport_max_message_size` ≤ both reserves rules this out (`DatabaseDescriptor.java:911-915`). Rebuilt as u0–u6 with reserves 2*M* that the test fills and frees (upstream `emulateInFlightConcurrentMessage`), a gate the test opens, and the server's own handler read by reflection.

| # | Recommendation | Applied? | Why |
|---|---|---|---|
| 1 | Run both sizes: small (65,000-byte value, one frame) and large (262,000-byte value); predictions per path: throwing held to *K* at both sizes; default large held to *K* by waiting with no drift; default small decoded despite refusal with the drift `A_i` = −*k_i*·*M_s* and `ΣD` above *K*; conclusions rows for each outcome | **applied** to 9a (Testability amendment (i)–(ii), How-this-verifies, amended prediction 1–3, amended conclusions table), dated 2026-10-15 | findings 1, 2 |
| 2 | `D` from a decode/release trace per handler; `A` from the acquire/release trace; live `QueryMessage` count from class histograms as the real resource | **applied** to 9a (amendment (iii), prediction 6, "Why `D`"), 9c (`ntq-trace.btm`), 9d (amended table) | finding 3, group A |
| 3 | Unit tier rebuilt (u0–u6): reserves 2*M* filled and freed by the test, gate, reflection on the server handler, the boundary, both paths in both modes, the drift's effect, wiring | **applied** to 9a (amendment (iv)), 9c, 9e | finding 4 |
| 4 | The two modes in separate arms, one after the other, fresh connections each; the default small arm last in each lifetime | **applied** to 9a (Testability, procedure), 9e | group B, alternative explanations |
| 5 | Workload and layout: a read of an empty table (`SELECT pk FROM ks.t WHERE pk = 0 AND v = ? ALLOW FILTERING`), no disk; `native_transport_timeout` and `read_request_timeout` 60 s; one node from `~/cassandra-run1` with its own `conf/`; `NativeFlood` on `SimpleClient` with its own response loop and a 100 ms retry; throwing windows ⌈2(*C* + *R*/*N*)/*M*⌉; `Bds` 180 s | **applied** to 9a (prediction notation), 9b (amended table), 9c, 9e | group C, group D |
| 6 | §5/§6b/§7/§8 describe the small path only; §6a's allocation site is the small path's (the large path decodes in `LargeMessage.onComplete`); the drift | **left for stage 3** (recorded in the case's §10 after the run) | not needed for a valid run |

**Agreement criteria** — filled only if run 2 is chosen.

## 2. Environment

| Field | Run 1 | Run 2 (fresh AI session, if done) |
|---|---|---|
| Date | 2026-10-15, 01:29 EDT onward (one chain: unit tier, then labels `c128k`, `c512k`, `c1m`, `c4m`, `nsweep`, `defres`) | — |
| Node (CloudLab name and type) | `pc57` (`node0.jason92-319347.misconfiguration-pg0.cloudlab.umass.edu`), 32 cores, 251 GiB; the session ran on the node itself | — |
| OS and kernel (`uname -r`) | Ubuntu 22.04, `5.15.0-187-generic` | — |
| JDK (`java -version`) | OpenJDK 11.0.32.1 (node: `-Xms4G -Xmx4G`, G1; client: `-Xmx4g`, `conf/jvm11-clients.options`, `-Dio.netty.eventLoopThreads=1`) | — |
| Ant (`ant -version`) | 1.10.12 | — |
| Local `cassandra-src` clone commit | `~/cassandra-run1` at `cassandra-5.0.9` (`b5f2a54`), built; the citation clone `/proj/misconfiguration-PG0/git-repos/cassandra-src` at the same tag | — |
| Case-file commit / harness commit | case file last committed `531c3ba`, amendments uncommitted (§9a `892454c7…`); harness uncommitted, run copy `~/stage4-harness-run/ntq/` identical to the repo (`md5sum` compared before run 1; every `summary.txt` carries the harness `md5sum`) | — |
| Storage for node data | `~/stage4-ntq/data` on the local disk (`/dev/sda3`, 50 GB free); the workload reads an empty table, so nothing is written but the schema | — |
| Full logs (path, outside the repo) | `pc57:~/stage4-logs/ntq/run1/` (`unit/`, `<label>/` with `ntq.trace`, `summary.txt`, `arms.csv`, `system.log`, one folder per arm); shakedowns in `~/stage4-logs/ntq/shakedown1`–`3` and `shakedown-out/` | — |

## 3. Runbook defects

None in run 1: every step of the amended 9b–9e ran as written. (The client-JVM defect and the missing `EXPECTED` line were found in shakedown 1, before run 1, and are recorded in §1's harness row.)

## 4. Run 1

**Scope:** both tiers; cluster capacity 128 KiB · 512 KiB · 1 MiB (default) · 4 MiB with every arm, the *N* sweep at
1 MiB and the default-reserves control at 512 KiB. **Command log:** `native_transport_receive_queue_capacity-acquireCapacity-queueCapacity/run1/`
(`chain.log`; `unit/summary.txt`, `unit/harness.out`; `cluster/<label>/summary.txt`, `arms.csv`, and per arm
`handlers.csv`, `meters.txt`, `flood-run.excerpt`; the self-check `selfcheck.py` and its `selfcheck.out`). Full logs on
the node: `pc57:~/stage4-logs/ntq/run1/` (traces 285 MB in all). Notation as in the amended §9a: *M_s* = 65,074 B,
*M_l* = 262,074 B (every `dec` line of an arm carried the same `b`); *N* = 10; *K* = *N*·*C* + *R*.

### 4.1 Readings

**Unit tier** (`unit/summary.txt`, `unit/harness.out`; *M* = 4,192 B, *C* = 3*M* = 12,576 B, both reserves 2*M* = 8,384 B filled by the test)

| Test or assertion | Result | Evidence (file) |
|---|---|---|
| upstream `ClientResourceLimitsTest` | 11/11 pass | `unit/summary.txt` |
| `NativeQueueModesTest` | 1/1 pass, **60/60 checks** | `unit/harness.out` |
| u0 | `queueCapacity` 1,048,576; one held request: `queueSize` = `channelPayloadBytesInFlight` = 4,192 | `harness.out` |
| u1 throwing, small | 3 accepted, `queueSize` 12,576 = *C* (third at exactly *C*); 4th: `OVERLOADED: Request breached limit on bytes in flight. (Endpoint: 8384/8384 bytes, Global: 8384/8384 bytes.)`, `RequestDiscarded` +1, `queueSize` and in-flight 12,576, 3 decoded; end 0 | `harness.out` |
| u2 default, small | 4th decoded (4 arrivals, in-flight 16,768) with `queueSize` still 12,576; 5th not decoded while paused; 4 results, 1 warned (`bytes in flight`), `RequestDiscarded` +0; **`queueSize` −4,192 after the releases**; reserves freed → the 5th served, no warning; `queueSize` ends at −4,192, in-flight 0 | `harness.out` |
| u3 the drift's effect | same connection, reserves full again: 4 requests all accepted (no refusal, no warning), `queueSize` 12,576 from −4,192: the connection admitted *C* + *M* of its own | `harness.out` |
| u4 default, large (1,024-byte frames) | 3 accepted; 4th refused and not decoded; `channelPayloadBytesInFlight` stays 0 on this path; after the 3 releases `queueSize` 0 and the 4th **still waits** for the reserve; reserves freed → decoded, answered with no warning; `RequestDiscarded` +0; end 0 | `harness.out` |
| u5 throwing, large | 4th `OVERLOADED … bytes in flight` after its frames, never decoded; `RequestDiscarded` +1; end 0 | `harness.out` |
| u6 wiring | new handlers 123,456 then 654,321, the first unchanged; `THROW_ON_OVERLOAD=1` → `true`; no option → config `false`, and `true` after `setNativeTransportThrowOnOverload(true)` | `harness.out` |

**Cluster tier** — B arms (`cluster/<label>/arms.csv`, `summary.txt`; refusals are `acq` lines with `INSUFFICIENT_*`, all `INSUFFICIENT_GLOBAL`)

| *C* | *K* | `Bts` peak `ΣA` / refusals = `RequestDiscarded` = client overloads / accepted | `Btl` peak `ΣA` / refusals (= `ldisc` = discards = overloads) / accepted | `Bdl` peak `ΣA` / refusals = `wake` / decoded = `SUCCESS` / end `ΣA` | `Bds` refusals *k* (= `dec bp=BYTES_IN_FLIGHT` = warned) / end `ΣA` (= −*k*·*M_s*) / peak `ΣA` / **peak `ΣD`** |
|---|---|---|---|---|---|
| 128 KiB | 5,505,024 | 5,466,216 / 50,425 / 9,996 | 5,503,554 / 16,943 / 2,500 | 5,503,554 / 2,710 / 2,798 / 0 | 1,196 / −77,828,504 / 5,466,216 / **83,294,720** |
| 512 KiB | 9,437,184 | 9,435,730 / 84,588 / 15,269 | 9,434,664 / 25,634 / 4,284 | 9,434,664 / 4,365 / 4,568 / 0 | 1,137 / −73,989,138 / 9,435,730 / **83,294,720** |
| 1 MiB | 14,680,064 | 14,641,650 / 136,225 / 15,434 | 14,676,144 / 37,209 / 6,664 | 14,676,144 / 6,658 / 6,927 / 0 | 1,055 / −68,653,070 / 14,641,650 / **83,294,720** |
| 4 MiB | 46,137,344 | 46,072,392 / 329,528 / 15,940 | 46,125,024 / 104,027 / 15,328 | 46,125,024 / 9,084 / 15,552 / 0 | 572 / −37,222,328 / 46,072,392 / **83,294,720** |

| *C* | Live `QueryMessage` at 1/3, 2/3 (class histogram) — `Bts` · `Btl` · `Bdl` · `Bds` | *K*/*M_s* · *K*/*M_l* | `[B` bytes `Bts` → `Bds` | `Bds`: `ΣD` > *K* from / reaches *N*·*W*·*M_s* at | every handler's end `A_i` in `Bts`/`Btl`/`Bdl` |
|---|---|---|---|---|---|
| 128 KiB | 83, 84 · 21, 21 · 21, 21 · 1,274, 1,280 | 84.6 · 21.0 | 21.9 MB → 101.5 MB | +2 s / +8 s | 0 |
| 512 KiB | 142, 145 · 36, 36 · 36, 36 · 1,280, 1,280 | 145.0 · 36.0 | 25.8 MB → 102.1 MB | +2 s / +8 s | 0 |
| 1 MiB | 224, 225 · 56, 56 · 56, 56 · 1,278, 1,280 | 225.6 · 56.0 | 31.2 MB → 101.8 MB | +2 s / +12 s | 0 |
| 4 MiB | 708, 707 · 176, 176 · 176, 176 · 1,278, 1,280 | 709.0 · 176.0 | 65.9 MB → 101.8 MB | +2 s / +21 s | 0 |

Every histogram count lies within `ΣD`/*M* over its interval ±1 s (32/32; `summary.txt` "histogram" lines).

**Cluster tier** — other arms and controls

| Value / label | Run | Observable | Reading | Evidence |
|---|---|---|---|---|
| each *C* | idle control (10 s) | acquires, decodes | none | `<label>/summary.txt` |
| each *C* | connected-idle (10 + 10 connections, 10 s) | read-back | 20 handlers, every `cap` = *C*, 10 `throw=true` and 10 `throw=false`; no acquire, no decode | `summary.txt` |
| each *C* | A, both modes (*W* = 2 · 8 · 16 · 64) | refusals, discards, warnings; peak `ΣA` | 0, 0, 0; peak `ΣA` = *N*·⌊*C*/*M_s*⌋·*M_s* exactly: 1,301,480 · 5,205,920 · 10,411,840 · 41,647,360 in both modes; end 0 | `arms.csv` |
| `nsweep` (1 MiB, throwing small, *W* 32) | `n1` | refusals; peak `ΣA` | 0; 2,082,368 = 32·*M_s* | `nsweep/arms.csv` |
| | `n10` | refusals = discards = overloads; peak `ΣA` | 27,788; 14,641,650 ∈ (14,549,916, 14,680,064] | `nsweep/arms.csv` |
| | `n100` | refusals = discards = overloads; peak `ΣA`; mean | 167,679; **108,673,580, below the band (108,921,756, 109,051,904]** (378,324 B = 5.8 *M_s* under *K*); per-second mean over the middle of the arm 105.8 MB; `ΣA` ≤ *K* at every line | `nsweep/summary.txt`, `n100/handlers.csv` |
| `defres` (512 KiB, reserves default) | throwing small, *W* 128 | refusals, discards; peak `ΣA`; global reserve | 0, 0; 83,294,720 = *N*·*W*·*M_s* (the window); global in use up to 78,051,840 B | `defres/summary.txt` |
| every arm | other overload | client `ovl_other`, `err`; `TimedOutBeforeProcessing`, `ProtocolException`; `system.log` texts; `ERROR` lines | all 0; every client got every response; `Client.RequestsSize` 0 after every drain | `summary.txt` |
| every B arm | networking pool (`Jmx` poll every 2 s) | `UsedSize` / `OverflowSize` max | small-request arms ≤ 1.3 MB; large-request arms rise and **do not fall back within a node lifetime** (`Bds` repeats `Bdl`'s maximum): 0.82 / 0.68 GB at 128 KiB, 1.34 / 1.21 GB at 512 KiB, 1.84 / 1.71 GB at 1 MiB, 4.87 / 4.74 GB at 4 MiB (recorded; not a §9a prediction) | `<label>/<arm>/jmx-poll.csv` on the node |

### 4.2 Conclusion and logic

1. **Validity.** Valid. The over-limit condition occurred in every B arm at every value (refusals 572 to 329,528)
   [observed: `cluster/*/arms.csv`]. Hold-fixed settings confirmed: the read-back (`new` lines) shows `cap` = the label's
   capacity on every handler and the mode chosen by the startup option [observed: `summary.txt` read-back lines]; reserves
   4 MiB (`gl=` limit 4,194,304 on every `acq` line, global in use ≤ 4,192,972) [observed: `arms.csv` `glmax`]; the yaml
   and JVM options [observed: `summary.txt` `yaml:`/`jvm:` lines, `-Xms4G -Xmx4G`, both agents]; no other overload fired
   (no `requests/second`, `spent over` or `timed out before it could start`; `TimedOutBeforeProcessing` and
   `ProtocolException` +0) [observed: `summary.txt`]; every client got every response [observed: `flood-run.excerpt`
   `outstanding=0`]. The trace is internally consistent: every acquire and release moves its handler's `queueSize` by
   exactly its bytes (self-check integrity, 0 violations in every arm) [observed: `selfcheck.out`].
2. **Readings.** One gap from a frozen relation: `n100`'s peak `ΣA` is 5.8 requests below *K*, outside the
   (*K* − 2*M*, *K*] band; the hard bound `ΣA` ≤ *K* holds at every line [observed]. With 100 connections each
   re-sending a refused request 100 ms later, the shared reserve's free room is not refilled before other requests
   complete, so the 100 own allowances and the reserve are never all full at one instant [inferred: the fill dynamics;
   `n10` reaches the band with the same window]. Two readings beyond §9a: (a) in `Bds` the counter `ΣA` peaks exactly
   where it does in `Bts` (5,466,216 · 9,435,730 · 14,641,650 · 46,072,392) while `ΣD` runs to the client's window, so
   the counter reports a bound the node does not hold [observed]; (b) the networking pool gauges rise without falling
   during large-request arms (table above) [observed]; whether that is memory held or a gauge that misses some frees is
   not established here [inferred: `BufferPool.allocate()`/`put()` count overflow buffers allocated minus freed,
   `BufferPool.java:233-264`, `:811-823`; no direct-memory reading was taken].
3. **Matched row** — amended §9a row 1: *"Predictions 1–3 hold: throwing mode held to K and following C with discards;
   default large held to K by waiting, no drift; default small decoded despite refusal, A_i = −k_i·M_s, ΣD above K"*.
   - Throwing mode held to *K*, following *C*, with discards: `Bts`/`Btl` `ΣA` ≤ *K* at every line, peaks within 2*M*
     of *K* (slope *N* across 128 KiB → 4 MiB: 5.47 → 46.07 MB small, 5.50 → 46.13 MB large); refusals = `RequestDiscarded`
     delta = client `bytes in flight` overloads exactly, each a `disc`/`ldisc` line, decodes = successful acquires (none
     of the refused decoded); every handler back to 0 [observed: `arms.csv`, `summary.txt`].
   - Default large held to *K* by waiting, no drift: `Bdl` refusals 2,710–9,084, each followed by a ticket (`wake` =
     refusals), decodes = successful acquires per handler, peak `ΣA` = `Btl`'s, `ΣD` ≤ `ΣA` at every line, no warning or
     error at the client, `RequestDiscarded` +0, every handler ends at 0 [observed].
   - Default small decoded despite refusal, drift, `ΣD` above *K*: `Bds` decodes with `BYTES_IN_FLIGHT` = refusals per
     handler = warned responses (1,196 · 1,137 · 1,055 · 572); every handler ends at exactly −*k_i*·65,074 (sum
     −77,828,504 · −73,989,138 · −68,653,070 · −37,222,328); `ΣD` exceeds *K* 2 s in and reaches the client's whole window
     (83,294,720 = 10 × 128 × 65,074) at every *C*; last third above first third; `RequestDiscarded` +0 [observed].
   - Real resource: live `QueryMessage` counts within `ΣD`/*M* in all 32 histograms; `Bts` at or just below
     ⌊*K*/*M_s*⌋ (83–84 · 142–145 · 224–225 · 707–708 against 84 · 145 · 225 · 709), `Btl` and `Bdl` exactly
     ⌊*K*/*M_l*⌋ (21 · 36 · 56 · 176), `Bds` 1,274–1,280 = the window at every *C*; `[B` live bytes rise from `Bts` to
     `Bds` by 79.6 · 76.3 · 70.6 · 35.9 MB against (1,280 − ⌊*K*/*M_s*⌋) × *M_s* = 77.8 · 73.9 · 68.7 · 37.2 MB, the heap
     copies of the extra values (`CBUtil.java:443-450`) [observed; the attribution of `[B` is inferred].
   - Controls and A: no refusal under the capacity, A's peak exactly *N*·⌊*C*/*M_s*⌋·*M_s*; `n1` window-bound; `defres`
     no refusal with the window at 83 MB [observed]. The unit tier shows each mechanism in isolation: u1/u5 discard,
     u2 decode-and-drift, u3 the eroded allowance, u4 the large-path wait [observed: `harness.out`].
4. **Excluded rows.** Row 2 (`ΣD` ≤ *K* at some *C* with the drift): `ΣD` peak 83.3 MB > *K* at all four. Row 3 (no
   drift): every `Bds` handler ends at −*k_i*·*M_s*, u2 at −*M*. Row 4 (`ΣD` follows *C*, refused not decoded): `ΣD`
   flat at 83.3 MB across *C*, every refusal decoded. Row 5 (refused large request decoded without a later successful
   acquire, or warned): decodes = successful acquires per handler, warned 0. Row 6 (throwing `ΣA` above *K* or flat):
   never above *K*, slope *N* across *C*. Row 7 (refusals ≠ discards): equal exactly in every throwing arm. Row 8
   (`QueryMessage` outside the `ΣD` band): 32/32 inside. Row 9 (no refusal, or another overload text): refusals in every
   B arm, no other text. The filed table's rows map onto these: its row 1 (throwing confirmed, default `D` flat in *C*)
   holds for small requests; its row 2 (default `D` stops near ⌊*C*/*F*⌋·*F* + *F*) is refuted for small requests and
   describes neither path (large requests stop at the reserves, not at *C* + *F*).
5. **Observed vs. inferred.** The conclusion rests on observed counts and exact equalities. Inferred: (i) why `n100`
   misses the band (fill dynamics); (ii) the attribution of the `[B` rise to decoded values; (iii) the drift's cause is
   the source reading of §1 finding 2 — the run observes its exact signature (−*k_i*·*M_s* per handler, u2's −*M*,
   u3's *C* + *M*), not the line of code.
6. **Deviations and gaps.** `n100`'s band missed (recorded, not re-run, predictions not tuned). The networking pool
   gauge observation is outside §9a and has no direct-memory reading behind it. The throwing arms ran with a window
   sized from an estimated *M* (65,100 / 262,100 against 65,074 / 262,074 measured): the windows are those frozen in the
   amended notation, so no deviation.
7. **Core question.** Usage follows the constraint where the check decides: in the throwing mode the bytes a connection
   holds stop at its capacity plus its share of the reserves, the plateau moves with the capacity (slope *N*, step 3),
   and every refusal is a discard the client sees (step 5) — parts 3 and 1. In the default mode the outcome depends on
   the request's size: a multi-frame request waits undecoded and is held to the same bound (part 3, `Bdl`; u4), but a
   one-frame request is decoded anyway and, because its release subtracts bytes that were never added, each refusal
   raises that connection's own allowance by one request, so decoded bytes run to whatever the client sends (83 MB at
   every capacity, 15× *K* at 128 KiB) while `queueSize` reports the same bound as the throwing mode (part 3, `Bds`;
   u2–u3) — §8's "bounds nothing" holds for small requests, more strongly than §8 said.

**Conclusion (one line):** amended §9a row 1 — **confirmed** (throwing mode bounds decoded requests at both sizes;
default mode: large requests bounded by waiting, small requests not bounded and the counter drifts by −*M* per
refusal); unit tier confirmed; one sub-prediction (`n100` peak band) not borne out.

## 5. Self-check of run 1 — AI

`run1/selfcheck.py` (written before run 1, tested on the shakedowns' data) re-parses the raw node files with its own
code: the full `ntq.trace` of each label (its own `key=value` parser, arm membership from the client's connection
addresses matched to `new` lines), each arm's client output, `meters.txt`, the class histograms and `system.log`, and
the unit tier's `harness.out`. It checks trace integrity, re-judges every frozen prediction, and compares its own
counts and peaks with the run script's `arms.csv`. Result (`run1/selfcheck.out`): **613 ok, 1 FAIL** — the FAIL is
`n100`'s band, the same miss as the run script's one `EXPECTED … NO`; every agreement check holds (counts and peaks to
the byte), integrity 0 violations in every arm.

### 5.1 Check of run 1's conclusion

| Part | Holds? (yes / no) | Note (file re-read) |
|---|---|---|
| 1. Validity | yes | `selfcheck.out` read-back, integrity, other-overload and drain lines; `summary.txt` yaml/jvm lines |
| 2. Readings | yes | `n100` peak re-derived (108,673,580); pool gauge maxima re-read from `jmx-poll.csv` |
| 3. Matched row | yes | every P1–P7 line of `selfcheck.out` for the four values; u0–u6 in `harness.out` |
| 4. Excluded rows | yes | as part 3; the filed rows mapped in §4.2 part 4 |
| 5. Observed vs. inferred | yes | the three inferred items are not load-bearing for the matched row |
| 6. Deviations and gaps | yes | the one FAIL is the recorded miss |

### 5.2 Run 2 decision

**No run 2.** The matched row rests on exact equalities (refusals = discards = overloads; refusals = warned decodes;
end `A_i` = −*k_i*·*M_s* per handler; decodes = successful acquires) that an independent parser reproduces to the byte,
at four capacity values, plus a unit tier that shows each mechanism alone. The one miss is a band on a dynamic peak at
*N* = 100, whose hard bound held; a second run would not change the row.

**Agreement criteria** — not needed (no run 2).

## 6. Run 2

Not run (§5.2).
