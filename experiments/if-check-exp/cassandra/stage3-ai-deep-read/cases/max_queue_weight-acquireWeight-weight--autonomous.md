# max_queue_weight (BinLog / WeightedQueue) — verification solution  <!-- file: cases/max_queue_weight-acquireWeight-weight--autonomous.md -->

| Field | Value |
|---|---|
| Entry pointer | [`WeightedQueue.java:283`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/utils/concurrent/WeightedQueue.java#L283); this file also covers `:305#1` and `:324#1` (same check in `tryAcquireWeight` and `releaseWeight`) |
| Pinned source | `cassandra-5.0.9` |
| Session / date | Claude Opus 5.5 (claude-opus-5-5[1m]), Claude Code stage-3 autonomous agent, 2026-10-26 |
| Estimate | `positive`. The three target checks are guards on the weigher's output (`weight < 1` throws). They are not the cap themselves. They protect the accounting of `WeightedQueue.maxWeight`, which is set from `max_queue_weight` (full query log and audit log). That cap does bound the heap held by records queued for the bin-log writer: a semaphore of `maxWeight` permits, one permit per estimated byte. The overshoot is bounded: one overweight record, plus up to 16 records the writer has already dequeued, plus records that producers are still building. |
| Ground | — |

## A. Constraint trace

**A1. The constraint.** `max_queue_weight`, a configuration entry in
`BinLogOptions` ([`BinLogOptions.java:49`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/utils/binlog/BinLogOptions.java#L49),
`public int max_queue_weight = 256 * 1024 * 1024;`). It is inherited by
`FullQueryLoggerOptions` (`fql/FullQueryLoggerOptions.java:25`) and `AuditLogOptions`
(`audit/AuditLogOptions.java:37`). Those two are the yaml blocks
`full_query_logging_options` and `audit_logging_options` (`config/Config.java:703-704`,
`conf/cassandra.yaml:1906` and `:1921`, both commented out with value `268435456 # 256 MiB`).
- Unit: bytes, as estimated by `ObjectSizes`. It is a plain `int`, not a `DataStorageSpec`, so the largest value is about 2 GiB.
- Default: 256 MiB, a literal constant.
- How to set it:
  - yaml (needs a restart, or takes effect at the next enable);
  - `nodetool enablefullquerylog --max-queue-weight <n>` (`tools/nodetool/EnableFullQueryLog.java:35-36`; the sentinel `Integer.MIN_VALUE` falls back to the yaml value, `service/StorageService.java:7137`);
  - `nodetool enableauditlog --max-queue-weight <n>` (`tools/nodetool/EnableAuditLog.java:58`);
  - the JMX equivalents.
  - No restart is needed: disable the log, then enable it again with the new value.
- Validation: the value must be > 0 (`utils/binlog/BinLog.java:138`, `:400`; [`WeightedQueue.java:273`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/utils/concurrent/WeightedQueue.java#L273)).


**Limit type (2026-10-29).** config: yaml entry. The traced constraint decides ([README §6](../../../stage3-ai-deep-read/README.md#6-rules-that-hold-for-both-agents)).
**A2. What it caps.** Heap, plus Netty pooled direct memory for the query-options
buffer, held by bin-log records waiting in `BinLog.sampleQueue` for the single
"Binary Log thread" to write them to Chronicle Queue files. The quantity compared
against the limit is the sum of `weight()` over queued records. It is tracked as
`maxWeight - availableWeight.permits()` (`WeightedQueue.java:65`, `:277`).
- FQL `Query.weight()` = shallow size + query string deep size + ByteBuf shell + `queryOptionsBuffer.capacity()` + keyspace string (`fql/FullQueryLogger.java:366-370`, `:556-560`).
- FQL `Batch.weight()` is precomputed in the constructor (`:403-420`).
- Audit `Message.weight()` = shallow size + log-string deep size (`audit/BinAuditLogger.java:136-139`).

**A3. Mechanism.**
1. The producer (the request thread) builds a record: `FullQueryLogger.querySuccess` → `new Query(...)`. This allocates `queryOptionsBuffer` from `CBUtil.allocator`, which is pooled direct memory by default (`transport/CBUtil.java:60`; `fql/FullQueryLogger.java:485`). The producer then calls `binLog.logRecord` (`:320-321`).
2. `BinLog.logRecord` (`utils/binlog/BinLog.java:295-330`) branches on `block`:
   - `block=true` (the default, [`BinLogOptions.java:43`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/utils/binlog/BinLogOptions.java#L43)): `put()` loops `sampleQueue.offer(record, 1, SECONDS)` until accepted (`:221-227`). The producer blocks while the queue is full.
   - `block=false`: `offer()`. On failure the record is dropped, `logDroppedSample()` runs (the NoSpam warning "Dropped {} binary log samples", `:74`, `:337-342`), and the record's buffer is released (`:326-328`).
3. `WeightedQueue.offer(t)` → `tryAcquireWeight` ([`WeightedQueue.java:72-93`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/utils/concurrent/WeightedQueue.java#L72-L93), `:302-314`). The timed offer goes through `acquireWeight` (`:136-158`, `:280-300`).
   - The weight comes from the weigher (`NATURAL_WEIGHER`, `:53-60`).
   - **Target check**: `if (weight < 1) throw IllegalArgumentException` (`:283`, `:305`).
   - The weight is clamped to `maxWeight` (`:289`, `:311`). This lets exactly one overweight element in.
   - Then it acquires that many semaphore permits (`:293`, `:297`, `:313`). If it cannot, the non-blocking offer returns false and the timed offer times out.
4. The consumer: `BinLog.run` → `sampleQueue.take()` plus `drainTo(tasks, 15)` ([`BinLog.java:254-256`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/utils/binlog/BinLog.java#L254-L256)). Each removal calls `releaseWeight` ([`WeightedQueue.java:100-105`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/utils/concurrent/WeightedQueue.java#L100-L105), `:160-165`, `:316-333`).
   - **Target check** at `:324`: it throws on weight < 1 *after* the element has left the wrapped queue. The permits would leak, so the cap would shrink.
   - The records are written ([`BinLog.java:241`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/utils/binlog/BinLog.java#L241)) and then `release()`d (`:266-269`).
5. Overshoot and bypass paths:
   - (a) A record weighing more than `maxWeight` is admitted when the queue is empty, because of the clamp.
   - (b) Up to 16 records are in the writer's `tasks` list after their permits were released ([`BinLog.java:254-256`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/utils/binlog/BinLog.java#L254-L256), `:266-269`).
   - (c) Records under construction in producer threads, plus records waiting in `put()`'s retry loop, are not counted.
   - (d) `NO_OP` and any non-`Weighable` element weigh 1 ([`WeightedQueue.java:59`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/utils/concurrent/WeightedQueue.java#L59)).
   - (e) Weights are estimates. For Batch, direct `ByteBuffer` values count only as `DIRECT_BUFFER_DEEP_SIZE` (`utils/ObjectSizes.java:171-172`), so they may be undercounted.
   - (f) A weight that changes after insertion corrupts the accounting (class Javadoc, [`WeightedQueue.java:42-44`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/utils/concurrent/WeightedQueue.java#L42-L44)).
   - The guards at the target lines only fire if `weight()` returns ≤ 0. For the real records this cannot happen, because `EMPTY_SIZE` > 0. Sizes over 2 GiB throw in `Ints.checkedCast` instead.

**A4. Other consumers.**
- The Chronicle Queue memory-mapped segment files: page cache, and disk bounded separately by `max_log_size` (`BinLogOptions.java:54`, through `DeletingArchiver`, `BinLog.java:449`).
- The client request buffers themselves (`native_transport_max_request_data_in_flight*`).
- The general Netty pool.
- The audit-log and FQL `BinLog`s each have their own queue and cap. Both can be active at once, so the total is up to 2 × max_queue_weight.

**A5. Evidence beyond the source.**
- `doc/modules/cassandra/pages/managing/operating/fqllogging.adoc:125-128` ("maximum weight of in-memory queue for records waiting to be written to the file before blocking or dropping").
- `doc/modules/cassandra/pages/managing/operating/audit_logging.adoc:184-187`.
- `test/unit/org/apache/cassandra/utils/concurrent/WeightedQueueTest.java` (`offerFullFails` :196-199; permits accounting :206-231, :350-357).
- `test/unit/org/apache/cassandra/utils/binlog/BinLogTest.java` (the queue weight-10 setup :72-81; the blocking-writer pattern :221-306).

## B. Verification solution

**B1. Claim under test.** With the bin-log writer slower than the producers, the
estimated weight of records queued in a `BinLog` never exceeds `max_queue_weight`
plus one record, and the writer's in-flight batch of ≤ 16 records comes on top of
that. On a node, the extra heap retained by full-query-log backlog therefore grows
with `max_queue_weight` and plateaus at about `max_queue_weight`. A weigher result
< 1 is rejected (`:283`/`:305`) and, on removal (`:324`), leaks permits.

### B2. Unit tier

**B2a. Environment and build.**
- JDK 11 and Ant.
- Clone the tag to local disk: `git clone --branch cassandra-5.0.9 --depth 1 /Users/yangwang/cassandra-src /local/c509 && cd /local/c509 && ant jar build-test`.
- Put the new tests at:
  - `test/unit/org/apache/cassandra/utils/concurrent/WeightedQueueCapTest.java` (in the same package, so it can reach the package-private `availableWeight`);
  - `test/unit/org/apache/cassandra/utils/binlog/BinLogCapTest.java` (in the same package, so it can reach `sampleQueue`; it reads `availableWeight.permits()` by reflection).
- Run with `ant testsome -Dtest.name=org.apache.cassandra.utils.concurrent.WeightedQueueCapTest` and the same for `BinLogCapTest`, using the default test JVM options.

> **Amendment U1 (2026-10-27, stage-4 audit; host paths and build).** On the advisor's Mac (no `/local`): full clone
> `git clone --branch cassandra-5.0.9 ~/cassandra-src $W/cassandra-run62` (`W=~/Library/Caches/stage4`, `source $W/env.sh`),
> built with `ant -Dlocal.repository=$W/m2 build-test` (this also builds the jar, so `ant jar` is not run separately). The two test
> classes are kept in `harness/max_queue_weight-acquireWeight-weight--autonomous/` (`WeightedQueueCapTest.java`, `BinLogCapTest.java`),
> copied into the clone's `test/unit/.../utils/concurrent/` and `.../utils/binlog/` by `unit-run.sh` and removed afterwards. Each class runs
> with `ant -Dlocal.repository=$W/m2 testsome -Dtest.name=<class>`, plus `_JAVA_OPTIONS=-Xmx4g` (the forked test JVM gets
> `maxmemory="1024m"`, `build.xml:1153`, which ant turns into an `-Xmx1024m` after the `-Dtest.jvm.args` of `:1192`, so only
> `_JAVA_OPTIONS` raises the heap; U2 needs about 0.6 GB retained at once) and the flag of U2. Readings are the `MQW ...` stdout lines in `build/test/logs/.../TEST-<class>.log`.

**B2b. Knobs.** `maxWeight` ∈ {1 MiB, 8 MiB, 64 MiB}, passed to `new WeightedQueue<>(M)` /
`new BinLog.Builder().maxQueueWeight(M)`. These span ×64, and each is far larger than
one record. Also an overweight case with M = 64 KiB and a record of weight about 128 KiB.

> **Amendment U2 (2026-10-27, stage-4 audit; the default value and the real-memory instrument).** (a) A fourth value, the
> default `M = 256 MiB` (268,435,456; `BinLogOptions.java:49`), is added to B2b and to every per-M step (queue and BinLog), so
> the knob is varied over 1, 8, 64 and 256 MiB. (b) The queued record's options buffer comes from `CBUtil.allocator`
> (`FullQueryLogger.java:485`), which is pooled **direct** memory by default (`CBUtil.java:59-60`); a heap delta cannot see it, so
> B2f's "heap delta ≈ W" could not hold under the default allocator whatever the cap does. The test JVM therefore runs with
> `-Dtest.jvm.args=-Dcassandra.netty_use_heap_allocator=true`, under which `CBUtil.allocator` is `UnpooledByteBufAllocator(false)`
> and every options buffer is an exact-size heap `byte[]`; the cap logic (`WeightedQueue`) is unchanged and `w` is still read as
> `q.weight()` (it now includes the heap buffer's shell). Gap named: the pooled direct case of a default node is not measured.
> (c) The heap delta is `Runtime.totalMemory() - freeMemory()` after three `System.gc()` calls (200 ms apart), taken before the
> first offer and after the last, with the queue still holding the accepted records. (d) The B2h controls use the offers of the
> largest M: `ceil(2 * 256 MiB / w)` records.

> **Runbook-defect fix D1 (2026-10-27, found by the unit shakedown before run 1; replaces U2(c)'s instrument, no band changed).**
> `Runtime.totalMemory() - freeMemory()` read 200 ms after the last `System.gc()` also counts what the test JVM's background threads
> allocated in eden since that GC, which is of the order of the smallest W (1 MiB). The heap reading is now the sum, over the heap
> memory pools, of `MemoryPoolMXBean.getCollectionUsage().getUsed()` (each pool's usage after the most recent collection) read right
> after the last of three `System.gc()` calls; the test JVM's CMS runs `System.gc()` as a stop-the-world full collection (no
> `ExplicitGCInvokesConcurrent` in `build.xml:231-243`). U4's bands and every other step are unchanged.

**B2c. Workload.**
- Records are `FullQueryLogger.Query("INSERT INTO ks.t (k,v) VALUES (?,?)", QueryOptions.forInternalCalls(ConsistencyLevel.ONE, List.of(int(1), ByteBuffer.allocate(4096))), QueryState.forInternalCalls(), System.currentTimeMillis())`. Call `DatabaseDescriptor.daemonInitialization()` in `@BeforeClass`, as `BinLogTest:66-70` does.
- Each record weighs about 4.3 KB. Read the exact value as `w = q.weight()`.
- Offer `ceil(2·M/w)` records: about 488 / 3,900 / 31,200 for the three values of M. That is double the cap, so the limit is reached.
- Guard tests: a `Weighable` returning 0, and one returning -1. A mutable `Weighable` that returns 5 on insert and 0 on removal.
- BinLog test: block the writer with the blocking-record pattern from `BinLogTest:233-266`, then call `binLog.offer(record)` 2·M/w times with `block=false`.

**B2d. Observables and instruments.**
- In-process counters: number accepted N_acc, Σ weight of accepted records W, `availableWeight.permits()`, and the offer return values.
- For BinLog, the same, via reflection on `sampleQueue.availableWeight`.
- Optional: `Runtime.totalMemory()-freeMemory()` after `System.gc()`, taken before and after filling, as a coarse heap delta.
- Not directly observable: the direct-memory share of `queryOptionsBuffer`, beyond its `capacity()`.

**B2e. Procedure.**
1. For each M: create the queue, offer records until `offer` returns false, then keep offering to 2·M/w. Record N_acc, W and permits.
2. Overweight: with M = 64 KiB and the queue empty, offer one 128 KiB-valued Query (expect true). Then offer a small record (expect false). Read permits.
3. Guards: offer the weight-0 and weight-(-1) Weighables. Expect `IllegalArgumentException` and permits still M.
4. Leak: offer the mutable item (weight 5), flip it to 0, call `poll()`. Expect `IllegalArgumentException`, and permits stay at M-5 even though the wrapped queue is now empty.
5. BinLog: build it with M, block the writer, offer 2·M/w records, record the accepted count and permits. Release the writer, wait for `permits()==M` (spin, 60 s), then `binLog.stop()`.

> **Amendment U3 (2026-10-27, stage-4 audit; exact procedure and output).** All in the two harness classes; each reading is
> one stdout line. `WeightedQueueCapTest`: `cap` (step 1, per M: offer `ceil(2M/w)` records with value 4,096 B, release each refused
> one; line `MQW CAP M w wmin wmax nOff nAcc W permits firstFalse trueAfterFalse floorMw MminusW h0 h1 dH dHoverW`, then drain and
> `MQW CAPDRAIN`); `overweight` (step 2, `MQW OVER`; also polls the big record and reads permits); `guards` (step 3, M = 1 MiB: the
> weight-0 and weight-(-1) items are each offered on a fresh queue through `offer(t)`, which reaches the check at `:305`, and through
> `offer(t, 1, SECONDS)` and `put(t)`, which reach `:283`; the IAE's throwing frame is printed (`tryAcquireWeight:307` /
> `acquireWeight:285`, the `throw` statements of the two checks); `MQW GUARD weight path result permits M`); `leak` (step 4, M = 1 MiB:
> the item weighs 5 on `offer`, is set to 0, then `poll()`; the throwing frame (`releaseWeight:326`) and permits after the poll and after
> a second `poll()` are printed; `MQW LEAK`); `controls` (B2h, `MQW CTRLMAX` with heap after each quarter of the offers, and
> `MQW CTRLLBQ`). `BinLogCapTest.binLogCap` (step 5, per M): `BinLog.Builder().path(<temp dir>).rollCycle("TEST_SECONDLY")
> .maxQueueWeight(M).maxLogSize(4 GiB).blocking(false).build(false)`; the blocking record of `BinLogTest:233-266` is `put`, the test
> waits (60 s spin) until its `writeMarshallablePayload` has signalled, reads permits, then calls `binLog.offer(q)` `ceil(2M/w)` times
> (refused records released); line `MQW BINLOG M writerBlocked permitsBefore w nOff nAcc W permits firstFalse trueAfterFalse floorMw
> MminusW`; then releases the writer, spins until permits = M (60 s), `stop()`s, deletes the directory, `MQW BINLOGDRAIN M permits
> restored ms`. Each class prints `MQW ENV` (allocator class, `useHeap`, `maxMemory`) first.

**B2f. Predictions.**
- For each M: W ≤ M, and M − W < w. N_acc = floor(M/w): about 243 / 1,950 / 15,600. permits = M − W. Every offer after the first false is also false.
- Heap delta ≈ W, within ±20% (the estimate error).
- Overweight: first offer true, permits = 0, second offer false.
- Guards: an IAE each time, permits unchanged.
- Leak: permits = M−5 after the poll.
- BinLog: the same N_acc as the queue (± the 1 blocking record of weight 1).

> **Amendment U4 (2026-10-27, stage-4 audit; exact predictions, no filed relation changed).** All records of one run have the
> same weight (same query string, same 4,113-byte V3 options encoding: consistency 2 + flags 1 + count 2 + (4+4) + (4+4,096) bytes,
> `QueryOptions.java:62-64`), so `wmin = wmax = w`; from source `w` = Query shell + query-string deep size + ByteBuf shell + 4,113,
> expected within [4,150, 4,500] B (validity check, not a verdict input). Per M ∈ {1, 8, 64, 256} MiB: `nAcc = floor(M/w)` exactly
> (about 243 / 1,950 / 15,600 / 62,400), `W = nAcc·w ≤ M`, `M − W < w`, `permits = M − W`, `firstFalse = nAcc`, `trueAfterFalse = 0`,
> `CAPDRAIN permits = M`; `nAcc` ratios between consecutive M follow the M ratios (×8, ×8, ×4) up to the floor; `dH/W` ∈ [0.8, 1.2].
> Overweight: `first = true`, `permitsAfterFirst = 0`, `second = false`, `permitsAfterSecond = 0`, `permitsAfterPoll = 65,536`.
> Guards: all six calls throw IAE (offer at `tryAcquireWeight:307`, timed offer and put at `acquireWeight:285`), permits = 1,048,576
> after each. Leak: IAE at `releaseWeight:326`, `permitsAfterPoll = permitsAfterNext = 1,048,571`, `nextPoll = null`. BinLog per M:
> `writerBlocked = true`, `permitsBefore = M`, `|nAcc − floor(M/w)| ≤ 1`, `trueAfterFalse = 0`, `restored = true`. Controls:
> `CTRLMAX nAcc = nOff`, its `dH/W` ∈ [0.8, 1.2] and each quarter's heap increment within ±20% of `dH/4`; `CTRLLBQ perRecord`
> within ±20% of `w`.

**B2g. Readings.**

| Observation | Meaning |
|---|---|
| W ≤ M, M−W < w, and N_acc scales ×8 between M values | Cap works as traced (claim holds) |
| W > M + w, or N_acc does not change with M | Claim wrong: the cap does not bound queued weight |
| Overweight admitted, then everything refused | Clamp behaves as documented (one-overweight overshoot) |
| Weight-0 item accepted without exception | Guard missing, so zero-cost elements could fill memory without bound (claim wrong for :283/:305) |
| permits not restored after the bad poll | :324 leak confirmed (cap shrinks, does not grow) |
| Heap delta ≫ W (more than 2×) | Weights underestimate real retention; cap binds its estimate but not actual heap |

> **Amendment U5 (2026-10-27, stage-4 audit; verdict words and missing rows).** Checked in this order; the first that applies is
> the verdict. (1) **Invalid**: a class does not run to its end, an `MQW` line is missing, `MQW ENV` does not show the unpooled heap
> allocator, `w` is outside [4,150, 4,500], or `writerBlocked = false`. (2) **Refuted — does not cap**: for some M `W > M` (beyond the one
> overweight element) or `nAcc` does not change with M, or a weight-0 / weight-(-1) item is accepted without an exception (row 4).
> (3) **Not confirmed**: any other U4 value missed, including `dH/W` outside [0.8, 1.2] (row 6 if above 2: the cap binds its
> estimate, not the heap), permits restored after the bad poll (B1's leak clause wrong), a BinLog `nAcc` off by more than 1, or a
> control out of band. (4) **Confirmed — caps**: every U4 value holds (rows 1, 3 and 5 together; direct disallow evidence = the refused
> offers after the first refusal and the IAEs at the target lines).

**B2h. Controls.**
- Run with M = Integer.MAX_VALUE and the same offers: all are accepted and the heap delta grows linearly. This shows the workload itself can move usage.
- Run a plain `LinkedBlockingQueue` with the same records to give the per-record heap cost.
- Record `w` for each run so the arithmetic can be checked.

### B3. Cluster tier

**B3a. Environment and build.**
- One Linux node built from `/local/c509` (`ant`). Use `-Xms4G -Xmx4G` with the default G1 (`conf/jvm11-server.options`).
- Put data, commitlog, hints and `full_query_logging_options.log_dir` on local disk with at least 20 GB free.
- Make the writer slow with Byteman, which is already a test dependency (`.build/parent-pom-template.xml:40`, version 4.0.20). Locate the jar with `find build -name 'byteman-4.0.20.jar'`. Put this rule in `/local/slow-binlog.btm`:
  ```
  RULE slow binlog writer
  CLASS org.apache.cassandra.utils.binlog.BinLog
  METHOD processTasks
  AT ENTRY
  IF true
  DO delay(50)
  ENDRULE
  ```
- Start with `JVM_EXTRA_OPTS="-javaagent:<byteman.jar>=script:/local/slow-binlog.btm"` (`conf/cassandra-env.sh:307`). With the rule, writer throughput is ≤ 16 records per 50 ms = 320 records/s.

> **Amendment C1 (2026-10-27, stage-4 audit; host node, paths and cleanup).** One node on 127.0.0.1 run from `$W/cassandra-run62`
> (U1; `build-test` already built it). `conf/` is copied to `$W/node-mqw/conf` with this node's lines (cluster `mqw`, data, commitlog,
> hints, saved caches and CDC under `$W/node-mqw/`); the FQL directory is `$W/node-mqw/fql`. `MAX_HEAP_SIZE=4G HEAP_NEWSIZE=800M`,
> G1 from `conf/jvm11-server.options`. The node runs as a tracked background process (`nohup bin/cassandra -f > node.out 2>&1 < /dev/null &`;
> this host has no `setsid`), with the STDOUT appender removed from its `logback.xml` so `node.out` carries only Byteman lines.
> `slow-binlog.btm` is the filed rule verbatim, kept in the harness folder; the agent is
> `-javaagent:$W/cassandra-run62/build/lib/jars/byteman-4.0.20.jar=script:<harness>/slow-binlog.btm,script:<harness>/mqw-observe.btm`
> (C3), passed in `JVM_EXTRA_OPTS` together with `-Dcassandra.netty_use_heap_allocator=true` (C3). Disk: 118 GiB free on the
> internal SSD. B4's cleanup becomes: `nodetool drain`, stop the tracked process, check `ps -eo command` for the daemon and stress,
> `rm -rf $W/node-mqw`; the clone is left clean.

**B3b. Knobs.**
- `nodetool enablefullquerylog --path /local/fql --blocking false --max-queue-weight M`, with M ∈ {16777216 (16 MiB), 134217728 (128 MiB), 1073741824 (1 GiB)}.
- Between runs, run `nodetool disablefullquerylog` and `rm -rf /local/fql/*`.
- `--blocking false` means a full queue drops records instead of throttling clients, so the queue sits at its cap.
- Second pass: `--blocking true` with M = 128 MiB.

**B3c. Workload.**
- `tools/bin/cassandra-stress write n=400000 no-warmup -col size=FIXED(4096) n=FIXED(1) -rate threads=64 -node 127.0.0.1`. The default stress mode uses prepared statements, which are logged through `executeSuccess` → `querySuccess`.
- Each FQL record carries a ~4.1 KB options buffer, so w ≈ 4.3 KB.
- Producers do more than 5,000 ops/s against 320 records/s drained. At that rate the backlog would grow by about 20 MB/s, so a 16 MiB cap fills in about 1 s, 128 MiB in about 7 s, and 1 GiB in about 55 s. The run lasts about 80 s or more, so all three caps are reached.

> **Amendment C2 (2026-10-27, stage-4 audit; the default value and a workload that reaches every cap inside the window).**
> (a) The default `M = 268435456` (256 MiB) is added between 128 MiB and 1 GiB. Each enable also passes `--max-log-size 2147483648`
> (B4's option). (b) Stress is `tools/bin/cassandra-stress write n=500000 no-warmup cl=ONE -col size=FIXED(4096) n=FIXED(1) -rate
> threads=64 throttle=5000/s -node 127.0.0.1`. The throttle makes the producer rate the 5,000 ops/s B3c's arithmetic assumes, so the
> run lasts 100 s and B3e's plateau window (from 60 s) lies inside it; unthrottled, this host may finish 400,000 writes before 60 s.
> n is raised to 500,000 because the 1 GiB cap (≈ 250,000 records) fills in about 250,000 / (5,000 − 320) ≈ 53 s, which would leave
> only 20 s of plateau at n = 400,000. (c) The `--blocking true` pass uses `duration=100s` in place of `n=500000` (at ≤ 320 ops/s the
> n-run would take 26 min); every other stress argument is the same. The schema run (B3e step 1) is the same command with FQL disabled.

**B3d. Observables and instruments.**
- `jcmd <pid> GC.class_histogram | grep 'fql.FullQueryLogger\$Query'` gives the live count of queued records, N_q. Sample every 5 s.
- `jcmd <pid> GC.run` followed by `jstat -gc <pid>`: old-generation used (OU) after a full GC, at the plateau.
- The system.log line "Dropped N binary log samples".
- The stress op rate.
- Not observable directly: the Netty direct pool share. It is inferred as N_q × options-buffer size. Optionally check it with `-XX:NativeMemoryTracking=summary` and `jcmd VM.native_memory summary` ("Other"/"Internal" growth).

> **Amendment C3 (2026-10-27, stage-4 audit; instruments that see the quantity).** (a) `jstat` cannot attach on this host, so OU is
> replaced by `jcmd <pid> GC.class_histogram` (each call forces a full GC and lists live objects only): N_q = the instance count of
> `org.apache.cassandra.fql.FullQueryLogger$Query`, live heap H = the `Total` bytes. A sampler takes one histogram every 5 s while
> stress runs (time stamped in epoch ms against the stress start). (b) Every node start carries `-Dcassandra.netty_use_heap_allocator=true`:
> under the default pooled direct allocator (`CBUtil.java:60`, `-Dio.netty.allocator.maxOrder=11`) each of the 20 direct arenas commits
> 16 MiB chunks on first use and keeps them, which would hide the 16 and 128 MiB caps; with the flag each options buffer is an exact-size
> heap `byte[]` and the live heap sees the whole weight. This replaces B3f's "OU stays small" premise (C5); the cap logic is unchanged.
> The optional NMT step is not run (the buffers are on the heap). (c) Retained heap per run: after stress ends, `nodetool flush`
> (empties the memtables, whose 4 KB values would otherwise swamp the delta), histogram `H_full` (with `N_q_full`),
> `nodetool disablefullquerylog` (`BinLog.stop()` ends the writer loop and `finalize()` polls and releases the rest,
> `BinLog.java:174-191, 273-292`), histogram `H_empty`; ΔH = H_full − H_empty. (d) Observe-only Byteman file `mqw-observe.btm`:
> `MQWP <ms> <permits> <maxWeight> <batch>` every 20th writer batch (the queue's own counter and its `maxWeight`, a read-back of the
> knob) and `MQWW <ms> <weight>` every 5,000th `Query.weight()` call (w_obs). (e) Drop evidence: `Dropped N binary log samples` lines in
> `system.log` after the run's byte offset. (f) The op rate of the blocking pass is the steady rate from stress's interval rows:
> (total ops at the last row − total ops at the first row with time ≥ 30 s) / elapsed time between them. Scripted in
> `harness/.../cluster-run.sh`.

**B3e. Procedure.**
1. Start the node and run stress once with FQL disabled to create the schema. Take the baseline OU after `GC.run`.
2. For each M: enable FQL, run stress, sample the histogram and OU at the plateau (from 60 s on), then stop stress. Run `nodetool disablefullquerylog` and wait until N_q = 0.
3. Positive control: with M = 1 GiB but **without** the Byteman agent, restart the node and repeat.
4. Run the `--blocking true` pass with M = 128 MiB. Record N_q and the stress op rate.
5. Stop: `nodetool stopdaemon`, then `pgrep -f CassandraDaemon` returns nothing.

> **Amendment C4 (2026-10-27, stage-4 audit; exact sequence and stop conditions).** `cluster-run.sh r1`: (1) start the node with the
> Byteman agent; schema run (FQL disabled); `nodetool flush`; `nodetool disableautocompaction keyspace1` (so no compaction runs
> between `H_full` and `H_empty`; it lasts until the restart of step 4, whose control has no ΔH band); baseline histogram. (2) For M = 16 MiB, 128 MiB, 256 MiB, 1 GiB in that order:
> `rm -rf $W/node-mqw/fql`; `nodetool enablefullquerylog --path $W/node-mqw/fql --blocking false --max-queue-weight M --max-log-size 2147483648`;
> `nodetool getfullquerylog` read-back; record the byte offsets of `system.log` and `node.out`; stress (C2) in the background with the 5-s
> sampler until stress exits; then C3(c); then wait 65 s, so the next run's first drop is logged (the drop warning is a NoSpam statement
> with a 1-minute window, `BinLog.java:73-74`). (3) The blocking pass, M = 128 MiB, `--blocking true`, the same steps. (4) Positive control:
> `nodetool drain`, stop, restart **without** the Byteman agent (the heap-allocator flag kept), M = 1 GiB `--blocking false`, the same steps.
> (5) `nodetool drain`, stop, check no daemon or stress process is left, wipe `$W/node-mqw`. The blocking pass runs before the control (the
> filed order is control then blocking) so the node restarts once. Abort (and stop/wipe) if the node dies, an enable fails, or stress exits
> non-zero; a sample that fails is recorded and the run goes on.

**B3f. Predictions.**
- Plateau N_q ≈ M / w + ≤ 16: about 3,900 / 31,200 / about 250,000 for the three values of M.
- OU − baseline ≈ the heap share of M: the query string and object shells, under 10% of w. The options buffer is direct, so OU differences stay small. N_q is the decisive reading.
- Dropped-sample warnings appear in all three blocking=false runs.
- Without Byteman, N_q stays in the hundreds or fewer and no drops are logged.
- blocking=true: N_q plateaus at the same value as the 128 MiB run, and the stress op rate falls to about 320 ops/s.

> **Amendment C5 (2026-10-27, stage-4 audit; exact predictions and bands).** w_obs = the MQWW values (all equal), expected from source
> within [4,200, 4,500] B: options buffer 4,118–4,160 B (consistency, flags, count, 10-byte key and 4,096-byte value with their length
> fields, plus optional timestamp/page-size/keyspace fields) + Query, ByteBuf and query-string shells. MQWP `maxWeight` = M in every
> Byteman run. **Plateau** = samples taken while stress runs at t ≥ 60 s; band per sample: `floor(M/w_obs) − 16 ≤ N_q ≤ floor(M/w_obs) + 144`
> (at most 16 records in the writer's batch after their permits were released, `BinLog.java:248-256`, and at most one record per
> request thread being built or refused, `native_transport_max_threads` = 128, `Config.java:283`): 16 MiB ≈ 3,900, 128 MiB ≈ 31,200,
> 256 MiB ≈ 62,400, 1 GiB ≈ 250,000. Median plateau N_q ratios between consecutive M within ±5% of 8, 2 and 4. At least one drop line in
> each blocking=false Byteman run. ΔH / (N_q_full · w_obs) ∈ [0.8, 1.2] in each Byteman run (replaces "OU − baseline small", C3(b)).
> Blocking pass: plateau samples in the 128 MiB band, 0 drop lines, steady op rate ∈ [160, 352] ops/s (≤ 16 records per 50 ms = 320/s,
> +10%; the lower bound allows Chronicle write time). Control (no Byteman): every sample N_q ≤ 999 and 0 drop lines.

> **Runbook-defect fixes D2 and D3 (2026-10-27, found by the cluster shakedown before run 1; no band or row changed).**
> D2: FQL logs every CQL query, including the driver's own metadata queries when stress connects (the shakedown's first MQWW value was
> 182 B), so the MQWW values are not all equal. w_obs is the MQWW values of records that carry the 4,096-byte stress value
> (weight ≥ 4,096); the other values are reported with their count. C5's band for w_obs and C6(1) apply to w_obs so defined.
> D3: the stress JVM stays alive for a few seconds after its last operation (it prints its results), and in that time the queue drains
> at the writer's rate, so "while stress runs" in C5 is read from stress's own output: a plateau sample is one taken at t ≥ 60 s whose
> histogram ended before stress printed its `Results:` line (the sampler records this per sample).

**B3g. Readings.**

| Observation | Meaning |
|---|---|
| N_q plateaus near M/w and scales ×8 across M values | Claim holds: queue usage follows max_queue_weight |
| N_q keeps growing past M/w + 16 for some M | Claim wrong (cap bypassed) |
| N_q same for all M | Claim wrong, or writer not slowed (check the drop warnings and Byteman load log) |
| No-Byteman control shows tiny N_q | Backlog is caused by the slow writer, so the knob sweep is meaningful |
| blocking=true: op rate collapses, N_q at cap | Cap enforced by back-pressure |
| Native memory grows far beyond N_q × w | Weights undercount real retention |

> **Amendment C6 (2026-10-27, stage-4 audit; verdict words and missing rows).** Checked in this order. (1) **Invalid**: the node or a
> run aborted; stress errors; no plateau sample in some run; no MQWP lines (agent not loaded) or `maxWeight` ≠ M; w_obs outside
> [4,200, 4,500]. (2) **Refuted — does not cap** (row 2): a plateau sample above `floor(M/w_obs) + 144`, or (row 3) median N_q within ±5%
> across all M while drop lines are present. (3) **Not confirmed**: any other C5 band missed: a sample below the band, a ratio out of
> ±5%, no drop line in a run, ΔH ratio outside [0.8, 1.2] (row 6 if above 2: weights undercount retention), the blocking pass out of
> band, or the control above 999 / with drops (the backlog does not need the slow writer). (4) **Confirmed — caps**: every C5 band holds
> (rows 1, 4 and 5 together; direct disallow evidence = drop lines in the blocking=false runs and the collapsed op rate under blocking).

**B3h. Controls.**
- Run with FQL disabled to get the baseline heap.
- Run without Byteman to show the backlog needs a slow writer.
- Use the same stress parameters in every run.
- Wait for the queue to drain between runs, and clear `/local/fql` so on-disk files do not grow.

**B4. Risks and cleanup.**
- Disk: FQL files grow at writer speed (about 1.4 MB/s throttled, much faster without Byteman). Set `--max-log-size 2147483648` or `rm -rf /local/fql` between runs. Stress data is about 2 GB.
- Use local disk only, and never build in the shared clone.
- Cleanup: run `nodetool disablefullquerylog` and `nodetool stopdaemon`. Kill any remaining `CassandraDaemon` and stress JVMs (check with `pgrep -f cassandra`). Remove `/local/c509/data`, `/local/fql` and `/local/slow-binlog.btm`.

## C. Sources read

- src/java/org/apache/cassandra/utils/concurrent/WeightedQueue.java
- src/java/org/apache/cassandra/utils/binlog/BinLog.java
- src/java/org/apache/cassandra/utils/binlog/BinLogOptions.java
- src/java/org/apache/cassandra/fql/FullQueryLogger.java
- src/java/org/apache/cassandra/audit/BinAuditLogger.java
- src/java/org/apache/cassandra/service/StorageService.java (7131-7146)
- src/java/org/apache/cassandra/transport/CBUtil.java (59-60)
- src/java/org/apache/cassandra/utils/ObjectSizes.java (155-175, 219-222)
- src/java/org/apache/cassandra/config/Config.java (703-704)
- src/java/org/apache/cassandra/tools/nodetool/EnableFullQueryLog.java, EnableAuditLog.java
- conf/cassandra.yaml (1891-1927), conf/cassandra-env.sh (307)
- doc/modules/cassandra/pages/managing/operating/fqllogging.adoc, audit_logging.adoc
- test/unit/org/apache/cassandra/utils/concurrent/WeightedQueueTest.java
- test/unit/org/apache/cassandra/utils/binlog/BinLogTest.java
- .build/parent-pom-template.xml (byteman version)

## D. Stage-4 feedback

**2026-10-27, stage 4 run 1 on the advisor's Mac (Claude Opus 5.5, claude-opus-5-5[1m]); results in
[`../../stage4-runtime-verification/results/max_queue_weight-acquireWeight-weight--autonomous.md`](../../stage4-runtime-verification/results/max_queue_weight-acquireWeight-weight--autonomous.md) (uncommitted).**

- **Version run.** Audit: Ready after amendments U1–U5 and C1–C6 (frozen `65f57ecb…`). Runbook defects D1–D3 were found by shakedowns and fixed before run 1: D1 the unit heap reading, D2 w_obs, D3 the plateau window. Both tiers ran at `7198059f…`.
- **Unit: Confirmed — caps** (B2g rows 1, 3, 5).
  - w = 4,281 B. At M = 1/8/64/256 MiB, nAcc = floor(M/w) exactly (244 / 1,959 / 15,675 / 62,703). W ≤ M, M − W < w, and no offer was accepted after the first refusal.
  - Heap delta 0.996 × W, with the options buffers on the heap via `-Dcassandra.netty_use_heap_allocator=true`.
  - Overweight: one element was admitted alone, and the next offer was refused.
  - Guards: weight 0 and −1 threw IAE at `tryAcquireWeight:307` (offer) and at `acquireWeight:285` (timed offer, put), with permits intact.
  - Leak: a weight changed to 0 threw at `releaseWeight:326` and left permits at M − 5.
  - `BinLog` with a blocked writer gave the same nAcc.
- **Cluster: Confirmed — caps** (B3g rows 1, 4, 5).
  - Under the slowed writer, plateau N_q = floor(M/w) + 16 at 16/128/256/1024 MiB (3,858 / 30,757 / 61,499 / 245,948; w = 4,366). Ratios ×7.97 / ×2.00 / ×4.00.
  - "Dropped N binary log samples" appeared in every blocking=false run.
  - Retained heap ΔH = 0.980 × N_q · w in all five runs.
  - Blocking: N_q 30,821 (floor + 16 batch + 64 producers held in `put()`), 281 ops/s, no drops.
  - The no-Byteman control never queued more than 2 records.
- **Findings for stage 3.**
  - (1) The options buffer is pooled **direct** memory by default (`CBUtil.java:59-60`, `FullQueryLogger.java:485`). B1's "extra heap … plateaus at about max_queue_weight" and B2f's heap delta hold only with the heap allocator; with the default allocator most of the capped bytes are Netty direct memory, which this run did not measure.
  - (2) `Query.weight()` counts the shared prepared-statement string once per record, so the real retention is about 2% below the weight.
  - (3) The overshoot terms of A3 step 5 (b) and (c) are visible exactly: +16 for the writer's batch, and +1 per producer blocked in `put()`.
  - (4) Source note, not measured: when `stop()` ends `BinLog.put`'s loop (`BinLog.java:221-227`), `put` returns without queuing, yet `logRecord` sets `putInQueue = true` (`:304-305`). The record is never released, which leaks a pooled buffer per blocked producer at disable under `block=true`.
  - (5) FQL also logs the driver's own metadata queries (166–182-B records).
- **No section amended by the result.**
