# B9 — native_transport_max_request_data_in_flight: v4 request frames force-admitted once per connection exhaust Netty's direct counter  <!-- file: cassandra/cases/native_transport_max_request_data_in_flight--v4-frames-per-connection/native_transport_max_request_data_in_flight--v4-frames-per-connection.md -->

| Field | Value |
|---|---|
| Case ID | `B9` (B = bypass investigation; campaign row B9 / P2) |
| From | `OC-60` of the phase 1 OOM candidate list |
| Phase-1 case file | [`native_transport_max_request_data_in_flight-releaseItem-globalInFlightBytesBelowLimit--autonomous`](../../../../capacity-enforcement-exp/cassandra/stage3-ai-deep-read/cases/native_transport_max_request_data_in_flight-releaseItem-globalInFlightBytesBelowLimit--autonomous.md) |
| System / pinned source | Cassandra 5.0.9 (`systems/cassandra/source/`, unpatched) |
| Stage 1 (design) | OOM agent stage 1 (Claude Opus 5.5, workflow subagent), 2026-11-17 22:45–23:30 EST |
| Stage 2 (verify) | fresh OOM-agent sessions (Claude Opus 5.5, workflow subagents): runs 2026-11-17 23:02–23:48 EST; interrupted by an API usage limit; resumed 2026-11-18 02:54 EST (no new arms, §3.1) |
| Verdict | **`true positive`** — `verified-OOM · deployment` (bypass, accounting omission × unlimited connections) |

## Summary

- **Conclusion:** true positive. At shipped defaults, heap 4 GiB and direct 1,280 MiB, a 128-request burst of
  15 MiB v4 writes over 128 connections killed Cassandra 3/3 (Netty `OutOfDirectMemoryError` in the request
  decoder ≈ 2.3 s into the burst, then a forced heap OOM). The same frames over 32 connections (control) and the same
  128 requests over 8 connections (intervention) survived 3/3 each. `verified-OOM · deployment`; 2 GiB direct untested.
