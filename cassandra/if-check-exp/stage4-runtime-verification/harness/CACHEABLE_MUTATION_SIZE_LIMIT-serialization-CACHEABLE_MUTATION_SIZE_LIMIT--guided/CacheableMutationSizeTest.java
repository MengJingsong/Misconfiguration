/*
 * Stage-4 harness, unit tier of CACHEABLE_MUTATION_SIZE_LIMIT-serialization-CACHEABLE_MUTATION_SIZE_LIMIT
 * (case file section 9, 9e unit step 2, amended 2026-10-14). Not part of upstream Cassandra.
 * Copy into test/unit/org/apache/cassandra/db/ of a local clone at cassandra-5.0.9 (package db: it reads Mutation's private fields).
 * One JVM per value: -Dcassandra.cacheable_mutation_size_limit_bytes=<L> -Dstage4.expect_limit=<L> [-Dstage4.out=<file>].
 * Delta = bytes the calling thread allocates across one call (com.sun.management.ThreadMXBean); inputs are built before it is read.
 * Prints "STAGE4 check <name> <expected> <actual> ok|MISMATCH" (the prediction) and "STAGE4 record ..." (recorded, not concluded:
 * the scratch capacity, 9a). Records a mismatch and goes on; fails at the end if any check mismatched.
 */
package org.apache.cassandra.db;

import java.io.FileWriter;
import java.io.PrintWriter;
import java.lang.management.ManagementFactory;
import java.lang.reflect.Field;
import java.lang.reflect.Method;
import java.nio.ByteBuffer;
import java.util.Arrays;
import java.util.LinkedHashMap;
import java.util.Map;

import org.junit.Assert;
import org.junit.BeforeClass;
import org.junit.Test;

import org.apache.cassandra.SchemaLoader;
import org.apache.cassandra.config.CassandraRelevantProperties;
import org.apache.cassandra.db.marshal.AsciiType;
import org.apache.cassandra.db.marshal.BytesType;
import org.apache.cassandra.io.util.DataInputBuffer;
import org.apache.cassandra.io.util.DataOutputBuffer;
import org.apache.cassandra.io.util.TeeDataInputPlus;
import org.apache.cassandra.net.MessagingService;
import org.apache.cassandra.schema.KeyspaceParams;
import org.apache.cassandra.utils.vint.VIntCoding;

public class CacheableMutationSizeTest
{
    private static final String KS = "CmsUnit";
    private static final String CF = "Standard1";          // as CommitLogTest.beforeClass() builds it (9b)
    private static final int V = MessagingService.current_version;
    private static final long SLACK = 65536;                // 9a "Heap allocated": T .. T + 64 KiB
    private static final int RECYCLE = 1048576;             // DOB_MAX_RECYCLE_BYTES default

    private static final com.sun.management.ThreadMXBean TMX = (com.sun.management.ThreadMXBean) ManagementFactory.getThreadMXBean();
    private static PrintWriter out;
    private static int checks = 0, mismatches = 0;
    private static long L;
    private static int ord;
    private static ColumnFamilyStore cfs;

    private static Field slotsF, limitF, serializedF;
    private static Method capacityM;

    @BeforeClass
    public static void beforeClass() throws Exception
    {
        String o = System.getProperty("stage4.out");
        out = o == null ? null : new PrintWriter(new FileWriter(o, true), true);
        SchemaLoader.prepareServer();
        SchemaLoader.createKeyspace(KS, KeyspaceParams.simple(1),
                                    SchemaLoader.standardCFMD(KS, CF, 0, AsciiType.instance, BytesType.instance));
        cfs = Keyspace.open(KS).getColumnFamilyStore(CF);
        slotsF = Mutation.class.getDeclaredField("cachedSerializations");
        slotsF.setAccessible(true);
        limitF = Mutation.class.getDeclaredField("CACHEABLE_MUTATION_SIZE_LIMIT");
        limitF.setAccessible(true);
        serializedF = Class.forName("org.apache.cassandra.db.Mutation$CachedSerialization").getDeclaredField("serialized");
        serializedF.setAccessible(true);
        capacityM = DataOutputBuffer.class.getDeclaredMethod("capacity");
        capacityM.setAccessible(true);
    }

    // ------------------------------------------------------------------ output

    private static void line(String s)
    {
        System.out.println(s);
        if (out != null) out.println(s);
    }

    private static void check(String name, Object expected, Object actual)
    {
        boolean ok = String.valueOf(expected).equals(String.valueOf(actual));
        checks++;
        if (!ok) mismatches++;
        line("STAGE4 check " + name + " " + expected + " " + actual + " " + (ok ? "ok" : "MISMATCH"));
    }

    private static void record(String name, String expected, Object actual, boolean holds)
    {
        line("STAGE4 record " + name + " " + expected + " " + actual + " " + (holds ? "as-predicted" : "differs"));
    }

