/*
 * Stage-4 harness, unit tier of local_read_size_fail_threshold-addSize-failBytes (case file section 9).
 * Not part of upstream Cassandra. Copy into test/unit/org/apache/cassandra/db/ of a local clone at cassandra-5.0.9.
 * System property stage4.out: a file that also receives the STAGE4 lines.
 */
package org.apache.cassandra.db;

import java.io.FileWriter;
import java.io.PrintWriter;
import java.lang.management.ManagementFactory;
import java.nio.ByteBuffer;
import java.util.ArrayList;
import java.util.Arrays;
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
import org.apache.cassandra.cql3.Operator;
import org.apache.cassandra.db.filter.DataLimits;
import org.apache.cassandra.db.filter.LocalReadSizeTooLargeException;
import org.apache.cassandra.db.marshal.BytesType;
import org.apache.cassandra.db.marshal.Int32Type;
import org.apache.cassandra.db.partitions.UnfilteredPartitionIterator;
import org.apache.cassandra.db.rows.Row;
import org.apache.cassandra.db.rows.Unfiltered;
import org.apache.cassandra.db.rows.UnfilteredRowIterator;
import org.apache.cassandra.net.MessagingService;
import org.apache.cassandra.net.ParamType;
import org.apache.cassandra.schema.KeyspaceParams;
import org.apache.cassandra.schema.TableMetadata;
import org.apache.cassandra.utils.ObjectSizes;

