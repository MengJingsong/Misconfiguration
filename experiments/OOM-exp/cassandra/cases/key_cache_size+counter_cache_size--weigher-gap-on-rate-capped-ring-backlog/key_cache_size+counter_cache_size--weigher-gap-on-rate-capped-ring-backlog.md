# R19 (retry of R11 / R8 / B7) — key_cache_size + counter_cache_size: weigher gap on a rate-capped, fixed-total RF=3 ring backlog  <!-- file: cassandra/cases/key_cache_size+counter_cache_size--weigher-gap-on-rate-capped-ring-backlog/key_cache_size+counter_cache_size--weigher-gap-on-rate-capped-ring-backlog.md -->

| Field | Value |
|---|---|
| Case ID | `R19` (R = a new attempt at an earlier case: R11, itself a retry of R8 / B7) |
| From | retry of `R11` ([phase-2 retry list](../../phase2-retry-list.md), row R11, status `picked again: R19 (2026-11-21)`) |
| Phase-1 case file | [`key_cache_size-create-size--autonomous`](../../../../capacity-enforcement-exp/cassandra/stage3-ai-deep-read/cases/key_cache_size-create-size--autonomous.md), [`counter_cache_size-putcachedcounter-capacity--autonomous`](../../../../capacity-enforcement-exp/cassandra/stage3-ai-deep-read/cases/counter_cache_size-putcachedcounter-capacity--autonomous.md) (phase-1 row OC-2) |
| System / pinned source | Cassandra 5.0.9 (`systems/cassandra/source/`; on the nodes `ms0611:/mydata/s4/cassandra-base`, git `02a233a`, jar md5 `1becab414e5f…` — the build R11 ran) |
| Stage 1 (design) | phase-2 OOM agent, stage 1 (Claude Opus 5.5, subagent), 2026-11-21 01:50–02:50 EST |
| Stage 2 (verify) | phase-2 OOM agent, stage 2 (Claude Opus 5.5, fresh subagent), 2026-11-21 02:00–03:30 EST; ring `ms0611` V, `ms0625`, `ms0617`, client `ms0604` |
| Verdict | **retry** (`candidate`: calibration stop §2.6 step 4, E survived at r = 4,700 up to N = 200 k; no counted arm) |

## Summary

- **Conclusion:** **retry**. The fixed-rate dial never reached the edge: the frozen rule capped the rate at 4,700 writes/s,
  and at that rate V kept up with the backlog alone (E survived N = 140 k, 170 k and 200 k; heap after GC at STOP 686–927 MiB
  of 2,048), so the design stopped before any T/P arm. Diagnostic E arms show V's CL=ONE apply rate is above 5.2 k/s; at
  ≈ 5.3 k/s E sat at its edge (97 % after GC at N = 200 k) and uncapped E died by heap OOM (S2's holder, 60 k queued writes).
  The question whether the 164 MiB cache gap decides the OOM is still open.
- **Root cause (claimed):** no control charges the coordinator's queued local writes (S2, `LocalMutationRunnable` and
  its `HintRunnable` re-queue on `MutationStage`), and the key/counter cache weighers count key + value bytes only, not
  the ≈ 90–100 B per entry of the Caffeine container (B7). The claim tested here: at one fixed, rate-capped inflow, the
  uncounted ≈ 164 MiB of the shipped weighers decides whether V's 2 GiB heap survives the backlog.

## 1. Candidate

**Retry row (quoted from [`phase2-retry-list.md`](../../phase2-retry-list.md), as of 2026-11-21 01:50 EST):**

> | [R11](cases/key_cache_size+counter_cache_size--weigher-gap-on-gated-ring-backlog/key_cache_size+counter_cache_size--weigher-gap-on-gated-ring-backlog.md) (retry of R8 / B7) | 2026-11-20 | On the aarch64 RF=3 ring (ms0611 V, ms0625, ms0617; 2 GiB heaps, defaults) the S2 backlog formed (V pending 56–66 k) and B7's weigher gap reproduced (T 392–396 vs P 230 vs E 122 MiB live pre-burst; 164 MiB uncounted). Heap OOM in 3 of 5 calibration arms (E uncapped, P at G 56 k, T at G 60 k), but the pending gate does not fix the burst: pending saw-tooths down 14–33 k at each self-drop burst, so survivors had ≤ 21 s / ≤ 101 k writes and every OOM ≥ 48 s / ≥ 142 k — a spread far wider than the ≈ 6 k-write gap window. The 5-arm calibration cap ended the run at 11:54; no counted arm | Fix the inflow, not the pending count: a fixed total N (bracket ≈ 100 k–140 k on this ring) or a rate cap ≈ 1.1–1.3 × E's apply rate for a fixed duration; ≥ 5 T and 5 P (plus E) at one N, compare OOM rates and heap after GC at STOP (or time-to-OOM under the rate cap); ≥ 3 E arms to calibrate and no 5-arm cap; keep ring, golden state and V-range fill; client on a fourth node if available | picked again: R19 (2026-11-21) |

**Earlier cases and verdicts.**
- [R11](../key_cache_size+counter_cache_size--weigher-gap-on-gated-ring-backlog/key_cache_size+counter_cache_size--weigher-gap-on-gated-ring-backlog.md)
  (2026-11-20, ms0611 V / ms0625 / ms0617 + client): **retry** (`candidate`). A gate on V's `MutationStage` pending
  stopped the client at G. Readings this design builds on (§3.2 there): pre-burst live heap (forced-GC histogram) T
  392–396 MiB, P 230, E 122 (T − P 164 MiB, T − E 272 MiB; entry counts exactly B7's: T 1,310,720 + 468,114, P 569,878 +
  242,725); memtable on-heap at the burst ≈ 167 MiB; uncapped CL=ONE offered rate 4.7–4.9 k writes/s while V was not
  stalled (cal2 83,450 in 17.1 s, cal4 101,265 in 21.4 s); after STOP V drains 5–6.5 k/s; T survived at 83 k and 101 k
  sent (max heap after any GC 96.6 / 97.9 %), T died at 142 k (cal5, before the gate), P died at 263 k (cal3), E died
  uncapped at 232 k (cal1). The three OOM dumps: 48–60 k `Mutation` = `StorageProxy$4`, `byte[]` 1.61–1.80 GiB; cal5 (T)
  dump with the caches intact (`PSMW` 1,778,839; ≈ 304 MiB in the cache classes). Arm length 7.5–9 min (cal1, uncapped
  120 s with a long thrash: 16.5 min).
- [R8](../key_cache_size+counter_cache_size--weigher-gap-on-write-backlog/key_cache_size+counter_cache_size--weigher-gap-on-write-backlog.md)
  (2026-11-17, pc91 x86): **retry** — gap reproduced (≈ 275 MiB in cache classes for K = 150 MiB), backlog did not form
  (max pending 9,724).
- [B7](../bypass/key_cache_size+counter_cache_size-accounting-mismatch/key_cache_size+counter_cache_size--accounting-mismatch.md)
  (2026-11-12): **retry** (`verified-gap · overshoot · deployment`): key cache 2.14×, counter cache 1.80× their caps at
  defaults, 3/3 at 512 MiB, 2 GiB and 7,965 MiB; a +104 B/entry weigher brings U/C to 0.95 / 0.93. No OOM alone.
- [S2](../convergence/coordinator-local-write-backlog--combo/coordinator-local-write-backlog--combo.md) (**true
  positive**, `verified-OOM · deployment`): run 2 G1 (aarch64 RF=3 ring, all heaps 2 GiB, CL=ONE uncapped, defaults)
  heap OOM 3/3; CL=ALL 0/3 with **328.7–329.8 k writes in 90 s (≈ 3.65 k/s: V's own apply capacity when the client
  waits for it)**; a 1,500/s cap (≈ 0.5 × that) 0/3 at ≤ 9 % live; 4 GiB 0/6 at 97–98 % live.

