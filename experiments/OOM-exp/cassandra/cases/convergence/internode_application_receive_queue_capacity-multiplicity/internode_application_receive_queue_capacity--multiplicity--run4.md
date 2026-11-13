# C1 run 4 — internode receive-queue multiplicity at default capacities, 2 GiB heap, 512 MiB+ direct

**Direction / sub-direction:** convergence · multiplicity (loaded peers × per-endpoint/per-connection
receive allowances). **Allocation domain:** victim's inbound application receive queue (queued LARGE
mutation frames in direct memory). **Capacity regime:** **default** (Q/E/G = 4/128/512 MiB unset in yaml;
all other capacities default). **Budget:** heap 2048 MiB (ideal), `-XX:MaxDirectMemorySize` the dial
(512 MiB = standing-rule minimum, searched upward), non-binding 12 GiB safety scope.
**Pinned source/build:** cassandra-5.0.9 (`f2de6956`), unpatched, read-only reuse of `/mydata/b6/cassandra`;
JDK 11.0.33, G1. **Node:** `pc96` only (victim, fast co-replica, 8 coordinators, client colocated on
loopback). **Date:** 2026-11-12. **Design:** [`design/C1-run4-design.md`](design/C1-run4-design.md)
(amendments 1–5, all dated before the readings they govern). Follows
[run 3](internode_application_receive_queue_capacity--multiplicity--run3-fastcoreplica.md).

