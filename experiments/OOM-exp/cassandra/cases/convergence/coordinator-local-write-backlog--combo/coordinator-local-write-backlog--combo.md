# S2 — coordinator's own local writes queue without bound on `MutationStage` (heap combo)

**Campaign row:** S2 (S = combo: convergence multiplicity → stacked layers → bypass accounting gap, per
[`combo-playbook.md`](../../../../combo-playbook.md)). **Sources:** B6 (B = bypass: internode queue on-wire vs heap
mismatch), B7 (bypass: cache weigher overhead), C2 (C = convergence: concurrent reads), R3/R4 (R = recheck of
pre-protocol cases). **Domain:** Java heap of the victim. **Stages run:** 1 (multiplicity = offered write load),
2 (key + counter caches filled to their default caps, `nodetool flush` overlap), 3 (B6 tiny-cell map payload).
**Regime:** default constraints. **Source:** Cassandra 5.0.9, builds `apt140:~/cassandra-b1` (victim) and
`apt149/apt138:~/cassandra-c1` (same yaml, md5 `714ee9bf…`), read-only. **Run:** S2 run 1, 2026-11-16
12:55–15:35 EST, one agent; design [`design/S2-design.md`](design/S2-design.md) (written before readings,
amendments A1 13:16, A2 14:18, A3 14:43, A4 14:45 EST). **Run 2** (2026-11-16/17, Utah m400 **aarch64**, `ms0640` victim,
`ms0604`/`ms0611` replicas, `ms0617` client): equal-heap RF=3 ring; design [`design/S2-run2-design.md`](design/S2-run2-design.md),
run file kept verbatim in [`history.md#run-2`](history.md#run-2), conditions G1/G2 below.

> **Scope (researcher, 2026-11-17).** A faster replica is **not** required. Run 2 found the same OOM in an
> equal-heap RF=3 ring (G1, all three nodes 2 GiB) and with two faster peers (G2), 3/3 each, on aarch64; the
> researcher accepted both as `verified-OOM · deployment` on 2026-11-17 and decided that an x86 repeat is not needed.
> Verified for a coordinator that is also a replica and acks after another replica at CL=ONE. *(Superseded scope,
> 2026-11-16: condition A was verified for a replica faster than the victim; with equal 2 GiB heaps the victim had
> survived 1/1 on x86, §3.5.)*

| Condition | Status (protocol *Verification status*) |
|---|---|
| **A — victim heap 2 GiB** (other replica 8 GiB), blob 11 000 B, 8 × 256 client in flight, CL=ONE, uncapped, no fault | **`verified-OOM · deployment`** (unprotected accumulation; **Researcher's review 2026-11-16:** promoted, the uncapped CL=ONE burst accepted as a workload within guardrails; moved from `candidates/` to `convergence/`). As filed: `candidate` — V1–V5 met (heap OOM 3/3 + 1 earlier arm; control 3/3 survive; intervention 3/3 survive; dumps), V6 met, V7 met (2 GiB, standing rule); **pending the researcher's review** of the interpretation (unprotected accumulation vs. accepted overload behaviour) and the topology note (§4; equal-heap replica survived 1/1). Proposed: `verified-OOM · deployment` (unprotected). |
| B — same at 4 GiB | `candidate`: stage 1 alone OOM 1/3 (survivors 82.5 %, 96.4 % live); **with stage-2 layers (default caches filled + flush) OOM 2/3**, third at 99.1 % live (§3.4); no control/intervention at 4 GiB |
| C — same at 8 GiB (stage 1, 2, 3) | survived 1/1 each (35 %, 36 %, 57.5 % post-Full-GC live): not a failing budget in 90 s of load |
| A on aarch64 (run 2: same topology and load on Utah m400) | reproduces A: heap OOM 3/3 (+ 1 shakedown), CL=LOCAL_ONE 0/3 ([run 2](history.md#run-2)); status of A unchanged |
| **G1 — RF=3 single DC, all three heaps 2 GiB** (run 2, aarch64), blob 11 000 B, 8 × 256 in flight to V, CL=ONE, uncapped, 90 s | **`verified-OOM · deployment`** (unprotected accumulation; **researcher's review 2026-11-17**): heap OOM 3/3, ≈ 63.4 k queued `Mutation`; rate cap 1 500/s 0/3; CL=ALL 0/3 with 2.4× the completed writes; V1–V7 in §4 |
| **G2 — RF=3, victim 2 GiB, two 8 GiB peers** (run 2, aarch64) | **`verified-OOM · deployment`** (unprotected accumulation; researcher's review 2026-11-17): heap OOM 3/3; CL=ALL 0/3; rate cap 0/3 |
| G1 at 4 GiB (all three nodes; run 2) | `candidate`: heap OOM 0/6, GC service loss 3/6 (97–98 % live); the backlog drains after the burst; no control or intervention at 4 GiB |
| Equal-heap RF=2, 300 s load (run 2, aarch64) | `candidate`: heap OOM 3/3 within 92 s; CL=LOCAL_ONE 0/3; no matched rate-cap control on this topology (V2). Run 1's x86 arm survived 1/1 at 81 % |

## Summary

- **Conclusion:** a Cassandra node with a 2 GiB heap (all constraints, timeouts and thread counts at their
  defaults) that coordinates CL=ONE writes for a table it replicates, alongside a replica that acknowledges faster,
  dies of **Java heap OOM 3/3** (plus 1/1 in the first arm) within 28–210 s of the start of a write burst of ≈ 13–17 k
  writes/s; the client keeps only 2 048 writes in flight. The heap at the OOM is ≈ 90 % queued local writes:
  ≈ 61 500 `Mutation`s each held by a pending `LocalMutationRunnable` on `MutationStage`. A client capped at
  2 000 writes/s survives 3/3 (14–17 % live), and the same uncapped load at **CL=LOCAL_ONE** survives 3/3 (39–46 %
  live) with *higher* completed throughput. At 4 GiB the same load OOMs 1/3 (others 82.5 %, 96.4 % live);
  8 GiB survives a 90 s burst. Stacking the default key/counter caches filled to their caps and a flush
  (stage 2) raises the 4 GiB rate to **2/3** (third arm 99.1 % live); at 8 GiB neither stage 2 nor the B6
  tiny-cell payload (stage 3) made it fail (35.5 %, 57.5 % live).
- **Root cause (unprotected accumulation):** the coordinator submits its own replica write to `MutationStage`,
  whose queue is unbounded, and answers the client as soon as **any** replica acknowledges (CL=ONE). When the
  other replica is faster, the client request, its slot in the client's in-flight window and its
  `native_transport_max_request_data_in_flight` charge are all released while the local write is still queued.
  So no client-side or native-transport limit bounds the local backlog, nothing charges it, and an expired local
  write is not dropped but resubmitted as a hint that applies the same mutation on the same stage
  (`StorageProxy.java:2633–2652`). The backlog grows with offered rate − local apply rate, persists after the
  client stops (one arm OOMed 120 s after its load ended), and fills the heap. With an equal-heap (2 GiB) replica
  V survived 1/1 at 81 % live: the faster replica is part of the condition. Not the stage-1 holder the design predicted (B6 callbacks to a stalled
  replica); see amendment A1.
- **Combo result:** the endpoint is reached at **stage 1** at 2 GiB (the playbook's stop rule); stage 2 and 3 were
  run only at budgets where stage 1 survives (4 and 8 GiB). Stage 2 moves the 4 GiB boundary (1/3 → 2/3); the B7
  cache overshoot is part of that layer, so the 4 GiB stage-2 result is tagged **mixed** (candidate); the 2 GiB
  endpoint needs no accounting gap (not mixed).

- **Run 2 (aarch64, 2026-11-16/17):** the faster replica is not part of the condition. In an RF=3 ring with all
  heaps 2 GiB (G1) the coordinator dies of heap OOM 3/3 with the same holder and count (≈ 63.4 k queued local
  `Mutation`s); the equal-heap replicas stay ≤ 25 % live with ≤ 77 pending. The coordinator is itself the slowest
  replica (CPU-bound, 93 % vs ≈ 50 % on the replicas, one reading); its copies to the peers pass bounded internode
  queues and are acked first, while its own copy waits on the unbounded stage and 33–64 k expired local copies per
  arm are re-queued as hints. CL=ALL survives 3/3 with 2.4× the writes; a 1 500/s cap 3/3. Details in
  [`history.md#run-2`](history.md#run-2).

## 1. Ceiling sheet, protection map, configuration

**Stage-0 ceiling sheet** (before readings): [`design/S2-design.md`](design/S2-design.md) §2. It predicted the
stage-1 holder to be the coordinator's write callbacks to a *stalled* replica (B6 shape; bound rate × 2 s × heap
size per mutation) and stage 1 with blob payload to stay ≈ 0.9 GiB below a 2 GiB heap. Arm 1 refuted the
holder: amendment A1, written before any further reading.

**Protection map of the holder found** (pinned 5.0.9 source, `systems/cassandra/source/`):

| Field | Evidence |
|---|---|
| Allocation and ownership | The CQL `INSERT` is decoded into a `Mutation` (+ `PartitionUpdate`, cell, the blob value's `byte[]`) on a `Native-Transport-Requests` thread. `StorageProxy.performLocally` (`StorageProxy.java:1674–1690`) wraps the local apply in a `LocalMutationRunnable` (anonymous `StorageProxy$4`, identified with `javap`) and submits it to `Stage.MUTATION` (`concurrent/Stage.java:46`, `concurrent_writes` = 32 threads, unbounded queue). The runnable holds the `Mutation` and the `WriteResponseHandler`. The same mutation is serialized and sent to the other replica R. |
| Local contract | None on the stage queue. Client-facing limits: `native_transport_max_request_data_in_flight` = heap/10 (`DatabaseDescriptor.java:649–652`; 204.8 MiB at 2 GiB), per IP heap/40, charged per CQL request and **released when the response is flushed** (`CQLMessageHandler.java:500–507`); `native_transport_max_threads` 128; the client's in-flight window (2 048 here). |
| Scope and multiplicity | One runnable per accepted write whose local apply has not run. At CL=ONE the response goes out when either replica acks; R (8 GiB, otherwise idle) acks first, so request, in-flight bytes and client slot are released while V's runnable stays queued. Bound: offered rate × residence time only. |
| Aggregate coverage | Outbound queue to R (on-wire 4 + 128 + 512 MiB, `OutboundConnection.java:330`) covers only the copy sent to R. The memtable pool (`memtable_heap_space` = ¼ heap) covers only applied data (measured 143–167 MiB at 2 GiB, below its 512 MiB cap: the stage is not blocked on memtable space). `max_hints_in_progress` (128 × cores) is checked only before sending (`StorageProxy.java:1505,1585–1598`). No control charges the local `MutationStage` backlog. |
| Lifetime | Until a `MutationStage` thread runs it. An expired local runnable (deadline = `write_request_timeout` 2 s) is **resubmitted** as a `HintRunnable` that applies the same mutation, again on `Stage.MUTATION` (`StorageProxy.java:2633–2652`, `submitHint` `:2822–2828`): the timeout does not shed the backlog. |
| Budget | Java heap of V (`-Xmx`). |

C/K/U: **C = none** (unprotected accumulation; implicit bound offered rate × residence time, not enforced),
**K = none** (`MutationStage` pending is a gauge), **U** = class histogram of the OOM dump and post-Full-GC live
heap from the GC log.

**Stage-2/3 layers** (design §2): memtable C = ¼ heap (K = memtable data size, 143–167 MiB at 2 GiB, 324 MiB at
4 GiB, 649–652 MiB at 8 GiB, never at its cap); key cache C = 100 MiB, counter cache C = 50 MiB (K = 100 / 50 MiB
at fill, entries 1 310 720 / 468 114; real heap ≈ 214 / 90 MiB by B7's measured 2.14× / 1.80×, not re-measured
here); B6 map payload 10.8 KiB on-wire ≈ 213 KiB heap per mutation (B6 run 1).

**Configuration and budget audit.**

| Item | Value | Class |
|---|---|---|
| Source / build | 5.0.9, existing builds, unmodified; client = Java driver 3.12.1 (`S2Load.java` = B6 run-4 `B6Load` + `-Dcl`; `S2CacheFill.java` = B7 `CacheFill` + `-Dhost/-Dks`) | — |
| OS / JDK / GC | Ubuntu, kernel 5.15 (apt r320: 8 cores / 16 threads, 15 GiB RAM, swap as provisioned), OpenJDK 11.0.33, shipped G1 options (`jvm11-server.options`), `-Xms = -Xmx`, `MaxDirectMemorySize` auto (3 982 MiB at 2 GiB) | environment |
| Topology | V `apt140` dc `c` (coordinator for every request + replica), R `apt149` dc `r` (8 GiB heap), client `apt138`; keyspace `b6` `NetworkTopologyStrategy {c:1, r:1}`; 10 GbE experiment LAN | environment (heterogeneous heaps: see §4) |
| yaml diffs (per instance `yaml.diff`) | cluster name, `num_tokens: 1` + `initial_token`, listen/rpc address, seed, GossipingPropertyFileSnitch, data/commitlog/hints/saved_caches dirs, `auto_bootstrap: false` | environment |
| Constraints (V6) | all at shipped default, resolved at V's heap: `memtable_heap_space` ¼ heap, `memtable_allocation_type: heap_buffers`, key/counter cache auto (100 / 50 MiB at ≥ 2 GiB), internode queue capacities, `native_transport_max_request_data_in_flight` heap/10, `concurrent_writes` 32, `write_request_timeout` 2 s, hints **on** | default |
| Budget (V7) | V heap 2 GiB (ideal), searched to 4 and 8 GiB; node auto heap would be ≈ 7.5 GiB | acceptable (standing rule) |
| R's disk | on a dm-delay device (delay 0 in every counted arm; 30 s only in `st1-blob-r1`, which failed before the stall began) | environment |
| Workload | blob 11 000 B or map 1 000 × int cells; 8 sessions × 256 in flight to V only; CL=ONE (intervention LOCAL_ONE); rate cap 2 000/s in the control; load 90 s (150 s in arm 1) | experimental variable |
| Instrumentation | `jcmd GC.heap_info` (no forced GC), `cqlsh` system views, `nodetool info/tpstats/tablestats` every ≈ 5 s on V; heap dump on OOM (shipped `HeapDumpOnOutOfMemoryError`); one dump parsed on apt140 pinned to core 15 at nice 19 during `E-blob-8G-r1` | disclosed |

## 2. Design per stage

Design and amendments: [`design/S2-design.md`](design/S2-design.md). Harness: [`harness/`](harness/) —
`arm.sh` (controller on pc96; clean start of V and R from the build's conf, schema, optional cache fill
1.6 M inserts + flush + 1.5 M distinct reads + 550 k counter updates, sampler, load, optional `nodetool flush b6`
at t = 85 s, 60 s observation, OOM dump → `hprofhist.py`, stop, copy back), `ctl.sh`, `sample.sh`, `client.sh`,
`slowdisk.sh`, `batch1–5.sh`, `summ.sh`, `gcpeak.sh` / `gcwin.py` / `hprofhist.py` (B6 run 3/4).

Endpoints: heap OOM of V (`HeapDumper` + `ReportJavaOutOfMemory` safepoints in gc.log, dump; Cassandra's own
`system.log` is starved in most OOM arms, the JVM's stdout is closed after daemonizing); GC service loss (protocol
default: ≥ 90 % STW over ≥ 60 s, all pauses, `gcwin.py`).

| Ingredient | Intervention (planned A1) | Arm |
|---|---|---|
| offered write load (multiplicity of queued local writes) | cap the client at 2 000 writes/s (matched control) | `ctl-rate-2G` |
| CL=ONE ack from the faster replica releasing every upstream bound | CL=LOCAL_ONE (the local write must complete before the client slot is released) | `int-lone-2G` |
| stacked layers | stage 2 on / off at the boundary heap | `st2-blob-4G` vs `E-blob-4G` |
| B6 gap | map vs blob at 8 GiB | `st3-map-8G` vs `st2-blob-8G` |

## 3. Results (ledger per stage)

Raw per-arm data (copied back): `pc96:/mydata/s2-evidence/runs/<arm>/` (arm.log, `V/` GC logs, system.log,
samples, outcome, dump histogram; `client/load.log`; `R-outcome.txt`). Committed excerpts: [`logs/`](logs/).
Headroom = heap − max post-Full-GC live. "Queued" = `Mutation` count in the OOM dump (U), or the sampler's max
`MutationStage` pending for survivors.

### 3.1 Condition A — 2 GiB, stage 1 (blob), endpoint, control, intervention

| Arm | n | Outcome | Max live after Full GC | Worst-60 s STW | Service loss | Queued / U at OOM | Completed writes |
|---|---|---|---|---|---|---|---|
| `st1-blob-r1` (first arm, stall armed at t = 20 s but GC spiral began at t ≈ 4–14 s) | 1 | **heap OOM** ≈ 28 s into load | 2 010 MiB (98.1 %) | 57 % | no | 61 923 `Mutation` / `StorageProxy$4` / `WriteResponseHandler`; `byte[]` 1 836 MiB of 2 046 MiB | 108 375 |
| `E-blob-2G` r1 | | **heap OOM** ≈ 41 s into load | 2 014 MiB (98.3 %) | 33 % | no | 61 645 `Mutation`, 61 502 `StorageProxy$4`; `byte[]` 1 834 / 2 057 MiB | 201 246 |
| `E-blob-2G` r2 | | **heap OOM** ≈ 71 s into load, after service loss | 2 010 MiB (98.1 %) | 99 % | **yes** (104 s window, 95 s paused) | 61 491 | 107 968 |
| `E-blob-2G` r3 | **3/3** | **heap OOM** ≈ 210 s after load start (120 s after the client stopped), after service loss | 2 015 MiB (98.4 %) | 99 % | **yes** (229 s, 216 s paused) | 61 186 / 61 159 | 138 965 |
| `ctl-rate-2G` r1–r3 (2 000 writes/s) | 0/3 | survived | 279–350 MiB (13.6–17.1 %) | 1 % | no | pending 0 | 178 263–178 451, 0 errors |
| `int-lone-2G` r1–r3 (CL=LOCAL_ONE) | 0/3 | survived | 802–942 MiB (39.2–46.0 %) | 3 % | no | pending ≤ 704 | 295 070–310 415 (≈ 3.3 k/s), 1.8–2.4 % write timeouts |

Endpoint client rate in the first 5 s: 13.2–16.6 k writes/s, falling to 0 within 15–20 s as GC takes over. At the
OOM: queued local writes ≈ 30 KiB of heap each (`byte[]` ÷ `Mutation` = 29.8–30.5 KiB; on-wire 10.8 KiB, so
≈ 2.8× — blob, not the tiny-cell gap), ≈ 61 500 queued ≈ 1.8 GiB ≈ 90 % of the heap. Memtable K 143–167 MiB, caches
empty, outbound to R 0–0.6 MiB pending at the samples (it overflowed at 130 MiB 4 s into `st1-blob-r1`, drops
logged once). Sampled `MutationStage`: 32 active, up to 29 997 pending, `Native-Transport-Requests` 128 active /
≈ 1 920 pending (= the client window): the backlog behind the stage is ≈ 30× the client's in-flight window.

**Ledger, stage 1 at 2 GiB (endpoint arms):** C none · K none · U ≈ 1.8 GiB queued mutations + 0.16 GiB memtable ·
headroom 0 (OOM) · GC: service loss in 2/3.

### 3.2 Heap search (stage 1, blob)

| Heap | n/N OOM | Max live after Full GC (survivors) | Worst-60 s STW | Queued (dump / max pending) | Headroom |
|---|---|---|---|---|---|
| 2 GiB | 3/3 (+1) | — | 33–99 % | ≈ 61 500 | 0 |
| **4 GiB** | **1/3** (r1, ≈ 170 s after load start, after 101 s of service loss) | r2 3 380 MiB (82.5 %), r3 3 949 MiB (96.4 %) | r1 99 %, r2 14 %, r3 28 % | r1 dump: 129 394 `Mutation`, `byte[]` 3 743 of 4 128 MiB; r2/r3 pending ≤ 121 904 / 131 812 | 0 / 17.5 % / 3.6 % |
| 8 GiB | 0/1 | 2 894 MiB (35.3 %) at its two Full GCs (both at a full heap after evacuation failure, 8 175 → 2 758 MiB) | 4 % | pending ≤ 25 620 | 64.7 % |

Largest failing heap: **4 GiB (1/3)**; reproducible (3/3): 2 GiB. Missing multiplicity at 8 GiB: headroom 5.2 GiB ÷
30 KiB ≈ 180 k more queued writes, against ≤ 26 k observed in a 90 s burst (the backlog grows only while offered
rate > apply rate; a longer burst was not tested).

### 3.3 Stack at 8 GiB (stage 2, stage 3)

| Arm | Layers | Outcome | Max live after Full GC | Worst-60 s STW | Max pending | Memtable K | Caches K | Completed |
|---|---|---|---|---|---|---|---|---|
| `E-blob-8G-r1` | stage 1 | survived | 2 894 MiB (35.3 %) | 4 % | 25 620 | 649 MiB | empty | 451 610 |
| `st2-blob-8G-r1` | + key/counter cache filled (100 / 50 MiB, 1.31 M / 468 k entries) + flush at 85 s | survived | 2 910 MiB (35.5 %) | 3 % | 27 402 | 652 MiB | 100 / 50 MiB | 452 327 |
| `st3-map-8G-r1` | + map payload (B6 gap, ≈ 213 KiB heap per mutation) | survived | 4 711 MiB (57.5 %) | 52 % | 11 655 | 114 MiB | 100 / 50 MiB | 98 311 (≈ 1.1 k/s) |

Stage 2 adds ≤ 16 MiB post-GC live at 8 GiB here (the two Full GCs fall at different points of the backlog; B7's
≈ 0.3 GiB real cache heap is not resolvable from two samples). Stage 3 raises live heap by ≈ 1.8 GiB and STW to
52 % with only ≈ 1/20 of the blob write rate: the map payload is applied ≈ 20× slower *and* weighs ≈ 7× more per
queued mutation; 11 655 queued × 213 KiB ≈ 2.4 GiB. Headroom 42.5 %. No layer closed the gap at 8 GiB.

### 3.4 Stack at the boundary heap 4 GiB (stage 2, blob)

Amendment A3 (written before these readings): stage 2 = caches filled to their default caps (K = 100 / 50 MiB,
1 310 720 / 468 114 entries, all three arms) + `nodetool flush b6` at t = 85 s, blob, 4 GiB. Compared with stage 1
alone at 4 GiB (`E-blob-4G` r1–r3).

| Arm | Layers | Outcome | Max live after Full GC | Worst-60 s STW | Service loss | Queued (dump / max pending) | Completed |
|---|---|---|---|---|---|---|---|
| `E-blob-4G` r1–r3 | stage 1 | **OOM 1/3** | 99.1 % / 82.5 % / 96.4 % | 99 / 14 / 28 % | 1/3 | 129 394 / ≤ 121 904 / ≤ 131 812 | 434 864–466 447 |
| `st2-blob-4G-r1` | + caches + flush | survived | 4 059 MiB (99.1 %) | 48 % | no | ≤ 84 235 | 451 465 |
| `st2-blob-4G-r2` | + caches + flush | **heap OOM** (`HeapDumper` at uptime 514 s, ≈ 270 s after load start; dump 4.59 GB written; JVM still in back-to-back Full GCs when the arm stopped it 5 min later) | 4 065 MiB (99.2 %) | 99 % | **yes** (369 s, 339 s paused) | dump 114 469 `Mutation`, 114 277 `StorageProxy$4` | 423 701 |
| `st2-blob-4G-r3` | + caches + flush | **heap OOM** (`HeapDumper` 765 s, `ReportJavaOutOfMemory` 794 s, killed) | 4 062 MiB (99.2 %) | 99 % | **yes** (328 s, 326 s paused) | dump 114 953 `Mutation`, 114 906 `StorageProxy$4` | 422 912 |

**Stage-2 ledger at 4 GiB (dumps r2/r3):** heap 4 193–4 197 MiB shallow; queued mutations ≈ 114.5 k × ≈ 30 KiB
≈ 3.3 GiB (C none, K none); caches visible as `PSMW` (Caffeine node) 101.8 MiB + `KeyCacheKey` 60.0 MiB +
`CounterCacheKey` 21.4 MiB, plus their key `byte[]`s and values (B7: ≈ 214 + 90 MiB real for K = 100 + 50 MiB:
U/K ≈ 2.0); memtable K ≈ 321–325 MiB (C = 1 GiB). Headroom 0 (r2, r3), 0.9 % (r1). **Stage 2 raises the 4 GiB
failure rate from 1/3 to 2/3 and every arm to ≥ 99 % live**; the layers (≈ 0.3 GiB real caches, of which ≈ 0.15
GiB is the B7 weigher gap) take the headroom the stage-1 survivors had (3.6–17.5 %). n = 3 each: the difference
is suggestive, not established.

### 3.5 Equal-heap replica (amendment A4)

| Arm | Change | Outcome | Max live after Full GC | Worst-60 s STW | Max pending | Completed | R |
|---|---|---|---|---|---|---|---|
| `Eeq-blob-2G-r1` | R heap 2 GiB (= V), otherwise condition A | **survived** | 1 658 MiB (81.0 %) | 8 % | 43 434 | 330 399 (3 439 write timeouts) | max after Full GC 557 MiB (27 % of 2 GiB) |

n = 1. With equal heaps V still built a 43 k-write backlog and reached 81 % live, but did not OOM in this arm:
the replica's spare capacity (here: a 4× larger heap, hence 4× larger memtable pool and fewer flushes) is part of
the condition. Not repeated (time).

### 3.6 Run 2 — equal-heap RF=3 ring (aarch64)

Full run file, arm tables and amendments R2-A1…A5: [`history.md#run-2`](history.md#run-2); harness
[`harness-run2/`](harness-run2/), excerpts [`logs-run2/`](logs-run2/). Never pooled with run 1's x86 arms.

| Condition (2 GiB victim unless noted) | Heap OOM | Max live after Full GC | Control / intervention |
|---|---|---|---|
| A on aarch64 (V 2 GiB, R 8 GiB, RF=2) | 3/3 (+1 shakedown) | — | CL=LOCAL_ONE 0/3 |
| **G1** RF=3, all 2 GiB | **3/3** | 99.1–99.3 %; service loss 2/3 | CL=ALL 0/3 (≈ 30 % live, 2.4× writes); rate cap 1 500/s 0/3 (≤ 9 %) |
| **G2** RF=3, two 8 GiB peers | **3/3** | ≈ 99 %; service loss 2/3 | CL=ALL 0/3 (26–30 %); rate cap 0/3 (≤ 9.7 %) |
| G1 at 4 GiB (all nodes) | 0/6 | 97.1–98.0 %; service loss 3/6 | — |
| Equal-heap RF=2, 300 s | 3/3 (66–92 s) | — | CL=LOCAL_ONE 0/3 |

## 4. Conclusion

**Stage reached:** the endpoint at **stage 1** (2 GiB 3/3, 4 GiB 1/3). Stage 2 (default caches at their caps +
flush) at 4 GiB: 2/3 (+1 at 99.1 % live). Stage 2 and stage 3 (B6 gap) did not make 8 GiB fail in a 90 s burst
(headroom 64.5 % and 42.5 %).

**Attribution.** The OOM needs (a) an offered write rate above the victim's local apply rate (a 2 000/s cap
removes it 3/3) and (b) a CL whose acknowledgement does not wait for the coordinator's own write: CL=LOCAL_ONE at
the same uncapped load removes it 3/3 and completes **more** writes (≈ 300 k vs 108–201 k before the OOM), so the
intervention does not work by stopping useful work. The holder is the coordinator's queued local writes
(`LocalMutationRunnable` → `Mutation`), ≈ 90 % of the heap at the OOM. No accounting gap of B6 or B7 is needed
(blob payload, caches empty): **not mixed**. Classification: **unprotected accumulation** — no control charges
`MutationStage` backlog; the bounds that look like they cover it (client in-flight window, native-transport
in-flight bytes, `write_request_timeout`) are released or re-armed (expired local writes are resubmitted as hints
on the same stage). Interpretation: a sizing/validation gap (load shedding of local writes depends on the
coordinator's own ack) with a likely implementation issue (the expired-local-write → hint resubmission keeps the
backlog instead of shedding it). JIRA not checked yet.

**V1–V7 (condition A, 2 GiB):**

| | Requirement | Evidence | Met |
|---|---|---|---|
| V1 | ≥ 3 failing runs | `E-blob-2G` r1–r3 heap OOM 3/3 (+ `st1-blob-r1`) | yes |
| V2 | matched control ≥ 3 | `ctl-rate-2G` r1–r3 survive (same build, heap, payload, client; offered rate 2 000/s) | yes (control differs in offered rate) |
| V3 | U independent of K | dump histograms (4 dumps at 2 GiB, 1 at 4 GiB), post-Full-GC from GC logs; K: none exists for the holder | yes |
| V4 | intervention ×3 | CL=LOCAL_ONE 3/3 survive with higher throughput; rate cap 3/3 | yes |
| V5 | initiating failure | `HeapDumper`/`ReportJavaOutOfMemory` safepoints in gc.log per arm; dumps → histograms with the holder; `OnOutOfMemoryError=kill -9` fired (V dead) | yes (thread/stack of the first error not captured: Cassandra's log starved, JVM stdout closed) |
| V6 | default constraints | all defaults resolved at the heap; hints on | yes |
| V7 | acceptable budget | 2 GiB heap (standing rule ≥ 512 MiB, 2 GiB ideal); 4 GiB 1/3 | yes |

**V1–V7 (G1 and G2, run 2, 2 GiB):** V1 heap OOM 3/3 each; V2 matched rate-cap control (1 500/s) 0/3 each; V3 dump
histograms 3/3 each (≈ 62–63.4 k `Mutation` = `StorageProxy$4` = `WriteResponseHandler`), no K exists; V4 CL=ALL 0/3
each; V5 `HeapDumper`/`ReportJavaOutOfMemory` safepoints, `OnOutOfMemoryError=kill -9` fired, first error logged in
G2 r1/r2 (`Native-Transport-Requests-69`, `Java heap space`); V6 all defaults, hints on; V7 2 GiB heap. Evidence:
[`history.md#run-2`](history.md#run-2) §4. **Researcher's review 2026-11-17:** G1 and G2 accepted as
`verified-OOM · deployment` (unprotected accumulation), added as conditions of this case; no x86 repeat needed.

**Researcher's review 2026-11-16:** condition A promoted to **`verified-OOM · deployment`** (unprotected accumulation); the workload is accepted. Filed in `convergence/`. Proposal as filed: condition A meets V1–V7 as measured. Filed in `candidates/` as **`candidate`** pending the
researcher's review because (1) the protocol requires the workload to stay within documented guardrails, and
whether an uncapped CL=ONE write burst above a node's apply rate is an accepted workload or documented overload is
a judgement call; (2) the topology has heterogeneous replica heaps (R 8 GiB), which makes R the faster replica;
with equal 2 GiB heaps V survived 1/1 at 81 % live (§3.5), so the faster replica is part of the condition and
the matched control would ideally be the equal-heap ring (×3, not run); (3) the stage-1 holder differs from the S2 design's, so the S2 combo question
(B6 callback retention + layers) is answered only for 8 GiB. If accepted: `verified-OOM · deployment`
(unprotected accumulation), filed in `convergence/` (C1-like multiplicity of queued writes) — the researcher's call.

**Limits.** One topology (2 nodes, RF 2 across 2 DCs, client to V only); 90 s bursts (longer bursts at 8 GiB
untested); R heap 8 GiB (equal heaps: 1 arm, survived at 81 %); the stall (B6 shape) never acted in a counted arm; C2 concurrent-reads layer not run;
B7's real cache heap only partly re-measured (Caffeine nodes and key objects in the 4 GiB stage-2 dumps); the 8 GiB
post-Full-GC readings rest on 2 Full GCs per arm; the 4 GiB dumps were parsed on the victim node pinned to one
hardware thread while the next arm ran (disclosed perturbation). Node clocks are MT
(2 h behind EST); `system.log` is UTC.

**Next step** *(updated 2026-11-17; item (1) done in run 2)*. (1) ~~Equal-heap replica ×3 with longer bursts, and an RF=3 single-DC ring at CL=ONE (two faster peers)~~; a token-aware client spreading coordination over the ring; (2) JIRA search
(`MutationStage` unbounded / local write backlog / CASSANDRA-  "LocalMutationRunnable hint"), then a diagnostic
patch that drops (not hints) expired *local* runnables when another replica already acked, as a second intervention;
(3) 8 GiB with a 300 s burst; (4) the B6-stall stage-1 holder of the original S2 design.
