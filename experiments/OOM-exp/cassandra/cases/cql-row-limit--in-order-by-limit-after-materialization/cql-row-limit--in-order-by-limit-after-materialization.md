# B17 — CQL row limit: IN on the partition key + ORDER BY reads every listed partition whole before LIMIT, and paging is refused  <!-- file: cassandra/cases/cql-row-limit--in-order-by-limit-after-materialization/cql-row-limit--in-order-by-limit-after-materialization.md -->

| Field | Value |
|---|---|
| Case ID | `B17` (B = bypass; README "ID prefixes") |
| From | `OC-320` of the phase 1 OOM candidate list (cluster of one row, primary OC-320; picked in wave 4) |
| Phase-1 case file | [`cql-row-limit-incrementRowCount-rowsCounted--autonomous`](../../../../capacity-enforcement-exp/cassandra/stage3-ai-deep-read/cases/cql-row-limit-incrementRowCount-rowsCounted--autonomous.md) |
| System / pinned source | Cassandra 5.0.9 (`systems/cassandra/source/`, `build.xml` `base.version` 5.0.9); built copy `pc72:/mydata/s4/cassandra-base` |
| Stage 1 (design) | phase-2 OOM agent, stage 1 session, 2026-11-18 13:38–13:50 EST; nothing run (read-only checks of pc72 only) |
| Stage 2 (verify) | phase-2 OOM agent, stage 2 session (fresh), 2026-11-18 13:49–15:31 EST on `pc72`; freeze hash checked (match) |
| Verdict | **true positive** — `verified-OOM · deployment`, bypass (exempt path) on an unprotected configuration |

## Summary

- **Conclusion (stage 2):** **true positive.** One unpaged `SELECT * … WHERE pk IN (4 keys) ORDER BY ck LIMIT 10` —
  a query whose answer is 10 rows (2.5 MiB) — kills a single node at the budget `cassandra-env.sh` resolves for a 4 GiB
  node (heap 2 GiB, direct 1 GiB, every capacity at its shipped default) with `java.lang.OutOfMemoryError: Java heap
  space`, **3/3** (`T-2G`), and also in the calibration run. The matched control (same IN and LIMIT without `ORDER BY`)
  survives 3/3, also under a 120 s closed loop at 175–181 queries/s; restoring the missing bound (`PER PARTITION LIMIT
  10`) returns the same 10 rows and survives 3/3. Largest failing budget: **8 GiB heap / 4 GiB direct**, 3/3, with
  **4 concurrent** such queries over 6 partitions; at 31,744 MiB / 15,872 MiB no OOM up to 96 concurrent queries (the
  5 s read timeout cancelled 97.8 % of them first).
- **Root cause:** for `IN` on the partition key plus `ORDER BY`, `getDataLimits` leaves the read's row limit at
  `NO_LIMIT` and paging is refused, so every listed partition is serialized whole into its own replica
  `DataOutputBuffer` (heap) and then copied into the coordinator `ResultSet` before `LIMIT 10` is applied. Nothing
  bounds those bytes at defaults: the read-size thresholds ship off, the `partition_keys_in_select` guardrail is off
  (and counts keys), and the 5 s read timeout bounds time, not bytes (≈ 600 MB/s of serialization fits in it).
  The dumps hold 4 replica buffers of 216–324 MiB (1,188–1,296 MiB) at 2 GiB, up to 22 of them (6,157 MiB) at 8 GiB.
- **Hypothesis (stage 1):** with `IN` on the partition key plus `ORDER BY`, Cassandra needs post-query ordering, so
  it drops the user's `LIMIT` from the read (`cqlRowLimit = NO_LIMIT`) and refuses paging; the client must run the
  query unpaged. Every row of every listed partition is serialized into one replica heap buffer per partition and
  then copied into the coordinator `ResultSet`, and only then sorted and trimmed to `LIMIT 10`. At shipped defaults
  (read thresholds off, `partition_keys_in_select` guardrail off) nothing bounds those bytes except the 5 s read
  timeout. Four 256 MiB partitions in one `LIMIT 10` query (≈ 2.3 GiB held) should exhaust a 2 GiB heap while
  returning 2.5 MiB.
