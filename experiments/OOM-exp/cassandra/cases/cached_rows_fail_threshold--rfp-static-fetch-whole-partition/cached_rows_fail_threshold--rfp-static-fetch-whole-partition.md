# B29 (OC-470 + OC-480) — cached_rows_fail_threshold: an unresolved static-column predicate makes replica-filtering protection read the stale replica's whole partition, uncounted  <!-- file: cassandra/cases/cached_rows_fail_threshold--rfp-static-fetch-whole-partition/cached_rows_fail_threshold--rfp-static-fetch-whole-partition.md -->

| Field | Value |
|---|---|
| Case ID | `B29` (B = bypass case; README "ID prefixes"): the design is a bypass, accounting omission (§2.1) |
| From | `OC-470` and `OC-480` of the phase 1 OOM candidate list (same holder, two agents; both rows `picked: B29 (2026-11-24)`) |
| Phase-1 case file | [`cached_rows_fail_threshold-queryProtectedPartitions-i--autonomous`](../../../../capacity-enforcement-exp/cassandra/stage3-ai-deep-read/cases/cached_rows_fail_threshold-queryProtectedPartitions-i--autonomous.md) · stage-4 result [`results/…`](../../../../capacity-enforcement-exp/cassandra/stage4-runtime-verification/results/cached_rows_fail_threshold-queryProtectedPartitions-i--autonomous.md) |
| System / pinned source | Cassandra 5.0.9 (`systems/cassandra/source/`); built copy `pc72:/mydata/s4/cassandra-base` (`build/apache-cassandra-5.0.9-SNAPSHOT.jar`) |
| Stage 1 (design) | phase-2 OOM agent, stage 1 (Claude Opus 5.5), 2026-11-24 05:40–06:30 EST, owner-approved batch of 2026-11-24; nothing run (pc72, pc82, pc91, pc75, pc99 checked read-only) |
| Stage 2 (verify) | pending (a fresh session) |
| Verdict | `pending` |

## Summary

- **Conclusion:** pending (stage 2).
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

pending

## 4. Conclusion (stage 2)

pending
