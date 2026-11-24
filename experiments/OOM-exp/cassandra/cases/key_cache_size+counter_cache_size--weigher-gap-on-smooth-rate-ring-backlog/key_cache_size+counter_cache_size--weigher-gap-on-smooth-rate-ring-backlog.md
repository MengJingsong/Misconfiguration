# R25 (retry of R19 / R11 / R8 / B7) — key_cache_size + counter_cache_size: weigher gap on a smooth-rate, fixed-total RF=3 ring backlog  <!-- file: cassandra/cases/key_cache_size+counter_cache_size--weigher-gap-on-smooth-rate-ring-backlog/key_cache_size+counter_cache_size--weigher-gap-on-smooth-rate-ring-backlog.md -->

| Field | Value |
|---|---|
| Case ID | `R25` (R = a new attempt at an earlier case: R19, itself a retry of R11 / R8 / B7) |
| From | retry of `R19` ([phase-2 retry list](../../phase2-retry-list.md), row R19, status `picked again: R25`; owner-approved batch of 2026-11-24) |
| Phase-1 case file | [`key_cache_size-create-size--autonomous`](../../../../capacity-enforcement-exp/cassandra/stage3-ai-deep-read/cases/key_cache_size-create-size--autonomous.md), [`counter_cache_size-putcachedcounter-capacity--autonomous`](../../../../capacity-enforcement-exp/cassandra/stage3-ai-deep-read/cases/counter_cache_size-putcachedcounter-capacity--autonomous.md) (phase-1 row OC-2) |
| System / pinned source | Cassandra 5.0.9 (`systems/cassandra/source/`; on the nodes `ms0611:/mydata/s4/cassandra-base`, jar md5 `1becab414e5f…`, the build R11 and R19 ran) |
| Stage 1 (design) | phase-2 OOM agent, stage 1 (Claude Opus 5.5, fresh subagent), 2026-11-24 05:40–06:40 EST |
| Stage 2 (verify) | pending (a fresh agent); ring V `ms0611`, R1 `ms0625`, R2 `ms0617`, client `ms0604` |
| Verdict | `pending` |

## Summary

- **Conclusion:** pending (stage 2). Design: the same three arm types as R19 (T shipped weigher, P weigher that charges
  the per-entry overhead, E caches invalidated) on the same aarch64 RF=3 ring at 2 GiB heaps and shipped defaults, but
  the inflow rate is set from smooth CL=ONE E arms (6,000 → 5,600 → 5,200 writes/s, 16 × 256 in flight, a zero-burst
  pacer), and the fixed total N is then placed by ≥ 3 E arms per N level.
- **Root cause (claimed):** no control charges the coordinator's queued local writes (S2: `LocalMutationRunnable` and
  its `HintRunnable` re-queue on `MutationStage`), and the key/counter cache weighers count key + value bytes only, not
  the ≈ 90–100 B per entry of the Caffeine container (B7). The claim tested: at one fixed rate and total, the uncounted
  ≈ 164 MiB of the shipped weighers decides whether V's 2 GiB heap survives the backlog.

## 1. Candidate

**Retry row (quoted from [`phase2-retry-list.md`](../../phase2-retry-list.md), as of 2026-11-24 05:40 EST):**

> | [R19](cases/key_cache_size+counter_cache_size--weigher-gap-on-rate-capped-ring-backlog/key_cache_size+counter_cache_size--weigher-gap-on-rate-capped-ring-backlog.md) (retry of R11 / R8 / B7) | 2026-11-21 | Rate-capped inflow on the ring (client ms0604, 2 GiB): the CL=ALL arm measured a_E = 4,318/s, so the frozen rule set r = 4,700/s, but V's CL=ONE apply rate is > 5.2 k/s, so E kept up (pending ≤ 21 k, heap after GC ≤ 927 MiB at N = 140–200 k) and the frozen calibration stop ended the case before any T/P arm. Diagnostics (uncounted): r 5,200 survived (1,361 MiB after Full GC); ≈ 5,307/s survived 200 k at 97.4 % heap; uncapped OOM at 155,603 writes (60,208 queued local writes, 1.81 GiB byte[]) | (1) Calibrate r from smooth CL=ONE E arms at ≈ 5,200 / 5,600 / 6,000/s with more sessions × in-flight (e.g. 16 × 256) so the limiter, not the 2,048 slots, sets the rate; drop the 4,700 cap; (2) fix r and dial N (E's edge ≈ 200 k at 5.3 k/s), ≥ 3 E arms per N, N* 10–20 k below the edge, keep T-chk; (3) keep per-second sends within ±10 % of r with no stored permits and record the series; (4) keep ring, client on ms0604, golden.sh full, the fill, patched P build, hstop.py, 5 T + 5 P + 3 E and the decision rule | picked again: R25 |

**Earlier cases and verdicts (the readings this design builds on).**
- [R19](../key_cache_size+counter_cache_size--weigher-gap-on-rate-capped-ring-backlog/key_cache_size+counter_cache_size--weigher-gap-on-rate-capped-ring-backlog.md)
  (2026-11-21, same ring and client): **retry** (`candidate`). E arms only, all at 2 GiB, caches filled then
  invalidated (pre-burst live 120–122 MiB). CL=ALL uncapped: a_E 4,318/s. CL=ONE at r = 4,700 (8 × 256 in flight):
  survive at N = 140 / 170 / 200 k, h_stop 686 / 857 / 927 MiB, max pending ≤ 21 k. Diagnostics: D2 smooth 5,208/s,
  200 k: survive, 41.5 k pending, 1,361 MiB after Full GC (66.5 %); D3 nominal 6,000, achieved 5,307/s because the
  2,048 in-flight slots bound (per-second sends 2.4–9.7 k): survive at 200 k, 56.6 k pending at STOP, h_stop 1,994 MiB
  (97.4 %), 1,932 MiB after Full GC; D1 uncapped (first 5 s at 5.5–7.5 k/s): heap OOM after 155,603 sent, dump 60,208
  `StorageProxy$4` = `Mutation`, `byte[]` 1,811 MiB. Fix H1 (limiter created before the sessions connected stored 1 s
  of permits) and fallback F1 (restoring an old V state with fresh replicas fails; `golden.sh full` rebuilds the state).
  The retry-list row above is its §4.
