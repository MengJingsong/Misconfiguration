# C2 run 1 — design (2026-11-12, written before any reading)

Campaign row C2 (convergence · concurrency/surge, P1). Source: Cassandra 5.0.9 (`systems/cassandra/source/`,
tag `cassandra-5.0.9`), victim build `apt140:~/cassandra-b1` (clean tree, `git describe` = `cassandra-5.0.9`).
Lead source: if-check inventory (capacity-enforcement-exp stage 4: `coordinator_read_size_fail_threshold`
guided + autonomous, `local_read_size_fail_threshold` guided).

**Stopping budget:** 7 h wall from 14:20 UTC (hard stop 21:15 UTC; no new Cassandra lifetime after 20:15 UTC),
at most 40 Cassandra lifetimes, heap ≤ 8 GiB (apt140 has 16 GiB RAM), per-lifetime load ≤ 10 min.

## 1. Source findings (protection map input)

### 1.1 Which per-query thresholds apply to a single-partition CQL read

| Threshold | Default (5.0.9) | Where enforced | Unit | Applies here? |
|---|---|---|---|---|
| `read_thresholds_enabled` (master switch) | **false** (`Config.java:526`; yaml comment "scheduled to be set true in 4.2") | `QueryOptions.ReadThresholds.create()` `:275-281` returns `DisabledReadThresholds` when false; `SelectStatement.java:334` calls `query.trackWarnings()` only when enabled | — | gates the three below |
| `coordinator_read_size_fail_threshold` | **null (unset)** `Config.java:528` | `SelectStatement.maybeFail` `:1057-1080`, per page, before each new row (`processPartition`) | value bytes of the page's `ResultSet` (`ResultSetBuilder.addSize` `:76-82`) | yes, when enabled and set; **binds first** at the accepted values below |
| `local_read_size_fail_threshold` | **null** `Config.java:530` | `ReadCommand.withQuerySizeTracking` `:663-730` inside `executeLocally` (`:457`), only if `trackWarnings` and not a system keyspace | `row.unsharedHeapSize()` incl. cell value bytes (`BufferCell.java:141-144`) | yes (the coordinator's own local read runs `executeLocally` with the command's `trackWarnings`) |
| `row_index_read_size_fail_threshold` | null | RowIndexEntry estimate | index entry bytes | not binding (partitions ≈ 3.5 MiB, a few KiB of index) |
| `tombstone_failure_threshold` | 100,000 (count) | `ReadCommand` `countTombstone` | tombstones | not binding (no tombstones written) |
| `page_size_fail_threshold` (guardrail) | -1 (off) | rows per page | rows | off; and a count, not bytes |
| `cached_rows_*` | row cache off by default | — | — | not on the path |

**Accepted enabled value.** No documented value exists in `cassandra.yaml`; the project's own test configuration
`test/conf/cassandra.yaml:63-69` enables them at `coordinator_read_size_warn/fail = 1024KiB/4096KiB`,
`local_read_size_warn/fail = 4096KiB/8192KiB`, `row_index_read_size_warn/fail = 4096KiB/8192KiB`. These are the
values for the protected arm (B). Each read is sized below every fail threshold: a page of 56 rows × 64 KiB =
3,670,016 value bytes < 4,194,304 (coordinator) and ≈ 3.68 MB `unsharedHeapSize` < 8 MiB (local).

Stage-4 evidence (capacity-enforcement-exp, `results/coordinator_read_size_fail_threshold-*`,
`local_read_size_fail_threshold-addSize-failBytes--guided.md`): both checks refuse exactly at their
per-query limit; the coordinator check is per page and refuses only after the replica built the full
answer (replica answer not withheld). Nothing in either check counts other queries: they are per-query
caps with no aggregate.

### 1.2 What bounds the number of simultaneous reads (aggregate coverage)

