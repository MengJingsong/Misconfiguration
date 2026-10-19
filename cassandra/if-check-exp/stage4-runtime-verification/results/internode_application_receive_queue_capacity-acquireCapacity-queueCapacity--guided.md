# internode_application_receive_queue_capacity-acquireCapacity-queueCapacity — stage-4 results

> **Case:** [`internode_application_receive_queue_capacity-acquireCapacity-queueCapacity`](../../stage3-ai-deep-read/cases/internode_application_receive_queue_capacity-acquireCapacity-queueCapacity--guided.md)
>
> **Status:** **Closed 2026-10-15 — Confirmed at both tiers** (run 1 on `pc57`, 00:12–00:34 EDT; independent self-check 95/95; no run 2). Audited 2026-10-14 (**Ready after amendments**), §9a frozen 23:37 EDT `5ef01c26…` before any harness code or reading, verified unchanged at the end of run 1.
>
> **Path:** long. Unit tier and cluster tier.

## 1. Before run 1 — design audit and freeze

| Field | Content |
|---|---|
| **Case-file version** | Last commit of the case file before the audit: `7a836d0`; the audit's amendments are not committed yet (commit on request). **§9a's hash: `5ef01c26a5a10e9385b96481b27f836c804e24c9`** (`sed -n '/^### 9a\. /,/^### 9b\. /p' <case file> \| git hash-object --stdin`), recorded 2026-10-14 23:37 EDT after the amendments and **before any harness code or reading existed**; §9a is frozen at this text. §9's hash (`sed -n '/^## 9\. /,/^## 10\. /p'`): `b63cf06a94973ec2b1ad335124c2e607f0db33d9`. Before the amendments (the filed text): §9a `f1433bd8a16b6e758d7c6960c38a698663a98364`, §9 `989bb9818f0411d93a653e80c473c0d3bdfd18d3`. Later dated amendments to 9b–9e that leave 9a unchanged change §9's hash but not §9a's. |
| **Harness** | written 2026-10-14/15 after the freeze, described in its `README.md`: `AcquireCapacityTest.java`, `ReceiveQueueWiringTest.java`, `receive-trace.btm`, `hold-handler.btm`, `write-load.py`, `sample-inbound.py`, `Jmx.java`, `make-node-yaml.sh`, `cluster-run.py`, `unit-run.sh`, under `../harness/internode_application_receive_queue_capacity-acquireCapacity-queueCapacity/` (uncommitted). **Instrument checks (not readings):** `TestScript` type-checks all three rules (after §3 row 1); `unit-run.sh instrument` gives 11 `acq` lines with `cap=1000` (one per three-argument call) and 3 `rel` lines with the right `q`; `Submit -l` lists the three rules on `R` at every start; shakedowns 1–4 (§3) exercised every label but `c512k` and `defres`. |
| **Tiers and values** | **Unit:** upstream `ResourceLimitsTest` (reserve control); `AcquireCapacityTest` (9e amended steps 1–5, *C* = 1000, reserves 800); `ReceiveQueueWiringTest` (step 6, its own JVM). **Cluster** (`pc57`, five processes on loopback: `R` = 127.0.0.2, `S1`–`S4` = .3–.6; RF 5): capacity 512 KiB · 1 MiB · 4 MiB (default) · 16 MiB with both reserves at 1 MiB, *P* = 1; peer arms *P* = 2, 4 at 4 MiB; small-message arm (32 KiB values) at 4 MiB; controls: idle (every arm), no-hold at 1 MiB, default reserves at 4 MiB. |
| **Audit bottom line** | **Ready after amendments** — 2026-10-14. Four defects that would have produced a wrong or invalid result were found in the source, none from a reading: the observable named as *S* is not the operand (rec. 1); the real resource is not where §9d looks for it (rec. 2); unit step 5 cannot pass (rec. 3); the 16 MiB arm cannot be saturated and the peer arms would time out (rec. 4). All are amended in the case file, dated, before the freeze. |

### 1.1 Design audit

Checked against the pinned clone `cassandra-5.0.9` (`/proj/misconfiguration-PG0/git-repos/cassandra-src`, `git describe --tags` = `cassandra-5.0.9`). **Re-read in context:** `AbstractMessageHandler.java` 140-200 (fields, constructor), 220-380 (frame processing, reactivation, `UpToOneMessageFrameProcessor`), 390-475 (both `acquireCapacity` overloads, `releaseCapacity`), 475-600 (`channelInactive`, `LargeMessage`), 600-800 (`WaitQueue`, `schedule()`, `ReactivateHandlers`, `Ticket`); `InboundMessageHandler.java` 55-560 (whole class: `processOneContainedMessage`, the small path, `processFirstFrameOfLargeMessage`, `LargeMessage.deserialize()`, `dispatch()`, `ProcessMessage.run()`); `InboundMessageHandlers.java` 70-160, 160-330 (callbacks, counters, `usingCapacity()`); `InternodeInboundMetrics.java` 40-110; `InternodeInboundTable.java` 40-135; `MessagingService.java` 305-312, 660-683; `Config.java` 254-261, 271-272; `DatabaseDescriptor.java` 970-1000, 3038-3058; `FrameDecoder.java` 170-300; `BufferPool.java` 150-160, 270-290; `BufferPools.java` 40-70; `BufferPoolMetrics.java` 50-64; `MutationVerbHandler.java` 40-75; `Verb.java:116`; `OutboundConnections.java` 69, 215; `ResourceLimits.java` 90-210; `conf/cassandra.yaml` (`concurrent_writes` 32, `write_request_timeout` 2000ms, `auto_snapshot` true, `internode_compression` dc). The filed citations are right except two small drifts: `MessagingService.java:678` is `:679`, and §1/§6a's allocation site `InboundMessageHandler.java:163` is the line before the call (`:166`); left for stage 3.

