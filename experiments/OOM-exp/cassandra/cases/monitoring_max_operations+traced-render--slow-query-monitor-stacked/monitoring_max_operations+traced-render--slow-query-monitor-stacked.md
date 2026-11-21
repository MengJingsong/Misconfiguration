# R12 (retry of B11) — `monitoring_max_operations` + ExecuteMessage literal `1000`: the slow-query monitor keeps finished reads with their 16 MB filter values and renders them uncut, alone and stacked on the traced render  <!-- file: cassandra/cases/monitoring_max_operations+traced-render--slow-query-monitor-stacked/monitoring_max_operations+traced-render--slow-query-monitor-stacked.md -->

| Field | Value |
|---|---|
| Case ID | `R12` (a new attempt at `B11`; README "ID prefixes") |
| From | retry of `B11` (retry-list row B11, from `OC-38`); also covers `OC-445` (the monitor, per triage 2026-11-20) |
| Phase-1 case file | render: [`ExecuteMessage_literal_1000-traceQuery-1000--autonomous`](../../../../capacity-enforcement-exp/cassandra/stage3-ai-deep-read/cases/ExecuteMessage_literal_1000-traceQuery-1000--autonomous.md); monitor: [`monitoring_max_operations-operationsqueue_offer-maxoperations--autonomous`](../../../../capacity-enforcement-exp/cassandra/stage3-ai-deep-read/cases/monitoring_max_operations-operationsqueue_offer-maxoperations--autonomous.md) |
| System / pinned source | Cassandra 5.0.9 (`systems/cassandra/source/`, `build.xml` `base.version` 5.0.9), OpenJDK 11.0.33 (aarch64, Ubuntu 22.04) |
| Stage 1 (design) | OOM-agent stage-1 session (phase-2 wave 5), 2026-11-20 10:30–11:45 America/New_York |
| Stage 2 (verify) | fresh OOM-agent session, 2026-11-20 10:44–13:05 America/New_York, node `ms0640` (aarch64) |
| Verdict | **true positive** — condition B `verified-OOM · deployment` (unprotected accumulation, largest failing heap 8 GiB); condition A `verified-OOM · deployment` (mixed) under the frozen fallback F, 2 GiB |

## Summary

- **Conclusion: true positive (condition B).** With 13 clients each sending reads with a different 16 MB filter value
  (`SELECT … WHERE k = 2 AND v = ? ALLOW FILTERING`, shipped config, no tracing), Cassandra 5.0.9 ran out of heap 5/5 at
  2 GiB (3/5 attributed to the slow-query monitor by the frozen test), 3/3 at 8 GiB, once at 4 GiB, and filled 12 GiB to
  96 % in 180 s; the same load with identical values survived 3/3 at 2 and 8 GiB, and with the monitor's queues disabled
  (`-Dcassandra.monitoring_max_operations=0`) survived 3/3 at both while completing twice as many reads. Status
  `verified-OOM · deployment` (unprotected accumulation), largest failing budget 8 GiB, aarch64.
- **Condition A (traced render + monitor, mixed): shown under the frozen fallback F.** At the designed partition (k = 2) the
  traced arms OOM 3/3 but so does the render-bounded build, and the dumps are led by a holder the design did not map: reads
  aborted at the 5 s deadline render the whole command into a `QueryCancelledException` message that the debug log queues
  (≈ 30–53 % of those dumps); the monitor-on control was invalid (row A5), so condition A ran B11's empty-partition fallback:
  traced 3/3 heap OOM with monitor values 40–51 % and render arrays 39–46 % of every dump, while untraced, render-bounded and
  monitor-off arms each survived 3/3 (§3.5.1).
- **Hypothesis under test (two conditions).** B11's traced-EXECUTE OOM had two holders outside every byte counter: the trace
  render (`ExecuteMessage.traceQuery`, ≈ 4–6 × each 16 MB value) and the slow-query monitor (`MonitoringTask`), which keeps up to
  50 finished slow reads per queue with their bound values and, at each drain, renders every one of them to an uncut hex CQL
  string. **Condition A (mixed):** with reads made slow by the data (a filtering scan over a wide partition) rather than by the
  render, the monitor fills in every arm, so a 2×2 design (tracing on/off × monitor on/off) can show whether the OOM needs both
  holders. **Condition B (monitor alone, unprotected accumulation):** with a different 16 MB value per request (no tracing), each
  drain keeps up to 50 distinct ≈ 32 MB names next to up to 100 kept values and then concatenates the names into one ≈ 1.6 GB log
  message (debug logging is on by default). The count cap of 50 does not bound these bytes.
- **Root cause (shown for condition B):** `MonitoringTask` caps its queues at 50 operations each but holds every finished
  slow or aborted `ReadCommand` with its bound value after the in-flight limit has released it, and each drain renders every
  polled command to an uncut hex string and keeps every distinct one; because polling frees queue slots, a drain under steady
  slow load never ends and its map grows past the count cap (`TB4-1`: 119 operations, 53 × 32 MB names, 3.46 GB = 89 % of
  the heap). Nothing counts these bytes.
- **Root cause as claimed at design time:** the monitor's limit counts operations, not bytes, and holds each `ReadCommand` (with its
  filter value) after the request's in-flight bytes are released; its log-time render has no cut. The traced render adds an uncharged
  4–6 × per rendering request on top.

## 1. Candidate

**Retry row (quoted from [`phase2-retry-list.md`](../../phase2-retry-list.md), status as handed to this session):**

> | [B11](cases/ExecuteMessage_literal_1000--traced-render-outside-inflight/ExecuteMessage_literal_1000--traced-render-outside-inflight.md) (from OC-38) | 2026-11-18 | At defaults and a 2 GiB heap (ms0611, aarch64), 13 connections sending traced 16 MB EXECUTEs ran the heap out 3/3; untraced 0/3 and render-first-1000-bytes 0/3. But dumps put the render arrays at only 32–38 % of heap; the largest holder (42–49 %) was finished queries kept by the slow-query monitor, so V5 attribution failed | Re-map as mixed/stacked: add the slow-query monitor (MonitoringTask queues, count cap `monitoring_max_operations` = 50 per queue, no byte counter) as its own domain; test it alone and stacked with the render | picked again: R12 (2026-11-20) |

**Earlier case and its verdict.** [`B11`](../ExecuteMessage_literal_1000--traced-render-outside-inflight/ExecuteMessage_literal_1000--traced-render-outside-inflight.md),
`retry` (protocol status `candidate` · mixed), stage 2 on `ms0611` (aarch64) 2026-11-17/18. Single node, shipped `conf/`, 2 GiB heap,
13 connections (one per source IP), closed loop of prepared `SELECT c FROM b11.t WHERE k = 0 AND v = ? ALLOW FILTERING` with one
16,000,000-byte blob on an **empty** partition:

| B11 arm | Result |
|---|---|
| T2 traced, base build | heap OOM 3/3, 15–22 s after N = 13; median latency 1.2 s; 7–25 Full GCs |
| C2 untraced | 0/3 (150 s), median latency 213–244 ms, live humongous median 2 regions |
| I2 traced, render bounded to 1000 bytes (`iv.patch`) | 0/3 (150 s), median latency 260–270 ms |
| T4 (N = 26), T8 (N = 256) | 0/1 each |
| Dumps (R2, T2-1..3) | values `byte[16,000,000]`: 60–65, of which **51–52 (≈ 780–793 MiB, 42–49 %) held by `MonitoringTask$OperationsQueue` → `SlowOperation` → `SinglePartitionReadCommand` → `RowFilter$SimpleExpression.value`**; render arrays 519–702 MiB (32–38 %); OOME thread 3× NTR in `Hex.bytesToHex` under `traceQuery`, 1× `ScheduledTasks` in `MonitoringTask.logSlowOperations` → `popOperations` → `ReadCommand.toCQLString` → `Hex.bytesToHex` |

B11's own diagnosis (§4 there): the render made every traced read slower than `slow_query_log_timeout` (500 ms), so the monitor
filled; the render-bounded intervention removed both holders at once (it also removed the latency), so it could not attribute the
OOM. Its "better design" items: (1) map the monitor as its own domain; (2) separate the two holders with a second intervention
(e.g. `-Dcassandra.monitoring_max_operations=0`); (3) search the budget by N at 4 GiB; (4) consider the monitor as a candidate of its own.

**Phase-1 cases.**
- Render: [`ExecuteMessage_literal_1000-traceQuery-1000--autonomous`](../../../../capacity-enforcement-exp/cassandra/stage3-ai-deep-read/cases/ExecuteMessage_literal_1000-traceQuery-1000--autonomous.md)
  (OC-38); stage 4 (2026-10-27, true positive for the persisted cap; JFR saw three ≥ 1 MiB render allocations per traced request) —
  details in B11 §1.
- Monitor: [`monitoring_max_operations-operationsqueue_offer-maxoperations--autonomous`](../../../../capacity-enforcement-exp/cassandra/stage3-ai-deep-read/cases/monitoring_max_operations-operationsqueue_offer-maxoperations--autonomous.md)
  (phase-1 candidate **OC-445**, open; triage 2026-11-20 assigns it to R12, not a new case). Stage 4
  ([results](../../../../capacity-enforcement-exp/cassandra/stage4-runtime-verification/results/monitoring_max_operations-operationsqueue_offer-maxoperations--autonomous.md),
  2026-10-28): outcome class true positive, effect `caps` — the count cap holds (slow and failed queues flat at 50 per queue at the
  default, 5000 at N = 5000, unbounded at −1), with small commands (≈ 1.2 KiB each); bytes per kept command were inferred, not
  measured, and no large-value command was tried. OC-445's row: "Each Operation pins its Monitorable (the whole ReadCommand …) for up
  to the 5 s report interval … the cap counts items (2 x 50 at defaults), not bytes. A command's size is bounded only by the 16 MiB
  native frame".
- Other filed cases where the monitor's render was the OOME thread without being claimed: B12 (`paxos_cache_size--weigher-omits-partition-key`,
  T-1/T-3: `MonitoringTask.logSlowOperations` → `DecoratedKey.toCQLString` → `Hex.bytesToHex`) and U5 (ledgered, not claimed).

**JIRA prior art (read only; nothing posted).** Survey file
`capacity-enforcement-exp/cassandra/stage5-oom-clue-find/jira-oom-survey.csv` (604 rows): no row on `MonitoringTask`, slow-query
logging, `toCQLString` or trace rendering. Nearest by shape (render an unbounded value to a string, fixed): CASSANDRA-2849 (0.8.5) and
CASSANDRA-14925 (3.0.24/3.11.10/4.0). JIRA REST search 2026-11-20 (`project = CASSANDRA AND …`): `text ~ "MonitoringTask"` → 5
(CASSANDRA-7392 Fixed 3.2 "Abort in-progress queries that time out"; CASSANDRA-12403 Fixed 3.10 "Slow query detecting"; CASSANDRA-13001
Fixed 6.0 slow queries to a virtual table; CASSANDRA-13650, -18219 unrelated); `text ~ "monitoring_max_operations"` → 14, none about
memory of kept commands; `"slow query" AND "memory"` (40), `"slow queries" AND "OutOfMemoryError"` (3), `"toCQLString" AND "memory"`
(16), `"slow query" AND "large"` (69) → no report of the monitor holding or rendering large values. **Design-review prior art:** in
CASSANDRA-7392 the reviewer wrote "we are going to be retaining the queries past the timeout for the logger … If someone has a memory
utilization issue they can't fix it by setting the timeout lower since the logger will still retain it and it runs on it's own
period", and "To really do this right you don't want to truncate the query you want to truncate the larger values in the query"; the
shipped code bounds the count (top 50) and does not truncate values. CASSANDRA-13001 (6.0) estimated ≈ 376 B per kept slow query
record — the small-command assumption. Render prior art as in B11 (CASSANDRA-11719: the 1000-char cut applied after rendering).
**Verdict: `new`** (the retention was discussed in review as a memory concern and bounded by count only; no report of OOM or of
large-value retention; the 6.0 virtual-table logger is a different holder).

