# DOB_MAX_RECYCLE_BYTES — scratch-buffer retention multiplied by worker threads (C3 run 1)

> **Filed 2026-11-12 in `negatives/`** as `negative · deployment` (defaults; 512 MiB direct / 2 GiB heap). The tightened 160 MiB result stays recorded here as `reproduced-OOM · diagnostic`.

**Direction:** convergence · multiplicity (one per-thread retention cap × the threads that hold a buffer).
**Regime:** default capacity (`DOB_MAX_RECYCLE_BYTES` unset = 1 MiB; worker bounds and in-flight limits
at their defaults), explicit deployment budget heap 2048 MiB / direct 512 MiB for the verdict; tightened
direct budgets (160–192 MiB) only in labelled diagnostic arms. **Source:** Cassandra 5.0.9 (pinned tree,
build `~/cassandra-c1` on apt190, unmodified). **Lead source:** campaign plan C3 (from the R2 DOB
calibration). **Run:** C3 run 1, 2026-11-12, `apt190`. **Design:** [design/C3-design.md](design/C3-design.md)
(written before readings, amendments 1–3 dated before the readings they govern).

| Condition | Status (protocol *Verification status*) |
|---|---|
| Retention alone at defaults, maximum reachable holders (4 client IPs × 128 threads), direct 512 MiB, heap 2 GiB | **`negative`** (0/7 max-holder fills at 512 MiB reach it; peak 195 MiB = 38%; ceiling by source ≈ 215 MiB write-only, ≤ ≈ 330 MiB all stages) |
| Retention + a concurrent large-mutation burst, direct 512 MiB (4/5/6 MB bursts, matched low-T control) | **not separating**: 4 MB 0/3 vs 0/3; 5 MB 0/3 vs 0/3 (high-T pinned at 98–100%, no error); 6 MB both die (high-T direct OOM, low-T heap OOM) |
| Retention alone, tightened direct 160 MiB, one IP × 256 threads (diagnostic mechanism check) | direct OOM 3/3, low-T control 0/3, L = 0 intervention 0/3 (V1–V5 met; V7 unmet: tightened budget). Largest failing budget for retention alone: **176 MiB** (1/1); 192 MiB survives (1/1) |

## Summary

- **Conclusion:** at defaults a Cassandra 5.0.9 node keeps at most one ≤ 1 MiB direct scratch buffer per
  thread that serialized a ≥ 512 KiB mutation, and at most ≈ 165 write-path threads can hold one
  (128 native-transport + 32 mutation workers + a few flush/compaction threads). Measured: 4 → 161
  holders and 6 → 142 MiB retained as client concurrency rises 1 → 512 at matched traffic; idle direct
  memory tops out at 195 MiB. That cannot reach the 512 MiB minimum acceptable budget, so the C3
  hypothesis is **negative at defaults**. With a large-mutation burst on top, the retained buffers add
  ≈ 45–95 MiB to the peak and bring a 6 MB-burst failure forward (27 s vs 53 s), but the matched
  low-holder control fails at the same burst level, so retention does not decide the outcome at 512 MiB.
  The mechanism is real: with the direct limit tightened to 160 MiB, retention alone ends in
  `OutOfMemoryError: Direct buffer memory` 3/3 (control 0/3, L = 0 intervention 0/3); the largest budget
  it exhausts is 176 MiB, about a third of the minimum acceptable budget.
- **Root cause (of the bound and of the gap that remains):** `DOB_MAX_RECYCLE_BYTES` caps what each
  thread keeps, not how many threads keep one; nothing counts the total, so T × L is bounded only by the
  shared-executor pool size (SEP workers are never terminated) and the JVM direct limit. At defaults
  that product is ≈ 165 MiB, i.e. bounded but uncovered. The larger direct-memory risk seen here is the
  *in-flight* DOB growth of 5–6 MB mutations (≈ 32 MutationStage permits × 2 × mutation size, held while
  a write waits for commit-log space), a separate C2-type lead.

## 1. Constraints, protection map and configuration

**Default rule.** `CassandraRelevantProperties.DOB_MAX_RECYCLE_BYTES("cassandra.dob_max_recycle_bytes",
1024*1024)` (`config/CassandraRelevantProperties.java:204`), read once into `MAX_RECYCLE_BUFFER_SIZE`
(`io/util/DataOutputBuffer.java:53`). Not set in any measured arm except the intervention
(`-Dcassandra.dob_max_recycle_bytes=0`); evidence: `jvm-args.txt` per arm, harness checks
"dob_max_recycle_bytes unset".

