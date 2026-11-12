# B1 design — native protocol v5 large-request retention (bypass · release-defect), run 1

Dated **2026-11-11**, written before any reading of this run. Amendments below are dated and
appended before the readings they affect. Protocol: [`verification-protocol.md`](../../../../../verification-protocol.md)
(V1–V7, standing budget rule 2026-11-11); playbook: [`bypass-playbook.md`](../../../../../bypass-playbook.md)
(ownership/release-defect row); queue row B1 / P1 of [`campaign-plan.md`](../../../../campaign-plan.md).

## 0. Lead and source label

Source: if-check inventory (`capacity-enforcement-exp`). The lead is the derived and observed
"large native-v5 requests never return their frame buffers" of
[`networking_cache_size` stage 3 §6b/§10](../../../../../../capacity-enforcement-exp/cassandra/stage3-ai-deep-read/cases/networking_cache_size-allocateMoreChunks-memoryUsageThreshold--guided.md)
and its [stage-4 arm L](../../../../../../capacity-enforcement-exp/cassandra/stage4-runtime-verification/results/networking_cache_size-allocateMoreChunks-memoryUsageThreshold--guided.md)
(one lifetime, 64 one-MB v5 INSERTs: `OverflowSize` +58,724,288 B = 64 × 7 × 131,081, pooled
`UsedSize − OverflowSize` +5,373,952 B = 64 × 83,968, never returned; `java.nio` direct fell back after
`GC.run` while `OverflowSize` did not). Corroboration: `native_transport_receive_queue_capacity` large
arms (`OverflowSize` 4.9 GB, never fell); the in-flight case's V5/256K arm (+780–820 MiB direct in 90 s
at every limit). No JIRA ticket found (2026-10-15 search; CASSANDRA-20753 is a different, fixed path).

## 1. Source audit (Cassandra 5.0.9, `systems/cassandra/source/`, `build.xml` base.version 5.0.9)

Path of a v5 request whose envelope is ≥ one frame payload (131,071 B):

