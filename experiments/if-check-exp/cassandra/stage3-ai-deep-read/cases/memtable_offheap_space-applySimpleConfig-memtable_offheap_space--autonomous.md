# memtable_offheap_space (startup branch in applySimpleConfig) — verification solution  <!-- file: cases/memtable_offheap_space-applySimpleConfig-memtable_offheap_space--autonomous.md -->

| Field | Value |
|---|---|
| Entry pointer | [`DatabaseDescriptor.java:591`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/DatabaseDescriptor.java#L591) (`591#1`) |
| Pinned source | `cassandra-5.0.9` |
| Session / date | Claude Opus 5.5 (claude-opus-5-5), Claude Code (CLI version not obtainable: `claude --version` failed inside the sandbox), 2026-10-24, band D triage |
| Estimate | `positive`: for `memtable_allocation_type` `offheap_buffers` or `offheap_objects` the entry is the off-heap `SubPool.limit`, and writers block when off-heap accounting would exceed it. Line 591 only chooses a log message for 0; the code behind 0 differs by type (heap fallback for `offheap_buffers`, a 0-byte off-heap limit for `offheap_objects`), and the yaml default type `heap_buffers` ignores the entry. |
| Ground | — |

## A. Constraint trace

**A1. The constraint.** `memtable_offheap_space`, configuration entry (`Config.memtable_offheap_space`, `IntMebibytesBound`), unit MiB, commented at `conf/cassandra.yaml:799`. Default when unset: `maxMemory / 4` MiB ([`DatabaseDescriptor.java:583-584`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/DatabaseDescriptor.java#L583-L584)). Line 591 logs "Global memtable off-heap threshold is disabled, HeapAllocator will be used instead" when 0, otherwise logs the threshold (`:591-594`); nothing is rejected. Read once into static `MEMORY_POOL` ([`AbstractAllocatorMemtable.java:59`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/memtable/AbstractAllocatorMemtable.java#L59), `82`): restart required.


**Limit type (2026-10-29).** config: yaml entry. The traced constraint decides ([README §6](../../../stage3-ai-deep-read/README.md#6-rules-that-hold-for-both-agents)).
**A2. What it caps.** Native (direct / `Unsafe`) memory holding memtable data for the off-heap allocation types. Operand: `MEMORY_POOL.offHeap.allocated` vs `offHeap.limit` (= value `<< 20`).

**A3. Mechanism.**
1. `offHeapLimit = getMemtableOffheapSpaceInMiB() << 20` ([`AbstractAllocatorMemtable.java:82`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/memtable/AbstractAllocatorMemtable.java#L82)).
2. Per type (`:97-110`): `heap_buffers` → `SlabPool(heapLimit, 0, …)` (off-heap value ignored); `unslabbed_heap_buffers*` → `HeapPool(heapLimit…)` (ignored); `offheap_buffers` → `SlabPool(heapLimit, offHeapLimit…)`; `offheap_objects` → `NativePool(heapLimit, offHeapLimit…)`.
3. `MemtablePool` builds `offHeap = new SubPool(maxOffHeapMemory, …)` ([`MemtablePool.java:60`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/utils/memory/MemtablePool.java#L60)).
4. `SlabPool` sets `allocateOnHeap = maxOffHeapMemory == 0` ([`SlabPool.java:28`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/utils/memory/SlabPool.java#L28)), and `SlabAllocator.allocate` charges `onHeap()` instead of `offHeap()` when that flag is set ([`SlabAllocator.java:89`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/utils/memory/SlabAllocator.java#L89)), allocating heap buffers (`:93-94`). This is the "HeapAllocator" fallback the log line describes, but only for `offheap_buffers`.
5. `NativeAllocator.allocate` always charges `offHeap()` ([`NativeAllocator.java:138-141`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/utils/memory/NativeAllocator.java#L138-L141)); with limit 0, `tryAllocate` ([`MemtablePool.java:151-161`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/utils/memory/MemtablePool.java#L151-L161)) fails for every positive size, and `needsCleaning` never fires because `used() > nextClean` is `0 > 0` ([`MemtablePool.java:125-129`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/utils/memory/MemtablePool.java#L125-L129)), so writes are expected to wait on `hasRoom` indefinitely unless the op group is blocking ([`MemtableAllocator.java:169-196`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/utils/memory/MemtableAllocator.java#L169-L196)). The log message at 592 is therefore not accurate for `offheap_objects`.
- Overshoot: blocking op groups record allocation without the check ([`MemtableAllocator.java:180-184`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/utils/memory/MemtableAllocator.java#L180-L184)). Cleaner trigger at `limit * memtable_cleanup_threshold` ([`MemtablePool.java:137-147`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/utils/memory/MemtablePool.java#L137-L147)).

**A4. Other consumers.** Other native memory: chunk cache (`file_cache_size`), networking buffer pool, Netty direct buffers, bloom filters and compression metadata (off-heap), index summaries, mmap'd files. None governed by this entry.

**A5. Evidence beyond the source.** `conf/cassandra.yaml:790-825` comments. None external.

## B. Verification solution

**B1. Claim under test.** With `offheap_objects` (and `offheap_buffers`), off-heap memtable accounting (`AllMemtablesOffHeapDataSize`, global) stays ≤ `memtable_offheap_space` (plus in-flight overshoot) and its peak scales with the knob; with value 0, `offheap_buffers` puts all memtable data on heap, and `offheap_objects` stalls writes.

### B2. Unit tier

**B2a. Environment and build.** Local clone `/local/c509` of tag `cassandra-5.0.9` (`git clone --branch cassandra-5.0.9 /path/to/shared/cassandra-src /local/c509`), `ant jar build-test`, JDK 11. Test `test/unit/org/apache/cassandra/utils/memory/MemtableOffHeapCapTest.java`; `ant testsome -Dtest.name=org.apache.cassandra.utils.memory.MemtableOffHeapCapTest`.

**Amendment 2026-10-24 (step-0 audit) — B2a, initialisation.** `MemtableOffHeapCapTest` calls `DatabaseDescriptor.daemonInitialization()` (the test yaml) in `@BeforeClass`, before it touches `AbstractAllocatorMemtable`: that class's initialiser builds the static `MEMORY_POOL` from `DatabaseDescriptor` (`AbstractAllocatorMemtable.java:59`, `:78-85`), so calling `createMemtableAllocatorPoolInternal` first fails. Every scenario passes its limits explicitly, so one class (one JVM) covers all of them. Reason: B2a left the order open.

**B2b. Knobs.** `createMemtableAllocatorPoolInternal(type, 64 MiB, offHeapLimit, 0.5f, noopCleaner)` with `type ∈ {offheap_buffers, offheap_objects}`, `offHeapLimit ∈ {0, 1 MiB, 8 MiB}`.

**B2c. Workload.** One allocator from `pool.newAllocator("t")`; writer thread calls `((SlabAllocator) a).allocate(1024, group)` or `((NativeAllocator) a).allocate(1024, group)` with `group = new OpOrder().start()`, up to 32 MiB worth of calls; no-op cleaner, so nothing is released.

**B2d. Observables and instruments.** `pool.offHeap.used()`, `pool.onHeap.used()`, writer thread state after 2 s and call count.

**B2e. Procedure.** For each (type, limit): start writer, wait 2 s, record the three observables, interrupt writer, discard pool.

**Amendment 2026-10-24 (step-0 audit) — B2e, exact steps.** "32 MiB worth of calls" is 32,768 calls of 1,024 B. The writer stops at the first of (all 32,768 calls done) or (interrupt: the wait in `MemtableAllocator.java:195` throws on interrupt). At 2 s the test records the call count, `pool.offHeap.used()`, `pool.onHeap.used()`, the largest `offHeap.used()` the writer saw after each call, and the writer's `Thread.State` (`TERMINATED` if it finished); then it interrupts and joins the writer and calls `pool.shutdownAndWait`. The B2b cleanup threshold 0.5 and the no-op cleaner `() -> ImmediateFuture.success(false)` are used as written. "≈0" in B2f means exactly 0 bytes for these direct allocator calls: `SlabAllocator.allocate` charges only one sub-pool (`SlabAllocator.java:89`) and `NativeAllocator.allocate` only `offHeap()` (`NativeAllocator.java:141`). Reason: B2e did not say what "32 MiB worth" counts or when the writer stops.

**B2f. Predictions.**
| type | offHeapLimit | offHeap.used | onHeap.used | writer |
|---|---|---|---|---|
| offheap_buffers | 1 MiB / 8 MiB | ≤ limit | ≈0 | WAITING after ≈limit/1KiB calls (±1 MiB region) |
| offheap_objects | 1 MiB / 8 MiB | ≤ limit | ≈0 | WAITING |
| offheap_buffers | 0 | 0 | grows to ≤ 64 MiB | WAITING only after 64 MiB on-heap; completes 32 MiB |
| offheap_objects | 0 | 0 | 0 | WAITING at first call |

**B2g. Readings.**
| Observation | Meaning |
|---|---|
| table above matches | mechanism as traced |
| `offHeap.used` > nonzero limit with non-blocking group | claim wrong |
| `offheap_objects`/0 completes the writes | 0-limit stall prediction wrong (perhaps an unseen fallback) |
| `offheap_buffers`/0 charges off-heap | heap-fallback claim wrong |

**Amendment 2026-10-24 (step-0 audit) — B2g, rows added; the four rows above are unchanged.** Row 1 ("table above matches") needs every B2f row, including the writer `WAITING` at the nonzero limits and at `offheap_objects`/0 (the direct evidence that the disallow branch fired). Added rows:

| Observation | Meaning |
|---|---|
| `offheap_buffers`/0: writer `WAITING` before 32,768 calls, or `onHeap.used` stays 0 | heap-fallback claim wrong (no fallback, or a limit other than the 64 MiB heap pool) |
| nonzero limit: writer neither `WAITING` nor finished at 2 s, or ended with an exception | invalid run for that scenario (the limit was not exercised) |
| an off-heap type at a nonzero limit charges `onHeap` (> 0) | mechanism differs from the trace (A3 step 4-5): not confirmed |
| a B2h control does not behave as stated in its amendment | the blocking cannot be attributed to the knob: not confirmed |

**B2h. Controls.** `offHeapLimit = Long.MAX_VALUE` → writer never blocks. Swap type to `heap_buffers` with offHeapLimit 1 MiB → off-heap unused (`offHeap.used` stays 0), showing the entry is ignored for that type.

**Amendment 2026-10-24 (step-0 audit) — B2h, sizes and expected outcomes.** (i) `offHeapLimit = Long.MAX_VALUE` for each of `offheap_buffers` and `offheap_objects`, 32,768 calls: all calls return, the writer is never `WAITING` (state `TERMINATED` at 2 s), `offHeap.used()` = 33,554,432 (32 MiB). (ii) `heap_buffers` with `offHeapLimit` 1 MiB, 32,768 calls: `offHeap.used()` = 0, `onHeap.used()` = 32 MiB, writer `TERMINATED` (`createMemtableAllocatorPoolInternal` passes 0 off-heap for that type, `AbstractAllocatorMemtable.java:100-102`). Reason: B2h gave neither sizes nor exact outcomes.

### B3. Cluster tier

**B3a. Environment and build.** One Linux node from `/local/c509` (`ant jar`), data/commitlog/hints/saved_caches under `/local/c509-node` (≥20 GB free). `MAX_HEAP_SIZE=2G HEAP_NEWSIZE=400M`; add `-XX:NativeMemoryTracking=summary` to `conf/jvm-server.options`. `memtable_heap_space: 512MiB` (fixed).

**B3b. Knobs.** (a) `memtable_allocation_type: offheap_objects` with `memtable_offheap_space` ∈ {`64MiB`, `256MiB`}; (b) `offheap_buffers` with `0MiB`; (c) `offheap_objects` with `0MiB`. Fresh node for each.

**Amendment 2026-10-24 (step-0 audit) — B3b, default value added.** (a) also runs with `memtable_offheap_space` **unset** (the default, `maxMemory / 4` MiB, `DatabaseDescriptor.java:583-584`; the knob in force is read from the startup line at `:594`). Order: (a) 64 MiB, 256 MiB, unset; (b); (c); then the B3h control. Reason: the core question needs at least three values including the default (README, audit group A); (a) had two.

**B3c. Workload.** `tools/bin/cassandra-stress write n=3000000 cl=ONE -col n=FIXED(5) size=FIXED(200) -rate threads=64 -schema "replication(factor=1)"` (≈3 GB of values, ≥10× the largest limit). For (c), a 60 s attempt with `duration=60s` instead of `n=`.

**B3d. Observables and instruments.** 1 s sampling of `nodetool sjk mx -b "org.apache.cassandra.metrics:type=Table,name=AllMemtablesOffHeapDataSize" -mg -f Value` and `…name=AllMemtablesOnHeapDataSize`; `jcmd <pid> VM.native_memory summary` every 10 s (`Other`/`Internal` categories, where `Unsafe.allocateMemory` and direct buffers appear); stress op rate; `logs/system.log` for "Flushing largest" and the line-592/594 messages.

**Amendment 2026-10-24 (step-0 audit) — B3d, instruments.** (1) Correction: `AllMemtablesOffHeapDataSize` / `AllMemtablesOnHeapDataSize` sum the **current** memtable of each table and its indexes (`TableMetrics.java:506-521`); memtables being flushed are not counted, so the gauges read at or below the pool's `allocated`. Added observable from the log: the `Used total: <on>/<off>` field of each `Flushing largest` line is `MEMORY_POOL.onHeap/offHeap.usedRatio()` at the trigger, flushing memtables included (`AbstractAllocatorMemtable.java:289-295`); off-heap pool bytes = the second ratio × knob. (2) Sampling: the two gauges, `org.apache.cassandra.metrics:type=MemtablePool,name=BlockedOnAllocation` `Count` and `org.apache.cassandra.metrics:type=Table,name=WriteLatency` `Count` (local writes completed: updated after `mt.put` returns, `ColumnFamilyStore.java:1477-1484`) are read every 1 s over one JMX connection (harness sampler), because each `nodetool` call starts a JVM; one `nodetool sjk mx` read of the off-heap gauge at the start and end of each run cross-checks the sampler. The sampler stops 10 s after stress exits. (3) Correction: `offheap_objects` memory is **not** `Unsafe.allocateMemory`: `NativeAllocator` regions come from `MemoryUtil.allocate` → `com.sun.jna.Native.malloc` (`NativeAllocator.java:176,190`, `MemoryUtil.java:81-84`), which the JVM's NMT does not track (checked on this machine before any run: a JVM holding 200 MiB of `Native.malloc` showed NMT `Other` 2 KB, `Internal` 555 KB). NMT is kept as written (every 10 s; it still sees direct buffers, e.g. `offheap_buffers` regions and Netty), and the real native resource is read as the daemon's **resident set size** (`ps -o rss= -p <pid>`) every 2 s; the heap is pre-touched (`-XX:+AlwaysPreTouch`, `conf/jvm-server.options:128`), so RSS growth during stress is native growth plus mapped file pages. "NMT native growth" in B3f is read as RSS growth: peak RSS during stress minus the last RSS sample before stress. (4) For (c), a thread dump (`jcmd <pid> Thread.print`) at the moment a stall is judged (120 s after start if startup has not completed, or 60 s into stress) — the number of threads whose stack contains `MemtableAllocator$SubAllocator.allocate` is the direct evidence of where writes wait. Reason: the gauge's scope and the NMT category are citation errors found by reading the source; `nodetool` cannot keep a 1 s cadence; (c) had no observable that ties a stall to the allocator.

**B3e. Procedure.** Configure → start → wait UN → start samplers → stress → stop samplers → `nodetool drain` → stop → wipe `/local/c509-node` → next knob. For (c), record whether startup completes (`nodetool status` UN within 120 s) and stress op rate.

**Amendment 2026-10-24 (step-0 audit) — B3e, stop conditions.** "Startup completes" means `nodetool status` shows `UN 127.0.0.1` **and** `nodetool statusbinary` prints `running`; the other runs wait up to 360 s for it and abort otherwise. For (c): if startup has not completed 120 s after launch, take the B3d thread dump and `kill -9` the daemon (no drain, no stress). If it completes, run stress `duration=60s` under an outer limit of 180 s (stress is killed then), take the thread dump 60 s into stress, and stop the node with `drain` bounded to 60 s, then `kill -9` if it is still alive. Each run ends with `ps -eo command | grep '[C]assandraDaemon'` and `pgrep -f cassandra-stress` empty and the node directory wiped. Reason: a stalled node does not drain, and B3e had no bound for stress or the drain.

**B3f. Predictions.** (a) peak off-heap gauge ≤ 64 MiB×1.05 and ≤ 256 MiB×1.05 respectively, with 64 < 256; NMT native growth during stress bounded by ≈ the knob plus other consumers (difference between runs ≈ 192 MiB). (b) off-heap gauge 0 throughout; on-heap gauge rises up to ≤ 512 MiB; log line 592 present. (c) log line 592 present; write path stalls: stress op rate falls to 0 or the node fails to finish startup (system-table writes block).

**Amendment 2026-10-24 (step-0 audit) — B3f, the added default value and the RSS reading.** (a, unset) peak off-heap gauge ≤ 1.05 × the startup-logged default (512 MiB expected at a 2 GiB G1 heap), and the three peaks are strictly ordered 64 < 256 < default. The native-growth sentence is read through B3d (3): RSS growth of a run minus RSS growth of the B3h control (where memtable data is on the pre-touched heap, so its RSS growth is the "other consumers") ≤ 1.05 × knob + 64 MiB (64 MiB: allocator region slack of up to 1 MiB per table allocator, `NativeAllocator.java:46`, plus run-to-run variation of mapped index pages and Netty buffers; fixed before any reading); "≈ 192 MiB" means RSS growth(256 MiB) − RSS growth(64 MiB) between 96 and 288 MiB (± 50 %). Reason: the default was not a value (B3b amendment), and NMT cannot see this memory (B3d amendment).

**B3g. Readings.**
| Observation | Meaning |
|---|---|
| (a) peaks ≤ knob and ordered | claim confirmed |
| (a) gauge exceeds knob persistently | cap not binding (claim wrong) |
| (b) off-heap gauge > 0 | heap-fallback claim wrong |
| (c) writes proceed normally | stall prediction wrong (log message accurate after all) |

**Amendment 2026-10-24 (step-0 audit) — B3g, definitions and rows added; the four rows above are unchanged.** "Persistently" in row 2 means at least 3 consecutive 1 s samples above 1.05 × knob. Row 1 also needs, in every (a) run, direct evidence that the off-heap limit acted — at least one `Flushing largest` line (with `Reason: MEMTABLE_LIMIT` on its `Enqueuing flush` line) whose off-heap `Used total` ratio is ≥ its on-heap ratio, or `BlockedOnAllocation` > 0 — and a valid workload (3,000,000 partitions, 0 errors). "Writes proceed normally" in row 4 means a stress op rate ≥ 50 % of run (a) 64 MiB's. Added rows:

| Observation | Meaning |
|---|---|
| (a) peaks not strictly ordered 64 < 256 < default | usage does not follow the knob: not confirmed |
| (a) a run with no `MEMTABLE_LIMIT` flush led by the off-heap ratio and `BlockedOnAllocation` = 0 | the off-heap limit was not reached in that run: not confirmed for that value |
| (a) off-heap `Used total` ratio > 1.05 at any trigger | the pool itself exceeded the limit: cap not binding (claim wrong) |
| (a) RSS growth − control RSS growth > 1.05 × knob + 64 MiB | counter capped but the real resource grows: not confirmed (accounting bypassed) |
| stress errors > 0 or fewer than 3,000,000 partitions in (a), (b) or the control | invalid run for that value |
| (b) on-heap gauge also stays < 1 MiB during stress | memtable data counted in neither pool: heap-fallback claim not confirmed |
| (b) or (c) startup logs line 594 ("enabled at 0MiB") instead of 592 | the startup branch differs from A1: claim wrong on the message |
| (c) startup not complete in 120 s, or < 1,000 local writes completed (`WriteLatency` Count delta) in the stress window; **and** the thread dump shows ≥ 1 thread in `MemtableAllocator$SubAllocator.allocate` | stall confirmed at the allocator (the line-592 message is inaccurate for `offheap_objects`) |
| (c) a stall as above but no thread in `MemtableAllocator$SubAllocator.allocate` | stall from another cause: not confirmed |
| (c) ≥ 1,000 local writes but op rate < 50 % of (a) 64 MiB's | partial stall: not confirmed |
| control: off-heap gauge > 0, or the on-heap gauge does not rise | the entry is not ignored for `heap_buffers` (B3h fails): the type-scope statement of the Estimate is wrong |

**B3h. Controls.** Run `heap_buffers` with `memtable_offheap_space: 64MiB`: off-heap gauge 0 (entry ignored for the default type), on-heap gauge rises. Confirm flush reason `MEMTABLE_LIMIT` in logs to exclude commit-log-space flushes.

**B4. Risks and cleanup.** Up to ≈4 GB under `/local/c509-node`. Case (c) may hang: kill with `pkill -9 -f CassandraDaemon` after 120 s; always check `pgrep -f CassandraDaemon` and `pgrep -f cassandra-stress` empty; `rm -rf /local/c509-node`.

## C. Sources read

src/java/org/apache/cassandra/config/DatabaseDescriptor.java (583-594, 4055-4065)
src/java/org/apache/cassandra/db/memtable/AbstractAllocatorMemtable.java (59, 78-112)
src/java/org/apache/cassandra/utils/memory/MemtablePool.java (55-260)
src/java/org/apache/cassandra/utils/memory/MemtableAllocator.java (165-200)
src/java/org/apache/cassandra/utils/memory/SlabPool.java (20-35)
src/java/org/apache/cassandra/utils/memory/SlabAllocator.java (80-100)
src/java/org/apache/cassandra/utils/memory/NativeAllocator.java (130-145)
src/java/org/apache/cassandra/metrics/TableMetrics.java (500-530)
conf/cassandra.yaml (790-825)

## D. Stage-4 feedback

**Stage 4 closed 2026-10-24** ([results](../../stage4-runtime-verification/results/memtable_offheap_space-applySimpleConfig-memtable_offheap_space--autonomous.md)); Claude Opus 5.5 (claude-opus-5-5), advisor's machine; estimate `positive` held. **Unit tier: Confirmed — caps** (both off-heap types stop the writer at exactly 1 · 8 MiB after limit/1024 calls, nothing charged on-heap; at 0, `offheap_buffers` puts all 32 MiB on the heap pool and completes, `offheap_objects` blocks at the first call; controls: no limit → all calls, `heap_buffers` → off-heap 0). **Cluster tier: Confirmed — caps** (`AllMemtablesOffHeapDataSize` peaks 21.2 · 82.8 · 160.6 MiB at 64 · 256 · 512 MiB (unset), all ≤ knob and ordered; `MEMTABLE_LIMIT` flushes led by the off-heap ratio 152 · 38 · 19; `BlockedOnAllocation` 1,260 · 0 · 0; (b) `offheap_buffers`/0: off-heap gauge 0, on-heap to 166.6 MiB, line 592 logged; (c) `offheap_objects`/0: line 592 logged, startup never completed (120 s), `main` waiting in `MemtableAllocator$SubAllocator.allocate` (`:195`); control `heap_buffers`: off-heap gauge 0). Notes for stage 3, not applied: the (c) stall is not at a system-table write as B3f's parenthetical says, but in `SkipListMemtable`'s class initialiser (`SkipListMemtable.java:79`, `:215-228`, row-overhead estimate cloning a key through `MEMORY_POOL`), reached from the startup checks about 1 s after launch, before JMX listens; `NativeAllocator` memory comes from JNA `Native.malloc` (`MemoryUtil.java:81-84`), invisible to NMT, and the RSS substitute is unreliable on macOS (RSS fell below the heap size mid-run); peaks sit near knob/3 (cleanup threshold 1/3; the gauge omits flushing memtables); at 256 and 512 MiB no writer blocked. The nine amendments of 2026-10-24 (B2a, B2e, B2g, B2h, B3b, B3d, B3e, B3f, B3g) were made at the step-0 audit; the frozen hash is in `_INDEX.md` §4, and this section was added after it.
