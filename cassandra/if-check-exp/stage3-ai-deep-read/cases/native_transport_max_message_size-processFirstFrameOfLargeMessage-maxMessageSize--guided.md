# native_transport_max_message_size — large CQL request

> **Index:** [../_INDEX.md](../_INDEX.md)
>
> **Source:** apache/cassandra @ tag `cassandra-5.0.9`

**Estimate: negative** (Rule 1, recorded in `predicted-negative.md`, batch "the capacity-word pass": "rejects a single oversized frame outright (protocol/sanity bound on one message), not a running-total capacity check"). This file writes the negative estimate up with a test of the opposite claim: that `native_transport_max_message_size` does **not** bound the memory the server holds for a large request.

## 1. Location

| Field | Content |
|-------|---------|
| **Case ID** | NATIVE_TRANSPORT_MAX_MESSAGE_SIZE-PROCESSFIRSTFRAMEOFLARGEMESSAGE-MAXMESSAGESIZE |
| **Constraint** | `native_transport_max_message_size` — configuration entry (`cassandra.yaml`), default derived (null in yaml), restart to change |
| **Enforcement pattern** | (b) the check sets a verdict (`tooBig`) that the large-message object reads when later frames arrive |
| **Capacity check** | [`CQLMessageHandler.processFirstFrameOfLargeMessage():551`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/transport/CQLMessageHandler.java#L551) — `messageSize > getNativeTransportMaxMessageSizeInBytes()` |
| **Decision point** | [`LargeMessage.onIntactFrame():799`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/transport/CQLMessageHandler.java#L799) — a `tooBig` message's frames are consumed, not buffered |
| **Allocation site** | the buffering of frames of an accepted large message, [`LargeMessage.onIntactFrame():572`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/net/AbstractMessageHandler.java#L572) (`buffers.add(frame.contents.sliceAndConsume(...).share())`) |
| **Related cases** | [`native_transport_receive_queue_capacity…`](native_transport_receive_queue_capacity-acquireCapacity-queueCapacity--guided.md) (the byte budget on the same path; used as the positive control), [`networking_cache_size…`](networking_cache_size-allocateMoreChunks-memoryUsageThreshold--guided.md), [`max_mutation_size…`](max_mutation_size-validateSize-MAX_MUTATION_SIZE--guided.md) |

```java
LargeMessage largeMessage = new LargeMessage(header);
if (messageSize > DatabaseDescriptor.getNativeTransportMaxMessageSizeInBytes())
{
    ClientMetrics.instance.markRequestDiscarded();
    // Mark as too big so that discard the message after consuming any subsequent frames
    largeMessage.markTooBig();
}
else if (throwOnOverload) { ... acquireCapacity ... }
...
// LargeMessage.onIntactFrame
if (tooBig || overload != Overload.NONE)
    // we do not want to add the frame to buffers (to not consume a lot of memory and throw it away later
    frame.consume();
else
    super.onIntactFrame(frame);
```

## 2. Context

A CQL request that does not fit in one network frame is received as several frames. Cassandra reads the request's declared size from the first frame. If the size is above a configured maximum, it keeps reading and discarding the remaining frames and answers with an error; otherwise it collects the frames until the request is whole, then runs it. Without this check a client could make the server hold a request as large as the client cared to declare.

## 3. Module

| Field | Content |
|-------|---------|
| **Module** | native transport — CQL request intake (`transport`) |
| **One-line role** | Reads client requests off the wire, applies byte limits, and hands them to the request executor. |

## 4. Capacity check & limit

| Field | Content |
|-------|---------|
| **Is this a capacity check?** | partial — one request's declared size against a per-request limit; it is not a running total |
| **Usage-side operand** | `messageSize` — the request's declared body size plus header |
| **Limit-side operand** | `DatabaseDescriptor.getNativeTransportMaxMessageSizeInBytes()` |
| **Limit type** | Configuration entry, derived when unset |

**Limit initialization path:**

1. [`Config.native_transport_max_message_size:288`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/Config.java#L288) — declared, `null` by default
2. [`DatabaseDescriptor.calculateDefaultNativeTransportMaxMessageSizeInBytes():3237`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/DatabaseDescriptor.java#L3237) — default is `min(max_mutation_size, native_transport_max_request_data_in_flight, native_transport_max_request_data_in_flight_per_ip)`; an explicit value may not exceed either in-flight limit ([`DatabaseDescriptor.java:910-915`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/DatabaseDescriptor.java#L910-L915))
3. [`setNativeTransportMaxMessageSizeInBytes():3231`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/DatabaseDescriptor.java#L3231) — stored in the cached field the check reads
4. [`processFirstFrameOfLargeMessage():551`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/transport/CQLMessageHandler.java#L551) — read at the comparison

## 5. Decision point & branch semantics

| Field | Content |
|-------|---------|
| **Decision point** | [`LargeMessage.onIntactFrame():799`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/transport/CQLMessageHandler.java#L799) |
| **Verdict** | `tooBig`, a field on the `LargeMessage` set by `markTooBig()` at [`CQLMessageHandler.java:791`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/transport/CQLMessageHandler.java#L791) and read by `onIntactFrame` and `onComplete` |

| Outcome | Condition | Effect |
|---------|-----------|--------|
| **Allow** | `messageSize <=` limit | continues to the byte-budget check (`acquireCapacity`), then frames are buffered |
| **Disallow** | `messageSize >` limit | the request is marked too big; every frame is consumed without buffering; on completion an `OversizedCQLMessageException` error is returned ([`CQLMessageHandler.java:824-826`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/transport/CQLMessageHandler.java#L824-L826)) |

**Scope of the check:** it is in `processFirstFrameOfLargeMessage`, so it applies only to multi-frame requests on native protocol v5 (a request larger than `LARGE_MESSAGE_THRESHOLD`, [`CQLMessageHandler.java:83`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/transport/CQLMessageHandler.java#L83)). A request that fits in one frame takes `processOneContainedMessage` ([`CQLMessageHandler.java:178`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/transport/CQLMessageHandler.java#L178)) and is bounded by the byte budget alone. Protocol v4 and older are bounded by `native_transport_max_frame_size` instead ([`Envelope.Decoder:429`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/transport/Envelope.java#L429)).

## 6. Code path

### 6a. Allow path → object creation

1. [`processFirstFrameOfLargeMessage():551`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/transport/CQLMessageHandler.java#L551) — the size is within the limit
2. [`processFirstFrameOfLargeMessage():559`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/transport/CQLMessageHandler.java#L559) / [`:605`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/transport/CQLMessageHandler.java#L605) — capacity is acquired from the endpoint and global reserves (throwing or backpressure mode)
3. [`LargeMessage.onIntactFrame():572`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/net/AbstractMessageHandler.java#L572) — each frame's bytes are sliced and kept in `buffers`
4. [`LargeMessage.assembleFrame():762`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/transport/CQLMessageHandler.java#L762) — on completion the buffers are wrapped as the request body

### 6b. Disallow path effect

The first frame (already in memory) is consumed. Each later frame is read off the channel and released at once, with no capacity acquired, so retained bytes stay at about one frame at a time. The client then gets an error. The connection stays open and keeps working.

## 7. Object & resource

| Field | Content |
|-------|---------|
| **Object created** | the retained frame buffers of one large request |
| **Resource consumed** | off-heap bytes from the networking buffer pool, until the request is processed and released |
| **Rough sizing** | about the request's declared size per accepted large request in progress |
| **Lifetime / release** | released when the request finishes ([`onComplete():824`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/transport/CQLMessageHandler.java#L824) for the discard branch, request completion otherwise) |

## 8. Maximum memory/disk bound

Per request, the retained bytes are at most the limit (a request above it retains almost nothing). The node-wide figure is the limit times the number of large requests being received at once, and that count is itself held down by the byte budget (`native_transport_max_request_data_in_flight`, the receive-queue capacity). So the limit sets the per-request ceiling and the byte budget sets the total. The rejection says this is a sanity check on one message, not a cap on retained memory; §9 tests which description fits the measured bytes.

**Stage-4 result (2026-10-20, [results file](../../stage4-runtime-verification/results/native_transport_max_message_size-processFirstFrameOfLargeMessage-maxMessageSize--guided.md)):** the per-request description fits; the rejection's does not (§9a row 2, Refuted at both tiers). One 8 MiB v5 request held before its last frame kept 8,389,184 B (64 frame stashes of 131,081 B) at 16 MiB and 0 B at 4 and 1 MiB, where it was refused at its first frame and every later frame was released at once. The operand is the envelope's body size (`CQLMessageHandler.java:534`), not body plus header as §4 says: a body of exactly the limit is admitted, one byte more is refused.

## 9. Test design (guidance for stage 4)

**Stage 3 writes this section; stage 3 never runs it.** No measured numbers and no verdict are recorded here.

### 9a. Procedure and conclusions

**Testability:** config, restart-only. Multi-frame requests need native protocol v5; the harness uses a raw v5 client.

**Claim under test (the rejection):** `native_transport_max_message_size` does not bound the memory held for a large request: the bytes the server retains while it receives a large request do not depend on the knob.

**How this verifies the hypothesis:**

- **Hypothesis:** the check is a sanity bound on declared size, so retained bytes for a request in progress are the same whatever the knob.
- **Test:** vary the knob over 1 MiB, 4 MiB and 16 MiB (the default on a stock `max_mutation_size`); send one large request of 8 MiB and hold it open after sending all but its last frame; read the networking pool's retained bytes.
- **Logic:** (1) the pool's retained bytes rise for the request (else the run is invalid); (2) read retained bytes at each knob value; (3) a positive control lowers the receive-queue capacity, a byte budget known to bind on this path; (4) the claim is confirmed only if retained bytes are the same across the knob values while the control moves them.
- **Refuted if:** retained bytes drop to about one frame when the knob is below the request size, and equal the request size when it is above.

**Procedure:**

1. **Unit tier** — drive `CQLMessageHandler`'s large-message path with a test frame decoder: feed the first frame of a request whose declared size is above, at and below the limit, then the remaining frames; read the `LargeMessage`'s retained buffer count and bytes and the `RequestDiscarded` metric.
2. **Cluster tier** — one node, three restarts (one per knob value); a raw v5 client sends all but the last frame of an 8 MiB request and waits; read the pool's retained bytes; then send the last frame and read the response.
3. **Positive control** — at the 16 MiB value, set `native_transport_receive_queue_capacity` to 2 MiB (restart) and repeat; the held request must stall or be refused. **Replaced 2026-10-20 (R1, see 9f): this control does not bind a multi-frame request; use the two-request reserves control in 9f.**
4. **Compare** with the prediction.

**Prediction (what the rejection claims):** retained bytes while the request is held are about 8 MiB at every knob value; the response is an oversized error at 1 MiB and 4 MiB and success at 16 MiB; the positive control lowers retention.

**Conclusions:**

| Result | Conclusion |
|---|---|
| Retained bytes are about the request size at every value, and the control lowers them | **Confirmed** — the knob does not bound retained memory. |
| Retained bytes are about one frame at 1 MiB and 4 MiB and about 8 MiB at 16 MiB | **Refuted** — retained memory follows the knob, per request. |
| Retained bytes are about one frame at every value | **Not confirmed** — the knob is not the reason; look at `native_transport_max_frame_size` or another cap. |
| The pool does not rise for the held request | **Invalid run** — the client did not hold a v5 large request; fix the client. |
| The control does not change retention | **Not confirmed** — the instrument cannot see a cap that binds. |

### 9b. Setup

| Field | Content |
|-------|---------|
| **Constraint knob** | yaml `native_transport_max_message_size: <n>MiB` (restart). It may not exceed either in-flight limit; raise `native_transport_max_request_data_in_flight` and `…_per_ip` to 256 MiB so the values 1, 4 and 16 MiB are accepted. |
| **Confirm it took effect** | the startup config dump, and a client request above the limit returning "CQL Message of size … exceeds allowed maximum of …" ([`buildOversizedCQLMessageException():847`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/transport/CQLMessageHandler.java#L847)) |
| **Capacity values** | 1 MiB, 4 MiB, 16 MiB. |
| **Scope** | Per request; node-wide use is `limit × concurrent large requests`. Send one request at a time. |
| **Level** | Unit and cluster. |

**Hold fixed:**

| Setting | Value | Why |
|---|---|---|
| `native_transport_receive_queue_capacity` | 128 MiB except in the control | keeps the byte budget from binding first |
| `native_transport_throw_on_overload` | false (default) | the mode where the large request is buffered |
| protocol | native v5, one connection | the check is in the v5 large-message path |
| request | a prepared INSERT with one 8 MiB blob parameter | larger than `LARGE_MESSAGE_THRESHOLD`, below `max_mutation_size` |

**Controls:** an idle node (pool baseline); a request of 64 KiB (single-frame path, not subject to the check).

**Reset between runs:** stop the node; restart with the next value.

### 9c. Workload

```bash
# raw v5 client: send frames 1..N-1 of an 8 MiB request, hold 30 s, then send frame N
python3 harness/hold_large_request.py --size-mib 8 --hold-s 30
```

### 9d. Observables

| Observable | How to read it | When to sample | Trap |
|---|---|---|---|
| **Retained bytes** — usage side | JMX `org.apache.cassandra.metrics:type=BufferPool,scope=networking,name=Size`, minus the baseline | at 5 s of the hold | Netty read buffers share the same wrapper class; take the baseline with the connection open and idle. |
| **Disallow evidence** | JMX `ClientMetrics` `RequestDiscarded` increments; the client's oversized error | at the end of the hold | Overload paths also increment `RequestDiscarded`; the error text tells them apart. |
| **Real resource** | `RssAnon` and direct-memory use of the process (`jcmd <pid> VM.native_memory`) | at 5 s of the hold | RSS is coarse; use it only as a cross-check. |

### 9e. Running the scenarios

1. **Control run** — idle connection, then a 64 KiB request; record pool baseline and response.
2. **Scenario A — knob at 16 MiB** — hold the 8 MiB request; record retained bytes and the response.
3. **Scenario B — knob at 4 MiB and 1 MiB** — restart and repeat.
4. **Scenario C — positive control** — knob 16 MiB, receive-queue capacity 2 MiB; repeat. **Replaced 2026-10-20 (R1): run the two-request arms of 9f.**

### 9f. Stage-4 audit amendments (2026-10-20)

Made at the step-0 audit, before any run or reading; each is a dated change that leaves the claim, the prediction and the conclusions table as filed (results file §1.1 gives the reason for each). Where one corrects a number or a procedure above, this block governs.

- **R1 (9a procedure 3, 9e scenario C: the positive control).** The filed control (`native_transport_receive_queue_capacity` 2 MiB, reserves 256 MiB) does not bind: `AbstractMessageHandler` borrows from the endpoint and global reserves only the part of a request beyond the connection's own capacity, and a multi-frame request is held to the reserves (closed `native_transport_receive_queue_capacity` results, part 3 and unit step u4), which at 256 MiB are far above one 8 MiB request. Replace it with two arms that differ only in the reserves, both at knob 12 MiB and with two connections from one address, each sending all but the last frame of an 8 MiB request and holding:
  - **reference arm:** `native_transport_max_request_data_in_flight` and `…_per_ip` 256 MiB, `native_transport_receive_queue_capacity` 128 MiB. Expected retained bytes: about 16 MiB (both requests).
  - **control arm:** both in-flight limits 12 MiB, `native_transport_receive_queue_capacity` 1 MiB (the default). Each request borrows 7 MiB from the reserves, so the second cannot be admitted (14 MiB > 12 MiB) and waits at its first frame. Expected retained bytes: about 8 MiB plus at most one frame.
  The 12 MiB knob satisfies the startup rule (it may not exceed either in-flight limit) and both 8 MiB requests are in the allowed branch, so the knob is not what differs. The conclusions rows are unchanged: the control must lower retention, else "Not confirmed".
- **R2 (9a: tolerances).** "About 8 MiB" means 6 to 10 MiB over the baseline taken with the connection idle; "about one frame" means at most 1 MiB over that baseline (a frame is at most 128 KiB, `FrameEncoder.Payload.MAX_SIZE`).

## 10. Provenance

| Field | Content |
|--------|---------|
| **Estimate** | `negative` |
| **Ground** | recorded ground: not a running-total capacity check (`predicted-negative.md`) |
| **Autonomous reference** | none |
| **Stage-3 feed** | 3b (found by reading the native-transport package; recorded in `predicted-negative.md`) |
| **Filed by / Date** | guided agent session, 2026-10-19 |
| **Line numbers checked** | 2026-10-19 against `cassandra-5.0.9` |
| **Escape hatch / Target-3 note** | single-frame requests and protocol v4 are outside this check (§5); a request just under the limit still occupies up to the limit |
| **Stage-4 feedback** | **2026-10-20 — unit Refuted, cluster Refuted** (§9a row 2: retained memory follows the knob, per request), [results file](../../stage4-runtime-verification/results/native_transport_max_message_size-processFirstFrameOfLargeMessage-maxMessageSize--guided.md), run 1 on `pc06`, not committed. Unit: the server's `LargeMessage` kept 0 · 0 · 8,388,544 B of an 8 MiB request at 1 · 4 · 16 MiB; boundary exact at three limits (body *L* kept every frame, *L* + 1 kept none, `RequestDiscarded` +1, error 8704). Cluster: networking-pool `Size` 5 s into a 30 s hold rose 0 · 0 · 8,389,184 B at 1 · 4 · 16 MiB (8,389,184 B at the derived default), all overflow frame stashes, equal to the per-frame Byteman trace; the 9f R1 control lowered two held requests from 16.001 MiB (reserves 256 MiB) to 8.251 MiB (reserves 12 MiB, the second paused at its first frame). Missed sub-prediction (R1): the control held 8 MiB + 2 frame stashes, not + at most one. **The source reading in Notes is borne out: the check gates the buffering of every frame after the first; the negative estimate in `predicted-negative.md` should be reversed by stage 3.** Correction to §4: the operand is the body size (`header.bodySizeInBytes`, `CQLMessageHandler.java:534`), without the 9-byte header. Seen again: an admitted large request's stash accounting is never returned (`OverflowSize` stayed +8,389,184 B; the `networking_cache_size` arm-L leak). No run 2. |
| **Notes** | **The write-up's source reading disagrees with the recorded rejection.** The check does gate buffer allocation: the disallow branch consumes frames without keeping them ([`onIntactFrame():799`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/transport/CQLMessageHandler.java#L799), with the comment about not consuming memory), the allow branch keeps them. That is a per-request bound whose disallow outcome avoids the allocation, the same shape as the qualified `max_mutation_size` (pattern (c)/(b)). I have **kept the recorded judgment** and written the opposite-claim test; a refutation at stage 4 would confirm the reading and is the route for reversing the entry. Pilot of the rejected-entry write-up. |

---

## 11. Notes

- `predicted-negative.md` says "Rejects a single oversized frame outright"; the code rejects a multi-frame *request* by declared size, after the first frame, and keeps draining the rest.
