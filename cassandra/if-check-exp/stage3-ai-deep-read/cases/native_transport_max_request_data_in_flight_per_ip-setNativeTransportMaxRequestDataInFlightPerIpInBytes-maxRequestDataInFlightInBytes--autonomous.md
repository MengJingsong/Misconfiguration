# native_transport_max_request_data_in_flight_per_ip — verification solution  <!-- file: cases/native_transport_max_request_data_in_flight_per_ip-setNativeTransportMaxRequestDataInFlightPerIpInBytes-maxRequestDataInFlightInBytes--autonomous.md -->

| Field | Value |
|---|---|
| Entry pointer | `src/java/org/apache/cassandra/config/DatabaseDescriptor.java:3369` |
| Pinned source | `cassandra-5.0.9` |
| Session / date | Claude Sonnet 5.5 (claude-sonnet-5-5), Claude Code CLI (Agent SDK), 2026-10-26 |
| Estimate | `positive`: the per-IP limit gates how many request-payload bytes one client IP may hold in flight beyond each connection's own 1 MiB queue, so the bytes held by that IP stay near the limit (plus the per-connection allowance and forced-allocation overshoot). |
| Ground | — |

## A. Constraint trace

**A1. The constraint.** `native_transport_max_request_data_in_flight_per_ip` (configuration entry), the per-client-IP cap on inbound CQL request bytes in flight.
- Declared at `Config.java:296` (`public volatile DataStorageSpec.LongBytesBound native_transport_max_request_data_in_flight_per_ip = null;`). The old name `native_transport_max_concurrent_requests_in_bytes_per_ip` is mapped by `@Replaces` at `Config.java:295`, with the converter in `Converters.java:108`.
- The target line `DatabaseDescriptor.java:3369` is the `-1` sentinel inside `setNativeTransportMaxRequestDataInFlightPerIpInBytes(long)` (3367-3377). `-1` is replaced by `Runtime.getRuntime().maxMemory() / 40`. The setter then stores the value (3372) and recomputes `native_transport_max_message_size` (3373-3376).
- Unit: bytes. A string such as `64MiB` is accepted in yaml.
- Default: null in `Config`, resolved in `applySimpleConfig` at `DatabaseDescriptor.java:654-657` to `maxMemory()/40`, which is 2.5% of the max heap. A 4 GiB heap gives about 102 MiB. It is not in the shipped `conf/cassandra.yaml` (grep finds no entry).
- How to set it:
  - yaml key, read at startup, restart needed.
  - Runtime via JMX `StorageService.setNativeTransportMaxConcurrentRequestsInBytesPerIp(long)` (`StorageService.java:7062`, `StorageServiceMBean.java:685`). It calls `ClientResourceLimits.setEndpointLimit` (`ClientResourceLimits.java:84-91`), which calls the target setter and then `setLimit` on every live per-IP allocator.
  - Gotcha: line 90 passes the raw `newLimit` to the live allocators, not the resolved value. Passing `-1` over JMX would set live allocators to `-1`, so every `tryAllocate` would fail (`next > limit`, `ResourceLimits.java:130-140`). Only new allocators get `maxMemory/40`. Tests must not use `-1` over JMX.
- Startup validation: when `native_transport_max_message_size` is set explicitly, it must not exceed this limit (`DatabaseDescriptor.java:914-915`). When not set, the default message size is `min(max_mutation_size, global limit, per-ip limit)` (3237-3244).

**A2. What it caps.** Memory held by inbound request payloads (Netty `ByteBuf`/frame bytes, mostly off-heap pooled buffers) on behalf of one remote IP. The quantity compared is `ResourceLimits.Concurrent.using` of that IP's limit object against `limit` (`ResourceLimits.java:130-140`). For protocol V5 it counts the bytes of a request beyond the connection's own queue capacity. For V4 and earlier it counts the whole body size.

**A3. Mechanism.**
1. A per-IP `Allocator` is created on first use (`ClientResourceLimits.java:50-58`, `getAllocatorForEndpoint`; amended 2026-10-26: the filed `:73-80` was the wrong range). It builds `new ResourceLimits.Concurrent(getEndpointLimit())` and wraps it with the global limit in `EndpointAndGlobal` (`ClientResourceLimits.java:160-162`). A wait queue is created per endpoint.
2. V5 and later: `CQLMessageHandler.processOneContainedMessage` (about 180-260) calls `acquireCapacity` (`AbstractMessageHandler.java:396-460`).
   - Each connection has an exclusive `queueCapacity` (`native_transport_receive_queue_capacity`, default 1 MiB, `Config.java:302`).
   - Only the excess of `queueSize + bytes` over `queueCapacity` is taken from the reserves (`AbstractMessageHandler.java:426-436`).
   - The global limit is tried first, then the endpoint limit. If the endpoint limit fails, the global permits are returned (433) and the result is `INSUFFICIENT_ENDPOINT`.
