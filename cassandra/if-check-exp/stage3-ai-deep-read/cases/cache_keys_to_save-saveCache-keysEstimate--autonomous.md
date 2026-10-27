# cache_keys_to_save (key/row/counter) — verification solution  <!-- file: cases/cache_keys_to_save-saveCache-keysEstimate--autonomous.md -->

| Field | Value |
|---|---|
| Entry pointer | `src/java/org/apache/cassandra/cache/AutoSavingCache.java:388` |
| Pinned source | `cassandra-5.0.9` |
| Session / date | Claude Sonnet 5.5 (claude-sonnet-5-5), Claude Code CLI (version not exposed to the agent), 2026-10-26 |
| Estimate | `positive` for disk: the number of entries written to the saved-cache file in `saved_caches_directory` is capped at `*_cache_keys_to_save`, so the file size is bounded by N times the per-entry size. It does not cap the in-memory cache (that is `*_cache_size`). |
| Ground | — (see A3 and A4 for what it does not cap: the live cache, and the transient heap used to pick the hottest N keys) |

## A. Constraint trace

**A1. The constraint.** Three sibling configuration entries with identical semantics:
`key_cache_keys_to_save`, `row_cache_keys_to_save`, `counter_cache_keys_to_save`.
Kind: configuration entry (int, `volatile`). First declared at
`src/java/org/apache/cassandra/config/Config.java:466` (key), `:477` (row), `:483` (counter).
Unit: number of cache keys (entries). Default: `Integer.MAX_VALUE` for all three (same lines),
i.e. effectively "all"; the yaml says "Disabled by default, meaning all keys are going to be saved"
(`conf/cassandra.yaml:541-543`, `:577-579`, `:605-607`; the entries are commented out). A value of `0`
also means "all" (`AutoSavingCache.java:305`). Set by yaml key (restart), or at runtime by JMX
`CacheServiceMBean.set{Key,Row,Counter}CacheKeysToSave` (`service/CacheServiceMBean.java:33-40`,
`service/CacheService.java:242-272`; negative values rejected) and by `nodetool setcachekeystosave`
(`tools/nodetool/SetCacheKeysToSave.java:31-43`, `tools/NodeProbe.java:1096-1101`). Runtime change takes
effect without restart, because the setter reschedules the save task with the new value (`CacheService.java:249`, `:262`, `:275`).
Read via `DatabaseDescriptor.get*CacheKeysToSave` (`config/DatabaseDescriptor.java:3901`, `:3937`, `:3978`).

**A2. What it caps.** Resource: disk (the saved-cache files `KEY_CACHE`/`ROW_CACHE`/`COUNTER_CACHE`
`-g.db`, `.crc`, `.metadata` under `saved_caches_directory`; paths from `AutoSavingCache.java:136-151`, delete/move in `saveCache`).
Quantity compared at the target line: `keysWritten >= keysEstimate` (`AutoSavingCache.java:388`), where
`keysWritten` is a counter of keys iterated and `keysEstimate` is `min(size(), keysToSave)` captured when the `Writer` is constructed (`:304-314`).
Secondary: transient heap used by the iterator for the hottest N keys (A3).

**A3. Mechanism.**
1. Startup: `CacheService` reads the setting and passes it to `scheduleSaving(period, keysToSave)`
   (`CacheService.java:131-133` key, `:165-167` row, `:183-189` counter). `scheduleSaving` captures the value in a Runnable (`AutoSavingCache.java:158-176`); only periods > 0 schedule anything. Row cache save period defaults to 0s (`Config.java:475`), so row cache is never auto-saved by default.
