# DOB_MAX_RECYCLE_BYTES + MAX_HINT_BUFFERS (custom) — hints slabs and kept DOB scratch buffers exhaust a shared direct-memory budget

**Direction:** convergence · standing-pool (hints pool) × multiplicity (per-thread DOB scratch retention).
**Regime:** custom capacities (`dob_max_recycle_bytes` = 8 MiB, `MAX_HINT_BUFFERS` = 8), tightened
direct-memory budget (`-XX:MaxDirectMemorySize=560m`). **Source:** Cassandra 5.0.9 (git tree
`b796bcfd…`), unmodified. **Runs:** run 8 (2026-11-03, `pc41`, one run per arm) and the R2 recheck
(2026-11-11, `apt140`, ×3 per arm); per-run records verbatim in [`history.md`](history.md).
**Consolidated:** 2026-11-11 (campaign-plan row R2).

| Condition | Status (protocol *Verification status*) |
|---|---|
| L = 8 MiB, n = 8, 560 MiB direct budget, `-Xmx3072M`, hints to a down replica then 4 MB local writes (8 client threads) | **`reproduced-OOM · diagnostic`** (3/3 on apt140; run 8 1/1 on pc41) |

> **Status amended 2026-11-11 (protocol *Defaults and acceptable budget*).** V1–V5 are met, so the
> result is reproduced and attributed, but *verified* now also needs V6 (constraints at defaults) and
> V7 (an acceptable budget). V6 not met: `dob_max_recycle_bytes` 8 MiB (default 1 MiB) and `MAX_HINT_BUFFERS` 8 (default 3). V7 not met: the 560 MiB `MaxDirectMemorySize` is deliberately tightened (`cassandra-env.sh` resolves ¼ RAM, 3982 MiB on apt140). Status therefore `reproduced-OOM · diagnostic`; filed in `candidates/`.
> Next step toward verified: the same mechanism with default constraints at a budget argued acceptable.

## Summary

- **Conclusion:** with the hints pool parked at its 8-slab cap (256 MiB) by writes to a down replica,
  a burst of 4 MB local writes ends in `OutOfMemoryError: Direct buffer memory` about 10 s in, 3 of 3
  runs on a second node (and once on the original node). Cassandra turns the direct OOM into a forced
  heap OOM, writes a heap dump, and `-XX:OnOutOfMemoryError=kill -9` kills the node. Each workload alone
  survives 3/3 (hints 49.6%, DOB 70.0–71.4% of the budget). This is a diagnostic result: it needs the
  tightened 560 MiB direct budget and both custom capacities.
- **Root cause:** two controls each hold, but nothing caps their sum. `MAX_HINT_BUFFERS` bounds the
  hints pool to n × 32 MiB slabs that are never freed; `dob_max_recycle_bytes` bounds what *each thread*
  keeps (≤ L), not how many threads keep one. Local writes run on shared-pool worker threads (both
  `MutationStage` and inline on `Native-Transport-Requests` threads), so every worker that once
  serialized a 4 MB mutation keeps a 7.63 MiB direct buffer. All three heap dumps at the OOM show the
  same split of the 560 MiB `Bits` limit: 36 kept DOB scratch buffers (≈ 282 MiB, 34–36 of them idle) +
  8 hint slabs (256 MiB) + ≈ 21 MiB other.
- **Causal test:** with only `dob_max_recycle_bytes` back at its 1 MiB default (DOB keeps nothing), the
  same workloads survive 3/3 with the hints pool still full. The margin is thin: transient in-flight
  growth still reached 522–526 MiB (93–94%) in 2 of 3 runs.
- **Interpretation:** a configuration-sizing / validation gap (no aggregate control over direct
  buffers other than the JVM limit), not a counter defect. Both settings are restart-only JVM
  properties and are not validated against `MaxDirectMemorySize`.

## 1. Constraints, protection map and configuration

