# B29 (OC-470 + OC-480) — cached_rows_fail_threshold: an unresolved static-column predicate makes replica-filtering protection read the stale replica's whole partition, uncounted  <!-- file: cassandra/cases/cached_rows_fail_threshold--rfp-static-fetch-whole-partition/cached_rows_fail_threshold--rfp-static-fetch-whole-partition.md -->

| Field | Value |
|---|---|
| Case ID | `B29` (B = bypass case; README "ID prefixes"): the design is a bypass, accounting omission (§2.1) |
| From | `OC-470` and `OC-480` of the phase 1 OOM candidate list (same holder, two agents; both rows `picked: B29 (2026-11-24)`) |
| Phase-1 case file | [`cached_rows_fail_threshold-queryProtectedPartitions-i--autonomous`](../../../../capacity-enforcement-exp/cassandra/stage3-ai-deep-read/cases/cached_rows_fail_threshold-queryProtectedPartitions-i--autonomous.md) · stage-4 result [`results/…`](../../../../capacity-enforcement-exp/cassandra/stage4-runtime-verification/results/cached_rows_fail_threshold-queryProtectedPartitions-i--autonomous.md) |
| System / pinned source | Cassandra 5.0.9 (`systems/cassandra/source/`); built copy `pc72:/mydata/s4/cassandra-base` (`build/apache-cassandra-5.0.9-SNAPSHOT.jar`) |
| Stage 1 (design) | phase-2 OOM agent, stage 1 (Claude Opus 5.5), 2026-11-24 05:40–06:30 EST, owner-approved batch of 2026-11-24; nothing run (pc72, pc82, pc91, pc75, pc99 checked read-only) |
| Stage 2 (verify) | phase-2 OOM agent, stage 2 (Claude Opus 5.5, a fresh session), 2026-11-24 20:11–21:45 EST on **pc72** (node lock 20:11–21:36); earlier attempts the same day on pc99 (stopped by the owner ≈ 16:25) and an API usage limit (≈ 18:03) are recorded in §3.4 |
| Verdict | **true positive** — `verified-OOM · deployment` (bypass · accounting omission × multiplicity; fault F1 external, in setup only) |

## Summary

- **Conclusion (stage 2, pc72): true positive, `verified-OOM · deployment`.** On a 2-instance RF 2 layout with every capacity
  constraint at its default and a 2 GiB heap, 8 concurrent QUORUM `SELECT * … WHERE k = ? AND s = 'x' ALLOW FILTERING` queries
  coordinated by the stale replica OOM the coordinator **3/3** (Java heap space, 2.9–3.6 s into the first wave, no query completed),
  while RFP's counter charges **2** per query and logs nothing. Replicas agree: 0/3; the same fetch at Q = 2: 0/3; the fetch
  reading named rows only (diagnostic build): 0/3 with every query answered. Budget search: OOM at 4 GiB (Q = 16), 8 GiB (Q = 32)
  and **12 GiB (Q = 48)**; 15,872 MiB at Q = 64 survives because the 5 s read deadline cancels 35 of 96 queries (boundary).
- **Root cause (verified):** for an unresolved static row, RFP's completion fetch reads the stale replica's whole partition
  (`DataLimits.NONE`, no row filter, no paging) and serializes it into one heap `DataOutputBuffer` per query on the coordinator
  (262 MB payload, 324 MiB backing array). These rows never reach `incrementCachedRows`, no byte threshold applies to the command
  and there is no aggregate bound, so the only limits are the 32 READ permits and the 5 s read deadline.
