# B21 — `sai_vector_search_max_top_k`: Top-K (ANN) results always run unpaged and are capped in rows, not bytes (OC-565)  <!-- file: cassandra/cases/sai_vector_search_max_top_k--unpaged-topk-wide-rows/sai_vector_search_max_top_k--unpaged-topk-wide-rows.md -->

| Field | Value |
|---|---|
| Case ID | `B21` (B = bypass; README "ID prefixes"; provisional ID kept: the design is a bypass) |
| From | `OC-565` of the phase 1 OOM candidate list (primary of the "Unpaged Top-K" cluster: OC-565, OC-456, OC-455, OC-462, OC-557, legacy OC-40; triage 2026-11-20 rank 3) |
| Phase-1 case file | [`sai_vector_search_max_top_k-execute-pageSize--autonomous`](../../../../capacity-enforcement-exp/cassandra/stage3-ai-deep-read/cases/sai_vector_search_max_top_k-execute-pageSize--autonomous.md) |
| System / pinned source | Cassandra 5.0.9 (`systems/cassandra/source/`, `build.xml` `base.version` 5.0.9); built copy `ms0604:/mydata/s4/cassandra-base` (`build/apache-cassandra-5.0.9-SNAPSHOT.jar`) |
| Stage 1 (design) | phase-2 OOM agent, stage 1 session, 2026-11-21 08:04–08:14 EST; nothing run (read-only checks of `ms0604`, JIRA read via REST) |
| Stage 2 (verify) | fresh phase-2 OOM agent session, 2026-11-21 08:14–09:36 EST on `ms0604` (aarch64); 21 lifetimes (incl. LOAD and IC-OVER) |
| Verdict | **true positive** — `verified-OOM · deployment` (V4 via the dose arm IL; the named intervention I failed — owner check requested, §4) |

## Summary

- **Conclusion (stage 2):** **true positive.** At shipped defaults and a 2 GiB heap, 12 concurrent ANN queries (LIMIT
  1000, 120 KiB `text` rows, client page size 100 overridden to 1,000) end in a Java heap OOM 5/5 (CAL-2G, T-2G 3/3), and
  at 4 GiB 3/3 with 32 queries; the same rows read through a paged range query at the same concurrency survive 3/3
  (≈ 430 MiB/s delivered). Dumps: 91–97 % of the live heap is the replicas' eagerly built top-K maps and their response
  buffers. Cutting LIMIT to 250 removes the OOM 3/3; switching on the 64 MiB read-size threshold does **not** (3/3 OOM with
  every query refused), because it fires only after the top-K map exists. No OOM at 8 GiB / 15,872 MiB (32 read threads
  and the 10 s timeout bound it), but the node then serves ≈ 0 queries.