**What is retained (source).** `DataOutputBuffer.scratchBuffer` is a `FastThreadLocal` (`:63`); its
buffer is `ByteBuffer.allocateDirect` (`:87`), so it is charged to `Bits`/`-XX:MaxDirectMemorySize`.
Growth (`expandToFit`, `:174-180`) allocates `max(2·cap, cap+count)` and frees the old buffer at once.
`close()` (`:71-80`) keeps the buffer if `capacity <= L`; otherwise it allocates a new 128 B buffer and
then frees the large one. So a buffer above 1 MiB is **dropped**, not trimmed to 1 MiB; a thread keeps
at most one buffer ≤ 1 MiB. For a value of S bytes the buffer grows to S+≈50 and then doubles on the
next byte, so it is kept only for S ≲ 524,000 B. Measured kept capacities: 520,050 B after a thread's
first 520,000 B write and 1,040,098 B (0.99 MiB) after its second.

**Holders (call sites).** (1) The coordinator's serialization cache, `Mutation.MutationSerializer.serialization`
(`db/Mutation.java:453`): every mutation whose size is < `CACHEABLE_MUTATION_SIZE_LIMIT` (1,000,000 B) is
serialized into the scratch buffer when it is first sized, which `Mutation.validateSize` does for every
CQL write (`SingleTableUpdatesCollector.toMutations:112` → `Mutation.validateSize:171`), on the
`Native-Transport-Requests` thread. (2) `CommitLog.add` (`db/commitlog/CommitLog.java:306`, every local
write, on the thread that applies it: `MutationStage` or NTR inline; the buffer is held from serialization
through `segmentManager.allocate` and the copy into the segment). (3) `UnfilteredSerializer` row body
(`db/rows/UnfilteredSerializer.java:195`, SSTable writes: flush writers, compaction). (4) The
`Mutation.deserialize` tee (`:491`, internode receive, < 1,000,000 B; not reached on one node);
`HintsWriter`, `SystemKeyspace` (tiny). *Correction to the design:* the design listed site (1) as
internode-only; the diagnostic OOM stacks (§3.3) show it on the native path for every write < 1 MB,
which is why NTR threads hold buffers even when the write runs on `MutationStage`. The worker bound is
unchanged.

**Worker bounds at defaults (16 hardware threads, heap 2 GiB).** `ReadStage`, `MutationStage`,
`CounterMutationStage`, `ViewMutationStage`, `RequestResponseStage` (`concurrent/Stage.java:45-50,229`) and
`Native-Transport-Requests`/`-Auth-Requests` (`transport/Dispatcher.java:58,77`) are executors of one
`SharedExecutorPool`; each limits concurrent tasks, the threads are shared SEP workers, created only when
none is spinning or descheduled (`SharedExecutorPool.java:103-116`) and terminated only at shutdown.
Permits: NTR 128, Auth 4, writes 32, reads 32, counter writes 32, view writes 32 (MVs disabled), request
responses 16 → ≤ 276 workers. A write-only workload can occupy NTR 128 (blocked on the response) +
MutationStage 32 → **≈ 160**; flush writers 2 and compactors 2 add 4. Client side: native requests are
admitted against `native_transport_max_request_data_in_flight` = heap/10 = 204.8 MiB and `…_per_ip` =
heap/40 = 51.2 MiB (`config/DatabaseDescriptor.java:649-656`; over the limit the connection is paused),
so one client IP can keep ≈ 100 × 520 KB requests in flight; four IPs were needed for 160.

**Protection map.**

| Field | DOB scratch retention (tested) | In-flight DOB growth (burst arms) |
|---|---|---|
| Allocation / ownership | thread-local `DataOutputBuffer`, `allocateDirect` on growth | same object while a mutation is serialized and copied |
| Local contract (C) | keep only if capacity ≤ L = 1 MiB, per thread (retention cap) | none from L; `max_mutation_size` 16 MiB per mutation |
| Scope / multiplicity | per thread; T ≤ ≈ 165 (write path), ≤ 276 + 4 (all SEP stages) | ≤ 32 MutationStage permits at once (inline NTR execution also takes a permit) |
| Aggregate coverage | none (no counter of kept bytes) | in-flight request bytes (heap/10, heap/40 per IP), indirectly |
| Lifetime | standing until the thread's next use; SEP workers never exit | transient, but held across a commit-log allocation wait |
| Budget | `Bits` (`MaxDirectMemorySize`); Netty pooled arenas use a **separate** counter with the same maximum | same |

