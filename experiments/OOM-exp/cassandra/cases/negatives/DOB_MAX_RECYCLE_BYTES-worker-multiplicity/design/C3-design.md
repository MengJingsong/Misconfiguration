# C3 run 1 — design (2026-11-12, written before any reading)

**Investigation:** C3 (campaign plan, P1), convergence · multiplicity: `DataOutputBuffer` scratch-buffer
retention (`DOB_MAX_RECYCLE_BYTES`, default) multiplied by the threads that hold one.
**Node:** `apt190` (`node3.jason92-325433.misconfiguration-pg0.apt.emulab.net`; APT r320, Xeon E5-2450,
8 cores / 16 hardware threads, 15,931 MiB RAM, 8 GiB swap, Linux 5.15.0-198, cgroup v2, OpenJDK 11.0.33).
**Build:** `~/cassandra-c1` (5.0.9 from the pinned tree, `src/` identical to `~/oom-src-pristine`;
`conf/` identical to `systems/cassandra/source/conf`), unmodified. Repo commit at design time `2eac8626`.
**Run data:** `/mydata/c3/` on apt190. **Lead source:** campaign plan C3 (from the R2 DOB calibration).

## 1. Source finding (5.0.9, before readings)

**What is retained.** `DataOutputBuffer.scratchBuffer` is a `FastThreadLocal<DataOutputBuffer>`
(`io/util/DataOutputBuffer.java:63`). Its buffer is `ByteBuffer.allocateDirect` (`:87`, allocation type
DIRECT by default), so it is charged to `-XX:MaxDirectMemorySize` (`Bits.reserveMemory`). Growth
(`expandToFit`, `:174`) allocates a new buffer of `max(2·cap, cap+count)` (doubling up to
`DOB_DOUBLING_THRESHOLD_MB` = 64 MiB, then ×1.5) and frees the old one at once (`setBuffer` →
`FileUtils.clean`). On `close()` (`:71-80`) the buffer is **kept** if `capacity <= MAX_RECYCLE_BUFFER_SIZE`
(`DOB_MAX_RECYCLE_BYTES`, `CassandraRelevantProperties.java:204`, default `1024*1024`), else it is
**replaced** by a fresh 128 B buffer (the large one is freed). So "trimmed" means *dropped*, not shrunk:
a thread keeps at most one buffer of ≤ 1 MiB; a buffer that grew past 1 MiB is freed at close.
In-flight growth is unbounded by L (up to the serialized size × ≤ 2, plus the old/new overlap at the last
expansion).

**Retained size per thread for a payload S.** A cell value is copied with
`BufferedDataOutputStreamPlus.write(ByteBuffer)` → `doFlush(S)` → capacity ≈ S + small; the next
1-byte write doubles it. R2 measured 8,000,100 B for S = 4,000,000 (= 2·(S+50)). So a thread keeps a
≈ 1 MiB buffer when 2·(S+~50) ≤ 1,048,576, i.e. S ≲ 524,000 B. **Chosen fill payload S = 520,000 B →
predicted kept capacity ≈ 1,040,100 B (0.992 MiB) per thread.** Payloads above ≈ 524 KB keep nothing.

**Call sites (holders)** (`grep scratchBuffer src/java`):

| Site | When it can grow ≥ 512 KiB | Threads |
|---|---|---|
| `CommitLog.add` (`db/commitlog/CommitLog.java:306`) | every local write; size = serialized mutation (≤ `max_mutation_size` = 16 MiB) | whoever applies the mutation: SEP workers running `MutationStage` / `CounterMutationStage` / `ViewMutationStage`, or `Native-Transport-Requests` inline (`SEPExecutor.maybeExecuteImmediately:218` ← `StorageProxy.performLocally`), commit-log replay at startup |
| `Mutation.serialize` cache (`db/Mutation.java:453`) | only mutations < `CACHEABLE_MUTATION_SIZE_LIMIT` = 1,000,000 B, internode sends | internode senders (not reached on a single node) |
| `Mutation.deserialize` tee (`:491`) | internode receive, tees up to 1,000,000 B | internode/`MutationStage` (not reached on a single node) |
| `UnfilteredSerializer` row body (`db/rows/UnfilteredSerializer.java:195`) | SSTable writing of a row ≥ 512 KiB | flush writers (`memtable_flush_writers` 2 per data dir), compaction (`concurrent_compactors` = min(8, max(2, min(cores, dirs))) = 2), streaming |
| `HintsWriter`, `SystemKeyspace.truncationAsMapEntry` | tiny | — |

