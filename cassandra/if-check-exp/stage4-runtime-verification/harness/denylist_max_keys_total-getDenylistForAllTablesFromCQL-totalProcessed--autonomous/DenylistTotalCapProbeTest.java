/*
 * Stage-4 harness, denylist_max_keys_total-getDenylistForAllTablesFromCQL-totalProcessed--autonomous, unit tier (B2 as amended
 * 2026-10-26, sha256 61bab981...28f9).
 * B2c workload (4 tables x 200 keys of 1024 B in system_distributed.partition_denylist), B2d readings by reflection on
 * StorageProxy.partitionDenylist -> denylist.asMap(), B2e procedure: control (flag off, initialLoad), phase 1 (T = 1, 150, 450,
 * 799, 800, 10000; refresh 3600 s; per table 200), phase 2 (refresh 1 s, T = 150, 30 polls of isKeyPermitted on t1..t4).
 * Every line is one println with prefix "DLP " (read from the test log). "DLP MARK <label>" opens each segment.
 * Shakedown only: environment DLP_SHAKE=1 switches to 20 rows per table, per table 20, T = 1, 30, 10000, phase 2 T = 15.
 */
package org.apache.cassandra.schema;

import java.lang.reflect.Field;
import java.nio.ByteBuffer;
import java.util.*;

import org.junit.BeforeClass;
import org.junit.Test;

import org.apache.cassandra.ServerTestUtils;
import org.apache.cassandra.config.DatabaseDescriptor;
import org.apache.cassandra.cql3.CQLTester;
import org.apache.cassandra.cql3.QueryProcessor;
import org.apache.cassandra.cql3.statements.schema.CreateTableStatement;
import org.apache.cassandra.db.ColumnFamilyStore;
import org.apache.cassandra.db.ConsistencyLevel;
import org.apache.cassandra.service.StorageProxy;
import org.apache.cassandra.service.StorageService;
import org.apache.cassandra.utils.ByteBufferUtil;

public class DenylistTotalCapProbeTest
{
    static final boolean SHAKE = "1".equals(System.getenv("DLP_SHAKE"));
    static final int ROWS = SHAKE ? 20 : 200;
    static final int PER_TABLE = SHAKE ? 20 : 200;
    static final int[] TS = SHAKE ? new int[]{ 1, 30, 10000 } : new int[]{ 1, 150, 450, 799, 800, 10000 };
    static final int T2 = SHAKE ? 15 : 150;
    static final int KEYLEN = 1024;

    @BeforeClass
    public static void init()
    {
        ServerTestUtils.daemonInitialization();
        CQLTester.prepareServer();
        List<TableMetadata> ts = new ArrayList<>();
        for (int i = 1; i <= 4; i++)
            ts.add(CreateTableStatement.parse("CREATE TABLE t" + i + " (k blob PRIMARY KEY, v int)", "dlprobe").build());
        SchemaTestUtil.addOrUpdateKeyspace(KeyspaceMetadata.create("dlprobe", KeyspaceParams.simple(1), Tables.of(ts)), false);
        DatabaseDescriptor.setPartitionDenylistEnabled(true);
        DatabaseDescriptor.setDenylistConsistencyLevel(ConsistencyLevel.ONE);
        StorageService.instance.initServer(0);
    }

    static void out(String s) { System.out.println("DLP " + s); }

    static PartitionDenylist pd() throws Exception
    {
        Field f = StorageProxy.class.getDeclaredField("partitionDenylist");
        f.setAccessible(true);
        return (PartitionDenylist) f.get(null);
    }

    @SuppressWarnings("unchecked")
    static Map<TableId, Object> cacheMap() throws Exception
    {
        PartitionDenylist p = pd();
        Field c = PartitionDenylist.class.getDeclaredField("denylist");
        c.setAccessible(true);
        return (Map<TableId, Object>) ((com.github.benmanes.caffeine.cache.LoadingCache<TableId, ?>) c.get(p)).asMap();
    }

    @SuppressWarnings("unchecked")
    static Set<ByteBuffer> field(Object e, String name) throws Exception
    {
        Field k = e.getClass().getDeclaredField(name);
        k.setAccessible(true);
        return (Set<ByteBuffer>) k.get(e);
    }

    static TableId tid(int t) { return Schema.instance.getTableMetadata("dlprobe", "t" + t).id; }

    static long totalK() throws Exception
    {
        long s = 0;
        for (Object e : cacheMap().values()) s += field(e, "keys").size();
        return s;
    }

    static long reads()
    {
        return ColumnFamilyStore.getIfExists("system_distributed", "partition_denylist").metric.readLatency.latency.getCount();
    }

