# R7 — `concurrent_writes` × `max_mutation_size`: in-flight `DataOutputBuffer` fill of large mutations on a replica (retry of U1)  <!-- file: cassandra/cases/concurrent_writes+max_mutation_size--inflight-DOB-fill-R7/concurrent_writes+max_mutation_size--inflight-DOB-fill-R7.md -->

| Field | Value |
|---|---|
| Case ID | `R7` (R = a new attempt at an earlier case; README "ID prefixes") |
| From | retry of `U1` (row U1 of [`phase2-retry-list.md`](../../phase2-retry-list.md)) |
| Phase-1 case file | [`DOB_MAX_RECYCLE_BYTES-close-MAX_RECYCLE_BUFFER_SIZE--guided`](../../../../capacity-enforcement-exp/cassandra/stage3-ai-deep-read/cases/DOB_MAX_RECYCLE_BYTES-close-MAX_RECYCLE_BUFFER_SIZE--guided.md), [`max_mutation_size-validateSize-MAX_MUTATION_SIZE--guided`](../../../../capacity-enforcement-exp/cassandra/stage3-ai-deep-read/cases/max_mutation_size-validateSize-MAX_MUTATION_SIZE--guided.md) |
| System / pinned source | Cassandra 5.0.9 (`systems/cassandra/source/`), unpatched; aarch64 build already on the nodes (jar md5 `beb4d0c1db2a0bbacc84e37158a9d7c7`) |
| Stage 1 (design) | phase-2 OOM agent stage 1 (wave 1 workflow), 2026-11-17 ≈ 22:40–23:20 EST |
| Stage 2 (verify) | pending (a fresh session; must finish before 02:30 EST 2026-11-18) |
| Verdict | `pending` |

## Summary

- **Design (stage 1).** Re-run U1's run-2 mechanism (replica-side `CommitLog.add` scratch of 16 MiB − 1 KiB mutations,
  32 `MutationStage` writers, delivered over internode messaging so no client frame reaches the victim) on the two
  assigned m400s, with the changes the retry row asks for: **fix one condition where the per-arm failure rate is high
  (direct 896 MiB, ≥ 512 MiB so V7 holds by the standing rule), lengthen each arm's load from 90 s to 180 s, and run
  that condition's own matched control and intervention ×3**; then search upward (1,024, 1,152 MiB) with the time left.
- **Conclusion:** pending (stage 2). **Root cause claimed:** the thread-local direct `DataOutputBuffer` that
  `CommitLog.add` serializes each mutation into grows to 2S (3S transiently) and is held through segment allocation and
  the copy; no control bounds the sum over writers except `concurrent_writes` (32), which is a thread count, not a
  memory limit (unprotected accumulation).

---

## 1. Candidate

**Retry row (quoted from [`phase2-retry-list.md`](../../phase2-retry-list.md), 2026-11-17):**

> | [U1](cases/candidates/concurrent_writes+max_mutation_size--inflight-DOB-fill/concurrent_writes+max_mutation_size--inflight-DOB-fill--run2-internode.md) | 2026-11-17 | `candidate` (V1 unmet in both runs): run 2 (aarch64, 8 coordinators, 16 MiB − 1 KiB mutations over internode) direct OOM 2/14 at heap 2 GiB / direct 1,024 MiB and 2/4 at 896; unconstrained U_peak 1,212 MiB; 15 MiB mutations 0/8 down to 640; run 1 2/14 at 576 MiB. Control 0/3, `concurrent_writes: 8` 0/3, ONHEAP 0/3 | HANDOFF: (a) 10–15 more arms at 1,024 MiB (failure rate ≈ 1/7, so 3/14+ is not assured), or (b) fix the condition at 896 MiB with its own matched control and intervention ×3 (likely `diagnostic`). Raise the per-arm rate: more concurrent large-mutation writers (counter and view stages, N20), keep Netty's separate counter from killing arms first (B9, run 1) | picked again: R7 |