**Status (filed 2026-11-12 in `convergence/`, researcher's review):** condition **D** (shipped yaml) at heap 2 GiB / direct 512 MiB: **`verified-OOM · diagnostic`** — V1–V7 met under the standing budget rule, but the researcher labelled it `diagnostic` because 512–640 MiB direct is below what `cassandra-env.sh` resolves for any 2 GiB-heap node (≥ 1 GiB; nothing fails at ≥ 672 MiB). Condition **H** (hints off, commitlog cap): `verified-OOM · diagnostic`; its V5 rests on D's dumps (same build, budget and mechanism), accepted by the researcher. Largest failing direct budget **640 MiB (4/5)**; none at 672 (0/3), 704 (0/3), 768 (0/1), 2048 MiB (0/2). This run-4 file is the case's final file; runs 1–3 files remain alongside as history.

## Summary

- **Conclusion.** At default receive-queue capacities (Q/E/G = 4/128/512 MiB) and an ideal 2 GiB heap,
  eight coordinators writing 1 MiB mutations at 500/s fill a victim's inbound receive queue to its admission
  ceiling during its own memtable-flush stalls (no injected delay, default 2 s timeouts), and the victim dies
  of `OutOfMemoryError: Direct buffer memory` at the minimum acceptable direct budget of 512 MiB: **10/10**
  (3/3 with hints off; 7/7 with a fully default yaml, three of them with heap dumps). One or two loaded peers at the same total load never
  fail (**0/6** each). The endpoint persists up to **640 MiB direct (4/5)** and disappears at ≥ 672 MiB
  (0/3, 0/3, 0/1, 0/2 at 672/704/768/2048 MiB).
- **Root cause.** The receive queue charges each peer at most Q + E and all peers together at most N·Q + G,
  and those bytes are **direct** memory (queued LARGE frames). With N ≥ 4 loaded peers the global reserve
  G = 512 MiB saturates, so the admitted total reaches 528–544 MiB, **every per-peer and global counter
  stays within its contract**, and that total plus ~50 MiB of other direct memory and the networking pool's
  slack exceeds `MaxDirectMemorySize`. Nothing reconciles G (+ N·Q) with the JVM direct limit: a
  configuration-sizing gap (convergence by multiplicity of peers), not a counter bypass. The exclusive
  allowances N·Q add only 32 MiB at N = 8; most of the N dependence is N·E filling G.

---

## 1. Constraints, protection map, configuration labels

### Mechanism (source, 5.0.9)
- `AbstractMessageHandler.acquireCapacity` (`net/AbstractMessageHandler.java:411–455`): each inbound message
  is charged (on-wire size) to the connection's exclusive allowance **Q**; the overflow to the global
  reserve **G** and the endpoint reserve **E**. Per peer at most Q + E; aggregate reserve at most G.
- LARGE messages (larger than one 128 KiB frame) keep their raw frames (`LargeMessage.buffers`,
  `ShareableBytes` slices of `BufferPool` **direct** buffers, `:522–600`) until the `MutationStage` task
  deserializes them just in time (`InboundMessageHandler.java:358–383`); capacity is released in
  `ProcessMessage.run`'s `finally` (`:404–444`), also for messages found expired at dequeue.
- Admission ceiling, one LARGE connection per peer: **K_max(N) = N·Q + min(G, N·E)** =
  **132 / 264 / 528 / 544 MiB for N = 1 / 2 / 4 / 8**. G caps only the reserve part; N·Q is outside G by
  contract.

### Protection map (fixed before the run; design §1)

| Domain | Owner / release | Contract (default) | Multiplicity | Budget metric |
|---|---|---|---|---|
| R: queued LARGE frames (victim) | `LargeMessage.buffers` until stage deserializes | Q=4 MiB/conn, E=128 MiB/peer, G=512 MiB global (on-wire bytes, hard) | N loaded coordinators | JVM direct |
| P: networking `BufferPool` retention/slack | pool chunks, overflow `allocateDirect` | `networking_cache_size` 128 MiB pool cap | per event loop | JVM direct |
| O: other direct (baseline, per-thread `DataOutputBuffer` scratch in MutationStage/flush/compaction) | thread-local scratch, freed on GC | DOB recycle limit 1 MiB/thread (default) | 32 writers + flush + compaction | JVM direct |
| H/M: mutation being applied, memtable | heap | 32 writers; `memtable_heap_space` = heap/4 = 512 MiB | — | heap (reported, not claimed) |

**Feasibility:** baseline direct (measured 50 MiB) + K_max(N) + P (≤ 128) vs budget: N=8 → ≤ 722 MiB,
N=4 → ≤ 706, N=2 → ≤ 442, N=1 → ≤ 310 MiB. Convergence is feasible at 512 MiB for N ≥ 4 and impossible
for N ≤ 2; at ≥ 768 MiB it is impossible for every N ≤ 8 (would need N·Q ≳ 200 MiB more, ≈ 50+ peers).

### Configuration / budget audit

| Setting | Class | Value |
|---|---|---|
| Q, E, G (receive and send queues) | **tested capacity — default** (absent from yaml; resolved values logged `internode_application_receive_queue_capacity=4MiB … reserve_global_capacity=512MiB`) | 4 / 128 / 512 MiB |
| `networking_cache_size`, `file_cache_size`, `memtable_*`, `concurrent_writes`, key/counter cache | default (unset) | 128 MiB; 512 MiB; heap/4; 32; defaults |
| heap `-Xms/-Xmx` | budget | 2048 MiB (standing-rule ideal) — every arm |
| `-XX:MaxDirectMemorySize` | budget (dial) | 512 / 640 / 672 / 704 / 768 / 2048 MiB; ≥ 512 meets the standing rule |
| resolved defaults on pc96 | reference | `cassandra-env.sh` would give heap 15872 MiB; its own direct value appears as `-XX:MaxDirectMemorySize=15872M` in the JVM args (overridden by ours, last flag wins) |
| victim scope | budget (safety, non-binding) | `systemd-run --user --scope -p MemoryMax=12G -p MemorySwapMax=0`; `oom_kill` = 0 in every valid arm (see INVALID arm below) |
| `write_request_timeout` | default 2000 ms on all instances | run-3 open item, see §3.1 |
| `hinted_handoff_enabled: false`, `commitlog_total_space: 2048MiB` | supporting deviation / environment — **condition H only** | removed in **condition D** (yaml = shipped file except environment keys) |
| storage on tmpfs (`/mydata/c1r4/shm`, 24 GiB) | environment | keeps disk out of the drain path; disk work stays paused |
| loopback colocation, `taskset` (V 0–7, F 8–15, C1–C8 16–23, client/sampler 24–31) | environment | victim = an 8-core node |
| `GossipingPropertyFileSnitch`, dc v/f/c, `NTS {v:1,f:1}`, `num_tokens: 1`, `initial_token` | environment/topology | `internode_compression: dc` (default) is active between dc c and dc v |
| workload | workload | INSERT 1 MiB **zero-filled** blob, CL=ONE, keys mod 2000, total **500 writes/s** shared by the N active coordinators (matched aggregate load), 90 s |
| Byteman | **not used** (dropped by amendment 1) | — |

Victim yaml diff (condition H): [`logs-run4/victim-yaml-diff-conditionH.txt`](logs-run4/victim-yaml-diff-conditionH.txt).

---

## 2. Verification solution (as executed)

Design and amendments: [`design/C1-run4-design.md`](design/C1-run4-design.md). Stopping budget: ≤ 7 h
(stop launching at 15:45), ≤ 45 arms, R ≤ 500/s. Every arm starts from a **clean ring** (all 10 instance
directories and tmpfs data regenerated: `harness-run4/ring-up.sh`), then 5 s sampler warm-up, 90 s load,
30 s observation, stop.

Harness ([`harness-run4/`](harness-run4/)): `ctl.sh` (instances; `DEFAULTS=1` = condition D),
`ring-up.sh`, `arm.sh <name> <N> <rate> <directMiB> none`, `batch1.sh` (arm queue), `C1Load.java`
(driver 3.x client, one session per active coordinator, shared RateLimiter), `C1Sample.java` (1 s JMX
`java.nio:BufferPool=direct` MemoryUsed = **U**, heap, MutationStage, Cassandra BufferPool metrics + CQL
`system_views.internode_inbound` Σ`using_bytes` = **K**, reserve, throttled/received/processed/expired),
`peaks.py`, `build.sh`, `load.sh`, `logback-quiet.xml`, `hprof_direct.py` (dump attribution, amendment 4), `netty-probe.sh` (amendment 5), `arm-peerlogs.sh` (arm.sh + tmpfs usage and F/C log copies; used for D_N8_d512_r4 only); `delay-*.btm` were prepared but **never used**. Endpoint detection: `java.lang.OutOfMemoryError: Direct buffer memory`
in the victim's system.log (Cassandra then forces a heap-space OOM and `-XX:OnOutOfMemoryError=kill -9`
kills the JVM), victim death in the samples, and the scope's `memory.events` (`oom_kill` must stay 0).

