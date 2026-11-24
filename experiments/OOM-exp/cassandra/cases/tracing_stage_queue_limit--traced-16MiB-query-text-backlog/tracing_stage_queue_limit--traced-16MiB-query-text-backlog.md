# B28 — TRACING stage queue limit (1000 tasks, not bytes): traced 16 MB QUERYs leave their uncut query text queued as trace mutations after the in-flight charge is released  <!-- file: cassandra/cases/tracing_stage_queue_limit--traced-16MiB-query-text-backlog/tracing_stage_queue_limit--traced-16MiB-query-text-backlog.md -->

| Field | Value |
|---|---|
| Case ID | `B28` (B = bypass case, accounting omission; README "ID prefixes") |
| From | `OC-453` of the phase 1 OOM candidate list |
| Phase-1 case file | [`ExecuteMessage_literal_1000-traceQuery-1000--autonomous`](../../../../capacity-enforcement-exp/cassandra/stage3-ai-deep-read/cases/ExecuteMessage_literal_1000-traceQuery-1000--autonomous.md); stage 4: [`results/ExecuteMessage_literal_1000-traceQuery-1000--autonomous.md`](../../../../capacity-enforcement-exp/cassandra/stage4-runtime-verification/results/ExecuteMessage_literal_1000-traceQuery-1000--autonomous.md) |
| System / pinned source | Cassandra 5.0.9 (`systems/cassandra/source/`, `build.xml` `base.version` 5.0.9; repo HEAD `8f76f2390` at design time), OpenJDK 11.0.33, **x86_64** node `pc72` |
| Stage 1 (design) | OOM-agent stage-1 session, owner-approved batch of 2026-11-24, 2026-11-24 ≈ 05:00–06:10 America/New_York |
| Stage 2 (verify) | pending (a fresh session) |
| Verdict | `pending` |

## Summary

- **Conclusion:** pending (stage 2).
- **Hypothesis (root cause to test):** a client-traced unprepared QUERY (frame flag `0x02`, no permission needed) makes the
  request thread build two trace mutations that each carry the whole query text: the `system_traces.sessions` start row
  (`parameters['query']`, uncut, `QueryMessage.java:138`) and the `system_traces.events` row `"Parsing <query>"`
  (`QueryProcessor.java:896`). Both are queued on the single-thread TRACING stage, whose queue is limited to **1000 tasks**
  (`Stage.java:200`), not bytes. The request does not wait for them (`wait_for_tracing_events_timeout_secs` = 0), and the
  native-transport in-flight charge (heap/10, per IP heap/40) is released when the response is flushed. When clients send
  traced 16 MB QUERYs faster than the one tracing thread can write 16 MB mutations, the queued copies (≈ 32 MB per request)
  grow with no byte bound up to ≈ 500 × 16 MB ≈ 7.8 GiB, and the heap fails at budgets of 2–8 GiB.

## 1. Candidate

**Candidate row (quoted from `capacity-enforcement-exp/cassandra/stage5-oom-clue-find/phase1-oom-candidates.md`, status as
handed to this session):**

