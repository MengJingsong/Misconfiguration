# native_transport_max_request_data_in_flight — verification solution  <!-- file: cases/native-transport-max-request-data-in-flight-setNativeTransportConcurrentRequestDataInFlightInBytes-maxRequestDataInFlightInBytes--autonomous.md -->

| Field | Value |
|---|---|
| Entry pointer | `src/java/org/apache/cassandra/config/DatabaseDescriptor.java:3386` |
| Pinned source | `cassandra-5.0.9` |
| Session / date | Claude Sonnet 5.5, Claude Code CLI, 2026-10-26 |
| Estimate | `positive` (soft cap): the limit gates admission of CQL request bytes (on-heap/direct buffers held per in-flight request); usage should plateau near the limit under load, with bounded overshoot. |
| Ground | — |

## A. Constraint trace

**A1. The constraint.** `native_transport_max_request_data_in_flight` (configuration entry, a `DataStorageSpec.LongBytesBound`), the global cap on bytes of client requests in flight. First declared at `Config.java:298` (`public volatile ... native_transport_max_request_data_in_flight = null`, with `@Replaces` old name `native_transport_max_concurrent_requests_in_bytes`, `Config.java:297`). Unit: bytes (accepts `MiB`, etc.). Default: null in Config, resolved in `DatabaseDescriptor.java:649-652` to `Runtime.getRuntime().maxMemory() / 10` (10% of max heap). Not present in the shipped `conf/cassandra.yaml` (grep finds no entry), but settable by adding the yaml key (restart needed). At runtime it is set through JMX `StorageServiceMBean.setNativeTransportMaxConcurrentRequestsInBytes` (`StorageService.java:7050-7053`) -> `ClientResourceLimits.setGlobalLimit` (`ClientResourceLimits.java:67-72`) -> the target `DatabaseDescriptor.setNativeTransportConcurrentRequestDataInFlightInBytes` (`DatabaseDescriptor.java:3384`). Target line 3386-3387: value `-1` means `maxMemory()/10`. Line 3389 stores the new bound; lines 3390-3393 recompute `native_transport_max_message_size` (min of itself and the new limit if explicitly configured, else `min(max_mutation_size, global, per_ip)`, `DatabaseDescriptor.java:3237-3245`). Startup validation: `native_transport_max_message_size` must not exceed it (`DatabaseDescriptor.java:911-912`).

Note: the target setter updates the config object only; the live limiter `GLOBAL_LIMIT` (`ClientResourceLimits.java:42`) is updated by the caller (`GLOBAL_LIMIT.setLimit`, `ClientResourceLimits.java:70`). The setter is therefore not the enforcement point.

**A2. What it caps.** Memory (heap/direct buffers holding the serialized request frames and their decoded messages), measured as one permit per byte of request body (`AbstractMessageHandler.java:131` comment: each message occupies more once inflated on-heap). The compared quantity is `ResourceLimits.Concurrent.using` vs `limit` (`ResourceLimits.java:125-143`); read via `ClientResourceLimits.getCurrentGlobalUsage()` (`ClientResourceLimits.java:~79`, returns `GLOBAL_LIMIT.using()`). It is not a cap on responses, nor on memtable, cache or disk.

**A3. Mechanism.**
1. `GLOBAL_LIMIT = new ResourceLimits.Concurrent(getGlobalLimit())` (`ClientResourceLimits.java:42`), with a global wait queue (line 43). Each connection has per-IP `Allocator` entries (line 44, 51-60), whose limit is `native_transport_max_request_data_in_flight_per_ip` (default maxMemory/40, `DatabaseDescriptor.java:654-657`).
2. V5 path (`CQLMessageHandler.processOneContainedMessage`, `CQLMessageHandler.java:178-262`): the connection first uses its own receive queue (`native_transport_receive_queue_capacity`, default 1MiB, `Config.java:302`) per `AbstractMessageHandler.acquireCapacity` (`AbstractMessageHandler.java:411-455`); only the excess beyond that is taken from global then endpoint reserve via `tryAllocate` (`ResourceLimits.java:130-143` fails if `next > limit`).
   - Default (no throw-on-overload): `acquireCapacityAndQueueOnFailure` (`CQLMessageHandler.java:~216`); failure registers on the wait queue, sets `Overload.BYTES_IN_FLIGHT`, pauses the connection (`CQLMessageHandler.java:245-256`). Processing resumes when permits are released.
   - With `THROW_ON_OVERLOAD` startup option (`StartupMessage.THROW_ON_OVERLOAD`; `CQLMessageHandler.java:198-204`): the message is discarded and an `OverloadedException` is returned.
   - Large messages (`processFirstFrameOfLargeMessage`, `CQLMessageHandler.java:516-`) acquire in the same way; `native_transport_max_message_size <= limit` prevents starvation (`CQLMessageHandler.java:640-649`).
