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

**Stage 3 writes this section; stage 3 never runs it** — no measured numbers
and no verdict here; results go to
[`../../../stage4-runtime-verification/README.md`](../../../stage4-runtime-verification/README.md).
The test sets `native_transport_receive_queue_capacity`, floods a node with large
CQL requests over protocol-v5 connections held in flight, and compares the two
overload modes (`throw_on_overload` on and off) at each value. **Run so far:**
none. Converted to this layout 2026-10-06.

### 9a. Procedure and conclusions

**Testability:** `native_transport_receive_queue_capacity` is config,
**restart-only** (read once per new connection from a non-`volatile` field,
[`PipelineConfigurator.java:306`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/transport/PipelineConfigurator.java#L306)).
The **mode is chosen per connection**, by the client's `THROW_ON_OVERLOAD` startup
option, and the config `native_transport_throw_on_overload` is only the fallback
when the client sends no option
([`PipelineConfigurator.java:309-314`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/transport/PipelineConfigurator.java#L309-L314)).
So both modes run on one node in one run, from two sets of connections, with the
config left at its default `false`. (A JMX flip of the config would only affect
connections opened afterwards.) Only protocol v5 connections reach this handler;
older versions use `PreV5Handlers` (§11).

**Claim under test:** with `throw_on_overload` on, a connection whose accounted
bytes plus a new frame would pass `native_transport_receive_queue_capacity` — after
borrowing from the endpoint and global reserves fails — has the frame discarded
undecoded and an `OverloadedException` returned, so decoded request bytes per
connection are bounded. With it off (the default), §6b and §8 say the over-limit
frame is still decoded and dispatched, so the capacity bounds nothing and only
the reserves do.

**How this verifies the hypothesis** (a restatement of the claim, procedure,
prediction and conclusions in this section; it adds none):

- **Hypothesis:** in the throwing mode the per-connection decoded bytes are held to
  the capacity (plus reserve borrowing) and over-limit frames are discarded; in the
  default mode they are not held to it.
- **Test:** vary the capacity (128 KiB, 512 KiB, 1 MiB the default, 4 MiB) with both
  reserves pinned low, and drive a fixed number of connections of each mode, each
  with a window of large requests that the server holds in flight. Read, per
  connection, the bytes accounted (`queueSize`) and the bytes decoded and not yet
  released (`channelPayloadBytesInFlight`), the discards, and the node's memory.
- **Logic:** (1) at each value the over-limit condition must occur, or the run is
  invalid. (2) Throwing mode: discards occur and decoded bytes per connection stop
  near the capacity: usage **stops at the limit**. (3) The plateau moves with the
  capacity: usage **follows the constraint**. (4) The default mode, run at the same
  values and offered load, shows whether decoded bytes follow the capacity (§8 says
  they do not); the two modes are read side by side. (5) The discards and the
  wait-queue evidence, not only the plateau, show which branch fired.
- **Refuted if:** throwing-mode decoded bytes do not move with the capacity, or
  exceed capacity plus reserves; or the default mode shows a dose-response (§8's
  second claim). **Not confirmed** if the plateau moves but no discard or
  backpressure evidence appears (rows of the Conclusions table).

**Procedure:**

1. **Unit tier** — (a) run upstream `ClientResourceLimitsTest` (the two modes both
   execute under exhausted reserves; backpressure warning). (b) Run the harness test
   `NativeQueueModesTest` (9c): one oversized frame at a capacity and reserves below
   it, in each mode, and a window of held frames, counting discards, decoded
   requests and `channelPayloadBytesInFlight`.
2. **Cluster tier** — one node, restarted per capacity value (128 KiB, 512 KiB,
   1 MiB, 4 MiB); reserves, `native_transport_max_message_size` and `-Xmx` pinned.
3. **At each value:** idle control → **A**, offered load that stays under the
   capacity, in both modes → **B**, offered load far above it, in both modes. No
   scenario C: no bypass beyond the default mode itself is recorded, and that mode
   is a column of B, not a separate arm.
4. **Compare** with the prediction and read the result below.

**Prediction.** Notation: *C* = the capacity; *F* = one request's frame body
(256 KiB at the cluster tier); *N* = connections per mode; *R* = the per-IP reserve
(4 MiB; the global reserve is also 4 MiB); `D` = peak `channelPayloadBytesInFlight`
of a connection (bytes decoded and not yet released, kept even when the accounting
did not accept them); `A` = peak `queueSize` of a connection.

- **A (both modes):** no discard, no backpressure warning, `D = A`, and `D` is at most
  `⌊C / F⌋ × F`. The modes are indistinguishable. This is the control.
- **B, throwing mode:** every frame that does not fit in `C` plus the reserves left is
  discarded and answered with `OverloadedException`; `Client.RequestDiscarded` rises.
  Per connection `D = A ≤ C + (share of R)`, so with *N* connections `ΣD ≤ N × C + R`,
  linear in *C* with slope *N*.
- **B, default mode, two readings to be told apart.** §8 reads the source as: the
  over-limit frame is decoded regardless, so `D` is not held to `C`: `D` grows with the
  client's window (a window of `W` frames gives `D = W × F` while `A` stays at most
  `C`), flat in *C*. Reading the handler's fall-through
  ([`CQLMessageHandler.java:236-261`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/transport/CQLMessageHandler.java#L236-L261))
  also gives a second possibility: after the first over-limit frame the handler
  returns `false`, which stops it reading further frames until a reserve wait-queue
  ticket fires, so `D` would stop near `⌊C / F⌋ × F + F` and follow *C*. The test
  decides between them from `D` against *C*, not from either reading. `A` stays at
  most `C` in both. The disallow evidence in this mode is the response warning
  `Request breached limit(s) on bytes in flight … and triggered backpressure` and the
  server's INFO line with the same text.
- **Second knob, *N*:** at 1, 10 and 100 connections (throwing mode) `ΣD` scales with
  *N* until the reserves bind; the knee is where the reserves take over.

**Conclusions:**

| Result | Conclusion |
|---|---|
| Throwing mode: discards occur, `D` stops at about `⌊C / F⌋ × F` plus borrowing, moves with *C* across the four values, and is at most `N × C + R` in total; default mode: `D` flat in *C* and above `⌊C / F⌋ × F` | **Confirmed**, including §8's second claim: the capacity bounds decoded bytes only in the throwing mode. |
| Throwing mode as above; default mode: `D` stops near `⌊C / F⌋ × F + F` and follows *C*, with the backpressure warning | **Confirmed for the throwing mode; §8's second claim refuted** — the default mode bounds decoded bytes per connection to `C` plus one frame by pausing the connection, not by withholding the decode. §5, §6b and §8 are amended. |
| Throwing mode: `D` is flat across the values, or exceeds `N × C + R`, while `RequestDiscarded` rises | **Refuted** — the capacity does not bound decoded bytes; the discards come from something else (check 9d, "other overload"). |
| Throwing mode: `D` follows *C* but no discard and no `OverloadedException` appears | **Not confirmed** — something other than this check is capping; re-read. |
| `A` passes `C` plus the reserves, or decoded memory grows while `A` is capped | **Refuted** — the counter does not track the resource; §8's ceiling claim is wrong. |
| Both modes behave the same and both follow *C* with discards | **Refuted** for §5/§6b: the mode flag does not select the branch. Re-read the pipeline. |
| No over-limit condition occurs (`A` never reaches `C`, no wait-queue ticket) | **Invalid run** — raise the window or lower the reserves (9b, 9c) and re-run. |
| Rejections appear with a message that is not the bytes-in-flight one (`requests/second`, queue time, or a protocol error) | **Invalid run** — another limit fired (9d); fix 9b and re-run. |

**Why `D` and not `A`:** the accounted `queueSize` is exactly what the check
compares, so it is capped by construction; only `D`, kept for decoded requests whatever
the accounting said, shows what the node holds.

### 9b. Setup

| Field | Content |
|-------|---------|
| **Constraint knob** | `native_transport_receive_queue_capacity` in `cassandra.yaml` (default `1MiB`, [`Config.java:301-302`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/Config.java#L301-L302)); restart-only. Unit tier: `DatabaseDescriptor.setNativeTransportReceiveQueueCapacityInBytes(<bytes>)`, as `ClientResourceLimitsTest.setUp()` does, before the server starts. |
| **Mode knob** | The client's startup option `THROW_ON_OVERLOAD=1` (`SimpleClient.connect(false, true)`); `connect(false, false)` sends nothing, so the connection takes the config default. Leave `native_transport_throw_on_overload` at `false`. |
| **Confirm it took effect** | The Byteman trace (9d) prints `queueCapacity=<bytes>` for every connection; the throwing connections' mode is read from the trace's `throw=` field, set from the handler's `throwOnOverload`. Unit: assertions on both. |
| **Capacity values** | `128KiB`, `512KiB`, `1MiB` (default), `4MiB`. |
| **Scope** | **Per connection.** One `CQLMessageHandler` per connection ([`PipelineConfigurator.java:317-332`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/transport/PipelineConfigurator.java#L317-L332)); *N* is set by the client: 10 per mode for the sweep, then 1, 10 and 100 for the second sweep at the default capacity. Hold *N* fixed within an arm and record it. |
| **Level** | Both. Unit: upstream `ClientResourceLimitsTest` (uses `queueCapacity = 1` and 600-byte reserves; both modes), `QueueBackpressureTest`; harness `NativeQueueModesTest`. Cluster: the in-tree `SimpleClient`, so the startup option and protocol v5 are controlled exactly. The Java driver does not set `THROW_ON_OVERLOAD`, so it cannot select the mode. |

**Hold fixed:**

| Setting | Value | Why |
|---|---|---|
| `native_transport_max_request_data_in_flight_per_ip` | `4MiB` | Heap-derived default (`maxMemory() / 40`) would move with `-Xmx` and be far above the capacities; 4 MiB makes the reserves bind soon after the per-connection tier ([`DatabaseDescriptor.java:649-656`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/DatabaseDescriptor.java#L649-L656)). All connections come from one client host, so this is the reserve that binds. |
| `native_transport_max_request_data_in_flight` | `4MiB` | The global reserve, for the same reason. |
| `native_transport_max_message_size` | `2MiB` | Must not exceed either reserve or startup throws ([`DatabaseDescriptor.java:911-915`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/DatabaseDescriptor.java#L911-L915)); frames (256 KiB) stay far below it. |
| `native_transport_throw_on_overload` | `false` (default) | The mode is set per connection; a `true` here would turn the default arm into the throwing one. |
| `native_transport_rate_limiting_enabled` | `false` (default) | The rate limiter also causes backpressure and `OverloadedException` (9d). |
| `native_transport_queue_max_item_age_threshold` | default | The queue-time check also backpressures when the executor is behind (9d); keep the load below the executor's capacity by holding the requests with a sleep, not by saturating it. |
| JVM heap | `-Xms4G -Xmx4G` | Hold fixed. |
| Table | one table `ks.t (pk int PRIMARY KEY, v blob)`, `RF = 1`, one node | Keeps internode traffic, which uses the sibling case's check, out of the run. |

**Controls:**

- **Idle run** — node up, no clients: the memory floor.
- **Connected-idle run** — all connections open, no requests: the per-connection floor.
- **Other-limit check** — the same load with the reserves at the heap-derived defaults and `throw_on_overload` on: no discard should occur (the reserves no longer bind); it shows the reserves, not *C* alone, produce the discards.

**Reset between runs:** stop the node (`bin/nodetool stopdaemon`), check nothing is left, empty the data, commit-log and saved-caches directories, move `logs/` aside, edit the capacity, start again.

### 9c. Workload

A request is a `QueryMessage` `INSERT INTO ks.t (pk, v) VALUES (?, ?)` with a 256 KiB blob. Its frame body is about 256 KiB. The server holds each request, as a slow query would, so its bytes stay accounted until the response is flushed; the hold changes when the bytes are released, not the path to the check.

**Harness.** `<harness>` stands for
`<misconfiguration-repo>/cassandra/if-check-exp/stage4-runtime-verification/long-path/harness/native_transport_receive_queue_capacity-acquireCapacity-queueCapacity`.
Work for step 1, before run 1:

| File | What it is |
|---|---|
| `NativeQueueModesTest.java` | Unit tier. Extends `NativeProtocolLimitsTestBase` (as `ClientResourceLimitsTest` does); see 9e. |
| `NativeFlood.java` | Cluster tier client on `SimpleClient`: opens *N* protocol-v5 connections of one mode, sends a window of *W* pipelined 256 KiB requests on each and keeps the window full for a set time, and prints per-second counts of responses, `OverloadedException`s, and responses carrying the backpressure warning. |
| `queue-trace.btm` | Byteman, observation only: one line at the exit of `AbstractMessageHandler.acquireCapacity(Limit,Limit,int)` (outcome, `queueSize`, `queueCapacity`) and one at the entry of `CQLMessageHandler.processRequest` (`channelPayloadBytesInFlight`, `throwOnOverload`, handler id). |
| `hold-request.btm` | Byteman, the trigger: sleeps `stage4.hold.ms` at the entry of the static `Dispatcher.processRequest(Channel, Request, Overload, RequestTime)` (it runs on the request executor, not the event loop), so a request's capacity is held. |

```bash
# unit tier
ant testsome -Dtest.name=org.apache.cassandra.transport.ClientResourceLimitsTest
cp <harness>/NativeQueueModesTest.java test/unit/org/apache/cassandra/transport/
ant testsome -Dtest.name=org.apache.cassandra.transport.NativeQueueModesTest

# cluster tier (one command per mode, started together); ant build must have run
java -cp "build/classes/main:build/classes/test:build/lib/jars/*" NativeFlood \
  --host 127.0.0.1 --connections <N> --window <W> --frame-bytes 262144 --seconds 60 --throw-on-overload <true|false>
```

**Starting values.** Estimates, not measurements:

| Setting | Value | Why |
|---|---|---|
| Frame | 256 KiB | Fits whole frames in all four capacities except that 128 KiB admits none: at *C* = 128 KiB every frame is over the limit and the connection depends on the reserves (a useful edge). |
| Window *W* | 32 (8 MiB per connection) | Above every capacity and above the 4 MiB reserves, so the over-limit condition occurs at every value. |
| Connections *N* | 10 per mode | `ΣD` under the throwing mode ≈ `10 × C + 4 MiB`: 5.3 MiB at 128 KiB to 44 MiB at 4 MiB, a range well above noise. |
| Hold | `-Dstage4.hold.ms=500` | Each request holds its capacity for 0.5 s, so a full window stays in flight for the sample period. |
| Time in B | 60 s | Several samples. |

**If the over-limit condition does not occur** (no discard in the throwing arm, no backpressure warning in the default arm): stop, reset, repeat that value with *W* = 64; if it still does not, lower both reserves to 2 MiB (and `native_transport_max_message_size` to 1 MiB). Record each step as a deviation. If none works, the run is invalid (9a).

### 9d. Observables

| Observable | How to read it | When to sample | Trap |
|---|---|---|---|
| **Usage counter** — `queueSize` of each connection's handler, `A` | The `acquireCapacity` trace line: `acquire outcome=<SUCCESS|INSUFFICIENT_*> queueSize=<n> queueCapacity=<n> throw=<bool> id=<handler>`. Not exposed as a gauge. | Every call; peaks from the file | `queueSize` is raised only on success, so over-limit frames in the default mode **do not appear in it**: that is why `D` is read too. Reads happen on the event loop: values are consistent per connection. |
| **Decoded bytes** — `channelPayloadBytesInFlight`, `D` | The `processRequest` trace line: `decode inflight=<n> throw=<bool> id=<handler>`; peak per `id`, summed over connections at each second for `ΣD`. | Every request | It includes frames the accounting refused (it is incremented in `processRequestAndUpdateMetrics` before the decode, [`CQLMessageHandler.java:264-267`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/transport/CQLMessageHandler.java#L264-L267)), so it is the amount of request data the node holds, independent of the verdict. |
| **Disallow evidence** — throwing mode | `Client.RequestDiscarded` (`bin/nodetool sjk mx -mg -b 'org.apache.cassandra.metrics:type=Client,name=RequestDiscarded' -f Count`), the client's count of `OverloadedException` whose message contains `breached limit on bytes in flight` (`buildOverloadedException`, [`CQLMessageHandler.java:298-312`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/transport/CQLMessageHandler.java#L298-L312)). | Before and after each scenario | `RequestDiscarded` is also marked for the rate-limit and queue-time reasons: only the **bytes** message belongs to this check. |
| **Disallow evidence** — default mode | The response warning `Request breached limit(s) on bytes in flight (Endpoint: …, Global: …) and triggered backpressure.` (`NativeFlood` counts responses carrying it) and the same text as an INFO line in `logs/system.log` (once a minute, `NoSpamLogger`, [`Dispatcher.java:391-397`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/transport/Dispatcher.java#L391-L397)); `Client.ConnectionPaused` and the `PausedConnections` gauge rise only when the decoder is active at that moment ([`CQLMessageHandler.java:249-251`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/transport/CQLMessageHandler.java#L249-L251)), so they are weaker evidence. | During B | A `Ticket` registered in the wait queue is the other half, but no metric exposes it; the `acquire outcome=INSUFFICIENT_*` trace line is its evidence. |
| **Other overload** — what would make a rejection not this check's | `Client.ProtocolException` count; the rejection message text; `native_transport_rate_limiting_enabled` read back; `dispatcher.hasQueueCapacity()` trouble shows as the `Request has spent over …` warning. | Throughout | The frame-size rejection at [`CQLMessageHandler.java:551`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/transport/CQLMessageHandler.java#L551) is a different path (already a rejected row). |
| **Real resource** — memory held for decoded requests | `jcmd <pid> GC.run` then `jcmd <pid> GC.heap_info`; direct memory `bin/nodetool sjk mx -mg -b 'java.nio:type=BufferPool,name=direct' -f MemoryUsed`; the networking pool `org.apache.cassandra.metrics:type=BufferPool,scope=networking,name=Size` and `OverflowSize`. | Connected-idle control; end of A; every 10 s in B | §7 says heap, but request payloads arrive in networking-pool buffers and may be held there; **record where the bytes sit** (heap, direct, or the networking pool) at the first value and read that one thereafter. The networking pool is bounded by `networking_cache_size` (a separate case) and overflows to the OS beyond it; keep it at its default and read `OverflowSize`. Each `sjk` call starts a JVM (1–2 s): time-stamp every reading. Never use RSS. |

### 9e. Running the scenarios

**Unit tier.** Commands are in 9c.

1. Run `ClientResourceLimitsTest` (upstream). Record pass or fail.
2. Run `NativeQueueModesTest`. It sets `queueCapacity` and both reserves to 600 bytes (as the upstream test does) and sends one `QueryMessage` with a 4 KiB blob:
   1. throwing connection (`client(true)`): asserts an `OverloadedException` whose message contains `bytes in flight`, `Client.RequestDiscarded` up by 1, and (with `queue-trace.btm` loaded) no `decode` line for that request;
   2. default connection (`client(false)`): asserts a normal response carrying the warning `bytes in flight`, `RequestDiscarded` unchanged, and one `decode` line;
   3. repeats 1 and 2 at capacities 1 KiB, 4 KiB and 16 KiB with reserves still at 600 bytes and a 4 KiB blob: the verdict flips to allow where `queueSize + 4 KiB ≤ C`, which is the check's allow branch;
   4. on one default-mode connection sends `⌊C / F⌋ + 3` held requests of *F* = 4 KiB at *C* = 16 KiB and records the maximum `decode inflight` value, to be set against *C* (the unit-tier reading of `D`).

   Record pass or fail and, per step, the asserted numbers.

**Before the cluster tier.**

1. **Instrument check.** Run `NativeQueueModesTest` with both rules attached and expect trace lines for both modes in step 2.1 and 2.2, with `queueCapacity=600`:

   ```bash
   ant testsome -Dtest.name=org.apache.cassandra.transport.NativeQueueModesTest \
     -Dtest.jvm.args="-javaagent:$PWD/build/lib/jars/byteman-4.0.20.jar=script:<harness>/queue-trace.btm,script:<harness>/hold-request.btm -Dstage4.byteman.out=$HOME/stage4-logs/cluster/instrument-check.txt -Dstage4.hold.ms=0"
   ```

2. **Start the node the same way for every run:**

   ```bash
   mkdir -p ~/stage4-logs/cluster/<value>
   export MAX_HEAP_SIZE=4G
   export JVM_EXTRA_OPTS="-javaagent:$PWD/build/lib/jars/byteman-4.0.20.jar=script:<harness>/queue-trace.btm,script:<harness>/hold-request.btm,listener:true -Dstage4.byteman.out=$HOME/stage4-logs/cluster/<value>/queue-trace.txt -Dstage4.hold.ms=500"
   bin/cassandra -p cassandra.pid > ~/stage4-logs/cluster/<value>/stdout.txt 2>&1
   ```

   Confirm both rules loaded with `java -cp build/lib/jars/byteman-submit-4.0.20.jar org.jboss.byteman.agent.submit.Submit -l`; if not, stop.

**Cluster tier, for each capacity value:**

1. **Control run** — set the capacity, reset (9b), start the node, create the table (`bin/cqlsh -e "CREATE KEYSPACE ks WITH replication = {'class':'SimpleStrategy','replication_factor':1}; CREATE TABLE ks.t (pk int PRIMARY KEY, v blob);"`), and with no clients read memory (9d). Open the *N* connections of each mode without sending (connected-idle) and read memory.
2. **Scenario A — under the capacity** — run `NativeFlood` for both modes with `--window` = `⌊C / F⌋` (2 frames at 512 KiB, 4 at 1 MiB, 16 at 4 MiB; at 128 KiB the window would be 0, so skip A at that value and record why). Expect no discard and no warning. Record the trace and the counters.
3. **Scenario B — far above it** — run both modes together for 60 s with `--window 32`, note the time, read `RequestDiscarded` and the warning counts before and after, take two thread dumps (`jcmd <pid> Thread.print`), and read memory every 10 s.
4. **Second sweep (*N*)** — at `1MiB` only, repeat B in the throwing mode with *N* = 1, 10, 100.
5. **Stop and read the trace** — `bin/nodetool stopdaemon`, check nothing is left, then compute per `id` the peak `inflight` (`D`) and the peak `queueSize` (`A`), by mode and value, and `ΣD` per second.

**Other-limit check (9b)** — once, at `512KiB`: reserves left at defaults, throwing mode only. Reported as a control; no §9a row depends on it.

Stop when each scenario's records are taken; a run that never reaches the over-limit condition is invalid (9a).

**Record for stage 4:** the `cassandra.yaml` diff and JVM options in force, the exact commands, `Submit -l` output, the trace and `NativeFlood` outputs, every reading above, per capacity value and mode.

## 10. Provenance

| Field | Content |
|--------|---------|
| **Stage-3 feed** | `3b` — established by deep-reading the source. (Stage 1/2 had surfaced this line as a row, but the case was made from the source, not the row.) |
| **Line numbers checked** | 2026-09-22 against the local `cassandra-5.0.9` clone (`git describe --tags`). |
| **Escape hatch / Target-3 note** | under the default `native_transport_throw_on_overload=false` the message is still decoded despite the over-limit verdict; see §6b. |
| **Stage-4 feedback** | none yet. **§9 converted to the new layout 2026-10-06** (9a to 9e) from the old §9; not yet audited (stage-4 README, step 0) and not yet run. The new §9 lists its harness as work for step 1. |
| **Notes** | **Found while converting §9 (2026-10-06), for stage 3 to judge, not applied to §5-§8:** (1) the overload mode is chosen **per connection** by the client's `THROW_ON_OVERLOAD` startup option; `native_transport_throw_on_overload` is only the fallback when no option is sent ([`PipelineConfigurator.java:309-314`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/transport/PipelineConfigurator.java#L309-L314)), and a JMX change affects connections opened afterwards only. (2) In the default mode the handler returns `false` after an over-limit request (`CQLMessageHandler.java:259`), which stops it reading further frames until a wait-queue ticket fires, so §8's "bounds nothing" may overstate: per connection the decoded bytes might stop near the capacity plus one frame. §9a states both readings as competing predictions. |

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
