# B6 run 2 — replica disk stall, default timeouts, no Byteman, 4 coordinators

**Direction / sub-direction:** bypass · accounting mismatch (receive side). **Allocation domain:**
replica heap holding deserialized `Mutation`s that wait on a blocked `MutationStage` while charged to
the internode receive queue at on-wire size. **Capacity regime:** default (4 / 128 / 512 MiB).
**Budget regime:** replica heap 8 GiB (deployment-like) and 6 GiB. **Pinned source:** cassandra-5.0.9,
local copy `/mydata/b6/cassandra`. **Date:** 2026-11-10/11. **Design:**
[`design/B6-run2-design.md`](design/B6-run2-design.md). **Follows:**
[run 1](internode_application_queue_capacity--accounting-mismatch--run1.md).

**Verdict: run 1's deviations are not needed for the memory effect; a hard OOM is intermittent.**
With **default timeouts, no Byteman, default `concurrent_writes`**, and a 30 s storage stall on the
replica, tiny-cell writes pushed the replica to **98.7–99.5% of heap live in 5/5 map arms** (8 GiB ×2,
6 GiB ×3), with back-to-back Full GCs for **80–123 s (79–120 s of pause, ≈ 97% of the window)**; one
6 GiB arm threw a real **heap OOM** and was killed. The matched **blob** payload had **0 Full GCs in
4/4** stall arms while carrying ≈ 4× more on-wire traffic. **Receive endpoint reserve 8 MiB** removed
the effect (max 21.6% live, 1 Full GC). Without a stall the replica stayed ≤ 27% live. A full disk
**hang** (600 s write delay) instead froze the whole replica JVM in 2/3 map arms (≈ 136–138 s
"local pause", nothing accumulates) and **OOM-killed an 8 GiB replica in 1/3**.
Per protocol the main outcome is **GC-driven service loss** (not OOM) with **2 heap OOMs** among 8
map stall/hang arms.

## Summary

- **Root cause:** internode queues limit messages by **on-wire size**, but a queued write lives on the
  heap as Java objects. A 1000-tiny-cell write is 10.8 KiB on the wire and ≈ 180–210 KiB on heap
  (≈ 17–20×, ~200 B of object overhead per cell), so a receive queue within its 528 MiB limit can hold
  ≈ 9 GiB of heap. Expired writes are only removed when a write thread runs them.
- **Trigger:** a replica whose writes stall (here a slow/stalled disk): write threads block, received
  writes pile up on heap.
- **Conclusion:** reproduced with default timeouts, default threads and an 8 GiB heap — 99% heap and
  ≈ 2 min of nonstop Full GC in 5/5 stall runs; real heap OOM in 2/8 stall/hang runs. Mostly
  **service loss, not a deterministic OOM**.
- **Proof it is the accounting:** blob writes of the same on-wire size (4× the traffic) never hit a
  Full GC; a receive endpoint reserve of 8 MiB removes the problem.
- **Interpretation:** documented behaviour (limits are on-wire bytes) → sizing gap, not a code bug.

---

## 1. Constraint and protection map

As run 1, receive side: `AbstractMessageHandler.acquireCapacity` charges the frame's on-wire size
(per connection 4 MiB, per endpoint 128 MiB, global 512 MiB); a small message (< 64 KiB) is
deserialized on arrival (`InboundMessageHandler.java:156`) and waits on `MutationStage` as heap objects;
capacity is released after processing; an expired message is dropped **only when a stage thread runs
it** (`:408–423`). With 4 senders the on-wire ceiling is 4·4 + 512 = 528 MiB; at run 1's R ≈ 17 that is
≈ 9 GiB of heap. Contract: on-wire bytes (`cassandra.yaml`). C = 528 MiB on-wire; K = Σ
`internode_inbound.using_bytes`; U = live heap (GC log after-Full-GC occupancy; class histogram in P1).

## 2. Executed design (2026-11-10)

