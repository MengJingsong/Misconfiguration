/*
 * Stage-4 harness, unit tier (B2) of max_mutation_size-allocateBytes-slabCapacity--autonomous (case file frozen
 * sha256 8ecb18b2...). Not upstream. Package org.apache.cassandra.hints, because HintsBuffer.create/allocate and the
 * Allocation class are package-private. Copied into a local clone's test/unit/org/apache/cassandra/hints/ by unit-run.sh.
 *
 * For each slab capacity C = 1 MiB, 4 MiB, 32 MiB (B2b) and each payload h = 100 B, 1 KiB, C/2 - 12 (B2b, B2h):
 *   - the JVM's "direct" BufferPoolMXBean (MemoryUsed, Count) around HintsBuffer.create(C)   (B2f row 1)
 *   - allocate(h) until the first null: n = floor(C/(h+12)), sum of accepted totalSize <= C, remaining() == C - sum
 *     after every accepted allocation, then remaining() == 0 and isClosed()                     (B2f row 2)
 *   - five more allocate(h) after the close: all null, direct pool unchanged                    (B2f row 3)
 *   - recycle(): capacity C, remaining C, open; the same n accepted again; direct pool unchanged (B2f row 5)
 *   - on an empty recycled slab: allocate(C/2 - 12) accepted; allocate(C/2 - 11) and allocate(C/2) throw
 *     IllegalArgumentException and leave remaining() == C                                         (B2f row 4)
 *   - free(): the direct pool falls by C (extra, not a B2f row)
 * and the derived-slab arithmetic of HintsService.java:110, max(2 * max_mutation_size, 32 MiB), for max_mutation_size
 * 4 MiB, 16 MiB, 32 MiB (B2f row 6), as a pure arithmetic assertion (B2b: the singleton cannot be re-created).
 *
 * Output: one "STAGE4 check <name> ok|MISMATCH <detail>" line per relation and "STAGE4 case ..." readings, on stdout and
 * appended to the file named by the system property stage4.out (if set). A MISMATCH is recorded and the test goes on;
 * the JUnit result fails at the end if any check mismatched.
 */
package org.apache.cassandra.hints;

import java.io.FileWriter;
import java.io.IOException;
import java.io.PrintWriter;
import java.lang.management.BufferPoolMXBean;
import java.lang.management.ManagementFactory;

import org.junit.AfterClass;
import org.junit.BeforeClass;
import org.junit.Test;

import org.apache.cassandra.config.DatabaseDescriptor;

import static org.junit.Assert.assertEquals;

public class SlabCapacityProbeTest
{
    static final int MIB = 1 << 20;
    static final int[] CAPACITIES = { MIB, 4 * MIB, 32 * MIB };
    static final int OVERHEAD = HintsBuffer.ENTRY_OVERHEAD_SIZE;   // 12
    static PrintWriter file;
    static int checks, mismatches;

    @BeforeClass
    public static void setUp() throws IOException
    {
        DatabaseDescriptor.daemonInitialization();
        String f = System.getProperty("stage4.out");
        if (f != null)
            file = new PrintWriter(new FileWriter(f, true), true);
        out("STAGE4 start java=" + System.getProperty("java.version") + " maxMemory=" + Runtime.getRuntime().maxMemory()
            + " ENTRY_OVERHEAD_SIZE=" + OVERHEAD);
    }

    @AfterClass
    public static void tearDown()
    {
        out("STAGE4 summary checks=" + checks + " mismatches=" + mismatches);
        if (file != null)
            file.close();
    }

    static void out(String s)
    {
        System.out.println(s);
        if (file != null)
            file.println(s);
    }

    static void check(String name, boolean ok, String detail)
    {
        checks++;
        if (!ok)
            mismatches++;
        out("STAGE4 check " + name + " " + (ok ? "ok" : "MISMATCH") + " " + detail);
    }

    static BufferPoolMXBean direct()
    {
        for (BufferPoolMXBean b : ManagementFactory.getPlatformMXBeans(BufferPoolMXBean.class))
            if (b.getName().equals("direct"))
                return b;
        throw new IllegalStateException("no direct pool");
    }

