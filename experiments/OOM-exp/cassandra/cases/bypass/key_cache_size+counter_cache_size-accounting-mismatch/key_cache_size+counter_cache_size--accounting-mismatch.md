# key_cache_size + counter_cache_size — Caffeine cache weight omits per-entry container memory

**Direction:** bypass · accounting mismatch (U > C, K ≤ C). **Regime:** default capacities, deployment budgets
(512 MiB, 2 GiB, auto-resolved 7965 MiB heap). **Source:** Cassandra 5.0.9 (`~/cassandra-c1`, git `7cb9cc77…`,
Caffeine 3.1.8), single node `apt149`. **Lead:** campaign-plan B7 (`source: R3/R4 recheck`). **Run:** B7 run 1,
2026-11-11/12 (design [`design/B7-design.md`](design/B7-design.md), written before any reading).
**Status (both conditions):** `verified-gap · overshoot · deployment` (filed 2026-11-12 in `bypass/`; V7 by the
standing budget rule of 2026-11-11, all budgets ≥ 512 MiB). OOM at defaults: no failing budget found (0/3).

## Summary

- **Conclusion:** with the shipped `cassandra.yaml` (both caches "auto"), filling the key cache or the counter cache
  alone to its cap through ordinary CQL reads / counter updates leaves it holding far more heap than its configured
  size, permanently: key cache **2.14 ×** its capacity (214 MiB of heap at the default 100 MiB), counter cache
  **1.80 ×** (90 MiB at 50 MiB), with the cache's own counter reading exactly its capacity. Same ratio at 512 MiB,
  2 GiB and the node's auto heap (7965 MiB), 3/3 runs each, unchanged after an idle minute and under churn. The ratio
  falls with entry size (512-byte keys: 1.15 × both) but stays above 1 at every size tested. This is a bounded
  overshoot (≤ ≈ 115 MiB key + 40 MiB counter beyond contract at defaults, ≈ 7.5 % of a 2 GiB heap), not an OOM:
  an all-defaults concurrent write / counter / read workload did **not** OOM at 512 MiB (0/2) or 2048 MiB (0/1),
  so no failing budget was found (§3.6).
- **Root cause:** both caches are `CaffeineCache` with weigher `key.unsharedHeapSize() + value.unsharedHeapSize()`.
  That counts the key and value objects exactly, but not the ≈ 90 B per entry the container needs: Caffeine's node
  (`PSMW`, 40 B), the `ConcurrentHashMap$Node` (32 B), the hash-table slot and the frequency-sketch slot (power-of-
  two arrays, ≈ 18 B/entry at the cap). For small entries (key cache 80 B, counter cache 112 B of weight) that is
  +114 % / +80 %. `cassandra.yaml` documents both settings as "Maximum size of the … cache **in memory**" and the
  Cache metrics as `Capacity`/`Size` "in bytes", so the contract is memory, not payload: a documented-unit mismatch,
  an implementation defect of the weigher (not a soft-limit exception). A diagnostic weigher that adds 104 B per
  entry brings U to 0.93–0.95 × C (3/3 each), at the cost of caching 48 % (counter) / 57 % (key) fewer entries.

## 1. Constraint and capacity

**Pinned source** (`systems/cassandra/source/`, read-only):

- `service/CacheService.java` `initKeyCache()` (l. 119–136) and `initCounterCache()` (l. 172–): capacity
  `getKeyCacheSizeInMiB() × 2^20` / `getCounterCacheSizeInMiB() × 2^20` → `CaffeineCache.create(capacity)`; the only
  two callers of `create(long)`. A stale comment in `initKeyCache` still reads "as values are constant size we can use
  singleton weigher where 48 = 40 bytes (average size of the key) + 8 bytes (size of value)".
- `cache/CaffeineCache.java` `create(long)` (l. 61–70): `Caffeine.newBuilder().maximumWeight(capacity)
  .weigher((k, v) -> k.unsharedHeapSize() + v.unsharedHeapSize()).executor(ImmediateExecutor.INSTANCE)`.
