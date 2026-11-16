# S1 — JVM-direct combo: receive-queue multiplicity + hint slabs + DOB scratch + networking pool + maintenance, then large-mutation DOB fill

**Campaign row:** S1 (S = stacked combo case, [combo playbook](../../../../combo-playbook.md)). **Direction:**
convergence (stacked: multiplicity → standing pools / maintenance overlap) + **unprotected accumulation** (stage 3:
in-flight `DataOutputBuffer` fill of large mutations, lead U1; U = unprotected-accumulation lead). Not a bypass:
no control's counter is exceeded. **Domain:** JVM direct (`-XX:MaxDirectMemorySize`), JDK `Bits` counter.
**Stages run:** 0 (ceiling sheet), 1 (C1 receive-queue multiplicity, N = 8 peers), 2 (layers: hint slabs,
DOB scratch via a coordinator write client, networking pool at cap, `nodetool flush`/`compact`), 3 (U1: the same
peers send 15 MiB mutations). **Regime:** default capacities (shipped yaml + environment keys).
**Budget:** heap 2048 MiB every arm; direct 2048 / 1536 / 1024 / 896 / 832 / 768 MiB (search).
**Source/build:** cassandra-5.0.9, unpatched, read-only reuse of `/mydata/b6/cassandra` (same build as C1 run 4).
JDK 11, G1. **Node:** `pc96` only (11 instances on loopback + clients). **Date:** 2026-11-16, 12:55–15:24 EST (measuring), filed 15:30.
**Design:** [`design/S1-design.md`](design/S1-design.md) (stage-0 sheet and predictions written before any reading;
amendments 1–5 dated before the readings they govern). Sources reused: C1 run 4 (C = convergence investigation),
C2, C3, R6-V (R = recheck; -V = re-test at defaults), B1 (B = bypass investigation), U1.

**Status (proposed, for the researcher's review):** **`verified-OOM · diagnostic`** proposed for condition **S3@768** (all stages stacked, 15 MiB
mutations, heap 2 GiB, direct 768 MiB): V1–V7 met under the standing budget rule (768 ≥ 512 MiB), labelled
`diagnostic` by analogy with C1 run 4's review (768 MiB is below the 1024 MiB that `cassandra-env.sh` resolves for a
node whose automatic heap is 2 GiB; by the letter of the protocol the conditions would be `deployment`: no
supporting deviation). Tag: convergence (stacked) + **unprotected** accumulation (U1); not mixed (no control's
counter exceeded). Filed in `convergence/` (V1–V7 met; V7 by the standing rule, no per-case review needed);
the researcher should confirm the `diagnostic` label and accept the thin gap-off control margin (§4 limits) —
otherwise move back to `candidates/` as `candidate`. Stages 1 and 2 alone: **negative** at
2048 MiB (headroom 67 % / 62 %).

## Summary

