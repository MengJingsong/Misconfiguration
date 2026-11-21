# R15 (retry of U6) — ErrorCollector.errorMsgs: one more 16 MiB request during the lexer-message GC thrash needs humongous regions the full heap cannot give  <!-- file: cassandra/cases/ErrorCollector_errorMsgs--humongous-request-during-gc-thrash/ErrorCollector_errorMsgs--humongous-request-during-gc-thrash.md -->

| Field | Value |
|---|---|
| Case ID | `R15` (a new attempt at `U6`; README "ID prefixes") |
| From | retry-list row `U6` (from the OC-409 cluster: OC-409, OC-410; supporting OC-278, OC-285) |
| Phase-1 case files | [`no_constraint-istokenvalid-token_position--autonomous`](../../../../capacity-enforcement-exp/cassandra/stage3-ai-deep-read/cases/no_constraint-istokenvalid-token_position--autonomous.md) (OC-409, OC-410; no stage 4); [`max-unsigned-short-prepare-boundTerms--autonomous`](../../../../capacity-enforcement-exp/cassandra/stage3-ai-deep-read/cases/max-unsigned-short-prepare-boundTerms--autonomous.md) (OC-278, OC-285; stage 4: [results](../../../../capacity-enforcement-exp/cassandra/stage4-runtime-verification/results/max-unsigned-short-prepare-boundTerms--autonomous.md)) |
| System / pinned source | Cassandra 5.0.9 (`systems/cassandra/source/`, `build.xml` `base.version` 5.0.9); built tree `pc82:/mydata/s4/cassandra-base` (**x86_64**); OpenJDK 11.0.33; ANTLR 3.5.2 |
| Stage 1 (design) | OOM-agent stage-1 session, 2026-11-20 10:30–11:30 America/New_York |
| Stage 2 (verify) | fresh session, 2026-11-20 10:41–13:20 ET on `pc82` (all runs done by 13:17 ET); interrupted by the usage limit, resumed 21:26 ET for §3–§4 |
| Verdict | **retry** (condition A: `verified-gap · service-loss · deployment` at 2 GiB, heap OOM 3/3 only at 4 GiB without control/intervention there); **true positive** (condition B: `verified-OOM · deployment`) |

## Summary

- **Conclusion (stage 2, 2026-11-20):** condition **A — retry.** At 2 GiB the two `#` QUERYs again end in GC service
  loss (≥ 90 % STW, 1 free region), but the one-more-request trigger did not end in OOM within the frozen 180-s hold
  (0/3): under the thrash the trigger frame takes ≈ 220 s just to be received. A 1,800-s diagnostic hold (`D1`) did end
  in heap OOM 220 s after the trigger, in the trigger's decode buffer, with lexer messages 90 % of the dump; at 4 GiB the
  same OOM came 3/3 within 13 s of the trigger (messages 93 % of the dump); controls and intervention (2 GiB) survived
  3/3. No single condition has repetition, control and intervention together. Condition **B — true positive**
  (`verified-OOM · deployment`): PREPARE of 8.39 M markers × 3 → heap OOM 3/3 at 2 GiB in ≤ 9 s, also at 4 and 8 GiB;
  comment control and in-parse marker bound survive 3/3.
- **Root cause:** A — `ErrorCollector.errorMsgs` keeps one message per bad character (≈ 138 B each, no bound; only the
  first is ever used); the in-flight limits count only the 16-MiB wire bytes (U/K ≈ 64–88). B — the parser buffers every
  token and marker of a PREPARE before the 65,535-marker check, which runs only after the parse (U/K ≈ 43).
