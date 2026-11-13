# R1-V design: `memtable_offheap_space` + `file_cache_size` at their defaults, container budget

**Written:** 2026-11-12, before any measured arm. **Node:** `apt149` (APT r320). **Status of this file:**
phase 1 (design only). **AWAITING RESEARCHER BUDGET REVIEW** (protocol V7: container limits are argued
case by case and reviewed before readings). Review date and decision go in §8.

**Predecessor:** R1 (run 7 + recheck 2026-11-11, [case](../../../candidates/memtable_offheap_space+file_cache_size/memtable_offheap_space+file_cache_size.md)):
`reproduced-OOM · diagnostic`. Kernel memcg kill 3/3 with both pools at 1200 MiB, a 3500 MiB cgroup and
`-Xmx768M`; alone 0/6; `file_cache_size` 300 MiB removes it 3/3. V6 and V7 unmet. This run moves **the
capacity dial to defaults** (both constraints unset) and **the budget dial to a container limit argued as a
deployment value**, and keeps the workload of R1. Dials, per the default-convergence playbook: capacities
(fixed at default), budget (searched, §5), workload (fixed, R1's).

## 1. Defaults, source-checked (Cassandra 5.0.9, tree `b796bcfd…`)

| Setting | Default rule (pinned source) | Notes |
|---|---|---|
| `memtable_offheap_space` | unset → `maxMemory / 4` (`DatabaseDescriptor.java:583–584`; logged at `:594`) | yaml: "If omitted, Cassandra will set both to 1/4 the size of the heap" (`conf/cassandra.yaml:792–799`) |
| `memtable_heap_space` | unset → `maxMemory / 4` (`DatabaseDescriptor.java:586–590`) | on-heap; inside `-Xmx` |
| `file_cache_size` | unset → `min(512, maxMemory / 4)` MiB (`DatabaseDescriptor.java:576–577`) | yaml `:744–753`: "Defaults to the smaller of 1/4 of heap or 512MB. This pool is allocated off-heap, so is in addition to the memory allocated for heap." |
| `file_cache_enabled` | **`false`** (`Config.java:499` ← system property `cassandra.file_cache_enabled`, unset = false; yaml `:740–742` `# file_cache_enabled: false`) | **The chunk cache is off by default.** Off, `ChunkCache.instance = null` (`ChunkCache.java:53–54`) and the `chunk-cache` `BufferPool` only holds per-reader rebuffer buffers (`BufferManagingRebufferer.java:45,52`), so `file_cache_size` is a capacity with no standing consumer. See §3. |
| `memtable_allocation_type` | `heap_buffers` (`Config.java:524`, yaml `:814–825`) | `offheap_objects` → `NativePool` (`AbstractAllocatorMemtable.java:106–108`); a documented option, **accepted setting** per the task brief |
| `memtable_flush_writers` | 0 → 2 for one data directory (`DatabaseDescriptor.java:753–755`, `Config.java:185`) | one data dir here |
| `memtable_cleanup_threshold` | unset → `1/(1+flush_writers)` = **0.333** (`DatabaseDescriptor.java:761–763`) | R1 used the deprecated 0.99 (supporting deviation); **R1-V leaves it unset**. A flush is triggered when `used > reclaiming + 0.333·limit` (`MemtablePool.java:125–145`); writers block only at the limit, so the pool can still reach its cap when flushes lag the write rate. |
| `networking_cache_size` | `min(128, maxMemory/16)` MiB (`DatabaseDescriptor.java:573–574`) | transient pool; recorded, not a tested constraint |
| Heap (`cassandra-env.sh`) | `min(½ RAM, 15872 MiB)` (`conf/cassandra-env.sh:54–67`) | from `free -m`, i.e. **host** RAM, not a cgroup limit |
| `MaxDirectMemorySize` | `¼ RAM`, or 7936 MiB above the heap cap (`cassandra-env.sh:59–66,156–158`) | not binding here: the memtable allocates with JNA `malloc` (outside the JDK direct counter); the chunk cache is ≤ 512 MiB of `allocateDirect` |
| `MALLOC_ARENA_MAX` | 4 (`cassandra-env.sh:143–144`) | |

**Resolved at startup (smoke, 2026-11-12, `logs/smoke/startup-resolved-lines.txt`), G1 so `maxMemory = -Xmx`:**

| `-Xmx` | memtable on-heap / off-heap threshold | chunk-cache pool limit | networking pool |
|---|---|---|---|
| 1024M | 256 / 256 MiB | 256 MiB | 64 MiB |
| 2048M | 512 / 512 MiB | 512 MiB | 128 MiB |
| 4096M | 1024 / 1024 MiB | 512 MiB | 128 MiB |

The yaml diff in every smoke arm is exactly two lines (`logs/smoke/cassandra.yaml.diff`):
`memtable_allocation_type: offheap_objects`, `file_cache_enabled: true`. No capacity key is set; the harness
fails the arm if `memtable_offheap_space`, `file_cache_size`, `memtable_heap_space`,
`memtable_cleanup_threshold`, `memtable_flush_writers` or `networking_cache_size` appear (except the
intervention arm's explicit `file_cache_size`).

## 2. Protection map (unchanged from R1, checked against the same tree)

| Domain | Allocation / lifetime | Contract C (at default) | K | Independent U | Aggregate coverage |
|---|---|---|---|---|---|
| Off-heap memtable | `NativeAllocator` → `MemoryUtil.allocate` → JNA `Native.malloc` (1 MiB regions); freed after flush; glibc may retain | `memtable_offheap_space` = H/4, hard (writers block at the limit); flush at 0.333 of limit | `AllMemtablesOffHeapDataSize` | RssAnon growth over the burst, bounded with glibc retention (R1 §3.3 method) | none |
| Chunk cache | Caffeine over `BufferPool` "chunk-cache", 8 MiB macro chunks via `allocateDirect` (zeroed, resident), never returned | `file_cache_size` = min(512, H/4) pool reservation; cache weight ≤ F − 32 MiB | `BufferPool chunk-cache Size`, `ChunkCache Size` | JDK `BufferPool direct MemoryUsed` − idle | none |
| Budget | cgroup v2 `memory.max` = L on the JVM scope only (`systemd-run --user --scope -p MemoryMax=L -p MemorySwapMax=0`) | | | RssAnon, cgroup `anon`, `memory.events`, `dmesg` | |

No startup or runtime check relates heap + `memtable_offheap_space` + `file_cache_size` + JVM native baseline to
the memory the process has (`DatabaseDescriptor.java:573–594` only fills the heap-derived defaults).

## 3. Configuration labels (for review)

- **Capacities:** both tested constraints **default, resolved at the heap used** (V6). `memtable_heap_space`
  and `memtable_cleanup_threshold` also default (R1's 200 MiB and 0.99 are gone).
- **`memtable_allocation_type: offheap_objects`:** documented option; recorded as an **accepted setting**
  (task brief). Without it the memtable is on-heap and this domain does not exist.
- **`file_cache_enabled: true` — needs the researcher's decision.** The chunk cache is **off** in the shipped
  5.0.9 config, so at strict shipped defaults `file_cache_size` contributes no standing memory and there is no
  pair to converge. Enabling it is a documented one-line yaml option (`# Enable the sstable chunk cache`) and
  leaves the tested capacity (`file_cache_size`) at its default, so V6 holds either way. Proposed label:
  **accepted documented setting** (like `offheap_objects`) → conditions label `deployment`. If the researcher
  instead counts it as a supporting deviation (the playbook: "A pool off at default contributes nothing;
  enabling it is a deviation"), the label is `diagnostic` and nothing else in the design changes.
- **Budget:** heap H and `MaxDirectMemorySize` = H/2 passed as `MAX_HEAP_SIZE` / `MAX_DIRECT_MEMORY_SIZE`
  (§4); container limit L. Labelled **explicit deployment budget** if the review accepts §4.
- **Environment:** one node; `cassandra-stress` on the same host outside the cgroup; data, commit log and logs on
  `/mydata` (LVM on rotational WD disks; R1 ran on pc96); instruments as in the R1 recheck (NMT summary,
  2 s JMX poller outside the cgroup, `jcmd` every 5 s in the burst). R1's instrument check showed they neither
  cause nor prevent the kill.
- **Node:** `apt149`, 16 hardware threads, 15931 MiB RAM, 8 GiB swap (excluded by `MemorySwapMax=0`),
  Ubuntu 22.04, kernel 5.15.0-198, glibc 2.35, cgroup v2 with `memory` delegated to the user manager,
  OpenJDK 11.0.33, G1, `-XX:+AlwaysPreTouch`. Build `/mydata/r1v/cassandra` (`cp -a ~/cassandra-c1`, HEAD
  `7cb9cc7`, tree `b796bcfd…`, clean).

## 4. Container-limit argument (V7)

**The node the result represents.** A machine (VM, or a container treated as one) with **RAM = L**, running
Cassandra 5.0.9 with the shipped startup script's own sizing. For that node `cassandra-env.sh` resolves
**heap = L/2** and **`MaxDirectMemorySize` = L/4** (`cassandra-env.sh:58–66`, for L ≤ 31.7 GiB), and then
Cassandra resolves `memtable_offheap_space` = L/8 and `file_cache_size` = min(512, L/8). The only setting
we choose is L; everything else follows from it.

**Why L is a value a deployment could run.**
1. **It is Cassandra's own memory model.** The startup script gives the heap half of RAM and assumes the other
   half covers direct memory, native memory and the OS. Running the JVM under `memory.max = L` with exactly
   the values the script derives for RAM = L is the shipped configuration for an L-sized node.
2. **The cgroup is, if anything, more generous than a real L-node:** on a VM with RAM L the kernel, other
   processes and the page cache share L; here the cgroup holds only the JVM (its page cache is charged but
   reclaimable) and the host has 16 GiB. A kill under `memory.max = L` therefore also implies a failure on an
   L-node; a survival here does not prove survival there.
3. **External guidance for containers matches L = 2H.** DataStax: "Heap size is usually between ¼ and ½ of
   system memory. Do not devote all memory to heap because it is also used for offheap cache and file system
   cache" ([DataStax, Tuning Java resources, 3.x](https://docs.datastax.com/en/cassandra-oss/3.x/cassandra/operations/opsTuneJVM.html),
   fetched 2026-11-12). For containers, a community answer for K8ssandra advises a heap of at most half the
   pod's memory limit, and a 2016 Red Hat OpenShift report suggests "60-70% of the limit value to allow room for
   native memory from the JVM" ([Red Hat bug 1370654](https://bugzilla.redhat.com/show_bug.cgi?id=1370654),
   comment 0, fetched 2026-11-12). No official K8ssandra/Apache figure was found; these are secondary sources.
   **L = 2H is at the generous end of all of them** (heap = 50% of the limit).
4. **Heap ≥ 512 MiB** in every proposed level, so the heap and direct limits meet the standing rule; only L
   needs this review.
5. **Why not the automatic heap of this host.** Inside a cgroup on this 16 GiB host the script would resolve
   heap 7965 MiB and direct 3982 MiB regardless of L (it reads `free -m`), which would not fit any L below
   ≈ 12 GiB; an operator setting a container limit must set `MAX_HEAP_SIZE`, and we model the one who sets it by
   the script's own rule for the container size. This pitfall is recorded but is not the tested mechanism.

**Family A (proposed, primary): L = 2H, direct = H/2.** Levels, all ≥ 512 MiB heap:

| H (`-Xmx`) | L = `memory.max` | direct | M (= H/4) | F (= min(512, H/4)) | M + F | M + F as % of L − H |
|---|---|---|---|---|---|---|
| 512 | 1024 | 256 | 128 | 128 | 256 | 50% |
| 768 | 1536 | 384 | 192 | 192 | 384 | 50% |
| 1024 | 2048 | 512 | 256 | 256 | 512 | 50% |
| 1536 | 3072 | 768 | 384 | 384 | 768 | 50% |
| **2048 (ideal)** | **4096** | 1024 | 512 | 512 | 1024 | 50% |
| 3072 | 6144 | 1536 | 768 | 512 | 1280 | 42% |
| 4096 | 8192 | 2048 | 1024 | 512 | 1536 | 38% |
| 8192 | 16384 | 4096 | 2048 | 512 | 2560 | 31% (not runnable: host has 15931 MiB) |

**Family B (optional, only if the researcher accepts it): H = 2048 fixed, L = H/0.6 = 3413 MiB** (heap = 60% of
the limit, the generous end of the 60–70% guidance in item 3), then bisect upward toward 4096 for the largest
L that still fails. Direct stays 1024. This is a tighter container than Cassandra's own node model; I do not
claim it meets V7 without the review.

## 5. Prediction (before readings) and budget search

Peak RssAnon ≈ H (pre-touched) + B(H) + M + F + O, where B(H) is the idle non-heap anon memory and O the
write/read-load overhead plus glibc retention not covered by the pools.

- **B(H), measured idle on apt149 (smoke, no load, no limit):** RssAnon − H = 302 / 359 / 504 MiB at
  H = 1024 / 2048 / 4096 (`logs/smoke/smoke-H*-summary.txt`; NMT GC 104 / 142 / 220 MB grows with the heap).
  Interpolated 512 → ≈ 270, 768 → ≈ 285, 1536 → ≈ 330, 3072 → ≈ 430.
- **O ≈ 200–270 MiB** from R1 on pc96 (`M_alone` RssAnon − idle − cap). Not yet measured on apt149 (fewer
  cores: fewer Netty arenas and threads, likely lower). Error bar on each prediction ± 150 MiB.
- **At the default cleanup threshold (0.333) the memtable may not reach its cap**; then M in the formula is
  an upper bound and the prediction falls.

| H / L | converge predicted (% of L) | M_alone (% of L) | F_alone (% of L) | expected |
|---|---|---|---|---|
| 512 / 1024 | 1290 (126%) | 1160 (113%) | 1160 (113%) | alone fails → not convergence (baseline does not fit) |
| 768 / 1536 | 1690 (110%) | 1495 (97%) | 1495 (97%) | alone at the edge → probably not a clean convergence |
| 1024 / 2048 | 2090 (102%) | 1830 (89%) | 1830 (89%) | **likely the largest failing A level**, borderline |
| 1536 / 3072 | 2880 (94%) | 2500 (81%) | 2500 (81%) | survive unless O or retention is high |
| **2048 / 4096** | 3680 (90%) | 3170 (77%) | 3170 (77%) | **survive predicted** |
| 3072 / 6144 | 5030 (82%) | 4520 (74%) | 4270 (70%) | survive |
| 4096 / 8192 | 6390 (78%) | 5870 (72%) | 5110 (62%) | survive |
| B: 2048 / 3413 | 3680 (108%) | 3170 (93%) | 3170 (93%) | fail predicted; alone margin only ≈ 7% |

Under L = 2H the margin is L − peak = H − B − M − F − O = H/2 − B − O for H ≤ 2048, so it closes near
H/2 ≈ B + O ≈ 550–620 MiB, i.e. H ≈ 1.1–1.25 GiB. **Prediction: at the ideal 2 GiB heap (L = 4 GiB) both pools
at their defaults fit (≈ 90%), and the pair overruns L = 2H only around H ≈ 1 GiB, where the alone arms still
leave ≈ 11%.** A negative at 2048/4096 is the most likely outcome of family A and is a valid result.

**Search procedure (budget dial only; capacities follow from H automatically, recorded per level):**
1. Start at the ideal level **A-2048 (H 2048, L 4096)**: `converge-1`, `M_alone-1`, `F_alone-1`. These also
   measure B and O on apt149.
2. Write a dated amendment with the recomputed predictions (no other change) before the next level.
3. If A-2048 fails: step **up** (A-3072, then A-4096), converge ×1 per level, ×3 at the largest failing level.
   If it survives: step **down** (A-1536, then A-1024), converge ×1 per level with `M_alone-1` / `F_alone-1` at
   any level where the alone prediction is ≥ 85%. A level counts as convergence only if both alone arms survive.
   Levels below 1024 are not run (alone predicted ≥ 97%).
4. At the **largest failing level** (if any): `converge` ×3, `M_alone` ×3, `F_alone` ×3, intervention ×3 (§6).
   If no A level fails with alone arms surviving: complete `converge` ×3, `M_alone` ×3, `F_alone` ×3 at
   **A-2048** → `negative` (V1–V3) for family A, with the boundary levels reported with their n/N.
5. Family B only if approved: `converge-1` at 2048/3413, alone arms, then bisect L toward 4096 (≤ 2 steps),
   ×3 at the largest failing L.

## 6. Arms and workload (R1's, unchanged except the cache-fill length)

All arms of one level: same build, H, L, direct, yaml (2-line diff), clean data directory, fresh JVM.

| Arm | yaml (beyond the 2-line diff) | Workloads |
|---|---|---|
| `converge` | none | preload → cachefill → memburst |
| `M_alone` | none | memburst only (the chunk cache stays near empty: the burst does no reads) |
| `F_alone` | none | preload → cachefill (no burst; the preload memtable and its glibc retention stay in, as in `converge`) |
| `int_F` | `file_cache_size` lowered: **64 MiB at H ≤ 1536, 128 MiB at H ≥ 2048** (cache weight 32 / 96 MiB) | preload → cachefill → memburst |

- *preload*: `cassandra-stress write n=800000`, 5 × 1 KiB columns, keyspace `dataks`, 32 threads; then
  `nodetool flush dataks` and `disableautocompaction dataks`.
- *cachefill*: `cassandra-stress read n=300000` over `seq=1..800000` (random tokens), 64 threads. Changed from
  R1's full 800,000-read pass: the cache is ≤ 512 MiB at default (R1: 1200 MiB) and 300,000 reads touch far more
  than 512 MiB of distinct chunks; this shortens each arm on rotational disks. The poller shows when the
  pool reaches its limit; if it does not reach F before the burst, the arm is invalid and N_FILL is raised by a
  dated amendment.
- *memburst*: `cassandra-stress write n=2000000` into `memks`, 64 threads, `-errors retries=50`, cap 240 s.
- Each arm: 30 s idle without poller, 30 s with poller, then the workloads; after the burst 30 s hold.
- Alone arms isolate a pool by **workload**, not by configuration, so every non-intervention arm has all
  constraints at default (V6 holds in the controls too). Intervention changes only `file_cache_size`.

**Readings:** per-pool JMX poller every 2 s (RssAnon, cgroup anon/events, heap, JDK direct, chunk-cache pool
Size/Used/Overflow, ChunkCache Size/Entries, memtable off/on-heap counters, memks writes, pending flushes,
BlockedOnAllocation); `/proc` + cgroup every 5 s; NMT every 5 s in the burst; memks flush lines (off-heap % at
enqueue); `dmesg` OOM block for the arm's scope; JVM `OutOfMemoryError` lines. V5 at a kill: kernel memcg
record with `oom_memcg` = arm scope and killed PID = node PID, plus the last poller and NMT rows (a kernel kill
leaves no dump).

**Endpoint:** kernel memcg OOM-kill of the JVM (or any JVM `OutOfMemoryError`), within the burst or hold.
**Throughput check for the intervention:** burst op/s and partitions written vs `M_alone`.

## 7. Limits and stopping budget

- **Phase 2 cap: ≤ 6 h wall and ≤ 22 arm executions** (≈ 12–16 min per arm expected on rotational disks);
  `/mydata/r1v/STOP` stops the run list before the next arm. Stop after the planned endpoint; no escalation
  after an OOM.
- Harness: [`../harness/oom-run.sh`](../harness/oom-run.sh) (from the R1 recheck harness; changes listed in
  its header), [`run-all.sh`](../harness/run-all.sh) (hygiene check after each arm: no `CassandraDaemon`,
  stress or poller process, no `oom-r1v-*` scope), [`PoolPoller.java`](../harness/PoolPoller.java),
  [`analyze.py`](../harness/analyze.py) (`python3 -I analyze.py <L> <arm-dir>…`),
  [`dmesg-block.sh`](../harness/dmesg-block.sh). Deployed to `/mydata/r1v/`; raw logs `/mydata/r1v/logs/`.
- **Resume:** a resumed session reads §8 for the decision, runs `run-all.sh <list>` from `/mydata/r1v` with
  one line per arm (`name L H M F workloads`, `M`/`F` = `def` for defaults), and copies excerpts to
  `../logs/<arm>/`. `oom-run.sh` sets direct = L/4 (= H/2 in family A); family B must run with
  `DIRECT=1024` in the environment of `run-all.sh`.
- Existing data on apt149 (`/mydata/b7`, `/mydata/oom-recheck`) is not touched.

## 8. Review record

- 2026-11-12: design written; smoke only (three startup/idle runs without a memory limit, H = 1024/2048/4096,
  no workload). **AWAITING RESEARCHER BUDGET REVIEW** of §3 (`file_cache_enabled` label) and §4 (family A;
  family B optional).
- **2026-11-12, researcher budget review (relayed by the coordinating session), before any measured arm:**
  (1) `file_cache_enabled: true` is an **accepted setting** (label `deployment` if verified).
  (2) **Family A** (L = 2 × heap, direct = heap/2, heaps 512 MiB–4 GiB) **accepted for V7**.
  (3) **Family B** (heap 2048, L = 3413, bisect L upward toward 4096) **also accepted for V7** (heap = 60% of
  the container limit); run after family A. Phase 2 proceeds per §5–§7; B arms may extend the arm budget by a
  dated amendment stating the new limit before they run.
- **2026-11-12 07:39 MST:** phase 2 started with `list-a2048.txt` (`A2048-converge-1`, `A2048-M_alone-1`,
  `A2048-F_alone-1`). The session had to hand back early, so **`A2048-converge-1` was aborted** a few minutes in
  (STOP file, processes stopped, scope removed). That arm is **void, not a reading**; its partial folder is
  `/mydata/r1v/logs/A2048-converge-1`. No arm completed. **Resume:** `rm /mydata/r1v/STOP`, move the void
  folder aside, then `cd /mydata/r1v && nohup bash run-all.sh list-a2048.txt > logs/run-a2048.log 2>&1 &`, and
  continue per §5.

## Amendment 1 (2026-11-12 08:15 MST, after `A2048-converge-1` and `A2048-M_alone-1`, before any further reading)

**New evidence.** At H 2048 / L 4096 (family A):
- `A2048-converge-1` survived, peak RssAnon 3537 MiB = **86.3%** (predicted 90%). At the default cleanup
  threshold every memks flush was enqueued at 33–36% of the off-heap limit; memtable K never exceeded
  **171 of 512 MiB** (writers still blocked: `BlockedOnAllocation` 4295). The chunk cache reached its full
  512 MiB pool (cache 480 MiB) **during the preload**, through compaction reads, before the read pass.
- `A2048-M_alone-1` (burst only) **also filled the chunk cache** to 512 MiB through compaction of `memks`, and
  peaked at 3511 MiB (85.7%). Isolating a pool by workload (design §6) therefore fails: the write workload
  drives both pools at defaults. `A2048-F_alone-1` (running) is kept as a supplementary reading, not as a
  control.

**Changes (no change to H, L, direct or tested capacities):**
1. **Alone controls isolate by configuration**, each by reverting the other pool's *enabling* setting to its
   shipped default, with all capacities still unset, and the full converge workload:
   - `M_only`: `file_cache_enabled` left at the shipped `false` (memtable alone).
   - `F_only`: `memtable_allocation_type` left at the shipped `heap_buffers` (memtable on-heap, inside `-Xmx`;
     chunk cache alone).
   Harness v2: [`oom-run2.sh`](../harness/oom-run2.sh) / [`run-all2.sh`](../harness/run-all2.sh) (`M=heapbuf`,
   `F=off`), deployed as new files so the running arm's script was not modified.
2. **Cache-fill pass shortened to 50,000 reads** (`N_FILL`): the cache is already full after the preload. All
   arms from here use it; `A2048-converge-1` (300,000 reads) is kept as the first A-2048 converge repeat, its
   pre-burst state (cache full, memtable 0) being the same.
3. **Predictions recomputed** from the measured non-heap total at H 2048 (peak − H = 1489 MiB: B 359, JDK direct
   556, memtable + glibc + load ≈ 574), scaling the pool shares with H:
   | Level | converge | M_only | F_only |
   |---|---|---|---|
   | A 1536 / 3072 | ≈ 2730 (89%) | ≈ 2350 (77%) | ≈ 2400 (78%) |
   | A 1024 / 2048 | ≈ 1920 (94%) | ≈ 1660 (81%) | ≈ 1700 (83%) |
   | A 2048 / 4096 | 3537 measured (86%) | ≈ 3000 (73%) | ≈ 3100 (76%) |
   | **B 2048 / 3413** | **≈ 3537 (104%) → kill** | ≈ 3000 (88%) | ≈ 3100 (91%) |
   Family A is now predicted **negative at every level** (the pools at default are ≤ ½ of L − H and memtable
   occupancy stays near ⅓ of its cap); family B is predicted to fail.
4. **Revised search and limits.** Family A: converge ×1 at 1536/3072 and 1024/2048; then at 2048/4096
   converge ×3 (incl. `converge-1`), `M_only` ×3, `F_only` ×3. If an A level fails, it takes the ×3 /
   controls / intervention block instead. Family B (after A): converge ×1 at 3413; if killed, one bisect step
   upward (3584 MiB, between 3413 and the 3537 MiB peak + headroom) ×1; then at the largest failing L:
   converge ×3, `M_only` ×3, `F_only` ×3, `int_F128` ×3 (`file_cache_size` 128 MiB). **Arm cap raised from 22
   to 28 executions** (B arms, as allowed by the review); **wall cap unchanged: phase 2 ends by 13:40 MST**
   (6 h from 07:40). If time runs short, family B's ×3 blocks take priority over A's remaining repeats.

## Amendment 2 (2026-11-12 08:50 MST, after `A1536-converge-1`, before any family-B reading)

- `A1536-converge-1` survived at 2732 MiB = 88.9% of 3072 (amendment 1 predicted 89%). Its 50,000-read fill
  took 5 min (167 op/s, cold rotational reads) while the cache was already full from the preload.
- **Cache-fill pass cut to 10,000 reads** (`N_FILL=10000` in the environment of `run-all2.sh`) for every arm
  from family B on. It is only a check that the cache is full before the burst. Earlier arms used 300,000
  (`A2048-converge-1`) or 50,000 reads; the pre-burst state (pool full, memtable 0) is the same.
- **Order** (time cap unchanged, 13:40 MST; arm cap 28): after `A1024-converge-1`, family B at 3413 MiB first
  (converge-1; if killed, the ×3 block: converge, `M_only`, `F_only`, `int_F128`), then one bisect step at
  **L = 3500 MiB** (×1), then family A's 2048/4096 negative block (converge-2..3, `M_only` ×3, `F_only` ×3).
  If B3413-converge-1 survives, B steps **down** instead (3200 MiB ×1) and the B ×3 block runs at the largest
  failing L, if there is one.

## Amendment 3 (2026-11-12 09:06 MST, after `A1024-converge-1`, before any A-768 reading)

- `A1024-converge-1` survived at 1885 MiB = 92.0% of 2048 (amendment 1: 94%). Peak − H: 1489 / 1196 / 861 MiB
  at H 2048 / 1536 / 1024.
- §5 skipped levels below 1024 because the *workload-isolated* alone arms were predicted ≥ 97%. With
  configuration-isolated controls (amendment 1) the prediction at **A 768 / 1536** (direct 384) is: converge
  ≈ 768 + ≈ 750 = 1518 MiB (≈ 99%), `M_only` ≈ 1280 (≈ 83%), `F_only` ≈ 1330 (≈ 87%). It is inside the accepted
  family-A range (heap ≥ 512). **Added: `A768-converge-1` ×1** after `B3413-converge-1`. If killed, A-768 gets the
  ×3 block (converge, `M_only`, `F_only`, `int_F64`) ahead of the A-2048 negative block. A 512 / 1024 is not
  run: `M_only` alone is predicted ≥ 100% (≈ 512 + 550).

## Pause and resume note (2026-11-12 11:00 MST, researcher's request)

Phase 2 is **paused**. `/mydata/r1v/STOP` exists. No Cassandra, stress, poller, harness or chain process is
left on apt149, there is no `oom-r1v-*` scope, and ports 7000/7199/9042 are free (checked 11:00 MST).
Used: 07:40–11:00 MST (3 h 20 min of the 6 h cap; 2 h 40 min remain), **18 valid arm executions of 28**.

**Completed arms** (raw: `/mydata/r1v/logs/<arm>/`; excerpts: `../logs/<arm>/`). MiB; peak = max RssAnon.

| Arm | H / L | Peak (% of L) | Outcome |
|---|---|---|---|
| A2048-converge-1 (300k fill) | 2048 / 4096 | 3537 (86.3%) | alive |
| A2048-M_alone-1 (burst only; superseded as a control, amendment 1) | 2048 / 4096 | 3511 (85.7%) | alive |
| A2048-F_alone-1 (preload + fill; supplementary) | 2048 / 4096 | 3497 (85.4%) | alive |
| A1536-converge-1 (50k fill) | 1536 / 3072 | 2732 (88.9%) | alive |
| A1024-converge-1 (50k fill) | 1024 / 2048 | 1885 (92.0%) | alive |
| B3413-converge-1..3 | 2048 / 3413 | 3342 / 3325 / 3366 sampled; kernel anon-rss 3342 / 3329 / 3367 | **kernel memcg OOM-kill 3/3**, 90–95 s into the preload |
| B3413-M_only-1..3 | 2048 / 3413 | 2993 / 2989 / 2953 (86.5–87.7%) | alive 3/3 |
| B3413-F_only-1..3 | 2048 / 3413 | 2956 / 2945 / 2956 (86.3–86.6%) | alive 3/3 |
| B3413-int_F128-1..3 | 2048 / 3413 | 3113 / 3103 / 3119 (90.9–91.4%) | alive 3/3; burst ≈ 1.27M writes, as `M_only` |

**Void (not readings):** `void-A2048-converge-1-aborted` (07:39, forced handback) and
`void-A768-converge-1-stopped` (started 10:55; stopped by this pause in its preload at RssAnon 1492 of
1536 MiB, no kill).

**Remaining, in order:**
1. `A768-converge-1` (amendment 3 probe). If killed: A-768 ×3 block (`converge` ×2 more, `M_only` ×3,
   `F_only` ×3, `int_F64` ×3) has priority, within the 28-arm cap.
2. `B3500-converge-1` (bisect step, family B).
3. Family-A 2048/4096 negative block: `A2048-converge-2..3`, `A2048-M_only-1..3`, `A2048-F_only-1..3`.

**Exact resume commands** (on apt149; lists `list-c1.txt`, `list-c2.txt` are already written):

    cd /mydata/r1v && rm -f STOP
    N_FILL=10000 nohup bash run-all2.sh list-c1.txt > logs/run-c1.log 2>&1 < /dev/null &      # A768-converge-1 (direct = L/4 = 384)
    # after LIST DONE in logs/run-c1.log:
    DIRECT=1024 N_FILL=10000 nohup bash run-all2.sh list-c2.txt > logs/run-c2.log 2>&1 < /dev/null &   # B3500-converge-1
    # then (edit if A768 failed; family A uses direct = L/4, so do not set DIRECT):
    N_FILL=10000 nohup bash run-all2.sh list-a2048-b.txt > logs/run-a2048-b.log 2>&1 < /dev/null &
    # excerpts: bash export.sh <L> <arm>...  then copy /mydata/r1v/export/<arm> to ../logs/

`list-a2048-b.txt` already holds the eight A-2048 arms (M_only / F_only / converge-2..3). Its converge arms
will use the 10k fill. Remaining wall budget at resume: 2 h 40 min (arms take ≈ 4 min when killed, ≈ 10–13 min
otherwise).

## Resume (2026-11-12 12:03 MST) and amendment 4 (12:20 MST, before any A-768 control or repeat)

- Resumed 12:03 MST by the coordinator's message (STOP removed); wall cap from the pause note: **14:43 MST**.
- `A768-converge-1` (H 768, L 1536, direct 384): **kernel memcg OOM-kill**, ≈ 225 s into the burst, kernel
  anon-rss 1495 MiB (1530924 kB); pool 192 MiB full, memtable K ≤ 67 of 192. `B3500-converge-1` is running
  (chained, started 12:15).
- Per amendment 3, the **A-768 ×3 block takes priority**: `converge-2..3`, `M_only-1..3` (`F=off`),
  `F_only-1..3` (`M=heapbuf`), `int_F64-1..3` (`file_cache_size` 64 MiB, cache weight 32 MiB), interleaved so that
  each kind has ≥ 1 run early: converge-2, M_only-1, F_only-1, int_F64-1, converge-3, M_only-2, F_only-2,
  int_F64-2, M_only-3, F_only-3, int_F64-3.
- **The family-A 2048/4096 negative block is dropped**: family A now has a failing level, so 2048/4096 (and
  1536/3072, 1024/2048) are reported as surviving boundary levels with n/N = 0/1, not as a negative.
- **Arm cap raised from 28 to 31** (11 A-768 arms after `B3500-converge-1`); **wall cap unchanged (14:43 MST)**.
  If an arm would end after 14:43, `/mydata/r1v/STOP` stops the list and the missing repeats are reported as
  not run.

## Amendment 5 (2026-11-12 12:50 MST, after `A768-converge-2` and `A768-M_only-1`, before further A-768 readings)

- `B3500-converge-1` (family B bisect): **kernel memcg OOM-kill** ≈ 100 s into the preload, anon-rss 3453 MiB.
  Family B fails at 3413 (3/3) and 3500 (1/1); the same heap/direct survives at L 4096 (`A2048-converge-1`,
  peak 3537 MiB). No further B bisect step fits the budget.
- `A768-converge-2` **survived** (peak 1474 MiB, 95.9%); `A768-converge-1` was killed. `A768-M_only-1` survived
  (84.5%). The outcome at A-768 is mixed, so per protocol step 6 the repeats are expanded. **The remaining A-768
  arms are reordered** (new list `list-a768b.txt`, started after `A768-F_only-1` ends; the old list is stopped by
  the STOP file before its next arm): `converge-3`, `M_only-2`, `F_only-2`, `converge-4`, `M_only-3`,
  `F_only-3`, `converge-5`, then `int_F64-1` only if time allows. A-768 intervention ×3 is **not run**:
  with a mixed converge rate it would not be interpretable within the budget (V4 for A-768 is reported as not
  met). Arm cap stays 31; wall cap stays 14:43 MST (the 14:31 guard still stops new arms).

## Phase 2 end (2026-11-12 14:37 MST)

Last arm `A768-int_F64-1` ended 14:37 (its burst never started: `cassandra-stress` schema-creation timeout;
invalid). Arms after the resume: `A768-converge-1..5` (kill 1/5), `B3500-converge-1` (kill), `A768-M_only-1..3`,
`A768-F_only-1..3` (0/6), `A768-int_F64-1` (invalid). Totals: 30 executions (29 valid, 1 invalid) plus 2 void
of the 31-arm cap; wall 07:40–11:00 and 12:03–14:37 MST. The family-A 2048/4096 negative block was not run
(amendment 4). `/mydata/r1v/STOP` present; no process, scope or open port left. Results and status:
[case file](../memtable_offheap_space+file_cache_size--default.md).
