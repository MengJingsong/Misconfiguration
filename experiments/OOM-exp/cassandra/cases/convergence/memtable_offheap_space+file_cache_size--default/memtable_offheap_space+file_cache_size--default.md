# memtable_offheap_space + file_cache_size at defaults — off-heap memtable and chunk cache converge past a container limit

**Direction:** convergence · standing-pool. **Lead source:** if-check-exp (two true positives; predecessor R1,
[`../memtable_offheap_space+file_cache_size/`](../../candidates/memtable_offheap_space+file_cache_size/memtable_offheap_space+file_cache_size.md)).
**Regime:** **default capacities** (both constraints unset, heap-derived). **Source:** Cassandra 5.0.9 (tree
`b796bcfd…`). **Run:** R1-V, 2026-11-12, `apt149`. **Design:** [`design/R1V-design.md`](design/R1V-design.md)
(written before readings; review record, amendments 1–5 and the pause note in its §8 and after).
**Researcher budget review:** 2026-11-12, before any measured arm (design §8): `file_cache_enabled: true`
accepted as a documented setting; family A (L = 2 × heap) and family B (heap 2048, L = 3413, bisect upward)
accepted for V7.

| Condition | Status (protocol *Verification status*) |
|---|---|
| **B:** heap 2048 MiB, `MaxDirectMemorySize` 1024 MiB, container `memory.max` **3413 MiB** (heap = 60% of the limit), constraints at defaults (memtable off-heap 512, chunk cache 512), `offheap_objects`, chunk cache enabled; 800k-partition write load | **`verified-OOM · deployment`** (proposed) |
| **A-768:** heap 768, direct 384, container 1536 MiB (L = 2 × heap) | `candidate` (kernel memcg kill **1/5**; controls 0/6 at 83–86%; V1 unmet) |
| **A, heap 1024–2048:** L = 2 × heap (2048 / 3072 / 4096 MiB) | no failure (0/1 per level), the boundary of family A |

## Summary

- **Conclusion:** with every capacity constraint at its shipped, heap-derived default (off-heap memtable
  512 MiB, chunk cache 512 MiB at a 2 GiB heap), a Cassandra JVM in a 3413 MiB container (heap = 60% of the
  limit, accepted for V7) is **killed by the kernel memcg OOM-killer in 3/3 runs** (and 1/1 at 3500 MiB), about
  80–95 s into a plain write load. With either pool switched back to its shipped default (chunk cache off, or
  memtable on-heap) the same load survives 3/3 each at 86–88%; lowering only `file_cache_size` to 128 MiB
  removes the kill 3/3 at the same write throughput. At the same heap the kill stops at a 4096 MiB container
  (L = 2 × heap, peak 86%). Under L = 2 × heap the only failing level is the smallest tested heap, 768 MiB
  (kernel memcg kill in 1 of 5 runs, the other four peaking at 95.2–96.6% of the limit).
- **Root cause:** two independently enforced off-heap pools, each sized from the heap, neither aware of the
  other or of the process budget. At the kill neither exceeds its own cap (chunk-cache pool 376–504 of 512 MiB,
  memtable counter ≤ 188 of 512 MiB, memtable-attributable native ≈ 500 MiB); their sum plus the pre-touched heap
  and the JVM's native baseline exceeds a container limit that the documented guidance treats as reasonable.
  No startup or runtime check relates `memtable_offheap_space` + `file_cache_size` + heap to the memory
  available. Configuration-sizing / validation gap, not a defect in either control.

## 1. Constraints, defaults, protection map, labels

**Defaults (source-checked, design §1).** `memtable_offheap_space` = `maxMemory/4`
(`DatabaseDescriptor.java:583–584`); `file_cache_size` = `min(512 MiB, maxMemory/4)` (`:576–577`);
`memtable_heap_space` = `maxMemory/4`; `memtable_cleanup_threshold` = 1/(1 + 2 flush writers) = 0.333
(`:753–763`); `networking_cache_size` = `min(128, maxMemory/16)`. `file_cache_enabled` defaults to **false**
(`Config.java:499`), `memtable_allocation_type` to `heap_buffers` (`Config.java:524`). Resolved values read back
from `system.log` in every arm (`logs/<arm>/startup-lines.txt`):

| Heap | memtable off-heap / on-heap limit | chunk-cache pool | networking pool |
|---|---|---|---|
| 768 | 192 / 192 | 192 | 48 |
| 1024 | 256 / 256 | 256 | 64 |
| 1536 | 384 / 384 | 384 | 96 |
| 2048 | 512 / 512 | 512 | 128 |

