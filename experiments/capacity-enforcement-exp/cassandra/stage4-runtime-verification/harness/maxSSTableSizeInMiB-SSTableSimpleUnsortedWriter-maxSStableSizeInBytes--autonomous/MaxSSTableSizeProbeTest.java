package org.apache.cassandra.io.sstable;

import java.lang.management.ManagementFactory;
import java.lang.reflect.Field;
import java.nio.ByteBuffer;
import java.util.*;

import org.junit.BeforeClass;
import org.junit.Test;

import org.apache.cassandra.config.CassandraRelevantProperties;
import org.apache.cassandra.config.Config;
import org.apache.cassandra.config.DatabaseDescriptor;
import org.apache.cassandra.db.Keyspace;
import org.apache.cassandra.dht.Murmur3Partitioner;
import org.apache.cassandra.utils.ByteBufferUtil;

public class MaxSSTableSizeProbeTest
{
    static final String OUT  = System.getProperty("probe.out");                 // existing empty dir .../probe_ks/t
    static final int    MIB  = Integer.getInteger("probe.mib", -1);             // -1: builder method not called
    static final String MODE = System.getProperty("probe.mode", "unsorted");    // unsorted | sorted | delete
    static final int    ROWS = Integer.getInteger("probe.rows", 147456);
    static final int    VAL  = Integer.getInteger("probe.value", 1024);         // blob bytes per row
    static final int    RPP  = Integer.getInteger("probe.rpp", 16);             // rows per partition

    @BeforeClass
    public static void setUp()
    {
        DatabaseDescriptor.clientInitialization(true, () -> { Config c = new Config(); c.data_file_directories = new String[]{ OUT }; return c; });
        CassandraRelevantProperties.FORCE_LOAD_LOCAL_KEYSPACES.setBoolean(true);
        DatabaseDescriptor.setPartitionerUnsafe(Murmur3Partitioner.instance);
        Keyspace.setInitialized();
    }

    static long heapAfterGc()
    {
        for (int i = 0; i < 3; i++) System.gc();
        return ManagementFactory.getMemoryMXBean().getHeapMemoryUsage().getUsed();
    }

    @Test
    public void probe() throws Exception
    {
        String schema = "CREATE TABLE probe_ks.t (k bigint, c int, v blob, PRIMARY KEY (k, c)) WITH compression = {'enabled': 'false'}";
        boolean delete = MODE.equals("delete");
        String stmt = delete ? "DELETE FROM probe_ks.t WHERE k = ?" : "INSERT INTO probe_ks.t (k, c, v) VALUES (?, ?, ?)";
        CQLSSTableWriter.Builder b = CQLSSTableWriter.builder().inDirectory(OUT).forTable(schema).using(stmt);
        if (MIB != -1) b.withMaxSSTableSizeInMiB(MIB);
        if (MODE.equals("sorted")) b.sorted();
        CQLSSTableWriter w = b.build();

        Field wf = CQLSSTableWriter.class.getDeclaredField("writer"); wf.setAccessible(true);
        Object sw = wf.get(w);
        Field cs = null; long limit = -1;
        if (sw instanceof SSTableSimpleUnsortedWriter)
        {
            cs = SSTableSimpleUnsortedWriter.class.getDeclaredField("currentSize"); cs.setAccessible(true);
            Field mf = SSTableSimpleUnsortedWriter.class.getDeclaredField("maxSStableSizeInBytes"); mf.setAccessible(true);
            limit = mf.getLong(sw);
        }
        System.out.println("PROBE writer=" + sw.getClass().getSimpleName() + " limitBytes=" + limit);

        // partition keys; for the sorted writer they must be fed in Murmur3 token order
        int parts = delete ? ROWS : (ROWS + RPP - 1) / RPP;
        Long[] keys = new Long[parts];
        for (int p = 0; p < parts; p++) keys[p] = (long) p;
        if (MODE.equals("sorted"))
            Arrays.sort(keys, Comparator.comparing(k -> Murmur3Partitioner.instance.getToken(ByteBufferUtil.bytes(k))));

        long base = heapAfterGc();
        System.out.println("PROBE baselineHeap=" + base);
        Random rnd = new Random(42);
        long prev = 0, maxCs = 0, maxInc = 0; int syncs = 0, heapSamples = 0; boolean sampledThisBuffer = false;
        for (int i = 0; i < ROWS; i++)
        {
            if (delete) w.addRow(keys[i]);
            else
            {
                byte[] v = new byte[VAL]; rnd.nextBytes(v);                 // fresh buffer per row
                w.addRow(keys[i / RPP], i % RPP, ByteBuffer.wrap(v));
            }
            if (cs != null)
            {
                long now = cs.getLong(sw);
                if (now < prev || (!delete && now == 0))   // S4-A1: a row that syncs leaves currentSize = 0 (also when prev was 0, Ubig)
                {
                    syncs++; sampledThisBuffer = false;
                    System.out.println("PROBE sync=" + syncs + " preSyncSample=" + prev + " limit=" + limit + " row=" + i);
                }
                else maxInc = Math.max(maxInc, now - prev);
                maxCs = Math.max(maxCs, now); prev = now;
                if (!sampledThisBuffer && heapSamples < 3 && now > 0.95 * limit)
                {
                    sampledThisBuffer = true; heapSamples++;
                    System.out.println("PROBE heapSample=" + heapSamples + " currentSize=" + now + " retained=" + (heapAfterGc() - base));
                }
            }
            if (i == ROWS / 4 || i == ROWS / 2 || i == 3 * ROWS / 4)   // S4-A1: also for unsorted runs (Uinf heap observable)
                System.out.println("PROBE " + (cs == null ? "sortedHeap" : "quarterHeap") + " row=" + i + " currentSize=" + (cs == null ? -1 : cs.getLong(sw)) + " retained=" + (heapAfterGc() - base));
        }
        System.out.println("PROBE syncs=" + syncs + " maxCurrentSize=" + maxCs + " maxIncrement=" + maxInc + " endCurrentSize=" + prev);
        w.close();
        java.io.File[] data = new java.io.File(OUT).listFiles((d, n) -> n.endsWith("-Data.db"));
        Arrays.sort(data, Comparator.comparing(java.io.File::getName));
        long tot = 0;
        for (java.io.File f : data) { tot += f.length(); System.out.println("PROBE data " + f.getName() + " " + f.length()); }
        System.out.println("PROBE dataFiles=" + data.length + " totalDataBytes=" + tot);
    }
}
