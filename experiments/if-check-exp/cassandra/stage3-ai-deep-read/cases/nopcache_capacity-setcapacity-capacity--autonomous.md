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

## B-audit. Stage-4 design-audit amendments (2026-10-27)

Applied by the stage-4 audit session on 2026-10-27, before any reading of the frozen run, next to the text they change (B2/B3 above stay as filed; where an item below makes a statement exact, the item governs). The claim (B1) is unchanged; B2f and B3f are changed only where an item says "made exact" or "adds". The sha256 of this file after these amendments is recorded in `stage4-runtime-verification/results/nopcache_capacity-setcapacity-capacity--autonomous.md` section 1. One reading of the claim, stated so a verdict is not mistaken for more than it is: the guard at `NopCacheProvider.java:39` refuses to *raise* the capacity of a cache that stores nothing, so "row-cache memory stays 0" holds because `NopCache` is a no-op class (A3 says so: `put`, `putIfAbsent`, `replace` do nothing even without the guard); the guard protects the contract, not the memory. Stage 4 therefore tests the claim as filed and, with a patched-literal arm, also tests whether the guard is what keeps the memory at 0.

**B2i. Unit tier.**
1. *Instrument.* One JUnit class `NopCacheCapTest extends CQLTester` (`test/unit/org/apache/cassandra/cache/` of a private copy; source in the harness folder), run with `ant testsome -Dtest.name=org.apache.cassandra.cache.NopCacheCapTest` on `tree-base` (unpatched) and on `tree-nopguard` (item 5). Parts: `N1` the class itself (`new NopCacheProvider().create()`), `N2` the `InstrumentingCache` wrapper `CacheService` holds, `N3` the OHC control.
2. *Values.* The operand of the guard takes 0 (the default and only legal value), 1 MiB, 64 MiB, -1 and `Long.MAX_VALUE`. At the class level `-1` and `Long.MAX_VALUE` are not rejected "earlier" than the guard (the negative test at `CacheService.java:329-330` is in the service method, which the unit tier does not call): both are non-zero, so both are predicted to throw `UnsupportedOperationException`. B2c's puts (2,000,000, see item 3) are made as `put` + `putIfAbsent` + `replace` + `get` per key with `RowCacheSentinel` values (a `NopCache` stores nothing whatever the value, so the value size is immaterial for it).
3. *Observables made exact.* B2f for `NopCache`: v=0 no exception; v=1 MiB, 64 MiB, -1, `Long.MAX_VALUE` throw `UnsupportedOperationException` whose message contains "is not permitted as this cache is disabled"; `capacity()` is 0 after every call; after the puts `size() == 0`, `weightedSize() == 0`, `putIfAbsent` and `replace` return false every time, `get` returns null every time; heap used (after three `System.gc()`) changes by less than 8 MiB and `RssAnon` by less than 4 MiB. (Amendment of the same day, before the freeze: the puts are raised from 10,000 to 2,000,000 per key triple so that a cache that did retain them would add about 180 MB; a shakedown showed the heap reading of a JVM at rest varies by about 2 MiB either way, so a 1 MiB threshold on 10,000 entries could not tell retention from noise. The decisive readings are `size()`, `weightedSize()` and `get`.) `N2`: `setCapacity(0)` no exception, `setCapacity(64 MiB)` throws.
4. *The control, made runnable.* B2c's OHC control ("OHCProvider.create() after daemonInitialization with 64 MiB, 10,000 entries of 1 KiB") cannot put 1 KiB entries by hand (an `IRowCacheEntry` is a cached partition or a sentinel, and a sentinel weighs next to nothing). `N3` instead uses the unit yaml's row cache (`OHCProvider`, 16 MiB, `test/conf/cassandra.yaml:44-45`) through CQL: a table with `caching = {'keys':'ALL','rows_per_partition':'ALL'}`, 20,000 partitions of a 1 KiB blob (about 21 MB, more than 16 MiB), each read twice. Prediction (made exact): `weightedSize() <= capacity() = 16 MiB` at every report and `>= 14 MiB` at the end; then `CacheService.instance.setRowCacheCapacityInMB(32)` succeeds (no exception, `capacity()` = 32 MiB) and two more passes leave `weightedSize()` above 16 MiB and at most 32 MiB; `RssAnon` rises with `weightedSize()` (growth at the end at least 80 % of `weightedSize()`).
5. *Patched-literal arm (the literal cannot be varied by configuration).* `tree-nopguard` is a second private copy that differs in exactly the guard: `NopCacheProvider.java:39` `if (capacity != 0)` changed to `if (false)`. The same test runs on it. Prediction, from the code and stated before it runs: `setCapacity(1 MiB)`, `setCapacity(64 MiB)`, `-1` and `Long.MAX_VALUE` are accepted (no exception), `capacity()` stays 0, and after the puts `size() == 0` and `weightedSize() == 0`; i.e. the memory stays 0 without the guard, and the guard is only what turns a request into an error.