    private static void note(String name, Object value)
    {
        line("STAGE4 note " + name + " " + value);
    }

    // ------------------------------------------------------------------ probes

    private static long allocated()
    {
        return TMX.getThreadAllocatedBytes(Thread.currentThread().getId());
    }

    /** a fresh mutation whose value is p zero bytes, built as CommitLogTest.getMaxRecordDataSize() builds it (9e step 3) */
    private static Mutation m(long p)
    {
        return new RowUpdateBuilder(cfs.metadata(), 0, "k").clustering("bytes").add("val", ByteBuffer.allocate((int) p)).build();
    }

    private static Object slot(Mutation x) throws Exception
    {
        return ((Object[]) slotsF.get(x))[ord];
    }

    private static String cls(Object s)
    {
        return s == null ? "null" : s.getClass().getSimpleName();
    }

    private static byte[] copy(Object s) throws Exception
    {
        return s != null && cls(s).equals("CachedSerialization") ? (byte[]) serializedF.get(s) : null;
    }

    private static long scratchCapacity() throws Exception
    {
        return (Long) capacityM.invoke(DataOutputBuffer.scratchBuffer.get());
    }

    /** the check's operand for a payload of p bytes, on a fresh mutation */
    private static long T(long p)
    {
        return Mutation.serializer.serializedSize(m(p), V);
    }

    // ------------------------------------------------------------------ the test

