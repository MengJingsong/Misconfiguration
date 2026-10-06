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

**Stage 3 writes this section; stage 3 never runs it** — no measured numbers
and no verdict here; results go to
[`../../../stage4-runtime-verification/README.md`](../../../stage4-runtime-verification/README.md).
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
- **Logic:** (1) the receiver must be saturated, or the run is invalid. (2) Per peer,
  `ScheduledBytes` stops near the capacity and `ThrottledCount` rises: usage **stops
  at the limit**, by the disallow branch (these two gauges move only on it). (3) The
  plateau moves with the capacity: usage **follows the constraint**. (4) The sum over
  peers moves with the peer count: **§8's multiplier**. (5) Every write completes
  with no error, so the disallow is a wait, not a drop. (6) With default reserves
  the same load barely throttles: the contrast shows the reserves are what bind.
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

**Conclusions:**

| Result | Conclusion |
|---|---|
| Reserves low: per-peer `S` plateaus near `C` plus the reserve share and moves with *C* across the four values; `ThrottledCount` rises; `Σ S` scales with *P*; no write errors | **Confirmed** — the check enforces as traced, and §8's multiplier holds. |
| As above, but `Σ S` does not scale with *P* | **Confirmed per connection; §8's multiplier refuted** — rewrite §8's worst-case formula (Target-3 material). |
| Reserves low: `S` passes `C` plus the reserves by more than borrowing explains, with the check being evaluated (`ThrottledCount` moving) | **Refuted** — something admits bytes without passing this check; no bypass is recorded, so it is a new finding. |
| Reserves low: `S` is flat across the values while `ThrottledCount` moves | **Refuted** — the check fires but does not govern the accounted bytes; check that the reserves really are pinned. |
| `S` follows *C* but `ThrottledCount` stays zero | **Not confirmed** — something other than this check is capping (the sender, the reserves); re-read. |
| The receiver's retained heap grows while `Σ S` is capped | **Refuted** — the counter does not track the resource; §8's ceiling claim is wrong. |
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
steps are in [`environment.md`](../../../stage4-runtime-verification/environment.md) §5).
All five must have joined the ring (`bin/nodetool status`: `UN`) before B. `R` is
the node under test; only its yaml carries the swept value.

**Hold fixed:**

| Setting | Value | Why |
|---|---|---|
| Keyspace | `SimpleStrategy`, `replication_factor` = the node count (`P + 1`), one table | Every write fans out to `R`. |
| Consistency level | `ALL` | The coordinator waits for `R`, so the throttle slows the sender and no write is hidden by an early return. |
| `concurrent_writes` | `32` (default) on `R` | Sets how many held handlers pile up. |
| `internode_application_send_queue_*` | defaults on every node | The senders' own send-side limit is the sibling `internode_application_send_queue_capacity` candidate; leave it. |
| Hardware and JVM | same `-Xmx` on all nodes (`2G` each) | Hold fixed. |
| Client traffic | none on `R`'s native port | The sibling case `native_transport_receive_queue_capacity` runs the same code on client connections. |

**Controls:**

- **Idle run** — the cluster up, no writes: the gauge floor and the heap floor of `R`.
- **Default-reserves arm** — once at `4MiB` capacity, with the reserves at 128 MiB and 512 MiB: expected to throttle little (9a).
- **No-hold run** — once at `1MiB`, without the Byteman hold: shows whether the queue fills without help (it should not).

**Reset between runs:** stop all nodes (`bin/nodetool -p <jmx> stopdaemon`), check nothing is left, empty every node's data, commit-log and hints directories, move `logs/` aside, edit `R`'s yaml, start `R` then the senders.

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

### 9d. Observables

