# coordinator_read_size_fail_threshold — concurrent reads each below the per-query size threshold

**Direction:** convergence · concurrency/surge (campaign row C2). **Lead source:** if-check inventory
(capacity-enforcement-exp stage 4: `coordinator_read_size_fail_threshold`, `local_read_size_fail_threshold`).
**Regime:** default capacities; read thresholds either at their shipped default (disabled, arm A = **unprotected
configuration**) or enabled at the project's own test value (arm B). Budgets: heap 512 MiB – 7965 MiB (auto),
direct 3982 MiB (auto) and 7936 MiB. **Source:** Cassandra 5.0.9, unmodified build `apt140:~/cassandra-b1`
(`git describe` = `cassandra-5.0.9`, jar sha256 `3e17de6b…d147`), single node `apt140` (victim), client `apt138`.
**Run:** C2 run 1, 2026-11-12, 14:20–17:53 and 19:03–19:20 UTC (paused in between by the researcher's request). Design [`design/C2-design.md`](design/C2-design.md) (written
before any reading; amendment 1 dated 15:16 UTC, before any repeated reading).
**Filed 2026-11-12 in `convergence/`** (F-A's negative is recorded in this case). **Status (researcher review 2026-11-12, recorded in the design):** S-A `verified-OOM · deployment` (**unprotected
configuration**); S-B `verified-OOM · diagnostic`; F-B `verified-OOM · diagnostic`; F-A `negative`. Per-condition table
in §4. Arms B are `diagnostic` because enabling the read thresholds at the `test/conf` values is a supporting deviation
(the acceptable threshold value is still to be discussed). Shared docs were not edited by this run.

## Summary

