# internode_application_receive_queue_capacity — message

> **Index:** [../_INDEX.md](../_INDEX.md)
>
> **Source:** apache/cassandra @ tag `cassandra-5.0.9`

## 1. Location

| Field | Content |
|-------|---------|
| **Case ID** | INTERNODE_APPLICATION_RECEIVE_QUEUE_CAPACITY-ACQUIRECAPACITY-QUEUECAPACITY |
| **Constraint** | `internode_application_receive_queue_capacity` — configuration entry (`Config.java`) |
| **Enforcement pattern** | (b) — the capacity check returns a `ResourceLimits.Outcome` verdict to its caller |
| **Capacity check** | [`AbstractMessageHandler.acquireCapacity():419`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/net/AbstractMessageHandler.java#L419) |
| **Decision point** | [`InboundMessageHandler.processOneContainedMessage():139-151`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/net/InboundMessageHandler.java#L139-L151) (returns without deserializing on a non-`SUCCESS` outcome) plus the wait-queue registration at [`AbstractMessageHandler.java:401-403`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/net/AbstractMessageHandler.java#L401-L403) |
| **Allocation site** | [`InboundMessageHandler.java:163`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/net/InboundMessageHandler.java#L163) — `serializer.deserialize(...)` creates the `Message` |
| **Related cases** | [`native_transport_receive_queue_capacity-acquireCapacity-queueCapacity`](native_transport_receive_queue_capacity-acquireCapacity-queueCapacity.md) (same `acquireCapacity()` check, CQL side) |

```java
protected ResourceLimits.Outcome acquireCapacity(Limit endpointReserve, Limit globalReserve, int bytes)
{
    long currentQueueSize = queueSize;

    /*
     * acquireCapacity() is only ever called on the event loop, and as such queueSize is only ever increased
     * on the event loop. If there is enough capacity, we can safely addAndGet() and immediately return.
     */
    if (currentQueueSize + bytes <= queueCapacity)
    {
        queueSizeUpdater.addAndGet(this, bytes);
        return ResourceLimits.Outcome.SUCCESS;
    }

    // we know we don't have enough local queue capacity for the entire message, so we need to borrow some from reserve capacity
    long allocatedExcess = min(currentQueueSize + bytes - queueCapacity, bytes);

    if (!globalReserve.tryAllocate(allocatedExcess))
        return ResourceLimits.Outcome.INSUFFICIENT_GLOBAL;

    if (!endpointReserve.tryAllocate(allocatedExcess))
    {
        globalReserve.release(allocatedExcess);
        globalWaitQueue.signal();
        return ResourceLimits.Outcome.INSUFFICIENT_ENDPOINT;
    }
    // ... (on success, addAndGet(bytes) and return SUCCESS — see full body)
}
```

**Note on scope of this case:** `acquireCapacity()` actually contains *two*
divergence points against two different limit-side operands: (1) the
per-connection `queueCapacity` check at line 419 (this case), and (2) the
per-endpoint/global `Limit.tryAllocate()` reserve checks at lines 428/431
(a distinct, further capacity source, backed by
`internode_application_receive_queue_reserve_endpoint_capacity` /
`internode_application_receive_queue_reserve_global_capacity`). This case
covers only (1), the exclusive per-connection queue; the reserve-capacity
checks are noted in 6b but not traced as their own case here — they share
the same object-creation path and could be filed as a sibling case if the
per-connection vs. reserve distinction is later judged worth separating
(same pattern as the memtable heap/offheap sibling pair).

## 2. Context

Cassandra nodes constantly exchange messages with peers over persistent
internode connections — replicated writes, read requests, gossip, repair
traffic, and more. Each inbound connection decodes messages off the wire
and deserializes them into in-memory objects before handing them to a
worker thread for processing; if a peer sends messages faster than this
node can drain its processing queue, that steady stream of deserialized
objects would otherwise accumulate in memory without bound. This if-check
is the flow-control gate on that inbound path: before deserializing an
arriving message, the connection checks whether adding its byte size to
what it's already holding would exceed a per-connection allowance — if so,
the connection stops decoding and applies backpressure to the sender
instead of buffering unboundedly.

## 3. Module

| Field | Content |
|-------|---------|
| **Module** | Internode messaging (`net/`) — inbound connection handling |
| **One-line role** | Netty pipeline handler that decodes and deserializes messages arriving from a peer node, applying flow control so a fast/misbehaving sender can't unboundedly grow in-memory buffered message state on the receiver. |

## 4. Capacity check & limit

| Field | Content |
|-------|---------|
| **Is this a capacity check?** | Yes — a running-total counter (`queueSize`) plus a requested increment (`bytes`, the incoming message's size) compared against a fixed per-connection ceiling (`queueCapacity`). |
| **Usage-side operand** | `queueSize` — `volatile long` on `AbstractMessageHandler`, bytes of not-yet-fully-processed inbound messages currently attributed to this connection. |
| **Limit-side operand** | `queueCapacity` — `protected final long` on `AbstractMessageHandler`, set once at construction. |
| **Limit type** | Configuration (`internode_application_receive_queue_capacity`), fixed default. |

**Limit initialization path** (declare → configure/derive → store → read at the check):

1. [`Config.java:256-257`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/Config.java#L256-L257) — declared: `internode_application_receive_queue_capacity` (`DataStorageSpec.IntBytesBound`, default `"4MiB"`).
2. [`DatabaseDescriptor.java:3040-3042`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/DatabaseDescriptor.java#L3040-L3042) — read/converted: `getInternodeApplicationReceiveQueueCapacityInBytes()` returns `conf.internode_application_receive_queue_capacity.toBytes()`.
3. [`MessagingService.java:678`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/net/MessagingService.java#L678) — configured/derived: `getInbound()` passes this value into a new per-peer `InboundMessageHandlers(..., DatabaseDescriptor.getInternodeApplicationReceiveQueueCapacityInBytes(), ...)`.
4. [`InboundMessageHandlers.java:97,118,147`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/net/InboundMessageHandlers.java#L97) — stored: constructor param `queueCapacity` is kept on `InboundMessageHandlers` and threaded into each per-connection `InboundMessageHandler::new` at line 147.
5. [`InboundMessageHandler.java:92,105`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/net/InboundMessageHandler.java#L92) → [`AbstractMessageHandler.java:172,185`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/net/AbstractMessageHandler.java#L172-L185) — stored: `InboundMessageHandler`'s constructor forwards `queueCapacity` to `super(...)`, which assigns `this.queueCapacity = queueCapacity` (`AbstractMessageHandler.java:185`) — a `final` field on the per-connection handler, this is what the check at line 419 reads.

## 5. Decision point & branch semantics

| Field | Content |
|-------|---------|
| **Decision point** | [`InboundMessageHandler.processOneContainedMessage():139-151`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/net/InboundMessageHandler.java#L139-L151) (returns without deserializing on a non-`SUCCESS` outcome) plus the wait-queue registration at [`AbstractMessageHandler.java:401-403`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/net/AbstractMessageHandler.java#L401-L403) |
| **Verdict** | `ResourceLimits.Outcome` returned by `AbstractMessageHandler.acquireCapacity()` (`:419`), read at the decision point above. |

| Branch | Condition | Effect |
|--------|-----------|--------|
| **Allow** | `currentQueueSize + bytes <= queueCapacity` | `queueSize` is bumped by `bytes` via `addAndGet`; returns `SUCCESS` — caller proceeds to deserialize the message into an object. |
| **Disallow** | `currentQueueSize + bytes > queueCapacity` | Falls through to try borrowing from the endpoint/global reserves (§1 note); if those are also insufficient, returns `INSUFFICIENT_GLOBAL`/`INSUFFICIENT_ENDPOINT` — caller does **not** deserialize, and instead registers to retry later. |

```java
// allow branch (AbstractMessageHandler.java:419-423)
if (currentQueueSize + bytes <= queueCapacity)
{
    queueSizeUpdater.addAndGet(this, bytes);
    return ResourceLimits.Outcome.SUCCESS;
}
```

```java
// disallow branch's ultimate failure outcome, after reserves are also exhausted
// (AbstractMessageHandler.java:428-436)
if (!globalReserve.tryAllocate(allocatedExcess))
    return ResourceLimits.Outcome.INSUFFICIENT_GLOBAL;
if (!endpointReserve.tryAllocate(allocatedExcess))
{
    globalReserve.release(allocatedExcess);
    globalWaitQueue.signal();
    return ResourceLimits.Outcome.INSUFFICIENT_ENDPOINT;
}
```

## 6. Code path

### 6a. Allow branch → object creation

1. [`AbstractMessageHandler.java:419-423`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/net/AbstractMessageHandler.java#L419-L423) — allow branch taken, `queueSize` bumped, returns `Outcome.SUCCESS`.
2. [`AbstractMessageHandler.java:398`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/net/AbstractMessageHandler.java#L398) — outer `acquireCapacity(endpointReserve, globalReserve, bytes, currentTimeNanos, expiresAtNanos)` sees `outcome == SUCCESS`, returns `true` to its caller.
3. [`InboundMessageHandler.java:139-151`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/net/InboundMessageHandler.java#L139-L151) — `processOneContainedMessage()`: `if (!acquireCapacity(...)) return false;` is skipped (capacity was granted), so execution proceeds to `processSmallMessage(bytes, size, header)` (or `processLargeMessage` for messages over `largeThreshold`).
4. [`InboundMessageHandler.java:163`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/net/InboundMessageHandler.java#L163) — **object creation**: `Message<?> m = serializer.deserialize(in, header, version);` — the inbound bytes are deserialized into a live `Message` object (header + payload, e.g. a mutation, read command, or response).

### 6b. Disallow branch effect

**Not a rejection.** Per
[`InboundMessageHandler.java:139-140`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/net/InboundMessageHandler.java#L139-L140),
a `false` return from `acquireCapacity()` makes `processOneContainedMessage()`
return `false` without deserializing. This propagates up through
`processFrameOfContainedMessages()` (`AbstractMessageHandler.java:239-241`)
and `UpToOneMessageFrameProcessor.processFirstFrame()`
(`AbstractMessageHandler.java:365-367`, sets `isActive = false`), and — per
`AbstractMessageHandler.java:401-403` — a `Ticket` is registered on the
`endpointWaitQueue` or `globalWaitQueue` (`WaitQueue.register()`,
`AbstractMessageHandler.java:661-667`) to reactivate this handler and retry
once capacity frees up (via `Ticket`/`WaitQueue.signal()` machinery, not
shown in full here). The message bytes are **not dropped** — the connection
simply stops decoding further frames until it is reactivated, applying
backpressure to the sender's socket rather than rejecting the message
outright. No escape hatch analogous to the memtable cases' `markBlocking()`
was found in this class; flagged as an open question for Target 3, not
pursued further here.

## 7. Object & resource

| Field | Content |
|-------|---------|
| **Object created** | `org.apache.cassandra.net.Message<?>` — the deserialized inbound message (header + typed payload, e.g. a `Mutation`, read command, or RPC response). |
| **Resource consumed** | JVM heap bytes — the accounting unit is `size`/`bytes` (`serializer.inferMessageSize(...)`), the on-wire serialized message size; the deserialized object's actual heap footprint is proportional to but not byte-identical to this accounted size. |
| **Rough sizing** | Bounded per-connection to `queueCapacity` (default 4MiB via `internode_application_receive_queue_capacity`), plus whatever the connection can additionally borrow from the shared endpoint/global reserves (§1 note) before backpressure applies. |
| **Lifetime / release** | Released via `releaseCapacity(size)` (referenced at `InboundMessageHandler.java:184`, called when deserialization fails, and — per class-level docs at `InboundMessageHandler.java:66`, "Permits are released after the verb handler has been invoked" — once the dispatched verb handler finishes processing the message), which frees `queueSize` and signals waiting handlers via the wait queues. |

## 8. Maximum memory bound

Raising `internode_application_receive_queue_capacity` raises how many bytes
of not-yet-processed inbound messages **one connection** may hold — and
deserialize into live `Message` objects — before it must fall back to
borrowing from shared reserves or applying backpressure; lowering it makes
that connection throttle sooner. But `queueCapacity` is a `final long`
copied onto *every* `AbstractMessageHandler` instance, and
`InboundMessageHandlers.createHandler()`
([InboundMessageHandlers.java:130-149](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/net/InboundMessageHandlers.java#L130-L149))
creates one handler per `ConnectionType` (urgent/small/large/legacy) per
peer, with `InboundMessageHandlers` itself one instance per peer
(`MessagingService.getInbound()`,
[MessagingService.java:669-682](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/net/MessagingService.java#L669-L682)).
So this if-check's enforcement multiplies by up to 4 connection types ×
however many peers this node talks to — raising the config value scales the
node's true worst-case receive-side memory by that same factor, not by a
flat per-node amount. On top of this per-connection tier, 6b's disallow
path lets a connection borrow from a per-endpoint reserve
(`internode_application_receive_queue_reserve_endpoint_capacity`, default
128MiB, shared by all connection-type handlers to one peer) and then a
single node-wide global reserve
(`internode_application_receive_queue_reserve_global_capacity`, default
512MiB, shared across every peer) — so the node's actual worst-case receive
memory is `(peers × connection_types × queueCapacity) + endpointReserve_per_active_peer + globalReserve`,
not simply "`internode_application_receive_queue_capacity` MiB." A node
talking to 50 peers already has `50 × 4 × 4MiB = 800MiB` of exclusive
per-connection allowance alone, before any peer touches the shared
reserves — the config name reads like a flat per-node cap but is actually a
per-connection-type-per-peer one.


## 9. Test design (guidance for stage 4)

**Stage 3 writes this section; stage 3 never runs it.** Method and pitfalls:
[README.md §8](../../../README.md#8-designing-a-test-for-a-case). Where stage 4's
numbers go: [`../../../stage4-runtime-verification/README.md`](../../../stage4-runtime-verification/README.md).

**Read §8 before designing anything here.** This check is **per connection
type, per peer**, and the node's receive-side ceiling is
`(peers × connection_types × queueCapacity) + endpoint reserves + global
reserve`. An experiment that changes `internode_application_receive_queue_capacity`
and measures node heap on a two-node cluster is measuring the smallest term in
that sum. **The multiplier is the experiment**, not a nuisance parameter.

**This case also has the best direct-evidence instrument in the folder**, which
shapes the whole design — see `ThrottledCount` below.

| Field | Content |
|-------|---------|
| **Testability** | **Config-testable, restart-only.** `queueCapacity` is a `final long` copied onto each handler at construction ([`AbstractMessageHandler.java:185`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/net/AbstractMessageHandler.java#L185)); `Config.internode_application_receive_queue_capacity` is not `volatile` and has no setter. Each value costs a restart of the **receiving** node. Checked 2026-09-28. |
| **Constraint knob** | `internode_application_receive_queue_capacity` in `cassandra.yaml` (default `4MiB`, [`Config.java:256-257`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/Config.java#L256-L257)). **The two reserves must be pinned alongside it**, or the disallow path borrows and nothing throttles: `internode_application_receive_queue_reserve_endpoint_capacity` (default `128MiB`, [`:258-259`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/Config.java#L258-L259)) and `internode_application_receive_queue_reserve_global_capacity` (default `512MiB`, [`:260-261`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/Config.java#L260-L261)). Set both to a small value in the arms that test this check in isolation. |
| **Capacity values to test** | `internode_application_receive_queue_capacity` ∈ {`512KiB`, `1MiB`, **`4MiB`** (default), `16MiB`}, with both reserves pinned small (say `1MiB` each) so the per-connection tier binds. **Then a second sweep with the reserves at their defaults**, which is the realistic configuration and shows how much the per-connection number actually governs — the two sweeps answer different questions and both are needed. |
| **Usage-side observable** | `queueSize` — the `volatile long` per handler, bytes of inbound messages accounted to this connection and not yet released. |
| **Instrument** | **Unusually good: the per-connection state is exposed.** `InternodeInboundMetrics` registers gauges under `InboundConnection.<peer>` ([`InternodeInboundMetrics.java:55-68`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/metrics/InternodeInboundMetrics.java#L55-L68)), **per peer**, including `ScheduledBytes`/`ScheduledCount` (pending, i.e. accounted and unprocessed — the closest published proxy for `queueSize`), `ReceivedBytes`, `ProcessedBytes`, and — the important ones — **`ThrottledCount` and `ThrottledNanos`**. Those two move *only* when a handler is throttled by this check, so they are direct evidence the disallow branch fired, not a symptom with other causes. This is exactly what README §8.2 rule 5 asks for and no other case in this folder has it. Cross-check heap with `jcmd <pid> GC.heap_info` after a forced full GC. |
| **Scope of the limit** | **Per connection type, per peer** — the finest-grained scope of any case here. `InboundMessageHandlers.createHandler()` ([`:130-149`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/net/InboundMessageHandlers.java#L130-L149)) makes one handler per `ConnectionType` (urgent/small/large/legacy), and `MessagingService.getInbound()` ([`:669-682`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/net/MessagingService.java#L669-L682)) makes one `InboundMessageHandlers` per peer. So `N = peers × connection_types` (up to 4). **Vary `N` deliberately** by running the sweep at 2, 3 and 5 nodes: §8's claim is that the node-wide allowance scales with peer count, and only changing the peer count tests it. Note the four connection types are not all active for every workload — large messages go to the `large` connection, small to `small` — so the effective `N` per peer is workload-dependent and should be read off `ScheduledBytes` per connection rather than assumed to be 4. |
| **Suggested level** | **Both.** Unit: there is no existing test for `acquireCapacity` itself, but `test/unit/org/apache/cassandra/net/ResourceLimitsTest.java` covers the reserve mechanism (`ResourceLimits.Basic`/`Concurrent`) that the disallow path falls back on, and `ConnectionTest.java` / `FramingTest.java` build real handler plumbing worth reusing. The designed unit trigger: construct an `InboundMessageHandler` with a tiny `queueCapacity` and reserves already exhausted, feed one oversized frame, and assert the outcome is `INSUFFICIENT_GLOBAL`/`INSUFFICIENT_ENDPOINT` and that no `Message` was deserialized. Cluster: required for the multiplier, which is the part §8 actually claims. |

### 9a. Workload — driving the usage operand

The operand is bytes of inbound internode messages not yet processed, so the
workload must make one node receive faster than it can process.

- Cluster of 2, then 3, then 5 nodes; `RF` equal to the node count so every write fans out to every peer; one table.
- Write from a coordinator with `cassandra-stress` at high concurrency (`-rate threads=`), `CONSISTENCY ALL` so the coordinator waits and backpressure is visible, with a **payload sized to make a single message a meaningful fraction of `queueCapacity`** — a few hundred KiB against a 512KiB capacity, so a handful of in-flight messages fill it.
- The receiving side is the node under test; **its** config carries the swept value. The senders' config is irrelevant to this check.
- To make processing lag receiving (which is what fills the queue), constrain the receiver: fewer CPUs, or a workload whose verb handlers are slow (large batches, wide partitions). Without a processing bottleneck the queue drains as fast as it fills and the check never binds.

**Deterministic single-shot form:** set `queueCapacity` *below the size of one
message* and both reserves below it too. The very first message then cannot be
admitted on any tier, so the boundary is hit on message one with no throughput
race — far preferable to tuning a sustained load until something throttles
(README §8.2 rule 2). Use this at the unit tier and as the cluster smoke test.

### 9b. Scenario A — just reach capacity

Hold offered load so `ScheduledBytes` for the connection under test sits just
below `queueCapacity`.

Expect: `ScheduledBytes` plateaus near the configured value and the plateau
moves with the knob across the four values; `ThrottledCount` stays at zero;
messages deserialize and throughput is steady. The zero on `ThrottledCount` is
what makes this a control rather than a measurement.

### 9c. Scenario B — try to exceed capacity

Push past it. **The disallow branch does not drop the message** (§6b) — it
declines to deserialize now and registers to retry:

| Expected | Evidence to capture |
|---|---|
| `ThrottledCount` **rises**, `ThrottledNanos` accumulates | The direct evidence. Only this check moves these gauges. |
| The message is **not deserialized**, and **not dropped** | `ReceivedBytes` continues to climb while `ProcessedBytes` lags; the handler registers on the wait queue at [`AbstractMessageHandler.java:401-403`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/net/AbstractMessageHandler.java#L401-L403) and retries later. Nothing should appear in dropped-message counters attributable to this path. |
| Reserves are consumed **before** throttling | With reserves at their defaults, expect the connection to borrow up to 128MiB endpoint / 512MiB global before `ThrottledCount` moves at all. This is why the two-sweep design exists: at default reserves the per-connection number barely governs anything. |
| Sender-side backpressure follows | TCP backpressure propagates; coordinator write latency rises. A *symptom*, not evidence — do not use it as the measurement. |

### 9d. Expected dose-response

If the traced path is the binding limit:

- **With reserves pinned small:** per-connection `ScheduledBytes` plateaus at ≈ `queueCapacity`, linear in the knob across 512KiB → 16MiB. Time-to-first-throttle falls as the knob falls.
- **With reserves at defaults:** the plateau is dominated by the reserves, and the per-connection knob moves the total only weakly. **Predict this explicitly** — it is the realistic configuration, and a stage-4 run that only tests the default reserves will see a weak response and may wrongly call the case refuted.
- **Across peer counts (2 → 3 → 5 nodes):** total receive-side accounted bytes at saturation should scale roughly with the number of active peer-connections, per §8. This is the claim most worth testing, because the config name reads like a node-wide cap and is not one. Compute `Σ ScheduledBytes` over all `InboundConnection.<peer>` gauges and check it against `peers × active_connection_types × queueCapacity`.
- **Heap** should follow accounted bytes only loosely: §7 notes the accounting unit is the on-wire serialized size, while the resource is the deserialized object's heap footprint. Expect a consistent ratio, not equality, and report the ratio.

### 9e. Interpretation — what each outcome means

| Observation at scenario B | Reading |
|---|---|
| `ThrottledCount` rises at the predicted point; `ScheduledBytes` plateaus at the knob; the sum over peers scales with peer count | The check enforces as traced, and §8's multiplier claim holds. |
| `ThrottledCount` stays at zero while load clearly exceeds `queueCapacity` | The reserves are absorbing it. Expected at default reserves — re-run the arm with reserves pinned small before drawing any conclusion. |
| `ScheduledBytes` climbs far past `queueCapacity` with reserves pinned small | Something admits messages without passing this check. No escape hatch is recorded for this case (§10 says "none found yet"), so this would be a **new finding** and is Target-3 material. |
| No response to the knob at any value, with `ThrottledCount` moving | The check fires but does not govern the accounted total — re-read §5's reserve fallback; likely the reserves were not actually pinned. |
| Nothing responds and `ThrottledCount` never moves | The workload never saturated the receiver. Add a processing bottleneck (§9a) before concluding anything. |

### 9f. What would refute this case

The case claims the comparison at `acquireCapacity():419` gates deserialization
of inbound internode messages, so bytes of unprocessed inbound messages per
connection are bounded by `internode_application_receive_queue_capacity` (plus
the reserves the disallow path may borrow). It is refuted if, **with both
reserves pinned below one message size**, per-connection `ScheduledBytes` does
not plateau near `queueCapacity` and does not move with it across the sweep,
while `ThrottledCount` confirms the check is being evaluated.

A secondary, sharper refutation targets §8 specifically: if total receive-side
accounted bytes at saturation does **not** scale with peer count, then the
per-connection multiplier §8 describes is wrong, and §8's worst-case formula
needs rewriting even if the per-connection claim survives.

### 9g. Confounders and controls

- **The reserves are the dominant confounder** and the reason a naive sweep will show almost nothing. Run every capacity value twice: once with reserves pinned small, once at defaults. Record both.
- **Peer count and connection types** change the multiplier. Fix the cluster size within a sweep, and vary it deliberately as its own arm. Read the active connection types off the per-peer gauges rather than assuming all four are in use.
- **Processing speed on the receiver** determines whether the queue fills at all. Hold the receiver's hardware, `concurrent_writes` and workload shape fixed across the sweep — changing any of them moves the same observable.
- **This is one of several inbound limits.** `internode_max_message_size` and the per-message sanity checks reject oversized frames on a different path; confirm messages are not being rejected before they reach `acquireCapacity`.
- **Accounted bytes ≠ heap bytes** (§7). Do not treat `ScheduledBytes` as a heap measurement; take heap separately after a forced full GC and report the ratio.
- **The sibling case shares this exact code.** `native_transport_receive_queue_capacity` runs the same `AbstractMessageHandler.acquireCapacity()` on CQL client connections. Client traffic must be quiet during an internode run, or both cases' handlers are moving at once.
- **Baseline** at default config under light load; **idle control** with the cluster up and no writes, for the gauge floor.

## 10. Provenance

| Field | Content |
|--------|---------|
| **Stage-3 feed** | `3b` — established by deep-reading the source; no stage-1/2 row led here. |
| **Line numbers checked** | 2026-09-22 against the local `cassandra-5.0.9` clone (`git describe --tags`). |
| **Escape hatch / Target-3 note** | none found yet. |
| **Stage-4 feedback** | none yet |

---

## 11. Notes

- **Sibling candidate not filed separately:** the CQL/native-transport side of
  this same `AbstractMessageHandler.acquireCapacity()` check is reached via
  `PipelineConfigurator.java:306`, `queueCapacity =
  DatabaseDescriptor.getNativeTransportReceiveQueueCapacityInBytes()`
  (config `native_transport_receive_queue_capacity`, default 1MiB) — same
  if-check, same class, different config and different peer path (CQL client
  connections vs. internode). Could be filed as a sibling case
  (`native_transport_receive_queue_capacity-acquireCapacity-queueCapacity.md`) following the same
  memtable heap/offheap precedent, if useful to distinguish later.
- **Reserve-capacity checks (lines 428/431) not separately cased:** see the
  §1 scoping note — `endpointReserve.tryAllocate()` /
  `globalReserve.tryAllocate()` are their own divergence points against
  `internode_application_receive_queue_reserve_endpoint_capacity` /
  `_reserve_global_capacity`, sharing this case's object-creation path.
- No escape-hatch/bypass analogous to the memtable cases' `OpOrder.Group.isBlocking()`
  was identified in this code path — worth a closer look under Target 3 to
  confirm one doesn't exist elsewhere in the reactivation logic, rather than
  assuming its absence.