3. Release: `releaseCapacity` once the request is fully processed (`AbstractMessageHandler.java:461-470`).
4. Pre-V5 (V4 and older) path (`PreV5Handlers.java:181-188`): `tryAllocate`; on failure it still does `endpointPayloadTracker.allocate(requestSize)` (unconditional, can exceed the limit), then pauses the connection. So the limit is a pause trigger, not a hard bound, for V4 clients; overshoot is bounded roughly by one request per connection that was already read.
Overshoots / bypasses: (a) V5 per-connection queue capacity (1MiB per connection) is outside the global limit, so total ~ limit + connections x 1MiB; (b) V4 unconditional allocate; (c) bytes already read from the socket before the pause takes effect; (d) internode and internal paths do not use it.

**A4. Other consumers.** Heap use by memtables, key/chunk/row caches, bloom filters, index summaries, compaction, repair/streaming, internode messaging (own limits `internode_application_*`), response buffers, decoded Java objects (multiplicatively larger than the wire bytes counted), and per-connection receive queues.

**A5. Evidence beyond the source.** none beyond the source (comments at `AbstractMessageHandler.java:111-131` and `CQLMessageHandler.java:640-649`). Original design: CASSANDRA-15013 (native transport backpressure); not relied on for claims.

**Amendment A (stage-4 audit, 2026-10-26; wrong or shifted citations, not load-bearing for any prediction).** (1) A global-usage gauge *is* exported in 5.0.9: `org.apache.cassandra.metrics:type=Client,name=RequestsSize` (`ClientMetrics.java:129`, `ClientResourceLimits::getCurrentGlobalUsage`), and `name=PausedConnections` (`ClientMetrics.java:145`); B3d's "not an exported gauge" is wrong. (2) `acquireCapacityAndQueueOnFailure` is called at `CQLMessageHandler.java:223` (defined `:693`), not `~:216`; the throw branch is `:195-205`. (3) The setter's recompute is `DatabaseDescriptor.java:3389-3393` (`-1` at `:3386-3387`). (4) `ClientResourceLimits.Allocator.tryAllocate/allocate/release` are package-private, so a probe must live in package `org.apache.cassandra.transport`; `EndpointAndGlobal.tryAllocate` (`ResourceLimits.java:~263`) tries the **global** limit first, then the endpoint limit. (5) `LARGE_MESSAGE_THRESHOLD` is 131,071 B (`CQLMessageHandler.java:83`): the 262,144-B requests of B3c take the large-message path in protocol v5 and the 100,000-B requests do not.

## B. Verification solution

**B1. Claim under test.** The global in-flight counter `GLOBAL_LIMIT.using()` never exceeds `native_transport_max_request_data_in_flight` by more than the documented overshoot (V5: connections x receive queue; V4: pending allocations), and the node's actual native-transport request memory (direct plus heap attributable to request buffers) plateaus near that limit when it is lowered, instead of growing with offered load.

### B2. Unit tier

**B2a. Environment and build.** JDK 11, Ant. Copy the tree to local disk (`rsync -a ~/cassandra-5.0.9/ /local/c509/`), `cd /local/c509 && ant jar`, then compile a test class against `build/classes` plus `lib/*.jar`. JVM options: `-Xmx512m -Dcassandra.config=file:///local/c509/test/conf/cassandra.yaml -Dcassandra.storagedir=/local/c509/tmpdata`. Test location: new file `/local/c509/test/unit/org/apache/cassandra/transport/GlobalInFlightLimitProbe.java` (outside the shared tree).

