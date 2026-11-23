# B22 (OC-479) — cached_rows_fail_threshold: replica-filtering protection counts row versions, not bytes, and never counts the raw replica responses  <!-- file: cassandra/cases/cached_rows_fail_threshold--rfp-counts-versions-not-bytes/cached_rows_fail_threshold--rfp-counts-versions-not-bytes.md -->

| Field | Value |
|---|---|
| Case ID | `B22` (B = bypass case; README "ID prefixes"), provisional ID kept: the design is a bypass (accounting omission), see §2.1 |
| From | `OC-479` of the phase 1 OOM candidate list (triage 2026-11-20 rank 5; cluster OC-469, OC-470, OC-480, legacy OC-39) |
| Phase-1 case file | [`cached_rows_fail_threshold-queryProtectedPartitions-i--autonomous`](../../../../capacity-enforcement-exp/cassandra/stage3-ai-deep-read/cases/cached_rows_fail_threshold-queryProtectedPartitions-i--autonomous.md) · stage-4 result [`results/…`](../../../../capacity-enforcement-exp/cassandra/stage4-runtime-verification/results/cached_rows_fail_threshold-queryProtectedPartitions-i--autonomous.md) |
| System / pinned source | Cassandra 5.0.9 (`systems/cassandra/source/`); built copy `pc82:/mydata/s4/cassandra-base` (`build/apache-cassandra-5.0.9-SNAPSHOT.jar`) |
| Stage 1 (design) | phase-2 OOM agent, stage 1 (Claude Opus 5.5), 2026-11-21 08:03–08:50 EST; nothing run (pc82 checked read-only) |
| Stage 2 (verify) | fresh phase-2 OOM agent, stage 2 (Claude Opus 5.5), 2026-11-21 08:14–10:20 EST on `pc82`; 20 measured lifetimes + LOAD + DIAG, 08:19–10:12 EST |
| Verdict | **`retry`** (protocol status `candidate`: heap OOM 2/5 at 2 GiB / 1,024 MiB direct, 0/6 at the frozen 2 GiB / 15,872 MiB) |

## Summary

- **Conclusion (stage 2): retry.** At the frozen budget (2 GiB heap, direct 15,872 MiB), 6 concurrent QUORUM filtering reads did
  **not** run node 1 out of heap in 6 runs (Q 5 ×2, Q 6 ×4); live heap after full GC peaked at 1.28–1.69 GiB. The same load at
  2 GiB / 1,024 MiB direct (optional arm E2) gave a **Java heap OOM in 2 of 5 runs**, with RFP held versions plus raw responses at
  77–84 % of the dump and K = 12,000 ≤ 32,000. The controls survived: C-small 0/3, C-ONE 0/3, intervention T = 2,000 0/3 (no page
  served).
- **What stopped it:** a protection the design did not map. The internode **outbound send-queue reserve** (128 MiB per endpoint)
  admits one ~98 MiB response per sender and drops the next, so about half of the queries time out at 10 s and release their memory.
  At QUORUM the coordinator's own replica response also goes through messaging.
- **Root cause (confirmed by calibration):** RFP charges row versions, not bytes, and does not charge the raw responses: 12,000
  versions = 433 MiB per query with 20 KiB rows against 46 MiB with 2 KiB rows. RFP also consumes the **whole partition**
  (short-read protection fetches past the page), so held versions grow with the partition up to 32,000. The retry should use that:
  long partitions and small internode messages.
- **Hypothesis (stage 1):** every filtering read at CL above ONE goes through replica-filtering protection (RFP).
  RFP keeps every replica's version of every row of the current partition on the coordinator heap and charges
  them to `cached_rows_fail_threshold` (32,000) as a **count**. The count ignores row bytes, and the raw replica
  responses that RFP reads from (one heap buffer per replica, held for the whole query) are not charged at all.
  With the driver's default 5,000-row page of 20 KiB rows on a 2-node RF 2 ring, one `ALLOW FILTERING` query at
  QUORUM is charged 10,000 versions (31 % of the threshold) but holds ≈ 0.39–0.42 GiB on the coordinator. Nothing
  sums concurrent queries, so 5 concurrent queries are predicted to exhaust a 2 GiB heap; the same load at CL ONE
  (one replica, one version) and the same count with 2 KiB rows are predicted to survive.

## 1. Candidate

**Candidate row (quoted from `phase1-oom-candidates.md`, line 488):**

> | OC-479 | 2026-11-18 | `cached_rows_fail_threshold-queryProtectedPartitions-i--autonomous` | guided | Holder: the coordinator's ReplicaFilteringProtection PartitionBuilder.contents (ArrayDeque of rows), plus the raw replica responses. [details](runs/wave3.md#oc-479) | CP-2, CP-7, CP-1 | picked: B22 (2026-11-21) |

**Details (quoted from `runs/wave3.md#oc-479`):**

> Holder: the coordinator's ReplicaFilteringProtection PartitionBuilder.contents (ArrayDeque of rows), plus the raw replica responses. Why nothing stops it: cached_rows_fail_threshold counts row versions (null versions included), not bytes, and applies per query. One RFP is built per filtering or index read at CL above ONE, and nothing caps the sum across the 128 native-transport request threads. The raw Message<ReadResponse> payloads are outside the count. Size at defaults: T = 32,000 versions gives 16,000 held rows at RF 2. At 2 KiB rows that is about 32 MiB held plus a similar amount of raw responses, so about 64 MiB per query. 128 concurrent queries reach about 8 GiB, more than an 8 GiB heap minus its memtable quarter.
>
> **Where:** systems/cassandra/source/src/java/org/apache/cassandra/service/reads/ReplicaFilteringProtection.java:316-332, :477-492; service/reads/DataResolver.java:122-144, :252-258

**Triage (quoted from `runs/triage-2026-11-20.md`, rank 5):**

> | 5 | OC-479 | yes | multi-node: 2 instances, RF 2, CL QUORUM or ALL | Every filtering or index read above CL ONE goes through replica-filtering protection (`DataResolver.java:122-144`). Its PartitionBuilder caches row versions on the coordinator until cached_rows_fail_threshold (32,000 versions, a count), and the raw replica responses are not counted at all. A client page of 16,000 rows (the page_size guardrail is off) of about 8 KiB (one remote response about 128 MB, at the internode cap) gives about 256 MB of cached rows plus about 256 MB of raw responses, about 0.5 GB per query. 4–8 concurrent queries pass a 2 GiB heap. It is weaker than ranks 1–4 because the per-query size is capped by the internode message limit. Test time: 1–2 h. | Same row-count family as U4 and B16. Duplicates OC-469, OC-470 and OC-480 (OC-470/480: the static-column completion fetch reads a whole partition with no limit, up to 128 MiB), and the legacy OC-39 (open). |

**Cluster duplicates named by the triage (quoted) and what this design covers:**

