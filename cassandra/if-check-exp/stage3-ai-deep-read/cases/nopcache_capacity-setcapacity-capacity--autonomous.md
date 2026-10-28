# NopCache.setCapacity zero-capacity guard (row cache disabled) — verification solution  <!-- file: cases/nopcache_capacity-setcapacity-capacity--autonomous.md -->

| Field | Value |
|---|---|
| Entry pointer | [`NopCacheProvider.java:39`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/cache/NopCacheProvider.java#L39) |
| Pinned source | `cassandra-5.0.9` |
| Session / date | Claude Sonnet 5.5, Claude Code CLI (Agent SDK), 2026-10-27 |
| Estimate | `positive`: the only legal capacity of the disabled row cache is 0, enforced by this guard, and NopCache stores nothing, so row-cache memory stays 0 whatever an operator asks for at runtime. |
| Ground | — |

**Type:** non-config (hard-coded constant): the numeric literal `0` is the compared value. The choice of `NopCacheProvider` itself is derived from the yaml entry `row_cache_size` (`CacheService.java:146-147`), but the check at the target compares the runtime argument only against the literal `0`.

## A. Constraint trace

**A1. The constraint.** Name: required capacity of the disabled row cache, the literal `0` in `capacity != 0` ([`NopCacheProvider.java:39`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/cache/NopCacheProvider.java#L39)); the same literal is returned by `NopCache.capacity()` (`NopCacheProvider.java:32-35`). Kind: hard-coded literal constant (no declared constant, no yaml or JVM property in the check). Unit: bytes. Default and derivation: fixed 0. Which cache is a NopCache is decided by the yaml entry `row_cache_size` (`Config.java:473-474`, default `0MiB`, [declaration](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/Config.java#L474)): `CacheService.initRowCache` picks `NopCacheProvider` when `DatabaseDescriptor.getRowCacheSizeInMiB() > 0` is false (`CacheService.java:146-147`). Settable: the literal is not settable; the choice of NopCache is made at startup by yaml and needs a restart to change.

**A2. What it caps.** Off-heap/heap memory of the row cache (`CacheService.rowCache`). The compared quantity is the `capacity` argument (bytes) of a runtime resize request; anything other than 0 is rejected, so the cache's capacity stays 0.

**A3. Mechanism.** Runtime resize path: `nodetool setcachecapacity` -> `NodeProbe.setCacheCapacities` (`NodeProbe.java:1088-1094`) -> `CacheService.setRowCacheCapacityInMB(long)` rejects negatives and calls `rowCache.setCapacity(capacity * 1024 * 1024)` (`CacheService.java:327-333`) -> `InstrumentingCache.setCapacity` -> `map.setCapacity` (`InstrumentingCache.java:82-85`) -> `NopCache.setCapacity`, where the check is [`if (capacity != 0)`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/cache/NopCacheProvider.java#L39). Outcome capacity != 0: throws `UnsupportedOperationException` (`:41-42`), the request fails (surfaced through JMX to the nodetool caller). Outcome capacity == 0: no-op. Even without the guard, `put`, `putIfAbsent`, `replace` are no-ops (`:46-58`), `get` returns null, `size`/`weightedSize` return 0 (`:60-77`), so nothing could be held. Bypass/overshoot: none; the guard only protects the contract. Other `setCapacity` implementations (CaffeineCache, SerializingCache, OHC) do not have this guard. Side note: because `setRowCacheCapacityInMB` runs `rowCache.setCapacity` after key-cache is already resized in `NodeProbe.setCacheCapacities`, the failure leaves a partial update of the key cache (not a memory-cap concern).

**A4. Other consumers.** The same resource (row-cache off-heap memory) is used by `OHCProvider`/`SerializingCacheProvider` when `row_cache_size > 0` at startup (`CacheService.java:146-147`); that path is not under this guard. Key cache, counter cache and chunk cache are separate caches and unaffected.

**A5. Evidence beyond the source.** Row cache yaml docs in `conf/cassandra.yaml:550-556` (row_cache_class_name, row_cache_size). Callers searched: `grep -rn setCapacity src/java` (only CacheService, InstrumentingCache and implementations); no tests or JIRA consulted.

## B. Verification solution

**B1. Claim under test.** On a node started with `row_cache_size: 0MiB`, a request to set a non-zero row cache capacity at runtime is rejected and row-cache memory stays 0 with row caching enabled on a table and a read workload; with `row_cache_size > 0` at startup the same request succeeds and memory use grows toward the cap.

### B2. Unit tier

**B2a. Environment and build.** JDK 11, `ant jar` (or `ant build-test`) in a private copy of the tag outside the shared tree; a small JUnit test or main program in that copy, JVM options `-Xmx512m`.

**B2b. Knobs.** Argument to `NopCache.setCapacity` / `CacheService.setRowCacheCapacityInMB`: 0, 1, 64 (MiB, converted to bytes), and -1 (rejected earlier at `CacheService.java:329-330`). Set by direct call. Positive control: an `OHCProvider.create()` cache (or `SerializingCache`) with the same calls.

**B2c. Workload.** Create the cache via `new NopCacheProvider().create()`; call `setCapacity(v)` for each v in bytes (0, 1048576, 67108864); then `put` 10,000 entries of 1 KiB-equivalent values, then read `size()`, `weightedSize()`, `capacity()`. Repeat with the OHC cache created via `OHCProvider.create()` after `DatabaseDescriptor.daemonInitialization()` with `row_cache_size: 64MiB`.

**B2d. Observables and instruments.** Exception thrown or not; `capacity()`, `size()`, `weightedSize()`; JVM used heap via `Runtime` before/after. Native memory of the OHC control is read with `ohCache.stats()` or RSS from `/proc/self/status` (VmRSS).

**B2e. Procedure.** 1) Build. 2) Run the test for each v on NopCache, log outcomes. 3) Run the same sequence on the OHC control. 4) Print table.