**Feasibility.** Σ contract over reachable holders = 165 × 1 MiB (write-only) or ≈ 280 MiB (every SEP stage
saturated) + idle direct 51.4 MiB (32 MiB hints slab, 16 MiB `BufferPool` chunks, Netty epoll arrays)
= **≈ 216 MiB / ≤ ≈ 330 MiB < 512 MiB**. Retention alone cannot reach the minimum acceptable budget.

**Configuration labels.** Capacity: **default** (L unset; `native_transport_max_threads` 128,
`concurrent_writes` 32, in-flight limits heap-derived 204.8/51.2 MiB at heap 2 GiB, `max_mutation_size`
16 MiB, all unset). Budget: heap `-Xms/-Xmx2048M` (ideal) and `-XX:MaxDirectMemorySize=512M` (minimum
acceptable), both **explicit deployment budgets** meeting V7 by the standing rule; `cassandra-env.sh` would
resolve 7965 MiB heap and 3982 MiB direct on this node (½ and ¼ of 15,931 MiB). Phase A used direct
2048M (non-binding); the T arms use 160–192 MiB (**tightened, diagnostic**). Environment: single node,
`listen/rpc_address 127.0.0.2`, local directories under `/mydata/c3/node`, cluster name (yaml diff in
each arm's `cassandra.yaml.diff`); an `iptables` SNAT on `lo` spreading client connections over 127.0.0.11–14
in the four-IP arms (emulates four client hosts; removed after every arm). Procedure: `nodetool flush c3ks`
between fill and burst (amendment 1). No supporting deviation in the default arms → `deployment`
conditions.

**Environment.** apt190 (`node3.jason92-325433.misconfiguration-pg0.apt.emulab.net`, APT r320, Xeon
E5-2450 2.1 GHz, 8 cores / 16 threads, 15,931 MiB RAM, 8 GiB swap, Linux 5.15.0-198, cgroup v2,
OpenJDK 11.0.33, G1); build `~/cassandra-c1` (src identical to the pristine copy, conf identical to
`systems/cassandra/source/conf`); repo commit `2eac8626` at design time.

## 2. Verification design

Full pre-reading design, predictions and amendments: [design/C3-design.md](design/C3-design.md).

- **Workloads** (`cassandra-stress user`, profiles without schema statements, protocol v4, CL ONE, table
  `c3ks.t (key blob PRIMARY KEY, "C0" blob)`, RF 1): *fill* = 4,000 × 520,000 B values (2.08 GB,
  matched in every arm), c client threads split over 1 or 4 stress processes/IPs (1 IP: 8 connections;
  4 IPs: 32 connections, 9 per source address observed); *burst* = S-byte values from 4 IPs × 4 threads
  (4,000,000 × 800, 5,000,000 × 640, 6,000,000 × 540).
- **Instruments** (U, independent of any Cassandra counter): `harness/DirectPoll.java` samples the JDK
  `java.nio` direct pool (`MemoryUsed`, `Count`), thread count and heap every 250 ms over one JMX
  connection; NMT summary (`Other`) and RSS at each phase point; `jstack` (distinct SEP worker ids);
  live heap dump after a 30 s idle (phase A) or the automatic dump at an OOM, analysed with
  `harness/hprof_direct.py` (R2's reader; it sums every `Bits`-owning `DirectByteBuffer` and maps DOB
  buffers to their thread). K: none exists for this domain.
- **Arms.** Phase A (direct 2048M): fill with c = 1, 4, 16, 64, 256 (1 IP) and 4 × 128 (4 IPs), ×1 each.
  Phase B (direct 512M): `hiT` = 4-IP fill → flush → burst; `loT` = c = 1 fill → flush → same burst
  (matched control); 4 MB and 5 MB ×3 each, 6 MB ×1 each; calibrations at 2048M before them.
  Diagnostic T arms (one IP, c = 256 fill, no burst): direct 160M `hi256` ×3, `loT` ×3, `hi256L0`
  (intervention L = 0) ×3; probes 176M and 192M ×1. The first T arms (176M, four IPs) were void for C3
  (Netty, amendment 3).
- **Predictions** (design): retained ≈ T × 0.99 MiB, T ≈ min(c+small, ≈ 130 one IP, ≈ 160 four IPs);
  no OOM at 512 MiB from retention; phase B expected not to separate under a 30% margin.
- **Stopping budget:** ≤ 6 h wall, ≤ 40 arm executions. Used: 3 h 08 min of arm time (07:26–10:34
  apt190 clock), **45 arm executions — 5 over the stated attempt limit** (2 validation, 6 phase A,
  7 calibrations, 14 phase B, 5 void four-IP T176 arms, 11 T160/T176/T192 arms). The overrun came from
  the void T176 arms (amendment 3); no arm escalated budget, payload or concurrency after an OOM.
- **Harness:** [`harness/c3-run.sh`](harness/c3-run.sh) (`arm <name> <direct_MiB> <L> <fill_threads>
  <fill_ips> <burst> [dump]`), sequences `harness/seq-A.sh`, `harness/seq-cal.sh`, `harness/seq.sh`.

## 3. Runtime results

Raw logs: apt190 `/mydata/c3/logs/<arm>/` (summary, 250 ms samples, jstacks, system/GC logs, stress
outputs, heap dumps); copies of the small files in [`logs/<arm>/`](logs/).

### 3.1 Phase A — U vs T at matched traffic (direct 2048 MiB, heap 2 GiB, 4,000 × 520 KB)

| Arm | Client threads × IPs | SEP workers | DOB holders ≥ 512 KiB (NTR + MS + flush/compaction) | Retained DOB (dump) | Idle direct after fill (pool) | Fill peak | Fill rate |
|---|---|---|---|---|---|---|---|
| `A-c1` | 1 × 1 | 18 | 8 (2 + 2 + 4) | 6.0 MiB | 57.6 MiB | 59.7 | 73 op/s |
| `A-c4` | 4 × 1 | 20 | 24 (6 + 14 + 4) | 15.9 MiB | 67.5 | 69.6 | 87 |
| `A-c16` | 16 × 1 | 47 | 51 (22 + 25 + 4) | 34.2 MiB | 85.9 | 88.0 | 86 |
| `A-c64` | 64 × 1 | 96 | 100 (68 + 28 + 4) | 85.3 MiB | 136.9 | 139.0 | 90 |
| `A-c256` | 256 × 1 | 141 | 145 (109 + 32 + 4) | 133.4 MiB | 185.0 | 187.1 | 92 |
| `A-c512x4` | 128 × 4 | 161 | 165 (129 + 32 + 4) | 141.8 MiB | 193.8 | 193.8 | 4 × 25–29 |

Idle direct before the fill was 51.4 MiB in every arm. Every large buffer in these dumps was idle
(position 0, no traffic for 30 s). Kept capacities were 520,050 B (thread used once) or 1,040,098 B
(used twice or more): e.g. `A-c512x4` 117 × 1,040,098 + 44 × 520,050 + 4 flush/compaction buffers of
≈ 1,040,014 B. **Active vs idle:** for these ≤ 1 MiB payloads the buffer a thread uses is the buffer it
keeps, so the fill-window peak exceeds the post-idle level by only ≈ 2 MiB in every arm; the retained
fraction is essentially all of it. **U vs T:** retained ≈ 0.84–0.99 MiB per holder (fill-dependent mix
of half- and full-size buffers), linear in T; T saturates at 161 SEP holders (129 NTR + 32 MS), the
write-path ceiling predicted from source. The same 4-IP fill reached 160–161 SEP workers and
181–195 MiB idle direct in the seven 4-IP fills of phase B and the three 4-IP calibrations.

### 3.2 Phase B — retention plus a burst at direct 512 MiB (heap 2 GiB)

| Burst | Arm | Direct before burst | Peak during burst (250 ms samples) | Direct after burst | Outcome |
|---|---|---|---|---|---|
| 4 MB × 800 | `loT` r1/r2/r3 | 57.1 / 58.1 / 58.1 | 366.8 / 390.2 / 306.3 (60–76%) | 53–55 | alive 3/3, 0 ERROR |
| | `hiT` r1/r2/r3 | 191.3 / 191.3 / 189.3 | 483.1 / 459.7 / 399.5 (78–94%) | 146.7 / 148.2 / 146.7 | alive 3/3, 0 ERROR |
| 5 MB × 640 | `loT` r1/r2/r3 | 58.6 / 58.1 / 58.1 | 468.3 / 402.1 / 416.4 (79–91%) | 53–55 | alive 3/3, 0 ERROR |
| | `hiT` r1/r2/r3 | 191.8 / 194.8 / 181.4 | **511.1 / 509.9 / 503.5 (98–100%)** | 149.2 / 154.0 / 136.4 | alive 3/3, 0 ERROR, burst duration unchanged (≈ 78 s) |
| 6 MB × 540 | `loT` r1 | 58.6 | 507.0 | — | **Java heap OOM** 53 s into the burst (`BatchlogTasks:1`, heap ≈ 1.9 GB `byte[]`), killed |
| | `hiT` r1 | 191.8 | 507.0 | — | **direct OOM** 27 s into the burst (`MutationStage`, `DataOutputBuffer.expandToFit` ← `CommitLog.add:308`), killed |

Calibrations at direct 2048 MiB (×1): 8 MB × 400 with 4 × 8 threads peaked at 589 MiB (loT) and
739 MiB (hiT), 4 × 4 threads at 703/707 MiB, then Java heap OOM in three of four runs; 4 MB × 800 at
383/469 MiB; 2 MB × 1600 (loT) at 193 MiB.

**Attribution at the 6 MB direct OOM**, `B512-b6m-hiT-r1` dump: DOB scratch 166 buffers = 436.8 MiB, of which **29 MutationStage buffers of
12,000,100 B (331.9 MiB)** plus 1 in use (5.7 MiB), and **83 kept 1,040,098 B buffers on NTR threads
(82.3 MiB)**; hints slab 32 MiB, `BufferPool` 16 MiB, 11.4 MiB unreferenced. The 12 MB buffers are
larger than L and so cannot be kept: they belong to writes between serialization and `close()` in
`CommitLog.add` (after `unsafeGetBufferAndFlip()` the position reads 0, so the reader's "idle" label does
not apply to them) — most plausibly waiting in `segmentManager.allocate`. The burst also erodes retention:
MutationStage threads that serialize a > 1 MiB mutation drop their kept buffer, so the hiT direct level
falls from ≈ 190 to ≈ 147 MiB across each burst, and only the NTR holders (≈ 83–117 MiB) stay on top of
the surge.

### 3.3 Diagnostic: retention alone at a tightened direct budget (heap 2 GiB, no burst)

One client IP, fill 4,000 × 520 KB; interleaved hi256 / loT / hi256L0, r1–r3 (amendment 3).

| Arm | Direct budget | Runs | Peak direct (pool) | Outcome | Evidence |
|---|---|---|---|---|---|
| `T160-hi256` (c = 256, L default) | 160 MiB | r1/r2/r3 | 159.8 / 159.7 / 159.7 | **direct OOM 3/3**, ≈ 8–10 s into the fill; forced heap OOM, dump, `kill -9` | dumps: 159.7–159.8 MiB charged to `Bits`, of which DOB scratch 108.1 MiB in 132–138 buffers (95–99 kept 1,040,098 B buffers on 85–91 NTR + 8–10 MS threads); hints slab 32, `BufferPool` 16 |
| `T160-loT` (c = 1) | 160 MiB | r1/r2/r3 | 60.2 / 61.2 / 60.7 (38%) | alive 3/3, 0 ERROR, 4,000 writes, 73–75 op/s | idle 58.1–59.1 MiB after the fill |
| `T160-hi256L0` (c = 256, `dob_max_recycle_bytes=0`) | 160 MiB | r1/r2/r3 | 71.0 / 72.5 / 71.9 (45%) | alive 3/3, 0 ERROR, 4,000 writes, 80–91 op/s (A-c256: 92) | idle back to 51.6–51.7 MiB: nothing kept |
| `T176-hi256` | 176 MiB | r1 | 175.6 | **direct OOM** (1/1) | DOB 124.0 MiB in 143 buffers |
| `T192-hi256` | 192 MiB | r1 | 190.7 (99%) | alive (1/1), 4,000 writes, 87 op/s | idle 188.5 MiB |

First error (r1–r3): `java.lang.OutOfMemoryError: Direct buffer memory` at `Bits.reserveMemory:175` ←
`DataOutputBuffer$1$1.allocate:87` ← `expandToFit:178` ← … `UnfilteredSerializer.writeEndOfPartition:415`
← `Mutation$MutationSerializer.serialization:455` ← `serializedSize:532` ← `Mutation.validateSize:171` ←
`SingleTableUpdatesCollector.toMutations:112` ← `ModificationStatement.execute` ← `Dispatcher.processRequest`,
on `Native-Transport-Requests-118/120`, then `JVMStabilityInspector` "Force heap space OutOfMemoryError in
the presence of" it, a heap dump and `kill -9` (excerpts `logs/T160-hi256-r*/first-oom.txt`, dump
summaries `logs/T160-hi256-r*/cassandra-*-analysis.txt`). The intervention keeps throughput (80–91 vs
92 op/s), so it does not protect by stopping work.