- Weights: `KeyCacheKey.unsharedHeapSize()` = EMPTY_SIZE + `sizeOfArray(key)` (key is a copied `byte[]`);
  `big.RowIndexEntry` = EMPTY_SIZE (unindexed partitions); `CounterCacheKey` = EMPTY_SIZE + `sizeOfArray(partitionKey)`
  + `sizeOfArray(cellName)`; `ClockAndCount` = EMPTY_SIZE. Measured: these equal the shallow sizes of the objects in
  the dumps (counter, L = 8: 32 + 24 + 24 + 32 = 112 B; key: 32 + 24 + 24 = 80 B).
- Defaults (`config/DatabaseDescriptor.java` l. 815–836, `Runtime.totalMemory()` at startup, -Xms = -Xmx):
  key `min(max(1, 5 % heap), 100)` MiB, counter `min(max(1, 2.5 % heap), 50)` MiB, matching the yaml comments. Resolved
  and confirmed from the startup log / JMX `Capacity`: 512 MiB heap → 25 / 12 MiB; 2048 MiB → 100 / 50 MiB; 7965 MiB
  (auto) → 100 / 50 MiB.

**Documented contract.** `conf/cassandra.yaml`: "Maximum size of the key cache in memory." / "Maximum size of the
counter cache in memory." (counter: "Only the local (clock, count) tuple of a counter cell is kept in memory … so it's
relatively cheap"). `doc/modules/cassandra/pages/managing/operating/metrics.adoc`, Cache Metrics: `Capacity` "Cache
capacity in bytes", `Size` "Total size of occupied cache, in bytes". No text says the size is entry payload only or
allows overshoot. **C = configured capacity in bytes of heap.** Caffeine evicts synchronously
(`ImmediateExecutor`), so K stays ≤ C (measured K = C to 0.01 MiB at the cap). CASSANDRA-10855 (move to Caffeine)
discusses no per-entry overhead accounting.

**Protection map** (design §2, fixed before readings):

| Domain | Control (C) | K | U measured as | Lifetime |
|---|---|---|---|---|
| Key cache | `key_cache_size` (auto): Caffeine `maximumWeight`, weigher key+value `unsharedHeapSize` | Caffeine `weightedSize` (dump), JMX `Cache.Size` | objects exclusively reachable from the cache's `BoundedLocalCache` in a live heap dump (`hprof_holders.py`) | standing; W-TinyLFU eviction at the cap; table and sketch never shrink |
| Counter cache | `counter_cache_size` (auto): same | same | same | same |

Scope: one cache per process; no aggregate check of caches + memtables against the heap. Not counted, per entry:
`PSMW` node 40 B, `ConcurrentHashMap$Node` 32 B, table slot (4 B refs, power of two ≥ n/0.75) and `FrequencySketch`
`long[]` (power of two ≥ n; allocated only once the weight reaches half the maximum).

**Labels.** Capacity: **default** (shipped yaml, verified unchanged by `cmp` in every arm). Budget: explicit
deployment (512, 2048 MiB) and automatic/resolved (7965 MiB). Interpretation: **suspected implementation defect /
documented-unit mismatch** (the weigher measures payload while the documented unit is memory); not an intentional
soft limit.

## 2. Verification solution

Design: [`design/B7-design.md`](design/B7-design.md) (2026-11-11 19:40 MST, before readings). Harness:
[`harness/`](harness/) — `b7-run.sh` (one arm = clean start, schema, fill, readings, stop), `CacheFill.java`
(CQL client on the driver in Cassandra's `lib/`), `run-batch.sh`, `arms.txt`, `table.py`, `hprof_holders.py` (R4's
parser, unchanged), `b7-weigher-overhead.diff` (diagnostic patch).

**Configuration audit.** apt149: Xeon E5-2450 2.1 GHz, 8 cores / 16 threads, 15.5 GiB RAM, 8 GiB swap, Ubuntu
22.04.2, kernel 5.15.0-198, cgroup v2 (no limit used), OpenJDK 11.0.33, G1 per shipped `jvm11-server.options`.
Build `/mydata/b7/run-orig` (copy of `~/cassandra-c1`); diagnostic build `/mydata/b7/run-patched` (same + patch,
`ant jar`, 1 file recompiled). Shipped `cassandra.yaml`, no edits; `MAX_HEAP_SIZE` set for 512M/2048M, unset for auto
(`-Xms7965M -Xmx7965M`; `MaxDirectMemorySize` 3982M in all arms). Schema: keyspace `b7` RF 1, `b7.kv (k blob PRIMARY
KEY, v int)`, `b7.ctr (k blob PRIMARY KEY, c counter)`, table defaults (keys cached ALL, BIG format). No supporting
deviations; the only instrumentation (`jcmd` histograms/heap info/dumps, `nodetool sjk mx`) runs after the fill.

