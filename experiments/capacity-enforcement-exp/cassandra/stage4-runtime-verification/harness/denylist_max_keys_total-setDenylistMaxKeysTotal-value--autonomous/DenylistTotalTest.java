/*
 * Stage-4 harness, denylist_max_keys_total-setDenylistMaxKeysTotal-value--autonomous, unit tier (B2).
 * B2e's skeleton with B2e's imports, plus the step-0 audit amendments of 2026-10-26 (marked "AMENDMENT"):
 *  (a) the test method is renamed totalCap(): the skeleton's static long total() and @Test void total() had the same signature;
 *  (b) every printed line is one println of one String, prefixed "DLT " (a printf is split in the test log);
 *  (c) read thresholds disabled in init() (test/conf/cassandra.yaml:63-67; the node default is off, Config.java:526);
 *  (d) rows per table, partitioner and getters printed; rejection lines print the message; getter printed after each set;
 *  (e) per-table counts, raw bytes and measureDeep for phase A and phase B; phase B also prints replaced= (entries whose object
 *      differs from the phase-A one: every refresh builds a new DenylistEntry) and reloadReads= (increase of the read count of
 *      system_distributed.partition_denylist across the phase-B loop).
 * Steps, values, sleeps, the poll loop and its stop condition are B2e's.
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

public class DenylistTotalTest {
  @BeforeClass public static void init() {
    org.apache.cassandra.ServerTestUtils.daemonInitialization();
    org.apache.cassandra.cql3.CQLTester.prepareServer();
    List<TableMetadata> ts = new ArrayList<>();
    for (int i = 1; i <= 5; i++) ts.add(CreateTableStatement.parse("CREATE TABLE t" + i + " (k blob PRIMARY KEY, v int)", "dl_ks").build());
    SchemaTestUtil.addOrUpdateKeyspace(KeyspaceMetadata.create("dl_ks", KeyspaceParams.simple(1), Tables.of(ts)), false);
    DatabaseDescriptor.setPartitionDenylistEnabled(true);
    DatabaseDescriptor.setDenylistConsistencyLevel(ConsistencyLevel.ONE);
    DatabaseDescriptor.setReadThresholdsEnabled(false); // AMENDMENT (c)
    StorageService.instance.initServer(0);
  }
  @SuppressWarnings("unchecked")
  static Map<TableId, Object> cacheMap() throws Exception {
    Field f = StorageProxy.class.getDeclaredField("partitionDenylist"); f.setAccessible(true); Object pd = f.get(null);
    Field c = pd.getClass().getDeclaredField("denylist"); c.setAccessible(true);
    return (Map<TableId, Object>) ((com.github.benmanes.caffeine.cache.LoadingCache<TableId, ?>) c.get(pd)).asMap();
  }
  static long total() throws Exception {
    Map<?, ?> m = cacheMap(); long s = 0;
    for (Object e : m.values()) { Field k = e.getClass().getDeclaredField("keys"); k.setAccessible(true); s += ((Set<?>) k.get(e)).size(); }
    return s;
  }
  @SuppressWarnings("unchecked")
  static Set<ByteBuffer> keys(Object e) throws Exception { Field k = e.getClass().getDeclaredField("keys"); k.setAccessible(true); return (Set<ByteBuffer>) k.get(e); }
  static TableId tid(int t) { return Schema.instance.getTableMetadata("dl_ks", "t" + t).id; }
  static void out(String s) { System.out.println("DLT " + s); } // AMENDMENT (b)
  static long reads() { return org.apache.cassandra.db.ColumnFamilyStore.getIfExists("system_distributed", "partition_denylist").metric.readLatency.latency.getCount(); }
  // AMENDMENT (e): one line per phase with per-table count/raw/deep and totals; returns the entry objects
  static Object[] snapshot(String label) throws Exception {
    Map<TableId, Object> m = cacheMap(); Object[] es = new Object[6];
    StringBuilder per = new StringBuilder(); long tot = 0, raw = 0, deep = 0;
    for (int t = 1; t <= 5; t++) {
      Object e = m.get(tid(t)); es[t] = e;
      if (e == null) { per.append(" t").append(t).append("=absent"); continue; }
      Set<ByteBuffer> ks = keys(e); long r = ks.stream().mapToLong(ByteBuffer::remaining).sum(); long d = org.apache.cassandra.utils.ObjectSizes.measureDeep(e);
      per.append(" t").append(t).append("=").append(ks.size()).append("/").append(r).append("/").append(d);
      tot += ks.size(); raw += r; deep += d;
    }
    out(label + " total=" + tot + " rawBytes=" + raw + " deep=" + deep + " perTable(keys/raw/deep):" + per + " cacheEntries=" + m.size());
    return es;
  }
  @Test public void totalCap() throws Exception { // AMENDMENT (a)
    Random r = new Random(11);
    for (int t = 1; t <= 5; t++) for (int i = 0; i < 2000; i++) { byte[] b = new byte[2048]; r.nextBytes(b);
      QueryProcessor.executeInternal("INSERT INTO system_distributed.partition_denylist (ks_name, table_name, key) VALUES (?, ?, ?)", "dl_ks", "t" + t, ByteBuffer.wrap(b)); }
    for (int t = 1; t <= 5; t++) // AMENDMENT (d)
      out("rows t" + t + "=" + QueryProcessor.executeInternal("SELECT key FROM system_distributed.partition_denylist WHERE ks_name='dl_ks' AND table_name='t" + t + "'").size());
    out("partitioner=" + StorageService.instance.getTokenMetadata().partitioner.getClass().getSimpleName() + " getterTotal0=" + DatabaseDescriptor.getDenylistMaxKeysTotal() + " getterPerTable0=" + DatabaseDescriptor.getDenylistMaxKeysPerTable());
    for (int bad : new int[]{0, -1}) { try { StorageProxy.instance.setDenylistMaxKeysTotal(bad); out("ACCEPTED " + bad + " getter=" + DatabaseDescriptor.getDenylistMaxKeysTotal()); }
      catch (IllegalArgumentException e) { out("REJECTED " + bad + " getter=" + DatabaseDescriptor.getDenylistMaxKeysTotal() + " msg=" + e.getMessage()); } }
    StorageProxy.instance.setDenylistMaxKeysPerTable(2000);
    for (int T : new int[]{1000, 3000, 10000}) {
      DatabaseDescriptor.setDenylistRefreshSeconds(1);
      StorageProxy.instance.setDenylistMaxKeysTotal(T);
      out("T=" + T + " set getter=" + DatabaseDescriptor.getDenylistMaxKeysTotal() + " perTableGetter=" + DatabaseDescriptor.getDenylistMaxKeysPerTable() + " refresh=" + DatabaseDescriptor.getDenylistRefreshSeconds());
      StorageProxy.instance.loadPartitionDenylist();
      out("T=" + T + " phaseA total=" + total());
      Object[] a = snapshot("T=" + T + " phaseA");
      long reads0 = reads();
      long prev = -1, stableSince = System.currentTimeMillis(), start = System.currentTimeMillis(); Thread.sleep(2000);
      while (System.currentTimeMillis() - start < 12000) {
        for (int t = 1; t <= 5; t++) StorageProxy.instance.isKeyDenylisted("dl_ks", "t" + t, "00");
        Thread.sleep(500); long cur = total(); if (cur != prev) { prev = cur; stableSince = System.currentTimeMillis(); }
        else if (System.currentTimeMillis() - stableSince > 2000) break;
      }
      long elapsed = System.currentTimeMillis() - start;
      out("T=" + T + " phaseB total=" + prev);
      Object[] b = snapshot("T=" + T + " phaseB");
      int replaced = 0; for (int t = 1; t <= 5; t++) if (a[t] != b[t]) replaced++;
      out("T=" + T + " phaseB replaced=" + replaced + " reloadReads=" + (reads() - reads0) + " loopMs=" + elapsed);
    }
  }
}
