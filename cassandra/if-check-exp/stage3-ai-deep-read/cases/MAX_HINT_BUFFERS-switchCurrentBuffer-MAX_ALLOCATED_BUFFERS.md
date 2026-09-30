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
[`../../stage4-runtime-verification/README.md`](../../stage4-runtime-verification/README.md).
The test changes `MAX_HINT_BUFFERS`, makes hints arrive faster than the disk
flush can recycle buffers, and checks that the pool stops at *n* buffers and the
writer waits. **Nothing has been run for this case**, and the harness it needs
is not written yet (9c).

### 9a. Procedure and conclusions

**Testability:** JVM system property, **restart-only** — every capacity value
needs a fresh JVM, at both tiers. No patched build is needed.

**Claim under test:** `MAX_HINT_BUFFERS` caps how many off-heap hint buffers the
node's one pool ever creates, so the pool holds at most `n × bufferSize` bytes of
direct memory (96 MiB at the defaults). When the cap is reached and the current
buffer is full, the writing thread waits until the disk flush recycles a buffer;
the hint is not dropped, and no way around the cap is recorded. This holds for
*n* ≥ 2; at *n* = 1 the wait cannot end (9b).

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
  unrelated direct buffers; the `Count` reading shows whether any moved. A node
  that has been up for ten seconds already holds one buffer, so the rise above
  idle is one buffer less (9d).
- **Second-knob arm:** *n* = 3 with 64 MiB buffers reaches the same 192 MiB as
  *n* = 6 with 32 MiB. If both arms land there, the product `n × bufferSize` in
  §8 is confirmed from both sides.

No bypass is recorded, so the prediction has no allowed excess: any direct
memory above `n × bufferSize` is unexplained.

**Conclusions:**

| Result | Conclusion |
|---|---|
| The pool holds exactly *n* buffers at every value, direct memory is `n × bufferSize`, a writer waits at the check, and the ceiling moves with *n* and with `bufferSize` | **Confirmed** — the check enforces as traced. |
| More than *n* buffers are ever created | **Refuted** — the check does not cap the pool. No bypass is recorded, so this is a new finding (Target-3 material): some path creates buffers around the check. |
| Exactly *n* buffers are created, but direct memory keeps rising above `n × bufferSize` | **Refuted** — the counter does not track the resource; §8's ceiling claim is wrong. Rule out other direct-buffer users first (9d). |
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
its memory is not measured. Setting it up (a second CloudLab node, or a second
process from a separate copy of the clone on another loopback address) is not in
[`environment.md`](../../stage4-runtime-verification/environment.md) yet; stage 4
adds it.

Prefer a deterministic trigger over a race (README §8.2 rule 2). A natural run
reaches the cap only if the writers outrun the flush, which depends on the disk
and cannot be repeated exactly. So the cluster tier holds each buffer flush back
with a Byteman rule. That imitates a slow disk: it changes only when a buffer
comes back, not the path to the check.

**Harness — not written yet.** Stage 4 writes these under
`harness/MAX_HINT_BUFFERS-switchCurrentBuffer-MAX_ALLOCATED_BUFFERS/` and checks
them before run 1, as the heap case's rule was checked. `<harness>` below stands
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
| Rows | `n=200000`, about 1 GB of hints | More than the `(n+1) × 32 MiB` (224 MiB at *n* = 6) needed to force a wait, and it fits the node's local disk. |
| Client threads | `threads=64` | More than `concurrent_writes` (32), so every writer thread has work. |
| Hold | `-Dstage4.hold.ms=3000` | At most one 32 MiB buffer comes back per 3 s (about 10.7 MiB/s). 64 clients writing 5 KiB hints are expected to outrun that. |
| Time in B | about 60 s | Long enough for several samples and dumps, short of the in-flight hint limit (9d). |

**If the pool does not reach *n* buffers** (no `created=<n>` line in A): stop,
reset (9b) and repeat that value with `threads=128`, then with a longer hold.
Record each step as a deviation. If none works, the run is invalid (9a).

### 9d. Observables