- **Hypothesis (stage 1):** a vector search `SELECT … ORDER BY emb ANN OF [...] LIMIT 1000` is always executed
  unpaged: the server raises any smaller client page size to the LIMIT (with a warning) and takes the unpaged branch
  (`SelectStatement.java:322-340`). Its only cap, `MAX_TOP_K` = 1,000, counts rows; the read-size byte thresholds ship
  off. With 1,000 rows of a 120 KiB `text` column (117 MiB of values, kept just under the 128 MiB internode message
  limit, which a 256 KiB row would exceed), each query holds ≈ 2–3 × 117 MiB at once on the single node (replica
  top-K map + its serialization buffer, then the coordinator's copy of the response + its re-sorted rows). Nothing
  sums those bytes across queries, so about 6 (band 3–8) concurrent such queries are predicted to exhaust a 2 GiB
  heap, while the same bytes read through a paged range query survive.
- **Root cause (measured, stage 2):** the Top-K path is exempt from paging and its only cap (`MAX_TOP_K`) counts rows;
  each replica materializes the whole top-K result (≈ 1 × the value bytes) and serializes it into one buffer, and nothing
  sums these bytes across concurrent queries. The only byte control ships off and, when on, is checked after the
  materialization. The internode reserve drops all but one ≈ 117 MiB response to self after it is built, so on one
  node the coordinator copies seldom add up; the replica side alone exhausts the heap.
- **Root cause (claimed, stage 1):** the paging control does not apply to Top-K (exempt mode, by design and warned), the
  Top-K cap is a row count, and the only byte control (`local_read_size_fail_threshold`) ships off.

## 1. Candidate

**The row** (`phase1-oom-candidates.md`, status set by the session to `picked: B21 (2026-11-21)`):

> | OC-565 | 2026-11-18 | `sai_vector_search_max_top_k-execute-pageSize--autonomous` | guided | Holder: the unpaged Top-K (ANN) result. SelectStatement raises any smaller client page size to LIMIT and runs Top-K queries unpaged, so all LIMIT rows exist at once. [details](runs/wave3.md#oc-565) | CP-2, CP-12, CP-7 | picked: B21 (2026-11-21) |

**Full text** (`runs/wave3.md#oc-565`):

> Holder: the unpaged Top-K (ANN) result. SelectStatement raises any smaller client page size to LIMIT and runs Top-K
> queries unpaged, so all LIMIT rows exist at once. They sit in the replica's VectorTopKProcessor priority queue of
> limit+1 rows (tombstones are kept outside it) and in the coordinator's single ResultMessage.Rows. Why nothing stops
> it: MAX_TOP_K = 1000 counts rows, not bytes. Read-size thresholds are off by default. No node-wide cap limits
> concurrent unpaged Top-K responses: native_transport_max_threads = 128, and the in-flight request byte limit counts
> request bytes, not response bytes. Size: stage 4 measured 48-80 MiB of coordinator heap per LIMIT-1000 query of
> 8 KiB rows (6-9x the value bytes), so 128 concurrent queries reach about 6-10 GiB, above an 8 GiB default heap. Rows
> can be up to max_mutation_size (16 MiB), so one query with large rows can reach GBs on its own.
>
> **Where:** src/java/org/apache/cassandra/index/sai/StorageAttachedIndex.java:501-503;
> src/java/org/apache/cassandra/cql3/statements/SelectStatement.java:322-329,338-340;
> src/java/org/apache/cassandra/index/sai/plan/VectorTopKProcessor.java:91,108-122;
> src/java/org/apache/cassandra/config/CassandraRelevantProperties.java:479

**Triage 2026-11-20, rank 3** (`runs/triage-2026-11-20.md`): "Top-K (ANN) queries are always unpaged … MAX_TOP_K =
1000 counts rows, not bytes, and read thresholds are off. … So 1,000 rows carrying a 256 KiB text column (about
256 MB of values, well within max_mutation_size) is about 1.5–2.3 GB for one query, and one or two queries pass a
2 GiB heap. Data is under 1 GB. Test time: under 1 h." Overlap note: "Same holder as U4 (a row count, not bytes), but
the client cannot page, which is the B17 pattern. Duplicates OC-456 and the legacy OC-40 (open). OC-455, OC-462 and
OC-557 are the multi-node multiplier (one response per contacted node). U8 is a different vector holder." Notes 4
and 5(b): "Unpaged Top-K: OC-565 (primary), OC-456, OC-455, OC-462, OC-557, plus the legacy OC-40" — "OC-456,
OC-455, OC-462 and OC-557 (rank 3). OC-455, OC-462 and OC-557 need tens of nodes for their per-node multiplier; the
single-node form is rank 3."

**The cluster's duplicates, quoted** (`runs/wave3.md`, `phase1-oom-candidates.md`):

- **OC-456** (`…validate-limit_count--autonomous`, autonomous): "Holder: each replica's eagerly materialized top-K
  rows, in the TreeMap/TreeSet built by takeTopKThenSortByPrimaryKey, plus the coordinator's InMemoryPartitionIterator.
  Why nothing stops it: the cap counts rows, not bytes. Non-vector columns of the selected rows (for example text
  chunks) can be up to max_mutation_size (16 MiB), and byte-based read thresholds are off by default. Rough size at
  defaults: 1000 rows x 100 KiB is about 100 MB per query per replica, and concurrent_reads 32 such queries is about
  3 GB."
- **OC-455** (`…validate-limit_count--autonomous`, autonomous): "Holder: the coordinator heap, which holds the top-K
  responses from every contacted node at once. … ScanAllRangesCommandIterator sends one full-range command to every
  contacted node and waits for all responses in one ReadCallback/DataResolver before merging. … each node's response
  limited only by internode_max_message_size (128 MiB by default). Several concurrent ANN queries can exhaust the
  coordinator heap."
- **OC-462** (`…validate-limit_count--autonomous`, guided): "Holder: the coordinator of an ANN top-k query
  (ReadCallback/DataResolver holding every replica's response). … Each response can carry up to LIMIT <= MAX_TOP_K =
  1000 rows. … about 1000 x 6 KiB (1536-dim float vectors) = 6 MiB per node, roughly doubled serialized plus
  deserialized. That is about 360 MiB per query on a 30-node cluster, and 128 native-transport threads can run such
  queries at once (several GiB). It grows linearly with wider non-vector columns."
- **OC-557** (`…execute-pageSize--autonomous`, autonomous): "MAX_TOP_K (1000) caps rows per response, not the rows
  the coordinator holds. A top-K range read uses ScanAllRangesCommandIterator: it sends the full-range command to every
  replica it needs at once … each replica returns up to LIMIT rows. The coordinator keeps all those responses until it
  has reduced them to LIMIT, and the result goes back unpaged. … At 1000 rows of about 10 KB … and 30 nodes, that is
  about 300 MB per query. Up to 128 NTR threads can run such queries concurrently …"
- **OC-40** (legacy, `…execute-pageSize--autonomous`, queued as U4 earlier): "Top-K queries run unpaged (page size
  forced to LIMIT, `SelectStatement.java:322-340`) and send one full-range command to every node at once, so a
  coordinator holds N_nodes × K rows per query (≈ 600 MiB on 100 nodes with 1536-dim vectors), and 128 concurrent
  queries × 48–80 MiB (stage 4) ≈ 6–10 GiB, with no byte cap."

**What this design covers.** OC-565 (the forced-unpaged single response, row-count cap, no byte bound) and OC-456
(the replica's eager top-K `TreeMap` plus the coordinator's in-memory re-sort) are covered in full: on one node the
coordinator and the replica are the same JVM, and both holders are measured. The concurrency part of OC-40, OC-462
and OC-557 (many such queries at once, nothing summing their bytes) is the design's dial. **Not covered:** the
per-node fan-out multiplier of OC-455, OC-462, OC-557 and OC-40 (one LIMIT-row response from each of N contacted
nodes held together on the coordinator); it needs N ≫ 1 nodes and is left open in those rows (owner's call whether
to close them against B21's verdict).

**Correction to the clue and the triage size, found in source (stage 1).** The ANN query has no partition key, so it
is a range read that `RangeCommands.java:81-82` routes to `ScanAllRangesCommandIterator`, which sends the command
**through `MessagingService` even to the local node** (`ScanAllRangesCommandIterator.java:95-103`;
`MessagingService.java:452-462`, "Message-to-self … going over MessagingService"). The replica's response is
therefore an internode message and is refused if larger than `internode_max_message_size`, whose default is
min(128 MiB, 128 MiB) = **128 MiB** (`DatabaseDescriptor.java:990-996`, `Config.java:252, 259`;
`OutboundConnection.java:330-332` throws `OversizedMessageException`). The triage's 1,000 × 256 KiB (250 MiB) response
would be refused after it is built, and the query would fail; per-query bytes on the wire are capped at ≈ 128 MiB.
Phase 1's stage 4 stayed under it (10,000 × 8 KiB = 78 MiB). This design sizes the row so the response is
117 MiB, and keeps a 256 KiB probe as an optional check (IC-OVER).

**Phase-1 case and its stage-4 result.** Constraint: the JVM property `cassandra.sai.vector_search.max_top_k`
(`CassandraRelevantProperties.java:479`, default `"1000"`, read once into `IndexWriterConfig.MAX_TOP_K`,
`IndexWriterConfig.java:57`); check at `StorageAttachedIndex.java:497-505` (`LIMIT > MAX_TOP_K` →
`InvalidRequestException`, commented "to avoid overflow of the vector graph internal data structure and avoid OOM when
filtering top-k"). Stage 4 run 1 (2026-10-26, advisor's macOS arm64 machine, 2 GiB heap, one node, 20,000 rows of
8 KiB, fetch size 10): **Confirmed — caps** in the unit and the cluster tier: LIMIT V returned V rows in one page with
the Top-K page-size warning and LIMIT V+1 was rejected, 3/3 at V = 1000, 5000, 10000; coordinator heap Δ median 48,
368, 656 MiB at LIMIT V; LIMIT 1000 cost 48–80 MiB at every V (6–9 × the 7.8 MiB of values, `heap used` peak minus
pre-query median — allocation including garbage, not live set). Not tested there: row size, tombstones, the
partition-restricted path, replica vs coordinator heap, concurrency. Recheck (2026-11-16, blind) E3 flagged the
missing node-wide cap on concurrent unpaged Top-K responses.

**JIRA prior art** (read only; nothing posted). Local survey `jira-oom-survey.csv` (title/notes/screen reason matching
`top-k|vector|SAI|ANN|jvector`): CASSANDRA-18673 (per-SSTable index component size, excluded) and CASSANDRA-20752 (SAI
segment builder flush, the C8 area) — neither is about query results. REST (`issues.apache.org`, reachable
2026-11-21 08:2x EST), project CASSANDRA:
- `text ~ "top-k" AND text ~ "OutOfMemory"` → 0; `summary ~ "vector" AND text ~ "OOM"` → 0;
- `text ~ "ScanAllRangesCommandIterator"` → 1: CASSANDRA-18715 (Add support for vector search in SAI, the feature
  itself, fixed 5.0-alpha2);
- `text ~ "max_top_k"` → 11, none about memory of results (18715, 18504 vector type, unrelated others);
- `text ~ "ANN" AND text ~ "paging"` → 7 (19030 docs, 18504, 19544 clustering restriction, 19018, 18715 …), none about
  result size;
- `text ~ "top-k" AND text ~ "page size"` → 8, of which **CASSANDRA-11745 "Add bytes limit to queries and paging"**
  (fixed 6.0-alpha3 / 7.0, not in 5.0.x) is the related general fix (byte-based paging); whether it covers Top-K is not
  checked (not in the pinned source);
- `text ~ "vector search" AND (heap OR memory)` → 15: CASSANDRA-21644 "Concurrent SAI vector inserts fail with 'Number
  of outstanding pooled objects has gone beyond the limit'" (fixed 5.0.10; the load-concurrency limit seen by phase 1's
  stage 4 — load concurrency is kept below the core count here), 20086, 19661, 21160, 18216, 19497 — none about query
  result memory.

**Verdict: `new`** for Top-K result bytes (no issue reports or bounds them in 5.0); the forced-unpaged behaviour is
**by design** (CASSANDRA-18715 code, with a client warning); the general missing byte limit is **known, fixed only in
6.0+** (CASSANDRA-11745). Not a known-fixed 5.0 bug, so not a positive control.

## 2. Design solution (stage 1; frozen)

**Direction and technique note.** **Bypass — exempt mode** of the paging control (the client's page size is
overridden for Top-K, by design and with a warning) on an **unprotected configuration** (the read-size byte thresholds
ship off), with **concurrency** of identical queries as the multiplicity dial — the B17 shape
([`bypass-playbook.md`](../../../bypass-playbook.md): compare the protected and the exempt path at matched data and
load). Interpretation: intentional exception (Top-K cannot page) plus a configuration-sizing gap (the only byte bound
ships off; `MAX_TOP_K` is a row count although its comment cites OOM). Not a suspected implementation defect.

**Mechanism** (all lines checked in `systems/cassandra/source`, 5.0.9).
1. `SelectStatement.execute`: for `restrictions.isTopK()` (`:299`) the LIMIT is required (`:318`), CL above ONE is
   downgraded (`:308-316`), and if `0 < pageSize < limit` the page size is set to the LIMIT and the client warned
   (`:322-329`, text `:122-123`). `:338-340`: `query.isTopK()` always takes the unpaged `execute` → `processResults`
   (`:417-429`, `:561`). The command passes `StorageAttachedIndex.validate` (`:497-505`): `LIMIT ≤ MAX_TOP_K = 1000`
   rows — the only size check, in rows.
2. Range read: `RangeCommands.java:81-82` → `ScanAllRangesCommandIterator` sends one full-range `ReadCommand` to every
   contacted replica by `MessagingService.sendWithCallback` (`ScanAllRangesCommandIterator.java:103`), **including the local node** (message to
   self over a real internode connection, `MessagingService.java:452-462`), and waits in one
   `ReadCallback`/`DataResolver` (`ScanAllRangesCommandIterator.java:95-96`).
3. Replica (READ stage, `concurrent_reads` 32; `ReadCommandVerbHandler.java:92-95`): `executeLocally` →
   `StorageAttachedIndexSearcher.search` (`:131-150`) → `VectorTopKProcessor.takeTopKThenSortByPrimaryKey`
   (`VectorTopKProcessor.java:168-183`) **eagerly** reads up to LIMIT matching rows (score-ordered retriever, each row's cell values copied to
   heap `byte[]`) into a `TreeMap<PartitionInfo, TreeSet<Unfiltered>>` (≈ 1.0 V, V = value bytes of the result).
   Only then is the size tracker attached (`ReadCommand.java:452` search, `:457` `withQuerySizeTracking`, which does
   nothing unless thresholds are on, `:655-660`). `createResponse` → `LocalDataResponse.build`
   (`ReadResponse.java:46-48, 197-204`) serializes into a `DataOutputBuffer` that doubles to 64 MiB then grows ×1.5
   (`DataOutputBuffer.java:158-181`, `DOB_DOUBLING_THRESHOLD_MB` 64, `CassandraRelevantProperties.java:203`):
   for V = 117 MiB the capacity steps 64 → 96 → **144 MiB**, with old + new live during each copy (96 + 144 = 240 MiB
   at the last step) while the 117 MiB `TreeMap` is still referenced. `buffer.buffer()` returns a duplicate of the
   144 MiB array (no trim), held by the response message until it is written.
4. Internode (to self): `OutboundConnection.enqueue` (`:325-345`) refuses a message > 128 MiB
   (`OversizedMessageException`) and charges the per-connection queue (4 MiB, `Config.java:250`) plus the endpoint
   reserve (128 MiB, `:252`) and global reserve (512 MiB, `:254`); if the endpoint reserve is short it prunes expired
   messages and otherwise **drops** the message (`onOverloaded`, `:456-468`; log "overloaded; dropping …") — the
   coordinator then waits `range_request_timeout` (10,000 ms) and fails the query. So at most ≈ 132 MiB of responses
   to self are pending at once; a second 117 MiB response arriving while one is pending is dropped **after** it was
   built. Inbound side: receive queue 4 MiB + endpoint reserve 128 MiB (`Config.java:257-261`), backpressure, not
   drop; the large message is deserialized into a heap buffer of V (`RemoteDataResponse`).
5. Coordinator (Native-Transport-Requests thread, `native_transport_max_threads` 128): `DataResolver` for Top-K
   neither trims nor counts against the limit (`DataResolver.java:137, 166`); the post-processor
   `VectorTopKProcessor.consumeSortByScoreAndTakeTopK` (`StorageAttachedIndexQueryPlan.java:146-154`;
   `VectorTopKProcessor.java:88-136`) deserializes every row (new `byte[]` per value, ≈ 1.0 V) into a priority queue
   and a `TreeMap` while the response buffer (V) is still referenced; `processResults` builds the `ResultSet`
   (references or copies the values; measured) and the native response is encoded into one pooled **direct** buffer
   of ≈ V (`CBUtil.java:60`, protocol v4).
6. Nothing sums these bytes across queries: no per-node byte budget for read results exists; the native in-flight
   limits count request bytes only.

**Claim.** U (live heap held by the in-flight Top-K results) grows ≈ linearly with the number c of concurrent ANN
queries, ≈ 2–3 × V per query in flight, until a heap OOM at 2 GiB, while K (rows per response ≤ `MAX_TOP_K` = 1000;
the client's requested page = 100 rows) stays within its count. U > C for the paging contract (C = one client page
≈ 100 × 120 KiB = 11.7 MiB per query) with K (rows per response, 1,000) above the requested page by the server's own
override → bypass, exempt mode; against `MAX_TOP_K` (rows) K ≤ C and the excess is bytes per row, which the cap does
not count (accounting mismatch by design).

**Protection map** (fixed before any run; V = 117.2 MiB value bytes per result in the planned workload).

| Domain | Holder (allocation → release) | Counter K | Limit at default | At the limit |
|---|---|---|---|---|
| Client paging (page size in rows) | all holders below | rows per response | **overridden for Top-K**: page := LIMIT (`SelectStatement.java:322-329`), unpaged branch `:338-340` | warning only → **exempt mode** |
| `MAX_TOP_K` (`cassandra.sai.vector_search.max_top_k`) | same | LIMIT (rows) | 1,000 rows (`CassandraRelevantProperties.java:479`) | `InvalidRequestException` for LIMIT 1001; bytes per row uncounted |
| Replica top-K map | `TreeMap<PartitionInfo, TreeSet<Unfiltered>>` in `takeTopKThenSortByPrimaryKey` (`VectorTopKProcessor.java:168-183`) → garbage after `createResponse` | — | ≤ LIMIT rows | none in bytes |
| Replica response buffer | `DataOutputBuffer` (`ReadResponse.java:197-204`) → released after the outbound write or the drop | — | none below `internode_max_message_size` | built first, refused or dropped afterwards |
| Internode message size | the serialized response | message bytes | **128 MiB** (`DatabaseDescriptor.java:990-996`) | `OversizedMessageException`; query fails after the build |
| Internode send reserves (to self) | pending outbound responses | queue/endpoint/global bytes | 4 MiB / 128 MiB / 512 MiB | **drop** (`onOverloaded`) → coordinator timeout; memory of the dropped message freed |
| Internode receive reserves | inbound frames (direct) | bytes | 4 MiB / 128 MiB / 512 MiB | backpressure (stop reading) |
| Coordinator response + re-sort | `RemoteDataResponse` (V heap) + `consumeSortByScoreAndTakeTopK` queue/map (≈ V) + `ResultSet` → released at request end | — | none | none |
| Encoded native response | pooled direct `ByteBuf` ≈ V (`CBUtil.java:60`) → released after the socket write | — | `MaxDirectMemorySize` | direct OOM (not this design's claim) |
| Read-size thresholds | replica: `withQuerySizeTracking` after the top-K build (`ReadCommand.java:457, 662-722`); coordinator: `ResultSetBuilder` (`SelectStatement.java:1045-1072`) | bytes | **off** (`read_thresholds_enabled: false`, thresholds null, `Config.java:526-530`) | nothing → unprotected configuration (arm I turns it on) |
| Read timeout (time) | replica read, coordinator wait | elapsed | `range_request_timeout` 10,000 ms (`conf/cassandra.yaml:1326`), `native_transport_timeout` 12 s (`Config.java:1399`) | read aborted (`QueryCancelledException`) / client timeout; frees that query's memory |
| Concurrency | queries in flight | NTR threads; READ stage threads | 128; 32 | queue; no byte sum |
| Native in-flight request bytes | request body (≈ 200 B) | request bytes | heap/10, per IP heap/40 | does not cover results |
| Baseline | SAI on-disk index + vector graph of the flushed segment (small: 4,000 × 16-dim), memtable heap pool (empty after the template), key cache (min(5 % H, 100 MiB)), chunk cache (direct, `file_cache_size` min(512 MiB, H/4)), networking pool 128 MiB direct | own | defaults | evict / flush |

**Configuration and budget audit.**
- Build: `ms0604:/mydata/s4/cassandra-base` (Cassandra 5.0.9 SNAPSHOT jar, as on every node since 2026-11-20), copied
  to `$ROOT/tree`, `ROOT=/mydata/s4/b21` (`/mydata` is root-owned on the m400s: `sudo mkdir -p /mydata/s4/b21 && sudo
  chown jason92: /mydata/s4/b21` if `/mydata/s4` is not writable). JDK 11.0.33 (checked 2026-11-21 08:07 EST),
  G1 with the shipped `jvm11-server.options` (16 MiB regions, `MaxGCPauseMillis=300`), `HeapDumpOnOutOfMemoryError`
  and `OnOutOfMemoryError="kill -9 %p"` from `jvm-server.options`. Record `uname -r`, `java -version`, jar sha256,
  the resolved `-Xmx`/`-XX:MaxDirectMemorySize` from `ps` in every `run.meta`.
- **SAI vectors on aarch64** (checked in the build, stage 1): `lib/jvector-1.0.2.jar` is pure Java; its Panama
  `SimdOps`/`PanamaVectorizationProvider` live only under `META-INF/versions/20/`, so JDK 11 uses
  `DefaultVectorizationProvider` (scalar Java); no native library ships with it (only `sigar` has `.so` files, x86
  builds, unused by SAI). No earlier case ran an SAI vector index on an m400 (U8 used vectors without an index), so
  the first step of stage 2 is a **go/no-go gate** (VERIFY below). CASSANDRA-21644 (fixed 5.0.10, not in 5.0.9):
  concurrent inserts into a memtable vector index beyond `availableProcessors() + 1` (= 9 here) fail; the load uses
  concurrency 4.
- **Every capacity constraint at its shipped default (V6)** in arms T and M: `MAX_TOP_K` 1000 (no `-D`);
  `read_thresholds_enabled: false`, all read-size thresholds null; `internode_max_message_size` unset (→ 128 MiB);
  internode queue/reserve capacities 4 / 128 / 512 MiB; `native_transport_max_threads` 128; `concurrent_reads` 32;
  `range_request_timeout` 10,000 ms, `read_request_timeout` 5,000 ms, `native_transport_timeout` 12 s (**not
  raised**); memtable, key/row/chunk caches at defaults; `num_tokens` 16; `AllowAllAuthenticator` (no guardrail in
  play: `vector_dimensions` and column-value guardrails are off and would be skipped for superusers anyway).
  Only arm I changes a constraint.
- `cassandra.yaml` diff (environment only): the five directories under `$ROOT/node/`; addresses stay `localhost`.
  Save `yaml.diff` per lifetime.
- **Budgets** (V7; standing rule ≥ 512 MiB, 2 GiB ideal, search upward):
  - **Primary: heap 2,048 MiB** (`MAX_HEAP_SIZE=2G`, `HEAP_NEWSIZE` irrelevant under G1). Direct: **left to
    `cassandra-env.sh`**, which on this node resolves `MaxDirectMemorySize` from RAM even with a hand-set heap: 62 GiB
    RAM → ½ RAM > 15,872 → `CALCULATED_MAX_DIRECT_MEMORY_SIZE` = 15,872 / 2 = **7,936 MiB** (record from `ps`). This
    is exactly what the shipped scripts give an operator who sets only the heap; it also keeps the encoded responses
    (direct, ≈ 117 MiB each) from ending the run with a direct OOM that this design does not claim.
  - **Upward search:** 4,096 MiB, 8,192 MiB, then **15,872 MiB** (what `cassandra-env.sh` resolves for this node, G1
    `heap_limit` 15,872 since ½ RAM exceeds it); direct stays 7,936 MiB (resolved) in every lifetime.
  - **No container budget.** Victim in `systemd-run --user --scope -p MemoryMax=<heap + 7936M + 6G> -p
    MemorySwapMax=0` for isolation only (swap off). A scope `oom_kill` makes the lifetime **invalid**; record
    `memory.events` at the end of every lifetime.
- **Node (read-only check, 2026-11-21 08:07 EST):** `ms0604` aarch64, 8 cores, 62 GiB (52 GiB free, 61 available),
  `/mydata` 39 GiB with **30 GiB free**, swap 8 GiB (unused), cgroup v2 (`memory` controller), load 0.00, **no java
  process**; `/mydata` holds `s2r2`, `u1r2` (never touched) and `s4/cassandra-base` only. Clock: the node's local
  time is MST; log in EST (`TZ=America/New_York`).
- **Disk plan (30 GiB):** tree 0.5 GiB + template ≈ 0.6 GiB (469 MiB of values, LZ4 on random alphanumerics, SAI
  index) + one node copy per lifetime ≈ 0.6 GiB (deleted at lifetime end, logs kept) + hprofs: 2 GiB each at 2 GiB
  heap. **Keep at most 4 hprofs on disk at once**: after `hprofhist.py`/`hprofstacks.py` have run, delete CAL and
  REP dumps (keep the three T-2G dumps until §3 is written). For heaps ≥ 8,192 MiB write the dump only if free space
  ≥ heap + 4 GiB; otherwise run that lifetime with `-XX:-HeapDumpOnOutOfMemoryError` (instrument change only,
  recorded) and rely on the first error stack, the sampler and one `GC.class_histogram`.
- **RAM:** victim ≤ 15.5 + 7.75 GiB + client JVM 6 GiB + page cache — fits 62 GiB.

**Ceiling arithmetic.** Row: `id int`, `emb vector<float, 16>` (64 B), `body text` of W = **122,880 B (120 KiB)**
random `[a-z0-9]`. Per result of L = 1,000 rows: V = 122.88 MB = **117.2 MiB** of `body` values; serialized ≈ V + 1,000
× (64 B vector + ≈ 40 B framing) ≈ 117.3 MiB < 128 MiB (margin ≈ 10.7 MiB, 8 %). Per query, live heap:
- replica, building: TreeMap V + DOB 96 + 144 MiB during the last growth → **≈ 357 MiB (3.0 V)** peak, then
  144 MiB (the response) until written or dropped;
- coordinator: `RemoteDataResponse` V + deserialized rows V (+ `ResultSet` 0–1 V) → **≈ 234–351 MiB (2–3 V)**;
- time-averaged over a query's life ≈ 2.5 V ≈ 290 MiB (band 2–3 V = 234–351 MiB).
Baseline (read-only node, memtables empty): 200–350 MiB; humongous objects (each DOB step ≥ 8 MiB) fragment regions,
so the usable heap above baseline is ≈ 1,500–1,750 MiB at 2 GiB.
- **2,048 MiB:** c × 290 MiB > ≈ 1,600 MiB → **c_T ≈ 6 (band 3–8)**; c = 1 and 2 (≤ 700 MiB) predicted safe.
- **4,096 MiB** (usable ≈ 3,600): c ≈ 13 (band 10–16).
- **8,192 MiB** (usable ≈ 7,600): c ≈ 26 — near the READ-stage bound (32 replicas building at once) and, on 8 cores,
  latency ≈ c/8 × the single-query time, so the 10 s range timeout starts aborting replica reads (freeing their
  memory); **uncertain**.
- **15,872 MiB:** c ≈ 50 needed > 32 READ threads × 3 V ≈ 11 GiB worst case → **predicted no OOM** (the boundary).
Σ contract capacities that bound these bytes: none (paging exempt, `MAX_TOP_K` in rows, thresholds off); the implicit
bounds are 32 READ threads × 3 V ≈ 11 GiB (replica side), 128 NTR threads × 3 V ≈ 44 GiB (coordinator side), the
≈ 132 MiB of pending responses to self (the rest are dropped after being built), and the 10 s timeout.
Direct: ≤ a few concurrent encoded responses × 117 MiB + chunk cache ≤ 512 MiB + networking pool 128 MiB ≪ 7,936 MiB.
The client JVM receives up to c × 117 MiB at once.

**Workload and environment.**
- Node `ms0604` only: victim = one Cassandra node (coordinator = replica); client = one Java-driver JVM on the same
  node (loopback), `-Xmx6g`. Before every lifetime refuse to start if a `CassandraDaemon` runs (wait in bounded polls
  ≤ 20 min, then record the block). Work only in `ROOT=/mydata/s4/b21`; copy `/mydata/s4/cassandra-base` read-only.
- Schema: `CREATE KEYSPACE b21 WITH replication = {'class':'SimpleStrategy','replication_factor':1}`;
  `CREATE TABLE b21.docs (id int PRIMARY KEY, emb vector<float, 16>, body text)` with default table options (LZ4
  16 KiB chunks, STCS); `CREATE INDEX docs_emb ON b21.docs(emb) USING 'sai'` (default similarity: cosine).
- Data: **N = 4,000 rows**, `id` 0–3,999, `emb` = 16 floats from `Random(id)` uniform in (0.1, 1.0), `body` = 122,880
  chars from `[a-z0-9]` with `Random(1_000_003 + id)` → 469 MiB of values (each write 120 KiB, ≪ `max_mutation_size`
  16 MiB; `max_value_size` 256 MiB). An ANN query returns 1,000 of the 4,000 rows (25 %), different per query vector.
- **Load once** (lifetime `LOAD`, heap 8G, not a reading): schema; inserts at concurrency **4** (CL ONE; each failed
  insert retried up to 5 times; report failures) with a prepared `INSERT INTO b21.docs (id, emb, body) VALUES
  (?, ?, ?)`, `emb` bound as raw bytes (`setBytesUnsafe`: 16 big-endian IEEE-754 floats, 64 B — the fixed-length
  vector serialization). Fallback if the Java driver cannot bind it: the bundled Python driver 3.29.0
  (`lib/cassandra-driver-internal-only-3.29.0.zip`, has `VectorType`; used by phase 1's stage 4) for the load only.
  Then `nodetool flush b21`, `nodetool compact b21`, wait until `nodetool compactionstats` shows no task and the
  index is queryable; `SELECT count(*) FROM b21.docs` (paged) = 4,000; `nodetool drain`; SIGTERM; `cp -a $ROOT/node
  $ROOT/template`; `rm -rf $ROOT/template/saved_caches/*`. **Every measured lifetime starts from a fresh `cp -a` of
  the template.**
- Client `B21Load` (adapted from B17's `B17Load.java`; Java driver 3.12.1, **protocol v4**, CL ONE, 4 connections,
  `readTimeoutMillis` 120,000, `FallthroughRetryPolicy`). Query variants (each query uses a fresh random query vector
  / start token from `Random(42 + thread)`; the vector is written as a literal into a non-prepared statement):
  - **T (test):** `SELECT id, body FROM b21.docs ORDER BY emb ANN OF [f1, …, f16] LIMIT 1000`, **fetch size 100**
    (the server raises it to 1,000 and warns; the client reads the one page).
  - **M (matched control, protected path):** `SELECT id, body FROM b21.docs WHERE token(id) > ? LIMIT 1000`, fetch
    size 100, the client iterates all pages → the same 1,000 rows × 120 KiB = 117.2 MiB delivered per query, in 10
    pages of 11.7 MiB (paging honoured). A start token in the last 25 % of the ring wraps short: draw the start from
    the first 70 % of the token space so every query returns 1,000 rows (check rows/query in the output).
  - **I (intervention arm, same query as T):** arm **I** node config = A + `read_thresholds_enabled: true` +
    `local_read_size_fail_threshold: 64MiB` (the byte control that ships off; U4/B17's intervention). Predicted:
    each T query is refused with a read-size failure after the replica has built its top-K map (≈ 1 V) but before the
    full response buffer, the transit and the coordinator copies; rejection rate recorded (this intervention stops the
    query, it does not serve it — the honest outcome of the only byte control 5.0.9 has).
  - **I-L (dose intervention, optional):** query T with **LIMIT 250** (V/4 = 29 MiB), arm A: the same path with the
    per-response bytes bounded; served.
  - Closed loop: c threads, each sends its next query when the last returns (success or error); step schedule
    `c:secs` lists. Output: per query a JSON line (start, end, ms, variant, rows, value bytes, pages, warnings count,
    error class + message); per second a CSV (`t, step_c, inflight, ok, err_timeout, err_readfail, err_invalid,
    err_other, rows_s, p50ms, p99ms, maxms, lastErr`); a `SUMMARY` line per step.
- **Lifetimes** (each from a fresh template copy; heap/direct as listed, direct = resolved 7,936M unless noted):

| Label | Arm | Heap | Query | Schedule | Reps |
|---|---|---|---|---|---|
| `VERIFY+IC+PROBE` (not readings) | A | 8G | T / M / I-L | **GATE (SAI on aarch64):** `DESCRIBE INDEX`, index status queryable, T with LIMIT 10 returns 10 rows; if the index build failed or the ANN query errors → stop, record, `ready` = blocked. **IC:** (a) T at fetch 100 → 1,000 rows, `has_more_pages` false, one warning "Top-K queries do not support paging and the page size is set to 100, which is less than LIMIT 1000. …"; (b) LIMIT 1001 → `InvalidRequest` "… not greater than 1000. LIMIT was 1001"; (c) M → 1,000 rows in 10 pages; (d) the response size in the coordinator: `LargeMessageCompletedBytes` of the self `Connection` grows by ≈ 123 MB per T query. **PROBE:** T at c = 1 ×5 (10 s apart): latency, rows, errors; then c steps `2:30,4:30` | 1 |
| `IC-OVER` optional | A | 8G | T on table `b21.big` (1,100 rows × 256 KiB) | T LIMIT 1000 ×2: predicted failure (`OversizedMessageException` "Message of size … exceeds allowed maximum of 134217728 bytes" in `system.log`, client read failure or timeout) — shows the triage's 256 KiB size cannot be served | 1 |
| `CAL-2G` | A | **2G** | T | warm-up T c = 1 ×3; then steps `1:30,2:45,3:45,4:45,6:45,8:45,12:45,16:45`; stop at first OOM → **c_T** (the step's c) | 1 |
| `T-2G-1..3` | A | 2G | T | warm-up: T c = 1 ×3, 20 s idle; then `c_T:120` | 3 (+2 if 2/3) |
| `M-2G-1..3` | A | 2G | M | same warm-up (M ×3); then `c_T:120` | 3 |
| `I-2G-1..3` | **I** | 2G | T | same warm-up; then `c_T:120` | 3 |
| `IL-2G-1..3` optional | A | 2G | I-L | same warm-up; then `c_T:120` | ≤ 3 |
| `CAL-4G` | A | 4G | T | steps `8:45,10:45,13:45,16:45,24:45,32:45` | 1 |
| `CAL-8G` | A | 8G | T | steps `16:45,24:45,32:45,48:45,64:45` | 1 |
| `CAL-15872M` | A | 15,872M | T | steps `32:45,48:45,64:45,96:45,128:45` | 1 (if time) |
| `REP-<H>-1..2` | A | the largest failing heap | T | warm-up, then its failing c for 120 s | 2 (if time) |

  If PROBE shows a single T query (c = 1) above 8 s, CAL-2G starts at its first step anyway but every 45 s step is
  stretched to 90 s (record). If CAL-2G reaches c = 16 without OOM, the design has not reached its endpoint at 2 GiB:
  run `CAL-2G` once more with steps `24:60,32:60` (READ-stage bound), then stop the 2 GiB claim and go to the
  verdict rules (retry with what was measured).

**Harness** (under `harness/` in this folder, adapted from B17's
[`../cql-row-limit--in-order-by-limit-after-materialization/harness/`](../cql-row-limit--in-order-by-limit-after-materialization/harness/)):
1. `setup.sh`: create `$ROOT`, `cp -a /mydata/s4/cassandra-base $ROOT/tree`, `cp -a $ROOT/tree/conf
   $ROOT/conf-pristine`, compile `B21Load.java` and `C2Sampler.java` into `$ROOT/cls` against `$ROOT/tree/lib`.
2. `victim-ctl.sh` (from B17's): `ROOT=/mydata/s4/b21`; arms `A`, `I`, `LOAD`; `MAX_HEAP_SIZE` explicit,
   `MAX_DIRECT_MEMORY_SIZE` **unset** (cassandra-env resolves it; record it); scope unit `b21-<label>-<epoch>` as
   above; NMT summary, GC log (`-Xlog:gc*,safepoint:file=<run>/gc.log:time,uptime`), `CASSANDRA_HEAPDUMP_DIR=<run>`;
   `run.meta`.
3. `B21Load.java` (from `B17Load.java`): `schema`, `load <rows> <bytes> <conc>`, `verify`, `one <T|M|IL> [fetch]`,
   `run <T|M|IL> <steps c:secs>`, outputs above.
4. `C2Sampler.java` + JMX names: heap used, G1 old gen after GC, NTR and ReadStage active/pending, `java.nio` direct
   `MemoryUsed`, and `org.apache.cassandra.metrics:type=Connection,scope=127.0.0.1,name=` `LargeMessagePendingBytes`,
   `LargeMessageCompletedBytes`, `LargeMessageDroppedTasksDueToOverload`, `LargeMessageDroppedTasksDueToTimeout`
   (self endpoint; confirm the scope string at VERIFY), every 1 s.
5. `run-arm.sh` / `batch.sh` / `wait-end.sh` (from B17): one lifetime per call; launch with `( setsid nohup … <
   /dev/null > /dev/null 2>&1 & )`; bounded background polls; on exit: OOM evidence (`OutOfMemoryError` lines in
   `stdout.log`/`system.log`, hprof, `memory.events`), `nodetool drain` + SIGTERM by PID if alive; small files to
   `logs/<label>/`, full logs and hprofs stay in `$ROOT/runs/<label>/`.
6. `gcwin.py`, `hprofstacks.py` from B17; `hprofhist.py` with B21 buckets: `byte[]` ≥ 64 MiB (DOB response buffers:
   64/96/144 MiB), `byte[]` 100–140 KiB (row values; split by owner: reachable from `VectorTopKProcessor` /
   `TreeMap`/`PriorityQueue` on a ReadStage thread vs on a Native-Transport-Requests thread, from
   `RemoteDataResponse`/`LocalDataResponse`, from `ResultSet`/`ResultMessage$Rows`), other.

**Instruments (U independent of K).**
- **K:** rows per response (client: rows of the first page, `has_more_pages`, the Top-K warning), LIMIT; requested
  page size (100).
- **U:** (a) at an OOM: the hprof → `hprofhist.py` buckets (value `byte[]` by owner and the ≥ 64 MiB response
  buffers) and `hprofstacks.py` (which threads are in `takeTopKThenSortByPrimaryKey`, `LocalDataResponse.build` /
  `DataOutputBuffer.expandToFit`, `consumeSortByScoreAndTakeTopK`, `processResults`, and the failing allocation's
  stack = first `OutOfMemoryError`); (b) during every lifetime: the JMX sampler (1 s) — heap used, old gen after
  each GC (live-set proxy), READ/NTR active, direct, self-connection large-message pending/dropped bytes; (c) the GC
  log (`gcwin.py`: pause share per 60 s window, humongous regions); (d) in `CAL` steps at c ≤ 4 and in one M and one T
  lifetime at c_T, one `jcmd <pid> GC.class_histogram` at step second 30 (intrusive, once per lifetime).
- Completed operations: per-second ok/error counts by class, rows/s and value bytes/s (M and T must deliver bytes at
  comparable rates, recorded).
- Validity per lifetime: `-Xmx`, `MaxDirectMemorySize` from `ps`; `MAX_TOP_K` default (no `-D` in `ps`); template
  intact (`count(*)` 4,000 in VERIFY only); `memory.events` `oom_kill` 0; sampler gap ≤ 3 s.

**Predicted response** (before readings).
- VERIFY/IC: as listed; single T latency on the m400 1.5–5 s (ANN + 1,000 random row reads of 120 KiB + 117 MiB
  over the loopback twice: internode and native).
- PROBE c = 2, 4: some T queries fail with a read timeout after 10 s and the log shows "overloaded; dropping … message
  (… endpoint …)" for the self connection (`LargeMessageDroppedTasksDueToOverload` > 0) — the internode reserve drops
  a second concurrent 117 MiB response after it was built. Their memory is freed; the replica phase still overlaps.
- **CAL-2G:** old-gen-after-GC rises ≈ 250–350 MiB per added concurrent query; GC pause share rises from c ≈ 4;
  **heap OOM at c_T = 6 (band 3–8)**, first error on a ReadStage thread in `DataOutputBuffer.expandToFit` (≈ 60 %) or
  on an NTR thread deserializing the response/rows (≈ 40 %); dump: value `byte[]` + response buffers ≥ 70 % of the
  live heap.
- **T-2G ×3:** OOM 3/3 within 120 s at c_T. **M-2G ×3:** survive 3/3 (≤ c_T × 2 pages × 11.7 MiB in flight ≈ 140 MiB
  at c = 6), with ≥ the same value bytes/s delivered as T before its OOM. **I-2G ×3:** survive 3/3; 100 % of T
  queries refused ("… attempted to read … bytes but max allowed is 64 MiB …"), live heap ≤ c_T × (1 V + 64 MiB).
  **IL-2G:** survive, all queries served (250 rows each).
- **Budget search:** OOM at 4,096 MiB (c ≈ 13, band 10–16); 8,192 MiB uncertain (timeouts); no OOM at 15,872 MiB up
  to c = 128 (READ bound + 10 s timeout).
- A **direct OOM**, a scope kill or a GC service loss (≥ 90 % pause over 60 s) without a heap OOM is recorded as such
  and does not count toward the heap claim.

**Stopping budget.** Wall clock: stage 2 from 09:00 EST; **no lifetime starts after 13:15 EST**; every process stopped
and §3–§4 written by **14:00 EST**. Per lifetime: ≤ 12 min including start (the m400 takes ≈ 1–2 min to start a node);
a sweep stops at its first OOM. No escalation after an OOM beyond the listed steps.

**Controls and intervention** (V2, V4). Matched control M (paged range read of the same 1,000 rows × 120 KiB per
query, same c, same data, budget, build and warm-up) ≥ 3 runs; intervention I (T with the read-size byte threshold
on) ≥ 3 runs; optional dose intervention IL (T with LIMIT 250). The diagnostic arm I differs from A only in the two
yaml lines; save the diff.

**Verdict rules (pre-registered).** True positive: T-2G OOM ≥ 3/3 (heap), M-2G 0/3, I-2G 0/3, dumps showing the
claimed holders (value `byte[]` of Top-K results + response buffers) as the majority of live heap. If T needs c above
16 at 2 GiB, the heap claim moves to the largest c tried with its readings (retry). If the 2 GiB OOMs come only as a
direct OOM, record it (retry: claim mismatch). If VERIFY fails the gate (SAI vector index not usable on aarch64),
the case is **blocked** (retry on an x86 node).

**Time plan (EST).** 09:00–09:25 setup, harness, compile; 09:25–09:50 `LOAD` (469 MiB at concurrency 4, flush,
compact, index, template); 09:50–10:15 `VERIFY+IC+PROBE` (+ `IC-OVER` only if ahead of plan); 10:15–10:40 `CAL-2G`;
10:40–11:55 `T-2G` ×3, `M-2G` ×3, `I-2G` ×3 (≈ 8 min each); 11:55–12:20 `CAL-4G`; 12:20–12:45 `CAL-8G`;
12:45–13:15 `IL-2G` or `CAL-15872M` or `REP` (whichever is next in the drop order is dropped first); 13:15–14:00
`hprofhist`/`hprofstacks`, §3–§4, write-back, cleanup.

**Drop order** (first dropped first): `IC-OVER` → `REP` → `CAL-15872M` → `IL-2G` → `CAL-8G` → the
`GC.class_histogram` probes → `CAL-4G`. Never dropped: GATE, `CAL-2G`, `T-2G` ×3, `M-2G` ×3, `I-2G` ×3.

**Cleanup.** Stop every process started (by PID), confirm no `CassandraDaemon` and no client JVM remain; keep
`/mydata/s4/b21/{template,runs}` (logs, at most the hprofs listed above) and report the size; never touch
`/mydata/s2r2`, `/mydata/u1r2` or `/mydata/s4/cassandra-base`.

`sha256 of §1–§2 at freeze: 6becde86f36f8f610eb9f392b5d11b37e60c1db44d2b17245b9257a18210c678` (computed as `awk '/^## 1\. Candidate/{f=1} /^.sha256 of §1–§2 at freeze/{f=0} f' <this file> | sha256sum`, i.e. from the `## 1. Candidate` line up to, not including, this line; 2026-11-21 08:13 America/New_York) · amendments after the freeze: A1 (below)

**Amendments after the freeze (stage 2).** Hash re-checked by the stage-2 session at 08:14 EST: matches.
- **A1 (2026-11-21 08:24 EST, after `LOAD`, before any reading).** The resolved `-XX:MaxDirectMemorySize` on `ms0604`
  is **15,872 MiB**, not 7,936 MiB: with G1 `cassandra-env.sh` takes the non-CMS branch, `heap_limit` = 31,744, and
  ½ RAM (`free -m` 64,249 → 32,124) exceeds it, so direct = 31,744 / 2 = 15,872M (seen in `ps` of `LOAD`; the design
  used the CMS `heap_limit` 15,872). Direct stays **left to `cassandra-env.sh`** as the design says, so every lifetime
  runs with the resolved 15,872 MiB (recorded per lifetime). Consequence for the isolation scope only: `MemoryMax` =
  heap + **15,872M** + 6G (was heap + 7,936M + 6G) so the direct limit still fits inside it. Also noted, no change:
  the automatic heap for this node is 31,744 MiB (not 15,872 MiB); `CAL-15872M` stays the design's top step of the
  upward search.

## 3. Runs (stage 2)

Stage-2 session (fresh, not the design session), 2026-11-21 08:14–09:36 EST. Freeze hash re-checked first: matches.
Amendment A1 (resolved direct limit, scope size) was recorded before the first reading.

**Environment.** `ms0604` (Utah m400, **aarch64**, 8 cores, 64,249 MiB RAM by `free -m`, kernel 5.15.0-191-generic,
cgroup v2, swap 8 GiB kept at 0 for every measured process by `MemorySwapMax=0`), OpenJDK 11.0.33, G1 with the shipped
options (16 MiB regions, `MaxGCPauseMillis=300`, `HeapDumpOnOutOfMemoryError`, `OnOutOfMemoryError="kill -9 %p"`).
Build: `/mydata/s4/cassandra-base` copied to `/mydata/s4/b21/tree`, jar `apache-cassandra-5.0.9-SNAPSHOT.jar` sha256
`b3fa4929…ed128df` (in every `run.meta`). No other Cassandra process ran on the node during the session (checked before
every lifetime). Victim and client on the node (loopback); client JVM `-Xmx6g` in its own scope. Per lifetime `ps`
showed `-Xmx` as listed, **`-XX:MaxDirectMemorySize=15872M`** (resolved by `cassandra-env.sh`, A1), no
`cassandra.sai.vector_search.max_top_k` property (default 1,000); scope `MemoryMax` = heap + 15,872M + 6G,
`memory.events` `oom_kill 0` in every lifetime. `yaml.diff` = the five directories only (arm I: + the two threshold
lines). Sampler gap ≤ 1 s in every lifetime. Harness: [`harness/`](harness/) (adapted from B17's; `hprofowner.py` is new:
a multi-source BFS from all GC roots that gives every large `byte[]` its shortest path from a root, used for the design's
"split by owner"; dumps were analysed on `pc96` after copying, so the node's CPU stayed with the runs). Full logs:
`ms0604:/mydata/s4/b21/runs/<label>/`; excerpts in [`logs/<label>/`](logs/) (`qsum.txt` per-step summary,
`hprofhist.txt`, `hprofowner.txt`, `oom-thread-stack.txt`, `gcwin.txt`, `samples.csv`, `client.out`).

**LOAD** (08:18–08:21 EST, heap 8G; not a reading). 4,000 rows × 122,880-char body at concurrency 4: 13 s, 0 retries,
0 failures (the Java driver 3.12.1 logs that it cannot parse `vector<float, 16>` in schema metadata; harmless, the
vector is bound as raw bytes). Flush + major compaction → 1 SSTable, 495 MB live (LZ4 ratio 1.004), compacted partition
126,934 B; index `docs_emb` "became queryable after successful build"; `count(*)` 4,000; scan 4,000 distinct ids,
5/5 bodies match. Template 474 MiB.

**VERIFY + IC + PROBE** (08:22–08:26, arm A, 8G).
- **GATE passed:** `system_schema.indexes`: `docs_emb` CUSTOM `{class_name=sai, target=emb}`;
  `system_views.sai_column_indexes` row queryable; T with LIMIT 10 → 10 rows (517 ms). SAI vector search works on
  aarch64 with jvector's scalar provider.
- **IC (a):** T LIMIT 1000 at fetch 100 → 1,000 rows, 1 page, `has_more_pages` false, one warning "Top-K queries do not
  support paging and the page size is set to 100, which is less than LIMIT 1000. The page size has been set to 1000 to
  match the LIMIT." (4,930 ms). **(b):** LIMIT 1001 → `InvalidQueryException` "Use of ANN OF in an ORDER BY clause
  requires a LIMIT that is not greater than 1000. LIMIT was 1001". **(c):** M → 1,000 rows in 10 pages (1,225 ms).
  **(d):** self `Connection` `LargeMessageCompletedBytes` +124,201,673 B (118.4 MiB) for one T query; the log names the
  message 117.275 MiB.
- **PROBE:** T c = 1 ×5 (10 s apart): 4,023 / 3,849 / 3,425 / 3,296 / 3,293 ms, 1,000 rows each (below 8 s, so CAL steps
  were not stretched). c = 2 (30 s): 16 ok, 1 failure; c = 4 (30 s): 26 ok, 1 failure. Each failure is a
  `ReadTimeoutException` with the log line "localhost/127.0.0.1:7000->…-LARGE_MESSAGES-… overloaded; dropping
  117.275MiB message (queue: 117.275MiB local, 113.275MiB endpoint, 113.275MiB global)": the internode send reserve
  drops a second concurrent response to self **after it was built**, as predicted. Not predicted: the coordinator fails
  at once (the drop calls the callback), not after 10 s; across all lifetimes the number of such fast
  `ReadTimeoutException`s equals the `LargeMessageDroppedTasksDueToOverload` count (CAL-2G 283 = 283, IL-2G-1 1,695 =
  1,695), with latencies 0.2–6 s.

**CAL-2G** (08:26–08:32, arm A, 2G; warm-up T ×3, then steps 1:30, 2:45, 3:45, 4:45, 6:45, 8:45, 12:45, 16:45;
histogram at c = 4, s30). Per step (from [`logs/CAL-2G/qsum.txt`](logs/CAL-2G/qsum.txt)):

| c | ok / 45 s (c=1: 30 s) | fast read timeouts (self-response drops) | value MiB/s served | old gen after GC, max | ReadStage active, max |
|---|---|---|---|---|---|
| 1 | 8 | 0 | 31 | 1,278 MiB | 1 |
| 2 | 25 | 1 | 65 | 1,546 MiB | 1 |
| 3 | 33 | 0 | 86 | 1,574 MiB | 1 |
| 4 | 39 | 2 | 102 | 1,626 MiB | 1 |
| 6 | 31 | 75 | 81 | 1,582 MiB | 4 |
| 8 | 22 | 122 | 57 | 1,787 MiB | 7 |
| 12 | 8 (42 s) | 83 | 22 | 1,516 MiB | 11 |

**Heap OOM** at +315 s, second 42 of the c = 12 step (`java.lang.OutOfMemoryError: Java heap space`, dump written,
`kill -9`); 111 full GCs, max 41 % STW over 60 s (service-loss criterion not met before the OOM). → **c_T = 12** (above
the predicted band 3–8; within the design's ≤ 16, so the design continued as written). Dump (1,818 MiB live shallow):
9,041 `byte[]` of exactly 122,880 B (1,060 MiB = 9.0 results) + 6 arrays ≥ 8 MiB (657 MiB: response
`DataOutputBuffer`s of 60/120/120/120 MiB, one 120 MiB message being written to the self connection, the coordinator's
117.3 MiB `RemoteDataResponse` buffer). Owner split (`hprofowner.py`): **replica 1,392 MiB** (top-K maps being built in
`ScoreOrderedResultRetriever`/`takeTopKThenSortByPrimaryKey`, top-K `TreeMap`s being serialized in
`LocalDataResponse.build`, their `DataOutputBuffer`s), **outbound to self 120 MiB**, **coordinator 205 MiB**
(`consumeSortByScoreAndTakeTopK`: 117.3 MiB response + 87.4 MiB rows in its `PriorityQueue`) = 1,717 MiB = **94 % of
the live heap**. **First error (V5):** the dump's thread whose top frame is `OutOfMemoryError.<init>` is a ReadStage
thread in `ByteBuffer.allocate` ← `DataOutputBuffer.expandToFit:178` ← … `Cell$Serializer.serialize` ←
`LocalDataResponse.build:201` ← `ReadCommandVerbHandler.doVerb:95` ([`oom-thread-stack.txt`](logs/CAL-2G/oom-thread-stack.txt)).
(Cassandra itself logs no stack: `OnOutOfMemoryError` kills the JVM right after the dump.)

**T-2G ×3, M-2G ×3, I-2G ×3, IL-2G ×3** (08:32–09:12; each: fresh template copy, 2G, warm-up 3 single queries of the
arm's variant + 20 s idle, then c = 12 for 120 s):

| Lifetime | Outcome | at c = 12 | Old gen after GC max | Dump (live) | Claimed holders in dump | First error |
|---|---|---|---|---|---|---|
| T-2G-1 | **heap OOM** at +51 s (10.1 s into c = 12) | 0 served; ReadStage active 12 | 897 MiB | 1,744 MiB | values 1,396 MiB (11.9 results) + 255 MiB buffers; replica 1,651 MiB = 95 % | ReadStage, `expandToFit` ← `LocalDataResponse.build` |
| T-2G-2 | **heap OOM** at +51 s (11.1 s) | 0 served; RS 12 | 1,694 MiB | 1,869 MiB | values 1,271 MiB (10.8) + 510 MiB; replica 1,630 + outbound 120 = 94 % | same frame |
| T-2G-3 | **heap OOM** at +51 s (11.1 s) | 0 served; RS 12 | 896 MiB | 1,887 MiB | values 1,374 MiB (11.7) + 405 MiB; replica 1,719 MiB = 91 % | same frame |
| M-2G-1 | survived | 439 ok, 0 errors, 3.66 q/s, **429 MiB/s** of values | 70 MiB | — | — | — |
| M-2G-2 | survived | 458 ok, 0 errors, 3.82 q/s, 447 MiB/s | 70 MiB | — | — | — |
| M-2G-3 | survived (histogram at s30: `[B` 92 MB live) | 405 ok, 0 errors, 3.38 q/s, 396 MiB/s | 360 MiB | — | — | — |
| I-2G-1 | **heap OOM** at +40 s (12.1 s) | 0 served; every T query refused | 1,244 MiB | 1,817 MiB | values 1,065 MiB + 660 MiB buffers (90–120 MiB each); replica 1,664 MiB = 92 % | same frame |
| I-2G-2 | **heap OOM** at +41 s (11.2 s) | 0 served; refused | 1,390 MiB | (deleted unread) | — | — |
| I-2G-3 | **heap OOM** at +41 s (11.1 s) | 0 served; refused | 1,199 MiB | (deleted unread) | — | — |
| IL-2G-1 | survived | 237 ok (250 rows each), 1,689 fast self-drop failures; 1.98 q/s, 58 MiB/s | 1,846 MiB | — | — | — |
| IL-2G-2 | survived | 225 ok, 1,689 drops; 1.88 q/s, 55 MiB/s | 1,952 MiB | — | — | — |
| IL-2G-3 | survived | 219 ok, 1,663 drops; 1.82 q/s, 54 MiB/s | 1,862 MiB | — | — | — |

- T: the warm-up singles take 4.0–5.8 s; once 12 ANN queries start together, all 12 ReadStage threads build their top-K
  maps at once and the heap is exhausted in 10–11 s, before any response reaches the coordinator (no coordinator or
  outbound copy in T-2G-1/-3). 3/3 heap OOM; no direct OOM (direct ≤ 263 MiB everywhere).
- M (same 1,000 rows × 120 KiB per query, same c, paged by 100): 3/3 survive with 0 errors, delivering 396–447 MiB/s
  of values (T delivered 0 at c = 12; at most 102 MiB/s at its best step, c = 4 in CAL-2G).
- I (`read_thresholds_enabled: true`, `local_read_size_fail_threshold: 64MiB`): the threshold **fires** — all 9 warm-up
  T queries fail with `ReadFailureException`, log "1 nodes loaded over 67191960 bytes and aborted the query" (100 %
  rejection) — but **3/3 heap OOM** at c = 12 with the same first-error frame. The dump shows why: the abort comes only
  while the response is being serialized, after the whole top-K map (≈ 1 V) has been built and while its
  `DataOutputBuffer` already holds 90–120 MiB. The design's own bound for this arm, c_T × (1 V + 64 MiB), is
  12 × 181 MiB ≈ 2.1 GiB at the measured c_T, above the heap.
- IL (T with LIMIT 250, V/4 = 29.3 MiB per result, arm A): 3/3 survive at c = 12 for 120 s; 219–237 queries served
  (250 rows each) and ≈ 88 % fail fast by self-response drops ("dropping 29.319MiB message"); old gen after GC reached
  1,846–1,952 MiB (close to the heap, no OOM); max 19 % STW over 60 s.

**CAL-4G** (08:52–08:57, arm A, 4G; steps 8, 10, 13, 16, 24, 32 × 45 s, no warm-up per design). c = 8–24 survived but
served 0.02–0.29 q/s with 120–195 fast drops per step; old gen after GC 3,249–3,685 MiB from c = 8 on. **Heap OOM** at
+268 s in the **c = 32** step (second 39). Dump 3,756 MiB live: 26,191 values (3,070 MiB = 26.2 results) + 570 MiB
buffers; replica 3,519 + outbound 120 = 97 %; first error the same ReadStage `expandToFit` frame. (Predicted c ≈ 13,
band 10–16.)

**CAL-8G** (08:57–09:02, arm A, 8G, dump on; steps 16, 24, 32, 48, 64 × 45 s). **No OOM** up to c = 64: 9 queries served
in the whole lifetime (8 at c = 16, then ≈ 0), 1,195 failures; old gen after GC 6.6–7.95 GiB; ReadStage active capped at
32 from c = 32 on; replica reads aborted by the 10 s timeout ("Query cancelled (timeout)", `QueryCancelledException`
in `debug.log`), which frees their maps; max 26 % STW over 60 s (no service loss by the GC criterion, but no useful
work). As predicted ("uncertain; timeouts").

**CAL-15872M** (09:12–09:17, arm A, 15,872M, dump on: 28 GiB free; steps 32, 48, 64, 96, 128 × 45 s). **No OOM** up to
c = 128; **0 queries served**, 1,865 failures (all fast self-response drops or 10 s timeouts); old gen after GC
13.4–14.7 GiB; ReadStage active capped at 32; max 16 % STW over 60 s. As predicted (no OOM at the top budget).

**REP-4G-1, -2** (09:17–09:21, arm A, 4G, warm-up then c = 32 for 120 s, the largest failing heap's failing c): **heap
OOM 2/2** at +61 s, 21–22 s into c = 32, 0 served, ReadStage active 32. With CAL-4G: **3/3 heap OOM at 4 GiB, c = 32**.
Dumps (4.1 GB each) analysed on the node after the batch had ended, then deleted: live 3,946 / 3,888 MiB; values
3,328 / 3,294 MiB (28.4 / 28.1 results) + 510 / 480 MiB buffers; claimed holders 3,838 / 3,774 MiB = **97 %** (replica
3,718 / 3,654 + outbound 120 / 120 MiB); first error the same ReadStage `expandToFit` ← `LocalDataResponse.build` frame.

**IC-OVER** (09:21–09:23, optional, arm A, 8G; ahead of plan, run after the batch, not a reading). Table `b21.big`
(1,100 rows × 262,144 chars, SAI index) loaded in this lifetime's node copy only (6 s, 0 failures), flushed. T on
`b21.big` LIMIT 1000 ×2: `ReadFailureException` after 2.5 s and 1.6 s; `system.log`: `Message$OversizedMessageException:
Message of size 262235773 bytes exceeds allowed maximum of 134217728 bytes` on ReadStage-2 (after the response was
built). One added check (recorded here, not in the design): LIMIT 250 on `b21.big` → 250 rows, 65.5 MB served, with the
Top-K page-size warning. As predicted: the triage's 256 KiB × 1,000 shape cannot be served on one node; per-query
response bytes are capped by `internode_max_message_size` (128 MiB), checked after the build.

**Budget search summary** (heap; direct resolved 15,872 MiB in all): **2 GiB: OOM 5/5 at c = 12** (CAL-2G, T ×3, and
c = 12 was the first failing step); **4 GiB: OOM 3/3 at c = 32** (CAL-4G, REP ×2); **8 GiB: no OOM to c = 64**,
**15,872 MiB: no OOM to c = 128** — at these heaps the 32 ReadStage threads and the 10 s timeout (replica reads
cancelled) bound the live set below the heap, and the node serves ≈ 0 queries. The largest heap that reaches the
endpoint is **4 GiB**; the boundary lies between 4 and 8 GiB.

**Deviations from the design** (none changes a constraint, budget or workload of a reading).
1. A1 (resolved direct limit 15,872 MiB; scope `MemoryMax` heap + 15,872M + 6G), recorded before the first reading.
2. c_T = 12 (the design's rule "the step's c" applied; outside the predicted band, within ≤ 16).
3. Histogram probes: CAL-2G (c = 4, s30) and M-2G-3 (c = 12, s30) taken; the T probe (T-2G-3, s30) did not fire because
   the victim died 11 s into c = 12.
4. Dumps were copied to `pc96:/mydata/b21-dumps/` and analysed there (keeps the node's CPU with the runs); the REP dumps
   were analysed on the node after all runs had ended (the WAN copy was too slow). I-2G-2 and -3 dumps were deleted
   unread (I-2G-1 analysed). One dump is kept: T-2G-1 on `pc96`.
5. Owner split by `hprofowner.py` (shortest path from a GC root), not by reachability from named classes; buckets as
   designed otherwise. The `GC.class_histogram` probe output is in `logs/<label>/histo-*-top.txt`.
6. IC-OVER run after the batch (ahead of plan) with one extra LIMIT 250 query on `b21.big` as a positive check.

**Predictions vs readings.** Mechanism, IC, PROBE drops, first-error site (ReadStage `DataOutputBuffer.expandToFit` in
`LocalDataResponse.build`, the ≈ 60 % option), T 3/3, M 0/3, the 8 GiB uncertainty and the 15,872 MiB no-OOM were as
predicted. Different from the prediction: **c_T = 12** (predicted 6, band 3–8) and 4 GiB c = 32 (predicted 13): the live
holder per in-flight query is ≈ 1.2 V (the replica's top-K map plus its growing response buffer), not 2–3 V, because the
internode reserve lets only one ≈ 117 MiB response to self pend at a time and drops the others after they are built, so
coordinator copies are rare (CAL-2G: 205 MiB coordinator, 120 MiB outbound, 1,392 MiB replica; T-2G: 0–120 MiB outside the
replica). Response buffers grow 15 → 30 → 60 → 90 → 120 MiB (not 64 → 96 → 144). The dropped responses fail the query at
once (`ReadTimeoutException` in 0.2–6 s), not after 10 s. **I-2G** was predicted to survive 3/3 and OOMed 3/3 (above).
**IL-2G** survived 3/3 as predicted, but served only ≈ 12 % of its queries (the rest dropped by the internode reserve),
not "all queries served".


## 4. Conclusion (stage 2)

**Verdict: true positive.** Protocol status **`verified-OOM · deployment`** (bypass — exempt mode of the paging control,
on an unprotected configuration; heap OOM at 2 GiB and 4 GiB with every constraint at its default). **Owner check
requested** on one point: the design's pre-registered verdict rule names `I-2G 0/3`, and arm I **failed** (3/3 OOM). V4 is
met here by the design's other pre-registered intervention, the dose arm IL (3/3 survive at matched c). See "V4" below;
if the owner holds to the named arm, the verdict becomes `retry` with the change listed under "If retry".

**Reason.** At 2 GiB heap and shipped defaults, 12 concurrent ANN queries `SELECT id, body … ORDER BY emb ANN OF […]
LIMIT 1000` (client page size 100, raised by the server to 1,000 with its Top-K warning; 1,000 rows × 120 KiB = 117 MiB
per result) ended in a Java heap OOM **5/5** (CAL-2G at c = 12, T-2G 3/3 within 10–11 s of c = 12), and at 4 GiB **3/3** at
c = 32. The paged control M — the same 1,000 rows × 120 KiB per query at the same c = 12, in 10 pages of 100 — survived
**3/3** for 120 s and delivered 396–447 MiB/s of values with old gen after GC ≤ 360 MiB, while T delivered 0 at c = 12.
Every dump (8 analysed) shows the claimed holders as **91–97 % of the live heap**: per in-flight query the replica's
eagerly built top-K map (`VectorTopKProcessor.takeTopKThenSortByPrimaryKey` /
`ScoreOrderedResultRetriever` → `TreeMap<…, TreeSet<Unfiltered>>`, ≈ 1 V of 122,880-B values) plus its response
`DataOutputBuffer` (15–120 MiB), with the coordinator's response + priority queue (205 MiB) and one outbound message
(120 MiB) when present. The first error is on a ReadStage thread growing that buffer (`DataOutputBuffer.expandToFit` ←
`LocalDataResponse.build`) in all 8 dumps. U (≈ 1.2 V ≈ 140 MiB per query, ≈ 1.65–1.75 GiB for 12) is measured from dumps
independently of K (1,000 rows per response, the `MAX_TOP_K` count, which it never exceeds); nothing sums these bytes
across queries. The dose intervention (LIMIT 250, V/4) removed the OOM 3/3 at c = 12; the shipped byte control
(`local_read_size_fail_threshold` 64 MiB, arm I) refused 100 % of the queries but did not prevent the OOM (3/3), because
it aborts only while the response is serialized, after the top-K map has been built.

**Classification (by measurement).** Paging domain: C = one client page (100 rows ≈ 11.7 MiB), K = rows per response
1,000 > 100 by the server's override, U ≈ 140 MiB per query → **bypass, exempt mode** (intentional exception, warned).
`MAX_TOP_K` domain: K = 1,000 ≤ C = 1,000 rows, U in bytes uncounted → **accounting mismatch** (count, not bytes; CP-2).
Read-size thresholds: off by default → **unprotected configuration**; when on, enforced after the materialization →
**late enforcement** (CP-11). The OOM needs concurrency (c = 12 at 2 GiB, 32 at 4 GiB; nothing caps the sum: CP-7) of
whole materialized results (CP-12) on the unpaged Top-K branch (CP-10). Interpretation: intentional exception plus a
configuration-sizing gap; the late threshold on the Top-K path looks like a limitation of the implementation (the size
tracker is attached after `searcher.search`), not a bug report (nothing posted).

**V1–V7** (one fixed condition: build `b3fa4929…`, arm A, 2 GiB heap, direct 15,872 MiB resolved, c = 12 for 120 s after
the warm-up, template data):

| | Met? | Evidence |
|---|---|---|
| V1 Repetition | yes | T-2G-1/-2/-3: heap OOM 3/3 (plus CAL-2G at c = 12; at 4 GiB CAL-4G + REP ×2: 3/3 at c = 32) |
| V2 Matched control | yes | M-2G-1/-2/-3: 0/3, same bytes per query, same c, same budget/build/warm-up |
| V3 Measurement | yes | dumps → `hprofhist.py` + `hprofowner.py` (U per holder, 91–97 % of live heap); JMX sampler old gen after GC; K from the client (rows/page, warning) |
| V4 Intervention | yes, via IL (see note) | IL-2G-1/-2/-3: 0/3 OOM at c = 12, 1.8–2.0 q/s served (12 % of attempts; the rest dropped by the internode reserve), old gen ≤ 1,952 MiB. Arm I (threshold on): 3/3 OOM with 100 % rejection — the shipped control does not remove the endpoint |
| V5 Initiating failure | yes | first error from each dump's throwing thread: ReadStage `DataOutputBuffer.expandToFit` ← `LocalDataResponse.build`; dumps at the failure show the claimed holders; `stdout.log` "java.lang.OutOfMemoryError: Java heap space" |
| V6 Default constraints | yes | `MAX_TOP_K` 1,000 (no `-D`), read thresholds off, `internode_max_message_size` 128 MiB and reserves default, `concurrent_reads` 32, `native_transport_max_threads` 128, timeouts default; `yaml.diff` = directories only |
| V7 Acceptable budget | yes | heap 2 GiB (standing rule: ideal) and 4 GiB; direct 15,872 MiB as `cassandra-env.sh` resolves it; no container limit (scope for isolation only, `oom_kill` 0). Largest failing heap 4 GiB (3/3); 8 GiB and 15,872 MiB: no OOM to c = 64 / 128 (boundary) |

Conditions label **deployment**: no supporting deviation (no raised timeout, no instrumentation in the victim, data and
queries within guardrails: 120 KiB `text` values ≪ `max_mutation_size`, LIMIT ≤ `MAX_TOP_K`).

**V4 note.** The design named two interventions: I (the byte threshold, "the honest outcome of the only byte control
5.0.9 has") and the optional dose arm IL (LIMIT 250). Its verdict rule listed `I-2G 0/3`. I fired as configured but
cannot remove the endpoint, because it is checked after the holder exists; at the measured c_T = 12 even the design's own
bound for I (c × (1 V + 64 MiB) ≈ 2.1 GiB) exceeds the heap. IL bounds the holder's size at the same multiplicity and
removes the OOM 3/3, which is the causal attribution V4 asks for ("bound multiplicity, … reserve before allocation";
protocol, Design and execution 7). IL is not an effective protection either: 88 % of its queries fail by internode drops.

**Limits of attribution.** One node (coordinator = replica): the replica side dominates because the self connection's
128 MiB endpoint reserve lets one response pend and drops the others after they are built; on a multi-node ring the
coordinator copies (OC-455/462/557/40, the per-node fan-out) are not tested here. The boundary at 8 GiB and above comes
from 32 ReadStage threads and the 10 s timeout cancelling replica reads; the node then serves ≈ 0 queries (no OOM, and
no GC service loss by the 90 % criterion: max 16–26 % STW). aarch64 only (m400); jvector's scalar provider.

**If retry** (only if the owner rejects IL as V4): repeat at c = 12 with an intervention that bounds the holder before it
is built, e.g. `nodetool setconcurrency ReadStage 4` (bound multiplicity of top-K builds) ×3, or a diagnostic build that
charges the top-K map to the read-size tracker during `takeTopKThenSortByPrimaryKey` ×3, keeping T and M as run here.

**Not covered / follow-ups for the owner.** The per-node fan-out multiplier (OC-455, OC-462, OC-557, OC-40) needs N ≫ 1
nodes. No new holder beyond the design's claim was found (the outbound 120 MiB message and the dropped-after-build
responses are the design's internode rows). No JIRA comment proposed.