## 2. Design solution (stage 1; frozen)

### 2.1 Mechanism

Direction: **mixed** (condition A: render bypass + monitor accumulation, both needed) and **unprotected accumulation** under a
count-only cap (condition B: monitor alone). Technique note: [`combo-playbook.md`](../../../combo-playbook.md) (stack: each layer
measured alone, then together, one intervention per layer) with the bypass shape of [`bypass-playbook.md`](../../../bypass-playbook.md)
for the render layer.

1. **When a read is "slow".** The local read runs in `StorageProxy.LocalReadRunnable.runMayThrow`, which sets the monitoring clock to
   the request's start on the NTR thread (`command.setMonitoringTime(requestTime.startedAtNanos(), …, getSlowQueryTimeout)`,
   `StorageProxy.java:2205`; `RequestTime(createdAt, startTime)`, `Dispatcher.java:307`). `ReadCommand.executeLocally` applies the
   cancellation checker **before** the row filter (`ReadCommand.java:459` vs `:473`), so every scanned row (not only matching rows)
   calls `maybeCancel` → `isAborted` → `check()` (`ReadCommand.java:784-792`, `MonitorableImpl.java:124-136`), which marks the
   command slow once ≥ `slow_query_log_timeout` (500 ms) has passed since the request started, and aborts it at the read deadline
   (5 s). At the end, `complete()` offers a slow command to the slow queue (`MonitorableImpl.java:110-122`, `MonitoringTask.java:112-115`);
   `abort()` offers it to the failed queue (`MonitorableImpl.java:96-108`). In B11 the render (which runs on the NTR thread after the
   start, `ExecuteMessage.java:160-161`) supplied the 500 ms; here a filtering scan over a wide partition supplies it in every arm.
2. **What is kept.** `OperationsQueue.offer` (`MonitoringTask.java:219-226`) puts a `SlowOperation` → the `Monitorable` (the whole
   `SinglePartitionReadCommand`) → `RowFilter` → `SimpleExpression.value` (the `HeapByteBuffer` of the decoded bound value, the same
   `byte[S]` that `CBUtil.readBoundValue` copied from the frame) into a `LinkedBlockingQueue` of capacity
   `cassandra.monitoring_max_operations` (default 50, `CassandraRelevantProperties.java:361`; 0 disables the queues, < 0 unbounded);
   when full the operation is dropped and counted. The native-transport in-flight count releases the request's S bytes at response
   flush (B11 §2.1), while the value stays reachable from the queue until the next drain.
3. **The drain.** `scheduleWithFixedDelay(logOperations, 5000, 5000 ms)` (`MonitoringTask.java:96-99`, interval
   `cassandra.monitoring_report_interval_ms` 5000, `:363`) runs on `ScheduledTasks`. `popOperations` (`:235-249`) polls every queued
   operation and computes `operation.name()` for each, which caches `ReadCommand.name()` = `toCQLString()` (`:340-345`;
   `ReadCommand.java:895-898`; `AbstractReadQuery.java:101-109`) → `RowFilter$SimpleExpression.toString` →
   `String.format("%s %s %s", …, type.toCQLString(value))` (`RowFilter.java:876`) → `BytesType` → `"0x" + Hex.bytesToHex` (the full
   value, no cut): per render a `char[2S]` (4S bytes), the hex `String` (2S), the concatenation (2S), the `String.format` copy (2S) and
   the query `StringBuilder` (grows to ≈ 4S; B11 dump `T2-1`: `byte[64,000,086]`), leaving a name `String` of ≈ 2S + 60 bytes.
   Operations with the same name are merged (`existing.add`), so with **identical** values the map keeps one operation and one
   name; with **distinct** values it keeps every polled operation, its command (value S) and its name (2S). Polling frees queue
   slots, so new slow reads refill the queue while the drain is still rendering.
4. **The log message** (debug is on by default: `conf/logback.xml:132` `org.apache.cassandra` level DEBUG, `ASYNCDEBUGLOG` at
   `:67-69`, `:123`, queue 1024, `discardingThreshold` 0). `logSlowOperations` (`:166-183`) calls `getLogMessage()` (`:277-300`):
   one `StringBuilder` gets `String.format("<%s>, …", name(), …)` (`:398-414`) for every distinct name, then `toString()`; logback
   formats that into the event's message (another copy), the async appender keeps the event until its worker has laid it out and
   written it to `debug.log`. With 50 distinct names that is a ≈ 1.6 GB `StringBuilder` (doubling to ≈ 2.1 GB at the last growth),
   its ≈ 1.6 GB `String`, and ≈ 1.6–3.2 GB more in logback, on top of the map.