**Earlier attempts (evidence this design builds on, not pooled with it):**
[U1 run 1](../candidates/concurrent_writes+max_mutation_size--inflight-DOB-fill/concurrent_writes+max_mutation_size--inflight-DOB-fill.md)
(pc96, x86, victim as coordinator: 2/14 at 576 MiB, 4 arms lost to Netty's counter) and
[U1 run 2](../candidates/concurrent_writes+max_mutation_size--inflight-DOB-fill/concurrent_writes+max_mutation_size--inflight-DOB-fill--run2-internode.md)
(aarch64, victim `ms0625` as the only replica, coordinators on four other m400s). Run 2's numbers used below
(all heap 2,048 MiB, N = 8 coordinators, value E16 = 16,776,192 B, 90 s load): at 1,024 MiB 2/14 (deaths at 38 and
54 s); at 896 MiB 2/4 (deaths 48, 68 s); N = 4 at 896 1/3 (death 9 s); 1,152 0/1; auto 0/1 with **U_peak 1,212 MiB**;
control (512 KiB) U_peak 594–612; `-Dcassandra.dob.allocate_type=ONHEAP` direct 202–230, heap peak 1,912–1,992;
`concurrent_writes: 8` U_peak 800–842; first error 5/5 a `MutationStage` thread, JDK counter,
`MutationVerbHandler.applyMutation` → `CommitLog.add:308` → `DataOutputBuffer.expandToFit:178`; dumps: DOB scratch
58–80 % of JDK owners, networking pool 136 MiB, hints buffer 32 MiB, live receive frames ≈ 0.
[S1](../convergence/internode_receive_queue+hint_slabs+DOB+networking_pool--direct-combo/internode_receive_queue+hint_slabs+DOB+networking_pool--direct-combo.md)
(true positive, stacked) contains U1's mechanism as one layer (x86, loopback, 3/3 at 768 MiB).

**Phase-1 constraints and stage 4.** `DOB_MAX_RECYCLE_BYTES` (1 MiB): `DataOutputBuffer` scratch recycle at
`close()` keeps a buffer of capacity ≤ 1 MiB and replaces larger ones — the check bounds what a thread keeps **after**
a write, not what it holds during one (stage 4 closed 2026-10-19, both tiers Confirmed; the unit tier recorded
C = 2(S − 1) after a copy, the "in use" size the check does not bound). `max_mutation_size` (16 MiB = ½ of the 32 MiB
commit-log segment): `Mutation.validateSize` refuses a mutation whose serialized size + 12 exceeds it (stage 4 closed
2026-10-19, Confirmed at both tiers). Together: per thread ≤ 2(M − 13) ≈ 32 MiB in use, × `concurrent_writes`
threads, with no aggregate limit.

**JIRA prior art** (read only, JIRA REST search 2026-11-17 ≈ 22:55 EST, plus the survey
[`jira-oom-survey.csv`](../../../../capacity-enforcement-exp/cassandra/stage5-oom-clue-find/jira-oom-survey.csv); nothing posted):

| Query | Hits that matter |
|---|---|
| `text ~ "DataOutputBuffer" AND text ~ "Direct buffer memory"` (7) | CASSANDRA-16471 (Fixed 5.0): made the scratch `allocateDirect` by default, `cassandra.dob.allocate_type` to switch; CASSANDRA-8670 (Fixed 2.2): large columns + NIO pooling → excessive direct memory (thread-local NIO buffers, historical) |
| `text ~ "CommitLog.add" AND text ~ "OutOfMemoryError"` (1) | CASSANDRA-5982 (Fixed 1.2): many tables, unrelated holder |
| `text ~ "large mutation" AND text ~ "direct memory"` (23) | **CASSANDRA-21656 (In Progress, updated 2026-09-11): "large mutations over-allocate on the commit log path"** — same buffer, measured as per-write churn on one thread; its WIP branch (U1 run 1 §4) keeps the scratch for mutations ≥ 1,000,000 B; CASSANDRA-12783 (Open): break up large MV mutations to prevent OOMs (view path, not this holder) |
| `text ~ "expandToFit"` (3), `text ~ "dob_max_recycle_bytes"` (2) | CASSANDRA-16471 again; nothing on the concurrent peak |
| survey CSV | CASSANDRA-11838 (Fixed 3.8): recycled DOBs retaining large buffers (the idle side, now `DOB_MAX_RECYCLE_BYTES`); CASSANDRA-10971 (Fixed 3.5): compressed commit-log buffers without backpressure (different holder; compression off by default) |

**Verdict: `known-open`** (CASSANDRA-21656 names the buffer but not the `concurrent_writes` × 2–3S concurrent peak
or an OOM; not known-fixed, so R7 is a real candidate, not a positive control). Not documented as by design.

---

## 2. Design solution (stage 1; frozen)

### 2.1 Mechanism

On the replica, `MutationVerbHandler.applyMutation` (`db/MutationVerbHandler.java:36`) applies each incoming
`MUTATION_REQ` synchronously on its `MutationStage` thread: `Mutation.applyFuture` → `Keyspace.applyInternal(:625)` →
`CommitLog.add` (`db/commitlog/CommitLog.java:300–330`). `add` checks `validateSize` (`:304`), takes the thread-local
`DataOutputBuffer.scratchBuffer` (`:306`; `io/util/DataOutputBuffer.java:53–88`, `ALLOCATION_TYPE` default `DIRECT`
→ `ByteBuffer.allocateDirect`, JDK `Bits`-counted), serializes the mutation into it (a single-cell 16 MiB − 1 KiB value
grows it to S − 1, then the end-of-partition byte doubles it in `expandToFit` (`:174–178`) to 2(S − 1), the old buffer
live during the copy → 3S transient), allocates a segment slot (`segmentManager.allocate`, `:311`; blocks when segments
are not ready), copies into the mmap segment, and only at `close()` (end of the try, after the copy) is the buffer
trimmed back by `DOB_MAX_RECYCLE_BYTES`. Up to `concurrent_writes` = 32 threads hold such buffers at once. The
internode receive queue bounds the number of admitted messages in **on-wire** bytes (≈ 34 × 16 MiB), not their
processing copies. When the sum touches `MaxDirectMemorySize`, `Bits.reserveMemory` runs `System.gc()` and retries for
≈ 0.5 s; the OOM needs a burst whose holders stay inside `CommitLog.add` past that window (run 2: bursts follow
memtable-allocation stalls behind the 100 MB/s commit-log disk). **Direction:** unprotected accumulation (no control
covers the in-flight scratch; implicit bound `concurrent_writes` × 2–3 × S). Technique notes:
[`bypass-playbook.md`](../../../bypass-playbook.md) (protection map, matched payload control),
[`default-convergence-playbook.md`](../../../default-convergence-playbook.md) (defaults, budget search).

**What R7 changes against run 2 (and why):**

| # | Change | Why |
|---|---|---|
| 1 | **Fixed endpoint condition at direct 896 MiB** (heap 2,048), with its own control ×3 and intervention ×3 | retry row option (b); run 2's per-arm rate there ≈ ½ (2/4) vs ≈ 1/7 at 1,024; 896 ≥ 512 MiB meets V7 by the standing rule (§2.3) |
| 2 | **Load 180 s per arm** (was 90 s) | the endpoint is a hazard over time: run 2 at 896 (N = 8) 2 deaths in ≈ 296 s of saturated load → λ ≈ 1/148 s → P(death in 180 s) ≈ 1 − e^(−180/148) ≈ 0.70 (90 s: 0.46). Disk allows it: commit-log segments recycle, V's data stayed ≤ 42 MB per arm (overwrites of 200 keys), commit log ≤ 1 GB |
| 3 | **Two nodes only**: victim `ms0625`; all 8 coordinators + 8 clients on `ms0640` (C1 at 10.10.1.2, C2–C8 at alias IPs 10.10.1.71–.77) | the assigned nodes. V-side load is unchanged: V's receive queue binds at its global reserve (K ≈ 544 MiB ≈ 34 messages) in both topologies |
| 4 | Coordinators: heap **5 GiB** (was 8 GiB), clients **2 writers × 4 in flight** (was 2 × 6), `hinted_handoff_enabled: false` on coordinators only | 8 × 8 GiB pretouched (`-XX:+AlwaysPreTouch`) does not fit 62 GiB; at 5 GiB the coordinator's per-IP native in-flight limit (heap/40 = 134,217,728 B) admits exactly 8 E16 requests (8 × ≈ 16,776,230 B), the same 8 per coordinator that run 2's coordinators could forward (128 MiB send endpoint reserve). Run 2's coordinators wrote 4–8.5 GB of hints each per arm; 8 on `ms0640` (19 GiB free) would fill it. Hint replay to V was ≤ 1 MiB/s (throttle) vs ≈ 100 MiB/s applied, so turning hints off on the coordinators does not change V's load |
| 5 | Intervention = **`-Dcassandra.dob.allocate_type=ONHEAP`** ×3 (primary); `concurrent_writes: 8` optional | ONHEAP moves only the claimed holder out of direct memory (run 2: direct 202–230, a 3.9× margin at 896). `concurrent_writes: 8` shifts the bytes to queued receive frames (run 2: 800–842 MiB, only 6–11 % below 896), so at 896 it is a weak test; run only if time remains |
| 6 | Clients and coordinators get no other change; V's yaml is the run-2 environment diff only | V6 |

Not taken from the retry row, with reasons: **counter and view stages (N20)** — a 16 MiB counter mutation needs
≈ 500 k counter cells in one partition update under the counter locks, and materialized views are disabled by default
in 5.0 (`materialized_views_enabled: false`; enabling them is a non-default feature switch); both would make a new
mechanism, not raise this one's rate. **B9 (Netty counter, run 1)** is already avoided by the replica path (run 2:
no client frame reaches V; V's Netty counter 160–176 MiB, not exhausted).

### 2.2 Protection map (fixed before readings)

| Domain | Allocation / release | Contract C | Multiplicity | Aggregate coverage | Lifetime | Budget metric |
|---|---|---|---|---|---|---|
| **U1 in-flight DOB scratch** (claimed holder) | `DataOutputBuffer$1$1.buffer`, grown in `CommitLog.add` (`CommitLog.java:306–308`), trimmed at `close()` | **none in flight**; `max_mutation_size` 16 MiB per mutation (≤ 2(M − 13) ≈ 32 MiB per thread) | ≤ `concurrent_writes` 32 | none; not reconciled with `MaxDirectMemorySize` | serialize → segment allocate → copy | JDK `Bits` (`java.nio` direct pool) |
| R receive frames | `LargeMessage` buffers (networking `BufferPool`; overflow `allocateDirect`), released at deserialize on the stage thread | per connection Q 4 MiB, per endpoint E 128 MiB, global G 512 MiB, on-wire bytes, until the verb returns (`AbstractMessageHandler.acquireCapacity:411–440`, `ProcessMessage.run:410–446`) | N = 8 peers | K = Σ `using_bytes` ≤ G + N·Q = 544 MiB | first frame → deserialize | JDK `Bits` |
| P networking `BufferPool` | pool chunks backing the frames | `networking_cache_size` = min(128, heap/16) = **128 MiB** retained | 1 | overflow unpooled | standing | JDK `Bits` |
| D kept DOB | scratch after `close()` | `DOB_MAX_RECYCLE_BYTES` **1 MiB**/thread | threads that serialized | none | standing | JDK `Bits` |
| B0 baseline | hints-writer buffer 32 MiB, NIO, 8 MiB chunk-cache chunk | per pool | — | — | standing | JDK `Bits` |
| Netty arenas (internode event loops) | Netty `PlatformDependent` counter | separate limit = `MaxDirectMemorySize` | — | own counter | — | Netty counter (not the endpoint) |
| Heap | deserialized mutations (≈ S each), memtable `heap_buffers` | `memtable_heap_space` = ¼ heap = 512 MiB | ≤ admitted | flush | — | heap 2,048 MiB |

### 2.3 Configuration and budget audit

| Setting | Class | Value (resolved at V's heap 2,048 MiB) |
|---|---|---|
| `concurrent_writes`, `max_mutation_size`, `commitlog_segment_size`, commit-log sync, `DOB_MAX_RECYCLE_BYTES`, `cassandra.dob.allocate_type`, internode receive/send queue capacities, `internode_max_message_size`, `networking_cache_size`, `file_cache_size`, `memtable_heap_space`, `memtable_allocation_type`, `commitlog_total_space`, write timeout, V's hinted handoff | **default** on V (absent from yaml, no `-D`) | 32; 16 MiB; 32 MiB; periodic 10 s; 1 MiB; DIRECT; 4/128/512 MiB; 128 MiB (min(recv, send) endpoint reserve); 128 MiB; 512 MiB; 512 MiB; `heap_buffers`; min(8,192 MiB, ¼ of the 39 GiB volume) = 8,192 MiB; 2 s; on |
| V yaml diff | environment | cluster name `r7`, listen/rpc address, seeds `10.10.1.1:7000`, `GossipingPropertyFileSnitch` (dc `v`), data/commitlog/hints/saved_caches/cdc dirs under `/mydata/r7/inst/V`, `num_tokens: 1`, `initial_token`, `auto_bootstrap: false` |
| Coordinator yaml diff | environment (non-victim nodes) | the same keys (dc `c`) **plus `hinted_handoff_enabled: false`** (reason: §2.1 change 4) |
| Keyspace | environment | `u1r2` = `NetworkTopologyStrategy {v: 1}` (V holds every replica; coordinators none); table `u1r2.t (pk int PRIMARY KEY, b blob)` |
| V heap | budget | `MAX_HEAP_SIZE=2048M` (the ideal budget) |
| V direct | budget (the dial) | `MAX_DIRECT_MEMORY_SIZE=896M` for the endpoint condition (documented `cassandra-env.sh` override); 1,024 / 1,152 in the upward search; unset (auto) in the shakedown — resolves to **15,872 MiB** on the m400 (½ RAM 32,124 > 31,744 → 31,744/2) |
| Coordinators | environment | heap 5 GiB, direct auto (15,872), `-XX:-HeapDumpOnOutOfMemoryError`, JMX ports 7199 (C1), 7201–7207 (C2–C8) |
| V scope | environment | `systemd-run --user --scope -p MemoryMax=40G -p MemorySwapMax=0` (safety only, non-binding) |
| Coordinator scopes | environment | `-p MemorySwapMax=0` |
| Storage | environment | each node's local SATA SSD (`/mydata`, LVM); not tmpfs |
| Byteman, patches | not used | — |

**V7 argument (before readings).** Heap 2,048 MiB is the ideal budget. Direct 896 MiB is ≥ 512 MiB, so it meets V7
by the standing rule without a per-case review. It is also exactly what `cassandra-env.sh` (`calculate_heap_sizes`,
lines 51–68, 139–141) resolves for a node with 3,584 MiB of RAM (¼ RAM); such a node's operator setting
`MAX_HEAP_SIZE=2G` (documented override) gets heap 2,048 / direct 896 — a plausible small-VM deployment. 1,024 MiB is
the 4 GiB-node resolution (heap 2,048 auto, direct 1,024 auto). No container limit is the budget (V's 40 GiB scope is
safety only and must show `oom_kill` 0). **Conditions label if V1–V7 hold: `deployment`.**

### 2.4 Ceiling arithmetic (JDK counter, V)

| Term | MiB |
|---|---|
| B0 measured idle (run 2) | 50 |
| P networking pool at cap + 1 chunk | 136 (128 + 8) |
| 32 writers × 2S16 standing (S16 = 16,776,192 B → 2S ≈ 32 MiB) | 1,024 |
| **Sum (all writers holding their doubled buffer)** | **1,210** (run 2 measured U_peak 1,212 at auto) |
| + transient doubling copy (≤ 32 × S) | up to + 512 |
| Budget | 896 (endpoint condition) → demand exceeds it by ≥ 314 MiB when ≥ 22 writers hold 2S at once |

Control G (524,288 B values): 50 + 136 + 32 × 1 MiB + frames → run 2 measured 594–612; margin to 896 ≈ 32–34 %
(meets the 30 % starting target). ONHEAP: direct 202–230 (run 2) → margin ≈ 74 %.

### 2.5 Workload and environment

- **Nodes.** Victim **V = `ms0625`** (10.10.1.1, aarch64, 8 cores, 62 GiB, `/mydata` 39 GiB with **29 GiB free** at
  stage 1). Coordinators **C1–C8 + their clients = `ms0640`** (10.10.1.2; aliases 10.10.1.71–.77 on `enp1s0d1`;
  8 cores, 62 GiB, `/mydata` **19 GiB free**). Both 10 GbE, NTP-synced, swap 8 GiB present (kept at 0 for the measured
  processes by the scopes). Checked read-only 2026-11-17 22:45 EST: no `java` running on either; ports 7000/9042/7199
  free; aliases .71–.77 unanswered; `sudo -n` works; linger off. Do not touch `/mydata/u1r2/runs` (U1 run 2's data),
  `/mydata/s2r2`, `/mydata/b8`, `/mydata/oom-smoke`. Driver host: `pc96` (this repo's node), as in run 2.
- **Build.** Reuse U1 run 2's copy: `cp -a /mydata/u1r2/cassandra /mydata/r7/cassandra` on both nodes, check
  `md5sum /mydata/r7/cassandra/build/apache-cassandra-5.0.9-SNAPSHOT.jar` = `beb4d0c1db2a0bbacc84e37158a9d7c7`
  (present on both at stage 1). No rebuild; OpenJDK 11.0.33, G1 (record `java -version`, `uname -r`).
- **Client.** `U1R2Load` unchanged (driver 3.12.1, protocol v4, prepared `INSERT INTO u1r2.t (pk, b)`, CL ONE,
  zero-filled blobs, keys mod 200, one `Cluster` per writer, whitelisted to its coordinator, no retries, no rate cap),
  one client per coordinator on `ms0640`, `-Dwriters=2`, client JVM `-Xmx2g`.
- **Values and in-flight.** E16 = **16,776,192 B** (16 MiB − 1 KiB; passes `max_mutation_size`, the 16 MiB native
  frame and the 128 MiB `internode_max_message_size`), **4 in flight per writer** (8 per coordinator, 64 total).
  Control G = **524,288 B**, **124 in flight per writer** (same in-flight bytes per client within 3 %, under the
  coordinator's per-IP limit).
- **Arm procedure** (as run 2, from a clean ring each time): wipe all instances on both nodes; generate V and C1–C8;
  start V, wait for 9042; start C1–C8 in parallel; wait for `nodetool status` UN = 9; create the schema via C1;
  `nodetool getendpoints u1r2 t 1` = 10.10.1.1; start V's samplers; 5 s idle; **180 s load**; 20 s observation;
  collect; stop and wipe everything. New: during the load, poll V's pid every 2 s; if V is dead, wait 5 s, kill the
  clients and go to the observation phase (record the real load end). New: a host sampler on `ms0640`
  (`vmstat 1` and `free -m` every 5 s into the arm's dir) for the co-location checks.

**Harness** (stage 2 builds it in `harness/` of this folder, from
[`../candidates/concurrent_writes+max_mutation_size--inflight-DOB-fill/harness-run2/`](../candidates/concurrent_writes+max_mutation_size--inflight-DOB-fill/harness-run2/), changing only):

| File | Change |
|---|---|
| all | `/mydata/u1r2` → `/mydata/r7` (B, ROOT, INST, H, RUNS, cls, mirror, STOP); keep keyspace `u1r2` and the class names |
| `ctl.sh` | cluster name `'r7'`; `IP`: V 10.10.1.1, C1 10.10.1.2, C2–C8 10.10.1.71–.77; `TOK` unchanged (9 values); JMX port per role (C1 7199, Ck → 7199+k for k = 2…8, i.e. 7201–7207) by `sed` on the instance's `cassandra-env.sh`; scopes unchanged |
| `node.sh` | client `-Xmx2g`; `schema` via 10.10.1.2; `wipe` unchanged (scoped to `/mydata/r7/inst`); new `csamp`/`cstop`: host sampler on `ms0640` |
| `arm.sh` | `HOST`: V `ms0625`, C1–C8 `ms0640`; `NODES="ms0625 ms0640"`; always C1–C8 (N = 8); `CX` default `5G`; `LOAD` default 180; coordinators generated with extra `hinted_handoff_enabled=false`; V-dead poll (above); mirror loops over `ms0640` only |
| `alias.sh` (new) | `up`: for x in 71…77, ping-check that 10.10.1.x is free, then `ssh ms0640 sudo ip addr add 10.10.1.x/24 dev enp1s0d1`; `down`: delete them |
| `queue.sh`, `dump.sh`, `peaks.py`, `table.py`, `gcwin.py`, `hprof_direct.py`, `U1R2Load.java`, `U1R2Sample.java`, `logback-quiet.xml` | path change only |

Also: `sudo loginctl enable-linger jason92` on both nodes for the run (systemd user scopes), disabled at the end;
`node.sh build` compiles the two classes into `/mydata/r7/cls` on each node.

### 2.6 Instruments

| What | How | Interval |
|---|---|---|
| **U** = V's JDK direct use | `U1R2Sample` JMX `java.nio:type=BufferPool,name=direct` MemoryUsed (plus count) | 1 s |
| **K** = receive-queue counter | CQL `system_views.internode_inbound` Σ `using_bytes` (per peer in `peers.txt`) | 1 s |
| writers | `MutationStage` active / pending / completed; commit-log `WaitingOnSegmentAllocation`, `WaitingOnCommit`; dropped `MUTATION_REQ`; local write count; memtable on-heap; networking pool | 1 s |
| heap / GC | heap used (JMX); V's GC log: count `System.gc()` lines (= `Bits.reserveMemory` forced GCs); `gcwin.py` worst 60 s STW share | 1 s / per arm |
| physical | V's cgroup `memory.current`, `anon`, `file`, `oom`, `oom_kill` | 1 s |
| initiating failure | V `system.log`: first `OutOfMemoryError` with stack (`first-oom.txt`); Netty `OutOfDirectMemoryError` count; heap OOM count | per arm |
| holders at failure | Cassandra's forced heap dump (shipped `-XX:+HeapDumpOnOutOfMemoryError`) → `dump.sh` → `hprof_direct.py` (6 hops) on pc96, `ionice -c3` on V | failing arms |
| co-location | `ms0640`: `vmstat 1` (us/sy/id/wa, swap si/so), `free -m` MemAvailable every 5 s; coordinator heap-OOM count; client sent/ok/timeouts | 1 s / 5 s |
| config proof | `jcmd VM.flags` (MaxDirectMemorySize, MaxHeapSize), `/proc/<pid>/cmdline`, yaml diffs of V and C1 | per arm |

U is independent of K (K counts on-wire bytes of admitted messages; the scratch has no counter). The 1 s sampler
under-reads transient peaks; the forced-GC count shows cap touches.

### 2.7 Arms, predicted response and stopping budget

| Arm (name) | Direct | Value / in flight per writer | Change | n | Predicted |
|---|---|---|---|---|---|
| `SHAKE_auto` (not a reading) | auto | E16 / 4 | load 60 s | 1 | U_peak ≥ 1,100 MiB, K_peak ≥ 480, active = 32 in ≥ 25 % of load samples; `ms0640` MemAvailable ≥ 4 GiB, swap 0 |
| **`E_d896_rN`** (endpoint) | 896 | E16 / 4 | — | 3–7 | U at the cap (≥ 40 forced GCs per surviving arm); **U1 direct OOM in ≈ 50–75 % of arms**, first error on a `MutationStage` thread via `MutationVerbHandler` → `CommitLog.add` → `expandToFit`; dump: DOB scratch the largest JDK holder (≥ 50 %), live receive frames ≈ 0, pool 136, hints buffer 32 |
| **`G_512k_d896_rN`** (matched control) | 896 | 524,288 B / 124 | — | 3 | survive 3/3; U_peak ≈ 590–620; K_peak ≈ 544 (same receive-queue occupancy); applied ≈ 100 MiB/s; 0 forced GCs |
| **`I_onheap_d896_rN`** (intervention) | 896 | E16 / 4 | V JVM `-Dcassandra.dob.allocate_type=ONHEAP` | 3 | no direct OOM 3/3; direct U_peak ≈ 200–240; heap peak near 2 GiB; applied ≈ 100 MiB/s. A heap OOM is possible (run 2 peak 1,992 of 2,048 in 90 s): record it as "endpoint moved to heap", not as a direct endpoint |
| `H_d1024_rN` (upward search) | 1,024 | E16 / 4 | — | 2–5 | P(death in 180 s) ≈ 0.2–0.3 per arm (run 2 λ ≈ 1/720 s) |
| `H_d1152_r1` (upward search) | 1,152 | E16 / 4 | — | 1 | likely survive at the cap |
| `I_cw8_d896_rN` (optional) | 896 | E16 / 4 | V yaml `concurrent_writes: 8` | 0–3 | U_peak ≈ 800–860 (frames replace scratch); may touch the cap; reported, not needed for V4 |

**Order** (interleaved so the core set completes first): `SHAKE_auto`, then
E1 G1 I1 E2 G2 I2 E3 G3 I3, then E4…E7 **only while fewer than 3 E arms have reached the U1 endpoint** (stop the E
series at the 3rd endpoint or after E7), then H1024 ×2 (up to ×5 if time remains), then H1152 ×1, then cw8 (up to ×3).

**Endpoint definition (per arm).** V's `system.log` shows `java.lang.OutOfMemoryError: Direct buffer memory` whose
first occurrence is on a `MutationStage` thread with `CommitLog.add` in its stack. Any other first OOM (frame
allocation in the networking path, Netty `OutOfDirectMemoryError`, heap OOM) is recorded as "OOM, other holder" and
does not count toward V1.

**Arm validity (pre-declared; an invalid arm is re-run if time allows and reported).** Ring UN = 9 before the load; no
coordinator died or heap-OOMed; `ms0640` swap in/out 0 and MemAvailable ≥ 4 GiB through the load; V's resolved
`MaxDirectMemorySize` equals the arm's value; for E/H/I arms K_peak ≥ 480 MiB and active = 32 in ≥ 25 % of load
samples up to death or load end (G arms: K_peak ≥ 480); `oom_kill` 0. **If the shakedown fails saturation**, before
any reading, a dated amendment may (in order) raise the clients to 6 in flight per writer, or drop coordinator heap to
4 GiB with clients at 3 per writer; if `ms0640` CPU is the limit (id < 5 % and K_peak < 480), record that the
two-node layout cannot reproduce the condition and end as **retry** (invalid design), not false positive.

**Stopping budget.** 180 s load + 20 s observation per arm; at most 7 E arms; no new arm after **01:50 EST**; all
processes stopped by **02:10**; the case file and write-backs done by **02:30 EST 2026-11-18**. No escalation after
an OOM.

**Time plan** (EST; stage 2 expected to start ≈ 23:30): read, hash check, node check 10 min → harness copy/adapt,
build copy, `node.sh build`, aliases, linger ≤ 30 min (≈ 00:10) → shakedown ≈ 7 min (≈ 00:20) → core 9 arms at
≈ 7.5 min each for survivors, ≈ 5 min for early-stopped deaths (≈ 01:20) → E4…E7 per the stop rule, then H arms until
01:50 → last arm done ≈ 02:00; dump attributions (≈ 2 min each) run in the background during later arms → cleanup
02:00–02:10 → §3, §4 and write-backs 02:10–02:30. If preparation ends later than 00:30, drop optional arms in reverse
order (cw8, H1152, extra H1024), never the core nine.

**Resource fit.** V: heap 2 GiB pretouched + direct ≤ 896 MiB + Netty ≤ ≈ 180 MiB + metaspace ≈ 3.5 GiB of 62 GiB;
one Cassandra JVM and the sampler on 8 cores. `ms0640`: 8 × (5 GiB pretouched heap + ≈ 0.7 GiB native) + 8 clients
× ≈ 0.5 GiB ≈ 50 GiB of 62 GiB (checked by the MemAvailable rule); 16 JVMs on 8 cores (checked by the shakedown).
Disk: V writes ≤ ≈ 2 GB per arm (commit log; wiped) plus ≈ 1.0–1.1 GB per failure dump; at most ≈ 10 dumps → ≤ 12 GB
of 29 GiB free. Keep the dumps of the first three endpoint arms; before each later arm, if `ms0625:/mydata` has
< 12 GiB free, delete the `.hprof` of arms already attributed beyond those three (their `direct-holders.txt` stays).
`ms0640`: no hints, system tables and logs only (≪ 19 GiB).

### 2.8 Controls, intervention and verdict mapping

- **Matched control (V2):** G at the same budget, N, writers and in-flight bytes, same applied bytes/s (disk-bound)
  and the same receive-queue occupancy, without large scratch buffers. Survive 3/3 with ≥ 30 % margin.
- **Intervention (V4):** ONHEAP at the same budget and load: removes the claimed holder from the direct pool and
  nothing else; the direct endpoint must be absent 3/3 with applied bytes/s within 15 % of the E arms' pre-death rate.
- **Upward search:** report the largest budget with an endpoint and its n/N (H arms), and the shakedown's
  unconstrained U_peak.
- **Verdict (oom-agent playbook):** **true positive** when E reaches the U1 endpoint in ≥ 3 valid arms (report n/N),
  G 0/3, ONHEAP 0/3 direct endpoints, ≥ 1 dump (ideally 3) attributes the largest JDK holder to
  `DataOutputBuffer$1$1.buffer`, and the V6/V7 audit above holds → `verified-OOM · deployment` (unprotected
  accumulation). **Retry** when E has < 3 endpoints in its ≤ 7 arms, or the control or intervention reaches the
  endpoint, or the arms are invalid; state what to change. **False positive** only if valid saturated arms show the
  scratch stopping below the budget (e.g. U_peak at auto < 896) — not expected, since the ceiling (1,210) was
  measured in run 2.
- **Write-back** (stage 2): retry-list row U1 → `true positive (R7)` / `retry (R7)`; `_INDEX.md` row; a clue pattern
  for a true positive only if none covers "per-thread scratch × thread pool, no aggregate limit"; nothing to JIRA.
- **Cleanup** (stage 2): `node.sh wipe` on both nodes, `alias.sh down`, linger off on both, check 0 `java`
  processes of this run and nothing listening on 7000/9042/7199–7207; keep `/mydata/r7/runs` and `/mydata/r7/cassandra`
  for the owner's acceptance; say what is left.

`sha256 of §1–§2 at freeze: feb446de0bf0ff3dc96b03820600302c9ed3e333a86d8798ff142df25f7836a6` (sha256 of the file's bytes from the line `## 1. Candidate` up to, not including,
this line) · amendments after the freeze: none.

## 3. Runs (stage 2)

pending

## 4. Conclusion (stage 2)

pending