**Worker bounds at defaults.** The request stages are **one shared pool**: `Stage.READ/MUTATION/
COUNTER_MUTATION/VIEW_MUTATION/REQUEST_RESPONSE` use `multiThreadedLowSignalStage` →
`SharedExecutorPool.SHARED.newExecutor` (`concurrent/Stage.java:45-50,229`), and so do
`Native-Transport-Requests` and `Native-Transport-Auth-Requests` (`transport/Dispatcher.java:58,77`).
Each executor limits its *concurrent tasks* (work permits); the threads are SEP workers shared by all of
them. A worker is created only when no spinning or descheduled worker exists
(`SharedExecutorPool.schedule:103-116`) and is **never terminated** before shutdown (descheduled workers
park; `terminateWorkers` runs only at shutdown). A `FastThreadLocal` is per thread, so the number of
potential holders is the SEP pool size, which only grows to the **peak simultaneous demand** and stays.

Upper bound on SEP workers (permits, defaults at 16 hardware threads): Native-Transport-Requests
`native_transport_max_threads` 128 + Auth 4 + MutationStage `concurrent_writes` 32 + ReadStage 32 +
CounterMutationStage 32 + ViewMutationStage 32 (MVs disabled by default) + RequestResponseStage 16
= **276** (+ a few spinning). For a **write-only** workload the reachable peak is about
NTR 128 (blocked on the write response) + MutationStage 32 = **≈ 160 threads**; only these
(plus ≈ 4 flush/compaction threads) can serialize a ≥ 512 KiB mutation and keep 1 MiB.

**A second, client-side bound.** Native requests are admitted against `native_transport_max_request_data_in_flight`
(heap/10) and `…_per_ip` (heap/40) (`DatabaseDescriptor.java:649-656`); over the limit the connection
is paused (`PreV5Handlers.pauseConnection`, back-pressure). At heap 2 GiB: per IP 51.2 MiB, global
204.8 MiB. With S = 520 KB one client IP can have ≈ 100 requests in flight (≤ 128 NTR), so one IP
can reach ≈ 130 holders; four IPs are needed to approach 160.

**Feasibility (protocol *Classification by measurement*).** C (contract) per thread = L = 1 MiB.
Σ over all reachable holders: write-only ≈ 160–165 MiB; every SEP stage saturated ≈ 280 MiB.
Idle direct baseline ≈ 51 MiB (R2, same build/JDK). So **pure retention at defaults peaks at ≈ 215 MiB
(write-only) and ≤ ≈ 330 MiB (all stages)**, below a 512 MiB direct budget. Prediction: retention
alone **cannot** reach the 512 MiB minimum acceptable budget at defaults; an OOM at ≥ 512 MiB needs
≥ 180–300 MiB of *other* simultaneous direct demand, of which the largest default-reachable source is
in-flight DOB growth of large mutations (bounded by the in-flight request bytes, ≤ 204.8 MiB of
requests at heap 2 GiB, × up to 2–3 in DOB capacity and expansion overlap).

## 2. Protection map