> | OC-469 | 2026-11-18 | `cached_rows_fail_threshold-queryProtectedPartitions-i--autonomous` | autonomous | Holder: the coordinator heap in RFP PartitionBuilder.contents/staticRow (ArrayDeque<Unfiltered>), plus the full Message<ReadResponse> payloads of every replica. [details](runs/wave3.md#oc-469) | — | open |

> | OC-470 | 2026-11-18 | `cached_rows_fail_threshold-queryProtectedPartitions-i--autonomous` | autonomous | Holder: the second-phase completion fetch (fetchFromSource). When a static-column predicate leaves the static row unresolved, it reads the entire partition from the silent replica with DataLimits.NONE and the command's full clustering filter. [details](runs/wave3.md#oc-470) | — | open |

> | OC-480 | 2026-11-18 | `cached_rows_fail_threshold-queryProtectedPartitions-i--autonomous` | guided | Holder: the second-phase protection fetch, fetchFromSource. When a static-column predicate is unresolved, it reads the entire partition from the silent replica with DataLimits.NONE and RowFilter.none(), outside the cached-rows count. [details](runs/wave3.md#oc-480) | CP-10, CP-12 | open |

> | OC-39 | 2026-11-16 | `cached_rows_fail_threshold-queryProtectedPartitions-i--autonomous` | legacy | [lead list, blind, E3; N17 cluster; queued as U4] Replica-filtering protection caps rows per query, not bytes, with no cap across queries: 128 concurrent queries × 16,000 held rows × 2 KiB, plus raw replica responses outside the count, ≈ 8 GiB, more than an 8 GiB heap leaves after the memtable pool (response size estimated). | CP-2, CP-7 | open |

| Row | Holder | Covered by this design? |
|---|---|---|
| OC-479 (primary) | `PartitionBuilder.contents` + raw responses, × concurrent queries | **yes** — every arm |
| OC-469 | the same holder (it adds `staticRow`, not used here) | **yes** — same holder and shape; the static row is not exercised |
| OC-470, OC-480 | second-phase `fetchFromSource` of a whole partition when a **static-column** predicate leaves the static row unresolved (`ReplicaFilteringProtection.java:510`, `:623-630`) | **no** — needs a static-column predicate and divergent replicas; a different holder (one single-partition response, ≤ 128 MiB remote, unbounded local). Not an arm here; they stay with the cluster for a later case or a retry arm |
| OC-39 (legacy) | the same holder, × 128 queries at 8 GiB | **yes** — same mechanism; this design scales it to a 2 GiB heap with larger rows, and the budget search (§2.9) goes up to 8 GiB |

The stage-2 session writes the verdict to OC-479; whether OC-469 and OC-39 are closed with it is the owner's call
(they are the same holder); OC-470/OC-480 are not closed by this case.

**Phase-1 constraint and stage-4 result.** The phase-1 case traced `replica_filtering_protection.cached_rows_fail_threshold`
(`ReplicaFilteringProtectionOptions.java:23-27`, default 32,000) to `incrementCachedRows()` (`ReplicaFilteringProtection.java:319-345`),
which throws `OverloadedException` at count T+1, one count per row version per replica, null versions counted but not stored
(`:477-492`), released per partition (`:564`). Its A4 names the raw `Message<ReadResponse>` payloads, second-phase fetches,
the CQL result and other queries as consumers outside the cap. Stage 4 (2026-10-27, advisor's Mac, 2 nodes RF 2, outcome class
**true positive**, i.e. the cap caps): at T = 1000 / 10000 / 32000 the query failed at count T+1 holding exactly 500 / 5,000 / 16,000
rows (0.40 / 4.0 / 12.8 MB at **800 B per held row** for a 512 B pad); at T = 1,000,000 it held all 100,000 rows (80.0 MB); the raw
response of the remote replica was **52,981,352 B outside the count** in every run. The stage-4 unit control showed that **agreeing
replicas are counted too** (both versions, histogram bucket of 2N). Stage 4 ran one query at a time; it never sized rows for bytes or
ran concurrent queries. Stage-4 recommendation 10 (the single-partition `LIMIT` branch, `:409-431`) is not used here (range reads).

**Related OOM-exp cases.** U4 (true positive): a default 5,000-row page of 48 KiB rows held twice on a single node's heap (replica
buffer + `ResultSet`), 3 concurrent reads OOM a 2 GiB heap — the same "page bounded in rows" holder without RFP. B16 (true positive):
`tombstone_failure_threshold` counts markers, not bound bytes — the same accounting-omission shape for a different counter. This case
differs from U4 by the RFP-specific memory (a second replica's raw response plus every replica's held version, ≈ 2× U4's per-query
footprint for the same page) and isolates it with a CL ONE arm (§2.7).

**JIRA prior art (read only; nothing posted).** `jira-oom-survey.csv` (605 lines): no row on replica-filtering protection memory;
CASSANDRA-8272 (2i stale data, excluded as a correctness bug) is the origin of RFP. REST (`issues.apache.org`, reachable 2026-11-21
08:12 EST): `text ~ "replica filtering protection"` → 59 issues; with OOM/heap/memory terms → 65 hits, none reporting coordinator
memory exhaustion under the threshold. **CASSANDRA-15907** "Operational Improvements & Hardening for Replica Filtering Protection"
(Fixed 3.0.22 / 3.11.8 / 4.0) introduced the per-partition caching and the two count thresholds — the design under test; the yaml
says the thresholds "limit the number of rows … individual index and filtering queries can materialize on-heap"
(`conf/cassandra.yaml:1823-1825`) and are per query (`:1827-1828`). CASSANDRA-16896 (Fixed 4.1) added the byte-based local/coordinator
read-size thresholds, which ship **off** (`read_thresholds_enabled: false`, `Config.java:526`). CASSANDRA-20243 (RFP over-fetches
partition data when no static predicate, Fixed 2025) and CASSANDRA-21623 (report rows cached on warn, Fixed 2026-08) touch RFP
fetching and reporting, not a byte charge. **Verdict: `new`** for the byte gap (the count design itself is documented by 15907);
not a known-fixed bug, so not a positive control.

## 2. Design solution (stage 1; frozen)

### 2.1 Mechanism and direction

A range read with a row filter (`SELECT … WHERE v = 'x' ALLOW FILTERING`, no partition-key restriction) at CL QUORUM on an RF 2
keyspace sends a full data request to both replicas (range reads use no digests) and resolves the two responses in
`DataResolver.resolve()`, which takes the RFP path whenever the row filter is non-empty and the query is not top-K or an index that
opts out (`DataResolver.java:122-123`, `:132-144`). `resolveWithReplicaFilteringProtection` builds one RFP per query with the
yaml thresholds (`:252-258`). Because the command is not limited to one partition, `consumeEntirePartitions` is true
(`ReplicaFilteringProtection.java:143`): the first-phase merge of each partition calls `onMergedRows` for every row and
`PartitionBuilder.addRow` for **every replica's version** (`:222`), which counts it (`incrementCachedRows`, `:319-345`, throw at
T+1 `:331`) and, when non-null, stores the deserialized `Row` in the builder's `ArrayDeque` `contents` (`:458`, `:477-492`). The
count is released only when the protected partition is consumed (`:564`), so a wide partition holds all its rows' versions at once.
The count has **no byte component**: a 20 KiB row costs one count, like a 50 B row. The two replica responses RFP iterates are held
in full for the whole query, uncounted: the coordinator's own `LocalDataResponse` serialized into a heap `DataOutputBuffer`
(`db/ReadResponse.java:182-203`, no size limit) and the remote replica's `RemoteDataResponse` read into one heap buffer
(`ReadResponse.java:338`, `readWithVIntLength`), the latter bounded only by `internode_max_message_size` (128 MiB at defaults,
`DatabaseDescriptor.java:988-995`, checked by the sender `OutboundConnection.java:979-980`). The rows per response are bounded by the
page in **rows** (driver default 5,000), and the byte-based read thresholds are off (`Config.java:526`). Nothing sums concurrent
queries (`native_transport_max_threads` 128 bounds them implicitly). The CQL `ResultSet` takes the merged cells' buffers without a
copy (`cql3/statements/SelectStatement.java:1146`), so it aliases one held version (ledgered, not claimed).

