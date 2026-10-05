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

**Stage 3 writes this section; stage 3 never runs it** — no measured numbers
and no verdict here; results go to
[`../../../stage4-runtime-verification/README.md`](../../../stage4-runtime-verification/README.md).
The test changes `MAX_HINT_BUFFERS`, makes hints arrive faster than the disk
flush can recycle buffers, and checks that the pool stops at *n* buffers and the
writer waits. **Run so far:** both tiers, 2026-09-30 (results file §4.2 and §4.3, §8).

### 9a. Procedure and conclusions

**Testability:** JVM system property, **restart-only** — every capacity value
needs a fresh JVM, at both tiers. No patched build is needed.

**Claim under test:** `MAX_HINT_BUFFERS` caps how many off-heap hint buffers the
node's one pool ever creates, so the pool holds at most `n × bufferSize` bytes of
direct memory (96 MiB at the defaults). When the cap is reached and the current
buffer is full, the writing thread waits until the disk flush recycles a buffer;
the hint is not dropped, and no way around the cap is recorded. This holds for
*n* ≥ 2; at *n* = 1 the wait cannot end (9b).

**How this verifies the hypothesis** (a restatement of the claim, procedure,
prediction and conclusions in this section; it adds none):

- **Hypothesis:** with `MAX_HINT_BUFFERS` = *n*, the hints pool creates at most
  *n* off-heap buffers, so it holds at most `n × bufferSize` of direct memory, and
  at the cap a writer waits instead of allocating.
- **Test:** vary *n* (2, 3 the default, 6) and `bufferSize`, push hints in faster
  than the flush returns buffers (at the cluster tier a Byteman rule holds the
  flush back), and read the pool's buffer count and the JVM's real direct memory.
- **Logic:** (1) at every value a writer must reach the cap and wait, or the run
  is invalid. (2) While it waits, buffers created = *n* and direct memory =
  `n × bufferSize`, unchanged over time: usage **stops at the limit**. (3) The same
  holds at the other *n*, and `n × bufferSize` is the same from 3 × 2 MiB as from
  6 × 1 MiB: usage **follows the constraint**. (4) Returning one buffer releases
  the writer without a new allocation: the **wait**, not a rejection or a fresh
  allocation, is what enforces the limit.
- **Refuted if:** more than *n* buffers appear; direct memory rises above
  `n × bufferSize` with *n* buffers; it stays flat across *n*; or it follows *n*
  but not `bufferSize` (rows of the Conclusions table).

**Procedure:**

1. **Unit tier** — (a) run the upstream `HintsBufferPoolTest` at *n* = 2, 3 and
   6. (b) Run a harness test at the same values that drives a pool of real
   direct buffers until a writer waits, and checks that the pool holds exactly
   *n* buffers, direct memory is up by `n × bufferSize`, the writer is parked at
   the check, nothing grows while it waits, recycling one buffer releases it
   without creating another, and every hint written is found in exactly one buffer.
2. **Cluster tier** — two nodes; node 2 joins the ring and is then stopped.
   Start node 1 once per capacity value: *n* = 2, 3 (the default) and 6, plus
   an arm that keeps *n* = 3 and doubles `bufferSize`.
3. **At each capacity value:** control run (idle) → **A**, write hints with the
   disk flush held back until the pool holds *n* buffers → **B**, keep writing
   under the hold and try to make the pool create an (*n*+1)-th, then release
   the hold and watch the writer resume. There is no scenario C: no bypass is
   recorded.
4. **Compare** with the prediction and read the result below.

**Prediction:**

- **Unit tier:** when the writer waits, the pool holds exactly *n* buffers and
  direct memory is up by `n × bufferSize`. Neither changes while it waits.
- **A:** the pool creates its *n*-th buffer.
- **B:** the pool never creates an (*n*+1)-th. A writer waits at the check, and
  writing resumes once a buffer is recycled. Direct memory is `n × bufferSize`
  counting from a node with no pool: 64, 96 and 192 MiB for *n* = 2, 3 and 6
  with the default 32 MiB buffers. The figures are exact apart from small,
  unrelated direct buffers (each thread that serializes a mutation keeps a
  per-thread scratch buffer, 128 bytes at first, `Mutation.java:453`). A node
  that has been up for ten seconds already holds one buffer, so the rise above
  idle is one buffer less (9d).
- **Second-knob arm:** *n* = 3 with 64 MiB buffers reaches the same 192 MiB as
  *n* = 6 with 32 MiB. If both arms land there, the product `n × bufferSize` in
  §8 is confirmed from both sides.

No bypass is recorded, so the prediction has no allowed excess: any direct
memory above `n × bufferSize` is unexplained.