**Arm procedure.** Start → schema → C from JMX → histogram (base) → calibration fill of 20,000 entries (weight/entry
from JMX) → fill to `fill × C` of weight: counter = distinct counter updates; key = insert ≥ 1.6× enough keys, flush,
compact to one sstable (21/21 key arms: 1 sstable), invalidate the key cache, read distinct keys once → 10 s → K →
flush → histogram + heap info → live heap dump → idle 60 s → K + histogram → (full-fill arms) churn with fill/2 new
keys → K + histogram → invalidate the cache → K + histogram → stop. Keys are L-byte blobs, an 8-byte SplitMix64-
scrambled index plus padding (validation showed plain sequential indices collide in `Arrays.hashCode` and treeify the
map; scrambled keys behave like real keys). Concurrency 256 async requests.

| Arm set | Build | Heap | L (B) | Fill | n per cache |
|---|---|---|---|---|---|
| S2 (main condition) | orig | 2048M | 8 | 1.5 × C | 3 |
| size sweep | orig | 2048M | 64, 512 | 1.5 × C | 3 each |
| budget sweep | orig | 512M, auto (7965M) | 8 | 1.5 × C | 3 each |
| V2 control: under-filled | orig | 2048M | 8 | 0.35 × C | 3 |
| V4 intervention: weigher + 104 B | patched | 2048M | 8 | 1.5 × C | 3 |
| OOM contribution | orig | 512M ×2, 2048M ×1 | stress defaults | concurrent write + counter_write + read | 3 |

Stop conditions: 7 h wall, ≤ 50 arm executions; no escalation after an OOM. Executed 43 batch arms 19:46–23:39 MST
2026-11-11 (cache arms all clean; the 43rd, mixed512-r1, lost its sampler, §3.6) and, after the session resumed,
mixed512-r2 (00:02–00:47) and mixed2048-r1 (00:47–01:21) on 2026-11-12: 45 arm executions in ≈ 5.6 h of node time;
3 validation arms before the batch (not counted). The 2048M mixed arm was added on resume (amendment 2026-11-12,
before its reading) to test a second budget for the OOM question.

## 3. Runtime results

Full table: [`logs/arm-table.tsv`](logs/arm-table.tsv). All arms: 0 client errors, resolved heap and caps as
designed. Repeats are identical to 0.1 MiB (deterministic keys and counts; distinct dumps of 259–477 MB).

### 3.1 Main condition (2048 MiB heap, defaults, L = 8)

| Cache | C | K at fill | entries | U (dump) | U/K | **U/C** | weight / heap per entry | n/N U > C |
|---|---|---|---|---|---|---|---|---|
| Counter | 50.0 MiB | 50.00 | 468,114 | 90.1 MiB | 1.80 | **1.80** | 112 / 202 B | 3/3 |
| Key | 100.0 MiB | 100.00 | 1,310,720 | 214.0 MiB | 2.14 | **2.14** | 80 / 171 B | 3/3 |

U breakdown (r1 dumps, MiB). Counter: `byte[]` 21.4 + `CounterCacheKey` 14.3 + `ClockAndCount` 14.3 (= K, 50.0) +
`PSMW` 17.9 + `ConcurrentHashMap$Node` 14.3 + table 4.0 + sketch `long[]` 4.0. Key: `KeyCacheKey` 40.0 + `byte[]`
30.0 + `RowIndexEntry` 30.0 (= K, 100.0) + `PSMW` 50.0 + `CHM$Node` 40.0 + sketch 16.0 + table 8.0.
**Sustained:** K = C and `PSMW` counts unchanged after 60 s idle and after churn with 50 % new keys (counter 468,131
→ 468,135 nodes; key 1,310,723 → 1,310,723) — 3/3 each.
**Independent cross-check** (heap after full GC, `GC.heap_info`): key cache, fill minus after-invalidate = 188–189 MiB
(= U 214 − 24 MiB table + sketch, which invalidation keeps) in 3/3; counter, fill minus base = 85–88 MiB vs U 90.1.

