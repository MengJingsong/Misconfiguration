/*
 * Stage-4 harness, unit tier (B2, as amended 2026-10-25) of
 * coordinator_read_size_fail_threshold-validateReadThresholds-fail--autonomous. Not part of upstream Cassandra.
 * Copy into test/unit/org/apache/cassandra/cql3/ of a local clone at cassandra-5.0.9.
 * System properties: stage4.out (file that also receives the STAGE4 lines); stage4.mode=shakedown (instrument check, not a reading).
 * Lines:
 *   STAGE4 info ...
 *   STAGE4 mirror b0=<> h=<distinct h values> rows=<n>
 *   STAGE4 row name=<> arm=<N|C|L|OFF> T=<bytes|-> P=<> rb_enabled=<> rb_coord=<> rb_local=<> rows=<> err=<class|-> codes=<> 
 *        coordMax=<> coordAborts=<> localMax=<> localAborts=<> s3=<ok|LocalReadSizeTooLargeException> len=<> cap=<> alloc=<> X=<>
 *   STAGE4 v1101 <case> <outcome> <message>
 */
package org.apache.cassandra.cql3;

import java.io.FileWriter;
import java.io.PrintWriter;
import java.lang.management.ManagementFactory;
import java.lang.reflect.Field;
import java.lang.reflect.Method;
import java.nio.ByteBuffer;
import java.util.ArrayList;
import java.util.Iterator;
import java.util.List;
import java.util.Random;
import java.util.TreeSet;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

import org.junit.BeforeClass;
import org.junit.Test;

import org.apache.cassandra.Util;
import org.apache.cassandra.config.Config;
import org.apache.cassandra.config.DataStorageSpec;
import org.apache.cassandra.config.DatabaseDescriptor;
import org.apache.cassandra.db.ColumnFamilyStore;
import org.apache.cassandra.db.Keyspace;
import org.apache.cassandra.db.MessageParams;
import org.apache.cassandra.db.ReadCommand;
import org.apache.cassandra.db.ReadExecutionController;
import org.apache.cassandra.db.ReadResponse;
import org.apache.cassandra.db.filter.LocalReadSizeTooLargeException;
import org.apache.cassandra.db.partitions.UnfilteredPartitionIterator;
import org.apache.cassandra.db.rows.Row;
import org.apache.cassandra.db.rows.Unfiltered;
import org.apache.cassandra.db.rows.UnfilteredRowIterator;
import org.apache.cassandra.utils.ObjectSizes;

public class ReadSizeCapUnitTest extends CQLTester
{
    static final int ROWS = 128, VAL = 65536;
    static PrintWriter out;
    static final com.sun.management.ThreadMXBean TMX = (com.sun.management.ThreadMXBean) ManagementFactory.getThreadMXBean();

    static void line(String s)
    {
        System.out.println(s);
        if (out != null) { out.println(s); out.flush(); }
    }

    @BeforeClass
    public static void setupStage4() throws Exception
    {
        String f = System.getProperty("stage4.out");
        if (f != null) out = new PrintWriter(new FileWriter(f, true));
        requireNetwork();
        line("STAGE4 info jvm " + System.getProperty("java.version") + " maxHeap=" + Runtime.getRuntime().maxMemory()
             + " allocSupported=" + TMX.isThreadAllocatedMemorySupported() + " allocEnabled=" + TMX.isThreadAllocatedMemoryEnabled()
             + " daemonInitialized=" + DatabaseDescriptor.isDaemonInitialized());
    }

    static DataStorageSpec.LongBytesBound b(Long v)
    {
        return v == null ? null : new DataStorageSpec.LongBytesBound(v, DataStorageSpec.DataStorageUnit.BYTES);
    }

    static void setAll(boolean enabled, Long coordFail, Long localFail)
    {
        DatabaseDescriptor.setReadThresholdsEnabled(enabled);
        DatabaseDescriptor.setCoordinatorReadSizeWarnThreshold(null);
        DatabaseDescriptor.setCoordinatorReadSizeFailThreshold(b(coordFail));
        DatabaseDescriptor.setLocalReadSizeWarnThreshold(null);
        DatabaseDescriptor.setLocalReadSizeFailThreshold(b(localFail));
        DatabaseDescriptor.setRowIndexReadSizeWarnThreshold(null);
        DatabaseDescriptor.setRowIndexReadSizeFailThreshold(null);
    }