Single host node0 (`jason92-325405`, 32 cores, 125 GiB), six instances on loopback
(`harness-run2/ctl.sh`): **V** 127.0.0.11 (dc=v, replica; data, commit log and hints on
`/mydata/b6/slow`, an ext4 on a **dm-delay** device over a loop file), **F** 127.0.0.12 (dc=f, fast
replica, 8 GiB), **S1–S4** 127.0.0.13–16 (dc=c, coordinators, 8 GiB). `NetworkTopologyStrategy
{v:1, f:1}`, CL=ONE, hints off, key/counter cache 0, **all timeouts default**, no Byteman, default
`concurrent_writes`.

Client: `harness-run2/B6Load.java` (Java driver 3.12.1, async, 256 in flight per coordinator, value
serialized once and bound with `setBytesUnsafe`), one session per coordinator. Map 1000 entries
(10.80 KiB on-wire) or blob 11 000 B (10.80 KiB). Throughput with a healthy replica ≈ 2.1k map
inserts/s — the same as run 1's Python client, so the limit is server-side (cell apply rate), not the
client.

Arm (`harness-run2/arm.sh`, clean start): load 150 s on S1–S4; at t = 20 s V's disk write delay is
set to the stall value (`slowdisk.sh`); at t = 150 s back to 0; V observed 60 s more. Outcome from V's
GC log (`gcsum.sh`): `ReportJavaOutOfMemory`, Full GCs with > 95% of heap live, and the longest
"local pause" reported by V's failure detector.

**Configuration audit:** capacities default (intervention: `internode_application_receive_queue_reserve_endpoint_capacity`
8 MiB); V heap 8/6 GiB (budget); disk stall = environment fault injection (dm-delay); hints off
(supporting deviation); topology/addresses/caches (environment).

## 3. Results

Evidence: [`logs-run2/arm-outcomes.txt`](logs-run2/arm-outcomes.txt),
[`logs-run2/P1-probe.txt`](logs-run2/P1-probe.txt). Raw: `/mydata/b6/runs2/<arm>/` on node0.

### 3.1 30 s stall (write delay 30 000 ms from t = 20 s to t = 150 s)

| Arm | V heap | Payload | Outcome | Max live after Full GC | Window of Full GCs > 95% live (pause total) |
|---|---|---|---|---|---|
| P1 (probe) | 8 GiB | map | **service loss, no recovery** (still at 99.4% 3 min after the stall; killed) | 8 141 MiB (99.4%) | 22:01:34 → 22:06:57+ |
| R2_V8g_map_stall_r1 | 8 GiB | map | service loss, recovered | 8 088 MiB (98.7%) | 107 s (104 s) |
| R2_V8g_map_stall_r2 | 8 GiB | map | service loss, recovered | 8 136 MiB (99.3%) | 109 s (106 s) |
| R2_V6g_map_stall_r1 | 6 GiB | map | service loss, recovered | 6 088 MiB (99.1%) | 123 s (120 s) |
| **R2_V6g_map_stall_r2** | 6 GiB | map | **heap OOM, JVM killed** | 6 111 MiB (99.5%) | 80 s (79 s) |
| R2_V6g_map_stall_r3 | 6 GiB | map | service loss, recovered | 6 099 MiB (99.3%) | 123 s (119 s) |
| R2_V8g_blob_stall_r1–r3 | 8 GiB | blob | survived, **0 Full GCs** | — | — |
| R2_V6g_blob_stall_r1 | 6 GiB | blob | survived, **0 Full GCs** | — | — |
| R2_V8g_map_nostall | 8 GiB | map | no stall: 15 Full GCs, healthy | 2 207 MiB (26.9%) | — |
| **R2_V8g_map_stall_rsv8m** | 8 GiB | map | **intervention** (receive endpoint reserve 8 MiB): survived | 1 770 MiB (21.6%), 1 Full GC | — |

