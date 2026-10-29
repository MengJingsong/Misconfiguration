/*
 * Stage-4 harness, unit tier (B2) of write_buffer_size-append-hint--autonomous. Not upstream.
 * Copy into test/unit/org/apache/cassandra/hints/ of a local copy (package-private HintsWriter, Session,
 * HintsWriteExecutor.WRITE_BUFFER_SIZE, HintsBuffer). Never into the repository's cassandra/cassandra-5.0.9/.
 *
 * B2b-B2e as audited (results §1): own direct aggregation buffer of N in {64 KiB, 256 KiB, 1 MiB} (the constant is not
 * settable; the test asserts WRITE_BUFFER_SIZE == 262144), hint size h in {1 KiB, 100 KiB, 300 KiB, 2 MiB}; the entry is an
 * opaque direct ByteBuffer of h + 12 bytes (HintsBuffer.ENTRY_OVERHEAD_SIZE, the production shape: flushInternal passes
 * direct slices of the slab) appended M = min(20000, ceil(256 MiB / (h + 12))) times (audit amendment: B2c's "2 GiB / hint
 * size capped at 20000" gives 2 GiB for 2 MiB hints, not the "few hundred MiB" it names); every cell 3 times; the file
 * is deleted after each cell. Writer: a counting subclass of HintsWriter (own open(), same steps as HintsWriter.create).
 * Observables: after each append buffer.position(), the file length, Session.getBytesWritten(); per cell the channel
 * writes (count, sizes), the file after close (length and a CRC32 over the bytes after the header against the expected
 * header + M copies), and the JVM direct pool (BufferPoolMXBean "direct") at three points: P0 after the entry buffer and
 * the writer exist, P1 after the aggregation buffer is allocated, P2 after the last append and close (buffer still held);
 * heap used after System.gc() before and after. A model of Session.append (HintsWriter.java:200-222) is compared with
 * every append. Positive control: HintsBuffer.create(32 MiB) and create(64 MiB) change the direct pool by exactly their
 * capacity; the HintsBuffer allocate guard at capacity/2 is also checked.
 * Output: "STAGE4 append/case/check/info" lines, also to -Dstage4.out.
 */
package org.apache.cassandra.hints;

import java.io.FileWriter;
import java.io.IOException;
import java.io.InputStream;
import java.io.PrintWriter;
import java.lang.management.BufferPoolMXBean;
import java.lang.management.ManagementFactory;
import java.nio.ByteBuffer;
import java.nio.channels.FileChannel;
import java.nio.file.Files;
import java.nio.file.StandardOpenOption;
import java.util.ArrayList;
import java.util.List;
import java.util.UUID;
import java.util.zip.CRC32;

import org.junit.AfterClass;
import org.junit.Assert;
import org.junit.BeforeClass;
import org.junit.Test;

import org.apache.cassandra.SchemaLoader;
import org.apache.cassandra.io.util.DataOutputBuffer;
import org.apache.cassandra.io.util.File;
import org.apache.cassandra.io.util.FileUtils;
import org.apache.cassandra.utils.NativeLibrary;

public class WriteBufferProbeTest
{
    static final int KIB = 1024, MIB = 1 << 20;
    static final int[] NS = { 64 * KIB, 256 * KIB, MIB };
    static final int[] HS = { KIB, 100 * KIB, 300 * KIB, 2 * MIB };
    static final int OVERHEAD = HintsBuffer.ENTRY_OVERHEAD_SIZE;
    static final BufferPoolMXBean DIRECT = ManagementFactory.getPlatformMXBeans(BufferPoolMXBean.class).stream()
                                                           .filter(b -> b.getName().equals("direct")).findFirst().get();

    static PrintWriter out;
    static File dir;
    static int mismatches = 0, checks = 0, errors = 0;

    static class CountingWriter extends HintsWriter
    {
        final List<Integer> writes = new ArrayList<>();      // writeBuffer calls that wrote bytes
        int zeroCalls = 0;                                    // writeBuffer calls with an empty buffer (the flush at HintsWriter.java:205-209 of an empty aggregation buffer)

        CountingWriter(File d, HintsDescriptor desc, File f, FileChannel ch, int fd)
        {
            super(d, desc, f, ch, fd, new CRC32());
        }

        @Override
        protected void writeBuffer(ByteBuffer bb) throws IOException
        {
            if (bb.remaining() == 0)
                zeroCalls++;
            else
                writes.add(bb.remaining());
            super.writeBuffer(bb);
        }
    }

    static CountingWriter open() throws IOException
    {
        HintsDescriptor desc = new HintsDescriptor(UUID.randomUUID(), System.currentTimeMillis());
        File file = desc.file(dir);
        FileChannel ch = FileChannel.open(file.toPath(), StandardOpenOption.WRITE, StandardOpenOption.CREATE_NEW);
        int fd = NativeLibrary.getfd(ch);
        try (DataOutputBuffer dob = DataOutputBuffer.scratchBuffer.get())
        {
            desc.serialize(dob);
            ch.write(dob.unsafeGetBufferAndFlip());
            desc.hintsFileSize(ch.position());
        }
        return new CountingWriter(dir, desc, file, ch, fd);
    }