    static String rb(DataStorageSpec.LongBytesBound v) { return v == null ? "null" : String.valueOf(v.toBytes()); }

    static long allocated() { return TMX.getThreadAllocatedBytes(Thread.currentThread().getId()); }

    static class Combo
    {
        final String arm; final Long T; final int P; String table;
        Combo(String arm, Long T, int P) { this.arm = arm; this.T = T; this.P = P; }
        String name() { return arm + (T == null ? "" : "_" + T) + "_P" + P; }
    }

    String makeTable(Random rnd) throws Throwable
    {
        String t = createTable("CREATE TABLE %s (pk int, ck int, v blob, PRIMARY KEY (pk, ck))");
        for (int ck = 0; ck < ROWS; ck++)
        {
            byte[] v = new byte[VAL];
            rnd.nextBytes(v);
            execute("INSERT INTO " + KEYSPACE + "." + t + " (pk, ck, v) VALUES (?, ?, ?)", 0, ck, ByteBuffer.wrap(v));
        }
        ColumnFamilyStore cfs = Keyspace.open(KEYSPACE).getColumnFamilyStore(t);
        cfs.disableAutoCompaction();
        Util.flush(cfs);
        return t;
    }

    static Field DATA;
    static
    {
        try
        {
            Class<?> dr = Class.forName("org.apache.cassandra.db.ReadResponse$DataResponse");
            DATA = dr.getDeclaredField("data");
            DATA.setAccessible(true);
        }
        catch (Exception e) { throw new RuntimeException(e); }
    }

    static long parseX(String msg)
    {
        Matcher m = Pattern.compile("attempted to read (\\d+) bytes").matcher(msg == null ? "" : msg);
        return m.find() ? Long.parseLong(m.group(1)) : -1;
    }

    /** B2d (3): build page 1 (limit P) as the replica does; returns "s3=.. len=.. cap=.. alloc=.. X=.." */
    static String respond(ColumnFamilyStore cfs, int P)
    {
        MessageParams.reset();
        ReadCommand cmd = Util.cmd(cfs, 0).withLimit(P).build();
        cmd.trackWarnings();
        long a0 = allocated();
        String s3 = "ok"; long len = -1, cap = -1, x = -1;
        ReadResponse r = null;
        try (ReadExecutionController ec = cmd.executionController(); UnfilteredPartitionIterator it = cmd.executeLocally(ec))
        {
            r = cmd.createResponse(it, ec.getRepairedDataInfo());
        }
        catch (LocalReadSizeTooLargeException e)
        {
            s3 = "LocalReadSizeTooLargeException"; x = parseX(e.getMessage());
        }
        long alloc = allocated() - a0;
        if (r != null)
        {
            try { len = ((ByteBuffer) DATA.get(r)).remaining(); } catch (Exception e) { throw new RuntimeException(e); }
            cap = ObjectSizes.measureDeep(r);
        }
        MessageParams.reset();
        return "s3=" + s3 + " len=" + len + " cap=" + cap + " alloc=" + alloc + " X=" + x;
    }