| Candidate bound | Source | What it actually bounds |
|---|---|---|
| `native_transport_max_threads` = 128 | `Dispatcher.java:58-61` (SEP `Native-Transport-Requests`) | requests *being processed*; the read blocks this thread (`StorageProxy.readRegular` `:2005`, `awaitResponses` `:2148`). Requests beyond 128 wait in the SEP queue (unbounded, tiny objects). It does **not** bound responses already produced and waiting to be flushed/written. |
| `concurrent_reads` = 32 | `Config.java:179`; `AbstractReadExecutor.java:165` `Stage.READ.maybeExecuteImmediately` | local reads executing (work permits); a finished `LocalDataResponse` (a heap `ByteBuffer` of the serialized page, `ReadResponse.java:182-207`) is handed back and held by the waiting request thread |
| `native_transport_max_request_data_in_flight(_per_ip)` = heap/10, heap/40 | `PreV5Handlers.checkLimits` `:151-217` (`CQLMessageHandler` for v5) | **request** body bytes (`header.bodySizeInBytes`), ≈ 50–100 B per SELECT; responses not charged |
| `native_transport_rate_limiting_enabled` = false, `max_requests_per_second` = 1,000,000 | same | off by default; when on, a rate, not memory |
| `native_transport_queue_max_item_age_threshold` = `Double.MAX_VALUE` | `Config.java:1394`, `Dispatcher.java:348` | off by default |
| `native_transport_receive_queue_capacity` 1 MiB | per channel inbound | inbound bytes only |
| Outbound | `Flusher`, `CBUtil.allocator` (`PooledByteBufAllocator(preferDirect=true)`), `Server` | no response-size or channel-writability admission in `PreV5Handlers`/`Dispatcher`: encoded responses wait in Netty's outbound buffer (pooled direct, 16 MiB chunks via `-Dio.netty.allocator.maxOrder=11`) until the socket drains |
| Protocol stream ids | v4: 32,768 per connection | client-side in-flight per connection; the only cap on outstanding responses is the client's own in-flight count |

**Hypothesis (convergence · concurrency/surge).** Every read is under its per-query threshold (arm B) or
no threshold is on (arm A), but the live working set is ≈ (reads in processing, ≤ 128) × (serialized page +
deserialized/`ResultSet` page) + (responses produced but not yet written) × (encoded page, direct) + heap
`ResultSet`s queued for the flusher. No control sums these. With 3.5 MiB pages, ≈ 128 × 2 × 3.5 MiB ≈ 0.9 GiB
heap in processing alone, plus the outbound backlog bounded only by client in-flight count.

**Predicted protective response:** none on the memory side; per-query checks pass every read; the only
throttles are thread count (128) and TCP/client drain rate. Prediction: at heap 2 GiB, U_heap grows with
actual simultaneous reads up to the 128-thread plateau, and the endpoint (heap OOM or ≥ 90 % STW over ≥ 60 s)
is reached once N_active × ~7 MiB + baseline exceeds ≈ 2 GiB, i.e. N_active ≳ 200–250 if beyond-128
responses also hold heap; if the processing set saturates at 128 and outbound holds only direct memory, the
heap endpoint may not be reachable at 2 GiB and the result would be a direct-memory question (the
auto-resolved direct limit, see §3) or a negative. Both outcomes are acceptable; the boundary is reported.

## 2. Protection map (fixed before the run)

| Domain | Allocation / owner | Local contract | Multiplicity and bound | Lifetime | Budget |
|---|---|---|---|---|---|
| D1 serialized local page | `LocalDataResponse.build` heap `ByteBuffer` (+ `DataOutputBuffer` growth copy) per read | arm B: page ≤ 8 MiB heap-size (local) and ≤ 4 MiB values (coordinator); arm A: none | one per read in processing; ≤ 128 request threads; `concurrent_reads` 32 bounds only execution | read execution → `ResultSet` built | heap |
| D2 coordinator `ResultSet` / `ResultMessage.Rows` | `ResultSetBuilder` value buffers, then the response message until encoded | same per-query cap (counted = value bytes) | one per request in processing **plus** each response queued for the flusher | until `Envelope` encoded on the event loop | heap |
| D3 encoded response | `Message.Response.encode` into `CBUtil.allocator` pooled direct (Netty no-cleaner) | none | one per response not yet written to the socket; bounded only by client in-flight | until the socket accepts it | JVM direct limit (Netty counts against `MaxDirectMemorySize`), NMT *Other* |
| Aggregate | none: no reservation spans D1–D3 | — | — | — | heap and direct |

