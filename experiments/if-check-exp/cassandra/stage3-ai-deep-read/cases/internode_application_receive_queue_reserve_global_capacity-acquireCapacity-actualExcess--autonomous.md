# internode_application_receive_queue_reserve_global_capacity — verification solution  <!-- file: cases/internode_application_receive_queue_reserve_global_capacity-acquireCapacity-actualExcess--autonomous.md -->

| Field | Value |
|---|---|
| Entry pointer | `src/java/org/apache/cassandra/net/AbstractMessageHandler.java:447` |
| Pinned source | `cassandra-5.0.9` |
| Session / date | Claude Sonnet 5.5 (claude-sonnet-5-5), Claude Code CLI via Agent SDK, 2026-10-22 |
| Estimate | `positive`: the global (and endpoint) reserve are hard `tryAllocate` limits on in-flight inbound internode bytes, so bytes held by not-yet-processed messages cannot exceed per-connection queue + reserves. The permit unit is serialized bytes, so heap/off-heap is bounded only up to an inflation factor. |
| Ground | — |

## A. Constraint trace

**A1. The constraint.** Primary: `internode_application_receive_queue_reserve_global_capacity` (configuration entry). Closely coupled: `internode_application_receive_queue_reserve_endpoint_capacity` and `internode_application_receive_queue_capacity` (per-connection). Declared `config/Config.java:260-261` (`DataStorageSpec.IntBytesBound`, default `"512MiB"`; endpoint at `:258-259`, 128MiB; per-connection at `:256-257`, 4MiB). Unit: bytes (yaml accepts `512MiB`). Default is a literal in Config.java, not derived (commented values at `conf/cassandra.yaml:1389-1391`). Set via yaml only (old `*_in_bytes` names are deprecated aliases, `Config.java:260`); read once at construction of `MessagingService.inboundGlobalReserveLimits` (`net/MessagingService.java:309-310`), so a restart is needed. Endpoint reserve is read at `MessagingService.java:680`; per-connection at `InboundConnectionSettings.java:183`. Validation: `internode_max_message_size` must not exceed either reserve (`DatabaseDescriptor.java:974-996`).

**A2. What it caps.** Memory (serialized-size proxy for on-heap objects and the retained network frames, which are pooled/direct buffers). Quantity compared: `Concurrent.using` (`net/ResourceLimits.java:96,130-143`), the sum over all inbound internode connections of "excess" permits, i.e. bytes of received-but-not-yet-fully-processed messages beyond each connection's exclusive `queueCapacity`.

**A3. Mechanism.**
1. Size inference per message: `InboundMessageHandler.java:127` (contained) / `:211` (first frame of large message).
2. `acquireCapacity(endpoint, global, bytes, ...)` at `AbstractMessageHandler.java:396`; delegates to the 3-arg version at `:411`.
3. If `queueSize + bytes <= queueCapacity` (`:419`), take permits from the connection's own queue only; no reserve touched.
4. Else `allocatedExcess = min(queueSize + bytes - queueCapacity, bytes)` (`:426`); `globalReserve.tryAllocate` (`:428`) fails -> `INSUFFICIENT_GLOBAL`; endpoint `tryAllocate` (`:431`) fails -> roll back global, `INSUFFICIENT_ENDPOINT` (`:433-435`).
5. Caller on failure registers in the global/endpoint wait queue (`:400-403`), `throttledCount++` (`:405-406`), returns false; `InboundMessageHandler.java:140,217` then returns false so the decoder stops reading (backpressure; message bytes stay in the socket/kernel buffer, not the app).
6. On success, `queueSize` is atomically bumped (`:438`) and `actualExcess` recomputed (`:439`). **The target line (`:447`)**: because `releaseCapacity` can run on another thread between the `queueSize` read at `:413` and the `addAndGet` at `:438`, the real excess can be smaller than reserved. When `actualExcess != allocatedExcess` (only ever `<`), the difference is released to both reserves (`:449-452`) and both wait queues signalled (`:454-455`). This is a correction that keeps `using` from over-counting; it does not enforce the cap, but a bug here (wrong sign, missed release, double release) would leak or underflow `using` and make the cap too tight or too loose.
7. Release: `releaseCapacity` (`:461-474`) returns `min(oldQueueSize - queueCapacity, bytes)` to the reserves; called from `InboundMessageHandler.java:185,438-440` after processing, or on drop.
Bypass/overshoot: expired messages never acquire (`InboundMessageHandler.java:130-137, 215-217`); the per-connection `queueCapacity` (4MiB x connections) is outside the reserves, so total in-flight = sum(queueCapacity) + at most 512MiB global; one message larger than the unspent reserve is blocked by the `internode_max_message_size` validation above. Permits count serialized bytes only, so heap used by deserialized objects can exceed the permit total (acknowledged in class javadoc `AbstractMessageHandler.java:131-132`). Permits are held until the verb handler finishes (`InboundMessageHandler.java:438`), not until memory is freed.

