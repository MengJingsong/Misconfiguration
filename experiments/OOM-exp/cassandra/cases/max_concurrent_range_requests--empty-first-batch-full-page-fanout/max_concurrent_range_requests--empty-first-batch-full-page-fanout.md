# C10 — max_concurrent_range_requests: after an empty first batch, one range read fans out to every sub-range with a full page each (OC-509)  <!-- file: cassandra/cases/max_concurrent_range_requests--empty-first-batch-full-page-fanout/max_concurrent_range_requests--empty-first-batch-full-page-fanout.md -->

| Field | Value |
|---|---|
| Case ID | `C10` (C = convergence case; README "ID prefixes"); provisional ID kept: the design is convergence (multiplicity) |
| From | `OC-509` of the phase 1 OOM candidate list (triage 2026-11-20 rank 4; cluster with OC-415, OC-522 and the legacy OC-37) |
| Phase-1 case file | [`max_concurrent_range_requests-computeConcurrencyFactor-liveReturned--autonomous`](../../../../capacity-enforcement-exp/cassandra/stage3-ai-deep-read/cases/max_concurrent_range_requests-computeConcurrencyFactor-liveReturned--autonomous.md) (stage-4 result: [`results/…`](../../../../capacity-enforcement-exp/cassandra/stage4-runtime-verification/results/max_concurrent_range_requests-computeConcurrencyFactor-liveReturned--autonomous.md)) |
| System / pinned source | Cassandra 5.0.9 (`systems/cassandra/source/`); built copy `pc91:/mydata/s4/cassandra-base` (`build/apache-cassandra-5.0.9-SNAPSHOT.jar`) |
| Stage 1 (design) | phase-2 OOM agent, stage 1 session (Claude Opus 5.5), 2026-11-21 08:02–08:55 EST; nothing run (pc91 checked read-only) |
| Stage 2 (verify) | phase-2 OOM agent, stage 2 session (Claude Opus 5.5), 2026-11-21 08:15–10:15 EST on pc91; harness `harness/`, excerpts `logs/`, raw data `pc91:/mydata/s4/c10/runs/` |
| Verdict | **true positive** (`verified-OOM · deployment`, convergence (multiplicity)) |

## Summary

- **Conclusion:** true positive. At shipped defaults and a 2 GiB coordinator heap, three concurrent paged
  `ALLOW FILTERING` range reads whose first sub-range has no match end in a Java heap OOM 3/3 (within ≈ 5 s); one such
  read alone (0/3), three reads without the fan-out (0/3), or three with `max_concurrent_range_requests=1` (0/3) survive.
  Larger heaps fail at more readers: 4 GiB at 6, 8 GiB at 16; the auto heap (31 GiB) did not fail up to 120 because
  replica drops turned the reads into timeouts. Topology stand-in: 3 instances on one host, RF 1.
- **Root cause (confirmed):** `cassandra.max_concurrent_range_requests` counts sub-range *requests*, not
  bytes. When the first batch of a paged range read returns no rows (an `ALLOW FILTERING` predicate with no match in the
  leading token ranges), the next batch sends every remaining sub-range at once, each with the full 5,000-row page limit,
  and all responses that arrive before the page is complete sit on the coordinator heap, charged to no counter (the
  internode reserve is released at delivery; the read-size thresholds ship off). Here one 10 MB page held up to 43
  responses (15 local arrays of 17 MB, each two G1 regions, plus remote 10 MB arrays) ≈ 0.93 GiB of heap regions, and
  nothing bounds the sum over concurrent range reads.

## 1. Candidate

**The row** (phase 1 OOM candidate list, `phase1-oom-candidates.md`, quoted; Status set to `picked: C10 (2026-11-21)`
by the session before this design):

