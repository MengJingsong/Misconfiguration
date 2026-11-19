# U6 — ErrorCollector.errorMsgs: one retained syntax-error message per unlexable character of a 16 MiB CQL string (≈ 120 B of heap per wire byte)  <!-- file: cassandra/cases/ErrorCollector_errorMsgs--one-message-per-bad-character/ErrorCollector_errorMsgs--one-message-per-bad-character.md -->

| Field | Value |
|---|---|
| Case ID | `U6` (unprotected accumulation; README "ID prefixes") |
| From | cluster `OC-409` (primary), `OC-410`, `OC-278`, `OC-285`, `OC-140` of the phase 1 OOM candidate list (all `picked: U6`); coverage per row in §1.2 |
| Phase-1 case files | [`no_constraint-istokenvalid-token_position--autonomous`](../../../../capacity-enforcement-exp/cassandra/stage3-ai-deep-read/cases/no_constraint-istokenvalid-token_position--autonomous.md) (OC-409, OC-410; no stage 4); [`max-unsigned-short-prepare-boundTerms--autonomous`](../../../../capacity-enforcement-exp/cassandra/stage3-ai-deep-read/cases/max-unsigned-short-prepare-boundTerms--autonomous.md) (OC-278, OC-285; stage 4: [results](../../../../capacity-enforcement-exp/cassandra/stage4-runtime-verification/results/max-unsigned-short-prepare-boundTerms--autonomous.md)); [`prepared_statements_cache_size-storePreparedStatement-capacityToBytes--autonomous`](../../../../capacity-enforcement-exp/cassandra/stage3-ai-deep-read/cases/prepared_statements_cache_size-storePreparedStatement-capacityToBytes--autonomous.md) (OC-140; stage 4: [results](../../../../capacity-enforcement-exp/cassandra/stage4-runtime-verification/results/prepared_statements_cache_size-storePreparedStatement-capacityToBytes--autonomous.md)) |
| System / pinned source | Cassandra 5.0.9 (`systems/cassandra/source/`, `build.xml` `base.version` 5.0.9); built tree `ms0604:/mydata/s4/cassandra-base` (aarch64); OpenJDK 11.0.33; ANTLR runtime 3.5.2 (`lib/antlr-runtime-3.5.2.jar`) |
| Stage 1 (design) | OOM-agent stage-1 session (workflow, wave 4), 2026-11-18 13:40–14:20 America/New_York |
| Stage 2 (verify) | OOM-agent stage-2 session (wave 4), runs 2026-11-18 13:55–16:07 ET on `ms0604`; suspended before §3/§4; resumed by a fresh stage-2 session 18:21 ET (no runs repeated, §3.0) |
| Verdict | **retry** — protocol status `verified-gap · service-loss · deployment` (no OOM in the main arm) |

## Summary

- **Conclusion (stage 2):** **retry.** The mechanism is real and fully attributed, but the claimed endpoint (Java heap OOM)
  was not reached. Two 16 MiB `#` QUERYs on a 2 GiB heap with every capacity at its default fill the heap with retained
  lexer messages (15.86 M `LinkedList$Node` + `String` + `byte[]` ≈ 1.95 GB, ≈ 120 B per message, U/K ≈ 58) and drive
  the node into **GC service loss** (≥ 90 % stop-the-world over 193–200 s windows, 3/3; zero responses), not OOM: G1's
  Full GCs keep reclaiming one 16 MiB region of transient garbage per cycle, so the lexers creep on and the heap never
  fails an allocation within 338 s (T2, 0/3 OOM), 430 s at 4 GiB (T4-1) or 1,203 s (D2-1). The matched comment
  control (0/3) and the keep-first-message intervention (0/3, same error returned in 176 s) stay healthy.
- **Root cause (stage 2, as measured):** `ErrorCollector.errorMsgs` (an unbounded `LinkedList<String>`) keeps one
  message per unlexable character for the whole parse although only the first is used; no capacity control covers it
  (the frame size and in-flight limits charge only the 16.8 MB of wire bytes per request). Unprotected accumulation,
  suspected implementation defect. Supporting arm B (PREPARE of 8.39 M markers, OC-278/285) **did** end in heap OOM 3/3
  at 2 GiB (token list growth in `BufferedTokenStream.fetch`), with one matched control surviving.
- **Hypothesis under test (stage 1, as designed):** the CQL lexer reports **every** character that no lexer rule
  matches (ANTLR 3.5.2 `Lexer.nextToken` → `reportError` → `recover` consumes one character and loops; no
  error-recovery suppression), and Cassandra's `ErrorCollector` appends one message per report to an unbounded
  `LinkedList<String>` (`ErrorCollector.java:52`, `:81`) although only the first message is ever used (`:98-102`). A
  QUERY whose text is 16,777,200 `#` characters (the largest a protocol-v4 frame carries at the default 16 MiB frame
  size) therefore builds ≈ 16.8 M messages of ≈ 54 characters, **≈ 120 B of heap each, ≈ 1.88 GiB per request**, all live
  until the parse ends. The only controls on the request — the 16 MiB frame size and the native in-flight limits
  (heap/10 global, heap/40 per IP) — count the **16.8 MB of wire bytes**, ≈ 1/120 of what the parse holds. Two such
  requests from one client, well inside its per-IP limit, are predicted to exhaust a 2 GiB heap (Java heap OOM) with
  every capacity at its shipped default; the budget search runs 4 and 8 GiB with 3 and 6 requests.

## 1. Candidate

### 1.1 The cluster rows (quoted from `phase1-oom-candidates.md`)

