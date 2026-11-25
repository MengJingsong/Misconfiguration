# B27 — native_transport_receive_queue_capacity: v5 per-connection allowance outside the reserves × unlimited connections  <!-- file: cassandra/cases/native_transport_receive_queue_capacity--v5-per-connection-allowance-outside-reserves/native_transport_receive_queue_capacity--v5-per-connection-allowance-outside-reserves.md -->

| Field | Value |
|---|---|
| Case ID | `B27` (assigned at pick, from the clue's "allowance outside the reserves" framing; the protection map below scopes the claim as multiplicity convergence with an unprotected configuration, see §2.1) |
| From | `OC-269` of the phase 1 OOM candidate list; cluster OC-50, OC-105, OC-125, OC-137, OC-139, OC-179, OC-261, OC-264, OC-420, OC-422, OC-433 (owner-approved batch of 2026-11-24) |
| Phase-1 case file | [`native_transport_max_request_data_in_flight_per_ip-setNativeTransportMaxRequestDataInFlightPerIpInBytes-maxRequestDataInFlightInBytes--autonomous`](../../../../capacity-enforcement-exp/cassandra/stage3-ai-deep-read/cases/native_transport_max_request_data_in_flight_per_ip-setNativeTransportMaxRequestDataInFlightPerIpInBytes-maxRequestDataInFlightInBytes--autonomous.md) (OC-269); OC-50's: [`native_transport_max_concurrent_connections-channelActive-limit--guided`](../../../../capacity-enforcement-exp/cassandra/stage3-ai-deep-read/cases/native_transport_max_concurrent_connections-channelActive-limit--guided.md) |
| System / pinned source | Cassandra 5.0.9 (`systems/cassandra/source/`, tag `cassandra-5.0.9`); node build `pc72:/mydata/s4/cassandra-base` |
| Stage 1 (design) | OOM agent, stage 1 (batch 2026-11-24 workflow subagent), 2026-11-24 05:30–06:10 EST |
| Stage 2 (verify) | fresh OOM-agent session (batch 2026-11-24 workflow subagent, attempt 3), 2026-11-24 20:10–21:30 EST, node `pc91`; attempts 1–2 earlier that day were interrupted (§3.0) |
| Verdict | **true positive** — `verified-OOM · deployment` (convergence by multiplicity, unprotected configuration: connection limits −1) |

**Summary:**
- **Conclusion:** heap OOM (`java.lang.OutOfMemoryError: Java heap space`) **3/3 at 2 GiB** (46–94 s) with every constraint at
  its shipped default: 3,500 v5 connections, each keeping 7 requests (≈ 0.88 MB) in flight, never refused, never
  charged to a reserve (global reserve in use ≤ 44 B). The dumps hold ≈ 16,030 decoded 125,000-byte values = 94 % of the
  heap (9.3 × the heap/10 global reserve), ≈ 4.6 requests per connection (inside each connection's 1 MiB).
  1,000 connections 0/3; the same 3,500 attempted with `native_transport_max_concurrent_connections: 1000` 0/3 (useful
  work continues); every byte charged to the reserves (queue capacity 0 B) holds 427 requests. Larger budgets also fail:
  4 GiB / 7,000 connections 3/3, **8 GiB / 14,000 connections 3/3** (largest tested).
- **Root cause:** each native-protocol v5 connection admits request bytes against its own exclusive
  `native_transport_receive_queue_capacity` (1 MiB) before the per-IP (heap/40) or global (heap/10) reserve is charged at
  all, and the number of connections ships unlimited (−1); so N well-behaved connections, each keeping < 1 MiB of
  requests in flight, hold N MiB of decoded requests on the heap while every reserve counter reads 0, and only the heap
  stops N.

## 1. Candidate

**Candidate row (quoted from `phase1-oom-candidates.md`, 2026-11-24):**

> | OC-269 | 2026-11-18 | `native_transport_max_request_data_in_flight_per_ip-setNativeTransportMaxRequestDataInFlightPerIpInBytes-maxRequestDataInFlightInBytes--autonomous` | guided | The native-v5 per-connection receive queue sits outside both the per-IP and the global in-flight limits, and connections are unbounded (also in case native-transport-max-request-data-in-flight-...--autonomous; [details](runs/wave2.md#oc-269) | CP-7, CP-1 | picked: B27 (2026-11-24) |

Details (`stage5-oom-clue-find/runs/wave2.md#oc-269`): "Holder: each CQL v5 connection's queueCapacity
(native_transport_receive_queue_capacity, default 1 MiB, Config.java:302). acquireCapacity takes the request bytes from
that queue first and charges only the excess to the global and endpoint reserves (AbstractMessageHandler.java:418-436).
Why nothing stops it: native_transport_max_concurrent_connections and native_transport_max_concurrent_connections_per_ip
are both -1 (Config.java:289-290), so one IP holds up to C x 1 MiB + heap/40, and the node holds up to C x 1 MiB +
heap/10. Size: stage 4 measured the bytes held beyond the limit as exactly C x Q. 1,000 connections give about 1 GiB of
request frames (mostly pooled direct memory) beyond the default global heap/10 …"

The cluster rows say the same with other stems: OC-50 (legacy: "≈ 1 MiB held per busy connection beyond the limits
(stage 4: exactly connections × 1 MiB), ≈ 2 GiB for 2,000 connections"), OC-105, OC-125 (adds "plus their decoded heap
copies"), OC-137, OC-139, OC-179, OC-261, OC-264, OC-420, OC-422, OC-433. Triage 2026-11-18 rank 18 and 2026-11-20 put
them in one cluster ("v5 per-connection 1 MiB allowance") and noted the overlap with U2 and B10.

**Phase-1 constraint and check.** `native_transport_receive_queue_capacity` (default 1 MiB, `Config.java:302`) is the
`queueCapacity` of each v5 connection's `CQLMessageHandler` (`PipelineConfigurator.java:306`, `:326`).
`AbstractMessageHandler.acquireCapacity` (`AbstractMessageHandler.java:411-458`) admits a message against that exclusive
`queueSize` when `queueSize + bytes ≤ queueCapacity` (`:418-423`, returns SUCCESS without touching any reserve), and only
the excess beyond it is charged to the global reserve (`native_transport_max_request_data_in_flight`, default heap/10,
`DatabaseDescriptor.java:651`) and the endpoint reserve (`…_per_ip`, default heap/40, `:656`). The connection count is
bounded only by `native_transport_max_concurrent_connections` / `…_per_ip`, both −1 (`Config.java:289-290`), so the
`ConnectionLimitHandler` is not even installed (`PipelineConfigurator.java:239-245`).

**Stage-4 evidence (phase 1).**
- OC-269's case, [stage-4 result 2026-10-26](../../../../capacity-enforcement-exp/cassandra/stage4-runtime-verification/results/native_transport_max_request_data_in_flight_per_ip-setNativeTransportMaxRequestDataInFlightPerIpInBytes-maxRequestDataInFlightInBytes--autonomous.md):
  unit tier **Confirmed** — "V5 plateau 0.79 / 3.93 / 16.52 MB at L = 1 / 4 / 16 MiB … admitted − plateau = C·Q exactly":
  the bytes admitted beyond the per-IP limit are exactly connections × queue capacity. Cluster tier (64 connections,
  Byteman 5 s write hold) "Not confirmed (no matching row)" only because a frozen clause read the `Client.PausedConnections`
  gauge, which goes negative on v5. Stage 4 counted bytes; it did not measure the decoded heap copies or seek an OOM.
- OC-50's case, [stage-4 result 2026-10-20](../../../../capacity-enforcement-exp/cassandra/stage4-runtime-verification/results/native_transport_max_concurrent_connections-channelActive-limit--guided.md):
  an idle connection costs 1,329.6 B of heap (1,285.5 B with no limit handler); its control (64 connections, limits
  1 GiB, queue capacity 1 MiB) held 64 requests with the global reserve at 4,736 B.

What phase 2 adds: an **OOM at defaults** from the allowance alone, with **no refused request** (so not B10's drift), the
reserves reading 0, and the held bytes measured on the heap independently of any counter.

**Relation to filed cases.** **B10** (true positive) is the *refused* path: windows above 1 MiB per connection, refused
requests dispatched uncharged, counter drift; its holder is the same (decoded `QueryMessage` values on the NTR queue).
B27 keeps every connection **inside** its contract (≤ 8 requests ≤ 1 MiB, never refused), so the default-mode refusal
branch is never taken; the gap is the contract itself × unlimited connections. **U2** (true positive) is pre-STARTUP
partial v4 envelopes in Netty direct memory; B27 is authenticated, complete v5 requests on the heap. **R13** is v4
forced allocation. None covers this mechanism.

**JIRA prior art (read only, nothing posted; issues.apache.org REST, 2026-11-24 05:40–05:45 EST).**
- `project = CASSANDRA AND text ~ "native_transport_receive_queue_capacity"` → 14 hits: CASSANDRA-20052 (v5 message size
  not limited; Fixed 4.1.8 / 5.0.3, so in 5.0.9; bounds one message, not connections × allowance), 17737, 17292, 20749,
  17431, 15299 (v5 framing follow-up), the rest test failures or unrelated.
- `text ~ "receive_queue_capacity" AND text ~ "native"` → 14 (same set).
- `text ~ "native_transport_max_concurrent_connections" AND (text ~ "memory" OR text ~ "OOM" OR text ~ "OutOfMemoryError")`
  → 22: 8723 (RSS growth, Cannot Reproduce), 10861 (driver leak, Not A Problem), 20052, 21191 (connection draining), 13365
  (GC loop, Awaiting Feedback), others unrelated; none on the allowance.
- `text ~ "queueCapacity" AND text ~ "connection"` → 0.
- `summary ~ "connections" AND (summary ~ "limit" OR summary ~ "unlimited") AND (text ~ "memory" OR text ~ "OOM")` → 1:
  **CASSANDRA-4265** "Limit total open connections (HSHA server)", **Won't Fix** — the same shape in the Thrift era
  (per-connection buffers × unlimited connections), closed without a limit; the native connection limit added later ships
  disabled.
- `text ~ "\"in flight\"" AND text ~ "per connection" AND text ~ "native"` → 25: 9318, 16663, 13304, **15519** (make the
  in-flight byte limits changeable at runtime, Fixed), 20052, **15013** (introduced the native in-flight byte limits,
  Fixed 4.0), 15299; none says the per-connection allowance sits outside the reserves or bounds connections × allowance.
- **Verdict: `new`** (related: CASSANDRA-4265 Won't Fix, Thrift). **Documented:** no. The shipped `cassandra.yaml`
  documents neither `native_transport_receive_queue_capacity` nor the native in-flight reserves (only the internode
  analogue, `conf/cassandra.yaml:1370-1383`, which says "the basic per-link limit is consumed in isolation before any
  endpoint or global limit is imposed" and that a node may hold N·3·(send + receive capacity) "without any coordination").
  Not a known-fixed bug, so not a positive control.

## 2. Design solution (stage 1; frozen)

### 2.1 Mechanism

**Direction (expected by measurement): convergence by multiplicity, unprotected configuration** (protocol
"Classification by measurement", the C1 precedent: "per-connection exclusive ≤ Q, but N·Q is outside G by contract, so it
is multiplicity convergence, not a G bypass"; "Unprotected results": the aggregate control,
`native_transport_max_concurrent_connections`, exists but ships disabled). The case keeps its pick-time ID `B27`; if the
readings show a reserve charged and exceeded (K > C for the reserves), the direction is re-read as bypass in §4.
Technique note: [`combo-playbook.md`](../../../combo-playbook.md) (multiplicity step) and
[`default-convergence-playbook.md`](../../../default-convergence-playbook.md). Interpretation: configuration-sizing gap
(a fixed 1 MiB per connection, not derived from the heap, times an unlimited count), not an implementation defect.

Chain at shipped defaults, protocol v5, one-frame requests (envelope ≤ `LARGE_MESSAGE_THRESHOLD` = 131,071 B,
`CQLMessageHandler.java:83`):

1. A client opens *N* v5 connections (no connection limit: `Config.java:289-290`, handler not installed,
   `PipelineConfigurator.java:239-245`; no idle timeout, `native_transport_idle_timeout` 0, `Config.java:139`).
2. On each connection it keeps *W* = 7 requests of body size *M* = 125,074 B in flight (875,518 B; with one re-send
   arriving before the previous response's release, 8 × *M* = 1,000,592 B ≤ 1,048,576 B). Every
   `acquireCapacityAndQueueOnFailure` (`CQLMessageHandler.java:223`, `:693-697`) succeeds on the exclusive queue
   (`AbstractMessageHandler.java:418-423`): **no reserve is charged** (`Client.RequestsSize` = global reserve in use,
   `ClientMetrics.java:129`, stays 0), no refusal, no backpressure branch (`:226-264` not entered), no "bytes in flight"
   warning.
3. The request is decoded (`composeRequest`, `CQLMessageHandler.java:372`; the bound value copied to a heap `byte[]` by
   `CBUtil.readValue`, `CBUtil.java:443-450`) and queued on `Native-Transport-Requests` (128 threads, unbounded queue);
   its capacity is released only after the response is flushed (`release`, `:500-510`). Queued requests are not shed by
   bytes or age at intake (`native_transport_queue_max_item_age_threshold` = `Double.MAX_VALUE`, `Config.java:1394`); one
   older than `native_transport_timeout` (12 s, `:1399`) is answered "timed out before it could start" when dequeued and
   the client re-sends it.
4. The node processes requests more slowly than they arrive (expensive filtering reads, below), so ≈ *N*·*W* decoded
   requests sit on the heap: ≈ *N* × 0.875 MB, each connection within its contract, the reserves untouched. When that
   exceeds the free heap: `java.lang.OutOfMemoryError: Java heap space`, the shipped `-XX:+HeapDumpOnOutOfMemoryError`
   (`conf/jvm-server.options:120`) dump, then the shipped `-XX:OnOutOfMemoryError="kill -9 %p"` (`conf/cassandra-env.sh:209`).

The slow request is B10's, unchanged: `SELECT pk FROM ks.t WHERE pk = 0 AND v = ? ALLOW FILTERING` at `ONE` over one
partition of *R* = 200,000 rows, the bound value a 125,000-byte blob (never matches). Filtering is allowed at defaults
(`allow_filtering_enabled: true`); the default authenticator makes the client a superuser, so no guardrail applies.

Why *W* = 7 and many connections (client behaviour, not a server setting): it is the shape of many small, well-behaved
clients (application instances or pools with a few requests in flight each) rather than one aggressive client; it keeps
each connection inside its own contract so the result cannot be B10's refusal path.

### 2.2 Protection map

| Domain | Holder (allocation, owner, release) | Counter (*K*) | Contract limit (*C*) | At the limit | Scope / multiplicity |
|---|---|---|---|---|---|
| D1 decoded one-frame requests (claimed) | `QueryMessage` + `QueryOptions` value: heap `byte[]` copy per request (`CBUtil.java:443-450`), owned by the NTR task from decode until the response flush (`CQLMessageHandler.java:500-510`) | per-connection `queueSize` (not exposed; bounded by the client window by construction) | **per connection: Q = 1 MiB** (`Config.java:302`); the reserves cover only bytes **beyond** Q (`AbstractMessageHandler.java:418-436`) | within Q: admitted, uncharged elsewhere; beyond Q: charged to reserves (never reached here) | per connection × *N* |
| D1-agg aggregate of D1 over connections | same objects | global reserve in use (`Client.RequestsSize`), per-IP reserve | **none for Σ Q**: G = heap/10 and E = heap/40 cover only the excess; the count control `native_transport_max_concurrent_connections` / `_per_ip` = −1 (**disabled**) | — | node; *N* unlimited |
| D2 NTR executor queue | `Native-Transport-Requests` SEP queue entries referencing D1 | none (count unbounded) | none in bytes; age shed at dequeue after 12 s | expired → error response at dequeue | node; alias of D1, not added |
| D3 connection objects | Netty channel, pipeline, `CQLMessageHandler`, `Flusher`, decoders (heap); socket buffers (kernel) | none | count control disabled | — | per connection; ≥ 1,285.5 B heap idle (stage 4), more once STARTUP completes; measured in arm X |
| D4 frame / networking buffers (direct) | `BufferPool` networking pool, Netty read buffers; a contained frame's buffer is released after decode | pool `UsedSize`/`OverflowSize`, direct `MemoryUsed` | `MaxDirectMemorySize` | direct OOM | node; recorded, not claimed |
| D5 read path (transient) | `ReadStage` (32) iterators over the *R*-row partition | none | `concurrent_reads` 32 | queue | garbage, not live beyond the read |
| D6 baseline | schema, key cache (≤ min(5 % heap, 100 MiB)), system tables | own caps | own caps | own policy | node |

Claimed: in every connection U(D1)/conn ≤ Q (≤ 8 requests), **K(reserves) = 0**, and Σ_conn U(D1) + D3 + baseline >
heap → convergence by multiplicity with the aggregate control disabled (unprotected configuration). Nothing is written
after the data set is loaded, so no memtable growth.

### 2.3 Configuration and budget audit

**Constraints (V6), all at shipped defaults in every test, control and search arm; none set in `cassandra.yaml`**
(resolved at heap *H*):

| Setting | Default | Resolved at H = 2 / 4 / 8 GiB |
|---|---|---|
| `native_transport_receive_queue_capacity` | 1 MiB (`Config.java:302`) | 1,048,576 B (intervention-support arm I2b only: 0 B) |
| `native_transport_max_request_data_in_flight_per_ip` | null → heap/40 (`DatabaseDescriptor.java:656`) | 53,687,091 / 107,374,182 / 214,748,364 B |
| `native_transport_max_request_data_in_flight` | null → heap/10 (`:651`) | 214,748,364 / 429,496,729 / 858,993,459 B |
| `native_transport_max_concurrent_connections` / `_per_ip` | −1 / −1 (`Config.java:289-290`) | unlimited (intervention arm I2 only: 1,000) |
| `native_transport_throw_on_overload` | false (`:1393`) | false (clients send no `THROW_ON_OVERLOAD`, except I2b) |
| `native_transport_max_threads` | 128 (`:283`) | 128 |
| `native_transport_timeout` | 12 s (`:1399`) | 12 s |
| `native_transport_queue_max_item_age_threshold` | `Double.MAX_VALUE` (`:1394`) | off |
| `native_transport_idle_timeout` | 0 ms (`:139`) | off |
| `native_transport_rate_limiting_enabled` | false | false |
| `native_transport_max_message_size` | null → derived | record the resolved value from `system.log` |
| `read_request_timeout` | 5000 ms | 5 s |
| `concurrent_reads` | 32 | 32 |
| `allow_filtering_enabled` | true | true |

**yaml diff from the shipped file (environment only):** `cluster_name: oom-b27`, `listen_address`/`rpc_address`
127.0.0.1, seeds `127.0.0.1:7000`, `data_file_directories`, `commitlog_directory`, `hints_directory`,
`saved_caches_directory`, `cdc_raw_directory` under the run folder, `auto_snapshot: false`. The run script fails the run
if the yaml of a test, control or search arm contains any key of the table above; I2 adds exactly
`native_transport_max_concurrent_connections: 1000`, I2b exactly `native_transport_receive_queue_capacity: 0B`.

**Supporting environment settings (disclosed, not constraints):** `ulimit -n 100000` for the node and each client JVM
(the project's packaging recommends a high `nofile`; the node's hard limit is 1,048,576); clients on the victim node,
one client IP (127.0.0.1); before each run the client-side TIME-WAIT count plus the planned *N* must be ≤ 26,000 (port
range 32768–60999 = 28,232 ports), else wait (≤ 120 s, then record).

**Budgets (V7).** The node the result claims to represent: a 2–8 GiB-heap Cassandra node (a common container or VM
size). What `cassandra-env.sh` would resolve on `pc72` (125 GiB): heap min(½ RAM, 31,744 MiB) = 31,744 MiB, direct
15,872 MiB; recorded, not used. Chosen: **heap 2 GiB (ideal) with `MaxDirectMemorySize` 2 GiB**; upward search **heap
4 GiB (direct 2 GiB)** and **heap 8 GiB (direct 4 GiB = heap/2, the `cassandra-env.sh` heap:direct ratio)**. All ≥ 512
MiB → V7 met by the standing rule (2026-11-11), no per-case review. JVM: OpenJDK 11.0.33, G1 (shipped
`jvm11-server.options`), shipped GC log, heap dump on OOM and `OnOutOfMemoryError=kill -9 %p`, `-XX:+AlwaysPreTouch`
(shipped, `jvm-server.options:128`).

**Containment, not a budget.** The node runs in `systemd-run --user --scope -p MemoryMax=<H + direct + 6 GiB> -p
MemorySwapMax=0` (10 / 12 / 18 GiB) only to protect the host and the clients. A run whose scope records `oom_kill` > 0 or
`memory.events max` > 0 is **invalid** (not a reading) and is repeated once with MemoryMax + 4 GiB (B10's T8 lesson: the
heap dump's page cache counts against the scope). No container limit is part of the claim.

### 2.4 Ceiling arithmetic (heap 2 GiB)

- Contract per connection: Q = 1,048,576 B. Contract aggregate for *N* connections: **N·Q + G** (G = heap/10 =
  214,748,364 B), with *N* unlimited → **no finite ceiling**; convergence is feasible (protocol feasibility check).
- Per-connection window here: *W*·*M* = 7 × 125,074 = **875,518 B** (83.5 % of Q).
- Baseline live heap ≈ 0.18 GB idle (B10 `idle`) + key cache ≤ 0.1 GB → ≈ 0.3 GB; D3 ≥ 1.3 KB per connection (idle,
  stage 4), assumed ≤ 50 KB per handshaken v5 connection (measured in arm X).
- **Test *N* = 3,500:** window 24,500 requests = **3,064,313,000 B (2.85 GiB)**, contract allowance 3.67 GB, against a
  heap of 2.15 GB. B10's T2 died at 15.2–15.4 k resident 125 KB requests (1.91–1.93 GB); here that is reached with
  ≈ 2,200 connections' windows resident (63 % of *N*·*W*) → **heap OOM** predicted.
- **Control *N* = 1,000:** window 7,000 requests = 875,518,000 B (0.82 GiB); + baseline 0.3 + D3 ≤ 0.05 → ≤ 1.23 GB =
  57 % of the heap (43 % margin ≥ the 30 % target). B10's C2 (8,192 such requests, 1.03 GB) survived 3/3 with post-GC
  ≤ 1.22 GB on the same node, build and data → no OOM predicted.
- **Search:** *H* = 4 GiB, *N* = 7,000 (49,000 requests, 6.13 GB window); *H* = 8 GiB, *N* = 14,000 (98,000 requests,
  12.26 GB window). The reserves stay at 0 in every arm, so the whole held amount is outside them.
- Direct (D4, not claimed): a connection idle-waiting with its window sent holds no partial frame; worst case ≈ *N* ×
  136 KiB (0.49 GB at 3,500, 1.9 GB at 14,000, hence direct 4 GiB at *H* = 8 GiB).

### 2.5 Workload and environment

**Node: `pc72` only** (x86_64, 40 cores, 125 GiB RAM, cgroup v2, Ubuntu 22.04, kernel 5.15, OpenJDK 11.0.33). Read-only
check 2026-11-24 05:47 EST: load 0.08, no Java process, 113 GiB free, `/mydata` 707 GiB free, `ulimit -Hn` 1,048,576,
`threads-max` 1,030,165, `pid_max` 4,194,304, user `TasksMax` infinity, user-slice `pids.max` 339,954, `somaxconn` 4096,
ports 32768–60999, `/mydata/s4/cassandra-base` built. `/mydata/s4/` also holds `3b-B21`, `3b-R22` (other cases; do not
touch) and a `NODE-LOCK/owner` reading "phase1-hadoop o7 Mon Nov 23 11:58:47 PM MST 2026": stage 2 starts only when the
coordinator has confirmed the node is free (every node carried such a lock at design time; `pc82` also had Hadoop JVMs
running). B10's harness and data shape were proven on this node. Victim and clients both on `pc72` (recorded deviation
from "clients on other nodes", as in B10: one client IP, and the per-IP reserve is not involved anyway because nothing is
charged to it). One measured experiment at a time; nothing else runs on `pc72`.

**Folders.** Run base `pc72:/mydata/s4/b27/`: `cassandra/` = `cp -a /mydata/s4/cassandra-base` (never run `ant` in it),
`classes/`, `harness/`, `node/` (conf, data), `data.pristine-<R>/`, `logs/<run-id>/`. Repo: `harness/` in this case
folder; small excerpts in `logs/`.

**Harness to build (stage 2).**
- From B10's harness ([`../native_transport_receive_queue_capacity--refused-v5-request-uncharged-drift/harness/`](../native_transport_receive_queue_capacity--refused-v5-request-uncharged-drift/harness/)):
  `Jmx.java`, `flood-logback.xml`, `hprof-histo.py` unchanged; `make-node-yaml.sh` unchanged except `cluster_name` and an
  optional extra-key argument for I2/I2b; `b10-run.py` adapted as `b27-run.py` (steps below; keep its 150-s histogram
  timeout, its scope headroom variable and its process check that ignores the launching command line).
- `NativeFlood.java` copied with **two changes only**, used in every arm: (a) each `connect` is wrapped in try/catch: on
  failure (the server closing the channel, or `SimpleClient`'s 10-s `TIMEOUT_SECONDS`) print `conn <i> refused <reason>`,
  count `refused`, shut that client's event loop group, and continue; the per-second line adds `refused=` and
  `connected=`; (b) `--window 0` is allowed (connect, STARTUP, then hold idle). Compile as B10 (`javac -d classes Jmx.java`;
  `javac -nowarn -d classes -cp "cassandra/build/classes/main:cassandra/build/lib/jars/*" NativeFlood.java`).
- Client JVMs: ≤ 500 connections each, `java -Xmx1g -XX:MaxDirectMemorySize=2g -Xss512k -Dio.netty.eventLoopThreads=1
  $(grep -v '^#' cassandra/conf/jvm11-clients.options) -Dlogback.configurationFile=<flood-logback.xml> -cp
  classes:cassandra/build/classes/main:cassandra/build/lib/jars/'*' org.apache.cassandra.transport.NativeFlood --host
  127.0.0.1 --connections <n_j> --window <W> --value-bytes 125000 --seconds 240 --throw <false|true> --retry-ms 100`,
  under `ulimit -n 100000`, started together, each to `logs/<run-id>/flood-<j>.out`.
- No Byteman agent, no patch, in any arm.

**Data set (once).** As B10: node at 2 GiB on an empty `node/data`; `CREATE KEYSPACE ks WITH replication =
{'class':'SimpleStrategy','replication_factor':1}; CREATE TABLE ks.t (pk int, ck int, v blob, PRIMARY KEY (pk, ck));`
load *R* = 200,000 rows `(0, i, 16 random bytes)` with `cqlsh COPY` (fallback: a SimpleClient INSERT loop, 64 in
flight); `nodetool flush ks t`, `nodetool drain`, stop, `cp -a node/data data.pristine-200000`. Every run restores
`node/data` from it (clean start = fresh JVM, same data files).

**Calibration (not a reading; once, H = 2 GiB, *N* = 500, *W* = 7, 1 JVM, 60 s).** Accept when (a) NTR `PendingTasks`
≥ 0.7 × 3,500 = 2,450 at 30–60 s; (b) `Client.RequestsSize` = 0 at every poll and `system.log` has no "breached
limit(s) on bytes in flight" line; (c) client `connected` = 500, `refused` = 0. If (a) fails, double *R* (≤ 800,000; ≤ 2
rounds; reload the data set). If (b) fails, set *W* = 6 (750,444 B) for every arm and raise every *N* by 7/6 (test
4,100, control 1,170, I2 cap 1,170, search 8,200 / 16,400), recorded as a dated amendment before any reading.

**Arms (each run a clean start; load phase 240 s from the first client `start ms=`).**

| Arm | Heap / direct | *N* (client JVMs × conns) | *W* | Server change | Client option | Runs | Purpose |
|---|---|---|---|---|---|---|---|
| `T2` test | 2 / 2 GiB | 3,500 (7 × 500) | 7 | none | default | 3 | failing condition (V1) |
| `C2` control | 2 / 2 GiB | 1,000 (2 × 500) | 7 | none | default | 3 | low multiplicity, same payload, data, window and client (V2) |
| `I2` intervention | 2 / 2 GiB | 3,500 attempted (7 × 500) | 7 | `native_transport_max_concurrent_connections: 1000` | default | 3 | bound multiplicity (V4) |
| `X2` support | 2 / 2 GiB | 3,500 (7 × 500) | 0 | none | default | 1 | connection count alone (D3), no requests held |
| `I2b` support | 2 / 2 GiB | 3,500 (7 × 500) | 7 | `native_transport_receive_queue_capacity: 0B` | `THROW_ON_OVERLOAD` | 1 (optional) | charge every byte to the reserves: attribution to "outside the reserves" (not V4; skipped if the node rejects 0B, recorded) |
| `T4` search | 4 / 2 GiB | 7,000 (14 × 500) | 7 | none | default | ≤ 3 | larger budget |
| `T8` search | 8 / 4 GiB | 14,000 (28 × 500) | 7 | none | default | ≤ 3 | larger budget |

**Pre-declared dose ladder (test condition at 2 GiB):** if `T2` run 1 ends without OOM **and** its peak live
`QueryMessage` count < 0.8 × *N*·*W* (window not resident: client-limited), the test condition moves to *N* = 4,500 (9
JVMs), then 5,500 (11 JVMs); the first that reaches OOM becomes `T2` for all repeats and the attempted *N* of `I2`
(`C2` stays 1,000). If `T2` run 1 ends without OOM with the window resident, do not escalate: record and continue.

**Steps of `b27-run.py` (per run).**
1. Check no `CassandraDaemon`/`NativeFlood` runs; TIME-WAIT check (§2.3); restore `node/data`; regenerate `node/conf`;
   check the yaml keys per arm (§2.3).
2. Start in the scope (§2.3) with `ulimit -n 100000`, env `CASSANDRA_CONF`, `CASSANDRA_LOG_DIR`,
   `CASSANDRA_HEAPDUMP_DIR` = `logs/<run-id>`, `MAX_HEAP_SIZE=<H>G`, `MAX_DIRECT_MEMORY_SIZE=<D>G`, `HEAP_NEWSIZE` unset.
   Wait (≤ 300 s) for UN and `statusbinary` running. Read back `-Xmx`, `-XX:MaxDirectMemorySize`, `UseG1GC`,
   `HeapDumpOnOutOfMemoryError`, `OnOutOfMemoryError` from `/proc/<pid>/cmdline`, scope `memory.max`/`memory.swap.max`,
   and from `system.log` the resolved receive queue capacity, in-flight reserves, connection limits, message size.
3. Warm-up (not a reading): NativeFlood *N* = 1, *W* = 7, 10 s; 20 s idle.
4. Idle readings: `jcmd <pid> GC.class_histogram` (`histo-idle.txt`); one JMX `get` of every poll bean.
5. Pollers every 2 s (epoch ms): `java.lang:type=Memory HeapMemoryUsage`; `java.nio:type=BufferPool,name=direct`
   `MemoryUsed`/`Count`; networking pool `UsedSize`/`OverflowSize`; `type=Client,name=RequestsSize` (global reserve in
   use), `connectedNativeClients`, `PausedConnections`, `RequestDiscarded`, `TimedOutBeforeProcessing`; NTR
   `PendingTasks`/`ActiveTasks`; ReadStage `PendingTasks`; scope `memory.current`, `memory.events`; **server-side
   established connections** `ss -Htn state established '( sport = :9042 )' | wc -l`.
6. Load: start the arm's client JVMs together; *t* = 0 at the first `start ms=`.
7. Histograms (`GC.class_histogram`, start/end ms recorded): *t* = 20 s, then every 20 s (*H* = 2 GiB) or 30 s
   (*H* ≥ 4 GiB) while the node lives (each forces a full GC: instrumentation overhead, recorded).
8. Endpoint watch every 1 s: PID gone → `stdout.txt` first `java.lang.OutOfMemoryError` (type), `Dumping heap to`,
   `OnOutOfMemoryError`; `system.log` first `OutOfMemoryError`/`ERROR` with thread; scope `memory.events`.
9. End at *t* = 240 s (or 30 s after node death): stop clients (kill after 30 s if the node is gone), stop the node
   (`nodetool stopdaemon`, then kill), check no `CassandraDaemon`/`NativeFlood` left, stop pollers.
10. `summary.txt` + `run.json`: arm, *H*, *D*, *N* attempted/connected/refused, *W*, *M*, *R*; endpoint and time; per
    histogram `QueryMessage` count and `[B` bytes; server connections max; **QM per connection** = QM / connections;
    U(D1) = max QM × *M*; `[B` − idle `[B`; K = max `RequestsSize`; breached-limit lines (count); NTR pending max;
    post-GC heap (last 5 `->` values of `gc.log`); GC pause fraction over the last 60 s before the endpoint; client
    totals (`sent ok warned ovl_bytes ovl_other err refused`) and `ok`/s; direct max; scope max; hprof name and size;
    one `EXPECTED:` line per prediction of §2.7.

### 2.6 Instruments

- **U (independent of K):** live `QueryMessage` count × *M* and `[B` above idle from `GC.class_histogram` (live objects
  after full GC); NTR `PendingTasks` as the continuous proxy; post-GC heap from `gc.log`; the OOM hprof (class histogram
  by `hprof-histo.py`; holder chain `byte[125000]` ← `QueryMessage` ← `Dispatcher$RequestProcessor`).
- **Per-connection U:** QM / server-side established connections (`ss`), each histogram; must stay ≤ 8 (= the contract
  Q / *M* rounded down) for the claim "each connection within its contract".
- **K:** `Client.RequestsSize` (global reserve in use; the per-IP reserve is charged together with it,
  `AbstractMessageHandler.java:428-436`), predicted 0; the per-connection `queueSize` is not exposed without Byteman and is
  bounded by the client window by construction (*W*·*M* ≤ Q).
- **Path evidence (not B10's):** `system.log` has no "breached limit(s) on bytes in flight" line; client `warned` = 0,
  `ovl_bytes` = 0; `RequestDiscarded` +0. In I2: server connections ≤ 1,000, client `refused`, the
  "Exceeded maximum native connection limit" ERROR line. In I2b: `ovl_bytes` > 0 = `RequestDiscarded`.
- **D3:** arm X2's live heap above idle / connections; `connectedNativeClients`.
- **Others:** heap used, direct, networking pool, `TimedOutBeforeProcessing`, ReadStage pending, scope memory, client
  per-second counters; one host clock.

### 2.7 Predicted response and stopping budget

| # | Arm | Prediction |
|---|---|---|
| P1 | T2, C2, X2, T4, T8 | `RequestsSize` = 0 at every poll (tolerance ≤ 1 × *M*); no "breached limit" line; `warned` = 0, `ovl_bytes` = 0, `RequestDiscarded` +0; `refused` = 0 |
| P2 | T2, C2, T4, T8 | QM / server connections ≤ 8 at every histogram (each connection within Q) |
| P3 | T2 | NTR pending ≥ 0.5 × *N*·*W* (12,250) within 90 s; live QM rises to ≥ 14,000 (≥ 1.75 GB) before the endpoint: **U(D1) ≥ 8 × G (heap/10) with K = 0** |
| P4 | T2 | **heap OOM** (`java.lang.OutOfMemoryError: Java heap space`, hprof, JVM killed) **3/3** within 180 s of *t* = 0; scope `oom_kill` 0 |
| P5 | T2 | OOM dump: `byte[125000]` ≥ 80 % of the shallow heap, one per `QueryMessage`/`RequestProcessor` (counts within 1 %) |
| P6 | C2 | QM plateau 7,000 ± 10 %; post-GC heap ≤ 1.35 GB; no OOM 0/3 in 240 s; GC pause fraction over the last 60 s < 90 % |
| P7 | I2 | server connections ≤ 1,000; client `refused` ≥ 2,400; QM ≤ 7,000 + 128 at every histogram; no OOM 0/3; `ok`/s ≥ 0.5 × C2's (useful work continues) |
| P8 | X2 | live heap above idle ≤ 0.2 GB (≤ 57 KB per connection); no OOM |
| P9 | I2b | QM ≤ E/*M* + 128 ≈ 557; `ovl_bytes` > 0; no OOM |
| P10 | T4, T8 | heap OOM if the window is resident (QM ≥ (H − 0.3 GB)/*M*); otherwise the plateau and client rate are recorded and the budget is reported as client-limited, not as a boundary of the system |
| P11 | all | direct `MemoryUsed` ≤ *N* × 136 KiB + 0.1 GB and < 0.5 × U(D1) (D4 does not carry the claim) |

**Stopping budget.** Load phase 240 s per run (1.3 × the 180-s prediction); no escalation after an OOM; at most 3 runs per
arm at 2 GiB plus at most the 2 dose-ladder steps; X2 and I2b one run each; search ≤ 3 runs at each heap, `T8` only if
`T4` reached OOM. Invalid runs (start-up failure, scope `oom_kill`/`max`, client crash before *t* = 60 s, TIME-WAIT check
failed) are repeated once each. Expected wall time ≈ 3 h 15 min: harness, copy, compile, smoke 40 min; data set +
calibration 20 min; 11 runs at 2 GiB × ≈ 7 min (connect ≈ 0.5, start 1, warm-up 0.5, load 4, stop/summary 1) ≈ 80 min;
search 6 runs ≈ 50 min (`T8`'s 28 client JVMs and 8 GiB dumps); stop/cleanup, excerpts, §3–§4, write-backs 25 min. If
time runs short, drop in this order: `T8` repeats, `T8`, `I2b`, `T4` repeats, `T4`. The 2 GiB set (T2, C2, I2 × 3)
is the minimum; without it the case ends as `retry` with the reason "time".

**Resources on `pc72`:** RAM — node scope ≤ 10 / 12 / 18 GiB + clients ≤ 28 × ≈ 1.5 GiB ≈ 42 GiB < 125 GiB; threads —
≈ 2 per client connection (reader + event loop) ≤ 28,000 + JVM threads, below `threads-max` and `pids.max`; ports — ≤
14,000 client ports + TIME-WAIT ≤ 26,000; disk — hprofs 2 GB × ≤ 5 + 4 GB × ≤ 3 + 8 GB × ≤ 3 ≈ 46 GB of 707 GB free.

### 2.8 Controls and intervention

- **V2 matched control:** `C2`: same build, heap, direct, data, statement, value, *W*, client code and JVM sizing, *N* =
  1,000 (low multiplicity, the convergence shape's nearest surviving condition), 3 runs from clean starts.
- **V4 intervention:** `I2`: identical to `T2` (3,500 connections attempted, same clients) with the aggregate control
  that ships disabled set: `native_transport_max_concurrent_connections: 1000` (a constraint change, allowed in an
  intervention arm, V6; precedent U2's `512`). It bounds multiplicity, the claimed cause; 3 runs; throughput and refusals
  recorded so a starved arm is not mistaken for protection.
- **Supporting:** `X2` (connections alone, no held requests, rules out D3 as the cause); `I2b` (every byte charged to the
  reserves, with the throwing client so B10's refusal path cannot carry it: shows the reserves would bound the same
  load), one run each; not V2/V4 evidence.

### 2.9 Outcome rows (decided before readings)

| Readings | Verdict / status |
|---|---|
| P1–P7 hold; `T2` OOM 3/3, `C2` 0/3, `I2` 0/3; K = 0 and QM/conn ≤ 8 in `T2` | **true positive**, `verified-OOM · deployment` (convergence by multiplicity, unprotected configuration: connection limits −1); largest failing heap reported with n/N |
| as above but K > 0 or a "breached limit" line in `T2` (the reserves were reached) | the refusal path (B10) may carry part of the load: report, re-read the direction; **true positive** only if QM attributable within Q per connection still exceeds the heap, else **retry** with *W* = 6 |
| `T2` sustained GC service loss (≥ 90 % in pauses over ≥ 60 s) without OOM 3/3 | **retry**, `verified-gap · service-loss · deployment`; better design: larger *N* or longer load |
| `T2` OOM < 3/3 | report n/N; expand to 5 runs if time, else **retry** |
| window never resident (QM < 0.5 × *N*·*W*) at the top of the dose ladder | **retry** (load not reached): more client JVMs or a second node as client |
| window resident ≥ heap − baseline and no OOM, no service loss, also at `T4`/`T8` | **false positive** only if the held bytes stop below the budget at every tested heap; otherwise **retry** |
| `C2` or `I2` reaches the OOM | V2/V4 unmet → **retry**, attribution gap stated |
| OOM is direct-buffer, or a scope kill | not the claimed endpoint: recorded; the run is invalid for V1 and repeated once |
| node refuses connections below the planned *N* in a test arm (fd, port, backlog) | environment limit, not a default control: fix and repeat; if it is a default capacity control, **false positive** |

`sha256 of §1–§2 at freeze: a2aa739298b0cc277749840e31602b0995ba559443fb876852f5a21fc97fb15f` · computed over the lines from `## 1. Candidate` up to, not including, this line
(`sed -n '/^## 1\. Candidate/,/^`sha256 of §1–§2 at freeze/p' <file> | sed '$d' | sha256sum`). Amendments after the
freeze: dated, with reason.

## 3. Runs (stage 2)

*Filled 2026-11-24 ≈ 21:30 EST by a fresh OOM-agent session (attempt 3), which did not write the design. Freeze hash
checked before any run: the §1–§2 sha256 recomputed with the command above is
`a2aa739298b0cc277749840e31602b0995ba559443fb876852f5a21fc97fb15f` = the frozen value. Node lock
`pc91:/mydata/s4/NODE-LOCK` held 20:11 EST → end of run; released at the end.*

### 3.0 Deviations and interruptions (dated)

| # | Date (EST) | Deviation | Effect |
|---|---|---|---|
| D1 | 2026-11-24 ≈ 12:06–16:25 | **Attempt 1 interrupted (owner stop ≈ 16:25).** A first stage-2 session built the harness in `harness/` (files dated 12:06–16:09) and ran the whole run list on `pc82` (not the design's `pc72`): CAL, T2 ×3, C2 ×3, I2 ×3, X2, I2b, T4 ×3 (invalid: scope `max` > 0, redone as T4-r1b…r3b at +4 GiB headroom), T8-r1, T8-r2; it was stopped during T8-r3, before §3 was written. | **Not used as evidence**; every run was repeated from a clean start on `pc91` (below). For the record only, its summaries agree with this attempt (T2 OOM 3/3 at 28–152 s, C2 0/3, I2 0/3 with 2,500 refused, X2 / I2b no OOM, T4 OOM 3/3 valid, T8 OOM 2/2 with scope `max` > 0). Its raw data (≈ 49 GB incl. 10 hprofs) remain at `pc82:/mydata/s4/b27/`: not touched by this session; left for the owner/filer to delete. |
| D2 | 2026-11-24 ≈ 18:03 | **Attempt 2 interrupted (API usage limit ≈ 18:03).** | No trace on `pc91` (no `b27` folder, no lock, no Java process at 20:11) and no change to the case file; nothing reused. |
| D3 | 2026-11-24 20:10 | **Node `pc91`** (coordinator's assignment) instead of the design's `pc72`: same class and site (CloudLab UMass `jason92-326665`, x86_64, 125 GiB, Ubuntu 22.04, kernel 5.15.0-203, cgroup v2, OpenJDK 11.0.33, `/mydata/s4/cassandra-base` = the 5.0.9 build copied from `pc96`); 32 cores (Xeon E5-2667 v2) instead of 40. | Environment only. Victim and clients on `pc91`, one client IP (as designed). Nothing else ran on `pc91` (other cases' folders `3b-B9`, `3b-C10`, `3b-S2`, `b26`, `r23` idle, not touched). |
| D4 | 2026-11-24 (attempt 1, before any reading; kept) | `NativeFlood` connects on `--connect-threads 64` threads (dated amendment in its header), **same value in every arm**, because a refused connect (I2) costs `SimpleClient`'s 10-s timeout. | Client behaviour only; matched across arms. |
| D5 | 2026-11-24 20:15, before the T4/T8 readings of this attempt | **Containment headroom** (not a budget, §2.3): T2/C2/I2/X2/I2b at the design's H + D + 6 GiB (10 GiB); T4 and T8 started at the "+ 4 GiB" re-run headroom and above: T4 at 16 GiB (H + D + 10), T8 at 30 GiB (H + D + 18), because in attempt 1 the OOM dump's page cache filled the 12-GiB T4 and the 22-GiB T8 scopes (`memory.events max` > 0 → invalid). | No container limit is part of the claim. Every run of this attempt: scope `oom_kill` 0 and `max` 0 → all valid, no re-runs. Scope peaks: 6.4–6.9 GiB (T2), 14.2–14.5 GiB (T4), 24.3–24.5 GiB (T8). |
| D6 | run time | At H = 2 GiB the T2 live histogram at *t* = 20 s did not complete (jcmd in GC thrash for 65 s, empty file; also T4-r3 and the second T4/T8 histogram). JMX polls stall in the same thrash, so NTR `PendingTasks` is under-read in T arms. | U for T arms comes from the **OOM hprof** (`hprof-histo.py`) and, where they completed, the 20–21-s histograms of T4/T8. Per-connection QM in T arms = hprof QM / 3,500 (7,000; 14,000) connections, all established (`ss`) at the endpoint. |
| D7 | harness | `b27-run.py`: host label in the "after stop" note now prints the hostname (cosmetic); new driver `harness/run-pc91.sh` (the whole run list in one detached driver, PID kept in `pc91:/mydata/s4/DRIVER-<agent>.pid`). `run-2g-set.sh`, `run-search-set.sh`, `run-search-redo.sh` are attempt 1's drivers (kept, not used here). | none on the mechanism |

### 3.1 Environment and configuration readback

- Node `pc91` (`node0.jason92-326665`), 32 × Xeon E5-2667 v2, 125 GiB, 8 GiB swap (0 for the scope), cgroup v2, Ubuntu
  22.04, kernel 5.15.0-203-generic, OpenJDK 11.0.33, G1 (shipped `jvm11-server.options`). Run base
  `pc91:/mydata/s4/b27/` (`cassandra/` = `cp -a /mydata/s4/cassandra-base`, never rebuilt; `classes/` = `Jmx`,
  `NativeFlood` compiled per §2.5). Load 0.00 and no Java process before the first run.
- JVM readback (every run, `/proc/<pid>/cmdline`): `-Xms<H> -Xmx<H> -XX:MaxDirectMemorySize=<D> -XX:+UseG1GC
  -XX:+HeapDumpOnOutOfMemoryError -XX:HeapDumpPath=<logs/run> -XX:OnOutOfMemoryError=kill -9 %p`, jamm agent only (no
  Byteman); scope `memory.swap.max` 0.
- Resolved from `system.log` (every run; test/control/search arms): `native_transport_receive_queue_capacity` 1MiB;
  `native_transport_max_request_data_in_flight` / `_per_ip` null (→ heap/10, heap/40); `native_transport_max_concurrent_connections`
  / `_per_ip` −1; `native_transport_throw_on_overload` false; `native_transport_max_threads` 128; `native_transport_timeout`
  12s; `native_transport_queue_max_item_age_threshold` 1.797E308; `native_transport_idle_timeout` 0ms;
  `native_transport_rate_limiting_enabled` false; `native_transport_max_message_size` null (derived); `read_request_timeout`
  5000ms; `concurrent_reads` 32; `allow_filtering_enabled` true. `make-node-yaml.sh`: "harness adds no §2.3 key" in every
  T/C/X arm; I2 adds exactly `native_transport_max_concurrent_connections: 1000`, I2b exactly
  `native_transport_receive_queue_capacity: 0B` (accepted by the node).
- **Data set** (20:12–20:13 EST): `cqlsh COPY` 200,000 rows in 2.6 s, `count(*)` = 200,000, flush, drain →
  `data.pristine-200000` (5.7 MB); restored before every run.
- **Calibration** (CAL, H = 2 GiB, *N* = 500, *W* = 7, 60 s; not a reading): (a) NTR `PendingTasks` 3,372 at 30–60 s ≥
  2,450 ✓; (b) `RequestsSize` 0 at every poll, no "breached limit" line ✓; (c) connected 500, refused 0 ✓; live QM 3,500 =
  7 / connection. → *R* = 200,000 and *W* = 7 kept; no amendment.
- Dose ladder: T2-r1 reached OOM → no escalation; *N* = 3,500 for all T2 and I2 runs.

### 3.2 Runs (all from clean starts, 2026-11-24 20:16–21:23 EST; `logs/<run>/` holds summary, run.json, polls, histogram heads, hprof histogram, OOM excerpt)

*K* = max global reserve in use (`Client.RequestsSize`, B). QM = live `QueryMessage`. U(D1) = byte[125000] in the OOM
dump (or live QM × *M* from histograms). GC = stop-the-world fraction over the last 60 s before the endpoint.

| Run | *H* / *D* | *N* (conn.) | Endpoint (t from first client start) | QM / connection | U(D1) | *K* | Other readings |
|---|---|---|---|---|---|---|---|
| T2-r1 | 2 / 2 GiB | 3,500 / 3,500 | **heap OOM 85.9 s** | 16,023 / 3,500 = **4.58** | 16,028 × 125,000 = **2.004 GB = 94.0 %** of 2.132 GB shallow | 44 | GC 0.90; refused 0; `breached` 0; warned/ovl_bytes 0; discarded 0; direct ≤ 0.193 GB |
| T2-r2 | 2 / 2 | 3,500 | **heap OOM 46.4 s** | 16,041 → **4.58** | 16,042 × 125,000 = 2.006 GB = 94.0 % | 0 | GC 0.66; same zeros |
| T2-r3 | 2 / 2 | 3,500 | **heap OOM 94.3 s** | 16,008 → **4.57** | 16,028 → 2.004 GB = 93.7 % | 0 | GC 0.98; same zeros |
| C2-r1 | 2 / 2 | 1,000 | none in 240 s | 6,902–7,018 → ≤ 7.02 | live total median 1.03 GB (max 1.73) | 0 | GC 0.38; ok 7,561 (31.5/s); 44,785 "timed out before it could start", 88,578 read timeouts; refused 0 |
| C2-r2 | 2 / 2 | 1,000 | none | ≤ 7.32 | median 0.99 (max 1.54) | 0 | GC 0.41; ok 30.3/s |
| C2-r3 | 2 / 2 | 1,000 | none | ≤ 7.05 | median 0.99 (max 1.84) | 0 | GC 0.38; ok 28.7/s |
| I2-r1 | 2 / 2 | 3,500 att. / **1,000** | none | ≤ 7.23 | median 1.00 (max 1.64) | 0 | refused **2,500**; "Exceeded maximum native connection limit of 1000" ×2; ok 28.2/s; GC 0.42 |
| I2-r2 | 2 / 2 | 3,500 / 1,000 | none | ≤ 7.62 | median 0.99 (max 1.69) | 22 | refused 2,500; ok 19.7/s; GC 0.39 |
| I2-r3 | 2 / 2 | 3,500 / 1,000 | none | ≤ 7.19 | median 0.99 (max 1.35) | 0 | refused 2,500; ok 19.6/s; GC 0.41; `ss` peak 1,072 (sockets accepted then closed by the limit handler; `connectedNativeClients` max 1,000) |
| X2-r1 | 2 / 2 | 3,500, *W* = 0 | none | 0 | live heap +15.5 MB over idle (**4.4 KB / connection**) | 0 | no requests; GC 0.00 |
| I2b-r1 | 2 / 2 | 3,500, queue capacity 0 B, `THROW_ON_OVERLOAD` | none | ≤ 0.12 (QM 422–427) | 427 × *M* = 53 MB | **53,656,746 ≈ E** (heap/40 = 53,687,091) | ovl_bytes 6,382,396 = `RequestDiscarded`; 29 "breached limit" lines; ok 44.1/s |
| T4-r1 | 4 / 2 | 7,000 | **heap OOM 35.0 s** | 32,839 / 7,000 = **4.69** (21-s histogram 32,844 → 4.69) | 4.108 GB = 95.9 % of 4.283 GB | 0 | GC 0.20; zeros as T2; direct ≤ 0.71 GB |
| T4-r2 | 4 / 2 | 7,000 | **heap OOM 67.8 s** | 32,839 → 4.69 | 4.110 GB = 95.9 % | 0 | GC 0.68 |
| T4-r3 | 4 / 2 | 7,000 | **heap OOM 96.6 s** | 32,735 → 4.68 | 4.102 GB = 95.6 % | 0 | GC 0.88 |
| T8-r1 | 8 / 4 | 14,000 | **heap OOM 82.0 s** | 66,099 / 14,000 = **4.72** (21 s: 54,720 → 3.91) | 8.274 GB = 96.3 % of 8.591 GB | 66 | GC 0.27; 76,605 timed out before start; direct ≤ 1.54 GB; ovl_bytes 0, breached 0 |
| T8-r2 | 8 / 4 | 14,000 | **heap OOM 64.2 s** | 66,091 → 4.72 | 8.271 GB = 96.3 % | 264 | GC 0.24; direct ≤ 1.61 GB |
| T8-r3 | 8 / 4 | 14,000 | **heap OOM 85.9 s** | 66,072 → 4.72 | 8.266 GB = 96.2 % | 22 | GC 0.36; direct ≤ 1.57 GB |

**Initiating failure (V5).** Every T run: `stdout.txt` "java.lang.OutOfMemoryError: Java heap space", "Dumping heap to
…hprof", then the shipped `OnOutOfMemoryError="kill -9 %p"`; the JVM is killed before Cassandra logs the error, so no
thread/stack is printed (as in B10; T8 also shows `epollEventLoopGroup` "Retried waiting for GCLocker too often
allocating 92–123 k words" just before). The hprof histogram supplies the holder: `byte[125000]` 93.7–96.3 % of the
shallow heap in all nine dumps, one per `QueryMessage` / `QueryOptions$DefaultQueryOptions` / `Envelope` /
`Dispatcher$RequestProcessor` (counts within 0.4 %; T8 `Envelope` +2–5 %).

**Predictions (§2.7).**

| # | Result |
|---|---|
| P1 | ✓ *K* ≤ 264 B (≤ 1 × *M*) in T2, C2, X2, T4, T8 (0 in 11 of 16 runs); "breached limit" 0; warned 0; ovl_bytes 0; `RequestDiscarded` +0; refused 0 |
| P2 | ✓ QM / connection ≤ 7.62 in C2/I2 histograms and 4.57–4.72 at the OOM in T2/T4/T8 (≤ 8 everywhere) |
| P3 | ✓ in part: QM at the OOM 16,008–16,041 ≥ 14,000; U(D1)/G = 2.004 GB / 214.7 MB = **9.3** ≥ 8; ✗ NTR `PendingTasks` max read 8,371–9,828 < 12,250 (JMX polls stalled in the GC thrash, D6; the dumps hold ≈ 16,000 queued `RequestProcessor`s) |
| P4 | ✓ heap OOM 3/3 within 180 s (46–94 s); scope `oom_kill` 0, `max` 0 |
| P5 | ✓ `byte[125000]` 93.7–94.0 % of the shallow heap; one per QM / RequestProcessor (within 0.1 %) |
| P6 | ✓ in part: QM plateau 6,902–7,324 (7,000 ± 5 %); no OOM 0/3; GC 0.38–0.41 < 0.9; live heap median 0.99–1.03 GB (46–48 % of 2.15 GB) ✓, but single histograms reached 1.54–1.84 GB (C2-r3 at 181 s: 1.55 M `BTreeRow`/`ArrayCell`/iterator objects of in-progress filtering reads, D5's transient read path) ✗ against "≤ 1.35 GB" |
| P7 | ✓ in part: `connectedNativeClients` ≤ 1,000; refused 2,500 each; no OOM 0/3; ok/s 28.2 / 19.7 / 19.6 ≥ 0.5 × C2's mean 30.2; ✗ QM max 7,189–7,621 slightly above 7,128 (still ≤ 8 per connection, the one-re-send overlap of §2.1 step 2) |
| P8 | ✓ +15.5 MB over idle (4.4 KB / connection) ≤ 0.2 GB; no OOM |
| P9 | ✓ QM ≤ 427 ≤ 557; ovl_bytes 6,382,396 > 0; no OOM; the per-IP reserve full (*K* = E) |
| P10 | ✓ T4 heap OOM 3/3 (QM 32.7–32.9 k ≥ (H − 0.3 GB)/*M* = 31.9 k); T8 heap OOM 3/3 (QM 66.1 k = 99.7 % of (H − 0.3 GB)/*M* = 66.3 k: the baseline is below the assumed 0.3 GB) |
| P11 | ✓ direct ≤ 0.193 / 0.724 / 1.610 GB vs *N* × 136 KiB + 0.1 GB = 0.59 / 1.08 / 2.05 GB, and < 0.5 × U(D1) |

**Stopping budget.** 17 runs + CAL in 67 min of load; no invalid run, no repeat, no escalation after an OOM; T8 run because
T4 reached OOM. Wall time of this attempt ≈ 1 h 20 min.

**Clean-up (21:23–21:27 EST).** After each run the driver stopped clients and node and checked none remained; at the end
no `CassandraDaemon`, `NativeFlood`, `jcmd`, driver or `oom-b27-*` scope on `pc91`. Deleted: 9 hprofs (52 GB),
`node/data`, `data.pristine-200000`, the rows CSV, the `cassandra/` copy. Kept: `pc91:/mydata/s4/b27/{harness,classes,
logs}` (508 MB; `debug.log`, `gc.log*`, `system.log` gzipped). Driver PID file removed; node lock released.

## 4. Conclusion (stage 2)

**Verdict: true positive.** Status `verified-OOM · deployment` — convergence by multiplicity, **unprotected
configuration** (the aggregate count control `native_transport_max_concurrent_connections` / `_per_ip` ships −1).
Interpretation: configuration-sizing gap (a fixed 1 MiB exclusive allowance per connection, not derived from the heap,
times an unlimited connection count), not an implementation defect. Largest failing budget tested: **heap 8 GiB /
direct 4 GiB, 3/3** (2 GiB 3/3, 4 GiB 3/3); the search stopped there (design's top), not at a boundary.

**Reason.** On Cassandra 5.0.9 with every §2.3 constraint at its shipped default and a 2 GiB heap, 3,500 protocol-v5
connections that each keep 7 filtering reads (125 KB bound value) in flight drive the node to `java.lang.OutOfMemoryError:
Java heap space` in 3/3 runs (46–94 s). At the OOM each connection holds ≈ 4.6 decoded requests (≈ 0.57 MB, inside its own
1 MiB `native_transport_receive_queue_capacity`), so `acquireCapacity` admits every request on the exclusive queue and
never charges the global (heap/10) or per-IP (heap/40) reserve: the global reserve in use reads ≤ 44 B while the dumps
hold 2.0 GB of decoded values (94 % of the heap, 9.3 × heap/10), no request is refused, and no "bytes in flight" warning is
sent. The convergence shape is attributed by its matched arms: 1,000 connections (same window, payload, data and client)
plateau at ≈ 7,000 requests and survive 0/3; the same 3,500 attempted connections with the shipped-disabled connection
limit set to 1,000 survive 0/3 with useful work at 65–93 % of the control's rate; 3,500 idle connections cost 4.4 KB each
(not the holder); and with the allowance set to 0 B (every byte charged to the reserves) the per-IP reserve fills at
heap/40 and only 427 requests stay resident. The same shape OOMs at 4 GiB / 7,000 connections and 8 GiB / 14,000
connections (3/3 each; `byte[125000]` 96 % of the heap; *K* ≤ 264 B), so the endpoint follows heap / (connections × 1
MiB allowance × the client's window share), not a fixed budget.

| | Requirement | Evidence | Met |
|---|---|---|---|
| V1 | ≥ 3 runs reach the endpoint | T2-r1..r3: heap OOM 3/3 at 2 GiB | yes |
| V2 | matched control does not | C2-r1..r3 (*N* = 1,000): 0/3 in 240 s, GC < 0.42 | yes |
| V3 | U independent of K | U: hprof `byte[125000]` / QM counts and live histograms; K: `Client.RequestsSize` (≤ 44 B) | yes |
| V4 | intervention removes the endpoint ≥ 3 runs | I2-r1..r3 (`native_transport_max_concurrent_connections: 1000`): 0/3, 2,500 refused, ok/s ≥ 0.5 × C2 | yes |
| V5 | initiating failure + holder | `OutOfMemoryError: Java heap space` + 9 hprofs: `byte[125000]` 93.7–96.3 % of the heap, one per queued `QueryMessage` / `RequestProcessor` (thread not printed: shipped `kill -9` first) | yes |
| V6 | default constraints | every §2.3 constraint at default (readback §3.1); the only constraint changes are in I2 / I2b | yes |
| V7 | acceptable budget | 2 GiB heap / 2 GiB direct (standing rule; ideal); also 4 / 8 GiB | yes |

**Limits.** Clients ran on the victim node from one IP (recorded in §2.5; the per-IP reserve is never charged, so one or
many client IPs give the same accounting). The per-connection `queueSize` is not exposed; "within Q" rests on the client
window (≤ 7 + 1 in flight) and on the dumps (≤ 4.72 per connection at the OOM, ≤ 7.62 in the C2/I2 histograms). The OOM
thread is not printed (shipped `OnOutOfMemoryError=kill -9`). C2's margin is smaller than §2.4 predicted at its transient
peaks (single histograms 1.54–1.84 GB, read-path objects), though its median live heap is 46–48 % of the heap and it
never reached the endpoint. The slow request (filtering read over a 200,000-row partition) only sets how long requests
stay queued; any workload whose service rate is below the arrival rate of *N* connections holds the same bytes.
Relation: B10 is the refused path of the same holder; B27 keeps every connection inside its contract (no refusal, no
drift), so the two mechanisms are distinct.
