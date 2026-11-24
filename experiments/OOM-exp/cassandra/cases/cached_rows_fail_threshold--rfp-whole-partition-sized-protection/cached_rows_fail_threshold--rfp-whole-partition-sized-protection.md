# R24 — cached_rows_fail_threshold: replica-filtering protection holds the whole partition from every replica, counted in rows, whatever the page  <!-- file: cassandra/cases/cached_rows_fail_threshold--rfp-whole-partition-sized-protection/cached_rows_fail_threshold--rfp-whole-partition-sized-protection.md -->

| Field | Value |
|---|---|
| Case ID | `R24` (R = a new attempt at an earlier case; README "ID prefixes"): retry of `B22` (B = bypass case) |
| From | retry of `B22` (from `OC-479`), [`phase2-retry-list.md`](../../phase2-retry-list.md) row B22; also `OC-39` and `OC-469` of the phase 1 OOM candidate list (same holder and mechanism) |
| Phase-1 case file | [`cached_rows_fail_threshold-queryProtectedPartitions-i--autonomous`](../../../../capacity-enforcement-exp/cassandra/stage3-ai-deep-read/cases/cached_rows_fail_threshold-queryProtectedPartitions-i--autonomous.md) · stage-4 result [`results/…`](../../../../capacity-enforcement-exp/cassandra/stage4-runtime-verification/results/cached_rows_fail_threshold-queryProtectedPartitions-i--autonomous.md) |
| System / pinned source | Cassandra 5.0.9 (`systems/cassandra/source/`); built copy `pc72:/mydata/s4/cassandra-base` (`build/apache-cassandra-5.0.9-SNAPSHOT.jar`, sha256 `570b5249…0176e`, the same jar as B22) |
| Stage 1 (design) | phase-2 OOM agent, stage 1 (Claude Opus 5.5), 2026-11-24 (owner-approved batch of 2026-11-24); nothing run (pc72, pc75, pc82, pc91, pc99 checked read-only) |
| Stage 2 (verify) | pending (a fresh session) |
| Verdict | `pending` |

## Summary

- **Conclusion:** pending (stage 2).
- **Hypothesis (stage 1).** A filtering range read (`… WHERE v = 'x' ALLOW FILTERING`, no partition key) at CL QUORUM on
  RF 2 goes through replica-filtering protection (RFP). RFP reads the **whole partition** from every replica before it returns
  the first page: for range reads it always consumes entire partitions (`ReplicaFilteringProtection.java:143`), and short-read
  protection keeps fetching page-sized chunks from each replica until the partition ends. It keeps every replica's version of
  every row on the coordinator heap. It charges them to `cached_rows_fail_threshold` (32,000) as a **count of rows**. The
  client's fetch size bounds only the page and the internode messages, not what RFP holds.
- **What changed from B22.** B22 sized the hold by the page (5,000 rows of 20 KiB, 98 MiB messages). Its messages hit the
  internode send-queue reserve, half its queries were dropped and timed out, and it reached OOM 0/6 at its frozen budget. R24
  sizes the hold by the **partition** (64 KiB rows, 2,048–12,288 rows per replica, chosen by a pre-declared calibration) and
  uses a small fetch size (128 rows, 8 MiB messages). So the messages stay far below the reserve, while each query still holds
  0.25–1.5 GiB at K = 4,096–24,576 ≤ 32,000. It also maps the binding deadline: every short-read fetch must finish within
  `read_request_timeout` (5 s) of the query's start.
- **Prediction.** About 3–14 concurrent closed-loop queries (set by the calibration) run a 2 GiB coordinator out of heap,
  with RFP's held 64 KiB values dominant and K never above 32,000. The same query at CL ONE (no short-read fetches, one page
  held), the same row count with 2 KiB rows, and a build where RFP consumes only the page for range reads (still serving the
  same pages) should all survive.

## 1. Candidate

**Retry row (quoted from [`phase2-retry-list.md`](../../phase2-retry-list.md), row B22; status set by the coordinator):**

> | [B22](cases/cached_rows_fail_threshold--rfp-counts-versions-not-bytes/cached_rows_fail_threshold--rfp-counts-versions-not-bytes.md) (from OC-479) | 2026-11-21 | pc82, 2 instances RF 2, defaults, 2 GiB: one QUORUM page holds 433 MiB (12,000 RFP versions + 2 × 98 MiB raw responses) while RFP charges 12,000 of 32,000; but at 5–6 concurrent queries the internode send-queue reserve (4 MiB + 128 MiB per endpoint, unmapped in the design) dropped 150–325 responses per sender, half the queries timed out and released memory: OOM 0/6 at the frozen budget, 2/5 at direct 1,024 MiB (not poolable). Controls and threshold-2,000 intervention 0/3 (intervention served no pages) | (1) Size by the partition, not the page: RFP consumes the whole partition (`ReplicaFilteringProtection.java:143`, `:387-396`), so ≈ 15,500 rows per replica (K ≈ 31,000) holds ≈ 0.6 GiB per query at 20 KiB rows or 1.4–1.9 GiB at 48–64 KiB, needing 1–3 queries; (2) keep each internode message ≤ 30–40 MiB with a smaller fetch size, add the send-queue reserve to the protection map and freeze dropped-message and timeout instruments; DIAG that one query finishes inside the 10 s / 12 s timeouts; (3) run every condition with its controls at one budget, U from the GC-log live heap; (4) keep C-small and C-ONE and pick an intervention that still serves pages | picked again: R24 |

**Candidate rows covered (quoted from `phase1-oom-candidates.md`, lines 48, 478, 488; statuses as set by the coordinator):**