    @BeforeClass
    public static void setUp() throws Exception
    {
        SchemaLoader.prepareServer();
        String o = System.getProperty("stage4.out");
        out = o == null ? null : new PrintWriter(new FileWriter(o, true), true);
        dir = new File(Files.createTempDirectory("stage4-wbs2"));
        say("STAGE4 info WRITE_BUFFER_SIZE=" + HintsWriteExecutor.WRITE_BUFFER_SIZE + " ENTRY_OVERHEAD_SIZE=" + OVERHEAD
            + " maxMemory=" + Runtime.getRuntime().maxMemory() + " dir=" + dir.path());
        check("constant_WRITE_BUFFER_SIZE", 262144, HintsWriteExecutor.WRITE_BUFFER_SIZE, HintsWriteExecutor.WRITE_BUFFER_SIZE == 262144);
    }

    @AfterClass
    public static void tearDown()
    {
        FileUtils.deleteRecursive(dir);
        say("STAGE4 info tmpdir deleted=" + !dir.exists());
        say("STAGE4 summary checks=" + checks + " mismatches=" + mismatches + " errors=" + errors);
        if (out != null)
            out.close();
    }

    static void say(String s)
    {
        System.out.println(s);
        if (out != null)
            out.println(s);
    }

    static boolean check(String name, Object expected, Object actual, boolean ok)
    {
        checks++;
        if (!ok)
            mismatches++;
        say("STAGE4 check " + name + " expected=" + expected + " actual=" + actual + " " + (ok ? "ok" : "MISMATCH"));
        return ok;
    }

    static ByteBuffer entryOf(int e, int h)
    {
        ByteBuffer b = ByteBuffer.allocateDirect(e);
        for (int i = 0; i < e; i++)
            b.put(i, (byte) (i * 31 + h));
        return b;
    }

    static void settle() throws InterruptedException
    {
        System.gc();
        Thread.sleep(150);
        System.gc();
        Thread.sleep(150);
    }

    static long heapUsed()
    {
        Runtime r = Runtime.getRuntime();
        return r.totalMemory() - r.freeMemory();
    }

    static void cell(int n, int h, int rep) throws Exception
    {
        int e = h + OVERHEAD;
        boolean fits = e <= n;
        int m = (int) Math.min(20000, Math.ceil(256.0 * MIB / e));
        String tag = "N=" + n + " h=" + h + " rep=" + rep;
        String c = tag.replace(' ', '_');
        settle();
        long heap0 = heapUsed();
        ByteBuffer entry = entryOf(e, h);
        CountingWriter w = open();
        File file = w.getFile();
        long header = file.length();
        long p0 = DIRECT.getMemoryUsed(), c0 = DIRECT.getCount();
        ByteBuffer agg = ByteBuffer.allocateDirect(n);
        long p1 = DIRECT.getMemoryUsed(), c1 = DIRECT.getCount();
        long mpos = 0, mfile = header, maxPos = 0, prevLen = header, bytesWritten, fileAfterClose, p2, c2, appendsLogged = 0;
        int mWrites = 0;
        long mBytesW = 0, modelBad = 0;
        try
        {
            try (HintsWriter.Session s = w.newSession(agg))
            {
                for (int i = 0; i < m; i++)
                {
                    s.append(entry.duplicate());
                    long pos = agg.position(), len = file.length();
                    if (e > n - mpos)
                    {
                        if (mpos > 0) { mfile += mpos; mWrites++; mBytesW += mpos; }
                        mpos = 0;
                    }
                    if (e <= n - mpos)
                        mpos += e;
                    else
                    {
                        mfile += e; mWrites++; mBytesW += e;
                    }
                    if (pos != mpos || len != mfile)
                        modelBad++;
                    maxPos = Math.max(maxPos, pos);
                    if ((i < 3 || len != prevLen) && appendsLogged < 40)
                    {
                        appendsLogged++;
                        say("STAGE4 append " + tag + " i=" + i + " bytesWritten=" + s.getBytesWritten() + " fileLen=" + len + " bufPos=" + pos);
                    }
                    prevLen = len;
                }
                bytesWritten = s.getBytesWritten();
            }
            fileAfterClose = file.length();
            p2 = DIRECT.getMemoryUsed();
            c2 = DIRECT.getCount();
        }
        finally
        {
            w.close();
        }
        if (mpos > 0) { mWrites++; mBytesW += mpos; }
        // CRC over the bytes after the header against header-less expected (m copies of the entry)
        CRC32 got = new CRC32(), exp = new CRC32();
        byte[] ev = new byte[e];
        entry.duplicate().get(ev);
        for (int i = 0; i < m; i++)
            exp.update(ev);
        try (InputStream in = Files.newInputStream(file.toPath()))
        {
            in.skip(header);
            byte[] buf = new byte[1 << 16];
            int r;
            while ((r = in.read(buf)) > 0)
                got.update(buf, 0, r);
        }
        long sumW = 0;
        int maxWrite = 0;
        for (int x : w.writes) { sumW += x; maxWrite = Math.max(maxWrite, x); }
        file.tryDelete();
        long heap1 = heapUsed();
        say("STAGE4 case " + tag + " entry=" + e + " m=" + m + " total=" + ((long) m * e) + " header=" + header + " bytesWritten=" + bytesWritten
            + " fileAfterClose=" + fileAfterClose + " channelWrites=" + w.writes.size() + " zeroLengthWriteCalls=" + w.zeroCalls + " channelWriteBytes=" + sumW + " maxWrite=" + maxWrite
            + " maxBufPos=" + maxPos + " directP0=" + p0 + " directP1=" + p1 + " directP2=" + p2 + " directCountDeltaAlloc=" + (c1 - c0)
            + " directCountDeltaRun=" + (c2 - c1) + " heap0=" + heap0 + " heap1=" + heap1);
        check(c + "_bytesWritten_and_file_length", header + (long) m * e, fileAfterClose, bytesWritten == (long) m * e && fileAfterClose == header + (long) m * e);
        check(c + "_file_bytes_CRC_equal_expected(every_byte_arrives)", Long.toHexString(exp.getValue()), Long.toHexString(got.getValue()), exp.getValue() == got.getValue());
        check(c + "_model_each_append", "0 differences", modelBad + " differences", modelBad == 0);
        check(c + "_bufpos_le_N", "<=" + n, maxPos, maxPos <= n);
        check(c + "_channel_writes_equal_model", mWrites + " writes, " + mBytesW + " B", w.writes.size() + " writes, " + sumW + " B",
              w.writes.size() == mWrites && sumW == mBytesW);
        if (!fits)
            check(c + "_one_channel_write_per_hint_(each_E_bytes)", m + " x " + e, w.writes.size() + " writes, max " + maxWrite,
                  w.writes.size() == m && w.writes.stream().allMatch(x -> x == e));
        else
        {
            int per = n / e;
            check(c + "_writes_about_total/N", "~" + (long) Math.ceil((double) m / per) + " buffer writes, each <= N", w.writes.size() + " writes, max " + maxWrite,
                  maxWrite <= n && Math.abs(w.writes.size() - Math.ceil((double) m / per)) <= 1);
        }
        check(c + "_direct_pool_delta_P1-P0_=_N", n, p1 - p0, p1 - p0 == n);
        check(c + "_direct_pool_delta_P2-P1_<=_0(no_growth_with_load/hint_size;_a_negative_value_is_an_unrelated_buffer_released_by_GC)", "<=0", p2 - p1, p2 - p1 <= 0);
        check(c + "_direct_count_P1-P0_=_1_and_P2-P1_<=_0", "1 / <=0", (c1 - c0) + " / " + (c2 - c1), c1 - c0 == 1 && c2 - c1 <= 0);
        entry = null;
        agg = null;
    }

