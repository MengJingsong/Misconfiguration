# denylist_max_keys_per_table (JMX setter in setDenylistMaxKeysPerTable) — verification solution  <!-- file: cases/denylist_max_keys_per_table-setDenylistMaxKeysPerTable-value--autonomous.md -->

| Field | Value |
|---|---|
| Entry pointer | [`DatabaseDescriptor.java:4815`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/DatabaseDescriptor.java#L4815) (`4815#1`, `value <= 0`) |
| Pinned source | `cassandra-5.0.9` |
| Session / date | Claude Opus 5.5 (claude-opus-5-5), Claude Code at Meta (version string not available in the sandbox), 2026-10-25, band D triage |
| Estimate | `positive` (scoped: a count cap on heap-held denylist keys per table; bytes per key are bounded only by the 64 KiB key limit). Every path that fills the in-memory partition-denylist cache reads a table's keys with `LIMIT perTable+1` and stops adding at `perTable` (`PartitionDenylist.java:390,404-409,443-446`). The three paths are full load, per-table refresh after `denylist_refresh`, and refresh after a JMX add/remove. Heap held by the cache for one table is therefore at most `perTable × (key size + overhead)`. Line 4815 only rejects values ≤ 0. |
| Ground | — |

## A. Constraint trace

**A1. The constraint.**
- **Declaration.** `denylist_max_keys_per_table` is a configuration entry ([`Config.java:774`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/Config.java#L774), `volatile int`, default 1000). The [`Config.java:771-773`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/Config.java#L771-L773) comment reads "We cap the number of denylisted keys allowed per table to keep things from growing unbounded". It appears commented out in yaml at `conf/cassandra.yaml:1454-1457`. The unit is a count of partition keys.
- **Runtime.** JMX `StorageProxyMBean.setDenylistMaxKeysPerTable(int)` ([`StorageProxyMBean.java:82`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/service/StorageProxyMBean.java#L82), [`StorageProxy.java:3110-3113`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/service/StorageProxy.java#L3110-L3113)) calls `DatabaseDescriptor.setDenylistMaxKeysPerTable` (`:4813-4818`). Line 4815 throws `IllegalArgumentException` for `value <= 0`; otherwise the value is stored. No getter is exposed over JMX, and there is no nodetool command.
- **Restart.** No restart is needed. The value is read at each load or refresh (`PartitionDenylist.java:390,422,497`). The cache does not shrink until the next load or refresh.


**Limit type (2026-10-29).** config: yaml entry. The traced constraint decides ([README §6](../../../stage3-ai-deep-read/README.md#6-rules-that-hold-for-both-agents)).
**A2. What it caps.** It caps heap. The cache is `LoadingCache<TableId, DenylistEntry>` (`PartitionDenylist.java:92`). Each entry holds an `ImmutableSet<ByteBuffer>` of keys and an `ImmutableSortedSet<Token>` (`:95-111`). The quantity compared is `processed`, the number of rows copied into the entry (`:439-446`), plus `results.size() > limit` for the error log (`:419-430`). The transient query result is also bounded by `LIMIT limit+1` (`:404-409`).

**A3. Mechanism.**
1. **Load.** `load()` (startup `initialLoad`, [`StorageProxy.java:3064`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/service/StorageProxy.java#L3064); JMX `loadPartitionDenylist`, [`StorageProxy.java:3068-3071`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/service/StorageProxy.java#L3068-L3071)) runs `getDenylistForAllTablesFromCQL` ([`PartitionDenylist.java:465-511`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/schema/PartitionDenylist.java#L465-L511)). For each denylisted table it reads `min(perTable, total − processedSoFar)` keys (`:497-498`).
2. **Per-table read.** `getDenylistForTableFromCQL(tid, limit)` (`:396-455`) sends `SELECT * FROM system_distributed.partition_denylist WHERE ks_name=… AND table_name=… LIMIT limit+1` at `denylist_consistency_level` (`:404-412`). If more than `limit` rows come back, it logs an ERROR "has exceeded the per-table allowance" (`:419-430`). It copies at most `limit` keys (`:439-446`) into immutable sets (`:448`).
3. **Refresh.** `refreshAfterWrite(denylist_refresh)` reload (`:185,201-213`) and `refreshTableDenylist` after JMX `denylistKey`/`removeDenylistKey` (`:243-262,515-528`) both use `getDenylistForTableFromCQL(tid)` with the per-table limit (`:388-391`).
4. **When the limit is reached,** the excess keys are ignored (they are not denied), and an ERROR is logged. The check at 4815 throws, and the value stays unchanged.

Bypasses and overshoots:
- **The cache has no `maximumSize`** (`:183-186`), so the number of table entries is unbounded. Total heap is about `perTable × number of denylisted tables` (see `denylist_max_keys_total`).
- **Each key is a `ByteBuffer` from `row.getBlob`** (`:441`). If such a buffer is a view over a larger result buffer, it may retain more than the key's own bytes.

**A4. Other consumers.** Other heap users are outside this cap:
- The denylist executor (`:90`).
- The query result of the `SELECT DISTINCT` (`:470-474`).
- The `system_distributed.partition_denylist` memtable and SSTables, which hold all rows regardless of the cap (disk and memtable).

**A5. Evidence beyond the source.**
- The in-tree test `test/unit/org/apache/cassandra/service/PartitionDenylistTest.java`, which exercises the limits with `setDenylistMaxKeysPerTable(5)` (lines 352-475).
- The class Javadoc, `PartitionDenylist.java:60-83`.
- CASSANDRA-12106, which introduced the partition denylist: https://issues.apache.org/jira/browse/CASSANDRA-12106.

## B. Verification solution

**B1. Claim under test.** After `setDenylistMaxKeysPerTable(P)` and a denylist load or refresh, the in-memory denylist entry for a table holds exactly `min(P, M)` keys, where M is the number of denylisted rows for that table. Its heap therefore grows with `min(P, M)` and not with M. Values ≤ 0 are rejected.

### B2. Unit tier

**B2a. Environment and build.**
- **Platform.** Linux, JDK 11, Ant.
- **Clone.** Run `git clone --depth 1 --branch cassandra-5.0.9 <shared-clone-path> /local/c509`. Never build in the shared clone.
- **Test location.** `/local/c509/test/unit/org/apache/cassandra/service/DenylistPerTableTest.java`.
- **Run.** `cd /local/c509 && ant testsome -Dtest.name=org.apache.cassandra.service.DenylistPerTableTest`. The test JVM heap is 1024 MiB (`build.xml:1153`).

**Amendment 2026-10-26 (step-0 audit) — B2a, this host.** Run clone `$W/cassandra-run25` (`W=~/Library/Caches/stage4`; `git clone --branch cassandra-5.0.9 ~/cassandra-src $W/cassandra-run25`, full clone, `ant -Dlocal.repository=$W/m2 build-test`), macOS arm64, JDK 11.0.32.1, Ant 1.10.18. The test class (B2e's skeleton with B2e's imports and the B2e amendment) is kept under `cassandra/stage4-runtime-verification/harness/<stem>/DenylistPerTableTest.java` and copied into the clone's `test/unit/org/apache/cassandra/service/` by `unit-run.sh`, which runs `ant -Dlocal.repository=$W/m2 testsome -Dtest.name=org.apache.cassandra.service.DenylistPerTableTest` once per run label (r1, r2, r3) and copies the JUnit XML and the test log `build/test/logs/**/TEST-org.apache.cassandra.service.DenylistPerTableTest.log`. The test JVM heap is 1024 MiB (`build.xml:1153`, `maxmemory="1024m"`). Instrument check (audit): the class compiles in the run clone (`ant build-test`, `BUILD SUCCESSFUL`). Reason: B2a named a CloudLab path.

**B2b. Knobs.**
- **P (per-table cap).** Set through `StorageProxy.instance.setDenylistMaxKeysPerTable(P)`. Rejection values: 0 and −5. Accepted values: P ∈ {10, 100, 1000, 2500}, which cover below, at and above M/2 and span 250×.
- **Total cap.** `setDenylistMaxKeysTotal(1_000_000)`, so the total cap never binds.

**B2c. Workload.**
1. Create keyspace `dl_ks` (SimpleStrategy 1) with table `t1 (k blob PRIMARY KEY, v int)`.
2. Insert M = 3000 rows into `system_distributed.partition_denylist` for (`dl_ks`, `t1`), each with a distinct 4096-byte random key, via `QueryProcessor.executeInternal`.
3. Run `loadPartitionDenylist()` for each P.

P = 10, 100 and 1000 are below M, so the cap binds. P = 2500 is also below M, so the cap still binds with a large entry: 2500 × 4 KiB ≈ 10 MiB.

**Amendment 2026-10-26 (step-0 audit) — B2c, partitioner and order, from the source.** (i) The unit JVM's partitioner is **ByteOrderedPartitioner** (`test/conf/cassandra.yaml:18`); the skeleton calls `CQLTester.prepareServer()` (`CQLTester.java:360-363` → `ServerTestUtils.prepareServer`), not `prePrepareServer()`, so the Murmur3 switch at `CQLTester.java:418` is not reached. Each token added at `PartitionDenylist.java:442` is then a `BytesToken` holding a **copy** of the key's bytes (`ByteOrderedPartitioner.java:66-69`, `:146-151`; `ByteBufferUtil.getArray` → `Arrays.copyOfRange`, `ByteBufferUtil.java:190-195`), so the entry holds each key's bytes twice (B2f amendment). (ii) The keys are clustering values of one partition (`SystemDistributedKeyspace.java:175-183`), read in clustering (unsigned byte) order, so the entry holds the first P keys in that order; the key `0xff…ff` added by `denylistKey` sorts last. (iii) The per-table limit reaches the read as `limit = min(P, total − 0) = P` on the load path (`:497`, total 1,000,000) and as `P` on the refresh paths (`:388-391`, used at `:206` and `:525`); the query is `LIMIT P+1` (`:404-409`) and the loop stops at P (`:444-446`). Keys beyond P are not loaded, so they are **not denied** (`isKeyPermitted` reads only `entry.keys`, `:318-321`); the only trace is the ERROR at `:425-431`. Reason: the partitioner and the order of the kept keys decide B2f's byte values and which key is dropped.

**B2d. Observables and instruments.** Reach the cache by reflection: `StorageProxy` field `partitionDenylist`, then `PartitionDenylist` field `denylist`, then `asMap()`, then the value's field `keys`. Record:
- `keys.size()`;
- the sum of `key.remaining()`;
- `ObjectSizes.measureDeep(entry)` (jamm, which is on the test classpath);
- the ERROR line "exceeded the per-table allowance" in `build/test/logs/system.log`.

If keys are views over a larger buffer, `measureDeep` counts the whole backing array. For that reason, report both the sum of `remaining()` and `measureDeep`.

**Amendment 2026-10-26 (step-0 audit) — B2d, where each reading is read.** The printed lines (prefix `DLPT `) and the ERROR lines are read from the test log `build/test/logs/**/TEST-…DenylistPerTableTest.log` (the unit JVM routes `System.out` to the logger; the JUnit XML's system-out is empty), not from the XML. The ERROR line is matched by its text `has exceeded the per-table allowance of (<P>)` (`PartitionDenylist.java:425-431`; the violation type is `per-table` because `limit == getDenylistMaxKeysPerTable()` on every path here, `:422-423`). Each held key read from the result is a fresh exact-size array (`LocalDataResponse` serializes the local result and it is deserialized with `ByteBufferUtil.read`, `ReadResponse.java:182-203`, `ByteBufferAccessor.java:100-103`, `ByteBufferUtil.java:444-452`), so `measureDeep` is expected to see no larger backing buffers. Reason: the reading location was a known defect on this machine (repair setter run, defect 1); the deep-size expectation needed the source.

**B2e. Procedure.** Test skeleton:
```java
package org.apache.cassandra.service;
public class DenylistPerTableTest {
  @BeforeClass public static void init() {
    org.apache.cassandra.ServerTestUtils.daemonInitialization();
    org.apache.cassandra.cql3.CQLTester.prepareServer();
    KeyspaceMetadata ks = KeyspaceMetadata.create("dl_ks", KeyspaceParams.simple(1),
        Tables.of(CreateTableStatement.parse("CREATE TABLE t1 (k blob PRIMARY KEY, v int)", "dl_ks").build()));
    SchemaTestUtil.addOrUpdateKeyspace(ks, false);
    DatabaseDescriptor.setPartitionDenylistEnabled(true);
    DatabaseDescriptor.setDenylistConsistencyLevel(ConsistencyLevel.ONE);
    StorageService.instance.initServer(0);
  }
  static Object entry(String t) throws Exception {
    Field f = StorageProxy.class.getDeclaredField("partitionDenylist"); f.setAccessible(true);
    Object pd = f.get(null); Field c = pd.getClass().getDeclaredField("denylist"); c.setAccessible(true);
    com.github.benmanes.caffeine.cache.LoadingCache<TableId, ?> cache = (com.github.benmanes.caffeine.cache.LoadingCache<TableId, ?>) c.get(pd);
    return cache.asMap().get(Schema.instance.getTableMetadata("dl_ks", t).id);
  }
  static Set<ByteBuffer> keys(Object e) throws Exception { Field k = e.getClass().getDeclaredField("keys"); k.setAccessible(true); return (Set<ByteBuffer>) k.get(e); }
  @Test public void perTable() throws Exception {
    Random r = new Random(7);
    for (int i = 0; i < 3000; i++) { byte[] b = new byte[4096]; r.nextBytes(b);
      QueryProcessor.executeInternal("INSERT INTO system_distributed.partition_denylist (ks_name, table_name, key) VALUES (?, ?, ?)", "dl_ks", "t1", ByteBuffer.wrap(b)); }
    StorageProxy.instance.setDenylistMaxKeysTotal(1_000_000);
    for (int bad : new int[]{0, -5}) { try { StorageProxy.instance.setDenylistMaxKeysPerTable(bad); System.out.println("ACCEPTED " + bad); }
      catch (IllegalArgumentException e) { System.out.println("REJECTED " + bad + " getter=" + DatabaseDescriptor.getDenylistMaxKeysPerTable()); } }
    for (int p : new int[]{10, 100, 1000, 2500}) {
      StorageProxy.instance.setDenylistMaxKeysPerTable(p);
      StorageProxy.instance.loadPartitionDenylist();
      Object e = entry("t1"); Set<ByteBuffer> ks = keys(e);
      long raw = ks.stream().mapToLong(ByteBuffer::remaining).sum();
      System.out.printf("P=%d keys=%d rawBytes=%d deep=%d%n", p, ks.size(), raw, org.apache.cassandra.utils.ObjectSizes.measureDeep(e));
    }
    // refresh path: add one key through JMX path with P=100; entry must stay at 100
    StorageProxy.instance.setDenylistMaxKeysPerTable(100); StorageProxy.instance.loadPartitionDenylist();
    StorageProxy.instance.denylistKey("dl_ks", "t1", "ff".repeat(4096));
    System.out.println("afterAdd keys=" + keys(entry("t1")).size());
  }
}
```
Imports: `java.lang.reflect.Field`, `java.nio.ByteBuffer`, `java.util.*`, `org.junit.*`, and the following `org.apache.cassandra` packages:
- `config.DatabaseDescriptor`;
- `cql3.QueryProcessor`;
- `cql3.statements.schema.CreateTableStatement`;
- `db.ConsistencyLevel`;
- `schema.*`.

Run the test three times. The output is in `build/test/output/TEST-org.apache.cassandra.service.DenylistPerTableTest.xml`.

**Amendment 2026-10-26 (step-0 audit) — B2e, instrument fixes and the timer path.** Changes to the skeleton, all in `harness/<stem>/DenylistPerTableTest.java`: (a) every printed line is a single `System.out.println` of one string with prefix `DLPT ` (a `printf` arrives in the test log split into pieces); the `P=` line also prints `getter=`; a `rows=` line after the inserts and a `partitioner=… getter0=` line are added (recorded); (b) after `denylistKey` the line `afterAdd keys=<n> denylistKeyReturned=<bool> addedKeyInEntry=<bool> rows=<n>` is printed, where `addedKeyInEntry` is `keys(entry).contains(0xff…ff)` read from the entry itself (calling `isKeyDenylisted` would go through `denylist.get` and could start a timed refresh); (c) **the timer-refresh path**, which B1 and the Estimate name but the filed procedure did not exercise: `DatabaseDescriptor.setDenylistRefreshSeconds(1)` in `init()` before any cache is built (as `PartitionDenylistTest.java:79` does; `buildEmptyCache` reads it, `PartitionDenylist.java:185`), and after the `afterAdd` line: `setDenylistMaxKeysPerTable(50)` without a load, sleep 1.5 s, one `LoadingCache.get(tid)` (this starts the `refreshAfterWrite` reload, `:201-213`, which re-reads with the current P at `:206` → `:390`), then poll `asMap().get(tid)` every 100 ms for up to 10 s and print `afterTimer keys=<n> waitedMs=<ms>`. `asMap().get` does not start a refresh, so nothing else in the test refreshes. Output: the test log (B2d amendment). Reason: the filed output location is wrong on this build, and the timer path is part of the claim.

**Runbook fix 2026-10-26 (stage 4 run 1, defect 1) — B2e, the unit yaml's read-size guardrail.** Unit attempt 0 failed in all three runs with `ReadSizeAbortException: … system_distributed.partition_denylist has exceeded the size failure threshold of 4,194,304 bytes` (`SelectStatement.java:1057-1077`): `test/conf/cassandra.yaml:63-67` sets `read_thresholds_enabled: true` and `coordinator_read_size_fail_threshold: 4096KiB`, so any read of more than about 1,000 keys of 4 KiB aborts (in the loads at P = 1000 and 2500 that abort would be caught at `PartitionDenylist.java:450-454` and leave an empty entry). The node default is off (`Config.java:526`), and the cluster tier's node does not set it. Fix: `DatabaseDescriptor.setReadThresholdsEnabled(false);` in `init()` (in `harness/<stem>/DenylistPerTableTest.java`); the harness's ERROR count matches `has exceeded the <type> allowance` only, since the guardrail's own message also contains "has exceeded the". B2f–B2h unchanged; the unit tier restarts from its beginning.

**B2f. Predictions.**
- **Rejections.** `REJECTED 0` and `REJECTED -5`, with the getter unchanged at 1000.
- **Key counts.** `keys` = 10, 100, 1000 and 2500 for the four values of P.
- **Raw bytes.** `rawBytes` = keys × 4096, which is 40 960, 409 600, 4 096 000 and 10 240 000.
- **Deep size.** `deep` lies between rawBytes and rawBytes × 1.3 + 64 KiB. The ratio deep(2500)/deep(1000) is 2.5 ± 0.3.
- **ERROR log.** One "exceeded the per-table allowance" line is logged for each load with P < 3000.
- **Refresh path.** `afterAdd keys` = 100. The table now has 3001 rows and the cap still holds on the refresh path.

**Amendment 2026-10-26 (step-0 audit) — B2f, exact values from the source.** (i) **Deep size.** The filed band (rawBytes to rawBytes × 1.3 + 64 KiB) is wrong by the source: with the ByteOrdered partitioner every token copies its key (B2c amendment), so the entry holds about 2.03 × rawBytes. Computed at the audit by `results/<stem>/audit/EntrySize.java`, which builds `PartitionDenylist$DenylistEntry` exactly as `:434-448` does from exact-size keys and measures it with the build's `ObjectSizes.measureDeep` (`audit/audit-entrysize.txt`): **deep = 83,200 · 830,800 · 8,304,368 · 20,756,560** for P = 10, 100, 1000, 2500, each within **±2 %**. The ratio deep(2500)/deep(1000) = 2.4995, inside the filed 2.5 ± 0.3 (kept). (ii) `getter=` equals P on each `P=` line. Rejections: `REJECTED 0` and `REJECTED -5`, getter 1000 (the unit yaml does not set the entry; `Config.java:774`). (iii) **ERROR lines:** exactly **7** `has exceeded the per-table allowance of (…)` lines, with allowances in this order: 10, 100, 1000, 2500 (the four loads), 100 (the load before the add), 100 (the refresh after the add), 50 (the timed refresh). (iv) `afterAdd keys=100`, `denylistKeyReturned=true`, `rows=3001`; `addedKeyInEntry=false` is recorded (the added key sorts last and is beyond the cap, so it is not denied — the dropped-key behaviour, not a row condition). (v) **Timer path:** `afterTimer keys=50` within 10 s. (vi) Every prediction holds in each of the three runs. Reason: the deep band and the ERROR count follow from the source and were wrong or open as filed; the timer path is added (B2e amendment). Changed before any reading.

**B2g. Readings.**

| Observation | Meaning |
|---|---|
| keys = min(P, 3000) and bytes scale with P | Claim confirmed |
| keys = 3000 for every P | Cap not applied (claim wrong) |
| `afterAdd keys` > 100 | Refresh path bypasses the per-table cap (claim wrong on that path) |
| `deep` ≫ rawBytes × 1.3 | Keys retain larger backing buffers: count is capped but bytes per key are not as assumed (scope note, report) |
| 0 or −5 accepted | Check at 4815 not enforced |

**Amendment 2026-10-26 (step-0 audit) — B2g, row 1 and added rows.** Row 1 ("keys = min(P, 3000) and bytes scale with P — claim confirmed") requires all of (i)–(vi) of the B2f amendment in all three runs. Added rows:

| Observation | Meaning |
|---|---|
| keys exact, but `deep` outside ±2 % of the computed value (and not ≫ it) | Count capped; bytes per key differ from the derived structure — **Not confirmed** for bytes (report the per-key size) |
| `deep` ≥ 1.3 × the computed value | Keys or tokens retain larger buffers (the filed "≫" row, now measured against the computed value) — **Not confirmed** for bytes |
| `afterTimer keys` ≠ 50 (e.g. 100: the reload kept the old value) | The timed refresh did not apply P — **Not confirmed** for the timer path |
| ERROR count ≠ 7, or allowances not in the order of B2f (iii) | Disallow evidence differs from the source — **Not confirmed** |
| getter ≠ 1000 after a rejection, or ≠ P after a set | Setter not as traced — **Refuted** for the setter |
| `addedKeyInEntry=true` with `afterAdd keys=100` | The kept order is not clustering order (recorded; the cap still holds by count) |
| the three runs disagree on any count or on deep beyond ±2 % | **Not confirmed** (report) |
| compile or test failure | **Invalid run** |

**B2h. Controls.**
- The total cap is set high so that only P varies.
- The same 3000 rows are used for every P.
- Every P runs a full `load()`, which builds a new cache.
- Three repetitions.

**Amendment 2026-10-26 (step-0 audit) — B2h, controls' evidence.** "Only P varies": the total cap is set to 1,000,000 before the sweep (so `limit = P`, `:497`) and every ERROR line says `per-table`. "Same rows": `rows=3000` before the sweep, `rows=3001` after the add. "A new cache per load": `load()` builds a new cache (`:229-236`). Reason: the controls' evidence was not named.

### B3. Cluster tier

**B3a. Environment and build.** A single Linux node, built from `/local/c509` with `ant jar`. Copy `conf/` to `/local/dn/conf` and set:
- `partition_denylist_enabled: true`;
- `denylist_consistency_level: ONE` (on one node, the default QUORUM over `system_distributed` RF 3 is unavailable);
- `denylist_max_keys_total: 1000000`;
- all data, commitlog, hints, saved_caches and cdc directories under `/local/dn/`.

Set `-Xms2G -Xmx2G` with G1. Start with `CASSANDRA_CONF=/local/dn/conf CASSANDRA_LOG_DIR=/local/dn/logs bin/cassandra -p /local/dn/pid`. At least 5 GB free on `/local` is needed.

**Amendment 2026-10-26 (step-0 audit) — B3a, this host.** One node on 127.0.0.1 from the run clone `$W/cassandra-run25` (built with `build-test`, which includes `jar`). Its conf is generated by the harness's `make-node-conf.sh` into `$W/node-dlmk/conf` from the clone's tag `conf/`, with `cluster_name: dlmk`, listen/rpc 127.0.0.1, data, commitlog, hints, saved_caches and cdc directories under `$W/node-dlmk/`, and B3a's lines `partition_denylist_enabled: true` (default false, `Config.java:759`), `denylist_consistency_level: ONE`, `denylist_max_keys_total: 1000000`. The enforcement flags `denylist_reads_enabled`, `denylist_writes_enabled`, `denylist_range_reads_enabled` default to true (`Config.java:761-765`); they act only on queries to the denied table and do not affect the cache, so they are left at default and read back. The partitioner is Murmur3 (`conf/cassandra.yaml:389`), so each token is a `LongToken` (no key copy). `denylist_refresh` stays 600 s; nothing reads `dl.t1`, so no timed refresh runs. Heap: `MAX_HEAP_SIZE=2G HEAP_NEWSIZE=400M` on the start command (`-Xms2G -Xmx2G`); G1 is the shipped collector (`conf/jvm11-server.options:63`), and no `ExplicitGCInvokesConcurrent` is set, so `GC.run` is a full collection. Start: `CASSANDRA_CONF=$W/node-dlmk/conf CASSANDRA_LOG_DIR=<log dir> nohup bin/cassandra -f`, pid from `$!` (no `setsid` on macOS). Reason: B3a named CloudLab paths.

**B3b. Knobs.** Set `DenylistMaxKeysPerTable` over JMX. It is a write-only attribute of `org.apache.cassandra.db:type=StorageProxy`. Use P ∈ {1000, 5000, 20000}, and try 0, which must be rejected. After each set, invoke the operation `loadPartitionDenylist`. Use this client, saved as `/local/tools/Jmx.java`:
```java
import javax.management.*; import javax.management.remote.*;
public class Jmx { public static void main(String[] a) throws Exception {
  MBeanServerConnection m = JMXConnectorFactory.connect(new JMXServiceURL("service:jmx:rmi:///jndi/rmi://" + a[0] + "/jmxrmi")).getMBeanServerConnection();
  ObjectName sp = new ObjectName("org.apache.cassandra.db:type=StorageProxy");
  if (a[1].equals("set")) { try { m.setAttribute(sp, new Attribute(a[2], Integer.parseInt(a[3]))); System.out.println("OK " + a[3]); } catch (Exception e) { System.out.println("REJECTED " + a[3] + " " + e); } }
  if (a[1].equals("load")) { m.invoke(sp, "loadPartitionDenylist", new Object[0], new String[0]); System.out.println("loaded"); } } }
```
Use it as `java /local/tools/Jmx.java 127.0.0.1:7199 set DenylistMaxKeysPerTable 5000`, then `... load`.

**Amendment 2026-10-26 (step-0 audit) — B3b, names checked and a read-back.** The MBean is `org.apache.cassandra.db:type=StorageProxy` (`StorageProxy.java:189`, registered at `:223`). `DenylistMaxKeysPerTable` is a **write-only attribute** (`StorageProxyMBean.java:82` has the setter and no getter); `loadPartitionDenylist` (`:73`), `denylistKey` and `removeDenylistKey` (`:80-81`) are **operations**. `Jmx.java` exactly as written, saved at `$W/tools-dlmk/Jmx.java`, run in source-file mode from `$W`. Since there is no JMX getter, each set is read back from `system_views.settings` (`SELECT value FROM system_views.settings WHERE name='denylist_max_keys_per_table'`; `SettingsTable.java` lists every `Config` property), and the eight denylist settings are read back once after start. Reason: B3b had no read-back.

**B3c. Workload.**
1. Create the schema: `bin/cqlsh -e "CREATE KEYSPACE dl WITH replication={'class':'SimpleStrategy','replication_factor':1}; CREATE TABLE dl.t1 (k blob PRIMARY KEY, v int);"`.
2. Generate M = 20 000 random 8 KiB keys: `python3 -I -c "import os;f=open('/local/dl.csv','w');[f.write('dl,t1,0x'+os.urandom(8192).hex()+'\n') for _ in range(20000)]"`. The file is about 330 MB.
3. Load the file: `bin/cqlsh -e "COPY system_distributed.partition_denylist (ks_name, table_name, key) FROM '/local/dl.csv' WITH MAXBATCHSIZE=1 AND CHUNKSIZE=50"`.
4. Flush: `bin/nodetool flush system_distributed`.

Arithmetic for the entry size, at about 8 192 + 150 B per key:
- P = 1000 → ≈ 8.0 MiB;
- P = 5000 → ≈ 40 MiB;
- P = 20 000 → ≈ 160 MiB, which is below the 2 GiB heap.

**Amendment 2026-10-26 (step-0 audit) — B3c, this host.** The CSV is written to `$W/node-dlmk/dl.csv` (≈ 330 MB, removed with the node directory); COPY and flush as written, with `cqlsh --request-timeout=120`; afterwards `SELECT count(*) … WHERE ks_name='dl' AND table_name='t1'` must return **20000**. Free disk 137 GiB. Reason: CloudLab paths; the row count decides what P = 20000 can hold.

**B3d. Observables and instruments.**
- After each load, run `jcmd $(cat /local/dn/pid) GC.run` twice, then `jcmd $(cat /local/dn/pid) GC.heap_info` and record the used heap.
- `jcmd <pid> GC.class_histogram | head -20`, recording the `[B` bytes.
- `grep "exceeded the per-table allowance" /local/dn/logs/system.log`.

The per-entry size cannot be read directly. The quantity used is used-heap after GC relative to a baseline, which is taken after an empty load: set P, then load before any rows are inserted.

**Amendment 2026-10-26 (step-0 audit) — B3d, readings, and a post-ingest control.** (i) `used` is the `used NK` figure of `GC.heap_info` after two `GC.run`; `[B` bytes and instances from the `GC.class_histogram` taken right after (`jcmd`, as `jstat` cannot attach on this machine). (ii) For each load, the part of `system.log` written after the load started (byte offset) is searched for `has exceeded the … allowance of (…)`, `Loaded partition denylist cache in …ms` (`PartitionDenylist.java:237`) and `Error reading partition_denylist` / `Error reading full partition denylist` (`:452`, `:508`; a read failure there returns an **empty** entry, which would look like a cap). (iii) **Post-ingest control:** after the insert and flush and before the first P load, the same measurement is taken (`used_i`); the cache is still empty then (the last load ran on an empty table, and nothing reads `dl.t1`), so `used_i − used₀` is the ingest's drift. Every quantity read is persistent (held by the cache until the next load), so a reading after GC sees it; the transient query result (`LIMIT P+1` rows, unpaged: `QueryOptions.forInternalCalls`) is not measured and not predicted. Reason: the readings' sources were open; the baseline is taken before a 330 MB ingest.

**Runbook fix 2026-10-26 (stage 4, cluster shakedown before run 1, defect 2) — B3d, the heap instrument.** The shakedown (M = 2000, not judged) showed that `GC.heap_info`'s `used` figure cannot resolve B3f's bands: with a 2 GiB heap G1 uses 16 MiB regions, and `used` taken after the two `GC.run` already counts the young regions the node's threads allocated since (`2 young (32768K)` in the shakedown's `heap_info`), so it moved by up to ≈ 17 MB between readings with no change in the cache. Fix: "used heap after GC" is read as the **`Total` bytes of `jcmd <pid> GC.class_histogram`**, which forces a full collection and counts only live objects (the B3d amendment already takes this histogram right after); `heap_info` is still recorded. The predicted quantity (live heap after GC), the baseline used₀ (after the empty load), the post-ingest control and every value and band in B3f/B3g are unchanged. The cluster tier's run 1 had not started.

**Amendment 2026-10-27 (after run 1, authorised by the user) — B3d, the heap baseline.** This amendment follows run 1's readings: run 1's cluster tier was Not confirmed only because the baseline used₀, taken after the empty load and **before** the ingest, was 216 MiB below the post-ingest level the loads started from (results file §4). It was written knowing all of run 1's cluster readings (listed in the B3f amendment of this date). Changes: (i) **The baseline is taken after the ingest.** used_b1 is the measurement right after COPY, flush and the row count (run 1's `used_i`); used_b2 = **used_b** is a second measurement taken after a "null label" that does everything a P label does except the load: `Jmx set DenylistMaxKeysPerTable 1000` (the value already stored, `Config.java:774`; the setter only stores it, `DatabaseDescriptor.java:4813-4818`), the `system_views.settings` read-back over cqlsh, 5 s, `GC.run` ×2, `heap_info`, and the class histogram (its Total forces a full GC and counts live objects, runbook fix 2). Δ_P = used_P − used_b. used₀ (after the empty load, before the ingest) is still measured and `used_b1 − used₀` is **recorded** as the ingest residue; it is no longer a condition. (ii) **Why the cache is empty at used_b1 and used_b, from the source.** The last load ran on an empty `partition_denylist`, so `getDenylistForAllTablesFromCQL` returned an empty map (`PartitionDenylist.java:473-475`) and `load()` installed a new cache with no entry (`:222-236`). An entry for `dl.t1` is created only by a later `load()`, a `denylistKey`/`removeDenylistKey` refresh (`:243-286`), or `denylist.get(tid)` in `isKeyPermitted` (`:318`). Nothing reads or writes `dl.t1` before the first P load. The COPY writes go to `system_distributed`, for which `isKeyPermitted` returns before `denylist.get` (`:312`, `canDenylistKeyspace`, `:292-300`). The timed refresh starts only from a `get` (`:185`, 600 s). (iii) **Why the baseline must be shown stable.** After the ingest the heap holds state whose lifetime the source does not bound within this run. Run 1 observed the flushed `heap_buffers` memtable (`conf/cassandra.yaml:825`) of `partition_denylist` still live after the flush: 20,009 `BTreeRow`, ≈ 218 MB of `[B`. That is kept as an observation, not tuned away. So the baseline is used only if used_b1 and used_b agree (B3f (v′)), and a release of that state during the loads shows up as a Δ below its band or as a failed reversal. (iv) Two run-1 instruments are unchanged: the histogram Total as the live heap, and the `system.log` segment per load.

**B3e. Procedure.**
1. Start the node and create the schema.
2. Baseline: run `Jmx load`, `GC.run` ×2 and `heap_info`, giving used₀.
3. Run `Jmx set DenylistMaxKeysPerTable 0`. It must be REJECTED.
4. Insert the CSV and flush.
5. For P in 1000 5000 20000 1000:
   1. Run `set` and then `load`.
   2. Wait 5 s.
   3. Run `GC.run` ×2 and record used_P and the `[B` bytes.
   4. Check the log for the ERROR line.
   The final P = 1000 shows the heap shrinking back.
6. Stop the node with `kill $(cat /local/dn/pid)`, then check that `pgrep -f CassandraDaemon` is empty.

**Amendment 2026-10-26 (step-0 audit) — B3e, run order on this host.** `cluster-run.sh run1 20000 1000 5000 20000 1000`: pre-checks (no Cassandra daemon, ports 7000, 7199, 9042 free), generate conf, start (UN and `statusbinary running`, ≤ 360 s), read back the eight settings, schema, step 2 (`load`, measure → used₀), step 3 (`set 0`, read back), step 4 (CSV, COPY, flush, row count), the post-ingest measurement (`used_i`), then for P in 1000 5000 20000 1000: set, read back, load, segment search, 5 s, `GC.run` ×2, `heap_info`, histogram. Then `nodetool drain`, kill, check, wipe `$W/node-dlmk`. A shakedown of the same script (`cluster-run.sh shake 2000 100 500 2000 100`) runs first and is not judged. Reason: B3e left the bounds, the read-backs and the shakedown open.

**Amendment 2026-10-27 (after run 1, authorised by the user) — B3e, order for the cluster re-run.** This amendment follows run 1's readings (see the B3d amendment of this date). The order is that of the 2026-10-26 amendment, with one step inserted after the post-ingest measurement (used_b1): the **null label** `B2` (B3d amendment (i)), which gives used_b. Nothing else changes: the empty load and used₀, `set 0`, CSV, COPY, flush, row count, then for P in 1000 5000 20000 1000: set, read back, load, segment search, 5 s, `GC.run` ×2, `heap_info`, histogram; drain, kill, check, wipe. The re-run uses a **fresh clone** `$W/cassandra-run65` (`git clone --branch cassandra-5.0.9 ~/cassandra-src $W/cassandra-run65`, `ant -Dlocal.repository=$W/m2 build-test`) and the node root `$W/node-dlmk2`. The commands are `DLMK_C=$W/cassandra-run65 DLMK_NODE=$W/node-dlmk2 DLMK_B2=1 cluster-run.sh shake2 2000 100 500 2000 100` (shakedown, not judged; the self-check runs end to end on it), then the same with `run2 20000 1000 5000 20000 1000`. The whole cluster tier runs again from its beginning; the unit tier is closed and does not re-run.

**B3f. Predictions.** Let Δ_P = used_P − used₀.
- **Heap.** Δ_1000 ≈ 8 MiB, Δ_5000 ≈ 40 MiB and Δ_20000 ≈ 160 MiB, each within ±25 % or ±6 MiB, whichever is larger. Δ_5000 − Δ_1000 ≈ 32 MiB. The final P = 1000 run returns to within 6 MiB of the first P = 1000 run.
- **ERROR log.** The line is logged for P = 1000 and P = 5000. It is not logged for P = 20000, because M = P means that `LIMIT 20001` returns 20000 rows and 20000 > 20000 is false.

**Amendment 2026-10-26 (step-0 audit) — B3f, bands derived and stated, and the other observables.** (i) Per held key the entry costs **8,294.6 B** (computed by `audit/EntrySize.java` with the Murmur3 partitioner and 8,192-byte keys: 8,208 B array + 48 B buffer + 24 B `LongToken` + references), so the derived Δ are **7.91 · 39.55 · 158.2 MiB** for P = 1000, 5000, 20000, inside the filed values. The filed tolerance gives the bands **[2, 14] MiB · [30, 50] MiB · [120, 200] MiB**; Δ_5000 − Δ_1000 (derived 31.64 MiB) in **[24, 40] MiB**; the last P = 1000 within 6 MiB of the first. (ii) Read-back = P after each set; `set 0` → `REJECTED … IllegalArgumentException …` and read-back 1000. (iii) ERROR lines: exactly one per load at P = 1000, 5000 and the last 1000, each `per-table allowance of (P)`; none at P = 20000 and none at the empty load. (iv) No `Error reading` line; one `Loaded partition denylist cache` line per load. (v) Post-ingest control: |used_i − used₀| ≤ 6 MiB. (vi) Recorded, not a row condition: `[B` bytes minus the post-ingest `[B` bytes, expected ≈ P × 8,208 B. Reason: the bands are now derived from the source, and the disallow evidence, read-back and drift control were not stated. Changed before any reading; the filed values stand.

**Amendment 2026-10-27 (after run 1, authorised by the user) — B3f (i) and (v), the heap relation against a post-ingest baseline.** This amendment follows run 1's readings. Relations (i) and (v) above failed in run 1 because used₀ was taken before the ingest. **What was known of run 1 when this was written: all of its cluster readings.** used₀ = 49,242,552 B; post-ingest = 275,852,240 B (drift 216.11 MiB); used_P = 284,156,440 · 317,347,808 · 441,777,784 · 284,197,120 B. So Δ against the post-ingest reading = 7.92 · 39.57 · 158.24 · 7.96 MiB (≈ 8.3 KB per key), Δ_5000 − Δ_1000 = 31.65 MiB, and the last P = 1000 was 40,680 B above the first. No number below is taken from these readings. Each comes from the source (centre) or from the filed tolerance (width).
- **(i′) Δ_P = used_P − used_b** (B3d amendment of this date).
  - **Centre: the entry's live size, derived from its structures.** For each held key, the source and bytecode give:
    - a fresh exact-size `HeapByteBuffer` over a `byte[8192]` (B2d amendment: `ReadResponse.java:182-203`, `ByteBufferUtil.java:444-452`): 16 + 8,192 = **8,208 B** for the array, and **48 B** for the buffer (JDK 11 `javap`: `Buffer` has 4 ints and 1 long; `ByteBuffer` has 1 reference, 1 int and 3 booleans; a 12 B header, rounded up to 8 B);
    - a Murmur3 `LongToken` (`PartitionDenylist.java:442`; one `long`): **24 B**;
    - one reference in `RegularImmutableSet.elements` and one in the `RegularImmutableList.array` behind `RegularImmutableSortedSet` (Guava 32.0.1 `javap`, from `ImmutableSet.copyOf` / `ImmutableSortedSet.copyOf` at `:448`): **4 + 4 B**.
  - That makes **8,288 B per key**. Add the hash table of `RegularImmutableSet`, 4·T(P) B, where T(P) = `ImmutableSet.chooseTableSize(P)` (bytecode: `highestOneBit(P−1) << 1`, doubled while T·0.7 < P), so T = 2,048 · 8,192 · 32,768. Add 176 B of fixed headers (the entry, two sets, one list, three array headers and the natural-order comparator). The result is **entry(P) = 8,288·P + 4·T(P) + 176 = 8,296,368 · 41,472,944 · 165,891,248 B (7.912 · 39.552 · 158.206 MiB)** for P = 1000 · 5000 · 20000. These equal, to the byte, the audit probe's `measureDeep` values (`audit/audit-entrysize.txt`, 2026-10-26, before any reading).
  - **Other heap a load leaves live, from the source: independent of P and ≪ 1 MiB.**
    - `load()` replaces the cache with one built the same way (`:222-236`, `buildEmptyCache` `:180-213`), so the difference is one cache node.
    - The statement is parsed and not cached (`QueryProcessor.java:382-392`, `:345-348`, `:893-905`).
    - The chunk cache is off (`file_cache_enabled` default false, `Config.java:499`, `conf/cassandra.yaml:742`), so no per-chunk heap objects grow with P.
    - The key cache holds at most one entry per SSTable for the one denylist partition.
    - The `UntypedResultSet` of the read is a local of `getDenylistForTableFromCQL` (`:413`) and is garbage once the load returns. The histogram's full GC removes it.
    - The comparator is a shared singleton, already live (−24 B).
  - **Bands: the filed tolerance (±25 % or ±6 MiB, whichever is larger; B3f) around these centres, not narrowed.** Δ_1000 and the last Δ_1000 in **[1.91, 13.91] MiB**; Δ_5000 in **[29.66, 49.44] MiB**; Δ_20000 in **[118.65, 197.76] MiB**. Δ_5000 − Δ_1000 (centre 33,176,576 B = 31.64 MiB) in **[23.73, 39.55] MiB**. The last P = 1000 within **6 MiB** of the first (as filed).
- **(v′) Baseline stability (replaces (v)):** |used_b − used_b1| ≤ **6 MiB** (the filed 6 MiB). `used_b1 − used₀` is recorded, not a condition.
- (ii), (iii), (iv) and (vi) are unchanged. For (vi), the `[B` bytes are now taken relative to used_b's histogram, expected ≈ P × 8,208 B. Also recorded, not a condition: `HeapByteBuffer` instances relative to used_b, expected +P.

**Would run 1 pass these relations?** Taking run 1's post-ingest reading as used_b, its Δ (7.92 · 39.57 · 158.24 · 7.96 MiB), difference (31.65 MiB) and reversal (0.04 MiB) all lie inside (i′). But run 1 has no second post-ingest reading, so (v′) cannot be evaluated, and under the amended table run 1 falls in the row "used_b missing" (B3g amendment of this date), **Not confirmed**. The widths are the filed ones and were not narrowed after seeing run 1's 0.7 % agreement. The centres differ from the 2026-10-26 ones (7.91 · 39.55 · 158.2 MiB) only by rounding.

**B3g. Readings.**

| Observation | Meaning |
|---|---|
| Δ tracks min(P, M) × 8 KiB and shrinks back when P is lowered | Claim confirmed on a node |
| Δ ≈ 160 MiB for every P | Cap not governing the held keys (claim wrong) |
| Δ grows with P but by ≫ 8 KiB/key | Keys retain larger buffers; cap holds by count, bytes per key larger than assumed |
| 0 accepted | Check 4815 not enforced |

**Amendment 2026-10-26 (step-0 audit) — B3g, row 1 and added rows.** Row 1 ("Δ tracks min(P, M) × 8 KiB and shrinks back when P is lowered — claim confirmed on a node") requires all of (i)–(v) of the B3f amendment and 20000 rows. Added rows:

| Observation | Meaning |
|---|---|
| an `Error reading …` line in a load, or a load that fails | The entry may be empty because the read failed, not because of the cap — **Invalid** for that value |
| row count ≠ 20000 | M is not as designed — **Invalid** |
| read-back ≠ P after a set | The value did not reach the node — **Invalid** |
| abs(used_i − used₀) > 6 MiB | The baseline moved with the ingest; absolute Δ not interpretable — **Not confirmed** (Δ against used_i and the differences reported) |
| Δ inside its band for some P and not others, or Δ_5000 − Δ_1000 outside [24, 40] MiB | **Not confirmed** (report which) |
| ERROR lines not as in B3f (iii) | Disallow evidence differs from the source — **Not confirmed** |
| the last P = 1000 not within 6 MiB of the first | Not reversible, or heap grows over time — **Not confirmed** |
| node fails to start or dies | **Invalid run** |

**Amendment 2026-10-27 (after run 1, authorised by the user) — B3g, row 1 and the baseline rows.** This amendment follows run 1's readings (run 1 matched the row "abs(used_i − used₀) > 6 MiB", Not confirmed). Row 1 now requires (i′), (ii)–(iv) and (v′) of the B3f amendment of this date, plus 20000 rows. The row "abs(used_i − used₀) > 6 MiB" no longer applies: that difference is recorded as the ingest residue. In the row "Δ inside its band for some P and not others…", Δ is against used_b and the difference band is [23.73, 39.55] MiB. The other rows are unchanged. Added rows:

| Observation | Meaning |
|---|---|
| used_b missing (no null-label histogram), or abs(used_b − used_b1) > 6 MiB | The post-ingest baseline is not shown stable — **Not confirmed** (Δ against used_b1 and used_b reported) |
| every Δ (vs used_b) below its band, or any Δ < 0 | The post-ingest state was released during the loads, or the entry is not held — **Not confirmed** (report the histogram classes) |
| every Δ above its band by a similar amount, with the difference and reversal inside | The baseline moved up between used_b and the first load — **Not confirmed** (report) |

**B3h. Controls.**
- The same rows are used for every P.
- The total cap is set high.
- The baseline is taken after an empty load.
- Two forced GCs run before every reading.
- Lowering P again shows that the change is reversible and is not due to heap growth over time.

**Amendment 2026-10-26 (step-0 audit) — B3h, controls' evidence.** "Same rows": the row count after flush; no write follows. "Total cap high": read back from `system_views.settings`, and every ERROR line says `per-table`. "Baseline after an empty load": the base `Loaded …` line; plus the post-ingest control (B3d amendment). "Two forced GCs": the command log. Reason: the controls' evidence was not named.

**Amendment 2026-10-27 (after run 1, authorised by the user) — B3h, the baseline control.** This amendment follows run 1's readings (B3d amendment of this date). "The baseline is taken after an empty load" now reads: **the baseline is taken after the ingest and flush, with the cache still empty from the last (empty) load** (B3d amendment (ii)). It is the histogram Total after a forced full GC at the null label (used_b). It is checked against the first post-ingest reading (B3f (v′)). The empty-load reading used₀ is kept and recorded. The other controls are unchanged.

**B4. Risks and cleanup.**
- **Unit tier.** About 12 MB of rows. Afterwards run `rm -rf /local/c509/build/test/cassandra`.
- **Cluster tier.** Clean up as follows:
  1. Remove the CSV: `rm /local/dl.csv`.
  2. Stop the node with `kill $(cat /local/dn/pid)`.
  3. Check that `pgrep -f CassandraDaemon` and `pgrep -f cqlsh` are both empty.
  4. Remove the node directory: `rm -rf /local/dn`.
- **Shared clone.** Never write in the shared clone.

**Amendment 2026-10-26 (step-0 audit) — B4, this host.** Node data and the CSV under `$W/node-dlmk` (≈ 0.7 GB with the commit log), wiped before and after; full logs under `$W/logs/denylist_max_keys_per_table-setDenylistMaxKeysPerTable/`; at the end `ps -eo command | grep '[C]assandraDaemon'`, `pgrep -f cqlsh`, `pgrep jcmd` empty; the copied test is removed from the run clone and `build/test/cassandra` cleaned after the unit runs; the clone's `test/conf` is left as checked out. Reason: CloudLab paths.

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

**2026-10-26 — stage 4 run 1 (Claude Opus 5.5, claude-opus-5-5; uncommitted).** Results: [`../../stage4-runtime-verification/results/denylist_max_keys_per_table-setDenylistMaxKeysPerTable-value--autonomous.md`](../../stage4-runtime-verification/results/denylist_max_keys_per_table-setDenylistMaxKeysPerTable-value--autonomous.md).
- **Verdict.** Unit: **Confirmed — caps** (B2g row 1: keys = P at 10, 100, 1000, 2500, after a JMX add (100) and after a timed refresh (50); deep size exactly as computed from the source, 83,200 · 830,800 · 8,304,368 · 20,756,560 B; 0 and −5 rejected; 7 ERROR lines as derived; three identical runs). Cluster: **Not confirmed — caps (per table)** (added B3g row "baseline moved with the ingest": the empty-load baseline was 216 MiB below the post-ingest level; against the post-ingest control Δ = 7.92 / 39.57 / 158.24 / 7.96 MiB for P = 1000 / 5000 / 20000 / 1000, inside every band, 8.3 KB per 8 KiB key; read-backs, rejection, ERROR lines, difference and reversal exact).
- **Audit findings on this file.** (1) The unit tier runs with the unit yaml's **ByteOrdered** partitioner, whose `BytesToken` copies each key, so the entry is ≈ 2.03 × the key bytes; the filed band (≤ raw × 1.3 + 64 KiB) would have matched the "larger backing buffers" row for the wrong reason. (2) The timer-refresh path named in B1 had no step. (3) The output is in the test log, and `printf` splits there. (4) No JMX getter exists; `system_views.settings` gives the read-back.
- **Runbook defects.** (1) `test/conf/cassandra.yaml:63-67` enables read thresholds (4096KiB coordinator fail), which aborts the denylist read above ≈ 1000 keys of 4 KiB; fixed in the test's `init()`. (2) `GC.heap_info` `used` includes young regions allocated after the GC (16 MiB regions); the live heap is read from the class histogram's Total.
- **For stage 3.** (a) Take a heap baseline after the ingest (the filed one, before it, includes a flushed `heap_buffers` memtable that stayed referenced: 20,009 `BTreeRow`, ≈ 218 MB of slab arrays). (b) A2 could note that per-key heap depends on the partitioner (ByteOrdered doubles it) and that the transient `LIMIT P+1` result is unpaged (`QueryOptions.forInternalCalls`) and is held in serialized and deserialized form during each read; the cap bounds it only through the LIMIT. (c) A finding on the read-size guardrail, not this constraint: with `read_thresholds_enabled` and a coordinator fail threshold below about P × key size, every denylist read aborts and the catch at `PartitionDenylist.java:450-454` installs an **empty** entry, so no key of that table is denied.

**2026-10-27 — stage 4 cluster re-run "run 1b" (Claude Opus 5.5, claude-opus-5-5; authorised by the user, Yang, the advisor, on 2026-10-27; uncommitted).** Results: same file, §7 and §8.
- **Re-freeze.** Five dated amendments, each headed `Amendment 2026-10-27 (after run 1, authorised by the user)`: B3d, B3e, B3f (i) and (v), B3g, B3h. They take the heap baseline after the ingest, at a null label, and centre the bands on the entry's live size derived from its structures (8,288·P + 4·T(P) + 176 B), keeping the filed tolerance. They were written knowing all of run 1's readings, and say so. New sha256 `e15e95b1…1e74` (new row in `_INDEX.md` §4). B1, B3f (ii)–(iv), (vi) and the unit tier are unchanged.
- **Verdict (cluster re-run).** **Confirmed — caps (per table)**: B3g row 1 read with (i′) and (v′).
  - Δ above the post-ingest baseline is 7.929 / 39.584 / 158.250 / 7.964 MiB for P = 1000 / 5000 / 20000 / 1000. The derived entry sizes are 7.912 / 39.552 / 158.206 MiB; Δ − entry is 17.7 / 33.6 / 45.5 / 55.0 KB.
  - The baseline was stable: the null label read 7,656 B above the post-ingest reading.
  - Δ_5000 − Δ_1000 = 31.655 MiB; reversal 37,352 B.
  - Read-backs exact; `set 0` rejected with read-back 1000; ERROR lines (1000), (5000), none, (1000); no read error.
  - `HeapByteBuffer` +P exactly; `[B` 8,208.5–8,219 B per key.
  - The unit tier stays Confirmed — caps (run 1, closed). The run-1 cluster verdict (Not confirmed) stays on record.
- **Observation kept from run 1, seen again.** The ingest leaves 226 MiB live in this run (216 MiB in run 1): 20,009 `BTreeRow` of the flushed `heap_buffers` memtable of `partition_denylist`, constant through every later reading. It is recorded, not a condition.
- **For stage 3.** A heap baseline for a cache filled from a system table must be taken after the ingest, and shown stable. The pre-ingest baseline of B3d was the only failed part of run 1.