| Group | Check | Rating | Note (section checked) |
|---|---|---|---|
| A. Core question | constrained quantity is memory or disk bytes | Met | accounted serialized bytes of accepted, unprocessed inbound messages (§4, §7) |
| A. Core question | knob varied, ≥ 3 values incl. default — or another approach, with the reason | Met | 512 KiB · 1 MiB · 4 MiB (default) · 16 MiB, restart-only (9a Testability, 9b) |
| A. Core question | real resource measured, not only the counter (gap named) | **Not met** (as filed) | §9d reads `R`'s heap and says held mutations sit deserialized in the `MutationStage` queue. True for small messages only: the design's 256 KiB messages take the large path, whose queued messages are raw frames from the **off-heap networking pool**, deserialized only when a stage thread runs them (`InboundMessageHandler.java:207-225`, `:332-384`, `:481-510`; `FrameDecoder` reads through `BufferPoolAllocator`). The heap would hold at most the 32 running messages whatever *S* is, and the "heap grows while Σ S is capped" row could not be read. Amended (rec. 2) |
| A. Core question | usage driven to the limit and past it | **Partly** | 16 MiB needs more than 68 messages in flight from one peer (`(C + 1 MiB)/M`); 9c's 64 threads per stress process cannot exceed 64, so the top value would have stopped at the client's bound with no refusal ("`S` follows *C* but `ThrottledCount` stays zero"). Amended (rec. 4) |
| B. Logic | each step says what it establishes | Met | the "How this verifies" block matches procedure and table; step (7) added with rec. 2 |
| B. Logic | prediction stated in numbers or a clear relation | **Partly** | "S ≈ C + share" and "Σ ≤ P × C + 1 MiB" are relations without numbers, and "that peer's share of the 1 MiB endpoint reserve" mixes the two reserves (the endpoint reserve is per peer, the global one is shared). Re-derived from `:413-447`: the large handler's plateau is exactly `⌊(C + E)/M⌋·M` (5 · 7 · 19 · 67 messages), every refusal `INSUFFICIENT_GLOBAL` with *P* = 1; the peer sweep's bounds; the real-resource numbers. Amended (rec. 1, 2, 4) |
| B. Logic | every plausible outcome has a conclusions row with its evidence | **Partly** | rows exist for exceeds-the-limit, flat across values, counter-capped-but-resource-grows, never-reached, drop; the resource row had no readable trigger (rec. 2), and no row covers a real resource held elsewhere than §7 says. Row added |
| B. Logic | confirmation needs ceiling-follows-knob and direct disallow evidence | Met | `ThrottledCount` and the trace's `INSUFFICIENT_*` lines; "Why `ThrottledCount` and not heap" |
| B. Logic | alternative explanations and their controls | **Partly** | the client's in-flight bound (rec. 4) and write expiry (rec. 4) were not ruled out; the default-reserves arm and the no-hold control were there. Amended: *W* sized from the plateau, the timeout raised, drop checked exactly |
| C. Specific | a human can follow it from the intro and §9a | Met | |
| C. Specific | an AI can run §9b–§9e without re-deriving the code path | **Partly** | which *P* the capacity sweep uses, how *P* is varied (ring size or writers), five processes from one clone (ports, `conf/` copies), how the hold is switched off for A and the idle control. Amended (rec. 5, 6) |
| C. Specific | knob, values, workload, commands, observables, sampling, stop conditions exact | **Partly** | *S* named as `ScheduledBytes`, which is not the operand: it counts a message from its dispatch to the stage until it has run (`InboundMessageHandlers.java:257-273`), so it misses a large message whose frames are still arriving and is not `queueSize`; the exact sum is `using_bytes` of `system_views.internode_inbound` (`InternodeInboundTable.java:118`). Amended (rec. 1) |
| D. Runnable | harness and environment prerequisites exist or are listed | Met | listed in 9c, none exists (step 1). `pc57`: JDK 11.0.32.1, Ant 1.10.12, `~/cassandra-run1` at `cassandra-5.0.9`, Byteman 4.0.20 in `build/lib/jars`, 32 cores, 251 GiB, 50 GB free |
| D. Runnable | workload arithmetic reaches the limit (data, time, disk, memory) | **Not met** (as filed) | (i) 16 MiB unreachable with 64 threads (above). (ii) Write deadline: `write_request_timeout` 2 s; `R` completes about 160 writes/s under the 200 ms hold, so 4 senders × 64 threads queue for 1.6 s and 4 × 128 for 3.2 s: writes would expire and be dropped (`MutationVerbHandler.java:47-52`, `InboundMessageHandler.java:414-425`), which the "no drop" row would misread. (iii) Disk: RF 5, 40 MiB/s on every node, about 1.2 GB per node per 30 s arm, 10 arms: 60 GB against 50 GB free unless truncated (with `auto_snapshot` off). (iv) Memory: 5 × 2 GiB on 251 GiB, fine; held bytes at most 33.6 MB. Amended (rec. 4, 5) |
| D. Runnable | load-bearing citations spot-checked against the pinned clone | Met | above; the wiring chain §4 1–5 holds (`MessagingService.java:675-682` reads the capacity and endpoint reserve per peer at first contact; the global reserve once, `:309-310`) |

