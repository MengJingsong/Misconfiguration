/*
 * Stage-4 harness, unit tier of row_index_read_size_fail_threshold-checkSize-failThreshold (case file section 9).
 * Not part of upstream Cassandra. Copy into test/unit/org/apache/cassandra/db/ of a local clone at cassandra-5.0.9.
 * System property stage4.out: a file that also receives the STAGE4 lines.
 */
package org.apache.cassandra.db;

import java.io.FileWriter;
import java.io.PrintWriter;
import java.lang.management.ManagementFactory;
import java.nio.ByteBuffer;
import java.util.ArrayList;
import java.util.List;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

import org.junit.Assert;
import org.junit.BeforeClass;
import org.junit.Test;

import org.apache.cassandra.SchemaLoader;
import org.apache.cassandra.Util;
import org.apache.cassandra.config.DataStorageSpec;
import org.apache.cassandra.config.DatabaseDescriptor;
import org.apache.cassandra.db.marshal.BytesType;
import org.apache.cassandra.db.marshal.Int32Type;
import org.apache.cassandra.db.partitions.UnfilteredPartitionIterator;
import org.apache.cassandra.db.rows.Unfiltered;
import org.apache.cassandra.db.rows.UnfilteredRowIterator;
import org.apache.cassandra.io.sstable.IndexInfo;
import org.apache.cassandra.io.sstable.format.SSTableReader;
import org.apache.cassandra.io.sstable.format.big.BigFormat;
import org.apache.cassandra.io.sstable.format.big.BigTableReader;
import org.apache.cassandra.io.sstable.format.big.RowIndexEntry;
import org.apache.cassandra.io.sstable.keycache.KeyCacheSupport;
import org.apache.cassandra.net.ParamType;
import org.apache.cassandra.schema.CachingParams;
import org.apache.cassandra.schema.KeyspaceParams;
import org.apache.cassandra.schema.TableMetadata;
import org.apache.cassandra.service.CacheService;

public class RowIndexSizeGuardTest
{
    static final String KS = "ks1";
    static final int PAYLOAD = 1200;
    static final int[] LADDER = { 20, 40, 80, 160, 320, 640, 1280 };
    static PrintWriter out;
    static int mismatches = 0;
    static ColumnFamilyStore cfs, cfs2;
    static final Pattern MSG = Pattern.compile("estimated to be (\\d+) bytes in-memory \\(total entries: (\\d+), total bytes: (\\d+)\\)");

    static void line(String s)
    {
        System.out.println(s);
        if (out != null) { out.println(s); out.flush(); }
    }

    static void check(String name, Object expected, Object actual)
    {
        boolean ok = String.valueOf(expected).equals(String.valueOf(actual));
        if (!ok) mismatches++;
        line("STAGE4 check " + name + " " + expected + " " + actual + " " + (ok ? "ok" : "MISMATCH"));
    }

    static void checkTrue(String name, boolean cond, String detail)
    {
        if (!cond) mismatches++;
        line("STAGE4 check " + name + " true " + cond + " " + (cond ? "ok" : "MISMATCH") + " [" + detail + "]");
    }

    @BeforeClass
    public static void setup() throws Exception
    {
        String f = System.getProperty("stage4.out");
        if (f != null) out = new PrintWriter(new FileWriter(f, true));
        DatabaseDescriptor.daemonInitialization();
        DatabaseDescriptor.setColumnIndexSizeInKiB(1);     // before the flush: one block per 1,200-byte row
        DatabaseDescriptor.setColumnIndexCacheSize(4096);  // KiB: entries are built on heap
        SchemaLoader.prepareServer();
        SchemaLoader.createKeyspace(KS, KeyspaceParams.simple(1),
                TableMetadata.builder(KS, "t").addPartitionKeyColumn("pk", Int32Type.instance).addClusteringColumn("ck", Int32Type.instance).addRegularColumn("v", BytesType.instance),
                TableMetadata.builder(KS, "t2").addPartitionKeyColumn("pk", Int32Type.instance).addClusteringColumn("ck", Int32Type.instance).addRegularColumn("v", BytesType.instance).caching(CachingParams.CACHE_NOTHING));
        cfs = Keyspace.open(KS).getColumnFamilyStore("t");
        cfs2 = Keyspace.open(KS).getColumnFamilyStore("t2");
        cfs.disableAutoCompaction();
        cfs2.disableAutoCompaction();
        Assert.assertTrue("BIG format must be selected", BigFormat.isSelected());
        byte[] payload = new byte[PAYLOAD];
        for (int k = 0; k < LADDER.length; k++)
            for (int i = 0; i < LADDER[k]; i++)
                new RowUpdateBuilder(cfs.metadata(), 0, k + 1).clustering(i).add("v", ByteBuffer.wrap(payload)).build().applyUnsafe();
        new RowUpdateBuilder(cfs.metadata(), 0, 8).clustering(0).add("v", ByteBuffer.wrap(payload)).build().applyUnsafe();
        Util.flush(cfs);
        line("STAGE4 info sstables " + cfs.getLiveSSTables().size());
        line("STAGE4 info jvm " + System.getProperty("java.version"));
        try { line("STAGE4 info UseCompressedOops " + ManagementFactory.getPlatformMXBean(com.sun.management.HotSpotDiagnosticMXBean.class).getVMOption("UseCompressedOops").getValue()); }
        catch (Throwable t) { line("STAGE4 info UseCompressedOops unknown " + t); }
    }

