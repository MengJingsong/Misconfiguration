# native_transport_max_request_data_in_flight (max message size must not exceed it) — verification solution  <!-- file: cases/native_transport_max_request_data_in_flight-applysimpleconfig-maxmessagesize--autonomous.md -->

| Field | Value |
|---|---|
| Entry pointer | [`DatabaseDescriptor.java:911`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/DatabaseDescriptor.java#L911) |
| Pinned source | `cassandra-5.0.9` |
| Session / date | Claude Sonnet 5.5, Claude Code CLI, 2026-10-27 |
| Estimate | `positive`: the check forces every admissible CQL message to fit within the in-flight byte limit, and that limit is what the request-limiter enforces on buffered request bytes (heap/off-heap). Whether the limiter bounds real memory is what B tests. |
| Ground | — |

**Type:** non-config (runtime-queried: default of the compared limit is `Runtime.getRuntime().maxMemory() / 10`, which contains the numeric literal 10; both operands are otherwise yaml entries)

## A. Constraint trace

**A1. The constraint.** `native_transport_max_request_data_in_flight` (global in-flight request bytes) is the compared limit; `native_transport_max_message_size` is the left operand. Kind: yaml entry, `volatile DataStorageSpec.LongBytesBound`, declared at [`Config.java:298`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/Config.java#L298) (message size at [`Config.java:288`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/Config.java#L288)). Unit: bytes. Default of the in-flight limit: null in `Config`, resolved at [`DatabaseDescriptor.java:649-652`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/DatabaseDescriptor.java#L649-L652) to `Runtime.getRuntime().maxMemory() / 10` (10% of max heap). The literal `10` (and the runtime heap query) is the constant that takes part in the compared value, so under the constant rule this row is non-config and written up. The same check is not reached via a literal inside the `if` itself. Settable: yaml keys, old names `native_transport_max_concurrent_requests_in_bytes`; also a runtime setter [`setNativeTransportConcurrentRequestDataInFlightInBytes`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/DatabaseDescriptor.java#L3384) (JMX, which does not rerun this check; it clamps the message size at 3389-3393). Yaml needs a restart. Neither key is in the shipped `conf/cassandra.yaml` (grep found no match), so the defaults apply unless uncommented.

**A2. What it caps.** Heap/off-heap bytes of CQL request payload currently held (received but not yet processed/responded), per `ClientResourceLimits` (`ClientResourceLimits.java:64`). The check's quantity: the maximum single message size `native_transport_max_message_size` vs that total in-flight capacity.

**A3. Mechanism.** Enclosing method: `DatabaseDescriptor.applySimpleConfig` (config apply, run at startup). At [`DatabaseDescriptor.java:911`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/DatabaseDescriptor.java#L911) (inside the `else` of `native_transport_max_message_size == null`, 903-917, so only when the message size is set explicitly): `maxCqlMessageSize = native_transport_max_message_size.toBytes()` (910) is compared with `native_transport_max_request_data_in_flight.toBytes()` (already defaulted at 649-652, earlier in the same method). True: `ConfigurationException` (912) and the node does not start. False: continue; line 914 repeats it with the per-IP limit. If the message size is unset, it defaults to `min(max_mutation_size, min(in_flight, in_flight_per_ip))` (3237-3245), so the invariant holds by construction. Runtime enforcement: `CQLMessageHandler.java:551` rejects messages above the max message size; `CQLMessageHandler.java:641-643` comments that the startup invariant prevents a single large message from starving forever for capacity. Bypasses: the JMX/test setters at 3379-3393 clamp message size down but do not recheck a raised message size; `Math.min` with per-IP limits applies only at the setter.

**A4. Other consumers.** Heap used by memtables, caches, repair, compaction, and already-decoded requests beyond the limiter's accounting; Netty buffers for the receive queue (`native_transport_receive_queue_capacity`, 1 MiB per connection); the in-flight limit does not account for response bytes.

**A5. Evidence beyond the source.** Comment at `CQLMessageHandler.java:641-643`; the `Config.java:294-296` note on defaults (CASSANDRA-ticket text in the source). No external docs relied on.

## B. Verification solution

**B1. Claim under test.** Raising or lowering `native_transport_max_request_data_in_flight` (with `native_transport_max_message_size` set at or below it) bounds the request bytes the node holds in memory, and a message size set above the limit is refused at startup.

### B2. Unit tier

**B2a. Environment and build.** JDK 11, Ant; copy the tag to a private directory, `ant jar`; a small JUnit/main class using `DatabaseDescriptor.daemonInitialization` with a `Config` object (do not touch the shared tree). JVM `-Xmx512m`.

**B2b. Knobs.** `native_transport_max_request_data_in_flight` set to 64MiB, 128MiB, unset (default = 51.2MiB at `-Xmx512m`); `native_transport_max_message_size` at 32MiB, 64MiB, 65MiB; set programmatically on `Config` before `applyAll`.

**B2c. Workload.** No traffic; only config application: pairs (message, in_flight) = (32, 64), (64, 64), (65, 64), (32, unset), (64, unset).

**B2d. Observables and instruments.** Whether `ConfigurationException` with the message at line 912 is thrown; the resulting `getNativeTransportMaxMessageSizeInBytes()` and `getNativeTransportMaxRequestDataInFlightInBytes()`.

**B2e. Procedure.** Build; run the class once per pair in a fresh JVM (the config is static); record the outcome.

**B2f. Predictions.** (32,64) and (64,64): accepted. (65,64): exception at line 912. (32, unset) with 512 MiB heap: accepted only if 32 MiB <= 51.2 MiB (yes); (64, unset): exception because 64 MiB > 51.2 MiB.

**B2g. Readings.**

| Observation | Meaning |
|---|---|
| Exception exactly when message size > in-flight | check works as stated |
| (64, unset) accepted | default not applied before the check, claim wrong |
| Exception for message <= limit | off-by-one or different operand, claim wrong |

**B2h. Controls.** The per-IP check at 914 held loose (per-IP set above message size) so only line 911 can fail; also the same pairs with the message size unset to show the defaulting path.

### B3. Cluster tier

**B3a. Environment and build.** One node, built from a private copy of the tag, `-Xmx1G`, JDK 11; `cassandra.yaml` with `native_transport_max_request_data_in_flight`, `native_transport_max_message_size`, `native_transport_max_request_data_in_flight_per_ip` set explicitly.

**B3b. Knobs.** in_flight 16MiB vs 128MiB; message size 8MiB fixed; per-IP at 128MiB so only the global limit binds; `native_transport_max_threads: 2` so requests queue.

**B3c. Workload.** Many concurrent client connections (e.g. 64 via cassandra-stress or a driver script) each sending 4MiB blob inserts (`INSERT ... blob` of 4MiB), saturating 64 x 4MiB = 256MiB offered, above 16MiB and above 128MiB nothing is held to the same extent. Run 2 minutes each.

**B3d. Observables and instruments.** `ClientMetrics` / `nodetool` metric `org.apache.cassandra.metrics:type=Client,name=RequestsSize`-style gauges via JMX and the limiter's in-flight counters (`ClientResourceLimits.GLOBAL_LIMIT` usage); heap and direct memory via `jcmd <pid> GC.heap_info` and NMT (`-XX:NativeMemoryTracking=summary`), sampled every 1 s. Peak in-flight bytes cannot be observed except via the metric.

**B3e. Procedure.** Start node with in_flight=16MiB; run workload; sample; stop; repeat with 128MiB; then a third run with message size 32MiB and in_flight 16MiB, which should fail to start (confirms line 912 end to end). Stop the node, check no process remains (`pgrep -f CassandraDaemon`), delete the private data directory.

**B3f. Predictions.** Peak in-flight bytes is <= 16MiB (plus at most one message in transit) in run 1 and clearly higher, up to about 128MiB, in run 2; peak request-related heap/direct memory is higher in run 2 by roughly the difference; run 3 refuses to start with the message from line 912.

**B3g. Readings.**

| Observation | Meaning |
|---|---|
| Peak in-flight and memory scale with the knob, never above it | claim confirmed |
| Memory rises with offered load beyond the limit | the limit does not bound memory, claim wrong |
| Both runs flat because offered load never reached 16MiB | limit not reached, not confirmed |
| Run 3 starts | check not applied, claim wrong |

**B3h. Controls.** Same workload with in_flight at 128MiB (a run where the cap is loose); idle baseline of heap/direct memory; identical heap and thread settings in all runs.

**B4. Risks and cleanup.** Disk: blob inserts of 4MiB x up to a few thousand rows, use a private data directory and truncate/delete afterwards; stop the node and the client processes, confirm none are left; no shared source tree writes.

## C. Sources read

- /users/jason92/cassandra-5.0.9/src/java/org/apache/cassandra/config/DatabaseDescriptor.java (lines 640-665, 880-940, 3215-3250, 3365-3395)
- /users/jason92/cassandra-5.0.9/src/java/org/apache/cassandra/config/Config.java (280-310)
- /users/jason92/cassandra-5.0.9/src/java/org/apache/cassandra/transport/CQLMessageHandler.java (620-665; grep at 551)
- /users/jason92/cassandra-5.0.9/conf/cassandra.yaml (grep only)

## D. Stage-4 feedback

`none yet`