**Unchanged-knob evidence.** The yaml diff is exactly two lines in every converge arm
(`memtable_allocation_type: offheap_objects`, `file_cache_enabled: true`; `logs/<arm>/cassandra.yaml.diff`); the
harness fails an arm if any capacity key appears, except `file_cache_size` in the intervention arms.

**Protection map.**

| Domain | Allocation / lifetime | Contract C (default) | K | Independent U |
|---|---|---|---|---|
| Off-heap memtable | `NativeAllocator` → JNA `Native.malloc` 1 MiB regions; freed after flush; glibc may retain | H/4, hard (writers block at the limit), flush at 0.333 of the limit | `AllMemtablesOffHeapDataSize` | RssAnon decomposition (§3.3), a bound: JNA malloc is outside NMT and the JDK direct counter |
| Chunk cache | Caffeine over `BufferPool` "chunk-cache", 8 MiB `allocateDirect` macro chunks (zeroed, resident), never returned | min(512, H/4) pool reservation | `BufferPool chunk-cache Size`, `ChunkCache Size` | JDK `BufferPool direct MemoryUsed` − idle |
| Budget | cgroup v2 `memory.max` = L on the JVM scope only, `MemorySwapMax=0` | | | RssAnon, cgroup `anon`, `memory.events`, `dmesg` |

No check relates the two pools, the heap and the process budget (`DatabaseDescriptor.java:573–594` only fills
the defaults).

**Labels.** Capacities: **default** (V6). Settings: `offheap_objects` and `file_cache_enabled: true` are
documented options, both accepted by the researcher (design §8). No supporting deviation: R1's
`memtable_cleanup_threshold: 0.99` and `memtable_heap_space: 200` are gone. Budget: **explicit deployment
budget**, container limit argued in design §4 and accepted 2026-11-12 (heap and direct ≥ 512 MiB meet the
standing rule; the container limits were reviewed). Environment: one node, `cassandra-stress` on the same host
outside the cgroup; instruments (NMT summary, 2 s JMX poller outside the cgroup) as in the R1 recheck, which
showed they neither cause nor prevent the kill. → conditions label **`deployment`**.

**Audit.** `apt149` (APT r320): 16 hardware threads, 15931 MiB RAM, 8 GiB swap (excluded), Ubuntu 22.04, kernel
5.15.0-198, glibc 2.35, cgroup v2, OpenJDK 11.0.33, G1, `-XX:+AlwaysPreTouch`, `MALLOC_ARENA_MAX=4`. Build
`/mydata/r1v/cassandra` (`cp -a ~/cassandra-c1`, HEAD `7cb9cc7`, tree `b796bcfd…`, clean). Data, commit log
and logs on `/mydata` (LVM on rotational disks). Heap and `MaxDirectMemorySize` passed as `MAX_HEAP_SIZE` /
`MAX_DIRECT_MEMORY_SIZE` (the startup script reads host RAM, design §4 item 5).

## 2. Verification design

Dated design and amendments: [`design/R1V-design.md`](design/R1V-design.md). In short:

- **Budget argument (V7, design §4).** Family A: the node Cassandra's own `cassandra-env.sh` sizes for RAM = L
  (heap L/2, direct L/4); the cgroup holds only the JVM, so it is more generous than a real L-sized node.
  Family B: heap = 60% of the limit, the generous end of the 60–70% container guidance (Red Hat bug 1370654),
  below DataStax's "heap ≤ ½ of system memory". Both accepted before readings.