2. Each firing calls `submitWrite(keysToSave)` -> `new Writer(keysToSave)` (`:290-292`, `:153-156`) -> run on the compaction executor with one save per cache type at a time (`CompactionManager.java:1928-1958`, `flushInProgress`).
3. Writer constructor: `size = size()`. If `keysToSave >= size || keysToSave == 0`, iterate all keys (`keyIterator()`), `keysEstimate = size`. Otherwise `keyIterator = hotKeyIterator(keysToSave)` and `keysEstimate = keysToSave` (`:304-314`). `hotKeyIterator` is `policy.hottest(n).keySet().iterator()` for Caffeine/Serializing caches (`CaffeineCache.java:132-135`, `SerializingCache.java:263-266`) and `ohCache.hotKeyIterator(n)` for the default off-heap row cache (`OHCProvider.java:107-110`).
4. `saveCache()` (`:349`): deletes old files (`:352`), returns early if the iterator is empty (`:354-358`). For each key: skip if the table was dropped (`:379-381`), call `cacheLoader.serialize` (`:385`), then `keysWritten++` and `if (keysWritten >= keysEstimate) break;` (`:387-389`). The break at `:388` is the second line of defence: it bounds the loop when the `keyIterator()` path is used and the cache grew after `size()` was read (`keysEstimate = size` snapshot), and for the hot path it is redundant with the `hottest(n)` bound.
5. Outcome at the limit: stop writing; `serializeMetadata` is written, files are renamed over the old ones (`:392-423`). Entries beyond N are simply not persisted (lost on restart, not evicted from the live cache).
Overshoot/bypass paths: (a) `keysWritten` counts iterated keys, not written entries: key cache `serialize` returns without writing when `getInternal(key)` is null (`CacheService.java:487-489`) and dropped tables are skipped without counting, so the file can hold fewer than N entries, never more. (b) The per-entry size is not bounded: key-cache entries include `serializeForCache` of the index entry (`:495`), row/counter entries are keys only (`:394-401`, `:365-372`); key length is up to the partition key size. So disk bound is N * (entry size), not a byte limit. (c) During a save the old and temp files coexist (temp files created at `:362-364`, old deleted at `:352` before), so peak disk is about one file. (d) Runtime change via JMX reschedules with the new count, but a save already running keeps its old `keysEstimate`. (e) `keysToSave == 0` means all, the opposite of "none". (f) Whether `hottest(n)` materialises an n-entry snapshot on heap is Caffeine library behaviour not visible in this tree; verify in the unit tier (B2d) and do not rely on it.

**A4. Other consumers.** Disk in `saved_caches_directory` is shared with nothing else Cassandra writes there except the three cache types. The live cache size is governed by `key_cache_size`, `row_cache_size`, `counter_cache_size` (`Config.java:467-484`), independent of this setting. Heap: Caffeine key/counter cache entries, and the temporary key/hot-key snapshot during save. Disk: SSTables, commitlog, hints, snapshots on other volumes.

**A5. Evidence beyond the source.** Cassandra docs for `key_cache_keys_to_save`, `row_cache_keys_to_save`, `counter_cache_keys_to_save` (cassandra.yaml reference, 5.0). Existing test `test/unit/org/apache/cassandra/cache/AutoSavingCacheTest.java:95-106` shows the submitWrite/clear/load round trip. Caffeine `Policy.Eviction#hottest(int)` javadoc (for the snapshot question). No issue links relied on.

## B. Verification solution

**B1. Claim under test.** For each cache type, the saved-cache file written by one save holds at most N entries and its size grows with N up to the live cache population and no further, where N = `*_cache_keys_to_save` (0 or >= population means all); and the setting does not change the live cache population or its memory.

### B2. Unit tier

**B2a. Environment and build.** JDK 11, Ant. Copy the tree to local disk (`rsync -a /users/jason92/cassandra-5.0.9/ /tmp/$USER/c509/`); never build in the shared tree. `cd /tmp/$USER/c509 && ant jar` (or `ant build-test`). Add a test class `test/unit/org/apache/cassandra/cache/KeysToSaveTest.java` modelled on `AutoSavingCacheTest` (same `@BeforeClass` schema setup with a table `Keyspace1.Standard1`). Run: `ant testsome -Dtest.name=org.apache.cassandra.cache.KeysToSaveTest`. JVM options: the test defaults (`-Xmx1g`). Set `-Dcassandra.storagedir=/tmp/$USER/c509-data` so `saved_caches` is on local disk.

**B2b. Knobs.** `keysToSave` argument of `AutoSavingCache.submitWrite(int)` (the same path used by the scheduler, `AutoSavingCache.java:290`). Values with population P = 10000 entries in the key cache: 1, 100, 1000, 9999, 10000, 20000, 0. Chosen to cover below, at, and above P, and the `0 = all` special case. Row cache variant: P = 2000, N in {100, 2000, 0}, using `SerializingCacheProvider` (heap-free of OHC native dependency; keys saved only). Counter cache variant, same.