- **Conclusion.** On a single default Cassandra 5.0.9 node, concurrent single-partition reads that each stay
  below the per-query size threshold (3.5 MiB pages against `coordinator_read_size_fail_threshold` 4 MiB, the
  project's test value; an oversize 4.5 MiB read is refused in every lifetime) kill the node with a **direct-memory
  OOM** when the clients drain responses more slowly than the server produces them. 64 connections with 16 reads
  outstanding each (1,024 outstanding) and an aggregate drain of 128 MiB/s (one 1 GbE client NIC's worth) reach
  Netty `OutOfDirectMemoryError` at the auto-resolved 3,982 MiB direct limit about 11 s after the load starts:
  **3/3 with thresholds enabled, 3/3 with them at their default (disabled), 3/3 at the auto-resolved 7,965 MiB heap,
  1/1 at the largest direct limit `cassandra-env.sh` can resolve (7,936 MiB, 2,048 outstanding)**.
  The arm-A result uses only shipped defaults and is `verified-OOM · deployment`, an unprotected configuration. Cassandra then
  forces a heap OOM, dumps and kills itself. The same reads at 128 outstanding (0/6) and with the client capped at
  512 outstanding (0/6, same drain-limited throughput) survive. With fast clients (10 GbE Java driver) server-side
  concurrency stops at the 128 native-transport threads. With thresholds enabled (arm B) the heap OOMs at 512 MiB
  (4/4) and 640 MiB (1/1), and survives at 768 MiB, 1 GiB and 2 GiB with heavy GC. At shipped defaults (arm A) the
  heap does not OOM at 512 MiB (0/3, 80–83 % STW per 60 s; condition F, §3.5).
- **Root cause.** The read thresholds are per query (per page): nothing sums the memory of concurrent reads. The
  only bound on simultaneous reads *being processed* is `native_transport_max_threads` (128), but a finished
  response is encoded on the request thread into Netty pooled direct memory (`Message.encode` →
  `CBUtil.allocator`) and handed to the channel; the thread is then free for the next request. Encoded responses
  wait in Netty's outbound buffer until the socket drains. No transport code consults channel writability
  (the server sets an 8/32 KiB write watermark, `PipelineConfigurator.java:139`, but nothing in `transport/` calls
  `isWritable()`), the native in-flight limits charge **request** bytes and release them when the response is
  handed to the flusher, and the request rate limiter still dispatches requests already read from the socket. So
  outstanding response memory = outstanding reads × page size, bounded only by the client's own in-flight count.
  Arm A (thresholds disabled, the shipped default) is an unprotected configuration; arm B shows that enabling the
  thresholds does not change the outcome, because each read is within its per-query allowance (convergence).

## 1. Constraints, protection map and configuration

### 1.1 Thresholds that apply to the tested read (source, 5.0.9)

| Setting | Default | Enforced at | Charged unit | Role here |
|---|---|---|---|---|
| `read_thresholds_enabled` | **false** (`config/Config.java:526`; yaml "scheduled to be set true in 4.2") | `cql3/QueryOptions.java:275-281` (`DisabledReadThresholds` when false); `SelectStatement.java:334` `query.trackWarnings()` | — | master switch: arm A off (default), arm B on |
| `coordinator_read_size_fail_threshold` | **null** (`Config.java:528`) | `SelectStatement.maybeFail` `:1057-1080`, per page, before each further row | page `ResultSet` value bytes (`ResultSetBuilder.addSize` `:76-82`) | arm B 4096 KiB; **binds first**; reads are 3,670,016 B |
| `local_read_size_fail_threshold` | **null** (`:530`) | `ReadCommand.withQuerySizeTracking` `:663-730`, applied in `executeLocally` `:457` when `trackWarnings` | `row.unsharedHeapSize()` incl. cell values (`BufferCell.java:141-144`) | arm B 8192 KiB; not reached (≈ 3.68 MB) |
| `row_index_read_size_fail_threshold` | null | RowIndexEntry estimate | index bytes | arm B 8192 KiB; not reached |
| `tombstone_failure_threshold` | 100,000 | `ReadCommand` `countTombstone` | tombstones | no tombstones |
| `page_size_fail_threshold` | -1 (off) | guardrail | rows | off |

Arm B uses the only enabled values the project ships, `test/conf/cassandra.yaml:63-69` (coordinator warn/fail
1024/4096 KiB, local 4096/8192 KiB, row index 4096/8192 KiB); `cassandra.yaml` documents no value. The stage-4
results (`capacity-enforcement-exp/cassandra/stage4-runtime-verification/results/coordinator_read_size_fail_threshold-*`,
`local_read_size_fail_threshold-addSize-failBytes--guided.md`) confirm both checks refuse exactly at their per-query
limit; neither counts other queries. **Rejection control (every arm-B lifetime, 30/30):** a read of the 72-row
partition (4,718,592 value bytes) fails with `ReadFailureException` (`SelectStatement.java:1067` "exceeded the size
failure threshold of 4,194,304 bytes"; `CoordinatorReadSizeAborts` = 1), the 56-row read passes with the 1 MiB
warning. In arm A the same oversize read returns all 72 rows in 15/15 lifetimes (no per-query cap: unprotected configuration).

### 1.2 What bounds the number of simultaneous reads

| Candidate bound | Default | Source | What it bounds | Measured |
|---|---|---|---|---|
| `native_transport_max_threads` | 128 | `transport/Dispatcher.java:58-61` (SEP `Native-Transport-Requests`); read blocks the thread (`StorageProxy.readRegular` `:2005`, `awaitResponses` `:2148`) | requests being processed (read + encode) | NTR active plateaus at 128 for N ≥ 256; excess = pending tasks (tiny) |
| `concurrent_reads` | 32 | `Config.java:179`; `AbstractReadExecutor.java:165` `maybeExecuteImmediately` | local reads executing | ReadStage active ≤ 32 |
| `native_transport_max_request_data_in_flight(_per_ip)` | heap/10, heap/40 | `PreV5Handlers.checkLimits` `:151-217`; release `:99-110` when the response is handed to the flusher | **request** body bytes (≈ 60 B per SELECT) | never binds |
| `native_transport_rate_limiting_enabled` / `max_requests_per_second` | false / 1,000,000 | same; `:85-87` "even if backpressure is applied, the current request is allowed to finish" | request rate; requests already read are dispatched | at 30/s: did not prevent the OOM (`I-S-R30-1`) |
| `native_transport_queue_max_item_age_threshold` | `Double.MAX_VALUE` (off) | `Config.java:1394`, `Dispatcher.java:348` | queue age | off |
| outbound (responses written, not yet drained) | **none** | `PreV5Handlers.java:91-97` encodes on the request thread into `CBUtil.allocator` = `PooledByteBufAllocator(preferDirect)` (`CBUtil.java:60`, `Message.java:367`); watermark 8/32 KiB (`PipelineConfigurator.java:139`), but no `isWritable()` anywhere in `transport/` | nothing | 1,702–1,812 `ChannelOutboundBuffer$Entry`, 244–248 × 16 MiB `PoolChunk`s at each 3982-MiB OOM |
| client stream ids | 32,768 per v4 connection | protocol | the client's in-flight count | 16 per connection (1,024 total) suffices |

### 1.3 Protection map (fixed in the design before readings; amended 15:16 for D2/D3 lifetimes)

| Domain | Allocation / owner / release | Local contract (C) | Multiplicity and its bound | Budget |
|---|---|---|---|---|
| D1 serialized local page | `ReadResponse.LocalDataResponse.build` heap `ByteBuffer` (`ReadResponse.java:182-207`, `DataOutputBuffer` growth copies) → released when the coordinator has built the `ResultSet` | arm B: ≤ 4 MiB value bytes per page (coordinator), ≤ 8 MiB heap size (local); arm A: none | one per read in processing; ≤ 128 threads | heap |
| D2 `ResultSet` / `ResultMessage.Rows` | `ResultSetBuilder` → `Message.encode` on the same thread → released | same | ≤ 128 | heap |
| D3 encoded response | `Message.encode` body in Netty pooled direct (16 MiB chunks, `-Dio.netty.allocator.maxOrder=11`, `jvm11-server.options:145`; no-cleaner, counted by Netty against `MaxDirectMemorySize`) → released when the socket accepts it | per response ≤ C (arm B); none (arm A) | **outstanding responses: bounded only by client in-flight** | direct (Netty counter; NMT *Other*) |
| Aggregate | no reservation spans D1–D3 or sums D3 | — | — | heap + direct |

**Classification by measurement.** Arm B: U per response ≤ C (3.5 MiB pages, 0 workload aborts), ΣU over
outstanding responses + baseline > the direct budget → **convergence** (multiplicity of a per-query allowance).
Arm A: control disabled → **unprotected configuration** (protocol 2026-11-10), not a bypass.
Interpretation: a missing aggregate control (no outbound/response-memory backpressure on the native transport), a
configuration-sizing gap only in the sense that no setting exists to bound it.

### 1.4 Configuration and budget audit

| Item | Value | Class |
|---|---|---|
| OS / kernel / JDK / GC | Ubuntu 22.04, 5.15, OpenJDK 11.0.33, G1 (shipped `jvm11-server.options`) | environment |
| Node | apt140 r320, 16 logical CPUs, 15.6 GiB RAM, swap 8 GiB partition (left on; heap is `-Xms=-Xmx`, AlwaysPreTouch), no cgroup limit | environment |
| yaml diffs | `listen_address`/`rpc_address`/seeds 10.10.1.1, data/commitlog/hints/caches/cdc under `/mydata/c2/node` (every lifetime's `yaml.diff` in `logs/<run>/`) | environment |
| arm B | `read_thresholds_enabled: true` + the six `test/conf` values | tested protection (enabled) |
| interventions | F: `native_transport_max_threads: 16`; S: client outstanding cap 8/connection; (S, failed attempt) `native_transport_rate_limiting_enabled: true`, 30/s | intervention arms only |
| JVM extras | `-XX:NativeMemoryTracking=summary`, `-Xlog:gc=info,safepoint=info` (run folder) | instrumentation |
| heap | 512 MiB, 768 MiB, 1 GiB, 2 GiB, auto (`cassandra-env.sh` ½ RAM → **7965 MiB**) | budget |
| direct | auto (`cassandra-env.sh:66,139-158` ¼ RAM → **3982 MiB**, from every JVM command line); 7936 MiB once (the value `cassandra-env.sh` resolves on any node with > 31 GiB RAM, `:62`) | budget |
| other capacity settings | all default (resolved values in each `system.log` "Node configuration" line): `native_transport_max_threads=128`, `concurrent_reads=32`, in-flight limits null (= heap/10, heap/40), `native_transport_receive_queue_capacity=1MiB`, `file_cache_enabled=false`, `memtable_allocation_type=heap_buffers` | default |
| client | v4 (Java driver 3.12.1, F) / raw v4 (`slowread.py`, S); CL ONE; prepared or simple `SELECT v FROM c2.t WHERE pk=?`, page size 5000 | workload |

**V7 argument (standing rule 2026-11-11).** Every heap (≥ 512 MiB) and direct limit (3982 / 7936 MiB) is
≥ 512 MiB, so V7 is met without per-case review. The S condition fails at the node's fully auto-resolved budget
(heap 7965 MiB, direct 3982 MiB) and at the largest direct limit the start-up script resolves on any node.

## 2. Design, workload and commands

Pre-run design: [`design/C2-design.md`](design/C2-design.md) (§1 source findings, §2 protection map, §5 arms, §6
outcome rules; amendment 1 at 15:16 UTC records the two conditions, the v4 encode-on-request-thread correction,
the failed rate-cap intervention and its replacement, all before any repeated reading). Stopping budget: 7 h wall
(hard stop 21:15 UTC; no lifetime after 20:15), ≤ 40 lifetimes.

**Data (every lifetime, fresh node directory):** keyspace `c2` (SimpleStrategy RF 1), `c2.t (pk int, ck int, v blob,
PRIMARY KEY (pk, ck))`; 64 partitions × 56 rows × 64 KiB random values (3,670,016 value bytes per partition), plus
pk 1000 with 72 rows; `nodetool flush` (2 SSTables, 241 MB); then the two rejection-control reads, `GC.run`, a baseline
reading, and the load.

**Endpoint:** Java heap OOM, Netty/JVM direct OOM, or ≥ 90 % STW over ≥ 60 s (`harness/gcwin.py`, linear rewrite of
B6's script, same criterion).

**Harness** ([`harness/`](harness/)): `victim-ctl.sh` (apt140: start/ready/read/stop, arm and modifier handling,
JMX sampler start), `C2Sampler.java` (1 s JMX: heap, G1 old post-GC, NTR/ReadStage active+pending, `java.nio`
direct, `CoordinatorReadSizeAborts`), `run-arm.sh` (controller on pc96: one clean lifetime; 10 s NMT/RSS readings;
OOM/GC check; copies small logs), `batch.sh` + `arms-S.txt`/`arms-F.txt` (resumable batches), `C2Load.java` + `load.sh`
(Java driver client, condition F), `slowread.py` (raw v4 client with per-connection outstanding count and drain
rate, condition S), `summarize.py`, `steps.py`, `hprofhist.py` (B6's, plus byte[] size buckets), `hprofstacks.py`.

| Condition / arm | Command (`harness/run-arm.sh <label> <arm> <heap> <load>`) | Reps |
|---|---|---|
| SW calibration, fast | `SW-B-2G B 2G 8:60,32:60,128:90,256:90,512:90,1024:90` | 1 |
| SQ calibration, slow | `SQ-B-2G B 2G "slow;64;2:30,4:30,8:30,16:30,32:30;300;2048"` | 1 |
| S fail (B / A) | `S-{B,A}-n {B,A} 2G "slow;64;16:120;150;2048"` (64 conns × 16 outstanding, 2 MiB/s per conn) | 3 + 3 |
| S matched control | `M-S-{B,A}-n {B,A} 2G "slow;64;2:60;70;2048"` (128 outstanding, 60 s ≥ failing runs' reads) | 3 + 3 |
| S intervention | `I-S-n B 2G "slow;64;8:120;150;2048"`, `I-S-A-n A 2G …` (client cap 512 outstanding) | 3 + 3 |
| S rate-cap attempt | `I-S-R30-1 B+R30 2G "slow;64;16:120;150;2048"` | 1 |
| S budget | `X-S-auto-n B auto "slow;64;16:120;150;2048"`; `DIRECT=7936M X-S-d7936-1 B 2G "slow;64;32:120;150;2048"` | 3, 1 |
| F probes | `P-B-512M B 512M 256:180`, `P-B-1G B 1G 256:180`, `P-B-768M B 768M 256:180` | 1 each |
| F fail / control / intervention | `F-{B,A}-n {B,A} 512M 256:180`; `M-F-{B,A}-n … 8:180`; `I-F-n B+T16 512M 256:180` | 3/3/3 (+A) |

## 3. Results

Raw logs on the nodes: `apt140:/mydata/c2/runs/<label>/` (system.log, gc logs, samples.csv, readings.csv, hprof on
OOM), `apt138:/mydata/c2/runs/<label>/client.csv`. Small copies per lifetime in [`logs/<label>/`](logs/)
(`client.csv` filtered, `samples.csv`, `readings.csv`, `run.meta`, `yaml.diff`, `gcwin.txt`, `oom-excerpt.txt`,
`threshold-excerpt.txt`), controller transcripts `logs/controller-<label>.out`, batch lines `logs/batch-*.out`.
One-line table of every lifetime: `python3 harness/summarize.py logs`.

### 3.1 Calibration and U versus concurrency

**Fast clients (SW-B-2G, heap 2 GiB, 16 driver connections, N in flight; `harness/steps.py logs/SW-B-2G`):**

| N (client in flight) | reads/s | MB/s | NTR active med/max | NTR pending max | heap max (MiB) | old post-GC max (MiB) | GC time (young + full) | p50 latency |
|---|---|---|---|---|---|---|---|---|
| 8 | 228 | 798 | 4/7 | 2 | 1282 | 82 | 1.7 % | 34 ms |
| 32 | 315 | 1101 | 11/29 | 7 | 1274 | 82 | 2.7 % | 100 ms |
| 128 | 238 | 832 | 109/123 | 13 | 1896 | 358 | 25.3 % | 532 ms |
| 256 | 230 | 806 | 128/128 | 125 | 1929 | 348 | 27.6 % | 1106 ms |
| 512 | 231 | 807 | 128/128 | 382 | 1923 | 345 | 27.6 % | 2223 ms |
| 1024 | 231 | 807 | 128/128 | 896 | 1935 | 446 | 27.8 % | 4428 ms |

Simultaneous reads at the server stop at 128 (thread cap); larger N only lengthens the queue. At 2 GiB: 601 Full GCs
in 485 s, max 28 % STW per 60 s, no OOM, 0 client errors. NMT *Other* 477 → 574 MiB (outbound direct stays small:
the client drains at 10 GbE).

**Slow consumers (SQ-B-2G, heap 2 GiB, direct 3982 MiB, 64 connections at 2 MiB/s each):**

| outstanding reads (64 × k) | NMT *Other* (MiB, 10 s readings) | Δ vs baseline 493 | Δ per outstanding read |
|---|---|---|---|
| 0 (baseline) | 493 | — | — |
| 128 | 1007–1087 | +514…594 | 4.0–4.6 MiB |
| 256 | 1583–1615 | +1090…1122 | 4.3–4.4 MiB |
| 512 | 2623–2831 | +2130…2338 | 4.2–4.6 MiB |
| 1024 | Netty `OutOfDirectMemoryError` ≈ 10 s into the step (used 4,160,749,568 of 4,175,429,632 B) | — | — |

U grows linearly with outstanding reads (≈ 4.4 MiB per 3.5 MiB response: 16 MiB pool chunks hold four), the
per-read K stays 3,670,016 B, and NTR active stays at 128 throughout. Throughput is the drain (≈ 128 MiB/s, 36
reads/s); the server produces ≈ 230 reads/s, so the backlog fills within seconds.

### 3.2 Condition S — slow consumers, heap 2 GiB, direct auto 3982 MiB

| Run | Arm | Outcome | Completed reads | Netty direct at failure | NMT *Other* max (MiB) | max STW / 60 s |
|---|---|---|---|---|---|---|
| S-B-1 | B | direct OOM @ +10 s | 112 | 4,160,749,568 / 4,175,429,632 B | — (died between readings) | 2 % |
| S-B-2 | B | direct OOM @ +11 s | 125 | same | — | 3 % |
| S-B-3 | B | direct OOM @ +11 s | 121 | same | — | 2 % |
| S-A-1 | A | direct OOM @ +11 s | 116 | same | — | 3 % |
| S-A-2 | A | direct OOM @ +11 s | 121 | same | — | 2 % |
| S-A-3 | A | direct OOM @ +11 s | 111 | same | — | 2 % |
| M-S-B-1/2/3 | B, 128 outstanding | survived 60 s | 2176 each | — | 1166 / 1150 / 1118 | 0 % |
| M-S-A-1/2/3 | A, 128 outstanding | survived 60 s | 2176 each | — | 1121 / 1183 / 1054 | 0 % |
| I-S-1/2/3 | B, client cap 512 outstanding | survived 120 s | 4352 each (36.3/s) | — | 3008 / 3007 / 3102 | 1 % |
| I-S-A-1/2/3 | A, client cap 512 outstanding | survived 120 s | 4352 each (36.3/s) | — | 3023 / 3010 / 3026 | 1–2 % |
| I-S-R30-1 | B + rate cap 30 req/s | direct OOM @ +11 s | 110 | same | — | 2 % |

"Completed reads" are responses the client finished receiving before the failure; the server had produced
≈ 850–900 (the outbound entries in the dumps, §3.4). The matched controls read ≥ 17 × more data than any failing
run, at the same drain rate. The intervention keeps the demand at 1,024 reads but lets only 512 be outstanding:
throughput equals the uncapped runs' drain-limited rate (36 reads/s, 128 MiB/s), so the cap removes no useful work.

**Budget search (condition S, arm B):** X-S-auto-1/2/3 (heap auto = 7965 MiB, direct 3982 MiB): direct OOM 3/3
at + 12/11/11 s (96/110/108 completed reads), Netty counter as above; the larger heap changes nothing (heap max
3.3–3.5 GiB, old post-GC ≤ 107 MiB). X-S-d7936-1 (heap 2 GiB, direct 7936 MiB, 2,048 outstanding): direct OOM at
+28 s, `used: 8321499136` (7936 MiB). The endpoint follows outstanding × ≈ 4.4 MiB > direct limit; the heap is not
the binding domain. **Largest failing budget tested: heap 7965 MiB with the auto 3982 MiB direct limit (3/3), and
direct 7936 MiB (1/1)** — i.e. every budget `cassandra-env.sh` can resolve.

### 3.3 Initiating failure (V5), condition S

First error in every S failure, e.g. S-B-1 (`apt140:/mydata/c2/runs/S-B-1/logs/system.log`, load started ≈ 15:17:31):

```
ERROR [Native-Transport-Requests-13] 2026-11-12T15:17:41,455 JVMStabilityInspector.java:70 - Exception in thread Thread[Native-Transport-Requests-13,10,SharedPool]
org.apache.cassandra.transport.messages.ErrorMessage$WrappedException: io.netty.util.internal.OutOfDirectMemoryError: failed to allocate 16777216 byte(s) of direct memory (used: 4160749568, max: 4175429632)
	at org.apache.cassandra.transport.messages.ErrorMessage.wrap(ErrorMessage.java:486)
	at org.apache.cassandra.transport.Message.encode(Message.java:423)
	at org.apache.cassandra.transport.PreV5Handlers$LegacyDispatchHandler.toFlushItem(PreV5Handlers.java:95)
	at org.apache.cassandra.transport.Dispatcher.processRequest(Dispatcher.java:462)
	...
Caused by: io.netty.util.internal.OutOfDirectMemoryError: ...
	at io.netty.util.internal.PlatformDependent.incrementMemoryCounter(PlatformDependent.java:880)
	at io.netty.util.internal.PlatformDependent.allocateDirectNoCleaner(PlatformDependent.java:809)
	at io.netty.buffer.PoolArena$DirectArena.newChunk(PoolArena.java:693)
ERROR [Native-Transport-Requests-60] 2026-11-12T15:17:41,501 JVMStabilityInspector.java:197 - Force heap space OutOfMemoryError in the presence of
```

`JVMStabilityInspector` (`:105-131`, `:193-197`) turns the direct OOM into a forced heap OOM, so the JVM writes an
hprof and `-XX:OnOutOfMemoryError="kill -9 %p"` kills it (16 `OutOfDirectMemoryError` lines in S-B-1 before that).
Excerpts: `logs/<run>/oom-excerpt.txt`.

### 3.4 Holders at failure (V3/V5)

- **Direct (S):** the Netty counter at every 3982-MiB failure is 4,160,749,568 B = 248 chunks × 16 MiB. Every S
  dump (`logs/hprof-histograms-summary.txt`) holds the chunks and the pending writes:

  | Dump | `PoolChunk` (16 MiB) | `ChannelOutboundBuffer$Entry` | heap shallow total |
  |---|---|---|---|
  | S-B-1 / S-B-2 / S-B-3 | 246 / 247 / 248 | 1,703 / 1,737 / 1,751 | 388 / 381 / 266 MiB |
  | S-A-1 / S-A-2 / S-A-3 | 248 / 244 / 248 | 1,790 / 1,702 / 1,812 | 254 / 406 / 198 MiB |
  | X-S-auto-1 (heap 7965 MiB) | 248 | 1,738 | 273 MiB |
  | X-S-d7936-1 (direct 7936 MiB) | 496 | 3,668 | 310 MiB |
  | SQ-B-2G (ramp) | 246 | 1,534 | 500 MiB |

  Header and body are separate entries, so ≈ 850–900 encoded 3.5 MiB responses (≈ 3 GiB of payload) wait in 64
  outbound buffers at the failure; doubling the direct limit doubles both chunk and entry counts. U (chunks) =
  3,968 MiB > the per-response contract by the factor of the outstanding count; K per read stays 3,670,016 B.
- **Heap (F, P-B-512M, 512 MiB heap):** `logs/P-B-512M/hprof-histogram.txt`: 404 MiB of 472 MiB shallow are
  `byte[]`: 1,655 × 64 KiB cell values (103 MiB), 106 arrays of 1–4 MiB (113 MiB) and 44 of 4–8 MiB (176 MiB) —
  serialized pages and `DataOutputBuffer` growth copies; 27 thread stacks are inside
  `ReadResponse$LocalDataResponse.build` serializing a page. The JVM logged only `java.lang.OutOfMemoryError: Java
  heap space` (stdout) before `kill -9`; no Java stack was logged.

### 3.5 Condition F — fast clients (10 GbE Java driver, 16 connections), server concurrency ≤ 128

Load: 256 reads in flight (NTR active pinned at 128, the rest pending) for 180 s; control 8 in flight; intervention
`native_transport_max_threads: 16` with the same 256-read demand.

| Run | Arm / heap | Outcome | Reads completed | max STW / 60 s | Full GCs | old post-GC max (MiB) |
|---|---|---|---|---|---|---|
| P-B-512M, F-B-1, F-B-2, F-B-3 | B, 512 MiB | **Java heap OOM** @ +41 / +10 / +45 / +25 s | 321 / 114 / 427 / 317 | 40 / 11 / 45 / 27 % | 128 / 31 / 137 / 78 | 414 / 322 / 344 / 369 |
| P-B-640M | B, 640 MiB | **Java heap OOM** @ +25 s | 1,055 | 22 % | 99 | 471 |
| P-B-768M | B, 768 MiB | survived 180 s | 18,915 | 52 % | 792 | 559 |
| P-B-1G | B, 1 GiB | survived 180 s | 28,517 | 51 % | 822 | 755 |
| SW-B-2G (N ≥ 256 steps) | B, 2 GiB | survived | 117,414 (whole sweep) | 28 % | 601 | 446 |
| M-F-B-1/2/3 | B, 512 MiB, 8 in flight | survived 180 s | 15,305 / 19,532 / 33,715 | 60 / 53 / 14 % | 543 / 423 / 66 | 225 / 220 / 217 |
| I-F-1/2/3 | B + 16 threads, 512 MiB | survived 180 s | 12,909 / 13,099 / 13,060 (≈ 71/s) | 68 / 68 / 69 % | 743 / 759 / 754 | 200 / 201 / 195 |
| F-A-1/2/3 | A, 512 MiB | survived 180 s | 7,386 / 8,112 / 7,105 (89 / 8 / 26 client errors) | 83 / 80 / 83 % | 762 / 769 / 779 | 370 / 360 / 368 |
| M-F-A-1/2/3 | A, 512 MiB, 8 in flight | survived 180 s | 36,263 / 35,194 / 28,267 | 10 / 12 / 34 % | 26 / 44 / 208 | 208 / 216 / 216 |

The large client error counts of the failing F runs (millions) are `NoHostAvailableException`s after the victim
died; the reads column counts only successful reads before death. The initiating failure is
`java.lang.OutOfMemoryError: Java heap space` on stdout, followed by the hprof and `kill -9` (no Java stack was
logged). The dumps (P-B-512M, P-B-640M, F-B-1: `logs/hprof-histograms-summary.txt`, `logs/P-B-512M/hprof-histogram.txt`)
are dominated by page-sized `byte[]` (serialized local pages and `DataOutputBuffer` copies: 150–165 arrays of
1–8 MiB, 289–363 MiB) plus 64 KiB cell values, with 27 threads inside `LocalDataResponse.build`. The
`M-F` samples show NTR active up to 32 with 8 client requests in flight (not attributed; possibly driver/system
requests sampled in the same second).

**Arm A vs arm B in F.** With identical reads, arm B (thresholds on) OOMs at 512 MiB 4/4 and arm A (thresholds at
the default) 0/3. Its 8-in-flight controls also GC harder in two of three runs. Enabling the thresholds adds
per-read work: every read exceeds the 1 MiB warn threshold, so each logs a WARN line through the synchronous
`SYSTEMLOG`/`STDOUT` appenders and adds a client warning. One candidate is that this holds a built `ResultSet`
longer on 128 threads. **This is not attributed; it was not tested.** The F endpoint needs the arm-B deviation, a
heap ≤ 640 MiB, and the 128-thread bound of simultaneous reads. Larger heaps survive with 28–52 % STW.

### 3.6 Run record

- 47 controller transcripts in `logs/`. Two runs are invalid, both from harness errors: `SQ-B-2G-aborted-redeploy`
  (I overwrote `victim-ctl.sh` while it was executing) and `logs/batch-S-attempt1.out` (stdin of the batch loop
  consumed by `ssh`; it ran only `I-S-R30-1`, which is kept as the rate-cap attempt). `I-S-A-2` was **void** when the
  researcher paused the run at 17:53. It was stopped before load and rerun at 19:03.
- Label renames before any repeated reading: the fast sweep `S-B-1` was renamed `SW-B-2G` (label collision with
  the batch), and the rate-cap run `I-S-1` was renamed `I-S-R30-1`.
- Lifetimes: 42 valid. Wall: 14:20–17:53 and 19:03–19:20 UTC.
- Cleanup (19:20 UTC): no java process on apt140 or apt138, no batch/controller on pc96, `/mydata/c2/node` removed.
  Run folders and hprofs kept under `/mydata/c2/runs/` on apt140 (≈ 7.9 GB) and client logs on apt138.

## 4. Conclusion

| Condition | Configuration | Endpoint and n/N | Status |
|---|---|---|---|
| **S-A** slow consumers, shipped defaults | thresholds disabled (default), heap 2 GiB, direct auto 3982 MiB | direct OOM 3/3; controls 0/3; intervention 0/3 | **`verified-OOM · deployment`**, **unprotected configuration** (researcher-accepted 2026-11-12) |
| **S-B** slow consumers, thresholds enabled | `test/conf` read thresholds; heap 2 GiB and auto 7965 MiB; direct 3982 / 7936 MiB | direct OOM 3/3 (2 GiB), 3/3 (auto heap), 1/1 (7936 MiB); controls 0/3; intervention 0/3; rate cap 1/1 failed | `verified-OOM · diagnostic` (convergence; supporting deviation: thresholds enabled) |
| **F-B** fast clients, thresholds enabled | heap 512 / 640 MiB | heap OOM 4/4 (512), 1/1 (640); 768 MiB, 1 GiB, 2 GiB survive; controls 0/3; intervention 0/3 | `verified-OOM · diagnostic`; largest failing heap 640 MiB (n = 1) |
| **F-A** fast clients, shipped defaults | heap 512 MiB | 0/3 (80–83 % STW per 60 s, below the 90 % criterion) | `negative` within 512 MiB – 2 GiB at ≤ 256 in flight |

**V1–V7**

| | S-A | S-B | F-B | F-A |
|---|---|---|---|---|
| V1 repetition | S-A-1/2/3: 3/3 | S-B-1/2/3 3/3; X-S-auto 3/3; X-S-d7936-1 1/1 | P-B-512M + F-B-1/2/3: 4/4 | 0/3, no endpoint |
| V2 matched control | M-S-A-1/2/3 0/3 (2176 reads each, ≥ 17 × the failing runs) | M-S-B-1/2/3 0/3 | M-F-B-1/2/3 0/3 (14–60 % STW) | M-F-A-1/2/3 0/3 |
| V3 U apart from K | NMT *Other* ramp (≈ 4.4 MiB per outstanding read), Netty counter 3,968 MiB at failure, `PoolChunk`/outbound entries in dumps; K = 3,670,016 B per read | same; K also via `CoordinatorReadSizeAborts` (only the oversize control) | heap dumps (page buffers), old post-GC, NTR active = 128 | same instruments |
| V4 intervention | client cap 512 outstanding, I-S-A-1/2/3 0/3, same throughput (36 reads/s) | I-S-1/2/3 0/3, same throughput; server rate cap 30/s did **not** remove it (1/1) | `native_transport_max_threads: 16`, I-F-1/2/3 0/3 at ≈ 71 reads/s | — |
| V5 initiating failure | `OutOfDirectMemoryError` in `Message.encode` on a request thread, then forced heap OOM, hprof, `kill -9`; dumps | same | `Java heap space` (stdout), hprof with page buffers and `LocalDataResponse.build` stacks | — |
| V6 defaults | all capacity settings default | read thresholds enabled (deviation) | same | defaults |
| V7 budget | heap 2 GiB, direct auto 3982 MiB (standing rule) | also auto heap 7965 MiB and direct 7936 MiB | 512 / 640 MiB (≥ 512 MiB) | 512 MiB |

**Gap and root cause.** The read-size thresholds cap one query's page and nothing else. Simultaneous reads are
bounded only by `native_transport_max_threads` while being processed. Each finished v4 response is encoded into
Netty pooled direct memory and queued on its channel, and no transport code applies backpressure on pending
outbound bytes. The in-flight limits charge request bytes and release them at hand-off. The rate limiter cannot
stop requests already read. So when clients drain more slowly than the node produces (here 128 MiB/s against
≈ 800 MB/s), outstanding responses × page size fill the direct limit. With 3.5 MiB pages, 16 outstanding per
connection over 64 connections is enough at every budget `cassandra-env.sh` resolves. This is a missing aggregate
control on response memory: per-query limits converge (arm B) or are absent (arm A). It is not a bypass of the
thresholds and not a soft-limit exception. The project documents no response-memory bound.

**Limits of attribution and scope.**
- Protocol v4 only. v5 (`CQLMessageHandler`, framed flusher via the networking `BufferPool`) is untested.
- Single node, so coordinator = replica.
- One page size (3.5 MiB), one drain rate (128 MiB/s aggregate) and one connection count (64).
- The S intervention is client-side, because no server setting bounds outstanding responses; that absence is the
  finding. A server-side fix (stop dispatching while a channel is unwritable, or reserve response bytes against a
  global limit) was not built.
- F needs the arm-B deviation and a small heap. The arm A/B difference in F is unexplained (§3.5).
- Next steps: v5 arm; smaller pages (e.g. 64 KiB) to map the outstanding-count boundary; JIRA search for
  native-transport outbound backpressure before any upstream report.
