# R8 — key_cache_size + counter_cache_size: weigher gap stacked on the coordinator's local-write backlog  <!-- file: cassandra/cases/key_cache_size+counter_cache_size--weigher-gap-on-write-backlog/key_cache_size+counter_cache_size--weigher-gap-on-write-backlog.md -->

| Field | Value |
|---|---|
| Case ID | `R8` (R = a new attempt at an earlier case: B7) |
| From | retry of `B7` ([phase-2 retry list](../../phase2-retry-list.md), row B7) |
| Phase-1 case file | [`key_cache_size-create-size--autonomous`](../../../../capacity-enforcement-exp/cassandra/stage3-ai-deep-read/cases/key_cache_size-create-size--autonomous.md), [`counter_cache_size-putcachedcounter-capacity--autonomous`](../../../../capacity-enforcement-exp/cassandra/stage3-ai-deep-read/cases/counter_cache_size-putcachedcounter-capacity--autonomous.md) |
| System / pinned source | Cassandra 5.0.9 (`systems/cassandra/source/`; on pc91 the built copy `/mydata/s4/cassandra-base`, git baseline `6a75178`, `conf/cassandra.yaml` md5 `714ee9bf…`, the same yaml as B7 and S2) |
| Stage 1 (design) | phase-2 OOM agent, stage 1 (Claude Opus 5.5, workflow subagent), 2026-11-17 22:40–23:10 EST |
| Stage 2 (verify) | phase-2 OOM agent, stage 2 (Claude Opus 5.5, fresh workflow subagent), 2026-11-17 22:52–23:20 EST, pc91 |
| Verdict | **retry** (`candidate`: the backlog holder did not form on pc91; stopped by §2.6 step 1 after 2 calibration arms) |

## Summary

- **Conclusion (stage 2, 2026-11-17): retry.** On pc91 the local-write backlog did not form (max `MutationStage`
  pending 9,724 and 2,684 for a 65,000-write burst, < the frozen 10,000 threshold; late local writes became hints), so
  the run stopped after two calibration arms with V alive (live heap after Full GC ≤ 61 %). The B7 cache gap itself
  reproduced (≈ 275 MiB in the cache classes for 150 MiB counted). No OOM, no counted arms.
- **Design (stage 1):** Stage 1 designs a **mixed** heap OOM at 2 GiB: S2's unbounded local-write
  backlog on `MutationStage` (a fixed-size write burst sized so the node sits just below the OOM edge) plus B7's
  uncounted cache memory (both caches filled at their default caps hold ≈ 304 MiB for 150 MiB of counted weight).
  The claim to test: at one burst size N\*, the shipped weigher OOMs 3/3, the B7 weigher that charges the per-entry
  overhead survives 3/3, and invalidated caches survive 3/3.
- **Root cause (claimed, not tested here):** no control charges the coordinator's queued local writes (S2), and the key and
  counter cache weighers count only key + value bytes, not the ≈ 90 B per entry the Caffeine container needs (B7), so
  the caches take ≈ 163 MiB more heap than their configured sizes allow; at the edge that excess decides the OOM.

## 1. Candidate

**Retry row (quoted from [`phase2-retry-list.md`](../../phase2-retry-list.md), 2026-11-17):**

> | [B7](cases/bypass/key_cache_size+counter_cache_size-accounting-mismatch/key_cache_size+counter_cache_size--accounting-mismatch.md) | 2026-11-12 | `verified-gap · overshoot · deployment`: at shipped defaults the key cache holds 2.14× and the counter cache 1.80× their caps (weigher omits node, table and sketch), 3/3 at 512 MiB, 2 GiB and auto 7,965 MiB heap; a weigher with +104 B/entry removes it 3/3. No OOM at defaults (0/2 at 512 MiB, 0/1 at 2 GiB; the excess is ≤ ≈ 7.5 % of the heap above contract) | Alone it cannot reach OOM (the caps are heap-derived), so use it as a layer: stack both caches filled with small entries (8 B keys, many distinct keys) on another growing heap holder at 2 GiB (S2 stage 2 moved 4 GiB 1/3 → 2/3 with the caches filled); add the back-link term that a runtime shrink leaves Caffeine's table and sketch at the old size (+17.3 MB); sibling weighers (pattern-leads L2 Paxos, L6 prepared statements / streaming state) add more of the same gap | picked again: R8 |

Phase-1 candidate list, row OC-2 (status `retry (B7)`): "The Caffeine weigher counts key + value `unsharedHeapSize`
only and leaves out ≈ 90 B per entry (node, table, sketch), so a full key cache holds ≈ 2.14× and a counter cache
≈ 1.80× its cap at small keys."

**Phase-1 constraint and check.** `key_cache_size` and `counter_cache_size` (yaml, MiB; "auto" =
`min(max(1, 5 % of heap), 100)` and `min(max(1, 2.5 % of heap), 50)` MiB, `DatabaseDescriptor.java:814–836`, heap =
`Runtime.totalMemory()` at startup) → `CacheService.initKeyCache` / `initCounterCache` → `CaffeineCache.create(capacity)`
(`cache/CaffeineCache.java:61–70`): `maximumWeight(capacity)` with weigher `key.unsharedHeapSize() +
value.unsharedHeapSize()`, synchronous eviction (`ImmediateExecutor`), so K ≤ C always.

**Stage-4 / earlier phase-2 evidence (B7, 2026-11-11/12, apt149 x86, JDK 11.0.33, G1).** At 2 GiB heap and defaults,
8-byte keys: key cache C = 100 MiB, K = 100.00, U = 214.0 MiB (1,310,720 entries, 171 B heap per entry, 80 B weight);
counter cache C = 50 MiB, K = 50.00, U = 90.1 MiB (468,114 entries, 202 B / 112 B); 3/3 each, identical at 512 MiB
and 7,965 MiB. Under-filled control U/C 0.71 / 0.60 (3/3). Diagnostic weigher +104 B/entry
(`harness/b7-weigher-overhead.diff` of B7): K at cap, U 94.6 / 46.6 MiB (569,878 / 242,725 entries), U/C 0.95 / 0.93
(3/3). Invalidating the key cache keeps its table and sketch (≈ 24 MiB). No OOM with an all-defaults mixed
write/counter/read load (0/2 at 512 MiB, 0/1 at 2 GiB).

