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
| **Related cases** | [`native_transport_receive_queue_capacity-acquireCapacity-queueCapacity`](native_transport_receive_queue_capacity-acquireCapacity-queueCapacity--guided.md) (same `acquireCapacity()` check, CQL side); [`internode_application_send_queue_capacity-acquireCapacity-pendingCapacityInBytes`](internode_application_send_queue_capacity-acquireCapacity-pendingCapacityInBytes--guided.md) (the send-side mirror, filed 2026-10-07: a per-link allowance on outbound messages with the same `ResourceLimits` reserve mechanism, whose disallow **drops** the message instead of waiting) |

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

**Stage 3 writes this section; stage 3 never runs it** — no measured numbers
and no verdict here; results go to
[`../../../stage4-runtime-verification/README.md`](../../stage4-runtime-verification/README.md).
The test sets `internode_application_receive_queue_capacity` on one receiving node,
makes its peers send large messages faster than it processes them, and checks that
the bytes it has accepted per peer stop near the capacity, that the check's
throttle counter moves, and that the node-wide total scales with the peer count.
**Run so far:** none. Converted to this layout 2026-10-06.

### 9a. Procedure and conclusions

**Testability:** config, **restart-only** — `queueCapacity` is a `final long` copied
onto each handler at construction
([`AbstractMessageHandler.java:185`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/net/AbstractMessageHandler.java#L185))
from a non-`volatile` `Config` field with no setter; each value costs a restart of
the **receiving** node only. Both reserves must be set low alongside it, or the
disallow path borrows and nothing throttles (§5).

**Claim under test:** `internode_application_receive_queue_capacity` bounds the
inbound message bytes one connection (one `ConnectionType` of one peer) may have
accepted and not yet processed; past it the handler borrows from the endpoint and
global reserves, and when those are exhausted it stops deserializing and waits,
without dropping the message. The node-wide receive allowance is therefore
`peers × active connection types × capacity` plus the reserves (§8).

**How this verifies the hypothesis** (a restatement of the claim, procedure,
prediction and conclusions in this section; it adds none):

- **Hypothesis:** with the reserves pinned low, the bytes accepted per peer plateau
  near `active types × capacity`, the throttle counter shows the disallow branch,
  and the total over peers scales with the number of peers.
- **Test:** vary the capacity (512 KiB, 1 MiB, 4 MiB the default, 16 MiB) with both
  reserves at 1 MiB; make 1, 2 and 4 peers write 256 KiB mutations to one receiver
  whose verb handler is held back; read per-peer `ScheduledBytes`, `ThrottledCount`
  and `ThrottledNanos`, the memory of the receiver, and the senders' success.
  Then repeat at the default capacity with the reserves at their defaults.
  *Amended 2026-10-14 (stage-4 audit; rec. numbers are those of the results file's §1):* the capacity sweep runs with
  *P* = 1; the ring is always `R` and four senders (RF 5) and *P* is the number of senders writing (rec. 5). *S* is
  read as the check's own operand: the `queueSize` of each handler from a trace at every `acquireCapacity` and
  `releaseCapacity`, and per peer `using_bytes` of `system_views.internode_inbound` (Σ `queueSize`), not
  `ScheduledBytes`, which counts a message only from its dispatch to the stage until it has run (rec. 1). The real
  resource is read where the accepted bytes really are (rec. 2): a 256 KiB message travels the **large** path and waits
  for its stage thread as raw frames from the off-heap networking buffer pool, deserialized only when a `MutationStage`
  thread runs it; so the heap holds at most the 32 running messages, and the rest sit in the pool. A **small-message
  arm** (32 KiB values, deserialized on the event loop before queueing, §6a) is added at 4 MiB to test §7's heap claim.
- **Logic:** (1) the receiver must be saturated, or the run is invalid. (2) Per peer,
  `ScheduledBytes` stops near the capacity and `ThrottledCount` rises: usage **stops
  at the limit**, by the disallow branch (these two gauges move only on it). (3) The
  plateau moves with the capacity: usage **follows the constraint**. (4) The sum over
  peers moves with the peer count: **§8's multiplier**. (5) Every write completes
  with no error, so the disallow is a wait, not a drop. (6) With default reserves
  the same load barely throttles: the contrast shows the reserves are what bind.
  *Amended 2026-10-14 (rec. 2):* (7) The held real resource (live deserialized `Mutation`s and the networking pool's
  bytes in use) follows the number of accepted messages and stays flat while *S* is capped.
- **Refuted if:** with the reserves low, per-peer `ScheduledBytes` does not follow
  the capacity or passes it by more than the borrowing explains; the total does not
  scale with peers; or messages are lost (rows of the Conclusions table).

**Procedure:**

1. **Unit tier** — run the harness test `AcquireCapacityTest` (9c): a handler
   built with a small capacity and `ResourceLimits` reserves, driven through the
   allow branch, the borrow, and both `INSUFFICIENT_*` outcomes, asserting the
   verdict, `queueSize`, the reserves' use, `throttledCount` and the registered
   wait-queue ticket. Run upstream `ResourceLimitsTest` as the reserve control.
2. **Cluster tier** — one receiver (`R`) and 1, 2 and 4 sender peers, all processes
   on one machine on loopback addresses (9b); restart `R` per capacity value.
3. **At each value:** idle control → **A**, offered load that stays below the
   capacity → **B**, offered load above it (a held verb handler). No scenario C: no
   bypass is recorded.
4. **Compare** with the prediction and read the result below.

*Amended 2026-10-14 (rec. 5, 6):* the senders stay up for the whole run; `R` restarts once per capacity value (one
lifetime each: `512KiB`; `1MiB` with the no-hold control after its B; `4MiB` with the peer arms *P* = 2, 4 and the
small-message arm after its B, which is *P* = 1; `16MiB`; the default-reserves arm). Unit step 5 is changed so the
release can reactivate the waiting handler (9e).

**Prediction.** Notation: *C* = the capacity; *M* = one message (about 256 KiB, a
mutation with one 256 KiB blob; above the ≈ 64 KiB large-message threshold, so it
travels on the `large` connection); *P* = peers; `S` = a peer's peak
`ScheduledBytes`.

- **A:** `S ≤ C` for every peer, `ThrottledCount = 0`, writes complete at the sender's
  pace. This is the control.
- **B, reserves low:** per peer, the `large` connection accepts `⌊C / M⌋` messages and
  borrows the rest from the reserves while they last; then `ThrottledCount` and
  `ThrottledNanos` rise and `S` stops: `S ≈ C + (that peer's share of the 1 MiB
  endpoint reserve)`, plus a little on the `small` connection (acknowledgements,
  gossip, below `C`). The sum over peers is at most `P × C + 1 MiB` (global reserve),
  so it is linear in *C* with slope *P*.
- **B, reserves at defaults (control):** the 128 MiB endpoint and 512 MiB global
  reserves absorb the load; `S` far above *C*, `ThrottledCount` near zero. The check
  governs the first *C* bytes only.
- **Every write succeeds** (CL ALL, `Total errors: 0`): throttling delays the
  receiver's reading, so senders slow down; no mutation is dropped.
- **Heap** of the receiver follows accepted bytes loosely (accounting is the
  serialized size; §7): report the ratio of the receiver's retained heap (after a
  forced full GC) to `Σ S`.
- *Amended 2026-10-14 (rec. 1–5): the prediction in numbers.* *M* is one message's accounted size (the trace's
  `bytes=`), above 262,144 B (the value alone); *E* and *G* are the endpoint and global reserve limits (1 MiB =
  1,048,576 B in the low arms); *q* is one handler's `queueSize`.
  - **The rule** (`AbstractMessageHandler.java:419-445`): an acquire succeeds iff `q + b ≤ C`, or its excess
    `min(q + b − C, b)` fits the remaining room of the global and then the endpoint reserve. So at every moment a
    handler's `q − C` is at most its peer's endpoint reserve in use (≤ *E*), and the sum of `(q − C)⁺` over all handlers is
    the global reserve in use (≤ *G*). Checked on every trace line: a `SUCCESS` leaves `q ≤ C + E`; a refusal has
    `q + b − C` above the room left in the reserve it names, and leaves *q* unchanged.
  - **B, reserves low, *P* = 1:** the `large` handler's peak `q = n·M` with `n = ⌊(C + 1 MiB) / M⌋` = **5 · 7 · 19 · 67**
    at 512 KiB · 1 MiB · 4 MiB · 16 MiB (about 1.31 · 1.84 · 4.98 · 17.57 MB); every refusal is `INSUFFICIENT_GLOBAL`
    (the global reserve is tried first and, with one peer borrowing, has the same use and limit as the endpoint reserve);
    `ThrottledCount` and `ThrottledNanos` rise; the `small` and `urgent` handlers stay below *C* and borrow nothing.
  - **Peer sweep at 4 MiB, *P* = 1, 2, 4:** each writing peer's `large` handler peaks at or above `⌊C/M⌋·M` (15 *M*, its
    own capacity, which needs no reserve) and at or below `C + 1 MiB`; the global reserve in use never exceeds *G* and
    peaks above `G − M`; the node total, Σ *q* over all handlers rebuilt from the trace at each line, never exceeds
    `P·C + G` plus 64 KiB (the idle handlers), and the sum over peers of each peer's peak is at least `P·⌊C/M⌋·M`. So the
    exclusive part grows by *C* per peer and the shared part stays *G*: §8's multiplier.
  - **Default reserves** (4 MiB, 128 MiB, 512 MiB, *P* = 1, 128 writes in flight): the writer's in-flight bound
    (128 *M* ≈ 33.6 MB, below `C + E`) binds first: `ThrottledCount` does not move, and the peak *q* is above
    `C + 1 MiB` and at most 128 *M*.
  - **Small-message arm** (4 MiB, reserves 1 MiB, *P* = 1, 32,768-byte values, 256 in flight): the `small` handler peaks
    at `n_s·M_s`, `n_s = ⌊5 MiB / M_s⌋` = 159 (`M_s` above 32,768 B); refusals `INSUFFICIENT_GLOBAL`.
  - **Real resource**, two live class histograms (each a full GC) a third and two thirds into B: live
    `org.apache.cassandra.db.Mutation` instances above the idle count are `min(n, 32)` within −3/+2 in the large arms
    (5 · 7 · 19 · 32: the queued rest are frames), and `n_s` within −4/+2 in the small arm (all deserialized); the two
    histograms of one arm agree within 3. The networking pool's `UsedSize` above idle, averaged over B, is
    `(n − 32)·M` ≈ 9.2 MB within a factor of 2 at 16 MiB and below 2 MiB at the three smaller values; its mean over the
    last third of B exceeds the first third's by less than *M*.
  - **Every write succeeds:** writer errors 0; `R`'s local write count for the table rises by exactly the rows written;
    `R`'s dropped `MUTATION` count and the peers' `expired_count` do not move.

