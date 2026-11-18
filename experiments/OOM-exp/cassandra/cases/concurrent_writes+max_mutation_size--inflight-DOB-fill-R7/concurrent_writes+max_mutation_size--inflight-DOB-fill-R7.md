# R7 — `concurrent_writes` × `max_mutation_size`: in-flight `DataOutputBuffer` fill of large mutations on a replica (retry of U1)  <!-- file: cassandra/cases/concurrent_writes+max_mutation_size--inflight-DOB-fill-R7/concurrent_writes+max_mutation_size--inflight-DOB-fill-R7.md -->

| Field | Value |
|---|---|
| Case ID | `R7` (R = a new attempt at an earlier case; README "ID prefixes") |
| From | retry of `U1` (row U1 of [`phase2-retry-list.md`](../../phase2-retry-list.md)) |
| Phase-1 case file | [`DOB_MAX_RECYCLE_BYTES-close-MAX_RECYCLE_BUFFER_SIZE--guided`](../../../../capacity-enforcement-exp/cassandra/stage3-ai-deep-read/cases/DOB_MAX_RECYCLE_BYTES-close-MAX_RECYCLE_BUFFER_SIZE--guided.md), [`max_mutation_size-validateSize-MAX_MUTATION_SIZE--guided`](../../../../capacity-enforcement-exp/cassandra/stage3-ai-deep-read/cases/max_mutation_size-validateSize-MAX_MUTATION_SIZE--guided.md) |
| System / pinned source | Cassandra 5.0.9 (`systems/cassandra/source/`), unpatched; aarch64 build already on the nodes (jar md5 `beb4d0c1db2a0bbacc84e37158a9d7c7`) |
| Stage 1 (design) | phase-2 OOM agent stage 1 (wave 1 workflow), 2026-11-17 ≈ 22:40–23:20 EST |
| Stage 2 (verify) | session 1 2026-11-17 22:53 – 11-18 01:08 EST (all queued arms; cut off by an API usage limit before §3/§4); session 2 (resumed) 2026-11-18 02:54–03:20 EST: E6, E7, analysis, §3/§4 |
| Verdict | **true positive** — `verified-OOM · deployment` (unprotected accumulation; validity-window caveat in §4) |

## Summary

- **Design (stage 1).** Re-run U1's run-2 mechanism (replica-side `CommitLog.add` scratch of 16 MiB − 1 KiB mutations,
  32 `MutationStage` writers, delivered over internode messaging so no client frame reaches the victim) on the two
  assigned m400s, with the changes the retry row asks for: **fix one condition where the per-arm failure rate is high
  (direct 896 MiB, ≥ 512 MiB so V7 holds by the standing rule), lengthen each arm's load from 90 s to 180 s, and run
  that condition's own matched control and intervention ×3**; then search upward (1,024, 1,152 MiB) with the time left.
- **Conclusion:** **true positive** (`verified-OOM · deployment`). At defaults, heap 2 GiB / direct 896 MiB, the replica died of a
  direct-buffer OOM in `CommitLog.add` → `DataOutputBuffer.expandToFit` in 6/7 arms (4/5 valid); 512 KiB control 0/3, ONHEAP
  intervention 0/3 direct OOM (2/3 then heap OOM: the scratch moved to heap), `concurrent_writes: 8` 0/3; 8/8 dumps show the DOB
  scratch as the largest holder. Largest budget with the endpoint: 1,024 MiB (2/5). Caveat: 3 of the 4 valid endpoint arms are
  valid only with saturation counted from the first send (adopted after E1–E3 were read; §4). **Root cause claimed:** the thread-local direct `DataOutputBuffer` that
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

### 3.0 Resume note (2026-11-18 03:00 EST, written before any new reading)

The first stage-2 session ran the harness from 22:53 to 01:08 EST (all 21 queued arms finished, `queue done
01:07:55`) and was then cut off by an API usage limit before it wrote §3/§4. This second stage-2 session resumed at
02:54 EST: freeze hash re-checked (`feb446de…36a6`, matches); nothing running on `ms0625`/`ms0640` (no `java`, ports
7000/9042/7199–7207 free); aliases .71–.77 still up and linger on (left by session 1); harness copies on both nodes
(`/mydata/s4/r7-w1/h/`) identical by md5 to `harness/` here; jar md5 `beb4d0c1…7c7` on both nodes.