Conditions:
- **H** (hints off, commitlog cap 2 GiB): sweep N=1/2/4/8 at 2048 MiB; OOM stage N=8 at 512 ×3; control
  N=1 at 512 ×3; intervention N=2 at 512 ×3; N=4 at 512 ×1; budget search N=8 at 640/672/704/768.
- **D** (no supporting deviation): N=8 ×3, N=1 ×3, N=2 ×3 at 512 MiB.

---

## 3. Runtime results

Raw data: `/mydata/c1r4/runs/<arm>/` on pc96 (`samples.csv`, `peers.txt`, `cg.csv`, `load.log`,
`V-logs/system.log`, `V-logs/gc.log*`, `first-oom.txt`, `outcome.txt`, `foreign.txt`); one line per arm in
`/mydata/c1r4/runs/summary.txt`. Excerpts in [`logs-run4/`](logs-run4/).

### 3.0 Invalid / aborted arms (excluded)
| Arm | Why |
|---|---|
| `INVALID_A0_nat_N8_r400` | victim killed by its own 12 GiB safety scope (`CONSTRAINT_MEMCG`, dmesg 09:26:23): tmpfs sstables of random blobs charged to the scope. Fixed by zero-filled blobs (amendment 1). |
| `INVALID_C_N1_d512_r2_aborted`, `INVALID_D_N8_d512_r1_aborted` | harness error 10:25: a mis-chained queue started a second ring-up concurrently; both aborted and re-run (`C_N1_d512_r2b`, `D_N8_d512_r1`). |

### 3.1 Calibration and the timeout check (run-3 open item)
| Arm (no Byteman, T = 2 s default, N=8, direct 2048) | K_peak / K_max | U_peak | throttled / expired | client |
|---|---|---|---|---|
| `A0_nat_N8_r300` | 57 / 544 | 146 | 0 / 0 | 303/s, 0 err |
| `A0_nat_N8_r500` | **543 / 544** (511 reserve + 8×4.0) | 683 | 2945 / 2486 | 505/s, 0 err |