    static void limits(Long fail, boolean enabled)
    {
        DatabaseDescriptor.setReadThresholdsEnabled(enabled);
        DatabaseDescriptor.setLocalReadSizeWarnThreshold(null);
        DatabaseDescriptor.setLocalReadSizeFailThreshold(null);
        DatabaseDescriptor.setRowIndexReadSizeWarnThreshold(null);
        DatabaseDescriptor.setRowIndexReadSizeFailThreshold(fail == null ? null : new DataStorageSpec.LongBytesBound(fail, DataStorageSpec.DataStorageUnit.BYTES));
    }

    static class Res { int rows; Throwable err; long est = -1, entries = -1, bytes = -1; Long failParam; }

    static Res read(ColumnFamilyStore c, ReadCommand cmd)
    {
        MessageParams.reset();
        Res r = new Res();
        try (ReadExecutionController ec = cmd.executionController(); UnfilteredPartitionIterator it = cmd.executeLocally(ec))
        {
            while (it.hasNext())
                try (UnfilteredRowIterator p = it.next())
                {
                    while (p.hasNext()) { Unfiltered u = p.next(); if (u.isRow()) r.rows++; }
                }
        }
        catch (RowIndexEntry.RowIndexEntryReadSizeTooLargeException e)
        {
            r.err = e;
            Matcher m = MSG.matcher(e.getMessage());
            if (m.find()) { r.est = Long.parseLong(m.group(1)); r.entries = Long.parseLong(m.group(2)); r.bytes = Long.parseLong(m.group(3)); }
        }
        r.failParam = MessageParams.get(ParamType.ROW_INDEX_READ_SIZE_FAIL);
        return r;
    }

    static ReadCommand point(int pk) { return Util.cmd(cfs, pk).withLimit(1).build(); }
    static int cacheEntries() { return CacheService.instance.keyCache.size(); }
    static long cacheWeight() { return CacheService.instance.keyCache.weightedSize(); }
    static long count(ColumnFamilyStore c) { return c.metric.rowIndexSize.cf.getCount(); }

    static Res freshRead(int pk)
    {
        CacheService.instance.invalidateKeyCache();
        return read(cfs, point(pk));
    }

    static SSTableReader sst(ColumnFamilyStore c) { return c.getLiveSSTables().iterator().next(); }

    static Object cachedEntry(ColumnFamilyStore c, int pk)
    {
        DecoratedKey dk = c.decorateKey(Int32Type.instance.decompose(pk));
        for (SSTableReader r : c.getLiveSSTables())
        {
            Object o = ((KeyCacheSupport<?>) r).getCachedPosition(dk, false);
            if (o != null) return o;
        }
        return null;
    }

    static long weightOf(Object e) { return ((RowIndexEntry) e).unsharedHeapSize(); }