- **Conclusion.** At default capacities and a 2 GiB heap, stacking the JVM-direct consumers of one node does
  reach a direct-buffer OOM at budgets above the single-shape boundaries, but only up to **768 MiB direct**
  (3/3; 832, 896, 1024 MiB survive by touching the cap while `Bits.reserveMemory`'s forced GCs reclaim enough).
  Stage 1 alone (8 loaded peers, C1) peaks at 684 MiB and stage 2 (+ hint slabs, DOB scratch, networking pool at
  cap, flush/compaction) at 772 MiB: at 2048 MiB both are negatives with 62–67 % headroom. Only stage 3 — the same
  peers sending **15 MiB mutations** (within the default 16 MiB `max_mutation_size`) — adds the excess: U_peak
  1,368–1,395 MiB at 1.5–2 GiB, endpoint at 768 MiB in 16–51 s. Each ingredient removal survives at 768 MiB:
  1 MiB mutations (gap off) 0/3, one coordinator (multiplicity off) 0/3, no hint/DOB client and no maintenance
  (layers off) 0/3 — a **joint** endpoint. The largest failing budget rises from C1's 640 MiB to 768 MiB; it
  stays below the 1024 MiB auto value for a 2 GiB-heap node and far below 2048/3982 MiB.
- **Root cause.** Nothing bounds the direct memory of mutations **being serialized**: each of the 32
  `MutationStage` threads grows its thread-local `DataOutputBuffer` to 15–30 MiB in `CommitLog.add`
  (`expandToFit`, first OOM thread in 3/3), and `DOB_MAX_RECYCLE_BYTES` only trims after use (U1, unprotected
  accumulation). Eight loaded peers keep all 32 writers busy with large mutations (receive queue at its 540 MiB
  admission ceiling, now mostly deserialized on heap), while the standing pools (hint slabs 96 MiB, networking
  pool 128 + 8 MiB) sit at their caps. Dumps at failure: DOB scratch 210–435 MiB, pool chunks 136 MiB, hint slabs
  96 MiB, receive-path frames 20–95 MiB. Every counted control (Q/E/G, pool cap, 3 slabs, 1 MiB recycle) holds;
  their sum plus the uncounted in-flight scratch is not reconciled with `MaxDirectMemorySize`.
- **Two counters.** The JDK `Bits` counter threw; Netty's separate direct counter stood at 176–224 MiB of its own
  768 MiB at failure, so C2's encoded-response layer (Netty) cannot be stacked onto this endpoint (§1.1).

---

## 1. Ceiling sheet, protection map, configuration

### 1.1 Two direct counters (stage-0 finding, before readings)

`-XX:MaxDirectMemorySize=X` sets **two independent limits of X**: the JDK `Bits` counter (every
`ByteBuffer.allocateDirect`: Cassandra `BufferPool` chunks and overflow, queued internode LARGE frames, `HintsBuffer`
slabs, `DataOutputBuffer` scratch, compaction read-ahead) and Netty's own `DIRECT_MEMORY_COUNTER` (no-cleaner
pooled arena chunks: CQL v4 encoding, C2's encoded responses). C1 run 4 §3.4c showed this from dumps; this run's
dumps at failure show Netty's counter at 176–224 MiB of its own 768 MiB limit while the JDK counter threw. So
**C2's concurrent-read layer cannot add to the JDK endpoint** (it fails alone on its own counter at 1,024
outstanding 3.5 MiB reads, C2 S-A, verified) and was not stacked; physically the two add (process direct
footprint up to ≈ 2X).

### 1.2 Stage-0 ceiling sheet (JDK counter; design §2)

| Pool | Contract C (default) | Reachable multiplicity | Predicted max U | K basis |
|---|---|---|---|---|
| B0 baseline | — | — | 50 MiB | — |
| R receive queue (C1) | Q 4 MiB/conn, E 128 MiB/peer, G 512 MiB, on-wire bytes | N = 8 peers → K_max = N·Q + min(G, N·E) = 544 | 544 (1 MiB msgs: frames in direct) | Σ `using_bytes` |
| P networking `BufferPool` | 128 MiB retained (`networking_cache_size`) | 1 | 128 | JMX pool Size − Overflow |
| H hint slabs (R6-V) | 3 × 32 MiB | global | 96 | none |
| D DOB scratch kept (C3/R6-V) | 1 MiB per thread | ≤ ≈ 177 threads | 131–195 | none |
| M flush/compaction scratch | none | flush writer + compactors | 10–40 (estimate) | none |
| U1 in-flight DOB fill (stage 3) | none (recycle cap trims only after use; mutation ≤ 16 MiB) | 32 MutationStage threads in `CommitLog.add` | 32 × 15–30 = 480–960 | none |

Ceilings: stage 1 ≈ 722 MiB, stage 2 ≈ 1,053 MiB (both < 2048: negatives by arithmetic), stage 3 ≈ 1.5–2.0 GiB
(feasible at 2048 only at the top of the range). Heap competes in stage 3 (32 × 15 MiB deserialized + 512 MiB
memtable at 2 GiB).