At 500/s the victim's MutationStage stalls during memtable flushes (pending = 511, heap ≈ 1.9 of 2 GiB,
`memtable_heap_space` = 512 MiB) and the queue sits at the ceiling for ≈ 14 s of 1 s samples
([`logs-run4/A0_nat_N8_r500-samples.txt`](logs-run4/A0_nat_N8_r500-samples.txt)). **Timeout verdict:** the
default 2 s sender timeout does not cap occupancy, because expired messages are only released when a
MutationStage thread dequeues them, and the stage is blocked; λ·T is irrelevant during a stall. No
timeout change was needed (unlike runs 1–3, which raised it or injected a 100 ms apply delay).

### 3.2 U vs K per N (matched aggregate load 500/s; surviving arms)
U = JVM direct pool `MemoryUsed`; K = Σ `using_bytes` over peers; baseline U at idle = 50 MiB in every arm.

| N | K_max | K_peak (arms) | U_peak (arms) | U_peak − baseline | max per-peer K | reserve peak |
|---|---|---|---|---|---|---|
| 1 | 132 | 130–131 (S_N1_d2048, C ×3, D ×2); 64 in D_N1_r3 | 201–242 | 151–192 | 131 (= Q+E−1) | 126–127 |
| 2 | 264 | 262 (S, I ×3, D ×3) | 332–352 | 282–302 | 131 | 254 |
| 4 | 528 | 524 (S_N4_d2048) | 594 | 544 | 131 | 508 |
| 8 | 544 | 543 (A0_r500, 672 ×3, 704 ×3, 768, 640_r2) | 658–704 (capped at the budget in 640_r2 and 704_r3) | 608–654 | 131 | 511 |

At the ceiling (samples with K ≥ 95 % of its peak) U − baseline − K ranges **−39 … +92 MiB** (median ≈ 0–30;
non-atomic 1 s sampling), i.e. the physical direct memory tracks the admitted bytes; the remainder is the
networking pool's retained chunks (pool `Size` ≈ 89 MiB after load, ≤ 128 MiB cap) and per-thread
`DataOutputBuffer` scratch. **Every domain stays within its contract** (per peer ≤ Q+E = 132, reserve ≤ G =
512, U − baseline − K ≤ pool cap), so the direction is **convergence**, not bypass. Physical memory grows with
N as K_max(N) does (K_max +132, +264, +16 MiB per doubling of N: N·E until G saturates, then only N·Q; U_peak − baseline +≈110, +≈250, +≈60–110).
Excerpts: `logs-run4/S_N{1,2,4}_d2048-samples.txt`.

### 3.3 OOM stage, control and intervention (heap 2048, direct 512 MiB, R = 500/s)

| Condition | Arm | N | Outcome | Death (s after load start) | K / U at last sample before death | First `Direct buffer memory` thread |
|---|---|---|---|---|---|---|
| H | O_N8_d512_r1 | 8 | **direct OOM → killed** | 27 | 480 / 512 | CompactionExecutor (DOB scratch) |
| H | O_N8_d512_r2 | 8 | **direct OOM → killed** | 27 | 466 / 512 | Messaging-EventLoop (`BufferPool.allocate`, inbound) |
| H | O_N8_d512_r3 | 8 | **direct OOM → killed** | 23 | 495 / 512 | CompactionExecutor |
| H | O_N4_d512_r1 | 4 | **direct OOM → killed** | 15 | 476 / 512 | MutationStage (DOB scratch) |
| H | C_N1_d512_r1/r2b/r3 | 1 | survive ×3 | — | K_peak 131, U_peak 232/242/201 | — |
| H | I_N2_d512_r1/r2/r3 | 2 | survive ×3 | — | K_peak 262, U_peak 350/334/345 | — |
| **D** | D_N8_d512_r1..r4 | 8 | **direct OOM → killed ×4** | 26 / 25 / 20 / 20 | 490, 480, 487, 469 / 511–512 | MemtableFlushWriter ×2, Messaging-EventLoop ×2 |
| **D** | DD_N8_d512_r1..r3 (+ heap dump, amendment 4) | 8 | **direct OOM → killed ×3**, dump written each time | 19 / 25 / 24 | 474, 468, 478 / 512 | CompactionExecutor ×2, Messaging-EventLoop ×1 |
| **D** | D_N1_d512_r1..r3 | 1 | survive ×3 | — | K_peak 131/131/64, U_peak 238/227/236 | — |
| **D** | D_N2_d512_r1..r3 | 2 | survive ×3 | — | K_peak 262, U_peak 352/343/332 | — |

