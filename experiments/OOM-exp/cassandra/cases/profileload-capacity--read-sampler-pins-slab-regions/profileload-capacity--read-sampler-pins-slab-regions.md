# B25 — profileload sampler capacity: read samplers keep memtable slab-slice keys, so each retained sample pins a 1 MiB region after flush  <!-- file: cassandra/cases/profileload-capacity--read-sampler-pins-slab-regions/profileload-capacity--read-sampler-pins-slab-regions.md -->

| Field | Value |
|---|---|
| Case ID | `B25` (B = bypass case; README "ID prefixes"). Predicted class by the protocol's measurement table: **bypass, accounting omission** (U > C, K ≤ C: the sampler counts entries while each read-sampler entry holds a whole 1 MiB slab region, and the memtable pool has released those regions at discard). The OOM needs the per-table retention to stack over several tables, so stage 2 may label it **mixed** (bypass excess + table multiplicity); §2.1 |
| From | `OC-585` (primary, autonomous) + `OC-588` (guided) of the [phase 1 OOM candidate list](../../../../capacity-enforcement-exp/cassandra/stage5-oom-clue-find/phase1-oom-candidates.md) (both Status `picked: B25 (2026-11-24)`); owner-approved batch of 2026-11-24 |
| Phase-1 case file | [`profileload-capacity-beginsampling-capacity--autonomous`](../../../../capacity-enforcement-exp/cassandra/stage3-ai-deep-read/cases/profileload-capacity-beginsampling-capacity--autonomous.md) (shared by OC-585 … OC-588) |
| System / pinned source | Cassandra 5.0.9 (`systems/cassandra/source/`, `build.xml` `base.version` 5.0.9); on pc82 `/mydata/s4/cassandra-base`, `build/apache-cassandra-5.0.9-SNAPSHOT.jar` sha256 `570b5249d9b9a43f6809eb3da562737492192026f974b2edbd20e94bea90176e`; OpenJDK 11.0.33 |
| Stage 1 (design) | fresh OOM-agent stage-1 session, 2026-11-24 05:40–06:40 America/New_York; nothing run (read-only check of the five x86 nodes, read-only source reads in the repository and on GitHub raw, read-only JIRA REST searches) |
| Stage 2 (verify) | pending (a fresh session) |
| Verdict | `pending` |

## Summary

- **Conclusion:** pending (stage 2). Design: on one node at a 2 GiB heap with every capacity constraint at its default, an
  operator runs **`nodetool profileload b25 t<k>` with all default options** (10 s, `-s 256`, `-k 10`, all eight samplers) on one
  table after another while a client writes ≈ 1 MiB partitions into that table and reads each one back. Predicted: heap OOM 3/3
  within 4–10 sessions; the write-side-samplers control and a build whose `Sampler.addSample` copies the key both survive 16 sessions.
- **Root cause claimed (to be verified):** the read samplers (`READS`, `READ_ROW_COUNT`, `READ_SSTABLE_COUNT`,
  `READ_TOMBSTONE_COUNT`) store the partition-key `ByteBuffer` by reference. For a read served from a memtable under the default
  `heap_buffers` allocator, that buffer is a slice of a 1 MiB on-heap slab region, so each retained sample keeps its whole region
  alive. The sampler capacity counts entries (≈ 116 B each as measured by phase-1 stage 4 on the write path), not the 1 MiB behind
  them; the memtable pool stops counting the regions when the memtable is flushed; and `finishSampling` leaves ≥ 244 of 256 entries
  per sampler referenced until the next session on the same table, which may never come. Each profiled table therefore keeps
  ≈ 270–500 MiB alive and uncounted, and the amounts add up across tables.

## 1. Candidate

### 1.1 The candidate rows, quoted