### 3.2 Entry-size sweep (2048 MiB)

| Cache, L | w (B) | u (B) | u − w | U/C (n/N > 1) |
|---|---|---|---|---|
| counter 8 / 64 / 512 | 112 / 168 / 616 | 202 / 260 / 706 | 90 / 92 / 90 | **1.80 / 1.55 / 1.15** (3/3 each) |
| key 8 / 64 / 512 | 80 / 136 / 584 | 171 / 224 / 673 | 91 / 88 / 89 | **2.14 / 1.65 / 1.15** (3/3 each) |

The omitted memory is a constant ≈ 88–92 B per entry, so U/C ≈ 1 + 90/w: it falls with entry size and never reaches 1.

### 3.3 Budget sweep (L = 8, defaults)

| Heap | Key C → U (U/C) | Counter C → U (U/C) | n/N |
|---|---|---|---|
| 512 MiB | 25 → 53.5 MiB (**2.14**) | 12 → 21.7 MiB (**1.81**) | 3/3 each |
| 2048 MiB | 100 → 214.0 (**2.14**) | 50 → 90.1 (**1.80**) | 3/3 each |
| 7965 MiB (auto) | 100 → 214.0 (**2.14**) | 50 → 90.1 (**1.80**) | 3/3 each |

Largest budget tried = the node's auto heap; the overshoot is reached there 3/3 per cache. Above 2 GiB the default caps
are at their 100/50 MiB ceilings, so U stays 214/90 MiB at any larger heap (the overshoot in MiB stops growing; as a
share of the heap it shrinks: the excess above contract is 114 + 40 MiB = 5.6 % + 2.0 % = 7.5 % of a 2 GiB heap,
1.9 % of 7965 MiB; at 512 MiB it is 28.5 + 9.7 MiB = 7.5 %).

### 3.4 V2 control — same build, budget and workload, under-filled (K = 0.35 C)

Counter: K 17.5 MiB, U 29.8 MiB, **U/C 0.60**; key: K 35.0, U 70.5, **U/C 0.71** — 3/3 each, endpoint not reached
(the sketch is not yet allocated below half the maximum, so per-entry heap is 191/161 B).

### 3.5 V4 intervention — diagnostic weigher (+104 B per entry), 2048 MiB, L = 8

Patch [`harness/b7-weigher-overhead.diff`](harness/b7-weigher-overhead.diff) (separate build; the original failure
is reproduced on the unmodified build in §3.1–3.3).

| Cache | K | entries (vs unpatched) | U | **U/C** | n/N U ≤ C |
|---|---|---|---|---|---|
| Counter | 50.00 MiB (216 B/entry) | 242,725 (−48 %) | 46.6 MiB | **0.93** | 3/3 |
| Key | 100.00 MiB (184 B/entry) | 569,878 (−57 %) | 94.6 MiB | **0.95** | 3/3 |

Sustained after idle and churn (3/3). Cost: at the same configured size the cache holds about half the entries, so
hit rates for a working set between the two sizes drop; the alternative fix (keep entry counts, document the setting
as payload size) changes only the documentation.

### 3.6 OOM contribution (defaults, 512 MiB)

**Feasibility first (design §4).** At defaults the uncounted excess is bounded by the caps: at 512 MiB, key
25 → 53.5 MiB and counter 12 → 21.7 MiB, i.e. ≈ 38 MiB above contract (7.5 % of the heap); at ≥ 2 GiB ≈ 154 MiB
(7.5 % of 2 GiB, 1.9 % of 7965 MiB). For this excess to be what tips the heap into an OOM, the other live data must
already hold ≈ 92 % of `-Xmx` on its own.

**Run.** Shipped yaml (memtable heap space ¼ heap = 128 MiB at 512 MiB, caches auto), `cassandra-stress` 500k-row
preload + flush, then concurrent `write n=3M` (256 threads, 1 KiB columns), `counter_write n=2M` (64 threads) and
`read n=4M -pop seq=1..500000` (192 threads), the R4 workload mix at default capacities; 30-min window
(`b7-run.sh mixed`).

