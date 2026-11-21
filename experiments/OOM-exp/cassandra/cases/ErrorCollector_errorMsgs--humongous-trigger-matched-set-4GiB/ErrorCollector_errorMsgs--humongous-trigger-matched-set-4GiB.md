# R20 (retry of R15 condition A / U6) — ErrorCollector.errorMsgs: the humongous trigger during the lexer-message GC thrash, as a matched set at 4 GiB  <!-- file: cassandra/cases/ErrorCollector_errorMsgs--humongous-trigger-matched-set-4GiB/ErrorCollector_errorMsgs--humongous-trigger-matched-set-4GiB.md -->

| Field | Value |
|---|---|
| Case ID | `R20` (a new attempt at `R15` condition A, itself a retry of `U6`; README "ID prefixes") |
| From | retry-list row `R15` condition A (retry of U6; OC-409, OC-410) |
| Phase-1 case file | [`no_constraint-istokenvalid-token_position--autonomous`](../../../../capacity-enforcement-exp/cassandra/stage3-ai-deep-read/cases/no_constraint-istokenvalid-token_position--autonomous.md) (OC-409, OC-410; no stage 4) |
| System / pinned source | Cassandra 5.0.9 (`systems/cassandra/source/`, `build.xml` `base.version` 5.0.9); built tree `pc82:/mydata/s4/cassandra-base` (**x86_64**, jar md5 `c560848c…`); OpenJDK 11.0.33 |
| Stage 1 (design) | OOM-agent stage-1 session, 2026-11-21 01:50–02:50 America/New_York |
| Stage 2 (verify) | fresh OOM-agent session, 2026-11-21 01:59–≈ 04:15 ET on `pc82` (runs 02:02–03:59 ET) |
| Verdict | **`true positive`** — `verified-OOM · deployment` (4 GiB V-set; largest failing budget 16 GiB 1/1, 8 GiB 3/3) |

## Summary

- **Hypothesis under test (stage 1):** R15 showed the mechanism and the endpoint but never in one matched condition:
  at 4 GiB three 16 MiB `#` QUERYs fill the heap with retained lexer messages (`ErrorCollector.errorMsgs`, ≈ 138 B
  per character, 93 % of the dump) and three ordinary 16 MiB QUERYs sent ≈ 30 s into the GC thrash fail their
  humongous decode buffer (`CBUtil.decodeString` → `CharBuffer.allocate`): heap OOM 3/3, 5.4–12.9 s after the trigger.
  At 2 GiB the same trigger frame took ≈ 218 s just to be received, so the 180-s hold missed it. R20 runs that 4 GiB
  workload as a full matched set — `T4` ×3, comment-payload control `C4` ×3 and keep-first-message intervention `I4`
  ×3 with the identical trigger at the identical offset — then searches the budget upward (8 GiB with a ≥ 600 s
  post-trigger hold and a second, pre-sent trigger wave at heap saturation), plus one 2 GiB diagnostic with the
  trigger frame pre-sent before the heap fills.
- **Predicted:** `T4` heap OOM 3/3 ≤ 60 s after the trigger, `C4` and `I4` survive 3/3 ⇒ `verified-OOM · deployment`
  (4 GiB ≥ 512 MiB, every capacity at its shipped default).
- **Conclusion (stage 2): true positive, `verified-OOM · deployment`.** At 4 GiB with shipped defaults, three 16-MiB
  `#` QUERYs plus three ordinary 16-MiB QUERYs from one client end in `OutOfMemoryError: Java heap space` 3/3
  (4.3–17.9 s after the ordinary requests); the equal-length comment load with the same three requests survives 3/3
  and the keep-first-message build survives 3/3. The workload scaled with the heap fails 3/3 at 8 GiB (H × 6), 1/1 at
  16 GiB (H × 12; there the ordinary requests' last byte arrived late) and 1/1 at 2 GiB (H × 2, same late-last-byte
  form, diagnostic).
- **Root cause:** the CQL lexer reports every unmatched character and `ErrorCollector` keeps each message in an
  unbounded `LinkedList` (≈ 138 B per character, ≈ 2.2 GB per 16-MiB query) although only the first is ever used;
  no control covers it (the in-flight reserve counts the 16.8-MB wire body, U/K 64–88). The retained messages leave
  1–6 free heap regions, and the next large request's 32-MiB decode buffer (or parse copy) cannot get contiguous
  regions, so G1 throws instead of thrashing forever.

## 1. Candidate

### 1.1 The retry row (quoted from `phase2-retry-list.md`, row R15; link re-pointed to this folder's sibling)

| Case | Verdict date | Why retry (what was shown, what was missing) | What a better design should change | Status |
|---|---|---|---|---|
| [R15](../ErrorCollector_errorMsgs--humongous-request-during-gc-thrash/ErrorCollector_errorMsgs--humongous-request-during-gc-thrash.md) condition A (retry of U6; OC-409/410) | 2026-11-20 | pc82 x86, defaults. At 2 GiB two 16 MiB `#` QUERYs refill the heap (1,997/2,048 MiB after GC, STW ≥ 90 % from ≈ +95 s), but the trigger's event loop needs ≈ 218 s to receive its 16 MiB frame under the thrash, so OOM 0/3 within the frozen 180 s hold (`verified-gap · service-loss`); C2 and I2 survived 3/3. D1 (1,800 s hold) OOMed at 219.7 s in `CBUtil.decodeString`. At 4 GiB (3 load + 3 trigger connections) OOM 3/3 5.4–12.9 s after the trigger (messages 93 % of the dump, ≈ 88× counted) but no control or intervention ran at 4 GiB; 8 GiB: no OOM | Run the full set at 4 GiB with the T4 workload (already 3/3): C4 ×3 (comment payload, same trigger offset) and I4 ×3 (iv build), then an 8 GiB budget run with a ≥ 600 s post-trigger hold; or stay at 2 GiB with a ≥ 600 s hold for T, C and I; or send the trigger frame before the heap fills to remove the receive delay | picked again: R20 (2026-11-21) |

Condition B of R15 (PREPARE of 8.39 M markers, OC-278/285) is already a **true positive** (`verified-OOM · deployment`)
and is **not** part of this case.

### 1.2 Earlier cases and verdicts

- **U6** ([case](../ErrorCollector_errorMsgs--one-message-per-bad-character/ErrorCollector_errorMsgs--one-message-per-bad-character.md);
  `ms0604`, aarch64, 2026-11-18): **retry**, `verified-gap · service-loss · deployment`. Two 16 MiB `#` QUERYs from one IP
  at 2 GiB: after-GC 2,009–2,017 MiB of 2,048, ≥ 90 % STW for ≈ 200 s, OOM 0/3 (also 0/1 at 4 GiB in 430 s and over a
  1,200-s hold); messages ≈ 123 B each, 92 % of the heap, U/K ≈ 58; comment control and keep-first-message
  intervention 0/3. Why no OOM: the lexers allocate only small objects and each Full GC frees about one region of their
  garbage; G1 has no GC-overhead limit.
- **R15** ([case](../ErrorCollector_errorMsgs--humongous-request-during-gc-thrash/ErrorCollector_errorMsgs--humongous-request-during-gc-thrash.md);
  `pc82`, x86_64, 2026-11-20): condition **A retry** (outcome row A3), condition B true positive. The condition-A
  readings this design builds on (R15 §3.2, §4.1):
  - `S0`: τ ≈ 3.4 µs per `#` ⇒ T_lex(16 MiB) = 57.6 s alone, 43.5–53.1 s per response under the two-connection `I2`
    load; t_max of the detector = max(300, 4 × 57.6) = 300 s.
  - `S1` (2 GiB, no trigger): t_det +99.7 s, after-GC settles at 1,998 MiB, **1 free region** (Humongous 10, Old 117),
    ≥ 90 % STW from +98 s, no OOM.
  - `T2-1..3` (2 GiB, H × 2, one trigger by the `gc:` rule at +116–128 s): **no OOM in the 180-s hold**; the trigger
    was never decoded (K stayed 33,554,414 B, no `G1 Humongous Allocation` GC). `C2-1..3` (comment load, same trigger):
    trigger answered in 177–221 ms, 4,359–4,595 responses, after-GC ≤ 1,111 MiB, STW ≤ 1 %. `I2-1..3` (iv build):
    trigger 158–187 ms, 6 responses per connection (43.5–53.1 s each), after-GC ≤ 841 MiB.
  - `D1` (diagnostic, T2 with an 1,800-s hold, full thread dumps): the trigger connection's event loop stayed RUNNABLE
    **receiving the 16-MiB frame** for ≈ 205 s (its CPU time 30 → 107 ms; ≥ 90 % STW leaves it a few ms per second);
    once complete, `Pause Full (G1 Humongous Allocation)` 1,999 → 1,999 MiB and **heap OOM 219.7 s after the trigger** in
    the event loop at `CharBuffer.allocate` ← `CBUtil.decodeString:107` ← `QueryMessage$1.decode:50`; messages 2,146 MB
    = 90 % of the dump, U/K ≈ 64.
  - **`T4-1..3`** (4 GiB, H × 3, k = 3 triggers by the `gc:` rule: t_det +100–111 s, t_trig +129–141 s): **heap OOM
    3/3**, t_OOM − t_trig = 12.9 / 6.3 / 5.4 s; free regions just before the trigger 1–7 (Humongous 15, after-GC
    3,957–3,980 MiB of 4,096); OOME thread every time = a trigger's event loop in `CharBuffer.allocate` ←
    `CBUtil.decodeString:107`; `T4-1` dump 5.42 GB written in 30.8 s: `byte[47..54]` + `LinkedList$Node` + `String`
    = 4,427.7 MB = **93.0 %** of 4,761 MB shallow, 32.1 M messages (≈ 138 B each, ≈ 64 % of each lex), `ErrorCollector`
    3, K_server 50,331,621 B (the triggers were not yet admitted), U/K ≈ 88. **No C4 or I4 ran.**
  - `T8-1` (8 GiB, H × 6, k = 3): the 0.95 × heap rule fired at after-GC 7,785 MiB (≈ 407 MiB = 25 regions free), the
    triggers got their regions through `Pause Young (G1 Humongous Allocation)` and were answered after 35.2 s; the thrash
    went on (after-GC 8,113 MiB, ≥ 90 % STW for 431 s) without OOM in the 300-s hold.
  - R15's run directory `pc82:/mydata/s4/r15-w5` has since been deleted; its harness, `iv.patch`/`iv.diff` and log
    excerpts are in R15's case folder.