### 3.4 Side finding: Netty's separate direct counter (T176, four IPs; void for C3)

`T176-hiT` r1, r2 and `T176-hiTL0` r1 died in the four-IP fill with `io.netty.util.internal.OutOfDirectMemoryError:
failed to allocate 16777216 byte(s) of direct memory (used: 184549376, max: 184549376)` at only
108–126 MiB (L default) and 69 MiB (L = 0) of `Bits` memory; `T176-loT` r1, r2 survived (≤ 60 MiB).
Netty's pooled arenas count against their own limit equal to `MaxDirectMemorySize`, not against `Bits`
and not in the `java.nio` pool MXBean, so the JVM flag effectively allows up to twice its value of direct
memory. Not C3; recorded for the protection map of the native-transport path (B1, C2).

## 4. Conclusion

**Negative at defaults and an acceptable budget.** The per-thread retention cap holds (no kept buffer
above 1,040,098 B in any dump) and the number of holders is bounded by the shared executor pool:
161 SEP holders at the structural write-path ceiling (129 NTR + 32 MutationStage), plus 4 flush/compaction
threads. Retained DOB memory rose linearly with holders (6 → 142 MiB for 8 → 165 holders at matched
traffic) and idle direct memory topped out at 181–195 MiB in every four-IP fill, 38% of the 512 MiB
minimum acceptable budget; 0 of 7 four-IP fills at 512 MiB (and 0 of 4 at 2048 MiB) failed. By source the
retention ceiling is ≈ 216 MiB for a write-only workload and ≤ ≈ 330 MiB with every SEP stage saturated,
both below 512 MiB, so no default workload can make retention alone reach an acceptable direct budget on
this build. The protocol's feasibility screen and the measurements agree: **`negative · deployment`**
within heap 2 GiB, direct 512 MiB, 520 KB values, 1–512 client threads from 1–4 client IPs, single node.