3. Outcome when the limit is reached:
   - Default clients (no THROW_ON_OVERLOAD): the message is queued on the endpoint wait queue (`AbstractMessageHandler.java:400-401`) and the connection stops reading (`CQLMessageHandler.java:224`, `acquireCapacityAndQueueOnFailure`). Bytes are not consumed from the socket beyond what is already held.
   - THROW_ON_OVERLOAD clients: the request is discarded and an `OverloadedException` is returned (`CQLMessageHandler.java:198-204`, `discardAndThrow`).
4. V5 large (multi-frame) messages follow the same two modes (`CQLMessageHandler.java:555-620`). A message above `native_transport_max_message_size` is rejected (`:549`). The comment at 643-649 explains that the message-size ≤ per-ip invariant prevents starvation.
5. V4 and earlier: `PreV5Handlers.java:157-185` (`checkLimits`) calls `endpointPayloadTracker.tryAllocate(requestSize)`. On failure the throw mode discards the request, and the default mode force-allocates (`:184`, `allocate`), so usage can go above the limit, and pauses the connection (autoread off). Release happens when the response is flushed (`PreV5Handlers.java:100-115`).
6. Release for V5 is at `CQLMessageHandler.java:500-512` (`releaseCapacity`), when the response flush item completes.
7. Bypasses and overshoot:
   - The per-connection `queueCapacity` (1 MiB) is outside the limit. N connections from one IP can hold up to `N × 1 MiB + limit`.
   - STARTUP allocates with the unconditional `allocator.allocate()` (`InitialConnectionHandler.java:119`).
   - Pre-V5 default mode force-allocates over the limit (`PreV5Handlers.java:184`).
   - A multi-frame message already being read is not stopped mid-way ("consume the subsequent frames", `CQLMessageHandler.java:530-545` comment). Concurrent large messages can overshoot.
   - The limit applies per IP, so many source IPs are bounded only by the global limit (`native_transport_max_request_data_in_flight`, default `maxMemory/10`).

> **Amendment 2026-10-26 (stage-4 audit, source reading only, before any run).** Two more rules the traces above omit, both in the pinned source:
> (i) V5, default mode, a *contained* message (one that fits inside a single frame, so smaller than `LARGE_MESSAGE_THRESHOLD` = 131,071 B) that fails `acquireCapacity` is **still dispatched** (`CQLMessageHandler.java:223-260`: `processRequestAndUpdateMetrics(..., backpressure)` runs, then the connection is paused and the ticket registered). Its bytes are not counted until the wait queue grants a ticket. So the real bytes held can exceed the counter by one contained message per connection. A *large* message (body of at least 131,071 B, so multi-frame) is different: when the first frame fails to acquire, `processFirstFrameOfLargeMessage` returns false and nothing is dispatched (`CQLMessageHandler.java:605-648`). Every message this solution sends is large (256 KiB in B2, 4 MiB in B3), so the strict reading applies to the workload.
> (ii) V4 default mode overshoots per connection, not once in total: each `LegacyDispatchHandler` checks independently and force-allocates a refused request (`PreV5Handlers.java:182-186` (the filed `:184` is the `allocate` call)), and requests already decoded in the same read are still dispatched after the pause. With C connections the overshoot is up to C requests (plus any requests already read), not one.

**A4. Other consumers.**
- Global in-flight limit (`maxMemory/10`), which is checked first.
- Per-connection receive queues (1 MiB each).
- Decoded request objects, statements, mutations and result sets on heap, which are not counted (an amplification of the payload).
- Response buffers, which are not counted.
- Memtables, caches, compaction and internode messaging buffers, which have their own limits.
- `native_transport_max_concurrent_connections(_per_ip)` bounds the connection count, not bytes.

**A5. Evidence beyond the source.** Tests: `test/unit/org/apache/cassandra/transport/ClientResourceLimitsTest.java` (`testBackPressureWhenEndpointLimitExceeded` at line 110, `testOverloadedExceptionWhenEndpointLimitExceeded` at 188, `testChangingLimitsAtRuntime` at 307) and `NativeProtocolLimitsTestBase.java`. No external sources were relied on.

## B. Verification solution