**Reading rule (added 2026-09-30, design audit; amended the same day, before any
run, after the instrument check, see results §3).** Unit tier: `Count` up by
exactly *n* and `MemoryUsed` by exactly `n × bufferSize`, taken from a baseline
after the writer thread is warmed up (9e). Cluster tier, over the idle control:
`MemoryUsed` up by `(n − 1) × bufferSize`, where a difference of up to 4 MiB is
read as unrelated small buffers, provided the create trace shows exactly *n*
buffers. `Count` is **reported, not asserted**, in the cluster tier: every
thread that serializes a mutation holds a scratch direct buffer, so up to 32
`MutationStage` threads add up to 32 to `Count` (and, estimated, well under 1 MiB
in all at 5 KiB hints; not measured). The smallest step between *n* and *n* + 1
buffers is 32 MiB (the default `bufferSize`), so the band cannot hide an extra
buffer. A larger difference is decided by the create trace (9d).

**Conclusions:**

| Result | Conclusion |
|---|---|
| The pool holds exactly *n* buffers at every value, direct memory is up by the predicted amount (reading rule above: unit `n × bufferSize`, cluster `(n − 1) × bufferSize` over idle), a writer waits at the check, and the ceiling moves with *n* and with `bufferSize` | **Confirmed** — the check enforces as traced. |
| More than *n* buffers are ever created | **Refuted** — the check does not cap the pool. No bypass is recorded, so this is a new finding (Target-3 material): some path creates buffers around the check. |
| Exactly *n* buffers are created, but direct memory keeps rising above the predicted amount | **Refuted** — the counter does not track the resource; §8's ceiling claim is wrong. Rule out other direct-buffer users first (9d). |
| The buffer count and direct memory follow *n* but not `bufferSize` (the second-knob arm does not land at 192 MiB), while the create trace shows `size=` as set | **Refuted** in part — §8's product `n × bufferSize` is wrong. If `size=` is not as set, the setting did not take effect: **Invalid run**, fix 9b. |
| A writer waits at the check, but after the hold is released it does not resume (no progress, `TotalHints` flat) | **Not confirmed** — the disallow is not the bounded wait traced in §6b. Re-read. |
| Direct memory is flat across every value of *n*, with hints flowing and the pool at its cap | **Refuted** — not the binding limit. Re-read, do not re-run. |
| The buffer count follows *n* and writers stall, but no writer is ever seen waiting at the check | **Not confirmed** — something else is holding the writers; §6b's disallow effect is not shown. Re-read. |
| Fewer than *n* buffers are created, or no writer waits although more than `n × bufferSize` of hints were written under the hold | **Invalid run** — the cap was never reached. Fix the setup (9b, 9c) and re-run. |

**Why direct memory alone is not enough:** other code allocates direct buffers,
so the memory reading can move for reasons unrelated to this check. Only the
count of buffers the pool made and the wait evidence tie it to the check.

### 9b. Setup