**The growing holder to stack on (S2, verified-OOM · deployment, true positive).** The coordinator's own CL=ONE local
writes queue on `MutationStage` (`StorageProxy.performLocally`, `StorageProxy.java:1674–1690`; unbounded stage queue;
expired local writes resubmitted as hints on the same stage, `StorageProxy.java:2633–2652`). Condition A (x86, V 2 GiB
coordinator + replica, R 8 GiB replica, RF 2 across DCs `c`/`r`, blob 11,000 B, 8 × 256 in flight, uncapped, 90 s):
heap OOM 3/3, ≈ 61.5 k queued `Mutation`s at ≈ 30 KiB heap each (≈ 1.8 GiB, ≈ 90 % of the heap), memtable K
143–167 MiB, caches empty. At 4 GiB: stage 1 alone 1/3; with both caches filled to their caps + a flush **2/3** (third
arm 99.1 % live) — n = 3, "suggestive, not established", tagged mixed candidate. S2 never isolated the cache gap from
the cache payload.

**What R8 adds.** S2's 4 GiB comparison changed two things at once (caches on, flush) and did not separate the counted
150 MiB from the uncounted ≈ 154 MiB. R8 fixes the holder's size with a **bounded burst** (exactly N writes) instead
of an open-ended one, finds the N where the shipped caches tip the node into OOM, and removes only the uncounted part
with B7's weigher (+104 B/entry) at the same N and the same counted cache weight.

**Terms of the retry row not used (with reason).** (a) Runtime-shrink table/sketch residue (+17.3 MB, OC-52): needs
`nodetool setcachecapacity`, a runtime change away from the shipped configuration; skipped to keep V6. (b) Paxos
weigher (L2; cap `min(1 % heap, 50 MiB)` = 20 MiB at 2 GiB, ≈ +24 MiB if 2.2×): needs an LWT fill and the B7 patch does
not cover it, so it would confound the intervention. (c) Prepared-statement / streaming-state weighers (L6, OC-17,
open in phase 1): small caps; not filled by this workload. (d) "More distinct keys": the caches are capped; 8-byte
keys already give the maximum entry count (1.31 M / 468 k) and the largest uncounted share.