- **Hypothesis (stage 1).** A filtering read at CL above ONE goes through replica-filtering protection (RFP). When the
  query has a predicate on a **static column** and one replica is **silent** about the static row (it missed the update),
  RFP marks the static row unresolved and, in its second phase, reads the silent replica's **entire partition** with no row
  limit, no row filter and no paging (`ReplicaFilteringProtection.java:623-632`). The fetched rows never pass through
  `incrementCachedRows`, so `cached_rows_fail_threshold` (32,000 rows, the control whose yaml text says it limits "the damage
  severely out-of-date replicas can cause") charges **2** for the query. When the silent replica is the coordinator itself,
  the whole partition is serialized into one heap `DataOutputBuffer` with no size bound at all (not the 128 MiB internode
  cap, and the byte read-size thresholds never track this command). A stale replica that missed a partition delete keeps
  every old row, so one query on a 250 MiB stale partition holds ≈ 288 MiB on the coordinator while returning one CQL row;
  8 such queries are predicted to exhaust a 2 GiB heap.
- **Root cause (claimed):** the RFP control counts rows it caches, but its completion fetch for an unresolved static row is
  unlimited and uncounted; the only bound on it is the 5 s read timeout.

## 1. Candidate

**Candidate rows (quoted from `phase1-oom-candidates.md`, lines 479 and 489):**

> | OC-470 | 2026-11-18 | `cached_rows_fail_threshold-queryProtectedPartitions-i--autonomous` | autonomous | Holder: the second-phase completion fetch (fetchFromSource). When a static-column predicate leaves the static row unresolved, it reads the entire partition from the silent replica with DataLimits.NONE and the command's full clustering filter. [details](runs/wave3.md#oc-470) | — | picked: B29 (2026-11-24) |

> | OC-480 | 2026-11-18 | `cached_rows_fail_threshold-queryProtectedPartitions-i--autonomous` | guided | Holder: the second-phase protection fetch, fetchFromSource. When a static-column predicate is unresolved, it reads the entire partition from the silent replica with DataLimits.NONE and RowFilter.none(), outside the cached-rows count. [details](runs/wave3.md#oc-480) | CP-10, CP-12 | picked: B29 (2026-11-24) |

**Details (quoted from `runs/wave3.md`):**

> **OC-470.** Holder: the second-phase completion fetch (fetchFromSource). When a static-column predicate leaves the static row
> unresolved, it reads the entire partition from the silent replica with DataLimits.NONE and the command's full clustering
> filter. handler.awaitResults() then holds that whole response as one materialized payload on the coordinator. The rows fetched
> are never passed to incrementCachedRows, so cached_rows_fail_threshold does not see them. A remote response is cut off only by
> internode_max_message_size (128 MiB at defaults), and the replica has already built it in a heap DataOutputBuffer. A local source
> has no size limit at all. Rough size: one whole partition per protected partition per query (partition size is only warned
> about), e.g. 100 MiB to 1 GiB for a wide partition, about twice that while the buffer grows, multiplied by concurrent queries.
> **Where:** service/reads/ReplicaFilteringProtection.java:162-184, 604-650 (623 unresolvedStatic, 630 DataLimits.NONE); db/ReadResponse.java:193-204

> **OC-480.** Holder: the second-phase protection fetch, fetchFromSource. When a static-column predicate is unresolved, it reads
> the entire partition from the silent replica with DataLimits.NONE and RowFilter.none(), outside the cached-rows count. Why
> nothing stops it: there is no row limit and no paging. The response is materialized whole on the coordinator heap, and only
> internode_max_message_size (about 128 MiB at defaults) bounds it. Size: up to about 128 MiB per fetch for a wide partition,
> times concurrent filtering queries and protected partitions.
> **Where:** systems/cassandra/source/src/java/org/apache/cassandra/service/reads/ReplicaFilteringProtection.java:603-631

The two rows name the same holder; this design covers both. The triage of 2026-11-20 (rank 5, quoted in B22 §1) grouped them
with OC-479 and noted "OC-470/480: the static-column completion fetch reads a whole partition with no limit, up to 128 MiB". B22
([`…rfp-counts-versions-not-bytes`](../cached_rows_fail_threshold--rfp-counts-versions-not-bytes/cached_rows_fail_threshold--rfp-counts-versions-not-bytes.md),
retry) left them out explicitly ("needs a static-column predicate and divergent replicas; a different holder … not closed by this
case").

**Phase-1 constraint and stage-4 result.** The phase-1 case traced `replica_filtering_protection.cached_rows_fail_threshold`
(default 32,000; warn 2,000) to `incrementCachedRows()` (`ReplicaFilteringProtection.java:319-345`), one count per row version
per replica, released per partition (`:564`). Its A4 lists "second-phase fetches (`fetchFromSource`, `:604-650`,
`DataLimits.NONE`) can return unbounded rows" among the consumers outside the cap. Stage 4 (2026-10-27, outcome class **true
positive**, i.e. the count caps what it counts) ran range filtering queries with **no** static predicate and agreeing replicas;
`ReplicaFilteringProtectionRequests` (second-phase fetches) was not exercised. The static-predicate path has never been run.

**Related OOM-exp cases.** B22 (retry): the same control, first-phase holder (held versions + raw responses), blocked by the
internode send-queue reserve at QUORUM. This design avoids that path on purpose: the large allocation is a **local** fetch on the
coordinator, and both first-phase responses are a few hundred bytes (§2.4). U4 (true positive): a default page of wide rows held
on a single node, no RFP. B20 (true positive): another "one partition read whole as one unit" holder (2i build).

**JIRA prior art (read only; nothing posted; REST `issues.apache.org`, 2026-11-24 05:45–05:50 EST).**

| JQL (`project = CASSANDRA AND …`) | Hits |
|---|---|
| `text ~ "replica filtering protection" AND text ~ "static"` | 42 |
| `text ~ "fetchFromSource"` | 2 (CASSANDRA-15907, 20323) |
| `text ~ "unresolvedStatic"` | 2 (CASSANDRA-20243, 20323) |
| `text ~ "replica filtering protection" AND (text ~ "OutOfMemoryError" OR text ~ "OOM" OR text ~ "heap")` | 19, none reporting coordinator memory from the completion fetch |
| `text ~ "ReplicaFilteringProtection" AND text ~ "entire partition"` | 5 (8272, 15907, 19018, 20243, 20323) |

Closest issues (read in full): **CASSANDRA-20243** "Replica filtering protection over-fetches partition data when no static column
predicates are present" (Fixed 5.0.4, in 5.0.9) narrowed the whole-partition fetch to the case with a static predicate — the case
under test — for correctness; **CASSANDRA-20323** "Multi-node filtering query on static column appears to miss partition delete"
(Fixed 5.0.4) is a correctness fix for exactly this data shape (static predicate + a replica that missed a partition delete), run
with `read_repair = 'NONE'` in its tests; **CASSANDRA-15907** (Fixed 3.0.22/3.11.8/4.0) added the two count thresholds;
**CASSANDRA-16896** (Fixed 4.1) added byte-based local/coordinator read thresholds, shipped off, and (checked in the source, §2.2)
not applied to the RFP fetch command even when enabled. CASSANDRA-19007 (open) and 19018 are RFP correctness work. The pinned code
says the risk out loud: "we have no way of knowing how many stale rows we might read on a silent replica before finding a live one"
(`ReplicaFilteringProtection.java:618-622`). `stage5-oom-clue-find/jira-oom-survey.csv` (605 lines): no row on RFP memory.
**Verdict: `new`** for the memory exposure (no issue reports it; the whole-partition fetch is a deliberate correctness choice); not a
known-fixed bug, so not a positive control.

## 2. Design solution (stage 1; frozen)

### 2.1 Mechanism and direction

A single-partition filtering read `SELECT * FROM b29.t WHERE k = ? AND s = 'x' ALLOW FILTERING` (`s` static) at **CL QUORUM** on
an RF 2 keyspace, coordinated by the **stale replica** (node 1). The replicas disagree: node 2 (up to date) holds a partition
deletion and a newer static `s = 'x'`; node 1 missed both and still holds the old static `s = 'a'` and all the old rows.

1. Each replica filters locally. A static expression is checked at partition level, and a partition whose static row does not
   match is dropped whole (`db/filter/RowFilter.java:241-251`): node 1 returns nothing, node 2 returns the partition deletion and
   the static row. The data/digest responses differ, so the coordinator reads full data from both and resolves them in
   `DataResolver` (`AbstractReadExecutor.java:435` → `AbstractReadRepair.java:142`; self read local, `:97-99`). The row filter
   is non-empty, so the RFP path is taken (`DataResolver.java:122`, `:132-144`, RFP built with the yaml thresholds `:232-258`).
2. First phase: the merge calls the RFP listener for the static row (`UnfilteredRowIterators.java:484-504`; the absent replica is
   an empty iterator, `UnfilteredPartitionIterators.java:155-176`). Each version is counted (`addRow` → `incrementCachedRows`,
   `ReplicaFilteringProtection.java:477-492`, `:319-345`): **K = 2**. Node 1's static version is empty, so node 1 is silent
   (`:232`) and `addToFetch` marks `unresolvedStatic = true` because the filter has a static expression (`:500-513`, `:510`).
3. Second phase (`DataResolver.java:267`, `queryProtectedPartitions` → `protectedPartition`, `:583-602`): node 1's builder has
   `toFetch != null`, so `fetchFromSource` (`:604-651`) builds a `SinglePartitionReadCommand` with the command's **full clustering
   filter** (`:623-624`), `RowFilter.none()` and **`DataLimits.NONE`** (`:626-632`) and runs it on node 1. The source is self, so it
   runs as `StorageProxy.LocalReadRunnable` via `Stage.READ.maybeExecuteImmediately` (`:170-172`; `SEPExecutor.java:218-230`: on the
   calling Native-Transport-Requests thread when a READ permit is free). `LocalReadRunnable` serializes the whole partition into one
   heap `DataOutputBuffer` (`StorageProxy.java:2197-2211` → `ReadCommand.createResponse` → `ReadResponse.java:182-209`), starting
   at 128 B and doubling up to 64 MiB, then growing ×1.5 (`DataOutputBuffer.java:57`, `:158-171`); the response keeps a view of the
   backing array (`:227-245`). `handler.awaitResults()` (`:182`) then holds it until the protected partition is consumed and the
   query returns. None of these rows passes `addRow`.
4. The merge applies node 2's partition deletion: every fetched row is shadowed, the client receives **one** CQL row (the static
   row), and blocking read repair writes the deletion and the new static to node 1 (`TableParams.java:374`, `read_repair`
   default `BLOCKING`). After that query the partition is consistent, so **each diverged partition triggers the fetch once**;
   the workload gives every query its own diverged partition (§2.5).

What bounds the fetch: no row or byte limit. The local path does not go through `internode_max_message_size`. The byte
read-size thresholds are off by default (`read_thresholds_enabled: false`, `Config.java:526`), and even when on they apply only
to commands marked `trackWarnings()` (`ReadCommand.java:656-668`); the fetch command is created fresh in `fetchFromSource` and
never marked. The only bound is time: `LocalReadRunnable` sets the monitoring deadline to the client request's start +
`read_request_timeout` (5 s, `StorageProxy.java:2204-2205`, `Config.java:145`) and `QueryCancellationChecker` aborts the
iteration past it (`ReadCommand.java:743-790`). Concurrency: builds ≤ `concurrent_reads` 32 (READ permits), retained responses ≤
`native_transport_max_threads` 128 (`Config.java:179`, `:283`); no aggregate byte control.

**Direction: bypass · accounting omission** (bypass technique note, "Accounting mismatch"; B16/B22 shape). The RFP control claims
to "limit the number of rows from all replicas individual index and filtering queries can materialize on-heap" and to "limit the
damage severely out-of-date replicas can cause" (`conf/cassandra.yaml:1822-1835`). Here it charges K = 2 while the out-of-date
replica's rows materialized for the same query are U ≈ 288 MiB (§2.4): U > C in bytes with K ≤ C, an accounting omission. The
endpoint needs about 8 concurrent queries, so it is recorded as a bypass excess **stacked by multiplicity** (no aggregate control
exists), as B22. If stage 2 finds that the fetch rows do pass a counter, or that the endpoint is reached without the fetch, it
reclassifies by §2.10.

### 2.2 Protection map (fixed before any reading; victim = coordinator node 1)

