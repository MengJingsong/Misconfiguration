# B6 run 1 — internode queues charge on-wire bytes; tiny-cell mutations hold ~17–20× that on heap

**Direction / sub-direction:** bypass · accounting mismatch (protocol *Classification by measurement*:
U > C while the control's counter K ≤ C). **Allocation domains:** (1) coordinator heap holding
`Mutation`s bound for a slow replica — in the send queue and, after flush, in the write callback;
(2) replica heap holding deserialized `Mutation`s waiting on `MutationStage` while charged to the
receive queue. **Capacity regime:** default internode queue capacities (4 MiB / 128 MiB / 512 MiB,
send and receive). **Budget regime:** deliberately tightened diagnostic heap (`-Xmx 2G`) on the
measured instance; others ample. **Pinned source:** cassandra-5.0.9 (`b5f2a54210`), local copy
`/mydata/b6/cassandra` (repository `8b83bbfb`). **Date:** 2026-11-10.
**Design:** [`design/B6-design.md`](design/B6-design.md) (amendments in §2).

**Verdict: bypass (accounting mismatch) confirmed on both sides; heap OOM reproduced with
supporting deviations.** A mutation of 1000 tiny map cells is 10.80 KiB on the wire but
**213 KiB on the coordinator heap and 181 KiB on the replica heap (R ≈ 19.7× / 16.7×)**; a blob
mutation of the same on-wire size is 23.6 KiB on both (R ≈ 2.2×). With every queue counter at or
below its 132 MiB contract, live heap reached **5.6 GiB on the coordinator and 2.2 GiB on the
replica**. At a 2 GiB heap: coordinator **3/3 heap OOM** (map) vs **0/3** (blob); replica **3/3
heap OOM** (+1 unplanned in A1) vs **0/3**. Shrinking both endpoint reserves to 8 MiB removed both
OOMs (n=1 each). The coordinator OOMs happened with its **send queue empty** (K = 0): the heap was
filled by mutations already flushed and held by the write callback, which no sender counter
charges. **Conditional on** a slow replica (Byteman), 60 s write and native-transport timeouts,
hints off and a tightened heap; at **default timeouts** no OOM was reached at the client rate this
single host could generate (≈ 2.3k inserts/s ≈ 25 MiB/s on-wire; ≥ 66 MiB/s is needed) —
unresolved, not negative.

---

## 1. Constraint, contract, protection map

| Field | Evidence |
|---|---|
| Control | Internode application queues. Send: `OutboundConnection.enqueue` charges `message.serializedSize()` (`OutboundConnection.java:330,1045–1048`) to per-link 4 MiB, then endpoint 128 MiB + global 512 MiB reserves; on failure prunes expired once, then **drops** (`:335–345`, `onOverloaded :456`). Receive: `AbstractMessageHandler.acquireCapacity` charges the frame size to the same three tiers; on failure the connection stops reading (back-pressure). |
| Contract | `cassandra.yaml`: "These limits are applied to the **on-wire size** of the message." Capacity per destination per link type: 4 + 128 = **132 MiB**. |
| Allocation / ownership | Sender: `Message<Mutation>` objects on heap while queued (serialized only at flush). After flush, the write handler keeps the `Mutation` as `hintOnFailure` (`Mutation.hintOnFailure()` returns `this`, `Mutation.java:158`; `AbstractWriteResponseHandler.java:81,309`) until the replica answers or the callback expires — even with hints disabled. Receiver: small messages are deserialized, then wait on `MutationStage` as heap objects; receive capacity is released only after processing. |
| Uncovered memory | Heap size of a `Mutation` is not its on-wire size. After flush, the sender's copy is charged to **no** sender counter (only to the replica's receive queue, in another JVM). |
| Lifetime | Until processed or expired. Expiry deadline = min(`write_request_timeout`, `native_transport_timeout` from client admission) (`Dispatcher.RequestTime.computeDeadline`, `Dispatcher.java:238–245`) — found during A0 (§2). |
| Budget | Java heap (`-Xmx`). |