**B2b. Knobs.** The limit passed to `ClientResourceLimits.setGlobalLimit(long)` (which calls the target): `-1`, `1MiB`, `8MiB`, `64MiB`. With `-1` the expected stored limit is `maxMemory/10` (~51MB at 512m heap); read it back with `getGlobalLimit()`. Also set `native_transport_max_message_size` explicitly (`-D` is not available; use `DatabaseDescriptor.daemonInitialization()` with a yaml that sets it to 1MiB) in one run to test the `min` at lines 3390-3393.

**B2c. Workload.** A loop calling `ClientResourceLimits.GLOBAL_LIMIT`-equivalent allocation through a fresh `ResourceLimits.Concurrent`/`Allocator` from `getAllocatorForEndpoint` (`ClientResourceLimits.java:51`), using `tryAllocate(n)` with n = 256KiB repeatedly without release, from 4 threads. With limit 8MiB, 32 allocations of 256KiB reach the limit exactly; allocations 33+ must fail. Then release half and verify more succeed. Also drive the V4 style `tryAllocate` followed by unconditional `allocate` to show the overshoot.

**B2d. Observables and instruments.** `getCurrentGlobalUsage()`, return values (`Outcome`) of `tryAllocate`, `getGlobalLimit()`, `DatabaseDescriptor.getNativeTransportMaxMessageSizeInBytes()`. JVM heap not meaningful here; not observed. Cannot observe real buffer memory at this tier.

**B2e. Procedure.** 1) Build. 2) `daemonInitialization()`. 3) For each knob value, `setGlobalLimit(v)`, assert `getGlobalLimit()` equals the value (or maxMemory/10 for -1). 4) Run the allocation loop; record the count of successes and final usage. 5) Release all, assert usage 0. 6) Run the V4-style loop, record peak usage. 7) Print results.

**B2f. Predictions.** `-1` gives `Runtime.maxMemory()/10`. For limit L, successful `tryAllocate` total never exceeds L (usage <= L); with 256KiB chunks and L=8MiB, exactly 32 succeed. V4-style forced `allocate` pushes usage above L by the forced amount (usage > L). Explicit message size is `min(old, L)`; without explicit config it equals `min(max_mutation_size, L, per_ip)`.

**B2g. Readings.**
| Observation | Meaning |
|---|---|
| usage <= L for all tryAllocate, count = L/chunk | mechanism works as traced |
| any tryAllocate success with usage > L | claim wrong (limit not enforced) |
| usage > L only after forced allocate | V4 overshoot as traced |
| `-1` gives something other than maxMemory/10 | default derivation wrong |
| message size not min(...) | A1 recompute wrong |

**B2 amendments (stage-4 audit, 2026-10-26; none depends on a reading).**

- **B2a/B2e (procedure).** The tier is a standalone `main` class, `GlobalInFlightLimitProbe` (package `org.apache.cassandra.transport`, kept in the harness folder and compiled with `javac` into a directory outside the shared tree against `build/classes/main:build/lib/jars/*:lib/*`), run as `java -Xmx512m <jvm11 module options> -Dcassandra.config=file://<yaml> -Dcassandra.storagedir=<tmp> ... GlobalInFlightLimitProbe <mode> <L>`; **one fresh JVM per (mode, L)** (B2h). It is not run under `ant testsome` (that forks a 1 GiB JVM and overrides `-Xmx`). The copy is made with `copy-source.sh` (not `rsync` of `~/cassandra-5.0.9`), `ant build-test`, and never rebuilt afterwards.
- **B2b/B2c (per-IP pinned).** `native_transport_max_request_data_in_flight_per_ip` defaults to maxMemory/40 (12.8 MB at 512 MiB), which would bind before the 64 MiB value and cap at 12.8 MB for a reason that is not the knob. Every sweep JVM calls `ClientResourceLimits.setEndpointLimit(1GiB)` before the loop. The loop is on `getAllocatorForEndpoint(addr).tryAllocate(262144)`; 4 threads take attempts from one shared counter of `L/262144 + 16` attempts; the counter `getCurrentGlobalUsage()` is the one read at the end. After the fill: release half (`L/2`), 16 more attempts; release all; usage 0.
- **B2b (message-size JVMs).** `nativeTransportMaxMessageSizeConfiguredExplicitly` is fixed at `daemonInitialization()`, so the `min` of `:3390-3393` needs two JVMs: mode `msg-default` (yaml without the key) and mode `msg-explicit` (yaml with `native_transport_max_message_size: 1MiB`; startup default of L is maxMemory/10 = 53,687,091 B at 512 MiB, which passes the `:911-912` check).
- **B2c (V4 overshoot).** Mode `v4`: L = 8 MiB; fill to L with `tryAllocate`; then 4 times: `tryAllocate(262144)` must fail, then `allocate(262144)` (the forced allocation of `PreV5Handlers.java:182-184`); usage = 9 MiB; all further `tryAllocate` fail; release all; usage 0.

