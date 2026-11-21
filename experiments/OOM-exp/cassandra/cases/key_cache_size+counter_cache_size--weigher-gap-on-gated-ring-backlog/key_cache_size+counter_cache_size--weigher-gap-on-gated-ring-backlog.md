# R11 (retry of R8 / B7) — key_cache_size + counter_cache_size: weigher gap on a gated RF=3 ring backlog  <!-- file: cassandra/cases/key_cache_size+counter_cache_size--weigher-gap-on-gated-ring-backlog/key_cache_size+counter_cache_size--weigher-gap-on-gated-ring-backlog.md -->

| Field | Value |
|---|---|
| Case ID | `R11` (R = a new attempt at an earlier case: R8, itself a retry of B7) |
| From | retry of `R8` ([phase-2 retry list](../../phase2-retry-list.md), row R8, status `picked again: R11`) |
| Phase-1 case file | [`key_cache_size-create-size--autonomous`](../../../../capacity-enforcement-exp/cassandra/stage3-ai-deep-read/cases/key_cache_size-create-size--autonomous.md), [`counter_cache_size-putcachedcounter-capacity--autonomous`](../../../../capacity-enforcement-exp/cassandra/stage3-ai-deep-read/cases/counter_cache_size-putcachedcounter-capacity--autonomous.md) (phase-1 row OC-2) |
| System / pinned source | Cassandra 5.0.9 (`systems/cassandra/source/`; on the nodes `ms0611:/mydata/s4/cassandra-base`, `build.xml` base.version 5.0.9, git `02a233a`, jar md5 `1becab41…`, `conf/cassandra.yaml` md5 `714ee9bf…` = the yaml of B7, S2, R8) |
| Stage 1 (design) | phase-2 OOM agent, stage 1 (Claude Opus 5.5, subagent), 2026-11-20 10:30–11:40 EST |
| Stage 2 (verify) | phase-2 OOM agent, stage 2 (Claude Opus 5.5, fresh subagent), 2026-11-20 10:40–12:25 EST; V `ms0611`, R1 `ms0625`, R2 + client `ms0617`, controller `pc96` |
| Verdict | **retry** (`candidate`: holder and cache gap both reproduced, heap OOM at defaults in 3/5 calibration arms, but the gated T/P bracket found no G\* within 5 calibration arms — T survived at 56 k and 58 k while P died at 56 k; no counted arm) |

## Summary

- **Conclusion (stage 2, 2026-11-20): retry.** On the aarch64 RF=3 ring (all heaps 2 GiB, shipped defaults) V's
  local-write backlog formed (56–66 k queued writes) and the B7 cache gap reproduced (pre-burst live T 394 MiB, P 230,
  E 122: 164 MiB uncounted). Heap OOM happened in 3 of 5 calibration arms (E uncapped, P at G = 56 k, T at G = 60 k), but
  not in the order the design needed: T survived at G = 56 k and 58 k while P died at 56 k. The 5-arm calibration limit
  stopped the run with no G\*, so no counted T/P/E rounds ran.
- **Why:** the gate on V's `MutationStage` pending did not fix the backlog's history. Pending is a saw-tooth (it drops
  by 14–33 k at each burst of self-dropped local writes), so reaching G took 17–21 s in the surviving T arms
  (≤ 101 k writes, drained ≈ 10 s after STOP) but 69 s or more in the OOM arms (≥ 142 k writes). The length of the
  overload decided the outcome, and its spread is much wider than the 164 MiB (≈ 6 k writes) cache window.
- **Root cause (claimed, still untested as a decider):** no control charges the coordinator's queued local writes
  (S2), and the key/counter cache weighers count only key + value bytes, not the ≈ 90 B per entry of the Caffeine
  container (B7). Both are confirmed again here; that the B7 excess decides an OOM is not.

## 1. Candidate

**Retry row (quoted from [`phase2-retry-list.md`](../../phase2-retry-list.md), 2026-11-20):**

