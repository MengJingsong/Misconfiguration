# U1 run 2 — in-flight `DataOutputBuffer` fill of large mutations, delivered to a replica over internode messaging (Utah m400, aarch64)

> **Verdict (2026-11-17 mapping):** retry. **Phase-1 case file:** [`DOB_MAX_RECYCLE_BYTES-close-MAX_RECYCLE_BUFFER_SIZE--guided`](../../../../../capacity-enforcement-exp/cassandra/stage3-ai-deep-read/cases/DOB_MAX_RECYCLE_BYTES-close-MAX_RECYCLE_BUFFER_SIZE--guided.md), [`max_mutation_size-validateSize-MAX_MUTATION_SIZE--guided`](../../../../../capacity-enforcement-exp/cassandra/stage3-ai-deep-read/cases/max_mutation_size-validateSize-MAX_MUTATION_SIZE--guided.md).

**Campaign row:** U1 (U = unprotected-accumulation lead: memory with no applicable control). **Run 2** of the case;
run 1 is [`concurrent_writes+max_mutation_size--inflight-DOB-fill.md`](concurrent_writes+max_mutation_size--inflight-DOB-fill.md)
(pc96, x86, the victim as coordinator). **Redesign (researcher's decision 2026-11-17):** the large mutations reach
the victim **as a replica, over internode messaging**, so no client request frame sits on its Netty counter (lead
B9; B = bypass investigation), the native in-flight limits do not throttle its write threads, and enough coordinators
keep all 32 `MutationStage` threads busy. Related: S1 (S = stacked combo case), whose stage 3 was U1 with 8 loopback
coordinators; C1 run 4 (C = convergence investigation), the internode receive queue. **Direction:** unprotected
accumulation. **Domain:** JVM direct, JDK `Bits` counter. **Regime:** default capacities on every node (shipped yaml,
environment keys only). **Budget:** victim heap 2,048 MiB every arm; direct 1,024 MiB (the `cassandra-env.sh`
resolution for a 4 GiB node), auto (15,872 MiB on the m400), 1,152, 960, 896, 768, 640 MiB.
**Source/build:** cassandra-5.0.9, unpatched; the S2 run-2 aarch64 build of the pinned source (`src/` identical to
`systems/cassandra/source/src/` file by file; jar md5 `beb4d0c1…` on all five nodes), copied read-only to
`/mydata/u1r2/cassandra`. OpenJDK 11.0.33, G1. **Platform:** **aarch64** (Utah m400, 8 cores, 62 GiB, SATA SSD at
≈ 100–113 MB/s); not comparable arm-by-arm with run 1's x86 arms. **Nodes:** victim `ms0625`; coordinators + clients
`ms0640`, `ms0604`, `ms0611`, `ms0617`. **Date:** 2026-11-17 12:15 – 16:30 EST (arms 12:30–16:28), filed ≈ 17:00. **Design:**
[`design/U1-run2-design.md`](design/U1-run2-design.md) (written 12:50 before any reading; amendments 1–5 dated before
the readings they govern).

**Status (proposed, researcher decides):** **`candidate`** — the U1 endpoint (JDK `OutOfMemoryError: Direct buffer
memory` in `CommitLog.add` → `expandToFit`, reached from `MutationVerbHandler`) occurs **at the 4 GiB-node budget
(heap 2,048 / direct 1,024 MiB)** in **2 of 14** clean-start arms of one fixed condition (8 coordinators, 16 MiB − 1 KiB
mutations), so V1 (≥ 3) is not met; V2–V7 hold (V7: 1,024 MiB needs no override; review pending). **Conditions label
if promoted: `deployment`.** At 896 MiB: 2/4. **Tag: unprotected accumulation (U1), not mixed** — live receive frames
are ≈ 0 at every failure; the scratch sits on top of the standing networking pool (128 MiB cap) and hints buffer.
With the specified **15 MiB** mutations nothing failed (0/8 saturated arms, 640–1,024 MiB and auto).

## Summary

- **Conclusion.** Delivering the large mutations to the victim as a replica works as designed: no client frame
  reaches it (no Netty endpoint, B9 avoided), ≥ 4 coordinators keep all 32 `MutationStage` threads busy (the
  receive queue admits 8 large messages per coordinator), and every burst puts up to 32 doubled scratch buffers into
  `CommitLog.add` at once. With **16 MiB − 1 KiB** mutations (inside `max_mutation_size`) the unconstrained demand is
  **U_peak 1,212 MiB** = 50 baseline + 136 networking pool + 32 × 2S (1,024): the arithmetic ceiling, reached.
  At **1,024 MiB** — what `cassandra-env.sh` resolves for a 4 GiB node — every arm hits the cap (46–105 forced GCs)
  and **2 of 14 die of a U1 direct OOM**; at 896 MiB 2/4; 1,152 survives (0/1). **Largest failing budget: 1,024 MiB**
  (run 1: 576). With **15 MiB** mutations: U_peak 936 unconstrained, **0/8** down to 640 MiB.
- **Root cause.** As run 1: `CommitLog.add` serializes each mutation into a thread-local direct `DataOutputBuffer`
  that grows to 2S (3S transiently) and is held through segment allocation and the copy; `DOB_MAX_RECYCLE_BYTES`
  trims it only afterwards, and the only bound on the sum is `concurrent_writes` (32). The receive queue bounds the
  number of messages (on-wire bytes), not their processing copies. `Bits.reserveMemory`'s retry rescues most cap
  touches; the OOM needs a burst whose holders stay in `CommitLog.add` past its ≈ 0.5 s window.
- **Ledger at failure (5 dumps):** DOB scratch 368–752 MiB (58–80 % of JDK owners), networking pool 136, hints
  buffer 32, live receive frames ≤ 0.4; Netty's separate counter 160–176 (not exhausted). Initiating thread:
  `MutationStage`, JDK counter, stack via `MutationVerbHandler` → `CommitLog.add:308` → `expandToFit` (5/5).
- **Attribution (1,024 MiB, ×3 each):** 512 KiB control 0/3 (U 594–612, K full); `concurrent_writes: 8` 0/3 (U
  800–842, same applied rate); `dob.allocate_type=ONHEAP` 0/3 (direct 202–230, heap ≤ 1,992 MiB, no heap OOM).
- **Platform:** aarch64 m400, 100 MB/s SATA SSD; every shape is disk-bound (≈ 100 MiB/s applied, 97–99 % client
  timeouts at the coordinators).

---

## 1. Constraints, protection map, configuration

### 1.1 Source check (pinned 5.0.9): the replica path

Run 1's §1.1 map (size check, holder, growth, hold, release) applies unchanged from `CommitLog.add` down. New on the
replica path:

| Step | Source | Finding |
|---|---|---|
| Receive admission | `InboundMessageHandler.processFirstFrameOfLargeMessage` (`:207–222`) → `AbstractMessageHandler.acquireCapacity` (`:411–440`) | a 15–16 MiB `MUTATION_REQ` exceeds the 4 MiB per-connection queue capacity and borrows the excess from the endpoint reserve (128 MiB) and the global reserve (512 MiB), in on-wire bytes, from the first frame. Per coordinator ≤ (4 + 128)/S = **8 messages**; in total ≤ (512 + 4N)/S ≈ 34–36. |
| Capacity release | `ProcessMessage.run` (`:410–446`) | after the verb handler returns, i.e. **after** `CommitLog.add` and the memtable write. K = Σ `using_bytes` therefore counts every message being received, queued or applied. |
| Frames | `LargeMessage` buffers (networking `BufferPool`, 128 MiB retained; overflow `allocateDirect`) | ≈ S direct per message until `deserialize()` on the stage thread (`:481–509`), then returned to the pool. |
| Verb | `MutationVerbHandler.doVerb` → `applyMutation` → `Mutation.applyFuture()` → `Keyspace.applyInternal` → `CommitLog.add(:308)` | expired messages are dropped before processing (`MutationVerbHandler.java:47–52`, `ProcessMessage.run`); the rest are applied **synchronously on the `MutationStage` thread** — the U1 holder of run 1, now reached from internode. |
| Max message size | `DatabaseDescriptor.java:974–996` | `internode_max_message_size` defaults to min(receive, send endpoint reserve) = **128 MiB**: 15 MiB and 16 MiB − 1 KiB mutations are admitted. |
| Multiplicity | `concurrent_writes` = 32; receive queue | `MutationStage` bounds the scratch holders at 32; the receive queue bounds the messages in flight on the replica at ≈ 8 per coordinator, so **≥ 4 coordinators are needed to reach 32** (measured: N = 1 → ≤ 8 active, N = 2 → ≤ 16, N = 4 → 32). |

Arithmetic ceiling (JDK counter): B0 + 32 × 2S standing (960 MiB at S = 15 MiB, **1,024 MiB at S16 = 16,776,192 B**)
+ up to 32 × S transient (the S → 2S doubling copy) + queued frames. B0 measured idle = 50 MiB (32 MiB hints-writer
buffer, 8 MiB networking-pool chunk, NIO); under load the networking pool fills to its 128 MiB cap (+ 8 MiB
chunk-cache chunk).

### 1.2 Protection map (design §3, fixed before readings)

| Domain | Allocation / release | Contract C | Multiplicity | Aggregate coverage | Lifetime |
|---|---|---|---|---|---|
| **U1 in-flight DOB** | `DataOutputBuffer$1$1.buffer` grown under `CommitLog.add`, freed at `close()` | **none in flight** (`max_mutation_size` 16 MiB per mutation) | ≤ `concurrent_writes` 32 | none; not reconciled with `MaxDirectMemorySize` | serialize → segment → copy |
| R receive frames (C1) | `LargeMessage` buffers in the networking pool, released at deserialize | Q 4 / E 128 / G 512 MiB on-wire, until the verb returns | N peers | K counts on-wire bytes of every admitted message | first frame → deserialize |
| P networking `BufferPool` | pool chunks (the frames' memory) | 128 MiB retained | 1 | overflow unpooled | standing |
| D kept DOB | same buffer after `close()` | 1 MiB/thread | threads that serialized | none | standing |
| B0 | hints-writer buffer (32 MiB), NIO, compaction read-ahead | per-pool | — | — | standing |
| Netty counter (separate limit = same value) | internode event-loop arenas on V; the sampler's CQL session | — | — | own counter | — |
| Heap (reported) | deserialized mutations (≈ S each), memtable (`heap_buffers`, 512 MiB) | memtable | ≤ admitted | flush | — |

### 1.3 Configuration and budget audit

| Setting | Class | Value |
|---|---|---|
| `concurrent_writes`, `max_mutation_size`, `commitlog_segment_size`, commit-log sync, `DOB_MAX_RECYCLE_BYTES`, `cassandra.dob.allocate_type`, internode receive/send queue capacities, `internode_max_message_size`, memtable, timeouts, hinted handoff | **default** on all five nodes (absent from yaml / no `-D`) | 32; 16 MiB; 32 MiB; periodic 10 s (block at 15 s lag); 1 MiB; DIRECT; 4/128/512 MiB; 128 MiB; `heap_buffers` ¼ heap; write 2 s; on |
| yaml diff (V) | environment | cluster name, addresses, seeds, `GossipingPropertyFileSnitch`, data/commitlog/hints/saved_caches/cdc dirs, `num_tokens: 1`, `initial_token`, `auto_bootstrap: false` ([`logs-run2/V-yaml.diff`](logs-run2/V-yaml.diff)) |
| V heap | budget | `MAX_HEAP_SIZE=2048M` (ideal) |
| V direct | budget (dial) | `MAX_DIRECT_MEMORY_SIZE` (the documented `cassandra-env.sh` override); auto = unset → **15,872 MiB** read back by `jcmd VM.flags` |
| keyspace / topology | environment | `u1r2` = `NetworkTopologyStrategy {v: 1}`: V (dc `v`) holds every replica, the coordinators (dc `c`) none |
| coordinators | environment | 8 GiB heap, direct auto, `-XX:-HeapDumpOnOutOfMemoryError`; N = 8 = a second instance on each coordinator node at an alias IP 10.10.1.12–.15 (amendment 2; aliases removed at the end) |
| scopes | environment | V: `systemd-run --user --scope -p MemoryMax=40G -p MemorySwapMax=0` (non-binding; `oom_kill` 0 in every arm); coordinators: `MemorySwapMax=0`; linger on for the run, off at the end |
| storage | environment | each node's local SATA SSD (LVM, `/mydata`), V measured 113 MB/s `dd oflag=direct`; not tmpfs |
| workload | experimental variable | `U1R2Load` (driver 3.12.1, protocol v4, prepared `INSERT INTO u1r2.t (pk int, b blob)`, CL ONE, zero-filled blobs, keys mod 200), one client per coordinator, whitelisted to its local coordinator, 2 connections × `INFL`, no rate cap. **E15** = 15,728,640 B; **E16** = 16,776,192 B (16 MiB − 1 KiB, the largest value accepted by `max_mutation_size` and the 16 MiB native frame); **G** = 524,288 B. 96 requests outstanding in every E arm (N = 4 × 2 × 12 or N = 8 × 2 × 6). |
| Byteman, patches | not used | — |

### 1.4 V7 argument (design §4, written before readings)

`conf/cassandra-env.sh` (`calculate_heap_sizes`, lines 58–68, 139–141): with G1 `USING_CMS` = 1, so `heap_limit` =
31,744 MiB; heap = min(½ RAM, 31,744) and direct = **¼ RAM** (or 15,872 MiB when ½ RAM > 31,744), independent of
`MAX_HEAP_SIZE`. A node with 4 GiB of RAM resolves heap **2,048 MiB** and direct **1,024 MiB** (`free -m` = 4,096; a
real 4 GiB VM reports slightly less, e.g. 3,900 → 975 MiB direct). On the m400 (`free -m` 64,249) the explicit 2 GiB
heap gets direct 15,872 MiB (confirmed: `-XX:MaxDirectMemorySize=16642998272`). 1,024 MiB therefore needs no
override and meets V7 both as the 4 GiB-node resolution and by the standing rule (≥ 512 MiB); 896–640 MiB are ≥ 512
but below that resolution. *Researcher's review: pending.*

---

## 2. Verification solution (as executed)

Harness [`harness-run2/`](harness-run2/): `ctl.sh` (per-node instance control, scopes, JVM budget via
`MAX_DIRECT_MEMORY_SIZE`), `node.sh` (client, samplers, collection, wipe), `arm.sh` (one arm from a clean ring,
driven from pc96), `queue.sh` + `q1–q6.txt` (queues as run), `U1R2Load.java`, `U1R2Sample.java` (1 s: JMX direct
= U, heap, `MutationStage` active/pending/completed, commit-log waits, dropped messages, memtable, networking pool;
CQL `system_views.internode_inbound`: K = Σ `using_bytes`), `peaks.py`, `table.py`, `jstk.py` (thread-dump
classification, arm `B_N4i12_d1024_r1` only), `hprof_direct.py` (dump attribution, from C1/S1/run 1), `dump.sh`.
Each arm: all instances regenerated (data, commit log, hints wiped), V started, then the coordinators in parallel,
all UN, schema, samplers, 5 s idle, **90 s load**, 20 s observation, collect, stop everything. Endpoint:
`OutOfMemoryError: Direct buffer memory` in V's `system.log`; Cassandra then forces a heap OOM and writes a dump
(shipped `-XX:+HeapDumpOnOutOfMemoryError`). Forced GCs = `System.gc()` lines in V's GC log (`Bits.reserveMemory`'s
reclamation). Dumps were read from V with `ionice -c3` and attributed on pc96.

---

## 3. Runtime results

Raw data: `ms0625:/mydata/u1r2/runs/<arm>/` (`samples.csv`, `peers.txt` (per-peer receive queue each second),
`cg.csv`, `V-logs/{system.log,debug.log,gc.log}`, `first-oom.txt`, `outcome.txt`, `V-flags.txt`, `V-cmdline.txt`,
`V-yaml.diff`, `gcsys.txt`; the five failure dumps `*.hprof` with `direct-holders.txt`; `B_N4i12_d1024_r1` also
`jstack.csv` and `threads-*.txt`); one line per arm in `ms0625:/mydata/u1r2/runs/summary.txt` (copy:
[`logs-run2/summary.txt`](logs-run2/summary.txt)). Client logs and coordinator `system.log`s:
`ms0640|0604|0611|0617:/mydata/u1r2/runs/<arm>/`. Small-file mirror of every arm: `pc96:/mydata/u1r2/mirror/<arm>/`.
Columns: U_peak = max of the 1 s JMX `java.nio` direct samples (the JDK `Bits` counter, incl. the networking pool
and the 50 MiB idle baseline); K = Σ receive-queue `using_bytes`; "death" from the first `ERROR` timestamp; "writes
applied" = Δ table write count on V up to the last good sample; client counts of dead arms include fast failures
after V died. Arm names: `B` = E15, `E16`, `N8` = 8 coordinators (else 4), `iX` = in flight per client connection,
`dX` = direct MiB, `A` = auto, `G` = control, `I_*` = intervention. Shakedown `SHAKE_1m_auto` (1 MiB, N = 1, 30 s) is
not a reading.

### 3.1 Saturation sweep and auto (heap 2 GiB)

| Arm | X (MiB) | value (MiB) | N×in-flight | change | outcome | death (s after load start) | U_peak (MiB) | K_peak (MiB) | heap peak | MutationStage active peak | load samples at 32 | writes applied on V | MUTATION_REQ dropped (expired) | client sent / timeouts | forced GCs | dump: DOB (MiB) | dump: R frames (MiB) |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `B_N1i12_d1024_r1` | 1024 | 15.00 | 1×12 | — | survive | — | 377 | 120 | 1985 | 8 | 0/101 (≥24: 0) | 577 | 132 | 836 / 536 | 0 |  |  |
| `B_N2i12_d1024_r1` | 1024 | 15.00 | 2×12 | — | survive | — | 631 | 240 | 1991 | 16 | 0/102 (≥24: 0) | 602 | 678 | 1396 / 1228 | 0 |  |  |
| `B_N4i12_d1024_r1` | 1024 | 15.00 | 4×12 | — | survive | — | 997 | 480 | 1744 | 32 | 61/104 (≥24: 69) | 605 | 1873 | 2667 / 2620 | 14 |  |  |
| `B_N4i12_d1024_r2` | 1024 | 15.00 | 4×12 | — | survive | — | 877 | 480 | 1948 | 32 | 59/104 (≥24: 65) | 614 | 1840 | 3030 / 2987 | 5 |  |  |
| `B_N4i12_d1024_r3` | 1024 | 15.00 | 4×12 | — | survive | — | 997 | 480 | 1886 | 32 | 59/104 (≥24: 69) | 600 | 1911 | 2780 / 2732 | 12 |  |  |
| `A_N4i12_auto_r1` | auto | 15.00 | 4×12 | — | survive | — | 936 | 480 | 1919 | 32 | 46/118 (≥24: 68) | 614 | 1696 | 3089 / 3032 | 0 |  |  |
| `A_N8_E16_auto_r1` | auto | 16.00 | 8×6 | — | survive | — | 1212 | 544 | 1932 | 32 | 61/116 (≥24: 67) | 559 | 3293 | 4821 / 4790 | 0 |  |  |

### 3.2 Budget search

| Arm | X (MiB) | value (MiB) | N×in-flight | change | outcome | death (s after load start) | U_peak (MiB) | K_peak (MiB) | heap peak | MutationStage active peak | load samples at 32 | writes applied on V | MUTATION_REQ dropped (expired) | client sent / timeouts | forced GCs | dump: DOB (MiB) | dump: R frames (MiB) |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `B_N4i12_d896_r1` | 896 | 15.00 | 4×12 | — | survive | — | 892 | 480 | 1949 | 32 | 61/104 (≥24: 69) | 594 | 1929 | 2685 / 2638 | 63 |  |  |
| `B_N4i12_d768_r1` | 768 | 15.00 | 4×12 | — | survive | — | 756 | 480 | 1920 | 32 | 44/110 (≥24: 64) | 588 | 1776 | 2926 / 2873 | 38 |  |  |
| `B_N4i12_d640_r1` | 640 | 15.00 | 4×12 | — | survive | — | 637 | 480 | 1870 | 32 | 47/110 (≥24: 56) | 603 | 1725 | 3173 / 3102 | 39 |  |  |
| `N8_E15_i6_d1024_r1` | 1024 | 15.00 | 8×6 | — | survive | — | 861 | 540 | 1883 | 32 | 61/105 (≥24: 65) | 606 | 3422 | 4286 / 4250 | 3 |  |  |
| `E16_N4i12_d1024_r1` | 1024 | 16.00 | 4×12 | — | survive | — | 1020 | 512 | 1954 | 32 | 59/104 (≥24: 68) | 551 | 1779 | 2750 / 2722 | 40 |  |  |
| `E16_N4i12_d1024_r2` | 1024 | 16.00 | 4×12 | — | survive | — | 1020 | 512 | 1737 | 32 | 59/103 (≥24: 70) | 572 | 1820 | 2436 / 2405 | 58 |  |  |
| `E16_N4i12_d1024_r3` | 1024 | 16.00 | 4×12 | — | survive | — | 1006 | 512 | 1717 | 32 | 34/113 (≥24: 46) | 579 | 1286 | 2765 / 2677 | 38 |  |  |
| `E16_N4i12_d960_r1` | 960 | 16.00 | 4×12 | — | survive | — | 940 | 512 | 1846 | 32 | 41/111 (≥24: 67) | 577 | 1573 | 2849 / 2797 | 45 |  |  |
| `E16_N4i12_d896_r1` | 896 | 16.00 | 4×12 | — | **direct OOM** (CommitLog.add) | 9 | 877 | 384 | 1616 | 28 | 0/8 (≥24: 1) | 31 | 10 | 7266956 / 2310 | 14 | 368.0 |  |
| `E16_N4i12_d896_r2` | 896 | 16.00 | 4×12 | — | survive | — | 892 | 512 | 1778 | 32 | 30/108 (≥24: 65) | 569 | 1538 | 2652 / 2610 | 85 |  |  |
| `E16_N4i12_d896_r3` | 896 | 16.00 | 4×12 | — | survive | — | 892 | 512 | 1650 | 32 | 32/118 (≥24: 66) | 553 | 1558 | 2549 / 2503 | 60 |  |  |
| `N8_E16_i6_d1152_r1` | 1152 | 16.00 | 8×6 | — | survive | — | 1149 | 544 | 1789 | 32 | 63/104 (≥24: 67) | 536 | 3452 | 4281 / 4252 | 59 |  |  |
| `N8_E16_i6_d896_r1` | 896 | 16.00 | 8×6 | — | survive | — | 892 | 544 | 1779 | 32 | 48/103 (≥24: 66) | 520 | 3462 | 4472 / 4457 | 115 |  |  |
| `N8_E16_i6_d896_r2` | 896 | 16.00 | 8×6 | — | survive | — | 894 | 544 | 1801 | 32 | 48/102 (≥24: 66) | 525 | 3487 | 4305 / 4287 | 125 |  |  |
| `N8_E16_i6_d896_r3` | 896 | 16.00 | 8×6 | — | **direct OOM** (CommitLog.add) | 68 | 892 | 528 | 1842 | 32 | 34/68 (≥24: 44) | 370 | 2321 | 5835 / 5703 | 57 | 496.0 |  |
| `N8_E16_i6_d896_r4` | 896 | 16.00 | 8×6 | — | **direct OOM** (CommitLog.add) | 48 | 892 | 528 | 1697 | 32 | 21/47 (≥24: 27) | 244 | 1578 | 1874831 / 5142 | 59 | 496.0 | 0.4 |

### 3.3 Condition N = 8 · E16 · 1,024 MiB: endpoint, control, interventions

| Arm | X (MiB) | value (MiB) | N×in-flight | change | outcome | death (s after load start) | U_peak (MiB) | K_peak (MiB) | heap peak | MutationStage active peak | load samples at 32 | writes applied on V | MUTATION_REQ dropped (expired) | client sent / timeouts | forced GCs | dump: DOB (MiB) | dump: R frames (MiB) |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `N8_E16_i6_d1024_r1` | 1024 | 16.00 | 8×6 | — | **direct OOM** (CommitLog.add) | 54 | 1021 | 544 | 1699 | 32 | 29/53 (≥24: 36) | 276 | 1748 | 7591 / 5161 | 57 | 752.0 |  |
| `N8_E16_i6_d1024_r2` | 1024 | 16.00 | 8×6 | — | survive | — | 1004 | 544 | 1764 | 32 | 60/104 (≥24: 68) | 543 | 3433 | 4403 / 4385 | 69 |  |  |
| `N8_E16_i6_d1024_r3` | 1024 | 16.00 | 8×6 | — | survive | — | 1020 | 544 | 1825 | 32 | 51/103 (≥24: 63) | 523 | 3450 | 4680 / 4656 | 99 |  |  |
| `N8_E16_i6_d1024_r4` | 1024 | 16.00 | 8×6 | — | survive | — | 1021 | 544 | 1745 | 32 | 54/104 (≥24: 69) | 524 | 3432 | 4493 / 4472 | 98 |  |  |
| `N8_E16_i6_d1024_r5` | 1024 | 16.00 | 8×6 | — | survive | — | 1020 | 544 | 1824 | 32 | 53/104 (≥24: 67) | 519 | 3509 | 4054 / 4031 | 83 |  |  |
| `N8_E16_i6_d1024_r6` | 1024 | 16.00 | 8×6 | — | survive | — | 1020 | 544 | 1941 | 32 | 53/104 (≥24: 66) | 509 | 3497 | 4264 / 4248 | 105 |  |  |
| `N8_E16_i6_d1024_r7` | 1024 | 16.00 | 8×6 | — | survive | — | 1021 | 544 | 1742 | 32 | 55/104 (≥24: 71) | 519 | 3448 | 4610 / 4585 | 103 |  |  |
| `N8_E16_i6_d1024_r8` | 1024 | 16.00 | 8×6 | — | survive | — | 1020 | 528 | 1723 | 32 | 55/104 (≥24: 70) | 539 | 3408 | 4641 / 4621 | 67 |  |  |
| `N8_E16_i6_d1024_r9` | 1024 | 16.00 | 8×6 | — | survive | — | 1021 | 544 | 1701 | 32 | 58/105 (≥24: 66) | 551 | 3447 | 4496 / 4473 | 64 |  |  |
| `N8_E16_i6_d1024_r10` | 1024 | 16.00 | 8×6 | — | survive | — | 1022 | 544 | 1779 | 32 | 58/103 (≥24: 67) | 519 | 3336 | 4938 / 4918 | 102 |  |  |
| `N8_E16_i6_d1024_r11` | 1024 | 16.00 | 8×6 | — | **direct OOM** (CommitLog.add) | 38 | 1022 | 544 | 1938 | 32 | 17/37 (≥24: 23) | 183 | 1050 | 9754 / 4909 | 46 | 624.0 | 0.1 |
| `N8_E16_i6_d1024_r12` | 1024 | 16.00 | 8×6 | — | survive | — | 1023 | 544 | 1730 | 32 | 55/116 (≥24: 64) | 531 | 3192 | 4399 / 4374 | 97 |  |  |
| `N8_E16_i6_d1024_r13` | 1024 | 16.00 | 8×6 | — | survive | — | 1023 | 544 | 1871 | 32 | 56/139 (≥24: 66) | 543 | 3368 | 4738 / 4715 | 56 |  |  |
| `N8_E16_i6_d1024_r14` | 1024 | 16.00 | 8×6 | — | survive | — | 1017 | 544 | 1730 | 32 | 58/116 (≥24: 67) | 544 | 3352 | 4667 / 4638 | 80 |  |  |
| `G_N8_512k_i192_d1024_r1` | 1024 | 0.50 | 8×192 | — | survive | — | 594 | 544 | 1862 | 32 | 91/110 (≥24: 91) | 18152 | 31527 | 49578 / 35167 | 0 |  |  |
| `G_N8_512k_i192_d1024_r2` | 1024 | 0.50 | 8×192 | — | survive | — | 612 | 544 | 1952 | 32 | 89/111 (≥24: 89) | 18246 | 31544 | 49657 / 35825 | 0 |  |  |
| `G_N8_512k_i192_d1024_r3` | 1024 | 0.50 | 8×192 | — | survive | — | 594 | 544 | 1968 | 32 | 88/110 (≥24: 88) | 17945 | 31906 | 49743 / 35848 | 0 |  |  |
| `I_cw8_N8_E16_d1024_r1` | 1024 | 16.00 | 8×6 | concurrent_writes=8 | survive | — | 801 | 544 | 1952 | 8 | 0/105 (≥24: 0) | 532 | 3510 | 4047 / 3983 | 0 |  |  |
| `I_cw8_N8_E16_d1024_r2` | 1024 | 16.00 | 8×6 | concurrent_writes=8 | survive | — | 800 | 544 | 1968 | 8 | 0/105 (≥24: 0) | 545 | 3498 | 4043 / 3985 | 0 |  |  |
| `I_cw8_N8_E16_d1024_r3` | 1024 | 16.00 | 8×6 | concurrent_writes=8 | survive | — | 842 | 544 | 1985 | 8 | 0/105 (≥24: 0) | 534 | 3503 | 4070 / 4016 | 0 |  |  |
| `I_onheap_N8_E16_d1024_r1` | 1024 | 16.00 | 8×6 | -Dcassandra.dob.allocate_type=ONHEAP | survive | — | 202 | 528 | 1912 | 32 | 56/104 (≥24: 63) | 569 | 3469 | 4207 / 4181 | 0 |  |  |
| `I_onheap_N8_E16_d1024_r2` | 1024 | 16.00 | 8×6 | -Dcassandra.dob.allocate_type=ONHEAP | survive | — | 230 | 544 | 1932 | 32 | 55/105 (≥24: 64) | 573 | 3431 | 4152 / 4131 | 0 |  |  |
| `I_onheap_N8_E16_d1024_r3` | 1024 | 16.00 | 8×6 | -Dcassandra.dob.allocate_type=ONHEAP | survive | — | 216 | 544 | 1992 | 32 | 54/105 (≥24: 59) | 552 | 3476 | 4129 / 4106 | 0 |  |  |

Offered vs applied (client `sent` × value size / 90 s; V's applied writes × size / 90 s): endpoint
`N8_E16_i6_d1024_r2` 783 / 97 MiB/s; control G r1–r3 275–276 / 100–101 MiB/s; `concurrent_writes: 8` r1 719 / 95;
ONHEAP r1 748 / 101; N = 4 E15 r1 444 / 101. Every shape is bound by V's SSD (≈ 100 MiB/s applied); 97–99 % of the
large client writes time out at the coordinator (2 s), V drops 1,300–3,500 expired `MUTATION_REQ` per arm, and each
coordinator writes ≈ 4–8.5 GB of hints per arm (wiped between arms). GC: worst 60 s STW share 6–13 % in the
endpoint, ONHEAP and control arms checked (`gcwin.py`); no service loss, no heap OOM in any arm.

### 3.4 What the writers do (thread dumps, `B_N4i12_d1024_r1`)

`jcmd Thread.print` every 5 s ([`logs-run2/B_N4i12_d1024_r1-jstack.csv`](logs-run2/B_N4i12_d1024_r1-jstack.csv),
[excerpt](logs-run2/B_N4i12_d1024_r1-threads-excerpt.txt)): in 12 of the 17 dumps taken during the load all 32 `MutationStage` threads are
parked in `MemtableAllocator$SubAllocator.allocate` (after `CommitLog.add`, scratch already trimmed) while
`MemtablePostFlush` waits on a commit-log segment monitor; in one dump 20 are inside `CommitLog.add` (2 in `expandToFit`, 1
waiting for a segment, 17 elsewhere in it: copy / allocation). The 1 s samples show the resulting cycle in every saturated arm: U
≈ 170–200 MiB while the writers wait, then within one second the next ≈ 32 admitted messages deserialize and
serialize together and U jumps to 700–1,020 MiB (e.g. `N8_E16_i6_d1024_r1`, s after load start: U MiB / active —
46: 992/32, 47: 208/32 … 50: 203/0, 51: 1,003/29, 53: 971/29, OOM at 54; `r11`: 31: 1,003/32 … 36: 923/24,
37: 1,019/31, OOM at 38; `N8_E16_i6_d896_r3`: 61: 811/24 … 67: 875/24, OOM at 68). `WaitingOnSegmentAllocation`
grows by 89–271 per arm with E15 at N = 4, 294–447 with E16 at N = 4 and 394–725 with E16 at N = 8.

### 3.5 Initiating failure and holders (the five failure dumps attributed)

First error in all five failing arms ([`logs-run2/*-first-oom.txt`](logs-run2/)): a `MutationStage` thread,
**JDK counter** — `java.lang.OutOfMemoryError: Direct buffer memory` at `Bits.reserveMemory` ← `ByteBuffer.allocateDirect`
← `DataOutputBuffer$1$1.allocate(:87)` ← `expandToFit(:178)` ← `BufferedDataOutputStreamPlus.writeByte` ←
`UnfilteredSerializer.writeEndOfPartition(:415)` (the S → 2S doubling after the value write) ← … ←
`Mutation$MutationSerializer.serialize(:414)` ← **`CommitLog.add(CommitLog.java:308)`** ← `Keyspace.applyInternal(:625)`
← `Mutation.applyFuture` ← **`MutationVerbHandler.applyMutation(:75)`** ← `InboundSink` ← `InboundMessageHandler$ProcessMessage.run(:430)`.
No Netty `OutOfDirectMemoryError` in any arm.

Dumps (Cassandra's forced heap OOM, ≈ 0.1 s after the first error; `hprof_direct.py`, 6 hops;
[`logs-run2/*-direct-holders.txt`](logs-run2/)):

| Holder (MiB) | `N8_E16_i6_d1024_r1` | `N8_E16_i6_d1024_r11` | `N8_E16_i6_d896_r3` | `N8_E16_i6_d896_r4` | `E16_N4i12_d896_r1` |
|---|---|---|---|---|---|
| budget X | 1,024 | 1,024 | 896 | 896 | 896 |
| **U1 `DataOutputBuffer` scratch** (`DataOutputBuffer$1$1.buffer`; 33,552,470 B = 2S buffers) | **752** (80 %) | **624** (74 %) | **496** (68 %) | **496** (71 %) | **368** (58 %) |
| released 2S buffers awaiting the Cleaner (freed by the failing / finishing writers) | 0 | 32 | 64 | 32 | 96 |
| P networking `BufferPool` chunks, no live consumer (17 × 8 MiB: the pool at its 128 MiB cap + 1 chunk-cache chunk) | 136 | 136 | 136 | 136 | 136 |
| hints-writer buffer (idle baseline) | 32 | 32 | 32 | 32 | 32 |
| R live receive frames (queued LARGE / being decoded) | 0 | 0.2 | 0 | 0.4 | 0 |
| other (one 16 MiB buffer; NIO; storage I/O) | 19 | 19 | 3 | 3 | 2 |
| JDK owners total at dump | 939.5 | 843.6 | 731.5 | 699.6 | 634.5 |
| Netty's separate counter (internode event-loop arenas; limit = X, not exhausted) | 176 | 176 | 160 | 160 | 160 |
| commit-log segments (mmap, not counted by either) | 800 | 704 | 736 | 800 | 544 |

The live DOB scratch is the largest holder in every dump (58–80 % of JDK owners); the rest is the networking pool
at its retention cap (136 MiB, present in every saturated arm, including the survivors and the control) and the
32 MiB hints-writer buffer. **Live receive frames are ≈ 0 at every failure**: the messages being applied have
already been deserialized onto the heap and their frames returned to the pool. Owners total < X because the
failing and finishing writers free their buffers in the ≈ 0.1 s before the dump. Physically V held ≈ X (JDK) +
160–176 MiB (Netty) of direct memory at failure.

### 3.6 Host and side events

- Platform: all five m400s idle apart from this run (load 0 before start). Each arm regenerated all instances;
  no arm was invalid. `oom_kill` = 0 in every arm (V's 40 GiB safety scope never bound).
- The 1 s sampler under-reads the transient peak: U_peak at the cap is 1,017–1,023 in the 1,024 arms, and the forced
  GCs (46–105 per arm at N = 8 · E16 · 1,024) show the counter reached the limit many times per arm.
- Two dumps (`N8_E16_i6_d1024_r1`, `r11`) were read from V with `ionice -c3` while later arms ran (≈ 40 s each).
- Coordinators: no coordinator heap OOM (`C*-heapoom.txt` 0 in every arm).

---

## 4. Conclusion

**Mechanism reached at the deployment-resolved budget, endpoint not reproducible enough.** Delivered as internode
`MUTATION_REQ`s to a replica, the U1 holder behaves as predicted and without B9's interference: the receive queue
admits ≈ 8 large messages per coordinator (K = 120 / 240 / 480 / 544 MiB at N = 1 / 2 / 4 / 8), four or more
coordinators keep all 32 `MutationStage` threads busy (active = 32 in ≈ 40–60 % of the 1 s load samples), and each burst puts
up to 32 thread-local scratch buffers of 2S into `CommitLog.add` at once. With **16 MiB − 1 KiB mutations the
unconstrained demand is U_peak = 1,212 MiB** (auto, N = 8) = 50 baseline + 136 networking pool + 32 × 2S16 (1,024):
every writer holding its doubled buffer at the same moment, 190 MiB above the 4 GiB-node budget. At **1,024 MiB the
counter is touched in every arm (46–105 forced GCs) and a U1 direct OOM occurs in 2 of 14 arms** (N = 8, E16; 38 and
54 s into the load); at 896 MiB in 2/4 (N = 8) and 1/3 (N = 4). 1,152 MiB survives (0/1, at the cap). With the
**15 MiB mutations** of the original spec the demand stays lower (U_peak 936 at auto, N = 4; 861–997 at 1,024) and
**no saturated arm failed** down to 640 MiB (0/8). As in run 1, `Bits.reserveMemory`'s forced GC + ≈ 0.5 s backoff usually lets
another writer finish its copy and free its scratch first; the OOM needs a burst whose holders stay in
`CommitLog.add` past that window (the E16 arms wait on segment allocation 2–3× as often as the E15 arms).

**Classification (protocol table).** The initiating holder is the in-flight DOB scratch, which no control's contract
covers (U1 → **unprotected accumulation**; implicit bound `concurrent_writes` × 2–3 × mutation size). The receive
queue stays within its contract (K ≤ 544 = G + N·Q) and its live frames are ≈ 0 at failure; the networking pool sits at
its 128 MiB retention cap; no counter is exceeded → no bypass. **Not mixed**: the OOM does not need receive frames
(researcher's holder rule) — what sits beside the scratch at failure is the standing pool + hints buffer present in
every arm (186 MiB). Workload within documented limits: 16,776,192 B values pass `max_mutation_size` (16 MiB,
checked on V by `MutationVerbHandler`), the 16 MiB native frame and the 128 MiB `internode_max_message_size`; the
excess is the system's own copy (serialized form ×2 by doubling). The overload itself (≈ 780 MiB/s offered to a
100 MiB/s replica disk, 97–99 % client timeouts) is a reachable condition, not an accepted input limit; it is what
keeps 32 messages in flight.

**Attribution at N = 8 · E16 · 1,024.**
- Control G (512 KiB values, same N, same in-flight bytes per client): 0/3, U_peak 594–612 with K at its full 544
  MiB — the same receive-queue occupancy and the same applied bytes/s (100 vs 97 MiB/s) without large scratch
  buffers. Offered bytes/s is lower (276 vs 783 MiB/s): the small writes partly succeed, so the timeout-bound
  offered rates do not match; the applied rate and K do.
- `concurrent_writes: 8`: 0/3, U_peak 800–842 (8 scratch holders + frames of up to 26 queued messages), applied
  95–97 MiB/s vs the endpoint's 90–98 — removes the endpoint without losing throughput (the disk is the bottleneck). Headroom 18–22 %.
- `-Dcassandra.dob.allocate_type=ONHEAP` (moves only the scratch to the heap; the 4.x behaviour, a JVM property):
  0/3, direct U_peak 202–230 (frames + pool + baseline), heap peak 1,912–1,992 of 2,048 MiB, worst 60 s STW 6–9 %, no
  heap OOM, applied 98–102 MiB/s. The receive path alone uses ≈ 150–180 MiB of direct memory.
- Multiplicity: N = 1 / 2 (receive-queue-bound 8 / 16 writers) peak at 377 / 631 MiB at the same applied rate.
- Size: E15 instead of E16 at the same budget: 0/4 at 1,024 (N = 4 ×3, N = 8 ×1).

**Relation to run 1 and S1.** Run 1 (x86, V as coordinator) failed only at 576 MiB (2/14) and lost 4 arms to
Netty's counter; here no Netty endpoint occurs (V's Netty counter 160–176 MiB, internode arenas) and the largest
failing budget rises to **1,024 MiB** (2/14), the value `cassandra-env.sh` resolves for a 4 GiB node with an
automatic heap. S1 (stacked, x86, loopback) failed at 768 MiB 3/3 with the extra standing pools of its layers.
Not compared arm-by-arm (platform rule).

**Status by condition (proposed; the researcher decides):**

| Condition (heap 2 GiB, all constraints default) | Endpoint (U1 direct OOM) | Control | Intervention | Proposed status |
|---|---|---|---|---|
| **N = 8 · E16 · 1,024 MiB** (4 GiB-node resolution) | **2/14** | G 0/3 | `concurrent_writes: 8` 0/3; ONHEAP 0/3 | **`candidate`** (V1 unmet: 2 < 3). If promoted: `deployment` (V6, V7 met without override). |
| N = 8 · E16 · 896 MiB | 2/4 | — (G and interventions run at 1,024 only) | — | `candidate` (V1 unmet; boundary reading; ≥ 512 MiB but below the 4 GiB-node resolution) |
| N = 4 · E16 · 896 / 960 / 1,024 | 1/3 / 0/1 / 0/3 | — | — | boundary readings |
| N = 8 · E16 · 1,152; auto (15,872) | 0/1; 0/1 (U_peak 1,212) | — | — | survive (n = 1) |
| E15 (15 MiB) · N = 4 at 640–1,024 and auto, N = 8 at 1,024 | 0/8 | — | — | survive within the tested range (n = 1–3 per budget; not a negative by V1) |
| Saturation sweep N = 1 / 2 / 4 (E15, 1,024) | 0/1 each | — | — | mechanism readings (receive-queue bound 8 per coordinator) |

**V1–V7 (condition N = 8 · E16 · 1,024 MiB):**

| | Evidence | Met |
|---|---|---|
| V1 repetition | `N8_E16_i6_d1024_r1..r14`: 2/14 (r1, r11) | **no** |
| V2 matched control | `G_N8_512k_i192_d1024_r1..r3`: 0/3, U_peak 594–612, K 544 (offered bytes/s not matched, applied matched) | yes (with that caveat) |
| V3 measurement | U = JMX direct (1 s) independent of K; per-holder U from 2 dumps at this condition (+ 3 at 896); no counter covers the scratch | yes |
| V4 intervention | `concurrent_writes: 8` 0/3 at 95–97 vs 90–98 MiB/s applied; also ONHEAP 0/3 | yes |
| V5 initiating failure | first error + stack (`MutationVerbHandler` → `CommitLog.add:308` → `expandToFit`, JDK counter) and dumps with the DOB scratch as the largest holder, 2/2 | yes (n = 2) |
| V6 default constraints | yaml diff environment-only on all nodes; no `-D`; 16,776,192 B < `max_mutation_size` | yes |
| V7 acceptable budget | heap 2,048 (ideal); direct 1,024 = the 4 GiB-node resolution, ≥ 512 (standing rule) | yes (review pending) |

**Limits.**
- V1: the endpoint is stochastic (≈ 1/7 per 90 s arm at 1,024, ≈ 1/2 at 896 with N = 8); 14 arms at 1,024 gave 2.
  Reaching ≥ 3 would need ≈ 8–15 more arms (≈ 40–70 min on these nodes), or acceptance of 896 MiB (2/4, needs its own
  control/intervention arms).
- The failing workload uses values at the very top of the accepted size (16 MiB − 1 KiB). With the 15 MiB values of
  the original spec nothing failed (0/8 saturated arms, down to 640 MiB); E15's lower failure rate is consistent with fewer
  simultaneous 2S holders (U_peak 936 unconstrained) and fewer segment-allocation waits, but its cause was not
  isolated.
- One storage type (a 100 MB/s SATA SSD) on aarch64; the bursts come from memtable-allocation stalls behind slow
  commit-log/flush I/O, so faster storage may change the holder overlap. No x86 positive (not needed, researcher).
- N = 8 needs a second coordinator per node at an alias IP (environment); N = 4 E16 at 1,024 was 0/3.
- The 1 s sampler under-reads transient peaks; the dumps are ≈ 0.1 s after the error, after some holders released.

**Next step (if the researcher wants V1).** 10–15 more clean-start arms of N = 8 · E16 · 1,024 (≈ 1 h), or fix V1 at
896 MiB with control and `concurrent_writes: 8` ×3 there (≈ 45 min). The B9 side lead (B = bypass investigation) is
unaffected: no client frame reached V.

**Cleanup (16:30 EST).** After every arm all instances, clients and samplers were stopped and the instance
directories wiped; at the end on all five nodes: 0 `java` processes, no `u1r2-*` scope, nothing listening on 7000;
alias IPs 10.10.1.12–.15 removed; **linger disabled on all five** (`Linger=no`). Kept: `ms0625:/mydata/u1r2/runs/`
(5.4 GB, five failure dumps 0.8–1.1 GB each with `direct-holders.txt`), coordinators' `/mydata/u1r2/runs/` (13 MB
each: client logs, coordinator `system.log`s), `/mydata/u1r2/cassandra` (build copy) and `/mydata/u1r2/h` (harness)
on each node; `pc96:/mydata/u1r2/mirror/` (44 MB). The S2/B8 directories on the nodes were only read.