**Phase-1 constraint and check** (unchanged from R8/R11 §1). `key_cache_size` / `counter_cache_size` "auto" =
`min(max(1, 5 % of heap), 100)` / `min(max(1, 2.5 % of heap), 50)` MiB (`DatabaseDescriptor.java:814–836`) →
`CacheService.initKeyCache` / `initCounterCache` → `CaffeineCache.create(capacity)` (`cache/CaffeineCache.java:61–71`,
re-read 2026-11-21): `maximumWeight(capacity)`, weigher `key.unsharedHeapSize() + value.unsharedHeapSize()`, eviction
on the writer (`ImmediateExecutor`, `:56`), so K ≤ C while the Caffeine node, `ConcurrentHashMap$Node`, table slot and
sketch slot are not weighed. Phase-1 stage 4 (2026-10-25): `caps` for the counted weight; cache classes 1.417× `Size`,
1.9–2.0× for the whole live-heap increase; runtime shrink leaves +17.3 MB.

**JIRA prior art** (read only; nothing posted).
- Survey [`jira-oom-survey.csv`](../../../../capacity-enforcement-exp/cassandra/stage5-oom-clue-find/jira-oom-survey.csv),
  re-grepped 2026-11-21 (`key cache|counter cache|weigh|caffeine|MutationStage|LocalMutationRunnable|19958|write
  backlog`): the same rows as R11 — 4315 / 4860 (Fixed, payload weighers), 5706 / 5986 / 6260 / 7171 / 9120 (saved-cache
  load, other path), 6149 (Fixed, other cache), 9754 (other holder), 11460 (Won't Fix: MutationStage queue under writes
  above capacity — the S2 holder, by design), 13213 (Unresolved: pending mutations OOM), 12689 (Fixed, MV deadlock),
  5039 (Won't Fix: bounded queues); no new row.
- JIRA REST (`issues.apache.org/jira/rest/api/2/search`, reachable, 2026-11-21 ≈ 01:55 EST): `text ~ "weigher" AND
  updated >= 2026-06-01` → 0; `(text ~ "key cache" OR text ~ "counter cache") AND text ~ "memory" AND updated >=
  2026-11-01` → 2 (21894 write-aware row cache, 21899 SslContext release: neither about the weigher); `(text ~
  "MutationStage" OR text ~ "LocalMutationRunnable" OR text ~ "self-dropped") AND updated >= 2026-11-01` → 4 (flaky
  tests, cqlsh, compression dictionaries: none); `CASSANDRA-19958` *Local Hints are stepping on local mutations* still
  **Needs Committer** (updated 2026-08-26).
- Verdict unchanged from R11: weigher gap **new** (not documented as a memory bound); local-write backlog
  **known-open** (19958; 11460 by design); the combination not found. Not known-fixed, so not a positive control.

**What R19 changes against R11 (not a rerun).**
1. **The dial fixes the inflow, not the pending count:** the client sends at a fixed rate r (≈ 1.2 × V's apply rate
   measured in E) until a fixed total N is sent (S2Load's existing rate argument and `-Dtotal`). The burst length
   (≈ N / r) and the total are the same in every arm; R11's gate is kept only as a 200 ms pending logger.
2. **Rates, not a bracket:** ≥ 5 T and ≥ 5 P (plus 3 E) at one (r, N\*), compared by OOM rate and by a continuous
   reading (heap after GC at STOP), with a decision rule for mixed outcomes stated in advance (§2.7).
3. **Calibration on E first, ≥ 3 E arms, no 5-arm cap:** one CL=ALL E arm measures V's apply rate a_E; 2–3 E arms at r
   find E's edge in N; one T placement check; then N\* is fixed by a frozen rule (§2.6).
4. **Client on a fourth node** (`ms0604`), so R2 (`ms0617`) is a plain replica (R11 A1: R2 spiked to 8.1 k pending once
   while it shared its node with the client).
5. **Kept:** the ring (V `ms0611`, R1 `ms0625`, R2 `ms0617`), tokens, schema, R11's golden V data state
   (`ms0611:/mydata/r11/golden-V.tgz`), the V-range cache fill with its replica check, the forced-GC pre-burst histogram,
   the B7 weigher patch for P, the instruments.

**Terms of the B7 row not used (as R8/R11, same reasons):** runtime-shrink residue (needs `setcachecapacity`, not V6),
Paxos and prepared-statement weighers (other fills, would confound P), "more distinct keys" (8-byte keys already give
the most entries per MiB).

## 2. Design solution (stage 1; frozen)

### 2.1 Mechanism and direction

Direction: **mixed** — an unprotected accumulation (S2's local-write backlog; no control, no counter) plus a bypass by
accounting mismatch (B7: U > C with K ≤ C in both caches) in the same heap. Technique notes:
[`combo-playbook.md`](../../../combo-playbook.md) (accounting gap as the last layer of a stack at its edge) and
[`bypass-playbook.md`](../../../bypass-playbook.md) (protected path = a weigher that charges the per-entry overhead).

V (`ms0611`) coordinates every CL=ONE blob write of the client and is a replica of every key (RF=3 in a 3-node ring).
For each write it submits its own copy as a `LocalMutationRunnable` on `Stage.MUTATION` (`StorageProxy.java:1674`
`performLocally`; `concurrent_writes` 32 threads, unbounded queue) and sends copies to R1 and R2. The first replica ack
releases the client slot and the request's `native_transport_max_request_data_in_flight` charge while V's copy still
waits. A local copy that waits past `write_request_timeout` (2 s) is counted as self-dropped and re-submitted as a
`HintRunnable` on the same stage (`StorageProxy.java:2634–2656`, `submitHint` `:2822–2828`), so the backlog is not shed
(this is also why the pending gauge saw-tooths: the dropped task completes at once, its re-queue follows). When the
offered rate r exceeds V's apply rate, the backlog grows by about (r − a) per second, faster once self-drops start, and
each queued 11,000-byte write holds ≈ 28 KiB (S2/R11 dumps). Before the burst both caches are filled to their
default caps (K = 100 + 50 MiB; physical ≈ 304 MiB with the shipped weigher, ≈ 141 MiB with the patched one, B7/R11).
With r and N fixed, the backlog's history is the same in every arm up to GC feedback, and the pre-burst live heap
differs by the cache gap: T (shipped) ≈ 164 MiB more than P (+104 B/entry charged, same K), ≈ 272 MiB more than E
(caches invalidated). N\* is placed so that T's peak demand is just above the heap and P's just below.

### 2.2 Protection map (fixed before readings; V's heap)

| Domain | Allocation, owner, release | Control C (contract) | K | U measured as | Lifetime / multiplicity |
|---|---|---|---|---|---|
| Local-write backlog (S2) | `Mutation` + `PartitionUpdate` + value `byte[]` decoded on `Native-Transport-Requests`, held by `StorageProxy$4` (`LocalMutationRunnable`) or its `HintRunnable` on `MutationStage` until applied | **none** (unprotected; here bounded by the fixed inflow N at rate r) | none (PendingTasks is a gauge) | pending log (200 ms), S2Poll 1 s; `Mutation` / `StorageProxy$4` in OOM dumps; heap after GC (gc.log) | transient; one per accepted, not yet applied local copy |
| Key cache | `KeyCacheKey` + key `byte[]` + `RowIndexEntry`, Caffeine `PSMW` node, `ConcurrentHashMap$Node`, table, sketch | `key_cache_size` auto = 100 MiB at 2 GiB (`maximumWeight`) | JMX `Cache.KeyCache.Size` | pre-burst forced-GC class histogram (B7 layout); pre-burst live T − P − E; dump counts | standing; table/sketch never shrink |
| Counter cache | `CounterCacheKey` + `byte[]` + `ClockAndCount`, same container | `counter_cache_size` auto = 50 MiB | JMX `Cache.CounterCache.Size` | same | standing |
| Memtables (`b6.t_blob`, `s2c`) | slab regions + partition objects (`heap_buffers`) | `memtable_heap_space` = ¼ heap = 512 MiB; flush at `memtable_cleanup_threshold` 1/3 | `MemtableOnHeapSize` | S2Poll; dump | standing, recycled at flush |
| Client request bytes | decoded requests in transport | `native_transport_max_request_data_in_flight` = heap/10 = 204.8 MiB (per IP heap/40) | transport counter | — | released at the first replica ack (before V's local write runs) |
| Outbound to R1/R2 | `Message` refs (same `Mutation`) in V's outbound queues | internode queue caps (4 MiB per link + 128 MiB per endpoint + 512 MiB global, on-wire) | queue bytes | — | transient |
| Remote hints | expired outbound copies written to V's hints buffers | hints buffers (direct) | `TotalHints` | S2Poll `hints_created` | transient |

Budget: V's Java heap, `-Xms = -Xmx = 2048 MiB`. Direct memory not claimed (heap OOM endpoint).

### 2.3 Configuration and budget audit

| Item | Value | Class |
|---|---|---|
| Nodes (checked read-only 2026-11-21 ≈ 01:53 EST) | Utah m400 (`jason92-326377`), each aarch64, 8 cores, 62 GiB RAM (≈ 61 GiB available), 8 GiB swap, Ubuntu 22.04, kernel 5.15, cgroup v2, OpenJDK 11.0.33; no Java process on any of the four. **V = `ms0611` 10.10.1.4** (`/mydata` 34 GiB free; `/mydata/r11` holds only `golden-V.tgz`, 46,144,288 B, md5 `cd69964e15b4…`; Linger=no), **R1 = `ms0625` 10.10.1.1** (29 GiB free; Linger=no), **R2 = `ms0617` 10.10.1.5** (36 GiB free; Linger=yes), **client = `ms0604` 10.10.1.3** (30 GiB free; Linger=no; holds `/mydata/s2r2`, `/mydata/u1r2` of other cases: never touched). Controller: the local node `pc96` (node0.jason92-325405), by `ssh`; the m400s cannot ssh to each other (relay `rsync` through `pc96`) | environment |
| Builds | `/mydata/s4/cassandra-base` jar md5: `ms0611` and `ms0617` `1becab414e5f…`, `ms0625` `beb4d0c1db2a…`, `ms0604` `a9b3ef8b9977…`; so, as R11, **orig** = `cp -a ms0611:/mydata/s4/cassandra-base` → `ms0611:/mydata/r19/run-orig`, relayed by `rsync -a` through `pc96` to `/mydata/r19/run-orig` on `ms0625`, `ms0617` and `ms0604` (the client's classpath); jar md5 equal on all four. **patched** = `ms0611:/mydata/r19/run-patched` = `cp -a` of run-orig + R11 `harness/b7-weigher-overhead.diff` (`git apply`), `ant jar` in that copy only; record jar md5 and that `CaffeineCache.class` contains `b7.entry_overhead`. V runs `patched` only in P arms; R1, R2 always `orig` | supporting (patched build = intervention only) |
| Work dirs | `/mydata/r19/` on the four nodes (`sudo mkdir /mydata/r19 && sudo chown jason92:misconfiguration /mydata/r19`: `/mydata` is root-owned); controller `pc96:/mydata/r19-evidence/`. `cp -p /mydata/r11/golden-V.tgz /mydata/r19/` on `ms0611` (md5 must equal `cd69964e15b4…`) | environment |
| JVM / GC | shipped `jvm-server.options` + `jvm11-server.options` (G1, `-XX:+HeapDumpOnOutOfMemoryError`, OOM → `kill -9`), `MAX_HEAP_SIZE=2G` on all three servers, `HEAP_NEWSIZE=256M` (ignored by G1); `MaxDirectMemorySize` resolved by `cassandra-env.sh` (R11: 15,872 MiB; record); gc.log with `time,uptime` decorations as written by `cassandra-env.sh` (R11 ran the same); dumps to the instance's `dumps/` | environment / budget |
| Memory scope | each server JVM in `systemd-run --user --scope -p MemorySwapMax=0` (no memory limit); `loginctl enable-linger` on `ms0611`, `ms0625` for the run, disabled again at the end (`ms0617` stays yes); the client JVM (`ms0604`, `-Xmx4g`) runs outside a scope, as R11's | environment |
| Topology (= R11 = S2 G1) | DC `c`, rack `r1`, `num_tokens: 1`; `initial_token` V −9223372036854775808, R1 −3074457345618258603, R2 3074457345618258602; seed `10.10.1.4:7000`; `GossipingPropertyFileSnitch`; `b6` `NTS {c:3}`, `t_blob (pk int PRIMARY KEY, b blob)`; `s2c` `NTS {c:1}`, `kv (k blob PRIMARY KEY, v int)`, `ctr (k blob PRIMARY KEY, c counter)` | environment |
| yaml diffs | exactly R11's `ctl.sh gen` (`cluster_name 'r11ring'` kept, because the golden system tables carry it; `num_tokens 1`, addresses, seed, snitch, dirs under `/mydata/r19/inst/<role>/`, `auto_bootstrap: false`, `initial_token`); per-instance `yaml.diff` saved | environment |
| Constraints (V6) | all at the shipped default, resolved at 2 GiB: `key_cache_size` 100 MiB, `counter_cache_size` 50 MiB, `memtable_heap_space` 512 MiB, `heap_buffers`, `concurrent_writes` 32, `native_transport_max_request_data_in_flight` 204.8 MiB, `native_transport_max_threads` 128, `write_request_timeout` 2 s, internode queue capacities, hints on, `commitlog_sync` periodic 10 s, key cache save period 4 h (no save in an arm) | default |
| Budget (V7) | heap 2,048 MiB on all three servers (≥ 512 MiB standing rule; 2 GiB ideal; the m400's auto heap would be 15.5 GiB). No container/cgroup memory limit | acceptable (no review needed) |
| Workload (burst) | S2 G1's write: blob 11,000 B (`new Random(1)`), `INSERT INTO b6.t_blob`, 8 driver sessions × 256 in flight, whitelist V only, CL=ONE, protocol V4; **rate cap r** (one Guava `RateLimiter` shared by the sessions; S2Load's 8th argument) and **total N** (`-Dtotal`); time cap `ceil(N / r) + 60` s. CL=ALL only in E-cal1 (§2.6) | experimental variable (r fixed after E-cal1; N the dial) |
| Cache fill (V only) | R11's `S2CacheFill` unchanged (key `mix64(i)` kept only if its token > 3074457345618258602; check `RANGEOK` of 1,000 kept / 1,000 rejected keys by driver metadata): `read kv 0..1,500,000` → `counter ctr 0..550,000` → `nodetool flush s2c`; concurrency 256, CL=ONE; client now on `ms0604` | workload |
| Golden data state | **V:** R11's `golden-V.tgz` (one compacted `kv` sstable, 1.6 M kept keys, ≈ 1.61 M partitions, system tables of the r11ring). **R1/R2:** their R11 tars were deleted, so stage 2 rebuilds them once (`golden-ring.sh`, §2.5) against the kept V state; fallback, if that ring does not come up clean: rebuild the whole golden state with R11's `golden.sh` (same keys, ≈ 5 min) and record it | environment (matched data state) |
| Instrumentation | **R11Gate** on V as a logger only (`G = 0`: reads `MutationStage` PendingTasks every 200 ms over local JMX, never sends STOP; `-Xmx32m`, nice 10); **S2Poll** on each server (1 s, nice 10; heap used, `mut_pending/active/done`, `self_dropped`, `hints_created/inprog`, memtable, caches); client per-second progress; pre-burst `jcmd GC.class_histogram` (forced full GC, before the load); heap dump on OOM (shipped option); gc.log. No agent inside the JVMs | disclosed |

### 2.4 Ceiling arithmetic and placement model (V, 2 GiB; before readings)

Terms (MiB), from R11's readings on this ring: pre-burst live L_T ≈ 394, L_P ≈ 230, L_E ≈ 122; memtable at the
burst M ≈ 167; heap usable at OOM H ≈ 2,030 (OOM arms: max after Full GC 99.0–99.3 %); per queued write s ≈ 28 KiB
(range 26–30).

| | T (shipped weigher) | P (+104 B/entry) | E (invalidated) |
|---|---|---|---|
| Room for the backlog H − L − M | ≈ 1,469 | ≈ 1,633 | ≈ 1,741 |
| Queued writes V can hold (room / s) | ≈ 53.7 k | ≈ 59.7 k | ≈ 63.7 k |
| Offset of the edge against E, in queued writes | −10.0 k | −4.0 k | 0 |
| … in sent writes (÷ f, f ≈ 0.65 = queued / sent at the peak; R11 cal2 0.68, cal4 0.65) | ≈ −15.3 k | ≈ −6.1 k | 0 |

Contract capacities alone: 512 + 100 + 50 + 204.8 = 867 MiB < 2,048 MiB, so no all-pools-full convergence; the OOM
needs the uncapped backlog (S2) and, at N\*, the uncounted cache memory (B7). The T–P window is ≈ 6.0 k queued ≈ 9.2 k
sent writes (164 MiB). **Placement:** N\* is the midpoint between T's and P's edges = E's edge − ((L_T + L_P)/2 − L_E)
/ (s · f) = E's edge − 190 MiB / (28 KiB × 0.65) ≈ **E's edge − 11,000 sent writes**. Known weakness: R11's T survived
with max pending 65.9 k (> 53.7 k), so s per pending write is below 28 KiB at the peak or pending includes short-lived
entries; the arithmetic sets only the offset, and E's edge itself is measured.

**Rate.** a_E is measured (E-cal1, CL=ALL: the client waits for V's own write, so the completed rate is V's apply
capacity with the coordination load included; S2 G1 CL=ALL: 3.65 k/s). r = round₁₀₀(1.2 × a_E), predicted 4,000–4,700
writes/s; if 1.2 × a_E > 4,700 (R11's uncapped CL=ONE offered rate, at which a cap would not bind), r = 4,700 and r / a_E
is recorded. **Predicted edges at r ≈ 4.4 k/s:** E's edge N ≈ 125–170 k sent (R11's uncapped T edge 101–142 k plus T − E
≈ 15 k, plus a little because V applies more of a slower burst); N\* ≈ 115–160 k; burst length N\* / r ≈ 26–36 s.

**Why the fixed inflow should separate T and P better than R11's gate.** R11's outcomes split by burst length (≤ 21 s
survived, ≥ 48 s died) because the gate fired at very different times. Here N and r fix the burst length; the
remaining spread is V's apply rate during the burst (GC). The design does not assume that spread is below the 9.2 k
window: it compares OOM rates over ≥ 5 + 5 arms and reads heap after GC at STOP, where T − P ≈ 164 MiB is visible as a
shift even when single arms cross the edge by chance.

### 2.5 Harness (stage 2 builds it under `harness/`; copy R11's, change only what is listed)

Node layout: `/mydata/r19/{run-orig, run-patched (V only), inst, golden-<role>.tgz, runs, dumps, h, cls}`; controller
`pc96:/mydata/r19-evidence/{runs/<arm>/, batch.log, dumps}`; excerpts in `logs/`.

| File | From | Change |
|---|---|---|
| `ctl.sh` | R11 `harness/ctl.sh` | root `/mydata/r19`; `restore` untars `/mydata/r19/golden-<role>.tgz`; otherwise unchanged (start in the swap-0 scope, stop by PID, 30 s then `kill -9`) |
| `golden-ring.sh` (new, ≈ 25 lines, from R11 `golden.sh`) | — | once: `restore V` (orig) from `golden-V.tgz`; `gen` R1 and R2 fresh (orig, 2 GiB); start V, then R1, R2; wait `UN = 3` and one schema version in `nodetool describecluster` (≤ 5 min); check on V `tablestats s2c.kv` ≈ 1.61 M partitions, 1 sstable, and `describering s2c`; `nodetool drain` R1, R2, V; stop; tar R1/R2 `data commitlog hints` (saved_caches emptied) to `golden-R1/R2.tgz`. Failure → fallback: R11 `golden.sh full` with `/mydata/r19` paths (rebuilds all three tars from the same keys), recorded |
| `S2Load.java` | R11 `harness/S2Load.java` | keep the rate argument and `-Dtotal`; no `-Dgate` in this case; print `TOTAL_REACHED t=<ms since first send> sent= epochMs=` when the last ticket is taken, and a progress line every 1 s (`t= sent= ok= err= inflight= rate1s=`) instead of every 5 s |
| `client.sh` | R11 | `W=/mydata/r19`; runs on `ms0604`; `load` passes `CL` (default ONE) |
| `R11Gate.java`, `S2Poll.java`, `sample.sh`, `S2CacheFill.java`, `vstate.sh`, `gcpeak.sh`, `gcwin.py`, `hprofhist.py`, `dumpparse.sh`, `logback-load.xml`, `b7-weigher-overhead.diff` | R11 harness | paths `/mydata/r19` and the client host only |
| `arm.sh` | R11 `harness/arm.sh` | `arm.sh <name> <T\|P\|E> <N>` with env `RATE` (r; empty = uncapped), `CL` (default ONE), `LOADCAP` (default `ceil(N/RATE)+60`); client commands on `ms0604`; gate started with `G = 0`; step 9 runs `client.sh load run blob 11000 256 $LOADCAP 0 <10.10.1.4 × 8> $RATE` with `-Dtotal=N` (omitted when N = 0); step 10 observation from the client's exit: dead / drained (pending ≤ 1,000 for 30 s) / **300 s**, extended once by **180 s** if alive with pending > 1,000, then `UNRESOLVED`; collect adds `hstop.py` |
| `hstop.py` (new, ≈ 40 lines) | — | from V's gc.log (`time` decoration; if absent, uptime + the JVM start epoch from `jcmd VM.uptime` recorded at arm start) and the client's `TOTAL_REACHED epochMs`: **h_stop** = heap after GC of the last pause that ends at or before STOP + 5 s (MiB); also max heap after any GC and after Full GC within [first send, STOP + 15 s], and seconds from first send / from STOP to the first OOM mark (`HeapDumper` / `ReportJavaOutOfMemory` safepoint) |
| `table.py` | R11 | columns: type, r, N, V outcome, time to STOP and achieved rate, sent/ok/err, max pending (200 ms), self-drops / hints, pre-burst live, K and entries, h_stop, max after any GC / after Full GC, worst-60 s STW, OOM mark after first send / after STOP, R1/R2 max pending and max after GC, dump `Mutation` / `PSMW` |

**Arm procedure** = R11 §2.5 steps 1–12 (clean slate; restore V (`BUILD` per type), R1, R2; start; `UN = 3` ≤ 5 min
else `RINGFAIL` void; record command line, resolved `-Xmx`, `MaxDirectMemorySize`, cache capacities; samplers and
gate logger; fill; fill validity key ≥ 99.0 MiB and counter ≥ 49.5 MiB (one refill, then `FILLFAIL` void); E only:
invalidate both caches and check 0; pre-burst `nodetool info`, `tablestats`, forced-GC histogram, 10 s idle; burst;
observation; collect; table row), with the burst and observation of the table above.

**Endpoint, per arm** (as R11). **Heap OOM** = V dead and at least one of: `HeapDumper` or `ReportJavaOutOfMemory`
safepoint in gc.log, `java.lang.OutOfMemoryError` in system.log/launch.log (skip `CompileCommand` lines), a dump written
by `HeapDumpOnOutOfMemoryError`. **Survive** = V alive and drained. **Unresolved** = alive, not drained at the end of
the extended window. V dead without OOM evidence = **void** (not counted). GC service loss (protocol default) is
recorded, not the endpoint. **Inflow validity:** an arm in which V stays alive but the client sent < 0.98 N by the time
cap is `LOADSHORT` (void); an arm whose V dies before STOP counts as OOM (its sent count recorded); an arm whose STOP
came later than 1.25 × N / r after the first send is counted but flagged `slow inflow` (V's GC slowing its own
coordination is part of the mechanism; reported per type).

**Shakedown** (not a reading, ≤ 10 min, after `golden-ring.sh`): `RATE=4000 FILL_SMALL=1 arm.sh shake T 20000` on the
full golden state: ports, ring `UN = 3`, schema, `RANGEOK`, rate cap held (progress lines), `TOTAL_REACHED`, sampler
and gate-logger columns, `hstop.py` output, collection, cleanup. Fix the harness, never the design.

### 2.6 Calibration (E first; then one T placement check), all at 2 GiB on the three servers

1. **E-cal1 — V's apply rate.** `CL=ALL LOADCAP=60 arm.sh ecal1 E 0` (N = 0: no total; uncapped, 60 s). **a_E** = successful writes ÷
   seconds from first to last ok. Prediction: a_E 3.3–3.9 k/s (S2 G1 CL=ALL 3.65 k/s); V survives, max heap after any
   GC ≤ 40 %, pending ≤ 500. Set **r = round₁₀₀(1.2 × a_E)**, capped at 4,700 (§2.4). If V OOMs here or a_E < 2,000/s,
   stop: verdict `retry` (the ring does not behave as R11's/S2's).
2. **E-cal2 — E at (r, N = 140,000).** Prediction: survive with h_stop ≈ 1,750–1,950 MiB, or OOM near the edge.
3. **E-cal3:** N = 170,000 if E-cal2 survived, N = 110,000 if it died.
4. **E-cal4 (optional, if the clock allows, §2.9):** the midpoint of the bracket if E-cal2/3 formed one (survive at
   N_s, OOM at N_o = N_s + 30 k → N = N_s + 15 k); if they did not, one more 30 k step in the same direction (200 k or
   80 k). Then **E's edge N_E** = midpoint of (highest N where E survived, lowest N where E died); if all E arms at r
   survived, N_E = highest + 15 k; if all died, N_E = lowest − 15 k (one-sided, recorded). If E survives at 200 k or
   dies at 80 k, stop: verdict `retry` (the rate does not place the edge in a usable range).
5. **N\*₀ = round₁ₖ(N_E − 11,000)** (§2.4).
6. **T-chk — T at (r, N\*₀)**, not counted: T survives with max heap after any GC < 1,950 MiB (95.2 %) → **N\* = N\*₀ +
   8,000**; T dies before STOP → **N\* = N\*₀ − 8,000**; otherwise (T dies after STOP, or survives at ≥ 95.2 %) **N\* =
   N\*₀**. One adjustment only.
7. Stage 2 writes r, a_E, N_E and N\* into §3 as a dated amendment **"N\* fixed"** before the first counted arm.
   Calibration arms are not counted. Readings per E arm also give f (max 200 ms pending ÷ N) and the backlog growth
   rate; they are reported, not used to move N\* (the 11 k offset is frozen).

### 2.7 Counted arms, predictions, controls, intervention and decision rule

All at (r, N\*), 2 GiB on all three servers, clean starts from the golden state, interleaved in this order:
`T1 P1 E1 T2 P2 T3 P3 E2 T4 P4 E3 T5 P5` (13 arms).

| Arm | Role | Prediction (before readings) |
|---|---|---|
| T (orig, caches at caps) ×5 | endpoint (V1) | heap OOM **4–5 of 5**, OOM mark within 120 s of STOP (some before STOP); pre-burst live 385–405 MiB; h_stop ≥ 1,980 MiB or censored (died before STOP); dump: ≈ 48–60 k `Mutation` (`StorageProxy$4` + local `HintRunnable` wrappers), `PSMW` ≈ 1.78 M, `KeyCacheKey` 1,310,720, `CounterCacheKey` 468,114 |
| P (patched weigher, caches at caps by K) ×5 | intervention (V4): removes only the uncounted ≈ 164 MiB at the same K, r, N | survive **4–5 of 5** (drained within the window); pre-burst live 220–240 MiB (T − P 150–175); h_stop ≈ T's − 164 ± 60 MiB, ≈ 1,820–1,900; `PSMW` ≈ 812 k; achieved rate and sent at STOP within 5 % of T's |
| E (orig, caches filled then invalidated) ×3 | matched control (V2): the holder alone at the same r, N | survive **3 of 3**; pre-burst live 115–135 MiB; h_stop ≈ T's − 272 ± 60 MiB, ≈ 1,700–1,790 |

Matched across arms: build and yaml (P differs only in the weigher of `CaffeineCache.create(long)`, whose only callers
are the key and counter caches), heaps, topology, nodes, golden data, fill (E differs only in the two invalidations),
r, N\*, client and its node. Recorded per arm for matching: time to STOP, achieved rate, sent/ok/err, max pending,
self-drops, hints, memtable on-heap, R1/R2 max pending and max after GC.

**Decision rule (frozen; t, p, e = OOM counts of T, P, E at N\*).** `UNRESOLVED` counts as *not OOM* for T and as *not
survived* for P and E (conservative both ways); void arms are re-run in the same slot if the clock allows, else the n
is reported.

| Outcome (n_T = n_P = 5, n_E = 3) | Verdict / action |
|---|---|
| t ≥ 4, p ≤ 1, e = 0, and median h_stop(T) − median h_stop(P) ≥ 100 MiB (OOM-censored T values count as 2,048) | proposed `verified-OOM · deployment`, mixed (S2 unprotected accumulation + B7 accounting gap) → **true positive** (Fisher one-sided p for 4/5 vs 1/5 = 0.10, 4/5 vs 0/5 and 5/5 vs 1/5 = 0.024, 5/5 vs 0/5 = 0.004; reported) |
| t − p = 2 or 3 but not the row above (e.g. 3/5 vs 0/5, 4/5 vs 2/5, 5/5 vs 2/5) and e = 0 | **extend**: more T/P pairs at the same N\* while the clock allows (§2.9), to at most 8 + 8; then true positive only if t/n_T ≥ 0.75, p/n_P ≤ 0.25, e = 0 and the h_stop shift ≥ 100 MiB; otherwise **retry** (state the rates) |
| p ≥ 3 (P dies as often as T) | **retry**: the gap does not decide the OOM at N\*; record the h_stop shift (if ≈ 164 MiB with equal rates, propose to the owner that the B7 line be closed as "gap real, not decisive at 2 GiB") |
| t ≤ 2 | **retry**: N\* below T's edge (placement); report h_stop of the three types |
| e ≥ 1 | **retry**: the matched control does not hold at N\* (V2 unmet) |
| counted set incomplete when the clock stops it | **retry** (incomplete), with what ran |

`false positive` is not a reachable outcome of this design: the endpoint is already reached at defaults on this ring
(S2, R11); the question is only whether the cache gap decides it.

**Continuous reading (reported in every outcome).** Per type: h_stop (median, range), pre-burst live, max heap after
any GC; the T − P and T − E shifts against the predicted 164 and 272 MiB; as a secondary check, h_stop against V's
pending at STOP (one common slope, separate intercepts per type: the intercept T − P should be ≈ 164 MiB). Time to OOM
after STOP for the OOM arms (not a decider: S2 showed 62–460 s spread under thrash).

**Budget search.** 2 GiB is the planned budget. An upward probe (one T and one P with all three heaps at 4 GiB, the
same r, N = 2.5 × N\*: the backlog room at 4 GiB is ≈ 2.4× that at 2 GiB) runs only if ≥ 35 min remain before 06:45 after the counted arms and any extension; n = 1 each, a
boundary probe, not a verified condition. Otherwise the case states "largest failing budget searched = 2 GiB; S2 G1 at
4 GiB alone 0/6 at 97–98 % live".

### 2.8 Instruments (U independent of K)

- **Backlog U:** pending log (200 ms), S2Poll `mut_pending` / `mut_done` / `self_dropped` / `hints_inprog` /
  `hints_created` (1 s, no forced GC); `Mutation`, `StorageProxy$4`, `WriteResponseHandler`, `byte[]` in OOM dumps
  (`hprofhist.py` on `pc96`).
- **Cache U:** class counts × shallow sizes from the pre-burst forced-GC histogram (`PSMW`, `ConcurrentHashMap$Node`,
  `KeyCacheKey`, `CounterCacheKey`, `ClockAndCount`, `RowIndexEntry`, key `byte[]`); pre-burst live T − P, T − E. K
  from JMX `Size` / `nodetool info`.
- **Heap:** gc.log (`gcpeak.sh`, `gcwin.py`, `hstop.py`); MemoryMXBean used every 1 s (S2Poll).
- **Inflow:** client progress every 1 s (sent, ok, err, in flight, rate), `TOTAL_REACHED`, `FINAL`.
- **Initiating failure (V5):** gc.log safepoint marks; first `OutOfMemoryError` with its thread from system.log or
  launch.log; the dump histogram of every counted T OOM and of any P/E OOM (parsed on `pc96` during later arms).
- **Overhead:** gate logger (32 MiB JVM, one JMX read / 200 ms) and S2Poll (1 s) at nice 10 on V, the same in every
  arm; forced GC only before the burst.

### 2.9 Time plan and stopping budget (America/New_York, 2026-11-21; window 03:00–07:30)

Arm length on this ring (R11): restore + ring ≈ 1.5–2.5 min, fill ≈ 2.5 min, histogram + idle ≈ 0.7 min, burst
0.5–0.7 min, observation 0.7 min (drained) to 5 min (OOM after thrash; window 300 s + 180 s), collect ≈ 1.5 min ≈
**8–10 min, worst ≈ 15**. E-cal1 (60 s, no OOM expected) ≈ 7 min.

| Window | Work |
|---|---|
| 03:00 – 03:40 | check the freeze hash; nodes (`ps`, `free`, `df`, Linger); `/mydata/r19` on the four nodes; builds (copy, relay, md5, `ant jar` in run-patched); copy `golden-V.tgz`; harness copy + changes + compile on the four nodes; `golden-ring.sh` (≈ 5 min; fallback ≈ 8 min); shakedown |
| 03:40 – 03:48 | E-cal1 (CL=ALL) → r |
| 03:48 – 04:20 | E-cal2, E-cal3 (+ E-cal4 if started by 04:15) → N_E |
| 04:20 – 04:32 | T-chk → amendment "N\* fixed" |
| 04:32 – 06:35 | 13 counted arms (≈ 9.5 min each) |
| 06:35 – 06:45 | extension pairs (decision rule row 2) or the 4 GiB probe; **no arm starts after 06:45** |
| ≤ 07:00 | every process the run started stopped (three `CassandraDaemon`, gate logger, samplers, client); `loginctl disable-linger` on `ms0611`, `ms0625`; dumps parsed or left on the node and named |
| ≤ 07:30 | §3, §4 and the write-backs (playbook stage 2 step 5) |

**Hard limits and checkpoints.** No arm starts after 06:45; whatever runs at 07:00 is stopped. At most 20 arm
executions. Calibration has no arm-count cap, but **the first counted arm starts by 04:50**: E-cal4 is skipped if it
could not start by 04:15, and T-chk is skipped if it could not start by 04:35 (then N\* = N\*₀). If counted arms start
after 04:50, the order stays as frozen and an incomplete set is `retry` (§2.7). No escalation after an OOM beyond the
planned arms.

**Drop order when behind** (first dropped first): the 4 GiB probe → extension pairs → T-chk → E-cal4 → (counted arms are
never reduced below 5 T, 5 P, 3 E; if they cannot finish, the verdict is `retry`, incomplete).

**Resources and disk.** Per server node one 2 GiB JVM (+ ≈ 1–2 GiB off-heap); the client (4 GiB heap) alone on
`ms0604`. Disk on V: builds ≈ 1 GB, golden 46 MB, `b6` data and commit log ≤ 3 GB per arm (wiped by the next restore),
dumps 2.2 GB each: keep the first counted T dump and the first P or E OOM dump on V, delete the others after their
histogram is on `pc96` (≤ 10 GB of 34 GiB free).

### 2.10 Limits known before the run

- A rate-capped CL=ONE burst of fixed size is an ordinary client workload; the overload is that r exceeds V's apply
  rate by ≈ 20 %. The researcher may rule on whether such a burst is an accepted workload (as for S2).
- The placement offset (11 k sent writes) comes from R11's per-write arithmetic, which overestimated per-pending
  heap; T-chk corrects it once. A misplaced N\* shows as t ≤ 2 or p ≥ 3 and ends in `retry`, not in a false claim.
- With 5 + 5 arms only large rate differences are significant (best case p = 0.004); the h_stop shift is the second,
  continuous line of evidence.
- The intervention charges 104 B/entry, an upper bound on this layout (B7: U/C 0.93–0.95), so it removes slightly
  more than the gap; K is the same in T and P. R11 measured the same per-entry layout on aarch64.
- The m400 ring and its golden state are shared with no other run during the window; `ms0604`'s other folders are not
  touched.

`sha256 of §1–§2 at freeze: 10dcb2406bb53128984a2360a3f53ac1cacccc246031720aa6c59ee0ad088fac` (UTF-8 bytes from the line `## 1. Candidate` through the line before this one, each line ending in `\n`; frozen 2026-11-21 02:00 EST) · amendments after the freeze: none in §1–§2; stage-2 records (F1 fallback, H1 harness fix, r fixed, calibration stop, D declaration) in §3.0.

## 3. Runs (stage 2)

Stage 2: a fresh phase-2 OOM agent (Claude Opus 5.5, subagent), 2026-11-21 from 02:00 EST. Freeze hash checked at
02:01: `10dcb240…0ad088fac` (matches). The design ran as frozen from 02:00 (earlier than §2.9's 03:00 start; the
window's limits — no arm after 06:45, all stopped and written by 07:30 — were kept).

### 3.0 Amendments and design-listed fallbacks (dated, each before the readings it affects)

- **F1 (2026-11-21 02:09 EST, golden state; the fallback §2.3/§2.5 names, not an amendment).** `golden-ring.sh`
  restored V from R11's `golden-V.tgz` and generated R1/R2 fresh; both replicas refused to join (`A node with address
  /10.10.1.1:7000 already exists, cancelling join. Use cassandra.replace_address`): V's system tables remember R11's
  R1/R2 host IDs. As §2.5 directs, the whole golden state was rebuilt with R11's `golden.sh full` (paths `/mydata/r19`,
  client `ms0604`): 1,600,000 kept `kv` keys inserted in 66.2 s (24.2 k/s), `RANGEOK kept=1000 rejected=1000`, one
  compacted sstable on V (53.2 MB, ≈ 1,614,344 partitions; R11: 53.3 MB, ≈ 1.61 M), `describering s2c`: V owns
  (3074457345618258602, −2^63]. New tars: `golden-V.tgz` 46,104,149 B, `golden-R1.tgz` 66,949 B, `golden-R2.tgz`
  67,320 B. Same keys and procedure as R11's state, so the matched data state holds across all R19 arms.
  [`logs/golden-ring-failed.log`](logs/golden-ring-failed.log), [`logs/golden-full.log`](logs/golden-full.log).
- **H1 (2026-11-21 02:18 EST, shakedown; harness fix, no design change).** `S2Load` created its `RateLimiter` before
  the 8 sessions connected, so Guava's bursty limiter had stored 1 s of permits and the first second ran at ≈ 2 r
  (shake: 6,195 sent in the first 1.0 s at r = 4,000; 20,000 in 4.0 s = 4,994/s). The limiter is now created just
  before the send threads start. `TOTAL_REACHED` is printed when the N-th write is *sent* (the inflow end), not when
  the N-th ticket is taken (a ticket can precede its send while the 256 in-flight slots are full).
- **r fixed (2026-11-21 02:27 EST, after E-cal1, by the frozen rule §2.4/§2.6 step 1).** E-cal1 (CL=ALL, uncapped, 60 s):
  266,250 ok in 61.66 s from first to last ok → **a_E = 4,318 writes/s** (predicted 3.3–3.9 k/s; S2 G1 3.65 k/s).
  1.2 × a_E = 5,182 → round₁₀₀ 5,200 > 4,700, so **r = 4,700** (the cap of §2.4); **r / a_E = 1.09**. Neither stop
  condition of step 1 holds (V survived; a_E ≥ 2,000).
- **Calibration stop (2026-11-21 02:52 EST, §2.6 step 4).** E survived at r = 4,700 with N = 140,000 (E-cal2),
  170,000 (E-cal3) and 200,000 (E-cal4). Step 4: "If E survives at 200 k … stop: verdict `retry` (the rate does not
  place the edge in a usable range)." N_E, N\*₀ and N\* were never fixed; T-chk and the 13 counted arms did not run;
  the 4 GiB probe (after the counted arms only) did not run.
- **D (2026-11-21 02:55 EST, declared before any reading; diagnostic arms outside the design, not counted, no effect on
  the verdict).** With ≈ 3.8 h left before 06:45, at most three E arms on the same harness, golden state and fill,
  to tell the retry design which inflow places E's edge in range: **D1** E, uncapped CL=ONE, N = 200,000 (the
  offered rate with the client on a fourth node; R11's uncapped E, client on R2's node, died at 232 k);
  **D2** E, r = 5,200 (round₁₀₀(1.2 × a_E), the value §2.4's 4,700 cap replaced), N = 200,000; **D3** only if D1 died
  and D2 survived: E, r = 6,000, N = 200,000. No T or P arm; all stopped by 03:45.

### 3.1 Environment (as run)

| Item | Value |
|---|---|
| Nodes | V `ms0611` 10.10.1.4, R1 `ms0625` 10.10.1.1, R2 `ms0617` 10.10.1.5, client `ms0604` 10.10.1.3; Utah m400 `jason92-326377`, aarch64, 8 cores, 62 GiB, 8 GiB swap (0 used), SSD (`sda` ROTA 0), kernel 5.15.0-191, cgroup v2, OpenJDK 11.0.33. All four idle at 02:01 EST (no `CassandraDaemon`, no Java of the user). Linger was no / no / yes / no; enabled on `ms0611` and `ms0625` at 02:04 for the run, disabled again at the end (`ms0617` stays yes, `ms0604` untouched). `/mydata/s2r2`, `/mydata/u1r2` (and `ms0625`'s `b8`, `oom-smoke`) not touched. Controller `pc96` (node0.jason92-325405, the local node) |
| Work dirs | `/mydata/r19/` on the four nodes (`sudo mkdir` + `chown jason92:misconfiguration`); controller `pc96:/mydata/r19-evidence/` (`runs/<arm>/`, `batch.log`, `h/`) |
| Builds | **orig** = `cp -a ms0611:/mydata/s4/cassandra-base` → `ms0611:/mydata/r19/run-orig` (jar md5 `1becab414e5f…`), relayed by `rsync` through `pc96` to `ms0625`, `ms0617`, `ms0604`: md5 `1becab414e5f…` on all four. **patched** = `ms0611:/mydata/r19/run-patched` = copy of run-orig + `harness/b7-weigher-overhead.diff` (`git apply`, 1 file), `ant jar` 39 s, BUILD SUCCESSFUL, jar md5 `da329b3ef099…`, `CaffeineCache.class` contains `b7.entry_overhead` (orig's does not). Never started: no P arm ran |
| JVM / budget (V, every arm) | `-Xms2G -Xmx2G -XX:+UseG1GC`; **`MaxDirectMemorySize` resolved by `cassandra-env.sh` = 15,872 MiB** (`-XX:MaxDirectMemorySize=15872M`; VM.flags 16,642,998,272 B); scope `memory.max = max`, `memory.swap.max = 0`; key cache capacity 100 MiB, counter cache 50 MiB, row cache 0 (system.log). R1/R2: the same heap, build orig |
| yaml diff | exactly §2.3 (`cluster_name 'r11ring'`, `num_tokens 1`, addresses, seed 10.10.1.4, GPFS snitch, dirs under `/mydata/r19/inst/<role>/`, `auto_bootstrap: false`, `initial_token`); `logs/<arm>/V-yaml.diff` |
| Golden state | rebuilt by the §2.5 fallback (F1): 1.6 M kept `kv` keys, one compacted sstable on V (53.2 MB, ≈ 1.61 M partitions) |
| Fill (per full arm) | read 1,500,000 kv in 99–104 s (≈ 15 k/s), counter 550,000 in ≈ 50 s; `RANGEOK kept=1000 rejected=1000` every time; fill validity met on the first pass in every arm (key 100.00 MiB, counter 50.00 MiB); E invalidation → 0 / 0 |
| Harness | [`harness/`](harness/): R11's files with `/mydata/r19` paths and the client on `ms0604`; `S2Load.java` (rate cap + `-Dtotal`, `TOTAL_REACHED`, 1 s progress, H1), `arm.sh` (`<name> <T\|P\|E> <N>`, env `RATE`, `CL`, `LOADCAP`; gate as logger `G = 0`; observation 300 s + 180 s), `batch.sh` (no start ≥ 06:45), `hstop.py`, `table.py`, `golden-ring.sh` (failed, F1), `golden.sh` (fallback), `dumpparse.sh` (keeps at most one dump), `excerpt.sh` (case-folder excerpts) |

**Shakedown** (`RATE=4000 FILL_SMALL=1 arm.sh shake T 20000`, 02:13–02:18, not a reading): ring UN = 3 in ≈ 95 s,
`RANGEOK`, fill 20 k + 20 k, `TOTAL_REACHED` at 4.0 s, V drained, gate-logger and sampler columns present,
`hstop.py` and `table.py` rows produced, all stopped. It showed the stored-permit burst fixed by H1.
[`logs/shake/`](logs/shake/)

### 3.2 Calibration arms (§2.6) and diagnostic arms (D), 2026-11-21 02:18–03:20 EST

All E (caches filled to 100 + 50 MiB, then invalidated to 0 / 0), clean starts from the golden state, 2 GiB on all three
servers, 8 × 256 in flight to V, client on `ms0604`. None is a counted arm. "STOP" = the client's `TOTAL_REACHED` (N-th
write sent). Pending = V `MutationStage` PendingTasks from the 200 ms logger. h_stop = heap after the last GC pause
ending at or before STOP + 5 s (`hstop.py`); max after any GC / after Full GC over [first send, STOP + 15 s]
(D1: to death). Pre-burst live = forced-GC histogram total.

| Arm | Inflow (r, N, CL) | V outcome | STOP at, achieved rate | Sent / ok / err | Max pending (at) | Self-drops / hints | Pre-burst live | h_stop | Max after any GC; Full GCs, max after Full | Worst 60 s STW | R1 / R2 max pending; max after Full | OOM evidence, dump |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `ecal1` | uncapped, 60 s, **CL=ALL** | survive (drained) | — (60 s cap); oks 61.66 s → **a_E 4,318/s** | 266,857 / 266,250 / 607 (`WriteTimeout` at ALL) | 323 | 121 / 533 | 122 MiB | — | 2,010 MiB (98.1 %, young evacuation failures); 5, 625 MiB (30.5 %) | 4 % | 170 / 224; 335 / 422 MiB | — |
| `ecal2` | 4,700, 140,000, ONE | survive (drained) | 29.7 s, 4,718/s | 140,000 / 140,000 / 0 | 21,036 (+27.5 s) | 14,930 / 74 | 120 MiB | **686 MiB** | 1,991 MiB; 3, 860 MiB (42.0 %) | 3 % | 8 / 17; 424 / 348 MiB | — |
| `ecal3` | 4,700, 170,000, ONE | survive (drained) | 36.0 s, 4,718/s | 170,000 / 170,000 / 0 | 6,213 (+27.7 s) | 0 / 0 | 120 MiB | **857 MiB** | 2,007 MiB; 3, 716 MiB (35.0 %) | 3 % | 22 / 4; 439 / 468 MiB | — |
| `ecal4` | 4,700, 200,000, ONE | survive (drained) | 42.4 s, 4,718/s | 200,000 / 200,000 / 0 | 6,393 (+11.2 s) | 0 / 0 | 121 MiB | **927 MiB** | 1,993 MiB; 3, 622 MiB (30.4 %) | 3 % | 2,448 / 2,020; 434 / 346 MiB | — |
| `D1` (diag.) | uncapped, 200,000 (120 s cap), ONE | **heap OOM** | never (client stalled at 155,603 sent, 2,048 in flight) | 155,603 / 153,547 / 2,056 | 59,919 (+34 s; logger starved after) | 81,778 / 35,270 | 121 MiB | censored | 2,044 MiB; 279, 2,031 MiB (99.2 %); service loss MET (124 s ≥ 90 %) | 99 % | 4,887 / 10,709; 496 / 489 MiB | `HeapDumper` 125.5 s after first send, `ReportJavaOutOfMemory` 158 s; no `OutOfMemoryError` line (logs starved); dump: 60,208 `Mutation` = `StorageProxy$4` = `WriteResponseHandler`, `byte[]` 1,811 MiB of 2,053 MiB; deleted after parsing |
| `D2` (diag.) | 5,200, 200,000, ONE | survive (drained) | 38.4 s, 5,208/s | 200,000 / 200,000 / 0 | 41,484 (+38 s) | 70,791 / 14 | 120 MiB | **928 MiB** (+3.9 s) | 1,991 MiB; 8, 1,361 MiB (66.5 %) | 7 % | 96 / 3,996; 554 / 559 MiB | — |
| `D3` (diag.) | 6,000 (binds at 2,048 in flight: achieved 5,307/s), 200,000, ONE | survive (drained) | 37.7 s, 5,307/s | 200,000 / 200,000 / 0 | 56,589 (+38 s, at STOP) | 101,899 / 5,786 | 121 MiB | **1,994 MiB (97.4 %)** | 1,994 MiB; 15, **1,932 MiB (94.3 %)** | 15 % | 1,557 / 4,631; 531 / 518 MiB | — |

Readings across the arms:
- **At r = 4,700 the S2 backlog does not build.** V's pending stayed ≤ 6.4 k at N = 170 k and 200 k (two short
  spikes per arm, back to ≈ 0 within 1–2 s), ≤ 21 k at 140 k (two ramps of ≈ 5 s, each collapsing at a self-drop
  burst); live heap after Full GC ≤ 860 MiB; h_stop 686 → 857 → 927 MiB, growing ≈ 4 MiB per 1,000 extra writes
  (memtable and young garbage, not queued writes: pending ≈ 0 at STOP). V's CL=ONE apply rate is above 4.7 k/s; the
  CL=ALL arm (a_E 4,318/s) underestimated it — at CL=ALL every write also waits on R1 and R2, which were themselves in
  evacuation-failure young GCs (100 % after young pauses on both replicas in every arm).
- **The backlog builds only when the inflow exceeds ≈ 5.2 k/s or comes in bursts.** D2 (5,208/s smooth) reached 41 k
  pending and 1,361 MiB after Full GC; D3 (nominal 6,000, achieved 5,307/s because the 2,048 in-flight slots filled;
  per-second sends 2.4–9.7 k, sd 2.2 k) reached 56.6 k pending at STOP and 1,932 MiB after Full GC — E at its edge
  with 2 % of heap to spare. D1 (uncapped: the first 5 s at 5.5–7.5 k/s, per-second sends sd 2.7 k, max 9.7 k) had
  30 k pending by +6 s, never drained, and died (OOM, 155,603 sent). Same N-range, same E state: one OOM, one survivor
  at 97 %, so the outcome near the edge is set by the first seconds' burst shape, not by N alone.
- **Self-drops shed the backlog.** In `ecal2`, 14,930 self-drops left only 74 hints and pending fell from 21 k to 90
  within 1 s. `enforce_native_deadline_for_hints` is `false` by default, so each self-dropped local copy is re-queued
  as a `HintRunnable` (`StorageProxy.java:2640–2654`), which re-runs the local write; `TotalHints` counts hint files
  written for remote replicas only, so it does not count these re-queues. Why pending still collapses (R11's open
  question) is not resolved here either.
- **Holder confirmed again** (D1): the OOM dump holds 60,208 queued local writes (`StorageProxy$4`) with 1.81 GiB of
  `byte[]` — S2's holder, as in R11 cal1 / cal3 / cal5.

Raw logs: `pc96:/mydata/r19-evidence/runs/<arm>/{arm.log,obs.log,hstop.txt,V,R1,R2,client}` and on each server node
`/mydata/r19/runs/<arm>/`. Excerpts: [`logs/<arm>/`](logs/) (`arm.log`, `*-outcome.txt`, `hstop.txt`, `load.txt`,
`gate-pending-1s.txt`, `V-poll-burst.txt`, `R*-poll-pending.txt`, `hist-pre-top.txt`, D1 `dump-hist.txt`),
[`logs/batch.log`](logs/batch.log) (rows by `table.py`), [`logs/batch-runner.log`](logs/batch-runner.log).

### 3.3 Counted arms (§2.7)

Not run: the calibration stop (§3.0) came first. No T, P, T-chk, extension pair or 4 GiB probe ran; the patched
build was never started. Largest failing budget searched: 2 GiB (D1, holder alone, uncapped; R11 and S2 G1 the same).

### 3.4 Cleanup (2026-11-21 03:21 EST)

Every process the run started is stopped (no `CassandraDaemon`, S2Poll, sampler, gate logger or client of the user on
the four nodes; no `r19-*` scope); last-instance data (`/mydata/r19/inst`) deleted on the three servers; the one heap
dump (D1) deleted after parsing. Linger disabled again on `ms0611` and `ms0625` (both `no`, as found); `ms0617` stays
`yes`, `ms0604` `no` (untouched). Left (all stopped data): **`ms0611` `/mydata/r19` 1.1 GB** (run-orig 469 MB,
run-patched 469 MB, golden-V.tgz 44 MB, runs 50 MB, harness); **`ms0625` 479 MB** (run-orig, golden-R1.tgz 68 KB,
runs 9.7 MB); **`ms0617` 479 MB** (run-orig, golden-R2.tgz 68 KB, runs 9.9 MB); **`ms0604` 469 MB** (run-orig, cls,
runs 160 KB); `pc96:/mydata/r19-evidence` 70 MB. `/mydata/r11` on `ms0611` (R11's golden-V.tgz) untouched.


## 4. Conclusion (stage 2)

**Verdict: retry.** Protocol status: `candidate` (V1–V5 not reached: no counted arm; the design's own calibration stop,
§2.6 step 4, "E survives at 200 k → stop, verdict `retry`"). Direction as designed: mixed (S2 unprotected accumulation
+ B7 accounting gap); neither their convergence nor the causal role of the cache gap was tested. The decision rule of
§2.7 was never reached, so its "propose to the owner" branch (p ≥ 3) does not apply; no new holder appeared (the D1
dump holds S2's holder only).

**Reason.** The frozen rate rule set r = min(round₁₀₀(1.2 × a_E), 4,700); E-cal1 measured a_E = 4,318 writes/s at
CL=ALL, so r = 4,700 (r / a_E 1.09). At that rate V kept up with the CL=ONE inflow: with the holder alone (E) V's
`MutationStage` pending stayed ≤ 21 k at N = 140 k and ≤ 6.4 k at 170 k and 200 k, heap after the last GC before STOP
was 686 / 857 / 927 MiB and after any Full GC ≤ 860 MiB of 2,048, so E survived at 200 k with ≈ 1.1 GiB to spare —
far more than the 272 MiB (T − E) or 108 MiB (P − E) the caches add, so no N in the design's range could place T and P
on opposite sides of the edge. Three declared diagnostic E arms (not counted) show why: V's CL=ONE apply rate is above
5.2 k/s (D2, smooth 5,208/s: survived, 41 k pending, 1,361 MiB after Full GC), not the 4.3 k/s the CL=ALL arm gave;
at 5,307/s with bursts to 9.7 k/s (D3, cap 6,000 bound by the 2,048 in-flight slots) E survived 200 k at its edge
(h_stop 1,994 MiB = 97.4 %, 1,932 MiB after Full GC, 56.6 k pending at STOP); uncapped (D1, first seconds at
5.5–7.5 k/s) E died by heap OOM after 155,603 sent (`HeapDumper` 125.5 s after the first send; dump 60,208 queued
`StorageProxy$4` local writes, 1.81 GiB `byte[]`). It is not a false positive: the endpoint is reached at defaults and a
2 GiB heap on this ring (D1 here; S2; R11), no T/P arm ran, and nothing shows the 164 MiB cache gap cannot decide an
OOM — at D3's operating point (E at 1,932–1,994 MiB) adding P's 108 MiB or T's 272 MiB of standing cache memory would
exceed the ≈ 2,030 MiB usable heap, which is exactly the placement the design wanted but did not reach.

**What a better design should change.**
1. **Set the rate from V's CL=ONE apply rate, not CL=ALL.** CL=ALL also waits on R1/R2 (themselves in evacuation-failure
   GCs) and gave 4.3 k/s; V applies > 5.2 k/s of CL=ONE writes. Calibrate with smooth E arms at r = 5,200 / 5,600 /
   6,000 (raise sessions × in-flight, e.g. 16 × 256, so the limiter — not the 2,048 slots — sets the rate; check
   per-second sends) and drop the 4,700 cap of §2.4, which assumed R11's offered rate with the client on R2's node.
2. **Then fix r and use N as the dial**, as R19 intended: at D3's operating point (≈ 5.3 k/s, N = 200 k) E is at 94–97 %
   of the heap, so E's edge in N at that r is ≈ 200 k; bracket it with ≥ 3 E arms per N (single E arms near the edge
   split: D1 OOM at 155 k uncapped vs D3 survive at 200 k), place N\* ≈ 10–20 k below E's edge, and keep T-chk.
3. **Control the burst shape.** The first seconds decide (D1 vs D3): start the limiter only when sessions are up
   (H1), keep per-second sends within ± 10 % of r (no stored permits, enough in-flight headroom), and record the
   per-second send series as a matching variable across T/P/E.
4. **Keep** the ring, client on `ms0604`, the golden-state recipe (`golden.sh full`; restoring an old V state with
   fresh replicas fails, F1), fill, forced-GC pre-burst histogram, patched weigher for P, `hstop.py`, and the 5 T + 5 P
   + 3 E counted set with §2.7's decision rule; the calibration above takes ≈ 5 arms (≈ 45 min) on this ring.