**B2f/B2g amendments (prediction and verdict lines; added before any reading).**

Prediction (exact, bytes), per fresh JVM, E = `Runtime.maxMemory()` read in the JVM:

| JVM (mode, L) | Exact expected values |
|---|---|
| `sweep` L = 1 MiB / 8 MiB / 64 MiB | `getGlobalLimit()` = L; successes = 4 / 32 / 256 (L / 262,144); failures = 16, every failure `INSUFFICIENT_GLOBAL`; usage after the fill = L; after releasing L/2 and 16 more attempts, successes = L/524,288 and usage = L; after releasing all, usage = 0 |
| `default` (no `setGlobalLimit`) and `setGlobalLimit(-1)` | `getGlobalLimit()` = E/10 in both |
| `control` L = 1 GiB | successes = attempts (L/262,144 + 16 is not reached: run 48 attempts), failures = 0 |
| `v4` L = 8 MiB | as in B2c: fill 32 successes, 4 failures then 4 forced; usage = 9 MiB = L + 4 x 262,144; later `tryAllocate` all fail |
| `msg-default` | after `setGlobalLimit(L)` for L = 1 MiB: `getNativeTransportMaxMessageSizeInBytes()` = min(`max_mutation_size`, L, per-IP limit) = 1 MiB; after `setGlobalLimit(64MiB)` (with per-IP 1 GiB): min(`max_mutation_size`, 64 MiB, 1 GiB) |
| `msg-explicit` (yaml 1 MiB) | at startup 1 MiB; after `setGlobalLimit(64MiB)` still 1 MiB; after `setGlobalLimit(524288)` = 524,288; after `setGlobalLimit(8MiB)` still 524,288 (the setter only lowers it) |

Verdict lines (a reading is matched to exactly one):

| # | Reading | Verdict | Effect |
|---|---|---|---|
| U1 | every expected value above holds, in every JVM | Confirmed | caps (hard on the V5-style `tryAllocate`; overshoot only through the forced `allocate`) |
| U2 | any `tryAllocate` succeeds with usage > L (without a forced `allocate`) | Refuted | does not cap |
| U3 | the allocation values hold but `-1`/default is not E/10, or a message-size value differs | Not confirmed (no matching row): the named derivation (A1) is wrong; the allocation result is reported separately | caps (allocation) |
| U4 | the control JVM shows failures, or the sweep shows a failure count other than 16 | Invalid (the workload or the pinned per-IP limit did not do what B2c says) | undetermined |

**B2h. Controls.** Run once with L larger than total workload (no failures expected) to show failures come from the limit; repeat with a fresh JVM per L to rule out state carried in static `GLOBAL_LIMIT`.

### B3. Cluster tier

**B3a. Environment and build.** One node, JDK 11, built from the local copy (`ant jar` in `/local/c509`). Data, commitlog, hints on a local disk directory of known size (>= 5GB free). JVM: `-Xms1g -Xmx1g` via `conf/jvm11-server.options`, `-XX:NativeMemoryTracking=summary`, `-XX:MaxDirectMemorySize=1g`. Add `native_transport_max_request_data_in_flight`, `native_transport_max_request_data_in_flight_per_ip` and `native_transport_max_message_size` to the node's `cassandra.yaml` copy; `native_transport_receive_queue_capacity: 1MiB` (default). Disable rate limiting (default false). Use `native_transport_max_threads: 4` to make requests queue behind execution so bytes accumulate in flight.