- **Workload** (R1's): *preload* `cassandra-stress write n=800000`, 5 × 1 KiB columns, 32 threads, then flush
  and `disableautocompaction dataks`; *cachefill* a short read pass (300k, then 50k, then 10k reads; amendments
  1–2: the chunk cache is already filled by compaction reads during the preload); *memburst*
  `cassandra-stress write n=2000000`, 64 threads, `retries=50`, ≤ 240 s.
- **Arms** (amendment 1): `converge` (both pools at default); controls isolate by **configuration**, each by
  reverting one pool's enabling setting to its shipped default with all capacities still unset: `M_only`
  (`file_cache_enabled` false) and `F_only` (`memtable_allocation_type` `heap_buffers`); intervention `int_F128`
  (`file_cache_size` 128 MiB) / `int_F64` at heap 768. Workload-isolated alone arms (design §6) failed as
  controls: compaction reads fill the chunk cache under a write-only load (`A2048-M_alone-1`).
- **Predictions** (design §5, amendments 1 and 3): family A converge 86–94% at heap 1024–2048 (survive), ≈ 99%
  at 768; family B ≈ 104% at 3413 (kill), controls 88–91%.
- **Search**: A from the ideal heap 2048 down to 768; B at 3413, one bisect step at 3500.
- **Limits**: ≤ 6 h wall (07:40–11:00 and 12:03–14:43 MST, paused 11:00–12:03 by request), ≤ 31 arm
  executions (amendments 1, 4, 5). Harness: [`harness/oom-run.sh`](harness/oom-run.sh) (v1, arms to
  `A2048-F_alone-1`), [`harness/oom-run2.sh`](harness/oom-run2.sh) + [`run-all2.sh`](harness/run-all2.sh) (v2,
  all later arms), [`PoolPoller.java`](harness/PoolPoller.java), [`analyze.py`](harness/analyze.py),
  [`dmesg-block.sh`](harness/dmesg-block.sh), [`export.sh`](harness/export.sh).

## 3. Results

Raw logs: `/mydata/r1v/logs/<arm>/` on `apt149` (`pools.csv`, `summary.txt`, `system.log` in the next arm's
`prev-logs/`, NMT, stress output). Excerpts: [`logs/<arm>/`](logs/) (`digest.txt`, `summary.txt`,
`pools-excerpt.csv`, `dmesg-block.txt`, `cassandra.yaml.diff`, `startup-lines.txt`, stress tails).
Void, not readings: `void-A2048-converge-1-aborted` (forced handback), `void-A768-converge-1-stopped` (pause).

### 3.1 Family B (heap 2048, direct 1024)

| Arm | L | Idle RssAnon | Peak RssAnon (% of L) | At peak / kill | Workload | Outcome |
|---|---|---|---|---|---|---|
| `B3413-converge-1` | 3413 | 2351 | kernel anon-rss **3342** | pool 392, cache 389, memtable K 170 | preload 513,736 writes in 83 s | **memcg OOM-kill** |
| `B3413-converge-2` | 3413 | 2357 | **3329** | pool 376, K 139 | 512,417 in 82 s | **memcg OOM-kill** |
| `B3413-converge-3` | 3413 | 2344 | **3367** | pool 432, K 154 | 512,335 in 81 s | **memcg OOM-kill** |
| `B3413-M_only-1..3` | 3413 | 2347–2360 | 2993 / 2989 / 2953 (86.5–87.7%) | memtable K ≤ 171, direct 53 | preload 800k; burst 1.24–1.35M writes | alive 3/3 |
| `B3413-F_only-1..3` | 3413 | 2349–2359 | 2956 / 2945 / 2956 (86.3–86.6%) | pool 512, cache 480 | preload 800k; burst 0.87–1.27M | alive 3/3 |
| `B3413-int_F128-1..3` | 3413 | 2349–2365 | 3113 / 3103 / 3119 (90.9–91.4%) | pool 128, cache 96, K ≤ 188 | preload 800k; burst 1.267–1.276M | alive 3/3 |
| `B3500-converge-1` | 3500 | 2347 | **3453** | pool 504, cache 480, K 168 | 580,731 in 93 s | **memcg OOM-kill** |
| `A2048-converge-1` (same heap/direct) | 4096 | 2347 | 3537 (86.3%) | pool 512, K ≤ 171 | preload, 300k reads, burst 1.26M | alive |

All kills happened during the preload, while compaction reads were still filling the chunk cache and the
memtable was cycling 0 → ⅓ of its limit (flushes enqueued at 33–36%). MiB throughout; "% of L" for kills is
≈ 98% of the anon limit by RssAnon (the cgroup also holds page cache).

### 3.2 Family A (L = 2 × heap, direct = heap/2)

| Arm | Heap / L | Peak RssAnon (% of L) | Outcome |
|---|---|---|---|
| `A2048-converge-1` | 2048 / 4096 | 3537 (86.3%) | alive |
| `A1536-converge-1` | 1536 / 3072 | 2732 (88.9%) | alive |
| `A1024-converge-1` | 1024 / 2048 | 1885 (92.0%) | alive |
| `A768-converge-1` | 768 / 1536 | kernel anon-rss **1495** (97.3% by RssAnon) | **memcg OOM-kill** ≈ 225 s into the burst |
| `A768-converge-2..5` | 768 / 1536 | 1474 / 1462 / 1477 / 1483 (95.2–96.6%) | alive 4/4 |
| `A768-M_only-1..3` | 768 / 1536 | 1297 / 1312 / 1289 (83.9–85.4%) | alive 3/3 |
| `A768-F_only-1..3` | 768 / 1536 | 1276 / 1291 / 1287 (83.1–84.0%) | alive 3/3 |
| `A768-int_F64-1` | 768 / 1536 | 1348 (87.7%), preload only | **invalid**: the burst never started (`cassandra-stress` timed out creating the `memks` schema, the run-8 harness lesson); not an intervention reading |

At heap 768 the pools are 192 + 192 MiB; the converge arms sit within 2–4% of the limit and only one of five
crossed it, during the burst (pool 192 full, memtable K ≤ 67 of 192; kernel record `PerDiskMemtable invoked
oom-killer`, `oom_memcg` = the arm's scope). Repeats were expanded per protocol step 6 (amendment 5); the A-768
intervention ×3 was not run (amendment 5).

### 3.3 U against C (V3), family B at 3413

- **Chunk cache:** U = JDK direct − idle direct (43 MiB) = 393 / 377 / 433 MiB at the three kills = the pool Size
  K (392 / 376 / 432) within 2 s sampling; ≤ C = 512. Resident: `allocateDirect` buffers are zeroed. No overflow.
- **Off-heap memtable:** K ≤ 188 MiB (live memtables; flushes at ⅓ of 512). Physical U is bounded from RssAnon:
  kill anon-rss − idle − Δdirect = 598 / 595 / 590 MiB (601 at 3500). The same residual is ≈ 87 MiB in `F_only`
  (memtable on-heap: the non-pool load overhead) and ≈ 600–640 MiB in `M_only` (memtable alone). So the
  memtable-attributable native memory at the kill is ≈ 500 MiB: live plus flushing memtables and glibc-retained
  regions, ≈ C (512) but not resolved further (JNA `malloc` is invisible to NMT and to the JDK counter).
- **Sum:** pre-touched heap 2048 + JVM baseline ≈ 300 + chunk cache 350–430 + memtable-attributable ≈ 500 +
  load overhead ≈ 90 ≈ 3330–3370 = the 3413 MiB anon limit. Every domain ≤ its C; the simultaneous sum exceeds
  the budget: **convergence**. Each control alone stays at 86–88%.

### 3.4 Initiating failure (V5)

Kernel record in each kill (`logs/<arm>/dmesg-block.txt`): `PerDiskMemtable invoked oom-killer`
(`GFP_HIGHUSER_MOVABLE|__GFP_WRITE`, a page charge from a memtable flush writer), `oom-kill:constraint=
CONSTRAINT_MEMCG`, `oom_memcg` = the arm's own `oom-r1v-*` scope, `Killed process <node pid> (java)
anon-rss:3422500kB / 3408740kB / 3447984kB` (3500: 3536360 kB), memcg usage = limit. No `OutOfMemoryError` and
no ERROR line in any arm. A kernel kill leaves no dump; the last poller row (≤ 2 s before the kill, table 3.1)
gives the per-pool readings at failure.

### 3.5 Intervention (V4)

`file_cache_size` 512 → 128 MiB, everything else identical: 0/3 kills, peaks 90.9–91.4% (≈ 400 MiB lower than
the kill level, the 384 MiB pool reduction). The load did not shrink: the whole 800,000-write preload completed
(converge was killed at ≈ 512,000) and the burst wrote 1.267–1.276M partitions, the same as `M_only` (1.24–1.35M).

## 4. Conclusion and limits

**Condition B (heap 2048, direct 1024, container 3413 MiB, both constraints at default):**

| | Requirement | Evidence | Met |
|---|---|---|---|
| V1 | endpoint ≥ 3 runs | memcg OOM-kill in `B3413-converge-1..3` (**3/3**); also `B3500-converge-1` (1/1) | yes |
| V2 | matched control ≥ 3 | `M_only` ×3 and `F_only` ×3: 0/6 kills, 86.3–87.7% | yes (margin ≈ 12–14%, below the 30% starting target, disclosed) |
| V3 | U apart from K | chunk cache: JDK direct = pool Size; memtable: RssAnon decomposition ≈ 500 MiB (bound) | yes (memtable as a bound) |
| V4 | intervention ×3 | `int_F128-1..3`: 0/3, full preload and equal burst throughput | yes |
| V5 | initiating failure | 3 kernel memcg records with scope and PID, per-pool rows ≤ 2 s before | yes |
| V6 | defaults | `memtable_offheap_space`, `file_cache_size` (and `memtable_heap_space`, cleanup threshold) unset, resolved 512/512 at the 2048 heap; read back from the log | yes |
| V7 | acceptable budget | heap 2048 / direct 1024 meet the standing rule; container 3413 MiB (heap = 60% of the limit) argued in design §4 and **accepted by the researcher 2026-11-12** before readings | yes |

**Status (filed 2026-11-12 in `convergence/`): `verified-OOM · deployment`** (convergence · standing-pool), filed in
`cassandra/cases/convergence/memtable_offheap_space+file_cache_size--default/`.
**Largest failing budget:** family B fails at L = 3413 (3/3) and 3500 (1/1); the same heap/direct survives at
4096 (0/1, 86.3%). The boundary lies between 3500 and 4096 MiB (≈ 3540 MiB of anon by the 4096 peak); not
bisected further within the time limit.

**Family A (L = 2 × heap):** At heap 768 / L 1536 the pair crossed the limit in **1 of 5** runs (others 95.2–96.6%), controls 0/6 at 83.1–85.4%: a `candidate` boundary, not a reproducible failure (V1 unmet, V4 not run). Heaps 1024, 1536 and 2048 survive (0/1 each, 92.0 / 88.9 / 86.3%).
Family A has no reproducible failure at heap ≥ 1024: in Cassandra's own memory model (heap = ½ RAM) the two
default pools fit for these heaps, because both are ≤ ¼ heap and the memtable is flushed at ⅓ of its limit.

**Condition A-768 (heap 768, direct 384, container 1536 MiB = 2 × heap, constraints at default):**

| | Requirement | Evidence | Met |
|---|---|---|---|
| V1 | endpoint ≥ 3 runs | memcg OOM-kill in `A768-converge-1` only (**1/5**) | no |
| V2 | matched control ≥ 3 | `M_only` ×3, `F_only` ×3: 0/6, 83.1–85.4% | yes |
| V3 | U apart from K | chunk cache JDK direct = pool (192); memtable by RssAnon decomposition | yes (bound) |
| V4 | intervention ×3 | not run (amendment 5); `A768-int_F64-1` invalid | no |
| V5 | initiating failure | one kernel memcg record with scope and PID, poller row ≤ 2 s before | yes (for the one kill) |
| V6 | defaults | constraints unset, resolved 192 / 192 | yes |
| V7 | acceptable budget | heap 768 / direct 384 ≥ 512 rule; L = 2 × heap accepted 2026-11-12 | yes |

**Status A-768: `candidate`** (1/5). **Family A overall:** no reproducible failure at heap 768–2048 under
L = 2 × heap; the largest level with any failure is 768 / 1536 (1/5); 1024 / 2048, 1536 / 3072 and
2048 / 4096 survive (0/1 each). Not a `negative` file of its own: heaps 1024–2048 have one run each, and V2 was
measured only at 768 and at family B's heap.

**Interpretation.** Configuration-sizing / validation gap: each pool is documented separately as "in addition
to the heap"; the defaults are fractions of the heap, so the default pair needs ≈ ½ heap of native memory
beyond the heap plus the JVM baseline, and nothing warns when the process cannot have it. A container that
gives the heap 60% of its memory, which published container guidance considers normal, is enough to fail at a
2 GiB heap.

**Limits.**
- The memtable's physical footprint is bounded, not measured exactly (JNA malloc, glibc retention).
- The kill happens during a bulk write load in which compaction reads fill the chunk cache; a read-only or
  write-light workload may not combine both pools this way. Preload of 800k × 5 KiB partitions from 32 client
  threads on rotational disks.
- Control margins ≈ 12–14% (below the 30% starting target).
- Single node, client co-located (outside the cgroup); only family-B levels 3413 and 3500 tested, A levels at
  n = 1 except A-768.
- `apt149` uses rotational disks; flush and compaction speed affect how many memtables are in flight.
- Control bursts: `B3413-F_only-2/-3` wrote fewer burst partitions (0.99M / 0.87M vs 1.27M); every control
  completed the full 800,000-write preload, the phase in which all family-B kills occurred.
- Harness change mid-run: v1 (`oom-run.sh`) for the first three arms, v2 (`oom-run2.sh`) for the rest; fill pass
  300k → 50k → 10k reads (amendments 1–2). One arm (`A768-int_F64-1`) is invalid (stress schema timeout).
