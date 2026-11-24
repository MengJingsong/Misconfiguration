/*
 * Stage-4 harness, case rowsize-checkcanread-bytesread--autonomous (o122), unit tier B2.
 * Not upstream. Copied into $RUN/src/test/unit/org/apache/cassandra/io/util/ for the run.
 */
package org.apache.cassandra.io.util;

import java.io.EOFException;
import java.io.FileWriter;
import java.io.IOException;
import java.lang.management.ManagementFactory;
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;

import org.junit.BeforeClass;
import org.junit.Test;

import org.apache.cassandra.config.DatabaseDescriptor;
import org.apache.cassandra.db.marshal.ByteArrayAccessor;
import org.apache.cassandra.db.marshal.BytesType;

import static org.junit.Assert.assertEquals;
import static org.junit.Assert.assertTrue;
import static org.junit.Assert.fail;

public class TrackedDataInputPlusLimitTest
{
    static final long MiB = 1L << 20;
    static final int R = 1024;
    static final int REPS = 3;

    static com.sun.management.ThreadMXBean tmx;

    @BeforeClass
    public static void setup() throws Exception
    {
        DatabaseDescriptor.daemonInitialization();
        tmx = (com.sun.management.ThreadMXBean) ManagementFactory.getThreadMXBean();
        assertTrue("thread allocated memory supported", tmx.isThreadAllocatedMemorySupported());
        tmx.setThreadAllocatedMemoryEnabled(true);
        assertTrue("thread allocated memory enabled", tmx.isThreadAllocatedMemoryEnabled());
        // warm-up (B2d): V = 1 MiB, L = 64, so class loading does not land in the measurement
        for (int i = 0; i < 3; i++)
            one("warmup", 64, MiB, 256 * MiB, false, false);
        out("WARMUP done");
    }

    static synchronized void out(String s)
    {
        System.out.println(s);
        String f = System.getenv("S4_OUT");
        if (f != null)
        {
            try (FileWriter w = new FileWriter(f, true)) { w.write(s + "\n"); }
            catch (IOException e) { throw new RuntimeException(e); }
        }
    }

    static long allocated()
    {
        return tmx.getThreadAllocatedBytes(Thread.currentThread().getId());
    }

    /** B2c: unsigned vint of V, then R zero bytes (or V bytes when wellFormed). */
    static byte[] src(long V, boolean wellFormed) throws IOException
    {
        try (DataOutputBuffer dob = new DataOutputBuffer())
        {
            dob.writeUnsignedVInt(V);
            int vintLen = dob.getLength();
            byte[] head = dob.toByteArray();
            int tail = wellFormed ? (int) V : R;
            byte[] b = new byte[vintLen + tail];
            System.arraycopy(head, 0, b, 0, vintLen);
            return b;
        }
    }

    static final class Reading
    {
        long alloc; String exc; long bytesRead; int vintLen;
    }

    static Reading one(String row, long L, long V, long max, boolean wellFormed, boolean print) throws IOException
    {
        byte[] s = src(V, wellFormed);
        Reading r = new Reading();
        r.vintLen = s.length - (wellFormed ? (int) V : R);
        TrackedDataInputPlus in = new TrackedDataInputPlus(new DataInputBuffer(s), L);
        String exc = "none";
        long before = allocated();
        try
        {
            byte[] v = BytesType.instance.read(ByteArrayAccessor.instance, in, (int) max);
            exc = "none(len=" + v.length + ")";
        }
        catch (IOException e)
        {
            exc = e.getClass().getSimpleName() + ":" + e.getMessage();
        }
        long after = allocated();
        r.alloc = after - before;
        r.exc = exc;
        r.bytesRead = in.getBytesRead();
        return r;
    }

    static Reading row(String row, long L, long V, long max, boolean wellFormed) throws IOException
    {
        List<Long> allocs = new ArrayList<>();
        List<Reading> rs = new ArrayList<>();
        for (int i = 1; i <= REPS; i++)
        {
            Reading r = one(row, L, V, max, wellFormed, true);
            rs.add(r);
            allocs.add(r.alloc);
            out(String.format("RESULT row=%s rep=%d L=%d V=%d max=%d vintLen=%d allocB=%d allocMiB=%.4f exc=%s bytesRead=%d",
                              row, i, L, V, max, r.vintLen, r.alloc, r.alloc / (double) MiB, r.exc, r.bytesRead));
        }
        Collections.sort(allocs);
        long med = allocs.get(REPS / 2);
        Reading m = rs.get(0);
        out(String.format("RESULT row=%s rep=median L=%d V=%d max=%d allocB=%d allocMiB=%.4f exc=%s bytesRead=%d",
                          row, L, V, max, med, med / (double) MiB, m.exc, m.bytesRead));
        Reading res = new Reading();
        res.alloc = med; res.exc = m.exc; res.bytesRead = m.bytesRead; res.vintLen = m.vintLen;
        // every repetition must agree on exception and bytesRead
        for (Reading r : rs)
        {
            assertEquals(row + " exc stable", m.exc, r.exc);
            assertEquals(row + " bytesRead stable", m.bytesRead, r.bytesRead);
        }
        return res;
    }