### 1.3 Protection map

| Domain | Allocation / release | Contract | Multiplicity | Aggregate coverage | Lifetime |
|---|---|---|---|---|---|
| R | `InboundMessageHandler$LargeMessage.buffers` (`BufferPool` chunks / overflow), released after the stage deserializes | Q/E/G on-wire, hard | N peers | G covers the reserve part only; not reconciled with X | until deserialized |
| P | networking `BufferPool` chunks | 128 MiB retained; overflow unpooled | 1 | none above cap | standing |
| H | `HintsBuffer.slab` 32 MiB | 3 slabs | global | hard 3 | standing while hints flow |
| D | `DataOutputBuffer.scratchBuffer` (thread-local) | 1 MiB kept/thread | ≤ ≈ 177 | none (T × 1 MiB) | standing |
| U1 | same buffer while serializing a mutation (`CommitLog.add`, `CommitLog.java:306–308` → `expandToFit`) | **none in flight** | `concurrent_writes` 32 | none | per write |
| M | compaction read-ahead (`ThreadLocalReadAheadBuffer`), writer buffers | none | compactors | none | transient |
| heap (reported) | deserialized mutations (K bytes when messages are large), memtable | memtable 512 MiB | 32 writers | flush | — |

### 1.4 Configuration and budget audit