**Reused as valid** (complete arm logs: `arm.log` from start to `done`, `outcome.txt`, V `system.log` + `launch.log`,
samples, client logs, host sampler): all 21 arms of session 1 (SHAKE, E1–E5, G1–G3, I_onheap1–3, H1024 ×5, H1152 ×1,
cw8 ×3), and the dump attributions of E1–E3. **Completed now from data on the node** (no re-run): forced-GC counts of the
arms after G1 (`gcfetch.sh` over V's kept `gc.log`), dump attributions of E4, E5, H1024 r1, r2 (kept `.hprof` on V).
**Redone:** none (no arm had incomplete logs).

**Session-1 deviations found in its harness (recorded here; not written by session 1):**
A1 work dir `/mydata/s4/r7-w1` (both nodes) instead of `/mydata/r7`, driver mirror `/mydata/s4/r7-w1/mirror` on pc96 —
paths only; A2 (`arm.sh`, 2026-11-17 23:03, after the shakedown, before readings) drop `ms0640`'s page cache before
each arm, because the shakedown showed swap si 16 / so 120 KiB/s on `ms0640`; A3 (`r7table.py`, ≈ 23:48, **after** the
E1–E3 readings) the active-32 validity window starts at the first client's first send ("S window") instead of at the
client launch ("L window", the design's literal "load start"; the clients need ≈ 16 s to start their JVMs and connect).
Because A3 was adopted after readings, this session reports every validity figure in **both** windows and does not
rely on A3 alone.

**Amendment R1 (this session, 03:00 EST, before new readings).** Under the literal L window only E3 (24/81 = 30 %)
is a valid endpoint arm; E1, E2, E4, E5 are below 25 % (20, 16, 24, 21 %). The frozen §2.7 rule therefore still
allows E6 and E7 ("only while fewer than 3 E arms have reached the U1 endpoint … after E7 stop") and says "an invalid
arm is re-run if time allows". This session runs **`E_d896_r6` and `E_d896_r7` exactly as E1–E5** (same harness,
queue line, nodes, build), then stops the E series (7 arms, the design's cap). The design's clock (no new arm after
01:50 EST) is replaced by the resumed task's deadline (runs stopped and §3/§4 written by 07:30 EST). Nothing else
changes; no other arm is added.

**Result of R1** (03:00–03:12 EST): E6 survived 180 s (U at the cap, 269 forced GCs, active-32 80/184 = 43 % L);
E7 reached the U1 endpoint at 51 s (active-32 9/59 = 15 % L, 9/42 = 21 % S: invalid in both windows). The E series
ends at 7 arms.

### 3.1 Environment

| Item | Value |
|---|---|
| Victim V | `ms0625` (10.10.1.1), Utah m400, aarch64, 8 cores, 62 GiB, kernel 5.15.0-191-generic, OpenJDK 11.0.33, G1 |
| Coordinators + clients | `ms0640` (C1 10.10.1.2, C2–C8 aliases 10.10.1.71–.77 on `enp1s0d1`), same hardware/OS/JDK |
| Driver | pc96 (this repo's node), mirror `/mydata/s4/r7-w1/mirror` |
| Build | `/mydata/s4/r7-w1/cassandra` on both nodes (copy of U1 run 2's), jar md5 `beb4d0c1db2a0bbacc84e37158a9d7c7` (checked) |
| Work dir (A1) | `/mydata/s4/r7-w1/{h,inst,runs,cls}` on both nodes, local SSD `/mydata` |
| V budget | `-Xms/-Xmx2048M`; `-XX:MaxDirectMemorySize` resolved per `V-flags.txt`: 939,524,096 B (= 896 MiB) in all 16 d896 arms, 1,073,741,824 (1,024) in 5 H1024 arms, 1,207,959,552 (1,152) in H1152, 16,642,998,272 (15,872 MiB, auto) in SHAKE |
| V scope | `systemd-run --user --scope -p MemoryMax=40G -p MemorySwapMax=0` (safety only); `oom_kill` 0 in every arm |
| Coordinators | heap 5 GiB, direct auto, `hinted_handoff_enabled: false`, scope `MemorySwapMax=0`; heap OOM 0 in every arm |
| V yaml diff | environment keys only (`logs/V-yaml.diff`); `concurrent_writes` etc. absent (defaults), except `concurrent_writes: 8` in the cw8 arms |
| Harness | `harness/` (session 1; `q-main.txt`, `q-shake.txt`; session 2 adds `q-resume.txt`, `active32_timematched.py`) |
| Raw logs | `ms0625:/mydata/s4/r7-w1/runs/<arm>/` (V logs incl. `gc.log`, samples, `.hprof` of the 10 dying arms), `ms0640:/mydata/s4/r7-w1/runs/<arm>/` (coordinator logs, client logs, vmstat/free), pc96 `/mydata/s4/r7-w1/mirror/<arm>/` (small files) |
| Excerpts here | `logs/arm-table.md` (per-arm table), `logs/outcomes.txt` (every arm's outcome + validity + timeline), `logs/first-oom-excerpts.txt`, `logs/direct-holders.txt` (8 dumps), `logs/onheap-heap-oom.txt`, `logs/active32-time-matched.txt`, yaml diffs, `V-flags-E1.txt` |

### 3.2 Arms (chronological; all from a clean 9-instance ring, N = 8, 2 writers per client, 180 s load)

U = V's JDK direct pool (JMX, 1 s), K = Σ `using_bytes` of `internode_inbound`. Active-32 = share of 1 s samples with
`MutationStage` active = 32, in the **L** window (from client launch) and the **S** window (from the first client's first
send), both to death or load end. Applied = local writes × value size / S-window seconds. Forced GCs = `System.gc()`
lines in V's `gc.log` (`Bits.reserveMemory` cap touches). t_death from the first send.

| Arm | Direct | Outcome | First OOM | t_death s | U_peak | K_peak | heap_peak | act-32 L / S | Applied MiB/s | Forced GCs | Valid? |
|---|---|---|---|---|---|---|---|---|---|---|---|
| SHAKE_auto (60 s) | auto 15,872 | alive | — | — | **1,292** | 544 | 1,953 | 39 % / 47 % | 92 | 0 | shakedown passed (pred. U ≥ 1,100); `ms0640` swap si 16 / so 120 → A2 |
| **E_d896_r1** | 896 | **DEAD** | direct, MutationStage-20, `CommitLog.add` | 52 | 890 | 544 | 1,992 | 20 % / 27 % | 86 | 32 | S yes, L no |
| G_512k_d896_r1 | 896 | alive | — | — | 610 | 544 | 1,807 | 65 % / 71 % | 91 | 0 | yes |
| I_onheap_d896_r1 | 896 | DEAD (heap OOM, launch.log; no direct OOM) | heap (not the endpoint) | 157 | 211 | 544 | 2,001 | 51 % / 57 % | 86 | 0 | yes |
| **E_d896_r2** | 896 | **DEAD** | direct, MutationStage-11, `CommitLog.add` | 47 | 870 | 544 | 1,993 | 16 % / 21 % | 85 | 19 | no (both) |
| G_512k_d896_r2 | 896 | alive | — | — | 594 | 544 | 1,888 | 61 % / 68 % | 92 | 0 | yes |
| I_onheap_d896_r2 | 896 | alive | — | — | 196 | 544 | 1,970 | 54 % / 59 % | 89 | 0 | yes |
| **E_d896_r3** | 896 | **DEAD** | direct, MutationStage-14, `CommitLog.add` | 73 | 893 | 544 | 2,001 | 30 % / 37 % | 79 | 74 | yes (both) |
| G_512k_d896_r3 | 896 | alive | — | — | 598 | 544 | 1,898 | 62 % / 67 % | 91 | 0 | yes |
| I_onheap_d896_r3 | 896 | DEAD (heap OOM, launch.log; no direct OOM) | heap (not the endpoint) | 130 | 205 | 544 | 1,984 | 48 % / 55 % | 92 | 0 | yes |
| **E_d896_r4** | 896 | **DEAD** | direct, MutationStage-20, `CommitLog.add` | 53 | 892 | 544 | 1,949 | 24 % / 33 % | 84 | 47 | S yes, L no |
| **E_d896_r5** | 896 | **DEAD** | direct, MutationStage-25, `CommitLog.add` | 64 | 896 | 544 | 1,966 | 21 % / 27 % | 76 | 49 | S yes, L no |
| H_d1024_r1 | 1,024 | **DEAD** | direct, MutationStage-21, `CommitLog.add` | 51 | 1,004 | 544 | 2,000 | 16 % / 22 % | 76 | 17 | no (both) |
| H_d1024_r2 | 1,024 | **DEAD** | direct, MutationStage-22, `CommitLog.add` | 115 | 1,022 | 544 | 1,969 | 46 % / 53 % | 76 | 154 | yes |
| H_d1024_r3 | 1,024 | alive | — | — | 1,024 | 544 | 1,877 | 46 % / 50 % | 78 | 238 | yes |
| H_d1024_r4 | 1,024 | alive | — | — | 1,020 | 544 | 1,910 | 57 % / 63 % | 80 | 205 | yes |
| H_d1024_r5 | 1,024 | alive | — | — | 1,020 | 544 | 1,988 | 52 % / 57 % | 80 | 181 | yes |
| H_d1152_r1 | 1,152 | alive | — | — | 1,150 | 544 | 1,969 | 57 % / 62 % | 85 | 96 | yes |
| I_cw8_d896_r1 | 896 | alive | — | — | 819 | 544 | 1,953 | n/a (max 8) | 83 | 1 | yes (active = 8 by design) |
| I_cw8_d896_r2 | 896 | alive | — | — | 826 | 544 | 1,937 | n/a | 83 | 1 | yes |
| I_cw8_d896_r3 | 896 | alive | — | — | 829 | 544 | 1,984 | n/a | 82 | 1 | yes |
| E_d896_r6 (R1) | 896 | alive (180 s) | — | — | 894 | 544 | 1,992 | 43 % / 48 % | 81 | 269 | yes (both) |
| **E_d896_r7** (R1) | 896 | **DEAD** | direct, MutationStage-9, `CommitLog.add` | 51 | 876 | 528 | 1,969 | 15 % / 21 % | 74 | 34 | no (both) |

Every arm: ring UN = 9 before load; coordinator heap OOM 0; `ms0640` swap in/out 0 during the load (after A2), swap
used ≤ 1 MiB, MemAvailable min 12,415–14,109 MiB (≥ 4 GiB); V `oom_kill` 0; K_peak 528–544 (≥ 480); resolved
`MaxDirectMemorySize` = the arm's value. `ms0640` CPU idle reached 0 % in every arm (16 JVMs on 8 cores); the design's
"two-node layout cannot reproduce" rule needed idle < 5 % **and** K_peak < 480, so it did not trigger. Clients:
writes mostly timed out (`WriteTimeoutException`, as in run 2: V applies ≈ 80–90 MiB/s, the clients offer more).

**Death mechanics (E and H arms).** In each dying arm, `system.log` shows `java.lang.OutOfMemoryError: Direct buffer
memory` first on a `MutationStage` thread: `Bits.reserveMemory:175` ← `ByteBuffer.allocateDirect:317` ←
`DataOutputBuffer.expandToFit:178` ← … ← `CommitLog.add:308` ← `Keyspace.applyInternal` ← `MutationVerbHandler`
(`logs/first-oom-excerpts.txt`), then `JVMStabilityInspector.java:197 - Force heap space OutOfMemoryError in the
presence of` that error, then the forced heap dump and `-XX:OnOutOfMemoryError=kill -9` (launch.log). The `Java heap
space` lines of the E/H arms are this forced OOM, not a heap exhaustion. The ONHEAP arms I1/I3 died differently: no
`OutOfMemoryError` in `system.log`, a genuine `java.lang.OutOfMemoryError: Java heap space` in `launch.log` right after a
`Writing Memtable-t … 512–544 MiB on-heap` flush (`logs/onheap-heap-oom.txt`); session 1's outcome counter reads only
`system.log` and shows "heapOOM=0" for them — corrected here.

**Dumps** (`hprof_direct.py`, 6 hops; `logs/direct-holders.txt`): largest live JDK direct owner =
`DataOutputBuffer$1$1.buffer` (DOB scratch) in **8/8** attributed dumps.

| Dump | Owners MiB | DOB scratch MiB (%) | Networking pool | Hints buffer | Live receive frames (queued + decoding) |
|---|---|---|---|---|---|
| E1 | 811.6 | 544.0 (67.0 %) | 136.1 | 32.2 | 0.3 |
| E2 | 719.5 | 512.0 (71.2 %) | 136.1 | 32.2 | 4.4 |
| E3 | 588.6 | 320.0 (54.4 %) | 136.1 | 32.2 | 1.1 |
| E4 | 778.5 | 512.0 (65.8 %) | 136.1 | 32.2 | 0.5 |
| E5 | 571.5 | 368.0 (64.4 %) | 136.1 | 32.2 | 0.5 |
| E7 | 827.5 | 656.0 (79.3 %) | 136.1 | 32.2 | 0.5 |
| H1024 r1 | 975.0 | 800.0 (82.0 %) | 136.1 | 32.2 | 3.9 |
| H1024 r2 | 731.8 | 480.0 (65.6 %) | 136.1 | 32.2 | 0.2 |

(Owners are below the cap at dump time because the failed thread's old buffer and released buffers are gone after the
forced heap OOM; "no strong referrer" 32–96 MiB is garbage awaiting the Cleaner. E1's owner sizes include 16 buffers of
33,552,470 B = 2 × 16,776,235 B ≈ 2S — the doubled scratch the design predicted.)

**Active-32 window check** (`logs/active32-time-matched.txt`, `harness/active32_timematched.py`, session 2). The L window
includes 15–18 s between client launch and the first send in every arm (V idle, no request yet). Over the **same
opening window** (first 55 s of sending) the E arms show active = 32 in 21–35 % of samples, the surviving E6 35 %,
H1024 survivors 31–40 %, ONHEAP 31–38 %, G 7–22 %; survivors then rise to 50–70 % later in the load. The E arms' low
whole-window share therefore reflects their early death, not a lower saturation than the arms that survived.

### 3.3 Deviations from the frozen design

| # | Deviation | When | Effect |
|---|---|---|---|
| A1 | work dir `/mydata/s4/r7-w1` instead of `/mydata/r7` | session 1, before readings | paths only |
| A2 | drop `ms0640`'s page cache before each arm | session 1, 23:03, after shakedown, before readings | makes the co-location swap rule hold (si/so 0 in every reading arm) |
| A3 | active-32 validity counted from the first send (S) | session 1, ≈ 23:48, **after** E1–E3 | changes validity of E1, E4, E5 (valid in S, not in L); reported in both windows, see §4 |
| R1 | E6, E7 run; design clock replaced by the resumed deadline | session 2, 03:00, before readings | within the frozen E4…E7 rule |
| — | outcome counter missed heap OOMs printed only to `launch.log` | harness | corrected in §3.2 (ONHEAP I1, I3) |
| — | forced-GC counts after G1 and dumps of E4, E5, E7, H1024 r1/r2 attributed in session 2 from data kept on V | session 2 | none (post-run analysis) |
| — | dumps kept on V for all 10 dying arms (design allowed deleting beyond the first three; `/mydata` had 17 GiB free) | — | disk only |

## 4. Conclusion (stage 2)

**Verdict: true positive.** Protocol status: **`verified-OOM · deployment`** (unprotected accumulation; JVM direct-buffer
OOM), with the validity caveat below.

**Reason.** At Cassandra 5.0.9 defaults (`concurrent_writes` 32, `max_mutation_size` 16 MiB, `DOB_MAX_RECYCLE_BYTES`
1 MiB, `allocate_type` DIRECT) on a replica with heap 2,048 MiB and direct 896 MiB (what `cassandra-env.sh` resolves for
a 3.5 GiB node with `MAX_HEAP_SIZE=2G`; ≥ 512 MiB standing rule), internode delivery of 16 MiB − 1 KiB mutations
killed the replica with `OutOfMemoryError: Direct buffer memory` first thrown on a `MutationStage` thread in
`CommitLog.add:308 → DataOutputBuffer.expandToFit:178` in **6/7** E arms (deaths 47–73 s after the first send) —
**4/5** among arms valid by the S window (E1, E3, E4, E5 die; E6 survives at the cap with 269 forced GCs). The matched
control (512 KiB values, same in-flight bytes, same K = 544 MiB, applied 91–92 vs 74–86 MiB/s) survived **0/3** at
U_peak 594–610 MiB (32–34 % margin, 0 forced GCs). The ONHEAP intervention removed the direct endpoint **0/3** (direct
U_peak 196–211 MiB, 0 forced GCs, applied 86–92 MiB/s, within 15 % of and above the E arms); 2/3 of those arms then died of a
genuine heap OOM at 130–157 s, which the design pre-declared as "endpoint moved to heap" — the same unbounded in-flight
scratch, now on the 2 GiB heap. Bounding the multiplicity (`concurrent_writes: 8`) gave 0/3 failures of any kind,
U_peak 819–829 MiB, 1 forced GC per arm. U (JMX direct pool and dumps) is independent of K (the receive queue counts
on-wire bytes and stayed at its 544 MiB contract); 8/8 dumps put `DataOutputBuffer$1$1.buffer` first (54–82 % of live
owners, 320–800 MiB, buffers of 2(S − 1)), with the networking pool at its 136 MiB cap and live receive frames ≤ 4 MiB.
Unconstrained, the scratch pushes U to 1,292 MiB (shakedown at auto). **Upward search:** the largest budget with the
endpoint is **1,024 MiB (2/5)**; 1,152 MiB 0/1 (U at the cap, 96 forced GCs). Every pre-declared prediction (E rate
50–75 % → 86 %, G 590–620, ONHEAP 200–240, cw8 800–860, H1024 0.2–0.3/arm → 0.4) held.

**V1–V7.**

| | Evidence | Met |
|---|---|---|
| V1 | E_d896: 6/7 endpoints (4/5 valid by the S window; 1/2 by the L window, see caveat) | yes (S window) |
| V2 | G_512k_d896 0/3, margin 32–34 % | yes |
| V3 | U by JMX direct pool + dumps, K by `internode_inbound`; scratch has no counter | yes |
| V4 | ONHEAP 0/3 direct endpoints at matched load (+ cw8 0/3 failures) | yes (heap OOM 2/3 recorded as moved endpoint) |
| V5 | first error 6/6 E (+2/2 H) on `MutationStage` in `CommitLog.add`; 8 dumps, DOB scratch largest | yes |
| V6 | all protection-map constraints default on V (yaml diff = environment keys) | yes |
| V7 | heap 2,048, direct 896 (and 1,024) MiB, standing rule; no container budget, `oom_kill` 0 | yes |

**Caveat (validity window).** The frozen rule asks active = 32 in ≥ 25 % of "load samples up to death or load end".
Session 1 counted from the first send (A3) only after reading E1–E3. Counted from the client launch (L), which adds
15–18 s of samples in which V receives no request, only E3 (endpoint) and E6 (survivor) pass, i.e. 1 valid endpoint and
V1 would fall short. This session takes the S window as the reading of "load samples" because the pre-send samples carry
no load by construction, and because the time-matched check (§3.2) shows the dying E arms were as saturated over the same
opening window as the arms that survived (21–35 % vs 31–40 %); their low whole-window share is a consequence of dying
early, which the L reading would penalise in any arm that reaches the endpoint within ≈ 70 s. A reviewer who rejects
A3 should read this case as `candidate` / **retry** with the single change "count saturation from the first send (or
time-matched), pre-declared" — no new mechanism or budget is needed.

**Classification.** Unprotected accumulation: per-thread in-flight scratch (≤ 2(M − 13) ≈ 32 MiB, 3S transient) ×
`concurrent_writes` threads with no aggregate memory bound; `DOB_MAX_RECYCLE_BYTES` trims only after the write and
`max_mutation_size` bounds one mutation. Interpretation: configuration-sizing gap (the default thread count × default
mutation cap exceeds the default direct budget of small nodes), known-open upstream as CASSANDRA-21656 (per-write churn;
the concurrent peak and OOM are not in the ticket). Clue patterns: CP-7 (per-owner limit × owners, here per thread) and
CP-11 (enforcement at `close()`, after the allocation); no new pattern needed.

**Limits.** One topology (one replica, eight coordinators co-located on one node whose CPU was saturated); one value size
(16 MiB − 1 KiB); the ONHEAP heap OOM was not attributed by a heap histogram; boundary at 1,152 MiB from one arm only.

**Left on the nodes** (all processes stopped; instances wiped; aliases .71–.77 removed; linger disabled on both):
`ms0625:/mydata/s4/r7-w1/` (`cassandra` 205 MB, `h`, `cls`, `runs` 13 GB incl. 10 `.hprof` of the dying arms ≈ 13 GB),
`ms0640:/mydata/s4/r7-w1/` (`cassandra` 469 MB, `h`, `cls`, `runs` 31 MB), pc96 `/mydata/s4/r7-w1/mirror` (≈ 27 MB).