From [`phase1-oom-candidates.md`](../../../../capacity-enforcement-exp/cassandra/stage5-oom-clue-find/phase1-oom-candidates.md)
(details: [`runs/p1-cassandra-2026-11-24.md#oc-585`](../../../../capacity-enforcement-exp/cassandra/stage5-oom-clue-find/runs/p1-cassandra-2026-11-24.md#oc-585), [`#oc-588`](../../../../capacity-enforcement-exp/cassandra/stage5-oom-clue-find/runs/p1-cassandra-2026-11-24.md#oc-588)):

> | OC-585 | 2026-11-24 | `profileload-capacity-beginsampling-capacity--autonomous` | autonomous | Read-sampler entries (READ_ROW_COUNT, READ_TOMBSTONE_COUNT, READ_SSTABLE_COUNT queues and the READS StreamSummary) keep the partition-key ByteBuffer of reads served from the memtable. With the default heap_buffers this is a slice of a 1 MiB on-heap slab region, so each retained sample keeps its whole 1 MiB region alive after the memtable is flushed. Capacity counts entries, not bytes, and after profileload returns the leftover entries stay until the next beginSampling: up to ~1000 regions (~1 GiB) per table at -s 256, ~4 GiB at -s 1024. The ceiling is the distinct regions of flushed memtables (memtable_heap_space = 1/4 heap each). None of it is counted against memtable_heap_space. | — | picked: B25 (2026-11-24) |

> | OC-588 | 2026-11-24 | `profileload-capacity-beginsampling-capacity--autonomous` | guided | read-path samplers (READS, READ_ROW_COUNT, READ_TOMBSTONE_COUNT, READ_SSTABLE_COUNT) keep the memtable's partition-key ByteBuffer, which under the default memtable_allocation_type heap_buffers is a slice of a 1 MiB on-heap slab region; each counted sample (~116 B) can pin a whole 1 MiB region after the memtable is flushed and outside memtable_heap_space, and the samples stay after finishSampling; at the nodetool default -s 256, up to ~256 MiB per hot table (1 GiB at -s 1024), times the hot tables in an all-tables profileload | CP-1, CP-3, CP-14, CP-7, CP-8 | picked: B25 (2026-11-24) |

The two rows describe one mechanism (same holder, same trigger); B25 tests it once and its verdict goes to both rows. OC-586
(JMX capacity unbounded) and OC-587 (`LOCAL_READ_TIME` CQL strings) share the phase-1 case file but are different mechanisms and are
**not** covered by B25. **Scope note:** OC-585's "~4 GiB at -s 1024" needs a non-default `-s`; B25 uses the default `-s 256` only
(rule "Default constraints only", 2026-11-23).

### 1.2 Phase-1 constraint and stage-4 result

- **Constraint:** the sampler capacity (nodetool `profileload`/`toppartitions` `-s`, default 256, `ProfileLoad.java:52-53`; client
  check `capacity <= 1024`, `:79`). Server side it is `maximumSize(max(1, capacity))` of the `MaxSampler` queue
  (`MaxSampler.java:45-47`) and `new StreamSummary<>(capacity)` of the `FrequencySampler` (`FrequencySampler.java:60`). Unit: entries.
- **Phase-1 estimate:** `positive` (the cap bounds entries per sampler per table).
- **Stage 4 (2026-11-24, ms0604):** confirmed: caps. Unit tier: every arm held exactly `min(max(1, cap), N)` entries (84–85 B per
  entry with short `String` items). Cluster tier: after 1,000,000 writes the live `Sampler$Sample` count was exactly 256 / 1024 / 100000
  at C = 256 / 1024 / 100000, and releasing the queue freed 116.5 MB at the 1,000,000-entry control, i.e. **116 B per entry**
  (`Sample` 32 + `HeapByteBuffer` 48 + key `byte[]` 32 + slot). Stage 4 used `WRITE_SIZE` only: its key comes from the decoded request,
  an exact copy (`CBUtil.readBoundValue` → `ByteBuffer.wrap(readRawBytes(…))`, `CBUtil.java:466-480`). **No stage-4 run sampled a
  read served from a memtable**; the per-entry size of the read samplers is what B25 measures.

### 1.3 Version check (2026-11-24, read only)

| Ref | `Sampler.addSample` copies the key? | `MaxSampler.finishSampling` clears the queue? |
|---|---|---|
| `cassandra-5.0.9` tag (= the pin; local history clone `cassandra-src`, and `systems/cassandra/source`) | no (`samplerExecutor.submit(() -> insert(item, value))`, `Sampler.java:109-113`) | no (polls `count + 2`, `MaxSampler.java:52-63`) |
| `cassandra-5.0` branch head (GitHub raw) | no (same lines 109-112) | no (same line 59) |
| `trunk` (GitHub raw) | no (same) | no (same) |

Latest 5.0 release tag is `cassandra-5.0.9`. The code that already avoids this for its own copy of a key is
`TopPartitionTracker` (`TopPartitionTracker.java:240`, `key.retainable()`; `DecoratedKey.retainable()` copies when
`ByteBufferUtil.canMinimize`, `DecoratedKey.java:198-207`; added by CASSANDRA-16310, 4.1).

### 1.4 JIRA prior art (2026-11-24 05:55 EST, REST `project = CASSANDRA`, requests ≥ 3 s apart; nothing posted)

| JQL (after `project = CASSANDRA AND`) | Hits | On point |
|---|---|---|
| `text ~ "MaxSampler"` | 3 | CASSANDRA-14436 (added the sampler, 4.0), 17821 (interval profileload, 5.0), 7926 (stress) — none about retention |
| `text ~ "FrequencySampler"` | 1 | 14436 |
| `text ~ "profileload" AND (text ~ "memory" OR text ~ "heap" OR text ~ "leak")` | 1 | 14436 |
| `text ~ "toppartitions" AND (text ~ "memory" OR text ~ "heap" OR text ~ "leak" OR text ~ "OOM")` | 3 | 14436, 18813, 8278 — none |
| `text ~ "toppartitions" AND text ~ "memtable"` | 2 | 14641 (IndexOutOfBounds), 8278 — none |
| `text ~ "sampler" AND text ~ "slab"` | 1 | 8897 (buffer pooling) — none |
| `summary ~ "sampler" AND (text ~ "leak" OR text ~ "retain" OR text ~ "memory")` | 1 | 14436 |
| `text ~ "StreamSummary"` | 7 | 7247, 7974 (added toppartitions, 2.1.3), 14436, 13704, 16227, 14096, 8278 — none |
| `text ~ "TopPartitionTracker"` | 5 | 16310 (introduced `retainable()` for its own tracker), 18697, 17733, 20918, 17258 — none about the samplers |
| `text ~ "topReadPartitionFrequency"` | 1 | 8612 (read metrics on all read types, open) — not memory |
| `text ~ "sampling" AND text ~ "HeapByteBuffer"` | 8 | 17298 (memtable heap accounting) — related, not this holder |
| `text ~ "slab" AND text ~ "slice" AND (text ~ "retain" OR text ~ "leak")` | 6 | none on point |

**Verdict: `new`** (no issue reports a sampler holding memtable slab slices; closest related CASSANDRA-16310, which copies keys for
the top-partition tracker only). Not known-fixed, so B25 is a normal case, not a positive control.

## 2. Design solution (stage 1; frozen)

### 2.1 Mechanism and direction

- **Where the sampled key comes from (read path).** A single-partition read queries memtables first
  (`SinglePartitionReadCommand.java:718-732`; timestamp-order path `:957-972`). The memtable iterator's key is
  `AbstractBTreePartition.this.partitionKey()` (`AbstractBTreePartition.java:197-199`) =
  `allocator.ensureOnHeap().applyToPartitionKey(key)` (`AtomicBTreePartition.java:201-205`). Under the shipped
  `memtable_allocation_type: heap_buffers` (`conf/cassandra.yaml:825`) the pool is `new SlabPool(heapLimit, 0, …)`
  (`AbstractAllocatorMemtable.java:100-102`) → `allocateOnHeap = true` (`SlabPool.java:28`) → `EnsureOnHeap.NoOp`
  (`SlabAllocator.java:67-70`): the key is returned as stored. It was stored by `cloner.clone(update.partitionKey())` at the
  partition's first write (`SkipListMemtable.java:115-116`; default memtable = `skiplist`, `cassandra.yaml:783-791`), which for sizes
  ≤ 128 KiB is `Region.allocate` = `data.duplicate().position(off).limit(off+size)` of a `ByteBuffer.allocate(1 MiB)`
  (`SlabAllocator.java:51-52`, `:91-112`, `:139`, `:197-205`). The merged/result partition takes the first (memtable) iterator's key
  (`UnfilteredRowIterators.java:411`; names path `SinglePartitionReadCommand.java:1068-1069`, `:1054`).
- **Who keeps it.** `READS` and `READ_SSTABLE_COUNT`: `addSample(key.getKey(), …)` at `SinglePartitionReadCommand.java:915-917`
  and `:1054-1056`. `READ_ROW_COUNT` / `READ_TOMBSTONE_COUNT`: `currentKey.getKey()` at `ReadCommand.java:545`, `:611-615`
  (installed for every local read, `:461`). `Sampler.addSample` hands the item unchanged to the single-thread `samplerExecutor`
  (queue limit 1000, `Sampler.java:100-113`); `MaxSampler.insert` stores `new Sample<T>(item, value, 0)` (`MaxSampler.java:66-70`),
  `FrequencySampler.insert` → `summary.offer(item, …)` (`FrequencySampler.java:81-87`). The `HeapByteBuffer` slice references the
  region's whole `byte[1048576]`.
- **What the controls count.** Sampler: entries (`queue.size() < capacity`, `MaxSampler.java:74`; `StreamSummary(capacity)`).
  Memtable pool (`memtable_heap_space`, heap/4): the region bytes **until the memtable is discarded after flush**, then nothing.
  No other control sees the pinned regions.
- **Retention in time.** `MaxSampler.finishSampling` polls `count + 2` entries and keeps the rest (`MaxSampler.java:52-63`);
  `FrequencySampler.finishSampling` reads `topK` and keeps `summary` (`:67-78`). They are replaced only by the next `beginSampling`
  of the same sampler on the same table (`MaxSampler.java:45`, `FrequencySampler.java:60`). Profiling table after table therefore
  accumulates one leftover set per table.
- **Per-session amount with the planned workload** (read-after-write, one 1.055 MiB partition per key, one writer per table, so
  every key sits in its own region; §2.5). Let n = reads of the profiled table inside its 10 s session, all with 1 live row:
  `READ_ROW_COUNT` keeps the **first 256** reads (ties never displace: `peekLast().count < value` is false), 244 left after
  `-k 10`; `READS` keeps the **last 256** distinct keys (space-saving replaces the minimum-count item; topK does not remove);
  `READ_SSTABLE_COUNT` gets value 0 for memtable-only partitions and admits nothing (`value > 0`); `READ_TOMBSTONE_COUNT` nothing (no
  tombstones). Pinned regions per session **P ≈ min(n, 512) − ≤ 12**; at the planned n ≈ 280, **P ≈ 268–280 MiB**.
  `WRITES`/`WRITE_SIZE` keep the decoded request's own key copy and `LOCAL_READ_TIME` keeps short CQL strings (≈ 116 B-class each).
- **Direction label: bypass — accounting omission** (U > C, K ≤ C): in the sampler domain K = entries ≤ 256 per sampler while U ≈
  entries × 1 MiB; in the memtable domain the pool's K excludes discarded memtables while their pinned regions stay live. The OOM
  needs the excess to stack over several profiled tables (multiplicity), so stage 2 may record **mixed** if the readings show a
  single table's excess is not enough (§2.4: one table ≈ 0.28 GiB). Interpretation: **suspected implementation defect** (the same
  code base copies keys for `TopPartitionTracker` with `retainable()` for this reason). Technique note:
  [`bypass-playbook.md`](../../../bypass-playbook.md) (accounting omission: measure U independently of K; protected vs suspect path),
  with the multiplicity step of [`combo-playbook.md`](../../../combo-playbook.md).

### 2.2 Protection map (2 GiB heap)

| Domain | Allocation, owner, release | Local contract (C) | Scope / multiplicity | Aggregate coverage | Lifetime |
|---|---|---|---|---|---|
| **D1 memtable regions** | `SlabAllocator` `byte[1048576]` regions of `b25.t*` memtables; charged at clone, released from the counter at discard after flush (`MemtableAllocator` `setDiscarded`) | `memtable_heap_space` = heap/4 = **512 MiB**; flush of the largest memtable at `memtable_cleanup_threshold` = 1/(1+2 flush writers) = 0.33 (`cassandra.yaml:801-812`, `:899-912`; `DatabaseDescriptor.java:753-755`; `MemtablePool.java:125-133`; `AbstractAllocatorMemtable.java:249`); soft overshoot (region tail ≤ 12.5 %, row overhead after the fact): **C_contract ≈ 600 MiB** | all tables share one pool | the pool | until discard — by contract |
| **D1-pin (claimed holder)** | the same regions after discard, reachable through `Sampler$Sample.value` in `MaxSampler.queue` and through the `StreamSummary` of `FrequencySampler.summary` (and transiently through `samplerExecutor` tasks) | **none in bytes**; the sampler contract is a count: 8 samplers × 256 entries per table, ≈ 116 B each (stage 4) → **≈ 0.24 MB per table** | per profiled table; leftovers persist across sessions on other tables | none | until the next `beginSampling` of that sampler on that table (unbounded) |
| D2 sampler entries themselves | `Sample` + `HeapByteBuffer` + counters | as D1-pin's count | per table | none | as D1-pin |
| D3 decoded requests in flight | v4/v5 frames → `Mutation` (1.06 MiB each) | `native_transport_max_request_data_in_flight` heap/10 = 204.8 MiB, per IP heap/40 = 51.2 MiB | 1 outstanding write per client thread (§2.5): ≤ 2 × 1.06 MiB | reserve | until response |
| D4 flush / compaction / commit log | flush writers (2), compaction (STCS), commit-log segments (mmap) | defaults | — | — | transient |
| D5 baseline | schema of ≤ 128 tables (≈ 0.34 MiB each, U14), key cache (≤ 100 MiB / 5 % heap), metrics, Netty | — | — | — | standing |
| Direct / native (recorded, not the budget) | Netty, `BufferPool`, commit-log mmap | `MaxDirectMemorySize` as `cassandra-env.sh` resolves on pc82 | — | — | RssAnon |

### 2.3 Configuration and budget audit

- **Build U (unmodified, all test and control arms):** `cp -a /mydata/s4/cassandra-base /mydata/s4/b25/cassandra-u`; jar sha256 must
  equal `570b5249…0176e` (checked on pc82 by stage 1, 2026-11-24); a different hash is recorded and said in §3.
- **Build P (diagnostic, the intervention):** `cp -a /mydata/s4/cassandra-base /mydata/s4/b25/cassandra-p`; patch
  `src/java/org/apache/cassandra/metrics/Sampler.java` `addSample` to copy a `ByteBuffer` item to a minimal buffer before queuing
  (the `retainable()` idea of `TopPartitionTracker`; nothing else changes):

  ```diff
       public void addSample(final T item, final int value)
       {
           if (isEnabled())
  -            samplerExecutor.submit(() -> insert(item, value));
  +        {
  +            @SuppressWarnings("unchecked")
  +            final T retained = item instanceof java.nio.ByteBuffer
  +                               ? (T) org.apache.cassandra.utils.ByteBufferUtil.minimalBufferFor((java.nio.ByteBuffer) item)
  +                               : item;
  +            samplerExecutor.submit(() -> insert(retained, value));
  +        }
       }
  ```

  (`ByteBufferUtil.minimalBufferFor` copies when the buffer does not span its whole array, `ByteBufferUtil.java:721-725`.) Save
  `diff -u` as `harness/sampler-copy.diff`. Build without Ant, as R21: `javac -source 11 -target 11 -nowarn -encoding UTF-8 -cp
  'build/apache-cassandra-5.0.9-SNAPSHOT.jar:build/lib/jars/*' -d /mydata/s4/b25/pcls src/java/org/apache/cassandra/metrics/Sampler.java`,
  then `jar uf` the P jar with exactly the `org/apache/cassandra/metrics/Sampler*.class` files javac wrote (list and record them).
  Checks before readings (Step A): `javap -c -p` of `Sampler.addSample` on P shows `invokestatic …ByteBufferUtil.minimalBufferFor`
  and on U does not; class major version 55; `unzip -l` member lists of the P and U jars are equal; record P's sha256. Fallback only if
  javac fails: `ant jar` in `cassandra-p` after deleting `build/classes/main/org/apache/cassandra/metrics/Sampler*.class`.
  `/mydata/s4/cassandra-base` is never modified.
- **Node/OS:** pc82 (node1.jason92-326665, UMass): x86_64, 40 cores, 125 GiB, Ubuntu 22.04, kernel 5.15, cgroup v2, 8 GiB swap present,
  `/mydata` 753 GiB on a **rotational disk** (`sda` ROTA 1; 705 GiB free on 2026-11-24), JDK 11.0.33. GC = shipped
  `jvm11-server.options` (G1, `G1HeapRegionSize=16m`, so a 1 MiB region `byte[]` is an ordinary, not humongous, object;
  `jvm-server.options:120` `HeapDumpOnOutOfMemoryError`; `cassandra-env.sh:209` `OnOutOfMemoryError=kill -9 %p`; GC log from
  `cassandra-env.sh:81-83`). pc82's clock zone may differ from New York (pc75 was America/Denver): every cut-off uses
  `TZ=America/New_York`.
- **Capacity constraints (V6): all shipped defaults, read back from `system_views.settings` at every lifetime start and recorded:**
  `memtable_allocation_type: heap_buffers`; `memtable` default `skiplist`; `memtable_heap_space`/`memtable_offheap_space` → heap/4;
  `memtable_cleanup_threshold` → 0.33; `memtable_flush_writers` → 2; `commitlog_segment_size: 32MiB` (→ `max_mutation_size` 16 MiB);
  `commitlog_total_space` → 8,192 MiB; `concurrent_reads/writes: 32`; `native_transport_max_request_data_in_flight`/`_per_ip` →
  heap/10, heap/40; `native_transport_max_message_size` → 16 MiB; `key_cache_size` → min(5 % heap, 100 MiB); row cache off;
  `tables_warn_threshold`/`tables_fail_threshold` −1 (guardrail off); `read_thresholds_enabled: false`; hard-coded `samplerExecutor`
  queue limit 1000. **The sampler constraint at its nodetool defaults:** `-s 256`, `-k 10`, `-a` all eight samplers, duration
  default 10,000 ms (two positional arguments `b25 t<k>` → `durationMillis` stays 10000, `ProfileLoad.java:86-100`). All labels:
  **default**.
- **Non-capacity choices (documented deployment / workload choices, labelled):** single node, RF 1; keyspace `b25` with tables
  `t0 … t<K_max>` (and `ttail`), each `pk text PRIMARY KEY, v0 … v8 blob`; 9 × 122,880-B values per partition (each < the 128 KiB slab
  threshold, so they go into regions); a read-after-write client (§2.5); an operator who profiles the hot table, one table after
  another, with the default command. The table count is uncapped at defaults (guardrail −1).
- **Arm-only deviations:** C runs `nodetool profileload -a WRITES,WRITE_SIZE,LOCAL_READ_TIME,CAS_CONTENTIONS b25 t<k>` (sampler
  selection; the capacity stays 256). I runs build P. Optional I2 sets `memtable_allocation_type: unslabbed_heap_buffers` (a
  constraint changed in an intervention arm only, V6's exception). No Byteman, no raised timeout, no fault, no `nodetool flush` in the
  test arm. Conditions label of the U test arm: **deployment**.
- **Environment diff only:** `cluster_name: b25`, `listen_address`/`rpc_address: 127.0.0.1`, seeds `127.0.0.1:7000`; data, commit log,
  hints, saved caches, cdc under `/mydata/s4/b25/run/` (local disk); client source addresses `127.0.0.11`, `127.0.0.12`.
- **Budget (V7):** heap `MAX_HEAP_SIZE=2G` (the ideal; ≥ 512 MiB standing rule, no review needed); `MaxDirectMemorySize` as
  `cassandra-env.sh` resolves on pc82 (record; expected 15,872 MiB as on pc75); **no container limit**: the node runs in
  `systemd-run --user --scope -p MemorySwapMax=0` without `MemoryMax` (record `memory.max` = `max`, used only to keep swap off and to
  read `memory.current`/`memory.events`). The client JVM runs in its own scope (`MemoryMax=4G`, `-Xmx3g`); `nodetool` is a separate
  short-lived JVM. Budget search upward (§2.7): 4,096, 8,192 and 15,872 MiB (the last = what `cassandra-env.sh` resolves for a
  ≥ 32 GiB node); record the resolved values at each.

### 2.4 Ceiling arithmetic (2 GiB)

| Item | Bound | Source |
|---|---|---|
| D5 baseline | ≈ 150–250 MiB (≤ 18 empty-ish tables ≈ 6 MiB, key cache ≤ 100 MiB, rest of the node) | U14, R21 L0 |
| D3 in flight | ≤ 2 × 1.06 MiB on wire × ≈ 2 decoded ≈ 5 MiB | §2.2 |
| D1 contract | C_contract ≈ 600 MiB | §2.2 |
| D2 sampler contract | 16 tables × 0.24 MB ≈ 4 MB | stage 4 (116 B/entry) |
| D4 transient | ≈ 50 MiB | estimate |
| **Σ contract + baseline** | **≈ 0.9 GiB < 2 GiB** (margin ≈ 1.1 GiB) | |
| D1-pin (uncontracted) | **P per profiled table ≈ 0.27 GiB** at n ≈ 280 (≤ 0.5 GiB at n ≥ 512); after k sessions ≈ k × P, of which ≤ the live pool is still counted | §2.1 |

By contract nothing can reach 2 GiB. With D1-pin, live heap after session k ≈ B + k·P + pool_used (pinned regions still in a live
memtable are inside pool_used). With B ≈ 200 MiB, pool_used ≈ 170–340 MiB, P ≈ 275 MiB: B + k·P + pool ≥ ≈ 1.95 GiB at **k ≈ 5.3**,
and k·P alone passes the heap at k = 7. **Predicted T: OOM during session 6–7 (allowed 4–10).** **C:** live ≈ B + pool + ≤ 8 MB of
samplers ≤ 0.9 GiB, survives 16 sessions (margin ≈ 55 %). **I (P build):** the copies cost ≈ 120 B per entry; same as C, survives.
**One table alone** (k = 1) ≈ 0.75 GiB: no OOM — the multiplicity is needed, which is why the test profiles one table after another.

### 2.5 Workload and environment (pc82 only)

**Node check (stage 1, read-only ssh, 2026-11-24 05:49 EST):** pc82 = node1.jason92-326665, 40 cores, 125 GiB (123 GiB available),
`/mydata` 705 GiB free, load average 0.01, **no Java process** (`pgrep CassandraDaemon|cassandra-stress` empty), JDK 11.0.33,
`/mydata/s4/` holds `cassandra-base`, `NODE-LOCK/` (a directory), `3b-B23`, `3b-R12` (other cases' stopped folders: do not touch),
base jar sha256 `570b5249…0176e`. Respect the `NODE-LOCK` convention of the batch coordinator (take/release the lock as the root
HANDOFF / coordinator says); if another case's node is running on pc82, wait (bounded, recorded).

**Directories (pc82, local only):** `/mydata/s4/b25/{cassandra-u,cassandra-p,pcls,cls,run,dumps,logs}`; `run/` recreated per lifetime.

**Harness** (`harness/` in this folder; base = R21's
[`harness/`](../memtable_heap_space--stale-btree-updater-pins-discarded-memtables/harness/), copied and renamed, keep the
lifetime runner, the scope, `Jmx.java` poller, RSS loop, `hprof_scan.py`, `hprof_reach.py`, `reachq.sh`):

- **`RawGen.java`** (new client; DataStax driver from `build/lib/jars/*`, as R21's `HotGen`): one session, prepared
  `INSERT INTO b25.t<k> (pk, v0, …, v8) VALUES (?, …)` and `SELECT pk FROM b25.t<k> WHERE pk = ?`, CL ONE. **One writer thread
  per hot table**, serial: insert a new partition (pk `k<k>-<seq>`, 9 × 122,880 random bytes from a pre-generated pool), then read it
  back; paced to **28 partitions/s** (≈ 29.5 MiB/s) with a rate limiter. A control file names the hot table; the thread switches on
  change. CSV per second: inserts ok, reads ok (and reads returning 1 row), errors by class, latency p50/p99, hot table. Source
  address 127.0.0.11. Values fixed: 9 cells (a partition is 1,105,920 B of values > 1 MiB, so with one writer every slab region
  holds **at most one key**).
- **`run.py`** — lifetime runner: `run.py life <label> <build> <arm> <heap> <K_max>`; arms `T`, `C`, `I` (= `T` on build P), `I2`,
  `D` (diagnostic, §2.6), `C0` (no profileload). It creates the schema (`t0 … t<K_max-1>`, `ttail`), starts the node in the scope,
  starts `RawGen`, and runs the **session schedule**: for k = 0 … K_max−1: set hot table `t<k>` (phase start s_k); at s_k + 1 s run
  the arm's nodetool command (T/I: `bin/nodetool profileload b25 t<k>`; C: with `-a WRITES,WRITE_SIZE,LOCAL_READ_TIME,CAS_CONTENTIONS`;
  C0: none), save its stdout and its start/return times; the next phase starts at max(s_k + 16 s, return + 2 s). After the last
  session (or at the OOM), **tail**: hot table `ttail` for 60 s, no profileload. Endpoint checks every 1 s (§2.7). The build, jar
  sha256 and the `javap` line of `addSample` go to `summary.json`. Every OOM dump is kept (wait ≤ 300 s for `Heap dump file created`);
  in a surviving lifetime, after the tail: stop the client, wait 10 s, two `GC.class_histogram` and one `GC.heap_dump` (live).
- **`hprof_reach.py`** — R21's tool with a new cut **`sampler`**: remove the edges `MaxSampler.queue` (field `queue` declared in
  `org.apache.cassandra.metrics.MaxSampler`), `FrequencySampler.summary`, and every reference out of instances whose class name starts
  with `org.apache.cassandra.metrics.Sampler$$Lambda` (queued `insert` tasks). Reports reachable `byte[1048576]` with and without the
  cut; **R_s** = regions reachable **only** through the cut. Also counts `Sampler$Sample` and `com.clearspring.analytics.stream.Counter`
  instances (entries, K_s).
- **`hprof_scan.py`** — R21's (pool `SubPool` fields `allocated`/`reclaiming`/`limit`, per-`SlabAllocator` `regionCount`/state).
- **`analyze.py`** — per lifetime: per-session n_k (reads of `t<k>` between nodetool start and return), old-gen floor per phase
  from `gc.log`, K_pool trajectory, endpoint; per dump: R_s, live regions, K_pool, K_s, uncounted = live regions − Σ `regionCount` of
  non-discarded allocators.

**Step A — tree and checks (not readings; a failure stops the case before readings).** (1) copy both trees, patch/build/check P
(§2.3); (2) build `RawGen`, `Jmx`; (3) **reach known-answer check**: in a test JVM (never the node) with the U jar on the classpath,
create `MaxSampler` and `FrequencySampler` instances as stage 4's probe did (package `org.apache.cassandra.metrics`,
`DatabaseDescriptor.daemonInitialization()` or client init if needed; if the real classes cannot run outside a node, a same-named stub
with fields `queue`/`summary`), insert 10 slices of 10 distinct `byte[1048576]` held only by the samplers, 5 slices whose arrays are
also in a static list, and keep 7 arrays only in the static list; `jcmd GC.heap_dump`: `hprof_reach.py` must report reachable regions
22 and **R_s = 10** exactly; time the tool; (4) **shakedown** on U (2 GiB, 3 sessions, then stop; not a reading): node up, inserts and
reads ok, nodetool prints `READS`/`READ_ROW_COUNT` tables with keys `k<k>-…`, `ERROR` lines in `system.log` none, **n_k ≥ 256 in each
session**; the same 1-session shakedown on P. **Pre-registered fallback F1** (decided in Step A only, before any reading, recorded as
an amendment): if one writer cannot reach n_k ≥ 256 per session (insert+read latency > 36 ms), use **two writer threads per hot table
with 18-cell partitions** (2.1 MiB; keys per region ≤ 1 still holds per thread, about 0.8 distinct regions per key overall) at the
same 28 partitions/s; P then ≈ 0.8 × min(n, 512) regions, and K_max at 2 GiB rises to 20.

### 2.6 Instruments and readings (U measured independently of K)

| Reading | Source | When | Meaning |
|---|---|---|---|
| **R_s** (claimed holder) | `hprof_reach.py` cut `sampler` | every OOM dump, every end dump, D dumps | regions kept only by sampler structures (U of D1-pin) |
| live regions, uncounted | dump `byte[1048576]` count; minus Σ `regionCount` of non-discarded allocators | same | physical memtable-region bytes vs what any live charge covers |
| **K_pool** | dump `SubPool.allocated` (+ `reclaiming`); JMX global `AllMemtablesOnHeapDataSize` (`org.apache.cassandra.metrics:type=Table,name=AllMemtablesOnHeapDataSize`) and `MemtablePool` `BlockedOnAllocation`/`PendingFlushTasks` | dump; JMX every 500 ms | the pool counter |
| **K_s** | dump counts of `Sampler$Sample` and stream-lib `Counter`; nodetool output per session | dump; per session | the sampler's own count |
| **U trajectory (non-intrusive)** | `gc.log`: heap after each GC; **old-gen floor per phase** = minimum heap-after-GC within the phase | continuous | the per-session step (≈ P) |
| load | `RawGen` CSV (n_k, errors, latency), nodetool start/return times, JMX `ReadStage`/`MutationStage` completed, dropped `_SAMPLE` messages | 1 s / per session | target load reached; intervention keeps useful work |
| first error (V5) | `stdout.txt`/`system.log` (`OutOfMemoryError: Java heap space`, `Dumping heap`, `Heap dump file created`, `kill -9`), thread stacks in the dump | OOM | initiating failure |
| process | `RssAnon`, scope `memory.current`, `memory.events` | 1 s / end | no kernel kill |

No `GC.class_histogram`/`GC.heap_dump` during a T, C or I lifetime before its endpoint (intrusive); they are taken at the OOM (by the
JVM), after the tail in surviving lifetimes, and in arm D.

**Arm D — retention and release (diagnostic, 2 GiB; one lifetime on U, one on P).** Sessions k = 0, 1, 2 exactly as T; then stop the
client; `nodetool flush` (all keyspaces: every `b25` memtable becomes discarded); wait 30 s; two histograms + live dump **D1**; then
`bin/nodetool profileload b25 t0` with **no client running** (new empty samplers on t0); dump **D2**; idle 300 s; dump **D3**.

### 2.7 Predicted response, outcome rows and stopping budget

**Predictions (frozen; 2 GiB, K_max = 16).**

- **P1 (T, build U, all defaults):** heap OOM **3/3** (`java.lang.OutOfMemoryError: Java heap space`) at session **k* ∈ [4, 10]**
  (point 6–7); old-gen floor rises **200–300 MiB per session** for k ≥ 1 until the OOM; at each OOM dump **R_s ≥ 800 regions** and
  **R_s ≥ 0.5 × live regions**, with **K_pool ≤ 1.0 × C_contract (600 MiB)** and **K_s ≤ 8 × 256 × (k*+1)** (U > C, K ≤ C).
- **P2 (C, build U, write-side samplers only):** survives all 16 sessions + tail **3/3**; old-gen floor ≤ 1,100 MiB in every phase
  and its slope ≤ 20 MiB per session; end dump R_s ≤ 8 regions; median n_k within ± 15 % of T's.
- **P3 (I, build P, same command as T):** survives all 16 sessions + tail **3/3**; old-gen floor ≤ 1,100 MiB, slope ≤ 20 MiB/session;
  end dump R_s ≤ 8 regions while K_s is of the same order as T's (≥ 0.8 × 16 × 500 retained entries in total); median n_k ≥ 0.85 × T's
  (the patch does not stop useful work).
- **P4 (D, build U):** D1: K_pool ≤ 16 MiB (only system memtables) and **R_s ≥ 0.85 × Σ_{k<3} (min(n_k, 512) − 12)** (expected 700–840);
  D2: R_s falls by ≥ 0.8 × t0's share (≥ 200 regions); D3: R_s ≥ 0.95 × D2 (no time-based release). **D on P:** R_s ≤ 8 at D1–D3.
- **P5 (optional, not a verdict condition):** I2 (`unslabbed_heap_buffers`, build U, T command), 1 lifetime: survives 16 sessions;
  C0 (no profileload), 1 lifetime: survives, old-gen floor flat.
- **Budget search (V7, build U, T, 1 lifetime each, ascending; stop at the first survival = the boundary):** 4,096 MiB with K_max 32
  (predicted OOM at k ≈ 12), 8,192 MiB with K_max 64 (k ≈ 24), 15,872 MiB with K_max 124 (k ≈ 48, ≈ 13 min of sessions, ≈ 22 GiB
  written). Report the largest failing budget; if time remains, repeat it to 3 runs and run C once there.
- **Validity (every lifetime):** read-back of settings equals §2.3; build hash/`javap` as planned; **n_k ≥ 256 in ≥ 80 % of sessions**
  and every nodetool call returned 0 with output naming `t<k>` keys (target load reached); `memory.events` `oom_kill` 0; no `ERROR` in
  `system.log` before the endpoint other than the OOM's. A lifetime failing validity is invalid (re-run once after fixing; recorded),
  not a reading.

**Outcome rows** (the fixed condition is **T on build U at 2 GiB, all defaults**; V2 = C; V4 = I):

| Row | Readings | Verdict (playbook) / status |
|---|---|---|
| 1 | P1 (≥ 3 OOMs, R_s and K as stated), P2 0 OOM in 3, P3 0 OOM in 3, P4 consistent | **true positive**, `verified-OOM · deployment`, bypass (accounting omission; mixed if stage 2 shows the multiplicity is required as a domain) |
| 2 | T OOM ≥ 3, but C or I also OOM | **retry** (attribution: another holder; dumps say which) |
| 3 | T no OOM within K_max, but R_s / old-gen floor grow per session as P1 (service loss or plateau) | **retry** (`verified-gap` if V1–V7 hold; next design: more sessions or larger n) |
| 4 | T no OOM, load valid, D1 R_s ≤ 8 (keys are not slab slices on this path) and the old-gen floor flat | **false positive** (the claimed holder does not exist at defaults) |
| 5 | invalid lifetimes only (load not reached, nodetool failures) | no reading; fix and re-run within the budget, else **retry** |

**Stopping budget.** Per lifetime: ≤ K_max × 18 s + 60 s tail + 300 s dump wait (2 GiB: ≤ 11 min). Planned lifetimes: Step A
shakedowns; T ×3, C ×3, I ×3 (2 GiB); D ×2; ladder ×3 (+ optional repeats, I2, C0). Total stage-2 wall budget **5 h**; no new
lifetime starts after 5 h from Step A's start (cut-off written into `plan.sh` with `TZ=America/New_York`). No escalation after an OOM
(no larger n, no `-s` above 256, no all-tables profileload) beyond the frozen ladder.

### 2.8 Controls and intervention

- **Matched control C (V2, ≥ 3):** same build, budget, schema, client, rate, session schedule and nodetool defaults, but the sampler
  selection is the four samplers whose items are **not** memtable keys (`WRITES`, `WRITE_SIZE`: the decoded request's own copy;
  `LOCAL_READ_TIME`: CQL strings; `CAS_CONTENTIONS`: idle). This is the protected path against the suspect path (bypass rule 5).
- **Intervention I (V4, ≥ 3):** build P (copy the key in `Sampler.addSample`), T's exact command (all eight samplers). Removes only the
  reference to the region; sampling, counts and capacity are unchanged. Its throughput (n_k, reads/s) is compared with T's.
- **Attribution aids:** arm D (retention after `finishSampling`, release by the next `beginSampling` of the same table), the cut
  `sampler` in every dump, optional I2 (unslabbed allocator removes the slab slice from the other side).
- **What stage 2 writes back** (playbook stage 2 step 5): the verdict to **both** OC-585 and OC-588; a row in `cases/_INDEX.md`;
  for a retry, the retry-list row.

`sha256 of §1–§2 at freeze: 895b55b0f622d5aa975204091e2367fd5ec502f5808a800d3d897c0320d7beb7` (computed as `awk '/^## 1\. Candidate/{f=1} /^.sha256 of §1–§2 at freeze/{f=0} f' <this file> | sha256sum`, i.e. from the `## 1. Candidate` line up to, not including, this line; 2026-11-24) · amendments after the freeze: none.

## 3. Runs (stage 2)

pending

## 4. Conclusion (stage 2)

pending