| Domain | Allocation and owner (release) | Local contract (K, limit, at limit) | Scope / multiplicity | Aggregate coverage | Claimed? |
|---|---|---|---|---|---|
| **D1 RFP completion fetch, local** | one heap `byte[]` behind `ReadResponse$LocalDataResponse` (`DataOutputBuffer`, ×2 up to 64 MiB then ×1.5; old + new array live during each growth); built by `LocalReadRunnable` on the NTR thread or a ReadStage thread; held by the fetch's `ReadCallback`/`DataResolver` until the protected partition is consumed and the query returns | **none**: not counted by RFP (`fetchFromSource` rows bypass `addRow`); `DataLimits.NONE`, `RowFilter.none()`; no internode cap (local); read-size thresholds off and not applied to this command (untracked); only the 5 s read deadline (`QueryCancellationChecker`) | per query (one per silent replica per protected partition); builds ≤ 32 (READ permits), retained ≤ 128 (NTR threads) | none | **yes** (accounting omission) |
| D2 RFP cached versions (the control) | `PartitionBuilder.staticRow`/`contents` (`RFP.java:457-458`) | K = `currentRowsCached`; T = `cached_rows_fail_threshold` 32,000 (warn 2,000); `OverloadedException` at T+1 | per query | none | no — the control; K = 2 per query here |
| D3 first-phase replica responses | node 2: partition deletion + static row (≈ 100 B); node 1: empty | none | per query × 2 | — | no (ledgered, tiny) |
| D4 RFP fetch from a **remote** silent replica | remote `byte[]` in `RemoteDataResponse` | `internode_max_message_size` 128 MiB; outbound send-queue reserve 4 MiB + 128 MiB per endpoint (B22) | per query | reserve | not exercised (the coordinator is the stale replica); recorded as the bounded variant |
| D5 read-repair mutation | partition deletion + static row to node 1 | `max_mutation_size` 16 MiB | per query | — | ledgered (≈ 100 B) |
| D6 memtables | `memtable_heap_space` = ¼ heap = 512 MiB at 2 GiB | flush at cleanup threshold | per node | yes | baseline (only read-repair writes during readings) |
| D7 chunk cache | `file_cache_size` min(512 MiB, ¼ heap) = 512 MiB, **direct** | pool cap | per node | yes | ledgered (direct) |
| D8 client response | one static row per query | — | per query | — | ledgered (tiny) |
| D9 baseline | schema, key cache min(5 % heap, 100 MiB), Netty, metrics | — | per node | — | baseline (measured at warm-up) |

### 2.3 Configuration and budget audit

- **Node:** `pc72` (node2.jason92-326665; x86_64, 40 cores, 125 GiB RAM, `/mydata` 707 GiB free; Ubuntu 22.04, kernel 5.15,
  cgroup v2 with the memory controller, 8 GiB swap present, unused). Read-only check 2026-11-24 05:55 EST: no `CassandraDaemon`,
  load 0.00, `/mydata/s4/` holds `cassandra-base` (jar `build/apache-cassandra-5.0.9-SNAPSHOT.jar`), `3b-B21`, `3b-R22` and a
  `NODE-LOCK/owner` file `phase1-hadoop o7 Mon Nov 23 11:58:47 PM MST 2026` (a lock from the previous night with nothing
  running; stage 2 checks it is stale before starting and follows the node-lock convention in force). OpenJDK 11.0.33,
  `jvm11-server.options` G1 with `G1HeapRegionSize=16m`, `lib/` has `cassandra-driver-core-3.12.1-shaded.jar`. Run folder
  `/mydata/s4/b29/` (not created). Any other free x86 node of the batch (pc82, pc91, pc75, pc99, same class) is equivalent if
  the coordinator assigns pc72 elsewhere; the aarch64 ms-nodes are not used (8 cores: the 5 s deadline, §2.1, is tighter there).
- **Topology (environment deviation, recorded; B22's layout):** two Cassandra instances on one host, RF 2. Node 1
  (**victim/coordinator, the stale replica**) `127.0.0.1`, JMX 7199; node 2 (**up-to-date replica**) `127.0.0.2`, JMX 7299; own
  `CASSANDRA_CONF`, data, commitlog, hints, saved_caches, logs under `/mydata/s4/b29/n1|n2/`; seeds `127.0.0.1`;
  `auto_bootstrap: false`; `cluster_name: b29`. **Start order node 1, then node 2** (B22 amendment A1: a non-seed cannot start
  while the seed is down).
- **Realistic fault F1 (external, recorded):** node 1 was down while the application deleted and re-initialized partitions, for
  longer than `max_hint_window` (3 h default, `Config.java:115`), so no hints were kept, and repair has not run since. Simulated in
  setup only: node 1 stopped, the writes go to node 2 at CL ONE, then `nodetool truncatehints` on node 2 (what node 2 holds after
  the window has passed). No fault is active during the readings.
- **Client choice (recorded):** the driver whitelists node 1, so the stale replica coordinates. With token-aware routing on RF 2,
  a stale replica coordinates about half of the queries for its keys; this is not a configuration change.
- **Capacity constraints (V6):** all at shipped defaults, resolved at the victim heap: `cached_rows_fail_threshold` 32,000,
  `cached_rows_warn_threshold` 2,000; `read_thresholds_enabled` false (so `local_read_size_*`, `coordinator_read_size_*` off);
  `internode_max_message_size` 128 MiB; `concurrent_reads` 32; `native_transport_max_threads` 128; `memtable_heap_space` 512 MiB;
  `file_cache_size` 512 MiB; guardrails (`partition_size_*`, `page_size_*`, …) off; `max_mutation_size` 16 MiB;
  `read_request_timeout` 5 s, `range_request_timeout` 10 s, `native_transport_timeout` 12 s (none raised). Table options default
  (`read_repair` BLOCKING, LZ4, STCS, `gc_grace_seconds` 864000). Constraints change only in the optional arm O-thr (§2.7), which
  is not a test arm. The intervention arm I changes code (diagnostic build), not a constraint.
- **Budgets (V7):** victim heap **2 GiB** (`MAX_HEAP_SIZE=2G`, `HEAP_NEWSIZE` unset; G1 from the shipped options), direct memory
  **as `cassandra-env.sh` resolves on pc72 with a hand-set heap** (expected `MaxDirectMemorySize=15872M`, as B22 found on the same
  node class; record the actual value from `ps` in every lifetime). Claimed node: a large node running a 2 GiB heap (common
  practice; B22, U4, C2 used the same pair). Both ≥ 512 MiB → V7 met by the standing rule. Budget search upward (§2.9). No
  container budget: the victim runs in `systemd-run --user --scope -p MemorySwapMax=0` (no `MemoryMax`). **Peer heap 4 GiB**
  (its work per query is a few hundred bytes; it is not a budget of the claim).
- **Other settings:** shipped `jvm-server.options` (`HeapDumpOnOutOfMemoryError`, dump path `/mydata/s4/b29/runs/<lifetime>/`,
  `OnOutOfMemoryError=kill -9 %p` as B22 used), shipped GC log. Byteman only in the DIAG lifetime.

### 2.4 Ceiling arithmetic

Table `b29.t (k int, c int, s text STATIC, pad blob, PRIMARY KEY (k, c))`. A stale partition on node 1: 4,000 rows × 65,536 B
random pad. Intra-node serialized row ≈ 65,550 B → **P = 262 MB = 250 MiB** per partition. `DataOutputBuffer` capacities:
… 64 → 128 → 192 → **288 MiB** (×1.5 above 64 MiB). Per fetch: retained array **288 MiB** (slack 1.15); during the last growth
the 192 MiB and 288 MiB arrays are both live (**480 MiB** transient). Each array is humongous in G1 (18 × 16 MiB regions).

| Per query (victim heap) | T (stale coordinator) | C-agree (replicas agree) | I-names (patched fetch) |
|---|---|---|---|
| K (versions charged) | 2 (static row × 2 replicas) | 2 | 2 |
| D3 first-phase responses | ≈ 100 B + 0 | ≈ 100 B × 2 | ≈ 100 B + 0 |
| **D1 completion fetch** | **288 MiB retained, 480 MiB peak in growth** | 0 (no silent replica, no fetch) | ≈ 0 (static row / nothing) |
| D5 read-repair mutation | ≈ 100 B | 0 | ≈ 100 B |
| Rows returned to the client | 1 | 1 | 1 |

Contracts: D1 has none (bounded only by time × read rate); D2's contract is 32,000 rows and is charged 2. Σ contracts is
unbounded, so convergence feasibility is not the limiter. Budget: 2,048 MiB − baseline (B22 measured 109–110 MiB on this build;
take 110–150) → ≈ 1,900–1,940 MiB for queries.

- **T, Q = 8:** 8 × 288 = **2,304 MiB** with all retained (119–121 % of the headroom), up to 3,840 MiB if all are growing; with
  only 6 of 8 retained and 2 growing: 6 × 288 + 2 × 480 = 2,688 MiB. → **Java heap OOM predicted** in the first wave(s).
- **C-Q2 (dose control, test data, Q = 2):** ≤ 2 × 480 = 960 MiB (≤ 50 % of the headroom) → survives.
- **C-agree, Q = 8:** ≈ baseline → survives. **I-names, Q = 8:** ≈ baseline → survives, with the same client result.
- **Time bound check:** one fetch reads and serializes 250 MiB from one local SSTable (page cache warm after the first lifetime,
  chunk cache direct). Expected 0.5–1.5 s at Q = 1 (B22 DIAG: a 120 MiB local `LocalDataResponse` plus client transfer of 100 MB
  in 1.65–1.8 s), under the 5 s deadline; the DIAG lifetime measures it (§2.10).

### 2.5 Workload and environment

1. **Harness** under `harness/` in this folder, adapted from B22's (`../cached_rows_fail_threshold--rfp-counts-versions-not-bytes/harness/`:
   `ctl.sh`, `run-arm.sh`, `B22Load.java` → `B29Load.java`, `B22Sampler.java`, `gcwin.py`, `hprofhist.py`, `hprofstacks.py`,
   `RfpJmx.java`, `rfp.btm`), with attribution. Changes: the schema and load below, the query, the partition hand-out, CL QUORUM.
   Build copy: `/mydata/s4/b29/tree` (copy of `cassandra-base`, unmodified; record the jar sha256). Patched copy for arm I:
   `/mydata/s4/b29/tree-I` with `harness/I-names.diff` (§2.7) applied and the jar rebuilt (`ant jar`); record both jar sha256s.