| Setting | Class | Value |
|---|---|---|
| all capacities (Q/E/G, `networking_cache_size`, `MAX_HINT_BUFFERS`, `DOB_MAX_RECYCLE_BYTES`, `concurrent_writes`, memtable, `max_mutation_size`, `commitlog_segment_size`) | **default** (absent from yaml; resolved values in V's system.log: Q/E/G 4/128/512 MiB, networking pool 128 MiB, chunk-cache pool 512 MiB, `memtable_allocation_type: heap_buffers`, `max_mutation_size` = 16 MiB) | V6 |
| heap | budget | 2048 MiB (ideal) |
| `-XX:MaxDirectMemorySize` | budget (dial) | 2048 / 1536 / 1024 / 896 / 832 / 768 MiB — all ≥ 512 (standing rule). Auto-consistent value for a 2 GiB-heap node = **1024 MiB** (`cassandra-env.sh`: heap ½ RAM, direct ¼ RAM → a 4 GiB node) |
| victim safety scope | environment (non-binding) | `systemd-run --user --scope MemoryMax=12G` (≤ 14:28), **44G** after amendment 4; `oom_kill` 0 in every valid arm |
| storage | environment | victim data/commitlog/hints on a 32 GiB tmpfs; all other instances' hints on local disk after amendment 1 |
| topology | environment | C1 run-4 topology on new loopback addresses: V .51 (cores 0–7), F .52 fast co-replica (8 GiB heap), C1–C8 .61–.68 coordinators (2 GiB heap), Dn .59 (dc d, stopped before load in every arm) |
| hinted handoff | default (on) | hint layer: keyspace `s1h` NTS {v:1, d:1}, Dn down → V writes a hint per write |
| workloads | experimental variables | stage 1: 1 MiB zero blobs, 500/s over N coordinators, CL=ONE, 90 s; stage 2: + client→V on `s1h`, 1 MiB, 100/s offered, + `nodetool flush` @20 s, `compact c1` @35 s; stage 3: coordinators' blobs 15 MiB (15,728,640 B), 33/s offered, keys mod 200, in-flight 16/coordinator |
| Byteman, patches, timeouts | not used / defaults | — |

Victim yaml diff (environment keys only): [`logs/V-yaml.diff`](logs/V-yaml.diff).

---

## 2. Verification solution (as executed)

Design and amendments: [`design/S1-design.md`](design/S1-design.md). Harness [`harness/`](harness/) (derived from
C1 run 4): `ctl.sh` (11 instances), `ring-up.sh` (clean ring every arm), `arm.sh` (one arm; env `LAYER=1` adds
the stage-2 layers; `BLOB`, `KEYS`, `INFL`, `HEAPDUMP`), `S1Load.java` (C1Load + `-Dks`, `-Dkeys`), `S1Sample.java`
(1 s JMX/CQL sampler = C1Sample), `ledger.py` (per-arm ledger), `peaks.py`, `gcwin.py` (STW share, from C2),
`hprof_direct.py` (dump attribution, from C1), `queue.sh` + `q*.txt` (arm queues as run). Each arm: clean
ring, Dn stopped, 5 s warm-up, 90 s load (+ layers), 30 s observation, stop all. Endpoint: `OutOfMemoryError:
Direct buffer memory` in V's system.log (Cassandra then forces a heap OOM, writes the dump, `kill -9`).

Invalid arms (excluded): `INVALID_S3_U1_N8_d2048_r1_tmpfsENOSPC` (tmpfs full from coordinator hints → ENOSPC
and a JVM crash, no OOM; amendment 1), `INVALID_I_N1_d768_r1_safetyscope` (12 GiB safety scope killed V, tmpfs
hints charged to it; amendment 4).

---

## 3. Runtime results

Raw data: `pc96:/mydata/s1/runs/<arm>/` (`samples.csv`, `peers.txt`, `cg.csv`, `load.log`, `layer-load.log`,
`maint.log`, `V-logs/{system.log,gc.log*}`, `first-oom.txt`, `outcome.txt`, dumps `*.hprof` for the failing arms,
`direct-holders.txt`); one line per arm in `/mydata/s1/runs/summary.txt` (copied to
[`logs/summary.txt`](logs/summary.txt)).

### 3.1 Ledger per stage (U = JMX `java.nio` direct MemoryUsed, K = Σ receive-queue `using_bytes`, at U's peak)

Budget X in MiB; headroom = X − U_peak. "Residual" = U − baseline − K (P + H + D + U1 + M, not split by JMX;
split by dumps in §3.4). STW = worst 60 s stop-the-world share (`gcwin.py`); `System.gc()` = Full GCs forced by
`Bits.reserveMemory` (direct-memory reclamation).

| Stage / arm | X | n/N endpoint | U_peak | K at peak (C = 544) | pool pooled (C = 128) | residual | heap peak | headroom | STW max 60 s | `System.gc()` | delivered |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 `S1_N8_d2048` (8 peers, 1 MiB, 500/s) | 2048 | 0/1 (+ C1 r4 0/2) | 684 | 540 | 127 | 94 | 1941 | **1,364 (67 %)** | 25 % | 0 | 505.7/s |
| 2 layers alone `L2_layers_N0_d2048` | 2048 | 0/1 | 119 | 0 | 8 | 69 | 1933 | 1,929 (94 %) | 3 % | 0 | layer 101/s |
| 2 `S2_stack_N8_d2048` (+ H/D client, flush, compact) | 2048 | 0/1 | 772 | 538 | 129 | 184 | 1929 | **1,276 (62 %)** | 34 % | 0 | 505.3/s + 62/s |
| 3 `S3_U1_N8_d2048_r2` (15 MiB) | 2048 | 0/1 | 1,368 | 525 | 128 | 793 | 1963 | **680 (33 %)** | 28 % | 0 | 19.1/s + 31/s |
| 3 `S3_U1_N8_d1536_r1` | 1536 | 0/1 | 1,395 | 540 | 128 | 805 | 1935 | 141 (9 %) | 28 % | 0 | 22.2/s + 31/s |

Stage-0 vs measured: stage 1 ceiling 722 / measured 684; stage 2 ceiling ≈ 1,053 / measured 772 (the layers add
only ≈ 88 MiB on the peak: the hint client is throttled to 62/s by the victim's stalls, and part of D was already in
stage 1); stage 3 ceiling 1.5–2.0 GiB / measured 1.37–1.40 GiB.

**Missing multiplicity at 2048 MiB.** Stage 1: once G is full each extra peer adds only Q = 4 MiB → ≈ 340 more
loaded peers to close 1,364 MiB (8 reachable here). Stage 2: ≈ 320 more peers, or ≈ 13 more 96 MiB hint pools
(only one exists). Stage 3: 680 MiB ≈ 23–45 more 15–30 MiB writers in flight (the stage has 32 permits, all
active at the peak) — not reachable at the default `concurrent_writes`.

### 3.2 Stage 3: budget search (N = 8, all stage-2 layers on, 15 MiB mutations)

| X (MiB) | Arm(s) | n/N direct OOM | U_peak | `System.gc()` | Note |
|---|---|---|---|---|---|
| 2048 | `S3_U1_N8_d2048_r2` | 0/1 | 1,368 | 0 | (r1 invalid: tmpfs ENOSPC, amendment 1) |
| 1536 | `S3_U1_N8_d1536_r1` | 0/1 | 1,395 | 0 | headroom 141 |
| 1024 | `S3_U1_N8_d1024_r1`, `_r2` | 0/2 | 1,024 / 1,023 | 85 / 99 | touches the cap; forced GCs reclaim |
| 896 | `S3_U1_N8_d896_r1` | 0/1 | 894 | 169 | touches the cap |
| 832 | `S3_U1_N8_d832_r1` | 0/1 | 832 | 333 | touches the cap |
| **768** | `S3_U1_N8_d768_r1..r3` | **3/3** | 768 / 754 / 767 | 153 / 18 / 160 | death 48 / 16 / 51 s after load start |

**Largest failing direct budget: 768 MiB (3/3); 832 MiB survives (0/1).** Above ≈ 800 MiB the JDK counter's own
reclamation (`Bits.reserveMemory` → `System.gc()` → retry) frees enough unreachable direct buffers (overflow
networking buffers, released DOB growth) for the waiting allocation; at 768 MiB the *live* set (standing pools
≈ 232 MiB + in-flight DOB of 32 writers + frames) exceeds the limit.

### 3.3 Endpoint, matched control and intervention at 768 MiB

Heap 2048 MiB, all arms from a clean ring, condition D yaml.

| Role | Arm | Change vs endpoint | n/N direct OOM | U_peak | K_peak | delivered (c1 + layer) |
|---|---|---|---|---|---|---|
| **Endpoint (V1)** | `S3_U1_N8_d768_r1..r3` | — (8 peers, 15 MiB, 33/s offered; layers on) | **3/3** | 768 / 754 / 767 | 540 / 525 / 540 | ≈ 17–19/s × 15 MiB until death |
| **Matched control (V2)**, gap off | `G_gapoff_N8_d768_r1..r3` | 1 MiB mutations, 500/s (≈ 1.9× the bytes/s stage 3 delivers), layers on | **0/3** | 766 / 740 / 751 | 543 | 491–500/s + 51–58/s |
| **Intervention (V4)**, multiplicity off | `I_N1_d768_r1b, r2, r3` | one coordinator, same 15 MiB × 33/s offered, layers on | **0/3** | 568 / 556 / 575 (headroom 25–28 %) | 120 | 21–23/s + 100/s |
| Intervention, layers off | `L_layeroff_N8_d768_r1..r3` | no H/D client, no flush/compact | **0/3** | 766 / 768 / 765 (touch the cap; 185–232 forced GCs) | 525–540 | 19–22/s |

The N=1 arms deliver the same 15 MiB write rate as the endpoint arms (20–23/s vs 17–22/s before death), and the
hint/DOB layer runs *faster* (100/s vs 13–31/s), so their survival is not bought by dropping work. With one
coordinator the receive queue holds ≤ Q + E = 132 MiB (≈ 8 large messages), so fewer of the 32 writers serialize
a 15 MiB mutation at once (U_peak 527–575 MiB). The gap-off control survives but with a thin margin: it touches the
cap too (740–766 MiB, 23–50 forced GCs) and one of its coordinators (C3, r2) died of a Java heap OOM (coordinator-side
retention, B6-like, not the victim).

### 3.4 Who holds the direct memory at failure (dumps, `hprof_direct.py`)

Dump written at Cassandra's forced heap OOM ≈ 1 s after the first direct OOM (`-XX:+HeapDumpOnOutOfMemoryError`,
1.2–1.3 GB each, kept at `/mydata/s1/runs/S3_U1_N8_d768_r{1,2,3}/*.hprof`). JDK-accounted owners
(`allocateDirect` with a cleaner) attributed by referrer chain (`hprof_direct.py`, 6 hops). Excerpts:
[`logs/S3_U1_N8_d768_r{1,2,3}-direct-holders.txt`](logs/).