**JIRA prior art** (read only; nothing posted). Survey
[`jira-oom-survey.csv`](../../../../capacity-enforcement-exp/cassandra/stage5-oom-clue-find/jira-oom-survey.csv)
(604 rows; filter `key cache|counter cache|weigh|caffeine|MutationStage|LocalMutationRunnable`) and
[`jira-prior-art-verified-cases.md`](../../../../capacity-enforcement-exp/cassandra/stage5-oom-clue-find/jira-prior-art-verified-cases.md)
§B7 and §S2:
- Weigher gap: **new**, not a regression. CASSANDRA-4315 / 4860 / 5549 / 10855 (Fixed) built the payload-only weigher;
  CASSANDRA-6709 (Later, 2014) acknowledges "100 + key length bytes" per key-cache entry as a density issue only;
  CASSANDRA-9738 (Won't Fix). No ticket ties it to the configured size or to an OOM.
- Local-write backlog: **known-open** core: CASSANDRA-19958 (*Needs Committer*, updated 2026-08-26; separates local
  hints from local mutations, does not bound the backlog); 6510 / 4753 (resubmit as hint, by design); 13213 (Open).
- The combination (cache under-count deciding a backlog OOM): not found.
- JIRA REST search, 2026-11-17 22:47 EST (`issues.apache.org/jira/rest/api/2/search`):
  `text ~ "weigher" AND created >= 2025-01-01` → 0; `text ~ "key cache" AND text ~ "overhead" AND created >= 2025-06-01`
  → 4 (20877, 21896, 21667, 21134; none about cache weight); `(text ~ "MutationStage" OR text ~ "LocalMutationRunnable")
  AND updated >= 2025-06-01` → 36 (top 15 read: 19958 still *Needs Committer*; 12689, 19564, 19785, 19784 other causes).
  Verdict: **new** (combination and gap), core holder **known-open** (19958). Not a known-fixed bug, so not a positive
  control.

## 2. Design solution (stage 1; frozen)

### 2.1 Mechanism and direction

Direction: **mixed** — an unprotected accumulation (S2's local-write backlog: C none, K none) plus a bypass by
accounting mismatch (B7: U > C with K ≤ C in both caches) in the same heap. Technique notes:
[`combo-playbook.md`](../../../combo-playbook.md) (stage 3 = accounting gap as the last layer on a stack measured near
its edge) and [`bypass-playbook.md`](../../../bypass-playbook.md) (protected path = weigher that charges the overhead).

A coordinator V that is also a replica accepts CL=ONE blob writes from a client that keeps 8 × 256 requests in flight.
Each write is forwarded to the other replica R and submitted locally as a `LocalMutationRunnable` on `Stage.MUTATION`
(`StorageProxy.java:1674–1690`, 32 threads, unbounded queue). R (8 GiB heap, data on tmpfs) acknowledges first, so the
client slot, the request and its `native_transport_max_request_data_in_flight` charge (released at response flush,
`CQLMessageHandler.java:500–507`) are freed while V's local write is still queued. With a burst of exactly N writes
sent as fast as V accepts them, V's backlog peaks near N − (writes applied during the burst) at ≈ 30 KiB of heap per
queued 11,000-byte write (S2: 29.8–30.5 KiB), then drains. Before the burst both caches are filled to their default
caps through CQL reads and counter updates (`CaffeineCache.java:61–70`: K = 100 + 50 MiB, physical ≈ 214 + 90 MiB).
The OOM edge in N therefore moves with the uncounted cache memory: ≈ 163 MiB ≈ 5.4 k queued writes at 2 GiB
(304 MiB shipped weigher vs 141 MiB with +104 B/entry). R8 places N just past the shipped weigher's edge and checks
that removing only the uncounted part (same K, same N) removes the OOM.

### 2.2 Protection map (fixed before readings; V's heap)

| Domain | Allocation, owner, release | Control C (contract) | K | U measured as | Lifetime / multiplicity |
|---|---|---|---|---|---|
| Local-write backlog (S2) | `Mutation` + `PartitionUpdate` + value `byte[]` decoded on `Native-Transport-Requests`, held by `StorageProxy$4` (`LocalMutationRunnable`) on `MutationStage` until a stage thread applies it; an expired one becomes a `HintRunnable` holding the same mutation | **none** (unprotected; implicit bound: offered − applied writes; here ≤ N by the client) | none (`MutationStage` PendingTasks is a gauge) | `Mutation` / `StorageProxy$4` counts in the OOM dump; `MutationStage` pending every 1 s (JMX); heap after GC (gc.log) | transient; one per accepted write not yet applied |
| Key cache | `KeyCacheKey` + key `byte[]` + `RowIndexEntry`, Caffeine `PSMW` node, `ConcurrentHashMap$Node`, table and frequency sketch | `key_cache_size` auto = 100 MiB at 2 GiB (`maximumWeight`) | JMX `Cache.KeyCache.Size` / `nodetool info` | class-histogram counts × per-object shallow size (B7 layout); fill-minus-invalidated heap after full GC; dump counts | standing; table/sketch never shrink |
| Counter cache | `CounterCacheKey` + `byte[]` + `ClockAndCount`, same container | `counter_cache_size` auto = 50 MiB | JMX `Cache.CounterCache.Size` | same | standing |
| Memtable (b6.t_blob, s2c) | slab regions + partition objects (`heap_buffers`) | `memtable_heap_space` = ¼ heap = 512 MiB; flush at `memtable_cleanup_threshold` = 1/(1+2) | `MemtableOnHeapSize` (JMX) | dump / sampler (S2 measured 143–167 MiB at the OOM, never at cap) | standing, recycled at flush |
| Client request bytes | decoded requests in transport | `native_transport_max_request_data_in_flight` = heap/10 = 204.8 MiB, per IP heap/40 | transport counter | — | released at response flush (before the local write runs) |
| Outbound to R | serialized copies in V's outbound queue | internode queue caps (on-wire, 4 + 128 + 512 MiB) | queue bytes | — (S2: 0–0.6 MiB pending) | transient |

Budget: V's Java heap, `-Xms = -Xmx = 2048 MiB`. Direct memory not claimed (heap OOM endpoint).

### 2.3 Configuration and budget audit

| Item | Value | Class |
|---|---|---|
| Node | `pc91` (UMass), x86_64, 2 × Xeon E5-2667 v2 3.3 GHz, 16 cores / 32 threads, NUMA node0 = even CPUs, node1 = odd; 125 GiB RAM; 8 GiB swap (unused; see start); `/mydata` 753 GB on a PERC H710P RAID volume (rotational), 713 GB free; Ubuntu 22.04, kernel 5.15, cgroup v2; OpenJDK 11.0.33; checked read-only 2026-11-17 22:44 EST: idle, no Java process | environment |
| Builds | **orig** `/mydata/r8/run-orig` = `cp -a /mydata/s4/cassandra-base` (no rebuild). **patched** `/mydata/r8/run-patched` = `cp -a` of the same + B7's `b7-weigher-overhead.diff` (`git apply`, then `ant jar`); patch adds `Long.getLong("b7.entry_overhead", 104L)` to the weigher of `CaffeineCache.create(long)`, whose only callers are the key and counter caches | supporting (patched build = intervention only) |
| JVM / GC | shipped `jvm-server.options` + `jvm11-server.options` (G1, `G1NewSizePercent=50`, `-XX:+HeapDumpOnOutOfMemoryError`, `OnOutOfMemoryError=kill -9 %p`); GC log via `cassandra-env.sh` to the instance's log dir; `MAX_HEAP_SIZE=2G` (V), `8G` (R), `HEAP_NEWSIZE=256M` (ignored by G1, set as in S2); `MaxDirectMemorySize` from `cassandra-env.sh` = 7,936 MiB on this 125 GiB node (record the resolved value from the command line) | environment / budget |
| Topology (one host) | V: `127.0.0.2`, dc `c`, rack `r1`, `initial_token: -9223372036854775808`, JMX 7199, CPUs `0-30:2` (NUMA node0, 8 cores / 16 threads = S2's apt140 size). R: `127.0.0.3`, dc `r`, `initial_token: 0`, JMX 7299 (`JMX_PORT` line of its `cassandra-env.sh` copy), CPUs `1-31:2`, data/commitlog/hints/saved_caches on tmpfs `/mydata/r8/rtmp` (16 GiB, `sudo mount -t tmpfs -o size=16g tmpfs /mydata/r8/rtmp`). V's directories on `/mydata/r8/inst/V/` (disk). Clients pinned to `1-31:2`. Keyspace `b6` `NetworkTopologyStrategy {c:1, r:1}` (= S2 condition A); keyspace `s2c` `{c:1}` (caches, V only) | environment (single-host form of S2 condition A; R on tmpfs keeps the replica faster than V as in A; disclosed) |
| yaml diffs (per instance, recorded as `yaml.diff`) | exactly S2 `ctl.sh gen`: `cluster_name: 'r8ring'`, `num_tokens: 1`, `listen_address`/`rpc_address` = the instance IP, `seeds: "127.0.0.2:7000"`, `endpoint_snitch: GossipingPropertyFileSnitch`, data/commitlog/hints/saved_caches dirs, `auto_bootstrap: false`, `initial_token` | environment |
| Constraints (V6) | all at the shipped default, resolved at 2 GiB: `key_cache_size` 100 MiB, `counter_cache_size` 50 MiB, `memtable_heap_space` 512 MiB, `memtable_allocation_type: heap_buffers`, `concurrent_writes` 32, `native_transport_max_request_data_in_flight` 204.8 MiB, `native_transport_max_threads` 128, `write_request_timeout` 2 s, internode queue capacities, hints on, `commitlog_sync: periodic` 10 s, key cache saving 4 h (no save in an arm) | default |
| Budget (V7) | heap 2,048 MiB (≥ 512 MiB: standing rule, 2 GiB ideal). This node would resolve 15,872 MiB heap / 7,936 MiB direct by itself; a 2 GiB heap is a value a deployment could run (S2 A, B7 at 2 GiB). No container/cgroup memory limit: the systemd scope sets only `MemorySwapMax=0` | acceptable (no review needed) |
| Workload | as S2 A: blob 11,000 B random-filled once (`new Random(1)`), `INSERT INTO b6.t_blob (pk int, b blob)`, 8 driver sessions × 256 in flight, all to V (whitelist), CL=ONE, protocol V4, **no rate cap**, **exactly N writes in total** (the dial) | experimental variable |
| Cache fill | B7/S2 `CacheFill`: 8-byte SplitMix64-scrambled blob keys; `insert kv 0..1,600,000` → `nodetool flush s2c` → `nodetool compact s2c kv` → `read kv 0..1,500,000` (populates key cache) → `counter ctr 0..550,000` (populates counter cache) → `nodetool flush s2c`; concurrency 256 | workload |
| Instrumentation | S2Poll (one JVM, `-Xmx48m`, JMX 1 s) on V; pre-burst `jcmd GC.class_histogram` (forced full GC, before the load); post-window histogram on survivors (after the endpoint window); heap dump on OOM (shipped option); gc.log | disclosed |

### 2.4 Ceiling arithmetic (V, 2 GiB; before readings)

| Term | Shipped weigher (T) | +104 B weigher (P) | Caches invalidated (E) | Source |
|---|---|---|---|---|
| Baseline (schema, metadata, buffers) | ≈ 150 | ≈ 150 | ≈ 150 | S2/B7 2 GiB arms (estimate; measured per arm by the pre-burst histogram) |
| Key cache U (K = C = 100 MiB) | 214 | 94.6 | ≈ 24 (table + sketch kept) | B7 §3.1, §3.5, §3.1 cross-check |
| Counter cache U (K = C = 50 MiB) | 90 | 46.6 | ≈ 8 | B7 |
| Memtable at the peak | ≈ 160 | ≈ 160 | ≈ 160 | S2 (143–167 MiB) |
| **Sum without backlog** | **≈ 614** | **≈ 451** | **≈ 342** | |
| Room for backlog (2,048 − sum) | ≈ 1,434 MiB ≈ 48.9 k writes | ≈ 1,597 MiB ≈ 54.5 k | ≈ 1,706 MiB ≈ 58.2 k | ÷ 30 KiB per queued write |

Contract capacities alone: 512 + 100 + 50 + 204.8 = 867 MiB < 2,048 MiB, so no all-pools-full convergence; the
OOM needs the uncapped backlog (S2) and, at the chosen N, the uncounted cache memory (B7). Edge window between T and P:
≈ 5.6 k queued writes ≈ 163 MiB (8 % of the heap). Applied during the burst: S2 measured V's apply ≈ 3.3 k/s against
13–17 k/s offered, so ≈ 78 % of N queues. **Predicted edge for T: N ≈ 63 k (48.9 k / 0.78); for P ≈ 70 k;
for E ≈ 75 k.** pc91's faster CPU may raise V's apply rate; the calibration (§2.6) measures the edge directly.

### 2.5 Harness (stage 2 builds it; copy, do not re-derive)

Node layout: `/mydata/r8/{h,cls,run-orig,run-patched,inst,rtmp,runs,dumps}`. Repo copy: `harness/` in this folder;
logs on the node `/mydata/r8/runs/<arm>/`, excerpts in `logs/`.

| File | Built from | Change |
|---|---|---|
| `ctl.sh` | S2 run-1 `harness/ctl.sh` | one host; roles `V`, `R` as in §2.3 (IP, dc, token, dirs, JMX port, CPU list, build = `$BUILD` for V: `orig`/`patched`, always `orig` for R); start = `taskset -c <cpus> systemd-run --user --scope -p MemorySwapMax=0 bash -c 'ulimit -n 100000; CASSANDRA_CONF=… CASSANDRA_LOG_DIR=… CASSANDRA_HEAPDUMP_DIR=<inst>/dumps MAX_HEAP_SIZE=… HEAP_NEWSIZE=256M <build>/bin/cassandra -p <inst>/cass.pid'` (if `systemd-run --user` fails, start without the scope and record `VmSwap` of V at the end of every arm; it must be 0); stop by PID (30 s, then `kill -9`) |
| `S2Load.java` | S2 run-1 `harness/S2Load.java` | (1) `-Dtotal=N`: one shared `AtomicLong tickets`; loop condition `System.nanoTime() < end && tickets.getAndIncrement() < total`; `seconds` stays as a cap (120); (2) `schema` also creates `s2c` `{'class':'NetworkTopologyStrategy','c':1}`, `s2c.kv (k blob PRIMARY KEY, v int)`, `s2c.ctr (k blob PRIMARY KEY, c counter)`; (3) contact host and whitelist `127.0.0.2`; print `FINAL sent= ok= err=` and the first and last ok timestamps |
| `S2CacheFill.java` | S2 `harness/S2CacheFill.java` | none (`-Dhost=127.0.0.2 -Dks=s2c`) |
| `S2Poll.java` | S2 run-2 `harness-run2/S2Poll.java` | interval 1,000 ms; add `Cache` metrics `KeyCache`/`CounterCache` `Size` and `Entries` (`org.apache.cassandra.metrics:type=Cache,scope=KeyCache,name=Size` etc.); cgroup arg may be `-` |
| `sample.sh` | S2 run-2 `harness-run2/sample.sh` | paths; one S2Poll on V only, `nice -n 10`, pinned to `1-31:2` |
| `client.sh` | S2 run-2 `harness-run2/client.sh` | classpath from `/mydata/r8/run-orig`; `taskset -c 1-31:2`; `load` passes `-Dtotal=$N`; `fill` as S2 run 1 |
| `arm.sh` | S2 run-1 `harness/arm.sh` + run-2 `collect.sh` | arm procedure below |
| `gcpeak.sh`, `gcwin.py`, `hprofhist.py`, `logback-load.xml` | S2 harness | none |
| `b7-weigher-overhead.diff` | B7 `harness/` | none |
| `table.py` | new | one line per arm from `arm.log`, `poll.log`, histograms, `outcome.txt`, `dump-hist.txt` (columns of §3) |

**Arm procedure** `arm.sh <name> <T|P|E> <N>` (T: build orig, caches kept; P: build patched, caches kept; E: build
orig, caches invalidated; V heap 2G unless a 4 GiB probe):

1. Clean slate: kill any `S2Load`/`S2CacheFill`/`S2Poll` started by the harness; `ctl.sh stop V`, `stop R`; check no
   `CassandraDaemon` remains; `rm -rf /mydata/r8/inst/V /mydata/r8/rtmp/R /mydata/r8/runs/<name>`.
2. `ctl.sh gen V 2G` (`BUILD` per arm type), `gen R 8G`; start V, wait for `127.0.0.2:9042`; start R; wait until
   `nodetool -h 127.0.0.1 -p 7199 status` shows `UN` = 2 (≤ 4 min, else `RINGFAIL`, arm void).
3. Record the V command line (`ps -o args`), `taskset -cp` of both PIDs, resolved `-Xmx`, `MaxDirectMemorySize`, and
   the startup lines `KeyCache`/`CounterCache` capacity from `system.log`.
4. Start `sample.sh` (poll.log, 1 s).
5. Schema (`client.sh load schema 127.0.0.2`); cache fill (§2.3, every arm type including E).
6. Validity of the fill: `nodetool info` → key cache size ≥ 99.0 MiB and counter cache size ≥ 49.5 MiB (capacity 100
   / 50 MiB). If short, read keys 1,500,000..1,600,000 once more; still short → arm void (`FILLFAIL`).
7. E only: `nodetool invalidatekeycache`, `nodetool invalidatecountercache`; check sizes 0.
8. Pre-burst reading: `nodetool info` (Key/Counter Cache lines), `nodetool tablestats s2c b6` memtable lines,
   `jcmd <V> GC.class_histogram > hist-pre.txt` (forced full GC: the post-fill live heap, the "component alone"
   reading), then 10 s idle.
9. Burst: `client.sh load run blob 11000 256 120 0 <127.0.0.2 × 8>` with `N`; T0 = start. Wait for the client to exit
   (≤ 150 s; it stops after N sends and their responses or errors).
10. Observation: 180 s after the client exits. If V is alive and the last poll line has `mut_pending` > 1,000, extend
    once by 180 s.
11. Collect (S2 run-2 `collect.sh` logic): wait while a dump is being written; record `V_ALIVE`/`V_DEAD`; if alive,
    `jcmd GC.class_histogram > hist-post.txt` (after the window; diagnostic) and `nodetool info`; copy gc.log*,
    system.log, launch.log, `yaml.diff`; `gcpeak.sh . 2048` and `gcwin.py .` into `outcome.txt`; move any dump to
    `/mydata/r8/dumps/<name>.hprof`; stop V and R; record R's `gcpeak` line.
12. `table.py` row; append to `/mydata/r8/runs/batch.log`.

**Endpoint, per arm.** **Heap OOM** = V dead and at least one of: `HeapDumper` or `ReportJavaOutOfMemory` safepoint in
V's gc.log, `java.lang.OutOfMemoryError` in system.log/launch.log, a dump written by `HeapDumpOnOutOfMemoryError`.
**Survive** = V alive at the end of the (extended) window. V dead without OOM evidence = **void** (investigate, do not
count). GC service loss (protocol default, `gcwin.py`) is recorded, not the endpoint.

**Shakedown (not a reading, ≤ 8 min, before calibration).** `arm.sh shake T 2000` with the fill reduced to 20 k
inserts/reads/counters (env `FILL_SMALL=1`): checks ports, ring, schema, sampler columns, `FINAL` line, collection,
cleanup. Fix the harness, never the design.

### 2.6 Calibration (boundary search on the dial N; T arms only)

1. `cal1` = T at **N = 65,000** (≈ the predicted edge + 3 %). Reachability check on its poll.log: max `mut_pending`
   ≥ 10,000 means the backlog holder is reproduced on pc91. If < 10,000: amendment F1 (written before the next
   reading): `SESS=16` (16 × 256 in flight) for all later arms; repeat cal1. If still < 10,000: stop; verdict
   `retry` (holder not reproduced on this node; the next design should use the aarch64 set where S2 run 2
   reproduced it).
2. Step: T survives → next N = 1.25 × N; T OOMs → next N = 0.8 × N, until one surviving N_s and one failing N_f are
   known; then bisect at √(N_s · N_f) (rounded to 500) until N_f / N_s ≤ 1.10.
3. At most **4 calibration arms** (5 if the shakedown ended before 23:50). If no failing N is found within them
   (N ≤ 127 k), stop: verdict `retry` with the measured peaks. If a bracket exists but is wider than 1.10, use it.
4. **N\* = 1.03 × N_f** (smallest failing N in calibration), rounded to 500. Write N\* into §3 as a dated amendment
   "N\* fixed" before the first counted arm. The predicted P edge is ≈ 1.10 × the T edge, so N\* leaves ≈ 7 % below it.

### 2.7 Counted arms, predictions, controls and intervention

Interleaved rounds from clean starts at N\* (2 GiB): `T-r1, P-r1, E-r1, T-r2, P-r2, E-r2, T-r3, P-r3, E-r3`.

| Arm | Role | Prediction (before readings) |
|---|---|---|
| T (orig, caches at caps) ×3 | endpoint (V1) | heap OOM **3/3** within 240 s after the burst starts; dump: ≈ 45–52 k queued `Mutation` (= `StorageProxy$4` ± hint runnables), `PSMW` ≈ 1.78 M (1,310,720 + 468,114), `KeyCacheKey` 1.31 M, `CounterCacheKey` 468 k; pre-burst live heap ≈ 450–500 MiB |
| P (patched weigher, caches at caps by K) ×3 | intervention (V4): removes only the uncounted ≈ 163 MiB | survive **3/3**; pre-burst live ≈ 160 MiB below T's; `PSMW` ≈ 0.81 M (569,878 + 242,725); max `mut_pending` within 10 % of T's; max heap after any GC ≤ 97 % |
| E (orig, caches invalidated) ×3 | matched control (V2): holder alone at the same N | survive **3/3**; pre-burst live ≈ 280 MiB below T's; max heap after any GC ≤ 95 % |

Matched across arms: build version and yaml (P differs only in the weigher), heap, topology, CPU pinning, fill
workload and data state (E differs only in the two invalidations), burst size and client. Throughput: `FINAL ok` and
burst duration per arm (an arm whose client completed < 90 % of N is reported; the backlog depends on accepted writes).

**Decision rules (frozen).**
- T OOM 3/3, P 0/3, E 0/3 → proposed `verified-OOM · deployment`, mixed (unprotected accumulation + B7 accounting
  gap) → verdict **true positive**.
- T 2/3 or P 1/3 or E 1/3 → if the clock allows (rule below), two more rounds of T and P (and E if it failed once);
  report n/N. V1 needs ≥ 3 OOMs; V4 needs P to survive ≥ 3 runs with no P OOM at N\*. Otherwise **retry** (state the
  rates; next design: more uncounted entries or a steadier holder).
- T ≤ 1/3 at N\* → **retry** (edge not reproducible at this N).
- P OOMs ≥ 2/3 at N\* → the gap does not decide the OOM at N\*: **retry** (the backlog alone is too close to the edge;
  record T and P peaks).
- If the clock stops the counted rounds before 3 × T, P and E are complete → **retry** (incomplete), with what ran.

**Budget search (only if ≥ 25 min remain before the 01:55 last-arm rule after the counted rounds).** One T and one
P at heap 4 GiB (V `gen V 4G`; caches still 100 / 50 MiB) with N₄ = 2.05 × N\* (rounded to 500); a boundary probe
(n = 1), not a verified condition. Otherwise state: largest failing budget searched = 2 GiB only (S2 4 GiB stage-2:
2/3 as a reference).

### 2.8 Instruments (U independent of K)

- **Backlog U:** `Mutation`, `StorageProxy$4`, `WriteResponseHandler`, `byte[]` in the OOM dump (`hprofhist.py`);
  `mut_pending` / `mut_done` every 1 s (JMX, no forced GC); per-queued-write heap = `byte[]` ÷ `Mutation` in the dump.
- **Cache U:** class counts × shallow sizes from `hist-pre.txt` (forced full GC before the load): `PSMW`,
  `KeyCacheKey`, `CounterCacheKey`, `ClockAndCount`, `RowIndexEntry` (big), plus the cache `byte[]` share by B7's
  per-entry layout; cross-check: pre-burst live heap T − E (≈ 304 − 32 MiB) and T − P (≈ 163 MiB). K from JMX.
- **Heap:** gc.log (`gcpeak.sh`: max after any pause, max after Full GC, Full GC count; `gcwin.py`: worst-60 s STW,
  service loss, `HeapDumper` / `ReportJavaOutOfMemory` marks); MemoryMXBean used every 1 s.
- **Initiating failure (V5):** gc.log safepoint marks; first `OutOfMemoryError` with its thread from system.log or
  launch.log if written; the dump histogram (parse one dump per OOM counted arm after the last arm, `nice -n 19`,
  pinned to `1-31:2`; if time is short parse T-r1 only and keep the others on the node).
- **Validation:** sampler overhead = one 48 MiB JVM on the other NUMA node; the forced GCs happen only before the burst
  and after the window.

### 2.9 Time plan and stopping budget (America/New_York, 2026-11-17/18)

Arm length estimate: start 1.5 min, schema + fill ≈ 3 min, histograms ≈ 0.5 min, burst ≤ 0.5 min, window 3 min (+3),
collect 0.7 min ≈ **9 min** (12 with an extension).

| Window | Work |
|---|---|
| start (≈ 23:20) – 23:55 | read this file, check the freeze hash and pc91 (`ps`, `free`, `df`), builds (`cp -a` ×2, `git apply`, `ant jar` in run-patched only), mount tmpfs, write and compile the harness, shakedown |
| 23:55 – 00:40 | calibration, ≤ 4 arms |
| 00:40 – 02:00 | 9 counted arms (≈ 81 min); extra rounds or the 4 GiB probe only if they start by **01:55** |
| ≤ 02:15 | dump parsing; every process started by the run stopped (`CassandraDaemon` ×2, S2Poll, clients); `sudo umount /mydata/r8/rtmp`; `/mydata/r8` kept (logs, ≤ 10 dumps ≈ 2.2 GB each) |
| ≤ 02:30 | §3, §4 and the write-backs (stage 2 step 5) |

Hard limits: no arm starts after 01:55; whatever is running at 02:15 is stopped; ≤ 18 arm executions in total;
no escalation after an OOM beyond the planned arms. If stage 2 starts after 23:40, calibration is capped at 3 arms; if
it starts after 00:10, the counted rounds run T and P first in each round and E last, and an incomplete set is
`retry` (§2.7). Resources: peak ≈ 2 + 8 GiB heaps + ≈ 3 GiB off-heap + clients 6 GiB + tmpfs ≤ 16 GiB ≪ 125 GiB;
CPUs split by NUMA node; disk ≤ 40 GB of 713 GB.

### 2.10 Limits known before the run

- One host: R shares the machine (other NUMA node) and runs on tmpfs; S2 A had separate machines. The backlog
  depends on V's apply rate on this CPU/disk; the calibration absorbs that, the reachability check guards it.
- The edge window is ≈ 8 % of the heap; run-to-run variance of the applied share during the burst (S2: apply rate
  fell under GC) can blur 3/3 vs 0/3; the decision rules report n/N rather than re-tuning N after counted readings.
- The intervention charges 104 B per entry, an upper bound for this JVM layout (B7: U/C 0.93–0.95), so it removes
  slightly more than the gap; the counted weight K is the same (100 / 50 MiB) in T and P.

`sha256 of §1–§2 at freeze: c2fbddeb68958f09dc468742f82d86fb1021b9c29eae8e86bee01150f183d409` (bytes from the line `## 1. Candidate` through the line before this one, as stored in git) · amendments after the freeze: A1–A3 in §3.0 (stage 2, 2026-11-17).

## 3. Runs (stage 2)

Stage 2: phase-2 OOM agent, stage 2 (Claude Opus 5.5, fresh workflow subagent), 2026-11-17 22:52 EST onward.
Freeze hash checked at 22:53: the bytes from `## 1. Candidate` to the line before the hash line hash to
`c2fbddeb…3d409`, equal to the frozen value.

### 3.0 Amendments (dated, written before the readings they affect)

- **A1 (2026-11-17 22:55, before any reading): node paths.** The workflow put this run in `/mydata/s4/r8-w1`, so every
  `/mydata/r8/...` path of §2.3/§2.5 is `/mydata/s4/r8-w1/...` (same layout: `h, cls, run-orig, run-patched, inst, rtmp,
  runs, dumps`). No other change.
- **A2 (2026-11-17 22:57, from the shakedown, not a reading): resolved direct limit.** `cassandra-env.sh` resolves
  `-XX:MaxDirectMemorySize=15872M` on pc91 (not 7,936 MiB as §2.3 expected). Direct memory is not claimed (heap
  endpoint); recorded only.
- **A3 (2026-11-17 23:07, after cal1, before the next reading): F1 applied.** cal1's reachability reading was max
  `mut_pending` 9,724 (< 10,000), so per §2.6 step 1 all later arms run with `SESS=16` (16 × 256 in flight) and cal1 is
  repeated as `cal1b` (T, N = 65,000).

### 3.1 Environment (as run)

pc91 (UMass), x86_64, 32 hardware threads, 125 GiB RAM, 8 GiB swap (unused: both JVMs in user scopes with
`MemorySwapMax=0`, `memory.max=max`; `VmSwap 0 kB` at the end of every arm), Ubuntu 22.04, kernel 5.15, cgroup v2,
OpenJDK 11.0.33, G1. Checked 22:53: idle, no Java process. `sudo loginctl enable-linger jason92` (user scopes survive
the ssh session). Builds: `run-orig` = `cp -a /mydata/s4/cassandra-base` (git `6a75178`, yaml md5 `714ee9bf…`, jar md5
`a2259a80…`); `run-patched` = the same + `b7-weigher-overhead.diff` (`git apply`, `ant jar` compiled 1 file; jar md5
`41b510fc…`, contains `b7.entry_overhead`; never used, see 3.3). tmpfs 16 GiB on `/mydata/s4/r8-w1/rtmp` for R
(unmounted at the end). V resolved: `-Xms2G -Xmx2G`, `-XX:+UseG1GC`, `-XX:MaxDirectMemorySize=15872M` (A2), key
cache capacity 100 MiB, counter cache 50 MiB (system.log), CPUs 0,2,…,30; R CPUs 1,3,…,31; clients and sampler
pinned to 1-31:2. yaml diffs = §2.3 only (`logs/*/V-yaml.diff`; R also `JMX_PORT="7299"` in its `cassandra-env.sh`).
Harness: [`harness/`](harness/) (`ctl.sh`, `arm.sh`, `batch.sh`, `client.sh`, `sample.sh`, `S2Load.java` (+`-Dtotal`),
`S2Poll.java` (+cache metrics), `S2CacheFill.java`, `gcpeak.sh`, `gcwin.py`, `hprofhist.py`, `table.py`, the B7 diff).
Full logs on pc91: `/mydata/s4/r8-w1/runs/<arm>/` (gc.log, system.log, poll.log at 1 s, load.log, histograms);
excerpts in [`logs/`](logs/).

### 3.2 Arms

Shakedown (`shake`, `FILL_SMALL=1`, N = 2,000, 22:56–23:01): ports, ring (UN = 2 in 25 s), schema, sampler columns,
`FINAL` line, collection and cleanup all worked. One harness fix before calibration (not a design change): the
OOM-line count matched the JVM's `CompileCommand … forceHeapSpaceOomMaybe(Ljava/lang/OutOfMemoryError;)` line in
launch.log; `arm.sh` now skips `CompileCommand` lines.

| Arm | Type | N | V outcome | client ok / err (ok span) | pre-burst live heap MiB (forced-GC histogram) | key / counter K pre-burst | Caffeine nodes / KeyCacheKey / CounterCacheKey | **max `mut_pending`** (1 s) | max heap used MiB (1 s) | max after any GC MiB (%) | Full GCs / max after Full GC MiB | hints created | worst-60 s STW |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `cal1` (SESS 8, 23:01–23:07) | T | 65,000 | survive | 65,000 / 0 (3.8 s; 13 k/s) | 401 | 100 / 50 MiB | 1,778,838 / 1,310,720 / 468,114 | **9,724** | 1,901 | 2,028 (99.0 %) | 6 / 1,240 (60.5 %) | 6,392 | 5 % |
| `cal1b` (SESS 16, A3, 23:07–23:13) | T | 65,000 | survive | 65,000 / 0 (5.0 s; 13 k/s) | 397 | 100 / 50 MiB | 1,778,838 / 1,310,720 / 468,114 | **2,684** | 1,909 | 2,028 (99.0 %) | 6 / 1,257 (61.4 %) | 9,918 | 4 % |

Readings (sources: `logs/cal1*/arm.log`, `poll-burst.txt`, `gc-full.txt`, `hist-pre-top.txt`, `outcome.txt`):

- **Cache fill (both arms).** Fill reached the caps exactly as in B7: key cache 1,310,720 entries at K = 100 MiB,
  counter cache 468,114 entries at K = 50 MiB (JMX `Size` 104,857,600 / 52,428,768 B). U from the forced-GC histogram
  before the burst (shallow sizes): `PSMW` 1,778,838 × 40 B = 67.9 MiB, `ConcurrentHashMap$Node` 55.4 MiB (1.82 M,
  ≈ 1.78 M of them cache nodes), `KeyCacheKey` 40.0 MiB, `RowIndexEntry` 30.0 MiB, `CounterCacheKey` 14.3 MiB,
  `ClockAndCount` 14.3 MiB, `ConcurrentHashMap$Node[]` 12.3 MiB, key `byte[]` ≈ 1.78 M × 24 B ≈ 40.7 MiB → ≈ 275 MiB in
  these classes (plus the frequency sketches in `long[]`), against K = 150 MiB. The B7 gap is reproduced on pc91
  (≈ 1.8×). Pre-burst live heap 397–401 MiB.
- **Backlog holder (the design's growing layer): not reproduced.** V accepted the 65,000 writes in 3.8–5.0 s
  (≈ 13 k/s) and applied them almost as fast: `MutationStage` pending peaked at 9,724 (8 sessions) and 2,684
  (16 sessions), `mut_done` rose by ≈ 47 k / 55 k within ~5 s, and the local writes that waited past the 2 s write
  timeout were turned into hints (6,392 / 9,918; `hints_created`) instead of staying queued. S2 condition A on apt140
  queued ≈ 61.5 k mutations at an apply rate of ≈ 3.3 k/s; pc91's V applies ≈ 4× faster.
- **Heap.** The peak came from the memtable and in-flight request/response objects during the 5 s burst, not from a
  standing backlog: memtable on-heap reached 175 MiB; G1 hit evacuation failures (young pauses ending at 1.9–2.0 GiB)
  and ran 3–4 Full GCs right after the burst that left 981–1,257 MiB live (≤ 61.4 % of the heap). The worst 60 s
  window had 4–5 % STW. V survived with ≈ 790 MiB headroom after Full GC; R (8 GiB) max 808 MiB after any GC.

### 3.3 Stop under §2.6 step 1

§2.6 step 1 (frozen): "max `mut_pending` ≥ 10,000 means the backlog holder is reproduced on pc91. If < 10,000:
amendment F1 … `SESS=16` …; repeat cal1. If still < 10,000: stop; verdict `retry`." cal1 = 9,724, cal1b (F1) = 2,684.
The run stopped at 23:13 EST after two calibration arms (plus the shakedown); no counted arm (T/P/E at N\*) ran, the
patched build was not started, no N\* was fixed. Everything started by the run was stopped (both Cassandra JVMs by
PID and scope, the sampler and clients; no Java process of the user left on pc91 at 23:14), tmpfs unmounted.
Left on pc91: `/mydata/s4/r8-w1/` (`run-orig`, `run-patched` builds, `runs/{shake,cal1,cal1b}` full logs and
histograms, `inst/` of the last arm; ≈ 1.5 GB, no heap dumps).


## 4. Conclusion (stage 2)

**Verdict: retry.** Protocol status: `candidate` (V1–V5 not reached; no endpoint arm ran). Detail: B7's accounting gap
reproduced on pc91 (U ≈ 275 MiB in the cache classes for K = 150 MiB, same entry counts as B7), but the design's
growing holder, S2's local-write backlog on `MutationStage`, did not form on this node, so the frozen stop rule of
§2.6 step 1 applied before any counted arm.

**Reason.** The design needed V to queue tens of thousands of local writes so the uncounted ≈ 125–163 MiB of cache
memory would decide an OOM at the edge. On pc91, a 65,000-write burst of 11,000 B blobs (CL=ONE, 8 × 256 and then
16 × 256 in flight) was accepted at ≈ 13 k/s and applied almost as fast: max `mut_pending` 9,724 and 2,684 (< 10,000,
the frozen reachability threshold), writes waiting past 2 s became hints (6,392 / 9,918), and with both caches full
the heap after Full GC peaked at 1,240–1,257 MiB of 2,048 (≤ 61 %), with ≈ 790 MiB left. Neither OOM nor service loss
(worst 60 s: 4–5 % STW). This is not a false positive: the design did not reach its target load (the backlog), the
P/E arms and the boundary search never ran, so nothing shows the endpoint cannot be reached.

**What a better design should change.**
1. Reproduce the holder first, on hardware where it forms: S2 run 2's aarch64 G1 ring (all 2 GiB, RF=3, no faster
   replica needed; heap OOM 3/3) or S2 condition A's apt140/apt149 pair (V apply ≈ 3.3 k/s). On a fast x86 host V
   applies ≈ 13 k/s and the local backlog converts to hints instead of queuing.
2. Calibrate the holder alone (caches invalidated, the E arm) before adding the caches: find the backlog size and N
   where E reaches ≥ 90 % live, then place T/P/E at that N; a 1 s `mut_pending` sample plus `hints_created` both
   measure the holder.
3. If an x86 node must be used, a sustained (time-bounded, uncapped) load rather than a fixed burst, with V's
   commitlog and data on a separate slower device or a smaller V CPU set, is the knob that lowers V's apply rate;
   these are environment choices and must be disclosed and kept equal across T, P and E.
4. Keep the cache fill as is (it reaches K = 100 / 50 MiB with 1.78 M entries in ≈ 35 s on this node).
