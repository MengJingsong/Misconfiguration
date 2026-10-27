# diagnostic_event_memory_store_max_size — verification solution  <!-- file: cases/diagnostic_event_memory_store_max_size-store-keyhead--autonomous.md -->

| Field | Value |
|---|---|
| Entry pointer | `src/java/org/apache/cassandra/diag/store/DiagnosticEventMemoryStore.java:56` |
| Pinned source | `cassandra-5.0.9` |
| Session / date | Claude Code CLI (Agent-tool subagent), 2026-10-27 |
| Estimate | `positive` (with a caveat on size): the number of events held per event class is capped at 200 by a hard-coded constant, so the retained on-heap event objects plateau instead of growing without bound. The cap counts events, not bytes, and applies per event class, so it bounds heap only as tightly as the events are small. |
| Ground | — |

## A. Constraint trace

**A1. The constraint.** `maxSize` in `DiagnosticEventMemoryStore`. Kind: constant (a non-final private instance field). First declared at `DiagnosticEventMemoryStore.java:39` as `private int maxSize = 200;`. Unit: number of events (entries of the map), not bytes. Default: the literal 200, no derivation. How it can be set: not by any yaml key, `-D` property or JMX. The only writer is `setMaxSize(int)` at `:92-95`, package-private and annotated `@VisibleForTesting` (`:91`); nothing in `src/` calls it (the only users of the store are `DiagnosticEventPersistence.java:128`, `:79`, `:151`). Changing the cap needs a code change and a restart. The check is at `:56` (`if (keyHead > maxSize) events.tailMap(keyHead - maxSize).clear();`), where `keyHead` is the running counter `lastKey.incrementAndGet()` (`:52`; `lastKey` declared `:37`). The earlier trace's claims were checked and hold. Corrections and additions: (a) the store is created lazily, one instance per event class, by `getStore` at `DiagnosticEventPersistence.java:149-152` (`stores.computeIfAbsent(cls, ...)`, `stores` declared `:47`); (b) the only things that gate it are `diagnostic_events_enabled` (`Config.java:708`, default `false`; `conf/cassandra.yaml:1936`; read by `DatabaseDescriptor.diagnosticEventsEnabled()` `DatabaseDescriptor.java:4402-4405`) and a subscription made through the JMX call `enableEventPersistence` (`DiagnosticEventService.java:298-301`, `DiagnosticEventPersistence.java:99-111`); neither sets the cap. The flag has a JMX disable (`DiagnosticEventService.java:288-291`) but no JMX enable, so it is turned on in yaml and needs a restart.

**A2. What it caps.** Resource: Java heap (on-heap only; the store is a `ConcurrentSkipListMap<Long, DiagnosticEvent>`, `:43`). Quantity compared with the limit: `keyHead - maxSize`, i.e. the monotonically increasing event id minus the cap, which equals "the id of the oldest event allowed to stay". Because ids are consecutive per store and nothing else removes entries, the map size is held at about `maxSize` (the `size()` accessor is `:85-89`). The cap is on entry count; each entry holds a `DiagnosticEvent` object whose size depends on the event class (e.g. `AuditEvent` keeps an `AuditLogEntry` with the query text and `QueryOptions`, `audit/AuditEvent.java:33-37`), so retained bytes are `200 x (event size)` per class, not a byte bound.

**A3. Mechanism.** Step by step:
1. `DiagnosticEventService.publish` returns immediately unless `diagnosticEventsEnabled()` (`DiagnosticEventService.java:72-75`), then calls every subscribed consumer (`:77-103`).
2. The persistence consumer is registered by `enableEventPersistence` -> `subscribe(...)` (`DiagnosticEventPersistence.java:99-111`); its callback is `onEvent` (`:122-129`), which calls `getStore(cls)` and `store.store(event)` (`:128`).
3. `store` (`DiagnosticEventMemoryStore.java:50-57`): increments `lastKey` (`:52`), puts the event under that key (`:53`), then if `keyHead > maxSize` clears `events.tailMap(keyHead - maxSize)` (`:56`). The map uses `Comparator.reverseOrder()` (`:43`), so `tailMap(k)` (inclusive) is the keys numerically `<= k`; entries `keyHead - maxSize + 1 .. keyHead` survive, i.e. exactly `maxSize` entries in the single-threaded case.
4. Outcomes: below the cap (`keyHead <= maxSize`) nothing is removed, the map grows by one; at or above it each insert evicts exactly the one oldest entry, so size stays at `maxSize`. Evicted events become unreachable from the store and are collectable.
5. Reading (`scan`, `:59-78`; `getEvents` `DiagnosticEventPersistence.java:62-97`) does not remove entries.

