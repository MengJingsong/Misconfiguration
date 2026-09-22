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
4. No escape hatch was found in this path — unlike the memtable cases' `markBlocking()`, there is no alternate route that lets a caller bypass this wait and force a new buffer allocation past the cap. (Not exhaustively verified via runtime tracing yet — see Verification below.)

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

## 9. Verification

See [README.md § Verifying a case](../README.md#8-verifying-a-case-triggering-the-disallow-branch)
before setting `Status: verified` — line-number checking alone is not enough;
a designed experiment must have actually driven execution into the disallow
branch with recorded evidence.

| Field | Content |
|--------|---------|
| **Status** | pending |
| **Verified By / Date** | — |
| **Trigger method** | Not yet run. An existing test, `test/unit/org/apache/cassandra/hints/HintsBufferPoolTest.java`'s `testBackpressure()`, already targets this exact line: it sets `bufferSize` small, drives 512 hint writes from a background thread, and uses a byteman rule (`@BMRule`, `targetMethod="switchCurrentBuffer"`, `targetLocation="AT INVOKE java.util.concurrent.BlockingQueue.take"`) to flip `blockedOnBackpressure = true` the instant the thread reaches the `reserveBuffers.take()` call inside the disallow branch — i.e. it already proves the disallow branch fires. Reuse as-is via `ant testsome -Dtest.name=org.apache.cassandra.hints.HintsBufferPoolTest` (note: needs Byteman on the classpath, which `ant testsome` should already resolve as a test dependency — confirm before running). |
| **Evidence** | Not yet captured — expected: `BUILD SUCCESSFUL`, `blockedOnBackpressure` assertion passes, confirming the calling thread actually reached the `take()` call inside the `if` block at line 113. |
| **Line numbers checked** | not recorded |
| **Escape hatch / Target-3 note** | none found yet (see Notes). |
| **Notes** | No escape hatch identified yet in this code path (unlike the memtable cases' `markBlocking()`) — flagged as an open question for Target 3, not chased further here. `allocatedBuffers` counts cumulative allocations, not live buffers, which is a minor discrepancy from a naive reading of "current buffer count" worth noting for anyone extending this case. |

---

## 10. Notes

- `MAX_ALLOCATED_BUFFERS` is set via a JVM system property (`-D` flag), not `cassandra.yaml` — different configuration mechanism from the memtable/net cases' YAML-backed limits, but still "Configuration" per the Limit type taxonomy since it's externally settable without a code change.
- This case was flagged as a runner-up candidate in [`../../../HANDOFF.md`](../../../HANDOFF.md) before this draft; see `_INDEX.md` for cross-reference.