| Field | DOB scratch retention (the tested domain) | In-flight DOB growth (phase B surge, same class) |
|---|---|---|
| Allocation / ownership | `scratchBuffer` thread-local; `allocateDirect` on growth; owner = thread | same object, while a mutation is being serialized |
| Local contract (C) | keep if capacity ≤ L = 1 MiB (default), per thread; a retention cap only | none (L does not bound growth); `max_mutation_size` 16 MiB per mutation |
| Scope / multiplicity | per thread; T = SEP workers that serialized a ≥ 512 KiB mutation (≤ ≈ 160 write-only, ≤ 276 permits) + flush/compaction threads | concurrent serializations ≤ MutationStage permits (32), and request bytes ≤ heap/10 global, heap/40 per IP |
| Aggregate coverage | none: no counter of kept bytes; only the JVM direct limit | in-flight request bytes (heap/10) only indirectly |
| Lifetime | standing until the thread's next use (and SEP workers never exit) | transient (ms–s) |
| Budget | `-XX:MaxDirectMemorySize` (`Bits`); Netty pooled arenas and commit-log mmaps not charged | same |

U = JDK direct pool `MemoryUsed`/`Count` (MXBean via `nodetool sjk mx`), NMT `Other` (summary), heap-dump
attribution of every `Bits`-owning `DirectByteBuffer` to its holder thread (`harness/hprof_direct.py`,
from R2). K: Cassandra has no counter for this domain. T: number of DOB scratch buffers ≥ 512 KiB in
the dump (and their thread names); SEP pool size from `jstack` (distinct worker ids).

## 3. Configuration and budget (V6/V7)

- **Constraint (V6):** `DOB_MAX_RECYCLE_BYTES` not set (default 1 MiB) in every arm except the
  intervention (`-Dcassandra.dob_max_recycle_bytes=0`: every buffer is replaced by 128 B at close; this
  is the "free the buffer" diagnostic, applied through the property instead of a source patch). Worker
  bounds (`native_transport_max_threads`, `concurrent_*`) and in-flight limits stay at their defaults
  (resolved at heap 2 GiB: 128, 32, 51.2/204.8 MiB). Evidence: per-arm JVM args and yaml diff.
- **Budget (V7, standing rule 2026-11-11):** heap `-Xms/-Xmx2048M` (ideal value), direct
  `MAX_DIRECT_MEMORY_SIZE=512M` (the minimum acceptable value) for the OOM stage; phase A uses direct
  2048M so it never binds. `cassandra-env.sh` would resolve on apt190 heap = ½ RAM = 7965 MiB, direct =
  ¼ RAM = 3982 MiB; both chosen values are below that and are explicit deployment budgets
  (≥ 512 MiB → acceptable without per-case review). If an OOM appears at 512 MiB, search upward
  (640, 768, 1024, 2048 MiB) for the largest failing budget.
- **Environment:** single node, `listen/rpc_address 127.0.0.2`, local dirs under `/mydata/c3/node`,
  `num_tokens: 1`. To emulate several client hosts for the per-IP in-flight limit, phase-A "4 IP" arms and
  phase B add an `iptables -t nat POSTROUTING` SNAT on lo that spreads new connections to
  127.0.0.2:9042 across sources 127.0.0.11–14 (`statistic nth`), removed after each arm. Disclosed as an
  environment change (deployments have many client hosts). No other supporting deviation.
- **Workload:** `cassandra-stress user` profiles without schema statements (run-8 lesson), protocol v4,
  table `c3ks.t (key blob PRIMARY KEY, "C0" blob)`, RF 1, CL ONE. *Fill* = W = 4,000 inserts of a
  520,000 B blob (2.08 GB total), client threads c. *Burst* (phase B) = large blobs (size and count set
  by the calibration below, ≤ 15,000,000 B so the mutation stays under `max_mutation_size`).

## 4. Phases, arms, predictions

**Phase A — U vs T at matched traffic (direct 2048 MiB, heap 2048 MiB, ×1 per point).** Fill with
c ∈ {1, 4, 16, 64, 256} from one IP, and c = 4 × 128 from four IPs; then 30 s idle, sample, live heap dump
(`GC.heap_dump`; forces a full GC so only reachable buffers stay), attribution. Prediction:
retained ≈ T × 0.992 MiB with T ≈ min(c + small, ≈ 130 one-IP, ≈ 160 four-IP); idle direct
≈ 51 + T MiB. Active vs idle: 1 s samples during the fill give the active peak; the post-idle sample and
dump give the retained part (buffers at position 0 = idle).