5. **The traced render** (condition A's second layer; B11 §2.1 unchanged): with the frame's TRACING flag, `ExecuteMessage.traceQuery`
   renders each bound value before the 1000-char cut (`ExecuteMessage.java:213-239`, `:230`): 6S live at its peak per rendering
   request, outside the in-flight count, on up to 128 NTR threads.
6. **Why it is mixed / unprotected.** The render is a bypass (uncharged request memory, K ≤ C). The monitor has a count control
   whose contract (50 per queue) holds (U_count ≤ C) but which claims no byte bound: per the protocol, it is an **unprotected
   accumulation** whose only bound is implicit (count × frame size, plus the log-time copies). Condition A claims both layers are
   needed (mixed); condition B claims the monitor alone reaches OOM when the kept values differ.

### 2.2 Protection map

S = 16,000,000 B (one blob per request), G1 region 16 MiB (`jvm11-server.options`), so `byte[S]` = 1 region, `byte[2S..2S+200]` = 2
regions, `char[2S]` (4S + 16 B) = 4 regions, a 4S `StringBuilder` = 4 regions, a ≈ 1.6 GB array ≈ 96 regions.

| # | Domain | Holder (allocation → release) | Counter (K) | Limit (C), shipped default | At the limit | Scope / multiplicity |
|---|---|---|---|---|---|---|
| 1 | Request in flight | Netty v4 frame (direct) + decoded value `byte[S]` (heap, `CBUtil.java:669`) → released at response flush (`PreV5Handlers.java:106`) | channel / per-IP / global bytes (`RequestsSize`) | global heap/10, per IP heap/40 (`DatabaseDescriptor.java:651`, `:656`); contract: one request per connection admitted even above the limit (`PreV5Handlers.java:85`, `:184`) | connection paused; admitted request processed | N connections, one request each |
| 2 | **Trace render** (layer R) | `char[2S]`, `byte[2S]`, `byte[2S+2]` locals of `traceQuery` on an NTR thread → unreachable after the cut | none | none (literal 1000 cuts the stored string only, after allocation) | — | rendering requests R ≤ N, ≤ 128 NTR threads |
| 3 | **Slow-op queue** (layer M) | `SlowOperation` → `ReadCommand` → bound value `byte[S]` (an alias of row 1's heap copy, kept after release) → released when polled at a drain and, for distinct names, after the drain's log call | queue size, `numDroppedOperations` | `cassandra.monitoring_max_operations` **50** (count; no bytes); excess dropped | offer refused, counted | one queue per node; refilled while a drain runs |
| 4 | Failed-op queue (layer M) | `FailedOperation` → `ReadCommand` → value (reads aborted at the 5 s deadline) | same | **50** (count) | same | only if reads exceed 5 s |
| 5 | **Drain map and names** (layer M) | `popOperations` `HashMap<String, Operation>`: one entry per distinct name, each keeping its command (S) and cached name (≈ 2S); per render transient ≈ 10 regions (`char[2S]`, hex, concat, format, 4S builder) on `ScheduledTasks` → released when `logSlowOperations` returns | none | distinct names ≤ queued operations (≤ 50 per queue per drain); bytes per name ≈ 2S (≤ 2 × 16 MiB frame) | — | one drain at a time (fixed delay) |
| 6 | **Drain log message** (layer M) | `getLogMessage` `StringBuilder` (Σ names, doubling) + its `String` + logback event message + async-appender queue (1024 events) + layout copy → released after `debug.log` write | none | none (debug on by default) | async queue full → caller blocks | one message per drain |
| 7 | Read scan | per-row iteration of the selected wide partition (small transients) | read deadline | `read_request_timeout` 5 s (→ failed queue) | `QueryCancelledException`, ReadTimeout to client | ≤ `concurrent_reads` 32 (local reads run via the read stage) |
| 8 | Trace rows | `system_traces.sessions/events` mutations (≈ 1.2 KB per traced request) → memtable | memtable pool | `memtable_heap_space` heap/4 | flush | negligible |
| 9 | Caches | key cache (3 partitions), chunk cache (off-heap) | weighers | key cache min(5 % heap, 100 MiB); `file_cache_size` min(¼ heap, 512 MiB) direct | evict | data ≈ 40 MB |
| 10 | Heap budget | JVM heap | — | `-Xmx` 2 GiB (4 / 8 / 12 GiB in budget search) | `OutOfMemoryError: Java heap space` → `-XX:OnOutOfMemoryError="kill -9 %p"` | — |
| 11 | Direct budget | Netty frames (≈ 2–2.5 × K, lead B9) | Netty / JDK | `MaxDirectMemorySize` auto 15,872 MiB on this node | competing endpoint (§2.7 row X1) | — |

Contract capacities claimed: rows 1 (heap/10 + one request per connection), 3 and 4 (50 operations each). Rows 2, 5, 6 have no
capacity. The protocol's scope rule: the monitor's kept values (row 3) are compared against the monitor's own contract (a count),
not against row 1 (whose contract ends at flush).

### 2.3 Configuration and budget audit

- **Build.** Base: `/mydata/s4/cassandra-base` on `ms0640` (checked 2026-11-20 10:33 ET: `git describe --tags` = `cassandra-5.0.9`,
  `git status` clean, `build/apache-cassandra-5.0.9-SNAPSHOT.jar` 2026-11-16, no `data/` or `logs/`). Stage 2 does **not** run in it:
  `cp -a /mydata/s4/cassandra-base /mydata/s4/r12-w5/cassandra-base` (≈ 0.47 GB) and runs there. Render-bounded build:
  `cp -a` of that copy to `/mydata/s4/r12-w5/cassandra-iv`, `git apply` B11's [`iv.patch`](../ExecuteMessage_literal_1000--traced-render-outside-inflight/harness/iv.patch)
  (3 lines in `ExecuteMessage.traceQuery`, copied to this case's `harness/iv.patch`), delete
  `build/classes/main/org/apache/cassandra/transport/messages/ExecuteMessage*.class`, `ant jar` (≈ 35 s on an m400), check
  `javap -p -c -classpath build/apache-cassandra-5.0.9-SNAPSHOT.jar org.apache.cassandra.transport.messages.ExecuteMessage | grep -c ByteBuffer.duplicate`
  = 1 in iv and 0 in base. Record repo commit and both trees' `git diff`.
- **Configuration.** Shipped `conf/` unchanged in every arm (no `cassandra.yaml`, `logback.xml` or `jvm*.options` edit). Every
  constraint of §2.2 at its shipped default (V6): `cassandra.monitoring_max_operations` 50, `cassandra.monitoring_report_interval_ms`
  5000, `slow_query_log_timeout` 500 ms, `read_request_timeout` 5000 ms, `cql_start_time` REQUEST, `native_transport_max_request_data_in_flight`
  heap/10, `…_per_ip` heap/40, `native_transport_max_threads` 128, `native_transport_max_frame_size` 16 MiB, `max_value_size` 256 MiB,
  `native_transport_max_concurrent_connections` −1 / `_per_ip` −1, `native_transport_timeout` 12 s, `concurrent_reads` 32,
  `memtable_heap_space` heap/4, key cache auto, `file_cache_size` auto, `batch_size_warn/fail_threshold` 5 / 50 KiB (seed load only),
  guardrail `allow_filtering_enabled` true, debug logging on (`logback.xml`). **The only constraint changed, and only in intervention
  arms:** `-Dcassandra.monitoring_max_operations=0` (via `JVM_EXTRA_OPTS`, `cassandra-env.sh:307`) in `IM`/`IB` arms; the iv build
  only in `IR` arms.
- **Resolved at each heap** (`Runtime.maxMemory()` = `-Xmx`): 2 GiB → in-flight global 214,748,364 B / per IP 53,687,091 B, key cache
  100 MiB cap, memtable 512 MiB; 4 GiB → 429,496,729 / 107,374,182; 8 GiB → 858,993,459 / 214,748,364; 12 GiB → 1,288,490,188 /
  322,122,547. Monitor: 50 + 50 operations at every heap (not heap-derived).
- **Environment settings (not capacity):** `MAX_HEAP_SIZE` (`-Xms = -Xmx`), `CASSANDRA_HEAPDUMP_DIR=<run dir>` (shipped
  `-XX:+HeapDumpOnOutOfMemoryError`), `ulimit -n 100000` in the launching shell, `systemd-run --user --scope -p MemorySwapMax=0
  --unit=r12-<run>` (no `MemoryMax`: no container budget), linger on for the session. **Budget-search readings at ≥ 8 GiB only:**
  `JVM_EXTRA_OPTS=-XX:-HeapDumpOnOutOfMemoryError` (an 8–12 GB dump does not fit `/mydata`; recorded as an environment deviation
  of those readings; V5 there rests on the GC log, `Thread.print` samples and the OOM line).
- **Node claimed (V7):** `ms0640` (`node1.jason92-326377`, Utah m400, **aarch64**, 8 cores, 64,249 MB RAM, 8 GiB swap present and
  unused, Ubuntu 22.04, kernel 5.15, cgroup v2, OpenJDK 11.0.33, Ant 1.10.12, Python 3.10.12; `/mydata` 39 G, **18 G free**; other
  folders `/mydata/s2r2` (19 G) and `/mydata/u1r2` belong to other cases: do not touch; no Java process; load 0.00; `Linger=no`;
  open-files hard limit 1,048,576; checked read-only 2026-11-20 10:33 ET). `cassandra-env.sh` would resolve heap 31,744 MiB and
  `MaxDirectMemorySize` 15,872 MiB here. **Budgets:** heap 2 GiB (ideal; the V1–V7 condition), then 4, 8, 12 GiB for the largest
  failing budget; all ≥ 512 MiB ⇒ V7 met by the standing rule; direct auto 15,872 MiB (record from `VM.flags`); no container limit.
  aarch64: do not pool with x86 results. B11 ran on `ms0611` (same hardware type); its numbers are priors, not controls.

### 2.4 Ceiling arithmetic (regions of 16 MiB; 2 GiB = 128 regions)

Per-domain peaks at N connections (identical values unless stated). Baseline (startup, schema, caches, trace tables) ≈ 15–25
regions (B11).

| Domain | Identical values (A) | Distinct values (B) |
|---|---|---|
| Row 1 in flight (heap copies) | N (one value per connection while its request runs) | N |
| Row 2 render (traced arms only) | 5–7 per rendering request; R ≈ 0.4–0.8 N with the scan (B11: R max 9–13 at N = 13 on an empty partition) | — (B is untraced) |
| Row 3 queue | 50 values = 50 | 50 |
| Row 5 drain | 1 kept op + 1 name (3) + transient ≈ 10 → ≈ 13 | up to 50 kept values (50) + 50 names (100) + transient 10 → ≤ 160, while the queue refills (row 3: +50) |
| Row 6 log message | one ≈ 32 MB name: ≈ 2–6 transient | `StringBuilder` 65 → 128 (last doubling) + `String` 96 + logback 96–192 |
| Contract capacity covering it | row 3: 50 operations (≈ 50 regions at S = 16 MB; ≤ 50 × 16 MiB frame) | same count; bytes ≈ 3× that per drain before the message |

**Predicted totals at 2 GiB, N = 13:**
- `TA` (traced, monitor on): 13 + 30–60 (R ≈ 6–10) + 50 + 13 + 20 = **126–156** → OOM.
- `CA` / `IR` (monitor alone; identical values): 13 + 50 + 13 + 20 = **≈ 96** (75 %) → survive (margin ≈ 25 %, below the 30 % starting
  target: the ramp and `CA` ×3 test it).
- `IM` (render alone): 13 + 30–60 + 20 = **63–93** → survive (B11's render-alone share at N = 13 was 33–44 regions).
- `TB` (distinct, monitor alone): during the first full drain, 13 + 50 + 20 + 3 per polled name + 10 > 128 after ≈ 12–15 names →
  OOM on `ScheduledTasks` (in `popOperations`/`toCQLString`) within the first drain that sees a full queue.
- `IB` (distinct, monitor off): 13 + 20 ≈ 33 → survive.

**Budget search (B).** End of `popOperations` with 50 distinct names: 50 (refilled queue) + 50 + 100 + 10 + N + 20 ≈ 243 regions
(3.8 GiB) → **4 GiB (256)** fails in `getLogMessage` (+ 65 + 128). **8 GiB (512):** ≈ 243 + 65 + 128 = 436 at the last doubling, then
`toString` (+96) and logback's copy (+96–192) with the map still on the drain thread's frame → 480–560 → OOM likely; if the drain
survives, the async writer must lay out and write ≈ 1.6 GB every drain (≈ 8–15 s on this SATA disk at ≈ 150–200 MB/s) while the
next drain builds another ≈ 3.8 GB → OOM within 2–3 drains. **12 GiB (768):** the async backlog alone grows ≈ 1.6 GB per drain it
falls behind; endpoint = OOM or the disk guard (each written message adds ≈ 1.6 GB to `debug.log`). Ceiling of the contract
(count) itself: 100 operations × 16 MiB = 1.6 GiB; the measured U is expected at 2–3× that because of the names and copies, which
no control covers.

**Budget search (A).** The monitor layer is fixed (≈ 63–76 regions = 1.0–1.2 GiB at any heap); the render and in-flight layers grow
with N. 4 GiB (256 regions): fails when N + R × 6 ≳ 160–170, i.e. N ≈ 26–48 at R ≈ 0.5 N; B11's `T4-1` at N = 26 (empty partition,
no full monitor in every second) survived with 189 regions max. 8 GiB: needs N ≳ 100 (R ≥ 60), B11 saw R ≤ 67 at N = 256: unlikely
(single-node client limit), not planned.

Direct memory: Netty frames ≈ 2–2.5 × K; at N ≤ 32 ≤ 1.3 GB ≪ 15,872 MiB. Disk: identical-value drains write one ≈ 32 MB name per
drain (≈ 1.2 GB per 180 s run) to `debug.log`; distinct-value drains ≈ 1.6 GB each → the disk guard (§2.6).

### 2.5 Workload and environment

- **Node:** `ms0640` only (victim and client on the same node, as B11). Work dir `/mydata/s4/r12-w5/` (trees, `harness/`, `seed/`,
  `runs/<run-id>/`, `series.log`). Before anything: `pgrep -af CassandraDaemon` empty; do not touch `/mydata/s2r2`, `/mydata/u1r2`,
  `/mydata/s4/cassandra-base` (read/copy only). `sudo loginctl enable-linger jason92` at start, `disable-linger` at the end.
- **Schema:** `CREATE KEYSPACE r12 WITH replication = {'class':'SimpleStrategy','replication_factor':1};`
  `CREATE TABLE r12.t (k int, c int, v blob, PRIMARY KEY (k, c));`
- **Seed data (built once, restored before every run):** partition k = 0 empty; k = 1: 100,000 rows; k = 2: 300,000 rows;
  k = 3: 1,000,000 rows; `v` = 8-byte big-endian `c` (never equal to a 16 MB value, so every read returns 0 rows). Load with
  `client.py --load` (prepared `INSERT INTO r12.t (k, c, v) VALUES (?, ?, ?)`, unlogged single-partition batches of 150 rows,
  ≤ 5 KiB, 8 connections), then `nodetool flush r12`, `nodetool compact r12`, `nodetool drain`, stop, and
  `tar -C <tree> -cf /mydata/s4/r12-w5/seed/data.tar data` (≈ 50–150 MB; record size and `sstablemetadata`/`ls` of the table dir).
  Every run: `rm -rf <tree>/data <tree>/logs` then `tar -C <tree> -xf seed/data.tar` (both trees use the same tar; schema lives in
  the system tables). Same data state in every arm.
- **Statement:** prepared once per connection, `SELECT c FROM r12.t WHERE k = <K> AND v = ? ALLOW FILTERING`, consistency ONE, one
  bound blob of S = 16,000,000 B. `<K>` = `k_sel` from the calibration (frozen rule below). A legal read (single partition, filtering
  a regular column, value ≤ frame and `max_value_size`), returns 0 rows, writes nothing.
- **Client** (`harness/client.py`, B11's raw protocol-v4 client, Python standard library) with these changes:
  `--k K` (statement partition); `--distinct` (each connection keeps its own `bytearray` copy of the frame and, before every send,
  writes `struct.pack('>IQ', conn_id, seq)` over the first 12 bytes of the value; without it all requests share one `bytes` frame,
  `00 01 02 … ff` repeated, as B11); `--load` (seed mode above); `--single K --count 20` (calibration: one connection, 20 sequential
  untraced requests, latency per request). Unchanged: one source IP per connection (`127.1.(i // 250).(1 + i % 250)`), STARTUP →
  PREPARE → closed loop of EXECUTE frames, flags `0x02` (tracing) or `0x00`, ramp (`--ramp … --step-s 60`) and fixed (`--fixed N
  --hold-s H`) modes, per-completion lines and the per-second line (`open established outstanding completed errors K_client`).
- **Run driver** (`harness/run.sh <run-id> <base|iv> <heap> <on|off> <ident|distinct> <mon50|mon0> <fixed:N | ramp:list> <hold-s>`):
  preflight (no daemon; ports 7000/7199/9042 free; `/mydata` free ≥ heap + 6 GiB) → wipe and restore seed → start (`MAX_HEAP_SIZE`,
  `CASSANDRA_HEAPDUMP_DIR=<run dir>`, `JVM_EXTRA_OPTS` = `-Dcassandra.monitoring_max_operations=0` for `mon0`, plus
  `-XX:-HeapDumpOnOutOfMemoryError` for heaps ≥ 8 GiB; `systemd-run --user --scope -p MemorySwapMax=0`) → wait for `Starting
  listening for CQL clients` (≤ 300 s) → `VM.flags`, `VM.command_line`, and the `system.log` line `Scheduling monitoring task with
  report interval of 5000 ms, max operations <50|0>` (abort as invalid if it does not match the arm) → monitors → client → endpoint =
  first of heap OOM, direct OOM, disk guard, hold end → stop (`kill`, `-9` after 60 s) → extract the monitor counts from
  `debug.log*` (`grep -aoE` patterns of §2.6, never whole lines) into `runs/<id>/drains.txt` → **delete `debug.log*`** → copy
  `system.log`, `gc.log*`, stdout → `summarize.py`. Launch with `( setsid nohup … < /dev/null > /dev/null 2>&1 & )`, bounded polls,
  never a foreground `sleep`; kill by PID.
- **Series** (`harness/series.sh`, B11's): one run at a time, **no new run starts after 16:30 America/New_York 2026-11-20**, `STOP`
  file honoured.

**Calibration (`CAL`, base, 2 GiB, mon50, not a reading).** (a) For k = 1, 2, 3: `--single K --count 20` untraced → median
latency L1, L2, L3 (server-side ≈ client latency; S0 of B11 had ≈ 150 ms for the frame alone with tracing). **Frozen rule:**
`k_sel` = the smallest k with median ∈ [600, 2,500] ms; if none, the k with the median closest to 1,000 ms. (b) At `k_sel`, N = 13
untraced, identical, 60 s: the drains must show the slow queue full (`was slow ≥ 50 times` or `were dropped` > 0) in ≥ 2 drains
and client errors < 5 %; if the queue is not full, move to the next larger k and repeat (b) once; if still not full, condition A
runs as the fallback F (below). (c) N = 2 traced, 30 s: `system_traces.sessions` `bound_var_0_v` = 1,004 chars ending `...'`,
`Thread.print` shows `traceQuery`.

**Arms.** All S = 16,000,000 B, `k_sel`, base build unless stated, same instruments; "hold" is at full N.

| Run | Build | Heap | Tracing | Values | Monitor | N | Hold | Purpose |
|---|---|---|---|---|---|---|---|---|
| `SEED` | base | 2 GiB | — | — | 50 | 8 (load) | — | build `seed/data.tar` |
| `CAL` | base | 2 GiB | off / on | ident | 50 | 1, 13, 2 | as above | `k_sel`; monitor fill; trace row |
| `RT` ramp | base | 2 GiB | on | ident | 50 | 8, 13, 16, 20, 24, 32 | 60 s / step | N_A = first failing step |
| `TA-1..3` | base | 2 GiB | on | ident | 50 | N_A | ≤ 180 s | A: stack (V1) |
| `CA-1..3` | base | 2 GiB | **off** | ident | 50 | N_A | 150 s | A: monitor alone, no tracing (V2) |
| `IM-1..3` | base | 2 GiB | on | ident | **0** | N_A | 150 s | A: render alone — intervention on layer M (V4) |
| `IR-1..3` | **iv** | 2 GiB | on | ident | 50 | N_A | 150 s | A: monitor alone, render bounded — intervention on layer R (V4) |
| `TB-1..3` | base | 2 GiB | off | **distinct** | 50 | 13 | ≤ 150 s | B: monitor alone, distinct names (V1) |
| `CB-1..3` | base | 2 GiB | off | ident | 50 | 13 | 150 s | B: matched control (only if N_A ≠ 13; else `CA` is it) |
| `IB-1..3` | base | 2 GiB | off | distinct | **0** | 13 | 150 s | B: intervention (V4) |
| `TB4-1` → `TB8-1` → `TB12-1` | base | 4 → 8 → 12 GiB | off | distinct | 50 | 13 | ≤ 180 s | B: largest failing budget (stop at the first survivor) |
| `RT4` ramp | base | 4 GiB | on | ident | 50 | 26, 32, 48, 64 | 60 s / step | A: largest failing budget |
| repeats | as test | largest failing B budget > 2 GiB | off | distinct / ident | 50 / 0 | 13 | as above | `TB<X>-2,3`, `CB<X>-1..3`, `IB<X>-1..3` if time allows |

**Frozen rules.** N_A = the first failing step of `RT` (8 ≤ N_A ≤ 32). If `RT` reaches 32 without failure, condition A runs as
**fallback F**: B11's empty partition (k = 0, where the render's own latency fills the monitor) at N = 13 with `TA`, `IM`, `IR`, `CA`
×3 each (then `IR` and `CA` show the monitor does not fill without the render, and `IM` alone separates the layers; the mixed claim
then rests on `IM` and the dump shares). If a fixed arm gives mixed outcomes (1/3 or 2/3), add two repeats (n/5). One rerun per invalid
run (node failed to start, client failed before full N, wrong monitor setting, disk guard in a 2 GiB arm).

### 2.6 Instruments

| What | How | Interval | Gives |
|---|---|---|---|
| Live humongous (U, independent of K) | shipped `gc.log`: per GC `Humongous regions: X->Y`, Eden/Old, `Pause Full`, causes | every GC | U_h = Y × 16 MiB after each GC |
| Heap occupancy | `jcmd <pid> GC.heap_info` (no forced GC) | 2 s | used / committed |
| Monitor fill and drains (U_count vs C) | `debug.log*` before deletion: `grep -aoE '[0-9]+ operations (were slow\|timed out) in the last [0-9]+ msecs'`, `'was slow [0-9]+ times'`, `'timed out [0-9]+ times'`, `'\.\.\. \([0-9]+ were dropped\)'`, `'ALLOW FILTERING>, (total )?time [0-9]+ msec'` (count = single-occurrence names), plus `system.log` `Some operations were slow`/`timed out` and the `Scheduling monitoring task … max operations` line | per drain | queued per drain, dropped, distinct names per drain, drain period |
| `debug.log` size | `stat` of `<tree>/logs/debug.log*` | 2 s | bytes written by the monitor's messages |
| Threads | `jcmd <pid> Thread.print` → `threadcount.py` extended: NTR total / in `traceQuery` / in `Hex.bytesToHex` etc. (B11), **plus** `ScheduledTasks` top frame in `popOperations`/`toCQLString`/`Hex.bytesToHex`, `getLogMessage`/`String.format`, logback; `AsyncAppender-Worker` in layout/encoder/`write` | 5 s | R(t), drain phase, writer phase |
| K (server) | `nodetool sjk mx` `RequestsSize`, `PausedConnections` (≈ 25–30 s on an m400, as B11) | 10 s target | in-flight bytes vs C |
| K (client) | per-second line | 1 s | outstanding × B |
| Process | `RssAnon`, scope `memory.current`, `memory.events` | 2 s | native/direct growth |
| Disk guard | `df --output=avail /mydata` | 2 s | free < 5 GiB → `kill -9` the daemon, write `DISKGUARD` (endpoint "disk guard", not an OOM) |
| Throughput | client completion lines | per request | ok/s, latency, errors (ReadTimeout = failed-queue feed) |
| Endpoint | `stdout.txt` `java.lang.OutOfMemoryError: …` (`grep -F`), `Dumping heap`, `OnOutOfMemoryError`; `system.log` ERROR | end | endpoint type, time after full N |
| Holder at failure (V5) | shipped heap dump → controller (`scp` to `/tmp/r12-dumps/` on the controller, 47 GB free), then: `hprof_oome_thread.py` (B11 copy), `bigarrays.py` (B11), `retainers.py` (B11), and **`holders.py`** (new, from `bigarrays.py` + `retainers.py`): every primitive array ≥ 1 MiB is assigned to the **first** root category that reaches it in a multi-source BFS in this order: **M** = static `MonitoringTask.instance` and `ScheduledTasks` thread frames; **R** = NTR thread frames whose stack contains `traceQuery` (render arrays: `char[32,000,000]`, `byte[32,000,000]`, `byte[32,000,002]`); **F** = other NTR frames and Netty/request objects (in-flight values); **L** = logback (`AsyncAppender` queue, worker frames); **O** = everything else. Also counts `SlowOperation`/`FailedOperation` instances, queue sizes, map entries and names (`byte[]` of 32,000,002–32,000,400) | every failing 2 GiB run (full); larger budgets: first failing run (4 GiB full; ≥ 8 GiB no dump) | shares H_M, H_R, H_F, H_L of the dump total |

Samplers identical in every arm; no forced GC or histogram under load. `summarize.py` writes per run: endpoint, time to endpoint,
N established, ok completions and rate, median latency, errors by code, max R, U_h median/max, max K, max RssAnon, drains (count,
queued, dropped, distinct names), `debug.log` bytes, dump shares.

### 2.7 Predicted response, outcome rows and stopping budget

**Predicted protective response:** none bounds the bytes. The in-flight limit admits one request per connection (paused above
heap/10); the monitor queue caps the count at 50 and drops the rest; no check charges the kept values, the names, the log message or
the render.

**Predicted readings (2 GiB).** `CAL`: L1 ≈ 0.3–0.8 s, L2 ≈ 1–2.4 s, L3 ≈ 3–8 s (aarch64 scan ≈ 3–8 µs/row) → `k_sel` = 1 or 2; at
N = 13 every drain reports the queue full (`was slow 50 times`, dropped > 0) and a drain period of 5–20 s (50 uncut renders per
drain on one thread). `RT`: first failure at N = 13–20 (N_A). `TA` OOM 3/3 within 90 s of full N; OOME thread an NTR thread under
`traceQuery` or `ScheduledTasks` under `popOperations`; dumps **H_M 35–50 %, H_R 20–40 %, H_F 8–15 %**. `CA`, `IR`: survive 3/3
with full drains (queued 50, dropped > 0), U_h after GC median 60–90 regions, Full GCs ≤ 3. `IM`: survive 3/3, no drain lines,
U_h median 30–70 regions. `TB`: OOM 3/3 within 30 s of full N (in the first drain with ≥ 12–15 distinct names), OOME thread
`ScheduledTasks` (`popOperations` → `toCQLString` → `Hex.bytesToHex`/`String.format`, or `getLogMessage`), dumps H_M ≥ 70 % with
12–50 name strings. `IB`: survive 3/3, U_h median ≤ 40 regions. `TB4-1` OOM (in `getLogMessage`), `TB8-1` OOM (likely),
`TB12-1` OOM or disk guard. `RT4` first failure at N = 32–64 or none. Throughput: `CA`/`IR`/`IM` complete ≥ 50 % of the untraced
rate measured in `CAL` (b).

| Row | Observation | Reading |
|---|---|---|
| A1 | `TA` ≥ 3/5 (or 3/3) heap OOM; `CA` 0/3, `IR` 0/3, `IM` 0/3; every `TA` dump has **H_M ≥ 20 %, H_R ≥ 20 %, H_M + H_R + H_F ≥ 60 %**; drains full in `TA`/`CA`/`IR` | condition A: **mixed**, V5 met (both layers present, each needed); `verified-OOM · deployment` if V1–V7 hold |
| A2 | `IM` (render alone) OOMs ≥ 1/3 | the monitor is not needed at N_A: the render bypass alone (B11's claim) — condition A not shown as mixed; record `IM` dump shares; retry for A unless `IM` meets V1 with H_R dominant (then report as a render-bypass reading, no matched control: retry) |
| A3 | `CA` or `IR` (monitor alone, identical values) OOMs ≥ 1/3 | the monitor alone suffices with identical values: condition A collapses into the monitor domain (B's mechanism with one name); record shares |
| A4 | `TA` < 2/5 | the stack does not reach OOM reliably at N_A: `verified-gap` at best, retry for A |
| A5 | drains not full in `CA`/`IR` (queue < 50) | the scan did not make reads slow: arm invalid; fallback F |
| B1 | `TB` ≥ 3/3 heap OOM; `CB`/`CA` (at 13) 0/3; `IB` 0/3; dumps H_M ≥ 60 % with ≥ 10 kept names, or OOME thread under `MonitoringTask` | condition B: **unprotected accumulation** (count cap, no byte bound) — `verified-OOM · deployment` if V1–V7 hold; largest failing budget from `TB4/8/12` |
| B2 | `TB` OOMs but H_M < 60 % and the OOME thread is not the monitor | attribution fails: retry for B |
| B3 | `TB` survives | distinct names do not converge at 2 GiB (drain slower than predicted, or names not kept): report U_h, names per drain; retry for B |
| X1 | direct `OutOfMemoryError` / Netty first | competing endpoint (lead B9): rerun the arm once; if repeated, invalid for that arm |
| X2 | GC service loss (≥ 90 % STW over ≥ 60 s) without OOM | `verified-gap · service-loss` at best for that condition |
| X3 | disk guard | not an OOM; for `TB12` it ends the budget search ("largest failing budget" = last OOM budget) |

**Case verdict rule (frozen).** R12 is **true positive** if condition A meets A1 with V1–V7, or condition B meets B1 with V1–V7
(the case file records a per-condition status; the claimed shape is whichever passed, both if both). **False positive** only if both
conditions ran as designed, reached their load, and the measurements show neither layer combination can reach OOM at ≥ 512 MiB.
Otherwise **retry**.

**Stopping budget.** Per run: ≤ 300 s to start; ramps 60 s per step; fixed test arms ≤ 180 s (B ≤ 150 s at 2 GiB), controls and
interventions 150 s. One run at a time. No escalation beyond the planned steps after an OOM. No new run after **16:30 ET**. At most
5 runs per arm per budget (3 + 2 for mixed outcomes) plus one rerun per invalid run.

### 2.8 Controls and intervention

- **Condition A (2 × 2 on the same data, statement, N, heap):** test `TA` = render + monitor; matched controls = each layer alone:
  `CA` (monitor alone, no tracing: the protected path) and `IM` (render alone). Interventions, one per layer: `IM` removes layer M
  (`-Dcassandra.monitoring_max_operations=0`, a shipped JVM property, intervention arm only) and `IR` removes layer R's memory but
  keeps tracing and the slow reads (B11's `iv.patch`: render at most the first 1000 bytes; the stored trace value is the same 1,004
  characters). Because the scan, not the render, makes the reads slow, `IR` leaves the monitor full — the confound B11 could not
  separate. Mixed is shown when `TA` fails and both single-layer arms survive with their layer measured present (drains full in `IR`
  and `CA`; R > 0 and render arrays in `IM`'s `Thread.print`).
- **Condition B:** test `TB` (distinct values); matched control `CB` = the same run with identical values (one kept name per drain
  instead of up to 50; same count, same bytes per value, same data, N and heap) — `CA` serves when N_A = 13 (documented equivalence:
  same series, build, heap, N, statement, data, instruments); intervention `IB` = `TB` with `-Dcassandra.monitoring_max_operations=0`.
  A diagnostic patch that queues the operation with a cut name and without its command would be a closer fix; it is not needed for
  attribution and is not built (time).
- **V-table plan:** V1 `TA`, `TB` (n/N); V2 `CA` (+`IM`) and `CB`/`CA`; V3 U_h, dump shares, drain counts vs K (`RequestsSize`) and
  vs the count cap; V4 `IM` + `IR` (A), `IB` (B), with throughput; V5 OOM line + `hprof_oome_thread.py` + `holders.py` shares on
  every 2 GiB failing dump; V6 §2.3 (one property changed only in `IM`/`IB`, the patch only in `IR`); V7 2 GiB (ideal) and the largest
  failing budget.

### 2.9 Time plan (stage 2: start ≈ 12:00, all work done by 17:30 America/New_York, 2026-11-20)

| Window (ET) | Work |
|---|---|
| 12:00–12:15 | read, hash check, node check (idle, free ≥ 15 GiB), linger, copy trees, iv patch + `ant jar` + `javap` check; port B11's harness (client options, driver, monitors, `holders.py`) |
| 12:15–12:35 | `SEED` (start ≈ 1.5 min, load 1.4 M rows ≈ 1–3 min, flush/compact/drain ≈ 2 min, tar) |
| 12:35–12:45 | `CAL` (a)–(c) |
| 12:45–12:55 | `RT` (≤ 6 steps × 60 s + start + dump) |
| 12:55–13:55 | `TA` ×3, `CA` ×3, `IM` ×3, `IR` ×3 (≈ 4.5–5 min each; dumps scp'd and analysed on the controller in parallel) |
| 13:55–14:25 | `TB` ×3, `IB` ×3 (`CB` ×3 adds 15 min if N_A ≠ 13) |
| 14:25–15:05 | `TB4-1`, `TB8-1`, `TB12-1` (stop at the first survivor), `RT4` |
| 15:05–16:30 | repeats at the largest failing B budget (`TB<X>-2,3`, `CB<X>` ×3, `IB<X>` ×3) and the n/5 expansions; last start 16:30 |
| 16:30–17:30 | dump analyses, self-check, §3/§4, write-backs, cleanup (no process, scope or linger left) |

**Priority if late:** `SEED` → `CAL` → `RT` → `TA` ×3 → `IM` ×3 → `CA` ×3 → `TB` ×3 → `IB` ×3 → `IR` ×3 → (`CB` ×3) → `TB4-1` →
`TB8-1` → `RT4` → `TB12-1` → repeats. The 2 GiB set for both conditions needs ≈ 2 h 30 min from 12:00.
**Disk (18 GiB free):** trees ≈ 1 GB, seed ≤ 0.2 GB; per run `debug.log` deleted after extraction; 2 GiB dumps (≈ 1.6–2.0 GB) copied
to the controller and deleted from the node after the copy (keep at most 2 on the node); 4 GiB dump (≈ 4 GB) likewise; no dumps at
≥ 8 GiB; preflight free ≥ heap + 6 GiB; disk guard at 5 GiB. **RAM/cores:** largest daemon 12 GiB heap + ≤ 2 GiB direct + ≈ 1 GiB
native, client ≤ 0.5 GiB (13 × 16 MB copies in distinct mode): ≤ 16 GiB of 62 GiB; 8 cores shared by daemon, drain thread and client.

`sha256 of §1–§2 at freeze: b9ad1b497a0b87613a977643d41b66e0e230a31d49e35eaa2d3b0d90a4e38a26` (computed as `awk '/^## 1\. Candidate/{p=1} /^`sha256 of §1–§2 at freeze/{p=0} p' <this file> | sha256sum`, i.e. from the `## 1. Candidate` line up to, not including, this line; 2026-11-20) · amendments after the freeze: none.

## 3. Runs (stage 2)

### 3.0 Amendments (dated, each made before the readings it affects)

- **A-1 (2026-11-20 10:57 ET, before `CAL-b`).** The `Scheduling monitoring task … max operations <n>` line is not logged at
  startup: `MonitoringTask.instance` is a static initializer that runs at the first slow or failed operation
  (`MonitorableImpl.java:101`, `:115`). The driver therefore checks the line in `system.log` **after** the run (same rule: a
  wrong value makes the run invalid; a missing line is recorded). Harness only: `drains.sh` pipes `debug.log*` through
  `squash.py` (runs of ≥ 64 hex digits → `H`) before the same `grep -aoE` patterns — the plain `grep -o` took > 4 min on
  ≈ 300 MB of names. (`CAL-a`'s drain counts were lost: the driver deleted `debug.log*` while the slow extraction was being
  replaced; `CAL-a` is a latency calibration and its drain lines are not a design reading.)
- **A-2 (2026-11-20 11:00 ET, after `CAL-b`, before `RT`).** `CAL` (b)'s "slow queue full in ≥ 2 drains" cannot be met in
  60 s at k = 2: one drain lasts ≈ 20–30 s (`popOperations` renders every polled operation and keeps polling a queue that
  refills meanwhile; `CAL-b`: one slow drain with 87 merged operations and **190 dropped**, plus one failed-op drain). The fill
  the rule tests is shown (dropped > 0); client errors 14/285 = 4.9 % < 5 %. `k_sel` stays **2** (no move to k = 3, whose
  N = 13 latency would exceed the 5 s deadline). The fill is re-checked in every `CA`/`IR` run (row A5).
- **A-3 (2026-11-20 11:20 ET, after the `RT`, `TA-1..3`, `IM-1..2` readings, before every later dump reading).** Two
  analysis defects found on the first dumps, corrected for every dump read from then on:
  (a) `holders.py`'s forward BFS leaked: an *idle* `ScheduledTasks` frame reached other periodic tasks through its
  `DelayedWorkQueue` and so claimed arrays for **M** even with the monitor off (`IM-2`: H_M 30.5 % with
  `maxOperations=0` and empty queues). Fix: traversal also stops at `ScheduledThreadPoolExecutor$DelayedWorkQueue` and
  `java.util.concurrent.FutureTask` instances (as it already did at `Thread`/`ThreadPoolExecutor`/`ClassLoader`).
  Even fixed, forward reachability from frames still crosses shared structures (`IM-2`: the 19 values then fall to **R**),
  so (b) a supplementary analysis `owners.py` assigns each live array ≥ 1 MiB to its **nearest** identifying owner walking
  referrers backwards (M = `MonitoringTask$*` objects or the drain frame; R = render-shaped arrays in a `traceQuery` NTR
  frame; **Q** = a `QueryCancelledException` or a frame under `QueryCancelledException.<init>`; L = logback; F = other NTR /
  Netty / transport objects; O = other). Q is a holder the design did not map (§2.2 row 7 called the read-deadline path
  "small transients"; see §3.4). The frozen V5 thresholds are applied to `holders.py` (fixed) shares; `owners.py` is reported
  beside them. `RT`, `TA-2`, `TA-3` dumps had already been deleted after a pre-fix reading (a mistake: dumps are kept on the
  controller until the case is written from here on); their H_M is an upper bound (the leak can only add to M), and their
  H_R would gain at most the ≤ 5 traced requests' own values (≤ 5 × 15.3 MiB ≈ 4 %) from the fix.
- **A-4 (2026-11-20 11:37 ET, after `TB-1..3`, before `TB-4`, `TB-5`).** `TB` reached heap OOM 3/3 but the B1
  attribution (H_M ≥ 60 % with ≥ 10 names, or the OOME thread under `MonitoringTask`) held in 2/3 (`TB-2` failed it). The
  frozen n/5 rule ("mixed outcomes → two more repeats") is applied to the claimed endpoint, a **monitor-attributed** OOM:
  `TB-4`, `TB-5` added (same arm). `IM` (1/3 OOM) gets its two repeats under the rule as written.
- **A-5 (2026-11-20 11:57 ET, after `TB8-1`, before `TB12-1`).** The preflight "free ≥ heap + 6 GiB" cannot be met at
  12 GiB on this node (≈ 15 GiB free with the trees and seed). Its heap term is room for a heap dump, and runs at ≥ 8 GiB
  take no dump (§2.3), so for those runs the preflight is free ≥ 6 GiB (`run2.sh`/`series2.sh`/`after2.sh`, copies made
  while `run.sh` was executing `RT4`; the disk guard at 5 GiB is unchanged).

No other deviation: every arm ran with the shipped `conf/`, the frozen statement, data, N and instruments; the only
changed constraint was `-Dcassandra.monitoring_max_operations=0` in `IM`/`IB` arms (confirmed by the `max operations 0`
line in every one of them) and the iv build in `IR` arms. Every monitor-on run that had a slow or failed read logged
`max operations 50` (`TB12-1`'s line is in the rolled `system.log` zip); `FIR`/`FCA` (fallback F) never had
one, so the monitor was never initialised there (A-1: recorded, not invalid). Fallback F (§3.5.1) is the
design's own rule, triggered by row A5, not an amendment.

### 3.1 Environment (V6, V7)

- Stage 2 by a fresh OOM-agent session, 2026-11-20 10:44–13:05 ET; last run started 12:56 ET. Freeze hash checked before anything (matches; re-checked
  after the runs). Repo commit `581de552`; build tree `ded97640` (`cassandra-5.0.9`, clean), copied to
  `/mydata/s4/r12-w5/cassandra-base`; iv tree = that copy + [`harness/iv.patch`](harness/iv.patch) (3 lines; `git diff` as in
  B11), `ant jar` 38 s, `javap … | grep -c ByteBuffer.duplicate` = **1** (iv) / **0** (base).
- Node `ms0640` (aarch64, 8 cores, 62 GiB, Ubuntu 22.04, kernel 5.15, cgroup v2, OpenJDK 11.0.33): idle at start (no
  `CassandraDaemon`, load 0.00), `/mydata` 18 G free; `/mydata/s2r2`, `/mydata/u1r2`, `/mydata/s4/cassandra-base` not touched
  (base read/copied only). Linger enabled for the session, disabled at the end.
- Resolved per run (`VM.flags`, `VM.command_line`): `-Xms = -Xmx` = 2 / 4 / 8 / 12 GiB, G1, region 16 MiB, `-XX:+AlwaysPreTouch`,
  **`MaxDirectMemorySize` = 16,642,998,272 B (15,872 MiB, auto)**, open files 100,000, `-XX:+HeapDumpOnOutOfMemoryError`
  (`-XX:-HeapDumpOnOutOfMemoryError` at 8 and 12 GiB), `OnOutOfMemoryError="kill -9 %p"`; scope `r12-<run>` with
  `MemorySwapMax=0`, no `MemoryMax`. The monitor line read back in every run's `system.log`: `report interval of 5000 ms,
  max operations 50` (or `0` in every `IM`/`IB` run).
- Seed (`SEED`, 10:49 ET): 1,400,000 rows (k = 1: 100,000; k = 2: 300,000; k = 3: 1,000,000) loaded in 12.1 s by 9,334
  unlogged 150-row batches, 0 errors; flush, compact → one SSTable (`nb-4-big-Data.db` 12,372,726 B, 3 partitions), drain;
  `seed/data.tar` 46,274,560 B, restored before every run.
- Full logs stay on the node in `/mydata/s4/r12-w5/runs/<run>/` (`driver.txt`, `client.txt`, `completions.txt`,
  `heapinfo.txt`, `threads.txt`, `ksrv.txt`, `drains.txt`, `system.log*`, `gc.log*`, `stdout.txt`, `summary.txt`);
  `debug.log*` deleted after extraction (as designed). Excerpts: [`logs/`](logs/) — `runs-table.md` (every run),
  `dump-<run>.txt` (`hprof_oome_thread.py` + `holders.py`), `owners-<run>.txt` (`owners.py`), `summaries/<run>.txt`,
  `series.log`, `seed-driver.txt`, `build-iv.log`, `vm-flags-TB-1.txt`. Heap dumps were copied to the controller (`node0.jason92-325405`,
  `/tmp/r12-dumps/`), read, and deleted on both sides except two kept as representatives: `TB-4.hprof` (1.9 GB, condition B)
  and `FTA-2.hprof` (1.8 GB, condition A). On the node, `stdout.txt`, `gc.log*` and `completions.txt` were gzipped after the
  runs (2.2 GB left in `/mydata/s4/r12-w5`).
  Harness: [`harness/`](harness/) (`client.py`, `run.sh`/`run2.sh`, `series.sh`/`series2.sh`, `after.sh`/`after2.sh`,
  `seed.sh`, `monitor.sh`, `threadcount.py`, `drains.sh`, `squash.py`, `summarize.py`, `table.py`, `holders.py`,
  `owners.py`, B11's `bigarrays.py`, `retainers.py`, `hprof_oome_thread.py`, `build.sh`, `iv.patch`).

### 3.2 Calibration

| Step | Reading |
|---|---|
| `CAL` (a), 1 connection, 20 untraced requests each | k = 1 median **286 ms** (264–2,049); k = 2 median **770 ms** (716–1,013); k = 3 median **2,264 ms** (2,188–2,498) → **`k_sel` = 2** (smallest k with median in [600, 2,500] ms) |
| `CAL` (b), k = 2, N = 13 untraced, identical, 60 s | 271 ok, median 2,311 ms, errors 14/285 = 4.9 % (12 read failures, 2 read timeouts, all in the first seconds); one slow drain logged: **87 merged operations, 190 dropped**, drain interval 19.9 s; one failed-op drain (14). U_h after GC median 71, max 111 regions; 3 Full GCs. One drain lasts ≈ 20–30 s → A-2 |
| `CAL` (c), k = 2, N = 2 traced, 30 s | `system_traces.sessions` `bound_var_0_v` = **1,004** chars, `0x0001020304…f1f2...'`; `Thread.print` R up to 2 (`traceQuery`, `Hex.bytesToHex`); 60 ok, median 992 ms |

### 3.3 All runs (2 GiB unless named; N = 13, k = 2)

"t" is the last client completion after full N (≈ time to the endpoint); "ST" counts `Thread.print` samples with the
`ScheduledTasks` thread inside `popOperations`; U_h from `gc.log` (`Humongous regions: X->Y`, regions of 16 MiB).

| Run | Endpoint | t (s) | ok | median lat (ms) | errors | max R | ST in pop / samples | U_h after GC median / max | Full GCs | slow drains logged (queued, dropped) | failed drains (queued) |
|---|---|---|---|---|---|---|---|---|---|---|---|
| `RT` ramp 8 → 13 | heap OOM at N = 13 (18 s into the step) | 17.6 | 16 | 3,834 | 29 | 3 | 9/12 | 78 / 120 | 13 | 0 | 0 |
| `TA-1` | heap OOM | 21.4 | 5 | 4,923 | 19 | 11 | 0/3 | 81 / 116 | 3 | 0 | 0 |
| `TA-2` | heap OOM | 20.5 | 0 | – | 26 | 7 | 0/3 | 86 / 118 | 6 | 0 | 0 |
| `TA-3` | heap OOM | 22.7 | 0 | – | 37 | 12 | 1/4 | 96 / 122 | 5 | 0 | 0 |
| `CA-1` | hold (survived) | 151.2 | 601 | 2,971 | 19 | 0 | 25/28 | 89 / 110 | 3 | 0 (one drain still running at hold end) | 1 (18) |
| `CA-2` | hold | 151.2 | 706 | 2,540 | 14 | 0 | 23/26 | 71 / 119 | 2 | 1 (**194, 521 dropped**; drain 140 s long) | 1 (14) |
| `CA-3` | hold | 151.2 | 612 | 2,950 | 18 | 0 | 25/28 | 91 / 120 | 3 | 0 (drain running) | 1 (18) |
| `IM-1` | hold | 151.1 | 773 | 2,188 | 18 | 9 | 0/24 | 24 / 113 | 4 | – (monitor off) | – |
| `IM-2` | **heap OOM** | 26.4 | 1 | 5,103 | 31 | 9 | 0/4 | 96 / 119 | 8 | – | – |
| `IM-3` | hold | 151.0 | 740 | 2,281 | 26 | 9 | 0/24 | 27 / 117 | 5 | – | – |
| `IM-4` | hold | 151.2 | 782 | 2,257 | 13 | 8 | 0/24 | 24 / 119 | 3 | – | – |
| `IM-5` | hold | 151.1 | 917 | 1,965 | 13 | 13 | 0/24 | 30 / 115 | 3 | – | – |
| `IR-1` | heap OOM | 21.9 | 2 | 5,668 | 24 | 0 | 1/4 | 87 / 119 | 5 | 0 | 0 |
| `IR-2` | heap OOM | 25.4 | 0 | – | 30 | 1 | 1/4 | 97 / 118 | 8 | 0 | 0 |
| `IR-3` | heap OOM | 23.9 | 0 | – | 25 | 0 | 1/4 | 89 / 119 | 4 | 0 | 0 |
| `TB-1` | heap OOM | 37.3 | 59 | 3,720 | 17 | 0 | 3/6 | 107 / 119 | 15 | 0 | 0 |
| `TB-2` | heap OOM | 22.9 | 0 | – | 26 | 0 | 1/4 | 97 / 116 | 4 | 0 | 0 |
| `TB-3` | heap OOM | 22.8 | 7 | 5,200 | 19 | 0 | 1/4 | 89 / 113 | 4 | 0 | 0 |
| `TB-4` | heap OOM | 34.6 | 62 | 3,366 | 28 | 0 | 3/6 | 105 / 118 | 11 | 0 | 0 |
| `TB-5` | heap OOM | 23.5 | 3 | 4,159 | 23 | 0 | 1/4 | 100 / 119 | 3 | 0 | 0 |
| `IB-1` | hold | 150.8 | **1,274** | 1,427 | 14 | 0 | 0/24 | 22 / 120 | 3 | – | – |
| `IB-2` | hold | 150.9 | **1,222** | 1,484 | 13 | 0 | 0/24 | 24 / 118 | 2 | – | – |
| `IB-3` | hold | 150.9 | **1,128** | 1,549 | 24 | 0 | 0/24 | 21 / 115 | 3 | – | – |
| `TB4-1` (4 GiB) | heap OOM | 71.0 | 213 | 2,864 | 15 | 0 | 7/10 | 218 / 246 (of 256) | 15 | 0 | 0 |
| `TB8-1` (8 GiB) | heap OOM | 124.2 | 554 | 2,457 | 22 | 0 | 16/19 | 415 / 501 (of 512) | 12 | 0 | 0 |
| `TB12-1` (12 GiB) | **hold end (180 s) first**; heap OOM 13 s later, during the stop | 180.8 | 875 | 2,499 | 15 | 0 | 27/30 | 550 / 739 (of 768) | 6 | 0 | 0 |
| `RT4` (4 GiB, ramp 26 → …) | heap OOM at N = 26 | 31.5 | 0 | – | 73 | 7 | 1/4 | 198 / 248 | 3 | 0 | 0 |
| `TB8-2` (8 GiB) | heap OOM | 127.1 | 656 | 2,127 | 13 | 0 | 17/20 | 433 / 504 (of 512) | 17 | 0 | 0 |
| `TB8-3` (8 GiB) | heap OOM (one large allocation; 3.6 GB live after GC) | 29.2 | 100 | 1,907 | 19 | 0 | 2/5 | 123 / 184 | 0 | 0 | 0 |
| `CB8-1` (8 GiB) | hold | 151.2 | 1,173 | 1,559 | 13 | 0 | 23/26 | 139 / 254 | 0 | 0 | 0 |
| `CB8-2` (8 GiB) | hold | 151.1 | 1,136 | 1,619 | 13 | 0 | 23/26 | 137 / 245 | 0 | 0 | 0 |
| `CB8-3` (8 GiB) | hold | 151.1 | 714 | 2,547 | 13 | 0 | 25/27 | 83 / 178 | 0 | 0 | 0 |
| `IB8-1` (8 GiB) | hold | 151.2 | 1,275 | 1,415 | 13 | 0 | 0/24 | 51 / 59 | 0 | – | – |
| `IB8-2` (8 GiB) | hold | 150.9 | 1,071 | 1,697 | 13 | 0 | 0/24 | 45 / 61 | 0 | – | – |
| `IB8-3` (8 GiB) | hold | 151.2 | 1,255 | 1,438 | 13 | 0 | 0/24 | 54 / 67 | 0 | – | – |

Client errors are read timeouts (`0x1200`) and read failures (`0x1300`, the read aborted at the 5 s deadline), almost all in
the first ≈ 10 s after the 13 connections start together on a cold node; `io_error` lines are the connections dropping
when the daemon is killed. K (`RequestsSize`) stayed at ≤ 13 × 16 MB = 208,000,351 B (≤ global heap/10 at 2 GiB = 214,748,364)
with `PausedConnections` 0 in every run: the in-flight limit was never the binding control. Direct memory: no direct OOM,
`RssAnon` ≤ 2.9 GiB at 2 GiB heap. No disk guard fired (lowest `/mydata` free 9.2 GiB).

### 3.4 Heap dumps (V5)

Shares of each dump's shallow total (arrays ≥ 1 MiB). `holders.py` (design categories, BFS fixed per A-3): H_M / H_R / H_F /
H_L / H_O / unreachable. `owners.py` (nearest owner, A-3): M / R / F / **Q** / L. `TA-2`, `TA-3`, `RT`: pre-fix `holders.py`
only (dumps deleted). "Kept ops" = `SlowOperation` / `FailedOperation` instances (queue counts); "names" = name-length
`byte[]` (32,000,003–32,000,400 B) reached first from M.

| Dump | total MiB | OOME thread (top identifying frame) | holders.py H_M / H_R / H_F / H_L / H_O / unreach. (%) | owners.py M / R / F / Q / L (%) | kept ops slow / failed (queue counts) | names in M |
|---|---|---|---|---|---|---|
| `RT` | 1,888 | NTR in `traceQuery` → `Hex.bytesToHex` | 65.7 / 0.0 / 0.0 / 4.8 / 9.7 / 16.2 (pre-fix) | – | 51 / 17 (48 / 17) | 1 |
| `TA-1` | 1,658 | ReadStage in `QueryCancelledException.<init>` → `toCQLString` | 26.7 / 15.7 / 0.0 / 18.4 / 7.4 / 27.9 | 21.2 / 3.7 / 9.2 / 27.6 / 5.5 | 5 / 20 (5 / 18) | 2 |
| `TA-2` | 1,871 | ReadStage, `QueryCancelledException.<init>` | 37.6 / 8.2 / 0.0 / 17.9 / 9.8 / 23.4 (pre-fix) | – | 0 / 19 (0 / 17) | 5 |
| `TA-3` | 1,934 | ReadStage, `QueryCancelledException.<init>` | 48.2 / 6.3 / 0.0 / 14.2 / 11.0 / 16.9 (pre-fix) | – | 0 / 25 (0 / 23) | 12 |
| `IM-2` | 1,809 | `AsyncAppender-Worker` laying out a `Query cancelled (timeout)` event (`ThrowableProxyConverter`) | 0.0 / 30.5 / 0.0 / 23.6 / 13.5 / 27.8 | 0.0 / 0.0 / 7.6 / **53.1** / 5.1 | 0 / 0 (monitor off) | 0 |
| `IR-1` | 1,792 | ReadStage, `QueryCancelledException.<init>` | 23.0 / 0.0 / 21.4 / 22.1 / 13.6 / 16.8 | 17.0 / 0.0 / 9.4 / **46.8** / 5.1 | 2 / 24 (2 / 21) | 1 |
| `IR-2` | 1,865 | ReadStage, `QueryCancelledException.<init>` | 30.3 / 0.0 / 17.3 / 18.0 / 16.4 / 15.2 | 21.3 / 0.0 / 9.8 / **45.0** / 4.9 | 0 / 29 (0 / 27) | 1 |
| `IR-3` | 1,801 | `ScheduledTasks` in `MonitoringTask$OperationsQueue.popOperations` | 25.4 / 0.0 / 24.7 / 18.6 / 15.3 / 11.1 | 17.8 / 0.0 / 6.8 / **51.7** / 5.1 | 0 / 26 (0 / 24) | 2 |
| `TB-1` | 1,907 | ReadStage, `QueryCancelledException.<init>` | **84.0** / 0.0 / 10.5 / 0.0 / 0.0 / 0.1 | **83.2** / 0.0 / 9.7 / 0.8 / 0.0 | 50 / 17 (50 / 1) | **17** |
| `TB-2` | 1,745 | ReadStage, `QueryCancelledException.<init>` | 28.0 / 0.0 / 26.2 / 15.7 / 15.7 / 10.7 | 19.2 / 0.0 / 9.6 / **50.7** / 5.2 | 0 / 26 (0 / 24) | 1 |
| `TB-3` | 1,673 | **`ScheduledTasks` in `popOperations`** | 27.4 / 0.0 / 21.0 / 20.1 / 1.8 / 22.7 | 26.5 / 0.0 / 9.1 / 26.5 / 5.5 | 7 / 19 (7 / 17) | 2 |
| `TB-4` | 1,781 | **`ScheduledTasks` in `AggregatedOperations.getLogMessage` → `FailedOperation.getLogMessage`** | **81.4** / 0.0 / 12.1 / 0.0 / 0.0 / 4.0 | **81.4** / 0.0 / 11.2 / 0.0 / 0.0 | 50 / 15 (50 / 0) | **15** |
| `TB-5` | 1,886 | ReadStage, `QueryCancelledException.<init>` | 24.3 / 0.0 / 19.4 / 16.2 / 8.1 / 27.9 | 21.0 / 0.0 / 10.5 / **30.7** / 4.9 | 3 / 23 (3 / 21) | 2 |
| `TB4-1` (4 GiB) | 3,888 | ReadStage, `QueryCancelledException.<init>` | **89.9** / 0.0 / 4.8 / 0.0 / 1.6 / 0.2 | **89.1** / 0.0 / 3.6 / 2.4 / 0.0 | **104** / 15 (50 / 15) | **53** |
| `RT4` (4 GiB) | 3,797 | ReadStage, `QueryCancelledException.<init>` | 22.1 / 24.2 / 4.0 / 20.9 / 16.1 / 11.4 | 14.1 / 9.6 / 8.0 / **52.2** / 2.4 | 0 / 51 (0 / 49) | 1 |

`TB4-1` in detail (`owners.py`): 53 names of 32,000,0xx B (1,617 MiB) and 104 values (1,572 MiB) held by `SlowOperation`s
— 50 in the queue and 54 polled into `popOperations`' map — plus 13 values (198 MiB) by `FailedOperation`s, a 64,000,086 B
query builder on the `ScheduledTasks` frame: the drain had rendered 53 distinct names while the queue refilled behind it.
`TB-1`/`TB-4`: the failed-op drain (aborted reads, distinct values) had rendered 15–17 names (458 / 427 MiB) while the slow
queue sat full with 50 values (763 MiB).

**A holder the design did not map (Q).** `ReadCommand$QueryCancellationChecker.maybeCancel` throws
`new QueryCancelledException(command)` when a read passes its 5 s deadline, and the constructor builds its message from
`command.toCQLString()` — the full value as hex, ≈ 2S + 60 B, with a 4S builder and `char[2S]` transient on the ReadStage
thread (`QueryCancelledException.java:26`, `ReadCommand.java:791`). `StorageProxy.LocalReadRunnable` then logs it at debug
(`logger.debug("Query cancelled (timeout)", e)`, `StorageProxy.java:2223`); the async appender keeps the event (queue 1,024
events, no byte bound) and lays the message out again (`ThrowableProxyConverter`). With 13 cold reads arriving together,
the first wave of reads passes 5 s (most client errors are in the first ≈ 10 s), so every arm starts with a burst of these
renders. They dominate the dumps of the early OOMs (`owners.py` Q 27–53 % in every OOM at t ≈ 20–31 s it was run on; the
OOME thread is in `QueryCancelledException.<init>` in 10 of the 15 dumps, and in `IM-2` it is logback laying out one), are present in the survivors' first seconds (U_h after GC max 110–120 of 128 regions in every 2 GiB arm at
k = 2, including `IB` and `IM`; absent at k = 0, §3.5.1), and they also feed the failed-op queue (M, row 4) in every monitor-on arm.

### 3.5 Condition A (traced render + monitor, identical values)

- `RT`: first failing step N = 13 → **N_A = 13** (so `CA` is also condition B's matched control, `CB` not run).
- `TA` heap OOM **3/3** (t = 20–23 s); `CA` **0/3** (slow queue full: drains with 194 merged / 521 dropped, the drain thread
  in `popOperations` in 23–25 of 26–28 samples); `IM` (render alone) **1/5** OOM (`IM-2`, t = 26 s); `IR` (render
  bounded, monitor on) **3/3** OOM (t = 22–25 s).
- Dumps: H_R (holders.py) 0–15.7 % in every `TA`/`IR` dump, render-shaped arrays in a `traceQuery` frame ≤ 3.7 %
  (`owners.py`); the OOME thread was an NTR thread in `traceQuery` only in `RT` (pre-fix); in `TA-1..3` it is the
  read-abort render. H_M + H_R + H_F = 42–58 % < 60 %.
- Rows at `k_sel` = 2: **A1 not met** (H_R < 20 % in every `TA` dump; `IM` and `IR` not 0/3); **A2** (`IM` OOMs 1/5) and
  **A3** (`IR` OOMs 3/3 with the render bounded) apply, and **A5**: in every `IR` run the slow queue held 0–2 operations at
  the OOM (dump queue counts; no slow drain logged) — the first-wave reads were aborted at the deadline instead of completing
  slow — so `IR` is not a valid monitor-on control and the frozen rule sends condition A to **fallback F** (§3.5.1). The
  traced arms at k = 2 fail in the start-up burst whether or not the render is bounded (`IR`) and with the monitor off
  (`IM-2`); what tracing adds there is load (more first-wave reads pass the deadline: `IR`/`TA` 0–5 ok completions before
  the OOM vs `CA` 600–700 over 150 s), not the render's bytes.
- `RT4` (4 GiB): heap OOM at its first step N = 26 (t = 31 s, 0 completions), dump Q 52 %, H_R 24 % / owners R 9.6 %.

### 3.5.1 Condition A, fallback F (frozen rule after A5: B11's empty partition k = 0, N = 13, 2 GiB, ×3 each)

Run 12:29–13:00 ET as one series (`K=0`; `FTA`, `FIM`, `FIR`, `FCA`), same build, config, instruments and seed; dumps of the
failing runs read with `holders.py` (fixed) and `owners.py`.

| Run | Endpoint | t (s) | ok | median lat (ms) | errors | max R | U_h after GC median / max | Full GCs | monitor line | dump: OOME thread; H_M / H_R / H_F (holders) ; M / R / F / Q (owners) |
|---|---|---|---|---|---|---|---|---|---|---|
| `FTA-1` | heap OOM | 14.2 | 71 | 1,023 | 0 | 9 | 77 / 113 | 3 | 50 | NTR in `traceQuery` → `Hex.bytesToHex`; **40.1 / 39.3** / 0.0 ; 40.1 / 27.9 / 10.5 / 0.0 |
| `FTA-2` | heap OOM | 18.9 | 106 | 1,265 | 0 | 9 | 102 / 118 | 16 | 50 | `ScheduledTasks` in `logSlowOperations` → `popOperations`; **51.1 / 43.0** / 0.0 ; 51.1 / 34.7 / 7.3 / 0.0 |
| `FTA-3` | heap OOM | 35.4 | 231 | 1,465 | 0 | 11 | 107 / 121 | 67 | 50 | NTR in `traceQuery`; **48.9 / 45.6** / 0.0 ; 48.9 / 34.9 / 9.7 / 0.0 |
| `FIM-1..3` (monitor off) | hold ×3 | 150.6 | 2,538 / 2,550 / 2,631 | 731–754 | 0 | 12–13 | 37–38 / 67–81 | 0 | 0 | — |
| `FIR-1..3` (render bounded) | hold ×3 | 150.3–150.5 | 8,034 / 8,010 / 7,947 | 230–231 | 0 | 1 | 2–3 / 6–9 | 0 | none (no read ever slow) | — |
| `FCA-1..3` (untraced) | hold ×3 | 150.3–150.5 | 8,722 / 8,508 / 8,852 | 207–215 | 0 | 0 | 2 / 6 | 0 | none (no read ever slow) | — |

- With no rows to scan there are no client errors and no deadline aborts (Q = 0 % in every `FTA` dump): the start-up burst
  of §3.4 does not occur. `FTA` heap OOM **3/3** (t = 14–35 s); kept slow operations 46–52 with the queue at 46–50, i.e.
  the monitor full of 16 MB values (702–854 MiB), and the render arrays of 9–11 traced NTR threads (`char[32,000,000]`,
  `byte[32,000,000]`; 488–610 MiB by `owners.py`). Every `FTA` dump meets the A1 thresholds: **H_M 40–51 % ≥ 20 %,
  H_R 39–46 % ≥ 20 %, H_M + H_R + H_F 79–95 % ≥ 60 %.**
- `FIM` (render alone, layer M removed) **0/3**: R up to 12–13 rendering threads in `Thread.print`, U_h after GC median
  37–38 regions, max 67–81 — the render is present and survivable alone. `FIR` and `FCA` **0/3**: reads take 207–231 ms,
  never reach the 500 ms slow threshold, the monitor is never even initialised (no `Scheduling monitoring task` line) —
  the monitor does not fill without the render (as F predicted), so `FIR` removes both layers and only `FIM` separates them.
- Row **A1 met under fallback F**: `TA` 3/3, `CA` 0/3, `IR` 0/3, `IM` 0/3, both layers present in every failing dump. The
  mixed claim rests, as the frozen F text says, on `FIM` and the dump shares: the render bypass (uncharged, 6S per traced
  request) makes the reads slow and supplies ≈ 40 % of the heap; the monitor keeps 50 finished reads' values (≈ 45 %); each
  alone survives at the same N.

### 3.6 Condition B (monitor alone, distinct values) and budget search

- **2 GiB:** `TB` heap OOM **5/5** (t = 23–37 s). Monitor-attributed by the frozen B1 test (H_M ≥ 60 % with ≥ 10 names, or
  the OOME thread under `MonitoringTask`): `TB-1` (H_M 84.0 %, 17 names), `TB-3` (OOME thread in `popOperations`), `TB-4`
  (H_M 81.4 %, 15 names, OOME thread in `getLogMessage`) → **3/5**; `TB-2` and `TB-5` are start-up-burst OOMs led by Q
  (owners Q 51 % / 31 %, M 19 % / 21 %). Matched control `CA` (same arm with identical values: one name per drain) **0/3**;
  intervention `IB` (`monitoring_max_operations=0`) **0/3**, with **1,128–1,274** ok completions in 150 s (2× `CA`'s 601–706;
  median latency 1.4–1.5 s vs 2.5–3.0 s) — the intervention removes the endpoint without stopping useful work. U_h after GC
  median: `TB` 89–107 regions vs `CA` 71–91 vs `IB` 21–24.
- **Budget search** (frozen order, stop at the first survivor): `TB4-1` (4 GiB) heap OOM at 71 s, H_M 89.9 %, 53 names;
  `TB8-1` (8 GiB) heap OOM at 124 s, U_h after GC climbing to 501 of 512 regions with the drain thread in `popOperations`
  in 16/19 samples (no dump at 8 GiB, by design; OOM line in `stdout.txt`); `TB12-1` (12 GiB) reached its 180 s hold end
  with U_h 739 of 768 regions after GC (`heap_info` 12,172,379 K used of 12,582,912 K, 9 s before the stop) and the drain
  still in `popOperations` (27/30 samples) — the endpoint by the frozen budget is **hold end**; its heap OOM came 13 s later,
  during the shutdown (`gc.log` `ReportJavaOutOfMemory` at 220.1 s uptime; client stopped at 207 s), outside the budget.
  **Largest failing budget: 8 GiB.**
- **Repeats at the largest failing budget (8 GiB, no dumps):** `TB8` heap OOM **3/3** (`TB8-1` 124 s, `TB8-2` 127 s with U_h
  after GC rising to 501 / 504 of 512 regions and the drain in `popOperations` in 16/19 and 17/20 samples; `TB8-3` at 29 s:
  one large allocation failed with 3.6 GB live after GC — humongous 147 regions — while the drain was in `popOperations` and
  the async appender encoding 6 s before; not separately attributed). Matched control `CB8` (identical values) **0/3**,
  U_h after GC max 178–254 regions (≤ 50 % of the heap, not growing to the end); intervention `IB8` **0/3**, U_h max 59–67
  regions, 1,071–1,275 ok completions (vs `CB8` 714–1,173). The 8 GiB set is the same 3 + 3 + 3 design as at 2 GiB,
  with the late OOMs (124–127 s) free of the start-up burst.

## 4. Conclusion (stage 2)

**Verdict: true positive** — by the frozen case rule (§2.7): condition B meets B1 with V1–V7, and condition A meets A1 with
V1–V7 under the frozen fallback F (both shapes claimed). At the designed `k_sel` = 2 condition A was not separable (§3.5).

| Condition | Protocol status | Rows | Deciding readings |
|---|---|---|---|
| **B** — monitor alone, distinct values | **`verified-OOM · deployment`**, unprotected accumulation (count-only cap) | B1 | 2 GiB: `TB` heap OOM 5/5, monitor-attributed **3/5** (`TB-1` H_M 84 %, `TB-3` OOME in `popOperations`, `TB-4` H_M 81 % + OOME in `getLogMessage`); `CA` 0/3; `IB` 0/3 at 2× throughput. Largest failing budget **8 GiB** (`TB8` 3/3, `CB8` 0/3, `IB8` 0/3; 12 GiB reached hold end with 96 % of the heap humongous) |
| **A** — traced render + monitor, identical values | **`verified-OOM · deployment`**, **mixed** (render bypass + monitor accumulation), under fallback F (k = 0) | A1 (fallback F); at k = 2: A2, A3, A5 | F: `FTA` heap OOM 3/3, every dump H_M 40–51 % and H_R 39–46 % (sum with H_F 79–95 %); `FCA` 0/3, `FIR` 0/3, `FIM` 0/3. Only 2 GiB tested under F (no budget search there). At k = 2: `TA` 3/3 but H_R ≤ 16 %, `IR` 3/3, `IM` 1/5 — OOMs led by the read-abort render Q in the start-up burst |

**V1–V7 for condition A (fallback F)** (base build, shipped `conf/`, 2 GiB, N = 13, k = 0 empty partition, identical
16 MB values, tracing flag on): V1 `FTA` 3/3 (t = 14–35 s). V2 `FCA` 0/3 (untraced: the protected path) and `FIM` 0/3 (render
alone). V3 dumps: 46–52 kept `SlowOperation`s (queue 46–50) = 702–854 MiB of values, render arrays of 9–11 traced NTR
threads 488–610 MiB (owners), K (`RequestsSize`) ≤ 208 MB < heap/10 — neither layer is charged. V4 `FIM` (monitor removed)
0/3 with 2,538–2,631 ok completions; `FIR` (render bounded) 0/3 with 7,947–8,034 (it removes both layers: the monitor no
longer fills, §3.5.1). V5 OOM line in every `FTA`; OOME threads NTR in `traceQuery` (`FTA-1`, `FTA-3`) and `ScheduledTasks`
in `popOperations` (`FTA-2`); every dump meets the A1 shares. V6 every constraint at default; changes only in `FIM`
(property) and `FIR` (patch). V7 2 GiB (ideal); larger budgets not searched under F (the frozen F set is 2 GiB ×3 each).

**V1–V7 for condition B** (one fixed condition: base build, shipped `conf/`, 2 GiB, N = 13, k = 2, distinct 16 MB values):

| | Evidence |
|---|---|
| V1 | `TB-1..5` heap OOM 5/5 (t = 23–37 s); monitor-attributed 3/5 (rate stated: the other two are start-up-burst OOMs led by Q) |
| V2 | `CA-1..3` (same series, build, heap, N, k, data, instruments; identical values → one name per drain): 0/3 at 150 s, slow queue full (194 merged / 521 dropped; drain thread in `popOperations` 23–25 of 26–28 samples) |
| V3 | U measured independently of K: dumps count the kept operations and bytes (`TB4-1`: **119 operations reachable from the monitor — 104 `SlowOperation` + 15 `FailedOperation` — against the contract's 50 + 50**, 53 names + 117 values = 3.46 GB, 89 % of the heap), U_h from `gc.log`; K (`RequestsSize`) ≤ 208,000,351 B < heap/10, no paused connection |
| V4 | `IB-1..3` (`-Dcassandra.monitoring_max_operations=0`): 0/3, 1,128–1,274 ok completions (vs `CA` 601–706), U_h after GC median 21–24 regions; at 8 GiB `IB8-1..3` 0/3 (U_h max 59–67 regions) vs `TB8` 3/3 |
| V5 | `stdout.txt` `java.lang.OutOfMemoryError: Java heap space` in every `TB` run; OOME thread from the dump (`hprof_oome_thread.py`); dumps show the claimed holder (`SlowOperation`/`FailedOperation` → `SinglePartitionReadCommand` → value, names cached in `Operation.name`, the drain's 64 MB builder) — 3/5 meet the frozen thresholds; ≥ 8 GiB: OOM line, `gc.log` growth and `Thread.print` (drain in `popOperations`) as designed |
| V6 | every §2.2 constraint at its shipped default (resolved at each heap, §2.3); the only change is the intervention property in `IB` |
| V7 | 2 GiB (ideal) heap, direct 15,872 MiB auto, no container limit; largest failing heap **8 GiB** (`TB8` 3/3, `CB8` 0/3, `IB8` 0/3), 12 GiB survived the 180 s budget |

**Reason.** The slow-query monitor bounds how many finished reads it keeps (`monitoring_max_operations` = 50 per queue), not
their bytes, and each kept `ReadCommand` holds its 16 MB filter value after the in-flight limit has released it. At every
drain `popOperations` renders each polled command to an uncut hex CQL string (≈ 32 MB name + ≈ 64 MB builder) and keeps
every distinct one with its command; polling frees queue slots, so under a steady slow load the queue refills behind the
drain and a single drain never ends (`TB12-1`: the drain thread in `popOperations` in 27 of 30 samples over 180 s). With
distinct values the drain's map grows by ≈ 48 MB per polled read: `TB4-1`'s dump holds 104 slow + 15 failed operations
(2.4× the count contract of 50 + 50), 53 names, 3.46 GB (89 % of a 4 GiB heap). At 2 GiB, 13 clients each sending one
16 MB value reach heap OOM 5/5 (3/5 attributed to the monitor by the frozen test), the identical-value control survives 3/3,
and disabling the monitor's queues survives 3/3 while doubling completed reads; the same load OOMs at 4 GiB (71 s) and
8 GiB (3/3, 29–127 s) and fills 12 GiB to 96 % within the 180 s budget. The workload stays within guardrails (values below the 16 MiB
frame and `max_value_size`, `ALLOW FILTERING` allowed by default, debug logging on by default). CASSANDRA-7392's review
raised exactly this retention ("the logger will still retain it … you want to truncate the larger values"); the shipped code
bounds the count only. Clue patterns: CP-2 (item count, not bytes), CP-3 (charge released while the monitor still holds
the value), CP-12 (a value rendered whole into a log string). Condition A (fallback F, B11's set-up plus the missing
monitor-off arm): with traced reads of an empty partition, the uncharged trace render (≈ 40 % of the dumps) makes every read
slower than 500 ms so the monitor fills with 50 kept values (≈ 45 %); each layer alone survives 3/3 at the same N and
heap, together they OOM 3/3 — a mixed result (bypass + count-only accumulation), which B11 could not separate.

**Limits of attribution.** (1) Two of the five `TB` OOMs (and every `TA`, `IR`, `IM-2`, `RT4` OOM) came in the first ≈ 25 s,
when 13 cold reads start together, pass the 5 s read deadline and each render the whole command into a
`QueryCancelledException` message that the debug log then queues and lays out again (Q, §3.4) — an unmapped, uncounted
holder of its own that also feeds the failed-op queue. Condition B's attributed OOMs are the later ones (t = 35–37 s at
2 GiB, 71 s at 4 GiB, 124–127 s at 8 GiB), after the start-up burst. (2) `IB` removes both the monitor's retention and
its rendering at once; no build that keeps the queue but drops the names (§2.8) was made. (3) ≥ 8 GiB readings have no
dump (by design); `TB8-3`'s OOM at 29 s came from one large allocation with 3.6 GB live after GC (humongous 147 regions),
the drain thread in `popOperations` and the async appender encoding 6 s before — not separately attributed.
(4) aarch64 only; do not pool with x86.

**Condition A — limits.** The mixed reading holds at k = 0, where the render itself makes the reads slow; there the
monitor cannot fill without the render, so `FIR` removes both layers and only `FIM` separates them (as the frozen F text
foresaw). At the designed `k_sel` = 2 the render was not the deciding layer (render arrays ≤ 16 % of every `TA` dump; the
render-bounded build failed 3/3): the start-up burst of deadline aborts (Q) decided those runs. A cleaner test of the mixed
claim with data-made slowness would warm the node and ramp the connections (e.g. 1 → 13 over 60 s), or pick k so reads stay
below the 5 s deadline at N, and require read errors ≈ 0 before the measured window. Q itself (a read aborted at the
deadline renders the full command into `QueryCancelledException`, then the debug log keeps and re-lays it out; bounded only by
concurrent reads × abort rate and the 1,024-event async queue) is a candidate of its own (CP-12, CP-5), not tested as a
claim here.

**Owner ruling (Jingsong, 2026-11-20, after the write-up):** amendment A-4 (TB-4 and TB-5 added under the n/5 rule to settle the B1 attribution count) stands; the verdict is unchanged. Holder Q is filed as candidate OC-578 (Agent `phase-2 (R12)`).
