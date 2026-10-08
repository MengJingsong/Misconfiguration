# Harness — internode_application_send_queue_capacity-acquireCapacity-pendingCapacityInBytes

Instruments for the case's section 9 (stage 4). Written 2026-10-07 (evening) from the case's 9c table, after the design audit (results
[§1.1](../../results/internode_application_send_queue_capacity-acquireCapacity-pendingCapacityInBytes.md)). The results are in the same file.

| File | What it is | Checked how |
|---|---|---|
| `SendQueueCapacityTest.java` | Unit tier. Package `org.apache.cassandra.net`; copy into `test/unit/org/apache/cassandra/net/` of a clone at `cassandra-5.0.9`. Builds an `OutboundConnection` with explicit *C*, *E*, *G* as `ConnectionTest.doTestManual()` does and calls the private `acquireCapacity(long, long)` by reflection to see the `Outcome`. Steps U1 to U7 (boundary, one byte over, reserve edge, `INSUFFICIENT_GLOBAL`, release order, only-the-excess, `INSUFFICIENT_ENDPOINT` with rollback), U8 (`enqueue` accepts an 80 KiB message and drops a 256 KiB one, over a real inbound socket) and U9 (a peer nothing listens on borrows nothing; the control borrows). Prints `STAGE4 check …` lines (stdout and `-Dstage4.out`). | exact arithmetic on the limits; the instrumented run (`unit-run.sh instrument`) gave one `config` line per connection built (6) and one `acquire` line per `acquireCapacity` call (16) |
| `SendQueueWiringTest.java` | Unit tier, **its own JVM**. Sets the raw config to send endpoint 2 MiB, receive endpoint 3 MiB, send node-wide 5 MiB, capacity 7 MiB, builds the connections the production way (`withDefaults()` then `OutboundConnections.tryRegister()`) and reads the limits back: U10 (3 MiB = the receive key, 2 MiB would refute §4); U11 (capacity 512 B refused, 1 KiB accepted). | as above |
| `unit-run.sh [instrument\|suffix]` | Copies both tests into the clone and runs `ConnectionTest#testInsufficientSpace`, `#testAcquireReleaseOutbound`, `ResourceLimitsTest`, `SendQueueCapacityTest`, `SendQueueWiringTest`, one `ant testsome` each; `~/stage4-logs/ssq/unit[-suffix]/{run.out,ant-*.log,summary.txt}`. `instrument` runs `SendQueueCapacityTest` alone with `send-config.btm` and `send-acquire.btm` attached. | — |
| `send-config.btm` | Byteman, observation only: one `config` line at the exit of the `OutboundConnection` constructor (type, peer, capacity, effective per-peer and node-wide reserve limits). The read-back for all three limits and the test of §4's wiring. | the instrumented unit run |
| `send-acquire.btm` | Byteman, observation only: one `acquire` line at the exit of `acquireCapacity(long, long)` (count, bytes, `Outcome`, pending bytes and count, overload count, both reserves in use). | the instrumented unit run |
| `hold-delivery.btm`, `Hold.java` | Byteman, the trigger: at the entry of `LargeMessageDelivery.doRun` the delivery thread **parks** in `stage4.Hold.park(path)` while the hold file exists (the helper is compiled into a jar on the boot class path by `cluster-run.py`). S only. | the hold check at the start of every cluster label (pending = *M* and unchanged for 3 s, completed count unchanged, a thread in `Hold.park` in `jcmd Thread.print`, released by removing the file, no second write) |
| `make-node-yaml.sh <S\|R1\|R2\|R3> [key=value …]` | Writes `~/stage4-ssq/<node>/conf` (a copy of `conf/` with that node's `cassandra.yaml` and its `JMX_PORT` 7102 to 7105) and creates the node's directories. Keys the node sets are removed from the shipped yaml first. | the yaml tail is echoed into the log; `S-yaml.diff` is kept per label |
| `Jmx.java` | JMX client, port as the first argument: `get <bean> <attr> …` (several attributes in one JVM start) and `query <pattern>`. Read-only; adapted from the `max_space…` harness. | — |
| `sample-outbound.py` | Python-driver poller (protocol 5, pinned to S) of `system_views.internode_outbound` four times a second. | — |
| `cluster-run.py <label>` | Cluster tier, one script per label (below). Starts R1 to R3 once (they stay up), restarts S per label with the agent, runs the idle control, the hold check, scenario A and B, the drain and the probe, parses the trace by time window, writes `summary.txt` with `EXPECTED:` lines. `cluster-run.py down` stops R1 to R3. | the hold check and the config trace check stop the run on failure; S is stopped and the hold file removed on any exit |

Labels: `c512k c1m c4m c16m` (reserves 1 MiB; idle, hold check, A, B), `defres` (default reserves, B), `nohold` (no-hold control), `c1` and `c2` (one
endpoint key lowered), `peer` (RF = 1, 2, 3 at 4 MiB), `down`. **Not implemented:** the optional hinting observation (9e step 6).

Copy the folder to the node (`~/stage4-harness-run/ssq`) and compare `md5sum` with the repo before a run. The clone is `~/cassandra-run1` at `cassandra-5.0.9`.

```bash
~/stage4-harness-run/ssq/unit-run.sh            # unit tier (and: unit-run.sh instrument)
( setsid nohup ~/stage4-harness-run/ssq/cluster-run.py c1m < /dev/null > /dev/null 2>&1 & )    # one label per call; read ~/stage4-logs/ssq/<label>/summary.txt
```
