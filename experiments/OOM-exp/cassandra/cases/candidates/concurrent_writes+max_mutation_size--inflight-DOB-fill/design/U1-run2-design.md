# U1 run 2 design — large mutations delivered to a replica over internode messaging (Utah m400, aarch64)

**Written 2026-11-17 12:50 EST, before any reading of run 2** (the only earlier step on the nodes was copying the
build, a 1 GiB `dd` of the victim's disk and reading `free -m`). Campaign row U1 (U = unprotected-accumulation lead:
memory with no applicable control). Run 1 (2026-11-16/17, pc96, x86) is the
[run-1 case](../concurrent_writes+max_mutation_size--inflight-DOB-fill.md) with its
[design](U1-design.md); this run follows the **researcher's decision of 2026-11-17**: deliver the large mutations to
the victim as a **replica over internode messaging**, not as a coordinator, so that (i) no client request frame sits
on the victim's Netty counter (lead B9; B = bypass investigation), (ii) the native-protocol in-flight limits do not
throttle the victim's write threads, and (iii) enough coordinators can keep all 32 `MutationStage` threads inside
`CommitLog.add`. Related: S1 (S = stacked combo case) stage 3 was U1 with 8 loopback coordinators; C1 run 4
(C = convergence investigation) measured the internode receive queue. One agent, controller `pc96`.

**Time budget (stopping rule).** Design 12:50; shakedown ≤ 13:15; arms until ≈ 16:30 (no arm starts after 16:25);
analysis/dumps until ≈ 16:50; all processes stopped, linger disabled and verified by ≈ 17:00; filing by ≈ 17:20.
At most 32 arms. No escalation of workload after an OOM.

## 1. Platform and topology

| Role | Node | LAN IP | Heap | Notes |
|---|---|---|---|---|
| **V — victim**, the only replica | `ms0625` | 10.10.1.1 | **2 GiB** | dc `v`; seed; `initial_token` −2^63 |
| C1 — coordinator + its client | `ms0640` | 10.10.1.2 | 8 GiB | dc `c` |
| C2 | `ms0604` | 10.10.1.3 | 8 GiB | dc `c` |
| C3 | `ms0611` | 10.10.1.4 | 8 GiB | dc `c` |
| C4 | `ms0617` | 10.10.1.5 | 8 GiB | dc `c` |

All five: Utah m400, **aarch64** (8 cores), 62 GiB (`free -m` 64,249), 8 GiB swap on (0 inside the server scopes),
Ubuntu 22.04, kernel 5.15, cgroup v2, OpenJDK 11.0.33, G1, 10 GbE LAN (~0.1 ms). Storage: `/mydata` = LVM on the
node's **SATA SSD** (XR0120GEBLT, 120 GB); the victim's volume measured **113 MB/s** (`dd oflag=direct`, 16 MiB
blocks) and 96 MB/s (`conv=fdatasync`) — slower than run 1's HDD RAID (200 MB/s). Not comparable arm-by-arm with run
1 (x86); no x86 positive is needed (researcher). Build: the S2 run-2 aarch64 build of the pinned 5.0.9 source
(`ant jar`; `src/` identical to `systems/cassandra/source/src/` by md5 of every file; jar md5 `beb4d0c1…` on all
five nodes), copied read-only to `/mydata/u1r2/cassandra` on each node. Run data under `/mydata/u1r2/` of each node;
small files mirrored to `pc96:/mydata/u1r2/mirror/`.

**Keyspace** `u1r2` = `NetworkTopologyStrategy {v: 1}`: V alone holds RF 1, dc `c` holds RF 0, so V applies every
write and the coordinators none (S2 run 1's two-DC trick). Table `u1r2.t (pk int PRIMARY KEY, b blob)`.
`num_tokens: 1` with fixed `initial_token`s, `GossipingPropertyFileSnitch`, `auto_bootstrap: false` (environment).
**Clients:** one `U1R2Load` per used coordinator node, driver 3.12.1, protocol v4, whitelisted to its *local*
coordinator only, prepared `INSERT`, CL ONE, zero-filled blobs, keys mod 200 (overwrite), 2 connections ×
`INFL` outstanding requests, no rate cap unless stated, no retries. Each coordinator forwards every write as one
internode `MUTATION_REQ` to V (one remote replica: no forwarding). V receives **no client request frames**.

**Scopes.** V: `systemd-run --user --scope -p MemoryMax=40G -p MemorySwapMax=0` (non-binding safety scope; heap +
direct ≤ 18 GiB even at auto); coordinators: `MemorySwapMax=0`, no memory limit, `-XX:-HeapDumpOnOutOfMemoryError`.
Linger enabled on all five for the run, **disabled at the end**. `memory.current` of V's scope sampled at 1 s (no
`memory.peak` on 5.15); `oom_kill` from `memory.events` must stay 0.

