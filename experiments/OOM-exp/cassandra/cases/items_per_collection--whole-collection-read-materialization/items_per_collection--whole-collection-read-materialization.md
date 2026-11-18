# U3 — items_per_collection: concurrent reads materialize appended collections whole on the heap  <!-- file: cassandra/cases/items_per_collection--whole-collection-read-materialization/items_per_collection--whole-collection-read-materialization.md -->

| Field | Value |
|---|---|
| Case ID | `U3` (U = unprotected-accumulation case; README "ID prefixes") |
| From | `OC-23` of the phase 1 OOM candidate list (campaign row U3 / P1) |
| Phase-1 case file | [`capacity-enforcement-exp/cassandra/stage3-ai-deep-read/cases/items_per_collection-doAdd-elements_size--autonomous.md`](../../../../capacity-enforcement-exp/cassandra/stage3-ai-deep-read/cases/items_per_collection-doAdd-elements_size--autonomous.md) |
| System / pinned source | Cassandra 5.0.9 (`systems/cassandra/source/`, `git describe` = `cassandra-5.0.9`; node build `pc99:/mydata/s4/cassandra-base`, release string `5.0.9-SNAPSHOT`) |
| Stage 1 (design) | OOM agent, phase 2 stage 1, Claude Opus 5.5 (`claude-opus-5-5`), 2026-11-17 (22:40–22:50 EST; frozen 22:50) |
| Stage 2 (verify) | pending (a fresh session) |
| Verdict | `pending` |

## Summary

- **Conclusion:** pending (stage 1 wrote the design only; nothing has run for this case).
- **Root cause (claimed, to be tested):** no capacity control bounds the heap a read spends on one stored collection. The only
  collection control, `items_per_collection_fail_threshold`, is off by default (−1) and when on counts only the fragment being
  written, so appends grow a non-frozen `set<int>` without limit; a read builds the whole collection as one row on the heap
  (≈ 150 B held per item, measured), twice per read (replica row, then coordinator row), and the read-size thresholds are off by
  default. Concurrent reads multiply it; `concurrent_reads` and `native_transport_max_threads` bound reads by count, not bytes.

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

Stage 2 by a fresh OOM-agent session (Claude Opus 5.5, `claude-opus-5-5`), 2026-11-17 22:50 – 2026-11-18 EST. Freeze hash checked
before anything ran: `db9d4ba2…adcf3` recomputed with the command in §2.10, **match**.

**Harness:** [`harness/`](harness/) — `lib.sh` (node start in its guard scope, samplers, stop), `golden.sh` (golden load lifetime and
shakedown), `run.sh` (one measured run per §2.5), `seq.sh` (runs a list; calibration stops at the first OOM, heap search at the first
survivor; refuses to start a run after 02:05 EST), `chain.sh` (heap search → fill to 3 → P after the main batch), `u3client.py`
(clients per §2.5), `analyze.py` (O1, O5, O7 and the endpoint rule), `hprof_histo.py` (O3, pure Python per §2.6), `arm-P.yaml`, the
`spec-*.txt` run lists. **Logs:** full logs, GC logs and hprof files on `pc99:/mydata/s4/u3-w1/runs/<run>/logs/`; excerpts
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
<!-- RUNS-CONTINUE -->

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

## 4. Conclusion (stage 2)

pending