**n/N:** N=8 at 512 MiB **10/10** (H 3/3, D 7/7 incl. the 3 dump arms); N=4 1/1; N=1 control **0/6**; N=2 intervention **0/6**.
In every failing arm the system.log has `java.lang.OutOfMemoryError: Direct buffer memory` first, then
Cassandra's `Force heap space OutOfMemoryError in the presence of` and `-XX:OnOutOfMemoryError="kill -9 %p"`
executing (launch.log); the scope's `memory.events` stayed `oom 0 / oom_kill 0` (not a container kill). The
thread that throws is whichever allocator hits the limit (inbound frame pool 4/12, DOB scratch in
compaction/flush/MutationStage 8/12 across all failing arms); the **holder** at failure is the receive queue:
K = 466–495 MiB of the 512 MiB budget one second before death. Excerpts:
`logs-run4/{O_N8_d512_r1,O_N8_d512_r2,O_N8_d512_r3,O_N4_d512_r1,D_N8_d512_r1,B_N8_d640_r1}-first-oom.txt`.
The control/intervention arms delivered the full workload (client 504.8–505.6/s, 0 errors; victim processed
all ≈ 45.5 k mutations, 0–36 expired), so their survival is not bought by dropping work. In the N=1/2 arms
the queue also reached its (smaller) ceiling (throttled 29–387).

**Post-endpoint artifact (condition D, N=8):** ≈ 30–45 s after the victim died, the fast replica and most
coordinators stopped on `No space left on device` — with hinted handoff on, hints for the dead victim filled
the 24 GiB tmpfs (`logs-run4/D_N8_d512_r4-post-endpoint-tmpfs-ENOSPC.txt`). This happens after, and because
of, the endpoint; it is an environment limit of this harness, not part of the result.

### 3.4 Budget search (N=8, condition H, heap 2048)

| Direct budget | n/N endpoint | U_peak of survivors |
|---|---|---|
| 512 MiB | **3/3** (+ 4/4 in D) | — |
| 640 MiB | **4/5** (r1, r3, r4, r5 die at 26–32 s with K = 543 = K_max, U = 640) | r2 touched 640 and survived (the allocation succeeded after the `Bits.reserveMemory` GC) |
| 672 MiB | 0/3 | 664–670 |
| 704 MiB | 0/3 | 658, 679, 704 (r3 touched the cap and survived) |
| 768 MiB | 0/1 | 677 |
| 2048 MiB | 0/2 (A0_r300, A0_r500; the N=1/2/4 sweep arms also survived) | ≤ 683 |

**Largest failing budget: 640 MiB direct (4/5)**; boundary 640–672 MiB, consistent with the feasibility
bound (baseline 50 + K_max 544 + pool slack ≤ 128 = 722 MiB maximum; observed U_peak ≤ 704).

### 3.4b Heap dumps at failure: who holds the direct memory (amendment 4, condition D)

`-XX:+HeapDumpOnOutOfMemoryError` on the victim; the dump is written at Cassandra's forced heap OOM, right after
the first `Direct buffer memory` error and before `kill -9` (writing took 1.4–1.7 s). Dumps (≈ 680 MB
each) are kept in `/mydata/c1r4/runs/DD_N8_d512_r{1,2,3}/`. Analysis `harness-run4/hprof_direct.py`: every
`DirectByteBuffer` with a `cleaner` and no `fd` owns `capacity` bytes counted by the JDK (`Bits`, the
`MaxDirectMemorySize` counter that threw); slices point to their owner through `att`; bytes are attributed by
address range to the referrer chain of each live slice (5–6 hops), Cleaner links ignored. Excerpts:
`logs-run4/DD_N8_d512_r{1,2,3}-direct-holders.txt`.