## 2. Mechanism and source check (pinned 5.0.9)

| Step | Source | What it does on the replica |
|---|---|---|
| Receive admission | `InboundMessageHandler.processFirstFrameOfLargeMessage` (`:207–222`) → `AbstractMessageHandler.acquireCapacity` (`:411–440`) | a message > 4 MiB per-connection queue capacity borrows the excess from the **endpoint reserve (128 MiB)** and the **global reserve (512 MiB)**; on-wire bytes, acquired at the first frame. Per coordinator ≤ (4 + 128)/S ⇒ **8 messages of 15 MiB** in flight; globally ≤ (512 + 4N)/S ⇒ ≈ 34–36. |
| Frames | `LargeMessage` buffers (networking `BufferPool` / overflow `allocateDirect`, JDK `Bits`) | ≈ S direct per message from the first frame until `deserialize()` on the stage thread (`ProcessLargeMessage.provideMessage`, `:481–509`), then released. |
| Capacity release | `ProcessMessage.run` (`:410–446`) | `releaseProcessedCapacity` in `finally`, **after** the verb handler returns. |
| Verb | `MutationVerbHandler.doVerb` → `applyMutation` → `Mutation.applyFuture()` | expired messages are dropped before processing (`:47–52`, and `ProcessMessage.run`), otherwise applied **synchronously on the `MutationStage` thread**: `Keyspace.applyInternal` → `CommitLog.add`. Also `HINT_REQ` runs on `MUTATION` (`Verb.java:118`). |
| U1 holder | `CommitLog.add` (`CommitLog.java:304–339`) | `validateSize` (≤ `max_mutation_size` 16 MiB) → thread-local `DataOutputBuffer.scratchBuffer` (direct, `cassandra.dob.allocate_type` default `DIRECT`, `DataOutputBuffer.java:55,84–88`) grows to S + 128 B, then ×2 (`calculateNewSize`, `:158–172`; old buffer freed at once, transient S + 2S) and is held across `segmentManager.allocate`, the copy into the mmap'd segment and `executor.finishWriteFor` → `PeriodicCommitLogService.maybeWaitForSync` (blocks when the sync lags > 1.5 × 10 s). Trimmed only at `close()` (`DOB_MAX_RECYCLE_BYTES` 1 MiB). |
| Max message size | `DatabaseDescriptor.java:974–996` | `internode_max_message_size` defaults to min(receive, send endpoint reserve) = **128 MiB**: a 15 MiB or 16 MiB − 1 KiB mutation is admitted. |
| Multiplicity | `concurrent_writes` = 32 (`MutationStage`) | the only bound on simultaneous scratch holders; the receive queue bounds the number of messages being received + queued + processed (above), not their processing footprint. |

**Prediction sheet (JDK `Bits` counter, S = 15 MiB = 15,728,640 B):**
U = B0 (≈ 10–40 MiB: networking pool chunk, NIO, compaction/flush buffers; V coordinates nothing, so no hints
buffer is expected) + H_dob × 2S (+ up to H_dob × S transient) + H_frames × S, with H_dob + H_frames ≤ admitted
messages ≤ min(8N, ≈ 35) and H_dob ≤ 32. Ceiling at N = 4: 32 × 2S = **960 MiB** standing, 32 × 3S = **1,440 MiB**
transient, + B0. At **1,024 MiB** an OOM therefore needs ≈ all 32 writers holding 2S at once *plus* either a few
writers in the 3S transient or queued frames, held longer than `Bits.reserveMemory`'s retry window (≈ 0.5 s of
backoff after a forced GC). With **S16 = 16,776,192 B (16 MiB − 1 KiB)**, the largest value that fits under
`max_mutation_size` and the 16 MiB native frame, 32 × 2S16 = 1,024 MiB standing: by arithmetic, 32 standing holders
alone fill a 1,024 MiB limit.

