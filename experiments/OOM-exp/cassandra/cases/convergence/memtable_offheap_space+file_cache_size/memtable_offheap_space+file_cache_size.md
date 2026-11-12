# memtable_offheap_space + file_cache_size — off-heap memtable and chunk cache converge past a 3500 MiB cgroup

**Direction:** convergence · standing-pool. **Lead source:** if-check-exp (two true positives, see §1).
**Regime:** custom capacities. **Source:** Cassandra 5.0.9 (source tree `b796bcfd…`). **Runs:** run 7
(2026-11-03, `pc41`, one run per arm) and the V1–V5 recheck R1 (2026-11-11, `pc96`, ×3 per arm); full
per-run records, the recheck design and its amendments in [`history.md`](history.md). **Consolidated:** 2026-11-11.

| Condition | Status (protocol *Verification status*) |
|---|---|
| 3500 MiB cgroup (`MemorySwapMax=0`), `-Xmx768M`, `memtable_offheap_space` = `file_cache_size` = 1200 MiB, `offheap_objects`, `memtable_cleanup_threshold` 0.99; chunk cache filled by a read pass, then a 64-thread write burst | **`verified-OOM · diagnostic`** |

## Summary

- **Conclusion:** each pool alone, driven to its own cap, stays at 76–78% of a 3500 MiB cgroup (6/6
  survived). With the chunk cache parked at its 1200 MiB cap, the off-heap memtable's first fill pushes the
  JVM past the budget and the **kernel memcg OOM-killer kills it 7–11 s into the write burst, 3/3** (run 7:
  1/1). The kill comes from the budget, not from either pool overrunning: the chunk-cache pool sits exactly at
  its 1200 MiB threshold and the memtable counter is at 283–738 MiB (≤ about 790 MiB physical) when it happens.
  Lowering `file_cache_size` to 300 MiB, with the same workload and the same write throughput, removes the kill
  (3/3). Diagnostic: tightened budget, deprecated `memtable_cleanup_threshold: 0.99`.
- **Root cause:** both settings are hard, independently enforced standing caps outside the Java heap, and
  nothing relates their sum (plus heap and load overhead) to the memory the process actually has. Cassandra
  sizes both defaults from the heap (memtable ¼ heap, file cache min(512 MiB, ¼ heap)) and accepts any custom pair without a cross-check, so two
  values that are each safe add up past a container limit. A configuration-sizing/validation gap, not a
  defect in either control.

## 1. Constraints, protection map, configuration labels

| | `memtable_offheap_space` | `file_cache_size` |
|---|---|---|
| if-check-exp | [`memtable_offheap_space-tryAllocate-limit--guided`](../../../../../capacity-enforcement-exp/cassandra/stage3-ai-deep-read/cases/memtable_offheap_space-tryAllocate-limit--guided.md), true positive | [`file_cache_size-allocateMoreChunks-memoryUsageThreshold--guided`](../../../../../capacity-enforcement-exp/cassandra/stage3-ai-deep-read/cases/file_cache_size-allocateMoreChunks-memoryUsageThreshold--guided.md), true positive |
| Allocation (pinned source) | `NativeAllocator.allocate` charges the off-heap sub-pool, then copies into 1 MiB regions from `MemoryUtil.allocate` → `com.sun.jna.Native.malloc` (glibc malloc; **not** in NMT or the JDK direct counter); regions freed after flush (`NativeAllocator.java:46,138–205`, `MemoryUtil.java:81–89`) | `ChunkCache` (Caffeine, `maximumWeight = file_cache_size − 32 MiB`) over `BufferPool` "chunk-cache", threshold `file_cache_size`; 8 MiB macro chunks (`MACRO_CHUNK_SIZE` = 64 × 128 KiB; the recheck design said 1 MiB, corrected here) by `ByteBuffer.allocateDirect` (zeroed, resident; in NMT *Other* and the JDK direct counter), never returned; overflow beyond the threshold also `allocateDirect` (`ChunkCache.java:49–50,152–154`, `BufferPool.java:233–239,438–460,1095–1101`, `BufferPools.java:38–39`) |
| Contract C | 1200 MiB, hard: writers block in `allocate` at the limit; the region slack above the counter is ≤ 1 MiB per memtable | 1200 MiB pool reservation (150 macro chunks; `Maximum memory usage reached (1.172GiB) for chunk-cache buffer pool` logged when refused), cache weight ≤ 1168 MiB |
| Counter K | `type=Table,name=AllMemtablesOffHeapDataSize` (sum of allocator `owns`) | `type=BufferPool,scope=chunk-cache,name=Size`; `type=Cache,scope=ChunkCache,name=Size` |
| Independent U | resident growth of RssAnon over the burst, corrected for glibc-retained free memory (§3.3) | JDK `java.nio:type=BufferPool,name=direct` `MemoryUsed` (resident; idle share ≈ 48 MiB) |
| Lifetime | standing while the memtable fills; under 0.99 cleanup it flushes only at the cap; glibc keeps freed regions | standing; the reservation is never released |
| Aggregate coverage | none: no check relates the sum of the two, the heap and the process budget (`DatabaseDescriptor.java:576–594` only fills heap-derived defaults) | same |
| Budget | cgroup v2 `memory.max` 3500 MiB on the JVM only (`systemd-run --user --scope -p MemoryMax=3500M -p MemorySwapMax=0`); read as `RssAnon`, cgroup `anon`, `memory.events`, `dmesg` | same |