**Phase B — fixed 512 MiB direct budget, heap 2048 MiB.**
- `B-hiT` (converge): four-IP fill (max T) → 20 s idle → burst. 
- `B-loT` (matched control): same fill traffic with c = 1 (T ≈ 1–3) → same idle → same burst.
- `B-int` (intervention): `B-hiT` with `dob_max_recycle_bytes=0`.
- Calibration (before the ×3 runs, at direct 2048 MiB, ×1): burst alone after a c = 1 fill, to size
  the burst so that `B-loT` peaks ≤ 70% of 512 MiB (≤ 358 MiB) — start with 8,000,000 B blobs,
  400 inserts, 4 IPs × 8 threads, and step size/threads geometrically.
- Prediction: with retention ≤ ≈ 165 MiB the converge arm can only reach 512 MiB if the burst alone is
  ≥ ≈ 300 MiB, which collides with the 70% control margin; **expected outcome: no OOM at 512 MiB from
  retention (negative), unless measured T or retained size exceeds this model.** ×3 each for `B-hiT`
  and `B-loT`; `B-int` ×3 and the upward budget search only if `B-hiT` fails.

**Endpoint:** `OutOfMemoryError: Direct buffer memory` (first error, thread, stack) followed by
Cassandra's forced heap OOM/kill; or no failure. Service-loss criterion not used.

**Stopping budget:** ≤ 6 h wall from the first arm, ≤ 40 arm executions; no escalation of payload,
heap or concurrency beyond the stated defaults/ranges after an OOM. Every arm starts from an empty data
directory, stops Cassandra and every stress client, removes the SNAT rules, and checks nothing is left.
Large dumps stay on apt190 under `/mydata/c3/logs/`; only summaries and excerpts are copied to the repo.

**Resume notes.** Harness `harness/c3-run.sh` (copied to `/mydata/c3/`); each arm writes
`/mydata/c3/logs/<arm>/summary.txt`; a resumed session lists `/mydata/c3/logs/` to see which arms ran.

## Amendment 1 (2026-11-12 08:10, after phase A and the first burst calibration, before any 512 MiB reading)

**What was read.** Phase A (×1 per point) matched the model: holders T = 4, 20, 47, 96, 141 at
c = 1, 4, 16, 64, 256 (one IP) and **161 = 129 Native-Transport-Requests + 32 MutationStage** with four
IPs × 128 (the structural write-path ceiling); idle direct after the fill 57.6 → 193.8 MiB. Calibration
`cal-b8m` (direct 2048 MiB, burst 8,000,000 B × 400, 4 IPs × 8 threads): peak direct 589 MiB after a
c = 1 fill and 739 MiB after the 4-IP fill (difference ≈ 150 MiB ≈ the retained buffers), then **both
nodes died of a Java heap `OutOfMemoryError`** (2 GiB heap still holding the fill's memtable, ≈ 1.8 GiB
old gen before the burst). So (a) this burst alone already exceeds 512 MiB of direct memory (an in-flight
surge, not retention), and (b) the heap, not direct memory, ended the run.