- **Overlap with U4 (verified):** the same two holders (replica `DataOutputBuffer` per partition, coordinator
  `ResultSet`), but here neither the user's `LIMIT` nor paging can bound them, the held bytes grow with the number
  of partitions in `IN` (not with concurrency or the client's page size), and the response is tiny, so Netty
  direct memory (where U4 failed above 2 GiB) is not involved.

## 1. Candidate

**Cluster rows (the cluster assigned for B17 is one row, OC-320; quoted from `phase1-oom-candidates.md`):**

> | OC-320 | 2026-11-18 | `cql-row-limit-incrementRowCount-rowsCounted--autonomous` | guided | Post-query ordering skips the user LIMIT. With IN on the partition key plus ORDER BY, getDataLimits leaves cqlRowLimit=NO_LIMIT, and paging is rejected for such queries, so every row of every listed partition is read, serialized and built into the ResultSet before the user's LIMIT trims the result. [details](runs/wave2.md#oc-320) | CP-10, CP-12, CP-6 | picked: B17 |

Full text (`runs/wave2.md#oc-320`): *"Holder: the replica response buffers and the coordinator ResultSet. Why nothing
stops it: the LIMIT is applied only after everything is collected, paging cannot be used, partition_keys_in_select_\*
is -1 (off), and no read-size threshold is on. Size: the sum of the IN partitions' live data, so `... WHERE pk IN
(k1..k100) ORDER BY ck LIMIT 10` over 100 MB partitions materializes about 10 GB (more with the 2x
replica-plus-coordinator copy) to return 10 rows. Where: SelectStatement.java:889-896,537-538,1174; Config.java:875."*

Triage (`runs/triage-2026-11-18.md`, rank 8): *"default-reachable yes; single ARM node; … Two partitions of about 1 GB
each give about 2 GB of replica buffers plus about 2 GB of ResultSet in one query, past a 2 GiB heap. Overlaps: Same
holders as U4, but the bypass is new: neither LIMIT nor paging can be applied. Duplicates OC-308."* It is listed among
the "likely fastest first wins, one request or one read on a single 2 GiB node".

**Coverage.** The design covers **OC-320** completely: its trigger (IN on the partition key + ORDER BY + LIMIT,
unpaged), both holders (replica buffers, coordinator `ResultSet`) and its claimed size relation (Σ live data of the
listed partitions × ≈ 2.3). It does **not** cover anything outside that row: not the unpaged-aggregate and GROUP BY
rows of the paging-off family (OC-298, OC-309–OC-318, OC-321, OC-322), not the IN cartesian-product rows (OC-351,
OC-365, OC-412) and not the ANN index-ordering branch of `needsPostQueryOrdering()` (`needIndexOrdering()`, which
keeps the user limit). **Related row outside the assigned cluster:** OC-308 (same phase-1 case, same mechanism, the
triage calls it a duplicate of OC-320) is quoted here for reference; this design tests its mechanism too, but its
list status is not changed by stage 1:

> | OC-308 | 2026-11-18 | `cql-row-limit-incrementRowCount-rowsCounted--autonomous` | autonomous | With an IN on the partition key plus ORDER BY (post-query ordering), the row limit is turned off: cqlRowLimit stays NO_LIMIT and the user LIMIT is applied only after every row of every listed partition is in the ResultSet. [details](runs/wave2.md#oc-308) | — | open |

**Phase-1 constraint and check.** `CQLLimits.rowLimit` (`DataLimits.java:349`), checked by
`if (++rowsCounted >= rowLimit) stop();` (`DataLimits.java:509-510`). The phase-1 case's estimate is `negative`
(the count does not cap bytes); stage 4 (pc12, 2026-10-27,
[results](../../../../capacity-enforcement-exp/cassandra/stage4-runtime-verification/results/cql-row-limit-incrementRowCount-rowsCounted--autonomous.md))
confirmed "does not cap" in both tiers: at a fixed LIMIT retained heap grows with row width (unit m(64 KiB)/m(16 B) =
218.6; cluster ×4.04 allocation per payload byte), and `local_read_size_fail_threshold: 20MiB` capped the same reads.
The recheck of 2026-11-17 (pc75, 8 GiB heap) measured one `LIMIT N` read or one N-row page holding **2.0–2.4 × N × W**
at the coordinator's end of the read (replica `DataOutputBuffer` 1.0–1.4 ×, growth ×2 to 64 MiB then ×1.5, plus the
`ResultSet` 1.0 ×). Neither stage-4 run used IN + ORDER BY; this case's path (the limit removed by post-query
ordering) was not run before.

**Path checked against the pinned source (2026-11-18).**
- `getDataLimits` (`SelectStatement.java:880-896`): `if (!needsPostQueryOrdering() || needIndexOrdering())
  cqlRowLimit = userLimit;` — with IN on the partition key and an ORDER BY, `needsPostQueryOrdering()` is true
  (`:1156-1160`) and `cqlRowLimit` stays `NO_LIMIT`; `cqlPerPartitionLimit = perPartitionLimit` (`:896`, NO_LIMIT
  unless the query says `PER PARTITION LIMIT`).
- Paging is refused: with a page size > 0, `query.limits().count()` (NO_LIMIT) > page size, so the pager path is
  taken (`:338`), where `checkFalse(pageSize > 0 && needsPostQueryOrdering(), "Cannot page queries with both ORDER BY
  and a IN restriction on the partition key; … or disable paging for this query")` throws (`:537-539`). The client
  has to send page size ≤ 0 (Java driver 3.12.1: `setFetchSize(Integer.MAX_VALUE)` is sent as −1, checked with
  `javap` on `SessionManager` in pc72's shaded jar, 2026-11-18).
- Unpaged execution (`:427-429`) → `StorageProxy.fetchRows` (`StorageProxy.java:2106-2171`): one read executor per
  partition; all `executeAsync()` first, then all `awaitResponses()`, then `PartitionIterators.concat` of every
  result (`:2170`). On one node each local read runs inline on the request thread when a READ permit is free
  (`AbstractReadExecutor.java:165` → `SEPExecutor.java:218-239`), so the partitions are read **one after another**
  and every response stays referenced until the query ends.
- Each local read serializes its whole partition into one heap `DataOutputBuffer` (`ReadResponse.java:197-201`;
  initial 128 B, ×2 up to 64 MiB, then ×1.5, `DataOutputBuffer.java:155-180`, max ≈ 2 GiB per buffer).
- Coordinator: `process` builds the full `ResultSet` from every partition (`SelectStatement.java:994-1014`), then
  `orderResults` sorts it (`:1172-1180`) and `cqlRows.trim(userLimit)` cuts it to the user's LIMIT (`:1019`).
- Byte controls: `query.trackWarnings()` only if `read_thresholds_enabled` (`:334-335`); it ships `false`
  (`Config.java:526`, `cassandra.yaml:2015`), with every read-size threshold null. Guardrails
  `partition_keys_in_select_*` = −1 (`Config.java:875-876`, `cassandra.yaml:2098-2099`; a count of partitions, not
  bytes) and `in_select_cartesian_product_*` = −1.
- **Time bound (not a memory bound):** each local read gets `setMonitoringTime(requestTime.startedAtNanos(), …,
  deadline − start)` with `deadline = min(start + read_request_timeout, client deadline)` (`StorageProxy.java:2204-2205`,
  `Dispatcher.java:238-245`); `QueryCancellationChecker` (`ReadCommand.java:743-791`) aborts the local read with
  `QueryCancelledException` once the **query** is older than `read_request_timeout` (5,000 ms, `cassandra.yaml:1322`),
  and the read then fails (`StorageProxy.java:2221-2236`). Because the partitions are read in sequence from the same
  start time, **all listed partitions must be serialized within 5 s** of the query start. Building the `ResultSet`
  after the reads is not covered by this check. Stage 2 must calibrate the serialization rate (§2 PROBE).
- The same code is on the `cassandra-5.0` branch and on trunk (`SelectStatement.java` trunk `:671`, `:1037-1038`,
  fetched from GitHub 2026-11-18): not fixed upstream.

**JIRA prior art (read only; nothing posted).** Survey
[`jira-oom-survey.csv`](../../../../capacity-enforcement-exp/cassandra/stage5-oom-clue-find/jira-oom-survey.csv):
CASSANDRA-9454 (*Log WARN on Multi Partition IN clause Queries*, an OOM from a multi-partition IN read, resolved
via the 17186 guardrails, which ship at −1), 15250 (IN cartesian product OOM, unresolved), 4304 (*Add bytes-limit
clause to queries*, Later), 6052 (unpaged huge LIMIT, Duplicate). JIRA REST searched 2026-11-18 13:55 EST:
`text ~ "\"post-query ordering\""` → 3 hits: **CASSANDRA-6722** *cross-partition ordering should have warning or be
disallowed when paging* (Fixed 2.0.6: the origin of the paging refusal; Sylvain Lebresne: "we can't … properly do
post-query reordering in general if we page"; the reporter: "that would require all results to be collated up
front"); **CASSANDRA-11556** *PER PARTITION LIMIT does not work properly for multi-partition query with ORDER BY*
(Fixed 3.6: `PER PARTITION LIMIT` is honoured with post-query ordering; this is what arm I below relies on); 10707
(GROUP BY). `text ~ "\"Cannot page queries with both ORDER BY\""` → 4 hits (7853, 9970, 10363, 10556), all result
order or NPE bugs, none on memory. `text ~ "\"ORDER BY\"" AND text ~ "IN" AND text ~ "LIMIT" AND (text ~ OOM OR
text ~ memory)` → 0 hits; a broader `… AND text ~ partition AND created >= 2016-01-01` → 59 hits, none about the
user LIMIT not being pushed to the partitions. **Verdict: `by design`** for refusing paging (6722) and
**`new`** for the memory consequence: no issue asks to push the user LIMIT into each partition's read for
clustering-column ordering (which is exact: each partition is already in ORDER BY order, so the global top N is
among each partition's top N). Not known-fixed; not a positive control.

## 2. Design solution (stage 1; frozen)

**Mechanism.** Direction: **bypass (exempt path)** of the CQL row limit and of paging (protocol: "a path … allows
allocations outside a control's protection"), on top of an **unprotected configuration** (the read-size byte
thresholds ship off). Technique note: [`bypass-playbook.md`](../../../bypass-playbook.md) (compare the protected and
the exempt path at matched data). One unpaged `SELECT * FROM b17.t WHERE pk IN (p1..pk) ORDER BY ck LIMIT 10`:
`getDataLimits` leaves the row limit at `NO_LIMIT` (`SelectStatement.java:894-895`); the request thread reads the k
partitions in sequence, each into its own heap `DataOutputBuffer` (`ReadResponse.java:199-201`), keeps all k
buffers, then copies every row into the `ResultSet` (`:1004-1014`) and only then sorts and trims to 10 rows
(`:1017-1019`). Held at the end of the reads ≈ Σ buffers (1.0–1.4 × D) + `ResultSet` (1.0 × D), D = Σ live data of
the k partitions. The control's contract (C) is the user's LIMIT: 10 rows (2.5 MiB here); its counter (K) is the
returned row count (10); U ≈ 2.3 × D. U > C with K ≤ C → **bypass, exempt path**.

**Protection map** (fixed before any run).

| Domain | Holder (allocation → release) | Counter K | Limit at default | At the limit |
|---|---|---|---|---|
| User LIMIT (CQL row limit) | replica `DataOutputBuffer` per partition (`ReadResponse.java:199`) and coordinator `ResultSet` (`SelectStatement.java:1004-1014`) → released when the query ends | `rowsCounted` vs `cqlRowLimit`; rows returned | **`NO_LIMIT`** in the read (post-query ordering, `:894-895`); LIMIT 10 applied by `trim` after the full `ResultSet` (`:1019`) | nothing in the read → **bypass (exempt path)** |
| Paging (page size in rows) | same holders | page rows | **refused** for this shape (`:537-539`); client must page ≤ 0 | the query fails if paged (`InvalidRequest`) |
| Per-partition limit | same holders | per-partition rows | NO_LIMIT unless `PER PARTITION LIMIT` (`:896`) | arm I sets it |
| Read-size thresholds | same holders (local: `row.unsharedHeapSize()` per partition read; coordinator: `ResultSetBuilder` bytes) | bytes | **off** (`read_thresholds_enabled: false`, thresholds null) | nothing → unprotected configuration |
| `partition_keys_in_select` guardrail | — | partitions in IN | −1 (off); counts keys, not bytes | nothing |
| Read timeout (time, not memory) | local reads of the query | elapsed time since query start | 5,000 ms (`read_request_timeout`) | local read aborted (`QueryCancelledException`), query fails; `ResultSet` phase not covered |
| Concurrency | one query = k sequential local reads on one request thread | NTR threads; READ permits | 128 NTR threads; 32 READ permits (inline local reads) | queue; no byte sum across queries |
| Native in-flight request bytes | request body (≈ 100 B + k × 4 B) | request bytes | heap/10, per IP heap/40 | does not cover response or read memory |
| Encoded response (ledgered, not claimed) | Netty direct buffer of the 10-row response (≈ 2.5 MiB) | — | `MaxDirectMemorySize` | negligible here (contrast U4/C2) |
| Baseline | memtable heap pool (H/4, empty: read-only), key cache (min(5 % H, 100 MiB)), chunk cache (direct, `file_cache_size` = min(512 MiB, H/4)), networking pool 128 MiB direct | own counters | defaults | evict / flush |

**Configuration and budget audit.**
- Source/build: `pc72:/mydata/s4/cassandra-base` (cassandra-5.0.9, `build/apache-cassandra-5.0.9-SNAPSHOT.jar`,
  copied and smoke-tested 2026-11-18), copied to `$ROOT/tree` with `ROOT=/mydata/s4/b17-w1`. JDK 11.0.33 (checked
  2026-11-18), G1 with the shipped `jvm11-server.options` (`G1HeapRegionSize=16m`, `MaxGCPauseMillis=300`),
  `HeapDumpOnOutOfMemoryError` and `OnOutOfMemoryError="kill -9 %p"` from `jvm-server.options`. Ubuntu 22.04, kernel
  5.15, cgroup v2. Record `uname -r`, `java -version`, jar sha256 in every `run.meta`.
- **Every capacity constraint at its shipped default (V6):** `read_thresholds_enabled: false` and thresholds null;
  `partition_keys_in_select_*` −1; `in_select_cartesian_product_*` −1; `page_size_*` −1; `native_transport_max_threads`
  128; `concurrent_reads` 32; `read_request_timeout` 5,000 ms and `native_transport_timeout` 12 s (**not raised**);
  memtable, key/row/chunk caches at defaults; `num_tokens` 16; `AllowAllAuthenticator`. The only constraints changed
  are in arm I2 (optional).
- `cassandra.yaml` diff from the shipped file (environment only): `data_file_directories`, `commitlog_directory`,
  `hints_directory`, `saved_caches_directory`, `cdc_raw_directory` under `$ROOT/node/`. Addresses stay `localhost`
  (client on the same node, loopback). Save `yaml.diff` per lifetime.
- **Budgets** (V7; standing rule: heap and direct ≥ 512 MiB meet V7, 2 GiB ideal; search upward):
  - **Primary: heap 2,048 MiB / direct 1,024 MiB** — exactly what the shipped `cassandra-env.sh` resolves for a
    4 GiB-RAM node (½ RAM = 2,048 MiB heap, ¼ RAM = 1,024 MiB direct, `cassandra-env.sh` `calculate_heap_sizes`).
    Set both explicitly (`MAX_HEAP_SIZE=2G`, `MAX_DIRECT_MEMORY_SIZE=1024M`) and record `-Xmx` and
    `-XX:MaxDirectMemorySize` from `ps`.
  - **Upward search** (node classes `cassandra-env.sh` resolves): 4,096 / 2,048 MiB (8 GiB node), 8,192 / 4,096 MiB
    (16 GiB node), 31,744 / 15,872 MiB (any node ≥ 64 GiB under G1 — also pc72's own resolution).
  - **No container budget.** Victim in `systemd-run --user --scope -p MemoryMax=<heap+direct+8G> -p
    MemorySwapMax=0` for isolation only (swap off). A scope `oom_kill` makes the lifetime **invalid**; record
    `memory.events` at the end of every lifetime.
- Disk/RAM/cores fit (pc72, read-only check 2026-11-18 13:42 EST = 11:42 MST on the node): x86_64, 40 cores,
  125 GiB RAM (123 GiB free), 8 GiB swap (excluded), `/mydata` 714 GiB free, `/dev/shm` 63 GiB; no java process,
  load 0.00; `/mydata/s4/` holds only `cassandra-base`. Needs: tree 0.5 GiB + template 4.1 GiB + node copy 4.1 GiB
  + hprofs (≈ 2 GiB each at 2 GiB heap, up to 31 GiB each at the largest) < 150 GiB; RAM: victim ≤ 31.7 + 15.5 GiB +
  client 4 GiB + page cache.

**Ceiling arithmetic.** Data: W = 262,144 B (256 KiB) per value, 1,024 rows per partition → P = 268,435,456 B =
**256 MiB** of values per partition (+ ≈ 30 B per row of row framing). Per partition, the replica buffer grows
64 → 96 → 144 → 216 → **324 MiB** (final capacity 1.27 × P); during its last growth 216 + 324 = 540 MiB are live
at once. In the `ResultSet` each partition adds 256 MiB of value copies (+ ≈ 0.3 MiB of row objects).
For one query over k partitions (D = 256 k MiB):
- reading phase, while partition j + 1 grows its last step: 324 j + 540 MiB;
- `ResultSet` phase (after all reads, not time-limited): up to **580 k MiB** (324 k buffers + 256 k copies).

Heap baseline (read-only, memtables empty, key cache tiny): 150–300 MiB; humongous arrays (≥ 8 MiB with 16 MiB
regions; a 324 MiB buffer takes 21 contiguous regions) can make the effective limit lower. No contract capacity
bounds this: Σ contract capacities is unbounded (LIMIT not applied, paging refused, thresholds off, guardrail off);
the only implicit bound is the 5 s read window × serialization rate r per query, × concurrency.
- **2,048 MiB heap (usable ≈ 1,750–1,900):** k = 3 → 1,740 MiB (borderline); **k = 4 → 2,320 MiB → OOM in the
  `ResultSet` phase**; k = 5 → reading phase 1,296 + 540 = 1,836 MiB (OOM possible in `expandToFit` already).
  Predicted smallest failing k (c = 1): **k_T = 4 (band 3–5)**, which needs 1 GiB read within 5 s (r ≥ ≈ 215 MB/s).
- Fallback if r is too low for k_T in 5 s: c concurrent queries at k_c (below): c × 580 k_c MiB; at k_c = 2,
  c = 2 → 2,320 MiB.
- 4,096 MiB heap (usable ≈ 3,800): c = 1 needs k ≥ 7 (1.75 GiB in 5 s); at k_c = 2: c ≥ 4; at k_c = 4: c ≥ 2.
- 8,192 MiB (usable ≈ 7,900): k_c = 2: c ≥ 7; k_c = 4: c ≥ 4.
- 31,744 MiB (usable ≈ 31,000): k_c = 2: c ≥ 27; k_c = 4: c ≥ 14 (concurrent queries overlap only partly, so the
  real c is higher; NTR has 128 threads, pc72 40 cores).
Direct memory per query: one 10-row response ≈ 2.5 MiB, plus the chunk cache (≤ 512 MiB at 2 GiB heap) — below
1,024 MiB; **a direct OOM is not predicted** and would be outside this design's claim (see verdict rules).

**Workload and environment.**
- Node `pc72` only (victim = one Cassandra node, coordinator = replica; client = one Java-driver JVM on the same node,
  loopback). Before every lifetime: refuse to start if any `CassandraDaemon` runs (another case may share the node:
  wait in bounded polls up to 20 min, then record the block). Work only in `ROOT=/mydata/s4/b17-w1`; do not touch
  `/mydata/s4/cassandra-base` beyond copying it. pc72's clock is MST (EST − 2 h): log in EST
  (`TZ=America/New_York`).
- Schema: `CREATE KEYSPACE b17 WITH replication = {'class':'SimpleStrategy','replication_factor':1}`;
  `CREATE TABLE b17.t (pk int, ck int, v blob, PRIMARY KEY (pk, ck))` with **default table options** (LZ4 16 KiB
  chunks, STCS, clustering ASC).
- Data: **16 partitions (pk 0–15) × 1,024 rows (ck 0–1023) × 262,144 random bytes** (`new Random(pk * 100003L +
  ck).nextBytes`), 4 GiB of values. Each write is 256 KiB (below `max_mutation_size` 16 MiB, `max_value_size`
  256 MiB).
- Load once (lifetime `LOAD`, heap 8G / direct 4096M, not a reading): schema; inserts at 16 concurrent async
  (CL ONE), each failed insert retried up to 5 times (report failures; U4 saw 178 write timeouts without retry);
  `nodetool flush b17`; `nodetool compact b17` (wait); `nodetool drain`; SIGTERM; then
  `cp -a $ROOT/node $ROOT/template` and `rm -rf $ROOT/template/saved_caches/*`. **Every measured lifetime starts from a
  fresh `cp -a` of the template** (no hard links), as in U4.
- Client `B17Load` (Java driver 3.12.1, protocol **v4**, CL ONE, 4 connections, `SocketOptions.readTimeoutMillis`
  120,000, retry policy: none — `FallthroughRetryPolicy`), three prepared query variants, k pk values bound per query:
  - **T (test):** `SELECT * FROM b17.t WHERE pk IN (?,…,?) ORDER BY ck LIMIT 10`, **unpaged**
    (`setFetchSize(Integer.MAX_VALUE)`).
  - **M (matched control, protected path):** `SELECT * FROM b17.t WHERE pk IN (?,…,?) LIMIT 10`, driver default
    paging (fetch 5,000) — the same IN and LIMIT without ORDER BY, so the LIMIT reaches the read.
  - **I (intervention):** `SELECT * FROM b17.t WHERE pk IN (?,…,?) ORDER BY ck PER PARTITION LIMIT 10 LIMIT 10`,
    unpaged — the same answer as T (the global top 10 by ck is among each partition's first 10 rows), with the
    missing bound restored per partition (CASSANDRA-11556 behaviour).
  - Partition choice: query i uses a distinct k-subset of 0–15 drawn from `Random(42 + thread)`; c closed-loop
    threads, each sends its next query as soon as the last returns (c = 1: one query at a time, with a 10 s pause
    between queries in sweeps that say "×3").
  - Output: per query a JSON line (start, end, ms, k, pks, rows, first 10 (pk, ck) pairs, value bytes, error class
    and message); per second a CSV (`t, step_c, inflight, ok, err_readfail, err_readtimeout, err_invalid, err_other,
    ok_s, p50ms, p99ms, maxms, rowsLast, lastErr`) and a `SUMMARY` line.
- **Lifetimes** (each a fresh node from the template unless "same lifetime"; c:secs step lists as in U4):

| Label | Arm | Heap / direct | Query | Schedule | Reps |
|---|---|---|---|---|---|
| `VERIFY+IC+PROBE` (not readings) | A | 8G / 4096M | — / T / M / I | VERIFY: per pk `SELECT ck FROM b17.t WHERE pk=?` (paged) → 1,024 rows; one full paged read of pk 0 (fetch 64) → 268,435,456 value bytes. IC: (a) T k = 2 **with fetch 5,000** must fail with `InvalidRequest` "Cannot page queries with both ORDER BY and a IN restriction"; (b) T k = 2 unpaged → 10 rows (pk ∈ {p1,p2}, ck 0,0,1,1,2,2,3,3,4,4); (c) I k = 2 → the same multiset of (pk, ck); (d) M k = 2 → 10 rows. PROBE: T unpaged, c = 1, k = 1, 2, 3, 4, 6, 8, 12, 16, each ×3 (10 s apart): outcome, latency, error | 1 |
| `CAL-2G` | A | **2G / 1024M** | T | c = 1, k = 2, 3, 4, 5, 6, 8 (only k ≤ k5 + 1), each ×3, 10 s apart, stop at the first OOM → **k_T**; if no OOM: same lifetime, `CAL-2G-c` at k_c with c steps `2:45,3:45,4:45,6:45,8:45` → **c_T** | 1 |
| `T-2G-1..3` | A | 2G / 1024M | T | warm-up: M k_T ×5, T k = 1 ×1, 20 s idle; then the failing condition (k_T, c_T): c = 1 → T k_T ×3, 10 s apart; c > 1 → `c_T:120` | 3 (+2 if 2/3) |
| `M-2G-1..3` | A | 2G / 1024M | M | same warm-up; then the M query at k_T with the same schedule (c = 1: 3 queries; c > 1: `c_T:120`) **plus** a 120 s closed loop at `c_T` (or 4) for load | 3 |
| `I-2G-1..3` | A | 2G / 1024M | I | same warm-up and the same schedule as T at (k_T, c_T) | 3 |
| `CAL-4G` | A | 4G / 2048M | T | if k_pred(4G) = 7 ≤ k5: c = 1, k = 6, 7, 8, … ≤ k5 + 1 ×3 first; else c steps at k_c `2:45,3:45,4:45,6:45,8:45,12:45` | 1 |
| `CAL-8G` | A | 8G / 4096M | T | c steps at k_c `4:45,6:45,8:45,12:45,16:45,24:45` | 1 |
| `CAL-31G` | A | 31744M / 15872M | T | c steps at k_c `12:45,16:45,24:45,32:45,48:45,64:45` | 1 (if time) |
| `REP-<H>-1..2` | A | the largest failing heap | T | warm-up, then its failing (k, c) for 120 s | 2 (if time) |
| `I2-2G-1..3` optional | **I2** | 2G / 1024M | T | as T-2G | ≤ 3 (if time) |

  **k5** = the largest k in PROBE with 3/3 success and every latency ≤ 4.0 s. **k_c** = the largest k in PROBE with
  3/3 success and every latency ≤ 3.0 s (margin for contention), at least 1. Arm **A** = shipped defaults. Arm **I2**
  = A + `read_thresholds_enabled: true` + `local_read_size_fail_threshold: 64MiB` (the byte control that ships off;
  U4's intervention). If PROBE shows k5 ≥ 4, the primary claim is a **single query** (c_T = 1); if k5 < 3, CAL-2G goes
  straight to the c steps (record which). Each sweep stops at its first OOM; the budget-search sweeps start at their
  predicted band and are extended by one step if no OOM.

**Harness** (build under `harness/` in this folder by adapting the verified U4 harness,
[`../cql-row-limit--wide-row-default-pages/harness/`](../cql-row-limit--wide-row-default-pages/harness/)):
1. `setup.sh`: `mkdir -p /mydata/s4/b17-w1`; `cp -a /mydata/s4/cassandra-base $ROOT/tree`; `cp -a $ROOT/tree/conf
   $ROOT/conf-pristine`; compile `B17Load.java` and `C2Sampler.java` into `$ROOT/cls`.
2. `victim-ctl.sh` (from U4's): `ROOT=/mydata/s4/b17-w1`; arms `A`, `I2`, `LOAD`; explicit `MAX_HEAP_SIZE` and
   `MAX_DIRECT_MEMORY_SIZE` for every lifetime (no "auto"); scope unit `b17-<label>-<epoch>`, `MemoryMax` =
   heap + direct + 8G (compute from the given direct, not U4's fixed 15872M); same `JVM_EXTRA_OPTS` (NMT summary, GC
   and safepoint log), `CASSANDRA_HEAPDUMP_DIR=<run dir>`; `run.meta` with label, arm, heap, direct, jar sha256 and
   the resolved flags from `ps`.
3. `B17Load.java` (from `U4Load.java`): `schema`; `load <host> <parts> <rows> <bytes> <conc>` with retries;
   `verify <host>`; `one <host> <T|M|I> <k> [fetch]`; `sweepk <host> <T> <k-list> <reps> <pauseMs>`;
   `run <host> <T|M|I> <k> <steps c:secs>`; outputs as above. Unpaged = `setFetchSize(Integer.MAX_VALUE)`.
4. `C2Sampler.java` unchanged: JMX 1 s — heap used, G1 old-gen post-GC usage, NTR and ReadStage active/pending,
   `java.nio` direct.
5. `run-arm.sh <label> <A|I2> <heap> <direct> <script>`: refuse if a `CassandraDaemon` runs; clone; start; ready
   (`Starting listening for CQL clients`, 120 s, one retry); `$V gc` + baseline reading; sampler; every 5 s `jcmd
   VM.native_memory summary` and `RssAnon`; the client script; on client exit or JVM death record the outcome
   (`OutOfMemoryError` lines in `stdout.log`/`system.log`, hprof present, scope `memory.events`, count of
   `Query cancelled (timeout)` in `debug.log`, `nodetool tpstats` dropped READ_REQ for survivors); stop a survivor
   (`nodetool drain`, SIGTERM by PID); copy small files to `logs/<label>/`; full logs and hprofs stay in
   `pc72:/mydata/s4/b17-w1/runs/<label>/`. Launch each lifetime as a background job; poll with bounded waits.
6. `gcwin.py`, `hprofstacks.py`, `steps.py` from U4; `hprofhist.py` with the B17 buckets: `byte[]` ≥ 128 MiB
   (replica buffers; sizes listed), `byte[]` of 262,144 ± 64 B (value copies; count ÷ 1,024 = partitions held in
   the `ResultSet` or being deserialized), `LocalDataResponse`, `DataOutputBuffer`, `ResultSet`/`ResultSetBuilder`
   counts. Parse hprofs only for heaps ≤ 8 GiB (time); for 31,744 MiB keep the dump and use the first error stack and
   the old-gen readings.

**Instruments (U independent of K).** K = rows returned per query (client; 10 for T/M/I) and, for the read, the
absence of any row limit (`cqlRowLimit` NO_LIMIT is a code fact, confirmed by U). U = (a) at an OOM, the hprof written
by `HeapDumpOnOutOfMemoryError`: count and sizes of `byte[]` ≥ 128 MiB, count of 256 KiB `byte[]`, thread stacks in
`LocalDataResponse.build` / `DataOutputBuffer.expandToFit` (reading phase) or in deserialization /
`ResultSetBuilder` / `SelectStatement.processPartition` (`ResultSet` phase); (b) G1 old-gen post-GC usage and heap used
(1 s JMX); (c) GC log → STW fraction per 60 s window; (d) per-query latency, outcome and error class (the 5 s
cancellation shows as a read failure with `Query cancelled (timeout)` in `debug.log`); (e) NTR / ReadStage active
(concurrency reached), queries/s; (f) NMT and `RssAnon` every 5 s; JVM direct for the ledger. In surviving T and I
lifetimes at c > 1, one `jcmd GC.class_histogram` at load second 100 (intrusive, once). For the response size, log the
client's value bytes per query (10 × 262,144 = 2,621,440 B for T and I).

**Predicted response.**
- VERIFY: 16 × 1,024 rows; pk 0 value bytes 268,435,456. IC (a) `InvalidRequest` with the paging message; (b)–(d) 10
  rows each, (b) and (c) the same (pk, ck) multiset. PROBE: k = 1 at ≈ 0.5–1.5 s; latency ≈ linear in k
  (r ≈ 200–600 MB/s, uncertain: U4's 245 MB first pages took ≈ 7 s end-to-end including the client transfer,
  which this query does not have); a k with D/r > 5 s fails with a read failure/timeout and `Query cancelled`.
- `CAL-2G`: k = 2 survives; **Java heap OOM at k = 4 (band 3–5)**, in the `ResultSet` phase at k = 4 (first stack in
  value deserialization / `ResultSetBuilder`) or in `DataOutputBuffer.expandToFit` at k = 5; old post-GC near the heap
  before death. If k5 < 3: OOM at c = 2–3 with k_c.
- `T-2G`: Java heap OOM 3/3 at (k_T, c_T); the dump holds ≥ k_T − 1 buffers of 216–324 MiB and/or ≥ 1,024 value
  copies of 256 KiB per partition already deserialized; the response would have been 10 rows.
- `M-2G`: 0/3 OOM; each query returns 10 rows in ≪ 100 ms, old post-GC < 0.5 GiB.
- `I-2G`: 0/3 OOM; each query returns the same 10 (pk, ck) rows as T would, in ≪ 1 s, with ≤ k × 10 rows read.
- `I2-2G` (optional): 0/3 OOM; every T query fails with READ_SIZE ("loaded over … bytes … local_read_size_fail_threshold")
  → 0 useful queries.
- Budget search: OOM at each heap near its predicted c band at k_c; largest failing heap predicted **31,744 MiB**
  (c ≈ 14–32 at k_c = 4, higher at k_c = 2); no direct OOM, no scope `oom_kill`.

**Stopping budget and time plan** (hard deadline: §3–§4 written and every process stopped by **18:07 EST,
2026-11-18**). Stage-2 start S expected ≈ 14:30 EST. Planned: setup + harness S → S+25 min; `LOAD` + template
→ S+45; `VERIFY+IC+PROBE` → S+60; `CAL-2G` (≤ 8 min) → S+70; `T-2G` ×3 (≈ 4 min each) → S+85; `M-2G` ×3 → S+97;
`I-2G` ×3 → S+109; `CAL-4G`, `CAL-8G` (≈ 8 min each) → S+125; `CAL-31G` (≈ 12 min with a 31 GB dump) → S+140;
`REP` ×2, extra T repetitions, `I2` → S+165; write-up 30 min. **Hard limits:** no new lifetime starts after
**17:15 EST**; all processes stopped by **17:30 EST**; if S is later than 15:15 EST skip `CAL-31G`, `REP` and `I2`;
if later than 16:00 EST also skip `CAL-8G`. Per lifetime: node ready ≤ 120 s (else invalid, one retry); single
queries ≤ 60 s each (client timeout 120 s); sweeps ≤ 6 × 45 s; T/M/I schedules ≤ 4 min. No escalation after an OOM
beyond the planned list (no raised timeouts, no tightened budgets).

**Controls and intervention.**
- **Matched control `M-2G` ×3 (protected path):** same build, budget, data, k_T, c_T and client; only `ORDER BY` is
  removed (so the LIMIT reaches the read and paging is allowed at the driver default). Shows the holder comes from the
  exempt path, not from the IN list, the data or the request count. Multiplicity boundary: the largest surviving k
  (or c) in `CAL-2G` (one run).
- **Intervention `I-2G` ×3:** the T query with `PER PARTITION LIMIT 10` — the bound the post-query-ordering path
  omits, restored per partition; same answer, same budget. Removing the OOM attributes it to the unbounded
  per-partition materialization. Record the rows returned (useful work kept).
- **Optional `I2-2G`:** the server byte control that ships off (record throughput: it protects by rejecting).

**Verdict rules (stated before readings).**
- **true positive:** `T-2G` Java heap OOM in ≥ 3 runs (n/N stated; if 2/3, add up to 2 more), `M-2G` 0/3, `I-2G`
  0/3, dumps show the claimed holders (replica buffers ≥ 128 MiB and/or 256 KiB value copies of the listed
  partitions), a query that would return 10 rows → `verified-OOM · deployment`, **bypass (exempt path)**, with c_T
  stated (c_T = 1: "one query"; c_T > 1: "c_T concurrent queries", the U4 overlap noted) and the largest failing
  budget from the search.
- **retry:** OOM only as a direct-buffer OOM or in Netty; service loss (≥ 90 % STW over ≥ 60 s) without OOM
  (`verified-gap`); OOM < 3 runs after 5; time ran out before V1/V2/V4; or every T query at every tested (k, c) is
  cancelled by the 5 s read timeout before the heap fills, while c ≤ 8 at 2 GiB was not exceeded.
- **false positive:** `CAL-2G` reaches c = 32 at k_c (NTR active ≥ c, load reached) with no OOM and old post-GC
  below 90 % of the heap, and the readings show why (e.g. the 5 s cancellation bounds each query's bytes to
  r × 5 s and concurrent queries do not overlap enough), with no named factor left untried.
- **invalid lifetime:** IC (a) not rejected (the client paged), T/I rows ≠ 10, client JVM OOM, scope `oom_kill`,
  workload not started; fix and rerun, recorded as a deviation.
- Cleanup: stop every process started; keep `/mydata/s4/b17-w1/runs/` (raw logs, hprofs) and the template; report
  what is left. Delete nothing in `/mydata/s4/cassandra-base`.

`sha256 of §1–§2 at freeze: e1212af475af178170ed5e6fcce0fd61ff7e7b01a1ab1b1f53e85e8e46b86985` · computed over the lines from `## 1. Candidate` through the line before this one (`sed -n '/^## 1\. Candidate/,/^`sha256 of §1–§2 at freeze/p' <file> | sed '$d' | sha256sum`) · amendments after the freeze: dated, with reason, below this line.

**Amendments (stage 2, dated, each before the readings it affects).**
- **A1 (2026-11-18 13:52 EST) — work directory `/mydata/s4/b17-w4`, not `b17-w1`.** Reason: the wave-4 session and the
  root `HANDOFF.md` name the per-case directory `/mydata/s4/<id>-w4`. Environment only.
- **A2 (13:52) — victim scope without `MemoryMax`.** Reason: node practice for this wave puts `MemoryMax` on a scope only
  where the approved budget is a container; §2 states "no container budget" and used `MemoryMax` for isolation only.
  The scope keeps `MemorySwapMax=0`. The rule "a scope `oom_kill` makes the lifetime invalid" is then moot;
  `memory.events` was still recorded (all zero in every lifetime). The client JVM ran in its own scope (swap off, 4 GiB heap).
- **A3 (13:58) — `LOAD` commit log on tmpfs; one extra `FILL` lifetime.** Reason: pc72's `/mydata` is a spinning RAID
  (PERC H710P, `ROTA=1`); the first `LOAD` stalled (commit-log sync 51,877 ms, inserts failing after 5 retries) and was
  stopped by PID and kept as `runs/LOAD.aborted1`. The second `LOAD` (commit log in `/dev/shm`, LOAD only, not a reading)
  reported 108 of 16,384 inserts failed after 5 retries (709 retries). A `FILL` lifetime (14:09–14:13, clone of the
  template, 8G / 4096M, commit log on tmpfs) found **all 16,384 rows present** (`filled=0`: the timed-out writes had been
  applied), re-ran flush + major compaction (1 sstable, 4,317,186,404 B, partition 268,650,950 B, compression ratio 1.005)
  and the template was rebuilt from it. Every measured lifetime keeps its commit log on `/mydata` as designed (they are
  read-only).
- **A4 (15:03) — client fix, instrument only.** After `CAL-8G`, the closed-loop threads stop as soon as the victim is gone
  (`CAL-8G` logged 28,177 `NoHostAvailableException` lines in the second after the OOM). Applies from `CAL-31G` on; no
  effect on the victim. `hprofstacks.py` gained an optional frame-count argument (15:05) to print whole OOM stacks.
- **Schedule details not fixed by §2 (chosen before the readings that use them):** warm-up M queries 1 s apart; the M
  closed loop at c = 4 (c_T = 1, so "c_T (or 4)" → 4); the "extended by one step" budget-search steps were written into
  the specs up front (`CAL-4G` k = 10 after k5 + 1 = 9; `CAL-8G` c = 32; `CAL-31G` c = 96); only `CAL-31G` reached its
  extension. The batch's time guard as written would have allowed a start after 17:15 EST if it ended by 17:30; not
  triggered (the batch ended 15:28 EST). Optional `I2-2G` ran (time allowed).

## 3. Runs (stage 2)

**Environment.** `pc72` (node2.jason92-326665, x86_64, 40 cores, 125 GiB RAM, 8 GiB swap kept off the victim; `/mydata`
on a rotational RAID, 714 GiB free), Ubuntu 22.04, kernel `5.15.0-203-generic`, cgroup v2, OpenJDK 11.0.33, G1
(`G1HeapRegionSize=16m`, `MaxGCPauseMillis=300`, `AlwaysPreTouch`), `HeapDumpOnOutOfMemoryError`,
`OnOutOfMemoryError=kill -9 %p`. Build: `/mydata/s4/b17-w4/tree` (copy of `cassandra-base`), jar
`apache-cassandra-5.0.9-SNAPSHOT.jar` sha256 `570b5249…a90176e`. Nothing else ran on pc72 (`pgrep` before the first
lifetime; every lifetime refused to start if a `CassandraDaemon` ran). `yaml.diff` per lifetime: only the five directory
lines (arm I2: plus the three threshold lines). Resolved flags recorded from `ps` in every `run.meta`
(e.g. `T-2G-1`: `-Xms2G -Xmx2G -XX:MaxDirectMemorySize=1024M`). Harness: [`harness/`](harness/) (from U4's: `B17Load.java`,
`victim-ctl.sh`, `run-arm.sh`, `batch.sh`, `load-data.sh`, `fill-data.sh`, `qsum.py`, `hprofhist.py` with B17 buckets,
`gcwin.py`, `hprofstacks.py`, `C2Sampler.java`). Small excerpts: [`logs/<label>/`](logs/) (`qsum.txt` = per-item summary,
`client.out` per-query JSON lines (closed-loop items trimmed), `samples.csv` 1 s JMX, `readings.csv` 5 s NMT/RssAnon,
`gcwin.txt`, `hprofhist.txt`, `hprofstacks-oom.txt`, `oom-excerpt.txt`, `outcome`). Full logs and hprofs:
`pc72:/mydata/s4/b17-w4/runs/<label>/`.

**Baseline (2 GiB heap, after `GC.run`):** heap used 87–92 MiB, G1 old 71–75 MiB, NMT total ≈ 2.6 GB, `java.nio` direct 48 MiB.

**`VERIFY+IC+PROBE`** (8G / 4096M; instrument checks, not readings; 14:19–14:26 EST):
- VERIFY: 16 partitions × 1,024 rows; pk 0 = 268,435,456 value bytes; three values compared with
  `Random(pk·100003+ck)`: 3/3 match.
- IC (pks 3, 7): (a) T with fetch 5,000 → `InvalidQueryException: Cannot page queries with both ORDER BY and a IN
  restriction on the partition key; …` ✔; (b) T unpaged → 10 rows `3/0 7/0 3/1 7/1 3/2 7/2 3/3 7/3 3/4 7/4`, 1,034 ms ✔;
  (c) I → the same 10 (pk, ck), 35 ms ✔; (d) M → 10 rows `3/0 … 3/9`, 29 ms ✔.
- PROBE (T unpaged, c = 1, ×3, 10 s apart), latencies in ms: k = 1: 29, 31, 45 (a one-key `IN` is not post-query ordering:
  the LIMIT reaches the read); k = 2: 968, 1,043, 940; k = 3: 1,116–1,738; k = 4: 1,224–1,976; k = 6: 2,760–2,808;
  k = 8: 3,151–3,769; k = 12: 4,378, 5,007, 5,655 (all 10 rows); **k = 16: 0/3** (1 `ReadTimeoutException`, 2
  `ReadFailureException` at 5,012–5,085 ms; 6 `Query cancelled (timeout)` in `debug.log`). Serialization rate ≈ 2.2–2.6
  partitions/s per query ≈ 600 MB/s. **k5 = 8, k_c = 6** (k5 ≥ 4 → the primary claim is a single query, c_T = 1).
- Observation: the per-partition local reads run on ReadStage threads in parallel (ReadStage active up to 4), not
  inline one after another as §1 assumed; several buffers therefore grow at the same time.
- The cancelled local commands print as `SELECT * FROM b17.t WHERE pk = 15 ALLOW FILTERING` for T (no row limit) and as
  `… WHERE pk = 5 LIMIT 10 ALLOW FILTERING` for M (`CAL-31G`, `M-2G-2` `cancel-excerpt.txt`): K (`cqlRowLimit`) is
  `NO_LIMIT` on the T path, as the code reading said.

**`CAL-2G`** (2G / 1024M, T, c = 1, k = 2, 3, 4, 5, 6, 8 ×3; 14:26–14:29): k = 2: 3/3 ok (1,095, 7,794, 1,199 ms);
k = 3: 3/3 ok (6,666, 1,947, 1,998 ms; G1 old post-GC max **1,633 MiB**); **k = 4: Java heap OOM on the first query**
(pks 15, 10, 1, 8: the seventh draw of `Random(42)`, as in `T-2G` and `I-2G`, whose six earlier draws are the warm-up) at +91 s.
**k_T = 4, c_T = 1.** Dump (1,364 MB): `byte[]` ≥ 128 MiB: 5 arrays, 216, 216, 216, 216, 324 MiB = 1,188 MiB (four
partition buffers, one of them caught mid-growth 216 → 324); 4 `LocalDataResponse`, 4 `DataOutputBuffer`, 4
`ReadCallback`. OOM thread (whole stack in `logs/CAL-2G/hprofstacks-oom.txt`): `SEPWorker.run` →
`StorageProxy$LocalReadRunnable.runMayThrow:2211` → `ReadCommand.createResponse` → `LocalDataResponse.build:201` →
`UnfilteredRowIteratorSerializer.serialize` → `Cell$Serializer.serialize` → `DataOutputBuffer.expandToFit:178` →
`ByteBuffer.allocate`. Direct ≤ 48 MiB; GC max 60 s STW 2 %.

**`T-2G-1..3`** (2G / 1024M, arm A; warm-up M k = 4 ×5, T k = 1 ×1, 20 s idle; then T k = 4 ×3, 10 s apart):

| Run | Warm-up | First T k = 4 query (pks 15, 10, 1, 8) | Dump: `byte[]` ≥ 128 MiB | 256 KiB value copies | OOM thread (first frames) | old post-GC max | direct max |
|---|---|---|---|---|---|---|---|
| T-2G-1 | 5 M ok (33–1,341 ms), T k = 1 ok | **Java heap OOM** (connection closed at 5,232 ms), +42 s | 4: 216, 324, 324, 324 = 1,188 MiB | 2 | `LocalDataResponse.build` → `DataOutputBuffer.expandToFit` (ReadStage) | 1,198 MiB | 48.9 MiB |
| T-2G-2 | 5 M ok, T k = 1 ok | **Java heap OOM** (16,930 ms), +47 s | 4: 324 ×4 = 1,296 MiB | 2,349 (587 MiB = 2.29 partitions) | `SelectStatement.execute:429` → `processResults:570` → `process:1010` → `processPartition:1123` → `Cell$Serializer.deserialize:339` | 1,648 MiB | 48.0 MiB |
| T-2G-3 | 5 M ok, T k = 1 ok | **Java heap OOM** (4,115 ms), +34 s | 4: 216, 324, 324, 324 = 1,188 MiB | 1 | as T-2G-1 | 1,198 MiB | 48.9 MiB |

**3/3 Java heap OOM** on the first T query, which would have returned 10 rows (2,621,440 value bytes; `I-2G` returned
them). Both phases of §2 occur: two in the reading phase (four partition buffers growing in parallel), one in the
`ResultSet` phase (all four buffers complete plus 2.29 partitions already copied). GC: max 60 s STW 1–6 %, no service
loss; scope `memory.events` all 0; no direct-memory growth.

**`M-2G-1..3`** (matched control: same budget, data, warm-up and k = 4; `ORDER BY` removed, driver paging 5,000):
M k = 4 ×3 → 10 rows each (32–353 ms); then 120 s closed loop at c = 4: **21,006 / 21,661 / 21,763 queries ok**
(175–181 q/s, p50 18 ms), errors 0 / 4 (2 `ReadTimeout`, 2 `ReadFailure`, latency max 6.4 s, 12 cancellations in
`debug.log`) / 0. G1 old post-GC max 71–78 MiB, heap used max 1,276–1,292 MiB, direct ≤ 49 MiB. **0/3 OOM.**

**`I-2G-1..3`** (intervention: T + `PER PARTITION LIMIT 10`; same warm-up and schedule): each I k = 4 query returned 10
rows in 27–618 ms; the first one (pks 15, 10, 1, 8 — the T-2G query) returned `1/0 8/0 10/0 15/0 1/1 8/1 10/1 15/1 1/2
8/2`, the ORDER BY answer. G1 old post-GC max 71–77 MiB, heap used max 487–552 MiB. **0/3 OOM, 9/9 queries answered.**

**`I2-2G-1..3`** (optional: arm A + `read_thresholds_enabled: true`, `local_read_size_fail_threshold: 64MiB`; T schedule):
every T k = 4 query failed with `ReadFailureException` (187–2,993 ms; `system.log`: "1 nodes loaded over 67164232 bytes
and aborted the query … (see local_read_size_fail_threshold)"), 9/9 rejected, 0 useful T queries; old post-GC ≤ 72 MiB.
**0/3 OOM** — the byte control that ships off protects by rejecting.

**Budget search (arm A, T):**
- **`CAL-4G`** (4G / 2048M; c = 1, k = 6, 7, … ×3): k = 6: 3/3 ok (2,412, 4,700, 4,259 ms; old post-GC 2,189 MiB);
  **k = 7: Java heap OOM on the first query** (18,146 ms, +68 s) — exactly k_pred(4G) = 7. Dump (4.19 GB): 7 × 324 MiB
  (2,268 MiB) + 6,460 value copies (1,615 MiB = 6.31 partitions); OOM thread in `processPartition` →
  `Cell$Serializer.deserialize` (`ResultSet` phase).
- **`CAL-8G`** (8G / 4096M; c steps at k_c = 6): **Java heap OOM at the first step, c = 4**, +29 s, before any query
  completed. Dump (7.51 GB): 18 buffers ≥ 128 MiB (5,401 MiB: 4 × 216, 14 × 324) + 6,495 value copies (1,624 MiB);
  OOM thread `LocalDataResponse.build` → `expandToFit`. Old post-GC 5,490 MiB, NTR active 4, ReadStage active 14.
- **`REP-8G-1, -2`** (8G / 4096M; warm-up, then T k = 6 at c = 4 for 120 s): **2/2 Java heap OOM** after 15 s and 12 s
  of load (19 and 22 buffers ≥ 128 MiB: 5,617 and 6,157 MiB; OOM thread `expandToFit`). With `CAL-8G`: **3/3 at 8 GiB**.
- **`CAL-31G`** (31,744M / 15,872M, pc72's own `cassandra-env.sh` resolution; c = 12 → 96 at k_c = 6, 45 s each):
  **no OOM.** 59 of 2,685 queries answered; 2,475 `ReadTimeoutException` + 151 `ReadFailureException`; 5,198
  `Query cancelled (timeout)`. ReadStage active max 32 (`concurrent_reads`), NTR active up to 96; G1 old post-GC max
  **27,032 MiB (85 % of the heap) at c = 32**, 26,786 MiB at c = 64; GC max 60 s STW 16 %, no service loss.
  Concurrent queries share the 32 READ threads, so each one's partitions are serialized more slowly and most are cut
  by the 5 s read timeout before the heap fills.
- **Largest failing budget: 8,192 MiB heap / 4,096 MiB direct (a 16 GiB node), 3/3.** 31,744 / 15,872 MiB survived the
  planned range (c ≤ 96 at k = 6); budgets between them were not in the design and were not run.

**Deviations from the predictions.** (1) Local reads ran in parallel on ReadStage, not inline in sequence; the
reading-phase OOM (several buffers growing at once) was therefore as frequent as the `ResultSet`-phase one; the claimed
holders are the same. (2) k_T = 4 and the 4 GiB boundary k = 7 match §2; at 8 GiB the OOM came at c = 4 with k = 6
(§2: k_c = 4 needs c ≥ 4; with k_c = 6 c = 4 is past it). (3) The largest failing budget is 8 GiB, not 31,744 MiB:
the read timeout plus the 32 READ threads cap concurrent serialization at the largest heap. (4) No direct OOM, no
scope event, no client OOM, no invalid lifetime.

**Cleanup.** Every process started was stopped (victims by drain + SIGTERM by PID or ended by the OOM kill; samplers;
clients; hprof parsers finished). `pgrep` at 15:29 EST: no `CassandraDaemon`, `B17Load`, `C2Sampler`, `run-arm`,
`batch` or parser on pc72. Left on pc72: `/mydata/s4/b17-w4/` ≈ 38 GB (tree 0.5 GB, template 4.1 GB, last `node`
clone 4.1 GB, `runs/` with full logs and 8 hprofs = 30.9 GB: CAL-2G 1.4, T-2G-1..3 1.4/2.1/1.4, CAL-4G 4.2, CAL-8G
7.5, REP-8G-1/-2 6.3/6.6 GB); `/dev/shm/b17-w4-commitlog` removed. `/mydata/s4/cassandra-base` untouched.

## 4. Conclusion (stage 2)

**Verdict: true positive.** Protocol status: **`verified-OOM · deployment`** — direction **bypass (exempt path)** of the
CQL row limit and of paging (U > C, K ≤ C: the read runs with `NO_LIMIT`, 10 rows are returned), on an **unprotected
configuration** (read-size thresholds ship off); interpretation: suspected implementation/design gap (the user LIMIT
could be pushed into each partition's read for clustering-order ORDER BY, as `PER PARTITION LIMIT` shows; JIRA: the
paging refusal is by design (CASSANDRA-6722), the memory consequence is not filed). Endpoint: Java heap
`OutOfMemoryError`, with one query (c_T = 1) at the primary budget.

**Reason.** At the budget `cassandra-env.sh` resolves for a 4 GiB node (heap 2,048 MiB, direct 1,024 MiB), every capacity
at its shipped default, one unpaged `SELECT * FROM b17.t WHERE pk IN (15, 10, 1, 8) ORDER BY ck LIMIT 10` — answer 10
rows, 2.5 MiB — ended in a Java heap OOM **3/3** (`T-2G`; also `CAL-2G`), with old-gen post-GC up to 1,648 MiB and the
dumps holding four whole-partition replica buffers of 216–324 MiB (1,188–1,296 MiB) and, in one run, 2.29 partitions
(587 MiB) already copied into the `ResultSet`; the OOM thread is `LocalDataResponse.build` →
`DataOutputBuffer.expandToFit` (2/3) or `SelectStatement.processPartition` → `Cell$Serializer.deserialize` (1/3).
The matched control without `ORDER BY` (LIMIT reaches the read) survived **0/3 OOM** including 175–181 queries/s for
120 s at c = 4 with old post-GC ≤ 78 MiB; the intervention restoring the per-partition bound (`PER PARTITION LIMIT 10`,
same 10-row answer) survived **0/3** with old post-GC ≤ 77 MiB; the byte threshold that ships off (`I2`) also stopped
it 0/3, by rejecting every query. The boundary at 2 GiB is k = 3 (3/3 survived, old post-GC 1,633 MiB) vs k = 4. The
budget search found OOM at 4 GiB (k = 7, single query) and **8 GiB heap / 4 GiB direct, 3/3** (4 concurrent queries
over 6 partitions); at 31,744 / 15,872 MiB there was no OOM up to 96 concurrent queries (old post-GC peaked at
27,032 MiB) because the 5 s read timeout cancelled 97.8 % of the queries first — the only bound is time × the
≈ 600 MB/s serialization rate, not bytes.

**V1–V7.**

| | Requirement | Evidence |
|---|---|---|
| V1 | ≥ 3 runs reach the endpoint | `T-2G-1..3`: 3/3 Java heap OOM (plus `CAL-2G`); 8 GiB: `CAL-8G`, `REP-8G-1..2` 3/3 |
| V2 | matched control ≥ 3 | `M-2G-1..3`: 0/3 (single queries and 120 s at c = 4); boundary k = 3 in `CAL-2G` 3/3 survived |
| V3 | U independent of K | hprof `byte[]` ≥ 128 MiB and 262,144 B value copies (U ≈ 1.19–1.88 GiB at 2 GiB; up to 7.0 GiB at 8 GiB) vs K = 10 rows returned / `NO_LIMIT` in the logged local commands |
| V4 | intervention ≥ 3 | `I-2G-1..3` (`PER PARTITION LIMIT 10`): 0/3, same answers, 9/9 queries served; also `I2-2G-1..3` 0/3 (rejects all) |
| V5 | initiating failure | first `OutOfMemoryError: Java heap space` with dump per run; OOM thread stacks in `logs/*/hprofstacks-oom.txt`; histograms show the holders |
| V6 | default constraints | read thresholds off, guardrails −1, `page_size` −1, `read_request_timeout` 5 s, `native_transport_timeout` 12 s, `concurrent_reads` 32, NTR 128, caches/memtables default; `yaml.diff` = directories only (arm A) |
| V7 | acceptable budget | 2,048 MiB heap / 1,024 MiB direct (≥ 512 MiB standing rule; = `cassandra-env.sh` for a 4 GiB node); largest failing 8,192 / 4,096 MiB (16 GiB node) 3/3 |

**Overlap with U4 (verified).** Same two holders (replica `DataOutputBuffer` per partition read, coordinator `ResultSet`
value copies), same build and data shape (wide partitions of large cells). New here: the path — `IN` + `ORDER BY` makes
the read drop the user's LIMIT and refuses paging, so neither the LIMIT nor any page size bounds the holders; the held
bytes scale with the number of keys in one query (one query suffices up to 4 GiB heaps), the response is 10 rows, and
Netty direct memory (U4's failure above 2 GiB) plays no part (direct ≤ 49 MiB).

**Limits of the result.** One node (coordinator = replica); RF 1; 256 MiB partitions of 256 KiB cells (the per-row
overhead of small rows, not tested here, would add to U). Budgets between 8 GiB and 31,744 MiB were not tried; at
31,744 MiB the outcome depends on the read timeout winning the race. Clustering-column ordering only (the ANN branch is
out of scope). Not tested: RF > 1 (replica responses over the network), whether drivers that page by default make users
hit the `InvalidRequest` first (the message itself tells them to disable paging). Clue patterns: CP-10 (an unpaged branch
skips the limit) and CP-12 (result materialized whole) cover the shape; no new pattern needed.

**Write-back for the session (not done here):** OC-320 → `true positive (B17)`; OC-308 (same mechanism, quoted in §1, not
in the assigned cluster) is covered by the same runs; `_INDEX.md` row B17 → true positive, `verified-OOM · deployment`.