- **Hypothesis under test (stage 1):** U6 showed that two 16 MiB QUERYs of `#` characters fill a 2 GiB heap with
  retained lexer messages (`ErrorCollector.errorMsgs`, ≈ 123 B per character, 92 % of the heap) and drive the node into
  ≥ 90 % stop-the-world GC, but never into `OutOfMemoryError`: the lexers only allocate small objects, and each Full GC
  frees about one 16 MiB region of transient garbage, which is enough for them. **Any request that needs a humongous
  array** cannot be served in that state: the decode of one more ordinary 16 MiB QUERY from the same client (still inside
  the per-IP in-flight limit) needs a 2-region `char[]` (thread-local decode buffer), a 1-region `byte[]` (the query
  `String`) and another 2-region `char[]` (`ANTLRStringStream`), while ≤ 2 whole regions are free after Full GC. G1 then
  throws `OutOfMemoryError: Java heap space` and the shipped `-XX:OnOutOfMemoryError` kills the node. Predicted: heap OOM
  3/3 at 2 GiB with every capacity at its default; the comment control and the keep-first-message intervention, with the
  identical trigger at the identical time, survive 3/3; the budget search runs 4, 8, 16 GiB (and the node's own 31 GiB).
- **Condition B (separately concluded, OC-278/285):** a PREPARE of 8.39 M bind markers buffers ≈ 16.8 M ANTLR tokens
  before the 65,535-marker check; U6 saw heap OOM 3/3 at 2 GiB with one control. Here it gets control ×3 (comment PREPARE
  of equal length) and an intervention ×3 (the same 65,535 bound applied during the parse), then a budget search.

## 1. Candidate

### 1.1 The retry row (quoted from `phase2-retry-list.md`)

| Case | Verdict date | Why retry (what was shown, what was missing) | What a better design should change | Status |
|---|---|---|---|---|
| [U6](../ErrorCollector_errorMsgs--one-message-per-bad-character/ErrorCollector_errorMsgs--one-message-per-bad-character.md) (from OC-409 cluster) | 2026-11-18 | 16 MiB `#` QUERYs: `ErrorCollector.errorMsgs` holds ≈ 123 B per character (92 % of heap), comment control and keep-first-message intervention 0/3, but the endpoint is GC service loss 3/3 (≥ 90 % STW ≈ 200 s), OOM 0/3, also at 4 GiB and over a 20-min hold (`verified-gap · service-loss`). Supporting arm B (PREPARE of 8.4 M markers, OC-278/285) OOM 3/3 at 2 GiB with one control | Add a trigger the thrashing heap cannot serve (a third 16 MiB QUERY from the same IP during the thrash, humongous decode buffers), control and intervention ×3, then a budget search; or a pre-declared ≥ 60 min hold. Give arm B (PREPARE markers) its own case with control ×3 and a marker-count intervention | picked again: R15 (2026-11-20) |

### 1.2 The earlier case and its verdict

[`U6`](../ErrorCollector_errorMsgs--one-message-per-bad-character/ErrorCollector_errorMsgs--one-message-per-bad-character.md)
(stage 2 on `ms0604`, **aarch64**, 8 cores, 2026-11-18): verdict **retry**, protocol status `verified-gap · service-loss
· deployment`. The readings this design builds on (U6 §3.2, §4):

- Mechanism confirmed. S0: a 1 MiB `#` QUERY returns `0x2000 line 1:0 no viable alternative at character '#'` after
  11.5 s (τ ≈ 11.0 µs per character on the m400, T_lex(16 MiB) ≈ 184 s); the comment payload returns one EOF error in
  ≈ 50 ms.
- T2-1..3 (2 GiB, two 16 MiB `#` QUERYs from one IP, shipped conf): 73–78 Full GCs, heap after GC **2,009–2,017 MiB of
  2,048**, ≥ 90 % STW from +198–204 s over 193–200 s, 0 responses, **OOM 0/3**. K 33,554,414 B (0.16 C global, 0.63 C per
  IP), no paused connection. T4-1 (4 GiB, N = 3): after GC 3,976–4,009 MiB of 4,096 (87–120 MiB free), ≥ 90 % STW,
  no OOM in 430 s. D2-1 (2 GiB, 1,200 s hold): after GC 2,016 → 2,022 MiB (+0.44 MiB/min), each Full GC frees one 16 MiB
  region (2,038 → 2,022 MiB), 0 responses in 1,203 s; non-live histogram: `LinkedList$Node` 15.86 M + `String` 15.95 M +
  `byte[]` 15.95 M ≈ 1,955 MB = **92 %** of 2,116 MB, ≈ 123 B per message, U/K ≈ 58.
- Control C2-1..3 (comment payload, same bytes/frame/K): 0/3, ≈ 2,300 responses each, after GC ≤ 257 MiB. Intervention
  I2-1..3 (keep only the first message): 0/3, every connection answered with the same first message in 176–177 s,
  after GC ≤ 313 MiB.
- **Why no OOM** (U6 §4): the lexers allocate only small objects (`NoViableAltException`, `StringBuilder`, the message);
  G1's Full GC always reclaims one region of that garbage, so every small allocation is eventually served; G1 has no
  GC-overhead limit. Only the humongous arrays of a request (allocated when the heap was still empty) needed contiguous
  regions.
- Arm B (supporting, OC-278/285): PREPARE of `SELECT v FROM u6.t WHERE k IN (?,…,?)` with 8,388,585 markers, N = 3,
  2 GiB: **heap OOM 3/3** at +62.6 / 65.6 / 64.6 s; OOME thread `ArrayList.grow` ← `BufferedTokenStream.fetch` ←
  `CommonTokenStream.consume` ← `Cql_Parser.singleColumnInValues` (during the parse, before prepare and the marker check);
  dump B2-1: `CommonToken` 24,776,649 = 1,486.6 MB (59 % of 2,517 MB), `Object[]` ≥ 1 M elements 466 MB,
  `AbstractMarker$Raw` 12,388,295 = 247.8 MB. One matched control CB2-1 (comment PREPARE): survived, after GC ≤ 529 MiB.
  No intervention, so OC-278/285 stayed `retry (U6)`.

### 1.3 Phase-1 case files and stage 4 (from U6 §1.3, re-read 2026-11-20)

- **`no_constraint-istokenvalid-token_position--autonomous`** (OC-409, OC-410; estimate `negative`, no stage 4):
  `isTokenValid` (`ErrorCollector.java:187-190`) only decides whether a parser error gets a snippet; its A4 notes the
  unbounded `errorMsgs` list (line 52) — the holder of this case. Nothing was run in phase 1.
- **`max-unsigned-short-prepare-boundTerms--autonomous`** (OC-278, OC-285; estimate `negative`; stage 4 2026-10-26:
  **true negative, does not cap**): 43 B per marker retained in a prepared statement (2,842,844 B at 65,535 markers);
  65,536 markers are rejected only after `parseAndPrepare`. Stage 4 never measured the transient parse memory of a
  statement far above 65,535 markers (condition B's subject).
- OC-140 (`prepared_statements_cache_size…`, the literal-term form) is **not** covered here (as in U6).

### 1.4 JIRA prior art (read only; nothing posted)

- **Survey** `capacity-enforcement-exp/cassandra/stage5-oom-clue-find/jira-oom-survey.csv` (604 rows, re-checked
  2026-11-20 10:34 ET; grep for `humongous|ErrorCollector|lexer|parser|syntax error|marker|token|prepare|full gc`): no row on
  the CQL lexer, `ErrorCollector`, the token buffer, marker count or humongous decode buffers as a memory holder. Nearest:
  CASSANDRA-2475 (prepared statements, uncapped map discussed), 6107 (prepared batch statements cache), 11846 (invalid
  insert OOM, a type mismatch), 19703 (prepared cache race) — none is this mechanism.
- **JIRA REST** (`issues.apache.org/jira/rest/api/2/search`, project CASSANDRA, 2026-11-20 10:33–10:37 ET):
  - `text ~ "ErrorCollector"` → 5 (7769, 7111, 7569, 11803, 14096), as U6 found; none about memory.
  - `text ~ "humongous"` → 9: **CASSANDRA-17655** "Prevent JVM Humongous allocations" (Open, 2022: large partitions cause
    humongous allocations; asks Cassandra to limit allocation sizes or move them off heap; no OOM, no parser),
    **CASSANDRA-17408** "Humongous Allocations after upgrading to 4.0" (Not A Problem), 19801, 16471 (scratch buffers),
    17456, others unrelated. General background for the trigger (humongous allocations are a known G1 pain point), not
    this mechanism.
  - `text ~ "Too many markers"` → 11: **CASSANDRA-5598** (fixed 1.2.13/2.0.4: added the marker check at PREPARE time,
    placed after the parse; no memory discussion), 18813, 6855, 2475, others unrelated.
  - `text ~ "CommonTokenStream"` → 7569, 14096 (unrelated); `text ~ "BufferedTokenStream"` → 0;
    `text ~ "no viable alternative at character" AND text ~ "heap"` → 0; `text ~ "G1 Humongous Allocation" AND
    text ~ "OutOfMemoryError"` → 0; `text ~ "readLongString"` → 8118 (decode exception handling, fixed 2.1.1);
    `text ~ "bind markers" AND text ~ "OutOfMemoryError"` → 12618 / 12769 (fixed 2.2.9/3.0.10: a malformed list value
    bound to an INSERT; not this).
- **Verdict: `new`** for condition A (OC-409/410) and condition B (OC-278/285). Not known-fixed (not a positive
  control), not documented as by design.

### 1.5 What changes from U6 (not a rerun)

U6's design had no allocation the full heap could refuse. R15 keeps U6's verified holder and payloads and adds a
**pre-declared trigger**: one (2 GiB) or three (≥ 4 GiB) further 16 MiB QUERYs of the harmless comment payload, from the
same client IP on already-open idle connections, sent once the GC log shows the thrash. Every allocation the trigger
needs is humongous (§2.4), so G1 cannot serve it from the one region a Full GC frees. The control and the intervention
get **the identical trigger at the identical offset**, so the only difference between arms remains the per-character
retention. The alternative of the row (a ≥ 60 min hold) is not chosen: D2-1's rate (+0.44 MiB/min with 26–32 MiB free)
puts its endpoint at an extrapolated 40–70 min, untested, and three test plus three matched control and three
intervention holds of ≥ 60 min do not fit the 5.5 h window. The node also changes: `pc82` is **x86_64** with 40 cores
(U6: aarch64, 8 cores); timings are re-measured (S0, S1) and not pooled with U6.

## 2. Design solution (stage 1; frozen)

### 2.1 Mechanism

**Condition A (direction: unprotected accumulation + a trigger; technique note: [`combo-playbook.md`](../../../combo-playbook.md),
multiplicity → budget; the trigger is a second, ordinary consumer of the same heap).**

Holder path of one `#` QUERY (U6 §2.1, re-checked against the pinned source 2026-11-20):

1. Admission: v4 frame ≤ `native_transport_max_frame_size` 16 MiB (`Envelope.java:197`, `:425-437`); body bytes charged to
   the per-IP and global in-flight reserves (`PreV5Handlers.java:151-186`; default non-throwing mode).
2. Decode on the Netty event-loop thread: `PreV5Handlers.ProtocolDecoder.decode` (`PreV5Handlers.java:277-289`) →
   `Message.Decoder.decodeMessage` → `QueryMessage.codec.decode` → `CBUtil.readLongString` (`QueryMessage.java:50`,
   `CBUtil.java:196-201`) → `readString(cb, length)` (`:118-134`) → `decodeString` (`:89-115`): a **thread-local**
   `CharBuffer` (`TL_CHAR_BUFFER`, `:81`) of capacity `remaining × maxCharsPerByte` (UTF-8: 1.0) is allocated when the
   thread has none or a smaller one (`:94-110`) and **kept on the thread**; `dst.flip().toString()` (`:115`) copies it into
   a new Latin-1 `String` (`byte[L]`).
3. Parse on a `Native-Transport-Requests` thread: `QueryProcessor.parseStatement` (`QueryProcessor.java:923-935`) →
   `CQLFragmentParser.parseAnyUnhandled` (`CQLFragmentParser.java:63-83`): `new ErrorCollector(input)` (`:66`),
   `new ANTLRStringStream(input)` (`:67`; ANTLR copies the string with `toCharArray()`), lexer and parser, `parser.query()`,
   and only then `errorCollector.throwFirstSyntaxError()` (`:80`).
4. ANTLR 3.5.2 `Lexer.nextToken` reports **every** unmatched `#` (`reportError` without `errorRecovery` suppression,
   `recover` consumes one character; U6 `javap` check), and `ErrorCollector.syntaxError` (`ErrorCollector.java:69-82`)
   appends one message (`line 1:<pos> no viable alternative at character '#'`) to the unbounded `LinkedList<String>
   errorMsgs` (`:52`, add at `:81`); only `errorMsgs.getFirst()` is ever used (`:98-102`). All messages stay live until the
   parse throws.

**Trigger.** Once two such parses hold ≈ 1.95 GB of messages in a 2 GiB heap, G1 runs back-to-back Full GCs, each
reclaiming about one 16 MiB region of transient garbage (U6 D2-1). A further 16 MiB QUERY (payload C, the comment text,
which itself retains nothing) needs, in order: on its event-loop thread, a `char[16,777,200]` decode buffer if that thread
has not decoded a 16 MiB string before (33,554,416 B → **2 humongous regions**, kept), the query `String`'s
`byte[16,777,200]` (16,777,216 B → **1 region**); on its NTR thread, the `ANTLRStringStream` `char[16,777,200]`
(**2 regions**). G1 allocates a humongous object only in wholly free contiguous regions; when they are missing it runs a
Full GC (twice, the second clearing soft references) and then throws `OutOfMemoryError: Java heap space`
(JDK 11 G1 `satisfy_failed_allocation`). The shipped `-XX:+HeapDumpOnOutOfMemoryError` (`jvm-server.options:120`) and
`-XX:OnOutOfMemoryError="kill -9 %p"` (`cassandra-env.sh:209`) act on the first such error in any thread. The trigger is
an ordinary request: the same frame, the same client and the same in-flight accounting as every request of the control
arm, which serves ≈ 2,300 of them per run without trouble (U6 C2).

**Classification:** unprotected accumulation (`errorMsgs` has no control; the in-flight reserves cover only wire bytes
and keep K ≤ 0.94 of the per-IP limit). The trigger does not change the direction: it is one more admitted request, and
the claimed holder is still `errorMsgs` (V3/V5 by dump histogram). Interpretation: suspected implementation defect
(diagnostics retained but never reported), not documented as by design.

**Condition B (direction: unprotected accumulation; the 65,535-marker check is a protocol limit applied after the
allocation, i.e. delayed, not a memory control).** PREPARE (`QueryProcessor.prepare` `:728` → `parseAndPrepare`
`:754` → `:441-471`) of `SELECT v FROM r15.t WHERE k IN (?,?,…,?)` with M = 8,388,585 markers: `CommonTokenStream`
(`BufferedTokenStream.tokens`, an `ArrayList<Token>`) buffers every token the parser consumes (`?` and `,`, ≈ 2M tokens);
each `?` creates an `AbstractMarker.Raw` via `newBindVariables` (`Parser.g:41-46`, used at `:431`, `:1598`, `:1604`) and
adds to `bindVariables` (`Parser.g:28`); the count is checked only after the whole parse and prepare
(`QueryProcessor.java:757-759`, bound `FBUtilities.MAX_UNSIGNED_SHORT` = 0xFFFF, `FBUtilities.java:158`).

### 2.2 Protection map

| Domain | Allocation and owner (release) | Counter K / contract C at 2 GiB | Scope, multiplicity | At the limit | Covers the claimed memory? |
|---|---|---|---|---|---|
| v4 frame size | inbound cumulation `ByteBuf` (direct, Netty pool); released after decode/response | frame length / `native_transport_max_frame_size` 16,777,216 B | per frame | frame discarded, `ProtocolException` | wire bytes only (direct) |
| Native in-flight reserves | body bytes per request, released at response | `RequestsSize` / heap/10 = 214,748,364 B; per IP heap/40 = 53,687,091 B (`DatabaseDescriptor.java:649-657`) | per node / per client IP; (N + k) × 16,777,207 B | default: force-allocate, pause the connection (`PreV5Handlers.java:178-186`) | **wire bytes only**; 3 requests = 50,331,621 B = 0.94 C_IP, no pause |
| Request concurrency | `Native-Transport-Requests` SEP pool | threads / `native_transport_max_threads` 128 | per node | queued | count only; ≤ 27 ≪ 128 |
| Decode buffer `TL_CHAR_BUFFER` | `char[capacity]` per event-loop thread (`CBUtil.java:81`, `:94-110`), **kept for the thread's life** | none | per event-loop thread that has decoded a long string; ≤ connections (default event loops 2 × cores = 80 on pc82; record from a thread dump) | — | uncovered; 32 MiB per connection's loop (standing, part of the per-request constant; not the claimed holder; recorded) |
| Query `String` and lexer `char[]` | `byte[16,777,200]` (1 region) + `ANTLRStringStream` `char[]` (2 regions) per request; released with the request | none | per request | — | uncovered, ≈ 48 MiB per request (constant; identical in all arms) |
| **`ErrorCollector.errorMsgs`** (claimed holder, A) | `LinkedList<String>` per parse (`ErrorCollector.java:52`, `:81`, `:90`); `LinkedList$Node` 24 B + `String` 24 B + `byte[46+d]` 64–72 B per lexer error ≈ 120 B (measured 123 B) | **none** | per request; one message per `#` (16.78 M per 16 MiB request) × N | none | **no control** |
| Transient lexer garbage | `NoViableAltException`, `StringBuilder`, header strings per error | none | per error | — | GC-reclaimable (what each Full GC frees) |
| **Token buffer + markers** (claimed holder, B) | `BufferedTokenStream.tokens` (`CommonToken` ≈ 60 B measured + 4 B slot; `ArrayList.grow` copies, humongous `Object[]`), `AbstractMarker.Raw` 20 B, `bindVariables` slots; released when the parse returns | none during the parse; marker count ≤ 65,535 checked after it (`QueryProcessor.java:757-759`) | per request × N | `0x2200 Too many markers(?)` after the memory is spent | **no memory control** (count check is late, protocol limit) |
| Prepared cache | `QueryProcessor.preparedStatements`, weight ≤ max(10 MiB, heap/256) | — | — | evict / refuse | not reached (B rejected before storing; A is QUERY) |
| Guardrails | — | — | — | skipped for superusers (`AllowAllAuthenticator`) | none bounds query length or marker count before the parse |
| Budgets | Java heap (`-Xmx` = `-Xms`); direct (`MaxDirectMemorySize` auto 15,872 MiB on pc82) | — | per process | heap OOM; direct OOM | both holders are heap |

### 2.3 Configuration and budget audit

- **Node `pc82`** (checked read-only 2026-11-20 10:32 ET): `node1.jason92-326665…umass.edu`, **x86_64**, 40 cores,
  MemTotal 131,943,312 kB (125 GiB), swap 8 GiB present (0 used), cgroup v2, Ubuntu 22.04, OpenJDK 11.0.33 (G1 defaults
  on this box: `ParallelGCThreads` 28, `ConcGCThreads` 7), Ant `/usr/bin/ant`, Linger=no; `/mydata` 753 GB, **714 GiB
  free**; `/mydata/s4/` holds only `cassandra-base` (jar `build/apache-cassandra-5.0.9-SNAPSHOT.jar`, ANTLR tool
  `build/lib/jars/antlr-3.5.2.jar`, `ST4-4.0.8.jar`, generated grammar in `src/gen-java/…/cql3/`); no Java process, ports
  7000/7199/9042 free, load 0.00. Node clock is **MST (ET − 2 h)**.
- **Shipped conf, unchanged in every arm**; md5 on pc82 (= U6/B14): `cassandra.yaml 714ee9bf58b3bc1710377ac16bcbba03`,
  `jvm11-server.options fbad82a853f1b85aea0fa5ea34b6d1bf`, `cassandra-env.sh 8be0588e87c594a03360751b1dbf4fbf`,
  `jvm-server.options 26a957bf004efa3b3d91285fb0975750`. Single node, `rpc_address: localhost`, port 9042,
  `AllowAllAuthenticator`, protocol v4 allowed.
- **Constraints at shipped defaults (V6):** `native_transport_max_frame_size` 16 MiB; `native_transport_max_request_data_in_flight`
  heap/10; `…_per_ip` heap/40; `native_transport_max_message_size` derived (16 MiB; enforced on v5); `max_mutation_size`
  derived 16 MiB; `native_transport_max_threads` 128; `native_transport_timeout` 12 s; rate limiting off; connection limits
  −1; `prepared_statements_cache_size` auto. The intervention arms differ only by the diagnostic build (§2.8).
- **Resolved values** (read from JMX `StorageService` `NativeTransportMaxConcurrentRequestsInBytes` / `…PerIp` once per
  budget; `Runtime.maxMemory()` = `-Xmx` under G1):

| Heap | Global C (B) | Per-IP C (B) | 16,777,207-B requests per IP | Regions (16 MiB) |
|---|---|---|---|---|
| 2 GiB | 214,748,364 | 53,687,091 | 3 | 128 |
| 4 GiB | 429,496,729 | 107,374,182 | 6 | 256 |
| 8 GiB | 858,993,459 | 214,748,364 | 12 | 512 |
| 16 GiB | 1,717,986,918 | 429,496,729 | 25 | 1,024 |
| 31,744 MiB (node auto) | 3,328,599,654 | 832,149,913 | 49 | 1,984 |

- **Environment (not capacity):** `MAX_HEAP_SIZE=<heap>`, `HEAP_NEWSIZE` unset (G1 ⇒ `-Xms = -Xmx`);
  `CASSANDRA_HEAPDUMP_DIR=<run dir>`; `systemd-run --user --scope -p MemorySwapMax=0` (no `MemoryMax`); `ulimit -n 100000`;
  shipped G1 (`G1HeapRegionSize=16m`, `MaxGCPauseMillis=300`), shipped GC log (`cassandra-env.sh:83`,
  `gc=info,heap*=trace,…`), shipped OOM dump and kill. Dumps stay **on** at every budget (disk is ample; a 31 GiB dump is
  ≈ 33 GB of 714 GiB); only the dump analysis is capped (§2.6).
- **V7 budgets.** `cassandra-env.sh` would resolve for pc82: heap = min(½ RAM 64,423 MiB, 31,744) = **31,744 MiB**,
  `MaxDirectMemorySize` = 31,744 / 2 = **15,872 MiB** (`cassandra-env.sh:51-68`; with a hand-set heap the direct limit
  stays 15,872 MiB, `:139-158`; record from the JVM-arguments line). Heaps 2 GiB (ideal, the V-runs), 4, 8, 16 GiB and the
  node-auto 31,744 MiB, all ≥ 512 MiB ⇒ V7 met without per-case review (standing rule 2026-11-11). Direct auto. **No
  container limit** is a budget ⇒ no owner review needed.
- **Arch:** x86_64; never pool with U6's aarch64 readings (compare only qualitatively).

### 2.4 Ceiling arithmetic

**Holder per request (A).** Payload H: QUERY of `#` × L, L = 16,777,200; body 16,777,207 B; frame 16,777,216 B
(accepted: the check is `>`). Messages per request E = L (+1 parser error). U6 measured 123 B per message
(prediction band 110–135 B) ⇒ **U_req(full lex) ≈ 1.92–2.06 GiB**, plus the request constant (String 16 MiB + ANTLR
`char[]` 32 MiB + decode buffer 32 MiB per event loop) ≈ 80 MiB. Baseline idle 5.0.9 at 2 GiB: 30–150 MiB.

**Trigger arithmetic (2 GiB).** U6 thrash: after-GC 2,009–2,022 MiB of 2,048 ⇒ 26–39 MiB free ⇒ **≤ 2 wholly free
regions**, not necessarily adjacent. The trigger's live humongous set is 2 (decode buffer, if its loop is fresh) + 1
(String) + 2 (ANTLR `char[]`) = **5 regions** (3 if the loop already holds a buffer). Either exceeds the free regions ⇒
an allocation fails after Full GC ⇒ heap OOM. The trigger request itself adds no messages (comment payload).

**Trigger arithmetic (≥ 4 GiB).** U6 T4-1: 87–120 MiB free after Full GC ⇒ ≤ 7 regions, so one trigger (3–5 regions)
might be served. Therefore k = 3 triggers at ≥ 4 GiB (9–15 regions together; sent at the same instant on three idle
connections), still inside the per-IP limit.

| Run | Heap | N (H) + k (trigger) | K = (N + k) × 16,777,207 B | vs per-IP C | Demand at full lex (N × 1.97 GiB) | Heap full at | Predicted endpoint |
|---|---|---|---|---|---|---|---|
| S1 (no trigger) | 2 GiB | 2 + 0 | 33,554,414 | 0.63 | 3.9 GiB | ≈ 52 % of each lex | GC service loss, no OOM (as U6) |
| T2 | 2 GiB | 2 + 1 | 50,331,621 | 0.94 | 3.9 GiB | ≈ 52 % | **heap OOM** ≤ 60 s after the trigger |
| C2 (control) | 2 GiB | 2 C + 1 | 50,331,621 | 0.94 | ≤ 3 × 80 MiB + baseline ≈ 0.4 GiB | never | survive |
| I2 (intervention) | 2 GiB | 2 H(iv) + 1 | 50,331,621 | 0.94 | ≤ 3 × 80 MiB + garbage ≈ 0.4 GiB | never | survive |
| T4 | 4 GiB | 3 + 3 | 100,663,242 | 0.94 | 5.9 GiB | ≈ 68 % | heap OOM |
| T8 | 8 GiB | 6 + 3 | 150,994,863 | 0.70 | 11.8 GiB | ≈ 68 % | heap OOM |
| T16 | 16 GiB | 12 + 3 | 251,658,105 | 0.59 | 23.6 GiB | ≈ 68 % | heap OOM |
| T31 (optional) | 31,744 MiB | 24 + 3 | 452,984,589 | 0.54 | 47.3 GiB | ≈ 66 % | heap OOM |

Σ contract capacities that cover this memory: none (the in-flight reserves cover only K, ≈ 1/120 of the holder). At
every budget N = ⌈1.5 × heap / 2 GiB⌉ plus k triggers stays inside both in-flight limits and the 128 NTR threads, so the
endpoint is reachable by arithmetic at the node's own heap. Direct memory: frames ≤ 27 × 32 MiB ≪ 15,872 MiB.
CPU: ≤ 24 lexer threads + 28 parallel GC threads on 40 cores (overlap acceptable; record load).

**Condition B.** PREPARE body = `[long string]`; query = `SELECT v FROM r15.t WHERE k IN (` (32 chars) + `?,` × (M − 1) +
`?)`, M = ⌊(16,777,203 − 32) / 2⌋ = **8,388,585** (query 16,777,202 B, body 16,777,206 B, frame 16,777,215 B; the harness
prints the sizes). From U6 B2-1 (failure at ≈ 50 % of each parse, 3 requests): ≈ 60 B per `CommonToken`, ≈ 16.8 M tokens
per request ⇒ tokens ≈ 1.0 GB + list arrays 67 MB (+ 1.5× during `grow`) + `Marker.Raw` and IN list ≈ 0.25 GB ⇒ **≈ 1.3–1.5
GB per request at the end of its parse** (± 30 %).

| Run | Heap | N | K | vs per-IP C | Demand (N × 1.3–1.5 GB) | Predicted |
|---|---|---|---|---|---|---|
| TB2 | 2 GiB | 3 | 50,331,618 | 0.94 | 3.9–4.5 GB | heap OOM in the parse (U6: +63–66 s on aarch64) |
| CB2 | 2 GiB | 3 | same | 0.94 | 3 × ≈ 80 MiB | survive |
| IB2 | 2 GiB | 3 | same | 0.94 | ≈ 131 K tokens per request ≈ 10 MB | survive, fast `0x2200` |
| TB4 | 4 GiB | 6 | 100,663,236 | 0.94 | 7.8–9 GB | heap OOM |
| TB8 | 8 GiB | 12 | 201,326,472 | 0.94 | 15.6–18 GB | heap OOM |

### 2.5 Workload and environment

- **Node:** `pc82` only (victim and client on one node; one run at a time). Work dir **`<W>` = `/mydata/s4/r15-w5/`**:
  `cassandra/` (`cp -a /mydata/s4/cassandra-base`), `cassandra-iv/` (A intervention), `cassandra-ivb/` (B intervention),
  `harness/`, `runs/<run-id>/`. Never touch `/mydata/s4/cassandra-base` except to copy from it. Preflight per run:
  `ps -eo pid,cmd | grep '[C]assandraDaemon'` and `ss -ltn | grep -E ':(7000|7199|9042) '` empty; if another agent's node
  runs on pc82, stop and report. Linger is off: drive each series from one long-lived `ssh` session started with
  `( setsid nohup … < /dev/null > … 2>&1 & )`, bounded background polls, never a foreground `sleep`.
- **Builds** (in the background during harness setup):
  - `build-iv.sh`: `cp -a cassandra cassandra-iv`; `git apply` U6's
    [`iv.patch`](../ErrorCollector_errorMsgs--one-message-per-bad-character/harness/iv.patch) (§2.8; save `git diff` as
    `harness/iv.diff`); `rm -f build/classes/main/org/apache/cassandra/cql3/ErrorCollector*.class`; `ant jar`; check
    `javap -p -c -classpath build/apache-cassandra-5.0.9-SNAPSHOT.jar org.apache.cassandra.cql3.ErrorCollector | grep -c
    isEmpty` = base + 2.
  - `build-ivb.sh`: `cp -a cassandra cassandra-ivb`; apply `harness/ivb.patch` (§2.8; save the diff); `rm -f
    build/classes/main/org/apache/cassandra/cql3/Cql*.class`; `ant jar` (the edited `Parser.g` is newer than
    `src/gen-java/…/Cql.tokens`, so `gen-cql3-grammar` regenerates with the local `antlr-3.5.2.jar`; check
    `ls -l --time-style=+%T src/gen-java/org/apache/cassandra/cql3/Cql_Parser.java` is new and `javap -p -classpath
    build/apache-cassandra-5.0.9-SNAPSHOT.jar org.apache.cassandra.cql3.Cql_Parser | grep -c checkMarkerCount` ≥ 1). If
    the grammar cannot be regenerated offline, condition B runs without intervention and is labelled `(no intervention)`
    with the reason. Never run `ant` in a tree a node runs from.
- **Harness** (`harness/` in this folder, synced to `<W>/harness/`; Python 3 stdlib; start from U6's
  [`harness/`](../ErrorCollector_errorMsgs--one-message-per-bad-character/harness/): `client.py`, `run.sh`, `series.sh`,
  `monitor.sh`, `Jmx.java`, `threadcount.py`, `stw.py`, `summarize.py`, `hprof-histo.py`, `hprof_oome_thread.py`; change
  `W`, unit names `r15-<run-id>`, keyspace `r15`). Changes:
  - `client.py`: payloads `H`, `C`, `M`, `CM` as U6 (C = `-- ` + `#` × (L − 4) + `\n`, the same L bytes, one comment
    token; CM = comment of L_M = 16,777,202). New options `--trig-n k` and `--trig-at <spec>`: at client start, besides
    the N load connections, open k **trigger connections** (STARTUP done, idle; all from 127.0.0.1). Each load connection
    runs U6's closed loop (one request outstanding). At the trigger instant each trigger connection sends **one** QUERY of
    payload C (full length) and waits for its response (socket timeout = hold + 120 s). `--trig-at` is either
    `gc:<gc.log path>:<heap MiB>` (detection rule below) or `fixed:<seconds after load start>`; **load start** = the
    instant the last of the N load connections sends its first request (all offsets in this design are from load start). Log the trigger
    send time, response time and code in `completions.txt` (tag `trig`), and the decision in `trigger.txt`
    (`t_det`, `t_trig`, rule used, the three Full-GC lines that fired it).
  - **Trigger rule (pre-declared).** Test runs: tail `gc.log`; when **three consecutive `Pause Full` lines** report an
    after-size ≥ **0.95 × heap**, that is t_det; **t_trig = t_det + 30 s**, but not earlier than +30 s after load start
    and not later than **t_max = max(300 s, 4 × T_lex)** (T_lex from S0); if not detected by t_max, fire at t_max and
    record `undetected`. **C-k and I-k fire at T-k's recorded offset** (`fixed:`), so the trigger is matched in time per
    triplet; budget-search runs use the `gc:` rule. S1 runs the detector but sends nothing.
  - `run.sh <run-id> <base|iv|ivb> <heap> <payload> <N> <k> <trig-spec> <hold-after-trigger-s>`: U6's driver (preflight
    with `df` ≥ 1.3 × heap + 4 GiB, wipe `data/`, `logs/`, start under the scope, wait ≤ 300 s for `Starting listening for
    CQL clients`, `jcmd VM.flags`, `--ddl` for B, 20 s baseline with monitors, client, stop at the endpoint (daemon gone and
    `java.lang.OutOfMemoryError` in `stdout.txt`) or at hold end, wait for `Heap dump file created` up to 240 s (600 s at
    ≥ 16 GiB), `kill` by PID, copy logs, `summarize.py`). The `series.sh` time guard becomes **16:40 ET** (no run starts
    later).
- **Runs** (shipped conf; one node lifetime per run):

| Run | Build | Heap | Load payload × N | Trigger k, rule | Hold | Purpose |
|---|---|---|---|---|---|---|
| `S0` (not a reading) | base, then iv, then ivb | 2 GiB | H, C, M, CM at `--len 1048576`, × 1, each 2× sequential; iv: H; ivb: M | — | per request | reachability and τ on x86: H → `0x2000 line 1:0 no viable alternative at character '#'`; C → one EOF `0x2000`; M → `0x2200 Too many markers(?). 524272 …`; iv H → the same first message; ivb M → `0x2200` with the intervention text, latency ≪ base M. T_lex = 16 × latency(H, 1 MiB); `jmap -histo:live` at idle; thread dump during H (lexer frame; count event-loop threads) |
| `S1` (diagnostic) | base | 2 GiB | H × 2 | 0, detector only | t_det + 180 s (cap t_max + 180 s) | x86 replication of U6 T2: thrash without trigger; gives t_det |
| `T2-1..3` | base | 2 GiB | H × 2 | 1, `gc:` | until OOM, else t_trig + 180 s | V1 |
| `C2-1..3` | base | 2 GiB | C × 2 | 1, `fixed:` T-k's offset | t_trig + 180 s | V2 |
| `I2-1..3` | iv | 2 GiB | H × 2 | 1, `fixed:` T-k's offset | t_trig + 180 s, and ≥ 1 load response per connection | V4 |
| `T4-1` | base | 4 GiB | H × 3 | 3, `gc:` | until OOM, else t_trig + 240 s | budget search |
| `T8-1` | base | 8 GiB | H × 6 | 3, `gc:` | until OOM, else t_trig + 300 s | budget search |
| `TB2-1..3` | base | 2 GiB | M × 3 | — | max(180 s, 3 × 16 × latency(M, 1 MiB) + 60 s) | B: V1 |
| `CB2-1..3` | base | 2 GiB | CM × 3 | — | same as TB2 | B: V2 |
| `IB2-1..3` | ivb | 2 GiB | M × 3 | — | same as TB2 | B: V4 |
| `T16-1` | base | 16 GiB | H × 12 | 3, `gc:` | until OOM, else t_trig + 300 s | budget search |
| `TB4-1` | base | 4 GiB | M × 6 | — | as TB2 + 60 s | B budget search |
| `TB8-1` | base | 8 GiB | M × 12 | — | as TB2 + 120 s | B budget search |
| `T<max>-2, -3` | base | largest failing A budget ≤ 16 GiB | as its run | as its run | as its run | n/N at the largest failing budget |
| `T31-1` (optional) | base | 31,744 MiB | H × 24 | 3, `gc:` | until OOM, else t_trig + 300 s | node-auto budget |

  **Order:** `S0`, `S1`, `T2-1`, `C2-1`, `I2-1`, `T2-2`, `C2-2`, `I2-2`, `T2-3`, `C2-3`, `I2-3`, `T4-1`, `T8-1`, `TB2-1`,
  `CB2-1`, `IB2-1`, `TB2-2`, `CB2-2`, `IB2-2`, `TB2-3`, `CB2-3`, `IB2-3`, `T16-1`, `TB4-1`, `TB8-1`, `T<max>-2`, `T<max>-3`,
  `T31-1`. Search rules: if `T4-1` survives, skip `T8-1`, `T16-1`, `T31-1` (boundary between 2 and 4 GiB); if `T8-1`
  survives, skip `T16-1`/`T31-1`; if `T16-1` survives skip `T31-1`. Same for B: `TB4-1` survives ⇒ skip `TB8-1`. Never
  drop a V-run of condition A for any other run.
- **Disk plan:** three trees ≈ 1.5 GB; dumps ≈ 2.5–3 GB (2 GiB), 5 GB (4), 10 GB (8), 20 GB (16), ≈ 35 GB (31 GiB):
  analyse, record size + sha256 prefix + findings, then delete the `.hprof` (keep none at the end). Peak disk < 50 GB of
  714 GiB.

### 2.6 Instruments

| What | How | Interval | Gives |
|---|---|---|---|
| Heap occupancy (U side, independent of K) | `logs/gc.log` (shipped Xlog, `heap*=trace` gives region counts): every `Pause Full` with after-size, humongous region counts, the GC cause (`G1 Humongous Allocation` / `Allocation Failure`); `jcmd <pid> GC.heap_info` (no forced GC) | every GC; 3 s | U(t); **free regions after Full GC just before the trigger** (heap − after-size, and humongous/free region counts from the trace lines) |
| Trigger | `trigger.txt` and `completions.txt` tag `trig` | event | t_det, t_trig, rule, trigger response (none / code) |
| Holder at failure (V3, V5) | the shipped OOM dump: `hprof_oome_thread.py` on **every** failing run; `hprof-histo.py` (U6's, `--len-range 47 54`) on the **first failing run per budget** (`T2-1`, `T4-1`, `T8-1`, `TB2-1`, `TB4-1`; at ≥ 16 GiB only if it completes within the cap): `LinkedList$Node`, `String`, `byte[47..54]`, `ErrorCollector`, `char[]` ≥ 1 M, `byte[]` ≥ 1 M, `NoViableAltException`; B: `CommonToken`, `Object[]` ≥ 1 M, `AbstractMarker$Raw` | at end | E_fail, U_fail (shallow sum of message classes), share of dump; U/K; which thread threw and in which frame (event loop `CBUtil.decodeString`/`StringUTF16.compress`, NTR `ANTLRStringStream.<init>`, or a lexer) |
| K (server) | JMX `org.apache.cassandra.metrics:type=Client,name=RequestsSize`, `…PausedConnections`, `StorageService` resolved limits (U6 `Jmx.java poll`) | 5 s | K ≤ C, paused 0 |
| K (client) | `client.txt` (outstanding × body, load and trigger separately) | 1 s | K |
| Parses in flight | `jcmd <pid> Thread.print`: NTR threads in `CqlLexer`/`Lexer.nextToken`/`ErrorCollector.syntaxError` (B: `CqlParser`/`BufferedTokenStream`); event-loop thread names and count | 10 s | n_held(t) |
| GC service level | `stw.py`: STW share per 60-s window (each GC id once across rotated files) | after run | onset of ≥ 90 % STW; share before and after the trigger |
| Process | `RssAnon`; client `ps -o pcpu,rss`; `uptime` load | 3 s / 10 s | native growth; CPU |
| Throughput | `completions.txt` | per response | responses by code and latency; I/IB: error text and rate |
| Endpoint | `stdout.txt`: first `java.lang.OutOfMemoryError` line, `Dumping heap to`, `Heap dump file created`, the kill; `system.log` ERRORs; exit time | end | endpoint type; t_OOM − t_trig |
| Disk | `df -BM /mydata` | 10 s | guard (avail < 50 GiB ⇒ stop the client, record) |

The samplers are the same in every arm; no forced GC or live histogram during a measured run (only in `S0`).
`summarize.py` writes per run: endpoint, t_det, t_trig, t_OOM − t_trig, n_held, K max, last Full-GC after-sizes and free
regions before the trigger, STW share, responses by code, max `RssAnon`, dump findings. Each dump analysis is capped at
15 min (record a cap hit).

### 2.7 Predicted response, outcome rows and stopping budget

**Predicted (before readings):**

- `S0`: H 1 MiB → `0x2000 line 1:0 no viable alternative at character '#'`, τ on x86 ≈ 2–7 µs (T_lex(16 MiB)
  ≈ 35–120 s; U6 m400: 11 µs); C → one EOF `0x2000` in < 0.2 s; M → `0x2200 Too many markers(?). 524272 markers exceed
  the allowed maximum of 65535`; iv H → the same first message, latency within ± 30 % of base; ivb M → `0x2200` with the
  intervention text in < 0.2 s.
- `S1`: GC service loss (≥ 90 % STW over ≥ 60 s) from ≈ 0.8–1.4 × T_lex after the sends, after-GC ≥ 1,990 MiB, no OOM
  (if `S1` ends in OOM without a trigger, record it: the endpoint then does not need the trigger on x86, and the T arm is
  still valid).
- `T2-*`: **heap OOM 3/3**, `java.lang.OutOfMemoryError: Java heap space`, t_OOM − t_trig ≤ 60 s (≤ 2 Full-GC cycles);
  free regions after the last Full GC before the trigger ≤ 2; OOME thread = the trigger's event-loop thread in
  `CBUtil.decodeString`/`CharBuffer.allocate`/`String` construction, or its NTR thread in `ANTLRStringStream.<init>`
  (a lexer thread is acceptable if the histogram shows the holder); dump (`T2-1`): message classes (`LinkedList$Node` +
  `String` + `byte[47..54]`) ≥ 1.5 GB and **≥ 60 %** of shallow bytes, `ErrorCollector` = 2 (+1 for the trigger if its
  parse started), U/K ≥ 30 (U_fail ≥ 1.5 GB / K 50.3 MB). K ≤ 50,331,621 B, paused 0.
- `C2-*`: survive 0/3; ≈ 1–3 responses per second per load connection, all EOF `0x2000`; the trigger answered `0x2000`
  within 5 s; after-GC peak ≤ 0.5 GiB; STW < 10 %.
- `I2-*`: survive 0/3; load responses `0x2000` with the base first message after ≈ T_lex each (≥ 1 per connection); the
  trigger answered within 5 s; after-GC peak ≤ 0.5 GiB.
- `T4-1`, `T8-1`, `T16-1`, `T31-1`: heap OOM ≤ 120 s after the trigger (Full GCs at 8–31 GiB may take 5–30 s each).
- `TB2-*`: heap OOM 3/3 during the parse (OOME in `ArrayList.grow`/`BufferedTokenStream.fetch` or another parse
  allocation), ≤ 70 s after the sends; dump `CommonToken` + token `Object[]` + `AbstractMarker$Raw` ≥ 60 % of shallow
  bytes. `CB2-*`: survive 0/3, after-GC ≤ 0.6 GiB. `IB2-*`: survive 0/3, every request answered `0x2200` (intervention
  text) in < 1 s, after-GC ≤ 0.3 GiB. `TB4-1`, `TB8-1`: heap OOM.

**Outcome rows — condition A:**

| Row | Observation | Reading |
|---|---|---|
| A1 | T2 OOM ≥ 3/3; C2 0/3; I2 0/3 with responses; dump shows message classes ≥ 60 %; defaults; 2 GiB | **true positive**: `verified-OOM · deployment` (unprotected accumulation, `errorMsgs`; trigger = one ordinary 16 MiB request); largest failing budget from T4/T8/T16/T31 with n/N |
| A2 | T2 OOM 3/3 but C2 or I2 OOM ≥ 1/3 | the trigger alone (or the 48–80 MiB request constant) reaches OOM, not the retention ⇒ **retry** (attribution fails) |
| A3 | T2 survives: the trigger is answered (or stays queued) and the thrash continues | G1 found the regions (record free regions); ⇒ **retry**, with k and the trigger time as the next dials |
| A4 | T2 OOM but message classes < 60 % of the dump or another holder largest | attribution fails ⇒ **retry** |
| A5 | T2 OOM before the trigger (as on x86 S1 may show) | counts for V1 (the endpoint, not the trigger, is the claim); record pre-trigger |
| A6 | direct-buffer OOM, kernel kill, or frames rejected / `Overloaded` / no lexer frame | competing endpoint or invalid run ⇒ record; **retry** or fix in shakedown |
| A7 | T2 mixed (1–2/3) | expand to 6 runs (time permitting) and report n/N; a stated rate < N/N is allowed by V1 |

**Outcome rows — condition B (separately concluded):**

| Row | Observation | Reading |
|---|---|---|
| B1 | TB2 OOM ≥ 3/3; CB2 0/3; IB2 0/3 (or `(no intervention)` if ivb could not be built); token classes ≥ 60 % | **true positive** for OC-278/285: `verified-OOM · deployment` (or `… (no intervention)`) |
| B2 | CB2 or IB2 OOM ≥ 1/3 | **retry** |
| B3 | TB2 survives (the per-request peak below the predicted 1.3 GB) | measured U_req × N vs budget: if 6 requests at 4 GiB (TB4-1) also survive with U_req measured, **false positive** by arithmetic; else **retry** |
| B4 | condition B not run (time) | left for a later case; OC-278/285 stay as they are |

**Stopping budget:** per run the hold of §2.5 (no run longer than start + baseline + t_max + hold + dump + 3 min); one
endpoint per run, no escalation after an OOM; N and k never above the table; the whole stage within the time plan.

### 2.8 Controls and intervention

- **A — matched control (V2), 3 runs:** `C2-k`: the same opcode, build, conf, heap, instruments, two load connections
  sending the comment payload C (the same 16,777,200 bytes, the same frame and K, the same query `String`, ANTLR `char[]`
  and decode buffer, the lexer walks every character) and the **same trigger** (one payload-C QUERY on an idle third
  connection) at **T-k's trigger offset**. The only difference is that the load text is one comment token, so no message
  per character is retained. Survival shows that the OOM needs the retained messages, not the trigger, the wire volume or
  the humongous request copies.
- **A — causal intervention (V4), 3 runs:** `I2-k`: build `cassandra-iv` with U6's one-file patch (saved as `harness/iv.diff`;
  each message is still built, only the first is retained):

  ```diff
  --- a/src/java/org/apache/cassandra/cql3/ErrorCollector.java
  +++ b/src/java/org/apache/cassandra/cql3/ErrorCollector.java
  @@ public void syntaxError(BaseRecognizer recognizer, String[] tokenNames, RecognitionException e)
  -        errorMsgs.add(builder.toString());
  +        String m = builder.toString();
  +        if (errorMsgs.isEmpty()) // U6 intervention (diagnostic build only): keep only the message that is thrown
  +            errorMsgs.add(m);
       }
  @@ public void syntaxError(BaseRecognizer recognizer, String errorMsg)
  -        errorMsgs.add(errorMsg);
  +        if (errorMsgs.isEmpty()) // U6 intervention: keep only the message that is thrown
  +            errorMsgs.add(errorMsg);
  ```

  Payload H × 2 and the same trigger at T-k's offset. Clients see the same error; throughput is recorded (one response
  per ≈ T_lex per connection, as in U6 I2). The original failure is reproduced on the unmodified build (T2).