| Observable | How to read it | When to sample | Trap |
|---|---|---|---|
| **Usage counter** — accepted and unprocessed bytes | Per peer: `org.apache.cassandra.metrics:type=InboundConnection,scope=<peer>,name=ScheduledBytes` ([`InternodeInboundMetrics.java:55-68`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/metrics/InternodeInboundMetrics.java#L55-L68)); `bin/nodetool -p <R's jmx> sjk mx -mg -b '<name>' -f Value`. Per connection: the trace's `queueSize` for each handler `id`. | Every 5 s in B; trace peaks at the end | The gauge sums a peer's handlers and **includes `small` and `urgent`**; use the trace to split by `type=`. The scope label is the peer's address with the port; list `bin/nodetool sjk mx -q 'org.apache.cassandra.metrics:type=InboundConnection,*'` first. |
| **Disallow evidence** — throttling | `ThrottledCount` and `ThrottledNanos` of the same peer (cumulative gauges). Trace: lines with `outcome=INSUFFICIENT_ENDPOINT` or `INSUFFICIENT_GLOBAL`. | Before and after A and B | Both counters rise only when `acquireCapacity` returns a non-`SUCCESS` outcome, i.e. after the reserves also refused (`:405-406`). So `ThrottledCount` = 0 does not mean the capacity was never reached, only that the reserves absorbed it: read `S` too. |
| **Bypass volume** | None recorded. A trace line with `outcome=SUCCESS` and `queueSize` above `queueCapacity` plus the borrowed excess would be one (it should not exist). | — | — |
| **Messages not dropped** | `cassandra-stress` `Total errors` (must be 0); `bin/nodetool tpstats` dropped counts on `R` (`MUTATION`); `ProcessedCount` of each peer at the end against the rows sent. | End of each run | Client write timeouts at CL ALL are expected while `R` is held back and are a symptom, not evidence of a drop. A timeout counts as an error in stress: if errors appear, check whether the writes landed (`ProcessedCount`) before calling them lost. |
| **Real resource** — heap of `R` | `jcmd <pid> GC.run` then `jcmd <pid> GC.heap_info`; subtract the idle floor and the young generation, as the memtable cases do | Idle control; end of A and B | Held mutations sit in the `MutationStage` queue (deserialized), so they are on the heap; `GC.heap_info` alone does not collect. Never use RSS. |

### 9e. Running the scenarios

**Unit tier.** Commands are in 9c. `AcquireCapacityTest` builds a handler with
`queueCapacity` = 1000 and reserves of 500 each, and asserts, in order:

1. a 600-byte request: `SUCCESS`, `queueSize` = 600, reserves untouched, `throttledCount` = 0;
2. a second 600-byte request: the excess over the capacity (200) is borrowed from both reserves: `SUCCESS`, `queueSize` = 1200, both reserves `using()` = 200;
3. a 600-byte request with the reserves' remaining room (300 each) below its excess (600): `INSUFFICIENT_GLOBAL`, `queueSize` unchanged, reserves unchanged, and (through the five-argument `acquireCapacity`) `throttledCount` = 1 with a ticket registered on the global wait queue;
4. the same with the global reserve large and the endpoint reserve small: `INSUFFICIENT_ENDPOINT`, and the global reserve's `using()` returns to its previous value;
5. `releaseCapacity(600)` signals the wait queue, and a retry then succeeds.

Record pass or fail and, per step, the asserted values. Run `ResourceLimitsTest` as the reserve control.

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

## 10. Provenance

| Field | Content |
|--------|---------|
| **Stage-3 feed** | `3b` — established by deep-reading the source; no stage-1/2 row led here. |
| **Line numbers checked** | 2026-09-22 against the local `cassandra-5.0.9` clone (`git describe --tags`). |
| **Escape hatch / Target-3 note** | none found yet. |
| **Stage-4 feedback** | none yet. **§9 converted to the new layout 2026-10-06** (9a to 9e) from the old §9; not yet audited (stage-4 README, step 0) and not yet run. The new §9 lists its harness as work for step 1. |
| **Notes** | **Found while converting §9 (2026-10-06):** the published `InboundConnection.<peer>` gauges are per peer, summed over the peer's connection types (`sumHandlers`), not per connection as the old §9 said; per-connection values come from a Byteman trace (§9d). `ThrottledCount` moves only after the reserves also refuse (`AbstractMessageHandler.java:405-406`). |

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