| Holder (MiB) | r1 | r2 | r3 |
|---|---|---|---|
| JDK-accounted owners total | 559 | 745 | 706 |
| **U1 `DataOutputBuffer` scratch** (`DataOutputBuffer$1$1.buffer`; 15,728,683 B × 8/12/0 and 31,457,366 B × 6/8/10 buffers = grown scratch of 15 MiB mutations) | **210** | **435** | **255** |
| P `BufferPool` chunks, no live consumer (17 × 8 MiB: networking pool at its 128 MiB cap + 1 chunk-cache chunk) | 136 | 136 | 136 |
| H hint slabs / hints writer | 96 | 96 | 96 |
| R queued LARGE frames + frames being decoded | 20 | 75 | 95 |
| M / other (compaction read-ahead `ThreadLocalReadAheadBuffer`, storage I/O) | 96 | 1 | 32 |
| no strong referrer (garbage awaiting Cleaner) | 0 | 0 | 90 |
| Netty counter (separate limit 768) | 192 | 176 | 224 |

Owners total is below 768 because buffers released between the throw and the dump (≈ 1 s) are gone. The
in-flight DOB scratch is the largest holder in 3/3 (37–58 %); the standing pools P + H are a fixed ≈ 232 MiB; the
receive queue's direct share is small because with 15 MiB messages most of the admitted K (on-wire bytes) is
already deserialized on the heap (heap 1.1–1.3 GiB at the last sample). First error in all three: `MutationStage`
thread, `OutOfMemoryError: Direct buffer memory` in `Bits.reserveMemory` ← `DataOutputBuffer.expandToFit` ←
`Mutation.serializer.serialize` ← `CommitLog.add(CommitLog.java:308)` ([`logs/*-first-oom.txt`](logs/)).

