# U1 — in-flight `DataOutputBuffer` fill of large mutations in `CommitLog.add` (standalone, JVM direct)

> **Verdict (2026-11-17 mapping):** retry. **Phase-1 case file:** [`DOB_MAX_RECYCLE_BYTES-close-MAX_RECYCLE_BUFFER_SIZE--guided`](../../../../../capacity-enforcement-exp/cassandra/stage3-ai-deep-read/cases/DOB_MAX_RECYCLE_BYTES-close-MAX_RECYCLE_BUFFER_SIZE--guided.md), [`max_mutation_size-validateSize-MAX_MUTATION_SIZE--guided`](../../../../../capacity-enforcement-exp/cassandra/stage3-ai-deep-read/cases/max_mutation_size-validateSize-MAX_MUTATION_SIZE--guided.md).

**Campaign row:** U1 (U = unprotected-accumulation lead: memory with no applicable control). **Lead source:** side
finding of R6-V (R = recheck of a pre-protocol convergence OOM; -V = re-test at defaults and an acceptable budget),
corroborated by C3 run 1 (C = convergence investigation) and stage 3 of S1 (S = stacked combo case), where U1 was the
layer that made the stack fail. **Direction:** **unprotected accumulation** (no control applies to the buffer while it
is filled; implicit bound `concurrent_writes` × ≈ 2–3 × mutation size, not enforced as a memory limit). Not a bypass,
not convergence. **Domain:** JVM direct, JDK `Bits` counter (`-XX:MaxDirectMemorySize`). **Regime:** default capacities
(shipped yaml, environment keys only). **Budget:** heap 2048 MiB every arm; direct auto (resolves to 15,872 MiB on
pc96), 1024, 768, 640, 608, 576, 544, 512 MiB. **Source/build:** cassandra-5.0.9, unpatched, read-only reuse of
`/mydata/b6/cassandra` (`f2de6956`, same build as S1 and C1 run 4; `src/` identical to the pinned
`systems/cassandra/source/src/` apart from generated files). JDK 11.0.33, G1. **Node:** `pc96` only (single
instance on 127.0.0.71, client and sampler colocated on separate cores; data and commit log on local HDD RAID).
**Date:** 2026-11-16 21:23 – 2026-11-17 00:33 EST. **Design:** [`design/U1-design.md`](design/U1-design.md)
(written 21:25 before any reading; amendments 1–6 dated before the readings they govern).

**Status (proposed, researcher decides):** **`candidate`** — the U1 endpoint (JDK `OutOfMemoryError: Direct buffer
memory` thrown in `CommitLog.add` → `DataOutputBuffer.expandToFit`) is real and reproduced twice at 576 MiB, but in
only 2 of 14 arms at that budget (E 1/3, E3 1/9 in 90 s; 0/2 in 240 s), so V1 (≥ 3 at one fixed condition) is not
met. V2–V5 and V6 hold; V7 holds (576 ≥ 512 MiB, standing rule). **Conditions label if promoted: `deployment`**
(all constraints default, budget ≥ 512 MiB, environment-only yaml, no instrumentation; the 576 MiB direct limit is
below the 1,024 MiB that `cassandra-env.sh` resolves for a 4 GiB node and needs `MAX_DIRECT_MEMORY_SIZE` set).
At the deployment-resolved budgets (auto 15,872 MiB; 1,024 MiB) U1 alone does **not** fail: U_peak 632–752 MiB.

## Summary

- **Conclusion.** With default constraints, a 2 GiB heap and 15 MiB mutations (inside the default 16 MiB
  `max_mutation_size`), up to 32 `MutationStage` threads fill their thread-local direct scratch buffers at once;
  the JDK direct counter peaks at **632–752 MiB** (incl. a 43 MiB baseline) — no failure at the auto value
  (15,872 MiB) or at 1,024 / 768 / 640 / 608 MiB. Between **512 and 640 MiB every 15 MiB arm with 16–32 outstanding requests drives
  the counter to the limit** (seconds at the cap, 80–600 forced `System.gc()` from `Bits.reserveMemory`), but the JDK's
  reservation retry usually waits long enough for another writer to free its buffer: a **U1 direct OOM occurred
  2 times, both at 576 MiB** (E 1/3, E3 1/9; 20–31 s into the load). Largest failing budget: **576 MiB**; 608 and
  640 survive (1/1, 2/2). The endpoint is stochastic and **not reproduced ≥ 3 times at one condition**.
- **Root cause.** `CommitLog.add` serializes every mutation > 1 MB into `DataOutputBuffer.scratchBuffer`, direct
  since CASSANDRA-16471, which grows to S then 2S (transiently S + 2S) and is held through segment allocation and the
  copy into the mmap'd segment. `DOB_MAX_RECYCLE_BYTES` (1 MiB) trims it only after use; `max_mutation_size` bounds
  one mutation; the only bound on the sum is `concurrent_writes` (32). Writers stall together in memtable
  allocation, then serialize in bursts of 20–32: U jumps from 45 to 450–570 MiB within a second.