> | OC-453 | 2026-11-18 | `ExecuteMessage_literal_1000-traceQuery-1000--autonomous` | autonomous | Holder: start-session trace mutations queued on the single-thread TRACING stage. Why nothing stops it: the stage queue is limited by count (1000), not bytes. [details](runs/wave3.md#oc-453) | — | picked: B28 (2026-11-24) |

Details (`stage5-oom-clue-find/runs/wave3.md#oc-453`): "Each queued mutation carries the uncut 'query' text plus up to
B x 1004 chars of bound values. Once the request finishes, those bytes no longer count against the native in-flight limits.
Rough size at defaults: a traced EXECUTE with about 30k bind markers whose values each render to more than 1000 chars fits a
16 MiB request but carries about 30 MB of parameters. A traced unprepared QUERY carries its up-to-16 MiB query text. If the
one tracing thread falls behind, 1000 x 16-30 MB means about 16-30 GB can queue." Where: `ExecuteMessage.java:223-239`;
`TracingImpl.java:53-66`; `TraceStateImpl.java:104-107`; `Stage.java:196-202`.

The 2026-11-20 triage (`runs/triage-2026-11-20.md`, note 5(c)) listed it as a caveat: "the TRACING stage queue is capped by
count (1,000), not bytes. It fills only if the single tracing thread falls behind. Traced 16 MiB QUERYs also hit U6's parse
path, and B11's dumps showed no tracing-queue share. Consider it an optional arm of R12." This design answers those three
points: (a) the producer is many request threads on a 40-core node against one tracing thread that waits for every 16 MB
write (§2.1, §2.4); (b) the payload is a **comment**, which lexes as one token (R15's "comment control", 0/3 at 2 GiB, about
135 ms per 16 MiB request on the same node class), not U6's unlexable `#` text, and it is `USE`, not a read, so the slow-query
monitor (B11/R12's holder) is not involved; (c) B11 traced prepared EXECUTEs with a short query text, so its trace mutations
were ≈ 1.2 KB each (B11 §2.2) and could not show a queue share.

**Phase-1 case (stage 3).** The constraint is the hard-coded `1000` in `ExecuteMessage.traceQuery`; the stage-3 file states
that it "does not cap ... the `query` text, or the unprepared QUERY path, where literals sit in `query` uncut
(`QueryMessage.java:138`)". **Stage 4** (advisor's machine, outcome class true positive for the persisted cap) measured
that unprepared control: cell Q1M stored a `query` parameter of 2,097,189–2,097,190 chars for a 1 MiB inline value
(stored bytes linear in S). It measured no queue, concurrency or endpoint.

**Related OOM-exp cases (not the same holder).** B11 (`retry`): traced EXECUTE render buffers, OOM 3/3 at 2 GiB but the
slow-query monitor dominated. R12 (`true positive`): slow-query monitor keeps whole read commands. R15/R20 (U6 family):
error messages of an unlexable 16 MiB query. None of them measured trace mutations queued on TRACING.

**JIRA prior art (read only; nothing posted; REST search 2026-11-24, `project = CASSANDRA AND …`):**

| Query | Hits | Relevant |
|---|---|---|
| `text ~ "TracingStage"` | 9 | CASSANDRA-5658 (Not A Problem, 2013: TracingStage write timeouts, "hitting the nodes hard enough that they start dropping mutations"); CASSANDRA-7425 (Duplicate: local writes at CL.ANY timing out) — not memory |
| `text ~ "tracing" AND text ~ "OutOfMemoryError"` | 46 | none on tracing memory |
| `summary ~ "tracing" AND (text ~ "memory" OR text ~ "heap")` | 14 | **CASSANDRA-13157** (Open, 2017, "reduce overheads of tracing": "we store a string description for every trace line ... a completely unnecessary memory and IO overhead") — general overhead, no queue or OOM; CASSANDRA-12750 (Open: TRACE messages get dropped) |
| `text ~ "makeStartSessionMutation"` | 1 | CASSANDRA-8162 (Fixed: log client address) — not memory |
| `text ~ "system_traces" AND text ~ "OOM"` | 30 | none on tracing |
| `text ~ "tracing" AND text ~ "queue" AND text ~ "1000"` | 36 | none on the TRACING queue |
| `text ~ "tracing" AND text ~ "large query"` | 84 | none on trace memory |
| `text ~ "\"Parsing\"" AND text ~ "trace" AND text ~ "query string"` | 15 | none |
| `text ~ "_TRACE" AND text ~ "dropped"` | 415 | CASSANDRA-12750 (dropped TRACE), **CASSANDRA-10444** (Open, 2015, "Create an option to forcibly disable tracing": operators cannot stop client-requested tracing) |
| `text ~ "tracing" AND (text ~ "heap pressure" OR text ~ "memory pressure")` | 38 | none on tracing |

Also CASSANDRA-11719 (Fixed 3.8, from B11's search): the 1000-char cut was added because "boundValue can become quite big";
it covers bound values of prepared statements only, not the query text. **Verdict: `new`** (closest related: CASSANDRA-13157
open, overhead of trace strings; CASSANDRA-10444 open, no server-side off switch). Not a known-fixed bug, so not a positive
control.

## 2. Design solution (stage 1; frozen)

### 2.1 Mechanism

- **Tracing is client-chosen.** `Message.Request.execute` (`Message.java:235-259`) starts a session when the frame's TRACING
  flag is set (v4 header flag `0x02`), and stops it in `finally` (`:255-259`). No permission or server setting is needed.
- **Two copies of the query text per request.** `QueryMessage.execute` calls `traceQuery` **before** parsing
  (`QueryMessage.java:110-111`). `traceQuery` puts `"query" → query` into the parameters map (`:138`) and calls
  `Tracing.instance.begin` (`:146`) → `TracingImpl.begin` builds `TraceKeyspace.makeStartSessionMutation(…, parameters, …)`
  (`TracingImpl.java:53-66`; `TraceKeyspace.java:115-136`, `.appendAll("parameters", parameters)` at `:133` serializes each
  value: a UTF-8 `byte[S]` for an ASCII query) and submits it (`TraceStateImpl.executeMutation`, `:104-110`). Then
  `QueryProcessor.parse` → `getStatement` traces `"Parsing {}"` with the whole query (`QueryProcessor.java:345-347`, `:896`):
  SLF4J formats a `String` of S + 8 chars (`TraceState.java:154-157`), and `makeEventMutation` serializes it into the
  `activity` cell (`TraceKeyspace.java:147-163`, `byte[S+8]`). For `USE <ks>` the remaining events are `"Preparing
  statement"` (`:903`) and the stop-session row (`TracingImpl.java:40-51`): **4 TRACING tasks per request, 2 of them ≈ S bytes**.
- **No backpressure from tracing to the request.** `TraceState.stop()` calls `waitForPendingEvents()` (`TraceState.java:112-118`),
  which returns at once at the default `cassandra.wait_for_tracing_events_timeout_secs` = 0
  (`CassandraRelevantProperties.java:627`, `TraceStateImpl.java:76-80`). The response is sent while the trace tasks are queued.
- **The queue counts tasks.** `Stage.TRACING` is one thread (`Stage.java:54`) built with `.withQueueLimit(1000)` and a
  rejection handler that only records a dropped `_TRACE` message (`Stage.java:196-202`); the queue is a
  `LinkedBlockingQueue(1000)` (`ThreadPoolExecutorBuilder.java:160-167`, `BlockingQueues.java:43-47`). A task holds its
  `Mutation` (≈ S bytes) until it runs. Nothing charges those bytes; the task size is bounded only by the request frame
  (16 MiB) at enqueue (a mutation above `max_mutation_size` would fail only when applied).
- **One slow consumer.** The tracing thread runs `StorageProxy.mutate([m], ANY, …)` (`TraceStateImpl.java:112-122`) and blocks
  in `responseHandler.get()` until the local apply finishes on MutationStage (`StorageProxy.java:905-907`): commit-log
  serialization of 16 MB into the thread's scratch `DataOutputBuffer`, CRC and copy into an mmapped 32 MiB segment, then a
  16 MB on-heap clone into the `system_traces` memtable (`SlabAllocator.java:92-96`, values > 128 KiB are allocated
  outside regions). If the apply exceeds `write_request_timeout` (2 s), CL.ANY writes a hint instead (`:909-912`, `:960-967`).
  Request threads (up to 128 NTR threads, one per in-flight request) produce in parallel.
- **The in-flight limit no longer covers the copies.** v4 admission (`PreV5Handlers.java:83-87`, `:176-185`) charges the body
  size S to the channel, per-IP (heap/40) and global (heap/10) limits, and releases it in `releaseItem` when the response is
  flushed (`:97-106`). The two queued copies (≈ 2S) were made from that request but outlive the charge.
- **Direction:** bypass, accounting omission (U > C, K ≤ C): memory derived from client requests stays live after the
  native in-flight counter (K) has released it; the only bound on it is the TRACING queue's task count (1000), which caps
  tasks, not bytes (implicit bound 1000 × task size). Interpretation: suspected design gap (no byte bound on trace work,
  query text stored uncut, no server off-switch for client tracing — CASSANDRA-10444). Technique note:
  [`bypass-playbook.md`](../../../bypass-playbook.md) (accounting-mismatch shape: matched payload on the protected path as
  control; a patch that adds the missing byte bound as intervention).

### 2.2 Protection map

| Domain | Holder (allocation → release) | Counter (K) | Limit (C), shipped default | At the limit |
|---|---|---|---|---|
| Request body in flight | v4 frame (Netty direct, S + 16 B) and the decoded query `String` (heap `byte[S]`, Latin-1) → frame released at response flush (`PreV5Handlers.java:97-106`) | channel / per-IP / global byte counters (`RequestsSize` gauge) | global heap/10, per IP heap/40; contract: one request per connection is processed even above the limit (`:83-87`, `:180-185`) | connection paused; admitted request processed |
| **Queued trace mutations** (claimed holder) | start-session `parameters['query']` `byte[S]` + event `activity` `byte[S+8]` per request, inside `Mutation` → `FutureTask` → `LinkedBlockingQueue$Node` of the TRACING executor → unreachable after the task runs | **none in bytes**; TRACING `PendingTasks` counts tasks | `withQueueLimit(1000)` tasks (`Stage.java:200`); per task ≤ frame size (16 MiB); implicit ≈ 500 big tasks × 16 MiB with this workload | further tasks rejected and counted as dropped `_TRACE`; nothing is freed or refused upstream |
| Request ↔ trace coupling | `TraceState.stop()` → `waitForPendingEvents()` | — | `cassandra.wait_for_tracing_events_timeout_secs` = 0 (no wait) | — |
| Tracing consumer | one thread, `StorageProxy.mutate` at CL.ANY, blocks per mutation | `CompletedTasks` | 1 thread; `write_request_timeout` 2 s, then a hint (CL.ANY) | — |
| Trace memtables | `system_traces.sessions` / `events` cells cloned on heap (> 128 KiB unslabbed) → freed after flush | memtable pool (`heap_buffers`) | `memtable_heap_space` = heap/4; cleanup threshold 1/(1+2) = 0.33 (`DatabaseDescriptor.java:753-763`) | flush largest memtable; writers block at heap/4 |
| Commit log | 32 MiB mmapped segments (page cache, not heap/direct) | segment manager | `commitlog_segment_size` 32 MiB, `max_mutation_size` 16 MiB (`DatabaseDescriptor.java:898-899`), `commitlog_total_space` min(8 GiB, ¼ volume), periodic sync 10 s | flush memtables to recycle; mutation > 16 MiB rejected |
| Decode buffer | `TL_CHAR_BUFFER` `char[S]` per event-loop thread that decoded a long string, kept for the thread's life (`CBUtil.java:81`, `:89-110`) | none | ≤ connections (event loops 2 × cores = 80) | — (standing baseline, same in every arm) |
| Parse transients | ANTLR `char[S]` (`ANTLRStringStream`), SLF4J `StringBuilder`/`String` of S+8 for `"Parsing"` (test and intervention only) | none | per NTR thread in flight | — (transient) |
| Rendering/request concurrency | NTR workers | active tasks | `native_transport_max_threads` 128 | queued |
| Connections | one v4 connection per client IP | `connectedNativeClients` | `native_transport_max_concurrent_connections` −1, `_per_ip` −1 | — |
| Request size | one frame | — | `native_transport_max_frame_size` 16 MiB (`Config.java:285`) | rejected |
| Heap budget | JVM heap | — | `-Xmx` (2 / 4 / 8 / 12 GiB arms) | `OutOfMemoryError: Java heap space` → shipped `-XX:OnOutOfMemoryError="kill -9 %p"` |
| Direct budget | Netty frames | Netty / JDK direct counters | `MaxDirectMemorySize` auto 15,872 MiB on pc72 | competing endpoint, not the claim |

### 2.3 Configuration and budget audit

- **Build:** the node's `/mydata/s4/cassandra-base` (Cassandra 5.0.9 built from `systems/cassandra/source/` with
  `copy-source.sh` + `ant jar`; jar `build/apache-cassandra-5.0.9-SNAPSHOT.jar` md5 `c560848c966e329bbfdbb143497b1b66`,
  `conf/cassandra.yaml` md5 `714ee9bf58b3bc1710377ac16bcbba03` = R15/U6's), **copied** to the work dir, never run in place.
  The tree is not a git checkout: record the jar md5 and the repo commit. Intervention build: a second copy with the patch of
  §2.8 (`git apply` against the copied `src/`, delete `build/classes/main/org/apache/cassandra/tracing/TraceStateImpl*.class`,
  `ant jar`; check `javap -p -c -classpath <jar> org.apache.cassandra.tracing.TraceStateImpl | grep -c B28_QUEUED_BYTES` ≥ 1
  in iv, = 0 in base).
- **Configuration:** the shipped `conf/` unchanged in every arm (no `cassandra.yaml` edit, no capacity `-D`): single node,
  `127.0.0.1`, data and commit log under the tree's `data/` on `/mydata`, `heap_buffers`, `commitlog_sync: periodic` 10 s,
  `commitlog_disk_access_mode: legacy`. Every capacity constraint of §2.2 is at its shipped default (V6):
  TRACING queue 1000 (hard-coded), `wait_for_tracing_events_timeout_secs` 0, `native_transport_max_request_data_in_flight`
  heap/10, `…_per_ip` heap/40, `native_transport_max_threads` 128, `native_transport_max_frame_size` 16 MiB, connections −1/−1,
  `native_transport_rate_limiting_enabled` false, `memtable_heap_space` heap/4, `commitlog_segment_size` 32 MiB,
  `max_mutation_size` 16 MiB, `write_request_timeout` 2 s, `trace_type_query_ttl` 1d, `system_traces` RF 2 (one node).
- **Resolved at each heap** (`-Xmx`): 2 GiB → in-flight global 214,748,364 B, per IP 53,687,091 B, memtable 512 MiB;
  4 GiB → 429,496,729 / 107,374,182 / 1,024 MiB; 8 GiB → 858,993,459 / 214,748,364 / 2,048 MiB; 12 GiB → 1,288,490,188 /
  322,122,547 / 3,072 MiB.
- **Environment settings (not capacity):** `MAX_HEAP_SIZE` (`-Xms = -Xmx`), `CASSANDRA_HEAPDUMP_DIR=<run dir>`,
  `ulimit -n 100000`, the daemon in `systemd-run --user --scope -p MemorySwapMax=0` (swap 0; **no `MemoryMax`**), linger
  enabled for the session and disabled at the end; the shipped GC log (`-Xlog:gc=info,heap*=trace,…` → `logs/gc.log`), G1
  with `G1HeapRegionSize=16m`, `AlwaysPreTouch`, `PerfDisableSharedMem`, `HeapDumpOnOutOfMemoryError`.
- **Node claimed (V7):** `pc72` (`pc72.cloudlab.umass.edu`, node2 of `jason92-326665`): **x86_64**, 40 cores (Xeon E5-2660 v2
  @ 2.20 GHz), 125 GiB RAM, 8 GiB swap (unused), Ubuntu 22.04.2, kernel 5.15.0-203, cgroup v2, OpenJDK 11.0.33, Ant
  `/usr/bin/ant`, Python 3.10.12, hard `nofile` 1,048,576; `/mydata` 753 GiB, **707 GiB free**, on a rotational PERC H710P
  volume; `/mydata/s4/` holds `cassandra-base`, `3b-B21`, `3b-R22` (do not touch) and a `NODE-LOCK/owner` file reading
  `phase1-hadoop o7 Mon Nov 23 11:58:47 PM MST 2026`; no Java process running (read-only check 2026-11-24 03:49 MST).
  **Stage 2 confirms with the coordinator that pc72 is free (or takes another idle x86 node of the same class and records it)
  before any run.** `cassandra-env.sh` would resolve heap = min(½ RAM, 31,744 MiB) = **31,744 MiB** and
  `MaxDirectMemorySize` = **15,872 MiB** for this node. **Budgets:** heap 2 GiB (ideal), then 4, 8 and 12 GiB, all ≥ 512 MiB ⇒
  V7 met without per-case review (standing rule 2026-11-11); direct at the auto 15,872 MiB (record from `VM.flags`); no
  container limit. x86 only: never pool with aarch64 runs.
- **Why x86/40 cores:** the gap needs producers faster than the one tracing thread. On pc82 (same class) R15's comment
  control answered 16 MiB comment QUERYs in 115–234 ms, about 7 per second per connection, so 4–8 connections produce
  ≈ 25–55 requests/s (0.8–1.8 GB/s of queued copies) on 40 cores, against one consumer writing ≈ 16 MB per task.

### 2.4 Ceiling arithmetic

**Payload.** Query text Q of exactly **S = 16,000,000 bytes**, ASCII:
`USE b28 /*` + `a` × (S − 12) + `*/` (one hidden `MULTILINE_COMMENT` token, `Lexer.g:398-400`). QUERY body =
`[long string]` (4 + S) + consistency `0x0001` (2) + flags `0x00` (1) = 16,000,007 B; frame 16,000,016 B ≤ 16,777,216 ✓.
Start-session mutation ≈ S + 0.3 KB and event mutation ≈ S + 8 + 0.3 KB, both ≤ `max_mutation_size` 16,777,216 ✓. Each
16,000,0xx-byte array is one humongous G1 region (16 MiB); a `char[S]` is 2 regions.

**Per request:** in flight (NTR): `String` 1 region + ANTLR `char[S]` 2 + `"Parsing"` formatting ≤ 2 (transient) ≈ 5 regions;
queued after the response: **2 regions (32 MiB) per request**; tasks per request 4 ⇒ the 1000-task cap holds at most ≈ 250
requests = **≈ 500 regions (7.8 GiB)**. Standing: baseline ≈ 15 regions after GC (B11 control), `TL_CHAR_BUFFER` 2 regions
per event loop used (≤ 2N), memtable copies (1 region per applied big mutation) between the flush trigger heap/12 and the
limit heap/4.

| Heap | regions | N | fixed: baseline + TL + in flight + memtable (regions) | room for the queue | queued requests at the endpoint (tasks) | Prediction |
|---|---|---|---|---|---|---|
| 2 GiB | 128 | 4 | 15 + 8 + 20 + 11…32 = 54…75 | 53…74 | ≈ 26–37 (105–150 ≪ 1000) | **fail** within seconds of the queue starting to grow |
| 4 GiB | 256 | 8 | 15 + 16 + 40 + 21…64 = 92…135 | 121…164 | ≈ 60–82 (240–330) | **fail** |
| 8 GiB | 512 | 8 | 15 + 16 + 40 + 43…128 = 114…199 | 313…398 | ≈ 156–199 (625–800 < 1000) | **fail** before the count cap |
| 12 GiB | 768 | 8 | 15 + 16 + 40 + 64…192 = 135…263 | 505…633 ≥ 500 | the cap (≈ 250 requests, 500 regions) is reached first | **borderline / survive** (count cap binds; dropped `_TRACE` > 0) |

Σ contract capacities covering this memory: none in bytes (the in-flight heap/10 covers only requests in flight, ≤ N × S =
64–128 MB here); the queue's implicit bound is 1000 tasks × ≤ 16 MiB. Feasibility: the queued bytes alone exceed the free heap
at 2–8 GiB, so the endpoint is reachable if production exceeds consumption. **Rate condition:** production ≈ r_req × 32 MB/s
with r_req ≈ 7 × N requests/s (R15 latency), consumption ≈ 16 MB per task-time of the one tracing thread (estimated
25–50 ms per 16 MB apply, i.e. 0.3–0.6 GB/s, less when the memtable pool blocks on flush to the HDD). At N = 4:
≈ 0.9 GB/s vs ≤ 0.6 GB/s ⇒ net growth ≥ 0.3 GB/s ⇒ 2 GiB exhausted in < 10 s of load. Direct memory: ≤ N frames of 16 MB, far
below 15,872 MiB.

### 2.5 Workload and environment

- **Node:** `pc72` only (victim and client on the same node, one run at a time). Work dir **`<W>` = `/mydata/s4/b28/`**:
  `cassandra/` (`cp -a /mydata/s4/cassandra-base`), `cassandra-iv/` (intervention build), `harness/`, `runs/<run-id>/`.
  Never modify `/mydata/s4/cassandra-base` or the `3b-*` folders. Preflight per run: no `CassandraDaemon` process, ports
  7000/7199/9042 free, `df /mydata` ≥ 60 GiB free. `sudo loginctl enable-linger jason92` at start, `disable-linger` at the end
  (or drive each series from one long-lived `ssh` session as R15 did).
- **Schema** (after each start, untraced): `CREATE KEYSPACE b28 WITH replication = {'class':'SimpleStrategy','replication_factor':1};`
  No table, no data. Wipe `<tree>/data`, `<tree>/logs` before each run (removes `system_traces` data too).
- **Statement:** the unprepared QUERY of §2.4 (`USE b28` plus a 15,999,988-byte comment), consistency ONE, protocol v4. It is
  valid CQL within every documented limit; it returns `RESULT` kind `SetKeyspace` and does no read or write of user data.
  The comment stands for any long query text (for example an inline literal); the mechanism needs only the text's length.
- **Client** (`harness/client.py`, Python 3 stdlib, raw v4; adapted from B11's client (per-connection source IPs, closed
  loop) and R15's QUERY builder):
  - N connections, connection i bound to `127.1.(i // 250).(1 + i % 250)` before `connect(('127.0.0.1', 9042))` (one
    request per IP ≤ heap/40).
  - Per connection: STARTUP → READY, then a closed loop: send the QUERY frame, wait for its response, repeat. Header
    `0x04, flags, stream 0, opcode 0x07, length`. **flags = `0x02` (tracing) in test and intervention arms, `0x00` in the
    control: the only difference.** The frame is built once and the same `bytes` object sent on every connection.
    Responses: `RESULT` (with tracing, the body starts with the 16-byte session id) or `ERROR` (log code + text, continue).
  - Modes: ramp (`--ramp 1,2,4,8 --step-s 60`) and fixed (all N started together, held `--hold-s`).
  - Logs: one line per completion (`t_ms conn latency_ms status`), a once-per-second line (`t_ms open outstanding
    completed errors`).
- **Run driver** (`harness/run.sh <run-id> <base|iv> <heap> <traced|untraced> <fixed N | ramp list> <hold-s>`): preflight →
  wipe → start `( ulimit -n 100000; MAX_HEAP_SIZE=<heap> CASSANDRA_HEAPDUMP_DIR=<run dir> systemd-run --user --scope -p
  MemorySwapMax=0 --unit=b28-<run-id> -- bin/cassandra -f > <run dir>/stdout.txt 2>&1 < /dev/null & )` → wait for
  `Starting listening for CQL clients` (≤ 300 s, bounded poll) → `jcmd <pid> VM.flags` → schema → monitors → client → wait
  for the endpoint (daemon gone and `grep -F 'java.lang.OutOfMemoryError:' stdout.txt`) or the hold end → stop the client,
  `kill <pid>` (`-9` after 60 s) → copy `system.log`, `gc.log*`, stdout, client and monitor logs → `summarize.py`. No
  foreground `sleep` in the agent's turn: launch detached and poll.
- **Arms** (all: S = 16,000,000, same instruments; base build unless stated):

| Run | Build | Heap | Tracing | N | Hold | Purpose |
|---|---|---|---|---|---|---|
| `S0` shakedown | base | 2 GiB | on | 1 | 3 requests at S = 1,000,000, then 3 at S | reachability (not a reading): RESULT SetKeyspace; `system_traces.sessions` `parameters['query']` length = S; `events` per session = 2 (`Parsing USE b28 /*aaa…` of S + 8 chars, `Preparing statement`); TracingStage `CompletedTasks` + 4 per request; JMX poller works |
| `R2` ramp | base | 2 GiB | on | 1, 2, 4, 8 | 60 s per step | calibration: per step requests/s, TracingStage `PendingTasks` slope, first failing N (N_f) |
| `T2-1..3` test | base | 2 GiB | on | N₂ | ≤ 180 s | V1 at 2 GiB |
| `C2-1..3` control | base | 2 GiB | off | N₂ | 150 s | V2 (same frames, no trace tasks) |
| `I2-1..3` intervention | iv | 2 GiB | on | N₂ | 150 s | V4 |
| `T4-1` (→ `-2`, `-3`) | base | 4 GiB | on | 8 | ≤ 180 s | budget search |
| `T8-1` (→ `-2`, `-3`) | base | 8 GiB | on | 8 | ≤ 180 s | budget search |
| `T12-1` | base | 12 GiB | on | 8 | ≤ 240 s | boundary (only if `T8-1` failed) |
| `C*`, `I*` at the largest failing budget | base / iv | largest failing | off / on | 8 | 150 s | V2/V4 there, as time allows |
| `I2b-1` (optional) | base, `-Dcassandra.wait_for_tracing_events_timeout_secs=10` | 2 GiB | on | N₂ | 150 s | second intervention (couples requests to their trace writes); only if time remains, not needed for V4 |

  **N₂ (frozen rule):** N₂ = 4, except: if `R2` fails at N ≤ 2, N₂ = that N; if `R2` survives N = 4 with TracingStage
  `PendingTasks` not growing (slope ≤ 0 over the step), N₂ = 8. If `R2` survives N = 8 with no queue growth, skip T2/C2/I2,
  run `T4-1`/`T8-1` as U readings only, and record outcome O9. Do not exceed N = 8 (the control's transient heap grows
  ≈ 5 regions per connection).

### 2.6 Instruments

| What | How | Interval | Gives |
|---|---|---|---|
| Queue length K_q (the control's own counter) and throughput of the consumer | JMX poller (R15's `Jmx.java poll`, one JVM, one connection): `org.apache.cassandra.metrics:type=ThreadPools,path=internal,scope=TracingStage,name=PendingTasks` / `CompletedTasks` / `ActiveTasks` (`Value`), `…type=DroppedMessage,scope=_TRACE,name=Dropped` (`Count`), `…scope=MutationStage,name=PendingTasks`, `…type=Client,name=RequestsSize` (in-flight bytes K), `java.lang:type=Memory HeapMemoryUsage` | 500 ms | K_q(t) ≤ 1000, dropped `_TRACE`, consumer rate, K (in-flight), heap used |
| Live humongous memory (U, independent of K) | shipped `gc.log`: per GC `Humongous regions: X->Y`, heap after GC, `Pause Full`, `To-space exhausted`, causes | every GC | U_h after GC; U_queue ≈ U_h(test) − U_h(control) at matched N |
| Memtable copies | JMX `org.apache.cassandra.metrics:type=Table,keyspace=system_traces,scope=sessions|events,name=AllMemtablesOnHeapDataSize` (`Value`) | 2 s | trace bytes in memtables (separate, capped domain) |
| Threads | `jcmd <pid> Thread.print`: NTR threads in `CqlLexer`/`TraceKeyspace`/`MessageFormatter`; the `TracingStage` thread's frame (`CommitLog.add`, `waitForMemory`, `responseHandler.get`) | 10 s | producer concurrency; where the consumer waits |
| Requests / latency | client completion lines | per response | requests/s, latency, errors per arm (an intervention that stops useful work is not protection) |
| Disk, hints | `df -BM /mydata`; `du -sm <tree>/data/commitlog <tree>/data/hints <tree>/data/data/system_traces` | 10 s | guard (< 60 GiB free ⇒ stop the client) and CL.ANY hints |
| Process | `RssAnon` (`/proc/<pid>/status`), scope `memory.current` | 2 s | native growth |
| Endpoint | `stdout.txt`: `java.lang.OutOfMemoryError: Java heap space`, `Dumping heap to …`, `OnOutOfMemoryError`; `system.log` ERROR lines | end | endpoint type |
| Holder at failure (V5) | the shipped heap dump: `hprof_oome_thread.py` (B11 `harness/`) for the initiating thread; `bigarrays.py` + `retainers.py` (B11 / R12 `harness/`) adapted to classify every `byte[]` of length 15,999,9xx–16,000,4xx and `char[]` ≥ 1 MiB by owner: **TRACING queue** (`LinkedBlockingQueue$Node.item` of the TracingStage executor → `FutureTask` → lambda → `Mutation` → … → `HeapByteBuffer.hb`), **running trace task** (TracingStage / MutationStage frames, scratch `DataOutputBuffer`), **memtable** (`system_traces` memtable partitions), **in-flight request** (NTR frames, `QueryMessage.query`), **decode buffer** (`TL_CHAR_BUFFER`), unreachable | first failing run per budget in full; every failing run: OOME thread + owner totals | U_queue bytes and share of the dump |
| Trace rows | `S0` and once after `I2-1`'s hold: `SELECT session_id, blobAsText(…)`-free check via `cqlsh`: `SELECT count(*) FROM system_traces.events`; length of `parameters['query']` in a few `sessions` rows | — | S0 reachability; intervention keeps tracing small sessions |

The JMX poller, thread sampler and disk monitor run identically in every arm (matched instrumentation). No forced GC, no
histogram during load. `summarize.py` writes per run: endpoint, time to endpoint after full N, requests/s, latency median,
max K_q, dropped `_TRACE`, max K, max/median U_h after GC, memtable trace bytes max, STW share over the last 60 s, max RssAnon,
dump findings.

### 2.7 Predicted response, outcome rows and stopping budget

**Predicted protective response:** none for the queued copies. The in-flight limit is never reached (K ≤ N × 16 MB ≤ 128 MB
< heap/10 at every budget) and is released per response; the TRACING queue rejects only past 1000 tasks; requests never
wait for trace writes. **Predicted readings:** `S0` shows 4 TRACING tasks per request and an uncut 16,000,000-char `query`
parameter. In `R2` at N = 4 the TracingStage `PendingTasks` rises steadily (≈ 10–20 tasks/s) while requests continue at
≈ 25/s; the test at 2 GiB fails with `OutOfMemoryError: Java heap space` 3/3 within 60 s of full N, dropped `_TRACE` = 0
(queue below the cap); the dump attributes **≥ 50 % of the dump's bytes, and the largest single owner**, to 16,000,0xx-byte
arrays held by the TRACING queue (≈ 26–37 queued requests ≈ 0.8–1.2 GiB), with K ≤ 64 MB. The initiating thread is an NTR
thread (decode, lexer or `"Parsing"` formatting) or the MutationStage clone; either is allowed (the attribution is by the
dump). Control (same N, untraced): survives, U_h after GC ≤ baseline + TL + in-flight ≈ 0.6 GiB, `PendingTasks` 0.
Intervention: survives, `PendingTasks` small, dropped `_TRACE` > 0 (big tasks dropped by the byte bound), requests/s within
± 30 % of the control. 4 and 8 GiB fail at N = 8 (U_queue ≈ 2–6 GiB); 12 GiB survives with the queue at the count cap
(dropped `_TRACE` > 0, U_queue ≈ 7.8 GiB): the largest failing budget is predicted 8 GiB.

| Row | Observation | Reading |
|---|---|---|
| O1 | test heap OOM ≥ 3/3 at a budget, control 0/3, intervention 0/3, dump: TRACING queue the largest owner and ≥ 50 % of the dump, U_queue ≫ K | endpoint reached: `true positive` candidate (`verified-OOM · deployment` if V1–V7 hold) |
| O2 | test survives at 2 GiB with the queue growing to the cap (dropped `_TRACE` > 0) | the count cap binds below the heap: report the ceiling; `false positive` only if every larger N/budget arithmetic also stays below (it should not at 2 GiB: 500 regions > 128) — otherwise `retry` |
| O3 | test OOMs but the dump's largest owner is not the queue (e.g. in-flight requests, memtable, decode buffers) | attribution fails: `retry` |
| O4 | direct OOM first | competing endpoint: record, rerun once at the next lower N; if repeated, `retry` |
| O5 | control also OOMs | request transients alone suffice at this N: rerun the 2 GiB set at the next lower N (N₂ − 1, ≥ 2) once; if the control still fails, `retry` |
| O6 | GC service loss (≥ 90 % STW over ≥ 60 s) without OOM | `verified-gap · service-loss`: `retry` |
| O7 | intervention also OOMs | the bound did not remove the holder: `retry` |
| O8 | 4/8 GiB survive with `PendingTasks` growing but the hold ends first | extend that budget's hold once to 300 s (pre-declared here); then boundary |
| O9 | `R2` survives N = 8 with no queue growth (consumer keeps up) | producer too slow on this node: report rates; `retry` (more producers: several client nodes or prepared EXECUTE of a long prepared text) |

**Stopping budget:** per run ≤ 300 s to start, ≤ 180 s of load at full N (test; 240 s for `T12-1`; one pre-declared 300 s
extension under O8), 150 s for control and intervention, 60 s per ramp step; one run at a time; at most 3 repeats per arm per
budget plus one rerun per invalid run; no N above 8, no budget above 12 GiB, no arbitrary escalation after an OOM. Endpoint
of a run = the first of heap OOM, direct OOM, hold end. **Time budget for stage 2: ≤ 4 h** from its start (build ≈ 10 min,
`S0` + `R2` ≈ 15 min, the 2 GiB set of 9 runs ≈ 50 min, the budget search ≈ 30 min, repeats/controls at the largest budget
≈ 40 min, analysis and cleanup ≈ 60 min). **Priority if late:** `S0` → `R2` → `T2` ×3 → `C2` ×3 → `I2` ×3 → `T4-1` → `T8-1`
→ `T12-1` → repeats at the largest failing budget → `I2b-1`. **Disk:** dumps ≈ heap each; keep every 2 GiB dump and the first
dump per larger budget, reduce and delete the others; trace data and commit log are wiped between runs. **RAM/cores:**
largest process ≈ 12 GiB heap + < 1 GiB direct + 1 GiB native, client < 1 GiB, of 125 GiB.

### 2.8 Controls and intervention

- **Matched control (V2), ≥ 3 runs per condition:** the same frames, N, source IPs, heap and build with the tracing flag clear
  (`0x00`): the same decode, in-flight charge, lexing of the comment, `USE` execution and response, without the trace
  mutations. Survival with `PendingTasks` = 0 and U_h ≈ baseline + decode buffers + in-flight shows that the request load
  alone does not reach the endpoint.
- **Causal intervention (V4), ≥ 3 runs per condition:** a separate build (`<W>/cassandra-iv`) that adds the missing **byte
  bound** on queued trace work: at most 64 MiB of serialized trace mutations may be queued; a mutation beyond it is dropped
  and counted as a dropped `_TRACE` (the same handling as the count cap). The count cap, the request path and every
  constraint stay as shipped. Diff saved as `harness/iv.patch`:

```diff
--- a/src/java/org/apache/cassandra/tracing/TraceStateImpl.java
+++ b/src/java/org/apache/cassandra/tracing/TraceStateImpl.java
@@ -53,6 +53,10 @@ public class TraceStateImpl extends TraceState
     @VisibleForTesting
     public static int WAIT_FOR_PENDING_EVENTS_TIMEOUT_SECS = CassandraRelevantProperties.WAIT_FOR_TRACING_EVENTS_TIMEOUT_SECS.getInt();
 
+    // B28 intervention (diagnostic build only): a byte bound on trace mutations queued on the TRACING stage
+    private static final java.util.concurrent.atomic.AtomicLong B28_QUEUED_BYTES = new java.util.concurrent.atomic.AtomicLong();
+    private static final long B28_QUEUED_BYTES_LIMIT = 64L << 20;
+
     private final Set<Future<?>> pendingFutures = ConcurrentHashMap.newKeySet();
 
     public TraceStateImpl(InetAddressAndPort coordinator, TimeUUID sessionId, Tracing.TraceType traceType)
@@ -103,7 +107,19 @@ public class TraceStateImpl extends TraceState
 
     void executeMutation(final Mutation mutation)
     {
-        Future<Void> fut = Stage.TRACING.executor().submit(() -> mutateWithCatch(mutation), null);
+        final long size = mutation.serializedSize(org.apache.cassandra.net.MessagingService.current_version);
+        if (B28_QUEUED_BYTES.addAndGet(size) > B28_QUEUED_BYTES_LIMIT)
+        {
+            B28_QUEUED_BYTES.addAndGet(-size);
+            org.apache.cassandra.net.MessagingService.instance().metrics.recordSelfDroppedMessage(org.apache.cassandra.net.Verb._TRACE);
+            return;
+        }
+        Future<Void> fut = Stage.TRACING.executor().submit(() -> {
+            try { mutateWithCatch(mutation); }
+            finally { B28_QUEUED_BYTES.addAndGet(-size); }
+        }, null);
         boolean ret = pendingFutures.add(fut);
         if (!ret)
             logger.warn("Failed to insert pending future, tracing synchronization may not work");
```

  (Apply with `git apply --recount` if the hunk offsets differ; context = `TraceStateImpl.java:53-56`, `:104-110`. A task
  rejected by the count cap would leak its bytes from the counter; at ≤ 64 MiB queued the cap of 1000 tasks is not reached
  by this workload, and `summarize.py` reports dropped `_TRACE` so a leak would show as a growing drop rate with an empty
  queue.) The original failure must reproduce on the unmodified base build (`T2`). Record the intervention's requests/s
  against the test's pre-failure rate and the control's.
- **Optional second intervention** `I2b-1` (config only, no patch): `-Dcassandra.wait_for_tracing_events_timeout_secs=10`
  makes `TraceState.stop()` wait for the request's own trace tasks, so each connection has ≤ 4 queued tasks; not required
  for V4.
- **V-table plan:** V1 `T2-1..3` (and repeats at the largest failing budget); V2 `C2-1..3`; V3 U_h and dump owners vs K
  (`RequestsSize`) and K_q (`PendingTasks`) in every arm; V4 `I2-1..3`; V5 stdout OOM line + `hprof_oome_thread.py` +
  owner totals on the first `T2` dump (and the first dump per larger budget); V6 §2.3 (no constraint changed in a test arm;
  the patch only in `iv`, the property only in `I2b`); V7 heap 2–12 GiB, direct auto 15,872 MiB, no container limit.
  Largest failing budget reported with n/N.

`sha256 of §1–§2 at freeze: 06eb83a2a9aefe1d7a0a5c07a16773df7fa140fff9d09df07ea315bb82d5c568` (computed as `awk '/^## 1\. Candidate/{p=1} /^`sha256 of §1–§2 at freeze/{p=0} p' <this file> | sha256sum`, i.e. from the `## 1. Candidate` line up to, not including, this line; 2026-11-24) · amendments after the freeze: none.

## 3. Runs (stage 2)

pending

## 4. Conclusion (stage 2)

pending