**B2c. Workload.** Populate `CacheService.instance.keyCache` directly with P `KeyCacheKey`s (created from `cfs.metadata()`, a live `Descriptor` from a flushed SSTable, and distinct 16-byte keys) and a stub index entry, mirroring `AutoSavingCacheTest`. Touch the first 100 keys 5 times to make them hot so `hottest(N)` order is checkable. Arithmetic: population P is 10000 so any N < 10000 must trigger the `hotKeyIterator` branch (`:312`), N >= P the full branch (`:307`).

**B2d. Observables and instruments.** (1) `keysWritten` via the log line "Saved KEY_CACHE (X items) in ..." (`AutoSavingCache.java:425`) and `Writer.getCompactionInfo().getCompleted()`; (2) data file length with `File.length()` (and `ls -l` on `KEY_CACHE-g.db`); (3) entry count in the file, by reading it back with `loadSavedAsync` into an emptied cache and checking `keyCache.size()`; (4) which keys were persisted (hot 100 present when N=100); (5) heap used by the save: `Runtime` used memory after `System.gc()` before/after, and a `-XX:+HeapDumpOnOutOfMemoryError`-free comparison with `jcmd <pid> GC.class_histogram` taken inside the iteration for N=1 vs N=10000 (to see whether the hottest snapshot is size N). Cannot be observed directly: the Caffeine snapshot size without a profiler.

**B2e. Procedure.**
1. Build; write the test with a loop over the N values.
2. For each N: clear key cache, repopulate P entries, `submitWrite(N).get()`, record log items, file length, then `clear()`, `loadSavedAsync().get()`, record `size()`.
3. Race check (target line 388): start a save with N = 0 on a cache of 10000 entries, and in another thread add 5000 more entries during the save (block the serializer with a latch via a wrapping `CacheSerializer`); record items written; expect <= the size at Writer construction.
4. Repeat for row and counter caches.
5. Control run: positive control, `key_cache_size` unrelated: same population with no save to show the file appears only after save and live `size()` is unchanged.
Commands: `ant testsome -Dtest.name=org.apache.cassandra.cache.KeysToSaveTest -Dtest.methods=...`.

**B2f. Predictions.** Items saved = min(N, P) for N > 0, P for N = 0; reloaded `size()` equals items saved (P for N=0 and N>=P); file length is roughly linear in items: length(N=1000) ~ 10 * length(N=100) within 10% (excluding a fixed header and metadata of tens of bytes and per-SSTable metadata). N=100: the persisted keys are the hot 100. Race test: items written <= 10000 even though the cache reaches 15000. Live `size()` after save is unchanged for every N. Wrong if: items > N for any N in (0, P); file length independent of N; or live size changes with N.

**B2g. Readings.**
| Observation | Meaning |
|---|---|
| items == min(N,P), length monotone in N | claim holds |
| items > N for some 0 < N < P | claim refuted (cap does not bind) |
| items < min(N,P) with nothing dropped | claim holds but counter counts skipped keys; check A3(a) |
| live size changes with N | claim refuted: setting also affects memory |
| race test writes > size at construction | line 388 not effective; refuted |
| heap during save grows with N | transient heap cost is real (record, side finding) |

**B2h. Controls.** Fixed P, fixed key length; the same run with N=0 (all) as baseline; confirm that the table is not dropped and the schema version is stable; run each N twice and in shuffled order to rule out stale files (old files are deleted at `:352`).

### B3. Cluster tier

**B3a. Environment and build.** One node, JDK 11, local copy built with `ant jar`, local disk of known size (>= 20 GB free; data, commitlog, hints, saved_caches all under `/tmp/$USER/node1/`). Heap `-Xms2G -Xmx2G` via `conf/jvm11-server.options`. Config in `cassandra.yaml`: `key_cache_size: 200MiB`, `key_cache_save_period: 10s` (shortest practical; the setting uses seconds), `counter_cache_size: 50MiB`, `counter_cache_save_period: 10s`, `row_cache_size: 100MiB`, `row_cache_save_period: 10s`, `saved_caches_directory: /tmp/$USER/node1/saved_caches`. Use `cassandra-stress` from the same build.

