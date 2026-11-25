# B25 — profileload sampler capacity: read samplers keep memtable slab-slice keys, so each retained sample pins a 1 MiB region after flush  <!-- file: cassandra/cases/profileload-capacity--read-sampler-pins-slab-regions/profileload-capacity--read-sampler-pins-slab-regions.md -->

| Field | Value |
|---|---|
| Case ID | `B25` (B = bypass case; README "ID prefixes"). Predicted class by the protocol's measurement table: **bypass, accounting omission** (U > C, K ≤ C: the sampler counts entries while each read-sampler entry holds a whole 1 MiB slab region, and the memtable pool has released those regions at discard). The OOM needs the per-table retention to stack over several tables, so stage 2 may label it **mixed** (bypass excess + table multiplicity); §2.1 |
| From | `OC-585` (primary, autonomous) + `OC-588` (guided) of the [phase 1 OOM candidate list](../../../../capacity-enforcement-exp/cassandra/stage5-oom-clue-find/phase1-oom-candidates.md) (both Status `picked: B25 (2026-11-24)`); owner-approved batch of 2026-11-24 |
| Phase-1 case file | [`profileload-capacity-beginsampling-capacity--autonomous`](../../../../capacity-enforcement-exp/cassandra/stage3-ai-deep-read/cases/profileload-capacity-beginsampling-capacity--autonomous.md) (shared by OC-585 … OC-588) |
| System / pinned source | Cassandra 5.0.9 (`systems/cassandra/source/`, `build.xml` `base.version` 5.0.9); on pc82 `/mydata/s4/cassandra-base`, `build/apache-cassandra-5.0.9-SNAPSHOT.jar` sha256 `570b5249d9b9a43f6809eb3da562737492192026f974b2edbd20e94bea90176e`; OpenJDK 11.0.33 |
| Stage 1 (design) | fresh OOM-agent stage-1 session, 2026-11-24 05:40–06:40 America/New_York; nothing run (read-only check of the five x86 nodes, read-only source reads in the repository and on GitHub raw, read-only JIRA REST searches) |
| Stage 2 (verify) | fresh OOM-agent stage-2 session, 2026-11-24 09:15–12:41 America/New_York (all runs), on **pc99** instead of pc82 (dated deviation, §3.1); the write-up, excerpts and node cleanup were finished 15:00–15:10 by a second stage-2 session started after the first ended (no new lifetime: the 14:17 cut-off had passed). Freeze hash checked by both: `895b55b0…7beb7` matches. 19 lifetimes + Step A (3 shakedowns, reach check); no amendment |
| Verdict | **true positive**: `verified-OOM · deployment`, **bypass (accounting omission)**, outcome row 1 |

## Summary

- **Conclusion:** **true positive** (`verified-OOM · deployment`, bypass, accounting omission). At a 2 GiB heap with every default, the T arm
  OOMs 3/3 after 7–8 profiled tables, with 1,625–1,667 slab regions (79–81 % of the heap) reachable only through sampler entries;
  the write-side-samplers control C and the key-copy build P each survive 3/3 with no pinned regions. OOM 3/3 also at 15,872 MiB (§3–§4). Design: on one node at a 2 GiB heap with every capacity constraint at its default, an
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