**Four findings the audit rests on, all from the source.**

1. **`ScheduledBytes` is not the check's operand.** It is `InboundCounters.scheduledBytes`, raised in `onDispatched` and lowered in `onExecuted` (`InboundMessageHandlers.java:257-273`). `queueSize` is raised at the acquire (`:419-421`, `:439`) and lowered by `releaseCapacity` after the verb handler (`InboundMessageHandler.java:427-442`). A large message is dispatched only when its last frame has arrived (`:332-340`), so between the acquire and the dispatch it is in `queueSize` and not in `ScheduledBytes`. The per-peer sum of `queueSize` is published, as `using_bytes` in `system_views.internode_inbound` (`InternodeInboundTable.java:118`), with the endpoint reserve in use beside it (`:119`).
2. **The large path keeps queued messages off heap.** `processFirstFrameOfLargeMessage` (`:207-225`) acquires the whole size and the `LargeMessage` collects the frames' `ShareableBytes` (`AbstractMessageHandler.java:552-576`), which come from the networking `BufferPool` (`FrameDecoder.java:170, 268-273`; `BufferPoolAllocator.java:40`). `ProcessLargeMessage.provideMessage()` deserializes them on the stage thread just before the verb handler (`InboundMessageHandler.java:358-384`, `:481-510`) and the input's close releases them. With a hold at `doVerb`'s entry the 32 `MutationStage` threads each hold one deserialized `Mutation`; the rest of the accepted messages are frames. Small messages (≤ 64 KiB) are deserialized on the event loop before dispatch (`:156-195`), so for them §7 holds as written.
3. **Unit step 5 as filed cannot pass through the wait queue.** A handler that waits is reactivated only when its reserve can lend the whole message (`WaitQueue.schedule()`, `AbstractMessageHandler.java:702`): with reserves of 500 a 600-byte ticket is never served. And `schedule()` calls `t.handler.eventLoop()`, i.e. `channel.eventLoop()` (`:503-506`, `:716`), so a `null` channel would throw. Hence reserves of 800, a 700-byte waiting request and an `EmbeddedChannel`. (Seen in passing, for stage 3: on the production path `internode_max_message_size`, when unset, is derived from the two **endpoint** reserves only, `DatabaseDescriptor.java:990-996`, not the receive **global** reserve, while a ticket on the global queue needs the whole message from it; with a global reserve set below the message size a throttled connection would never be reactivated. Not tested here.)
4. **The workload as filed cannot reach 16 MiB and would expire writes.** See group D. The writer now keeps exactly *W* writes in flight (128; 256 in the small arm), the deadline is 10 s on every node, and the senders get 512 request threads (each write held at `ALL` occupies one, as in the send-side case).