> | [R8](cases/key_cache_size+counter_cache_size--weigher-gap-on-write-backlog/key_cache_size+counter_cache_size--weigher-gap-on-write-backlog.md) (retry of B7) | 2026-11-18 | On pc91 (x86) the B7 weigher gap reproduced (≈ 275 MiB in cache classes vs 150 MiB counted at a 2 GiB heap), but the S2 write backlog it was to stack on did not form: MutationStage pending peaked at 9,724 < the frozen 10,000 threshold, so no counted arm ran | Run where the backlog forms (S2 run 2's aarch64 RF=3 ring, or a slower-apply pair); calibrate the backlog alone first (caches invalidated) with mut_pending and hints_created | picked again: R11 (2026-11-20) |

**Earlier cases and verdicts.**
- [R8](../key_cache_size+counter_cache_size--weigher-gap-on-write-backlog/key_cache_size+counter_cache_size--weigher-gap-on-write-backlog.md)
  (2026-11-17, pc91, x86): **retry** (`candidate`). Design: S2's coordinator local-write backlog as the growing holder,
  sized by a fixed burst of N writes on a single-host V (2 GiB) + R (8 GiB, tmpfs) pair, with both caches filled
  (T), the B7 weigher +104 B/entry (P, intervention) and invalidated caches (E, control) at one N\*. Stage 2: fill
  reached the caps exactly as B7 (key 1,310,720 entries, counter 468,114; ≈ 275 MiB in the cache classes for K = 150
  MiB, pre-burst live 397–401 MiB), but V applied ≈ 13 k writes/s, max `mut_pending` 9,724 (8 × 256) and 2,684
  (16 × 256) < 10,000, late local writes turned into hint runnables (6,392 / 9,918), max live after Full GC 61 %.
  Stopped by its §2.6 step 1 after 2 calibration arms. Its own "what to change": (1) reproduce the holder where it
  forms (S2 run 2's aarch64 ring); (2) calibrate the holder alone (E) first, then place T/P/E; (3) on x86 only with
  a slowed V; (4) keep the cache fill.
- [B7](../bypass/key_cache_size+counter_cache_size-accounting-mismatch/key_cache_size+counter_cache_size--accounting-mismatch.md)
  (2026-11-12): **retry** (`verified-gap · overshoot · deployment`). At defaults and 8-byte keys the key cache holds
  2.14× (U 214.0 MiB for C = K = 100 MiB) and the counter cache 1.80× (U 90.1 MiB for 50 MiB), 3/3 at 512 MiB, 2 GiB
  and 7,965 MiB heaps; a weigher that charges +104 B/entry brings U/C to 0.95 / 0.93 (3/3; 569,878 / 242,725
  entries). Invalidating keeps the table and sketch (≈ 24 MiB key cache). No OOM alone (the caps are heap-derived).
- [S2](../convergence/coordinator-local-write-backlog--combo/coordinator-local-write-backlog--combo.md) (true positive,
  `verified-OOM · deployment`). Run 2 ([history](../convergence/coordinator-local-write-backlog--combo/history.md#run-2),
  2026-11-16, Utah m400 aarch64, `ms0640` V, `ms0604` R1, `ms0611` R2, client `ms0617`): condition **G1** — RF=3 single
  DC `{c:3}`, **all three heaps 2 GiB**, blob 11,000 B, 8 × 256 in flight to V only, CL=ONE, uncapped, 90 s, shipped
  defaults — heap OOM **3/3** (62, 460, 176 s after load start; two after ≥ 90 % STW windows of 466 / 161 s), max V
  `MutationStage` pending 62.8–64.0 k, dumps 63,349–63,520 `Mutation` = `StorageProxy$4`; replicas ≤ 25 % live,
  pending ≤ 77; V self-dropped 33–64 k local writes per arm and re-queued them on the same stage; CL=ALL 0/3 (2.4×
  writes), 1,500 writes/s cap 0/3 (≈ 0.5 × V's apply rate); caches empty in all arms. At 4 GiB (all three nodes):
  OOM 0/6, 97–98 % live, ≈ 128–136 k pending at the peak, the backlog drains once the client stops.

**Phase-1 constraint and check (unchanged from R8 §1).** `key_cache_size` / `counter_cache_size` "auto" =
`min(max(1, 5 % of heap), 100)` / `min(max(1, 2.5 % of heap), 50)` MiB (`DatabaseDescriptor.java:814–836`), →
`CacheService.initKeyCache` / `initCounterCache` (`service/CacheService.java:119–128`, `:172–179`) →
`CaffeineCache.create(capacity)` (`cache/CaffeineCache.java:61–70`): `maximumWeight(capacity)` with weigher
`key.unsharedHeapSize() + value.unsharedHeapSize()`, eviction on the writer (`ImmediateExecutor`), so K ≤ C always
while the Caffeine node, `ConcurrentHashMap$Node`, table slot and sketch slot (≈ 90–100 B per entry) are not weighed.
Phase-1 stage 4 (2026-10-25): confirmed `caps` for the counted weight (`Size` 64 B under the cap); "the heap of the
key cache's classes" factor 1.417 over `Size`, 1.9–2.0 for the whole live-heap increase; runtime shrink leaves +17.3 MB.

**JIRA prior art** (read only; nothing posted).
- Survey [`jira-oom-survey.csv`](../../../../capacity-enforcement-exp/cassandra/stage5-oom-clue-find/jira-oom-survey.csv),
  filter `key cache|counter cache|weigh|caffeine|MutationStage|LocalMutationRunnable|19958`: CASSANDRA-4315 / 4860 (Fixed;
  built the payload weighers), 5706 / 5986 / 6260 / 7171 / 9120 (saved-cache load at startup; other path), 6149
  (FileCacheService under-count, Fixed), 9754 (IndexInfo, unresolved; other holder), 11460 (Won't Fix: MutationStage
  SEP queue holding 60+ GB when writes exceed capacity — the S2 holder, called by design), 13213 (Open: pending
  mutations OOM), 12689 (Fixed, MV deadlock). R8's survey verdicts stand: 6709 (Later) acknowledges ≈ 100 B + key per
  entry as density only; 9738 Won't Fix.
- JIRA REST search, 2026-11-20 ≈ 10:33 EST (`issues.apache.org/jira/rest/api/2/search`, project CASSANDRA):
  `text ~ "weigher" AND created >= 2025-06-01` → 0; `text ~ "key cache" AND text ~ "memory" AND updated >= 2026-06-01`
  → 33 (first 20 read: none about cache weight vs heap; 21117 *Review In Progress* is `nodetool info`'s network-cache
  size report, not the key cache weigher; 9929 off-heap tiny entries, other provider); `(text ~ "MutationStage" OR
  text ~ "LocalMutationRunnable") AND updated >= 2026-06-01` → 11 (19958 *Local Hints are stepping on local
  mutations* still **Needs Committer**, updated 2026-08-26; the rest other causes).
- Verdict: weigher gap **new** (not a regression, not documented as a memory bound); local-write backlog
  **known-open** (19958; 11460 by design); the combination (the cache under-count deciding a backlog OOM) not found.
  Not a known-fixed bug, so not a positive control.

**What R11 changes against R8 (not a rerun).**
1. **Where:** the backlog is formed on the exact platform and topology that verified it: S2 run 2's G1 ring
   (aarch64 m400, RF=3 single DC, all heaps 2 GiB, client whitelisted to V), not a single x86 host.
2. **Dial:** the holder's size is set by **V's own `MutationStage` pending** — a gate process on V reads it every 200
   ms and tells the client to stop sending at G — instead of a fixed burst N. On the m400 the share of accepted writes
   that V applies during the burst varies with GC (S2: OOM 62–460 s after start), so a fixed N would carry that spread
   into the backlog; the gate fixes the backlog itself (±overshoot, measured) and leaves only the heap terms to differ
   between arms.
3. **Calibration order (the retry row):** the first reading is the holder alone with caches filled then invalidated
   (E, uncapped), reading `mut_pending`, self-drops, hints in progress and hints written; only then T and P are placed.
4. **Fill confined to V:** the cache keyspace is RF=1 and its keys are chosen client-side to fall in V's token range,
   so only V's caches fill, at the same per-entry layout as B7/R8, without loading the replicas.
5. **Observation:** at least 480 s after the stop (S2 G1 r2 died ≈ 370 s after its client stopped), not 180 s.

**Terms of the B7 row not used (as in R8, with reason).** Runtime-shrink residue (+17.3 MB) needs
`nodetool setcachecapacity` (not the shipped configuration, V6); the Paxos weigher (L2) needs an LWT fill the B7 patch
does not cover (would confound P); prepared-statement / streaming weighers (L6) have small caps and no fill here;
"more distinct keys" is capped (8-byte keys already give the most entries per MiB).

## 2. Design solution (stage 1; frozen)

### 2.1 Mechanism and direction

Direction: **mixed** — an unprotected accumulation (S2's local-write backlog; C none, K none) plus a bypass by
accounting mismatch (B7: U > C with K ≤ C in both caches) in the same heap. Technique notes:
[`combo-playbook.md`](../../../combo-playbook.md) (the accounting gap as the last layer on a stack placed at its edge)
and [`bypass-playbook.md`](../../../bypass-playbook.md) (protected path = a weigher that charges the per-entry overhead).

V (`ms0611`) coordinates every CL=ONE blob write from one client and is a replica of every key (RF=3 in a 3-node
ring). For each write it submits its own copy as a `LocalMutationRunnable` on `Stage.MUTATION`
(`StorageProxy.java:1569` → `performLocally` `:1674–1690`; `concurrent_writes` 32 threads, unbounded queue) and sends
copies to R1 and R2 through bounded internode queues. V is CPU-bound (S2 run 2: 93 % busy vs ≈ 50 % on the
replicas), the replicas apply what reaches them at once and ack, and at CL=ONE the first ack releases the client
slot, the request and its `native_transport_max_request_data_in_flight` charge while V's copy waits. A local copy that
waits past `write_request_timeout` (2 s) is counted as a self-dropped `MUTATION_REQ` and re-submitted as a
`HintRunnable` that applies the same mutation on the same stage (`StorageProxy.java:2623–2654`, `submitHint`
`:2822–2828`), so the backlog is not shed. Each queued 11,000-byte write holds ≈ 28–30 KiB of heap (S2: 63.4 k
`Mutation` ≈ 1.74–1.86 GiB). Before the burst both of V's caches are filled to their default caps through CQL
(K = 100 + 50 MiB; physical ≈ 214 + 90 MiB with the shipped weigher, B7). The client stops at a fixed V backlog G;
at that G the heap peak = pre-burst live + memtable + G × s. The shipped weigher's uncounted ≈ 163 MiB (≈ 6 k queued
writes, 8 % of the heap) decides whether the peak passes the heap: T (shipped) is placed just past its edge, P (same
K, +104 B/entry charged, so ≈ 163 MiB less held) and E (caches invalidated) just inside theirs.

### 2.2 Protection map (fixed before readings; V's heap)

| Domain | Allocation, owner, release | Control C (contract) | K | U measured as | Lifetime / multiplicity |
|---|---|---|---|---|---|
| Local-write backlog (S2) | `Mutation` + `PartitionUpdate` + value `byte[]` decoded on `Native-Transport-Requests`, held by `StorageProxy$4` (`LocalMutationRunnable`) or its `HintRunnable` on `MutationStage` until a stage thread applies it | **none** (unprotected; here bounded by the gate: ≈ G + overshoot) | none (`MutationStage` PendingTasks is a gauge) | gate log (pending every 200 ms), S2Poll 1 s; `Mutation` / `StorageProxy$4` in OOM dumps; heap after GC (gc.log) | transient; one per accepted, not yet applied local copy |
| Key cache | `KeyCacheKey` + key `byte[]` + `RowIndexEntry`, Caffeine `PSMW` node, `ConcurrentHashMap$Node`, table, frequency sketch | `key_cache_size` auto = 100 MiB at 2 GiB (`maximumWeight`) | JMX `Cache.KeyCache.Size` | pre-burst forced-GC class histogram (counts × shallow sizes, B7 layout); live-heap difference T − P − E; dump counts | standing; table/sketch never shrink |
| Counter cache | `CounterCacheKey` + `byte[]` + `ClockAndCount`, same container | `counter_cache_size` auto = 50 MiB | JMX `Cache.CounterCache.Size` | same | standing |
| Memtables (`b6.t_blob`, `s2c`) | slab regions + partition objects (`heap_buffers`) | `memtable_heap_space` = ¼ heap = 512 MiB; flush at `memtable_cleanup_threshold` = 1/3 | `MemtableOnHeapSize` (JMX) | S2Poll; dump (S2: ≤ 170 MiB at the OOM) | standing, recycled at flush |
| Client request bytes | decoded requests in transport | `native_transport_max_request_data_in_flight` = heap/10 = 204.8 MiB (per IP heap/40) | transport counter | — | released at response flush (before V's local write runs) |
| Outbound to R1/R2 | `Message` refs (same `Mutation`) in V's outbound queues; serialized on send | internode queue caps (4 MiB per link + 128 MiB per endpoint + 512 MiB global, on-wire) | queue bytes | — (S2: expired ones dropped and hinted) | transient |
| Remote hints | expired outbound copies written to V's hints buffers | `max_hints_size_per_host` etc. (direct/disk) | `TotalHints` | S2Poll `hints_created` | transient |

Budget: V's Java heap, `-Xms = -Xmx = 2048 MiB`. Direct memory not claimed (heap OOM endpoint).

### 2.3 Configuration and budget audit

| Item | Value | Class |
|---|---|---|
| Nodes (checked read-only 2026-11-20 08:33 MST = 10:33 EST) | Utah m400 (`jason92-326377`), each aarch64 8 cores, 62 GiB RAM (≈ 61 GiB available), 8 GiB swap (0 used), SSD `sda` (ROTA 0), Ubuntu 22.04, kernel 5.15, cgroup v2, OpenJDK 11.0.33, Ant; all idle, no Java process. **V = `ms0611` 10.10.1.4** (`/mydata` 35 GiB free), **R1 = `ms0625` 10.10.1.1** (29 GiB free), **R2 = `ms0617` 10.10.1.5** (36 GiB free; also runs the client). Controller: the local node (`pc96`), over `ssh` (as S2 run 2); dumps parsed there (572 GiB free, 32 threads) | environment |
| Builds | `ms0611` and `ms0617` have the same `/mydata/s4/cassandra-base` (git `02a233a`, jar md5 `1becab41…`); `ms0625`'s jar differs (md5 `beb4d0c1…`, no git metadata), so it is **not used**. **orig** = `ms0611:/mydata/s4/cassandra-base` → `/mydata/r11/run-orig` on all three nodes (`cp -a` on ms0611, `rsync -a` to the other two; check jar md5 equal). **patched** = `ms0611:/mydata/r11/run-patched` = `cp -a` of run-orig + `harness/b7-weigher-overhead.diff` (`git apply` or `patch -p1`, then `ant jar` in that copy only; record jar md5 and that it contains `b7.entry_overhead`). V runs `patched` only in P arms; R1, R2 always `orig` | supporting (patched build = intervention only) |
| JVM / GC | shipped `jvm-server.options` + `jvm11-server.options` (G1, `-XX:+HeapDumpOnOutOfMemoryError`, `OnOutOfMemoryError=kill -9 %p`), `MAX_HEAP_SIZE=2G` on all three (S2 G1), `HEAP_NEWSIZE=256M` (ignored by G1, as S2); `MaxDirectMemorySize` resolved by `cassandra-env.sh` (S2 run 2: 15,872 MiB; record); GC log in the instance log dir; heap dumps to `/mydata/r11/inst/<role>/dumps` | environment / budget |
| Memory scope | each server JVM in `systemd-run --user --scope -p MemorySwapMax=0` (no memory limit; `memory.max` = max), `loginctl enable-linger jason92` on the three nodes for the run (ms0611, ms0625 have Linger=no now: disable again at the end); `memory.swap.current` 0 in every arm | environment |
| Topology (= S2 G1) | one DC `c`, rack `r1`, `num_tokens: 1`; `initial_token` V −9223372036854775808, R1 −3074457345618258603, R2 3074457345618258602; seed `10.10.1.4:7000`; `GossipingPropertyFileSnitch`; keyspace `b6` `NTS {c:3}`, table `t_blob (pk int PRIMARY KEY, b blob)`; keyspace `s2c` `NTS {c:1}`, tables `kv (k blob PRIMARY KEY, v int)`, `ctr (k blob PRIMARY KEY, c counter)` | environment |
| yaml diffs (per instance `yaml.diff`) | exactly S2 run-2 `ctl.sh gen`: `cluster_name: 'r11ring'`, `num_tokens: 1`, listen/rpc address, seeds, snitch, data/commitlog/hints/saved_caches dirs under `/mydata/r11/inst/<role>/`, `auto_bootstrap: false`, `initial_token` | environment |
| Constraints (V6) | all at the shipped default, resolved at 2 GiB: `key_cache_size` 100 MiB, `counter_cache_size` 50 MiB, `memtable_heap_space` 512 MiB, `memtable_allocation_type: heap_buffers`, `concurrent_writes` 32, `native_transport_max_request_data_in_flight` 204.8 MiB, `native_transport_max_threads` 128, `write_request_timeout` 2 s, internode queue capacities, hints on, `commitlog_sync: periodic` 10 s, key cache save period 4 h (no save in an arm) | default |
| Budget (V7) | heap 2,048 MiB (≥ 512 MiB, the standing rule; 2 GiB ideal); the m400's auto heap would be 15.5 GiB. No container/cgroup memory limit | acceptable (no review needed) |
| Workload (burst) | S2 G1's: blob 11,000 B random-filled once (`new Random(1)`), `INSERT INTO b6.t_blob`, 8 driver sessions × 256 in flight, whitelist V only, CL=ONE, protocol V4, **no rate cap**; **stop when V's gate signals pending ≥ G** (the dial; G = none in uncapped calibration arms), time cap 120 s | experimental variable |
| Cache fill (V only) | R8's `S2CacheFill` (8-byte SplitMix64 keys) with one change: candidate index i → key `mix64(i)`; **kept only if its Murmur3 token > 3074457345618258602** (V's primary range; ≈ 1/3 kept), the j-th kept key is fill key j. Per arm: `read kv 0..1,500,000` (populates the key cache) → `counter ctr 0..550,000` (V is the only replica, so the counter leader; populates the counter cache) → `nodetool flush s2c`; concurrency 256, CL=ONE. The 1,600,000-key `kv` sstable comes from the golden state (§2.5) | workload |
| Golden data state | built once in stage 2: clean ring, schema, `insert kv 0..1,600,000` (kept keys), `nodetool flush s2c`, `nodetool compact s2c kv`, `nodetool drain` on all three, stop, tar each node's `data commitlog hints` (`saved_caches` emptied) to `/mydata/r11/golden-<role>.tgz`. Every arm restores it into a fresh instance dir, so each arm is a clean JVM start on identical data (one compacted `kv` sstable on V, empty `b6`, no hints, no saved caches) | environment (matched data state) |
| Instrumentation | **R11Gate** on V (new; `-Xmx32m`, nice 10; local JMX 127.0.0.1:7199; reads `MutationStage` PendingTasks every 200 ms into `gate.log`; TCP 7401 → sends `STOP` once pending ≥ G); **S2Poll** on each server node (R8 version, 1 s, nice 10, + `DroppedMessage,scope=MUTATION_REQ,name=InternalDroppedLatency` Count); pre-burst `jcmd <V> GC.class_histogram` (forced full GC, before the load); heap dump on OOM (shipped option); gc.log. No agent inside the JVMs | disclosed |

### 2.4 Ceiling arithmetic (V, 2 GiB; before readings)

Terms (MiB): baseline (schema, metadata, buffers, no caches) ≈ 120 (R8: T pre-burst live 397–401 with ≈ 275 + sketches
in cache classes); key + counter cache U: T 304 (214 + 90, B7), P 141 (94.6 + 46.6, B7), E ≈ 32 (table + sketch kept);
memtable at the peak M ≈ 170 (S2 ≤ 170); heap usable at OOM H ≈ 2,030 (S2 run 2 max live at OOM 99.1–99.3 %);
per queued write s ≈ 28 KiB (S2 G1: (2,030 − 120 − 170) MiB / 63.4 k; `byte[]` / `Mutation` gives 29.6 KiB because it
includes memtable slabs; range 28–30).

| | T (shipped weigher) | P (+104 B/entry) | E (invalidated) |
|---|---|---|---|
| Pre-burst live L (baseline + caches) | ≈ 400 | ≈ 237 | ≈ 128 |
| Room for the backlog H − L − M | ≈ 1,460 | ≈ 1,623 | ≈ 1,732 |
| **Gated edge G_X = room / s** (backlog V can hold) | **≈ 53.4 k** | **≈ 59.4 k** | **≈ 63.3 k** |
| Heap demand at G = 56 k (L + M + 56 k × 28 KiB = L + 1,701) | ≈ 2,101 (> H: OOM) | ≈ 1,938 (95 %) | ≈ 1,829 (89 %) |

Contract capacities alone: 512 + 100 + 50 + 204.8 = 867 MiB < 2,048, so no all-pools-full convergence; the OOM needs
the uncapped backlog (S2) and, at the chosen G, the uncounted cache memory (B7). T–P window ≈ 6.0 k queued writes
(163 MiB); the predicted G\* ≈ 56 k leaves ≈ +71 MiB past T's edge and ≈ 92 MiB below P's. Error terms: s ±1 KiB
moves every edge by ±2 k (equally, so the T–P window stays ≈ 6 k wide); the gate overshoot (≈ 200 ms × ≤ 6.7 k/s
offered ≈ 1.3 k) is the same in all arms by construction and measured. If the measured pre-burst T − P difference on
this platform is < 120 MiB (window < 4.4 k), stage 2 records it; the calibration still places G\* from readings.

### 2.5 Harness (stage 2 builds it under `harness/`; copy, do not re-derive)

Node layout on each node: `/mydata/r11/{run-orig,run-patched (V only),inst,golden-<role>.tgz,runs,dumps,h,cls}`;
controller `pc96:/mydata/r11-evidence/runs/<arm>/`; excerpts in `logs/`.

| File | Built from | Change |
|---|---|---|
| `ctl.sh` (per node) | S2 run-2 [`harness-run2/ctl.sh`](../convergence/coordinator-local-write-backlog--combo/harness-run2/ctl.sh) | roles V `ms0611` 10.10.1.4 (seed), R1 `ms0625` 10.10.1.1, R2 `ms0617` 10.10.1.5, tokens of §2.3, root `/mydata/r11/inst`, build `$BUILD` (`orig`/`patched`, V only; R1/R2 always orig); new verb `restore <role>` = `gen` + untar `golden-<role>.tgz` into the instance + `rm -f saved_caches/*`; start in the swap-0 user scope; stop by PID (30 s, then `kill -9`) |
| `S2Load.java` | R8 `harness/S2Load.java` | `-Dgate=host:port`: connect before the first send (fail → abort, `GATEFAIL`); a reader thread sets a volatile `stop` on the line `STOP`; send loop `!stop && now < end`; print `STOP_RECEIVED t= sent=` and `FINAL sent= ok= err=` with first/last ok timestamps; whitelist and contact `10.10.1.4`; `schema` creates `b6 {c:3}` and `s2c {c:1}` |
| `S2CacheFill.java` | R8 `harness/S2CacheFill.java` | `-Dvrange=3074457345618258602`: keep key `mix64(i)` only if `MurmurHash.hash3_x64_128(k,0,8,0)[0]` (normalized `Long.MIN_VALUE` → `MAX_VALUE`) > vrange; `first/count` index the kept keys; at start, check the first 1,000 kept keys with the driver's `Metadata.getReplicas("s2c", k)` = {10.10.1.4} and 1,000 rejected keys ≠ {10.10.1.4} (else abort `RANGEFAIL`) |
| `R11Gate.java` | new (≈ 60 lines) | `java -Xmx32m R11Gate <G or 0> 7401 <log>`; JMX `org.apache.cassandra.metrics:type=ThreadPools,path=request,scope=MutationStage,name=PendingTasks` every 200 ms → `<epoch ms> pending=<n>`; on the first reading ≥ G (G > 0) write `STOP` to every connected socket and log `GATE t= pending=`; keeps logging until killed |
| `S2Poll.java`, `sample.sh` | R8 harness | V, R1, R2 each local; + `self_dropped` (InternalDroppedLatency Count); 1 s |
| `client.sh` | S2 run-2 `harness-run2/client.sh` | on `ms0617`, classpath from `/mydata/r11/run-orig`, `load` passes `-Dgate`, `fill` passes `-Dvrange`, `-Xmx4g` |
| `arm.sh`, `collect.sh` | S2 run-2 `harness-run2/arm.sh`, `collect.sh` + R8 `arm.sh` | arm procedure below |
| `dumpparse.sh` | S2 run-2 `harness-run2/dumpparse.sh` | dump rsync'd to `pc96`, parsed there by `hprofhist.py` (nice 10), copy deleted |
| `gcpeak.sh`, `gcwin.py`, `hprofhist.py`, `logback-load.xml`, `b7-weigher-overhead.diff` | R8 harness | none |
| `table.py` | R8 harness | adds gate columns (G, gate time, max pending 200 ms, sent at stop) and per-node replica columns |

**Arm procedure** `arm.sh <name> <T|P|E> <G|0>` (T: V orig, caches kept; P: V patched, caches kept; E: V orig, caches
invalidated; all heaps 2 GiB):

1. Clean slate on all three nodes: kill harness JVMs (S2Load, S2CacheFill, S2Poll, R11Gate) by PID; `ctl.sh stop`
   each role; check no `CassandraDaemon` of the user remains; `rm -rf /mydata/r11/inst/<role>`.
2. `ctl.sh restore` V (`BUILD` per arm), R1, R2; start V, wait for 10.10.1.4:9042; start R1 and R2; wait until
   `nodetool status` on V shows `UN` = 3 (≤ 5 min, else `RINGFAIL`, arm void).
3. Record V's command line, resolved `-Xmx`, `MaxDirectMemorySize`, and `KeyCache`/`CounterCache` capacity lines from
   V's `system.log`; `nodetool info` on V: key cache entries ≈ 0 (no saved cache loaded).
4. Start `sample.sh` on the three nodes (poll.log, 1 s) and `R11Gate <G>` on V.
5. Fill (§2.3: read 1.5 M, counter 550 k, flush s2c) — every arm type including E.
6. Fill validity on V: `nodetool info` key cache size ≥ 99.0 MiB and counter cache ≥ 49.5 MiB. Short → read kept
   keys 1,500,000..1,600,000 once more; still short → `FILLFAIL`, arm void.
7. E only: `nodetool invalidatekeycache`, `nodetool invalidatecountercache`; check both sizes 0.
8. Pre-burst: `nodetool info` (cache lines), `nodetool tablestats s2c b6` (memtable lines), `jcmd <V> GC.class_histogram
   > hist-pre.txt` (forced full GC: the component-alone reading), then 10 s idle.
9. Burst from `ms0617`: `client.sh load run blob 11000 256 120 0 <10.10.1.4 × 8>` with `-Dgate=10.10.1.4:7401`
   (G = 0: no gate). T0 = first send. The client exits after STOP (or 120 s) and its in-flight responses/errors.
10. Observation from the client's exit: until V is dead, or V alive with `mut_pending` ≤ 1,000 for 30 consecutive
    seconds (drained), or **480 s**, whichever is first; if alive at 480 s with `mut_pending` > 1,000, extend once by
    240 s. Alive with pending > 1,000 at the end = `UNRESOLVED`.
11. Collect (S2 run-2 `collect.sh` logic): wait while a dump is written; `V_ALIVE`/`V_DEAD`; if alive, `nodetool info`
    on V (no histogram after the window: not needed); copy gc.log*, system.log, launch.log, `yaml.diff`, poll.log,
    gate.log, load.log; `gcpeak.sh . 2048` and `gcwin.py .` per node into `outcome.txt`; move any dump to
    `/mydata/r11/dumps/<name>-V.hprof` and start `dumpparse.sh` on pc96 in the background; stop the gate, samplers and
    all three nodes.
12. `table.py` row; append to `pc96:/mydata/r11-evidence/batch.log`.

**Endpoint, per arm.** **Heap OOM** = V dead and at least one of: `HeapDumper` or `ReportJavaOutOfMemory` safepoint in
V's gc.log, `java.lang.OutOfMemoryError` in system.log/launch.log (skip `CompileCommand` lines, R8 fix), a dump written
by `HeapDumpOnOutOfMemoryError`. **Survive** = V alive and drained (step 10). **Unresolved** = alive, not drained at the
end of the extended window. V dead without OOM evidence = **void** (investigate, not counted). GC service loss
(protocol default, `gcwin.py`) is recorded, not the endpoint. **Gate validity:** an arm that survives without the gate
firing (120 s cap reached first) is `LOADFAIL` (void); an arm whose V dies before the gate fires counts as OOM with its
pending at death recorded.

**Shakedown (not a reading, ≤ 12 min, before the golden state is final).** One arm `shake T 3000` on a reduced golden
state (fill 20 k keys, `FILL_SMALL=1`): ports, ring UN = 3, schema, key-range filter check, gate STOP reaching the
client, sampler columns, collection, cleanup. Fix the harness, never the design. The fill timing of the full golden
state is recorded when it is built.

### 2.6 Calibration (holder alone first; then the T/P bracket on the dial G)

1. **cal1 = E, G = 0 (uncapped, 120 s cap)** — the holder alone with caches filled then invalidated, = S2 G1 plus the
   fill-and-invalidate. Read: max `mut_pending` (gate log, 200 ms) = D_E, V's outcome, self-drops, `hints_inprog`,
   `hints_created`, replicas' pending. **Reachability:** D_E ≥ 30,000 (S2 G1: 62.8–64.0 k) and replicas' max pending
   ≤ 5,000 → the holder forms on this ring. If D_E < 30,000: amendment F1 (written before the next reading): `SESS=16`
   for all later arms; repeat cal1 once. Still < 30,000 → stop; verdict `retry` (holder not formed on these nodes).
   Prediction: heap OOM with D_E ≈ 60–64 k (S2 G1 3/3).
2. **G₁ = round₅₀₀(min(D_E, 63,000) − 7,000)** (predicted ≈ 56,000).
3. **cal2 = T at G₁, cal3 = P at G₁.** Predicted: T OOM, P survive.
4. Bracket (step 2,000 = ≈ 55 MiB): T survives → G ← G + 2,000, run T (then P at the same G); T and P both OOM →
   G ← G − 2,000, run P (then T at the same G if T has not OOMed there). The first G at which T OOMed and P survived
   (in the same or neighbouring readings at that G) is **G\***. At most **5 calibration arms including cal1**; no such
   G within them → stop, verdict `retry` with the readings. P `UNRESOLVED` at G counts as "not survived".
5. Write G\* into §3 as a dated amendment "G\* fixed" before the first counted arm. Calibration arms are not counted.

### 2.7 Counted arms, predictions, controls and intervention

Interleaved rounds from clean starts at G\* (2 GiB): `T-r1, P-r1, E-r1, T-r2, P-r2, E-r2, T-r3, P-r3, E-r3`.

| Arm | Role | Prediction (before readings) |
|---|---|---|
| T (orig, caches at caps) ×3 | endpoint (V1) | heap OOM **3/3**, within 600 s of the gate STOP (S2: OOM 62–460 s, some after a ≥ 60 s service-loss window); pre-burst live ≈ 380–420 MiB; dump: ≈ 50–57 k `Mutation` (`StorageProxy$4` + local `HintRunnable` wrappers), `PSMW` ≈ 1.78 M (1,310,720 + 468,114), `KeyCacheKey` 1.31 M, `CounterCacheKey` 468 k |
| P (patched weigher, caches at caps by K) ×3 | intervention (V4): removes only the uncounted ≈ 163 MiB at the same K and G | survive **3/3** (drained within the window); pre-burst live ≈ 150–175 MiB below T's; `PSMW` ≈ 0.81 M (569,878 + 242,725 entries by B7); max heap after any Full GC ≤ 97 %; max pending within ±3 k of T's |
| E (orig, caches filled then invalidated) ×3 | matched control (V2): the holder alone at the same G | survive **3/3**; pre-burst live ≈ 260–290 MiB below T's; max heap after any Full GC ≤ 93 % |

Matched across arms: build and yaml (P differs only in the weigher of `CaffeineCache.create(long)`, whose only callers
are the key and counter caches), heaps, topology, nodes, golden data, fill workload (E differs only in the two
invalidations), gate level G\*, client and its node. Recorded per arm for matching: sent at STOP, `FINAL ok/err`, time
to STOP, max `mut_pending` (200 ms) and its overshoot over G\*, self-drops, `hints_inprog` peak, `hints_created`,
memtable on-heap at the peak, replicas' max pending and live. An arm whose max pending exceeds G\* by > 3,000 is
reported and flagged in the decision.

**Decision rules (frozen).**
- T OOM 3/3, P survive 3/3, E survive 3/3 → proposed `verified-OOM · deployment`, mixed (unprotected accumulation +
  B7 accounting gap) → verdict **true positive**.
- T 2/3, or one P or E not surviving → if the clock allows (§2.9), two more rounds of T and P (and E if it failed);
  report n/N. V1 needs ≥ 3 T OOMs; V4 needs ≥ 3 P survivals and no P OOM at G\*; V2 needs ≥ 3 E survivals and no E
  OOM. Otherwise **retry** (state the rates).
- T ≤ 1/3 at G\* → **retry** (edge not reproducible at this G).
- P OOMs ≥ 2/3 at G\* → **retry** (the gap does not decide the OOM at G\*; record T and P peaks).
- Rounds incomplete when the clock stops them → **retry** (incomplete), with what ran.

**Budget search.** 2 GiB is the planned budget (largest failing at 2 GiB found by the gate). Upward probe, only if ≥ 35
min remain before the last-arm rule after the counted rounds: one T and one P with all three heaps at **4 GiB**
(caches stay 100 / 50 MiB), uncapped (G = 0), 90 s time cap — S2 G1-4G's load (alone: OOM 0/6, 97–98 % live). Predicted
T OOM (+304 MiB = 7.4 % of 4 GiB), P borderline (+141 MiB). n = 1 each: a boundary probe, not a verified condition.
Otherwise the case states "largest failing budget searched = 2 GiB; 4 GiB: S2 G1 alone 0/6 at 97–98 %".

### 2.8 Instruments (U independent of K)

- **Backlog U:** gate log (pending, 200 ms), S2Poll `mut_pending` / `mut_done` / `self_dropped` / `hints_inprog` /
  `hints_created` (1 s, no forced GC); `Mutation`, `StorageProxy$4`, `WriteResponseHandler`, `byte[]` in OOM dumps
  (`hprofhist.py` on pc96).
- **Cache U:** class counts × shallow sizes from `hist-pre.txt` (forced full GC before the load): `PSMW`,
  `ConcurrentHashMap$Node`, `KeyCacheKey`, `CounterCacheKey`, `ClockAndCount`, `RowIndexEntry`, key `byte[]` share by
  B7's layout; cross-check by pre-burst live heap T − E and T − P. K from JMX `Size` / `nodetool info`.
- **Heap:** gc.log (`gcpeak.sh`: max after any pause, max after Full GC, Full GC count; `gcwin.py`: worst-60 s STW,
  service loss, `HeapDumper` / `ReportJavaOutOfMemory` marks); MemoryMXBean used every 1 s.
- **Initiating failure (V5):** gc.log safepoint marks; first `OutOfMemoryError` with its thread from system.log or
  launch.log if written; the dump histogram of every counted T arm (parsed on pc96 during later arms).
- **Overhead:** gate (32 MiB JVM, one JMX read / 200 ms) and S2Poll (48 MiB, 1 s) at nice 10 on V, the same in every
  arm; forced GCs only before the burst.

### 2.9 Time plan and stopping budget (America/New_York, 2026-11-20)

Arm length estimate (m400): restore + start ring ≈ 2.5 min, fill ≈ 4 min (reads + counters; measured when the golden
state is built), histogram ≈ 0.5 min, burst to STOP ≈ 0.5–1 min, observation 1–8 min (OOM arms end early; E/P drain,
S2 4 GiB drained within 300 s), collect ≈ 1.5 min ≈ **11–17 min** (worst 21 with the extension).

| Window | Work |
|---|---|
| ≈ 12:00 – 12:55 | read this file, check the freeze hash; check the three nodes (`ps`, `free`, `df`); builds (`cp -a`, `rsync`, `ant jar` in run-patched only); write and compile the harness; shakedown; golden state (insert 1.6 M + flush + compact + drain + tar) |
| 12:55 – 14:05 | calibration, ≤ 5 arms |
| 14:05 – 16:20 | 9 counted arms |
| 16:20 – 16:50 | extra rounds (decision rule 2) or the 4 GiB probe; **no arm starts after 16:50** |
| ≤ 17:05 | every process the run started stopped (three `CassandraDaemon`, gate, samplers, clients); `loginctl disable-linger` where it was off before (ms0611, ms0625); dump parsing finished or the dumps left on the node and named |
| ≤ 17:30 | §3, §4 and the write-backs (playbook stage 2 step 5) |

Hard limits: ≤ 18 arm executions; no arm starts after 16:50; whatever runs at 17:05 is stopped. If stage 2 starts
after 12:30, calibration is capped at 4 arms; if counted rounds start after 14:45, run T and P first in each round and
E last, and an incomplete set is `retry` (§2.7). No escalation after an OOM beyond the planned arms. Resources per
node: one 2 GiB server JVM (+ ≈ 1–2 GiB off-heap), on `ms0617` also the client (4 GiB heap); ≪ 62 GiB. Disk on V:
builds 1 GB, golden ≈ 0.2 GB, b6 data and commit log ≤ 3 GB per arm (wiped by the next restore), dumps 2.2 GB each:
keep cal1's and T-r1's dumps on V, delete the others once their histogram is on pc96 (≤ 12 GB of 35 GiB free).

### 2.10 Limits known before the run

- The gate is a client-side stop driven by one JMX read on V; it changes nothing inside the server, but it is a
  measured, not a natural, burst end. The equivalent deployment event is a CL=ONE write burst whose length puts V's
  backlog at G\*; `sent at STOP` is reported so the burst size is visible. The researcher may rule on the label.
- R2 shares its node with the client (S2 run 2 had a separate client node); the same in every arm, disclosed.
- The edge window is ≈ 8 % of the heap; GC slows V near the edge in T only, which is part of the mechanism.
- The intervention charges 104 B/entry, an upper bound on this JVM layout (B7: U/C 0.93–0.95), so it removes slightly
  more than the gap; K is the same (100 / 50 MiB) in T and P. The per-entry layout was measured on x86 (B7, R8);
  aarch64 JDK 11 with compressed oops should match, and `hist-pre.txt` measures it.

`sha256 of §1–§2 at freeze: de59a261e81cbf890f8816c6ff52cb9635c0f5df79347c2c82fd37e69752c98d` (bytes from the line `## 1. Candidate` through the line before this one, as written by stage 1) · amendments after the freeze: A1 (2026-11-20 11:20 EST, §3.0; no setting changed).

## 3. Runs (stage 2)

Stage 2: a fresh phase-2 OOM agent (Claude Opus 5.5, subagent), 2026-11-20 from 10:40 EST. Freeze hash checked at 10:41:
`de59a261…752c98d` (matches).

### 3.0 Amendments (dated, each written before the readings it affects)

- **A1 (2026-11-20 11:20 EST, after cal1, before cal2).** §2.6 step 1 reads "D_E ≥ 30,000 and replicas' max pending
  ≤ 5,000 → the holder forms on this ring" but gives a branch only for D_E < 30,000. cal1 gave D_E = 65,898 (met) with
  R1 max pending 96 (met) and R2 max pending 8,106 (not met): R2 exceeded 1,000 in 3 one-second samples only (6,843 /
  8,106 / 1,480 at +28–35 s), each gone by the next sample, while V held 33–66 k from +17 s to its death. R2 shares its
  node with the client (§2.10). Decision: the holder forms on V (the claimed domain); the R2 spikes are transient
  replica queueing, not a second holder. Calibration continues as frozen; each arm reports R1/R2 max pending, and R2
  peaks are compared across T/P/E as a matching variable. No setting changes.


### 3.1 Environment (as run)

| Item | Value |
|---|---|
| Nodes | V `ms0611` 10.10.1.4, R1 `ms0625` 10.10.1.1, R2 `ms0617` 10.10.1.5 (+ client); Utah m400 `jason92-326377`, aarch64, 8 cores, 62 GiB, 8 GiB swap (0 used in every arm), SSD `sda` (ROTA 0), kernel 5.15.0-191, cgroup v2, OpenJDK 11.0.33. All idle at 10:41 (no Java process); Linger was no / no / yes; enabled on ms0611 and ms0625 for the run, disabled again at the end. Controller `pc96` (node0.jason92-325405, the local node; 32 threads) |
| Work dirs | `/mydata/r11/` on each node (created with `sudo mkdir` + `chown`, `/mydata` is root-owned); controller `pc96:/mydata/r11-evidence/` (runs, batch.log, dump histograms) |
| Builds | **orig** = `cp -a ms0611:/mydata/s4/cassandra-base` → `/mydata/r11/run-orig` (git `02a233a`, jar md5 `1becab414e5f…`), relayed to ms0625 and ms0617 by `rsync` through pc96 (the m400s cannot ssh to each other); jar md5 equal on all three. **patched** = `ms0611:/mydata/r11/run-patched` = copy of run-orig + `harness/b7-weigher-overhead.diff` (`git apply`, 1 file), `ant jar` 41 s, BUILD SUCCESSFUL, jar md5 `450355e1c94d…`, `CaffeineCache.class` contains `b7.entry_overhead` |
| JVM / budget (V, every arm) | `-Xms2G -Xmx2G -XX:+UseG1GC`, `MaxDirectMemorySize` resolved by `cassandra-env.sh` = 15,872 MiB (VM.flags 16,642,998,272 B); scope `memory.max = max`, `memory.swap.max = 0`; key cache capacity 100 MiB, counter cache 50 MiB, row cache 0 (system.log); R1/R2 the same heap and build orig |
| yaml diff | exactly §2.3 (`cluster_name 'r11ring'`, `num_tokens 1`, addresses, seed 10.10.1.4, GPFS snitch, dirs, `auto_bootstrap: false`, `initial_token`); `logs/*/V-yaml.diff` |
| Golden state | built 10:59–11:02: 1,600,000 kept `kv` keys inserted in 70.8 s (22.6 k/s; 4,799,963 candidates for 1.6 M kept, ⅓ as designed), one compacted sstable on V (53.3 MB, ≈ 1.61 M partitions), drained, tarred (`golden-V.tgz` 46 MB; R1/R2 66 KB). Range check `RANGEOK kept=1000 rejected=1000` in every fill. `describering s2c`: V owns (3074457345618258602, −2^63] as designed. [`logs/golden-full.log`](logs/golden-full.log) |
| Fill (per arm) | read 1,500,000 kv in ≈ 104 s (14.5 k/s), counter 550,000 in ≈ 47 s (11.8 k/s); fill validity met in every full arm (key 100.00 MiB, counter 50.00 MiB on the first pass) |
| Harness | [`harness/`](harness/): `ctl.sh`, `S2Load.java` (gate client), `S2CacheFill.java` (V-range filter + replica check), `R11Gate.java`, `S2Poll.java` (+ `self_dropped`, `dropped_mut`), `sample.sh`, `client.sh`, `vstate.sh` (observation helper), `arm.sh`, `batch.sh`, `golden.sh`, `dumpparse.sh`, `table.py`; `gcpeak.sh`, `gcwin.py`, `hprofhist.py`, `logback-load.xml`, `b7-weigher-overhead.diff` copied from R8 unchanged |

Harness fixes during the shakedown (harness only, no design change): `arm.sh`'s leftover-daemon check matched its own
ssh command line (now `[C]assandraDaemon`); `S2Load` `SocketOptions` import clash; `batch.sh` let `arm.sh`'s ssh read
the arm list from stdin (ran only the first line; now `< /dev/null`; cal2 and cal3 were therefore launched as two
batches, same procedure).

**Shakedown** (`shake T 3000`, 20 k golden + 20 k fill, 10:52–10:58, not a reading): ring UN = 3 in 90 s, gate STOP
reached the client 5.7 s after the first send (gate reading 7,246, first reading ≥ 3,000; the pending series jumps by
up to ≈ 6 k in 200 ms), V drained, all three stopped, collection and table OK. [`logs/shake/`](logs/shake/)

### 3.2 Calibration arms (§2.6), 2026-11-20 11:02–11:54 EST

All arms from clean starts on the golden state, 2 GiB on all three nodes, 8 × 256 in flight to V, CL=ONE, 120 s cap.
"Inflow" = time from the first send to the last successful write (oks) or to STOP. Pending = V `MutationStage`
PendingTasks from the gate (200 ms). Self-drops / hints = V's `MUTATION_REQ` InternalDroppedLatency count / `TotalHints`.

| Arm | Type, G | V outcome | Gate (STOP at, reading) | Writes sent / ok / err | Inflow | Max pending (over G) | Pre-burst live (forced-GC histogram) | K key / counter, entries | Max after any GC; Full GCs, max after Full | Worst 60 s STW | Self-drops / hints | R1 / R2 max pending, max after GC | OOM mark (s after first send / after STOP) | Dump (parsed on pc96) |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `cal1` | E, 0 (uncapped) | **heap OOM** | — (G = 0) | 234,042 / 231,986 / 2,056 | 54.6 s of oks, then V stalled; client to the 120 s cap | **65,898** (D_E) | 122 MiB | 0 / 0 (invalidated) | 2,043 MiB (99.8 %); 988, 2,033 (99.3 %) | 99 % (service loss MET, 489 s ≥ 90 % window) | 91,929 / 41,222 | 96, 100 % (young); 8,106, 100 % (young) — A1 | HeapDumper 245 s (uptime 583 s); ReportJavaOutOfMemory uptime 832 s | 59,859 `Mutation` = `StorageProxy$4` = `WriteResponseHandler`; `byte[]` 1,804 MiB of 2,055; dump kept on ms0611 |
| `cal2` | T, 56,000 | survive (drained 8.7 s after STOP) | 17.1 s, 56,694 | 83,450 / 83,450 / 0 | 17.1 s | 56,694 (+694) | **394 MiB** | 100 / 50 MiB; 1,310,720 / 468,114 | 1,978 MiB (96.6 %); 7, 1,685 (82.3 %) | 14 % | 54,839 / 45,347 | 96, 47.5 %; 11, 25.6 % | — | — |
| `cal3` | P, 56,000 | **heap OOM** | 68.6 s, 56,217 | 263,298 / 261,768 / 1,530 | 68.6 s | 56,441 (+441) | **230 MiB** | 100 / 50 MiB; 569,878 / 242,725 | 2,043 MiB (99.8 %); 55, 2,028 (99.0 %) | 60 % (not met) | 129,717 / 43,262 | 2,131, 100 %; 2,441, 100 % | 79 / 11 (first `OutOfMemoryError` logged on `GossipStage:1` in `InboundSink.accept`) | 56,202 `Mutation` / 56,201 `StorageProxy$4`; `byte[]` 1,746 MiB of 2,102; `PSMW` 812,608; deleted after parsing |
| `cal4` | T, 58,000 | survive (drained 10.7 s after STOP) | 21.4 s, 60,759 | 101,265 / 101,265 / 0 | 21.4 s | 65,864 (**+7,864**, > 3,000: flagged) | 396 MiB | 100 / 50 MiB; 1,310,720 / 468,114 | 2,004 MiB (97.9 %); 11, 1,906 (93.1 %) | 20 % | 67,356 / 63,155 | 22, 100 % (young); 9, 24.6 % | — | — |
| `cal5` | T, 60,000 | **heap OOM before the gate fired** (counts as OOM, §2.5) | never (max reading 58,596) | 142,172 ok (then 6.7 M `NoHostAvailable` client retries after V's death) | ≈ 48 s of oks | 58,596 at +26.6 s; last gate reading 48,095 at +48.5 s, none in the 26 s before the OOM mark (JMX starved) | 392 MiB | 100 / 50 MiB; 1,310,720 / 468,114 | 2,044 MiB (99.8 %); 72, 2,030 (99.1 %) | 82 % (not met) | 74,899 / 58,288 | 4, 100 % (young); 19, 100 % (young) | 75 / — | 48,228 `Mutation` / 48,227 `StorageProxy$4`; `byte[]` 1,607 MiB of 2,126; caches intact (`PSMW` 1,778,839, `ConcurrentHashMap$Node` 1,818,669, `KeyCacheKey` 1,310,720, `CounterCacheKey` 468,114; ≈ 304 MiB in the cache classes by `hprofhist`'s +16 B estimate); deleted after parsing |

Readings common to the arms:
- **Cache gap on aarch64 (B7 reproduced).** Pre-burst live heap T 392–396 MiB, P 230 MiB, E 122 MiB: T − P = 164 MiB
  (predicted ≈ 163), T − E = 272 MiB (predicted 260–290). Entry counts are B7's exactly (T 1,310,720 + 468,114, P
  569,878 + 242,725). Caffeine `PSMW` nodes 1,778,838 (T) vs 812,607 (P), 40 B each; `KeyCacheKey` 32 B,
  `RowIndexEntry` 24 B, `ClockAndCount` / `CounterCacheKey` 32 B — the B7 layout.
- **The holder (S2) forms on this ring.** V's `MutationStage` pending reaches 56–66 k in every arm, replicas stay ≤
  2.4 k (8.1 k once, A1); the three OOM dumps hold 48–60 k queued local writes (`StorageProxy$4`), `byte[]` 1.61–1.80 GiB.
- **The pending series is a saw-tooth, not a ramp.** Local copies that wait > 2 s are self-dropped in bursts of 10–44 k
  and re-submitted as `HintRunnable`s (`StorageProxy.java:2623–2654`); at each such burst pending falls by 14–33 k within
  1–3 s (why the re-submitted copies do not keep it up was not resolved here)
  (cal1: 30 k → 1.5 k at +21 s, 42 k → 28 k at +31 s, 65.9 k → 33 k at +42 s). The time for V's pending to first reach
  G therefore varied 17.1 s (cal2), 21.4 s (cal4), 68.6 s (cal3), never within 75 s (cal5).
- **After STOP the backlog drains in ≈ 9–11 s** (V applies ≈ 5–6 k/s once inflow stops; cal2, cal4); the
  "≥ 370 s after the stop" death of S2 run 2 did not recur in any gated arm. The OOM arms died while inflow continued
  (cal5, cal1) or 11 s after a STOP that came 68.6 s into the burst (cal3).
- Self-drops and hints were large in every arm (55–130 k self-drops, 41–63 k hints): the client's CL=ONE writes keep
  being acked by R1/R2 while V's copy waits, as in S2.

### 3.3 Calibration bracket and stop (§2.6 step 4)

- G₁ = round₅₀₀(min(65,898, 63,000) − 7,000) = **56,000**. cal2 (T) survived and cal3 (P) died: the opposite of the
  prediction (T OOM, P survive), and a combination the bracket rule does not use (it moves on T's result).
- T survived at 56,000 → G = 58,000: cal4 (T) survived (max pending 65,864, 97.9 % after GC).
- T survived at 58,000 → G = 60,000: cal5 (T) died before the gate fired.
- That was the 5th calibration arm including cal1. No G had T OOM and P survive, so §2.6 step 4's stop applied
  ("no such G within them → stop, verdict `retry` with the readings"). **No counted arm ran; G\* was never fixed; the
  4 GiB probe was not run** (§2.7: only after the counted rounds). Calibration ended 11:54 EST, well inside the window.

Raw logs: `pc96:/mydata/r11-evidence/runs/<arm>/{arm.log,obs.log,V,R1,R2,client}` and on each node
`/mydata/r11/runs/<arm>/`. Excerpts: [`logs/`](logs/) (`<arm>/arm.log`, `*-outcome.txt`, `gate-events.txt`,
`gate-pending-1s.txt`, `V-poll-burst.txt`, `R*-poll-pending.txt`, `hist-pre-top.txt`, `load.txt`, `dump-hist.txt`,
`V-oom-excerpt.txt`), [`logs/batch.log`](logs/batch.log) (table rows by `table.py`).

**Cleanup (12:08 EST).** Every process the run started is stopped (no Java, sampler or gate of the user on the three
nodes, no `r11-*` scope); Linger disabled again on ms0611 and ms0625 (ms0617 was and stays `yes`). Left on the nodes
(all stopped data): ms0611 `/mydata/r11` 4.9 GB (builds run-orig + run-patched 0.94 GB, golden 45 MB, last instance
1.7 GB, runs 108 MB, **`dumps/cal1-V.hprof` 2.2 GB** kept per §2.9; the cal3 and cal5 dumps were deleted after parsing);
ms0625 `/mydata/r11` 1.5 GB (run-orig, last instance 1.0 GB, runs); ms0617 `/mydata/r11` 1.2 GB (run-orig, last
instance 0.7 GB, runs); pc96 `/mydata/r11-evidence` 122 MB.

## 4. Conclusion (stage 2)

**Verdict: retry.** Protocol status: `candidate` (V1–V5 not reached: no G\* and no counted arm; calibration stopped by
§2.6 step 4 after the 5-arm limit). Direction as designed: mixed (S2 unprotected accumulation + B7 accounting gap);
neither the convergence of the two nor the causal role of the cache gap was shown.

**Reason.** On this aarch64 RF=3 ring the S2 holder formed as predicted (V `MutationStage` pending 56–66 k, dumps
with 48–60 k queued local writes = `StorageProxy$4`, 1.61–1.80 GiB of `byte[]`), and the B7 gap reproduced at
defaults (pre-burst live heap T 392–396 MiB vs P 230 MiB vs E 122 MiB: the shipped weighers leave 164 MiB uncounted at
K = 100 + 50 MiB). Heap OOM at defaults and a 2 GiB heap happened in 3 of 5 calibration arms, including the holder
alone with invalidated caches (cal1, uncapped) and patched-weigher P (cal3). But the gated bracket did not separate T
from P: at G = 56,000 T survived (cal2, 96.6 % max after GC) while P died (cal3); T survived again at 58,000 (cal4,
97.9 %) and died only at 60,000 before the gate fired (cal5). The deciding variable was not the backlog level G nor
the 164 MiB cache gap but how long the client kept sending while V was saturated: the gate's pending reading is a
saw-tooth (it falls by 14–33 k within 1–3 s at each burst of self-drops), so reaching G took 17.1 / 21.4 s in
the surviving T arms (83 k / 101 k writes sent, drained 9–11 s after STOP) but 68.6 s in P (263 k sent, OOM 11 s after
STOP) and > 75 s in cal5 (OOM before STOP). Every OOM arm had ≥ 48 s of sustained inflow and ≥ 142 k writes; every
survivor ≤ 21 s and ≤ 101 k. The run-to-run spread in inflow time is far wider than the ≈ 6 k-write (164 MiB) window
the design needed. This is not a false positive: the endpoint is reachable at defaults on this ring (as in S2), the
counted T/P/E rounds never ran, and nothing shows the cache gap cannot decide an OOM; the experiment could not isolate
it with this dial.

**What a better design should change.**
1. **Replace the pending gate with a dial that fixes the inflow.** V's `MutationStage` PendingTasks is not monotone in
   the accepted backlog (self-drop / hint re-queue cycles), so a threshold on it fires at very different burst lengths.
   Use either a fixed total N (S2Load `-Dtotal`) bracketed on this ring between ≈ 100 k (T survived) and ≈ 140 k (T
   OOM), or a rate cap slightly above V's apply rate (S2: 1,500/s = 0.5 × survived; try ≈ 1.1–1.3 × V's measured apply
   rate, measured in E first) for a fixed duration, so the backlog grows smoothly and the heap terms, not GC timing,
   set the edge.
2. **Expect mixed outcomes at the edge and plan for rates, not 3/3 brackets:** with run-to-run spread this large, run
   ≥ 5 T and ≥ 5 P at one fixed N (and E) and compare OOM rates and peak live heap after GC; or use a continuous
   reading (heap after the last Full GC at STOP, or time to OOM under a fixed rate cap) where T − P ≈ 164 MiB is
   visible without an exact edge.
3. Calibrate the dial on E with ≥ 3 arms before placing T/P (one E arm could not show the spread), and allow more than
   5 calibration arms (each arm is ≈ 8–10 min here; the 5-arm limit was reached by 11:54 with ≥ 5 h left).
4. Keep: the ring, golden state, V-range fill (RANGEOK every arm, caches reach K exactly), forced-GC pre-burst
   histogram, and the observation window; record R2 separately from the client node or move the client to a fourth
   m400 (R2 spiked to 8.1 k pending once, A1).

**Limits.** n = 1 per calibration condition; the inverted cal2/cal3 pair could also be chance at one G. The OOM in
cal1/cal5 is S2's verified mechanism (unprotected local-write backlog), not new evidence about the caches.
