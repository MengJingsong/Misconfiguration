# B19 (OC-533) — native_transport_max_request_data_in_flight: v4 LZ4 bodies are decompressed before any check and charged at their compressed size  <!-- file: cassandra/cases/native_transport_max_request_data_in_flight--v4-lz4-body-charged-compressed/native_transport_max_request_data_in_flight--v4-lz4-body-charged-compressed.md -->

| Field | Value |
|---|---|
| Case ID | `B19` (B = bypass case; sub-direction **accounting mismatch**, plus an **ordering** gap: allocation before any check) |
| From | `OC-533` of the phase 1 OOM candidate list (cluster duplicates `OC-431`, `OC-535`, §1.2) |
| Phase-1 case file | [`native_transport_max_frame_size-applySimpleConfig-valueInBytes--autonomous`](../../../../capacity-enforcement-exp/cassandra/stage3-ai-deep-read/cases/native_transport_max_frame_size-applySimpleConfig-valueInBytes--autonomous.md) |
| System / pinned source | Cassandra 5.0.9 (`systems/cassandra/source/`, `build.xml:36` `base.version` 5.0.9; unpatched for T/C arms) |
| Stage 1 (design) | OOM agent stage 1 (Claude Opus 5.5, subagent), 2026-11-21 08:02–08:17 EST |
| Stage 2 (verify) | fresh OOM-agent session (Claude Opus 5.5, subagent), 2026-11-21 08:17–09:35 EST on `ms0625` (aarch64); 21 arms + calibration; amendments A1–A3 |
| Verdict | **true positive** — T2 `verified-OOM · deployment`; T: V1–V3, V5–V7 met, V4 partial (strictly `candidate`) |

## Summary

- **Conclusion (stage 2):** true positive, heap OOM at shipped defaults and a 2 GiB heap. **T2:** one 22-byte
  frame from an unauthenticated v4 LZ4 connection, declaring a 1.9 GiB uncompressed length, kills the node in
  0.3–0.4 s (3/3; control 0/3; a cap before the allocation removes it 3/3) — `verified-OOM · deployment`.
  **T:** valid 131.6 KB frames that decompress to 32 MiB fill the heap in 3.6–9.4 s (3/3) with 36 bodies
  (1,152 MiB) held while the in-flight limits count 4 MiB; the same charged traffic with incompressible bodies
  survives (3/3). Charging the decompressed size keeps the node up during the load (3/3) but it still OOMs 2/3 when
  the client closes and the buffered frames are drained (V4 partial). 4 GiB survived 90 s (boundary).
- **Root cause (measured):** the LZ4 decompressor allocates the client-declared length before any check, and the
  in-flight limits charge the compressed length while the decompressed body stays live until the response is
  written.
- **Root cause (hypothesis under test, stage 1):** on a protocol v3/v4 connection that chose LZ4 in STARTUP (any
  client can; the default `AllowAllAuthenticator` answers READY), `Envelope.Decompressor` allocates a heap buffer of
  the length the client wrote in the first 4 bytes of the body (`transport/Compressor.java:179-184`) before any
  check. `native_transport_max_frame_size` (16 MiB) and both in-flight limits
  (`native_transport_max_request_data_in_flight` heap/10, `_per_ip` heap/40) see only the **compressed** length
  (`Envelope.with` keeps the compressed header, `Envelope.java:190-193`; the charge is `header.bodySizeInBytes`,
  `PreV5Handlers.java:105,153`), while the decompressed buffer stays live until the response is flushed
  (`PreV5Handlers.java:105-106`). A valid all-zero LZ4 body expands ≈ 255×, so the per-IP limit admits ≈ 6.4 × heap
  of decompressed bodies. With slow requests (a `count(*)` scan) the bodies pile up and the heap fails long before the
  limit engages.

## 1. Candidate

### 1.1 The row (quoted)

Phase 1 OOM candidate list
([`phase1-oom-candidates.md`](../../../../capacity-enforcement-exp/cassandra/stage5-oom-clue-find/phase1-oom-candidates.md),
line 542; full text in [`runs/wave3.md#oc-533`](../../../../capacity-enforcement-exp/cassandra/stage5-oom-clue-find/runs/wave3.md#oc-533)):

> | OC-533 | 2026-11-18 | `native_transport_max_frame_size-applySimpleConfig-valueInBytes--autonomous` | autonomous | Holder: the heap ByteBuf for a v3/v4 decompressed body. The LZ4 decompressor reads uncompressedLength from the first 4 bytes of the client's body and calls CBUtil.allocator.heapBuffer(uncompressedLength) before any validation. [details](runs/wave3.md#oc-533) | — | picked: B19 (2026-11-21) |
>
> Holder: the heap ByteBuf for a v3/v4 decompressed body. The LZ4 decompressor reads uncompressedLength from the first 4 bytes of the client's body and calls CBUtil.allocator.heapBuffer(uncompressedLength) before any validation. Why nothing stops it: max_frame_size checks only the compressed envelope length (a 13-byte envelope passes). Decompression runs in the Netty pipeline before LegacyDispatchHandler.checkLimits, and checkLimits charges header.bodySizeInBytes, which is the compressed size. Neither max_frame_size nor max_message_size nor the in-flight budget bounds the allocation. Size at defaults: up to 2^31-1 bytes (about 2 GiB) of heap per frame. A few connections on different event loops doing this at once exhaust an 8 GiB heap. Snappy validates the stream first, but a valid 16 MiB frame can still expand about 20x (about 340 MiB per request), also uncharged.
>
> **Where:** Compressor.java:175-184 (LZ4 heapBuffer(uncompressedLength)), Compressor.java:90-98 (Snappy), Envelope.java:520-539 (Decompressor before dispatch), PreV5Handlers.java:153,181 (in-flight charges compressed bodySizeInBytes), Envelope.java:429

Triage ([`runs/triage-2026-11-20.md`](../../../../capacity-enforcement-exp/cassandra/stage5-oom-clue-find/runs/triage-2026-11-20.md),
rank 1): default-reachable, single ARM node, test time minutes; **caveat:** "the bogus-length buffer is transient
(freed when decompression fails), so the design must make the allocations overlap or use valid bodies so the heap
really fills"; overlaps: "No existing case. Duplicates OC-431 and OC-535. Same pre-v5 pipeline as B9 and U2 (those
hold direct cumulations, not this heap buffer). A large valid QUERY body would also feed U6's parser amplification."

### 1.2 Cluster duplicates (quoted) and what this design covers

> **OC-431** (line 440, `native_transport_max_request_data_in_flight-applysimpleconfig-maxmessagesize--autonomous`, guided, CP-13, CP-1, CP-10, `open`):
> Holder: the decompressed request body of a pre-v5 (protocol v3/v4) connection that negotiated LZ4 or Snappy in STARTUP, which happens before authentication. Envelope.Decompressor runs before the legacy dispatch handler. LZ4Compressor.decompress reads a 4-byte uncompressedLength from the client's payload and calls heapBuffer(uncompressedLength) before anything validates it (Snappy does the same through Snappy.uncompressedLength). Envelope.with() keeps the original header, so the in-flight charge in PreV5Handlers.checkLimits is header.bodySizeInBytes, the compressed size. Why nothing stops it: the only size checks on v4 are native_transport_max_frame_size (16 MiB, applied to the compressed length) and the in-flight limits (heap/10 global, heap/40 per IP), all on compressed bytes. native_transport_max_message_size is checked only on the v5 path. Rough size at defaults: a ~20-byte frame from an unauthenticated client can ask for a heap byte[] of up to 2 GiB (transient, released when the decompressor's length check fails). Several connections doing it at once exceed a default heap. Legitimate traffic: a 16 MiB compressed frame of repetitive data decompresses up to about 255x (capped at 2 GiB) while charged 16 MiB, so heap/10 of charged bytes can hold several heaps' worth of decompressed bodies. This applies equally to the per-IP limit (stem native_transport_max_request_data_in_flight_per_ip-applysimpleconfig-maxmessagesize--autonomous); file it once.
>
> **OC-535** (line 544, `native_transport_max_frame_size-decode-bytesToDiscard--autonomous`, autonomous, `open`):
> Holder: the heap buffer allocated to decompress a v3/v4 envelope that is within the size limit. LZ4Compressor.decompress allocates heapBuffer(uncompressedLength), where uncompressedLength is the first 4 bytes of the client's body, before checking anything. Why nothing stops it: the discard/size check bounds only the compressed envelope (a tiny frame passes), decompression happens before LegacyDispatchHandler.checkLimits, and the in-flight budget charges the compressed bodySizeInBytes. Size at defaults: about 2 GiB of heap per 13-byte request. Several concurrent connections (one per event loop) can exhaust the default heap (8 GiB max). Snappy: a valid 16 MiB frame expands about 20x, to about 340 MiB per request, also uncharged.

| Claim in the cluster | Covered by | How |
|---|---|---|
| Valid repetitive LZ4 body, charged compressed, held until flush (OC-431 "legitimate traffic", the in-flight limits global and per-IP) | **Condition T (primary)** | 32 MiB bodies at ≈ 131.6 KB on the wire, many in flight; the per-IP limit is the one that binds first (one client IP) |
| Frame cap applies to the compressed length only (OC-533, OC-535) | Condition T | each T request is 32 MiB decompressed, 2× the 16 MiB frame cap, from a 131.6 KB frame |
| Bogus declared length, 13-byte envelope, allocation before any check (OC-533, OC-535, OC-431 "~20-byte frame") | **Condition T2 (secondary)** | one 13-byte frame declaring 1.9 GiB at a 2 GiB heap |
| "Several connections on different event loops" with bogus lengths (OC-533, OC-535) | not run | transient (allocation freed microseconds later when LZ4 fails); T replaces it with valid bodies that stay live (triage caveat) |
| Snappy (validated stream, ≈ 20×) (all three) | **not covered** | Snappy-specific; the same accounting path, lower ratio; left open for a later case |

When stage 2 writes back, OC-431 and OC-535 are duplicates of B19 for their LZ4 parts (owner's call to close them;
this stage does not change any list status).

### 1.3 Phase-1 case and its stage-4 result

The row names the stage-3 case
[`native_transport_max_frame_size-applySimpleConfig-valueInBytes--autonomous`](../../../../capacity-enforcement-exp/cassandra/stage3-ai-deep-read/cases/native_transport_max_frame_size-applySimpleConfig-valueInBytes--autonomous.md):
its constraint is `native_transport_max_frame_size` (16 MiB, `Config.java:285`, read once into
`Envelope.Decoder.MAX_TOTAL_LENGTH`, `Envelope.java:197`; check `Envelope.java:429-441`). It does not discuss
compression. Its stage-4 result
([`results/…valueInBytes--autonomous.md`](../../../../capacity-enforcement-exp/cassandra/stage4-runtime-verification/results/native_transport_max_frame_size-applySimpleConfig-valueInBytes--autonomous.md),
advisor-run 2026-10-24) is **"Confirmed — caps only on some paths (bypass)"**, outcome class **true positive**:
uncompressed legacy envelopes above the cap were rejected with "Request is too big" at 1, 4 and 16 MiB, while v5
used its own limit. That run measured the uncompressed envelope only; the LZ4 path of this case was **not tested**
in phase 1. The cluster duplicates' case files (`…decode-bytesToDiscard--autonomous`, two stage-4 results including a
2026-11-17 recheck; `…max_request_data_in_flight-applysimpleconfig-maxmessagesize--autonomous`) likewise test
uncompressed frames.

