# denylist_max_keys_total (JMX setter in setDenylistMaxKeysTotal) — verification solution  <!-- file: cases/denylist_max_keys_total-setDenylistMaxKeysTotal-value--autonomous.md -->

| Field | Value |
|---|---|
| Entry pointer | [`DatabaseDescriptor.java:4827`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/DatabaseDescriptor.java#L4827) (`4827#1`, `value <= 0`) |
| Pinned source | `cassandra-5.0.9` |
| Session / date | Claude Opus 5.5 (claude-opus-5-5), Claude Code at Meta (version string not available in the sandbox), 2026-10-25, band D triage |
| Estimate | `undetermined`. The total cap is enforced only by a full `load()`, which reads each table with `min(perTable, total − processed)` and puts an empty entry once the total is used up (`PartitionDenylist.java:481-500`). The per-table refresh paths reload each table with the per-table limit only (`:201-213,388-391,515-528`). These paths are the timer refresh after `denylist_refresh` (default 600 s) on the next access, and refresh after a JMX add or remove. The class Javadoc says so (`:74-83`). Heap held therefore follows the total right after a load, but can rise to `perTable × denylisted tables` later. Whether usage "follows" the constraint depends on time since load and traffic. Line 4827 only rejects values ≤ 0. |
| Ground | — |

## A. Constraint trace

**A1. The constraint.**
- **Declaration.** `denylist_max_keys_total` is a configuration entry at [`Config.java:780`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/Config.java#L780) (`volatile int`, default 10000). The comment at `:776-779` reads "We cap the total number of denylisted keys allowed in the cluster to keep things from growing unbounded". The unit is a count of partition keys across all tables.
- **yaml.** It appears commented out at `conf/cassandra.yaml:1459-1462`.
- **Runtime setting.** It can be changed over JMX with `StorageProxyMBean.setDenylistMaxKeysTotal(int)` ([`StorageProxyMBean.java:83`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/service/StorageProxyMBean.java#L83), [`StorageProxy.java:3116-3119`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/service/StorageProxy.java#L3116-L3119)). That calls `DatabaseDescriptor.setDenylistMaxKeysTotal` (`:4825-4830`). Line 4827 throws `IllegalArgumentException` for values ≤ 0; otherwise the value is stored.
- **No restart.** No restart is needed. The value is read at each full load (`PartitionDenylist.java:484,497`) and in the error message (`:424`).


**Limit type (2026-10-29).** config: yaml entry. The traced constraint decides ([README §6](../README.md#6-rules-that-hold-for-both-agents)).
**A2. What it caps.** It caps heap. The quantity is the total number of keys across all `DenylistEntry` values in the cache (`PartitionDenylist.java:92-111`). The running sum compared is `totalProcessed` (`:478,484,497-500`).

**A3. Mechanism.**
1. **Full load.** `load()` runs at startup (`initialLoad`, [`StorageProxy.java:3064`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/service/StorageProxy.java#L3064)) and when JMX `loadPartitionDenylist` is called (`:3068-3071`). It builds a new cache from `getDenylistForAllTablesFromCQL()` ([`PartitionDenylist.java:222-238`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/schema/PartitionDenylist.java#L222-L238)).
2. **Per-table loop.** That method runs `SELECT DISTINCT ks_name, table_name` (`:470-474`). For each table:
   - if `total − totalProcessed <= 0`, it logs an ERROR "Hit limit on allowable denylisted keys in total" and puts an empty entry (`:484-493`);
   - otherwise it reads `min(perTable, total − totalProcessed)` keys (`:497-498`) and adds their count to `totalProcessed` (`:499-500`).
3. **Bypass.** The per-table reload paths do not consult the total:
   - Caffeine's `refreshAfterWrite(denylist_refresh)` calls `reload(tid, old)` on the first access after expiry (`:185,201-213`);
   - JMX add or remove calls `refreshTableDenylist` (`:243-262,515-528`).
   Both use `getDenylistForTableFromCQL(tid)` with `perTable` (`:388-391`). An entry that was emptied or truncated by the total therefore grows back to `min(perTable, rows)`. The Javadoc at `:74-83` documents this as an accepted edge case.
4. **At the limit.** Excess keys are not denied, and an ERROR is logged. A check failure at line 4827 throws and leaves the value unchanged.

**A4. Other consumers.**
- Per-table limit (`denylist_max_keys_per_table`, `Config.java:774`).
- Query results while loading.
- The `system_distributed.partition_denylist` memtable and SSTables, which hold all rows.

**A5. Evidence beyond the source.**
- `test/unit/org/apache/cassandra/service/PartitionDenylistTest.java:398-475`, which tests the total limit on full load with `setDenylistMaxKeysTotal(12)` and `(15)`.
- The class Javadoc at `PartitionDenylist.java:74-83`.
- CASSANDRA-12106 (`CHANGES.txt:997`), https://issues.apache.org/jira/browse/CASSANDRA-12106.

## B. Verification solution

**B1. Claim under test.**
1. **After load.** Right after a full `load()` with total cap T and per-table cap P, the cache holds `min(T, Σ min(P, M_i))` keys, so heap follows T.
2. **After refresh.** After `denylist_refresh` has elapsed and each table has been accessed, the cache holds `Σ min(P, M_i)` keys whatever T is, so heap no longer follows T.

Stage 4 decides which phase determines the verdict. If part (2) holds, the constraint does not cap steady-state usage.

**Amendment 2026-10-26 (step-0 audit) — B1, which paths apply the total, and what makes each part falsifiable.** Derived from the source at the tag (re-read in `~/cassandra-src`, `b5f2a54210`). (i) **Applies the total:** only the full `load()` (startup `initialLoad`, `PartitionDenylist.java:132-163`, and JMX `loadPartitionDenylist`, `StorageProxy.java:3068-3071`), through `getDenylistForAllTablesFromCQL` (`PartitionDenylist.java:463-513`). It walks the tables in the order `SELECT DISTINCT ks_name, table_name` returns them, which is the token order of the `(ks_name, table_name)` partitions (`SystemDistributedKeyspace.java:175-183`); each table gets `limit = min(P, T − processed)` (`:497`) and `processed` grows by the keys actually held (`:499-500`); once `T − processed <= 0` every later table gets an **empty** entry and one ERROR `Hit limit on allowable denylisted keys in total. Processed <processed> total entries. …` (`:484-493`) and is not read at all. A table read with `limit < P` that has more than `limit` rows logs `… has exceeded the global allowance of (<T>)` (`:419-431`, `globalLimit = limit != P`). So the total is split first-come in token order: with five tables of M = P keys, T = 1000 holds 1000 in the first table and 0 in four; T = 3000 holds P = 2000, 1000, 0, 0, 0. (ii) **Ignore the total** (read with `limit = P`, `:388-391`): the timer refresh (`refreshAfterWrite(denylist_refresh)`, `:185`, `reload`, `:201-213`) started by the first `denylist.get(tid)` after the interval, which every read, write and `isKeyDenylisted` reaches through `isKeyPermitted` (`:302-329`, `StorageProxy.java:1870-1880`, `:3166-3177`); the refresh after a JMX add or remove (`refreshTableDenylist`, `:243-286`, `:515-528`); and the cache-miss load of a table that has no entry yet (`load(tid)`, `:190-198`). An entry emptied by the total is an entry like any other and is refreshed too. (iii) **What the held count can reach after refresh:** `Σ min(P, M_i)` over the tables accessed — up to P × (tables accessed), independent of T: here 5 × 2000 = 10000 (unit) and 5 × 4000 = 20000 (cluster), i.e. 10× and 5× the smallest T. (iv) **Falsifiability.** Part (1) is refuted by a phase-A count above `min(T, ΣM)`. Part (2) is refuted only if a refresh is **shown to have run** and the count still equals phase A; as filed, "phase B = phase A" matched both the refutation row and the "refresh not triggered" row, so part (2) could not be refuted. Added instruments that see the refresh: in the unit tier, whether each table's `DenylistEntry` object was replaced (every refresh builds a new one, `:207`, `:448`) and the read count of `system_distributed.partition_denylist`; in the cluster tier, that read count (`nodetool tablestats`, `Local read count`, recorded per single-partition read at `ReadCommand.java:624`, `SinglePartitionReadCommand.java:482-485`) before and after the access phase — each refresh is one read. Claim unchanged. Reason: the brief's questions; B1 part (2) needed an instrument that can tell "refresh ran" from "refresh did not run".

### B2. Unit tier

**B2a. Environment and build.**
- **Platform.** Linux, JDK 11, Ant.
- **Clone.** `git clone --depth 1 --branch cassandra-5.0.9 <shared-clone-path> /local/c509`. Never build in the shared clone.
- **Test file.** `/local/c509/test/unit/org/apache/cassandra/service/DenylistTotalTest.java`.
- **Run.** `ant testsome -Dtest.name=org.apache.cassandra.service.DenylistTotalTest`. The test heap is 1024 MiB (`build.xml:1153`).

**Amendment 2026-10-26 (step-0 audit) — B2a, this host.** Run clone `$W/cassandra-run26` (`W=~/Library/Caches/stage4`; `git clone --branch cassandra-5.0.9 ~/cassandra-src $W/cassandra-run26`, full clone, `ant -Dlocal.repository=$W/m2 build-test`), macOS arm64, JDK 11.0.32.1, Ant 1.10.18. The test class (B2e's skeleton with the B2e amendment) is kept as `stage4-runtime-verification/harness/<stem>/DenylistTotalTest.java` and copied into the clone's `test/unit/org/apache/cassandra/service/` by `unit-run.sh`, which runs `ant -Dlocal.repository=$W/m2 testsome -Dtest.name=org.apache.cassandra.service.DenylistTotalTest` once per run label (r1, r2, r3) and copies the JUnit XML and the test log `build/test/logs/**/TEST-org.apache.cassandra.service.DenylistTotalTest.log`. Test JVM heap 1024 MiB (`build.xml:1153`). Instrument check: the class compiles in the run clone (`ant build-test`). Reason: B2a named a CloudLab path.

**B2b. Knobs.**
- **T.** Set via `StorageProxy.instance.setDenylistMaxKeysTotal(T)`. The rejected values are 0 and −1. The accepted values are T ∈ {1000, 3000, 10000}. 1000 is half of one table, 3000 is 1.5 tables, and 10000 covers all five tables of 2000 keys.
- **P.** Fixed at 2000, so it never truncates a table on its own.
- **`denylist_refresh`.** Set to 1 s with `DatabaseDescriptor.setDenylistRefreshSeconds(1)` before each load, because the cache is built with the current refresh interval (`:185`).

**B2c. Workload.**
1. Create keyspace `dl_ks` with tables `t1`…`t5`, each `(k blob PRIMARY KEY, v int)`.
2. Insert 2000 rows per table into `system_distributed.partition_denylist`. Each row has a distinct 2048-byte random key. This gives M_i = 2000 and Σ = 10000.
3. Per T:
   - Run `load()` and count the keys (phase A).
   - Sleep 2 s, call `StorageProxy.instance.isKeyDenylisted("dl_ks","tN","00")` for every table, sleep 1 s, repeat, and count again (phase B). Each call reaches `denylist.get(tid)` through `isKeyPermitted` (`PartitionDenylist.java:304-327`), which triggers the async reload.

**Amendment 2026-10-26 (step-0 audit) — B2c, partitioner, order and expected per-table counts.** (i) The unit JVM's partitioner is **ByteOrderedPartitioner** (`test/conf/cassandra.yaml:18`; `CQLTester.prepareServer()` does not switch it), so each token is a `BytesToken` holding a copy of its key (`ByteOrderedPartitioner.java:66-69`, `:146-151`) and the entry costs ≈ 2.05 × the key bytes (B2f amendment). (ii) Under that partitioner the denylist partitions `(dl_ks, tN)` sort t1 < t2 < t3 < t4 < t5 (computed with the build's classes, `results/<stem>/audit/audit-entrysize.txt`), so the expected phase-A per-table counts are T = 1000: 1000, 0, 0, 0, 0; T = 3000: 2000, 1000, 0, 0, 0; T = 10000: 2000 × 5; phase B: 2000 × 5 for every T. (iii) Nothing in the test touches a `dl_ks` table before the first `load()`, so the cache-miss path (B1 amendment (ii)) never runs. (iv) `test/conf/cassandra.yaml:63-67` enables read thresholds with a 4096 KiB coordinator fail threshold; a read of 2000 keys of 2 KiB (≈ 4.1 MB) is at that threshold, and an aborted read leaves an **empty** entry (`:450-454`) that would look like the cap. The test disables read thresholds in `init()` (the node default is off, `Config.java:526`), as the sister case's runbook fix 1 found. Reason: decides B2f's values and removes a known failure that mimics the cap.

**B2d. Observables and instruments.**
- **Key counts.** Reach the cache by reflection: `StorageProxy.partitionDenylist` → `PartitionDenylist.denylist` → `asMap()` → `DenylistEntry.keys`. Record the per-table counts and their sum Σkeys. Also record the sum of `key.remaining()`.
- **ERROR lines.** Look for "Hit limit on allowable denylisted keys in total" in `build/test/logs/system.log`.
- **Timing.** Refresh timing is asynchronous on the `DenylistCache` executor, and the reload's completion cannot be observed directly. Phase B therefore polls Σkeys until it is stable for 2 consecutive seconds, or up to 10 s.

**Amendment 2026-10-26 (step-0 audit) — B2d, where each reading is read and what is added.** (i) Printed lines (prefix `DLT `) and ERROR lines are read from the test log `build/test/logs/**/TEST-…DenylistTotalTest.log`, not from the XML or `build/test/logs/system.log` (the unit JVM routes `System.out` to the logger). (ii) Per table t1…t5 and per phase: key count, raw bytes (Σ `key.remaining()`), and `ObjectSizes.measureDeep` of the entry (the heap held; the real-resource reading for this tier). (iii) Refresh evidence for phase B: `replaced=<n>` — the number of tables whose entry object (identity) differs from the phase-A one; and `reloadReads=<n>` — the increase of `ColumnFamilyStore.getIfExists("system_distributed","partition_denylist").metric.readLatency.latency.getCount()` across the phase-B loop. (iv) ERROR lines matched by text: `Hit limit on allowable denylisted keys in total. Processed <n> total entries` (`:486`), `has exceeded the <global|per-table> allowance of (<n>)` (`:425`), and `Error reading partition_denylist` (`:452`, `:508`). Reason: the filed output locations are wrong on this build; part (2) needs the refresh evidence (B1 amendment (iv)); group A needs the heap held, not only the count.

**B2e. Procedure.** Test skeleton. The setup is the same as below; it is self-contained.
```java
package org.apache.cassandra.service;
public class DenylistTotalTest {
  @BeforeClass public static void init() {
    org.apache.cassandra.ServerTestUtils.daemonInitialization();
    org.apache.cassandra.cql3.CQLTester.prepareServer();
    List<TableMetadata> ts = new ArrayList<>();
    for (int i = 1; i <= 5; i++) ts.add(CreateTableStatement.parse("CREATE TABLE t" + i + " (k blob PRIMARY KEY, v int)", "dl_ks").build());
    SchemaTestUtil.addOrUpdateKeyspace(KeyspaceMetadata.create("dl_ks", KeyspaceParams.simple(1), Tables.of(ts)), false);
    DatabaseDescriptor.setPartitionDenylistEnabled(true);
    DatabaseDescriptor.setDenylistConsistencyLevel(ConsistencyLevel.ONE);
    StorageService.instance.initServer(0);
  }
  static long total() throws Exception {
    Field f = StorageProxy.class.getDeclaredField("partitionDenylist"); f.setAccessible(true); Object pd = f.get(null);
    Field c = pd.getClass().getDeclaredField("denylist"); c.setAccessible(true);
    Map<?, ?> m = ((com.github.benmanes.caffeine.cache.LoadingCache<?, ?>) c.get(pd)).asMap(); long s = 0;
    for (Object e : m.values()) { Field k = e.getClass().getDeclaredField("keys"); k.setAccessible(true); s += ((Set<?>) k.get(e)).size(); }
    return s;
  }
  @Test public void total() throws Exception {
    Random r = new Random(11);
    for (int t = 1; t <= 5; t++) for (int i = 0; i < 2000; i++) { byte[] b = new byte[2048]; r.nextBytes(b);
      QueryProcessor.executeInternal("INSERT INTO system_distributed.partition_denylist (ks_name, table_name, key) VALUES (?, ?, ?)", "dl_ks", "t" + t, ByteBuffer.wrap(b)); }
    for (int bad : new int[]{0, -1}) { try { StorageProxy.instance.setDenylistMaxKeysTotal(bad); System.out.println("ACCEPTED " + bad); }
      catch (IllegalArgumentException e) { System.out.println("REJECTED " + bad + " getter=" + DatabaseDescriptor.getDenylistMaxKeysTotal()); } }
    StorageProxy.instance.setDenylistMaxKeysPerTable(2000);
    for (int T : new int[]{1000, 3000, 10000}) {
      DatabaseDescriptor.setDenylistRefreshSeconds(1);
      StorageProxy.instance.setDenylistMaxKeysTotal(T);
      StorageProxy.instance.loadPartitionDenylist();
      System.out.printf("T=%d phaseA total=%d%n", T, total());
      long prev = -1, stableSince = System.currentTimeMillis(), start = System.currentTimeMillis(); Thread.sleep(2000);
      while (System.currentTimeMillis() - start < 12000) {
        for (int t = 1; t <= 5; t++) StorageProxy.instance.isKeyDenylisted("dl_ks", "t" + t, "00");
        Thread.sleep(500); long cur = total(); if (cur != prev) { prev = cur; stableSince = System.currentTimeMillis(); }
        else if (System.currentTimeMillis() - stableSince > 2000) break;
      }
      System.out.printf("T=%d phaseB total=%d%n", T, prev);
    }
  }
}
```
Imports: `java.lang.reflect.Field`, `java.nio.ByteBuffer`, `java.util.*`, `org.junit.*`, and from `org.apache.cassandra`: `config.DatabaseDescriptor`, `cql3.QueryProcessor`, `cql3.statements.schema.CreateTableStatement`, `db.ConsistencyLevel`, `schema.*`.

Run three times. The output is in `build/test/output/TEST-org.apache.cassandra.service.DenylistTotalTest.xml`.

**Amendment 2026-10-26 (step-0 audit) — B2e, instrument fixes.** In `harness/<stem>/DenylistTotalTest.java`: (a) **the skeleton does not compile**: `static long total()` and `@Test public void total()` have the same signature; the test method is renamed `totalCap()`; (b) every printed line is one `System.out.println` of one string with prefix `DLT ` (a `printf` arrives split in the test log); (c) `DatabaseDescriptor.setReadThresholdsEnabled(false)` in `init()` (B2c amendment (iv)); (d) after the inserts, `rows tN=<n>` for each table and `partitioner=… getterTotal0=… getterPerTable0=…`; the rejection lines also print the exception message; after each set, `getter=`; (e) the phase-A and phase-B lines print, per table, the count, raw bytes and `measureDeep`, plus the totals (B2d amendment (ii)), and phase B prints `replaced=` and `reloadReads=` (B2d amendment (iii)); the phase-A entry objects are kept for the identity check. The skeleton's steps, values, sleeps, poll loop and stop condition are unchanged. Output: the test log. Reason: the filed skeleton cannot compile, and the readings above were not printed.

**B2f. Predictions.**
- **Setter.** The output shows `REJECTED 0` and `REJECTED -1`, with the getter at 10000.
- **Phase A.** The total is 1000, 3000 and 10000 for T = 1000, 3000 and 10000. That is min(T, 10000), and the ERROR "Hit limit…" appears for T < 10000. Bytes are ≈ 2048 × total.
- **Phase B.** The total is 10000 for every T, because each table is reloaded with P = 2000. This follows from the documented bypass.
- **Refutation.** If phase B equals phase A for T = 1000 and T = 3000, the total cap holds in steady state and part (2) is refuted.

**Amendment 2026-10-26 (step-0 audit) — B2f, exact values from the source.** (i) **Setter:** `REJECTED 0` and `REJECTED -1` with the message `denylist_max_keys_total must be a positive integer.` and getter 10000 (`Config.java:780`; the unit yaml does not set it); after each set, getter = T. (ii) **Phase A:** total = 1000, 3000, 10000 with the per-table counts of the B2c amendment (ii); raw bytes = 2048 × total exactly; Σ deep = **4,209,008 · 12,625,408 · 42,082,800 B** (±2 %), computed with the build's `measureDeep` by `results/<stem>/audit/EntrySize.java`: 160 B for an empty entry, 4,208,368 B for 1000 keys and 8,416,560 B for 2000 keys of 2048 B under ByteOrdered (`audit/audit-entrysize.txt`). (iii) **Phase B:** total = 10000 (2000 per table) for every T, raw bytes 20,480,000, Σ deep = 42,082,800 B (±2 %), `replaced=5` and `reloadReads ≥ 5` for every T. (iv) **ERROR lines** over the whole test: exactly **7** `Hit limit …` lines — 4 with `Processed 1000 total entries` (T = 1000: t2…t5) and 3 with `Processed 3000` (T = 3000: t3…t5); exactly **2** `has exceeded the global allowance of (…)` lines, `(1000)` (T = 1000, t1) and `(3000)` (T = 3000, t2); **no** `per-table allowance` line and no `Error reading` line (the refreshes read with `limit = P = M`, so none exceeds). (v) Every prediction holds in each of the three runs. Reason: the per-table split, the ERROR lines, the heap held and the refresh evidence follow from the source and were open; changed before any reading.

**B2g. Readings.**

| Observation | Meaning |
|---|---|
| Phase A = min(T,10000) and phase B = 10000 for all T | Total caps usage only until refresh; steady-state usage does not follow T (constraint does not durably cap) |
| Phase A = phase B = min(T,10000) | Total cap holds in steady state; estimate resolves to positive |
| Phase A = 10000 for all T | Total not applied even at load (constraint does not cap) |
| Phase B never changes from A within 12 s | Refresh not triggered (control failed; check refresh interval); not confirmed |
| 0 or −1 accepted | Check at 4827 not enforced |

**Amendment 2026-10-26 (step-0 audit) — B2g, the verdict of each row and added rows.** The filed rows are kept with these verdicts. Row 1 ("Phase A = min(T,10000) and phase B = 10000 for all T") requires all of (i)–(v) of the B2f amendment: **Confirmed** (both parts of B1), Effect *caps only on some paths (bypass)*. Row 2 ("Phase A = phase B = min(T,10000)") counts only with `replaced=5` for T = 1000 and 3000 (the refresh ran): **Refuted** (part 2), Effect *caps*. Row 3 ("Phase A = 10000 for all T"), or any phase-A total above min(T, 10000): **Refuted** (part 1), Effect *does not cap*. Row 4 ("Phase B never changes from A", for T < 10000) with `replaced` < 5: **Not confirmed** (refresh not triggered), Effect *undetermined*. Row 5 ("0 or −1 accepted"): **Not confirmed** (the setter prediction failed). Added rows:

| Observation | Meaning |
|---|---|
| `replaced=5` for T < 10000 and phase B neither phase A nor 10000 | The refresh ran but held neither the total's nor the per-table count — **Refuted** (part 2's value), Effect *undetermined* (report per-table counts) |
| phase B between A and 10000 with `replaced` < 5 | Partial refresh — **Not confirmed** |
| an `Error reading …` line, or a phase-A table at 0 without its `Hit limit` line | The entry may be empty because a read failed, not because of the total — **Invalid run** |
| counts as predicted, but Σ deep outside ±2 % of the computed value or raw ≠ 2048 × total | Count follows T; bytes per key differ from the derived structure — **Not confirmed** for bytes (report) |
| ERROR lines not exactly as in B2f (iv) | Disallow evidence differs from the source — **Not confirmed** |
| getter ≠ 10000 after a rejection or ≠ T after a set | Setter not as traced — **Not confirmed** |
| the three runs disagree on any count or on deep beyond ±2 % | **Not confirmed** (report) |
| compile or test failure | **Invalid run** |

Per-table counts that follow a different table order but give the same totals are recorded, not a row condition. Reason: the filed table gave meanings without verdicts, could not tell row 2 from row 4, and lacked rows for partial refresh, read failure, bytes, ERROR lines and run disagreement.

**B2h. Controls.**
- P is fixed at 2000, so only T varies.
- The same rows are used for every T.
- Every T starts with a fresh `load()`, which builds a new cache with a 1 s refresh.
- The per-table counts show which tables were emptied in phase A and refilled in phase B.
- The test is repeated three times.

**Amendment 2026-10-26 (step-0 audit) — B2h, controls' evidence.** "Only T varies": the per-table getter is 2000 throughout (printed) and no `per-table allowance` line appears. "Same rows": `rows tN=2000` for each table before the sweep; no write follows. "A fresh `load()` per T": one `Loaded partition denylist cache` line per T in the test log. "Refresh ran": `replaced` and `reloadReads` (B2d amendment). Reason: the controls' evidence was not named.

### B3. Cluster tier

**B3a. Environment and build.** One Linux node, built from `/local/c509` with `ant jar`. Copy `conf/` to `/local/dt/conf` and set:
- `partition_denylist_enabled: true`
- `denylist_consistency_level: ONE` (one node; the default QUORUM over `system_distributed` RF 3 is unavailable)
- `denylist_max_keys_per_table: 4000`
- `denylist_refresh: 20s`
- data, commitlog, hints, saved_caches and cdc directories under `/local/dt/`
- `-Xms2G -Xmx2G`

Start: `CASSANDRA_CONF=/local/dt/conf CASSANDRA_LOG_DIR=/local/dt/logs bin/cassandra -p /local/dt/pid`. Needs ≥ 5 GB free on `/local`.

**Amendment 2026-10-26 (step-0 audit) — B3a, this host.** One node on 127.0.0.1 from the run clone `$W/cassandra-run26` (built by `build-test`, which includes `jar`). Its conf is generated by the harness's `make-node-conf.sh` (copied from the sister case's harness with its paths changed to `cassandra-run26` and `$W/node-dlmt`) into `$W/node-dlmt/conf` from the tag's `conf/`, with `cluster_name: dlmt`, listen/rpc 127.0.0.1, data, commitlog, hints, saved_caches and cdc directories under `$W/node-dlmt/`, and B3a's lines `partition_denylist_enabled: true` (default false, `Config.java:759`), `denylist_consistency_level: ONE`, `denylist_max_keys_per_table: 4000`, `denylist_refresh: 20s`; `denylist_max_keys_total` is left at its default 10000 and set over JMX (B3b). The nine denylist settings are read back from `system_views.settings` after start. The partitioner is Murmur3 (`conf/cassandra.yaml:389`), so each token is a `LongToken`. Heap `MAX_HEAP_SIZE=2G HEAP_NEWSIZE=400M` (`-Xms2G -Xmx2G`), G1 (`conf/jvm11-server.options:63`), so `GC.run` is a full collection. Start `CASSANDRA_CONF=$W/node-dlmt/conf CASSANDRA_LOG_DIR=<log dir> nohup bin/cassandra -f`, pid from `$!` (no `setsid` on macOS). Free disk 137 GiB. Reason: B3a named CloudLab paths.

**B3b. Knobs.** Set `DenylistMaxKeysTotal`, a write-only attribute of `org.apache.cassandra.db:type=StorageProxy`, to T ∈ {4000, 20000}, and try 0 (rejected). Then invoke `loadPartitionDenylist`. Use this client, saved as `/local/tools/Jmx.java`:
```java
import javax.management.*; import javax.management.remote.*;
public class Jmx { public static void main(String[] a) throws Exception {
  MBeanServerConnection m = JMXConnectorFactory.connect(new JMXServiceURL("service:jmx:rmi:///jndi/rmi://" + a[0] + "/jmxrmi")).getMBeanServerConnection();
  ObjectName sp = new ObjectName("org.apache.cassandra.db:type=StorageProxy");
  if (a[1].equals("set")) { try { m.setAttribute(sp, new Attribute(a[2], Integer.parseInt(a[3]))); System.out.println("OK " + a[3]); } catch (Exception e) { System.out.println("REJECTED " + a[3] + " " + e); } }
  if (a[1].equals("load")) { m.invoke(sp, "loadPartitionDenylist", new Object[0], new String[0]); System.out.println("loaded"); } } }
```

**Amendment 2026-10-26 (step-0 audit) — B3b, names checked and a read-back.** MBean `org.apache.cassandra.db:type=StorageProxy` (`StorageProxy.java:189`). `DenylistMaxKeysTotal` is a **write-only attribute** (`StorageProxyMBean.java:83`, setter only; no getter), `loadPartitionDenylist` an operation (`:73`). `Jmx.java` exactly as written (identical to the sister case's copy), saved at `$W/tools-dlmt/Jmx.java` and run in source-file mode from `$W`. Each set is read back with `SELECT value FROM system_views.settings WHERE name='denylist_max_keys_total'`. Reason: B3b had no read-back.

**B3c. Workload.**
1. Create keyspace `dl` (RF 1) with tables `t1`…`t5`, each `(k blob PRIMARY KEY, v int)`.
2. Generate 4000 random 8 KiB keys per table (20 000 rows, ≈ 330 MB CSV): `python3 -I -c "import os;f=open('/local/dt.csv','w');[f.write('dl,t%d,0x%s\n'%(t,os.urandom(8192).hex())) for t in range(1,6) for _ in range(4000)]"`.
3. Load and flush: `bin/cqlsh -e "COPY system_distributed.partition_denylist (ks_name, table_name, key) FROM '/local/dt.csv' WITH MAXBATCHSIZE=1 AND CHUNKSIZE=50"`, then `nodetool flush system_distributed`.
4. Access phase. Each read passes `isKeyPermitted` while `denylist_reads_enabled` is true by default (`StorageProxy.java:1874`). To trigger refresh, run `for t in 1 2 3 4 5; do bin/cqlsh -e "SELECT * FROM dl.t$t WHERE k=0x00"; done` twice, 5 s apart.

Expected heap held by the cache, at about 8 KiB per key:
- T = 4000: ≈ 32 MiB at load
- T = 20000: ≈ 160 MiB at load
- after refresh: ≈ 160 MiB for both

**Amendment 2026-10-26 (step-0 audit) — B3c, this host and the access phase.** The CSV (5 × 4000 keys of 8192 random bytes, ≈ 328 MB) is written to `$W/node-dlmt/dl.csv` and removed with the node directory; COPY with `cqlsh --request-timeout=120`, then `nodetool flush system_distributed`; afterwards `SELECT count(*) … WHERE ks_name='dl' AND table_name='tN'` must return **4000** for each of t1…t5. **No `dl` table is read before the first load:** the startup cache is empty, and the first access to a table without an entry runs the cache-miss load with P only (`PartitionDenylist.java:190-198`), which would hold keys outside the total's control. The access phase is as written (`bin/cqlsh -e "SELECT * FROM dl.tN WHERE k=0x00"` for t1…t5, twice, 5 s apart; key `0x00` is not denylisted, so the reads succeed). Expected heap: the B3f amendment. Reason: CloudLab paths; M decides what each T can hold; the cache-miss path would confound phase A.

**B3d. Observables and instruments.**
- **Used heap after GC.** Run `jcmd <pid> GC.run` twice, then `jcmd <pid> GC.heap_info`. Take the baseline after an empty load, before the CSV is inserted.
- **Log lines.** Grep `system.log` for "Hit limit on allowable denylisted keys in total" and "exceeded the … allowance".
- **Limit.** Keys per table cannot be observed directly. Heap is the proxy.

**Amendment 2026-10-26 (step-0 audit) — B3d, readings, the baseline after the ingest, and the refresh evidence.** (i) **Used heap after GC** is the `Total` bytes of `jcmd <pid> GC.class_histogram` (it forces a full GC and counts live objects), taken after `jcmd <pid> GC.run` ×2; `GC.heap_info` is recorded only (on this machine its `used` counts young regions allocated after the GC; sister case, runbook fix 2). `[B` bytes are recorded. (ii) **Baseline:** the filed baseline (after an empty load, before the 328 MB ingest) is recorded as `used_pre` but **not** used for Δ: in the sister run a baseline before the ingest was 216 MiB below the post-ingest level, a flushed memtable that stayed referenced. **used₀** is measured after the COPY, flush and row counts, with the cache still empty (the last load ran on an empty table and no `dl` table has been read); **drift control:** a second reading `used₀′` 30 s later; ΔA_T = usedA_T − used₀ and ΔB_T = usedB_T − used₀. (iii) **Refresh evidence:** `Local read count` of `nodetool tablestats system_distributed.partition_denylist` before each load (r0), after it (r1), before the access phase (r2) and 10 s after it (r3): r1 − r0 counts the tables the load read, r2 − r1 shows no refresh before the access phase, r3 − r2 counts the refresh reads. (iv) For each load and each access phase, the part of `system.log` written after it started (byte offset) is searched for `Hit limit on allowable denylisted keys in total. Processed <n> total entries`, `has exceeded the <type> allowance of (<n>)`, `Error reading partition_denylist` / `Error reading full partition denylist` (an empty entry from a failed read would look like the cap) and `Loaded partition denylist cache in …ms`. Every predicted quantity is persistent (held by the cache until the next load or refresh), so a reading after GC sees it. Reason: the baseline's position is a known failure on this machine; part (2) needs refresh evidence (B1 amendment (iv)).

**Runbook fix 2026-10-26 (stage 4, defect 1; found by the cluster shakedown before cluster run 1) — B3d (iii) and B3e, the refresh-read instrument.** In the shakedown, `Local read count` of `partition_denylist` rose by 9 more than the dl-table reads in every window that contained a cqlsh command (load windows 10 and 14 for 1 and 5 dl reads; access windows 14 for 5): each cqlsh connection reads the `system_schema` tables, which are not excluded by `canDenylistKeyspace` (`PartitionDenylist.java:292-300`), so every such read goes through `isKeyPermitted` and the cache-miss load (`:190-198`) or a timed refresh adds an empty entry for that table and one read of its (empty) denylist partition (9 `DenylistEntry` instances in the histogram after the ingest, 14 after an access phase). Fix, with the predicted quantities, values and rows of B3f/B3g unchanged: (a) r0 is read **after** the cqlsh read-back of each set, so no CQL client runs between r0 and r1 or between r1 and r2 (`r1 − r0` and `r2 − r1` keep their meaning and values); (b) the access-phase refresh reads of the dl tables ("`r3 − r2`" in B3f (iv) and B3g) are counted by the READS sampler, `nodetool profileload -a READS -k 20 system_distributed partition_denylist 40000`, started 1 s before the access phase and ending ≥ 10 s after it; the sampler records only non-empty partitions (`SinglePartitionReadCommand.java:911-917`, `:1052-1055`), so it counts the `dl:t1`…`dl:t5` reads and not the empty `system_schema` partitions; `Local read count` r3 − r2 is still recorded. In the second shakedown the load windows gave 1 and 5 and the sampler 5 (one per dl table) in each access phase. The unit tier is unaffected (it ran at the frozen version). Reason: the instrument named at the audit counted reads the prediction does not refer to.

**B3e. Procedure.**
1. Start the node and create the schema. Run `Jmx load`, then GC ×2, and record used₀.
2. `Jmx set DenylistMaxKeysTotal 0` → REJECTED.
3. Insert the CSV and flush.
4. For T in 4000 20000 4000:
   1. Run `set` then `load`.
   2. GC ×2 and record usedA_T (phase A).
   3. Wait 25 s (more than `denylist_refresh`), run the access phase, wait 10 s.
   4. GC ×2 and record usedB_T (phase B).
5. Stop: `kill $(cat /local/dt/pid)`, then check `pgrep -f CassandraDaemon` is empty.

**Amendment 2026-10-26 (step-0 audit) — B3e, run order on this host.** `cluster-run.sh run1 4000 4000 20000 4000` (M per table, then T values): pre-checks (no Cassandra daemon, ports 7000, 7199, 9042 free), conf, start (UN and `statusbinary running`, ≤ 360 s), read back the nine settings, schema (`dl`, RF 1, t1…t5), step 1 (`load`, measure → `used_pre`, recorded), step 2 (`set DenylistMaxKeysTotal 0`, read back), step 3 (CSV, COPY, flush, five row counts), used₀, 30 s, used₀′; step 4 for each T: r0, set, read back, `load`, r1, segment search, measure (5 s, `GC.run` ×2, `heap_info`, histogram → usedA_T), 25 s, r2, access phase (two rounds 5 s apart), 10 s, r3, segment search, measure → usedB_T. Then `nodetool drain`, kill, check, wipe `$W/node-dlmt`. A shakedown of the same script with a small load (`cluster-run.sh shake 400 400 2000 400`, `denylist_max_keys_per_table` 400 for that run only) runs first and is not judged; its readings are used only to check the instruments and the drift bound. Reason: B3e left the read-backs, the read counts, the baseline position and the shakedown open.

**B3f. Predictions.** ΔA_T = usedA_T − used₀ and ΔB_T = usedB_T − used₀.
- **Phase A:** ΔA_4000 ≈ 32 MiB and ΔA_20000 ≈ 160 MiB (±25 % or ±8 MiB). The ERROR "Hit limit…" is logged for T = 4000.
- **Phase B:** ΔB_4000 ≈ ΔB_20000 ≈ 160 MiB (±25 %).
- **Refutation:** if ΔB_4000 stays ≈ 32 MiB, the total cap holds in steady state.

**Amendment 2026-10-26 (step-0 audit) — B3f, bands derived and the other observables.** (i) Per entry, computed with the build's `measureDeep` (Murmur3, 8192-byte keys, `results/<stem>/audit/audit-entrysize.txt`): 33,184,944 B for 4000 keys (8,296.2 B/key), 160 B empty. Derived **ΔA_4000 = 31.65 MiB** (one full table, four empty) and **ΔA_20000 = ΔB_T = 158.24 MiB** (five full tables). The filed tolerance "±25 % or ±8 MiB" is read as the wider of the two: bands **ΔA_4000 ∈ [23.65, 39.65] MiB**; **ΔA_20000, ΔB_4000, ΔB_20000 ∈ [118.68, 197.80] MiB** (the two bands do not overlap). (ii) Read-back = T after each set; `set 0` → `REJECTED … IllegalArgumentException: denylist_max_keys_total must be a positive integer.` and read-back 10000; settings read back: `denylist_refresh` 20s, per table 4000, CL ONE, enabled true. (iii) **Disallow evidence at each T = 4000 load:** exactly 4 `Hit limit …` lines, each `Processed 4000 total entries` (the tables after the first in token order; computed order t1, t5, t4, t3, t2, so t5, t4, t3, t2 — the names recorded, not a row condition), no `has exceeded` line (the first table is read with `limit = 4000 = P = M`); `r1 − r0 = 1` (the four emptied tables are not read). At T = 20000: no ERROR line, `r1 − r0 = 5`. (iv) **Refresh evidence:** `r2 − r1 = 0` and `r3 − r2 ≥ 5` (predicted 5: one refresh per table; the second round is within 20 s of each reload), and no ERROR line in any access phase. (v) No `Error reading` line; one `Loaded …` line per load. (vi) Drift: |used₀′ − used₀| ≤ 6 MiB. (vii) The last T = 4000: ΔA and ΔB each within 6 MiB of the first T = 4000's. (viii) Recorded, not a row condition: `[B` bytes above the used₀ reading (expected ≈ keys × 8,208 B). Reason: the bands are now derived; disallow and refresh evidence, read-back and drift control were not stated. Changed before any reading; the filed values stand.

**B3g. Readings.**

| Observation | Meaning |
|---|---|
| ΔA follows T, ΔB ≈ 160 MiB for both T | Total cap governs heap only until per-table refresh (does not durably cap) |
| ΔA and ΔB both follow T | Total cap holds in steady state (resolves positive) |
| ΔA ≈ 160 MiB for T = 4000 | Total cap not applied on load |
| ΔB = ΔA for T = 4000 and no access-triggered reload seen | Refresh did not fire; not confirmed (repeat with longer wait) |
| 0 accepted | 4827 not enforced |

**Amendment 2026-10-26 (step-0 audit) — B3g, the verdict of each row and added rows.** Row 1 ("ΔA follows T, ΔB ≈ 160 MiB for both T") requires all of (i)–(vii) of the B3f amendment and 4000 rows per table: **Confirmed** (both parts of B1 on a node), Effect *caps only on some paths (bypass)*. Row 2 ("ΔA and ΔB both follow T") counts only with `r3 − r2 ≥ 5` at T = 4000 (the refresh ran): **Refuted** (part 2), Effect *caps*. Row 3 ("ΔA ≈ 160 MiB for T = 4000", i.e. ΔA_4000 in the 158-MiB band, or no `Hit limit` line): **Refuted** (part 1), Effect *does not cap*. Row 4 ("ΔB = ΔA for T = 4000 and no access-triggered reload seen", `r3 − r2 = 0`): **Not confirmed** (refresh not triggered), Effect *undetermined*. Row 5 ("0 accepted"): **Not confirmed** (setter prediction failed). Added rows:

| Observation | Meaning |
|---|---|
| `r3 − r2 ≥ 5` at T = 4000 and ΔB_4000 in neither band | The refresh ran but held neither count — **Refuted** (part 2's value), Effect *undetermined* (report) |
| 0 < `r3 − r2` < 5, ΔB_4000 between the bands | Partial refresh — **Not confirmed** |
| abs(used₀′ − used₀) > 6 MiB | The baseline is moving; absolute Δ not interpretable — **Not confirmed** (Δ and differences reported) |
| an `Error reading …` line, or a load that fails | An entry may be empty because the read failed — **Invalid** for that T |
| row count ≠ 4000 for a table, or read-back ≠ T, or `denylist_refresh` not 20s | The design did not reach the node — **Invalid** |
| ERROR lines or `r1 − r0` not as in B3f (iii)–(v) | Disallow evidence differs from the source — **Not confirmed** |
| a Δ outside its band for one T and inside for the others (not covered above), or the last T = 4000 not within 6 MiB of the first | **Not confirmed** (report which) |
| node fails to start or dies | **Invalid run** |

Reason: the filed table had no verdicts, could not tell row 2 from row 4 on the node, and lacked rows for partial refresh, baseline drift, read failure, read-back, ERROR lines and reversibility.

**B3h. Controls.**
- The per-table cap is fixed at 4000, so it never truncates on its own.
- The same rows are used for every T.
- A fresh `load()` per T.
- A repeated T = 4000 at the end shows reversibility.
- The access phase is the only difference between phase A and phase B.

**Amendment 2026-10-26 (step-0 audit) — B3h, controls' evidence.** "P fixed": read back 4000, and no `has exceeded` line. "Same rows": the five row counts after the flush; no write follows. "Fresh `load()` per T": one `Loaded` line per load. "Access phase the only difference": `r2 − r1 = 0` (no refresh before it). Baseline after the ingest with the drift control (B3d amendment). Reason: the controls' evidence was not named.

**B4. Risks and cleanup.**
- **Unit tier:** about 20 MB of rows. Afterwards run `rm -rf /local/c509/build/test/cassandra`.
- **Cluster tier:**
  1. `rm /local/dt.csv`
  2. `kill $(cat /local/dt/pid)`
  3. Check that `pgrep -f CassandraDaemon` and `pgrep -f cqlsh` are empty.
  4. `rm -rf /local/dt`
- Never write in the shared clone.

**Amendment 2026-10-26 (step-0 audit) — B4, this host.** Unit: the copied test is removed from the run clone and `build/test/cassandra` cleaned after the unit runs; the clone's `test/conf` is left as checked out. Cluster: node data and the CSV under `$W/node-dlmt` (≈ 0.7 GB with the commit log), wiped before and after; full logs under `$W/logs/denylist_max_keys_total-setDenylistMaxKeysTotal/`; at the end `ps -eo command | grep '[C]assandraDaemon'`, `pgrep -f cqlsh`, `pgrep jcmd` empty. Reason: CloudLab paths.

## C. Sources read

- src/java/org/apache/cassandra/config/DatabaseDescriptor.java
- src/java/org/apache/cassandra/config/Config.java
- src/java/org/apache/cassandra/schema/PartitionDenylist.java
- src/java/org/apache/cassandra/schema/SystemDistributedKeyspace.java
- src/java/org/apache/cassandra/service/StorageProxy.java
- src/java/org/apache/cassandra/service/StorageProxyMBean.java
- test/unit/org/apache/cassandra/service/PartitionDenylistTest.java
- conf/cassandra.yaml, build.xml, CHANGES.txt
- https://issues.apache.org/jira/browse/CASSANDRA-12106

## D. Stage-4 feedback

**2026-10-26 — stage 4 run 1 (Claude Opus 5.5, claude-opus-5-5; uncommitted).** Results: [`../../stage4-runtime-verification/results/denylist_max_keys_total-setDenylistMaxKeysTotal-value--autonomous.md`](../../stage4-runtime-verification/results/denylist_max_keys_total-setDenylistMaxKeysTotal-value--autonomous.md).
- **Verdict.** Unit: **Confirmed — caps only on some paths (bypass)** (B2g row 1: phase A = 1000 · 3000 · 10000 keys with per-table counts 1000/0/0/0/0 and 2000/1000/0/0/0, deep exactly 4,209,008 · 12,625,408 · 42,082,800 B; phase B = 10000 keys (42,082,800 B) for every T with all five entries replaced; 0 and −1 rejected; 7 `Hit limit` and 2 `global allowance` lines; three identical runs). Cluster: **Confirmed — caps only on some paths (bypass)** (B3g row 1: ΔA = 31.82 / 158.41 / 31.84 MiB for T = 4000 / 20000 / 4000, ΔB = 158.40 / 158.42 / 159.94 MiB after five dl-table refresh reads each; four `Hit limit` lines per T = 4000 load; drift 1.3 KB). Both parts of B1 hold: the total caps the cache only until the tables are refreshed, after which it holds the per-table sum (10× and 5× T here). The Estimate stays `undetermined` as filed; the runs resolve it as a bypass.
- **Audit findings on this file.** (1) B2e's skeleton does not compile (`static long total()` and `@Test void total()` share a signature). (2) Part (2) of B1 was not falsifiable: "phase B = phase A" matched both the refutation and "refresh not triggered"; refresh evidence was added (replaced entry objects and read counts; on the node, dl-table reads of `partition_denylist`). (3) The unit yaml's ByteOrdered partitioner copies each key into its token (≈ 2.05 × the key bytes) and enables read thresholds at 4096 KiB, which would abort the 2000-key reads and leave empty entries. (4) The cluster baseline must be taken after the ingest (the sister case's 216-MiB failure; here the ingest moved the heap by 230 MiB). (5) Any read of a `dl` table before the first load would use the cache-miss path (`:190-198`), which also ignores the total.
- **Runbook defects.** (1) `Local read count` of `partition_denylist` counts reads for `system_schema` tables too: `canDenylistKeyspace` (`PartitionDenylist.java:292-300`) does not exclude `system_schema`, so every client's schema reads add empty cache entries and their reads; fixed before cluster run 1 (r0 after the read-back; access-phase reads from the READS sampler, which samples only non-empty partitions).
- **For stage 3.** (a) The add/remove refresh and the cache-miss load ignore the total in the same way (derived, not run). (b) A2 could note that `system_schema` tables get denylist cache entries from ordinary client traffic (empty, 160 B each). (c) A finding beyond this constraint: since the total is spent first-come in token order of `(ks_name, table_name)`, which tables are emptied by a full load depends on the partitioner's hash, not on the operator's intent.