### 3.5 Prediction fit

| Prediction (design §7, amendments) | Observed |
|---|---|
| Stage 1 survive at 2048, U 650–720 | survive, 684 ✓ |
| Stage 2 survive at 2048, U 750–1,000; layers alone ≤ 350 | survive, 772 ✓; 119 ✓ |
| Stage 3 at 2048: heap OOM / heavy GC first (60 %) | survive, no heap OOM, STW ≤ 28 % ✗ (heap peaked 1.96 GiB but held) |
| Amendment 1: survive at 2048, direct OOM at ≤ 1,280 | survive ✓; OOM only at ≤ 768 (832–1,024 rescued by forced GCs) — partly ✗ |
| Amendment 2: S3 at 768 ≥ 2/3; gap-off survive (borderline); N1 survive 3/3 | 3/3 ✓; 0/3 (touches cap) ✓; 0/3 ✓ (headroom 25–28 %) |
| Amendment 3/5: layer-off fails (layers not needed) | ✗ — layer-off survives 0/3 (touching the cap): the stage-2 layers are needed at 768 |

### 3.6 Host and side events

- pc96 was shared: another agent's S2 controller ran on pc96 from ≈ 13:20 (ssh to apt nodes only; no local JVM,
  load average ≤ 2 from it); `foreign.txt` per arm records loadavg and foreign processes. No foreign Java process
  on pc96 during any arm.