**B3b. Knobs.** Global limit L: `-1` (default, ~102MB at 1GB heap), `16MiB`, `64MiB`. Per-IP set equal to L (so it is not the binding cap), message size `1MiB`. Set at startup via yaml; one run also via JMX `StorageService.setNativeTransportMaxConcurrentRequestsInBytes` to test live change. Values chosen so L is far below heap/10 and below what offered load can reach.

**B3c. Workload.** Single client host (single IP) using `cassandra-stress` from the same build: write of 256KB blobs (`-col size=FIXED(262144)`), `-mode native cql3 protocol(version=5)` and a second run with `protocol(version=4)`, `-rate threads=256` (256 x 256KB = 64MiB offered in flight, above L=16MiB and 64MiB-ish at the boundary), `n=20000` rows or 10 minutes, whichever first. Make the node slow to drain: `-Dcassandra.commitlog_sync` default plus `concurrent_writes: 8`. Add a 10 s-compaction-free table (`compaction = SizeTiered`, defaults).

**B3d. Observables and instruments.** (1) JMX/`nodetool` metrics: `org.apache.cassandra.metrics:type=Client,name=...` and `ClientRequest` pause/overload counters; JMX attribute `getNativeTransportMaxConcurrentRequestsInBytes`; `nodetool clientstats` (connections). Global usage is not an exported gauge in 5.0.9 beyond log lines; `OverloadedException` messages print `Global: x/y bytes` (`CQLMessageHandler.java:293`) when `THROW_ON_OVERLOAD` is used. (2) Process memory: `jcmd <pid> VM.native_memory summary` and `jcmd <pid> GC.heap_info` every 5 s; Netty direct memory via JMX `java.nio:type=BufferPool,name=direct` (MemoryUsed). (3) `ps -o rss`. Cannot observe the exact per-request buffer size directly; direct-buffer pool and heap occupancy after forced `jcmd GC.run` are the proxies.

**B3e. Procedure.** 1) Build, copy conf, set data dirs to local disk, start node with L=16MiB. 2) Wait for `nodetool status` UN. 3) Create keyspace (RF1) and blob table. 4) Start the sampler loop (5 s) writing a CSV. 5) Run cassandra-stress V5 for the duration. 6) Record peak direct buffer MemoryUsed and heap after `GC.run`, and the count of `throttled` / pause events from the log. 7) Repeat for V4. 8) Stop node, restart with 64MiB then `-1`, repeat. 9) Positive control: run with a very large L (e.g. 1GiB, with `-Xmx` kept at 1g so heap/10 does not bind) and same load. 10) Stop all processes (`pkill -f cassandra`; `pgrep` to confirm none) and delete the data directory.

**B3f. Predictions.** V5: peak direct-buffer plus request heap above idle baseline is about <= L + connections x 1MiB (256 x 1MiB would be 256MiB; with 256 threads over few connections the term is small, so use `-mode ... connectionsPerHost=4` to keep it ~4MiB). So peak increment for L=16MiB is <= ~30MiB, for 64MiB <= ~100MiB, and clients see no failures but lower throughput (paused connections). V4: increment exceeds the V5 figure by up to one request per connection (256KB x 256 = 64MiB worst case). In the control (L=1GiB), increment is higher than in the L=16MiB run by a factor of at least 2 with the same offered load. Increment should scale with L between runs rather than stay flat.

**B3g. Readings.**
| Observation | Meaning |
|---|---|
| increment tracks L (16 < 64 < control), within overshoot bound | claim holds |
| increment equal across L values while the control (L=1GiB) matches | limit does not govern usage (claim wrong) |
| increment > L + overshoot bound in V5 | extra uncounted memory or enforcement gap (claim wrong) |
| V4 exceeds V5 by up to ~one request per connection | overshoot at `PreV5Handlers.java:184` confirmed |
| no pause/throttle events and the increment is below L in all runs | limit not reached; not confirmed (raise offered load) |

