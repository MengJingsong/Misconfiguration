# S1 design — JVM-direct combo stack (combo playbook), Cassandra 5.0.9, pc96

Written 2026-11-16 13:00–13:20 EST, **before any reading of this run**. Amendments below are dated
before the readings they govern. Campaign row S1 (S = stacked combo case). Playbook:
[`combo-playbook.md`](../../../../../combo-playbook.md). Source cases reused: C1 run 4 (C = convergence
investigation; receive-queue multiplicity, pc96), C2 (concurrent reads), C3 (DOB worker multiplicity),
R6-V (R = recheck; -V = re-test at defaults: DOB + hint slabs), B1 (B = bypass investigation;
networking-pool release defect), U1 (U = unprotected-accumulation lead; large-mutation DOB fill).

## 0. Time and stopping budget

Start ≈ 12:55 EST. Measuring stops at **15:40 EST**; filing by 15:55. ≤ 26 arms of ≈ 5 min each.
Single node `pc96` (local), no apt node is used (no separate client is needed: all layers are
driven from pc96 cores 24–31, as in C1 run 4). If time runs out the case is filed `candidate` with
the stage reached. No escalation after an endpoint beyond the planned repeats/controls/interventions.

## 1. Budget domain, budgets (V7) and the two direct counters

- **Domain: JVM direct** (`-XX:MaxDirectMemorySize`). Heap fixed at **2048 MiB** (ideal) in every arm.
- Direct budgets: **2048 MiB** (ideal; main dial), **3982 MiB** (what `cassandra-env.sh` resolves as
  ¼ RAM on a 15.55 GiB node, the "auto" value in the campaign row; pc96 itself would resolve heap 15872 MiB),
  512 MiB (standing-rule minimum — already reached by stage 1 alone, C1 run 4: 10/10; not re-run here).
  All ≥ 512 MiB → V7 met by the standing rule (2026-11-11).
- Safety scope only: victim in `systemd-run --user --scope -p MemoryMax=12G -p MemorySwapMax=0`
  (non-binding; `oom_kill` must stay 0, else the arm is invalid).
- **Stage-0 finding fixed before readings: the "JVM direct" domain has two independent counters**, both
  limited to the same `MaxDirectMemorySize` value X (C1 run 4 §3.4c, from dumps):
  - **JDK counter** (`java.nio.Bits`, JMX `java.nio:type=BufferPool,name=direct` = our U): every
    `ByteBuffer.allocateDirect` — Cassandra `BufferPool` chunks and overflow (networking pool, chunk-cache
    pool), queued internode LARGE frames, `HintsBuffer` slabs, `DataOutputBuffer` scratch (retained and
    in-flight), commit-log/compression buffers.
  - **Netty counter** (`PlatformDependent.DIRECT_MEMORY_COUNTER`, no-cleaner arena chunks, not in JMX):
    Netty pooled `ByteBuf`s — CQL v4 request/response encoding, C2's encoded responses waiting in the
    outbound buffer (C2 failed with `io.netty.util.internal.OutOfDirectMemoryError`, i.e. this counter).
  - Consequence for the stack: **C2 (concurrent reads) cannot add to the JDK counter**, and the JDK-side
    layers cannot add to the Netty counter. Each counter reaches its endpoint only from its own layers;
    physically they add (process direct footprint up to ≈ 2X). The S1 stack is therefore built on the
    **JDK counter**; C2 is recorded as a separate-counter layer (it reaches X alone at 1,024 outstanding
    3.5 MiB reads — C2 S-A, verified) and is run in this case only if time remains, as a physical-footprint
    arm, not as a contributor to the JDK endpoint.

## 2. Stage 0 — ceiling sheet (JDK counter, defaults, heap 2 GiB)