**B2g additions.**

| Observation | Meaning |
|---|---|
| `tree-nopguard` stores entries or `capacity()` != 0 after `setCapacity(64 MiB)` | the guard is what keeps the memory at 0; claim holds in a stronger form |
| `tree-nopguard` accepts the request and still stores nothing | memory stays 0 because `NopCache` is a no-op; the guard protects the contract only (estimate's reading holds for the claim as filed, with this qualification) |
| `N3` control weightedSize above its capacity, or no growth after the raise | control failed or the harness is invalid; not confirmed |

**B3i. Cluster tier.**
1. *Node.* One node on loopback `127.39.8.1` (tag `nc`), JMX 7438, heap `-Xms2G -Xmx2G`, private directory on local disk (`~/s4-cc/ncnode`, removed afterwards), `counter_cache_size: 0MiB`, `row_cache_save_period: 0s`, `auto_snapshot: false`. A fresh node directory per arm.
2. *Arms and values.* Arm A: `row_cache_size: 0MiB` (the default, `NopCache`). Arm AP: the same on the patched build `tree-nopguard`. Arm B32: `row_cache_class_name: org.apache.cassandra.cache.OHCProvider`, `row_cache_size: 32MiB` at start, raised to 64 MiB at run time. Arm B8: OHCProvider 8 MiB, no runtime change (a third knob value, so the control is dose-responsive). The filed arm B (64 MiB then 128 MiB) is replaced because 20,000 x 4 KiB (about 82 MB serialized) never reaches 128 MiB, and a cap that is not reached shows nothing about a bound.
3. *Workload.* `cassandra-stress user` with `harness/<stem>/rc.yaml`: `ks.t (id int PRIMARY KEY, v blob)`, `caching = {'keys':'ALL','rows_per_partition':'ALL'}`, no compression; load 20,000 partitions of 4096-byte blobs (`insert`, `-pop seq=1..20000`), `nodetool flush ks t`; read passes `read1` over `seq=1..20000` (each partition read once per pass). Arms A, AP, B32: pass 1, pass 2, the runtime request `nodetool setcachecapacity 0 64 0` (key, row, counter MiB; the filed command; as a side effect it sets the key cache to 0, which is irrelevant to the row cache), a second request `nodetool setcachecapacity 0 0 0` in arm A, then pass 3 and pass 4. Arm B8: pass 1 and pass 2.
4. *Instruments.* `org.apache.cassandra.metrics:type=Cache,scope=RowCache,name=Size|Capacity|Entries|Hits|Requests` over JMX every 5 s (`Jmx.java`); `nodetool` exit status and its full output for each request; `RssAnon` from `/proc/<pid>/status` at every sample (the row cache is off-heap, so heap histograms do not show it; a class histogram at the phase ends is kept for the on-heap side); `nodetool info`'s Row Cache line at the end.
5. *Predictions made exact.* Arm A: the request `0 64 0` exits non-zero with output containing "Setting capacity of NopCache is not permitted"; the request `0 0 0` exits 0; RowCache `Capacity`, `Size`, `Entries`, `Hits` are 0 at every sample, before and after both requests, including after pass 4; the `RssAnon` growth from the end of the load to the end of pass 4 is below half of arm B32's growth over the same phases. Arm AP: the request `0 64 0` exits 0; `Capacity` stays 0 and `Size`, `Entries` stay 0 after pass 4. Arm B32: `Capacity` 32 MiB at start; after passes 1 and 2 `Size <= 32 MiB` and `>= 80 %` of it; the request exits 0 and `Capacity` becomes 64 MiB; after passes 3 and 4 `Size <= 64 MiB` and `>= 80 %` of it, `Entries` higher than before. Arm B8: `Size <= 8 MiB` and `>= 80 %` of it; `Size(B32 at 32 MiB) / Size(B8)` between 3 and 5.
6. *Stop and cleanup.* Per-arm stop condition: all passes finished with 0 stress errors. The node is stopped by PID (`nodetool drain`, then SIGTERM). "No process left" is checked with `ps -eo cmd | grep '[C]assandraDaemon'` run on the node itself; the node directory and private copies are removed afterwards.

**B3g additions.**

| Observation | Meaning |
|---|---|
| arm AP accepts the request and shows `Capacity` 0, `Size` 0 | memory stays 0 without the guard (no-op cache); the guard protects the contract only |
| arm AP shows `Capacity` > 0 or `Size` > 0 | the guard is what keeps the memory at 0 |
| arm A request accepted, or arm A `Size` > 0 | claim refuted |
| arm B32 or B8 `Size` above `Capacity`, or no growth to 80 % of it | control failed or workload too small; not confirmed |

## C. Sources read

- src/java/org/apache/cassandra/cache/NopCacheProvider.java
- src/java/org/apache/cassandra/service/CacheService.java
- src/java/org/apache/cassandra/cache/InstrumentingCache.java
- src/java/org/apache/cassandra/tools/NodeProbe.java
- src/java/org/apache/cassandra/config/Config.java
- conf/cassandra.yaml

## D. Stage-4 feedback

**Stage 4, run 2026-10-28 (pc39; results [`results/nopcache_capacity-setcapacity-capacity--autonomous.md`](../../stage4-runtime-verification/results/nopcache_capacity-setcapacity-capacity--autonomous.md)).** Verdict: **unit Confirmed, cluster Confirmed; Effect on the constraint: caps; Outcome class: true positive** (estimate `positive`, effect `caps`).
- Numbers. Unit: `NopCache.setCapacity` threw for 1 MiB, 64 MiB, -1 and Long.MAX and accepted 0; after 2,000,000 puts `size`/`weightedSize` 0; OHC control filled to 16,774,464 B of 16 MiB and accepted a raise to 32 MiB (23.5 MB). Cluster: arm A (`row_cache_size: 0MiB`) `nodetool setcachecapacity 0 64 0` exit 2 with "Setting capacity of NopCache is not permitted"; RowCache Capacity/Size/Entries/Hits 0 after 80,000 reads; the same command had already set the key cache to 0 (partial update, as A3 notes). OHC arms: 8 MiB -> Size 8.16 MB; 32 MiB -> 33.2 MB, raised at run time to 64 MiB -> 64.4 MB.
- The guard's role: on a build with the guard removed the request is accepted, `capacity()` stays 0 and nothing is stored (unit and cluster). Row-cache memory is 0 because `NopCache` is a no-op class; the guard protects the contract. Claim holds as filed.
- Amendments by the audit ("B-audit", 2026-10-27): runnable OHC control via CQL; cluster arm B changed to 32 -> 64 MiB plus an 8 MiB arm (82 MB of data never reaches 128 MiB); patched-guard arms; 2,000,000 puts with an 8 MiB heap threshold (heap reading noise); `ps` process check.
- For stage 3: the secondary `RssAnon` clause in B3f is not usable as an instrument (the process holds 2.9 GB and drifts 20 to 45 MiB in every arm); use RowCache `Size`/`Entries` instead. The claim is close to tautological (a no-op cache cannot hold memory); the guard itself is not what bounds memory.
