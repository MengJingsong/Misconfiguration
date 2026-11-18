# B10 — native_transport_receive_queue_capacity: refused v5 requests dispatched uncharged, counter drift  <!-- file: cassandra/cases/native_transport_receive_queue_capacity--refused-v5-request-uncharged-drift/native_transport_receive_queue_capacity--refused-v5-request-uncharged-drift.md -->

| Field | Value |
|---|---|
| Case ID | `B10` (bypass: accounting omission; README "ID prefixes") |
| From | `OC-20` of the phase 1 OOM candidate list (campaign row B10 / P1, retired) |
| Phase-1 case file | [`native_transport_receive_queue_capacity-acquireCapacity-queueCapacity--guided`](../../../../capacity-enforcement-exp/cassandra/stage3-ai-deep-read/cases/native_transport_receive_queue_capacity-acquireCapacity-queueCapacity--guided.md) |
| System / pinned source | Cassandra 5.0.9 (`systems/cassandra/source/`, tag `cassandra-5.0.9`); node build `pc72:/mydata/s4/cassandra-base` (built 2026-11-17) |
| Stage 1 (design) | OOM agent, stage 1 (wave-1 workflow subagent), 2026-11-17 22:40–23:20 EST |
| Stage 2 (verify) | pending (a fresh session) |
| Verdict | `pending` |

**Summary:** pending (stage 2).

## 1. Candidate

**Candidate row (quoted from `phase1-oom-candidates.md`, 2026-11-17):**

> | OC-20 | 2026-11-16 | `native_transport_receive_queue_capacity-acquireCapacity-queueCapacity--guided` | legacy | [lead list, blind, E2; N13; queued as B10] In the default non-throwing mode a v5 single-frame request that fails `acquireCapacity` is still processed uncharged (`CQLMessageHandler.java:223`, `:245-260`) and its release subtracts the full size (`:509`), so `queueSize` drifts negative and neither the 1 MiB per-connection capacity nor the heap/10 reserve bounds decoded requests: stage 4 held 15× the bound (83.3 MB from 10 connections), linear in connections × client window. | CP-6, CP-3 | picked: B10 |

**Phase-1 constraint and check.** `native_transport_receive_queue_capacity` (default 1 MiB, `Config.java:302`) is each
v5 connection's exclusive budget for in-flight request bytes; beyond it a request borrows from the per-IP reserve
(`native_transport_max_request_data_in_flight_per_ip`, default heap/40) and the global reserve
(`native_transport_max_request_data_in_flight`, default heap/10) in `AbstractMessageHandler.acquireCapacity`
(`AbstractMessageHandler.java:411-458`). In the default mode (`native_transport_throw_on_overload: false`,
`Config.java:1393`; client did not send `THROW_ON_OVERLOAD`) a failed acquire sets `backpressure = BYTES_IN_FLIGHT`
(`CQLMessageHandler.java:223-224`) and the request is then **still decoded and dispatched**
(`processRequestAndUpdateMetrics`, `:245-260`, `:266-271`), with a client warning, without having been charged. When
it completes, `release(header)` (`:506-510`) calls `releaseCapacity(bodySize)` (`AbstractMessageHandler.java:460-475`),
subtracting bytes that were never added: `queueSize` drifts down by *M* per refusal, later acquires succeed against the
drifted counter, and the decoded requests on the heap are bounded only by connections (`native_transport_max_concurrent_connections`
−1 = unlimited) × each client's window.

**Stage-4 evidence (phase 1).** [Recheck 2026-11-17 on `pc72`](../../../../capacity-enforcement-exp/cassandra/stage4-runtime-verification/results/native_transport_receive_queue_capacity-acquireCapacity-queueCapacity--guided--recheck-2026-11-17.md):
**Confirmed — does not cap** (heap). Every knob at default, heap 2 GiB, one client IP, *W* = 240 one-frame requests of
*M* = 65,074 B per connection, request executor slowed by a **Byteman 250 ms hold** (an injected delay; 60 s timeouts):
decoded requests 312 / 468 / 624 MB at *N* = 20 / 30 / 40 against counted bounds *K_N* = 75 / 85 / 96 MB (4.2–6.5 ×
*K_N*, 1.45–2.91 × heap/10), exactly *W*·*M* per connection, every handler's `queueSize` ending at −*k*·*M*; the
counters (`ΣA`, global reserve in use 53.5–53.7 MB = per-IP reserve full) read "at the bound" the whole time.
Throwing mode (`T40`) and multi-frame requests (`L20`) held the same windows to *K_N*. Direct memory: undetermined (one
84 MB step, not following). No OOM was sought (heap 2 GiB, peak 624 MB of decoded requests).