C = 132 MiB on-wire per destination (one link type: these mutations are < 64 KiB → SMALL).
K = `internode_outbound.pending_bytes` (sender) / `internode_inbound.using_bytes` (receiver).
U = live heap from `jcmd GC.class_histogram` (full GC) minus the idle baseline.

## 2. Executed design and amendments (2026-11-10)

Single host `node0.jason92-325405` (32 cores, 125 GiB, Ubuntu 22.04, OpenJDK 11.0.33, Ant 1.10.12),
three instances on loopback, `GossipingPropertyFileSnitch`, one token each, hints off, key/counter
cache 0, keyspace `NetworkTopologyStrategy {v:1, f:1}`, CL=ONE:

| Instance | Address | Role | Notes |
|---|---|---|---|
| V | 127.0.0.11 dc=v | slow replica | Byteman 100 ms at `MutationVerbHandler.doVerb` entry, `concurrent_writes: 2` (drains ≈ 20 mutations/s) |
| F | 127.0.0.12 dc=f | fast replica, 8 GiB | acks CL=ONE so the client never waits on V |
| S | 127.0.0.13 dc=c | coordinator; client talks only to S | owns no replica |

Client: Python driver bundled with cqlsh, async prepared inserts, 256 in flight, to S only.
- **map (tiny cells):** `t_map(pk int PRIMARY KEY, m map<int,int>)`, 1000 entries per insert →
  **10.80 KiB on-wire** per mutation (`pending_bytes / pending_count`).
- **blob (control):** `t_blob(pk int PRIMARY KEY, b blob)`, 11000-byte blob → **10.80 KiB on-wire**
  (matched to 0.1%).

Harness: `harness/` (`ctl.sh`, `ring-up.sh`, `load.py`, `sample.sh`, `snap.sh`, `arm.sh`, `armx.sh`,
`analyze.sh`, `mutation-delay.btm`, `batch1.sh`, `batch2.sh`). Raw data `/mydata/b6/runs/<arm>/`.

**Configuration audit**

| Change | Class | Value |
|---|---|---|
| internode send/receive queue capacities | tested capacity (default) | 4 / 128 / 512 MiB (intervention arm: endpoint reserves 8 MiB) |
| measured instance `-Xmx` | budget (tightened diagnostic) | 2 GiB; 8 GiB in calibration |
| `write_request_timeout` | supporting deviation | 60 s (default 2 s); default in D arms |
| `native_transport_timeout` | supporting deviation | 60 s (default 12 s); default in D arms |
| V Byteman delay, `concurrent_writes: 2` | supporting deviation (intervention) | 100 ms |
| `hinted_handoff_enabled` | supporting deviation | false |
| addresses, snitch, dc, tokens, caches 0 | environment | — |

**Amendments.**
- *A0 (dropped):* with only `write_request_timeout` raised, V expired 77% of messages at a mean
  12.5 s cross-node latency. In 5.0 the message deadline is also capped by `native_transport_timeout`
  (12 s) from client admission; raised to 60 s on all instances.
- *A1:* the slow replica V (then 2 GiB heap) **died of heap OOM** while its receive queue held
  ≤ 129 MB from S (`throttled_count` 0) and `MutationStage` pending was 11 746. This receive-side
  instance of the same mismatch was not in the design; it is added as domain (2) with its own arms.
- `jstat` cannot attach (Cassandra sets `-XX:+PerfDisableSharedMem`); heap is sampled with
  `jcmd GC.heap_info` (no forced GC) and measured with `GC.class_histogram` (forced full GC).

---

## 3. Results

Excerpts: [`logs/calibration-histograms.txt`](logs/calibration-histograms.txt),
[`logs/arm-outcomes.txt`](logs/arm-outcomes.txt), [`logs/oom-evidence.txt`](logs/oom-evidence.txt).
Heap dumps (2.9 GB each, A1 replica and `B_S2g_map_r1` coordinator) stay on node0 under
`/mydata/b6/runs/`.