**Labels.** Capacities custom (`memtable_offheap_space` 1200, `file_cache_size` 1200, `memtable_heap_space`
200); `memtable_allocation_type: offheap_objects` and `file_cache_enabled: true` are documented values. Budget:
deliberately tightened diagnostic cgroup 3500 MiB with `-Xmx768M`. Supporting deviation:
`memtable_cleanup_threshold: 0.99` (deprecated; parks writers at the cap; the default would flush earlier).
Environment: one node, client on the same host outside the cgroup. → **diagnostic**.

**Configuration and environment audit (recheck).** `pc96`: 2 × Xeon E5-2667 v2 (32 cores, 2 NUMA nodes),
125 GiB, 8 GiB swap (excluded by `MemorySwapMax=0`), Ubuntu 22.04, kernel 5.15.0-198, glibc 2.35, cgroup v2,
OpenJDK 11.0.33, G1. Build `/mydata/oom-recheck/R1/cassandra` (`cp -a` of `/mydata/b6/cassandra`, HEAD
`f2de695`, tree `b796bcfd…`, clean). Resolved: `MALLOC_ARENA_MAX=4`, `MaxDirectMemorySize=15872M`,
`-XX:+AlwaysPreTouch` (heap resident from start), `-Dio.netty.allocator.maxOrder=11`. Run 7 ran on `pc41`
(40 cores, 251 GiB). **Environment changes disclosed:** node/CPU count (G1 threads 23 vs 28; Netty arenas
64 vs 80, ≈ 1 GB of mostly untouched arena malloc on pc96), and the recheck's added instruments
(`-XX:NativeMemoryTracking=summary`, a JMX poller outside the cgroup every 2 s, `jcmd` every 5 s in the burst).
Complete yaml diff in every arm folder (`cassandra.yaml.diff`).

## 2. Verification design

