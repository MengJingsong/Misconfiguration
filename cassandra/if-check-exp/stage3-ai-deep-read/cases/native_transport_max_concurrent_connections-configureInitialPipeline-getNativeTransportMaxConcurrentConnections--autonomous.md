# native_transport_max_concurrent_connections — verification solution  <!-- file: cases/native_transport_max_concurrent_connections-configureInitialPipeline-getNativeTransportMaxConcurrentConnections--autonomous.md -->

| Field | Value |
|---|---|
| Entry pointer | [`PipelineConfigurator.java:240`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/transport/PipelineConfigurator.java#L240) |
| Pinned source | `cassandra-5.0.9` |
| Session / date | Claude Opus 5.5 (`claude-opus-5-5`), Claude Code CLI, 2026-10-26 (Band D triage) |
| Estimate | `positive`. Line 240 installs `ConnectionLimitHandler` when the limit is > 0. The handler closes every connection beyond the limit before it reads a byte, which bounds how many per-connection buffer sets (pipeline, decoder cumulation of up to one max frame, connection state) exist at once. Memory is capped only as count × footprint per connection. |
| Ground | — |

## A. Constraint trace

**A1. The constraint.** `native_transport_max_concurrent_connections` is a configuration
entry (`long`, a count) declared at [`Config.java:289`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/Config.java#L289).
Its default is `-1`, meaning unlimited (`conf/cassandra.yaml:1046-1048`). The getter and
setter are at [`DatabaseDescriptor.java:3163-3171`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/DatabaseDescriptor.java#L3163-L3171). It can be set in yaml, or at runtime
through JMX as `StorageProxyMBean.setNativeTransportMaxConcurrentConnections`
([`StorageProxy.java:2851-2852`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/service/StorageProxy.java#L2851-L2852), [`StorageProxyMBean.java:56-57`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/service/StorageProxyMBean.java#L56-L57)); there is no nodetool
command. A runtime change applies to connections accepted afterwards. See the overshoot
note in A3.


**Limit type (2026-10-29).** config: yaml entry. The traced constraint decides ([README §6](../README.md#6-rules-that-hold-for-both-agents)).
**A2. What it caps.** It caps the number of concurrently open native (CQL) client
connections. The resource is the heap and off-heap memory those connections hold: the
Netty channel and pipeline, the `InitialConnectionHandler` or `Envelope.Decoder`
cumulation (up to `native_transport_max_frame_size` for an incomplete frame,
`Envelope.java:429-442`), `ServerConnection` and `ClientState`. The quantity compared is
`counter`, an `AtomicLong` that counts active channels which passed through the handler
(`ConnectionLimitHandler.java:56, 87-99`).

**A3. Mechanism.**
1. On every accepted channel, `initChannel` calls `configureInitialPipeline`
   ([`PipelineConfigurator.java:155-163`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/transport/PipelineConfigurator.java#L155-L163)).
2. **Entry line 240:** if `getNativeTransportMaxConcurrentConnections() > 0` or the per-IP
   limit is > 0 (`:240-241`), the code adds the shared static `connectionLimitHandler`
   first in the pipeline (`:73, 244`). Otherwise no handler is added and nothing is counted.
3. `channelActive` increments `counter`. A limit < 0 means `Long.MAX_VALUE`. If
   `count > limit`, it logs and calls `ctx.close()` without firing `channelActive`
   further ([`ConnectionLimitHandler.java:87-99`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/transport/ConnectionLimitHandler.java#L87-L99)). Otherwise it goes on to the per-IP
   check (`:101-127`).
4. `channelInactive` decrements the counter (`:131-145`).

At the limit, the new connection is accepted by the kernel and Netty, then closed at
once, so no client bytes are decoded.

Bypasses and overshoot:
- **Runtime enabling:** channels accepted while both limits were ≤ 0 have no handler and
  are never counted. If the limit is set later through JMX, `counter` reflects only the
  new channels, so the real count can exceed the limit by the number of connections that
  existed before.
- Each rejected connection briefly costs one channel before the close.
- The limit does not bound memory per connection: that depends on frame size, in-flight
  requests and so on.

**A4. Other consumers.** Per-connection memory is governed by other limits:
`native_transport_max_frame_size`, `native_transport_max_request_data_in_flight[_per_ip]`,
`native_transport_receive_queue_capacity`, and `native_transport_max_message_size` for v5.
Internode connections are not counted. Sessions on the JMX or other ports are not counted.

**A5. Evidence beyond the source.** `conf/cassandra.yaml:1046-1052`. The log message in
`ConnectionLimitHandler.java:96` names the yaml key.

## B. Verification solution

**B1. Claim under test.** With `native_transport_max_concurrent_connections = N > 0`, at
most N client connections stay open. Memory held by connections that each keep an
incomplete frame scales with min(attempted, N) instead of with the number attempted. With
the limit at -1, it scales with the number attempted.

### B2. Unit tier

**B2a. Environment and build.** JDK 11 and Ant. Work in a local copy:
`git clone --branch cassandra-5.0.9 <shared-clone> /local/c509 && cd /local/c509 && ant jar build-test`.
Put the test at `test/unit/org/apache/cassandra/transport/ConnLimitProbeTest.java`
(same package, so package-private classes are visible).

> **Amendment U1 (2026-10-27, stage-4 step-0 audit, before any harness run or reading).** B2a and B2e on this host (the advisor's Mac, `stage4-runtime-verification/environment-advisor.md`): there is no `/local`. The run clone is `$W/cassandra-run55` (`W=~/Library/Caches/stage4`; `git clone --branch cassandra-5.0.9 ~/cassandra-src $W/cassandra-run55`, commit `b5f2a54210`), built with `ant -Dlocal.repository=$W/m2 build-test` (it also builds the jar classes the cluster tier uses). The test source is kept in `stage4-runtime-verification/harness/<this stem>/ConnLimitProbeTest.java` and copied to `test/unit/org/apache/cassandra/transport/ConnLimitProbeTest.java` in the clone by `harness/<this stem>/unit-run.sh`, which runs `ant -Dlocal.repository=$W/m2 testsome -Dtest.name=org.apache.cassandra.transport.ConnLimitProbeTest`, logs every command, and copies `build/test/logs/**/TEST-*ConnLimitProbeTest*.log` out. The test yaml (`test/conf/cassandra.yaml`) sets neither limit, so both start at -1 (`Config.java:289-290`).

**B2b. Knobs.** Set `DatabaseDescriptor.setNativeTransportMaxConcurrentConnections(v)`
for v in {-1, 0, 5, 20}, keeping the per-IP limit at -1. The value -1 is the default, 0
skips the gate at line 240 (`> 0` is false), and 5 and 20 bracket the attempt count.

**B2c. Workload.** In `@BeforeClass`, call `DatabaseDescriptor.daemonInitialization()`.
Build `PipelineConfigurator pc = new PipelineConfigurator(false, false, false, EncryptionOptions.TlsEncryptionPolicy.UNENCRYPTED)`.
For each knob value, open M = 10 channels:
```java
EmbeddedChannel ch = new EmbeddedChannel(false, false);
ch.pipeline().addLast(new ChannelInitializer<Channel>() {
    protected void initChannel(Channel c) { pc.configureInitialPipeline(c, null); }
});
ch.register();   // fires channelActive through the configured pipeline
```
The `null` connection factory is unused until STARTUP. With the limit at 5 and M = 10,
the limit is crossed at channel 6.

**B2d. Observables and instruments.** Record `ch.isOpen()` for each channel, and whether
the pipeline contains `"connectionLimitHandler"`. Read the handler's private `counter`
by reflection on the static `PipelineConfigurator.connectionLimitHandler`. Close all
channels between knob values, then check that `counter` returns to 0.

> **Amendment U2 (2026-10-27, stage-4 step-0 audit, before any harness run or reading).** B2c and B2d, exact. Values run in the order -1, 0, 5, 20, in one JVM; before each value the test sets the per-IP limit to -1 and the global limit to the value with the `DatabaseDescriptor` setters (`DatabaseDescriptor.java:3168-3171`). For each channel i = 1..10: build it as B2c says, call `ch.register()` and then `ch.runPendingTasks()` (so a refused channel's queued `channelInactive` has run before the reading), and print `CH,<limit>,<i>,<open>,<handlerPresent>,<counter>`, where `handlerPresent` is read inside `initChannel` right after `configureInitialPipeline` returns (a refused channel's pipeline is emptied when it is closed and deregistered, so it cannot be read afterwards). After the 10 channels: `PROBE,<limit>,<openCount>,<counter>,<handlerPresentCount>`. Then every channel is closed (`ch.close()`, `ch.runPendingTasks()`) and `CLOSED,<limit>,<counter>` is printed. `counter` is read by reflection from the private field `counter` of the object in the private static field `connectionLimitHandler` of `PipelineConfigurator` (`PipelineConfigurator.java:73`, `ConnectionLimitHandler.java:54`). A final `READBACK,<getNativeTransportMaxConcurrentConnections>,<getNativeTransportMaxConcurrentConnectionsPerIp>` line is printed for each value right after it is set. The test asserts nothing that would stop it early; it only prints, and the readings are matched in B2g.

**B2e. Procedure.** Run
`ant testsome -Dtest.name=org.apache.cassandra.transport.ConnLimitProbeTest`. The test
prints `limit,openCount,counter,handlerPresent`.

**B2f. Predictions.**
- -1: 10 open, no handler, counter unchanged at 0.
- 0: the same as -1.
- 5: handler present, 5 open and 5 closed, counter 5 after the rejected channels close
  (each close fires `channelInactive` and decrements).
- 20: 10 open, counter 10.

> **Amendment U3 (2026-10-27, stage-4 step-0 audit, before any harness run or reading).** B2f, exact values from source (`PipelineConfigurator.java:240-245`, `ConnectionLimitHandler.java:84-98, 134-136`): -1 and 0 → `PROBE,v,10,0,0` (no handler, so the counter is never touched); 5 → channels 1-5 open and 6-10 closed, `PROBE,5,5,5,10` (each refused channel increments, is closed, and its `channelInactive` decrements); 20 → `PROBE,20,10,10,10`; every `CLOSED` line has counter 0; every `READBACK` echoes the value and -1. Line citations corrected: `counter` is `ConnectionLimitHandler.java:54`, `channelActive` is `:84-131`, `channelInactive` is `:134-148` (A2, A3 cite :56, :87-99, :131-145).

**B2g. Readings.**
| Observation | Meaning |
|---|---|
| 5 → exactly 5 open; -1/0 → 10 open | Mechanism works as traced |
| 5 → more than 5 open | Claim wrong: the limit does not stop connections |
| 0 → the handler is installed | The trace of the line-240 gate is wrong |
| counter does not return to 0 after closing | Leak in the counter (record it; it affects later limits) |

> **Amendment U4 (2026-10-27, stage-4 step-0 audit, before any harness run or reading).** B2g, rows with verdicts (Effect in brackets), checked in this order; the first matching row is the result. **I (Invalid):** at 5 or 20 the handler is present on every channel but the counter stays 0 and all 10 channels stay open (`channelActive` did not reach the handler; the instrument is blind). **R1 (Refuted — does not cap):** at 5, more than 5 channels are open. **R2 (Refuted — the line-240 gate trace is wrong):** at 0 or -1 the handler is installed on any channel. **C (Confirmed — caps the connection count):** every U3 value holds (the -1/0 controls 10 open with no handler; 5 → exactly channels 1-5 open, counter 5; 20 → 10 open, counter 10; counter 0 after each close). **N1 (Not confirmed — counter leak):** everything as C except a `CLOSED` counter ≠ 0. **N2 (Not confirmed):** no row fits (record which value differs). The unit tier measures no memory; its Effect speaks only of the connection count, and the memory side is the cluster tier's.

**B2h. Controls.** The -1 and 20 runs are the unlimited controls. Reset the counter
between values by closing every channel. If the EmbeddedChannel registration timing
differs (no `channelActive`), check with a channel that has the handler but limit 20,
which must stay open.

### B3. Cluster tier

**B3a. Environment and build.** One Linux node from `/local/c509` (`ant jar`). Use a
config copy at `/local/c509-conf` with data, commit log, hints and saved caches under
`/local/c509-data` (local disk, at least 5 GB free). Set the environment:
`export CASSANDRA_CONF=/local/c509-conf MAX_HEAP_SIZE=1G HEAP_NEWSIZE=256M JVM_EXTRA_OPTS="-XX:NativeMemoryTracking=summary -XX:MaxDirectMemorySize=2G"`.
Keep `native_transport_max_frame_size` at its default of 16MiB and
`native_transport_idle_timeout` at 0.

**B3b. Knobs.** `native_transport_max_concurrent_connections: -1` (run A, unlimited) and
`native_transport_max_concurrent_connections: 16` (run B). Keep the per-IP limit at -1
in both. Restart between runs.

> **Amendment C1 (2026-10-27, stage-4 step-0 audit, before any harness run or reading).** B3a and B3b on this host. There is no `/local`, no `ss`, no `/proc`, no `setsid`. The node runs from the clone `$W/cassandra-run55` (built in U1; `ant` is not run in it while a node runs). Node files live under `$W/node-ntcc` (data, commit log, hints, saved caches, cdc_raw, logs, and a copy of the clone's `conf/` with these overrides: `listen_address` and `rpc_address` 127.0.0.1, the directories, and `native_transport_max_concurrent_connections: <value>`; the per-IP limit, `native_transport_max_frame_size` (16MiB) and `native_transport_idle_timeout` (0ms, `Config.java:139`) are left at their defaults). The directory is made fresh for every node start and removed at the end. The node is started as a tracked background process, `CASSANDRA_CONF=$W/node-ntcc/conf CASSANDRA_LOG_DIR=$W/node-ntcc/logs MAX_HEAP_SIZE=1G HEAP_NEWSIZE=256M JVM_EXTRA_OPTS="-XX:NativeMemoryTracking=summary -XX:MaxDirectMemorySize=2G -Dcassandra.netty_use_heap_allocator=true" bin/cassandra -f > node-stdout.log 2>&1 < /dev/null &`; its pid is found with `pgrep -f cassandra.logdir=$W/node-ntcc/logs`. **Two changes to B3b, both from source and before any reading.** (1) **A third value, 32 (run C)**, so the knob takes three values including the default (-1, 16, 32): 32 lies between 16 and K = 64, so the cap still binds, and it doubles run B's ceiling. (2) **Every node runs with `-Dcassandra.netty_use_heap_allocator=true`.** Without it the native transport's allocator is `PooledByteBufAllocator(true)` (`CBUtil.java:59-60`) with `-Dio.netty.allocator.maxOrder=11` (`conf/jvm11-server.options:145`), so each direct arena commits 16 MiB chunks (8 KiB pages << 11) on first use and keeps them. The worker group is `new NioEventLoopGroup()` (`NativeTransportService.java:74`), which has 2 × 10 = 20 event loops on this host, each tied to one of min(2 × 10, 2048 MiB / 16 MiB / 6) = 20 direct arenas. So 16 held connections spread over up to 16 loops can commit up to 16 × 16 MiB = 256 MiB of `Other` whatever they hold, inside run A's band, and run B could not be told from run A: the instrument would be blind to the quantity B1 bounds. With the flag the allocator is `UnpooledByteBufAllocator(false)`, whose `ioBuffer()` still returns direct buffers when Unsafe is available (Netty 4.1.130 `AbstractByteBufAllocator.ioBuffer`), so every socket read buffer and the decoder's merge cumulation are exact-size direct buffers allocated through `Unsafe` (NMT `Other`) and freed on close. The flag does not touch `PipelineConfigurator` or `ConnectionLimitHandler`. B3g's last row already names this flag as the fallback; it is used from the start instead.

**B3c. Workload.** Save this as `/local/tools/hold_frames.py`, outside the clone. It opens
K raw connections. Each one sends a v4 OPTIONS header that declares a body of L bytes,
then sends L-1 bytes and holds the connection open. A socket the server closed shows up
as an exception and is counted.
```python
import socket, struct, sys, time
host, port, K, L, hold = sys.argv[1], int(sys.argv[2]), int(sys.argv[3]), int(sys.argv[4]), int(sys.argv[5])
socks, failed = [], 0
for i in range(K):
    try:
        s = socket.create_connection((host, port))
        s.sendall(struct.pack('>BBhBI', 0x04, 0, 1, 0x05, L))
        sent, chunk = 0, b'\0' * 65536
        while sent < L - 1:
            n = min(65536, L - 1 - sent); s.sendall(chunk[:n]); sent += n
        socks.append(s)
    except OSError:
        failed += 1
print("attempted", K, "send_failed", failed, flush=True); time.sleep(hold)
for s in socks: s.close()
```
Use K = 64 and L = 4 MiB (4194304). The direct memory this targets is 64 × 4 MiB =
256 MiB unlimited, against 16 × 4 MiB = 64 MiB with the cap. Hold for 120 s. On a
rejected socket, `sendall` of 4 MiB is expected to fail with a reset, because the
server closed it with `SO_LINGER 0` (`PipelineConfigurator.java:136`).

> **Amendment C2 (2026-10-27, stage-4 step-0 audit, before any harness run or reading).** B3c. `hold_frames.py` is kept verbatim (same code) at `stage4-runtime-verification/harness/<this stem>/hold_frames.py`, outside the clone, and is run with the system Python 3.8. **L is changed from 4194304 to 4194296**, from source and before any reading. Each connection's held bytes are the 9-byte v4 header plus L − 1 body bytes. The decoder (`InitialConnectionHandler` extends Netty's `ByteToMessageDecoder` with the default merge cumulator, `InitialConnectionHandler.java:52, 67-71`, `Envelope.java:441-442` returns null while `readableBytes < totalLength`) grows its cumulation with `AbstractByteBuf.ensureWritable0` → `AbstractByteBufAllocator.calculateNewCapacity`: the next power of two up to the 4 MiB threshold, then whole 4 MiB steps (checked in the bytecode of `netty-buffer-4.1.130.Final.jar`). With L = 4194304 a connection holds 4194312 bytes, just over 4 MiB, so its cumulation would be 8 MiB, twice what B3c's arithmetic and B3f's bands assume (64 × 8 = 512 MiB against the 520 MiB upper bound, 16 × 8 = 128 MiB against 130 MiB). With L = 4194296 a connection holds exactly 4194304 bytes = 4 MiB, the cumulation is exactly 4 MiB (`calculateNewCapacity` returns the threshold when asked for it), the frame stays incomplete (`totalLength` = 4194305 > 4194304 readable) and far below the 16 MiB frame limit, and B3c's arithmetic (64 × 4 MiB = 256 MiB unlimited, 16 × 4 MiB = 64 MiB capped, and 32 × 4 MiB = 128 MiB for run C) holds as written. The command is `python3 hold_frames.py 127.0.0.1 9042 64 4194296 120`.

**B3d. Observables and instruments.**
- `ss -tn state established '( sport = :9042 )' | wc -l` on the server: the established
  CQL connections, sampled every 5 s.
- The `Other` category of `jcmd <pid> VM.native_memory summary.diff`, against a baseline
  taken before the workload.
- `VmRSS` from `/proc/<pid>/status`.
- `grep "Exceeded maximum native connection limit" logs/system.log` (logged at most once
  per minute, through NoSpamLogger).
- The script's `send_failed` count.

> **Amendment C3 (2026-10-27, stage-4 step-0 audit, before any harness run or reading).** B3d on this host. Established connections: `netstat -an -p tcp`, counting lines whose local address is `127.0.0.1.9042` and state `ESTABLISHED` (the server side only). NMT: the committed delta of the `Other` line of `jcmd <pid> VM.native_memory summary.diff` (in KB, reported in MiB = KB / 1024), against the baseline of step 2. RSS: `ps -o rss= -p <pid>` (KB), context only, no row uses it. The log line is counted in the node's `system.log` of the run (each run starts a fresh node, so NoSpamLogger's first refusal is logged). `send_failed` and `attempted` are read from the script's output line.

**B3e. Procedure.**
1. Start the node with `bin/cassandra -p /local/c509-run/pid`, wait for UN, then idle
   for 60 s.
2. Run `jcmd <pid> VM.native_memory baseline` and record VmRSS.
3. Run `python3 /local/tools/hold_frames.py 127.0.0.1 9042 64 4194304 120 &`. After
   20 s, sample `ss`, `summary.diff` and RSS three times, 20 s apart.
4. After the script exits and 15 s more, take the diff again.
5. Stop the node, switch the knob to 16, and repeat steps 1-4.

> **Amendment C4 (2026-10-27, stage-4 step-0 audit, before any harness run or reading).** B3e, exact. Runs in the order A (-1), B (16), C (32), each on a fresh node (C1). Per run: (1) start the node, wait until `nodetool status` shows `UN` and `nodetool statusbinary` prints `running` (abort the run if the daemon dies), record the limit from the `Node configuration` line of `system.log`, then idle 60 s. (2) `jcmd <pid> VM.native_memory baseline`, RSS, and the established count (expected 0). (3) Launch `hold_frames.py` (C2) in the background at t0; at t0 + 20, 40 and 60 s take the established count, `summary.diff` and RSS. Stop condition: if the script has not printed its `attempted` line by t0 + 20 s the run is marked (row I of C6). (4) Wait for the script to exit, then 15 s, and take `summary.diff`, the established count and RSS again. (5) Count the log lines, copy `system.log`, stop the node (`nodetool stopdaemon`, then kill after 60 s) and check that no Cassandra daemon is left. Readings per run: E = the largest of the three established counts, O = the largest of the three `Other` deltas, P = the `Other` delta at step 4, F = `send_failed`, G = the number of `Exceeded maximum native connection limit` lines. A shakedown with small K on a throw-away node precedes run 1 and is not a reading.

**B3f. Predictions.**
- Run A (-1): about 64 established connections; `Other` grows by 230 to 520 MiB, which is
  0.9-2 × 256 MiB; `send_failed = 0`.
- Run B (16): at most 16 established connections; `Other` grows by 55 to 130 MiB, which is
  0.9-2 × 64 MiB; `send_failed` is about 48; the log line is present.
- In both runs, growth returns to near baseline after the script exits.

> **Amendment C5 (2026-10-27, stage-4 step-0 audit, before any harness run or reading).** B3f, exact counts and the run C prediction, from source; the bands are the filed 0.9-2 × rule. Run A: E = 64, F = 0, G = 0, O in [230, 520] MiB. Run B: E = 16, F = 48, G ≥ 1, O in [55, 130] MiB. **Run C (added): E = 32, F = 32, G ≥ 1, O in [115, 256] MiB (0.9-2 × 128 MiB).** In every run P ≤ 0.1 × O (the unpooled buffers are freed when the connections close; this is B3f's "returns to near baseline").

**B3g. Readings.**
| Observation | Meaning |
|---|---|
| B: 16 connections and about 64 MiB; A: 64 connections and about 256 MiB | Claim supported: the limit caps connection-held memory by capping the count |
| B: more than 16 established and memory like A | Claim wrong |
| B: 16 connections, but memory like A | The rejected connections still hold memory before the close (overshoot). Claim wrong for memory |
| A: memory flat | Positive control failed (frames not buffered, or instrument blind). Retry with `-Dcassandra.netty_use_heap_allocator=true` and measure heap |

> **Amendment C6 (2026-10-27, stage-4 step-0 audit, before any harness run or reading).** B3g, rows with verdicts (Effect in brackets), checked in this order; the first matching row is the result; "about" in the filed rows means the C5 bands. **I (Invalid run):** F_A > 0, or E_A < 60, or E_B < 16, or E_C < 32 (the workload was not held, or the limit was not reached), or a script printed no `attempted` line by t0 + 20 s. **R (Confirmed — caps)** (filed row 1): E_B ≤ 16 and E_C ≤ 32; O_A in [230, 520], O_B in [55, 130], O_C in [115, 256] MiB and O_B < O_C < O_A; G_B ≥ 1, G_C ≥ 1, F_B ≥ 1 and F_C ≥ 1 (direct evidence that the disallow branch fired); P ≤ 0.1 × O in every run. **W1 (Refuted — does not cap)** (filed row 2): E_B > 16 or E_C > 32, with O_B > 130 MiB. **W2 (Refuted — does not cap memory; overshoot)** (filed row 3): E_B ≤ 16 but O_B > 130 MiB, or E_C ≤ 32 but O_C > 256 MiB. **N1 (Not confirmed — undetermined; positive control failed)** (filed row 4): O_A < 230 MiB. **N2 (Not confirmed — caps the count, release not observed):** every condition of R except release. **N3 (Not confirmed — undetermined):** no row fits; record which condition failed.

**B3h. Controls.** Run A is the positive control with the same workload. The release in
step 4 ties the growth to the connections. Optional runtime check: start with -1, open
20 connections, then set the limit to 16 through JMX (`org.apache.cassandra.db:type=StorageProxy`,
attribute `NativeTransportMaxConcurrentConnections`) and open 20 more. The prediction is
that up to 36 stay established, because of the uncounted pre-existing channels.

> **Amendment C7 (2026-10-27, stage-4 step-0 audit, before any harness run or reading).** B3h. Run A is the positive control. The optional runtime check is run last, as **run R**, and is informational only: no B3g row uses it and it does not change the verdict. A fresh node with the limit at -1 (C1); `hold_frames.py 127.0.0.1 9042 20 4194296 240` in the background; after its `attempted` line, set `NativeTransportMaxConcurrentConnections` of `org.apache.cassandra.db:type=StorageProxy` to 16 with a small JMX client (`harness/<this stem>/Jmx.java`; read back); then `hold_frames.py 127.0.0.1 9042 20 4194296 120` in the background, and after its `attempted` line take the established count three times 10 s apart. Prediction from source (`PipelineConfigurator.java:240-245`, `ConnectionLimitHandler.java:84-98`): the first 20 channels have no handler and are never counted; of the next 20 the first 16 are counted and stay, and 4 are refused, so 36 established, the second script's `send_failed` = 4, and at least one log line.

**B4. Risks and cleanup.** Nothing goes into the shared clone, and all state lives under
`/local/c509-*`. Afterwards run `kill $(cat /local/c509-run/pid)`, then `pkill -f hold_frames.py`,
and confirm that `pgrep -f CassandraDaemon` returns nothing. Then
`rm -rf /local/c509-data /local/c509-run`. The 2 GiB direct cap keeps the host safe.

> **Amendment C8 (2026-10-27, stage-4 step-0 audit, before any harness run or reading).** B4 on this host: nothing goes into `~/cassandra-src`; the node files are under `$W/node-ntcc` and are removed at the end; full logs stay in `$W/logs/<this stem>/`. Every script stops the node it started (`nodetool stopdaemon`, then `kill`, then `kill -9`), kills its `hold_frames.py` processes, and checks `ps -eo command | grep '[C]assandraDaemon'` is empty. The copied test file is removed from the clone afterwards so that its `git status` is clean.

## C. Sources read

src/java/org/apache/cassandra/transport/PipelineConfigurator.java
src/java/org/apache/cassandra/transport/ConnectionLimitHandler.java
src/java/org/apache/cassandra/transport/Envelope.java
src/java/org/apache/cassandra/transport/InitialConnectionHandler.java
src/java/org/apache/cassandra/transport/CBUtil.java
src/java/org/apache/cassandra/config/Config.java
src/java/org/apache/cassandra/config/DatabaseDescriptor.java
src/java/org/apache/cassandra/service/StorageProxy.java
src/java/org/apache/cassandra/service/StorageProxyMBean.java
conf/cassandra.yaml
conf/cassandra-env.sh

## D. Stage-4 feedback

**2026-10-27, stage 4 run 1** (advisor's Mac; results: [`results/native_transport_max_concurrent_connections-configureInitialPipeline-getNativeTransportMaxConcurrentConnections--autonomous.md`](../../stage4-runtime-verification/results/native_transport_max_concurrent_connections-configureInitialPipeline-getNativeTransportMaxConcurrentConnections--autonomous.md); frozen version sha256 `d59f24607d61abd3ca25e225563948246fc1d007d7e95f739107b98f13ddfd13`, after the audit's amendments U1–U4 and C1–C8; uncommitted at the time of the run). **Unit: Confirmed — caps** (U4 row C): limits -1 and 0 install no handler and keep all 10 channels; 5 keeps exactly channels 1–5, counter 5; 20 keeps 10, counter 10; the counter returns to 0 after every close. **Cluster: Confirmed — caps** (C6 row R): with 64 connections each holding exactly 4 MiB, 64/16/32 stayed established at -1/16/32 and NMT `Other` grew by 256.0/64.0/128.0 MiB = min(64, N) × 4 MiB; 48 and 32 sends were refused and one `Exceeded maximum native connection limit` line was logged in each capped run; the growth fell to 0 after the connections closed. Informational run R: raising the limit from -1 to 16 by JMX with 20 connections open left 36 open (the earlier 20 are never counted), as A3 says. Audit findings for stage 3: the filed L = 4194304 would have made each cumulation 8 MiB (Netty's capacity growth past 4 MiB), and the default pooled allocator would have hidden per-connection bytes behind 16 MiB arena chunks; both were fixed by C1/C2 before any reading. No runbook defect.