Heap competes (reported, not the budget under test): each in-processing mutation is ≈ S on heap after
deserialization; memtable `heap_buffers` 512 MiB (¼ heap).

## 3. Protection map (fixed before readings)

| Domain | Allocation / release | Contract C | Multiplicity | Aggregate coverage | Lifetime |
|---|---|---|---|---|---|
| **U1 in-flight DOB** | `DataOutputBuffer$1$1.buffer` grown under `CommitLog.add`, freed at `close()` | **none in flight** (`max_mutation_size` bounds one mutation) | ≤ `concurrent_writes` 32 | none; not reconciled with `MaxDirectMemorySize` | serialize → segment → copy → sync wait |
| R receive frames (C1) | `LargeMessage` buffers, released at deserialize | Q 4 MiB/conn, E 128 MiB/peer, G 512 MiB, on-wire bytes, until the verb returns | N peers | K counts on-wire bytes of every admitted message (frames *and* processing) | first frame → deserialize |
| D kept DOB | same buffer after `close()` | 1 MiB/thread | threads that serialized | none | standing |
| P networking `BufferPool` | chunks for frames | 128 MiB retained | 1 | overflow unpooled | standing |
| B0 other | NIO, compaction read-ahead, flush writers | per-pool | — | — | — |
| Netty counter (separate limit = same value) | native transport: only the sampler's CQL session on V | native in-flight limits | 1 sampler | own counter | — (expected ≈ 0: B9 avoided) |
| Heap (reported) | deserialized mutations, memtable (512 MiB) | memtable | ≤ admitted | flush | — |

**Classification target:** **unprotected accumulation** (U1: no control covers the in-flight scratch; implicit bound
`concurrent_writes` × 2–3 × S). The receive queue's contract covers on-wire message bytes (K ≤ C expected), not the
copies made while processing, so a DOB excess with K ≤ C is not a bypass of it. Holder tags at failure (dump +
first stack): **U1** if the first `Direct buffer memory` error is thrown in `CommitLog.add` and the DOB scratch is
the largest live holder; **mixed** (researcher's usage for this run: the OOM needs both holders) if DOB alone stays
below the limit and the receive frames (R) supply the rest; **R-initiated** if the first error is in the receive path
(`LargeMessage`/`BufferPool` allocation on an event-loop thread).

## 4. Configuration and budget (V6, V7)

| Setting | Class | Value |
|---|---|---|
| `concurrent_writes`, `max_mutation_size`, `commitlog_segment_size`, commit-log sync (periodic 10 s, lag block 15 s), `DOB_MAX_RECYCLE_BYTES`, `cassandra.dob.allocate_type`, receive/send queue capacities, `internode_max_message_size`, memtable, timeouts, hints | **default** on every node (absent from yaml / no `-D`) | 32; 16 MiB; 32 MiB; —; 1 MiB; DIRECT; 4/128/512 MiB; 128 MiB; heap_buffers ¼ heap; write 2 s; hinted handoff on |
| yaml diff | environment | cluster name, addresses, seeds, snitch, data/commitlog/hints/saved_caches/cdc dirs, `num_tokens: 1`, `initial_token`, `auto_bootstrap: false`; kept per arm (`V-yaml.diff`) |
| V heap | budget | `MAX_HEAP_SIZE=2048M` (ideal) |
| V direct | budget (dial) | `MAX_DIRECT_MEMORY_SIZE` (the documented `cassandra-env.sh` override) = **1024M** first; **auto** (unset) once; then searched |
| coordinators | environment | 8 GiB heap, direct auto, `-XX:-HeapDumpOnOutOfMemoryError` |
| workload | experimental variable | see §5 |
| Byteman, patches | not used | — |

### V7 argument (written before readings; researcher reviews afterwards)

`conf/cassandra-env.sh` (pinned, `calculate_heap_sizes`, lines 58–68 and 139–141; checked today): with G1 the
`UseConcMarkSweepGC` grep fails so `USING_CMS` = 1 and `heap_limit` = 31,744 MiB; heap = min(½ RAM, 31,744) and
`MAX_DIRECT_MEMORY_SIZE` = **¼ RAM**, or `heap_limit / 2` = 15,872 MiB when ½ RAM > 31,744. The direct value does
**not** depend on `MAX_HEAP_SIZE`: an operator who sets only the heap still gets ¼ RAM. The result claims a node sized
by the script for **4 GiB of RAM**: heap ½ RAM = **2,048 MiB**, direct ¼ RAM = **1,024 MiB** (for `free -m` = 4,096; a
real 4 GiB VM reports a little less, e.g. 3,900 → heap 1,950 / direct 975 MiB, so 1,024 is the upper end of that
claim). Both are above the standing floor (512 MiB) and the heap is the standing ideal; no override is needed. On
the m400 itself (`free -m` 64,249, ½ = 32,124 > 31,744) the script resolves direct = **15,872 MiB** for the explicit
2 GiB heap (to be confirmed by `jcmd VM.flags` in the auto arm); that arm is infeasible for a direct OOM by the
ceiling sheet and serves as the unconstrained U_peak calibration. Budgets searched below 1,024 MiB stay ≥ 512 MiB
(V7 by the standing rule) but are reported as below the 4 GiB-node resolution (they need `MAX_DIRECT_MEMORY_SIZE` or
a node of ≈ 3–3.5 GiB). The largest failing budget is the reported boundary. *Researcher's review: pending.*

## 5. Arms, predictions, stopping

Each arm: all five instances regenerated (clean data, commit log, hints), V started, then C1–C4 in parallel,
5 UN, schema, V samplers, 5 s idle, **90 s load**, 20 s observation, collect, stop all. Samplers on V:
`U1R2Sample` 1 s (JMX: direct used/count = U, heap, `MutationStage` active/pending/completed, commit-log waits,
dropped `MUTATION_REQ`/`HINT_REQ`, memtable, networking pool; CQL `system_views.internode_inbound`: K = Σ
`using_bytes`), cgroup 1 s, and in diagnostic arms only `jcmd Thread.print` every 5 s (`jstk.py`: `MutationStage`
threads in `CommitLog.add` / `expandToFit` / segment wait / sync wait / memtable wait). Endpoint: `OutOfMemoryError:
Direct buffer memory` in V's `system.log` (then Cassandra forces a heap OOM and writes a dump, shipped
`-XX:+HeapDumpOnOutOfMemoryError`); dumps attributed with `hprof_direct.py` (C1/S1/U1 run 1) on a pc96 copy.
"Saturated" = `MutationStage` active = 32 in ≥ 50 % of the 1 s samples of the load window.