    static void control() throws Exception
    {
        // positive control: the slab (HintsBuffer.create -> ByteBuffer.allocateDirect(slabSize), HintsBuffer.java:77) moves the pool by its capacity
        for (int mib : new int[]{ 32, 64 })
        {
            settle();
            long a = DIRECT.getMemoryUsed(), ca = DIRECT.getCount();
            HintsBuffer b = HintsBuffer.create(mib * MIB);
            long z = DIRECT.getMemoryUsed(), cz = DIRECT.getCount();
            check("control_HintsBuffer.create(" + mib + "MiB)_direct_delta", (long) mib * MIB, z - a, z - a == (long) mib * MIB);
            check("control_HintsBuffer.create(" + mib + "MiB)_count_delta", 1, cz - ca, cz - ca == 1);
            // the allocate guard (HintsBuffer.java:150-157): hint + 12 > capacity/2 throws
            long half = (long) mib * MIB / 2;
            String edge, over;
            try (HintsBuffer.Allocation x = b.allocate((int) (half - OVERHEAD))) { edge = "allocated"; } catch (Throwable t) { edge = t.toString(); }
            try (HintsBuffer.Allocation x = b.allocate((int) (half - OVERHEAD + 1))) { over = "allocated"; } catch (IllegalArgumentException t) { over = "refused"; }
            check("control_slab_" + mib + "MiB_hint_at_capacity/2_admitted", "allocated", edge, edge.equals("allocated"));
            check("control_slab_" + mib + "MiB_hint_over_capacity/2_refused", "refused", over, over.equals("refused"));
            b.free();
        }
    }

    @Test
    public void probe() throws Exception
    {
        for (int rep = 1; rep <= 3; rep++)
            for (int n : NS)
                for (int h : HS)
                {
                    try
                    {
                        cell(n, h, rep);
                    }
                    catch (Throwable t)
                    {
                        errors++;
                        say("STAGE4 error cell N=" + n + " h=" + h + " " + t);
                        t.printStackTrace(System.out);
                    }
                }
        try
        {
            control();
        }
        catch (Throwable t)
        {
            errors++;
            say("STAGE4 error control " + t);
            t.printStackTrace(System.out);
        }
        Assert.assertEquals("instrument or set-up errors (see STAGE4 error lines)", 0, errors);
    }
}