### 1.4 JIRA prior art (read only; nothing posted)

Sources: [`jira-oom-survey.csv`](../../../../capacity-enforcement-exp/cassandra/stage5-oom-clue-find/jira-oom-survey.csv)
(rows CASSANDRA-14997, -20052, -15299, -21081) and the JIRA REST API (reachable 2026-11-21 08:20 EST), JQL:
`text ~ "uncompressedLength"` (10 hits, none on the native transport), `text ~ "decompress" AND text ~ "in flight"`
(7 hits: 15299, 13304 v5 checksumming/compression, others unrelated), `text ~ "compression bomb"` (0),
`text ~ "decompressed" AND text ~ "native_transport_max_request_data_in_flight"` (0), `key = CASSANDRA-15556`.

| Issue | Status | Relevance | Verdict for B19 |
|---|---|---|---|
| CASSANDRA-14997 "OOM or segmentation fault tipping node over on erroneous uncompressed lengths" (2019, updated 2024-05-13) | **Open**, unresolved, no fix version | the bogus declared length of condition T2 | T2: **known-open** (not fixed in 5.0.9: `Compressor.java:184` unchanged) |
| CASSANDRA-15556 "When a LZ4 stream is corrupted it could cause the JVM to crash" | Fixed 4.0-alpha4 | corrupt-stream crash, not allocation size | not prior art for either condition |
| CASSANDRA-20052 "Size of CQL messages is not limited in V5 protocol logic" | Fixed 4.1.8 / 5.0.3 | added `native_transport_max_message_size` on v5 only; the survey row notes "protocol ≤v4 LZ4 decompress length (see 14997)" | shows the v5 path is bounded and the v4 path is not |
| CASSANDRA-15299, -13304 (v5 framing, checksums, LZ4 per frame) | Fixed 4.0 | v5 compresses per frame (≤ 128 KiB payload), so the v5 path has no client-declared whole-message length | context |
| — (none found) | — | the in-flight limits charging the compressed length while the decompressed body is held (condition T) | T: **new** |

## 2. Design solution (stage 1; frozen)

Technique note: [`bypass-playbook.md`](../../../bypass-playbook.md) rows "Accounting mismatch" (fixed charged usage
with varying object shape) and "Arithmetic, ordering, race" (allocation before the check). Direction label:
**bypass**. Interpretation (protocol): suspected implementation defect (the compressed header kept for charging) plus
a validation gap (no bound on the declared length; known-open CASSANDRA-14997).

### 2.1 Mechanism (checked in `systems/cassandra/source`, 5.0.9)

1. **Negotiation.** A client opens a v4 connection; `PipelineConfigurator.configureLegacyPipeline`
   (`transport/PipelineConfigurator.java:388-398`) installs `Envelope.Decoder` → `Envelope.Decompressor` →
   `PreV5Handlers.ProtocolDecoder` → `PreV5Handlers.LegacyDispatchHandler`. STARTUP with `COMPRESSION: lz4` sets the
   connection's compressor (`messages/StartupMessage.java:88-103`); with the default `AllowAllAuthenticator` the
   reply is READY.
2. **Frame cap on the compressed length.** `Envelope.Decoder.decode` compares `bodyLength + 9` with
   `MAX_TOTAL_LENGTH` = `native_transport_max_frame_size` (16 MiB) (`Envelope.java:197`, `:425-441`), counts
   `ClientMessageSizeMetrics.bytesReceived` (`:443-444`) and slices the body (`:447-453`). The body here is the
   **compressed** body.
3. **Allocation before any check.** `Envelope.Decompressor.decode` (`Envelope.java:516-541`) calls
   `LZ4Compressor.decompress` (`Compressor.java:175-206`): `input = readRawBytes(body)` (heap copy of the compressed
   bytes, transient), `uncompressedLength` = the first 4 body bytes (big-endian, `:179-182`),
   **`CBUtil.allocator.heapBuffer(uncompressedLength)` (`:184`)**, then `decompressor.decompress(...)` (`:188`); a
   mismatch throws and releases the buffer (`:189-199`). `CBUtil.allocator` is a `PooledByteBufAllocator(true)`
   (`CBUtil.java:60`); with the shipped `io.netty.allocator.maxOrder=11` (`conf/jvm11-server.options:145`) its chunk
   is 16 MiB, so a request > 16 MiB is a Netty **huge** allocation: a fresh `byte[]` of exactly that length (a G1
   humongous object), released to the GC when the buffer is released.
4. **Compressed header kept.** The result is `compressed.with(output)` (`Compressor.java:194`), and
   `Envelope.with` keeps the original header (`Envelope.java:190-193`), so `header.bodySizeInBytes` stays the
   compressed length.
5. **Charge = compressed length; hold = until flush.** `ProtocolDecoder` decodes the message from the decompressed
   body and attaches the envelope as its source (`Message.java:443-444`); trailing body bytes after the message's
   fields are not checked (no remaining-bytes test in `Message.Decoder.decodeMessage`, `Message.java:429-465`).
   `LegacyDispatchHandler.channelRead0` → `checkLimits` charges `request.getSource().header.bodySizeInBytes`
   (`PreV5Handlers.java:153`) against the per-IP and global limits (`ClientResourceLimits`, defaults heap/40 and
   heap/10, `DatabaseDescriptor.java:649-656`); over the limit the request is still admitted and the channel paused
   (`:173-178`). The envelope — with the decompressed body — is released only in `releaseItem` after the response
   is written (`PreV5Handlers.java:105-106`; `Flusher.java:145`, `:250`), which also returns the compressed charge.
6. **Multiplicity and hold time.** A connection keeps reading while its charged bytes are under the limits, so with
   slow requests (here a `SELECT count(*)` over a 1 M-row table) many requests are queued in the
   `Native-Transport-Requests` executor (128 threads; reads limited to `concurrent_reads` 32) each holding its
   decompressed body. The only other bound is the queue timeout: a request that waited longer than
   `native_transport_timeout` (12 s) is answered without processing (`Dispatcher.java:364-366`) and released.