### 1.3 Phase-1 case file and stage 4

- **`no_constraint-istokenvalid-token_position--autonomous`** (OC-409, OC-410; estimate `negative`; **no stage 4**):
  `isTokenValid` (`ErrorCollector.java:187-190`) only decides whether a parser error gets a snippet; its A4 notes the
  unbounded `errorMsgs` list (`ErrorCollector.java:52`) — the holder of this case. Nothing ran in phase 1. Candidate-list
  rows OC-409 and OC-410 now read `retry (R15 condition A; U6 was retry)`.

### 1.4 JIRA prior art (read only; nothing posted; re-checked 2026-11-21 01:53–01:54 ET)

- **Survey** `capacity-enforcement-exp/cassandra/stage5-oom-clue-find/jira-oom-survey.csv` (604 rows): grep for
  `humongous|ErrorCollector|lexer|syntax error|no viable|decodeString|readLongString|full gc|gc thrash|gc storm` → only
  CASSANDRA-1014, 1177, 2543, 5736 (GC storms from inserts, memtables or Hadoop reads); none on the CQL lexer, error
  messages or humongous decode buffers.
- **JIRA REST** (`issues.apache.org/jira/rest/api/2/search`, project CASSANDRA, reachable):
  - `text ~ "ErrorCollector"` → 5 (7769, 7111, 7569, 11803, 14096), as U6 and R15 found; none about the message list's
    memory.
  - `text ~ "humongous"` → 9, including **CASSANDRA-17655** "Prevent JVM Humongous allocations" (Open, 2022) and 17408
    (Not A Problem): background for the trigger (humongous allocations are a known G1 pain point), not this mechanism.
  - `text ~ "decodeString"` → **CASSANDRA-11428** "Eliminate Allocations" (fixed 2016; background for the thread-local
    decode buffer `TL_CHAR_BUFFER`, not a report of this failure), 20259 (unrelated).
  - `text ~ "no viable alternative at character" AND text ~ "memory"` → 0; `text ~ "syntax error" AND text ~
    "OutOfMemoryError"` → 0.
- **Verdict: `new`** (as U6 and R15). Not known-fixed, not documented as by design.

### 1.5 What changes from R15 (not a rerun)