    void runCombo(Combo c) throws Throwable
    {
        ColumnFamilyStore cfs = Keyspace.open(KEYSPACE).getColumnFamilyStore(c.table);
        boolean enabled = !c.arm.equals("OFF");
        Long coord = c.arm.equals("C") || c.arm.equals("OFF") ? c.T : null;
        Long local = c.arm.equals("L") || c.arm.equals("OFF") ? c.T : null;
        setAll(enabled, coord, local);
        String readBack = "rb_enabled=" + DatabaseDescriptor.getReadThresholdsEnabled()
                          + " rb_coord=" + rb(DatabaseDescriptor.getCoordinatorReadSizeFailThreshold())
                          + " rb_local=" + rb(DatabaseDescriptor.getLocalReadSizeFailThreshold())
                          + " rb_coordWarn=" + rb(DatabaseDescriptor.getCoordinatorReadSizeWarnThreshold())
                          + " rb_localWarn=" + rb(DatabaseDescriptor.getLocalReadSizeWarnThreshold());
        long ca0 = cfs.metric.coordinatorReadSizeAborts.table.getCount();
        long la0 = cfs.metric.localReadSizeAborts.table.getCount();
        int rows = 0; String err = "-"; String codes = "-";
        try
        {
            com.datastax.driver.core.ResultSet rs = executeNetWithPaging("SELECT * FROM " + KEYSPACE + "." + c.table + " WHERE pk = 0", c.P);
            Iterator<com.datastax.driver.core.Row> it = rs.iterator();
            while (it.hasNext()) { it.next(); rows++; }
        }
        catch (com.datastax.driver.core.exceptions.ReadFailureException e)
        {
            err = "ReadFailureException"; codes = String.valueOf(e.getFailuresMap()).replace(' ', '_');
        }
        catch (Throwable t)
        {
            err = t.getClass().getName(); codes = String.valueOf(t.getMessage()).replace(' ', '_');
            if (codes.length() > 300) codes = codes.substring(0, 300);
        }
        long coordMax = cfs.metric.coordinatorReadSize.cf.getSnapshot().getMax();
        long localMax = cfs.metric.localReadSize.cf.getSnapshot().getMax();
        long ca = cfs.metric.coordinatorReadSizeAborts.table.getCount() - ca0;
        long la = cfs.metric.localReadSizeAborts.table.getCount() - la0;
        String s3 = respond(cfs, c.P);
        line("STAGE4 row name=" + c.name() + " arm=" + c.arm + " T=" + (c.T == null ? "-" : c.T) + " P=" + c.P + " " + readBack
             + " rows=" + rows + " err=" + err + " codes=" + codes + " coordMax=" + coordMax + " coordAborts=" + ca
             + " localMax=" + localMax + " localAborts=" + la + " " + s3);
        setAll(true, null, null);
    }

    void mirror(String table)
    {
        setAll(true, null, null);
        ColumnFamilyStore cfs = Keyspace.open(KEYSPACE).getColumnFamilyStore(table);
        ReadCommand cmd = Util.cmd(cfs, 0).withLimit(ROWS).build();
        long key = 0, del = 0; int n = 0;
        TreeSet<Long> hs = new TreeSet<>();
        try (ReadExecutionController ec = cmd.executionController(); UnfilteredPartitionIterator it = cmd.executeLocally(ec))
        {
            try (UnfilteredRowIterator p = it.next())
            {
                key = ObjectSizes.sizeOnHeapOf(p.partitionKey().getKey());
                del = p.partitionLevelDeletion().unsharedHeapSize();
                while (p.hasNext()) { Unfiltered u = p.next(); if (u.isRow()) { hs.add(((Row) u).unsharedHeapSize()); n++; } }
            }
        }
        line("STAGE4 mirror b0=" + (key + del) + " key=" + key + " del=" + del + " h=" + hs.toString().replace(" ", "") + " rows=" + n);
    }

    static void v1101(String name, Config conf)
    {
        try
        {
            Method m = DatabaseDescriptor.class.getDeclaredMethod("applyReadThresholdsValidations", Config.class);
            m.setAccessible(true);
            m.invoke(null, conf);
            line("STAGE4 v1101 " + name + " accepted -");
        }
        catch (java.lang.reflect.InvocationTargetException e)
        {
            Throwable t = e.getCause();
            line("STAGE4 v1101 " + name + " threw " + t.getClass().getSimpleName() + ": " + t.getMessage());
        }
        catch (Exception e)
        {
            line("STAGE4 v1101 " + name + " harness-error " + e);
        }
    }

