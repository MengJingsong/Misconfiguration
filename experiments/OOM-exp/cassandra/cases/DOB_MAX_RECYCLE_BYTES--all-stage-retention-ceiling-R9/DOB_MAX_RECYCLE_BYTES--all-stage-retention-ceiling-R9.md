# R9 (retry of C3) — `DOB_MAX_RECYCLE_BYTES`: kept scratch buffers over every DOB-writing stage, ceiling screen  <!-- file: cassandra/cases/DOB_MAX_RECYCLE_BYTES--all-stage-retention-ceiling-R9/DOB_MAX_RECYCLE_BYTES--all-stage-retention-ceiling-R9.md -->

| Field | Value |
|---|---|
| Case ID | `R9` (R = a new attempt at an earlier case; README "ID prefixes") |
| From | retry of `C3` (C = convergence case; row C3 of [`phase2-retry-list.md`](../../phase2-retry-list.md)) |
| Phase-1 case file | [`DOB_MAX_RECYCLE_BYTES-close-MAX_RECYCLE_BUFFER_SIZE--guided`](../../../../capacity-enforcement-exp/cassandra/stage3-ai-deep-read/cases/DOB_MAX_RECYCLE_BYTES-close-MAX_RECYCLE_BUFFER_SIZE--guided.md) |
| System / pinned source | Cassandra 5.0.9 (`systems/cassandra/source/`), unpatched; x86_64 build on `pc72` at `/mydata/s4/cassandra-base` |
| Stage 1 (design) | phase-2 OOM agent stage 1, 2026-11-20 ≈ 10:30–11:15 EST |
| Stage 2 (verify) | **not run**: the ceiling screen (§2.4) fails, `ready_for_stage2 = false`; owner closed C3 without a run (2026-11-20) |
| Verdict | **false positive** (owner ruling 2026-11-20, from the ceiling arithmetic of §2.4–§2.6 and C3's measured 0/7 at 512 MiB; not run) |

## Summary

- **Design outcome (stage 1).** The retry row asks for more holders than C3 had: counter and view stages, more
  SEP workers (SEP = Cassandra's shared executor pool), or the in-flight fill. By source, the retention
  domain on `pc72` (40 CPUs, heap 2 GiB) can hold at most ≈ 197 MiB with every concurrently reachable DOB-writing
  thread (128 native-transport + 32 mutation + 32 counter + 5 non-SEP), ≈ 271 MiB if every SEP worker the node can
  create kept a full buffer (not client-controllable), ≈ 303 MiB with materialized views (a non-default feature).
  Plus the idle base (51 MiB) that is ≤ 356 MiB, under 512 MiB. Adding every other default standing direct pool
  at its cap (3 hint slabs, networking pool) gives ≈ 440–478 MiB realistic and ≈ 514 MiB as the theoretical maximum.
  That 514 MiB stack is the R6-V + S1 stage-2 combination already tested (both negative).
- **Holders that do pass 512 MiB are not C3's.** The in-flight fill (U1/R7, ≈ 1–1.5 GiB) is already a true
  positive (R7 at 896 MiB; S1 at 768 MiB *with retention as a layer*, 832–2,048 MiB surviving). The
  chunk-cache pool (512 MiB at a 2 GiB heap) is OC-29's stack (closed by S1) or OC-28's overflow domain (open).
  At defaults, filling it costs C9's ≈ 0.5 GiB read-ahead transient, which fires before retention could matter. In
  neither stack can retention be the deciding layer with a matched control and an intervention.
- **Recommendation:** no stage-2 run. Close C3 as **false positive**. The protocol's ceiling test holds for the
  retention domain at shipped defaults and an acceptable budget. C3 already measured the holder (U independent of K,
  0/7 at 512 MiB, peak 195 MiB). The remaining multiplicity (counter, read- and response-created workers) is bounded
  by the arithmetic in §2.4.

---

## 1. Candidate

**Retry row (quoted from [`phase2-retry-list.md`](../../phase2-retry-list.md), row C3; status set by the session):**

> | [C3](cases/negatives/DOB_MAX_RECYCLE_BYTES-worker-multiplicity/DOB_MAX_RECYCLE_BYTES--worker-multiplicity.md) | 2026-11-12 | Main condition `negative · deployment` (0/7 at 512 MiB direct / 2 GiB heap; peak 195 MiB; ceiling by source ≈ 216 MiB write-only, ≤ ≈ 330 MiB all stages). Retry only by the mapping rule: the tightened 160 MiB condition is recorded as `reproduced-OOM · diagnostic` (3/3, largest failing 176 MiB, V7 unmet). Retention plus a 4–6 MB burst did not separate from its control | Retention alone stays below 512 MiB by source, so a rerun alone will not reach OOM; it is already a layer of S1 (verified). A new design needs more holders than C3 had: counter and view stages add 64 DOB writers (N20, ≈ 3 GiB ceiling, producibility unchecked) and reads/counters ≈ 116 SEP workers; or the in-flight fill (U1). Owner may close it as false positive (the protocol's ceiling test holds) | picked again: R9 (2026-11-20) |

**Earlier case and verdict.** [C3](../negatives/DOB_MAX_RECYCLE_BYTES-worker-multiplicity/DOB_MAX_RECYCLE_BYTES--worker-multiplicity.md)
(apt190, 16 hardware threads, 2026-11-12). The verdict was `retry` only because of the 2026-11-17 mapping rule:
the main condition is `negative · deployment`, and only the tightened condition is `reproduced-OOM · diagnostic`.
- §1: `DataOutputBuffer.scratchBuffer` is a `FastThreadLocal` direct buffer. `close()` keeps it when its
  capacity is ≤ L = `DOB_MAX_RECYCLE_BYTES` = 1 MiB (`io/util/DataOutputBuffer.java:53,63–88`). A larger buffer
  is dropped, not trimmed. So a thread keeps ≤ 1 MiB, and in practice 520,050 B or 1,040,098 B with values of
  S ≲ 524,000 B. No counter covers the sum over threads.
- §3: holders grew linearly with client concurrency, from 8 to 165 holders and 6.0 to 141.8 MiB kept
  (0.84–0.99 MiB per holder). Holders saturated at 161 SEP workers (129 native-transport + 32 mutation) plus 4
  flush/compaction threads. Idle direct peaked at 181–195 MiB in every four-IP fill, and 0/7 such fills failed at
  512 MiB direct / 2 GiB heap.
- Bursts of 4/5/6 MB mutations on top did not separate from the low-holder control: 4 and 5 MB, 0/3 vs 0/3;
  6 MB, both arms died. During those bursts, mutation threads that serialize a > 1 MiB mutation **drop** their
  kept buffer. Only the native-transport holders (≈ 83–117 MiB) stayed on top of the surge.
- Diagnostic: at a tightened 160 MiB budget, retention alone ended in a direct OOM 3/3. The control was 0/3 and
  L = 0 was 0/3. The largest failing budget was 176 MiB.

**Cases the row names.**
- [S1](../convergence/internode_receive_queue+hint_slabs+DOB+networking_pool--direct-combo/internode_receive_queue+hint_slabs+DOB+networking_pool--direct-combo.md)
  (S = stacked combo; true positive, `verified-OOM · deployment`): receive queue × 8 peers, hint slabs 96 MiB,
  DOB retention from a coordinator write client, and the networking pool at its cap, then 15 MiB mutations.
  Direct OOM 3/3 at 768 MiB. 832, 896, 1,024, 1,536 and 2,048 MiB survive. Stages 1–2 (the standing layers,
  retention included) were negative at 2,048 MiB, with a 772 MiB peak.
- [U1](../candidates/concurrent_writes+max_mutation_size--inflight-DOB-fill/concurrent_writes+max_mutation_size--inflight-DOB-fill--run2-internode.md)
  (U = unprotected accumulation) → [R7](../concurrent_writes+max_mutation_size--inflight-DOB-fill-R7/concurrent_writes+max_mutation_size--inflight-DOB-fill-R7.md)
  (true positive, `verified-OOM · deployment`): the in-flight DOB fill of 16 MiB − 1 KiB mutations by 32
  `MutationStage` writers. 6/7 at 896 MiB direct, largest failing 1,024 MiB (2/5).
- N20 = OC-58: the counter and view stages fill the same `CommitLog.add` scratch. Closed as covered by R7
  (triage 2026-11-18). R7 §2.1 set it aside: a 16 MiB counter mutation needs ≈ 500 k counter cells, and views
  are disabled by default.
- [R6-V](../negatives/DOB_MAX_RECYCLE_BYTES+MAX_HINT_BUFFERS--default-v7/DOB_MAX_RECYCLE_BYTES+MAX_HINT_BUFFERS--default-v7.md)
  (false positive): retention + 3 hint slabs at defaults and 512 MiB, 0/3. Peak ≈ 260 MiB; its ceiling
  96 + 281 × 1 + 21 ≈ 398 MiB.
- Phase-1 list: OC-29 ("the default direct pools stack with no check of their sum", chunk cache, networking,
  hints, DOB) is closed as true positive (S1). OC-28 (chunk-cache / networking pool overflow) is `open`.

**Phase-1 constraint and stage 4.** `DOB_MAX_RECYCLE_BYTES` (1 MiB, `config/CassandraRelevantProperties.java:204`),
checked at `close()`. Stage 4 closed 2026-10-19 with both tiers Confirmed: the check bounds what a thread keeps
after a write, not what it holds during one (quoted in R7 §1).

**JIRA prior art** (read only, nothing posted). Searched with JIRA REST (`issues.apache.org`, 2026-11-20 ≈ 10:40 EST)
and in [`jira-oom-survey.csv`](../../../../capacity-enforcement-exp/cassandra/stage5-oom-clue-find/jira-oom-survey.csv):

| Query / source | Hits that matter |
|---|---|
| `text ~ "DataOutputBuffer" AND text ~ "thread local"` (18) | CASSANDRA-16471 (Fixed 5.0: scratch `allocateDirect` by default, `cassandra.dob.allocate_type`); CASSANDRA-8670 (Fixed 2.2, historical NIO pooling); CASSANDRA-21535 (Review In Progress: "Avoid extra copy for cached Mutation serialization", touches the `Mutation.java:453` site, not the retained sum) |
| `text ~ "dob_max_recycle_bytes" OR text ~ "MAX_RECYCLE_BUFFER_SIZE"` (51, mostly other projects) | CASSANDRA-16471, CASSANDRA-17797 (property plumbing); nothing on the sum over threads |
| `text ~ "scratchBuffer"` (8) | CASSANDRA-16471, -20167, -21535; nothing on retention × threads |
| `text ~ "SharedExecutorPool" AND text ~ "direct memory"` (2) | CASSANDRA-7546, -14096 (unrelated holders) |
| survey CSV | CASSANDRA-11838 / -11937 (Fixed 3.8: recycled DOBs retaining large buffers, which introduced the 1 MiB recycle cap); CASSANDRA-7743 (Fixed 2.1: per-thread pooled Netty buffers on SEP threads); CASSANDRA-13754 / -19942 (per-thread `BTree.Builder` retention, heap) |

**Verdict: `known-fixed`** for the single-thread retention of large buffers (the 1 MiB cap is the fix, 3.8).
**`new`** for the uncovered sum T × L, but at ≈ 0.2–0.3 GiB it is a sizing cost, not a reported failure. Not
documented as by design.

## 2. Design solution (stage 1; frozen)

### 2.1 Mechanism and what R9 was to change

- **Mechanism (as in C3).** Every thread that serializes a ≥ ≈ 512 KiB mutation or sstable row through
  `DataOutputBuffer.scratchBuffer` keeps a direct buffer of ≤ 1 MiB after `close()`, for as long as the thread
  lives. SEP workers are terminated only at shutdown, so the kept bytes are standing: T × ≤ 1 MiB, with
  T = the threads that ever held one. Direction: convergence (multiplicity). Technique notes:
  [`combo-playbook.md`](../../../combo-playbook.md) (multiplicity → stack) and
  [`default-convergence-playbook.md`](../../../default-convergence-playbook.md) (feasibility check before running).
- **The row's options.** (a) More holders of the same kind: the counter and view stages and the SEP workers
  created by reads and responses. (b) The in-flight fill (U1). This design runs the protocol's feasibility check
  ("if Σ contract capacities + baseline < budget, convergence is impossible") on each option *before* writing a
  runnable design. It also checks a third stack the evidence suggests: (c) the chunk-cache `BufferPool` at its
  cap, which C9 found to be a standing 512 MiB.

**DOB scratch users** (`grep scratchBuffer`, Cassandra 5.0.9) and the threads that run them:

| Site | When it serializes ≥ 512 KiB | Thread |
|---|---|---|
| `db/Mutation.java:453` | coordinator serialization cache, mutation < 1,000,000 B, via `validateSize` for every CQL write | `Native-Transport-Requests` (SEP) |
| `db/Mutation.java:491` | internode receive tee, < 1,000,000 B | `MutationStage` / `CounterMutationStage` (SEP) |
| `db/commitlog/CommitLog.java:306` | every local apply | `MutationStage`, `CounterMutationStage`, `ViewMutationStage` (SEP), or inline |
| `db/rows/UnfilteredSerializer.java:195` | sstable row body (`header.isForSSTable()`) | flush writers, compaction executor |
| `hints/HintsWriter.java:77` | hint write | the hints-write executor (1 thread) |
| `db/SystemKeyspace.java:774` | small | — |

Read, response and auth tasks never touch the scratch buffer.

### 2.2 Protection map (fixed before any reading)

| Domain | Allocation / release | Contract C | Multiplicity on `pc72` (40 CPUs, 1 data dir, heap 2 GiB) | Aggregate coverage | Lifetime | Budget metric |
|---|---|---|---|---|---|---|
| **D kept DOB scratch** (claimed holder) | `DataOutputBuffer$1$1.allocate` (`allocateDirect`), kept at `close()` if ≤ L | L = 1 MiB per thread; in practice ≤ 1,040,098 B (S ≲ 524,000 B, doubling) | SEP permits (`concurrent/Stage.java:45–50`, `transport/Dispatcher.java:58,77`): native transport 128, auth 4, read 32, mutation 32, counter 32, view 32, request-response = CPUs = 40 → **≤ 300 workers**. `SharedExecutorPool.schedule` (`:101–116`) creates a worker only when none is spinning or descheduled. DOB-capable concurrent tasks: 128 + 32 + 32 = **192** (views off). Non-SEP: flush 2 (`DatabaseDescriptor.java:755`), compactors min(8, max(2, min(40, 1))) = 2 (`:778`), hints writer 1 | none (no counter of kept bytes) | standing until the thread's next use; workers never exit | JDK `Bits` (`MaxDirectMemorySize`) |
| H hint slabs | `HintsBuffer` 32 MiB slabs (`HintsService.java:79`) | `MAX_HINT_BUFFERS` 3 → 96 MiB (1 slab at idle) | 1 pool | pool count | standing | `Bits` |
| P networking `BufferPool` | 8 MiB macro chunks | `networking_cache_size` = min(128, heap/16) = 128 MiB (`DatabaseDescriptor.java:573–574`) | 1 | overflow uncapped (OC-28) | standing (never freed) | `Bits` |
| CC chunk-cache `BufferPool` | 8 MiB macro chunks (`BufferPool.java:385,438–460`) | `file_cache_size` = min(512, heap/4) = 512 MiB (`:576–577`), used by every reader even with `file_cache_enabled: false` (`BufferManagingRebufferer.java:45`) | 1 | overflow uncapped (OC-28) | standing (C9 R0: filled on the first range read and kept) | `Bits` |
| U in-flight DOB fill (U1/R7, not C3) | same object while > L, in `CommitLog.add` | none in flight; per writer ≤ 2(M − 13) ≈ 32 MiB, `max_mutation_size` 16 MiB | `concurrent_writes` 32 (+ counter 32 if near-16 MiB counter mutations are producible; + view 32 with MVs) | none | transient | `Bits` |
| B0 idle base | 1 hint slab 32, 2 chunk-cache macro chunks 16, other ≈ 3.4 | — | — | — | standing | `Bits` (C3: 51.4 MiB) |

Netty's arenas count against a separate limit equal to `MaxDirectMemorySize` (C3 §3.4, S1 §1.1). They do not add
to the `Bits` sum.

### 2.3 Configuration and budget audit (`pc72`, checked read-only 2026-11-20 ≈ 10:33 EST)

| Item | Value |
|---|---|
| Node | `pc72.cloudlab.umass.edu`, Xeon E5-2660 v2, 2 sockets × 10 cores × 2 threads = **40 CPUs**, 128,850 MiB RAM, 8 GiB swap, cgroup v2, `/mydata` 753 GB (714 GB free), OpenJDK 11.0.33, Ant; `/mydata/s4/cassandra-base` present; no Java process running |
| What the node resolves by itself | `cassandra-env.sh:58–66`: ½ RAM > 15,872 → heap **15,872 MiB**, direct 15,872/2 = **7,936 MiB**; at that heap `file_cache_size` 512, `networking_cache_size` 128 |
| Planned budget (if run) | heap 2,048 MiB (ideal), direct 512 MiB (minimum acceptable; V7 by the standing rule), then an upward search |
| Constraints, all **default** | `DOB_MAX_RECYCLE_BYTES` 1 MiB (unset), `cassandra.dob.allocate_type` DIRECT, `native_transport_max_threads` 128, `native_transport_max_auth_threads` 4, `concurrent_reads/writes/counter_writes/materialized_view_writes` 32/32/32/32 (`cassandra.yaml:722–728`), request-response = 40 CPUs, `memtable_flush_writers` 2, `concurrent_compactors` 2, `MAX_HINT_BUFFERS` 3, `networking_cache_size` 128 MiB, `file_cache_size` 512 MiB, `materialized_views_enabled: false` (`cassandra.yaml:1981`), `max_mutation_size` 16 MiB |

### 2.4 Ceiling arithmetic (the feasibility check)

Per-holder kept size: ≤ 1,040,098 B = 0.992 MiB. C3 measured a mean of 0.86 MiB (141.8 MiB / 165 holders).

| # | Stack (all at shipped defaults, heap 2 GiB) | Holders T | D (kept) | + other | Ceiling | vs 512 MiB |
|---|---|---|---|---|---|---|
| A0 | C3 as measured (write path) | 165 | 141.8 (measured) | B0 51.4 | **195** (measured peak) | 38 % |
| A1 | + counter stage (N20, retention form) | 192 SEP + 5 | ≤ 195 | B0 51 | **≤ 246** | 48 % |
| A2 | + every SEP worker the node can create (reads 32, request-response 40, auth 4), each later handed a ≥ 512 KiB DOB task | 268 + 5 | ≤ 271 | B0 51 | **≤ 322** | 63 % |
| A3 | A2 + views (non-default `materialized_views_enabled: true`) | 300 + 5 | ≤ 303 | B0 51 | **≤ 354** | 69 % (and fails V6/labels) |
| A4 | A1 + every other standing default pool at its cap (hint slabs +64, networking pool +128; multi-node, down peer) | 197 | ≤ 195 | 51 + 192 | **≤ 438** (at the measured mean: 413) | 86 % |
| A5 | A2 + the same pools (theoretical maximum of the retention domain plus standing pools) | 273 | ≤ 271 | 51 + 192 | **≤ 514** (at the measured mean: 478) | 100.4 % (93 %) |
| B | A1 + the in-flight fill (U1/R7) | 197 + 32 writers | ≤ 195 (MS holders dropped by > 1 MiB writes) | 32 × 2–3 × 16 MiB ≈ 1.0–1.5 GiB | ≫ 512 | passes, but not by D (below) |
| C | A1 + chunk-cache pool at its cap | 197 | ≤ 195 | 512 + 35 | ≈ 742 | passes, but not by D (below) |

**A0–A5 (the retention domain, the C3 claim).** At shipped defaults this domain cannot reach 512 MiB. Only A5's
theoretical bound touches it (≤ 514 MiB, 0.4 % over), and A5 needs all of these at once:
1. All 76 workers created by read, response and auth tasks are later handed a ≥ 512 KiB DOB task. SEP picks
   workers from its spinning/descheduled maps (`SharedExecutorPool.java:107–109`), so a client cannot direct this.
   Keeping 40 request-response tasks running at once means 40 response callbacks of microseconds each, which is
   not a reachable load.
2. Every kept buffer is at the 0.992 MiB maximum. The measured mean is 0.86 MiB.
3. Three hint slabs (a down peer under write load) and the networking pool at its cap (heavy internode frames)
   stand at the same moment.

At the measured mean, A5 is 478 MiB (93 %). With only the reachable DOB-capable holders (A4) it is ≤ 438 MiB (86 %).
A4/A5 is also the layer set that R6-V tested (negative at 512 MiB, peak ≈ 260 MiB) and that S1 stage 2 tested
(negative at 2,048 MiB). So none of the row's same-kind holders (counter, view, SEP multiplicity) can make
retention alone, or retention plus the standing pools, reach the minimum acceptable budget. At 2 GiB direct the
gap is ≥ 4×.

**B (in-flight fill).** The ceiling passes 512 MiB, but the endpoint is not C3's:
- The in-flight fill alone already reaches OOM at defaults: R7 at 896 MiB (6/7) and up to 1,024 MiB (2/5).
- While the fill runs, each `MutationStage` thread that serializes a > 1 MiB mutation replaces its kept buffer
  (`close()`, `DataOutputBuffer.java:71–80`; C3 §3.2). Retention adds only ≤ 128 + 32 ≈ 160 MiB on top of a
  hazard that spans ≈ 250 MiB of budget (896 → 1,152 MiB).
- S1 is this exact stack (retention layer + hint slabs + pool + receive queue + 15 MiB mutations). Its largest
  failing budget was 768 MiB, and 832–2,048 MiB survived.
- C3 phase B (retention + 4/5/6 MB bursts) did not separate from its control.

So no budget ≥ 512 MiB is predicted where fill alone survives 3/3 and fill + retention fails 3/3. Any OOM would be
R7's endpoint, and the design would rerun S1.

**C (chunk-cache pool at 512 MiB; my own alternative, not named by the row).** The arithmetic passes: the control
without retention is ≈ 547–563 MiB, the test ≈ 690–760 MiB, so a budget of ≈ 600–740 MiB would separate them on
paper. But:
1. At defaults the pool fills only when about 2,000 readers are open at once (C9 R0: one range read over 2,000
   sstables filled it to the cap). Each of those scanners also allocates C9's 256 KiB read-ahead buffer outside
   the pool, so the fill phase peaks at ≈ 51 + 962 ≈ 1,013 MiB. That is above every budget where retention could
   decide, so C9's endpoint (true positive) fires first. A fill without read-ahead (point reads over a partition
   spread across thousands of sstables) is unverified and would need C9's compaction pause.
2. With the pool at 512 MiB, the pool alone equals the 512 MiB minimum budget. Such a result is a statement about
   the pool size `file_cache_size` against `MaxDirectMemorySize`. That is OC-29's stack (closed by S1) and OC-28's
   domain (open), not C3's.

### 2.5 Workload, instruments, prediction, controls, time plan

**Not released: no design passes §2.4 for the C3 holder.** The protocol forbids escalating budgets or capacities to
force an endpoint, so no runnable arm is frozen.

If the owner prefers a measured close to an arithmetic one, the smallest useful run on `pc72` measures A1 (the
counter stage and the read-created workers that C3 did not exercise). It reuses C3's harness and instruments
([`c3-run.sh`](../negatives/DOB_MAX_RECYCLE_BYTES-worker-multiplicity/harness/c3-run.sh) and `DirectPoll.java`
every 250 ms, an idle live dump read with `hprof_direct.py`):

| Item | Value |
|---|---|
| Node and data | `pc72`, `/mydata/s4/r9-w5/` |
| Phase 1: create workers | 32 slow reads (one 64 MiB partition each) and a four-IP write fill of 4,000 × 520,000 B values (4 × 128 threads) |
| Phase 2: counter writers | 32 threads of single-partition counter batches of ≈ 15,000 rows (≈ 520 KB serialized; single-partition batches skip `verifyBatchSize`) |
| Phase 3: idle | 30 s idle, then a dump |
| Budget and repeats | heap 2 GiB, direct 512 MiB, test ×3; low-holder control (c = 1) ×3; L = 0 ×3 |
| Prediction | peak ≤ 246 MiB (48 %), 0/3 failures |
| Time | ≈ 1 h 45 min including the build check, well inside 12:00–17:30 |

It would turn the arithmetic false positive into a measured one. It cannot produce a true positive.

### 2.6 Decision

- **`ready_for_stage2 = false`.**
- **owner_review_reason:** the retention domain's ceiling at shipped defaults stays below the minimum acceptable
  budget, even with the counter and view stages and every SEP worker counted. Single node: ≤ 246 MiB reachable,
  ≤ 322 MiB theoretical, ≤ 354 MiB with views (non-default), against 512 MiB. With every other standing default
  pool at its cap it is ≤ 438 MiB reachable and ≤ 514 MiB only under assumptions no client controls (478 MiB at
  the measured per-holder mean). That stack is R6-V + S1 stage 2, both already negative. The stacks that do pass
  512 MiB (the in-flight fill; the chunk-cache pool) carry their own endpoints, which are already true positives
  (R7, S1, C9) or another open candidate (OC-28). Retention cannot be the deciding layer in them: S1's largest
  failing budget with retention stacked on the fill is 768 MiB, versus R7's 1,024 MiB without it.
- **Recommendation:** close C3 as **false positive** (`oom-agent-playbook.md`, "False positive or retry"). C3
  measured the holder independently of K and found no growth past the budget (0/7 at 512 MiB, peak 195 MiB). The
  ceiling arithmetic at defaults cannot reach an acceptable budget. The multiplicities the row names are covered by
  that arithmetic.

`sha256 of §1–§2 at freeze: 0161848a0752d877889019e5cb9bfce64eb5ff9099292e17c7a23ff29c351653 (computed over the lines from `## 1. Candidate` up to, not including, this line)` · amendments after the freeze: none.

## 3. Runs (stage 2)

Not run. 2026-11-20: the owner (Jingsong) closed C3 on the ceiling screen and declined the optional pc72 confirmation run of §2.5.

## 4. Conclusion (stage 2)

**Verdict: false positive** (owner ruling, 2026-11-20). Protocol status: `negative · deployment` (C3's measurement stands: 0/7 at 512 MiB direct / 2 GiB heap, peak 195 MiB).

Reason: C3 measured the holder independently of its counter and its growth stopped below the budget; the ceiling arithmetic at shipped defaults (§2.4) keeps retention at ≤ 246 MiB reachable (≤ 322 MiB with every shared-pool worker, ≤ 354 MiB with views) and ≤ 438 MiB reachable with every other standing default pool at its cap — the stack R6-V and S1 stage 2 already tested negative. Stacks that pass 512 MiB fail through holders with their own verdicts (R7, S1, C9; open OC-28), so retention is never the deciding layer. All three false-positive conditions of `oom-agent-playbook.md` hold. C3 and R9 are closed; nothing is left on the nodes.