**B3b. Knobs.** `key_cache_keys_to_save`, `row_cache_keys_to_save`, `counter_cache_keys_to_save`, each in {100, 10000, unset(all)}, applied first as yaml (restart) for the first runs, then at runtime with `nodetool setcachekeystosave <key> <row> <counter>` to verify no restart is needed. Table schema `CREATE TABLE ks.t (k int PRIMARY KEY, v text) WITH caching = {'keys':'ALL','rows_per_partition':'ALL'}`; counter table analogue.

**B3c. Workload.** Insert 200000 partitions with `cassandra-stress user` or CQL; flush; read every partition once by primary key (`SELECT v FROM ks.t WHERE k=?`) so key cache and row cache each hold up to 200000 entries (key cache 200MiB comfortably holds that; row cache with 100 MiB holds the rows if each row is < 500 bytes: 200000 * 500 B = 100 MB; use 100-byte values so all fit). For counters, 200000 distinct counter updates. Arithmetic: the populations exceed N=10000 and N=100 by 20x and 2000x, so the cap must bind. Duration: about 5 min per setting, covering at least two save periods.

**B3d. Observables and instruments.** `ls -l` and `du -b` on `saved_caches_directory` after each save (sampled every 5 s with `watch`); log lines "Saved KEY_CACHE (X items) ..." in `system.log`; `nodetool info` (cache entries and capacity); JMX `org.apache.cassandra.metrics:type=Cache,scope=KeyCache,name=Entries` and `Size`; heap via `jcmd <pid> GC.heap_info` / `jstat -gc <pid> 1000`; off-heap via `nodetool info` and `pmap -x` for the row cache; disk free via `df`. Not observable directly: the transient heap of the hottest snapshot (only seen as a short heap bump in `jstat`).

**B3e. Procedure.**
1. Build, edit config with the first setting, start node, create schema.
2. Load and read workload (B3c); wait for two save periods.
3. Record per cache: saved items (log), file sizes, live entries (JMX), heap.
4. `nodetool setcachekeystosave 10000 10000 10000`, wait two periods, record again; repeat with `100 100 100`, then `0 0 0`.
5. Restart the node and record entries after warm load (`nodetool info`), to see the file content actually reloaded.
6. Stop the node (`nodetool drain`, `kill`), `pgrep -f CassandraDaemon` to confirm none left; delete `/tmp/$USER/node1`.

**B3f. Predictions.** Saved items (log) = min(N, live entries) for every cache; file size at N=100 is under 1% of N=all and at 10000 is about 5% of N=all (200000 entries), within about 20% for variable key and SSTable metadata. Live entries (JMX `Entries`) are about 200000 (key) in all runs: unchanged by N. Heap and off-heap totals in steady state differ by < 5% between settings (aside from the transient bump during a save). The runtime `nodetool setcachekeystosave` takes effect at the next save without restart. After restart with N=100, `nodetool info` shows about 100 entries per cache, not 200000. Wrong if: file sizes independent of N; live entries or steady heap/off-heap follow N; the change needs a restart.

**B3g. Readings.**
| Observation | Meaning |
|---|---|
| saved items and file size scale with N, plateau at the live population | claim holds |
| live entries and steady memory unchanged by N | claim holds for the memory side (setting does not touch memory) |
| file size independent of N | claim refuted |
| steady heap/off-heap changes with N | claim refuted: also affects memory |
| after restart entries ~ N | file really limits warm cache |
| file exceeds N * entry size by a large factor | per-entry size larger than assumed (note, claim on count still holds) |

**B3h. Controls.** Same workload with `*_cache_keys_to_save` unset as baseline; same workload with saving disabled (period 0 on key cache) to show no file is created; a second control changing `key_cache_size` (50 MiB vs 200 MiB) shows memory does move with the real memory cap while N does not. Row cache save is off by default (`row_cache_save_period: 0s`), so it must be set explicitly as in B3a, otherwise no row cache file appears.

**B4. Risks and cleanup.** Disk: saved row cache of 200000 rows is small (< 100 MB); all state under `/tmp/$USER/c509*` and `/tmp/$USER/node1`, on local disk only, none on shared storage. Do not build in the shared tree. Stop the node and test JVMs (`pgrep -f 'CassandraDaemon|ant'`), delete the data directories, restore nothing else (no changes outside the nodes).