Workloads: **E15** = 15,728,640 B values, N coordinators × 1 client × 2 connections × `INFL` in flight (no rate cap);
**E16** = E15 with 16,776,192 B values; **G** (matched control) = 524,288 B values, same N, rate-capped per client
to the endpoint's measured offered bytes/s (sent/s × S), in-flight raised so the cap binds.

0. **Shakedown (not a reading):** 1 MiB values, N = 1, `INFL` 4, auto, 30 s: harness check only.
1. **Saturation sweep** at 1,024 MiB, E15, `JSTACK=1` in the first: N = 4 × `INFL` 12 (48 outstanding ≥ 32 + 16),
   then N = 2 × 12 and N = 1 × 12 (n = 1 each). Predict (receive-queue bound): active ≤ 8 at N = 1, ≤ 16 at N = 2,
   32 saturated at N = 4. If N = 4 is not saturated, raise `INFL` to 24.
2. **Auto** (unset, expect 15,872 MiB): E15 at the saturating shape ×1 → unconstrained U_peak. Predict 750–1,150 MiB
   (run 1 at auto: 752 with ≤ 21 active; here up to 32 holders), no direct OOM (infeasible), heap peak 1.8–2.0 GiB,
   heap OOM possible (P ≈ 20 %).
3. **Budget search** (E15, saturating shape): 1,024 (×3 total with step 1's arm); if it fails, step up 1,280 → 1,536
   (n = 1, then ×3 at the largest failing); if 1,024 survives 3/3, E16 at 1,024 ×1–3, then step down 896 → 768
   → 640 (n = 1, refine), and repeat the largest failing E15 budget ×3. Predict: E15 at 1,024 survives
   (P(OOM) ≈ 30 % per arm; U touches the cap with forced GCs); E16 at 1,024 fails ≥ 1/3; E15 fails at 768–896.
4. **At the V1 condition X*** (largest budget/workload with ≥ 2 failures in its first 3 arms; if none, the 1,024
   E15 condition is reported as a negative candidate with all four arms run anyway):
   endpoint ×3 (V1); control G ×3 (V2); intervention `concurrent_writes: 8` ×3 (V4; predict U ≤ 8 × 3S + B0 ≈
   400 MiB, survive 3/3 at ≥ 80 % of the endpoint's delivered bytes/s, the disk being the bottleneck);
   `-Dcassandra.dob.allocate_type=ONHEAP` ×3 (moves only the scratch to heap: predict U ≤ B0 + frames ≤ 150 MiB,
   no direct OOM; heap may OOM — recorded as such, P ≈ 30 %).
5. Dumps: one per failing condition kept on V (`/mydata/u1r2/runs/<arm>/`), the others reduced to
   `direct-holders.txt` and deleted if V's free space < 15 GiB.

**Predicted initiating failure.** `OutOfMemoryError: Direct buffer memory` on a `MutationStage` thread in
`Bits.reserveMemory` ← `DataOutputBuffer.expandToFit` ← `Mutation.serializer.serialize` ← `CommitLog.add(:308)` ←
`Keyspace.applyInternal` ← `MutationVerbHandler`; dump: DOB scratch ≥ 70 % of JDK owners, receive frames ≤ 60 MiB;
Netty counter ≈ 0. Tag predicted: U1, not mixed.

## Amendment 1 — 2026-11-17 13:06 EST (after the shakedown and q1–q2, before any arm below 1,024 MiB)

- **Harness fixes (no readings affected):** `ctl.sh cg` now reads the cgroup from the live pid (the shakedown
  sampled the root cgroup); `arm.sh` reads stdin from `/dev/null` (its `ssh` calls consumed the queue file, so q1
  ran only its first arm; the other two were re-queued unchanged in q2). Shakedown `SHAKE_1m_auto` (1 MiB, N = 1,
  30 s): harness works; auto resolves to **15,872 MiB** (`-XX:MaxDirectMemorySize=16642998272`), as computed in §4.
- **Readings (E15 unless stated, heap 2 GiB, 90 s, 1 s samples):** saturation sweep at 1,024 MiB exactly as the
  receive-queue bound predicts — N = 1: `MutationStage` active ≤ 8, K ≤ 120 MiB, U_peak 377; N = 2: ≤ 16, K ≤ 240,
  U_peak 631; **N = 4: active 32 in 59–61 of ≈ 104 load samples, K = 480 MiB (= 32 × 15 MiB), U_peak 997 / 877 /
  997** (r1–r3), all **survive**, touching the cap (5–14 `System.gc()` from `Bits.reserveMemory`). Auto (15,872):
  U_peak 936, survive. **E16 at 1,024: U_peak 1,020, K 512, 40 forced GCs, survive.** Every N = 4 arm: ≈ 600 writes
  applied in 90 s (≈ 100 MiB/s, the SSD's rate), ≈ 1,700–1,900 `MUTATION_REQ` dropped as expired, 98 % of client
  writes time out; coordinators write ≈ 8.5 GB of hints each per arm (wiped every arm).
- **Mechanism seen in the thread dumps (r1, `jcmd` every 5 s):** most of the time all 32 writers are parked in
  `MemtableAllocator$SubAllocator.allocate` (after `CommitLog.add`, scratch already trimmed), while
  `MemtablePostFlush` waits on a commit-log segment monitor; when memory is released the next ≈ 32 messages
  deserialize and serialize together (U jumps from ≈ 170 to 700–1,000 MiB within a second; `WaitingOnSegmentAllocation`
  +3–13 per burst). The holds last well under `Bits.reserveMemory`'s ≈ 0.5 s retry window, so at 1,024 the cap is
  touched but not exceeded for long.
- **Next (unchanged plan, §5 step 3):** 1,024 survives 4/4 → complete E16 at 1,024 (r2, r3), then step down:
  E15 at 896 and 768, E16 at 896 (n = 1 each), refine; then the V1 condition with control, `concurrent_writes: 8`
  and ONHEAP ×3. Predictions: E15 at 896 fails ≤ 1/1 (P ≈ 40 %), at 768 ≥ 1/1 (P ≈ 70 %); E16 at 1,024 stays
  ≤ 1/3.

## Amendment 2 — 2026-11-17 13:33 EST (after q3's first four arms, before q4)

- **Readings:** E16 at 1,024 r2 survive (U_peak 1,020, `WaitingOnSegmentAllocation` +447); E15 at 896 survive
  (892), E15 at 768 survive (756, touching the cap); **E16 at 896: direct OOM 15 s after load start**, first error
  on `MutationStage-14` in `Bits.reserveMemory` ← `DataOutputBuffer.expandToFit` (the 2S doubling step, at
  `UnfilteredSerializer.writeEndOfPartition`) ← `Mutation.serializer` … (U1 stack). E16 at 1,024 r3 is running.
- **Changes (dated before the readings they govern):**
  1. **N = 8 coordinators** (the researcher's "sweep coordinators until saturation", extended past 4): a second
     coordinator on each coordinator node at an alias IP (`ip addr add 10.10.1.12–.15/24`, environment; removed at
     the end), JMX 7299, 8 GiB heap; each client `INFL` 6 (48 outstanding in total, as at N = 4, and the same hint
     volume per node). Prediction from the receive-queue bound (§2): admitted ≈ 8 + (512 − 8 × 11)/15 ≈ 36 (E15)
     / ≈ 34 (E16) messages, i.e. **2–4 messages' frames (30–64 MiB) queued in direct memory on top of 32 scratch
     holders** — the "mixed" shape. Predict at 1,024: E16 fails (P ≈ 50 %), E15 survives touching the cap
     (P(OOM) ≈ 25 %).
  2. Budget search continues: E16 at 896 ×2 more (V1 candidate), E16 at 960 ×1, E15 at 640 ×1.
- Queue q4 (interleaved): `E16_N4i12_d896_r2`, `N8_E16_i6_d1024_r1`, `E16_N4i12_d896_r3`, `N8_E15_i6_d1024_r1`,
  `B_N4i12_d640_r1`, `E16_N4i12_d960_r1`. The V1 condition is chosen after q4 by the rule of §5 step 4 (largest
  budget with ≥ 2 failures in its first 3 arms; prefer 1,024 if an N = 8 condition qualifies).

## Amendment 3 — 2026-11-17 13:58 EST (after q4's first four arms; governs q5)

- **Correction:** `INFL` is per client *connection* and each client has 2, so N = 4 × `INFL` 12 and N = 8 × `INFL` 6
  both keep **96** requests outstanding (not 48 as written in §5 and amendment 2); per coordinator 12 × 16 MiB =
  192 MiB ≤ its per-client-IP native limit (204.8 MiB at an 8 GiB heap). Readings are unaffected.
- **Readings:** E16 at 896 r2, r3 survive (892, 892) → E16 at 896 = 1/3. **N = 8, E16 at 1,024: direct OOM 61 s
  after load start** (first error `MutationStage-25`, U1 stack via `MutationVerbHandler` → `CommitLog.add:308` →
  `expandToFit`; K_peak 544 MiB = the full global reserve 512 + 8 × 4, as predicted). N = 8, E15 at 1,024: survive
  (U_peak 861, K_peak 540). Dump of `E16_N4i12_d896_r1` (taken ≈ 0.1 s after the error): JDK owners 634 MiB = DOB
  scratch 368 + 96 MiB of released 2S buffers awaiting the Cleaner + networking `BufferPool` chunks 136 (at its
  128 MiB cap) + hints slab 32 (idle baseline) + NIO 2; Netty's separate counter 160 MiB.
- **V1 condition (fixed now): N = 8 coordinators × 2 × 6, E16 (16,776,192 B), heap 2 GiB, direct 1,024 MiB (the
  4 GiB-node resolution), 90 s.** Interleaved ×3 each (endpoint r2–r6, i.e. up to 6 in total, so that V1 can be
  read with its n/N): **control G** = 524,288 B values, same N and the same in-flight bytes per client (2 × 192
  requests = 192 MiB, as 2 × 6 × 16 MiB), no rate cap (both shapes are timeout-bound, so offered bytes/s match;
  measured and reported); **`concurrent_writes: 8`**; **`-Dcassandra.dob.allocate_type=ONHEAP`**.
  Predictions: endpoint ≥ 2/5 more (P ≈ 50 % per arm); G 0/3 (U = frames ≤ K 544 + pool + B0 ≈ 600–750 MiB:
  512 KiB messages are LARGE (> 64 KiB) so their frames wait in direct memory, but within K's contract);
  `concurrent_writes: 8` 0/3 (U ≈ B0 + P + 8 × 32–48 + queued frames ≤ (34 − 8) × 16 ≈ 750–950 MiB, delivered
  ≥ 80 % of the endpoint's); ONHEAP 0/3 direct (U ≈ B0 + P + frames ≤ 700 MiB), heap OOM possible (P ≈ 40 %:
  32 × 32 MiB scratch + 32 × 16 MiB mutations + memtable on a 2 GiB heap).
- Dumps: copied to pc96 for attribution only between queues (a 1 GB read from V's 100 MB/s disk during an arm would
  perturb it).

## Amendment 4 — 2026-11-17 14:25 EST (q5 at its fifth arm; governs q6, which runs after q5)

- **Readings so far in q5:** endpoint (N = 8, E16, 1,024) r2, r3 survive touching the cap (U_peak 1,004 / 1,020,
  57–… forced GCs) → endpoint 1/3 so far; control G r1 survive (U_peak 594, K 544, 18,152 writes applied, same
  ≈ 100 MiB/s); `concurrent_writes: 8` r1 survive (U_peak 801, `MutationStage` active ≤ 8, 26 queued, applied 532 vs
  the endpoint's 523–543).
- The endpoint is stochastic (as in run 1). To read V1 with a stated rate, q6 adds **8 more endpoint arms**
  (`N8_E16_i6_d1024_r7…r14`) — the condition, build and harness are unchanged — plus one **auto** arm in the N = 8
  shape (unconstrained U_peak for the ceiling comparison) and one arm at **1,152 MiB** (upward search for the largest
  failing budget). Stop rule unchanged (no arm starts after 16:25). Prediction: endpoint rate ≈ 1/3 → ≈ 3 more OOMs
  in r4–r14; 1,152 survives; auto U_peak 1,000–1,150 MiB.

## Amendment 5 — 2026-11-17 15:27 EST (q6 at its third arm; governs q7, which runs after q6)

- **Readings:** q5 finished: endpoint (N = 8, E16, 1,024) r1–r6 = **1/6** (r2–r6 survive at the cap, U_peak
  1,004–1,021, 69–105 forced GCs each); control G 0/3 (U_peak 594–612, K 544); `concurrent_writes: 8` 0/3
  (800–842); ONHEAP 0/3 (direct 202–230, heap peak 1,912–1,992 MiB, no heap OOM). q6 r7, r8 survive (1,020–1,021).
- The endpoint rate at 1,024 is ≈ 1/8 so far, so V1 there depends on q6's remaining six arms. As a boundary reading
  for the same shape, q7 (if time allows, no arm after 16:25) runs **N = 8, E16 at 896 MiB ×4** (budget ≥ 512 MiB,
  below the 4 GiB-node resolution). Prediction: ≥ 2/4 at 896 (N = 4 gave 1/3). No control/intervention is repeated
  at 896 (no time); the 1,024 control and interventions are reported as they are.

## Closing note — 2026-11-17 16:35 EST (no new design; record only)

- q6 and q7 ran as written; no arm started after 16:25 (last start 16:23). Endpoint N = 8 · E16 · 1,024: **2/14**
  (r1, r11); 1,152: 0/1; auto (N = 8, E16): U_peak 1,212 MiB; N = 8 · E16 · 896: 2/4 (r3, r4). All four failures:
  `MutationStage`, JDK counter, `CommitLog.add:308` → `expandToFit`; dumps: DOB scratch 496–752 MiB, live receive
  frames ≤ 0.4 MiB.
- Death times in the case file come from the first `ERROR` timestamp (amendments 2–3 quoted the first missing
  sample: 15 s → 9 s for `E16_N4i12_d896_r1`, 61 s → 54 s for `N8_E16_i6_d1024_r1`).
- Prediction fit: receive-queue bound on writers (8 / 16 / 32 at N = 1 / 2 / 4) ✓; auto no OOM ✓ (U_peak 936 E15,
  1,212 E16 — the E16 value is the standing ceiling, E15's is below its 1,146 ceiling); E15 at 1,024 survive ✓ but
  E15 never failed down to 640 ✗ (predicted failure at 768–896); E16 at 1,024 ≤ 1/3 ✓ (N = 4 0/3, N = 8 2/14);
  N = 8 E16 at 1,024 P ≈ 50 % ✗ (≈ 14 %); control ✓; `concurrent_writes: 8` ✓ (U 800–842, at the top of the
  predicted range); ONHEAP ✓ (direct ≤ 230, no heap OOM); initiating stack ✓; tag U1, not mixed ✓.
- Cleanup 16:30: all processes stopped on the five nodes, alias IPs removed, linger disabled on all five.