7. **Endpoint.** The next 32 MiB humongous allocation finds no room after a full GC →
   `java.lang.OutOfMemoryError: Java heap space`; HotSpot writes the heap dump (`HeapDumpOnOutOfMemoryError`,
   `conf/jvm-server.options:120`) and runs `-XX:OnOutOfMemoryError=kill -9 %p` (`conf/cassandra-env.sh:209`), so the
   JVM dies at the throw point (Cassandra's own logging and `JVMStabilityInspector` do not run). Evidence is the
   HotSpot banner on stdout, the GC log and the dump.

**Ratio.** A body of D bytes that is a ~45-byte QUERY followed by zeros compresses (LZ4 block, lz4-java fast
compressor) to c ≈ D/255 + ~20 B: D = 33,554,432 → **c ≈ 131.6 KB** (stage 2 records the exact c).

**Condition T2 (bogus length).** A 13-byte body = 4-byte L + 9 zero bytes. Step 3 allocates L bytes before LZ4
fails. At a 2 GiB heap, L = 2,040,109,465 (0x79999999, 1.90 GiB) cannot be placed (needs ≈ 1,946 contiguous 1 MiB
G1 regions of 2,048, with the baseline resident) → immediate heap OOM from one 13-byte frame. Optional side note
(condition S, diagnostic only): L ≥ 2,147,483,646 exceeds HotSpot's byte-array limit
(`max_jint − 2` words of header) → `OutOfMemoryError: Requested array size exceeds VM limit`, which also triggers
`OnOutOfMemoryError` at **any** heap size; that is not budget exhaustion and is not counted for V7.

### 2.2 Protection map (fixed before readings)

| Domain | Allocation and ownership | Local contract (C) | Counter (K) | Scope and multiplicity | Lifetime | At the limit |
|---|---|---|---|---|---|---|
| **R — pre-v5 request bodies of one client IP (claimed)** | decompressed body `byte[]` (`Compressor.java:184`), owned by the request's `Envelope` | `native_transport_max_request_data_in_flight_per_ip` = heap/40 (**53,687,091 B = 51.2 MiB** at 2 GiB) + one force-admitted request per paused connection (E × c) → **C ≈ 51.7 MiB** at E = 4; global heap/10 = 204.8 MiB (not binding with one IP) | `org.apache.cassandra.metrics:type=Client,name=RequestsSize` (global in-flight bytes = this IP's, one client IP) | per request; requests in flight per IP bounded only by the charged sum (and the client's own cap E × Q = 1,024) | decode → response written (`PreV5Handlers.java:105-106`); queued > 12 s → answered without processing | channel paused (autoRead off); current request still admitted |
| F — frame size (claimed, per request) | same buffer | `native_transport_max_frame_size` 16 MiB per request (`Envelope.java:429`) | the compressed total length | per frame | — | discard + "Request is too big" (compressed length only) |
| X — decompression in progress | the same `byte[]` during `decompress` (≤ one per event loop) | none | none | ≤ E = 4 event loops (distinct, round-robin) → ≤ 128 MiB | ms per request | — |
| N — Netty cumulation (direct) | `Envelope.Decoder` cumulation (B9/U2's domain) | none / `MaxDirectMemorySize` | Netty direct counter | per connection | ≤ one 131.6 KB frame | not claimed; ≤ 1 MiB here |
| B — heap baseline + scans | memtables (none written during arms), `count(*)` paging (5,000 rows of `(int,int)` per page, ≤ 32 concurrent reads), caches | various defaults | — | — | — | measured in C1 |

Aliases: the decompressed `byte[]` is aliased by the `PooledHeapByteBuf`/`PooledUnsafeHeapByteBuf`, the `Envelope`
and (through `getSource()`) the `QueryMessage`; the query string and options are copies of ~45 bytes.

### 2.3 Configuration and budget audit

| Setting | Class | Value (resolved) |
|---|---|---|
| `native_transport_max_request_data_in_flight` | **default** (absent) | heap/10: 214,748,364 B (204.8 MiB) at `-Xmx2048M` (G1 `maxMemory` = 2,147,483,648); 429.5 MB at 4 GiB; 859.0 MB at 8 GiB; 1,664.2 MB at 15,872 MiB |
| `native_transport_max_request_data_in_flight_per_ip` | default | heap/40: 53,687,091 B (51.2 MiB) at 2 GiB; 102.4 / 204.8 / 396.8 MiB at 4 / 8 / 15.5 GiB |
| `native_transport_max_frame_size` | default | 16 MiB (`Config.java:285`) |
| `native_transport_max_message_size` | default | v5 only; not on this path |
| `native_transport_max_concurrent_connections`, `_per_ip` | default | −1, −1 |
| `native_transport_max_threads`, `concurrent_reads` | default | 128, 32 |
| `native_transport_timeout`, `read_request_timeout`, `range_request_timeout`, `cql_start_time` | default | 12 s, 5 s, 10 s, REQUEST |
| `native_transport_rate_limiting_enabled`, `native_transport_queue_max_item_age_threshold` | default | false, `Double.MAX_VALUE` |
| authenticator | default | `AllowAllAuthenticator` (READY after STARTUP) |
| Netty allocator | shipped `jvm11-server.options` | `maxOrder=11` (16 MiB chunks), `useCacheForAllThreads=true`; heap arenas = min(2 × 6, heap/16 MiB/6) (record) |
| OOM handling | shipped | `HeapDumpOnOutOfMemoryError` (`jvm-server.options:120`), `OnOutOfMemoryError=kill -9 %p` (`cassandra-env.sh:209`) |
| yaml diff | environment | `cluster_name: 'b19'`, `listen_address`/`rpc_address` `127.0.0.19`, seeds `127.0.0.19:7000`, data/commitlog/hints/saved_caches/cdc under `/mydata/s4/B19/node`; JMX port 7319 (cassandra-env) |
| JVM extras | instrumentation (all arms alike) | `-XX:ErrorFile=$D/logs/hs_err_pid%p.log`; `-XX:-HeapDumpOnOutOfMemoryError` only in the budget-search arms > 4 GiB (disk, §2.5) |
| I1 / I2 property | intervention arms only | `-Dcassandra.b19.charge_decompressed=true` (I1), `-Dcassandra.b19.cap_uncompressed=true` (I2), on the separate patched build (§2.8) |
| heap | **budget** | **2,048 MiB** (V arms); 4,096 / 8,192 / 15,872 MiB in the budget search |
| `MaxDirectMemorySize` | budget (not claimed) | not passed: `cassandra-env.sh` resolves it from RAM even with a hand-set heap: 62 GiB node → **7,936 MiB** (record from `VM.flags`) |
| process scope | environment (non-binding) | `systemd-run --user --scope -p MemoryMax=48G -p MemorySwapMax=0` (swap 0 for the measured process); not a budget |
| CPU | environment | Cassandra `taskset -c 0-5` (→ 6 available processors, 12 event loops); client, sampler, `jcmd`, hprof scripts on 6–7 |
| storage | environment | `/mydata` local disk (not NFS), not tmpfs |

**V7 argument (written before readings).** The standing rule (2026-11-11) accepts a heap ≥ 512 MiB without review;
2 GiB is the ideal and is what `cassandra-env.sh` resolves for a 4 GiB node (½ RAM). The budget search climbs to
**15,872 MiB**, which is what `cassandra-env.sh` resolves on this very node (62 GiB RAM: min(½ RAM, 15,872 MiB),
`conf/cassandra-env.sh:51-67`). No container limit is a budget (the scope is a safety net only). Researcher's review:
not required (standing rule).

**V6.** Every capacity constraint in the protection map is at its shipped default in T, C1, T2, C2 and the budget
search; only the intervention arms differ, and only by a diagnostic patch (not a setting).

### 2.4 Ceiling arithmetic

D = 33,554,432 B (32 MiB) per T request; c ≈ 131.6 KB charged; ratio r ≈ 255.

| Quantity | 2,048 MiB | 4,096 | 8,192 | 15,872 |
|---|---|---|---|---|
| Per-IP contract C (51.2 MiB × heap/2 GiB + E·c) | 51.7 MiB | 102.9 | 205.3 | 397.3 |
| T requests admitted before the first pause, ⌈per-IP / c⌉ | ≈ 408 | ≈ 816 | ≈ 1,632 | ≈ 3,162 |
| T decompressed bytes those hold (cap: client E·Q = 1,024 requests = 32 GiB) | ≈ 12.75 GiB | 25.5 GiB | 32 GiB (client cap) | 32 GiB (client cap) |
| Bodies needed to fill the heap, (heap − baseline ≈ 0.3 GiB)/32 MiB | ≈ 56 | ≈ 120 | ≈ 248 | ≈ 487 |
| K when the heap is full (bodies × c) | ≈ 7.0 MiB (< C) | ≈ 15 MiB | ≈ 31 MiB | ≈ 61 MiB |
| C1 (incompressible, c ≈ 131.6 KB, decompressed ≈ 131 KB): held at the per-IP limit | ≈ 51.7 MiB | — | — | — |
| I1 (charge = 32 MiB): held ≤ E × 2 bodies | ≤ 256 MiB | — | — | — |

The contract cannot cover T: the limit admits ≈ 6.2 × heap of T bodies at every heap (per-IP/c × D = heap/40 × 255).
The only effective bound is time: bodies held = arrival rate λ × hold time, with the hold capped at ≈ 12 s by
`native_transport_timeout`. To fill the heap at 15,872 MiB within 12 s needs a sustained λ ≥ 41 requests/s
(1.3 GiB/s); at 2 GiB, 56 bodies at any λ ≥ 5/s. The event loops share 6 cores with ≤ 32 running scans, so λ at
large heaps is the uncertain factor; the calibration measures it (§2.5 step 4).

### 2.5 Workload, environment and procedure

**Node.** `ms0625` only (node0.jason92-326377, Utah m400, **aarch64**, 8 cores, 62 GiB RAM, 8 GiB swap; `/mydata`
39 GiB with **29 GiB free**). Checked read-only 2026-11-21 08:08 EST: no Java process, `Linger=no`, JDK 11.0.33,
Python 3.10.12; existing `/mydata/b8`, `/mydata/oom-smoke`, `/mydata/u1r2` belong to other cases — **do not touch**.
Build `/mydata/s4/cassandra-base` (copied tree, no `.git`; jar `build/apache-cassandra-5.0.9-SNAPSHOT.jar` md5
`beb4d0c1db2a0bbacc84e37158a9d7c7`; `lib/lz4-java-1.10.1.jar`, `netty-all-4.1.130.Final.jar`; `build/tools/lib/stress.jar`
present). HANDOFF notes this jar differs from `ms0611`'s: before step 1, `diff` the build's
`src/java/org/apache/cassandra/transport/{Compressor,Envelope,PreV5Handlers,Message,Dispatcher}.java` against the
repository's `systems/cassandra/source/` copies and record the result; any difference on these files stops the
case (blocked). Run root **`/mydata/s4/B19/`** (`/mydata/s4` is owned by `jason92`; no `sudo` needed). Client and
server colocated on loopback. Never mix with x86 nodes.

**Harness** (`harness/` in this folder, copied to `/mydata/s4/B19/h`; derived from B9's
[`harness/`](../native_transport_max_request_data_in_flight--v4-frames-per-connection/harness/)):

- `ctl.sh` (from B9 `ctl.sh`): `BUILD` (unpatched `/mydata/s4/cassandra-base` or patched `/mydata/s4/B19/patched`),
  `D=/mydata/s4/B19/node`, `IP=127.0.0.19`, `JMXP=7319`, `CPUS=0-5`, cluster `b19`; env `XMX`, `DUMP` (1 keep heap
  dump in `$D/dumps`, 0 add `-XX:-HeapDumpOnOutOfMemoryError`), `VEXTRA` (only the I1/I2 property). Cassandra runs in
  the foreground (`bin/cassandra -f`) under the scope with **stdout and stderr to `$D/logs/stdout.log`** (the
  HotSpot OOM banner goes there). `gen` restores the data template (`rsync -a /mydata/s4/B19/template/ $D/`) after
  writing the conf. Record `V-flags.txt` (`jcmd VM.flags`: `MaxHeapSize`, `MaxDirectMemorySize`), `V-cmdline.txt`,
  `V-yaml.diff`.
- `B19Client.java` (new; Java 11 single-file launch with `-cp $BUILD/lib/lz4-java-1.10.1.jar`, raw sockets, no
  driver). Protocol **v4** frames (9-byte header: `0x04`, flags, stream id, opcode, length). Modes:
  - `schema` / `load <rows>`: uncompressed QUERY frames `CREATE KEYSPACE b19 … SimpleStrategy RF 1`,
    `CREATE TABLE b19.t (k int PRIMARY KEY, v int)`, then `INSERT INTO b19.t (k, v) VALUES (i, i)` for
    i = 0…rows−1, pipelined (4 connections × 256 outstanding).
  - `probe`: one uncompressed `SELECT count(*) FROM b19.t` (page_size 5,000), prints the latency and the count.
  - `flood <kind> <E> <Q> <seconds>`: E connections opened back to back (distinct event loops), each sends
    STARTUP `{CQL_VERSION: 3.0.0, COMPRESSION: lz4}`, waits for READY, then a writer thread keeps up to Q requests
    outstanding (stream ids 0…Q−1 reused) and a reader thread reads responses (decompressing LZ4 bodies) and counts
    ROWS / ERROR by code. Request body (built and compressed **once** per kind, reused): QUERY
    `SELECT count(*) FROM b19.t`, consistency ONE, flags 0x04, page_size 5,000, then padding to a total of D bytes;
    compressed with `LZ4Factory.fastestInstance().fastCompressor()` and prefixed with the 4-byte big-endian D
    (the format `Compressor.java:142-163` writes). Kinds: **`zero`** (padding zeros, D = 33,554,432); **`rand`**
    (padding random bytes, total length chosen so the compressed length equals the `zero` kind's c within ±1 %,
    i.e. ≈ 131 KB); **`bogus <L>`** (one 13-byte body: L then 9 zero bytes; one connection, one frame, then read
    one response or EOF ≤ 30 s). Prints `FLOOD_START <epoch_ms>`, a 1-s line (`sent`, `rows`, `errors{code}`,
    `outstanding`, socket state) and `FINAL`; c and D printed at start. Client JVM `taskset -c 6-7 java -Xmx2g`.
  - First-trigger check (before any arm): `flood zero 1 1 5` must return ROWS with count = rows (proves the server
    decompressed and executed a 32 MiB body from a ≈ 131.6 KB frame); `flood rand 1 1 5` likewise; `bogus 67108864`
    must return an ERROR (or close) with the node alive. A failure stops the case (blocked, harness or path).
- `B19Sample.java` (from `B9Sample.java`), JMX `127.0.0.1:7319` every **500 ms**: heap used and committed; G1 Old
  Gen pool used; **K** = `type=Client,name=RequestsSize`; `PausedConnections`; `ConnectionPaused` count;
  `RequestDispatched` count; `TimedOutBeforeProcessing` count; `ConnectedNativeClients`;
  `Native-Transport-Requests` and `ReadStage` Active/Pending/Completed; `ClientRequest,scope=Read`/`RangeSlice`
  Timeouts. (Verify every ObjectName in the shakedown; a missing one is a harness fix.) A 1-s loop writes
  `epoch_ms,RssAnon_kB,memory.current,oom_kill` (`/proc/<pid>/status`, the scope's cgroup) to `cg.csv`.
- `arm.sh <name> <kind> <xmx> <dump> [vextra] [build]`: preflight (no `CassandraDaemon`, `/mydata` free ≥ 8 GiB,
  `MemAvailable` ≥ 30 GiB, time before 13:15 EST, else stop the queue); `ctl.sh gen`; start; wait for
  `Starting listening for CQL clients` (≤ 180 s); `probe` (one count(*), warm-up, recorded); samplers on; **10 s
  idle baseline**; `B19Client flood <kind> 4 256 90` (bogus kinds: the single frame, then 30 s observation); then
  if the JVM is alive at flood t = 75 s: one `taskset -c 6-7 jcmd <pid> GC.class_histogram` (end-of-window U check,
  after the readings); 10 s idle; collect `system.log`, `debug.log`, `gc.log*`, `stdout.log`, `hs_err*`, histogram,
  V-files; stop the node (kill by PID); classify `OOM` (HotSpot banner in `stdout.log` and JVM gone) / `alive` /
  `other`; move the dump (if any) into the arm folder; append one line to `/mydata/s4/B19/runs/summary.txt`.
- `b19peaks.py <armdir>`: from `samples.csv`, `client.log`, `cg.csv`, `gc.log`: baseline heap (median of the idle
  10 s); peak heap; K at the last sample and K max; outstanding at the last client line; λ (frames sent per second,
  first 5 s and overall); time from `FLOOD_START` to the OOM banner (or JVM death); post-GC heap occupancy series
  (G1 "Pause" lines) and the maximum; `PausedConnections` max; `TimedOutBeforeProcessing` delta; completed count(*)
  per second.
- `hprofhist.py` (from U10's [`hprofhist.py`](../default_page_size--unpaged-aggregate-whole-partition/harness/hprofhist.py))
  with B19 buckets: `byte[]` of length exactly D (count, bytes), `byte[]` ≥ 1 MiB (count, bytes), counts of
  `org.apache.cassandra.transport.Envelope`, `…messages.QueryMessage`, `io.netty.buffer.PooledUnsafeHeapByteBuf` /
  `PooledHeapByteBuf`; `hprof_oome_thread.py` (from
  [`ErrorCollector_errorMsgs--humongous-trigger-matched-set-4GiB/harness/`](../ErrorCollector_errorMsgs--humongous-trigger-matched-set-4GiB/harness/hprof_oome_thread.py))
  for the OOM thread's stack. Run with `python3 -I`, pinned to cores 6–7, only between arms.

**Procedure (in this order; time plan §2.7):**

1. `mkdir -p /mydata/s4/B19/{h,runs,template,node}`; copy `harness/`; source `diff` (above); record JDK, kernel,
   `nproc`, md5 of the jar.
2. **Patched build in the background** (§2.8): `cp -a /mydata/s4/cassandra-base /mydata/s4/B19/patched`; apply
   `harness/b19-diagnostic.patch`; delete `build/classes/main/org/apache/cassandra/transport/{PreV5Handlers*,Compressor*}.class`
   (Ant's 1-s timestamps, HANDOFF Lessons); `( setsid nohup ant jar < /dev/null > /mydata/s4/B19/build-patched.log 2>&1 & )`
   in `/mydata/s4/B19/patched`; done at `BUILD SUCCESSFUL`; record the jar md5 and
   `unzip -p …jar org/apache/cassandra/transport/Compressor\$LZ4Compressor.class | grep -c b19` ≥ 1. Never run `ant`
   in `cassandra-base`.
3. **Template:** start at 2,048 MiB with an empty data dir, `schema`, `load 1000000`, `nodetool flush b19`,
   `nodetool drain`, stop; copy `data/ commitlog/ hints/ saved_caches/` to `/mydata/s4/B19/template/` (record size).
4. **Calibration (not readings), 2,048 MiB:** start from the template; `probe` ×3 → L1 = median count(*) latency.
   Rule: L1 in [1, 10] s → keep; L1 < 1 s → rebuild the template with `load 3000000` once and re-probe; L1 > 10 s →
   rebuild with 300,000 rows. Then the first-trigger checks (above). Then one **shakedown** `flood zero 4 256 20`
   to check every instrument and print λ (frames/s, first 5 s); its outcome is not a reading. Record c (`zero`),
   the `rand` padding length and its c.
5. **V arms at 2,048 MiB** (unpatched for T, C1; patched for I1), interleaved T, C1, I1 × 3 with `DUMP=1`:
   `arm.sh T_rN zero 2048M 1`, `arm.sh C1_rN rand 2048M 1`,
   `arm.sh I1_rN zero 2048M 1 -Dcassandra.b19.charge_decompressed=true /mydata/s4/B19/patched`.
6. **Condition T2** at 2,048 MiB, interleaved × 3: `arm.sh T2_rN "bogus 2040109465" 2048M 1`;
   `arm.sh C2_rN "bogus 67108864" 2048M 1` (C2 sends its frame **50 times**, a fresh connection each, 200 ms apart);
   `arm.sh I2_rN "bogus 2040109465" 2048M 1 -Dcassandra.b19.cap_uncompressed=true /mydata/s4/B19/patched`, followed in
   the same JVM by `flood zero 1 1 5` and an uncompressed `probe` (useful work still served; under I2 the 32 MiB
   body is refused, which is recorded, not hidden).
7. **Budget search (condition T, upward):** `arm.sh T_4G zero 4096M 1`; if OOM → `arm.sh T_8G zero 8192M 0`; if
   OOM → `arm.sh T_15872 zero 15872M 0`. Then 2 more runs at the **largest failing** heap (n/N ≥ 2/3 there makes
   it the reported maximum; 1/3 → report n/N and the next lower heap). A heap where T survives is the boundary:
   record λ, outstanding, `TimedOutBeforeProcessing` and the post-GC heap peak (not a negative).
8. Optional (drop first): `S_vm`: `arm.sh S_vm "bogus 2147483647" 15872M 0` (VM-limit OOM, diagnostic note);
   `P0`: `arm.sh P0 zero 2048M 0 "" /mydata/s4/B19/patched` (patched build without a property reproduces T).
9. Dumps: analyze every OOM dump at ≤ 4 GiB with `hprofhist.py` and `hprof_oome_thread.py`; keep the dumps on
   the node until the case is filed; small excerpts to `logs/`.

Disk: template ≈ 0.1 GiB; dumps ≈ 3 × 2 GiB (T) + 3 × ≤ 0.5 GiB (T2) + up to 3 × 4 GiB (T_4G if it is the largest)
≤ 20 GiB < 29 GiB free; arms > 4 GiB keep no dump. Stop the queue if `/mydata` free < 8 GiB.

### 2.6 Instruments (U independent of K)

- **K:** `RequestsSize` every 500 ms (the in-flight counter both limits use); `PausedConnections`,
  `ConnectionPaused`.
- **U (claimed holder):** (a) at OOM, the dump: `byte[]` of length exactly 33,554,432 (count × size) and
  `Envelope`/`QueryMessage` counts; (b) every 500 ms, JMX heap used and G1 Old Gen used, and after each GC the G1
  log's post-GC occupancy minus the idle baseline (upper bound on live bodies); (c) the client's outstanding count
  × D (upper bound, includes frames still in socket buffers); (d) surviving arms: the end-of-window class
  histogram (`[B` bytes, `Envelope` and `QueryMessage` counts).
- **Initiating failure (V5):** the HotSpot banner in `stdout.log` (`java.lang.OutOfMemoryError: Java heap space`,
  `-XX:OnOutOfMemoryError="kill -9 %p"`); the OOM thread's stack from the dump (predicted: an `epollEventLoopGroup`
  thread in `HeapArena.newByteArray` ← `PoolArena.allocateHuge` ← … ← `Compressor$LZ4Compressor.decompress:184` ←
  `Envelope$Decompressor.decode:539`; another allocating thread is possible when the heap is already full of
  bodies, then the holder evidence is the histogram); the GC log's last cycles (`Pause Full (G1 Humongous
  Allocation)` expected); the scope's `oom_kill` = 0 (not a kernel kill).
- Sampling: 500 ms is shorter than the predicted growth window at 2 GiB (≈ 1–5 s). JMX polling and the 1-s client
  line are not intrusive; the only forced GC is the end-of-window histogram after the readings.

### 2.7 Predicted response, stopping budget and time plan

| Arm (heap) | Predicted endpoint | Predicted readings |
|---|---|---|
| **T** (2,048 MiB) ×3 | **heap OOM 3/3** within 30 s of `FLOOD_START` (expected ≤ 10 s) | dump: ≥ 38 `byte[]` of 33,554,432 B (≥ 1.2 GiB, ≥ 60 % of the heap at the dump); `Envelope` ≈ `QueryMessage` ≈ that count ± E; **K at the last sample ≤ 10 MiB** (≈ 7 MiB predicted, < C = 51.7 MiB), `PausedConnections` 0; outstanding ≥ 40; λ ≥ 5/s; no `oom_kill` → **U > C, K ≤ C: bypass (accounting mismatch)** |
| **C1** (2,048 MiB) ×3 | **no OOM 3/3** over the 90 s window | K plateau 50–53 MiB with `PausedConnections` ≥ 1 and `ConnectionPaused` ≥ 1 (the limit acts); post-GC heap ≤ 0.8 GiB; end-of-window `[B` ≤ 0.5 GiB; completed count(*) ≥ 0.2/s |
| **I1** (2,048 MiB, patched, charge decompressed) ×3 | **no OOM 3/3** | K peaks ≥ 51.2 MiB (each request charged 32 MiB), `PausedConnections` ≥ 1 most of the window; post-GC heap ≤ 0.3 GiB + 8 × 32 MiB ≤ 0.6 GiB; completed count(*) per second within a factor 2 of C1 (CPU-bound in both) |
| **T2** (2,048 MiB) ×3 | **heap OOM 3/3** within 30 s of the single 13-byte frame | banner `Java heap space`; OOM thread stack through `Compressor.java:184`; dump heap ≈ baseline (the failed request is the cause, not a holder) |
| **C2** (2,048 MiB) ×3 | **no OOM 3/3** after 50 frames of L = 64 MiB | each frame → an ERROR response or a closed connection; post-GC heap back to baseline ± 50 MiB |
| **I2** (2,048 MiB, patched, cap) ×3 | **no OOM 3/3** | ERROR "B19: declared uncompressed length 2040109465 exceeds native_transport_max_frame_size"; the uncompressed probe then succeeds; the 32 MiB compressed request is refused (recorded) |
| T_4G / T_8G / T_15872 | OOM at 4 GiB (likely), 8 GiB (≈ 50 %), 15,872 MiB (unlikely: needs λ ≥ 41/s sustained) | K at OOM ≈ bodies × c; boundary arm: held ≈ λ × ≤ 12 s × D, `TimedOutBeforeProcessing` rising |
| S_vm (15,872 MiB, optional) | `Requested array size exceeds VM limit` → kill (diagnostic only) | — |

**Stopping budget.** Flood window 90 s per arm; ≤ 6 min wall per arm; client cap E × Q = 4 × 256 outstanding;
≤ 2 re-runs per arm for a harness/infra failure (an arm that ends `other` is re-run once, then reported);
≤ 30 arms in total; **no arm starts after 13:15 EST**; every process stopped and §3–§4 written by 14:00 EST. No
escalation after an OOM beyond the planned budget search.

**Time plan (EST, 2026-11-21).**

| Time | Step |
|---|---|
| 09:00–09:10 | read the case, check the freeze hash, check `ms0625` (no `CassandraDaemon`, free disk/RAM), source `diff` |
| 09:10–09:15 | start the patched build in the background (step 2) |
| 09:10–09:50 | harness: `ctl.sh`, `arm.sh`, `B19Client.java`, `B19Sample.java`, `b19peaks.py`, hprof scripts |
| 09:50–10:15 | template load (step 3), calibration and first-trigger checks, shakedown (step 4) |
| 10:15–10:55 | V arms T, C1, I1 × 3 at 2 GiB (9 × ≈ 4 min) |
| 10:55–11:25 | T2, C2, I2 × 3 (9 × ≈ 3 min); dump analysis of T runs between arms on cores 6–7 |
| 11:25–12:10 | budget search 4 → 8 → 15.5 GiB + 2 repeats at the largest failing heap |
| 12:10–12:25 | optional S_vm, P0 |
| 12:25–13:15 | slack for re-runs (last arm start 13:15) |
| 13:15–14:00 | independent self-check from raw files, §3–§4, write-backs, cleanup |

**Drop order (if behind):** (1) optional S_vm, P0; (2) the two repeats at the largest failing heap (single runs
stay, n/N = 1/1 reported); (3) T_15872; (4) T_8G; (5) I2 (T2 then carries "(no intervention)"); (6) C2 and T2 (T2
reported as not run). T, C1, I1 × 3 at 2 GiB are never dropped; if they cannot all run, the verdict is `retry`.

### 2.8 Controls and intervention

- **Matched control C1 (protected path):** the same E, Q, query, compression on, the same on-wire and charged size
  c (±1 %); only the decompressed size differs (≈ 131 KB instead of 32 MiB). The in-flight limit then covers the
  held bytes, pauses connections, and the node survives. This isolates the ratio decompressed/charged as the cause.
- **Intervention I1 (charge the decompressed length), patched build** — separate tree `/mydata/s4/B19/patched`,
  exact diff saved as `harness/b19-diagnostic.patch`; the original failure (T) runs on the unmodified build:

  ```diff
  --- a/src/java/org/apache/cassandra/transport/PreV5Handlers.java
  +++ b/src/java/org/apache/cassandra/transport/PreV5Handlers.java
  @@ public static class LegacyDispatchHandler extends SimpleChannelInboundHandler<Message.Request>
           private static final Logger logger = LoggerFactory.getLogger(LegacyDispatchHandler.class);
  +        // B19 diagnostic (I1): charge the decompressed body, not the compressed header length
  +        private static final boolean B19_CHARGE_DECOMPRESSED = Boolean.getBoolean("cassandra.b19.charge_decompressed");
  +        private static long b19Charge(Envelope e)
  +        {
  +            return B19_CHARGE_DECOMPRESSED ? Math.max(e.header.bodySizeInBytes, e.body.capacity()) : e.header.bodySizeInBytes;
  +        }
  @@ private void releaseItem(Flusher.FlushItem<Envelope> item)
  -            long itemSize = item.requestEnvelope.header.bodySizeInBytes;
  +            long itemSize = b19Charge(item.requestEnvelope);
               item.requestEnvelope.release();
  @@ private void checkLimits(ChannelHandlerContext ctx, Message.Request request)
  -            long requestSize = request.getSource().header.bodySizeInBytes;
  +            long requestSize = b19Charge(request.getSource());
  --- a/src/java/org/apache/cassandra/transport/Compressor.java
  +++ b/src/java/org/apache/cassandra/transport/Compressor.java
  @@ imports
  +import org.apache.cassandra.config.DatabaseDescriptor;
  @@ public static class LZ4Compressor implements Compressor
           private static final int INTEGER_BYTES = 4;
  +        // B19 diagnostic (I2): refuse a declared length above native_transport_max_frame_size before allocating
  +        private static final boolean B19_CAP_UNCOMPRESSED = Boolean.getBoolean("cassandra.b19.cap_uncompressed");
  @@ public Envelope decompress(Envelope compressed) throws IOException
                                      | ((input[3] & 0xFF));
  +
  +            if (B19_CAP_UNCOMPRESSED && (uncompressedLength < 0 || uncompressedLength > DatabaseDescriptor.getNativeTransportMaxFrameSize()))
  +            {
  +                compressed.release();
  +                throw new ProtocolException("B19: declared uncompressed length " + uncompressedLength + " exceeds native_transport_max_frame_size");
  +            }
  
               ByteBuf output = CBUtil.allocator.heapBuffer(uncompressedLength);
  ```

  (Hunk headers are descriptive; stage 2 writes the patch with real line numbers and saves the exact `diff -u`.)
  `body.capacity()` is the decompressed length for a decompressed body (`heapBuffer(uncompressedLength)`) and the
  body length for an uncompressed slice (`Envelope.java:447`), so I1 is neutral for uncompressed traffic; it is
  read before the release in `releaseItem`. Both properties default to false, so the patched build without a
  property behaves as 5.0.9 (optional P0). **I1 prediction:** each T request is charged 32 MiB; the first request
  per connection after the per-IP sum passes 51.2 MiB is still admitted and the connection paused (as at 5.0.9),
  and a paused channel stops reading after the current socket read (Netty's `continueReading` checks autoRead), so
  held bodies ≤ E × 2 = 8 (≤ 256 MiB) and the node survives. Throughput (completed count(*)/s) is recorded against
  C1's so a stopped workload is not mistaken for protection.
- **Intervention I2 (reserve/validate before allocation)** for T2: the cap hunk above; the 13-byte frame is
  refused before the allocation. It also refuses T's 32 MiB bodies (recorded; I2 is T2's intervention only).
- **Attribution for V5:** the banner, the OOM thread stack, and the dump histogram showing the 32 MiB `byte[]`
  population (T) or the failed size in the stack frame (T2).
- **Classification by measurement (domain R):** T predicted U ≥ 1.2 GiB > C = 51.7 MiB with K ≈ 7 MiB ≤ C →
  bypass, accounting mismatch (and allocation before the check). T2: U (requested 1.9 GiB) > C_F = 16 MiB, K = 13 B
  → bypass of the frame cap's intent by a client-declared length (known-open CASSANDRA-14997).

`sha256 of §1–§2 at freeze: bce25ab9b0475b096bad60e1e19f4752130034048fe691c64496379c82e91ea4` (sha256 of the bytes from the line `## 1. Candidate` up to, not including, this line) · amendments after the freeze: A1–A3 (stage 2, 2026-11-21), see §3.0.

## 3. Runs (stage 2)

Stage 2: a fresh OOM-agent session (Claude Opus 5.5, subagent), 2026-11-21 08:17–09:35 EST, on `ms0625`; every process stopped by 09:28. Freeze hash
re-computed at 08:18 EST: `bce25ab9…ea4`, **matches**.

### 3.0 Amendments (dated, each made before the readings it affects)

- **A1 (2026-11-21 08:22 EST) — source diff, design §2.5 "before step 1".** Cannot run as written:
  `/mydata/s4/cassandra-base` on `ms0625` is a copied build tree **without `src/`** (only `build/`, `lib/`, `conf/`,
  `bin/`, …). Replacement check: (a) `ms0611:/mydata/s4/cassandra-base/src/java/org/apache/cassandra/transport/`
  {`Compressor`, `Envelope`, `PreV5Handlers`, `Message`, `Dispatcher`, `CBUtil`, `Flusher`, `PipelineConfigurator`,
  `ClientResourceLimits`}`.java` md5 = the repository's `systems/cassandra/source/` copies (all 9 identical);
  (b) all **172** class files under `org/apache/cassandra/transport/` (incl. `messages/`) of `ms0625`'s jar
  (md5 `beb4d0c1…7c7`) are **byte-identical** to those of `ms0611`'s jar (md5 `1becab41…f1ab`; the two jars differ
  elsewhere, as HANDOFF notes). Result: no difference on the transport path; the case proceeds (record in
  `/mydata/s4/B19/srcdiff/`).
- **A2 (2026-11-21 08:24 EST) — patched build, design §2.5 step 2.** `ant jar` cannot run (no source tree in the copy;
  "never run `ant` in `cassandra-base`"). Instead: `cp -a /mydata/s4/cassandra-base /mydata/s4/B19/patched`; the
  repository's `Compressor.java` and `PreV5Handlers.java` with the §2.8 hunks
  ([`harness/b19-diagnostic.patch`](harness/b19-diagnostic.patch), exact `diff -u`) compiled with JDK 11.0.33
  `javac -g --release 11` against the build's jar and `lib/*`; the 8 resulting classes (`Compressor*`,
  `PreV5Handlers*`) replaced in the patched copy's jar with `jar uf`, and the stale copies in
  `build/classes/main` deleted. Patched jar md5 `fb9f5d7345a1299916ca85c0216c589b`; `grep -c b19` = 1 in
  `Compressor$LZ4Compressor.class`, 2 in `PreV5Handlers$LegacyDispatchHandler.class`. Same semantics as designed
  (both properties default false).
- **A3 (2026-11-21 08:35 EST) — template size, design §2.5 step 4.** Calibration at 1,000,000 rows: probe ×3 all
  **failed** at 5.0 s (`ReadFailure … 1 failures: UNKNOWN`; debug.log `QueryCancelledException: Query cancelled for
  taking too long`), so L1 > 10 s was taken and the frozen rule applied (rebuild with 300,000 rows). At 300,000 rows
  the probe still failed (5.0 s, 10.0 s, 5.0 s). Cause: with `cql_start_time: REQUEST` the whole `count(*)`
  aggregate (all internal pages) must finish within the read deadline (5 s), not 10 s as the frozen [1, 10] s window
  assumed; the rule has no step after 300,000. Amendment: template rows lowered to **100,000** so L1 lies in
  [1, 5) s. Re-calibration (2,048 MiB): probes 5,039 ms (cold, failed) / 2,490 / 2,330 ms with count 100,000 →
  **L1 = 2.49 s** (median). Everything else in the design is unchanged. (Effect: hold time per request ≈ the scan
  time under load; the design's other bound, `native_transport_timeout` 12 s, is unchanged.)

### 3.1 Environment (recorded)

| Item | Value |
|---|---|
| Node | `ms0625` (node0.jason92-326377, Utah m400), **aarch64**, 8 cores, 62 GiB RAM, 8 GiB swap (0 for the measured scope), kernel 5.15.0-191-generic, Ubuntu 22.04 |
| JDK | OpenJDK 11.0.33+9 (Ubuntu); G1; `G1HeapRegionSize` **16 MiB** (from `cassandra-env.sh`/jvm options; the design's T2 arithmetic assumed 1 MiB regions: 1.90 GiB = 122 of 128 regions at 2 GiB) |
| Build | `/mydata/s4/cassandra-base` jar md5 `beb4d0c1db2a0bbacc84e37158a9d7c7` (T, C1, T2, C2, budget search); `/mydata/s4/B19/patched` jar md5 `fb9f5d73…c589b` (I1, I2) |
| Resolved budgets | heap `MaxHeapSize` 2,147,483,648 at `-Xmx2048M`; **`MaxDirectMemorySize` 16,642,998,272 B = 15,872 MiB** (resolved by `cassandra-env.sh` on this 62 GiB node; the design predicted 7,936 MiB; direct memory is not claimed) |
| Scope | `systemd-run --user --scope -p MemoryMax=48G -p MemorySwapMax=0` (safety only; `memory.max` 51,539,607,552, `swap.max` 0 recorded per arm) |
| CPU | Cassandra `taskset -c 0-5`; client, sampler, `jcmd` on 6–7 |
| Template | 100,000 rows `b19.t (k int PRIMARY KEY, v int)`, one sstable, 3.6 MiB (A3) |
| Frame sizes (client) | `zero`: D = 33,554,432 B decompressed, **c = 131,638 B** compressed body (frame 131,647 B), ratio 254.9; `rand`: D = 131,116 B, c = 131,636 B (Δc = 2 B, 0.002 %) |
| First-trigger checks (2,048 MiB, before any arm) | `flood zero 1 1 5`: ROWS with count 100,000 (2 of 2 completed, `badcount` 0); `flood rand 1 1 5`: same; `bogus 67108864`: connection reset after 50 ms (`LZ4Exception: Malformed input`), node alive → **pass** |
| Shakedown (not a reading) | `flood zero 4 256 20` at 2,048 MiB: JVM gone 2.6 s after `FLOOD_START`, banner `java.lang.OutOfMemoryError: Java heap space`, K at last sample 3.39 MiB, λ first 5 s 38.4 frames/s; all instruments present (JMX columns, GC log, stdout banner) |

Raw data on the node: `ms0625:/mydata/s4/B19/runs/<arm>/` (`args.txt`, `samples.csv` (500 ms JMX), `cg.csv`,
`client.log`, `V-logs/{system,debug,gc,stdout}.log`, `V-flags.txt`, `V-cmdline.txt`, `V-yaml.diff`, `histo-end.txt`,
`hprofhist.txt`, `oome-thread.txt`, `outcome.txt`), `runs/summary.txt`, `runs/queue*.log`; calibration in
`runs/calib-1M/`, `runs/calib-300k/`, `runs/calib/`. Committed excerpts: [`logs/`](logs/) (`selfcheck.md` is the
independent re-read of every arm from raw files, by [`harness/selfcheck.py`](harness/selfcheck.py)). Harness:
[`harness/`](harness/) (`ctl.sh`, `arm.sh`, `queue.sh`, `q1–q4.txt`, `B19Client.java`, `B19Sample.java`, `cg.sh`,
`b19peaks.py`, `hprofhist.py`, `hprof_oome_thread.py`, `dumps.sh`, `template.sh`, `calib.sh`, `build.sh`, `cli.sh`,
`b19-diagnostic.patch`). Order run: q1 (T, C1, I1 interleaved ×3) 08:40–09:02; dumps; q2 (T2, C2, I2 ×3)
09:03–09:19; T_4G 09:19–09:22; optional P0, S_vm 09:24–09:28 EST. Every arm from a clean regenerated node and the
same 100,000-row template; one measured JVM at a time.

### 3.2 Condition T (valid LZ4 bodies, 32 MiB decompressed, c = 131,638 B charged) and its control and intervention, 2,048 MiB

| Arm | Outcome | JVM gone after `FLOOD_START` | K max / last (MiB) | Paused max / `ConnectionPaused` Δ | λ first 5 s / overall (frames/s) | Client out at end | Post-GC max (MiB) | U: 32 MiB `byte[]` | `oom_kill` |
|---|---|---|---|---|---|---|---|---|---|
| T_r1 | **heap OOM** (`Java heap space`, `kill -9`) | 3.6 s | 4.02 / 4.02 | 0 / 0 | 39.8 / 22.1 | 199 | 1,907 | dump: **36 = 1,152 MiB** (of 1,287 MiB live shallow); `Envelope` 37, `QueryMessage` 33 | 0 |
| T_r2 | **heap OOM** | 4.1 s | 4.02 / 4.02 | 0 / 0 | 38.2 / 19.1 | 191 | 1,897 | dump: **36 = 1,152 MiB** (of 1,293); 37 / 33 | 0 |
| T_r3 | **heap OOM** | 9.4 s | 4.27 / 4.27 | 0 / 0 | 36.2 / 18.1 | 181 | 1,895 | dump: **36 = 1,152 MiB** (of 1,289); 37 / 34 | 0 |
| C1_r1 | alive 90 s | — | 59.76 / 24.61 | 4 / 1,643 | 112.6 / 38.8 | 572 | 412 | end histogram `[B` 188 MiB total | 0 |
| C1_r2 | alive | — | 51.60 / 15.44 | 4 / 1,856 | 113.0 / 38.6 | 567 | 434 | `[B` 187 MiB | 0 |
| C1_r3 | alive | — | 58.12 / 22.97 | 4 / 1,848 | 112.8 / 38.8 | 580 | 388 | `[B` 186 MiB | 0 |
| I1_r1 (patched, charge decompressed) | alive (window and close) | — | **128 in window** / 896 after close | 4 / 158 | 29.6 / 3.3 | 148 | 2,006 (after close) | end histogram (75 s) `[B` 219 MiB | 0 |
| I1_r2 | alive in window; **heap OOM ≈ 3.5 s after the client closed** (last GC 93.5 s) | (≈ 98 s) | **160 in window** / 1,088 after close | 4 / 154 | 29.6 / 3.3 | 147 | 1,951 | dump: 37 = 1,184 MiB | 0 |
| I1_r3 | as r2 (last GC 93.6 s) | 99.9 s | **160 in window** / 928 after close | 4 / — | 32.0 / 3.4 | 161 | 1,888 | dump: 37 = 1,184 MiB | 0 |

- **Initiating failure (V5), T ×3:** HotSpot `java.lang.OutOfMemoryError: Java heap space` → `Dumping heap` →
  `Executing /bin/sh -c "kill -9 <pid>"` in `stdout.log`; the OOM thread (from the dump) is an event-loop thread in
  `PoolArena.allocateHuge` ← `AbstractByteBufAllocator.heapBuffer` ← **`Compressor$LZ4Compressor.decompress`
  (`Compressor.java:184`)** ← `Envelope$Decompressor.decode` (`Envelope.java:539`) ← `ByteToMessageDecoder` (3/3,
  [`logs/T_r1-oome-thread.txt`](logs/T_r1-oome-thread.txt)); last GCs `Pause Young … (G1 Humongous Allocation)
  …→1,9xxM(2048M)`; `oom_kill` 0 (not a kernel kill).
- **U vs K (V3):** the dump holds 36 decompressed bodies (1,152 MiB = 56 % of the heap, 89 % of live shallow bytes)
  while the in-flight counter read 4.02–4.27 MiB = 32–34 × c (the bodies charged at their compressed size); no
  connection was ever paused. **U/K ≈ 287.** Predictions: "OOM 3/3 within 30 s" met; "K ≤ 10 MiB" met; "≥ 38 bodies,
  ≥ 60 % of the heap" slightly missed (36, 56 %).
- **C1 (same E, Q, c ± 2 B; decompressed 131 KB):** the per-IP limit acted: K plateaued at 51.6–59.8 MiB (= limit
  + force-admits), 4 connections paused, 1,643–1,856 pause events; post-GC heap ≤ 434 MiB; alive 3/3. Deviation from
  the predicted readings: **no count(*) completed** in C1 (all responses were ERROR: `ReadFailure` "1 failures:
  UNKNOWN" = scans cancelled at the 5 s deadline under 32-way concurrency, and `ReadTimeout`, 480–536 and 2,380–2,426
  per run; C1_r1's codes were mislabelled by the then client, below). The node stayed alive and responsive; the
  prediction "≥ 0.2 count(*)/s" was not met.
- **I1 (charge the decompressed length):** during the 90 s flood the counter now sees each body (32 MiB charge):
  K pinned at **128–160 MiB** (one force-admitted body per paused connection, + one), 4 connections paused the
  whole window, old gen ≤ 734 MiB, **143–149 count(*) completed** (≈ 1.6/s, more than C1's 0, so the intervention did
  not stop useful work). The design's "no OOM 3/3" prediction **failed** for the arm as a whole: when the client
  closed its 4 sockets at t = 90 s (≈ 150 frames still unanswered), the server drained the frames buffered in the
  sockets, decompressed and admitted them (K → 896–1,088 MiB, Native-Transport-Requests active 4 → 27) and ran out
  of heap 3.5 s later in 2 of 3 runs. The OOM thread is the same site (`Compressor.java:193` in the patched file =
  `:184` + 9 patch lines; [`logs/I1_r2-oome-thread70.txt`](logs/I1_r2-oome-thread70.txt)), on an epoll read task
  (`AbstractEpollUnsafe$1.run` → `epollInReady`). I1 moves the charge, not the check: frames that are read after a
  pause (here at peer close) are still decompressed before any check.
- **P0** (patched build, no property, `DUMP=0`): heap OOM 3.6 s after `FLOOD_START` (`# java.lang.OutOfMemoryError:
  Java heap space`, `kill -9`), K 3.64 MiB → the patched build without a property behaves as 5.0.9.

### 3.3 Condition T2 (one 13-byte body declaring L = 2,040,109,465), its control and intervention, 2,048 MiB

| Arm | Frames | Outcome | JVM gone after the frame | Live heap in the dump | OOM thread | Post-GC max (MiB) |
|---|---|---|---|---|---|---|
| T2_r1 | 1 × 22 B | **heap OOM** (`Java heap space`, `kill -9`) | 0.3 s | 84 MiB | `Compressor.java:184` ← `Envelope$Decompressor.decode:539` | — |
| T2_r2 | 1 | **heap OOM** | 0.4 s | 78 MiB | same | — |
| T2_r3 | 1 | **heap OOM** | 0.4 s | 84 MiB | same | — |
| C2_r1 (L = 64 MiB) | 50 × 22 B, fresh connection each | alive; each frame → `LZ4Exception: Malformed input`, connection reset | — | — | — | 846 (back to 410) |
| C2_r2 | 50 | alive | — | — | — | 868 (410) |
| C2_r3 | 50 | alive | — | — | — | 951 (410) |
| I2_r1 (patched, cap) | 1 | alive; `ProtocolException: B19: declared uncompressed length 2040109465 exceeds native_transport_max_frame_size`, reset | — | — | — | 121 |
| I2_r2 | 1 | alive; same | — | — | — | 121 |
| I2_r3 | 1 | alive; same | — | — | — | 121 |

Under I2 the following uncompressed `probe` succeeded (count 100,000 in 2,684 / 3,168 / 2,898 ms), and the 32 MiB
`zero` request was refused with the same `ProtocolException` (recorded: I2 also refuses condition T's valid bodies).
Every T2 run ended in under half a second from one 22-byte frame from an unauthenticated connection; the heap was at
baseline (78–84 MiB live), so the requested allocation itself is the cause, not a holder.

### 3.4 Budget search (condition T, upward) and optional arms

| Arm | Heap | Outcome | Readings |
|---|---|---|---|
| T_4G | 4,096 MiB | **alive** over the 90 s window (boundary) | K ≤ 8.16 MiB, paused 0; post-GC heap up to **4,035 MiB** (one evacuation failure → `Pause Full` 4,056 → 1,686 MiB at ≈ 85 s); STW ≤ 2.8 % of any 60 s (no service loss); end histogram (76.5 s) `[B` 2,180 MiB (≈ 68 bodies) with K = 3.8 MiB; 704 frames sent, 0 count(*) completed (365 `ReadFailure`, 137 `ReadTimeout`); `TimedOutBeforeProcessing` Δ 0; λ first 5 s 37.8/s, overall 7.8/s |
| T_8G, T_15872 | — | not run | design step 7: run only if the previous heap failed |
| repeats at the largest failing heap | — | not needed | the largest failing heap is 2,048 MiB, already 3/3 |
| S_vm (optional, diagnostic) | 15,872 MiB | **OOM** `Requested array size exceeds VM limit` → `kill -9`, 0.3 s after one 22-byte frame (L = 2³¹ − 1) | not budget exhaustion; not counted for V7 |
| P0 (optional) | 2,048 MiB | heap OOM 3.6 s | see §3.2 |

Largest failing heap for T: **2,048 MiB, 3/3**; at 4,096 MiB the node survived 1/1 with the heap repeatedly near full
(held ≈ λ × hold ≈ 68 bodies ≈ 2.1 GiB while K stayed ≤ 8 MiB).

### 3.5 Deviations and harness fixes (none changes a reading)

- Amendments A1–A3 (§3.0).
- After T_r1: the outcome line's banner `grep` matched a JVM option line; fixed (outcome text only; classification
  was correct). After C1_r1: the client did not strip the v4 **warnings** prefix (flag 0x08) from responses, so
  C1_r1's error codes were printed as `0x1002c`/`0x20070` (the warning list) instead of `ReadFailure`/`ReadTimeout`;
  fixed in a new class dir (`cls2`), switched atomically between arms; the server-side readings and counts are
  unaffected. `b19peaks.py`: GC-log lines carry no tag decorator and rotated files must be read by mtime; fixed
  before the readings were tabulated (affects only the post-GC/STW columns, recomputed for every arm).
- `arm.sh` classifies an OOM by `^java.lang.OutOfMemoryError` in `stdout.log`; with `DUMP=0` HotSpot prints only the
  `# java.lang.OutOfMemoryError` form, so P0 and S_vm were tagged `other` in `summary.txt`; both are OOM kills
  (`selfcheck.md`).
- The I1 arms' OOM happened after the 90 s flood window, on the client's socket close; the arm protocol (10 s idle
  observation) recorded it as designed.
- `MaxDirectMemorySize` resolved to 15,872 MiB (design: 7,936 MiB); `G1HeapRegionSize` 16 MiB (design arithmetic:
  1 MiB). Neither is claimed; T2 still failed (1.90 GiB = 122 of 128 regions).
- C1 completed no count(*) (scans cancelled at 5 s under 32-way load); predicted ≥ 0.2/s.

### 3.6 Classification by measurement (protection map §2.2)

| Domain | Condition | U (independent) | C (contract) | K | Class |
|---|---|---|---|---|---|
| R (pre-v5 bodies of one IP) | T, 2 GiB | 1,152 MiB (dump, 36 × 32 MiB) | 51.7 MiB | 4.02–4.27 MiB | **U > C, K ≤ C → bypass, accounting mismatch** (charged compressed, held decompressed; U/K ≈ 287) |
| R | T, 4 GiB | ≈ 2,180 MiB `[B` (histogram) | 102.9 MiB | ≤ 8.2 MiB | same (no OOM at 4 GiB within 90 s) |
| F (frame cap) + R | T2 | 1,945.6 MiB requested (`heapBuffer(2040109465)`) | 16 MiB per frame | 0 (never charged: allocation precedes `checkLimits`) | **bypass, allocation before any check** (client-declared length) |
| R under I1 | in window | ≤ 160 MiB | ≈ 51.2 MiB + E force-admits (4 × 32 MiB) | 128–160 MiB | within contract (force-admit soft overshoot) |
| R under I1 | client-close drain | 896–1,184 MiB | same | 896–1,088 MiB | U > C, K > C: late enforcement (each drained frame force-admitted after decompression) |

### 3.7 Verification table

| | Condition T (valid bodies) | Condition T2 (declared length) |
|---|---|---|
| V1 repetition | **3/3** heap OOM at 2,048 MiB (T_r1–r3) | **3/3** heap OOM (T2_r1–r3) |
| V2 matched control | C1 alive **3/3** (same c, same E/Q; per-IP limit pauses) | C2 alive **3/3** (50 × L = 64 MiB each) |
| V3 measurement | dumps: 36 × 32 MiB vs K 4.0–4.3 MiB; post-GC series; end histograms in controls | requested size in the OOM stack frame; dump heap at baseline |
| V4 intervention | **partial**: I1 removes the endpoint during the 90 s flood **3/3** (T dies at 3.6–9.4 s; I1 holds K ≤ 160 MiB, serves 1.6 count(*)/s), but OOMs **2/3** on the client-close drain after the window (I1 charges after decompressing; frames read after the pause are still decompressed unchecked) | **met**: I2 alive **3/3**, useful work still served (uncompressed probe OK) |
| V5 initiating failure | banner + `kill -9`; OOM thread at `Compressor.java:184` (3/3); dump histogram with the holder | banner + `kill -9`; OOM thread at `Compressor.java:184` (3/3) |
| V6 default constraints | all at shipped defaults (yaml diff: environment keys only) | same |
| V7 acceptable budget | 2,048 MiB heap (standing rule, ideal); largest failing heap 2,048 MiB (4,096 MiB survived 1/1) | 2,048 MiB heap |

## 4. Conclusion (stage 2)

**Verdict: true positive.**

| Condition | Protocol status (detail) |
|---|---|
| **T2** — one 13-byte LZ4 body declaring 1.90 GiB | **`verified-OOM · deployment`** (bypass: allocation sized by a client-declared length before any check; known-open CASSANDRA-14997; the input is a forged/corrupt LZ4 length from an unauthenticated client) |
| **T** — valid 255:1 LZ4 bodies charged at their compressed size | V1–V3, V5–V7 met; **V4 partial** (I1 removes the in-window endpoint 3/3 but not the close-drain OOM, 2/3). Strictly **`candidate`** (V4 as designed not met); `verified-OOM · deployment` if the owner accepts the in-window removal as V4 |
| T at 4,096 MiB | no OOM within 90 s (1/1): the budget boundary, not a negative |
| S_vm | `Requested array size exceeds VM limit` kill at 15,872 MiB from one frame — diagnostic note, not a V7 budget result |

**Reason.** At shipped defaults and a 2 GiB heap, Cassandra 5.0.9 on protocol v4 with LZ4 negotiated in STARTUP
(no authentication needed with the default authenticator) died with `OutOfMemoryError: Java heap space` in every
run of both conditions. **T2:** a single 22-byte frame whose body declares an uncompressed length of 2,040,109,465
made `LZ4Compressor.decompress` call `heapBuffer(2040109465)` before any validation (`Compressor.java:184`), and the
JVM was killed 0.3–0.4 s later (3/3); 50 frames declaring 64 MiB were each refused after a transient allocation and
the node survived (3/3); refusing a declared length above `native_transport_max_frame_size` before allocating (I2)
removed the failure (3/3) with normal queries still served. **T:** 4 connections sending valid LZ4 QUERY frames of
131,638 B that decompress to 32 MiB filled the heap in 3.6–9.4 s (3/3): the dumps held 36 decompressed bodies
(1,152 MiB) while `native_transport_max_request_data_in_flight[_per_ip]` counted 4.0–4.3 MiB (the compressed sizes)
and never paused a connection; the same traffic with incompressible 131 KB bodies (same charged size) made the
per-IP limit pause all 4 connections at ≈ 52–60 MiB and the node survived (3/3). Charging the decompressed size (I1)
held the in-flight counter at 128–160 MiB with all connections paused for the whole 90 s load (3/3), but when the
client then closed its sockets the server drained and decompressed the buffered frames before charging them and ran
out of heap in 2 of 3 runs: the accounting fix alone is not a complete intervention, because the allocation still
happens before the check. The budget search found 2 GiB as the largest failing heap for T; at 4 GiB T survived the
90 s window (post-GC peak 4,035 MiB). The case verdict rests on T2 (V1–V7 met) with T as strong supporting evidence
for the claimed accounting mismatch (U/K ≈ 287 measured).

**Limits of attribution.** T2 needs a forged LZ4 length (corrupt input; the stage-1 skip list names "needs corrupt
input" — owner's call whether that weighs against the verdict; it is the exact claim of the OC-533 row and of the
known-open CASSANDRA-14997). T's endpoint at 2 GiB is reached by the initial burst (≈ 190 frames sent in the first
second, ≈ 36 decompressed before the heap filled); at 4 GiB the hold time (scans cancelled at 5 s) bounded the held
set to ≈ 2.1 GiB. One ARM node (aarch64), colocated client. C1 completed no queries (scans timed out under load),
so its survival is not a throughput match. Clue patterns: T2 = CP-13 (allocation size from untrusted input; already
cites 14997), T = CP-1 (counted unit ≠ held memory) and CP-11 (enforcement after the allocation); no new pattern
needed.

**For a later case (not a retry of this verdict):** an intervention for T that reserves the declared uncompressed
length against the in-flight limits **before** `heapBuffer` (in `Envelope.Decompressor`, refusing or deferring the
frame) would close both the in-window and the close-drain paths; the close-drain over-admission under I1 (frames read
from a paused v4 channel at peer close, each force-admitted) is a holder path the design did not claim (proposed to
the owner, §3.2).