| Holder (JDK-accounted direct memory) | r1 | r2 | r3 |
|---|---|---|---|
| JDK-accounted owners total | 511.0 | 509.9 | 508.9 MiB |
| **R** queued LARGE frames: `ShareableBytes.bytes ← Object[] ← ArrayList.elementData ← InboundMessageHandler$LargeMessage.buffers` | **311.7 (61.0 %)** | **307.9 (60.4 %)** | **318.6 (62.6 %)** |
| **R** frames being decoded: `ShareableBytes.bytes ← FrameDecoder$IntactFrame.contents` | 28.3 (5.5 %) | 31.0 (6.1 %) | 20.4 (4.0 %) |
| **P** Cassandra `BufferPool` chunk slabs with no live consumer slice (17 × 8 MiB macro-chunks: networking pool at its 128 MiB cap + 1 chunk-cache chunk) | 136.3 (26.7 %) | 136.1 (26.7 %) | 136.1 (26.7 %) |
| O hints buffers (`HintsBuffer.slab`, hints on in D) | 32.2 | 32.2 | 32.2 |
| O netty/NIO, storage I/O buffers | 2.4 | 2.7 | 1.6 |
| O `DataOutputBuffer` scratch | 0.0 | 0.0 | 0.0 |

The frames are 32 KiB `allocateDirect` buffers (≈ 10.9 k owners of 32768 B), i.e. `BufferPool` **overflow**
allocations made because the networking pool was at its 128 MiB cap (the JMX `OverflowSize` peak ≈ 333 MiB
agrees). **Receive-path holders (R) are 66–68 % of the JDK-accounted direct memory, R + its buffer pool (P)
93–94 %**; the threads that threw (compaction/flush DOB scratch, inbound `BufferPool.allocate`) hold almost
nothing (DOB 0.0 MiB): they are the allocation that found the budget used up. R in the dump (336–340 MiB) is
below K one second earlier (468–478 MiB): K is on-wire bytes of every admitted message, including those
already deserialized onto the heap by the 32 MutationStage writers (capacity is released only after apply)
and messages released between the last sample and the dump.

### 3.4c Netty's separate direct-memory counter (coordinator question, amendment 5)

Netty allocates its pooled arena chunks with no Cleaner (`USE_DIRECT_BUFFER_NO_CLEANER = true`) and counts
them in its own `PlatformDependent.DIRECT_MEMORY_COUNTER`, limited by `DIRECT_MEMORY_LIMIT` = the same
`MaxDirectMemorySize`. These bytes are **not** in the JMX `java.nio` pool (our U) and not in `Bits`.

| Dump | Netty `DIRECT_MEMORY_COUNTER` | Netty limit | Netty memory (no-cleaner `PoolChunk.memory`, 16 MiB each) | JDK-accounted (U domain) |
|---|---|---|---|---|
| DD r1/r2/r3, at failure, direct 512 | **96.0 MiB** (all three) | 512 MiB | 6 × 16 MiB | 509–511 MiB (at its 512 cap) |
| NP_N8_d2048 idle (before load) | 192.0 MiB | 2048 MiB | 12 × 16 MiB | 49.9 MiB |
| NP_N8_d2048 at the ceiling (K = 543) | 272.0 MiB | 2048 MiB | 17 × 16 MiB | (dump taken with `-all`: includes unreachable buffers; only the Netty counter is read) |

- **Which counter threw:** in all 15 failing arms the error is `java.lang.OutOfMemoryError: Direct buffer
  memory` from `java.nio.Bits.reserveMemory` (via `ByteBuffer.allocateDirect` in Cassandra's `BufferPool` or
  `DataOutputBuffer`). No `io.netty.util.internal.OutOfDirectMemoryError` appears in any victim log. Netty's
  counter was at 96 of its 512 MiB at failure.