    /** One line: totals K, tokens, B, R, noArray, cacheEntries and per table keys/tokens/B/R. Returns the entry objects. */
    static Object[] snapshot(String label) throws Exception
    {
        Map<TableId, Object> m = cacheMap();
        Object[] es = new Object[5];
        StringBuilder per = new StringBuilder();
        long k = 0, tk = 0, b = 0, r = 0, noArray = 0;
        for (int t = 1; t <= 4; t++)
        {
            Object e = m.get(tid(t));
            es[t] = e;
            if (e == null) { per.append(" t").append(t).append("=absent"); continue; }
            Set<ByteBuffer> keys = field(e, "keys");
            Set<?> toks = field(e, "tokens");
            Set<Object> arrays = Collections.newSetFromMap(new IdentityHashMap<>());
            long tb = 0, tr = 0;
            for (ByteBuffer key : keys)
            {
                tb += key.remaining();
                if (key.hasArray()) { if (arrays.add(key.array())) tr += key.array().length; }
                else noArray++;
            }
            per.append(" t").append(t).append("=").append(keys.size()).append("/").append(toks.size()).append("/").append(tb).append("/").append(tr);
            k += keys.size(); tk += toks.size(); b += tb; r += tr;
        }
        out(label + " K=" + k + " tokens=" + tk + " B=" + b + " R=" + r + " noArray=" + noArray + " cacheEntries=" + m.size()
            + " perTable(keys/tokens/B/R):" + per);
        return es;
    }

    static String getters()
    {
        return "enabled=" + DatabaseDescriptor.getPartitionDenylistEnabled() + " total=" + DatabaseDescriptor.getDenylistMaxKeysTotal()
               + " perTable=" + DatabaseDescriptor.getDenylistMaxKeysPerTable() + " refresh=" + DatabaseDescriptor.getDenylistRefreshSeconds()
               + " cl=" + DatabaseDescriptor.getDenylistConsistencyLevel();
    }

    @Test
    public void probe() throws Exception
    {
        out("START shake=" + SHAKE + " rows=" + ROWS + " perTable=" + PER_TABLE + " T=" + Arrays.toString(TS) + " T2=" + T2);
        // B2c: insert the workload once
        byte[] filler = new byte[KEYLEN - 4];
        Arrays.fill(filler, (byte) 0xAB);
        for (int t = 1; t <= 4; t++)
            for (int i = 0; i < ROWS; i++)
            {
                ByteBuffer key = ByteBuffer.allocate(KEYLEN);
                key.putInt(i).put(filler).flip();
                QueryProcessor.process("INSERT INTO system_distributed.partition_denylist (ks_name, table_name, key) VALUES ('dlprobe','t" + t + "',0x"
                                       + ByteBufferUtil.bytesToHex(key) + ")", ConsistencyLevel.ONE);
            }
        for (int t = 1; t <= 4; t++)
            out("rows t" + t + "=" + QueryProcessor.executeInternal("SELECT key FROM system_distributed.partition_denylist WHERE ks_name='dlprobe' AND table_name='t" + t + "'").size());
        out("partitioner=" + DatabaseDescriptor.getPartitioner().getClass().getSimpleName() + " " + getters());
        snapshot("before-control");

        // B2e amendment (a): control, flag off, startup path
        out("MARK control");
        DatabaseDescriptor.setPartitionDenylistEnabled(false);
        StorageProxy.instance.initialLoadPartitionDenylist();
        out("control " + getters());
        snapshot("control");
        DatabaseDescriptor.setPartitionDenylistEnabled(true);

        // Phase 1
        for (int T : TS)
        {
            DatabaseDescriptor.setDenylistRefreshSeconds(3600);
            DatabaseDescriptor.setDenylistMaxKeysPerTable(PER_TABLE);
            DatabaseDescriptor.setDenylistMaxKeysTotal(T);
            out("MARK phase1 T=" + T);
            out("phase1 T=" + T + " set " + getters());
            StorageProxy.instance.loadPartitionDenylist();
            snapshot("phase1 T=" + T);
        }

        // Phase 2
        DatabaseDescriptor.setDenylistRefreshSeconds(1);
        DatabaseDescriptor.setDenylistMaxKeysPerTable(PER_TABLE);
        DatabaseDescriptor.setDenylistMaxKeysTotal(T2);
        out("MARK phase2-load T=" + T2);
        out("phase2 set " + getters());
        StorageProxy.instance.loadPartitionDenylist();
        Object[] a = snapshot("phase2-after-load T=" + T2);
        out("MARK phase2-poll");
        PartitionDenylist p = pd();
        ByteBuffer any = ByteBuffer.wrap(new byte[]{ 0 });
        long reads0 = reads();
        long start = System.currentTimeMillis();
        Thread.sleep(2000);
        for (int i = 1; i <= 30; i++)
        {
            for (int t = 1; t <= 4; t++) p.isKeyPermitted("dlprobe", "t" + t, any);
            Thread.sleep(500);
            out("poll " + i + " " + (System.currentTimeMillis() - start) + " K=" + totalK());
        }
        Object[] b = snapshot("phase2-end T=" + T2);
        int replaced = 0;
        for (int t = 1; t <= 4; t++) if (a[t] != b[t]) replaced++;
        out("phase2 replaced=" + replaced + " reloadReads=" + (reads() - reads0) + " loopMs=" + (System.currentTimeMillis() - start));
        out("END");
    }
}