**Changes (before new readings).**
1. Every burst arm runs `nodetool flush c3ks` after the retained reading and before the burst (same in
   every arm; it frees the fill's memtable; flush writers can add ≤ 2 holders in every arm).
2. The burst is the dial for phase B and is re-sized so the low-T control survives at 512 MiB:
   next calibration 8,000,000 B × 400 with 4 IPs × 4 threads (expected ≈ half the b8m increment:
   loT ≈ 320 MiB, hiT ≈ 470 MiB). Then step threads/IP (4 → 5 → 6) or blob size at **512 MiB direct**
   with the c = 1 control first; the first level where the control survives is run ×3 for both arms.
3. Margin: retained buffers at the 4-IP ceiling are ≈ 140–160 MiB, i.e. ≈ 27–31% of 512 MiB, so a
   30% safe-alone margin and an OOM in the converge arm cannot both hold unless peaks are additive to
   within a few MiB. The declared margin for phase B is therefore **"control survives 3/3 at the same
   budget"**, and the control's peak fraction is reported as measured. If the arms do not separate
   (both OOM or both survive) at any tested level, phase B is reported as not separating and the case
   rests on the arithmetic negative.
4. The `cal-b8m` result (burst alone > 512 MiB of direct memory at defaults) is recorded as a side
   finding: in-flight DOB growth of large mutations is bounded only by the in-flight request limit
   (heap/10) × the DOB growth factor; it is a C2-type surge lead, not part of C3.

## Amendment 2 (2026-11-12 09:43, after phase B at 512 MiB, before the tightened-budget readings)

**Phase B outcome (read).** At 512 MiB direct / 2 GiB heap the arms did not separate at any burst level:
4 MB × 800 (4 IPs × 4 threads): low-T 0/3, high-T 0/3; 5 MB × 640: low-T 0/3 (peaks 78–91%),
high-T 0/3 (peaks 98–100%: direct pinned at the limit, no `OutOfMemoryError`); 6 MB × 540 ×1 each:
both nodes died (high-T: direct OOM in `DataOutputBuffer.expandToFit`; low-T: Java heap OOM). Per
amendment 1, phase B is closed as "not separating"; no further burst levels.

**Added arms (retention alone, no burst; all labelled tightened/diagnostic, V7 unmet by design).**
Purpose: show that the retained buffers alone *can* exhaust a direct budget and locate the largest such
budget, with matched control and intervention ×3 at one budget.
- `T176-hiT` ×3 (four-IP fill, default L), `T176-loT` ×3 (c = 1 fill), `T176-hiTL0` ×3 (four-IP fill,
  `dob_max_recycle_bytes=0`), interleaved, direct 176 MiB, heap 2048 MiB.
- Boundary probes ×1: `T208-hiT`, `T192-hiT`.
- Prediction: idle direct ≈ 51 MiB + retained ≈ 140–145 MiB ≈ 192–196 MiB at the end of the fill →
  `T176-hiT` direct OOM during the fill (3/3), `T176-loT` ≈ 60 MiB (0/3), `T176-hiTL0` ≈ 52–60 MiB
  (0/3); `T192` borderline, `T208` survives.

## Amendment 3 (2026-11-12 09:53 apt190 clock, after T176 r1–r2, before the replacement arms)

**Read.** `T176-hiT` r1, r2 and `T176-hiTL0` r1 all died during the four-IP fill, at only 108–126 MiB
(hiT) and 69 MiB (L0) of `Bits` direct memory, of `io.netty.util.internal.OutOfDirectMemoryError:
failed to allocate 16777216 byte(s) of direct memory (used: 184549376, max: 184549376)`. Netty's pooled
allocator keeps its **own** direct counter with the same maximum as `-XX:MaxDirectMemorySize` (not
charged to `Bits`, not visible in the `java.nio` pool MXBean); four client IPs × 128 in-flight 520 KB
native requests fill it before the DOB buffers fill `Bits`. The failure is the same with the DOB
intervention, so the T176 four-IP arms do not test C3; the sequence was stopped after `T176-loT-r2`
(survived, like r1). Results are kept and reported as a side finding.

**Replacement (retention alone, tightened, diagnostic).** One client IP (per-IP in-flight limit
51.2 MiB keeps Netty's share small), c = 256 (phase A: 141 holders, idle direct 185 MiB):
`T160-hi256` ×3, `T160-loT` (c = 1) ×3, `T160-hi256L0` (`dob_max_recycle_bytes=0`) ×3, interleaved, direct
160 MiB, heap 2048 MiB; boundary probes ×1 at 176 and 192 MiB (one IP, c = 256). Prediction: hi256
reaches 160 MiB of `Bits` after ≈ 110 holders → `Direct buffer memory` OOM in `DataOutputBuffer` during
the fill 3/3; loT ≈ 60 MiB 0/3; L0 ≈ 52–60 MiB 0/3 (Netty share ≤ ≈ 64 MiB, below 160); 176 likely
fails, 192 survives (≈ 187 MiB peak).
