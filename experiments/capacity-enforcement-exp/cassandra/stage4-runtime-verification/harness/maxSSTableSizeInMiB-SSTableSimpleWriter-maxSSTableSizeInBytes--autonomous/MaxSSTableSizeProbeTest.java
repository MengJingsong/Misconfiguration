package org.apache.cassandra.io.sstable;

import java.io.FileWriter;
import java.io.PrintWriter;
import java.lang.reflect.Field;
import java.nio.ByteBuffer;
import java.util.*;
import org.junit.BeforeClass;
import org.junit.Test;
import org.apache.cassandra.config.*;
import org.apache.cassandra.db.Keyspace;
import org.apache.cassandra.dht.ByteOrderedPartitioner;
import org.apache.cassandra.io.util.File;

public class MaxSSTableSizeProbeTest
{
    static final int UNSET = Integer.MIN_VALUE;
    static final String BASE = System.getenv().getOrDefault("PROBE_DIR", System.getProperty("java.io.tmpdir") + "/probe-unit");
    static final String OUT  = System.getenv().getOrDefault("PROBE_OUT", BASE + ".csv");
    static int seq = 0;

    @BeforeClass
    public static void setup()
    {
        new File(BASE).tryCreateDirectories();
        DatabaseDescriptor.clientInitialization(true, () -> { Config c = new Config(); c.data_file_directories = new String[]{ BASE }; return c; });
        CassandraRelevantProperties.FORCE_LOAD_LOCAL_KEYSPACES.setBoolean(true);
        DatabaseDescriptor.setPartitionerUnsafe(ByteOrderedPartitioner.instance);
        Keyspace.setInitialized();
    }

    @Test
    public void probe() throws Exception
    {
        for (boolean comp : new boolean[]{ false, true })
            for (int m : new int[]{ 1, 4, 16, 0, UNSET })
                run("sorted", m, true, comp, 60_000, 1);
        run("bigpart", 1, true, false, 3_000, 5_000);
        run("unsorted", 4, false, false, 60_000, 1);
    }

    void run(String label, int m, boolean sorted, boolean comp, int partitions, int rowsInFirst) throws Exception
    {
        String ks = "probe_ks" + (++seq);
        File dir = new File(BASE + "/" + ks + "/t");
        dir.tryCreateDirectories();
        String schema = "CREATE TABLE " + ks + ".t (k int, c int, v blob, PRIMARY KEY (k, c))"
                        + (comp ? "" : " WITH compression = {'enabled': 'false'}");
        CQLSSTableWriter.Builder b = CQLSSTableWriter.builder().inDirectory(dir).forTable(schema)
                .using("INSERT INTO " + ks + ".t (k, c, v) VALUES (?, ?, ?)")
                .withPartitioner(ByteOrderedPartitioner.instance);
        if (sorted) b.sorted();
        if (m != UNSET) b.withMaxSSTableSizeInMiB(m);
        CQLSSTableWriter w = b.build();

        Field fSimple = CQLSSTableWriter.class.getDeclaredField("writer"); fSimple.setAccessible(true);
        Object simple = fSimple.get(w);
        long limit = -2; Field fTxn = null;
        if (simple instanceof SSTableSimpleWriter)
        {
            Field fl = SSTableSimpleWriter.class.getDeclaredField("maxSSTableSizeInBytes"); fl.setAccessible(true);
            limit = fl.getLong(simple);
            fTxn = SSTableSimpleWriter.class.getDeclaredField("writer"); fTxn.setAccessible(true);
        }
        List<Long> operandAtSwitch = new ArrayList<>();
        Object cur = null; long curVal = -1;
        Random rnd = new Random(42);
        for (int k = 0; k < partitions; k++)
            for (int c = 0; c < (k == 0 ? rowsInFirst : 1); c++)
            {
                byte[] v = new byte[1000]; rnd.nextBytes(v);
                w.addRow(k, c, ByteBuffer.wrap(v));
                if (fTxn != null)
                {
                    SSTableTxnWriter t = (SSTableTxnWriter) fTxn.get(simple);
                    if (t != null)
                    {
                        if (t != cur) { if (cur != null) operandAtSwitch.add(curVal); cur = t; }
                        curVal = t.getOnDiskBytesWritten();
                    }
                }
            }
        w.close();

        // group component files by generation id (file name "<ver>-<gen>-<fmt>-<Component>.db")
        TreeMap<Long, long[]> byGen = new TreeMap<>();
        for (File f : dir.tryList())
        {
            String[] p = f.name().split("-");
            if (p.length < 4) continue;
            long gen; try { gen = Long.parseLong(p[1]); } catch (NumberFormatException e) { continue; }
            long[] s = byGen.computeIfAbsent(gen, g -> new long[2]);
            if (f.name().endsWith("-Data.db")) s[0] = f.length();
            s[1] += f.length();
        }
        try (PrintWriter out = new PrintWriter(new FileWriter(OUT, true)))
        {
            int i = 0;
            for (long[] s : byGen.values())
            {
                String op = i < operandAtSwitch.size() ? String.valueOf(operandAtSwitch.get(i)) : "";
                out.println(String.join(",", label, String.valueOf(m), String.valueOf(comp), String.valueOf(limit),
                                        String.valueOf(i), String.valueOf(s[0]), String.valueOf(s[1]), op));
                i++;
            }
        }
        dir.deleteRecursive();
    }
}