**Retention plus a surge.** Retained buffers do add to other direct demand. With a large-mutation burst
after the fill, the high-holder arm peaked 45–95 MiB higher than the matched low-holder control (4 MB:
400–483 vs 306–390 MiB; 5 MB: 504–511 vs 402–468 MiB) and, at 6 MB, hit a direct OOM 26 s earlier than
the control hit a heap OOM. But the two arms never separated on the endpoint: both survive at 4 and 5 MB
(the high-holder arm pinned at the 512 MiB limit without an error), and both die at 6 MB. The surge,
not the retention, decides the outcome; it also erodes retention (MutationStage holders drop their kept
buffer after a > 1 MiB mutation), leaving only the NTR holders (≈ 83–117 MiB) on top of it.

**The mechanism exists below the acceptable range.** With the direct limit tightened to 160 MiB,
retention alone fails 3/3 with the first error in `DataOutputBuffer.expandToFit` on a native-transport
thread and ≈ 108 MiB of kept scratch buffers in the dump, while the matched low-holder fill (0/3) and the
same fill with `dob_max_recycle_bytes=0` (0/3, same throughput) survive. The largest budget retention
alone exhausts is 176 MiB (1/1); 192 MiB survives (1/1). That diagnostic result meets V1–V5 but not V7.

**Interpretation.** A bounded but uncovered multiplicity: `DOB_MAX_RECYCLE_BYTES` is a per-thread
retention cap with no aggregate counterpart, and the shared pool never shrinks, so idle nodes keep
T × ≤ 1 MiB of direct memory indefinitely after one burst of concurrency. At defaults T × L ≈ 165 MiB is
a sizing cost, not a failure, unless the direct limit is set below ≈ 200 MiB. Not a defect.

