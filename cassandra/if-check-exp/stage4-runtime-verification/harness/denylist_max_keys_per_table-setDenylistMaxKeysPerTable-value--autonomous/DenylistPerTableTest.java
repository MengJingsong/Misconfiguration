/*
 * Stage-4 harness, denylist_max_keys_per_table-setDenylistMaxKeysPerTable-value--autonomous, unit tier (B2).
 * B2e's skeleton with B2e's imports, plus the step-0 audit amendments of 2026-10-26 (marked "AMENDMENT"):
 *  (a) every printed line is one println of one String (no printf), prefixed "DLPT ", because the unit JVM routes System.out to
 *      the test log and splits a printf into pieces (lesson from the repair_session_max_tree_depth setter run);
 *  (b) membership of the added key is read from the entry itself (no cache access, so no refresh is triggered);
 *  (c) the timer-refresh path: denylist_refresh = 1 s (set in init, as PartitionDenylistTest.java:79 does, before any cache is built),
 *      then P = 50 without a load, wait 1.5 s, one LoadingCache.get() (triggers the refreshAfterWrite reload,
 *      PartitionDenylist.java:185, 201-213), poll the entry for up to 10 s.
 * Runbook fix 2026-10-26 (defect 1): read thresholds disabled in init (the unit yaml enables them; the node default is off).
 */
package org.apache.cassandra.service;

import java.lang.reflect.Field;
import java.nio.ByteBuffer;
import java.util.*;

import org.junit.*;

import org.apache.cassandra.config.DatabaseDescriptor;
import org.apache.cassandra.cql3.QueryProcessor;
import org.apache.cassandra.cql3.statements.schema.CreateTableStatement;
import org.apache.cassandra.db.ConsistencyLevel;
import org.apache.cassandra.schema.*;