**B2f. Predictions.** NopCache: v=0 no exception; v=1 MiB and v=64 MiB throw `UnsupportedOperationException`; after 10,000 puts `size()==0`, `weightedSize()==0`, `capacity()==0`. OHC control: setCapacity succeeds, after puts `size()>0` and `weightedSize()` grows up to about the set capacity.

**B2g. Readings.**

| Observation | Meaning |
|---|---|
| NopCache rejects v>0, size and weightedSize stay 0 | claim confirmed |
| NopCache accepts v>0 or holds entries | claim refuted |
| OHC control does not grow with puts | control failed, not confirmed |

**B2h. Controls.** OHC control above; v=0 as the no-throw baseline; confirm the entry point is reached by a breakpoint/log in the test and not an earlier exception.

### B3. Cluster tier

**B3a. Environment and build.** One node, JDK 11, private build of the tag (`ant jar`), data/commitlog dirs on a private scratch path, `-Xms2g -Xmx2g`, `row_cache_size: 0MiB` (default) for arm A; arm B uses `row_cache_class_name: org.apache.cassandra.cache.OHCProvider`, `row_cache_size: 64MiB`.

**B3b. Knobs.** Arm A: yaml `row_cache_size: 0MiB`, then at runtime `nodetool setcachecapacity 0 64 0` (key, row, counter MiB). Arm B: startup 64MiB, then runtime `nodetool setcachecapacity 0 128 0` as control. Table option `caching = {'keys':'ALL','rows_per_partition':'ALL'}` on both.

**B3c. Workload.** Table `ks.t(id int primary key, v blob)`, 20,000 partitions with 4 KiB blobs (~80 MB), then read each partition twice via cqlsh/`cassandra-stress` or a driver script. Duration ~ 2 minutes.

**B3d. Observables and instruments.** `nodetool info` (Row Cache line: entries, size, capacity, hits), `nodetool setcachecapacity` exit status and stderr, JMX `org.apache.cassandra.metrics:type=Cache,scope=RowCache,name=Capacity|Size|Entries`, process RSS from `/proc/<pid>/status`, sampled every 5 s.

**B3e. Procedure.** 1) Start node arm A, create schema, load data. 2) Record `nodetool info`. 3) Run `nodetool setcachecapacity 0 64 0`, record exit status and message. 4) Run the read workload; record metrics. 5) Stop node, clean data dir. 6) Repeat as arm B.

**B3f. Predictions.** Arm A: the setcachecapacity command fails with an error mentioning "Setting capacity of NopCache is not permitted"; RowCache Capacity, Size, Entries remain 0; hit count 0; RSS growth is not attributable to a row cache. Arm B: command succeeds, Capacity becomes 128 MiB, Entries and Size grow with reads and Size stays <= capacity.

**B3g. Readings.**

| Observation | Meaning |
|---|---|
| Arm A rejects non-zero capacity, Size/Entries 0 after reads; arm B grows and plateaus at cap | claim confirmed |
| Arm A accepts or shows Size > 0 | claim refuted |
| Arm B does not grow (no cache hits or Size stays 0) | control did not move, not confirmed |

**B3h. Controls.** Arm B as positive control; same data and reads in both arms; confirm the table has row caching enabled so that a 0 result is from NopCache, not from table options.

**B4. Risks and cleanup.** Small data (~100 MB) on private scratch dir; stop the Cassandra process in both arms (`nodetool drain` then kill), check with `pgrep -f CassandraDaemon`, delete scratch dirs and test classes.

## C. Sources read

- src/java/org/apache/cassandra/cache/NopCacheProvider.java
- src/java/org/apache/cassandra/service/CacheService.java
- src/java/org/apache/cassandra/cache/InstrumentingCache.java
- src/java/org/apache/cassandra/tools/NodeProbe.java
- src/java/org/apache/cassandra/config/Config.java
- conf/cassandra.yaml

## D. Stage-4 feedback

`none yet`