- After the victim died in the endpoint arms, 1–5 coordinators stopped ≈ 20–30 s later with their 2 GiB heaps full
  (G1 old gen at 2.0 GiB; they keep 15 MiB mutations for hints to the dead victim) — post-endpoint, like C1's
  post-endpoint ENOSPC. In `G_gapoff_N8_d768_r2` coordinator C3 died of `Java heap space` during the load (victim
  survived; client still 491/s).
- Invalid arms: see §2. The 12 GiB safety scope was raised to 44 GiB after the second (amendment 4); `oom_kill` = 0 in
  every valid arm.

---

## 4. Conclusion

**Stage reached: 3.** Stage 1 (multiplicity) and stage 2 (standing pools + maintenance) are **negatives at 2048 MiB**
(headroom 1,364 / 1,276 MiB, 67 / 62 %); their ceilings (722 / ≈ 1,053 MiB) are below 2048 by arithmetic. Stage 3
(the U1 gap: large mutations' in-flight DOB) raises U_peak to 1.37–1.40 GiB but still leaves 680 MiB (33 %) at
2048 MiB and 141 MiB at 1536 MiB; the endpoint is reached only at **768 MiB (3/3)**, with 832–1,024 MiB rescued by
`Bits.reserveMemory`'s forced GCs. **Direct OOM at 2048 MiB or at the auto values (1024 MiB for this heap, 3982 MiB
for a 16 GiB node) was not reached** within the tested range (0/2 at 1024, 0/1 at 1536 and 2048; 3982 not run:
infeasible by the ceiling sheet).

**Attribution (joint endpoint).** At 768 MiB each single ingredient removal survives: gap off (1 MiB mutations)
0/3, multiplicity off (1 coordinator, same 15 MiB rate) 0/3 with 25–28 % headroom, layers off (no hint/DOB client,
no flush/compact) 0/3 but touching the cap. The dumps put the excess in the in-flight DOB scratch of `MutationStage` (210–435 MiB) on top of the standing
pools at their caps (P 136, H 96). Classification by the protocol's table: every control's U ≤ C (receive queue K
≤ 544, pool ≤ 128, slabs ≤ 3, kept scratch ≤ 1 MiB/thread) and the holder that decides the outcome has **no control**
(in-flight serialization buffer; `max_mutation_size` bounds a single mutation, not the 32 concurrent ones) →
**convergence (stacked) + unprotected accumulation**; not mixed (no bypass shown).

**Interpretation.** A configuration-sizing gap: none of the default direct consumers is reconciled with
`MaxDirectMemorySize`, and the in-flight scratch of large mutations (≈ `concurrent_writes` × 1–2 × mutation size,
up to ≈ 1 GiB at defaults) is uncounted. In this topology the stack fails at 768 MiB, 128 MiB above C1's single
shape (640) and 256 MiB short of the auto value for a 2 GiB heap. Stacking narrowed the gap to the auto budget but
did not close it.

**Status by condition (proposed):**

| Condition | Endpoint | Control | Intervention | Proposed status |
|---|---|---|---|---|
| S3@768 (stack + 15 MiB, heap 2 GiB, direct 768) | 3/3 | gap off 0/3 | N=1 0/3; layers off 0/3 | `verified-OOM · diagnostic` (pending review; see label note) |
| S3@832–2048 | 0/5 (832, 896, 1024 ×2, 1536, 2048) | — | — | boundary: largest failing 768 |
| Stage 1, stage 2 @2048 | 0/1 each (+ C1 r4 0/2) | — | — | negative (headroom 67 / 62 %) |