public class LocalReadSizeGuardTest
{
    static final String KS = "ks1", T = "t";
    static final int N = 2000, PAYLOAD = 1000;
    static PrintWriter out;
    static int mismatches = 0;
    static ColumnFamilyStore cfs;
    static final com.sun.management.ThreadMXBean TMX = (com.sun.management.ThreadMXBean) ManagementFactory.getThreadMXBean();

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
        SchemaLoader.prepareServer();
        SchemaLoader.createKeyspace(KS, KeyspaceParams.simple(1),
                TableMetadata.builder(KS, T)
                             .addPartitionKeyColumn("pk", Int32Type.instance)
                             .addClusteringColumn("ck", Int32Type.instance)
                             .addRegularColumn("v", BytesType.instance));
        cfs = Keyspace.open(KS).getColumnFamilyStore(T);
        cfs.disableAutoCompaction();
        byte[] payload = new byte[PAYLOAD];
        for (int i = 0; i < N; i++)
            new RowUpdateBuilder(cfs.metadata(), 0, 1).clustering(i).add("v", ByteBuffer.wrap(payload)).build().applyUnsafe();
        Util.flush(cfs);
        line("STAGE4 info sstables " + cfs.getLiveSSTables().size());
        line("STAGE4 info jvm " + System.getProperty("java.version") + " " + ManagementFactory.getRuntimeMXBean().getInputArguments());
        try
        {
            line("STAGE4 info UseCompressedOops " + ManagementFactory.getPlatformMXBean(com.sun.management.HotSpotDiagnosticMXBean.class).getVMOption("UseCompressedOops").getValue());
        }
        catch (Throwable t) { line("STAGE4 info UseCompressedOops unknown " + t); }
        line("STAGE4 info allocatedBytesSupported " + TMX.isThreadAllocatedMemorySupported());
    }

    static void limits(Long warn, Long fail)
    {
        DatabaseDescriptor.setReadThresholdsEnabled(true);
        DatabaseDescriptor.setRowIndexReadSizeWarnThreshold(null);
        DatabaseDescriptor.setRowIndexReadSizeFailThreshold(null);
        DatabaseDescriptor.setLocalReadSizeWarnThreshold(warn == null ? null : new DataStorageSpec.LongBytesBound(warn, DataStorageSpec.DataStorageUnit.BYTES));
        DatabaseDescriptor.setLocalReadSizeFailThreshold(fail == null ? null : new DataStorageSpec.LongBytesBound(fail, DataStorageSpec.DataStorageUnit.BYTES));
    }

    static class Result
    {
        int rows; Throwable err; Long fail, warn; String msg; Clustering<?> last;
    }

    /** iterate the rows one at a time until the end or the guard's exception */
    static Result iterate(ReadCommand cmd, boolean flag)
    {
        MessageParams.reset();
        if (flag) cmd.trackWarnings();
        Result r = new Result();
        try (ReadExecutionController c = cmd.executionController(); UnfilteredPartitionIterator it = cmd.executeLocally(c))
        {
            while (it.hasNext())
                try (UnfilteredRowIterator p = it.next())
                {
                    while (p.hasNext())
                    {
                        Unfiltered u = p.next();
                        if (u.isRow()) { r.rows++; r.last = ((Row) u).clustering(); }
                    }
                }
        }
        catch (LocalReadSizeTooLargeException e) { r.err = e; r.msg = e.getMessage(); }
        r.fail = MessageParams.get(ParamType.LOCAL_READ_SIZE_FAIL);
        r.warn = MessageParams.get(ParamType.LOCAL_READ_SIZE_WARN);
        return r;
    }

    static long allocated() { return TMX.getThreadAllocatedBytes(Thread.currentThread().getId()); }

    /** build the response as a replica does; returns {allocated bytes, serialized size or -1 on abort} */
    static long[] respond(ReadCommand cmd, boolean flag)
    {
        MessageParams.reset();
        if (flag) cmd.trackWarnings();
        long a0 = allocated();
        long size = -1;
        try (ReadExecutionController c = cmd.executionController(); UnfilteredPartitionIterator it = cmd.executeLocally(c))
        {
            ReadResponse resp = cmd.createResponse(it, c.getRepairedDataInfo());
            size = ReadResponse.serializer.serializedSize(resp, MessagingService.current_version);
        }
        catch (LocalReadSizeTooLargeException e) { }
        return new long[]{ allocated() - a0, size };
    }

    static long median(java.util.function.Supplier<ReadCommand> mk, boolean flag, int warm, int runs)
    {
        for (int i = 0; i < warm; i++) respond(mk.get(), flag);
        long[] d = new long[runs];
        for (int i = 0; i < runs; i++) d[i] = respond(mk.get(), flag)[0];
        Arrays.sort(d);
        line("STAGE4 info deltas " + Arrays.toString(d));
        return d[runs / 2];
    }

    static ReadCommand full() { return Util.cmd(cfs, 1).build(); }
    static ReadCommand upTo(int toExcl) { return Util.cmd(cfs, 1).fromIncl(0).toExcl(toExcl).build(); }

    static long parseX(String msg)
    {
        Matcher m = Pattern.compile("attempted to read (\\d+) bytes").matcher(msg == null ? "" : msg);
        return m.find() ? Long.parseLong(m.group(1)) : -1;
    }

    @Test
    public void guard() throws Exception
    {
        // 2. mirror
        limits(null, null);
        List<Long> h = new ArrayList<>();
        long b0;
        {
            MessageParams.reset();
            ReadCommand cmd = full();
            long key = 0, del = 0;
            try (ReadExecutionController c = cmd.executionController(); UnfilteredPartitionIterator it = cmd.executeLocally(c))
            {
                try (UnfilteredRowIterator p = it.next())
                {
                    key = ObjectSizes.sizeOnHeapOf(p.partitionKey().getKey());
                    del = p.partitionLevelDeletion().unsharedHeapSize();
                    while (p.hasNext()) { Unfiltered u = p.next(); if (u.isRow()) h.add(((Row) u).unsharedHeapSize()); }
                }
            }
            b0 = key + del;
        }
        check("rows", N, h.size());
        boolean same = h.stream().distinct().count() == 1;
        checkTrue("same_h", same, "h=" + h.get(0));
        long hh = h.get(0);
        long[] T = new long[N + 1];
        T[0] = b0;
        for (int i = 1; i <= N; i++) T[i] = T[i - 1] + h.get(i - 1);
        line("STAGE4 info b0 " + b0 + " h " + hh + " T(N) " + T[N] + " T(100) " + T[100]);
        // known answer
        limits(1L, null);
        Result ka = iterate(full(), true);
        check("known_answer_T(N)", T[N], ka.warn);
        check("known_answer_rows", N, ka.rows);

        long[] fs = { 65536L, 262144L, 1048576L };
        long[] dd = new long[3];
        long d0, dfull;
        // delta references (wrapped, never aborting)
        limits(null, 8388608L);
        d0 = median(() -> upTo(1), true, 2, 5);
        dfull = median(() -> full(), true, 2, 5);
        long[] big = respond(full(), true);
        line("STAGE4 info d0 " + d0 + " dfull " + dfull + " a " + ((dfull - d0) / (double) (N - 1)) + " responseBytes " + big[1] + " failParam " + MessageParams.get(ParamType.LOCAL_READ_SIZE_FAIL));
        check("above_data_completes_rows", N, iterate(full(), true).rows);
        check("above_data_no_fail_param", null, MessageParams.get(ParamType.LOCAL_READ_SIZE_FAIL));

        for (int k = 0; k < 3; k++)
        {
            long F = fs[k];
            limits(null, F);
            check("readback_" + F, F, DatabaseDescriptor.getLocalReadSizeFailThreshold().toBytes());
            int istar = 1;
            while (T[istar] < F) istar++;
            Result r = iterate(full(), true);
            check("stop_delivered_" + F, istar - 1, r.rows);
            check("stop_exception_" + F, true, r.err != null);
            check("stop_X_msg_" + F, T[istar], parseX(r.msg));
            check("stop_X_param_" + F, T[istar], r.fail);
            checkTrue("stop_X_in_range_" + F, T[istar] >= F && T[istar] < F + hh, "X=" + T[istar]);
            dd[k] = median(() -> full(), true, 2, 5);
            line("STAGE4 info delta_" + F + " " + dd[k] + " istar " + istar);
        }
        double r1 = (dd[1] - d0) / (double) (dd[0] - d0), r2 = (dd[2] - d0) / (double) (dd[1] - d0);
        line("STAGE4 info ratios 1:" + r1 + " : " + r2 + " (expect about 4 and 4)");
        checkTrue("alloc_ratio_4", Math.abs(r1 - 4) / 4 < 0.15 && Math.abs(r2 - 4) / 4 < 0.15, r1 + " " + r2);

        // boundary pair at 65536 scale: F = T(100) and T(100)+1
        limits(null, T[100]);
        Result b1 = iterate(full(), true);
        check("boundary_eq_delivered", 99, b1.rows);
        limits(null, T[100] + 1);
        Result b2 = iterate(full(), true);
        check("boundary_plus1_delivered", 100, b2.rows);
        check("boundary_plus1_X", T[101], b2.fail);

        // C1 names filter
        int M = 1000;
        Object[] names = new Object[M];
        for (int i = 0; i < M; i++) names[i] = i;
        limits(null, 65536L);
        long dn_lim = median(() -> { AbstractReadCommandBuilder b = Util.cmd(cfs, 1); for (Object o : names) b.includeRow(o); return b.build(); }, true, 2, 5);
        long ds_lim = median(() -> upTo(M), true, 2, 5);
        limits(null, null);
        long dn_unl = median(() -> { AbstractReadCommandBuilder b = Util.cmd(cfs, 1); for (Object o : names) b.includeRow(o); return b.build(); }, true, 2, 5);
        line("STAGE4 info C1 names_limited " + dn_lim + " names_unlimited " + dn_unl + " slice_limited " + ds_lim + " d0 " + d0);
        checkTrue("C1_names_alloc_within_10pct", Math.abs(dn_lim - dn_unl) / (double) dn_unl < 0.10, dn_lim + " vs " + dn_unl);
        checkTrue("C1_slice_alloc_small", ds_lim - d0 < 0.25 * (dn_unl - d0), "slice " + ds_lim + " names_unl " + dn_unl);
        limits(null, 65536L);
        AbstractReadCommandBuilder nb = Util.cmd(cfs, 1);
        for (Object o : names) nb.includeRow(o);
        Result nr = iterate(nb.build(), true);
        check("C1_names_aborts", true, nr.err != null);

        // C2 paging
        for (long F : new long[]{ 262144L, 65536L })
        {
            limits(null, F);
            int total = 0, aborts = 0;
            ReadCommand cmd = Util.cmd(cfs, 1).withLimit(100).build();
            for (int page = 0; page < 20; page++)
            {
                Result pr = iterate(cmd, page == 0);
                total += pr.rows;
                if (pr.err != null) { aborts++; break; }
                cmd = ((SinglePartitionReadCommand) cmd).forPaging(pr.last, DataLimits.cqlLimits(100));
            }
            line("STAGE4 info C2 F=" + F + " rows=" + total + " aborts=" + aborts);
            if (F == 262144L) { check("C2_paged_rows", N, total); check("C2_paged_aborts", 0, aborts); }
            else check("C2_small_first_page_aborts", 1, aborts);
        }

        // C3 filter that matches nothing
        limits(null, 262144L);
        Result fr = iterate(Util.cmd(cfs, 1).filterOn("v", Operator.EQ, ByteBuffer.wrap(new byte[]{ 9, 9, 9 })).build(), true);
        check("C3_filter_aborts", true, fr.err != null);
        check("C3_filter_rows", 0, fr.rows);
        limits(null, null);
        Result fu = iterate(Util.cmd(cfs, 1).filterOn("v", Operator.EQ, ByteBuffer.wrap(new byte[]{ 9, 9, 9 })).build(), true);
        check("C3_unlimited_completes", null, fu.err);
        check("C3_unlimited_rows", 0, fu.rows);

        // controls
        limits(null, 65536L);
        Result nf = iterate(full(), false);
        check("control_noflag_completes", null, nf.err);
        check("control_noflag_rows", N, nf.rows);
        check("control_noflag_no_params", null, nf.fail);
        limits(65536L, null);
        Result wt = iterate(full(), true);
        check("control_warn_twin_completes", null, wt.err);
        check("control_warn_twin_param", T[N], wt.warn);

        line("STAGE4 summary mismatches " + mismatches);
        Assert.assertEquals(0, mismatches);
    }
}