U is measured per domain apart from K (K = coordinator `CoordinatorReadSize` histogram / aborts meter, local
`LOCAL_READ_SIZE_*` params): U_heap from the GC log (heap after each pause; post-GC old-gen floor) and a heap
dump/histogram at failure; U_direct from NMT `Other` (Netty no-cleaner `Unsafe.allocateMemory`) and the
`java.nio` direct pool; concurrency from `Native-Transport-Requests` Active/Pending and client in-flight.

## 3. Configuration and budget audit

- **Capacity (tested constraints):** arm A `read_thresholds_enabled` absent (default false), thresholds unset
  → **unprotected configuration** (protocol 2026-11-10). Arm B `read_thresholds_enabled: true` + the six
  `test/conf` values above (an enabled, accepted value; each read below it). Everything else default:
  `native_transport_max_threads` 128, `concurrent_reads` 32, in-flight limits heap/10 and heap/40, rate
  limiting off, `file_cache_size` auto, row cache off, `memtable_allocation_type: heap_buffers`.
- **Environment:** `listen_address`/`rpc_address`/seeds 10.10.1.1, data/commitlog/hints/saved_caches/cdc under
  `/mydata/c2/node` (same edits as B1's `victim-ctl.sh`); JVM extra `-XX:NativeMemoryTracking=summary` and
  `-Xlog:gc=info,safepoint=info` to the run folder (instrumentation, low overhead).
- **Budget:** heap via `MAX_HEAP_SIZE` (2 GiB first, then 4 GiB, then 7808 MiB ≈ the node's auto-resolved
  heap; bisect if 4 fails and 7.8 survives); `MaxDirectMemorySize` left to `cassandra-env.sh`, which resolves
  it to ¼ RAM on apt140 (`free -m` total / 4, recorded per lifetime from the JVM command line). Standing rule:
  heap ≥ 512 MiB and direct ≥ 512 MiB meet V7 without per-case review; 2 GiB is ideal. Auto-resolved values
  for apt140 (16 GiB): heap ½ RAM ≈ 7.8 GiB, direct ¼ RAM ≈ 3.9 GiB. No cgroup limit, swap left on (8 GiB
  partition; the JVM heap is fixed-size `-Xms=-Xmx` and fits in RAM; recorded).
- **Supporting deviations:** none on the victim. Intervention arm only: `native_transport_rate_limiting_enabled:
  true`, `native_transport_max_requests_per_second: R` (R set from the calibration, below the drain rate).
- **Client:** protocol v4 (Java driver 3.12.1 shaded from `apt138:~/cassandra-c1/build/lib/jars`), CL ONE,
  16 connections to the victim (several application instances' worth), prepared `SELECT v FROM c2.t WHERE pk=?`,
  fetch size 5000 (one page), closed loop with N total in flight. v5 not tested (driver 3.x V5 is beta).
  Disclosed as a limit.

## 4. Workload and data

Keyspace `c2` (SimpleStrategy RF 1), `c2.t (pk int, ck int, v blob, PRIMARY KEY (pk, ck))`.
- 64 partitions × 56 rows × 64 KiB random values = 3,670,016 value bytes per partition (224 MiB total), flushed
  to SSTables (`nodetool flush`) before reads; one oversize partition pk = 1000 with 72 rows (4.5 MiB).
- Read: random pk ∈ [0, 64) per request.

## 5. Arms and repetitions (each a clean start: fresh node dir, fresh load)

| Arm | Config | Load | Purpose | Reps |
|---|---|---|---|---|
| S-A, S-B | A / B, heap 2 GiB | N = 8, 32, 128, 256, 512, 1024 in one lifetime, 90 s per step, stop at endpoint | calibration: U vs actual concurrency; pick N_fail | 1 each |
| R | B | one read of pk 1000 (4.5 MiB) and one of pk 0, then the load | rejection control: oversize refused (`ReadSizeAbortException`, `CoordinatorReadSizeAborts` +1), under-size passes | in every B lifetime |
| F-A, F-B | A / B, heap 2 GiB | N_fail for ≤ 300 s | failing condition | ×3 each |
| M-A, M-B | A / B, heap 2 GiB | N = 8 until it has completed as many reads as the median F run did (cap 600 s) | matched control: same total data at low concurrency | ×3 each |
| I-B | B + rate limit R, heap 2 GiB | N_fail ≤ 300 s | intervention (bound admitted concurrency); record throughput | ×3 |
| X-B | B, heap 4 GiB, 7.8 GiB (bisect between) | N_fail (and up to 2× N_fail if the larger heap survives at N_fail) | largest failing budget, n/N per budget | ×3 at the largest failing, ≥ 1 at the surviving |

**Endpoint (fixed):** Java heap OOM (`java.lang.OutOfMemoryError` in `system.log`/`stdout`, or Netty
`OutOfDirectMemoryError`, or JVM death with an hprof) **or** service loss: ≥ 90 % of wall time in STW pauses
over a window ≥ 60 s (protocol default; `gcwin.py` from B6 run 4). A client timeout storm without either is
not an endpoint.

**Measurements per lifetime:** 1 s JMX sampler (heap used, NTR Active/Pending/Completed, ReadStage
Active/Pending, java.nio direct, CoordinatorReadSize aborts, client connections), NMT summary + RSS every
10 s, GC log, client per-second CSV (ok, errors by class, in-flight, MB/s, p50/p99 latency), `system.log`,
hprof on OOM (`-XX:+HeapDumpOnOutOfMemoryError` default, dir = run folder). On survivors: final
`jcmd GC.class_histogram` (live, after the load) only in calibration lifetimes.

## 6. Outcome rules

- Endpoint ≥ 3/3 in F-B, 0/3 in M-B, 0/3 in I-B with useful throughput recorded → protected arm meets V1–V5;
  with V6 (all tested constraints default or at the accepted enabled value — note: arm B's constraints are
  *enabled* non-defaults; V6 is met for arm A, and arm B is the accepted documented value requested by the
  campaign, labelled so) and V7 (heap ≥ 512 MiB) → `verified-OOM`/`verified-gap` · convergence.
- Arm A failing → labelled **unprotected configuration**, not a bypass.
- No endpoint at 2 GiB within N ≤ 1024 → `negative` within that range, with U vs N reported.
- Results stay in `candidates/` in this run; the researcher moves folders (shared docs not edited by this run).

## Amendment 1 — 2026-11-12 15:16 UTC (after calibration, before any repeated reading)

Calibration readings so far (SW-B-2G, P-B-512M, P-B-1G, Q-B-2G, SQ-B-2G, I-S-R30-1) changed the design:

1. **Two conditions instead of one.** (F) *fast clients* (Java driver, 16 connections, 10 GbE): server concurrency
   saturates at `native_transport_max_threads` = 128 (N ≥ 256 adds only pending tasks); at heap 2 GiB no endpoint
   (max 28 % STW per 60 s), 1 GiB survives (51 %), 512 MiB heap OOM. (S) *slow consumers* (raw v4 client, 64
   connections, aggregate drain 64 × 2 MiB/s = 128 MiB/s, i.e. ≈ one 1 GbE client NIC): encoded responses wait in
   Netty's outbound buffer in pooled direct memory; outstanding responses are bounded only by the client's
   in-flight count; NMT *Other* grows ≈ 4.4 MiB per outstanding 3.5 MiB read and 1024 outstanding reach Netty
   `OutOfDirectMemoryError` at the auto-resolved 3,982 MiB limit with a 2 GiB heap.
2. **Correction to §2 D2/D3:** in v4 the response is encoded on the request thread
   (`PreV5Handlers.LegacyDispatchHandler.toFlushItem` → `Message.encode`, `PreV5Handlers.java:91-97`), so the heap
   `ResultMessage` is released early and the outbound backlog is direct memory only.
3. **Intervention for S replaced.** `native_transport_rate_limiting_enabled` + 30 req/s (`I-S-R30-1`, n = 1) did
   not remove the endpoint (direct OOM at +11 s): requests already read from a socket are dispatched even when
   backpressure is applied (`PreV5Handlers.java:85-87`), and in-flight request bytes are released when the
   response is handed to the flusher, not when it drains (`:99-110`). No server setting bounds outstanding
   responses, so the S intervention is a **client-side outstanding cap of 8 per connection (512 total)** under the
   same drain, ×3; the matched control is 2 per connection (128 total) for 60 s (≥ the failing runs' completed
   reads), ×3 per arm.
4. **F runs at heap 512 MiB** (the standing-rule minimum; 768 MiB probed once to bound the largest failing heap),
   N = 256 vs control N = 8, intervention `native_transport_max_threads: 16` (server-side concurrency cap), ×3.
5. **S budget search:** heap is not the binding domain; run S at the fully auto-resolved heap (MAX_HEAP_SIZE unset,
   ½ RAM) ×3 and once at the largest direct limit `cassandra-env.sh` can resolve (7,936 MiB) with 2048 outstanding.

## Resume note — 2026-11-12 17:53 UTC (paused by the researcher's request)

**State:** every process stopped; nothing runs on apt140 or apt138 (verified, 0 java on both). `I-S-A-2` was
stopped about 1 min after start, before any load. It is **void**: controller log `logs/controller-I-S-A-2-VOID-stopped.out`,
node data `/mydata/c2/runs/I-S-A-2-VOID`. Elapsed wall: 14:20–17:53 (3 h 33 min of the 7 h budget).

**Done (summary in `python3 harness/summarize.py logs`):**
- Calibration: SW-B-2G (fast sweep), P-B-512M/768M/1G, Q-B-2G, SQ-B-2G (slow ramp); SQ-B-2G-aborted is my
  redeploy error and is invalid.
- Condition S (slow consumers, 2 GiB, direct auto 3982M): S-B 3/3 direct OOM, S-A 3/3, M-S-B 0/3, M-S-A 0/3,
  I-S (client cap 512) 0/3, I-S-R30-1 rate cap failed (OOM 1/1), X-S-auto 3/3 (heap 7965M), X-S-d7936-1 1/1.
  I-S-A-1 survived (1/3 done).
- Condition F (fast clients, 512 MiB): F-B 3/3 heap OOM (+ P-B-512M), M-F-B 0/3, I-F (T16) 0/3, F-A 0/3
  (80–83 % max STW), M-F-A 0/3. 768 MiB and 1 GiB survive.

**Remaining:** I-S-A-2, I-S-A-3 (arm-A V4), P-B-640M (F bisection). Then: hprof histograms of the S dumps on apt140
(`python3 /mydata/c2/harness/hprofhist.py /mydata/c2/runs/<run>/*.hprof 400`) for V3/V5, fill case-file §3.5, §3.6
and §4, and clean up `/mydata/c2/node`. Do not modify `victim-ctl.sh` while a lifetime is running.

**Exact commands to continue (from pc96, in the case folder):**
```
cd /proj/misconfiguration-PG0/git-repos/Misconfiguration/experiments/OOM-exp/cassandra/cases/candidates/coordinator_read_size_fail_threshold-concurrent-reads
nohup bash harness/batch.sh harness/arms-F.txt > logs/batch-F-resume.out 2>&1 &
```
`batch.sh` skips labels that have a `logs/<label>/gcwin.txt`, so it runs only I-S-A-2, I-S-A-3 and P-B-640M. That is
about 15 min. Afterwards, check that no `CassandraDaemon`/`C2Sampler`/`slowread`/`C2Load` process is left on either node.

## Researcher review (2026-11-12, relayed by the coordinating session)

- **S-A (shipped defaults, slow consumers):** status `verified-OOM · deployment`, tagged **unprotected
  configuration**, accepted by the researcher — conditional on the remaining arm-A intervention runs
  (I-S-A-2, I-S-A-3) completing so V4 is 3/3.
- Still open: whether the read thresholds enabled at the `test/conf` values (arms B: S-B, F-B) count as an
  accepted setting (`deployment`) or a supporting deviation (`diagnostic`).
- **Update (2026-11-12, researcher):** thresholds enabled at the `test/conf` values (arms B: S-B, F-B) are a
  **supporting deviation** → `diagnostic`. The acceptable read-threshold value is to be discussed later.
