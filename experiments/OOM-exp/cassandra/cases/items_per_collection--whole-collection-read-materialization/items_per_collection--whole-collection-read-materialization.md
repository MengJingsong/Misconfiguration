# U3 — items_per_collection: concurrent reads materialize appended collections whole on the heap  <!-- file: cassandra/cases/items_per_collection--whole-collection-read-materialization/items_per_collection--whole-collection-read-materialization.md -->

| Field | Value |
|---|---|
| Case ID | `U3` (U = unprotected-accumulation case; README "ID prefixes") |
| From | `OC-23` of the phase 1 OOM candidate list (campaign row U3 / P1) |
| Phase-1 case file | [`capacity-enforcement-exp/cassandra/stage3-ai-deep-read/cases/items_per_collection-doAdd-elements_size--autonomous.md`](../../../../capacity-enforcement-exp/cassandra/stage3-ai-deep-read/cases/items_per_collection-doAdd-elements_size--autonomous.md) |
| System / pinned source | Cassandra 5.0.9 (`systems/cassandra/source/`, `git describe` = `cassandra-5.0.9`; node build `pc99:/mydata/s4/cassandra-base`, release string `5.0.9-SNAPSHOT`) |
| Stage 1 (design) | OOM agent, phase 2 stage 1, Claude Opus 5.5 (`claude-opus-5-5`), 2026-11-17 (22:40–22:50 EST; frozen 22:50) |
| Stage 2 (verify) | OOM agent, phase 2 stage 2, Claude Opus 5.5 (`claude-opus-5-5`), fresh sessions: 2026-11-17 22:50 – 2026-11-18 ≈ 00:05 EST (cut off by an API usage limit), resumed 2026-11-18 02:54–03:45 EST |
| Verdict | **true positive** — `verified-OOM · deployment` (unprotected configuration + unprotected accumulation); largest failing heap 8 GiB (3/3) |

## Summary

- **Conclusion:** **true positive.** At shipped defaults and a 2 GiB heap, 16 clients each reading one of 8 appended `set<int>`s of
  10⁶ items drove Cassandra 5.0.9 to `java.lang.OutOfMemoryError: Java heap space` in **3/3** runs (10–14 s after the clients
  started; the shipped `kill -9` handler then killed the daemon), while the same bytes as one blob (3/3), the same items as a paged
  clustering table at the same c (3/3, same useful throughput as c = 8) and c = 8 (3/3) survived. The OOM repeats at 4 GiB (1/1) and
  **8 GiB (3/3, largest failing heap)** with M scaled to the heap; at 15872 MiB no OOM came within the 180 s window (0/3) but the node
  was in GC service loss (≥ 90 % STW) for the whole window. Enabling the 64 MiB read-size fail threshold (diagnostic) did not stop it
  (3/3 OOM). Conditional on an application that grows collections to 10⁶+ items and reads them concurrently — which the docs
  discourage but allow (limit 2·10⁹ items).
- **Root cause (measured):** no enabled control bounds the heap a read spends on one stored collection. `items_per_collection_fail_threshold`
  is off by default and counts only the written fragment, so appends grow a set without limit; every read deserializes the whole
  collection into one row on the replica (≈ 150 B per item: one `ArrayCell`, `CellPath`, `HeapByteBuffer` and `byte[]` per item —
  the dumps hold ≈ 15 such rows at the OOM), with no byte bound across reads: `concurrent_reads` (32) and the native-transport
  limits count reads or request bytes, and timed-out reads keep building (`ReadStage` Active up to 28–31 > c). The read-size
  threshold, off by default, is checked only after a row is built, too late for this memory.

## 1. Candidate

**Candidate row (phase 1 OOM candidate list, `capacity-enforcement-exp/cassandra/stage5-oom-clue-find/phase1-oom-candidates.md`), quoted:**

> | OC-23 | 2026-11-16 | `items_per_collection-doAdd-elements_size--autonomous` | legacy | [lead list, blind, E1; N15; queued as U3] The collection guardrail counts only the written fragment (and is off at defaults), so appends grow a stored collection without limit and a read builds it whole in one row on heap (≈ 200 B per item, estimate; read-size thresholds off): ≈ 10⁷ items ≈ 2 GB per read, × up to 32 concurrent reads. | CP-12, CP-2 | picked: U3 |

**Campaign row** (`cassandra/campaign-plan.md`, row U3 / P1, abridged): hypothesis "concurrent reads of large stored collections
exhaust the heap at defaults"; workload: partitions each holding a `set<int>` of M = 10⁶ items built by appends; c concurrent
`SELECT`s (c = 1…32), heap 2 GiB, then searched upward; matched control: the same serialized bytes as one blob column at the same c;
intervention: c capped or M bounded. Screening: keep; default arm = unprotected configuration (guardrail and read thresholds off).

**Phase-1 constraint and check.** `items_per_collection_fail_threshold` (default −1, `Config.java:920`; commented out in
`conf/cassandra.yaml:2168-2169`). The check, `Sets.java:396-399` (`Adder.doAdd`), guards `elements.size()` — the items of the
fragment being added — and the source comment says so: *"Guardrails about collection size are only checked for the added elements
without considering already existent elements"*. `collection_size_fail_threshold` (default null, `Config.java:917-918`) guards the
fragment's `dataSize` the same way (`Sets.java:400-409`). Guardrails are also skipped for superusers, and the default
`AllowAllAuthenticator` makes every client one (OC-10 / N8).

**Stage 4 (phase 1) — measured.** [Recheck results, pc99, 2026-11-17](../../../../capacity-enforcement-exp/cassandra/stage4-runtime-verification/results/items_per_collection-doAdd-elements_size--autonomous--recheck-2026-11-17.md),
outcome *confirmed — does not cap*: one `SELECT` of a `set<int>` grown by appends to M = 10⁵ / 10⁶ / 10⁷ items succeeds at defaults
and returns all M items; per item the node **allocates 334–352 B** and **holds 148–154 B** live while the coordinator holds the row
(1.53 GB held, 3.52 GB allocated at M = 10⁷), against 4.0 B per item on disk and 8 B serialized. The held objects at the pause were
`HeapByteBuffer`, `ArrayCell`, `byte[]`, `CellPath$SingleItemCellPath` (each ≈ M instances) and `Object[]`. The same 8,000,004 bytes
as one blob cost 0.115× (allocated) and 0.161× (held). With the guardrail at T = 5,000 and an ordinary role, 200 accepted appends grew
a set to 10⁶ items and its read cost the same. With `local_read_size_fail_threshold` = 64 MiB the 10⁶ and 10⁷ reads were rejected,
but the replica still allocated ≈ 150 B per item first (the check runs per row after the row is built). Three *sequential* 10⁷-item
reads at an 8 GiB heap already drove G1 to `To-space exhausted` and a full GC (`7898M->796M`). Concurrent reads were not tested.

**Documentation (by-design status).** The CQL docs say collections are "meant for storing/denormalizing relatively small amount of
data", that items expected to grow unbounded belong in a clustering table, and that "the whole collection has to be read (and reading
one is not paged internally)" (`doc/modules/cassandra/pages/developing/cql/types.adoc:216-227`); the collections page lists the
guard rails for non-frozen collections as "No more than 2 billion items in a collection" and "Collections are not paged internally"
(`doc/.../developing/cql/collections/collection-create.adoc:11-26`). So whole-collection reads are **documented behavior**; the sizes
used here (10⁶–8·10⁶ items of 4-byte ints) are inside the documented limit of 2·10⁹ items, and the guardrail designed to bound
collection size (CASSANDRA-17153) does not bound the stored size. The finding claimed is that no control keeps the heap of
concurrent reads of such collections within the heap budget at defaults; whether this is a configuration-sizing gap (guardrail off,
counts fragments) or accepted documented behavior is stated in §4.

**JIRA prior art (checked 2026-11-17, read only; nothing posted).**

| Query / source | Hits | Relevant |
|---|---|---|
| Survey `jira-oom-survey.csv` (604 rows), grep `collection\|set<\|list<\|map<` | 10 | CASSANDRA-5736 (*CQL3PagingRecordReader can OOM and kill nodes*, Duplicate; Hadoop reader on collections, cause not analysed); CASSANDRA-19959 (*OOM risks due to unbound growth in collections*, Unresolved; static analysis of Java collections, not CQL collections); 11846, 12618, 12769 (malformed collection values in inserts, Fixed; input bugs, different mechanism). No entry on reading large stored CQL collections. |
| REST `project=CASSANDRA AND text ~ "collection" AND (text ~ "OutOfMemoryError" OR text ~ "OOM")` | 149 | none on read materialization of a large stored collection (top 40 read) |
| REST `summary ~ "collection" AND (summary ~ large/big/huge/memory/heap)` | 3 | CASSANDRA-12623 *Performance impact for the big collection* (Open, 3.0.x: aggressive GC and high CPU when updating rows with ~10 MB collections of UDTs; write side, no OOM); 19959; 11108 (dtest) |
| REST `text ~ "large collection" AND (text ~ heap/GC/memory)` | 108 | CASSANDRA-6534 (slow inserts with collections into one partition, pathological GC, Duplicate); CASSANDRA-16896 (*Add soft/hard limits to local reads*, Fixed 4.1: the `local_read_size_*` thresholds, off by default); CASSANDRA-9754 (index info for large partitions, open). None reports an OOM from reading large collections. |
| REST `summary ~ "collection" AND summary ~ "paging"` | 1 | CASSANDRA-15201 (LegacyLayout paging state, Fixed 3.0.19; unrelated) |
| Earlier (campaign row, 2026-11-17) | — | 17153 (*Guardrails for collection items and size*, Fixed 4.1: the guardrail itself), 4304 (*bytes-limit clause*, Later), 21827 (cursor compaction AssertionError on an oversized static collection, not memory) |