**Side findings (leads, not C3).**
1. *In-flight DOB growth (C2-type surge, `source: C3`).* A burst of 6 MB writes from 16 client threads
   at defaults ends in a direct OOM at 512 MiB (high-holder arm) or a heap OOM at 2 GiB (low-holder
   arm); 8 MB bursts reach 589–739 MiB of direct memory. The dump shows 29 `MutationStage` threads each
   holding a 12,000,100 B scratch buffer between serialization and `close()` in `CommitLog.add` (most
   plausibly waiting in `segmentManager.allocate`). The bound is ≈ `concurrent_writes` × 2 × mutation size
   (32 × 2 × 16 MiB = 1 GiB at `max_mutation_size`), not covered by any direct-memory control. Worth a
   C2-style case with its own control (bounded `concurrent_writes` or a commit-log path that does not
   hold the scratch buffer across allocation).
2. *Netty's separate direct counter.* Netty's pooled arenas are limited to `MaxDirectMemorySize` on a
   counter of their own (`OutOfDirectMemoryError ... max: 184549376` at 176 MiB), invisible to the
   `java.nio` pool MXBean; the JVM flag therefore admits up to twice its value. Relevant to B1/C2 and to
   every case that reads U from the `java.nio` pool alone.

**Limits.** One node size (16 hardware threads: `RequestResponseStage` and compaction bounds derive from
it); write-only fills (reads/counters could add up to ≈ 116 more SEP workers, still under 512 MiB by
arithmetic, not measured); 250 ms sampling understates burst peaks; per-thread retained size depends on
how often each thread was used (520,050 vs 1,040,098 B); the four-IP SNAT is an environment emulation;
the stated attempt limit was overrun by 5 executions (§2). The design's description of the
`Mutation.java:453` site was wrong (corrected in §1), without effect on the bound.