| Pool | Contract C (default, source) | Reachable multiplicity (bound) | Predicted max U | K basis |
|---|---|---|---|---|
| B0 baseline (idle) | — | — | 50 MiB (C1 r4, measured every arm) | — |
| R receive-queue LARGE frames (stage 1, C1) | Q=4 MiB/conn, E=128 MiB/peer, G=512 MiB (`AbstractMessageHandler.java:411–455`), on-wire bytes | N loaded coordinators; N=8 here (ceiling N·Q+min(G,N·E)=544 MiB) | 544 MiB (K_max), measured U−B0 608–654 incl. pool slack | Σ `using_bytes` (`system_views.internode_inbound`) |
| P networking `BufferPool` | `networking_cache_size` = 128 MiB (min(128, heap/16)) | 1 pool; overflow beyond cap = `allocateDirect` (counted in R when holding frames) | 128 MiB (+ ≈ 8 MiB chunk-cache chunk) | JMX `BufferPool,scope=networking,name=Size` |
| H hint slabs (stage 2, R6-V) | 3 × 32 MiB (`MAX_HINT_BUFFERS`=3, `HintsService.MIN_BUFFER_SIZE` 32 MiB) | independent of #down nodes | 96 MiB | none (no counter; dump `HintsBuffer.slab`) |
| D DOB scratch retained (stage 2, C3/R6-V) | `DOB_MAX_RECYCLE_BYTES` 1 MiB per thread | ≤ 128 NTR + 32 MutationStage + flush/compaction ≈ 165–177 holders | 131–195 MiB (measured C3/R6-V) | none |
| M maintenance overlap (stage 2): flush/compaction scratch, compression buffers | none (transient) | 1 flush writer per disk + `concurrent_compactors` | ≈ 10–40 MiB (estimate; C1 dumps: storage I/O ≤ 3 MiB) | none |
| U1 in-flight DOB fill of large mutations (stage 3) | **none** — `DOB_MAX_RECYCLE_BYTES` trims only at recycle; `max_mutation_size` 16 MiB per mutation | `concurrent_writes` 32 MutationStage threads in `CommitLog.add` (serialize → allocate), each ≈ 1–2 × mutation size (doubling `expandToFit`) | 32 × 15–30 MiB = 480–960 MiB | none |
| C2 encoded responses | per-query only | client outstanding reads | — | **Netty counter, not this sum** |

**Ceilings (JDK counter):**
- Stage 1 (B0+R+P): ≈ 50 + 544 + 128 = **722 MiB** (measured U_peak ≤ 704). Budget 2048 → headroom ≥ 1,326 MiB;
  3982 → ≥ 3,260. At 512 → infeasible to survive (C1: OOM 10/10). Missing multiplicity at 2048: N·Q adds
  4 MiB per extra peer once G is full → **≈ 330 more peers** needed; ≤ 8 reachable here → stage 1 cannot
  reach 2048.
- Stage 2 (+H+D+M): ≈ 722 + 96 + 195 + 40 = **≈ 1,053 MiB** < 2048 → stage 2 can only be a **confirmed
  negative** at 2048 (predicted headroom ≈ 1.0 GiB, ≈ 50 %). Some D is already inside stage 1's U (DOB on
  MutationStage), so the true sum is lower; predicted measured U_peak 750–950 MiB. One confirming stack arm
  + one layer-without-stage-1 arm, then stage 3.
- Stage 3 (+U1, coordinators send 15 MiB mutations instead of 1 MiB): R stays ≤ 544 (same contract, fewer,
  larger messages), plus up to 480–960 MiB in-flight scratch → **≈ 1.5–2.0 GiB** ≥ 2048 at the top of the
  range → **feasible at 2048 only if ≥ ≈ 20 of 32 writers hold a 2×-grown buffer at once while the queue is
  near its ceiling**; infeasible at 3982 (needs ≈ 3.2 GiB more than the ceiling).
