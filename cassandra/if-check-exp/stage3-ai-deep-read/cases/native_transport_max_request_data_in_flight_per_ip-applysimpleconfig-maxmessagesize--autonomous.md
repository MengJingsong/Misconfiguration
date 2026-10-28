# native_transport_max_request_data_in_flight_per_ip — verification solution  <!-- file: cases/native_transport_max_request_data_in_flight_per_ip-applysimpleconfig-maxmessagesize--autonomous.md -->

| Field | Value |
|---|---|
| Entry pointer | [`DatabaseDescriptor.java:914`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/DatabaseDescriptor.java#L914) |
| Pinned source | `cassandra-5.0.9` |
| Session / date | Claude Sonnet 5.5 (claude-sonnet-5-5), Claude Code CLI, 2026-10-27 |
| Estimate | `positive`: the per-IP in-flight byte limit caps the request payload bytes held per client IP, and the check at :914 guarantees any single admitted message (max_message_size) fits inside that limit, so per-IP usage is bounded by limit plus a bounded overshoot. |
| Ground | — |

**Type:** non-config (runtime-queried + hard-coded literal). The check at :914 compares two yaml entries (`native_transport_max_message_size` and `native_transport_max_request_data_in_flight_per_ip`), but the per-ip operand's default is derived at startup as `Runtime.getRuntime().maxMemory() / 40` (runtime-queried heap size and the literal `40`, [`DatabaseDescriptor.java:656`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/DatabaseDescriptor.java#L656)). Under the widened constant rule (a numeric literal taking part in how the compared value is computed) this is written up rather than skipped. Judgement call for the lead: if only the literal text of the `if` condition counts, this would instead be `SKIP | ... | yaml entry`.

## A. Constraint trace

**A1. The constraint.** `native_transport_max_request_data_in_flight_per_ip` (the limit side of the check); the other operand is `native_transport_max_message_size`. Kind: configuration entry (yaml), declared in [`Config.java:296`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/Config.java#L296) (`volatile LongBytesBound`, default `null`; old name `native_transport_max_concurrent_requests_in_bytes_per_ip`). Unit: bytes (any DataStorage unit in yaml). Default: when null, `maxMemory/40` (heap/40), set at `DatabaseDescriptor.java:654-657`; constants involved: literal `40` and the JVM max heap. Settable via yaml (restart) and at runtime via JMX `setNativeTransportMaxRequestDataInFlightPerIpInBytes` (`DatabaseDescriptor.java:3367-3376`, `-1` resets to heap/40, literal `-1` and `40`). `native_transport_max_message_size` is declared at [`Config.java:288`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/Config.java#L288), default null (computed as min(max_mutation_size, in_flight, in_flight_per_ip), `DatabaseDescriptor.java:3237-3245`, only when not set explicitly). Neither entry is uncommented in the shipped yaml by default (check `conf/cassandra.yaml` to confirm before the run).

**A2. What it caps.** Memory: bytes of client request payload (Netty/frame buffers of CQL requests received but not yet processed/released) held per remote IP. The check at :914 compares the configured single-message ceiling (bytes) with this per-IP byte limit.

**A3. Mechanism.**
1. `DatabaseDescriptor.applySimpleConfig` fills defaults for in-flight limits at lines 649-657.
2. At [`DatabaseDescriptor.java:914`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/DatabaseDescriptor.java#L914) (`if (maxCqlMessageSize > conf.native_transport_max_request_data_in_flight_per_ip.toBytes())`), reached only when `native_transport_max_message_size` is set explicitly (else branch of :903), startup throws `ConfigurationException` (:915) when the message ceiling exceeds the per-IP limit. Otherwise startup proceeds. The sibling check at :911 does the same for the global limit.
3. Runtime enforcement of the per-IP limit: `ClientResourceLimits.Allocator` builds a `ResourceLimits.Concurrent(getEndpointLimit())` per endpoint (`ClientResourceLimits.java:160`); `tryAllocate` (`:190`) requires both endpoint and global permits (`ResourceLimits.java:263-272`); `CQLMessageHandler` acquires capacity per request (`CQLMessageHandler.java:200,223,551`), queueing or throwing `OverloadedException` (`throwOnOverload`) when exhausted, and rejects messages larger than max_message_size outright (`:551`).
4. Overshoot: `Allocator.allocate` is a forced allocation that may exceed limits (`ClientResourceLimits.java:197-203`); a message is always <= max_message_size <= per-IP limit (guaranteed by :914 at startup), so overshoot per forced allocation is bounded. Runtime setter `setNativeTransportMaxRequestDataInFlightPerIpInBytes` does not re-run :914 but clamps message size with `Math.min` when set explicitly (:3370-3373).
Callers: `applySimpleConfig` only (startup).

**A4. Other consumers.** Heap/direct buffers used by the same node for reads, memtables, other clients on other IPs (global limit heap/10), internode messaging, and the 1 MiB receive queue (`native_transport_receive_queue_capacity`).

**A5. Evidence beyond the source.** none (conf/cassandra.yaml comments to be read at run time; CASSANDRA-15013 introduced these limits in 4.0, not re-verified here).

## B. Verification solution

**B1. Claim under test.** With `native_transport_max_request_data_in_flight_per_ip = L`, the bytes of in-flight request payload attributed to one client IP never exceed about L plus one max-size message; and startup fails if `native_transport_max_message_size > L`.

### B2. Unit tier

**B2a. Environment and build.** JDK 11, Ant, in a private copy of the tag (not the shared tree): `ant jar`; a JUnit test under a scratch test dir next to `test/unit/org/apache/cassandra/transport/ClientResourceLimitsTest.java` (existing similar test; read it, do not edit the original). JVM opts: default test opts.

**B2b. Knobs.** `L` (per-IP limit) in {1 MiB, 4 MiB, 16 MiB}; `native_transport_max_message_size` M in {L/2, L, L+1}. Set through `DatabaseDescriptor.setNativeTransportMaxMessageSizeInBytes` / `ClientResourceLimits.setEndpointLimit(L)`; for the startup check, load a `Config` yaml with both keys via `DatabaseDescriptor.daemonInitialization` in a forked JVM per case.

**B2c. Workload.** Startup arm: construct config with M = L/2, L, L+1 and call config application; expect pass, pass, fail. Runtime arm: from one fake endpoint, call `Allocator.tryAllocate(M)` repeatedly without release until it refuses; count granted bytes; then call forced `allocate(M)` once and read usage.

**B2d. Observables and instruments.** Exception from config application; `Allocator.endpointUsing()` (`ClientResourceLimits.java:~219`), `globallyUsing()`.

**B2e. Procedure.** Per (L, M): fresh JVM, apply config, record pass/fail; for passing cases run the allocation loop, record endpointUsing at first refusal and after one forced allocate. Use a fixed global limit large enough (e.g. 1 GiB) so only the per-IP limit binds.

**B2f. Predictions.** M = L/2 and M = L: startup passes; M = L+1: `ConfigurationException` text "must not exceed native_transport_max_request_data_in_flight_per_ip". First refusal when endpointUsing > L - M (granted bytes <= L, and >= L - M + 1... i.e. in (L-M, L]); after one forced allocate usage <= L + M <= 2L.

**B2g. Readings.**
| Observation | Meaning |
|---|---|
| M > L fails, M <= L passes; granted bytes never above L; forced usage <= L+M | claim confirmed |
| M = L+1 starts up | check does not guard (claim wrong) |
| granted bytes exceed L by more than one message | limit does not cap per IP (claim wrong) |
| refusal never happens | limit not reached; not confirmed |

**B2h. Controls.** Same loop with global limit binding (per-IP set very large) to show refusals come from the per-IP reserve in the main run; a run with L unset (heap/40 default) to compare against `Runtime.maxMemory()/40`.

### B3. Cluster tier

**B3a. Environment and build.** One node, JDK 11, `ant jar` in a private copy, heap `-Xmx2G` (Xms equal), data dir on local scratch. Config: `native_transport_max_request_data_in_flight_per_ip: 8MiB`, `native_transport_max_message_size: 4MiB`, `native_transport_max_request_data_in_flight: 1GiB`, `native_transport_rate_limiting_enabled: false`.

**B3b. Knobs.** per-IP limit L in {8MiB, 32MiB, 128MiB} with M = 4MiB fixed; plus one startup-failure run with M = 16MiB, L = 8MiB. Set in yaml, restart between values (or JMX `setNativeTransportMaxRequestDataInFlightPerIpInBytes`).

**B3c. Workload.** From one client IP, many concurrent connections (e.g. 64) each issuing ~3.5 MiB blob inserts (`INSERT ... blob`) with `cassandra-stress` or a driver script, for 2 minutes; total offered in-flight (64 x 3.5 MiB = 224 MiB) exceeds every L.

**B3d. Observables and instruments.** JMX `org.apache.cassandra.metrics:type=Client,name=...` / `ClientResourceLimits` per-IP usage histogram (`getCurrentIpUsage`) and global usage; Netty direct memory via `jcmd <pid> VM.native_memory` (needs `-XX:NativeMemoryTracking=summary`) and `jstat -gc` sampled every 1 s. OverloadedException counts at the client.

**B3e. Procedure.** Start node, wait for CQL, run workload, sample per second, stop; repeat per L; run the failing-startup config and read the log for the ConfigurationException; stop all processes (`pgrep -f CassandraDaemon`), delete scratch data.

**B3f. Predictions.** Per-IP usage histogram max <= L + M for each L (about 12 MiB, 36 MiB, 132 MiB); direct memory growth attributable to requests scales with L; M=16MiB/L=8MiB run exits at startup with the :915 message.

**B3g. Readings.**
| Observation | Meaning |
|---|---|
| per-IP usage plateaus near L, tracks L across runs, startup rejects M > L | claim confirmed |
| usage rises with offered load past L + M | limit not capping (claim wrong) |
| usage flat but offered load never reached L | not confirmed |

**B3h. Controls.** Same workload from two client IPs (second host or loopback alias) to show the limit is per IP while the global limit is not hit; repeat with the limit raised well above offered load as an uncapped baseline.

**B4. Risks and cleanup.** 224 MiB offered, 2 GiB heap, data volume small; use local scratch, delete data dir; kill node and client processes and verify none remain.

## C. Sources read

- src/java/org/apache/cassandra/config/DatabaseDescriptor.java (649-657, 895-920, 3212-3245, 3362-3395)
- src/java/org/apache/cassandra/config/Config.java (280-302)
- src/java/org/apache/cassandra/transport/ClientResourceLimits.java (55-235)
- src/java/org/apache/cassandra/transport/CQLMessageHandler.java (160-260, 540-570)
- src/java/org/apache/cassandra/net/ResourceLimits.java (grep)
- conf/cassandra.yaml (grep)

## D. Stage-4 feedback

none yet
