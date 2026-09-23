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

## 9. Provenance

| Field | Content |
|--------|---------|
| **Stage-3 feed** | `3b` — established by deep-reading the source; no stage-1/2 row led here. |
| **Line numbers checked** | 2026-09-22 against the local `cassandra-5.0.9` clone (`git describe --tags`). |
| **Escape hatch / Target-3 note** | none found yet. |

---

## 10. Notes

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
