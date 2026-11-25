# U16 — `QueryCancelledException`: a read aborted at its deadline renders every bound value whole into the exception message, which the debug log queues and lays out again  <!-- file: cassandra/cases/QueryCancelledException--timed-out-read-renders-bound-values/QueryCancelledException--timed-out-read-renders-bound-values.md -->

| Field | Value |
|---|---|
| Case ID | `U16` (U = unprotected-accumulation case; README "ID prefixes") |
| From | `OC-578` of the phase 1 OOM candidate list (Agent `phase-2 (R12)`: a holder found in R12's dumps, not tested as a claim there) |
| Phase-1 case file | none |
| System / pinned source | Cassandra 5.0.9 (`systems/cassandra/source/`, `build.xml` `base.version` 5.0.9); built tree `pc91:/mydata/s4/cassandra-base` (`build/apache-cassandra-5.0.9-SNAPSHOT.jar` 2026-11-17 21:05, sha256 `570b5249…ea90176e`), OpenJDK 11.0.33 **x86_64**, Ubuntu 22.04.2, kernel 5.15.0-203, logback 1.5.18 (`lib/logback-*-1.5.18.jar`) |
| Stage 1 (design) | OOM-agent stage-1 session (owner-approved batch of 2026-11-24), 2026-11-24 05:50 America/New_York |
| Stage 2 (verify) | fresh OOM-agent session (owner-approved batch of 2026-11-24), 2026-11-24 09:16–12:16 America/New_York (series), finished by a resumed session of the same task 15:01–15:15 (T31-2/3 excerpts, cleanup), node **pc72** (deviation from pc91, §3.2) |
| Verdict | **retry** (`candidate`: V1, V3–V7 met; V2 not met — frozen outcome row O4) |

## Summary

- **Conclusion: retry.** The test arm OOMs at shipped defaults at every budget tried — 4 GiB 3/3, 8 GiB 3/3, 15,872 MiB
  1/1, and 31,744 MiB 3/3 (the heap `cassandra-env.sh` picks on this node) — and the holder is the claimed one: in all six
  dumps (4 and 8 GiB) the abort renders and the exception messages own 56–78 % of the live large arrays, the OOM thread is
  in `QueryCancelledException.<init>`, and above 8 GiB the queued 32 MB debug-log events grow by ≈ 1.1–2.8 per second
  until the heap is gone. The intervention (message names only the table) survives 6/6 at the same,
  higher abort rate (≈ 6.4 aborts/s). But the **matched control failed**: the frozen control (slow reads under the
  deadline, k = 2) OOMs 3/3 at 4 GiB and 3/3 at 8 GiB, because under 16 MB-value load some of its reads also cross the
  5 s deadline and then render; even a faster control (amendment, k = 1) OOMs 1/5. That is frozen row O4 → **retry**: the
  next design needs a control that stays abort-free (or an owner ruling that the intervention arm serves as the match).
- **Status (detail):** `candidate` — V1, V3, V4, V5, V6, V7 met; V2 not met.
- **Claim under test (unprotected accumulation).** When a local read passes its 5 s deadline, `ReadCommand`'s cancellation
  checker throws `new QueryCancelledException(command)`, whose constructor renders the whole command with `toCQLString()` —
  every bound value in full, a 16 MB blob filter value as a ≈ 32 MB hex string, built through ≈ 6–10 × S of transient
  arrays on the ReadStage thread — and `StorageProxy` logs the exception at DEBUG (on by default), so logback's async
  appender keeps the ≈ 2S message per queued event (1,024 events, no byte bound) and lays it out again on its worker. No
  counter charges any of these bytes: the request's in-flight charge covers only its wire value, `concurrent_reads` (32)
  bounds only how many renders run at once, and the appender queue bounds only the event count.
- **Design in one line.** pc91 (x86_64, 32 hw threads), shipped `conf/`, 32 connections (= `concurrent_reads`) in a closed
  loop of `SELECT c FROM u16.t WHERE k = <k_sel> AND v = ? ALLOW FILTERING` with one identical 16,000,000-byte blob, on a
  partition wide enough that every read passes the 5 s deadline: each wave of 32 aborts renders 32 commands at once and
  queues 32 × 32 MB log events. Matched control: the same load on a partition whose reads finish slow but under the
  deadline (same in-flight values, same monitor fill, no abort). Intervention: a build whose `QueryCancelledException`
  message names only the table. Budget 4 GiB (2 GiB if the control fits), then 8 GiB, 15,872 MiB, 31,744 MiB.
- **Root cause as claimed at design time:** the read-abort path renders the full command (values uncut) into an exception
  message and hands it to an unbounded-in-bytes logging queue; nothing bounds bytes per abort or aborts in flight in the log.
- **Root cause as measured (stage 2):** confirmed in both parts. At 4 GiB the first waves of 32 concurrent renders
  (R_Q up to 27–31 threads at once, ≈ 6–10 × 16 MB each) end the heap; at 8 GiB and above the async debug appender's queue
  of whole 32 MB exception messages grows because its single worker writes ≈ 3.2–5.0 events/s against ≈ 6 aborts/s, and
  nothing bounds it in bytes (1,024 events ≈ 32 GB). What the case could not show is a no-abort control at the same load.

## 1. Candidate

**Candidate row (quoted from [`phase1-oom-candidates.md`](../../../../capacity-enforcement-exp/cassandra/stage5-oom-clue-find/phase1-oom-candidates.md), status as handed to this session):**

> | OC-578 | 2026-11-20 | none | phase-2 (R12) | [found in R12's dumps, not tested as a claim] A local read aborted at its deadline (`read_request_timeout` 5 s) builds `QueryCancelledException` with `"Query cancelled for taking too long: " + command.toCQLString()` (`QueryCancelledException.java:26`), rendering every bound value whole (a 16 MB blob filter value becomes a ≈ 32 MB hex string), and `StorageProxy.java:2223` passes it to `logger.debug(…, e)`, which is on by default, so the async appender holds and lays out the message again. Nothing counts these bytes: the in-flight limits charged only the wire request, and up to `concurrent_reads` 32 reads can time out together. In R12 at 2 GiB (ms0640) this holder owned 27–53 % of the start-up-burst OOM dumps and held the OOME thread in 10 of 15. | CP-12, CP-5 | picked: U16 (2026-11-24) |

**Phase-1 case file:** none (the holder came from a phase-2 run). **Phase-1 stage 4:** none.

**Where it was seen (R12, [`…slow-query-monitor-stacked`](../monitoring_max_operations+traced-render--slow-query-monitor-stacked/monitoring_max_operations+traced-render--slow-query-monitor-stacked.md) §3.4, §4 "Limits of attribution").**
`ms0640` (aarch64, 8 cores), 2 GiB, 13 connections, 16 MB filter values, partition k = 2 (300,000 rows). With 13 cold reads
arriving together, the first wave passed the 5 s deadline; every 2 GiB arm at k = 2 began with a burst of these renders:
`owners.py` Q 27–53 % in every OOM dump at t ≈ 20–31 s, the OOME thread in `QueryCancelledException.<init>` in 10 of 15
dumps (in `IM-2` logback laying one out), and U_h after GC max 110–120 of 128 regions in every 2 GiB arm at k = 2,
including the monitor-off arms (`IB` survived 3/3, `IM` 1/5 OOM). R12 did not claim Q: its runs mixed Q with the slow-query
monitor (M) and the trace render (R), the abort rate was not controlled (most aborts came in the first ≈ 10 s), and no
intervention removed Q alone. R12's write-up names Q "a candidate of its own (CP-12, CP-5)". This case isolates it: aborts
sustained by the data (every read passes the deadline), identical values so the monitor's drain merges to one name, and an
intervention that removes only the exception's render.

**JIRA prior art (read only; nothing posted; REST search 2026-11-24, `project = CASSANDRA AND …`, requests ≥ 2 s apart).**

| JQL (`project = CASSANDRA AND` …) | Hits | On point? |
|---|---|---|
| `text ~ "QueryCancelledException"` | 5 | no: CASSANDRA-18282 (RTBoundValidator exception, fixed 5.0.9), -21468 (TimeoutAbortTest failure, 6.0), -19177 (SAI query-timeout resource leaks, fixed 5.0-rc1: iterators, not the message), -21710 (shadowed exception on close, 6.0), -18715 (SAI vector) |
| `text ~ "\"Query cancelled for taking too long\""` | 2 | no: -21468, -21710 (tests / exception chaining) |
| `text ~ "\"Query cancelled\"" AND text ~ "OutOfMemoryError"` | 0 | — |
| `text ~ "\"Query cancelled\"" AND (text ~ "memory" OR "heap" OR "large")` | 1 | no: -21710 |
| `text ~ "toCQLString" AND (log OR exception) AND (large OR memory)` | 26 | none on the abort message; closest related: CASSANDRA-7392 (fixed 3.2, "Abort in-progress queries that time out", which added the abort path; its review discussed retaining queries for the logger and truncating large values, see R12 §1), CASSANDRA-16896 / -16850 (read-size and tombstone thresholds, off by default), CASSANDRA-21165 (read timeout, open, unrelated) |
| `text ~ "AsyncAppender" AND (memory OR OOM OR OutOfMemoryError)` | 6 | no: CASSANDRA-10241 (separate debug log, 2.2.2 / 3.0.0) is the origin of the DEBUG-on async debug log; -14096 (repair OOM), others unrelated |

Render prior art (from R12/B11): CASSANDRA-11719 (the 1000-char cut for traced values, applied after rendering) and
CASSANDRA-2849 / -14925 (render of an unbounded value to a string, fixed). **Verdict: `new`** — no report of the read-abort
exception rendering large bound values or of the debug log holding them; closest related CASSANDRA-7392 (design-review memory
concern about the monitor, not the exception) and CASSANDRA-10241 (the DEBUG-on async appender).

## 2. Design solution (stage 1; frozen)

### 2.1 Mechanism

Direction: **unprotected accumulation** (no control applies to the exception message, its render or the queued log events; the
only bounds are implicit: `concurrent_reads` × render size, and the appender's 1,024-event count × message size). Technique
notes: [`combo-playbook.md`](../../../combo-playbook.md) "Stage 1 — multiplicity" (32 concurrent renders at the default
`concurrent_reads`, each measured) and "Attribution and interventions" (one intervention that removes one holder);
[`default-convergence-playbook.md`](../../../default-convergence-playbook.md) "What defaults mean" for V6.

1. **Deadline and abort.** `StorageProxy.LocalReadRunnable.runMayThrow` (`StorageProxy.java:2178`, `:2205`) sets the command's
   monitoring clock to the request's start (`cql_start_time` REQUEST) with timeout `read_request_timeout` (5 s) and slow
   threshold `slow_query_log_timeout` (500 ms). `ReadCommand.executeLocally` applies `withQueryCancellation` before the row filter
   (`ReadCommand.java:456-472`), so every scanned row (not only matching rows) calls `maybeCancel` (`:766`, `:773`, at most once
   per 2 ms approx-clock tick, `:777-786`) → `isAborted` → `MonitorableImpl.check` (`MonitorableImpl.java:124-136`), which
   calls `abort()` once 5 s have passed: the command is offered to the monitor's failed-op queue (`MonitorableImpl.java:96-108`,
   `MonitoringTask.java:107`), and `maybeCancel` throws `new QueryCancelledException(ReadCommand.this)` (`ReadCommand.java:788-791`).
   A task that waited in the ReadStage queue past its deadline is dropped before it runs (`DroppableRunnable.run`,
   `StorageProxy.java:2596-2605`): it renders nothing and the client gets a ReadTimeout at the coordinator deadline.
2. **The render (Q_R).** `QueryCancelledException(ReadCommand command)` = `super("Query cancelled for taking too long: " +
   command.toCQLString())` (`QueryCancelledException.java:24-27`). `toCQLString` (`AbstractReadQuery.java:101-109`) →
   `RowFilter$SimpleExpression.toString` → `String.format("%s %s %s", …, type.toCQLString(value))` → `BytesType` →
   `"0x" + Hex.bytesToHex(value)` with no cut (R12 §2.1 item 3): per render a `char[2S]` (4S bytes), the hex `String` (2S),
   the concatenation (2S), the `String.format` copy (2S), the query `StringBuilder` (grows to ≈ 4S; R12/B11 dumps
   `byte[64,000,086]`), then the exception's own concatenation (2S): ≈ 6–10 × S live at the peak of one render, on the
   ReadStage thread, outside every counter. Up to `concurrent_reads` = 32 ReadStage threads can render at once, and reads that
   started together (a closed loop of N ≤ 32 connections) reach their deadline in the same 2 ms tick.
3. **The log event (Q_L).** `catch (QueryCancelledException e) { logger.debug("Query cancelled (timeout)", e); … }`
   (`StorageProxy.java:2221-2225`), then `handler.onFailure(…, UNKNOWN)` (`:2236`): the client gets a ReadFailure at once and its
   next request starts. `org.apache.cassandra` logs at DEBUG by default (`conf/logback.xml:132`) into `ASYNCDEBUGLOG`
   (`:67-72`: `AsyncAppender`, `queueSize` 1024, `discardingThreshold` 0 so nothing is discarded, the caller blocks only when
   1,024 events are queued; `includeCallerData` true). The `LoggingEvent` built on the ReadStage thread keeps a `ThrowableProxy`
   whose message is the exception's ≈ 2S + 37-byte Latin-1 string, so each queued event holds ≈ 2S (2 regions at S = 16 MB)
   until the single `AsyncAppender-Worker` has laid it out. The pattern has no `%ex`, so `PatternLayout` appends its default
   throwable converter, which writes the class name and the whole message again (a `StringBuilder` growing to ≈ 2–4S, its
   `String`, the encoder's `byte[]`), then writes ≈ 32 MB to `debug.log` (`DEBUGLOG`, `:50-63`: rolled at 50 MB, zip-compressed
   archives, 5 GB total cap). The queue's only bound is 1,024 events ≈ 1,024 × 2S ≈ 32 GB at S = 16 MB, above every budget
   tested here; whether it fills depends on the abort rate A against the worker's rate w.
4. **Why it is unprotected.** The request's in-flight charge (native transport, heap/10) covers its wire value S and is
   released when the failure response is flushed; the render happens while the request is in flight but is not charged, and
   the log event outlives the release. `concurrent_reads` and the appender queue are counts, not bytes. Classification by the
   protocol: **unprotected accumulation** (no applicable control; implicit bound concurrency × size, abort rate × logging
   lag), interpreted as a suspected implementation defect (an exception message built from user-supplied values with no cut;
   the trace path cuts at 1000 chars, CASSANDRA-11719, and the monitor was asked to "truncate the larger values in the
   query", CASSANDRA-7392 review).

### 2.2 Protection map

S = 16,000,000 B (one blob per request), G1 region 16 MiB (`conf/jvm11-server.options`; record `G1HeapRegionSize` from
`VM.flags`), so `byte[S]` = 1 region, a 2S `String` = 2 regions, `char[2S]` = 4 regions.

| # | Domain | Holder (allocation → release) | Counter (K) | Limit (C), shipped default | At the limit | Scope / multiplicity |
|---|---|---|---|---|---|---|
| F | Request in flight | Netty v4 frame (direct) + decoded value `byte[S]` (heap, `CBUtil.readBoundValue`) → released at response flush | channel / per-IP / global bytes (`RequestsSize`) | `native_transport_max_request_data_in_flight` heap/10, `_per_ip` heap/40; contract: one request per connection admitted even above the limit (R12 §2.2 row 1, `PreV5Handlers.java:85`, `:184`) | connection paused; the admitted request runs | N connections (one source IP each), one request each |
| Q_R | **Abort render** | `char[2S]`, hex / concat / format `String`s, query `StringBuilder` (≈ 4S), exception message (2S) on a ReadStage thread → transient except the message | none | none | — | ≤ `concurrent_reads` **32** ReadStage threads at once |
| Q_L | **Queued log event** | `LoggingEvent` → `ThrowableProxy` → message `String` (≈ 2S) in the `AsyncAppender` `ArrayBlockingQueue`; worker layout copies (≈ 4–6S transient) → released after the `debug.log` write | none in bytes (queue count, not exposed) | `queueSize` **1024** events (`logback.xml:68`), `discardingThreshold` 0 | the logging thread (ReadStage) blocks in `put` | one queue per process; one worker |
| M | Monitor (failed / slow queues, drain) | `FailedOperation`/`SlowOperation` → `ReadCommand` → value `byte[S]` (kept after release); drain renders each polled op's name (≈ 10 regions transient, one at a time) and, with identical values, merges to one ≈ 2S name per drain and one ≈ 2S log message | queue size, dropped count | `cassandra.monitoring_max_operations` **50** per queue (count) | offer refused, counted | one queue each per node; drain every 5 s (`monitoring_report_interval_ms` 5000) |
| X | Read scan | per-row iteration of the wide partition (small transients) | read deadline | `read_request_timeout` **5000 ms** | abort (→ Q_R, Q_L, M) | ≤ 32 |
| Y | Caches | key cache, chunk cache (off-heap) | weighers | key cache min(5 % heap, 100 MiB); `file_cache_size` min(¼ heap, 512 MiB) direct | evict | data ≈ 0.3 GB |
| H | Heap budget | JVM heap | — | `-Xmx` per §2.3 | `OutOfMemoryError: Java heap space` → shipped `-XX:OnOutOfMemoryError="kill -9 %p"`, `HeapDumpOnOutOfMemoryError` | — |
| D | Direct budget | Netty frames (≈ 2–2.5 × K, lead B9), chunk cache | Netty / JDK | `MaxDirectMemorySize` as `cassandra-env.sh` resolves (expected 15,872 MiB on pc91; record) | direct OOM (competing endpoint) | — |

Contract capacities claimed: F (heap/10 plus one request per connection), M (50 + 50 operations), Q_L (1,024 events). Q_R and
the bytes of Q_L have no capacity. Scope rule: Q is compared against no control (unprotected); F and M are measured so that
they can be subtracted, not claimed.

### 2.3 Configuration and budget audit

- **Builds.** Base: `pc91:/mydata/s4/cassandra-base` (checked read-only 2026-11-24 05:47 ET: not a git checkout; `build.xml`
  `base.version` 5.0.9; jar sha256 `570b5249d9b9a43f6809eb3da562737492192026f974b2edbd20e94bea90176e`; no `data/` or `logs/`).
  Stage 2 does **not** run in it: `cp -a /mydata/s4/cassandra-base /mydata/s4/u16/cassandra-base` and runs there. Intervention
  build: `cp -a` of that copy to `/mydata/s4/u16/cassandra-iv`, apply `harness/iv.patch` (below) with `patch -p1`, delete
  `build/classes/main/org/apache/cassandra/exceptions/QueryCancelledException.class`, `ant jar`; check
  `javap -c -classpath build/apache-cassandra-5.0.9-SNAPSHOT.jar org.apache.cassandra.exceptions.QueryCancelledException | grep -c toCQLString`
  = 1 in base and 0 in iv; record both jars' sha256 and `diff -ru` of the two `src/` trees (must equal `iv.patch`).

  `harness/iv.patch` (the intervention; saved verbatim in the case folder):
  ```diff
  --- a/src/java/org/apache/cassandra/exceptions/QueryCancelledException.java
  +++ b/src/java/org/apache/cassandra/exceptions/QueryCancelledException.java
  @@ -23,6 +23,6 @@ public class QueryCancelledException extends RuntimeException
   {
       public QueryCancelledException(ReadCommand command)
       {
  -        super("Query cancelled for taking too long: " + command.toCQLString());
  +        super("Query cancelled for taking too long: " + command.metadata().keyspace + '.' + command.metadata().name);
       }
   }
  ```
  It removes Q_R (no render) and shrinks Q_L to ≈ 100 B per event; it leaves the abort, the failure response, the log call,
  F and M (the monitor's drain still renders its operations' names) unchanged.
- **Configuration.** Shipped `conf/` unchanged in every arm (no `cassandra.yaml`, `logback.xml`, `jvm*.options` edit). Every
  constraint of §2.2 at its shipped default (V6): `concurrent_reads` 32, `read_request_timeout` 5000 ms, `slow_query_log_timeout`
  500 ms, `cql_start_time` REQUEST, `cassandra.monitoring_max_operations` 50, `cassandra.monitoring_report_interval_ms` 5000,
  `native_transport_max_request_data_in_flight` heap/10, `…_per_ip` heap/40, `native_transport_max_threads` 128,
  `native_transport_max_frame_size` 16 MiB, `native_transport_max_message_size` (shipped default; record the resolved value),
  `max_value_size` 256 MiB, `native_transport_max_concurrent_connections` −1 / `_per_ip` −1, `native_transport_timeout` 12 s,
  `memtable_heap_space` heap/4, key cache auto, `file_cache_size` auto, guardrails as shipped (`allow_filtering_enabled` true,
  read-size thresholds off), logback as shipped (DEBUG for `org.apache.cassandra`, `ASYNCDEBUGLOG` `queueSize` 1024,
  `discardingThreshold` 0, `DEBUGLOG` 50 MB / 5 GB). `batch_size_warn/fail_threshold` 5 / 50 KiB apply to the seed load only.
  **No constraint is changed in the test arm.** The control changes no setting (only the partition read). The intervention
  changes the build only.
- **Resolved at each heap** (`Runtime.maxMemory()` = `-Xmx`): 2 GiB → in-flight global 214,748,364 B / per IP 53,687,091 B,
  memtable 512 MiB; 4 GiB → 429,496,729 / 107,374,182; 8 GiB → 858,993,459 / 214,748,364; 15,872 MiB → 1,664,299,827 /
  416,074,956; 31,744 MiB → 3,328,599,654 / 832,149,913 (record the logged values). Key cache min(5 % heap, 100 MiB). Monitor
  50 + 50 operations and appender 1,024 events at every heap (not heap-derived).
- **Environment settings (not capacity):** `MAX_HEAP_SIZE` with `HEAP_NEWSIZE` unset (G1; `-Xms = -Xmx`),
  `CASSANDRA_HEAPDUMP_DIR=<run dir>`, `ulimit -n 100000` in the launching shell, `systemd-run --user --scope -p MemorySwapMax=0
  --unit=u16-<run>` (no `MemoryMax`: no container budget; `sudo loginctl enable-linger jason92` at start, `disable-linger` at
  the end; Linger was `no` on 2026-11-24). Heaps ≥ 15,872 MiB: `JVM_EXTRA_OPTS=-XX:-HeapDumpOnOutOfMemoryError` (a 16–31 GB
  dump is too slow to read back with the Python dump tools; recorded as an environment deviation of those readings; V5 there
  rests on the OOM line, GC log, thread samples and the backlog readings).
- **Node claimed (V7):** **`pc91`** (`node0.jason92-326665`, UMass, x86_64, 2 × Xeon E5-2667 v2 3.3 GHz, 32 hw threads,
  MemTotal 131,943,328 kB ≈ 125.8 GiB, 8 GiB swap partition present and unused (swappiness 60; the scope sets `MemorySwapMax=0`),
  cgroup v2, `/mydata` 753 G with 706 G free on a PERC H710P (rotational) volume, `vm.dirty_ratio` 20, open-files hard limit
  1,048,576, OpenJDK 11.0.33, Ant, Python 3.10.12; load 0.00, no Java process; `/mydata/s4/3b-C10`, `/mydata/s4/3b-S2` belong to
  other cases: do not touch; `/mydata/s4/NODE-LOCK/owner` read `phase1-hadoop o9 Mon Nov 23 11:12:13 PM MST 2026` — stage 2 checks
  with the coordinator that this lock is released or stale before starting; checked read-only 2026-11-24 05:47 ET).
  `cassandra-env.sh` would resolve heap **31,744 MiB** (½ RAM above the G1 cap 31,744) and `MaxDirectMemorySize` **15,872 MiB**
  here (record from an unset-`MAX_HEAP_SIZE` start's `VM.flags` in `CAL-r`). **Budgets:** heap H0 (4 GiB predicted, 2 GiB if the
  control fits; frozen rule §2.5), then 8 GiB, 15,872 MiB and 31,744 MiB (the node's own default) for the largest failing
  budget; all ≥ 512 MiB ⇒ V7 met by the standing rule; direct as resolved (with `MAX_HEAP_SIZE` set, `cassandra-env.sh` still
  sets `MaxDirectMemorySize` from the node: record it per run); no container limit. x86_64: R12's aarch64 numbers are priors,
  not controls.

### 2.4 Ceiling arithmetic (regions of 16 MiB: 2 GiB = 128, 4 GiB = 256, 8 GiB = 512, 15,872 MiB = 992, 31,744 MiB = 1,984)

N = 32 connections, identical values. Per-domain live peaks:

| Domain | Regions | Basis |
|---|---|---|
| Baseline (startup, schema, caches) | 15–25 | B11/R12 |
| F in flight | 32 | one `byte[S]` per connection while its request runs |
| M monitor | ≤ 50 kept values + one drain render ≈ 10 + merged name 2 + log message 2–4 ≈ **≤ 66** | count cap 50; identical values → one name per drain |
| Q_R abort renders | **6–10 per concurrent render × R_Q**, R_Q ≤ 32 | `concurrent_reads` 32; a wave of reads started together aborts in the same 2 ms tick |
| Q_L log events | **2 per queued event × E** + worker layout 4–8 | E ≤ 1,024 (count cap ≈ 2,048 regions = 32 GB) |

**Arms at 2 GiB / 4 GiB.**
- Control `C` (reads finish under the deadline; no Q): 20 + 32 + 66 ≈ **118** → 92 % of 2 GiB (fails or near; the frozen H0 rule
  then picks 4 GiB) and **46 % of 4 GiB** (margin 54 %).
- Intervention `I` (k_sel, iv build): the same ≈ 118 (+ < 1 region of short messages) → 46 % of 4 GiB.
- Test `T` (k_sel, base): 118 + Q_R + Q_L. The first wave (32 reads started together) aborts together: with R_Q ≥ 14 renders
  overlapping (140 regions), or E ≥ 70 events queued, 4 GiB is exceeded. Predicted OOM in the first or second wave.

**Budget search (T).** Q has two parts with different bounds:
- **Burst (Q_R + the wave's own events):** ≤ 32 × 10 + 32 × 2 = 384 regions (6 GiB). 8 GiB (512): 118 + 384 = 502 → OOM only
  if nearly every render overlaps (R_Q ≈ 30–32) — borderline. 15,872 MiB and above: the burst alone cannot reach it.
- **Backlog (Q_L):** steady abort rate A ≈ 32 / (5 s + render time) ≈ 6–6.4 /s (one wave per ≈ 5 s), each event ≈ 2S = 32 MB,
  so inflow ≈ 200 MB/s. If the worker's rate w (events/s: layout of a 32 M-char throwable, encode, write, roll) is below A, E
  grows at (A − w)/s with no byte bound: 15,872 MiB is reached at E ≈ (992 − 118 − 40)/2 ≈ 417 events, 31,744 MiB at
  E ≈ 913 (< 1,024, so the count cap does not stop it). With A − w = 2/s: ≈ 210 s and ≈ 460 s. If w ≥ A, no backlog grows and
  the boundary lies between 8 GiB and 15,872 MiB.
- Ceiling of the counted contracts: F heap/10 + 32 × S, M 100 × S ≈ 1.5 GiB, appender 1,024 events (bytes unbounded, ≈ 32 GB
  here). Σ counted ≈ 2 GiB at a 4 GiB heap leaves room; the excess must come from Q.

Direct memory: 32 Netty frames ≈ 1.2 GB at most ≪ 15,872 MiB. Disk: the worker writes up to ≈ 200 MB/s of near-constant hex;
`debug.log` rolls at 50 MB into zip archives (hex of the repeated pattern compresses ≫ 10×) capped at 5 GB, and the live
`debug.log` can exceed 50 MB between size checks; ≤ 600 s × 200 MB/s ≈ 120 GB written in the longest hold, against 706 G free
(disk guard below).

### 2.5 Workload and environment

- **Node:** `pc91` only (victim and client on the same node, as B11/R12; the client is a Python process using ≤ 2 cores).
  Work dir `/mydata/s4/u16/` (trees, `harness/`, `seed/`, `runs/<run-id>/`, `series.log`). Before anything: `pgrep -af java`
  shows no Cassandra/Hadoop process; ports 7000/7199/9042 free; do not touch `/mydata/s4/3b-*`, `/mydata/s4/cassandra-base`
  (read/copy only).
- **Schema:** `CREATE KEYSPACE u16 WITH replication = {'class':'SimpleStrategy','replication_factor':1};`
  `CREATE TABLE u16.t (k int, c int, v blob, PRIMARY KEY (k, c));`
- **Seed data (built once, restored before every run):** k = 0 empty; k = 1: 300,000 rows; k = 2: 1,000,000; k = 3: 3,000,000;
  k = 4: 10,000,000 (14.3 M rows); `v` = 8-byte big-endian `c` (never equal to a 16 MB value, so every read returns 0 rows).
  Load with `client.py --load` (R12's: prepared `INSERT`, unlogged single-partition batches of 150 rows ≤ 5 KiB, 8 connections;
  R12 loaded 1.4 M rows in 12 s), then `nodetool flush u16`, `nodetool compact u16`, `nodetool drain`, stop, and
  `tar -C <tree> -cf /mydata/s4/u16/seed/data.tar data` (record size and the table dir listing). Every run:
  `rm -rf <tree>/data <tree>/logs` then `tar -C <tree> -xf seed/data.tar` (both trees use the same tar).
- **Statement:** prepared once per connection, `SELECT c FROM u16.t WHERE k = <K> AND v = ? ALLOW FILTERING`, consistency ONE,
  one bound blob of S = 16,000,000 B, **identical** in every request (R12's default frame: `00 01 02 … ff` repeated), untraced
  (flags `0x00`). A legal read (single partition, filter on a regular column, value ≤ frame and `max_value_size`), returns 0
  rows, writes nothing.
- **Client:** R12's [`client.py`](../monitoring_max_operations+traced-render--slow-query-monitor-stacked/harness/client.py)
  (raw protocol v4, standard library), copied to `harness/`, one source IP per connection (`127.1.(i // 250).(1 + i % 250)`),
  STARTUP → PREPARE → closed loop of EXECUTE frames, `--fixed N --hold-s H` and `--ramp … --step-s`, `--single K --count n`.
  Required (add if missing): every completion line carries the result kind (`ok`, `0x1300` ReadFailure, `0x1200` ReadTimeout,
  other code) and latency; the per-second line carries `ok`, `rf` (ReadFailure), `rt` (ReadTimeout), `err` (other), open,
  established, outstanding.
- **Run driver** (`harness/run.sh <run-id> <base|iv> <heap> <K> <N> <hold-s>`, from R12's): preflight (no daemon; ports free;
  `/mydata` free ≥ heap + 60 GiB) → wipe and restore seed → start (`MAX_HEAP_SIZE`, `CASSANDRA_HEAPDUMP_DIR=<run dir>`,
  `JVM_EXTRA_OPTS` per §2.3, `systemd-run --user --scope -p MemorySwapMax=0`) → wait for `Starting listening for CQL clients`
  (≤ 300 s) → `VM.flags`, `VM.command_line` → monitors → client → endpoint = first of heap OOM, direct OOM, disk guard, hold end
  → stop (`kill`, `-9` after 60 s) → extract counts from `debug.log*` (§2.6, never whole lines) → **delete `debug.log*`** →
  copy `system.log`, `gc.log*`, stdout → `summarize.py`. Launch with `( setsid nohup … < /dev/null > /dev/null 2>&1 & )`,
  bounded polls, never a foreground `sleep`; kill by PID. After the run, `system.log` must show `Scheduling monitoring task
  with report interval of 5000 ms, max operations 50` (logged at the first slow/failed operation, R12 A-1); a different value
  makes the run invalid.
- **Series** (`harness/series.sh`): one run at a time, `STOP` file honoured, no new run after the stopping budget (§2.7).

**Calibration (`CAL`, not readings).**
- `CAL-r` (base, `MAX_HEAP_SIZE` unset, no client, 60 s): record the heap and `MaxDirectMemorySize` that `cassandra-env.sh`
  resolves on pc91 (expected 31,744 MiB / 15,872 MiB). If the heap differs, the top budget step is that value.
- `CAL-a` (base, 4 GiB): for k = 1, 2, 3, 4: `--single K --count 5` → latency of a read alone (k = 4 may abort: record).
- `CAL-b` (**iv build**, 4 GiB, so that Q cannot end the run): for k = 1, 2, 3, 4: N = 32, 60 s each, one start per k. Per k,
  over t = 10–60 s after full N: abort fraction f = rf / (ok + rf + rt), median latency of `ok`, ReadTimeout count.
  **Frozen rule:** **k_sel** = the smallest k with f ≥ 0.90; **k_c** = the largest k < k_sel with f ≤ 0.02 and median ok latency
  ≥ 600 ms (slow, so the monitor's slow queue fills as the failed queue does in T); if none has the latency, the largest k < k_sel
  with f ≤ 0.02. If no k reaches f ≥ 0.90, k_sel = the k with the largest f if f ≥ 0.50 (recorded as a weaker abort rate); if no k
  reaches 0.50, stop: the design cannot sustain aborts on this node (verdict `retry`: wider partition).
- `CAL-c` (base, **2 GiB**, k_c, N = 32, 150 s = one control run): **frozen H0 rule:** if it survives with U_h after GC max ≤ 100
  regions (78 %) and ≤ 3 Full GCs, **H0 = 2 GiB** and `CAL-c` counts as `C-1`; otherwise **H0 = 4 GiB**.

**Arms.** All S = 16,000,000 B, identical values, untraced, N = 32, shipped `conf/`, same seed and instruments.

| Run | Build | Heap | K | Hold | Purpose |
|---|---|---|---|---|---|
| `SEED` | base | 4 GiB | — | — | build `seed/data.tar` |
| `CAL-r`, `CAL-a`, `CAL-b`, `CAL-c` | base / iv | as above | 1–4 | as above | resolved budgets; `k_sel`, `k_c`; H0 |
| `T-1..3` | base | H0 | k_sel | ≤ 150 s | test (V1) |
| `C-1..3` | base | H0 | k_c | 150 s | matched control: same load, reads slow but under the deadline (V2) |
| `I-1..3` | **iv** | H0 | k_sel | 150 s | intervention: no render, short message (V4) |
| `T8-1` → `T16-1` → `T31-1` | base | 8 GiB → 15,872 MiB → 31,744 MiB | k_sel | ≤ 180 s (8 GiB), ≤ 600 s (≥ 15,872 MiB) | largest failing budget; stop at the first survivor |
| `RN` (only at the first surviving heap H_s) | base | H_s | k_sel | 90 s per step | N = 32 → 48 → 64 → 96: does queueing near the deadline raise the abort rate and the backlog? |
| repeats | as test | largest failing heap > H0 | k_sel / k_c | as above | `T<X>-2,3`, `C<X>-1..3`, `I<X>-1..3` if the stopping budget allows |

**Frozen rules.** If a fixed arm gives mixed outcomes (1/3 or 2/3), add two repeats (n/5). One rerun per invalid run (node failed
to start, client failed before full N, wrong monitor line, disk guard at H0). If `C` fails at H0 = 4 GiB, raise H0 once to 8 GiB
for `T`, `C`, `I` (record; the budget search then starts at 15,872 MiB). If `RN` fails at a step N\* with a Q-attributed OOM,
(N\*, H_s) becomes the largest-budget condition: `T` ×3, `C` ×3 (k_c at N\*), `I` ×3 there if the stopping budget allows.

### 2.6 Instruments

| What | How | Interval | Gives |
|---|---|---|---|
| Live humongous and heap (U, independent of K) | shipped `gc.log`: `Humongous regions: X->Y`, Eden/Old, `Pause Full`, causes; `jcmd <pid> GC.heap_info` (no forced GC) | every GC; 2 s | U_h after each GC, used/committed |
| Concurrent renders R_Q (U) | `jcmd <pid> Thread.print` → `threadcount.py` extended: ReadStage threads with `QueryCancelledException.<init>` / `toCQLString` / `Hex.bytesToHex` / `String.format` under it; ReadStage threads blocked in `AsyncAppenderBase.put` / `ArrayBlockingQueue.put` (queue full); `AsyncAppender-Worker-ASYNCDEBUGLOG` top frame (layout / encode / write / rollover); `ScheduledTasks` in `MonitoringTask` | 2 s | R_Q(t), queue-full blocking, worker phase, drain phase |
| Abort rate A (inflow) | client per-second `rf` (ReadFailure = aborted while running, rendered) vs `rt` (ReadTimeout = dropped before running, no render) vs `ok` | 1 s | A(t), dropped reads, completed reads |
| Worker rate w (outflow) | `/proc/<pid>/io` `wchar` and `write_bytes`; `stat` of `<tree>/logs/debug.log*` (size, count of archives) | 2 s | bytes written per second; w ≈ Δwchar / (2S + 4 KB) |
| Backlog E | E(t) ≈ Σ rf − (bytes written to `debug.log*` / (2S + 4 KB)); at the end, the written count = `grep -aoF 'StorageProxy.java:2223 - Query cancelled (timeout)'` over `debug.log` and `unzip -p` of the archives (or R12's `squash.py` first if slow), compared with Σ rf; in dumps the appender queue's `ArrayBlockingQueue.count` | 2 s; end; dump | E(t), events lost to the kill |
| Monitor (K, M) | `debug.log*` before deletion: R12's `drains.sh` patterns (`operations (were slow\|timed out) in the last … msecs`, `was slow N times`, `timed out N times`, `… (N were dropped)`), `system.log` `Some operations were slow/timed out`, the `Scheduling monitoring task … max operations` line | per drain | queue fill per drain (T: failed; C: slow), dropped |
| K (server in flight) | `nodetool sjk mx` `RequestsSize`, `PausedConnections`; `nodetool tpstats` READ dropped, ReadStage active/pending | 10 s | in-flight bytes vs C; dropped reads |
| Process / CPU | `RssAnon`, scope `memory.current`, `memory.events`; `top -b -H -n 1 -p <pid>` top 10 threads | 2 s; 10 s | native growth; worker / zip / ReadStage CPU |
| Disk guard | `df --output=avail /mydata` | 2 s | free < 60 GiB → `kill -9` the daemon, write `DISKGUARD` (endpoint "disk guard", not an OOM) |
| Endpoint | `stdout.txt` `java.lang.OutOfMemoryError: …` (`grep -F`), `Dumping heap`, `OnOutOfMemoryError`; `system.log` ERROR | end | endpoint type, time after full N |
| Holder at failure (V5) | shipped heap dump (≤ 8 GiB budgets; kept on pc91 under `/mydata/s4/u16/dumps/` until the case is written, then all but one representative deleted) → `hprof_oome_thread.py` (OOME thread and stack) and **`owners.py`** (R12's, extended, below) | every failing run ≤ 8 GiB | shares Q_R, Q_L, M, F, L, O of the live ≥ 1 MiB array bytes; counts of `QueryCancelledException`, queued `LoggingEvent`s, `FailedOperation`/`SlowOperation`, `byte[16,000,000]`, `byte[32,000,0xx]` |

`owners.py` extension (nearest-owner walk, ties in order Q_R, Q_L, M, L, F, O): **Q_R** = a frame of a ReadStage thread whose
stack contains `QueryCancelledException.<init>` (render transients and the message under construction); **Q_L** = a
`QueryCancelledException` instance, or a `ThrowableProxy` / `LoggingEvent` whose throwable is a `QueryCancelledException`, or the
`AsyncAppender-Worker` frame while the event it lays out carries one; **M** = `MonitoringTask$*` objects or a `ScheduledTasks`
frame under `MonitoringTask`, and a `LoggingEvent` whose message is a monitor drain message; **L** = other logback objects;
**F** = NTR / Netty / transport objects and ReadStage frames not under the render (commands in flight); **O** = other.
**Frozen V5 attribution test:** an OOM is **Q-attributed** iff Q_R + Q_L ≥ 40 % of the dump's live ≥ 1 MiB array bytes **and**
Q (= Q_R + Q_L) is the largest of {Q, M, F, L, O}; the OOME thread is reported beside it. Above 8 GiB (no dump) a run counts as
Q-attributed iff the last two `Thread.print` samples before the OOM show R_Q ≥ 8 or the worker in a `QueryCancelledException`
layout with E(t) ≥ 100, and U_h after GC rose with E(t) (state which).

Samplers identical in every arm; no forced GC or class histogram under load. `summarize.py` writes per run: endpoint, time to
endpoint after full N, ok / rf / rt counts and rates, median latency, max R_Q, max E, w, U_h median/max, Full GCs, max K, max
RssAnon, monitor drains (queued, dropped), `debug.log` bytes, dump shares.

### 2.7 Predicted response, outcome rows and stopping budget

**Predicted protective response:** none bounds the bytes. The in-flight limit admits each connection's request (one each); the
read deadline aborts every read at 5 s as designed; `concurrent_reads` lets 32 render at once; the appender queues every event
(count ≪ 1,024 before memory runs out); the monitor keeps ≤ 50 commands. Nothing rejects or defers.

**Predicted readings.** `CAL-a`: k = 1 ≈ 0.3–0.6 s, k = 2 ≈ 1–2 s, k = 3 ≈ 3–6 s, k = 4 ≈ 10–20 s alone (≈ 1–2 µs per row on
this CPU, R12's aarch64 2.2 µs). `CAL-b` at N = 32 (32 scans on 16 cores, ≈ 2× slower each): **k_sel = 3 or 4**, **k_c = 1 or 2**.
`CAL-c`: U_h max ≈ 110–125 of 128 → **H0 = 4 GiB**.
- `T` at 4 GiB: heap OOM **3/3** within the first two waves (t ≈ 5–15 s after full N); R_Q ≥ 16 in the sample nearest the
  failure; OOME thread a ReadStage thread in `QueryCancelledException.<init>` (or the appender worker); dumps **Q 50–75 %**
  (Q_R ≥ Q_L in the first wave), M 15–25 %, F 8–15 %.
- `C` at 4 GiB: **0/3**, slow queue full in every drain (dropped > 0), rf ≤ 2 %, U_h after GC max ≤ 140 regions (55 %), ≤ 3 Full
  GCs.
- `I` at 4 GiB: **0/3**, rf ≥ 90 % (abort rate ≥ T's), failed queue full in every drain, U_h after GC max ≤ 140, `debug.log`
  bytes per abort ≈ 3–5 KB (stack trace only).
- `T8-1`: OOM likely (burst ≈ 502 of 512 if renders overlap fully, or the backlog). `T16-1`: OOM iff w < A (E rising);
  `T31-1`: OOM iff A − w ≳ 2/s over the 600 s hold. Predicted largest failing budget: **8 GiB**, or 15,872–31,744 MiB if the
  worker lags (w < 6 events/s).

**Outcome rows (frozen).**

| Row | Readings | Status / verdict path |
|---|---|---|
| O1 | `T` Q-attributed heap OOM ≥ 3/3 (or n/5 ≥ 3 after the rule), `C` 0/3, `I` 0/3 at H0 | `verified-OOM · deployment` (unprotected accumulation), V1–V7 → **true positive**; report the largest failing budget with n/N |
| O2 | `T` OOM 3/3 but not Q-attributed (M or F the largest) | the holder is not Q → **retry** (re-map) |
| O3 | `I` OOM ≥ 1/3 at matched abort rate | Q is not the deciding holder → **retry** |
| O4 | `C` OOM at H0 after the one raise of H0 | control invalid → **retry** (smaller N or S for the control) |
| O5 | `T` 0/3 at H0 with rf ≥ 90 % and R_Q, E measured | negative within the range; **false positive** only if `RN` and the budget steps were run and the ceiling arithmetic of §2.4 with the measured R_Q, w and A cannot reach 4 GiB; otherwise **retry** |
| O6 | k_sel cannot be found (`CAL-b` f < 0.50 for every k) | invalid design → **retry** (wider partition) |

Service-loss criterion: the protocol default (≥ 90 % STW over ≥ 60 s), recorded but not the endpoint claimed.

**Stopping budget.** Per run: hold ≤ 150 s at full N at ≤ 4 GiB, ≤ 180 s at 8 GiB, ≤ 600 s at ≥ 15,872 MiB; start ≤ 300 s; the
first OOM ends a run (no escalation after an OOM beyond the planned steps). Series: ≤ 40 runs including calibration and reruns,
and **no new run starts more than 7 h after `SEED` begins**. Order if short of time: `SEED` → `CAL` → `T` ×3 → `C` ×3 → `I` ×3 →
`T8-1` → `T16-1` → `T31-1` → `RN` → repeats. At the end: no Cassandra or client process left, linger disabled, `debug.log*`
deleted, trees + seed + kept dumps listed with sizes.

### 2.8 Controls and intervention (summary)

- **Matched control `C` (V2, ×3 at H0):** same build, heap, N, S, identical values, client, seed and instruments; only the
  partition differs (k_c, reads finish slow under the 5 s deadline), so F (32 values in flight) and M (≤ 50 kept commands, one
  merged name per drain, the drain renders) are matched and Q is absent. It shows that the load without aborts survives.
- **Intervention `I` (V4, ×3 at H0):** the iv build (`harness/iv.patch`, one line) at k_sel: aborts, failure responses, log
  calls, F and M unchanged; no render and a ≈ 100-byte message. It shows that removing the uncut render removes the OOM at the
  same abort rate (record A, ok/rf/rt and latency so that a slower or faster abort rate is visible).
- **Original failure on the unmodified build:** `T` runs on base; iv runs only in `I` and `CAL-b`.

`sha256 of §1–§2 at freeze: 27fbd095cef25e099a6cb6c238ca4edd78f75130ad6ffea3916c70f4a7a4d24f` (computed as `awk '/^## 1\. Candidate/{p=1} /^`sha256 of §1–§2 at freeze/{p=0} p' <this file> | sha256sum`, i.e. from the `## 1. Candidate` line up to, not including, this line; 2026-11-24) · amendments after the freeze: none at stage 1; stage 2 recorded A-1 to A-3 and the node deviation in §3.2 (2026-11-24; this suffix is outside the hashed range, which stage 2 re-checked: `27fbd095…a4d24f`, match).

## 3. Runs (stage 2)

Stage 2 by a fresh OOM-agent session, 2026-11-24 09:16–12:16 America/New_York (the last run, T31-3, ended 12:16 ET; node
clock MST = ET − 2 h; debug.log timestamps UTC); that session ended before its cleanup, and a resumed session of the same
task ("try again", no new runs) copied the T31-2/3 excerpts and did the cleanup 15:01–15:15 ET. Freeze hash re-checked before
anything ran: `27fbd095…a4d24f`, match (re-checked again 15:03 ET, match). Node lock `pc72:/mydata/s4/NODE-LOCK` held for the
whole series; it was found absent (no process running) at 15:01 ET and re-acquired for the cleanup, then released. Harness: [`harness/`](harness/) (from R12's; changes listed in §3.2);
small excerpts: [`logs/`](logs/) (`logs/runs/<run>/summary.txt`, `driver.txt`, `debugcounts.txt`, `drains.txt`;
`logs/dumps/<run>.owners.txt`, `.oome.txt`, `oome-thread-frames.txt`; `logs/series.log`, `logs/calib.txt` with the dated
decisions). Raw run directories stayed on pc72 under `/mydata/s4/u16/runs/` until cleanup (§3.8).

### 3.1 Environment

- **Node `pc72`** (`node2.jason92-326665`, UMass): x86_64, 2 × Intel Xeon E5-2660 v2 2.2 GHz, 40 hw threads, MemTotal
  131,943,324 kB, 8 GiB swap present (swappiness 60; every daemon in a `systemd-run --user --scope -p MemorySwapMax=0`),
  cgroup v2, kernel 5.15.0-203, OpenJDK 11.0.33, Python 3.10.12, logback 1.5.18, `/mydata` 753 G with 707 G free at start.
  Load 0.00, no Java process, ports free at start; `/mydata/s4/3b-B21`, `/mydata/s4/3b-R22` (other cases) untouched.
- **Builds.** `/mydata/s4/u16/cassandra-base` = `cp -a /mydata/s4/cassandra-base` (jar sha256 `570b5249…ea90176e`, same as
  pc91's in §2.3). `/mydata/s4/u16/cassandra-iv` = copy + [`harness/iv.patch`](harness/iv.patch) + `ant jar` (BUILD
  SUCCESSFUL; jar sha256 `8415bc0d780294586c4c7f5c6e58b68a9bddea08ef7b0a951795829ce73a969b`); `javap … | grep -c toCQLString`
  = **1** base, **0** iv; `diff -ru` of the two `src/` trees = the patch plus the build-generated `version.properties`
  timestamp ([`logs/build.log`](logs/build.log)).
- **Resolved budgets (`CAL-r`, base, `MAX_HEAP_SIZE` unset):** heap **31,744 MiB** (`MaxHeapSize` 33,285,996,544),
  `MaxDirectMemorySize` **15,872 MiB** (16,642,998,272), `G1HeapRegionSize` 16 MiB — as predicted. With a hand-set heap
  `cassandra-env.sh` kept the direct limit at 15,872 MiB in every run (`vm-flags.txt`).
- **Configuration:** shipped `conf/` in every arm; `VM.command_line` of every run has no `-Dcassandra.monitoring*` or other
  capacity override; the first slow/failed operation logged `Scheduling monitoring task with report interval of 5000 ms, max
  operations 50` (in the rolled `system.log` archive for the ≥ 15,872 MiB runs, where the monitor's INFO line carries a
  32 MB name and rolls `system.log`; the line is not in the copied plain file there, `montask.txt` empty, no override on the
  command line). Resolved in-flight limits as §2.3 (`RequestsSize` peaked at 512,000,864 B = 32 × 16 MB in every N = 32 arm:
  one request per connection admitted above heap/10 at 4 GiB, paused connections up to 31–32).
- **Seed (`SEED`, 4 GiB):** `client.py --load --conns 16` wrote **14,299,100 of 14,300,000 rows** in 58 s (6 batches of 150
  ended in write timeouts and were not retried; < 0.01 %, recorded), flush, compact → one sstable (125 MiB `Data.db`,
  4 partitions), drain; `seed/data.tar` 165,406,720 B, restored before every run.

### 3.2 Deviations and amendments (dated 2026-11-24, each before the readings it affects)

| # | When | What | Why / effect |
|---|---|---|---|
| D-1 | start | Node **pc72** instead of pc91 | assigned by the batch; same class (x86_64, same base jar); 40 instead of 32 hw threads (`concurrent_reads` 32 unchanged) |
| D-2 | start | No `sudo loginctl enable-linger` (the session's permission check refused it); an ssh session to pc72 was held open for the whole series instead | keeps the user manager (and the `--user` scopes) alive; no run lost a scope |
| D-3 | build | `iv.patch` regenerated with `diff -u` from the pinned file | same one-line change; the frozen text applied only with fuzz 2 because the file has no trailing newline |
| A-1 | after `CAL-a`, before `CAL-b` | **Abort count from the server, not the client:** an aborted read reaches the client as **ReadTimeout `0x1200`**, not ReadFailure — the coordinator's wait expires at the same 5 s deadline as the local abort (`CAL-a` k = 4: 5/5 `rt`, 5/5 `StorageProxy.java:2223` events logged). f = server-logged aborts / completions (`qc-events.txt` timestamps), and E(t) inflow = `rf` + `rt` (with ReadStage pending 0 at N = 32, `rt` = aborts) | frozen rule's `rf` would read 0.03–0.15 for k = 4; the rule's intent (aborted fraction) is kept |
| D-4 | after `CAL-b4` | Debug-log extraction also reads `debug.log.*.tmp` (a roll cut short by the stop) and skips incomplete zips | `CAL-b4`'s server count was lost (k = 4 decided from the client: 375/375 `rt`/`rf`, no queueing) |
| D-5 | after `T-3` | `threadcount.py` counts renders on **Native-Transport-Requests threads too** (a local read can run inline on the NTR thread, `Stage.maybeExecuteImmediately`; seen in T-3's dump) | R_Q of `T-1..3`, `C-1` counted ReadStage threads only (a lower bound) |
| A-2 | after `C-2`, before its readings | Extra control **C1: k = 1** (CAL-b1: f = 0, ok median 1,125 ms ≥ 600 ms — the next k meeting the frozen k_c criteria, 4.4× under the deadline) ×3 at H0, mixed-outcome rule applies | the frozen control (k = 2) crossed the deadline under load (below) |
| A-3 | after `C8-3`, before its readings | **Supplementary** control at the frozen O4 remedy: base, 8 GiB, k = 2, **N = 8**, 150 s ×3 (`CN8`) — declared before readings **not to change the frozen outcome mapping** | evidence for the retry design |
| D-6 | series | No new run after 13:15 ET (stage-2 wall-clock cap), tighter than the design's 7 h | — |

### 3.3 Calibration

| Run | Build, heap | Readings | Decision |
|---|---|---|---|
| `CAL-r` | base, auto, idle 60 s | heap 31,744 MiB, direct 15,872 MiB | top budget step 31,744 MiB |
| `CAL-a` | base, 4 GiB, 1 connection × 5 | median latency k = 1 **356 ms**, k = 2 **1,060 ms**, k = 3 **2,748 ms**, k = 4 **5,034 ms = abort** (5/5 `rt`, 5 events logged, message `… v = 0x<32,000,000 hex> ALLOW FILTERING`) | — |
| `CAL-b1..4` | **iv**, 4 GiB, N = 32, 60 s | t = 10–60 s: k = 1 f = 0 (1,372 ok, median 1,125 ms); k = 2 f = 0 (429 ok, median 3,588 ms); k = 3 **f = 0.875** (281 of 321; 0.901 over the run); k = 4 **f = 1.0** (320 of 320 `rt`/`rf`; ReadStage pending 0) | **k_sel = 4** (smallest k with f ≥ 0.90), **k_c = 2** (largest k < k_sel with f ≤ 0.02 and median ≥ 600 ms) |
| `CAL-c` | base, **2 GiB**, k_c, N = 32, 150 s | heap OOM at 16.8 s (dump: M 54 %, F 35 %, Q 8.5 % — the control load alone does not fit 2 GiB) | **H0 = 4 GiB** |

### 3.4 Runs (all base unless marked iv; N = 32 unless marked; S = 16,000,000 B identical; shipped `conf/`)

Columns: endpoint; time after full N (OOM) or hold length; client completions ok / `rt` / `rf` (plus 32 `io_error` when the
daemon died); server-logged aborts (`StorageProxy.java:2223` events written to `debug.log*`; events still queued at a kill are
lost); median ok latency (ms); max R_Q (concurrent renders in one 2 s sample); humongous regions after GC median / max; Pause
Full count; owners.py on the dump (Q = QR + QL share of live ≥ 1 MiB arrays, frozen V5 test, next-largest owner).

| Run | Arm (k, heap) | Endpoint | Time | ok / rt / rf | Aborts logged | ok median | max R_Q | U_h med/max | Full GC | Dump (V5) |
|---|---|---|---|---|---|---|---|---|---|---|
| T-1 | T (4, 4 GiB) | **heap OOM** | 18.8 s | 0 / 45 / 18 | 20 | — | 9 | 163/249 | 7 | Q 56.5 %, YES; M next |
| T-2 | T (4, 4 GiB) | **heap OOM** | 27.8 s | 0 / 45 / 19 | 13 | — | 27 | 141/242 | 5 | Q 77.4 %, YES |
| T-3 | T (4, 4 GiB) | **heap OOM** | 27.4 s | 0 / 33 / 26 | 19 | — | 27 | 142/246 | 5 | Q 77.6 %, YES |
| C-1 | C (2, 4 GiB) | **heap OOM** | 28.8 s | 0 / 75 / 9 | 6 | — | 22 | 204/245 | 16 | Q 73.3 %, YES |
| C-2 | C (2, 4 GiB) | **heap OOM** | 25.2 s | 66 / 39 / 0 | 0 (lost) | 2,422 | 31 | 219/247 | 24 | Q 55.7 %, YES |
| C-3 | C (2, 4 GiB) | **heap OOM** | 22.7 s | 32 / 70 / 1 | 4 | 3,280 | 30 | 208/242 | 17 | Q 55.1 %, YES |
| I-1 | I **iv** (4, 4 GiB) | survived | hold 150 s | 0 / 539 / 95 | 666 | — | 0 | 111/164 | 0 | — |
| I-2 | I **iv** (4, 4 GiB) | survived | hold 148 s | 0 / 856 / 72 | 960 | — | 0 | 93/166 | 0 | — |
| I-3 | I **iv** (4, 4 GiB) | survived | hold 147 s | 0 / 854 / 74 | 960 | — | 0 | 115/168 | 0 | — |
| T8-1 | T (4, **8 GiB**) | **heap OOM** | 61.9 s | 0 / 243 / 32 | 180 | — | 21 | 242/477 | 0 | Q 77.4 %, YES |
| T8-2 | T (4, 8 GiB) | **heap OOM** | 49.8 s | 0 / 160 / 14 | 68 | — | 27 | 322/483 | 2 | Q 75.2 %, YES |
| T8-3 | T (4, 8 GiB) | **heap OOM** | 48.9 s | 0 / 125 / 29 | 60 | — | 28 | 226/499 | 1 | Q 75.6 %, YES |
| C8-1 | C (2, 8 GiB) | **heap OOM** | 44.0 s | 68 / 59 / 0 | 15 | 3,972 | 22 | 186/497 | 0 | Q 54.9 %, YES |
| C8-2 | C (2, 8 GiB) | **heap OOM** | 113.0 s | 413 / 151 / 1 | 98 | 2,245 | 4 | 251/478 | 4 | Q 50.3 %, YES |
| C8-3 | C (2, 8 GiB) | **heap OOM** | 123.4 s | 904 / 123 / 0 | 97 | 2,240 | 6 | 222/440 | 1 | not analysed |
| C1x8-1 | C1 A-2 (1, 8 GiB) | **heap OOM** | 100.1 s | 2,209 / 90 / 2 | 47 | 579 | 4 | 212/485 | 0 | Q 40.8 %, NO (M 44.3 %) |
| C1x8-2 | C1 A-2 (1, 8 GiB) | survived | hold 151 s | 3,339 / 101 / 2 | 93 | 728 | 0 | 223/435 | 1 | — |
| C1x8-3 | C1 A-2 (1, 8 GiB) | survived | hold 151 s | 4,106 / 0 / 0 | 0 | 1,083 | 0 | 90/103 | 0 | — |
| C1x8-4 | C1 A-2 (1, 8 GiB) | survived | hold 151 s | 5,335 / 0 / 0 | 0 | 698 | 0 | 91/101 | 0 | — |
| C1x8-5 | C1 A-2 (1, 8 GiB) | survived | hold 151 s | 4,346 / 0 / 0 | 0 | 1,204 | 0 | 91/103 | 0 | — |
| I8-1 | I **iv** (4, 8 GiB) | survived | hold 147 s | 0 / 838 / 90 | 960 | — | 0 | 202/342 | 0 | — |
| I8-2 | I **iv** (4, 8 GiB) | survived | hold 147 s | 0 / 845 / 83 | 960 | — | 0 | 191/328 | 0 | — |
| I8-3 | I **iv** (4, 8 GiB) | survived | hold 148 s | 0 / 862 / 66 | 960 | — | 0 | 196/330 | 0 | — |
| T16-1 | T (4, **15,872 MiB**) | **heap OOM** | 182.5 s | 0 / 1,079 / 31 | 832 | — | 10 | 667/979 | 0 | no dump (design); backlog rule YES |
| T31-1 | T (4, **31,744 MiB**) | **heap OOM** | 242.8 s | 0 / 1,431 / 34 | 747 | — | 13 | 1,663/1,893 | 0 | no dump (design); backlog rule YES |
| T31-2 | T (4, 31,744 MiB) | **heap OOM** | 442.8 s | 0 / 2,716 / 23 | 2,137 | — | 13 | 1,644/1,863 | 0 | no dump (design); backlog rule YES (R_Q 9, worker in QCE layout, E 506) |
| T31-3 | T (4, 31,744 MiB) | **heap OOM** | 423.7 s | 0 / 2,593 / 30 | 1,998 | — | 15 | 1,661/1,889 | 0 | no dump (design); backlog rule YES (R_Q 13, E 565) |
| CN8-1 | A-3 (2, 8 GiB, **N = 8**) | survived | hold 151 s | 662 / 0 / 0 | 0 | 1,415 | 0 | 51/59 | 0 | — |
| CN8-2 | A-3 (2, 8 GiB, N = 8) | survived | hold 151 s | 1,171 / 0 / 0 | 0 | 1,004 | 0 | 155/257 | 0 | — |
| CN8-3 | A-3 (2, 8 GiB, N = 8) | survived | hold 151 s | 1,123 / 0 / 0 | 0 | 1,042 | 0 | 163/267 | 0 | — |

Every OOM is `java.lang.OutOfMemoryError: Java heap space` followed by the shipped `kill -9`; no direct-memory OOM, no
cgroup event (no container limit), no disk guard (`/mydata` ≥ 626 GiB free throughout). Monitor drains in the CN8 / C1 runs
that survived: slow queue full in every drain with drops (max queued 398–750), so M was loaded in the controls as designed.

### 3.5 Attribution (V5)

- **OOM thread.** In all 9 dumps checked with 40 frames (T-1..3, T8-1..3, C-1, C8-1, C1x8-1) the OOM-initiating thread is a
  read worker (`SEPWorker` → `StorageProxy$LocalReadRunnable.runMayThrow:2211` → `ReadCommand$QueryCancellationChecker.maybeCancel`)
  inside **`QueryCancelledException.<init>` (`QueryCancelledException.java:26`)**, in `Hex.bytesToHex`, `String.format`
  (`RowFilter$SimpleExpression.toString`) or the `StringBuilder` of `AbstractReadQuery.toCQLString`
  ([`logs/dumps/oome-thread-frames.txt`](logs/dumps/oome-thread-frames.txt)). (CAL-c's 2 GiB control OOM'd in the appender
  worker's `ThrowableProxyConverter`.)
- **Holders, T at 4 GiB** (owners.py, share of live ≥ 1 MiB arrays): Q 56.5 / 77.4 / 77.6 % (QR 23–49 % = renders in progress:
  `char[32,000,000]`, hex `String`s, values; QL 28–33 % = 40–62 live `QueryCancelledException`s, 27–30 of them in queued
  `LoggingEvent`s); M 16–21 % (45–52 `FailedOperation`s); F 3–19 %. **At 8 GiB:** Q 75–77 %, now mostly **QL**
  (50–74 %: 71–135 queued `LoggingEvent`s carrying a QCE, 2.3–4.1 GiB of 32 MB messages); M 13–16 %, F 8–11 %.
- **Above 8 GiB (no dump, frozen rule):** T16-1 and T31-1..3 all meet it — in the last two thread samples before the OOM
  R_Q ≥ 8 (T31-1 10, T31-2 9, T31-3 13) or the appender worker is laying out a `QueryCancelledException`
  (`ThrowableProxyConverter`; T16-1, T31-1, T31-2), with E(t) = 248, 675, 506, 565 (≥ 100), and humongous-after-GC rose with E(t) (T16-1 median 667 of 992 regions; T31-1 median 1,663 of 1,984)
  ([`logs/runs/large-heap-last-thread-samples.txt`](logs/runs/large-heap-last-thread-samples.txt)).
- **Backlog numbers (Q_L).** Inflow A ≈ 6.0–6.1 aborts/s (32 per ≈ 5.3 s wave; I arms 960 per 150 s = 6.4/s). Worker output
  from `wchar`: T16-1 846 events in 183 s (**4.6/s**), T31-1 779 in 243 s (**3.2/s**), T31-2 2,220 in 443 s (**5.0/s**),
  T31-3 2,040 in 424 s (**4.8/s**), never above 6.1/s in any 10 s; so E grew by ≈ 1.1–2.8/s to 248 (T16-1) and 506–675 events
  (≈ 16–21 GB; T31-1..3) until the heap ran out — the design's
  "w < A" branch; the 1,024-event count cap was never reached. `debug.log*` written per run up to ≈ 26 GB (412 rolled
  zips at 15,872 MiB).

### 3.6 Controls (V2) — what happened

The frozen control at k_c = 2 is not abort-free under this load: its reads take 2.2–4.0 s (median) with 32 concurrent scans,
and a GC- or drain-induced slowdown pushes a wave past 5 s; the first aborts render (R_Q 22–31 in one sample), which slows
and fills the heap further, and the control dies the same way as the test — **6/6 OOM (4 GiB 3/3, 8 GiB 3/3), 5 of 5
analysed control dumps Q-attributed (Q 50–73 %)**. The A-2 control at k = 1 (median 0.6–1.2 s) is 4/5 at 8 GiB: its two
first runs had waves of aborts (90 and 101 `rt`), one of which OOM'd with a full wave of 32 renders live (QR 40.0 %, M 44.3 %);
runs 3–5 had no abort at all. The A-3 supplementary control (k = 2, N = 8) had no abort and survived 3/3 with the slow queue
full in every drain. The CAL-b/I runs show the same load is harmless without the render: the iv build survives 6/6 with
**every** read aborted (≈ 6.4/s), more aborts than any T run reached.

### 3.7 Budget search

T fails at every budget tried: 4 GiB 3/3, 8 GiB 3/3, 15,872 MiB 1/1, **31,744 MiB 3/3** — the node's own default heap
(`cassandra-env.sh`). No budget step survived, so `RN` (run only at the first surviving heap) did not apply. Time to OOM grows
with the heap (≈ 19–28 s, 49–62 s, 183 s, 243–443 s) as the backlog has more room to grow.

### 3.8 Cleanup

Cleanup 2026-11-24 15:01–15:15 ET (resumed session, lock re-acquired): no Java, client, sampler or driver process of the
user on pc72 (`pgrep`), no `u16-*` user scope, ports 7000/7199/9042 free; linger was never enabled (D-2) and reads `no`.
Deleted on pc72: the two run trees `/mydata/s4/u16/cassandra-base` (copy) and `cassandra-iv` (with their `data/`, `logs/`;
the iv jar's sha256 is in §3.1 and the patch in `harness/`), `seed/` (`data.tar`), and every `debug.log*` (by the driver,
after counting). Compressed (`gzip -1`) every run file > 1 MiB (`stdout.txt`, `system.log`, `gc.log*`, `completions.txt`).
**Left on pc72:** `/mydata/s4/u16/` 272 MB — `runs/` (200 MB, per-run logs), `harness/`, `series.log`, `calib.txt`,
`build.log`, and one representative heap dump `dumps/T-2.hprof.gz` (3.9 GB → 73 MB; T at 4 GiB, Q 77.4 %; the other dumps
were read and deleted during the series, §2.6). `/mydata/s4/cassandra-base` (read only), `/mydata/s4/3b-B21`, `3b-R22`
(other cases) untouched. `/mydata` 707 G free. Node lock released 15:15 ET.

## 4. Conclusion (stage 2)

**Verdict: retry** (protocol status `candidate`: V1, V3–V7 met, **V2 not met**; frozen outcome row **O4**).

**Reason.** The mechanism is shown at shipped defaults and deployment budgets: with 32 connections reading a partition that
passes the 5 s deadline, each abort renders the whole 16 MB bound value as a 32 MB hex string on the read thread and hands it
to the async debug appender, and the heap runs out at 4 GiB (3/3, renders in progress dominate), 8 GiB (3/3, queued 32 MB log
events dominate), 15,872 MiB (1/1) and the node's default 31,744 MiB (3/3; the appender's single worker writes ≈ 3.2–5.0 events/s
against ≈ 6 aborts/s; nothing bounds the queue in bytes). The one-line intervention (message without the command) removes
it: 6/6 survive with every read aborted. But the frozen matched control — the same load with reads that finish slow but under
the deadline — is not achievable at N = 32 with 16 MB values: its reads also cross the deadline under the load and then OOM by
the same holder (6/6, H0 raised once per the frozen rule). Row O4 maps this to retry. The amendment control at k = 1 OOM'd
1/5 (abort waves in 2/5); only the supplementary O4-remedy control (N = 8) stayed abort-free (0/3), and by its pre-reading
declaration it does not change the frozen mapping.

**V1–V7.**

| | Requirement | Evidence | Met? |
|---|---|---|---|
| V1 | ≥ 3 runs reach the endpoint | T 3/3 at 4 GiB (T-1..3), 3/3 at 8 GiB (T8-1..3); also 15,872 MiB 1/1, 31,744 MiB 3/3 | yes |
| V2 | matched control ≥ 3 runs, no endpoint | frozen C (k = 2): 3/3 OOM at 4 GiB, 3/3 at 8 GiB (after the one raise); A-2 C1 (k = 1): 1/5 OOM; A-3 CN8 (N = 8): 0/3 (supplementary) | **no** |
| V3 | U measured independently of K | heap dumps (owners.py), `Thread.print` R_Q, appender backlog from `wchar` vs inflow, GC log humongous; K = `RequestsSize` (512 MB = 32 values), monitor queue counts | yes |
| V4 | intervention removes the endpoint ≥ 3 runs | iv build 0/3 at 4 GiB and 0/3 at 8 GiB, 960 aborts per 150 s (≥ T's abort rate) | yes |
| V5 | initiating failure + holder | OOM thread in `QueryCancelledException.<init>` in 6/6 T dumps; Q 56–78 % of live large arrays (6/6 YES); above 8 GiB the frozen thread/backlog rule (2/2) | yes |
| V6 | default constraints | shipped `conf/`, no override on any command line; `concurrent_reads` 32, `read_request_timeout` 5 s, appender 1,024 / threshold 0, monitor 50 | yes |
| V7 | acceptable budget | 4 GiB and 8 GiB (≥ 512 MiB), up to the node's automatic 31,744 MiB; direct 15,872 MiB as resolved; no container limit | yes |

**Interpretation (if V2 is settled):** unprotected accumulation, a suspected implementation defect — an exception message
built from user-supplied bound values with no cut (the trace path cuts at 1,000 chars, CASSANDRA-11719), queued by an appender
bounded only in event count. JIRA prior art (§1): `new`.

**What a better design should change (retry row).** Keep T and I as run here (they are decisive at 4 and 8 GiB) and freeze a
control that stays abort-free at the same budget — e.g. the A-3 shape (base, k = 2, **N = 8**: 0/3 at 8 GiB, no abort, slow
queue full), or N = 32 at k_c with a short value (S ≤ 64 KiB) so that any abort renders small — and test it ×3 at 4 GiB and
8 GiB; or ask the owner to rule that the intervention arm (same load, same abort rate, no render) is the matched control here,
since every failed control run failed through the claimed holder (5/5 analysed control dumps Q-attributed). The budget search
is done (fails at the node default, 31,744 MiB); `RN` is not needed.

**Limits.** R_Q in T-1..3 / C-1 counted ReadStage threads only (D-5); the k = 4 abort fraction in CAL-b4 is from the client
(D-4); server-logged abort counts exclude events still queued at a kill; C8-3's dump was not analysed; pc72 instead of pc91
(D-1).