### Status per condition and V1–V7

| | Requirement | Retention alone, defaults, 512 MiB direct / 2 GiB heap (`negative`) | Diagnostic: retention alone, 160 MiB direct |
|---|---|---|---|
| V1 | Repetition | 7 four-IP (max-holder) fills at 512 MiB from clean starts (`B512-*-hiT-*`), 0/7 reach the endpoint (peaks 183–195 MiB); plus 4 four-IP fills at 2048 MiB (`A-c512x4`, `cal-b8m-hiT`, `cal-b8m4-hiT`, `cal-b4m-hiT`) | direct OOM 3/3 (`T160-hi256-r1..3`) |
| V2 | Matched control | low-holder fills (c = 1, same traffic) ×7 at 512 MiB (`B512-*-loT-*`), 57–59 MiB | `T160-loT` ×3, 0/3 |
| V3 | Measurement | U = `java.nio` direct pool every 250 ms, NMT, live heap dumps grouped by holder thread (phase A); no K exists | same + OOM dumps (108 MiB DOB of 159.8 MiB) |
| V4 | Intervention | not required for a negative; shown in the diagnostic column | `dob_max_recycle_bytes=0` ×3: 0/3 OOM, idle back to 51.6 MiB, throughput kept |
| V5 | Initiating failure | none (no failure) | first error + dump per run (§3.3) |
| V6 | Default constraints | met: L unset; worker bounds and in-flight limits unset (heap-derived values recorded) | met for the constraint (L default); intervention arm differs only |
| V7 | Acceptable budget | met: 512 MiB direct, 2 GiB heap (standing rule; auto 3982/7965 MiB) | **not met**: 160 MiB is tightened |
| | **Status** | **`negative · deployment`** | `reproduced-OOM · diagnostic` (largest failing budget 176 MiB) |

**Proposed filing.** Status `negative · deployment` for C3 at defaults; the case folder moves to
`cassandra/cases/negatives/DOB_MAX_RECYCLE_BYTES-worker-multiplicity/` when the researcher files it. The
diagnostic condition is recorded inside this case, not as a separate `reproduced` case. Phase B is
"not separating". New leads: in-flight DOB surge (C2-type) and Netty's double direct limit.