### 3.1 Calibration — R at full queues (A2 map, A3 blob; S and V at 8 GiB)

Snapshot 55 s into a 75 s load; histograms force a full GC (live objects only).

| Payload | On-wire / mutation | S live `Mutation`s | S Δheap | S heap / mutation | **R (S)** | V live `Mutation`s | V Δheap | **R (V)** |
|---|---|---|---|---|---|---|---|---|
| map, 1000 entries | 10.80 KiB | 27 720 | 5 763 MiB | 212.9 KiB | **19.7** | 12 513 | 2 211 MiB | **16.7** |
| blob, 11 000 B | 10.80 KiB | 28 165 | 648 MiB | 23.6 KiB | **2.2** | 12 519 | 289 MiB | **2.2** |

Counters at the map snapshot: S→V `pending_bytes` 138 407 744 B = **132.0 MiB = C**, 12 512 messages,
`overload_count` 11 278 (dropping); V←S `using_bytes` 138 406 293 B = **C**, `throttled_count` 553;
V `MutationStage` pending 12 511. So **K = C on both sides while U = 5.6 GiB (S) and 2.2 GiB (V)**.

Where the coordinator's 27 720 mutations are: 12 502 are in queued `Message`s; the other ≈ 15 200 were
already flushed (sitting in TCP buffers and V's receive queue) and are reachable only from the write
handler's `hintOnFailure`. Heap per tiny cell on S ≈ 212 B (two `HeapByteBuffer`s 48 B each, two
`byte[]` ≈ 30 B each, `BufferCell` 40 B, `CellPath` 16 B) against ≈ 11 B on the wire. On V the cells are
`ArrayCell`s (deserialized form), ≈ 181 B each.

### 3.2 Boundary — one instance at a 2 GiB heap, the other at 8 GiB (`arm.sh`, clean starts)

| Arm | Payload | Budgeted | Outcome | Queue counters near failure / at peak |
|---|---|---|---|---|
| `B_S2g_map_r1–r3` | map | S 2 GiB | **3/3 S heap OOM** (`ReportJavaOutOfMemory`, `OnOutOfMemoryError` kill; dump 2.85 GB in r1) | **S→V pending 0**, sent 7.7–9.4k; V←S using 95–97 MiB, throttled 0 |
| `B_S2g_blob_r1–r3` | blob | S 2 GiB | 0/3 (≈ 490k inserts each, 0 errors) | S→V pending **132.0 MiB**, overload 431–441k; V←S **132.0 MiB**, throttled ≈ 1.2k |
| `B_V2g_map_r1–r3` (+ A1) | map | V 2 GiB | **3/3 V heap OOM** (+ A1: dump 2.86 GB) | V←S using ≤ 122 MiB, throttled 0 at last sample |
| `B_V2g_blob_r1–r3` | blob | V 2 GiB | 0/3 | V←S **132.0 MiB**, throttled ≈ 1.2k |

The blob controls fill both queues to the contract and keep dropping for the whole run, yet stay
alive: measured live ≈ 715 MiB (S, 35% of 2 GiB) and ≈ 366 MiB (V, 18%). The map arms die **before**
any counter reaches C. Client throughput is not matched (map ≈ 700 inserts/s, blob ≈ 5.4k/s, both
Python-bound): the control offers ~7× **more** on-wire bytes and still survives.

### 3.3 Intervention — endpoint reserves 8 MiB on send and receive (`armx.sh`, 60 s timeouts)

| Arm | Outcome | Counters |
|---|---|---|
| `C_S2g_map_rsv8m` | S alive (66k inserts, 0 errors) | S→V pending **12.0 MiB** (= 4 + 8), overload 55k; V←S 12.0 MiB, throttled 1118 |
| `C_V2g_map_rsv8m` | V alive (70k inserts, 0 errors) | same caps reached, throttled 1243 |