- **Root cause (measured):** Netty's direct counter reached 1,280 MiB, mostly request frames still being read
  (3.0 × the contract C = 424.6 MiB), while the in-flight counter held only 75–180 MiB and no connection was paused: frames are held in
  pooled direct memory *before* `native_transport_max_request_data_in_flight` is checked, and connections are
  unlimited, so the limit never gets a chance to act. The force-admit overshoot below (the design's hypothesis) is
  real at large budgets but did not drive these failures (§3.5).
- **Root cause (hypothesis under test, stage 1):** on protocol v4 connections a whole request frame is buffered in Netty's
  pooled direct memory (one 16 MiB chunk per 15 MiB frame) and decoded before
  `native_transport_max_request_data_in_flight` is consulted; a request that fails the reservation is still
  admitted (force-allocated) and only the connection is paused, so each connection holds at least one frame
  beyond the limit, and connections are unlimited at defaults. Netty's own direct counter (limit =
  `MaxDirectMemorySize`, separate from the JDK's) then fills with C × 16 MiB.

## 1. Candidate

**Candidate row (quoted from the phase-1 OOM candidate list, 2026-11-17):**

> | OC-60 | 2026-11-17 | `native_transport_max_request_data_in_flight-releaseItem-globalInFlightBytesBelowLimit--autonomous` | legacy | [campaign B9 / P2, never run; U1 run 1 side result] Native v4 request frames of large writes sit in Netty's direct memory (a 16 MiB chunk per 15 MiB frame) from decode to response, and `native_transport_max_request_data_in_flight` (heap/10) is checked only after decode; 8 connections × 3–4 in flight held 416–564 MiB (≈ 2–2.5× the limit) and killed U1 arms at 512–576 MiB direct | CP-6, CP-11 | picked: B9 |

Campaign row: [`campaign-plan.md`](../../campaign-plan.md) row "B9 / P2" (researcher's decision 2026-11-17).

**Phase-1 constraint and check.** `native_transport_max_request_data_in_flight` (yaml; default `null` →
`Runtime.maxMemory()/10`, `DatabaseDescriptor.java:649-652`) and `_per_ip` (heap/40, `:654-657`) feed
`ClientResourceLimits` (`GLOBAL_LIMIT`, per-IP `Allocator`). On v4 connections `LegacyDispatchHandler.checkLimits`
(`PreV5Handlers.java:151-209`) charges `header.bodySizeInBytes` after the frame is decoded; on a failed
`tryAllocate` the default (non-throw) path force-allocates (`:184`) and pauses the connection (`:185`); the
request is dispatched anyway (`:87`). The phase-1 target check `PreV5Handlers.java:127` unpauses a connection
when its own in-flight bytes reach 0 **or** both reserves are below their limits.

**Phase-1 stage-4 result** ([results](../../../../capacity-enforcement-exp/cassandra/stage4-runtime-verification/results/native_transport_max_request_data_in_flight-releaseItem-globalInFlightBytesBelowLimit--autonomous.md),
pc12 x86, 2026-10-22): unit U3 and cluster C5 **confirmed** — the accounted bytes are a *soft* cap with an
overshoot of one request per connection (peak = (⌊L/S⌋ + 1)·S; 95·S at L = 64 MiB with 32 connections).
Pooled direct memory (Netty made visible with `-Dio.netty.maxDirectMemory=0`) followed the accounted bytes at
Δdirect ≈ 1.2 GiB + 2.1 × `RequestsSize` (1 MiB frames, 8 GiB heap, 40 cores). Side finding: the THROW_ON_OVERLOAD
path retains rejected envelopes (not used here).

**U1 run 1 side evidence** ([U1 case §3.5](../candidates/concurrent_writes+max_mutation_size--inflight-DOB-fill/concurrent_writes+max_mutation_size--inflight-DOB-fill.md),
pc96 x86, heap 2 GiB): 4 arms died of `io.netty.util.internal.OutOfDirectMemoryError: failed to allocate
16777216 byte(s) of direct memory (used: 504–564 MiB, max: 512–576 MiB)` on an `epollEventLoopGroup` thread in
`ByteToMessageDecoder.cumulate` → `PoolArena.reallocate` → `newChunk`, with 8 connections × 3–4 outstanding
15 MiB writes (`B_d512_r1` 6 s, `E3_d512_r1` 23 s, `B_d576_r3` 17 s, `E3_d576_r4` 16 s after load start;
excerpt [`B_d512_r1-netty-first-oom.txt`](../candidates/concurrent_writes+max_mutation_size--inflight-DOB-fill/logs/B_d512_r1-netty-first-oom.txt)).
The Netty counter in the dumps was 488–520 MiB while the global limit was 204.8 MiB. That workload was not
designed for this case (one budget family, no K/U ledger, no control or intervention).

**JIRA prior art** (read only; nothing posted). Survey
`capacity-enforcement-exp/cassandra/stage5-oom-clue-find/jira-oom-survey.csv` (604 rows) searched for in-flight,
frame, connection, Netty and native-transport rows; JIRA REST search on 2026-11-17 22:55 EST:
`text ~ "OutOfDirectMemoryError"` (1 hit), `text ~ "native_transport_max_request_data_in_flight"` (17),
`text ~ "native_transport_max_concurrent_requests_in_bytes"` (39), `text ~ "bytes in flight" AND text ~ "connections"` (21),
`text ~ "PreV5Handlers"` (10), `text ~ "max_concurrent_connections" AND text ~ "memory"` (32).

| Issue | Status | Relation |
|---|---|---|
| CASSANDRA-15013 | Fixed 3.0.19 / 3.11.5 / 4.0 | introduced the v4 bytes-in-flight limit and pause-reading: the control under test |
| CASSANDRA-15519 | Fixed | made the limits settable at runtime |
| CASSANDRA-8518 → 9318 | Duplicate / Fixed 3.10 | in-flight data limit request (heap); response bytes uncovered |
| CASSANDRA-4265 | Won't Fix | Thrift HSHA: per-connection frame buffers × unlimited connections OOM; the same multiplicity shape in an older server, connections still unlimited by default in 5.0.9 |
| CASSANDRA-12034 | Fixed 3.8 | Netty `OutOfDirectMemoryError` for *response* buffers to be handled as a request error; 5.0.9 has no reference to `OutOfDirectMemoryError` in `src/`, and the request-decode path goes to `JVMStabilityInspector.inspectThrowable` (`PreV5Handlers.java:368`), which forces a heap OOM (`JVMStabilityInspector.java:193-206`) and the JVM dies (U1 run 1 observed this) |
| CASSANDRA-19534 | Fixed 5.0-rc1 | bounded native-transport queue time (`native_transport_timeout` 12 s, shedding): bounds how long a queued frame waits |
| CASSANDRA-20052 | Fixed 5.0.3 | the v5 sibling (CQL message size unlimited in v5 logic); included in 5.0.9; v5 is not this path |
| CASSANDRA-21508 / 21766 | Fixed 5.0.9 / Fixed 5.0.10 | 21508 moved v4 response encoding onto the request worker; 21766 (not in 5.0.9) leaks Netty memory when a v4 channel closes with a request in flight. A **confound to avoid**: the design keeps every client connection open until after the endpoint or the end of the observation window |
| CASSANDRA-11082 | Open | outbound (slow-reader) direct growth; the C2 case, not this one |

**Verdict: `new`.** No issue reports request frames held in Netty's direct counter beyond the in-flight limit
by one force-admitted frame per connection; the related tickets cover the limit's introduction, the v5
sibling, the response-side Netty OOM handling and a different leak.

## 2. Design solution (stage 1; frozen)

Technique note: [`bypass-playbook.md`](../../../bypass-playbook.md), row "Failed reservation but admitted work"
(with an accounting-mismatch component). Protocol: [`verification-protocol.md`](../../../verification-protocol.md).
Platform: **aarch64** (Utah m400). Not comparable arm by arm with the x86 stage-4 or U1 readings.

### 2.1 Mechanism

Direction label: **bypass — enforcement failure (work admitted after a failed reservation)**, with a secondary
accounting mismatch (Netty holds a 16 MiB chunk per 15 MiB charged body, plus the transient copy while the
cumulation grows). Expected classification: U > C and K > C in the Netty-direct domain.

1. A v4 client sends an EXECUTE of a prepared `INSERT` with one 15 MiB blob (15,728,640 B; frame ≈ 15,728,700 B,
   under `native_transport_max_frame_size` 16 MiB, `Config.java:285`, and `max_mutation_size` 16 MiB).
2. The legacy pipeline (`PipelineConfigurator.java:388-397`) runs `Envelope.Decoder`, a Netty
   `ByteToMessageDecoder`: the frame accumulates in a cumulation buffer allocated from
   `CBUtil.allocator = new PooledByteBufAllocator(true)` (`CBUtil.java:60`). The buffer grows by reallocation
   (doubling to 4 MiB, then 4 MiB steps) and ends at 16 MiB = one whole pool chunk
   (`-Dio.netty.allocator.maxOrder=11`, `conf/jvm11-server.options:145`). The body is
   `buffer.slice(...).retain()` (`Envelope.java:448-449`), so the 16 MiB buffer stays pinned until the envelope
   is released. **No limit is consulted while the frame is read.**
3. `PreV5Handlers.ProtocolDecoder` decodes the message; bound values are copied to the heap
   (`CBUtil.readValue` → `readRawBytes`, `CBUtil.java:443-449`).
4. `LegacyDispatchHandler.channelRead0` → `checkLimits` (`PreV5Handlers.java:82-88`, `:151-209`): the size is
   added to `channelPayloadBytesInFlight` (`:179`); if `tryAllocate` on the endpoint+global reserves fails, the
   size is **allocated anyway** (`:184`, `ResourceLimits.java:146-154`, `:275-279`) and the connection is paused
   (`:185`, `autoRead=false`); the request is dispatched regardless (`:87`). Rate limiting and queue-age
   backpressure are off by default.
5. The frame is released only when the response is flushed (`Flusher` → `releaseItem`,
   `PreV5Handlers.java:100-129`): after the coordinator finishes or times out. With `cql_start_time: REQUEST`
   (`Config.java:1391`) the write deadline counts from the start of processing: ≤ `write_request_timeout` 2 s
   (`Config.java:151`) after a `Native-Transport-Requests` thread (128, `Config.java:283`) picks it up; a request
   waiting for a thread can queue up to `native_transport_timeout` 12 s (`Config.java:1399`, `Dispatcher.java:364`)
   before it is shed.
6. Multiplicity: `native_transport_max_concurrent_connections` and `_per_ip` are −1 (unlimited,
   `Config.java:289-290`). With C connections each holding one request, accounted bytes K ≈ C·S regardless of
   L; physical Netty bytes U ≈ C × 16 MiB + growing cumulations. Netty's counter limit is `MaxDirectMemorySize`
   (`io.netty.maxDirectMemory` unset; `PlatformDependent.incrementMemoryCounter`), **separate** from the JDK
   `Bits` counter of `ByteBuffer.allocateDirect`.
7. Endpoint: the next chunk allocation throws `io.netty.util.internal.OutOfDirectMemoryError`; the pipeline's
   exception handler calls `JVMStabilityInspector.inspectThrowable` (`PreV5Handlers.java:368`;
   `JVMStabilityInspector.java:108-131`), which forces a heap OOM (`:193-206`) so that
   `-XX:OnOutOfMemoryError=kill -9 %p` (cassandra-env) kills the JVM.

**Hold-time caveat (what the calibration measures).** Frames are released ≤ ≈ 2 s after processing starts, so
the number held at once is N_held ≈ min(C·k, frames decoded within the hold window), where the window is ≈ 2 s
while NTR threads are free and grows by the NTR queue wait once all 128 are blocked (i.e. when the decode rate
exceeds ≈ 64 frames/s). On the m400 the decode rate (loopback, cumulation copies, heap copy) is unknown, so
§2.5 calibrates it before choosing the budget.

### 2.2 Protection map (fixed before readings)

| Domain | Allocation / owner / release | Local contract (C) | Scope and multiplicity | Aggregate coverage | Lifetime | Budget |
|---|---|---|---|---|---|---|
| **N: v4 request frames (claimed)** | Netty pooled direct chunk (16 MiB per 15 MiB frame) for the cumulation; pinned by the envelope body slice; released at response flush | `native_transport_max_request_data_in_flight` L = heap/10 of `bodySizeInBytes` (global) and heap/40 per IP; contract **C = L + S** (the crossing request "is allowed to finish", code comment `PreV5Handlers.java:84-85`); hard only with THROW_ON_OVERLOAD | per connection; connections unlimited (−1); ≤ 128 in NTR threads + NTR queue (≤ 12 s) | the same L is the only aggregate; the frame is buffered before it is checked; chunk rounding and growth copies uncounted | decode → response (≤ queue wait + 2 s) | Netty counter = `MaxDirectMemorySize` |
| H: heap copies and decoded messages | `CBUtil.readValue` heap copy (15 MiB per request), `Message`, `Mutation` | charged to the same K (body bytes) | per decoded request | none beyond K | decode → request done; a timed-out write's `Mutation` stays queued on `MutationStage` (S2 shape, `StorageProxy.java:2623-2660`, re-run as a hint runnable) until applied | heap |
| J: JDK direct (U1 domain, competing) | `DataOutputBuffer` scratch in `CommitLog.add` (direct), hints buffer, NIO | none in flight (`max_mutation_size` per mutation) | ≤ `concurrent_writes` 32 × 2–3 × S ≈ 0.94–1.4 GiB transient | none | serialize → copy | JDK `Bits` counter = `MaxDirectMemorySize` |
| M: memtable | `heap_buffers` | heap/4 = 1,024 MiB at 4 GiB heap; flush at cleanup threshold | per table | flush | until flush | heap |

Only domain N is claimed. H, J and M are monitored as competing endpoints.

### 2.3 Configuration and budget audit

| Setting | Class | Value (resolved) |
|---|---|---|
| `native_transport_max_request_data_in_flight` | **default** (absent) | heap/10 = 429,496,729 B (409.6 MiB) at `-Xmx4G` (G1 `maxMemory` = 4,294,967,296); 858,993,459 B at 8 GiB (boundary arms only) |
| `native_transport_max_request_data_in_flight_per_ip` | default | heap/40 = 107,374,182 B (102.4 MiB) at 4 GiB |
| `native_transport_max_concurrent_connections`, `_per_ip` | default | −1, −1 (unlimited) |
| `native_transport_max_frame_size` | default | 16 MiB |
| `native_transport_max_threads` | default | 128 |
| `native_transport_timeout`, `write_request_timeout`, `cql_start_time` | default | 12 s, 2 s, REQUEST |
| `native_transport_rate_limiting_enabled`, queue max item age | default | false, `Double.MAX_VALUE` |
| `concurrent_writes`, `max_mutation_size`, `commitlog_segment_size`, commit-log sync | default | 32, 16 MiB, 32 MiB, periodic 10 s |
| memtable | default | `heap_buffers`, heap/4 |
| Netty allocator | shipped `jvm11-server.options` | `useCacheForAllThreads=true`, `maxOrder=11` (16 MiB chunks); `io.netty.maxDirectMemory` unset (Netty counter limit = `MaxDirectMemorySize`); direct arenas = min(2 × 6 cores, D/16 MiB/6) (12 at D ≥ 1,152 MiB; record) |
| yaml diff | environment | `cluster_name: 'b9'`, `listen_address`/`rpc_address` 127.0.0.81, seeds `127.0.0.81:7000`, data/commitlog/hints/saved_caches/cdc directories under `/mydata/b9/node`; JMX port 7299 |
| JVM extras | instrumentation (all arms alike) | `-XX:NativeMemoryTracking=summary`; `-Dcassandra.printHeapHistogramOnOutOfMemoryError=true` (acts only after the first OOM); `-XX:-HeapDumpOnOutOfMemoryError` except in the one arm that keeps a dump (§2.5) |
| heap | **budget** | **4,096 MiB** (calibration and V arms); 8,192 MiB only in the upward boundary arms (§2.5 step 6) |
| `MaxDirectMemorySize` | **budget (dial)** | calibration: **auto** (not passed; `cassandra-env.sh` resolves ¼·RAM capped at 31,744/2 = **15,872 MiB** on the m400, record from `VM.flags`); V arms: **D\*** from the calibration rule, a ladder value ≥ 512 MiB |
| process scope | environment (non-binding) | `systemd-run --user --scope -p MemoryMax=48G -p MemorySwapMax=0` (swap 0 for the measured process); linger on for the run, off at the end |
| CPU | environment | Cassandra `taskset -c 0-5`; client, sampler and `jcmd` on 6–7 |
| storage | environment | `/mydata` (SATA SSD ≈ 100 MB/s, local), not tmpfs |

**V7 argument (written before readings).** The standing rule (2026-11-11) accepts any heap or direct limit
≥ 512 MiB without a per-case review; 2 GiB is the ideal. Heap 4,096 MiB with direct 2,048 MiB is exactly what
`cassandra-env.sh` resolves for an **8 GiB node** (½ and ¼ of RAM, `conf/cassandra-env.sh:57-67`); heap 8,192 /
direct 4,096 MiB is the resolution for a 16 GiB node. A D\* below 2,048 MiB with a 4 GiB heap is set with the
documented `MAX_DIRECT_MEMORY_SIZE` override (`cassandra-env.sh:120`, `:139-140`) and is acceptable by the
standing rule as long as D\* ≥ 512 MiB. No container/cgroup limit is a budget here (the scope is a non-binding
safety net). The design searches for the **largest** failing direct budget (§2.5). Researcher's review: not
required (standing rule).

### 2.4 Ceiling arithmetic

S = 15,728,640 B body (15.0 MiB, 1.0 frame); one held frame = 16 MiB on Netty's counter (+ up to one 12 MiB old
buffer per event loop during the final reallocation; ≤ 12 event loops).

| Quantity | Value |
|---|---|
| Contract C (domain N) at heap 4 GiB | L + S = 409.6 + 15.0 = 424.6 MiB (≈ 28 frames); Netty equivalent ≈ 28 × 16 = 448 MiB |
| K at C connections, k = 1 request each, all decoded | C·S: C = 128 → 1,920 MiB = **4.5 × C**; C = 64 → 960 MiB |
| U (Netty) at N_held frames | ≈ N_held × 16 MiB + Netty idle (measured) + growth transients: N = 128 → 2,048 MiB + idle |
| Budget D | Netty counter dies at the first chunk that would pass D: N_held ≥ (D − idle)/16 MiB, e.g. 2,048 → 128 frames, 1,536 → 96, 1,024 → 64, 768 → 48, 512 → 32 |
| Heap at the burst (domain H) | ≈ 0.3 GiB baseline + N_decoded × 15 MiB + memtable (≤ 1 GiB) ≤ 0.3 + 1.9 + 1.0 = 3.2 GiB for a 128-request burst, < 4 GiB: the heap is not expected to fail first. Bursts > 140 requests at 4 GiB would risk a heap OOM first (hence C ≤ 128 at 4 GiB) |
| JDK direct (domain J) | ≤ 43 MiB idle + 32 × 3 × 15 MiB ≈ 1.45 GiB transient; U1 with 15 MiB mutations on these m400s: 0/8 failures down to 640 MiB (U1 run 2). A J endpoint is possible only at D\* ≤ ~1,024 MiB and is recorded as competing |

Convergence check is not the claim; the bypass claim is U > C with K > C in domain N, and the OOM claim is that
N alone exhausts Netty's counter at D\*.

### 2.5 Workload, environment and procedure

**Node.** `ms0617` only (node4.jason92-326377, Utah m400, **aarch64**, 8 cores, 62.7 GiB RAM, 8 GiB swap,
`/mydata` 39 GiB with 37 GiB free, SATA SSD; checked read-only 2026-11-17 22:46 EST: idle, no Java process,
`Linger=no`, existing `/mydata/s2r2` and `/mydata/u1r2` belong to other cases — **do not touch them**). Client
and server colocated (loopback). Never mix with x86 nodes.

**Build** (none exists under `/mydata/s4` on ms0617):

```bash
# on the local node (repository checkout):
T=$(mktemp -d)
experiments/capacity-enforcement-exp/cassandra/stage4-runtime-verification/copy-source.sh $T/cassandra-base
ssh ms0617 'test ! -e /mydata/s4/cassandra-base && mkdir -p /mydata/s4'
rsync -a $T/cassandra-base/ ms0617:/mydata/s4/cassandra-base/ && rm -rf $T
# on ms0617 (≈ 5–6 min on the m400; Maven downloads work there, U1 run 2 built the same way):
cd /mydata/s4/cassandra-base && ( setsid nohup ant jar < /dev/null > /mydata/s4/build-b9.log 2>&1 & )
# done when the log ends with BUILD SUCCESSFUL; then record:
git -C /mydata/s4/cassandra-base describe --tags          # cassandra-5.0.9
md5sum /mydata/s4/cassandra-base/build/apache-cassandra-5.0.9-SNAPSHOT.jar
ls /mydata/s4/cassandra-base/build/lib/jars | grep -E 'cassandra-driver-core-3.12.1-shaded|guava-32|metrics-core-4|epoll.*aarch_64'
```

The build is read-only after this (never run `ant` in it again); runs use `/mydata/b9/`.

**Harness** (in this case folder `harness/`, copied to `/mydata/b9/h` on the node; derived from U1 run 1's
[`harness/`](../candidates/concurrent_writes+max_mutation_size--inflight-DOB-fill/harness/)):

- `ctl.sh` (from U1 `ctl.sh`): `BUILD=/mydata/s4/cassandra-base`, `D=/mydata/b9/node`, `IP=127.0.0.81`,
  `JMXP=7299`, `CPUS=0-5`, cluster name `b9`, scope `MemoryMax=48G MemorySwapMax=0`; env `XMX` (default
  `4096M`), `DIRECT` (MiB or `auto`), `DUMP` (1 = keep `HeapDumpOnOutOfMemoryError` with
  `CASSANDRA_HEAPDUMP_DIR=$D/dumps`; 0 = add `-XX:-HeapDumpOnOutOfMemoryError`), `VEXTRA` unused (no capacity
  changes in any arm). Always add `-XX:NativeMemoryTracking=summary -Dcassandra.printHeapHistogramOnOutOfMemoryError=true
  -XX:ErrorFile=...`. Same `gen` sed edits as U1 (the 5.0.9 yaml lines: `cluster_name` :26, seeds :706,
  `listen_address` :981, `rpc_address` :1090, directories :97/:395-396/:408/:431/:611).
- `B9Load.java` (from `U1Load.java`), driver 3.12.1, **protocol V4**, prepared
  `INSERT INTO b9.t (pk, b) VALUES (?, ?)`, CL ONE, keyspace `b9` RF 1 (SimpleStrategy), table
  `b9.t (pk int PRIMARY KEY, b blob)`, zero-filled 15,728,640-byte blob, `pk = floorMod(n, 16)` (`-Dkeys=16`, keeps
  sstables small). Usage `B9Load run <blobBytes> <connsPerWriter P> <inflightPerWriter Q> <seconds> <sustainRate R> <host>`
  with `-Dsrcips=127.0.1.1,...` (one `Cluster` per writer, bound to its source IP, as U1). Changes from U1Load:
  (a) `PoolingOptions.setConnectionsPerHost(LOCAL, P, P)`, `setMaxRequestsPerConnection(LOCAL, 2048)`;
  (b) one shared `NioEventLoopGroup(2)` and one shared `HashedWheelTimer` for all clusters through `NettyOptions`
  (`eventLoopGroup`, `channelClass` = `NioSocketChannel`, `timer`, no-op `onClusterClose` for both,
  `afterBootstrapInitialized` binds the source IP; shaded classes `com.datastax.shaded.netty.*`); (c) every
  writer connects, prepares, and waits until `session.getState().getOpenConnections(host) == P` (≤ 30 s), then
  all writers wait on one `CountDownLatch`; the client prints `BURST_START <epoch_ms>` and every writer issues
  its Q requests at once (**burst**, no rate limiter; the driver puts them on the least-busy connections, i.e.
  Q/P per connection); (d) after the burst each completion frees one permit and the next request waits on a
  shared Guava `RateLimiter(R)` (**sustain** phase, R = 6/s ≈ 90 MiB/s, about what the m400's disk applies) until
  `<seconds>` after `BURST_START`; (e) prints `BURST_DONE <epoch_ms>` when all W·Q burst requests have completed
  (ok or error), a 1-s progress line (sent, ok, errors by class), and `FINAL`. Client JVM:
  `taskset -c 6-7 java -Xmx6g -XX:MaxDirectMemorySize=16g`. No client disconnects before the end of the window
  (CASSANDRA-21766 confound); read timeout 60 s; `FallthroughRetryPolicy`.
- `B9Sample.java` (from `U1Sample.java`), JMX `127.0.0.1:7299`, **every 500 ms**: heap used;
  `java.nio:type=BufferPool,name=direct` `MemoryUsed`, `Count` (JDK counter); **K** =
  `org.apache.cassandra.metrics:type=Client,name=RequestsSize` `Value`; `type=Client,name=PausedConnections`
  `Value`; `type=Client,name=ConnectedNativeClients` `Value`; `type=Client,name=ConnectionPaused` `Count`;
  `type=Client,name=RequestDispatched` `Count`; `type=Client,name=TimedOutBeforeProcessing` `Count`;
  `Native-Transport-Requests` active/pending; `MutationStage` active/pending/completed; `ClientRequest,scope=Write`
  `Timeouts` and `Latency` count; `Table,keyspace=b9,scope=t,name=AllMemtablesHeapSize`; dropped `MUTATION_REQ`.
  (Verify every ObjectName in the shakedown; a missing one is a harness fix, not a design change.)
- `nmt.sh` + `nmt.py`: every **2 s** `taskset -c 6-7 jcmd <pid> VM.native_memory summary`, parse
  `Other (reserved=…KB, committed=…KB)` and `Total`, write `epoch_ms,other_committed_kb,total_committed_kb` to
  `nmt.csv`. A 1-s loop writes `epoch_ms,RssAnon_kB,memory.current,oom_kill` to `cg.csv` (`/proc/<pid>/status`,
  the scope's cgroup).
- `arm.sh <name> <directMiB|auto> <W> <P> <Q> [window_s=45] [xmx=4096M] [dump=0]`: preflight (no
  `CassandraDaemon` running, `/mydata` free ≥ 10 GiB, `MemAvailable` ≥ 20 GiB, else abort the queue), `ctl.sh gen`,
  start, wait for `Starting listening for CQL clients` (≤ 180 s), `B9Load schema`, start the samplers, **10 s idle
  baseline**, run `B9Load run 15728640 P Q window 6 127.0.0.81` with `-Dsrcips=127.0.1.1..127.0.1.W`, then 15 s
  idle, collect `system.log`, `gc.log*`, `first-oom.txt` (first OOM line with 3 lines before and 40 after,
  excluding the JVM-arguments line), the heap-histogram lines from `system.log`, `V-flags.txt` (`MaxDirectMemorySize`,
  `MaxHeapSize`), `V-yaml.diff`, `V-cmdline.txt`; stop the node; classify; append one line to
  `/mydata/b9/runs/summary.txt`; wipe `data/commitlog/hints/saved_caches`. A dead arm's `hprof` (only when
  `dump=1`) is moved into the arm folder.
- `b9peaks.py <armdir>`: from `samples.csv`, `nmt.csv`, `cg.csv`, `load.log`, `first-oom.txt`:
  - X0 = median over the idle baseline of (NMT Other − JDK `MemoryUsed`);
  - **ΔU_netty(t)** = NMT Other(t) − JDK `MemoryUsed`(nearest sample) − X0; **ΔU_peak** = its maximum;
  - **U_fail** = `used` in the Netty error message (absolute Netty counter at failure);
  - **K_peak** (MiB and N = K/S frames), `PausedConnections` peak, `ConnectedNativeClients`;
  - decode rate = Δ`RequestDispatched` over the first 5 s after `BURST_START` / 5;
  - ΔRssAnon peak, heap peak, JDK direct peak, NTR active/pending peaks, write timeouts, `BURST_DONE − BURST_START`,
    death time after `BURST_START`, and the outcome class (below).
- `queue.sh` runs a list of arms in order, stopping on a `STOP` file or a failed preflight; launch with
  `( setsid nohup bash queue.sh qN.txt < /dev/null > qN.log 2>&1 & )`. `sudo loginctl enable-linger jason92` before
  the first arm, `disable-linger` at the end.

Compile on the node:
`J=/mydata/s4/cassandra-base/build/lib/jars; javac -cp "$J/*" -d /mydata/b9/cls B9Load.java B9Sample.java`.

**Outcome classes** (from the first OOM line in `system.log`, the "JVM Arguments" line excluded):

| Class | Rule | Meaning here |
|---|---|---|
| `NETTY-REQ` | first OOM is `io.netty.util.internal.OutOfDirectMemoryError` on an event-loop thread with `ByteToMessageDecoder` (`cumulate`) in its stack | **the claimed endpoint** |
| `NETTY-OTHER` | `OutOfDirectMemoryError` elsewhere (e.g. response encode on a request worker) | counts as the claimed endpoint only if K at the last sample ≥ 0.8 × U_fail × 15/16 (request frames are ≥ 80 % of the counter); reported separately |
| `JDK-DIRECT` | `OutOfMemoryError: Direct buffer memory` first | U1 domain, competing |
| `HEAP` | `Java heap space` / `GC overhead limit exceeded` first (the forced heap OOM that follows a Netty error is logged after "Force heap space OutOfMemoryError in the presence of" and does not count) | H/S2 domain, competing |
| `KILL` | `oom_kill` > 0 in the scope's `memory.events` or a kernel OOM record | competing |
| `NONE` | alive at the end | no endpoint |

**Arms and order.** W writers × P = 8 connections; Q = in-flight per writer; C = W·P connections carrying the
burst; S = 15 MiB. Arms run from a clean regenerated node, one at a time.

| Step | Arm | Heap | Direct | W × P | Q (k per conn) | Burst | Purpose |
|---|---|---|---|---|---|---|---|
| 0 | `shake` | 4096 | auto | 1 × 8 | 8 (1) | 8 | harness shakedown, 20-s window — **not a reading** |
| 1 | `cal128` | 4096 | auto (15,872) | 16 × 8 = 128 | 8 (1) | 128 | calibration of N_held, ΔU_peak and decode rate at the test shape |
| 1 | `cal64` | 4096 | auto | 8 × 8 = 64 | 8 (1) | 64 | calibration of the control shape |
| 1 | `calI8` | 4096 | auto | 1 × 8 = 8 | 128 (16) | 128 | calibration of the intervention shape (matched burst) |
| 2 | — | | | | | | **choose D\*** (rule below) |
| 3 | `T_r1..r3` | 4096 | D\* | 16 × 8 | 8 (1) | 128 | test, ×3 |
| 3 | `Ctl_r1..r3` | 4096 | D\* | per rule (64, 32 or 16 conns) | 8 (1) | = C | matched low-multiplicity control, ×3 |
| 3 | `Int_r1..r3` | 4096 | D\* | 1 × 8 | 128 (16) | 128 | intervention: same burst over 8 connections, ×3 |
| 6 | `B_up1`, `B_up2` | 8192 | next ladder values above D\* | 24 × 8 = 192 | 8 (1) | 192 | upward boundary search (largest failing budget) |

Run step 3 interleaved: T_r1, Ctl_r1, Int_r1, T_r2, Ctl_r2, Int_r2, T_r3, Ctl_r3, Int_r3. `dump=1` only for
**T_r1** (first test arm; heap 4 GiB, dump ≈ live heap ≤ 4 GiB); every other arm `dump=0`.

**Rules fixed now (no other changes after readings):**

1. **D\*** = the largest value of the ladder {2048, 1792, 1536, 1280, 1024, 896, 768, 640, 512} MiB that is
   ≤ 0.85 × ΔU_peak(`cal128`). (ΔU excludes Netty's idle use, so this is conservative.) If 0.85 × ΔU_peak < 512:
   run `T` once at 512; if it survives, stop the V arms (endpoint not reachable at an acceptable budget on this
   platform at C = 128) and go to the conclusion.
2. **Control size:** 64 connections if ΔU_peak(`cal64`) ≤ 0.7 × D\*; else 32 (W = 4) if ΔU_peak(`cal64`)/2 ≤ 0.7 × D\*;
   else 16 (W = 2).
3. **Intervention** runs as `calI8` at D\* whatever its calibration; if ΔU_peak(`calI8`) > 0.7 × D\*, state before
   step 3 that the 30 % margin is not met (V4 may fail on margin) and run it anyway.
4. **Step-down once:** if `T_r1` ends `NONE` with ΔU_peak < D\*, lower D\* by one ladder step, record the
   amendment with its time, and restart step 3 at the new D\* (controls and intervention at the same D\*). At most once.
5. **Upward search (step 6):** run only if `cal128` was multiplicity-limited (N_held peak ≥ 0.9 × 128). Run
   `B_up1` at the next ladder value above D\* (above 2048: 2560, 3072, 4096) with heap 8192 and 192 connections; if
   it fails, `B_up2` one step higher; stop at the first survivor. Heap 8 GiB keeps the 192-request burst
   (2.8 GiB of heap copies) off the heap limit; these arms report the largest failing budget with its n/N, not V1–V4.
6. A competing endpoint (`JDK-DIRECT`, `HEAP`, `KILL`) is recorded as such; it is not the claimed endpoint and
   the arm is **not** re-run.

### 2.6 Instruments

- **U (domain N), independent of K:** NMT `Other` (Netty's no-cleaner chunks are `Unsafe.allocateMemory`,
  tracked as `mtOther` in JDK 11, as are JDK direct buffers) minus the JDK direct MXBean, every 2 s; ΔRssAnon every
  1 s as a cross-check; **U_fail** from the Netty error message (`used: X, max: Y`); the heap histogram that
  Cassandra logs at the first OOM (`io.netty.buffer.PoolChunk`, `org.apache.cassandra.transport.Envelope`, `[B`
  counts and bytes); for `T_r1` the heap dump analysed with U1's
  [`hprof_direct.py`](../candidates/concurrent_writes+max_mutation_size--inflight-DOB-fill/harness/hprof_direct.py)
  (`DIRECT_MEMORY_COUNTER`, no-cleaner buffer totals).
- **K:** `Client.RequestsSize` every 500 ms; C = L + S from the resolved heap.
- **Multiplicity:** `ConnectedNativeClients`, `PausedConnections`, `ConnectionPaused`, the client's per-writer
  open connections before the burst.
- **Load reached:** client `BURST_START`/`BURST_DONE`, sent/ok/errors, `RequestDispatched`, NTR active/pending,
  write timeouts, `TimedOutBeforeProcessing`.
- **Competing domains:** heap used and GC log (H, M), JDK direct (J), `memory.events`.
- Sampling 500 ms (JMX), 2 s (NMT), 1 s (RSS/cgroup): shorter than the ≈ 2-s frame hold window. NMT summary and
  the OOM histogram flag are identical in every arm; the histogram acts only after the first OOM.

### 2.7 Predicted response, stopping budget and time plan

**Predictions (before readings).**

| Arm | Endpoint | Key readings |
|---|---|---|
| `cal128` | `NONE` (budget 15,872) | K_peak > C: N ≥ 50 frames (K ≥ 750 MiB ≈ 1.8 × C); ΔU_peak ≈ 16 MiB × N_held, between 0.8 and 2.2 GiB depending on the decode rate (N_held = 128 if ≥ 64 frames/s); `PausedConnections` > 0 |
| `cal64` | `NONE` | N_held ≤ 64, ΔU_peak ≤ 1.1 GiB |
| `calI8` | `NONE` | N_held ≈ L/S + 8 ≈ 36 (K_peak ≤ L + 10·S ≈ 560 MiB); ΔU_peak ≈ 0.6 GiB; 8 paused connections most of the burst |
| `T` at D\* | **`NETTY-REQ` 3/3**, within 20 s of `BURST_START` (before `BURST_DONE`) | U_fail ≥ D\* − 16 MiB; K at the last sample ≥ 0.8 × D\* × 15/16 > C (bypass: U > C, K > C); histogram `Envelope` count ≈ K/S; heap < 4 GiB at failure |
| `Ctl` at D\* | `NONE` 3/3 | ΔU_peak ≤ 0.7 × D\* |
| `Int` at D\* | `NONE` 3/3 | K_peak ≤ L + 10·S; ΔU_peak ≈ ΔU(`calI8`); same 128 requests delivered (ok + timed-out responses), throughput (requests completed by `BURST_DONE`) within 25 % of the control's per-request rate |
| `B_up*` | `NETTY-REQ` while D < ≈ 16 MiB × N_held(192) | the first survivor marks the boundary |

**Stopping budget.** At most 19 arms (1 shakedown + 3 calibration + 9 V + 3 for one step-down + 2 upward + 1
spare); load window 45 s per arm plus 15 s observation; a node that is not listening 180 s after start is a failed
start (one retry, then stop). **No arm starts after 01:50 EST on 2026-11-18**; every process this case started is
stopped by 02:10; the case file is filled by 02:30. No escalation after an OOM beyond the rules above.

**Time plan** (stage 2 assumed to start ≈ 23:30 EST on 2026-11-17; ≈ 3.5–4 min per arm: start ≈ 60 s, schema +
connect ≈ 30 s, 10 s idle, 45 s load, 15 s idle, stop/wipe ≈ 20 s; a dying arm is shorter, plus ≈ 1–2 min for the
one dump):

| Window (EST) | Work |
|---|---|
| 23:30–23:40 | read the case, check the freeze hash, check ms0617 (idle, disk, RAM), copy the source |
| 23:40–23:50 | `ant jar` on ms0617 (background) while writing/adapting the harness |
| 23:50–00:05 | compile, shakedown arm, fix harness only |
| 00:05–00:20 | calibration arms (3) and the D\* decision (write it in §3 before step 3) |
| 00:20–01:00 | V arms (9, interleaved) |
| 01:00–01:15 | upward boundary arms (0–2) or the step-down repeats |
| 01:15–01:35 | dump analysis (`hprof_direct.py` on T_r1's dump, pinned to cores 6–7 once no arm runs), self-check from raw files |
| 01:35–02:30 | fill §3–§4, write-backs; stop everything, disable linger, report what is left |

Total stage-2 wall time ≈ 3 h, ending before 02:30 EST on 2026-11-18. Resources per arm: Cassandra ≤ heap 4 (8) GiB
+ Netty ≤ D + JDK direct ≤ 1.5 GiB + ≈ 0.5 GiB other; client ≤ 6 GiB heap + ≤ 3 GiB direct; total ≤ 20 GiB of
62.7 GiB. Disk per arm ≤ 8 GiB commit log (default cap min(8 GiB, ¼ volume)) + small LZ4 sstables (zero blobs,
16 keys), wiped per arm; one dump ≤ 4 GiB; build ≈ 1 GiB; total well under 37 GiB.

### 2.8 Controls and intervention

- **Matched control (V2), low multiplicity:** same build, heap, D\*, blob size, keys, burst-then-sustain workload
  and instruments; only the number of connections carrying the burst is smaller (64, 32 or 16 by rule 2). It shows
  that the same frames at a multiplicity whose N_held × 16 MiB stays below D\* do not reach the endpoint
  (component safe alone, ≥ 30 % margin by construction).
- **Causal intervention (V4), bound the multiplicity at matched load:** the **same 128-request burst** (same bytes,
  same writers' total in flight) carried by **8 connections** (16 requests each). The in-flight limit then works
  as designed: each connection is paused after its crossing frame, so N_held ≈ L/S + 8, and the endpoint should
  disappear without losing delivered work (all 128 requests still reach the server; throughput is disk-bound).
  This is the client-side form of `native_transport_max_concurrent_connections` (a server-side connection limit
  would refuse connections, and the driver's handling of refused pools would change the delivered load; not run).
- **Repetitions:** 3 clean-start runs each of T, Ctl and Int at the one fixed condition (heap 4,096 MiB, direct
  D\*), interleaved; report n/N and the peak distributions.
- **Attribution for V5:** first error with its thread and stack (`first-oom.txt`), the OOM-time histogram
  (`PoolChunk`, `Envelope`, `[B`), U_fail vs K, and the T_r1 dump (`DIRECT_MEMORY_COUNTER` and holders).

`sha256 of §1–§2 at freeze: 1d9e8695447058d9e718d7b8c0dda490cd9ac57804ac4ef42a2b0183151d0bec` (sha256 of the bytes from the line `## 1. Candidate` up to, not including, this line) · amendments after the freeze: none.

## 3. Runs (stage 2)

*Stage 2 by a fresh OOM-agent session (Claude Opus 5.5, workflow subagent), 2026-11-17 23:02 EST onward.*
Freeze hash checked at 23:03 EST: the bytes from `## 1. Candidate` up to the hash line hash to
`1d9e8695…151d0bec`, equal to the recorded value.

### 3.0 D\* decision (written 23:22 EST, after calibration, before step 3)

Calibration readings (auto direct, resolved 15,872 MiB): ΔU_peak(`cal128`) = 1,775 MiB, ΔU_peak(`cal64`) =
1,420 MiB, ΔU_peak(`calI8`) = 707 MiB.

- Rule 1: 0.85 × 1,775 = 1,509 MiB → **D\* = 1,280 MiB** (1,536 > 1,509).
- Rule 2: 1,420 > 0.7 × 1,280 = 896; 1,420 / 2 = 710 ≤ 896 → **control = 32 connections (W = 4 × P = 8, Q = 8)**.
- Rule 3: 707 ≤ 896 → the intervention's 30 % margin is met.
- Rule 5: N_held(`cal128`) peak = 111 (ΔU/16 MiB) or 49 (K/S), both < 0.9 × 128 = 115 → **no upward search**.

Step-3 queue (interleaved): T_r1 (dump=1), Ctl_r1, Int_r1, T_r2, Ctl_r2, Int_r2, T_r3, Ctl_r3, Int_r3, all heap
4,096 MiB, direct 1,280 MiB.

### 3.1 Interruption and resumption (note dated 2026-11-18 02:54 EST)

The first stage-2 session ran every arm of the frozen design (shakedown, 3 calibration arms, 9 V arms) between
23:09 and 23:47 EST on 2026-11-17, analysed `T_r1`'s heap dump at 23:48 EST, and was then cut off by an API usage
limit (not by the design) before it wrote §3 and §4. A fresh stage-2 session resumed at **02:54 EST on
2026-11-18**. It re-checked the freeze hash (`1d9e8695…151d0bec`, unchanged), found ms0617 idle (no Java process,
no user scope or service of this case; `Linger=yes` from the first session), and checked every arm on the node for
complete logs: each arm folder has `samples.csv`, `nmt.csv`, `cg.csv`, `load.log` with its `FINAL` line,
`V-logs/{system,debug,gc,launch}.log`, `V-flags.txt`, `V-yaml.diff`, `outcome.txt`, `readings.json` and
`stop.log`, and the queue logs `q0.log`–`q2.log` end with `QUEUE DONE`. The harness on the node
(`/mydata/s4/b9-w1/h/`) is byte-identical (md5) to this folder's `harness/`.

**Reused:** the build (`/mydata/s4/cassandra-base`, [`logs/build-identity.txt`](logs/build-identity.txt)), the
compiled harness (`/mydata/s4/b9-w1/cls`), all 13 arms and their raw logs, and the `T_r1` dump analysis
(`runs/T_r1/hprof_direct.txt`). **Redone:** nothing. No arm was incomplete, so no arm was re-run and no new
readings were taken; the resumed session only re-read the raw files, re-derived the numbers below from them
(including two that `b9peaks.py` did not produce, see 3.6), copied excerpts into `logs/`, and wrote §3–§4.

### 3.2 Environment and configuration (as run)

| Item | Value |
|---|---|
| Node | ms0617 (node4.jason92-326377, Utah m400), **aarch64**, 8 cores, 62.7 GiB RAM, kernel 5.15.0-191-generic, cgroup v2; client and server colocated over loopback |
| JDK / GC | OpenJDK 11.0.33, G1 |
| Build | `cassandra-5.0.9` (tag), `apache-cassandra-5.0.9-SNAPSHOT.jar` md5 `1becab414e5f4a4ce6ad3d25c63bf1ab`, `ant jar` BUILD SUCCESSFUL in 4 min 57 s, unpatched; driver 3.12.1 shaded, Netty epoll 4.1.130 aarch_64 |
| Work dir | `/mydata/s4/b9-w1/` (node `node/`, harness `h/`, classes `cls/`, arms `runs/<arm>/`), not `/mydata/b9` (environment only) |
| yaml diff | environment keys only (cluster name `b9`, 127.0.0.81 addresses and seed, directories under the work dir); [`runs/*/V-yaml.diff`] identical in all arms; **no capacity setting changed in any arm** |
| Heap | `-Xms4096M -Xmx4096M` (MaxHeapSize 4,294,967,296) in every arm |
| `MaxDirectMemorySize` (resolved, `VM.flags`) | calibration: auto → **16,642,998,272 B = 15,872 MiB**; V arms: **1,342,177,280 B = 1,280 MiB** via `MAX_DIRECT_MEMORY_SIZE` |
| Netty | `io.netty.allocator.maxOrder=11`, `useCacheForAllThreads=true` (shipped options); `io.netty.maxDirectMemory` unset, so Netty's counter limit = `MaxDirectMemorySize` (confirmed by the error text `max: 1342177280` and by the dump's `DIRECT_MEMORY_LIMIT`) |
| Resolved in-flight limits at 4 GiB | L = 409.6 MiB global, 102.4 MiB per IP; contract C = L + S = 424.6 MiB (Netty equivalent ≈ 448 MiB) |
| Process scope | `systemd-run --user --scope -p MemoryMax=48G -p MemorySwapMax=0` (non-binding safety net); Cassandra `taskset -c 0-5`, client / samplers on 6–7 |
| Instruments | JMX every 500 ms; NMT summary via `jcmd` (nominally 2 s, **actually every 3–4 s** on the m400, see 3.6); RssAnon / `memory.current` / `oom_kill` every 1 s |
| Clocks | queue logs in EST, node shell in MST, Cassandra logs in UTC, samples in epoch ms (one host clock) |

### 3.3 Calibration (heap 4,096 MiB, direct auto = 15,872 MiB)

Full lines: [`logs/summary.txt`](logs/summary.txt). ΔU = NMT Other − JDK direct − X0 (X0 = 208 MiB, idle).

| Arm | Conns × k | Outcome | Burst done | K_peak (frames) | Paused peak | ΔU_peak | JDK direct peak | Client ok / timeouts |
|---|---|---|---|---|---|---|---|---|
| `shake` | 8 × 1 | NONE | 0.8 s | 30 MiB (2) | 0 | 61 MiB | 117 MiB | 129 / 0 (20-s window, not a reading) |
| `cal128` | 128 × 1 | NONE | 12.0 s | 735 MiB (49) | 49 | **1,775 MiB** (at +3.0 s) | 1,047 MiB | 130 / 274 |
| `cal64` | 64 × 1 | NONE | 4.3 s | 495 MiB (33) | 27 | 1,420 MiB | 1,002 MiB | 162 / 176 |
| `calI8` | 8 × 16 | NONE | 15.4 s | 210 MiB (14) | 8 | 707 MiB | 808 MiB | 225 / 170 |

The D\* decision (3.0, written before step 3) follows from these: D\* = 1,280 MiB, control 32 connections,
intervention margin met, no upward search (rule 5: N_held(`cal128`) 111 by ΔU or 49 by K, both < 115).

### 3.4 V arms (heap 4,096 MiB, direct 1,280 MiB; interleaved T, Ctl, Int × 3; 23:21–23:47 EST)

**Test `T` (128 connections × 1 request, 128-request burst of 15 MiB writes).** All three died of the claimed
endpoint. Per arm (raw: `/mydata/s4/b9-w1/runs/T_r{1,2,3}/`; excerpts
[`logs/T_r1-first-oom.txt`](logs/T_r1-first-oom.txt), [`T_r2`](logs/T_r2-first-oom.txt),
[`T_r3`](logs/T_r3-first-oom.txt), [`logs/T-oom-histograms.txt`](logs/T-oom-histograms.txt),
[`logs/T-samples-around-failure.txt`](logs/T-samples-around-failure.txt)):

| | T_r1 (dump=1) | T_r2 | T_r3 |
|---|---|---|---|
| First OOM (system.log) | `ERROR [epollEventLoopGroup-5-4] 04:23:31,016 UTC` | `[epollEventLoopGroup-5-7] 04:32:14,277` | `[epollEventLoopGroup-5-5] 04:40:54,995` |
| Error | `io.netty.util.internal.OutOfDirectMemoryError: failed to allocate 16777216 byte(s) of direct memory (used: 1342177280, max: 1342177280)` in all three | same | same |
| Stack | `PoolArena.newChunk` ← `PoolArena.reallocate` ← `AbstractByteBuf.ensureWritable` ← `ByteToMessageDecoder$1.cumulate` ← `ByteToMessageDecoder.channelRead` ← `EpollStreamUnsafe.epollInReady` | same | same |
| Time after `BURST_START` | **+2.40 s** | **+2.35 s** | **+2.26 s** |
| Netty OOM errors logged | 31 | 49 | 31 |
| **U_fail** (Netty counter at failure) | **1,280 MiB** | **1,280 MiB** | **1,280 MiB** |
| NMT Other just before failure (+1.9 s) | 1,358 MiB (ΔU 1,033) | 1,855 MiB (ΔU 1,500) | 1,802 MiB (ΔU 1,552) |
| **K** at the last sample before failure | **165 MiB (11 frames)** at +2.22 s | **75 MiB (5)** at +1.89 s | **180 MiB (12)** at +2.25 s |
| `ConnectionPaused` count / `PausedConnections` at that sample | **0 / 0** | **0 / 0** | **0 / 0** |
| JDK direct at that sample | 312 MiB | 147 MiB | 357 MiB |
| Heap used at that sample | 961 MiB | 816 MiB | 945 MiB |
| OOM-time histogram (HeapUtils, ms after first error) | +66 ms: `PoolChunk` 34, `Envelope` 18, `Envelope$Decoder` 127, `ExecuteMessage` 8, `[B` 664.5 MiB | +27 ms: 44, 21, 108, 17, 648.5 MiB | +114 ms: 57, 24, 121, 18, 768.5 MiB |
| Forced heap OOM (`JVMStabilityInspector`, then `kill -9`) | +7.5 s | +6.6 s | +6.4 s |
| K_peak / paused peak (whole arm, includes the dying seconds) | 390 MiB / 5 | 675 MiB / 31 | 405 MiB / 15 |
| Kernel / cgroup OOM kill | 0 | 0 | 0 |
| Client | ok 111, `NoHostAvailable` 205, `Transport` 90 | ok 90, 233, 83 | ok 90, 231, 85 |

`T_r1` heap dump (`runs/T_r1/cassandra-1794975704-pid102884.hprof`, 933 MiB, written at the forced heap OOM,
≈ 5 s after the first Netty error; [`logs/T_r1-hprof_direct.txt`](logs/T_r1-hprof_direct.txt)): Netty
`DIRECT_MEMORY_COUNTER` = 512 MiB with `DIRECT_MEMORY_LIMIT` = `MAX_DIRECT_MEMORY` = 1,342,177,280; 167
no-cleaner `DirectByteBuffer`s ≤ 954.5 MiB; JDK owner buffers 267 MiB (`DataOutputBuffer` scratch 195 MiB, hints
32 MiB). The counter had already fallen from 1,280 to 512 MiB because the 31 failing channels were closed and their
cumulations released before the dump, so the dump confirms the counter and its limit but is not the at-failure
holder picture; the at-failure picture is U_fail plus the histogram taken 27–114 ms after the first error.

**Matched control `Ctl` (32 connections × 1 request, 32-request burst).** 0/3 endpoints.

| | Ctl_r1 | Ctl_r2 | Ctl_r3 |
|---|---|---|---|
| Outcome | NONE (alive, no ERROR in system.log) | NONE | NONE |
| Burst done | 2.5 s, 32/32 ok | 2.6 s, 32/32 ok | 2.7 s, 32/32 ok |
| K_peak (frames) / paused peak | 315 MiB (21) / 2 | 435 MiB (29) / 6 | 285 MiB (19) / 1 |
| ΔU_peak (NMT) | 61 MiB | 62 MiB | 78 MiB |
| JDK direct peak / ΔRssAnon peak | 597 / 981 MiB | 612 / 1,258 MiB | 582 / 1,178 MiB |
| Client (45-s window) | ok 306, 0 errors | ok 305, 0 errors | ok 305, 0 errors |

The NMT ΔU of the control missed its 2.5-s burst (NMT every 3–4 s; see 3.6), so the control's Netty peak is bounded
by arithmetic instead: the client never has more than W·Q = 32 requests outstanding, so at most 32 frames are
buffered (≤ 32 × 16 MiB = 512 MiB) plus at most one reallocation transient per event loop (≤ 12 × 12 MiB =
144 MiB): **≤ 656 MiB < 0.7 × 1,280 = 896 MiB**, the 30 % margin. `cal64` (64 connections, 15.9 GiB budget) is
the measured upper reference: ΔU_peak 1,420 MiB for twice the connections.

**Intervention `Int` (the same 128-request burst over 8 connections × 16).** 0/3 endpoints.

| | Int_r1 | Int_r2 | Int_r3 |
|---|---|---|---|
| Outcome | NONE (alive, no ERROR) | NONE | NONE |
| Burst done | 19.2 s, 128/128 | 15.1 s, 128/128 | 18.0 s, 128/128 |
| K_peak (frames) / paused peak / pause events | 210 MiB (14) / 8 / 283 | 210 MiB (14) / 8 / 281 | 210 MiB (14) / 8 / 287 |
| ΔU_peak (NMT, burst covered by 4–5 samples) | 707 MiB | 658 MiB | 400 MiB (all ≤ 0.55 × D\*) |
| JDK direct peak | 792 MiB | 852 MiB | 552 MiB |
| Client (≈ 56-s window) | ok 226, write timeouts 170 | ok 216, 180 | ok 207, 188 |

Load reached and throughput ([`logs/load-excerpts.txt`](logs/load-excerpts.txt)): the intervention delivered the
same 128 burst requests (128/128 completed, ok or write timeout) and kept 128 requests outstanding through the
sustain phase. Its ok writes (207–226, 3.5–3.9/s) exceed those of the same 128-request load over 128 connections
at the 15.9 GiB budget (`cal128`: ok 130, 2.6/s, 274 timeouts; burst done 12.0 s), so bounding the connections did
not cost useful work. The design's stated throughput check (burst completion rate within 25 % of the control's)
is **not met as worded**: 128 requests in 15.1–19.2 s (6.7–8.5/s) against the control's 32 in 2.5–2.7 s
(12–13/s); the control carries a quarter of the outstanding bytes, so its per-request rate is not a matched
reference, and `cal128` is the matched-load one. The write timeouts in `Int` (and `cal128`) come from 128
outstanding 15 MiB writes on one SATA-SSD node with 2-s `write_request_timeout`; the control (32 outstanding) had
none.

### 3.5 Classification by measurement (domain N)

- **C** = L + S = 424.6 MiB (Netty ≈ 448 MiB); **U** = 1,280 MiB at failure (Netty's own counter, independent of
  K) = **3.0 × C**; **K** at the last sample before failure 75–180 MiB, **below L**, with zero connection pauses.
- So the row is **U > C, K ≤ C → bypass, accounting omission**: the bytes are request frames that the in-flight
  control is meant to cover, but they are held in Netty cumulation buffers **before** `checkLimits` charges them,
  and with 128 connections reading frames at once ≈ 80 chunks (128 cumulations, growing by reallocation copies)
  fill Netty's counter while only 5–12 frames have been decoded and charged.
- The design's predicted sub-mechanism (force-admitted frames after a failed reservation, K > C) **did not
  occur before the endpoint**: `ConnectionPaused` was 0 at failure in 3/3 arms. K passed C only afterwards in
  T_r2 (675 MiB while the JVM was dying) and in the surviving calibration arm `cal128` (735 MiB, 49 paused). The
  force-admit overshoot is real at a large budget but is not what exhausts the counter at 1,280 MiB.
- The intervention isolates the factor: with 8 connections only 8 frames can be in reading at once, the limit
  pauses all 8 after their crossing frames (K_peak 210 MiB < L), and the endpoint disappears 3/3.

### 3.6 Deviations from the frozen design

1. **Work directory** `/mydata/s4/b9-w1/` instead of `/mydata/b9/` (environment; same disk).
2. **NMT cadence** ≈ 3–4 s, not 2 s (`jcmd` per sample is slow on the m400). Consequences: in `T` only one NMT
   sample falls between `BURST_START` and the failure; in `Ctl` no sample caught the 2.5-s burst (ΔU 61–78 MiB is
   an under-reading, bounded by arithmetic in 3.4). U for the claimed endpoint rests on U_fail (Netty's counter in
   the error text), not on NMT.
3. **`b9peaks.py` reported `first_oom_thread=None`** (parser miss); the thread and stack were read directly from
   `first-oom.txt` (above). The classifier's `NETTY-REQ` class matches the raw stacks in 3/3.
4. **K at failure** was read by the resumed session from `samples.csv` (last sample before the first error's
   timestamp); `b9peaks.py`'s `K_last` (−0) is the last sample of the dead JVM and is not used.
5. **Interruption** (3.1): stage 2 stopped after the runs and the dump analysis (23:48 EST) and resumed at 02:54
   EST without new arms. All arms ran inside the design's window (before the 01:50 EST cutoff).
6. **Upward boundary search** not run: rule 5's condition was not met (3.0). No other arm was added.

No capacity setting was changed in any arm; no patch, Byteman or injected delay was used.

### 3.7 Left on the node and cleanup

No process of this case runs on ms0617 (checked 02:58 EST: only the user's `systemd --user` manager; no Java,
no scope). Left on disk (`/mydata`, 36 GiB free): `/mydata/s4/cassandra-base` (build, 469 MiB),
`/mydata/s4/build-b9.log`, `/mydata/s4/b9-w1/` (963 MiB: harness, classes, node config/logs, `runs/` with all
13 arms' raw logs and the 933 MiB `T_r1` hprof). `Linger=yes` for `jason92` (enabled by the first session) is
**still on**: the resumed session's `loginctl disable-linger` was refused by the session's permission check, so it
must be turned off by hand (`sudo loginctl disable-linger jason92` on ms0617). `/mydata/s2r2` and `/mydata/u1r2`
(other cases) were not touched.

## 4. Conclusion (stage 2)

**Verdict: `true positive`.** Protocol status: **`verified-OOM · deployment`** (bypass, accounting omission,
under unlimited connection multiplicity), endpoint a Netty direct-memory OOM (`OutOfDirectMemoryError` on the
request-decode path), followed by Cassandra's forced heap OOM and `kill -9` of the JVM.

**Reason.** At shipped defaults (in-flight limit L = heap/10 = 409.6 MiB, connections unlimited, frame size
16 MiB) and a 4 GiB heap with a 1,280 MiB direct budget, a burst of 128 v4 EXECUTEs of 15 MiB over 128
connections killed Cassandra in **3/3** runs, 2.26–2.40 s after the burst started, with
`OutOfDirectMemoryError … (used: 1342177280, max: 1342177280)` on an epoll event loop in
`ByteToMessageDecoder.cumulate` → `PoolArena.reallocate` → `newChunk`. Netty held **U = 1,280 MiB = 3.0 × the
contract C = 424.6 MiB** while the control's own counter K stood at **75–180 MiB (5–12 frames, below L)** and
**no connection had been paused**: the request frames sit in pooled direct cumulation buffers before
`LegacyDispatchHandler.checkLimits` sees them, so the limit cannot stop memory it has not yet been asked about,
and nothing bounds how many connections read a frame at once. The matched control (the same frames over 32
connections, ≤ 656 MiB by construction) survived **0/3** with all writes ok, and the intervention (the same
128-request burst over 8 connections, so the limit's pause works) reached the endpoint in **0/3** runs with K_peak 210 MiB,
ΔU ≤ 707 MiB and more useful writes than the same load over 128 connections at a 15.9 GiB budget.

**V1–V7.**

| | Evidence | Met |
|---|---|---|
| V1 Repetition | T_r1–r3: `NETTY-REQ` 3/3 from clean regenerated nodes | yes |
| V2 Matched control | Ctl_r1–r3 (32 connections, same build, heap, D\*, frames, instruments): NONE 3/3 | yes (peak bounded by arithmetic, not NMT; 3.4) |
| V3 Measurement | U_fail from Netty's own counter (1,280 MiB) and NMT Other (1,358–1,855 MiB just before failure) vs K (`RequestsSize`, 75–180 MiB) | yes |
| V4 Intervention | Int_r1–r3 (8 connections, matched 128-request burst): NONE 3/3, 128/128 delivered, ok 207–226 | yes (throughput check as worded not met; matched-load comparison with `cal128` given in 3.4) |
| V5 Initiating failure | first error, thread and stack in 3/3 (`logs/T_r*-first-oom.txt`); OOM-time histograms 27–114 ms after it (`PoolChunk` 34–57, `Envelope` 18–24, `Envelope$Decoder` 108–127); `T_r1` dump (counter and limit) | yes |
| V6 Default constraints | every capacity setting at its shipped default, resolved at 4 GiB (L 409.6 MiB, per-IP 102.4 MiB, connections −1, frame 16 MiB, 128 NTR threads) | yes |
| V7 Acceptable budget | heap 4,096 MiB, direct 1,280 MiB (≥ 512 MiB standing rule); the 15,872 MiB auto budget survived (`cal128`, 1 run) | yes |

**Largest failing budget.** 1,280 MiB fails 3/3; 15,872 MiB (auto for this 62.7 GiB node) survived the same
burst once with ΔU_peak 1,775 MiB. The design's upward search was not triggered (rule 5), so the boundary between
1,280 MiB and ≈ 2 GiB, in particular the ideal 2,048 MiB (what `cassandra-env.sh` resolves on an 8 GiB node), is
**untested**. More connections should move the boundary up roughly 16 MiB per concurrently reading connection
(≈ 128 connections reached ≈ 1.8–2 GiB of Netty memory here), but that is a prediction, not a reading.

**Interpretation.** A suspected implementation / design gap rather than an intentional exception: the code
comment's documented overshoot is "one request per connection after the limit" (`PreV5Handlers.java:84-85`), but
the memory that fails is taken **before** any request is counted. Clue patterns: **CP-11** (enforcement after the
allocation: frames are buffered, then checked) combined with **CP-7** (a per-connection natural size, one frame
of ≤ 16 MiB, × unlimited connections). The phase-1 row's CP-6 (force-admit) is real at large budgets (`cal128`:
K 735 MiB, 49 paused) but did not drive these failures.

**Limits of attribution.** Platform aarch64 m400 only, client colocated on loopback. The control's Netty peak is
an arithmetic bound (NMT too slow for a 2.5-s burst). The dump was taken 5 s after the first error, after
channel closures had freed part of the counter, so it does not show the at-failure holders; the histogram and
U_fail do. Whether a real client population opens 128 connections and sends 15 MiB writes simultaneously is a
workload question: each request is within `native_transport_max_frame_size` and `max_mutation_size`, and the
connection count is unlimited by default.