- **Heap competes** in stage 3: 32 deserialized 15 MiB mutations on heap (≈ 480 MiB, plus the serialized copy
  in the receive path's deserialization) + memtable `memtable_heap_space` = 512 MiB (heap_buffers) at a
  2 GiB heap. R6-V/U1: at 1–2 GiB direct the 2 GiB heap ran out first. **Prediction: stage 3 at 2048 direct
  ends in a Java heap OOM or heavy GC before the JDK direct counter fills, more likely than a direct OOM.**
  A heap OOM is recorded as such (endpoint in another domain), not as a direct endpoint.

## 3. Protection map (one row per allocation domain)

| Domain | Allocation / owner / release | Local contract | Scope & multiplicity | Aggregate coverage | Lifetime | Budget |
|---|---|---|---|---|---|---|
| R | `InboundMessageHandler$LargeMessage.buffers` (`ShareableBytes` of `BufferPool` chunks or overflow `allocateDirect`), released in `ProcessMessage.run` finally | Q/E/G on-wire bytes, hard | per connection/peer; N=8 | G (512) covers only the reserve part; nothing ties G+N·Q to X | until MutationStage deserializes | JDK direct |
| P | `BufferPool` (networking) chunks | 128 MiB retained cap; overflow is unpooled | 1 | none beyond cap; overflow freed by Cleaner/explicit free | standing | JDK direct |
| H | `HintsBuffer.slab` (`allocateDirect` 32 MiB) | `MAX_HINT_BUFFERS` 3 | global | hard 3 | standing while hints are written (flushed every 10 s, recycled) | JDK direct |
| D | `DataOutputBuffer.scratchBuffer` thread-local | 1 MiB kept per thread | per shared-pool worker (≤ ≈ 177) | none (T × 1 MiB uncounted) | standing | JDK direct |
| U1 | same thread-local, while serializing in `CommitLog.add` (`CommitLog.java:306`) / messaging | none in flight; mutation ≤ 16 MiB | `concurrent_writes` = 32 | none | transient, per write | JDK direct |
| M | flush/compaction write buffers, compressor scratch | none | flush writers, compactors | none | transient | JDK direct |
| heap (reported) | deserialized `Mutation`s, memtable | `memtable_heap_space` 512 MiB (heap/4) | 32 writers | memtable flush | — | heap 2 GiB |

## 4. Topology and workloads (all on pc96; instances and cores as C1 run 4 condition D)

- Build `/mydata/b6/cassandra` (5.0.9, unpatched) read-only. Data/commitlog/hints on a **tmpfs**
  `/mydata/s1/shm` (32 GiB) — environment, keeps disk out of the drain path (disk work paused).
- Instances (loopback, own addresses so nothing collides with other sessions): V 127.0.0.51 (victim, dc v,
  cores 0–7, JMX 7251), F 127.0.0.52 (fast co-replica, dc f, 8 GiB heap, cores 8–15), C1–C8 127.0.0.61–68
  (coordinators, dc c, own no replica of `c1`, cores 16–23), **Dn 127.0.0.59** (dc d, 1 GiB heap, cores 8–15;
  only for the hint layer: replica of keyspace `s1h`, **stopped before load** so the victim writes hints for it).
  Shipped yaml except environment keys (cluster name, addresses, seeds, GossipingPropertyFileSnitch,
  `num_tokens: 1`, `initial_token`, directories, `auto_bootstrap: false`) = C1 condition **D** (hints on,
  default commitlog space). JMX on the victim as in C1.
- Keyspaces: `c1` NTS {v:1, f:1} (stage-1 load via C1–C8, CL=ONE); `s1h` NTS {v:1, d:1} (hint layer: client
  writes **to V as coordinator**, CL=ONE; V applies locally, the Dn replica is down → hint).
- Stage-1 load: `C1Load` (as C1 r4), 1 MiB zero-filled blobs, total 500/s over N coordinators, 90 s.
- Stage-2 layers (added on top, same 90 s window):
  - **H + D layer** = second client to V only, keyspace `s1h`, 1 MiB zero blobs, **100/s**, in-flight 256:
    native-transport threads serialize ≥ 512 KiB mutations (DOB holders up to 128 NTR), V's MutationStage
    applies locally (32 holders), and every write produces a ≈ 1 MiB hint → hint slabs fill to 3 × 32 MiB.
  - **M layer** = `nodetool -p 7251 flush` at load + 20 s and `nodetool -p 7251 compact c1` at load + 40 s
    (deterministic triggers).
  - **P layer** (networking pool at its 128 MiB cap) is already present in stage 1 (C1 dumps: 136 MiB of
    pool chunks); recorded, no extra workload.
  - **C2 layer**: Netty counter (§1) — not stacked on the JDK endpoint; optional physical-footprint arm.
- Stage-3 gap (U1): the coordinators send **15 MiB** mutations (`c1` blobs 15 MiB, total rate 33/s ≈ 500 MiB/s,
  keys mod 200) with the stage-2 layers kept on. B1's release defect (native v5 large requests) is **not
  reachable** on this harness's v4 client and, per B1, plateaus at the pool cap (no excess over P); it is
  recorded as an excluded stage-3 ingredient.

## 5. Arms (heap 2048 MiB; condition D yaml; each from a clean ring; 5 s warm-up, 90 s load, 30 s observe)

| Order | Arm | Stage | Load | Direct | Reps |
|---|---|---|---|---|---|
| 1 | `S1_N8_d2048` | 1 | C1 N=8, 1 MiB, 500/s | 2048 | 1 (+ C1 r4's 0/2 at 2048 reused as stage-1 readings) |
| 2 | `S2_stack_N8_d2048` | 2 | arm 1 + H/D layer + M triggers | 2048 | 1–2 |
| 3 | `L2_layers_N0_d2048` | 2 (layer alone) | H/D layer + M only | 2048 | 1 |
| 4 | `S3_U1_N8_d2048` | 3 | 15 MiB to C1–C8 + H/D + M | 2048 | 1 → 3 if endpoint |
| 5 | control `S3_U1_N1_d2048` (multiplicity off) | 3 | same bytes via 1 coordinator | 2048 | 3 if 4 fails |
| 6 | interventions: `I_gapoff` = arm 2 (1 MiB mutations, gap off); `I_layeroff` = arm 4 without H/D/M | 3 | — | 2048 | 3 each if 4 fails |
| 7 | budget search `S3_U1_N8_d3982` | 3 | as 4 | 3982 | 1–2 |

Heap dumps on OOM (`-XX:+HeapDumpOnOutOfMemoryError`, C1 amendment 4) on stage-3 arms, attributed with
`hprof_direct.py` (JDK-accounted holders: LargeMessage frames, DOB, HintsBuffer, BufferPool chunks).

## 6. Measurements and ledger

1 s sampler (C1Sample): U = JMX direct `MemoryUsed`, heap used, MutationStage pending/active, networking
pool Size/OverflowSize, chunk-cache pool Size, K = Σ `using_bytes`, reserve, throttled/expired; cgroup
`memory.current`/`memory.events`; victim system.log (first `OutOfMemoryError` with stack), GC log. Ledger per
arm: C, K, U per pool where measurable (R: K and U; P: Size; H, D, U1: from dumps at failure only — for
surviving arms only the total U − (B0 + R K + P) residual is attributable), total U_peak, **headroom = X −
U_peak**, missing multiplicity, heap peak and STW share.

## 7. Predictions (before readings)

1. Stage 1 at 2048: survive, U_peak 650–720 MiB, headroom ≈ 1.3 GiB (65 %).
2. Stage 2 at 2048: survive, U_peak 750–1,000 MiB, headroom ≥ 1.0 GiB; hint slabs ≤ 96 MiB, DOB residual
   ≤ 195 MiB; the H/D layer alone peaks ≤ 350 MiB.
3. Stage 3 at 2048: the in-flight DOB of 15 MiB mutations adds ≥ 300 MiB on top of the queue; **endpoint
   uncertain**: most likely a Java heap OOM / heavy GC first (prediction 60 %), direct OOM 30 %, survival 10 %.
   At 3982 MiB: no direct OOM (infeasible by the ceiling sheet).
4. Classification: if a direct OOM occurs at 2048 with K ≤ C for R and the excess in U1 holders, the result
   is **mixed** (convergence R + unprotected in-flight DOB): the endpoint needs an uncovered holder.

## 8. Planned interventions (one per ingredient)

- multiplicity: N=1 coordinator at matched bytes (`S3_U1_N1`);
- layer off: no H/D client, no maintenance triggers;
- gap off: 1 MiB mutations (= stage-2 arm) — the U1 in-flight scratch is then ≤ 1 MiB per thread.

## 9. Deviations / labels

Constraints all at defaults (V6). Environment: loopback colocation, taskset, tmpfs storage, extra down node
Dn for the hint layer (topology), zero-filled blobs. No Byteman, no patches, default timeouts. Any later
deviation will be labelled a supporting deviation (→ `diagnostic`).

## Amendment 1 — 2026-11-16 13:25 EST (before any further reading)

Evidence: the first stage-3 arm (`S3_U1_N8_d2048_r1`) is **invalid**: the 32 GiB tmpfs filled (`No space left
on device` on every instance, then a JVM crash of the victim, no `OutOfMemoryError`): coordinators wrote hints
for the victim's timed-out 15 MiB writes, and V and F each keep up to 8 GiB of commit log. It is excluded
(renamed `INVALID_S3_U1_N8_d2048_r1_tmpfsENOSPC`). Disk exhaustion is out of scope.

1. **Environment change:** the hints directory of every non-victim instance (F, Dn, C1–C8) moves to local disk
   `/mydata/s1/disk/<n>/hints`; the victim keeps all its storage on the tmpfs. Applies to all following arms.
   (Stages 1–2 already ran with the old layout; their hint volume on the tmpfs stayed ≤ 9 GiB, no ENOSPC.)
2. **Budget dial for stage 3 (V7 argument).** `cassandra-env.sh` resolves heap = ½ RAM and direct = ¼ RAM
   (below the caps). A node whose *automatic* heap is our 2 GiB (4 GiB RAM) gets **direct = 1024 MiB**. So with
   heap 2 GiB the auto-consistent direct budget is **1024 MiB** (3982 MiB is the auto value only for a 15.55 GiB
   node, whose heap would be 7965 MiB). Search order: 2048 → 1536 → 1024 (one arm each), then the largest
   failing budget B* gets the repeats. At B*: stage-3 endpoint ×3; matched controls ×3 each:
   `N1` (one coordinator, same 15 MiB × 33/s = multiplicity intervention) and `gapoff` (= stage-2 stack, 1 MiB
   mutations, 500/s = same bytes/s); `layeroff` (stage 3 without H/D client and maintenance) ×≥ 1 if time.
3. Prediction (from the invalid arm's pre-ENOSPC samples, which reached U = 1,203 MiB with K = 540 MiB and all
   32 MutationStage threads active): at 2048 MiB **survive** (headroom ≈ 0.8 GiB); a direct OOM is expected
   at ≤ 1,280 MiB. At 1024 MiB: OOM likely; gap-off (stage 2 peaked at 772 MiB) predicted to survive at 1024.

## Amendment 2 — 2026-11-16 13:57 EST (before the reading of `S3_U1_N8_d768_r1` and all later arms)

Evidence so far (stage 3, one arm each): 2048 survive (U_peak 1,368), 1536 survive (1,395), **1024 and 896
survive while touching the cap** (U_peak 1,024 / 894; 85 `System.gc()` Full GCs at 1024 = `Bits.reserveMemory`
reclaiming unreachable direct buffers and retrying). So above ≈ 900 MiB the JDK counter's own GC-and-retry
rescues the allocation: much of the stage-3 excess is *garbage awaiting its Cleaner* (grown DOB scratch
dropped at recycle), not live memory. The endpoint needs **live** direct > X: the stage-1 live floor
(B0 50 + K ≤ 544 + pool 128 ≈ 720 MiB) plus the live in-flight DOB of the 32 writers.

Plan change: **B* = 768 MiB** (provisional; ≥ 512 MiB standing rule; below the 1024 MiB auto-consistent value,
so a failure here is labelled like C1's). Interleaved, each from a clean ring: `S3_U1_N8_d768` r1–r3
(endpoint), `G_gapoff_N8_d768` r1–r3 (V2 matched control = stage-2 stack, same layers, 1 MiB mutations, 500/s
= more bytes/s than stage 3 delivers), `I_N1_d768` r1–r3 (V4 intervention: multiplicity off, same 15 MiB load
via one coordinator). If `S3_U1_N8_d768_r1` survives, the queue stops after it and 640 MiB (C1's largest failing
stage-1 budget) is tried to state whether stage 3 moves the boundary at all. Prediction: S3 at 768 fails ≥ 2/3;
gap-off survives (stage-2 peak 772 MiB was at 2048, so it is borderline: a failure of gap-off at 768 would mean
stage 2 alone already reaches 768 and stage 3 is not needed there); N1 survives 3/3 (K ≤ 132 MiB).

## Amendment 3 — 2026-11-16 14:10 EST (before the readings of the two arms it adds)

`S3_U1_N8_d768_r1` reached the endpoint (direct OOM, first thread MutationStage in `CommitLog.add` →
`DataOutputBuffer.expandToFit`), so the queue of amendment 2 continues. Appended after it (time permitting):
`L_layeroff_N8_d768_r1` (stage 3 without the stage-2 layers: no hint/DOB client, no flush/compact — the
"layer off" ingredient, n=1) and `S3_U1_N8_d832_r1` (boundary between 768 fail and 896 survive, n=1).
Prediction: layer-off fails too (the stage-2 layers added only ≈ 90 MiB at 2048), so the layers are not
necessary at 768; 832 fails or survives with similar likelihood.

## Amendment 4 — 2026-11-16 14:28 EST (governs arms started from 14:29 on, i.e. `G_gapoff_N8_d768_r2` and later; no reading of them yet)

1. `I_N1_d768_r1` is **invalid**: the victim was killed by its own 12 GiB *safety* scope (`CONSTRAINT_MEMCG`,
   dmesg 14:21:38; anon-rss 3.4 GB) because the victim's tmpfs files (commit log + 7.9 GB of `s1h` hints — with
   one coordinator the hint layer ran at 87/s instead of ≈ 50/s) are charged to the scope. Same failure mode as
   C1 run 4's `INVALID_A0` arm. The safety scope is raised to **44 GiB** (still non-binding: tmpfs ≤ 32 GiB +
   heap 2 GiB + direct ≤ 2 GiB + JVM overhead), environment only. The arm is re-run as `I_N1_d768_r1b`.
2. `G_gapoff_N8_d768_r1` ran correctly but its arm script's tail broke after an in-place edit of `arm.sh`
   (14:18, adding a copy of peer logs); its samples, V logs and client logs are complete, its outcome line was
   written by hand. `arm.sh` is not edited again while an arm runs.

## Amendment 5 — 2026-11-16 14:58 EST (before the readings of the two arms it adds)

`L_layeroff_N8_d768_r1` survived (n=1). Two more layer-off repeats are appended after `I_N1_d768_r1b`
(`L_layeroff_N8_d768_r2`, `_r3`) so that the layer-off ingredient has n=3 like the other two interventions, if they
finish by 15:40. Prediction: survive (borderline: U touched 766 of 768 MiB in r1).