2. **Schema (once, both nodes up):** `CREATE KEYSPACE b29 WITH replication = {'class': 'SimpleStrategy', 'replication_factor': 2}`;
   `CREATE TABLE b29.t (k int, c int, s text STATIC, pad blob, PRIMARY KEY (k, c))` (all table options default).
3. **History load (template TA, "test"):**
   1. Both up, CL ALL via node 1, 8 loader threads: for `k = 0..95` (**D = 96 test partitions**) `UPDATE b29.t SET s = 'a' WHERE k = ?`
      and `c = 0..3,999` rows with a 65,536 B random `pad`; for `k = 1000..1009` (**10 warm-up partitions**) `s = 'x'` and 10 rows
      each. `nodetool flush b29` on both.
   2. F1 (§2.3): stop node 1 (`nodetool drain`, then kill by PID). Through node 2 at CL ONE, for `k = 0..95`:
      `DELETE FROM b29.t WHERE k = ?`, then `UPDATE b29.t SET s = 'x' WHERE k = ?` (client timestamps, the update after the delete).
      `nodetool truncatehints` on node 2; `nodetool listpendinghints` empty. `nodetool flush b29` and `nodetool compact b29 t` on
      node 2 (drops the shadowed rows; node 2 keeps 96 partition tombstones and statics).
   3. Start node 1 (node 2 still up); both `UN`; hints folders empty. `nodetool compact b29 t` on node 1 (one SSTable,
      ≈ 25 GB; nothing pending afterwards). Checks, **none at CL above ONE** on `k = 0..95` (a QUORUM read would repair them):
      `nodetool tablestats b29.t` on both (node 1 ≈ 25 GB, max partition ≈ 262 MB; node 2 small);
      `nodetool getendpoints b29 t 0` = both; one `TRACING ON` CL ONE read of `SELECT s FROM b29.t WHERE k = 0` on each node, read
      locally (trace shows the local replica), giving `a` on node 1 and `x` on node 2.
   4. Drain and stop both; save TA (both nodes' data directories).
4. **Template TB ("agree", for C-agree):** from a copy of TA, start both, re-apply step 3.2's two statements for `k = 0..95` at
   **CL ALL** through node 1 (node 1 now has the deletion and the static, its old rows stay in the older SSTable), flush both, no
   compaction, drain and stop; save TB. Same node-1 SSTable bytes as TA plus a small newer SSTable.
5. **Per-lifetime data:** a fresh copy of TA (or TB) for both nodes. To save time `*-Data.db` may be hard-linked (never rewritten
   in place); every other component is copied. The partitions are consumed by read repair within a lifetime, so a lifetime never
   reuses a template.
6. **Query and hand-out:** prepared `SELECT * FROM b29.t WHERE k = ? AND s = 'x' ALLOW FILTERING` at **QUORUM**, protocol v4,
   Java driver 3.12.1, whitelist `127.0.0.1`, `FallthroughRetryPolicy` (no retry on another host), fetch size default. Each of Q
   workers takes the next `k` from a shared counter over `0..95` (every test partition exactly once per lifetime) in a closed loop,
   and stops when the counter is exhausted.
7. **Lifetime (per run, clean start):** copy the template; start node 1, then node 2; wait for both `UN`; read back thresholds by
   JMX (`RfpJmx`); start the sampler; **warm-up** 20 s at Q = 1 on `k = 1000..1009` (round-robin; consistent partitions, RFP path, no
   fetch); then the **test step** with Q workers on `k = 0..95` until the counter is exhausted, the victim dies, or 160 s; then 30 s
   idle; stop both (kill by PID). One measured lifetime at a time on the node.
8. **DIAG lifetime (calibration, not a readings arm), template TA:** victim with Byteman (helper from B22's `rfp.btm`): at
   `ReplicaFilteringProtection$PartitionBuilder.fetchFromSource` entry log `unresolvedStatic` and the clustering count; at
   `ReplicaFilteringProtection.executeReadCommand` exit log the elapsed ms and the payload's `LocalDataResponse` data buffer
   limit and backing-array capacity. Q = 1 for 10 test partitions, then one partition with `TRACING ON` ("Requesting 0 rows in
   partition … for replica filtering protection"). Gives per-fetch P, capacity and fetch time without GC noise.

### 2.6 Instruments (U independent of K)

- **K (the control's counter):** JMX `org.apache.cassandra.metrics:type=Table,keyspace=b29,scope=t,name=ReplicaFilteringProtectionRowsCachedPerQuery`
  (max and buckets; predicted 2–3) and `…name=ReplicaFilteringProtectionRequests` (second-phase fetches; predicted = test queries
  started, `TableMetrics.java:836-837`), every 5 s; `ReadRepair` metrics (`RepairedBlocking`); count of RFP `cached over` warn /
  error lines in node 1's `system.log` (predicted 0: K ≪ 2,000). Thresholds read back by JMX at start.
- **U (physical, independent of K):** (a) sampler at 1 s on JMX 7199: heap used, NTR active/pending, ReadStage active/pending;
  (b) shipped GC log → live heap after every Full GC and after young GCs that reclaim humongous regions; STW fraction per 60 s
  (`gcwin.py`) (B22 Ve3: the JMX `old_postgc` column does not discriminate, so U comes from the GC log); (c) one
  `jcmd GC.class_histogram` 10 s into the test step in every lifetime still alive then (intrusive, once); (d) at an OOM, the hprof
  (`hprofhist.py`, `hprofstacks.py`): count and bytes of `byte[]` ≥ 128 MiB and their owners (`DataOutputBuffer` /
  `HeapByteBuffer` of `ReadResponse$LocalDataResponse`), count of `ReplicaFilteringProtection` and `ReadCallback` instances,
  `byte[]` of length 65,536 (fetched rows deserialized during the merge), and the thread and stack of the first `OutOfMemoryError`
  from stdout/`system.log`; (e) DIAG probe lines; (f) victim `RssAnon` at 1 s (informational).
- **Load and completion:** client per-second counters: queries started/completed, rows per result (must be 1), read timeouts
  (with "received / blockFor"), `Overloaded`, other errors; per-query latency. NTR active ≥ Q confirms actual concurrency.
- **Direct memory (ledgered):** `java.nio:type=BufferPool,name=direct` at 1 s, to show whether a direct OOM comes first.

### 2.7 Arms, controls and intervention

All arms: same node, same templates' load, same 2-node layout, victim 2 GiB / resolved direct (except the budget search), peer
4 GiB, warm-up then test step (§2.5 step 7), clean start per run.

| Arm | Template | Build | Q | Runs | Role |
|---|---|---|---|---|---|
| **T** (test) | TA (stale node 1) | shipped | 8 | 3 (+ up to 2 if mixed) | the claimed endpoint |
| **C-agree** (matched control, V2) | TB (replicas agree) | shipped | 8 | 3 | protected path: same query, same K (2), same node-1 SSTable bytes; no silent replica → no fetch |
| **C-Q2** (dose control) | TA | shipped | 2 | 3 | same fetch per query at low multiplicity: shows one or two fetches are safe (≥ 30 % margin) |
| **I-names** (intervention, V4) | TA | patched (`I-names.diff`) | 8 | 3 | the completion fetch for an unresolved static row reads the static row and named rows only, not the whole partition |
| O-thr (optional, diagnostic) | TA | shipped, `read_thresholds_enabled: true`, `local_read_size_fail_threshold: 64MiB` | 8 | ≤ 2 | shows whether the byte read threshold (a constraint off by default; changed only here) covers the fetch; predicted not (untracked command) |

`I-names.diff` (diagnostic build, `ReplicaFilteringProtection.java:623-624`):

```
-            ClusteringIndexFilter filter = unresolvedStatic ? command.clusteringIndexFilter(key)
-                                                            : new ClusteringIndexNamesFilter(clusterings, command.isReversed());
+            // B29 intervention (diagnostic only): never read the whole partition to complete a static row
+            ClusteringIndexFilter filter = new ClusteringIndexNamesFilter(clusterings, command.isReversed());
```

For this data it returns the same result (one static row: node 1's old rows are shadowed by node 2's deletion either way) and
read repair still runs, so useful work is kept and measured (queries/s, rows per result). It is not a correct general fix (a
stale static could hide matching rows elsewhere in the partition); it is the causal removal of D1.

Pre-declared Q step (boundary, not an amendment): if T survives its first 2 runs at Q = 8, run T at **Q = 12** ×3 (aligned
3,456 MiB) and C-Q2 unchanged; report both. No escalation after an OOM.

### 2.8 Predicted response and stopping budget

| Arm | Prediction (with numbers) |
|---|---|
| DIAG | `unresolvedStatic = true`, 0 clusterings, one fetch per query; fetch payload limit 262 MB ± 3 %, backing capacity 288 MiB (301,989,888 B); fetch time 0.5–1.5 s; K bucket 2–3; `ReplicaFilteringProtectionRequests` +1 per query; 1 row returned |
| T (Q = 8) | **Java heap OOM in ≥ 2/3 runs** (expected 3/3) within the first 3 waves (≤ 15 s into the test step); first `OutOfMemoryError` on a Native-Transport-Requests or ReadStage thread in `DataOutputBuffer.expandToFit` ← … ← `ReadResponse$LocalDataResponse.build` ← `StorageProxy$LocalReadRunnable.runMayThrow` ← `ReplicaFilteringProtection.executeReadCommand` ← `fetchFromSource` (or the merge deserializing a fetched response); hprof: ≥ 4 `byte[]` ≥ 128 MiB owned by local data responses, together ≥ 60 % of the dumped live heap; K max bucket ≤ 3, no RFP warn/error line; `ReplicaFilteringProtectionRequests` = test queries started |
| C-agree | 0/3 OOM; `ReplicaFilteringProtectionRequests` 0; live heap after GC ≤ 0.4 GiB; 96 queries complete, 1 row each, K bucket 2 |
| C-Q2 | 0/3 OOM; live heap peak ≤ 1.1 GiB; 96 queries complete, 1 row each, read timeouts 0 |
| I-names | 0/3 OOM; `ReplicaFilteringProtectionRequests` = 96; live heap ≤ 0.4 GiB; 96 queries complete, 1 row each (same result as T's completed queries); queries/s ≥ T's pre-OOM rate |
| O-thr | OOM as T (the 64 MiB local read-size fail threshold does not abort the fetch); if it aborts the fetch, record that the threshold covers it once enabled |

A run that ends in GC service loss (≥ 90 % STW over ≥ 60 s) without an OOM is recorded as service loss.

**Stopping budget:** per lifetime ≤ 10 min (template copy ≈ 1 min, start ≈ 1.5 min, 20 s warm-up, ≤ 160 s test step, 30 s idle,
stop/collect ≈ 1 min). Setup (tree copy, patched build, load ≈ 25 GB, two compactions, templates TA/TB) ≤ 2 h. Readings ≤ 16
lifetimes + DIAG + ≤ 5 budget-search/optional lifetimes. No lifetime starts later than **6 h** after stage 2 begins; every process
stopped and §3–§4 written by **7 h**. A lifetime whose nodes fail to reach `UN` twice is invalid and repeated at most once.

### 2.9 Budget search

After T has ≥ 2 OOMs at 2 GiB, from TA, one run each (n/1), direct as resolved: **4 GiB, Q = 16** (aligned 4,608 MiB vs ≈ 3.9 GiB
headroom → OOM predicted); **8 GiB, Q = 32** (9,216 MiB aligned; builds are capped at 32 by READ permits → OOM likely);
**15,872 MiB** (cassandra-env's heap for this node class), **Q = 64** (needs ≥ 54 retained responses of 288 MiB at once while
builds run 32 at a time; uncertain, recorded as the boundary if it survives). D = 96 partitions suffice for 1.5 waves at Q = 64.
Report the largest failing heap.

### 2.10 Interpretation rules (fixed before readings)

- T ≥ 2/3 heap OOM; the first error's stack or the dump attributes the dominant memory to RFP completion-fetch responses
  (`fetchFromSource` → local data response) with K ≤ 3; C-agree 0/3, C-Q2 0/3, I-names 0/3 → claim holds:
  `verified-OOM · deployment` (bypass, accounting omission × multiplicity 8, fault F1 external) → **true positive**.
- `ReplicaFilteringProtectionRequests` = 0 in T, or rows returned ≠ 1, or the node-1 static read back is not `a` at the start of a
  T lifetime → invalid template (divergence lost or deletion missing); rebuild TA and record a dated amendment before new
  readings.
- DIAG fetch time > 2.5 s at Q = 1, or > 25 % read timeouts in T's first run with T surviving → the 5 s deadline caps
  multiplicity (B22's lesson in another form): record it; the pre-declared Q step still runs; if T still survives, verdict
  **retry** with "smaller stale partitions (e.g. 2,000 rows, capacity 128 MiB) at higher Q" named.
- C-Q2 OOMs → per-query footprint larger than predicted; record, keep C-agree as the V2 control, and do not count C-Q2 as V2.
- T survives at Q = 8 and Q = 12 with live heap after GC < 1.5 GiB and no timeouts → measure per-query U from DIAG; if 12 × U +
  baseline < 2 GiB, the estimate was wrong: **retry** with larger partitions or higher Q named.
- A direct-memory OOM before the heap is recorded as that endpoint, not as the claim.
- If the dump shows the fetched rows deserialized (65,536 B `byte[]`) rather than the serialized response as the dominant holder,
  the attribution still holds (same fetch); state which form dominated.

### 2.11 Drop order

First dropped first: O-thr; the 15,872 MiB search; the 8 GiB search; C-Q2 to 1 run (C-agree stays the V2 control). Never dropped:
T ×3, C-agree ×3, I-names ×3.

### 2.12 Decision

- **`ready_for_stage2 = true`.** Constraints at shipped defaults (V6); heap 2 GiB with resolved direct (V7, standing rule); no
  container budget; one realistic external fault in setup only (F1); node pc72 idle (read-only check), harness largely reusable
  from B22; disk need ≈ 100 GB of 707 GiB free.

`sha256 of §1–§2 at freeze: f48b617a164d2cd48d6feb23f5487eabd03e69a7a0fae825677f6d1fb3cc204f (computed over the lines from `## 1. Candidate` up to, not including, this line)` · amendments after the freeze: none.

## 3. Runs (stage 2)

Stage 2 by a fresh session, 2026-11-24 20:11–21:45 EST. Freeze hash checked before any action: sha256 of §1–§2 (from
`## 1. Candidate` up to, not including, the freeze line) = `f48b617a…cc204f`, **matches**. All counted readings are from **pc72**,
the design's node; earlier attempts are in §3.4.

### 3.1 Environment (pc72)

- `pc72` (node2.jason92-326665): x86_64, 40 cores, 125 GiB RAM, Ubuntu 22.04, kernel 5.15.0-203, cgroup v2, 8 GiB swap present
  (`MemorySwapMax=0` on every Cassandra and client scope), OpenJDK 11.0.33. Before the run there was no `CassandraDaemon`, load 0.00
  and no `NODE-LOCK` (the lock named in §2.3 had been released). Lock held 20:11–21:36 EST and released; driver PID kept in
  `/mydata/s4/DRIVER-B29.pid` and removed at the end.
- Build: `/mydata/s4/b29/tree` = copy of `/mydata/s4/cassandra-base`, jar sha256 `570b5249…92192026` (unmodified 5.0.9 build, the
  same hash as pc99's copy). Arm I: `/mydata/s4/b29/tree-I`, [`harness/I-names.diff`](harness/I-names.diff) applied and only
  `ReplicaFilteringProtection*.class` recompiled into a copy of the jar (sha256 `bf6b4de6…df64eb8666`; [`harness/setup.sh`](harness/setup.sh)).
  The peer always runs the shipped build.
- Resolved budgets (from `ps` every lifetime, [`logs/*/run.meta`](logs/T1/run.meta)): victim `-Xms2G -Xmx2G`,
  `-XX:MaxDirectMemorySize=15872M` (resolved by `cassandra-env.sh` on this node, as predicted), G1 `G1HeapRegionSize=16m`,
  `MaxGCPauseMillis=300`, `HeapDumpOnOutOfMemoryError`, `OnOutOfMemoryError=kill -9 %p`, NMT summary. Peer `-Xmx4G`, same direct.
  No `MemoryMax`; every lifetime's scope `memory.events` shows `oom_kill 0` (a Java heap OOM, not a kernel kill).
- Config diff (both nodes, [`logs/T1/yaml-n1.diff`](logs/T1/yaml-n1.diff)): directories, `listen_address`/`rpc_address`
  127.0.0.1 / 127.0.0.2, `cluster_name: 'b29'`, `auto_bootstrap: false`; peer JMX 7299. **No capacity setting changed** in any arm
  except O-thr (`read_thresholds_enabled: true`, `local_read_size_fail_threshold: 64MiB`, node 1 only, [`logs/O1/yaml-n1.diff`](logs/O1/yaml-n1.diff)).
  Thresholds read back by JMX at every start: `fail=32000 warn=2000` ([`logs/T1/rfpk.txt`](logs/T1/rfpk.txt)).
- Harness: [`harness/`](harness/) (from B22's, with attribution in each file): `ctl.sh`, `run-arm.sh`, `drive.sh` (pc72 driver:
  `setup`, `main`, `search`, `refine` phases), `load-data.sh`, `ta-fix.sh` (pc99 history), `B29Load.java`, `B29Sampler.java`,
  `RfpJmx.java`, `b29.btm` (DIAG only), `gcwin.py`, `hprofhist.py`, `hprofstacks.py`, `summ.py`; `batch.sh` is the pc99 attempt's driver
  (history). Per-lifetime excerpts in [`logs/<label>/`](logs/); `summ.py logs/<label>` reproduces the one-line summaries below.
- Data: templates TA (stale node 1) and TB (replicas agree) **built on pc99 and copied to pc72** (deviation D2, §3.4). Node 1's
  `b29.t`: one SSTable of 25,294,014,157 B (sha256 `a50a9cbb…ba47af08`, identical on both nodes), 106 partitions, max partition
  268,650,950 B; node 2: one SSTable of 6.6 MB (96 partition deletions + statics `x`, 10 warm-up partitions). TB adds the deletion and
  `x` to node 1 in a newer 1.5 KB SSTable (the 25 GB SSTable is the same file, hard-linked). Each lifetime starts from a fresh clone
  (`*-Data.db` hard-linked, every other file copied).

### 3.2 Readings (pc72, one lifetime at a time, clean start each)

U comes from the GC log (live heap after each collection; Full GCs) and from the hprof at the OOM; K from the JMX histogram
`ReplicaFilteringProtectionRowsCachedPerQuery` and the RFP warn/error lines; load from the client's per-query log.

| Run (EST) | Arm · template · build | Heap · Q | Outcome | Test queries (96) | K max · RFP fetches · blocking RR | U (independent of K) | Logs |
|---|---|---|---|---|---|---|---|
| DIAG 20:43 | calibration · TA · shipped + Byteman | 2 GiB · 1 (k 0–9) + 1 traced | survived | 10/10 + 1 traced, 1 row each, 0.86–0.96 s | 2 · +11 · +11 | per fetch (Byteman, 11/11): `unresolvedStatic=true`, payload **262,196,026–262,200,030 B**, backing array **339,956,352 B (324.2 MiB)**, fetch 717–768 ms, built on ReadStage-1..3; trace: "Requesting 0 rows in partition … for replica filtering protection" | [`DIAG/`](logs/DIAG/) |
| T1 20:46 | **T** · TA · shipped | 2 GiB · 8 | **heap OOM** 3.4 s into the test step (T2 3.6 s, T3 2.9 s) | 0/96 (8 in flight closed, 88 no host) | ≤ 2 (no query completed) · +8 · +8; RFP warn/error lines 0 | dump 1,561 MiB: 14 `byte[]` ≥ 8 MiB = **1,473 MiB (94 %)** (8 × 96 + 4 × 144 + …); 8 `ReplicaFilteringProtection`, 16 `PartitionBuilder`, 16 `LocalDataResponse`; last Full GC 1,780 → 1,776 MiB | [`T1/`](logs/T1/) |
| T2 20:48 | **T** | 2 GiB · 8 | **heap OOM** | 0/96 | ≤ 2 · +8 · +8; 0 | dump 1,430 MiB: 10 arrays ≥ 8 MiB = **1,345 MiB (94 %)** (8 × 144 + 2 × 96); 8 RFP; last Full GC 1,588 → 1,584 MiB | [`T2/`](logs/T2/) |
| T3 20:51 | **T** | 2 GiB · 8 | **heap OOM** | 0/96 | ≤ 2 · +8 · +8; 0 | dump 1,298 MiB: 11 arrays ≥ 8 MiB = **1,201 MiB (92.5 %)** (8 × 96 + 3 × 144); 8 RFP; last Full GC 1,460 → 1,456 MiB | [`T3/`](logs/T3/) |
| CA1–3 20:53–21:00 | **C-agree** · TB · shipped | 2 GiB · 8 | survived 3/3 | 96/96 ×3, 1 row each, median 1 ms, max 6–7 ms | **0** · **+0** · +0 (digests match: RFP not engaged) | live after GC ≤ 96 MiB, no humongous region after any GC | [`CA1/`](logs/CA1/) [`CA2/`](logs/CA2/) [`CA3/`](logs/CA3/) |
| CQ1–3 21:01–21:11 | **C-Q2** · TA · shipped | 2 GiB · 2 | survived 3/3 | 96/96 ×3, 1 row each, median 0.97–1.05 s, max 1.16–1.18 s, 0 timeouts | 2 · +96 · +96 ×3 | live after GC up to **1,327 / 1,387 / 1,614 MiB** (CQ3 Full GC 1,209 → 1,205 MiB); ≤ 76 humongous regions after GC; STW ≤ 5 % per 60 s | [`CQ1/`](logs/CQ1/) [`CQ2/`](logs/CQ2/) [`CQ3/`](logs/CQ3/) |
| I1–3 21:11–21:19 | **I-names** · TA · `tree-I` | 2 GiB · 8 | survived 3/3 | 96/96 ×3, **1 row each** (the same result as T asks for), median 4–5 ms, max 49–69 ms | 2 · **+96** · **+96** ×3 | live after GC ≤ 96 MiB, no humongous region | [`I1/`](logs/I1/) [`I2/`](logs/I2/) [`I3/`](logs/I3/) |
| S4G 21:19 | search · TA · shipped | **4 GiB** · 16 | **heap OOM** | 0/96 | +16 · +16 | dump 2,673 MiB: 16 arrays ≥ 128 MiB = 2,378 MiB (89 %; ≥ 8 MiB: 2,570 MiB, 96 %); **16 threads with `fetchFromSource` on the stack** | [`S4G/`](logs/S4G/) |
| S8G 21:21 | search | **8 GiB** · 32 | **heap OOM** | 0/96 | +32 · +32 | dump 6,662 MiB: 34 arrays ≥ 128 MiB = 6,556 MiB (98 %); 32 threads in `fetchFromSource` | [`S8G/`](logs/S8G/) |
| S15872M 21:25 | search | **15,872 MiB** · 64 | survived (**boundary**) | 61/96, 1 row each; **33 read timeouts + 2 read failures** (`QueryCancelledException` at the 5 s deadline), latency median 4.7 s, max 5.3 s | 2 · +96 · +96 | ReadStage active max 32 (READ permits), NTR 64; live after Full GC up to **11,831 MiB (74 %)**, after-GC max 14,087 MiB; STW ≤ 3 % | [`S15872M/`](logs/S15872M/) |
| S12G 21:33 | search refinement (added, §3.4 D10) | **12 GiB** · 48 | **heap OOM** | 0/96 | +48 · +48 | dump 9,846 MiB: 35 arrays ≥ 128 MiB = 9,726 MiB (99 %; 15 × 216 + 20 × 324 MiB); 46 threads in `fetchFromSource` | [`S12G/`](logs/S12G/) |
| O1 21:28 | **O-thr** (optional, diagnostic) · TA · shipped, byte read thresholds on, local fail 64 MiB | 2 GiB · 8 | **heap OOM** (as T) | 0/96 | +8 · +8; no read-size abort line | dump 1,436 MiB: 12 arrays ≥ 8 MiB = 1,345 MiB (94 %); 8 threads in `fetchFromSource` | [`O1/`](logs/O1/) |

**First error (V5).** Every OOM lifetime ends in `java.lang.OutOfMemoryError: Java heap space`, followed by the heap dump and
`kill -9` ([`T1/oom-excerpt.txt`](logs/T1/oom-excerpt.txt)). The throwing stack, taken from the hprof
([`T1/oom-stack-from-hprof.txt`](logs/T1/oom-stack-from-hprof.txt)), is:
`DataOutputBuffer.expandToFit:178` ← `UnfilteredRowIteratorSerializer.serialize` ← `ReadResponse$LocalDataResponse.build:201` ←
`ReadCommand.createResponse:374` ← `StorageProxy$LocalReadRunnable.runMayThrow:2211` ← `SEPExecutor.maybeExecuteImmediately:229` ←
`ReplicaFilteringProtection.executeReadCommand:172` ← **`ReplicaFilteringProtection$PartitionBuilder.fetchFromSource:639`** ←
`protectedPartition:589` ← … ← `SelectStatement.execute` (T1: the fetch ran inline on a Native-Transport-Requests thread). In T2
and T3 the same `LocalReadRunnable` → `LocalDataResponse.build` → `expandToFit` stack runs on a ReadStage `SEPWorker` (the
dispatched form of the same fetch). In the search and O-thr dumps, every query's NTR thread is parked inside `fetchFromSource`
(16 / 32 / 46 / 8 threads). In T the only local read with a response over 1 MiB is the completion fetch: in DIAG all 11 such
responses pair one-to-one with `fetch-exit`, and node 1's first-phase response is empty because the static filter drops the partition.

**Holder shape.** The OOM comes during the first wave, while all 8 buffers are still growing (96 → 144 → 216 → 324 MiB, old and new
arrays both live), before any fetch completes. That is earlier than §2.8 predicted ("within the first 3 waves", "≥ 4 `byte[]` ≥ 128 MiB").
T3 has 3 arrays ≥ 128 MiB plus 8 of 96 MiB. In every dump, though, the ≥ 8 MiB arrays from the 8 fetches are 92–94 % of the dumped heap,
so attribution holds under §2.10 (serialized-response form dominant). No 64 KiB `byte[]` accumulates (≤ 33 arrays, ≤ 2.1 MiB), so the
merge-side deserialized form is not the holder.

### 3.3 Arithmetic check against §2.4

Per query: the fetch serializes 4,000 stale rows (262.2 MB, as predicted ± 0 %) into a buffer that ends at 324.2 MiB, not the
predicted 288 MiB. During the last growth, 216 + 324 = 540 MiB is live. At Q = 8 that is 8 × (216 + 324) ≈ 4.2 GiB transient against
≈ 1.9 GiB of headroom, so the first wave cannot finish. At Q = 2 the same arithmetic gives ≤ 1.08 GiB plus baseline, matching CQ's
1.2–1.6 GiB live peaks; the margin is below the declared 30 % (deviation D8). The search follows the 32 READ permits: Q = 16 / 32 / 48
put 16 / 32 / 32 builds in flight and OOM at 4 / 8 / 12 GiB. At 15,872 MiB, 32 builds plus retained responses peaked at 11.8 GiB live;
the remaining queries waited past the 5 s deadline and were cancelled, which released their share.

### 3.4 Deviations and interruptions (dated)

- **D1 (2026-11-24, interruptions).** (a) A first stage-2 attempt ran on **pc99** (not the design's pc72) from ≈ 15:29 EST. It
  built the harness and templates (amendment A1 below), then ran DIAG, T1–T3 (heap OOM 3/3, 25–26 s, the same stack) and CA1–CA3
  (0/3). It was **stopped by the owner at ≈ 16:25 EST** while CQ1 was starting; CQ1's partial data is discarded. Its small logs are
  kept as supplementary evidence in [`logs/pc99-attempt1/`](logs/pc99-attempt1/) (including `template-build.txt` and
  `CQ1-interrupted.txt`) and are **not counted** in V1–V5. (b) A second attempt was cut off by an **API usage limit at ≈ 18:03 EST**.
  It left no file in the case folder and nothing on pc72 or pc99 (checked 20:11 EST). (c) This session repeated every reading on pc72.
- **D2 (2026-11-24 20:13–20:43, templates).** A fresh TA load on pc72 was **aborted**. pc72's `/mydata` writes at **31 MB/s**
  (2 GiB `dd oflag=direct`) against pc99's 245 MB/s on the same disk model. The CL ALL load timed out 930 times in 3 min (8 partitions
  in 187 s against 35 s on pc99), and an unretried static UPDATE timeout killed the loader before F1. Everything was stopped
  and removed ([`logs/pc72-setup/loadTA-aborted.txt`](logs/pc72-setup/loadTA-aborted.txt)). The pc99 templates (same jar, same
  harness, A1 checks passed) were streamed to pc72 with tar (hard links kept). The TA `Data.db` sha256 is identical on both nodes,
  and the data was `sync`ed (6 min 40 s) before any reading. Environment deviation only: the data bytes are the same, and every
  lifetime reads them from page cache (the DIAG fetch takes 0.72–0.77 s, as on pc99's 0.62–0.65 s).
- **D3 (pc99, before any reading, amendment A1).** In the first TA build, F1 mutations that timed out towards the stopped node 1 were
  hinted after `truncatehints` and replayed when node 1 restarted. Node 1 was killed without a flush, its commit log removed and the
  hints truncated again; [`harness/ta-fix.sh`](harness/ta-fix.sh) then checked node 1's memtable empty after restart, compacted it and
  read `s = a` (4,000 rows) on node 1 and `s = x` on node 2 ([`logs/pc99-attempt1/template-build.txt`](logs/pc99-attempt1/template-build.txt)).
  `load-data.sh` now carries the waits and a hard check (abort if node 1's memtable is non-empty after its restart).
- **D4 (template load).** 2,587 of 384,000 CL ALL inserts timed out on pc99 (0.67 %). The fetched payload of every test partition is
  262.2 MB = 4,000 × 65,550 B, so node 1's stale partitions are complete.
- **D5.** Buffer capacity 324.2 MiB (339,956,352 B), not 288 MiB. The growth steps seen in the dumps are 96 → 144 → 216 → 324 MiB.
- **D6.** The fetch usually runs on a ReadStage thread (dispatched), and sometimes inline on the NTR thread (T1); §2.1 expected inline.
- **D7 (C-agree).** With agreeing replicas the digests match, so the coordinator never resolves data and **RFP is not engaged at all**
  (K 0 and RFP fetches 0, not "K = 2"). The control still matches the query, the template bytes and the budget, but it differs from T
  in more than the fetch. I-names is the tighter comparison: same RFP path, same divergence, same read repair, only the fetch filter changed.
- **D8 (C-Q2).** Live peak 1.2–1.6 GiB against the predicted ≤ 1.1 GiB, so the margin is below 30 %. Per §2.10, C-agree stays the V2
  control; C-Q2 is reported as the dose control (0/3 at Q = 2).
- **D9.** The `jcmd GC.class_histogram` 10 s into the test step was never taken in T (the victim was dead by then); U comes from the
  dumps and GC logs.
- **D10 (21:33 EST, budget search).** After 8 GiB OOM'd and 15,872 MiB survived, one bisect point was added: **12 GiB, Q = 48**
  (protocol step 4, V7 "search upward"). It is not an amendment to any arm.
- **Not run:** the pre-declared Q = 12 step (T did not survive at Q = 8).
- **Cleanup:** every process this session started on pc72 was stopped and checked gone (no `CassandraDaemon`, client, sampler or
  driver; no b29 scope). Bulk data deleted on pc72 (templates, data dirs, build copies, every hprof) and on pc99 (the first attempt's
  templates, build copies and the interrupted CQ1 data). Left: `pc72:/mydata/s4/b29/` 118 MB (harness, driver logs, per-run Cassandra
  and GC logs) and `pc99:/mydata/s4/b29/` 60 MB (the same for the first attempt). The local ssh/tar helpers have all ended.

## 4. Conclusion (stage 2)

**Verdict: true positive.** Protocol status: **`verified-OOM · deployment`**, bypass · accounting omission × multiplicity
(fault F1 external, applied in setup only; no instrumentation in the counted arms).

| Condition (pc72, 5.0.9 shipped, all capacity constraints default) | n/N | Status |
|---|---|---|
| T: stale coordinator, 2 GiB heap / 15,872 MiB direct, Q = 8 | **3/3 heap OOM** | verified-OOM · deployment |
| C-agree (replicas agree) / C-Q2 (Q = 2) / I-names (named-rows fetch) | 0/3 / 0/3 / 0/3 | controls and intervention |
| Budget search: 4 GiB Q 16 · 8 GiB Q 32 · 12 GiB Q 48 · 15,872 MiB Q 64 | 1/1 · 1/1 · 1/1 · 0/1 (35/96 cancelled at 5 s) | largest failing heap **12 GiB** (n/1) |
| O-thr (byte read thresholds on, 64 MiB local fail) | 1/1 OOM | the byte threshold does not cover the fetch |

| | Evidence |
|---|---|
| V1 Repetition | T1–T3: heap OOM 3/3 from clean starts (pc72); the pc99 attempt's T1–T3 are 3/3 as well (supplementary) |
| V2 Matched control | CA1–CA3 0/3 (same query, same node-1 SSTable, same budget; no fetch); dose control CQ1–CQ3 0/3 (the same fetch at Q = 2, margin < 30 %) |
| V3 Measurement | U from the hprof and GC log: 1.2–1.5 GiB in ≥ 8 MiB `byte[]` (92–94 % of the dump) held by 8 completion-fetch buffers; K from JMX: max 2 per query, 0 RFP warn/error lines |
| V4 Intervention | I1–I3 0/3 at the same Q = 8: 96/96 queries answered with the same 1 row, the same 96 RFP fetches and 96 blocking read repairs, live heap ≤ 96 MiB, median 4–5 ms |
| V5 Initiating failure | first `OutOfMemoryError` in `DataOutputBuffer.expandToFit` ← `LocalDataResponse.build` ← `LocalReadRunnable` ← `RFP.executeReadCommand:172` ← `fetchFromSource:639` (T1; T2/T3 the same on a ReadStage worker); the dumps show the claimed holder (above) |
| V6 Default constraints | yaml diff = directories, addresses, cluster name, `auto_bootstrap` only; RFP thresholds read back 32,000 / 2,000; read-size thresholds off |
| V7 Acceptable budget | heap 2 GiB (ideal), direct 15,872 MiB as resolved (standing rule); search upward: OOM up to **12 GiB**, boundary at 15,872 MiB, where the 5 s deadline caps concurrency |

**Reason.** When a filtering query has a static-column predicate and the coordinating replica missed a partition deletion, RFP
marks the static row unresolved. It completes it by reading that replica's **entire partition** with `DataLimits.NONE`, no row filter
and no paging, then serializes it into one heap `LocalDataResponse` per query (262 MB of stale rows into a 324 MiB array) to return a
single CQL row. None of those rows passes `incrementCachedRows`, so the control charges 2 per query and never warns. The byte read-size
thresholds do not apply to the fetch command even when enabled (O-thr). Nothing bounds the bytes across queries: 8 concurrent queries
exhaust a 2 GiB heap in the first wave, and up to 12 GiB fails at proportionally higher concurrency. Restricting the completion fetch
to the named rows removes the OOM and keeps every answer.

**Limits of attribution.**
- The omission is shown in rows (4,002 versions materialized per query against K = 2). At this row count the fetch is still under
  the 32,000-row threshold, so even a correct count would not have rejected these queries. The OOM depends on wide rows (65 KiB)
  times concurrency, which no count control bounds (B22's lesson). A stale partition of more than 32,000 rows would show the row-count
  bypass directly; that was not run.
- C-agree does not engage RFP at all (D7); I-names is the closer causal control.
- The two instances share one host (environment deviation). The stale replica coordinates because the client whitelists it; with
  token-aware routing on RF 2 that happens for about half of a stale replica's keys.
- F1 (a node down past the 3 h hint window, no repair since) is an external fault applied in setup only.
- At large heaps the 5 s read deadline and the 32 READ permits are what stop the growth. That is a time bound, not a memory bound
  (15,872 MiB: 74 % live, 36 % of queries failed).
- **Not done here (not this stage's scope):** new clue pattern or new holder proposals. The holder is the claimed one, and the
  U4-style "one partition serialized whole" shape already exists (U4, B17, B20).