- **Competing endpoint (side result).** At ≤ 576 MiB the same `MaxDirectMemorySize` also limits **Netty's own
  counter**, where the native-protocol v4 frames of the clients' outstanding 15 MiB requests sit (416–564 MiB at
  failure): 4 arms died of `io.netty.util.internal.OutOfDirectMemoryError` in the frame decoder before U1 could
  (512 MiB 2/2 with E/E3, 576 MiB 2/14). This is not U1; it is a lead for its own case (§3.5).
- **Attribution.** `concurrent_writes: 8` with the same workload never touches the cap (U 379–439 MiB, 0 forced
  GCs, 7/7 survive at 240–321 MiB/s, ≥ the endpoint arms' throughput); 512 KiB mutations at the same offered bytes/s
  stay at 127 MiB (5/5); 4 MiB mutations peak at 266 MiB.
- **CASSANDRA-21656** (In Progress) describes the same buffer as per-write native churn; its WIP branch, as pushed
  (`21656-commitlog-write-path`, 2026-10-12), serializes straight into the segment only mutations **< 1,000,000 B**
  (those with a cached serialization). Larger mutations — every U1 mutation — still go through the direct scratch
  buffer, so the branch would not remove this case (§4).

---

## 1. Constraints, protection map, configuration

### 1.1 Source check (pinned 5.0.9)

| Step | Source | Finding |
|---|---|---|
| Size check | `CommitLog.java:304` → `Mutation.validateSize` (`Mutation.java:169–172`) | per mutation ≤ `max_mutation_size`; default `commitlog_segment_size`/2 = **16 MiB** (`DatabaseDescriptor.java:898–899`). Bounds S, not the sum. |
| Holder | `CommitLog.java:306` `DataOutputBuffer.scratchBuffer.get()` | thread-local; `allocate()` = `ByteBuffer.allocateDirect` (`DataOutputBuffer.java:55,84–88`; `cassandra.dob.allocate_type` default `DIRECT`, CASSANDRA-16471). JDK `Bits`-counted. |
| Growth | `CommitLog.java:308` `Mutation.serializer.serialize` → `expandToFit` (`DataOutputBuffer.java:158–182`) | first to `capacity + count` (one 15 MiB value write), then ×2 on the next small write (`DOB_DOUBLING_THRESHOLD_MB` 64): buffers of 15,728,683 B and 31,457,366 B in every dump. Old buffer freed immediately (`setBuffer` → `FileUtils.clean`), so the transient peak per thread is S + 2S. Mutations ≥ 1,000,000 B have no cached serialization (`Mutation.java:451`), so each is serialized in full here. |
| Hold | `CommitLog.java:309–337` | across `segmentManager.allocate` (blocks in `awaitAvailableSegment` while a new 32 MiB segment is prepared — a 15 MiB mutation fills half a segment), the copy into the mmap'd segment (`:323`, page faults on the HDD-backed mapping), `finishWriteFor`. Thread dumps: holders were in `expandToFit`, in the copy at `:323`, or waiting for a segment (`WaitingOnSegmentAllocation` +45–660 per arm). |
| Release | `DataOutputBuffer.java:71–81` | `close()`: a buffer > `DOB_MAX_RECYCLE_BYTES` (1 MiB) is replaced by 128 B and freed. **Only after use.** |
| Concurrency | `MutationStage`, `concurrent_writes` = 32 | the only bound on simultaneous holders. `native_transport_max_request_data_in_flight` (heap/10 = 204.8 MiB) and `_per_ip` (heap/40 = 51.2 MiB) count request bytes until the response; a write that times out (2 s) releases them while its `MutationStage` task continues, and an expired local mutation is resubmitted as a hint runnable on the same stage (`StorageProxy.java:2634–2660`, the S2 finding). Observed: `MutationStage` active up to 32 with 24 outstanding requests. |

Arithmetic ceiling: 32 × 2S = 960 MiB standing, up to 32 × 3S = 1,440 MiB transient at S = 15 MiB, plus a 43 MiB
idle baseline (32 MiB hints buffer, 8 MiB `BufferPool` chunk, NIO). No Cassandra counter covers it (no K).

### 1.2 Protection map (design §2, fixed before readings)

| Domain | Allocation / release | Contract C | Multiplicity | Aggregate coverage | Lifetime |
|---|---|---|---|---|---|
| **U1 in-flight DOB** | `DataOutputBuffer$1$1.buffer` grown under `CommitLog.add`, freed at `close()` | **none in flight** (`max_mutation_size` 16 MiB per mutation) | ≤ `concurrent_writes` 32 | none; not reconciled with `MaxDirectMemorySize` | serialize → segment → copy |
| D kept DOB | same buffer after `close()` | ≤ 1 MiB per thread | threads that serialized | none | standing |
| Baseline direct | hints buffer, `BufferPool` chunk, NIO | per-pool caps | — | — | standing (43 MiB) |
| Netty counter (separate limit = same value) | native v4 request frames (16 MiB pooled chunks per 15 MiB frame) | native in-flight bytes 204.8 MiB / 51.2 MiB per IP (checked after a frame is decoded) | outstanding requests | its own `MaxDirectMemorySize`-sized counter | until the response |
| Heap (reported) | decoded mutations, `MutationStage` queue, memtable (heap/4 = 512 MiB) | memtable 512 MiB | — | flush | — |

### 1.3 Configuration and budget audit

| Setting | Class | Value |
|---|---|---|
| `concurrent_writes`, `max_mutation_size`, `commitlog_segment_size`, `DOB_MAX_RECYCLE_BYTES`, `cassandra.dob.allocate_type`, memtable, native in-flight limits, timeouts, commit-log sync | **default** (absent from yaml / no `-D`) | 32; 16 MiB; 32 MiB; 1 MiB; DIRECT; heap_buffers 512 MiB; 204.8 / 51.2 MiB; write 2 s; periodic 10 s |
| yaml diff | environment | cluster name, 127.0.0.71, seeds, data/commitlog/hints/saved_caches/cdc directories ([`logs/V-yaml.diff`](logs/V-yaml.diff)); JMX port 7271 |
| heap | budget | 2048 MiB (ideal) |
| `MaxDirectMemorySize` | budget (dial) | **auto** first: not passed; `cassandra-env.sh` resolved **15,872 MiB** on pc96 (`heap_limit` is 31,744 with G1 because the CMS test fails, /2; amendment 1; [`logs/A_auto_r1-V-flags.txt`](logs/A_auto_r1-V-flags.txt)). Then 1,024 (= ¼ RAM of the 4 GiB node whose automatic heap is 2 GiB), 768, 640, 608, 576, 544, 512 |
| storage | environment | local HDD RAID (`/mydata`, 200 MB/s `dd oflag=direct`), not tmpfs |
| safety scope | environment (non-binding) | `systemd-run --user --scope -p MemoryMax=44G -p MemorySwapMax=0`; `oom_kill` 0 in every arm |
| CPU | environment | V cores 0–15; client + sampler 24–31; dump analysis 16–23 |
| workload | experimental variable | `U1Load`: driver 3.12.1, protocol v4, prepared `INSERT INTO u1.t (pk int, b blob)`, CL ONE, RF 1, zero-filled blobs, keys mod 200; writers = connections from separate loopback source IPs (127.0.0.101…); **E** = 15 MiB, 8 writers × 4 in flight, 40/s offered (600 MiB/s); **E3** = E with 3 in flight; **E2** = 2 in flight; **G** (control) = 512 KiB, 8 × 16 in flight, 1,200/s (600 MiB/s offered) |
| Byteman, patches | not used | — |

### 1.4 V7 argument (design §3, written before readings)

The result claims a node sized as `cassandra-env.sh` sizes a **4 GiB-RAM node** (heap 2,048 MiB, direct 1,024 MiB),
or a larger node where the operator sets a 2 GiB heap (direct then ¼ RAM, ≤ 15,872 MiB here). Heap 2 GiB is the
standing rule's ideal. The direct limit is searched down from the resolved values to the 512 MiB floor; values
≥ 512 MiB meet V7 by the standing rule. The failing 576 MiB is below both resolved values: it needs
`MAX_DIRECT_MEMORY_SIZE` (a documented override in `cassandra-env.sh`) or a 2.25 GiB node. *Researcher's review: pending.*

---

## 2. Verification solution (as executed)

Harness [`harness/`](harness/) (derived from S1 / C1 run 4): `ctl.sh` (single node, scope, JVM flags), `arm.sh` (one
arm from a clean node: gen conf, start, schema, samplers, load, 20 s observation, stop, wipe data), `U1Load.java`
(S1Load with per-writer source IP), `U1Sample.java` (1 s JMX: `java.nio` direct = U, heap, `MutationStage`
active/pending/completed, commit-log waits, write timeouts, memtable), `jstk.py` (classifies `MutationStage` threads in
`jcmd Thread.print`, diagnostic arm only), `peaks.py`, `table.py`, `gcwin.py` (STW share), `hprof_direct.py` (dump
attribution, from C1/S1), `queue.sh` + `q1–q4.txt` (queues as run). Endpoint: `OutOfMemoryError: Direct buffer memory`
in V's `system.log`; Cassandra then forces a heap OOM, writes the dump and `kill -9`s itself. Forced GCs = lines with
`System.gc()` in the GC log (`Bits.reserveMemory` reclamation).

---

## 3. Runtime results

Raw data: `pc96:/mydata/u1/runs/<arm>/` (`samples.csv`, `cg.csv`, `load.log`, `V-logs/{system.log,gc.log*}`,
`first-oom.txt`, `outcome.txt`, `V-cmdline.txt`, `V-flags.txt`, dumps `*.hprof` of the dead arms,
`direct-holders.txt`); one line per arm in `/mydata/u1/runs/summary.txt` (copy: [`logs/summary.txt`](logs/summary.txt)).
"Delivered MiB/s" is averaged over the 90 s client window, so it is low for arms that died.

### 3.1 Budget search (15 MiB, heap 2 GiB)

| Arm | X (MiB) | mutation | writers×in-flight @offered | change | outcome | death after load start | U_peak (MiB) | heap peak | MutationStage active peak | delivered MiB/s | write timeouts | forced GCs (`System.gc()` lines) | dump: DOB (MiB) | dump: Netty counter (MiB) |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `A_auto_r1` | auto | 15.00 MiB | 8×4 @40/s | — | survive | — | 752 | 1955 | 21 | 314.2 | 0 | 0 |  |  |
| `B_d1024_r1` | 1024 | 15.00 MiB | 8×4 @40/s | — | survive | — | 632 | 1937 | 32 | 202.7 | 200 | 0 |  |  |
| `B_d768_r1` | 768 | 15.00 MiB | 8×4 @40/s | — | survive | — | 695 | 1919 | 21 | 304.4 | 0 | 7 |  |  |
| `B_d640_r1` | 640 | 15.00 MiB | 8×4 @40/s | — | survive | — | 633 | 1888 | 32 | 220.1 | 165 | 79 |  |  |
| `B_d640_r2` | 640 | 15.00 MiB | 8×4 @40/s | — | survive | — | 632 | 1871 | 21 | 259.6 | 18 | 100 |  |  |
| `B_d608_r1` | 608 | 15.00 MiB | 8×4 @40/s | — | survive | — | 603 | 1903 | 32 | 208.0 | 179 | 130 |  |  |
| `B_d576_r1` | 576 | 15.00 MiB | 8×4 @40/s | — | **U1 direct OOM** | 31 s | 570 | 1681 | 32 | 50.1 | 66 | 60 | 180.0 | 520.0 |
| `B_d576_r2` | 576 | 15.00 MiB | 8×4 @40/s | — | survive | — | 575 | 1873 | 21 | 257.0 | 28 | 170 |  |  |
| `B_d576_r3` | 576 | 15.00 MiB | 8×4 @40/s | — | Netty-counter OOM | 17 s | 555 | 1498 | 21 | 43.8 | 0 | 30 | 330.0 | 516.0 |
| `E3_d544_r1` | 544 | 15.00 MiB | 8×3 @40/s | — | survive | — | 544 | 1788 | 32 | 214.7 | 117 | 219 |  |  |
| `E2_d544_r1` | 544 | 15.00 MiB | 8×2 @40/s | — | survive | — | 543 | 1859 | 22 | 254.9 | 15 | 211 |  |  |
| `E2_d512_r1` | 512 | 15.00 MiB | 8×2 @40/s | — | survive | — | 500 | 1891 | 16 | 239.8 | 17 | 261 |  |  |
| `E3_d512_r1` | 512 | 15.00 MiB | 8×3 @40/s | — | Netty-counter OOM | 23 s | 510 | 1675 | 21 | 50.7 | 0 | 67 |  |  |
| `B_d512_r1` | 512 | 15.00 MiB | 8×4 @40/s | — | Netty-counter OOM | 6 s | 269 | 1367 | 19 | 10.5 | 0 | 10 | 315.0 | 488.0 |

**Largest failing budget: 576 MiB** (U1 1/3 with E, 1/9 with E3); 608 (0/1) and 640 (0/2) survive touching the
cap; 768 and above never reach it. Below 576, E and E3 at 512 die on Netty's counter (§3.5), E2 / E3 at 512–544
survive touching the cap.

### 3.2 Endpoint, control and intervention at 576 MiB

Arms `L_*` ran a 240 s load (amendment 5); all others 90 s. `I_cw8_*` used E (8 × 4 in flight), `I_cw8E3_*` and `L_cw8` E3.

| Arm | X (MiB) | mutation | writers×in-flight @offered | change | outcome | death after load start | U_peak (MiB) | heap peak | MutationStage active peak | delivered MiB/s | write timeouts | forced GCs (`System.gc()` lines) | dump: DOB (MiB) | dump: Netty counter (MiB) |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `E3_d576_r1` | 576 | 15.00 MiB | 8×3 @40/s | — | **U1 direct OOM** | 20 s | 570 | 1900 | 32 | 21.1 | 58 | 41 | 330.0 | 416.0 |
| `E3_d576_r2` | 576 | 15.00 MiB | 8×3 @40/s | — | survive | — | 575 | 1863 | 25 | 231.7 | 74 | 250 |  |  |
| `E3_d576_r3` | 576 | 15.00 MiB | 8×3 @40/s | — | survive | — | 574 | 1886 | 21 | 249.4 | 30 | 153 |  |  |
| `E3_d576_r4` | 576 | 15.00 MiB | 8×3 @40/s | — | Netty-counter OOM | 16 s | 525 | 1852 | 21 | 42.4 | 0 | 36 |  |  |
| `E3_d576_r5` | 576 | 15.00 MiB | 8×3 @40/s | — | survive | — | 574 | 1888 | 23 | 278.8 | 11 | 122 |  |  |
| `E3_d576_r6` | 576 | 15.00 MiB | 8×3 @40/s | — | survive | — | 576 | 1848 | 32 | 206.0 | 132 | 194 |  |  |
| `E3_d576_r7` | 576 | 15.00 MiB | 8×3 @40/s | — | survive | — | 574 | 1837 | 21 | 248.1 | 18 | 278 |  |  |
| `E3_d576_r8` | 576 | 15.00 MiB | 8×3 @40/s | — | survive | — | 572 | 1789 | 32 | 175.0 | 298 | 80 |  |  |
| `E3_d576_r9` | 576 | 15.00 MiB | 8×3 @40/s | — | survive | — | 573 | 1866 | 30 | 213.2 | 141 | 233 |  |  |
| `L_E3_d576_r1` | 576 | 15.00 MiB | 8×3 @40/s | — | survive | — | 574 | 1895 | 25 | 219.8 | 210 | 616 |  |  |
| `L_E3_d576_r2` | 576 | 15.00 MiB | 8×3 @40/s | — | survive | — | 575 | 1939 | 32 | 176.4 | 564 | 554 |  |  |
| `G_ctl512k_d576_r1` | 576 | 0.50 MiB | 8×16 @1200/s | — | survive | — | 127 | 1964 | 32 | 388.6 | 0 | 0 |  |  |
| `G_ctl512k_d576_r2` | 576 | 0.50 MiB | 8×16 @1200/s | — | survive | — | 127 | 1943 | 32 | 366.7 | 0 | 0 |  |  |
| `G_ctl512k_d576_r3` | 576 | 0.50 MiB | 8×16 @1200/s | — | survive | — | 127 | 1882 | 32 | 365.7 | 0 | 0 |  |  |
| `L_G_d576_r1` | 576 | 0.50 MiB | 8×16 @1200/s | — | survive | — | 127 | 1965 | 32 | 365.8 | 0 | 0 |  |  |
| `L_G_d576_r2` | 576 | 0.50 MiB | 8×16 @1200/s | — | survive | — | 127 | 1937 | 32 | 345.7 | 0 | 0 |  |  |
| `I_cw8E3_d576_r1` | 576 | 15.00 MiB | 8×3 @40/s | concurrent_writes=8 | survive | — | 381 | 1948 | 8 | 300.5 | 9 | 0 |  |  |
| `I_cw8E3_d576_r2` | 576 | 15.00 MiB | 8×3 @40/s | concurrent_writes=8 | survive | — | 379 | 1853 | 8 | 293.8 | 4 | 0 |  |  |
| `I_cw8E3_d576_r3` | 576 | 15.00 MiB | 8×3 @40/s | concurrent_writes=8 | survive | — | 379 | 1939 | 8 | 239.5 | 81 | 0 |  |  |
| `L_cw8_d576_r1` | 576 | 15.00 MiB | 8×3 @40/s | concurrent_writes=8 | survive | — | 439 | 1938 | 8 | 300.5 | 15 | 0 |  |  |
| `I_cw8_d576_r1` | 576 | 15.00 MiB | 8×4 @40/s | concurrent_writes=8 | survive | — | 393 | 1930 | 8 | 273.9 | 39 | 0 |  |  |
| `I_cw8_d576_r2` | 576 | 15.00 MiB | 8×4 @40/s | concurrent_writes=8 | survive | — | 408 | 1994 | 8 | 321.3 | 4 | 0 |  |  |
| `I_cw8_d576_r3` | 576 | 15.00 MiB | 8×4 @40/s | concurrent_writes=8 | survive | — | 380 | 1909 | 8 | 296.8 | 6 | 0 |  |  |
| `I_onheap_d576_r1` | 576 | 15.00 MiB | 8×3 @40/s | -Dcassandra.dob.allocate_type=ONHEAP | survive | — | 51 | 1903 | 21 | 239.5 | 14 | 0 |  |  |
| `I_mms4_d576_r1` | 576 | 15.00 MiB | 8×3 @40/s | max_mutation_size=4MiB | survive | — | 44 | 1969 | 0 | 0.0 | 0 | 0 |  |  |

### 3.3 Sweeps at 576 MiB (n = 1)

| Arm | X (MiB) | mutation | writers×in-flight @offered | change | outcome | death after load start | U_peak (MiB) | heap peak | MutationStage active peak | delivered MiB/s | write timeouts | forced GCs (`System.gc()` lines) | dump: DOB (MiB) | dump: Netty counter (MiB) |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `S_4m_d576_r1` | 576 | 4.00 MiB | 8×3 @150/s | — | survive | — | 266 | 1949 | 24 | 284.8 | 0 | 0 |  |  |
| `S_8m_d576_r1` | 576 | 8.00 MiB | 8×3 @75/s | — | survive | — | 374 | 1918 | 32 | 224.6 | 54 | 0 |  |  |
| `W_1x3_d576_r1` | 576 | 15.00 MiB | 1×3 @40/s | — | survive | — | 200 | 1955 | 3 | 263.7 | 0 | 0 |  |  |
| `W_4x3_d576_r1` | 576 | 15.00 MiB | 4×3 @40/s | — | survive | — | 379 | 1859 | 12 | 297.2 | 0 | 0 |  |  |

Reference at the same budget: E3 (8 writers × 3, 15 MiB) U_peak 572–576 (at the cap) in all 9 arms, `MutationStage` active 21–32.
Fewer writers or smaller mutations keep U well below the cap: 1 writer → 3 active, 200 MiB; 4 writers → 12 active, 379 MiB; 4 MiB → 266 MiB; 8 MiB → 374 MiB. Throughput stays 225–297 MiB/s (HDD-bound), so the extra writers of E3 add holders, not throughput.

### 3.4 Initiating failure and holders (U1 arms)

First error, both U1 arms ([`logs/B_d576_r1-first-oom.txt`](logs/B_d576_r1-first-oom.txt),
[`logs/E3_d576_r1-first-oom.txt`](logs/E3_d576_r1-first-oom.txt)): `MutationStage` thread,
`java.lang.OutOfMemoryError: Direct buffer memory` at `Bits.reserveMemory` ← `ByteBuffer.allocateDirect` ←
`DataOutputBuffer$1$1.allocate(DataOutputBuffer.java:87)` ← `expandToFit(:178)` ← … ←
`Mutation$MutationSerializer.serialize(Mutation.java:414)` ← **`CommitLog.add(CommitLog.java:308)`** ←
`CassandraKeyspaceWriteHandler.beginWrite` ← `Keyspace.applyInternal`. Time series before death (s after load start:
U MiB / `MutationStage` active): `B_d576_r1` … 21: 75/32, 22: 45/32, 25: 554/24, 26: 554/29, 27: **569/32**, dead;
`E3_d576_r1` … 12: 44/32, 13: 449/25, 14: **569/25**, dead — all writers stalled (U low), then released together and
held at the cap for 2–3 s.

Dumps (Cassandra's forced heap OOM, 0.3–1 s after the first error; `hprof_direct.py`, 6 hops;
[`logs/*-direct-holders.txt`](logs/)):

| Holder (MiB) | `B_d576_r1` (U1) | `E3_d576_r1` (U1) | `B_d576_r3` (Netty) | `B_d512_r1` (Netty) |
|---|---|---|---|---|
| **U1 `DataOutputBuffer` scratch** (`DataOutputBuffer$1$1.buffer`; 31,457,366 B and 15,728,683 B buffers) | **180** (4 × 30 + 4 × 15) | **330** (11 × 30) | 330 | 315 |
| hints buffer (idle baseline) | 32 | 32 | 32 | 32 |
| `BufferPool` chunk, NIO | 11 | 11 | 11 | 11 |
| "no strong referrer" (S-sized buffers already released by `FileUtils.clean` before the dump; tool counts their objects) | 60 | 120 | 0 | 120 |
| JDK owners total at dump | 285 | 494 | 375 | 479 |
| JMX U at the last sample before death | 570 | 570 | 555 | 269 |
| **Netty counter** (separate limit) | 520 | 416 | 516 | 488 |

The live DOB scratch is the largest JDK holder in every dump (63–88 % of owners). Owners at dump time are below the
limit because the failing and the finishing writers release their buffers in the 0.3–1 s before the dump; the JMX
sample 1 s before death shows 570 of 576 MiB. Physically the process held ≈ 900–1,000 MiB of direct memory at
failure (JDK ≈ 570 + Netty 416–520).

### 3.5 Side result: Netty's counter (native v4 request frames)

Four arms died of `io.netty.util.internal.OutOfDirectMemoryError: failed to allocate 16777216 byte(s)` (used 504–564
of 512–576 MiB) in `ByteToMessageDecoder.cumulate` on an `epollEventLoopGroup` thread
([`logs/B_d512_r1-netty-first-oom.txt`](logs/B_d512_r1-netty-first-oom.txt)): `B_d512_r1` (E, 6 s), `E3_d512_r1`
(E3, 23 s), `B_d576_r3` (E, 17 s), `E3_d576_r4` (E3, 16 s). Each outstanding 15 MiB request occupies a 16 MiB
pooled chunk (`io.netty.allocator.maxOrder=11`) while being decoded and until its response; the native in-flight
limits (204.8 MiB global, 51.2 MiB per IP) are checked after a frame is decoded and only pause reading, and the
counter stood at 416–564 MiB with 24–32 outstanding requests — about 2–2.5× the global limit. U1 is not involved
(JDK U 269 MiB in `B_d512_r1`). Proposed as a **new lead** (native v4 large-request frames on Netty's counter beyond
`native_transport_max_request_data_in_flight`; possibly an accounting mismatch, U > C with K ≤ C), not part of this
case.

### 3.6 Host and side events

- pc96 was shared with another session's S2 controller (ssh to Utah nodes; no local JVM); `foreign.txt` per arm
  records load average and foreign Java processes (none besides the S2 controller's tools).
- No heap OOM in any arm (heap peak 1.79–1.99 GiB of 2 GiB; worst 60 s STW share ≤ 23 %).
- Two queue mishaps cost time, not data: a waiter that matched its own command line (q2 started 8 min late) and
  the cancelled L arms of amendment 6 (`STOP` file; listed in `runs/q3.log`).

---

## 4. Conclusion

**Mechanism confirmed, endpoint not reproducible enough.** At default constraints and a 2 GiB heap, the in-flight
DOB scratch of large mutations is the dominant JDK direct holder and is bounded only by `concurrent_writes` × 2–3 ×
mutation size. Measured U_peak 632–752 MiB with 15 MiB mutations: below the 1,024 MiB a 4 GiB node resolves and far
below the 15,872 MiB resolved on pc96 — **no failure at any deployment-resolved budget**. From 640 MiB down to 512 MiB
every 15 MiB arm with 8 writers reaches the limit and survives on `Bits.reserveMemory`'s forced-GC-and-wait loop, which acts as an
accidental throttle (writers wait for each other's buffers); a U1 direct OOM occurred in 2 of 14 arms at 576 MiB
(E 1/3, E3 1/9 at 90 s, L 0/2 at 240 s), both 20–31 s after the load started, when a burst of 24–32 writers held
their buffers for 2–3 s. At ≤ 576 MiB the separate Netty counter (request frames) competes and killed 4 arms first.

**Classification (protocol table).** No control's contract covers the in-flight buffer → **unprotected
accumulation**. Within documented guardrails: mutations 15 MiB < `max_mutation_size` 16 MiB and < the 16 MiB native
frame limit; the excess is the system's own copy (serialized form, ×2 by doubling, ×3 transient). Not documented as
by design; CASSANDRA-16471 made the buffer direct with a CHANGES.txt line only.

**Attribution.** `concurrent_writes: 8` (the protocol's "bound multiplicity" intervention) removes the cap-touching
entirely — U 379–439 MiB (= 8 × 45 MiB transient + baseline), 0 forced GCs, 7/7 survive at 240–321 MiB/s, at
least the endpoint arms' throughput, because the HDD, not the writer count, sets the rate. 512 KiB mutations at the
same offered bytes/s: 127 MiB, 5/5. Size: 4 MiB → 266 MiB; 8 MiB → 374 MiB; 1 writer → 200 MiB, 4 writers → 379 MiB, at 225–297 MiB/s. `max_mutation_size: 4MiB` rejects every 15 MiB write
(`InvalidQueryException` 3,593/3,593, nothing delivered, U 44 MiB): it removes the endpoint only by removing the
work, so it is not counted as protection. `-Dcassandra.dob.allocate_type=ONHEAP` (the 4.x behaviour, a JVM property,
not a patch) moves the scratch to the heap: U 51 MiB, no heap OOM (heap peak 1.90 of 2 GiB), 240 MiB/s, 1/1 survive.

**Relation to CASSANDRA-21656** (In Progress, "large mutations over-allocate on the commit log path", reporter/assignee
Jon Haddad, created 2026-09-05). Same buffer, different consequence: the ticket measures per-write native churn on
one thread (10.42 MB native per 4 MiB mutation) and proposes serializing straight into the segment slot. This case
measures the **concurrent peak**: up to 32 writers × 30–45 MiB of direct scratch at once, reaching
`MaxDirectMemorySize` at 512–640 MiB and failing at 576 MiB. The WIP branch
(`github.com/rustyrazorblade/cassandra`, `21656-commitlog-write-path` @ `5a88d42`, 2026-10-12, on `cassandra-6.0`)
takes the direct path only when `Mutation.serializer.hasCachedSerialization` is true, i.e. for mutations below
`CACHEABLE_MUTATION_SIZE_LIMIT` = 1,000,000 B; its commit message says a mutation above that limit "is still serialized
first and its slot sized from the bytes written" — into the same direct `scratchBuffer`. So, as pushed, it **does not
cover U1** (all U1 mutations are 4–15 MiB), although the ticket's description reports its 4 MiB measurement as fixed.
Upstream contribution: a comment on 21656 that the large-mutation path keeps the direct scratch and that its
concurrent peak is ≈ `concurrent_writes` × 2–3 × mutation size (measured 632–752 MiB at defaults, a direct OOM at
576 MiB), with the `concurrent_writes: 8` and 512 KiB controls. Not a new ticket.

**Status by condition (proposed):**

| Condition (heap 2 GiB, defaults) | Endpoint (U1 direct OOM) | Other endpoint | Control | Intervention | Proposed status |
|---|---|---|---|---|---|
| E3 @ 576 MiB, 90 s | 1/9 | Netty 1/9 | G 512 KiB 0/3 (+ 0/2 at 240 s) | `concurrent_writes: 8` 0/3 (+ 0/1 at 240 s) | `candidate` (V1 unmet) |
| E @ 576 MiB, 90 s | 1/3 | Netty 1/3 | (G 0/3) | `concurrent_writes: 8` 0/3 | `candidate` (V1 unmet) |
| E/E2/E3 @ 512–544 | 0/4 | Netty 2/4 | — | — | boundary readings |
| E @ 608–1,024, auto 15,872 | 0/6 | — | — | — | survive (n ≤ 2 per budget; not a negative by V1) |

**V1–V7 (condition E3 @ 576 MiB):**

| | Evidence | Met |
|---|---|---|
| V1 repetition | U1 OOM in `E3_d576_r1` only (1/9); also `B_d576_r1` under E (1/3) | **no** |
| V2 matched control | `G_ctl512k_d576_r1..r3` + `L_G_d576_r1..r2`: 0/5, U 127 MiB | yes |
| V3 measurement | U = JMX direct (1 s) independent of any counter (no K exists); per-holder U from 4 dumps; Netty counter from dumps | yes |
| V4 intervention | `concurrent_writes: 8`: `I_cw8E3_d576_r1..r3` 0/3 (+ `L_cw8` 0/1, `I_cw8_d576_r1..r3` with E 0/3), U 379–439, throughput ≥ endpoint | yes |
| V5 initiating failure | first error + stack (`CommitLog.add:308` → `expandToFit`) and dumps with the DOB holder, in both U1 arms | yes (n = 2) |
| V6 default constraints | yaml diff environment-only; no `-D`; 15 MiB < 16 MiB `max_mutation_size` | yes |
| V7 acceptable budget | heap 2,048 (ideal); direct 576 ≥ 512 (standing rule); below the resolved 1,024 / 15,872 | yes (standing rule; review pending) |

**Limits.**
- The U1 endpoint is rare at every tested budget (2/14 at 576); a longer load did not help (hazard in the first
  ≈ 30 s). Reaching V1 would need ≈ 10–25 more clean-start arms at E3 @ 576, or a workload with more simultaneous
  writers that does not also fill Netty's counter (e.g. mutations arriving over internode messaging, as in S1, which
  is no longer standalone).
- Only HDD storage was tested; the bursts come from memtable-allocation stalls and segment waits, so faster
  storage may lower the holder count (or remove the stalls that synchronize the writers).
- Protocol v4 only. With v5 the request bodies would move from Netty's counter to Cassandra's `BufferPool` on the
  JDK counter (B1 territory, B = bypass investigation), changing both endpoints.
- n = 1–2 per budget above 576.

**Next step.** If the researcher wants a verified U1: 15–20 more 90 s arms of E3 @ 576 (≈ 1 h), or a two-node
variant where a coordinator forwards 15 MiB mutations so the victim's request frames are internode (JDK counter,
receive queue) — which is S1's stage 3 without the other layers. Separately, file the Netty-counter result (§3.5) as
a lead.

**Cleanup:** after every arm `ctl.sh stop` and the node's data/commit log deleted; at the end (00:33) no
`CassandraDaemon`, `U1Load` or `U1Sample` process from `/mydata/u1`, no `u1V-*` scope, nothing listening on 127.0.0.71.
Kept on `pc96:/mydata/u1/`: `runs/` (8.9 GB, 6 dumps of the dead arms), `node/` (last arm's conf and logs only),
`harness/`, `cls/`, `wip21656/` (31 MB shallow fetch of the CASSANDRA-21656 WIP branch). `/mydata/b6/cassandra` was only read.
