# internode_application_receive_queue_capacity — message

> **Index:** [../_INDEX.md](../_INDEX.md)
>
> **Source:** apache/cassandra @ tag `cassandra-5.0.9`

## 1. Location

| Field | Content |
|-------|---------|
| **Case ID** | INTERNODE_APPLICATION_RECEIVE_QUEUE_CAPACITY-MESSAGE |
| **If-statement** | [`AbstractMessageHandler.acquireCapacity():419`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/net/AbstractMessageHandler.java#L419) |

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
checks are noted in §5 but not traced as their own case here — they share
the same object-creation path and could be filed as a sibling case if the
per-connection vs. reserve distinction is later judged worth separating
(same pattern as the memtable heap/offheap sibling pair).

## 2. Module

| Field | Content |
|-------|---------|
| **Module** | Internode messaging (`net/`) — inbound connection handling |
| **One-line role** | Netty pipeline handler that decodes and deserializes messages arriving from a peer node, applying flow control so a fast/misbehaving sender can't unboundedly grow in-memory buffered message state on the receiver. |

## 3. Capacity-overflow check

| Field | Content |
|-------|---------|
| **Is this a capacity/overflow check?** | Yes — a running-total counter (`queueSize`) plus a requested increment (`bytes`, the incoming message's size) compared against a fixed per-connection ceiling (`queueCapacity`). |
| **Usage-side operand** | `queueSize` — `volatile long` on `AbstractMessageHandler`, bytes of not-yet-fully-processed inbound messages currently attributed to this connection. |
| **Limit-side operand** | `queueCapacity` — `protected final long` on `AbstractMessageHandler`, set once at construction. |
| **Limit type** | Configuration (`internode_application_receive_queue_capacity`), fixed default. |

**Limit initialization path** (declare → configure/derive → store → read at the check):

1. [`Config.java:256-257`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/Config.java#L256-L257) — declared: `internode_application_receive_queue_capacity` (`DataStorageSpec.IntBytesBound`, default `"4MiB"`).
2. [`DatabaseDescriptor.java:3040-3042`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/DatabaseDescriptor.java#L3040-L3042) — read/converted: `getInternodeApplicationReceiveQueueCapacityInBytes()` returns `conf.internode_application_receive_queue_capacity.toBytes()`.
3. [`MessagingService.java:678`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/net/MessagingService.java#L678) — configured/derived: `getInbound()` passes this value into a new per-peer `InboundMessageHandlers(..., DatabaseDescriptor.getInternodeApplicationReceiveQueueCapacityInBytes(), ...)`.
4. [`InboundMessageHandlers.java:97,118,147`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/net/InboundMessageHandlers.java#L97) — stored: constructor param `queueCapacity` is kept on `InboundMessageHandlers` and threaded into each per-connection `InboundMessageHandler::new` at line 147.
5. [`InboundMessageHandler.java:92,105`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/net/InboundMessageHandler.java#L92) → [`AbstractMessageHandler.java:172,185`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/net/AbstractMessageHandler.java#L172-L185) — stored: `InboundMessageHandler`'s constructor forwards `queueCapacity` to `super(...)`, which assigns `this.queueCapacity = queueCapacity` (`AbstractMessageHandler.java:185`) — a `final` field on the per-connection handler, this is what the check at line 419 reads.

## 4. Branch semantics

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

## 5. Code path: allow-branch → object creation

1. [`AbstractMessageHandler.java:419-423`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/net/AbstractMessageHandler.java#L419-L423) — allow branch taken, `queueSize` bumped, returns `Outcome.SUCCESS`.
2. [`AbstractMessageHandler.java:398`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/net/AbstractMessageHandler.java#L398) — outer `acquireCapacity(endpointReserve, globalReserve, bytes, currentTimeNanos, expiresAtNanos)` sees `outcome == SUCCESS`, returns `true` to its caller.
3. [`InboundMessageHandler.java:139-151`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/net/InboundMessageHandler.java#L139-L151) — `processOneContainedMessage()`: `if (!acquireCapacity(...)) return false;` is skipped (capacity was granted), so execution proceeds to `processSmallMessage(bytes, size, header)` (or `processLargeMessage` for messages over `largeThreshold`).
4. [`InboundMessageHandler.java:163`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/net/InboundMessageHandler.java#L163) — **object creation**: `Message<?> m = serializer.deserialize(in, header, version);` — the inbound bytes are deserialized into a live `Message` object (header + payload, e.g. a mutation, read command, or response).

**Disallow-branch effect (not a rejection):** per
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

## 6. Object & resource

| Field | Content |
|-------|---------|
| **Object created** | `org.apache.cassandra.net.Message<?>` — the deserialized inbound message (header + typed payload, e.g. a `Mutation`, read command, or RPC response). |
| **Resource consumed** | JVM heap bytes — the accounting unit is `size`/`bytes` (`serializer.inferMessageSize(...)`), the on-wire serialized message size; the deserialized object's actual heap footprint is proportional to but not byte-identical to this accounted size. |
| **Rough sizing** | Bounded per-connection to `queueCapacity` (default 4MiB via `internode_application_receive_queue_capacity`), plus whatever the connection can additionally borrow from the shared endpoint/global reserves (§1 note) before backpressure applies. |
| **Lifetime / release** | Released via `releaseCapacity(size)` (referenced at `InboundMessageHandler.java:184`, called when deserialization fails, and — per class-level docs at `InboundMessageHandler.java:66`, "Permits are released after the verb handler has been invoked" — once the dispatched verb handler finishes processing the message), which frees `queueSize` and signals waiting handlers via the wait queues. |

## 7. Maximum memory bound

| Field | Content |
|-------|---------|
| **Multiplicity** | **Not a global cap.** `queueCapacity` is a `final long` copied onto *every* `AbstractMessageHandler` instance. `InboundMessageHandlers.createHandler()` ([InboundMessageHandlers.java:130-149](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/net/InboundMessageHandlers.java#L130-L149)) creates one handler per `ConnectionType` (urgent/small/large/legacy) per peer, and `InboundMessageHandlers` itself is one instance per peer (`MessagingService.getInbound()`, [MessagingService.java:669-682](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/net/MessagingService.java#L669-L682)). So the exclusive allowance this if-check enforces multiplies by up to 4 connection types × however many peers this node communicates with — it is **not bounded by this if-check** and grows with cluster size. |
| **Shared/tiered limits** | This if-check (line 419) is only the innermost of three tiers, all read at the same `acquireCapacity()` call: (1) **per-connection exclusive** — `queueCapacity`, this case, `internode_application_receive_queue_capacity` (default 4MiB), one allowance per `AbstractMessageHandler`; (2) **per-endpoint shared reserve** — `endpointReserveCapacity`, backed by `internode_application_receive_queue_reserve_endpoint_capacity` (default 128MiB), one `ResourceLimits.Concurrent` instance shared by *all* connection-type handlers for a single peer (constructed once in `InboundMessageHandlers`'s constructor, [InboundMessageHandlers.java:118](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/net/InboundMessageHandlers.java#L118)), borrowed from at lines 428-436 of the if-check's method; (3) **global shared reserve** — `globalReserveCapacity`, backed by `internode_application_receive_queue_reserve_global_capacity` (default 512MiB), a *single* `ResourceLimits.Concurrent` for the entire node, constructed once in `MessagingService` ([MessagingService.java:309-310](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/net/MessagingService.java#L309-L310)) and shared across every peer. Only tier (3) doesn't grow with peer count. |
| **Worst-case bound** | `max bytes ≈ (peers × connection_types_per_peer × queueCapacity) + endpointReserveCapacity_per_active_peer + globalReserveCapacity`, where the middle term itself can be up to `peers × endpointReserveCapacity` in the worst case (each peer has its own endpoint reserve instance), bounded overall by however much of `globalReserveCapacity` the union of all peers' borrowing can draw from at once (borrowed reserve capacity is a single shared pool, so peers contend for it rather than each getting a full independent 512MiB). |

**Worst case vs. typical case:** the config name `internode_application_receive_queue_capacity` (4MiB default) reads like a flat per-node receive-buffer cap. It is not — it is a **per-connection-type-per-peer** allowance. A node talking to 50 peers has up to `50 × 4 × 4MiB = 800MiB` of *exclusive* allowance alone before any peer even touches the shared reserves, on top of which each peer can additionally borrow from the 128MiB endpoint reserve and the node-wide 512MiB global reserve. The true worst-case total scales with cluster topology (peer count), not with this one config value in isolation.

## Verification

See [README.md § Verifying a case](../README.md#verifying-a-case-triggering-the-disallow-branch)
before setting `Status: verified` — line-number checking alone is not enough;
a designed experiment must have actually driven execution into the disallow
branch with recorded evidence.

| Field | Content |
|--------|---------|
| **Status** | pending |
| **Verified By / Date** | — |
| **Trigger method** | Not yet designed. Candidate approach: unit/programmatic level — construct an `InboundMessageHandler` directly (check `test/unit/org/apache/cassandra/net/` for existing inbound-handler test scaffolding, e.g. `InboundMessageHandlerTests` / `PipelineIntegrationTest`-style harnesses, before writing a new one) with a small `queueCapacity` and both reserve `Limit`s set to 0 (or already exhausted), then feed it a message frame sized to deterministically exceed `queueCapacity` in a single shot — per the README's "prefer a deterministic single-shot trigger" guidance. Evidence to capture: the handler's `throttledCount` incrementing (`AbstractMessageHandler.java:406`) and/or a `Ticket` appearing on `endpointWaitQueue`/`globalWaitQueue`, rather than just an absence of dispatch. |
| **Evidence** | — |
| **Notes** | Line numbers checked against the local pinned-tag clone (`/cassandra-cassandra-5.0.9/cassandra-cassandra-5.0.9`, confirmed `5.0.9` via `build.xml`/`CHANGES.txt`) on 2026-09-17. Behavioral trigger not yet run. |

---

## Notes

- **Sibling candidate not filed separately:** the CQL/native-transport side of
  this same `AbstractMessageHandler.acquireCapacity()` check is reached via
  `PipelineConfigurator.java:306`, `queueCapacity =
  DatabaseDescriptor.getNativeTransportReceiveQueueCapacityInBytes()`
  (config `native_transport_receive_queue_capacity`, default 1MiB) — same
  if-check, same class, different config and different peer path (CQL client
  connections vs. internode). Could be filed as a sibling case
  (`native_transport_receive_queue_capacity-message.md`) following the same
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
