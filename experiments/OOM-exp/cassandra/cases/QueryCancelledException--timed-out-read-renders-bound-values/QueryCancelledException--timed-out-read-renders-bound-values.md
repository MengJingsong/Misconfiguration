# U16 — `QueryCancelledException`: a read aborted at its deadline renders every bound value whole into the exception message, which the debug log queues and lays out again  <!-- file: cassandra/cases/QueryCancelledException--timed-out-read-renders-bound-values/QueryCancelledException--timed-out-read-renders-bound-values.md -->

| Field | Value |
|---|---|
| Case ID | `U16` (U = unprotected-accumulation case; README "ID prefixes") |
| From | `OC-578` of the phase 1 OOM candidate list (Agent `phase-2 (R12)`: a holder found in R12's dumps, not tested as a claim there) |
| Phase-1 case file | none |
| System / pinned source | Cassandra 5.0.9 (`systems/cassandra/source/`, `build.xml` `base.version` 5.0.9); built tree `pc91:/mydata/s4/cassandra-base` (`build/apache-cassandra-5.0.9-SNAPSHOT.jar` 2026-11-17 21:05, sha256 `570b5249…ea90176e`), OpenJDK 11.0.33 **x86_64**, Ubuntu 22.04.2, kernel 5.15.0-203, logback 1.5.18 (`lib/logback-*-1.5.18.jar`) |
| Stage 1 (design) | OOM-agent stage-1 session (owner-approved batch of 2026-11-24), 2026-11-24 05:50 America/New_York |
| Stage 2 (verify) | pending (a fresh OOM-agent session) |
| Verdict | `pending` |

## Summary

- **Conclusion:** pending (stage 2).
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

`sha256 of §1–§2 at freeze: 27fbd095cef25e099a6cb6c238ca4edd78f75130ad6ffea3916c70f4a7a4d24f` (computed as `awk '/^## 1\. Candidate/{p=1} /^`sha256 of §1–§2 at freeze/{p=0} p' <this file> | sha256sum`, i.e. from the `## 1. Candidate` line up to, not including, this line; 2026-11-24) · amendments after the freeze: none.

## 3. Runs (stage 2)

pending

## 4. Conclusion (stage 2)

pending