**Conclusions:**

| Result | Conclusion |
|---|---|
| Reserves low: per-peer `S` plateaus near `C` plus the reserve share and moves with *C* across the four values; `ThrottledCount` rises; `Σ S` scales with *P*; no write errors | **Confirmed** — the check enforces as traced, and §8's multiplier holds. |
| As above, but `Σ S` does not scale with *P* | **Confirmed per connection; §8's multiplier refuted** — rewrite §8's worst-case formula (Target-3 material). |
| Reserves low: `S` passes `C` plus the reserves by more than borrowing explains, with the check being evaluated (`ThrottledCount` moving) | **Refuted** — something admits bytes without passing this check; no bypass is recorded, so it is a new finding. |
| Reserves low: `S` is flat across the values while `ThrottledCount` moves | **Refuted** — the check fires but does not govern the accounted bytes; check that the reserves really are pinned. |
| `S` follows *C* but `ThrottledCount` stays zero | **Not confirmed** — something other than this check is capping (the sender, the reserves); re-read. |
| The receiver's retained heap grows while `Σ S` is capped. *Amended 2026-10-14 (rec. 2):* read as: the held real resource (live `Mutation` instances, networking-pool bytes in use) grows over B while *S* is flat, or exceeds what *S* accounts for by more than the tolerances above | **Refuted** — the counter does not track the resource; §8's ceiling claim is wrong. |
| *Added 2026-10-14 (rec. 2):* the real resource is held as predicted, but the small arm's live `Mutation` count is not near `n_s` (the messages are not deserialized before queueing) or a large arm's exceeds `min(n, 32)` | **Confirmed for the counter; §6a/§7 refuted on where the bytes live** — amend §7 (Target-2 detail, not the ceiling). |
| Writes fail or time out in a way that loses data (errors at CL ALL not explained by the held handler) | **Not confirmed** — §6b's "not dropped" is not shown; read the sender errors and the dropped-message counters. |
| `ThrottledCount` stays zero and `S` never nears *C*, at every value | **Invalid run** — the receiver never saturated; raise the hold or the load (9c) and re-run. |