> | OC-509 | 2026-11-18 | `max_concurrent_range_requests-computeConcurrencyFactor-liveReturned--autonomous` | autonomous | Holder: coordinator heap. Each sub-range response (the serialized `data` ByteBuffer in ReadResponse, kept by the DataResolver/ReadCallback of each SingleRangeResponse) stays on the heap until the batch is iterated or closed. [details](runs/wave3.md#oc-509) | — | picked: C10 (2026-11-21) |

Full text (`runs/wave3.md` § OC-509), quoted:

> Holder: coordinator heap. Each sub-range response (the serialized `data` ByteBuffer in ReadResponse, kept by the
> DataResolver/ReadCallback of each SingleRangeResponse) stays on the heap until the batch is iterated or closed. Why
> nothing stops it: the cap counts requests, not bytes. Each sub-range gets the full command limit (one page of rows,
> any row size). The `liveReturned == 0` branch, and the initial estimate when the local estimate is low, both jump
> straight to min(ranges, 10 x cores). At defaults no byte limit applies: read_thresholds_enabled=false and
> coordinator/local_read_size_* are null. The internode inbound reserve is released once the callback is delivered,
> so held responses count against nothing. Each query has its own cap with no node-wide total, and up to
> native_transport_max_threads=128 range queries can run at once (the native in-flight limit counts request bytes,
> not response bytes). Rough size at defaults: 6 nodes x 16 tokens (RF3) gives about 96 sub-ranges; with 16 cores the
> cap is 160, so all 96 go out. At QUORUM that is 2 data responses each, x 5,000-row driver page x 1 KiB, about 960 MB
> per query. Stage 4 measured 166 MB at only C=16 with 10 MB responses. A handful of concurrent scans like this go
> past a default heap (half of RAM, at most 16 GiB). Top-K (SAI ANN) queries skip the cap entirely through
> ScanAllRangesCommandIterator.
>
> **Where:** src/java/org/apache/cassandra/service/reads/range/RangeCommandIterator.java:162 (also :230-236, :255);
> RangeCommands.java:54, :84, :96, :81-82; db/ReadResponse.java:228; config/Config.java:283, :526-530

**Triage (`runs/triage-2026-11-20.md`, rank 4), quoted:**

> | 4 | OC-509 | yes | multi-node: 3 instances, RF 1 (can share one x86 node) | A range read gives every sub-range command
> the full page limit and enforces the limit only after merging. When the first batch returns no rows (ALLOW FILTERING
> whose matches lie in later token ranges), or the local estimate is low, concurrency jumps to min(ranges, 10 x cores).
> All those responses then sit on the coordinator heap, charged to nothing once the internode receive callback has
> run. A single node merges all its ranges into one sub-range, so this needs nodes with different replica sets: 3
> nodes x 16 tokens is about 30–48 sub-ranges. With 5,000-row pages of about 16 KiB rows (about 80 MB per response,
> under the 128 MiB internode message cap), that is about 2.4 GB of responses for one page of one query. Stage 4
> measured 166 MB at C = 16 with 10 MB responses. Test time: 1–2 h. | Same coordinator holder as U4, multiplied by the
> sub-range count, which U4 did not test. Duplicates OC-415, OC-522 and the legacy OC-37 (open). |

**The cluster the triage names** ("Range-read sub-range concurrency: OC-509 (primary), OC-415, OC-522, plus the legacy
OC-37"), quoted from the list / `runs/wave3.md`:

- **OC-415** (autonomous, phase-1 case `no_constraint-needfiltering-restriction_count--autonomous`): "Holder: the
  replica responses buffered at the coordinator for one page of a key-range (ALLOW FILTERING) scan. needFiltering()
  only gates the query on the client's ALLOW FILTERING opt-in … RangeCommandIterator sends sub-range commands that
  each carry the full page limit (command.forSubRange keeps DataLimits). The limit is enforced only globally, after
  merge … A filter that matches nothing in the early ranges makes liveReturned==0, so computeConcurrencyFactor jumps
  to maxConcurrencyFactor = min(#ranges, 10 x cores). Every concurrent sub-range response is then received in full …
  Rough size: 6 nodes x num_tokens 16 = 96 ranges … about 1 GB per page of one query. A few concurrent clients exceed a
  default heap. If paging is off, each sub-range response holds all matching rows of its range (no limit)."
- **OC-522** (guided, same phase-1 case as OC-509; patterns CP-2, CP-7, CP-3, CP-12): "Holder: the coordinator heap,
  in the per-sub-range DataResolver/ReadCallback of one range query. When the first batch returns no rows, the next
  batch sends min(ranges, 10 x cores) sub-range requests at once. Each one carries the full command limit: the page
  size, or for an unpaged query the whole CQL LIMIT … Size at defaults: 3 nodes x 16 tokens = 48 ranges … 48 x
  5,000-row page x 1 KiB is about 240 MB per query … Across up to 128 concurrent range queries that reaches tens of
  GB, past any default heap. Unpaged scans are worse because each sub-range response can hold the whole range."
- **OC-37** (legacy, Status `open`): "[lead list, blind, E1; N17 cluster; queued as U4] The range-read concurrency cap
  counts sub-range requests, not bytes; each carries a full page and the responses sit on coordinator heap untracked
  after the internode receive reserve is released at callback (`InboundMessageHandler.java:438`): default
  `min(ranges, 10 × cores)` gives e.g. 48 × 5,000 × 1 KiB ≈ 240 MB per query (stage 4: 166 MB at C = 16), × concurrent
  range queries."

**What this design covers.** The shared mechanism of all four rows: the `liveReturned == 0` branch
(`RangeCommandIterator.java:162-166`) reached through an `ALLOW FILTERING` predicate with no match in the leading
token ranges (OC-415's and the triage's trigger), every remaining sub-range sent in one batch with the full 5,000-row
page limit (`:190`), responses held on the coordinator heap uncharged after the internode callback, multiplied by
concurrent range queries (OC-509, OC-522, OC-37). Sizing follows OC-522 / the triage (3 instances × 16 tokens) at RF 1.
**Not covered:** the "low local estimate" initial-batch route (`RangeCommands.java:84-96`), the RF 3 / QUORUM sizing
(two data responses per sub-range, OC-509/OC-415), the unpaged variant (each sub-range up to the whole CQL LIMIT,
OC-415/OC-522), and the Top-K `ScanAllRangesCommandIterator` route (OC-509's last sentence; that belongs to the
unpaged Top-K cluster, OC-565). A true positive here would be written to OC-509; closing OC-415, OC-522 and OC-37 as
covered is the owner's call.

**Phase-1 case and its stage-4 result.** Stage 3 (2026-10-26, autonomous) traced
`cassandra.max_concurrent_range_requests` (JVM property, default `max(1, 10 × availableProcessors)`, read once at
`RangeCommands.java:54`) and estimated `positive`: the property caps coordinator heap per range read at about
cap × page-limit rows, in requests not bytes. Stage 4 (advisor-run, filed 2026-10-27/11-03): **Unit Confirmed — caps;
Cluster Confirmed — caps** (run 1b), outcome class true positive (as a cap). Cluster: 3 nodes on loopback, node 1
the coordinator with one empty range, nodes 2/3 owning 48 dense ranges, 288,000 rows of 2 KiB. Run 1 (`fetch_size`
5,000): one dense response 10,389,2xx B; bytes brought in per read = C × 10.39 MB (166.23 MB at C = 16); at C = 48 and
the default (100) the replicas' outbound queue to node 1 (4 MiB + 128 MiB endpoint reserve) **dropped every response
beyond ≈ 13 per replica** (523/524 drops, 272.7 MB per read, 3/20 and 1/20 reads timed out at 10 s); retained heap at
close H was timing-dependent (median 42–62 MB, max 270 MB), and the post-GC live heap was ≈ 1.6 bytes per held data
byte (a 10.39 MB `byte[]` fills one 16 MiB G1 region). Run 1b (`fetch_size` 1,000 to avoid the drops): 99.74 MB per
uncapped read, H max 51.95 MB on a 4 GiB heap; "the re-run shows the cap governing the bytes a read brings in, not a
heap failure without it". **Lessons used here:** (a) keep each replica's burst to the coordinator below ≈ 132 MiB per
query (else drops, not the knob, bound it); (b) make retention deterministic: in stage 4 the page filled from the
*first* response and later arrivals were dropped at close, so this design puts slow, match-free sub-ranges at the
head of the burst (below); (c) count heap in G1 regions, not data bytes; (d) no stage 4 test ran concurrent range
reads or an OOM endpoint.

**JIRA prior art** (read only: `jira-oom-survey.csv` and the Apache JIRA REST search API, reachable 2026-11-21;
nothing posted). Survey CSV: range-read OOM rows are all about one huge page or unpaged result (CASSANDRA-4743 "Range
slice query causes OOM", Not A Problem; CASSANDRA-6052, CASSANDRA-11528 "Server crash when select returns more than a
few hundred rows" — 5,000-row pages of 100 KB–4 MB blobs, Unresolved; these are the U4 holder), none about the
sub-range fan-out. REST queries `text ~ "concurrency factor" AND text ~ "range"` (102 hits),
`text ~ "max_concurrent_range_requests"` (76), `text ~ "RangeCommandIterator" AND text ~ "memory"` (2),
`text ~ "range" AND text ~ "OutOfMemoryError" AND text ~ "concurrent"` (30), titles read:
- **CASSANDRA-15752** "Range read concurrency factor didn't consider range merger" (Fixed 3.0.21/3.11.7/4.0): added
  the `max_concurrent_range_requests` cap because "when executing range read on table with very small amount of data,
  concurrency factor can be bumped to size of total vnode ranges … coordinator will send large number of concurrent
  range requests, potentially slowing down the cluster" — the constraint under test; motivation is load, not memory.
- **CASSANDRA-15774** "Improve range reads to query by endpoints instead of vnodes to reduce number of remote
  requests" (Unresolved, 7.x): "when concurrency factor is high because returned row count is small comparing to query
  limit or index filtering is used, coordinator may send too many concurrent remote range requests in a batch" —
  request count, not response bytes.
- **CASSANDRA-18515** (Fixed 6.0): SAI initial concurrency; not this path.
No hit reports coordinator heap exhaustion from the fan-out of full-page sub-range responses. **Verdict: `new`** (as an
OOM; the burst itself is a known performance concern, CASSANDRA-15752 fixed by the count cap, CASSANDRA-15774 open).

## 2. Design solution (stage 1; frozen)

**Mechanism.** Direction: **convergence (multiplicity)**, with an unprotected-configuration element (the byte
controls `read_thresholds_enabled` / `coordinator_read_size_*` ship off, as in U4); technique note
[`default-convergence-playbook.md`](../../../default-convergence-playbook.md) (multiplicity sweep at default
capacities). A paged range read (`SELECT * … WHERE b = 1 ALLOW FILTERING`, driver page 5,000 rows) runs
`RangeCommands.partitions` (`RangeCommands.java:56-66`). The initial concurrency comes from the coordinator's local
estimate, which ignores the filter (`estimateResultsPerRange`, `RangeCommands.java:125-136`;
`DataLimits.java:456-462`): ≈ 20,000 rows per vnode range here, so `ceil(5000 / 18,000) = 1`
(`RangeCommands.java:84-96`) and batch 1 is one merged sub-range (`RangeCommandIterator.java:230-238`). If that
sub-range has no row with `b = 1`, `liveReturned == 0` and `computeConcurrencyFactor` returns
`maxConcurrencyFactor = min(vnode ranges, 10 × cores)` (`:159-167`; `RangeCommands.java:54`, `:84`), capped only by
the vnode ranges left: **batch 2 sends every remaining merged sub-range at once** (`:223-238`). Each sub-range command
keeps the full page limit (`command.forSubRange(…)`, `:190`; "a RangeCommandIterator will honor the command limit for
each range, but will not enforce it globally", `RangeCommands.java:60`); the batch counter is `DataLimits.NONE`
(`:254`). Responses are stored per sub-range in the `DataResolver` of each `SingleRangeResponse`
(`SingleRangeResponse.java:33-59`): remote ones as one heap array of exactly the data length
(`ReadResponse.java:338`), local ones (the coordinator's own sub-ranges, `LocalReadRunnable`,
`RangeCommandIterator.java:205-207`, `StorageProxy.java:2211`, `:2230`) as the backing array of a
`DataOutputBuffer` grown by doubling from 128 B (`ReadResponse.java:197-203`; `DataOutputBuffer.java:57`, `:158-170`,
doubling below 64 MiB). The internode receive reserve is released as soon as the callback has run
(`InboundMessageHandler.java:436-440`), so held responses are charged to nothing. The batch is consumed in token order
(`StorageProxy.concatAndBlockOnRepair`, `:255`); the page closes after 5,000 counted rows and the iterator closes all
responses (`:259-264`). **Design lever:** the first two sub-ranges of batch 2 are also match-free, so the consumer
blocks while their replicas scan every row of them, while the dense sub-ranges (each stopping at 5,000 rows) finish and
are held; then the first dense response fills the page. Per query ≈ (S − 3) full-page responses are held at once for
one page that uses one of them. Concurrent clients multiply this; the only bound on concurrent range reads is
`native_transport_max_threads` = 128 (`Config.java:283`).

**Protection map** (fixed before any run).

| Domain | Holder (allocation → release) | Counter K | Limit at default (resolved) | At the limit |
|---|---|---|---|---|
| **Sub-range concurrency (claimed)** | per query, one `SingleRangeResponse` → `DataResolver` → response `byte[]` per sub-range in the batch (`RangeCommandIterator.java:188-219`, `ReadResponse.java:338` / `:197-203`) → released at `close()` after the page | requests per batch (`concurrencyFactor`) | `min(vnode ranges = 48, 10 × availableProcessors)`; node 1 pinned to 16 CPUs → 160, so 48 (all) | nothing: counts requests; per-request bytes unbounded |
| Row limit per sub-range | each response ≤ page limit rows | rows (`DataLimits` per sub-range) | 5,000 rows (driver default page) | stops each sub-range at 5,000 rows; no byte bound |
| Read-size thresholds | the same holders | bytes | **off** (`read_thresholds_enabled: false`, `coordinator_read_size_*` / `local_read_size_*` null, `Config.java:526-530`) | nothing |
| Page-size guardrail | — | rows | off (−1) | nothing |
| Internode, replica side (nodes 2/3) | outbound queue to node 1 (`OutboundConnection.java:330-348`) | queued bytes | 4 MiB per connection + 128 MiB endpoint + 512 MiB global reserve (`Config.java:250-254`) | **drops** the response (`onOverloaded`); the coordinator then waits up to `range_request_timeout` 10 s (`Config.java:148`) for that sub-range |
| Internode, coordinator side | inbound bytes until the callback has run (`InboundMessageHandler.java:436-440`) | bytes being processed | 4 MiB + 128 MiB endpoint + 512 MiB global (`Config.java:256-261`); max message 128 MiB (`DatabaseDescriptor.java:990-996`) | back-pressure on reading; **does not cover held responses** |
| Concurrency of queries | one blocked request thread per range read | NTR threads; READ stage | 128 NTR threads; `concurrent_reads` 32 per node | queues; no byte sum across queries |
| Native in-flight request bytes | request body (small SELECT) | request bytes | heap/10, per IP heap/40 | does not cover responses |
| Coordinator page (U4's holder, ledgered, not claimed) | deserialized page + `ResultSet` of 5,000 rows (`SelectStatement` paged path) | rows | 5,000 rows | ≈ 25–40 MB per query here (2 KiB rows); measured by arm M |
| Encoded response (ledgered) | Netty direct buffer until flushed | — | `MaxDirectMemorySize` | C2's domain; local fast client |
| Baseline | memtable heap pool (empty: read-only), key cache min(5 % heap, 100 MiB), chunk cache (`file_cache_enabled` shipped commented, record value) | own | defaults | evict / flush |

**Configuration and budget audit.**
- Source/build: `pc91:/mydata/s4/cassandra-base` (5.0.9, `build/apache-cassandra-5.0.9-SNAPSHOT.jar`, copied from
  `pc96` 2026-11-18, smoke-tested), copied to `/mydata/s4/C10/tree` (never build in it). JDK 11.0.33; GC per shipped
  `conf/jvm11-server.options`: G1 (`:63`), `G1HeapRegionSize=16m` (`:66`); `HeapDumpOnOutOfMemoryError` from
  `jvm-server.options`. Ubuntu 22.04, kernel 5.15, cgroup v2, 8 GiB swap (excluded per scope). pc91 checked read-only
  2026-11-21 06:07 MST (08:07 EST): 32 cores, 125 GiB RAM (123 free), `/mydata` 714 GiB free (spinning), `/dev/shm`
  63 GiB tmpfs, load 0.00, **no `CassandraDaemon` running**, `/mydata/s4/` holds only `cassandra-base`, `lo` has only
  `127.0.0.1/8` (the whole `127.0.0.0/8` routes to `lo` on Linux: no alias needed). Node clock is **MST = EST − 2 h**.
- **Every capacity constraint at its shipped default** (V6), resolved: `max_concurrent_range_requests` unset →
  10 × availableProcessors = **160** on node 1 (pinned to 16 CPUs; JDK 11 honours affinity; the value is not exposed over JMX, so record
  `nproc` under the pin and the trace's "new concurrent requests: N"); vnode ranges 48 → the cap does not bind (it would bind only below 5 CPUs);
  `num_tokens: 16`, `allocate_tokens_for_local_replication_factor: 3`, `read_thresholds_enabled: false`, page-size
  guardrail off, `concurrent_reads: 32`, `native_transport_max_threads: 128`, internode queue/reserve capacities
  4 MiB/128 MiB/512 MiB, `internode_max_message_size` resolved 128 MiB, `range_request_timeout: 10000ms`,
  `read_request_timeout: 5000ms`, `native_transport_timeout: 12s`, memtable/caches default. The only constraint changed
  is `max_concurrent_range_requests` in the intervention arm I.
- **Environment deviations** (disclosed; none is a capacity setting): (1) **three instances on one node** (pc91),
  `listen_address`/`rpc_address` = `127.0.0.1`, `127.0.0.2`, `127.0.0.3`; same `storage_port` 7000 and
  `native_transport_port` 9042 (different addresses); **separate JMX ports 7199/7299/7399** (JMX binds `127.0.0.1`
  only; HANDOFF "Lessons" and `_run-log.md`); separate `cassandra.yaml`, `cassandra-env.sh`, log and data dirs per
  instance; seeds `127.0.0.1:7000`; `cluster_name: C10`. (2) **RF 1** (`SimpleStrategy`), a topology stand-in for
  "replica sets differ between adjacent ranges": at RF 3 on 3 nodes every range has the same replicas and merges into
  one sub-range (`ReplicaPlanMerger.java`, `ReplicaPlans.maybeMerge`); the candidate's RF 3 / 6-node sizing is not
  reproduced. (3) **CPU pinning** (`taskset`): node 1 CPUs 0–15, node 2 16–23, node 3 24–29, client 30–31 (keeps the
  victim's CPU independent of replica load; changes `availableProcessors`-derived defaults: record them).
  (4) Node data, commit log, hints and saved caches on **tmpfs** `/dev/shm/c10/node<i>/` (HANDOFF "Lessons": several
  local nodes on a spinning disk stall); logs, GC logs, heap dumps and run outputs on `/mydata/s4/C10/runs/<label>/`.
  (5) Replicas (nodes 2/3) run **heap 8 GiB** (`MAX_HEAP_SIZE=8G`, direct auto) so the victim is node 1; record any
  replica OOM as an invalid lifetime. (6) Client on the same node, talking to node 1 only (white-list policy).
- **Budgets** (V7; standing rule: heap and direct ≥ 512 MiB meet V7, 2 GiB ideal):
  - **Primary: node 1 heap 2 GiB** (`MAX_HEAP_SIZE=2G`), direct **auto** as `cassandra-env.sh` resolves it with a
    hand-set heap on pc91 (U4 amendment A2 found 15,872M on a 125 GiB node under G1; record `-Xmx` and
    `-XX:MaxDirectMemorySize` from the process command line).
  - **Upward search** (node 1 only): 4 GiB, 8 GiB, then the auto heap (`MAX_HEAP_SIZE` unset; U4 A2: 31,744M on pc91)
    if time allows.
  - **No container budget.** Each JVM runs in `systemd-run --user --scope -p MemoryMax=<heap+direct+8G>
    -p MemorySwapMax=0` for isolation and swap exclusion only; a scope `oom_kill` makes the lifetime **invalid**;
    record `memory.events` at the end of each lifetime.

**Ceiling arithmetic.** Row: `pk bigint`, `b int`, `v blob` of 2,048 random bytes → a 5,000-row response
r ≈ **10.39 MB** (stage 4 measured 10,389,2xx B for 5,000 rows of 2 KiB; IC re-measures it). Heap per held response
(G1, 16 MiB regions; humongous ≥ 8 MiB): **remote** `byte[r]` = one region = **16 MiB** (stage-4 known answer:
+16,786,657 B per 10,389,262-B array); **local** `DataOutputBuffer` backing array doubled to 16,777,216 B, which with
its 16-B header spans **two regions = 32 MiB** (estimate from the G1 humongous rule; not measured in stage 4), plus a
transient 8 MiB predecessor during the last doubling. Ring: 3 × 16 = 48 vnode ranges; adjacent ranges with the same
owner merge (RF 1), so S merged sub-ranges ≈ **32** (band 24–40; computed exactly from the LOAD ring). Cold
(match-free) sub-ranges: SR1 (batch 1), SR2, SR3 (head of batch 2); dense D = S − 3 ≈ **29** (21–37), about one third
local to node 1. **Held per query** at the moment the consumer reaches the first dense sub-range, if all dense
responses have arrived: ≈ 10 × 32 MiB + 19 × 16 MiB ≈ **0.61 GiB** (band 0.35–0.8 GiB: S band, local share, arrival
fraction 0.7–1), of which ≈ 0.30 GB is response data. Plus the page in consumption (U4 holder, ≈ 25–40 MB). Baseline at
2 GiB (read-only, memtables empty): ≈ 0.25–0.35 GiB. **No contract capacity bounds the sum**: the cap allows 47
requests per query, each ≤ 5,000 rows of any size; implicit ceiling ≈ 128 NTR threads × 0.61 GiB ≈ 78 GiB here.
Replica bursts: per query each remote replica sends ≈ 19/2 × 10.39 ≈ **99 MB < 132 MiB** (no drop at Q = 1); at
Q ≥ 2 overlapping bursts can exceed it and drop responses (a dropped first-dense response makes that query hold
everything for 10 s and fail with `ReadTimeout`; drops are recorded, not prevented). Predicted smallest failing
concurrency at heap H with holding fraction f (share of a query's life spent in batch 2 with dense responses held,
f ≈ 0.6, band 0.4–1, rising under load as READ stages queue): Q_fail ≈ (H − 0.3 GiB − 0.1 GiB fragmentation) /
(f × 0.61 GiB): **2 GiB → 4 (band 3–6)**; 4 GiB → 10 (7–14); 8 GiB → 20 (14–30); 31,744 MiB → ≈ 80 (> 64; may be
beyond the reachable load, see stopping budget). Q = 1 at 2 GiB: peak ≈ 0.3 + 0.61 + 0.04 ≈ 0.95 GiB, **≈ 52 % margin**
(above the 30 % target): predicted safe.

**Workload and environment.**
- Node `pc91` only; work dir `/mydata/s4/C10/` (tree, conf templates, runs) and `/dev/shm/c10/` (node data,
  template). Do not touch `/mydata/s4/cassandra-base` beyond copying it.
- Schema: `CREATE KEYSPACE c10 WITH replication = {'class':'SimpleStrategy','replication_factor':1}`;
  `CREATE TABLE c10.t (pk bigint PRIMARY KEY, b int, v blob)` with default table options.
- **Ring and cold boundary** (after the ring forms, before loading): from `nodetool -p 7199 ring` (tokens and owners)
  compute the vnode ranges `(t_{i−1}, t_i]` owned by the owner of `t_i`, split the wrapping range at the minimum token,
  merge adjacent ranges with the same owner (never across the minimum token) → SR1…SRS in token order from
  −2^63; **T_hot = right bound of SR3**. Save `ring.txt`, `subranges.csv` (bounds, owner, vnode count) and
  `T_hot` in the run folder. Requirement: SR1–SR3 each hold ≥ 1 row and every dense SR has ≥ 5,000 rows (else record
  the smaller response sizes).
- Data: **N = 1,000,000 rows**, `pk` 0…N−1, `v` = 2,048 bytes from `Random(pk)`, `b = 1` if Murmur3 token(pk) > T_hot
  else 0 (token computed in the client with `org.apache.cassandra.utils.MurmurHash.hash3_x64_128` on the 8-byte
  big-endian key, seed 0, `hash[0]` with `Long.MIN_VALUE` → `Long.MAX_VALUE`, as `Murmur3Partitioner`; verify on 20
  keys against `SELECT token(pk)`). ≈ 2.1 GB of values, ≈ 0.7 GB per node; ≈ 9 % of rows cold (SR1–SR3).
- **LOAD** (lifetime, not a reading; all three nodes heap 8G): start node 1, wait for CQL; start node 2, wait `UN`;
  start node 3, wait `UN` (default bootstrap of empty nodes; if it fails, `auto_bootstrap: false` as an environment
  deviation); ring → `T_hot`; schema; load at 64 concurrent async inserts (CL ONE, node 1 coordinator);
  `nodetool flush c10` on each; record `nodetool tablestats c10.t` (rows/keys per node); `nodetool drain` and SIGTERM
  each; `cp -a /dev/shm/c10/node<i> /dev/shm/c10/template<i>` with `saved_caches/*` removed. **Every measured lifetime
  starts from a fresh `cp -a` of the three templates** (same ring, data, sstables).
- Lifetime start (measured): node 1 first with its arm's heap, then nodes 2/3 together (8G); ready = CQL listening on
  all three and `nodetool status` shows 3 × `UN` from node 1; then 30 s idle.
- **Client** `C10Load.java`, adapted from U4's `U4Load.java`
  ([`../cql-row-limit--wide-row-default-pages/harness/`](../cql-row-limit--wide-row-default-pages/harness/)): Java
  driver 3.12.1 (shaded jar in `tree/build/lib/jars`), protocol **v4**, `WhiteListPolicy` → `127.0.0.1:9042` only,
  8 connections, CL ONE, driver read timeout 60 s, prepared statements:
  - **test** `SELECT * FROM c10.t WHERE b = 1 ALLOW FILTERING`;
  - **control M** `SELECT * FROM c10.t WHERE b >= 0 ALLOW FILTERING` (same filtering path, matches every row, so SR1
    fills the page in batch 1);
  fetch size **5,000** (driver default, set explicitly); closed loop of Q workers, each executes, reads **only the
  first page** (`getAvailableWithoutFetching`), counts rows and value bytes, drops them, repeats; steps `Q:secs`
  (U4 format); per-second CSV: pages done, rows/page, MB/s, in flight, errors by class (`ReadTimeout`,
  `ReadFailure`, `Unavailable`, `OperationTimedOut`, other). Client JVM `-Xmx16g`, own scope (`MemoryMax=40G`).
  Subcommands `load`, `ring` (T_hot), `trace` (one traced test query, printing trace events), `run`.
- **Arms and lifetimes** (node 1 heap / direct; Q = concurrent client workers):

| Label | Arm | Node-1 heap / direct | Query | Steps (`Q:secs`) | Reps |
|---|---|---|---|---|---|
| `LOAD` (not a reading) | — | 8G (all nodes) | — | load | 1 |
| `IC` instrument check (not a reading) | A | 2G / auto | test, traced | `trace` ×3, then `1:30` | 1 |
| `CAL-2G` calibration sweep | A | 2G / auto | test | `1:60,2:60,3:60,4:60,6:60,8:60,12:60,16:60` (stop at first OOM) | 1 |
| `T-2G-1..3` test | A | 2G / auto | test | `1:20,<Q_T>:160` | 3 |
| `L-2G-1..3` matched control (component alone) | A | 2G / auto | test | `1:180` | 3 |
| `M-2G-1..3` matched control (no fan-out) | A | 2G / auto | control M | `1:20,<Q_T>:160` | 3 |
| `I-2G-1..3` intervention | **I** | 2G / auto | test | `1:20,<Q_T>:160` | 3 |
| `CAL-4G` budget search | A | 4G / auto | test | `4:60,6:60,8:60,12:60,16:60,24:60,32:60` | 1 |
| `CAL-8G` | A | 8G / auto | test | `8:60,12:60,16:60,24:60,32:60,48:60,64:60` | 1 |
| `CAL-auto` (optional) | A | auto / auto | test | `16:60,32:60,48:60,64:60,96:60,120:60` | 1 |
| `I4-2G` (optional) | I with cap 4 | 2G / auto | test | `1:20,<Q_T>:160` | 1 |

  Arm **A** = shipped defaults (plus the environment deviations). Arm **I** = A plus
  `-Dcassandra.max_concurrent_range_requests=1` on **node 1 only** (`JVM_EXTRA_OPTS`; static final, read at class
  init): every batch is one sub-range, so a query walks SR1, SR2, SR3 serially and holds at most one dense response.
  **Q_T** = the smallest Q at which `CAL-2G` reached an OOM (read the step from the sampler's NTR-active count at the
  last valid sample, not from timestamps alone; U4 A3). If `CAL-2G` survives Q = 16, run `CAL-2G-x`
  `24:60,32:60,48:60,64:60` before deciding.

**Harness** (stage 2 builds it under `harness/`; adapt U4's verified harness, same driver and samplers):
1. `setup.sh`: `mkdir -p /mydata/s4/C10 /dev/shm/c10`; `cp -a /mydata/s4/cassandra-base /mydata/s4/C10/tree`;
   pristine `conf` copy; per-instance conf dirs `conf1..3` (yaml: addresses, seeds, `cluster_name`, data dirs under
   `/dev/shm/c10/node<i>/`; `cassandra-env.sh`: `JMX_PORT` 7199/7299/7399); compile client and sampler into
   `/mydata/s4/C10/cls`. Save `yaml.diff` per instance against the shipped file.
2. `ring-ctl.sh start|stop <label> <arm> <heap1>`: refuse if any `CassandraDaemon` runs; per lifetime
   `rm -rf /dev/shm/c10/node<i> && cp -a /dev/shm/c10/template<i> /dev/shm/c10/node<i>`; launch each instance as
   `( setsid nohup taskset -c <cpus> systemd-run --user --scope --unit=c10-<label>-n<i> -p MemoryMax=… -p MemorySwapMax=0
   env CASSANDRA_CONF=… CASSANDRA_LOG_DIR=… MAX_HEAP_SIZE=… CASSANDRA_HEAPDUMP_DIR=<run dir> JVM_EXTRA_OPTS="…"
   bin/cassandra -f < /dev/null > … 2>&1 & )`; node 1 `JVM_EXTRA_OPTS` adds
   `-XX:NativeMemoryTracking=summary -Xlog:gc*=info,safepoint=info:file=<run>/gc-n1.log:time,uptime,level,tags`;
   stop with `nodetool -h 127.0.0.1 -p <jmx> drain` then SIGTERM by PID (match `java` + conf dir), confirm with a
   ≤ 60 s `pgrep` retry. Save `run.meta` (label, arm, heaps, resolved `-Xmx`/`MaxDirectMemorySize` per node from `ps`,
   `nproc` under each pin, jar sha256, `T_hot`, S).
3. `C10Load.java` as above; `C2Sampler.java` unchanged on node 1 (JMX 127.0.0.1:7199, 1 s: heap used, G1 old-gen
   post-GC usage, NTR and ReadStage active/pending, direct `java.nio`), extended with
   `org.apache.cassandra.metrics:type=ClientRangeRequest,scope=RangeSlice,name=RoundTrips` (count, mean, max) and
   `…,name=Timeouts` / `Unavailables`.
4. `run-arm.sh <label> <arm> <heap1> <query> <steps>`: start ring, sampler, run client; every 10 s on node 1
   `jcmd VM.native_memory summary` and `RssAnon`; every 10 s on nodes 2/3 the JMX meters
   `org.apache.cassandra.metrics:type=Connection,scope=127.0.0.1_7000,name=LargeMessageDroppedTasksDueToOverload`
   (and `…DueToTimeout`), or `nodetool -p <jmx> netstats` if the MBean name differs; at the end `grep -c "overloaded;
   dropping"` in nodes 2/3 logs; on client exit or node-1 JVM death record the outcome (first `OutOfMemoryError` with
   thread and stack from `stdout`/`system.log`, hprof present, scope `memory.events` for all three); copy small files
   to `logs/<label>/`; raw logs and hprofs stay in `pc91:/mydata/s4/C10/runs/<label>/`. Launch each lifetime as a
   background job and poll with bounded waits.
5. `gcwin.py`, `hprofhist.py`, `hprofstacks.py`, `summarize.py`, `steps.py` from U4; `hprofhist.py` buckets:
   `byte[]` of 10.0–10.8 MB (remote responses), `byte[]` of capacity 16,777,216 B (local `DataOutputBuffer`
   arrays), `byte[]` of 2,048 ± 16 B (page value copies; count ÷ 5,000 = pages being built), plus counts of
   `ReadResponse$RemoteDataResponse`, `ReadResponse$LocalDataResponse`, `SingleRangeResponse`, `DataResolver`.

**Instruments (U independent of K).** K = requests per batch and batches per query (trace "Submitting range requests
on 48 ranges with a concurrency of 1", "Didn't get any response rows; new concurrent requests: N", "Submitted M
concurrent range requests"; RoundTrips histogram: test 2, M 1, I ≈ 4) and rows per page (client = 5,000). U = node 1
heap held by responses: (a) G1 old-gen post-GC usage and heap used (1 s JMX); (b) at an OOM, the hprof: counts and
bytes of the response buckets and of `SingleRangeResponse`/`DataResolver` instances (÷ D ≈ queries holding),
request-thread stacks blocked in `ReadCallback.awaitResults` / `SingleRangeResponse.computeNext`; (c) in each
surviving `L`, `M`, `I` lifetime one `jcmd <pid> GC.class_histogram` at load second 120 (same buckets; intrusive,
once); (d) GC log → STW share per 60 s window (`gcwin.py`) and humongous allocation counts; (e) NTR/ReadStage active
(load reached Q), client pages/s and errors; (f) replica drops (nodes 2/3 meters and log lines); (g) NMT and `RssAnon`
every 10 s, direct `java.nio` for the ledger. **IC checks** (stop and fix the harness if any fails): the traced test
query shows concurrency 1 then "new concurrent requests: 47 − (vnodes of SR1 − 1)" and "Submitted S − 1"; the client
gets 5,000 rows whose `pk` tokens all lie in SR4; M's trace shows one batch; one response ≈ 10.39 MB (node 1
`InboundConnection`/`ReceivedBytes` delta for one query ≈ remote dense responses × r).

**Predicted response.**
- `IC`: as the checks above; RoundTrips 2; a single query brings ≈ D × 10.39 ≈ 0.30 GB to node 1; no drops.
- `CAL-2G`: survives Q = 1–2 (Q = 2–3 with heavy GC, old post-GC rising ≈ 0.35–0.6 GiB per added Q); **Java heap OOM
  at Q = 4** (band 3–6) within its 60 s step; drops on nodes 2/3 appear from Q ≈ 2–3; some `ReadTimeout`s.
- `T-2G` ×3: Java heap OOM **3/3** within 160 s at Q_T. First error `java.lang.OutOfMemoryError: Java heap space` on a
  thread allocating a response array (internode deserialization `ByteBufferUtil.read` for remote, or
  `DataOutputBuffer` growth on a READ thread for local) or on a request thread building the page; hprof holds
  ≥ (Q_T − 1) × D × 0.7 response arrays in the buckets (≥ 60 at Q_T = 4) and ≥ Q_T − 1 `SingleRangeResponse` sets.
- `L-2G` ×3 (Q = 1): survives **0/3 OOM**; old post-GC peak ≤ 1.1 GiB; histogram at 120 s shows ≤ D response arrays.
- `M-2G` ×3 (control query, Q_T): survives **0/3 OOM**; RoundTrips 1; held ≤ Q_T × (1 response + 1 page) ≈ 0.2 GiB
  above baseline; STW < 50 %. Pages/s higher than T (no cold scans).
- `I-2G` ×3 (cap 1, Q_T): survives **0/3 OOM**; RoundTrips ≈ 4; held ≤ Q_T × 1 dense response; pages/s lower than T
  (serial cold scans; recorded so a throughput collapse is not mistaken for protection: the cap stops the fan-out, not
  useful work, since every query still returns its 5,000 rows).
- Budget search: OOM near the predicted Q bands; largest failing heap predicted **≥ 8 GiB** (Q ≈ 20); `CAL-auto`
  possibly survives Q ≤ 120 if replica drops and READ-stage queueing cap the arrival rate (that heap is then the
  boundary, not a negative).
- Direct stays far below its limit; no scope `oom_kill`; nodes 2/3 never OOM.

**Stopping budget and time plan** (all times EST; pc91 shows MST = EST − 2 h). Stage 2 runs ≈ **09:00–14:00 EST**;
**no lifetime starts after 13:15**, every process stopped by **13:35**, §3–§4 written by **14:00**. Planned from S =
09:00: harness + IC-ready configs → 09:45; `LOAD` + templates → 10:10; `IC` → 10:20; `CAL-2G` (≤ 10 min) → 10:35;
`T-2G` ×3 (≈ 6 min each incl. ring start) → 10:55; `L-2G` ×3 → 11:15; `M-2G` ×3 → 11:35; `I-2G` ×3 → 11:55;
`CAL-4G` → 12:10; `CAL-8G` → 12:25; `CAL-auto` (heap dump ≈ 31 GB on spinning disk; skip if it cannot end by 13:15)
→ 12:50; `I4-2G` and extra repeats if time remains. Per lifetime: ring ready ≤ 180 s (else invalid, retry once);
load ≤ 180 s (T/L/M/I), ≤ 8 × 60 s (sweeps), each sweep stops at its first OOM; client read timeout 60 s. No
escalation after an OOM beyond the planned list. **Drop order** if late: `I4-2G` → `CAL-auto` → `CAL-8G` → `M-2G`
down to 1 run (L ×3 stays as V2's control) → `CAL-4G`. `T`, `L` and `I` ×3 are not dropped; if they cannot all run,
the verdict is `retry` with the reason.

**Controls and intervention.**
- **Matched control `L-2G` ×3 (component alone, V2):** same build, budget, data, ring, client; one worker. Shows one
  query's fan-out alone stays within the 2 GiB heap (≈ 52 % margin predicted).
- **Matched control `M-2G` ×3 (no fan-out):** same Q_T, page size, rows, filtering path; the predicate matches in SR1,
  so batch 1 fills the page and no burst is sent. Separates the fan-out holder from U4's per-page holder.
- **Intervention `I-2G` ×3:** the T workload with the constraint under test bounded (`max_concurrent_range_requests=1`
  on the coordinator). Removing the OOM attributes it to the fan-out. Throughput and errors recorded per arm.

**Verdict rules (stated before readings).**
- **true positive:** `T-2G` heap OOM in ≥ 3 runs (n/N stated; if 2/3, up to 2 more), `L-2G` 0/3, `I-2G` 0/3 (and
  `M-2G` 0/n), and the dump shows the claimed holder (response arrays of ≈ r and/or 16 MiB-capacity local buffers held
  by `SingleRangeResponse`/`DataResolver` of ≥ 2 queries) → `verified-OOM · deployment`, convergence (multiplicity),
  largest failing heap from the search. If L also OOMs (one query alone exceeds 2 GiB), the 2 GiB result is
  re-labelled at the next budget where L survives (rerun T/L/I there if time), else `retry`.
- **retry:** OOM only through a holder other than the responses (e.g. client-page build, Netty direct); OOM whose
  dump shows the responses were mostly retained by 10 s drop timeouts *and* the same Q without drops survives (a
  replica-drop artefact, to redesign with smaller responses); service loss (≥ 90 % STW over ≥ 60 s) without OOM
  (`verified-gap`); OOM in < 3 runs after 5; time ran out before V1/V2/V4; IC checks failed and could not be fixed.
- **false positive:** `CAL-2G` and `CAL-2G-x` reach Q = 64 with NTR active ≥ Q and RoundTrips 2 (fan-out reached), old
  post-GC stays below 90 % of the heap with no OOM, and the measured held set per query shows why (e.g. responses do
  not overlap across queries), with no named factor (Q, cold SR count, row size up to the 128 MiB message cap) left
  untried.
- **invalid lifetime:** replica (node 2/3) or client JVM OOM, scope `oom_kill`, ring not 3 × `UN`, rows per page
  ≠ 5,000, RoundTrips ≠ the arm's value, workload not started; fix, rerun, record as a deviation.
- Cleanup: stop every process started; remove `/dev/shm/c10/` (RAM) at the end; keep `/mydata/s4/C10/runs/` (raw logs,
  hprofs) and say what is left. Nothing in `/mydata/s4/cassandra-base` is changed.

`sha256 of §1–§2 at freeze: 547b882022f0df0f4c39f6c25e9bef6330e82cbdd3386b8a432e24c081aa8861` · computed over the lines from `## 1. Candidate` through the line before this one (`sed -n '/^## 1\. Candidate/,/^`sha256 of §1–§2 at freeze/p' <file> | sed '$d' | sha256sum`) · amendments after the freeze: dated, with reason, below this line.

## 3. Runs (stage 2)

**Session.** Stage-2 OOM agent (fresh session, Claude Opus 5.5), 2026-11-21 08:15–10:15 EST (pc91 clock MST = EST − 2 h).
Freeze hash re-computed before any run with the command in §2's last line: `547b8820…aa8861`, **matches**. No
amendment to the design was needed; deviations from the written design are listed below (none changes a constraint,
budget, workload, arm or verdict rule).

**Environment (as run).** `pc91` (node0.jason92-326665, x86_64, 32 cores, 125 GiB RAM, 8 GiB swap unused by the
measured scopes, Ubuntu 22.04, kernel 5.15.0, cgroup v2), JDK 11.0.33 (OpenJDK, Ubuntu build), G1 with
`G1HeapRegionSize=16m` from the shipped options. Build: `/mydata/s4/cassandra-base` copied to `/mydata/s4/c10/tree`
(jar sha256 `570b5249…0176e`, unchanged, never rebuilt). Before the first run: no `CassandraDaemon`, `/mydata/s4/`
held only `cassandra-base`, `/dev/shm` empty, load 0.00. Resolved per lifetime (`run.meta` in every `logs/<label>/`):
node 1 `-Xms2G -Xmx2G -XX:MaxDirectMemorySize=15872M` (2 GiB arms; 4G / 8G arms the same direct value), `nproc` under
the pin = **16** → `max_concurrent_range_requests` default = 160, bound by the 49 − 1 = 48 vnode ranges left (trace:
"new concurrent requests: 48"); nodes 2/3 `-Xmx8G`, direct 15872M, `nproc` 8 / 6. Config diff per instance: only
`cluster_name`, `listen_address`/`rpc_address` (127.0.0.1/.2/.3), the five data directories (tmpfs) and `JMX_PORT`
(7199/7299/7399) (`logs/*/n1.yaml.diff`, `n1.env.diff`). Arm I / I4 add only `-Dcassandra.max_concurrent_range_requests=1`
/ `=4` on node 1 (seen on the command line, `run.meta`). Scopes: `MemoryMax` = heap + 15,872 MiB + 8 GiB,
`MemorySwapMax=0`; `memory.events` `oom 0 oom_kill 0` for every scope read (`logs/*/memory.events.last`; node 1's scope
is gone after a JVM death, the death is the JVM's own `-XX:OnOutOfMemoryError=kill -9`).

**Harness** (`harness/`): `setup.sh`, `ring-ctl.sh` (3-instance ring, `taskset` pins 0–15 / 16–23 / 24–29, client and
sampler on 30–31), `load-data.sh`, `ringcalc.py` (merged sub-ranges, T_hot), `C10Load.java` (schema / load / tokcheck /
trace / run), `C10Sampler.java` (1 s JMX on node 1), `run-arm.sh` (one lifetime), `client.sh`, `queue1-3.sh` (the
lifetimes in order), `hprof-read.sh` + `hprofhist.py` (C10 buckets) + `hprofstacks.py`, `steps.py`, `gcwin.py` (U4's,
glob `gc*.log*`). Raw data: `pc91:/mydata/s4/c10/runs/<label>/` (per node `n<i>/logs/system.log`, `stdout.log`,
node-1 `gc.log`, `samples.csv`, `client.csv`, `readings.csv`, `netstats.txt`); small copies in `logs/<label>/`.

**Deviations from the written design (environment / procedure; no constraint, budget or arm changed).**
1. Work directory `/mydata/s4/c10/` (lower case, as the session instruction names it) instead of `/mydata/s4/C10/`.
2. **First ring lost (08:29 EST).** The first `LOAD` (08:20–08:25) and `IC` (08:25–08:29) completed, then
   `systemd-logind` stopped the user manager once no SSH session of the user remained (journal 06:29:20 MST "Exit the
   Session") and its `RemoveIPC` emptied `/dev/shm` (the templates). Enabling linger was refused by the session's
   permission policy, so the session instead held one self-bounded SSH session open on pc91 for the rest of the work
   (a loop ending at a stop file or 21,000 s). `LOAD` and `IC` were then redone from empty directories (08:34–08:43);
   the first ring's files are kept as `runs/LOAD-ring1-wiped`, `runs/IC-ring1-wiped`, excerpt `logs/IC-ring1-pilot/`
   (not a reading; it showed the same trace shape: 49 ranges, concurrency 1 → 48 → "Submitted 45"). Every reading below
   is on the second ring.
3. The design expected 48 vnode ranges; a full scan splits the ring into **49** ranges (the last, `(t_47, MIN]`, is
   separate), so the trace reads "on 49 ranges" and "new concurrent requests: 48" (= 49 − 1 vnode of SR1). Same
   mechanism; `ringcalc.py` follows it.
4. **S = 46** merged sub-ranges (design band 24–40): `allocate_tokens_for_local_replication_factor: 3` interleaves the
   three owners, so few adjacent ranges merge. D = 43 dense (15 local to node 1, 12 on node 2, 16 on node 3).
5. Control **M uses two batches of one sub-range** (RoundTrips 2, not 1): SR1 holds 4,783 rows (< 5,000), so the
   page is completed from SR2 in a second batch whose concurrency is computed from the rows seen (1). No fan-out: the
   trace shows "Submitted 1 concurrent range requests" twice (`logs/IC/trace-M.txt`). M still separates the fan-out
   holder from the page holder as designed.
6. The 120 s histogram is taken in L, M, I (and I4) lifetimes only, at 120 s as designed; T lifetimes died first.
7. JMX bean for RoundTrips is `type=ClientRequest,scope=RangeSlice,name=RoundTripsPerReadHistogram` (the design guessed
   `type=ClientRangeRequest`); the sampler was fixed after the first-ring IC, before any reading.

**LOAD (not a reading), 08:34–08:40 EST.** Ring formed by default bootstrap (`3 x UN`), tokens from
`nodetool ring` → `logs/../` `runs/LOAD/ring.txt`, `subranges.csv`: 49 vnode ranges, **S = 46**, SR1 1 vnode;
SR1–SR3 (owners n1, n2, n1) hold an expected 4,783 / 30,134 / 22,307 rows; dense sub-ranges 12,664–51,991 rows each
(all ≥ 5,000); SR4 (the first dense) is on node 2; **T_hot = −8,167,769,604,769,451,402**. Load: 1,000,000 rows,
`b = 1` for 942,355, `b = 0` for 57,645, 0 errors; token check 20/20 client = server. Flushed; partitions per node
326,993 / 315,206 / 355,296; templates 656 / 638 / 716 MB on tmpfs.

**IC (instrument check, not a reading), 08:40–08:43, 2 GiB.** All checks passed:
- traced test query ×3: "Submitting range requests on 49 ranges with a concurrency of 1 (18381.6 rows per range
  expected)" → "Submitted 1" → "Didn't get any response rows; new concurrent requests: 48" → "Submitted **45**
  concurrent range requests" (= S − 1); 5,000 rows, value bytes 10,240,000, all row tokens in SR4
  (−8,167,767,072,588,956,586 … −8,075,889,488,795,309,970); 0.6–2.1 s per query (`logs/IC/trace-test.txt`).
- M: one sub-range per batch, two batches (deviation 5).
- Q = 1 for 30 s: 47 pages of 5,000 rows, 0 errors, RoundTrips max 2; node 3 dropped 28 large messages
  (`netstats`), node 2 none.
- Response sizes (from the dumps below, not from `ReceivedBytes`): a remote 5,000-row response is a `byte[]` of
  **10.41 MB**; a local one is a `DataOutputBuffer` array of **17.06 MB** (its growth is not pure doubling) — a
  humongous object spanning **two 16 MiB G1 regions**, as the design estimated; 8.53 MB arrays are the predecessor
  during growth.

**Readings** (node 1; `pages/s` = client first pages per second; drops = large messages dropped by node 2 / node 3
outbound over the lifetime, `netstats`; old post-GC is the G1 old-gen `CollectionUsage` from JMX).

| Label | Arm / heap | Query, steps | Outcome | Key readings |
|---|---|---|---|---|
| `CAL-2G` | A / 2G | test, 1→16 | **heap OOM at Q = 3** (+128 s, 8 s into Q = 3) | Q 1: 1.68 pages/s, 0 err; Q 2: 1.52 pages/s, 4 `ReadTimeout`; drops 106 / 693; 117 full GCs, max STW 27 %/60 s |
| `T-2G-1` | A / 2G | test, `1:20,3:160` | **heap OOM**, +31 s (Q = 3) | first pages stop when Q = 3 starts; 0 `ReadTimeout` before death; drops 23 / 210 |
| `T-2G-2` | A / 2G | same | **heap OOM**, +32 s (Q = 3, NTR active 3) | 0 `ReadTimeout`; drops 18 / 135 |
| `T-2G-3` | A / 2G | same | **heap OOM**, +31 s (Q = 3, NTR active 3) | 0 `ReadTimeout`; drops 27 / 241 |
| `L-2G-1` | A / 2G | test, `1:180` | survived | 291 pages, 0 err; heap max 1,896 MiB, old post-GC max 1,807 MiB; 73 full GCs, STW max 24 %/60 s; histogram @120 s `byte[]` 165 MB; drops 0 / 1,530 |
| `L-2G-2` | A / 2G | same | survived | 279 pages, 0 err; old post-GC max 1,815 MiB; 104 full GCs, 24 %; `byte[]` 557 MB @120 s; drops 0 / 381 |
| `L-2G-3` | A / 2G | same | survived | 299 pages, 0 err; old post-GC max 1,770 MiB; 90 full GCs, 24 %; `byte[]` 163 MB @120 s; drops 0 / 948 |
| `M-2G-1` | A / 2G | M, `1:20,3:160` | survived | 1,968 pages (11.9/s at Q 3), 0 err, RoundTrips 2; old post-GC max 1,879 MiB; 27 full GCs, 10 %; `byte[]` 73 MB @120 s; drops 0 / 0 |
| `M-2G-2` | A / 2G | same | survived | 2,044 pages (12.3/s), 0 err; 29 full GCs, 10 %; `byte[]` 72 MB; drops 0 / 0 |
| `M-2G-3` | A / 2G | same | survived | 2,059 pages (12.4/s), 0 err; 31 full GCs, 10 %; `byte[]` 50 MB; drops 0 / 0 |
| `I-2G-1` | **I** (cap 1) / 2G | test, `1:20,3:160` | survived | 896 pages (5.39/s at Q 3), 0 err, **RoundTrips 4**; heap max 1,516 MiB, old post-GC max 88 MiB; 1 full GC, 2 %; `byte[]` 42 MB; drops 0 / 0 |
| `I-2G-2` | I / 2G | same | survived | 889 pages (5.35/s), 0 err; old post-GC max 101 MiB; 1 full GC; `byte[]` 49 MB; drops 0 / 0 |
| `I-2G-3` | I / 2G | same | survived | 915 pages (5.51/s), 0 err; old post-GC max 77 MiB; 1 full GC; `byte[]` 31 MB; drops 0 / 0 |
| `CAL-4G` | A / 4G | test, 4→32 | **heap OOM at Q = 6** (+67 s, 7 s into Q = 6) | Q 4: 1.76 pages/s, 13 `ReadTimeout`/60 s; drops 184 / 733; 11 full GCs, 17 % |
| `CAL-8G` | A / 8G | test, 8→64 | **heap OOM at Q = 16** (+140 s, 20 s into Q = 16) | Q 8: 1.68 pages/s, 34 `ReadTimeout`; Q 12: 0.75 pages/s, 59 errors; drops 1,366 / 2,693; 3 full GCs, 19 % |
| `I4-2G` (optional) | I4 (cap 4) / 2G | test, `1:20,3:160` | survived | 1,563 pages (9.37/s at Q 3), 0 err, RoundTrips 2; old post-GC max 126 MiB; 1 full GC, 3 %; drops 0 / 0 |
| `CAL-auto` (optional) | A / auto | test, 16→120 | survived to Q = 120 (**boundary**) | heap `-Xmx31744M`; Q 16: 1.42 pages/s, 74 errors/60 s, heap max 31,529 MiB, old post-GC max 30,297 MiB; Q 32–120: 0.02–0.25 pages/s, almost every query `ReadTimeout` (2,222 of 2,345 over the lifetime); drops 6,184 / 6,534; 0 full GCs, STW max 20 %/60 s; no OOM |

No lifetime was invalid: every ring started `3 x UN` on the first try, rows per page 5,000 in every arm, RoundTrips
as the arm predicts (test 2, I 4, M 2 per deviation 5, I4 2), no replica OOM (`java.lang.OutOfMemoryError` absent from
nodes 2/3 logs), no scope `oom`/`oom_kill`. No lifetime met the service-loss criterion (max STW share 2–27 % per 60 s).

**Initiating failure and dumps (V5).** Every OOM is `java.lang.OutOfMemoryError: Java heap space` on node 1. The
first error (CAL-2G `system.log`, `ERROR [ReadStage-6] … JVMStabilityInspector … Exception in thread
Thread[ReadStage-6,10,SharedPool]`) is thrown in `DataOutputBuffer.expandToFit` ← `UnfilteredRowIteratorSerializer.serialize`
← `ReadResponse$LocalDataResponse.build(ReadResponse.java:201)` ← `ReadResponse.createDataResponse` ←
`ReadCommand.createResponse`: a READ-stage thread building a **local sub-range response** (`logs/CAL-2G/oom-excerpt.txt`).
In the T lifetimes the JVM's `kill -9` ran before the log line; the dump's own stack of the throwing thread
(`OutOfMemoryError.<init>` ← `HeapByteBuffer.<init>` ← … ← `DataOutputBuffer.expandToFit`) is the same in T-2G-1/2/3,
CAL-4G and CAL-8G (`hprofstacks.py`). Dumps (shallow sizes from `hprofhist.py`; `logs/<label>/hprofhist.txt`,
`stacks-summary.txt`):

| Dump | Shallow heap | `byte[]` ≥ 8 MB (responses) | of which local 17.06 MB / remote 10.41 MB / growing 8.53 MB | `RangeCommandIterator` (queries) | `SingleRangeResponse` | request threads in `ReadCallback.awaitResults` |
|---|---|---|---|---|---|---|
| CAL-2G (Q 3) | 1,147 MiB | 65 = **903 MiB (79 %)** | 42 / 18 / 5 | 3 | 135 (= 3 × 45) | 3 |
| T-2G-1 | 1,187 MiB | 68 = **936 MiB (79 %)** | 42 / 23 / 3 | 3 | 135 | 3 |
| T-2G-2 | 1,187 MiB | 68 = **951 MiB (80 %)** | 44 / 22 / 2 | 3 | 135 | 2 |
| T-2G-3 | 1,098 MiB | 63 = **877 MiB (80 %)** | 41 / 17 / 5 | 3 | 135 | 3 |
| CAL-4G (Q 6) | 2,744 MiB | 165 = **2,063 MiB (75 %)** | 72 / 75 / 18 | 6 | 270 | 6 |
| CAL-8G (Q 16) | 4,540 MiB | 272 = **4,090 MiB (90 %)** | 223 / 35 / 14 | 16 | 720 | 16 |

Each dump holds the claimed holder of every running query: one `SingleRangeResponse` per merged sub-range of batch 2
(45 per query) with its response array, all request threads blocked on a not-yet-consumed sub-range. The local
responses (15 per query, each a two-region humongous array) dominate: 42–44 at Q = 3 ≈ 1.3–1.4 GiB of regions on a
2 GiB heap, which is why the heap fills at ≈ 1.1–1.2 GiB of shallow live data (and 4.5 GiB of live data fills 8 GiB:
223 local arrays × 32 MiB ≈ 7 GiB of regions). Design threshold "≥ (Q_T − 1) × D × 0.7 response arrays" = 60 at
Q_T = 3: observed 63–68. Dumps were deleted after reading except the representative CAL-2G one
(`pc91:/mydata/s4/c10/runs/CAL-2G/n1/cassandra-1795268619-pid206273.hprof`, 1.23 GB).

**Replica drops.** As stage 4 found, a replica's burst to node 1 above ≈ 132 MiB is partly dropped: node 3 (16 dense
sub-ranges ≈ 166 MB per query) dropped in every test lifetime, node 2 (12 ≈ 125 MB) only under concurrency. A drop of a
sub-range the page does not need costs nothing (L: 0 errors with up to 1,530 drops); a drop of SR4 makes the query wait
10 s and fail with `ReadTimeout` (CAL-2G Q 2: 4; CAL-4G Q 4: 13; CAL-8G Q 8–12: 34 and 59). At 2 GiB the OOM does not
depend on these waits: in T-2G-1/2/3 the node died ≈ 4–5 s after Q = 3 started (first client connection errors) with **no** `ReadTimeout` before
death, and the dumps are dominated by local responses, which no replica drop touches. At 4G / 8G the drop waits lengthen
the holding time and are part of the observed Q boundary (recorded, not removed).

**Time line** (EST): setup 08:15–08:20; first LOAD/IC 08:20–08:29 (lost, deviation 2); LOAD 08:34–08:40; IC 08:40–08:43;
CAL-2G 08:44–08:48; T-2G ×3 08:49–08:59; L-2G ×3 08:59–09:15; M-2G ×3 09:15–09:31; I-2G ×3 09:31–09:47; CAL-4G
09:47–09:51; CAL-8G 09:51–09:56; I4-2G 09:57–10:02; CAL-auto 10:02–10:10. Nothing was dropped from the plan; every process was stopped by 10:11 and `/dev/shm/c10` emptied.

## 4. Conclusion (stage 2)

**Verdict: true positive.** Protocol status: **`verified-OOM · deployment`**, direction **convergence (multiplicity)**
with an unprotected-configuration element (the byte controls `read_thresholds_enabled` / `coordinator_read_size_*`
ship off). Endpoint: Java heap OOM on the coordinator.

| Condition | Status | n/N |
|---|---|---|
| 2 GiB heap, direct auto 15,872M, defaults, Q = 3 concurrent `ALLOW FILTERING` range reads (T-2G) | `verified-OOM · deployment` | 3/3 OOM (and CAL-2G 1/1 at Q = 3) |
| 4 GiB heap (CAL-4G) | OOM at Q = 6 (sweep, 1 run) | 1/1 |
| 8 GiB heap (CAL-8G) | OOM at Q = 16 (sweep, 1 run) — **largest failing heap tested** | 1/1 |
| auto heap 31,744 MiB (CAL-auto) | no OOM up to Q = 120; the replicas' drops turn almost every query into a 10 s `ReadTimeout` from Q = 32, which caps the held set (boundary, not a negative) | 0/1 |

| Item | Evidence |
|---|---|
| V1 Repetition | T-2G-1/2/3: heap OOM 3/3, each within ≈ 5 s of Q = 3 starting; CAL-2G also at Q = 3. |
| V2 Matched control | L-2G (same build/budget/data/ring, Q = 1): 0/3 OOM over 180 s, 0 errors. M-2G (same Q = 3, page size, filtering path, no fan-out): 0/3 OOM, 0 errors. |
| V3 Measurement | U from the dumps, independent of K: per query 45 `SingleRangeResponse`, 15 local 17.06 MB and up to 28 remote 10.41 MB arrays; at OOM 63–68 such arrays (877–951 MiB, 79–80 % of the shallow heap) for 3 queries at 2 GiB, 165 (2,063 MiB) for 6 at 4 GiB, 272 (4,090 MiB, 90 %) for 16 at 8 GiB. K = requests per batch (trace "Submitted 45"), RoundTrips 2. |
| V4 Intervention | I-2G (`max_concurrent_range_requests=1` on the coordinator, the same Q = 3 workload): 0/3 OOM, 0 errors, RoundTrips 4, old post-GC ≤ 101 MiB, 1 full GC; useful work continues (5.4 pages/s at Q = 3, vs ≈ 1.5–1.7 pages/s for the default arm at Q = 1–2). Optional I4-2G (cap 4): 1/1 survived, 9.4 pages/s. |
| V5 Initiating failure | `java.lang.OutOfMemoryError: Java heap space` on `ReadStage-6` in `DataOutputBuffer.expandToFit` ← `ReadResponse$LocalDataResponse.build` (CAL-2G `system.log`); the same throwing stack in every dump; dumps show the claimed holder (table in §3). |
| V6 Default constraints | `max_concurrent_range_requests` unset (resolved 160 with 16 CPUs; 48 sub-range requests sent), `num_tokens` 16, read thresholds off, page-size guardrail off, `concurrent_reads` 32, `native_transport_max_threads` 128, internode reserves 4/128/512 MiB, timeouts default. Only arm I/I4 changes the cap. |
| V7 Acceptable budget | 2 GiB heap (standing rule: ≥ 512 MiB meets V7; 2 GiB ideal), `MaxDirectMemorySize` auto-resolved 15,872M, no container limit. Upward search: OOM at 4 GiB and 8 GiB; the auto heap (31,744 MiB) did not OOM within Q ≤ 120. |

**Reason.** A paged `SELECT … WHERE b = 1 ALLOW FILTERING` whose first merged sub-range has no match makes the
coordinator jump from 1 to 48 sub-range requests in its second batch ("Didn't get any response rows; new concurrent
requests: 48" → "Submitted 45"), each carrying the full 5,000-row page limit, and keeps every response it has received
until the page is assembled and the batch is closed. Per query that is 15 local 17.06 MB response arrays (two 16 MiB G1
regions each) plus up to 28 remote 10.41 MB arrays ≈ 0.93 GiB of heap regions for one 10 MB page. The cap counts
requests per query, not bytes, and nothing sums across queries, so three concurrent such reads exhaust a 2 GiB heap
(3/3, within ≈ 5 s, dumps 79–80 % response arrays of 3 queries), while one alone (0/3), three without the fan-out (M,
0/3) or three with the cap set to 1 (I, 0/3, with higher throughput) survive; six reads exhaust 4 GiB and sixteen 8 GiB.
Root cause: `cassandra.max_concurrent_range_requests` (default 10 × cores) bounds the number of in-flight sub-range
requests per query, but each request's response size is bounded only by the row limit (any row size), the internode
receive reserve is released when the response is delivered (held responses are charged to nothing), no node-wide bound
covers the responses of concurrent range queries, and the byte thresholds that could abort them ship disabled.

**Limits of attribution and caveats.**
- **Control margin.** The JMX old-gen post-GC reading stays at 1.6–1.9 GiB in L *and* in M (M's live `byte[]` at
  120 s is only 50–73 MB): with G1 on a 2 GiB heap it reflects deferred reclamation of humongous regions, not live data,
  so it does not show the design's 30 % margin. The arithmetic does: one query holds ≈ 0.93 GiB of regions (S = 46, not
  the ≈ 32 the design assumed), i.e. ≈ 45 % of the heap, and L survived 3/3 over 180 s each (73–104 full GCs, STW ≤ 24 %).
  The margin is thinner than predicted (≈ 52 %); a 4 GiB T/L/I set was not run (it was not in the plan).
- **Replica drops.** Node 3's 16-response burst exceeds its outbound reserve, so some responses are dropped in every
  test lifetime; a dropped first-dense response turns a query into a 10 s `ReadTimeout`. At 2 GiB the OOM does not need
  that (no `ReadTimeout` before death in T-2G; local responses, which are never dropped, dominate the dumps). At 4–8 GiB
  the 10 s waits lengthen holding and lower the useful throughput, and at the auto heap they stop the queries before the
  held set fills 31 GiB. The OOM Q values above 2 GiB are therefore drop-influenced; the 2 GiB result is not.
- **Topology.** Three instances on one host at RF 1 stand in for "different replica sets for adjacent ranges"; the
  RF 3 / QUORUM and the 6-node sizing of OC-509, the unpaged variant and the Top-K route (§1 "Not covered") were not
  tested. The predicted Q_fail was 4 (band 3–6) at 2 GiB, 10 at 4 GiB and 20 at 8 GiB; observed 3, 6, 16 (the larger
  S = 46 and the two-region local arrays make each query heavier than modeled).
- **Pattern.** Covered by CP-2 (item count, not bytes), CP-7 (per-query cap × unbounded concurrent queries) and CP-3
  (internode reserve released at delivery while the response stays); no new clue pattern is needed.
- **Left on pc91:** `/mydata/s4/c10/` 3.2 GB (tree 419 MB; `runs/` 2.7 GB with raw logs and the one kept dump
  `runs/CAL-2G/n1/cassandra-1795268619-pid206273.hprof`, 1.23 GB); `/dev/shm/c10` removed; no process left
  (`pgrep CassandraDaemon|C10Load|C10Sampler` empty at 10:11 EST).