> | OC-479 | 2026-11-18 | `cached_rows_fail_threshold-queryProtectedPartitions-i--autonomous` | guided | Holder: the coordinator's ReplicaFilteringProtection PartitionBuilder.contents (ArrayDeque of rows), plus the raw replica responses. [details](runs/wave3.md#oc-479) | CP-2, CP-7, CP-1 | retry (B22) |

> | OC-469 | 2026-11-18 | `cached_rows_fail_threshold-queryProtectedPartitions-i--autonomous` | autonomous | Holder: the coordinator heap in RFP PartitionBuilder.contents/staticRow (ArrayDeque<Unfiltered>), plus the full Message<ReadResponse> payloads of every replica. [details](runs/wave3.md#oc-469) | — | picked: R24 (2026-11-24; same mechanism as OC-479, B22 re-picked as R24) |

> | OC-39 | 2026-11-16 | `cached_rows_fail_threshold-queryProtectedPartitions-i--autonomous` | legacy | [lead list, blind, E3; N17 cluster; queued as U4] Replica-filtering protection caps rows per query, not bytes, with no cap across queries: 128 concurrent queries × 16,000 held rows × 2 KiB, plus raw replica responses outside the count, ≈ 8 GiB, more than an 8 GiB heap leaves after the memtable pool (response size estimated). | CP-2, CP-7 | picked: R24 (2026-11-24; same mechanism as OC-479, B22 re-picked as R24) |

| Row | Holder | Covered here? |
|---|---|---|
| B22 retry (OC-479) | `PartitionBuilder.contents` (held versions) + raw responses, × concurrent queries | **yes**: every arm; R24 makes the held versions (D1) the dominant holder by sizing them by the partition |
| OC-469 | the same holder (it adds `staticRow`, not exercised) | **yes**: same holder and shape |
| OC-39 (legacy) | the same holder, rows × concurrent queries, at 8 GiB | **yes**: same mechanism with 64 KiB rows instead of 2 KiB and a partition-sized hold. The budget search (§2.9) goes to 8 GiB |
| OC-470, OC-480 | second-phase `fetchFromSource` of a whole partition for an unresolved **static** row | **no**: a different holder (static-column predicate, divergent replicas); not touched |

**Phase-1 constraint and stage-4 result** (as in B22 §1, unchanged): `replica_filtering_protection.cached_rows_fail_threshold`
(default 32,000; warn 2,000) is checked in `incrementCachedRows()` (`ReplicaFilteringProtection.java:319-345`). It counts one per
row version per replica (null versions are counted but not stored, `:477-492`), throws `OverloadedException` at T+1 (`:331`) and is
released per partition when the protected partition closes (`:564`). Stage 4 (2026-10-27, 2 nodes RF 2) found that the cap holds
at T = 1,000 / 10,000 / 32,000 (800 B per held row for a 512 B pad) and that the remote raw response (≈ 53 MB) lies outside the
count. It ran one query at a time and never sized rows for bytes.

**What B22 measured that this design builds on** ([B22 §3.2–§3.5](../cached_rows_fail_threshold--rfp-counts-versions-not-bytes/cached_rows_fail_threshold--rfp-counts-versions-not-bytes.md)):
(a) a 20,480 B pad costs **20,768 B per held version** (288 B overhead), measured with `measureDeep`; (b) with a 5,000-row page
and 6,000 rows per replica, RFP held **6,000 per replica** (K = 12,000; histogram bucket 14,237). Short-read protection fetched
the rest of the partition. (c) At CL ONE, RFP still runs with one source but has no short-read protection
(`DataResolver.java:189-198`: `replicas.size() > 1`), so it held exactly one page (5,000). (d) At QUORUM node 1's own initial
range response also goes through internode messaging. (e) Responses of 98 MiB overran the send-queue reserve
(4 MiB + 128 MiB per endpoint), which dropped about half of them. (f) RFP's populate step ran ≈ 0.3 s after the responses
arrived for 245 MB of versions, so the coordinator's merge is not the slow step. Live heap after full GC (GC log) was the only
U that separated the arms; the JMX `old_postgc` column did not.

**New source reading for this design (2026-11-24, pinned 5.0.9):**

- `consumeEntirePartitions = limits.isUnlimited() || !command.isLimitedToOnePartition() || rowFilter.hasStaticExpression()`
  (`ReplicaFilteringProtection.java:143`). A range read is never limited to one partition, so the first phase drains the whole
  merged partition (`:387-396`) before the second phase returns any row.
- The first phase is unlimited (`ResolveContext(replicas, false)` → `onlyCount()`, `DataResolver.java:157-158`, `:270-274`) and
  each replica's response is wrapped in short-read protection (`:274`, `:202-214`). When a replica returned a full chunk,
  `ShortReadRowsProtection.moreContents()` fetches `min(count, perPartitionCount)` = **the page size** more rows from that replica
  (`ShortReadRowsProtection.java:165`, `:171`). It stops only when a fetch returns fewer (`:128`). So the number of fetches is
  ≈ rows per replica / page size, per replica, one after another.
- Each fetch is a `SinglePartitionReadCommand` (timeout `read_request_timeout`, 5,000 ms, `SinglePartitionReadCommand.java:446-449`,
  yaml `:1322`). `ReadCallback.awaitResults()` waits until `requestTime.computeDeadline(5 s)` (`ReadCallback.java:98-101`, `:130`).
  That deadline is min(base + 5 s, enqueue + 12 s), with base = the query's processing start (`cql_start_time: REQUEST`,
  `Config.java:1391`; `Dispatcher.java:173-184`, `:238-245`). **So the whole partition must be fetched within 5 s of the query's
  start**, or the next fetch times out and the query fails and releases its versions. B22's retry item named 10 s / 12 s; the
  binding limit for this shape is 5 s.
