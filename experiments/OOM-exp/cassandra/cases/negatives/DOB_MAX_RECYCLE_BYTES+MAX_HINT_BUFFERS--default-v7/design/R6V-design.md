# R6-V design — DOB_MAX_RECYCLE_BYTES + MAX_HINT_BUFFERS at defaults, at an acceptable direct budget

**Dated 2026-11-12, written before any reading of this run.** Campaign row R6 (P2), V7 variant.
Node `apt179` (APT r320, 16 threads, 15,931 MiB RAM, 8 GiB swap, cgroup v2, OpenJDK 11.0.33, Ubuntu 22.04).
Build: copy of `~/cassandra-c1` (cassandra-5.0.9, `28adf4907aed`, unmodified) at `/mydata/r6v/cassandra`.
Run data, logs, dumps: `/mydata/r6v/` (local disk). Harness: `../harness/`.

## 1. Question

Default run 1 (2026-11-04, pc41) OOMed with both constraints at defaults, but only at a 192 MiB
`MaxDirectMemorySize`. Under the standing budget rule (protocol, 2026-11-11) a direct limit of
≥ 512 MiB meets V7. Can the same two default pools (hints slabs + kept DOB scratch buffers) exhaust a
direct limit of ≥ 512 MiB with reachable workload at defaults? Then: what is the largest direct budget
that still reaches the endpoint?

## 2. Budget (V7) and resolved defaults

