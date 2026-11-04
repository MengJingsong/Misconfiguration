# native_transport_max_concurrent_connections_per_ip — verification solution  <!-- file: cases/native_transport_max_concurrent_connections_per_ip-channelActive-perIpLimit--autonomous.md -->

| Field | Value |
|---|---|
| Entry pointer | [`ConnectionLimitHandler.java:102`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/transport/ConnectionLimitHandler.java#L102) (also covers `ConnectionLimitHandler.java:142#1`, the per-IP release in `channelInactive`) |
| Pinned source | `cassandra-5.0.9` |
| Session / date | Claude Opus 5.5 (`claude-opus-5-5`), Claude Code at Meta (version string not available), 2026-10-26, band D triage |
| Estimate | `positive` (per source IP). The check at :102 turns on a per-address count (`:110-127`): a connection that takes one source IP over P is closed. So the per-connection memory attributable to one client address is bounded by P connections, in particular up to P × `native_transport_max_frame_size` of partly received envelopes that no byte budget covers. Line :142 is the matching release that keeps the count, and the per-IP map, exact. The node-wide total is not capped by this key: it grows with the number of distinct source addresses. |
| Ground | — |

## A. Constraint trace

**A1. The constraint.** `native_transport_max_concurrent_connections_per_ip`, a configuration entry.
- Declared at [`Config.java:290`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/Config.java#L290) as `public volatile long … = -1L`. Unit: connections per remote `InetAddress`. Default -1, meaning off (`conf/cassandra.yaml:1050-1052`).
- Getter and setter: [`DatabaseDescriptor.java:3173-3181`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/DatabaseDescriptor.java#L3173-L3181). JMX: `StorageProxyMBean.setNativeTransportMaxConcurrentConnectionsPerIp(Long)` ([`StorageProxyMBean.java:59-60`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/service/StorageProxyMBean.java#L59-L60), [`StorageProxy.java:2854-2855`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/service/StorageProxy.java#L2854-L2855)), attribute `NativeTransportMaxConcurrentConnectionsPerIp` on `org.apache.cassandra.db:type=StorageProxy`.
- No restart is needed for new connections. Both the handler installation ([`PipelineConfigurator.java:240-245`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/transport/PipelineConfigurator.java#L240-L245), per accepted channel) and the per-IP check ([`ConnectionLimitHandler.java:101`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/transport/ConnectionLimitHandler.java#L101)) read the live value.
- Values ≤ 0 disable the per-IP branch (`:102`). With the per-IP limit > 0 and the global limit exactly 0, the handler is installed and the global check refuses every connection, since `count > 0` (`:87-97`); see B3h.


**Limit type (2026-10-29).** config: yaml entry. The traced constraint decides ([README §6](../../../stage3-ai-deep-read/README.md#6-rules-that-hold-for-both-agents)).
**A2. What it caps.** The count of live native connections from one remote IP address. The operand is `connectionsPerClient.get(address)` (`ConnectionLimitHandler.java:53,110-121`), incremented at `:121` and decremented at `:142`. Each connection holds the memory listed in the global case's A2. The large part is the `InitialConnectionHandler` cumulation of a partly received envelope:
- up to `native_transport_max_frame_size` = 16 MiB per connection (`Envelope.java:197,428-442`);
- no client byte budget applies before STARTUP (`InitialConnectionHandler.java:107-108`).

The map itself costs one entry per distinct live source IP.

**A3. Mechanism.**
1. The handler is present if either limit > 0 ([`PipelineConfigurator.java:240-244`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/transport/PipelineConfigurator.java#L240-L244)).
2. `channelActive` first passes the global check ([`ConnectionLimitHandler.java:86-98`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/transport/ConnectionLimitHandler.java#L86-L98)).
3. **Check at :102**: if P > 0, store the remote address as a channel attribute (`:104`, `:60-74`). A non-`InetSocketAddress` remote gives null, and the channel is closed (`:105-109`). Then get or create the per-IP `AtomicLong` (`:110-120`).
4. `incrementAndGet() > P` → error log (NoSpamLogger) and `ctx.close()` (`:121-127`). Otherwise `fireChannelActive()` (`:129`).
5. **Line 142**: on `channelInactive` the global counter is decremented (`:136`). If the channel had an address attribute, its per-IP counter is decremented, and the map entry is removed when it reaches ≤ 0 (`:137-146`). Channels refused by the global check never set the attribute, so they are not decremented per IP, which matches their never having been incremented.
- Overshoot paths:
  - (a) Race at :142–:144. `remove(address)` is unconditional, not `remove(address, count)`. If a new channel from the same IP fetches the old `AtomicLong` at `:110` just before the removal and increments it, that connection is counted in an orphaned counter, and the next connection from the IP starts a fresh counter at 1. So a single IP can briefly hold more than P live connections. It needs concurrent close and open from one IP on different event loops; it is rare and is not part of the predictions.
  - (b) The cap is per address, so the node-wide total is P × (number of distinct client IPs), bounded only by the global limit.
  - (c) The per-connection bytes come from other settings (A2).

**A4. Other consumers.**
- Same as the global case: `native_transport_max_request_data_in_flight[_per_ip]` (bytes after STARTUP), `native_transport_receive_queue_capacity`, `native_transport_max_frame_size`, the networking `BufferPool`, Netty outbound buffers and kernel socket buffers.
- `native_transport_max_concurrent_connections` caps the node-wide count.

**A5. Evidence beyond the source.**
- `conf/cassandra.yaml:1050-1052` ("The maximum number of concurrent client connections per source ip").
- Netty `ByteToMessageDecoder` javadoc (https://netty.io/4.1/api/io/netty/handler/codec/ByteToMessageDecoder.html).
- No test in `test/` covers this handler.

## B. Verification solution

**B1. Claim under test.** With k source IPs each opening M > P connections that each hold a partly sent envelope of S bytes:
- each IP keeps exactly min(M, P) connections open;
- decoder-held bytes are k × min(M, P) × S;
- with P = -1 all k × M are kept;
- after every connection closes, the per-IP map is empty (line 142).

### B2. Unit tier

**B2a. Environment and build.** Same as the global case:
- local clone `/local/c509`, `ant build-test`;
- new test `/local/c509/test/unit/org/apache/cassandra/transport/ConnectionLimitPerIpProbeTest.java` (package `org.apache.cassandra.transport`);
- run with `ant testsome -Dtest.name=org.apache.cassandra.transport.ConnectionLimitPerIpProbeTest`.

> **Amendment U1 (2026-10-27, stage-4 step-0 audit, Claude Opus 5.5 `claude-opus-5-5`, before any harness run or reading):** this host has no `/local` and the filed text points to the companion case for the build. Clone `$W/cassandra-run52` (`W=~/Library/Caches/stage4`; fresh `git clone --branch cassandra-5.0.9 ~/cassandra-src`, `ant -Dlocal.repository=$W/m2 build-test`). The probe class is kept in `stage4-runtime-verification/harness/native_transport_max_concurrent_connections_per_ip-channelActive-perIpLimit--autonomous/ConnectionLimitPerIpProbeTest.java`, copied into the clone's `test/unit/org/apache/cassandra/transport/` only for the run and removed afterwards; run with `ant -Dlocal.repository=$W/m2 testsome -Dtest.name=org.apache.cassandra.transport.ConnectionLimitPerIpProbeTest`. Its stdout is read from `build/test/logs/**/TEST-org.apache.cassandra.transport.ConnectionLimitPerIpProbeTest.log` (one line per `System.out` write), not from `build/test/output/TEST-*.xml` (B2e step 4).

**B2b. Knobs.**
- P ∈ {-1, 2, 4}, set with `DatabaseDescriptor.setNativeTransportMaxConcurrentConnectionsPerIp(P)`; the global limit stays -1.
- Edge row: global 0 with P = 4.
- Why these: -1 is off; 2 and 4 are both below M = 8, so the cap binds at two levels.

**B2c. Workload.**
- k = 8 addresses 127.0.0.1 … 127.0.0.8, with M = 8 channels each (64 channels).
- Each channel is a subclass `class IpChannel extends EmbeddedChannel { IpChannel(InetSocketAddress r) { super(false, false); this.r = r; } protected SocketAddress remoteAddress0() { return r; } }`. The plain `EmbeddedChannel` remote is not an `InetSocketAddress`, so `ConnectionLimitHandler.java:105-108` would close it.
- Pipeline: `configureInitialPipeline(ch, null)`, then `register()`, then `runPendingTasks()`.
- On each open channel, write the same partial v4 STARTUP envelope as the global case: 9-byte header with body length 16,000,000, plus S = 1,048,576 bytes.
- Arithmetic: at P = -1, 64 × 1 MiB = 64 MiB held.

**B2d. Observables and instruments.**
- `open` per IP and in total.
- `connectionsPerClient` by reflection: its size and each value.
- `held` = Σ `internalBuffer().readableBytes()` of `InitialConnectionHandler` over open channels, read reflectively as in the global case.
- After closing all channels: map size and the global `counter`.

**B2e. Procedure.**
1. `DatabaseDescriptor.daemonInitialization()`.
2. For each P:
   - set P;
   - create, configure and register the 64 channels, then `runPendingTasks()`;
   - record open per IP, the map and the counter;
   - write the envelopes and record `held`;
   - close all (`finishAndReleaseAll()`, then `runPendingTasks()`), and record the map size and counter.
3. Edge row: set global 0 and P = 4, register 8 channels from one IP, record `open`, then reset global to -1.
4. Print one line per run and collect it from `build/test/output/TEST-*.xml`.

> **Amendment U2 (2026-10-27, stage-4 step-0 audit, Claude Opus 5.5 `claude-opus-5-5`, before any harness run or reading):** exact procedure. (1) `DatabaseDescriptor.daemonInitialization()`; one `PipelineConfigurator` from the test constructor `new PipelineConfigurator(false, false, false, EncryptionOptions.TlsEncryptionPolicy.UNENCRYPTED)` (`PipelineConfigurator.java:116-127`); the shared handler is the static `PipelineConfigurator.connectionLimitHandler` (`:73`), read by reflection, with its fields `connectionsPerClient` (`ConnectionLimitHandler.java:53`) and `counter` (`:54`). (2) Runs in this order, each with the global limit -1 unless stated: `P-1` (P = -1, 8 IPs × 8), `P2` (P = 2, 8 × 8), `P4` (P = 4, 8 × 8), `ONEIP` (B2h control: P = 4, 64 channels all from 127.0.0.1), `EDGE` (global 0, P = 4, 8 channels from 127.0.0.1; global reset to -1 afterwards). (3) Per run: check map empty and counter 0 (printed as `pre`); for each channel in turn create an `IpChannel` (remote port 10000 + index), `configureInitialPipeline(ch, null)`, `ch.register()`, and nothing else; after all channels are registered print `before`: open (`isOpen()`) per IP and in total, the map's values and the counter (each channel has its own `EmbeddedEventLoop`, so the close of a refused channel, queued by `ctx.close()` inside `channelActive`, has not yet run its `channelInactive`); then `runPendingTasks()` on every channel and print `after` (same fields); then write to every open channel one fresh unpooled heap buffer of S + 9 = 1,048,585 bytes (header `04 00 0000 01 00F42400`: v4 request, no flags, stream 0, opcode STARTUP, body length 16,000,000; then S zero bytes) with `writeInbound`, and print `held` = Σ `internalBuffer().readableBytes()` of the pipeline's `initialHandler` (`InitialConnectionHandler`, `PipelineConfigurator.java:78,265`; `internalBuffer()` is protected in `ByteToMessageDecoder` and called by reflection) and the same sum of `capacity()`; then `finishAndReleaseAll()` and `runPendingTasks()` on every channel and print `close`: map size and counter. (4) One line per step, prefixed `PROBE <run> <step>`. The test asserts the B2f values only after every run has printed, so a failed value does not hide later lines.

**B2f. Predictions.**

| P | open per IP | open total | map values while open | held (bytes) | map size after close |
|---|---|---|---|---|---|
| -1 | 8 | 64 | map empty (branch skipped) | 64 × 1,048,585 = 67,109,440 | 0 |
| 2 | 2 | 16 | 8 for each IP before the closes run, then 2 after `runPendingTasks()` | 16,777,360 | 0 |
| 4 | 4 | 32 | 4 after tasks | 33,554,720 | 0 |
| global 0, P 4 | 0 | 0 | — | 0 | 0 |

Rejected channels are counted until their close runs. "After tasks" values assume `runPendingTasks()` has executed every close.

> **Amendment U3 (2026-10-27, stage-4 step-0 audit, Claude Opus 5.5 `claude-opus-5-5`, before any harness run or reading):** exact rows for every printed step (counter = the global `counter`, which counts every channel that reached `channelActive` while the handler is installed and is decremented in `channelInactive`, `:86,136`):

| Run | `before`: open total / map values / counter | `after`: open per IP / open total / map values / counter | held (bytes) | `close`: map size / counter |
|---|---|---|---|---|
| `P-1` | 64 / map empty / 0 (handler not installed, `PipelineConfigurator.java:240-245`) | 8 / 64 / empty / 0 | 67,109,440 | 0 / 0 |
| `P2` | 16 / 8 per IP / 64 | 2 / 16 / 2 per IP / 16 | 16,777,360 | 0 / 0 |
| `P4` | 32 / 8 per IP / 64 | 4 / 32 / 4 per IP / 32 | 33,554,720 | 0 / 0 |
| `ONEIP` | 4 / 64 for 127.0.0.1 / 64 | 4 / 4 / 4 / 4 | 4 × 1,048,585 = 4,194,340 | 0 / 0 |
| `EDGE` | 0 / empty (global branch, attribute never set) / 8 | 0 / 0 / empty / 0 | 0 | 0 / 0 |

Capacity per held channel is informational (≥ 1,048,585).

> **Runbook fix D1 (2026-10-27, stage-4 unit shakedown before run 1, Claude Opus 5.5 `claude-opus-5-5`):** the `before` column of U3 assumed that the close queued by `ctx.close()` inside `channelActive` stays pending until `runPendingTasks()`. In Netty 4.1.130 (`build/lib/jars/netty-transport-4.1.130.Final.jar`) `EmbeddedChannel` wraps its `Unsafe` (`EmbeddedChannel$EmbeddedUnsafe$1.close` and `register` run the channel's pending tasks when the outermost unsafe call returns), so a refused channel's `channelInactive` has run before `register()` returns and the transient count above P is not observable in this harness. Corrected `before` cells: `P2` 16 / 2 per IP / 16; `P4` 32 / 4 per IP / 32; `ONEIP` 4 / 4 for 127.0.0.1 / 4; `P-1` and `EDGE` unchanged except `EDGE` counter 0. The `after`, `held` and `close` columns, the claim and every B2g row are unchanged (U4 (b) already judges the ceiling on `after`). The unit tier's direct disallow evidence is therefore the refused channels being closed (`isOpen()` false) with the handler installed, plus the error line "Exceeded maximum native connection limit per ip of 2 by using 3 connections" (`ConnectionLimitHandler.java:124`) in the test log (NoSpamLogger, `:50`: one line per minute, so only the first refusal is logged).

**B2g. Readings.**

| Observation | Meaning |
|---|---|
| open per IP = min(8, P), held = open × (S + 9), map empty after close | Mechanism as traced; claim holds at the unit level |
| an IP holds more than P open channels (sequential test, no race) | Claim wrong: the per-IP check does not cap |
| map not empty after all closes | Line 142 release is broken; the counts and the map leak |
| global 0 / P 4 admits connections | A1 edge mis-traced |
| held per channel ≪ S | The per-connection byte term is mis-traced (count cap still holds) |

> **Amendment U4 (2026-10-27, stage-4 step-0 audit, Claude Opus 5.5 `claude-opus-5-5`, before any harness run or reading):** rows added. (a) An IP keeps fewer than min(8, P) open channels, or `ONEIP` keeps fewer than 4 → **Not confirmed**: the knob does not set the ceiling (over-refusal). (b) `before` map values not 8 (or 64 for `ONEIP`) for P > 0 while `after` is right → the per-IP counter does not count refused channels as traced in A3 step 4; recorded, the claim's ceiling is judged on `after`. (c) Global `counter` not 0 at `close` → a leak of the global count (outside this key); recorded, does not decide the claim. (d) The probe cannot reach a field or a `PROBE` line is missing → **Invalid run**. The claim holds at the unit level (**Confirmed — caps**) only if every row of U3 matches.

**B2h. Controls.**
- P = -1 is the positive control: held moves with the number of channels.
- Before each P, the reflective map is checked empty and the counter is 0.
- One run with all 64 channels from a single IP at P = 4 gives open = 4, which shows the cap is per address, not per run.

### B3. Cluster tier

**B3a. Environment and build.** Same node set-up as the global case's B3a:
- local clone, `ant jar`;
- data, commit log, hints and caches under `/local/cass`;
- `MAX_HEAP_SIZE=4G HEAP_NEWSIZE=800M`, and `JVM_EXTRA_OPTS="-Dcassandra.netty_use_heap_allocator=true"`;
- `native_transport_idle_timeout` default 0ms; `rpc_address: localhost`.
- Linux routes all of 127.0.0.0/8 to `lo`, so the client can bind source addresses 127.0.0.1 … 127.0.0.5 without configuration.
- Client: the same `/local/probe/hold.py` as the global case (it takes a source IP as argument 5). `ulimit -n 4096`.

> **Amendment C1 (2026-10-27, stage-4 step-0 audit, Claude Opus 5.5 `claude-opus-5-5`, before any harness run or reading):** this host (macOS, arm64) has no `/local`, no `ss`, and the filed text points to the companion case for the node set-up and the client. Clone `$W/cassandra-run52` (built by `build-test`, which includes the jar; no `ant` while a node runs from it). Node files under `$W/node-ntpip/` (`data`, `commitlog`, `hints`, `saved_caches`, `cdc_raw`, `logs`, and a copy of the clone's `conf/` used as `CASSANDRA_CONF`), removed at the end. yaml overrides: `listen_address` and `rpc_address` 127.0.0.1, the directories above, the two connection keys per run (B3b); everything else as shipped (`native_transport_idle_timeout` default 0, `native_transport_max_frame_size` default 16 MiB). `MAX_HEAP_SIZE=4G HEAP_NEWSIZE=800M`; `JVM_EXTRA_OPTS="-Dcassandra.netty_use_heap_allocator=true -javaagent:$C/build/lib/jars/byteman-4.0.20.jar=script:<harness>/ntpip.btm"` (heap allocator: `CBUtil.java:59-60`, `CassandraRelevantProperties.java:98`; the rule is C4). The node runs as a tracked background process (`bin/cassandra -f > node-stdout.log 2>&1 < /dev/null`; no `setsid` here). Only 127.0.0.1–127.0.0.3 are configured on `lo0` (macOS does not route 127/8 to `lo0` without an alias, and aliases need `sudo`), so k ≤ 3 (C2). Client: `<harness>/hold.py` (C3), Python 3.8; `ulimit -n` is 1,048,576 here.

**B3b. Knobs.**
- `native_transport_max_concurrent_connections_per_ip` ∈ {-1, 40, 10}, set in yaml with a restart between values; global stays -1.
- Edge: global 0 and per-IP 10.
- Why: with k = 5 IPs × M = 60, the totals are 300 / 200 / 50, which are distinct and well within the heap.

> **Amendment C2 (2026-10-27, stage-4 step-0 audit, Claude Opus 5.5 `claude-opus-5-5`, before any harness run or reading):** k = 3 source IPs (127.0.0.1, .2, .3) instead of 5, because only three loopback addresses exist on this host (C1). The knob values {-1 (default), 40, 10} and M = 60 are unchanged; the totals become 180 / 120 / 30. Edge unchanged (global 0, per-IP 10). Each value is a node start with a fresh `$W/node-ntpip` (B3e).

**B3c. Workload.**
- For ip in 127.0.0.1 … 127.0.0.5: `python3 /local/probe/hold.py 127.0.0.1 9042 60 4194295 $ip &`.
- Each connection sends 9 + 4,194,295 = 4 MiB of a declared 16,000,009-byte envelope.
- Arithmetic: P = -1 → 300 × 4 MiB = 1,200 MiB; P = 40 → 200 × 4 MiB = 800 MiB; P = 10 → 50 × 4 MiB = 200 MiB.
- Hold for 60 s.

> **Amendment C3 (2026-10-27, stage-4 step-0 audit, Claude Opus 5.5 `claude-opus-5-5`, before any harness run or reading):** the client, defined here because the filed text refers to the companion case's script. `hold.py HOST PORT M S SRC`: (1) opens M TCP connections one after another, each bound to (SRC, 0), connect timeout 10 s; (2) sleeps 2 s, so the node's `channelActive` has run for each; (3) if S ≥ 0, on every connection still open sends the 9-byte v4 header `04 00 00 00 01 00 F4 24 00` (STARTUP, body length 16,000,000) and then S zero bytes with `sendall`; a send error (reset, broken pipe) marks the connection refused; if S = -1 sends nothing; (4) sleeps 2 s and probes every connection with a non-blocking `recv(1, MSG_PEEK)`: no data and would-block = open; empty read or reset = refused; (5) prints `held=<open> refused=<M-open> src=<SRC> s=<S> t=<epoch ms>` and flushes; (6) holds the connections until 60 s after its start, prints `end held=<n>` from a second probe, closes all and exits. The node closes a refused connection with `SO_LINGER 0` (`PipelineConfigurator.java:136`), so the client sees a reset. Workload per value: `python3 hold.py 127.0.0.1 9042 60 4194295 $ip &` for ip in 127.0.0.1 … 127.0.0.3. Arithmetic at k = 3: P = -1 → 180 × 4 MiB = 720 MiB; P = 40 → 120 × 4 MiB = 480 MiB; P = 10 → 30 × 4 MiB = 120 MiB. The decoder's cumulation for 4,194,304 readable bytes has capacity exactly 4 MiB (Netty `AbstractByteBufAllocator.calculateNewCapacity`: power-of-two growth up to the 4 MiB threshold, which it returns when the needed capacity equals it).

**B3d. Observables and instruments.**
- Per-IP kept count: each script's `held=` line, and `ss -Htn state established '( sport = :9042 )' | awk '{print $5}' | cut -d: -f1 | sort | uniq -c`.
- Refusals: `grep -c "Exceeded maximum native connection limit per ip" logs/system.log` (NoSpamLogger, so ≥ 1).
- Held bytes: ΔH from `jcmd <pid> GC.run; jcmd <pid> GC.heap_info` and the `GC.class_histogram` `[B` total, baseline vs reading, as in the global case.
- Not observable: the per-IP map, which is only reachable through a heap dump. Optional: `jcmd <pid> GC.heap_dump /local/cass/h.hprof`, then inspect `ConnectionLimitHandler.connectionsPerClient` after all scripts end; it is expected empty.

> **Amendment C4 (2026-10-27, stage-4 step-0 audit, Claude Opus 5.5 `claude-opus-5-5`, before any harness run or reading):** instruments on this host. (1) Per-IP kept count on the node side: `netstat -an -p tcp` lines in state `ESTABLISHED` whose local address ends in `.9042`, counted by the foreign address's IP; plus each script's `held=` line. (2) Refusals: `grep -c "Exceeded maximum native connection limit per ip"` in the node's `system.log` (NoSpamLogger, ≥ 1 per node start at P > 0). (3) ΔH = the `Total` bytes of `jcmd <pid> GC.class_histogram` (it runs a full GC first and counts live objects only) at the reading minus the same at the baseline; the `[B` line's bytes are recorded as the byte-array share. `GC.heap_info` is dropped: a 4 MiB array is a G1 humongous object that occupies whole regions, so region-based heap used overstates it, and this host's `GC.heap_info` after `GC.run` failed a known-answer check in an earlier run. (4) The per-IP map, replacing the optional heap dump: a Byteman observe-only rule file `ntpip.btm` prints, at every exit of `ConnectionLimitHandler.channelActive` and `channelInactive`, a line `NTPIP <active|inactive> t=<ms> counter=<global counter> size=<map size> map=<map>` to the node's stdout; the map after all scripts end is the last `inactive` line. The rule is type-checked with Byteman's `TestScript` before use.

> **Runbook fix D2 (2026-10-27, stage-4 cluster shakedown before run 1, Claude Opus 5.5 `claude-opus-5-5`):** B3d (3) cannot see the held bytes. With `-Dcassandra.netty_use_heap_allocator=true` the child channels use `new UnpooledByteBufAllocator(false)` (`CBUtil.java:60`), but the read buffers come from `ioBuffer()`, which in Netty 4.1.130 returns a **direct** buffer whenever `PlatformDependent.hasUnsafe()` (`AbstractByteBufAllocator.ioBuffer`, bytecode of `build/lib/jars/netty-buffer-4.1.130.Final.jar`); the decoder's cumulation starts as that buffer and grows in place, so the partly received envelopes live in direct memory and a live-heap delta is ≈ 0 whatever the count (the shakedown, 36 × 1 MiB, showed a heap delta of 1.0 MiB). Fix: the held bytes are read from the native-transport allocator's own metric, `CBUtil.allocator.metric()` (`UnpooledByteBufAllocator$UnpooledByteBufAllocatorMetric`: the capacity bytes of its live instrumented direct and heap buffers, adjusted on every reallocation). An observe-only Byteman rule in `ntpip.btm` prints `NTPIPMEM t=<ms> direct=<bytes> heap=<bytes> nettyDirect=<PlatformDependent.usedDirectMemory()> heapAllocatorFlag=<CBUtil.USE_HEAP_ALLOCATOR>` at every entry of `StorageService.getReleaseVersion`, which `nodetool version` calls (`NodeProbe.java:859-861`, `StorageService.java:3984`); B3e takes this reading next to each histogram (baseline, reading, post). **ΔA = (direct + heap) at the reading minus the same at the baseline** replaces ΔH in B3f, B3g, B3h and C6/C7, with the same numbers and bands (the claim's per-connection term is 4 MiB of capacity, C3); ΔH from the class histogram is kept as an informational heap reading and the "post within 50 MiB of baseline" check applies to both. The claim, the counts, every band and every row are otherwise unchanged; the cluster tier starts at this version.

> **Runbook fix D3 (2026-10-27, same cluster shakedown, Claude Opus 5.5 `claude-opus-5-5`):** C4 (4) reads "the map after all scripts end" from the last `inactive` line. When a script is killed its connections close on several event loops in the same millisecond, and each rule line reads the counter and the map at its own moment and is printed in no fixed order (the shakedown's last line read `size=1 map={/127.0.0.1=2}` while a line printed before it read `size=0`), so the last printed line is not the final state. Fix: the on-demand `NTPIPMEM` line of D2 also prints the shared handler's state (`PipelineConfigurator.connectionLimitHandler`, `PipelineConfigurator.java:73`): ` mapSize=<connectionsPerClient.size()> counter=<counter> map=<connectionsPerClient>`; the map after all scripts end is the `post` reading (taken ≥ 7 s after the kill, when no connection is open). The per-event `NTPIP` lines are kept as the disallow evidence (an `active` line whose value for an IP exceeds P). Claim, predictions and rows unchanged.

**B3e. Procedure.**
1. Clean `/local/cass`, set the knob, start `bin/cassandra -p /local/cass/pid`, wait for "Starting listening for CQL clients".
2. Warm up with 3 cqlsh queries and wait 60 s; take the baseline readings.
3. Start the 5 scripts and wait for all `held=` lines; run `ss`; after 20 s take the readings and count the log lines.
4. Kill the scripts; after 5 s confirm `ss` is empty and that ΔH is back within 50 MiB of baseline.
5. Repeat for each value.
6. Edge run (global 0, per-IP 10): try `bin/cqlsh -e "SELECT now() FROM system.local"` and one `hold.py … 5 0 127.0.0.1` run.
7. Stop Cassandra and check that no process is left.

> **Amendment C5 (2026-10-27, stage-4 step-0 audit, Claude Opus 5.5 `claude-opus-5-5`, before any harness run or reading):** exact sequence (script `cluster-run.sh`, every command logged). Node start 1, P = -1: main run (k = 3, S = 4,194,295), then the S = 0 control (k = 3, `s = -1`) with its own baseline. Node start 2, P = 40: main run. Node start 3, P = 10: main run, then the scope control (k = 1: 127.0.0.1 only, S = 4,194,295) with its own baseline. Node start 4, edge (global 0, per-IP 10). Per node start: fresh `$W/node-ntpip`, yaml written, start, wait for `nodetool statusbinary` = `running` and the log line "Starting listening for CQL clients"; 3 `cqlsh` queries (`SELECT now() FROM system.local`) as warm-up; wait 60 s. Per run: baseline histogram; start the scripts; wait until every script printed `held=` (stop condition: 120 s); `netstat` count; wait 20 s; reading histogram; second `netstat`; count the log lines; kill the scripts (`kill`, then confirm none left); wait 5 s; `netstat` must show no established :9042 connection; a post histogram must be within 50 MiB of the baseline. Edge: `cqlsh -e "SELECT now() FROM system.local"` (expected to fail) and `hold.py 127.0.0.1 9042 5 0 127.0.0.1`. Then stop the node (`nodetool stopdaemon`, then the process must be gone).

**B3f. Predictions.**

| per-IP | held per IP | held total | ΔH (MiB) |
|---|---|---|---|
| -1 | 60 | 300 | 1,200, range [1,150, 1,450] |
| 40 | 40 | 200 | 800, range [760, 980] |
| 10 | 10 | 50 | 200, range [180, 260] |
| global 0, per-IP 10 | 0 (cqlsh fails to connect; script `held=0`) | 0 | ≈ 0 |

- The claim is wrong if any IP holds more than P at P ∈ {40, 10}.
- It is also wrong if ΔH at P = 10 exceeds 400 MiB while the count is capped.

> **Amendment C6 (2026-10-27, stage-4 step-0 audit, Claude Opus 5.5 `claude-opus-5-5`, before any harness run or reading):** predictions at k = 3 (C2). The ΔH bands are the filed bands scaled by 3/5, so their relative tolerance is unchanged; the refutation threshold scales the same way.

| per-IP | held per IP | held total | ΔH (MiB) |
|---|---|---|---|
| -1 | 60 | 180 | 720, range [690, 870] |
| 40 | 40 | 120 | 480, range [456, 588] |
| 10 | 10 | 30 | 120, range [108, 156] |
| 10, scope control k = 1 | 10 | 10 | 40, range [36, 52] (the P = 10 band ÷ 3) |
| -1, S = 0 control (`s = -1`) | 60 | 180 | < 18 (30 × 3/5) |
| global 0, per-IP 10 | 0 (cqlsh fails to connect; script `held=0`) | 0 | ≈ 0 (not measured) |

- The claim is wrong if any IP holds more than P at P ∈ {40, 10}.
- It is also wrong if ΔH at P = 10 (k = 3) exceeds 240 MiB while the count is capped.
- At P > 0 the Byteman lines show per-IP values ≤ P after every refused connection's `inactive` line, and the map is empty (`size=0`) after all scripts end; at P = -1 there are no `NTPIP` lines (handler not installed).

**B3g. Readings.**

| Observation | Meaning |
|---|---|
| held per IP = min(60, P) and ΔH ≈ total × 4 MiB | Confirmed per IP: the per-IP count bounds the decoder-held memory from each address |
| held per IP > P | Claim wrong on a real node |
| counts capped but ΔH the same at every P | Claim wrong: refused connections still hold memory |
| ΔH ≪ 300 × 4 MiB at P = -1 | Positive control failed (decoder or allocator assumption wrong); not confirmed |
| edge run admits connections | A1 edge mis-traced |
| ΔH at P = 10 grows when more IPs are added (control below) | Expected: the per-IP key does not cap the node total (B1 is scoped per IP) |

> **Amendment C7 (2026-10-27, stage-4 step-0 audit, Claude Opus 5.5 `claude-opus-5-5`, before any harness run or reading):** rows added. (a) An IP keeps fewer than min(60, P) connections → **Not confirmed** (over-refusal; the knob does not set the ceiling). (b) Refusals at P > 0 but no "per ip" log line and no Byteman `active` line with a value > P → disallow evidence missing → **Not confirmed**. (c) Byteman map not empty after all scripts end → line 142 release broken (the B2g row). (d) Counts as predicted but ΔH outside its band at some value while inside the refutation limits → **Not confirmed** for the byte term, the count cap recorded. (e) S = 0 control ΔH ≥ 18 MiB → the bytes are not (only) the envelopes; the byte term is **Not confirmed**. (f) An instrument fails (no histogram, no `held=` line within 120 s, rule not loaded) → **Invalid run** for that value. Confirmed per IP requires held per IP = min(60, P) at every value, ΔH in band at every value, the log line or a Byteman value > P at P > 0, the map empty after close, and the scope control's ΔH ≈ ΔH(k = 3) ÷ 3 (its band).

**B3h. Controls.**
- Positive control: P = -1 at k = 5 shows memory moves with the connection count.
- Scope control: at P = 10, run k = 10 IPs (127.0.0.1 … 127.0.0.10) × 60. Prediction: held 100, ΔH ≈ 400 MiB, double the k = 5 run. That shows the cap is per address.
- S = 0 control: P = -1 with connections that send nothing (`s = -1`); ΔH < 30 MiB.
- The global counter path is ruled out by keeping the global limit at -1 except in the edge run.

> **Amendment C8 (2026-10-27, stage-4 step-0 audit, Claude Opus 5.5 `claude-opus-5-5`, before any harness run or reading):** scope control at k = 1 (127.0.0.1 only) instead of k = 10, since this host has three loopback addresses: at P = 10, ΔH(k = 3) ≈ 3 × ΔH(k = 1) shows that the cap is per address and the node total grows with the number of addresses. S = 0 control at k = 3: ΔH < 18 MiB (C6).

**B4. Risks and cleanup.**
- As in the global case: everything goes under `/local/cass` (< 1 GB disk); heap peaks at about 1.3 GB.
- Kill all `hold.py` processes (`pkill -f hold.py`; confirm `pgrep -f hold.py` is empty).
- Stop Cassandra and confirm `pgrep -f CassandraDaemon` is empty; confirm no sockets remain on :9042; `rm -rf /local/cass`.
- The edge run refuses all clients, so restore the yaml afterwards.
- Never point the scripts at a shared node.

> **Amendment C9 (2026-10-27, stage-4 step-0 audit, Claude Opus 5.5 `claude-opus-5-5`, before any harness run or reading):** on this host everything goes under `$W/node-ntpip` (removed at the end) and `$W/logs/native_transport_max_concurrent_connections_per_ip-channelActive-perIpLimit/`; heap peak about 0.9 GB (180 × 4 MiB humongous plus growth garbage). Clean-up checks: `pgrep -f hold.py` empty, `ps -eo command | grep '[C]assandraDaemon'` empty, no socket on :9042, the clone's `git status` clean.

## C. Sources read

- `src/java/org/apache/cassandra/transport/ConnectionLimitHandler.java`
- `src/java/org/apache/cassandra/transport/PipelineConfigurator.java`
- `src/java/org/apache/cassandra/transport/InitialConnectionHandler.java`
- `src/java/org/apache/cassandra/transport/Envelope.java`
- `src/java/org/apache/cassandra/transport/CBUtil.java`
- `src/java/org/apache/cassandra/net/AbstractMessageHandler.java`
- `src/java/org/apache/cassandra/config/Config.java`
- `src/java/org/apache/cassandra/config/DatabaseDescriptor.java`
- `src/java/org/apache/cassandra/service/StorageProxy.java`, `StorageProxyMBean.java`
- `conf/cassandra.yaml`
- `cases/native_transport_max_concurrent_connections-channelActive-limit--autonomous.md` (companion case, same session)
- https://netty.io/4.1/api/io/netty/handler/codec/ByteToMessageDecoder.html

## D. Stage-4 feedback

**2026-10-27, stage 4 run 1 (Claude Opus 5.5 `claude-opus-5-5`, advisor-run, the advisor's Mac; results [`../../stage4-runtime-verification/results/native_transport_max_concurrent_connections_per_ip-channelActive-perIpLimit--autonomous.md`](../../stage4-runtime-verification/results/native_transport_max_concurrent_connections_per_ip-channelActive-perIpLimit--autonomous.md); case file uncommitted at sha256 `ceb0cbc5…ff28`, on `b95104d`).**
- Unit: **Confirmed — caps** (B2g row 1). Open per IP 8 / 2 / 4 at P = -1 / 2 / 4, held = open × 1,048,585 bytes exactly, map size and counter 0 after every close; the single-IP control kept 4 of 64; the edge (global 0) admitted none.
- Cluster: **Confirmed — caps per source IP** (B3g row 1) at k = 3: held per IP 60 / 40 / 10 at P = -1 / 40 / 10, decoder bytes ΔA = 720.00 / 480.00 / 120.00 MiB (exactly 4 MiB per kept connection), S = 0 control 0.00 MiB, the map empty after every run; the node total grew 3.000 × from k = 1 to k = 3 at P = 10, as B1 scopes it.
- Audit amendments U1–U4, C1–C9 and runbook fixes D1–D3 (all 2026-10-27, above). For stage 3: (1) on a real node the partly received envelopes are in **direct** memory even with `cassandra.netty_use_heap_allocator=true` (Netty's `ioBuffer()` returns direct buffers when Unsafe is available), so a heap instrument cannot see the bytes this key bounds (D2); (2) the per-IP counter transiently exceeds P + 1 (up to 46 at P = 40) because refused connections stay counted until their `channelInactive`, and the logged "by using N connections" is formatted later; live connections were exactly P; (3) the companion-case pointers in B2a/B2d/B3a/B3c made the file not self-contained.

