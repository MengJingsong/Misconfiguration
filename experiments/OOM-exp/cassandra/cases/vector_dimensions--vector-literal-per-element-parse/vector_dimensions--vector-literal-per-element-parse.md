# U17 — vector_dimensions (off): a vector literal in an unprepared INSERT is parsed and prepared into ≈ 190 B of heap per element  <!-- file: cassandra/cases/vector_dimensions--vector-literal-per-element-parse/vector_dimensions--vector-literal-per-element-parse.md -->

| Field | Value |
|---|---|
| Case ID | `U17` (U = unprotected accumulation; README "ID prefixes") |
| From | `OC-579` of the phase 1 OOM candidate list (owner-approved follow-up of U8, the write side; batch of 2026-11-24) |
| Phase-1 case file | [`no_constraint-isallzero-vectorelement--autonomous`](../../../../capacity-enforcement-exp/cassandra/stage3-ai-deep-read/cases/no_constraint-isallzero-vectorelement--autonomous.md) (the same as U8's) |
| System / pinned source | Cassandra 5.0.9 (`systems/cassandra/source/`, `build.xml` `base.version` 5.0.9); ANTLR runtime 3.5.2; built copy `pc91:/mydata/s4/cassandra-base` (`build/apache-cassandra-5.0.9-SNAPSHOT.jar`, sha256 `570b5249…0bea90176e`) |
| Stage 1 (design) | OOM-agent stage-1 session (workflow, owner-approved batch of 2026-11-24), 2026-11-24 05:00–06:10 America/New_York; nothing run (nodes checked read-only over ssh) |
| Stage 2 (verify) | fresh OOM-agent stage-2 session (workflow, owner-approved batch of 2026-11-24), 2026-11-24 09:16–11:26 America/New_York on **pc75** (x86_64; dated deviation, §2 A1); freeze hash checked (match) |
| Verdict | **true positive** — `verified-OOM · deployment` (unprotected accumulation + unprotected configuration) |

## Summary

- **Conclusion:** **true positive.** Two concurrent unprepared `INSERT … VALUES (0, [0,0,…,0])` of a
  `vector<tinyint, 6,500,000>` (13.0 MB each, under the 16 MiB frame and the 16 MiB mutation limit) kill a 2 GiB
  node with a Java heap OOM in **3/3** runs, every capacity at its shipped default. The same bytes as one blob literal
  (0/3), one such INSERT alone (0/3) and a one-at-a-time patch on large unprepared QUERYs (0/3) do not. The same holds
  with only 8,192-dimension vectors (the documented limit) in one single-partition batch (3/3 vs 0/3, 0/3). Budget
  search: OOM 3/3 at 8 GiB (N = 9), 3/5 at 12 GiB (N = 13); at 16 GiB and 31,744 MiB GC service loss, no OOM in 600 s.
- **Root cause:** the CQL parser and `Vectors.Literal.prepare` materialize every element of a vector literal as
  heap objects (two ANTLR `CommonToken`s, a `String` and a `Constants.Literal` per element, then a `Constants.Value`
  and a one-byte `HeapByteBuffer`): **≈ 168 B of heap per element** (measured) on the request thread, while every
  check on the request counts **2 B per element** (frame, in-flight bytes, mutation size). Nothing bounds the element
  count (`vector_dimensions_fail_threshold` ships −1; the documented 8K dimension limit is not enforced) and nothing
  bounds the number of concurrent parses but the 128 native threads. Every such INSERT also ends in a write timeout
  (the ≈ 5 s parse exceeds the 2 s write deadline), so the memory is spent for a write that is never applied.
- **Hypothesis under test (stage 1):** an unprepared `INSERT … VALUES (0, [0,0,…,0])` into a `vector<tinyint, D>`
  column is charged as its wire bytes (≈ 2 B per element: 12.0 MB for D = 6,000,000, inside the 16 MiB frame and
  the 16 MiB mutation limit), but the coordinator's request thread holds ≈ 190 B of heap per element while it parses
  and prepares the literal (two ANTLR `CommonToken`s, a `String` and a `Constants.Literal` per element, then a
  `Constants.Value` and a one-byte `HeapByteBuffer` per element): ≈ 1.1 GB per request, ≈ 93× its counted bytes.
  Nothing bounds it: the vector-dimension guardrail ships off (−1) and the only checks count bytes. Two such INSERTs
  at once should exhaust a 2 GiB heap (Java heap OOM) with every capacity at its shipped default.

## 1. Candidate

**Row of the phase 1 OOM candidate list** (`phase1-oom-candidates.md:588`), quoted:

> | OC-579 | 2026-11-23 | `no_constraint-isallzero-vectorelement--autonomous` | phase-2 (U8, stage 3) | [owner-approved follow-up of U8; not yet tested] Write side of U8: a vector value sent as a CQL **literal** (`INSERT … VALUES ([true, false, …])` in an unprepared QUERY) is parsed element by element. `listLiteral` builds a `List<Term.Raw>` with one literal (plus its lexer tokens) per element (`Parser.g:1572-1575`), and `Vectors.Literal.prepare` builds a second `List<Term>` and then one `ByteBuffer` per element (`Vectors.java:116-140`). The only limits are on bytes: the 16 MiB native frame bounds the query text (≈ 3–8 M elements at 2–5 characters each), `max_mutation_size` bounds the serialized result, and 5.0.9 does not enforce the documented 8K-dimension limit (`VectorType.java:89` checks only > 0; `vector_dimensions_fail_threshold` ships −1). Rough size: several hundred bytes of heap per element, i.e. ≈ 1 GiB or more per 16 MiB request, on the request thread, with up to 128 native threads. **Where:** src/antlr/Parser.g:1572-1575; src/java/org/apache/cassandra/cql3/Vectors.java:94-140; src/java/org/apache/cassandra/db/marshal/VectorType.java:86-92 | CP-1, CP-12, CP-8 | picked: U17 (2026-11-24) |

**Phase-1 case.** [`no_constraint-isallzero-vectorelement--autonomous`](../../../../capacity-enforcement-exp/cassandra/stage3-ai-deep-read/cases/no_constraint-isallzero-vectorelement--autonomous.md):
estimate `negative`, no constraint (`isAllZero`, `VectorFcts.java:96-103`, is an argument check of `similarity_cosine`).
The clue came from reading the vector code around it (U8 §1). Stage 4: none for this case file. Its read side is
U8 (`true positive`, `SELECT JSON` splits one cell into one `HeapByteBuffer` per element; JIRA label `new`).

**Stage 1 trace (pinned source).** QUERY opcode → `QueryMessage.execute` (`transport/messages/QueryMessage.java:116`)
`queryHandler.parse` → `QueryProcessor.getStatement` (`cql3/QueryProcessor.java:893-905`) → `parseStatement` →
`CQLFragmentParser.parseAnyUnhandled` (`cql3/CQLFragmentParser.java:66-76`): `new ANTLRStringStream(input)` (a
`char[]` copy of the whole text), `new CommonTokenStream(lexer)` (ANTLR 3.5.2 `BufferedTokenStream`: **every token is
kept** in an `ArrayList<Token>` for the whole parse), `CqlParser.query`. For the value list the grammar runs
`listLiteral` (`src/antlr/Parser.g:1572-1575`: `l.add(t1)` … `l.add(tn)` into one `ArrayList<Term.Raw>`), each element
through `term → termAddition → termMultiplication → termGroup → simpleTerm → value → constant` (`Parser.g:1631-1660`,
`:1527-1531`, no syntactic predicate on this path), and `constant` creates `Constants.Literal.integer($t.text)`
(`CommonToken.getText()` returns a new `String` from the char stream each call; the literal keeps it,
`cql3/Constants.java:218-223`; its constructor also parses the text once with `new BigInteger`, transient). The raw
INSERT returns from the parser holding the `ArrayLiteral(l)`; the token stream and `char[]` become unreachable.
`statement.prepare` → `Operation.SetValue.prepare` (`cql3/Operation.java:166-191`) → `ArrayLiteral.prepare` →
`new Vectors.Literal(elements)` (`cql3/ArrayLiteral.java:45`) → `Vectors.Literal.prepare` (`cql3/Vectors.java:116-142`):
`List<Term> values = new ArrayList<>(D)` (`:127`), per element `testAssignment` + `Constants.Literal.prepare` →
`new Value(parsedValue(...))` (`Constants.java:266`) → `ByteType.fromString` → `ByteBufferUtil.bytes(byte)` =
`ByteBuffer.allocate(1)` (`utils/ByteBufferUtil.java:568-571`): one `HeapByteBuffer` + `byte[1]` per element; then
`DelayedValue.bind` (`Vectors.java:211-223`) copies the buffers into a second `ArrayList<ByteBuffer>(D)` held by
`Vectors.Value`. Execution: `Constants.Setter` → `Vectors.Value.get` → `VectorType.decomposeRaw` →
`VariableLengthSerializer.serializeRaw` (`db/marshal/VectorType.java:604-615`, `tinyint` is variable-length in a
vector: one vint length byte + 1 data byte per element) → a 2·D-byte cell → mutation → commit log and memtable.

**What this design covers and does not cover.**

| Part of OC-579 | Covered? |
|---|---|
| Holder = per-element objects of an unprepared vector literal: lexer tokens + `List<Term.Raw>` of literals (parse), second `List<Term>` + one `ByteBuffer` per element (prepare); unbounded dimension, guardrail off | **yes** (claimed holder) |
| Element type `boolean` (`[true, false, …]`, the row's example) | **no, by choice**: `tinyint` (`0`, 2 characters per element with the comma) carries ≈ 2.4–3× more elements per frame, and `ByteType.fromString` allocates a buffer per element while `BooleanType` returns two shared constants (`BooleanSerializer.java:27-28,40-43`), so the row's "one ByteBuffer per element" holds only for non-boolean types. Same parse path, so the result transfers in kind to `boolean` (≈ 0.3–0.4× the size per frame) |
| "the 16 MiB native frame bounds the query text", "`max_mutation_size` bounds the serialized result" | **yes**: the test request is 12.0 MB (< 16 MiB frame), the cell 12.0 MB (< 16 MiB mutation); both checks pass and are recorded |
| "does not enforce the documented 8K-dimension limit" | **yes, both ways**: the main arms use one 6,000,000-dimension vector (accepted, the documented limit not enforced); condition **W** carries the same ≈ 6 M elements as 732 vectors of **8,192** dimensions (within the documented limit) in one single-partition unprepared BATCH, so the result does not rest on input the docs call invalid |
| "up to 128 native threads" | **yes**: multiplicity N of concurrent INSERTs (N = 2 at 2 GiB; up to 31 in the budget search), bounded only by `native_transport_max_threads` 128 |
| Prepared statements, `toJson`/`SELECT JSON` (U8), protocol v5 framing | **no** (prepared binds are the matched control C3 only if time allows, not claimed) |

**JIRA prior art** (read only; nothing posted). JIRA REST search 2026-11-24 (`issues.apache.org/jira/rest/api/2/search`,
requests ≥ 2 s apart), JQL → hits:
`project = CASSANDRA AND text ~ "vector literal"` → 15 (feature/validation work: CASSANDRA-18504, 19118, 18652, 20979,
18813; none on memory); `… text ~ "CqlParser" AND text ~ "OutOfMemoryError"` → 1 (CASSANDRA-14096, repair/gossip,
unrelated); `… text ~ "ANTLR" AND (text ~ "OutOfMemoryError" OR text ~ "heap")` → 22 (none on parse memory);
`… text ~ "large query string"` → 62 (closest: CASSANDRA-8254 "Query parameters limited to 65,536 entries", Not A
Problem; CASSANDRA-20052 V5 message size not limited, fixed 5.0.3, a frame check; CASSANDRA-16060 OOM, Invalid, a read
path); `… summary ~ "vector" AND (OutOfMemoryError|OOM|heap)` → 3 (SAI recall/sharding, unrelated);
`… text ~ "vector_dimensions"` → 15 (CASSANDRA-18730 "Add guardrail for vector dimensions", fixed 5.0-alpha1, shipped
at −1); `… text ~ "query string" AND (OutOfMemoryError|OOM)` → 38 (CASSANDRA-12618 "Out of memory bug with one insert",
fixed 2.2.9/3.0.10/3.10: a **bound** list value with a bogus element count, malformed input, different holder, linked
CASSANDRA-12769/11846); `… text ~ "literal" AND text ~ "parse" AND (OutOfMemoryError|heap)` → 11 (CASSANDRA-21139
"Guardrail for miss-prepared statements", fixed 7.0: literals instead of bind markers churn the prepared cache; not
parse memory, not in 5.0.9); `… text ~ "CommonTokenStream"` → 2 (CASSANDRA-7569 error snippet, 14096). **Verdict:
`new`** (no issue on the per-element parse/prepare expansion of literals; related: 18730 guardrail ships off, 21139).
Repo-local related cases: U8 (read side, true positive); U6's supporting arm B (a PREPARE of 8.39 M `?` markers in an
`IN` list reached heap OOM 3/3 at 2 GiB in `BufferedTokenStream.fetch`, no control ×3 or intervention; OC-278/285
`retry (U6)`): the same token buffer, but markers, a PREPARE, and a request the marker check rejects. U17 is an
accepted write whose literal adds per-element `String`/`Literal` and prepared `ByteBuffer`s to the tokens.

## 2. Design solution (stage 1; frozen)

**Mechanism.** Direction: **unprotected** (protocol "Unprotected results"): unprotected accumulation (no control
covers the per-element objects a literal's parse and prepare hold; the bound is implicit, concurrency × size) plus
unprotected configuration (`vector_dimensions_warn/fail_threshold: -1`, `Config.java:924-925`; with the default
`AllowAllAuthenticator` guardrails would not apply to the anonymous superuser anyway). Interpretation: a
validation/sizing gap (the docs state "Vectors are limited to a maximum dimension of 8K (2^13) items",
`doc/modules/cassandra/pages/reference/vector-data-type.adoc:15`, but `VectorType.java:89` checks only `dimension > 0`)
and a parse design that materializes every token. Technique note:
[`default-convergence-playbook.md`](../../../default-convergence-playbook.md) (multiplicity sweep at default
capacities). For an unprepared INSERT of a `vector<tinyint, D>` literal written as `[0,0,…,0]` (2 characters per
element), the request thread holds per element, at the parse peak: 2 `CommonToken` (48 B each, compressed oops) +
2 token-list slots (8 B) + the element's text `String` (24 B + `byte[1]` 24 B) + `Constants.Literal` (24 B) + a raw-list
slot (4 B) + 2 B of `char[]` per character (4 B) + the query `String` (2 B) ≈ **186 B**, plus `ArrayList` slack and
growth copies (≤ 1.5× the slots, transient); at the prepare peak (tokens and `char[]` unreachable): the raw literal and
its `String` (76 B) + `Constants.Value` (16 B) + `HeapByteBuffer` (48 B) + `byte[1]` (24 B) + 2 list slots (8 B) ≈
**172 B**. The only byte counts on the request see **2 B per element** (wire body, cell, mutation). All of it lives on
the coordinator's Native-Transport-Requests thread from the start of the parse to the end of prepare (seconds), and
the parse of one request does not wait for any other; N concurrent INSERTs hold ≈ N × 186·D + baseline.

**Protection map** (fixed before any run).

| Domain | Holder (allocation → release) | Counter K | Limit at default | At the limit |
|---|---|---|---|---|
| Vector dimension | the column type; sets the element count a literal must have (`Vectors.java:123-124`) | dimension (count) | `vector_dimensions_fail_threshold: -1` (off); documented 8K not enforced (`VectorType.java:89`) | nothing → **unprotected configuration** |
| Request text (wire) | the v4 frame body (Netty buffer), the query `String` (`QueryMessage.java:50`) | body bytes (`PreV5Handlers.java:153`) | `native_transport_max_frame_size` 16 MiB (`Config.java:285`, `Envelope.java:429`) | `Request is too big` above 16 MiB (12.0 MB is under it) |
| In-flight request bytes | the same body, until the response | body bytes | heap/10 global, heap/40 per IP (`DatabaseDescriptor.java:649-656`) | **pause** reading on that connection; the request is still processed (`PreV5Handlers.java:180-186`); not reached at the planned N (2 × 12.0 MB < 51.2 MiB at 2 GiB) |
| **Parse objects (claimed holder, part 1)** | `ANTLRStringStream` `char[]`, `BufferedTokenStream.tokens` (2 `CommonToken` per element), per element `String` + `Constants.Literal` in `listLiteral`'s `ArrayList` (`CQLFragmentParser.java:66-76`, `Parser.g:1572-1575`) → tokens/`char[]` unreachable when the parser returns; literals when prepare returns | none | none | nothing → **unprotected accumulation** |
| **Prepared values (claimed holder, part 2)** | `Vectors.Literal.prepare` `List<Term>` of `Constants.Value` + one `HeapByteBuffer`/`byte[1]` per element (`Vectors.java:127-142`, `ByteBufferUtil.java:568-571`), `DelayedValue.bind` `List<ByteBuffer>` (`:211-223`) → until the response is written | none | none | nothing → **unprotected accumulation** |
| Cell / mutation | the serialized 2·D-byte cell (`VectorType.java:604-615`), the mutation, the memtable copy (`heap_buffers`) | serialized bytes | `max_mutation_size` = ½ `commitlog_segment_size` = 16 MiB (`DatabaseDescriptor.java:898-899`); `column_value_size` guardrail null (`Config.java:915-916`) | write rejected above 16 MiB (12.0 MB is under it) |
| Batch size (condition W only) | the batch's mutations | data size | `batch_size_fail_threshold` 50 KiB, **only for multi-partition batches** (`BatchStatement.java:331-335`) | not applied to the single-partition batch W |
| Concurrency | one parse + prepare per in-flight request | NTR threads | `native_transport_max_threads` 128 (`Config.java:283`) | queue; no byte sum |
| Write deadline (ledger, not a capacity) | the local write after prepare | time | `write_request_timeout` 2 s from the start of processing (`cql_start_time: REQUEST`, `Dispatcher.java:173-184,238-245`); `native_transport_timeout` 12 s from enqueue | an expired local write is dropped/hinted and the client gets a write timeout; the parse has already run (does not bound the holder) |
| Baseline | memtable heap pool (H/4), key cache, chunk cache (direct), hints buffers (direct) | own counters | defaults | evict / flush |

**Configuration and budget audit.**
- **Node:** `pc91` (node0.jason92-326665, CloudLab UMass), **x86_64**, Intel Xeon E5-2667 v2, 32 hardware threads,
  125 GiB (`MemTotal` 131,943,328 kB), swap 8 GiB (unused; kept off for the victim), cgroup v2 (`memory` delegated to
  the user service), Ubuntu 22.04.2, kernel 5.15.0-203-generic, OpenJDK 11.0.33, `jcmd`/`jmap`, Python 3.10.12; `/proj`
  mounted; `/mydata` 753 G with 706 G free (checked read-only 2026-11-24 05:49 EST). No Java process was running;
  load 0.04. `/mydata/s4/NODE-LOCK/owner` reads `phase1-hadoop o9 Mon Nov 23 11:12:13 PM MST 2026` (a lock from an
  earlier phase-1 Hadoop run; nothing of it is running): the coordinator assigns the node; stage 2 starts only once
  the lock is cleared or handed to it. `/mydata/s4/3b-C10`, `/mydata/s4/3b-S2` belong to other cases: do not touch.
  Any other x86 node of the set (pc72, pc75, pc99; pc82 runs HDFS daemons) is an equivalent substitute if the
  coordinator moves the case (record it); do not mix x86 and aarch64 readings.
- **Build:** `/mydata/s4/cassandra-base` (419 M; `build/apache-cassandra-5.0.9-SNAPSHOT.jar` sha256
  `570b5249d9b9a43f6809eb3da562737492192026f974b2edbd20e94bea90176e`; `lib/antlr-runtime-3.5.2.jar`), copied read-only
  to `/mydata/s4/u17/tree`.
- **JVM** (shipped options): G1 (`jvm11-server.options`: `G1HeapRegionSize=16m`, `G1NewSizePercent=50`,
  `MaxGCPauseMillis=300`, `InitiatingHeapOccupancyPercent=70`), `HeapDumpOnOutOfMemoryError`, `AlwaysPreTouch`,
  `-XX:OnOutOfMemoryError="kill -9 %p"` (`cassandra-env.sh`).
- **Every capacity constraint at its shipped default (V6):** `vector_type_enabled: true`,
  `vector_dimensions_warn/fail_threshold: -1`, `commitlog_segment_size: 32MiB` → `max_mutation_size` 16 MiB,
  `native_transport_max_frame_size` 16 MiB, `native_transport_max_message_size` derived (v5 only),
  `native_transport_max_threads` 128, `native_transport_max_request_data_in_flight` heap/10 and `_per_ip` heap/40,
  `native_transport_throw_on_overload: false`, rate limiting off, `batch_size_warn/fail_threshold` 5/50 KiB,
  `column_value_size` guardrail null, `memtable_allocation_type: heap_buffers`, `authenticator: AllowAllAuthenticator`,
  timeouts (`write_request_timeout` 2 s, `native_transport_timeout` 12 s, `cql_start_time: REQUEST`) not raised. Only
  arm I (and WI) changes anything: one patched class (below).
- **`cassandra.yaml` diff** from the shipped file (environment only): `data_file_directories`, `commitlog_directory`,
  `hints_directory`, `saved_caches_directory`, `cdc_raw_directory` under `/mydata/s4/u17/node/`. Single node,
  `127.0.0.1`, client on the same node. Save the diff per run (`yaml.diff`).
- **Budgets (V7;** standing rule: heap/direct ≥ 512 MiB meets V7, 2 GiB ideal, search upward**):**
  - What `pc91` resolves by itself (`cassandra-env.sh:51-68`, G1): heap_limit 31,744 MiB; ½ RAM = 64,425 MiB > limit
    → heap **31,744 MiB**, `MaxDirectMemorySize` **15,872 MiB**.
  - **Primary: heap 2 GiB** (`MAX_HEAP_SIZE=2G`), direct **auto** (`MAX_DIRECT_MEMORY_SIZE` unset → 15,872 MiB, as U8
    recorded with a hand-set heap; read the resolved `-XX:MaxDirectMemorySize` from `ps` and record it). Claimed node
    class: any node running a ≥ 2 GiB heap (≥ 512 MiB rule; no per-case review needed).
  - **Upward search:** 4 GiB, 8 GiB, 16 GiB and **31,744 MiB** (the node's own resolved heap), direct auto.
  - **Container:** `systemd-run --user --scope -p MemoryMax=<heap + 15,872 MiB + 8 GiB> -p MemorySwapMax=0`: isolation
    only, **not** a budget; it must never fire (`memory.events` `oom_kill` 0 in every run; a cgroup kill makes the run
    invalid, not a result).

**Ceiling arithmetic.** D = 6,000,000 (default; calibrated by D1, below). Payload VEC:
`INSERT INTO u17.t (pk, v) VALUES (0, [` + `0,` × (D − 1) + `0` + `])` = 2D + 39 = **12,000,039 characters**; v4 body
4 + 12,000,039 + 2 + 1 = **12,000,046 B** (< 16,777,216 frame); cell 2D = 12,000,000 B (< 16,777,216 mutation).
Per request, heap (MB = 10⁶ B):

| Phase | Items | MB |
|---|---|---|
| Parse peak | query `String` 12 + `char[]` 24 + `CommonToken` 12 M × 48 = 576 + token list 48 (≤ 72 with slack) + element `String`+`byte[1]` 6 M × 48 = 288 + `Constants.Literal` 6 M × 24 = 144 + raw list 24 (≤ 36) | **1,116** (≤ 1,190 with slack/growth) |
| Prepare peak | query 12 + raw (literal + string + slot) 456 + `Constants.Value` 96 + `HeapByteBuffer` 288 + `byte[1]` 144 + two lists 48 | **1,044** |
| Execute | `Vectors.Value` buffers 456 + lists 24 + cell 12 + mutation/memtable copies ≤ 36 | ≈ 0.53 GB |

So U_req ≈ **1.12–1.19 GB** per request (b ≈ 186–198 B per element) against K = 12.0 MB (**U/K ≈ 93–99**). Baseline at
2 GiB (idle node, empty table) 0.1–0.3 GB. Contract capacities: no contract covers the holder (the frame, in-flight,
mutation and dimension checks see 12.0 MB or are off). Reachable sums at 2 GiB (2,147 MB): **N = 1** → 1.22–1.49 GB
(57–69 % of the heap; margin ≥ 31 %), **N = 2** → 2.34–2.68 GB > 2,147 MB (**OOM**, 9–25 % over). Even at a per-element
cost 15 % below the estimate (158 B), N = 2 needs 2.00 GB + 0.15 GB baseline ≥ 2.15 GB. Needed N at heap H:
N(H) = ceil((H − 0.3 GB) / U_req) + 1 → **5 at 4 GiB, 9 at 8 GiB, 17 at 16 GiB, 31 at 31,744 MiB**, all ≤ 128 threads
and inside the per-IP in-flight limit without a pause (N × 12.0 MB vs heap/40: 60 vs 107, 108 vs 215, 204 vs 429,
372 vs 832 MB). The C1 hex QUERY (below) holds ≈ 0.07 GB per request (one token).

**Workload and environment.**
- Single node on `pc91`, client on the same node (loopback, one client IP 127.0.0.1). Fresh node dir per run (no
  cloning), then schema (client `--ddl`): `CREATE KEYSPACE u17 WITH replication = {'class':'SimpleStrategy',
  'replication_factor':1}`; `CREATE TABLE u17.t (pk int PRIMARY KEY, v vector<tinyint, D>)`;
  `CREATE TABLE u17.h (pk int PRIMARY KEY, b blob)`; `CREATE TABLE u17.w (pk int, ck int, v vector<tinyint, 8192>,
  PRIMARY KEY (pk, ck))`. Idle 30 s after the schema, then the arm's load. No preloaded data (the holder is on the
  write path).
- **Payloads** (built once per client process, all CL ONE, all to pk 0):
  - **VEC** (test): the unprepared QUERY above (D elements `0`, no spaces).
  - **HEX** (matched-path control C1): `INSERT INTO u17.h (pk, b) VALUES (0, 0x` + `00` × D + `)` = 2D + 40 characters
    (one character longer than VEC; same QUERY path, same in-flight K, same parse entry), one `HEXNUMBER` token, a
    D-byte blob. Expected per-request heap ≈ 12 + 24 + 12 + 12 + 6 + 6 MB.
  - **WB** (condition W, documented-limit form): `BEGIN UNLOGGED BATCH ` + M × (`INSERT INTO u17.w (pk, ck, v) VALUES
    (0, <ck>, [` + `0,` × 8,191 + `0` + `]); `) + `APPLY BATCH`, ck = 0 … M − 1, **M = floor(D / 8,192) = 732** (5,996,544
    elements, ≈ 12.03 M characters, single partition: no batch-size check; mutation ≈ 732 × 16,384 B ≈ 12.0 MB). The
    client prints the exact text, body and frame lengths and refuses to run if the body exceeds 16,777,207 B.
- **Client `u17client.py`** (Python 3 standard library, raw protocol v4 unsegmented frames, adapted from U6's
  `../ErrorCollector_errorMsgs--one-message-per-bad-character/harness/client.py`): STARTUP → READY per connection;
  modes `--ddl D`, `--sizes`, `--payload {VEC,HEX,WB} --n N --rounds R --out DIR`, `--readback` (QUERY
  `SELECT v FROM u17.t WHERE pk = 0` and `SELECT b FROM u17.h WHERE pk = 0`; parse the ROWS body and print the cell
  length). N connections (one thread each), a `threading.Barrier(N)` per round, one request outstanding per
  connection, socket timeout 120 s (client side only). Per request one CSV line: UTC ms send/response, connection,
  round, request body bytes (K), response opcode, error code + first 120 characters. The client ends a run when R
  rounds finish or every connection is refused/reset; a timeout alone does not end it (U8 A4).
- **Harness:** under this folder's `harness/`, adapted from U8's
  (`../vector_dimensions--select-json-element-slices/harness/`: `victim-ctl.sh` start/ready/stop/oom with per-run
  `CASSANDRA_CONF` and the `systemd-run` scope, `run-arm.sh` with the **watch rule** — if the client gives up while the
  victim is alive, keep watching the victim to 600 s from the first request or its death — `C2Sampler.java`,
  `gcwin.py`, `hprofhist.py`, `hprofstacks.py`) and U6's (`hprof-histo.py`, `hprof_oome_thread.py`). Node root
  `/mydata/s4/u17/` (`tree/`, `conf-pristine/`, `node/` wiped per run, `runs/<label>/`, `cls/`, `patch/`). Launch with
  `( setsid nohup … < /dev/null > … 2>&1 & )`; poll in bounded background loops; kill by PID.

**Arms.** All at 2 GiB unless stated; fresh node per run; R = 5 rounds unless stated.

| Arm | Heap | Load | Runs | Purpose |
|---|---|---|---|---|
| **S0** shakedown (not a reading) | 2 GiB | VEC, HEX, WB at D_s = 500,000 (tables made with that dimension; WB M = 61), N = 1, 2 sequential each; then the I build with VEC D_s once | 1 lifetime (+1 for I) | reachability: response `RESULT Void` (or a write timeout, recorded), readback cell length 2·D_s (VEC) / D_s (HEX); latency per element; class-load source of the patched class in I |
| **D1** diagnostic | 8 GiB | VEC, N = 1, 3 sequential requests | 1 lifetime | **U of the holder**, independent of K (histograms below); calibrates b and D\* |
| **T** test | 2 GiB | VEC, N = 2 | 3 | V1: OOM endpoint |
| **C1** matched-path control | 2 GiB | HEX, N = 2 (same QUERY path, same wire bytes and K, same concurrency; no per-element objects) | 3 | V2 |
| **C2** multiplicity control | 2 GiB | VEC, N = 1 | 3 | V2 (one request alone) |
| **I** intervention | 2 GiB | VEC, N = 2, **patched `QueryMessage`** (large unprepared QUERYs one at a time) | 3 | V4 |
| **B** budget search | 4 / 8 / 16 GiB / 31,744 MiB | VEC, N = N(H) = 5 / 9 / 17 / 31, R = 3 | 1 each, then 2 more at the largest failing heap | V7: largest failing budget, n/3 |
| **W** documented-limit form | 2 GiB | WB, N = 2 | 3 | the same holder with 8,192-dimension vectors |
| **WC2** | 2 GiB | WB, N = 1 | 3 | W's low-multiplicity control |
| **WI** | 2 GiB | WB, N = 2, patched `QueryMessage` | 3 | W's intervention |
| C3 (only if time) | 2 GiB | VEC's cell as a **bound** value: PREPARE `INSERT INTO u17.t (pk, v) VALUES (0, ?)` + EXECUTE with the 12,000,000-byte serialized vector, N = 2 | 1 | supporting: the same cell without a literal |

**Pre-declared dial rules.**
- **D\* from D1** (calibration of footprint before any T reading): b = max over D1's in-request samples of
  ΣΔbytes(claimed classes) / D. Then D\* = min(8,000,000, max(3,000,000, ⌊1.15 × 10⁹ / b / 500,000⌋ × 500,000)): for
  b in 175–200 B, D\* = 6,000,000 (no change). If D\* ≠ 6,000,000, every later arm uses D\* (VEC, HEX, and WB with
  M = ⌊D\*/8,192⌋) and N(H) is recomputed with U_req = b·D\*; record it as a dated amendment before T run 1.
- If T run 1 survives at N = 2, raise N to 3, then 4 (2 GiB; 4 × 12.0 MB = 48.0 MB < 51.2 MiB per-IP limit, no
  pause); the first N with an OOM is N\*, run T ×3 at N\*, and C1 and I at N\*; C2 becomes the nearest surviving N
  (N\* − 1). The same for W/WC2/WI.
- If C2 (N = 1) OOMs in ≥ 1 of 3, the claimed condition becomes N = 1 at 2 GiB (one 12 MB INSERT): C1 runs at N = 1;
  the semaphore intervention cannot act on one request, so the status carries `(no intervention)` with D1 + C1 as the
  attribution, and T is reported as the N = 2 arm.
- If a B step survives, run one step between it and the last failing heap (e.g. 12 GiB with N = 13) if time allows.

**Intervention (arms I, WI).** A diagnostic build of one class, the unmodified jar otherwise: copy
`systems/cassandra/source/src/java/org/apache/cassandra/transport/messages/QueryMessage.java` to
`harness/QueryMessage.java`; rename the existing `execute(QueryState, Dispatcher.RequestTime, boolean)` to
`executeU17` (private, without `@Override`, body unchanged) and add:

```java
    // U17 intervention: unprepared QUERYs with >= 1 MiB of text are parsed, prepared and executed one at a time
    private static final java.util.concurrent.Semaphore U17_LARGE_QUERY = new java.util.concurrent.Semaphore(1, true);

    @Override
    protected Message.Response execute(QueryState state, Dispatcher.RequestTime requestTime, boolean traceRequest)
    {
        boolean large = query.length() >= (1 << 20);
        if (large)
            U17_LARGE_QUERY.acquireUninterruptibly();
        try
        {
            return executeU17(state, requestTime, traceRequest);
        }
        finally
        {
            if (large)
                U17_LARGE_QUERY.release();
        }
    }
```

Save `diff -u` as `harness/querymessage-intervention.diff`; compile with
`javac --release 11 -cp "tree/build/apache-cassandra-5.0.9-SNAPSHOT.jar:tree/lib/*:tree/build/lib/jars/*" -d patch harness/QueryMessage.java`;
for I/WI copy `patch/org/apache/cassandra/transport/messages/QueryMessage*.class` into the run's
`conf/org/apache/cassandra/transport/messages/` (`CASSANDRA_CONF` is the first classpath entry,
`bin/cassandra.in.sh:27`, so the patched class shadows the jar's). Every arm runs with
`-Xlog:class+load=info:file=<run>/classload.log`; check the `QueryMessage` line's `source:` (the run's `conf/` in I/WI,
the jar elsewhere). The patch bounds the multiplicity of the holder (one large literal parse at a time) and changes
nothing else; small queries and every other message are not affected. Record I's completed requests, response codes and
latency per round next to C2's (the second request of a round waits for the first), so a survival that stops useful
work is not mistaken for a fix.

**Realistic fault:** none needed.

**Instruments** (U independent of K; K = the request body bytes from the frame header, 12,000,046 B per VEC request,
which is what the in-flight limits charge; the cell 12,000,000 B, which is what the mutation check counts).
- **D1 (U of the holder):** one `jcmd <pid> GC.class_histogram` before the first request (baseline); then for each of
  the 3 sequential requests, `GC.class_histogram` back to back (≈ 1–2 s apart) while it is in flight. Per sample record
  instances and bytes of `org.antlr.runtime.CommonToken`, `org.apache.cassandra.cql3.Constants$Literal`,
  `org.apache.cassandra.cql3.Constants$Value`, `java.lang.String`, `[B` (`byte[]`), `java.nio.HeapByteBuffer`,
  `[Ljava.lang.Object;`, `[C` (match the `(java.base@11.0.33)` module suffix, U8 A2). U_req = max over samples of
  ΣΔbytes of these classes over baseline; b = U_req / D. Also per-request latency, response code and readback length.
  The forced GCs slow the request; acceptable in a diagnostic arm.
- **All arms:** GC log `-Xlog:gc*=info:file=<run>/gc.log:time,uptime,level,tags:filecount=5,filesize=20m` (heap after
  every pause → live peaks; `gcwin.py` for the service-loss criterion); JMX sampler (`C2Sampler`, 1 s: heap used, GC
  counts, `Native-Transport-Requests` active/pending, `Client` `PausedConnections` if exposed); `jcmd <pid> Thread.print`
  every 10 s during load: count NTR threads with a `org.antlr.runtime`, `Cql_Parser`, `CqlParser`, `Vectors$Literal` or
  `ByteBufferUtil.bytes` frame (= parses/prepares in flight, the actual multiplicity); `RssAnon`, cgroup
  `memory.current` and `memory.events` at start/end and on death; client CSV; `stdout.log`/`system.log` for
  `java.lang.OutOfMemoryError`, `OnOutOfMemoryError`, `Request is too big`, write timeouts and dropped `MUTATION`.
- **At OOM (2 GiB only):** the default heap dump into the run dir (≤ 2.7 GB). For **T run 1** and **W run 1** run
  `hprof-histo.py` (want-list: `CommonToken`, `Constants$Literal`, `Constants$Value`, `String`, `byte[]` of length 1,
  `HeapByteBuffer`, `Object[]` ≥ 1 M elements, `char[]` ≥ 1 M, `ErrorCollector` = parses in progress) and
  `hprof_oome_thread.py` / `hprofstacks.py <hprof> Cql_Parser|Vectors` (the OOME thread's frames and the other request
  thread's); keep the text outputs in `logs/`, delete the hprof. T/W runs 2–3: at least the OOME thread; delete the
  dump after. Arms above 2 GiB (D1, B): `-XX:-HeapDumpOnOutOfMemoryError` appended in `JVM_EXTRA_OPTS`; in B take one
  `jcmd <pid> GC.class_histogram -all` (no forced GC) when heap used first exceeds 85 %, if the JVM answers.

**Predicted response** (stated before readings).
- S0: `RESULT Void` (or `0x1100` write timeout if the parse of D_s takes > 2 s: recorded, not a failure) for VEC, HEX
  and WB; readback 1,000,000 B (VEC) and 500,000 B (HEX); latency growing ≈ linearly with D.
- D1: ΔCommonToken ≥ 0.9 × 2D (≥ 10.8 M) in at least one in-parse sample per request, or (in a prepare-phase sample)
  ΔHeapByteBuffer ≥ 0.9·D and ΔConstants$Literal ≥ 0.9·D; U_req 1.0–1.25 GB per request (b 170–210 B) against
  K = 12.0 MB. Latency a few seconds to ≈ 20 s per request (x86, with histograms).
- **T (2 GiB, N = 2):** Java heap OOM (`java.lang.OutOfMemoryError: Java heap space`, process killed by
  `OnOutOfMemoryError`) in **3/3**, in round 1, within ≈ 60 s of the first request; OOME thread a
  Native-Transport-Requests thread in the parse (`ArrayList.grow` ← `BufferedTokenStream.fetch`, `Lexer.emit`/
  `CommonToken.<init>`, `Cql_Parser.listLiteral`/`constant`, `CommonToken.getText`) or in prepare
  (`Vectors$Literal.prepare`, `ByteBufferUtil.bytes`); the dump shows ≥ 70 % of the heap in the listed classes, with
  2 parses/prepares in progress. cgroup `oom_kill` 0.
- C1 (HEX, N = 2): **0/3** OOM; 10/10 responses per run (`RESULT Void` or write timeouts, same class as S0's HEX);
  live heap after GC < 0.5 GiB.
- C2 (VEC, N = 1): **0/3** OOM; 5/5 responses per run; live peak 1.2–1.5 GB; G1 pauses possible (the margin is the
  weakest prediction).
- I (patched, N = 2): **0/3** OOM; 10/10 responses per run with the same response class as C2; the second request of a
  round answers ≈ one C2 latency later; live peak as C2's.
- B: OOM at 4 GiB (N = 5) and 8 GiB (N = 9); at 16 GiB (N = 17) and 31,744 MiB (N = 31) OOM, possibly after GC service
  loss (U8: minutes of thrash at 16 GiB). The largest failing heap is reported with its n/3.
- W (WB, N = 2): OOM 3/3 as T (the 732 statements add < 1 % to the holder); WC2 0/3; WI 0/3.
- **False-positive conditions:** D1 shows b < 60 B in every in-request sample (the per-element objects are not held),
  or T survives at N = 4 with b measured ≥ 150 B (then the arithmetic or the overlap is wrong; the verdict follows the
  playbook's "False positive or retry").

**Stopping budget.** Per run: 600 s wall from the first request, or node death, whichever first (watch rule above); a
run that completes R rounds with the node alive and no OOM line is a survival (GC service loss recorded separately with
`gcwin.py`). No escalation after an OOM beyond the pre-declared dials. Stage-2 total: **4 h 30 min** wall from its
start T0; no new run starts after **T0 + 4 h 00 min**; every process started by stage 2 is stopped by **T0 + 4 h 15 min**.

**Time plan** (each 2 GiB lifetime ≈ 1 min start incl. pre-touch + 1 min schema/idle + load + stop + dump ≈ 3–4 min):

| Step | Budget | Cumulative |
|---|---|---|
| Setup: copy tree, conf, client, compile and check the patched class; node checks | 20 min | 0:20 |
| S0 (2 lifetimes) | 15 min | 0:35 |
| D1 (1 lifetime, 3 requests with histograms) | 15 min | 0:50 |
| T × 3 (+ T1 dump parse in the background, `nice 19`) | 15 min | 1:05 |
| C1 × 3, C2 × 3 | 25 min | 1:30 |
| I × 3 | 15 min | 1:45 |
| B: 4 / 8 / 16 GiB / 31,744 MiB, one each (≤ 10 min each) | 40 min | 2:25 |
| W × 3, WC2 × 3 | 25 min | 2:50 |
| B repeats (2 at the largest failing heap) | 20 min | 3:10 |
| WI × 3 (then C3 × 1 if time) | 20 min | 3:30 |
| Cleanup, §3, §4, write-backs | 45 min | 4:15 |

If time runs short, drop from the bottom: C3, WI, B repeats, W/WC2, then the 31,744 MiB and 16 GiB steps. The minimum
valid set (V1–V5 for the main condition) is S0, D1, T × 3, C1 × 3, C2 × 3, I × 3 (≈ 1 h 45 min incl. setup).

**Node fit.** RAM: at most a 31,744 MiB heap (pre-touched) + ≤ 0.4 GB direct in use (N × 12 MB bodies) + Python client
(one 12 MB payload, N socket buffers) < 40 GiB of 125 GiB. Cores: 32 hardware threads shared by node and client
(recorded). Disk: tree 0.42 G + per-run node dir < 0.1 G (wiped) + logs (GC ≤ 100 M per run) + at most two 2.7 GB hprofs
at a time → < 7 G of 706 G free. x86_64 only; never pool with aarch64 runs.

**Controls and intervention (summary).** V2: C1 (same QUERY path, wire bytes, K, concurrency and budget, one token
instead of 6 M elements) ×3 and C2 (one request alone) ×3. V4: I (one patched class bounds the holder's multiplicity to
one large parse at a time; same load) ×3; the original failure reproduced on the unmodified build (T). V3: D1 histograms
plus the T1 dump histogram. V5: T1 dump OOME stack and histogram, `stdout.log` OOM lines, GC logs. V6: defaults as
audited. V7: 2 GiB primary, upward search to the node's own 31,744 MiB. Condition W repeats V1/V2/V4 in the
documented-limit form.

**Cleanup.** Stop every Cassandra, client, sampler and `jcmd` loop started by stage 2; delete `/mydata/s4/u17/node` and
every hprof; leave `/mydata/s4/u17/runs/` (logs only) and `/mydata/s4/u17/tree` and say so in §3. Do not touch
`/mydata/s4/cassandra-base`, `/mydata/s4/3b-*` or `/mydata/s4/NODE-LOCK` (the coordinator's).

`sha256 of §1–§2 at freeze: 68711681fc650d7cd4d801730cdbc65aea6898e238c2c7be3fbb804f5a6452d4` · computed over the lines from `## 1. Candidate` through the line before this one (`sed -n '/^## 1\. Candidate/,/^`sha256 of §1–§2 at freeze/p' <file> | sed '$d' | sha256sum`) · amendments after the freeze: dated, with reason, below this line.

**Amendment A1 (2026-11-24 09:29 EST, stage 2, before any T reading; pre-declared dial rule "D\* from D1").** D1
(8 GiB, 3 sequential VEC requests at D = 6,000,000, 20 back-to-back histograms) measured b = max ΣΔbytes(claimed
classes) / D = 1,009.1 MB / 6,000,000 = **168.2 B** (prepare-phase sample s19; the best parse-phase sample s18 was at
10.9 M of 12 M tokens, 990 MB). The rule gives D\* = min(8,000,000, max(3,000,000, ⌊1.15 × 10⁹ / 168.2 / 500,000⌋ ×
500,000)) = **6,500,000**. Every later arm therefore uses **D\* = 6,500,000**: VEC text 13,000,039 characters, body
13,000,046 B (< 16,777,216 frame), cell 13,000,000 B (< 16,777,216 mutation); HEX text 13,000,040; WB M =
⌊6,500,000 / 8,192⌋ = **793** (6,496,256 elements, ≈ 13.03 M characters, body checked < 16,777,207 by the client).
U_req = b·D\* = 1.093 GB, so N(H) = ceil((H − 0.3 GB) / 1.093 GB) + 1 = **5 at 4 GiB, 9 at 8 GiB, 17 at 16 GiB,
32 at 31,744 MiB** (31 in the frozen table); per-IP in-flight check N × 13.0 MB vs heap/40: 65 vs 107, 117 vs 215,
221 vs 429, 416 vs 832 MB (no pause); at 2 GiB the dial maximum N = 4 is 52.0 MB vs 53.7 MB (no pause).
**Deviation D-node (2026-11-24, coordinator):** the case runs on **pc75** (node3.jason92-326665, x86_64, Intel Xeon
E5-2660 v2, 40 hardware threads, 125 GiB, same kernel/JDK/build jar sha256 `570b5249…0bea90176e`) instead of pc91,
an equivalent x86 node named in §2; recorded here and in §3.

**Amendment A2 (2026-11-24 11:06 EST, stage 2, before the readings it adds).** B gave 4 GiB OOM, 8 GiB OOM, 16 GiB and
31,744 MiB GC service loss without OOM in 600 s; the dial step between (12 GiB, N = 13) OOMed, and its two repeats
gave 1 OOM and 1 service loss (12 GiB: 2/3). Under the protocol's "expand repetitions if timing produces mixed
outcomes", two more runs at 12 GiB (B12-4, B12-5, same N) and two repeats at 8 GiB (B8-2, B8-3, N = 9, so the next
lower budget has its own n/3) are added. Readings unchanged in kind; no new arm. Also added: C3 (frozen as "only if
time") ran once with a client mode `--payload PREP` (PREPARE + EXECUTE of the 13,000,000-byte serialized vector).

## 3. Runs (stage 2)

**Session.** Fresh OOM-agent stage-2 session (workflow, owner-approved batch of 2026-11-24), T0 = 2026-11-24 09:16 EST
(node lock `/mydata/s4/NODE-LOCK` on pc75 taken 09:16:31, released 11:25:54 EST); last run ended 11:25 EST (T0 + 2 h 09 min,
inside the 4 h 30 min budget). Freeze hash recomputed before any run: `68711681…6452d4`, **match** (rechecked after A1/A2).

**Environment (as run).** **pc75** = node3.jason92-326665 (CloudLab UMass), x86_64, Intel Xeon E5-2660 v2 @ 2.20 GHz,
**40** hardware threads (design: pc91, 32 threads; deviation D-node in §2 A1), 125 GiB (`MemTotal` 131,943,324 kB),
8 GiB swap (unused; `MemorySwapMax=0` on the victim scope), cgroup v2 (`memory pids` delegated to the user service),
kernel 5.15.0-203-generic, OpenJDK 11.0.33, Python 3.10. Node idle at start (load 0.00, no Java); `/mydata` 703 G free.
Untouched: `/mydata/s4/cassandra-base`, `3b-B17`, `3b-B20`, `b23`. Build: `/mydata/s4/cassandra-base` copied to
`/mydata/s4/u17/tree`, jar sha256 `570b5249d9b9a43f6809eb3da562737492192026f974b2edbd20e94bea90176e` (= the design's),
`antlr-runtime-3.5.2.jar` sha256 `ce3fc8ec…89c8734`; shipped `conf/cassandra.yaml` identical to the pinned source's
(non-comment lines). Patched class for I/WI: `QueryMessage.class` sha256 `fc8fb364…70077c43`, `QueryMessage$1.class`
`7304de35…8f32eb` (diff `harness/querymessage-intervention.diff`, exactly the §2 change). Resolved JVM (every run, from
`ps`): `-Xms/-Xmx` = the arm's heap, `-XX:MaxDirectMemorySize=15872M` (auto), G1 with `G1HeapRegionSize=16m`,
`G1NewSizePercent=50`, `MaxGCPauseMillis=300`, `InitiatingHeapOccupancyPercent=70`, `AlwaysPreTouch`,
`HeapDumpOnOutOfMemoryError` (2 GiB; `-XX:-HeapDumpOnOutOfMemoryError` above 2 GiB), `OnOutOfMemoryError=kill -9 %p`.
`yaml.diff` of every run: only `data_file_directories`, `commitlog_directory`, `hints_directory`,
`saved_caches_directory`, `cdc_raw_directory` (→ `/mydata/s4/u17/node/`); V6 audit as §2 (vector thresholds −1,
frame 16 MiB, `commitlog_segment_size` 32 MiB, `heap_buffers`, `AllowAllAuthenticator`, timeouts not raised).
Container scope `MemoryMax` = heap + 15,872 MiB + 8 GiB: `memory.events` `oom_kill 0` in **every** run.

**Harness** (`harness/`): `u17client.py` (raw v4, payloads VEC/HEX/WB, `--ddl`, `--sizes`, `--readback`; `PREP` added
for C3, A2), `victim-ctl.sh`, `run-arm.sh` (watch rule as §2), `batch.sh` + `list-*.txt` (the run order), `s0.sh`,
`setup.sh`, `C2Sampler.java`, `gcwin.py` (from U8), `hprof-histo.py` (U6's, U17 want-list), `hprof_oome_thread.py`,
`hprofstacks.py`, `QueryMessage.java` + diff. Small per-run excerpts in `logs/<label>/` (outcome, client CSV, readings,
threads, GC summary, OOM excerpt, dump outputs, `yaml.diff`, `run.meta`, `memory.events`); one line per run in
`logs/summary.txt`. Raw logs (GC, system, stdout, D1 histograms) on pc75 `/mydata/s4/u17/runs/` (≈ 0.7 GB).

**Payload sizes** (`--sizes`): at D\* = 6,500,000: VEC text 13,000,039, body **13,000,046 B** (K), frame 13,000,055;
HEX text 13,000,040, body 13,000,047; WB M = 793, 6,496,256 elements, text 13,032,084, body 13,032,091 B
(< 16,777,207, client check passed). At 6,000,000 (D1): VEC body 12,000,046 B. No run logged
`Request is too big`; no in-flight pause was needed (N × 13 MB below heap/40 in every arm).

**Instrument faults (recorded, not readings).** D1 try 1 (09:22, `logs/D1-try1-badhsum/`): the histogram summary used
an awk regex that `mawk` rejects, so the samples were lost; same lifetime outcome as D1 (3 × write timeout). Fixed to
a string match and D1 re-run in a fresh lifetime. The JMX sampler stops answering once the heap is full (heap-used
column frozen in `samples.csv` from the first seconds of each 2 GiB T/W run and of each thrash run); GC logs and
`jcmd Thread.print` counts are the readings there.

### Runs

| Label | Arm | Heap | Load | Outcome (n) | Readings |
|---|---|---|---|---|---|
| S0 | S0 | 2 GiB | D_s = 500,000: VEC, HEX, WB, N = 1, 2 sequential each | `RESULT Void` 6/6 | VEC 0.88 / 0.33 s, HEX 0.10 / 0.01 s, WB 0.45 / 0.33 s; readback cell 1,000,000 B (VEC), 500,000 B (HEX), 61 rows (WB); `QueryMessage` from the jar |
| S0-I | S0 (I build) | 2 GiB | VEC D_s, N = 1, 2 seq | `RESULT Void` 2/2 | 0.81 / 0.31 s; readback 1,000,000 B; `QueryMessage source: …/runs/S0-I/conf/` (patched class shadows the jar) |
| D1 | D1 | 8 GiB | VEC D = 6,000,000, N = 1, 3 sequential, histograms back to back | 3 × write timeout `0x1100` (8.2–8.4 s each, with histograms); alive | 20 in-request samples; see "D1" below; **b = 168.2 B/element** → D\* = 6,500,000 (A1) |
| T1 | T | 2 GiB | VEC, N = 2, R = 5 | **Java heap OOM** (death detected +74 s incl. 33 s dump) | round 1, 0 completed; 64 Full GCs, live after Full ≤ 2,012 MiB; NTR in parse/prepare 2 (every Thread.print); dump: see V5 |
| T2 | T | 2 GiB | same | **Java heap OOM** (+29 s) | round 1; 4 Full GCs; OOME thread = NTR in `BufferedTokenStream.fetch` |
| T3 | T | 2 GiB | same | **Java heap OOM** (+50 s) | round 1; 47 Full GCs, live after Full ≤ 2,012 MiB; 2 NTR in parse |
| C1-1/2/3 | C1 | 2 GiB | HEX, N = 2, R = 5 | **survived 3/3**; 10/10 `RESULT Void` each | latency 0.14–0.28 s; 0 Full GCs; heap after GC ≤ 83 MiB; in-parse count 0 |
| C2-1/2/3 | C2 | 2 GiB | VEC, N = 1, R = 5 | **no OOM 3/3**; 5/5 answered each, all write timeout `0x1100` | latency 5.12–5.40 s; 9–10 Full GCs, live after Full ≤ 884 / 1,290 / 886 MiB; max STW 60 s window 12 % |
| I1/2/3 | I (patched) | 2 GiB | VEC, N = 2, R = 5 | **no OOM 3/3**; 10/10 answered each, all `0x1100` (C2's class) | first request of a round 5.10–5.65 s, second 10.1–11.8 s (≈ one C2 latency later); NTR threads 2, in parse/prepare **1** (every sample); live after Full ≤ 1,338 MiB; max60 24–26 % |
| B4 | B | 4 GiB | VEC, N = 5, R = 3 | **Java heap OOM** (+18 s) 1/1 | at-85 % histogram: 30.7 M `CommonToken` (1.48 GB), 15.4 M `Constants$Literal`; 5/5 NTR in parse |
| B8, B8-2, B8-3 | B | 8 GiB | VEC, N = 9, R = 3 | **Java heap OOM 3/3** (+14, +51, +22 s) | 9/9 NTR in parse; live after Full ≤ 7,666–8,006 MiB |
| B12, -2, -3, -4, -5 | B (+A2) | 12 GiB | VEC, N = 13, R = 3 | **Java heap OOM 3/5** (+83, +34, +35 s); B12-3, B12-5: no OOM in 600 s, **GC service loss** (≥ 90 % STW over 889 / 834 s), 0 of 13 answered | 13/13 NTR in parse in every answered `Thread.print` (a few timed out during thrash) |
| B16 | B | 16 GiB | VEC, N = 17, R = 3 | no OOM in 600 s; **GC service loss** (≥ 90 % STW over 891 s, 414 Full GCs); 0 of 17 answered (85 client 120-s timeouts) | at-85 % histogram 15.0 GB, 148.6 M `CommonToken` (7.13 GB) + 74.3 M `Constants$Literal` + 74.4 M `String`; 17/17 NTR in parse |
| B31 | B | 31,744 MiB | VEC, N = 32, R = 3 | no OOM in 600 s; **GC service loss** (≥ 90 % STW over 813 s, 211 Full GCs); 0 of 32 answered | at-85 %: 255.8 M `CommonToken` (12.3 GB); 32/32 NTR in parse |
| W1, W2, W3 | W | 2 GiB | WB (793 × 8,192-dim vectors, single-partition unlogged batch), N = 2, R = 5 | **Java heap OOM 3/3** (+43, +136, +47 s) | round 1, 0 completed; W2 after ≈ 120 s of thrash (≥ 90 % STW over 116 s); 2 NTR in parse; dumps below |
| WC2-1/2/3 | WC2 | 2 GiB | WB, N = 1, R = 5 | **no OOM 3/3**; 5/5 answered each, all `0x1100` | 4.9–5.5 s; live after Full ≤ 843 / 897 / 1,292 MiB |
| WI1/2/3 | WI (patched) | 2 GiB | WB, N = 2, R = 5 | **no OOM 3/3**; 10/10 answered each, all `0x1100` | second request of a round 10.3–10.6 s; in parse/prepare 1; live after Full ≤ 1,352 MiB |
| C3-1 | C3 (supporting) | 2 GiB | PREPARE once + EXECUTE of the bound 13,000,000-byte vector, N = 2, R = 5 | survived; **10/10 `RESULT Void`** | 0.2–0.3 s; 0 Full GCs; heap after GC ≤ 82 MiB |

**D1 (U of the holder, independent of K).** Baseline histogram, then 20 samples while the 3 requests ran (≈ 1–1.5 s
apart; `logs/D1/histsum.csv`). Δ over baseline of the eight claimed classes (bytes, jcmd shallow):

| Sample (phase) | ΔCommonToken (n) | Constants$Literal (n) | HeapByteBuffer / Constants$Value (Δn) | ΣΔ claimed | ΔTotal heap |
|---|---|---|---|---|---|
| s4 (req 1, parse, 85 % of tokens) | 10,216,736 | 5,108,358 | 0 / 0 | 918 MB | 999 MB |
| s5 (req 1, prepare) | 0 | 6,000,001 | 1,532,417 / 1,532,416 | 603 MB | 656 MB |
| s11 (req 2, parse) | 10,199,834 | 5,099,907 | 0 / 0 | 930 MB | 1,015 MB |
| s18 (req 3, parse, 91 % of tokens) | 10,911,502 | 5,455,741 | 0 / 0 | 990 MB | 1,075 MB |
| **s19 (req 3, prepare peak)** | 0 | 6,000,001 | **6,000,003 / 6,000,000** | **1,009 MB** | 1,091 MB |

Per-element objects as claimed: 2 `CommonToken` per element (48 B each), a `String` + `byte[1]` + `Constants.Literal`
per element in the parse, then per element a `Constants.Value` and a one-byte `HeapByteBuffer`, all on the request
thread. **U_req ≥ 1.01 GB** (claimed classes; 1.09 GB whole-heap Δ) for one request whose counted size is K =
12,000,046 B: **U/K ≈ 84** (b = 168.2 B per element against 2 B counted). The parse samples catch at most 91 % of the
12 M tokens, so the true parse peak is ≈ 1.09 GB (s18 / 0.91). The prediction (b 170–210 B) held within 2 %.

**Response class.** Every VEC and WB request at D\* (and at 6 M in D1) answered `0x1100 Operation timed out - received
only 0 responses` (write timeout): parse + prepare alone take ≈ 5 s, past the 2 s `write_request_timeout` counted from
the start of processing, so the mutation is never applied. S0 (≤ 0.9 s) and C3 (bound value, 0.2 s) were applied.
This was predicted as possible and does not bound the holder (protection map row "Write deadline").

**V5 (initiating failure, 2 GiB).** `stdout.log` of every OOM run: `java.lang.OutOfMemoryError: Java heap space`,
`Dumping heap …`, `Executing /bin/sh -c "kill -9 <pid>"`; no other error first. OOME-initiating thread
(`logs/<T|W>n/dump-oome-thread.txt`): **T2** — a Native-Transport-Requests thread in `ArrayList.grow` ←
`BufferedTokenStream.fetch` (the token list); **W2** — an NTR thread in `Lexer.emit` (new `CommonToken`); **T1, T3** —
the logback `AsyncAppenderBase$Worker` (a bystander that allocated first while the heap was full), with both NTR
threads in `Lexer.emit` / `BufferedTokenStream.fetch` ← `Cql_Parser.listLiteral` ← `collectionLiteral` ← `value` in the
T1 dump; **W1, W3** — no trace with a leading `OutOfMemoryError.<init>` frame in the dump (initiating thread not
resolved); W1's `GCInspector` logged `G1 Old Gen: 2,126,801,696 -> 2,108,877,560` just before, and the dump shows one NTR
thread in the parse (`DFA.predict` ← `BufferedTokenStream.fetch`). **T1 dump histogram** (`logs/T1/dump-histo.txt`,
2.97 GB file, shallow estimate 2,569 MB): `CommonToken` 19,964,142 (1,198 MB), `Constants$Literal` 9,982,051 (399 MB),
`Object[]` 311 MB (4 arrays ≥ 1 M elements = the token and literal lists, 302 MB), `String` 10,073,139 (292 MB),
`byte[]` 10,075,818 of which **9,982,393 of length 1** (211 MB), `char[]` 104 MB (4 arrays ≥ 1 M elements: the two
parses' char streams and query copies); `ErrorCollector` 2 (= two parses in progress). The claimed classes are **2,515 MB = 98 %** of the dump. **W1
dump**: `CommonToken` 10,201,222, `Constants$Literal` 5,092,212, `byte[1]` 5,092,565: the same holder, from 8,192-element
lists. Dumps deleted after parsing.

**V7 / budget search (largest failing budget).** 4 GiB 1/1, **8 GiB 3/3**, 12 GiB 3/5 (2/5 GC service loss for the
whole 600 s), 16 GiB 0/1 OOM + service loss, 31,744 MiB (the node's own resolved heap) 0/1 OOM + service loss. Above
≈ 12 GiB G1 thrashes (hundreds of Full GCs each reclaiming little) instead of throwing within the 600 s stopping budget;
no request is answered there either.

**Deviations from the design.** (1) Node pc75 instead of pc91 (A1, coordinator). (2) D\* = 6,500,000 by the
pre-declared D1 rule (A1); N(H) at 31,744 MiB = 32 (frozen table: 31). (3) A2: two extra repetitions at 8 GiB and at
12 GiB (mixed outcome), C3 run with an added client mode. (4) D1 histogram summary fixed after try 1 (instrument). (5)
The JMX sampler cannot read a full heap (instrument limit; GC logs used). Nothing else changed; no constraint changed in
any T, W or B run.

**Cleanup (11:25 EST).** Every Cassandra, client, sampler and `jcmd` process started by stage 2 stopped (checked: no
`java`/client/batch process left, no `u17-*` scope); every hprof deleted after parsing; `/mydata/s4/u17/node` deleted.
Left on pc75: `/mydata/s4/u17/tree` (419 M), `conf-pristine`, `cls`, `patch`, `harness`, `runs/` (logs only,
≈ 0.7 G), `out/` (the excerpts copied to `logs/`). Lock released.

## 4. Conclusion (stage 2)

**Verdict: true positive.** Protocol status **`verified-OOM · deployment`**; direction **unprotected** — unprotected
accumulation (no control covers the per-element objects of a literal's parse and prepare; the only bound is the
implicit 128 native threads × request size) together with unprotected configuration (`vector_dimensions_warn/
fail_threshold: -1`, and the documented 8K dimension limit is not enforced by `VectorType`). Interpretation: a
validation/sizing gap plus a parser design that materializes every token; not documented as by design.

**Reason.** At every shipped default and a 2 GiB heap, two concurrent unprepared INSERTs of a 6.5 M-element
`vector<tinyint>` literal (13.0 MB each, accepted by the 16 MiB frame, in-flight and mutation checks) exhaust the heap
in 3/3 runs, in round 1, on the parse of the literal. D1 measured the holder independently of every counter: ≈ 168 B of
heap per element (two ANTLR tokens, a `String`, a `Constants.Literal`, then a `Constants.Value` and a one-byte
`HeapByteBuffer`) against the 2 B per element that the frame, in-flight and mutation checks count (U/K ≈ 84; ≈ 1.09 GB
per request). The matched-path control with the same QUERY path, wire bytes, K and concurrency (a 13 MB hex blob
literal: one token) survived 3/3 with < 0.1 GiB live, one VEC INSERT alone survived 3/3, and admitting only one large
unprepared QUERY at a time (one patched class) removed the OOM 3/3 at the same load, with the same response class and
the second request answered one parse later. The T1 dump attributes 98 % of the heap to the claimed classes with two
parses in progress. The documented-limit form (793 × 8,192-dimension vectors in one single-partition batch, which no
batch-size check applies to) behaves the same (W 3/3 vs WC2 0/3, WI 0/3), so the result does not depend on the
unenforced 8K limit. The bound-value form of the same cell (C3) is cheap (10/10 written, < 0.1 GiB live).

| | Evidence | Runs |
|---|---|---|
| V1 Repetition | Java heap OOM 3/3 at 2 GiB, N = 2 | T1–T3 (W1–W3 for the documented-limit form) |
| V2 Matched control | HEX literal, same path/K/N: 0/3, 10/10 written; VEC N = 1: 0/3, 5/5 answered | C1-1..3, C2-1..3 (WC2-1..3) |
| V3 Measurement | b = 168.2 B/element, U_req ≥ 1.01 GB vs K = 12.0 MB (histograms, independent of K); T1 dump 98 % in the claimed classes | D1, T1 dump, B at-85 % histograms |
| V4 Intervention | one large unprepared QUERY at a time: 0/3, 10/10 answered (C2's class), second request one parse later | I1–I3 (WI1–WI3) vs T1–T3 on the unmodified jar |
| V5 Initiating failure | first error `OutOfMemoryError: Java heap space`; OOME thread an NTR thread in `BufferedTokenStream.fetch` / `Lexer.emit` (T2, W2), a bystander logback thread with both NTR threads in `listLiteral` (T1, T3); T1 dump histogram | T1–T3, W1–W3 |
| V6 Default constraints | every capacity at its shipped default; `yaml.diff` = directories only; the only patch is in I/WI | all |
| V7 Acceptable budget | 2 GiB (≥ 512 MiB standing rule, ideal); largest failing budget **8 GiB 3/3**, 12 GiB 3/5; 16 GiB and 31,744 MiB GC service loss (≥ 90 % STW over ≥ 13 min) without OOM in 600 s | B4, B8 ×3, B12 ×5, B16, B31 |

**Limits.** (1) Above ≈ 12 GiB the endpoint within 600 s is GC service loss, not OOM (the request multiplicity scaled
with N(H) was not raised further; the node answers nothing during it). (2) Every VEC/WB request at this size ends in a
write timeout, so the attack spends memory for writes that never apply; a request just under 2 s of parse (≈ 2 M
elements) would be applied but would need ≈ 3× the concurrency for the same heap (estimate, not run). (3) The `boolean` element type of the
OC-579 row was not run (by design choice, §1; ≈ 0.3–0.4× the elements per frame, and `BooleanType` shares its two
buffers). (4) Single node, client on the same node (loopback, one client IP), x86_64 only. (5) The OOME-initiating
thread of W1 and W3 was not resolved from their dumps. No new holder outside the claimed one appeared in any dump or
histogram; OC-579 already names CP-1, CP-12 and CP-8, so no new clue pattern is proposed.