| Observable | How to read it | When to sample | Trap |
|---|---|---|---|
| **Usage counter** — `allocatedBuffers`, a private `int` on the pool ([`HintsBufferPool.java:46`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/hints/HintsBufferPool.java#L46)), incremented only in `createBuffer()` ([`:132`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/hints/HintsBufferPool.java#L132)) and never decremented. A recycled buffer reuses its slab ([`HintsBuffer.java:96-100`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/hints/HintsBuffer.java#L96-L100)), so it also counts the direct buffers the pool owns. | Unit: read the field by reflection. Cluster: no gauge exposes it — `metrics/` holds only `HintsServiceMetrics` and `HintedHandoffMetrics` (checked 2026-09-30). Use the create trace: a Byteman rule at the exit of `createBuffer()` writes one line per buffer to `stage4.byteman.out`, `created=<allocatedBuffers> size=<bufferSize> max=<MAX_ALLOCATED_BUFFERS> ms=<epoch millis> thread=<name>`. The number of lines is the counter. | Unit: when the writer waits. Cluster: read the file at the end of each scenario; `ms` places each line in A or B. | An idle node already has one line. The periodic flush calls `currentBuffer()`, which creates the first buffer ([`HintsService.java:116-121`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/hints/HintsService.java#L116-L121), [`HintsWriteExecutor.java:168`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/hints/HintsWriteExecutor.java#L168), [`HintsBufferPool.java:93-105`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/hints/HintsBufferPool.java#L93-L105)); its `thread=` is the hints executor, not a writer. |
| **Disallow evidence** — a writer waiting at the check | (i) A second trace line, one per entry into the disallow branch, at the `BlockingQueue.take` invocation in `switchCurrentBuffer` (the location `HintsBufferPoolTest`'s rule uses): `waiting ms=<epoch millis> thread=<name>`. (ii) A thread dump, `jcmd <pid> Thread.print`: one `MutationStage` thread parked in `java.util.concurrent.LinkedBlockingQueue.take` under `HintsBufferPool.switchCurrentBuffer(HintsBufferPool.java:118)` ([link](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/hints/HintsBufferPool.java#L118)). | (i) End of each scenario. (ii) Two or three dumps during B while the hold is in force. | `take()` runs only when the reserve is empty and the cap is reached ([`:112-118`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/hints/HintsBufferPool.java#L112-L118)), and nothing else reads the property (`:41` and `:113` only; grep, 2026-09-30), so a `waiting` line belongs to this check. `switchCurrentBuffer` is `synchronized` ([`:107`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/hints/HintsBufferPool.java#L107)), so **only one** writer is in `take()`; the others are BLOCKED on the pool's monitor in the same method. Do not count parked threads. Client write timeouts are a symptom, not evidence. So is `OverloadedException: Too many in flight hints`: it comes from `checkHintOverload` (limit `128 × cores`, [`StorageProxy.java:202`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/service/StorageProxy.java#L202), [`:1592-1597`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/service/StorageProxy.java#L1592-L1597)), not from this check. |
| **Real resource** — direct memory | `bin/nodetool sjk mx -mg -b 'java.nio:type=BufferPool,name=direct' -f MemoryUsed` (bytes), and `-f Count` (number of direct buffers). Cross-check: start the JVM with `-XX:NativeMemoryTracking=summary`, then `jcmd <pid> VM.native_memory summary \| grep 'Other ('`. Direct buffers are counted under **Other** on this node's JDK; checked 2026-09-30: three `allocateDirect(32 MiB)` raised `MemoryUsed` by 100,663,296 bytes and `Count` by 3, and NMT's `Other` then read 98,314 KB (96 MiB plus 10 KB). Unit: the same beans in-process, `ManagementFactory.getPlatformMXBeans(BufferPoolMXBean.class)`. | Idle control, end of A, every 5 s during B, end of B. | The idle floor already holds one hints buffer, so the rise **above idle** is `(n − 1) × bufferSize`; the same figure is `n × bufferSize` above a node with no pool. The floor also holds the executor's 256 KiB write buffer ([`HintsWriteExecutor.java:60`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/hints/HintsWriteExecutor.java#L60), constant) and any other `allocateDirect` user, so read `Count` too: a rise of exactly *n* − 1 says only the pool moved. If it did not, the create trace decides. Each `sjk` call starts a JVM (1–2 s), so time-stamp every reading. Never use process RSS. |
| **Hints flowing** — the control for a null result | `bin/nodetool sjk mx -mg -b 'org.apache.cassandra.metrics:type=Storage,name=TotalHints' -f Count` and `bin/nodetool sjk mx -mg -b 'org.apache.cassandra.db:type=StorageProxy' -f HintsInProgress`. | Before A, and at the end of A and B. | `TotalHints` is incremented after the pool write returns ([`HintsService.java:169-171`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/hints/HintsService.java#L169-L171)), so it stops rising while writers wait. A run where it never rises had no hints: node 2 was not seen as down (`bin/nodetool status` shows `DN`), or it was never in the ring, and then the hint is discarded ([`StorageProxy.java:2801`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/service/StorageProxy.java#L2801)). `HintsInProgress` near `128 × cores` (5,120 on 40 cores) means the coordinator is about to refuse writes: stop B early. |

### 9e. Running the scenarios

**Unit tier.** Commands are in 9c; one JVM per value.

1. Run the upstream `HintsBufferPoolTest` at *n* = 2, 3 and 6. Record pass or fail.
2. Run `HintsPoolCeilingTest` at *n* = 2, 3 and 6 with `bufferSize` 1 MiB, and once
   more at *n* = 3 with 2 MiB: 3 × 2 MiB and 6 × 1 MiB are both 6 MiB, which is
   the second-knob check. The test uses `HintsBufferTest`'s hint helper
   ([`HintsBufferTest.java:196`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/test/unit/org/apache/cassandra/hints/HintsBufferTest.java#L196))
   and a flush callback that queues buffers without recycling them, as
   `HintsBufferPoolTest` does. It:
   1. asserts `MAX_ALLOCATED_BUFFERS == n`, then reads `Count` and `MemoryUsed` of the direct pool;
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
   export JVM_EXTRA_OPTS="-Dcassandra.MAX_HINT_BUFFERS=<n> -XX:NativeMemoryTracking=summary -Dstage4.byteman.out=$HOME/stage4-logs/hints/<value>/hints-pool.txt -Dstage4.hold.out=$HOME/stage4-logs/hints/<value>/hold.txt -Dstage4.hold.ms=3000 -javaagent:$PWD/build/lib/jars/byteman-4.0.20.jar=script:<harness>/hints-pool.btm,listener:true"
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
   hold in force. Every 5 s record `MemoryUsed` and `Count`; take two or three
   thread dumps; read `HintsInProgress` at the end. Then release the hold:

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
and B as above. Every `created` line should show `size=67108864`.

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
| **Stage-4 feedback** | none yet |
| **Notes** | §9 converted 2026-09-30 to the template layout (9a summary for review, 9b–9e runbook), before any stage-4 run. Moved: testability, prediction, conclusions and refutation → 9a; knob, values, scope, level, controls → 9b; workload → 9c; instruments → 9d; scenarios → 9e. **Changed, not only moved:** (1) capacity values {1, 2, 3, 6} → {2, 3, 6}: *n* = 1 is left out of the sweep; the reason is in 9b. It is not recorded as a stage-3 finding (Jingsong, 2026-09-30). (2) An idle node already holds one buffer, made by the periodic flush (`HintsService.java:116-121`); the memory rise above idle is `(n − 1) × bufferSize`, where the old text predicted `n × bufferSize` above idle. (3) Instruments: added a Byteman create trace as the usage counter, the JVM direct-buffer bean (`java.nio:type=BufferPool,name=direct`), and the NMT category (`Other`, checked 2026-09-30). (4) The cluster tier holds the flush back with a Byteman rule instead of relying on a load race; the harness (one test, two rules) is not written. (5) Dropped: the "time to first block" and "throughput falls with *n*" predictions (soft, and the hold sets them); "shrink `bufferSize`" as a way to reach the cap (`MIN_BUFFER_SIZE` clamps it at 32 MiB); "no hint is lost" at the cluster tier (only the unit tier can count hints, and `StorageProxy.checkHintOverload` can refuse writes first). (6) `HintsBufferPoolTest` range corrected from `:49-72` to `:49-73`. (7) The old open risk, whether Byteman resolves as a test dependency, is closed: `byteman-bmunit` 4.0.20 is a declared dependency. Whether its runtime attach works on this JDK is settled by the first run. |

---

## 11. Notes

- `MAX_ALLOCATED_BUFFERS` is set via a JVM system property (`-D` flag), not `cassandra.yaml` — different configuration mechanism from the memtable/net cases' YAML-backed limits, but still "Configuration" per the Limit type taxonomy since it's externally settable without a code change.
- This case was flagged as a runner-up candidate in [`../../../HANDOFF.md`](../../../../HANDOFF.md) before this draft; see `../_INDEX.md` for cross-reference.
