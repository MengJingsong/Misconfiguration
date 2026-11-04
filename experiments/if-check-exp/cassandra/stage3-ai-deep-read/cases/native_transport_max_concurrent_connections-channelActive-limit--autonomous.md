# native_transport_max_concurrent_connections — verification solution  <!-- file: cases/native_transport_max_concurrent_connections-channelActive-limit--autonomous.md -->

| Field | Value |
|---|---|
| Entry pointer | [`ConnectionLimitHandler.java:89`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/transport/ConnectionLimitHandler.java#L89) |
| Pinned source | `cassandra-5.0.9` |
| Session / date | Claude Opus 5.5 (`claude-opus-5-5`), Claude Code at Meta (version string not available), 2026-10-26, band D triage |
| Estimate | `positive`. The check caps the number of live native-transport connections at L (a connection over L is closed at `channelActive`, `ConnectionLimitHandler.java:93-97`), so all per-connection memory scales with min(N, L). One per-connection consumer is bounded by nothing else: before STARTUP (and on v3/v4 after it), a connection's `ByteToMessageDecoder` keeps a partly received envelope of up to `native_transport_max_frame_size` (16 MiB) outside every bytes-in-flight budget. Node memory held this way is therefore at most L × 16 MiB, and only this constraint caps it. The cap is on the count; the bytes per connection come from another setting. |
| Ground | — |

## A. Constraint trace

**A1. The constraint.** `native_transport_max_concurrent_connections`, a configuration entry.
- Declared at [`Config.java:289`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/Config.java#L289) as `public volatile long native_transport_max_concurrent_connections = -1L`. Unit: connections. Default -1, meaning off (`conf/cassandra.yaml:1046-1048`, commented out).
- Getter and setter: [`DatabaseDescriptor.java:3163-3171`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/DatabaseDescriptor.java#L3163-L3171). JMX: `StorageProxyMBean.setNativeTransportMaxConcurrentConnections(Long)` ([`StorageProxyMBean.java:56-57`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/service/StorageProxyMBean.java#L56-L57), [`StorageProxy.java:2851-2852`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/service/StorageProxy.java#L2851-L2852)). MBean `org.apache.cassandra.db:type=StorageProxy`, attribute `NativeTransportMaxConcurrentConnections`. nodetool has no command for it.
- Changing it needs no restart for new connections. `PipelineConfigurator.configureInitialPipeline` (run once per accepted channel) reads both limits when it builds each channel's pipeline ([`PipelineConfigurator.java:240-245`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/transport/PipelineConfigurator.java#L240-L245)), and `channelActive` reads the limit again ([`ConnectionLimitHandler.java:87`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/transport/ConnectionLimitHandler.java#L87)). Connections already open are never closed by a lower limit.
- Values ≤ 0: the handler is installed only if this limit or the per-IP limit is **> 0** ([`PipelineConfigurator.java:240-241`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/transport/PipelineConfigurator.java#L240-L241)). So 0 behaves like -1 (unlimited) when the per-IP limit is off. If the per-IP limit is on, 0 makes `count > 0` true for every connection (`:89-93`), so every connection is refused. That edge is covered in the per-IP case file.


**Limit type (2026-10-29).** config: yaml entry. The traced constraint decides ([README §6](../../../stage3-ai-deep-read/README.md#6-rules-that-hold-for-both-agents)).
**A2. What it caps.** It caps the count of live client TCP connections on the native port. The operand is `counter` (`ConnectionLimitHandler.java:54`): incremented for every accepted channel (`:86`), decremented on `channelInactive` (`:136`), and compared with L at `:93`.
- The memory that follows the count is everything a channel holds:
  - the Netty channel and pipeline objects;
  - `InitialConnectionHandler` and its `Envelope.Decoder` (`PipelineConfigurator.java:264-265`);
  - after STARTUP, a `ServerConnection`, a `CQLMessageHandler` (v5) or the pre-v5 handlers, plus the per-channel receive allowance `native_transport_receive_queue_capacity` (1 MiB, `Config.java:302`; used at `AbstractMessageHandler.java:419`);
  - the decoder's cumulation buffer.
- The cumulation buffer is the large part. `InitialConnectionHandler extends ByteToMessageDecoder` (`InitialConnectionHandler.java:52`) and returns nothing until a whole envelope is present (`Envelope.java:441-442`). Netty keeps the received bytes in the cumulation buffer until then. The only bound on that buffer is the envelope length check, `totalLength > MAX_TOTAL_LENGTH` with `MAX_TOTAL_LENGTH = native_transport_max_frame_size` (`Envelope.java:197,428-439`, default 16 MiB, `conf/cassandra.yaml:1044`).
- No client byte budget applies before STARTUP. `ClientResourceLimits.getAllocatorForEndpoint` is first called when STARTUP is handled (`InitialConnectionHandler.java:107-108`).
- The buffer lives in the channel allocator: `CBUtil.allocator` (`PipelineConfigurator.java:138`). That is a pooled direct allocator by default, or unpooled heap with `-Dcassandra.netty_use_heap_allocator=true` (`CBUtil.java:59-60`, `CassandraRelevantProperties.java:98`).

**A3. Mechanism.**
1. The server accepts a TCP connection. `initChannel` calls `configureInitialPipeline` (`PipelineConfigurator.java:157-163,235`).
2. If either limit > 0, the shared, stateless singleton `connectionLimitHandler` ([`PipelineConfigurator.java:73`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/transport/PipelineConfigurator.java#L73)) is added first (`:244`).
3. `channelActive` runs `count = counter.incrementAndGet()` ([`ConnectionLimitHandler.java:86`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/transport/ConnectionLimitHandler.java#L86)) and reads L (`:87`). **Check at :89**: if `limit < 0`, L becomes `Long.MAX_VALUE` (`:89-92`).
4. If `count > L` (`:93`), it logs an error through a NoSpamLogger (one line per minute at most, `:50,96`) and calls `ctx.close()` (`:97`). `channelActive` is **not** propagated, so the rest of the pipeline never sees the channel as active. The decrement happens in `channelInactive` (`:136`).
5. Otherwise it applies the per-IP branch (`:101-128`) and calls `ctx.fireChannelActive()` (`:129`).
- Over-admission: none. Each channel's increment is atomic and admission needs `count ≤ L` at that moment, so at most L admitted channels are live at once.
- Under-admission is possible: rejected channels are counted until their close runs, so a burst can refuse some connections even though fewer than L admitted ones are live.
- Transient overshoot: every accepted channel, including a refused one, has its pipeline built ([`PipelineConfigurator.java:247-273`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/transport/PipelineConfigurator.java#L247-L273)) before the check closes it. That costs a few KB per refused connection for the time until close.
- Bypasses:
  - (a) L ≤ 0 with the per-IP limit off installs no handler (A1).
  - (b) Channels accepted while the handler was not installed are never counted, even if L is raised later.
  - (c) The cap is on the count only. Per-connection bytes are capped by `native_transport_max_frame_size` (cumulation), `native_transport_receive_queue_capacity` and the shared in-flight budgets, not by this check.

**A4. Other consumers.** These use client-connection memory outside this constraint:
- `native_transport_max_request_data_in_flight` and `_per_ip` (`Config.java:296-298`, defaulted at `DatabaseDescriptor.java:649-651`): bytes of decoded requests after STARTUP, shared across connections;
- `native_transport_receive_queue_capacity`: per channel, so it too scales with the count;
- `native_transport_max_frame_size` and `native_transport_max_message_size`: the size of a single envelope or message;
- the networking `BufferPool` for v5 frames (`networking_cache_size`);
- Netty outbound buffers (write watermarks 8/32 KiB, `PipelineConfigurator.java:139`);
- kernel socket buffers (not JVM memory).
- `native_transport_idle_timeout` (`Config.java:139`, default 0 = off; `PipelineConfigurator.java:247-259`) is the only thing that would close an idle, half-sent connection.

**A5. Evidence beyond the source.**
- `conf/cassandra.yaml:1046-1052`: the comments describe both keys as connection counts, -1 meaning unlimited.
- Netty 4.1 `ByteToMessageDecoder` javadoc (https://netty.io/4.1/api/io/netty/handler/codec/ByteToMessageDecoder.html): it cumulates inbound bytes until the decoder produces a message. The Netty version is 4.1.130.Final (`.build/parent-pom-template.xml:749`).
- The feature's origin is believed to be CASSANDRA-8086 (https://issues.apache.org/jira/browse/CASSANDRA-8086); the pinned clone is shallow, so this was not checked against its history.
- No unit or dtest in `test/` covers `ConnectionLimitHandler` (grep found only `test/data/jmxdump/*` attribute listings).

## B. Verification solution

**B1. Claim under test.** With N > L clients each holding a partly sent envelope of S bytes on the native port:
- the node keeps exactly min(N, L) of those connections open;
- the bytes held for them in the decoders grow as min(N, L) × S, about S per kept connection;
- with L = -1 (or 0) all N are kept and the held bytes are N × S.

### B2. Unit tier

**B2a. Environment and build.**
- JDK 11 and Ant on a Linux box. Clone to local disk, never into the shared clone: `git clone --branch cassandra-5.0.9 --depth 1 /Users/yangwang/cassandra-src /local/c509 && cd /local/c509 && ant build-test` (on a Linux host, use whatever path the clone lives at).
- Test source, a new file in the local clone only: `/local/c509/test/unit/org/apache/cassandra/transport/ConnectionLimitProbeTest.java`. It sits in package `org.apache.cassandra.transport` because `ConnectionLimitHandler` and `InitialConnectionHandler` are package-private.
- Run: `ant testsome -Dtest.name=org.apache.cassandra.transport.ConnectionLimitProbeTest`. The default test JVM options from `build.xml` apply, and `test/conf/cassandra.yaml` is loaded by `DatabaseDescriptor.daemonInitialization()`.

> **Amendment U1 (2026-10-27, stage-4 step-0 audit, before any harness run or reading).** The run host is the advisor's Mac
> (`stage4-runtime-verification/environment-advisor.md`), where `/local` does not exist. The clone is
> `$W/cassandra-run53` (`git clone --branch cassandra-5.0.9 ~/cassandra-src $W/cassandra-run53`, then
> `ant -Dlocal.repository=$W/m2 build-test`; `W=~/Library/Caches/stage4`). The test source is kept at
> `stage4-runtime-verification/harness/native_transport_max_concurrent_connections-channelActive-limit--autonomous/ConnectionLimitProbeTest.java`;
> the harness script `unit-run.sh` in the same folder copies it into the clone's
> `test/unit/org/apache/cassandra/transport/`, runs the `ant testsome` line above with `-Dlocal.repository=$W/m2`, and removes it
> afterwards. Nothing else in B2 changes.

**B2b. Knobs.** L ∈ {-1, 0, 8, 32}, set with `DatabaseDescriptor.setNativeTransportMaxConcurrentConnections(L)` before each run, with the per-IP limit left at -1.
- -1 and 0 are the two "off" encodings (0 is off only because the handler is not installed).
- 8 and 32 sit well under and well over half of N, so the min(N, L) relation is visible on both sides.

**B2c. Workload.**
- N = 64 channels per run. Each is a `new EmbeddedChannel(false, false)` (unregistered), and `new PipelineConfigurator(false, false, false, EncryptionOptions.TlsEncryptionPolicy.UNENCRYPTED).configureInitialPipeline(ch, null)` builds the real initial pipeline. Then `ch.register()` fires `channelActive`, then `ch.runPendingTasks()`.
- On each channel that is still open, `ch.writeInbound(buf)` with `buf` = a 9-byte v4 header plus S bytes:
  - header: version `0x04`, flags `0x00`, stream `0x0000`, opcode `0x01` (STARTUP), body length `16,000,000` big-endian;
  - S = 1,048,576 body bytes (zeros).
- Arithmetic: declared total 16,000,009 < 16,777,216 = `MAX_TOTAL_LENGTH`, so the decoder waits for more data and keeps all 9 + S bytes. At L = -1, 64 × 1 MiB = 64 MiB is held, well within the test JVM.

**B2d. Observables and instruments.**
- `open` = number of channels with `ch.isOpen()` after `runPendingTasks()`.
- `counter` = `ConnectionLimitHandler.counter`, read by reflection from the private static `PipelineConfigurator.connectionLimitHandler`.
- `held` = Σ over open channels of `internalBuffer().readableBytes()` on `ch.pipeline().get(InitialConnectionHandler.class)`. `internalBuffer()` is a protected method of `io.netty.handler.codec.ByteToMessageDecoder`; call it via `getDeclaredMethod("internalBuffer")` with `setAccessible(true)`. Also record `Σ capacity()`.
- Not observable here: process heap or RSS, kernel buffers, real-socket timing.

**B2e. Procedure.**
1. `@BeforeClass`: `DatabaseDescriptor.daemonInitialization()`.
2. For each L in {-1, 0, 8, 32}:
   - set L;
   - create, configure and register 64 channels as in B2c, then run their pending tasks;
   - record `open` and `counter`;
   - write the partial envelope to each open channel and record `held`;
   - close every channel (`ch.finishAndReleaseAll()`, then `runPendingTasks()`) and assert `counter` returns to 0 before the next L.
3. Print one line per L via `System.out` (`L open counter held capacity`), and collect it from `build/test/output/TEST-*.xml`.

> **Amendment U2 (2026-10-27, stage-4 step-0 audit, before any harness run or reading).** The procedure is made exact; the
> observables and B2f's numbers are unchanged except as U3 says.
> - Runs, in this order, each with the per-IP limit at -1: `L-1` (L = -1), `L0` (L = 0), `L8` (L = 8), `L32` (L = 32), all with
>   S = 1,048,576, then the B2h control `S0` (L = 8, nothing written). After each run L is set back to -1.
> - Each envelope is one heap buffer `Unpooled.buffer(9 + S, 9 + S)` holding the 9-byte header of B2c and S zero bytes, written
>   with one `writeInbound` call.
> - `open` and `counter` are read once, after `register()` and `runPendingTasks()` of all 64 channels. (Netty 4.1.130's
>   `EmbeddedChannel` already runs the close of a refused channel before `register()` returns; this changes no prediction.)
> - `closeCounter` = `counter` after every channel's `finishAndReleaseAll()` and `runPendingTasks()`.
> - Each run prints one line `PROBE <run> L=<L> open=<n> counter=<n> written=<n> held=<bytes> capacity=<bytes> closeCounter=<n>`.
>   The test asserts B2f (as amended by U3) only after every line is printed.
> - The lines are collected from `build/test/logs/**/TEST-org.apache.cassandra.transport.ConnectionLimitProbeTest.log` (where the
>   build at this tag writes test stdout), with the XML under `build/test/output/` as a fallback.

**B2f. Predictions.**

| L | open | counter after tasks | held (bytes) |
|---|---|---|---|
| -1 | 64 | 64 | 64 × 1,048,585 = 67,109,440 |
| 0 | 64 | n/a (no handler installed; reflection reads the unchanged 0) | 67,109,440 |
| 8 | 8 | 8 | 8,388,680 |
| 32 | 32 | 32 | 33,554,720 |

- `capacity` ≥ `held` and ≤ 2 × `held`.
- `counter` returns to 0 after every close.

> **Amendment U3 (2026-10-27, stage-4 step-0 audit, before any harness run or reading; a source error in the table, not a
> reading).** At L = -1 with the per-IP limit at -1 the handler is **not** installed either: `configureInitialPipeline` adds it
> only if one of the two limits is > 0 (`PipelineConfigurator.java:240-245`), so nothing increments `counter`, which reads its
> unchanged 0. The L = -1 row's "counter after tasks 64" is replaced by "n/a (no handler installed; reflection reads the
> unchanged 0)", the same as the L = 0 row. `open` and `held` at L = -1 are unchanged (64 and 67,109,440). The B2h control gets its
> own row:
>
> | run | L | open | counter after tasks | held (bytes) |
> |---|---|---|---|---|
> | S0 | 8 | 8 | 8 | 0 |
>
> `capacity` for each buffer is exactly 9 + S (the cumulation is the written buffer itself, `Unpooled.buffer(9 + S, 9 + S)`, kept
> by Netty's merge cumulator when the cumulation is empty), which lies inside the band above. `closeCounter` = 0 for every run.

**B2g. Readings.**

| Observation | Meaning |
|---|---|
| open = min(64, L) for L > 0, 64 for L ∈ {-1, 0}; held = open × (S + 9) | Mechanism as traced; claim holds at the unit level |
| open > L for some L > 0 | Claim wrong: the check does not cap the count |
| open = min(N, L) but held for refused channels > 0 | Refused channels still accumulate; the cap does not bound the bytes (claim wrong in part) |
| held per open channel ≪ S | The decoder does not keep partial envelopes; the per-connection byte term is mis-traced, so re-derive it (count cap still holds) |
| L = 0 refuses connections | A1 mis-traced (handler installed at 0) |
| counter does not return to 0 after closes | Leak in the decrement path; the cap would tighten over time |

> **Amendment U4 (2026-10-27, stage-4 step-0 audit, before any harness run or reading).** Rows added so every outcome has a
> meaning:
>
> | Observation | Meaning |
> |---|---|
> | `counter` ≠ 0 at L ∈ {-1, 0} (per-IP off) | A1 mis-traced (handler installed while both limits are ≤ 0); Not confirmed |
> | `counter` ≠ `open` at L ∈ {8, 32} | The operand does not track the admitted channels as traced; Not confirmed |
> | S0 control: held ≠ 0 | The held bytes do not come from the writes; run invalid |
> | Any reading that matches no row above | Not confirmed; record it as feedback to stage 3 |
>
> Row 1 ("Mechanism as traced") is the **Confirmed** row (effect: caps); it needs, in addition, `counter` = `open` at L ∈ {8, 32},
> `counter` = 0 at L ∈ {-1, 0}, `closeCounter` = 0 everywhere and the S0 row of U3. Rows 2 and 3 are the **Refuted** rows for B1;
> rows 4, 5 and 6 and the rows of this amendment are **Not confirmed** (or invalid, as stated).

**B2h. Controls.**
- L = -1 with the same writes is the positive control: held moves with N (64 × S).
- A run with S = 0 (header-less, nothing written) at L = 8 gives held = 0, so the bytes come from the writes, not the channel objects.
- The `counter` reset between L values rules out carry-over in the shared static handler.

### B3. Cluster tier

**B3a. Environment and build.**
- One Linux node, JDK 11, built in the local clone (`cd /local/c509 && ant jar`).
- `conf/cassandra.yaml`: `data_file_directories: [/local/cass/data]`, `commitlog_directory: /local/cass/commitlog`, `hints_directory: /local/cass/hints`, `saved_caches_directory: /local/cass/caches`; `native_transport_idle_timeout` left at its default `0ms`; `rpc_address: localhost`, `native_transport_port: 9042` (defaults).
- `conf/cassandra-env.sh` environment: `MAX_HEAP_SIZE=4G HEAP_NEWSIZE=800M`. Add `JVM_EXTRA_OPTS="-Dcassandra.netty_use_heap_allocator=true"`, so channel buffers come from `UnpooledByteBufAllocator(false)` on heap (`CBUtil.java:60`) and show in heap tools. The default pooled direct allocator is not reliably visible to the JDK's direct `BufferPoolMXBean` when Netty allocates without a cleaner.
- Client: Python 3 standard library only. Raise the client shell limit: `ulimit -n 4096`.
- Disk: < 1 GB of local disk (no data is written).

> **Amendment C1 (2026-10-27, stage-4 step-0 audit, before any harness run or reading).** The run host is the advisor's Mac
> (`stage4-runtime-verification/environment-advisor.md`; macOS, no `/local`, no `ss`, no `setsid`). Substitutions, all else as
> written:
> - Clone `$W/cassandra-run53` (already built by `ant -Dlocal.repository=$W/m2 build-test`, which includes the jar), never run
>   `ant` in it while a node runs.
> - Node files under `$W/node-ntc` (fresh for every node start, removed at the end) instead of `/local/cass`: a copy of the clone's
>   `conf/` with `data_file_directories`, `commitlog_directory`, `hints_directory`, `saved_caches_directory`, `cdc_raw_directory`
>   under it, `listen_address`/`rpc_address` `127.0.0.1`, and `native_transport_max_concurrent_connections` set to L;
>   `native_transport_max_concurrent_connections_per_ip` and `native_transport_idle_timeout` left at their defaults.
> - Start: `CASSANDRA_CONF=$W/node-ntc/conf CASSANDRA_LOG_DIR=$W/node-ntc/logs MAX_HEAP_SIZE=4G HEAP_NEWSIZE=800M
>   JVM_EXTRA_OPTS="-Dcassandra.netty_use_heap_allocator=true -javaagent:<clone>/build/lib/jars/byteman-4.0.20.jar=script:<harness>/ntc.btm"
>   bin/cassandra -f` as a tracked background process. The Byteman rules (C4, C5) are observe-only. Ready = `nodetool statusbinary`
>   prints `running` and `system.log` has "Starting listening for CQL clients".
> - The client limit `ulimit -n` is 1,048,576 on this host already (≥ 4096). Python is 3.8.11.
> - The run is driven by `harness/<stem>/cluster-run.sh`, which logs every command under
>   `$W/logs/native_transport_max_concurrent_connections-channelActive-limit/`.

**B3b. Knobs.** `native_transport_max_concurrent_connections` ∈ {-1, 200, 50}, set in `conf/cassandra.yaml` with a restart between values (restart keeps the counter clean). `native_transport_max_concurrent_connections_per_ip` stays -1. Why these values: -1 is the unlimited baseline, 200 is below N = 300, and 50 is far below it, so the held bytes take three distinct values.

**B3c. Workload.** Script `/local/probe/hold.py` (outside the clone):
```python
import socket, struct, sys, time, signal
host, port, n, s = sys.argv[1], int(sys.argv[2]), int(sys.argv[3]), int(sys.argv[4])
src = sys.argv[5] if len(sys.argv) > 5 else None
hdr = struct.pack('>BBhBI', 0x04, 0x00, 0, 0x01, 16000000)
body = b'\0' * max(s, 0)          # s = -1: connect only, send nothing
socks, refused = [], 0
for i in range(n):
    c = socket.socket()
    if src:
        c.bind((src, 0))
    c.connect((host, port))
    try:
        if s >= 0: c.sendall(hdr + body)
        socks.append(c)
    except OSError:
        refused += 1; c.close()
    time.sleep(0.01)
time.sleep(3)
alive = []
for c in socks:
    try:
        r = c.recv(1, socket.MSG_PEEK | socket.MSG_DONTWAIT)
        if r == b'':
            refused += 1
        else:
            alive.append(c)
    except BlockingIOError:
        alive.append(c)
    except OSError:
        refused += 1
print(f"held={len(alive)} refused={refused}", flush=True)
signal.signal(signal.SIGTERM, lambda *a: sys.exit(0))
try:
    while True: time.sleep(1)
finally:
    for c in alive: c.close()
```
- N = 300 connections, S = 4,194,295 body bytes, so each connection sends 9 + S = 4,194,304 bytes = 4 MiB.
- Arithmetic: declared total 16,000,009 < 16 MiB, so every kept connection's decoder holds 4 MiB. At L = -1 that is 300 × 4 MiB = 1,200 MiB, within the 4 GB heap. At L = 200 it is 800 MiB; at L = 50, 200 MiB.
- Duration: about 10 s to open, then held for 60 s while sampled.

> **Amendment C2 (2026-10-27, stage-4 step-0 audit, before any harness run or reading).** The script above is kept verbatim as
> `harness/<stem>/hold.py` (only its location changes) and is run as `python3 <harness>/hold.py 127.0.0.1 9042 <N> <S>`. It is
> stopped with SIGTERM to its PID (instead of `kill %1`).

**B3d. Observables and instruments.**
- Kept count:
  - the script's `held=` line;
  - `ss -Htn state established '( sport = :9042 )' | wc -l`;
  - `grep -c "Exceeded maximum native connection limit" /local/c509/logs/system.log` (≥ 1 when refusing; NoSpamLogger limits it to one per minute).
  - `nodetool clientstats` lists only connections past STARTUP, so it shows none of these.
- Held bytes:
  - live heap after a full GC: `jcmd <pid> GC.run; sleep 2; jcmd <pid> GC.heap_info` (used);
  - `jcmd <pid> GC.class_histogram | awk '$4=="[B"{print $3}'` (total `byte[]` bytes).
  - Baseline: both taken just before the script starts; reading: both taken 20 s after `held=` prints. ΔH = reading − baseline, from each instrument.
- Not observable directly: kernel socket memory (context only: `ss -tm`), and per-connection Netty object sizes (inferred from the S = 0 control).

> **Amendment C3 (2026-10-27, stage-4 step-0 audit, before any harness run or reading).** macOS has no `ss`. The independent kept
> count is `netstat -an -p tcp`, counting lines in state `ESTABLISHED` whose local address is `127.0.0.1.9042` (the node's side of
> each connection). `ss -tm` context is dropped. The log count reads `$W/node-ntc/logs/system.log`.
>
> **Amendment C4 (2026-10-27, stage-4 step-0 audit, before any harness run or reading; a source finding, not a reading).** The
> heap instruments cannot see the held bytes, with or without `-Dcassandra.netty_use_heap_allocator=true`:
> - Netty's channel reads take their buffer from `allocator.ioBuffer()`, and `AbstractByteBufAllocator.ioBuffer(int)` returns
>   `directBuffer(...)` whenever `PlatformDependent.hasUnsafe()` is true (netty-buffer 4.1.130, `javap -c`); the flag only changes
>   `CBUtil.allocator` to `UnpooledByteBufAllocator(false)` (`CBUtil.java:59-60`), whose preference affects `buffer()`, not
>   `ioBuffer()`.
> - `ByteToMessageDecoder`'s merge cumulator returns the first read buffer itself as the cumulation when the cumulation is empty,
>   and appends later reads with `writeBytes`, growing the same (direct) buffer in place while its reference count is 1
>   (netty-codec 4.1.130, `ByteToMessageDecoder$1.cumulate`, `javap -c`).
>
> So the cumulation is direct memory. The **held bytes (ΔH) are read instead from the native-transport allocator's own metric**:
> `CBUtil.allocator.metric().usedDirectMemory() + usedHeapMemory()` (capacity bytes of the live buffers it allocated). A Byteman
> observe-only rule (`harness/<stem>/ntc.btm`, on `StorageService.getReleaseVersion`) prints one `NTCMEM` line with both values
> and `counter` on every `nodetool version` call. ΔH = reading − baseline of that sum.
> - Per kept connection the cumulation's capacity is exactly 4,194,304 B: the buffer grows by
>   `AbstractByteBufAllocator.calculateNewCapacity`, which below the 4 MiB threshold returns the smallest power of two ≥ the
>   target (from 64) and at exactly 4,194,304 returns 4,194,304; the target never exceeds 9 + S = 4,194,304. So ΔH = held × 4 MiB,
>   and B3f's MiB values and bands stand unchanged (MiB = 2^20 B).
> - The heap readings are kept as context, not as a row condition: `jcmd <pid> GC.run`, then `jcmd <pid> GC.class_histogram`
>   (`Total` bytes and the `[B` row). `GC.heap_info` is dropped (on this host it failed a known-answer check after `GC.run`).
>
> **Amendment C5 (2026-10-27, stage-4 step-0 audit, before any harness run or reading).** Direct disallow evidence besides the
> NoSpamLogger line (at most one per minute): a second observe-only rule in `ntc.btm`, at the `ChannelHandlerContext.close()`
> call inside `ConnectionLimitHandler.channelActive` (with the per-IP limit off, the only close reachable is `:97`), prints one
> `NTCREFUSE` line per refused channel with `counter` and L. Expected count per run: 0 at L = -1; N − L at L ∈ {200, 50}
> (connections are opened one by one 10 ms apart, so a refused channel is closed before the next arrives). The count is recorded;
> B3f's condition stays "≥ 1".

**B3e. Procedure.**
1. `rm -rf /local/cass && mkdir -p /local/cass`. Set L in yaml. Start: `cd /local/c509 && bin/cassandra -p /local/cass/pid`. Wait for "Starting listening for CQL clients" in `logs/system.log`.
2. Warm up: `bin/cqlsh -e "SELECT now() FROM system.local"` 3 times. Then wait 60 s.
3. Baseline: GC.run, GC.heap_info and class_histogram as in B3d.
4. `python3 /local/probe/hold.py 127.0.0.1 9042 300 4194295 &`, then wait for the `held=` line.
5. Run `ss … | wc -l`, wait 20 s, then take the readings (GC.run, heap_info, class_histogram), and count the log lines.
6. `kill %1`. Wait 5 s, check that `ss … | wc -l` gives 0, then take a GC reading again (it should return to baseline ± 50 MiB).
7. Stop: `kill $(cat /local/cass/pid)`, and confirm `pgrep -f CassandraDaemon` is empty.
8. Repeat for L = 200 and L = 50, then the controls in B3h.

> **Amendment C6 (2026-10-27, stage-4 step-0 audit, before any harness run or reading).** Exact procedure (paths per C1, instruments
> per C3–C5):
> - Nodes, each fresh (new `$W/node-ntc`), in this order: L = -1, L = 200, L = 50. Each node: start and wait ready (step 1); 3 ×
>   `cqlsh` warm-up, then 60 s (step 2).
> - On the L = -1 node three runs, each with its own baseline: `main` (N = 300, S = 4,194,295), then the B3h positive control
>   `n100` (N = 100, S = 4,194,295), then the B3h `s0` control (N = 300, S = -1). On the L = 200 and L = 50 nodes one run, `main`.
> - Each run: baseline = `GC.run`, class histogram, `NTCMEM` line, netstat count (step 3); start `hold.py` (step 4) and wait up to
>   120 s for its `held=` line (stop condition: no line → the run is invalid); netstat count; wait 20 s; reading = `GC.run`, class
>   histogram, `NTCMEM`, netstat count; log-line count and `NTCREFUSE` count for the run (step 5); SIGTERM to `hold.py`, 5 s,
>   netstat count (expected 0), 2 s, post = `GC.run`, class histogram, `NTCMEM` (step 6).
> - Stop: `nodetool stopdaemon`, then `kill` of the PID if still alive after 60 s; check that no Cassandra daemon process remains
>   (step 7).

**B3f. Predictions.**

| L | held (script, ss) | log lines | ΔH (heap used, byte[]) |
|---|---|---|---|
| -1 | 300 | 0 | 1,200 MiB, accepted range [1,150, 1,450] MiB |
| 200 | 200 | ≥ 1 | 800 MiB, range [760, 980] |
| 50 | 50 | ≥ 1 | 200 MiB, range [180, 260] |

- The ranges allow up to about 20% per-connection overhead and capacity rounding above 4 MiB per connection.
- ΔH(L) / ΔH(-1) ≈ min(300, L) / 300 within ± 0.05.
- After step 6, ΔH returns to within 50 MiB of baseline.
- The claim is wrong if held > L for L ∈ {200, 50}, or if ΔH at L = 50 is not clearly below ΔH at L = -1 (for example > 400 MiB).

**B3g. Readings.**

| Observation | Meaning |
|---|---|
| held = min(300, L) and ΔH ≈ held × 4 MiB at each L | Confirmed: the count cap bounds the decoder-held memory |
| held = min(300, L) but ΔH the same at every L | Claim wrong: refused connections still hold memory, or the bytes live elsewhere |
| held > L | Claim wrong: the check does not cap live connections on a real node |
| ΔH per held connection ≪ 4 MiB at L = -1 (positive control did not move) | Workload invalid (the decoder does not keep partial envelopes as traced, or the allocator setting did not apply); not confirmed, so fix before judging L |
| ΔH does not return to baseline after close | Leak; record it, and the claim stands for the open phase only |

> **Amendment C7 (2026-10-27, stage-4 step-0 audit, before any harness run or reading).** ΔH in this table and in B3f is the
> allocator ΔH of C4. Row 1 is the **Confirmed** row (effect: caps); "ΔH ≈ held × 4 MiB" means every B3f condition holds (held
> counts, log lines, bands, ratios within ± 0.05, return within 50 MiB) and the B3h controls hold (n100 ΔH in [383, 484] MiB, the
> band of B3f's L = -1 row divided by 3 and rounded outward; s0 ΔH < 30 MiB). Rows 2 and 3 are the **Refuted** rows. Added rows:
>
> | Observation | Meaning |
> |---|---|
> | held = min(300, L) but no log line and no `NTCREFUSE` line at L ∈ {200, 50} | No direct disallow evidence; Not confirmed |
> | held = min(300, L) and ΔH follows the knob, but a band or ratio of B3f is missed | Not confirmed (shape right, numbers outside the frozen prediction) |
> | s0 control ΔH ≥ 30 MiB | Per-connection overhead larger than traced; Not confirmed |
> | n100 control outside [383, 484] MiB | Positive control did not scale with N; workload invalid |
> | Any reading that matches no row above | Not confirmed; record it as feedback to stage 3 |

**B3h. Controls.**
- Positive control: L = -1 with N = 100 and N = 300 shows ΔH moves with N (≈ 400 vs 1,200 MiB), so the workload moves memory where nothing caps it.
- S = 0 control: at L = -1, open 300 connections that send nothing (run with `s = -1`, which skips the send). ΔH should be < 30 MiB, which bounds the per-connection object overhead.
- The `ss` count, run independently of the script, rules out client-side miscounting.
- The heap-allocator flag puts the bytes where GC tools see them. Running the L = -1 case once without the flag and seeing ΔH ≈ 0 on heap shows the flag is what moved them.

> **Amendment C8 (2026-10-27, stage-4 step-0 audit, before any harness run or reading).** The premise of the last control (the
> flag moves the bytes onto the heap) is contradicted by the source (C4): the cumulation is direct with or without the flag. The
> no-flag run is therefore not run; the flag is kept only because it makes `CBUtil.allocator` an `UnpooledByteBufAllocator`, whose
> metric counts each live buffer's capacity (C4). Where the bytes are not is shown instead by the heap context readings of every
> run (C4: class-histogram `[B` and `Total`). The `ss` control is the netstat count of C3.

**B4. Risks and cleanup.**
- Unit tier: in-JVM only; the test file lives in the local clone. Delete `/local/c509` when done if space matters.
- Cluster tier: data, commit log and hints go under `/local/cass` (local disk, < 1 GB). Heap use peaks at about 1.3 GB of the 4 GB heap.
- After each run: kill `hold.py` and confirm `pgrep -f hold.py` is empty; stop Cassandra and confirm `pgrep -f CassandraDaemon` is empty; confirm `ss -Htn '( sport = :9042 )'` shows no sockets; `rm -rf /local/cass`.
- Do not run against a shared node: the workload deliberately holds about 1.2 GB of heap.

> **Amendment C9 (2026-10-27, stage-4 step-0 audit, before any harness run or reading).** On this host: node files under
> `$W/node-ntc` (removed at the end), the copied unit test removed from the clone after the unit run, and the checks are
> `pgrep -f <harness>/hold.py` empty, no Cassandra daemon in `ps -eo command`, no listener on 9042 (`lsof -nP -iTCP:9042
> -sTCP:LISTEN`), and the clone's `git status --short` empty. The ~1.2 GB held is direct memory (C4), within the node's default
> `MaxDirectMemorySize` (a quarter of 32 GiB RAM, `conf/cassandra-env.sh:58-66`).

## C. Sources read

- `src/java/org/apache/cassandra/transport/ConnectionLimitHandler.java`
- `src/java/org/apache/cassandra/transport/PipelineConfigurator.java`
- `src/java/org/apache/cassandra/transport/InitialConnectionHandler.java`
- `src/java/org/apache/cassandra/transport/Envelope.java`
- `src/java/org/apache/cassandra/transport/CBUtil.java`
- `src/java/org/apache/cassandra/transport/CQLMessageHandler.java`
- `src/java/org/apache/cassandra/net/AbstractMessageHandler.java`
- `src/java/org/apache/cassandra/transport/Dispatcher.java`
- `src/java/org/apache/cassandra/config/Config.java`
- `src/java/org/apache/cassandra/config/DatabaseDescriptor.java`
- `src/java/org/apache/cassandra/config/CassandraRelevantProperties.java`
- `src/java/org/apache/cassandra/service/StorageProxy.java`, `StorageProxyMBean.java`
- `conf/cassandra.yaml`
- `.build/parent-pom-template.xml`
- https://netty.io/4.1/api/io/netty/handler/codec/ByteToMessageDecoder.html
- https://issues.apache.org/jira/browse/CASSANDRA-8086

## D. Stage-4 feedback

**2026-10-27, stage 4 run 1 (Claude Opus 5.5 `claude-opus-5-5`, advisor-run, the advisor's Mac; results [`../../stage4-runtime-verification/results/native_transport_max_concurrent_connections-channelActive-limit--autonomous.md`](../../stage4-runtime-verification/results/native_transport_max_concurrent_connections-channelActive-limit--autonomous.md); case file uncommitted at sha256 `8f7f5202…8153`, on `419619f`).**
- Unit: **Confirmed — caps** (B2g row 1). Open 64 / 64 / 8 / 32 at L = -1 / 0 / 8 / 32, held = open × 1,048,585 bytes exactly, `counter` = open at L ∈ {8, 32} and 0 at L ∈ {-1, 0} (no handler installed), 0 after every close; the S0 control held 0.
- Cluster: **Confirmed — caps** (B3g row 1). Kept 300 / 200 / 50 connections at L = -1 / 200 / 50 (script and netstat), native-transport allocator ΔH = 1,200.0 / 800.0 / 200.0 MiB (exactly 4 MiB per kept connection), N − L refusals at the `:97` close (100 and 250), one NoSpamLogger line per refusing node, everything back to 0 B after the clients left; positive control N = 100 400.0 MiB, S = 0 control 0 MiB.
- Audit amendments U1–U4 and C1–C9 (2026-10-27, above); no runbook defect. For stage 3: (1) the B2f L = -1 `counter` cell was wrong — with both limits ≤ 0 no handler is installed, so nothing counts (U3); (2) on a real node the partly received envelopes are **direct** memory even with `cassandra.netty_use_heap_allocator=true` (Netty `ioBuffer()` is direct whenever Unsafe is available, and the merge cumulator keeps that first read buffer), so B3d's heap instruments could not see the bytes; the allocator metric did (C4), and the B3h no-flag control was not run (C8); (3) the production default (pooled allocator) was not measured.