Bypasses and overshoot: (i) the cap is per store and there is one store per event class (`DiagnosticEventPersistence.java:151`), so total retained events are up to `200 x (number of distinct event classes persisted)`, and the `stores` map is never trimmed (no removal in the file). (ii) Under concurrent publishers the put (`:53`) and the clear (`:56`) are separate, non-atomic steps, so the size can briefly exceed 200 by about the number of in-flight publishers; it re-converges on the next store. (iii) The cap is not a byte bound: `200 x` large events (long audit-logged statements) can be large. (iv) Events published but not persisted (no `enableEventPersistence` subscription) never reach the store, so the cap is moot for them; other subscribers' own buffering is outside this class.

**A4. Other consumers.** Other things that use heap outside this cap: memtables, caches, the events' own referents (an event can hold references to larger objects such as `KeyspaceMetadata`, `TableMetadata`, `HintsService` in `SchemaEvent`, `HintsServiceEvent`), the JMX serialization copies made by `getEvents` (`DiagnosticEventPersistence.java:81-92`, a temporary `HashMap` per returned event), other `DiagnosticEventService` subscribers (`DiagnosticEventService.java:51` `subscribersAll`, and by-class maps), and `LastEventIdBroadcaster`. The audit path additionally has its own queues when `BinAuditLogger` is the logger; that is a different object from this store.