    static long[] pool()
    {
        BufferPoolMXBean d = direct();
        return new long[]{ d.getMemoryUsed(), d.getCount() };
    }

    static long[] settledPool() throws InterruptedException
    {
        System.gc();
        Thread.sleep(300);
        return pool();
    }

    /** fill: allocate(h) until the first null; returns {n, sum, remainingMismatches} */
    static long[] fill(HintsBuffer b, int h)
    {
        long n = 0, sum = 0, remBad = 0;
        while (true)
        {
            HintsBuffer.Allocation a = b.allocate(h);
            if (a == null)
                break;
            a.close();
            n++;
            sum += h + OVERHEAD;
            if (b.remaining() != b.capacity() - sum)
                remBad++;
        }
        return new long[]{ n, sum, remBad };
    }

    static boolean throwsIAE(HintsBuffer b, int h)
    {
        try
        {
            HintsBuffer.Allocation a = b.allocate(h);
            if (a != null)
                a.close();
            return false;
        }
        catch (IllegalArgumentException e)
        {
            return true;
        }
    }

    @Test
    public void slabCapacity() throws Exception
    {
        for (int c : CAPACITIES)
        {
            String cn = "C=" + (c / MIB) + "MiB";
            long[] p0 = settledPool();
            HintsBuffer buf = HintsBuffer.create(c);
            long[] p1 = pool();
            out("STAGE4 case " + cn + " create direct_used " + p0[0] + "->" + p1[0] + " count " + p0[1] + "->" + p1[1]);
            check(cn + " create: direct MemoryUsed +C", p1[0] - p0[0] == c, "delta=" + (p1[0] - p0[0]) + " C=" + c);
            check(cn + " create: direct Count +1", p1[1] - p0[1] == 1, "delta=" + (p1[1] - p0[1]));
            check(cn + " capacity()==C", buf.capacity() == c, "capacity=" + buf.capacity());
            check(cn + " fresh: remaining()==C and open", buf.remaining() == c && !buf.isClosed(), "remaining=" + buf.remaining());

            int[] hs = { 100, 1024, c / 2 - OVERHEAD };
            boolean first = true;
            for (int h : hs)
            {
                String hn = cn + " h=" + h;
                HintsBuffer b = first ? buf : buf.recycle();
                first = false;
                long[] q0 = pool();
                long expect = c / (h + OVERHEAD);
                long[] r = fill(b, h);
                long[] q1 = pool();
                out("STAGE4 case " + hn + " n=" + r[0] + " expected_n=" + expect + " sum=" + r[1] + " C=" + c
                    + " remaining_after=" + b.remaining() + " closed=" + b.isClosed());
                check(hn + " null at n+1, n=floor(C/(h+12))", r[0] == expect, "n=" + r[0] + " expected=" + expect);
                check(hn + " accepted sum <= C", r[1] <= c, "sum=" + r[1] + " C=" + c + " C-sum=" + (c - r[1]));
                check(hn + " remaining()==C-sum after every accepted allocation", r[2] == 0, "bad=" + r[2]);
                check(hn + " after the null: remaining()==0 and isClosed()", b.remaining() == 0 && b.isClosed(),
                      "remaining=" + b.remaining() + " closed=" + b.isClosed());
                int extraNull = 0;
                for (int i = 0; i < 5; i++)
                    if (b.allocate(Math.min(h, 1)) == null && b.allocate(h) == null)
                        extraNull++;
                long[] q2 = pool();
                check(hn + " closed slab: 5 more allocate (1 B and h) all null", extraNull == 5, "null pairs=" + extraNull);
                check(hn + " no direct growth while filling and after close", q1[0] == q0[0] && q2[0] == q0[0] && q2[1] == q0[1],
                      "used " + q0[0] + "/" + q1[0] + "/" + q2[0] + " count " + q0[1] + "/" + q1[1] + "/" + q2[1]);

                // recycle: same slab, same n again
                HintsBuffer rb = b.recycle();
                long[] q3 = pool();
                check(hn + " recycle: capacity C, remaining C, open", rb.capacity() == c && rb.remaining() == c && !rb.isClosed(),
                      "capacity=" + rb.capacity() + " remaining=" + rb.remaining() + " closed=" + rb.isClosed());
                long[] r2 = fill(rb, h);
                long[] q4 = pool();
                check(hn + " recycle: same n accepted again", r2[0] == r[0] && r2[1] == r[1], "n=" + r2[0] + " sum=" + r2[1]);
                check(hn + " recycle: no direct growth", q3[0] == q0[0] && q4[0] == q0[0] && q4[1] == q0[1],
                      "used " + q3[0] + "/" + q4[0] + " count " + q3[1] + "/" + q4[1]);
                buf = rb;
            }

            // largest legal hint on an empty slab, and the two just above it
            HintsBuffer e1 = buf.recycle();
            HintsBuffer.Allocation big = e1.allocate(c / 2 - OVERHEAD);
            boolean bigOk = big != null;
            if (big != null)
                big.close();
            check(cn + " allocate(C/2-12) accepted on an empty slab", bigOk && e1.remaining() == c / 2,
                  "accepted=" + bigOk + " remaining=" + e1.remaining());
            HintsBuffer e2 = e1.recycle();
            boolean t1 = throwsIAE(e2, c / 2 - OVERHEAD + 1);
            boolean t2 = throwsIAE(e2, c / 2);
            check(cn + " allocate(C/2-11) throws IllegalArgumentException", t1, "threw=" + t1);
            check(cn + " allocate(C/2) throws IllegalArgumentException", t2, "threw=" + t2);
            check(cn + " a refused oversize hint leaves the slab untouched", e2.remaining() == c && !e2.isClosed(),
                  "remaining=" + e2.remaining() + " closed=" + e2.isClosed());
            long[] p5 = pool();
            check(cn + " end of C: direct pool still +C over the pre-create baseline", p5[0] - p0[0] == c && p5[1] - p0[1] == 1,
                  "used delta=" + (p5[0] - p0[0]) + " count delta=" + (p5[1] - p0[1]));

            // free (extra, not a B2f row)
            e2.free();
            long[] p6 = pool();
            out("STAGE4 case " + cn + " free direct_used " + p5[0] + "->" + p6[0] + " count " + p5[1] + "->" + p6[1]);
            check(cn + " free (extra): direct MemoryUsed -C, Count -1", p5[0] - p6[0] == c && p5[1] - p6[1] == 1,
                  "used delta=" + (p6[0] - p5[0]) + " count delta=" + (p6[1] - p5[1]));
        }

        // derived slab size, HintsService.java:110: Math.max(DatabaseDescriptor.getMaxMutationSize() * 2, MIN_BUFFER_SIZE)
        int min = 32 << 20;
        int[][] derived = { { 4 * MIB, 32 * MIB }, { 16 * MIB, 32 * MIB }, { 32 * MIB, 64 * MIB } };
        for (int[] d : derived)
        {
            int slab = Math.max(d[0] * 2, min);
            check("derived slab mms=" + (d[0] / MIB) + "MiB -> " + (d[1] / MIB) + "MiB", slab == d[1], "slab=" + slab);
        }
        // the default max_mutation_size: commitlog_segment_size 32 MiB / 2 (DatabaseDescriptor.java:898-899), in KiB
        int defaultMmsKiB = (32 * 1024) / 2;
        check("derived default mms = 32MiB/2 = 16384KiB -> slab 32MiB", defaultMmsKiB == 16384
                                                                         && Math.max(defaultMmsKiB * 1024 * 2, min) == 32 * MIB,
              "mmsKiB=" + defaultMmsKiB);
        // this test JVM's own yaml (test/conf), for the record only
        out("STAGE4 case test-yaml max_mutation_size=" + DatabaseDescriptor.getMaxMutationSize()
            + " -> slab " + Math.max(DatabaseDescriptor.getMaxMutationSize() * 2, min));

        assertEquals("mismatches", 0, mismatches);
    }
}