What phase 2 adds: an **OOM at defaults without an injected hold and without raised timeouts** — the stage-4 delay and
the 60 s timeouts are replaced by a realistic slow request (expensive filtering reads on a wide partition), the
shipped `native_transport_timeout` (12 s) and `read_request_timeout` (5 s), and windows sized to exceed the heap.

**JIRA prior art (read only, nothing posted; checked 2026-11-17 22:50 EST).**
- Survey `jira-oom-survey.csv` (604 rows): related native-transport rows 9318 (in-flight byte limits, Fixed 3.10),
  15013 (client requests blocking on executor queue, Fixed 4.0), 20052 (v5 message size not limited, Fixed 5.0.3),
  7743, 3911; none describes a refused-but-dispatched request or counter drift.
- JIRA REST (issues.apache.org, read only):
  `project = CASSANDRA AND text ~ "queueSize"` → 6 hits (21091 "Missing metrics with protocol v5", open: the
  `Client.RequestSize` metric reads 0 on v5 — a metric gap, not the drift; 19486, 16120, 15766, 2034, 1035 unrelated);
  `text ~ "CQLMessageHandler"` → 12 (21884 v5 **multi-frame** requests do not return networking buffers, Needs
  Committer — another path; 21766 PreV5 flush leak, Fixed; 20052; 19534 unbounded native-transport queues, Fixed
  5.0-rc1 — sheds by queue **age** only when `native_transport_queue_max_item_age_threshold` is set, default
  `Double.MAX_VALUE` = off; 16663 rate limiting; others unrelated);
  `text ~ "throw_on_overload" AND (memory OR OOM OR heap)` → 23 (none on the drift);
  `text ~ "receive_queue_capacity"` → 16 (none); `("bytes in flight" OR "max_request_data_in_flight") AND (OOM OR
  OutOfMemoryError)` → 7 (9318, 20052, 8723, others unrelated). The campaign row's queries of the same day
  (`queueSize` 6, `CQLMessageHandler AND (capacity OR overload)` 8, `native_transport_receive_queue_capacity` 14,
  `throw_on_overload` 55) found nothing either.
- **Verdict: `new`.** Not documented as by design: the code comment at `CQLMessageHandler.java:74-80` describes the
  default mode as applying backpressure by pausing the connection, not as admitting refused requests uncharged.

## 2. Design solution (stage 1; frozen)

### 2.1 Mechanism

**Direction: bypass — accounting omission (U > C, K ≤ C)**, technique note [`bypass-playbook.md`](../../../bypass-playbook.md)
row "Failed reservation but admitted work". Interpretation: suspected implementation defect (the default branch
dispatches a refused one-frame request without charging it, and its release still subtracts its size).

Chain at shipped defaults, protocol v5, one-frame requests (envelope ≤ `LARGE_MESSAGE_THRESHOLD` = 131,071 B,
`CQLMessageHandler.java:83`):

1. A connection's window *W* of requests of body size *M* arrives; once `queueSize` + reserves are used up,
   `acquireCapacityAndQueueOnFailure` fails (`CQLMessageHandler.java:223`), the handler registers a wait-queue ticket and
   the request is **processed anyway** with `Overload.BYTES_IN_FLIGHT` (`:245-260`): decoded (`composeRequest`, the bound
   value copied onto the heap by `CBUtil.readValue`, `CBUtil.java:443-450`) and submitted to the
   `Native-Transport-Requests` executor (`native_transport_max_threads` 128, unbounded queue), with a "bytes in flight"
   client warning (`Dispatcher.java` `case BYTES_IN_FLIGHT`).
2. On completion `release(header)` → `releaseCapacity(M)` (`CQLMessageHandler.java:506-510`,
   `AbstractMessageHandler.java:460-475`) subtracts *M* that was never added: `queueSize` −= *M*. Stage 4 showed the
   counted figures then sit at the bound while every connection holds *W*·*M* decoded.
3. Queued requests are not shed by bytes or by age at intake (`native_transport_queue_max_item_age_threshold` default
   `Double.MAX_VALUE`, `Config.java:1394`, `Dispatcher.hasQueueCapacity`); a request older than
   `native_transport_timeout` (12 s) is answered "timed out before it could start" **when dequeued**
   (`Dispatcher.processRequest`, `Dispatcher.java:357-367`), so it occupies the heap until then and the client re-sends.
   Live decoded bytes in the node ≈ min(*N*·*W*·*M*, client send rate × 12 s) — far above the contract bound *K_N*.
4. When that exceeds the free heap: `java.lang.OutOfMemoryError: Java heap space`; the shipped
   `-XX:+HeapDumpOnOutOfMemoryError` (`conf/jvm-server.options:120`) writes a dump and the shipped
   `-XX:OnOutOfMemoryError="kill -9 %p"` (`conf/cassandra-env.sh:209`) kills the JVM.