- **No receive-queue frames are in Netty memory:** the queued frames found in the dumps are all JDK-accounted
  `allocateDirect` buffers; the Netty chunks hold no `LargeMessage` chain.
- **Effect on the U-vs-K table:** none for the claimed domain. U (JMX `java.nio`) is exactly the counter
  that fails and the memory that holds the queued frames. But U **undercounts the process's total direct
  memory** by Netty's arena memory: ≈ 96 MiB at a 512 MiB flag, 192–272 MiB at 2048 MiB (Netty sizes its
  arena count from the limit, so this part grows with the flag and with load, not with N in a measured way).
- **Effect on the budget interpretation:** `-XX:MaxDirectMemorySize=X` caps the JDK counter at X and Netty
  separately at X. At failure with X = 512 MiB the victim held ≈ 607 MiB of native direct memory (511 + 96);
  at the largest failing flag (640 MiB) about 640 + ~100 MiB. The endpoint is the **JDK** counter reaching X;
  n/N and the boundary (640 fails, ≥ 672 survives) are unchanged, but the physical direct footprint at the
  boundary is ≈ 100 MiB above the flag value, and a container limit sized to the flag would be too small.

### 3.5 Prediction fit
Predicted (amendment 1): OOM at 512 for N = 8 and 4, survive at N = 1, 2; largest failing ≈ 640; none at
768 — all as observed. Run-2's earlier statement that total occupancy is Q-invariant is not contradicted
(run 4 did not vary Q).