- [R11](../key_cache_size+counter_cache_size--weigher-gap-on-gated-ring-backlog/key_cache_size+counter_cache_size--weigher-gap-on-gated-ring-backlog.md)
  (2026-11-20, same ring): **retry**. Pre-burst live heap (forced-GC histogram) T 392–396 MiB, P 230, E 122 (T − P
  164 MiB, T − E 272 MiB; entry counts T 1,310,720 key + 468,114 counter, P 569,878 + 242,725); the pending gate did
  not fix the burst; heap OOM in 3 of 5 calibration arms, dumps 48–60 k queued `Mutation`.
- [R8](../key_cache_size+counter_cache_size--weigher-gap-on-write-backlog/key_cache_size+counter_cache_size--weigher-gap-on-write-backlog.md)
  (2026-11-17, pc91 x86): **retry**: gap reproduced (≈ 275 MiB in cache classes for K = 150 MiB), backlog did not form.
- [B7](../bypass/key_cache_size+counter_cache_size-accounting-mismatch/key_cache_size+counter_cache_size--accounting-mismatch.md)
  (2026-11-12): **retry** (`verified-gap · overshoot · deployment`): key cache 2.14×, counter cache 1.80× their caps
  at defaults; a +104 B/entry weigher brings U/C to 0.95 / 0.93. No OOM alone.
- [S2](../convergence/coordinator-local-write-backlog--combo/coordinator-local-write-backlog--combo.md) (**true
  positive**, `verified-OOM · deployment`): the local-write backlog alone OOMs V on this ring at 2 GiB (CL=ONE
  uncapped 3/3).

**Phase-1 constraint and check** (unchanged from R8/R11/R19 §1). `key_cache_size` / `counter_cache_size` "auto" =
`min(max(1, 5 % of heap), 100)` / `min(max(1, 2.5 % of heap), 50)` MiB (`DatabaseDescriptor.java:814–836`) →
`CacheService.initKeyCache` / `initCounterCache` → `CaffeineCache.create(long)` (`cache/CaffeineCache.java:61–70`,
re-read 2026-11-24): `maximumWeight(capacity)`, weigher `key.unsharedHeapSize() + value.unsharedHeapSize()`,
eviction on the writer (`ImmediateExecutor`, `:56`), so K ≤ C while the Caffeine node, `ConcurrentHashMap$Node`,
table slot and sketch slot are not weighed. Phase-1 stage 4 (2026-10-25): `caps` for the counted weight; cache
classes 1.417× `Size`, 1.9–2.0× for the whole live-heap increase.

**JIRA prior art** (read only; nothing posted).
- R19's survey grep (`jira-oom-survey.csv`) and queries stand (weigher gap **new**; local-write backlog
  **known-open** via CASSANDRA-19958, 11460 Won't Fix by design; the combination not found).
- JIRA REST re-run 2026-11-24 ≈ 05:50 EST (`issues.apache.org/jira/rest/api/2/search`): `project = CASSANDRA AND
  text ~ "weigher" AND updated >= 2026-11-01` → 0; `project = CASSANDRA AND (text ~ "key cache" OR text ~ "counter
  cache") AND text ~ "memory" AND updated >= 2026-11-20` → 1 (21899, SslContext release: not about the weigher);
  `project = CASSANDRA AND (text ~ "MutationStage" OR text ~ "LocalMutationRunnable" OR text ~ "self-dropped") AND
  updated >= 2026-11-20` → 1 (19985, cqlsh output: none); `CASSANDRA-19958` still **Needs Committer**, unresolved
  (updated 2026-08-26).
- Verdict unchanged: not known-fixed, so not a positive control.

**What R25 changes against R19 (not a rerun).**
1. **Rate from smooth CL=ONE E arms, no 4,700 cap.** Three candidate rates 6,000 / 5,600 / 5,200 writes/s, tried in
   that order at N = 200,000; r is the highest one whose inflow was smooth and at which E survived (§2.6 A).
2. **16 sessions × 256 in flight (4,096 slots)** instead of 8 × 256, so the pacer, not the slots, sets the rate
   (D3's 2,048 slots bound at 5.3 k/s). 4,096 × ≈ 11.05 KB ≈ 45.3 MB stays below the per-IP transport limit
   (heap/40 = 51.2 MiB = 53.7 MB, `DatabaseDescriptor.java:654–656`), so no default limit changes the inflow shape.
3. **Zero-burst pacer** in `S2Load` in place of Guava's `RateLimiter` (which stores up to 1 s of permits whenever the
   senders fall behind): one shared slot clock `next = max(next, now) + 1/r`; a sender that was blocked does not catch
   up. Per-second sends and in-flight are recorded in every arm and checked against ±10 % of r (§2.5, §2.6).