Fresh OOM-agent stage-2 session, 2026-11-24 09:15–12:41 America/New_York (all lifetimes; the write-up, excerpt copy and cleanup were finished 15:00–15:10 by a second
stage-2 session after the first ended, which re-checked the freeze hash, started no lifetime and read the readings from the node logs) (node clock is America/Denver; every time
below is New York). Freeze hash checked before anything ran: `895b55b0…7beb7` = the value in §2 (match). Harness:
[`harness/`](harness/) (`run.py` lifetime runner, `RawGen.java` client, `client.py` admin, `Jmx.java` poller (R21's),
`hprof_scan.py` (R21's, unchanged), `hprof_reach.py` (R21's with the cut `sampler`), `ReachCheck.java` + `reach-check.sh`
(known-answer check), `analyze.py`, `table.py`, `sampler-copy.diff`). Raw logs on pc99 `/mydata/s4/b25/logs/<label>/`; small
excerpts (summary.json, reach JSONs, one nodetool output, OOM stdout tails, yaml diff, memory.events) in [`logs/`](logs/).

### 3.1 Environment, deviations, Step A

- **Node (dated deviation, 2026-11-24):** **pc99** (node4.jason92-326665, UMass) instead of pc82, as assigned by the batch
  coordinator; same class: x86_64, **32 cores** (pc82: 40), 125 GiB, Ubuntu 22.04, kernel 5.15, cgroup v2, 8 GiB swap present
  (scope `MemorySwapMax=0`), `/mydata` 753 GiB on a rotational disk (`sda` ROTA 1, 695 GiB free), OpenJDK 11.0.33. At 09:17 EST the
  node was idle (load 0.00, no Java process, no `NODE-LOCK`); lock taken 09:17:52 EST as `B25-stage2`. `/mydata/s4/` also holds
  `3b-C9`, `3b-U9`, `u14` (other cases' stopped folders, not touched). Base jar sha256 = `570b5249…0176e` (as planned).
- **Budget resolved on pc99:** `MaxDirectMemorySize=15872M` (cassandra-env, as expected); heap per arm via `MAX_HEAP_SIZE`
  (`-Xms = -Xmx`); node scope `memory.max = max`, `memory.swap.max = 0` in every lifetime; JVM flags as shipped (G1,
  `G1HeapRegionSize=16m`, `HeapDumpOnOutOfMemoryError`, `OnOutOfMemoryError=kill -9 %p`; full command line in each
  `jvm-cmdline.txt`).
- **Settings read-back (every lifetime, `system_views.settings`):** `memtable_allocation_type heap_buffers` (I2 arm:
  `unslabbed_heap_buffers`), `memtable_heap_space`/`memtable_offheap_space` = heap/4 (512 / 1024 / 2048 / 3968 MiB),
  `memtable_cleanup_threshold 0.33333334`, `memtable_flush_writers 2`, `commitlog_segment_size 32MiB`, `max_mutation_size 16384KiB`,
  `commitlog_total_space 8192MiB`, `concurrent_reads/writes 32`, `native_transport_max_request_data_in_flight 214748364B` /
  `_per_ip 53687091B` (at 2 GiB), `native_transport_max_message_size 16777216B`, `key_cache_size 100MiB`, `row_cache_size 0MiB`,
  `tables_warn/fail_threshold -1`, `read_thresholds_enabled false`, `memtable` null (default skiplist). All as §2.3. The yaml
  diff of every lifetime changes only `cluster_name`, `listen_address`, `rpc_address`, seeds and the run directories
  ([`logs/T1/yaml.diff`](logs/T1/yaml.diff)).
- **Step A (1) builds:** U = `cp -a cassandra-base`, sha256 `570b5249…0176e`. P = `cp -a cassandra-base` + the §2.3 diff
  ([`harness/sampler-copy.diff`](harness/sampler-copy.diff)), `javac -source 11 -target 11` of `Sampler.java` (it wrote
  `Sampler.class`, `Sampler$Sample.class`, `Sampler$SamplerType.class`), `jar uf` with exactly those three; P jar sha256
  **`43823304885fa0e2cd90a92fedc957873fcd861046b3817c1fee98814da9e9ce`**; `javap -c -p` of `addSample`: P has
  `invokestatic …ByteBufferUtil.minimalBufferFor`, U has none; class major version 55; `unzip -l` member lists equal (5,956).
  `bin/cassandra.in.sh` puts the single `build/apache-cassandra-*.jar` on the classpath (not `build/classes/main`). The
  runner re-checks hash and `javap` at every lifetime start.
- **Step A (3) reach known-answer check** ([`logs/reach-check-summary.txt`](logs/reach-check-summary.txt)): real `MaxSampler` /
  `FrequencySampler` instances (anonymous subclasses, U jar) in a test JVM. First attempt read 18 / R_s 6: the **test program**
  inserted all-zero 12-byte slices, and `StreamSummary` keys by `ByteBuffer.equals` (content), so the five FrequencySampler-only
  slices collapsed into one `Counter` and four arrays were collected (the tool's count was right for the heap it saw). Fixed in
  the test program (distinct content per slice, as distinct partition keys have); second attempt: **reachable 22, R_s 10**, 2 cut
  field references, 8 `Sampler$Sample` + 7 `Counter`, 0.47 s. Not a reading.
- **Step A (4) shakedowns (not readings):** the first U attempt stopped at the settings read-back before any load because the
  harness expected `16MiB` where `system_views` prints `16777216B` (same value; expectation corrected). `shk-U2` (U, 2 GiB,
  3 sessions): node up, 1,432 inserts and 1,432 reads all returning 1 row, **n_k 313 / 305 / 282**, every nodetool rc 0 and its
  `Frequency of reads by partition` table lists `b25.t<k> k<k>-…` keys ([`logs/shk-U2/nt-s1.txt`](logs/shk-U2/nt-s1.txt)),
  `ERROR` lines 0, cycle (insert + read) p50 7–22 ms. `shk-P` (P, 1 session): n_k 313, nodetool ok, no `ERROR`. **F1 not
  needed** (one writer reaches n_k ≥ 256). Harness fixes during Step A (before readings): `pgrep` patterns that matched their own
  shell (`[R]awGen`).
- **Analysis gaps (recorded):** (a) the shipped `-Xlog:gc…heap*=trace` with `filecount=10,filesize=10M` rotates over the
  earliest phases at 8,192 / 15,872 MiB, so the gc.log old-gen floor exists only for the last sessions there; the 500 ms JMX
  sampler (`sampler.csv`: old-gen used after collection) covers the whole run. (b) With `-XX:OnOutOfMemoryError=kill -9 %p` the
  JVM prints the OOM without a thread name and `system.log` has no line for it (as R21); V5 rests on the stdout sequence and
  the dump.

### 3.2 Readings at 2 GiB (T, C, I; build, arm, sessions as §2.5; K_max 16)

Per-session reads n_k (reads of t<k> between nodetool start and return; every read returned 1 row), old-gen floor
(minimum heap-after-GC in the phase, gc.log), dump readings by `hprof_reach.py` / `hprof_scan.py`. K_pool = dump
`SubPool.allocated` (JMX `AllMemtablesOnHeapDataSize` max per phase ≤ 171 MiB in every 2 GiB lifetime). K_s = reachable
`Sampler$Sample` + stream-lib `Counter` instances.

| Lifetime | Build / arm | Endpoint | Sessions done (OOM in) | n_k median (≥ 256) | Old-gen floor per phase (MiB) | Dump | R_s regions | live regions | K_pool (MiB) | K_s |
|---|---|---|---|---|---|---|---|---|---|---|
| T1 | U / T | **heap OOM** at 124 s | 8 (k = 7) | 301 (6/7) | 202, 677, 809, 1027, 1268, 1531, 1764, 1894 | OOM | **1,625** | 1,831 | 184.9 (+ 81.3 reclaiming) | 4,678 + 3,288 |
| T2 | U / T | **heap OOM** at 117 s | 7 (k = 6) | 298 (6/6) | 199, 680, 818, 1038, 1277, 1543, 1770 | OOM | **1,655** | 1,837 | 163.8 | 4,690 + 3,296 |
| T3 | U / T | **heap OOM** at 123 s | 8 (k = 7) | 292 (6/7) | 186, 669, 803, 1017, 1248, 1535, 1766, 1898 | OOM | **1,667** | 1,839 | 154.3 | 4,695 + 3,298 |
| C1 | U / C | survives 16 + tail | 16 | 303 (16/16) | 200 … max 777 (slope 8.4 / session) | end | **0** | 181 | 159.5 | 7,782 + 4,083 |
| C2 | U / C | survives 16 + tail | 16 | 295 (16/16) | 233 … max 747 (slope 11.5) | end | **0** | 132 | 116.2 | 7,794 + 4,089 |
| C3 | U / C | survives 16 + tail | 16 | 298 (16/16) | 198 … max 815 (slope 0.0) | end | **0** | 179 | 159.5 | 7,786 + 4,085 |
| I1 | P / I | survives 16 + tail | 16 | 288 (16/16) | 182 … max 672 (slope 5.1) | end | **0** | 61 | 49.7 | 11,670 + 8,164 |
| I2 | P / I | survives 16 + tail | 16 | 291 (16/16) | 184 … max 637 (slope −5.3) | end | **0** | 62 | 50.7 | 11,621 + 8,133 |
| I3 | P / I | survives 16 + tail | 16 | 296 (15/16) | 184 … max 797 (slope 7.3) | end | **0** | 157 | 137.3 | 11,642 + 8,146 |

- **T, every OOM:** `stdout.txt` reads `java.lang.OutOfMemoryError: Java heap space` → `Dumping heap to …` → `Heap dump file
  created [2,025–2,039 MB]` → `kill -9 <pid>` → `Killed` ([`logs/T1/stdout-tail.txt`](logs/T1/stdout-tail.txt)); scope
  `memory.events` `oom 0`, `oom_kill 0` (no kernel kill); no `ERROR` in `system.log`; the last GCs before the OOM are back-to-back
  Full GCs at 1,899 → 1,899 MiB of 2,048. The session before the OOM is already GC-bound (n_k 139–163, 185 GCs in T1's phase 6).
  The client saw only transport errors (node gone).
- **Uncounted:** at every T dump, live regions − Σ `regionCount` of non-discarded allocators = **R_s exactly** (1,625 / 1,655 /
  1,667): every region held only by a sampler belongs to a memtable the pool no longer counts, and 89–91 % of all live regions
  are such regions. R_s = 1.59–1.63 GiB = 79–81 % of the heap, held by 7.97–7.99 k sampler entries whose contract is
  ≈ 116 B each (≈ 0.9 MB in total).
- **Per-session step:** the T floor rises 475–483 MiB from phase 0 to 1 (the first table's pinned regions plus the pool filling),
  then 132–138, 214–220, 231–241, 263–287, 227–233 MiB; least-squares slope **245 / 250 / 247 MiB per session**. C and I floors
  saw-tooth (young/mixed collections) with no trend.
- **n_k:** T medians 301 / 298 / 292; C 303 / 295 / 298 (within ± 3 % of T); I 288 / 291 / 296 (0.97–0.99 × T). Every nodetool call
  in a completed session returned 0 and listed `t<k>` keys.

### 3.3 Arm D — retention and release (2 GiB; §2.6)

| Lifetime | Sessions n_k | After `nodetool flush` + 30 s: **D1** | after `profileload b25 t0` with no client: **D2** | after 300 s idle: **D3** |
|---|---|---|---|---|
| DU (build U) | 286, 303, 290 | **R_s 816** of 819 live regions; K_pool 3,839 B (allocators all LIVE, 3 regions); K_s 2,196 + 1,536 | **R_s 540** (−276); K_s 1,464 + 1,024 (t0's 732 + 512 entries replaced by empty samplers) | **R_s 540**; K_s unchanged |
| DP (build P) | 314, 302, 286 | R_s **0** (0 live regions); K_pool 0; K_s 2,196 + 1,536 | R_s 0; K_s 1,464 + 1,024 | R_s 0 (2 live regions, a new system memtable) |

Histograms agree: DU `[B` 869 MB at D1 → 580 MB at D2 → 582 MB at D3 with `AllMemtablesOnHeapDataSize` 3,839 B; the same
`Sampler$Sample` / `Counter` counts on U and P. So after every memtable is flushed and discarded, **≈ 816 MiB stays reachable
only through the samplers of three tables**, uncounted by the pool, until a new `beginSampling` on the same table; a new
session on t0 frees t0's share and nothing else; idle time frees nothing. The copy in `addSample` removes all of it at the
same entry counts.

### 3.4 Budget search (V7; build U, T command, all defaults; ascending)

| Lifetime | Heap (pool) | K_max | Endpoint | OOM in session | n_k median | OOM dump: R_s / live regions | K_pool | K_s |
|---|---|---|---|---|---|---|---|---|
| L4 | 4,096 MiB (1,024 MiB) | 32 | **heap OOM** at 240 s | k = 14 (pred. ≈ 12) | 289 | 3,449 / 3,756 (3.37 GiB) | 280 MiB | 9,406 + 6,607 |
| L8 | 8,192 MiB (2,048 MiB) | 64 | **heap OOM** at 490 s | k = 29 (pred. ≈ 24) | 303 | 6,987 / 7,595 (6.82 GiB) | 564 MiB | 19,942 + 13,981 |
| L16 | 15,872 MiB (3,968 MiB) | 124 | **heap OOM** at 920 s | k = 54 (pred. ≈ 48) | 300 | 13,403 / 14,794 (13.1 GiB) | 1,299 MiB | 37,953 + 26,586 |
| L16b | 15,872 MiB (3,968 MiB) | 124 | **heap OOM** at 878 s | k = 53 | 300 | 13,435 / 14,776 (13.1 GiB) | 1,254 MiB | 37,986 + 26,598 |
| L16c | 15,872 MiB (3,968 MiB) | 124 | **heap OOM** at 894 s | k = 53 | 298 | 13,461 / 14,795 (13.1 GiB) | 1,247 MiB | 37,920 + 26,554 |
| LC16 | 15,872 MiB, **C** (write-side samplers) | 124 | **survives** 124 sessions + tail (2,072 s) | — | 304 (124/124 ≥ 256) | end: **0** / 641 | 599 MiB | 60,512 + 31,744 |

Heap dumps at 15,872 MiB were 15.66–15.68 GB. The repeats L16b/L16c and LC16 ran because time allowed (§2.7: "repeat it to 3 runs
and run C once there"). At this heap the old-gen floor per phase does not show liveness: G1 (IHOP 70 %) runs no mixed cycle inside
most 16 s phases, so LC16's floor goes up and down between 762 and 13,528 MiB, falls back to 1,176–1,508 MiB after each mixed cycle,
and has no trend (slope −6.5 MiB/session). Its end dump (641 live regions, R_s 0) is the liveness reading. gc.log rotated over the
early phases, as recorded in §3.1 gap (a).

Every step failed (15,872 MiB: 3/3); 15,872 MiB is what `cassandra-env.sh` resolves for a node with ≥ 32 GiB RAM (the largest heap it picks), so
the **largest failing budget is the top of the ladder** (no surviving boundary within acceptable budgets). The OOM session
scales with the heap (≈ 3.5 tables per GiB). Every OOM: same stdout sequence, `oom_kill 0`, no `ERROR`; uncounted regions =
R_s in each dump.

### 3.5 Optional arms (P5; not verdict conditions)

| Lifetime | Build / arm | Endpoint | n_k median | Old-gen floor (MiB) | End dump: R_s / live regions | K_pool | K_s |
|---|---|---|---|---|---|---|---|
| X1 (the design's optional arm "I2"; renamed so it does not clash with lifetime I2) | U / T command with `memtable_allocation_type: unslabbed_heap_buffers` (read back) | **survives** 16 + tail | 296 (16/16) | 113 … max 897 (slope −18.6) | **0 / 0** (no slab regions exist under this allocator) | (no `SubPool` reading; JMX max 170 MiB) | 11,707 + 8,188 |
| C0a | U / C0 (no profileload) | **survives** 16 + tail | (411 reads per matching window) | 197 … max 758 (slope −0.1) | 0 / 159 | 139 MiB | 0 + 0 |

P5 met: when the allocator does not slice slab regions, the same command with the same sampler counts pins nothing. Without any
profileload, the workload's floor is flat. `ERROR` lines 0 and `oom_kill` 0 in both. Excerpts: [`logs/X1/`](logs/X1/), [`logs/C0a/`](logs/C0a/),
[`logs/LC16/`](logs/LC16/).

### 3.6 Predictions against readings

| Prediction | Reading | Met? |
|---|---|---|
| P1: T OOM 3/3 at k* ∈ [4, 10] (point 6–7) | OOM 3/3 at k* = 7, 6, 7 | yes |
| P1: floor rises 200–300 MiB per session for k ≥ 1 | slope 245–250 MiB/session; individual steps 132–287 (the k = 1 → 2 step 132–138 below the band, the first step 475–483 above) | yes as a trend; one step per lifetime below the band |
| P1: R_s ≥ 800 and ≥ 0.5 × live regions | 1,625–1,667; 0.89–0.91 × live | yes |
| P1: K_pool ≤ 600 MiB; K_s ≤ 8 × 256 × (k* + 1) | 154–185 MiB; 7,966–7,993 ≤ 14,336–16,384 | yes |
| P2: C survives 16 + tail 3/3; floor ≤ 1,100, slope ≤ 20; R_s ≤ 8; n_k ± 15 % | 3/3; max 747–815, slope 0.0–11.5; R_s 0; ± 3 % | yes |
| P3: I survives 3/3; floor ≤ 1,100, slope ≤ 20; R_s ≤ 8; K_s ≥ 6,400; n_k ≥ 0.85 × T | 3/3; max 637–797, slope −5.3–7.3; R_s 0; 19.8 k; 0.97–0.99 × T | yes |
| P4 (DU): D1 K_pool ≤ 16 MiB, R_s ≥ 0.85 × Σ(min(n_k, 512) − 12) = 717 | 3,839 B; 816 | yes |
| P4 (DU): D2 R_s falls by ≥ 200; D3 ≥ 0.95 × D2 | −276; 540 = 540 | yes |
| P4 (DP): R_s ≤ 8 at D1–D3 | 0, 0, 0 | yes |
| Ladder predicted k ≈ 12 / 24 / 48 | 14 / 29 / 54, 53, 53 | OOM at every step (15,872 MiB 3/3; C survives there); ≈ 15 % later than predicted (P per session ≈ 245 MiB, not 275) |
| Validity: settings, hash/javap, n_k ≥ 256 in ≥ 80 % of sessions, nodetool rc 0 with `t<k>` keys, `oom_kill` 0, no `ERROR` | all lifetimes (T: 0.86 / 1.0 / 0.86 of completed sessions; the GC-bound session before each OOM is the one below 256) | yes |

### 3.7 Cleanup

- Every lifetime's runner stopped its node, client and poller. The runner deleted each OOM and end heap dump after
  `hprof_reach.py`/`hprof_scan.py` had read it (`/mydata/s4/b25/dumps/` and the run directories were empty or gone at 15:01 EST).
- 2026-11-24 15:02 EST (second session, under the node lock): deleted `/mydata/s4/b25/cassandra-u` and `cassandra-p` (838 MB), the
  rotated gc logs (585 MB), `debug.log`, `rawgen.csv.reads` and class histograms. Left on pc99: `/mydata/s4/b25/` (22 MB: harness,
  compiled client/P classes, chain scripts, and per-lifetime `summary.json`, `system.log`, `stdout.txt`, `session.log`, CSVs,
  `nt-s*.txt`, reach/scan JSONs). `pgrep` found no Cassandra, RawGen, Jmx or nodetool process. `/mydata/s4/cassandra-base` and other
  cases' folders (`3b-C9`, `3b-U9`, `u14`) were not touched. `NODE-LOCK` released 15:02 EST.

## 4. Conclusion (stage 2)

**Verdict: true positive.** Status **`verified-OOM · deployment`** (V1–V7 met for T on build U at 2 GiB, all defaults);
direction **bypass — accounting omission** (U > C, K ≤ C); interpretation **suspected implementation defect**.

Operator-run `nodetool profileload <ks> <table>` with every default option, on one table after another while that table takes
read-after-write traffic, ends in a heap `OutOfMemoryError` 3/3 at a 2 GiB heap after 7–8 tables, and at every budget up to
15,872 MiB (4,096 / 8,192 MiB: after 15 / 30 tables; 15,872 MiB 3/3 after 54–55 tables, where the C control survives 124 tables). The dumps show the claimed holder: 1,625–1,667 slab regions
(1.6 GiB, 79–81 % of the heap) are reachable only through `MaxSampler.queue` / `FrequencySampler.summary`, held by ≈ 8 k
sampler entries whose count is within the capacity contract (256 per sampler per table) but each of which keeps a whole 1 MiB
`byte[]` through its partition-key slice; the memtable pool counts none of them (live regions − regions of non-discarded
allocators = R_s exactly). Arm D shows the retention directly: after a flush, ≈ 816 MiB stays reachable only through three
tables' samplers with the pool at 3,839 B; a new `beginSampling` on one table releases that table's share only, and idle time
releases nothing. The protected path (write-side samplers, whose keys are the decoded request's own copy) survives 3/3 with
R_s 0, and the intervention (`Sampler.addSample` copies a `ByteBuffer` key with `ByteBufferUtil.minimalBufferFor`, the
`retainable()` idea `TopPartitionTracker` already uses) removes the endpoint 3/3 and every pinned region at the same sample
counts and 0.97–0.99 × T's reads.

**Classification.** The OOM is reached by the D1-pin domain alone stacking over profiled tables (R_s ≈ 80 % of heap at each
OOM; the pool stays at 154–185 MiB, under ⅓ of its contract), so it is labelled bypass, not mixed: the multiplicity is that
of the uncounted holder itself (per table), and no other domain has to exceed its contract. One table pins ≈ 245–280 MiB, so
a 2 GiB node needs ≈ 7 profiled tables; the number scales with the heap (≈ 3.5 tables per GiB).

**Deployment conditions.** Capacities all at their defaults and read back (V6); budgets 2,048 → 15,872 MiB heap with the
resolved 15,872 MiB direct limit, no container limit (V7). Non-capacity choices as designed: single node, RF 1, a
read-after-write client with ≈ 1.06 MiB partitions (each key in its own slab region; smaller partitions share regions, so fewer
regions per retained key), and an operator who profiles hot tables one after another with the default command. `nodetool`
is an operator tool (JMX), so stage 3-b should expect `not client-triggerable` unless a client path to sampling exists.

| | Evidence |
|---|---|
| V1 Repetition | T OOM **3/3** (T1–T3); also L4, L8 (1/1 each) and 15,872 MiB **3/3** (L16, L16b, L16c); C at 15,872 MiB (LC16) survives 124 sessions |
| V2 Matched control | C (write-side samplers, same build, budget, schema, client, schedule) **0/3** OOM, R_s 0 |
| V3 Measurement | U (R_s, live regions by `hprof_reach.py`; old-gen floor from gc.log; histograms) measured independently of K (sampler entry counts; pool `SubPool.allocated`, JMX `AllMemtablesOnHeapDataSize`) |
| V4 Intervention | build P (copy in `addSample`) **0/3** OOM at matched load (n_k 0.97–0.99 × T), R_s 0; DP R_s 0 at D1–D3 |
| V5 Initiating failure | `OutOfMemoryError: Java heap space` → heap dump → `kill -9 %p` in each T stdout, `oom_kill 0`; each OOM dump shows the holder (R_s 1,625–1,667) |
| V6 Default constraints | every capacity setting at its shipped default, read back each lifetime (§3.1); profileload at its defaults (`-s 256`, `-k 10`, all samplers, 10 s) |
| V7 Acceptable budget | 2 GiB (ideal) and every ladder step up to 15,872 MiB; direct 15,872 MiB as resolved; no container limit |

**Limits of attribution.** The OOM needs an operator to run `profileload` (or `toppartitions` for the read samplers) on
several distinct tables that take reads served from memtables, with no later session on the same table; the amount per table
is bounded by min(reads in the window, 512) distinct regions, so tables whose partitions share regions pin less per entry.
Off-heap allocators (`offheap_buffers` / `offheap_objects`) were not tested (not defaults). The ≈ 15 % later OOM session than
predicted comes from P ≈ 245 MiB per table (READS and READ_ROW_COUNT overlap more than the design assumed), not from any
release.