| Arm | Window | Caches | Live heap after Full GC (gc.log) | STW share (whole / worst 60 s) | OOM / kill | Errors |
|---|---|---|---|---|---|---|
| mixed512-r1 | ≈ 40 min, unsampled (harness bug, below) | not sampled | 1,074 Full GCs, median 280, max **316 MiB (62 %)** | 22.2 % / 60.5 % | none | 9 `CounterMutationStage` write timeouts |
| mixed512-r2 | 30 min, 301 heap samples | key 25/25 MiB from 00:07:47 (≈ 2 min into load), counter 12/12 MiB; at the end 297,891 / 104,857 entries | 1,019 Full GCs, median 283, max **317 MiB (62 %)**; post-window forced GC 208.5 MiB | 20.8 % / 62.3 % | none | 1 counter write timeout |
| mixed2048-r1 | 30 min, 310 heap samples | key 100/100 MiB from 00:53:52 (≈ 3 min into load), counter 50/50 MiB from 00:52:03; at the end 1,191,563 / 436,906 entries | 86 Full GCs, median 722, max **925 MiB (45 %)**; post-window forced GC 596 MiB | 3.0 % / 14.3 % | none | 15 counter write timeouts |

Completed operations in r2's 30 min: 2.35M writes (client-side timeouts retried), 0.55M counter updates, 1.71M reads;
clients were stopped at the window cap with work outstanding. GC pressure comes from G1's young-generation reserve
(`G1NewSizePercent=50`) next to 200–320 MiB of old data, not from the caches: the most the cache overshoot adds is
≈ 38 MiB against ≈ 195 MiB of headroom above the largest post-Full-GC live heap. At 2048 MiB (2.65M writes, 0.72M
counter updates, 1.56M reads in 30 min) the excess is ≈ 154 MiB against ≈ 1,120 MiB of headroom; the larger live
heap there is the default memtable pool (512 MiB) plus ≈ 304 MiB of cache heap. **Result: no OOM at 512 MiB (0/2)
or 2048 MiB (0/1)**, and no service loss by the 90 % criterion; since the overshoot is a fixed share (≈ 7.5 %) of the
heap up to 2 GiB and a shrinking share above, larger budgets have more headroom, not less. **Largest failing budget:
none found** (tested 512 and 2048 MiB). Classification: the bypass did not contribute to an
OOM; the mixed endpoint was not reached, so no separate control of background memory was needed.