The node must process requests more slowly than the client offers them, or the window sits in the client. Stage 4
used an injected hold; here the requests are **themselves expensive**: `SELECT pk FROM ks.t WHERE pk = 0 AND v = ?
ALLOW FILTERING` (the stage-4 client's statement, unchanged) against a partition `pk = 0` of *R* clustering rows, so
every read scans *R* rows (filtering is allowed at defaults, `allow_filtering_enabled: true`, `Config.java:906`; the
default authenticator makes the client a superuser, so no guardrail applies either way). The bound value is a
125,000-byte blob (never matches; result empty).

**OC-50 not folded in.** OC-50 (each connection's own 1 MiB charged before the reserves, unlimited connections) needs
≈ 2,000 connections for 2 GiB, a different client and file-descriptor setup, and is a contract-level (unprotected
multiplicity) claim rather than this drift; it does not fit the time window below. OC-50 stays a separate candidate.

### 2.2 Protection map

| Domain | Holder (allocation, owner, release) | Counter (*K*) | Contract limit (*C*) | At the limit | Scope / multiplicity |
|---|---|---|---|---|---|
| D1 decoded one-frame requests (claimed) | `QueryMessage` + `QueryOptions` values: heap `byte[]` copy of each bound value (`CBUtil.java:443-450`), owned by the request task from decode (`CQLMessageHandler.composeRequest`) until the response is flushed (`release`, `:500-510`) | per-connection `queueSize` + per-IP reserve use + global reserve use (`Client.RequestsSize`) | **K_N = N·C + E**, C = 1 MiB per connection, E = per-IP reserve heap/40 (one client IP; the global reserve G = heap/10 > E) | default mode: refused requests **still dispatched uncharged** (the bypass); throwing mode: discarded with `OverloadedException` | per connection × *N* connections (unlimited, −1); per IP |
| D2 request executor queue | `Native-Transport-Requests` SEP executor queue entries referencing D1 | none (count unbounded) | none in bytes; age shed only at dequeue after 12 s | expired → error response at dequeue | node |
| D3 frame / networking buffers (direct) | `BufferPool` networking pool, Netty read buffers; one-frame payload released after decode (`FrameDecoder.deliver`) | pool `UsedSize`/`OverflowSize` | `MaxDirectMemorySize` | direct OOM | node; recorded only (stage 4: does not follow D1) |
| D4 read path (transient) | `ReadStage` (32 threads) iterators over the *R*-row partition | none | `concurrent_reads` 32 | queue | node; garbage, not live beyond the read |
| D5 baseline | schema, key cache (≤ min(5 % heap, 100 MiB)), chunk cache (direct), system tables | own caps | own caps | own policy | node |

Claimed: U(D1) > C(D1) = K_N with K ≤ K_N → bypass by accounting omission. D2 only references D1 (an alias, not
added). No memtable growth: the workload writes nothing after the data set is loaded and flushed.

### 2.3 Configuration and budget audit

**Constraints (V6), all at shipped defaults, none set in `cassandra.yaml`** (resolved values at heap *H*):

| Setting | Default | Resolved at H = 2 / 4 / 8 GiB |
|---|---|---|
| `native_transport_receive_queue_capacity` | 1 MiB (`Config.java:302`) | 1,048,576 B |
| `native_transport_max_request_data_in_flight_per_ip` | null → heap/40 | 53,687,091 / 107,374,182 / 214,748,364 B |
| `native_transport_max_request_data_in_flight` | null → heap/10 | 214,748,364 / 429,496,729 / 858,993,459 B |
| `native_transport_throw_on_overload` | false (`:1393`) | false (and clients do not send `THROW_ON_OVERLOAD`, except the intervention arm) |
| `native_transport_max_concurrent_connections` / `_per_ip` | −1 / −1 | unlimited |
| `native_transport_max_threads` | 128 (`:283`) | 128 |
| `native_transport_timeout` | 12 s (`:1399`) | 12 s |
| `native_transport_queue_max_item_age_threshold` | `Double.MAX_VALUE` (`:1394`) | off |
| `native_transport_rate_limiting_enabled` | false | false |
| `native_transport_max_message_size` | null → derived (`DatabaseDescriptor.java:903-918`) | record the resolved value from `system.log` |
| `read_request_timeout` | 5000 ms (`:145`) | 5 s |
| `concurrent_reads` | 32 (`:179`) | 32 |
| `allow_filtering_enabled` | true (`:906`) | true |
| `slow_query_log_timeout` | 500 ms | 500 ms (reads are calibrated to stay below it, §2.5) |

**yaml diff from the shipped file (environment only):** `cluster_name: oom-b10`, `listen_address`/`rpc_address`
127.0.0.1, `seed_provider` seeds `127.0.0.1:7000`, `data_file_directories`, `commitlog_directory`,
`hints_directory`, `saved_caches_directory`, `cdc_raw_directory` under the run folder, `auto_snapshot: false`. No
timeout, no transport, no capacity key. The run script fails the run if the generated yaml contains any key of the
table above.

**Budgets (V7).** The node the result claims to represent: a 2–8 GiB-heap Cassandra node (a common container or VM
size). What `cassandra-env.sh` would resolve on `pc72` (125 GiB, G1): heap min(½ RAM, 31,744 MiB) = **31,744 MiB**,
direct **15,872 MiB**; recorded, not used. Chosen: **heap 2 GiB (ideal budget) with `MaxDirectMemorySize` 2 GiB**,
then an upward search to **4 GiB and 8 GiB heap** (direct stays 2 GiB; D3 is not the claimed domain). All are ≥ 512
MiB → V7 met by the standing rule (2026-11-11), no per-case review needed. JVM: OpenJDK 11.0.33, G1 (shipped
`jvm11-server.options`), shipped `cassandra-env.sh` GC log, heap dump on OOM and `OnOutOfMemoryError=kill -9 %p`.

**Containment, not a budget.** The node runs in `systemd-run --user --scope -p MemoryMax=<H + 6 GiB> -p
MemorySwapMax=0` (8 / 10 / 14 GiB) only to protect the host and the client; it is set far above heap + direct +
metaspace/threads (stage 4 peaked at 4.47 GB of scope memory with a 2 GiB heap and direct). It is **not** the budget:
a run whose scope records `oom_kill` > 0 or `memory.events max` > 0 is **invalid** (not a reading) and is repeated
once with MemoryMax + 4 GiB. No container limit is part of the claim, so no owner review is needed.

### 2.4 Ceiling arithmetic (heap 2 GiB)

- Contract ceiling of D1 for *N* connections from one IP: **K_N = N·1,048,576 + 53,687,091 B**; for *N* = 20:
  74,658,611 B (71.2 MiB) — identical to stage-4 `D20`'s bound.
- Baseline live heap: ≈ 0.18 GB idle (stage 4 `idle`) + key cache ≤ 0.1 GB → ≈ 0.3 GB.
- Σ contract capacities + baseline ≈ 0.3 + 0.07 ≈ **0.37 GB ≪ 2 GiB**: a node that honoured the contract cannot
  reach heap OOM with this workload; an OOM can only come from D1 above its contract (U > C).
- Workload: *M* = 125,074 B (125,000-byte value + 74 B of query and options; stage 4 measured 74 B overhead with the
  same statement), *W* = 1,024, *N* = 20 → window **V = 2,561,515,520 B (2.39 GiB) = 34.3 × K_20**. Live D1 is
  predicted ≈ min(V, client send rate × 12 s); with two client JVMs (stage 4: one single-event-loop JVM sent ≈ 160 MB/s)
  the 12 s cap is ≥ 3.8 GB, so D1 → V > heap − baseline (≈ 1.7 GiB usable) → **heap OOM**.
- Low-multiplicity control *N* = 8: V = 1,024,606,208 B (0.95 GiB); D1 + baseline ≈ 1.33 GB = 62 % of the heap (38 %
  margin ≥ the 30 % target) → no OOM predicted.
- Upward search: *N* = 40 at 4 GiB (V = 5.12 GB), *N* = 80 at 8 GiB (V = 10.25 GB), same per-connection window; D1
  needs a client send rate ≥ (H − 0.3 GB)/12 s ≈ 0.31 / 0.69 GB/s, provided by 4 / 8 client JVMs.

### 2.5 Workload and environment

**Node: `pc72` only** (x86_64, 40 cores, 125 GiB RAM, 8 GiB swap, `/mydata` 713 GiB free on a rotating disk,
Ubuntu 22.04, kernel 5.15, cgroup v2, `ulimit -n` 1024 for the user shell; checked read-only 2026-11-17 22:45 EST:
no Java process running, load 0.00; `/mydata/s4/cassandra-base` built; `/mydata/s4/ntq-recheck/` holds the stage-4
run, do not touch it). Victim node and client JVMs both on `pc72` (recorded deviation from the protocol's "clients
on other nodes": acceptable as the client is outside the node's scope; one client IP 127.0.0.1, so the per-IP reserve
is the binding counter, as in stage 4). One measured experiment at a time; nothing else runs on `pc72`.

**Folders.** Run base `pc72:/mydata/oom-b10/`: `cassandra/` = `cp -a /mydata/s4/cassandra-base` (never run `ant` in
it), `classes/`, `harness/` (copy of this case's `harness/`), `node/` (conf, data), `data.pristine/`, `logs/<run-id>/`.
Repo harness: `harness/` in this case folder; small excerpts: `logs/`.

**Harness to build (stage 2).**
- `NativeFlood.java`, `Jmx.java`: **copied unchanged** from
  `capacity-enforcement-exp/cassandra/stage4-runtime-verification/harness/native_transport_receive_queue_capacity-acquireCapacity-queueCapacity--guided--recheck-2026-11-17/`
  (compile exactly as that harness's `recheck-run.py` does: `javac -d classes Jmx.java`; `javac -nowarn -d classes -cp
  "cassandra/build/classes/main:cassandra/build/lib/jars/*" NativeFlood.java`). NativeFlood sends the statement of
  §2.1 at `ONE`, *W* stream slots per connection, re-sends on success at once and on `OverloadedException` after
  `--retry-ms` (100), and prints per-second `sent ok warned ovl_bytes ovl_other err outstanding`.
- `make-node-yaml.sh`: adapted from the stage-4 one with **only** the environment lines of §2.3 (drop its
  `native_transport_timeout`, `read_request_timeout`, `throw_on_overload`, `rate_limiting_enabled` lines).
- `b10-run.py <run-id> <arm> <heap GiB> <N> [--throw]`: one clean-start node lifetime (steps below).
- No Byteman agent in any arm (deployment label).

**Data set (once, before calibration).** Start a node (heap 2 GiB) on an empty `node/data`; `CREATE KEYSPACE ks WITH
replication = {'class':'SimpleStrategy','replication_factor':1}; CREATE TABLE ks.t (pk int, ck int, v blob, PRIMARY
KEY (pk, ck));` load *R* rows `(0, i, 16 random bytes)` for i in 0…R−1 with `cqlsh COPY ks.t (pk, ck, v) FROM
'rows.csv'` (CSV written by a Python one-liner, blob as `0x…` hex); if COPY fails, a SimpleClient loop of `INSERT INTO
ks.t (pk, ck, v) VALUES (0, ?, ?)` with 64 in flight. Then `nodetool flush ks t`, `nodetool drain`, stop the node,
`cp -a node/data data.pristine`. Every run restores `rm -rf node/data && cp -a data.pristine node/data` (clean start =
fresh JVM, same data files).

**Calibration of *R* (not a reading; values recorded in §3).** Start *R* = 200,000. With heap 2 GiB, run *N* = 4,
*W* = 1,024 (V = 0.51 GB, safe) for 60 s. Accept *R* when (a) client `ok` rate μ ≤ 1,000/s, (b) NTR `PendingTasks`
≥ 0.7 × N·W at 30–60 s, (c) one idle `cqlsh` read with a 16-byte value (`time bin/cqlsh -e "SELECT pk FROM ks.t
WHERE pk = 0 AND v = 0x00 ALLOW FILTERING"`, minus cqlsh start-up measured with `SELECT now() FROM system.local`)
≤ 400 ms, and (d) client `warned` > 0 with `RequestDiscarded` +0 (the refused-but-dispatched path is reached). If
(a) or (b) fails, double *R* (≤ 800,000); if (c) fails, halve it; at most 3 calibration rounds, then use the last *R*
meeting (c) and (d) and record which of (a)/(b) failed. *R* is a data-shape choice, not a server setting.

**Arms (each run a clean start; load phase 240 s).**

| Arm | Heap / direct | *N* | *W* | Value bytes | Client option | Client JVMs | Purpose |
|---|---|---|---|---|---|---|---|
| `T2` test | 2 / 2 GiB | 20 | 1,024 | 125,000 | default (no `THROW_ON_OVERLOAD`) | 2 × 10 conns | failing condition (V1) |
| `C2` control | 2 / 2 GiB | 8 | 1,024 | 125,000 | default | 1 × 8 | low multiplicity, same payload and data (V2) |
| `I2` intervention | 2 / 2 GiB | 20 | 1,024 | 125,000 | `THROW_ON_OVERLOAD` (NativeFlood `--throw true`) | 2 × 10 | restores the charge-before-dispatch: refused requests discarded (V4) |
| `T4` search | 4 / 2 GiB | 40 | 1,024 | 125,000 | default | 4 × 10 | larger budget |
| `T8` search | 8 / 2 GiB | 80 | 1,024 | 125,000 | default | 8 × 10 | larger budget |

*W* = 1,024 is the default per-connection in-flight limit of the DataStax Java drivers (4.x
`advanced.connection.max-requests-per-connection`; 3.x local `maxRequestsPerConnection` with protocol ≥ v3).
**Pre-declared dose ladder for the test condition at 2 GiB:** if `T2` run 1 ends without OOM **and** its peak
`QueryMessage` count < 0.8 × N·W (window not resident, client-limited), the test condition moves to *N* = 30 (3 JVMs),
then *N* = 40 (4 JVMs), same *W* and value; the first *N* that reaches OOM becomes `T2` for all repeats and for `I2`
(`C2` stays *N* = 8). If `T2` run 1 ends without OOM with the window resident (≥ 0.8 × N·W), do not escalate: record
the outcome (service loss or no failure) and continue the plan unchanged.

**Steps of `b10-run.py` (per run).**
1. Check `ps -eo pid,cmd | grep '[C]assandraDaemon'` is empty; restore `node/data`; regenerate `node/conf`; fail if the
   yaml sets any §2.3 key.
2. Start: `systemd-run --user --scope --unit oom-b10-<run-id> -p MemoryMax=<H+6>G -p MemorySwapMax=0 bash -c 'ulimit -n
   100000 && exec bin/cassandra -f'` from `cassandra/`, env `CASSANDRA_CONF=node/conf CASSANDRA_LOG_DIR=logs/<run-id>
   CASSANDRA_HEAPDUMP_DIR=logs/<run-id> MAX_HEAP_SIZE=<H>G MAX_DIRECT_MEMORY_SIZE=2G` (unset `HEAP_NEWSIZE`); stdout to
   `logs/<run-id>/stdout.txt`. Wait (bounded, ≤ 300 s) for `nodetool status` UN and `statusbinary` running.
   Read back: `-Xmx`, `-XX:MaxDirectMemorySize`, `-XX:+UseG1GC`, `HeapDumpOnOutOfMemoryError`, `OnOutOfMemoryError`
   from `/proc/<pid>/cmdline`; scope `memory.max`, `memory.swap.max`; resolved `native_transport_max_message_size` and
   reserve limits from `system.log` / JMX.
3. Warm-up (not a reading): NativeFlood *N* = 1, *W* = 8, value 125,000, 10 s; then 20 s idle.
4. Idle readings: `jcmd <pid> GC.class_histogram` (`histo-idle.txt`), one JMX `get` of every poll bean.
5. Start pollers: `Jmx poll 2000` of `java.lang:type=Memory HeapMemoryUsage`, `java.nio:type=BufferPool,name=direct
   MemoryUsed/Count`, `org.apache.cassandra.metrics:type=BufferPool,scope=networking,name=UsedSize/OverflowSize Value`,
   `type=Client,name=RequestsSize Value` (global reserve in use), `type=Client,name=PausedConnections Value`,
   `type=Client,name=RequestDiscarded Count`, `type=Client,name=TimedOutBeforeProcessing Count`,
   `type=ThreadPools,path=transport,scope=Native-Transport-Requests,name=PendingTasks Value` and `ActiveTasks`,
   `type=ThreadPools,path=request,scope=ReadStage,name=PendingTasks Value` (if a bean name differs, list
   `type=ThreadPools,*` once and use the listed name; record it); scope `memory.current` and `memory.events` every 2 s.
6. Load: start the client JVMs together (`java -Xmx4g -XX:MaxDirectMemorySize=8g -Dio.netty.eventLoopThreads=2
   $(cat cassandra/conf/jvm11-clients.options | grep -v '^#') -Dlogback.configurationFile=<flood-logback.xml> -cp
   classes:cassandra/build/classes/main:cassandra/build/lib/jars/'*' org.apache.cassandra.transport.NativeFlood --host
   127.0.0.1 --connections <n_j> --window 1024 --value-bytes 125000 --seconds 240 --throw <false|true> --retry-ms
   100`), each to `logs/<run-id>/flood-<j>.out`; *t* = 0 at the first `start ms=` line.
7. Histograms (`jcmd <pid> GC.class_histogram`, `histo-<k>.txt`, record start/end ms): at *t* = 20 s, then every 20 s
   at H = 2 GiB and every 30 s at H ≥ 4 GiB, while the node lives. (A histogram forces a full GC: a pause, not a
   change of the live set; recorded as instrumentation overhead.)
8. Endpoint watch every 1 s: node PID gone → read `stdout.txt` for `java.lang.OutOfMemoryError` (first line and type),
   `Dumping heap to`, `OnOutOfMemoryError`; `system.log` for the first `OutOfMemoryError` / `ERROR` with thread name;
   scope `memory.events` (`oom_kill`, `max`). Endpoint time = first OOM line's log time or PID-gone time.
9. End: at *t* = 240 s (or 30 s after the node died) stop the clients (they drain ≤ 120 s; kill their PIDs after 30 s if
   the node is gone); stop the node if alive (`nodetool stopdaemon`, then kill PID); check no `CassandraDaemon` and no
   `NativeFlood` remain; stop pollers.
10. Summarise into `summary.txt` and `run.json`: arm, *H*, *N*, *W*, *M*, *R*; endpoint (OOM type / none) and time;
    per-histogram `QueryMessage` count and `[B` bytes; U(D1) = max(`QueryMessage` count) × *M*; `[B` − idle `[B`;
    K = max global reserve in use; *K_N*; U/K_N; max NTR `PendingTasks`; heap max and post-GC occupancy from `gc.log`
    (last 5 `Pause Full`/`Pause Young` "->" values); fraction of wall time in GC pauses over the last 60 s before the
    endpoint (service-loss criterion); client totals (`sent ok warned ovl_bytes ovl_other err`) and `ok`/s; direct
    `MemoryUsed` max; scope `memory.current` max; hprof file name and size. One `EXPECTED:` line per prediction of §2.7.

### 2.6 Instruments

- **U (independent of K):** live `org.apache.cassandra.transport.messages.QueryMessage` count × *M* and `[B` bytes
  above idle from `GC.class_histogram` (live objects after full GC); NTR `PendingTasks` (queued requests, every 2 s)
  as the continuous proxy; post-GC heap from `gc.log`; the hprof at OOM (kept on the node) as the dump.
- **K:** global reserve in use (`Client.RequestsSize`), which stage 4 showed equals the per-IP reserve when full; the
  per-connection `queueSize` is not exposed without Byteman, so K is bounded by construction (an acquire never exceeds
  *K_N*) and the stage-4 trace (every handler `queueSize` = −*k*·*M*) is cited for the per-handler drift.
- **Path evidence without instrumentation:** client `warned` (responses carrying the "bytes in flight" warning =
  refused-but-dispatched requests) > 0 and `RequestDiscarded` +0 in default-mode arms; in `I2`, `ovl_bytes` > 0 and
  `RequestDiscarded` = `ovl_bytes`.
- **Others:** heap used, direct `MemoryUsed`/count, networking pool, `TimedOutBeforeProcessing`, ReadStage pending,
  scope memory, client per-second counters; all with epoch-ms timestamps (single host clock).

### 2.7 Predicted response and stopping budget

| # | Arm | Prediction |
|---|---|---|
| P1 | all default arms | client `warned` > 0, `RequestDiscarded` +0; global reserve in use ≤ E + 1 MiB at every poll (≤ 54.7 MB at 2 GiB) |
| P2 | `T2` | NTR `PendingTasks` ≥ 0.5 × N·W within 60 s; histogram `QueryMessage` count rises to ≥ 0.6 × N·W (≥ 12,288; ≥ 1.54 GB) before the endpoint: **U/K_N ≥ 20** |
| P3 | `T2` | **heap OOM** (`java.lang.OutOfMemoryError: Java heap space` in `stdout.txt`, hprof written, JVM killed) **3/3**, within 180 s of *t* = 0; scope `oom_kill` 0 |
| P4 | `T2` | last histogram before the OOM: `QueryMessage` and `[B` are the two largest live classes by bytes, `[B` above idle ≥ 0.9 × count × 125,000 |
| P5 | `C2` | `QueryMessage` plateau within N·W ± 10 % (8,192); post-GC heap ≤ 1.45 GB; no OOM 0/3 in 240 s; GC pause fraction over the last 60 s < 90 % |
| P6 | `I2` | `QueryMessage` ≤ K_20/M + 128 = 725 at every histogram; `ovl_bytes` > 0; no OOM 0/3 in 240 s; client `ok`/s within a factor 2 of `C2`'s (useful work continues) |
| P7 | `T4`, `T8` | heap OOM if the client keeps D1 ≥ H − 0.3 GB resident; otherwise the plateau `QueryMessage` × *M* and the client send rate are recorded and the budget is reported as client-limited, **not** as a boundary of the system |
| P8 | all | direct `MemoryUsed` stays < 0.5 × D1 (D3 does not carry the claim; recorded) |

**Stopping budget.** Load phase 240 s per run (≈ 1.3 × the 180 s OOM prediction); no escalation after an OOM;
at most 3 runs per arm at 2 GiB, plus at most the 2 dose-ladder steps; upward search ≤ 3 runs at the largest failing
heap. Invalid runs (start-up failure, scope `oom_kill`, client crash before *t* = 60 s) are repeated once each.

### 2.8 Controls and intervention

- **V2 matched control:** `C2`, same build, heap, direct, data, statement, value, *W* and client code, *N* = 8
  (low multiplicity; the bypass shape's nearest surviving condition), 3 runs from clean starts.
- **V4 intervention:** `I2`, identical to `T2` except each connection's STARTUP carries `THROW_ON_OVERLOAD=1`
  (`StartupMessage.java:111`), which routes refused requests to `discardAndThrow` (`CQLMessageHandler.java:198-216`)
  instead of uncharged dispatch — the charge-before-dispatch is restored without a patch or a server-config change.
  3 runs; record throughput (`ok`/s) and refusals so a starved arm is not mistaken for protection.
- Stage-4 `T40`/`L20` (throwing mode and multi-frame requests held to *K_N*) are cited as path-specificity evidence,
  not reused as V2.

### 2.9 Time plan (deadline: every process stopped by 02:10, case file written by 02:30 EST, 2026-11-18)

Stage 2 is expected to start ≈ 23:30 EST (*S*). Durations: harness + compile + node folder 35 min; data set + calibration
20 min; each 2 GiB run ≈ 6 min (start 1 min, warm-up 0.5, load 4, stop/summary 0.5) — `T2` runs end earlier at OOM.

| From | To | Work |
|---|---|---|
| *S* | *S* + 0:35 | harness, copy `cassandra-base`, compile, instrument check (Jmx `get` against an idle node, NativeFlood 5-s smoke) |
| *S* + 0:35 | *S* + 0:55 | data set, calibration of *R* |
| *S* + 0:55 | *S* + 1:50 | 9 runs at 2 GiB in the order `T2`, `C2`, `I2` ×3 (interleaved) (+ ≤ 12 min if the dose ladder fires) |
| *S* + 1:50 | *S* + 2:15 | upward search: `T4` ×1 → if OOM `T8` ×1 → repeat the largest failing heap to 3 runs while time allows |
| *S* + 2:15 | *S* + 2:40 | stop/cleanup check, excerpts, §3/§4, write-backs |

Hard cut-offs regardless of *S*: no new run starts after **01:55 EST**; all node and client processes stopped by
**02:10**; the case file written by **02:30**. If *S* is later than 23:30, drop in this order: `T8` repeats, `T8`,
`T4` repeats, `T4`. The 2 GiB set (9 runs) is the minimum; if it cannot finish by 01:55, the case ends as `retry`
with the reason "time", stating which of V1/V2/V4 ran.

**Resources on `pc72`:** RAM — node scope ≤ 8 / 10 / 14 GiB + clients ≤ 2–8 × ~3 GiB actual (≤ 4 GiB heap each) <
60 GiB of 125; cores — 40 (node ReadStage 32 + NTR 128 threads, clients 2–16 event-loop threads; CPU shared, recorded);
disk — data set < 0.1 GB, logs ≈ 0.2 GB per run, hprofs 2 GB × ≤ 6 + 4 GB × ≤ 3 + 8 GB × ≤ 3 ≈ 48 GB of 713 GB free.
Nothing is deleted from the node by stage 2 except the per-run `node/data` restore; the owner cleans up after accepting
the wave.

### 2.10 Outcome rows (decided before readings)

| Readings | Verdict / status |
|---|---|
| P1–P6 hold; `T2` OOM 3/3, `C2` 0/3, `I2` 0/3, U/K_N ≥ 20 | **true positive**, `verified-OOM · deployment` (bypass, accounting omission) at 2 GiB; largest failing heap reported with n/N |
| `T2` sustained GC service loss (≥ 90 % in pauses over ≥ 60 s) without OOM 3/3, U > K_N | **retry**, `verified-gap · service-loss · deployment`; better design: longer load phase or larger *N* |
| `T2` OOM < 3/3 with others surviving | report n/N; ≥ 1/3 with V2–V7 met → expand to 5 runs if time, else **retry** |
| D1 never resident (QueryMessage < 0.5 × N·W) at the top of the dose ladder | **retry** (design did not reach load): faster client (more JVMs or a second node `pc91`/`pc84` as client) |
| D1 resident ≥ heap − baseline and no OOM, no service loss | **false positive** only if `T4`/`T8` also hold it below the budget; otherwise **retry** |
| `C2` or `I2` reaches the OOM | V2/V4 unmet → **retry** with the attribution gap stated |
| any arm's OOM is direct-buffer or a scope kill | not the claimed endpoint: recorded; the run is invalid for V1 and repeated once |

`sha256 of §1–§2 at freeze: f57ed7fdccb650da2085249dffa639ba60f3cf9d8cbf2f4260826ea180554620` · computed over the lines from `## 1. Candidate` up to, not including, this
line (`sed -n '/^## 1\. Candidate/,/^`sha256 of §1–§2 at freeze/p' <file> | sed '$d' | sha256sum`). Amendments after
the freeze: dated, with reason.

## 3. Runs (stage 2)

pending

## 4. Conclusion (stage 2)

pending