**Why `ThrottledCount` and not heap:** other code allocates on the heap too, so
heap can move for reasons unrelated to this check. Only the throttle counters, which
`acquireCapacity` alone increments
([`AbstractMessageHandler.java:405-406`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/net/AbstractMessageHandler.java#L405-L406)),
tie a reading to the disallow branch.

### 9b. Setup

| Field | Content |
|-------|---------|
| **Constraint knob** | `internode_application_receive_queue_capacity` in the **receiver's** `cassandra.yaml` (default `4MiB`, [`Config.java:256-257`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/Config.java#L256-L257)); restart-only. **Reserves, pinned in the low arms:** `internode_application_receive_queue_reserve_endpoint_capacity: 1MiB` and `internode_application_receive_queue_reserve_global_capacity: 1MiB` (defaults `128MiB` and `512MiB`, [`:258-261`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/Config.java#L258-L261)). Leave `internode_max_message_size` unset: it then derives to the lower endpoint reserve (1 MiB), above the 256 KiB messages ([`DatabaseDescriptor.java:990-996`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/DatabaseDescriptor.java#L990-L996)); if startup names it, set it at or below the reserves. Unit tier: the handler takes the capacity as a constructor argument. |
| **Confirm it took effect** | The Byteman trace (9d) prints `queueCapacity=<n>` and the two reserve limits at the first `acquireCapacity` (no gauge or JMX read exposes the capacity or the reserves, so the trace is the read-back). Unit: assertions on the constructed handler. |
| **Capacity values** | `512KiB`, `1MiB`, `4MiB` (default), `16MiB`, reserves 1 MiB each; then `4MiB` once with the reserves at their defaults (the control arm). |
| **Scope** | **Per connection type per peer** — the finest of any case. `InboundMessageHandlers.createHandler()` makes one handler per `ConnectionType` ([`:130-149`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/net/InboundMessageHandlers.java#L130-L149)), one `InboundMessageHandlers` per peer ([`MessagingService.java:669-682`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/net/MessagingService.java#L669-L682)). The published gauges are **per peer, summed over its handlers** (`sumHandlers`, [`InboundMessageHandlers.java:311-318`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/net/InboundMessageHandlers.java#L311-L318)), so the active types per peer are read from the trace (`type=`), not assumed to be 4. *P* = 1, 2 and 4, as its own sweep at `4MiB` with the reserves low. |
| **Level** | Both. Unit: `AcquireCapacityTest` (harness) and upstream `ResourceLimitsTest` (reserve mechanism); no upstream test calls `acquireCapacity`. Cluster: required for the multiplier. |

**Cluster layout.** `R` plus up to four senders as separate processes on one
machine, on loopback addresses `127.0.0.1` to `127.0.0.5` (`listen_address`,
`rpc_address`, JMX port and data directories distinct per node; the multi-node
steps are in [`environment.md`](../../stage4-runtime-verification/environment.md) §5).
All five must have joined the ring (`bin/nodetool status`: `UN`) before B. `R` is
the node under test; only its yaml carries the swept value.

**Hold fixed:**

| Setting | Value | Why |
|---|---|---|
| Keyspace | `SimpleStrategy`, `replication_factor` = the node count (`P + 1`), one table | Every write fans out to `R`. |
| Consistency level | `ALL` | The coordinator waits for `R`, so the throttle slows the sender and no write is hidden by an early return. |
| `concurrent_writes` | `32` (default) on `R` | Sets how many held handlers pile up. |
| `internode_application_send_queue_*` | defaults on every node | The senders' own send-side limit is the sibling case [`internode_application_send_queue_capacity-acquireCapacity-pendingCapacityInBytes`](internode_application_send_queue_capacity-acquireCapacity-pendingCapacityInBytes--guided.md) (filed 2026-10-07); leave it. |
| Hardware and JVM | same `-Xmx` on all nodes (`2G` each) | Hold fixed. |
| Client traffic | none on `R`'s native port | The sibling case `native_transport_receive_queue_capacity` runs the same code on client connections. |

**Controls:**

- **Idle run** — the cluster up, no writes: the gauge floor and the heap floor of `R`.
- **Default-reserves arm** — once at `4MiB` capacity, with the reserves at 128 MiB and 512 MiB: expected to throttle little (9a).
- **No-hold run** — once at `1MiB`, without the Byteman hold: shows whether the queue fills without help (it should not).

**Reset between runs:** stop all nodes (`bin/nodetool -p <jmx> stopdaemon`), check nothing is left, empty every node's data, commit-log and hints directories, move `logs/` aside, edit `R`'s yaml, start `R` then the senders.

*Amended 2026-10-14 (stage-4 audit, rec. 5–8), replacing the layout, part of "Hold fixed" and the reset above:*

- **Layout.** Five processes on `pc57` from one clone (`~/cassandra-run1`), each with its own `conf/` copy
  (`CASSANDRA_CONF`, `CASSANDRA_LOG_DIR`, `JMX_PORT` replaced in `cassandra-env.sh`) and directories under
  `~/stage4-rqc/<node>/`: `R` = 127.0.0.2 (JMX 7102, the seed, the only node with the Byteman agent), `S1`–`S4` =
  127.0.0.3–.6 (JMX 7103–7106); `storage_port` 7010; one evenly spaced Murmur3 token each, `auto_bootstrap: false`.
  The ring is always these five, keyspace `ks` RF 5, table `ks.t (pk bigint PRIMARY KEY, v blob)`; *P* is the number
  of senders writing, each through its own native port only, so `R` coordinates nothing.
- **Hold fixed, added:** `write_request_timeout: 10000ms` on every node (the default 2 s is shorter than the queue the
  peer arms build: up to 512 writes in flight drain at about 160 per second, 3.2 s; a write that expires is dropped,
  which the "no drop" step would misread); `native_transport_max_threads: 512` on the senders (each write held at CL ALL
  occupies a request thread; up to 256 are in flight per sender); `auto_snapshot: false` on every node (the table is
  truncated between arms, and a snapshot would keep the data on disk). Each `-Xmx2G`, `concurrent_writes` 32. The
  coordinator's wait is the nearer of `write_request_timeout` and `native_transport_timeout` (12 s), so 10 s governs.
- **Reset between arms:** the senders stay up for the whole run. `R` is restarted (`nodetool stopdaemon`, yaml rebuilt,
  started with the agent) once per capacity value, keeping its data directories; after every arm the table is truncated
  (`TRUNCATE ks.t`, every node up), so each arm starts empty. 5 nodes × about 1.2 GB per 30 s arm would otherwise fill
  the disk.

### 9c. Workload

The operand is inbound internode bytes accepted and not yet processed, so `R` must
receive faster than it processes. The senders are the coordinators; `R` holds each
mutation's verb handler for a fixed time, as a slow disk would, so the permits
(released only after the handler ran, `InboundMessageHandler.java:66`) stay out.

**Harness.** `<harness>` stands for
`<misconfiguration-repo>/cassandra/if-check-exp/stage4-runtime-verification/long-path/harness/internode_application_receive_queue_capacity-acquireCapacity-queueCapacity`.
Work for step 1, before run 1:

| File | What it is |
|---|---|
| `AcquireCapacityTest.java` | Unit tier. Package `org.apache.cassandra.net` (the method is `protected`). Builds an anonymous `AbstractMessageHandler` subclass (five abstract methods, all `throw new UnsupportedOperationException()`; the decoder and channel are `null`, as `acquireCapacity(Limit, Limit, int)` does not use them) with `ResourceLimits.Concurrent` reserves and `WaitQueue.endpoint/global`, as `ConnectionBurnTest` builds them. |
| `receive-trace.btm` | Byteman, observation only: one line at the exit of `AbstractMessageHandler.acquireCapacity(Limit, Limit, int)` (outcome, `queueSize`, `queueCapacity`, the reserves' `using()` and `limit()`, handler `id()`). |
| `hold-handler.btm` | Byteman, the trigger: sleeps `stage4.hold.ms` at the entry of `MutationVerbHandler.doVerb`, **loaded on `R` only**. |

```bash
# unit tier
ant testsome -Dtest.name=org.apache.cassandra.net.ResourceLimitsTest
cp <harness>/AcquireCapacityTest.java test/unit/org/apache/cassandra/net/
ant testsome -Dtest.name=org.apache.cassandra.net.AcquireCapacityTest

# cluster tier, once: schema (every node up)
bin/cqlsh 127.0.0.2 -e "CREATE KEYSPACE keyspace1 WITH replication = {'class': 'SimpleStrategy', 'replication_factor': <P+1>};"
# per capacity value, with R's hold in force: stress against the senders only
tools/bin/cassandra-stress write n=<rows> no-warmup cl=ALL -col 'n=FIXED(1)' 'size=FIXED(262144)' \
  -rate threads=<t> -node whitelist 127.0.0.2,127.0.0.3,...   # the sender addresses, not R
```

**Starting values.** Estimates, not measurements:

| Setting | Value | Why |
|---|---|---|
| Mutation | one column of 256 KiB (about 256 KiB on the wire) | Above the large-message threshold; about `⌊C / M⌋` = 2, 4, 16, 64 messages per capacity. |
| Hold | `-Dstage4.hold.ms=200` | Caps the receiver at roughly `32 / 0.2 s` = 160 mutations/s, about 40 MiB/s, which the senders outrun. |
| Rows | `n=20000` (about 5 GiB per run) | At 40 MiB/s that is above a minute of saturation. |
| Client threads | `threads=64` per stress process, one process per sender | Enough in flight to fill the largest capacity (16 MiB = 64 messages). |
| Time in B | 60 s | Several gauge samples. |

**If `R` is not saturated** (`ThrottledCount` flat in the reserves-low arm): stop, reset, and repeat with `hold.ms=500` and `threads=128`. Record each step. If it still is not, the run is invalid (9a).

*Amended 2026-10-14 (stage-4 audit, rec. 1, 2, 4, 6–8), replacing the harness list, the stress commands and the
starting values above where they differ:*

| File | What it is |
|---|---|
| `AcquireCapacityTest.java` | As above, but the channel is a Netty `EmbeddedChannel` (its event loop runs the wait queue's reactivation task, which a `null` channel cannot) and the subclass overrides `processUpToOneMessage` to retry the waiting request through the three-argument `acquireCapacity` and record the outcome; the steps are 9e's amended list. Prints `STAGE4 check <name> expected=… actual=… ok\|MISMATCH`. |
| `receive-trace.btm` | Byteman, observation only, three lines to the file named by `-Dstage4.trace`: `acq id=<handler id, with peer and type> b=<bytes> out=<Outcome> q=<queueSize after> cap=<queueCapacity> ep=<endpoint using>/<limit> gl=<global using>/<limit> ms=` at the exit of `acquireCapacity(Limit, Limit, int)`; `rel id= b= q= ms=` at the exit of `releaseCapacity(int)`; `hold <ms>` once per held `doVerb`, from the hold rule. |
| `hold-handler.btm` | The trigger, `R` only: at the entry of `MutationVerbHandler.doVerb`, **if the file named by `-Dstage4.hold.file` exists**, sleep `stage4.hold.ms` (200). The file is created for B only, so the idle control and A run unheld. |
| `write-load.py` | The writer, replacing `cassandra-stress`: bundled Python driver, protocol 5, pinned to one sender, CL `ALL`, `INSERT INTO ks.t (pk, v)` with a fresh `pk` and a random value of fixed size, **exactly *W* writes in flight** for a fixed time, every `pk` and outcome logged. A fixed in-flight count is what decides whether `R` can be saturated, so it replaces stress's thread count. Also `probe`, `schema`, `vt` (one read of `system_views.internode_inbound` on `R`). |
| `sample-inbound.py` | Polls `system_views.internode_inbound` on `R` twice a second during A and B (one driver connection to `R`'s native port: a few small client requests, which use a separate handler instance and not the internode ones under test). |
| `Jmx.java` | JMX client: `get`, `query`, and `poll <ms> <n> <bean> <attr> …` (one JVM, one line per sample) for the networking pool (`type=BufferPool,scope=networking,name=UsedSize`), heap used, the table's local write count and the dropped-`MUTATION` counter. |
| `make-node-yaml.sh`, `cluster-run.py` | Per-node `conf/` (layout of 9b) and the run script: one label per `R` lifetime, `EXPECTED:` lines, every node stopped on a failed check. |

**Workload (amended):** values of 262,144 B (`large` connection; 32,768 B in the small arm, `small` connection, both
sides of the 64 KiB threshold, `OutboundConnections.java:215`); *W* = 128 writes in flight per writing sender (256 in
the small arm), enough for the largest plateau (67 messages at 16 MiB; 159 small ones); the hold 200 ms, so `R`
completes about 160 writes a second; **B lasts 30 s**, A is 200 writes with one in flight and no hold. The writer runs
until the end of B, then the in-flight writes finish.

### 9d. Observables

| Observable | How to read it | When to sample | Trap |
|---|---|---|---|
| **Usage counter** — accepted and unprocessed bytes | Per peer: `org.apache.cassandra.metrics:type=InboundConnection,scope=<peer>,name=ScheduledBytes` ([`InternodeInboundMetrics.java:55-68`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/metrics/InternodeInboundMetrics.java#L55-L68)); `bin/nodetool -p <R's jmx> sjk mx -mg -b '<name>' -f Value`. Per connection: the trace's `queueSize` for each handler `id`. | Every 5 s in B; trace peaks at the end | The gauge sums a peer's handlers and **includes `small` and `urgent`**; use the trace to split by `type=`. The scope label is the peer's address with the port; list `bin/nodetool sjk mx -q 'org.apache.cassandra.metrics:type=InboundConnection,*'` first. |
| **Disallow evidence** — throttling | `ThrottledCount` and `ThrottledNanos` of the same peer (cumulative gauges). Trace: lines with `outcome=INSUFFICIENT_ENDPOINT` or `INSUFFICIENT_GLOBAL`. | Before and after A and B | Both counters rise only when `acquireCapacity` returns a non-`SUCCESS` outcome, i.e. after the reserves also refused (`:405-406`). So `ThrottledCount` = 0 does not mean the capacity was never reached, only that the reserves absorbed it: read `S` too. |
| **Bypass volume** | None recorded. A trace line with `outcome=SUCCESS` and `queueSize` above `queueCapacity` plus the borrowed excess would be one (it should not exist). | — | — |
| **Messages not dropped** | `cassandra-stress` `Total errors` (must be 0); `bin/nodetool tpstats` dropped counts on `R` (`MUTATION`); `ProcessedCount` of each peer at the end against the rows sent. | End of each run | Client write timeouts at CL ALL are expected while `R` is held back and are a symptom, not evidence of a drop. A timeout counts as an error in stress: if errors appear, check whether the writes landed (`ProcessedCount`) before calling them lost. |
| **Real resource** — heap of `R` | `jcmd <pid> GC.run` then `jcmd <pid> GC.heap_info`; subtract the idle floor and the young generation, as the memtable cases do | Idle control; end of A and B | Held mutations sit in the `MutationStage` queue (deserialized), so they are on the heap; `GC.heap_info` alone does not collect. Never use RSS. |
| *Amended 2026-10-14 (rec. 1):* **Usage counter, exact** | Per handler: the trace's `q=` on every `acq` and `rel` line (the peak per `id`, and the node total rebuilt line by line); per peer: `using_bytes` and `using_reserve_bytes` of `system_views.internode_inbound` (Σ `queueSize` and the endpoint reserve in use, `InternodeInboundTable.java:118-119`), sampled twice a second | A and B | `ScheduledBytes` (`InboundCounters`, added at dispatch, removed after the run, `InboundMessageHandlers.java:257-273`) misses a large message whose frames are still arriving; it is recorded beside `using_bytes`, not used for *S*. |
| *Amended 2026-10-14 (rec. 2):* **Real resource, where it is** | A large message waits as frames from the networking pool (`FrameDecoder` reads through `BufferPoolAllocator`, `BufferPools.forNetworking()`; `InboundMessageHandler.java:358-384` deserializes them on the stage and releases them): `org.apache.cassandra.metrics:type=BufferPool,scope=networking,name=UsedSize`, once a second through `Jmx.java poll`. Deserialized messages: `jcmd <pid> GC.class_histogram` (live objects, a full GC), the `org.apache.cassandra.db.Mutation` row's instance count, idle and twice in B (a third and two thirds in). Heap used is polled with the pool | Idle; B | A small message is deserialized on the event loop before it is queued (`:156-195`), a large one only when its stage thread runs it, so the two arms put the same accounted bytes in different places. |
| *Amended 2026-10-14 (rec. 4):* **No drop, exactly** | Writer: every `pk` and its outcome. `R`: `org.apache.cassandra.metrics:type=Table,keyspace=ks,scope=t,name=WriteLatency` `Count` (local applies) and `type=DroppedMessage,scope=MUTATION,name=Dropped` `Count`, before and after each arm; `expired_count` of every peer | Before and after each arm | `R` coordinates nothing, so each local apply on `R` is one received mutation: the delta must equal the rows the writers sent. |

### 9e. Running the scenarios

**Unit tier.** Commands are in 9c. `AcquireCapacityTest` builds a handler with
`queueCapacity` = 1000 and reserves of 500 each, and asserts, in order:

1. a 600-byte request: `SUCCESS`, `queueSize` = 600, reserves untouched, `throttledCount` = 0;
2. a second 600-byte request: the excess over the capacity (200) is borrowed from both reserves: `SUCCESS`, `queueSize` = 1200, both reserves `using()` = 200;
3. a 600-byte request with the reserves' remaining room (300 each) below its excess (600): `INSUFFICIENT_GLOBAL`, `queueSize` unchanged, reserves unchanged, and (through the five-argument `acquireCapacity`) `throttledCount` = 1 with a ticket registered on the global wait queue;
4. the same with the global reserve large and the endpoint reserve small: `INSUFFICIENT_ENDPOINT`, and the global reserve's `using()` returns to its previous value;
5. `releaseCapacity(600)` signals the wait queue, and a retry then succeeds.

Record pass or fail and, per step, the asserted values. Run `ResourceLimitsTest` as the reserve control.

*Amended 2026-10-14 (stage-4 audit, rec. 3), replacing steps 1–5:* as filed, step 5 cannot pass through the wait
queue: a waiting handler is reactivated only when its reserve can lend the **whole** message
(`WaitQueue.schedule()`, `AbstractMessageHandler.java:686-721`, `tryAllocate(t.bytesRequested)` at `:702`), and 600 B never fits
a 500 B reserve. Reserves of 800 B each, `queueCapacity` 1000:

1. `b = 1000` on a fresh handler: `SUCCESS` with `q = 1000` and both reserves at 0 (the `≤` boundary); then `b = 1`:
   `SUCCESS`, both reserves at 1 (only the excess is borrowed). A second fresh handler then runs 2–3 and 5.
2. `600` → `SUCCESS`, `q = 600`, reserves 0, `throttledCount = 0`; `600` → `SUCCESS`, `q = 1200`, reserves 200 / 200.
3. `700` through the five-argument method: excess 700 > 600 left → `INSUFFICIENT_GLOBAL`, `q` and reserves unchanged,
   `throttledCount = 1`, a ticket on the global wait queue (no reactivation task yet: 200 + 700 > 800).
4. A third handler, endpoint 300 / global 10,000: `600`, `600` (endpoint 200), `600` → `INSUFFICIENT_ENDPOINT`, the
   global reserve back at 200 (rolled back), a ticket on the endpoint queue.
5. On the second handler, `releaseCapacity(600)`: `q = 600`, both reserves 0, and the global queue schedules one
   reactivation on the channel's event loop; running it retries the 700 with a 700 B lease: `SUCCESS`, `q = 1300`,
   endpoint 300, global 300 (the lease's unused 400 returned), `throttledNanos > 0`.
6. **Wiring** (its own JVM): raw config capacity 123,456 B, endpoint 654,321 B, global 777,777 B before
   `MessagingService` is built; `getInbound(<peer>)` holds 123,456 and an endpoint limit of 654,321, the global limit is
   777,777, and a handler made by `createHandler` has `queueCapacity` 123,456 (§4 steps 1–5).

Instrument check (amended): the instrumented run must give one `acq` line per three-argument call with `cap=1000`, and
`rel` lines for the releases.

**Before the cluster tier.**

1. **Instrument check.** Run `AcquireCapacityTest` with `receive-trace.btm` attached and expect one trace line per assertion above (`queueCapacity=1000`):

   ```bash
   ant testsome -Dtest.name=org.apache.cassandra.net.AcquireCapacityTest \
     -Dtest.jvm.args="-javaagent:$PWD/build/lib/jars/byteman-4.0.20.jar=script:<harness>/receive-trace.btm -Dstage4.byteman.out=$HOME/stage4-logs/cluster/instrument-check.txt"
   ```

2. **Start `R` with both rules, the senders with neither:**

   ```bash
   mkdir -p ~/stage4-logs/cluster/<value>
   export MAX_HEAP_SIZE=2G
   export JVM_EXTRA_OPTS="-javaagent:$PWD/build/lib/jars/byteman-4.0.20.jar=script:<harness>/receive-trace.btm,script:<harness>/hold-handler.btm,listener:true -Dstage4.byteman.out=$HOME/stage4-logs/cluster/<value>/receive-trace.txt -Dstage4.hold.ms=200"
   bin/cassandra -p cassandra.pid > ~/stage4-logs/cluster/<value>/stdout.txt 2>&1   # in R's tree
   ```

   Confirm with `Submit -l` (listener port per node must differ; `R` uses the default 9091, senders do not load the agent).

**Cluster tier, for each capacity value:**

1. **Control run** — set `R`'s capacity and reserves, reset (9b), start `R`, then the senders, wait for `UN` on all, and with no writes read the gauges and heap.
2. **Scenario A — below the capacity** — one sender, one stress thread, `n=200`, no hold: read `ScheduledBytes` and `ThrottledCount` (zero expected).
3. **Scenario B — above it** — start the stress processes (one per sender, `P` of them) with the hold in force and the time noted (`date +%s%3N`); sample every 5 s; at 30 s take a thread dump of `R` (`jcmd <pid> Thread.print`: `MutationStage` threads inside the hold) and a heap reading; stop the stress at 60 s; wait for `ScheduledBytes` to drain to the floor (the permits are released) and record how long it took.
4. **Peer sweep** — at `4MiB`, repeat B with *P* = 1, 2 and 4.
5. **Stop and read the trace** — stop all nodes, then per peer and `type=`: peak `queueSize` and the count of `INSUFFICIENT_*` lines.

**Controls (9b)** — the default-reserves arm and the no-hold run, once each, B only. Reported as controls; no §9a row depends on them.

Stop when each scenario's records are taken; a run where `ThrottledCount` stays zero in the reserves-low arm is invalid (9a).

**Record for stage 4:** every node's `cassandra.yaml` diff and JVM options, the exact commands, the `Submit -l` output, the trace, the gauge samples, the stress output headers and result blocks, and the thread dump, per value.

*Amended 2026-10-14 (stage-4 audit, rec. 5–8), replacing steps 1–5 of the cluster tier with the same scenarios:*

0. Once: build the five `conf/` copies, start `R` (with the agent, hold file absent) then `S1`–`S4`, wait for five
   `UN` and the binary protocol on each, create `ks` and `ks.t` (RF 5).
1. Per `R` lifetime (labels `c512k`, `c1m`, `c4m`, `c16m`, `defres`): stop `R`, rebuild its yaml with the label's
   capacity and reserves, start it with the agent and wait for five `UN`. The first `acq` line of the trace must
   show `cap=` and the reserve limits of the label, or the run stops (the read-back).
2. Per arm: **control** (10 s, no writes): `using_bytes`, the networking pool, a class histogram, the counters.
   **A**: one sender, one write in flight, 200 rows, no hold. **B**: create the hold file, start *P* writers with
   *W* in flight each for 30 s; sample `internode_inbound` twice and the JMX poll once a second; class histograms and
   a thread dump (`jcmd <pid> Thread.print`: `MutationStage` threads in `MutationVerbHandler.doVerb` sleeping) at 10 s and
   20 s; stop the writers at 30 s, wait for their last writes, remove the hold file, wait until every peer's
   `using_bytes` is 0; the counters again; `TRUNCATE ks.t`.
3. Arms by lifetime: `c512k`: B (*P* = 1). `c1m`: B, then `nohold` (B without the hold file). `c4m`: B (*P* = 1),
   `p2` (S1, S2), `p4` (S1–S4), then `small` (*P* = 1, 32,768 B, *W* = 256). `c16m`: B. `defres`: B.
4. At the end stop every node and check none is left; per arm, the script writes `summary.txt` with `EXPECTED:` lines
   built from the trace (peak *q* per handler id, outcomes, the rule checks of 9a), the samples and the counters.

*Corrected 2026-10-15 after the shakedowns (results §3 rows 1–4; §9a unchanged):* (a) the five nodes' data, commit-log,
hints and cache directories are on a tmpfs, `/mnt/stage4-rqc` (48 GiB, `sudo mount -t tmpfs -o size=48g,mode=1777
tmpfs /mnt/stage4-rqc`; `conf/` and `logs/` stay under `~/stage4-rqc/<node>/`): `pc57`'s disk is a spinning RAID volume,
and with every node applying every write its flushes stalled all five nodes' writes past the 10 s timeout. (b) After the
counters of each arm, `nodetool truncatehints` on every node before `TRUNCATE ks.t`; at the start of each arm no node
may hold a pending hint (`nodetool listpendinghints`), or the arm records it as a failed check. (c) The no-drop reading
adds each sender's dropped-`MUTATION` count and `TotalHints` (`type=Storage,name=TotalHints`), before and after: a write
the receiver's backpressure holds past its deadline expires in the **sender's** outbound queue and is hinted, not
dropped by `R`. (d) `c1m` runs last, because its unheld control leaves hints that a dispatch in progress keeps from
`truncatehints`. (e) The unheld control's no-drop reading is printed as a `CONTROL` line: no §9a row rests on it.

## 10. Provenance

| Field | Content |
|--------|---------|
| **Stage-3 feed** | `3b` — established by deep-reading the source; no stage-1/2 row led here. |
| **Line numbers checked** | 2026-09-22 against the local `cassandra-5.0.9` clone (`git describe --tags`). |
| **Escape hatch / Target-3 note** | none found yet. |
| **Stage-4 feedback** | **Closed 2026-10-15, long path, run 1 on `pc57`: unit Confirmed; cluster Confirmed (§9a row 1); no run 2** — [results](../../stage4-runtime-verification/results/internode_application_receive_queue_capacity-acquireCapacity-queueCapacity--guided.md). Step-0 audit 2026-10-14 **Ready after amendments** (§9a frozen `5ef01c26…`, 23:37 EDT, verified unchanged at the end of run 1; §9 at run 1 `6f6fed0d…`): *S* is the check's operand (`queueSize` from a trace, `using_bytes`), not `ScheduledBytes`; the real resource is read where it is (deserialized `Mutation`s, the networking pool) with a small-message arm; unit step 5 made passable (whole-message lease, an `EmbeddedChannel`); a fixed in-flight writer sized to the plateau, a 10 s write deadline; five processes on loopback, RF 5; corrected 2026-10-15 after the shakedowns (node data on a tmpfs, hints cleared between arms, `c1m` last). Readings: per-connection plateau `⌊(C + 1 MiB)/M⌋·M` = **5 · 7 · 19 · 67** messages at 512 KiB · 1 · 4 · 16 MiB, exactly as predicted, every refusal `INSUFFICIENT_GLOBAL`, `ThrottledCount` 259 · 431 · 976 · 814; at 4 MiB each of *P* = 1, 2, 4 peers fills its own 19 *M* while the shared global reserve stays below 1 MiB (§8's multiplier); default reserves: no refusal, 128 messages (the writer's bound) held; every write completed and was applied on `R`, no drop, expiry or hint. **Real resource:** live deserialized `Mutation`s = `min(n, 32)` in the large arms and all 159 in the small arm; the queued large messages sit in the off-heap networking pool (13.5 MB at 16 MiB for 35 queued). Unit 74/74 checks; independent self-check 95/95. No §4–§8 text amended. |
| **Notes** | **Found while converting §9 (2026-10-06):** the published `InboundConnection.<peer>` gauges are per peer, summed over the peer's connection types (`sumHandlers`), not per connection as the old §9 said; per-connection values come from a Byteman trace (§9d). `ThrottledCount` moves only after the reserves also refuse (`AbstractMessageHandler.java:405-406`). **From stage 4 (2026-10-15), for stage 3 to judge, not applied to §5–§8:** (1) §7's "deserialized `Message` on the heap" and §6a's allocation site (`InboundMessageHandler.java:166`, cited as `:163`) hold for **small** messages (≤ 64 KiB, deserialized on the event loop before dispatch); a **large** message is accepted on its first frame (`:207-225`), waits as off-heap networking-pool frames and is deserialized on the stage thread just before the verb handler (`:358-384`, `:481-510`), so the heap holds at most `concurrent_writes` of them; observed: 159 live `Mutation`s in the small arm, ≤ 32 in the large arms, the rest in the pool. (2) §6b's "not dropped" holds at the receiver (no drop in any held arm), but the wait has no bound of its own: in shakedown 1 (spinning disk, unheld) the queue backed up into the **sender's** outbound link, where messages expired after `write_request_timeout` and were hinted (`dropping message of type MUTATION_REQ whose timeout expired before reaching the network`); a shakedown observation, not a run-1 reading. (3) A waiting handler is reactivated only when its reserve can lend the **whole** message (`AbstractMessageHandler.java:702`), while `internode_max_message_size`, when unset, is derived from the two endpoint reserves only (`DatabaseDescriptor.java:990-996`), not the receive global reserve: with a global reserve below a message's size a throttled connection could never be reactivated (derived, not tested; Target-3 material). (4) The throttle also bounds a slow receiver's concurrency: `R` completed `min(n, 32)` / hold writes per second (24 · 34 · 93 · 158/s). (5) Citation drift: `MessagingService.java:678` is `:679`. |

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