    @Test
    public void guard() throws Exception
    {
        long o = IndexInfo.EMPTY_SIZE + org.apache.cassandra.db.ArrayClustering.EMPTY_SIZE + DeletionTime.EMPTY_SIZE;
        line("STAGE4 info o " + o + " (IndexInfo " + IndexInfo.EMPTY_SIZE + ", ArrayClustering " + org.apache.cassandra.db.ArrayClustering.EMPTY_SIZE + ", DeletionTime " + DeletionTime.EMPTY_SIZE + ")");
        // setup checks: blocks per partition (no command on the thread: no check)
        limits(null, true);
        for (int k = 0; k < LADDER.length; k++)
        {
            DecoratedKey dk = cfs.decorateKey(Int32Type.instance.decompose(k + 1));
            RowIndexEntry e = ((BigTableReader) sst(cfs)).getRowIndexEntry(dk, SSTableReader.Operator.EQ);
            check("blocks_pk" + (k + 1), LADDER[k], e.blockCount());
        }
        CacheService.instance.invalidateKeyCache();

        // known answer at F = 1
        limits(1L, true);
        long[] est = new long[LADDER.length], bytes = new long[LADDER.length];
        for (int k = 0; k < LADDER.length; k++)
        {
            Res r = freshRead(k + 1);
            check("known_refused_pk" + (k + 1), true, r.err != null);
            check("known_entries_pk" + (k + 1), LADDER[k], r.entries);
            check("known_formula_pk" + (k + 1), o * r.entries + r.bytes, r.est);
            check("known_param_pk" + (k + 1), r.est, r.failParam);
            est[k] = r.est; bytes[k] = r.bytes;
            line("STAGE4 info est pk" + (k + 1) + " B=" + LADDER[k] + " bytes=" + r.bytes + " est=" + r.est);
        }
        long c0 = count(cfs);
        Res single = freshRead(8);
        check("single_row_not_refused", null, single.err);
        check("single_row_count_unchanged", c0, count(cfs));

        // boundary pair, pk 4 (B = 160)
        limits(est[3] - 1, true);
        Res b1 = freshRead(4);
        check("boundary_minus1_refused", true, b1.err != null);
        check("boundary_minus1_cache_entries", 0, cacheEntries());
        check("boundary_minus1_no_cached_position", null, cachedEntry(cfs, 4));
        limits(est[3], true);
        Res b2 = freshRead(4);
        check("boundary_eq_accepted", null, b2.err);
        check("boundary_eq_cache_entries", 1, cacheEntries());
        Object ce = cachedEntry(cfs, 4);
        line("STAGE4 info boundary cached " + (ce == null ? null : ce.getClass().getSimpleName()) + " w=" + (ce == null ? -1 : weightOf(ce)) + " cacheWeight=" + cacheWeight());

        // ladder
        long[] fs = { 8192L, 32768L, 131072L, 8388608L, -1L };
        long[] wLast = new long[LADDER.length];
        for (long F : fs)
        {
            limits(F < 0 ? null : F, true);
            long cBefore = count(cfs);
            boolean prefix = true, seenRefused = false;
            for (int k = 0; k < LADDER.length; k++)
            {
                CacheService.instance.invalidateKeyCache();
                long cw = cacheWeight();
                Res r = read(cfs, point(k + 1));
                boolean accepted = r.err == null;
                boolean expectAccepted = F < 0 || est[k] <= F;
                check("ladder_F" + F + "_pk" + (k + 1) + "_accepted", expectAccepted, accepted);
                if (accepted && seenRefused) prefix = false;
                if (!accepted) seenRefused = true;
                if (accepted)
                {
                    Object e = cachedEntry(cfs, k + 1);
                    long w = e == null ? -1 : weightOf(e);
                    check("ladder_F" + F + "_pk" + (k + 1) + "_cached", true, e != null);
                    line("STAGE4 info ladder F=" + F + " pk" + (k + 1) + " w=" + w + " est=" + est[k] + " cacheDelta=" + (cacheWeight() - cw));
                    if (F == 8388608L) wLast[k] = w;
                }
                else
                {
                    check("ladder_F" + F + "_pk" + (k + 1) + "_cache_unchanged", 0, cacheEntries());
                }
            }
            check("ladder_F" + F + "_prefix", true, prefix);
            if (F < 0) check("ladder_unset_count_unchanged", cBefore, count(cfs));
        }
        // real weight is linear in B: slope w/est between rungs within 20 %
        List<Double> slopes = new ArrayList<>();
        for (int k = 1; k < LADDER.length; k++)
            slopes.add((wLast[k] - wLast[k - 1]) / (double) (est[k] - est[k - 1]));
        double smin = slopes.stream().mapToDouble(Double::doubleValue).min().getAsDouble(), smax = slopes.stream().mapToDouble(Double::doubleValue).max().getAsDouble();
        line("STAGE4 info slopes " + slopes + " w/est " + (wLast[LADDER.length - 1] / (double) est[LADDER.length - 1]));
        checkTrue("weight_linear_in_estimate", (smax - smin) / smax < 0.20, "min " + smin + " max " + smax);

        // scenario S: stock cache size 2 KiB, F = 32768
        DatabaseDescriptor.setColumnIndexCacheSize(2);
        limits(32768L, true);
        long shallowW = -1; boolean shallowSame = true;
        for (int k = 0; k < LADDER.length; k++)
        {
            Res r = freshRead(k + 1);
            check("S_pk" + (k + 1) + "_accepted", est[k] <= 32768L, r.err == null);
            if (r.err == null && bytes[k] > 2048)
            {
                Object e = cachedEntry(cfs, k + 1);
                long w = e == null ? -1 : weightOf(e);
                line("STAGE4 info S pk" + (k + 1) + " class=" + (e == null ? null : e.getClass().getSimpleName()) + " w=" + w);
                if (shallowW < 0) shallowW = w; else if (shallowW != w) shallowSame = false;
                check("S_pk" + (k + 1) + "_is_shallow", true, e != null && e.getClass().getSimpleName().contains("Shallow"));
            }
            else if (r.err != null)
                line("STAGE4 info S refused pk" + (k + 1) + " bytes=" + bytes[k] + " (above 2048: " + (bytes[k] > 2048) + ")");
        }
        check("S_shallow_weight_constant", true, shallowSame);
        DatabaseDescriptor.setColumnIndexCacheSize(4096);

        // C0: no command on the thread
        limits(1L, true);
        DecoratedKey dk7 = cfs.decorateKey(Int32Type.instance.decompose(7));
        RowIndexEntry direct = null; Throwable dt = null;
        try { direct = ((BigTableReader) sst(cfs)).getRowIndexEntry(dk7, SSTableReader.Operator.EQ); } catch (Throwable t) { dt = t; }
        check("C0_no_exception", null, dt);
        check("C0_entry_returned", true, direct != null);

        // C1: key-cache hit
        limits(131072L, true);
        Res first = freshRead(5);
        check("C1_first_accepted", null, first.err);
        limits(est[4] - 1, true);
        long cb = count(cfs);
        Res second = read(cfs, point(5));
        check("C1_hit_completes", null, second.err);
        check("C1_entries_unchanged", 1, cacheEntries());
        check("C1_count_unchanged", cb, count(cfs));
        Res third = freshRead(5);
        check("C1_after_invalidate_refused", true, third.err != null);

        // C2: SSTable opened late (table without key cache)
        byte[] payload = new byte[PAYLOAD];
        for (int i = 0; i < 10; i++)
            new RowUpdateBuilder(cfs2.metadata(), 0, 1).clustering(i).add("v", ByteBuffer.wrap(payload)).build().applyUnsafe();
        Util.flush(cfs2);
        for (int i = 1000; i < 1640; i++)
            new RowUpdateBuilder(cfs2.metadata(), 0, 1).clustering(i).add("v", ByteBuffer.wrap(payload)).build().applyUnsafe();
        Util.flush(cfs2);
        check("C2_two_sstables", 2, cfs2.getLiveSSTables().size());
        limits(1L, true);
        Res probe = read(cfs2, Util.cmd(cfs2, 1).fromIncl(1000).build());
        long e2 = probe.est;
        line("STAGE4 info C2 second SSTable entry est=" + e2 + " entries=" + probe.entries + " bytes=" + probe.bytes);
        limits(e2 - 1, true);
        Res up = read(cfs2, Util.cmd(cfs2, 1).fromIncl(1000).build());
        check("C2_ck_ge_1000_refused", true, up.err != null);
        long cc = count(cfs2);
        Res asc = read(cfs2, Util.cmd(cfs2, 1).build());
        check("C2_full_ascending_completes", null, asc.err);
        check("C2_full_ascending_rows", 650, asc.rows);
        check("C2_count_plus_one", cc + 1, count(cfs2));
        Res desc = read(cfs2, Util.cmd(cfs2, 1).reverse().build());
        check("C2_full_descending_refused", true, desc.err != null);

        // C3: scan
        limits(1L, true);
        long cs = count(cfs);
        Res scan = read(cfs, Util.cmd(cfs).build());
        check("C3_scan_completes", null, scan.err);
        line("STAGE4 info C3 rows " + scan.rows);
        check("C3_count_unchanged", cs, count(cfs));

        // control: master switch off
        limits(1L, false);
        Res off = freshRead(7);
        check("switch_off_not_refused", null, off.err);
        limits(null, true);

        line("STAGE4 summary mismatches " + mismatches);
        Assert.assertEquals(0, mismatches);
    }
}