**JIRA verdict: `new`** (no ticket reports or fixes a heap OOM from concurrent reads of large stored collections); the
whole-collection read itself is **`documented`** behavior (above). Not a known-fixed bug, so this is not a positive control.

## 2. Design solution (stage 1; frozen)

### 2.1 Mechanism

Direction: **unprotected accumulation** (no applicable control at defaults; the guardrail and the read-size thresholds are disabled
and, when on, do not bound this memory), with a concurrency multiplier. Technique notes used: `default-convergence-playbook.md`
(multiplicity dial at default capacities, geometric then refined) and `custom-convergence-playbook.md` (protection map, feasibility).

1. **Write side, unbounded growth.** `UPDATE t SET v = v + ? WHERE k = ?` adds cells without read-before-write; `Sets.Adder.doAdd`
   guards only the fragment (`Sets.java:396-409`) and both guardrails are off by default (`Config.java:917-920`). A partition's set
   therefore grows to any M ≤ 2·10⁹ by appends; on disk it costs ≈ 4 B per item (stage 4).
2. **Replica side, whole row.** A `SELECT v … WHERE k = ?` on a single node runs `StorageProxy.LocalReadRunnable`
   (`StorageProxy.java:2178-2211`; dispatched by `Stage.READ.maybeExecuteImmediately`, `AbstractReadExecutor.java:165`), bounded in
   count by `concurrent_reads` = 32. The sstable reader deserializes the complex column cell by cell into one row builder
   (`UnfilteredSerializer.java:680-688`, `builder.build()` at `:635`): M `ArrayCell` + M `CellPath` + their buffers ≈ 150 B per item.
   `LocalDataResponse` then serializes the partition into a buffer (`ReadResponse.java:182-194`). The read-size check, when enabled,
   adds `row.unsharedHeapSize()` only in `applyToRow` after the row exists (`ReadCommand.java:691-694`, `:709-722`); the timeout
   abort (`QueryCancelledException`) is also checked at row boundaries, so a timed-out read still builds its row.