Run 7 design: [history.md § Run 7](history.md#run-7). Recheck design (written before any 3500 MiB reading),
its validation note and the two amendments: [history.md § Recheck design](history.md#recheck-design).

- **Workloads** (unchanged from run 7): *preload* `cassandra-stress write n=800000` (5 × 1 KiB columns) into
  `dataks`, flush, autocompaction off; *cachefill* one read pass over all 800,000 partitions, 64 threads;
  *memburst* `cassandra-stress write n=2000000` into `memks`, 64 threads, `retries=50`, cap 240 s.
- **Arms** (3500 MiB each, from clean starts, data and logs on `/mydata`): `M_alone` (M = 1200, F = 64,
  memburst), `F_alone` (M = 64, F = 1200, preload + cachefill), `converge` (M = F = 1200, preload → cachefill →
  memburst), intervention `int_F300` (M = 1200, **F = 300**, same three workloads). Order: M_alone-1, F_alone-1,
  check, then converge-1, M_alone-2, F_alone-2, converge-2, M_alone-3, F_alone-3, converge-3, int_F300-1..3, and
  a supplementary uninstrumented converge (amendment 2).
- **Harness:** [`oom-run.sh`](oom-run.sh) (run 7) with minimal recheck changes
  ([`recheck-2026-11-11/harness.diff`](recheck-2026-11-11/harness.diff)): paths, scope prefix, NMT, JMX poller
  ([`PoolPoller.java`](recheck-2026-11-11/harness/PoolPoller.java)), NMT samples, a poller-off switch, tighter
  process matching. Versions: v1 ran `val_modest`, `M_alone-1`, `F_alone-1`; v2 (process matching only,
  [`harness-v1-to-v2.diff`](recheck-2026-11-11/harness-v1-to-v2.diff)) the nine arms after the check; v3 (poller-off
  switch, [`harness-v2-to-v3.diff`](recheck-2026-11-11/harness-v2-to-v3.diff)) only `converge-noinst`. Driver [`run-all.sh`](recheck-2026-11-11/harness/run-all.sh), digests
  [`analyze.py`](recheck-2026-11-11/harness/analyze.py), kernel record
  [`dmesg-block.sh`](recheck-2026-11-11/harness/dmesg-block.sh).
- **Stopping budget:** ≤ 7 h wall, ≤ 18 arm executions. Used: 14 executions (incl. one 8000 MiB instrument
  validation and the uninstrumented check), 14:40–17:59 EST (3 h 20 min of arms), filing after.

## 3. Results

Raw logs: `/mydata/oom-recheck/R1/logs/` on `pc96` (run 7: `~/oom-offheap-run7/logs/` on `pc41`). Excerpts
per arm: [`recheck-2026-11-11/logs/`](recheck-2026-11-11/logs/) (`digest.txt`, `summary.txt`,
`pools-excerpt.csv`, `dmesg-block.txt`, stress tails, flush lines, NMT); run 7: [`logs/`](logs/).

### 3.1 Per arm (recheck, pc96)

| Arm | Idle RssAnon | Peak RssAnon (% of 3500) | Pools reached | Workload | Outcome |
|---|---|---|---|---|---|
| `M_alone-1` | 1261 | 2660 (76.0%) | memtable: 8 flushes at 99–100% off-heap, `BlockedOnAllocation` 527 | burst 2,000,000 writes, 16,471 op/s, 0 errors | alive |
| `M_alone-2` | 1247 | 2671 (76.3%) | 8 flushes at 99–100%, blocked 821 | 16,786 op/s, 0 errors | alive |
| `M_alone-3` | 1247 | 2715 (77.6%) | 8 flushes at 99–100%, blocked 729 | 16,651 op/s, 0 errors | alive |
| `F_alone-1` | 1243 | 2670 (76.3%) | pool 1200 MiB, cache 1168 MiB (149,503 entries), direct 1248 | 800,000 reads, 2,297 op/s | alive |
| `F_alone-2` | 1250 | 2677 (76.5%) | same | 2,058 op/s | alive |
| `F_alone-3` | 1248 | 2692 (76.9%) | same | 1,475 op/s | alive |
| `converge-1` | 1257 | 3019 sampled; **3467 at kill** | cache full (pool 1200) before burst; memtable K 283 at +7 s | reads 657 op/s; burst killed at +7–9 s | **kernel memcg OOM-kill** |
| `converge-2` | 1249 | 3264 sampled (93.3%); **3467 at kill** | same; memtable K 626 at +8 s | reads 665 op/s; killed at +8–10 s | **kernel memcg OOM-kill** |
| `converge-3` | 1243 | 3361 sampled (96.0%); **3468 at kill** | same; memtable K 738 at +9 s | reads 767 op/s; killed at +9–11 s | **kernel memcg OOM-kill** |
| `int_F300-1` | 1248 | 2974 (85.0%) | pool 296, cache 268 MiB (full); memtable 8 flushes at 99–100%, max K 1200 | reads 1,164 op/s; burst 2,000,000, 16,525 op/s, 0 errors | alive |
| `int_F300-2` | 1243 | 2959 (84.5%) | same; max K 1171 | reads 1,087 op/s; burst 16,769 op/s, 0 errors | alive |
| `int_F300-3` | 1244 | 2964 (84.7%) | same; max K 1167 | reads 901 op/s; burst 16,956 op/s, 0 errors | alive |
| `converge-noinst` (NMT and poller off) | 1242 | 2982 at +5 s (5 s `/proc` sampling only); **3468 at kill** | cache full (1.14 GiB) before the burst | reads 770 op/s; killed at +5–10 s | **kernel memcg OOM-kill** |

MiB throughout. "Sampled" = highest 2 s poller row; the kill falls between two rows, so the at-kill value is
the kernel's `anon-rss`. Run 7 (pc41): `M_alone` 2717 (77.6%), `F_alone` 2721 (77.7%), `converge` killed 16 s
into the burst at 3465 MiB.

### 3.2 At the kill (V5)

| | converge-1 | converge-2 | converge-3 |
|---|---|---|---|
| `dmesg` | `MutationStage-8 invoked oom-killer` (GFP_NOFS, ext4 page-fault on a commit-log mapping) | `MutationStage-4` (GFP_HIGHUSER_MOVABLE, file page fault) | `MutationStage-7` (GFP_HIGHUSER_MOVABLE, file page fault) |
| `oom_memcg` = this arm's scope; killed PID = node PID | yes (611747) | yes (637832) | yes (666102) |
| memcg usage / limit; memcg `anon` | 3584000 / 3584000 kB; 3471 MiB | same; 3471 MiB | same; 3471 MiB |
| killed `anon-rss` | 3550016 kB (3467 MiB) | 3550448 kB | 3551048 kB |
| last poller row before the kill | +7 s: RssAnon 3019, heap 270 used / 768 committed | +8 s: 3264, heap 340 | +9 s: 3361, heap 430 |
| chunk cache: JDK direct / pool Size / cache Size | 1248 / 1200 / 1168 | 1248 / 1200 / 1168 | 1248 / 1200 / 1168 |
| memtable K (`memks`) / writes done | 283 / 56,619 | 626 / 125,222 | 738 / 147,702 |
| last NMT (≤ 5 s): heap / class / thread / code / GC / Other | 768 / 66 / 104 / 48 / 127 / 2288 | 768 / 66 / 105 / 48 / 127 / 2288 | 768 / 66 / 105 / 49 / 127 / 2288 |

No `OutOfMemoryError`, no ERROR line in any arm; a kernel kill leaves no JVM dump, so the per-pool rows stand in
for the histogram. The invoking allocation differs (a commit-log page, a file page): in every case the cgroup's
anon memory had filled the budget and the next charge of any kind failed. Kernel time stamps (`sched_clock`)
run ≥ 3–4 s behind wall time here; the kill time is bracketed by the last full poller row and the first empty one.

### 3.3 U against C per domain (V3)

- **Chunk cache:** U = JDK direct − idle direct ≈ 1248 − 48 = **1200 MiB = C**, resident (direct buffers are
  zeroed at allocation); K (pool Size) = 1200, cache weight 1168 ≤ 1168. No overflow (`OverflowSize` 0) in any arm.
  NMT *Other* (2288 MB) is not usable as a resident measure: it adds ≈ 1040 MB of Netty pool arenas that are
  malloc'd but mostly untouched (NMT committed total 3431 MB > RssAnon 2980 MiB at the same moment).
- **Memtable:** K ≤ C in every arm (max 1200 in `int_F300-1`, flush enqueued at 99–100%). Physical U at the kill
  is bounded without K: RssAnon grew 487 / 482 / 557 MiB from the pre-burst row to the kill, and the memtable can
  additionally have reused at most the glibc-retained memory the preload's flushed memtable left behind, measured as
  converge pre-burst RssAnon − `F_alone` after-cachefill RssAnon (mean 2675) = 305 / 310 / 236 MiB. So **U ≤ 792 /
  792 / 793 MiB < C**, and U ≥ K at the last row (283 / 626 / 738; regions are filled by copying). In `M_alone`
  RssAnon − idle = 1399–1468 MiB with the memtable at its cap, i.e. the cap plus ≈ 200–270 MiB of write-load
  overhead, consistent with U ≈ K.
- **Sum:** heap 768 (pre-touched) + chunk cache 1200 + memtable 283–738 (K) + the rest (≈ 48 MiB other direct,
  metaspace, threads, code, GC, touched Netty arenas, glibc) fills 3471 MiB of anon. Every domain stays ≤ its C and
  the simultaneous total exceeds the budget: **convergence**.

### 3.4 Intervention (V4)

`file_cache_size` 1200 → 300 MiB, everything else identical. Predicted (design) 2980–3210 MiB (85–92%), no kill;
observed 2974 / 2959 / 2964 MiB (84.5–85.0%), no kill 3/3. The workload did not shrink: the burst wrote 2,000,000 partitions at
16,525 / 16,769 / 16,956 op/s against 16,471–16,786 op/s in `M_alone` (same memtable cap), the memtable reached
its cap and flushed 8 times as in `M_alone`, and the read pass completed all 800,000 reads (901–1,164 op/s, between
`F_alone`'s 1,475–2,297 and `converge`'s 657–767).

### 3.5 Instrument check

- Idle RssAnon: +30 s without the poller grew 1–5 MiB, the next +30 s with it 1–6 MiB, in every arm (same size
  as the drift). Poller and `jcmd` run outside the cgroup.
- Alone peaks are 2–57 MiB below run 7's (which had no NMT/poller); idle RssAnon is ≈ 40 MiB lower on pc96.
- `converge-noinst` (NMT and poller off): kernel memcg OOM-kill 5–10 s into the burst (anon-rss 3468 MiB, invoked by
  a `Native-Transport` thread, GFP_HIGHUSER_MOVABLE), the same outcome as the instrumented arms: the instruments
  neither cause nor prevent the kill.
- Kill attribution: `oom_memcg` = the arm's scope unit and killed PID = node PID in all three.
- After every arm: no `CassandraDaemon`, `cassandra-stress` or poller left, no `oom-r1-*` scope (checked by
  `run-all.sh`, lines `leftover procs: none; scopes: none`).

## 4. Conclusion and limits

**Promotion rule (V1–V5), condition above:**

| | Requirement | Evidence | Met |
|---|---|---|---|
| V1 | endpoint ≥ 3 runs | kernel memcg OOM-kill in `converge-1..3` (**3/3**); run 7 1/1; `converge-noinst` (uninstrumented, not counted) also killed | yes |
| V2 | matched control ≥ 3 | `M_alone-1..3` and `F_alone-1..3`: 0/6 kills, peaks 76.0–77.6%, each pool at its cap | yes |
| V3 | U apart from K | chunk cache: JDK direct (resident) = C; memtable: RssAnon-based bound ≤ 793 MiB < C (§3.3) | yes (memtable as a bound) |
| V4 | intervention ×3 | `int_F300-1..3`: 0/3 kills, burst throughput equal to `M_alone` | yes |
| V5 | initiating failure | three `dmesg` OOM blocks (`recheck-2026-11-11/logs/converge-*/dmesg-block.txt`) with per-pool poller rows ≤ 2 s and NMT ≤ 5 s before | yes |

**Status: `verified-OOM · diagnostic`** (convergence · standing-pool). Diagnostic because of the tightened
3500 MiB cgroup with `-Xmx768M` and the supporting `memtable_cleanup_threshold: 0.99`.

**Mechanism.** Two independently correct caps. The chunk-cache pool stops at its threshold and the memtable's
writers park at theirs, but neither knows about the other or about the process budget, and their sum (2400 MiB)
plus the 768 MiB heap and ≈ 450 MiB of baseline and load overhead does not fit 3500 MiB. The kill arrives while the
memtable is still filling (283–738 MiB of 1200), so the order matters only in that the cache was already full.

**Interpretation.** Configuration-sizing / validation gap: both defaults derive from the heap, the yaml documents each
knob separately, and no startup check relates the off-heap knobs to the memory available. Not an implementation
defect of either control.

**Limits.**
- The memtable's physical footprint is bounded, not measured exactly (JNA malloc is invisible to NMT and to the
  direct counter; glibc reuses freed regions).
- Diagnostic settings: a tightened cgroup and the deprecated 0.99 cleanup threshold. With the default threshold the
  memtable would flush earlier; the kill here came during the first fill, so a lower threshold may delay rather than
  prevent it, but that arm was not run. A deployment-budget arm (larger container sized from the documented knobs) is
  open.
- Single node; the stress client shares the host (outside the cgroup). The alone margin (≈ 22–24%) is below the
  protocol's 30% starting target.
- Kill timing moved from 16 s (pc41) to 7–11 s (pc96); environment differences are disclosed in §1.