- **A — trigger attribution (diagnostic, not a V-item):** `S1` (no trigger) shows whether the thrash alone ends in OOM on
  x86; with U6's 0/3 + D2-1 on aarch64 it frames the trigger as the step that turns the service loss into an OOM.
- **B — matched control (V2), 3 runs:** `CB2-k`: PREPARE of `-- ` + `#` × (L_M − 4) + `\n` (L_M = 16,777,202; the same
  bytes, frame and K; one token), N = 3, same heap/build/instruments.
- **B — causal intervention (V4), 3 runs:** `IB2-k`: build `cassandra-ivb`, payload M × 3. Patch (`harness/ivb.patch`,
  save the exact diff): the existing 65,535 bound (`QueryProcessor.java:757-759`) applied while the parser creates markers,
  so the parser stops consuming tokens at marker 65,536:

  ```diff
  --- a/src/antlr/Parser.g
  +++ b/src/antlr/Parser.g
  @@ @members {
       protected final List<ColumnIdentifier> bindVariables = new ArrayList<ColumnIdentifier>();
   
  +    // R15 intervention (diagnostic build only): apply the 65535-marker bound during the parse
  +    private void checkMarkerCount()
  +    {
  +        if (bindVariables.size() >= org.apache.cassandra.utils.FBUtilities.MAX_UNSIGNED_SHORT)
  +            throw new org.apache.cassandra.exceptions.InvalidRequestException(
  +                "Too many markers(?). More than 65535 markers (R15 intervention: checked during the parse)");
  +    }
  +
  @@ public AbstractMarker.Raw newBindVariables(ColumnIdentifier name)
       {
  +        checkMarkerCount();
           AbstractMarker.Raw marker = new AbstractMarker.Raw(bindVariables.size());
  ```

  and the same `checkMarkerCount();` first line in `newINBindVariables`, `newTupleBindVariables`,
  `newTupleINBindVariables`, `newJsonBindVariables`. The exception is a `CassandraException`, which ANTLR's rule code
  (catching only `RecognitionException`) lets through and `QueryProcessor.parseStatement` rethrows unchanged
  (`QueryProcessor.java:927-931`), so the client gets `0x2200` (the base build also answers this payload with `0x2200 Too
  many markers` after the parse, so no useful work is lost; record the response rate).