**B3 amendments (stage-4 audit, 2026-10-26; none depends on a reading).**

- **B3a (node and instruments).** One node on loopback `127.0.5.1` (JMX 7150, Byteman agent port 19150, native 9042 only on that address), heap `MAX_HEAP_SIZE=1G`, `-XX:MaxDirectMemorySize=4g` (B3a filed 1g; changed in this audit, before run 1: large v5 requests leave their frame buffers in the networking pool, a known source fact, so a 90 s V5/256K arm would reach 1 GiB and the JVM's out-of-memory handling would end the arm before it measures anything; the setting is not a prediction), `-XX:NativeMemoryTracking=summary`, and **`-Dio.netty.maxDirectMemory=0`** so that Netty's pooled direct buffers are JDK direct `ByteBuffer`s and appear in the `java.nio:type=BufferPool,name=direct` MXBean (as in the sibling case `native_transport_max_request_data_in_flight-releaseItem-...`). Data, commit log and hints are on a tmpfs (`/dev/shm`); the workload writes nothing (see B3c), so no disk is exercised. `native_transport_max_threads: 4`, `native_transport_timeout: 600000ms`, `read_request_timeout: 600000ms`, `native_transport_throw_on_overload: false`, `native_transport_rate_limiting_enabled: false`, `native_transport_receive_queue_capacity: 1MiB`, message size `1MiB`, per-IP limit equal to the global one in every arm.
- **B3c (workload; replaces `cassandra-stress`).** `cassandra-stress` cannot hold requests in flight: B3c's offered 256 x 256 KB = 64 MiB is also not above L = 64 MiB, and a fast node completes each request in milliseconds, so the counter would stay near zero and the limit would not be reached. The client is the in-tree `SimpleClient` (harness `NativeFlood.java`, adapted from the sibling harness): C = 4 connections, window W requests in flight on each (a response re-sends its slot), request `SELECT pk FROM ks.t WHERE pk = 0 AND v = ? ALLOW FILTERING` at ONE with a blob value (a read of an empty table: the request body is the same bytes path and nothing is written, so no memtable or commit-log traffic contaminates the heap reading, which is B3h's concern). **Hold:** a Byteman rule (harness `hold-request.btm`) sleeps 100 ms at the entry of `Dispatcher.processRequest` for these requests while a flag file exists; with 4 executor threads the node completes about 40 requests/s and the rest wait with their bytes counted. Arms: **V4/256K** (protocol v4, value 262,144 B, W = 250: 1000 requests = 250 MiB offered), **V5/256K** (protocol v5, same value and W; each request is above `LARGE_MESSAGE_THRESHOLD`), **V5/100K** (protocol v5, value 100,000 B, W = 640: 2560 requests = 244 MB offered; below the threshold, self-contained frames). V5/100K is added because large v5 requests leave their frame buffers in the networking pool (a known pre-run source fact recorded in `HANDOFF.md` Lessons, not a reading of this case): it is the control that separates the limit from that residue. Load runs 90 s, then the client drains (up to 120 s) and the flag file is removed.
- **B3b/B3e (values and node lifetimes).** L = 16 MiB, 64 MiB, **default** (global key absent; maxMemory/10 = 107,374,182 B at a 1 GiB heap; per-IP pinned to 107374182B), and the **control 1 GiB**. One fresh node start per (L, arm): 12 arms in pass 1; pass 2 repeats only L = 16 MiB (3 arms) instead of "each L twice" (cost). Before each arm: 5 s warm-up flood (C = 1, W = 4, no hold file), 10 s settle, then the idle baseline for 30 s (not 60 s). The **live arm**: start at L = 1 GiB, V4/256K; at 30 s of load, `StorageService.setNativeTransportMaxConcurrentRequestsInBytes(16777216)` through JMX (the path that reaches the target); load continues to 120 s.
- **B3d (observables).** One JMX probe every 200 ms: `Client.RequestsSize` (the counter), `Client.PausedConnections`, `java.nio:type=BufferPool,name=direct` `MemoryUsed`/`Count` (the real-resource signal), heap used; `jcmd <pid> VM.native_memory summary` (the "Other" line) every 2 s; one `jcmd <pid> GC.class_histogram` total (live heap) at the baseline and at 60 s of load; `nodetool sjk mx` reads of `NativeTransportMaxConcurrentRequestsInBytes` at the start and, in the live arm, right after the set. Gaps stay as filed: the per-request buffer is not read directly; pool slack (Netty arena chunks, 4 MiB) and uncounted header/decoded copies are inside the bound below.
- **B3e step 10 / B4.** Stop by PID (the node and the client), confirm none left with a `java` process listing, remove the tmpfs data directory; no disk beyond a few MB of logs is used (B4's 2 GB figure does not apply).

**B3f/B3g amendments (prediction and verdict lines; added before any reading).**

Definitions. MiB = 1,048,576 B. For an arm, Delta = peak `BufferPool direct MemoryUsed` during load minus the median of the 30 s idle baseline; Peak_RS = maximum `RequestsSize`. **bound(L) = 1.5 x L + 6 MiB** (this reproduces B3f's "<= ~30 MiB for 16 MiB" and "<= ~100 MiB for 64 MiB"; 153 MiB for the default).

Prediction (V4/256K and V5/100K arms, capped L = 16 MiB, 64 MiB, default):
1. Peak_RS <= L + 4 MiB (V4: one request per connection already read; V5: <= L).
2. Delta <= bound(L), with Delta(16 MiB) < Delta(64 MiB) < Delta(default) < Delta(control 1 GiB), and Delta(control) >= 2 x Delta(16 MiB) for the same arm.
3. Disallow evidence: max `PausedConnections` >= 1 in every capped arm; 0 in the control; the client sees `other_err` = 0 and fewer completions per second at smaller L.
4. Control (1 GiB): Peak_RS >= 0.8 x offered (200 MiB for V4/256K, 195 MB for V5/100K), `PausedConnections` 0.
V5/256K arm: the same relations are the filed B3f prediction for v5 and are reported separately; it is matched to rows C1/C3/C4 on its own readings, and its result alone does not decide the other arms.
Live arm: before the set Peak_RS >= 0.8 x offered; after the set `getNativeTransportMaxConcurrentRequestsInBytes` = 16,777,216; `RequestsSize` then falls (no new admissions above the limit) and, from the first sample at or below L + 4 MiB, stays <= L + 4 MiB to the end (<= 90 s after the set: it falls at about 10 MiB/s).

Verdict lines (a tier reading is matched to exactly one; arms are judged on V4/256K and V5/100K; V5/256K is listed separately):

| # | Reading | Verdict | Effect |
|---|---|---|---|
| C1 | predictions 1-4 and the live arm hold, V4/256K and V5/100K | Confirmed | caps (soft: overshoot <= one request per V4 connection) |
| C2 | Delta equal across 16 MiB / 64 MiB / default / control (spread <= 25 %) while offered load is above L | Refuted | does not cap |
| C3 | Peak_RS within prediction 1 but Delta > bound(L) in a capped arm (extra uncounted memory or a leak) | Refuted for that arm (claim "resource plateaus near L" wrong), counter still caps | caps only on some paths (bypass) |
| C4 | Peak_RS > L + 4 MiB in a capped arm | Refuted (enforcement gap) | does not cap |
| C5 | Peak_RS < 0.9 x L or `PausedConnections` 0 in a capped arm, or the control did not reach 0.8 x offered | Not confirmed (limit not reached) | undetermined |
| C6 | V4/256K Peak_RS exceeds the same-L V5/100K Peak_RS by <= C x 256 KiB x 2 | consistent with the V4 overshoot of `PreV5Handlers.java:184` (report only; no change of verdict) | - |
| C7 | the live arm violates its prediction | Refuted for the live-change path (the setter does not take effect on the live limiter) | caps only on some paths (bypass) |
| C8 | Delta cannot be measured (probe fails, baseline unstable by more than 25 % of bound(16 MiB)) | Invalid | undetermined |

**B3h. Controls.** Control run with L far above load; V4 vs V5 comparison; idle baseline sampled for 60 s before load; repeat each L twice; fix per-IP limit and message size so only the global limit changes; confirm no memtable flush spikes dominate heap by using direct-buffer MemoryUsed as the primary signal and heap measured after `GC.run`.

**B4. Risks and cleanup.** Disk: ~20000 x 256KB = ~5GB written at most; use `n` to cap at 2GB and a local filesystem of known size; commitlog/hints/saved_caches under the same local directory. No shared storage used. Copy the source before building. After each run stop node and stress (`pkill -f CassandraDaemon`, `pkill -f cassandra-stress`), verify with `pgrep -fl cassandra`, then remove the data directory and build copy.

## C. Sources read

- /users/jason92/writeup-A/playbook-autonomous.md
- /users/jason92/writeup-A/_TEMPLATE-autonomous.md
- src/java/org/apache/cassandra/config/DatabaseDescriptor.java (lines 207, 640-660, 898-915, 3237-3245, 3335-3394)
- src/java/org/apache/cassandra/config/Config.java (lines 290-305)
- src/java/org/apache/cassandra/transport/ClientResourceLimits.java (lines 40-130)
- src/java/org/apache/cassandra/transport/CQLMessageHandler.java (lines 178-262, 640-649, grep)
- src/java/org/apache/cassandra/transport/PreV5Handlers.java (lines 160-200, grep)
- src/java/org/apache/cassandra/net/ResourceLimits.java (lines 125-175, grep)
- src/java/org/apache/cassandra/net/AbstractMessageHandler.java (lines 400-440, grep)
- src/java/org/apache/cassandra/service/StorageService.java (lines 7040-7056)
- conf/cassandra.yaml (grep only)

## D. Stage-4 feedback

**Stage-4 feedback (2026-10-26, set A batch 8; results: [`stage4-runtime-verification/results/native-transport-max-request-data-in-flight-setNativeTransportConcurrentRequestDataInFlightInBytes-maxRequestDataInFlightInBytes--autonomous.md`](../../stage4-runtime-verification/results/native-transport-max-request-data-in-flight-setNativeTransportConcurrentRequestDataInFlightInBytes-maxRequestDataInFlightInBytes--autonomous.md); not committed).**

- **Audit amendments** (dated 2026-10-26, in place): Amendment A (citations; the `Client.RequestsSize` gauge exists), the B2 and B3 amendment blocks (procedure, per-IP pin, flood client plus Byteman hold instead of `cassandra-stress`, offered load, arms, `MaxDirectMemorySize` 4g), and the B2f/B2g and B3f/B3g prediction and verdict lines (U1-U4, C1-C8), frozen before run 1.
- **Unit tier: Confirmed, caps (U1).** 68 of 68 checks: the global counter admits exactly L/262,144 chunks in every fresh JVM (L = 1 / 8 / 64 MiB), never exceeds L through `tryAllocate`, the default and `-1` give maxMemory/10, the setter lowers `native_transport_max_message_size` as A1 says (and only lowers an explicit one), and the PreV5 forced `allocate` takes usage to L + 1 MiB.
- **Cluster tier: Refuted (the claim's second half), effect `caps only on some paths (bypass)`.** The counter is capped in all 12 capped arm-passes (Peak `RequestsSize` 0.985-1.047 L) and the live setter (A1's JMX path to the target) takes effect (250 MiB to 16 MiB in 23 s at the executor's drain rate). The memory does not follow it everywhere: V4/256K live heap follows L (+16.8 / +64.9 / +103.5 MiB) but the direct pool grows 2-4 x past `1.5 L + 6 MiB` (128 / 208 / 320 MiB); V5 with 100,000-B requests holds the whole offered load (+246 MiB live heap, `byte[]`) at every L including 16 MiB while the counter sits at L; V5 with 262,144-B requests adds 780-820 MiB of direct memory in 90 s at every L (the large-request frame-buffer residue). A3 step 2 and the A2/A4 text should say that the counter bounds admission, not what a V5 connection has already buffered. The Estimate line stays `positive` (not re-estimated); outcome class true positive.
- **Other:** `Client.PausedConnections` goes to about -4500 on the V5 large-message path (unpause without pause); B3d's "global usage is not an exported gauge" was wrong (`RequestsSize`).