*Harness note (disclosed).* mixed512-r1's sampler was skipped and the arm ended only at the 45-min `timeout`
(its `rc=0` is the trap's exit, not a clean end): `wait` in bash also waits for the `exec > >(tee …)` process
substitution, which never exits. Its readings come from its GC and system logs alone. The fix (wait for the three
stress JVMs before sampling, bound every `jcmd`/`nodetool`, wait for the stress JVMs by name instead of `wait`) was
applied before mixed512-r2's sampling and, for the final `wait`, before mixed2048-r1; mixed512-r2's final cache line,
histogram and heap info were taken by hand (same commands) at the end of its window, before its `timeout` cleanup.

## 4. Conclusion

**Protection gap: confirmed** (bypass, accounting omission: U > C with K ≤ C) for both caches at their shipped
defaults and at every budget tried (512 MiB, 2 GiB, 7965 MiB auto): key cache U = 2.14 × C, counter cache U = 1.80 × C
with small entries, 1.15 × C with 512-byte keys; sustained, deterministic, n = 3/3 per condition. The matched
under-filled control stays below C (3/3) and a weigher charging the per-entry container overhead keeps U ≤ 0.95 C
(3/3). **OOM: not reached** — at defaults the overshoot is bounded by the heap-derived caps (≤ ≈ 7.5 % of the heap
above contract) and an all-defaults concurrent write / counter / read load left 38–55 % of the heap free after
Full GC at 512 MiB (0/2 OOM) and 2048 MiB (0/1). No failing budget was found, so the result is an overshoot, not a
mixed OOM. The R3/R4 OOMs needed custom cache sizes of 200–300 MiB, where the same ≈ 2 × factor adds 100–250 MiB.

**Per-condition status**

| Condition | Status | Basis |
|---|---|---|
| A — key cache, defaults, 2 GiB heap (also 512 MiB, 7965 MiB) | proposed `verified-gap · overshoot · deployment` | §3.1, §3.3–3.5 |
| B — counter cache, defaults, 2 GiB heap (also 512 MiB, 7965 MiB) | proposed `verified-gap · overshoot · deployment` | §3.1, §3.3–3.5 |
| C — overshoot contributing to a heap OOM at defaults | OOM not reached at 512 MiB (0/2) and 2048 MiB (0/1); not a `negative` filing (n < 3 at each budget), recorded as the boundary: no failing budget | §3.6 |

**V1–V7 (conditions A and B; identical evidence structure)**

| | Requirement | Evidence | Met |
|---|---|---|---|
| V1 | endpoint ≥ 3 runs | S2-key8-r1..r3 / S2-ctr8-r1..r3: U/C 2.14 / 1.80, 3/3; also 3/3 at 512M, auto, L = 64, 512 | yes |
| V2 | matched control ×3 | ctl-*8-r1..r3, same build/budget/workload at 0.35 × C: U/C 0.71 / 0.60, 0/3 reach | yes |
| V3 | U apart from K | U = exclusive set of the `BoundedLocalCache` in live dumps vs K = `weightedSize` (dump) and JMX; cross-checked by heap-after-GC deltas | yes |
| V4 | intervention ×3 | iv-*8-r1..r3 (patched weigher): U/C 0.95 / 0.93, 3/3; −57 % / −48 % entries recorded | yes |
| V5 | initiating failure | overshoot endpoint (not OOM/service loss): dump histograms of the holder at the endpoint and after idle/churn; per-arm logs kept | yes (n/a for OOM) |
| V6 | defaults | shipped yaml, `key_cache_size`/`counter_cache_size` auto, resolved 100/50 (2 GiB, auto), 25/12 (512 MiB); custom value only in the patched build's weigher (intervention) | yes |
| V7 | acceptable budget | 512 MiB, 2048 MiB, 7965 MiB auto, `MaxDirectMemorySize` 3982 MiB; all ≥ 512 MiB (standing rule 2026-11-11); largest tried = auto 7965 MiB, endpoint 3/3 | yes |

**Interpretation.** An implementation defect against the documented unit: the weigher returns payload bytes while
the setting and the metrics are documented as memory bytes. Fixes: charge the per-entry overhead in the weigher (as
tested), or document the settings as entry payload and the real footprint (≈ 2 × for small keys). Upstream: check
JIRA for an existing report before filing; the interaction with the heap-derived defaults is small (≤ ≈ 7.6 % of a
2 GiB heap above contract), so the report is about correctness of the documented limit, not an OOM.

**Limits of attribution.**
- U is a shallow-size estimate from the dump (compressed oops, 8-byte alignment); R4 validated the parser against
  `GC.heap_info` within 0.4 %. Table and sketch are power-of-two arrays: their per-entry share varies 1–2 × with
  where n falls, so U/C moves by up to ≈ ±0.1 across cache sizes.
- Key cache tested with BIG sstables and unindexed (small) partitions only; an indexed `RowIndexEntry` carries
  its own (counted) column index. BTI sstables do not use the key cache. Counter cache tested with RF = 1 and
  one-column partitions (cell name = column name only).
- Deterministic workload; repeats differ only in run-to-run state, not in the cache content.
- Only the original weigher and one diagnostic constant were tested; 104 B is an upper bound for this JVM layout.

## Raw data

apt149: `/mydata/b7/logs/<arm>/` (session log, summary, client outputs, class histograms at base / fill / idle /
churn / invalidated, heap info, `hprof-report.txt`, node logs incl. `gc.log*` for the mixed arms),
`/mydata/b7/dumps/<arm>.hprof` (live dumps of the cache arms, 44 files, ≈ 12 GB), `/mydata/b7/logs/batch1.log`
(43 arms), `batch2.log` (mixed512-r2), `batch3.log` (mixed2048-r1), `/mydata/b7/run-{orig,patched}` (builds).
Committed excerpts: [`logs/`](logs/) — `arm-table.tsv`, `batch1.log`, `arms/<arm>/summary.txt` + startup lines,
`hprof/<arm>-holders.txt` (one repeat per condition; repeats are identical), `S2-key8-r1-histo-trend.txt`,
`mixed/<arm>/` (summary, GC Full-pause tail, error lines, samples).