| Field | Content |
|-------|---------|
| **Constraint knob** | `-Dcassandra.MAX_HINT_BUFFERS=<n>`, a JVM system property; restart-only. `MAX_ALLOCATED_BUFFERS` is a `static final int` read once when `HintsBufferPool` loads ([`HintsBufferPool.java:41`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/hints/HintsBufferPool.java#L41)), and there is no JMX setter. Unit tier: pass it through ant with `-Dtest.jvm.args` ([`build.xml:1192`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/build.xml#L1192)). Cluster tier: `JVM_EXTRA_OPTS` (9e). **Second knob:** `bufferSize`, set indirectly by `max_mutation_size` in `cassandra.yaml` (the shipped file only mentions it in a comment, so add the line). `bufferSize = max(2 × max_mutation_size, 32 MiB)` ([`HintsService.java:110`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/hints/HintsService.java#L110), [`:79`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/hints/HintsService.java#L79)), so a value at or below 16 MiB changes nothing. `commitlog_segment_size` must be at least twice `max_mutation_size`, or startup throws ([`DatabaseDescriptor.java:900-901`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/DatabaseDescriptor.java#L900-L901)). Unit tier: the pool takes `bufferSize` directly. |
| **Confirm it took effect** | Unit: an assertion that `HintsBufferPool.MAX_ALLOCATED_BUFFERS == n`. Cluster: the `max=` and `size=` fields of the create trace (9d) give *n* and `bufferSize` as the pool read them; `jcmd <pid> VM.system_properties \| grep MAX_HINT_BUFFERS` shows the property on the JVM. |
| **Capacity values** | *n* = 2, 3 (default), 6 — 64, 96 and 192 MiB at the default `bufferSize`. That default is 32 MiB: `max_mutation_size` defaults to `commitlog_segment_size / 2` ([`DatabaseDescriptor.java:898-899`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/DatabaseDescriptor.java#L898-L899)) and `commitlog_segment_size` to 32 MiB ([`Config.java:397`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/Config.java#L397)), so `bufferSize` = max(2 × 16 MiB, 32 MiB). **Second-knob arm:** *n* = 3 with `max_mutation_size: 32MiB` and `commitlog_segment_size: 64MiB` — 64 MiB buffers, 192 MiB. **Do not use *n* ≤ 1.** `allocate()` hands a full buffer to the flush callback only *after* `switchCurrentBuffer()` returns ([`HintsBufferPool.java:79-80`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/hints/HintsBufferPool.java#L79-L80)), and that callback's task is the only code that recycles a buffer ([`HintsWriteExecutor.java:141-154`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/hints/HintsWriteExecutor.java#L141-L154); the periodic flush explicitly does not, [`:88-94`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/hints/HintsWriteExecutor.java#L88-L94)). With one buffer, `take()` ([`:118`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/hints/HintsBufferPool.java#L118)) waits for a recycle that cannot start: the writer waits forever, and the upstream test would spin until ant's timeout. Read from the code, not run. |
| **Scope** | Global: one pool per node, built once in `HintsService` ([`:111`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/hints/HintsService.java#L111)). N = 1; nothing is per table or per destination. |
| **Level** | Both, unit first. `HintsBufferPoolTest.testBackpressure()` ([`:49-73`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/test/unit/org/apache/cassandra/hints/HintsBufferPoolTest.java#L49-L73)) already reaches the check: a Byteman rule (`byteman-bmunit`, a declared build dependency in `.build/cassandra-deps-template.xml`) sets a flag when `take()` is invoked. It asserts no counts, so the ceiling needs a harness test (9c). The unit tier's flush callback stands in for `HintsWriteExecutor`; it does not test the wiring in `HintsService` or the `bufferSize` derivation. The cluster tier does. |

**Hold fixed:**

| Setting | Value | Why |
|---|---|---|
| `commitlog_segment_size`, `max_mutation_size` | `32MiB`, unset (the defaults) | They set `bufferSize`, hence the ceiling. Changed only in the second-knob arm. |
| `hinted_handoff_enabled` | `true` (default) | With it off, no hint is written ([`StorageProxy.java:2444-2447`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/service/StorageProxy.java#L2444-L2447)). |
| `hints_flush_period` | `10000ms` (default) | The periodic flush creates the pool's first buffer and writes the current buffer out without recycling it ([`HintsService.java:116-121`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/hints/HintsService.java#L116-L121), [`HintsWriteExecutor.java:157-180`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/hints/HintsWriteExecutor.java#L157-L180)). Changing it changes when the idle floor is reached. |
| `hints_compression` | unset (default) | Compression allocates buffers of its own ([`CompressedHintsWriter.java:55`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/hints/CompressedHintsWriter.java#L55)) that would move the memory reading. |
| `memtable_allocation_type` | `heap_buffers` (default) | Off-heap memtables also allocate off-heap memory. Start from `conf/cassandra.yaml`, **not** `conf/cassandra_latest.yaml`, which sets `offheap_objects` ([`:836`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/conf/cassandra_latest.yaml#L836)). |
| `concurrent_writes` | `32` (default) | The writers are `MutationStage` threads ([`Config.java:180`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/Config.java#L180)); this is how many can wait at once. |
| `max_hint_window` | `3h` (default) | The coordinator stops hinting for a node that has been down longer than this ([`StorageProxy.java:2461-2463`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/service/StorageProxy.java#L2461-L2463)). Node 2 stays down for the whole sweep, so record when it was stopped (results §2); a sweep that runs past 3 h would silently stop producing hints, and the hints-flowing control (9d) would show it. |
| Hint, data and log directories | local disk, never `/proj` | The test writes about 1 GB of hints per run; see the safety rules in the stage-4 README. |
| Client load | same command and thread count at every value | Other direct-buffer users move with the load. |

**Controls:**

- **Idle control** — node 1 up for at least 15 s, no writes, at every value: the direct-memory floor to subtract. It already contains one buffer (9d).
- **Natural-load control** — once, at *n* = 3, without the hold rule and with the same stress command: shows whether the pool grows to its cap on this disk without help. Reported as a control; no §9a row depends on it.

**Reset between runs:** stop node 1 (`bin/nodetool stopdaemon`), check nothing is
left (`pgrep -f org.apache.cassandra.service.CassandraDaemon`), empty its hints
directory (`data/hints/` in a source-tree clone) and move `logs/` aside. Leave
node 2 stopped and its data untouched: it has to stay a ring member. Table data
can stay; every run writes the same 200,000 keys.

### 9c. Workload

Hints exist only while a replica is down, so the cluster tier needs a second
node that has joined the ring and then been stopped. It is only a hint target;
its memory is not measured. It is set up as a second CloudLab node, on the control network, as in
[`environment.md`](../../../stage4-runtime-verification/environment.md) §5
(added 2026-09-30).

Prefer a deterministic trigger over a race (README §8.2 rule 2). A natural run
reaches the cap only if the writers outrun the flush, which depends on the disk
and cannot be repeated exactly. So the cluster tier holds each buffer flush back
with a Byteman rule. That imitates a slow disk: it changes only when a buffer
comes back, not the path to the check.

**Harness.** Stage 4 wrote these under
`harness/MAX_HINT_BUFFERS-switchCurrentBuffer-MAX_ALLOCATED_BUFFERS/` and checked
them before run 1 (results §1.2). `<harness>` below stands
for `<misconfiguration-repo>/cassandra/if-check-exp/stage4-runtime-verification/harness/MAX_HINT_BUFFERS-switchCurrentBuffer-MAX_ALLOCATED_BUFFERS`.

| File | What it is |
|---|---|
| `HintsPoolCeilingTest.java` | Unit tier (9e). Package `org.apache.cassandra.hints`, because the pool is package-private. |
| `hints-pool.btm` | Byteman, observation only: the `created` and `waiting` trace lines (formats in 9d). Loaded at node start. |
| `hold-flush.btm` | Byteman, the trigger: delays every `HintsWriteExecutor$FlushBufferTask.run()` by `stage4.hold.ms` and appends `hold ms=<epoch millis> delay=<ms>` to `stage4.hold.out`. Loaded and unloaded with `Submit` (9e). |

```bash
# unit tier — one JVM per capacity value (n = 2, 3, 6; never 1, see 9b)
ant testsome -Dtest.name=org.apache.cassandra.hints.HintsBufferPoolTest \
  -Dtest.jvm.args="-Dcassandra.MAX_HINT_BUFFERS=<n>"
cp <harness>/HintsPoolCeilingTest.java test/unit/org/apache/cassandra/hints/
ant testsome -Dtest.name=org.apache.cassandra.hints.HintsPoolCeilingTest \
  -Dtest.jvm.args="-Dcassandra.MAX_HINT_BUFFERS=<n> -Dstage4.hints.bufferSize=<bytes>"

# cluster tier, first time only, while both nodes are up: keyspace and table, RF = 2
bin/cqlsh -e "CREATE KEYSPACE keyspace1 WITH replication = {'class': 'SimpleStrategy', 'replication_factor': 2};"
tools/bin/cassandra-stress write n=1000 no-warmup -node 127.0.0.1
# stop node 2; wait until `bin/nodetool status` on node 1 shows it as DN; then, at each value:
tools/bin/cassandra-stress write n=200000 no-warmup -col 'size=FIXED(1024)' -rate threads=64 -node 127.0.0.1
```

The default consistency level (`LOCAL_ONE`) needs only the live replica, so the
writes succeed and each one leaves a hint for node 2.

**Starting values.** Estimates, not measurements:

| Setting | Value | Why |
|---|---|---|
| Hint size | 5 columns × `FIXED(1024)` ≈ 5 KiB | Roughly 6,000 hints fill a 32 MiB buffer. |
| Rows | `n=200000`, about 1 GB of hints; **second-knob arm `n=400000`** (amended 2026-09-30 after the first attempt, results §3 defect 3) | More than the `(n+1) × 32 MiB` (224 MiB at *n* = 6) needed to force a wait, and it fits the node's local disk. With 64 MiB buffers each recycled buffer admits twice the hints, so 200,000 rows ran out 34 s into B; 400,000 covers the 60 s. |
| Client threads | `threads=64` | More than `concurrent_writes` (32), so every writer thread has work. |
| Hold | `-Dstage4.hold.ms=3000` | At most one 32 MiB buffer comes back per 3 s (about 10.7 MiB/s). 64 clients writing 5 KiB hints are expected to outrun that. |
| Time in B | about 60 s, **ended early** when `HintsInProgress` passes 75 % of `128 × cores` | Long enough for several samples and dumps. **Estimate, not measured (design audit, 2026-09-30):** while the pool is at its cap the writers are the `MutationStage` threads (32), one in `take()` and the rest blocked on the pool's monitor, so the coordinator's own local writes queue behind them and each of the 64 client threads times out after about 2 s (`write_request_timeout`). Each write submits a hint before it waits, which is up to 64 hints per 2 s, about 1,900 in 60 s, against a limit of 2,048 on 16 cores and 5,120 on 40. On a small node B can therefore hit the limit; record `nproc` (results §2) and apply the stop rule. |

**If the pool does not reach *n* buffers** (no `created=<n>` line in A): stop,
reset (9b) and repeat that value with `threads=128`, then with a longer hold.
Record each step as a deviation. If none works, the run is invalid (9a).

### 9d. Observables

| Observable | How to read it | When to sample | Trap |
|---|---|---|---|
| **Usage counter** — `allocatedBuffers`, a private `int` on the pool ([`HintsBufferPool.java:46`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/hints/HintsBufferPool.java#L46)), incremented only in `createBuffer()` ([`:132`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/hints/HintsBufferPool.java#L132)) and never decremented. A recycled buffer reuses its slab ([`HintsBuffer.java:96-100`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/hints/HintsBuffer.java#L96-L100)), so it also counts the direct buffers the pool owns. | Unit: read the field by reflection. Cluster: no gauge exposes it — `metrics/` holds only `HintsServiceMetrics` and `HintedHandoffMetrics` (checked 2026-09-30). Use the create trace: a Byteman rule at the exit of `createBuffer()` writes one line per buffer to `stage4.byteman.out`, `created=<allocatedBuffers> size=<bufferSize> max=<MAX_ALLOCATED_BUFFERS> ms=<epoch millis> thread=<name>`. The number of lines is the counter. | Unit: when the writer waits. Cluster: read the file at the end of each scenario; `ms` places each line in A or B. | An idle node already has one line. The periodic flush calls `currentBuffer()`, which creates the first buffer ([`HintsService.java:116-121`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/hints/HintsService.java#L116-L121), [`HintsWriteExecutor.java:168`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/hints/HintsWriteExecutor.java#L168), [`HintsBufferPool.java:93-105`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/hints/HintsBufferPool.java#L93-L105)); its `thread=` is the hints executor, not a writer. |
| **Disallow evidence** — a writer waiting at the check | (i) A second trace line, one per entry into the disallow branch, at the `BlockingQueue.take` invocation in `switchCurrentBuffer` (the location `HintsBufferPoolTest`'s rule uses): `waiting ms=<epoch millis> thread=<name>`. (ii) A thread dump, `jcmd <pid> Thread.print`: one `MutationStage` thread parked in `java.util.concurrent.LinkedBlockingQueue.take` under `HintsBufferPool.switchCurrentBuffer(HintsBufferPool.java:118)` ([link](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/hints/HintsBufferPool.java#L118)). | (i) End of each scenario. (ii) Two or three dumps during B while the hold is in force. | `take()` runs only when the reserve is empty and the cap is reached ([`:112-118`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/hints/HintsBufferPool.java#L112-L118)), and nothing else reads the property (`:41` and `:113` only; grep, 2026-09-30), so a `waiting` line belongs to this check. `switchCurrentBuffer` is `synchronized` ([`:107`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/hints/HintsBufferPool.java#L107)), so **only one** writer is in `take()`; the others are BLOCKED on the pool's monitor in the same method. Do not count parked threads. Client write timeouts are a symptom, not evidence. So is `OverloadedException: Too many in flight hints`: it comes from `checkHintOverload` (limit `128 × cores`, [`StorageProxy.java:202`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/service/StorageProxy.java#L202), [`:1592-1597`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/service/StorageProxy.java#L1592-L1597)), not from this check. |
| **Real resource** — direct memory | `bin/nodetool sjk mx -mg -b 'java.nio:type=BufferPool,name=direct' -f MemoryUsed` (bytes), and `-f Count` (number of direct buffers). Cross-check: start the JVM with `-XX:NativeMemoryTracking=summary`, then `jcmd <pid> VM.native_memory summary \| grep 'Other ('`. Direct buffers are counted under **Other** on this node's JDK; checked 2026-09-30: three `allocateDirect(32 MiB)` raised `MemoryUsed` by 100,663,296 bytes and `Count` by 3, and NMT's `Other` then read 98,314 KB (96 MiB plus 10 KB). Unit: the same beans in-process, `ManagementFactory.getPlatformMXBeans(BufferPoolMXBean.class)`. | Idle control, end of A, every 5 s during B, end of B. | The idle floor already holds one hints buffer, so the rise **above idle** is `(n − 1) × bufferSize`; the same figure is `n × bufferSize` above a node with no pool. The floor also holds the executor's 256 KiB write buffer ([`HintsWriteExecutor.java:60`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/hints/HintsWriteExecutor.java#L60), constant) and any other `allocateDirect` user, and every thread that serializes a mutation keeps a scratch direct buffer (`Mutation.java:453`; seen at the unit instrument check, 2026-09-30), so `Count` rises by more than *n* − 1 (up to 32 more on the `MutationStage`). Record `Count`; do not accept or reject on it. The create trace and the 4 MiB band on `MemoryUsed` decide. Each `sjk` call starts a JVM (1–2 s), so time-stamp every reading. Never use process RSS. |
| **Hints flowing** — the control for a null result | `bin/nodetool sjk mx -mg -b 'org.apache.cassandra.metrics:type=Storage,name=TotalHints' -f Count` and `bin/nodetool sjk mx -mg -b 'org.apache.cassandra.db:type=StorageProxy' -f HintsInProgress`. | Before A, and at the end of A and B. | `TotalHints` is incremented after the pool write returns ([`HintsService.java:169-171`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/hints/HintsService.java#L169-L171)), so it stops rising while writers wait. A run where it never rises had no hints: node 2 was not seen as down (`bin/nodetool status` shows `DN`), or it has been down longer than `max_hint_window` (9b), or it was never in the ring, and then the hint is discarded ([`StorageProxy.java:2801`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/service/StorageProxy.java#L2801)). `HintsInProgress` near `128 × cores` (5,120 on 40 cores) means the coordinator is about to refuse writes: stop B early. |

### 9e. Running the scenarios

**Unit tier.** Commands are in 9c; one JVM per value.

1. Run the upstream `HintsBufferPoolTest` at *n* = 2, 3 and 6. Record pass or fail.
2. Run `HintsPoolCeilingTest` at *n* = 2, 3 and 6 with `bufferSize` 1 MiB, and once
   more at *n* = 3 with 2 MiB: 3 × 2 MiB and 6 × 1 MiB are both 6 MiB, which is
   the second-knob check. The test calls `HintsBufferTest.defineSchema()` first, as `HintsBufferPoolTest`'s `@BeforeClass` does (the helper needs the schema), and uses `HintsBufferTest`'s hint helper
   ([`HintsBufferTest.java:196`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/test/unit/org/apache/cassandra/hints/HintsBufferTest.java#L196))
   and a flush callback that queues buffers without recycling them, as
   `HintsBufferPoolTest` does. It:
   1. asserts `MAX_ALLOCATED_BUFFERS == n`; starts the writer and has it serialize one hint before it writes (its per-thread scratch buffer, `Mutation.java:453`, would otherwise land inside the deltas as `Count` +1 and `MemoryUsed` +128); settles with `System.gc()` and a 500 ms wait; then reads `Count` and `MemoryUsed` of the direct pool as the baseline and lets the writer go;
   2. starts a writer that writes hints until it waits, and waits (up to 60 s) for it to be parked in `LinkedBlockingQueue.take` under `HintsBufferPool.switchCurrentBuffer`;
   3. asserts `allocatedBuffers == n`, that the callback received *n* − 1 buffers, and that `Count` is up by *n* and `MemoryUsed` by `n × bufferSize`;
   4. sleeps 2 s and asserts none of that changed;
   5. recycles one queued buffer (`pool.offer(buffer.recycle())`), waits for the writer to park again, and asserts the same numbers;
   6. recycles the rest and lets the writer finish. Before each buffer is recycled (`recycle()` clears its offsets) it counts that buffer's entries with `consumingHintsIterator`; at the end the counts of every buffer, the current one included, add up to the number of hints the writer wrote.

   Record pass or fail and, per value, the printed *n*, `bufferSize`, `allocatedBuffers` and both direct-memory deltas.

**Before the cluster tier.**

1. **Instrument check, unit** — attach `hints-pool.btm` to the harness test at *n* = 3:

   ```bash
   mkdir -p ~/stage4-logs/hints
   ant testsome -Dtest.name=org.apache.cassandra.hints.HintsPoolCeilingTest \
     -Dtest.jvm.args="-javaagent:$PWD/build/lib/jars/byteman-4.0.20.jar=script:<harness>/hints-pool.btm -Dstage4.byteman.out=$HOME/stage4-logs/hints/instrument-check.txt -Dcassandra.MAX_HINT_BUFFERS=3 -Dstage4.hints.bufferSize=1048576"
   ```

   Expect the test to pass and the trace to hold exactly three `created` lines
   (`created=1`, `2`, `3`, each `max=3`) and at least one `waiting` line.
2. **Start node 1 the same way for every run** — every capacity value, the
   controls and the second-knob arm. `hints-pool.btm` is loaded from startup, so
   it counts from the first buffer. Node 2 is stopped.

   ```bash
   mkdir -p ~/stage4-logs/hints/<value>
   JVM_EXTRA_OPTS="-Dcassandra.MAX_HINT_BUFFERS=<n> -XX:NativeMemoryTracking=summary -Dstage4.byteman.out=$HOME/stage4-logs/hints/<value>/hints-pool.txt -Dstage4.hold.out=$HOME/stage4-logs/hints/<value>/hold.txt -Dstage4.hold.ms=3000 -javaagent:$PWD/build/lib/jars/byteman-4.0.20.jar=script:<harness>/hints-pool.btm,listener:true" \
     bin/cassandra -p cassandra.pid > ~/stage4-logs/hints/<value>/stdout.txt 2>&1
   ```

   Once the node is up, confirm the rules are in place:

   ```bash
   java -cp build/lib/jars/byteman-submit-4.0.20.jar org.jboss.byteman.agent.submit.Submit -l
   ```

   It must list triggers on `HintsBufferPool.createBuffer()` and
   `HintsBufferPool.switchCurrentBuffer(...)`. If it does not, stop: an empty
   trace would then mean nothing.
3. **Instrument check, hold rule** — once, on a throwaway start at *n* = 3:
   load the hold (scenario A, below), then write enough to fill one buffer (10,000
   rows of about 5 KiB is 50 MB, more than 32 MiB):

   ```bash
   tools/bin/cassandra-stress write n=10000 no-warmup -col 'size=FIXED(1024)' -node 127.0.0.1
   ```

   Expect at least one `hold` line and `created=2`. Unload the hold, stop, and reset.

**Cluster tier, for each capacity value:**

1. **Control run** — reset (9b) and start node 1 (above). Wait 15 s after
   `bin/nodetool status` shows it `UN`. With no writes, record `MemoryUsed`,
   `Count`, NMT `Other` and `TotalHints`. Expect one `created=1` line, from the
   hints executor's thread.
2. **Scenario A — reach the cap** — load the hold, note the time
   (`date +%s%3N`), and start the stress command (9c) in the background:

   ```bash
   java -cp build/lib/jars/byteman-submit-4.0.20.jar org.jboss.byteman.agent.submit.Submit <harness>/hold-flush.btm
   ```

   Poll the trace until `created=<n>` appears. Record its time and, at that
   moment, `MemoryUsed`, `Count`, NMT `Other` and `TotalHints`.
3. **Scenario B — try to exceed the cap** — keep writing for about 60 s with the
   hold in force. Every 5 s record `MemoryUsed`, `Count` and `HintsInProgress`;
   end B early if `HintsInProgress` passes 75 % of `128 × cores` (9c); take two or
   three thread dumps. Then release the hold:

   ```bash
   java -cp build/lib/jars/byteman-submit-4.0.20.jar org.jboss.byteman.agent.submit.Submit -u <harness>/hold-flush.btm
   ```

   Once the writers move again, take one more dump (no thread should be at
   `:118`) and one last `MemoryUsed` and `Count`. Stop the stress.
4. **Stop and read the traces** — `bin/nodetool stopdaemon`, check
   `pgrep -f org.apache.cassandra.service.CassandraDaemon` prints nothing, then:

   ```bash
   T=~/stage4-logs/hints/<value>
   grep -c '^created=' $T/hints-pool.txt   # buffers ever created
   grep -c '^waiting'  $T/hints-pool.txt   # entries into the disallow branch
   grep -c '^hold'     $T/hold.txt         # flushes that were held
   ```

   Every `max=` should equal *n* and every `size=` the `bufferSize`.

**Natural-load control (9b)** — once, at *n* = 3: the control run, then the
stress command for about 60 s without loading the hold. It may never reach the
cap, so there is nothing to poll for. Report the highest `created` value, the
peak `MemoryUsed`, and whether any `waiting` line appeared.

**Second-knob arm (9b)** — *n* = 3, with `max_mutation_size` added and
`commitlog_segment_size` changed in `cassandra.yaml` (9b), the same start, and A
and B as above, with `n=400000` rows (9c). Every `created` line should show `size=67108864`.

Stop when each scenario's records are taken; a run where no writer ever waits
is invalid (9a) — fix the workload and repeat it.

**Record for stage 4:** the `cassandra.yaml` diff and JVM options in force, the
exact commands, every reading in 9d, the `Submit -l` output, and the three trace
files, per capacity value.

## 10. Provenance

| Field | Content |
|--------|---------|
| **Stage-3 feed** | `3b` — established by deep-reading the source; no stage-1/2 row led here. |
| **Line numbers checked** | 2026-09-22 against the local `cassandra-5.0.9` clone (`git describe --tags`). §9 rewritten 2026-09-30; every citation in it checked against the same clone. |
| **Escape hatch / Target-3 note** | none found yet (see Notes). |
| **Stage-4 feedback** | Design audit 2026-09-30 (stage-4 README, step 0): **Ready after amendments**; see [`results/MAX_HINT_BUFFERS-switchCurrentBuffer-MAX_ALLOCATED_BUFFERS.md`](../../../stage4-runtime-verification/results/MAX_HINT_BUFFERS-switchCurrentBuffer-MAX_ALLOCATED_BUFFERS.md) §1.1. Amended in §9 (all dated 2026-09-30, before any run): reading rule and 4 MiB band (9a), two new conclusions rows and the cluster/unit wording of the Confirmed row (9a), the in-flight-hint estimate and stop rule (9c, 9e), `max_hint_window` (9b, 9d), `defineSchema()` (9e), and `JVM_EXTRA_OPTS` scoped to the `bin/cassandra` command instead of exported (9e). **Instrument check, 2026-09-30 (unit, n = 3, on node0; not a reading):** two runbook defects found and fixed before run 1 (results §3): the unit baseline must follow a writer warm-up (9e step 1), and cluster `Count` cannot be asserted (reading rule in 9a, 9d). **Unit tier, run 1, 2026-09-30 (node0): consistent with Confirmed; no Refuted or Not-confirmed row fired** (results §4.2, §8). Upstream `HintsBufferPoolTest` passed at *n* = 2, 3, 6; `HintsPoolCeilingTest` passed at *n* = 2, 3, 6 with 1 MiB buffers and at *n* = 3 with 2 MiB: the pool held exactly *n* buffers, direct memory was up by exactly `n × bufferSize` (2, 3, 6 MiB; 3 × 2 MiB = 6 × 1 MiB), the writer waited at the check, and every hint was found in one buffer. No section amended after the unit run began. **Cluster tier, run 1, 2026-09-30 (node0 + `pc80`): Confirmed, with one recorded deviation from the reading rule** (results §4.3, §5, §8). At every value the create trace held exactly *n* lines (*n* = 2, 3, 6, and 3 with 64 MiB buffers), every one with `max=` *n* and the set `size=`; a writer was parked in `LinkedBlockingQueue.take` at `HintsBufferPool.java:118` with 31 more blocked on the monitor; `MemoryUsed` stopped rising at the *n*-th buffer and stayed flat for 60 s under the hold and after its release; the rise over idle followed the knob one buffer per step (33,535,742 against 33,554,432 from *n* = 2 to 3; 100,673,499 against 100,663,296 from 3 to 6) and followed `bufferSize` as a product (3 × 64 MiB and 6 × 32 MiB land 29,761 bytes apart at 227 MB); the natural-load control reached the cap with no hold. **The deviation:** the rise over idle exceeded `(n − 1) × bufferSize` by 8.85–8.89 MiB at every value, outside the reading rule's 4 MiB band. The rule sends a larger difference to the create trace, which shows exactly *n*; the excess is the same at every value and every `bufferSize` (within 38 KB), and an allocation trace (a supplementary diagnostic, not a reading) attributes it to one 8 MiB + 4 KiB `BufferPool` macro-chunk allocated from a netty event-loop thread plus about 120 small per-thread buffers, none of them the hints pool. The 4 MiB figure was an under-estimate that stage 3 could raise or replace (recommendation, results §8); §9a was not edited after a reading existed. **Amended after the cluster run began (documentation only, §9a unchanged):** the row count for the second-knob arm (9c, 9e) after its first 200,000-row attempt ran out of rows 34 s into B (results §3 defect 3), and two stale statements (the §9 intro's "run so far", 9c's "harness not written yet"). |
| **Notes** | §9 converted 2026-09-30 to the template layout (9a summary for review, 9b–9e runbook), before any stage-4 run. Moved: testability, prediction, conclusions and refutation → 9a; knob, values, scope, level, controls → 9b; workload → 9c; instruments → 9d; scenarios → 9e. **Changed, not only moved:** (1) capacity values {1, 2, 3, 6} → {2, 3, 6}: *n* = 1 is left out of the sweep; the reason is in 9b. It is not recorded as a stage-3 finding (Jingsong, 2026-09-30). (2) An idle node already holds one buffer, made by the periodic flush (`HintsService.java:116-121`); the memory rise above idle is `(n − 1) × bufferSize`, where the old text predicted `n × bufferSize` above idle. (3) Instruments: added a Byteman create trace as the usage counter, the JVM direct-buffer bean (`java.nio:type=BufferPool,name=direct`), and the NMT category (`Other`, checked 2026-09-30). (4) The cluster tier holds the flush back with a Byteman rule instead of relying on a load race; the harness (one test, two rules) is not written. (5) Dropped: the "time to first block" and "throughput falls with *n*" predictions (soft, and the hold sets them); "shrink `bufferSize`" as a way to reach the cap (`MIN_BUFFER_SIZE` clamps it at 32 MiB); "no hint is lost" at the cluster tier (only the unit tier can count hints, and `StorageProxy.checkHintOverload` can refuse writes first). (6) `HintsBufferPoolTest` range corrected from `:49-72` to `:49-73`. (7) The old open risk, whether Byteman resolves as a test dependency, is closed: `byteman-bmunit` 4.0.20 is a declared dependency. Whether its runtime attach works on this JDK is settled by the first run (settled 2026-09-30: `HintsBufferPoolTest` ran under BMUnit at *n* = 2, 3, 6 on node0, JDK 11.0.32). |

---

## 11. Notes

- `MAX_ALLOCATED_BUFFERS` is set via a JVM system property (`-D` flag), not `cassandra.yaml` — different configuration mechanism from the memtable/net cases' YAML-backed limits, but still "Configuration" per the Limit type taxonomy since it's externally settable without a code change.
- This case was flagged as a runner-up candidate in [`../../../HANDOFF.md`](../../../../../HANDOFF.md) before this draft; see `../_INDEX.md` for cross-reference.