- **V-table plan:** A — V1 `T2-1..3`; V2 `C2-1..3`; V3 U from `gc.log` and the `T2-1` dump vs K from `RequestsSize` and
  `client.txt`; V4 `I2-1..3`; V5 the OOME thread of every T2 run + `T2-1` histogram; V6 §2.3 (conf md5, JMX limits); V7
  2 GiB, direct auto, no container limit; largest failing budget with n/N. B — the same with `TB2`, `CB2`, `IB2`, `TB2-1`
  histogram, `TB4-1`/`TB8-1`.

### 2.9 Time plan (America/New_York; node clock MST = ET − 2 h)

Stage 2 starts ≈ **12:00** (T0); hard end **17:30**. Per-run estimates on pc82 (x86 starts in ≈ 30–60 s; T_lex assumed
35–120 s): T2 ≈ 6–8 min (start 1 min, baseline 20 s, thrash ≈ 1–2.5 min, trigger + OOM ≤ 1.5 min, 3 GB dump ≤ 1 min,
teardown/OOME-thread ≤ 2 min); C2/I2 ≈ 6–7 min; TB/CB/IB ≈ 4–5 min.

| ET | Step |
|---|---|
| 12:00–12:25 | read, freeze-hash check, node check, copies, `build-iv.sh` and `build-ivb.sh` in the background, harness |
| 12:25–12:40 | `S0` (base, iv, ivb lifetimes) |
| 12:40–12:52 | `S1` |
| 12:52–14:05 | nine A V-runs (+ `T2-1` histogram ≤ 15 min) |
| 14:05–14:35 | `T4-1`, `T8-1` (10 GB dump) |
| 14:35–15:30 | nine B V-runs (+ `TB2-1` histogram) — **start only if begun by 15:00**, else condition B is not run (outcome B4) |
| 15:30–15:55 | `T16-1` (20 GB dump; OOME thread only if the histogram would exceed the cap) |
| 15:55–16:15 | `TB4-1`, `TB8-1` |
| 16:15–16:40 | `T<max>-2`, `-3`; `T31-1` only if it can start by 16:15 and nothing else is pending |
| ≤ 16:40 | last run start (`series.sh` guard) |
| ≤ 16:55 | every process stopped, pc82 checked empty (no daemon, ports free), `.hprof` files deleted |
| 16:55–17:30 | §3, §4, write-backs |