public class DenylistPerTableTest {
  @BeforeClass public static void init() {
    org.apache.cassandra.ServerTestUtils.daemonInitialization();
    org.apache.cassandra.cql3.CQLTester.prepareServer();
    KeyspaceMetadata ks = KeyspaceMetadata.create("dl_ks", KeyspaceParams.simple(1),
        Tables.of(CreateTableStatement.parse("CREATE TABLE t1 (k blob PRIMARY KEY, v int)", "dl_ks").build()));
    SchemaTestUtil.addOrUpdateKeyspace(ks, false);
    DatabaseDescriptor.setPartitionDenylistEnabled(true);
    DatabaseDescriptor.setDenylistConsistencyLevel(ConsistencyLevel.ONE);
    DatabaseDescriptor.setDenylistRefreshSeconds(1); // AMENDMENT (c)
    // RUNBOOK FIX 2026-10-26 (defect 1): test/conf/cassandra.yaml:63-67 enables read thresholds with a 4096KiB coordinator fail
    // threshold, which aborts every read of more than ~1000 4-KiB denylist keys (ReadSizeAbortException); the node default is off
    // (Config.java:526).
    DatabaseDescriptor.setReadThresholdsEnabled(false);
    StorageService.instance.initServer(0);
  }
  static Object cacheObj() throws Exception {
    Field f = StorageProxy.class.getDeclaredField("partitionDenylist"); f.setAccessible(true);
    Object pd = f.get(null); Field c = pd.getClass().getDeclaredField("denylist"); c.setAccessible(true);
    return c.get(pd);
  }
  @SuppressWarnings("unchecked")
  static Object entry(String t) throws Exception {
    com.github.benmanes.caffeine.cache.LoadingCache<TableId, ?> cache = (com.github.benmanes.caffeine.cache.LoadingCache<TableId, ?>) cacheObj();
    return cache.asMap().get(Schema.instance.getTableMetadata("dl_ks", t).id);
  }
  @SuppressWarnings("unchecked")
  static Set<ByteBuffer> keys(Object e) throws Exception { Field k = e.getClass().getDeclaredField("keys"); k.setAccessible(true); return (Set<ByteBuffer>) k.get(e); }
  static void out(String s) { System.out.println("DLPT " + s); } // AMENDMENT (a)
  @SuppressWarnings("unchecked")
  @Test public void perTable() throws Exception {
    Random r = new Random(7);
    for (int i = 0; i < 3000; i++) { byte[] b = new byte[4096]; r.nextBytes(b);
      QueryProcessor.executeInternal("INSERT INTO system_distributed.partition_denylist (ks_name, table_name, key) VALUES (?, ?, ?)", "dl_ks", "t1", ByteBuffer.wrap(b)); }
    out("rows=" + QueryProcessor.executeInternal("SELECT key FROM system_distributed.partition_denylist WHERE ks_name='dl_ks' AND table_name='t1'").size());
    out("partitioner=" + StorageService.instance.getTokenMetadata().partitioner.getClass().getSimpleName() + " getter0=" + DatabaseDescriptor.getDenylistMaxKeysPerTable());
    StorageProxy.instance.setDenylistMaxKeysTotal(1_000_000);
    for (int bad : new int[]{0, -5}) { try { StorageProxy.instance.setDenylistMaxKeysPerTable(bad); out("ACCEPTED " + bad + " getter=" + DatabaseDescriptor.getDenylistMaxKeysPerTable()); }
      catch (IllegalArgumentException e) { out("REJECTED " + bad + " getter=" + DatabaseDescriptor.getDenylistMaxKeysPerTable() + " msg=" + e.getMessage()); } }
    for (int p : new int[]{10, 100, 1000, 2500}) {
      StorageProxy.instance.setDenylistMaxKeysPerTable(p);
      StorageProxy.instance.loadPartitionDenylist();
      Object e = entry("t1"); Set<ByteBuffer> ks = keys(e);
      long raw = ks.stream().mapToLong(ByteBuffer::remaining).sum();
      out(String.format("P=%d getter=%d keys=%d rawBytes=%d deep=%d", p, DatabaseDescriptor.getDenylistMaxKeysPerTable(), ks.size(), raw, org.apache.cassandra.utils.ObjectSizes.measureDeep(e)));
    }
    // refresh path: add one key through JMX path with P=100; entry must stay at 100
    StorageProxy.instance.setDenylistMaxKeysPerTable(100); StorageProxy.instance.loadPartitionDenylist();
    out("beforeAdd keys=" + keys(entry("t1")).size());
    String added = "ff".repeat(4096);
    boolean ok = StorageProxy.instance.denylistKey("dl_ks", "t1", added);
    Set<ByteBuffer> after = keys(entry("t1"));
    byte[] ab = new byte[4096]; Arrays.fill(ab, (byte) 0xff);
    out("afterAdd keys=" + after.size() + " denylistKeyReturned=" + ok + " addedKeyInEntry=" + after.contains(ByteBuffer.wrap(ab)) // AMENDMENT (b)
        + " rows=" + QueryProcessor.executeInternal("SELECT key FROM system_distributed.partition_denylist WHERE ks_name='dl_ks' AND table_name='t1'").size());
    // AMENDMENT (c): timer-refresh path
    StorageProxy.instance.setDenylistMaxKeysPerTable(50);
    out("timer set P=50 getter=" + DatabaseDescriptor.getDenylistMaxKeysPerTable() + " keysBeforeWait=" + keys(entry("t1")).size());
    Thread.sleep(1500);
    TableId tid = Schema.instance.getTableMetadata("dl_ks", "t1").id;
    Object got = ((com.github.benmanes.caffeine.cache.LoadingCache<TableId, Object>) cacheObj()).get(tid);
    out("timer get returned keys=" + keys(got).size());
    long t0 = System.currentTimeMillis(); int n = keys(entry("t1")).size();
    while (n == 100 && System.currentTimeMillis() - t0 < 10_000) { Thread.sleep(100); n = keys(entry("t1")).size(); }
    out("afterTimer keys=" + n + " waitedMs=" + (System.currentTimeMillis() - t0));
  }
}
