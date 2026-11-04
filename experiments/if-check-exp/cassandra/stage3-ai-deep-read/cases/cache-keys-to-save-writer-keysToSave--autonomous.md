# cache-keys-to-save-AutoSavingCache.Writer-keysToSave — verification solution  <!-- file: cases/cache-keys-to-save-writer-keysToSave--autonomous.md -->

| Field | Value |
|---|---|
| Entry pointer | `src/java/org/apache/cassandra/cache/AutoSavingCache.java:305` |
| Pinned source | `cassandra-5.0.9` |
| Session / date | Claude Sonnet 5.5 (claude-sonnet-5-5), Claude Code CLI, 2026-10-26 |
| Estimate | `positive` for disk: `*_cache_keys_to_save` caps the number of entries written to the saved-cache file in `saved_caches_directory`, so that file's size follows it. It does NOT cap heap/off-heap (the live cache is bounded by `*_cache_size`). |
| Ground | — (the disk claim is positive; the memory side is recorded in A4/B1 as not governed by this knob) |

## A. Constraint trace

**A1. The constraint.** Three sibling configuration entries share the check at line 305: `key_cache_keys_to_save`, `row_cache_keys_to_save`, `counter_cache_keys_to_save` (int, unit = number of cache entries). Declared in `Config.java:466` (key), `:477` (row), `:483` (counter), all `public volatile int ... = Integer.MAX_VALUE`. Default `Integer.MAX_VALUE` means "save everything" (the yaml comment, `conf/cassandra.yaml:541-543`, says "Disabled by default, meaning all keys are going to be saved"; commented examples at `:543,579,607`). The default is therefore not derived from anything else; it is a sentinel. Settable by yaml key (restart) and at runtime by JMX `CacheServiceMBean.set{Key,Row,Counter}CacheKeysToSave` (`CacheService.java:242,255,268`, which reject negatives and reschedule the save task) or `nodetool setcachekeystosave` (`NodeTool.java:207`, `NodeProbe.java:1096`). Value 0 is treated as "all" (`AutoSavingCache.java:305`). The value is read at startup by `CacheService.java:131,165,183` and passed to `scheduleSaving` (`AutoSavingCache.java:158`); periodic saves capture it in a closure (`:167-173`); the manual `saveCaches` path reads the live value (`CacheService.java:357-359`).

**A2. What it caps.** Resource: disk (the `<saved_caches_directory>/<CACHE>-g.db/.crc/.metadata` files; default directory `DatabaseDescriptor.java:700-702`). Quantity compared: `keysToSave` against `size()` (the live entry count of the cache, `AutoSavingCache.java:304`), and during writing `keysWritten >= keysEstimate` (`:388`). It is a count of entries, not bytes, so the byte bound is count x serialized entry size (key cache entry: sstable id/descriptor + `int` key length + key bytes + `serializeForCache` of the index entry, `CacheService.java:486-495`).