    static void checkEof(String row, Reading r, long V, long aLoMiB, long expBytesRead)
    {
        assertEquals(row + " vint is 4 bytes", 4, r.vintLen);
        assertTrue(row + " EOFException: " + r.exc, r.exc.startsWith("EOFException:"));
        assertTrue(row + " message ends out of V: " + r.exc, r.exc.endsWith("out of " + V));
        double a = r.alloc / (double) MiB;
        assertTrue(row + " A=" + a + " in [" + aLoMiB + "," + (aLoMiB + 1) + ")", a >= aLoMiB && a < aLoMiB + 1);
        if (r.bytesRead != expBytesRead)
            out("MECHANISM-MISS row=" + row + " bytesRead=" + r.bytesRead + " expected=" + expBytesRead);
    }

    @Test
    public void r1_L64_V16() throws IOException
    {
        checkEof("r1", row("r1", 64, 16 * MiB, 256 * MiB, false), 16 * MiB, 16, 64);
    }

    @Test
    public void r2_L1M_V16() throws IOException
    {
        checkEof("r2", row("r2", MiB, 16 * MiB, 256 * MiB, false), 16 * MiB, 16, 4 + R);
    }

    @Test
    public void r3_L16M_V64() throws IOException
    {
        checkEof("r3", row("r3", 16 * MiB, 64 * MiB, 256 * MiB, false), 64 * MiB, 64, 4 + R);
    }

    @Test
    public void r4_L64_V64() throws IOException
    {
        checkEof("r4", row("r4", 64, 64 * MiB, 256 * MiB, false), 64 * MiB, 64, 64);
    }

    @Test
    public void r5_control_max8M() throws IOException
    {
        Reading r = row("r5", MiB, 64 * MiB, 8 * MiB, false);
        assertTrue("r5 IOException corrupt length: " + r.exc,
                   r.exc.startsWith("IOException:Corrupt value length 67108864") && r.exc.contains("max_value_size"));
        assertTrue("r5 A < 1 MiB: " + r.alloc, r.alloc < MiB);
        if (r.bytesRead != 4)
            out("MECHANISM-MISS row=r5 bytesRead=" + r.bytesRead + " expected=4");
    }

    @Test
    public void r6_wellformed() throws IOException
    {
        long V = 16 * MiB;
        Reading r = row("r6", V + 4, V, 256 * MiB, true);
        assertTrue("r6 no exception: " + r.exc, r.exc.startsWith("none(len=" + V + ")"));
        double a = r.alloc / (double) MiB;
        assertTrue("r6 A in [16,17): " + a, a >= 16 && a < 17);
        if (r.bytesRead != V + 4)
            out("MECHANISM-MISS row=r6 bytesRead=" + r.bytesRead + " expected=" + (V + 4));
    }

    static volatile Object sink;

    /** Instrument check (known answer), run before run 1: a plain new byte[32 MiB] must read as A in [32, 33) MiB. */
    @Test
    public void instrumentKnownAnswer()
    {
        int n = 32 * (int) MiB;
        long before = allocated();
        sink = new byte[n];
        long after = allocated();
        double a = (after - before) / (double) MiB;
        out(String.format("INSTRUMENT known=new byte[%d] allocB=%d allocMiB=%.4f", n, after - before, a));
        sink = null;
        assertTrue("instrument A in [32,33): " + a, a >= 32 && a < 33);
    }

    @Test
    public void testLimitFires() throws IOException
    {
        byte[] b = new byte[200];
        TrackedDataInputPlus in = new TrackedDataInputPlus(new DataInputBuffer(b), 100);
        for (int i = 0; i < 100; i++)
            in.readByte();
        assertEquals(100, in.getBytesRead());
        String m1 = null;
        try { in.readByte(); fail("101st readByte should throw"); }
        catch (EOFException e) { m1 = e.getMessage(); }

        TrackedDataInputPlus in2 = new TrackedDataInputPlus(new DataInputBuffer(b), 100);
        String m2 = null;
        try { in2.readFully(new byte[150]); fail("readFully(150) should throw"); }
        catch (EOFException e) { m2 = e.getMessage(); }
        assertEquals(100, in2.getBytesRead());

        TrackedDataInputPlus in3 = new TrackedDataInputPlus(new DataInputBuffer(b), -1);
        for (int i = 0; i < 200; i++)
            in3.readByte();
        assertEquals(200, in3.getBytesRead());
        out("RESULT row=testLimitFires readByte101=EOF(" + m1 + ") readFully150=EOF(" + m2 + ") bytesRead2=" + in2.getBytesRead()
            + " unlimited200=" + in3.getBytesRead() + " PASS");
    }
}