3. **Coordinator side, whole row again.** The coordinator deserializes the response into a row (`ByteArrayAccessor`, ≈ 150 B per item,
   stage 4's held reading) and `SelectStatement.processPartition` hands it to `ResultSetBuilder.newRow` (`SelectStatement.java:1124-1126`),
   which serializes the set into one value (8 B per item + 4) that is encoded into the response. This runs on a
   Native-Transport-Requests thread (≤ `native_transport_max_threads` = 128).
4. **Multiplicity.** c clients each with one read in flight hold up to c rows (≈ 150 B × M each) at once; when reads exceed
   `read_request_timeout` (5 s) the coordinator gives up and the client retries, while the replica keeps building the abandoned row,
   so replica-side rows can exceed c (up to the 32 READ permits). Nothing counts these bytes: the request in-flight limits
   (`native_transport_max_request_data_in_flight`, heap/10) charge the ~100-byte request, not the response.

Predicted endpoint: **Java heap OOM** (`java.lang.OutOfMemoryError: Java heap space`) once overlapping rows exceed the free heap.

### 2.2 Protection map (fixed before any reading)

| Domain / control | Allocation and owner | Local contract (default) | Scope and multiplicity | Aggregate coverage | Lifetime | Budget |
|---|---|---|---|---|---|---|
| `items_per_collection_fail_threshold` | stored collection cells (memtable/sstable) | −1 = off; when on: items **of the written fragment** (`Sets.java:399`) | per write statement | none on stored size; skipped for superusers (default auth) | n/a on reads | — |
| `collection_size_fail_threshold` | same | null = off; when on: bytes of the fragment (`Sets.java:409`) | per write | none on stored size | n/a on reads | — |
| `read_thresholds_enabled` / `local_read_size_fail_threshold` (CASSANDRA-16896) | replica read row (`ReadCommand` size tracking) | `false` / null = off; when on: per-row `unsharedHeapSize` checked **after** the row is built | per read command | none across reads | until row built | heap |
| `concurrent_reads` | replica row builds on READ stage | 32 permits (count) | per node | bounds simultaneous replica executions; not bytes; queue unbounded (`DroppableRunnable` drops tasks queued past their deadline) | per read | heap |
| `native_transport_max_threads` | coordinator row + `ResultSetBuilder` value + encoded response | 128 threads (count) | per node | count only | per request | heap (+ Netty direct for the encoded frame) |
| `read_request_timeout` / `native_transport_timeout` | coordinator wait | 5 000 ms / 12 s | per request | time, not bytes; replica row still built after timeout | — | — |
| `native_transport_max_request_data_in_flight` (/`_per_ip`) | request bytes | heap/10 (/ heap/40) | per node (/ IP) | charges request size (~100 B per `SELECT`), not response or row | released at response | heap |
| Heap budget | everything above | `-Xmx` = H | per JVM | — | — | **the budget** |

**Claimed holder:** the per-read whole-collection row (replica and coordinator copies, plus the serialized set value), U measured by
the GC log (post-GC occupancy) and by a class histogram of the heap dump at OOM (cells per row = M). **K: none** — at defaults no
counter tracks these bytes (`LocalReadSize` metrics update only when read thresholds are enabled). Classification rule: OOM with
U ≫ any contract (there is none) = **unprotected configuration** (controls off by default) and **unprotected accumulation** (no
enabled control bounds the stored collection or the concurrent read heap).

### 2.3 Configuration and budget audit

| Item | Value in every arm unless stated | Label |
|---|---|---|
| Source / build | `pc99:/mydata/s4/cassandra-base` copied to `/mydata/s4/u3/cassandra` (`cp -a`); 5.0.9 | environment |
| Node | `pc99` (x86_64, 32 cores, 125 GiB RAM, 8 GiB swap on, `/mydata` 714 GiB free, Ubuntu 22.04, kernel 5.15, cgroup v2; checked read-only 2026-11-17 22:43 EST: idle, no Cassandra or Java running, load 0.00) | environment |
| JDK / GC | OpenJDK 11.0.33; shipped `jvm11-server.options`: G1 (`:63`), `G1HeapRegionSize=16m` (`:66`), `MaxGCPauseMillis=300` (`:79`); `jvm-server.options`: `-XX:+HeapDumpOnOutOfMemoryError` (`:120`), `-XX:+AlwaysPreTouch` (`:128`); `cassandra-env.sh`: `-XX:OnOutOfMemoryError=kill -9 %p` (`:209`), `HeapDumpPath=$CASSANDRA_HEAPDUMP_DIR` (`:197-200`) | shipped |
| Heap (budget) | `MAX_HEAP_SIZE` = 2G (main condition), 4G, 8G; unset for the 15872M step (cassandra-env resolves min(½ RAM, 15872 MiB) = 15872M on pc99) | **budget: explicit deployment heap** |
| Direct memory | not set: cassandra-env resolves `MaxDirectMemorySize` = 7936M on pc99 even with a hand-set heap (heap_limit/2, `cassandra-env.sh:60-62`, `:150-158`); record from `JVM Arguments` in `system.log` | resolved default |
| Container | a **guard only**, not the budget: `systemd-run --user --scope -p MemoryMax=<H+14G> -p MemorySwapMax=0` (16G, 18G, 22G, 30G); swap 0 for the measured process. The guard is ≥ heap + resolved direct limit; a cgroup OOM-kill is **not** the endpoint and makes the run invalid | environment |
| `cassandra.yaml` diff | only `data_file_directories`, `commitlog_directory`, `hints_directory`, `saved_caches_directory`, `cdc_raw_directory` → the run's node dir. Everything else shipped, including `authenticator: AllowAllAuthenticator`, `concurrent_reads: 32`, `native_transport_max_threads` 128, `read_request_timeout: 5000ms`, `native_transport_timeout` 12s, `read_thresholds_enabled` false, guardrails off, `memtable_allocation_type: heap_buffers`, `row_cache_size: 0MiB`, key/chunk caches default | environment |
| Extra JVM options | `JVM_EXTRA_OPTS=-Xlog:gc:file=<run>/logs/gc-pauses.log:time,uptime:filecount=0` (a second, unrotated `gc=info` log; appended after the shipped `-Xlog` at `cassandra-env.sh:307`); `CASSANDRA_LOG_DIR` and `CASSANDRA_HEAPDUMP_DIR` = `<run>/logs` | instrumentation |
| Diagnostic-only arm P (optional) | `read_thresholds_enabled: true`, `local_read_size_fail_threshold: 64MiB` | custom constraint → `diagnostic` |

**V6.** Every capacity constraint in the protection map is at its shipped default in the test, control and heap-search arms (none is
heap-derived except `native_transport_max_request_data_in_flight`, heap/10, which charges requests only; resolve and record it).
**V7.** Heap 2 GiB meets the standing rule (≥ 512 MiB, 2 GiB ideal) without review; the search goes up to 15872 MiB, the heap
cassandra-env itself resolves for this 125 GiB node, i.e. a fully automatic deployment budget. The direct limit (7936M, resolved)
is not expected to bind. The container guard is not a budget. **No container budget needs owner review.**

**Node size claimed.** 2 GiB heap: what cassandra-env resolves on a 4 GiB-RAM node (½ RAM); 4 GiB and 8 GiB: 8 and 16 GiB nodes;
15872 MiB: any node with ≥ 31 GiB RAM (pc99 itself).

### 2.4 Ceiling arithmetic

- Baseline live heap after start with compacted data and empty memtables: ≈ 80–150 MB (stage 4: 76 MB histogram total at idle, 8 GiB heap).
- Per in-flight read of an M-item set: held ≈ 150 B × M (measured 148–154 B/item); transient allocation ≈ 345 B × M; plus the
  serialized set value 8 B × M and the encoded response 8 B × M (≈ 16 MB at M = 10⁶).
- At H = 2 GiB, M = 10⁶ (≈ 150–170 MB per read): free heap ≈ 2048 − 150 − G1 reserve (10 %, ≈ 200) ≈ 1.7 GB → **≈ 10–11 fully
  overlapping reads exhaust it**. Contract ceiling at defaults: none in bytes; count bounds 32 replica builds and 128 coordinator
  threads → 32 × 160 MB ≈ 5.1 GB ≫ 2 GiB. Feasible.
- Heap search keeps the per-read share constant by scaling M with H: M = 10⁶ × H / 2 GiB (2·10⁶ at 4G, 4·10⁶ at 8G, 8·10⁶ at
  15872M: 1.2 GB held per read); at the same c the demand stays ≈ c × 7.5 % of H.

### 2.5 Workload and environment

All on **pc99** (victim node and clients; no other node). Working tree `R=/mydata/s4/u3` (fresh; do not reuse
`/mydata/s4/ipc-recheck`). Ports 7000/7199/9042 must be free; `ps -eo cmd | grep '[C]assandraDaemon'` empty before every run.

**Keyspace and data** (`CREATE KEYSPACE u3 WITH replication = {'class':'SimpleStrategy','replication_factor':1}`), P = 8 partitions
per table, k = 0…7:

| Table | Schema | Per partition | Used by |
|---|---|---|---|
| `u3.s1m` | `k int PRIMARY KEY, v set<int>` | M = 1,000,000 distinct ints | calibration, test T, control B (2G) |
| `u3.b1m` | `k int PRIMARY KEY, b blob` | one blob of 8,000,004 B (= the serialized size of `s1m.v`) | control A (2G) |
| `u3.r1m` | `k int, i int, PRIMARY KEY (k, i)` | 1,000,000 clustering rows (the same ints as rows) | intervention I (2G) |
| `u3.s2m` / `u3.s4m` / `u3.s8m` | as `s1m` | M = 2·10⁶ / 4·10⁶ / 8·10⁶ | heap search 4G / 8G / 15872M |

**Golden data (load lifetime, not a reading).** One node lifetime at `MAX_HEAP_SIZE=12G`, guard `MemoryMax=28G`, default yaml (directories
only). Sets are built by appends `UPDATE u3.<t> SET v = v + ? WHERE k = ?` of chunk = 100,000 distinct ints (`range(j·chunk, (j+1)·chunk)`;
accepted at defaults; the stage-4 recheck loaded 10⁷ this way in 26 s). Blobs: one prepared `INSERT` per partition. Rows: single-partition
`UNLOGGED BATCH`es of 1,000 `INSERT INTO u3.r1m (k, i) VALUES (?, ?)`, 32 in flight (`execute_concurrent_with_args`). Load order:
`s1m, b1m, r1m, s2m, s4m, s8m` (s8m last; skip it if behind the time plan). Then `nodetool flush u3`, `nodetool compact u3 <t>` for each
table, `nodetool tablestats u3` (record SSTable count 1 and space used per table), `nodetool drain`, stop. Copy the node's `data/`
(all keyspaces) to `$R/golden/data` and remove `saved_caches/`; commit log empty after drain. Expected disk ≈ 0.6 GB.

**Every measured run** (clean start): new dir `$R/runs/<run-id>/{node,logs}`; `cp -a $R/golden/data` into `node/data`; empty
`commitlog`, `hints`, `saved_caches`, `cdc_raw`; yaml as in 2.3; start the node in its guard scope; wait for `UN` and
`statusbinary` = running (≤ 360 s); settle 10 s; start the clients; **window = 180 s after the first client starts**, or until the
daemon dies; then stop the clients, and (survivors only) take one `jcmd <pid> GC.class_histogram` as the last reading, then
`nodetool stopdaemon` (kill after 90 s). Collect logs. Remove the run's `node/data` after the run (keep logs and the hprof).

**Clients** (`harness/u3client.py`, on pc99, bundled Python driver from `$CASSANDRA_HOME/lib`, as the stage-4 `s4.py`: protocol v5,
`DCAwareRoundRobinPolicy(local_dc='datacenter1')`, `token_metadata_enabled=False`, `idle_heartbeat_interval=0`, CL ONE, client
`request_timeout=60`). `readers <table> <mode> <c> <seconds> <outfile>` forks **c processes**, each with its own `Cluster`/connection;
process i loops until the deadline: `SELECT v FROM u3.<t> WHERE k = ?` (prepared) with k = (i + n) mod 8, logging one line per read:
`proc k t_start t_end outcome count bytes errtype`. Modes: `set` (patch `cqltypes.SetType.deserialize_safe` after connect to return the
count and byte length, as `s4.py` does — the server's work is unchanged), `blob` (`SELECT b`), `rows` (`SELECT i FROM u3.r1m WHERE k = ?`,
`fetch_size = 5000` = the driver default, `tuple_factory`, iterate every page and count rows). On an error (timeout, failure) the process
retries at once (pre-registered: no backoff, as a naive application would); on connection loss it exits. Before starting the readers,
one warm-up read per partition is **not** done (it would be part of the reading); the first 10 s are reported separately.

**Pre-run reachability (shakedown, not a reading):** a throwaway node at `MAX_HEAP_SIZE=2G` with a table of 8 partitions × 10⁴ items,
`readers … set 2 30`: check client lines, count = 10⁴, sampler/tpstats files, GC log, and `hprof_histo.py` on a dump made with
`jcmd <pid> GC.heap_dump <file>` (instrument check of the parser only). Fix harness faults; do not change §2.

### 2.6 Instruments (U independent of K)

| # | Reading | How | Rate |
|---|---|---|---|
| O1 | heap after each GC (U trend, peak post-GC live), pause durations, `To-space exhausted`, `Pause Full`, humongous | `gc-pauses.log` (unrotated) + shipped `gc.log*` | every GC |
| O2 | endpoint and first error | node stdout (`java.lang.OutOfMemoryError: Java heap space` / `Direct buffer memory`, `Dumping heap to …`, `kill -9`), `system.log` (`JVMStabilityInspector`, first `ERROR` with thread and stack if logged before the kill) | event |
| O3 | holder at failure | heap dump (`HeapDumpOnOutOfMemoryError`) parsed by `harness/hprof_histo.py`: instance counts and approx. shallow bytes for `org.apache.cassandra.db.rows.ArrayCell`, `…rows.CellPath$SingleItemCellPath`, `…rows.BTreeRow`, `…rows.ComplexColumnData`, `java.nio.HeapByteBuffer`, `byte[]`, `Object[]`; **rows held ≈ ArrayCell count / M**; and stack traces at the dump: count of threads whose frames contain `UnfilteredSerializer.deserializeRowBody`/`readComplexColumn` (replica row build), `ReadResponse`/`LocalDataResponse.build` (serialization), `SelectStatement.processPartition`/`ResultSetBuilder` (coordinator) | once per OOM run (parse ≥ 1 dump per condition) |
| O4 | survivors' held objects | `jcmd <pid> GC.class_histogram` at the window end (last reading; forces a GC) | once |
| O5 | process memory | cgroup `memory.current`, `memory.events` `oom_kill`, daemon `RssAnon` | 1 s |
| O6 | server concurrency | `timeout 15 nodetool tpstats` → ReadStage and Native-Transport-Requests Active/Pending/Completed, dropped `READ_REQ` | 5 s |
| O7 | client load | per-read lines → completed reads, items delivered/s, timeouts/errors by type, **actual in-flight reads per second** (from t_start/t_end) | per read |

`hprof_histo.py` (stage 2 writes it; pure Python, `struct`, run with `python3 -I`): read the header (`JAVA PROFILE 1.0.2\0`, u4 id size,
u8 time); records (u1 tag, u4 time, u4 length): `0x01` UTF8 (id, chars), `0x02` LOAD CLASS (u4 serial, id class, u4 stack serial,
id name), `0x04` STACK FRAME (id frame, id method name, id sig, id source, u4 class serial, i4 line), `0x05` STACK TRACE (u4 serial,
u4 thread serial, u4 n, n ids), `0x0C`/`0x1C` HEAP DUMP (SEGMENT) with sub-records `0xFF` (id), `0x01` (2 ids), `0x02` (id, u4, u4),
`0x03` (id, u4, u4), `0x04` (id, u4), `0x05` (id), `0x06` (id, u4), `0x07` (id), `0x08` (id, u4, u4), `0x20` CLASS DUMP (id, u4, 6 ids,
u4 instance size, u2 constant-pool n × (u2, u1 type, value), u2 statics n × (id, u1 type, value), u2 fields n × (id, u1 type)),
`0x21` INSTANCE (id, u4, id class, u4 n, n bytes), `0x22` OBJ ARRAY (id, u4, u4 n, id class, n ids), `0x23` PRIM ARRAY (id, u4, u4 n,
u1 type, n × size); type sizes 2 = id, 4/8 = 1, 5/9 = 2, 6/10 = 4, 7/11 = 8. Count instances by class name; arrays by element type.
A dump taken at OOM is not preceded by an extra GC, so it may include some unreachable objects; it follows the failed full GC, so
it approximates live heap — report it as such.

### 2.7 Arms, dial and predicted response

Main condition: **H = 2 GiB, table `s1m` (M = 10⁶), defaults**. Dial: client concurrency c.

| Step | Arm | Runs | Condition | Prediction (before readings) |
|---|---|---|---|---|
| S3 | calibration | 1 each, in order c = 8, 16, 32; add c = 4 only if c = 8 fails | `s1m`, 2G | c = 8: survives (peak post-GC ≤ 1.5 GB, possible timeouts); c = 16: heap OOM within 120 s; c = 32: heap OOM within 60 s |
| S4 | **test T** | 3 fresh runs | `s1m`, 2G, c = c_f | heap OOM 3/3, `Java heap space`, within the window; dump: ArrayCell count ≥ 8·10⁶ (≥ 8 rows held), `SingleItemCellPath` ≈ ArrayCell |
| S5 | **control A (matched payload)** | 3 | `b1m` (same serialized bytes per read), 2G, c = c_f | survives 3/3; peak post-GC ≤ base + c_f × 30 MB (≤ 1.1 GB at c = 32); no service loss |
| S6 | **intervention I (paging bound)** | 3 | `r1m` (same 10⁶ ints per partition as clustering rows; native paging 5,000 rows per page), 2G, c = c_f, each read consumes all pages | survives 3/3; peak post-GC ≤ 0.5 GB; record items delivered/s vs T so that a stalled workload is not mistaken for protection |
| S7 | **control B (nearest surviving c)** | 3 | `s1m`, 2G, c = c_s | survives 3/3 (no OOM; service loss recorded if it occurs) |
| S8 | heap search | 1 per step, then to 3 at the largest failing step | `s2m`@4G, `s4m`@8G, `s8m`@15872M (MAX_HEAP_SIZE unset), c = c_T | OOM at each step (per-read share constant); largest failing budget reported with n/N |
| S9 | optional, diagnostic P | 3 | `s1m`, 2G, c = c_T, `read_thresholds_enabled: true`, `local_read_size_fail_threshold: 64MiB` | the reads are rejected, but each replica still builds its ≈ 150 MB row first; prediction: OOM still possible at c_T (late enforcement), recorded as `diagnostic`, not part of V1–V7 |

**Rules fixed now.** c_f = the smallest c in the calibration that reaches a heap OOM; c_s = the next lower c in the sequence (which
survived). Calibration runs are not counted in any triple. **c_T** = c_f; if T gives ≤ 1/3 OOM, run one more triple at 2·c_f and use
that as the test condition (c_T = 2·c_f), reporting both triples; controls A and I then run at c_T. If c = 32 survives in calibration:
one escalation run at c = 32 with `s2m` (M = 2·10⁶) at 2G; if that OOMs, the main condition becomes (`s2m`, 2G, c = 32), controls use a
16,000,004-byte blob table `b2m` (load it then) and a 2·10⁶-row table, else stop: no OOM within the tested range (§4 decides
false positive or retry). Heap search climbs one step at a time and stops climbing at the first step that survives (then that step
gets 2 more runs to confirm the boundary, if time allows).

**Endpoint classification per run.** OOM = daemon death with `OutOfMemoryError` in stdout/system.log and `oom_kill` = 0 (heap or
direct, by message). Cgroup kill (`oom_kill` > 0) or any other death = **invalid** (record, do not count). Survival = window completed,
daemon alive. Service loss (recorded, not OOM) = ≥ 90 % of wall time in STW pauses over a ≥ 60 s window (protocol default), computed
from `gc-pauses.log`. A run whose clients completed < 1 read per client in the window is **invalid** (workload did not run).

**Stopping budget.** Window 180 s per run; at most 4 calibration runs + 1 escalation; no arm repeated more than its count above; no
new run starts after **02:05 EST** on 2026-11-18; all processes stopped by 02:20.

### 2.8 Controls and intervention (why these)

- **Control A (matched payload):** same bytes on disk-to-wire per read (8,000,004 B), same c, same heap, same partitions and client;
  only the shape changes from M cells to one cell. Stage 4: 0.16× the held heap. Separates "big reads" from "per-item materialization".
- **Control B (low multiplicity):** same data and heap at the nearest surviving c; shows a single (or few) read(s) is safe alone.
- **Intervention I (add the bound):** the documented alternative for unbounded items (a clustering table) with the native protocol's
  page bound (5,000 rows per page). Same items, same c, same heap; per-request memory is bounded by the page. If T fails and I
  survives with comparable items/s, the whole-collection materialization is the cause. (Capping c is control B.)

### 2.9 Time plan (stage 2 must end before 02:30 EST, 2026-11-18)

Assumes stage 2 starts by about 23:20 EST; if it starts later, drop items from the bottom of the priority list.

| Step | Content | Minutes | Ends by (start 23:20) |
|---|---|---|---|
| S0 | read case, check hash and pc99, `cp -a` base, write harness (`run.sh`, `u3client.py`, `sampler.sh`, `hprof_histo.py`, `gcpause.py`) | 20 | 23:40 |
| S1 | shakedown (instrument check) | 8 | 23:48 |
| S2 | golden data load lifetime | 12 | 00:00 |
| S3 | calibration (3–4 runs, ≈ 4 min each) | 15 | 00:15 |
| S4 | test T ×3 (OOM runs ≈ 3 min each) + parse one dump (≈ 2 min) | 12 | 00:27 |
| S5 | control A ×3 (≈ 5 min each) | 15 | 00:42 |
| S6 | intervention I ×3 | 15 | 00:57 |
| S7 | control B ×3 | 15 | 01:12 |
| S8 | heap search 4G, 8G, 15872M, fill to 3 at the largest failing step (dumps 4–16 GB; parse one) | 35 | 01:47 |
| S9 | optional P ×3 | 15 | 02:02 |
| S10 | §3–§4, write-back, stop every process, list what stays on pc99 | 20 | 02:20 (cleanup) |

**Priority if short of time:** S0–S6 (V1–V5 at 2G) > S7 > S8 at 4G/8G > S8 at 15872M > S9. Disk: dumps ≤ ≈ 100 GB in total (≤ 714 GiB);
RAM: node ≤ 30G guard + ≤ 32 client processes (≈ 60 MB each) ≪ 125 GiB; CPU: 32 cores shared by node and clients (record client CPU).

### 2.10 What stays on pc99

`/mydata/s4/u3/` (source copy, golden data, run logs, hprof files) stays until the owner accepts the results; no process is left
running. `/mydata/s4/ipc-recheck/` and `/mydata/s4/cassandra-base/` are not touched.

`sha256 of §1–§2 at freeze: db9d4ba2c95e15b09c98bacad903ce80a0bd445ea8da461c904da719ce1adcf3` (frozen 2026-11-17 22:50 EST)  ·  amendments after the freeze: none. Hash command: `awk '/^## 1\. Candidate/{f=1} /^.sha256 of §1–§2 at freeze/{f=0} f' <case file> | sha256sum`.

## 3. Runs (stage 2)

Stage 2 by a fresh OOM-agent session (Claude Opus 5.5, `claude-opus-5-5`), 2026-11-17 22:50 – 2026-11-18 ≈ 00:05 EST (cut off by an
API usage limit), **resumed** by a second fresh stage-2 session 2026-11-18 02:54–03:45 EST (see the resume note in §3.4). Freeze hash
checked before anything ran, and again at resume: `db9d4ba2…adcf3` recomputed with the command in §2.10, **match** both times.

**Harness:** [`harness/`](harness/) — `lib.sh` (node start in its guard scope, samplers, stop), `golden.sh` (golden load lifetime and
shakedown), `run.sh` (one measured run per §2.5), `seq.sh` (runs a list; calibration stops at the first OOM, heap search at the first
survivor; refuses to start a run after 02:05 EST), `chain.sh` (heap search → fill to 3 → P after the main batch), `u3client.py`
(clients per §2.5), `analyze.py` (O1, O5, O7 and the endpoint rule), `hprof_histo.py` (O3, pure Python per §2.6), `arm-P.yaml`, the
`spec-*.txt` run lists; added at resume: `resume-lib.sh` + `run-r.sh` (D7), `a2.py` (A2 endpoint rule), `seq-r.sh`, `chain-r.sh`,
`chain-r2.sh` (A3, A4). **Logs:** full logs, GC logs and hprof files on `pc99:/mydata/s4/u3-w1/runs/<run>/logs/`; excerpts
(per-run `analysis.txt`, `summary-raw.txt`, `hprof-histo.txt` of parsed dumps, OOM lines of `node.out`, StatusLogger lines) in [`logs/`](logs/).

### 3.1 Environment (as run)

| Item | Value |
|---|---|
| Node | `pc99` (node3.jason92-326528, x86_64, 32 cores, 125 GiB, swap 8 GiB on, `/mydata` 714 GiB free); checked idle before start (`pgrep -af CassandraDaemon` empty, ports 7000/7199/9042 free, load 0.00); one node, victim and clients |
| Build | `cp -a /mydata/s4/cassandra-base` → `/mydata/s4/u3-w1/cassandra`; `release_version` = `5.0.9-SNAPSHOT`; OpenJDK 11.0.33; Python 3.10.12 with the bundled driver 3.29.0 |
| JVM (resolved, `system.log` JVM Arguments) | `-Xms2G -Xmx2G` (main), G1, `G1HeapRegionSize=16m`, `MaxGCPauseMillis=300`, `+HeapDumpOnOutOfMemoryError`, `HeapDumpPath=<run>/logs/…hprof`, `OnOutOfMemoryError=kill -9 %p`, **`MaxDirectMemorySize=15872M`** (resolved; §2.3 expected 7936M, see deviation D2) |
| yaml | shipped, diff = the five directory keys only (`yaml-diff.txt` per run); arm P adds the two read-threshold keys |
| Guard | `systemd-run --user --scope -p MemoryMax=<16G at 2G heap> -p MemorySwapMax=0`; `memory.swap.max` = 0 confirmed per run |
| Golden data | one lifetime at 12G heap / 28G guard (22:57–23:05 EST; pc99's clock is MST): all appends accepted (s1m 80/80 statements, s2m 160/160, s4m 320/320, s8m 640/640; b1m 8/8 blobs of 8,000,004 B; r1m 8,000/8,000 batches); flush, `nodetool compact` per table → **1 SSTable per table**; space used: s1m 32.2 MB, s2m 64.4 MB, s4m 128.8 MB, s8m 257.5 MB, r1m 35.5 MB, b1m 0.36 MB (zeros compress; 8,000,004 B per value on read); drained; golden copy 519 MB |
| Shakedown | throwaway node 2G, `sz` 8 × 10⁴: `readers sz set 2 30` → 7,188 reads, count = 10,000 each, 80,004 B each; tpstats/GC/memory files written; `jcmd GC.heap_dump` 115.5 MB parsed by `hprof_histo.py` in 1.3 s (1.05 M objects, 95.6 MB approx shallow vs 81.5 MB `GC.class_histogram` total — the parser counts 8-byte ids, so its byte column overstates; counts are exact). No harness fault, §2 unchanged |

### 3.2 Runs

All at H = 2 GiB unless stated, every run from the golden data, window 180 s from the first client. *OOM t* = first
`OutOfMemoryError` (creation time of the `HeapDumpOnOutOfMemoryError` file) after the clients start; *post-GC* = heap after GC
pauses after the clients start (`gc-pauses.log`), p50 / max; *pause frac* = max share of wall time in STW pauses over any 60 s; *histo*
= `GC.class_histogram` total at the window end (survivors). `oom_kill` = 0 in every run (no cgroup kill); no run invalid by the cgroup rule.

| Run | Arm | c | Load reached (client) | Endpoint | Key reading (U; K: none) |
|---|---|---|---|---|---|
| cal-c8 | S3 calibration | 8 | 422 reads ok, 4.22·10⁸ items (2.35 M items/s), 0 errors; in flight max 8, mean 7.9; read p50 3.47 s, max 5.35 s | **none** (survived) | post-GC 1884 / 2028 MB; 154 Full GCs, 266 `To-space exhausted`; pause frac 0.81 (< 0.90: no service loss); histo 568 MB with 3.0 M `ArrayCell` (3 rows in flight) |
| cal-c16 | S3 calibration | 16 | 0 reads completed; 16 in flight from t ≈ 0 (each client: 1 read, client timeout at 60 s, 1 retry, then `NoHostAvailable`) | **heap OOM** `Java heap space` at 7.3 s; dump 3.08 GB done at 88 s; `kill -9` (shipped handler) at 106.9 s | post-GC 2017 / 2028 MB; 136 Full GCs; pause frac 1.00; dump: **15,218,273 `ArrayCell`, 15,218,333 `CellPath$SingleItemCellPath`, 15,222,373 `HeapByteBuffer`, 15,420,938 `byte[]`** (≈ 15.2 rows of 10⁶ items); 16 threads in `UnfilteredSerializer.deserializeRowBody`/`readComplexColumn`; the thread at `OutOfMemoryError.<init>` was in `ByteBufferUtil.read ← CollectionType$CollectionPathSerializer.deserialize ← Cell$Serializer.deserialize ← UnfilteredSerializer.readComplexColumn` |
| T1 | S4 test | 16 | as cal-c16 (0 completed, 16 in flight) | **heap OOM** at 12.2 s; dump done 40.4 s; killed 103.8 s | post-GC 2014 / 2028 MB; 135 Full; pause frac 1.00; StatusLogger at the OOM: `ReadStage` Active 16, `Native-Transport-Requests` Active 16; dump: 15,197,691 `ArrayCell`, 15,197,753 `SingleItemCellPath`; 16 replica-row-build threads; OOM thread in `ByteBuffer.wrap ← ByteBufferUtil.read ← CollectionPathSerializer.deserialize` |
| T2 | S4 test | 16 | 0 completed; 16 in flight all window (48 client timeouts at 60 s) | **heap OOM** at 13.5 s; dump done 78.2 s; the shipped `kill -9` ran ≈ 190 s (≈ 10 s after the window end; amendment A2) | post-GC 2015 / 2028 MB; 273 Full; pause frac 1.00 from the OOM on; StatusLogger `ReadStage` Active 16; dump: 15,198,679 `ArrayCell`; 13 replica-row-build threads |
| T3 | S4 test | 16 | 0 completed; 16 in flight | **heap OOM** at 10.4 s; dump done 38.0 s; killed 72.7 s | post-GC 2015 / 2028 MB; 78 Full; pause frac 0.62; StatusLogger `ReadStage` 16, NTR 16; dump: 15,204,680 `ArrayCell`; 16 replica-row-build threads |
| A1 | S5 control A (blob, same 8,000,004 B per read) | 16 | 15,877 reads ok (88/s, 0.70 GB/s on the wire), 0 errors; p50 0.18 s | **none** | post-GC 552 / 1990 MB (max = transient humongous regions, p90 767); 8 Full; pause frac 0.14; histo 104 MB |
| A2 | S5 control A | 16 | 17,363 ok (96/s), 0 errors | **none** | post-GC 601 / 2014 MB; 12 Full; pause frac 0.13; histo 107 MB |
| A3 | S5 control A | 16 | 17,334 ok (96/s), 0 errors | **none** | post-GC 626 / 2003 MB; 34 Full; pause frac 0.14; histo 106 MB |
| I1 | S6 intervention I (clustering rows, 5,000 per page, all pages) | 16 | 464 reads ok = **4.64·10⁸ items (2.57 M items/s)**, 0 errors; p50 6.09 s | **none** | post-GC 115 / 271 MB; 1 Full; pause frac 0.01; histo 108 MB |
| I2 | S6 intervention I | 16 | 464 ok, 4.64·10⁸ items (2.61 M items/s) | **none** | post-GC 112 / 185 MB; 1 Full; pause frac 0.01; histo 107 MB |
| I3 | S6 intervention I | 16 | 448 ok, 4.48·10⁸ items (2.50 M items/s) | **none** | post-GC 112 / 264 MB; 1 Full; pause frac 0.01; histo 106 MB |
| B1 | S7 control B (c_s) | 8 | 462 ok, 4.62·10⁸ items (2.56 M items/s), 0 errors; p50 3.09 s | **none** | post-GC 1873 / 2028 MB; 154 Full; pause frac 0.80; histo 723 MB with 4.0 M `ArrayCell` |
| B2 | S7 control B | 8 | 487 ok, 4.87·10⁸ items (2.70 M items/s), 0 errors; p50 2.93 s, max 5.22 s; in flight max 8, mean 7.9 | **none** | peak post-GC 2028 MB; 161 Full, 308 `To-space exhausted`; pause frac 0.78; max `RssAnon` 2.79 GB; histo 96 MB (taken after the clients stopped) |
| B3 | S7 control B | 8 | 452 ok, 4.52·10⁸ items (2.51 M items/s), 0 errors; p50 3.12 s, max 4.99 s; in flight max 8, mean 7.9 | **none** | peak post-GC 2028 MB; 153 Full, 291 `To-space exhausted`; pause frac 0.79; histo 96 MB |
| HS4G | S8 heap search, 4 GiB, `s2m` (M = 2·10⁶) | 16 | 0 completed; 55 reads issued (36 client `OperationTimedOut`, 19 `ReadTimeout`, retried at once); in flight max 16, mean 13.0 | **heap OOM** `Java heap space` at **38.1 s** (hprof creation); dump 6.14 GB complete at 158.0 s; the shipped `kill -9` ran ≈ 190 s (just after the window end, as T2; counted by amendment A2 — the harness analyzer printed `survived` by the literal rule, see A3) | post-GC 4076 MB peak of 4096, last pauses `Pause Full 4061->4061(4096)M` ≈ 0.78 s each back to back; 195 Full; pause frac 1.00; max `RssAnon` 4.80 GB, `memory.current` 10.77 GB (incl. dump page cache); StatusLogger `ReadStage` Active 16; `oom_kill` 0 |
| P1 | S9 diagnostic P (`read_thresholds_enabled: true`, `local_read_size_fail_threshold: 64MiB`) | 16 | 0 completed (ReadTimeout / OperationTimedOut, then `NoHostAvailable` at death); in flight mean 15.7 | **heap OOM** at 11.3 s; dump 3.07 GB done 49.0 s; daemon died (shipped `kill -9`) at 61.7 s | post-GC 2028 MB peak; 60 Full; pause frac 0.61; StatusLogger `ReadStage` Active 16, NTR 13; **no read-size rejection logged** before the OOM (no `local_read_size` warning/abort line in `system.log`): the 64 MiB check runs per row after the row is built, and no 10⁶-item row finished |
| P2 | S9 diagnostic P | 16 | 0 completed; in flight mean 15.6 | **heap OOM** at 12.6 s; dump done 44.6 s; died 88.8 s | post-GC 2028 MB; 106 Full; pause frac 0.71; StatusLogger `ReadStage` 16, NTR 14 |
| P3 | S9 diagnostic P | 16 | 0 completed; in flight mean 15.8 | **heap OOM** at 11.9 s; dump done 78.6 s; died 95.8 s | post-GC 2028 MB; 116 Full; pause frac 0.91 |

*Runs below: the resumed session (2026-11-18 02:56–03:32 EST), harness `run-r.sh` / `seq-r.sh` / `chain-r.sh` / `chain-r2.sh`,
endpoint by `a2.py` (A2 rule, A3). Same build, golden data, yaml (directories only), client and window as above.*

| Run | Arm | c | Load reached (client) | Endpoint | Key reading (U; K: none) |
|---|---|---|---|---|---|
| HS8G | S8 heap search, 8 GiB, `s4m` (M = 4·10⁶), guard 22G | 16 | 0 completed; 57 reads issued (25 `ReadTimeout`, 32 `OperationTimedOut`, retried at once); in flight max 16, mean 12.4 | **heap OOM** `Java heap space` at **138.5 s**; dump 12.07 GB in 240 s (D7 waited 186 s after the window); shipped `kill -9` ran after the dump | post-GC peak 8172 of 8192 MB, `Pause Full 8156->8156(8192)M` ≈ 1.2 s back to back; 258 Full, 115 `To-space exhausted`; pause frac 1.00; max `RssAnon` 8.99 GB, `memory.current` 20.70 GB (incl. dump page cache), `oom_kill` 0; StatusLogger `ReadStage` 16, NTR 16; dump: **61,736,109 `ArrayCell`**, 61,736,171 `SingleItemCellPath`, 61,740,234 `HeapByteBuffer` (≈ 15.4 rows of 4·10⁶), 30 threads in replica row builds |
| HS16G | S8 heap search, `MAX_HEAP_SIZE` unset, `s8m`, guard 30G | 16 | none (no client started) | **invalid**: cgroup OOM-kill during JVM start (journal, 2 s after start; unset heap resolves to 31744M with G1 > guard; A4) | — |
| HS8Gr2 | S8 fill to 3 at 8 GiB | 16 | 0 completed; 53 issued; in flight mean 11.8 | **heap OOM** at **111.3 s**; dump 12.07 GB in 110 s | post-GC peak 8172 MB; 179 Full; pause frac 1.00; `RssAnon` 8.97 GB; `oom_kill` 0; StatusLogger `ReadStage` 16, NTR 16 |
| HS8Gr3 | S8 fill to 3 at 8 GiB | 16 | 0 completed; 56 issued; in flight mean 13.0 | **heap OOM** at **143.6 s**; dump 11.60 GB in 242 s; shipped `kill -9` after it | post-GC peak 8172 MB; 242 Full; pause frac 1.00; `oom_kill` 0; StatusLogger `ReadStage` **Active 28** (> c = 16: timed-out reads still building their rows, §2.1 item 4), NTR 16 |
| HS16Gx | S8 heap search, `MAX_HEAP_SIZE=15872M` (A4), `s8m` (M = 8·10⁶), guard 30G | 16 | 0 completed; 64 issued (29 `ReadTimeout`, 31 `OperationTimedOut`, 4 `NoHostAvailable`); in flight mean 12.7 | **no OOM** in the window (no `OutOfMemoryError` up to the stop at ≈ 290 s; `stopdaemon` failed, killed by the harness after 90 s); **service loss** | post-GC peak 15852 of 15872 MB, then `Pause Full 15842->15826(15872)M` ≈ 2.1 s back to back; 135 Full; first Full at 11.7 s; every 60 s window ending from 61.9 s to 292.4 s ≥ 90 % STW (pause frac 1.00); `RssAnon` 16.63 GB; `oom_kill` 0; StatusLogger `ReadStage` 16, NTR 16 |
| HS16Gxr2 | S8 boundary, 2 more runs | 16 | 0 completed; 58 issued; in flight mean 13.1 | **no OOM**; service loss | post-GC peak 15852 MB, Full GCs recovering ≈ 16 MB each; 147 Full; ≥ 90 % STW windows ending 60.5–314.5 s; StatusLogger `ReadStage` **Active 31**; `oom_kill` 0 |
| HS16Gxr3 | S8 boundary | 16 | 0 completed; 59 issued; in flight mean 12.2 | **no OOM**; service loss | post-GC peak 15852 MB; 135 Full; ≥ 90 % STW windows ending 60.9–291.5 s; `oom_kill` 0 |

### 3.2.1 Heap search result (S8)

| Heap (budget) | Table (M per read) | Runs | OOM | First OOME after clients start | Notes |
|---|---|---|---|---|---|
| 2 GiB | `s1m` (10⁶) | T1–T3 (+ cal-c16) | **3/3** (+1) | 7.3–13.5 s | main condition |
| 4 GiB | `s2m` (2·10⁶) | HS4G | 1/1 | 38.1 s | dump: 30,376,873 `ArrayCell` ≈ 15.2 rows of 2·10⁶; 26 replica-row-build threads (> 16) |
| **8 GiB** | `s4m` (4·10⁶) | HS8G, HS8Gr2, HS8Gr3 | **3/3** | 111.3 / 138.5 / 143.6 s | **largest failing budget** |
| 15872 MiB (set) | `s8m` (8·10⁶) | HS16Gx, r2, r3 | **0/3** within the window | — | boundary: no OOME in 180 s (to the stop at ≈ 290–315 s), but service loss 3/3 (heap pinned at 15.83 of 15.87 GB, ≥ 90 % STW from ≈ 1 min on) |
| 31744 MiB (unset, automatic) | — | not run | — | — | climbing stopped at the first survivor (§2.7); HS16G with this heap was invalid (A4) |

The time to the first OOME grows with H (≈ 10 s at 2G, 38 s at 4G, 111–144 s at 8G) because each read's row is M ∝ H items and
takes ∝ M to build; at 15872M it would come after the 180 s window, if at all — the window, not the heap, sets the boundary there.
That is a limit of the design (fixed window), recorded, not an extension: no run was lengthened (protocol rule 8).

All processes stopped: after HS16Gxr3 `pgrep` for `CassandraDaemon`, `u3client`, `seq-r`, `chain-r`, `run-r` on pc99 is empty
(03:32 EST); every run's `summary-raw.txt` ends with `END … daemons_left=0`. The two dumps parsed at resume (HS4G, HS8G) were copied
to the controller's local disk (`/mydata/jason92-u3-parse/`, not NFS), parsed with `harness/hprof_histo.py`, and the copies deleted;
the parser output is in `logs/HS4G/` and `logs/HS8G/` (the controller directory was removed afterwards).

### 3.3 Calibration result and conditions fixed by the §2.7 rules

c = 8 survived, c = 16 reached a heap OOM → **c_f = 16, c_s = 8, c_T = 16** (T gave 3/3, so no 2·c_f triple). Controls A and I ran
at c = 16, control B at c = 8.

### 3.4 Deviations and amendments

- **D1 (working directory).** `R = /mydata/s4/u3-w1` instead of `/mydata/s4/u3` (§2.5): the wave-1 orchestration assigned a fresh
  directory by that name. Nothing else changes.
- **D2 (direct limit).** `MaxDirectMemorySize` resolved to **15872M** on pc99 (not 7936M as §2.3 expected), so the 16G guard at
  2G heap is below heap + direct limit (§2.3 says the guard is ≥ both). No run used direct memory near that: max `memory.current`
  5.7 GB (OOM runs, including page cache of the dump file being written), max `RssAnon` 3.0 GB, `oom_kill` = 0 everywhere, no
  `Direct buffer memory` error. Recorded, no effect on any reading.
- **D3 (calibration length).** Calibration stopped after the first OOM (c = 16); c = 32 was not run. §2.7 defines c_f as the smallest
  failing c, which c = 32 cannot change; it would have added a fourth OOM run outside every triple.
- **D4 (O6 sampler).** The 5 s `nodetool tpstats` sampler printed no `ReadStage` line before the first read (the stage is created on
  first use), and during the Full-GC storm of the OOM runs `nodetool` timed out (30 s). Server concurrency at the OOM is taken from
  the shipped `StatusLogger` lines that `GCInspector` writes on long pauses (`ReadStage` Active 16, `Native-Transport-Requests`
  Active 16) and from the dump's thread stacks (13–16 replica row builds). Survivors' tpstats are complete.
- **D5 (OOM instant).** The JVM writes the OOM message without a timestamp; the first-OOM time is the creation time (`stat %W`) of
  the hprof file that `HeapDumpOnOutOfMemoryError` starts at the first `OutOfMemoryError`. The daemon's death comes later, from the
  shipped `-XX:OnOutOfMemoryError=kill -9 %p` after the dump (27–80 s to write 3.1 GB) and a further 20–110 s of Full GCs.
- **D6 (prediction miss, control A).** Control A's peak post-GC (1990–2014 MB) is above its §2.7 prediction (≤ base + c × 30 MB);
  the peaks are single pauses during humongous-allocation churn (8 MB values in 16 MB regions), p50 552–626 MB, live heap at the end
  104–107 MB. The control's criterion (survives 3/3, no service loss) holds; the prediction miss is recorded.
- **Amendment A1 (2026-11-18 00:00 EST, workload-validity rule, §2.7 "a run whose clients completed < 1 read per client in the window
  is invalid (workload did not run)").** At c = 16 no 10⁶-item read can complete: the 16 replica rows (≈ 150 MB each) are built
  concurrently and the first `OutOfMemoryError` comes 7–14 s after the clients start, while one read takes 3.1–3.5 s (p50) even at
  c = 8 with the heap nearly full. The rule as written cannot tell this case from a workload that never ran, which is the rule's stated
  purpose. Applied test: the workload ran if every client issued ≥ 1 read (each client logged a read with `t_start` ≈ the start and an
  outcome) and the server was executing them (`ReadStage` Active 16 in the StatusLogger at the OOM and 13–16 replica row builds in the
  dump). By that test T1–T3 and cal-c16 are valid. **Under the literal rule they would be invalid**, and no OOM run at defaults could
  be valid at any c ≥ 16; §4 states what that would change.
- **Amendment A2 (2026-11-18 00:00 EST, endpoint inside the window).** T2's first `OutOfMemoryError: Java heap space` came at 13.5 s
  and its dump was complete at 78.2 s, inside the window; the shipped `kill -9` handler ran at ≈ 190 s, about 10 s after the window
  end, so at the window end the daemon was alive but in back-to-back Full GCs at 2015 MB of 2048 MB (pause frac 1.00). §2.7 counts
  OOM as "daemon death with `OutOfMemoryError` … and `oom_kill` = 0", which T2 meets, with the death 10 s late. T2 is counted as an
  OOM run; without it T would be 2/2 + the calibration OOM.
- **Resume note (2026-11-18 02:54 EST).** The first stage-2 session was cut off by an API usage limit (not by the design) after
  writing §3 up to B1. A fresh stage-2 session resumed: freeze hash recomputed, **match** (`db9d4ba2…adcf3`); pc99 idle (no
  Cassandra daemon, no harness process, ports free, load 0.00); no `STOP` file. On the node the interrupted session's chain had
  **finished** every queued run before the cut-off (last run P3 ended 00:01 EST): cal-c8, cal-c16, T1–T3, A1–A3, I1–I3, B1–B3,
  HS4G, P1–P3, each with a complete `summary-raw.txt` (`END … daemons_left=0`), `analysis.txt`, GC and client logs. **Reused as
  is:** the build `/mydata/s4/u3-w1/cassandra`, the golden data `/mydata/s4/u3-w1/golden`, and all 18 completed runs (logs clean;
  none redone). The harness on the node was byte-identical to `harness/` (checked with `cmp`), plus `spec-P.txt`, now copied
  here. The excerpts directory [`logs/`](logs/) had not been written; it was filled from the node at resume (per run
  `analysis.txt`, `summary-raw.txt` cut to 600 chars per line, `oom-lines.txt` = OOM lines of `node.out` + first StatusLogger
  `ReadStage`/NTR lines, and the existing `hprof-histo.txt` of cal-c16/T1–T3). **Not done before the cut-off:** the heap search
  stopped after HS4G (see A3), so 8 GiB and 15872M had not run; that is what the resumed session ran (runs below).
- **Amendment A3 (2026-11-18 02:56 EST, before any new reading; heap-search climbing rule and time limits).** (a) The interrupted
  chain's `seq.sh` stopped climbing after HS4G because `analyze.py` applies the literal endpoint rule (daemon death inside the
  window) and printed `survived`; HS4G's first `OutOfMemoryError: Java heap space` came at 38.1 s and its dump completed at 158 s,
  inside the window, with the shipped `kill -9` just after it — exactly T2's case, which A2 already counts as OOM. Applying A2
  consistently, HS4G is an OOM and the heap search continues per §2.7 (climb to 8 GiB `s4m`, then 15872M `s8m`, stop at the first
  survivor; then fill the largest failing step to 3). The A2 rule is now coded in `harness/a2.py` (OOM = death with OOME in the
  window, or first OOME — hprof creation — inside the window with `oom_kill` 0) and used by `harness/seq-r.sh` / `chain-r.sh`.
  (b) §2.7's "no new run after 02:05 EST" and §2.9's plan belonged to the interrupted session's time budget; the resumed session's
  deadline is 07:30 EST (all runs stopped, §3–§4 written), so `seq-r.sh` starts no run after 06:30 EST. Window, arms, counts,
  data and configuration are unchanged.
- **D7 (dump preservation, resumed runs only).** `harness/resume-lib.sh` wraps `stop_node`: if a `HeapDumpOnOutOfMemoryError`
  dump is still being written when the window ends, it waits for `Heap dump file created` (≤ 900 s) before `stopdaemon`/kill, so
  the 8–16 GB dumps of the larger heaps are not truncated by the 90 s kill. It acts only after the window and after the first
  OOME, so it cannot change the endpoint. `harness/run-r.sh` = `run.sh` sourcing `resume-lib.sh` (one-line diff).
- **Amendment A4 (2026-11-18 03:08 EST, after HS8G; design fault in the top heap step).** The spec line `HS16G unset 30G s8m`
  (§2.3/§2.7: "15872M, MAX_HEAP_SIZE unset") was cgroup-OOM-killed **during JVM start** (journal: `u3w1-HS16G.scope: A process of
  this unit has been killed by the OOM killer` 2 s after start, `-XX:+AlwaysPreTouch`; no client ran) → **invalid**, not a
  reading. Cause: in `cassandra-env.sh:51-56` the cap is 15872M only when CMS is used (`USING_CMS` = 0); with the shipped G1 it is
  **31744M**, so on pc99 an unset heap resolves to `-Xmx31744M` and `MaxDirectMemorySize` = 15872M (heap_limit/2 — the same
  15872M seen as D2), above the 30G guard. §2.3's "cassandra-env resolves min(½ RAM, 15872 MiB)" was wrong for G1. The two
  intentions of that step are now separate steps, climbing in order: **HS16Gx** = `MAX_HEAP_SIZE=15872M` set explicitly, `s8m`
  (keeps §2.4's arithmetic, 1.2 GB per read ≈ 7.5 % of H), guard 30G; then, only if it OOMs, **HS31G** = `MAX_HEAP_SIZE` unset
  (the fully automatic budget, `-Xmx31744M`), `s8m` (no `s16m` table; the per-read share halves to ≈ 3.8 % of H, so it is a
  harder step), guard 48G (≥ heap + resolved direct limit, as §2.3 requires). Then the largest failing step is filled to 3 and a
  surviving step gets 2 more runs if time allows (`harness/chain-r2.sh`, `spec-hs-r2.txt`). The interrupted chain's tail (two more
  `HS16G unset 30G` runs, which would have been killed the same way) was stopped by killing `chain-r.sh` (PID) while the HS8G
  fill was running; the fill itself continued.

## 4. Conclusion (stage 2)

Written 2026-11-18 ≈ 03:45 EST by the resumed stage-2 session.

**Verdict: true positive.** Protocol status: **`verified-OOM · deployment`**, endpoint Java heap OOM, classification
**unprotected** (unprotected configuration: the collection guardrail and the read-size thresholds are off by default; unprotected
accumulation: with them on, neither bounds the heap of concurrent whole-collection reads). Interpretation: a configuration-sizing /
validation gap (guardrail counts the written fragment and ships off; the read-size check runs after the row is built), on behaviour
the project documents (collections are read whole, not paged; meant for small data; limit 2·10⁹ items). Not an implementation defect
in the narrow sense, and not a known-fixed bug (JIRA verdict `new`, §1).

### 4.1 Per-condition status

| Condition | Runs | Result | Status |
|---|---|---|---|
| **2 GiB heap, `s1m` (10⁶ items), c = 16, defaults** (main) | T1–T3 (+ cal-c16) | heap OOM 3/3 (+1), first OOME 10.4–13.5 s | **verified-OOM · deployment** |
| 4 GiB, `s2m`, c = 16 | HS4G | heap OOM 1/1 at 38.1 s | heap-search step (1 run) |
| **8 GiB, `s4m`, c = 16** | HS8G, r2, r3 | heap OOM **3/3** at 111–144 s | **largest failing budget, 3/3** |
| 15872 MiB, `s8m`, c = 16 | HS16Gx, r2, r3 | no OOME within the 180 s window 0/3; GC service loss 3/3 (heap 15.83/15.87 GB, ≥ 90 % STW from ≈ 60 s to the stop) | boundary within the window (`verified-gap · service-loss`-shaped, not counted as OOM) |
| 31744 MiB (unset heap, automatic for G1 on pc99) | — | not run (climbing stopped at the first survivor; the first attempt was invalid, A4) | untested |
| diagnostic P: `local_read_size_fail_threshold` 64 MiB | P1–P3 | heap OOM 3/3; no read-size rejection logged first | `reproduced-OOM · diagnostic` (custom constraint): the shipped read-size bound, when enabled, does not prevent it |

### 4.2 V1–V7 (main condition: build `5.0.9-SNAPSHOT`, shipped yaml + directories, 2 GiB heap, `s1m`, c = 16)

| | Requirement | Evidence | Met |
|---|---|---|---|
| V1 | ≥ 3 runs reach the endpoint | T1, T2, T3: `OutOfMemoryError: Java heap space` at 12.2 / 13.5 / 10.4 s, `oom_kill` 0, 3/3 (cal-c16 a 4th, not counted). T2's death by the shipped `kill -9` came ≈ 10 s after the window (A2) | yes (A1, A2 noted) |
| V2 | nearest surviving control ≥ 3 runs, same budget/build | control B (c = 8): B1–B3 survive 3/3, 452–487 reads each, 2.51–2.70 M items/s, 0 errors (heavy GC, pause frac 0.78–0.80, below the 0.90 service-loss line); control A (same 8,000,004 B per read as one blob, c = 16): A1–A3 survive 3/3, 15.9–17.4 k reads, pause frac 0.13–0.14 | yes |
| V3 | U measured independently of K | K: none (no counter at defaults). U: post-GC heap pinned at 2014–2017 of 2048 MB; dumps (cal-c16, T1–T3) 15.20–15.22 M `ArrayCell`, the same number of `CellPath$SingleItemCellPath`, `HeapByteBuffer`, `byte[]` ≈ **15.2 rows of 10⁶ items** (≈ 150 MB each) ; 13–16 threads in `UnfilteredSerializer.deserializeRowBody`/`readComplexColumn`. HS4G: 30.38 M cells ≈ 15.2 rows of 2·10⁶, 26 builder threads; HS8G: 61.74 M ≈ 15.4 rows of 4·10⁶, 30 builder threads | yes |
| V4 | intervention removes the endpoint ≥ 3 runs at recorded load | I (same 10⁶ ints per partition as clustering rows, native paging 5,000 rows, same c = 16, same heap): survive 3/3, **4.48–4.64·10⁸ items delivered (2.50–2.61 M items/s)** — the same useful throughput as control B, vs 0 items in T — peak post-GC ≤ 271 MB. Bounding c (control B) also removes it. Enabling the shipped read-size bound (P) does **not** | yes |
| V5 | initiating failure + holder at failure | first OOME thread stack in the dumps: `OutOfMemoryError.<init> ← ByteBuffer.wrap ← ByteBufferUtil.read ← CollectionType$CollectionPathSerializer.deserialize ← Cell$Serializer.deserialize ← UnfilteredSerializer.readComplexColumn` (replica row build); StatusLogger at the OOM `ReadStage` Active 16, NTR Active 16; histograms above (`logs/*/hprof-histo.txt`) | yes |
| V6 | constraints at shipped defaults | every protection-map row at default in T, A, B, I and heap search (guardrails off, read thresholds off, `concurrent_reads` 32, NTR 128, timeouts 5 s / 12 s, in-flight request limits heap-derived: heap/10); only P changes a constraint (diagnostic arm) | yes |
| V7 | acceptable budget | 2 GiB heap = the ideal budget of the standing rule (≥ 512 MiB, no review needed); repeated at 8 GiB 3/3. Direct limit resolved 15872M (not binding; no direct OOM). The cgroup scope was a guard only (`oom_kill` 0 in every valid run), not the budget | yes |

### 4.3 Reason (deciding numbers)

At a 2 GiB heap and shipped defaults, each read of a 10⁶-item appended set builds a ≈ 150 MB row on the replica; 16 concurrent
readers put ≈ 15 such rows on the heap at once (dumps: 15.2 M cells each of `ArrayCell`, `CellPath`, `HeapByteBuffer`, `byte[]`)
and the JVM threw `OutOfMemoryError: Java heap space` 10–14 s after the clients started in 3/3 runs, with no byte counter (K: none)
and the 32-permit `concurrent_reads` bound not binding (16 builders; up to 28–31 when timed-out reads were retried). The same bytes
as one blob (3/3), the same items as a paged clustering table at the same concurrency with 2.5 M items/s delivered (3/3), and half
the concurrency (3/3) survived. Scaling M with the heap, the OOM repeats at 4 GiB (1/1) and 8 GiB (3/3, OOME at 111–144 s); at
15872 MiB no OOME came within the 180 s window (0/3) although the node spent ≥ 90 % of wall time in Full GCs with the heap pinned at
15.83 of 15.87 GB. The read-size fail threshold, when enabled at 64 MiB, did not prevent the OOM (3/3), because it is checked after
the row is built.

### 4.4 Limits of attribution and caveats

- **Workload validity (A1).** At c = 16 no read completes before the OOM, so the literal "≥ 1 completed read per client" rule could
  not hold for any OOM run; validity was taken from every client having issued reads and the server executing 16 of them
  (StatusLogger, dump stacks). A reviewer who rejects A1 would have no valid OOM run at c ≥ 16; the survivors at c = 8 completed
  452–487 reads each.
- **Death after the window (A2/A3).** T2, HS4G and HS8G/r3 threw their first OOME inside the window but were killed by the shipped
  `-XX:OnOutOfMemoryError=kill -9 %p` after it; the first OOME (hprof creation, D5) is the endpoint instant.
- **Top of the heap search.** The 180 s window, not the heap, bounded the search at 15872 MiB (time to OOME grows ∝ M); the shipped
  automatic heap for G1 on pc99 (31744M, A4) was not tested. "Largest failing budget = 8 GiB" is under this window.
- **Coordinator copy not observed.** §2.1 predicted a second (coordinator) row per read; at the OOM no row had finished, so all
  measured holder memory is replica-side row builds. The coordinator copy remains a prediction.
- **Control B margin.** c = 8 survives but with 78–80 % STW in the worst 60 s and post-GC peaks at the heap limit: the survivable
  region is narrow (§2.7's 30 % margin target is not met in heap terms; it is met in multiplicity, c 8 vs 16).
- **By-design reading.** The CQL docs say collections are read whole and are for small data; the workload (sets of 10⁶–4·10⁶ ints
  built by accepted appends, 16 concurrent readers, client retries without back-off) stays within the documented 2·10⁹-item limit
  and every shipped default. A deployment following the docs' advice (clustering table) is protected (arm I).
- **What stays on the nodes.** `pc99:/mydata/s4/u3-w1/` (62 GB: build `cassandra/`, `golden/` data 519 MB, `runs/<run>/logs/` with
  GC/system/client logs and 11 hprof files — cal-c16, T1–T3, P1–P3 ≈ 3.1 GB each, HS4G 6.1 GB, HS8G/r2/r3 11.6–12.1 GB), node data
  directories removed per run; no process running (checked 03:32 EST). `/mydata/s4/cassandra-base` and `/mydata/s4/ipc-recheck`
  untouched.