### 3.6 Host and foreign load
pc96 shared with other sessions: no foreign Java or heavy (> 50 % CPU) process at any arm start/mid/end
except transient `git` (≤ 77 %) and another agent's ssh controller to apt140; 1-min load average at arm
start ≤ 11 (mostly the previous arm's own decay), up to ≈ 23 mid-arm (our 10 JVMs + client). Victim pinned to
cores 0–7, others 8–31 (`foreign.txt` per arm).

---

## 4. Conclusion

**Mechanism established (convergence · multiplicity, default capacities).** The per-peer contract
(Q + E = 132 MiB) and the global reserve (G = 512 MiB) both hold exactly, yet with ≥ 4 loaded peers the
admitted on-wire bytes (N·Q + G = 528–544 MiB), which live in direct memory as queued LARGE frames, plus
≈ 50 MiB baseline and pool slack exceed a 512–640 MiB `MaxDirectMemorySize`, and the victim dies of a
direct-buffer OOM within 15–32 s of load. Reducing the loaded peers to 1 or 2 at the same total load keeps
the admitted total at 132 / 264 MiB and removes the endpoint (0/12) without losing work.

**Interpretation.** Configuration-sizing / validation gap: Cassandra does not check the receive-queue
reserves (or N·Q) against the JVM direct limit; the default G alone equals the protocol's minimum
acceptable direct budget. The precise multiplicity is *N·E filling G* (N ≥ 4 needed), with N·Q contributing
only 32 MiB at N=8; the original C1 hypothesis that exclusive allowances N·Q outside G drive OOM at default Q
is **not** what fails here — N·Q would need ≈ 100+ peers to matter at ≥ 768 MiB.

**Status by condition (proposed):**

| Condition | Config | Endpoint at 512 MiB | Control N=1 | Intervention N=2 | Proposed status |
|---|---|---|---|---|---|
| D | shipped yaml + environment keys only | 7/7 (3 with dumps) | 0/3 | 0/3 | `verified-OOM · diagnostic` (researcher, 2026-11-12) |
| H | + hints off, `commitlog_total_space` 2 GiB | 3/3 (640 MiB: 4/5) | 0/3 | 0/3 | `verified-OOM · diagnostic` |

**V1–V7 (condition D, heap 2 GiB, direct 512 MiB, N=8, 500/s 1 MiB writes):**

| | Evidence | Met |
|---|---|---|
| V1 repetition | D_N8_d512_r1–r4 + DD_N8_d512_r1–r3: 7/7 direct OOM (H: 3/3; 640 MiB: 4/5) | yes |
| V2 matched control | D_N1_d512_r1–r3 (N=1, same budget/build/load): 0/3 (H: 0/3) | yes |
| V3 measurement | U = JVM direct `MemoryUsed` (JMX, 1 s) vs K = Σ `using_bytes`; table §3.2, U − base − K ∈ [−39, +92] MiB at the ceiling | yes |
| V4 intervention | reduced N: D_N2_d512_r1–r3 0/3 (H 0/3), matched total load, client 505/s, 0 errors | yes |
| V5 initiating failure | first `OutOfMemoryError: Direct buffer memory` (JDK `Bits` counter) + stack in every failing arm; **heap dumps at failure ×3 (DD_N8_d512_r1–r3)**: queued LARGE frames held by `InboundMessageHandler$LargeMessage.buffers` = 308–319 MiB, + frames in decode 20–31 MiB = 66–68 % of the 509–511 MiB JDK-accounted direct memory; with the receive path's `BufferPool` chunks 93–94 %; DOB scratch 0 (§3.4b). Netty's separate counter 96 MiB, did not throw (§3.4c) | **yes** |
| V6 default constraints | Q/E/G, networking pool, DOB, memtable, concurrent_writes all unset in yaml (`victim-yaml-diff-conditionD.txt`); resolved values in system.log | yes |
| V7 acceptable budget | heap 2048 MiB (ideal), direct 512 MiB (= standing-rule minimum; largest failing 640 MiB); safety scope 12 GiB non-binding (oom_kill 0) | yes (standing rule) |

**Condition H, V1–V7:** V1 3/3 (+ 640 MiB 4/5), V2 0/3 (N=1), V3 as D, V4 0/3 (N=2), V6 and V7 as D. V5:
first errors and 1 s counters in H; the heap dumps were taken in condition D only (same build, budget,
topology and mechanism; hints and the commitlog cap do not touch the direct-memory holders apart from D's
32 MiB `HintsBuffer`). Status `verified-OOM · diagnostic` (hints off), if the reviewer accepts the D dumps
for H's V5.

**Limits and realism (for the researcher's review).**
- 512–640 MiB direct is acceptable under the standing rule but **below what `cassandra-env.sh` resolves**
  for any node: ¼ RAM for a node with ≤ 63 GiB, i.e. 1 GiB direct for the 4 GiB-RAM node whose automatic heap
  would be 2 GiB (on pc96 itself the JVM args showed 15872M). At ≥ 672 MiB the endpoint did not occur (0/7).
  A deployment that sets heap explicitly but leaves `MAX_DIRECT_MEMORY_SIZE` unset gets the large default.
- Fill is **episodic** (memtable-flush stalls of the victim at 2 GiB heap and 500 MiB/s ingest on 8 cores);
  at 300/s the victim kept up (K_peak 57). Results hold for this ingest rate, 1 MiB zero-filled blobs (the
  sstables compress; `internode_compression: dc` is active), loopback colocation, tmpfs storage.
- Peers are colocated processes on one host (topology choice); the senders, fast replica and client stayed
  healthy until the victim died.
- No Byteman, patches or timeout changes in either condition; hints off only in H.
- V5 now rests on three heap dumps at failure (amendment 4); the dumps were written after Cassandra's forced heap OOM, i.e. ~1 s after the direct OOM, so a few messages may have been released in between.
- U (JMX `java.nio`) excludes Netty's own direct memory (96 MiB at a 512 MiB flag, up to 272 MiB at 2048); the physical direct footprint is that much above U and above the flag (§3.4c).

**Cleanup:** all instances stopped after every arm (`ctl.sh stop all`); at the end no c1r4 JVM or listening
port (127.0.0.21/.22/.31–.38) remained, no `c1r4V-*` scope, the tmpfs `/mydata/c1r4/shm` was emptied and
unmounted. After the amendment-4/5 arms the same cleanup was repeated (tmpfs remounted for them, then emptied and unmounted again). Raw data kept under `/mydata/c1r4/runs/` (≈ 3.7 GB incl. the four dumps: `DD_N8_d512_r{1,2,3}/*.hprof`, `NP_N8_d2048/{idle,ceiling}.hprof`) and `/mydata/c1r4/ring/` (last ring's logs/configs).
`/mydata/b6/cassandra` was only read.