### B5. Stage-4 audit amendments (2026-10-26, before any reading; none changes B1, B2f/B3f or the meaning of a row)

- **U1 (B2a, environment).** The source copy is made with `stage4-runtime-verification/copy-source.sh` into a per-case work tree (not `rsync` from `/users/jason92/...`). `-Dcassandra.storagedir` is not used: the unit yaml's `saved_caches_directory` is `build/test/cassandra/saved_caches` inside the local copy, which is local disk. Test class `KeysToSaveTest` is copied into the copy's `test/unit/org/apache/cassandra/cache/`; the harness folder holds the source.
- **U2 (B2b/B2c, workload).** A "stub index entry" cannot be serialized (`KeyCacheSerializer.serialize` calls `entry.serializeForCache`, `CacheService.java:495`). The key cache is populated as in `AutoSavingCacheTest`: P = 10000 single-row partitions flushed into one SSTable, then `sstable.getPosition(key, EQ)` for each key. The row cache is not `SerializingCacheProvider`: the unit yaml sets `row_cache_class_name: OHCProvider` and `row_cache_size: 16MiB` (`test/conf/cassandra.yaml:44-45`), so the `ohCache.hotKeyIterator` branch (`OHCProvider.java:107-110`) is the one tested; the table has `caching = {'keys':'ALL','rows_per_partition':'ALL'}`, P = 2000 partitions, populated by reading each. The counter cache: a counter table, P = 2000 distinct counters updated once each. Population is read back from `cache.size()` before each save and `P` in B2f means that value.
- **U3 (B2d item 5, heap).** Replaced by: `ThreadMXBean.getThreadAllocatedBytes` of the test thread around `getWriter(N).saveCache()` called directly (both are public), for N = 1 and N = P, a side observation only (it is not a row of B2g's logic). `jcmd` inside the iteration is dropped.
- **U4 (B2e step 3, race).** `cacheLoader` is final, so the serializer cannot be wrapped. The race uses a private `AutoSavingCache` over `CaffeineCache.create(...)` of type `KEY_CACHE` with a stub `CacheSerializer` (writes one int per key; blocks on a latch at the 100th key); 5000 more keys are added during the block. It is an extra test beyond the main sweep and runs last (it overwrites the `KEY_CACHE` files).
- **U5 (B2g, rows added; a missing outcome, not a changed one).** (a) `N >= P` (incl. 20000 and 0): items == P, "limit not reached; file holds the whole cache" (cap not binding, not a refutation). (b) hot-key check fails (N=100 persisted keys are not the touched 100): reported as a side finding, claim on count unaffected. (c) reload count != items: reading back disagrees with the log; row Invalid until explained.
- **C1 (B3a, ports and paths).** Port slot 1 on pc07: node address 127.0.1.1, JMX 7110 (`nodetool -p 7110`), native 9042 on 127.0.1.1 only; data, commitlog, hints and `saved_caches` under `/dev/shm/s4-b8-kt/` (tmpfs, local); JDK 11, heap 2 GiB, `ulimit -n 100000`. In B3e step 6 the leftover check is `ps -eo cmd | grep '[C]assandraDaemon'`, not `pgrep -f`.
- **C2 (B3c, exact workload).** `cassandra-stress write n=200000 -schema keyspace=keyspace1 -rate threads=50 -node 127.0.1.1` (table `keyspace1.standard1`), then `ALTER TABLE keyspace1.standard1 WITH caching = {'keys':'ALL','rows_per_partition':'ALL'}`, flush, `cassandra-stress read n=200000 -pop seq=1..200000 -rate threads=50`; counters: `cassandra-stress counter_write n=200000 -pop seq=1..200000` (table `keyspace1.counter1`, five counters per partition, so the counter cache may hold more entries than partitions and may reach its 50 MiB cap), after `ALTER TABLE keyspace1.counter1 WITH caching = {'keys':'ALL','rows_per_partition':'NONE'}`. The `ks.t` tables of B3b are replaced by these. The live population of each cache is measured (`nodetool info`, JMX `Entries`) and B3f's "N=all" ratios are taken against that measured population, not against 200000.
- **C3 (B3h control).** The `key_cache_size` control is `nodetool setcachecapacity 8 100 50` at runtime against the 200 MiB start (50 MiB would not bind for about 200000 entries); with keys-to-save unset, `Entries` falls with capacity while the saved items follow `Entries`, not N.
- **C4 (B3g, rows added).** (a) The runtime change needs a restart (no change in the next save after the setter): claim on the no-restart point refuted. (b) Live population smaller than N for every tested N=10000 and 100 not reached: "limit never reached" (Not confirmed). (c) After restart, entries do not follow the saved file: file does not limit warm cache (note; the count claim is unaffected).

## C. Sources read

- /users/jason92/writeup-A/playbook-autonomous.md
- /users/jason92/writeup-A/_TEMPLATE-autonomous.md
- src/java/org/apache/cassandra/cache/AutoSavingCache.java
- src/java/org/apache/cassandra/config/Config.java (lines 455-490)
- src/java/org/apache/cassandra/config/DatabaseDescriptor.java (grep)
- src/java/org/apache/cassandra/service/CacheService.java
- src/java/org/apache/cassandra/service/CacheServiceMBean.java (grep)
- src/java/org/apache/cassandra/cache/CaffeineCache.java, SerializingCache.java, InstrumentingCache.java, OHCProvider.java (excerpts)
- src/java/org/apache/cassandra/db/compaction/CompactionManager.java (submitCacheWrite)
- src/java/org/apache/cassandra/tools/nodetool/SetCacheKeysToSave.java, tools/NodeProbe.java (grep)
- conf/cassandra.yaml (lines 520-612)
- test/unit/org/apache/cassandra/cache/AutoSavingCacheTest.java (grep)

## D. Stage-4 feedback

2026-10-26, pc07, results: `stage4-runtime-verification/results/cache_keys_to_save-saveCache-keysEstimate--autonomous.md`. **Unit tier Confirmed (caps), cluster tier Confirmed (caps); outcome class true positive** (estimate `positive`, effect `caps`).

- Unit (key P = 10000, row and counter P = 2000): items written = min(N,P) for N = 1, 100, 1000, 9999, 10000, 20000, 0 (and 100 / P / 0 for row and counter), reload count and size equal items, file length linear in items (15.8 B per key-cache item after a 16-byte header), live size unchanged; race test (5000 keys added during an N = 0 save): 10000 written, the break at `:388` bounded the loop (a counterfactual iterator yields 15000).
- Cluster (200000 stress partitions, saves every 10 s): saved items = min(N, live) in every phase for unset / 10000 / 100 / 0 at runtime and for yaml 100 and 10000 after restart; file bytes 5.02% (key), 5.00% (row), 2.29% (counter, population 436906) of the unset file at N = 10000 and 0.05% / 0.05% / 0.02% at N = 100; live entries (200016 / 200000 / 436906) and steady heap (234.4 MB) and `RssAnon` unchanged by N; runtime setter takes effect at the next save; with `setcachecapacity 8` the key cache fell to 95325 entries and the saved items followed it; with save periods 0 no file appears.
- Amendments B5 (before run 1, 2026-10-26): real flushed SSTable instead of a stub key-cache entry (U2), row cache is OHC in the unit yaml (not `SerializingCacheProvider`), `ThreadMXBean` allocation instead of a mid-iteration `jcmd` (U3), race through a private cache (U4), exact stress commands and ports (C1, C2), capacity control by runtime `setcachecapacity 8` (C3), added B2g/B3g rows (U5, C4).
- Not as predicted: B2f "N=100 persisted keys are the hot 100" (side check): 0 of 100 touched keys were in the file. After restart with N = 100 the key cache showed 255 entries (row and counter exactly 100).
- Side findings: the log line "Completed loading (n keys) <type> cache" prints the key cache size for every type (`AutoSavingCache.java:189-192`); `nodetool setcachekeystosave` help says "0 to disable" but 0 saves all; the save thread allocates about 0.5 KB per saved item (127 KB at N = 1, 5.5 MB at N = 10000); live key-cache entries grow across restarts because `counter_write` reads `counter1` sstables into the key cache.
