# MAX_HINT_BUFFERS — hintsbuffer

> **Index:** [../_INDEX.md](../_INDEX.md)
>
> **Source:** apache/cassandra @ tag `cassandra-5.0.9`

## 1. Location

| Field | Content |
|-------|---------|
| **Case ID** | MAX_HINT_BUFFERS-SWITCHCURRENTBUFFER-MAX_ALLOCATED_BUFFERS |
| **Constraint** | `MAX_HINT_BUFFERS` — JVM system property (`CassandraRelevantProperties`) |
| **Enforcement pattern** | (a) — the capacity check is the decision |
| **Capacity check** | [`HintsBufferPool.switchCurrentBuffer():113`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/hints/HintsBufferPool.java#L113) |
| **Decision point** | the same statement, [`HintsBufferPool.switchCurrentBuffer():113`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/hints/HintsBufferPool.java#L113) — the disallow branch blocks on `reserveBuffers.take()` (line 118) |
| **Allocation site** | [`HintsBufferPool.createBuffer():130-134`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/hints/HintsBufferPool.java#L130-L134) → `HintsBuffer.create()` (`ByteBuffer.allocateDirect(slabSize)`) |
| **Related cases** | none |

```java
private synchronized boolean switchCurrentBuffer(HintsBuffer previous)
{
    if (currentBuffer != previous)
        return false;

    HintsBuffer buffer = reserveBuffers.poll();
    if (buffer == null && allocatedBuffers >= MAX_ALLOCATED_BUFFERS)
    {
        try
        {
            //This BlockingQueue.take is a target for byteman in HintsBufferPoolTest
            buffer = reserveBuffers.take();
        }
        catch (InterruptedException e)
        {
            throw new UncheckedInterruptedException(e);
        }
    }
    currentBuffer = buffer == null ? createBuffer() : buffer;

    return true;
}
```

## 2. Context

When a node can't immediately deliver a write to a target replica (e.g. it's
down), Cassandra stashes the write as a "hint" and buffers it in memory
before flushing it to disk. Hints for all destinations share one small pool
of fixed-size off-heap buffers: one buffer is actively being written to at
any time, and when it fills up, the pool needs to hand the writer a fresh
buffer to keep going. Without a cap, a burst of hint writes arriving faster
than buffers can be flushed to disk would make the pool keep manufacturing
brand-new off-heap buffers indefinitely, growing native memory usage without
bound. This check caps how many buffers the pool is allowed to have
allocated at once — once the cap is hit, a writer needing a new buffer must
instead wait for a previously-flushed buffer to be recycled back into the
pool, rather than getting a new allocation.

## 3. Module

| Field | Content |
|-------|---------|
| **Module** | hints — hint buffering and dispatch (`hints/`) |
| **One-line role** | Buffers and later delivers writes destined for replicas that are temporarily unreachable. |

## 4. Capacity check & limit

| Field | Content |
|-------|---------|
| **Is this a capacity check?** | Yes — compares the count of buffers already allocated (`allocatedBuffers`) against a fixed cap (`MAX_ALLOCATED_BUFFERS`) before permitting another buffer to be created. |
| **Usage-side operand** | `allocatedBuffers` — an `int` field incremented each time `createBuffer()` actually allocates a new `HintsBuffer` (never decremented — it counts cumulative buffers ever created, not buffers currently live). |
| **Limit-side operand** | `MAX_ALLOCATED_BUFFERS` — a `static final int` field on `HintsBufferPool`. |
| **Limit type** | JVM system property (`cassandra.MAX_HINT_BUFFERS`), not a `cassandra.yaml` setting, defaulting to `3`. |

**Limit initialization path** (declare → configure/derive → store → read at the check):

1. [`CassandraRelevantProperties.MAX_HINT_BUFFERS`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/CassandraRelevantProperties.java#L351) — declared as the system property `cassandra.MAX_HINT_BUFFERS`, default value `"3"`.
2. [`HintsBufferPool.MAX_ALLOCATED_BUFFERS`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/hints/HintsBufferPool.java#L41) — read once via `MAX_HINT_BUFFERS.getInt()` and stored as a `static final int` at class-init time (so it's effectively fixed for the JVM's lifetime, though externally configurable via `-Dcassandra.MAX_HINT_BUFFERS=<n>` at startup).
3. [`HintsBufferPool.switchCurrentBuffer():113`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/hints/HintsBufferPool.java#L113) — read directly at the comparison point (no intermediate config object; the static field is referenced in place).

## 5. Decision point & branch semantics

| Field | Content |
|-------|---------|
| **Decision point** | the same statement, [`HintsBufferPool.switchCurrentBuffer():113`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/hints/HintsBufferPool.java#L113) — the disallow branch blocks on `reserveBuffers.take()` (line 118) |
| **Verdict** | n/a — pattern (a): the check is the decision. |

| Branch | Condition | Effect |
|--------|-----------|--------|
| **Allow** | `buffer == null && allocatedBuffers < MAX_ALLOCATED_BUFFERS` (i.e. no reserve buffer was available, but the cap hasn't been hit) — falls through the `if` without entering it | `currentBuffer = createBuffer()`: a brand-new `HintsBuffer` is allocated |
| **Disallow** | `buffer == null && allocatedBuffers >= MAX_ALLOCATED_BUFFERS` | Blocks the calling thread on `reserveBuffers.take()` until some other thread returns a recycled buffer via `offer()`; no new buffer is allocated |

```java
// allow-branch (the "if" is skipped; falls through to)
currentBuffer = buffer == null ? createBuffer() : buffer;
```

```java
// disallow-branch body
try
{
    //This BlockingQueue.take is a target for byteman in HintsBufferPoolTest
    buffer = reserveBuffers.take();
}
catch (InterruptedException e)
{
    throw new UncheckedInterruptedException(e);
}
```

## 6. Code path

### 6a. Allow branch → object creation

1. [`HintsBufferPool.allocate():68-84`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/hints/HintsBufferPool.java#L68-L84) — `current.allocate(hintSize)` on the current buffer returns `null` (buffer full), so `switchCurrentBuffer(current)` is invoked.
2. [`HintsBufferPool.switchCurrentBuffer():112`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/hints/HintsBufferPool.java#L112) — `reserveBuffers.poll()` returns `null` (no recycled buffer waiting) and `allocatedBuffers < MAX_ALLOCATED_BUFFERS`, so the `if` at line 113 is **not** entered.
3. [`HintsBufferPool.switchCurrentBuffer():125`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/hints/HintsBufferPool.java#L125) — `currentBuffer = buffer == null ? createBuffer() : buffer` calls `createBuffer()`.
4. [`HintsBufferPool.createBuffer():130-134`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/hints/HintsBufferPool.java#L130-L134) — `allocatedBuffers++`, then **object creation**: `HintsBuffer.create(bufferSize)`.
5. [`HintsBuffer.create():75-78`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/hints/HintsBuffer.java#L75-L78) — `return new HintsBuffer(ByteBuffer.allocateDirect(slabSize))`: an off-heap direct `ByteBuffer` of `bufferSize` bytes is allocated.
6. [`HintsBufferPool.allocate():82`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/hints/HintsBufferPool.java#L82) — the loop retries `current.allocate(hintSize)` against the freshly-created buffer.

### 6b. Disallow branch effect

This is a **block-and-wait**, not a reject or drop — the write is never discarded, just delayed.

1. [`HintsBufferPool.switchCurrentBuffer():118`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/hints/HintsBufferPool.java#L118) — the calling thread (the hint-writing thread, holding `HintsBufferPool`'s monitor via `synchronized`) parks on `reserveBuffers.take()`, blocking until another thread calls `offer()`.
2. [`HintsBufferPool.offer():86-90`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/hints/HintsBufferPool.java#L86-L90) — a *different* code path (the flush machinery, after a buffer has been written to disk and recycled) calls `offer(buffer)`, which pushes a reused `HintsBuffer` onto `reserveBuffers`, unblocking the waiting `take()`.
3. Back in `switchCurrentBuffer():125` — since `buffer` is now non-null (the recycled one), `createBuffer()` is **not** called: no new allocation happens; the existing buffer is reused as `currentBuffer` instead.
4. No escape hatch was found in this path — unlike the memtable cases' `markBlocking()`, there is no alternate route that lets a caller bypass this wait and force a new buffer allocation past the cap. (Established by reading the call paths, not by runtime tracing.)

## 7. Object & resource

| Field | Content |
|-------|---------|
| **Object created** | `HintsBuffer`, wrapping a direct (off-heap) `java.nio.ByteBuffer` |
| **Resource consumed** | Off-heap/native memory — `ByteBuffer.allocateDirect(bufferSize)` |
| **Rough sizing** | `bufferSize = Math.max(DatabaseDescriptor.getMaxMutationSize() * 2, MIN_BUFFER_SIZE)`, fixed for the pool's lifetime (see [`HintsService.java:109-110`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/hints/HintsService.java#L109-L110)) — so each buffer's size is derivable from `max_mutation_size` config, and total bytes = `bufferSize × (number of buffers allocated)`. |
| **Lifetime / release** | A buffer isn't freed when replaced as `currentBuffer` — it's handed to `flushCallback.flush()` (writes it to the hints file on disk), then recycled back into `reserveBuffers` via `offer()` for reuse, rather than being garbage-collected/deallocated. `allocatedBuffers` itself is never decremented, so it tracks the high-water mark of buffers ever created, not buffers currently alive. |

## 8. Maximum memory bound

`MAX_ALLOCATED_BUFFERS` directly caps how many distinct off-heap buffers the
pool will ever bring into existence: once `allocatedBuffers` reaches this
value, every subsequent "buffer full" event is satisfied by *recycling* an
existing buffer via the wait-for-`offer()` path instead of calling
`createBuffer()` again. Since each buffer is a fixed-size direct
`ByteBuffer` (`bufferSize`, itself derived from `max_mutation_size`), the
maximum off-heap memory this pool can hold is bounded by
`MAX_ALLOCATED_BUFFERS × bufferSize`. Raising `MAX_ALLOCATED_BUFFERS`
(via the `-Dcassandra.MAX_HINT_BUFFERS` system property) raises this
ceiling linearly; lowering it tightens the ceiling but increases how often
writer threads block waiting for a buffer to be flushed and recycled.


## 9. Test design (guidance for stage 4)

**Stage 3 writes this section; stage 3 never runs it.** Method and pitfalls:
[README.md §8](../../README.md#8-designing-a-test-for-a-case). Where stage 4's
numbers go: [`../../stage4-runtime-verification/README.md`](../../stage4-runtime-verification/README.md).

**The cleanest case in the folder to test.** The limit is a small integer, the
object is a fixed-size buffer, and the ceiling is exactly
`MAX_ALLOCATED_BUFFERS × bufferSize` — so the predicted dose-response is an
exact number at each capacity value, not a trend. An existing unit test already
proves the disallow branch fires.

**Work out the default ceiling first, because it is not written down
anywhere.** `bufferSize = max(max_mutation_size × 2, MIN_BUFFER_SIZE)`
([`HintsService.java:110`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/hints/HintsService.java#L110)),
with `MIN_BUFFER_SIZE = 32 << 20` = 32 MiB
([`:79`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/hints/HintsService.java#L79)).
`max_mutation_size` defaults to `commitlog_segment_size / 2`
([`DatabaseDescriptor.java:898-899`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/DatabaseDescriptor.java#L898-L899)),
and `commitlog_segment_size` defaults to 32 MiB
([`Config.java:397`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/Config.java#L397)) —
so by default `bufferSize` = max(32 MiB, 32 MiB) = **32 MiB**, and the default
ceiling is **3 × 32 MiB = 96 MiB of direct off-heap memory**. Verified against
the pinned clone 2026-09-28. Stage 4 should confirm this figure first; it is
the prediction everything else rests on.

| Field | Content |
|-------|---------|
| **Testability** | **JVM system property, restart-only.** `MAX_ALLOCATED_BUFFERS` is a `static final int` read once at class-init from `cassandra.MAX_HINT_BUFFERS` ([`HintsBufferPool.java:41`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/hints/HintsBufferPool.java#L41)), so each value costs a restart and there is no JMX setter. Not a patched build, though — it is externally settable. |
| **Constraint knob** | `-Dcassandra.MAX_HINT_BUFFERS=<n>` in `jvm.options` (or `JVM_OPTS`). **Second knob, and the more informative one:** `bufferSize`, moved indirectly by raising `max_mutation_size` **above 16 MiB** (below that, `MIN_BUFFER_SIZE` clamps it and nothing changes) — note `commitlog_segment_size` must be at least twice `max_mutation_size` or startup throws ([`DatabaseDescriptor.java:900-901`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/DatabaseDescriptor.java#L900-L901)). At the unit tier both are bypassed: `new HintsBufferPool(bufferSize, flushCallback)` takes the size directly, as `HintsBufferPoolTest` does. |
| **Capacity values to test** | `cassandra.MAX_HINT_BUFFERS` ∈ {1, 2, **3** (default), 6}. Predicted ceilings at the default `bufferSize`: 32, 64, 96, 192 MiB. **Cross-sweep on the second knob:** hold `MAX_HINT_BUFFERS = 3` and set `max_mutation_size` to 32 MiB (`commitlog_segment_size` 64 MiB), giving `bufferSize` 64 MiB and a predicted 192 MiB — the same ceiling as `MAX_HINT_BUFFERS = 6` reached a different way. If both arms land on the same figure, the product formula in §8 is confirmed directly. |
| **Usage-side observable** | `allocatedBuffers` — an `int` counting buffers ever created. Note §7: it is **never decremented**, so it is a high-water mark, not a live count. The corresponding physical quantity is `allocatedBuffers × bufferSize` bytes of direct `ByteBuffer`. |
| **Instrument** | **Neither the counter nor the pool is exposed as a metric** — `metrics/` has `HintsServiceMetrics` and `HintedHandoffMetrics`, neither of which gauges the buffer pool (checked 2026-09-28). Three routes: (1) **unit tier** — construct the pool and read `allocatedBuffers` reflectively or assert on the flush-callback's buffer identities, which is what `HintsBufferPoolTest` effectively does; (2) **NMT** — `-XX:NativeMemoryTracking=summary` at JVM start, then `jcmd <pid> VM.native_memory summary`, looking at the direct-buffer category; the buffers are `ByteBuffer.allocateDirect`, so they appear there and the ceiling is coarse enough (32 MiB steps) to see plainly; (3) **thread dump** for the disallow evidence — threads parked in `BlockingQueue.take()` inside `switchCurrentBuffer`. |
| **Scope of the limit** | **Global — one `HintsBufferPool` per node**, constructed once in `HintsService` ([`:111`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/hints/HintsService.java#L111)). Not per table, per keyspace or per destination node. `N = 1`, no multiplier. |
| **Suggested level** | **Both, unit first.** `test/unit/org/apache/cassandra/hints/HintsBufferPoolTest.java` — its single test `testBackpressure()` ([`:49-72`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/test/unit/org/apache/cassandra/hints/HintsBufferPoolTest.java#L49-L72)) uses a Byteman rule targeting `switchCurrentBuffer` at the `BlockingQueue.take` invocation, so it already proves the disallow branch is reached. Run: `ant testsome -Dtest.name=org.apache.cassandra.hints.HintsBufferPoolTest`. **Confirm Byteman resolves as a test dependency first** — this was flagged as the open risk when the trigger was originally designed, and has never been checked. Extend the test to assert the *buffer count* at several `MAX_ALLOCATED_BUFFERS` values, which it does not currently do. Then the cluster tier for the off-heap figure. |

### 9a. Workload — driving the usage operand

Hints accumulate only when a replica is **down**, so the workload has an
unusual prerequisite: a node that cannot be written to.

- Two-node cluster (or one node plus a replica that is stopped), keyspace with `RF = 2` so writes have a hinted destination.
- Start both, then **stop node 2**. Write to node 1 with `cassandra-stress` or a CQL client at `CONSISTENCY ONE` so writes succeed while node 2 is down; each write to the missing replica becomes a hint.
- Keep `max_hints_delivery_threads` and dispatch as they are, but note that hints are written to disk and buffers recycled continuously — the pool only grows to its cap when the **write rate outruns the flush-and-recycle loop**. Sustained high-rate writes are needed, which makes this the one case in the folder where README §8.2 rule 2's "prefer a single shot" is hard to honour at the cluster tier.
- **So prefer the unit tier for the boundary itself.** `HintsBufferPoolTest` sizes the pool at 256 bytes and writes 512 hints from one thread with no consumer, which forces the cap deterministically in milliseconds. Use the cluster tier to confirm the off-heap figure, not to find the boundary.

### 9b. Scenario A — just reach capacity

Drive exactly `MAX_ALLOCATED_BUFFERS` buffers into existence and no more.

Expect: `allocatedBuffers == MAX_ALLOCATED_BUFFERS`, direct off-heap memory up
by `MAX_ALLOCATED_BUFFERS × bufferSize`, no thread blocked. At the cluster tier
this is the arm that confirms the 96 MiB default figure. Writers should not
stall.

### 9c. Scenario B — try to exceed capacity

Keep writing once the cap is reached. **The disallow branch blocks; it does
not reject and it does not drop the hint** (§6b):

| Expected | Evidence to capture |
|---|---|
| Writer threads **block** in `reserveBuffers.take()` | Thread dump showing threads parked inside `HintsBufferPool.switchCurrentBuffer` at [`:118`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/hints/HintsBufferPool.java#L118); at the unit tier the Byteman rule already sets a flag when that invocation is reached. This is the direct evidence README §8.2 rule 5 asks for. |
| `allocatedBuffers` **stops rising**, pinned at the cap | No further `createBuffer()` calls. |
| Off-heap memory **plateaus** at `cap × bufferSize` | NMT direct-buffer category flat while writes continue. |
| Blocking **clears** when a buffer is flushed and recycled | `offer()` returns a recycled buffer and the parked thread proceeds. `HintsBufferPoolTest` drives exactly this loop. |
| **No hint is lost and nothing throws** | Distinguishes this case from `cdc_total_space`, whose disallow branch genuinely rejects the write. |

### 9d. Expected dose-response

If the traced path is the binding limit, this case predicts **exact numbers**,
which is rare here:

- **Peak off-heap for the pool = `MAX_ALLOCATED_BUFFERS × bufferSize`**, exactly, at every value: 32 / 64 / 96 / 192 MiB for n = 1 / 2 / 3 / 6 at the default `bufferSize`. Strictly linear through the origin, with no offset.
- **Time-to-first-block falls as n falls**, at constant hint rate.
- **Write throughput to the hinted destination falls as n falls**, because writers spend longer parked — but total hints written should be unaffected, since nothing is dropped.
- **The two-knob cross-check:** n = 6 at 32 MiB buffers and n = 3 at 64 MiB buffers should produce the *same* 192 MiB ceiling. If they do not, the ceiling is not the product §8 claims.

### 9e. Interpretation — what each outcome means

| Observation at scenario B | Reading |
|---|---|
| Off-heap plateaus at exactly `n × bufferSize`; threads park in `take()`; nothing is dropped | The check enforces as traced. |
| Off-heap climbs past `n × bufferSize` | Some other path allocates hint buffers without going through `switchCurrentBuffer`, or the buffers are not being recycled as §7 describes. No escape hatch is known for this case (§10), so this would be a **new finding** — chase it, and it is Target-3 material. |
| Off-heap plateaus but **below** `n × bufferSize` | The workload never drove the pool to its cap — the flush-and-recycle loop kept up. Raise the write rate or shrink `bufferSize`; a measurement shortfall, not a finding. |
| Off-heap flat across all four values of n | The traced path is not the binding limit. Re-read, do not re-run. Check first that hints are actually being generated (a replica really is down). |

### 9f. What would refute this case

The case claims `MAX_ALLOCATED_BUFFERS` caps the number of `HintsBuffer`s ever
created, so peak off-heap memory held by the hints buffer pool is exactly
`MAX_ALLOCATED_BUFFERS × bufferSize`. It is refuted if peak direct off-heap
attributable to the pool **does not scale with `MAX_ALLOCATED_BUFFERS`** across
the sweep, with hints confirmed to be flowing and the pool confirmed to reach
its cap.

Because the prediction is an exact product rather than a trend, this case is
more sharply falsifiable than most in the folder: a measured ceiling that is
not `n × bufferSize` — in either direction — needs explaining. The two-knob
cross-check in §9d is the cheapest way to catch a wrong `bufferSize`
assumption, which is the most likely source of a mismatch.

### 9g. Confounders and controls

- **No hints, no test.** The single largest risk is a run where hints never accumulate. Confirm with `nodetool tpstats` / the hints directory on disk that hints are actually being written before trusting any null result.
- **Other direct-buffer consumers** dominate NMT: the chunk cache, compression buffers, Netty's pooled direct buffers, and — if `memtable_allocation_type` is off-heap — the memtable pools. Use NMT's category breakdown, take an idle-node baseline to subtract, and consider setting `memtable_allocation_type: heap_buffers` for this case so the memtable pools do not move the same number.
- **`max_mutation_size` and `commitlog_segment_size`** change `bufferSize`, hence the ceiling, and the two are constrained relative to each other. Hold both fixed except in the deliberate cross-sweep arm, and record the resolved `bufferSize` in every arm.
- **`MIN_BUFFER_SIZE` clamps small values** — setting `max_mutation_size` below 16 MiB changes nothing, because `max(x, 32MiB)` is still 32 MiB. An arm that lowers it and sees no change has confirmed the clamp, not refuted the case.
- **`allocatedBuffers` is a high-water mark**, never decremented. Do not read a stable value as "buffers currently live"; peak and steady-state are the same number by construction here.
- **Byteman availability** for the unit tier — confirm it resolves before scheduling the work.
- **Baseline** at default (n = 3) with hints flowing; **idle control** with both nodes up so no hints are generated at all, to establish the off-heap floor.

## 10. Provenance

| Field | Content |
|--------|---------|
| **Stage-3 feed** | `3b` — established by deep-reading the source; no stage-1/2 row led here. |
| **Line numbers checked** | 2026-09-22 against the local `cassandra-5.0.9` clone (`git describe --tags`). |
| **Escape hatch / Target-3 note** | none found yet (see Notes). |
| **Stage-4 feedback** | none yet |

---

## 11. Notes

- `MAX_ALLOCATED_BUFFERS` is set via a JVM system property (`-D` flag), not `cassandra.yaml` — different configuration mechanism from the memtable/net cases' YAML-backed limits, but still "Configuration" per the Limit type taxonomy since it's externally settable without a code change.
- This case was flagged as a runner-up candidate in [`../../../HANDOFF.md`](../../../../HANDOFF.md) before this draft; see `../_INDEX.md` for cross-reference.