Bounding the on-wire charge to 24 MiB per pair (≈ 0.5 GiB of heap at R ≈ 20) removes both OOMs under
the same map load. n = 1 per arm.

### 3.4 Default timeouts (2 s write, 12 s native transport) — realism check

| Arm | Clients | Inserts/s | Outcome | Peak counters |
|---|---|---|---|---|
| `D_S2g_map_deftimeout_c4` | 4 | ≈ 1.7k | alive | S→V pending 0.3 MiB; V←S 45 MiB; no throttle/overload |
| `D_V2g_map_deftimeout_c4` | 4 | ≈ 2.0k | alive | V←S 56 MiB |
| `D_S2g_map_deftimeout_c16` | 16 | ≈ 1.8k | alive | V←S 43 MiB |
| `D_V2g_map_deftimeout_c16` | 16 | ≈ 2.3k | alive | V←S 55 MiB |

At default deadlines the queues hold ≈ 2–3 s of arrivals and expire before reaching C. Filling 132 MiB
in 2 s needs ≥ 66 MiB/s of these mutations to one slow replica (≈ 6k inserts/s); the Python client on
this host saturated at ≈ 2.3k/s with 4–16 processes. Default-timeout reproduction is **not
established** (blocked by load-generator rate), not shown safe.

---

## 4. Conclusion and limits of attribution

**Classification (protocol, *Classification by measurement*): bypass · accounting mismatch, on two
allocation domains.** For both the coordinator and the slow replica, U > C while K ≤ C:
- **Replica (receive queue):** charged on-wire bytes ≤ 132 MiB; live deserialized mutations waiting on
  `MutationStage` ≈ 16.7× that. Same objects, measured directly (12 513 `Mutation`s = stage pending).
- **Coordinator (send side):** the send queue charges on-wire bytes ≤ 132 MiB, but (a) queued messages
  are ≈ 19.7× larger on heap, and (b) after flush the `Mutation` stays on the coordinator heap via the
  write handler until the replica answers or the deadline passes, charged to no sender counter. In the
  2 GiB arms (b) alone was enough: the coordinator died with an empty send queue.

**Causal evidence:** matched on-wire size, the blob payload (R ≈ 2.2) survives 6/6 with queues full and
dropping, while the tiny-cell payload (R ≈ 17–20) OOMs 6/6 (+1) with counters below C; capping the
endpoint reserves at 8 MiB removes the OOM at the same load (n = 1 each).

**Interpretation:** the contract states the limits are applied to the on-wire size, so this is a
**documented accounting unit that does not bound heap** — a sizing/validation gap — rather than an
implementation defect of the counters. The after-flush coordinator retention is a separate uncovered
path. A heap budget sized from the documented limits (`N*3*(send+receive capacity)` plus reserves) can
be wrong by ≈ 20× for collection-heavy writes.

**Limits / dependence on supporting deviations:**
- Slow replica injected with Byteman (100 ms per mutation, `concurrent_writes: 2`).
- Deadlines raised to 60 s (`write_request_timeout` *and* `native_transport_timeout`); at defaults, no
  OOM within the reachable client rate (§3.4).
- Hints off; single host, all instances on loopback; tightened 2 GiB heap on the measured instance.
  At 8 GiB the coordinator survived one slow replica (live ≈ 5.7 GiB). Each further slow destination can
  add another ≈ 264 MiB on-wire (≈ 5 GiB of heap at R ≈ 20) until the 512 MiB global reserves fill —
  predicted, not tested.
- Intervention n = 1 per side; client rates not matched between payloads (the control is heavier).

**Next steps:** a faster load generator (Java driver or several hosts) for the default-timeout arm;
coordinator with ≥ 2 slow replicas at a deployment-sized heap (8 GiB); repeat the intervention ×3;
compare against the JIRA history for this accounting choice before any upstream report.

All instances stopped after each batch; no Java process left on node0 (checked with `pgrep java`).