    static Config pair(String which, String fail, String warn)
    {
        Config c = new Config();
        DataStorageSpec.LongBytesBound f = new DataStorageSpec.LongBytesBound(fail), w = new DataStorageSpec.LongBytesBound(warn);
        switch (which)
        {
            case "coordinator_read_size": c.coordinator_read_size_fail_threshold = f; c.coordinator_read_size_warn_threshold = w; break;
            case "local_read_size": c.local_read_size_fail_threshold = f; c.local_read_size_warn_threshold = w; break;
            default: c.row_index_read_size_fail_threshold = f; c.row_index_read_size_warn_threshold = w;
        }
        return c;
    }

    static void setterBypass(String which)
    {
        DataStorageSpec.LongBytesBound one = new DataStorageSpec.LongBytesBound("1KiB"), two = new DataStorageSpec.LongBytesBound("2KiB");
        String outcome; String rbf, rbw;
        try
        {
            switch (which)
            {
                case "coordinator_read_size":
                    DatabaseDescriptor.setCoordinatorReadSizeWarnThreshold(two); DatabaseDescriptor.setCoordinatorReadSizeFailThreshold(one);
                    rbf = String.valueOf(DatabaseDescriptor.getCoordinatorReadSizeFailThreshold()); rbw = String.valueOf(DatabaseDescriptor.getCoordinatorReadSizeWarnThreshold()); break;
                case "local_read_size":
                    DatabaseDescriptor.setLocalReadSizeWarnThreshold(two); DatabaseDescriptor.setLocalReadSizeFailThreshold(one);
                    rbf = String.valueOf(DatabaseDescriptor.getLocalReadSizeFailThreshold()); rbw = String.valueOf(DatabaseDescriptor.getLocalReadSizeWarnThreshold()); break;
                default:
                    DatabaseDescriptor.setRowIndexReadSizeWarnThreshold(two); DatabaseDescriptor.setRowIndexReadSizeFailThreshold(one);
                    rbf = String.valueOf(DatabaseDescriptor.getRowIndexReadSizeFailThreshold()); rbw = String.valueOf(DatabaseDescriptor.getRowIndexReadSizeWarnThreshold());
            }
            outcome = "accepted fail=" + rbf + " warn=" + rbw;
        }
        catch (Throwable t) { outcome = "threw " + t.getClass().getSimpleName() + ": " + t.getMessage(); }
        line("STAGE4 v1101 setter-" + which + " " + outcome);
        setAll(true, null, null);
    }

    @Test
    public void stage4() throws Throwable
    {
        boolean shakedown = "shakedown".equals(System.getProperty("stage4.mode"));
        List<Combo> combos = new ArrayList<>();
        if (shakedown)
        {
            combos.add(new Combo("C", 524288L, 32));
            combos.add(new Combo("L", 524288L, 32));
        }
        else
        {
            combos.add(new Combo("N", null, 16));
            combos.add(new Combo("N", null, 64));
            for (String arm : new String[]{ "C", "L" })
                for (long T : new long[]{ 262144L, 1048576L, 4194304L })
                    for (int P : new int[]{ 16, 64 })
                        combos.add(new Combo(arm, T, P));
            combos.add(new Combo("OFF", 262144L, 16));
        }
        line("STAGE4 info mode=" + (shakedown ? "shakedown" : "run") + " combos=" + combos.size());
        setAll(true, null, null);
        Random rnd = new Random(20261025L);
        for (Combo c : combos)
            c.table = makeTable(rnd);
        boolean agreed = sessionNet().getCluster().getMetadata().checkSchemaAgreement();
        Thread.sleep(2000);
        line("STAGE4 info tables created and flushed: " + combos.size() + " schemaAgreement=" + agreed);
        mirror(combos.get(0).table);
        for (Combo c : combos)
            runCombo(c);
        if (!shakedown)
        {
            for (String w : new String[]{ "coordinator_read_size", "local_read_size", "row_index_read_size" })
            {
                v1101(w + "-fail1KiB-warn2KiB", pair(w, "1KiB", "2KiB"));
                v1101(w + "-fail2KiB-warn1KiB", pair(w, "2KiB", "1KiB"));
                v1101(w + "-fail1KiB-warn1KiB", pair(w, "1KiB", "1KiB"));
                setterBypass(w);
            }
        }
        setAll(true, null, null);
        line("STAGE4 info done");
    }
}