**A3. Mechanism.** `Writer` constructor (`AutoSavingCache.java:302`): `size = size()` (`:304`). If `keysToSave >= size || keysToSave == 0` (`:305`), use `keyIterator()` (all keys) and `keysEstimate = size` (`:307-308`). Otherwise use `hotKeyIterator(keysToSave)` (the N hottest by the eviction policy: `CaffeineCache.java:132-135`, `SerializingCache.java:263-266`) and `keysEstimate = keysToSave` (`:312-313`). `saveCache()` (`:349`) iterates and serializes each key (`:375-385`), counts `keysWritten++` and breaks at `keysWritten >= keysEstimate` (`:387-389`). So the file holds at most `keysEstimate` entries. Bypass/overshoot: (1) the value 0 means unlimited, not zero; (2) with `keysToSave >= size` the full-cache path iterates the live map, which may grow while saving, but the break at `:388` stops at the `size` snapshot; (3) entries whose table was dropped are skipped (`:379-381`) so the file can hold fewer; (4) `hotKeyIterator(n)` materialises the n hottest into a map (Caffeine `Policy.Eviction.hottest`), a transient heap cost proportional to n, so the knob does not reduce, and may add, heap during the save; (5) the file is written to a temp file then renamed (`:362-423`), and old files are deleted first (`:352`), so peak disk is old-file-free but temp + nothing else; (6) the load side `loadSaved` is not bounded by this knob (bounded by `cache_load_timeout`, `:230`, and by the cache's own capacity at `put`). The metadata file size depends on the number of sstables/readers, not on the knob (`CacheService.java:433-447`).

**A4. Other consumers.** Disk in `saved_caches_directory` is also used by the other two caches and by leftover temp files from failed saves; the same filesystem may host other directories. Heap/off-heap used by the live caches is governed by `key_cache_size` (`DatabaseDescriptor.java:815-816`, default min(5% heap, 100 MiB)), `row_cache_size` (`Config.java:474`, default 0), `counter_cache_size` (`Config.java:480`), not by keys_to_save.

**A5. Evidence beyond the source.** none (code and yaml comments only).

## B. Verification solution

**B1. Claim under test.** (Disk) For a cache holding N entries, the saved-cache data file contains min(K, N) entries (K = keys_to_save, K=0 meaning N), so its size scales linearly with min(K, N) at constant per-entry size, independent of the live cache size once K < N. (Heap) The knob does not reduce live-cache memory: the cache's in-memory weight stays at its `*_cache_size`-governed level regardless of K. Either relation failing refutes the claim.

### B2. Unit tier

**B2a. Environment and build.** JDK 11, Ant. Copy the tree to local disk (`rsync -a ~/cassandra-5.0.9/ /local/work/c509/`; never build in the shared tree). Add a JUnit test (not committed to the shared tree) `test/unit/org/apache/cassandra/cache/KeysToSaveWriterTest.java` extending `CQLTester`. Build: `cd /local/work/c509 && ant jar -Duse.jdk11=true`; run: `ant testsome -Dtest.name=org.apache.cassandra.cache.KeysToSaveWriterTest -Duse.jdk11=true`. JVM opts: test defaults plus `-Xmx1g`. Test data directories are under the local build dir.

**B2b. Knobs.** K in {1, 100, 500, 1000, 0, Integer.MAX_VALUE, 2000} against a fixed N = 1000 key-cache entries (range spans K<N, K=N, K>N and the sentinel values). Set by calling `AutoSavingCache.submitWrite(K)` directly / `CacheService.instance.setKeyCacheKeysToSave(K)` and `saveCaches()`.

*Amendment 2026-10-26: the counter-cache repeat of B2h uses a counter table, N = 1000 counters updated once each (default `counter_cache_size`), K in {100, 0}; the same assertions n_K = min(K, N) and affine file length apply.*

**B2c. Workload.** `createTable("CREATE TABLE %s (k int PRIMARY KEY, v int)")`, insert 1000 rows, `flush()`, then read each row once with `executeNet`/`execute("SELECT v FROM %s WHERE k=?")` to populate `CacheService.instance.keyCache` (key cache is populated on partition-index lookups for the BIG format; set `key_cache_size` >= 10 MiB so no eviction: 1000 entries x ~150 B << 10 MiB). Assert `keyCache.size() == 1000` before every run. Repeat each of the first 100 keys 5 more times so "hottest" is distinguishable (used to check which keys are chosen).

**B2d. Observables and instruments.** (1) Number of entries written: `Writer.keysWritten` is private, so read it through the log line `Saved KeyCache (<n> items) in ...` (`AutoSavingCache.java:425`; capture with a logback appender) and also count entries by loading the file into a fresh cache via `keyCache.clear(); keyCache.loadSaved()` (returns count, `:287`). (2) File size: `File.length()` of `getCacheDataPath("g")` (`:138`, path `...-g.db`). (3) Heap side: `keyCache.weightedSize()` and `size()` before/after each save. Not directly observable: the transient heap of `hottest(n)`; measure it only coarsely by `Runtime` used-memory delta around the call after `System.gc()`.

**B2e. Procedure.** 1. Start the test JVM; populate as in B2c. 2. For each K: `keyCache.submitWrite(K).get()`; record log count n_K, file length L_K, `size()`. 3. Reload: `keyCache.clear(); loaded = keyCache.loadSaved()`; record; then repopulate to N for the next K. 4. Compute slope (L_K - L_1)/(n_K - 1). 5. Delete saved-cache files and stop the JVM; check no `java` process of yours remains (`pgrep -u $USER -f KeysToSaveWriterTest`).

**B2f. Predictions.** n_K = min(K, 1000) for K>0 and n_0 = 1000, n_MAX = 1000, n_2000 = 1000. L_K is affine in n_K: L_K = L_hdr + n_K * e with e constant (roughly 50 to 150 B per entry) and L_hdr being header + schema version (16 B) + checksummed stream overhead, so L_100 / L_1000 is close to 0.1 (above it by L_hdr/L_1000) and L_1000 = L_2000 = L_0 = L_MAX within a few bytes. `size()` and `weightedSize()` are unchanged by the save. For K=100 the saved keys are the 100 repeated hot keys (verify via reload contents).

*Amendment 2026-10-26 (stage-4 audit, from the source alone): the hot-key sentence is informational and belongs to no B2g row. `hotKeyIterator(n)` is Caffeine `policy.eviction().hottest(n)` (`CaffeineCache.java:132-135`), which orders by the eviction policy's recency/frequency estimate, not by read count, so "the 100 repeated keys" is not guaranteed. The run records which keys were saved and reports it; no verdict depends on it.*

**B2g. Readings.**

| Observation | Meaning |
|---|---|
| n_K = min(K,N), L_K affine in n_K | claim holds (disk) |
| n_K > K for some 0<K<N | claim wrong: knob does not cap the file |
| L_K not monotone in n_K, or L grows with N at fixed K<N | claim wrong (bytes not governed by count) |
| K=0 writes 0 entries | mechanism differs from line 305 reading |
| `weightedSize()` changes with K | knob also affects live memory (unexpected; refutes the heap half) |
| reload count differs from n_K | entries skipped (dropped table / schema mismatch), investigate before concluding |
| size() < N at start | limit not reached; run not valid |

**B2h. Controls.** K=Integer.MAX_VALUE (default) as baseline; K=0 versus MAX equal; same data and read order across K; fresh saved_caches directory per K; same cache type throughout (repeat once with the counter cache to confirm the check is shared).

### B3. Cluster tier

**B3a. Environment and build.** One node (second node optional, for replication-independent confirmation) on a Linux host, JDK 11, built from the local copy (`ant jar`; `bin/cassandra -f` from the copy). `cassandra.yaml` changes: `data_file_directories`, `commitlog_directory`, `hints_directory`, `saved_caches_directory` all on a local disk of known size (>= 20 GiB free; saved caches expected < 2 GiB); `key_cache_size: 200MiB`; `key_cache_save_period: 1h` (we trigger saves manually); `row_cache_size: 0MiB`; heap `-Xms2g -Xmx2g` in `conf/jvm11-server.options`; default `sstable.selected_format` (big) so the key cache is used. Keep `commitlog_sync` default.

**B3b. Knobs.** `key_cache_keys_to_save` in {10000, 100000, 0, default MAX}; set at runtime with `nodetool setcachekeystosave <key> <row> <counter>` (e.g. `10000 0 0`; note that row/counter 0 means "all", harmless since both caches are empty) so no restart is needed, plus one restart-based run with the yaml key to confirm startup wiring. A second dimension: `key_cache_size` {200MiB, 20MiB} to show the live cache is governed by the size knob (positive control for memory).

**B3c. Workload.** `cassandra-stress` (from the copy, `tools/bin/cassandra-stress`): write 2,000,000 partitions (`write n=2000000 -rate threads=50`, small values), `nodetool flush`, then read them: `read n=500000 -pop dist=UNIFORM(1..2000000)` repeated until `nodetool info` shows Key Cache entries >= 300,000 (200 MiB / ~150 B per entry ~ 1.4M capacity, so it is reachable; use the 20 MiB setting to hit the eviction ceiling). Duration: about 10 to 20 min per population. Reaching the limit: entries (>= 300000) exceed every K in the table (10000, 100000).

**B3d. Observables and instruments.** (1) `ls -l` / `du -b` of `saved_caches_directory/KeyCache-g.db` (and `.crc`, `.metadata`), sampled once after each `nodetool` triggered save (`nodetool flush` does not save caches; trigger by `setcachekeystosave` which reschedules, or JMX `CacheServiceMBean.saveCaches` through `jmxterm`: `run -b org.apache.cassandra.db:type=Caches saveCaches`).

*Amendment 2026-10-26 (checked against the pinned source): (a) the MBean name `org.apache.cassandra.db:type=Caches` is right (`CacheService.MBEAN_NAME`, `CacheService.java:80`) and `saveCaches()` is an operation of it (`CacheServiceMBean.java:66`); (b) `setcachekeystosave` does NOT trigger a save: `setKeyCacheKeysToSave` calls `scheduleSaving(period, count)` (`CacheService.java:260-262`), which cancels the old task and schedules the next run one full `key_cache_save_period` later (`AutoSavingCache.java:158-178`), so the save is triggered only by the JMX operation `saveCaches` (which also submits the empty row and counter cache writes: they delete their old files and skip, `AutoSavingCache.java:352-359`); (c) `jmxterm` is not installed on the nodes; the harness uses its own JMX client (`Jmx.java`: get / set / invoke), which does the same calls.* (2) Log line `Saved KeyCache (<n> items) ... : <MB> MB` in `system.log`. (3) `nodetool info` "Key Cache" entries and size. (4) Heap: `jcmd <pid> GC.heap_info` and `jstat -gc <pid> 1000` during the save. (5) `df` of the saved-cache filesystem. Not observable: per-entry serialized size except by division.

**B3e. Procedure.** 1. Start node; confirm settings by reading JMX attribute `KeyCacheKeysToSave` of `org.apache.cassandra.db:type=Caches` (amended 2026-10-26: `nodetool getcachekeystosave` does not exist, confirmed: `NodeTool.java:200-215` lists only `SetCacheKeysToSave`, and `nodetool/` has no Get class for it). 2. Populate the key cache as in B3c, record `nodetool info`. 3. For each K in the list: set K, trigger a save, wait for the log line, record n, file bytes, `jstat` peak, then re-populate if entries fell. 4. Repeat with `key_cache_size: 20MiB` for the control (amended 2026-10-26: K in {10000, 0} in this arm, which is enough to show the K-limited file does not change and the full file shrinks; corrected the same day before any run: a key-cache entry weighs about 80-130 B, so 20 MiB holds about 200,000 entries, not fewer than 100,000). 5. Restart-based run: set yaml `key_cache_keys_to_save: 10000`, restart, populate, save, record. 6. Stop node (`nodetool drain; kill <pid>`), verify with `pgrep -u $USER -f CassandraDaemon`, delete data directories.

**B3f. Predictions.** Logged n = min(K, entries) for K>0, equal to the entries count for 0 and default. File bytes = hdr + n*e (e ~ the unit-tier value, within 20%); K=10000 file ~ 1/10 of K=100000 file (<= 0.11 ratio, ignoring the header), and the K=0/default file ~ entries * e (largest). Live `Key Cache` entries and size in `nodetool info` unchanged by K. With `key_cache_size: 20MiB`, entries drop (about 10x fewer) and the full-save file shrinks proportionally while K-limited files (K < entries) stay the same size.

*Amendment 2026-10-26 (arithmetic from the source, not from any reading): "about 10x fewer" is replaced by "entries(20 MiB) < 0.5 x entries(200 MiB)", because the 200 MiB arm holds only the distinct keys the read passes touch (2M x (1 - e^-0.25) = 442,000 after one 500,000-read pass; the run reads until the cache holds at least 700,000 entries, 2M x (1 - e^-0.5) = 787,000 after two passes), not the 200 MiB capacity, and 20 MiB holds about 200,000 entries at 80-130 B of weight each, so the entry ratio is about 0.2-0.3, not 0.1. Heap relation in the last sentence of B3f is informational (no B3g row depends on it). The frozen relations are: logged n = min(K, entries); file bytes = hdr + n x e; ratio file(K=10000)/file(K=100000) <= 0.11; K=0 and default files equal each other; live entries unchanged by K; entries(20 MiB) < 0.5 x entries(200 MiB).* Heap: no decrease of used heap from lowering K; peak during save for K=100000 slightly above K=10000.

**B3g. Readings.**

| Observation | Meaning |
|---|---|
| file size and logged n follow min(K, entries) | claim holds (disk cap works on a real node) |
| file larger than K*e_max for K<entries | knob does not cap the file; claim wrong |
| live key-cache size changes with K | knob also affects memory (refutes heap half) |
| live size changes only with `key_cache_size` (control) | the memory cap is the size knob, as expected |
| file at K=0 or default equals K=10000 file | "all" sentinel not working, or entries <= 10000 (limit not reached) |
| entries < K for every K | limit never reached; not confirmed |

**B3h. Controls.** Same node, same data, same populated cache across K (re-warm after each run); `key_cache_size` variation as a positive control for memory; default (MAX) as baseline; one pass with the row-less/counter-less settings to exclude other caches; no compaction during measurement (`nodetool disableautocompaction`); take the file size only after the rename completes (log line seen).

**B4. Risks and cleanup.** Disk: data, commitlog, hints and saved caches on a local disk of known size; saved-cache files expected < 1 GiB for 1.4M entries; check `df` before each run, abort if free < 5 GiB. Temp files `KeyCache-g.db*.tmp` can remain after a failed save: delete the directory. Processes: JUnit JVM (unit tier), Cassandra daemon, cassandra-stress, jmxterm, jstat; stop each and verify with `pgrep -u $USER -f 'cassandra|CassandraDaemon|stress|jmxterm|jstat'`. Never write to the shared source tree or shared storage. Cleanup: remove the local copy's data directories and logs.

## C. Sources read

- /users/jason92/writeup-A/playbook-autonomous.md
- /users/jason92/writeup-A/_TEMPLATE-autonomous.md
- src/java/org/apache/cassandra/cache/AutoSavingCache.java
- src/java/org/apache/cassandra/service/CacheService.java (lines 120-275, 357-359, 433-495 by grep)
- src/java/org/apache/cassandra/cache/CaffeineCache.java
- src/java/org/apache/cassandra/cache/SerializingCache.java
- src/java/org/apache/cassandra/config/Config.java (grep)
- src/java/org/apache/cassandra/config/DatabaseDescriptor.java (lines 700-702, 810-830, 3898-3912)
- conf/cassandra.yaml (lines 530-545 and grep)
- src/java/org/apache/cassandra/tools/NodeTool.java, NodeProbe.java (grep)

## D. Stage-4 feedback

`none yet`

**Stage-4 result (2026-10-26, pc12; results file `stage4-runtime-verification/results/cache-keys-to-save-writer-keysToSave--autonomous.md`; commits: not yet committed, the orchestrator records them).** Unit **Confirmed** (caps, disk): at N = 1000, K = 1, 100, 500, 1000, 0, MAX, 2000 logged 1, 100, 500, 1000, 1000, 1000, 1000 items and the file is affine in n (16.6 B + 12.45 B per entry); counter cache the same. Cluster **Confirmed** (caps, disk): with 846,505 entries in the key cache, K = 10000 / 100000 / 0 / default wrote 10000 / 100000 / 846,505 / 846,505 items = 199,883 / 1,998,556 / 16,918,090 / 16,918,090 B (19.99 B per entry); the live cache (entries, weight) is unchanged by K and follows `key_cache_size` (20 MiB: 238,312 entries); the yaml value read at startup is also the value the periodic save uses. Outcome class: true positive. What the file got wrong or left open: the per-entry size guess "50 to 150 B" (measured 12.45 B and 19.99 B); the hot-key sentence of B2f (K = 100 did not save the 100 repeated keys; `hottest(n)` is policy order); the transient heap of `hottest(n)` was not isolated (heap-used sampling too coarse), so B3f's last sentence is neither confirmed nor refuted. Upstream/doc candidates: "0 to disable" in the `nodetool setcachekeystosave` description against the code (0 saves everything), and `keysWritten++` counting an entry that `serialize` skipped because it was evicted meanwhile.

**Step-0 audit amendments (2026-10-26).** All five are dated next to the text they change: B2b (counter-cache repeat made exact), B2f (hot-key sentence informational), B3d (MBean name confirmed; `setcachekeystosave` does not trigger a save, JMX `saveCaches` does; no jmxterm), B3e (`getcachekeystosave` does not exist; control arm K values), B3f (entry-ratio relation). Observation for the record (not an amendment): the `nodetool setcachekeystosave` description ("0 to disable", `SetCacheKeysToSave.java`) disagrees with the code, where 0 means save all entries (`AutoSavingCache.java:305`).
