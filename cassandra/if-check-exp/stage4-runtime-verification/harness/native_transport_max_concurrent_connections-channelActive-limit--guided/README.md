# Harness — native_transport_max_concurrent_connections-channelActive-limit--guided

Instruments for the case's §9 (stage 4), written 2026-10-20 after the step-0 audit (frozen §9 hash `52393486…`, results
file §1), before any reading. Run from a copy on the node, `~/stage4-harness-run/ncc/` (compare `md5sum` with the repo
first); both run scripts write the harness `md5sum` into their `summary.txt`.

| File | Tier | What it is | Checked how |
|---|---|---|---|
| `ConnectionLimitHandlerTest.java` | unit | Package `org.apache.cassandra.transport`. `ConnectionLimitHandler` in an `EmbeddedChannel` pipeline (remote address an `InetSocketAddress`) ahead of a counting stub: u1 limits *k*−1, *k*, *k*+1, *k*/2, −1 for *k* = 100 channels (open, downstream `channelActive`, the handler's `counter` by reflection, the boundary channel, counter 0 after close); u2 per-IP 10 from two addresses; u3 the limit is read only at `channelActive`; u4 `PipelineConfigurator.configureInitialPipeline` installs the handler first iff a limit is > 0. `STAGE4 check` lines; fails at the end on any mismatch. | shakedown 1 found a harness bug (the stub was not `@Sharable`, so every channel after the first failed to build); fixed; shakedown 2: 44 checks, 0 mismatches |
| `unit-run.sh [run]` | unit | Copies the test into the clone, `ant testsome`, `EXPECTED:` lines. Output `~/stage4-logs/ncc/<run>/unit/`. | — |
| `ncc.btm` | cluster | Byteman, 6 rules: `acc`/`rej` (admitted / refused at `channelActive`, with `count` and `limit`), `ina` (counter after `channelInactive`), `new` and `acq` (CQL handler queue capacity and every capacity acquire; from the `native_transport_receive_queue_capacity` harness), `hold` (the control's requests wait at `Dispatcher.processRequest` entry while the hold file exists, through `stage4.Hold`). Observation only except `hold`. | `TestScript`: 6 rules type checked, no errors (2026-10-20); `Submit -l` lists 6 at every node start |
| `Hold.java` | cluster | `stage4.Hold.await(file, maxMs)`, on the node's boot class path. | — |
| `hold_connections.py` | cluster | The 9c client: 4,000 idle TCP sockets from 127.0.0.1, never a byte sent; a selector counts sockets the server closes; `HELD` line at 30 s, holds until a stop file appears. | the shakedown |
| `HeldRequests.java` | cluster | The control client (on `SimpleClient`, protocol v5, default overload mode): 64 connections, one 1 MiB-blob `SELECT … ALLOW FILTERING` each, waits for every response. Connection code from `NativeFlood` (`native_transport_receive_queue_capacity` harness). | the shakedown |
| `cluster-run.py <run> <label…>` | cluster | One node lifetime per label, `-Xms2G -Xmx2G`: `idle` (arms warm, m1a, L2000, m1b, L1000, m1c, L500: limit set live and read back, burst, sample at 30 s, close, counter back to 0; R1 analysis), `C0-1g` / `C0-16m` (9f R2 as frozen), `C-1g` / `C-16m` (R2 with `native_transport_receive_queue_capacity` 0B, results §3 defect 1). Per sample: `ss`, `GC.class_histogram` (full GC), `GC.heap_info`, `/proc/<pid>/status`, fd count, JMX gauges. `EXPECTED:` lines; node stopped on any exit. | its own set-up checks stop the run on failure |
| `Jmx.java` | cluster | JMX reader from the `batch_size_fail_threshold` harness, plus `setlong` (the `Long` attribute `NativeTransportMaxConcurrentConnections`). | the read-back after each set |
| `make-node-yaml.sh` | cluster | Builds `~/stage4-ncc/conf` (loopback, data under `~/stage4-ncc/data`). From the `batch_size_fail_threshold` harness, names changed. | the yaml tail in `summary.txt` |
| `client-logback.xml` | cluster | Client logging: warnings only. | — |

**Read before run 1 (from the source and the shipped conf, no reading):**

- `conf/jvm-server.options:128` sets `-XX:+AlwaysPreTouch`, so the whole 2 GiB heap is resident from start and
  `RssAnon` cannot show heap growth; it sees only native memory. The heap readings are the histogram `Total` after a
  full GC and `GC.heap_info` after it. The primary heap reading is the histogram `Total` (live bytes after the full GC
  the histogram forces); `GC.heap_info` is taken right after without another GC, so it also counts what was allocated
  in between (the shakedown showed both within 1 KB on an idle node).
- The node uses the epoll transport (`NativeTransportService.useEpoll()`, the native jar is in `lib/`), so 9d's
  `NioSocketChannel` row is read as `io.netty.channel.epoll.EpollSocketChannel` (both are recorded).
- 9f R2's control does not bind as written: every connection's own receive queue capacity (1 MiB by default,
  `AbstractMessageHandler.acquireCapacity:419`) takes a 1 MiB request, so only the few bytes above 1 MiB are drawn from
  the 16 MiB reserves (results §3, defect 1). Both the frozen arms and the fixed ones run.

Run order (run 1):

```bash
H=~/stage4-harness-run/ncc
$H/unit-run.sh run1
python3 $H/cluster-run.py run1 idle C0-1g C0-16m C-1g C-16m      # background job; about 20 min
```

**Instrument check (2026-10-20, not readings):** `TestScript` on `ncc.btm`: 6 rules type checked, no errors. Unit shakedown 2:
44 checks, 0 mismatches. Cluster shakedown 1 (`NCC_COUNT=300 NCC_HOLD_S=5 NCC_LIMITS=200,100,50`, labels `idle` and `C-16m`,
logs `~/stage4-logs/ncc/shakedown1/`): every set-up check passed; Submit -l listed 6 rules; open = min(count, limit) with
`acc`/`rej`/`ina` lines and the counter back to 0; the control's queue capacity read back 0, 15 requests held and
`RequestsSize` 15,729,750 B. One expected line said NO by design of the shakedown, not of the harness: the
`NoSpamLogger` line appears once a minute, and the shakedown's arms were seconds apart (run 1's refusal arms are about
90 s apart).