Blob arms completed 1.09–1.27 M inserts (≈ 4× the on-wire bytes of the map arms' ≈ 0.27–0.31 M) and
still had no Full GC. Clients saw few errors in map arms (F acks CL=ONE), so the replica's distress is
invisible to the client; blob arms had ≈ 27–31 k write timeouts from F under its own load.

P1 live histogram in the spiral: **37 217 `Mutation`s / 37.2 M `ArrayCell`s waiting** (≈ 393 MiB
on-wire, below C = 528 MiB) plus ≈ 13 M `BufferCell`s (memtable); 7.95 GiB live of 8 GiB.
`MutationStage` 20 s into the stall: 32 active, 30 411 pending. The sampler's JMX/CQL queries to V time
out during the spiral, so K during the spiral is known from the histogram (P1) only; the coordinator
send queues stayed ≤ 2.5 MiB with tens of thousands of expired messages (2 s deadline at the sender).

Why it does not always OOM: with a 30 s write delay the commit-log sync completes every ~30 s, the
blocked stage threads advance in bursts, and each burst drops expired messages; heap settles at the
edge (each Full GC frees ≈ 16 MiB), so G1 rarely fails an allocation outright.

### 3.2 Full disk hang (write delay 600 000 ms, cleared at t = 150 s)

| Arm | V heap | Payload | Outcome | Longest JVM "local pause" |
|---|---|---|---|---|
| R2H_V8g_map_hang_r1 | 8 GiB | map | whole JVM frozen, no accumulation (19% max) | **137.9 s** |
| **R2H_V8g_map_hang_r2** | 8 GiB | map | **heap OOM, JVM killed** (99.6% live, 42 Full GCs, 106 s pause) | 39.3 s |
| R2H_V6g_map_hang_r1 | 6 GiB | map | whole JVM frozen, no accumulation (23% max) | **135.7 s** |
| R2H_V8g_blob_hang_r1 | 8 GiB | blob | survived, 0 Full GCs | 39.3 s |

A full hang usually stops the **entire** replica JVM (likely a thread blocked in commit-log mmap /
dirty-page writeback delaying safepoints — not verified), so it stops reading the network and nothing
accumulates. When the JVM keeps running (r2) the receive queues fill and the 8 GiB replica OOMs.

## 4. Conclusion and limits

**The mismatch reproduces under realistic conditions.** Default timeouts, default thread pools, a
deployment-sized 8 GiB heap and four ordinary coordinators: a replica whose writes stall on storage
fills its heap to ≈ 99% with waiting tiny-cell mutations while the on-wire counters stay at or below
the 528 MiB ceiling (P1: 393 MiB on-wire waiting ↔ 7.95 GiB live). The blob control (same on-wire size,
4× the traffic) never triggers a Full GC, and capping the receive endpoint reserve at 8 MiB removes the
effect — the charged unit, not the traffic volume, decides the outcome.

**Outcome type:** mostly **GC-driven service loss** (≈ 97% of an 80–123 s window spent in Full GC; in
P1 no recovery after the stall), which the protocol does not count as OOM; **2 genuine heap OOMs**
(6 GiB stall r2, 8 GiB hang r2) out of 8 map stall/hang arms. Not a deterministic OOM.

**Limits:**
- Fault injection is a storage stall via dm-delay on a loop file (one host; all instances share CPU).
- 30 s and 600 s write delays are two points; the outcome depends on whether the JVM freezes (hang)
  or advances in bursts (30 s).
- Hints off (supporting deviation). Coordinator heaps were not measured in run 2 (8 GiB, default
  deadlines — run 1 showed the coordinator side needs long deadlines or ≥ 66 MiB/s per destination).
- Intervention n = 1; blob 6 GiB n = 1; V-side K during the spiral only from one histogram.
- The OOM thread/stack was not preserved (`OnOutOfMemoryError` kill; heap dumps disabled in run 2).

**Next:** heap dumps on for one OOM arm; repeat the intervention ×3; vary the stall length (5 / 15 /
60 s) to map service loss vs OOM; measure the coordinators; check JIRA for receive-queue/heap issues
(CASSANDRA-15066 introduced these limits) before reporting upstream.

All instances stopped and the delay device reset to 0 after each batch (`pgrep java` = 0;
`dmsetup table b6slow` shows delay 0). The dm-delay device and loop file remain on node0 for reuse.