| Field | Hints pool (`MAX_HINT_BUFFERS`) | DOB scratch retention (`DOB_MAX_RECYCLE_BYTES`) |
|---|---|---|
| Allocation / ownership | `HintsBuffer.create` → `ByteBuffer.allocateDirect(slabSize)` (`HintsBuffer.java:60,77`); held in `HintsBuffer.slab`, recycled into `reserveBuffers`, freed only on `close()` | `DataOutputBuffer.scratchBuffer`, a `FastThreadLocal<DataOutputBuffer>` (`DataOutputBuffer.java:63`); growth via `expandToFit` → `allocate` → `ByteBuffer.allocateDirect` (`:87,178`); old buffer freed at once (`setBuffer` → `FileUtils.clean`) |
| Local contract (C) | New slab only while `allocatedBuffers < MAX_ALLOCATED_BUFFERS`, else the writer waits in `reserveBuffers.take()` (`HintsBufferPool.java:111-118`): hard cap n × `bufferSize`, `bufferSize = max(2 × max_mutation_size, 32 MiB)` = 32 MiB (`HintsService.java:110`) → **256 MiB** at n = 8 | On `close()`, keep the buffer if `capacity <= L`, else replace with 128 B (`DataOutputBuffer.java:73`): retention cap **L = 8 MiB per thread**. It caps idle retention only, not in-flight growth |
| Scope / multiplicity | One pool per node | Per thread. *T* = shared-pool (SEP) worker threads that ever serialized a large mutation; bounded only by pool sizes (`MutationStage` workers plus native-transport threads, which run local writes inline: `SEPExecutor.maybeExecuteImmediately` ← `StorageProxy.performLocally`, seen in the OOM stacks). Measured *T* ≈ 45 (D_alone), 36 at the OOM |
| Aggregate coverage | None besides the JVM direct limit | None: no counter of total kept bytes; T × L is uncovered |
| Lifetime | Standing (slabs recycled, never freed) | Standing per thread until that thread's next use |
| Budget | `-XX:MaxDirectMemorySize` (`Bits.reserveMemory`), shared by both (both use `allocateDirect`). Netty's pooled arenas and file mappings (commit-log segments) are not charged to it | same |

**Measured quantities.** U (physical, independent of any control counter) = JDK direct pool
`MemoryUsed`/`Count` (MXBean `java.nio:type=BufferPool,name=direct`) every 5–9 s, live `HintsBuffer`
count from `GC.class_histogram`, and in the OOM heap dumps the capacity of every `DirectByteBuffer` that
owns `Bits` memory, grouped by holder. K = the pool's `allocatedBuffers` (never read; the slab count is
taken from the heap). C as in the table.

**Configuration labels.** Capacities: L = 8 MiB (default 1 MiB) and n = 8 (default 3), both **custom**,
set as JVM properties (`-Dcassandra.dob_max_recycle_bytes`, `-Dcassandra.MAX_HINT_BUFFERS`). Budget:
`-XX:MaxDirectMemorySize=560m`, a **deliberately tightened diagnostic** budget (resolved default on
apt140 would be 3982 MiB from `cassandra-env.sh`; the later 560m flag wins, confirmed by the OOM level);
`-Xms/-Xmx3072M` sized so the heap never binds. Everything else is the shipped `cassandra.yaml` plus ring
settings (2-node loopback ring, `num_tokens: 1`, `GossipingPropertyFileSnitch`, local directories,
`max_hint_window: 24h`: environment/supporting). Supporting deviations: the tightened budget; the
second node exists only to be down (topology needed for hints). → **diagnostic**.