- `cassandra-env.sh` on apt179: `system_memory_in_mb` = 15,931 → heap = ½ RAM = **7,965 MiB**,
  `MaxDirectMemorySize` = ¼ RAM = **3,982 MiB** (the script's `else` branch; heap_limit 15,872 not hit).
- Chosen: `-Xms/-Xmx2048M` (the "ideal" 2 GiB), `-XX:MaxDirectMemorySize=512m` (the floor of the
  standing rule) for the main arms. Both meet V7 without per-case review (standing rule). Upward
  search 512 → 1024 → 2048 only if 512 fails.
- Heap-derived defaults at 2 GiB heap (not tested constraints, other direct consumers, recorded):
  `file_cache_size` = min(512 MiB, heap/4) = 512 MiB; `networking_cache_size` = min(128 MiB, heap/16) =
  128 MiB; native-transport in-flight request bytes = heap/10 = 204.8 MiB global, heap/40 = 51.2 MiB per
  client IP.

## 3. Tested constraints (V6), defaults resolved

| Constraint | Default rule | Resolved here |
|---|---|---|
| `cassandra.dob_max_recycle_bytes` | `CassandraRelevantProperties.java:204` = 1 MiB; `DataOutputBuffer.java:53,73` | 1,048,576 B per thread, kept only if capacity ≤ that |
| `cassandra.MAX_HINT_BUFFERS` | `CassandraRelevantProperties.java:351` = 3; slab = max(2 × `max_mutation_size`, 32 MiB) (`HintsService.java:110`), `max_mutation_size` unset → `commitlog_segment_size/2` = 16 MiB | 3 × 32 MiB = 96 MiB |

Neither `-D` is passed (harness checks the N1 command line); yaml differs from the shipped file only
in environment lines (as in default run 1). No supporting deviation is planned.

## 4. Protection map (before readings)

| Domain | Allocation / owner | Contract C | Multiplicity | Aggregate coverage | Lifetime |
|---|---|---|---|---|---|
| Hints pool | `HintsBuffer.create` → `allocateDirect(32 MiB)` | ≤ 3 slabs (96 MiB); writer waits in `reserveBuffers.take()` | one pool per node, whatever the number of down destinations; per-destination `HintsWriter` adds one 256 KiB write buffer on the single `HintsWriteExecutor` thread | JVM direct limit only | standing |
| DOB kept scratch | `DataOutputBuffer.scratchBuffer` (FastThreadLocal), `allocateDirect` | ≤ 1 MiB kept per thread | T = threads that ever serialized a ≤ ~0.52 MB value: shared-pool (SEP) workers (Native-Transport-Requests inline writes, MutationStage `CommitLog.add`), memtable flush writers and compaction threads (`UnfilteredSerializer` row bodies), `HintsWriteExecutor` | none | standing per thread |
| DOB in-flight growth | same buffer while growing (`expandToFit`, new = max(2C, C+n), old freed at once) | **none** (recycle cap applies only at `close()`); a mutation is ≤ `max_mutation_size` 16 MiB | threads concurrently serializing; bounded by SEP permits and native in-flight bytes, but MutationStage tasks outlive timed-out requests | none | transient |
| Other default direct | idle (~23 MiB non-hints in run 1), `BufferPool` chunk/networking pools (≤ 512 + 128 MiB contract), compaction read-ahead 256 KiB × compactors | per pool | — | — | — |

Budget: `-XX:MaxDirectMemorySize` (`Bits.reserveMemory`). Netty's own pooled direct arenas are not
charged to `Bits` (protocol v4 framing, as in run 1 and R2).

U (independent of any control counter): JDK `BufferPool direct` MemoryUsed/Count every 5 s; live
`HintsBuffer` count from a class histogram; at the end of alive arms and at any OOM a heap dump read
by `hprof_direct.py` (from R2) grouping every Bits-owning `DirectByteBuffer` by holder (hints slab,
DOB scratch with its thread, other). K (`allocatedBuffers`) is not read.

## 5. Arithmetic ceiling of the two pools at defaults (feasibility screen)

SEP executors (`Stage.java:45-50`, `Dispatcher.java:58,77`) and their permits: Native-Transport-Requests
128, ReadStage 32, MutationStage 32, CounterMutationStage 32, ViewMutationStage 32, RequestResponseStage
16 (= cores), auth 4: Σ = **276**. SEP workers are parked (`descheduled`), not terminated, and are
reused before a new one is spawned (`SharedExecutorPool.schedule`), so physical workers ≈ peak concurrent
tasks + a few spinners ≤ ~280. Non-SEP holders: 2 flush writers, ≤ 2 compactors, 1 hints writer.

Kept-retention ceiling: hints 96 + DOB 1 MiB × ~285 ≈ 381 MiB, + non-hints idle ≈ 23 → **≈ 405 MiB
< 512 MiB**. A write-only workload only drives NTR + MutationStage (+ spinners): ≈ 165 threads →
≈ 23 + 96 + 165 ≈ **285 MiB (56% of 512)**.

Convergence with matched controls: the hints pool grows the budget use by only Hg ≈ +64 MiB above
idle (one slab exists at startup). For "each alone ≤ (1−m)·X, sum > X" one needs Hg > m·X: with the
30% margin X < ~215 MiB; even with a 10% margin X < ~640 MiB and a DOB demand window of only
(X − Hg, 0.9X), ≈ 14 MiB wide at 512 MiB. **Prediction: the retention mechanism cannot reach 512 MiB
at defaults; the combined demand peaks at ≈ 250–300 MiB in a write-only workload (≤ ≈ 400 MiB
arithmetic ceiling with every SEP stage busy).**

In-flight DOB growth (no contract): a value of S bytes grows a buffer to ≈ 2S, transiently with the old
one alive (≈ 3S). S ≤ ~16 MiB (max_mutation_size) → up to ≈ 32 MiB per serializing thread; R2 saw
≈ 245 MiB of transient DOB from 8 client threads of 4 MB values plus server-side retries (MutationStage
keeps running timed-out writes). This can exceed 512 MiB alone; if it does, it is DOB-alone
(unprotected accumulation, bounded only by concurrency × mutation size), not convergence of the two
named pools. Tested as a separate, labelled probe (§6 condition L).

## 6. Arms (all on N1, `-Xmx2048M`, both constraints default, 2-node loopback ring, N2 killed)

Workloads (cassandra-stress user profiles, CL ONE, protocol v4): *hints* (1 KiB into `hintks`, RF
dc1:1 dc2:1, N2 down), *local* (same 1 KiB into `dobks`, no hints), *dob* (S-byte values into `dobks`),
*fill* (extra 1 KiB writes into `dobks` at high thread count to drive more SEP workers).

**Condition S (retention mechanism, run 1's shape, demand maximised).** S = 523,000 B, so the doubled
buffer (≈ 2 × (S + ~250 B) ≈ 1,046,500 B) stays ≤ 1 MiB and is kept (run 1 used 500,000). Demand dials
at defaults: DOB client threads 512, fill 256 threads, hints 64 threads.

| Arm | Budget | Workloads | N |
|---|---|---|---|
| `S_cal` | 4096 (calibration, unconstrained) | hints + fill, then dob after 20 s | 1 (+ heap dump at end) |
| `S_conv` | 512 | hints 64 + fill 256, dob 512 thr after 20 s | 3 |
| `S_H_alone` | 512 | hints 64 + fill 256, no dob | 3 |
| `S_D_alone` | 512 | local 64 (replaces hints) + fill 256 + dob 512 | 3 |
| `S_noreplica` (intervention: no down replica) | 512 | = `S_D_alone` (hints → local) | (same arm as `S_D_alone`; see note) |
| `S_conv_diag` | below the measured `S_cal` peak (diagnostic, < 512, V7 unmet) | as `S_conv` | 1–2 if time allows |

Note: the "no down replica" intervention and the DOB-alone matched control are the same arm here
(hints workload redirected to the non-hinted keyspace at matched concurrency). If `S_conv` survives,
no intervention is needed for a negative (V4 not required); a second intervention (`S_fewDOB`, DOB
threads 8) is run ×3 only if `S_conv` fails.

**Condition L (in-flight probe; a different holder: DOB growth, not retention).** S = 15,000,000 B
(< 16 MiB frame and mutation limits). `L_D_alone` 512 (dob 32 threads, local 8) ×1, `L_conv` 512
(hints 8 + dob 32) ×1. If L_D_alone OOMs, the probe is filed as a separate unprotected-accumulation
lead and the budget search for it (1024, 2048) runs ×1 each if time allows. Not counted toward the
convergence verdict.

**Budget search.** If `S_conv` OOMs at 512: 1024, then 2048 (or bisect), ×3 at the largest failing.
If it survives: largest failing budget for S is below 512 by construction; `S_conv_diag` locates it
diagnostically.

## 7. Predicted outcome and stop rules

- `S_cal` peak ≈ 250–300 MiB; `S_conv` survives 3/3 at ≈ 50–60% of 512; `S_H_alone` ≈ 120 MiB (24%);
  `S_D_alone` ≈ 180–240 MiB. → `negative` within: defaults, 2 GiB heap, 512 MiB direct, write-only
  workloads up to 512+256+64 client threads, one victim, one down replica.
- Endpoint: JVM `OutOfMemoryError: Direct buffer memory` (first error + stack from `system.log`, holder
  breakdown from the `-XX:+HeapDumpOnOutOfMemoryError` dump). Service-loss criterion: protocol default.
- **Limits:** ≤ 6 h wall (start 07:22 MST, hard stop 13:15 MST); ≤ 25 arms; each arm ≤ 8 min
  (hints cap 150 s, dob cap 180 s). No escalation after an OOM beyond the planned budget steps.
- Clean-up: every arm ends with `stopdaemon`/`kill -9` of its N1/N2 and `pkill` of stress, checked by
  `pgrep`; at the end `pgrep -af 'CassandraDaemon|cassandra.stress'` must be empty. `/mydata/oom-recheck`
  and `/mydata/jingsong-cass-s4` are not touched.

## 8. Resume notes

Arm list and progress: `/mydata/r6v/run-seq.log` (one line per arm with rc and leftovers); per-arm
`/mydata/r6v/logs/<arm>/summary.txt`. A resumed session re-runs any arm missing `ARM … DONE` in its
`session.log` (the harness renames a partial arm folder to `.attempt-<ts>`).

## Amendment 1 — 2026-11-12 07:43 MST, after calibration, before any 512 MiB reading

Calibration at 4096 MiB (`S_cal`, `S_cal2`, both alive, end-of-arm heap dumps analysed with
`hprof_direct.py`):

- `S_cal` (hints 64 + fill 256 from t0, DOB 512 thr after 20 s): peak 225 MiB; the hints pool reached
  only 2 slabs (fill starved the hints client). Dump: 171 DOB scratch buffers = 138.7 MiB (kept buffers
  1,046,098 B each, ≤ 1 MiB as intended; some 523,050 B), 2 slabs = 64 MiB, BufferPool 16 MiB, Netty/epoll 3.5 MiB.
- `S_cal2` (hints 16 with a 30 s lead, then fill 256 + reads 64 + DOB 512 together): hints pool 3 slabs
  (115 MiB before the DOB burst), peak **258 MiB** (6.3% of 4096; 50.4% of 512). Dump: 177 DOB buffers =
  139.2 MiB (holders: 128 Native-Transport-Requests, 33 MutationStage, 6 ReadStage names), 3 slabs = 96 MiB.
  Reads did not raise T (+6 buffers).

Changes (workload only; constraints and budget unchanged):
- Main condition S fixed to `S_cal2`'s workload: `H_THREADS=16 D_LEAD=30 F_THREADS=256 F_WITH_D=1
  R_THREADS=64 D_THREADS=512 D_N=12000 D_SIZE=523000`.
- `S_H_alone` = same workloads and concurrency, DOB values 1,024 B (`D_SIZE=1024`), so no thread keeps
  a large buffer (matched total concurrency; replaces "no DOB" in §6).
- `S_D_alone` = same, `H_PROFILE=local.yaml` (no down-replica hints; also the no-hints intervention).
- Prediction at 512 MiB: `S_conv` ≈ 255–265 MiB (≈ 50–52%), alive 3/3; `S_H_alone` ≈ 120 MiB; `S_D_alone`
  ≈ 195–200 MiB. Diagnostic budget search below the floor: the largest failing budget is predicted
  just under the peak, ≈ 240–255 MiB; arms `S_diag_240`, then 250 or 220 as needed (×1–2, V7 unmet).

## Amendment 2 — 2026-11-12 08:01 MST (main 512 MiB arms running; r1 of each read), before the arms below

Queued after `list-main` (`list-next.txt`):
- Diagnostic budget search, condition S (V7 unmet, < 512): `S_diag_250` and `S_diag_240`, ×1 each, same
  workload as `S_conv`. Prediction: demand ≈ 256–258 MiB → both OOM (direct), first error in DOB
  `expandToFit` or a hints slab allocation. Refine (e.g. 256, 264) ×1 only if time allows.
- Condition L probe at 512 MiB (both constraints default; holder = DOB in-flight growth, not retention):
  `L_D_alone` (`H_PROFILE=local.yaml H_THREADS=8 D_THREADS=32 D_N=600 D_SIZE=15000000 D_LEAD=20`) and
  `L_conv` (same with `hints.yaml`), ×1 each. Prediction: transient DOB ≈ 30 MiB per serializing
  thread; up to 128 NTR + 32 MutationStage threads could serialize at once, but in-flight request
  bytes are bounded per client IP at heap/40 = 51 MiB (≈ 3 requests) → transient DOB ≈ 100–200 MiB
  (more if timed-out MutationStage tasks pile up as in R2). If `L_D_alone` OOMs alone, condition L is a
  separate DOB-alone lead (unprotected in-flight growth), not convergence.

## Amendment 3 — 2026-11-12 08:47 MST, after `S_diag_250/240` and `L_D_alone` (both OOMed), before the arms below

`L_D_alone` (no hints, 15 MB values, 32 DOB threads) reached a direct OOM at 512 MiB in `CommitLog.add`
DOB growth on MutationStage threads. Condition L is therefore a **DOB-alone** endpoint (in-flight
growth, no contract), not convergence of the two pools; it is recorded as a separate lead. Queued
(`list-next2.txt`), ×1 unless stated:
- `L_D_alone_r2`, `L_D_alone_r3` at 512 (n/N at 512); `L_D_1024`, `L_D_2048` (largest failing budget for L;
  4096 only if 2048 fails and time allows); `L_D_8thr_512` (intervention: 8 DOB threads instead of 32).
- Condition S boundary (diagnostic): `S_diag_250_r2`, `S_diag_250_r3`, `S_diag_270` (predicted: 250 fails,
  270 survives since the 512 MiB arms peaked at 256–264 MiB).