    @Test
    public void cacheableMutationSize() throws Throwable
    {
        Long expect = Long.getLong("stage4.expect_limit");
        Assert.assertNotNull("-Dstage4.expect_limit is required", expect);
        L = expect;
        ord = MessagingService.getVersionOrdinal(V);

        // step 1: setup
        line("STAGE4 setup L=" + L + " current_version=" + V + " ordinal=" + ord + " versions=" + Arrays.toString(MessagingService.Version.values())
             + " dob.allocate_type=" + System.getProperty("cassandra.dob.allocate_type") + " dob_max_recycle_bytes=" + System.getProperty("cassandra.dob_max_recycle_bytes")
             + " java=" + System.getProperty("java.version"));
        check("setup.allocated_bytes_supported", true, TMX.isThreadAllocatedMemorySupported());
        if (!TMX.isThreadAllocatedMemorySupported())
        {
            line("STAGE4 INVALID isThreadAllocatedMemorySupported() is false");
            Assert.fail("invalid run");
        }
        TMX.setThreadAllocatedMemoryEnabled(true);

        // step 2: read-back
        check("readback.field", L, limitF.getLong(null));
        check("readback.property", L, CassandraRelevantProperties.CACHEABLE_MUTATION_SIZE_LIMIT.getLong());

        // step 3: calibrate (L >= 100,000)
        Map<String, Long> sizes = new LinkedHashMap<>();
        long pStar = -1;
        if (L >= 100000)
        {
            long t1 = T(1);
            long k1 = t1 - 2;
            int s = VIntCoding.computeUnsignedVIntSize(L);
            long p = L - 1 - k1 - s;
            int steps = 0;
            while (T(p) >= L && steps < 64) { p--; steps++; }
            while (T(p + 1) < L && steps < 64) { p++; steps++; }
            check("calibration.steps_within_64", true, steps < 64);
            pStar = p;
            long tp = T(pStar), tp1 = T(pStar + 1);
            note("calibration", "T(1)=" + t1 + " k1=" + k1 + " s=" + s + " start=" + (L - 1 - k1 - s) + " steps=" + steps
                                + " p*=" + pStar + " T(p*)=" + tp + " T(p*+1)=" + tp1 + " k=T(p*)-p*=" + (tp - pStar));
            check("calibration.T(p*)", L - 1, tp);
            check("calibration.T(p*+1)", L, tp1);
            sizes.put("1024", 1024L);
            sizes.put("p*", pStar);
            sizes.put("p*+1", pStar + 1);
            sizes.put("1.01L", Math.round(1.01 * L));
            sizes.put("2L", 2 * L);
        }
        else
        {
            sizes.put("1024", 1024L);
            sizes.put("100000", 100000L);
            sizes.put("3000000", 3000000L);
        }

        // step 4: serialize site
        Map<String, Long> tOf = new LinkedHashMap<>();
        Map<String, Long> deltaOf = new LinkedHashMap<>();
        for (Map.Entry<String, Long> e : sizes.entrySet())
        {
            String n = e.getKey();
            long p = e.getValue();
            Mutation w = m(p);
            Mutation.serializer.serializedSize(w, V);            // warm-up on a throw-away mutation of the same size
            Mutation x = m(p);                                    // fresh: the slot is filled by the first call and never cleared
            long c0 = scratchCapacity();
            long a0 = allocated();
            long t = Mutation.serializer.serializedSize(x, V);
            long a1 = allocated();
            long c1 = scratchCapacity();
            Object s = slot(x);
            long delta = a1 - a0;
            tOf.put(n, t);
            deltaOf.put(n, delta);
            boolean cached = t < L;                               // L <= 0: never
            note("ser." + n, "payload=" + p + " T=" + t + " slot=" + cls(s) + " delta=" + delta + " scratch " + c0 + "->" + c1);
            check("ser." + n + ".class", cached ? "CachedSerialization" : "SizeOnlyCacheableSerialization", cls(s));
            if (cached)
                check("ser." + n + ".length", t, copy(s) == null ? -1 : copy(s).length);
            if (n.equals("p*"))
            {
                boolean kept = c1 >= t && c1 <= RECYCLE;
                record("ser.p*.scratch_after", ">=T&&<=1048576|128", c1, kept || c1 == 128);
            }
            if (n.equals("p*+1"))
                record("ser.p*+1.scratch_unchanged", Long.toString(c0), c1, c0 == c1);
        }
        if (L >= 100000)
        {
            long diff = deltaOf.get("p*") - deltaOf.get("p*+1");
            long t = tOf.get("p*");
            note("heap.delta_diff", "delta(p*)=" + deltaOf.get("p*") + " delta(p*+1)=" + deltaOf.get("p*+1") + " diff=" + diff + " T(p*)=" + t);
            check("heap.delta_diff_in_[" + t + "," + (t + SLACK) + "]", true, diff >= t && diff <= t + SLACK);
        }

        // step 5: receive site
        for (Map.Entry<String, Long> e : sizes.entrySet())
        {
            String n = e.getKey();
            long p = e.getValue();
            Mutation x = m(p);
            DataOutputBuffer o = new DataOutputBuffer();          // not the scratch buffer
            Mutation.serializer.serialize(x, o, V);
            byte[] w = o.toByteArray();
            Mutation r = Mutation.serializer.deserialize(new DataInputBuffer(w), V);
            Object s = slot(r);
            boolean cached = L <= 0 || w.length < L;
            byte[] c = copy(s);
            note("recv." + n, "payload=" + p + " W=" + w.length + " slot=" + cls(s) + (c == null ? "" : " copy=" + c.length));
            check("recv." + n + ".wire_length_is_T", tOf.get(n), w.length);
            check("recv." + n + ".class", cached ? "CachedSerialization" : "null", cls(s));
            if (cached)
            {
                check("recv." + n + ".length", w.length, c == null ? -1 : c.length);
                check("recv." + n + ".bytes_equal_wire", true, c != null && Arrays.equals(c, w));
            }
            Mutation.serializer.serializedSize(r, V);
            check("recv." + n + ".after_size.class", cached ? "CachedSerialization" : "SizeOnlyCacheableSerialization", cls(slot(r)));
        }

        // step 6: the tee alone
        if (L > 1)
        {
            byte[] src = new byte[(int) (2 * L)];
            DataOutputBuffer b1 = new DataOutputBuffer();
            TeeDataInputPlus t1 = new TeeDataInputPlus(new DataInputBuffer(src), b1, L);
            t1.readFully(new byte[(int) (L - 1)]);
            check("tee.L-1.limit_reached", false, t1.isLimitReached());
            check("tee.L-1.mirrored", L - 1, b1.getLength());
        }
        if (L >= 1)
        {
            byte[] src = new byte[L > 1 ? (int) (2 * L) : 3000000];
            DataOutputBuffer b2 = new DataOutputBuffer();
            TeeDataInputPlus t2 = new TeeDataInputPlus(new DataInputBuffer(src), b2, L);
            t2.readFully(new byte[(int) L]);
            check("tee.L.limit_reached", true, t2.isLimitReached());
            check("tee.L.mirrored", 0, b2.getLength());
        }
        if (L == 0)
        {
            byte[] src = new byte[3000000];
            DataOutputBuffer b3 = new DataOutputBuffer();
            TeeDataInputPlus t3 = new TeeDataInputPlus(new DataInputBuffer(src), b3, L);
            t3.readFully(new byte[3000000]);
            check("tee.0.limit_reached", false, t3.isLimitReached());
            check("tee.0.mirrored", 3000000, b3.getLength());
        }

        // step 7: idle. "Unchanged" is read against the meter's own cost: two back-to-back reads of the allocated bytes.
        long m0 = allocated();
        long m1 = allocated();
        long meter = m1 - m0;
        long c0 = scratchCapacity();
        long a0 = allocated();
        Thread.sleep(2000);
        long a1 = allocated();
        long c1 = scratchCapacity();
        note("idle", "meter=" + meter + " delta=" + (a1 - a0) + " scratch " + c0 + "->" + c1);
        check("idle.alloc_delta_equals_meter", meter, a1 - a0);
        check("idle.scratch_unchanged", c0, c1);

        line("STAGE4 done L=" + L + " checks=" + checks + " mismatches=" + mismatches);
        Assert.assertEquals("STAGE4 mismatches (see STAGE4 check lines)", 0, mismatches);
    }
}