**Drop order if late** (check at 14:05 and 15:30): `T31-1`, `T<max>-2/-3`, `TB8-1`, `TB4-1`, `T16-1`, the `TB2-1`
histogram, then condition B as a whole (only before any B run starts). Never dropped: `S0`, the nine A V-runs, `T4-1`.
`S1` may be dropped only if `S0` gives T_lex > 4 min (record it). RAM: largest JVM 31 GiB heap + ≤ 1 GiB direct/native on
125 GiB; CPU ≤ 24 lexer + 28 GC threads on 40 cores; disk < 50 GB.

### 2.10 Write-back rule (fixed now, applied by stage 2)

- Condition A's verdict closes the **U6 retry row** (`true positive (R15)` / `false positive (R15)` / `retry (R15)`), and is
  written to OC-409 and OC-410 in the phase-1 candidate list (OC-410 with "lexer part; parser-error path not tested").
- Condition B's verdict is written to OC-278 and OC-285 (if B ran; if not, they keep their current status and the U6 row
  text keeps "arm B: own case"). OC-140 is unchanged (literal form not tested).
- `_INDEX.md`: one row for R15 with both conditions' verdicts. A true positive whose shape no clue pattern covers adds a
  pattern ("retained per-item diagnostics + a humongous request turns GC thrash into OOM", or "parse-time token buffer
  before a post-parse count check") with source `phase 2: R15`.

`sha256 of §1–§2 at freeze: 29179745be817bed412bfe9b86bf36538836526bbde16e4e85e5503dff619b6a` · computed over the lines from `## 1. Candidate` through the line before this one (`awk '/^## 1\. Candidate/{f=1} /^.sha256 of §1–§2 at freeze/{f=0} f' <case file> | sha256sum`), frozen 2026-11-20 · amendments after the freeze: dated, with reason.

## 3. Runs (stage 2)

### 3.0 Amendments and notes after the freeze (dated; amendments written before the readings they affect)

- **Amendment 1 (2026-11-20 11:20 ET, after `T2-1`, before any `D1` reading).** `T2-1` ended in outcome row A3: the
  trigger was sent at +116.2 s, but in the 180-s hold no `G1 Humongous Allocation` GC occurred, Humongous regions stayed
  10 (the two load requests' arrays), the server's `RequestsSize` stayed 33,554,414 B (the trigger was never admitted) and
  the trigger got no response. The frozen design has no instrument that shows where the trigger request is held. Added
  **one diagnostic run `D1`**, after every frozen run (it displaces none): identical to `T2` (base, 2 GiB, H × 2, k = 1,
  `gc:` rule) except the hold after the trigger is **1,800 s** and the monitor keeps every full `Thread.print` (env
  `R15_DIAG=1`, `harness/monitor.sh`; same 10-s cadence as the counted samples of every arm). Purpose: locate the trigger
  (event-loop read/decode, admission, NTR queue) and see whether a longer hold after the trigger ends in OOM. `D1` is not
  a V-run and does not change any frozen run or outcome row; if it ends in OOM it is reported as a diagnostic reading
  only.
- **Interruption and resumption note (2026-11-20 21:30 ET).** The stage-2 session was suspended by the API usage limit at
  ≈ 13:20 ET (not by the design) and resumed at 21:26 ET. The coordinator's resume message described the cut-off as
  "while writing build scripts"; the node and this file show otherwise: the builds had finished at 10:43 ET
  (`logs/build-iv.log`, `logs/build-ivb.log`: `ant rc=0`, `BUILD-DONE iv`/`ivb`, the `isEmpty` and `checkMarkerCount`
  checks), and **every run of the frozen design plus `D1` had finished by 13:16:53 ET** (`series-list-d.txt.log` "SERIES
  DONE"); the session was then writing this §3. Check at 21:26 ET on `pc82`: no `java`, `series.sh`, `run.sh` or
  `client.py` process; ports free; `/mydata/s4/r15-w5` = 1.8 GB (`cassandra/` 444 MB, `cassandra-iv/` 433 MB,
  `cassandra-ivb/` 437 MB, `runs/` 478 MB, no `.hprof` left); all 29 run directories complete (driver `END …` and `done`
  lines, summaries). **Reused:** both builds, the harness, all 29 runs and their summaries/dump analyses. **Redone:**
  nothing. Added after resumption: the excerpts of `T4-2`, `T4-3`, `D1` and `logs/D1/trigger-eventloop-stacks.txt`.
- **Amendment 2 (2026-11-20 21:30 ET; clock only, the design stays frozen).** By the coordinator's instruction the time
  plan of §2.9 is shifted by the interruption: hard end 17:30 → **03:30 ET 2026-11-21**; the condition-B start rule
  "by 15:00" → "by 00:30 ET"; last run start and drop order shifted the same way and otherwise unchanged. It had no effect
  on any reading: all runs had already been completed in the original window (condition B started 12:15 ET, before the
  original 15:00 rule), and no run was started after the resumption.

### 3.1 Environment and configuration (as run)

- Stage 2 session 2026-11-20 10:41 ET (freeze hash re-checked: `29179745…9b6a`, matches). Node `pc82`
  (`node1.jason92-326665`, x86_64, 40 cores, 125 GiB, kernel 5.15.0-203, swap 8 GiB present and `MemorySwapMax=0` per
  scope, no `MemoryMax`), OpenJDK 11.0.33. Before the first run: no Java process, ports 7000/7199/9042 free, load 0.00,
  `/mydata` 714 GiB free; only `/mydata/s4/cassandra-base` present. One run at a time; client on the same node. Node
  clock MST (ET − 2 h); `system.log` UTC.
- Work dir **`pc82:/mydata/s4/r15-w5/`** (as §2.5): `cassandra/` (copy of `cassandra-base`, jar md5 `c560848c…`),
  `cassandra-iv/` (U6's `iv.patch` applied as §2.8, saved as `harness/iv.diff`; `ant jar` rc 0 in 15 s; `isEmpty` count
  base 1 → iv 3; jar `97bc7c23…`), `cassandra-ivb/` (`harness/ivb.patch` = §2.8 `checkMarkerCount()` in all five
  `new*BindVariables`, saved as `harness/ivb.diff`; `ant jar` rc 0 in 19 s, `gen-cql3-grammar` re-ran ("Building
  Grammar …/Cql.g"), `Cql_Parser.java` regenerated 08:43:25 MST, `checkMarkerCount` in `Cql_Parser` 1 (base 0); jar
  `fe139e44…`). Build logs: `logs/build-iv.log`, `logs/build-ivb.log`.
- Conf md5 in every run (`logs/<run>/conf-md5.txt`): `cassandra.yaml 714ee9bf…`, `jvm11-server.options fbad82a8…`,
  `cassandra-env.sh 8be0588e…`, `jvm-server.options 26a957bf…` = shipped (§2.3). Resolved from the JVM line and JMX:
  `MaxDirectMemorySize=15872M` at every heap; G1 `G1HeapRegionSize=16m`, **`ParallelGCThreads=40`, `ConcGCThreads=40`**
  (set by the shipped `cassandra-env.sh` from the core count; §2.3 had expected the JVM's own 28/7); in-flight limits
  2 GiB → 214,748,364 / 53,687,091 B, 4 GiB → 429,496,729 / 107,374,182 B, 8 GiB → 858,993,459 / 214,748,364 B (as §2.3);
  frame 16 MiB, NTR threads 128.
- Harness `harness/` (built from U6's): `client.py` (payloads as U6, keyspace `r15`, CM length 16,777,202; new
  `--trig-n`, `--trig-at none|gc:<gc.log>:<heap MiB>|fixed:<s>`, `--trig-max`, `--min-resp`; trigger connections opened
  and STARTed before load start; load start = last load connection's first send; detector = three consecutive `Pause
  Full` lines with after-size ≥ 0.95 × heap → t_trig = t_det + 30 s, ≥ +30 s, ≤ t_max), `run.sh` (args `<run-id> <build>
  <heap> <payload> <N> <k> <trig-spec> <hold-after-trigger> [len] [t_max]`; `fixedfrom:<T-run>` reads T-k's t_trig
  offset; logs "OOM line seen" at 1-s resolution), `series.sh` (16:40 ET guard; `SKIPIF-SURVIVED`/`SKIPIF-OOM` blocks for
  the frozen skip rules), `monitor.sh` (U6's; diag mode see Amendment 1), `trigsum.py` (trigger offsets, region counts
  per Full GC from the `heap*=trace` lines: free regions = heap regions − (eden + survivor + old + humongous) after GC),
  U6's `summarize.py`, `stw.py`, `gctl.py`, `threadcount.py`, `Jmx.java`, `hprof-histo.py`, `hprof_oome_thread.py`;
  run lists `list-s0.txt`, `list-main.txt`, `list-b.txt`, `list-c.txt`, `list-d.txt`, chained by `after-main.sh`.
  `client.py --sizes`: H/C query 16,777,200 B, body 16,777,207 B, frame 16,777,216 B; M query 16,777,202 B (8,388,585
  markers), body 16,777,206 B, frame 16,777,215 B; CM the same sizes.
- From `S0`: T_lex(16 MiB) = 16 × 3.60 s = **57.6 s** ⇒ t_max = max(300, 4 × 57.6) = **300 s**; condition-B hold =
  max(180, 3 × 16 × 0.589 + 60 = 88) = **180 s**.
- Full logs: `pc82:/mydata/s4/r15-w5/runs/<run>/`; excerpts: `logs/<run>/` (summary incl. trigger summary, driver,
  trigger, GC windows, client tail, completions head, JMX excerpt, thread counts, dump record, OOME thread, histogram).

### 3.2 Runs and readings (times ET; "after-GC" = heap after GC from `gc.log`; offsets from load start)

**Shakedown and trigger attribution**

| Run | Build / heap / load / k / trigger | Endpoint | Readings |
|---|---|---|---|
| `S0` 10:46 | base / 2G / H, C, M, CM at 1 MiB, ×1, 2× each | hold (shakedown) | H: `0x2000 line 1:0 no viable alternative at character '#'`, 3,715 / 3,485 ms ⇒ **τ ≈ 3.4 µs per character** (U6 m400: 11.0); C: one EOF `0x2000`, 16 / 14 ms; CM: EOF `0x2000`, 32 / 20 ms; M: `0x2200 Too many markers(?). 524272 markers exceed the allowed maximum of 65535`, 673 / 505 ms. Thread dump during H: the NTR thread in `CqlLexer.mTokens` ← `Lexer.nextToken` ← `BufferedTokenStream.fetch` ← `Cql_Parser.cqlStatement` ← `CQLFragmentParser.parseAnyUnhandled`; 3 `epollEventLoopGroup` threads at that moment (Netty starts loops lazily). Idle live histogram 16 MB `byte[]`. |
| `S0iv` 10:48 | iv / 2G / H 1 MiB | hold | the same first message; 3,391 / 2,817 ms (τ_iv ≈ base). |
| `S0ivb` 10:49 | ivb / 2G / M 1 MiB | hold | `0x2200 Too many markers(?). More than 65535 markers (R15 intervention: checked during the parse)`, **201 / 143 ms** (base M 673 / 505 ms). |
| `S1` 10:51 | base / 2G / H × 2 / 0 (detector only) / hold t_trig(no send) + 150 s | **GC service loss, no OOM** | t_det **+99.7 s** (Full GCs 2,024→1,952, 2,000→1,956, 1,972→1,956 MiB); 199 Full GCs (1.1–2.0 s each), after-GC settles at **1,998 MiB**, region counts after each late Full GC: Humongous 10, Old 117 ⇒ **1 free region**; ≥ 90 % STW from +98 s, 233 of 280 window ends, span 244 s; 0 responses; K 33,554,414 B (0.63 C_IP), paused 0; RssAnon 2,886 MiB. |

**Condition A — V-runs at 2 GiB (shipped conf, H × 2 or C × 2, k = 1)**

| Run | Trigger | Endpoint | Readings |
|---|---|---|---|
| `T2-1` 10:58 | `gc:` t_det +86.2 s, **t_trig +116.2 s** | **hold, no OOM** (row A3); daemon `kill -9` 60 s after hold end | Last Full GCs before the trigger: after 1,992 / 1,994 / 1,997 MiB, **free regions 2 / 2 / 1** (Humongous 10). After the trigger: 316 GCs in the 180-s hold, **none with cause `G1 Humongous Allocation`**, Humongous regions stay **10**, every Full GC frees one region (2,013 → 1,997 MiB); server `RequestsSize` stays **33,554,414 B** (the trigger request was never decoded/admitted, `checkLimits` runs after decode), **no response to the trigger** in 180 s, 0 load responses; ≥ 90 % STW from +94 s, 261/305 window ends, span 263 s; NTR threads ≤ 2 (lexers); direct 48 MiB; RssAnon 2,892 MiB. |
| `C2-1` 11:05 | `fixed:` +116.2 s (sent +116.4 s) | hold | trigger answered in **179 ms** (`0x2000` EOF); 4,359 load responses `0x2000`, 115–234 ms; after-GC max 946 MiB; STW ≤ 1 %; K ≤ 33,554,414 B. |
| `I2-1` 11:12 | `fixed:` +116.2 s | hold | trigger answered in **187 ms**; 12 load responses (6 per connection), all `0x2000 line 1:0 no viable alternative at character '#'`, latency 46.0–53.1 s; after-GC max 554 MiB; STW ≤ 1 %. |
| `T2-2` 11:18 | t_det +92.7 s, **t_trig +122.8 s** | **hold, no OOM** (A3) | free regions before the trigger 1 (Humongous 10, after 1,997 MiB); after it 314 GCs, no humongous-allocation GC, Humongous 10, K 33,554,414 B, no trigger response, 0 responses; ≥ 90 % STW from +98 s, span 266 s. |
| `C2-2` 11:25 | `fixed:` +122.8 s | hold | trigger 221 ms; 4,539 load responses (119–250 ms); after-GC max 888 MiB; STW ≤ 1 %. |
| `I2-2` 11:31 | `fixed:` +122.8 s | hold | trigger 173 ms; 12 load responses (6 per connection, same first message, 46.8–52.4 s); after-GC max 841 MiB; STW ≤ 1 %. |
| `T2-3` 11:38 | t_det +97.7 s, **t_trig +127.8 s** | **hold, no OOM** (A3) | free regions before the trigger 1 (after 1,997 MiB); after it 312 GCs, no humongous-allocation GC, Humongous 10, K 33,554,414 B, no trigger response; ≥ 90 % STW from +98 s, span 270 s. |
| `C2-3` 11:45 | `fixed:` +127.8 s | hold | trigger 177 ms; 4,595 load responses (118–218 ms); after-GC max 1,111 MiB; STW ≤ 1 %. |
| `I2-3` 11:52 | `fixed:` +127.8 s | hold | trigger 158 ms; 12 load responses (43.5–51.8 s); after-GC max 560 MiB; STW ≤ 1 %. |

**Condition A — budget search (H × N, k = 3, `gc:` rule)**

| Run | Trigger | Endpoint | Readings |
|---|---|---|---|
| `T4-1` 11:58 | 4G, N = 3; t_det +110.8 s, **t_trig +140.8 s** | **heap OOM** `java.lang.OutOfMemoryError: Java heap space` at +153.7 s (**t_OOM − t_trig = 12.9 s**); dump, then `kill -9` by `OnOutOfMemoryError`; triggers and load see `Connection reset` | Free regions after the last three Full GCs before the trigger 1 / 3 / 4 (Humongous 15, after 3,957–3,961 MiB of 4,096); after the trigger 7 Full GCs (each 1.2–1.7 s; free regions 1–3), then `GC(190) Pause Young (Concurrent Start) (G1 Humongous Allocation)` 4,008→4,008 MiB, free 0, then the OOM. **OOME thread: `epollEventLoopGroup` event loop in `HeapCharBuffer.<init>` ← `CharBuffer.allocate` ← `CBUtil.decodeString:107` ← `readLongString` ← `QueryMessage$1.decode:50` ← `PreV5Handlers$ProtocolDecoder.decode:289`** (a trigger's decode buffer, §2.1 step 2). Dump 5,419,719,228 B (sha256 `a5a78043…`, deleted after analysis): `byte[47..54]` 32,077,213 = 2,212.1 MB, `LinkedList$Node` 32,073,097 = 1,282.9 MB, `String` 32,161,136 = 932.7 MB ⇒ message classes **4,427.7 MB = 93.0 %** of 4,761.2 MB shallow (≈ 138 B per message; 10.7 M messages per request ≈ 64 % of each 16.78 M-character lex); `ErrorCollector` 3; `char[]` ≥ 1 M elements 6 = 201 MB. K_server 50,331,621 B (3 load requests; 0.47 C_IP), paused 0 ⇒ **U/K ≈ 4,428 / 50.3 ≈ 88**. ≥ 90 % STW from +108 s; RssAnon 5,017 MiB. |
| `T8-1` 12:05 | 8G, N = 6; t_det +153.5 s, **t_trig +183.5 s** | **hold, no OOM** (300-s hold; skip rule ⇒ `T16-1`, `T31-1` not run) | Before the trigger the Full GCs left 1–10 free regions (Humongous 30, after 7,797–7,811 MiB of 8,192); `GC(196) Pause Young (G1 Humongous Allocation)` at +188.5 s, then the 3 triggers were **decoded, admitted (K_server max 150,994,863 B = 9 requests, 0.70 C_IP) and answered `0x2000` after 35.2 s**; the six lexes went on: after-GC 8,113 MiB, ≥ 90 % STW from +113 s, span 431 s, 0 load responses; RssAnon 9,417 MiB. |
| `T4-2` 12:59 | 4G, N = 3; t_det +100.3 s, **t_trig +130.3 s** | **heap OOM** at +136.6 s (**t_OOM − t_trig = 6.3 s**) | Free regions after the Full GCs around the trigger 1 / 1 / 3 / 3 / 5 (Humongous 15, after 3,974–3,980 MiB); OOME thread: event loop in `CharBuffer.allocate` ← `CBUtil.decodeString:107` ← `QueryMessage$1.decode:50` (a trigger's decode buffer), as `T4-1`. Dump 5,450,851,570 B (`0da5a9bc…`, deleted; OOME thread only, as designed). K 50,331,621 B, paused 0; RssAnon 4,950 MiB. |
| `T4-3` 13:04 | 4G, N = 3; t_det +99.3 s, **t_trig +129.3 s** | **heap OOM** at +134.7 s (**t_OOM − t_trig = 5.4 s**) | Free regions 1 / 2 / 3 / 7 before and at the trigger; `Pause Young (G1 Humongous Allocation)` twice at +130.8–130.9 s, then the OOM; OOME thread as `T4-2` (trigger decode buffer). Dump 5,426,463,206 B (`3d83adc2…`, deleted). K 50,331,621 B; RssAnon 4,955 MiB. |

**Diagnostic (Amendment 1; not a V-run)**

| Run | Build / heap / load / k / trigger | Endpoint | Readings |
|---|---|---|---|
| `D1` 13:08 | base / 2G / H × 2 / 1 / `gc:`, hold after trigger 1,800 s, full thread dumps every 10 s | **heap OOM** at +341.9 s, **t_OOM − t_trig = 219.7 s** (t_det +92.2 s, t_trig +122.3 s) | Up to the trigger's decode the run reads as `T2-*` (free regions 1 before the trigger, Humongous 10, every Full GC 2,013 → 1,997 MiB, K 33,554,414 B, ≥ 90 % STW from +98 s). **Where the trigger was:** in all 21 dumps from +128 s to +333 s the trigger connection's event loop (`epollEventLoopGroup-5-2`) is RUNNABLE **still receiving the 16-MiB frame** (`Socket.recvAddress` ← `doReadBytes`, `PooledByteBufAllocator.newDirectBuffer`, `Unsafe.copyMemory` ← `ByteToMessageDecoder` cumulation, `Envelope$Decoder.decode`); its CPU time grows only from 30 ms to 107 ms in those 205 s (the ≥ 90 % STW leaves the event loop a few ms per second), `logs/D1/trigger-eventloop-stacks.txt`. Once the frame was complete: `GC(489) Pause Young (G1 Humongous Allocation)`, `GC(490)`, `GC(491) Pause Full (G1 Humongous Allocation)` 1,999 → 1,999 MiB, then **`OutOfMemoryError: Java heap space` in the event loop at `CharBuffer.allocate` ← `CBUtil.decodeString:107` ← `QueryMessage$1.decode:50`** (the trigger's decode buffer), dump, `kill -9`. Dump 2,712,049,619 B (`d8de09d0…`, deleted): `byte[47..54]` 15,552,217 = 1,070.9 MB, `LinkedList$Node` 15,548,104 = 621.9 MB, `String` 15,636,191 = 453.4 MB ⇒ message classes **2,146.2 MB = 90.0 %** of 2,384.1 MB shallow (≈ 138 B per message, 7.8 M per request ≈ 46 % of each lex); `ErrorCollector` 2, `NoViableAltException` 2 ⇒ **U/K ≈ 2,146 / 33.55 ≈ 64**. |

**Condition B — V-runs at 2 GiB (PREPARE, N = 3, no trigger, hold 180 s)**

| Run | Endpoint | Readings |
|---|---|---|
| `TB2-1` 12:15 | **heap OOM** at **+6.8 s** | OOME thread: `ArrayList.grow` ← `ArrayList.add` ← **`Cql_Parser.newBindVariables:306`** (the `bindVariables` list) ← `Cql_Parser.value` ← `simpleTerm` (during the parse, before prepare and the 65,535 check). Dump 2,867,294,137 B (`ad425ec3…`, deleted): `CommonToken` 24,813,087 = 1,488.8 MB, `Object[]` ≥ 1 M elements 9 = 433.4 MB (token and marker lists), `AbstractMarker$Raw` 12,406,516 = 248.1 MB ⇒ **2,170 MB = 86 %** of 2,515.3 MB shallow; `ErrorCollector` 3; message-size `byte[]` 4,751 (no lexer messages). K 50,331,618 B (0.94 C_IP), paused 0 ⇒ U/K ≈ 43. Clients: `Connection reset` at +30.3 s (after the 3-GB dump). |
| `CB2-1` 12:18 | hold | 2,550 responses `0x2000` (EOF), 181–388 ms; after-GC max 532 MiB; STW ≤ 1 %. |
| `IB2-1` 12:23 | hold | 2,732 responses `0x2200 Too many markers(?). More than 65535 markers (R15 intervention: checked during the parse)`, 168–807 ms; after-GC max 538 MiB; STW ≤ 1 %. |
| `TB2-2` 12:27 | **heap OOM** at **+7.8 s** | OOME thread `ArrayList.grow` ← `Cql_Parser.singleColumnInValues:16394` ← `relation` (the IN-value list); dump 2,868,278,631 B (`215a5c71…`, deleted). K 50,331,618 B. |
| `CB2-2` 12:29 | hold | 2,560 responses `0x2000`, 188–319 ms; after-GC max 1,100 MiB; STW ≤ 1 %. |
| `IB2-2` 12:34 | hold | 2,692 responses `0x2200` (intervention text), 164–812 ms; after-GC max 538 MiB. |
| `TB2-3` 12:38 | **heap OOM** at **+8.9 s** | OOME thread as `TB2-2` (`singleColumnInValues:16394`); dump 2,895,536,157 B (`5c443fb4…`, deleted). K_client 50,331,618 B (the 5-s JMX poller took no sample before the OOM). |
| `CB2-3` 12:40 | hold | 2,514 responses `0x2000`, 188–368 ms; after-GC max 539 MiB. |
| `IB2-3` 12:44 | hold | 2,725 responses `0x2200` (intervention text), 166–843 ms; after-GC max 509 MiB. |
**Condition B — budget search (no `TB16` in the frozen table)**

| Run | Heap / N | Endpoint | Readings |
|---|---|---|---|
| `TB4-1` 12:48 | 4G / M × 6 (hold 240 s) | **heap OOM** at **+8.9 s** | OOME thread `ArrayList.grow` ← **`BufferedTokenStream.fetch:146`** ← `sync` (the token buffer). Dump 5,732,464,092 B (`dd81f6c4…`, deleted): `CommonToken` 49,989,475 = 2,999.4 MB, `Object[]` ≥ 1 M 18 = 933.6 MB, `AbstractMarker$Raw` 24,994,681 = 499.9 MB ⇒ **4,432.9 MB = 88 %** of 5,040.4 MB; `ErrorCollector` 6. K 100,663,236 B (0.94 C_IP), paused 0. RssAnon 5,060 MiB. |
| `TB8-1` 12:52 | 8G / M × 12 (hold 300 s) | **heap OOM** at **+10.0 s** | OOME thread as `TB4-1` (`BufferedTokenStream.fetch:146`). Dump 11,230,135,212 B (`15fcbfea…`, deleted): `CommonToken` 98,750,889 = 5,925.1 MB, `Object[]` ≥ 1 M 36 = 1,864.9 MB, `AbstractMarker$Raw` 49,375,331 = 987.5 MB ⇒ **8,777.5 MB = 89 %** of 9,879.6 MB; `ErrorCollector` 12. K 201,326,472 B (0.94 C_IP). RssAnon 9,463 MiB. |

### 3.3 Deviations from the frozen design

- **Extra run `D1`** (Amendment 1, diagnostic): outside the frozen table, run after all frozen runs; not a V-run.
- **Harness fixes before readings:** the first `S0` attempt (10:46 ET) aborted in preflight because `pgrep -f
  CassandraDaemon` matched the launching `ssh` shell; no daemon was started; the match was narrowed to the `java …
  org.apache.cassandra.service.CassandraDaemon` command line and `S0` re-run from a clean start. `trigsum.py` (analysis
  only) failed on the `-0700` offset after `S1` and was fixed and re-run on `S1`. `series.sh` gained `SKIPIF-OOM` and
  `run.sh` MiB heaps during the series (both replaced atomically by `mv`; no running script was edited; neither changed
  a run already started; neither was exercised: `T16-1`/`T31-1` were skipped).
- **Detector reading of the rule:** "three consecutive `Pause Full` lines" was implemented as three consecutive Full-GC
  lines (young pauses in between ignored), each with after-size ≥ 0.95 × heap. `S1` (k = 0) ran its hold as
  t_det + 30 s + 150 s = t_det + 180 s, as designed.
- **Resolved GC threads:** `ParallelGCThreads=40`, `ConcGCThreads=40` (from the shipped `cassandra-env.sh`), not the
  28 / 7 named in §2.3; conf unchanged (md5 as shipped).
- **Predictions missed (no effect on outcome rows):** S0 τ ≈ 3.4 µs (inside 2–7 µs); T_lex at 16 MiB under load
  43.5–53.1 s (I2). C2 after-GC peaks 888–1,111 MiB and I2 up to 841 MiB (predicted ≤ 0.5 GiB), `CB2-2` 1,100 MiB
  (≤ 0.6 GiB), with STW ≤ 2 % in all of them. `TB*` OOM at +6.8–10.0 s (predicted ≤ 70 s; x86 is faster than U6's m400).
  `T2-*`: the trigger was not decoded within the 180-s hold (row A3), whereas §2.7 predicted OOM ≤ 60 s after it; `D1`
  shows why (the 16-MiB trigger frame took ≈ 218 s to be received under ≥ 90 % STW).
- **Missing samples:** `TB2-3` server `RequestsSize` has no sample before the OOM (5-s JMX poll, OOM at +8.9 s); K from
  the client (50,331,618 B). JMX samples also stop during deep thrash in T2/T8 (the poller JVM times out); K values are
  the last samples and the client's. `T8-1` `gc.log` rotated through 10 files of 10 MB (earliest lines lost; the
  region counts around the trigger are intact).
- **Order and skips:** as §2.5. `T8-1` survived ⇒ `T16-1` and `T31-1` not run (frozen skip rule); the largest failing A
  budget is 4 GiB ⇒ `T<max>-2/-3` = `T4-2`, `T4-3`. `TB4-1` failed ⇒ `TB8-1` run (failed). Nothing dropped. Timing:
  started 10:41 ET (plan 12:00); last run ended 13:16:53 ET.

## 4. Conclusion (stage 2)

### 4.1 Verdicts

| Condition | Verdict | Protocol status (detail) | Outcome row |
|---|---|---|---|
| **A** — `ErrorCollector.errorMsgs` (OC-409, OC-410) + one more 16-MiB request | **retry** | at 2 GiB: `verified-gap · service-loss · deployment` (as U6, now on x86); OOM at 2 GiB 0/3 within the frozen hold; at 4 GiB **heap OOM 3/3** (`T4-1..3`) without a matched control or intervention at 4 GiB ⇒ `candidate` for the OOM endpoint | **A3** (T2 survives; the trigger stays queued) |
| **B** — PREPARE token/marker buffering before the 65,535 check (OC-278, OC-285) | **true positive** | **`verified-OOM · deployment`** (unprotected accumulation; the marker-count protocol limit is applied after the allocation); largest tested failing budget 8 GiB (1/1; 4 GiB 1/1; 2 GiB 3/3) | **B1** |

**Condition A reason.** The frozen V-runs did not reach the endpoint: at 2 GiB the two `#` QUERYs fill the heap with
lexer messages (after-GC 1,997 MiB of 2,048, **1 free region**, Humongous 10, ≥ 90 % STW from ≈ +95 s, U/K ≈ 64 in
`D1`), but in `T2-1..3` the trigger request produced no humongous allocation in the 180-s hold after it (K stayed
33,554,414 B, no `G1 Humongous Allocation` GC, no response), so OOM 0/3 while the matched control `C2-1..3` (trigger
answered in 177–221 ms, ≈ 4,500 responses, after-GC ≤ 1,111 MiB) and the keep-first-message intervention `I2-1..3`
(trigger 158–187 ms, 6 responses per connection, after-GC ≤ 841 MiB) survive as planned. The diagnostic `D1` (identical,
1,800-s hold) shows that the frozen hold was simply too short: under ≥ 90 % STW the trigger connection's event loop needs
≈ 218 s to receive the 16-MiB frame (its CPU time grows 30 → 107 ms in 205 s); once the frame is complete its decode
buffer (`CBUtil.decodeString` → `CharBuffer.allocate`, 2 regions) fails after two `G1 Humongous Allocation` Full GCs and
the node dies with `OutOfMemoryError: Java heap space` **219.7 s after the trigger**, message classes 90 % of the dump.
At 4 GiB (3 load + 3 trigger connections) the same failure comes 5.4–12.9 s after the trigger, **3/3** (`T4-1..3`), the
OOME thread is the trigger's decode buffer every time, and `T4-1`'s dump holds 32.1 M messages = 4,428 MB = **93 %**
(U/K ≈ 88). At 8 GiB (6 + 3) the triggers found free regions after a humongous-allocation GC and were answered after
35 s; the thrash went on (after-GC 8,113 MiB of 8,192, ≥ 90 % STW for 431 s) without OOM in the 300-s hold. The mechanism
and the endpoint are therefore shown (2 GiB 1/1 diagnostic, 4 GiB 3/3), but no single condition has V1 + V2 + V4
together: the 2-GiB V-set ended in row A3 and the 4-GiB OOMs have no 4-GiB control or intervention. By the playbook this
is a retry.

**Condition A: what a better design should change.** Either (a) keep 2 GiB and set the post-trigger hold from `D1`:
≥ 600 s (the trigger frame takes ≈ 220 s to arrive under the thrash), with `C2`/`I2` holding the same time; or, better,
(b) run the V-set at **4 GiB** with the `T4` workload (H × 3, k = 3, `gc:` rule) — `T4` already failed 3/3 within 13 s of
the trigger — adding `C4-1..3` (C × 3 + the same 3 triggers at T4-k's offset) and `I4-1..3` (iv build, H × 3, same
triggers), then the 8-GiB budget with a ≥ 600-s post-trigger hold. Sending the trigger frame before the heap fills
(so only its decode waits) would also remove the receive delay. Expect the true-positive shape "retained per-item
diagnostics + one ordinary humongous request turns GC thrash into OOM".

### 4.2 V1–V7

| | Condition A (2 GiB V-set) | Condition B |
|---|---|---|
| V1 Repetition | `T2-1..3`: OOM **0/3** in the frozen hold (service loss 3/3, span 263–270 s); OOM 3/3 only at 4 GiB (`T4-1..3`), 1/1 at 2 GiB in diagnostic `D1` | `TB2-1..3`: heap OOM **3/3** at +6.8 / 7.8 / 8.9 s |
| V2 Matched control | `C2-1..3` 0/3 (same bytes, frame, K, the same trigger at the same offset) — none at 4 GiB | `CB2-1..3` 0/3 (comment PREPARE of equal length; 2,514–2,560 responses; after-GC ≤ 1,100 MiB) |
| V3 Measurement | U from `gc.log` (after-GC, region counts) and dumps (`D1` 2,146 MB = 90 %, `T4-1` 4,428 MB = 93 %) vs K = `RequestsSize` 33.55 / 50.33 MB, paused 0 | U from the `TB2-1` dump (`CommonToken` + `Object[]` + `AbstractMarker$Raw` = 2,170 MB = 86 %) vs K 50.33 MB (0.94 C_IP), paused 0 |
| V4 Intervention | `I2-1..3` 0/3 (keep only the thrown message; same answer to clients) — none at 4 GiB | `IB2-1..3` 0/3: the existing 65,535 bound applied during the parse; every request answered `0x2200` in 164–843 ms (base: an OOM) |
| V5 Initiating failure | not reached in the V-set; `T4-*`/`D1`: OOME thread = trigger event loop in `CharBuffer.allocate` ← `CBUtil.decodeString:107`; histogram as V3 | OOME thread in the parse: `ArrayList.grow` ← `Cql_Parser.newBindVariables:306` (`TB2-1`) / `singleColumnInValues:16394` (`TB2-2`, `-3`) / `BufferedTokenStream.fetch:146` (`TB4-1`, `TB8-1`); histogram as V3 |
| V6 Default constraints | shipped conf (md5), limits at defaults resolved from JMX | same |
| V7 Acceptable budget | 2 GiB (ideal), direct auto 15,872 MiB, no container limit | 2 GiB; also 4 GiB and 8 GiB (1/1 each); largest tested failing budget **8 GiB** (no larger B run in the frozen table) |

**Condition B reason.** A single PREPARE of `SELECT v FROM r15.t WHERE k IN (?,…,?)` with 8,388,585 markers fits the
16-MiB frame and the per-IP in-flight limit; the parser buffers ≈ 16.8 M `CommonToken`s (≈ 60 B each), their list arrays
and ≈ 8.4 M `AbstractMarker$Raw` before the 65,535-marker check that runs only after `parseAndPrepare`. Three such
requests from one client (K = 0.94 of the per-IP limit, nothing paused) end in `OutOfMemoryError: Java heap space` in
the parse 3/3 at 2 GiB within 9 s, with the token/marker classes 86 % of the dump (U/K ≈ 43); six at 4 GiB and twelve at
8 GiB fail the same way (88 % / 89 % of the dump). The equal-length comment PREPARE survives 3/3 and applying the same
65,535 bound during the parse removes the failure 3/3 while giving clients the same error class. Shape covered by
**CP-11** (check after the allocation; here the count check follows the parse that allocates per marker), with CP-2
(the limit counts markers, not the parse memory); no new pattern needed.

**Limits of attribution.** Client and server on one node (x86, 40 cores); one client IP; protocol v4. A's 4-GiB result
and `D1` are not V-sets; the trigger is the ordinary decode of a 16-MiB QUERY, and A's dumps show that the heap was
held by the lexer messages, not by the trigger. B's budget search stops at 8 GiB by the frozen table (the node's own
31,744 MiB heap was not tried for B); B's OOME frames vary between the marker list, the IN-value list and the token
buffer — all parse-time holders of the same request.
