# R21 (retry of R16 / B18) — memtable_heap_space: the stale `updateF` in each SEP worker's pooled `BTree.Updater` pins flushed, DISCARDED memtables  <!-- file: cassandra/cases/memtable_heap_space--stale-btree-updater-pins-discarded-memtables/memtable_heap_space--stale-btree-updater-pins-discarded-memtables.md -->

| Field | Value |
|---|---|
| Case ID | `R21` (R = a new attempt at an earlier case; README "ID prefixes"), retry of **R16** (itself the retry of **B18**). Predicted class by the protocol's measurement table: **bypass, release defect** (U > C, K ≤ C in the memtable domain: memory released from `memtable_heap_space` at discard while still reachable); stage 2 labels it from the readings (§2.7) |
| From | retry-list row **R16** of [`phase2-retry-list.md`](../../phase2-retry-list.md) (Status `picked again: R21 (2026-11-21)`); lineage B18 ← cluster `OC-323` (primary), `OC-46`, `OC-367`, `OC-373`, `OC-257`, `OC-266`, `OC-41` |
| Phase-1 case file | **none for the re-targeted holder** (found by R16's stage-2 diagnostic, not by phase 1). The lineage's phase-1 files are listed in [R16's header](../memtable_heap_space--hot-partition-cas-retries-gated-client/memtable_heap_space--hot-partition-cas-retries-gated-client.md); the nearest is [`memtable_heap_space-tryAllocate-limit--autonomous`](../../../../capacity-enforcement-exp/cassandra/stage3-ai-deep-read/cases/memtable_heap_space-tryAllocate-limit--autonomous.md) (OC-41, the pool whose charge is released) |
| System / pinned source | Cassandra 5.0.9 (`systems/cassandra/source/`, `build.xml` `base.version` 5.0.9; on pc75 `/mydata/s4/cassandra-base`, `build/apache-cassandra-5.0.9-SNAPSHOT.jar`, sha256 `570b5249…0176e`), OpenJDK 11.0.33 |
| Stage 1 (design) | OOM-agent stage-1 session, 2026-11-21 01:50–02:50 America/New_York; nothing run (read-only check of pc75, read-only GitHub source reads, read-only JIRA REST searches) |
| Stage 2 (verify) | fresh OOM-agent stage-2 session, 2026-11-21 02:01–04:40 America/New_York, pc75 (freeze hash checked: `4efd3a2d…6688` matches); 24 lifetimes + Step A (3 shakedowns); no amendment |
| Verdict | **true positive** — `verified-OOM · deployment`, **bypass (release defect)**, outcome row 1 |

## Summary

- **Conclusion:** **true positive** (`verified-OOM · deployment`, bypass — release defect). At 2 GiB heap and every shipped default,
  the hot-partition write workload (T) OOMs the unmodified 5.0.9 node 3/3 within 7–8 s; the matched perthread control survives 3/3; the
  two-line diagnostic patch (trunk's `Updater.reset()` nulling `updateF`/`comparator`) removes the OOM 3/3 at 37–46 × the unpatched
  pre-OOM acknowledged load. In every OOM dump 1,449–1,655 slab regions (2.83–3.23 × the 512 MiB pool, above the 626 MiB contract) are
  reachable **only** through the stale `BTree$Updater.updateF` while the pool counter reads 173–443 MiB (0.34–0.87 × C). The same holds
  for the `concurrent_writes: 4` shape (3/3 OOM, patch 3/3 survive), for 4 hot partitions at all defaults (2/2 OOM, patch survives), and
  at idle: after all memtables are flushed, 609 MiB (1.19 × C) stays pinned with K = 0.5 MiB for 300 s on U and 0 regions on P.
- **Root cause (verified):** every write merges into a memtable partition through a pooled
  `BTree.Updater` kept per thread in a `TinyThreadLocalPool`; `Updater.reset()` (`BTree.java:3600-3604`) clears the builder buffers
  but never nulls `updateF` (or `comparator`), so each SEP worker thread keeps a reference to the `AtomicBTreePartition$Updater` of
  its last write and through it the whole partition of that memtable. When the memtable is flushed and DISCARDED its charge is released
  from `memtable_heap_space` (`MemtableAllocator.java:140-154`), but every slab region holding one of that partition's cells stays
  reachable, uncounted, until the thread writes again (idle SEP workers park and never exit). With one hot partition each pin is a
  whole memtable; a few pinned memtables fill a 2 GiB heap while the pool counter stays below its limit (R16: pool 0.54–0.93 × C,
  regions reachable only through `updateF` 2.67–2.76 × C).
- **What is new against R16:** the claim, class and intervention are re-targeted at that holder: a **diagnostic build whose
  `Updater.reset()` also nulls `updateF` and `comparator`** (the same two lines trunk carries since 2025-07-23, §1.4), run beside the
  unmodified build for T, the `concurrent_writes: 4` shape and C (≥ 3 each); U = regions reachable only through `updateF`, K = the
  pool's decoded fields; a multiplicity dial; an idle-retention reading after explicit flushes.

## 1. Candidate

### 1.1 The retry row, quoted

From [`phase2-retry-list.md`](../../phase2-retry-list.md):

> | [R16](cases/memtable_heap_space--hot-partition-cas-retries-gated-client/memtable_heap_space--hot-partition-cas-retries-gated-client.md) (retry of B18) | 2026-11-20 | Gated client removed B18's re-send backlog: T OOM 3/3 at 2 GiB and 15,872 MiB, control C survives 3/3. But the intervention (`concurrent_writes: 4`) removed the overshoot and still OOMed 3/3; dumps show the pool counter ≤ C while 2.7 × C of slab regions are reachable only through the stale `updateF` of each SEP worker's pooled `BTree.Updater` (`BTree.java:3593-3604` `reset()` never nulls it), pinning flushed, DISCARDED memtables. V4 unmet | Re-target the holder (bypass · release defect, U > C, K ≤ C): intervention = diagnostic build whose `Updater.reset()` nulls `updateF`/`comparator`; run T, the `concurrent_writes: 4` shape and C ≥ 3 each on unpatched and patched builds; U = `hprof_reach.py` regions reachable only via `updateF`, K = decoded pool fields; dial SEP threads × pinned partition size (1/4/36 partitions per memtable); add an idle-retention reading; check 5.0.10/trunk first | picked again: R21 (2026-11-21) |

### 1.2 Earlier cases and verdicts

| Case | Date, node | Verdict (detail) | What it established | Used in R21 |
|---|---|---|---|---|
| [B18](../memtable_heap_space--hot-partition-cas-retries-past-flush-barrier/memtable_heap_space--hot-partition-cas-retries-past-flush-barrier.md) | 2026-11-18, pc75 | retry (`candidate`; V2 via fallback only, V4 not met) | hot-partition CAS retries admitted past the limit inside the blocking cohort (flushing memtable 216–382 % of C at 5 MiB); T OOM 3/3 at 2/4/8 GiB; C and I died from a client re-send backlog | the T workload shape |
| [R16](../memtable_heap_space--hot-partition-cas-retries-gated-client/memtable_heap_space--hot-partition-cas-retries-gated-client.md) | 2026-11-20, pc75 | retry (`candidate`; V1–V3, V5–V7 met for T at 2 GiB, V4 not met; outcome row 3) | gated client (no re-send while a write may be pending) removed the backlog; T OOM 3/3 at 7 s (0 timeouts), C (perthread) survives 3/3, I (`concurrent_writes: 4`) OOM 3/3 at 64–100 s with no contention flag; pool counter 0.54–0.93 × C at every 2 GiB OOM dump vs live regions 3.48–3.56 × C; regions reachable only via `BTree$Updater.updateF`: T-2 1,402 (2.74 × C), I-2 1,368, I-3 1,413, C-2 end (idle) 431 (0.84 × C); budget search: T OOM 3/3 at 15,872 MiB (S = 14 MiB; pool 1.10–1.34 × C, uncounted ≥ 2.31–2.56 × C); 4 GiB S = 1.25 MiB T OOM with every barrier ≤ 87 % of C; D8, D16 OOM | harness, gate, scanner, `hprof_reach.py`/`hprof_refs.py`, the arms T/C/I, all readings as the expected unpatched response |

R16's §4 lists what the next design should change: (1) re-target holder and class; (2) intervention = diagnostic build nulling the two
fields, T and the I shape ≥ 3 each on it, re-run T and C beside it; (3) U = `hprof_reach.py` "only via `updateF`" at every OOM and end
dump, plus decoded K, keep the gated client; (4) multiplicity dial and idle retention; (5) version check first. **R21 implements all five.**

### 1.3 Phase-1 constraint and stage-4 measurements

No phase-1 case names this holder. The constraint is `memtable_heap_space` (heap/4 at the shipped `heap_buffers` allocator), whose
charge for a memtable's regions is released at discard (`SubAllocator.setDiscarded` → `releaseAll`, `MemtableAllocator.java:140-154`); the
phase-1 lead for that pool is OC-41 (`memtable_heap_space-tryAllocate-limit--autonomous`, check `tryAllocate` against `limit`). Stage 4
of that lead measured the counter against the limit only; nothing measured retention after discard. Same holder **type** as C6 (verified;
slab regions × written tables, uncounted regions); different mechanism (C6: regions outside any pool's view across many tables; here:
regions released from the pool and kept alive by a thread-local reference).

### 1.4 Version check and JIRA prior art (2026-11-21, read only; nothing posted)

**Source of `BTree.Updater.reset()` across versions** (GitHub raw / API, read only; `/tmp/r21-src/` on the controller, not kept):

| Ref | `Updater.reset()` nulls `updateF`/`comparator`? |
|---|---|
| `cassandra-5.0.9` tag (= the pin; `systems/cassandra/source` Updater class identical) | **no** (`super.reset(); insert.reset();`) |
| `cassandra-5.0.10` | **tag does not exist** on 2026-11-21 (`git ls-remote`: latest 5.0 tag is `cassandra-5.0.9`; 5.0.10 is only a JIRA fix version) |
| `cassandra-5.0` branch head (last BTree.java commit 2026-08-04, `52ff1c1f4e` "Fix memtable on-heap accounting drift …") | **no** (Updater differs from the pin only in `DISABLED`/`completeBuild(update)`) |
| `cassandra-4.1.10`, `cassandra-4.1.12` tags | **no** |
| `trunk` (6.0/7.0 line) and tag `cassandra-6.0-alpha1` | **yes**: `reset() { super.reset(); insert.reset(); comparator = null; updateF = null; }` |

Trunk got the two lines in commit `54e39a90b0` (2025-07-23, Benedict, "Limit replay to those records not durably persisted to both
command store and data store", **CASSANDRA-20780**, an Accord change; it moved `comparator = null` from `close()` into `reset()` and
added `updateF = null`). Its message lists "clear heavy fields in some messages once processed" among side fixes; it names no memtable
retention, has no fix version, and was **not backported** to 4.1/5.0.

**JIRA** (local survey `capacity-enforcement-exp/cassandra/stage5-oom-clue-find/jira-oom-survey.csv`, 604 rows, grep `threadlocal`,
`thread local`, `BTree`, `updater`, `pooled`, `retain`, `leak`, `discarded`; JIRA REST reachable: `text ~ "TinyThreadLocalPool"` (5),
`text ~ "updateF"` (4), `BTree AND Updater AND leak` (13), `memtable AND "thread local" AND retain` (26), `"flushed memtable" AND "heap dump"`
(51, first 15 read), `SEPWorker AND memtable` (82, first 15 read), `key = CASSANDRA-20780`):

| Issue | Status | Relevance |
|---|---|---|
| CASSANDRA-13754 "BTree.Builder memory leak" | Fixed 3.11.1 | same family: recycled thread-local BTree builders on `FastThreadLocalThread`s held > 10 GB of a 12 GB heap; fixed for the builder, not this field |
| CASSANDRA-19785 "Possible memory leak in BTree.FastBuilder" | Fixed 4.0.14/4.1.7/**5.0.1** | same family (thread-local FastBuilder growth); in 5.0.9; does not touch `Updater.updateF` |
| CASSANDRA-11026 "OOM due to HeapByteBuffer instances" | Fixed 3.0.3 | 1 MiB `HeapByteBuffer` slabs retained (≈ 2 GB) in 3.0.2; older code path |
| CASSANDRA-20780 (Accord) | Resolved, no fix version | carries the trunk fix incidentally (above) |
| CASSANDRA-21418 "Switch more hot thread locals to CassandraThread-based ones" | Open (7.x) | lists `TinyThreadLocalPool` among thread locals to move; no retention claim |
| CASSANDRA-21055 (shared `Row.Builder` not freed after a rejected collection update) | Fixed 6.0-alpha1 | a different pooled-builder leak |
| CASSANDRA-21472, CASSANDRA-21019, CASSANDRA-18125 | Fixed 5.0.10 / 5.0.10 / 5.0 | memtable accounting and limit checks, not retention after discard |

**Verdict: `new` for every released line that a deployment runs (4.1.x, 5.0.x up to the latest release 5.0.9 and the 5.0 branch head);
fixed only on trunk / 6.0-alpha by an unrelated commit, with no issue describing the retention.** It is not `known-fixed` in the sense of
playbook stage 1 (no released version of the pinned line has the fix); the owner may rule otherwise (then R21 runs as a positive control,
unchanged). The trunk change is the exact intervention used here, which also shows the patch is safe.

## 2. Design solution (stage 1; frozen)

### 2.1 Mechanism and direction

- **Write path** (unchanged from R16 §2.1): CQL write, CL ONE, one node, applied on `MutationStage` (SEP executor; threads =
  `concurrent_writes`, default 32). `AtomicBTreePartition.addAll` makes a new `AtomicBTreePartition$Updater` per call
  (`AtomicBTreePartition.java:120-123`; inner class at `:137-145`, field `current`, implicit `this$0` = the partition). Values are cloned
  into the memtable's `SlabAllocator` 1 MiB on-heap regions (`heap_buffers`); a cloned cell is a `ByteBuffer` slice of its region's
  `byte[]` (`SlabAllocator.java:197-205`), so **one live cell keeps its whole 1 MiB region alive**.
- **The pooled updater.** The merge runs `BTree.update(current.tree, update.holder().tree, comparator, this)`
  (`BTreePartitionUpdater.java:89`) → `try (Updater updater = Updater.get())` (`BTree.java:395-398`): `Updater.get()` polls a per-thread
  `TinyThreadLocalPool` (Netty `FastThreadLocal`, up to 3 pooled objects per thread, `TinyThreadLocalPool.java:23-74`; `BTree.java:3426-3434`);
  `update(…)` sets `this.updateF = updateF; this.comparator = comparator` (`:3443-3445`); `close()` → `reset()` → `pool.offer(this)`
  (`:3593-3604`). `reset()` calls `AbstractFastBuilder.reset()` (clears leaf/branch buffers, `:3273-3290`, the CASSANDRA-19785 fix) and
  `insert.reset()`, but **not** `updateF = null` / `comparator = null` (fields `:3422-3423`).
- **The pin.** The pooled updater's `updateF` is the `AtomicBTreePartition$Updater` of that thread's last write → `this$0`
  (`AtomicBTreePartition`, its `ref` = the partition's final tree) and `allocator`/`cloner` (the memtable's `SlabAllocator`). When the
  memtable is flushed, `setDiscarded()` releases its whole charge from the pool (`MemtableAllocator.java:140-154`), but every region that
  holds a cell of the pinned partition stays reachable until that worker's next write replaces `updateF`. SEP workers are shared by all
  SEP stages (MutationStage, Native-Transport-Requests, ReadStage, …); an idle worker parks in `pool.descheduled` and its thread never exits
  before shutdown (`SEPWorker.java:210-240`, `SharedExecutorPool.java:114`, `:170-176`), so a pin lasts while the worker does other
  stages' work or nothing.
- **Multiplicity.** Retained ≈ D × M × f: **D** = distinct DISCARDED memtables still referenced by ≥ 1 pooled updater (≤ the number of SEP
  workers whose last mutation fell in a memtable that has since been discarded); **M** = that memtable's regions at discard (T: 500–660
  MiB, inflated by failed-CAS clones; I: ≈ 175 MiB; C: 170–280 MiB at 2 GiB); **f** = fraction of M holding ≥ 1 cell of a pinned partition
  (1 for one hot partition; with several partitions concurrent writers interleave their cells in the shared current region, so f stays high
  — R16's C idle: 431 regions over 4–8 DISCARDED allocators). At 2 GiB an OOM needs D·M·f ≳ 1.4 GiB: T D ≥ 3, I D ≥ 8 (R16 dumps: 3 and 8
  DISCARDED allocators). D grows when many workers stop running mutations at different times (T: writers stall on contention; I: only 4
  mutations run at once while ≥ 36 workers rotate through native-transport and mutation tasks); it stays low when every worker keeps writing
  (C: the stale reference is replaced within one memtable).
- **Direction label: bypass — release defect** (U > C with K ≤ C in domain D1: the bytes are released from the pool's counter at discard
  while still reachable). Interpretation: **suspected implementation defect** (the method comment of `AbstractFastBuilder.reset()` says
  "Clear any references we might still retain, to avoid holding onto memory"; trunk nulls both fields). The B18 overshoot (blocking cohort
  admits failed-CAS clones past the limit, K > C) still exists in T and enlarges M; if a T dump shows K > C_contract as well, the T result is
  **mixed** (enforcement failure + release defect), and the patched build tells which one is necessary. Technique note:
  [`bypass-playbook.md`](../../../bypass-playbook.md), row "Ownership/release defect" (repeated fill/clear/idle cycles, residual live
  allocations versus cycle count and a healthy release control), with the multiplicity step of [`combo-playbook.md`](../../../combo-playbook.md).

### 2.2 Protection map (2 GiB heap, S = 1.25 MiB)

| Domain | Allocation, owner, release | Local contract (C) | Scope / multiplicity | Aggregate coverage | Lifetime |
|---|---|---|---|---|---|
| **D1 memtable regions + charged overhead** | `SlabAllocator` 1 MiB `byte[]` regions of `ks.t` (and system) memtables; charged at clone; released from the counter at `setDiscarded` | `memtable_heap_space` = heap/4 = **512 MiB**, wait at the limit, flush at cleanup threshold 0.33; documented soft overshoot (blocking cohort's own attempts ≤ 40 MiB, 10 MiB waste allowance, region tail ≤ 12.5 %): **C_contract ≈ 626 MiB** (R16 §2.2) | all memtables share one pool | the pool; its contract ends at discard | until discard (seconds) — **by contract** |
| **D1-pin (the claimed holder)** | the same regions after discard, kept by `TinyThreadLocalPool$TinyPool.val1..3` → `BTree$Updater.updateF` → `AtomicBTreePartition$Updater` (`this$0`, `current`, `allocator`) on each `SEPWorker` `FastThreadLocalThread` | **none** — the pool has released the charge (K excludes it) | per SEP worker × its last-written partition; D·M·f (§2.1) | none | until that worker's next write (unbounded while idle) |
| D1' per-attempt garbage | failed merges' rows/cells | none | × attempts | GC | young gen |
| D2 decoded requests in flight | v4 frames → `Mutation`s | `native_transport_max_request_data_in_flight` heap/10 = 204.8 MiB, per IP heap/40 = 51.2 MiB; 36 × 1.25 = 45 MiB | per IP | global reserve | until response |
| D3 timed-out writes still queued | — | none; **bounded by the gated client** (D2 + D3 ≤ 36 × S = 45 MiB) | per client thread | — | until applied |
| D4 flush / compaction / commit log | flush writers, compaction buffers (heap), commit-log mmap | defaults | 2 flush writers | — | transient |
| D5 baseline | schema, metrics, caches, sampler | — | — | — | standing (L0 ≈ 65 MiB in R16) |
| Direct (recorded, not the budget) | Netty, `BufferPool` | `MaxDirectMemorySize` as resolved on pc75 (15,872 MiB) | — | — | RssAnon |

### 2.3 Configuration and budget audit

- **Builds.** **U** (unmodified): `cp -a /mydata/s4/cassandra-base /mydata/s4/r21/cassandra-u`, jar sha256 must equal
  `570b5249d9b9a43f6809eb3da562737492192026f974b2edbd20e94bea90176e` (B18/R16; a different hash is recorded and said in §3).
  **P** (diagnostic, the intervention): `cp -a /mydata/s4/cassandra-base /mydata/s4/r21/cassandra-p`; patch
  `src/java/org/apache/cassandra/utils/btree/BTree.java` `Updater.reset()` to

  ```diff
           void reset()
           {
               super.reset();
               insert.reset();
  +            comparator = null;
  +            updateF = null;
           }
  ```

  (the trunk lines of §1.4; nothing else). Save the diff as `harness/updater-reset.diff` (`diff -u` of the file). Build **without Ant**:
  `javac -source 11 -target 11 -nowarn -encoding UTF-8 -cp 'build/apache-cassandra-5.0.9-SNAPSHOT.jar:build/lib/jars/*' -d /mydata/s4/r21/pcls
  src/java/org/apache/cassandra/utils/btree/BTree.java`, then `jar uf build/apache-cassandra-5.0.9-SNAPSHOT.jar -C /mydata/s4/r21/pcls
  org/apache/cassandra/utils/btree` restricted to the `BTree.class` and `BTree$*.class` files javac wrote (list them; record names).
  Checks (Step A, a failure stops the case before readings): `javap -c -p -cp <P jar> 'org.apache.cassandra.utils.btree.BTree$Updater'`
  shows `aconst_null`/`putfield …updateF` and `…comparator` in `reset()`, the same command on U shows neither; the class file major version
  equals the original's (55); `unzip -l` member list of the P jar equals U's; record P's jar sha256. Fallback only if javac fails: `ant jar`
  in `cassandra-p` after deleting `build/classes/main/org/apache/cassandra/utils/btree/BTree*.class` (HANDOFF lesson: 1-s timestamps), before
  any node runs from that tree. No other file of either tree changes; `/mydata/s4/cassandra-base` is never modified.
- **Node/OS** (pc75, as R16 §3.1): x86_64, 40 cores, 125 GiB, Ubuntu 22.04, kernel 5.15, cgroup v2, swap 8 GiB present, JDK 11.0.33,
  GC = shipped `jvm11-server.options` (G1, `G1HeapRegionSize=16m`, `G1NewSizePercent=50`, `MaxGCPauseMillis=300`,
  `HeapDumpOnOutOfMemoryError`; `cassandra-env.sh` `OnOutOfMemoryError=kill -9 %p`). pc75's clock zone is America/Denver: every
  cut-off in the harness uses `TZ=America/New_York`.
- **Capacity constraints (V6), shipped defaults, read back from `system_views.settings` every lifetime** (R16 §2.3 list):
  `memtable_allocation_type: heap_buffers`; `memtable_heap_space`/`memtable_offheap_space` → heap/4; `memtable_cleanup_threshold` → 0.33;
  `memtable_flush_writers` → 2; `concurrent_writes: 32`; `concurrent_reads: 32`; `concurrent_counter_writes: 32`;
  `native_transport_max_threads: 128`; `native_transport_max_request_data_in_flight`/`_per_ip` → heap/10, heap/40;
  `native_transport_max_message_size` → 16 MiB; `max_mutation_size` → 16 MiB; `commitlog_segment_size: 32MiB`; `commitlog_total_space` →
  8,192 MiB; `write_request_timeout: 2000ms`; `native_transport_timeout` 12 s; hints on; key cache 100 MiB. Labels: all **default**.
- **Arm-only deviations:** I and P-I: `concurrent_writes: 4` (a shipped setting, changed only in the I shape; §2.8 says how the I shape
  counts). The P build in P-arms (the diagnostic patch = the intervention). Instrument only: `nodetool setlogginglevel
  org.apache.cassandra.db.memtable.SkipListMemtable TRACE`. No Byteman, no raised timeout, no fault. Conditions label of the unpatched
  default arms: `deployment`.
- **Environment diff only:** `cluster_name: r21`, `listen_address`/`rpc_address: 127.0.0.1`, seeds `127.0.0.1:7000`, data, commit log,
  hints, saved caches, cdc under `/mydata/s4/r21/run/`; client source addresses 127.0.0.11–14.
- **Budget (V7):** heap `MAX_HEAP_SIZE=2G` (the ideal; ≥ 512 MiB standing rule, no review needed); `MaxDirectMemorySize` as
  `cassandra-env.sh` resolves on pc75 (15,872 MiB; recorded). **No container limit:** the node runs in `systemd-run --user --scope -p
  MemorySwapMax=0` **without `MemoryMax`** (record `memory.max` = `max`; the scope exists only to keep swap off and to read
  `memory.current`/`memory.events`). The client JVM keeps its own scope (`MemoryMax=4G`, `-Xmx3g`), which is not the victim. Budget search:
  R16's 15,872 MiB result (T OOM 3/3) is reused with documented equivalence (same jar sha256, settings, client, harness lineage); R21
  adds an optional patched lifetime at 15,872 MiB (§2.9).
- **Resolved values to record:** pool limit 512 MiB (2 GiB), cleanup threshold, in-flight limits (204.8 / 51.2 MiB), `MaxDirectMemorySize`,
  key-cache cap, `memory.max`/`memory.swap.max` of the scope.

### 2.4 Ceiling arithmetic (2 GiB, S = 1.25 MiB)

| Item | Bound | Source |
|---|---|---|
| D5 baseline | ≈ 100 MiB (L0 65 MiB + sampler) | R16 §3.1 |
| D2 + D3 (gated) | ≤ 45 MiB on wire × ≈ 2 decoded ≈ 90 MiB | §2.2 |
| D1 contract | C_contract ≈ 626 MiB | §2.2 |
| D4 transient | ≈ 50 MiB | estimate |
| **Σ contract + baseline** | **≈ 0.85 GiB < 2 GiB** (margin ≈ 1.15 GiB) | |
| D1-pin (uncontracted) | D·M·f; T: 3 × 0.5–0.66 GiB ≈ 1.5–2.0 GiB; I: 8 × 0.17 ≈ 1.4 GiB; C: 0.4–0.6 GiB at idle (R16) | §2.1, R16 §3.4 |

Convergence of contract capacities cannot reach 2 GiB; an OOM needs ≳ 1.1 GiB outside the contract, which D1-pin supplies in T and I
and which the patch removes. **Patched build, T shape:** without D1-pin the B18 overshoot remains; per barrier the flushing memtable is
98–129 % of C (R16), with ≤ 2 flushing memtables (2 flush writers) plus the live one: worst ≈ 2 × 660 + 170 + 100 + 90 ≈ 1.68 GiB, typical
≈ 0.9–1.2 GiB (each flushing memtable holds only 50–62 MiB of rows, so its flush ends in < 2 s and its regions become garbage at discard).
R16's T dumps with `updateF` cut held 504 MiB reachable. **Predicted: P-T survives** (moderate confidence: the worst case is within 20 % of
the heap). **Patched I and C:** ≤ 0.85 GiB, survive (high confidence).

### 2.5 Workload and environment (pc75 only)

**Node check (stage 1, read-only, 2026-11-21 01:53 EST):** pc75 = `pc75.cloudlab.umass.edu` (node3.jason92-326665), 40 cores, 125 GiB
(124 GiB available), `/mydata` 714 GiB free (419 MiB used), **no Java process**, ports 9042/7000/7199 free, JDK 11.0.33, `javac`, `jar`,
`ant` present, `/mydata/s4/` holds only `cassandra-base` (**R16's `/mydata/s4/r16` is gone**: rebuild from R16's repo harness), base jar
sha256 `570b5249…0176e` (= R16).

**Directories (pc75, local `/mydata` only):** `/mydata/s4/r21/{cassandra-u,cassandra-p,pcls,harness,cls,run,dumps,logs}`; `run/` recreated
per lifetime; dumps moved to `dumps/` for analysis then deleted. Do not touch `/mydata/s4/cassandra-base` or other cases' folders.
**Co-tenancy** before every lifetime: no other `CassandraDaemon`, ≥ 40 GiB available, ports free; else wait (bounded) and record.

**Harness** (`harness/` in this folder; base = R16's [`harness/`](../memtable_heap_space--hot-partition-cas-retries-gated-client/harness/),
copied, `r16` → `r21` in unit/cluster names and paths, keep everything else, notably the gate):

- **`run.py`** — R16's lifetime runner with: (a) a **build** argument `U`/`P` selecting `cassandra-u`/`cassandra-p`
  (`run.py life <label> <build> <arm> <heap> [R]`; the build, its jar sha256 and a `javap` one-liner of `Updater.reset()` are written to
  each lifetime's `summary.json`); (b) arms `T` (hot, cw 32), `I` (hot, cw 4), `C` (perthread, cw 32), **`Q`** (quad: pk = thread mod 4,
  cw 32); (c) the node scope **without `MemoryMax`**; (d) every OOM dump and every end dump moved to `dumps/<label>-<tag>.hprof` and queued
  for analysis instead of deleted (R16 amendment A2 made general); (e) mode **`idle <label> <build>`** (§2.6); (f) `plan.sh` cut-off **06:45
  America/New_York** (no new lifetime starts after it) and the `plan.halt` file.
- **`HotGen.java`** — R16's gated client unchanged plus mode `quad` (pk = global thread number mod 4; the gate polls the same pk).
- **`hprof_scan.py`** — R16's (pool `SubPool` fields, per-`SlabAllocator` `{regionCount, owns, reclaiming, state}`, region counts, top
  classes), plus each allocator's **object id** in its output.
- **`hprof_reach.py`** — R16's (reachable regions with and without the cut of `BTree$Updater.updateF` / of `TinyPool`), extended to print:
  the object ids of `SlabAllocator` instances reachable only through the `updateF` cut (**D**); the number of `SEPWorker` instances; the
  number of pooled `BTree$Updater` with non-null `updateF` (exists). Run `python3 -I`.
- **`hprof_refs.py`** (R16's, `discarded` mode) on the first OOM dump of each arm only (backward chain from DISCARDED allocators; shows the
  thread type holding each pin).
- **`reachq.sh`** (new) — a queue that, for each dump in `dumps/` in order, runs `hprof_scan.py`, `hprof_reach.py` (and `hprof_refs.py`
  where flagged) under `nice -n 19 taskset -c 36-39`, writes the JSONs to the lifetime's log folder, then deletes the dump. Analysis of
  a dump may overlap a later lifetime (4 of 40 cores, lowest priority; recorded); if the queue is > 6 dumps behind, `run.py` waits before
  starting the next lifetime until it is ≤ 3 behind.
- **`analyze.py`** — R16's plus, per dump: **U_pin** = regions only via `updateF`; **U** = live regions; **K** = `pool.allocated`
  (+ `reclaiming`); **uncounted** = live regions − Σ `regionCount` of non-DISCARDED allocators; **D** = number of DISCARDED allocators
  reachable only via `updateF`; **M_D** = Σ `regionCount` of those D allocators (from the scan, joined on object id); **f** = U_pin / M_D;
  SEP workers; stale updaters.
- Kept unchanged: `Jmx.java` sampler (500 ms), RSS loop (1 s), `after.sh`, `excerpts.sh`, `logback-client.xml`, `HoldRegions.java`,
  `instrument-check.sh` (extended below).

**Step A — tree and checks (not readings).** (1) copy both trees; patch, build and check P (§2.3); save the diff; (2) build `HotGen` and
the sampler; (3) **scanner known-answer check** (R16's, must pass exactly); (4) **reach known-answer check** (new): a test JVM (its own
classpath, never the node's) with a class `org.apache.cassandra.utils.btree.BTree$Updater` (test source `BTree.java` with a static nested
`Updater` having a field `Object updateF`) holds 10 × `byte[1048576]` reachable only through one `Updater.updateF`, 5 reachable through it
and through a static list, 7 reachable only through the static list; `jcmd GC.heap_dump` (live): `hprof_reach.py` must report reachable
regions 22 and regions only via `updateF` **10** exactly; also time the tool on that dump; (5) **source-binding shakedown** on U
(20 s, 2 GiB, `perthread` R = 64: sockets from 127.0.0.11–14) and the same 20 s shakedown on **P** (node starts, writes acknowledged, no
`ERROR` in `system.log`); (6) gate self-test on U (as R16: ≥ 20 gate waits ended by the first or second poll, 0 retired); (7) time
`hprof_reach.py` on the P shakedown's end dump.

**Lifetime** (labels `<build><heap>-<arm>-<n>`, e.g. `U2-T-1`, `P2-I-3`) — R16 §2.5 steps 1–8 with these differences: the build's tree;
no `MemoryMax`; step 7 keeps the OOM dump (wait ≤ 300 s for `Heap dump file created`) or, in a surviving lifetime at W = 240 s, stops the
client, waits 10 s, takes two `GC.class_histogram` (U_end) and one `GC.heap_dump` (live objects) — every surviving lifetime, every arm,
both builds; both go to `reachq.sh`.

### 2.6 Instruments and readings (U measured independently of K)

| Reading | Source | When | Meaning |
|---|---|---|---|
| **U_pin** (the claimed holder) | `hprof_reach.py`: regions reachable from GC roots minus regions reachable with `BTree$Updater.updateF` cut | every OOM dump and every end dump | bytes kept only by stale pooled updaters |
| **U** (D1 total) | dump `byte[1048576]` count × 1,048,592 B; reachable regions | same | physical live regions, independent of K |
| **K** | dump `SubPool.allocated`, `reclaiming`, `limit` (on-heap); per allocator `owns`, `regionCount`, `state` | same | the pool counter and per-memtable split |
| **uncounted** | U − Σ `regionCount` (non-DISCARDED) | same | regions outside every live charge (R16's metric) |
| **D, M_D, f; SEP workers; stale updaters** | `hprof_reach.py` + scan join (§2.5) | same | the multiplicity dial |
| K per memtable / pool total in flight | `Enqueuing flush …`, `Writing Memtable-t…(… on-heap)`, `Flushing largest … Used total` lines; `High update contention` TRACE | per flush | the B18 overshoot (whether K > C) |
| U trajectory | `gc.log` heap after each GC, old-gen after full GC | continuous | growth per flush |
| U_end | `GC.class_histogram` total and `[B` | surviving lifetimes, idle cycles | live heap |
| control activity | sampler: `BlockedOnAllocation`, `PendingFlushTasks`, MutationStage active/pending/completed, dropped MUTATION_REQ, write timeouts | 500 ms | cohort, backlog |
| client / gate | `hotgen.csv` (ok requests/rows per s, errors by class, `gated_now`, gate waits/polls, retired) | 1 s | load reached; throughput of each arm (intervention not stopping work) |
| first error (V5) | `stdout.txt` (`OutOfMemoryError: Java heap space`, `Dumping heap`, `Heap dump file created`, `kill -9`), `system.log`, dump thread stacks | OOM | initiating failure |
| process | `RssAnon`, scope `memory.current`, `memory.events` | 1 s / end | no external kill |

**Idle-retention reading (mode `idle`, one lifetime per build, 2 GiB, all defaults, perthread R = 160):** `s0`; then **3 cycles** of
{workload 60 s → stop client → `nodetool flush` (all tables; every `ks.t` memtable becomes DISCARDED) → 30 s idle → two
`GC.class_histogram` → `GC.heap_dump` (live) → queue}; after cycle 3 a further **300 s idle** and one more histogram pair and dump. Per
reading: U_pin, U, K, uncounted, D, histogram total. The perthread shape survives 240 s at 2 GiB in R16, so 3 × 60 s cannot OOM.

The OOM-time readings come only from the dump taken at the OOM (the sampler stalls in T, as in B18/R16); every other intrusive reading is at
the end of a lifetime or in the idle cycles (the workload is stopped first).

### 2.7 Predicted response, outcome rows and stopping budget

**Predictions (frozen).** C = 512 MiB (2 GiB heap). "Pre-OOM acked bytes" = rows acknowledged × 8 KiB before the OOM of that lifetime.

- **P1 (U-T, unpatched, hot, cw 32):** heap OOM **3/3** within 120 s (expected 5–20 s; R16 7 s), V5 lines present; each dump: U ≥ 2.5 × C,
  **U_pin ≥ 1.5 × C** (R16 2.74 ×), **K = `pool.allocated` ≤ 1.1 × C** (R16 0.54–0.93 ×), D ≥ 2, f ≥ 0.8. Writing lines 98–130 % of C and
  `High update contention in 1/1` (the overshoot, recorded).
- **P2 (P-T, patched, same workload):** **survives 240 s 3/3**; old-gen after every GC from workload + 30 s ≤ 0.80 × heap (1,638 MiB); end
  dump U_pin ≤ 16 regions and uncounted ≤ 32 regions; Writing lines still reach ≥ 95 % of C in ≥ 1 flush per run (the overshoot is
  untouched); acked bytes in 240 s ≥ **5 ×** the median U-T pre-OOM acked bytes (R16 ≈ 200 MiB → ≥ 1 GiB); client `retired` = 0.
- **P3 (U-I, unpatched, cw 4):** heap OOM **3/3** within 240 s (R16 64–100 s); no contention line; Writing ≤ 70 %; MutationStage pending ≤ 36;
  each dump U_pin ≥ 1.5 × C, K ≤ 1.0 × C, D ≥ 4.
- **P4 (P-I, patched, cw 4):** **survives 240 s 3/3**; old-gen after GC ≤ 0.80 × heap; end dump U_pin ≤ 16, uncounted ≤ 32; acked bytes in
  240 s ≥ **1.5 ×** the median U-I pre-OOM acked bytes (R16 U-I ≈ 3.0–4.1 GiB in 64–100 s, so ≥ 4.5–6 GiB; the patch must not slow the
  write path).
- **P5 (U-C, unpatched, perthread):** survives 240 s 3/3 (R16); end dump K ≈ 0 (≤ 16 MiB; the client is stopped, the current memtable may be
  small), **U_pin 0.4–1.2 × C** (R16 0.84 ×), uncounted ≥ 0.4 × C.
- **P6 (P-C, patched, perthread):** survives 240 s 3/3; end dump **U_pin ≤ 16 regions, uncounted ≤ 32 regions**; acked bytes within ± 15 % of
  the U-C median (the patch does not change throughput).
- **P7 (idle retention):** U build: in each of the 3 cycles and after the 300 s idle, K ≤ 16 MiB (system memtables only), **U_pin ≥ 0.25 × C
  (≥ 128 regions)**, D ≥ 1, and U_pin after 300 s idle ≥ 0.8 × U_pin of cycle 3 (no time-based release); residual does not need to grow
  with the cycle number (bounded by D·M·f; reported). P build: every reading U_pin ≤ 4 regions and live regions ≤ 32.
- **P8 (multiplicity dial; reported, not a verdict condition):** across T (1 partition per memtable), Q (4) and C (36) on U: f ≥ 0.8 for T,
  ≥ 0.5 for Q, 0.3–1.0 for C; U_pin ≈ D × M_D × f within ± 10 % by construction; D largest in T and I. Q on U (2 lifetimes): OOM or
  survival either way (stated; contention per partition 9 writers → overshoot ≈ 4 × 36 × 0.84 × 1.25 ≈ 150 MiB per barrier, memtables ≈
  320 MiB, OOM needs D ≥ 5); P-Q (1 lifetime) survives.
- **Validity (every lifetime):** read-backs equal the arm and §2.3; the build is the planned one (jar sha256 + `javap` line in
  `summary.json`); first-trigger check passes (≥ 5 requests acked, 4 client IPs, MutationStage active ≥ 24 in T/C/Q, ≥ 3 in I, or ≥ 24 / 3
  writer stacks in the dump if the sampler stalled first); `memory.events` `oom_kill` 0; no `ERROR` in `system.log` before the endpoint other
  than the OOM's and write-timeout lines; client `retired` = 0 (recorded, not invalidating, for U-T as in R16).

**Outcome rows** (the fixed condition is **U-T at 2 GiB, all defaults**; V2 = U-C; V4 = P-T):

| Readings | Verdict |
|---|---|
| U-T OOM 3/3; U-C survives 3/3; **P-T survives 3/3** with P2's acked floor; every U-T dump U_pin > C_contract (626 MiB) and K ≤ C_contract | **true positive** — `verified-OOM · deployment`, **bypass (release defect)**. Supporting (stated, not required): U-I 3/3 OOM and P-I 3/3 survive; idle P7 |
| as row 1 but some U-T dump has K > C_contract (the overshoot also past the contract at the endpoint) | **true positive**, `verified-OOM · deployment`, **mixed** (release defect necessary — the patch removes the endpoint — with the B18 enforcement failure enlarging each pin) |
| U-T 3/3, U-C 3/3 survive, **P-T OOMs in ≥ 1 run** and its dump has uncounted ≤ 32 regions and K ≥ 1.3 × C, while **P-I survives 3/3** and U-I OOMs 3/3 | **retry**: at defaults the counted overshoot (B18's claim) alone can exhaust 2 GiB, the release defect is shown only in the `concurrent_writes: 4` shape (a non-default setting in its fixed condition → V6 unmet there: `reproduced-OOM · diagnostic` for that shape). Name both mechanisms as separate next designs |
| any P arm OOMs with U_pin ≤ 16 and uncounted ≤ 32 and K ≤ 1.1 × C | **retry**: a further holder (counted bytes elsewhere); record the dump's top holders as a new lead |
| U-C OOMs in ≥ 1 run (gate held) | V2 fails as a survival control: if its dump has U_pin > C_contract the release defect also fires without hot-partition contention (record; strong lead, **retry** with a control re-chosen) — otherwise as R16 row 4 |
| U-T survives in any run (validity held) | **retry** (the R16 readings did not reproduce; record D, M, f) |
| P1–P6 as row 1 but P-T's acked bytes below P2's floor | **retry** (the intervention may have reduced load rather than removed the holder) |
| validity fails | invalid lifetime; one rerun; else **retry** |

Mixed outcomes in an arm (e.g. P-T 2/3 survive) → run 2 more lifetimes of that arm in the optional slot (protocol: expand repetitions)
and report n/N; row 1 then needs P-T to survive in every run.

**Pre-declared V6 note for the I shape:** `concurrent_writes: 4` is a lowered shipped setting used in R16 as the intervention; here it is a
second shape of the same claim. A result that holds only in that shape is not a default-constraint result (row 3). Owner may rule otherwise.

**Stopping budget (finite):** per lifetime CQL within 300 s (else invalid); W = 240 s; after a client stall (60 s with no success) wait ≤ 120 s
for an OOM, then classify from `gc.log`, one histogram if `jcmd` answers within 60 s, kill the JVM by PID. One rerun per invalid lifetime.
No escalation after an OOM beyond the planned optional runs. **No lifetime starts after 06:45 America/New_York on 2026-11-21; every
process (node, client, sampler, queue) stopped by 07:05; case file written by 07:30.**

### 2.8 Controls and intervention

- **Matched control (V2), U-C, 3 runs:** same build, heap, client (4 IPs × 9 threads, gated, one write in flight per thread), R = 160;
  `perthread` partitions. Every SEP worker keeps writing, so its stale reference moves to the current memtable within one memtable life and
  D stays small (R16 C: survive, retention 0.84–1.07 × C at idle). Margin: old-gen after GC ≤ 0.80 × heap.
- **Causal intervention (V4), P-T, 3 runs:** the patched build (two lines, trunk's) with T's workload. It removes only the stale
  reference; it does not change the pool, the overshoot, concurrency or the client. Throughput is recorded (P2's acked-bytes floor) so a
  slowed write path is not taken for protection. Also **P-I × 3** and **P-C × 3** (the patch in each shape; the healthy-release control of the
  bypass-playbook row).
- **Release-defect shape (bypass-playbook):** the idle-retention lifetimes (fill → flush → idle, 3 cycles + 300 s; U vs P).
- **Multiplicity dial:** U-Q × 2, P-Q × 1 (4 partitions per memtable) beside T (1) and C (36).
- **Not used (and why):** `unslabbed_heap_buffers` or `offheap_*` allocation types (change the holder and the counter at once); Byteman
  (would make the result diagnostic and alter timing; the patch is a separate build as protocol step 7 asks); raised timeouts; R16's
  D8/D16 (done; same holder).

### 2.9 Time plan (America/New_York, 2026-11-21; stage 2 starts ≈ 03:00; last start 06:45; all stopped 07:05; written 07:30)

Lifetime cost from R16 (pc75, `plan-h2.out`): U-T ≈ 100 s (OOM at 7 s + dump); surviving lifetime (240 s + end histograms + live dump)
≈ 340 s; U-I ≈ 160–210 s. A round {U-T, P-T, U-I, P-I, U-C, P-C} ≈ 100 + 340 + 190 + 340 + 340 + 340 ≈ 1,650 s ≈ **28 min**.
`hprof_reach.py` runs in the queue beside the next lifetimes (timed in Step A; R16 ran it offline).

| Window | Work | Est. |
|---|---|---|
| 03:00–03:45 | Step A: trees, patch + javac + `javap`/sha checks, harness copy and changes, `HotGen` `quad`, scanner and reach known-answer checks, shakedowns on U and P, gate self-test | 45 min |
| 03:45–05:15 | **18 core lifetimes**, rounds interleaved by build: round n = U2-T-n, P2-T-n, U2-I-n, P2-I-n, U2-C-n, P2-C-n, n = 1..3 | 84 min + 6 min slack |
| 05:15–05:50 | idle retention: `U2-Idle-1`, `P2-Idle-1` (≈ 16 min each) | 32 min |
| 05:50–06:10 | dial: `U2-Q-1`, `U2-Q-2`, `P2-Q-1` | ≤ 20 min |
| 06:10–06:45 | optional, in order: reruns of invalid lifetimes; extra repetitions of a mixed arm (2 each); `P16-T-1` (P build, 15,872 MiB, R = 1,792, the largest budget; survive → no dump, histograms only; OOM → dump scanned with `hprof_scan.py` only) | ≤ 35 min |
| 06:45–07:05 | last lifetime ends; reach queue finishes (or the remaining dumps are copied to pc96 `/mydata/r21-diag/` and analysed there until 07:15); stop everything; check no process left | 20 min |
| 07:05–07:30 | `analyze.py`, §3–§4, write-backs (retry row, `_INDEX.md`, candidate/clue pattern if earned), excerpts to `logs/` | 25 min |

**Drop order if late** (keep the window ends; drop from the bottom): (1) the 18 core lifetimes (never dropped; if < 84 min remain, run
rounds in order and stop at a round boundary — rounds 1–3 of U-T, P-T, U-C first, then the I shape); (2) `P2-Idle-1` then `U2-Idle-1`;
(3) the dial; (4) the optional runs.

**Resource fit:** 2 GiB heap (+ ≈ 1 GiB non-heap) per node, 3 GiB client, the analysis queue (≤ 4 GiB, 4 cores) against 125 GiB / 40 cores;
disk per lifetime: commit log ≤ 8 GiB, sstables ≲ 15 GiB (perthread 240 s), one 2 GiB dump until analysed; all under `run/` or `dumps/` and
removed; kept logs < 2 GiB; 714 GiB free.

**Cleanup and leftovers.** Stop every JVM and queue process this case started (by PID); `rm -rf /mydata/s4/r21/run`; delete each `.hprof`
after its analysis; keep `/mydata/s4/r21/{cassandra-u,cassandra-p,harness,cls,logs}` and say so in §3. Commit small excerpts (client
heads/tails, flush lines, scan/reach JSONs, histogram heads, first-error lines, `analyze.py` output, the patch diff and `javap` lines) to
`logs/` and `harness/` in this folder.

`sha256 of §1–§2 at freeze: 4efd3a2d45d54109d00f2ada8452b2f7c168a75d2a6539990850a92133016688` (computed as `awk '/^## 1\. Candidate/{f=1} /^.sha256 of §1–§2 at freeze/{f=0} f' <this file> | sha256sum`, i.e. from the `## 1. Candidate` line up to, not including, this line; 2026-11-21) · amendments after the freeze: none.

## 3. Runs (stage 2)

### 3.1 Environment, builds and Step A (2026-11-21, pc75; times America/New_York)

- **Node:** pc75 = `node3.jason92-326665` (UMass), x86_64, 40 cores, 125 GiB (123 GiB free at start), Ubuntu 22.04, kernel
  `5.15.0-203-generic`, cgroup v2, swap 8 GiB present (0 for the node: scope `MemorySwapMax=0`), OpenJDK 11.0.33
  (`11.0.33+9-post-1ubuntu1-22.04.1`), G1 with the shipped `jvm11-server.options`. Checked 02:01: no Java process, no
  `CassandraDaemon`, ports 7000/9042/7199 free, `/mydata` 714 GiB free, `/mydata/s4/` held only `cassandra-base`
  (jar sha256 `570b5249…0176e`). Co-tenancy re-checked by `run.py` before every lifetime (`summary.json` `cotenancy`): no other daemon.
- **Builds (Step A 1):** `cassandra-u` = `cp -a cassandra-base`, jar sha256 `570b5249d9b9a43f6809eb3da562737492192026f974b2edbd20e94bea90176e`
  (= B18/R16). `cassandra-p` = the same copy with the two-line patch ([`harness/updater-reset.diff`](harness/updater-reset.diff)),
  compiled with the frozen `javac -source 11 -target 11 …` command (2.3 s; 17 class files `BTree.class`, `BTree$*.class`, the same 17
  names the jar holds) and `jar uf` of exactly those 17; P jar sha256 `5817c26b8fbb4af726a56816f746699f9007f083c7230f42ee47c5120ee2d609`;
  member list of P = U (`cmp` equal); class major version 55 (`ca fe ba be 00 00 00 37`) in both; `javap` of `BTree$Updater.reset()`:
  U ends `invokevirtual SimpleTreeKeysIterator.reset; return`, P adds `aconst_null; putfield comparator` and `aconst_null; putfield updateF`
  ([`logs/stepA-patch-check.txt`](logs/stepA-patch-check.txt)). The node runs from `build/apache-cassandra-*.jar`
  (`bin/cassandra.in.sh`; `build/classes` is not on the class path). Every lifetime re-checks the jar sha256 and the `javap` putfields
  (`summary.json` `build`; a mismatch stops the lifetime): all lifetimes ran the planned build. `/mydata/s4/cassandra-base` untouched.
  The fallback (`ant jar`) was not needed.
- **Resolved values (every lifetime, `system_views.settings` read-back = the design's list):** `heap_buffers`, `memtable_heap_space`
  512MiB, `memtable_offheap_space` 512MiB, cleanup threshold 0.33333334, 2 flush writers, `concurrent_writes` 32 (4 in I),
  `concurrent_counter_writes` 32, in-flight 214,748,364 B / 53,687,091 B per IP, max message 16 MiB, `write_request_timeout` 2000ms,
  `max_mutation_size` 16384KiB, commit-log segment 32MiB, total 8192MiB, `native_transport_throw_on_overload` false, hints on, key
  cache 100MiB, `native_transport_timeout` 12s. JVM: `-Xms2G -Xmx2G`, `-XX:MaxDirectMemorySize=15872M` (resolved by `cassandra-env.sh`
  on pc75), `G1HeapRegionSize=16m`, `G1NewSizePercent=50`, `MaxGCPauseMillis=300`, `HeapDumpOnOutOfMemoryError`,
  `OnOutOfMemoryError=kill -9 %p`. Node scope `memory.max` = `max`, `memory.swap.max` = 0 (no container limit, as designed).
- **Harness** ([`harness/`](harness/), copied from R16's, `r16` → `r21`): `run.py` (build argument, arms T/I/C/Q, scope without
  `MemoryMax`, dumps queued, mode `idle`, queue back-pressure), `HotGen.java` (+ `quad`), `hprof_scan.py` (every allocator with its id),
  `hprof_reach.py` (+ allocator ids reachable only via the `updateF` cut, SEP workers, `BTree$Updater` counts), `reachq.sh` (new; up to 3
  dumps at once under `nice -n 19 taskset -c 36-39`, each dump deleted after its JSONs), `analyze.py` (+ U_pin, U, K, uncounted, D, M_D,
  f, acked MiB, old/humongous regions after GC), `plan.sh`/`after.sh` (cut-off 06:45, `plan.halt`), `reach-check.sh` +
  `reachcheck/BTree.java` (new), `table.py` (row formatter). `excerpts.sh` also copies the reach/refs JSONs. Unchanged except paths: `Jmx.java`, `client.py`,
  `logback-client.xml`, `HoldRegions.java`, `instrument-check.sh`, `hprof_refs.py`. Plans: `plan-stepA.txt`, `plan-core.txt`,
  `plan-idle.txt`, `plan-dial.txt`, `plan-opt.txt` (outputs `logs/plan-*.out`, queue log `logs/reachq.out`).
- **Step A checks (not readings), 02:03–02:10:** (3) scanner known-answer check **ok** (40 regions, 40 near-regions, 1,000 markers, all
  probe fields exact); (4) reach known-answer check **ok** — reachable regions **22**, only via `updateF` **10**, 1 updater with
  `updateF`, 0.21 s. The first attempt read 22 / **0**: the test program built the arrays in `main()`, whose live local variable is a
  frame GC root, so nothing was reachable *only* through `updateF`; the test was changed to build them in a separate method (a fix of
  the test program, not of the tool or the design); (5) source-binding shakedowns (20 s, perthread R = 64) on **U** and on **P**: 4
  client IPs (127.0.0.11–14), 3,602 / 3,609 requests acknowledged, no `ERROR` in `system.log`, settings read-back ok; (6) gate self-test
  on U: 457 gate waits, **351 ended by the first poll**, 0 retired (≥ 20 required); (7) `hprof_reach.py` timing on the shakedown end
  dumps: 7.0 s (U, 458 MB dump: 305 regions only via `updateF` after 20 s of perthread load) and 7.5 s (P, 319 MB dump: 65
  `BTree$Updater`, **0** with `updateF`, 0 regions only via `updateF`). In the readings `reachq.sh` took 2–5 s (scan), 6–14 s (reach) and
  16–25 s (refs) per 2 GiB dump.

### 3.2 Schedule and deviations

- All work ran on pc75 only; times America/New_York (pc75's clock is America/Denver, its Cassandra logs are UTC). Step A 02:01–02:10;
  **core 18 lifetimes 02:10–03:35** (rounds interleaved by build, exactly the frozen order: U2-T-n, P2-T-n, U2-I-n, P2-I-n, U2-C-n, P2-C-n);
  idle 03:35–03:58; dial 03:58–04:10; optional `P16-T-1` 04:10–04:16; analysis queue stopped 04:16. The session started ≈ 1 h before
  the design's window, so every window ran early; no lifetime came near the 06:45 cut-off, nothing was dropped.
- **No amendment.** Every lifetime ran as frozen; no lifetime was invalid (all first-trigger checks ok, every read-back equal, every
  jar sha256/`javap` check equal to the planned build, `memory.events` `oom_kill` 0 everywhere, client `retired` 0 everywhere, no
  `ERROR` line in any `system.log` — the OOM appears only in `stdout.txt`), so no rerun was needed.
- Notes (not deviations): (a) `analyze.py`'s `K_recl` (allocated + reclaiming) double-counts — `SubPool.allocated` is "total bytes
  allocated and reclaiming" (`MemtablePool.java:110`) — so **K = `pool.allocated`** is used throughout, as P1 defines it;
  (b) the gc.log "old + humongous regions after GC" reading reached 2,048 MiB in **every** arm (U and P, controls included) because
  G1 had `To-space exhausted` evacuation failures in all of them (e.g. P2-T-1 224, P2-C-1 59, U2-C-1 67), which keep regions as old;
  the heap after **full** GCs is used for the old-gen margin (column "after full GC"); (c) the sampler's `K` bean
  (`AllMemtablesOnHeapDataSize`) covers live memtables only, so the per-flush `Writing` lines and the dump's `pool.allocated` are the K
  readings.

### 3.3 Core lifetimes (2 GiB, S = 1.25 MiB, R = 160, W = 240 s)

Columns: outcome (s after workload start); acked MiB = rows acknowledged × 8 KiB (pre-OOM for an OOM); gate waits / retired threads;
largest `Writing Memtable-t` on-heap as % of C and the number of `High update contention` lines; per dump: U = reachable 1 MiB regions
(× C), **U_pin** = regions reachable only via `BTree$Updater.updateF` (× C), **K** = decoded `pool.allocated` MiB (× C), uncounted = U −
Σ `regionCount` of non-DISCARDED allocators, D / M_D / f, pooled updaters with non-null `updateF` / `SEPWorker` instances; heap after
full GC max / after any GC max (gc.log); end histogram total (surviving lifetimes, client stopped 10 s). C = 512 MiB, C_contract ≈ 626 MiB.
Full table with every column: [`logs/table.md`](logs/table.md); per-lifetime JSON: [`logs/analyze.jsonl`](logs/analyze.jsonl).

| Lifetime | Outcome | acked MiB | gate / ret. | Writing % / cont. | dump | U (×C) | **U_pin (×C)** | **K MiB (×C)** | uncounted | D / M_D / f | stale upd. / SEP | after full GC / any GC MiB | end hist MiB |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| **U2-T-1** | **OOM 8 s** | 171.2 | 0 / 0 | 125 / 3 | oom | 1,821 (3.56) | **1,600 (3.13)** | **244.6 (0.48)** | 1,569 | 3 / 1,891 / 0.85 | 60 / 66 | 1,932 / 1,968 | – |
| **U2-T-2** | **OOM 8 s** | 198.8 | 0 / 0 | 140 / 2 | oom | 1,829 (3.57) | **1,449 (2.83)** | **443.0 (0.87)** | 1,377 | 3 / 1,693 / 0.86 | 63 / 67 | 1,932 / 1,968 | – |
| **U2-T-3** | **OOM 7 s** | 171.2 | 0 / 0 | 139 / 3 | oom | 1,808 (3.53) | **1,655 (3.23)** | **173.4 (0.34)** | 1,627 | 3 / 1,883 / 0.88 | 62 / 67 | 1,931 / 1,951 | – |
| P2-T-1 | survived 244 s | 7,456.2 | 1,285 / 0 | 148 / 149 | end | 6 (0.01) | 0 | 0.1 | 0 | 0 | 0 / 71 | 796 / 1,985 | 84 |
| P2-T-2 | survived 243 s | 7,161.2 | 1,380 / 0 | 148 / 146 | end | 6 (0.01) | 0 | 0.1 | 0 | 0 | 0 / 76 | 782 / 1,961 | 81 |
| P2-T-3 | survived 244 s | 7,883.8 | 1,493 / 0 | 157 / 161 | end | 6 (0.01) | 0 | 0.1 | 0 | 0 | 0 / 73 | 792 / 1,977 | 80 |
| U2-I-1 | OOM 57 s | 2,383.8 | 387 / 0 | 46 / 0 | oom | 1,791 (3.50) | 1,448 (2.83) | 356.4 (0.70) | 1,432 | 8 / 1,497 / 0.97 | 24 / 49 | 1,949 / 1,968 | – |
| U2-I-2 | OOM 79 s | 3,265.0 | 538 / 0 | 35 / 0 | oom | 1,793 (3.50) | 1,358 (2.65) | 444.8 (0.87) | 1,347 | 8 / 1,393 / 0.97 | 26 / 49 | 1,954 / 1,968 | – |
| U2-I-3 | OOM 77 s | 3,532.5 | 539 / 0 | 38 / 0 | oom | 1,789 (3.49) | 1,365 (2.67) | 432.5 (0.84) | 1,357 | 8 / 1,394 / 0.98 | 27 / 49 | 1,949 / 1,959 | – |
| P2-I-1 | survived 249 s | 8,870.0 | 1,648 / 0 | 41 / 0 | end | 10 (0.02) | 0 | 4.0 | 0 | 0 | 0 / 47 | 635 / 1,999 | 78 |
| P2-I-2 | survived 244 s | 8,617.5 | 1,550 / 0 | 52 / 0 | end | 150 (0.29) | 0 | 151.2 | −5 | 0 | 0 / 50 | 634 / 1,975 | 221 |
| P2-I-3 | survived 248 s | 10,231.2 | 1,733 / 0 | 52 / 0 | end | 57 (0.11) | 0 | 52.7 | −1 | 0 | 0 / 50 | 642 / 1,973 | 130 |
| U2-C-1 | survived 251 s | 10,255.0 | 1,283 / 0 | 39 / 0 | end | 609 (1.19) | 559 (1.09) | 41.4 (0.08) | 562 | 6 / 1,075 / 0.52 | 68 / 71 | 976 / 1,957 | 689 |
| U2-C-2 | survived 248 s | 10,018.8 | 1,173 / 0 | 51 / 0 | end | 476 (0.93) | 458 (0.89) | 0.1 | 470 | 6 / 1,065 / 0.43 | 68 / 72 | 1,013 / 1,968 | 550 |
| U2-C-3 | survived 247 s | 10,497.5 | 1,423 / 0 | 48 / 0 | end | 384 (0.75) | 376 (0.73) | 1.3 | 376 | 4 / 709 / 0.53 | 68 / 72 | 1,003 / 1,968 | 464 |
| P2-C-1 | survived 248 s | 10,103.8 | 1,292 / 0 | 41 / 0 | end | 6 (0.01) | 0 | 0.1 | 0 | 0 | 0 / 73 | 659 / 1,952 | 75 |
| P2-C-2 | survived 244 s | 9,913.8 | 1,108 / 0 | 52 / 0 | end | 21 (0.04) | 0 | 5.2 | 9 | 0 | 0 / 75 | 652 / 1,990 | 94 |
| P2-C-3 | survived 244 s | 11,641.2 | 1,512 / 0 | 47 / 0 | end | 8 (0.02) | 0 | 0.1 | 2 | 0 | 0 / 71 | 670 / 1,958 | 81 |

- **Initiating failure (V5)**, every OOM lifetime: `stdout.txt` `java.lang.OutOfMemoryError: Java heap space` → `Dumping heap to …` →
  `Heap dump file created [2,074,561,593 bytes in 3.491 secs]` (U2-T-1) → `# -XX:OnOutOfMemoryError="kill -9 %p"`; scope
  `memory.events` `oom 0`, `oom_kill 0` (a JVM heap OOM, no external kill); RSS loop shows the process gone after the dump. Excerpts:
  `logs/<label>/oom-lines.txt`. The OOM dump holds 23–31 writer stacks (T) / 4 (I) in `Keyspace.applyInternal`/`Mutation.apply`.
- **Holder chain** (`hprof_refs.py discarded`, depth 4, first OOM dump of each build+arm: U2-T-1, U2-I-1, U2-Q-1;
  `logs/U2-T-1/refs-disc-oom.json`): each DISCARDED `SlabAllocator` (U2-T-1: three, regionCount 624/643/624) ←
  `AtomicBTreePartition$Updater.allocator` / `.cloner` / `this$0` (26 instances) ← **`BTree$Updater.updateF`** (26) ←
  `TinyThreadLocalPool$TinyPool.val1` ← `Object[]` (the `FastThreadLocal` slot array of the thread). In every U dump the
  only-via-`updateF` allocators are **all DISCARDED** (`only_via_updateF_allocators_by_state`), i.e. memtables already flushed, whose
  charge the pool has released. Shallow heap reachable: 1,915–1,927 MiB with the edge, 254–471 MiB without it (T).
- **K (counted) at the endpoint:** `pool.allocated` 173–443 MiB in the U-T dumps (one DISCARDING memtable of 173–443 MiB plus ≈ 0 live),
  ≤ C_contract in every dump → outcome row 1, not row 2. The B18 overshoot is still present during the runs: `Writing Memtable-t` lines
  reach 559–718 MiB (109–140 % of C) in U-T and 148–157 % in P-T, with `High update contention in 1/1 partitions` (2–3 lines in U-T,
  146–161 in P-T); it does not by itself exhaust 2 GiB (P-T survives 3/3 with old gen after full GC ≤ 796 MiB).
- **Throughput (V4 accounting):** P-T acked 7,161–7,884 MiB in 240 s vs the U-T pre-OOM median 171.2 MiB (≥ 41.8 ×, floor 5 × =
  856 MiB); P-I 8,618–10,231 MiB vs U-I median 3,265 MiB (≥ 2.6 ×, floor 1.5 × = 4,898 MiB); P-C 9,914 / 10,104 / 11,641 MiB vs U-C
  median 10,255 MiB (−3.3 %, −1.5 %, +13.5 %, within ± 15 %). The gate engaged in every surviving lifetime (1,108–1,733 waits, 0 retired),
  so D2 + D3 stayed ≤ 36 × S as designed.

### 3.4 Idle retention (`U2-Idle-1`, `P2-Idle-1`; 2 GiB, all defaults, perthread R = 160)

3 × {60 s load → stop client → `nodetool flush` → 30 s idle → 2 histograms → live dump}, then 300 s idle → histograms + dump. L0 (s0)
65 MiB in both. Acked per cycle U: 3,750 / 2,550 / 2,634 MiB; P: 3,770 / 2,875 / 3,640 MiB.

| Build | reading | K MiB | live regions | **U_pin** (×C) | uncounted | D / M_D / f | histogram total MiB |
|---|---|---|---|---|---|---|---|
| U | c1 | 0.0 | 392 | **390 (0.76)** | 390 | 3 / 537 / 0.73 | 471 |
| U | c2 | 0.0 | 427 | **422 (0.82)** | 424 | 4 / 716 / 0.59 | 504 |
| U | c3 | 0.0 | 618 | **610 (1.19)** | 618 | 8 / 1,251 / 0.49 | 694 |
| U | +300 s idle | 0.5 | 617 | **609 (1.19)** | 612 | 7 / 1,250 / 0.49 | 693 |
| P | c1 / c2 / c3 / +300 s | 0.0 / 0.0 / 0.0 / 0.5 | 8 / 3 / 11 / 11 | **0 / 0 / 0 / 0** | 8 / 0 / 9 / 6 | 0 | 79 / 69 / 81 / 78 |

After every `ks.t` memtable is flushed and DISCARDED and the node is idle, the U build keeps 390–610 MiB of regions with no pool charge
(K ≤ 0.5 MiB); 300 s of idling releases nothing (609 vs 610); the P build keeps ≤ 11 regions. Residual is bounded by D·M·f (it rose
with D from 3 to 8, not monotonically per cycle).

### 3.5 Multiplicity dial (Q: pk = thread mod 4, 4 partitions per memtable, cw 32, all defaults)

| Lifetime | Outcome | acked MiB | Writing % / cont. | U (×C) | U_pin (×C) | K MiB (×C) | uncounted | D / M_D / f | stale upd. / SEP |
|---|---|---|---|---|---|---|---|---|---|
| U2-Q-1 | **OOM 125 s** | 5,656.2 | 70 / 0 | 1,813 (3.54) | 1,585 (3.10) | 225.4 (0.44) | 1,582 | 7 / 1,763 / 0.90 | 72 / 72 |
| U2-Q-2 | **OOM 48 s** | 2,385.0 | 62 / 0 | 1,815 (3.54) | 1,310 (2.56) | 506.1 (0.99) | 1,305 | 7 / 1,641 / 0.80 | 68 / 68 |
| P2-Q-1 | survived 255 s | 10,907.5 | 76 / 0 | 6 (0.01) | 0 | 0.1 | 0 | 0 | 0 / 72 |

f by shape: T 0.85–0.88 (1 partition), Q 0.80–0.90 (4), C 0.43–0.53 (36, end dumps), I 0.97–0.98; D: T 3, Q 7, I 8, C 4–6;
U_pin = D × M_D × f by construction. Q has no contention line and no overshoot (Writing ≤ 70 %), yet OOMs 2/2 on U at defaults.

### 3.6 Optional run and budget

- **`P16-T-1`** (P build, T shape, 15,872 MiB heap, pool 3,968 MiB, R = 1,792, S = 14 MiB; no dump by design): **survived 240 s**, acked
  1,400 MiB, 862 gate waits, 0 retired; `Writing` lines up to **7,861 MiB (198 % of C)** with 25 contention lines (the B18 overshoot at
  large S); heap after any GC up to 15,680 MiB, after full GC ≤ 6,831 MiB, 26 full GCs. **End histograms (client stopped 10 s, ≈ 14 s
  after the last large flush completed, current memtable 14.5 MiB): 6,832 MiB live, `[B` 7.07 GB**, on the patched build. The design
  takes no dump at this heap, so the holder of these ≈ 6.8 GB is unidentified (see §4 "new lead").
- **Budget (V7) and the largest failing budget:** 2 GiB heap (the ideal), `MaxDirectMemorySize` 15,872M as resolved, no container
  limit. The largest failing budget is R16's 15,872 MiB result (U-T OOM 3/3, `H16-T-1..3`, uncounted ≥ 2.31–2.56 × C), reused with
  documented equivalence: the same U jar sha256 `570b5249…`, the same settings read-back, the same gated `HotGen` (only `quad` added, not
  used by T), the same lifetime steps; R21 did not re-run U at 15,872 MiB.

### 3.7 Predictions against readings

| Prediction | Result |
|---|---|
| P1 U-T | **met** except one sub-item: OOM 3/3 at 7–8 s; U 3.53–3.57 × C (≥ 2.5); U_pin 2.83–3.23 × C (≥ 1.5); K 0.34–0.87 × C (≤ 1.1); D 3 (≥ 2); f 0.85–0.88 (≥ 0.8); contention lines present. Writing 109–140 % (predicted 98–130 %; one flush at 140 %) |
| P2 P-T | survived 3/3; end U_pin 0 (≤ 16), uncounted 0 (≤ 32); Writing ≥ 95 % in every run (148–157 %); acked 7,161–7,884 MiB (≥ 856); retired 0. Old gen: after full GC ≤ 796 MiB (≤ 1,638) **met**; after young/mixed GCs the heap reached 1,961–1,985 MiB (evacuation failures; the same in the U-C and P-C controls) — **not met in the strict "after every GC" reading** |
| P3 U-I | met: OOM 3/3 at 57–79 s; no contention line; Writing 35–46 %; MutationStage pending ≤ 32; U_pin 2.65–2.83 × C; K 0.70–0.87 × C; D 8 |
| P4 P-I | met (survived 3/3; U_pin 0; uncounted −5…0; acked ≥ 2.6 × U-I median); old-gen as in P2 (full GC ≤ 642 MiB) |
| P5 U-C | survived 3/3; U_pin 0.73–1.09 × C (0.4–1.2); uncounted 376–562 (≥ 205); K at end 0.1 / 1.3 MiB, **41.4 MiB in U2-C-1** (> 16 MiB predicted: a non-empty current memtable) |
| P6 P-C | met: survived 3/3; U_pin 0; uncounted 0 / 9 / 2; acked within ± 15 % of U-C median |
| P7 idle | met: U K ≤ 0.5 MiB, U_pin 390–610 (≥ 128), D 3–8, U_pin after 300 s = 99.8 % of cycle 3; P U_pin 0, live regions ≤ 11 |
| P8 dial | f T 0.85–0.88 (≥ 0.8), Q 0.80–0.90 (≥ 0.5), C 0.43–0.53 (0.3–1.0); D largest in I (8) and Q (7) rather than T (3); Q on U OOM 2/2; P-Q survived |
| Validity | held in every lifetime (none invalid, no rerun) |

### 3.8 What is left on pc75

- `/mydata/s4/r21/` ≈ 1.2 GB: `cassandra-u/` (419 MB), `cassandra-p/` (419 MB, the patched jar), `logs/` (328 MB, full logs of every
  lifetime and Step A), `excerpts/` (3 MB, copied here), `harness/`, `cls/`, `pcls/`, the jar member lists and `BTree.java.orig`.
  `run/` and `dumps/` are removed; **no heap dump is kept** (all 29 reading dumps were deleted by `reachq.sh` after their JSONs; the 2 shakedown timing dumps right after timing).
  `/mydata/s4/cassandra-base` unchanged. No process of this case runs (checked 04:16: no `CassandraDaemon`, `HotGen`, `Jmx`,
  `reachq.sh`, `plan.sh`/`after.sh`). Nothing was copied to pc96 (`/mydata/r21-diag` never created).

## 4. Conclusion (stage 2)

**Verdict: true positive.** Protocol status `verified-OOM · deployment`; direction **bypass — release defect** (U > C, K ≤ C in D1);
interpretation **suspected implementation defect** (fixed on trunk only, incidentally, by CASSANDRA-20780's commit `54e39a90b0`; not in
any released 4.1/5.0 version, §1.4). Outcome row **1** of §2.7.

**Reason.** The fixed condition — unmodified 5.0.9, 2 GiB heap, every shipped default, the gated hot-partition writer (T) — reached a
Java heap OOM in **3/3** lifetimes at 7–8 s, after only 171–199 MiB of acknowledged writes. Its matched control (the same build, heap and
client with one partition per thread) **survived 3/3** for 240 s at ≈ 10 GiB acknowledged each. In every U-T OOM dump **1,449–1,655
slab regions (2.83–3.23 × C = 512 MiB, all > C_contract 626 MiB) were reachable only through `BTree$Updater.updateF`**, pinning 3
DISCARDED memtable allocators (f = 0.85–0.88), while the pool counter `pool.allocated` read **173–443 MiB (0.34–0.87 × C)** — the
memory had been released from `memtable_heap_space` at discard while still reachable (U > C, K ≤ C). The intervention — a separate
build whose `Updater.reset()` nulls only `updateF` and `comparator` (trunk's two lines; jar sha256 `5817c26b…`, diff saved) — removed
the endpoint in **3/3** P-T lifetimes, which acknowledged 7,161–7,884 MiB each (≥ 41 × the U-T pre-OOM median; floor 5 ×), with 0
pinned regions and ≤ 6 live regions after the run, while the B18 overshoot was still there (Writing 148–157 % of C). The same holder
explains the other shapes: `concurrent_writes: 4` U-I 3/3 OOM (U_pin 2.65–2.83 × C, D 8) vs P-I 3/3 survive; **4 hot partitions at
all defaults** U-Q 2/2 OOM (U_pin 2.56–3.10 × C, no contention, no overshoot) vs P-Q survives; at idle after flushing every memtable the
U build holds 390–610 MiB (0.76–1.19 × C) with K ≤ 0.5 MiB and releases nothing in 300 s, the P build ≤ 11 regions. V1–V7 hold:

| | Evidence (run) |
|---|---|
| V1 Repetition | U2-T-1..3: OOM 3/3 (7, 8, 8 s), clean starts (`run/` recreated) |
| V2 Matched control | U2-C-1..3: survive 3/3, same build/heap/client/gate, old gen after full GC ≤ 1,013 MiB (≤ 0.8 × heap) |
| V3 Measurement | U = reachable regions and U_pin from the dump graph (`hprof_reach.py`, known-answer check 22/10 exact), K = decoded `SubPool.allocated` (`hprof_scan.py`, known-answer check exact) — independent readings; holder chain from `hprof_refs.py` |
| V4 Intervention | P2-T-1..3: survive 3/3 at 7.2–7.9 GiB acked (U-T pre-OOM 0.17–0.20 GiB); also P-I 3/3, P-C 3/3 (throughput −3 %…+14 % of U-C), P-Q 1/1 |
| V5 Initiating failure | `OutOfMemoryError: Java heap space` → heap dump → `kill -9 %p` in each U-T `stdout.txt`, `oom_kill 0`; the OOM dump shows the holder (U_pin 2.83–3.23 × C, chain `TinyPool.val1` → `BTree$Updater.updateF` → `AtomicBTreePartition$Updater` → DISCARDED `SlabAllocator`) |
| V6 Default constraints | T arm: every setting shipped (read back each lifetime); the only non-default arms are I (`concurrent_writes: 4`, supporting) and the P build (intervention) |
| V7 Acceptable budget | 2 GiB heap (ideal), `MaxDirectMemorySize` 15,872M as resolved, no container limit; largest failing budget 15,872 MiB (R16 `H16-T-1..3`, 3/3, reused with documented equivalence, §3.6) |

**Classification detail.** Not mixed: K stayed ≤ C_contract at every U-T endpoint, and the patch alone removes the OOM although the
counted overshoot (B18) remains. The overshoot enlarges each pin (M ≈ 560–720 MiB per memtable in T), which is why T OOMs with D = 3,
but Q and I (no overshoot, Writing ≤ 70 %) OOM through the same holder with D = 7–8. CP patterns: CP-3 (counter released before the
memory is freed) and CP-14 (per-thread pooled object kept after use) cover the shape; no new pattern.

**Limits of attribution.** (1) The 2 GiB P runs ran close to the heap after young/mixed collections in every arm, controls included
(evacuation failures; heap after full GC ≤ 796 MiB): P2's "old gen after every GC ≤ 0.8 × heap" is met only for full GCs. (2) The
largest failing budget is R16's U-T at 15,872 MiB, not re-run here. (3) **New lead (for the owner, not claimed by this design):** the
optional `P16-T-1` (patched build, 15,872 MiB, S = 14 MiB) survived, but its end histograms showed **6,832 MiB live (`[B` 7.07 GB) ≈ 14 s
after the last 7.4–7.6 GiB memtable flushes completed**, with the current memtable at 14.5 MiB; no dump was taken by design, so this
retention on the patched build is unattributed — a candidate further holder at large request sizes (to check with an end dump of a
patched T lifetime at 15,872 MiB). The B18 overshoot itself reached 198 % of C per flushing memtable there.

**Retry change:** none (true positive).