**Environment.** Run 8: `pc41` (40 cores, 251 GiB). Recheck: `apt140`
(`node0.jason92-325433.misconfiguration-pg0.apt.emulab.net`, APT r320, 16 threads Xeon E5-2450 2.1 GHz,
15.5 GiB RAM, 8 GiB swap, Linux 5.15.0-198, cgroup v2, OpenJDK 11.0.33); build copy
`/mydata/oom-recheck/R2/cassandra` (same source tree as run 8's build). Disclosed effects of the node
change: idle direct 51 vs 55 MiB; the hints pool needs 47–84 s instead of ≈ 18 s to reach 8 slabs
(lead time amended, §2); DOB keeps a few more buffers (+341–349 vs +334 MiB).

## 2. Verification design

Full pre-reading design, predictions and the dated amendment: [history, R2 recheck design](history.md#recheck-design-2026-11-11)
(run 8's design: [history, run 8 §2](history.md#run-8)).

- **Topology:** N1 127.0.0.2 (dc1, measured), N2 127.0.0.3 (dc2) up only for ring and schema, then
  `kill -9`. Keyspaces `dobks {dc1:1}` (never hinted), `hintks {dc1:1, dc2:1}` (every write hints N2).
  Fresh ring and data for every arm.
- **Workloads** (`cassandra-stress user`, profiles without schema statements): *hints* 6,000,000 × 1 KiB
  rows, 64 threads, CL ONE, capped at 240 s; *dob* 1,500 × 4,000,000-byte rows, 8 threads, CL ONE. Each
  4 MB mutation grows a scratch buffer to 8,000,100 B (7.63 MiB ≤ L, so it is kept).
- **Arms** (harness [`oom-run.sh`](oom-run.sh) as filed, recheck copy with paths/pins/instrumentation in
  [`recheck-2026-11-11/harness-R2.diff`](recheck-2026-11-11/harness-R2.diff), driven by
  [`run-seq.sh`](recheck-2026-11-11/run-seq.sh); pinned `N_HINTS=6000000 N_DOB=1500`, converge arms
  `HINT_LEAD=50`):
  `H_alone` = `arm H_alone 560 8388608 8 hints`; `D_alone` = `arm D_alone 560 8388608 8 dob`;
  `converge` = `arm converge 560 8388608 8 hints,dob overlap`; intervention `converge_Ldefault` =
  `arm converge_Ldefault 560 1048576 8 hints,dob overlap`.
- **Amendment (2026-11-11, before any converge reading).** `HINT_LEAD` 20 → 50 so the DOB burst starts
  after the pool is at its cap on this slower node (effective lead 118–125 s instead of ≈ 35 s on pc41);
  per-run gate: direct ≥ 275 MiB in the last sample before the burst. The filed condition is otherwise
  unchanged; D_alone's 70.0–71.4% was recorded as a margin miss, not resized.
- **Predictions:** H_alone ≈ 281 MiB (50%), D_alone ≈ 340–400 MiB, converge ≈ 623 MiB demand → direct
  OOM within ≈ 5–20 s of the burst; converge_Ldefault ≈ 51% (DOB keeps nothing).
- **Validation (modest load, 4096 MiB budget, `recheck-2026-11-11/logs/val/`):** ring, both workloads
  and both pools reachable (300,000 hints → 3 slabs; 100 DOB writes → +107 MiB kept), 0 errors.
- **Stopping budget:** ≤ 4 h, ≤ 20 arm executions. Used: ≈ 2 h 05 min, 13 executions.

## 3. Runtime results

Recheck logs (excerpts): `recheck-2026-11-11/logs/<arm>-rN/` (`summary.txt` holds every sample). Full
logs and the three heap dumps stay on apt140 in `/mydata/oom-recheck/R2/logs/`. Run 8's single runs are
in [`logs/`](logs/) and [history §3](history.md#run-8).

| Arm | Run | Idle | Peak direct (sampled) | % of 560 | Pool / retention evidence | Outcome |
|---|---|---|---|---|---|---|
| `H_alone` | r1 | 51 | 278 | 49.6% | 8 `HintsBuffer`s; once at cap, a writer parked in `take()` and 32 on the pool monitor in the jstack samples; at cap after 73 s; 5,187,424 server-side writes in 240 s | alive, 0 ERROR |
| | r2 | 51 | 278 | 49.6% | 8; at cap after 84 s; 5,035,373 writes | alive, 0 ERROR |
| | r3 | 51 | 278 | 49.6% | 8; at cap after 47 s; 5,082,239 writes | alive, 0 ERROR |
| `D_alone` | r1 | 51 | 400 | 71.4% | +349 MiB kept, flat through the hold; 1 `HintsBuffer`; 1,500 writes (9 op/s) | alive, 0 ERROR |
| | r2 | 51 | 393 | 70.2% | +342 MiB; 1,500 writes | alive, 0 ERROR |
| | r3 | 51 | 392 | 70.0% | +341 MiB; 1,500 writes | alive, 0 ERROR |
| `converge` | r1 | 51 | 277 before the burst; **560 at the OOM** (dump) | **100% → OOM** | pool at cap at the burst (277 MiB, writer parked); burst 118 s after hints start | **direct OOM** 9.6 s into the burst (`MutationStage-54`); heap dump 1.06 GB; JVM killed |
| | r2 | 51 | 277 before; **560** | **OOM** | 277 MiB at the burst; lead 124 s | **direct OOM** 9.9 s in (`MutationStage-26`, `Native-Transport-Requests-25`); dump 0.89 GB; killed |
| | r3 | 51 | 277 before; **560** | **OOM** | 277 MiB, writer parked; lead 125 s | **direct OOM** 10.2 s in (`Native-Transport-Requests-38`); dump 1.04 GB; killed |
| `converge_Ldefault` | r1 | 51 | 526 (transient; plateau 277–293) | 93.9% | 8 `HintsBuffer`s at the end; lead 121 s | alive, 0 ERROR; DOB 1,500 writes (7 op/s), hints 3,079,832 |
| | r2 | 51 | 522 (transient) | 93.2% | 8; lead 122 s | alive, 0 ERROR; DOB 1,500 (6 op/s), hints 3,155,185 |
| | r3 | 51 | 395 (transient) | 70.5% | 8; lead 119 s | alive, 0 ERROR; DOB 1,500 (7 op/s), hints 3,107,785 |

**First error (all three converge runs, `n1-system-first-oom.txt`).** `java.lang.OutOfMemoryError: Direct
buffer memory` at `Bits.reserveMemory:175` ← `DataOutputBuffer$1$1.allocate:87` ← `expandToFit:178` ←
`BufferedDataOutputStreamPlus.writeByte:162` ← `UnfilteredSerializer.writeEndOfPartition:415` ← …
`Mutation$MutationSerializer.serialize:414` ← `CommitLog.add:308` ← `Keyspace.apply` ←
`StorageProxy$LocalMutationRunnable.run`, on a `MutationStage` worker, or inline on a
`Native-Transport-Requests` thread (`SEPExecutor.maybeExecuteImmediately` ← `StorageProxy.performLocally`).
The same stack as run 8. Then `JVMStabilityInspector` "Force heap space OutOfMemoryError in the presence
of" the direct OOM, a `HeapDumper` safepoint, `ReportJavaOutOfMemory`, and `kill -9`. G1 old generation
held 0.76–0.91 GB of 3 GB at the last GCs (`GCInspector`), so the heap was not the cause. No kernel
OOM-kill (`dmesg` empty).

**Heap-dump breakdown (V5; `hprof-analysis.txt` per converge run).** Method: a small python HPROF reader
([`recheck-2026-11-11/tools/hprof_direct.py`](recheck-2026-11-11/tools/hprof_direct.py), run on the node
with `python3 -I`, ≈ 50 s and 0.44 GB RSS per 1 GB dump; no MAT). It sums the capacities of
`DirectByteBuffer`s that own `Bits` memory (`cleaner != null`, `att == null`, `fd == null`; views and
file mappings excluded) and groups them by referring object. Identical in r1–r3:

| Holder | Buffers | MiB |
|---|---|---|
| `DataOutputBuffer$1$1.buffer` (thread-local DOB scratch) | 36 × 8,000,100 B + 2 × 4,000,050 B (+ 76 small) | 282.4 |
| `HintsBuffer.slab` (hints pool) | 8 × 33,554,432 B | 256.0 |
| `BufferPool$Chunk.slab` | 2 | 16.0 |
| Netty `EpollEventArray`, read-ahead blocks, hints write buffer, misc | ≈ 140 | ≈ 5 |
| **Total charged to `Bits`** | 256–263 | **559.5** (586.7 M of 587.2 M bytes) |
| Not charged: commit-log `MemoryMappedSegment` mappings | 7–8 | 224–256 |

Of the 36 full-size scratch buffers, 34 (r1) and 36 (r2, r3) were idle (position 0, i.e. cleared by
`close()` and kept), held by `Native-Transport-Requests` and `MutationStage` workers (r1 26 + 8, r2 21 + 15,
r3 12 + 24); at most 2 were in use. So the DOB share at the OOM is retained memory, not in-flight writes.
Only 2 owners had no strong referrer (0 B).

**V3 (U apart from K).** Hints: U = 277–278 MiB plateau in the direct pool (51 idle + 7 × 32 MiB),
8 live `HintsBuffer`s by histogram, and 8 × 32 MiB slabs in each dump; `allocatedBuffers` never read.
DOB: U = +341–349 MiB (≈ 45 buffers) in D_alone, and 282 MiB in 36 kept buffers at the OOM; Cassandra has
no aggregate counter to compare. Every kept buffer is ≤ L, and the slabs are = C: **U ≤ C in each domain,
ΣU + baseline = budget → convergence** (protocol *Classification by measurement*).

**Memory fit on apt140.** N1 `VmSwap` = 0 kB in every sample of every arm; system swap used 3–8 MiB
(pre-existing); `MemAvailable` ≥ 9.9 GiB throughout.

**Client counts.** The DOB client reports 1,500 partitions and 0 errors in the converge runs (90–128 op/s):
1,435–1,441 of those are `NoHostAvailableException` after the kill, which this cassandra-stress counts as
done. Server-side `tablestats` are used for the alone and intervention arms. The hints client hit its
240 s cap in every arm (no summary line); its `WriteTimeoutException`s (≈ 1,100–1,200 alone, 2,200–3,000 in
the intervention) are retried. The DOB client saw 495–683 write timeouts per alone/intervention run
(retried); retries add server-side in-flight writes beyond the 8 client threads.

**Intervention (V4) throughput.** `converge_Ldefault` completes all 1,500 DOB writes (6–7 op/s vs 9 op/s
alone) while hint writes drop to 3.08–3.16 M in 240 s (vs 5.04–5.19 M alone; run 8: 2.89 M), so the
intervention does not stop useful work. Its direct use stays on the hints plateau (277–293 MiB) with
transient spikes to 351–526 MiB: with L = 1 MiB nothing is kept, but every in-flight 4 MB write still
grows a buffer to 7.63 MiB (with an old/new overlap during the last doubling), and concurrent in-flight
writes (client threads plus retries) briefly reach ≈ 245 MiB. At this budget the default L removes the OOM
3/3, but with as little as ≈ 34 MiB headroom.

## 4. Conclusion

**The pair converges to a direct-buffer OOM, reproducibly.** On a second node, with the run-8 build,
settings, budget and workloads, `converge` reached `OutOfMemoryError: Direct buffer memory` 3/3 about
10 s into the DOB burst, while the hints pool alone (3/3, 49.6%) and the DOB workload alone (3/3,
70.0–71.4%) survived, and setting only `dob_max_recycle_bytes` back to its default removed the OOM 3/3.
The dumps put the limit exactly at 8 hint slabs (256 MiB) + 36 kept 7.63 MiB DOB scratch buffers
(282 MiB) + ≈ 21 MiB of other direct buffers.

**Root cause.** Each control holds its local contract: the hints pool stopped at 8 slabs with a writer
parked, and every kept scratch buffer is ≤ L. Neither bounds the aggregate. The DOB retention cap is per
thread, and the number of threads that keep one grows with the shared worker pool (native-transport
threads run local writes inline, so they keep buffers too); T × L has no limit below
`MaxDirectMemorySize`. Cassandra converts the resulting direct OOM into a forced heap OOM and a JVM kill.

**Limits of the result.**
- Diagnostic: the 560 MiB direct budget is deliberately tight, and both capacities are custom. At the
  defaults (n = 3, L = 1 MiB) the same mechanism needs a much smaller budget (separate case, R6).
- D_alone used 70.0–71.4% on apt140 (run 8: 69.5%): the declared 30% free margin is missed by up to
  1.4 pp. The control still survives 3/3 with ≥ 160 MiB headroom, and the dumps attribute both holders,
  so the convergence reading stands; the margin miss is disclosed, not hidden by resizing.
- The lead time was amended for the slower node (≈ 120 s instead of ≈ 35 s); the mechanism and order
  (pool full first, then the burst, both running) are unchanged.
- The intervention's survival margin is thin (transient 93–94% in 2/3 runs). It shows the kept buffers
  are what tip the budget; it does not show that the default L is safe against in-flight growth at this
  budget in general.
- Minimum boundary not searched (sizing as filed, ≈ 10–11% predicted overshoot).

**Target-3 note** (unchanged from run 8): moderately realistic. Raising `dob_max_recycle_bytes` for
multi-MB rows and running with a replica down are both ordinary; raising `MAX_HINT_BUFFERS` is less
common; `MaxDirectMemorySize` is often set below `-Xmx` in containers.

## V1–V5

| | Requirement | Evidence | Met |
|---|---|---|---|
| V1 Repetition | Endpoint ≥ 3 runs from clean starts | `converge` r1–r3: direct-buffer OOM 3/3 (plus run 8, 1/1, other node) | yes (3/3) |
| V2 Matched control | Nearest surviving control ×3, same budget/build | `H_alone` r1–r3 alive (49.6%); `D_alone` r1–r3 alive (70.0–71.4%; 70% margin missed by ≤ 1.4 pp, disclosed) | yes (margin note) |
| V3 Measurement | U apart from K per domain | Direct pool `MemoryUsed`/`Count`, `HintsBuffer` histogram, dump capacities by holder (§3); K not used | yes |
| V4 Intervention | Removes the endpoint ≥ 3 runs, load recorded | `converge_Ldefault` r1–r3 alive; DOB 1,500/1,500, hints 3.08–3.16 M server-side writes; transient peaks 70.5–93.9% | yes (thin margin) |
| V5 Initiating failure | First error with thread/stack + histogram/dump at failure | `n1-system-first-oom.txt` (r1–r3); dumps analysed (`hprof-analysis.txt` r1–r3): 8 slabs + 36 kept scratch buffers = 559.5 MiB | yes |

## Instrument check and process hygiene

- Each arm's N1 command line was checked for `-Xmx3072M`, `-XX:MaxDirectMemorySize=560m`, both
  properties and the intervention's L = 1048576 (`n1-jvm-args-excerpt.txt`, `CHECK PASS` in the node's
  `session.log`). `cassandra-env.sh` sets `MaxDirectMemorySize=3982M` first; the later value wins
  (OOM at 559.5 MiB).
- Heap dumps went to the arm folder on `/mydata` (`CASSANDRA_HEAPDUMP_DIR`); nothing heavy was written to
  `/proj`; `systems/cassandra/source/` was only read.
- After every arm `pgrep` found no `CassandraDaemon` or `cassandra-stress` (`run-A.log`, `run-B.log`);
  after the analysis nothing of this run was left running on apt140. Run data, full logs and dumps:
  `/mydata/oom-recheck/R2/` on apt140.