**Direction: bypass · accounting omission** (bypass technique note, "Accounting mismatch: fixed charged usage with varying object
shape/copies"; B16 is the same shape): the RFP control charges K = row versions and stays within its contract (K = 10,000 ≤
32,000), while the physical memory of the path it protects (held versions **and** the raw responses it reads from) is U ≈ 0.4 GiB
per query. The endpoint needs 5 concurrent queries, so by the protocol's table it is a bypass excess **stacked by multiplicity**
(no aggregate control exists); stage 2 records it as `bypass` with the multiplicity stated, and reclassifies by the rules of §2.10
if the CL ONE arm also OOMs (then U4's unprotected page holder alone suffices and the RFP attribution fails).

### 2.2 Protection map (fixed before any reading; victim = coordinator node 1)

| Domain | Allocation and owner (release) | Local contract (K, limit, at limit) | Scope / multiplicity | Aggregate coverage | Claimed? |
|---|---|---|---|---|---|
| **D1 RFP held versions** | `PartitionBuilder.contents` (`ArrayDeque<Unfiltered>`, `RFP.java:458`), one builder per replica per partition; deserialized `Row`s (values copied, stage 4: 800 B per 512 B-pad row); released when the protected partition closes (`:564`) | K = `currentRowsCached` (row versions incl. null); T = `cached_rows_fail_threshold` 32,000 (warn 2,000); `OverloadedException` at T+1 (`:319-345`) | per query; Q concurrent queries | none | **yes** (bypass: count, not bytes) |
| **D2 raw replica responses** | `ResponseResolver.responses` → `Message<ReadResponse>`: local `LocalDataResponse` heap buffer (`ReadResponse.java:197-203`), remote `RemoteDataResponse` heap buffer (`:338`); held until the query's resolver is dropped | none (not counted by RFP); remote only: `internode_max_message_size` 128 MiB per message (sender refuses; the read then times out) | per query × replicas (2 at QUORUM, 1 at ONE) | none | **yes** (accounting omission) |
| D3 page row limit | replica `DataLimits` of the page; driver default fetch size 5,000 rows | rows only; `read_thresholds_enabled: false` → `local_read_size_*`, `coordinator_read_size_*` off; `page_size_*` guardrail off (yaml `:2015-2026`, `:2089-2090`) | per query | — | no (the dial that sizes D1/D2; U4's domain) |
| D4 CQL result | `ResultSet` rows alias D1 cell buffers (`SelectStatement.java:1146`); ≈ 0.5 MB of list overhead per page | none | per query | — | ledgered |
| D5 encoded client response | Netty **direct** buffer from `Message.encode` until flushed (C2's domain) | `MaxDirectMemorySize` | per query | — | ledgered (direct) |
| D6 inbound large message (node 1) | remote response frames buffered on receive (direct, BufferPool) until deserialized | `internode_application_receive_queue_reserve_endpoint_capacity` 128 MiB / global 512 MiB (one large message at a time per endpoint) | per peer | yes (reserve) | ledgered (direct, transient) |
| D7 memtables | `memtable_heap_space` = ¼ heap = 512 MiB at 2 GiB | flush at cleanup threshold | per node | yes | baseline only (no writes during readings; data flushed) |
| D8 chunk cache | `file_cache_size` = min(512 MiB, ¼ heap) = 512 MiB at 2 GiB (`DatabaseDescriptor.java:576-577`), direct | pool cap + unpooled overflow (C9) | per node | yes | ledgered (direct) |
| D9 baseline | schema, caches, Netty, metrics; key cache min(5 % heap, 100 MiB) | — | per node | — | baseline (measured at warm-up) |

### 2.3 Configuration and budget audit

- **Node:** `pc82` (node1.jason92-326665; x86_64, 40 cores, 125 GiB RAM, `/mydata` 714 GiB free; Ubuntu 22.04, kernel 5.15, cgroup
  v2, 8 GiB swap present). Read-only check 2026-11-21 08:06 EST: no `CassandraDaemon` running, load 0.00, `/mydata/s4/` holds only
  `cassandra-base` (jar `build/apache-cassandra-5.0.9-SNAPSHOT.jar`), OpenJDK 11.0.33, Python 3.10.12, `lib/` has
  `cassandra-driver-core-3.12.1-shaded.jar` and `cassandra-driver-internal-only-3.29.0.zip`, `jcmd` present; loopback `127.0.0.1/8`
  (so `127.0.0.2` needs no alias). Run folder: `/mydata/s4/b22/` (not yet created).
- **Topology (environment deviation, recorded):** two Cassandra instances on one host, RF 2 (owner's instruction). Node 1
  (**victim/coordinator**) `127.0.0.1`, node 2 (**peer replica**) `127.0.0.2`; each with its own `CASSANDRA_CONF`, data, commitlog,
  hints, saved_caches and log directories under `/mydata/s4/b22/n1|n2/`; same `storage_port` 7000 and `native_transport_port` 9042
  on different addresses; JMX 7199 (node 1) and 7299 (node 2); seeds `127.0.0.1`; `auto_bootstrap: false` on both (empty ring,
  schema created after both are up); `cluster_name: b22`. A shared host means shared disk, page cache and CPU; the peer's serving
  work (building 5 × ≈ 100 MB responses) competes for CPU with the victim. Not a capacity or budget change.
- **Capacity constraints (V6):** all at shipped defaults, resolved at the victim's heap: `cached_rows_fail_threshold` 32,000,
  `cached_rows_warn_threshold` 2,000; `read_thresholds_enabled` false; `internode_max_message_size` = min(receive, send endpoint
  reserve) = 128 MiB = 134,217,728 B; `native_transport_max_threads` 128; `concurrent_reads` 32; `memtable_heap_space` 512 MiB;
  `file_cache_size` 512 MiB; `page_size_*`, `partition_size_*`, `column_value_size_*` guardrails off; `max_mutation_size` 16 MiB
  (half of `commitlog_segment_size` 32 MiB); `read_request_timeout` 5 s, `range_request_timeout` 10 s, `native_transport_timeout`
  12 s (none raised). The only constraint changed is `cached_rows_fail_threshold` = 2,000 in the **intervention arm** (via JMX
  `StorageService.setCachedReplicaRowsFailThreshold`, `StorageService.java:6749-6752`), allowed by V6.
- **Budgets (V7):** victim heap **2 GiB** (`-Xms2G -Xmx2G` via `MAX_HEAP_SIZE`/`HEAP_NEWSIZE` unset; G1 from the shipped
  `jvm11-server.options`: `G1HeapRegionSize=16m`, `MaxGCPauseMillis=300`), direct memory **as `cassandra-env.sh` resolves on pc82
  with a hand-set heap**: G1 → `heap_limit` 31,744; ½ RAM (≈ 64,000 MiB) > 31,744 → `MaxDirectMemorySize = 15872M`
  (`cassandra-env.sh` `calculate_heap_sizes`; the U4 amendment A2 found the same). Claimed node: a large node running a 2 GiB heap
  (common practice; U4 and C2 used the same pair). Both values ≥ 512 MiB → V7 met by the standing rule. Optional arm E2 (§2.9) uses
  the 4 GiB-node class pair that `cassandra-env.sh` resolves for 4 GiB RAM: heap 2,048 MiB, direct 1,024 MiB. No container budget:
  the victim runs in `systemd-run --user --scope -p MemorySwapMax=0` (swap 0, no `MemoryMax`). **Peer heap 16 GiB** (direct
  auto) so the peer's own response buffers never end a run; the peer is not a budget of the claim (environment deviation, recorded).
  Record `-Xmx`/`MaxDirectMemorySize` from `ps` in every lifetime.
- **Other settings:** shipped `jvm-server.options` (`HeapDumpOnOutOfMemoryError`; dump path set to `/mydata/s4/b22/<lifetime>/`),
  shipped GC log; no Byteman except in the DIAG lifetime (§2.5). Table options default (LZ4, `read_repair` BLOCKING — the replicas
  agree, so nothing is repaired). Client: protocol v4 (Java driver) or v5 (bundled Python driver), whichever the reused U4 client
  uses; fetch size **left at the driver default 5,000** (Java 3.12 and Python 3.29 both default to 5,000).

### 2.4 Ceiling arithmetic

Row: `k int, c int, v text, pad blob`, pad **20,480 B** random (incompressible). Serialized row ≈ 20,500 B → one replica's page
response **S = 5,000 × 20,500 ≈ 102.5 MB = 97.8 MiB**, under the 128 MiB internode cap by 30 MiB (24 %). Held version (stage-4
overhead ≈ 290 B per row) ≈ 20,770 B.

| Per query (victim heap) | QUORUM (test) | ONE (C-ONE) | QUORUM, 2 KiB pad (C-small) | QUORUM, T = 2,000 (I) |
|---|---|---|---|---|
| K (versions charged) | 10,000 (bucket 11,864) | 5,000 (bucket 5,722) | 10,000 (bucket 11,864) | 2,001 → Overloaded (bucket 2,299) |
| D1 held versions | 2 × 5,000 × 20.8 KB = **198 MiB** | 99 MiB | 22 MiB | ≤ 2,000 × 20.8 KB = 40 MiB, then released |
| D2 local response buffer (1.0–1.4 × S, U4's measured `DataOutputBuffer` slack) | 98–137 MiB | 98–137 MiB (if served locally; 0 if remote) | 10–14 MiB | 98–137 MiB |
| D2 remote response | 98 MiB | 0 (or 98 if served remotely) | 10 MiB | 98 MiB |
| **Sum** | **394–433 MiB** | **197–236 MiB** | **42–46 MiB** | **236–275 MiB, short-lived** |

Contract capacities: D1's contract is 32,000 versions with **no byte bound** — at this row size up to 32,000 × 20.8 KB = 634 MiB per
query, and up to 32,000 × 16 MiB in principle; D2 has no contract (remote ≤ 128 MiB per message, local unbounded); no aggregate
contract across queries (≤ 128 request threads). Σ contracts is unbounded, so convergence feasibility is not the limiter.
**Budget:** 2,048 MiB heap − baseline (measured at warm-up, expected 150–300 MiB) → ≈ 1,750–1,900 MiB for queries. Test at
**Q = 5**: 5 × 394–433 = **1,970–2,165 MiB** aligned (104–124 % of the headroom) → OOM predicted. U4's calibration (3 × ≈ 0.55 GiB =
1.65 GiB aligned OOMed a 2 GiB heap 4/5) says G1 with humongous ≈ 100 MB buffers fails before 100 % alignment. C-ONE at Q = 5:
985–1,180 MiB (52–67 % of headroom); C-small at Q = 5: ≈ 230 MiB; I at Q = 5: ≤ 1,375 MiB transient (≤ 79 %), each query rejected.

### 2.5 Workload and environment

1. **Harness** under `harness/` in this folder, adapted from U4's (`../cql-row-limit--wide-row-default-pages/harness/`:
   `victim-ctl.sh`, `C2Sampler.java`, `U4Load.java`, `load-data.sh`, `gcwin.py`, `hprofhist.py`, `hprofstacks.py`, `steps.py`) and
   stage 4's RFP probe (`capacity-enforcement-exp/cassandra/stage4-runtime-verification/harness/cached_rows_fail_threshold-queryProtectedPartitions-i--autonomous/`:
   `rfp.btm`, `stage4/rfp/RfpProbe.java`, `RfpJmx.java`), with attribution. Changes: two instances (§2.3), client whitelist to
   node 1 only (`WhiteListPolicy`/`WhiteListRoundRobinPolicy` on `127.0.0.1`), consistency per arm, `FallthroughRetryPolicy` (no
   retry on another host), the query below, first page only.
2. **Data (once, before the readings):** keyspace `b22` `SimpleStrategy` RF 2; tables `b22.wide` and `b22.small`, each
   `(k int, c int, v text, pad blob, PRIMARY KEY (k, c))`, defaults. One partition `k = 0`, `c = 0..5,999`, `v = 'x'`, pad
   20,480 B (`wide`, ≈ 123 MB per replica) or 2,048 B (`small`, ≈ 12 MB), written at CL ALL by 8 loader threads; then
   `nodetool flush b22` on both nodes; check `nodetool tablestats b22` (6,000 partitions' rows, both nodes) and a CL ALL
   `SELECT count(*)` read-back. Data stays across lifetimes (read-only workload); the hints folder is checked empty.
3. **Query:** `SELECT k, c, v, pad FROM b22.<table> WHERE v = 'x' ALLOW FILTERING` — a range read (no partition-key restriction,
   `consumeEntirePartitions` = true). With 2 nodes at RF 2 every range has the same replicas and the coordinator merges them into one
   sub-range command (stage 4 saw one response per replica). Each worker issues the statement, reads the **first page** (5,000 rows,
   all matching), discards it and repeats (closed loop; the paging state is not followed, so every query is a fresh first page).
4. **Lifetime (per run, clean start):** stop both nodes (kill by PID), start node 2 then node 1 (`setsid nohup`, victim in its
   swap-0 scope), wait for both `UN`, set/read back thresholds by JMX (`RfpJmx`), start the sampler, then the client steps
   `1:20,Q:160` (1 worker for 20 s warm-up, then Q workers for 160 s or until the victim dies), then 30 s idle, then stop. On an OOM
   the shipped `-XX:OnOutOfMemoryError="kill -9 %p"` ends the victim after the heap dump. One measured lifetime at a time on pc82.
5. **DIAG lifetime (calibration, not a readings arm):** victim with Byteman (`rfp.btm`: `PEAK` at throw/populate with
   `measureDeep` of held rows, `RESP` at resolve with each response's size), Q = 1, 10 queries at QUORUM then 5 at ONE on `wide`,
   10 at QUORUM on `small`. Gives S, held bytes per version and K per query directly, without the GC noise of the arms.

### 2.6 Instruments (U independent of K)

- **K (the control's counter):** JMX `org.apache.cassandra.metrics:type=Table,keyspace=b22,scope=<table>,name=ReplicaFilteringProtectionRowsCachedPerQuery`
  (max and recent buckets, `TableMetrics.java:837`) and `…name=ReplicaFilteringProtectionRequests` (second-phase fetches; predicted
  0, the replicas agree), read every 5 s; RFP's own log line count (`Replica filtering protection has cached over`) in node 1's
  `system.log`; thresholds read back by JMX at start.
- **U (physical, independent of K):** (a) `C2Sampler` at 1 s on JMX 7199: heap used, G1 old-gen usage after GC, NTR active/pending,
  ReadStage active; (b) GC log (shipped `-Xlog:gc…`) → STW fraction per 60 s window (`gcwin.py`); (c) one `jcmd GC.class_histogram`
  at load second 60 in every lifetime still alive then (intrusive, once); (d) at an OOM, the hprof (`hprofhist.py`,
  `hprofstacks.py`): bytes and count of `byte[]` of length 20,480 (pad values: D1 held versions, aliased by D4) and of 2,048 (C-small),
  `byte[]` ≥ 90 MiB with their owners (`DataOutputBuffer`/`LocalDataResponse`, `HeapByteBuffer` of `RemoteDataResponse`: D2),
  count of `ReplicaFilteringProtection$PartitionBuilder` and their `ArrayDeque` sizes, the thread and stack of the first
  `OutOfMemoryError` (from `system.log`/stdout); (e) the DIAG probe's `PEAK`/`RESP` lines; (f) `RssAnon` of the victim at 1 s
  (informational) and NMT summary at start (direct baseline).
- **Load and completion:** client per-second counters: queries completed, rows per page (must be 5,000), Overloaded errors (with
  message), read timeouts, other errors; NTR active ≥ Q confirms actual concurrency (client thread count alone is not enough).
- **Direct memory (ledgered):** `java.nio:type=BufferPool,name=direct` (count, memory used) at 1 s, to show whether a direct OOM
  (D5/D6/D8) comes first.

### 2.7 Arms, controls and intervention

All arms: same build, same data, same 2-node layout, victim 2 GiB / 15872M (except E2 and the budget search), peer 16 GiB, steps
`1:20,Q:160`, clean start per run.

| Arm | Table | CL | T | Q | Runs | Role |
|---|---|---|---|---|---|---|
| **T** (test) | `wide` (20 KiB) | QUORUM | 32,000 (default) | 5 | 3 (+ up to 2 if mixed) | the claimed endpoint |
| **C-small** (matched control, V2) | `small` (2 KiB) | QUORUM | 32,000 | 5 | 3 | protected path: same K per query (10,000), 10× smaller rows — the count is a fair proxy here |
| **C-ONE** (attribution control) | `wide` | ONE | 32,000 | 5 | 3 | same rows, page, Q; one replica → no second response, one version (U4's holder only) |
| **I** (intervention, V4) | `wide` | QUORUM | **2,000** via JMX | 5 | 3 | the count binds: each query fails at 2,001 versions; record rejections and useful work (0 completed pages expected) |

Pre-declared Q step (boundary, not an amendment): if T survives its first 2 runs, run T at **Q = 6** ×3 and C-ONE at Q = 6 ×3
(C-ONE predicted 1,182–1,416 MiB, 62–81 % of headroom) instead of Q = 5; report both. No escalation after an OOM.

### 2.8 Predicted response and stopping budget

| Arm | Prediction (with numbers) |
|---|---|
| DIAG | `RESP`: 2 responses per QUORUM query, 102–103 MB each (≤ 134,217,728 B); `PEAK populate`: current 10,000, held rows 10,000 (5,000 per builder), bytes held 200–215 MB (≈ 20.8 KB per version); ONE: 1 response, current 5,000, held 5,000; `small`: 10,000 held, 22–25 MB |
| T (Q = 5) | **Java heap OOM in ≥ 2/3 runs** within the 160 s at Q (expected first within ≈ 60 s); G1 old-gen after GC rising past 1.8 GiB before it; first `OutOfMemoryError` on a Native-Transport-Requests, ReadStage or messaging thread in RFP row deserialization/`addRow`, `LocalDataResponse.build` (`DataOutputBuffer` growth) or `RemoteDataResponse` deserialization; hprof: ≥ 20,000 pad `byte[]` (≥ 2 queries' held versions, ≥ 0.4 GiB) and ≥ 4 `byte[]` ≥ 90 MiB (D2 of ≥ 2 queries), D1 + D2 ≥ 60 % of the dumped live heap; K max bucket 11,864 (10,000 versions) with **no** RFP log line (K never reaches 32,001); pages complete at ≈ 1–3 s each before the OOM. A run that ends in GC service loss (≥ 90 % STW over ≥ 60 s) without an OOM is recorded as service loss |
| C-small | survives 0/3 OOM; old-gen after GC ≤ 0.6 GiB; K bucket 11,864 (same K as T); pages complete; STW < 10 %/60 s |
| C-ONE | survives 0/3 OOM; old-gen after GC ≤ 1.5 GiB; K bucket 5,722; pages complete at a rate ≥ T's pre-OOM rate |
| I | survives 0/3 OOM; every query fails with Overloaded "cached over 2000 rows" (one RFP log line each); K bucket 2,299; 0 completed pages/s (recorded as stopped work); old-gen after GC ≤ 1.4 GiB |

**Stopping budget:** per lifetime ≤ 8 min (start ≈ 1.5 min, 180 s load, 30 s idle, stop/collect ≈ 1 min); readings arms ≤ 15
lifetimes + DIAG + ≤ 5 search/optional lifetimes; no run starts after **13:15 EST**; every process stopped and §3–§4 written by
**14:00 EST**. A lifetime whose victim fails to reach `UN` twice is invalid and not repeated more than once.

### 2.9 Budget search and optional arm

After T has ≥ 2 OOMs: **4 GiB heap, Q = 10** (predicted 3.9–4.2 GiB aligned → OOM), then **8 GiB, Q = 20** (7.7–8.5 GiB aligned
→ OOM likely; 20 × 98 MiB of remote responses cross one internode large-message connection in ≈ 1–3 s, inside the 10 s range
timeout; the peer's 16 GiB holds 20 × ≤ 137 MiB buffers), one run each (n/1), direct auto (15872M), same steps with Q scaled.
Report the largest failing heap. **E2** (optional): T at 2 GiB heap / **1,024 MiB direct** (4 GiB-node class) ×3 — a direct OOM
(D5 `Message.encode` 5 × 98 MiB + D8 ≤ 512 MiB + D6 ≤ 128 MiB ≈ 1.1 GiB > 1 GiB) may come before the heap; record whichever
is first, as U4's E2 did.

### 2.10 Interpretation rules (fixed before readings)

- T ≥ 2/3 heap OOM, C-small 0/3, C-ONE 0/3, I 0/3, hprof shows D1 + D2 as the dominant holders with K ≤ 32,000 → claim holds:
  `verified-OOM · deployment`, bypass (accounting omission, × multiplicity 5) → **true positive**.
- C-ONE also OOMs at the failing Q → U4's single-response holder suffices at that Q and the RFP part is not shown necessary:
  step Q down (Q = 4 for both, ×3) if time allows; if C-ONE still fails wherever T fails → **retry** (attribution), with
  "lower Q / smaller rows so ONE survives" as the change.
- T survives at Q = 5 and Q = 6 with old-gen after GC < 1.6 GiB and pages completing at 5,000 rows → measure per-query U; if
  5 × U + baseline < 2 GiB by ≥ 20 %, the estimate was wrong: **retry** with higher Q (the triage's 4–8) named.
- Pages not reaching 5,000 rows, a response refused for size (`OversizedMessageException` on node 2), or second-phase fetches
  > 0 → invalid design input; fix and record as a dated amendment before new readings.
- A direct-memory OOM before the heap (D5/D6/D8) is recorded as that endpoint, not as the claim.

### 2.11 Time plan (EST, 2026-11-21) and drop order

| Window | Work |
|---|---|
| 09:00–09:40 | harness copy/adapt, configs, start both nodes, load and flush, read-backs |
| 09:40–09:50 | DIAG lifetime |
| 09:50–10:30 | T ×3 |
| 10:30–11:05 | C-ONE ×3 |
| 11:05–11:35 | I ×3 |
| 11:35–12:05 | C-small ×3 |
| 12:05–12:35 | budget search 4 GiB / Q 10, 8 GiB / Q 20 |
| 12:35–13:15 | slack: Q = 6 step or extra T runs; else E2 ×3 |
| 13:15–14:00 | no new runs; hprof analysis, §3–§4, write-backs, stop everything, clean `/mydata/s4/b22` data except logs/dumps needed |

**Drop order** (first dropped first): E2; 8 GiB search; DIAG's ONE and `small` parts; 4 GiB search; C-small to 1 run (C-ONE then
serves as the V2 control). Never dropped: T ×3, C-ONE ×3, I ×3.

### 2.12 Decision

- **`ready_for_stage2 = true`.** Constraints at shipped defaults (V6), heap 2 GiB with resolved direct (V7, standing rule), no
  container budget needed, node pc82 available and idle, harness mostly reusable from U4 and stage 4.

`sha256 of §1–§2 at freeze: e997b5a0a4c06b73667b16af61e6c779539a2b6d1e2f0bf78f6a824135f43231 (computed over the lines from `## 1. Candidate` up to, not including, this line)` · amendments after the freeze: A1 (2026-11-21, start order; §3.0).

## 3. Runs (stage 2)

### 3.0 Amendments after the freeze (dated, before the readings they affect)

- **A1 (2026-11-21 08:20 EST, before any lifetime): start order node 1, then node 2.** §2.5 step 4 says "start node 2 then
  node 1". With the frozen seeds (`127.0.0.1` only), node 2 is not a seed, and a non-seed node whose seed is down aborts its
  start in the shadow round (`Gossiper.java:2107-2110`, "Unable to gossip with any peers", CASSANDRA-13851; called from
  `StorageService.checkForEndpointCollision`, `StorageService.java:1192`, for every non-replacing start). The step cannot run as
  written without changing the seeds; the order is changed instead (victim first, peer second, then 2 UN). Memory effect: none on
  the claim (both nodes are up and `UN` before the sampler, the baseline reading and the load).

**Deviations from the design's execution (not amendments; none changes a constraint, budget or arm definition):**

- **Ve1 — batch driver replaced mid-run (08:43 EST).** The first driver (`harness/batch.sh`) would have run I and C-small at
  Q = 6 after the pre-declared Q step; §2.7 moves only T and C-ONE to Q = 6. It was stopped by PID while T6-2 ran (the lifetime
  itself was not touched) and `harness/batch2.sh` ran the rest in the design's order with the design's Q per arm (I and C-small at
  Q = 5).
- **Ve2 — side instrument added from T6-1 on (08:45 EST).** T-1/T-2's node logs showed `LARGE_MESSAGES … overloaded; dropping
  97.733MiB message` on both senders (see §3.4). `harness/netpoll.sh` (read-only `nodetool netstats` on both nodes every 10 s:
  outbound large messages completed/dropped) ran from T6-1 to the end; T-1 and T-2 have only the (rate-limited) log lines.
- **Ve3 — U read from the GC log.** The JMX column `old_postgc` (G1 Old Gen `CollectionUsage`) does not separate the arms: C-small,
  whose live set stayed ≤ 354 MiB, showed 1.84–1.87 GiB on it. Live heap U is therefore taken from the shipped GC log's heap
  after every `Pause Full` (G1 ran 25–147 full GCs per lifetime), plus the t60 class histogram and the OOM dumps.
- **Ve4 — histogram time.** The one `GC.class_histogram` was taken 60 s after the client started (40 s into the Q step), not at
  "load second 60" counted from the Q step.
- **Ve5 — E2 at Q = 6.** E2 (§2.9, optional) is "T at 2 GiB / 1,024 MiB direct"; after the pre-declared step T ran at Q = 6, so
  E2 ran at Q = 6.
- **Ve6 — extra repetitions.** E2 gave a mixed outcome (1/3 after E2-1..3), so the protocol's rule ("expand repetitions if timing
  produces mixed outcomes") was applied within the design's stopping budget (§2.8: ≤ 15 readings lifetimes + ≤ 5
  search/optional): E2-4, E2-5 (optional lifetimes 4–5) and T6-4 (readings lifetime 15). The budget is used up; nothing else ran.
- **Ve7 — predicted "no RFP log line".** Every lifetime logs 2–3 `WARN … has cached over 2000 rows` lines (the warn threshold,
  NoSpamLogger); no `ERROR` (fail-threshold) line appears outside arm I.

### 3.1 Environment

- `pc82` (node1.jason92-326665): x86_64, 40 cores, 125 GiB RAM, Ubuntu 22.04.2, kernel 5.15.0-203, cgroup v2, swap 8 GiB present
  (0 for every node: each JVM in its own `systemd-run --user --scope -p MemorySwapMax=0`, no `MemoryMax`); OpenJDK 11.0.33+9;
  nothing else running (checked 08:15 EST: no `CassandraDaemon`, load 0.00).
- Build: copy of `/mydata/s4/cassandra-base` at `/mydata/s4/b22/tree`, `build/apache-cassandra-5.0.9-SNAPSHOT.jar` sha256
  `570b5249d9b9a43f6809eb3da562737492192026f974b2edbd20e94bea90176e`, unmodified.
- Node 1 (victim/coordinator) `127.0.0.1`, JMX 7199; node 2 (peer) `127.0.0.2`, JMX 7299. yaml diff per node (`logs/*/yaml-n1.diff`):
  `cluster_name`, `listen_address`, `rpc_address`, the five directories, `auto_bootstrap: false`; node 2's `cassandra-env.sh` only
  `JMX_PORT`. All capacity settings shipped defaults (V6). Resolved victim flags (every lifetime, `logs/*/run.meta`):
  `-Xms2G -Xmx2G -XX:MaxDirectMemorySize=15872M` (E2: `1024M`), G1, `G1HeapRegionSize=16m`, `MaxGCPauseMillis=300`,
  `HeapDumpOnOutOfMemoryError`, `OnOutOfMemoryError=kill -9 %p`; peer `-Xmx16G`, direct 15872M. Baseline live heap after the
  warm-up GC 109–110 MiB in every lifetime.
- Data (`logs/LOAD/`): `b22.wide` and `b22.small`, one partition `k = 0`, 6,000 rows each, pad 20,480 / 2,048 B, CL ALL, 0 load
  errors, flushed: one SSTable per node (`wide` 123,668,779 B live, max partition 129,557,750 B; `small` 12,469,776 B), CL ALL
  `count(*)` = 6,000 for both, hints folders empty. Every lifetime started from a fresh copy of the two post-load templates.
- Harness: `harness/` (`ctl.sh`, `run-arm.sh`, `batch.sh` → `batch2.sh` → `batch3.sh`, `diag.sh`, `load-data.sh`, `client.sh`,
  `B22Load.java`, `B22Sampler.java`, `netpoll.sh`; adapted from U4's harness and stage 4's `RfpJmx.java`, `rfp.btm`,
  `stage4/rfp/RfpProbe.java`, copied unchanged; `hprofhist.py` extended with 20,480 B / 2,048 B / ≥ 90 MiB `byte[]` buckets).
  Client: Java driver 3.12.1, protocol v4, whitelist `127.0.0.1`, `FallthroughRetryPolicy`, fetch size left at the default (5,000;
  every completed page returned 5,000 rows).

### 3.2 DIAG lifetime (calibration, 08:22–08:26 EST; `logs/DIAG/probe.txt`)

| Query | RESP (measureDeep of each response payload at resolve) | PEAK populate (RFP held versions) | K bucket (JMX) | Client |
|---|---|---|---|---|
| `wide` QUORUM ×10 | 2 × 102,480,176 B (195.5 MiB) | **12,000 versions (6,000 per replica)**, 249,216,048 B = 237.7 MiB (20,768 B per version) | 14,237 | 5,000 rows, 2.2–2.9 s |
| `wide` ONE ×5 | 1 × 126,007,456 B (local `LocalDataResponse`, `DataOutputBuffer` slack 1.23×) | 5,000, 103,840,048 B = 99.0 MiB | 5,722 | 5,000 rows, 1.65–1.8 s |
| `small` QUORUM ×10 | 2 × 10,315,136 B | 12,000, 28,032,048 B = 26.7 MiB | 14,237 | 5,000 rows, 0.34–0.44 s |

Per-query U (D1 + D2): **QUORUM `wide` 433 MiB** (top of the predicted 394–433 MiB), ONE 219 MiB, `small` 46 MiB. Two findings
the design did not predict: (a) RFP held **6,000** versions per replica, not 5,000: it consumes the whole partition
(`ReplicaFilteringProtection.java:143`, `:387-396`) and short-read protection fetches the rest in page-sized chunks
(`ShortReadRowsProtection.java:165`), so held versions grow with the partition, not the page (K = 12,000 ≤ 32,000; not an
invalidity condition of §2.10); (b) at QUORUM both responses, **including node 1's own**, arrive through internode messaging
(`RangeCommandIterator.java:205-216`: only a single self replica runs locally), so node 1 also serializes its replica response into
a ≈ 120 MiB `DataOutputBuffer` (`LocalDataResponse.build`) before sending it to itself. RFP second-phase requests: 0 in every
lifetime.

### 3.3 Readings (2026-11-21 08:27–10:12 EST; steps `1:20,Q:160`; all from clean starts)

Live heap U = heap after `Pause Full` from node 1's GC log (median / max over the lifetime). Drops = outbound large messages
dropped for overload over the lifetime, node 1 (to itself) / node 2 (to node 1), from `netstats` (Ve2).

| Run | Table, CL, T, Q, heap/direct | Outcome | Pages done (/s) | Timeouts / Overloaded | Live heap U after full GC, med / max MiB | Full GCs, STW | Drops n1 / n2 | K max bucket |
|---|---|---|---|---|---|---|---|---|
| T-1 | wide QUORUM 32,000, Q 5, 2G/15872M | survived | 199 (1.24) | 204 / 0 | 678 / 1,281 | 103, 14 %/60 s | (log only) | 14,237 |
| T-2 | same | survived | 213 (1.33) | 209 / 0 | 750 / 1,556 | 99, 13 % | (log only) | 14,237 |
| T6-1 | wide QUORUM 32,000, **Q 6**, 2G/15872M | survived | 217 (1.36) | 222 / 0 | 884 / 1,452 | 147, 18 % | 193 / 184 | 14,237 |
| T6-2 | same | survived | 210 (1.31) | 188 / 0 | 871 / 1,513 | 117, 14 % | 156 / 154 | 14,237 |
| T6-3 | same | survived | 203 (1.27) | 217 / 0 | 869 / 1,690 | 146, 18 % | 187 / 175 | 14,237 |
| T6-4 | same | survived | 211 (1.32) | 241 / 0 | 885 / 1,348 | 139, 18 % | 217 / 200 | 14,237 |
| C16-1 | wide **ONE**, Q 6, 2G/15872M | survived | 468 (2.92) | 6 / 0 | 366 / 799 | 27, 7 % | 1 / 6 | 5,722 |
| C16-2 | same | survived | 484 (3.02) | 6 / 0 | 382 / 1,044 | 25, 7 % | 1 / 6 | 5,722 |
| C16-3 | same | survived | 514 (3.21) | 0 / 0 | 372 / 841 | 30, 7 % | 0 / 0 | 5,722 |
| I-1 | wide QUORUM, **T 2,000**, Q 5 | survived | 0 | 309 / 347 | 691 / 1,026 | 16, 15 % | 273 / 248 | 2,299 |
| I-2 | same | survived | 0 | 281 / 393 | 642 / 642 | 1, 7 % | 244 / 229 | 2,299 |
| I-3 | same | survived | 0 | 358 / 381 | 610 / 894 | 4, 13 % | 324 / 302 | 2,299 |
| CS-1 | **small** QUORUM 32,000, Q 5 | survived | 3,197 (19.98) | 0 / 0 | 223 / 354 | 98, 17 % | 1 / 0 | 14,237 |
| CS-2 | same | survived | 3,207 (20.04) | 0 / 0 | 226 / 351 | 95, 16 % | 1 / 0 | 14,237 |
| CS-3 | same | survived | 3,253 (20.33) | 0 / 0 | 222 / 337 | 95, 16 % | 1 / 0 | 14,237 |
| E2-1 | wide QUORUM 32,000, Q 6, **2G/1024M** | survived | 212 (1.32) | 278 / 0 | 867 / 1,586 | 146, 17 % | 253 / 240 | 14,237 |
| E2-2 | same | survived | 212 (1.32) | 230 / 0 | 884 / 1,569 | 142, 18 % | 204 / 187 | 14,237 |
| **E2-3** | same | **Java heap OOM at +136 s** (116 s into Q 6) | 130 (0.81) | 131 / 0 | 930 / 1,663 | 96, 16 % | 110 / 108 | 14,237 |
| **E2-4** | same | **Java heap OOM at +105 s** (85 s into Q 6) | 96 (0.73) | 110 / 0 | 913 / 1,569 | 62, 15 % | 90 / 102 | 14,237 |
| E2-5 | same | survived | 218 (1.36) | 230 / 0 | 869 / 1,473 | 118, 16 % | 202 / 197 | 14,237 |

Concurrency was reached in every arm (NTR active median 4–5, max = Q; client in-flight = Q). No lifetime met the service-loss
criterion (max STW 18 % per 60 s). No cgroup `oom_kill` (scope `memory.events` all 0). The peer never failed. The t60 class
histograms (live `byte[]`): T 418–598 MiB, C-ONE 29–453 MiB, I 523–747 MiB, C-small 136 MiB, E2-3 560 MiB.

### 3.4 What limited the test arm: internode send-queue drops, then range timeouts

In every QUORUM `wide` lifetime, about half the queries ended in `ReadTimeoutException` at `range_request_timeout` (10 s), with
"0 or 1 replica responded". Both senders log `/127.0.0.x:7000->/127.0.0.1:7000-LARGE_MESSAGES-… overloaded; dropping 97.733MiB
message (queue: 97.733MiB local, 93.733MiB endpoint, 93.733MiB global)` (`OutboundConnection.java:456-467`; T-1 excerpts in
`logs/T-1/run-arm.out` and the node logs). `netstats` counts 150–325 dropped large messages per sender per lifetime against
250–500 completed. Mechanism: a 98 MiB response does not fit next to another one in the outbound queue's byte reserve
(`internode_application_send_queue_capacity` 4 MiB per connection + `…_reserve_endpoint_capacity` 128 MiB, both defaults), so
while one is being flushed a second is dropped, and the query waits for the timeout and then releases what it held. Because node 1's
own replica response also goes through messaging at QUORUM (§3.2 b), both D2 responses of every query pass this reserve. The
effect is a byte-based cap on how many 98 MiB responses are in flight per sender, i.e. on how many queries can hold their responses
and versions at once: the test arm completed 1.24–1.36 pages/s against C-ONE's 2.92–3.21 (local path, no messaging, ≤ 6 drops). The
protection map (§2.2) listed only the receive-side reserve (D6) and ledgered it; the send-side reserve was not in it.

### 3.5 The two OOMs (E2-3, E2-4; V5 evidence)

- Initiating error: `java.lang.OutOfMemoryError: Java heap space` on node 1, then heap dump and `kill -9` (`logs/E2-3/oom-excerpt.txt`,
  `logs/E2-4/oom-excerpt.txt`; the JVM died before `system.log` got an ERROR line). The throwing thread's stack in both dumps
  (`logs/E2-*/hprofstacks.txt`): `DataOutputBuffer.expandToFit` ← `Cell$Serializer.serialize` ← `UnfilteredPartitionIterators$Serializer.serialize`
  ← `ReadResponse$LocalDataResponse.build/<init>` ← `ReadResponse.createDataResponse`: node 1 serializing its own replica's
  page (D2, local side) — one of the sites §2.8 predicted.
- Dumps (`logs/E2-*/hprofhist.txt`; HotSpot dumps on OOM without a preceding GC): E2-3 1,529 MiB shallow, of which **`byte[]` ≥ 90 MiB:
  9 arrays, 924.5 MiB** (7 × 97.7 MiB response buffers, 6 `RemoteDataResponse`; 2 × 120.2 MiB `DataOutputBuffer`s) and **20,480 B
  pad `byte[]`: 18,617 arrays, 363.6 MiB** (held versions + their `ResultSet` alias, 3.7 pages' worth), 2 RFP instances with 4
  `PartitionBuilder`s → D1 + D2 = 1,288 MiB = **84 %** of the dump. E2-4: 1,377 MiB, 7 × 97.7 MiB (684 MiB), 19,087 pad arrays
  (373 MiB), 3 RFPs / 6 builders → 77 %. K never exceeded 12,000 (bucket 14,237); no fail-threshold line.
- Predictions (§2.8) vs these dumps: "≥ 20,000 pad `byte[]`" → 18,617 / 19,087 (just below); "≥ 4 `byte[]` ≥ 90 MiB" → 9 / 7; "D1 + D2 ≥
  60 %" → 84 % / 77 %.

### 3.6 Logs

Repo (small excerpts): `logs/<run>/` for LOAD, DIAG and the 20 lifetimes (`run.meta`, `outcome`, `steps.txt`, `gcwin.txt`,
`client.csv`, `samples.csv`, `readings.csv`, `rfpk.txt`, `netpoll.csv`, `histo-t60-top.txt`, `rfp-excerpt.txt`, yaml/env diffs;
E2-3/E2-4 also `oom-excerpt.txt`, `hprofhist.txt`, `hprofstacks.txt`), `logs/batch*.out`, `logs/batch.outcomes`, `logs/netpoll.csv`.
Node (full logs): `pc82:/mydata/s4/b22/runs/<run>/` (node 1 and node 2 `system.log`, `debug.log`, GC logs, stdout, full histograms,
`hprofstacks-all.txt`); one representative dump kept, `pc82:/mydata/s4/b22/runs/E2-3/n1/cassandra-1795272732-pid487367.hprof`
(1.6 GB); E2-4's dump was deleted after reading.

## 4. Conclusion (stage 2)

**Verdict: `retry`.** Protocol status (detail): **`candidate`**, from the bypass direction (accounting omission × multiplicity):
the claimed endpoint (Java heap OOM with RFP held versions + raw responses dominant, K ≤ 32,000) was reached **2/5 at 2 GiB heap /
1,024 MiB direct (E2)** and **0/6 at the frozen budget (2 GiB / 15,872 MiB; Q = 5 ×2, Q = 6 ×4)**; V1 (≥ 3 runs) is not met at
either budget, and the matched controls ran only at the frozen budget.

**Reason.** The per-query arithmetic held: the DIAG probe measured 433 MiB per QUORUM query on the coordinator (12,000 held versions
= 237.7 MiB + 2 × 97.7 MiB responses) while RFP charged K = 12,000 of its 32,000 count (bucket 14,237, no fail line), and 6 of these
were in flight (NTR active max 6). But the memory never stacked to 6 × 433 MiB: about half of the QUORUM queries were dropped by a
protection the design did not map, the internode **outbound send-queue reserve** (4 MiB per connection + 128 MiB per endpoint,
defaults). It admits one 98 MiB response per sender and drops the next (150–325 drops per sender per lifetime), so those queries
time out at 10 s (188–278 timeouts per lifetime) and release their memory. At QUORUM node 1 sends its own replica response through
messaging too, so both responses of every query pass the reserve. The live heap after full GC reached a median of 680–930 MiB and
a maximum of 1,281–1,690 MiB of 2,048 in the test arm, against 799–1,044 for C-ONE (Q 6), 337–354 for C-small and 642–1,026 for
I. Two of the five E2 lifetimes still ran out of heap (in `LocalDataResponse.build`, D1 + D2 = 77–84 % of the dump), so the
endpoint is reachable but rare at this size and Q. The §2.10 survival branch (old-gen < 1.6 GiB, then measure U) does not apply,
since live heap peaked above 1.6 GiB. A `false positive` is ruled out because the ceiling is not bounded (Σ contracts unbounded,
one OOM site observed), and the named higher multiplicity (the triage's 4–8 and the 128-thread bound) and the budget search were
not reached under the frozen rules.

**V1–V7 at the frozen condition (T, 2 GiB / 15,872 MiB, Q = 6):**

| | Result | Evidence |
|---|---|---|
| V1 repetition | **not met**: 0/4 at Q 6 (0/2 at Q 5); 2/5 at the E2 budget | §3.3 |
| V2 matched control | C-small 0/3 (same K, 10× smaller rows), C-ONE 0/3 at Q 6 (no internode path) | §3.3 |
| V3 U independent of K | met: DIAG `measureDeep` per query, GC-log live heap, t60 histograms, two dumps vs K buckets | §3.2–§3.5 |
| V4 intervention | I (T = 2,000) 0/3 OOM, 0 pages served (347–393 Overloaded per lifetime): the count binds, but stops all useful work; not informative while T itself does not OOM | §3.3 |
| V5 initiating failure | for E2-3/E2-4: heap OOM, thread stack in `LocalDataResponse.build`, dump with D1 + D2 dominant | §3.5 |
| V6 defaults | met (all capacity constraints shipped; only T in I changed via JMX) | §3.1 |
| V7 budget | met for both budgets (heap 2 GiB, direct 15,872 / 1,024 MiB ≥ 512 MiB); budget search not run (needs ≥ 2 T OOMs) | §2.9 |

**Classification note.** The accounting omission itself is shown by the calibration: K = 12,000 versions for 433 MiB per query
(`wide`) and 46 MiB (`small`) at the same K, a 9.4× byte spread at equal charge. The raw responses are not charged at all. No byte
contract exists, so this is recorded as an observation and not as `verified-gap`: no overshoot endpoint is defined, and the OOM
endpoint was not met by V1.

**What a better design should change (retry):**

1. **Use the partition, not the page, to size D1.** RFP consumes the whole partition (`ReplicaFilteringProtection.java:143`,
   `:387-396`) and short-read protection fetches the rest in page-sized chunks (`ShortReadRowsProtection.java:165`). So one query
   holds min(rows per replica × RF, 32,000) versions regardless of the page (DIAG: 6,000 per replica from a 5,000-row page). A
   partition of ≈ 15,500 rows per replica (K ≈ 31,000 < 32,000) holds ≈ 0.6 GiB per query at 20 KiB rows, or ≈ 1.4–1.9 GiB
   at 48–64 KiB rows. That needs 1–3 concurrent queries for 2 GiB, not 6, and puts the claim on the count/byte gap directly.
2. **Keep every internode message well under the send-queue reserve** so the drop/timeout path does not cap multiplicity: a
   client fetch size giving messages ≤ 30–40 MiB (e.g. fetch 1,000–2,000 at 20 KiB rows, 500 at 64 KiB). The SRP chunks follow the
   page size. Add `netstats` dropped large messages and timeouts as frozen instruments, and map the send-side reserve
   (`internode_application_send_queue_*`) in the protection map. Check in a DIAG that one query finishes inside
   `native_transport_timeout` (12 s) and `range_request_timeout` (10 s), since it now makes many SRP round trips.
3. **Run the controls at the same budget as any condition that is claimed.** E2's 1,024 MiB direct limit should not matter to the
   heap, but its 2/5 cannot be pooled with T's 0/6 under the protocol. Use one budget, with the GC-log live heap as U (the JMX
   `old_postgc` column does not discriminate).
4. Keep C-small (same K, small rows) and C-ONE, and use an intervention that keeps useful work (e.g. T at about the
   per-query version count, or a smaller fetch size) so that V4 is not "0 pages served".
