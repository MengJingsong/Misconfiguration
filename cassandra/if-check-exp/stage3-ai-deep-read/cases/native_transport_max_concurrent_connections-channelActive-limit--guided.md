# native_transport_max_concurrent_connections — client connection

> **Index:** [../_INDEX.md](../_INDEX.md)
>
> **Source:** apache/cassandra @ tag `cassandra-5.0.9`

**Judgment: `rejected`** (Rule 2, recorded in `rejected.md`, batch "the capacity-word pass": it bounds the *count* of connections, not bytes, and a connection's memory is not fixed at this check). This file writes the rejection up with a test of the opposite claim: that `native_transport_max_concurrent_connections` (and its per-IP twin) does **not** bound the memory a node uses for client connections.

## 1. Location

| Field | Content |
|-------|---------|
| **Case ID** | NATIVE_TRANSPORT_MAX_CONCURRENT_CONNECTIONS-CHANNELACTIVE-LIMIT |
| **Constraint** | `native_transport_max_concurrent_connections` (global) and `native_transport_max_concurrent_connections_per_ip` — configuration entries, default -1 (off), live-settable (JMX on `StorageProxy`) |
| **Enforcement pattern** | (a) the check is the decision |
| **Capacity check** | [`ConnectionLimitHandler.channelActive():93`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/transport/ConnectionLimitHandler.java#L93) — `count > limit` (global); [`:121`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/transport/ConnectionLimitHandler.java#L121) — `perIpCount.incrementAndGet() > perIpLimit` |
| **Decision point** | the same lines: `ctx.close()` vs. `ctx.fireChannelActive()` ([`:129`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/transport/ConnectionLimitHandler.java#L129)) |
| **Allocation site** | what the connection would otherwise build: the rest of the channel pipeline, installed at [`PipelineConfigurator.initChannel():244`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/transport/PipelineConfigurator.java#L244) and onwards |
| **Related cases** | [`native_transport_receive_queue_capacity…`](native_transport_receive_queue_capacity-acquireCapacity-queueCapacity--guided.md) (the byte budget on the same traffic; the positive control) |

```java
final long count = counter.incrementAndGet();
long limit = DatabaseDescriptor.getNativeTransportMaxConcurrentConnections();
if (limit < 0) limit = Long.MAX_VALUE;           // -1 disables it
if (count > limit)
{
    noSpamLogger.error("Exceeded maximum native connection limit of {} ...", limit, count);
    ctx.close();                                  // the decrement is in channelInactive
}
else { ... per-IP check ...; ctx.fireChannelActive(); }
```

## 2. Context

Every client connection to Cassandra's CQL port costs the server some memory: a network channel, a chain of protocol handlers, and, once the client sends requests, buffers for them. Operators can cap how many connections a node accepts, in total and per client address. Without a cap, a burst of clients could exhaust the node's file descriptors and memory.

## 3. Module

| Field | Content |
|-------|---------|
| **Module** | native transport — connection admission (`transport`) |
| **One-line role** | Accepts client TCP connections and builds the protocol pipeline on each. |

## 4. Capacity check & limit

| Field | Content |
|-------|---------|
| **Is this a capacity check?** | partial — the operands are counts of connections, not bytes |
| **Usage-side operand** | `counter` — connections currently active on channels that carry this handler; per client address, `perIpCount` |
| **Limit-side operand** | `getNativeTransportMaxConcurrentConnections()` and `…PerIp()` |
| **Limit type** | Configuration entry |

**Limit initialization path:**

1. [`Config.native_transport_max_concurrent_connections:289`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/Config.java#L289) and [`…_per_ip:290`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/Config.java#L290) — declared, default `-1L`, `volatile`
2. [`DatabaseDescriptor.getNativeTransportMaxConcurrentConnections():3163`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/DatabaseDescriptor.java#L3163) and [`…PerIp():3173`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/DatabaseDescriptor.java#L3173) — read through accessors; live-set via [`StorageProxy MBean:2851`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/service/StorageProxy.java#L2851)
3. [`PipelineConfigurator.initChannel():240-241`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/transport/PipelineConfigurator.java#L240-L241) — **the handler is added to a channel's pipeline only if one of the limits is positive when that channel is created**
4. [`channelActive():93`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/transport/ConnectionLimitHandler.java#L93) — read at the comparison

## 5. Decision point & branch semantics

| Field | Content |
|-------|---------|
| **Decision point** | [`ConnectionLimitHandler.channelActive():93`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/transport/ConnectionLimitHandler.java#L93) |
| **Verdict** | n/a |

| Outcome | Condition | Effect |
|---------|-----------|--------|
| **Allow** | `count <= limit` and the per-IP count is within its limit | `ctx.fireChannelActive()`; the connection proceeds |
| **Disallow** | `count > limit`, or `perIpCount > perIpLimit` | an error is logged (rate-limited) and the channel is closed |

**Not covered:** connections created while both limits were -1 never get the handler (§4 step 3), so they are neither counted nor closed after a limit is switched on; and the counter is per channel carrying the handler, so it is not the node's true connection count in that case.

## 6. Code path

### 6a. Allow path → object creation

1. [`channelActive():93`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/transport/ConnectionLimitHandler.java#L93) — within the limit
2. [`channelActive():129`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/transport/ConnectionLimitHandler.java#L129) — `ctx.fireChannelActive()`
3. [`initChannel():244`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/transport/PipelineConfigurator.java#L244) onwards — the pipeline's other handlers (idle-state, frame decoders, message handlers) are in place for the channel; the handler is first in the pipeline (`addFirst`), so it runs before any request bytes are read

### 6b. Disallow path effect

`ctx.close()` closes the channel immediately; no request is read. `channelInactive` decrements the counter ([`channelInactive():136`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/transport/ConnectionLimitHandler.java#L136)). The channel and its pipeline objects were already created by Netty before `channelActive`, so a refused connection costs a short-lived channel but retains nothing afterwards.

## 7. Object & resource

| Field | Content |
|-------|---------|
| **Object created** | the Netty channel and its pipeline of handlers; request buffers once the client sends |
| **Resource consumed** | heap (channel, pipeline, handler objects), off-heap (socket buffers, pooled receive buffers), file descriptors |
| **Rough sizing** | a fixed per-connection base cost for an idle connection; more once requests arrive, bounded separately by the byte budget |
| **Lifetime / release** | at close (client close, idle timeout, or this handler) |

## 8. Maximum memory/disk bound

For idle connections the node's memory is `connections × per-connection base cost`, so the cap `L` limits that part to `L × base cost`. Active connections add buffered request bytes, limited by the in-flight byte budget, not by `L`. The rejection says the count is not a byte limit; §9 measures the base cost and checks whether memory follows `L` for idle connections.

## 9. Test design (guidance for stage 4)

**Stage 3 writes this section; stage 3 never runs it.** No measured numbers and no verdict are recorded here.

### 9a. Procedure and conclusions

**Testability:** config, live-settable (`StorageProxy` MBean attribute `NativeTransportMaxConcurrentConnections`); a restart is not needed, but the handler is only installed on channels created after the limit is positive (§5), so set it before opening connections.

**Claim under test (the rejection):** the connection limit does not bound the memory used for client connections; node memory after opening far more connections than the limit is the same as without a limit.

**How this verifies the hypothesis:**

- **Hypothesis:** a count is not a byte limit, so memory does not follow the limit.
- **Test:** set the limit to 500, 1,000 and 2,000 (plus -1 as the default); open 4,000 idle TCP connections from one client; read the node's live connection objects and process memory.
- **Logic:** (1) the number of connections that stay open equals `min(4000, limit)` (else the run is invalid); (2) read heap and resident memory at each limit; (3) a positive control uses a known byte cap on the same traffic: with active clients each holding a 1 MiB request, `native_transport_max_request_data_in_flight` lowered to 64 MiB must hold memory down; (4) the claim is confirmed only if memory is flat across the limits while the control moves it.
- **Refuted if:** memory after the burst follows `min(4000, limit)`.

**Procedure:**

1. **Unit tier** — instantiate `ConnectionLimitHandler` in an `EmbeddedChannel` pipeline with a stub downstream handler; open *k* channels from one remote address and read the `counter` (via reflection) and the number of closed channels at limits below, at and above *k*.
2. **Cluster tier** — one node, the limit set through JMX before the burst; a client opens 4,000 idle sockets from one address and holds them; read connection counts and memory; close and repeat per limit.
3. **Positive control** — at limit -1, 64 connections each send a 1 MiB request and hold it; run once with the default in-flight budget and once with 64 MiB.
4. **Compare** with the prediction.

**Prediction (what the rejection claims):** connections that stay open are `min(4000, limit)` at each limit, but resident memory and live channel objects differ by less than the noise band across the limits; the positive control lowers memory.

**Conclusions:**

| Result | Conclusion |
|---|---|
| Open connections follow the limit, memory is flat across limits, and the control lowers memory | **Confirmed** — the count limit does not cap memory. |
| Memory follows `min(4000, limit)` (a fixed per-connection slope) | **Refuted** — usage follows the constraint, through a per-connection base cost; the rejection is too narrow for idle connections. Record the slope in bytes per connection. |
| Open connections do not follow the limit | **Not confirmed** — the handler was not installed or counts differently; check §5 and rerun. |
| Memory is flat and the control does not move it | **Not confirmed** — the instrument cannot see a cap that binds. |
| Fewer connections open than the lowest limit | **Invalid run** — raise the client's socket count or `ulimit -n`. |

### 9b. Setup

| Field | Content |
|-------|---------|
| **Constraint knob** | JMX `StorageProxy` attribute `NativeTransportMaxConcurrentConnections` (live), yaml `native_transport_max_concurrent_connections` (restart). Leave the per-IP limit at -1. |
| **Confirm it took effect** | the JMX read-back, and the "Exceeded maximum native connection limit of …" lines in `system.log` once the burst passes the limit |
| **Capacity values** | 500, 1,000, 2,000 connections, and -1 (the default, off). |
| **Scope** | Global across all clients; the burst comes from one address. |
| **Level** | Unit and cluster. |

**Hold fixed:**

| Setting | Value | Why |
|---|---|---|
| `native_transport_max_concurrent_connections_per_ip` | -1 | otherwise the per-IP limit binds |
| `native_transport_idle_timeout` | 0 (off) | idle connections must not be closed |
| client file limit | `ulimit -n` ≥ 10,000 on client and node | the limit under test must be the binding one |
| heap | `-Xms2G -Xmx2G` | fixes sizing |

**Controls:** an idle node (baseline), and the default (-1) run with 4,000 connections.

**Reset between runs:** close all client sockets, wait for the node's counter to return to its baseline, force a GC, take a new baseline.

### 9c. Workload

```bash
# cluster tier: open N idle sockets and hold them
python3 harness/hold_connections.py --count 4000 --hold-s 60
```

### 9d. Observables

| Observable | How to read it | When to sample | Trap |
|---|---|---|---|
| **Open connections** — the check's operand | JMX `org.apache.cassandra.metrics:type=Client,name=connectedNativeClients`; `ss -tn state established '( sport = :9042 )' \| wc -l` | at 30 s of the hold | The JMX gauge counts connections that finished the handshake; idle raw sockets are visible only in `ss`. |
| **Disallow evidence** | the "Exceeded maximum native connection limit" lines in `system.log`; client sockets closed by the server | at the end of the burst | The log line is rate-limited (`NoSpamLogger`); count closed sockets on the client. |
| **Live channel objects** | `jcmd <pid> GC.class_histogram` rows for `NioSocketChannel` and the pipeline classes | at 30 s | Take the histogram after a forced GC. |
| **Real resource** | `RssAnon` of the process from `/proc/<pid>/status`, and heap used from `jcmd <pid> GC.heap_info` | at 30 s | Netty pools memory; compare the delta to the baseline. |

### 9e. Running the scenarios

1. **Control run** — idle node; record baselines. Then limit -1 and 4,000 connections; record memory.
2. **Scenario A — limit 2,000** — set the limit, burst 4,000 connections, hold, sample.
3. **Scenario B — limits 1,000 and 500** — repeat.
4. **Scenario C — positive control** — the byte-budget arm in 9a procedure step 3.

## 10. Provenance

| Field | Content |
|--------|---------|
| **Judgment** | `rejected` — Rule 2: counts of connections, not bytes (`rejected.md`, batch "the capacity-word pass") |
| **Autonomous reference** | none |
| **Stage-3 feed** | 3b (recorded in `rejected.md`) |
| **Filed by / Date** | guided agent session, 2026-10-19 |
| **Line numbers checked** | 2026-10-19 against `cassandra-5.0.9` |
| **Escape hatch / Target-3 note** | connections created while the limits are -1 are never counted and are not closed when a limit is switched on (§5) |
| **Stage-4 feedback** | none yet |
| **Notes** | Source reading predicts **Refuted** for idle connections: a per-connection base cost times a bounded count is a memory bound, an indirect one. The recorded reason ("per-connection memory is not fixed") is the open question the sweep answers by measuring the slope. Pilot of the rejected-entry write-up. |

---

## 11. Notes

- The earlier `rejected.md` entry cites `ConnectionLimitHandler.java:93,121`; the lines still match.