**V1–V7 (condition S3@768):**

| | Evidence | Met |
|---|---|---|
| V1 repetition | `S3_U1_N8_d768_r1..r3`: 3/3 direct OOM | yes |
| V2 matched control | `G_gapoff_N8_d768_r1..r3` (same build, budget, layers, 8 peers; 1 MiB mutations at 500/s): 0/3 | yes (thin margin: U touched 740–766) |
| V3 measurement | U = JMX direct (1 s) vs K = Σ `using_bytes`, pool Size/Overflow; per-holder U from 3 dumps (§3.1, §3.4) | yes |
| V4 intervention | multiplicity off `I_N1_d768_r1b, r2, r3`: 0/3 at matched 15 MiB rate (21–23/s, 0 errors), U_peak 556–575; also layers off 0/3 | yes |
| V5 initiating failure | first `OutOfMemoryError: Direct buffer memory` + stack (MutationStage, `CommitLog.add` → `expandToFit`) 3/3; dumps ×3 with holders | yes |
| V6 default constraints | all capacities unset (yaml diff = environment keys); 15 MiB mutations within the default `max_mutation_size` 16 MiB | yes |
| V7 acceptable budget | heap 2048 (ideal), direct 768 ≥ 512 (standing rule); below the 1024 MiB auto value → `diagnostic` by the C1 precedent (researcher to confirm) | yes (standing rule) |

**Limits.**
- Only up to 768 MiB direct; the stack does **not** reach the ideal 2 GiB or any auto-resolved budget. The S1 aim
  (failure at 2 GiB / auto) is not met; the distance is 680 MiB at 2048 and 256 MiB below the 1024 auto value.
- n = 1 per budget above 768 (832, 896, 1536, 2048) and n = 2 at 1024; the boundary 768–832 is not refined, and the
  forced-GC rescue is timing-dependent, so a low rate of failures above 768 is not excluded.
- The gap-off control at 768 survives 3/3 but touches the cap (0–4 % headroom): stage 2 alone is close to 768 MiB,
  so the 768 condition sits near stage 2's own boundary (C1: stage 1 alone fails ≤ 640).
- Workload: 15 MiB zero-filled blobs at ≈ 20 writes/s (≈ 300 MiB/s) from 8 coordinators; large but within the
  default `max_mutation_size` and `native_transport_max_frame_size` (16 MiB). Loopback colocation, tmpfs storage,
  one down node (Dn) for the hint layer.
- B1's release defect (native v5 large requests) and C2's concurrent reads were not stacked: the harness uses
  protocol v4, B1 plateaus at the pool cap already in the stack, and C2 runs on Netty's separate counter (§1.1).
- U (JMX `java.nio`) excludes Netty's own direct memory (176–224 MiB at failure).

**Next step.** Raise the in-flight DOB share without more peers: larger `concurrent_writes` is a capacity change
(V6), so instead test (a) mutations near 16 MiB with the commit log on a slower volume (longer time in
`CommitLog.add`), (b) the coordinator side (native-transport threads serializing 15 MiB mutations for 2 replicas),
both at 1024 MiB direct; and file U1 as its own case (unprotected in-flight DOB; intervention = bound the total
in-flight serialization bytes or serialize large mutations into pooled chunks).

**Cleanup:** after every arm `ctl.sh stop all`; at the end (15:24) no `/mydata/s1` process, no listening
port on 127.0.0.51–.68, no `s1V-*` scope; the tmpfs `/mydata/s1/shm` was emptied and unmounted, and the non-victim
hint directories (`/mydata/s1/disk`, 22 GB of scratch hints) deleted. Kept: `/mydata/s1/runs/` (3.8 GB incl. the
three dumps of the 768 MiB endpoint arms) and `/mydata/s1/ring/` (last ring's configs/logs). `/mydata/b6/cassandra`
was only read. No apt node was used.
