# native_transport_queue_max_item_age_threshold — queued CQL request

> **Index:** [../_INDEX.md](../_INDEX.md)
>
> **Source:** apache/cassandra @ tag `cassandra-5.0.9`

**Estimate: negative** (Rule 2, recorded in `predicted-negative.md`, batch "the capacity-word pass": time-based — the age of the oldest queued item — not a byte or capacity comparison). This file writes the negative estimate up with a test of the opposite claim: that `native_transport_queue_max_item_age_threshold` does **not** bound the memory held by queued client requests.

## 1. Location

| Field | Content |
|-------|---------|
| **Case ID** | NATIVE_TRANSPORT_QUEUE_MAX_ITEM_AGE_THRESHOLD-HASQUEUECAPACITY-OLDESTTASKQUEUETIME |
| **Constraint** | `native_transport_queue_max_item_age_threshold` — configuration entry (`cassandra.yaml`, a multiple of `native_transport_timeout`; default `Double.MAX_VALUE`, i.e. off), live-settable (JMX `setNativeTransportQueueMaxItemAgeThreshold`) |
| **Enforcement pattern** | (b) the check returns a verdict (`false` = no queue capacity) that the message handlers read |
| **Capacity check** | [`Dispatcher.hasQueueCapacity():348`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/transport/Dispatcher.java#L348) — `requestExecutor.oldestTaskQueueTime() < timeout × threshold` |
| **Decision point** | [`CQLMessageHandler.processOneContainedMessage():208`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/transport/CQLMessageHandler.java#L208) (throwing mode) and [`:237`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/transport/CQLMessageHandler.java#L237) (backpressure mode); the large-message twins at [`:585`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/transport/CQLMessageHandler.java#L585) and [`:618`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/transport/CQLMessageHandler.java#L618); the pre-v5 twins at [`PreV5Handlers:165`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/transport/PreV5Handlers.java#L165) and [`:201`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/transport/PreV5Handlers.java#L201) |
| **Allocation site** | enqueueing the request for execution: `processRequest` hands it to the dispatcher's executor, [`CQLMessageHandler.processRequest():385`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/transport/CQLMessageHandler.java#L385) |
| **Related cases** | [`native_transport_receive_queue_capacity…`](native_transport_receive_queue_capacity-acquireCapacity-queueCapacity--guided.md) (the byte budget on the same queue; the positive control) |

```java
public boolean hasQueueCapacity()
{
    double threshold = DatabaseDescriptor.getNativeTransportQueueMaxItemAgeThreshold();
    if (threshold <= 0)
        return true;
    return requestExecutor.oldestTaskQueueTime() < (DatabaseDescriptor.getNativeTransportTimeout(TimeUnit.NANOSECONDS) * threshold);
}
```

## 2. Context

Client requests wait in a queue for a worker thread. If workers fall behind, the queue grows and requests wait longer than the client would. This check looks at how long the oldest queued request has waited, and when it exceeds a share of the request timeout the server stops taking more work: it answers with an overload error, or pauses the connection, depending on the connection's mode. It protects latency; whether it also protects memory is what is in question.

## 3. Module

| Field | Content |
|-------|---------|
| **Module** | native transport — request dispatch (`transport`) |
| **One-line role** | Reads client requests, queues them for execution and sheds or delays them under overload. |

## 4. Capacity check & limit

| Field | Content |
|-------|---------|
| **Is this a capacity check?** | partial — a time (age of the head of the queue) against a time limit; the queue's bytes are not compared |
| **Usage-side operand** | `requestExecutor.oldestTaskQueueTime()` — nanoseconds since the oldest queued task was created ([`SEPExecutor.oldestTaskQueueTime():88`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/concurrent/SEPExecutor.java#L88)) |
| **Limit-side operand** | `native_transport_timeout × native_transport_queue_max_item_age_threshold` |
| **Limit type** | Derived from two configuration entries |

**Limit initialization path:**

1. [`Config.native_transport_queue_max_item_age_threshold:1394`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/Config.java#L1394) — declared, `Double.MAX_VALUE`
2. [`Config.native_transport_timeout:1399`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/Config.java#L1399) — declared, `12s`
3. [`getNativeTransportQueueMaxItemAgeThreshold():2312`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/DatabaseDescriptor.java#L2312) and the live setter [`setNativeTransportMaxQueueItemAgeThreshold():2317`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/DatabaseDescriptor.java#L2317), reached via [`StorageService.setNativeTransportQueueMaxItemAgeThreshold():7638`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/service/StorageService.java#L7638)
4. [`hasQueueCapacity():348`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/transport/Dispatcher.java#L348) — read at the comparison; `threshold <= 0` returns true (the check off)

## 5. Decision point & branch semantics

| Field | Content |
|-------|---------|
| **Decision point** | [`CQLMessageHandler:208`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/transport/CQLMessageHandler.java#L208), :237, :585, :618 and [`PreV5Handlers:165`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/transport/PreV5Handlers.java#L165), :201 |
| **Verdict** | `hasQueueCapacity()` returning `false`, read as `Overload.QUEUE_TIME` ([`Overload:48`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/transport/ClientResourceLimits.java#L48)) |

| Outcome | Condition | Effect |
|---------|-----------|--------|
| **Allow** | head-of-queue age below the limit (or the threshold off) | the request is queued and run |
| **Disallow, throwing mode** | age at or above the limit, `native_transport_throw_on_overload` true | the request's bytes are released and an overloaded error is returned ([`discardAndThrow():215`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/transport/CQLMessageHandler.java#L215)) |
| **Disallow, default mode** | age at or above the limit | the connection is paused for a back-off (`native_transport_min_backoff_on_queue_overload`, [`:1395`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/Config.java#L1395)); the request is still processed ([`CQLMessageHandler.java:237-245`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/transport/CQLMessageHandler.java#L237-L245)) |

## 6. Code path

### 6a. Allow path → object creation

1. [`hasQueueCapacity():348`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/transport/Dispatcher.java#L348) — true
2. [`processRequest():385`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/transport/CQLMessageHandler.java#L385) — the request envelope is handed to the dispatcher
3. the dispatcher's executor holds the request (and its body buffer) until a worker runs it

### 6b. Disallow path effect

In throwing mode the request is discarded and the bytes counted against the in-flight budget are released, so the queue stops growing at the cost of dropped requests. In default mode nothing is dropped: the connection is paused for a short back-off, then reads again, so the queue keeps growing at a reduced rate. Whether queued bytes stop growing is mode-dependent.

## 7. Object & resource

| Field | Content |
|-------|---------|
| **Object created** | a queued request: the envelope, its body buffer (off-heap from the networking pool) and the task wrapper |
| **Resource consumed** | off-heap bytes for the body, plus a small heap object |
| **Rough sizing** | about the request's body size per queued request |
| **Lifetime / release** | until a worker runs the request and releases it |

## 8. Maximum memory/disk bound

A time limit on the head of the queue bounds how long a request waits, not how many bytes queue behind it. Bytes queued ≈ arrival rate × request size × wait time, so with a finite threshold the queue's bytes are limited by `rate × size × timeout × threshold` in throwing mode (arrivals are refused after that wait) and are only slowed in default mode. The byte budget (`native_transport_max_request_data_in_flight`) bounds the same bytes independently. The rejection says the time check is not a byte limit; §9 measures whether queued bytes nevertheless follow it.

## 9. Test design (guidance for stage 4)

**Stage 3 writes this section; stage 3 never runs it.** No measured numbers and no verdict are recorded here.

### 9a. Procedure and conclusions

**Testability:** config, live-settable (JMX `StorageService.setNativeTransportQueueMaxItemAgeThreshold`).

**Claim under test (the rejection):** the queue-age threshold does not bound the memory held by queued requests: with workers stalled, peak queued request bytes are the same at every threshold value.

**How this verifies the hypothesis:**

- **Hypothesis:** the check compares time, not bytes, so queued bytes do not follow the threshold.
- **Test:** stall the request workers (a Byteman delay in `Dispatcher` request processing), send 64 KiB requests at a fixed rate for 60 s with the in-flight byte budget set high, in throwing mode; vary the threshold over off (default), 0.5, 0.1 and 0.02 (6 s, 1.2 s and 0.24 s of the 12 s timeout); read peak queued bytes and the number refused.
- **Logic:** (1) with the check off, queued bytes grow for the whole run (else the run is invalid); (2) read peak queued bytes at each threshold; (3) a positive control lowers `native_transport_max_request_data_in_flight` and must cap queued bytes at its value; (4) the claim is confirmed only if peak queued bytes do not fall with the threshold while the control moves them.
- **Refuted if:** peak queued bytes fall with the threshold (about `rate × size × timeout × threshold`).

**Procedure:**

1. **Unit tier** — build a `Dispatcher` over a request executor whose workers are held; enqueue requests of known size; call `hasQueueCapacity()` as the head ages across the limit, at thresholds above, at and below the head's age, and read the return value and the number of queued bytes.
2. **Cluster tier** — one node with a Byteman delay in request processing; a client sends at a fixed rate; per threshold, read queued bytes and refusals (9e).
3. **Positive control** — threshold off, `native_transport_max_request_data_in_flight` set to 8 MiB; the queue must stop at about 8 MiB.
4. **Compare** with the prediction.

**Prediction (what the rejection claims):** with workers stalled, peak queued request bytes are the same at every threshold and exceed the budget-free total of the run; requests are refused once the head's age passes the limit, but the bytes already queued stay; the control caps queued bytes at 8 MiB.

**Conclusions:**

| Result | Conclusion |
|---|---|
| Peak queued bytes are the same across thresholds, and the control caps them | **Confirmed** — the age threshold does not bound queued memory. |
| Peak queued bytes fall as the threshold falls, near `rate × size × timeout × threshold` | **Refuted** — usage follows the constraint; the time check bounds bytes indirectly. |
| Peak queued bytes fall with the threshold only in throwing mode | **Refuted for throwing mode**, confirmed for default mode; report both modes' slopes. |
| Queued bytes never grow with the check off | **Invalid run** — the workers were not stalled; fix the delay. |
| The control does not cap queued bytes | **Not confirmed** — the instrument cannot see a cap that binds. |

### 9b. Setup

| Field | Content |
|-------|---------|
| **Constraint knob** | JMX `StorageService.setNativeTransportQueueMaxItemAgeThreshold(<double>)` (live); yaml `native_transport_queue_max_item_age_threshold` (restart). |
| **Confirm it took effect** | `getNativeTransportQueueMaxItemAgeThreshold` over JMX. |
| **Capacity values** | `Double.MAX_VALUE` (default, off), 0.5, 0.1, 0.02 (multiples of `native_transport_timeout`). |
| **Scope** | Node-wide, one dispatcher; the multiplier is the arrival rate. |
| **Level** | Unit and cluster. |

**Hold fixed:**

| Setting | Value | Why |
|---|---|---|
| `native_transport_timeout` | 12 s (default) | the threshold is a multiple of it |
| `native_transport_throw_on_overload` | true for the main sweep; repeat once with false | the two modes differ (§6b) |
| `native_transport_max_request_data_in_flight`, `…_per_ip` | 1 GiB | keeps the byte budget from binding except in the control |
| `native_transport_max_threads` | 4 | a small worker pool that the delay can stall |
| request | a prepared INSERT with a 64 KiB blob, 100 requests/s for 60 s | about 384 MiB offered per run, a fixed load |
| client timeout | 120 s | the client must not give up first |

**Controls:** an idle node; the check off with the workers stalled (the unbounded baseline); the positive control.

**Reset between runs:** stop the node, restart, remove the Byteman rule.

### 9c. Workload

```bash
# cluster tier: fixed-rate writer, 64 KiB values; Byteman holds request processing for the run
python3 harness/fixed_rate_writer.py --rate 100 --size-kib 64 --duration-s 60 --out <log>
```

### 9d. Observables

| Observable | How to read it | When to sample | Trap |
|---|---|---|---|
| **Queued bytes** — the real resource | JMX `org.apache.cassandra.metrics:type=Client,…` request-bytes-in-flight gauge, or the pool gauge `BufferPool,scope=networking,name=Size` minus the baseline | every 2 s | In-flight bytes also count requests being run; with workers stalled they equal queued bytes. |
| **Queue age** — the check's operand | a Byteman line at `Dispatcher.hasQueueCapacity` logging the age and the return | every call | The call is on the netty thread; keep the rule cheap. |
| **Disallow evidence** | the overloaded error at the client; `ClientMetrics` `RequestDiscarded` and the log line from `logOverload` | continuous | Byte-budget overloads share the counter; the error text names the cause (queue time). |
| **Refusals** | client log, one line per request | continuous | Pair with the age lines to see the first refusal. |

### 9e. Running the scenarios

1. **Control run** — idle node; record the pool baseline.
2. **Scenario A — check off** — stall the workers, send for 60 s; queued bytes should grow without bound.
3. **Scenario B — vary the threshold** — repeat at 0.5, 0.1 and 0.02, then once in default (non-throwing) mode at 0.1.
4. **Scenario C — positive control** — check off, in-flight budget 8 MiB; repeat.

### 9f. Stage-4 audit amendments (2026-10-20)

Made at the step-0 audit, before any run or reading; each is a dated change that leaves the claim, the prediction and the conclusions table as filed (results file §1.1 gives the reason for each). Where one corrects a number or a procedure above, this block governs.

- **R1 (9d: queued bytes).** The "request-bytes-in-flight gauge" is `org.apache.cassandra.metrics:type=Client,name=RequestsSize` (`ClientMetrics.java:129`, backed by `ClientResourceLimits.getCurrentGlobalUsage`). Read it every 2 s together with the networking pool `Size` gauge.
- **R2 (9b, 9c: the stall).** The Byteman rule holds `org.apache.cassandra.transport.Dispatcher$RequestProcessor.run` (`Dispatcher.java:304`) at entry until a flag file appears, with `native_transport_max_threads` 4, so four requests run (stalled) and the rest wait in the executor queue. `oldestTaskQueueTime` reads only the head of that queue (`SEPExecutor.java:88-100`), not running tasks, so the check has an age to read once a fifth request is queued. Write and check the rule in step 1.
- **R3 (9b: mode).** Set `native_transport_throw_on_overload` in the yaml as the connection default (`Config.java:1393`; `PipelineConfigurator.java:309-313` uses it when the client's STARTUP option is absent): true for the main sweep, false for the single repeat at 0.1.
- **R4 (9a: criteria).** The noise band is the range of the peak queued bytes over three repeats of the check-off arm. "The same" means the peaks at 0.5, 0.1 and 0.02 are within that band of the check-off peak; "fall with the threshold" means the peak at 0.02 is more than 50 % below the check-off peak and more than three times the band below it. With the workers stalled and nothing completing, the check-off peak is expected near the offered 375 MiB.

## 10. Provenance

| Field | Content |
|--------|---------|
| **Estimate** | `negative` |
| **Ground** | Rule 2: a time-based check, not a byte or capacity comparison (`predicted-negative.md`, batch "the capacity-word pass") |
| **Autonomous reference** | none |
| **Stage-3 feed** | 3b (recorded in `predicted-negative.md`) |
| **Filed by / Date** | guided agent session, 2026-10-19 |
| **Line numbers checked** | 2026-10-19 against `cassandra-5.0.9` |
| **Escape hatch / Target-3 note** | default is off (`Double.MAX_VALUE`); in default (non-throwing) mode the check only delays reads (§6b) |
| **Stage-4 feedback** | **2026-10-20, run 1 on `pc13` (results [`../../stage4-runtime-verification/results/native_transport_queue_max_item_age_threshold-hasQueueCapacity-oldestTaskQueueTime--guided.md`](../../stage4-runtime-verification/results/native_transport_queue_max_item_age_threshold-hasQueueCapacity-oldestTaskQueueTime--guided.md)): Refuted at both tiers (§9a row 2) — Effect: caps in throwing mode, only slows growth in default mode; not committed.** With the 4 workers stalled and 100 × 64 KiB req/s for 60 s, peak `RequestsSize` was 392.5 MB at threshold off (three repeats, band 0) and 38.6 / 7.15 / 0.85 MB at 0.5 / 0.1 / 0.02; admitted = 5 + rate × timeout × threshold to the request (605 / 125 / 29; unit 125 / 35 / 11), i.e. §8's `rate × size × timeout × threshold` holds in throwing mode and Rule 2's "time-based, not bytes" ground was too strong for this site, as the Notes row predicted. Default mode at 0.1 refuses nothing and pauses the connection for a back-off that saturates at `native_transport_max_backoff_on_queue_overload` (200 ms), so the queue still grew linearly at 5 req/s (33.3 MB after 60 s) — slowed about 20×, not bounded. Positive control (in-flight 8 MiB) capped `RequestsSize` at 8,331,080 B. Corrections for §7/§9d (not applied to §9, which is frozen): the queued bytes are on the **heap** (decoded values, 65,821 B of `byte[]` per 65,592-B request), not in the networking pool, whose `Size` stayed 8 MiB with `UsedSize` 0, so R1's pool gauge cannot see them; `RequestsSize` is the global reserve only and reads 1 MiB (the per-connection `native_transport_receive_queue_capacity`) under the queued bytes; `logOverload` is a TRACE line, not visible at the default level; the hold at `RequestProcessor.run` entry is not cut by the 12 s `native_transport_timeout` (the requests answer "Query timed out before it could start" after the release). |
| **Notes** | Source reading predicts **Refuted in throwing mode**: refusing arrivals once the head ages out caps queued bytes at about `rate × size × timeout × threshold`. The time check then bounds memory indirectly, and Rule 2's "time-based, not bytes" ground would be too strong. In default mode the check delays but drops nothing, so the conclusion may differ by mode; the sweep records both. Pilot of the rejected-entry write-up. |

---

## 11. Notes

- The earlier `predicted-negative.md` entry cites `Dispatcher.java:345`; the method is at line 348 in the pinned tree (the entry's line has drifted by 3).