| # | Recommendation | Applied? | Why |
|---|---|---|---|
| 1 | *S* is the operand: the trace's `q` per handler (on `acq` and `rel`) and per peer `using_bytes`; `ScheduledBytes` recorded beside it only | **applied** to 9a (Test, prediction), 9c (`receive-trace.btm`, `sample-inbound.py`), 9d (row added), dated 2026-10-14 | finding 1 |
| 2 | The real resource is read where it is: live `Mutation` instances (class histogram) and the networking pool's `UsedSize`; a small-message arm at 4 MiB tests §7's heap claim; the resource row reworded and a row added for a resource held elsewhere | **applied** to 9a (Test, Logic 7, prediction, two table rows), 9c, 9d | finding 2 |
| 3 | Unit steps: reserves 800, a 700-byte waiting request, an `EmbeddedChannel`, the boundary step, and a wiring step in its own JVM | **applied** to 9e (unit), 9c | finding 3 |
| 4 | Workload: a writer with exactly *W* in flight (128, small arm 256), B 30 s, `write_request_timeout` 10 s on every node, `native_transport_max_threads` 512 on the senders; no drop checked exactly (`R`'s local write count, dropped `MUTATION`, `expired_count`) | **applied** to 9b (hold fixed), 9c (`write-load.py`, workload), 9d (row added) | finding 4 |
| 5 | Layout: five processes from one clone on loopback (per-node `conf/`, JMX 7102–7106), ring always five nodes with RF 5, *P* = writing senders, *P* = 1 for the capacity sweep; `auto_snapshot: false` and `TRUNCATE` between arms; `R` restarted per value, senders up throughout | **applied** to 9a (Test, procedure), 9b (layout, reset), 9e | the filed layout left *P* for the sweep, the ring per *P* and the disk budget open |
| 6 | The hold switches on a file, so the idle control and A run unheld on the same `R` | **applied** to 9c (`hold-handler.btm`), 9e | A is specified "no hold" while the agent is loaded |
| 7 | The arms of one `R` lifetime share it: `c1m` + `nohold`; `c4m` (= *P* 1) + `p2` + `p4` + `small` | **applied** to 9a (procedure), 9e | saves four restarts; each arm still has its own idle control and counters |
| 8 | Citation drifts (`MessagingService.java:678` → `:679`; allocation site `:163` → `:166`); §7's "heap" and §6a's allocation site hold only for small messages; the `internode_max_message_size` / global-reserve liveness note (finding 3) | **left for stage 3** (recorded in the case's §10 after the run) | not needed for a valid run |

**Agreement criteria** — filled only if run 2 is chosen.

## 2. Environment

| Field | Run 1 | Run 2 (fresh AI session, if done) |
|---|---|---|
| Date | 2026-10-15 00:12–00:34 EDT (`run1/cluster/chain.log`) | |
| Node (CloudLab name and type) | `pc57` = `node0.jason92-319347.misconfiguration-pg0.cloudlab.umass.edu`; 32 cores, 251 GiB. One machine, five processes on loopback: `R` = 127.0.0.2 (JMX 7102, the Byteman agent), `S1`–`S4` = 127.0.0.3–.6 (JMX 7103–7106), `-Xmx2G` each | |
| OS and kernel (`uname -r`) | Ubuntu 22.04.2 LTS, `5.15.0-187-generic` | |
| JDK (`java -version`) | `openjdk 11.0.32.1 2026-08-18` | |
| Ant (`ant -version`) | `1.10.12` | |
| Local `cassandra-src` clone commit | `~/cassandra-run1` at tag `cassandra-5.0.9` (`b5f2a54`); `AcquireCapacityTest.java`, `ReceiveQueueWiringTest.java` copied into `test/unit/org/apache/cassandra/net/` (untracked) | |
| Case-file commit / harness commit | case file: last commit `7a836d0`, audit amendments and 2026-10-15 corrections uncommitted (§9a `5ef01c26…` verified unchanged at the end of run 1, §9 `6f6fed0d…`); harness uncommitted, md5s in every `summary.txt` (`receive-trace.btm` `8835ba35…`, `cluster-run.py` `292b83e2…`) | |
| Storage for node data | data, commit log, hints, caches on a 48 GiB tmpfs `/mnt/stage4-rqc` (9b corrected (a)); `conf/` and node `logs/` on local disk under `~/stage4-rqc/<node>/`. Each arm truncated `ks.t`; the tmpfs held 5.2 MB at the end and was unmounted | |
| Full logs (path, outside the repo) | `pc57:~/stage4-logs/rqc/run1/<label>/` (35 MB): `rqc.trace` (R's Byteman trace, 0.5–7.5 MB per label), `session.log`, `summary.txt`, `arms.csv`, and per arm `vt-*.csv`, `jmx-*.csv`, `histo-*.txt`, `threads-*.txt`, `keys-*.csv`, `tpstats-after.txt`; unit `~/stage4-logs/rqc/unit/`, `unit-instrument/`; shakedowns `~/stage4-logs/rqc/shakedown1`–`4`, `unit-shakedown1`, `unit-instrument-shakedown`. Excerpts in `run1/` (each label's `summary.txt` and `arms.csv`, the unit summaries, `chain.log`, `selfcheck.py` and its output) | |

## 3. Runbook defects

Rows 1–6 were found in the harness checks and shakedowns of 2026-10-14/15 (`~/stage4-logs/rqc/unit*-shakedown*`,
`shakedown1`–`4`), which are not readings; every fix leaves §9a unchanged (hash `5ef01c26…` re-checked after them and at
the end of run 1) and was made before run 1. **Run 1 itself added no defect:** every label ran to its end (`chain.log`).

| # | Run | Step (§9b–§9e) | Problem | Fix | Decision (date) | Case-file commit with the fix |
|---|---|---|---|---|---|---|
| 1 | `TestScript` | 9c `hold-handler.btm` | Byteman's parser rejects `IF new java.io.File(…).exists()` ("invalid expression") | parenthesized: `IF (new java.io.File(…)).exists()`; type-checks | harness, 2026-10-14 | harness only |
| 2 | shakedown 1 (`c1m`, unheld control) | 9e step 2 (reset) | the unheld control saturated `R` anyway (5 nodes on one disk); 357 writes timed out, of which only 38 expired on `R`: the rest expired in **S1's outbound queue** ("dropping message of type MUTATION_REQ whose timeout expired before reaching the network") and were hinted, 256 MB; the hints would replay into later arms and add writes to `R` | `nodetool truncatehints` on every node after each arm; a pending-hints check at each arm's start; senders' dropped `MUTATION` and `TotalHints` added to the no-drop reading; `c1m` (with the unheld arm) runs last, since a file in dispatch survives `truncatehints`; the unheld arm's no-drop reading printed as `CONTROL` | 9e corrected 2026-10-15 (b)–(e) | not committed |
| 3 | shakedown 2 (`c4m`: `p2`, `small`) | 9b layout | in `p2` each writer lost exactly its 128 writes in flight to `WriteTimeout`, with "received only 0 responses" (the coordinator's **own** replica too): every node stalled. `pc57`'s `sda` is a spinning RAID volume (PERC H710P, `rotational` 1) and each node flushed about 170 MB every 4 s (`MEMTABLE_LIMIT`), with `StatusLogger` dumps on all nodes. Not the check: `R`'s readings matched every bound | node data, commit log, hints and caches on a 48 GiB tmpfs at `/mnt/stage4-rqc` (`conf/`, `logs/` stay on disk) | 9b corrected 2026-10-15 (a); ring re-formed | not committed |
| 4 | shakedown 1, 2 | — | the first `unit-run.sh all` ran before the instrument check, so it is a shakedown | unit tier re-run in full as run 1 | 2026-10-14 | — |
| 5 | shakedown 3 (`p4`) | 9c `receive-trace.btm`, `rel` line | the node total rebuilt from the trace read 18,092,145 B against `P·C + G + 64 KiB` = 17,891,328 B, about one message over, while every line's global reserve in use was within *G*. Cause, in the harness: the `rel` line was written at `releaseCapacity`'s exit, i.e. after the method had released the reserves and signalled the wait queues (`AbstractMessageHandler.java:461-474`), so the acquire of a handler reactivated by that room could be written first, and the rebuild counted the released message and its successor together | the `rel` line is written right after `queueSizeUpdater.getAndAdd(this, -bytes)` (`AFTER INVOKE`, `q` = the returned old value − *b*), before the reserves are released; `traceln` is serialized, so an acquire that needs the freed room is always written later. Instrument check repeated (3 `rel` lines, `q` 600 · 600 · 0). **A residual race remains** (shakedown 4 read the same 18,092,145 B): two releases of one handler on two `MutationStage` threads can be written in the opposite order (consecutive `rel` lines of one handler with `q` rising, impossible in event order), so the last-printed `q` can be one message stale. No print position removes it, since the counter update and the line are not atomic together; the frozen rebuild is kept, and two diagnostics are printed beside it (the count of such pairs, and the node total sampled from `using_bytes`) | harness, 2026-10-15 | harness only |
| 6 | shakedown 3 (`c16m`) | the run script's pool statistic | "mean over the last third of B minus the first third" read 1.77 MB against *M*, but the samples are flat at 13.8 MB from 2 s on: the first third included the ramp from 0 before *S* reached its plateau (`jmx-B.csv`). 9a (7) asks for the resource to stay flat **while *S* is capped** | the pool statistics (mean, drift) use the samples from the arm's first refusal (the moment *S* is capped) to the last send; an arm with no refusal uses the whole send window. Not a change of 9a's numbers or tolerances | harness, 2026-10-15 | harness only |

## 4. Run 1

**Scope:** unit tier (instrument check, upstream `ResourceLimitsTest`, `AcquireCapacityTest` u1–u5,
`ReceiveQueueWiringTest` u6); cluster tier, every label and arm of 9e as amended: `c512k` (B), `c4m` (B = *P* 1, `p2`,
`p4`, `small`), `c16m` (B), `defres` (B), `c1m` (B, `nohold`), in that order (`c1m` last, §3 row 2). One chain,
2026-10-15 00:12–00:34 EDT. **Command log:** `run1/cluster/chain.log`, each label's `session.log` on the node; summaries
`run1/cluster/<label>/summary.txt`, per-arm numbers `run1/cluster/<label>/arms.csv`.

### 4.1 Readings

**Unit tier** (`run1/unit/summary.txt`, `run1/unit/harness.out`; instrument `run1/unit-instrument/`)

| Test or assertion | Result | Evidence (file) |
|---|---|---|
| Instrument check: `AcquireCapacityTest` with `receive-trace.btm` | 11 `acq` lines, all `cap=1000` (7 `SUCCESS`, 2 `INSUFFICIENT_GLOBAL`, 2 `INSUFFICIENT_ENDPOINT`), the lease line `gl=300/700`, 3 `rel` lines (`q` 600 · 600 · 0) | `unit-instrument/summary.txt`, `rqc.trace` |
| upstream `ResourceLimitsTest` | 5/5 pass | `unit/summary.txt` |
| `AcquireCapacityTest` u1–u5 | pass, 54 checks, 0 mismatch: `q + b = C` succeeds with no reserve, `C + 1` borrows exactly 1; 600 + 600 borrows only 200; 700 refused `INSUFFICIENT_GLOBAL` with nothing taken, `throttledCount` 1, a ticket, no reactivation; `INSUFFICIENT_ENDPOINT` rolls the global borrow back; a release lets the wait queue lease 700 B and reactivate the handler on its event loop, retry `SUCCESS`, `q` 1300, reserves 300 / 300, lease's 400 returned, `throttledNanos` 54,960,423 | `unit/harness.out` |
| `ReceiveQueueWiringTest` u6 | pass, 20 checks, 0 mismatch: 123,456 / 654,321 / 777,777 B reach the getters, `InboundMessageHandlers` and the urgent, small and large handlers' `queueCapacity` and reserve limits; a second peer has its own endpoint reserve and the same global one | `unit/harness.out` |

**Cluster tier.** *M* = 262,205–262,206 B (large) and 32,829 B (small), from the trace's `b=`. Every arm: the read-back
(the first `acq` line after `R` started) named the label's capacity and reserves; no pending hint at the start; A
(200 writes, one in flight, no hold) 200/200 written, no refusal, peak one message; the idle control showed 0 live
`Mutation` instances; `TRUNCATE` ok. All from `run1/cluster/<label>/summary.txt` and `arms.csv`.

| Arm (C; E = G) | *P* | Peak *q* of the data handler (= *n·M*) | Predicted *n* | Refusals (all `INSUFFICIENT_GLOBAL`) / `ThrottledCount` Δ / `ThrottledNanos` Δ | Global reserve in use, max | Live `Mutation` above idle, b1 / b2 | Networking pool above idle, mean while capped | Writes sent = applied on R; errors, drops, hints |
|---|---|---|---|---|---|---|---|---|
| `c512k` (512 KiB; 1 MiB) | 1 | 1,311,025 (5.000 *M*) | 5 | 259 / 259 / 34.2 s | 786,737 | 5 / 5 | 0.13 MB | 1,058 = 1,058; 0, 0, 0 |
| `c1m` (1 MiB; 1 MiB) | 1 | 1,835,442 (7.000 *M*) | 7 | 431 / 431 / 32.5 s | 786,866 | 7 / 7 | 0.15 MB | 1,350 = 1,350; 0, 0, 0 |
| `c4m` B (4 MiB; 1 MiB) | 1 | 4,981,895 (19.000 *M*) | 19 | 976 / 976 / 29.1 s | 787,591 | 19 / 19 | 0.14 MB | 3,102 = 3,102; 0, 0, 0 |
| `c16m` (16 MiB; 1 MiB) | 1 | 17,567,802 (67.000 *M*) | 67 | 814 / 814 / 27.2 s | 794,554 | 32 / 32 | 13.47 MB (pred. 35 *M* = 9.18 MB, ×2) | 5,029 = 5,029; 0, 0, 0 |
| `p2` (4 MiB; 1 MiB) | 2 | 4,981,895 each | ≥ 15 *M* each | 2,911 / 1,457 + 1,454 / 29.5 + 29.5 s | 789,543 | 32 / 32 | 1.32 MB | 5,155 = 5,155; 0, 0, 0 |
| `p4` (4 MiB; 1 MiB) | 4 | 4,981,895 each | ≥ 15 *M* each | 4,377 / 1,089 · 1,090 · 1,104 · 1,094 / 31.4–31.6 s each | 792,471 | 32 / 32 | 13.73 MB | 5,418 = 5,418; 0, 0, 0 |
| `small` (4 MiB; 1 MiB; 32 KiB values) | 1 | 5,219,811 (159.000 *M_s*) | 159 | 1,073 / 1,073 / 28.4 s | 1,025,507 | **159 / 159** | 0.12 MB | 5,165 = 5,165; 0, 0, 0 |
| `defres` (4 MiB; 128 / 512 MiB) | 1 | 33,562,368 (128.000 *M* = *W*) | > C + 1 MiB, ≤ 128 *M* | **0** / 0 / 0 | 29,368,064 (= 128 *M* − *C*) | 32 / 32 | 30.0 MB | 5,032 = 5,032; 0, 0, 0 |
| `nohold` control (1 MiB; 1 MiB) | 1 | 1,835,442 (7 *M*) | no prediction | 3 / 3 / 0.0 s | 786,866 | 0 / 0 | 0.05 MB | 13,516 = 13,516; 0, 0, 0 (CONTROL line) |

| Further reading | Value | Evidence |
|---|---|---|
| Rule checks on every `acq` line (9a "the rule") | 0 `SUCCESS` lines with `q > cap + E`, 0 lines with a reserve above its limit, in every arm | `summary.txt` per label; `selfcheck.out` |
| Other handlers (urgent, small for large arms) | max *q* 521–870 B, 0 refusals, every arm | `summary.txt` |
| Hold | `hold` lines = writes in B (858 · 1,150 · 2,902 · 4,829 · …); `MutationStage` threads sleeping in `doVerb` at b1/b2 = 5 · 7 · 19 · 32 · 32 · 32 · 32 · 32 (c512k · c1m · c4m · c16m · p2 · p4 · small · defres) | `summary.txt`, `threads-b*.txt` |
| R's write rate in B | 24.4 · 34.0 · 92.5 · 157.6 rows/s at 512 KiB · 1 · 4 · 16 MiB (≈ min(*n*, 32) / 0.2 s); `nohold` 443.8 | writer lines in `summary.txt` |
| Node total (peer sweep, 4 MiB): sum of peer peaks · max sampled Σ `using_bytes` · max trace rebuild | *P* 1: 4,981,895 · 4,982,045 · 4,982,482; *P* 2: 9,963,790 · 9,177,175 · 9,439,380; *P* 4: 19,927,580 · 17,567,735 · 17,829,940. Bound `P·C + G` = 5,242,880 · 9,437,184 · 17,825,792 (+ 64 KiB) | `selfcheck.out`, `arms.csv` |
| Trace print order (diagnostic, §3 row 5) | consecutive `rel` pairs of one handler with *q* rising: 15 · 18 · 47 · 793 · 125 · 72 · 503 · 870 per arm | `arms.csv` (`rel_disorder`) |

### 4.2 Conclusion and logic

1. **Validity.** The limit was reached and passed at every value: every reserves-low held arm has refusals and a
   rising `ThrottledCount` [observed: `summary.txt`]. The read-back named the label's capacity and both reserve limits
   at every `R` start [observed: `READ-BACK` lines]. Hold fixed: `concurrent_writes` 32 (32 threads held whenever
   *n* ≥ 32) [observed: `threads-b*.txt`]; the hold fired in every held arm and not in A or `nohold` [observed: `hold`
   counts]; no pending hint at any arm's start and no hint or drop on any node during any arm [observed: `EXPECTED`
   lines, `selfcheck.out`]; client traffic on `R` limited to the samplers' virtual-table reads, which appear in the trace
   as a CQL handler (cap 1 MiB, no refusal) and touch no internode handler [observed: `rqc.trace`, `selfcheck.out`
   "CQL-client lines"]. Valid.
2. **Readings.** No gap or outlier. Two things to note: (a) *M* differs by one byte between labels (262,205 / 262,206;
   the header's vints), which changes no *n*. (b) The trace rebuild of the node total exceeds `P·C + G` by 2,196 B
   (`p2`) and 4,148 B (`p4`), inside the frozen 64 KiB allowance; the print-order diagnostic shows why it can exceed at all
   (§3 row 5), and the sampled totals stay at or below `P·C + G` [observed: `selfcheck.out`].
3. **Matched row:** "Reserves low: per-peer `S` plateaus near `C` plus the reserve share and moves with *C* across the
   four values; `ThrottledCount` rises; `Σ S` scales with *P*; no write errors → **Confirmed**".
   - *Plateaus at C plus the reserve and moves with C:* 5 · 7 · 19 · 67 messages exactly as `⌊(C + 1 MiB)/M⌋`, each
     peak inside `(C + E − M, C + E]` [observed: table above].
   - *ThrottledCount rises:* 259 · 431 · 976 · 814, every refusal `INSUFFICIENT_GLOBAL` [observed].
   - *Σ S scales with P:* each peer's own handler fills 19 *M* (≥ 15 *M*, its own *C*) at *P* = 1, 2, 4; the sum of peaks
     4.98 · 9.96 · 19.93 MB grows by about *C* per peer, while the global reserve in use stays below *G*
     (787,591 · 789,543 · 792,471) and the node total stays at or below `P·C + G` [observed: `selfcheck.out`].
   - *No write errors:* 0 failures, `R` applied exactly the rows sent, no drop, no expiry, no hint, in every held arm
     [observed].
   - The real-resource rows agree: live deserialized `Mutation`s = `min(n, 32)` in the large arms and *n_s* = 159 in
     the small arm, the networking pool holds the rest (13.47 MB at 16 MiB, flat while *S* is capped) [observed].
4. **Excluded rows.**
   - "`Σ S` does not scale with *P*" (multiplier refuted): excluded by the per-peer peaks 19 *M* at *P* = 1, 2, 4.
   - **Refuted** "`S` passes `C` plus the reserves by more than borrowing explains": excluded: 0 `SUCCESS` lines with
     `q > C + E` in any arm; every peak ≤ `C + E`.
   - **Refuted** "`S` flat across the values while `ThrottledCount` moves": excluded: 1.31 → 1.84 → 4.98 → 17.57 MB.
   - **Not confirmed** "`S` follows *C* but `ThrottledCount` stays zero": excluded: counts 259–976.
   - **Refuted** "the held real resource grows over B while *S* is flat, or exceeds what *S* accounts for": excluded:
     `Mutation` counts equal at b1 and b2 in every arm; pool drift −244,326 B (`c16m`) and below *M* in every arm; the
     pool at 16 MiB is 1.47 × the queued frames' accounted bytes, inside the frozen factor of 2, and at 4 MiB with
     *P* = 4 (67 messages node-wide, as at 16 MiB) the same 13.7 MB.
   - "Real resource held as predicted, but the small arm's count is not near *n_s* or a large arm's exceeds
     `min(n, 32)`" (§6a/§7 refuted on where the bytes live): excluded: 159 / 159 and 5 · 7 · 19 · 32.
   - **Not confirmed** "writes fail or time out": excluded in run 1 (0 failures). Seen only in shakedowns 1 and 2, with a
     cause outside the check (§3 rows 2, 3).
   - **Invalid run** "`ThrottledCount` stays zero and `S` never nears *C*": excluded.
5. **Observed vs. inferred.** The conclusion rests on observed readings. Inferred: (i) that the networking pool's use
   above idle is the queued large messages' frames: the pool is `BufferPools.forNetworking()`, the inbound decoders'
   allocator (source, §1.1 finding 2), its use moves with the queued count (0.12–0.15 MB with no queue; 13.5 / 13.7 MB
   with 35 queued in two different arms; 30.0 MB with 96 queued in `defres`) [inferred from the source and the
   proportionality, not from a per-buffer trace]. (ii) That the trace rebuild's excess over `P·C + G` is the print-order
   race, not real use: the global reserve's own counter, printed on every line, never exceeded *G* and the sampled
   totals never exceeded `P·C + G` [inferred; no row depends on it: the rebuild stayed inside the frozen allowance].
6. **Deviations and gaps.** Only the active connection types were loaded: urgent and small carried gossip and
   responses (≤ 870 B), so §8's "× connection types" factor is not exercised beyond one type per peer (as 9b scoped it).
   The storage was a tmpfs (§3 row 3), so `R`'s apply speed is not a disk's; it only sets how fast held messages
   complete, not the check's arithmetic. `ScheduledBytes` was recorded beside `using_bytes` but not used.
7. **Core question.** Yes. Accepted, unprocessed inbound bytes per connection stop exactly at the largest whole number of
   messages that fits `C` plus the borrowed reserve, at every capacity value, and move with it 1 : 1.4 : 3.8 : 13.4
   (Logic 2–3, parts 3); the stop is the disallow branch, seen as `INSUFFICIENT_GLOBAL` refusals and `ThrottledCount`
   (Logic 2, part 3); per-peer capacity adds up across peers while the shared reserve does not (Logic 4); the writes wait
   and all complete (Logic 5); with default reserves the same load is not throttled at all and 128 messages are held
   (Logic 6); and the held real resource follows the count (Logic 7), on the heap for small messages and in the
   off-heap networking pool for queued large ones.

**Conclusion (one line):** "Reserves low: per-peer `S` plateaus near `C` plus the reserve share and moves with *C* …"
— **Confirmed** (unit and cluster).

## 5. Self-check of run 1 — AI

### 5.1 Check of run 1's conclusion

`run1/selfcheck.py` re-parses the raw files on the node (the trace, the key logs for the windows, the inbound-table and
JMX samples, the histograms, the thread dumps and the session logs' counter lines), with its own parser and the 9a
numbers written out again, and compares with the run script's `arms.csv`: **95 checks, 95 ok** (`run1/selfcheck.out`).

| Part | Holds? | Note (file re-read) |
|---|---|---|
| 1. Validity | yes | read-back per label, hold lines and held threads, no pending hints, 0 drops/hints: `selfcheck.out` (`read-back`, `hold fired`, `no write lost` rows); the CQL handler lines counted apart (114–123 per arm) |
| 2. Readings | yes | every number in §4.1 re-derived (peaks, *n*, refusals, global max, `Mutation` counts, pool means while capped, rows and writes); the self-check's pool window starts at the first send, so `defres`'s mean reads 31.0 MB against the script's 30.0 MB (no refusal; no row depends on it) |
| 3. Matched row | yes | each clause re-checked: plateau `n·M` for 5 · 7 · 19 · 67 and 159, all refusals `INSUFFICIENT_GLOBAL`, throttled count and nanos up, per-peer peaks at *P* 2 and 4, no write lost |
| 4. Excluded rows | yes | rule checks (0 violations of 1,277–13,473 internode `acq` lines per arm), b1 = b2 `Mutation` counts, pool drift < *M*, capacity sweep strictly increasing |
| 5. Observed vs. inferred | yes | the two inferred statements are named in §4.2 part 5; neither decides a row |
| 6. Deviations and gaps | yes | — |
| 7. Core question | yes | the steps follow the audited Logic 1–7 |

### 5.2 Run 2?

**No** — 2026-10-15. The conclusion rests on observed readings that match exact predictions (*n* to the message at
four values and in the small arm, every refusal's outcome, every write accounted for), the independent self-check holds
in full, and the result neither refutes the case nor confirms a bypass.

## 8. Verdict — AI

| Tier | Verdict (§9a row) | Basis | Date |
|---|---|---|---|
| Unit | **Confirmed** — the arithmetic of `acquireCapacity` (boundary, excess-only borrowing, both refusals and their rollback, the whole-message lease and reactivation) and the limit's wiring from `Config` to the handler's `queueCapacity` hold as traced | run 1 + self-check | 2026-10-15 |
| Cluster | **Confirmed** — row 1: per-connection plateau `⌊(C + 1 MiB)/M⌋·M` = 5 · 7 · 19 · 67 messages, disallow seen (`INSUFFICIENT_GLOBAL`, `ThrottledCount`), per-peer capacity adds up across *P* = 1, 2, 4, every write completes; default reserves do not throttle the same load (128 messages held); the held real resource follows the count (deserialized `Mutation`s on the heap: all for small messages, at most `concurrent_writes` for large ones; the queued large ones as frames in the off-heap networking pool) | run 1 + self-check | 2026-10-15 |

**Feedback filed:** the case file's §10 "Stage-4 feedback" and Notes (uncommitted; commit on request). No §4–§8 text is
amended: no Refuted row fired. Recorded for stage 3, not applied: §7 and §6a hold for small messages only (large ones
wait off heap); §6b's "not dropped" holds at the receiver, but the wait has no bound of its own, and in shakedown 1 the
queue backed up into the sender, where messages expired and were hinted (§3 row 2; a shakedown observation, not a run-1
reading); the citation drifts of §1.1 rec. 8; the wait queue's whole-message lease versus the derived
`internode_max_message_size` (§1.1 finding 3).