- The self replica's fetches run locally (`ShortReadPartitionsProtection.java:184-186`). The remote ones are internode messages
  of page × row bytes. When short-read protection starts, the original response is released (`responses.clearUnsafe(i)`,
  `DataResolver.java:208`), and held `Row`s copy their values (B22's dumps: separate 20,480 B `byte[]`s). So the raw responses
  (B22's D2) become transient chunks, and the held versions (D1) are the standing holder.
- Upstream: CASSANDRA-20639 (fixed 5.0.5, commit `e5c101673a`) added page-sized consumption (`consumeEntirePartitions = false`)
  but **only for single-partition reads**. Range reads still drain entire partitions in 5.0.9, on the `cassandra-5.0` branch and
  on trunk (history clone checked 2026-11-24: the same line at `:144` / `:147`). CASSANDRA-21781 (commit `06468fb06b`, not in
  5.0.9) fixes a correctness bug in 20639's single-partition paging. Neither bounds bytes.

**JIRA prior art (read only; nothing posted).** B22's searches (2026-11-21): no issue reports RFP coordinator memory exhaustion
under the threshold. CASSANDRA-15907 introduced the count thresholds. CASSANDRA-16896's byte-based read thresholds ship off
(`read_thresholds_enabled: false`). New REST queries (`issues.apache.org`, 2026-11-24, ≥ 3 s apart):

| JQL (`project = CASSANDRA AND …`) | Hits | On point |
|---|---|---|
| `text ~ "\"replica filtering protection\"" AND text ~ "\"entire partition\""` | 3 | 15907 (the thresholds), 21332 and 19018 (SAI correctness); none on memory |
| `text ~ "consumeEntirePartitions"` | 2 | **CASSANDRA-20639** (Resolved Fixed 5.0.5): "consuming all the matches in a partition triggers a flurry of short-read protection reads"; a latency/efficiency report, fixed for single-partition reads only, with no word on memory. 21836 (SAI, open) is unrelated |
| `text ~ "\"replica filtering protection\"" AND (text ~ "OutOfMemoryError" OR text ~ "heap" OR text ~ "OOM")` | 10 | 15907, 8272 and config/yaml issues (20843: yaml wording); none reports an OOM |
| `text ~ "\"short read protection\"" AND text ~ "\"range read\"" AND (text ~ "memory" OR text ~ "heap")` | 1 | 16180 (test audit); unrelated |

The yaml documents that RFP "materializes replica results by partition on-heap at the coordinator" and that the thresholds limit
"the number of rows" (`conf/cassandra.yaml:1818-1825`). It also says that breaching the fail threshold means the "page/fetch size is too
large" (`:1832-1833`). That is not true for range reads: the hold here does not depend on the fetch size. **Verdict: `new`** for the
byte gap and for whole-partition holding on range reads. 20639 is **related** (the same drain, reported for its short-read cost,
fixed only on the single-partition path). This is not a known-fixed bug, so it is not a positive control.

## 2. Design solution (stage 1; frozen)

### 2.1 Mechanism and direction

The query `SELECT k, c, v, pad FROM r24.<table> WHERE v = 'x' ALLOW FILTERING` at CL QUORUM, client fetch size **F = 128**, on a
2-instance ring with RF 2. It is a range read with a non-empty row filter, so `DataResolver.resolve()` takes the RFP path
(`DataResolver.java:122-123`, `:132-144`, `:242-270`). Both replicas return the first F = 128 rows of the single partition
`k = 0`. RFP's first phase merges them and, because `consumeEntirePartitions` is true (`ReplicaFilteringProtection.java:143`),
drains the merged partition (`:387-396`). Each time a replica's chunk runs out, short-read protection fetches the next F rows from
that replica (`ShortReadRowsProtection.java:165-171`), until a fetch returns fewer than F (`:128`). Every row version of every
replica is passed to `PartitionBuilder.addRow` (`:477-492`), counted (`incrementCachedRows`, `:319-345`) and, being non-null,
stored as a deserialized `Row` in `contents` (`:491`). Only after the whole partition (N rows per replica) is held does the second
phase return F rows to the client and close the partition, which releases the count (`:564`) and makes the versions garbage. So
for one query the coordinator holds **2N versions ≈ 2N × 65,824 B** (64 KiB pad + 288 B, per B22's measured overhead). The
count it is charged is 2N ≤ 32,000. The fetch size F bounds only the page sent to the client and each internode chunk
(F × 64 KiB = 8 MiB). Nothing sums concurrent queries; `native_transport_max_threads` (128) bounds them implicitly. The time
bound is the 5-s short-read deadline (§1).

**Direction: bypass · accounting omission** (bypass technique note, "Accounting mismatch: fixed charged usage with varying object
shape/copies"; the same shape as B16 and B22). The control charges K = row versions and stays within its contract (K ≤ 32,000),
while the physical memory it materializes is K × row bytes and is independent of the page. The endpoint needs Q concurrent
queries, so it is a bypass excess **stacked by multiplicity** (no aggregate control). It is recorded as bypass with the
multiplicity and the partition size stated.

### 2.2 Protection map (fixed before any reading; victim = coordinator node 1)

| Domain | Allocation and owner (release) | Local contract (K, limit, at limit) | Scope / multiplicity | Aggregate coverage | Claimed? |
|---|---|---|---|---|---|
| **D1 RFP held versions** | `PartitionBuilder.contents` (`RFP.java:458`, `:491`), one builder per replica per partition; deserialized `Row`s with copied 64 KiB values; released when the protected partition closes (`:564`) or the query fails | K = `currentRowsCached` (row versions); T = `cached_rows_fail_threshold` 32,000 (warn 2,000); `OverloadedException` at T+1 (`:319-345`) | per query: 2N versions; × Q concurrent queries | none | **yes** (count, not bytes; whole partition, not page) |
| D2 replica chunks | per fetch: local `LocalDataResponse` heap `DataOutputBuffer` (≤ 1.23 × chunk, B22) and remote `RemoteDataResponse` heap buffer, F × 64 KiB ≈ 8 MiB each; the original responses are released when short-read protection starts (`DataResolver.java:208`); each chunk becomes garbage after its rows are copied | none (uncounted); remote ≤ `internode_max_message_size` 128 MiB | ≤ 2 live chunks per query | none | ledgered (transient, ≤ 20 MiB per query) |
| D3 short-read fetch deadline | every fetch waits until min(start + `read_request_timeout` 5 s, enqueue + `native_transport_timeout` 12 s) (`ReadCallback.java:98-101`; `Dispatcher.java:238-245`) | time, not bytes: a fetch past the deadline throws `ReadTimeoutException`, the query fails and releases D1 | per query | — | mapped: **bounds the hold time**, not the hold size. The workload is sized so that a query finishes inside it (§2.5 DIAG) |
| D4 internode send queue (node 2 → node 1, and node 1 → itself for the initial range response) | `OutboundConnection` queue | `internode_application_send_queue_capacity` 4 MiB per connection + `…_reserve_endpoint_capacity` 128 MiB + `…_reserve_global_capacity` 512 MiB; a message that does not fit is **dropped** (`OutboundConnection.java:456-467`), and its query times out | per endpoint | yes (byte reserve) | mapped (B22's unmapped limiter): 8 MiB chunks, one outstanding per query and replica, Q ≤ 16 → ≤ 128 MiB even if all are queued at once. Drops are a frozen instrument (§2.6) |
| D5 inbound large messages (node 1) | frames buffered on receive (direct, `BufferPool`) until deserialized | `internode_application_receive_queue_reserve_endpoint_capacity` 128 MiB / global 512 MiB: backpressure, not drop | per peer | yes | ledgered (direct, transient) |
| D6 page row limit | `DataLimits` of the page: F = 128 rows (client fetch size) | rows only; `read_thresholds_enabled: false` → `local_read_size_*`, `coordinator_read_size_*` off; `page_size_*`, `partition_size_*`, `column_value_size_*` guardrails off | per query | — | no: it bounds the page and the chunks, **not D1** (the claim) |
| D7 CQL result + encoded response | `ResultSet` aliases ≤ F held values (≈ 8 MiB); Netty **direct** buffer from `Message.encode` until flushed | `MaxDirectMemorySize` | per query | — | ledgered |
| D8 memtables | `memtable_heap_space` = ¼ heap = 512 MiB at 2 GiB | flush at cleanup threshold | per node | yes | baseline only (no writes during readings; data flushed) |
| D9 chunk cache | `file_cache_size` = min(512 MiB, ¼ heap) = 512 MiB at 2 GiB, direct | pool cap | per node | yes | ledgered (direct) |
| D10 baseline | schema, caches, Netty, metrics; key cache min(5 % heap, 100 MiB) | — | per node | — | baseline (measured at warm-up; B22: 109–110 MiB) |

### 2.3 Configuration and budget audit

- **Node: `pc72`** (node2.jason92-326665; x86_64, 40 cores, 125 GiB RAM, Ubuntu 22.04.2, kernel 5.15.0-203, cgroup v2, swap
  8 GiB present, `/mydata` 707 GiB free; OpenJDK 11.0.33, `jcmd`, Python 3.10.12; `/mydata/s4/cassandra-base` jar sha256
  `570b5249d9b9a43f6809eb3da562737492192026f974b2edbd20e94bea90176e` (the same as B22's); `lib/` has
  `cassandra-driver-core-3.12.1-shaded.jar`; `build/lib/jars/byteman-4.0.20.jar`; loopback `127.0.0.1/8`). Read-only check
  2026-11-24 ≈ 03:48 (node clock): no Java process, load 0.03, `/mydata/s4/` holds `cassandra-base`, `3b-B21`, `3b-R22` and a
  `NODE-LOCK/owner` reading `phase1-hadoop o7` (another workflow's lock at the time of the check). **Stage 2 starts only when
  the lock is gone or the coordinator assigns the node.** Equivalent fallbacks: `pc75` or `pc82` (same class, 40 cores, same
  jar). The 32-core `pc91`/`pc99` are acceptable with Q capped at 12. The aarch64 nodes (8 cores) are not suitable: the design
  depends on per-query throughput inside the 5-s deadline. Run folder: `/mydata/s4/r24/` (not created).
- **Topology (environment deviation, recorded; as B22, owner's instruction for this case family):** two Cassandra instances on
  one host, RF 2. Node 1 (**victim/coordinator**) `127.0.0.1`, JMX 7199; node 2 (**peer replica**) `127.0.0.2`, JMX 7299; each
  with its own `CASSANDRA_CONF`, data, commitlog, hints, saved_caches and logs under `/mydata/s4/r24/n1|n2/`; seeds `127.0.0.1`;
  `auto_bootstrap: false`; `cluster_name: r24`. **Start order: node 1, then node 2** (B22 amendment A1: a non-seed cannot start
  with its seed down). The shared host means shared disk, page cache and CPU. This is not a capacity or budget change.
- **Capacity constraints (V6), all at shipped defaults, resolved at the victim's heap:** `cached_rows_fail_threshold` 32,000,
  `cached_rows_warn_threshold` 2,000; `read_thresholds_enabled` false; `internode_max_message_size` 128 MiB;
  `internode_application_send_queue_capacity` 4 MiB, `…_reserve_endpoint_capacity` 128 MiB, `…_reserve_global_capacity` 512 MiB
  (and the receive-side equivalents); `native_transport_max_threads` 128; `concurrent_reads` 32; `memtable_heap_space` 512 MiB;
  `file_cache_size` 512 MiB; `page_size_*`, `partition_size_*`, `column_value_size_*` guardrails off; `column_index_size` default;
  `max_mutation_size` 16 MiB. **Timeouts at defaults** (not raised): `read_request_timeout` 5 s, `range_request_timeout` 10 s,
  `native_transport_timeout` 12 s, `cql_start_time` REQUEST. No constraint is changed in any arm. The intervention changes code
  (a diagnostic build, §2.7), not a setting.
- **Budget (V7), one pair for every readings arm (retry item 3):** victim heap **2 GiB** (`MAX_HEAP_SIZE=2G`; G1 from the shipped
  `jvm11-server.options`: `G1HeapRegionSize=16m`, `MaxGCPauseMillis=300`). Direct memory is what `cassandra-env.sh` resolves on
  this node with a hand-set heap: **`MaxDirectMemorySize=15872M`** (as B22 and U4 recorded on the same node class). The claimed
  node is a large node running a 2 GiB heap (common practice; U4, C2 and B22 used the same pair). Both values are ≥ 512 MiB, so
  V7 is met by the standing rule. No container budget: each JVM runs in `systemd-run --user --scope -p MemorySwapMax=0` (swap 0,
  no `MemoryMax`). **Peer heap 16 GiB** (direct auto), so the peer never ends a run. The peer is not a budget of the claim
  (environment deviation, recorded). Record `-Xmx`/`MaxDirectMemorySize` from `ps` in every lifetime.
- **Other settings:** shipped `jvm-server.options` (`HeapDumpOnOutOfMemoryError`, dump path `/mydata/s4/r24/runs/<lifetime>/`,
  `OnOutOfMemoryError=kill -9 %p` as B22), shipped GC log. Byteman only in the DIAG-B lifetime and the intervention fallback.
  Table options default (LZ4, `read_repair` BLOCKING; the replicas agree, so nothing is repaired). Client: Java driver 3.12.1,
  protocol v4, whitelist `127.0.0.1`, `FallthroughRetryPolicy`, **fetch size 128** (a client setting, labelled: a documented
  deployment choice; the driver default is 5,000). Paging state not followed: every query is a fresh first page, as B22.

### 2.4 Ceiling arithmetic

Row `(k int, c int, v text, pad blob)`, pad **65,536 B** random (incompressible). Held version ≈ 65,536 + 288 = **65,824 B**
(B22's measured overhead). Chunk = F × ≈ 65,560 B ≈ **8.0 MiB** per message. One partition `k = 0` per table, N rows per replica,
every row `v = 'x'`.

| Table (N rows per replica) | Partition per replica | K per query (2N) | **D1 per query** | Short-read fetches per query (2 × N/F) | Q_T (rule §2.5) |
|---|---|---|---|---|---|
| `w2k` (2,048) | 134 MB | 4,096 (warn 2,000 passed, fail 32,000 not) | **257 MiB** | 32 | 14 |
| `w4k` (4,096) | 268 MB | 8,192 | **514 MiB** | 64 | 7 |
| `w8k` (8,192) | 537 MB | 16,384 | **1,028 MiB** | 128 | 4 |
| `w12k` (12,288) | 805 MB | 24,576 | **1,543 MiB** | 192 | 3 |
| `s<N>` (2,048 B pad) | N × 2 KiB | same as `w<N>` | 2N × 2,336 B: 9 / 18 / 37 / 55 MiB | same | — |

Contract capacities: D1's contract is 32,000 versions with **no byte bound**: up to 32,000 × 65,824 B = 2,009 MiB per query at
this row size, and the page does not reduce it. D2 has no contract. There is no aggregate contract across queries (≤ 128 request
threads). Σ contracts is unbounded, so convergence feasibility is not the limiter. The binding bounds are **time** (D3: a query
holds its versions ≤ 5 s) and **multiplicity**. **Budget:** 2,048 MiB − baseline B (≈ 110 MiB) ≈ 1,940 MiB headroom. A
closed-loop query's D1 ramps from 0 to 2N versions during its first phase and drops at its end. So Q queries at random phases
hold ≈ Q × D1 / 2 on average, and up to Q × D1 when phases align. Q_T is set so that the average reaches ≈ 90 % of the headroom
(1.8 × headroom / D1). For example, at `w4k`, Q = 7 gives an average of 7 × 257 = 1,800 MiB (93 %) and an aligned peak of
3.6 GiB, so OOM is predicted (U4's calibration: G1 with large live sets fails before 100 % alignment). Controls at Q = 7:
C-ONE ≈ 7 × (8 MiB held + 10 MiB chunk) ≈ 126 MiB; C-small ≤ 7 × 36 MiB ≈ 250 MiB; I-patch ≤ 7 × 32 MiB ≈ 224 MiB.

### 2.5 Workload and environment

1. **Harness** under `harness/` in this folder, adapted from B22's (`../cached_rows_fail_threshold--rfp-counts-versions-not-bytes/harness/`:
   `ctl.sh`, `run-arm.sh`, `B22Load.java`, `B22Sampler.java`, `load-data.sh`, `netpoll.sh`, `gcwin.py`, `hprofhist.py`,
   `hprofstacks.py`, `steps.py`, `RfpJmx.java`, `rfp.btm`), with attribution. Changes: keyspace `r24`, the tables below, fetch
   size 128, client check that every completed page has 128 rows and `c = 0..127`, per-query outcome and latency log,
   `hprofhist.py` buckets for `byte[]` of length 65,536 and 2,048, and a JMX read of the `ShortReadProtectionRequests` meter.
2. **Data (once, before the readings):** keyspace `r24` `SimpleStrategy` RF 2. Tables `w2k`, `w4k`, `w8k`, `w12k` (pad 65,536 B)
   and `s2k`, `s4k`, `s8k`, `s12k` (pad 2,048 B), each `(k int, c int, v text, pad blob, PRIMARY KEY (k, c))`, defaults; one
   partition `k = 0`, `c = 0..N−1`, `v = 'x'`. Written at CL ALL by 8 loader threads (≈ 1.75 GB + 55 MB per replica), then
   `nodetool flush r24` and `nodetool compact r24` on both nodes (one SSTable per table per node). Check with `nodetool tablestats r24`
   and a CL ALL `count(*)` per table. Then stop both nodes cleanly (`nodetool drain`) and keep the data directories as templates;
   every lifetime starts from a fresh copy (`cp -a`, ≈ 3.6 GB). Hints folders are checked empty.
3. **Query:** `SELECT k, c, v, pad FROM r24.<table> WHERE v = 'x' ALLOW FILTERING`, fetch size 128, CL per arm, first page only,
   closed loop per worker (B22's loop).
4. **Lifetime (per run, clean start):** fresh data copy; start node 1 then node 2 (`setsid nohup`, each in its swap-0 scope);
   wait for both `UN`; read the thresholds back by JMX (`RfpJmx`, read only); start the sampler, `netpoll.sh` and the client steps
   `1:20,Q:160` (1 worker for 20 s warm-up, then Q workers for 160 s or until the victim dies); 30 s idle; stop. One measured
   lifetime at a time on the node.
5. **Calibration (before the readings; fixes N\* and Q_T by pre-declared rules, not readings):**
   - **DIAG-A (timing and K ladder; victim heap 8 GiB only for this lifetime so that GC does not limit it; calibration, not a V7
     budget):** Q = 1, at QUORUM, F = 128: 5 queries each on `w2k`, `w4k`, `w8k`, `w12k`, in that order. Record per query the
     latency and outcome, and per table the K max bucket and the `ShortReadProtectionRequests` delta. Also: 3 queries on `w2k` at
     **F = 1,024** (page-independence: K must equal the F = 128 value); 3 queries on `w4k` at **CL ONE** (K = 128, about 0 fetches);
     3 queries on `w2k` with `LIMIT 10` added (a LIMIT, not the fetch size, sets the page; K predicted 4,096).
     **Rule:** N\* = the largest N whose 5 queries all complete with K max bucket ≥ 2N and median latency ≤ 2.0 s (≤ 40 % of
     the 5-s deadline, leaving room for concurrency and GC at 2 GiB). If no N qualifies, the design input is invalid: record a
     dated amendment (a smaller F or N ladder) before any reading.
   - **Q_T = clamp(ceil(1.8 × (2,048 − B) / D1(N\*)), 2, 16)** with D1 from §2.4 and B the baseline measured in DIAG-C
     (Q_T = 14 / 7 / 4 / 3 for `w2k` / `w4k` / `w8k` / `w12k` at B = 110 MiB; cap 12 on a 32-core node).
   - **DIAG-C (reachability at the readings budget, 2 GiB / 15,872M):** Q = 1 for 20 s, then Q = ceil(Q_T/2) for 60 s on
     `w<N*>` at QUORUM. Rules, applied once, in order: (i) if the Q = 1 queries all time out, step N\* down one rung and
     recompute Q_T; (ii) if > 30 % of the queries at Q_T/2 time out (`ReadTimeoutException` from the 5-s fetch deadline), step N\*
     down one rung and recompute Q_T; (iii) if DIAG-C itself ends in OOM, record it (not counted) and set Q_T := ceil(Q_T/2);
     (iv) if the dropped large messages exceed 5 % of the completed ones, set F = 64 (4 MiB chunks) for every arm.
   - **DIAG-B (optional, Byteman `rfp.btm` probe; drop first):** victim 8 GiB, `w2k` QUORUM × 3: `PEAK populate` must show
     4,096 versions and ≈ 65,824 B per version (`measureDeep`).

### 2.6 Instruments (U independent of K)

- **K (the control's counter):** JMX `…type=Table,keyspace=r24,scope=<table>,name=ReplicaFilteringProtectionRowsCachedPerQuery`
  (max and recent buckets, `TableMetrics.java:837`), `…name=ReplicaFilteringProtectionRequests` (second-phase fetches; predicted
  0) and `…name=ShortReadProtectionRequests` (predicted 2N/F per completed query; `TableMetrics.java:835`), every 5 s. RFP log
  lines in node 1's `system.log`: the warn threshold (`cached over 2000`) is expected; a fail-threshold (`ERROR … cached over
  32000`) line is predicted absent.
- **U (physical, independent of K):** (a) the sampler at 1 s on JMX 7199: heap used, NTR active/pending, ReadStage active,
  direct `BufferPool`; (b) **the shipped GC log: heap after every `Pause Full` and after each young/mixed pause** (the primary U,
  as B22's Ve3), plus the STW fraction per 60 s (`gcwin.py`); (c) one `jcmd GC.class_histogram` 40 s into the Q step in every
  lifetime still alive then: count and bytes of `byte[]` of length 65,536 (held versions plus ≤ F page aliases per query) and
  2,048 (C-small); (d) at an OOM, the hprof (`hprofhist.py`, `hprofstacks.py`): `byte[65,536]` count and bytes, number of
  `ReplicaFilteringProtection$PartitionBuilder`s and their `ArrayDeque` sizes, `byte[]` ≥ 4 MiB with their owners (D2 chunks),
  and the thread and stack of the first `OutOfMemoryError`; (e) `RssAnon` of the victim at 1 s (informational).
- **Load and completion (client, per second and per query):** queries started, completed (rows per page must be 128), read
  timeouts (with the "received x of y" text), Overloaded errors, other errors; latency per completed query; NTR active ≥ Q
  confirms actual concurrency.
- **Internode (frozen now; B22's Ve2 made a design instrument):** `nodetool netstats` on both nodes every 10 s: large messages
  completed / dropped per sender; `overloaded; dropping` lines in both `system.log`s.

### 2.7 Arms, controls and intervention

All readings arms: same build (except I-patch), same data, same 2-instance layout, victim **2 GiB / 15,872M**, peer 16 GiB, steps
`1:20,Q:160`, clean start per run, table `w<N*>` (or `s<N*>`), F = 128 (or 64 by DIAG-C rule iv), Q = Q_T (or the stepped Q).

| Arm | Table | CL | Build | Runs | Role |
|---|---|---|---|---|---|
| **T** (test) | `w<N*>` | QUORUM | unmodified | 3 (+ 2 if mixed) | the claimed endpoint |
| **C-small** (matched control, V2) | `s<N*>` | QUORUM | unmodified | 3 | same K, page, fetch count and Q, 32× smaller rows: the count is a fair proxy here |
| **C-ONE** (attribution control) | `w<N*>` | ONE | unmodified | 3 | same rows, page and Q; one source, so no short-read fetches: RFP holds one page (B22 §3.2 c) |
| **I-patch** (intervention, V4) | `w<N*>` | QUORUM | **diagnostic build**: RFP consumes page-sized chunks on range reads too | 3 | bounds D1 to ≈ 2F versions per query while still serving the same pages; record pages/s against T's |

**I-patch build:** a copy of `cassandra-base` at `/mydata/s4/r24/tree-patched`, one-line diff (saved as `harness/i-patch.diff`,
with the jar's sha256):

```
-        this.consumeEntirePartitions = command.limits().isUnlimited() || !command.isLimitedToOnePartition() || command.rowFilter().hasStaticExpression();
+        this.consumeEntirePartitions = command.limits().isUnlimited() || command.rowFilter().hasStaticExpression();
```

This is 20639's single-partition behaviour extended to range reads. With one partition per table and agreeing replicas, the
first page is the same 128 rows (the client checks `c = 0..127`). No claim is made about its general correctness: it is a
diagnostic build. Build with `ant jar` offline (≤ 45 min). **Fallback** if the build fails: the unmodified build with a Byteman
rule `ShortReadRowsProtection.moreContents` AT ENTRY `return null` (no short-read row fetches, so RFP holds the first chunk per
replica). The same pages are served for agreeing replicas. The rule is saved as `harness/i-srp-off.btm`, labelled.

**Pre-declared Q step (a boundary, not an amendment):** if T survives its first 2 runs at Q_T, then T runs × 3 at
**Q_T + ceil(Q_T/2)** (cap 16, or 12 on a 32-core node), and every control runs at that Q. Controls always run at the Q of the T
condition that is claimed. There is no escalation after an OOM.

### 2.8 Predicted response and stopping budget

| Arm | Prediction (with numbers, for N\* = 4,096, Q_T = 7; scale by §2.4 for another N\*) |
|---|---|
| DIAG-A | K max bucket ≥ 2N per table (4,096 / 8,192 / 16,384 / 24,576; never > 32,000). `ShortReadProtectionRequests` ≈ 2N/128 per query. F = 1,024 on `w2k`: the same K (4,096). CL ONE on `w4k`: K = 128 and ≈ 0 short-read fetches. `LIMIT 10` on `w2k`: K = 4,096. Latency grows about linearly with N; `w2k`/`w4k` ≤ 2 s at Q = 1 |
| DIAG-C | Q = 1 completes; at Q_T/2 ≤ 30 % timeouts; live heap after GC ≤ 60 % of 2 GiB; drops ≤ 5 % |
| T | **Java heap OOM in ≥ 2/3 runs** within the 160 s at Q (expected first within ≈ 60 s). Live heap after GC rises past 1.7 GiB before it. The first `OutOfMemoryError` is on a Native-Transport-Requests thread in RFP row deserialization or `addRow`, or on a ReadStage or messaging thread allocating a chunk (`LocalDataResponse.build`, `RemoteDataResponse` deserialization). hprof: `byte[65,536]` ≥ 0.6 × (dump size) / 64 KiB, i.e. D1 ≥ 60 % of the dumped live heap; ≥ 2 builders holding > 1,000 rows. K max bucket for 8,192 and no fail-threshold line. Completed pages at Q: 1–4 per s before the OOM. A run that ends in GC service loss (≥ 90 % STW over ≥ 60 s) without an OOM is recorded as service loss |
| C-small | 0/3 OOM; live heap after GC ≤ 0.5 GiB; the same K bucket as T; pages complete |
| C-ONE | 0/3 OOM; live heap after GC ≤ 0.4 GiB; K bucket ≈ 128; pages complete at ≥ T's rate |
| I-patch | 0/3 OOM; K bucket ≈ 256; ≈ 0 short-read fetches; pages complete at ≥ T's rate (useful work kept); live heap after GC ≤ 0.5 GiB |

**Stopping budget:** a lifetime takes ≤ 9 min (data copy ≈ 1 min, start ≈ 1.5 min, 180 s load, 30 s idle, collect ≈ 1 min).
Readings: ≤ 17 lifetimes (T ≤ 8 including the step and mixed extension, C-small 3, C-ONE 3, I-patch 3), plus DIAG-A, DIAG-C,
optional DIAG-B, and ≤ 2 budget-search lifetimes. Load ≤ 40 min, patched build ≤ 45 min (it may overlap the load). Wall budget:
**≤ 5 h from the stage-2 start; no lifetime starts after start + 4 h 15 min**; every process stopped and §3–§4 written by
start + 5 h. A lifetime whose victim fails to reach `UN` twice is invalid and is repeated at most once.

### 2.9 Budget search

After T has ≥ 2 OOMs at 2 GiB: **4 GiB heap at Q = 2 × Q_final**, then **8 GiB at Q = 4 × Q_final** (cap 32), one run each (n/1),
direct auto (15,872M), same steps. Report the largest failing heap. Above that, the 5-s deadline and per-query throughput may
cap the aggregate (D3): a survival there is the boundary, not a negative.

### 2.10 Interpretation rules (fixed before readings)

- T ≥ 2/3 heap OOM (or ≥ 3/5 after a mixed extension), C-small 0/3, C-ONE 0/3, I-patch 0/3 with pages served, and the hprof
  showing D1 (`byte[65,536]` held by RFP builders) as the dominant holder with K ≤ 32,000 → the claim holds: `verified-OOM ·
  deployment`, bypass (accounting omission: whole partition × replicas held, counted in rows, × multiplicity Q) → **true positive**.
- If T OOMs while most of its queries time out (completed pages < 20 % of started queries), the endpoint still stands (the
  memory is RFP's, within its count). Record the completion rate in the conclusion.
- If C-ONE or C-small also OOMs at the claimed Q → attribution fails at that Q: step Q down by ceil(Q/3) for T and that control
  (× 3 each) if time allows; if the control still fails wherever T fails → **retry** (attribution).
- If T survives at Q_T and at the stepped Q with live heap after GC < 1.6 GiB: if > 30 % of its queries time out at the 5-s
  fetch deadline → **retry** with "smaller N, more Q" named; otherwise measure per-query U, and if Q × U/2 + B < 2 GiB by
  ≥ 20 % → **retry** with the corrected Q named. A **false positive** needs the protocol's three conditions (§"False positive or
  retry" of the playbook), including the budget search being blocked by the deadline arithmetic.
- K max bucket < 2N\* (the partition not drained), second-phase fetches > 0, pages not at 128 rows, or drops > 5 % in T →
  invalid design input; fix and record a dated amendment before new readings.
- A direct-memory OOM before the heap (D5/D7/D9) is recorded as that endpoint, not as the claim.

### 2.11 Time plan (relative to the stage-2 start S) and drop order

| Window | Work |
|---|---|
| S – S+0:45 | harness copy and adaptation, configs, start both nodes, load, flush, compact, read-backs, templates; patched build in parallel |
| S+0:45 – S+1:05 | DIAG-A (8 GiB), DIAG-C (2 GiB); fix N\*, Q_T (and F) by the rules; record them in §3 before the readings |
| S+1:05 – S+1:35 | T × 3 (Q step after 2 survivals) |
| S+1:35 – S+2:05 | C-ONE × 3 |
| S+2:05 – S+2:35 | I-patch × 3 |
| S+2:35 – S+3:05 | C-small × 3 |
| S+3:05 – S+3:25 | budget search 4 GiB, 8 GiB |
| S+3:25 – S+4:15 | slack: stepped Q or mixed-outcome extension; else DIAG-B |
| S+4:15 – S+5:00 | no new lifetimes; hprof analysis, §3–§4, write-backs, stop everything, clean `/mydata/s4/r24` data except logs and one dump |

**Drop order** (first dropped first): DIAG-B; the 8 GiB search; DIAG-A's `LIMIT 10` and `F = 1,024` lines; the 4 GiB search;
C-small to 1 run (C-ONE then serves as the V2 control). Never dropped: DIAG-A's ladder, DIAG-C, T × 3, C-ONE × 3, I-patch × 3.

### 2.12 Decision

- **`ready_for_stage2 = true`.** All constraints at shipped defaults (V6), one budget of 2 GiB heap with resolved direct (V7,
  standing rule), no container budget, node `pc72` (fallback `pc75`/`pc82`) idle at the read-only check apart from another
  workflow's lock, harness mostly reusable from B22. Retry items (1)–(4) of B22 are each addressed: (1) partition-sized hold
  (§2.4); (2) 8 MiB chunks, the send-queue reserve mapped (D4), drops and timeouts frozen as instruments, and the binding 5-s
  short-read deadline mapped (D3) and calibrated (DIAG-A/C); (3) one budget for every arm, U from the GC log; (4) C-small and
  C-ONE kept, and an intervention that serves pages (I-patch).

`sha256 of §1–§2 at freeze: 7bd8ed5fc8ccdf7327bc9f6de9909ce545217af5e2fbcd750fc5a32ec6b3dc02 (computed over the lines from `## 1. Candidate` up to, not including, this line)` · amendments after the freeze: none.

## 3. Runs (stage 2)

pending

## 4. Conclusion (stage 2)

pending
