# native_transport_max_concurrent_connections_per_ip — verification solution  <!-- file: cases/native_transport_max_concurrent_connections_per_ip-configureInitialPipeline-getNativeTransportMaxConcurrentConnectionsPerIp--autonomous.md -->

| Field | Value |
|---|---|
| Entry pointer | [`PipelineConfigurator.java:240`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/transport/PipelineConfigurator.java#L240) (the second operand of the gate at `:240-241`) |
| Pinned source | `cassandra-5.0.9` |
| Session / date | Claude Opus 5.5 (`claude-opus-5-5`), Claude Code CLI, 2026-10-26 (Band D triage) |
| Estimate | `positive`. When the per-IP limit is > 0, line 240 installs `ConnectionLimitHandler` even if the global limit is off. The handler closes a source IP's connections beyond the limit before they read anything, which bounds the per-connection buffers one client host can pin. The memory bound is count × footprint per connection, and only per source IP. |
| Ground | — |

## A. Constraint trace

**A1. The constraint.** `native_transport_max_concurrent_connections_per_ip` is a
configuration entry (`long`, a count) declared at [`Config.java:290`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/Config.java#L290).
Its default is `-1`, meaning unlimited (`conf/cassandra.yaml:1050-1052`). The getter and
setter are at [`DatabaseDescriptor.java:3173-3181`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/DatabaseDescriptor.java#L3173-L3181). It can be set in yaml or through JMX
([`StorageProxy.java:2854-2855`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/service/StorageProxy.java#L2854-L2855), [`StorageProxyMBean.java:59-60`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/service/StorageProxyMBean.java#L59-L60)); there is no nodetool
command. A change applies to channels accepted afterwards.


**Limit type (2026-10-29).** config: yaml entry. The traced constraint decides ([README §6](../README.md#6-rules-that-hold-for-both-agents)).
**A2. What it caps.** It caps the number of open native connections from one remote
`InetAddress`. The memory those connections hold is the pipeline, the decoder cumulation
of up to `native_transport_max_frame_size` (`Envelope.java:429-442`) and connection
state. The quantity compared is `connectionsPerClient.get(address)`, an `AtomicLong`
(`ConnectionLimitHandler.java:55, 103-125`).

**A3. Mechanism.**
1. **Entry line 240 (second operand):** if `getNativeTransportMaxConcurrentConnectionsPerIp() > 0`,
   the code adds the shared handler first in the pipeline ([`PipelineConfigurator.java:240-245`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/transport/PipelineConfigurator.java#L240-L245)).
2. In `channelActive`, the global check runs first ([`ConnectionLimitHandler.java:87-99`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/transport/ConnectionLimitHandler.java#L87-L99)).
   Then, with `perIpLimit > 0` (`:103-104`), the handler stores the remote address as a
   channel attribute. If there is no `InetSocketAddress`, it closes the channel (`:106-111`).
   It then increments the per-address counter, and if `> perIpLimit`, it logs and closes
   (`:112-126`).
3. `channelInactive` decrements the counter and removes the map entry at 0 (`:131-145`).

Bypasses and overshoot:
- Many source IPs each get the full allowance, so this is not a node-wide cap unless the
  global limit is also set.
- Channels accepted while the gate was off are never counted, so enabling at runtime
  overshoots.
- A remote address that is not `InetSocketAddress` is rejected outright (`:69-73` warn,
  `:108-111` close).

**A4. Other consumers.** The same as for the global limit: frame size, in-flight request
limits, the receive queue, internode traffic, and all connections from other IPs.

**A5. Evidence beyond the source.** `conf/cassandra.yaml:1050-1052`. The log text at
`ConnectionLimitHandler.java:122` names the key.

## B. Verification solution

**B1. Claim under test.** With `native_transport_max_concurrent_connections_per_ip = P > 0`
and the global limit at -1, a single client IP keeps at most P connections open. The
memory those connections pin with incomplete frames scales with min(attempted, P). A
second IP gets its own P.

### B2. Unit tier

**B2a. Environment and build.** The same as the global-limit probe: work in the local
copy `/local/c509` and run `ant jar build-test`. Put the test at
`test/unit/org/apache/cassandra/transport/PerIpLimitProbeTest.java`.

> **Amendment U1 (2026-10-27, stage-4 step-0 audit, before any harness run or reading).** B2a and B2e on this host (the advisor's Mac, `stage4-runtime-verification/environment-advisor.md`): there is no `/local`. The run clone is `$W/cassandra-run56` (`W=~/Library/Caches/stage4`; `git clone --branch cassandra-5.0.9 ~/cassandra-src $W/cassandra-run56`, commit `b5f2a54210`), built with `ant -Dlocal.repository=$W/m2 build-test`, which also builds the classes the cluster tier runs. The test source is kept at `stage4-runtime-verification/harness/<this stem>/PerIpLimitProbeTest.java`; `harness/<this stem>/unit-run.sh` copies it to the B2a path, runs `ant -Dlocal.repository=$W/m2 testsome -Dtest.name=org.apache.cassandra.transport.PerIpLimitProbeTest`, logs every command, copies `build/test/logs/**/TEST-*PerIpLimitProbeTest*.log` out of the clone and removes the copied test. `test/conf/cassandra.yaml` sets neither limit, so both start at -1 (`Config.java:289-290`).

**B2b. Knobs.** Per-IP limit in {-1, 3}, with `setNativeTransportMaxConcurrentConnections(-1)`.
Set through `DatabaseDescriptor.setNativeTransportMaxConcurrentConnectionsPerIp(v)`.

**B2c. Workload.** `PipelineConfigurator pc = new PipelineConfigurator(false, false, false, EncryptionOptions.TlsEncryptionPolicy.UNENCRYPTED)`.
For i in 1..8, create a channel with a real remote address:
```java
final InetSocketAddress ra = new InetSocketAddress(InetAddress.getByName(i <= 6 ? "10.0.0.1" : "10.0.0.2"), 40000 + i);
EmbeddedChannel ch = new EmbeddedChannel(false, false) {
    @Override protected SocketAddress remoteAddress0() { return ra; }
};
ch.pipeline().addLast(new ChannelInitializer<Channel>() {
    protected void initChannel(Channel c) { pc.configureInitialPipeline(c, null); }
});
ch.register();
```
With the limit at 3, IP .1 crosses the limit at its 4th channel, and IP .2's two channels
stay under it.

**B2d. Observables and instruments.** Record `isOpen()` for each channel, and read the
handler's private `connectionsPerClient` map by reflection. Close everything between knob
values, then check that the map is empty.

> **Amendment U2 (2026-10-27, stage-4 step-0 audit, before any harness run or reading).** B2b–B2d, exact. **Values -1, 0, 3, 5**, in that order, in one JVM. 0 is added because it is the other disabled value of the `> 0` gate (`PipelineConfigurator.java:241`); 5 is added so the knob takes four values including the default and the ceiling can be seen to follow it (3 → 3, 5 → 5, both below the 6 channels from 10.0.0.1). Before each value the test sets the global limit to -1 and the per-IP limit to the value with the `DatabaseDescriptor` setters (`DatabaseDescriptor.java:3168-3171, 3178-3181`) and prints `READBACK,<global>,<perIp>`. For each channel i = 1..8, built exactly as B2c says (remote 10.0.0.1:40000+i for i ≤ 6, 10.0.0.2:40000+i for i = 7, 8), it calls `ch.register()` and then `ch.runPendingTasks()`, and prints `CH,<limit>,<i>,<ip>,<open>,<handlerPresent>,<mapCount>`. `handlerPresent` is read inside `initChannel` right after `configureInitialPipeline` returns (Netty empties a pipeline when a closed channel is deregistered, so it cannot be read afterwards). `mapCount` is the value for that address in the private map `connectionsPerClient` (`ConnectionLimitHandler.java:53`) of the handler held in the private static field `connectionLimitHandler` of `PipelineConfigurator` (`PipelineConfigurator.java:73`), read by reflection, 0 when the address is absent. After the 8 channels it prints `PROBE,<limit>,<ip>,<openCount>,<mapCount>` for each of the two addresses; then it closes every channel (`close()`, `runPendingTasks()`) and prints `CLOSED,<limit>,<mapSize>`. After the last value it prints `END`. The test only prints and asserts nothing; the rows are matched in B2g.

**B2e. Procedure.** Run
`ant testsome -Dtest.name=org.apache.cassandra.transport.PerIpLimitProbeTest`. The test
prints `limit,ip,open,mapCount`.

**B2f. Predictions.**
- -1: all 8 open, and no handler is installed (the global limit is also -1).
- 3: for 10.0.0.1, 3 open and 3 closed, with the map at 3 after the rejected channels
  close; for 10.0.0.2, 2 open, with the map at 2.

> **Amendment U3 (2026-10-27, stage-4 step-0 audit, before any harness run or reading).** B2f, exact values from source (`PipelineConfigurator.java:240-245`; `ConnectionLimitHandler.java:84-131` for `channelActive`, `:133-148` for `channelInactive`). **-1 and 0:** no handler on any channel, all 8 open, `PROBE,v,10.0.0.1,6,0` and `PROBE,v,10.0.0.2,2,0`. **3:** the handler is present on all 8; channels 1-3 open, 4-6 closed (each raises the address's count to 4, is closed at `:125`, and its `channelInactive` brings the count back to 3, because the address attribute was set at `:104` before the increment), 7-8 open; `PROBE,3,10.0.0.1,3,3` and `PROBE,3,10.0.0.2,2,2`. **5:** channels 1-5 open, 6 closed, 7-8 open; `PROBE,5,10.0.0.1,5,5` and `PROBE,5,10.0.0.2,2,2`. Every `CLOSED` line has map size 0 (the entry is removed when its count reaches 0, `:142-145`); every `READBACK` line is `-1,<value>`. Line citations corrected (A2 and A3 cite them about two lines high): `connectionsPerClient` is `:53`; the per-IP limit is read at `:101-102`; the null-address close is `:104-109`; the increment and refusal are `:110-127`, with the log text at `:124`; `channelInactive` is `:133-148`; the unknown-type warning is `:68-72`.

**B2g. Readings.**
| Observation | Meaning |
|---|---|
| 3 open for .1, 2 for .2 | Mechanism as traced |
| more than 3 open for .1 | Claim wrong |
| .2 is rejected | The limit is not per IP; the trace is wrong |
| all channels closed, including the first | `remoteAddress0` override not seen (address null path); the run is invalid, so fix the harness |

> **Amendment U4 (2026-10-27, stage-4 step-0 audit, before any harness run or reading).** B2g, rows with verdicts (Effect in brackets), checked in this order; the first matching row is the result. **I (Invalid run; fix the harness)** (filed row 4): at 3 or 5 every channel is closed, including channel 1, or there is no `END` line. **W1 (Refuted — does not cap)** (filed row 2): at 3 or 5, more channels from 10.0.0.1 are open than the limit. **W2 (Refuted — the limit is not per IP)** (filed row 3): at 3 or 5, a 10.0.0.2 channel is closed. **W3 (Refuted — the line-240 trace is wrong):** at -1 or 0 the handler is present on any channel, or at 3 or 5 it is missing on any channel. **C (Confirmed — caps the per-IP connection count)** (filed row 1): every U3 value holds. **N1 (Not confirmed — counter leak):** everything as C except a `CLOSED` map size other than 0. **N2 (Not confirmed — undetermined):** no row fits; record which value differs. The unit tier measures no memory; its Effect speaks only of the connection count per source address, and the memory side is the cluster tier's.

**B2h. Controls.** The -1 run is the unlimited control. The second IP checks that the
counter is per address.

### B3. Cluster tier

**B3a. Environment and build.** One Linux node, set up as in the global case: local
config copy at `/local/c509-conf`, data under `/local/c509-data`, and
`export CASSANDRA_CONF=/local/c509-conf MAX_HEAP_SIZE=1G HEAP_NEWSIZE=256M JVM_EXTRA_OPTS="-XX:NativeMemoryTracking=summary -XX:MaxDirectMemorySize=2G"`.
Set `native_transport_max_concurrent_connections: -1`. Keep the frame size at 16MiB and
the idle timeout at 0. For the second-IP check, give the node `rpc_address: 0.0.0.0` and
`broadcast_rpc_address` set to the host IP, so the client can come from 127.0.0.1 and
from the host's LAN IP.

**B3b. Knobs.** `native_transport_max_concurrent_connections_per_ip: -1` (run A) and
`native_transport_max_concurrent_connections_per_ip: 16` (run B). Restart between runs.

> **Amendment C1 (2026-10-27, stage-4 step-0 audit, before any harness run or reading).** B3a and B3b on this host. There is no `/local`, `ss`, `/proc` or `setsid`. The node runs from the clone `$W/cassandra-run56` (U1; `ant` is not run in it while a node runs). Node files live under `$W/node-ntpip` (data, commit log, hints, saved caches, cdc_raw, logs, and a copy of the clone's `conf/` with these overrides: `listen_address` and `rpc_address` 127.0.0.1, the directories, `native_transport_max_concurrent_connections: -1` (the default, written explicitly) and `native_transport_max_concurrent_connections_per_ip: <value>`; `native_transport_max_frame_size` (16MiB, `Config.java:285`) and `native_transport_idle_timeout` (0ms, `Config.java:139`) are left at their defaults). The directory is made fresh for every node and removed at the end. The node is started as a tracked background process: `CASSANDRA_CONF=$W/node-ntpip/conf CASSANDRA_LOG_DIR=$W/node-ntpip/logs MAX_HEAP_SIZE=1G HEAP_NEWSIZE=256M JVM_EXTRA_OPTS="-XX:NativeMemoryTracking=summary -XX:MaxDirectMemorySize=2G -Dcassandra.netty_use_heap_allocator=true" bin/cassandra -f > node-stdout.log 2>&1 < /dev/null &`. **Three changes, all from source and before any reading.** (1) **A third value, 32 (run C)**, so the knob takes three values including the default (-1, 16, 32); 32 lies between 16 and K = 64, so the cap still binds, and it doubles run B's ceiling. (2) **The second IP is the loopback alias 127.0.0.2**, used as the client's source address (C2), and `rpc_address` stays 127.0.0.1 with no `broadcast_rpc_address`; port 9042 is never exposed to the LAN (B4's risk), and the node sees a second, distinct `InetAddress`. (3) **Every node runs with `-Dcassandra.netty_use_heap_allocator=true`.** Without it the child channels' allocator is `PooledByteBufAllocator(true)` (`CBUtil.java:60`, `PipelineConfigurator.java:138`) with `-Dio.netty.allocator.maxOrder=11` (`conf/jvm11-server.options:145`): each direct arena allocates 8 KiB << 11 = 16 MiB chunks on first use and keeps them, the worker group is `new NioEventLoopGroup()` (`NativeTransportService.java:74`, 2 × 10 = 20 event loops on this host), and there are min(2 × 10, 2048 MiB / 16 MiB / 2 / 3) = 20 direct arenas, so 16 connections holding 4 MiB each, spread over up to 16 loops, could commit up to 16 × 16 MiB = 256 MiB, inside run A's band: NMT would see chunks, not held bytes. With the flag the allocator is `UnpooledByteBufAllocator(false)`, whose `ioBuffer()` returns a direct buffer whenever Unsafe is available (bytecode of `AbstractByteBufAllocator.ioBuffer` in `netty-buffer-4.1.130.Final.jar`), so each socket read buffer and the decoder's cumulation are exact-size direct buffers allocated through Unsafe (NMT `Other`) and freed on close. The flag touches neither `PipelineConfigurator` nor `ConnectionLimitHandler`. B3g's last row names this flag as the fallback; it is used from the start instead.

**B3c. Workload.** The `/local/tools/hold_frames.py` script, outside the clone. It opens
K connections, each sending a v4 OPTIONS header that declares L bytes, then L-1 bytes,
and holds them:
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
Use K = 64 from 127.0.0.1 and L = 4 MiB, which targets 256 MiB unlimited against
16 × 4 MiB = 64 MiB capped. Second-IP step: also run K = 16 against the host LAN IP,
adding 64 MiB in both runs. Hold for 120 s.

> **Amendment C2 (2026-10-27, stage-4 step-0 audit, before any harness run or reading).** B3c. `hold_frames.py` is kept at `stage4-runtime-verification/harness/<this stem>/hold_frames.py`, outside the clone, and run with the system Python 3.8. It is the filed script with one change: an optional sixth argument, a source address, passed as `source_address=(src, 0)` to `socket.create_connection` (absent, the script behaves as filed). **L is changed from 4194304 to 4194296**, from source and before any reading. A connection holds the 9-byte v4 header plus L − 1 body bytes. `InitialConnectionHandler` extends Netty's `ByteToMessageDecoder` with the default merge cumulator (`InitialConnectionHandler.java:52, 67-71`), and `Envelope.Decoder` returns null while `readableBytes < totalLength` (`Envelope.java:441-442`), so the whole partial frame stays in the cumulation. The cumulation is the first read's direct buffer, grown through `writeBytes` → `ensureWritable` → `AbstractByteBufAllocator.calculateNewCapacity`: the next power of two (at least 64) up to 4 MiB, exactly 4 MiB when 4 MiB is asked for, and beyond that the request rounded down to a 4 MiB multiple plus 4 MiB (bytecode of `netty-buffer-4.1.130.Final.jar`; merge cumulator in `netty-codec-4.1.130.Final.jar`). With L = 4194304 a connection holds 4194312 bytes and its cumulation is 8 MiB, twice B3c's arithmetic. With L = 4194296 it holds exactly 4194304 bytes, the cumulation is exactly 4 MiB, the frame stays incomplete (`totalLength` = 4194305 > 4194304 readable) and far below the 16 MiB frame limit, and B3c's arithmetic holds as written: 64 × 4 MiB = 256 MiB unlimited, 16 × 4 MiB = 64 MiB capped, 32 × 4 MiB = 128 MiB for run C, and 16 × 4 MiB = 64 MiB more for the second IP. Commands: `python3 hold_frames.py 127.0.0.1 9042 64 4194296 120` and, for the second-IP step, `python3 hold_frames.py 127.0.0.1 9042 16 4194296 90 127.0.0.2` (checked on this host that a listener on 127.0.0.1 sees such a client as 127.0.0.2).

**B3d. Observables and instruments.**
- `ss -tn state established '( sport = :9042 )'`, grouped by peer address
  (`awk '{print $5}' | cut -d: -f1 | sort | uniq -c`), sampled every 5 s.
- The `Other` category of `jcmd <pid> VM.native_memory summary.diff`, against the
  baseline.
- `VmRSS`.
- `grep "Exceeded maximum native connection limit per ip" logs/system.log`.

> **Amendment C3 (2026-10-27, stage-4 step-0 audit, before any harness run or reading).** B3d on this host. Established connections per source address: `netstat -an -p tcp`, the server-side lines only (local address `127.0.0.1.9042`, state `ESTABLISHED`), grouped by the foreign address with its port removed. NMT: the committed delta of the `Other` line of `jcmd <pid> VM.native_memory summary.diff` (KB; MiB = KB / 1024), against the baseline of step 2. RSS: `ps -o rss= -p <pid>` (KB), context only; no row uses it. Log: the number of `Exceeded maximum native connection limit per ip` lines in the run's `system.log` (G; each run starts a fresh node, and NoSpamLogger logs the first refusal and then at most one line a minute, `ConnectionLimitHandler.java:50`, so G counts at least one line, not refusals), and of the global message `see native_transport_max_concurrent_connections in cassandra.yaml` (Gg). `attempted` and `send_failed` are read from each script's output line; `send_failed` is context only (a refused socket's `sendall` can finish into kernel buffers before the node's close reaches the client, so it is not a row condition).

**B3e. Procedure.**
1. Start the node, wait for UN, then idle for 60 s.
2. Take the baseline with `jcmd <pid> VM.native_memory baseline`.
3. Run `python3 /local/tools/hold_frames.py 127.0.0.1 9042 64 4194304 120 &`. After 20 s,
   sample three times.
4. Second-IP step: run `python3 /local/tools/hold_frames.py <host-lan-ip> 9042 16 4194304 90 &`
   and sample again.
5. After both scripts exit and 15 s more, take the diff again.
6. Stop the node, set the knob to 16, and repeat.

> **Amendment C4 (2026-10-27, stage-4 step-0 audit, before any harness run or reading).** B3e, exact. Runs in the order A (-1), B (16), C (32), each on a fresh node (C1). Per run: (1) start the node, wait until `nodetool status` shows `UN` and `nodetool statusbinary` prints `running` (abort the run if the daemon dies), record the per-IP limit from the `Node configuration` line of `system.log`, then idle 60 s. (2) `jcmd <pid> VM.native_memory baseline`, RSS, and the established count (expected 0). (3) Launch script 1 (64 connections from 127.0.0.1, C2) in the background at t0; at t0 + 20, 25 and 30 s (5 s apart, B3d) take the established counts, `summary.diff` and RSS (samples s1–s3). Stop condition: no `attempted` line from script 1 by t0 + 20 s marks the run (row I of C6). (4) At t0 + 35 s launch script 2 (16 connections from 127.0.0.2); at t0 + 55, 60 and 65 s take the same samples (s4–s6). Stop condition: no `attempted` line from script 2 by t0 + 55 s marks the run. (5) Wait for both scripts to exit, then 15 s, and take `summary.diff`, the established counts and RSS (sample post). (6) Count the log lines, copy `system.log`, stop the node (`nodetool stopdaemon`, then kill after 60 s) and check that no Cassandra daemon is left. Readings per run: E1 = the largest count from 127.0.0.1 over s1–s3; E1' = the largest count from 127.0.0.1 over s4–s6; E2 = the largest count from 127.0.0.2 over s4–s6; O1 = the largest `Other` delta over s1–s3; O2 = the largest over s4–s6; D = O2 − O1; P = the `Other` delta at post; F1, F2 = `send_failed` of scripts 1 and 2; G and Gg (C3). A shakedown with small K on throw-away nodes precedes run 1 and is not a reading.

**B3f. Predictions.**
- Run A: 64 established from 127.0.0.1, `Other` up 230 to 520 MiB; with the second IP,
  80 established and about 64 MiB more.
- Run B: at most 16 from 127.0.0.1, `Other` up 55 to 130 MiB; with the second IP, 16 more
  connections from the LAN IP and about 64 MiB more (it is not blocked by the first IP's
  count); the log line is present.
- Memory returns to near baseline after the scripts exit.

> **Amendment C5 (2026-10-27, stage-4 step-0 audit, before any harness run or reading).** B3f, exact counts and the run C prediction, from source (`PipelineConfigurator.java:240-245`, `ConnectionLimitHandler.java:101-127`, C2's 4 MiB per connection). **Run A:** E1 = E1' = 64, E2 = 16, F1 = F2 = 0, G = 0, O1 in [230, 520] MiB, D in [55, 130] MiB. **Run B:** E1 = E1' = 16, E2 = 16 (exactly the limit, not blocked by 127.0.0.1's count), F2 = 0, G ≥ 1, O1 in [55, 130] MiB, D in [55, 130] MiB. **Run C (added):** E1 = E1' = 32, E2 = 16, F2 = 0, G ≥ 1, O1 in [115, 256] MiB (0.9–2 × 128 MiB, the ratio of the filed bands to 256 and 64 MiB), D in [55, 130] MiB. In every run Gg = 0 and P ≤ 0.1 × O2 (the unpooled buffers are freed when the connections close; this is B3f's "returns to near baseline"). D's band is the filed band for 16 connections, which is what "about 64 MiB more" means here.

**B3g. Readings.**
| Observation | Meaning |
|---|---|
| B: 16 from loopback at about 64 MiB; A: 64 at about 256 MiB | Claim supported |
| B: more than 16 from one IP and memory like A | Claim wrong |
| B: second IP blocked | Not per IP; the trace is wrong |
| A: memory flat | Positive control failed (instrument or buffering); retry with `-Dcassandra.netty_use_heap_allocator=true` and heap measurement |

> **Amendment C6 (2026-10-27, stage-4 step-0 audit, before any harness run or reading).** B3g, rows with verdicts (Effect in brackets), checked in this order; the first matching row is the result; "about" in the filed rows means the C5 bands. **I (Invalid run):** in run A, F1 > 0, E1 < 64 or E2 < 16 (the unlimited control did not hold the workload, so the limit was never passed), or a script printed no `attempted` line by its stop time, or a node did not start. **N1 (Not confirmed — undetermined; positive control failed)** (filed row 4): O1 of run A < 230 MiB. **W1 (Refuted — does not cap)** (filed row 2): E1 of run B > 16 or E1 of run C > 32. **W2 (Refuted — the limit is not per IP)** (filed row 3): E2 < 16 in run B or run C. **W3 (Refuted — the count is capped but memory is not):** E1 within the limit but O1 of run B > 130 MiB or O1 of run C > 256 MiB. **R (Confirmed — caps, per source IP)** (filed row 1): E1 = E1' = 16 in run B and 32 in run C; E2 = 16 in runs B and C; O1 in its C5 band in every run, with O1(B) < O1(C) < O1(A); D in [55, 130] MiB in every run; G ≥ 1 in runs B and C (direct evidence that the per-IP disallow branch fired) and Gg = 0 in every run; P ≤ 0.1 × O2 in every run. **N2 (Not confirmed — caps the count, release not observed):** every condition of R except P. **N3 (Not confirmed — undetermined):** no row fits; record which condition failed.

**B3h. Controls.** Run A is the positive control with the same workload. The second IP
shows the per-address scope. The release step ties memory to the connections.

> **Amendment C7 (2026-10-27, stage-4 step-0 audit, before any harness run or reading).** B3h. Run A is the positive control with the same workload. The second IP (E2 = 16 in run B, while 127.0.0.1 is at its limit of 16) shows the per-address scope; the post sample ties memory to the connections. The runtime-enable overshoot named in A3 is not part of B3 and is not run.

**B4. Risks and cleanup.** Nothing goes into the shared clone, and all files live under
`/local/c509-*`. Binding to 0.0.0.0 exposes port 9042 on the LAN for the test, so run
only on an isolated test host or firewall the port to the client IPs. Afterwards run
`kill $(cat /local/c509-run/pid)` and `pkill -f hold_frames.py`, check that
`pgrep -f CassandraDaemon` is empty, then `rm -rf /local/c509-data /local/c509-run`.

> **Amendment C8 (2026-10-27, stage-4 step-0 audit, before any harness run or reading).** B4 on this host: nothing goes into `~/cassandra-src`; the node files are under `$W/node-ntpip` and are removed at the end; full logs stay in `$W/logs/<this stem>/`. The node listens on 127.0.0.1 only (C1), so no firewall is needed. Every script stops the node it started (`nodetool stopdaemon`, then `kill`, then `kill -9`), kills its `hold_frames.py` processes and checks that `ps -eo command | grep '[C]assandraDaemon'` is empty. The copied test file is removed from the clone afterwards so that its `git status` is clean.

## C. Sources read

src/java/org/apache/cassandra/transport/PipelineConfigurator.java
src/java/org/apache/cassandra/transport/ConnectionLimitHandler.java
src/java/org/apache/cassandra/transport/Envelope.java
src/java/org/apache/cassandra/transport/InitialConnectionHandler.java
src/java/org/apache/cassandra/config/Config.java
src/java/org/apache/cassandra/config/DatabaseDescriptor.java
src/java/org/apache/cassandra/service/StorageProxy.java
src/java/org/apache/cassandra/service/StorageProxyMBean.java
conf/cassandra.yaml
conf/cassandra-env.sh

## D. Stage-4 feedback

**2026-10-27, stage 4 run 1** (advisor's Mac; results: [`results/native_transport_max_concurrent_connections_per_ip-configureInitialPipeline-getNativeTransportMaxConcurrentConnectionsPerIp--autonomous.md`](../../stage4-runtime-verification/results/native_transport_max_concurrent_connections_per_ip-configureInitialPipeline-getNativeTransportMaxConcurrentConnectionsPerIp--autonomous.md); frozen version sha256 `ba3b32eb87542965adcaa4e02ddbab2d5d53068ab57b519ea2defaa806ca76a9`, after the audit's amendments U1–U4 and C1–C8; uncommitted at the time of the run). **Unit: Confirmed — caps** (U4 row C): per-IP limits -1 and 0 install no handler and keep all 8 channels; 3 and 5 keep exactly channels 1–3 and 1–5 of 10.0.0.1 and both channels of 10.0.0.2; the per-address map is empty after every close. **Cluster: Confirmed — caps, per source IP** (C6 row R): with 64 connections from 127.0.0.1 each holding exactly 4 MiB, 64/16/32 stayed established at -1/16/32 and NMT `Other` grew by 256.0/64.0/128.0 MiB = min(64, P) × 4 MiB; 16 more connections from 127.0.0.2 were admitted in every run (+64.0 MiB); one `Exceeded maximum native connection limit per ip` line in each capped run; the growth fell to 0 after the connections closed. Audit findings for stage 3: the filed L = 4194304 would have made each cumulation 8 MiB (Netty's capacity growth past 4 MiB), the default pooled allocator would have hidden per-connection bytes behind 16 MiB arena chunks, and the second-IP step exposed port 9042 on the LAN; all three were fixed by C1/C2 before any reading. The runtime-enable overshoot named in A3 is untested (recommendation S2). No runbook defect.
