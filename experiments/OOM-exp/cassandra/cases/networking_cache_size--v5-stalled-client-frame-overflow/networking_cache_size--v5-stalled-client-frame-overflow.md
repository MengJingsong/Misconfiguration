# B13 — networking_cache_size: a stalled protocol-v5 client makes the node hold every response frame in unbounded overflow  <!-- file: cassandra/cases/networking_cache_size--v5-stalled-client-frame-overflow/networking_cache_size--v5-stalled-client-frame-overflow.md -->

| Field | Value |
|---|---|
| Case ID | `B13` (B = bypass: the networking `BufferPool`'s overflow path is outside its limit; README "ID prefixes") |
| From | `OC-57` of the phase 1 OOM candidate list (the v5 remainder of N1; the v4 form is C2) |
| Phase-1 case file | [`networking_cache_size-allocateMoreChunks-memoryUsageThreshold--guided`](../../../../capacity-enforcement-exp/cassandra/stage3-ai-deep-read/cases/networking_cache_size-allocateMoreChunks-memoryUsageThreshold--guided.md) |
| System / pinned source | Cassandra 5.0.9 (`systems/cassandra/source/`, tag `cassandra-5.0.9`, unpatched); runs on the build `ms0617:/mydata/s4/cassandra-base` (`git describe` = `cassandra-5.0.9`, jar `build/apache-cassandra-5.0.9-SNAPSHOT.jar` sha256 `e55f4f29…5a942`, checked read-only 2026-11-18 08:01 EST) |
| Stage 1 (design) | OOM agent stage 1 (Claude Opus 5.5, workflow subagent), 2026-11-18 07:55–08:45 EST |
| Stage 2 (verify) | fresh OOM-agent session (Claude Opus 5.5, workflow subagent), 2026-11-18 08:11–09:10 EST, ms0617 (aarch64); 16 lifetimes 08:19–09:01 |
| Verdict | **true positive** — `verified-OOM · deployment` (bypass, accounting omission) |

## Summary

- **Conclusion:** true positive, `verified-OOM · deployment`. At shipped defaults with heap 2 GiB and direct 2 GiB,
  16 protocol-v5 clients that send paced reads of a 3.5 MiB partition and never read made the node throw
  `OutOfMemoryError: Direct buffer memory` from `BufferPool.allocate` on the event loop at ≈ 38 s in 3/3 runs, then the
  JVM was killed (forced heap OOM). Control with a quarter of the requests: 0/3. Intervention (defer requests for
  unwritable channels): 0/3. The OOM was also reached at direct 4 / 7.75 / 15.5 GiB (the node's auto value).
- **Root cause (measured):** the `networking` pool stopped at its 128 MiB cap (K = 128 MiB), and every later response
  frame went to the unchecked `allocateDirect` overflow. Those frames are held in `ChannelOutboundBuffer` until a
  socket write that never comes: 1,990 MiB at failure, 16,546 queued frames. Nothing checks channel writability, and
  request permits are returned once a response is framed, so `MaxDirectMemorySize` is the only bound.
- **Claimed root cause (stage 1, now confirmed):** over native protocol v5 every response is copied into 128 KiB frames taken
  from the `networking` `BufferPool`. `networking_cache_size` (default min(128 MiB, heap/16)) caps only the pool's
  8 MiB slabs; past it each frame is a plain `ByteBuffer.allocateDirect` counted in `OverflowSize`, which nothing
  checks. Frames are freed only when Netty writes them to the socket, no transport code checks `isWritable()`, and
  the request's in-flight permits are returned once the response is framed. So a client that keeps sending requests
  but stops reading makes the node hold every response frame until `-XX:MaxDirectMemorySize` throws
  `OutOfMemoryError: Direct buffer memory`.

## 1. Candidate

**Row (phase 1 OOM candidate list, `capacity-enforcement-exp/cassandra/stage5-oom-clue-find/phase1-oom-candidates.md`),
quoted:**

> | OC-57 | 2026-11-17 | `networking_cache_size-allocateMoreChunks-memoryUsageThreshold--guided` | legacy | [lead list, back-link, E2, new; N1's v5 remainder] Over protocol v5 a client that stops reading makes the node hold every response frame in the networking pool and then in unbounded `allocateDirect` overflow (no `isWritable`, permits returned once framed), limited only by `MaxDirectMemorySize`; stage 4 saw a ≈ 183 MiB rise at every knob value. | CP-5, CP-6 | picked: B13 |

**Phase-1 constraint and check.** `networking_cache_size` (`Config.java:493-494`; unset → `min(128 MiB,
maxMemory/16)`, `DatabaseDescriptor.java:573-574`; yaml `conf/cassandra.yaml:730-738`: "Maximum memory to use for
inter-node and client-server networking buffers") is the threshold of the `networking` pool
(`BufferPools.java:44-45`, `recyclePartially = false`). The check `BufferPool$GlobalPool.allocateMoreChunks():443`
(`cur + MACRO_CHUNK_SIZE > memoryUsageThreshold`) refuses another 8 MiB slab; the caller then allocates the same
bytes unpooled (`LocalPool.get():923` → `BufferPool.allocate():233-239`, `updateOverflowMemoryUsage(size)` then
`ByteBuffer.allocateDirect(size)`). The overflow counter is compared with nothing. Phase-1 recheck (2026-11-17,
back-link from C2) flagged E2: on the v5 response path no transport code reads channel writability,
`Flusher.writeAndFlush` writes every frame at once (`Flusher.java:201-206`, called from `flushLargeMessage`
`:163-199` and `FlushBuffer.finish` `:294-314`), and the request's permits are returned once the response is
framed (`Flusher.flushWrittenChannels` `:225-260` → `CQLMessageHandler.release` `:500-510`).

**Stage-4 result** ([`results/networking_cache_size-allocateMoreChunks-memoryUsageThreshold--guided.md`](../../../../capacity-enforcement-exp/cassandra/stage4-runtime-verification/results/networking_cache_size-allocateMoreChunks-memoryUsageThreshold--guided.md),
run 1, 2026-10-15, `pc57` x86_64, heap 4 GiB, direct 8 GiB, one stalled v5 client holding 192 one-MiB responses):
the pool stopped exactly at T′ = 16 · 32 · 64 · 96 · 128 MiB for `networking_cache_size` 16 · 32 · 64 · 100 MiB and
unset, the rest went to overflow (1,390 … 494 refusals of a slab, overflow bytes = 131,070 × refusals exactly), and
**the stall's direct rise was 182.8–183.3 MiB (191.6–192.2 MB) at every knob value**: the knob decides the
pooled/overflow split, not the total. Held frames at the peak: 1,517 of 1,536 (the kernel held the rest: server
`Send-Q` 2,488,848 B + client `Recv-Q` 65,496 B per connection). After the client closed, overflow returned to ≈ 0
(−6 B per overflowed frame, the `putUnusedPortion` drift) and the retained rise followed T′. NMT `Other` rose from
≈ 0.26 GB to 0.90–1.09 GB at the peak (Netty arena chunks for the response bodies, a separate counter). Stage 4 never
approached the direct limit (demand 192 MiB against 8 GiB).

**Relation to filed cases.** C2 (`convergence/coordinator_read_size_fail_threshold-concurrent-reads/`,
`verified-OOM · deployment`) is the **protocol v4** form: encoded responses wait in Netty's pooled allocator
(`CBUtil.allocator`) and fill Netty's own direct counter; its §4 lists the v5 arm as untested. On v5 the response
body is still encoded on the request thread into `CBUtil.allocator` (`CQLMessageHandler.toFlushItem` `:480-498` →
`response.encode`), but it is copied into frames on the event loop and released right after framing
(`Flusher.flushWrittenChannels` → `CQLMessageHandler.release` → `responseEnvelope.release()`). What is held is the
frames, in a **different allocator (the `networking` `BufferPool`) and a different counter** (the JDK's
`java.nio.Bits` reservation, which `ByteBuffer.allocateDirect` charges; Netty's no-cleaner counter does not see it).
So B13 tests a different holder and a different limit check than C2, with the same trigger.

**JIRA prior art** (read only; nothing posted). Sources: `stage5-oom-clue-find/jira-oom-survey.csv` (604 rows),
`jira-prior-art-verified-cases.md` (C2 section), and Apache JIRA REST search run 2026-11-18 08:10–08:20 EST:

| Query | Hits | Relevant |
|---|---|---|
| survey CSV: `writab`, `slow client`, `backpressure`, `outbound`, `BufferPool`, `networking`, `v5`, `frame`, `Flusher` | 30 rows read | CASSANDRA-11082, -14855, -19535 (below) |
| `text ~ "isWritable"` | 10 | **CASSANDRA-11082** (Open since 2016-01-28): "netty's level hadn't prevent OOM when receiver handle slow" — watermarks set, `isWritable()` never checked, outbound buffer grows with slow clients; maintainers confirmed, lowered priority for lack of evidence. CASSANDRA-15013 (Fixed 3.0.19/3.11.5/4.0): bounded request bytes in flight, not response bytes. |
| `text ~ "Flusher" AND text ~ "OutOfMemoryError"` | 4 | CASSANDRA-11818 (Resolved Done, 2016): a direct OOM not caught by `JVMStabilityInspector`; CASSANDRA-10689 (Open, 2.1 reader path). Neither is this path. |
| `text ~ "\"networking buffer pool\""` | 1 | CASSANDRA-21117 (Review In Progress): `nodetool info` network-cache size wrong (the `OverflowSize` drift of 21815/21884); accounting display, not this holder. |
| `text ~ "\"Direct buffer memory\"" AND created >= 2020-01-01` | 14 | **CASSANDRA-19535** (Cannot Reproduce, 2024): "Running with default configuration OOMs under light load": `OutOfMemoryError: Cannot reserve 65536 bytes of direct buffer memory (allocated: 8589921806, limit: 8589934592)` at `BufferPool.allocate(BufferPool.java:238)` ← `LocalPool.get:923` ← `BufferPoolAllocator.newDirectBuffer` on `epollEventLoopGroup-5-16`, forced heap OOM; no comments. The same overflow site on a native event loop at a default 8 GiB limit — **possibly a field instance of this mechanism, unexplained by the reporter**. CASSANDRA-21529 (Open, 2026-07, 5.0.6): direct OOM in compaction with a 4 GiB networking pool configured; different thread. |
| `text ~ "channelWritabilityChanged"`, `text ~ "ChannelOutboundBuffer"`, `text ~ "\"BufferPool.allocate\""`, `text ~ "\"protocol v5\"" AND text ~ "backpressure"` | 4, 3, 1, 5 | nothing on the native v5 response path (internode backlog, repair, test failures, rate limiting 16663) |

**Verdict: known-open** (CASSANDRA-11082 names the missing writability check for slow readers in general; no
ticket describes the v5 frame/overflow form or measures it). CASSANDRA-19535 is a possible unreproduced report of it.
Not a known-fixed bug, so not a positive control.

## 2. Design solution (stage 1; frozen)

### 2.1 Mechanism

Direction: **bypass — accounting omission** (U > C, K ≤ C): the `networking` pool's contract C = T′ (its pooled
slabs, documented as the "maximum memory to use for … client-server networking buffers"); the frames past it are
real direct memory that the pool counts in `OverflowSize` but never checks. Technique note:
[`bypass-playbook.md`](../../../bypass-playbook.md) (protected vs suspect path inside one control's domain), with the
multiplicity shaping of C2. Interpretation: missing aggregate control on outbound response memory (the 11082 shape),
plus a pool whose limit is a retention cap presented as a maximum.

Path (5.0.9 source):

1. A v5 connection (`PipelineConfigurator.java:282-290`: `GlobalBufferPoolAllocator`, CRC frame codec) receives
   `QUERY` frames; `CQLMessageHandler` acquires request-byte permits (≈ 80 B per SELECT) and dispatches each to
   `Dispatcher.requestExecutor` (128 `Native-Transport-Requests` threads, `Dispatcher.java:58`, `:123-125`).
2. The worker runs the read and encodes the `Rows` response into Netty's `CBUtil.allocator`
   (`CQLMessageHandler.toFlushItem` `:480-498`), then enqueues a `FlushItem.Framed` on the channel's event-loop
   `Flusher` (`Dispatcher.processRequest` `:459-465`, `flush`).
3. On the event loop, `Flusher.processFramedResponse` (`:149-161`) sends a response ≥ 131,060 B to
   `flushLargeMessage` (`:163-199`): one `FrameEncoder.Payload` per 131,054 B of body, each from the CRC encoder's
   allocator (`FrameEncoderCrc.java:35-41`, `FrameEncoder.java:64`) = `BufferPools.forNetworking().getAtLeast(131,070)`.
   Within T′ that is a 128 KiB normal chunk of an 8 MiB slab; past T′ `allocateMoreChunks():443-450` returns null
   and `LocalPool.get():923` → `BufferPool.allocate():233-239` makes an exact 131,070-B `allocateDirect` buffer
   (overflow). Every frame is `channel.writeAndFlush`'ed at once (`:201-206`). No code in
   `org.apache.cassandra.transport` calls `isWritable()` (grep, 2026-11-18); the 8/32 KiB water mark
   (`PipelineConfigurator.java:139`) only flips the flag.
4. `flushWrittenChannels` (`:225-260`) then releases the flush item: request permits returned, request and
   response-body buffers released (`CQLMessageHandler.release` `:500-510`). **From here nothing counts the frames
   except the pool's own gauges.** They live in the channel's `ChannelOutboundBuffer` until the kernel accepts them;
   a frame buffer is freed when Netty releases the wrapping `BufferPoolAllocator$Wrapped` (`BufferPoolAllocator.java:147-152`,
   overflow freed at once by `LocalPool.put():816-820`).
5. A client that writes requests and does not read: the server's socket send queue fills (≈ 2.5–4 MiB,
   `tcp_wmem` max 4 MiB on ms0617), every later frame stays in the outbound buffer. Held bytes = outstanding
   responses × response size, bounded only by how many requests the client sends (stream ids: 32,768 per connection;
   connections unlimited at defaults, `Config.java:289-290`).
6. When the JDK reservation reaches `MaxDirectMemorySize`, `Bits.reserveMemory` (after its `System.gc()` and
   back-off retries) throws `java.lang.OutOfMemoryError: Direct buffer memory` from `BufferPool.allocate` on the event
   loop. Where it lands decides what the process does: from the `Flusher` task it propagates to Netty's
   `SingleThreadEventExecutor.safeExecute` (logged as `WARN … A task raised an exception`, process alive, that flush
   item never released); from a v5 read-buffer allocation (`BufferPoolAllocator.newDirectBuffer`, any connection
   that is still reading, e.g. the probe) it reaches `ExceptionHandlers.PostV5ExceptionHandler.exceptionCaught`
   (`ExceptionHandlers.java:72-125`) → `JVMStabilityInspector.inspectThrowable` → forced heap OOM → hprof (if enabled)
   and `-XX:OnOutOfMemoryError="kill -9 %p"` — the CASSANDRA-19535 stack.

### 2.2 Protection map (fixed before readings)

| Domain | Allocation / owner / release | Local contract (C) and counter (K) | Scope and multiplicity | Budget |
|---|---|---|---|---|
| **F (claimed): v5 response frames** | `FrameEncoderCrc` payloads from the `networking` `BufferPool`: pooled 128 KiB chunks of 8 MiB slabs (`allocateDirectAligned`) or exact-size overflow `allocateDirect`; owned by the channel's `ChannelOutboundBuffer`; released when written to the socket | **C = T′ = ⌊`networking_cache_size`/8 MiB⌋ × 8 MiB = 128 MiB** at heap 2 GiB (min(128, 2048/16)); hard cap on slabs only. **K = `memoryAllocated`** (= pool `Size` − `OverflowSize`), checked at `:443`. Overflow (`OverflowSize`) is counted, compared with nothing | one pool per JVM; demand = Σ over v5 connections of outstanding responses × frames per response; outstanding bounded only by the client | JDK direct reservation (`java.nio:type=BufferPool,name=direct` `MemoryUsed`) vs `MaxDirectMemorySize` |
| R: request bytes in flight | `native_transport_max_request_data_in_flight(_per_ip)` (heap/10 = 204.8 MiB, heap/40 = 51.2 MiB at 2 GiB) | charges request body bytes (≈ 80 B per SELECT), released at framing; K = `Client.RequestsSize` | per node / per IP | heap (accounting only) — **does not cover F** |
| N: encoded response bodies (Netty) | `CBUtil.allocator` (`PooledByteBufAllocator`, preferDirect, 16 MiB chunks, `-Dio.netty.allocator.maxOrder=11`), no-cleaner; released after framing | none (transient: ≤ responses being encoded + queued in the `Flusher`) | ≤ 128 workers + flusher queue | **Netty's own counter** vs `MaxDirectMemorySize` (separate from F's counter); competing domain, not claimed |
| H: heap | read path (`ReadResponse` buffers, `ResultSet`), ≤ 128 concurrent reads of 3.5 MiB | GC; no byte control at defaults (read thresholds disabled) | ≤ 128 | `-Xmx` (competing) |
| Kernel | server `Send-Q` + client `Recv-Q` per connection (≈ 2.5–4 MiB) | `tcp_wmem` / `SO_RCVBUF` | per connection | kernel memory; not in any JVM budget (subtracted from held demand) |
| Aggregate | nothing sums F, R, N | — | — | — |

**Classification by measurement (decided now):** in domain F, U = JDK direct `MemoryUsed` rise (independent of the
pool's counters) and `UsedSize`; K = `Size − OverflowSize`. Bypass if U_F > C and K ≤ C (expected: U_F ≈ 1.9 GiB,
K = 128 MiB). If the endpoint is reached with U_F ≤ C (impossible by construction) it would be convergence; a Netty
counter OOM (domain N) or heap OOM first is a **competing** endpoint, not the claim.

### 2.3 Configuration and budget audit

| Item | Value | Class |
|---|---|---|
| Node | `ms0617` (node4.jason92-326377, Utah m400), **aarch64**, 8 cores, 64,249 MiB RAM (`free -m`), 8 GiB swap (kept off the measured process: scope `MemorySwapMax=0`), `/mydata` 39 GiB with 36 GiB free, `/dev/shm` 32 GiB; Ubuntu 22.04, kernel 5.15, cgroup v2; OpenJDK 11.0.33 (aarch64), G1 (shipped `jvm11-server.options`); idle at 08:01 EST 2026-11-18 (no Java process). `/mydata/s4/b9-w1` belongs to B9: **do not touch or delete** | environment |
| Build | `/mydata/s4/cassandra-base` (5.0.9 unpatched, read-only; never run `ant` in it); intervention build `/mydata/b13/cassandra-int` (§2.8) | environment / intervention |
| Topology | single node at `127.0.0.131` (native 9042, storage 7000, JMX 7313), clients and samplers colocated on loopback | environment |
| yaml diffs | only cluster name `b13`, `listen_address`/`rpc_address`/seeds `127.0.0.131`, data/commitlog/hints/saved_caches/cdc directories under `/mydata/b13/node` (B9 `ctl.sh gen` edits), JMX port | environment |
| Capacity settings | **all shipped defaults** (none set in the yaml): `networking_cache_size` unset → **128 MiB** at heap 2 GiB and above (min(128 MiB, maxMemory/16)); `file_cache_enabled: false` (`Config.java:499`); `native_transport_max_threads` 128; `native_transport_max_request_data_in_flight(_per_ip)` null → heap/10, heap/40; `native_transport_receive_queue_capacity` 1 MiB; `native_transport_max_concurrent_connections(_per_ip)` −1; `native_transport_timeout` 12 s; `native_transport_flush_in_batches_legacy: false` (immediate flusher); `native_transport_rate_limiting_enabled: false`; read thresholds off; `native_transport_allow_older_protocols: true` | default (V6) |
| Resolved defaults to record from `system.log` | "Global buffer pool limit is … for chunk-cache and 128.000MiB for networking"; the "Node configuration" line; JVM arguments line (`-Xmx`, `-XX:MaxDirectMemorySize`) | record |
| Budgets (V7) | **heap 2048 MiB, direct 2048 MiB** (`MAX_HEAP_SIZE=2048M`, `MAX_DIRECT_MEMORY_SIZE=2048M`, the documented `cassandra-env.sh` overrides) for every V arm; upward search: direct **4096 MiB** and the node's auto value **7936 MiB** (heap 2048 MiB); optionally fully auto (heap 15872 MiB, direct 7936 MiB) | budget |
| What the node resolves itself | `cassandra-env.sh:58-67`: half RAM 32,124 MiB > 15,872 → heap **15,872 MiB**, direct **7,936 MiB** (also with a hand-set heap, since `MAX_DIRECT_MEMORY_SIZE` comes from RAM) | record |
| Safety scope | `systemd-run --user --scope -p MemoryMax=48G -p MemorySwapMax=0` (as B9): a guard for the shared node, **not the budget** (reachable JVM total ≤ 2 + 7.75 + 7.75 + ≈ 1 GiB ≈ 18.5 GiB in the largest arm) | environment |
| JVM extras | `-XX:NativeMemoryTracking=summary`, `-Dcassandra.printHeapHistogramOnOutOfMemoryError=true`, `-XX:ErrorFile=…`; `-XX:-HeapDumpOnOutOfMemoryError` except in `T_r1` | instrumentation |
| Pinning | Cassandra `taskset -c 0-5`; clients, samplers, `jcmd` on cores 6–7 | environment |

**V7 argument.** Heap 2 GiB and direct 2 GiB are ≥ 512 MiB and the standing rule's ideal value: V7 is met without
per-case review. 2 GiB direct is below what `cassandra-env.sh` resolves on this 62 GiB node (7,936 MiB) and equals
what it resolves on an 8 GiB-RAM node (¼ RAM); the upward arms test 4,096 MiB and the node's own 7,936 MiB so the
largest failing budget is reported.

### 2.4 Ceiling arithmetic

In the JDK direct domain at heap 2 GiB, the contracted capacities are: the `networking` pool 128 MiB; the
`chunk-cache` pool min(512 MiB, heap/4) = 512 MiB only if used (`file_cache_enabled: false`; stage 4 read its `Size`,
record it); no internode reserves in use (one node, no peers); hint slabs none (no hints); commit log uncompressed
(mmap, not in this counter). Baseline JDK direct at idle ≈ 48.6 MB on x86 at stage 4 (measure here). **Σ contracts +
baseline ≤ 128 + 512 + ≈ 50 ≈ 690 MiB < 2,048 MiB**: with every pool full the direct limit cannot be reached, so the
endpoint, if reached, needs the uncontracted overflow (bypass). Demand needed: frames to fill ≈ 2,048 − 50 ≈ 2,000 MiB
→ at 3.50 MiB of frames per response (28 × 131,070 B + one small frame) ≈ **570 held responses**, plus ≈ 1 response
per connection in the kernel (16 connections) → **≈ 590 requests sent**. The test sends 1,280 (2.2 ×), the control
320 (≈ 1,120 MiB, 55 % of the budget).

### 2.5 Workload and environment

**Work directory** `/mydata/b13` (fresh; `h/` harness copy, `cls/`, `node/`, `tmpl/`, `runs/<arm>/`). Check before
use: `ps -eo cmd | grep '[C]assandraDaemon'` empty, `/mydata` free ≥ 10 GiB, `MemAvailable` ≥ 30 GiB.
`sudo loginctl enable-linger jason92` before the first arm (B9 practice), `disable-linger` at the end.

**Data template (built once, not a reading):** start the node (heap 2 GiB, direct auto), create keyspace `b13`
(SimpleStrategy RF 1) and `b13.t (pk int, ck int, v blob, PRIMARY KEY (pk, ck))`; insert **64 partitions × 56 rows ×
65,536 random bytes** (3,670,016 value bytes per partition, as C2) over **protocol v4** (lessons: large v5 requests
leak frame buffers; each INSERT here is 64 KiB < 131,071 anyway) with the bundled Python driver or a prepared
statement in a small Java/Python loader; `nodetool flush b13`, `nodetool drain`, stop; copy `node/data` to
`tmpl/data` (≈ 240 MB). Every lifetime: `ctl.sh gen` (fresh `node/`), `cp -a tmpl/data/. node/data/`, start. Same
node identity (system tables copied), no commit-log replay.

**Response** (all arms): `SELECT v FROM b13.t WHERE pk = <i mod 64>` at CL ONE, no paging options → one `Rows`
response of ≈ 3,670,300 B → 28 full frames + 1 small. Each connection walks the partitions round-robin from its own
offset.

**Clients** (harness `stall5.py`, from stage-4 `stall-client.py`, same bundled driver codec via `drv.py` with
`CASSANDRA_HOME=/mydata/s4/cassandra-base`): one process, `C` raw sockets to `127.0.0.131:9042`, `SO_RCVBUF` 65,536
before connect, STARTUP/READY at protocol v5, then **paced waves**: every `period` s it writes `w` `QUERY` messages to
every socket (each in its own self-contained CRC frame), stream ids 1… per socket, until `R` requests per socket have
been sent; `mode stall` never reads after READY; `mode drain` reads and discards on a thread per socket. Prints
`LOAD_START <epoch_ms>`, one line per wave (`epoch_ms, sent_total`), `SENT_ALL <epoch_ms>`; on the stop file closes
with `SO_LINGER` 0. Pinned to cores 6–7. Pacing is needed because a request queued more than `native_transport_timeout`
(12 s) gets a small `Overloaded` error instead of its 3.5 MiB response (`Dispatcher.java:357-366`); the rate is below
the server's production rate, so the held demand grows at λ × 3.5 MiB per second.

- **Pacing (fixed):** `C = 16`, `w = 1`, `period = 1 s` → λ = 16 requests/s (≈ 56 MiB/s). **Rule:** if the
  calibration arm shows `TimedOutBeforeProcessing` > 0 or NTR pending > 32 at λ = 16, use `period = 2 s`
  (λ = 8/s) in every later arm (record the change with its time in §3 before step 3).
- **Probe** (`probe5.py`, every arm, identical): one v5 connection that reads normally, sends
  `SELECT release_version FROM system.local` once per second with a 2 s timeout, logs `epoch_ms, ok|timeout|error,
  latency_ms`. It measures availability and, as a reading connection, exercises the v5 read-buffer allocation.

**Arms** (one clean lifetime each; heap 2048 MiB; `D` = `MaxDirectMemorySize`):

| Step | Arm | Build | D (MiB) | Clients | R per conn (total) | Window from `LOAD_START` | Purpose |
|---|---|---|---|---|---|---|---|
| 0 | `shake` | base | auto (7936) | stall, 2 conns | 4 (8) | 30 s | harness shakedown — **not a reading** |
| 1 | `cal` | base | auto (7936) | stall, 16 conns, λ = 16/s for 40 s, then one burst of 16 per conn | 56 (896, ≈ 3.1 GiB) | 70 s | reachability at modest load (protocol step 2); U per held response; production rate μ (from the burst); pacing rule |
| 2 | `T_r1..r3` | base | **2048** | stall, 16 conns, λ | **80 (1,280)** | until endpoint + 20 s, else 110 s | test ×3 (`T_r1` with `DUMP=1`) |
| 2 | `M_r1..r3` | base | **2048** | stall, 16 conns, λ | **20 (320)** | 110 s | matched control ×3 (V2) |
| 2 | `I_r1..r3` | **int** | **2048** | stall, 16 conns, λ | **80 (1,280)** | 110 s | intervention ×3 (V4) |
| 3 | `B8_r1` | base | auto (7936) | stall, 16 conns, λ | 312 (4,992 ≈ 17 GiB) | until endpoint + 20 s, else 340 s | largest failing budget (node auto) |
| 3 | `B4_r1` | base | 4096 | stall, 16 conns, λ | 160 (2,560) | until endpoint + 20 s, else 190 s | budget ladder |
| 3 | `BA_r1` (optional) | base | auto (heap 15872, direct 7936) | as B8 | 312 | as B8 | fully auto-resolved node |
| — | `D_r1` (optional, supporting) | base | 2048 | **drain**, 16 conns, λ | 80 | 110 s | same requests, client reads: frames freed as written |

Run step 2 interleaved: T_r1, M_r1, I_r1, T_r2, M_r2, I_r2, T_r3, M_r3, I_r3 (if the intervention build is not ready
when I_r1 is due, run the T and M arms first and the I arms after). Step 3 in the order B8, B4, then BA/D only if
time allows (§2.7).

**Per-lifetime procedure** (`arm.sh <arm> <build> <D|auto> <mode> <C> <R> <window_s> [dump]`, from B9's `arm.sh`):
preflight → `ctl.sh gen` (with `BUILD=` the chosen build) → restore template → start (`XMX=2048M`, `DIRECT=`) → wait
for `Starting listening for CQL clients` (≤ 180 s; one retry, then stop the queue) → start sampler, NMT and cgroup
loops, `ss` loop, probe → **10 s idle baseline** → `stall5.py` → watch `system.log` (and `logs/launch.log`) every 1 s
for `OutOfMemoryError`; on the first match: immediately `jcmd <pid> GC.class_histogram` (if alive) →
`hist-at-oom.txt`, `jcmd <pid> VM.native_memory summary` → `nmt-at-oom.txt`, `ss -tmnp '( sport = :9042 )'` →
`ss-at-oom.txt`; keep sampling 20 s; then (or at the window end) touch the stop file, 5 s, collect and stop. Collect:
`system.log`, `debug.log` excerpt, `gc.log*`, `first-oom.txt` (first `OutOfMemoryError`/`OutOfDirectMemoryError`
line with 5 lines before and 60 after, the "JVM Arguments" line excluded), `V-flags.txt` (`jcmd VM.flags` taken
after start: `MaxHeapSize`, `MaxDirectMemorySize`), `V-yaml.diff`, `V-cmdline.txt`, the buffer-pool startup line,
client and probe logs; classify (§2.6); append one line to `runs/summary.txt`; wipe `node/`.

### 2.6 Instruments and outcome classes

Sampler (`B13Sample.java`, from B9's `B9Sample.java`, JMX `127.0.0.131:7313`, every **500 ms**, `epoch_ms` first):

- **U_F (independent of the pool's counters):** `java.nio:type=BufferPool,name=direct` `MemoryUsed`, `Count`,
  `TotalCapacity` (the JDK reservation that `MaxDirectMemorySize` limits).
- **Pool:** `org.apache.cassandra.metrics:type=BufferPool,scope=networking,name=` `Size`, `UsedSize`,
  `OverflowSize`, `Capacity`, `Misses`, `Hits`; same for `scope=chunk-cache`. **K = Size − OverflowSize.**
- **R:** `type=Client,name=RequestsSize`; `type=Client,name=` `ConnectedNativeClients`, `PausedConnections`,
  `RequestDispatched` (count), `TimedOutBeforeProcessing` (count).
- **Load reached:** `type=ClientMessageSize,name=BytesSent` (count of encoded response bytes) → responses produced =
  ΔBytesSent / 3,670,300; client `sent_total`; NTR active/pending (`type=ThreadPools,path=transport,scope=Native-Transport-Requests`).
- **Competing:** heap used, G1 old after GC; `memory.events` `oom_kill` (cgroup loop, 1 s, with `RssAnon`).
- **Netty domain N:** NMT `Other` committed every 2 s (`nmt.sh`, as B9) minus JDK `MemoryUsed` → ΔU_N over the idle
  median (Netty no-cleaner chunks are in NMT `Other`, as are JDK direct buffers).
- **Kernel share:** `ss -tmn` every 2 s on port 9042: Σ server `Send-Q` over the stalled connections.
- **Holder at failure:** `hist-at-oom.txt` (`java.nio.DirectByteBuffer`, `io.netty.channel.ChannelOutboundBuffer$Entry`,
  `org.apache.cassandra.net.BufferPoolAllocator$Wrapped`, `org.apache.cassandra.net.FrameEncoder$Payload` counts),
  `nmt-at-oom.txt`, the heap histogram Cassandra logs if `JVMStabilityInspector` runs, and `T_r1`'s hprof if one is
  written.

Derived per arm (`b13peaks.py`): idle medians; **U_F,peak = max(MemoryUsed) − idle median**; K_peak; `OverflowSize`
peak; responses produced and timed out; held responses ≈ (U_F rise − pool idle) / 3.50 MiB; Σ Send-Q peak; ΔU_N peak;
heap peak; endpoint time after `LOAD_START`; probe ok/timeout/error counts before and after the endpoint; outcome class.

| Class | Rule (first OOM line, "JVM Arguments" excluded) | Meaning |
|---|---|---|
| `NIO-NET` | `java.lang.OutOfMemoryError: Direct buffer memory` whose stack contains `org.apache.cassandra.utils.memory.BufferPool.allocate` (any thread: `Flusher`/`FrameEncoder` on the event loop, or `BufferPoolAllocator` read buffers) | **the claimed endpoint** (JVM direct-buffer OOM) |
| `NIO-OTHER` | `Direct buffer memory` elsewhere | counts as the claimed endpoint only if the last sample has pool `UsedSize` ≥ 0.8 × `MaxDirectMemorySize` (frames hold ≥ 80 % of the JDK reservation); reported separately |
| `NETTY` | `io.netty.util.internal.OutOfDirectMemoryError` first (domain N) | competing |
| `HEAP` | `Java heap space` / `GC overhead limit exceeded` first (a heap OOM logged after "Force heap space OutOfMemoryError in the presence of" does not count) | competing |
| `KILL` | `oom_kill` > 0 in the scope's `memory.events` | competing |
| `NONE` | no OOM line in the window | no endpoint |

Also recorded per arm, not part of the class: whether the JVM exited (time, and whether via `JVMStabilityInspector`
"Force heap space OutOfMemoryError"), and the probe's availability after the endpoint.

### 2.7 Predicted response, stopping budget and time plan

**Predictions (before readings).**

| Arm | Endpoint | Key readings |
|---|---|---|
| `cal` | `NONE` (D = 7936) | U_F rises linearly at ≈ 3.5 MiB per held response (slope 3.4–3.7 MiB); K stops at 128 MiB (one INFO "Maximum memory usage reached (128.000MiB) for networking buffer pool"); `OverflowSize` ≈ U_F − K − idle; Σ Send-Q ≈ 16 × 2.5–4 MiB; `RequestsSize` < 1 MiB throughout; no `TimedOutBeforeProcessing` at λ = 16/s; μ (burst) ≥ 25 responses/s |
| `T` (D 2048) | **`NIO-NET` 3/3**, ≈ 30–45 s after `LOAD_START` (≈ 570–600 responses produced) | at the last sample before the OOM: `MemoryUsed` ≥ 0.9 × 2,048 MiB; **K = 128 MiB ≤ C, U_F ≥ 1.8 GiB > C (≥ 14 × C)**; `OverflowSize` ≥ 1.6 GiB; `RequestsSize` < 1 MiB; ΔU_N < 512 MiB; heap below 2 GiB; histogram: `DirectByteBuffer` ≥ 12,000, `ChannelOutboundBuffer$Entry` ≥ 12,000. After the OOM: either the process exits (forced heap OOM via a read-path allocation, the 19535 stack) or stays up with repeated `A task raised an exception … Direct buffer memory` warnings and the probe failing; both are recorded, neither changes the class |
| `M` (D 2048) | `NONE` 3/3 | U_F peak ≈ 1,120 MiB − Σ Send-Q ≈ 1.05–1.15 GiB (≤ 0.7 × 2,048 = 1,434 MiB); stays flat after `SENT_ALL` (frames held, not freed); probe ok |
| `I` (D 2048, patched) | `NONE` 3/3 | U_F peak ≤ 600 MiB (≤ 16 × a few responses + pool); ≥ 1,100 requests still deferred at the window end (dispatched, not produced: ΔBytesSent / 3.67 MB ≤ 200); probe ok ≥ 90 % (workers are not blocked) |
| `B8` (D 7936) | `NIO-NET` ≈ 140–160 s after `LOAD_START` (≈ 2,250 responses) | U_F ≥ 0.9 × 7,936 MiB; K = 128 MiB |
| `B4` (D 4096) | `NIO-NET` ≈ 70–80 s | as above at 4,096 MiB |
| `D_r1` (optional) | `NONE` | U_F peak ≤ 300 MiB (frames written as produced) |

If T reaches its 1,280 requests without an endpoint and U_F stays below D, the claim is refuted at that budget (record
U_F and where the frames went); one repeat of `T` with R = 160 is allowed once (recorded as an amendment) before
concluding.

**Stopping budget.** At most 16 lifetimes (shake, cal, 9 V arms, B8, B4, BA, D, 1 spare). Window per arm as in the
table; a node not listening 180 s after start is a failed start (one retry, then stop the queue). No escalation after
an OOM beyond the listed arms. **No lifetime starts after 10:25 EST on 2026-11-18; every process this case started is
stopped by 10:40; §3–§4 and the write-backs are done by 10:58** (hard limit 11:00 America/New_York).

**Time plan** (stage 2 assumed to start ≈ 08:45 EST; ≈ 3.5–4.5 min per lifetime on the m400: gen + restore 15 s,
start ≈ 60–90 s, 10 s idle, load window 60–110 s (B8 ≤ 340 s), collect + stop ≈ 30 s):

| Window (EST) | Work |
|---|---|
| 08:45–08:55 | read the case, check the freeze hash, check ms0617 (idle, disk, RAM; B9's folder untouched), create `/mydata/b13`; start the intervention build in the background (§2.8) |
| 08:55–09:20 | harness: copy B9's `ctl.sh`, `arm.sh`, `nmt.sh`, `nmt.py`, `queue.sh`, `B9Sample.java` and stage-4 `stall-client.py`, `drv.py`; adapt (paths, IP/JMX, `BUILD=` switch, pool and `BytesSent` metrics, OOM watcher, `stall5.py`, `probe5.py`, `b13peaks.py`); `javac` on the node |
| 09:20–09:30 | data template; `shake` (fix harness only) |
| 09:30–09:35 | `cal`; apply the pacing rule; write the decision in §3 before step 2 |
| 09:35–10:15 | step 2: 9 V arms interleaved |
| 10:15–10:25 | step 3: `B8_r1`, then `B4_r1` if it can start by 10:25 (BA, D only if time) |
| 10:25–10:40 | stop everything; self-check from the raw files (`b13peaks.py`, first-OOM excerpts, histograms) |
| 10:40–10:58 | fill §3–§4, write-backs (candidate row, `_INDEX.md`, retry list if needed); report what is left on the node |

Total stage-2 wall time ≈ 2 h 15 min. Resources: Cassandra ≤ heap 2 GiB + JDK direct ≤ D + Netty ≤ ≈ 1 GiB + ≈ 0.5
GiB other (≤ 11.5 GiB in B8; BA ≤ 25 GiB) of 62.7 GiB; clients < 1 GiB; cores 0–5 / 6–7. Disk: template 0.25 GB, node
copy 0.25 GB per lifetime (wiped), intervention build ≈ 0.5 GB, one hprof ≤ 2.5 GB (`T_r1`, only if the forced heap
OOM runs), logs < 1 GB: under 5 GB of the 36 GiB free.

### 2.8 Controls and intervention

- **Matched control (V2), low multiplicity:** same build, heap, D = 2048 MiB, data, response size, connections,
  pacing, stall and instruments; only the number of requests per connection is 20 instead of 80 (320 held responses ≈
  1,120 MiB, 55 % of D; ≥ 30 % margin by construction). It shows the same overflow frames held below the direct limit
  do not reach the endpoint, and that the held memory follows the outstanding count, not time.
- **Causal intervention (V4), stop producing responses for an unwritable channel (the CASSANDRA-11082 remedy), same
  load:** a diagnostic build in a separate tree; the T workload unchanged (16 stalled connections, 1,280 requests,
  D = 2048 MiB). The exact diff (save it as `harness/intervention.diff`), in `RequestProcessor.run()`
  (`src/java/org/apache/cassandra/transport/Dispatcher.java:303-308`, `run()` at `:304`):

  ```java
          @Override
          public void run()
          {
              // B13 diagnostic intervention (not upstream): defer a request whose channel is above its
              // outbound high water mark, so no response is built for a client that is not reading.
              if (channel.isActive() && !channel.isWritable())
              {
                  org.apache.cassandra.concurrent.ScheduledExecutors.scheduledFastTasks
                      .schedule(() -> requestExecutor.submit(this), 100, TimeUnit.MILLISECONDS);
                  return;
              }
              startTimeNanos = MonotonicClock.Global.preciseTime.now();
  ```

  (`requestExecutor` is the static `Dispatcher` field `:58`; `TimeUnit` is imported `:23`.) Build:
  `cp -a /mydata/s4/cassandra-base /mydata/b13/cassandra-int`, apply the diff, delete
  `build/classes/main/org/apache/cassandra/transport/Dispatcher*.class` (Ant timestamp lesson), then
  `( setsid nohup ant jar < /dev/null > /mydata/b13/build-int.log 2>&1 & )` (full build was 4 min 57 s on this node,
  `/mydata/s4/build-b9.log`); done when the log ends with `BUILD SUCCESSFUL`; record the jar's sha256 and `git -C …
  diff --stat`. The base tree is never built again. Prediction above (`I` row): each channel produces at most the
  responses already in processing when it turns unwritable, so U_F stays far below D while the requests stay queued
  (deferred, not dropped). Useful work: the stalled clients receive nothing in any arm; the probe's success rate is
  the useful-work measure and must not fall below the M arms'. **If the build has not succeeded by 09:50**, the I
  arms are not run and V4 is recorded as not done, with the missing attribution named (the status then carries
  `(no intervention)`); no other intervention is substituted.
- **Supporting (optional, not V2):** `D_r1`, the T requests with a reading client, shows the frames are freed as they
  are written when the client reads.

**Repetitions:** T, M, I ×3 each from clean lifetimes (V1, V2, V4). Budget arms ×1 each (they report the largest
failing budget with n/N, not V1–V4).

`sha256 of §1–§2 at freeze: a15c6bf7a3bfe7c5f6704415820ddb232241c6d021f569a62c0cbb7237efdfc1` · amendments after the freeze: none. Verify with
`awk '/^## 1\. Candidate/{f=1} /^.sha256 of §1/{f=0} f' <this file> | sha256sum` (the lines from the §1 heading to the
line before this one).

## 3. Runs (stage 2)

*Stage 2 by a fresh OOM-agent session (Claude Opus 5.5, workflow subagent), 2026-11-18 08:11 EST onward. Freeze hash
checked at 08:11 EST: `a15c6bf7…efdfc1`, matches §2's line (design unchanged).*

### 3.0 Amendments and decisions (recorded before the readings they affect)

| # | Time (EST) | Amendment / decision | Reason |
|---|---|---|---|
| A1 | 08:12 | Run root `/mydata/s4/b13-w3` instead of `/mydata/b13`; intervention tree `/mydata/s4/b13-w3/cassandra-int` | path only (the session's instruction: a fresh directory `/mydata/s4/b13-w3`); nothing else changes |
| A2 | 08:13 | Intervention build: `ant jar` on the copy was incremental (35 s, `[javac] Compiling 1 source file`), not a 5-min full build | the copied tree's other classes were already current; the patched `Dispatcher$RequestProcessor` bytecode was checked with `javap` (calls `Channel.isWritable` and `ScheduledExecutors.scheduledFastTasks`); jar sha256 `866ea979…1f78` |
| A3 | 08:20 | `linger` was already `yes` for `jason92` (left by B9); not toggled, left as found | B9 practice already in effect |
| A4 | 08:21 (after `shake`, before `cal`) | **The node's auto direct limit is 15,872 MiB, not 7,936.** ms0617 runs G1, so `cassandra-env.sh:53-62` uses `heap_limit = 31744`; half RAM 32,124 > 31,744 → auto heap 31,744 MiB, auto `MaxDirectMemorySize` = 31,744 / 2 = **15,872 MiB** (`V-flags.txt` of `shake`/`cal`: `-XX:MaxDirectMemorySize=16642998272`). §2.3's 15,872 / 7,936 are the CMS values. Consequences: `cal` ran at D = auto = 15,872 MiB (still `NONE` by design: 3.1 GiB demand); **`B8_r1` runs at an explicit D = 7,936 MiB** (the value its R = 312 and window were sized for); **`BA_r1` (optional) becomes heap 2,048 MiB, D = auto = 15,872 MiB, R = 312, window 340 s** (the node's own direct value; the fully auto heap of 31,744 MiB plus 15,872 MiB direct would exceed the 48 GiB safety scope, and `AlwaysPreTouch` on 31 GiB is outside the time plan) | factual error in §2.3 found from the resolved flags; arms keep their R and windows |
| A5 | 08:20 | Harness fix after `shake` (not a reading): the OOM watcher matched the JVM's `CompileCommand: exclude …forceHeapSpaceOomMaybe(Ljava/lang/OutOfMemoryError;)V` line in `launch.log`; the watcher and `first-oom.txt` now match `OutOfMemoryError:` / `OutOfDirectMemoryError` and exclude `CompileCommand` and `JVM Arguments` lines; `system.log` times are UTC (`2026-11-18T13:17:13,786`), parsed as such | shakedown, harness only |
| P1 | 08:24 (after `cal`, before step 2) | **Pacing rule: unchanged, λ = 16/s (`period` = 1 s).** In `cal`'s paced phase (0–40 s after `LOAD_START`) NTR pending max = 0 and `TimedOutBeforeProcessing` = 0; the pending peak of 172 was the 256-request burst at 40 s | §2.5 rule (`TimedOutBeforeProcessing` > 0 or NTR pending > 32 at λ = 16) not triggered |
| A6 | 08:31 (after `I_r1`, before `I_r2`) | **`I_r1` is not an intervention run.** `arm.sh` exported `CASSANDRA_HOME=/mydata/s4/cassandra-base` (for `drv.py`), and `bin/cassandra` of the intervention tree takes the classpath from `CASSANDRA_HOME`, so `I_r1` ran the **base** jars (`I_r1/V-cmdline.txt`: `-cp …/cassandra-base/build/apache-cassandra-5.0.9-SNAPSHOT.jar…`; conf copied from the int tree, identical to base). Fix: `ctl.sh`'s `launch.sh` exports `CASSANDRA_HOME` = the chosen build (file swapped atomically while `M_r2` ran). `I_r2`–`I_r4` verified on the int jar (`V-cmdline.txt`). `I_r1` is reported as an extra base-build T-equivalent run (same workload and D), not counted for V4; the spare lifetime is used for **`I_r4`**, appended after `D_r1` | harness defect found from `I_r1`'s classpath |
| A7 | 08:27 (after `T_r1`, before `T_r2`) | Harness fix: the OOM watcher used `grep -q` in a pipeline under `set -o pipefail`, so the early `grep -q` exit made the pipeline fail (SIGPIPE) on large logs; in `T_r1` it never fired, so `hist-at-oom.txt`/`nmt-at-oom.txt`/`ss-at-oom.txt` were not taken and the window ended on the process death (+5 s). Replaced by `grep -c … -gt 0` (atomic swap while `M_r1` ran). `T_r1`'s holder evidence is Cassandra's own logged heap histogram (at the forced heap OOM, +4.7 s) and its hprof | harness defect; no reading changed |

### 3.1 Environment (as run)

| Item | Value |
|---|---|
| Node | `ms0617` = `node4.jason92-326377.misconfiguration-pg0.utah.cloudlab.us`, Utah m400, **aarch64**, 8 cores, 64,249 MiB RAM, 8 GiB swap (off for the measured process), kernel **5.15.0-191-generic**, cgroup v2, `net.ipv4.tcp_wmem` = 4096 16384 4194304, `tcp_rmem` max 6 MiB. Idle at 08:11 (no Java process); `/mydata` 36 GiB free; B9's `/mydata/s4/b9-w1` untouched |
| JVM | OpenJDK 11.0.33+9 (aarch64), G1 (`jvm11-server.options`), `-Xms/-Xmx 2048M` every arm, `-XX:MaxDirectMemorySize` per arm (resolved values in `V-flags.txt`: 2,147,483,648 / 4,294,967,296 / 8,321,499,136 / 16,642,998,272 B), NMT summary, `-XX:-HeapDumpOnOutOfMemoryError` except `T_r1`, `-XX:OnOutOfMemoryError=kill -9 %p` (shipped) |
| Builds | base `/mydata/s4/cassandra-base` (5.0.9, jar sha256 `e55f4f29…5a942`, matches §1, read-only); intervention `/mydata/s4/b13-w3/cassandra-int` (copy + [`harness/intervention.diff`](harness/intervention.diff), exactly §2.8's diff; jar sha256 `866ea97953ce417f081175cfc16a07c4549c4f64cca53246d5b496fb9cbf1f78`) |
| Config | [`logs/V-yaml.diff`](logs/V-yaml.diff): cluster name, listen/rpc/seeds `127.0.0.131`, five directories; JMX port 7313. Startup lines in every arm: `Global buffer pool limit is 512.000MiB for chunk-cache and 128.000MiB for networking`; Node configuration `networking_cache_size=null; file_cache_enabled=false; native_transport_max_threads=128` (all capacity settings shipped defaults, V6) |
| Process | `systemd-run --user --scope -p MemoryMax=48G -p MemorySwapMax=0` (safety only; `memory.max` 51,539,607,552, `swap.max` 0 read back in `ctl.log`); `taskset -c 0-5`; clients, sampler, `jcmd`, probe on cores 6–7 |
| Data template | 64 partitions × 56 rows × 65,536 B over v4 (`B13Load`), `count(*)` = 3,584, 2 SSTables, 236,216,093 B live; restored into every lifetime (`tmpl.sh`, 08:17–08:19, not a reading) |
| Harness | [`harness/`](harness/): `ctl.sh`, `arm.sh`, `queue.sh` (cutoff 10:25 EST), `tmpl.sh`, `B13Sample.java` (JMX every 500 ms), `B13Load.java`, `stall5.py`, `probe5.py`, `drv.py`, `nmt.sh`/`nmt.py`, `ss.sh`, `b13peaks.py`, `apply-intervention.py`, `intervention.diff` |
| Raw data | `ms0617:/mydata/s4/b13-w3/runs/<arm>/` (samples.csv, nmt.csv, cg.csv, ss.csv, probe.csv, load.log, V-logs/system.log, debug.log, gc.log*, first-oom.txt, hist-at-oom.txt, readings.json); `T_r1` hprof `runs/T_r1/cassandra-1795008275-pid130381.hprof` (98 MB, written at the forced heap OOM); `runs/summary.txt`. Excerpts: [`logs/`](logs/) |

### 3.2 Lifetimes (16 of 16 allowed; 08:19–09:01 EST)

U_F = JDK direct `MemoryUsed` peak − idle median (57.9 MiB in every arm); K = networking pool `Size − OverflowSize`;
"produced" = ΔBytesSent / 3,670,300; Σ Send-Q = server-side sum over port 9042 (`ss`); ΔU_N = (NMT Other − JDK `MemoryUsed`) − idle; t = seconds after `LOAD_START`.

| Arm | Build | D (MiB) | Sent / planned | Class | t endpoint | U_F peak | K peak | Overflow peak | Last sample: MemoryUsed / D | Produced | Σ Send-Q | ΔU_N peak | Heap peak | Probe ok/to/err (load → endpoint; after) | JVM |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `shake` | base | auto 15,872 | 8 / 8 | `NONE` | — | 16.1 | 24 | 0 | — | 8 | 4.7 | 32 | 304 | 23/0/0 | alive (not a reading) |
| `cal` | base | auto 15,872 | 896 / 896 | `NONE` | — | **3,092.8** | **128** | 2,971.3 | 0.20 at peak | 896 | 38.7 | 904.9 (burst only) | 1,261 | 69/1/0 | alive |
| `T_r1` | base | 2,048 | 736 / 1,280 | **`NIO-NET`** | **38.2** | **1,990.1** | **128** | 1,873.8 | **1.000** (UsedSize 0.976) | 640 | 38.7 | 336 | 1,256 | 36/1/0; 0/3/7 | exits +7.8 s (forced heap OOM) |
| `M_r1` | base | 2,048 | 320 / 320 | `NONE` | — | 1,076.1 | 128 | 955.4 | 0.55 at peak | 320 | 38.4 | 216 | 1,071 | 110/0/0 | alive |
| `I_r1` *(base classes, A6)* | base (int conf) | 2,048 | 752 / 1,280 | `NIO-NET` | 38.3 | 1,990.1 | 128 | 1,875.0 | 1.000 | 669 | 38.7 | 368 | 1,240 | 36/1/0; 0/4/6 | exits +8.9 s |
| `T_r2` | base | 2,048 | 720 / 1,280 | **`NIO-NET`** | **38.2** | **1,990.1** | **128** | 1,873.0 | **1.000** (0.976) | 605 | 38.7 | 224 | 1,262 | 37/0/1 (one ERROR reply); 0/2/7 | exits +6.4 s |
| `M_r2` | base | 2,048 | 320 / 320 | `NONE` | — | 1,076.4 | 128 | 955.4 | 0.55 | 320 | 38.5 | 172 | 1,252 | 110/0/0 | alive |
| `I_r2` | **int** | 2,048 | **1,280 / 1,280** | `NONE` | — | **32.7** | 40 | **0** | 0.04 | **16** | 38.7 | 160 | 1,008 | 111/0/0 | alive |
| `T_r3` | base | 2,048 | 688 / 1,280 | **`NIO-NET`** | **37.7** | **1,990.1** | **128** | 1,872.5 | **1.000** (0.975) | 618 | 38.7 | 224 | 1,244 | 36/1/0; 0/1/7 | exits +4.9 s |
| `M_r3` | base | 2,048 | 320 / 320 | `NONE` | — | 1,076.4 | 128 | 955.4 | 0.55 | 320 | 38.5 | 230 | 1,239 | 111/0/0 | alive |
| `I_r3` | **int** | 2,048 | 1,280 / 1,280 | `NONE` | — | 32.4 | 40 | 0 | 0.04 | 16 | 38.7 | 160 | 1,008 | 111/0/0 | alive |
| `B8_r1` | base | **7,936** (explicit, A4) | 2,448 / 4,992 | **`NIO-NET`** | **143.3** | **7,878.1** | 128 | 7,761.6 | 1.000 (0.994) | 2,327 | 38.7 | 336 | 1,279 | 141/1/0; 0/4/7 | exits +9.6 s |
| `B4_r1` | base | **4,096** | 1,296 / 2,560 | **`NIO-NET`** | **73.8** | **4,038.0** | 128 | 3,921.6 | 1.000 (0.988) | 1,224 | 38.7 | 256 | 1,273 | 72/1/0; 0/3/6 | exits +7.1 s |
| `BA_r1` | base | **auto = 15,872** (A4) | 4,784 / 4,992 | **`NIO-NET`** | **286.0** | **15,814.1** | 128 | 15,696.6 | 1.000 (0.997) | 4,598 | 38.7 | 384 | 1,298 | 283/2/0; 0/5/7 | exits +13.7 s |
| `D_r1` | base | 2,048 | 1,280 / 1,280, **drain** | `NONE` | — | 48.6 | 56 | 0 | 0.05 | **1,280** | 18.0 | 208 | 1,258 | 111/0/0 | alive |
| `I_r4` | **int** | 2,048 | 1,280 / 1,280 | `NONE` | — | 16.4 | 24 | 0 | 0.04 | 16 | 38.7 | 160 | 1,008 | 111/0/0 | alive |

Other readings (all arms): `Client.RequestsSize` 0.0 MiB at every 500-ms sample (requests ≈ 80 B, released at framing);
`PausedConnections` 0; `TimedOutBeforeProcessing` 0 in every base arm; `chunk-cache` pool `Size` 16 MiB; no `oom_kill` in
any scope. In the I arms `TimedOutBeforeProcessing` = 1,264 = 1,280 − 16: the deferred requests stayed queued for the
whole window and ran (as `Overloaded`, their 12 s having passed) only when the clients closed the sockets at the window end;
NTR pending ≤ 13 (re-queued every 100 ms). `held_resp_est` (U_F / 3.5 MiB) at the endpoint: 569 (D 2,048), 1,154 (4,096),
2,251 (7,936), 4,518 (15,872).

**Per-arm detail**

- **`cal`** (reachability, D auto): during the paced phase U_F rose linearly at 224 MiB per 4 s = **56 MiB/s** (16 × 3.5
  MiB/s), K reached 128 MiB at 4 s and stayed there (`INFO … Maximum memory usage reached (128.000MiB) for networking
  buffer pool, cannot allocate chunk of 8.000MiB`), everything after went to `OverflowSize`. 896 responses produced, U_F
  3,092.8 MiB → **3.45 MiB per response**; the burst of 256 was produced within 4 s (**μ ≥ 56 responses/s**). U_F stayed
  flat at 3,151 MiB from 44 s to the window end (frames held, not freed), and fell to 179 MiB as soon as the clients
  closed (overflow → 0). Σ Send-Q 38.7 MiB over 17 sockets (≈ 2.4 MiB per stalled connection), client Recv-Q 1.2 MiB.
  ΔU_N 905 MiB only at the 256-request burst (bodies encoded and waiting for the flusher), 160–222 MiB otherwise.
- **T (×3) and `I_r1`**: identical trajectories (U_F 56 MiB/s, K = 128 MiB from 4 s); the first OOM at 37.7–38.3 s, at
  a sample where JDK `MemoryUsed` = 2,048.0 MiB = D and the pool's `UsedSize` = 1,997–2,001 MiB. **First error**, all
  four ([`logs/T_r1-first-oom.txt`](logs/T_r1-first-oom.txt)):
  `WARN [epollEventLoopGroup-5-N] AbstractEventExecutor.java:168 - A task raised an exception. Task: org.apache.cassandra.transport.Flusher$ImmediateFlusher` /
  `java.lang.OutOfMemoryError: Direct buffer memory` at `Bits.reserveMemory:175` ← `ByteBuffer.allocateDirect` ←
  `BufferPool.allocate(BufferPool.java:238)` ← `BufferPool$LocalPool.get:923` ← `getAtLeast` ←
  `FrameEncoder$Payload.<init>:64` ← `FrameEncoderCrc` ← `Flusher.flushLargeMessage:173` ← `processFramedResponse:154` —
  §2.1 step 6's Flusher case. 13–37 such warnings followed (one per event loop / flush). Then, 0.5–3.0 s after the first,
  a **`ReadStage` read** (`ThreadLocalReadAheadBuffer` → `BufferType.allocate` in a `PartitionRangeReadCommand`, consistent with the
  probe's `system.local` query) also failed to reserve direct memory → `JVMStabilityInspector` → `Force heap space
  OutOfMemoryError in the presence of java.lang.OutOfMemoryError: Direct buffer memory`
  (logged 2.9–6.6 s after the first OOM; [`logs/T_r1-forced-heap-oom.txt`](logs/T_r1-forced-heap-oom.txt)) → heap histogram logged → `kill -9` (process gone
  4.9–8.9 s after the first OOM). **Holder at failure** (`jcmd GC.class_histogram` within ≈ 1–2 s of the first OOM,
  [`logs/T_r2-hist-at-oom-head.txt`](logs/T_r2-hist-at-oom-head.txt), [`logs/T_r3-hist-at-oom-head.txt`](logs/T_r3-hist-at-oom-head.txt); the logged histogram in
  [`logs/T_r1-logged-histogram-head.txt`](logs/T_r1-logged-histogram-head.txt)): **`io.netty.channel.ChannelOutboundBuffer$Entry` 16,545–16,547 and
  `org.apache.cassandra.net.BufferPoolAllocator$Wrapped` 16,545–16,546** (frames queued on the stalled channels: ≈ 570
  responses × 29 frames), `java.nio.DirectByteBuffer` 34,8xx–34,9xx, **`java.nio.DirectByteBuffer$Deallocator` 15,046–15,048**
  (the overflow `allocateDirect` buffers: 15,048 × 131,070 B = 1,881 MiB ≈ `OverflowSize` 1,873 MiB). NMT at failure
  (`T_r3`): Other committed 2,320 MiB (JDK direct 2,048 + Netty ≈ 270). The probe answered every second until the endpoint
  (one 2-s timeout per run during the load) and timed out or errored from the endpoint on.
- **M (×3)**: 320 responses produced by 20 s, U_F 1,076 MiB (**52.5 % of D**), flat from `SENT_ALL` to the window end
  (110 s), K = 128 MiB, overflow 955 MiB; no OOM line; probe 110–111/110–111 ok.
- **I (×3 valid: `I_r2`–`I_r4`)**: same 1,280 requests sent; each connection's first response was produced (16 in total)
  and filled the socket (Σ Send-Q 38.7 MiB, as in T), the channel turned unwritable, and every later request was
  deferred: U_F ≤ 32.7 MiB, overflow 0, K ≤ 40 MiB, heap 1,008 MiB; probe 111/111 ok (useful work for the reading client
  unchanged; the stalled clients receive nothing in any arm).
- **Budget ladder** (×1 each): the endpoint was reached at every budget tried, with the same first error and the same
  JVM exit: **4,096 MiB at 73.8 s, 7,936 MiB at 143.3 s, 15,872 MiB (the node's own auto value) at 286.0 s**; U_F at
  the endpoint = D − 58 MiB idle in each; K = 128 MiB in each. Time to endpoint ≈ D / 56 MiB/s.
- **`D_r1`** (supporting): the clients read; all 1,280 responses produced and drained, U_F ≤ 48.6 MiB, no overflow.

### 3.3 Deviations from the design

A1–A7 above. In short: different run root (A1); the node's auto direct value is 15,872 MiB, so B8 ran at an explicit
7,936 MiB and BA at heap 2 GiB / auto 15,872 MiB (A4); `I_r1` ran base classes and was replaced by `I_r4` (A6); the OOM
watcher failed in `T_r1` only (A7). Everything else (workload, pacing, response size, connections, budgets of the V arms,
instruments, windows, order) as frozen. Predictions vs readings: every §2.7 prediction held, except that the JVM's exit
came from a `ReadStage` direct allocation (forced heap OOM) rather than from a v5 read-buffer allocation on the event
loop; §2.6 says neither changes the class.

## 4. Conclusion (stage 2)

**Verdict: true positive.** Status: **`verified-OOM · deployment`** (endpoint: JVM direct-buffer OOM, `NIO-NET`; then
JVM exit via `JVMStabilityInspector`'s forced heap OOM and `kill -9`). Direction by measurement: **bypass, accounting
omission** (U > C, K ≤ C) in domain F. Interpretation: missing aggregate control on outbound response memory (no
writability check; the CASSANDRA-11082 shape), plus a networking pool whose documented "maximum memory" is a cap on
pooled slabs only, with an unchecked overflow path. Configuration and budget: every capacity setting at its shipped
default; heap 2 GiB and direct 2 GiB (standing rule), endpoint also at 4 GiB, 7.75 GiB and the node's own auto value
15.5 GiB.

**Reason.** One node at shipped defaults (`networking_cache_size` unset → 128 MiB at heap 2 GiB), heap 2,048 MiB and
`MaxDirectMemorySize` 2,048 MiB, 16 protocol-v5 connections that send one `SELECT` of a 3.67 MB partition per second
each and never read: the networking pool stopped at K = 128 MiB 4 s after load start, and every later response frame
was an unpooled 131,070-B `allocateDirect` buffer held in the channel's outbound buffer. The JDK direct reservation (U_F,
measured independently of the pool) rose at 56 MiB/s to 1,990 MiB (15.5 × C) and the node threw `OutOfMemoryError:
Direct buffer memory` from `BufferPool.allocate:238` in `Flusher.flushLargeMessage` on the event loop at **37.7–38.2 s in
3/3 runs** (`T_r1`–`T_r3`; a fourth base-class run, `I_r1`, at 38.3 s), with **16,545–16,547 `ChannelOutboundBuffer$Entry`**
and 15,046–15,048 overflow `DirectByteBuffer$Deallocator` live at failure (15,048 × 131,070 B = 1,881 MiB ≈ `OverflowSize`
1,873 MiB); 2.9–6.6 s later a read thread's direct allocation failed, `JVMStabilityInspector` forced a heap OOM and the
JVM was killed, and the probe lost service. Request accounting never saw it (`RequestsSize` 0.0 MiB, no paused
connections, no `TimedOutBeforeProcessing`). The matched control with a quarter of the requests (320 held responses)
held U_F flat at 1,076 MiB (52.5 % of D) with K = 128 MiB and did not fail (0/3); the intervention that defers requests
of unwritable channels (`harness/intervention.diff`) at the same 1,280 requests kept U_F ≤ 32.7 MiB with no overflow and
the probe 111/111 ok (0/3, `I_r2`–`I_r4`). The endpoint was reached at every budget up to the node's own resolved
direct limit: **4,096 MiB at 73.8 s, 7,936 MiB at 143.3 s, 15,872 MiB at 286.0 s** (1/1 each), always with K = 128 MiB:
the knob decides only the pooled/overflow split, and the only bound on held frames is `MaxDirectMemorySize`.

**Per-condition status**

| Condition | Runs | n/N | Status |
|---|---|---|---|
| heap 2 GiB, direct 2 GiB, defaults, 16 stalled v5 clients, 1,280 requests | `T_r1`–`T_r3` | 3/3 OOM | `verified-OOM · deployment` |
| same, 320 requests (matched control) | `M_r1`–`M_r3` | 0/3 | control (no endpoint) |
| same as T, intervention build | `I_r2`–`I_r4` | 0/3 | intervention removes the endpoint |
| direct 4,096 / 7,936 / 15,872 MiB (heap 2 GiB) | `B4_r1`, `B8_r1`, `BA_r1` | 1/1 each | largest failing budget tried: **15,872 MiB** (node auto); no surviving budget found |
| same as T, clients read (supporting) | `D_r1` | 0/1 | frames freed as written |

**V1–V7**

| | Met | Evidence |
|---|---|---|
| V1 Repetition | yes | `T_r1`–`T_r3`: `NIO-NET` 3/3 at 37.7–38.2 s from clean lifetimes (plus `I_r1`, base classes, 38.3 s) |
| V2 Matched control | yes | `M_r1`–`M_r3`: 0/3, same build, budget, data, connections, pacing; U_F 1,076 MiB = 52.5 % of D (margin 47.5 % ≥ 30 %) |
| V3 Measurement | yes | U_F = JDK `java.nio` direct `MemoryUsed` (independent of the pool) 1,990 MiB > C = 128 MiB; K = `Size − OverflowSize` = 128 MiB ≤ C; histogram counts of `ChannelOutboundBuffer$Entry`/`BufferPoolAllocator$Wrapped`/`DirectByteBuffer$Deallocator` match the held frames |
| V4 Intervention | yes | `I_r2`–`I_r4`: 0/3 at the same load (1,280 requests sent, 16 responses produced, 1,264 deferred), U_F ≤ 32.7 MiB, probe 111/111 ok; `I_r1` excluded (ran base classes, A6) |
| V5 Initiating failure | yes | first error: `java.lang.OutOfMemoryError: Direct buffer memory` on `epollEventLoopGroup-5-*` in `Flusher$ImmediateFlusher` → `flushLargeMessage:173` → `FrameEncoder$Payload.<init>:64` → `BufferPool.allocate:238` ([`logs/T_r1-first-oom.txt`](logs/T_r1-first-oom.txt) and T_r2/T_r3); histogram at failure ([`logs/T_r2-hist-at-oom-head.txt`](logs/T_r2-hist-at-oom-head.txt), [`logs/T_r3-hist-at-oom-head.txt`](logs/T_r3-hist-at-oom-head.txt), [`logs/T_r1-logged-histogram-head.txt`](logs/T_r1-logged-histogram-head.txt)); `T_r1` hprof on the node |
| V6 Default constraints | yes | yaml diff = environment keys only; `networking_cache_size=null` → 128 MiB, `native_transport_*` defaults, `file_cache_enabled=false` (startup lines in every arm) |
| V7 Acceptable budget | yes | heap 2,048 MiB and direct 2,048 MiB (≥ 512 MiB standing rule, the ideal value); endpoint also at 4,096, 7,936 and 15,872 MiB (the node's own `cassandra-env.sh` value under G1) |

**Conditions label: deployment.** No supporting deviation: shipped capacities and timeouts, no injected delays or
instrumentation that alters timing (JMX polling every 500 ms, NMT summary); the fault is external (clients that send but
do not read), within protocol limits (≤ 80 stream ids per connection, 16 connections, requests ≈ 80 B). The 48 GiB scope
is a non-binding safety limit (no `oom_kill`).

**Limits of attribution.**

- The intervention is a diagnostic patch, not a proposed fix. It removes the endpoint by producing no response for an
  unwritable channel. Requests then wait in the executor until the channel drains or closes, and in this run they were
  answered `Overloaded` at close. It shows that responses produced for a non-reading client are the cause. It does not
  show the cost of a real backpressure design.
- Pacing at 16 requests/s keeps every request within `native_transport_timeout` (12 s). A client that sends faster sees
  the excess answered with small `Overloaded` errors instead of 3.5 MiB responses. The held demand therefore grows at
  min(λ, μ) × response size, with μ ≥ 56 responses/s measured here. Fewer, slower or smaller-response clients reach the
  same endpoint later. The time to endpoint is ≈ D / (λ × response size).
- The JVM exit came from a `ReadStage` direct allocation that failed once the JDK limit was exhausted (forced heap OOM).
  It did not come from the event-loop read-buffer path of CASSANDRA-19535. Whatever thread next needs direct memory
  takes the node down, so which path ends the process depends on timing.
- Single node, clients on loopback; the kernel held ≈ 2.4 MiB per stalled connection (Σ Send-Q 38.7 MiB). Over a real
  network the kernel share differs per connection but stays bounded. aarch64 m400.
- Relation to C2 (v4): the trigger is the same, but the holder and limit differ. B13's frames sit in the `networking`
  `BufferPool` overflow, which is charged to the JDK `Bits` reservation. Netty's domain N stayed at ΔU_N 160–384 MiB
  in every arm.

**Retry change:** none (true positive). **New clue pattern:** none needed; the shape is CP-5 (accepting queue with a
stalled consumer, no writability check) together with CP-6 (pool overflow bounded only by `MaxDirectMemorySize`). C2 is
already the phase-2 example of both.