**B1. Claim under test.** For one client IP, the bytes held by in-flight request payloads (the check's operand `endpoint.using()` and the node's actual off-heap/direct memory attributable to that IP's requests) stay at or near `native_transport_max_request_data_in_flight_per_ip` plus the per-connection allowance (`connections × native_transport_receive_queue_capacity`) and the stated forced-allocation overshoot, and move proportionally when the limit is changed. A reading that stays flat as the limit changes, or that exceeds `limit + connections × 1 MiB + one max message`, shows the claim wrong.

### B2. Unit tier

**B2a. Environment and build.** JDK 11, Ant. Copy the source to local disk (`cp -r ~/cassandra-5.0.9 /local/c509`), then `cd /local/c509 && ant jar` and `ant build-test`. Test source: a new class `test/unit/org/apache/cassandra/transport/PerIpInFlightLimitTest.java` in package `org.apache.cassandra.transport`, modelled on `ClientResourceLimitsTest` and extending `NativeProtocolLimitsTestBase`. The package is needed because `Allocator.endpointUsing()` is package-private. Run: `ant testsome -Dtest.name=org.apache.cassandra.transport.PerIpInFlightLimitTest`. JVM: `-Xmx512m` (so `maxMemory()/40` is about 12.8 MiB, known).

> **Amendment 2026-10-26 (audit, recommendations R1, R2).** The path `/local/c509` and the JVM line do not fit the node: `ant testsome` forks a 1 GiB JVM and `maxmemory` overrides `-Xmx` (HANDOFF Lessons). Run instead in the working tree `~/s4-b8-pi` on `pc12`, made by `copy-source.sh` and built with `ant build-test` (logs `~/s4-b8-pi-logs/`). The sentinel check therefore compares against `Runtime.getRuntime().maxMemory() / 40` read inside the test, not the figure 12.8 MiB. Harness: `harness/<stem>/`.

**B2b. Knobs.** Per-IP limit L via `ClientResourceLimits.setEndpointLimit(L)` (the JMX path) with L ∈ {1 MiB, 4 MiB, 16 MiB}. Also `DatabaseDescriptor.setNativeTransportMaxRequestDataInFlightPerIpInBytes(-1)` on a fresh allocator to check the sentinel resolves to `Runtime.maxMemory()/40`. Hold the global limit at 512 MiB (so it never binds). Hold `native_transport_receive_queue_capacity` at 1 MiB, then 64 KiB as a second setting, so the per-connection allowance is visible.

**B2c. Workload.** Use `SimpleClient` (protocol V5, and V4 as a second run) from 127.0.0.1. Open C = 4 connections. Block request processing so permits are not released: use `QueryHandler` stub or a `Dispatcher` latch as `ClientResourceLimitsTest.backPressureTest` does (line 118). Send 256 KiB messages until the client stops being served. Arithmetic: at L = 4 MiB and C = 4 with 1 MiB queues, the expected held total is about 4 MiB + 4 MiB = 8 MiB, which is 32 messages of 256 KiB. Sending 64 messages (16 MiB) exceeds that, so the limit is reached and passed.

> **Amendment 2026-10-26 (audit, recommendations R3, R4).** (1) *How the handler is blocked.* `backPressureTest` does not hold permits (it relies on the connection pause), so it cannot be copied for that. Block with a virtual table whose `SimpleTable` supplier waits on a `CountDownLatch`, as `testQueryUpdatesConcurrentMetricsUpdate` (line 249 onward) does; the request keeps its body bytes until the response is flushed. The message is `SELECT * FROM <vk>.<vt> /* <P x 'a'> */` with P = 262,144 (a CQL comment pads the body to S ≈ 262,2xx B, so it is a large, multi-frame message; no partition-key length limit is touched). S is measured by the harness from the encoded request, not assumed. (2) *Sending without waiting.* `SimpleClient.execute` keeps one request in flight and waits for its response, so the harness writes requests the way `execute` does (`request.attach(connection)`, `channel.writeAndFlush(singletonList(request))`, stream ids set through a dummy source envelope as `execute(List)` does) from a thread per client, and a poller thread per client drains `responseHandler.responses` (a `SynchronousQueue`, so an undrained client stalls its own event loop) and counts results and `OverloadedException`s. (3) *Offered load.* 64 messages (16 MiB) do not pass L = 16 MiB with 1 MiB queues (the held total is about 20 MiB). Every arm offers K = 48 messages per client, 192 in all (about 48 MiB): at least 2.4 times L + C x Q in every V5 arm. At most about 80 requests are held in the executor at L = 16 MiB, below the 128-thread `native_transport_max_threads`. (4) *Arms.* V5 default mode: L in {1, 4, 16} MiB x queue Q in {1 MiB, 64 KiB} (six arms); V5 THROW_ON_OVERLOAD (L = 4 MiB, Q = 1 MiB); V5 runtime change (L = 4 MiB, Q = 1 MiB, then `setEndpointLimit(8 MiB)`); V4 default and V4 THROW (L = 4 MiB); the sentinel; and controls (a), (b), (c) of B2h.

**B2d. Observables and instruments.** `Allocator.endpointUsing()` and `globallyUsing()`; `ClientResourceLimits.getCurrentIpUsage()`; `ClientMetrics` gauge `RequestsSize`; count of responses received versus sent (how many messages were admitted). Not observable directly in this tier: off-heap memory. Sampling: after each send batch, once the server side has stopped reading (poll until `endpointUsing()` is stable for 200 ms).

**B2e. Procedure.**
1. Start the test JVM with the settings above.
2. Set L. Open C connections.
3. Block the handler. Send messages in batches of 8.
4. After each batch, read `endpointUsing()` and the number admitted.
5. Release the handler and confirm `endpointUsing()` returns to 0.
6. Repeat for each L, each protocol version, each queue capacity.
7. Repeat once with `THROW_ON_OVERLOAD` set in the STARTUP options, and count `OverloadedException` replies.
8. Repeat after `setEndpointLimit(2*L)` at runtime to confirm live allocators follow.

> **Amendment 2026-10-26 (audit, R5).** Step 8: raising the limit does not wake a connection that is already paused; `setEndpointLimit` calls `setLimit` on the live allocators and nothing else (`ClientResourceLimits.java:84-91`), and the existing test signals the wait queue explicitly after lifting a limit (`ClientResourceLimitsTest.java:162-167`, `provider.endpointWaitQueue().signal()`). The harness records `endpointUsing()` and the admitted count (a) just after `setEndpointLimit(2*L)` and (b) after `new ResourceProvider.Default(allocator).endpointWaitQueue().signal()`, and row U-follow below is judged on (b). Reading (a) is recorded as information (a paused connection only resumes on the next release or signal). Step 3: "Block the handler" is the latch of B2c (1); "batches of 8" means 8 messages per client between samples, with K = 48 messages per client sent in all. Between samples the harness polls until `entered` (requests that reached the supplier) and `endpointUsing()` are unchanged for 500 ms (8 s cap). Step 7 counts `OverloadedException` replies with the pollers of B2c (2).

**B2f. Predictions (before any run).**
- V5, default mode: plateau of `endpointUsing()` ≈ L, never above L (`tryAllocate` refuses `next > limit`). Admitted bytes ≈ L + C × queueCapacity. For L = 1/4/16 MiB with C = 4 and 1 MiB queues: admitted about 5/8/20 MiB.
  *Amendment 2026-10-26 (audit, R6): the same prediction in terms of the measured S (body size of one message), so a reading can contradict it exactly.* For V5 default mode with all C connections at their queue limit: L - S < plateau <= L (a waiting message needs S of reserve, so the slack after the last admission is less than S), and admitted bytes (entered x S) - plateau <= C x Q (the bytes in the per-connection queues are the only uncounted part), and admitted bytes >= plateau.
- With 64 KiB queues: admitted about L + 0.25 MiB.
- V5, THROW_ON_OVERLOAD: the same admitted total; the excess requests return `OverloadedException`.
- V4: `endpointUsing()` counts whole bodies, with default-mode overshoot of at most one request above L (forced allocation).
  *Amendment 2026-10-26 (audit, R6; reason in A3 amendment (ii)):* the V4 overshoot is up to one request per connection (C = 4), not one in all: V4 default, L = 4 MiB: L <= plateau <= L + C x S + (requests already read when the pause took effect, at most the K sent); V4 THROW_ON_OVERLOAD: plateau <= L (the throw path uses `tryAllocate` and discards).
- Runtime change to 2L: plateau moves to about 2L without reconnecting.
- Fresh allocator with `-1`: limit = `maxMemory()/40`.

**B2g. Readings.**

| Observation | Meaning |
|---|---|
| Plateau tracks L (ratio 1:1 across L values) | Claim holds at the operand level |
| Plateau independent of L | Claim wrong: the knob does not govern this operand |
| `endpointUsing()` above `L` in V5 | Claim wrong for V5 (the code says it cannot) |
| Admitted bytes above `L + C × queueCapacity + 1 message` | Unmodelled bypass; claim wrong or incomplete |
| Plateau above L only in V4 default mode, by ≤ one request per connection (amended 2026-10-26: was "≤ one request") | Expected forced allocation (`PreV5Handlers.java:184`) |
| Limit never reached (client stopped sending, handler not blocked) | Not confirmed; rerun with a smaller L or a larger workload |
| Live allocator stays at old limit after the runtime set | Update path broken (`ClientResourceLimits.java:88-89`) |

> **Amendment 2026-10-26 (audit, R7): verdict lines.** The table above gives meanings, not verdicts. The harness prints one `U,<arm>,...` line per arm; "pass" below means the stated inequality on those lines. The verdict is the first line that applies, in this order.
>
> - **U1 Not confirmed / Invalid:** any control fails (B2h a: plateau does not follow the global limit; b: usage does not return to 0 after release, or an arm with the handler unblocked reaches the cap; c: the L = 0 arm admits more than C x Q), or an V5 default arm did not reach the limit (entered x S - C x Q < L - S, i.e. fewer messages than the limit needs).
> - **U2 Refuted (the claim is wrong):** in any V5 default arm `endpointUsing()` > L at any sample; or the plateau is the same at L = 1, 4 and 16 MiB (max - min < S); or admitted bytes - plateau > C x Q + S; or after `setEndpointLimit(8 MiB)` + signal the plateau stays <= 4 MiB.
> - **U3 Confirmed (caps on V5; V4 soft as recorded):** for all six V5 default arms, L - S < plateau <= L and 0 <= admitted bytes - plateau <= C x Q; plateaus increase with L at each Q; THROW arm: plateau <= L, `OverloadedException` count > 0 and entered + overloaded = offered (the excess is refused, not queued); runtime arm: after `setEndpointLimit(8 MiB)` + signal, 8 MiB - S < plateau <= 8 MiB; every arm returns to `endpointUsing()` = 0 after release; sentinel: `getEndpointLimit()` = `maxMemory()/40`; V4 THROW plateau <= L; V4 default plateau >= L and <= L + (C + R) x S where R is what the V4 line reports as read-ahead (recorded, never a refutation).
> - **U4 Update path broken:** U3 holds except the runtime arm (plateau after set + signal <= 4 MiB while the knob reads 8 MiB).
> - **U5 Not confirmed (no matching row):** anything else.

**B2h. Controls.** (a) Global limit set low (1 MiB) and per-IP high: the plateau tracks the global limit instead, ruling out misattributing the stop. (b) Handler not blocked: usage returns to 0 and no cap is hit. (c) Unit-only mutated check: L = 0 case expects all out-of-queue messages to be refused.
Amendment 2026-10-26 (audit, R8): with L = 0 the setter recomputes the default `native_transport_max_message_size` to 0, which would reject every large message as too big, not because of the cap. Control (c) therefore calls `DatabaseDescriptor.setNativeTransportMaxMessageSizeInBytes(1 MiB)` after setting L = 0 (a test-only breach of the message-size <= per-IP invariant in the code comment at `CQLMessageHandler.java:643-649`; the connection then waits forever, which is the "refused" outcome). Expected: admitted bytes <= C x Q and `endpointUsing()` = 0. Control (a) sets the global limit to 1 MiB and per-IP to 512 MiB; the plateau must then follow the global limit (`globallyUsing()` in (1 MiB - S, 1 MiB], `endpointUsing()` the same, since one IP).

### B3. Cluster tier

**B3a. Environment and build.** One node on local disk (data, commitlog, hints under `/local/node1/`), JDK 11, a copy of the tag built with `ant jar`. `MAX_HEAP_SIZE=2G`, `HEAP_NEWSIZE=400M` via the env, plus `-XX:MaxDirectMemorySize=2g` (so direct buffer growth is visible, not hidden by the default). Disable the rate limiter (default off). Set `native_transport_receive_queue_capacity: 64KiB` to make the per-connection allowance small. Set `native_transport_max_request_data_in_flight: 1GiB` (so global does not bind). Load generator on a second host or the same host from one IP (127.0.0.1).

> **Amendment 2026-10-26 (audit, R9 to R14).** (R9, environment) Node `pc12`, working tree `~/s4-b8-pi` (built), data, commit log, hints, saved caches on tmpfs `/dev/shm/s4-b8-pi` (lesson: spinning disk), logs `~/s4-b8-pi-logs/`. Port slot 4: the node listens on `127.0.4.1` (`listen_address`, `rpc_address`, seed), native port 9042 on that address only, JMX `7140` (set in the tree's `conf/cassandra-env.sh`), Byteman agent port `19140`. `ulimit -n 100000` in the shell that starts the node. The node is found and killed by PID (the `java` whose working directory or command line holds `~/s4-b8-pi`), never by `pkill -f`. (R10, hold) The filed text assumes requests stay in flight long enough to reach 8/32/128 MiB. A write of 4 MiB completes in milliseconds on this node and the client offers load at about the same rate, so the held total is not guaranteed to reach the larger limits (and the filed text says nothing that holds requests). Every run therefore loads a Byteman agent whose one rule holds each write to keyspace `ks` for 5 s on the mutation thread (`CLASS org.apache.cassandra.db.commitlog.CommitLog METHOD add(org.apache.cassandra.db.Mutation) AT ENTRY IF $1.getKeyspaceName().equals("ks") DO java.lang.Thread.sleep(5000L)`; rule on a Cassandra class, so no `boot:`; `JVM_EXTRA_OPTS` scoped to the `bin/cassandra` command so no client JVM loads the agent). With `concurrent_writes` 32 the node drains at most 32 writes per 5 s, so 64 clients with 4 MiB each hold about 256 MiB. The rule is the same in every run, so it is a hold-fixed setting, not a knob. (R11, timeouts) `write_request_timeout: 600000ms`, `native_transport_timeout: 600000ms` (HANDOFF Lessons: a request held more than 12 s needs the latter raised), client timeout 600 s. (R12, memory flags) `-XX:MaxDirectMemorySize=8g` instead of 2g: if V5 large-request frame buffers are retained (HANDOFF open follow-ups), 2 GiB of traffic would crash the node with `OutOfMemoryError: Direct buffer memory` and no reading; 8 GiB cannot. `-Dio.netty.maxDirectMemory=0` and `-XX:NativeMemoryTracking=summary` in every run (the sibling case showed that without the first flag Netty's pooled buffers are invisible to the `java.nio` MXBean). (R13, files) `commitlog_total_space: 512MiB`, `commitlog_segment_size` default 32MiB, `max_mutation_size: 16MiB`, `auto_snapshot: false`, `commitlog_sync` default periodic. (R14, client) one Python process with 64 `Cluster` objects, one connection each (`protocol_version` 5 or 4 per run, `token_metadata_enabled=False`, `DCAwareRoundRobinPolicy`; the driver in `lib/cassandra-driver-internal-only-3.29.0.zip` as `cqlsh` uses it), each thread a synchronous loop of prepared `INSERT INTO ks.t (k, v) VALUES (?, ?)` with a 4 MiB blob, so at most 64 requests are in flight and 256 MiB are offered at once.

**B3b. Knobs.** `native_transport_max_request_data_in_flight_per_ip` ∈ {8MiB, 32MiB, 128MiB}, set in yaml (restart) and, as a second run, via JMX `setNativeTransportMaxConcurrentRequestsInBytesPerIp` (never `-1`). Hold `native_transport_max_message_size: 8MiB` (≤ the smallest limit; valid per `DatabaseDescriptor.java:914`).

> **Amendment 2026-10-26 (audit, R15).** Each limit is run on protocol V5 (the filed claim) and, as the arms the filed B3h already requires for the forced-allocation path, on V4: six node runs r1 to r6 (r1 to r3 V5 at 8, 32, 128 MiB; r4 to r6 V4 at the same values). Rationale for V4 beside V5: HANDOFF Lessons say large native-v5 requests leave unreturned direct buffers, so the direct-memory comparison across L is confounded on V5 and is clean only on V4. The JMX variant (r9) is run on V5.

**B3c. Workload.** Table `ks.t (k int primary key, v blob)`, RF 1. 64 connections from one IP (python driver with `protocol_version=5` and a thread per connection, or `cassandra-stress user` with `-rate threads=64`). Each thread issues INSERTs of a 4 MiB blob concurrently, no throttling, for 5 minutes. *(Amended 2026-10-26, R16: each thread issues 8 INSERTs, 512 in all (2 GiB offered over a run), instead of running for 5 minutes. With the 5 s hold of B3a the run lasts about 512 / 6.4 = 80 s, and the node's disk writes are bounded by `commitlog_total_space`; the thread count, blob size, and 64 x 4 MiB = 256 MiB offered at once are as filed. Keys are the thread number, so the table holds 64 rows.)* Arithmetic: 64 × 4 MiB = 256 MiB of payload offered at once, versus limits of 8/32/128 MiB, so the lowest two limits bind and the 128 MiB one binds partially (plus 64 × 64 KiB = 4 MiB of queues). Use an unloaded memtable/commitlog setup so writes complete: `commitlog_segment_size` default, `commitlog_total_space: 512MiB`.

**B3d. Observables and instruments.**
- JMX `org.apache.cassandra.metrics:type=Client,name=RequestsSize` (global in-flight bytes) and `RequestsSizeByIpDistribution` (per-IP histogram max).
  *(Amendment 2026-10-26, R17: with one source IP and no other client traffic of size, the global count equals the per-IP count, so `RequestsSize` (an exact counter, `ClientResourceLimits.java:129`) is the primary per-IP reading; `RequestsSizeByIpDistribution` is read through a `DecayingEstimatedHistogramReservoir` whose maximum is a bucket bound (about 20 % wide), so it is recorded as a second reading and no verdict row depends on it. Also sampled every 200 ms: `PausedConnections` (`ClientMetrics.java:145`). The second-IP arm r8 is where the per-IP and global counts differ.)*
- `java.nio:type=BufferPool,name=direct` (`MemoryUsed`).
- Netty pooled arena metrics via `jcmd <pid> VM.native_memory` (needs `-XX:NativeMemoryTracking=summary`).
- Process RSS from `/proc/<pid>/status` (VmRSS), sampled every 1 s.
- Heap `jstat -gc` every 1 s.
- `OverloadedException` counts on the client; `ClientMetrics RequestDiscarded`.
- Not directly observable: how much of the direct memory belongs to request payloads versus response and other buffers.

**B3e. Procedure.**
1. Copy the tree to local disk and build.
2. Start the node with `NativeMemoryTracking` on; wait for CQL.
3. Create the schema. Record a baseline: RSS, direct pool, `RequestsSize`.
4. Run the workload for 5 minutes at L = 8 MiB; sample every second.
5. Stop the workload and wait for `RequestsSize` to reach 0.
6. Restart with L = 32 MiB, then 128 MiB, repeating steps 3-5.
7. Run the JMX variant: a single node at 128 MiB, then set 8 MiB over JMX mid-run, and watch the drop at the plateau.
8. Positive control (below).

> **Amendment 2026-10-26 (audit, R18): run list.** Steps 3 to 6 are one scripted run each, in this order; a run is node start, schema, 20 s idle baseline, 1 s NMT + 200 ms JMX sampling during the load, load, stop. r1 V5 8MiB; r2 V5 32MiB; r3 V5 128MiB; r4 V4 8MiB; r5 V4 32MiB; r6 V4 128MiB; r7 positive control (V5, global 16MiB, per-IP 128MiB); r8 two source IPs (V5, per-IP 32MiB, 32 threads from `127.0.4.1` and 32 from `127.0.4.3`, global 1GiB); r9 JMX variant (V5, 128MiB, `setNativeTransportMaxConcurrentRequestsInBytesPerIp(8388608)` over JMX from a thread started when the held total first passes 100 MiB; offered 16 INSERTs per thread so the drop is observed during the load). Step 5 (wait for `RequestsSize` 0): the client has finished and the probe continues 30 s. The idle baseline is the 20 s before the load of each run (step 3), and the probe of r1 continues for 120 s after its load as an idle-tail control.
9. Stop the node and the load generator; confirm with `pgrep -f CassandraDaemon`.

**B3f. Predictions.**
- Peak `RequestsSizeByIpDistribution` max ≤ L for each run. Peak direct pool above baseline ≈ L + 64 × 64 KiB (+ transient response buffers), so roughly 12 MiB / 36 MiB / 132 MiB above baseline.
  *Amendment 2026-10-26 (audit, R19: the direct-pool level is not predicted).* The counter prediction is kept and made exact (S = 4 MiB + about 100 B per request, measured): V5 r1 to r3: L - S < peak `RequestsSize` <= L, with `PausedConnections` max >= 1. The absolute direct-pool figure above is withdrawn: the sibling case (the global limit, closed 2026-10-22) measured the pool at 1.2 GiB above its idle baseline that did not depend on the limit, and HANDOFF Lessons say large native-v5 requests leave unreturned direct buffers; both are source-independent facts of this node, not readings of this case. What stays predicted is the direction: the direct-pool rise (peak minus idle median) increases with L at V4 (r4 < r5 < r6), where the sibling case showed that it follows the accounted bytes; whatever it does at V5 is a reading, not a prediction. V4 runs r4 to r6: L <= peak <= L + 64 x S (each of 64 connections can add one forced request, A3 amendment (ii)). r7: peak `RequestsSize` in (16 MiB - S, 16 MiB]. r8: each IP's share <= 32 MiB, the global peak > 32 MiB (up to 64 MiB). r9: after the JMX set, the held total falls to <= 8 MiB within 60 s of the last pre-set request completing, while the knob reads 8388608.
- Peak direct-pool rise is monotone in L (about 4× from 8 MiB to 32 MiB, up to the offered 256 MiB at 128 MiB).
- JMX drop to 8 MiB: `RequestsSize` falls to about 8 MiB after in-flight requests drain; no new admission above 8 MiB.
- Heap is not governed: decoded mutations on heap rise with admitted bytes but are not capped by L, so heap peak may exceed the direct-pool rise.
- Claim wrong if the peak direct-pool rise stays the same across L, or if per-IP `using` exceeds L + 4 MiB sustained.

**B3g. Readings.**

| Observation | Meaning |
|---|---|
| Per-IP max ≈ L and direct-pool rise scales with L | Claim holds |
| Per-IP max ≤ L but direct-pool rise flat across L | Operand capped, but the limit does not govern real memory (claim wrong at the resource level) |
| Per-IP max > L + 64 × queue + 1 message | Bypass larger than modelled |
| Offered load below L (limit not reached) | Not confirmed; raise concurrency or blob size |
| After the JMX drop, usage stays high | Runtime update did not reach live allocators |
| Peak RSS grows with L but heap does not | Limit governs off-heap only; state this scope |

> **Amendment 2026-10-26 (audit, R20): verdict lines.** The harness prints one reduced summary per run; "peak" is the maximum `RequestsSize` sample. The verdict is the first line that applies, in this order.
>
> - **C1 Invalid / Not confirmed:** the knob did not read back as L (`StorageService.NativeTransportMaxConcurrentRequestsInBytesPerIp`); or r1 (V5, 8 MiB) peak < 4 MiB (the limit was not reached); or the positive control r7 does not plateau in (16 MiB - S, 16 MiB]; or any client error other than `OverloadedException`; or the node died.
> - **C2 Refuted:** V5 peak > L in any of r1 to r3; or the three V5 peaks are not increasing (r1 < r2 < r3 fails).
> - **C3 Confirmed (caps on V5):** r1 to r3 all have L - S < peak <= L, increasing in L, `PausedConnections` max >= 1 in each, 512 of 512 client requests ok (back-pressure, not rejection), and the direct-pool rise (peak minus idle median) at V5 is greater at r3 than at r1; and r7 passes. V4 runs r4 to r6 are recorded and, if their peaks exceed L (up to L + 64 x S), the conclusion line adds "V4 soft cap: forced allocation, bypass as recorded".
> - **C4 Operand capped, real resource not governed:** the counter conditions of C3 hold but the V5 direct-pool rise is not greater at r3 than at r1.
> - **C5 Bypass larger than modelled:** any V4 peak > L + 64 x S, or r8 shows an IP above its own limit.
> - **C6 JMX update broken:** r9's held total stays above 8 MiB + S more than 60 s after the set, with the knob reading 8388608.
> - **C7 Not confirmed (no matching row):** anything else.

**B3h. Controls.**
- Positive control (a cap known to bind): the same workload with the global limit `native_transport_max_request_data_in_flight=16MiB` and per-IP at 128 MiB. `RequestsSize` must plateau at about 16 MiB; this shows the harness can see a binding cap.
- Idle baseline for the same duration, to separate GC and pool noise from load.
- A second source IP (127.0.0.2 as bind address, if available) to show the per-IP limits are independent and the sum is bounded only by the global limit.
- Protocol V4 run (`protocol_version=4`) to cover the forced-allocation path.
- *(Amendment 2026-10-26, R21.)* The second source IP is `127.0.4.3`, bound by the client (a socket module wrapper for the driver's connections), which is available on loopback; run r8 of B3e. The positive control is run r7 of B3e.

**B4. Risks and cleanup.** *(Amendment 2026-10-26: paths are `~/s4-b8-pi`, `/dev/shm/s4-b8-pi` (tmpfs, 126 GiB free), `~/s4-b8-pi-logs`; leftovers are checked by PID and by `ss -ltn` on 127.0.4.1; `pgrep -f` is not used.)* Disk: node data, commitlog and hints on local disk only, 20 GiB free assumed; the 4 MiB blob workload writes at most a few GiB over 5 minutes, so cap the run with `commitlog_total_space` and delete `/local/node1` after. Do not build in the shared source tree. Do not use `-1` over JMX. Stop the node, load generator and any test JVM; verify with `pgrep -f 'CassandraDaemon|ant'` and `ss -ltn | grep 9042`. Remove `/local/c509` and `/local/node1`.

## C. Sources read

- /users/jason92/writeup-A/playbook-autonomous.md
- /users/jason92/writeup-A/_TEMPLATE-autonomous.md
- src/java/org/apache/cassandra/config/DatabaseDescriptor.java (3210-3260, 3340-3400, 640-662, 895-920)
- src/java/org/apache/cassandra/config/Config.java (285-302)
- src/java/org/apache/cassandra/transport/ClientResourceLimits.java
- src/java/org/apache/cassandra/transport/CQLMessageHandler.java (180-262, 385-660)
- src/java/org/apache/cassandra/transport/PreV5Handlers.java (100-200)
- src/java/org/apache/cassandra/transport/InitialConnectionHandler.java (100-130)
- src/java/org/apache/cassandra/transport/Dispatcher.java (385-400)
- src/java/org/apache/cassandra/net/AbstractMessageHandler.java (195-215, 396-460)
- src/java/org/apache/cassandra/net/ResourceLimits.java (105-175)
- src/java/org/apache/cassandra/service/StorageService.java (7050-7070)
- src/java/org/apache/cassandra/service/StorageServiceMBean.java (684-685, by grep)
- src/java/org/apache/cassandra/metrics/ClientMetrics.java (by grep)
- conf/cassandra.yaml (by grep)
- test/unit/org/apache/cassandra/transport/ClientResourceLimitsTest.java (by grep)

## D. Stage-4 feedback

**Audit amendments (2026-10-26, stage-4 step 0, before any run).** File sha256 as filed `bea9e8ca9c3b264438d98b395429ff80b9f5048248ba550c47ea2168a16aca8e`. Amended in place, each marked "Amendment 2026-10-26" next to the text it changes: A3 (citation `:73-80` -> `:50-58`; two source-level rules the trace omitted: the V5 contained-message path dispatches a refused message, and the V4 overshoot is per connection), B2a, B2c (blocking mechanism, sending mechanism, offered load 48 messages per client, arms), B2e (step 8 needs a wait-queue signal), B2f (exact bands; V4 overshoot per connection), B2g (V4 row; verdict lines U1 to U5), B2h (control c needs a message-size override), B3a (environment, Byteman hold, timeouts, direct-memory flag, client), B3b (V4 arms), B3c (8 INSERTs per thread), B3d (primary reading), B3e (run list), B3f (absolute direct-pool figure withdrawn; exact bands), B3g (verdict lines C1 to C7), B3h (second IP), B4 (paths). No amendment depends on a reading.

**Stage-4 results (2026-10-26, run 1 at both tiers, self-checked, no run 2; results file `stage4-runtime-verification/results/<this stem>.md`).**
Unit **Confirmed (U3)** — caps: with the handler blocked, the V5 per-IP count plateaus one message below L (787,591 / 3,934,051 / 16,519,891 B at L = 1 / 4 / 16 MiB), the bytes held beyond it are exactly the per-connection queues (C x Q), THROW_ON_OVERLOAD refuses the excess (161 of 192), a live `setEndpointLimit` takes effect for paused connections only after a wait-queue signal (the filed step 8 had omitted this), and the `-1` sentinel reads `maxMemory()/40`. V4 default is soft (L + 3 messages in the unit arm).
Cluster **Not confirmed (no matching row, C7)** — the counter result is exact (V5 peak 7.9 / 31.5 / 126.0 MiB at L = 8 / 32 / 128 MiB, each one 4 MiB message below L; positive control 15.75 MiB under a 16 MiB global limit; the JMX change to 8 MiB followed) and direct memory rose only 10 % for a 16x larger L on top of a ~1.5 GiB floor, but the frozen C3 clause "`PausedConnections` max >= 1" cannot be met: on V5 the gauge reads 0 at its maximum and goes negative (-224 to -510). The user may overrule to Confirmed (C3).
Errors found in the filed text, all source-level: the V5 contained-message path dispatches a refused message and the V4 overshoot is per connection (A3); 64 messages do not pass L = 16 MiB (B2c); step 8 needs a signal (B2e); L = 0 recomputes the message size (B2h); a write does not stay in flight long enough to reach the larger limits without a hold (B3a); at a cap of L only L/S requests are in flight, so a run of fixed length at 8 MiB takes ~21 min (B3c).
Upstream candidates (JIRA check first): `Client.PausedConnections` goes negative on native protocol V5.