**A4. Other consumers.** The same class is the base for `transport/CQLMessageHandler` (separate native-transport limits, not this constraint). Memtables, row/key/chunk caches, BufferPool (frames are allocated from it), outbound send queues (`internode_application_send_queue_*`), hints, streaming, and executor queues of already-accepted messages share the heap and direct memory.

**A5. Evidence beyond the source.** In-tree docs only: class javadoc `AbstractMessageHandler.java:103-133`; `conf/cassandra.yaml:1376-1391`; CASSANDRA-15066 (internode messaging rewrite, introduced this flow control) as background, not relied on for any claim.

## B. Verification solution

**B1. Claim under test.** Total reserve permits in use never exceed `internode_application_receive_queue_reserve_global_capacity`, and node memory attributable to inbound internode messages stops growing with offered load once that limit is hit, rather than growing without bound; and the `:447` release path returns exactly `allocatedExcess - actualExcess` so `using` returns to 0 when traffic stops.

### B2. Unit tier

**B2a. Environment and build.** JDK 11, Ant. Clone the tag to local disk (e.g. `/tmp/$USER/c509`, never the shared clone); `ant jar` then run a new JUnit test (kept outside the shared clone, copied into the local clone's `test/unit/org/apache/cassandra/net/`). Model it on `ResourceLimitsTest.java` and `ConnectionTest.java` in that directory. JVM opts: `-Xmx512m -Dcassandra.config=file:///.../cassandra.yaml` (test default config).

**B2b. Knobs.** Handler `queueCapacity` Q in {1 KiB, 64 KiB}; `ResourceLimits.Concurrent` endpoint E = 256 KiB and global G in {128 KiB, 512 KiB, 2 MiB}. Constructed directly (constructor `AbstractMessageHandler.java:167`) via a minimal test subclass or an `InboundMessageHandler` over an embedded Netty channel; no yaml needed.

**B2c. Workload.** Message size S = 16 KiB. Call `acquireCapacity(E, G, S)` repeatedly from one thread (the "event loop") without releasing: expect permits to exhaust at Q + min(E, G). Example G=128 KiB, Q=64 KiB: first 4 succeed on queue, next 8 draw reserves, 13th returns INSUFFICIENT_GLOBAL (64+128 = 192 KiB = 12 messages). Race scenario for line 447: a second thread loops `releaseCapacity(S)` concurrently while the first loops acquire, so `queueSize` drops between `:413` and `:438`; this makes `actualExcess < allocatedExcess` occur. A deterministic variant uses a subclass hook (or a `Limit` wrapper whose `tryAllocate` calls `releaseCapacity` on the same handler) to force the interleaving.

**B2d. Observables and instruments.** `G.using()`, `E.using()`, handler `queueSize` (package-private, test in package `org.apache.cassandra.net`), return values, wait-queue signalled flag, `throttledCount`. Sample after every call and at end. Not observable: real memory (that is the cluster tier).

**B2e. Procedure.**
1. Copy the test into the local clone; `ant build-test` is not required beyond `ant jar` plus `ant testsome -Dtest.name=<Class>`.
2. Run the sequential-exhaustion scenario for each (Q, G) pair.
3. Run the concurrent acquire/release scenario for 10^6 iterations, then stop releasing and drain all permits.
4. Assert invariants after every step: `0 <= G.using() <= G.limit()`, `E.using() == G.using()` for a single endpoint, `G.using() == max(0, queueSize - Q)` when quiescent.

**B2f. Predictions.** Sequential: successes = floor((Q + min(E,G)) / S); the next call returns INSUFFICIENT_GLOBAL when G < E, INSUFFICIENT_ENDPOINT when E < G; `G.using()` never exceeds G. Concurrent: `G.using() <= G.limit()` at every sample; after draining all releases `G.using() == 0` and `E.using() == 0`; the `:449-452` branch is entered at least once (count via a debugger-free counter in the test subclass or by a `Limit` wrapper counting `release` calls with excess > 0).

**B2g. Readings.**

| Observation | Meaning |
|---|---|
| using <= limit always, drains to 0, branch at `:447` hit | claim holds, release path balanced |
| using > limit at any sample | cap not enforced (claim wrong) |
| using > 0 after drain | `:447` correction leaks or a double release (claim wrong on the accounting part) |
| using < 0 or release exceeds allocation | over-release at `:451-452` (claim wrong) |
| branch never hit | race not produced; use the deterministic hook; not confirmed |

**B2h. Controls.** Same workload with Q large enough (>= total offered bytes): reserves untouched (`G.using() == 0`), showing reserves are used only beyond Q. Single-thread run (no concurrent release) must never enter the `:447` branch.

### B3. Cluster tier

**B3a. Environment and build.** Two nodes (A = target, B = load/peer) on local disk, JDK 11, built from a local clone with `ant jar`. Heap fixed `-Xms1g -Xmx1g` on A; `data_file_directories`, `commitlog_directory`, `hints_directory`, `saved_caches_directory` on local disk of known size (>= 10 GiB free). Use `ccm` or two hand-configured nodes on loopback aliases.

**B3b. Knobs.** On A (yaml, restart per value): `internode_application_receive_queue_reserve_global_capacity` in {4MiB, 32MiB, 512MiB}; keep `internode_application_receive_queue_reserve_endpoint_capacity` = same as global (must be >= `internode_max_message_size`) and `internode_application_receive_queue_capacity: 1MiB` to make reserves the dominant term. Slow the consumer: on A, `concurrent_writes: 2` and mutation stage busy (large writes with a `commitlog_sync: batch` or throttle A's disk by placing the commitlog on a small slow device if available; otherwise rely on large mutations).

**B3c. Workload.** From B, drive writes with replication factor 2 at consistency ONE so every mutation is forwarded to A: `cassandra-stress` with 256 KiB blobs (`-col size=FIXED(262144)`), 64 threads, 120 s per value. Offered inflight to A = 64 x 256 KiB = 16 MiB, so G = 4MiB must bind, 32MiB is borderline, 512MiB does not bind. Add a second sender (node C or second stress process with more threads) if the first cannot saturate.

**B3d. Observables and instruments.** On A: `nodetool sjk` / `jcmd <pid> GC.heap_info` and `jcmd <pid> VM.native_memory summary` (needs `-XX:NativeMemoryTracking=summary`) every 2 s; BufferPool/direct-memory via JMX `java.nio:type=BufferPool,name=direct`; virtual table `select * from system_views.internode_inbound` (`USING_RESERVE_BYTES`, `db/virtual/InternodeInboundTable.java:119`) and JMX InternodeInbound metrics `ThrottledCount/ThrottledNanos`; `nodetool tpstats` for pending MutationStage. Not directly observable: global `using` (only endpoint `using` is exposed via the table).

**B3e. Procedure.**
1. Local clone, `ant jar`; configure A and B; start both; create keyspace RF=2, table with a blob column.
2. For each G: set yaml, restart A, warm up 20 s, start sampling, run stress 120 s, stop stress, wait 60 s idle, sample, stop nodes.
3. Collect peak and idle values of direct-buffer memory, old-gen used, `USING_RESERVE_BYTES`, `ThrottledCount`.
4. Kill all Cassandra/stress processes; verify with `pgrep -f cassandra`; delete data dirs.

**B3f. Predictions.** `USING_RESERVE_BYTES` peak <= G for every setting (<= 4MiB, <= 32MiB); `ThrottledCount` > 0 for G=4MiB, ~0 for G=512MiB; peak inbound-attributable memory (direct buffers + retained mutation heap) grows with G over {4,32} MiB and is flat or load-limited between 32MiB and 512MiB since offered inflight is only ~16 MiB; `USING_RESERVE_BYTES` returns to 0 at idle. Peak memory growth from G=4MiB to 32MiB is roughly the permit delta times an inflation factor of about 1 to 3.

**B3g. Readings.**

| Observation | Meaning |
|---|---|
| reserve use capped at G, throttling at small G, memory tracks G | claim holds |
| `USING_RESERVE_BYTES` > G | cap not enforced (claim wrong) |
| `USING_RESERVE_BYTES` capped but heap/direct memory identical across G with throttling present | permit does not translate to memory (inflation or other consumers dominate); partial |
| no throttling at G=4MiB | load did not reach the limit; not confirmed, raise offered load |
| nonzero `USING_RESERVE_BYTES` at idle | `:447`/release leak (accounting wrong) |

**B3h. Controls.** Positive control: same workload with the per-connection `internode_application_receive_queue_capacity` varied (1MiB vs 16MiB) where the cap is known to bind; memory should move. Baseline run with no stress to bound heap noise; force a full GC (`jcmd GC.run`) before each reading to separate retained from garbage.

**B4. Risks and cleanup.** Disk: 120 s x ~100 MB/s worst case ~12 GB per value on each node; keep data on local disk and delete between values. No shared storage or shared clone writes. Leftover processes: `pkill -f CassandraDaemon`, `pkill -f cassandra-stress`, then `pgrep` to confirm none. Unit tier is memory only (<= 512 MB heap).

**Audit amendments (stage 4 step 0, 2026-10-22).** Made before any harness run or reading; each is justified by the source or by arithmetic, not by a reading (results file §1.1 gives the reason for each). B1, B2f and B3f are kept as filed; the amendments add concrete values, add conclusions rows, and fix reading rules. Where an amendment corrects text above, the amendment governs.

- **R1 (B2c, B2e, B2f: the exact sequential values and the deterministic hook).** S = 16 KiB, E = 256 KiB, one acquiring thread, no release. Successes = floor((Q + min(E, G)) / S) because message n borrows n·S − Q (Q < S) or S once the queue is full; the next 3-argument call returns `INSUFFICIENT_GLOBAL` when G < E (the global reserve is tried first, `:428`), else `INSUFFICIENT_ENDPOINT` (`:431`, with the global permits rolled back at `:432`, so `E.using() == G.using()` after it). Expected: Q = 1 KiB: G = 128 KiB 8 successes (reserve 127 KiB) then GLOBAL; G = 512 KiB and 2 MiB 16 then ENDPOINT. Q = 64 KiB: G = 128 KiB 12 then GLOBAL (the example in B2c); G = 512 KiB and 2 MiB 20 then ENDPOINT. The `:447` branch needs `actualExcess < allocatedExcess`, i.e. a release between `:413` and `:438`. The deterministic hook is a `Limit` wrapper passed as the global reserve to the 3-argument `acquireCapacity` whose `tryAllocate` first calls `handler.releaseCapacity(x)`, while the handler's own reserve fields (used by `releaseCapacity`) are the raw `Concurrent` limits. With Q = 1024, E = G = 2048, the handler first holding `q0` bytes: (H1) q0 = 1624 (reserve 600), acquire 600, hook releases 1624: after, q = 600, E = G = 0 (allocated 600, branch releases all 600); (H2) q0 = 1124 (reserve 100), acquire 600, hook releases 500: after, q = 1224, E = G = 200 (= q − Q, branch releases 400); (H3) no hook: the single-thread sequences never enter the branch. The number of branch entries is the number of `release(>0)` calls the acquire path makes on a wrapper of the endpoint reserve (only the `:449` branch releases the endpoint reserve inside `acquireCapacity`). The concurrent scenario (B2e step 3) is 10^6 acquires of 1 to 600 bytes by one thread against 4 releasing threads, Q = 1024, E = G = 2048, counting branch entries; a zero count there does not by itself make the unit tier "not confirmed" (B2c names H1/H2 as the deterministic variant): see the added row 5b.
- **R2 (B2e step 4, B2h: sensitivity control).** The test must fail on two mutants that exist only in a separate local clone (reverted and removed afterwards): M1 removes `globalReserve.release(excess)` at `:450` (H1 leaves G.using = 600 after the drain: a leak) and M2 sets `excess = allocatedExcess` at `:448` (releases the whole allocation: H2 ends at E = G = 0 instead of 200, and the later drain over-releases, `UnrecoverableIllegalStateException`). A control with Q ≥ the offered bytes (1 MiB, 40 messages of 16 KiB) must leave `G.using() == 0`.
- **R3 (B2g: rows added, same style as the table).** 1b: sequential success count or refusal outcome differs from R1's values, but `using` never exceeds its limit: the cap holds, B2f's arithmetic is wrong (partial, not Confirmed). 5b: the natural race entered the branch zero times but H1 and H2 matched: the `:447` correction is shown by the deterministic variant only (Confirmed, the zero recorded). 6: H1 or H2 produce a (q, E, G) other than R1's, or the drain is not (0, 0): the `:447` accounting is wrong (claim wrong). 7: a mutant (R2) passes the test: the test cannot see the property (Not confirmed).
- **R4 (B3c: workload).** CL=ONE does not make the client wait for the forwarded replica (the coordinator is itself a replica and answers when its local write is done), so "offered inflight = 64 x 256 KiB = 16 MiB" does not hold: the backlog would be set by the sender's send queues, not the client. Use `cl=ALL` (the client waits for the target's acknowledgement, a closed loop whose in-flight bytes to A are threads x 256 KiB), 192 threads (48 MiB offered: binds at 4 and 32 MiB, whose ceilings Q + G are 5 and 33 MiB, and not at 512 MiB), `no-warmup` (a user-mode warm-up of 5,000 writes at the held rate would take minutes), `duration=120s` (B3c's 120 s). Stress writes 256 KiB blobs, one row per partition, to a table created with replication `datacenter1: 2`.
- **R4a (runbook defect 1, found in run 1 attempt 1, 2026-10-22 08:10 MDT; workload fix only, no row or prediction changed).** With 192 stress threads at `cl=ALL` the target never held more than 128 messages (accounted peak 33,562,368 B = 128 x 262,206 B at both 32 MiB and 512 MiB; no throttling at 32 MiB, whose ceiling Q + G is 34,603,008 B), because a write at `cl=ALL` holds one of the sender's `Native-Transport-Requests` threads until the replica answers and `native_transport_max_threads` defaults to 128 (`Config.java`). R4's "192 x 256 KiB offered" therefore did not reach node A. Fix: `native_transport_max_threads: 256` on the sender (node B) only; the stress threads stay 192. The affected tier (cluster) restarts from its beginning; attempt 1's logs are kept as `run1a` and listed in the results file.
- **R5 (B3a, B3b: the slow consumer and the timeouts).** B3b's "mutation stage busy" is a Byteman rule on A: while a flag file exists, `MutationVerbHandler.doVerb` sleeps 20 ms at entry, with `concurrent_writes: 2` as filed (about 100 messages/s of service, so the closed loop of R4 fills the reserve). `write_request_timeout` and `native_transport_timeout` are both 60000ms on both nodes, `hinted_handoff_enabled: false`, `auto_snapshot: false` (a coordinator stamps the nearer of the two timeouts on the forwarded mutation, and an expired inbound message is skipped before capacity is acquired, `InboundMessageHandler.java:130-138`; the 2 s default would hide the limit). A is heap 1 GiB fixed (`-Xms1g -Xmx1g`), `memtable_allocation_type: offheap_buffers` on A, NMT summary on A; B uses 2 GiB.
- **R6 (B3b, B3e: the runs).** One lifetime of both nodes per label, A restarted for each: `g4` (E = G = 4 MiB, Q = 1 MiB), `g32` (32 MiB), `g512` (512 MiB), `ctlq16` (B3h positive control: E = G = 4 MiB, Q = 16 MiB, so the ceiling is 20 MiB), `base` (the `g4` yaml, no stress, 120 s of the same samples: the heap-noise baseline). Nodes A (127.0.0.2, target, Byteman and the samplers) and B (127.0.0.3, sender, stress target) are two JVMs on one host on loopback; node data is on a tmpfs (local RAM), wiped after each label.
- **R7 (B3d: what is observable).** With one sender, the endpoint reserve's `using` equals the global reserve's `using` whenever the two limits are equal (E = G), so `system_views.internode_inbound.using_reserve_bytes` is also the global figure in these runs; a Byteman trace on `acquireCapacity` reports both limits' `using` and `limit` at every call (and the data handler's `queueSize`), which is the exact check for "never above G". `ThrottledCount` is the JMX `InboundConnection` metric (scope = sender).
- **R8 (B3f, B3g: reading rules fixed before any reading; they implement B3f's words and do not change its numbers).** acc = the largest `queueSize` after a SUCCESS acquire on the sender's large-message handler (the "accounted peak"; its ceiling is Q + G). Memory M = retained heap + pool: the peak, over the histograms taken from 2 s after the load reaches A (every 10 s, after `GC.run`), of live `Mutation` + `[B` bytes above the idle histogram's, plus the peak of the networking BufferPool `UsedSize` above its idle mean. "Memory grows with G over {4, 32}" = M(g32) - M(g4) is at least 10 MiB and at least 2 x the `base` run's range of the same quantity; the inflation factor r = (M(g32) - M(g4)) / (acc(g32) - acc(g4)) must lie in [1, 3] (B3f's "about 1 to 3"). "Flat or load-limited between 32 and 512" = `ThrottledCount` delta <= 1 % of the messages received at 512 MiB and M(g512) <= 3 x acc(g512). "Throttling at 4 MiB" = `ThrottledCount` delta > 0 and a non-SUCCESS acquire outcome in the trace; "~0 at 512" = `ThrottledCount` delta <= 1 % of messages received. "Returns to 0 at idle" = `using_reserve_bytes` 0 and trace `ep`/`gl` using 0 after the drain. B3h positive control passes when M(ctlq16) - M(g4) >= 15 MiB (the Q delta at inflation 1) and acc(ctlq16) > acc(g4).
- **R9 (B3g: rows added).** 6: reserve <= G, throttling at 4 MiB, M rises with G, but r is outside [1, 3] (or the 512 MiB clause fails): the cap and the memory growth hold, B3f's inflation sub-prediction is missed (Confirmed, the miss recorded). 7: no throttling at `g32` (the offered load did not reach 33 MiB): the claim is tested at 4 MiB and in the control only (partial). 8: the positive control (R8) does not move M: the instruments cannot show an effect, Not confirmed.
- **R10 (B4: disk and environment).** The ceilings are small (about 100 messages/s x 256 KiB = 25 MiB/s, 3 GB per node per label, on a tmpfs sized 80 GiB, wiped after each label); the node's disk is not used for node data. The run node is `pc06`, one host for both nodes, not two machines.

## C. Sources read

- playbook-autonomous.md, _TEMPLATE-autonomous.md (stage3 folder)
- src/java/org/apache/cassandra/net/AbstractMessageHandler.java
- src/java/org/apache/cassandra/net/InboundMessageHandler.java (excerpts)
- src/java/org/apache/cassandra/net/InboundMessageHandlers.java (excerpts)
- src/java/org/apache/cassandra/net/ResourceLimits.java (Concurrent)
- src/java/org/apache/cassandra/net/MessagingService.java (grep)
- src/java/org/apache/cassandra/net/InboundConnectionSettings.java (grep)
- src/java/org/apache/cassandra/config/Config.java, DatabaseDescriptor.java (grep)
- conf/cassandra.yaml (grep); test/unit/org/apache/cassandra/net (directory listing, grep of ConnectionTest.java)

## D. Stage-4 feedback

**2026-10-22 — run 1 (stage 4), closed; no run 2.** Results:
[`stage4-runtime-verification/results/internode_application_receive_queue_reserve_global_capacity-acquireCapacity-actualExcess--autonomous.md`](../../stage4-runtime-verification/results/internode_application_receive_queue_reserve_global_capacity-acquireCapacity-actualExcess--autonomous.md);
harness `stage4-runtime-verification/harness/internode_application_receive_queue_reserve_global_capacity-acquireCapacity-actualExcess--autonomous/`
(not committed). Frozen sha256 (whole file, after amendments R1-R10 and R4a, section D "none yet"): `3a7804acd1f3b1830dc117f287b65208d377e1afb34ff1b4997cbedc9baecfb3`. Two loopback JVMs on `pc06`, node data on a tmpfs.

- **Unit (B2): Confirmed - B2g row 1, caps.** 149 checks, 0 mismatches: successes 8 / 16 / 16 (Q 1 KiB) and 12 / 20 / 20 (Q 64 KiB) at G = 128 KiB / 512 KiB / 2 MiB = floor((Q + min(E,G))/S), refusal `INSUFFICIENT_GLOBAL` only at G < E; the deterministic hook entered the `:447` branch once per scenario with the exact release (H1: 600 of 600, ends (600,0,0); H2: 400 of 600, ends (1224,200,200)); 10^6 acquires against 4 releasers entered it **8,218 times**, `using` never above 2048, final (0,0,0). Mutants M1 (no global release) and M2 (`excess = allocatedExcess`) both fail the test (R2).
- **Cluster (B3): Confirmed - B3g row 1, caps.** Accounted peak 4,981,914 / 34,348,986 B at G = 4 / 32 MiB (Q 1 MiB; ceilings 5,242,880 / 34,603,008), reserve `using` 3,933,338 / 33,300,410 B (= acc - Q, never above G, trace and vtable equal), `ThrottledCount` 10,226 / 9,674, and 0 throttling at the default 512 MiB (acc 50.3 MB = the 192 messages offered). Memory attributable to the held messages (pool + heap) 11.2 / 56.2 / 75.1 MB; inflation r = 1.53 for the 4 -> 32 MiB step (B3f: 1 to 3); positive control (Q 1 -> 16 MiB at G = 4 MiB) +24.1 MB. All reserves back to 0 after each drain.
- **Refines B1 / A3.** The memory of held inbound messages is **not on the heap**: live `Mutation` instances stay at 2 and the retained heap is flat (about 4.2 MB) at every G, while the networking BufferPool grows 7.0 -> 52.0 -> 70.9 MB (1.4 to 1.5 x the accounted bytes). A3's "bounded only up to an inflation factor" holds, with the factor applying to the off-heap pool.
- **Runbook defects.** (1) B3c's "192 x 256 KiB offered" was not reached: a `cl=ALL` write holds one sender `Native-Transport-Requests` thread and `native_transport_max_threads` defaults to 128, so attempt 1 held at most 128 messages (no throttling at 32 MiB); fixed in R4a (`native_transport_max_threads: 256` on the sender), cluster tier restarted. (2) CL=ONE (the filed value) does not bound the offered in-flight; R4. (3) The slow consumer needs a concrete rule (Byteman 20 ms hold with `concurrent_writes: 2`) and 60 s timeouts (R5).
- **Gaps for stage 3.** The `:447` branch is shown by the unit tier (hook and natural race) but not counted on a node; a per-branch Byteman counter would close it. The default 512 MiB reserve never binds with this load (acc 50.3 MB), so the cap at the default is shown by the 4 and 32 MiB points, not by reaching 512 MiB.