R15's condition-A V-set ran at 2 GiB, where the trigger frame itself cannot be received in the hold; its only
3/3 OOM condition (4 GiB) had no control or intervention. R20 follows the row's preferred change: **the full V-set at
4 GiB with R15's `T4` workload unchanged** (H × 3, k = 3, the same `gc:` trigger rule), new `C4-1..3` and `I4-1..3`
with the identical trigger at each `T4-k`'s offset, and the C/I hold made at least as long as the window the T arm
needed. R15's `T4-1..3` are **not** reused as V1: the matched arms need their trigger offsets from the same series,
and R15's run directory is gone; they are cited as prior readings only. The budget search then takes the row's
8-GiB step with a **≥ 600-s post-trigger hold**; because R15's `T8-1` showed that the 0.95 × heap rule fires at 8 GiB
while ≈ 25 regions are still free (its triggers were simply served), the 8-GiB run adds a **second trigger wave whose
frames are pre-sent before the heap fills** (the row's third alternative) and completed at heap saturation. One 2-GiB
diagnostic (`P2-1`) tests the same pre-sent trigger at the ideal budget. The row's 2-GiB ≥ 600-s V-set is not chosen:
three triplets of ≥ 13-min runs do not fit beside the 4-GiB set in the 4.5-h window.

## 2. Design solution (stage 1; frozen)

### 2.1 Mechanism

**Direction:** unprotected accumulation + an ordinary trigger request (technique note
[`combo-playbook.md`](../../../combo-playbook.md): multiplicity → budget; the trigger is a second, ordinary consumer of the
same heap). Interpretation: suspected implementation defect (diagnostics retained but never reported); not documented
as by design.

Holder path of one `#` QUERY (U6/R15 §2.1, citations re-checked against the pinned source 2026-11-21):

1. Admission: v4 frame ≤ `native_transport_max_frame_size` 16 MiB (`Envelope.java:425-442`: a frame is decoded only when
   `buffer.readableBytes() >= totalLength`, else `return null` and the bytes stay in the channel's cumulation buffer);
   body bytes charged to the per-IP and global in-flight reserves **after decode** (`PreV5Handlers.java:151-186`;
   default non-throwing mode).
2. Decode on the Netty event-loop thread: `PreV5Handlers.ProtocolDecoder.decode` (`:277-289`) → `QueryMessage.codec.decode`
   (`QueryMessage.java:50`) → `CBUtil.readLongString` (`CBUtil.java:196-201`) → `readString` (`:118-134`) →
   `decodeString` (`:89-115`): the thread-local `CharBuffer` `TL_CHAR_BUFFER` (`:81`) of `remaining × maxCharsPerByte`
   chars is allocated if the thread has none or a smaller one (`:96-109`, `CharBuffer.allocate` at `:99`/`:107`) and
   **kept on the thread**; `dst.flip().toString()` (`:115`) copies it into a Latin-1 `String` (`byte[L]`).
3. Parse on a `Native-Transport-Requests` thread: `QueryProcessor.parseStatement` → `CQLFragmentParser.parseAnyUnhandled`
   (`CQLFragmentParser.java:63-83`): `new ErrorCollector(input)`, `new ANTLRStringStream(input)` (copies to a `char[L]`),
   lexer, parser, then `errorCollector.throwFirstSyntaxError()` (`:80`).
4. ANTLR 3.5.2 `Lexer.nextToken` reports **every** unmatched `#`; `ErrorCollector.syntaxError` (`ErrorCollector.java:69-82`)
   appends one message `line 1:<pos> no viable alternative at character '#'` to the unbounded `LinkedList<String>
   errorMsgs` (`:52`, add at `:81`); only `errorMsgs.getFirst()` is ever used (`:98-102`). All messages stay live until
   the parse throws (R15: ≈ 138 B per message on x86).

**Trigger.** With N such parses holding the heap at after-GC ≥ 97 % (R15 `T4`: 1–7 free regions of 256), G1 runs
back-to-back Full GCs that each free about one region of transient lexer garbage. A further 16 MiB QUERY of the harmless
comment payload C needs, all humongous (16 MiB regions): the decode buffer `char[16,777,200]` = 33,554,416 B
(**2 regions**, if its event loop has none), the query `String`'s `byte[16,777,200]` (**1 region**), and on its NTR
thread the `ANTLRStringStream` `char[16,777,200]` (**2 regions**). G1 allocates a humongous object only in wholly free
contiguous regions; failing that it runs Full GCs and throws `OutOfMemoryError: Java heap space`. The shipped
`-XX:+HeapDumpOnOutOfMemoryError` (`jvm-server.options:120`) and `-XX:OnOutOfMemoryError="kill -9 %p"`
(`cassandra-env.sh:209`) act on the first error in any thread. The trigger is one more admitted request from the same
client, within every limit; the control arm serves thousands of identical requests (R15 `C2`).

**Receive delay (why 2 GiB missed, R15 `D1`).** Under ≥ 90 % STW the trigger's event loop gets a few ms per second, so
receiving a 16 MiB frame (copying into a growing direct cumulation buffer) took ≈ 205–218 s at 2 GiB; at 4 GiB, where
the triggers were sent at the onset of the thrash, it took ≤ 13 s. **Pre-sent trigger (new here, `T8`/`T6`/`T16`
wave 2 and `P2-1` only):** the trigger connection sends all but the **last byte** of its frame before the heap fills
(at load start + 10 s); the frame stays undecoded in the event loop's direct cumulation buffer (`Envelope.java:441-442`,
no heap, nothing charged to K; `native_transport_idle_timeout` default 0 ms, so the idle connection is kept,
`Config.java:139`, `PipelineConfigurator.java:247-256`); at the trigger instant it sends the last byte, so the event loop
needs to read one byte and then decodes at once. This is ordinary network behavior (the tail segment of a large request
arriving late) and adds no server-side setting.

**Classification by measurement:** unprotected accumulation (`errorMsgs` has no control; the in-flight reserves count
only wire bytes, K ≤ 0.94 of the per-IP limit, U/K ≈ 60–90). The trigger does not change the direction: the claimed
holder at the OOM is still `errorMsgs` (V3/V5 by the dump histogram).

### 2.2 Protection map

| Domain | Allocation and owner (release) | Counter K / contract C at 4 GiB | Scope, multiplicity | At the limit | Covers the claimed memory? |
|---|---|---|---|---|---|
| v4 frame size | inbound cumulation `ByteBuf` (direct, Netty pool); released after decode | frame length / `native_transport_max_frame_size` 16,777,216 B | per frame | frame discarded, `ProtocolException` | wire bytes only (direct) |
| Native in-flight reserves | body bytes per decoded request, released at response | `RequestsSize` / heap/10 = 429,496,729 B; per IP heap/40 = 107,374,182 B (`DatabaseDescriptor.java:649-657`) | per node / per client IP; (N + k) × 16,777,207 B | default: force-allocate, pause the connection (`PreV5Handlers.java:178-186`) | **wire bytes only**; 6 requests = 100,663,242 B = 0.94 C_IP, no pause |
| Request concurrency | `Native-Transport-Requests` SEP pool | threads / `native_transport_max_threads` 128 | per node | queued | count only; ≤ 18 ≪ 128 |
| Decode buffer `TL_CHAR_BUFFER` | `char[capacity]` per event-loop thread (`CBUtil.java:81`, `:96-109`), kept for the thread's life | none | per event-loop thread that decoded a long string (≤ connections) | — | uncovered; 32 MiB per loop, standing; identical in every arm; **the trigger's failing allocation** |
| Query `String`, ANTLR `char[]` | `byte[L]` (1 region) + `char[L]` (2 regions) per request; released with the request | none | per request | — | uncovered, ≈ 48 MiB per request (identical in every arm) |
| **`ErrorCollector.errorMsgs`** (claimed holder) | `LinkedList<String>` per parse (`ErrorCollector.java:52`, `:81`, `:90`): `LinkedList$Node` 40 B + `String` 29 B + `byte[47..54]` ≈ 69 B per lexer error ≈ 138 B (R15 measured) | **none** | per request; one message per `#` (16.78 M per 16 MiB request) × N | none | **no control** |
| Transient lexer garbage | `NoViableAltException`, `StringBuilder`, header strings per error | none | per error | — | GC-reclaimable (what each Full GC frees) |
| Prepared cache, guardrails | — | — | — | guardrails skipped for superusers (`AllowAllAuthenticator`) | not involved (QUERY); nothing bounds query length before the parse |
| Budgets | Java heap (`-Xmx` = `-Xms`); direct `MaxDirectMemorySize` auto 15,872 MiB; no container limit | — | per process | heap OOM / direct OOM | holder is heap; frames and pre-sent partial frames are direct (≤ 18 × 32 MiB) |

### 2.3 Configuration and budget audit

- **Node `pc82`** (checked read-only 2026-11-21 01:52 ET; node clock MST = ET − 2 h): `pc82.cloudlab.umass.edu`
  (`node1.jason92-326665`), **x86_64**, 40 cores, 125 GiB RAM (122 GiB free), swap 8 GiB present (0 used), cgroup v2
  (memory controller on), OpenJDK 11.0.33, Linger=no, load 0.00, `/mydata` 753 GB with **714 GiB free**; `/mydata/s4/`
  holds only `cassandra-base` (R15's `r15-w5` deleted); no Java process; ports 7000/7199/9042 free. `cassandra-base` jar
  md5 `c560848c966e329bbfdbb143497b1b66` (= R15's base copy); conf md5 `cassandra.yaml 714ee9bf…`,
  `jvm11-server.options fbad82a8…`, `cassandra-env.sh 8be0588e…`, `jvm-server.options 26a957bf…` = shipped (= R15).
- **Shipped conf, unchanged in every arm.** Single node, `rpc_address: localhost`, port 9042, `AllowAllAuthenticator`,
  protocol v4 allowed. G1 as shipped (`G1HeapRegionSize=16m`, `MaxGCPauseMillis=300`), `ParallelGCThreads=40`,
  `ConcGCThreads=40` (set by `cassandra-env.sh:181-183` from the core count; R15 §3.1), shipped GC log
  (`gc=info,heap*=trace`), shipped heap dump and `kill -9` on OOM.
- **Constraints at shipped defaults (V6):** `native_transport_max_frame_size` 16 MiB; `native_transport_max_request_data_in_flight`
  heap/10; `…_per_ip` heap/40; `native_transport_max_message_size` derived; `native_transport_max_threads` 128;
  `native_transport_timeout` 12 s; `native_transport_idle_timeout` 0 (off); rate limiting off; connection limits −1.
  The intervention arm differs only by the diagnostic build (§2.8).
- **Resolved values** (read from JMX `StorageService` `NativeTransportMaxConcurrentRequestsInBytes` / `…PerIp` per run;
  R15 confirmed 2/4/8 GiB):

| Heap | Regions | Global C (B) | Per-IP C (B) | 16,777,207-B requests per IP |
|---|---|---|---|---|
| 2 GiB | 128 | 214,748,364 | 53,687,091 | 3 |
| 4 GiB | 256 | 429,496,729 | 107,374,182 | 6 |
| 6 GiB | 384 | 644,245,094 | 161,061,273 | 9 |
| 8 GiB | 512 | 858,993,459 | 214,748,364 | 12 |
| 16 GiB | 1,024 | 1,717,986,918 | 429,496,729 | 25 |

- **Environment (not capacity):** `MAX_HEAP_SIZE=<heap>`, `HEAP_NEWSIZE` unset (G1 ⇒ `-Xms = -Xmx`);
  `CASSANDRA_HEAPDUMP_DIR=<run dir>`; `systemd-run --user --scope -p MemorySwapMax=0` (**no `MemoryMax`**);
  `ulimit -n 100000`. Client (Python 3 stdlib) on the same node, all connections from 127.0.0.1 (one client IP).
- **V7.** `cassandra-env.sh` would resolve for pc82 (G1): heap = min(½ RAM 64,423 MiB, 31,744) = 31,744 MiB, direct
  15,872 MiB (`cassandra-env.sh:51-68`; with a hand-set heap the direct limit stays 15,872 MiB). The V-set heap **4 GiB**
  and every budget-search heap (2, 6, 8, 16 GiB) are ≥ 512 MiB ⇒ V7 met by the standing rule (2026-11-11) without
  per-case review; direct auto; **no container limit** (heap budget only), so no owner review is needed.
- **Arch:** x86_64; compare with U6 (aarch64) only qualitatively; R15 (same node, same build) readings are priors, not
  pooled.

### 2.4 Ceiling arithmetic

Per `#` request (payload H, L = 16,777,200, body 16,777,207 B, frame 16,777,216 B): E = L messages at full lex × 138 B
(R15 x86 measurement; band 120–145 B) ⇒ **U_req(full lex) ≈ 2.16 GiB** (band 1.9–2.3 GiB), plus the request constant
≈ 80 MiB (String 16 + ANTLR `char[]` 32 + decode buffer 32). Baseline idle 5.0.9: 30–150 MiB. Σ contract capacities that
cover this memory: **none** (the in-flight reserves cover only K, ≈ 1/88 of the holder).

| Run | Heap | N (H) + k1 + k2 | Max K = (N + k1 + k2) × 16,777,207 B | vs per-IP C | Demand at full lex (N × 2.16 GiB) | Heap full at | Free regions at the plateau (R15) | Trigger demand (regions) | Predicted |
|---|---|---|---|---|---|---|---|---|---|
| `T4` | 4 GiB | 3 + 3 + 0 | 100,663,242 | 0.94 | 6.5 GiB | ≈ 60 % of each lex | 1–7 | 3 × (2 + 1 + 2) = 15 (≥ 9 if loops shared) | **heap OOM** ≤ 60 s after t_trig |
| `C4` | 4 GiB | 3 C + 3 + 0 | same | 0.94 | 6 × 80 MiB + baseline ≈ 0.6 GiB live | never | ≫ 15 | 15 | survive |
| `I4` | 4 GiB | 3 H(iv) + 3 + 0 | same | 0.94 | ≤ 6 × 80 MiB + garbage ≈ 0.6 GiB | never | ≫ 15 | 15 | survive |
| `T8` | 8 GiB | 6 + 3 + 3 | 201,326,484 | 0.94 | 13 GiB | ≈ 60 % | ≈ 5 at 8,113 MiB | wave 2: 3 × 5 = 15 | heap OOM after wave 2 (moderate confidence) |
| `T6` (only if `T8-1` survives) | 6 GiB | 4 + 2 + 3 | 150,994,863 | 0.94 | 8.6 GiB | ≈ 69 % | not measured (expect ≤ 8) | wave 2: 15 | heap OOM after wave 2 |
| `T16` (optional) | 16 GiB | 12 + 3 + 3 | 301,989,726 | 0.70 | 26 GiB | ≈ 60 % | not measured | wave 2: 15 | heap OOM after wave 2 |
| `P2-1` (diagnostic) | 2 GiB | 2 + 0 + 1 | 50,331,621 | 0.94 | 4.3 GiB | ≈ 46 % | 1 (R15 `S1`/`T2`) | 5 | heap OOM ≤ 60 s after t_trig |

K is counted only after decode, so the pre-sent partial frames add nothing to K until they are complete. Every row
stays inside both in-flight limits and the 128 NTR threads; the endpoint is reachable by arithmetic. Direct memory:
≤ 18 frames × 32 MiB ≪ 15,872 MiB. CPU: ≤ 12 lexer threads + 40 GC threads on 40 cores (record load). RAM: largest JVM
16 GiB heap on 125 GiB.

### 2.5 Workload and environment

- **Node:** `pc82` only (victim and client on one node; one run at a time). Work dir **`<W>` = `/mydata/s4/r20/`**:
  `cassandra/` (`cp -a /mydata/s4/cassandra-base`), `cassandra-iv/` (intervention build), `harness/`, `runs/<run-id>/`.
  Never touch `/mydata/s4/cassandra-base` except to copy from it. Preflight per run (in `run.sh`): no `java …
  org.apache.cassandra.service.CassandraDaemon` command line (match the `java` command, not `pgrep -f CassandraDaemon`,
  which matched R15's own `ssh` shell), ports 7000/7199/9042 free, `/mydata` free ≥ 1.3 × heap + 4 GiB; if another
  agent's node runs on pc82, stop and report. Linger is off: drive the series from one `( setsid nohup … < /dev/null >
  … 2>&1 & )` launch, bounded background polls, never a foreground `sleep`, kill by PID.
- **Build** (in the background during harness setup): `build-iv.sh` from R15's
  [`harness/build-iv.sh`](../ErrorCollector_errorMsgs--humongous-request-during-gc-thrash/harness/build-iv.sh) with
  `W=/mydata/s4/r20`: `cp -a cassandra cassandra-iv`; apply R15's
  [`iv.patch`](../ErrorCollector_errorMsgs--humongous-request-during-gc-thrash/harness/iv.patch) (= §2.8; save `git diff`
  as `harness/iv.diff` and compare with R15's `iv.diff`); `rm -f build/classes/main/org/apache/cassandra/cql3/ErrorCollector*.class`;
  `ant jar`; check `javap -p -c -classpath build/apache-cassandra-5.0.9-SNAPSHOT.jar org.apache.cassandra.cql3.ErrorCollector
  | grep -c isEmpty` = base + 2 (R15: 1 → 3). Never run `ant` in a tree a node runs from. No `ivb` build (condition B is
  closed).
- **Harness** (`harness/` in this folder, synced to `<W>/harness/`; start from R15's
  [`harness/`](../ErrorCollector_errorMsgs--humongous-request-during-gc-thrash/harness/): `client.py`, `run.sh`,
  `series.sh`, `monitor.sh`, `Jmx.java`, `threadcount.py`, `stw.py`, `gctl.py`, `summarize.py`, `trigsum.py`,
  `hprof-histo.py`, `hprof_oome_thread.py`; change `W` to `/mydata/s4/r20`, scope units `r20-<run-id>`). Changes:
  - **`client.py`** keeps R15's load loop, payloads H and C, trigger connections (wave 1: `--trig-n k1`, `--trig-at
    gc:<gc.log>:<heap MiB> | fixed:<s> | none`, `--trig-max`), detector (three consecutive `Pause Full` lines with
    after-size ≥ 0.95 × heap ⇒ t_det; t_trig = t_det + 30 s, ≥ load start + 30 s, ≤ t_max) and `--min-resp`. New:
    - `--trig2-n k2`: k2 further trigger connections (STARTUP done before load start), each **pre-sends** its payload-C
      frame minus the last byte (16,777,215 of 16,777,216 B) at `--trig2-presend-s` (default 10 s) after load start,
      then waits; at t_trig2 it sends the last byte and waits for the response. Log `presend` time and bytes per
      connection in `trigger.txt`.
    - `--trig2-at`: `sat:<gc.log>:<heap MiB>:<free MiB>` = three consecutive `Pause Full` lines with heap − after-size
      ≤ free MiB (128 MiB = 8 regions), counted only from t_trig1 + 30 s (or from load start when k1 = 0), ⇒ t_det2;
      **t_trig2 = t_det2 + 30 s**, capped at t_trig1 + 300 s (`undetected` recorded if the cap fires); or `gc:` (the
      wave-1 rule, used by `P2-1` with k1 = 0).
    - The hold runs from t_trig1 (from t_trig2 when k1 = 0); socket timeout = hold + 3,600 s.
    - `trigger.txt` gains `t_det2`, `t_trig2`, the three lines that fired it, and `trig2-<j> send/response` lines.
  - **`run.sh`**: R15's driver (args `<run-id> <base|iv> <heap> <payload> <N> <k1> <trig-spec> <hold> [len] [t_max]`
    plus optional `<k2> <trig2-spec>`); `fixedfrom:<T-run>` reads that run's t_trig offset (as R15); new hold spec
    **`holdfrom:<T-run>`** = max(300 s, 2 × (t_OOM − t_trig of that T run) + 60 s), or 600 s if that T run did not OOM;
    dump wait 240 s (600 s at ≥ 16 GiB).
  - **`series.sh`**: R15's (`SKIPIF-SURVIVED`/`SKIPIF-OOM`/`ENDSKIP`, `HALT` file, dump analysis then delete);
    time guard **06:45 ET** (no run starts at or after it).
  - **`monitor.sh`**: R15's, non-diagnostic mode in the V-set (thread-print counts only, 10 s); `R15_DIAG=1` (full
    thread dumps every 10 s, same cadence) in the budget runs and `P2-1` only, to locate the trigger connections'
    event loops (read / decode / done).
- **Runs** (shipped conf; one node lifetime per run; offsets from load start = the instant the last of the N load
  connections sends its first request):

| Run | Build | Heap | Load payload × N | Trigger k1, rule | Wave 2 k2 (pre-sent), rule | Hold (until OOM, else) | Purpose |
|---|---|---|---|---|---|---|---|
| `S0` (not a reading) | base, then iv | 2 GiB | H, C at `--len 1048576`, × 1, 2× each; iv: H | — | — | per request | reachability on this build: H → `0x2000 line 1:0 no viable alternative at character '#'`; C → one EOF `0x2000`; iv H → the same first message; τ (R15: 3.4 µs) |
| `S0p` (not a reading) | base | 2 GiB | none (idle) | — | 1 C frame pre-sent at +10 s, last byte at +40 s | 30 s after t_trig2 | shakedown of the pre-send: `RequestsSize` 0 during the wait; trigger answered `0x2000` EOF ≤ 1 s after the last byte; connection not closed |
| `T4-1..3` | base | 4 GiB | H × 3 | 3, `gc:` (0.95 × heap, +30 s, t_max 300 s) | — | t_trig + 600 s | **V1** (R15 `T4` workload unchanged) |
| `C4-1..3` | base | 4 GiB | C × 3 | 3, `fixedfrom:T4-k` | — | `holdfrom:T4-k` | **V2** |
| `I4-1..3` | iv | 4 GiB | H × 3 | 3, `fixedfrom:T4-k` | — | `holdfrom:T4-k`, and ≥ 1 load response per connection (`--min-resp 1`, ≤ +300 s) | **V4** |
| `T8-1` | base | 8 GiB | H × 6 | 3, `gc:` (t_max 600 s) | 3, `sat:…:8192:128` | t_trig1 + 600 s | budget search (row: ≥ 600 s post-trigger hold) |
| `T8-2`, `T8-3` | as `T8-1` | 8 GiB | as `T8-1` | as `T8-1` | as `T8-1` | as `T8-1` | n/N at 8 GiB — only if `T8-1` OOMs |
| `T6-1` | base | 6 GiB | H × 4 | 2, `gc:` (t_max 600 s) | 3, `sat:…:6144:128` | t_trig1 + 600 s | boundary — only if `T8-1` survives |
| `T6-2`, `T6-3` | as `T6-1` | 6 GiB | as `T6-1` | as `T6-1` | as `T6-1` | as `T6-1` | n/N at 6 GiB — only if `T6-1` OOMs |
| `P2-1` (diagnostic) | base | 2 GiB | H × 2 | 0 | 1, `gc:` (0.95 × heap, +30 s, t_max 300 s) | t_trig2 + 300 s | does the pre-sent trigger end the 2-GiB thrash in OOM without the ≈ 218-s receive delay? |
| `T16-1` (optional) | base | 16 GiB | H × 12 | 3, `gc:` (t_max 600 s) | 3, `sat:…:16384:128` | t_trig1 + 600 s | upward search — only if `T8` is ≥ 2/3 and it can start by 06:10 ET |

  **Order:** `S0`, `S0p`, `T4-1`, `C4-1`, `I4-1`, `T4-2`, `C4-2`, `I4-2`, `T4-3`, `C4-3`, `I4-3`, `T8-1`, then either
  (`T8-2`, `T8-3`) or (`T6-1` [, `T6-2`, `T6-3`]), then `P2-1`, then `T16-1`. Skip rules (encoded with `SKIPIF-*` in the
  run list): `T8-1` survives ⇒ skip `T8-2/-3` and `T16-1`, run `T6-1`; `T6-1` survives ⇒ skip `T6-2/-3` (boundary
  between 4 and 6 GiB). If `S0p` fails (connection closed, K charged, or no answer), the pre-send is not used: `T8`/`T6`
  run wave 1 only (k2 = 0, still the ≥ 600-s hold, as the row asks) and `P2-1` is dropped — record it.
- **Disk:** two trees ≈ 0.9 GB; dumps ≈ 5.4 GB (4 GiB), ≈ 8 GB (6), ≈ 11 GB (8), ≈ 2.7 GB (2), ≈ 21 GB (16):
  analyse, record size + sha256 prefix + findings, delete the `.hprof` (none kept). Peak disk < 30 GB of 714 GiB.

### 2.6 Instruments

| What | How | Interval | Gives |
|---|---|---|---|
| Heap occupancy (U side, independent of K) | `logs/gc.log` (shipped Xlog, `heap*=trace` region counts): every `Pause Full` with after-size, GC cause (`G1 Humongous Allocation` / `G1 Evacuation Pause`), Humongous/Old/Eden region counts; `jcmd <pid> GC.heap_info` (no forced GC) | every GC; 3 s | U(t); **free regions after the last three Full GCs before each trigger** (`trigsum.py`) |
| Trigger | `trigger.txt` and `completions-*.txt` (tags `trig<j>`, `trig2-<j>`) | event | t_det, t_trig, t_det2, t_trig2, presend times, response / code / latency per trigger |
| Holder at failure (V3, V5) | the shipped OOM dump: `hprof_oome_thread.py` on **every** failing run; `hprof-histo.py --len-range 47 54` on `T4-1`, the first failing budget run (`T8-1` or `T6-1`) and `P2-1`: `LinkedList$Node`, `String`, `byte[47..54]`, `ErrorCollector`, `char[]` ≥ 1 M, `byte[]` ≥ 1 M, `NoViableAltException` | at end; each analysis capped at 15 min | message bytes and share of the dump; U/K; the throwing thread and frame |
| K (server) | JMX `org.apache.cassandra.metrics:type=Client,name=RequestsSize`, `…PausedConnections`, `StorageService` resolved limits; direct `BufferPool`/`java.nio` `MemoryUsed` (R15 `Jmx.java poll`) | 5 s | K ≤ C, paused 0; partial frames not charged |
| K (client) | `client-*.txt` (outstanding × body, load and triggers separately) | 1 s | K |
| Parses in flight; trigger event loops | `jcmd <pid> Thread.print` counts (NTR threads in `CqlLexer`/`Lexer.nextToken`/`ErrorCollector.syntaxError`; event-loop count); budget runs and `P2-1` also keep full dumps (`R15_DIAG=1`) | 10 s | n_held(t); where each trigger is (receiving / decoding / parsing / answered) |
| GC service level | `stw.py` STW share per 60-s window (each GC id once across rotated files) | after run | onset of ≥ 90 % STW; share before and after the trigger |
| Process | `RssAnon`; client `ps -o pcpu,rss`; `uptime` load | 3 s / 10 s | native growth; CPU |
| Throughput | `completions-*.txt` | per response | responses by code and latency; `I4`: error text and rate |
| Endpoint | `stdout.txt`: first `java.lang.OutOfMemoryError` line, `Dumping heap to`, `Heap dump file created`, the kill; `system.log` ERRORs; exit time | end | endpoint type; t_OOM − t_trig |
| Disk | `df -BM /mydata` | 1 s in `run.sh` | guard (avail < 50 GiB ⇒ stop the client, record) |

The samplers are the same in every arm of the V-set; no forced GC or live histogram during a measured run (only in
`S0`). `summarize.py` + `trigsum.py` write per run: endpoint, t_det, t_trig (and wave 2), t_OOM − t_trig, n_held,
K max, after-sizes and free regions before each trigger, STW share, responses by code, max `RssAnon`, dump findings.

### 2.7 Predicted response, outcome rows and stopping budget

**Predicted (before readings):**

- `S0`: H 1 MiB → `0x2000 line 1:0 no viable alternative at character '#'` in 2.5–4.5 s (τ ≈ 2.5–4.5 µs); C → one EOF
  `0x2000` in < 0.1 s; iv H → the same first message, latency within ± 30 % of base. `S0p`: `RequestsSize` 0 during
  the 30-s partial wait, trigger answered `0x2000` EOF ≤ 1 s after the last byte.
- **`T4-1..3`: heap OOM 3/3**, `java.lang.OutOfMemoryError: Java heap space`; t_det +95–120 s, t_trig +125–150 s;
  after-GC before the trigger 3,940–3,990 MiB, free regions ≤ 8; **t_OOM − t_trig 3–30 s** (bound ≤ 60 s; R15: 5.4–12.9 s);
  OOME thread = a trigger's event loop in `CharBuffer.allocate` ← `CBUtil.decodeString` (an NTR thread in
  `ANTLRStringStream.<init>` or a lexer thread is also acceptable when the histogram shows the holder); `T4-1` dump
  ≈ 5.4 GB: message classes ≥ 3.5 GB and **≥ 60 %** of shallow bytes (R15: 4.43 GB, 93 %), `ErrorCollector` 3 (+ up to 3
  if trigger parses started), U/K ≥ 30 (R15 88); K_server ≤ 100,663,242 B, paused 0; ≥ 90 % STW from ≈ +100 s.
- **`C4-1..3`: survive 3/3**; the three triggers answered `0x2000` EOF within 1 s; load responses all EOF `0x2000`,
  ≈ 5–8 per second per connection, latency 100–300 ms; after-GC peak ≤ 2,048 MiB (≤ 50 % of heap); STW < 5 %.
- **`I4-1..3`: survive 3/3**; the three triggers answered within 1 s; load responses `0x2000 line 1:0 no viable
  alternative at character '#'` after 40–80 s each, ≥ 1 per connection (≈ 5–8 per connection over the run); after-GC
  peak ≤ 2,048 MiB; STW < 5 %.
- `T8-1`: wave 1 (0.95 × heap at ≈ +150–200 s) answered within ≈ 40 s as in R15, or OOM; heap then saturates
  (three Full GCs with ≤ 128 MiB free) at ≈ t_trig1 + 30–200 s; **heap OOM ≤ 60 s after t_trig2** in a wave-2
  decode buffer (`CBUtil.decodeString`), message classes ≥ 60 % of the ≈ 11-GB dump. Confidence moderate (R15's
  8-GiB plateau left ≈ 5 regions; G1 may compact enough for one or two of the three).
- `T6-1` (if run): as `T8-1`, at ≈ +130–180 s. `T16-1` (if run): saturation later (Full GCs of 3–6 s); OOM after
  wave 2 if saturation is reached inside the cap.
- `P2-1`: t_det ≈ +85–100 s, t_trig ≈ +115–130 s (R15 `T2`), the last byte read at once, **heap OOM ≤ 60 s after
  t_trig** in the trigger's decode buffer (1 free region vs 2 needed), messages ≥ 60 % of the ≈ 2.7-GB dump.

**Outcome rows (V-set at 4 GiB):**

| Row | Observation | Reading |
|---|---|---|
| A1 | `T4` OOM 3/3; `C4` 0/3 with triggers answered; `I4` 0/3 with ≥ 1 response per connection; `T4-1` dump message classes ≥ 60 %; defaults; 4 GiB | **true positive**: `verified-OOM · deployment` (unprotected accumulation, `errorMsgs`; trigger = ordinary 16 MiB requests); largest failing budget from `T8`/`T6`/`T16` with n/N |
| A2 | `T4` OOM ≥ 3/3 but `C4` or `I4` OOM ≥ 1/3 | the trigger or the request constant alone reaches OOM, not the retention ⇒ **retry** (attribution fails) |
| A3 | a `T4` run survives its 600-s hold (triggers answered or never decoded) | record free regions and where the triggers were; with ≥ 1 survivor see A7 |
| A4 | `T4` OOM but message classes < 60 % of the dump or another holder largest | attribution fails ⇒ **retry** |
| A5 | `T4` OOM before the trigger | counts for V1 (the endpoint is the claim); record pre-trigger |
| A6 | direct-buffer OOM, kernel kill, frames rejected / `Overloaded`, or no lexer frame | competing endpoint or invalid run ⇒ record; fix in shakedown, else **retry** |
| A7 | `T4` mixed (1–2/3) | add `T4-4..6` with `C4`/`I4` matched only if they can start by 05:30 ET; report n/N (a stated rate < N/N is allowed by V1); else **retry** |

**Budget-search rows (not V-runs; they set the "largest failing budget" of the result phrase):**

| Row | Observation | Reading |
|---|---|---|
| G1 | `T8-1` OOM after wave 2 (or wave 1), then `T8-2/-3` | largest failing budget 8 GiB with n/3 (16 GiB if `T16-1` fails); state the trigger form (pre-sent wave 2) |
| G2 | `T8-1` survives, `T6-1` OOM | largest failing budget 6 GiB with n/3 |
| G3 | `T8-1` and `T6-1` survive | largest failing budget 4 GiB (the V-set); boundary 4–6 GiB under this workload, not a negative |
| G4 | `P2-1` OOM ≤ 60 s after t_trig | diagnostic: at 2 GiB the endpoint needs only the receive delay removed; a 2-GiB matched set with pre-sent triggers is the follow-up (not run here) |

**Stopping budget:** per run the hold of §2.5 (no run longer than start + 20 s baseline + t_max + hold + dump wait +
3 min); one endpoint per run, no escalation after an OOM; N, k1, k2 never above the table; no run starts at or after
**06:45 ET**; every process stopped by 07:00 ET.

### 2.8 Controls and intervention

- **Matched control (V2), 3 runs:** `C4-k`: the same opcode, build, conf, heap, instruments, three load connections
  sending the comment payload C (the same 16,777,200 bytes, frame and K, the same query `String`, ANTLR `char[]` and
  decode buffers; the lexer walks every character into one COMMENT token) and the **same three triggers at T4-k's
  offset**, held at least as long as T4-k needed (`holdfrom:`). The only difference from `T4-k` is that no message per
  character is retained. Survival shows the OOM needs the retained messages, not the trigger, the wire volume or the
  humongous request copies.
- **Causal intervention (V4), 3 runs:** `I4-k`: build `cassandra-iv` with U6/R15's one-file patch (each message is still
  built, only the first is retained; clients get the same error):

  ```diff
  --- a/src/java/org/apache/cassandra/cql3/ErrorCollector.java
  +++ b/src/java/org/apache/cassandra/cql3/ErrorCollector.java
  @@ -78,7 +78,9 @@
           if (recognizer instanceof Parser)
               appendQuerySnippet((Parser) recognizer, builder);
   
  -        errorMsgs.add(builder.toString());
  +        String m = builder.toString();
  +        if (errorMsgs.isEmpty()) // U6 intervention (diagnostic build only): keep only the message that is thrown
  +            errorMsgs.add(m);
       }
  @@ -87,7 +89,8 @@
       public void syntaxError(BaseRecognizer recognizer, String errorMsg)
       {
  -        errorMsgs.add(errorMsg);
  +        if (errorMsgs.isEmpty()) // U6 intervention: keep only the message that is thrown
  +            errorMsgs.add(errorMsg);
       }
  ```

  Payload H × 3 and the same three triggers at T4-k's offset; throughput recorded (one response per ≈ T_lex per
  connection). The original failure is reproduced on the unmodified build (`T4`).
- **V-table plan:** V1 `T4-1..3`; V2 `C4-1..3`; V3 U from `gc.log` (after-size, region counts) and the `T4-1` dump vs
  K from `RequestsSize` and the client; V4 `I4-1..3`; V5 the OOME thread of every `T4` run + `T4-1` histogram; V6 §2.3
  (conf md5 per run, JMX limits); V7 4 GiB, direct auto, no container limit; largest failing budget with n/N from
  `T8`/`T6`/`T16`.

### 2.9 Time plan (America/New_York; node clock MST = ET − 2 h)

Stage 2 starts ≈ **03:00**; every run stopped and the case file written by **07:30**; no run starts after **06:45**.
Per-run estimates from R15 on pc82: start ≈ 40 s, baseline 20 s; `T4` ≈ 3.5 min to OOM + 31 s dump + analysis
(OOME thread ≈ 1 min; histogram ≈ 3 min) ≈ 5–8 min; `C4`/`I4` ≈ 1 + 2.3 + 5 (hold ≥ 300 s) + 0.5 ≈ 9 min; `T8` ≈ 1 +
3 + 10 (hold) + dump/analysis ≈ 15–25 min; `T6` ≈ 14–22 min; `P2-1` ≈ 6–9 min; `T16-1` ≈ 25–35 min.

| ET | Step |
|---|---|
| 03:00–03:25 | read, freeze-hash check, node check, `/mydata/s4/r20` copies, `build-iv.sh` in the background, harness (R15's + §2.5 changes), `client.py --sizes` |
| 03:25–03:35 | `S0` (base, iv lifetimes), `S0p` |
| 03:35–05:05 | the nine V-runs (`T4`/`C4`/`I4` interleaved per triplet; `T4-1` histogram) |
| 05:05–05:30 | `T8-1` (≥ 600-s hold; histogram if it fails) |
| 05:30–06:20 | `T8-2`, `T8-3` (if `T8-1` failed) or `T6-1` [+ `T6-2`, `T6-3`] |
| 06:20–06:35 | `P2-1` |
| 06:10–06:45 | `T16-1` only if `T8` ≥ 2/3 and it can start by 06:10 (in place of nothing else pending) |
| ≤ 06:45 | last run start (`series.sh` guard) |
| ≤ 07:00 | every process stopped, pc82 checked (no daemon, ports free, no `.hprof`), sizes recorded |
| 07:00–07:30 | §3, §4, write-backs |

**Checkpoints and drop order.** At 05:15 ET: if the V-set is not finished, drop everything after it except `T8-1`.
At 06:00 ET: re-plan the rest against the 06:45 guard. Drop first → last: `T16-1`, the n/N repeats (`T8-2/-3` or
`T6-2/-3`), `T6-1`, `P2-1`, `T8-1`. **Never dropped:** `S0`, the nine 4-GiB V-runs. `S0p` may be skipped only together
with every pre-send arm (then `T8` runs wave 1 only and `P2-1` is dropped).

### 2.10 Write-back rule (fixed now, applied by stage 2)

- The verdict closes the **R15 condition A retry row** (`true positive (R20)` / `false positive (R20)` / `retry (R20)`;
  for retry, a new row) and is written to OC-409 and OC-410 in the phase-1 candidate list (OC-410 with "lexer part;
  parser-error path not tested"). OC-140 is unchanged.
- `_INDEX.md`: one row for R20. A true positive whose shape no clue pattern covers adds a pattern ("retained per-item
  diagnostics + one ordinary humongous request turns GC thrash into OOM") with source `phase 2: R20`; stage 2 checks
  CP-2 (item count, not bytes), CP-1 and CP-14 first.

`sha256 of §1–§2 at freeze: 01ab8ba1e24c15233693b5e3e257c07573b2c5a84ee34c16961b14c873691472` · computed over the lines from `## 1. Candidate` through the line before this one (`awk '/^## 1\. Candidate/{f=1} /^.sha256 of §1–§2 at freeze/{f=0} f' <case file> | sha256sum`), frozen 2026-11-21 · amendments after the freeze: dated, with reason.

## 3. Runs (stage 2)

Stage 2: a fresh OOM-agent session, 2026-11-21 01:59–≈ 04:15 ET on `pc82`. Freeze hash re-computed at 01:59 ET with the
command in §2's last line: `01ab8ba1e24c15233693b5e3e257c07573b2c5a84ee34c16961b14c873691472` = the frozen value.

### 3.0 Amendments and notes after the freeze

- **No amendment to the design.** Every run below ran as frozen (heaps, N, k1, k2, rules, holds, order, skip rules).
- **Harness implementation notes (not design changes).** The harness is R15's with exactly the §2.5 changes
  ([`harness/`](harness/)): `client.py` gains `--trig2-n/--trig2-presend-s/--trig2-at` (pre-sent wave 2; `sat:` and
  `gc:` rules), an idle load (`--n 0`, for `S0p`) and the hold base t_trig1 (t_trig2 when k1 = 0); `run.sh` gains the
  `k2`/`trig2-spec` arguments and `holdfrom:<T-run>` (via [`harness/holdfrom.py`](harness/holdfrom.py)); `series.sh`
  takes a 14-field run line (`diag` sets `R20_DIAG=1`, R15's `R15_DIAG` renamed), the 06:45 ET guard, a
  `runs/SKIP-<rid>` file (for the checkpoint re-plans) and two skip rules that encode §2.5's "only if" conditions
  (`SKIPIF-FEWOOM 2 T8-1 T8-2 T8-3` and `SKIPIF-AFTER 0610` before `T16-1`); `trigsum.py` reports wave 2.
  `S0` sent payloads H and C only (no M/CM: condition B is closed, §1.1); `run.sh` no longer runs the keyspace DDL,
  which only M needed. `build-iv.sh` builds `iv` only. Run lists: [`list-s0.txt`](harness/list-s0.txt),
  [`list-main.txt`](harness/list-main.txt).
- **Timing.** Stage 2 started ≈ 1 h earlier than §2.9 planned (S0 at 02:02 ET, the V-set from 02:08 ET), so the
  checkpoints (05:15, 06:00) and the 06:45 guard left more room than planned.

### 3.1 Environment and configuration (as run)

- **Node `pc82`** (`node1.jason92-326665`), x86_64, 40 cores, 125 GiB RAM, kernel 5.15.0-203-generic, OpenJDK
  11.0.33; checked 01:59 ET: no Java process, ports 7000/7199/9042 free, load 0.00, `/mydata` 714 GiB free,
  `/mydata/s4/` held only `cassandra-base`. Work dir `/mydata/s4/r20/` (`cassandra/`, `cassandra-iv/`, `harness/`,
  `runs/<run-id>/`).
- **Builds.** `cassandra/` = `cp -a /mydata/s4/cassandra-base`, jar md5 `c560848c966e329bbfdbb143497b1b66` (= R15).
  `cassandra-iv/`: R15's `iv.patch` applied (applied diff saved as [`harness/iv.diff`](harness/iv.diff); same changed lines as R15's), `ErrorCollector*.class` deleted, `ant jar`
  rc 0 in 15 s; `javap … | grep -c isEmpty` base 1 → iv 3; iv jar md5 `3a0fcbeb82cb5e2cf3ca17872854def9`.
- **Conf (every run, `conf-md5.txt`):** `cassandra.yaml 714ee9bf…`, `jvm11-server.options fbad82a8…`,
  `cassandra-env.sh 8be0588e…`, `jvm-server.options 26a957bf…` = shipped (= §2.3).
- **Resolved per run (`resolved.txt`, JMX):** `MaxDirectMemorySize=15872M` in every run; global / per-IP in-flight
  limits 214,748,364 / 53,687,091 B (2 GiB), 429,496,729 / 107,374,182 B (4 GiB) (8/6/16 GiB in §3.2);
  `native_transport_max_frame_size=16MiB`, `native_transport_max_threads=128`. JVM: `-Xms = -Xmx = <heap>`,
  `G1HeapRegionSize=16m`, `MaxGCPauseMillis=300`, `ParallelGCThreads=40`, `ConcGCThreads=40`,
  `+HeapDumpOnOutOfMemoryError`, `OnOutOfMemoryError=kill -9 %p`; open files 100,000. Each daemon ran in
  `systemd-run --user --scope -p MemorySwapMax=0 --unit=r20-<run-id>` (no `MemoryMax`).

### 3.2 Runs and readings

Times ET (node clock MST = ET − 2 h); offsets from load start; "after-GC" = heap after GC from `gc.log`; free regions
from the `heap*=trace` region counts (256 regions at 4 GiB). Full logs: `pc82:/mydata/s4/r20/runs/<run-id>/`; excerpts
in [`logs/<run-id>/`](logs/) (`summary.txt` = `summarize.py` + `trigsum.py`).

**Shakedown (not readings), 02:02–02:08 ET, 2 GiB:**

| Run | Reading | vs prediction |
|---|---|---|
| `S0` (base) | H 1 MiB → `0x2000 line 1:0 no viable alternative at character '#'` in 4.11 s and 3.23 s (τ ≈ 3.1–3.9 µs per `#`; T_lex(16 MiB) ≈ 52–66 s ⇒ t_max = max(300, 4 × 66) = **300 s**, as frozen); C → one EOF `0x2000` in 33 / 20 ms | as predicted |
| `S0iv` (iv) | H → the same first message in 3.52 s / 2.92 s (−14 % / −9 % vs base) | as predicted (± 30 %) |
| `S0p` (base, idle, 1 C frame pre-sent) | 16,777,215 B pre-sent at +10.0 s (sent in 76 ms); `RequestsSize` 0 in every 5-s sample through the 30-s wait, heap used unchanged (872 MiB), connection kept; last byte at +40.1 s → `0x2000` EOF **211 ms** later; `PausedConnections` 0 | as predicted ⇒ the pre-send is used (`T8`, `T6`, `P2-1`) |

**V-set, 4 GiB, 02:08–03:16 ET** (load H or C × 3, k1 = 3 trigger connections, payload C; `holdfrom:` resolved to
300 s for every C4/I4 run because 2 × (t_OOM − t_trig) + 60 ≤ 96 s):

| Run | t_det / t_trig | Free regions, last 3 Full GCs before t_trig (after-GC) | Endpoint | t_OOM − t_trig | OOME thread (`oome-thread.txt`) | Triggers | Load responses | after-GC max | STW (max 60 s; first ≥ 90 % window) | K_server max / paused |
|---|---|---|---|---|---|---|---|---|---|---|
| `T4-1` | +97.2 / +127.3 s | 2, 2, 6 (3,966–3,970 MiB; Humongous 15, Old 235–239) | **heap OOM** `Java heap space`, dump 5,463,385,220 B in 28.4 s, `kill -9` | **4.3 s** | event loop: `CharBuffer.allocate` ← `CBUtil.decodeString:107` ← `readLongString:201` ← `QueryMessage$1.decode:50` ← `PreV5Handlers$ProtocolDecoder.decode:289` | 3 sent; reset at the kill (32.7 s) | 0 (3 resets) | 4,076 MiB | 95 %; +113 s | 50,331,621 B (3 × 16,777,207) / 0 |
| `C4-1` | — / +127.4 s (`fixedfrom:T4-1`) | no Full GC; ≥ 221 free after every GC | survived 300-s hold | — | — | 3 × `0x2000` EOF in 202–220 ms | 9,845 EOF `0x2000` (3,277–3,285 per conn; 107/131/268 ms min/med/max) | 611 MiB | 1 %; none | 50,331,621 / 0 |
| `I4-1` | — / +127.4 s | no Full GC; ≥ 165 free after every GC | survived 300-s hold | — | — | 3 × `0x2000` EOF in 160–163 ms | 27 `line 1:0 no viable alternative at character '#'` (9 per conn; 43.5/47.3/53.0 s) | 1,419 MiB | 1 %; none | 50,331,621 / 0 |
| `T4-2` | +99.8 / +129.8 s | 3, 1, 2 (3,979–3,983 MiB; Hum 15, Old 238–240) | **heap OOM**, dump 5,500,130,150 B | **17.9 s** | the same event-loop stack (`CBUtil.decodeString:107`) | reset at the kill (53.3 s) | 0 (3 resets) | 4,076 MiB | 98 %; +110 s | 50,331,621 / 0 |
| `C4-2` | — / +129.8 s | no Full GC; ≥ 230 free | survived 300-s hold | — | — | 169–187 ms | 9,876 (3,290–3,293 per conn; 108/129/259 ms) | 473 MiB | 1 %; none | 67,108,828 (4 requests at once) / 0 |
| `I4-2` | — / +129.8 s | no Full GC; ≥ 165 free | survived 300-s hold | — | — | 203–204 ms | 27 (9 per conn; 44.6/46.7/54.3 s) | 1,418 MiB | 1 %; none | 50,331,621 / 0 |
| `T4-3` | +109.8 / +139.8 s | 6, 1, 3 (3,971–3,979 MiB; Hum 15, Old 235–240) | **heap OOM**, dump 5,464,857,895 B | **4.9 s** | the same event-loop stack (`CBUtil.decodeString:107`) | reset at the kill (38.4 s) | 0 (3 resets) | 4,076 MiB | 97 %; +109 s | 50,331,621 / 0 |
| `C4-3` | — / +139.8 s | no Full GC; ≥ 230 free | survived 300-s hold | — | — | 160–204 ms | 9,884 (3,290–3,299 per conn; 109/133/239 ms) | 462 MiB | 1 %; none | 50,331,621 / 0 |
| `I4-3` | — / +139.8 s | no Full GC; ≥ 173 free | survived 300-s hold | — | — | 170–173 ms | 27 (9 per conn; 43.3/45.6/52.3 s) | 1,277 MiB | 1 %; none | 50,331,621 / 0 |

- **After the trigger in the T arms** (`T4-1`, `logs/T4-1/summary.txt`): `Pause Young (Concurrent Start) (G1 Humongous
  Allocation)` and `Pause Young (Normal) (G1 Humongous Allocation)` (Humongous 15 → 17 regions: the triggers'
  first humongous objects got the last free regions), then `Pause Full (G1 Humongous Allocation)` 4,016 → 4,015 MiB and
  4,015 → 4,015 MiB (3 free regions, 2 contiguous needed per decode buffer) and the OOME. `T4-2`: the same sequence
  (Humongous 15 → 17, `Pause Full (G1 Humongous Allocation)` 4,047 → 4,021 → 4,021 MiB).
- **`T4-1` dump** (`logs/T4-1/histo.txt`; sha256 prefix `d0614d170e1c56b0`; deleted after analysis): 97.2 M objects,
  4,802,471,197 B shallow; `byte[47..54]` 32,198,263 / 2,220,528,364 B + `LinkedList$Node` 32,194,115 / 1,287,764,600 B +
  `String` 32,282,133 / 936,181,857 B = **4,444,474,821 B = 92.5 %** of shallow; ≈ 138 B per message;
  `ErrorCollector` 3 (the three load parses; the triggers were not yet parsed), `NoViableAltException` 3, large `char[]`
  7 / 234,880,912 B (decode buffers and ANTLR copies), large `byte[]` 7 / 54,526,016 B. K_server 50,331,621 B ⇒
  **U/K = 88.3**. The next class after the message classes is `char[]` (235 MB, 4.9 %).
- `T4-2`/`T4-3` dumps (5.50 / 5.46 GB, sha256 prefixes `cccaa15d07538e5f` / `b04312bbac874f1e`): OOME thread only
  (as planned), deleted.
- Threads (`threads.txt`): 3 NTR threads in `CqlLexer`/`Lexer.nextToken` from the second sample on in every T4 and
  I4 run; C4: 0–3 (short parses). `PausedConnections` 0 and NTR pending 0 in all nine runs; direct `MemoryUsed`
  ≤ 48 MiB; `RssAnon` ≤ 4,975 MiB.

**Budget search** (§2.5 order; `R20_DIAG=1`; 03:16–03:59 ET):

| Run | Heap; load; k1 + k2 | t_det / t_trig1 (wave 2) | Free regions, last 3 Full GCs before the trigger (after-GC) | Endpoint | t_OOM − trigger | OOME thread | K_server max (vs per-IP C) / paused | STW max; first ≥ 90 % window |
|---|---|---|---|---|---|---|---|---|
| `T8-1` | 8 GiB (512 regions); H × 6; 3 + 3 pre-sent | +150.1 / +180.1 s (wave 2 pre-sent at +10 s, **never fired**: OOM came first) | 4, 1, 4 (7,821–7,825 MiB; Humongous 30, Old 478–481) | **heap OOM**, dump 10,906,704,377 B in 59.8 s | **39.1 s** after wave 1 | NTR thread: `String.toCharArray` ← `ANTLRStringStream.<init>:75` ← `CQLFragmentParser.parseAnyUnhandled:67` ← `QueryProcessor.parseStatement:927` (a trigger's parse) | 117,440,449 B (7 requests; 0.55 C_IP 214,748,364) / 0 | 100 %; +115 s |
| `T8-2` | as `T8-1` | +164.1 / +194.1 s (wave 2 not fired) | 2, 2, 11 (7,854 MiB; Hum 30, Old 471–480) | **heap OOM**, dump 10,909,205,043 B | **7.6 s** | same NTR stack (`ANTLRStringStream.<init>:75`) | 100,663,242 / 0 | 99 %; +113 s |
| `T8-3` | as `T8-1` | +186.2 / +216.3 s (wave 2 not fired) | 2, 10, 17 (7,878–7,892 MiB; Hum 30, Old 465–480) | **heap OOM**, dump 10,979,058,336 B | **10.9 s** | same NTR stack | 134,217,656 (8 requests; 0.63 C_IP) / 0 | 99 %; +110 s |
| `T6-1..3` | — | — | — | **skipped by rule** (`T8-1` ended in OOM) | — | — | — | — |
| `P2-1` (diagnostic) | 2 GiB (128 regions); H × 2; 0 + 1 pre-sent | t_det2 +89.7 / t_trig2 +119.8 s (`gc:` rule; frame pre-sent at +10 s) | 2, 1, 1 (1,995–1,998 MiB; Hum 10, Old 116–117) | **heap OOM**, dump 2,718,455,713 B in 15.9 s | **4.8 s** after the last byte | event loop: `CharBuffer.allocate` ← `CBUtil.decodeString:107` ← `QueryMessage$1.decode:50` (the trigger's decode) | 33,554,414 B (0.63 C_IP 53,687,091; the trigger not admitted) / 0 | 98 %; +100 s |
| `T16-1` | 16 GiB (1,024 regions); H × 12; 3 + 3 pre-sent | +112.5 / +142.6 s; wave 1 **answered** (trig1 `0x1001 Query timed out before it could start` after 130.9 s; trig0/trig2 EOF `0x2000` after 277.6 s); `sat:` rule never met ⇒ wave 2 at the cap, t_trig2 **+442.9 s** | before wave 2: 3, 8, 7 (16,088–16,092 MiB; Humongous 66, Old 950–955); before wave 1: not in the kept logs (rotated) | **heap OOM**, dump 21,964,516,436 B in 124.9 s | **7.6 s** after wave 2's last byte (307.9 s after wave 1) | event loop: `CharBuffer.allocate` ← `CBUtil.decodeString:107` ← `QueryMessage$1.decode:50` (a wave-2 trigger's decode) | 234,880,898 B (14 requests; 0.55 C_IP 429,496,729) / 0 | 100 %; +219 s |

- **`T8-1` after the trigger:** `Pause Young (Concurrent Start) (G1 Humongous Allocation)` at +182.6 s, Humongous
  30 → 36 regions (the three decode buffers got regions after a Full GC freed 13), then back-to-back
  `Pause Full (G1 Evacuation Pause)` 8,029 → 7,939 MiB with 0–3 free regions until the OOME in a trigger's
  `ANTLRStringStream` copy (`char[16,777,200]`, 2 regions). The last full thread dump before it (+206 s,
  `threads-full.txt` on the node) shows the 3 trigger event loops in `CBUtil.decodeString` and 6 NTR threads lexing.
- **`T8-1` dump** (`logs/T8-1/histo.txt`; sha256 prefix `c8a4b732d2dc3d40`; deleted): 192.3 M objects,
  9,611,356,869 B shallow; `byte[47..54]` 63,910,888 / 4,407,078,778 B + `LinkedList$Node` 63,906,738 / 2,556,269,520 B +
  `String` 63,994,843 / 1,855,850,447 B = **8,819,198,745 B = 91.8 %**; `ErrorCollector` **9** (6 load parses + 3 trigger
  parses begun), large `char[]` 17 / 570,425,072 B (5.9 %), large `byte[]` 13 / 155,189,312 B. U/K = 8,819,198,745 /
  117,440,449 = **75.1**. `T8-2`/`T8-3` dumps (sha256 prefixes `930e720aaa71e23e`, `52c4bbe7b90ee414`): OOME thread
  only, deleted.
- **`P2-1` after the last byte:** `Pause Young (Concurrent Start)` and `Pause Young (Normal) (G1 Humongous
  Allocation)` (0 free), `Pause Full (G1 Humongous Allocation)` 2,007 → 1,998 MiB and 1,998 → 1,998 MiB (1 free
  region, 2 contiguous needed), OOME at +124.6 s. Compare R15 `T2-1..3` (the same 2-GiB load, trigger sent whole at
  the onset: never decoded in 180 s) and `D1` (decoded after ≈ 205 s, OOM 219.7 s after the trigger): with the frame
  pre-sent the event loop needed one byte and the OOM followed in 4.8 s. **`P2-1` dump** (`logs/P2-1/histo.txt`; sha256
  prefix `5129097bcfedbfd8`; deleted): 2,390,576,388 B shallow; `byte[47..54]` 15,551,063 / 1,070,789,121 B +
  `LinkedList$Node` 621,876,880 B + `String` 453,413,927 B = **2,146,079,928 B = 89.8 %**; `ErrorCollector` 2;
  U/K = **64.0**.
- **Pre-send in the budget runs:** in `T8-1..3` each wave-2 connection sent 16,777,215 B at +10 s (in 40–700 ms)
  and stayed idle; `RequestsSize` did not include them (K above = load + admitted wave-1 triggers only). The wave-2
  `sat:` rule counts only from t_trig1 + 30 s, and every T8 run ended in OOM from wave 1 before the rule could fire
  (`# all load connections ended … before wave 2` in `trigger.txt`).
- **`T16-1`** (03:46–03:59 ET; resolved limits 1,717,986,918 / 429,496,729 B): after wave 1 the heap stayed at
  after-GC 15,975–16,157 MiB with 0–8 free regions and ≥ 90 % STW for 298 s; the three whole-frame triggers were
  received and answered slowly (they found regions after Full GCs freed up to 7; Humongous 64 → 66), so wave 1 did not
  end in OOM. The `sat:` rule (heap − after ≤ 128 MiB) never held because the after-size stayed 227–296 MiB below the
  heap while only 1–8 regions were free (fragmentation), so wave 2 fired at the frozen cap t_trig1 + 300 s. Its three
  pre-sent frames were decoded at once: `Pause Young (G1 Humongous Allocation)` ×3 (Humongous 66 → 70, free 6 → 1),
  `Pause Full (G1 Humongous Allocation)` 16,157 → 16,157 and → 16,156 MiB (3 free regions), OOME at +450.5 s. Dump
  sha256 prefix `9a12e9def948f42c`, OOME thread only (no histogram by design), deleted. `RssAnon` max 18,739 MiB.

### 3.3 Deviations from the frozen design, and notes

- **None in the runs.** Every run used the frozen build, conf, heap, N, k1, k2, rules and holds; the skip rules
  selected `T8-2/-3` (row G1) and skipped `T6-1..3`; `T16-1` ran because `T8` was 3/3 and it started at 03:46 ET
  (before 06:10). The series log line `skip rule: T6-1 survived` is the harness's wording for "T6-1 did not end in an
  OOM" (it was skipped, not run); it only re-skipped `T6-2/-3`, which were already skipped.
- **Wave 2 never fired in `T8-1..3`**: wave 1 reached the OOM first (7.6–39.1 s after t_trig1, before the `sat:` rule's
  window could close). The pre-sent trigger form was therefore exercised by `P2-1` and `T16-1` (and `S0p`). The budget
  result at 8 GiB is the **wave-1 (whole-frame) trigger**, the same trigger form as the V-set; at 16 GiB it is the
  pre-sent wave 2, fired at the frozen cap (t_trig1 + 300 s) because the `sat:` rule never held (§3.2).
- **OOME thread at 8 GiB:** a trigger's NTR parse (`ANTLRStringStream.<init>`), not the decode buffer; §2.7 allowed
  either when the histogram shows the holder (it does: 91.8 %).
- Dumps: every `.hprof` was analysed and deleted by `series.sh` (none kept).

### 3.4 Clean-up and what is left on `pc82`

Checked 04:00 ET (02:00 node time) after `SERIES DONE`: no `java`, `client.py`, `series.sh`, `run.sh`, `monitor.sh`
or `Jmx` process; ports 7000/7199/9042 free; no `r20-*` scope unit; no `.hprof` anywhere under `/mydata/s4/r20`
(every dump analysed then deleted). **Left:** `/mydata/s4/r20/` **1.4 GB** — `cassandra/` 528 MB and `cassandra-iv/`
445 MB (build copies; `data/` and `logs/` of the last run inside `cassandra/`), `harness/` 120 KB, `runs/` 448 MB (the
17 run directories with full logs; `T16-1` 113 MB, `T8-*` 41–45 MB each, `threads-full.txt` in the budget runs). `pc82`
was idle from 03:59 ET. `/mydata/s4/cassandra-base` untouched (copied from only).

## 4. Conclusion (stage 2)

### 4.1 Verdict

- **Verdict: `true positive`** (outcome row **A1**; budget row **G1**, diagnostic row **G4**).
- **Protocol status (detail):** `verified-OOM · deployment` — unprotected accumulation (`ErrorCollector.errorMsgs`),
  endpoint Java heap OOM, V1–V7 met at 4 GiB with every capacity at its shipped default; largest tested failing
  budget **16 GiB** (1/1, `T16-1`, the pre-sent second trigger wave) and **8 GiB 3/3** (`T8-1..3`, the same
  whole-frame trigger as the V-set). Interpretation: suspected implementation defect (every lexer error message is built and
  kept although only the first is ever used; not documented as by design).
- **Reason.** On `pc82` (x86_64, shipped conf, 4 GiB heap, direct auto 15,872 MiB, no container limit), three 16-MiB
  `#` QUERYs from one client fill the heap with retained lexer messages (after-GC 3,966–3,983 MiB of 4,096, 1–6 free
  regions, ≥ 90 % STW from ≈ +110 s), and three ordinary 16-MiB comment QUERYs sent by the `gc:` rule ≈ 30 s later end
  in `OutOfMemoryError: Java heap space` **3/3** (`T4-1..3`, 4.3 / 17.9 / 4.9 s after the trigger), each time in a
  trigger's event loop allocating its 32-MiB decode buffer (`CharBuffer.allocate` ← `CBUtil.decodeString:107`). The
  `T4-1` dump holds 32.2 M messages (`byte[47..54]` + `LinkedList$Node` + `String`) = 4,444 MB = **92.5 %** of the
  heap against K = 50,331,621 B in the in-flight reserve (U/K = 88; 0.47 of the per-IP limit, nothing paused). The
  matched comment load with the same triggers at the same offsets survives **0/3 OOM** (`C4-1..3`: ≈ 9,870
  responses each, triggers answered in 160–220 ms, after-GC ≤ 611 MiB, STW 1 %), and the keep-first-message build
  survives **0/3** (`I4-1..3`: the same first error to every client, 9 responses per connection at 43–54 s each,
  triggers answered in 160–204 ms, after-GC ≤ 1,419 MiB, STW 1 %). The same workload scaled to 8 GiB (H × 6) fails
  **3/3** (`T8-1..3`, 39.1 / 7.6 / 10.9 s after the trigger; messages 91.8 % of the `T8-1` dump, U/K 75), and at 16 GiB (H × 12) the whole-frame triggers were answered slowly but a second, pre-sent trigger wave
  ended in heap OOM 7.6 s after its last byte (`T16-1`, 1/1),
  and at 2 GiB a trigger whose frame was pre-sent before the heap filled fails 1/1 in 4.8 s (`P2-1`, messages 89.8 %),
  which removes R15's 2-GiB receive delay.

### 4.2 V1–V7 (condition: 4 GiB, H × 3 + 3 ordinary C triggers by the `gc:` rule, shipped conf, base build)

| | Evidence |
|---|---|
| V1 Repetition | `T4-1..3`: heap OOM **3/3** (t_OOM − t_trig 4.3 / 17.9 / 4.9 s), from clean starts (one node lifetime each, data and logs removed before each start) |
| V2 Matched control | `C4-1..3`: 0/3 — same opcode, frame (16,777,216 B), K, decode buffers, query `String` and ANTLR copies, the same three triggers at T4-k's offset (+127.4 / +129.8 / +139.8 s), held 300 s (`holdfrom:`); the only difference is no message per character |
| V3 Measurement | U from `gc.log` (after-GC 3,966–3,983 MiB, region counts: 1–6 free, Humongous 15) and the `T4-1` dump (messages 4,444 MB = 92.5 %) vs K = `RequestsSize` 50,331,621 B (≤ 0.47 C_IP 107,374,182), `PausedConnections` 0; U/K = 88 (8 GiB: 75; 2 GiB: 64) |
| V4 Intervention | `I4-1..3`: 0/3 — `iv` build keeps only the first (thrown) message; clients get the same `0x2000 line 1:0 no viable alternative at character '#'`; throughput recorded (27 responses per run, 9 per connection); the original failure reproduced on the unmodified build (`T4`) |
| V5 Initiating failure | OOME thread of every `T4` run = a trigger's Netty event loop in `CharBuffer.allocate` ← `CBUtil.decodeString:107` ← `QueryMessage$1.decode:50`; `T4-1` histogram (V3). Budget runs: `T8-1..3` in a trigger's `ANTLRStringStream.<init>` (histogram `T8-1`: 91.8 %); `P2-1` in the trigger's decode buffer (89.8 %) |
| V6 Default constraints | shipped conf in every run (md5 = §2.3); in-flight limits resolved from JMX per heap (§3.1, §3.2); frame 16 MiB, 128 NTR threads, `native_transport_idle_timeout` 0; only `I4` differs (diagnostic build) |
| V7 Acceptable budget | 4 GiB heap (≥ 512 MiB standing rule), direct auto 15,872 MiB, no container limit (`MemorySwapMax=0` only); budget search: 8 GiB **3/3** (`T8-1..3`); 16 GiB **1/1** with the pre-sent second wave (`T16-1`; its whole-frame wave 1 was answered); largest tested failing budget 16 GiB (about half of the 31,744-MiB heap `cassandra-env.sh` would resolve for this node); 2 GiB 1/1 with the pre-sent trigger (`P2-1`, diagnostic, not a V-set) |

**Classification by measurement.** No control covers `errorMsgs` (unprotected accumulation). The only control on the
path, the native in-flight reserve, charges wire bytes: K ≤ 0.47–0.63 of the per-IP limit while the held messages are
64–88× K. The trigger is an ordinary admitted request of the same client within every limit; it converts the
GC-thrash service loss of U6/R15 into an OOM because a 16-MiB string needs 2–5 contiguous free 16-MiB regions and the
retained messages leave 1–6.

**Clue pattern.** The shape is covered by **CP-1** (counted unit ≠ held memory: the in-flight reserve counts the
16.8-MB wire body while the parse holds ≈ 2.2 GB of messages per request, held ÷ counted ≈ 64–88; × the default
per-IP cap heap/40 ⇒ ≈ 1.6–2.2 × the heap) with **CP-6** (nothing refuses before the JVM's own `OutOfMemoryError`). CP-2
does not apply (no item limit exists) and CP-14 does not (the messages are released when the parse throws). No new
pattern is added.

**Limits of attribution.** Client and server on one node (x86_64, 40 cores), one client IP, protocol v4,
`AllowAllAuthenticator` (with `PasswordAuthenticator` the client must be authenticated before QUERY; the parse is then
the same). The endpoint needs a second large request to arrive while the heap is saturated; without it the outcome is
GC service loss (U6, R15 `S1`). At 8 GiB the OOME was thrown in a trigger's parse copy rather than its decode buffer
(both are the trigger's 16-MiB allocations). The pre-sent trigger form was tested at 2 GiB (`P2-1`) and 16 GiB
(`T16-1`), one run each; at 8 GiB wave 1 reached the OOM before wave 2 could fire, and at 16 GiB wave 1 alone (whole
frames, sent at the onset of the thrash) was answered after 131–278 s without an OOM. Earlier arches (U6, aarch64) are not pooled.

### 4.3 Retry

Not applicable (true positive). Follow-up noted by row G4 (not a retry item): a 2-GiB matched set (T/C/I × 3) with the
pre-sent trigger would extend the `deployment` result to the ideal budget.
