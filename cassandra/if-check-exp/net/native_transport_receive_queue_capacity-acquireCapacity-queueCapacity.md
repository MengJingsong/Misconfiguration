# native_transport_receive_queue_capacity — message

> **Index:** [../stage3-ai-deep-read/_INDEX.md](../stage3-ai-deep-read/_INDEX.md)
>
> **Source:** apache/cassandra @ tag `cassandra-5.0.9`

## 1. Location

| Field | Content |
|-------|---------|
| **Case ID** | NATIVE_TRANSPORT_RECEIVE_QUEUE_CAPACITY-ACQUIRECAPACITY-QUEUECAPACITY |
| **Constraint** | `native_transport_receive_queue_capacity` — configuration entry (`Config.java`) |
| **Enforcement pattern** | (b) — the capacity check returns a verdict to its caller, and the decision point itself depends on `native_transport_throw_on_overload` |
| **Capacity check** | [`AbstractMessageHandler.acquireCapacity():419`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/net/AbstractMessageHandler.java#L419) (reached via `CQLMessageHandler`) |
| **Decision point** | [`CQLMessageHandler.processOneContainedMessage():196-256`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/transport/CQLMessageHandler.java#L196-L256) |
| **Allocation site** | [`CQLMessageHandler.processRequest():385-391`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/transport/CQLMessageHandler.java#L385-L391) — `messageDecoder.decode(...)` creates the `Message.Request` |
| **Related cases** | [`internode_application_receive_queue_capacity-acquireCapacity-queueCapacity`](internode_application_receive_queue_capacity-acquireCapacity-queueCapacity.md) (same `acquireCapacity()` check, internode side) |

```java
protected ResourceLimits.Outcome acquireCapacity(Limit endpointReserve, Limit globalReserve, int bytes)
{
    long currentQueueSize = queueSize;
    if (currentQueueSize + bytes <= queueCapacity)
    {
        queueSizeUpdater.addAndGet(this, bytes);
        return ResourceLimits.Outcome.SUCCESS;
    }
    // ... borrow from endpoint/global reserves (see the internode sibling case's §1 note) ...
}
```

**Relationship to the internode case:** identical enforcement point and
`queueCapacity`/reserve mechanics — see the internode case for the shared
if-check's full body and the endpoint/global reserve sub-checks (lines
428/431). What differs here is *everything downstream of a disallow
outcome*: this case's caller (`CQLMessageHandler`) has its own, materially
different handling of a `false` result — see §5/§6b, the most important
divergence from the internode sibling.

## 2. Context

Every CQL client connection (from drivers, `cqlsh`, application code) sends
query/execute/prepare requests to a Cassandra node over a native-protocol
connection. As with internode traffic, a connection decodes bytes off the
wire and deserializes them into an in-memory CQL request object before
dispatching it for execution; if a client (or many clients) send requests
faster than the node can drain them, deserialized request objects would
otherwise accumulate in memory without bound. This if-check is the same
per-connection flow-control gate as the internode case, applied to CQL
client connections instead of peer-to-peer messaging — but, notably, its
*default* configuration does not actually stop deserialization when the
check fails (see §6b); it primarily drives client-visible overload
signaling instead.

## 3. Module

| Field | Content |
|-------|---------|
| **Module** | Native transport / CQL client connections (`transport/`) |
| **One-line role** | Netty pipeline handler (`CQLMessageHandler`) that decodes and deserializes CQL requests arriving from a client connection, tracking per-connection in-flight byte usage and applying overload signaling when a client sends faster than the node can absorb. |

## 4. Capacity check & limit

| Field | Content |
|-------|---------|
| **Is this a capacity check?** | Yes — same running-total (`queueSize`) vs. fixed per-connection ceiling (`queueCapacity`) comparison as the internode case, on the CQL side. |
| **Usage-side operand** | `queueSize` — inherited `volatile long` on `AbstractMessageHandler`, bytes of not-yet-fully-processed inbound CQL requests attributed to this client connection. |
| **Limit-side operand** | `queueCapacity` — `protected final long`, set once at construction from the CQL-side config value. |
| **Limit type** | Configuration (`native_transport_receive_queue_capacity`), fixed default. |

**Limit initialization path** (declare → configure/derive → store → read at the check):

1. [`Config.java:301-302`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/Config.java#L301-L302) — declared: `native_transport_receive_queue_capacity` (`DataStorageSpec.IntBytesBound`, default `"1MiB"` — note: 4× smaller than the internode side's 4MiB default).
2. [`DatabaseDescriptor.java:3208-3210`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/DatabaseDescriptor.java#L3208-L3210) — read/converted: `getNativeTransportReceiveQueueCapacityInBytes()` returns `conf.native_transport_receive_queue_capacity.toBytes()`.
3. [`PipelineConfigurator.java:306`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/transport/PipelineConfigurator.java#L306) — configured/derived: `int queueCapacity = DatabaseDescriptor.getNativeTransportReceiveQueueCapacityInBytes();`, read once per new client connection during pipeline setup.
4. [`PipelineConfigurator.java:317-332`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/transport/PipelineConfigurator.java#L317-L332) — passed into `new CQLMessageHandler<>(..., queueCapacity, ...)`.
5. [`CQLMessageHandler.java:124,134`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/transport/CQLMessageHandler.java#L124) → [`AbstractMessageHandler.java:172,185`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/net/AbstractMessageHandler.java#L172-L185) — stored: `CQLMessageHandler`'s constructor forwards `queueCapacity` to `super(...)`, assigned to the inherited `final` field the check at line 419 reads — identical storage mechanism to the internode case, just a different config value threaded in.

## 5. Decision point & branch semantics

| Field | Content |
|-------|---------|
| **Decision point** | [`CQLMessageHandler.processOneContainedMessage():196-256`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/transport/CQLMessageHandler.java#L196-L256) |
| **Verdict** | verdict returned by `AbstractMessageHandler.acquireCapacity()` (`:419`), read at the decision point above, whose outcome also depends on `native_transport_throw_on_overload`. |

The if-check's own two branches are identical to the internode case (see
that case's §5). What's specific to this case is *how the caller reacts*
to a `false`/disallow outcome, which depends on the
`native_transport_throw_on_overload` config (default **`false`**) —
[`CQLMessageHandler.java:196-224`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/transport/CQLMessageHandler.java#L196-L224):

| Config | Branch | Effect |
|--------|--------|--------|
| `native_transport_throw_on_overload = true` | Disallow | [`acquireCapacity()`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/transport/CQLMessageHandler.java#L701) (the non-queueing variant) returns `false` → [`discardAndThrow()`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/transport/CQLMessageHandler.java#L274) fires: **the message is discarded, never deserialized**, and an `OverloadedException` is sent back to the client. Matches the internode case's "no object created" outcome, but via a clean client-facing error instead of silent backpressure. |
| `native_transport_throw_on_overload = false` **(default)** | Disallow | [`acquireCapacityAndQueueOnFailure()`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/transport/CQLMessageHandler.java#L693) (the internode-style queueing variant) returns `false`, registering a `Ticket` on the endpoint/global wait queue exactly like the internode case — **but the caller does not stop there.** Per [`CQLMessageHandler.java:236-256`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/transport/CQLMessageHandler.java#L236-L256), even with `backpressure = Overload.BYTES_IN_FLIGHT` set, execution falls through to `processRequestAndUpdateMetrics(...)` — **the message is deserialized and dispatched anyway.** The only observable effects are a `backpressure` flag threaded into the response (client sees an overload warning) and, if the client is paused (`decoder.isActive()` check), `ClientMetrics.instance.pauseConnection()`. |

## 6. Code path

### 6a. Allow branch → object creation

1. [`CQLMessageHandler.java:200`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/transport/CQLMessageHandler.java#L200) (`throwOnOverload=true` path) or [`CQLMessageHandler.java:223`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/transport/CQLMessageHandler.java#L223) (`throwOnOverload=false` path, when capacity *is* available) — `acquireCapacity(...)` returns `true`/`Outcome.SUCCESS` for this connection's `queueSize + bytes <= queueCapacity` check.
2. [`CQLMessageHandler.java:267-271`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/transport/CQLMessageHandler.java#L267-L271) — `processRequestAndUpdateMetrics()`: tracks `channelPayloadBytesInFlight`, updates metrics, calls `processRequest(composeRequest(header, bytes), backpressure)`.
3. [`CQLMessageHandler.java:372-382`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/transport/CQLMessageHandler.java#L372-L382) — `composeRequest()` slices the raw frame bytes into an `Envelope` (header + un-decoded `ByteBuf` body) — not yet the CQL object itself.
4. [`CQLMessageHandler.java:385-391`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/transport/CQLMessageHandler.java#L385-L391) — **object creation**: `M message = messageDecoder.decode(channel, request);` — deserializes the envelope body into a live `Message.Request` (e.g. a `QueryMessage`, `ExecuteMessage`, `PrepareMessage`, or `BatchMessage`), then `dispatcher.dispatch(...)` hands it to the execution stage.

### 6b. Disallow branch effect

**Depends entirely on `native_transport_throw_on_overload`, and the
default case does *not* withhold object creation:**

- **`throwOnOverload=true` (non-default):** clean reject. [`discardAndThrow()`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/transport/CQLMessageHandler.java#L274-L292) releases the raw `buf`, logs the overload, and throws a `OverloadedException` back to the client via `handleError()` — `processOneContainedMessage()` returns `true` (frame consumed) without ever reaching `messageDecoder.decode()`. No object is created; matches the internode case's disallow outcome, but as an explicit client error rather than silent queueing.
- **`throwOnOverload=false` (default, per `Config.java:1393`):** **not a rejection at all.** [`acquireCapacityAndQueueOnFailure()`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/transport/CQLMessageHandler.java#L693-L698) still registers a wait-queue `Ticket` (same mechanism as the internode case, inherited from `AbstractMessageHandler`), but `processOneContainedMessage()` [does not branch away from decoding](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/transport/CQLMessageHandler.java#L236-L256) — it proceeds to `processRequestAndUpdateMetrics()` → `messageDecoder.decode()` regardless. **This means, under the default configuration, this if-check's disallow branch has no effect on whether the object is created at all** — only on a `backpressure` flag surfaced to the client and a wait-queue registration whose practical effect (given decode already happened) is unclear from this method alone. This is a stronger, *default-mode* version of the escape-hatch pattern flagged as Target-3-relevant in the memtable cases (there, the escape hatch required a specific `markBlocking()` state; here, it's simply the out-of-the-box config).

## 7. Object & resource

| Field | Content |
|-------|---------|
| **Object created** | A concrete `Message.Request` subtype (e.g. `QueryMessage`, `ExecuteMessage`, `PrepareMessage`, `BatchMessage`), decoded from a CQL client's request frame. |
| **Resource consumed** | JVM heap bytes — accounting unit is `messageSize`/`header.bodySizeInBytes` (the on-wire CQL frame body size); actual deserialized object heap footprint is proportional to, not byte-identical to, this accounted size. |
| **Rough sizing** | Bounded per-connection to `queueCapacity` (default 1MiB via `native_transport_receive_queue_capacity`) under `throwOnOverload=true`; effectively unbounded by *this* check under the default `throwOnOverload=false`, since decode proceeds regardless of outcome (see §6b) — the node instead relies on the endpoint/global reserve limits (`native_transport_max_request_data_in_flight_per_ip` / `native_transport_max_request_data_in_flight`, `Config.java:296-298`) as the effective backstop in that mode. |
| **Lifetime / release** | [`release(Envelope.Header)`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/transport/CQLMessageHandler.java#L507-L510) calls `releaseCapacity(bytes)` and decrements `channelPayloadBytesInFlight`; invoked from `handleErrorAndRelease()` on decode failure and (per `release(FlushItem)`, line 500) once a response for the request has been flushed back to the client. |

## 8. Maximum memory/disk bound

Under `throwOnOverload=true`, the effect mirrors the internode case exactly
(substituting `native_transport_receive_queue_capacity`'s 1MiB default for
`internode_application_receive_queue_capacity`'s 4MiB): raising the config
raises how many not-yet-processed bytes **one CQL connection** may hold
before falling back to the endpoint/global reserves or rejecting outright;
multiplied across however many concurrent client connections the node
serves.

Under the **default** `throwOnOverload=false`, this if-check's limit-side
operand does **not** bound maximum memory on its own — per §6b, decoding
proceeds regardless of the check's outcome, so `queueCapacity` only affects
when a `backpressure` signal is surfaced to the client, not whether bytes
get deserialized. In this (default) mode, the actual memory ceiling for
CQL-request deserialization is set one layer up, by the endpoint/global
reserve limits (`native_transport_max_request_data_in_flight_per_ip`,
`native_transport_max_request_data_in_flight`, `Config.java:296-298`) —
those *are* still enforced via the shared `Limit.tryAllocate()` reserve
checks inherited from `AbstractMessageHandler` (same lines 428/431 as the
internode case), which this case does not independently re-verify. This is
a materially different "maximum memory bound" story from every other case
in this folder so far: the config named in this case's title does not, by
itself and by default, bound anything — a reader relying on the config
name alone would be misled. **Flagged as noteworthy for Target 3
(bypass/default-failure-mode analysis)**, beyond this folder's normal
Target 1+2 scope, since the "bypass" here is simply the out-of-the-box
default rather than requiring any special caller state.

## 9. Provenance

| Field | Content |
|--------|---------|
| **Stage-3 feed** | `3b` — established by deep-reading the source. (Stage 1/2 had surfaced this line as a row, but the case was made from the source, not the row.) |
| **Line numbers checked** | 2026-09-22 against the local `cassandra-5.0.9` clone (`git describe --tags`). |
| **Escape hatch / Target-3 note** | under the default `native_transport_throw_on_overload=false` the message is still decoded despite the over-limit verdict; see §6b. |

---

## 10. Notes

- **Biggest finding of this case, distinct from its internode sibling:**
  under the *default* configuration, this if-check's disallow branch does
  not withhold object creation at all (§6b) — a stronger and more directly
  reachable version of the escape-hatch pattern noted in the memtable
  cases. Worth flagging prominently for Target 3.
- **Reserve-capacity checks not separately cased here either**, same
  scoping choice as the internode case — `endpointReserve`/`globalReserve`
  (`native_transport_max_request_data_in_flight_per_ip` /
  `native_transport_max_request_data_in_flight`) share this case's
  object-creation path but aren't traced as their own case.
- Second sibling not investigated: `PreV5Handlers.LegacyDispatchHandler`
  (pre-protocol-V5 connections) appeared in the `transport/` triage batch
  (`checkLimits()`, `PreV5Handlers.java:197-209`) and may use a related but
  distinct capacity-tracking path (`channelPayloadBytesInFlight`) — not
  confirmed to be the same if-check; flagged for a future triage pass, not
  pursued here.
