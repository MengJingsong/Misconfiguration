# internode_application_send_queue_capacity-acquireCapacity-pendingCapacityInBytes — stage-4 results

> **Case:** [`internode_application_send_queue_capacity-acquireCapacity-pendingCapacityInBytes`](../../../stage3-ai-deep-read/long-path/cases/internode_application_send_queue_capacity-acquireCapacity-pendingCapacityInBytes.md)
>
> **Status:** audited and frozen 2026-10-07 (**Ready after amendments**); harness not written; run 1 not started
>
> **Path:** long. Unit tier and cluster tier.

## 1. Before run 1 — design audit and freeze

| Field | Content |
|---|---|
| **Case-file version** | Working tree on top of commit `6453abb` (the audit's amendments are not committed yet). **§9a's hash: `efd85ccc7840d755bbc3b254843733c3bfab9888`** (`sed -n '/^### 9a\. /,/^### 9b\. /p' <case file> \| git hash-object --stdin`), recorded 2026-10-07 after the amendments and **before any harness code or reading existed**; §9a is frozen at this text and must not be edited after any reading of run 1. §9's hash (`sed -n '/^## 9\. /,/^## 10\. /p'`): `b673b7cc710702d11964ca38d8e6d06468f4761b` after the amendments. Before them (the filed text): §9a `0eaefb90d5aab291548eeec7c7724cbd439f0b2d`, §9 `41f124f9de56c4843c1365f4a351d531270a6746`. Later dated amendments to 9b to 9e that leave 9a unchanged change §9's hash but not §9a's. |
| **Harness** | none yet. To write in step 1, under `../harness/internode_application_send_queue_capacity-acquireCapacity-pendingCapacityInBytes/` (case 9c, as amended): `SendQueueCapacityTest.java`, `SendQueueWiringTest.java`, `send-config.btm`, `send-acquire.btm`, `hold-delivery.btm`, `Hold.java` (boot-class-path helper), `make-node-yaml.sh` (also writes each node's `conf/` copy), `Jmx.java` (the `max_space…` client with a port argument), `sample-outbound.py`, `cluster-run.py`, `unit-run.sh`, `README.md`. |
| **Tiers and values** | **Unit:** upstream `ConnectionTest#testInsufficientSpace`, `#testAcquireReleaseOutbound` and `ResourceLimitsTest` as controls; `SendQueueCapacityTest` (U1 to U9, *C* = 4096, *E* = 1500, *G* = 1000); `SendQueueWiringTest` (U10, U11; its own JVM). **Cluster** (one machine, four processes: S = `127.0.0.2`, R1 to R3 = `127.0.0.3` to `.5`): capacity 512 KiB · 1 MiB · 4 MiB (default) · 16 MiB with both reserves at 1 MiB; the default-reserves control at 4 MiB; the peer sweep (RF = *P* = 1, 2, 3) at 4 MiB; C1 and C2 (one endpoint-reserve key at a time) at 4 MiB; idle, no-hold and default-reserves controls; the hinting observation (optional). |
| **Audit bottom line** | **Ready after amendments** — 2026-10-07. Nothing blocks the run. Two defects that would have produced a false result were found in the source and amended (the drain step and the server's request pool), and one missing recipe (four nodes from one clone) was written; one reading rule was made measurable. All amendments are in the case file, dated, none depends on a reading. |

### 1.1 Design audit

Checked against the pinned clone `cassandra-5.0.9` (`~/git-repos/cassandra-src`, `git describe --tags` = `cassandra-5.0.9`; the node's `~/cassandra-run1` reports the same tag). **Every distinct citation of the case file was re-checked by a script** (128 links, each cited file and range exists, the first line of each range read; the 122 of the filed text plus the 6 the amendments add): none wrong. **The load-bearing ones were re-read in context:** `OutboundConnection.java` 95-175 (fields, packing), 255-283 (`Connecting.isFailingToConnect`), 307-358 (constructor, `enqueue()`), 365-520 (`acquireCapacity()`, `releaseCapacity()`, `onOverloaded()`, `onExpired()`), 520-720 (`Delivery`: `execute()`, `run()`, `executeAgain()`), 756-830 and 925-1010 (the two `doRun()`s), 1036-1052, 1095-1130, 1185-1200, 1370-1425 (`setDisconnected()`), 1655-1779 (counters, test hooks); `OutboundConnections.java` 60-130, 195-262; `OutboundConnectionSettings.java` 95-140, 320-345, 372-400, 440-520; `OutboundMessageQueue.java` 60-240; `ResourceLimits.java` 100-300; `MessagingService.java` 300-330, 415-500, 650-675; `DatabaseDescriptor.java` 649-656, 960-1005, 3015-3060; `Config.java` 238-261, 283; `InternodeOutboundMetrics.java` 40-200; `InternodeOutboundTable.java` 30-140; `RequestCallbacks.java` 100-160, 255-305; `StorageProxy.java` 878-930, 1494-1600, 2423-2490; `AbstractWriteResponseHandler.java` 280-320; `Dispatcher.java` 55-62, 228-270; `Message.java` 205-245; `Mutation.java`, `CounterMutation.java` (`hintOnFailure()`); `ConnectionTest.java` 150-300, 350-430, 735-815; `HandshakeTest.java` 290-320; `CQLMessageHandler.java` 150-270, 380-420, 495-515; `AbstractMessageHandler.java` 60-200; `SocketFactory.java:181`; `bin/cassandra`, `bin/cassandra.in.sh`, `bin/nodetool`, `conf/cassandra-env.sh`; `build.xml:1192`; the stress client (`SettingsMode`, `JavaDriverClient`). The amendments' own citations were read the same way. **The case's central derived claim, the per-peer reserve read from the receive-side key, holds on this reading too:** `getOutbound():662-668` builds the settings with `withDefaults()`, whose argument `applicationSendQueueReserveEndpointCapacityInBytes()` (`:392-396`) falls back to the **receive** getter, so the field is set before `OutboundConnections:83` runs `withDefaultReserveLimits()`; upstream `ConnectionTest:244-247` calls the two in the opposite order, `HandshakeTest:306-314` in the production order. It is still a derivation: unit step U10 and scenario C decide it.

| Group | Check | Rating | Note (section checked) |
|---|---|---|---|
| A. Core question | constrained quantity is memory or disk bytes | Met | accounted serialized bytes of unsent messages, which pin heap (§7, §8); the gap to the heap is named in 9a and §8 |
| A. Core question | knob varied, ≥ 3 values incl. default — or another approach, with the reason | Met | 512 KiB · 1 MiB · 4 MiB (default) · 16 MiB, restart-only so one start of S per value (9a Testability, 9b); the reserves are swept as a second axis (peer sweep, C1, C2) |
| A. Core question | real resource measured, not only the counter (gap named) | **Partly** | the heap of S after a full GC and the instance counts are read, the gap is named; but the reference ratio came from scenario A (about 0.26 MiB accounted), below the noise of a `used` reading. Amended: idle floor read three times and a proportionality rule over the values that clear the noise (rec. 4) |
| A. Core question | usage driven to the limit and past it | **Partly** | arithmetic fine at three values, but at 16 MiB the plateau needs 135 held writes and the server's request pool holds 128, so the top value could not reach `C + F − M`; the default-reserves control needs 256. Amended (rec. 2) |
| B. Logic | each step says what it establishes | Met | the "How this verifies" block matches the procedure, prediction and table; step 7 amended with rec. 1 |
| B. Logic | prediction stated in numbers or a clear relation | **Partly** | exact intervals for the plateau, the peer sweep and the reserve gauge (re-derived from `:383-454` and `ResourceLimits:263-273`: the plateau is in `(C + F − M, C + F]` for a link that carries the load alone, the sweep's bounds `P·C + G − (P + 1)·M` and `P·C + G` follow from the same rule); the **heap** relation had no usable number (rec. 4) and the **drain** bullet depended on a write that cannot restart the link (rec. 1) |
| B. Logic | every plausible outcome has a conclusions row with its evidence | **Partly** | rows exist for exceeds-the-limit, flat across values, counter-capped-but-heap-grows, never-reached, leak, early fall, U9; the leak row's trigger (a probe write) could not occur. Amended |
| B. Logic | confirmation needs ceiling-follows-knob and direct disallow evidence | Met | the rule after the table; `overload_count`, the `INSUFFICIENT_*` lines, the WARN, with the timed-out counter held at zero |
| B. Logic | alternative explanations and their controls | Met | expiry: the timed-out counter and the 8 s load inside the 10 s deadline; client or server throttling: the default-reserves arm, C1, and the thread-pool and in-flight arithmetic of 9b; the no-hold control is an empirical expectation and no row rests on it (rec. 7) |
| C. Specific | a human can follow the claim, the steps and the conclusions from the intro and 9a | Met | |
| C. Specific | an AI can run 9b–9e without re-deriving the code path | **Partly** | four nodes from one clone need per-node configuration directories and JMX ports (9b pointed at `environment.md` §5, which is about separate hosts); the hold's mechanism and its release were not specified. Amended (recs 1, 3) |
| C. Specific | knob, values, workload, commands, observables, sampling and stop conditions exact | **Partly** | as above, plus `native_transport_max_threads` (rec. 2), the start command of S, and which of S's directories are emptied between values (rec. 5). Amended |
| D. Runnable | harness and environment prerequisites exist or are listed | Met | listed in 9c, none exists (step 1); `pc66` has JDK 11.0.32.1, Ant, the clone and Byteman 4.0.20 (`build/lib/jars`), 40 cores, 125 GiB; the helper jar and a port-taking `Jmx.java` were added to the list |
| D. Runnable | workload arithmetic reaches the limit (data, time, disk, memory) | **Not met** (as filed) | held writes needed: 11 · 15 · 39 · **135** at 512 KiB · 1 · 4 · 16 MiB, 256 for the default arms, against a pool of 128. Memory: 4 × 2 GiB heap and about 32 MiB held, on 125 GiB; per-IP in-flight limit about 51 MiB at `-Xmx2G` against about 32 MiB held (margin 1.6); the stress pool is 8 connections × 40 requests, enough for 256 threads. Disk: S stores nothing. Time: about 50 minutes of the case's budget. Met after rec. 2 |
| D. Runnable | load-bearing citations spot-checked against the pinned clone | Met | see the list above; one range corrected (`ConnectionTest#L229-L263` began at `doTest()`, now `#L237-L263`) |

**Two findings that the audit rests on, both from the source, neither from a reading.**

1. **A write cannot restart a link that is held and full, so the drain could not have been seen.** The filed hold returns `false` from `LargeMessageDelivery.doRun()`; `Delivery.run()` then breaks out of its loop (`OutboundConnection.java:691-692`) and `maybeExecuteAgain()` (`:695`, `:615`) leaves the delivery `STOPPED` unless another run was already requested. Nothing restarts it but `enqueue():349` (after an accepted `queue.add()`), the connect listener (`:685-686`, only when the link is not connected), `disconnectNow():1388` and `stopAndRun()` (close and reconnect). At the plateau the probe write is refused inside `acquireCapacity()` and `enqueue()` returns at `:344-345`; `INSUFFICIENT_GLOBAL`, the first refusal in every reserves-low arm (the node-wide reserve is tried first, `ResourceLimits:265`), does not even take the prune-and-retry branch (`:337-341`, `INSUFFICIENT_ENDPOINT` only). So pending bytes would never have returned to zero and the row "the accounting leaks → **Refuted**" would have fired at the first B run for a harness reason. The hold now parks the thread inside `doRun()` and the lift releases that invocation, which polls and expires the queue; `LargeMessageDelivery.run()` renames the thread to `Messaging-OUT-<from>-><to>-LARGE_MESSAGES`, so a thread dump shows it. The pool that runs it is `Messaging-SynchronousWork`, capped at `Integer.MAX_VALUE` threads (`SocketFactory:181`), so one parked thread per held link costs nothing.
2. **The server's request pool caps the number of held writes.** Each write the plateau holds blocks a `Native-Transport-Requests` thread in `StorageProxy.mutate()` (`:906`, `responseHandler.get()`) until the 10 s deadline; the pool has `native_transport_max_threads` workers (default 128, `Config:283`, `Dispatcher:58-61`). With `M` ≈ 131.3 kB the plateau at 16 MiB needs `⌊17 MiB / M⌋` = 135 held writes: a pool of 128 would stop at about 16.0 MiB, below `C + F − M` = 16.875 MiB, with no refusal at all (`overload_count` 0, the row "*X* follows *C* but `overload_count` stays 0 → **Not confirmed**"), and the default-reserves control would show half of *D*. A 128-thread pool also leaves the poller and `cqlsh` without a thread once it is full. S now runs with 512.

| # | Recommendation | Applied? | Why |
|---|---|---|---|
| 1 | The hold parks the delivery thread inside `doRun()` (a boot-class-path helper polls the hold file) instead of `RETURN false`; the drain waits for the release, the probe write comes after it | **applied** to 9a (logic 7, drain bullet, leak row), 9c (`hold-delivery.btm`, `Hold.java`), 9d (Drain), 9e (hold check, scenarios A and B), dated 2026-10-07 | finding 1 |
| 2 | S runs with `native_transport_max_threads: 512`; the arithmetic (135 and 256 held writes, the per-IP limit) is stated once in 9b and referred to in 9c | **applied** to 9b (hold fixed), 9c ("if not saturated") | finding 2 |
| 3 | The per-node recipe: `CASSANDRA_CONF` and `CASSANDRA_LOG_DIR` per node, `JMX_PORT` replaced in each copy of `cassandra-env.sh` (`:235` hard-codes 7199), ports 7102 to 7105, every directory named in the yaml, the start command of S written out | **applied** to 9b (cluster layout), 9c (`make-node-yaml.sh`, `Jmx.java`), 9e (start command) | four processes from one clone collide on the JMX port otherwise; `environment.md` §5 is for separate hosts |
| 4 | The heap rule: the idle floor read three times; Δ*heap* / *X* within a factor of 2 of the median over the values where Δ*heap* exceeds three times the idle spread; the row reworded accordingly | **applied** to 9a (heap bullet and table row), 9b (idle control), 9d (Real resource), 9e (control run) | the reference ratio came from A (0.26 MiB accounted), below the noise; the filed row would have fired at any value |
| 5 | S's `data/` and `commitlog/` stay between values; its `hints/` and `saved_caches/` are emptied, `logs/` moved aside; the hold is removed before stopping S | **applied** to 9b (reset) | S owns no token range, so wiping changes nothing the check sees, and a wiped S rejoins as a new host ID at an old address, which was not traced |
| 6 | Unit-tier detail: U9's closing sentence names a connection "connected" that never was; the `doTestManual()` link range began at `doTest()` | **applied** (documentation) to 9e and 9c | accuracy |
| 7 | The no-hold control's expectation (X far below `C + F`, no drops) is empirical: *R1*'s apply rate decides it, not the source; no row of 9a rests on it | **applied** (documentation) to 9b | an underivable expectation should not read as a prediction |
| 8 | Nothing in §4 to §8 was found wrong | **left for stage 3**: none | the wiring finding awaits U10 and scenario C |

**Agreement criteria** — filled only if run 2 is chosen.

## 2. Environment

| Field | Run 1 | Run 2 (fresh AI session, if done) |
|---|---|---|
| Date | | |
| Node (CloudLab name and type) | | |
| OS and kernel (`uname -r`) | | |
| JDK (`java -version`) | | |
| Ant (`ant -version`) | | |
| Local `cassandra-src` clone commit | | |
| Case-file commit / harness commit | | |
| Storage for node data | | |
| Full logs (path, outside the repo) | | |

## 3. Runbook defects

None yet (no step has been run). Defects found by reading, before any run, are the amendments of §1.1.

| # | Run | Step (§9b–§9e) | Problem | Fix | Decision (date) | Case-file commit with the fix |
|---|---|---|---|---|---|---|

## 4. Run 1

Not started.

## 5. Self-check of run 1 — AI

Not started.

## 6. Run 2 — fresh AI session (optional)

Not done.

## 8. Verdict — AI

| Tier | Verdict (§9a row) | Basis | Date |
|---|---|---|---|
| Unit | — | — | — |
| Cluster | — | — | — |

**Feedback filed:** the case file's §10 "Stage-4 feedback" carries the audit (2026-10-07); no run has reported yet.