| ID | Date | Phase-1 case file | Agent | Clue (mechanism, rough magnitude at defaults) | Patterns | Status |
|---|---|---|---|---|---|---|
| OC-409 | 2026-11-18 | `no_constraint-istokenvalid-token_position--autonomous` | autonomous | ErrorCollector.errorMsgs, an unbounded LinkedList<String>, keeps one message per lexer error for the whole parse. [details](runs/wave2.md#oc-409) | — | picked: U6 |
| OC-410 | 2026-11-18 | `no_constraint-istokenvalid-token_position--autonomous` | guided | Holder: ErrorCollector.errorMsgs, a LinkedList<String> per parse that keeps one message for every lexer and parser syntax error, although only the first is ever used (throwFirstSyntaxError, ErrorCollector.java:100-101). [details](runs/wave2.md#oc-410) | CP-1, CP-2, CP-13 | picked: U6 |
| OC-278 | 2026-11-18 | `max-unsigned-short-prepare-boundTerms--autonomous` | autonomous | The 65535-marker check runs only after the whole query string has been lexed, parsed and prepared, so the parser's memory is already spent when the check rejects the statement. [details](runs/wave2.md#oc-278) | — | picked: U6 |
| OC-285 | 2026-11-18 | `max-unsigned-short-prepare-boundTerms--autonomous` | guided | Holder: the coordinator's native-transport request thread during PREPARE (ANTLR token buffer, the parsed and prepared statement, then the jamm measureDeep walk of it). [details](runs/wave2.md#oc-285) | CP-11, CP-1, CP-12, CP-7 | picked: U6 |
| OC-140 | 2026-11-17 | `prepared_statements_cache_size-storePreparedStatement-capacityToBytes--autonomous` | guided | Holder: the parsed and prepared statement graph of a PREPARE (CQL text, AST, terms and selectors), plus jamm's visited-object tracking during ObjectSizes.measureDeep. [details](runs/wave1.md#oc-140) | CP-11, CP-12, CP-1 | picked: U6 |

Full texts ([`runs/wave2.md#oc-409`](../../../../capacity-enforcement-exp/cassandra/stage5-oom-clue-find/runs/wave2.md#oc-409),
[`#oc-410`](../../../../capacity-enforcement-exp/cassandra/stage5-oom-clue-find/runs/wave2.md#oc-410),
[`#oc-278`](../../../../capacity-enforcement-exp/cassandra/stage5-oom-clue-find/runs/wave2.md#oc-278),
[`#oc-285`](../../../../capacity-enforcement-exp/cassandra/stage5-oom-clue-find/runs/wave2.md#oc-285),
[`wave1.md#oc-140`](../../../../capacity-enforcement-exp/cassandra/stage5-oom-clue-find/runs/wave1.md#oc-140)). The primary's
full text, quoted:

> ErrorCollector.errorMsgs, an unbounded LinkedList<String>, keeps one message per lexer error for the whole parse. Every
> message stays live until throwFirstSyntaxError, which uses only the first. The ANTLR 3.5.2 Lexer reports every
> unrecognised character: Lexer.reportError has no errorRecovery suppression, and recover() consumes one char. Cassandra's
> Lexer.g displayRecognitionError forwards each one to ErrorCollector.syntaxError, which builds 'line 1:<pos> no viable
> alternative at character '#'' (about 54 chars) and adds it to the list. Only the parser's recover() is a no-op; the
> lexer's is not. The lexer is pulled lazily, but one nextToken() call loops over a whole run of bad characters before it
> returns. So a single QUERY whose text is all '#' (no lexer rule matches '#') makes one error per character before
> parsing fails. Nothing caps the error count; the only bound is the query length. native_transport_max_message_size
> defaults to min(max_mutation_size=16 MiB, in-flight limits), so about 16 MiB. Rough size: 16.7M errors x (about 72 B
> byte[] + 24 B String + 24 B LinkedList node) is about 2 GB retained per query. Add 16 MiB for the query String and
> 32 MiB for the ANTLRStringStream char[]. The in-flight byte limits charge only the 16 MiB frame, not this roughly 120x
> amplification. So 2-4 concurrent such requests (up to 128 native threads) exceed a default 4-8 GB heap.
>
> **Where:** cassandra-5.0.9 src/java/org/apache/cassandra/cql3/ErrorCollector.java:52 (errorMsgs), :69-81 syntaxError
> adds builder.toString(), :98-102 throwFirstSyntaxError only after the parse; src/antlr/Lexer.g:51-55
> displayRecognitionError -> listener.syntaxError for every lexer error; src/antlr/Parser.g:193-205 (only the parser's
> recover is a no-op); src/java/org/apache/cassandra/cql3/CQLFragmentParser.java:65-82 (ErrorCollector attached to lexer
> and parser, throw after parse); cql3/QueryProcessor.java:927 parse of the client query;
> transport/messages/QueryMessage.java:50 readLongString; config/DatabaseDescriptor.java:903-905, :3237-3244 (default
> max message size = min(max_mutation_size, in-flight limits))

**Triage** ([`runs/triage-2026-11-18.md`](../../../../capacity-enforcement-exp/cassandra/stage5-oom-clue-find/runs/triage-2026-11-18.md),
advisory) ranked the primary **2 of 20**:

> | 2 | OC-409 | yes | single ARM node | A 16 MiB QUERY made only of '#' (no lexer rule matches it) produces one
> ErrorCollector message per character. That is about 16.7M strings at about 120 B each, roughly 2 GB kept live for the
> whole parse, against 16 MiB charged to the in-flight limits. One request, or at most 2-3 from one IP (the per-IP limit
> is heap/40, about 51 MiB), should exhaust a 2 GiB heap. | No existing case (B11 is a different render amplification).
> Duplicate of OC-410 and in the same parser-amplification family as OC-278, OC-285 and OC-140. |

and OC-278 6 of 20 ("Duplicates OC-285 (and OC-140 for the prepared-cache measure). Same parser-amplification family as
OC-409."); its notes group "Parser amplification: OC-140, 278, 285, 409, 410" and list OC-409 and OC-278 among the
"likely fastest first wins, each one request or one read on a single 2 GiB node".

### 1.2 The shared mechanism and what this design covers

**Shared mechanism (all five rows):** a CQL string of up to 16 MiB is admitted and charged by its **wire bytes** only
(frame size, native in-flight limits); the coordinator's request thread then lexes, parses (and for PREPARE, prepares and
`measureDeep`s) the whole string, building heap structures **proportional to the string length × a large factor**, and
no check bounds those structures before they exist (the error is thrown, or the marker limit or the cache-size guard
applies, only after the work is done).

| Row | Holder named | Covered by this design? |
|---|---|---|
| OC-409 | `ErrorCollector.errorMsgs`, one message per lexer error | **Yes, fully** — the decisive arms T/C/I and the budget search (§2.5) test exactly this QUERY of `#` characters. The case verdict is its verdict. |
| OC-410 | the same list; also parser errors with snippets and `query.split("\n")` per parser error | **Yes for the lexer part** (same holder, same payload, also notes QUERY or PREPARE). **Not covered:** the parser-error path (one message plus a 13-token snippet and a transient full `query.split` copy per *parser* error); a `#` payload yields only one parser error (at EOF, no snippet, `isTokenValid` false for Cassandra's EOF token — the phase-1 `no_constraint-istokenvalid` case). The verdict applies to the row through its lexer part. |
| OC-278 | ANTLR `CommonTokenStream` tokens + `Marker.Raw` AST + prepared markers for an 8 M-marker `IN (?,?,…)` before the 65535 check | **Partly, supporting arm only** — arm B (§2.5) sends that PREPARE and measures it (OOM or peak per request), but without its own control ×3 and intervention, so it cannot give the row a verified verdict here (write-back rule in §2.8). |
| OC-285 | the same request thread: token buffer, prepared statement, then jamm `measureDeep` of it | **Partly, as OC-278** (arm B uses PREPARE, so `measurePstmnt` at `QueryProcessor.java:469` runs before the marker check at `:757-759`). |
| OC-140 | parsed and prepared graph of a PREPARE of ≈ 8 M **literal** terms, plus `measureDeep`, before the cache guard at `:825` | **Mostly not covered**: arm B uses markers, not literals, and is rejected by the marker check before the cache guard is reached. Only the shared part (whole parse + prepare + measure before any size check) is touched by arm B. |

### 1.3 Phase-1 cases and stage 4

- **`no_constraint-istokenvalid-token_position--autonomous`** (estimate `negative`, no stage 4): `isTokenValid`
  (`ErrorCollector.java:187-190`) only decides whether a snippet is appended to a parser error; it caps nothing. Its A4
  already notes "the unrelated `errorMsgs` LinkedList (line 52) grows with the number of syntax errors and is not bounded
  by this check either" — the holder of OC-409/410. Nothing was run.
- **`max-unsigned-short-prepare-boundTerms--autonomous`** (estimate `negative`, stage 4 2026-10-26: **true negative,
  does not cap**): one prepared statement weighs 43 B per marker (2,842,844 B at 65,535 markers, unit tier);
  65,536 markers are rejected with `Too many markers(?). 65536 markers exceed the allowed maximum of 65535` after
  `parseAndPrepare`; retained prepared statements stay at the cache cap. Stage 4 never measured the **transient** parse
  memory of a statement far above 65,535 markers — the gap OC-278/285 point at.
- **`prepared_statements_cache_size-storePreparedStatement-capacityToBytes--autonomous`** (estimate `positive`, stage 4
  2026-10-19: **true positive**, cache bounded at 0.9998 × cap; knob-dependent heap 0.80 × weights; an oversize PREPARE
  reached the size guard only at caps below the 16 MiB transport limit; the `system.prepared_statements` memtable grows
  uncapped, ≈ 614 B per PREPARE). Relevant here only as the guard that runs after the whole parse and measure.

### 1.4 JIRA prior art (read-only; nothing posted)

- **Survey** (`jira-oom-survey.csv`, 604 rows): no row on the CQL lexer, parser, `ErrorCollector`, query length or
  marker count as a memory holder. Nearest: CASSANDRA-2475 (prepared statements, design discussion on an uncapped
  statement map, later capped by the cache) and CASSANDRA-19703 (cache eviction race) — neither is this mechanism.
- **JIRA REST search** (`issues.apache.org/jira/rest/api/2/search`, project CASSANDRA, 2026-11-18 13:55 ET):
  - `text ~ "ErrorCollector"` → 5: CASSANDRA-7769 (pg-style `$$` strings), **CASSANDRA-7111** (added the query snippet to
    syntax errors, 2.1; reviewers note "3.5.2 produces two errors for some syntax errors instead of one", no memory
    discussion), 7569 (IndexOutOfBounds in the snippet), 11803 (MV on a `token` column), 14096 (repair OOM; `ErrorCollector`
    appears only as one 24-byte instance in an idle heap histogram).
  - `text ~ "\"no viable alternative at character\""` → 10, all user syntax mistakes or test fixes; none about memory.
  - `text ~ "lexer" AND text ~ "memory"` → 14096 (above), 20943 (schema comments); not this.
  - `text ~ "Too many markers"` → **CASSANDRA-5598** (fixed 1.2.13/2.0.4: added the marker-count check at PREPARE time
    "instead of no error until execute"; it placed the check after the parse, with no memory discussion), 18813, 6855,
    2475 and unrelated hits.
  - `text ~ "large query string" AND text ~ "OutOfMemory"` → 16060 (Invalid; unrelated 3.11 OOM), 15214 (internode OOM
    handling).
  - `summary ~ "parser" AND text ~ "OOM"` → 0.
- **Verdict: `new`** for OC-409/410 (no issue about retaining every lexer error, or about parse-time memory of a long
  query); **`new`** for OC-278/285/140 (5598 introduced the post-parse check but never discussed its memory). Not known-fixed,
  so not a positive control. Not documented as by design.

## 2. Design solution (stage 1; frozen)

### 2.1 Mechanism (direction: **unprotected accumulation**; technique note: [`combo-playbook.md`](../../../combo-playbook.md) for multiplicity → budget, otherwise none applies)

Path of one QUERY request (protocol v4, pinned source):

1. **Admission.** The v4 envelope decoder discards frames whose total length exceeds `native_transport_max_frame_size`
   (16 MiB; `Envelope.java:197`, `:425-437`, check `totalLength > MAX_TOTAL_LENGTH`). The request is then charged its
   **body bytes** against the per-IP and global in-flight reserves (`PreV5Handlers.java:151-186`; default non-throwing
   mode: over the limit the bytes are force-allocated and the connection paused, `:178-186`). Defaults:
   `native_transport_max_request_data_in_flight` = heap/10, `…_per_ip` = heap/40 (`DatabaseDescriptor.java:649-657`).
   (`native_transport_max_message_size`, derived min(`max_mutation_size` 16 MiB, heap/10, heap/40) at `:903-905`,
   `:3237-3245`, is enforced on the v5 path, `CQLMessageHandler.java:551`; on v4 the frame size is the size bound.)
2. **Decode.** `QueryMessage.codec.decode` reads the query with `CBUtil.readLongString` (`QueryMessage.java:50`,
   `CBUtil.java:196-201`) into a 16 MiB Latin-1 `String`.
3. **Parse.** `QueryMessage.execute` → `QueryProcessor.parse` (`QueryProcessor.java:345-348`) → `getStatement`
   (`:893-897`) → `parseStatement` (`:923-926`) → `CQLFragmentParser.parseAnyUnhandled` (`CQLFragmentParser.java:63-83`):
   `new ErrorCollector(input)` (`:66`), `new ANTLRStringStream(input)` (`:67`; a `char[]` copy, 32 MiB), `CqlLexer`
   with the collector as listener (`:68-69`), `CommonTokenStream` (`:71`), `CqlParser` (`:72-73`), `parser.query()`
   (`:76`), and **only then** `errorCollector.throwFirstSyntaxError()` (`:80`).
4. **Per-character error.** The first `LT(1)` pulls `CqlLexer.nextToken()` (`Cql.g` `@lexer::members`, which calls
   `super.nextToken()`). ANTLR 3.5.2 `org.antlr.runtime.Lexer.nextToken` loops: `mTokens()`; on a
   `RecognitionException` it calls `reportError(re)` and `recover(re)` and goes round again (`javap -c` of the shipped
   jar, offsets 158–166). `Lexer.reportError` is `displayRecognitionError(getTokenNames(), e)` with **no** `errorRecovery`
   suppression (offsets 0–9), and `Lexer.recover` is `input.consume()` (one character). No lexer rule matches `#`
   (`grep '#' src/antlr/Lexer.g` is empty), so every `#` raises a `NoViableAltException` and is reported. `Cql.g`'s
   lexer `displayRecognitionError` forwards each report to every listener (`Cql.g` lexer members; same code in
   `Lexer.g:51-55`).
5. **Retention.** `ErrorCollector.syntaxError(BaseRecognizer, String[], RecognitionException)` (`ErrorCollector.java:69-82`)
   builds `getErrorHeader(e) + ' ' + getErrorMessage(e, tokenNames)` = `line 1:<pos> no viable alternative at character
   '#'` (46 + digits of `<pos>` characters; ANTLR `BaseRecognizer.getErrorHeader`, `Lexer.getErrorMessage`) and
   `errorMsgs.add(builder.toString())` (`:81`) into `private final LinkedList<String> errorMsgs` (`:52`). Nothing bounds the
   list; `throwFirstSyntaxError` (`:98-102`) reads only `errorMsgs.getFirst()`. The whole run of `#` is consumed inside one
   `nextToken()` call, so all messages are live together; the list is released only when `parseAnyUnhandled` throws.
6. **Response.** A `SyntaxException` (`0x2000`) with the first message, `line 1:0 no viable alternative at character '#'`.

**Classification (protocol "Unprotected results"):** no capacity control applies to `errorMsgs`; the only bound is
implicit (query length × ≈ 120 B, times concurrent requests) → **unprotected accumulation**, not a bypass: the in-flight
control does not claim to cover parse memory (its contract is wire bytes, and it holds K ≤ C throughout). The request is a
valid v4 frame inside every documented size limit, and CQL defines the response to invalid text (a syntax error, which the
node also returns for this input); no documented limit on query length exists besides the frame/message size. The excess
is the system's own retention of diagnostics it never reports. Interpretation: **suspected implementation defect**
(retaining every message when only the first is used), not documented as by design.

**Arm B (supporting, OC-278/285):** a PREPARE of `SELECT v FROM u6.t WHERE k IN (?,?,…,?)` with ≈ 8.39 M markers runs
`QueryProcessor.prepare` (`:728`) → `parseAndPrepare` (`:754` → `:441-471`: `parseStatement`, `raw.prepare`, `validate`,
`measurePstmnt` = `ObjectSizes.measureDeep` at `:469`, `:947-949`) and only then the marker check (`:757-759`). During the
parse the `CommonTokenStream` buffers every token (≈ 16.8 M `CommonToken`, `?` and `,` each a token), next to the
`Marker.Raw` list; during prepare the per-marker specifications and jamm's visited set.

### 2.2 Protection map

| Domain | Allocation and owner (release) | Counter K / contract C at 2 GiB | Scope, multiplicity | At the limit | Covers the claimed memory? |
|---|---|---|---|---|---|
| v4 frame size | inbound cumulation `ByteBuf` (direct, Netty pool), released after the response | frame total length / `native_transport_max_frame_size` 16,777,216 B (`Envelope.java:197`, `:427`) | per frame | longer frames discarded, `ProtocolException` | wire bytes only |
| Native in-flight reserves | charge of `header.bodySizeInBytes` per request, released at response | `RequestsSize` (global) / heap/10 = 214,748,364 B; per IP heap/40 = 53,687,091 B (`DatabaseDescriptor.java:649-657`) | per node / per client IP; N × 16,777,207 B | default mode: force-allocate, pause the connection (`PreV5Handlers.java:178-186`) | **wire bytes only**; N = 2 uses 33.6 MB of 53.7 MB per IP (no pause) |
| Request concurrency | `Native-Transport-Requests` SEP pool | threads / `native_transport_max_threads` 128 (`Config.java:283`) | per node | queued | count, not bytes; N ≤ 12 ≪ 128 |
| Query `String` and lexer `char[]` | `QueryMessage.query` 16 MiB `byte[]` (Latin-1), `ANTLRStringStream.data` 32 MiB `char[]`; released with the request | none | per request | — | uncovered, but ≈ 3 × K (part of the per-request constant, ≈ 48 MiB) |
| **`ErrorCollector.errorMsgs`** (claimed holder) | `LinkedList<String>` per parse (`ErrorCollector.java:52`, add at `:81`, `:90`); one `LinkedList$Node` 24 B + `String` 24 B + `byte[46+d]` 64–72 B per lexer error; released when the parse throws (`CQLFragmentParser.java:80`) | **none** | per request; one message per unlexable character (≈ 16.8 M per 16 MiB request); N requests in parallel | none | **no control** (unprotected accumulation) |
| Transient error garbage | `NoViableAltException` + stack trace, `StringBuilder`, header/message strings per error | none | per error, dead after `syntaxError` returns | — | GC-reclaimable; not claimed |
| Prepared cache (`prepared_statements_cache_size`) | `QueryProcessor.preparedStatements` | weight / `auto` = max(10 MiB, heap/256) | — | evict / refuse | not on the QUERY path; arm B is rejected by the marker check before storing |
| Guardrails | — | — | — | skipped for superusers (`AllowAllAuthenticator` default) | none bounds query length |
| Budgets | Java heap (`-Xmx`); direct (`MaxDirectMemorySize`, auto) | — | per process | heap OOM; direct OOM | the holder is heap |

Arm B rows (supporting): `CommonTokenStream`/`BufferedTokenStream.tokens` (`ArrayList<CommonToken>`, ≈ 48 B + 4 B slot
per token, no counter, released when the parse returns); `Marker.Raw` list and per-marker bind specifications (no counter;
stage 4: 43 B per marker retained in the prepared statement); jamm visited set during `measureDeep` (no counter); the
65535-marker check (count, after all of these exist).

### 2.3 Configuration and budget audit

- **Build:** copy the existing `ms0604:/mydata/s4/cassandra-base` (Cassandra 5.0.9, `git describe --tags` =
  `cassandra-5.0.9`, clean, `build/apache-cassandra-5.0.9-SNAPSHOT.jar`, `lib/antlr-runtime-3.5.2.jar`,
  `lib/jamm-0.4.0.jar`) with `cp -a` to the work directory (`<W>/cassandra`); never touch the shared tree. Intervention
  build: a second copy `<W>/cassandra-iv` with the one-file patch of §2.8 (record `git diff`). Record per run `md5sum` of
  `conf/cassandra.yaml`, `conf/jvm11-server.options`, `conf/cassandra-env.sh`, `conf/jvm-server.options` (expected the
  shipped files B14 recorded: `714ee9bf58b3bc1710377ac16bcbba03`, `fbad82a853f1b85aea0fa5ea34b6d1bf`,
  `8be0588e87c594a03360751b1dbf4fbf`; record `jvm-server.options` fresh).
- **Configuration: the shipped `conf/` unchanged in every arm** (single node, `rpc_address: localhost`, port 9042,
  `AllowAllAuthenticator`, `native_transport_allow_older_protocols: true`). Every constraint of §2.2 at its shipped
  default (V6): `native_transport_max_frame_size` 16 MiB, `native_transport_max_request_data_in_flight` heap/10,
  `…_per_ip` heap/40, `native_transport_max_message_size` derived (16 MiB at heaps ≥ 640 MiB), `max_mutation_size`
  derived 16 MiB (`commitlog_segment_size` 32 MiB / 2, `DatabaseDescriptor.java:898-899`), `native_transport_max_threads`
  128, `native_transport_timeout` 12 s, `native_transport_rate_limiting_enabled` false, connection limits −1,
  `prepared_statements_cache_size` auto. The intervention arm differs only by the build (diagnostic patch, §2.8).
- **Resolved values** (`Runtime.maxMemory()` = `-Xmx` under G1): 2 GiB → global 214,748,364 B, per IP 53,687,091 B;
  4 GiB → 429,496,729 / 107,374,182; 8 GiB → 858,993,459 / 214,748,364; 16 GiB → 1,717,986,918 / 429,496,729. Read them
  from JMX `StorageService` (`NativeTransportMaxConcurrentRequestsInBytes`, `…PerIp`) once per budget (B14 A3: the
  `system.log` config line prints them as `null`).
- **Environment (not capacity):** `MAX_HEAP_SIZE=<heap>`, `HEAP_NEWSIZE` unset (G1) ⇒ `-Xms = -Xmx`;
  `CASSANDRA_HEAPDUMP_DIR=<run dir>`; `systemd-run --user --scope -p MemorySwapMax=0` (swap 0; **no `MemoryMax`**, no
  container budget); `ulimit -n 100000`; shipped G1 (`G1HeapRegionSize=16m`, `MaxGCPauseMillis=300`), shipped GC log
  (`cassandra-env.sh:83` → `logs/gc.log`), shipped `-XX:+HeapDumpOnOutOfMemoryError` (`jvm-server.options:120`) and
  `-XX:OnOutOfMemoryError="kill -9 %p"` (`cassandra-env.sh:209`), `-Xss256k`. **Only for the optional 16 GiB run**:
  `JVM_EXTRA_OPTS=-XX:-HeapDumpOnOutOfMemoryError` (a ≈ 20 GB dump does not fit the disk; affects only what happens
  after the OOM; disclosed as an environment deviation).
- **Node claimed (V7):** `ms0604` (Utah m400, **aarch64**, 8 cores, MemTotal 65,791,808 kB, swap 8 GiB present, Ubuntu
  22.04, OpenJDK 11.0.33, Python 3.10.12; `/mydata` 39 GiB with **30 GiB free**; `/dev/shm` 32 GiB; checked read-only
  2026-11-18 13:42 ET: no Java process running, load 0.08; other folders `/mydata/s2r2`, `/mydata/u1r2` present and **not
  to be touched**; `/mydata/s4` holds only `cassandra-base`). `cassandra-env.sh` would resolve, for this node, heap =
  31,744 MiB (G1 ⇒ `heap_limit` 31,744 < ½ RAM 32,124 MiB, `cassandra-env.sh:51-68`) and `MaxDirectMemorySize` =
  15,872 MiB; with a hand-set heap the direct limit stays 15,872 MiB (`:139-158`; B14 measured 16,642,998,272 B).
  **Budgets:** heap **2 GiB** (ideal) for the V-runs; upward search 4 and 8 GiB (16 GiB optional); all ≥ 512 MiB ⇒ V7
  met without per-case review (standing rule 2026-11-11). Direct: auto. No container limit is a budget ⇒ no owner review
  needed. ARM: never pool these runs with x86 runs.

### 2.4 Ceiling arithmetic

**Payload H (test, OC-409/410).** QUERY (opcode `0x07`) with query text = `#` × **L = 16,777,200**; v4 body = 4 + L +
2 (consistency ONE) + 1 (flags 0) = **16,777,207 B**; frame = 9 + body = **16,777,216 B** = `MAX_TOTAL_LENGTH` (accepted:
the check is `>`). K per request = 16,777,207 B.

- Errors per request E = L (one per `#`) + 1 parser error at EOF. Message length 46 + d, d = digits of the position
  (0 … L−1): d ≤ 2 for 100 positions (`byte[]` 64 B), d ≥ 3 for the rest (`byte[49..54]` → 72 B). Per error: `byte[]` 72 +
  `String` 24 (JDK 11: header 12, `value` 4, `hash` 4, `coder` 1 → 24) + `LinkedList$Node` 24 (header 12 + 3 refs) =
  **120 B** (compressed oops, heaps < 32 GiB).
- **U_req (full parse) = 16,777,200 × 120 B = 2,013,264,000 B = 1,920 MiB**, plus the query `String` 16 MiB and the
  `char[]` 32 MiB (in G1 16 MiB regions these humongous objects occupy 2 + 3 regions = 80 MiB) ⇒ **≈ 2,000 MiB per
  request at the end of its lex**, U/K ≈ 125. Error band for predictions: 110–135 B per error (alignment and JDK
  details), i.e. 1.76–2.11 GiB per full request.
- Lex progress is linear in time (one message per character): U_req(t) ≈ 120 B × t / τ, τ = time per character (unknown
  on the m400; S0 measures it; estimate 2–10 µs ⇒ T_lex(16 MiB) ≈ 35–170 s).
- **Baseline:** idle 5.0.9 at 2 GiB on the m400: 33 MiB after Full GC (B14 S0); use 30–150 MiB.

| Heap | C global / requests admitted | C per IP / admitted from one IP | N (one client IP) | K = N × 16.8 MB | Demand at full lex (N × 2.0 GiB) | Predicted endpoint |
|---|---|---|---|---|---|---|
| 2 GiB | 214.7 MB / 12 | 53.7 MB / 3 | **1** (S1, diagnostic) | 16.8 MB | 1.95–2.06 GiB + baseline | **marginal**: OOM near the end of the lex or survive (≤ 2 % margin either way) |
| 2 GiB | 214.7 MB / 12 | 53.7 MB / 3 | **2** (T2) | 33.6 MB (0.16 C, 0.63 C_IP) | 3.9 GiB | **heap OOM** at ≈ 50 % of the lex (both requests in parallel) |
| 4 GiB | 429.5 MB / 25 | 107.4 MB / 6 | 3 (T4) | 50.3 MB | 5.9 GiB | heap OOM at ≈ 67 % |
| 8 GiB | 859.0 MB / 51 | 214.7 MB / 12 | 6 (T8) | 100.7 MB | 11.7 GiB | heap OOM at ≈ 67 % |
| 16 GiB (optional) | 1,718.0 MB / 102 | 429.5 MB / 25 | 12 (T16) | 201.3 MB | 23.4 GiB | heap OOM at ≈ 67 %, or Full-GC service loss first |
| 31 GiB (node auto, not run) | 3,328.6 MB / 198 | 832 MB / 49 | ≥ 17 needed | — | — | reachable by arithmetic (17 ≪ 49 from one IP); not run (time) |
| 2 GiB, control C | as T2 | as T2 | 2 | 33.6 MB | ≤ 2 × (48 MiB + one message) ≈ 0.1 GiB | survive (≥ 90 % margin) |
| 2 GiB, intervention I | as T2 | as T2 | 2 | 33.6 MB | ≤ 2 × 48 MiB + transient garbage | survive |

Σ contract capacities that cover this memory: **none** (the in-flight reserves cover only K, which stays ≤ 0.2 C
globally and ≤ 0.63 C per IP; the per-request demand is ≈ 125 × K). At every heap H, N = ⌈1.5 × H / 2 GiB⌉ requests from
one client IP are inside both in-flight limits and the 128 threads, so the endpoint is arithmetically reachable at any
budget; the search is limited by CPU time and dump disk. Direct: frames ≈ N × 16–32 MiB ≪ 15,872 MiB.

**Payload M (arm B, supporting).** PREPARE (opcode `0x09`, v4 body = `[long string]` only) of
`SELECT v FROM u6.t WHERE k IN (` (32 chars) + `?,` × (M − 1) + `?)`, **M = 8,388,585** (query 16,777,202 B, body
16,777,206 B, frame 16,777,215 B; the harness computes M = ⌊(16,777,203 − 32) / 2⌋ and prints the sizes). Tokens ≈
2M ≈ 16.78 M `CommonToken` × (48 B + 4 B list slot) ≈ 0.87 GB, + list growth copy (transient ≤ 0.1 GB) + `Marker.Raw`
and IN list ≈ 0.2–0.3 GB at the parse peak; after the parse the tokens die and prepare + `measureDeep` hold ≈ 43 B × M
≈ 0.36 GB + the visited set ≈ 0.1–0.3 GB. **Peak per request ≈ 1.0–1.3 GB (estimate, uncertain ± 40 %)**; N = 3
(50.3 MB, inside the 53.7 MB per-IP limit) ⇒ 3.0–3.9 GB at 2 GiB ⇒ OOM predicted, lower confidence than arm A.

### 2.5 Workload and environment

- **Node:** `ms0604` only (victim and client on the same node; the client is outside the measured scope, its CPU is
  recorded). Work dir **`<W>` = `/mydata/s4/u6-w4/`** (or the fresh directory the stage-2 task assigns; a dated
  amendment, environment only): `cassandra/`, `cassandra-iv/`, `harness/`, `runs/<run-id>/`. Before anything:
  `ps -eo pid,cmd | grep '[C]assandraDaemon'` and `ss -ltn | grep -E ':(7000|7199|9042) '` must be empty (if another
  agent's node runs there, stop and report; do not share the node). Do not touch `/mydata/s2r2`, `/mydata/u1r2`,
  `/mydata/s4/cassandra-base` (read only, copy from). Linger: if `loginctl enable-linger` is refused, drive each series
  from one long-lived `ssh` session (B14 A2).
- **Intervention build** (`harness/build-iv.sh`, run in the background while the harness is written): `cp -a
  <W>/cassandra <W>/cassandra-iv`; `git apply harness/iv.patch` (§2.8); `rm -f
  build/classes/main/org/apache/cassandra/cql3/ErrorCollector*.class`; `ant jar` (≈ 5–6 min on the m400, B11); check
  `javap -p -c -classpath build/apache-cassandra-5.0.9-SNAPSHOT.jar org.apache.cassandra.cql3.ErrorCollector | grep -c
  isEmpty` = base count + 2. Fallback if `ant` fails: `javac -cp 'build/apache-cassandra-5.0.9-SNAPSHOT.jar:lib/*' -d
  <tmp> src/java/org/apache/cassandra/cql3/ErrorCollector.java` and `jar uf` the class into the copy's jar (record which
  route was used).
- **Harness** (`harness/` in this folder, synced to `<W>/harness/`; Python 3 stdlib only):
  - `client.py` — raw CQL **protocol v4** client adapted from B11
    (`../ExecuteMessage_literal_1000--traced-render-outside-inflight/harness/client.py`: frame I/O, STARTUP
    `{"CQL_VERSION":"3.0.0"}`). **All connections from one source address (127.0.0.1)** to `127.0.0.1:9042` (one client
    IP; N × K stays inside the per-IP limit at every budget, so no connection is paused). Per connection: STARTUP →
    closed loop with **one request outstanding**: send the arm's frame (built once per process as `bytes`), wait for the
    response, record it, repeat until the hold ends. Socket timeout = hold + 120 s. Arms (`--payload`):
    - `H` (test, also intervention): QUERY of `#` × L, L = 16,777,200 (`--len` overrides, e.g. 1,048,576 for S0).
    - `C` (matched control): QUERY of `-- ` + `#` × (L − 4) + `\n` — **the same L bytes, the same characters, the same
      frame size, K and path**; the text is one `COMMENT` token (`Lexer.g:394-396`, hidden channel), so the lexer walks
      every character without an error and the parser reports one error at EOF.
    - `M` (arm B): PREPARE of payload M (§2.4); `CM` (arm B control): PREPARE of `-- ` + `#` × (L_M − 4) + `\n`, L_M =
      16,777,202.
    - `--ddl`: `CREATE KEYSPACE IF NOT EXISTS u6 WITH replication = {'class':'SimpleStrategy','replication_factor':1}`;
      `CREATE TABLE IF NOT EXISTS u6.t (k int PRIMARY KEY, v int)` (arm B and S0 only; arm A needs no schema).
  - Logs: `completions.txt` (`t_ms conn latency_ms opcode code first-120-chars-of-message`); `client.txt` per second
    (`t_ms open established outstanding completed errors K_client`, K_client = outstanding × body).
  - `run.sh <run-id> <build: base|iv> <heap> <payload> <N> <hold-s>` adapted from B14's `run.sh`: preflight (no daemon,
    ports free, `df -BG /mydata` avail ≥ 1.3 × heap + 4 GiB, else skip the run and record) → wipe the tree's `data/`,
    `logs/` → start `( ulimit -n 100000; MAX_HEAP_SIZE=<heap> CASSANDRA_HEAPDUMP_DIR=<run dir> systemd-run --user --scope
    -p MemorySwapMax=0 --unit=u6-<run-id> -- <tree>/bin/cassandra -f > <run dir>/stdout.txt 2>&1 < /dev/null & )` with
    `setsid nohup` → wait for `Starting listening for CQL clients` (≤ 300 s, bounded background poll, never a foreground
    `sleep`) → `jcmd <pid> VM.flags` → (`--ddl` if needed) → 20 s idle with monitors (baseline) → client → stop at the
    endpoint (daemon gone and `java.lang.OutOfMemoryError` in `stdout.txt`) or at hold end → stop the client, `kill
    <pid>` (`-9` after 60 s; but if `Dumping heap to` is in `stdout.txt` without `Heap dump file created`, wait for it up
    to 240 s first) → copy `system.log`, `gc.log*`, stdout, client and monitor logs to the run dir → `summarize.py`.
    Match the daemon by `java` + working directory, kill by PID; call scripts with `bash` (lost execute bits).
  - `monitor.sh`, `summarize.py`, dump tools: §2.6.
- **Runs and order** (one node lifetime per run; shipped conf; one run at a time):

| Run | Build | Heap | Payload | N | Hold after last send | Purpose |
|---|---|---|---|---|---|---|
| `S0` shakedown (not a reading) | base, then iv | 2 GiB | H, C, M at `--len 1048576` (M ≈ 524,272 markers), then iv H | 1 | each request ×2 sequential | reachability: H → `0x2000` `line 1:0 no viable alternative at character '#'`; C → one `0x2000` error at EOF; M → `0x2200 Too many markers(?). 524272 markers exceed …`; iv H → the same first message as base H. Measure τ = latency(H) / L and τ_iv; one `jmap -histo:live` at idle (baseline counts of `LinkedList$Node`, `String`, `byte[]`); instrument check (GC log, JMX, `Thread.print` shows an NTR thread in `CqlLexer`/`ErrorCollector` during an H request). Compute T_lex = 16 × latency(H, 1 MiB) |
| `S1` (diagnostic) | base | 2 GiB | H | 1 | max(300 s, 1.5 × T_lex + 60 s) | component alone: does one request exhaust 2 GiB? (marginal by §2.4; either outcome is recorded, not a V-reading) |
| `T2-1..3` test | base | 2 GiB | H | 2 | max(300 s, 1.5 × T_lex + 60 s) | V1 |
| `C2-1..3` control | base | 2 GiB | C | 2 | max(240 s, 1.5 × T_lex + 60 s) | V2 (matched payload) |
| `I2-1..3` intervention | iv | 2 GiB | H | 2 | max(240 s, 1.5 × T_lex_iv + 60 s), and ≥ 1 response per connection | V4 |
| `T4-1` | base | 4 GiB | H | 3 | max(300 s, 2 × T_lex + 60 s) | budget search |
| `T8-1` | base | 8 GiB | H | 6 | max(360 s, 2.5 × T_lex + 60 s) | budget search |
| `B2-1` (→ `-2`, `-3`) | base | 2 GiB | M | 3 | max(300 s, 3 × latency(M, 1 MiB) × 16 + 60 s) | supporting arm B (OC-278/285) |
| `CB2-1` | base | 2 GiB | CM | 3 | 240 s | arm B matched control (one run, if time) |
| `T16-1` (optional) | base | 16 GiB | H | 12 | max(420 s, 3 × T_lex + 60 s) | budget search; dumps off (§2.3) |

  **Order:** `S0`, `S1`, `T2-1`, `C2-1`, `I2-1`, `T2-2`, `C2-2`, `I2-2`, `T2-3`, `C2-3`, `I2-3`, `T4-1`, `T8-1`, `B2-1`,
  `CB2-1`, `B2-2`, `B2-3`, `T16-1`; then repeats of the largest failing budget (`T8-2`, `T8-3`) if time remains. If
  `T4-1` survives, skip `T8-1`/`T16-1` (largest failing budget 2 GiB; record the boundary). If `T8-1` survives, skip
  `T16-1`. Never drop a V-run (`T2`, `C2`, `I2`) for any other run.
- **Disk plan:** trees 2 × 0.47 GB; dumps ≈ 2.2–2.6 GB at 2 GiB, ≈ 5 GB at 4 GiB, ≈ 10 GB at 8 GiB (B14 sizes): analyse,
  record size + sha256 prefix + findings in the run dir, delete the `.hprof` before the next run (keep none at the end).
- **Time plan (America/New_York; the node clock is MST = ET − 2 h).** Stage 2 assumed to start at ≈ 14:20 (T0).
  T0 + 0:00–0:15 read, hash check, node check, copies, `build-iv.sh` in the background, harness; 0:15–0:30 `S0` (two
  node lifetimes); 0:30–0:38 `S1`; 0:38–1:55 nine V-runs (≈ 7–9 min each: start 60–90 s, baseline 20 s, load ≤ 3–5 min,
  dump 30–60 s, teardown and copy 60 s); 1:55–2:10 `T4-1`; 2:10–2:30 `T8-1` (10 GB dump ≈ 180 s); 2:30–3:00 arm B;
  then `T16-1` if ≥ 20 min remain before the hard stop. **Hard limits:** no run starts after **17:20 ET**; every process
  stopped and the node checked empty by **17:35**; §3, §4 and write-backs done by **18:00** (deadline 18:07). If stage 2
  starts later than 14:35, or `S0` gives T_lex > 6 min, drop in this order: `T16-1`, `CB2-1`, `B2-*`, `S1`, `T8-1`
  (record each drop); the V-runs and `T4-1` stay. Full histograms (`hprof-histo.py`) only where the plan says (§2.6), each
  capped at 15 min (record a cap hit).

### 2.6 Instruments

| What | How | Interval | Gives |
|---|---|---|---|
| Heap occupancy (U side, independent of K) | `logs/gc.log` (shipped Xlog): heap after each GC, `Pause Full` count and after-sizes, humongous regions, `To-space exhausted`; `jcmd <pid> GC.heap_info` (no forced GC) | every GC; 3 s | U(t) = heap after GC − baseline; growth rate vs τ |
| Holder at failure (V3, V5) | the shipped OOM dump: `hprof_oome_thread.py` (from B14's harness) on **every** failing run; `hprof-histo.py` (from B14, want-list changed) on the **first failing run per budget** (T2-1, T4-1; T8-1 only if ≤ 15 min): counts and shallow bytes of `java.util.LinkedList$Node`, `java.lang.String`, `byte[]` of length **47–54** (the messages; add a `--len-range 47 54` option), `org.apache.cassandra.cql3.ErrorCollector` (= parses in progress), `char[]` ≥ 1 M and `byte[]` ≥ 1 M (query copies), `org.antlr.runtime.NoViableAltException`, `org.antlr.runtime.CommonToken`; arm B adds `org.antlr.runtime.CommonToken`, `Object[]` ≥ 1 M, `org.apache.cassandra.cql3.Marker$Raw` / `AbstractMarker$Raw`, `ColumnSpecification` | at end | E_fail = `LinkedList$Node` − baseline; U_fail = E_fail × 120 B (and the measured shallow sum); share of the dump; U/K = U_fail / (n_held × 16,777,207) |
| K (server) | JMX `org.apache.cassandra.metrics:type=Client,name=RequestsSize`, `…name=PausedConnections`, `StorageService` resolved limits, by one long-lived `Jmx.java poll` (B14 harness) | 5 s | K ≤ C; paused connections (expected 0) |
| K (client) | `client.txt` | 1 s | outstanding × body |
| Parses in flight (actual concurrency) | `jcmd <pid> Thread.print`: count NTR threads with a `CqlLexer`/`org.antlr.runtime.Lexer.nextToken`/`ErrorCollector.syntaxError` frame (arm B: `CqlParser` or `ObjectSizes.measureDeep` or `parseAndPrepare` frames) | 10 s | n_held(t) |
| Process | `RssAnon` (`/proc/<pid>/status`); client `ps -o pcpu,rss`; `uptime` load | 3 s / 10 s | native growth; client and node CPU |
| Throughput | `completions.txt` | per response | responses by code, latency; for C and I the error text (must equal the base H first message for I) |
| Endpoint | `stdout.txt`: first `java.lang.OutOfMemoryError` line, `Dumping heap to …`, the `OnOutOfMemoryError` kill; `system.log` ERROR lines; process exit time | at end | endpoint type, t_OOM = (OOME time from the last GC-log line before the dump start) − time of the last send |
| Disk | `df -BM /mydata` | 10 s | guard: if avail < 5 GiB during a run, stop the client and record a deviation |

`monitor.sh` runs the same samplers in every arm (matched instrumentation); no forced GC and no live histogram during a
measured run (only in `S0`). `summarize.py` writes `summary.txt` per run: endpoint and t_OOM; n_held max and at the last
sample; K_server max and at the last good sample; max heap after GC and the last Full-GC after-sizes; GC STW share over
the last 60 s (count each GC id once across rotated `gc.log*` files — B14's note); responses by code and latency; max
RssAnon; client CPU; dump findings (size, sha256 prefix, OOME thread top frames, the histogram lines above).

### 2.7 Predicted response, outcome rows and stopping budget

**Predicted (before readings):**
- `S0`: H 1 MiB → `0x2000` with message `line 1:0 no viable alternative at character '#'`, latency = τ × 1,048,576 with
  τ in 2–10 µs (2–10 s); C 1 MiB → one `0x2000` message (at EOF), latency ≪ H; M 1 MiB → `0x2200 Too many markers(?).`;
  iv H → the same message as base H, latency within ± 30 % of base H.
- `S1`: marginal (OOM near the end of the lex, or a survive whose last Full GCs leave ≥ 1.9 GiB); either is recorded.
- `T2-*`: **heap OOM 3/3** (`java.lang.OutOfMemoryError: Java heap space`) within the hold, at t_OOM ≈ 0.4–0.7 × T_lex
  after the last send (plus Full-GC time); n_held = 2 at the last sample; K_server ≤ 33,554,414 B (≤ 0.16 of C global,
  ≤ 0.63 of C per IP), PausedConnections 0; dump: `LinkedList$Node` − baseline ≥ 13 M (≥ 1.5 GB of node + `String` +
  `byte[47..54]`), these three classes **≥ 60 %** of the dump's shallow bytes; `ErrorCollector` instances = 2 (+ idle
  ones); U/K at failure ≥ 40 (prediction ≈ 50–65 at N = 2, since each request is half-way). OOME thread: an NTR thread in
  `ErrorCollector.syntaxError` / `StringBuilder` / `NoViableAltException.<init>` under `Lexer.nextToken` (another thread
  that happens to allocate is acceptable if the histogram shows the holder).
- `C2-*`: survive 0/3 OOM over the hold; every response `0x2000` (one message); heap after GC peak ≤ 0.5 GiB (≤ 25 % of
  the heap); GC STW share < 90 %.
- `I2-*`: survive 0/3; responses `0x2000` with the same first message as base H; latency ≈ T_lex_iv; heap after GC peak
  ≤ 0.5 GiB; ≥ 1 response per connection.
- `T4-1`: OOM (n_held 3); `T8-1`: OOM (n_held 6), Full GCs ≈ 5–10 s each before it; `T16-1`: OOM or Full-GC service loss.
- `B2-*`: OOM (lower confidence) with `CommonToken` + the token list the largest holder if the OOM falls in the parse, or
  marker/specification classes if it falls in prepare/measure; a survive gives `0x2200 Too many markers(?). 8388585 …`
  and a measured per-request peak. `CB2-1`: survive.

| Row | Observation | Reading |
|---|---|---|
| O1 | T2 OOM ≥ 3/3 (V1); C2 0/3 (V2); I2 0/3 with responses (V4); U from GC log and dump vs K (V3); OOME thread / histogram show `errorMsgs` content ≥ 60 % (V5); shipped defaults (V6); 2 GiB heap (V7) | **true positive**: `verified-OOM · deployment`, unprotected accumulation (`ErrorCollector.errorMsgs`), largest failing budget from T4/T8/T16 with n/N |
| O2 | T2 ends in GC service loss (≥ 90 % STW over ≥ 60 s) without an OOM event by the hold end | `verified-gap · service-loss` at best → **retry** (raise N or the hold) |
| O3 | T2 OOM but the message classes < 60 % of the dump, or another holder is largest | attribution fails → **retry** (name the holder) |
| O4 | T2 survives 0/3 with n_held = 2 for the whole lex and the measured U_req per request (dump-free: heap after GC at the end of an S1 lex − baseline) × 2 + baseline < 2 GiB | **if** U/K measured < 50 and the same arithmetic fails at 4 GiB with N = 6 (still inside the per-IP limit): **false positive**; otherwise **retry** with a larger N |
| O5 | the lexer stops reporting after the first error (S0: heap after GC flat, `LinkedList$Node` count flat during an H request) | mechanism absent (source/runtime differs) → stop the arms; **false positive** if confirmed by the S0 histogram, else **retry** |
| O6 | C2 OOM (≥ 1/3) | the endpoint does not need the per-character messages → **retry** |
| O7 | I2 OOM (≥ 1/3), or I2 returns no response / a different first message | intervention fails or changes behaviour → V4 unmet → **retry** (or `(no intervention)` only if the patch was impossible, which it is not) |
| O8 | direct-buffer OOM or kernel kill first | competing endpoint → record → **retry** |
| O9 | frames rejected (`ProtocolException`, frame discarded), `0x1001 Overloaded`, node fails to start, or the request never starts lexing (`Thread.print` shows no lexer frame) | invalid run: fix the harness before readings (shakedown) or record as invalid |

**Stopping budget:** per run the hold of §2.5 (no run longer than its hold + start + dump + 2 min); one endpoint per run,
no escalation after an OOM; the whole stage within the time plan's hard limits; N never above the table value.

### 2.8 Controls and intervention

- **Matched control (V2), 3 runs:** arm C — the same opcode (QUERY), connections, N, heap, build, conf and instruments;
  the same number of wire bytes (16,777,200 query bytes, the same frame and K), the same characters (`#`), the same
  query `String` and `char[]` copies, and the lexer walks every character as in T; the only difference is that the
  characters are inside one comment token, so the lexer reports no error per character. Survival shows that the endpoint
  needs the per-character messages, not the wire volume, the query copies or the lexing work.
- **Causal intervention (V4), 3 runs:** arm I — the diagnostic build `cassandra-iv` with this one-file patch
  (`harness/iv.patch`; save the exact diff), payload H, everything else as T:

  ```diff
  --- a/src/java/org/apache/cassandra/cql3/ErrorCollector.java
  +++ b/src/java/org/apache/cassandra/cql3/ErrorCollector.java
  @@ public void syntaxError(BaseRecognizer recognizer, String[] tokenNames, RecognitionException e)
           if (recognizer instanceof Parser)
               appendQuerySnippet((Parser) recognizer, builder);
   
  -        errorMsgs.add(builder.toString());
  +        String m = builder.toString();
  +        if (errorMsgs.isEmpty()) // U6 intervention (diagnostic build only): keep only the message that is thrown
  +            errorMsgs.add(m);
       }
  @@ public void syntaxError(BaseRecognizer recognizer, String errorMsg)
       {
  -        errorMsgs.add(errorMsg);
  +        if (errorMsgs.isEmpty()) // U6 intervention: keep only the message that is thrown
  +            errorMsgs.add(errorMsg);
       }
  ```

  Every message is still built (the same allocation and CPU per character); only its retention is bounded to the one
  message `throwFirstSyntaxError` uses, so the client sees the same error. Survival with responses at a measured rate
  shows the OOM is caused by the retention of the messages. The original failure is reproduced on the unmodified build
  (T2).
- **Low multiplicity / component alone:** `S1` (N = 1) and `S0` (1 MiB) give one request's U(t) and the boundary.
- **Supporting arm B:** `B2-*` and `CB2-1` measure the OC-278/285 form (tokens and markers) under the same budget and
  client; no intervention is planned for it in this case.
- **V-table plan:** V1 `T2-1..3`; V2 `C2-1..3`; V3 U from the GC log and dump counts vs K from `RequestsSize` and
  `client.txt`; V4 `I2-1..3`; V5 OOME thread of every T2 run + `T2-1` histogram; V6 §2.3 (conf md5, resolved limits from
  JMX); V7 2 GiB heap, auto direct, no container limit; largest failing budget from `T4-1`/`T8-1`/`T16-1` with n/N.
- **Write-back rule (fixed now, applied by stage 2):** OC-409 and OC-410 get the case verdict (`true positive (U6)` /
  `false positive (U6)` / `retry (U6)`; OC-410 with the note "lexer part; parser-error path not tested"). OC-278 and
  OC-285 get `retry (U6)` whatever arm B shows (no control ×3 and no intervention here), with arm B's readings and "a
  dedicated case: PREPARE of ≈ 8.4 M markers, control ×3 (comment PREPARE of equal length), intervention (marker count
  bounded during the parse)" in the retry row; if arm B did not run, the same with "not run (time)". OC-140 gets
  `retry (U6)` with "literal form not tested; arm B readings apply only to the shared parse-and-measure part".

`sha256 of §1–§2 at freeze: 06f6f66bcaa23bbb1577ac1a7b38f50da149fcc7ab48a0128863b36ca853b7a5` · computed over the lines from `## 1. Candidate` through the line before this one (`awk '/^## 1\. Candidate/{f=1} /^.sha256 of §1–§2 at freeze/{f=0} f' <case file> | sha256sum`), frozen 2026-11-18 · amendments after the freeze: dated, with reason.

## 3. Runs (stage 2)

### 3.0 Resumption note (2026-11-18, 18:21 ET)

The first stage-2 session ran every arm of the frozen design (plus one diagnostic extension, D2-1) between 13:55 and
16:07 ET, then the owner suspended the wave before §3 and §4 were written; that session's leftover processes were stopped.
A fresh stage-2 session resumed at 18:21 ET: freeze hash re-checked (`06f6f66b…53b7a5`, matches); `ms0604` checked (no
`java`/client process, ports 7000/7199/9042 free, load 0.00, `/mydata` 29 GiB free); every run directory under
`ms0604:/mydata/s4/u6-w4/runs/` checked for completeness (driver `END …` and `done` lines, `stdout.txt`, `system.log`,
`gc.log*`, `jmx.csv`, `threads.txt`, `completions-*.txt`, `summary.txt`; failing runs also `dump.txt` + `oome-thread.txt`).
All 19 are complete except `T8-1`, which was aborted on purpose by the frozen skip rule (below). **Reused:** both builds
(`cassandra/`, `cassandra-iv/`, `logs/build-iv.log`), the harness (identical md5 to the node copy; added the missing
`harness/list-s0.txt`), all runs and their summaries. **Redone:** nothing (no arm was missing or incomplete; no new arm
was started). Added excerpt: `logs/D2-1/fullgc-progression.txt`. Node clock is MST (ET − 2 h); `system.log` is UTC.

### 3.1 Environment and configuration (as run)

- Node `ms0604` (Utah m400, aarch64, 8 cores, 62 GiB, kernel 5.15.0-191, swap 8 GiB present, `MemorySwapMax=0` per scope,
  no `MemoryMax`), OpenJDK 11.0.33, G1 (`G1HeapRegionSize=16m`, `ParallelGCThreads=8`), `-Xms = -Xmx` = 2G / 4G,
  **`MaxDirectMemorySize=15872M`** (resolved by `cassandra-env.sh`, from the JVM-arguments line).
- Builds: base `ms0604:/mydata/s4/u6-w4/cassandra` (jar md5 `a9b3ef8b…`, copy of `cassandra-base`), intervention
  `…/cassandra-iv` (jar md5 `5a5fa0d6…`; patch exactly §2.8, saved as `harness/iv.diff`; `ant jar` rc 0 in 36 s;
  `isEmpty` count base 1 → iv 3).
- Conf md5 every run (`logs/<run>/conf-md5.txt`): `cassandra.yaml 714ee9bf…`, `jvm11-server.options fbad82a8…`,
  `cassandra-env.sh 8be0588e…` (= shipped, as B14), `jvm-server.options 26a957bf…` (recorded fresh). Shipped conf in
  every arm (V6).
- Resolved limits from JMX: 2 GiB → global 214,748,364 B, per IP 53,687,091 B; 4 GiB → 429,496,729 / 107,374,182 B (as
  §2.3). Frame size 16 MiB, NTR threads 128.
- Harness: `harness/` (`run.sh`, `series.sh`, `client.py`, `monitor.sh`, `Jmx.java`, `threadcount.py`, `stw.py`,
  `summarize.py`, `hprof-histo.py`, `hprof_oome_thread.py`, run lists `list-s0.txt`, `list-main.txt`, `list-2.txt`,
  `list-3.txt`, `after-main.sh`). Full logs: `ms0604:/mydata/s4/u6-w4/runs/<run>/`; excerpts: `logs/<run>/`
  (summary, driver, gc-windows, client tail, completions head, JMX excerpt, threads, OOME thread/histogram/dump record);
  60-s STW windows of all runs: `logs/stw-all.txt`.

### 3.2 Runs and readings (times ET; "after-GC" = heap after GC from `gc.log`)

| Run | Build / heap / payload / N / hold | Endpoint | Readings |
|---|---|---|---|
| `S0` 13:57 | base / 2G / H, C, M at 1 MiB / 1 / 2× each | hold (shakedown) | H: `0x2000 line 1:0 no viable alternative at character '#'`, latency 11.58 / 11.49 s ⇒ **τ ≈ 11.0 µs per character**, T_lex(16 MiB) ≈ 184 s. C: `0x2000 line 0:-1 no viable alternative at input '<EOF>'`, 58 / 47 ms. M: `0x2200 Too many markers(?). 524272 markers exceed the allowed maximum of 65535`, 2.19 / 1.77 s. Thread dump during H shows the NTR thread in the lexer. PausedConnections 0. |
| `S0iv` 14:00 | iv / 2G / H 1 MiB / 1 | hold | same first message as base; latency 11.38 / 10.16 s (τ_iv ≈ base). |
| `S1` 14:03 | base / 2G / H / 1 / 336 s | hold, no OOM | after-GC rises to 1,915 MiB (29 Full GCs, 5–9 s each); max 60-s STW 91 %, ≥ 90 % in 2 windows spanning 63 s (marginal service loss); **0 responses in 339 s** (unloaded lex 184 s); K 16,777,207 B. |
| `T2-1` 14:11 | base / 2G / H / 2 / 336 s | **hold, no OOM; GC service loss** | 73 Full GCs, after-GC 2,009–2,017 MiB; ≥ 90 % STW from +204 s, 56 of 115 windows, span 193 s; max 101 %; 0 responses; n_held 2 throughout; K_server max 33,554,414 B (0.16 C, 0.63 C_IP), PausedConnections 0; direct 42 MiB; RssAnon 2,648 MiB. Killed (`-9`) at hold end + 60 s. |
| `C2-1` 14:19 | base / 2G / C / 2 / 336 s | hold | 2,301 responses, all `0x2000` (EOF), latency ≈ 0.3 s; after-GC max 257 MiB; max STW 0–1 %. |
| `I2-1` 14:26 | iv / 2G / H / 2 / 319 s | hold | 2 responses (1 per connection), `0x2000 line 1:0 no viable alternative at character '#'`, latency 176.5 / 177.2 s; after-GC max 307 MiB; 74 GCs, STW 0 %; n_held 2. |
| `T2-2` 14:33 | as T2-1 | **service loss, no OOM** | 78 Full GCs, after-GC 2,013–2,016 MiB; ≥ 90 % from +198 s, 66/124 windows, span 200 s; 0 responses; K 33,554,414 B; paused 0. |
| `C2-2` 14:41 | as C2-1 | hold | 2,300 responses `0x2000`; after-GC max 251 MiB; STW 0–1 %. |
| `I2-2` 14:48 | as I2-1 | hold | 2 responses (same message); after-GC max 313 MiB; STW 0 %. |
| `T2-3` 14:55 | as T2-1 | **service loss, no OOM** | 75 Full GCs, after-GC 2,009–2,016 MiB; ≥ 90 % from +200 s, 67/119 windows, span 196 s; 0 responses; K 33,554,414 B; paused 0. |
| `C2-3` 15:03 | as C2-1 | hold | 2,304 responses `0x2000`; after-GC max 254 MiB; STW 0–1 %. |
| `I2-3` 15:11 | as I2-1 | hold | 2 responses (same message); after-GC max 307 MiB; STW 0 %. |
| `T4-1` 15:18 | base / 4G / H / 3 / 428 s | **service loss, no OOM** | 61 Full GCs (3.4–7.0 s), after-GC 3,976–4,009 MiB; ≥ 90 % STW from +277 s, 47/104 windows, span 210 s; 0 responses in 430 s; n_held 3; K 50,331,621 B (0.12 C, 0.47 C_IP); paused 0; RssAnon 4,993 MiB. |
| `T8-1` 15:26 | base / 8G / H / 6 | **aborted during start, no client, no readings** | frozen rule §2.5: T4-1 survived ⇒ skip T8-1 / T16-1. |
| `B2-1` 15:28 | base / 2G / M (8,388,585 markers) / 3 / 300 s | **heap OOM** at +62.6 s (daemon `kill -9` by `OnOutOfMemoryError`; clients see connection reset) | OOME thread: `ArrayList.grow` ← `BufferedTokenStream.fetch` ← `CommonTokenStream.consume` ← `Cql_Parser.singleColumnInValues` (parse, before prepare and the marker check). Dump 2,868 MB (sha256 `8d298a12…`, deleted after analysis): `CommonToken` 24,776,649 = 1,486.6 MB (59 % of 2,517 MB shallow), `Object[]` ≥ 1 M elements 466 MB (token buffers), `AbstractMarker$Raw` 12,388,295 = 247.8 MB, `char[]` ≥ 1 M 201 MB; `ErrorCollector` 3. K 50,331,621 B (0.94 C_IP), paused 0. |
| `CB2-1` 15:33 | base / 2G / CM / 3 / 240 s | hold | 1,726 responses `0x2000` (EOF); after-GC max 529 MiB; STW ≤ 2 %. |
| `B2-2` 15:39 | as B2-1 | **heap OOM** +65.6 s | same OOME stack; dump 2,889 MB (`b121d190…`, deleted). |
| `B2-3` 15:42 | as B2-1 | **heap OOM** +64.6 s | same OOME stack; dump 2,873 MB (`66219c32…`, deleted). |
| `D2-1` 15:45 | base / 2G / H / 2 / **1,200 s** (diagnostic, see 3.3) | **service loss, no OOM** | 248 Full GCs; after-GC 2,016 MiB at uptime 484 s → 2,022 MiB at 1,298 s (**+0.44 MiB/min**; each Full GC frees one 16 MiB region: 2,038 → 2,022 MiB); ≥ 90 % STW in 416 of 466 windows, span 1,057 s; **0 responses in 1,203 s**. Non-live `jmap -histo` at 15:58 (≈ 12 min of load): `LinkedList$Node` 15,858,746 = 380.6 MB, `String` 15,945,075 = 382.7 MB, `byte[]` 15,947,961 = 1,191.7 MB, `char[]` 134.3 MB, `ErrorCollector` 2, `NoViableAltException` 2; total 2,116 MB ⇒ the three message classes ≈ 1,955 MB = **92 %**, ≈ 123 B per message, ≈ 7.93 M messages (47 % of 16.78 M characters) per request, **U/K ≈ 1,955 MB / 33.55 MB ≈ 58**. |

### 3.3 Deviations from the frozen design

- **D2-1 is outside the frozen run table.** The first stage-2 session added it after the T2 runs (driver tag `A6`),
  identical to T2 except the hold (1,200 s instead of 336 s) and one non-live `jmap -histo` at ≈ 12 min, but no dated
  amendment text was written into this file before its readings. It is recorded here as a **diagnostic** run (attribution
  of the holder in a non-failing T2 condition, and whether a longer hold ends in OOM); it is not counted as a V-run.
- T2 runs produced no dump (no OOM), so the planned `T2-1` histogram could not be taken; V3/V5 holder attribution comes
  from the D2-1 histogram (same build, conf, heap, payload and N) and the GC logs.
- Responses were not counted as "per connection ≥ 1" for T2 (0 by outcome). STW shares above 100 % in `stw-all.txt` are a
  window-edge artefact of `stw.py` (a pause straddling the window start counted in full); the ≥ 90 % criterion holds with
  wide margin in the middle windows (`logs/T2-*/gc-windows.txt`: 90–107 % from +210 s on).
- Order as designed; `T8-1`, `T16-1`, `T8-2/3` not run by the frozen skip rule; nothing else dropped.

## 4. Conclusion (stage 2)

**Verdict: retry.** Protocol status: **`verified-gap · service-loss · deployment`** (unprotected accumulation,
`ErrorCollector.errorMsgs`); outcome row **O2** of §2.7.

| | Evidence | Met? |
|---|---|---|
| V1 Repetition | T2-1..3: GC service loss 3/3 (≥ 90 % STW over 193 / 200 / 196 s), **OOM 0/3** | for service loss; not for OOM |
| V2 Matched control | C2-1..3 (same bytes, same frame/K, comment token): 0/3, STW ≤ 1 %, after-GC ≤ 257 MiB, ≈ 2,300 responses each | yes |
| V3 Measurement | U from `gc.log` (after-GC 2,009–2,017 MiB) and D2-1 histogram (15.86 M messages ≈ 1.95 GB, 92 % of heap) vs K = 33.55 MB server and client (0.16 C, 0.63 C_IP, paused 0) | yes |
| V4 Intervention | I2-1..3 (keep only the thrown message): 0/3, STW 0 %, after-GC ≤ 313 MiB, every connection answered with the same first message in 176–177 s | yes |
| V5 Initiating failure | service loss: `gc.log` windows (`logs/T2-*/gc-windows.txt`, `logs/stw-all.txt`); no OOM event exists | yes (service loss) |
| V6 Default constraints | shipped conf (md5 above), all §2.2 limits at defaults, resolved from JMX | yes |
| V7 Acceptable budget | 2 GiB heap (ideal), direct auto 15,872 MiB, no container limit; also 4 GiB (T4-1, 1/1 service loss) | yes |

**Reason.** Every element of the hypothesis was confirmed except the endpoint. The lexer reports every `#` and the
collector keeps every message (≈ 123 B each, U/K ≈ 58 at 12 min); no control covers it (K ≤ 0.63 of the per-IP limit,
no pause). But the growth does not end in `OutOfMemoryError`: once the retained messages fill the heap, G1 runs back-to-back Full GCs
(≈ 12 per minute, 2.5–5.8 s each) that each reclaim one 16 MiB region of transient garbage (exceptions, builders), the two
lexers advance only a few hundred characters per cycle, and retention grows ≈ 0.44 MiB/min (D2-1), so the JVM sits in ≥ 90 % stop-the-world
GC with zero responses for the whole hold (T2 338 s, T4-1 430 s, D2-1 1,203 s) instead of failing an allocation. By the
protocol this is a verified gap with service loss, which the playbook maps to **retry**. The frozen O4 rule for a false
positive does not apply (the holder demonstrably exceeds the budget). Arm B (OC-278/285, supporting) reached heap OOM 3/3
at 2 GiB in ≈ 64 s, OOME thread in `BufferedTokenStream.fetch` with `CommonToken` + token buffers + `Marker.Raw` ≈ 87 %
of the dump, and its single matched control survived; under the frozen write-back rule it stays `retry (U6)` (no control
×3, no intervention) and is a strong lead for its own case.

**What a better design should change.** (1) Make the OOM trigger an allocation the thrashing heap cannot serve: during the
T2 thrash (≥ +200 s), have a further client of the same IP (still inside the per-IP limit at N = 3: 50.3 of 53.7 MB) send
one more 16 MiB QUERY, whose decode needs a 16 MiB `byte[]` and a 32 MiB `char[]` (humongous, 1–3 contiguous free
regions) while only one region is free after Full GC — arm B shows this kind of large array growth fails at once; run
its matched control (the extra request against the C arm) and intervention the same way, 3× each. (2) Alternatively a
predefined long hold (≥ 60 min) at N = 2: by D2-1's rate, free space after Full GC drops below one region after ≈ 40–45
min of load (extrapolation, untested). (3) Search the budget with these triggers at 4 and 8 GiB. (4) Give arm B
(PREPARE of ≈ 8.4 M markers) its own case with control ×3 and an intervention (marker count bounded during the parse).

**Limits of attribution.** The holder histogram is from the diagnostic D2-1 (same condition, longer hold), not from a
T2 run; no dump of a T2 heap exists. Single node, aarch64; not pooled with x86 results.

**Left on the node:** `ms0604:/mydata/s4/u6-w4/` (`cassandra/` 499 MB, `cassandra-iv/` 474 MB, `harness/`, `runs/`
129 MB of logs; no `.hprof`); no process running.
