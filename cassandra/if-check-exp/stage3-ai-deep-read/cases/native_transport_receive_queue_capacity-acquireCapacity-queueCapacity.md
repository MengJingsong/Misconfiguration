# native_transport_receive_queue_capacity — message

> **Index:** [../_INDEX.md](../_INDEX.md)
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


## 9. Test design (guidance for stage 4)

**Stage 3 writes this section; stage 3 never runs it.** Method and pitfalls:
[README.md §8](../../README.md#8-designing-a-test-for-a-case). Where stage 4's
numbers go: [`../../stage4-runtime-verification/README.md`](../../stage4-runtime-verification/README.md).

**This case's experiment is a comparison of two modes, not a single sweep.**
§8 says the config in this case's title **does not bound anything by itself
under the default** `native_transport_throw_on_overload = false` — decoding
proceeds regardless of the verdict. So the design must run the whole capacity
sweep **twice**, once in each mode, and the finding is the difference between
them. A single-mode run at the default would correctly observe "no effect" and
would be worthless as evidence, because "no effect" is the predicted result.

**One piece of luck makes this cheap:** unlike every other knob in this case's
family, `native_transport_throw_on_overload` is **hot-settable over JMX**
([`StorageServiceMBean.setNativeTransportThrowOnOverload(boolean)`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/service/StorageServiceMBean.java#L1296)
→ [`DatabaseDescriptor.java:2381`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/DatabaseDescriptor.java#L2381)),
so the two modes can be compared on one node without a restart between them.

| Field | Content |
|-------|---------|
| **Testability** | **Config-testable; mixed restart requirements.** `queueCapacity` is restart-only — a `final` field read per connection at [`PipelineConfigurator.java:306`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/transport/PipelineConfigurator.java#L306) from a non-`volatile` `Config` field, so a new value needs a restart (a *reconnect* is not enough, because the config itself does not change). The mode flag and both reserves **are** hot-settable. Checked 2026-09-28. |
| **Constraint knob** | `native_transport_receive_queue_capacity` in `cassandra.yaml` (default `1MiB`, [`Config.java:301-302`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/Config.java#L301-L302)). **Mode knob:** `native_transport_throw_on_overload` ([`Config.java:1393`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/Config.java#L1393), default `false`), over JMX. **Reserves, which must be pinned:** `native_transport_max_request_data_in_flight_per_ip` and `native_transport_max_request_data_in_flight` ([`Config.java:296-298`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/Config.java#L296-L298)) — both `volatile` with setters. **Their defaults are heap-derived**, `maxMemory()/10` global and `maxMemory()/40` per IP ([`DatabaseDescriptor.java:649-656`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/DatabaseDescriptor.java#L649-L656)), so pin `-Xmx` too or the reserves move between arms on their own. |
| **Capacity values to test** | `native_transport_receive_queue_capacity` ∈ {`128KiB`, `512KiB`, **`1MiB`** (default), `4MiB`}, each run in **both** modes, with reserves pinned small enough that the per-connection tier is what binds. Note `native_transport_max_message_size` must not exceed either reserve or startup throws ([`DatabaseDescriptor.java:911-915`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/DatabaseDescriptor.java#L911-L915)) — so lower it alongside the reserves. |
| **Usage-side observable** | `queueSize` on the per-connection `CQLMessageHandler` — bytes of CQL request frames accounted and not yet released. |
| **Instrument** | The per-connection counter is not exposed, but **the two modes have distinct, direct-evidence metrics**, which is what the comparison rests on. Under `throwOnOverload = true`: **`Client.RequestDiscarded`** (a meter, [`ClientMetrics.java:147`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/metrics/ClientMetrics.java#L147)), marked inside `discardAndThrow()` at [`CQLMessageHandler.java:278`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/transport/CQLMessageHandler.java#L278) — plus the client-side `OverloadedException` itself. Under the default: **`Client.ConnectionPaused`** and the **`Client.PausedConnections`** gauge ([`ClientMetrics.java:144-146`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/metrics/ClientMetrics.java#L144-L146)), incremented at [`CQLMessageHandler.java:250`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/transport/CQLMessageHandler.java#L250) — note this fires only when the decoder is inactive, so it is weaker evidence than `RequestDiscarded`. Heap via `jcmd <pid> GC.heap_info` after a forced full GC. |
| **Scope of the limit** | **Per client connection.** One `CQLMessageHandler` is built per connection during pipeline setup ([`PipelineConfigurator.java:317-332`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/transport/PipelineConfigurator.java#L317-L332)), so `N` = concurrent client connections — and unlike the internode sibling's peer count, **`N` is controlled by the client and can be raised arbitrarily**. That makes the multiplier the sharper half of this case: fix connection count per arm, then vary it (say 1, 10, 100) as its own sweep. |
| **Suggested level** | **Cluster-first, unusually.** The mode-dependent behaviour lives in `CQLMessageHandler`'s caller, and the client-visible outcome (`OverloadedException` versus a decoded response with a backpressure warning) is the clearest signal — both are easiest to observe with a real driver. Unit support: `test/unit/org/apache/cassandra/net/ResourceLimitsTest.java` covers the reserve mechanism; `test/unit/org/apache/cassandra/transport/` has handler scaffolding worth checking before writing a harness. The designed unit trigger is two tests, one per mode: a handler with tiny `queueCapacity` and exhausted reserves, fed one oversized frame, asserting (a) `throwOnOverload = true` → no `Message.Request` constructed and an `OverloadedException` raised, (b) `false` → the request **is** constructed despite the over-limit verdict. |

### 9a. Workload — driving the usage operand

- Single node, dedicated, with a CQL driver client on a separate host. Pin `-Xmx` (the reserves derive from it).
- Pin both reserves and `native_transport_max_message_size` low, so the per-connection capacity is the binding tier rather than the reserves.
- Drive requests whose frame bodies are a large fraction of `queueCapacity` — large `BatchMessage`s or wide `QueryMessage`s with big bound values. A few hundred KiB against a 128KiB capacity means one or two in flight fills it.
- Hold **connection count** fixed within an arm and record it; the driver's pool size is the multiplier.
- Make request processing lag intake so the queue fills: high concurrency per connection, and queries that are slow server-side.

**Deterministic single-shot form:** set `queueCapacity` and both reserves below
a single request's frame size, then send one request. Under
`throwOnOverload = true` the client should get `OverloadedException` for the
very first request; under the default it should get a **normal response**. That
single pair of observations is the case's central finding, obtainable in
seconds, and it should be the first thing stage 4 runs (README §8.2 rule 2).

### 9b. Scenario A — just reach capacity

Hold offered load so per-connection accounted bytes sit just below
`queueCapacity`, in both modes.

Expect, in **both** modes identically: requests succeed, `RequestDiscarded` and
`ConnectionPaused` flat at zero, no `OverloadedException`. The modes should be
indistinguishable here — that is what makes this the control.

### 9c. Scenario B — try to exceed capacity

Push past it, in each mode. **Derive the expectation from §6b** — the two modes
diverge completely:

| Mode | Expected | Evidence |
|---|---|---|
| **`throwOnOverload = true`** | The request is **discarded and never deserialized**; the client receives `OverloadedException`. | `Client.RequestDiscarded` rises; the driver surfaces `OverloadedException`. Heap attributable to in-flight requests plateaus near `queueCapacity × connections`. |
| **`throwOnOverload = false`** (default) | The request is **deserialized and dispatched anyway**. A `backpressure` flag rides along in the response and, if the decoder is inactive, the connection is paused. **Nothing is withheld.** | `Client.RequestDiscarded` stays flat. `Client.ConnectionPaused` / `PausedConnections` may move, or may not. The client gets a normal result. **Accounted bytes and heap should exceed `queueCapacity`**, bounded only by the reserves. |

The pair of rows above is the experiment. Report them side by side at every
capacity value.

### 9d. Expected dose-response

If the traced path is the binding limit:

- **Under `throwOnOverload = true`:** peak in-flight request bytes ≈ `queueCapacity × connections`, linear in the knob across 128KiB → 4MiB, and linear in connection count. `RequestDiscarded` rate rises as the knob falls at fixed offered load.
- **Under the default:** peak in-flight bytes should be **flat in `queueCapacity`**, or nearly so, and instead track the reserves. This is the prediction that matters, and it is a *negative* one — §8 says the config named in this case's title bounds nothing by itself in the default mode.
- **Across connection counts (1 → 10 → 100), in `true` mode:** total should scale with connection count until a reserve binds, then flatten. The knee is where the reserve takes over, and locating it is worth doing: it says how many clients it takes for the per-connection number to stop being the operative limit.
- **Heap versus accounted bytes:** §7 notes accounting is the on-wire frame size while the resource is the deserialized object. Expect a consistent ratio > 1; report it.

### 9e. Interpretation — what each outcome means

| Observation at scenario B | Reading |
|---|---|
| `true` mode: in-flight plateaus at `queueCapacity × connections` and tracks the knob; `RequestDiscarded` rises. Default mode: flat in the knob, bounded by the reserves | **The case is confirmed, including §8's central claim** that the default mode does not enforce. Both halves matter. |
| Both modes behave identically and both track the knob | §6b is wrong about the fall-through at [`CQLMessageHandler.java:236-256`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/transport/CQLMessageHandler.java#L236-L256) — the default mode *does* withhold. That would be a genuine correction to §5, §6b and §8, and should amend the case file. |
| Both modes flat in the knob, with `RequestDiscarded` moving in `true` mode | The reserves are binding before the per-connection tier in both arms. Pin them lower and re-run; a setup error, not a finding. |
| Nothing moves in either mode and no overload metric fires | The workload never saturated a connection, or `native_transport_max_message_size` is rejecting the frames earlier on a different path. Check before concluding. |

### 9f. What would refute this case

The case makes **two** claims and they are refuted differently.

1. *Under `throwOnOverload = true`, the comparison at `acquireCapacity():419` gates deserialization of CQL requests, so per-connection in-flight request bytes are bounded by `native_transport_receive_queue_capacity`.* Refuted if, with reserves pinned below one frame, in-flight bytes do not plateau near `queueCapacity` and do not move with it, while `RequestDiscarded` confirms the check is evaluated.
2. *Under the default `throwOnOverload = false`, the check withholds nothing.* Refuted — and this is the more interesting direction — if the default mode **does** show a dose-response to `queueCapacity` with the reserves held constant. That would mean §6b misread the fall-through, and §8's "the config name would mislead a reader" conclusion would have to be withdrawn.

A stage-4 run that only tests the default mode cannot settle either claim: it
would observe no effect, which claim 2 predicts and claim 1 says nothing about.

### 9g. Confounders and controls

- **The reserves are the dominant confounder**, and their defaults are derived from `-Xmx` ([`DatabaseDescriptor.java:649-656`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/DatabaseDescriptor.java#L649-L656)). Pin `-Xmx` and set both reserves explicitly in every arm, including the baseline.
- **`native_transport_max_message_size`** rejects oversized frames on a *different* path, and is constrained to be no larger than either reserve. Keep frames below it, and confirm rejections are not coming from there — `Client.ProtocolException` and the rejection at [`CQLMessageHandler.java:551`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/transport/CQLMessageHandler.java#L551) (already recorded as a separate rejected row) are the tell.
- **Connection count is the multiplier and is client-controlled.** Fix the driver's pool size per arm and record it; a driver that silently opens more connections invalidates the arm.
- **The native-transport rate limiter** (`native_transport_max_requests_per_second`) also produces `OverloadedException`, via a different `Overload` reason. Check the exception's message — `buildOverloadedException()` at [`:298-312`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/transport/CQLMessageHandler.java#L298-L312) distinguishes "breached limit on bytes in flight" from the requests/second and queue-time variants. Only the bytes-in-flight message belongs to this case.
- **The sibling case shares this exact code.** `internode_application_receive_queue_capacity` runs the same `AbstractMessageHandler.acquireCapacity()` for internode traffic. Keep internode traffic quiet — a single-node instance with `RF = 1` is the cleanest way.
- **Accounted bytes ≠ heap bytes** (§7); measure heap separately after a forced full GC.
- **Baseline** at defaults in both modes under light load; **idle control** with the node up and clients connected but idle, for the metric floor.

## 10. Provenance

| Field | Content |
|--------|---------|
| **Stage-3 feed** | `3b` — established by deep-reading the source. (Stage 1/2 had surfaced this line as a row, but the case was made from the source, not the row.) |
| **Line numbers checked** | 2026-09-22 against the local `cassandra-5.0.9` clone (`git describe --tags`). |
| **Escape hatch / Target-3 note** | under the default `native_transport_throw_on_overload=false` the message is still decoded despite the over-limit verdict; see §6b. |
| **Stage-4 feedback** | none yet |

---

## 11. Notes

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