**A5. Evidence beyond the source.** Unit test `test/unit/org/apache/cassandra/diag/store/DiagnosticEventMemoryStoreTest.java` (store/scan semantics, uses `DiagnosticEventServiceTest.TestEvent1`, `DiagnosticEventServiceTest.java:214-225`); `test/unit/org/apache/cassandra/transport/CQLUserAuditTest.java:75` shows `DiagnosticEventAuditLogger` configured as the audit logger. Public docs: Cassandra "Diagnostic events" (CASSANDRA-12944, introduced the feature; https://issues.apache.org/jira/browse/CASSANDRA-12944). No upstream doc states the 200 cap.

## B. Verification solution

**B1. Claim under test.** For any single event class persisted in `DiagnosticEventMemoryStore`, the number of events retained never exceeds `maxSize` (200) plus a small in-flight margin, regardless of how many events are published, and heap retained by the store therefore plateaus after about 200 events instead of growing with the event count. Unit-tier version: store size equals `min(N, maxSize)` and evicted events become unreachable. Cluster-tier version: after publishing far more than 200 events of one class, the live `AuditEvent` count and live heap stay flat, and the plateau scales with event size and with the number of event classes, not with the event count. It would be wrong if retained events keep growing past the cap.

### B2. Unit tier

**B2a. Environment and build.** JDK 11, Ant. Copy the tree to local disk (`rsync -a /users/jason92/cassandra-5.0.9/ $LOCAL/cassandra-5.0.9/`; never build in the shared tree). `cd $LOCAL/cassandra-5.0.9 && ant jar` (or `ant build-test`). Add a JUnit test `test/unit/org/apache/cassandra/diag/store/DiagnosticEventMemoryStoreCapTest.java` in package `org.apache.cassandra.diag.store` (needed for the package-private `size()` `:86` and `setMaxSize` `:92`). Run: `ant testsome -Dtest.name=org.apache.cassandra.diag.store.DiagnosticEventMemoryStoreCapTest`. JVM options: the test default; add `-Xmx512m -XX:+UseSerialGC` via `-Dtest.jvm.args` for deterministic GC.

**B2b. Knobs.** `setMaxSize(m)` with m in {1, 50, 200 (default), 1000}: 200 is the shipped value, the others show the check tracks the field and not a hidden constant; 1 is the edge. Event count N in {m-1, m, m+1, 10*m, 100000}. Payload per event in {0, 64 KiB} to separate count from bytes. Set by calling `setMaxSize` on a fresh store before the loop.

**B2c. Workload.** Single thread: `for i in 1..N: store.store(new PayloadEvent(payloadBytes))`, where `PayloadEvent extends DiagnosticEvent` holds a `byte[]` (implement abstract `getType` and `toMap`, as `DiagnosticEventServiceTest.java:214-225`). Arithmetic: at default cap and N = 100000, 99800 events must be evicted; with 64 KiB payload the retained bytes should be about `200 x 64 KiB = 12.5 MiB`, against `100000 x 64 KiB = 6.1 GiB` if nothing were evicted (which would exceed `-Xmx512m` and throw OOM, an unmistakable failure). A concurrency run: 8 threads x 20000 stores each, to look at transient overshoot.

**B2d. Observables and instruments.** (1) `store.size()` (`:86`) after each phase. (2) `store.getLastEventId()` (`:80`) to confirm N inserts were counted. (3) `store.scan(0L, 0)` size and lowest/highest keys (expect `N-m+1 .. N`). (4) A `WeakReference` list of every inserted event; after `System.gc()` (repeat 3 times) count references not cleared = events still strongly reachable. (5) Used heap after GC via `Runtime.totalMemory()-freeMemory()` as a coarse check for the 64 KiB runs. Cannot be observed directly: exact retained bytes per event (use the payload-dominated estimate).

**B2e. Procedure.**
1. Build as in B2a.
2. For each m: new store, `setMaxSize(m)`, insert N events for each N in the list, recording `size()`, key range, `lastKey`.
3. After each insertion, `System.gc()` x3 and count live `WeakReference`s and used heap.
4. Repeat with the 64 KiB payload for m = 200 and N = 100000 (single-thread), recording used heap at N = 200, 1000, 10000, 100000.
5. Run the 8-thread case and record `size()` immediately after join and the maximum of `size()` sampled by a monitor thread during the run.
6. Positive control: construct a plain `ConcurrentSkipListMap` with the same inserts and no eviction and show its size equals N and its used heap grows linearly (small N, e.g. 5000 at 64 KiB = 312 MiB, to stay within heap). Record all outputs.

**B2f. Predictions** (stated before any run). For default m = 200: `size()` = N for N <= 200 and = 200 for every N > 200; key range `N-199 .. N`; live weak refs = 200 (+ at most a handful of stack-held ones) for N > 200. For m = 1: size 1. For m = 50 and 1000: size = min(N, m). Used heap with 64 KiB payload: flat from N = 200 to N = 100000 (within noise, around 12.5 MiB above baseline), not growing with N. Concurrent case: final size within `[200, 200 + 8]`, with a transient maximum under about `200 + 8` (one in-flight put per thread); if the final size is far above 200 the claim is wrong. Control map: size = N, heap linear in N.

**B2g. Readings.**

| Observation | Meaning |
|---|---|
| `size()` = min(N, m) at every point, live refs ~ m, heap flat after N > m | Cap works as traced (claim confirmed) |
| `size()` keeps growing past m, or heap grows with N | Claim wrong: eviction does not bound the store |
| `size()` < m after N >= m (e.g. 0 or 199) | Off-by-one or over-eviction at `:56`; trace in A3 step 3 wrong |
| Final size beyond m + threads after the concurrent run | Overshoot larger than A3 (ii) says; report the amount |
| Size right but live refs >> m after gc | Evicted events still held elsewhere (not by the store); the cap does not release memory |
| Control map not growing | Workload too small or events not retained; reading invalid, rerun |

**B2h. Controls.** The unbounded-map control (B2e step 6) shows the workload would otherwise grow; varying m shows size follows the field; the 0-byte vs 64 KiB payload separates count from bytes; GC repeated x3 and the weak-reference count remove timing noise; JIT warmup by discarding a first pass of 20000 inserts.

### B3. Cluster tier

**B3a. Environment and build.** One node, local disk of known size (>= 10 GiB free). Copy the tree to local disk, `ant jar` there. Run from the build tree with a fresh data directory under a local path (e.g. `$LOCAL/run1/{data,commitlog,hints,saved_caches,logs}`) via `-Dcassandra.storagedir=$LOCAL/run1` and `-Dcassandra.logdir=$LOCAL/run1/logs`. JVM: `MAX_HEAP_SIZE=1G`, `HEAP_NEWSIZE=256M`, JDK 11, G1 default. Config changes in the copied `conf/cassandra.yaml`: `diagnostic_events_enabled: true` (`Config.java:708`); `audit_logging_options: {enabled: true, logger: [{class_name: DiagnosticEventAuditLogger}]}` (resolved by `FBUtilities.java:648-651`, constructor with `Map` `DiagnosticEventAuditLogger.java:27`); keep `listen_address`/`rpc_address` on localhost, `authenticator` default. A JMX client is needed (the `nodetool` has no command for this MBean): use `jmxterm` or a 30-line Java `JMXConnector` program against `localhost:7199` and MBean `org.apache.cassandra.diag:type=DiagnosticEventService` (registered at `DiagnosticEventService.java:60-63`). Heap instruments: `jcmd`, `jstat` from the same JDK.

**B3b. Knobs.** The cap itself is not settable at runtime or by config, so the cluster tier holds the cap at 200 and varies what the claim says the retained usage depends on: (1) number of audited statements N in {100, 200, 201, 1000, 20000}; (2) statement size S in {about 200 B, 256 KiB} (text literal in an INSERT); (3) number of persisted event classes C in {1, 2}: `org.apache.cassandra.audit.AuditEvent` only, then also `org.apache.cassandra.gms.GossiperEvent` (needs one more node or a gossip state change such as a `nodetool disablegossip`/`enablegossip` pair to emit events; if impractical, keep C = 1 and say so). Set by JMX `enableEventPersistence(<class>)` (`DiagnosticEventService.java:298`). Reason for values: 100/200/201 straddle the boundary; 20000 is 100x the cap; 256 KiB makes bytes distinguishable from counts.

**B3c. Workload.** Create keyspace `ks` (SimpleStrategy RF 1) and table `t(id int primary key, v text)`. Drive through the normal client path with `cqlsh -f` files of N `INSERT INTO ks.t (id, v) VALUES (<i>, '<S bytes>');` statements, or the Python driver. Each statement produces one `AuditEvent` (type per statement; `AuditEvent.create` `AuditEvent.java:41-45`, gate `:47-50`). Arithmetic: N = 20000 events at S = 256 KiB would be 5 GiB if all were retained, over the 1 GiB heap (so unbounded retention fails visibly); retained by the cap is `200 x 256 KiB = 50 MiB` of strings (plus the bound-values/options copy). N = 20000 at 256 KiB sent over cqlsh is slow, so use N = 2000 for the large-S phase (still 10x the cap, 500 MiB if unbounded). Duration: minutes per phase; sample for 30 s after the last statement to confirm the plateau.

**B3d. Observables and instruments.** (1) Store size: JMX `readEvents("org.apache.cassandra.audit.AuditEvent", 0L, 100000)` (`DiagnosticEventService.java:293-296` -> `DiagnosticEventPersistence.getEvents` `:62-97`); the returned map's size is the retained count and its largest key is the latest id; note that it builds temporary maps of the whole store (a transient allocation), so call it once per phase. (2) Live event instances: `jcmd <pid> GC.class_histogram` (live: it forces a full GC) and read the row for `org.apache.cassandra.audit.AuditEvent` and `AuditLogEntry`. (3) Heap after GC: `jcmd <pid> GC.run` then `jstat -gc <pid>` (old + eden used) or JMX `java.lang:type=Memory` HeapMemoryUsage after the GC. (4) Optional heap dump `jcmd <pid> GC.heap_dump` and the dominator tree of `DiagnosticEventMemoryStore.events` (local disk, size about the heap). Cannot be observed directly: the exact retained bytes of the store alone; the dominator tree gives it, the histogram gives only per-class totals.

**B3e. Procedure.**
1. Copy tree to local disk, `ant jar`, apply the yaml changes of B3a, start one node (`bin/cassandra -f` in background, output to a local log); wait for "Starting listening for CQL clients".
2. `jcmd` baseline: GC.run, record used heap and the histogram counts for `AuditEvent`, `AuditLogEntry`. Confirm `isDiagnosticsEnabled` is true over JMX.
3. Call `enableEventPersistence("org.apache.cassandra.audit.AuditEvent")`. Create schema (these create events too; note the baseline `readEvents` count and last key).
4. Phase P1: N = 100 small statements. Record readEvents count, histogram, heap after GC.
5. Phase P2: cumulative N = 200, then 201, then 1000, then 20000 small statements; at each point record the same three readings.
6. Phase P3 (size control): fresh run (restart node with a clean storage dir), same setup, statements of S = 256 KiB, cumulative N = 100, 200, 400, 2000; record the three readings.
7. Phase P4 (class count): in the P2 setup also enable a second class and repeat 1000 events of each; record per-class counts from `readEvents` for each class.
8. Positive control (cap that binds elsewhere): in the same JVM take the same N = 20000 small-statement workload with the persistence subscription disabled (`disableEventPersistence`) and show the `AuditEvent` count does not grow either, and compare with a control where a known unbounded retainer is used (for instance, a client-side list in the JMX program that keeps every returned event map, which must grow linearly with N). This shows the workload and the instruments can see growth when there is no cap.
9. Cleanup per B4.

**B3f. Predictions.** Small statements: `readEvents` count = min(events_since_enable, 200) per class; after N = 20000 it is 200 (plus at most a few from concurrent sessions; one client thread gives exactly 200). Largest key increases by N + baseline events while the count stays 200. Histogram live `AuditEvent` count about 200 (+ transient few) at every phase from N >= 200 on; `AuditLogEntry` similarly. Heap after GC plateaus: the difference between N = 1000 and N = 20000 is within noise. Large statements (256 KiB): live heap above the baseline grows up to N = 200 (about `200 x 256 KiB`, i.e. about 50 MiB or up to about double if bound values are also retained as buffers) and is then flat to N = 2000, not 10x. Two classes: total retained events = 200 per class (400 with two). Disabled subscription: the store is not appended, count flat. Control list in the JMX client grows linearly. What would show the claim wrong: the `AuditEvent` count or post-GC heap still rising between N = 1000 and N = 20000.

**B3g. Readings.**

| Observation | Meaning |
|---|---|
| `readEvents` count capped at 200, histogram live `AuditEvent` ~200, heap after GC flat from N = 1000 to 20000, and the 256 KiB phase plateaus around `200 x S` | Cap bounds heap as traced (claim confirmed, estimate `positive`) |
| Count capped but heap after GC keeps rising | Something else holds the events (A4), so the cap does not bound heap; claim wrong for the actual resource |
| Count and heap grow with N | Eviction not working on a live node; claim wrong |
| Large-S plateau scales with S while the count stays 200 | Confirms the cap is a count, not a byte bound; plateau size is `200 x S`, not a defect of the trace |
| Count 400 with two classes | Per-class store confirmed (A3 (i)) |
| Count of the store stays 0 or no events | `diagnostic_events_enabled` or the subscription or the audit logger was not active; reading invalid, recheck B3a/B3e step 3 |
| The positive control also stays flat | The instruments cannot show growth; reading invalid, fix the control before drawing conclusions |

**B3h. Controls.** Baseline reading taken before the subscription; same workload with persistence disabled (no store growth) and with the client-side unbounded list (linear growth); forced GC (`GC.run`) before every heap reading and the live class histogram so garbage does not count; one client thread to remove concurrency overshoot; the audit events of the node's own system keyspace traffic are noted by the baseline (set `excluded_keyspaces` for `system,system_schema,system_virtual_schema,system_auth,system_distributed,system_traces` if they add noise).

**B4. Risks and cleanup.** Disk: all data, commitlog, hints, saved caches, logs and heap dumps go under a local directory (`$LOCAL/run*`) on a disk with >= 10 GiB free; heap dumps are about the heap size (1 GiB), delete them after reading. Unit tier writes only to the local copy's `build/` directory (a few GB; delete the copy afterwards). Never build or write in `/users/jason92/cassandra-5.0.9`. Large-S statements need `native_transport_max_frame_size` at its default (16 MiB, fine for 256 KiB). Processes: the Cassandra JVM, the JMX client, `cqlsh` and `ant` forks; after each run `pkill -f CassandraDaemon` (only the ones started from `$LOCAL`), then check `pgrep -fa 'CassandraDaemon|ant|jmxterm'` is empty and `ss -ltnp | grep -E '7199|9042|7000'` shows nothing left. Remove `$LOCAL/run*` and the source copy when done.

## C. Sources read

- `/users/jason92/cassandra-5.0.9/src/java/org/apache/cassandra/diag/store/DiagnosticEventMemoryStore.java`
- `/users/jason92/cassandra-5.0.9/src/java/org/apache/cassandra/diag/DiagnosticEventPersistence.java`
- `/users/jason92/cassandra-5.0.9/src/java/org/apache/cassandra/diag/DiagnosticEventService.java`
- `/users/jason92/cassandra-5.0.9/src/java/org/apache/cassandra/diag/DiagnosticEvent.java`
- `/users/jason92/cassandra-5.0.9/src/java/org/apache/cassandra/audit/AuditEvent.java`
- `/users/jason92/cassandra-5.0.9/src/java/org/apache/cassandra/audit/DiagnosticEventAuditLogger.java`
- `/users/jason92/cassandra-5.0.9/src/java/org/apache/cassandra/audit/AuditLogManager.java` (lines 85-125)
- `/users/jason92/cassandra-5.0.9/src/java/org/apache/cassandra/utils/FBUtilities.java` (lines 648-660)
- `/users/jason92/cassandra-5.0.9/src/java/org/apache/cassandra/config/Config.java` (line 708)
- `/users/jason92/cassandra-5.0.9/src/java/org/apache/cassandra/config/DatabaseDescriptor.java` (lines 4402-4410)
- `/users/jason92/cassandra-5.0.9/conf/cassandra.yaml` (lines 1893-1936)
- `/users/jason92/cassandra-5.0.9/test/unit/org/apache/cassandra/diag/store/DiagnosticEventMemoryStoreTest.java`
- `/users/jason92/cassandra-5.0.9/test/unit/org/apache/cassandra/diag/DiagnosticEventServiceTest.java` (TestEvent1)
- https://issues.apache.org/jira/browse/CASSANDRA-12944

## D. Stage-4 feedback

none yet
