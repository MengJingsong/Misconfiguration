# U17 — vector_dimensions (off): a vector literal in an unprepared INSERT is parsed and prepared into ≈ 190 B of heap per element  <!-- file: cassandra/cases/vector_dimensions--vector-literal-per-element-parse/vector_dimensions--vector-literal-per-element-parse.md -->

| Field | Value |
|---|---|
| Case ID | `U17` (U = unprotected accumulation; README "ID prefixes") |
| From | `OC-579` of the phase 1 OOM candidate list (owner-approved follow-up of U8, the write side; batch of 2026-11-24) |
| Phase-1 case file | [`no_constraint-isallzero-vectorelement--autonomous`](../../../../capacity-enforcement-exp/cassandra/stage3-ai-deep-read/cases/no_constraint-isallzero-vectorelement--autonomous.md) (the same as U8's) |
| System / pinned source | Cassandra 5.0.9 (`systems/cassandra/source/`, `build.xml` `base.version` 5.0.9); ANTLR runtime 3.5.2; built copy `pc91:/mydata/s4/cassandra-base` (`build/apache-cassandra-5.0.9-SNAPSHOT.jar`, sha256 `570b5249…0bea90176e`) |
| Stage 1 (design) | OOM-agent stage-1 session (workflow, owner-approved batch of 2026-11-24), 2026-11-24 05:00–06:10 America/New_York; nothing run (nodes checked read-only over ssh) |
| Stage 2 (verify) | pending (a fresh session) |
| Verdict | `pending` |

## Summary

- **Conclusion:** pending (stage 2).
- **Root cause:** pending (stage 2).
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

## 3. Runs (stage 2)

pending

## 4. Conclusion (stage 2)

pending