4. **N placed by ≥ 3 E arms per N level** on a 25 k ladder, then the offset Δ from the measured queued/sent ratio
   (the R19 arithmetic with its measured f ≈ 0.3 instead of R11's 0.65), then T-chk (§2.6 B–D).
5. **Kept:** the ring and client nodes, topology, schema, `golden.sh full` (R19's F1 recipe; `/mydata/r19` no longer
   exists on any node), the V-range cache fill, the forced-GC pre-burst histogram, the B7 weigher patch for P,
   `hstop.py`, the 5 T + 5 P + 3 E counted set and R19 §2.7's decision rule.

**Terms of the B7 row not used (as R8/R11/R19, same reasons):** runtime-shrink residue (needs `setcachecapacity`, a
non-default action), Paxos and prepared-statement weighers (other fills, would confound P), "more distinct keys"
(8-byte keys already give the most entries per MiB).

## 2. Design solution (stage 1; frozen)

### 2.1 Mechanism and direction

Direction: **mixed**: an unprotected accumulation (S2's local-write backlog; no control, no counter) plus a bypass by
accounting mismatch (B7: U > C with K ≤ C in both caches) in the same heap. Technique notes:
[`combo-playbook.md`](../../../combo-playbook.md) (accounting gap as the last layer of a stack at its edge) and
[`bypass-playbook.md`](../../../bypass-playbook.md) (protected path = a weigher that charges the per-entry overhead).

V (`ms0611`) coordinates every CL=ONE blob write of the client and is a replica of every key (RF=3 in a 3-node ring).
For each write it submits its own copy as a `LocalMutationRunnable` on `Stage.MUTATION` (`StorageProxy.java:1569`
→ `performLocally` `:1674`; `concurrent_writes` 32 threads, unbounded queue) and sends copies to R1 and R2. The first
replica ack releases the client slot and the request's transport charge while V's copy still waits. A local copy
that waits past `write_request_timeout` (2 s) is counted as self-dropped and, with
`enforce_native_deadline_for_hints: false` (default), re-submitted as a `HintRunnable` on the same stage
(`StorageProxy.java:2623–2656`, `submitHint` `:2822`), so the backlog is not shed. When the offered rate r exceeds V's
apply rate the backlog grows, faster once GC slows V; each queued 11,000-byte write holds ≈ 28 KiB (S2/R11/R19 dumps).
Before the burst both caches are filled to their default caps (K = 100 + 50 MiB; physical ≈ 304 MiB with the shipped
weigher, ≈ 141 MiB with the patched one). With r and N fixed and the inflow smooth, the backlog's history is the same
in every arm up to GC feedback, and the pre-burst live heap differs by the cache gap: T ≈ 164 MiB more than P,
≈ 272 MiB more than E. N\* is placed so that T's peak demand is above the usable heap and P's below.

### 2.2 Protection map (fixed before readings; V's heap)

| Domain | Allocation, owner, release | Control C (contract) | K | U measured as | Lifetime / multiplicity |
|---|---|---|---|---|---|
| Local-write backlog (S2) | `Mutation` + `PartitionUpdate` + value `byte[]` decoded on `Native-Transport-Requests`, held by `StorageProxy$4` (`LocalMutationRunnable`) or its `HintRunnable` on `MutationStage` until applied | **none** (unprotected; bounded here only by the fixed inflow N at rate r) | none (PendingTasks is a gauge) | pending log (200 ms), S2Poll 1 s; `Mutation` / `StorageProxy$4` in OOM dumps; heap after GC (gc.log) | transient; one per accepted, not yet applied local copy |
| Key cache | `KeyCacheKey` + key `byte[]` + `RowIndexEntry`, Caffeine `PSMW` node, `ConcurrentHashMap$Node`, table, sketch | `key_cache_size` auto = 100 MiB at 2 GiB (`maximumWeight`) | JMX `Cache.KeyCache.Size` | pre-burst forced-GC class histogram; pre-burst live T − P − E; dump counts | standing; table/sketch never shrink |
| Counter cache | `CounterCacheKey` + `byte[]` + `ClockAndCount`, same container | `counter_cache_size` auto = 50 MiB | JMX `Cache.CounterCache.Size` | same | standing |
| Memtables (`b6.t_blob`, `s2c`) | slab regions + partition objects (`heap_buffers`) | `memtable_heap_space` = ¼ heap = 512 MiB; flush at `memtable_cleanup_threshold` | `MemtableOnHeapSize` | S2Poll; dump | standing, recycled at flush |
| Client request bytes | decoded requests in transport | `native_transport_max_request_data_in_flight` = heap/10 = 204.8 MiB; per IP heap/40 = 51.2 MiB (the client's 4,096 slots ≤ 45.3 MB) | transport counter | — | released at the first replica ack (before V's local write runs) |
| Outbound to R1/R2 | `Message` refs (same `Mutation`) in V's outbound queues | internode queue caps (4 MiB per link + 128 MiB per endpoint + 512 MiB global, on-wire) | queue bytes | — | transient |
| Remote hints | expired outbound copies written to V's hints buffers | hints buffers (direct) | `TotalHints` | S2Poll `hints_created` | transient |

Budget: V's Java heap, `-Xms = -Xmx = 2048 MiB`. Direct memory not claimed (heap OOM endpoint).

### 2.3 Configuration and budget audit

| Item | Value | Class |
|---|---|---|
| Nodes (checked read-only 2026-11-24 ≈ 05:45 EST) | Utah m400 (`jason92-326377`), each aarch64, 8 cores, 62 GiB RAM (≈ 58–61 GiB available), OpenJDK 11.0.33, cgroup v2. **V = `ms0611` 10.10.1.4** (`/mydata` 30 GiB free; Linger=no), **R1 = `ms0625` 10.10.1.1** (27 GiB free; Linger=no), **R2 = `ms0617` 10.10.1.5** (35 GiB free; Linger=yes), **client = `ms0604` 10.10.1.3** (30 GiB free; Linger=no). `/mydata/r19` is gone on all four (R19's golden tars and builds deleted). **At design time each of the four holds a phase-1 lock** `/mydata/s4/NODE-LOCK/owner` (`phase1-cassandra o72` / `o57` / `o120` / `o115`, taken 2026-11-23 23:16–23:53 MST), and `ms0617` runs a 2 GiB `CassandraDaemon` of `/mydata/jingsong-cass-s4/o120` (up 3 h 59 min). Folders `/mydata/jingsong-cass-s4`, `s2r2`, `u1r2`, `/mydata/s4/3b-*` and `ms0625`'s `b8`, `oom-smoke` belong to other work: never touched. Controller: the local node `node0.jason92-327358` (UMass; `/mydata` root-owned, 715 GiB free), which reaches the m400s by `ssh <name>`; the m400s cannot ssh to each other (relay `rsync` through the controller) | environment |
| Node access (stage 2) | Before the first command that writes on a node: no foreign `CassandraDaemon` (`ps -eo user,args \| grep [C]assandraDaemon`) and `mkdir /mydata/s4/NODE-LOCK` succeeds on **all four** (then `echo "phase2-cassandra R25 $(date)" > /mydata/s4/NODE-LOCK/owner`); release (`rm -r`) at cleanup. A held lock is waited for, never broken; if the four cannot be locked within 60 min of stage-2 start, stage 2 stops before any arm: verdict `retry` (not run, blocked). **Substitution** (only before `golden.sh`, recorded): `ms0640` (10.10.1.2, same hardware, 17 GiB free) may replace the client or one replica, never V | environment |
| Builds | **orig** = `cp -a ms0611:/mydata/s4/cassandra-base` → `ms0611:/mydata/r25/run-orig` (jar md5 must be `1becab414e5f…`), relayed by `rsync -a` through the controller to `/mydata/r25/run-orig` on `ms0625`, `ms0617`, `ms0604` (`ms0625`'s and `ms0604`'s own bases differ: `beb4d0c1db2a…`, `a9b3ef8b9977…`); jar md5 equal on all four. **patched** = `ms0611:/mydata/r25/run-patched` = `cp -a` of run-orig + R19 `harness/b7-weigher-overhead.diff` (`git apply`), `ant jar` in that copy only; record jar md5 and that `CaffeineCache.class` contains `b7.entry_overhead`. V runs `patched` only in P arms; R1, R2 always `orig` | supporting (patched build = intervention only) |
| Work dirs | `/mydata/r25/` on the four nodes (`sudo mkdir /mydata/r25 && sudo chown jason92:misconfiguration /mydata/r25`); controller `/mydata/r25-evidence/` (same `sudo mkdir` + `chown`) | environment |
| JVM / GC | shipped `jvm-server.options` + `jvm11-server.options` (G1, `-XX:+HeapDumpOnOutOfMemoryError`, OOM → `kill -9`), `MAX_HEAP_SIZE=2G` on all three servers, `HEAP_NEWSIZE=256M` (ignored by G1); `MaxDirectMemorySize` resolved by `cassandra-env.sh` (R19: 15,872 MiB; record); gc.log with `time,uptime` decorations; dumps to the instance's `dumps/` | environment / budget |
| Memory scope | each server JVM in `systemd-run --user --scope -p MemorySwapMax=0` (no memory limit); `loginctl enable-linger` on `ms0611`, `ms0625` for the run, disabled again at the end (`ms0617` stays yes); the client JVM (`-Xmx4g`) runs outside a scope | environment |
| Topology (= R11 = R19 = S2 G1) | DC `c`, rack `r1`, `num_tokens: 1`; `initial_token` V −9223372036854775808, R1 −3074457345618258603, R2 3074457345618258602; seed `10.10.1.4:7000`; `GossipingPropertyFileSnitch`; `b6` `NTS {c:3}`, `t_blob (pk int PRIMARY KEY, b blob)`; `s2c` `NTS {c:1}`, `kv (k blob PRIMARY KEY, v int)`, `ctr (k blob PRIMARY KEY, c counter)` | environment |
| yaml diffs | exactly R19's `ctl.sh gen` (`cluster_name 'r11ring'`, `num_tokens 1`, addresses, seed, snitch, dirs under `/mydata/r25/inst/<role>/`, `auto_bootstrap: false`, `initial_token`); per-instance `yaml.diff` saved | environment |
| Constraints (V6) | all at the shipped default, resolved at 2 GiB: `key_cache_size` 100 MiB, `counter_cache_size` 50 MiB, `memtable_heap_space` 512 MiB, `heap_buffers`, `concurrent_writes` 32, `native_transport_max_request_data_in_flight` 204.8 MiB (per IP 51.2 MiB), `native_transport_max_threads` 128, `write_request_timeout` 2 s, `enforce_native_deadline_for_hints` false, internode queue capacities, hints on, `commitlog_sync` periodic 10 s, key cache save period 4 h (no save in an arm). Only the P arm (patched weigher) and the E arm (caches invalidated by `nodetool`, an operation, not a setting) differ, as intervention and control | default |
| Budget (V7) | heap 2,048 MiB on all three servers (≥ 512 MiB standing rule; 2 GiB ideal; the m400's auto heap would be 15.5 GiB). No container/cgroup memory limit | acceptable (no review needed) |
| Workload (burst) | S2 G1's write: blob 11,000 B (`new Random(1)`), `INSERT INTO b6.t_blob`, **16 driver sessions × 256 in flight** (whitelist V only), CL=ONE, protocol V4; **zero-burst pacer at r** (§2.5) and **total N** (`-Dtotal`); time cap `ceil(N / r) + 60` s | experimental variable (r fixed by §2.6 A; N the dial) |
| Cache fill (V only) | R19's `S2CacheFill` unchanged (key `mix64(i)` kept only if its token > 3074457345618258602; `RANGEOK` check of 1,000 kept / 1,000 rejected keys): `read kv 0..1,500,000` → `counter ctr 0..550,000` → `nodetool flush s2c`; concurrency 256, CL=ONE; from `ms0604`. Validity key ≥ 99.0 MiB, counter ≥ 49.5 MiB (one refill, then `FILLFAIL` void) | workload |
| Golden data state | rebuilt once by R19's `golden.sh full` with `/mydata/r25` paths (1,600,000 kept `kv` keys, flush + compact on V, drain, tars `golden-V/R1/R2.tgz`); check one sstable on V with ≈ 1.61 M partitions (R19: 53.2 MB, ≈ 1,614,344). Every arm restores all three tars | environment (matched data state) |
| Instrumentation | **R11Gate** on V as a pending logger only (`G = 0`, 200 ms, `-Xmx32m`, nice 10); **S2Poll** on each server (1 s, nice 10); client per-second progress incl. sends, in-flight and pacer lateness; pre-burst `jcmd GC.class_histogram` (forced full GC, before the load); heap dump on OOM (shipped option); gc.log. No agent inside the JVMs | disclosed |

### 2.4 Ceiling arithmetic and placement model (V, 2 GiB; before readings)

Terms (MiB), from R11/R19 on this ring: pre-burst live L_T ≈ 394, L_P ≈ 230, L_E ≈ 121; heap usable at OOM
H ≈ 2,030 (OOM arms: max after Full GC 99.0–99.3 %); per queued write s ≈ 28 KiB (26–30). Contract capacities alone:
512 + 100 + 50 + 204.8 = 867 MiB < 2,048 MiB, so no all-pools-full convergence; the OOM needs the uncapped backlog
(S2) and, at N\*, the uncounted cache memory (B7).

**Offset in sent writes.** The cache terms translate into queued writes as (L − L_E) / s: T − E ≈ 9.9 k, P − E ≈ 3.9 k,
their midpoint (190 MiB) ≈ 6.95 k queued writes. Sent writes per queued write at the peak: f = max pending / N. R19
measured f ≈ 0.28 (D3: 56.6 k at 200 k) and 0.39 (D1: 59.9 k at 155 k); R11's 0.65 was at the uncapped burst. With
f ≈ 0.3: T's edge ≈ N_E − 33 k, P's ≈ N_E − 13 k, the midpoint ≈ N_E − 23 k sent writes. So
**Δ = round₁ₖ(6,950 / f)**, clamped to [10 k, 25 k] (the retry row says 10–20 k; the measured f puts the midpoint at
≈ 23 k, so the upper clamp is widened to 25 k), and **N\*₀ = N_E − Δ**; T-chk corrects it once. The arithmetic sets
only the offset; E's edge N_E is measured.

**Rate.** V's CL=ONE apply rate is above 5.2 k/s (R19 D2) and the uncapped burst (5.5–7.5 k/s in its first seconds)
OOMs E at 155 k. Predicted E outcomes at N = 200 k with a smooth inflow: **6,000/s** OOM or survive above 95 % after
GC (edge ≈ 150–200 k), **5,600/s** survive at 80–97 %, **5,200/s** survive at 60–75 % (D2: 66.5 %). The burst lasts
33–38 s at 200 k. A higher r grows the backlog faster and more deterministically (less time for V's apply rate to
wander), so the rule prefers the highest rate whose E arm survives smoothly.

**Why a smooth rate should separate T and P better than R19 D1/D3.** Near the edge R19's outcome was set by the first
seconds' burst shape (D1 OOM at 155 k with bursts to 9.7 k/s; D3 survived 200 k). The pacer removes stored permits and
the 4,096 slots keep the pacer binding, so with r and N fixed the remaining spread is V's apply rate under GC. The
design does not assume that spread is below the T–P window: it compares OOM rates over ≥ 5 + 5 arms and reads h_stop,
where T − P ≈ 164 MiB shows as a shift even when single arms cross the edge by chance.

### 2.5 Harness (stage 2 builds it under `harness/`; copy R19's, change only what is listed)

Node layout: `/mydata/r25/{run-orig, run-patched (V only), inst, golden-<role>.tgz, runs, dumps, h, cls}`; controller
`/mydata/r25-evidence/{runs/<arm>/, batch.log, h, dumps}`; excerpts in `logs/`.

| File | From | Change |
|---|---|---|
| `ctl.sh`, `golden.sh`, `client.sh`, `R11Gate.java`, `S2Poll.java`, `sample.sh`, `S2CacheFill.java`, `vstate.sh`, `gcpeak.sh`, `gcwin.py`, `hprofhist.py`, `dumpparse.sh`, `logback-load.xml`, `b7-weigher-overhead.diff`, `excerpt.sh`, `batch.sh` | R19 [`harness/`](../key_cache_size+counter_cache_size--weigher-gap-on-rate-capped-ring-backlog/harness/) | `/mydata/r19` → `/mydata/r25`, `/mydata/r19-evidence` → `/mydata/r25-evidence`, `pc96` → the controller; `batch.sh`'s start-time limit set to §2.9's (T0 + 6:00) |
| `S2Load.java` | R19 | (1) **zero-burst pacer** replaces `RateLimiter`: one shared object, `synchronized long slot() { long now = nanoTime(); next = max(next, now); long t = next; next += 1e9 / r; return t; }`; a sender thread takes a semaphore slot, then `slot()`, sleeps until `t` (`LockSupport.parkNanos`), then sends; created after all sessions are connected (keeps H1); (2) the progress line every 1 s adds `inflightMax` (max in flight sampled every 10 ms in that second) and `late` (sends in that second whose slot time was > 50 ms in the past when the semaphore was granted: a sign the slots bound); (3) `TOTAL_REACHED` and `FIRST_SEND` unchanged |
| `arm.sh` | R19 | default `SESS=16`; hosts `HOST[...]`, `CLI` and controller paths as above; otherwise unchanged (steps 1–12 of R19 `arm.sh`: clean slate, restore, ring UN = 3 else `RINGFAIL` void, record, samplers + gate logger, fill + validity, E invalidation, pre-burst histogram + 10 s idle, burst, observation dead / drained (pending ≤ 1,000 for 30 s) / 300 s + 180 s once / `UNRESOLVED`, collect, table row) |
| `smooth.py` (new, ≈ 40 lines) | — | from the client's `load.log`: per full second between first send and STOP (or V's death / the first second with `inflightMax ≥ 3,686` = 0.9 × 4,096, whichever is first: **t_sat**): sends, min/max/sd; fraction of seconds within ±10 % of r; achieved rate N / t_STOP; **SMOOTH** = every full second before t_sat ≤ 1.10 r, ≥ 90 % of them ≥ 0.90 r, and (for an arm in which V survives) no saturation before STOP and N / t_STOP ≥ 0.95 r; prints `SMOOTH` / `NOT_SMOOTH (<which>)` and the series |
| `hstop.py`, `table.py` | R19 | `table.py` adds the `smooth.py` columns (SMOOTH, achieved rate, min/max per-second sends, t_sat) |

**Shakedown** (not a reading, ≤ 10 min, after `golden.sh full`): `RATE=6000 FILL_SMALL=1 arm.sh shake T 30000` (16
sessions): ports, ring `UN = 3`, schema, `RANGEOK`, `TOTAL_REACHED` at ≈ 5.0 s, per-second sends within ±10 % of
6,000 from the first second (no stored-permit burst), `smooth.py`, `hstop.py` and `table.py` rows, collection,
cleanup. Fix the harness, never the design.

**Inflow validity (every arm).** V alive but sent < 0.98 N by the time cap → `LOADSHORT` (void). V dies before STOP →
counts as OOM (sent recorded). STOP later than 1.25 × N / r after the first send → counted but flagged `slow inflow`
(V's GC slowing its own coordination is part of the mechanism). `NOT_SMOOTH` arms are counted in the counted set but
flagged and reported per type; in §2.6 A they decide eligibility of a rate.

**Endpoint, per arm** (as R19). **Heap OOM** = V dead and at least one of: `HeapDumper` or `ReportJavaOutOfMemory`
safepoint in gc.log, `java.lang.OutOfMemoryError` in system.log/launch.log (skip `CompileCommand` lines), a dump
written by `HeapDumpOnOutOfMemoryError`. **Survive** = V alive and drained. **Unresolved** = alive, not drained at the
end of the extended window. V dead without OOM evidence = **void** (not counted). GC service loss (protocol default)
is recorded, not the endpoint.

### 2.6 Calibration (all E unless named; 2 GiB on the three servers; none counted)

**A. Rate (2–3 arms).** E at N = 200,000, CL=ONE, 16 × 256, in this order, stopping at the first eligible rate:
`RATE=6000 arm.sh rcal6000 E 200000` → `RATE=5600 … rcal5600 …` → `RATE=5200 … rcal5200 …`. A rate is **eligible**
when its arm is `SMOOTH` and V survived (drained). **r** = the first eligible rate.
- If no rate is eligible because every smooth arm died (OOM), **r = 5,200** when `rcal5200` was smooth, and the ladder
  starts below 200 k (B).
- If `rcal5200` is not smooth (the pacer cannot hold even the lowest rate with 4,096 slots), or 5,200 survives smooth
  but neither higher rate is smooth and the 5,200 arm's max after Full GC is < 50 % (V too far from its edge to place
  N in range), stop: verdict `retry` (inflow).
Stage 2 records the per-second series of each rate arm and f (max pending / N).

**B. N ladder (≤ 3 levels × 3 E arms, step 25 k).** Ladder values …, 125 k, 150 k, 175 k, 200 k, 225 k, 250 k, 275 k.
First level L1 = 200 k when r's rate arm survived (it is the first of L1's 3 arms; run 2 more), L1 = 175 k when r was
set by the "every smooth arm died" branch (3 arms). Level result: **S** = 3/3 survived; **M** = 1 or 2 of 3 OOM (or
`UNRESOLVED`); **O** = 3/3 OOM / `UNRESOLVED`. Next level: after S go up 25 k, after O go down 25 k, after M stop.
**N_E** = the lowest M level if any; otherwise the midpoint of the highest S level and the lowest O level once both
exist. If three levels give only S (or only O), stop: verdict `retry` (edge outside the ladder at r). A void arm is
re-run once in the same slot.

**C. Offset.** f = median of (max 200 ms pending / N) over the surviving E arms at the level nearest N_E (S level
below, else M level survivors); **Δ = round₁ₖ(6,950 / f)** clamped to [10 k, 25 k]; **N\*₀ = N_E − Δ** (§2.4).

**D. T-chk (1 arm, T at (r, N\*₀), not counted).** T survives with max heap after any GC < 1,950 MiB (95.2 %) →
**N\* = N\*₀ + 8,000** (but at most N_E − 5,000); T dies before STOP → **N\* = N\*₀ − 8,000**; otherwise (T dies after
STOP, or survives at ≥ 95.2 %) **N\* = N\*₀**. One adjustment only.

**E. Amendment.** Stage 2 writes r, the rate-arm results, the ladder table, N_E, f, Δ and N\* into §3 as a dated
amendment **"r and N\* fixed"** before the first counted arm.

Predictions: rcal6000 survives smooth at 95–99 % after GC or OOMs (then rcal5600 survives smooth at 80–97 %); r =
6,000 or 5,600; N_E 190–240 k; f 0.25–0.35; Δ 20–25 k; N\* 165–215 k.

### 2.7 Counted arms, predictions, controls, intervention and decision rule

All at (r, N\*), 2 GiB on all three servers, clean starts from the golden state, interleaved in this order:
`T1 P1 E1 T2 P2 T3 P3 E2 T4 P4 E3 T5 P5` (13 arms).

| Arm | Role | Prediction (before readings) |
|---|---|---|
| T (orig, caches at caps) ×5 | endpoint (V1) | heap OOM **4–5 of 5**, OOM mark within 120 s of STOP (some before); pre-burst live 385–405 MiB; h_stop ≥ 1,980 MiB or censored; dump: ≈ 50–60 k `Mutation` (`StorageProxy$4` + local `HintRunnable` wrappers), `PSMW` ≈ 1.78 M, `KeyCacheKey` 1,310,720, `CounterCacheKey` 468,114 |
| P (patched weigher, caches at caps by K) ×5 | intervention (V4): removes only the uncounted ≈ 164 MiB at the same K, r, N\* | survive **4–5 of 5**; pre-burst live 220–240 MiB (T − P 150–175); h_stop ≈ 1,780–1,900 MiB; `PSMW` ≈ 812 k; achieved rate within 5 % of T's |
| E (orig, caches filled then invalidated) ×3 | matched control (V2): the holder alone at the same r, N\* | survive **3 of 3**; pre-burst live 115–130 MiB; h_stop ≈ 1,650–1,800 MiB |

Matched across arms: build and yaml (P differs only in the weigher of `CaffeineCache.create(long)`, whose only callers
are the key and counter caches), heaps, topology, nodes, golden data, fill (E differs only in the two invalidations),
r, N\*, 16 × 256, client and its node. Recorded per arm for matching: SMOOTH and the per-second send series, time to
STOP, achieved rate, sent/ok/err, max pending, self-drops, hints, memtable on-heap, R1/R2 max pending and max after
GC.

**Decision rule (frozen, R19 §2.7; t, p, e = OOM counts of T, P, E at N\*).** `UNRESOLVED` counts as *not OOM* for T
and as *not survived* for P and E; void arms are re-run in the same slot if the clock allows, else the n is reported.

| Outcome (n_T = n_P = 5, n_E = 3) | Verdict / action |
|---|---|
| t ≥ 4, p ≤ 1, e = 0, and median h_stop(T) − median h_stop(P) ≥ 100 MiB (OOM-censored T values count as 2,048) | proposed `verified-OOM · deployment`, mixed (S2 unprotected accumulation + B7 accounting gap) → **true positive** (Fisher one-sided p reported: 4/5 vs 1/5 0.10, 4/5 vs 0/5 and 5/5 vs 1/5 0.024, 5/5 vs 0/5 0.004) |
| t − p = 2 or 3 but not the row above, and e = 0 | **extend**: more T/P pairs at the same N\* while the clock allows (§2.9), to at most 8 + 8; then true positive only if t/n_T ≥ 0.75, p/n_P ≤ 0.25, e = 0 and the h_stop shift ≥ 100 MiB; otherwise **retry** (state the rates) |
| p ≥ 3 | **retry**: the gap does not decide the OOM at N\*; record the h_stop shift (if ≈ 164 MiB with equal rates, propose to the owner that the B7 line be closed as "gap real, not decisive at 2 GiB") |
| t ≤ 2 | **retry**: N\* below T's edge (placement); report h_stop of the three types |
| e ≥ 1 | **retry**: the matched control does not hold at N\* (V2 unmet) |
| counted set incomplete when the clock stops it | **retry** (incomplete), with what ran |

More than 3 of the 13 counted arms `NOT_SMOOTH` (any type) → the verdict of the table is still reported, but a true
positive needs, in addition, the same outcome counts when only `SMOOTH` arms are counted (t ≥ 4 of the smooth T, etc.,
with n reported); otherwise **retry** (inflow).

`false positive` is not a reachable outcome of this design: the endpoint is already reached at defaults on this ring
(S2, R11, R19 D1); the question is only whether the cache gap decides it.

**Continuous reading (reported in every outcome).** Per type: h_stop (median, range), pre-burst live, max heap after
any GC; T − P and T − E shifts against the predicted 164 and 272 MiB; h_stop against V's pending at STOP (one common
slope, separate intercepts per type: the T − P intercept should be ≈ 164 MiB). Time to OOM after STOP (not a decider).

**Budget search.** 2 GiB is the planned budget. Upward probe (one T and one P, all three heaps 4 GiB, the same r,
N = 2.5 × N\*) only if ≥ 35 min remain before the last-start limit after the counted arms and any extension; n = 1
each, a boundary probe, not a verified condition. Otherwise the case states "largest failing budget searched = 2 GiB;
S2 G1 at 4 GiB alone 0/6 at 97–98 % live".

### 2.8 Instruments (U independent of K)

- **Backlog U:** pending log (200 ms), S2Poll `mut_pending` / `mut_done` / `self_dropped` / `hints_inprog` /
  `hints_created` (1 s, no forced GC); `Mutation`, `StorageProxy$4`, `WriteResponseHandler`, `byte[]` in OOM dumps
  (`hprofhist.py` on the controller).
- **Cache U:** class counts × shallow sizes from the pre-burst forced-GC histogram (`PSMW`, `ConcurrentHashMap$Node`,
  `KeyCacheKey`, `CounterCacheKey`, `ClockAndCount`, `RowIndexEntry`, key `byte[]`); pre-burst live T − P, T − E. K
  from JMX `Size` / `nodetool info`.
- **Heap:** gc.log (`gcpeak.sh`, `gcwin.py`, `hstop.py`); MemoryMXBean used every 1 s (S2Poll).
- **Inflow:** client progress every 1 s (sent, ok, err, in flight, `inflightMax`, `late`, rate), `TOTAL_REACHED`,
  `FINAL`; `smooth.py` per arm.
- **Initiating failure (V5):** gc.log safepoint marks; first `OutOfMemoryError` with its thread from system.log or
  launch.log; the dump histogram of every counted T OOM and of any P/E OOM (parsed on the controller during later
  arms).
- **Overhead:** gate logger and S2Poll at nice 10 on V, the same in every arm; forced GC only before the burst.

### 2.9 Time plan and stopping budget

T0 = the moment all four node locks are held (§2.3). Arm length on this ring (R19): ≈ 8–10 min, worst ≈ 15.

| From T0 | Work |
|---|---|
| 0:00 – 0:40 | freeze hash check; nodes (`ps`, `free`, `df`, Linger); `/mydata/r25` on the four nodes and the controller; builds (copy, relay, md5, `ant jar` in run-patched); harness copy + changes + compile on the four nodes; `golden.sh full` (≈ 8 min); shakedown |
| 0:40 – 1:10 | A: rate arms (2–3) → r |
| 1:10 – 2:40 | B: ladder (≤ 8 more arms) → N_E; C: Δ |
| 2:40 – 2:55 | D: T-chk → amendment "r and N\* fixed" |
| 2:55 – 5:05 | 13 counted arms (≈ 10 min each) |
| 5:05 – 6:00 | extension pairs or the 4 GiB probe; **no arm starts after T0 + 6:00** |
| ≤ T0 + 6:15 | every process the run started stopped (three `CassandraDaemon`, gate logger, samplers, client); `loginctl disable-linger` on `ms0611`, `ms0625`; locks released; dumps parsed or left on the node and named |
| ≤ T0 + 7:00 | §3, §4 and the write-backs (playbook stage 2 step 5) |

**Hard limits.** At most 35 arm executions (shakedown included). No arm starts after T0 + 6:00; whatever runs at
T0 + 6:15 is stopped. **The first counted arm starts by T0 + 3:15**: the third ladder level is skipped if it could not
start by T0 + 2:30 (then N_E from the levels run, or `retry` if no edge), and T-chk is skipped if it could not start by
T0 + 3:00 (then N\* = N\*₀). Counted arms are never reduced below 5 T, 5 P, 3 E; an incomplete set is `retry`. No
escalation after an OOM beyond the planned arms.

**Drop order when behind** (first dropped first): the 4 GiB probe → extension pairs → T-chk → third ladder level.

**Resources and disk.** Per server one 2 GiB JVM (+ ≈ 1–2 GiB off-heap); the client (4 GiB heap) alone on `ms0604`.
Disk on V: builds ≈ 1 GB, golden ≈ 46 MB, `b6` data and commit log ≤ 3.5 GB per arm (wiped by the next restore), dumps
≈ 2.2 GB each: keep the first counted T dump and the first P or E OOM dump on V, delete the others after their
histogram is on the controller (≤ 10 GB of 30 GiB free). R1/R2 ≤ 3.5 GB per arm, wiped by the next restore.

### 2.10 Limits known before the run

- A smooth CL=ONE burst of fixed size at 5.2–6 k writes/s is an ordinary client workload; the overload is that r
  exceeds V's apply rate. The researcher may rule on whether such a burst is an accepted workload (as for S2).
- The offset uses R19's measured f near the edge; T-chk corrects it once. A misplaced N\* shows as t ≤ 2 or p ≥ 3 and
  ends in `retry`, not in a false claim.
- With 5 + 5 arms only large rate differences are significant (best case p = 0.004); the h_stop shift is the second,
  continuous line of evidence.
- The intervention charges 104 B/entry, an upper bound on this layout (B7: U/C 0.93–0.95), so it removes slightly
  more than the gap; K is the same in T and P.
- The four m400s are shared with phase-1 work (locks and a running instance at design time); stage 2 uses them only
  under the four locks and never touches other folders or processes.

`sha256 of §1–§2 at freeze: c914f2f854804b2a9b0e54e1a344750791115adc3cf1903d7a88dcc042c5afab` (UTF-8 bytes from the line `## 1. Candidate` through the line before this one, each line ending in `\n`; frozen 2026-11-24 06:40 EST) · amendments after the freeze: none.

## 3. Runs (stage 2)

pending

## 4. Conclusion (stage 2)

pending