1. `AbstractMessageHandler.LargeMessage.onIntactFrame` (`net/AbstractMessageHandler.java:565-579`) keeps
   every frame as `frame.contents.sliceAndConsume(frame.frameSize).share()` in `buffers`; each slice
   holds one count on its owner `ShareableBytes` (a networking-pool buffer: a read buffer from
   `BufferPoolAllocator`, or the decoder's stash for a frame that spans reads).
2. `CQLMessageHandler.LargeMessage.onComplete` (`transport/CQLMessageHandler.java:821-835`) on the
   normal path calls `processRequest(assembleFrame(), backpressure)` and nothing else.
   `assembleFrame()` (`:762-771`) wraps the buffers with `Unpooled.wrappedBuffer(ByteBuffer...)`, which
   does not own them; `body.retain()`.
3. `processRequest` (`:385-391`) decodes synchronously (`CBUtil.readValue` copies values to heap
   `byte[]`, `CBUtil.java:443-450`) and dispatches. On flush, `release(FlushItem)` (`:498-503`)
   returns the in-flight capacity (`releaseCapacity(bodySize)`) and `requestEnvelope.release()`, which
   only drops the Netty wrapper's count.
4. `releaseBuffers()` (`net/AbstractMessageHandler.java:593-596`), the only place the slices are
   released, is reached from `abort()`, `onCorruptFrame()` and expiry, not from `onComplete()`.
   The self-contained path releases its frame after decoding; the internode twin releases in
   `InboundMessageHandler.deserialize` (`ChunkedInputPlus.close()`).
5. Consequence (`net/ShareableBytes.java:127-140`): the owner count never reaches `RELEASED`, so
   `BufferPools.forNetworking().put(bytes)` never runs:
   - **pooled** owner (≤ `NORMAL_CHUNK_SIZE` 128 KiB, e.g. the last partial frame's stash or a read
     buffer): its slots stay allocated in the chunk; the networking pool has `recyclePartially = false`,
     so the chunk never returns to the global pool. The global pool allocates new 8 MiB macro chunks
     until `memoryAllocated` reaches `networking_cache_size`, then **every later networking buffer is
     an overflow `ByteBuffer.allocateDirect`** (`BufferPool.java:443-450, 923`).
   - **overflow** owner (a full-frame stash of 131,081 B > 128 KiB): an unpooled `allocateDirect`
     buffer; `overflowMemoryUsage` is never decremented, but the buffer becomes unreachable once the
     `LargeMessage` (handler field nulled at `AbstractMessageHandler.java:260`) and the request are
     gone, so its Cleaner frees it at the next GC. `ByteBuffer.allocateDirect` triggers `System.gc()`
     when `MaxDirectMemorySize` is reached (`DisableExplicitGC` is not set in `conf/jvm*-server.options`).
6. Native-transport capacity controls: `native_transport_max_request_data_in_flight` (global, default
   heap/10) and `_per_ip` (heap/40) are charged `bodySizeInBytes` at the first frame and returned at
   flush — not drifted by this path. `native_transport_max_message_size` (derived 16 MiB) gates size
   per request. None of them charges the frame buffers after flush.

**Audit verdict: reachable retention exists**, so the run proceeds. The source predicts:
(a) live pooled residual growing linearly with large requests and **plateauing at the networking pool's
cap** `networking_cache_size` (resolved 128 MiB at a 2 GiB heap); (b) `OverflowSize`/`Size`/`UsedSize`
gauges drifting up by ≈ 917,567 B per 1 MB request **without bound** while the physical overflow bytes are
GC-reclaimable (accounting drift); (c) no drift in `RequestsSize` (in-flight counter). Physical
memory past a control's contract is therefore **not** predicted: the leaked pooled bytes stay inside the
networking pool's retention cap. The case name uses `networking_cache_size`, the cap that charges the
retained bytes; the in-flight limits are recorded as not involved (prediction (c)).

## 2. Protection map

| Domain | Allocation / owner / release | Local contract (C) | Scope | Aggregate coverage | Lifetime | Budget |
|---|---|---|---|---|---|---|
| D1 networking pool, pooled slots | `BufferPool` networking instance; read buffers and ≤ 128 KiB stashes; release via `ShareableBytes` → `put` | `networking_cache_size` (default min(128 MiB, heap/16)): cap on chunks the pool reserves (a retention cap; overflow above it) | node-wide, one pool | none beyond the pool cap | should be transient; leaked slots pinned for JVM life | JVM direct (`MaxDirectMemorySize`), NMT `Other` |
| D2 networking overflow stashes | `allocateDirect` 131,081 B per full frame; release via `put` (`FileUtils.clean`) or GC Cleaner | none (overflow is unbounded by design); counted in `OverflowSize` | per frame | `native_transport_max_request_data_in_flight` while in flight only | until GC after the leak | JVM direct |
| D3 in-flight request bytes | `ClientResourceLimits` global/endpoint reserve | heap/10 global, heap/40 per IP | node / client IP | soft: one large request per connection can exceed when admitted | acquire at first frame, release at flush | — (counter) |

K per domain: D1 `UsedSize − OverflowSize` (pool counter), D2 `OverflowSize`, D3 `RequestsSize`.
U (independent): `java.nio:type=BufferPool,name=direct` MemoryUsed and NMT `Other` committed, read
after an idle window **before and after** `jcmd GC.run`; process RSS.

## 3. Configuration and budget

- Build: `apt140:~/cassandra-b1` (5.0.9, `src/` identical to the pristine copy `~/oom-src-pristine`,
  built 2026-11-09 for C1). Intervention build: a copy at `apt140:/mydata/b1/cassandra-patched` with the
  saved diff `harness/patch-release-large-buffers.diff` only.
- Conf: pristine `conf/` copied to `apt140:/mydata/b1/conf`; changes: addresses (10.10.1.1 listen/rpc/
  seed), directories under `/mydata/b1/node` (environment). **All capacity settings at defaults (V6):**
  `networking_cache_size`, `native_transport_max_request_data_in_flight(_per_ip)`,
  `native_transport_max_message_size`, `native_transport_receive_queue_capacity` untouched.
- Budget (V7 standing rule): heap **2 GiB** (`MAX_HEAP_SIZE=2G`, ideal), `MaxDirectMemorySize` **2 GiB**
  for the cycle arms. Resolved defaults at 2 GiB heap: `networking_cache_size` 128 MiB, in-flight
  204.8 MiB global / 51.2 MiB per IP, max message size 16 MiB. What `cassandra-env.sh` would resolve on
  this 16 GiB node: heap ≈ 7.9 GiB (½ RAM), direct ≈ 3.9 GiB (¼ RAM); networking pool still 128 MiB.
  No cgroup limit (swap present but unused; recorded). Both budgets ≥ 512 MiB: V7 met without review.
- Instrumentation: `-XX:NativeMemoryTracking=summary` (supporting, measurement only), GC log (default
  from `cassandra-env.sh`), JMX sampler at 1 s on the victim. No Byteman, no patches in S/H arms.
- Client `apt138` (10.10.1.3), bundled Python driver 3.29.0 from `~/cassandra-c1/lib`, no LZ4 module
  (no compression). **Preflight:** the client prints the negotiated `protocol_version`; the server's
  `ClientsByProtocolVersion` / pool movement confirms v5 vs v4.

## 4. Arms (each a fresh JVM, fresh data directory, same build/budget unless stated)

Cycle = R = 200 prepared `INSERT INTO b1.t (pk, v) VALUES (?, ?)` (pk = i mod 64, one connection,
4 requests in flight), wait for all acknowledgements, idle 20 s, read K and U (pre-GC), `jcmd GC.run`,
5 s, read again (post-GC). K = 12 cycles (2,400 requests) per lifetime. Baseline reading (cycle 0)
after the schema is created over v4 and a 20 s idle.

| Arm | Build | Protocol | Value | Role |
|---|---|---|---|---|
| S | unmodified | v5 | 1,000,000 B | suspect path |
| H4 | unmodified | v4 | 1,000,000 B | healthy path, same payload (v4 does not use the networking pool for requests) |
| H5s | unmodified | v5 | 100,000 B | healthy release on v5 (self-contained frames) |
| I | patched | v5 | 1,000,000 B | restored release (intervention) |
| P | unmodified | v5 | 1,000,000 B | OOM probe: no forced GC, 8 client processes × 4 in flight, 10 min; budget search below |

Each of S, H4, H5s, I runs ×3 from clean starts (V1, V2, V4).

## 5. Predictions (per 1 MB v5 request, from arm L)

- S: post-GC pooled residual (`UsedSize − OverflowSize`) +83,968 B/request until the pool's
  `Size − OverflowSize` reaches 128 MiB (≈ cycle 8, ≈ 1,600 requests), then flat (**plateau at C**);
  `OverflowSize` +917,567 B/request before the plateau, ≈ +1,001,535 B after (linear, no bound;
  ≈ 2.2 GB after 12 cycles); post-GC `java.nio` direct and NMT `Other` rise by ≈ the pooled residual
  (≤ 128 MiB + ≤ 16 MiB slack) and are flat after the plateau; `RequestsSize` 0 at every idle.
- H4, H5s: pooled and overflow residuals ≈ 0 (≤ one 8 MiB macro chunk), no trend with cycles.
- I: as H5s (residual ≈ 0, no trend). Throughput within 20% of S.
- Endpoint classification: if S plateaus at C with U ≤ C + slack → **release defect confirmed
  (capacity loss + accounting drift), no physical overshoot**; per the protocol table U ≤ C is not a
  memory bypass, so the memory result is `negative` (no overshoot, no OOM) within the tested range,
  with the defect recorded. If post-GC U grows past C + 16 MiB with cycles → **accumulating leak,
  U > C, K ≤ C** (`verified-gap` candidate). If post-GC U returns to baseline → allocator/GC
  retention only.

## 6. OOM / budget search (arm P)

Start at heap 2 GiB / direct 2 GiB. The question is whether the leak can drive the JVM to a direct or
heap OOM at any acceptable budget. Prediction: no — after the pool plateau the residual is fixed
(≤ 128 MiB) and overflow garbage is reclaimed by the `System.gc()` in `Bits.reserveMemory`. Plan:
P at 2 GiB direct ×1; if no OOM, P at the **smallest acceptable** direct budget, 512 MiB (heap 2 GiB),
×3 — the hardest acceptable case; if that does not fail, no larger budget will (the residual does
not depend on the direct limit), and the search ends with "no failing budget ≥ 512 MiB". If 512 MiB
fails, step up 1 → 2 → 4 GiB (×3 at the largest failing value) and add a v4 control (P-H4) at the
failing budget.

## 7. Stop conditions and limits

Wall time ≤ **6 hours** from the first node start; ≤ 30 Cassandra lifetimes. No escalation after an
OOM beyond §6. Stop an arm on client errors > 1% (record; invalid), on `failed to allocate` or any
`OutOfMemoryError` (record, keep `hs_err`/dump). Disk: commit log and data on `/mydata` (1.7 TB free).
Cleanup: stop every run-owned JVM/sampler/client on both nodes by PID; verify with `pgrep -a java`.
Raw logs: `apt140:/mydata/b1/runs/<arm>-<n>/`, `apt138:/mydata/b1/runs/<arm>-<n>/`, controller copies
in the case `logs/` (small excerpts only).

## Amendments

- **2026-11-12 02:33Z (smoke, no readings used):** PID taken from `$!`; sampler launched outside a subshell.
- **2026-11-12 03:10Z (after S-1, before S-2):** NMT total committed appended to each reading (RSS rose while
  NMT `Other` stayed flat). S-1 lacks the column.
- **2026-11-12 03:29Z:** the controller was stopped at a tool time limit during I-1 cycle 1; that lifetime is kept as
  `runs/I-1-aborted` and unused. I-1 rerun from a clean start; remaining arms unchanged (`batch-cycles2.sh`).
- **2026-11-12 07:00Z (before the probes):** `System.trim_native_heap` reading added at the end of each probe
  (allocator-retention check). After P-512M-1..3 showed about 125 explicit Full GCs, one intervention probe
  PI-512M-1 (patched build, 512 MiB, n=1) was added to attribute them. The session was paused 05:05–07:00Z
  by a usage limit with nothing running. Wall time from the first node start (02:33Z) to cleanup (≈ 08:20Z):
  ≈ 5 h 47 min, including the pause; 22 Cassandra lifetimes (4 smoke starts, 13 cycle lifetimes incl. the aborted I-1, 5 probes). Within the § 7 limits.
