/*
 * Stage-4 harness, unit tier (B2) of hints_write_buffer_size-append-hint_remaining--autonomous. Not upstream.
 * Copy into test/unit/org/apache/cassandra/hints/ of a local copy (package-private HintsWriter, Session,
 * HintsWriteExecutor.WRITE_BUFFER_SIZE, HintsBuffer). Never into the repository's cassandra/cassandra-5.0.9/.
 *
 * B2b-B2e as audited (results §1): the aggregation buffer N in {64 KiB, 256 KiB, 1 MiB} is passed to
 * writer.newSession(ByteBuffer.allocateDirect(N)); hint size H in {1, 100, 255, 300 KiB, 2 MiB}; the entry is an opaque
 * direct ByteBuffer of H + 12 bytes (HintsBuffer.ENTRY_OVERHEAD_SIZE) filled with a pattern, the production shape
 * (HintsWriteExecutor.flushInternal passes direct slices). K = ceil(2.5 N / (H + 12)), at least 3, when H + 12 <= N,
 * else 3 (B2c). The writer is a counting subclass of HintsWriter (own open(), same steps as HintsWriter.create) so that
 * every channel write is seen.
 * Per append: Session.getBytesWritten(), the file length, the aggregation buffer's position. Per cell: the first
 * file-length jump, the number and sizes of channel writes, the file length after close, a byte-for-byte comparison of
 * the file against header + K copies of the entry. A model of HintsWriter.java:200-222 (written from B2f's prediction:
 * flush when the entry does not fit, copy when it fits, write through when it cannot fit) is compared with every append.
 * Positive control (B2h): flushInternal's loop (HintsWriteExecutor.java:245-248) with maxHintsFileSize = 1 MiB, for every
 * N and H: it must stop at the same entry count for every N. Second control: the same sequence with a heap aggregation
 * buffer of 256 KiB gives the same (file length, position) sequence.
 * Output: "STAGE4 append ..." per append, "STAGE4 case ..." per cell, "STAGE4 check <name> expected=... actual=...
 * ok|MISMATCH" per check; also to -Dstage4.out. Mismatches are recorded and the run goes on; the test fails only on an
 * instrument or set-up error (the readings are judged in the results file).
 */
package org.apache.cassandra.hints;

import java.io.FileWriter;
import java.io.IOException;
import java.io.PrintWriter;
import java.nio.ByteBuffer;
import java.nio.channels.FileChannel;
import java.nio.file.Files;
import java.nio.file.StandardOpenOption;
import java.util.ArrayList;
import java.util.Arrays;
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
    static final int[] HS = { KIB, 100 * KIB, 255 * KIB, 300 * KIB, 2 * MIB };
    static final int OVERHEAD = HintsBuffer.ENTRY_OVERHEAD_SIZE;

    static PrintWriter out;
    static File dir;
    static int mismatches = 0, checks = 0, errors = 0;

    /** HintsWriter with every writeBuffer call recorded (size of the buffer handed to the channel) */
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

    /** same steps as HintsWriter.create (HintsWriter.java:67-91) for the uncompressed, unencrypted writer */
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
        dir = new File(Files.createTempDirectory("stage4-hwb"));
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

    /** one cell: N, H, rep; heapAgg selects a heap aggregation buffer (B2h second control). Returns the (fileLen, pos) sequence. */
    static long[] cell(int n, int h, int rep, boolean heapAgg) throws IOException
    {
        int e = h + OVERHEAD;
        boolean fits = e <= n;
        int k = fits ? Math.max(3, (int) Math.ceil(2.5 * n / e)) : 3;
        String tag = (heapAgg ? "heapagg " : "") + "N=" + n + " H=" + h + " rep=" + rep;
        String c = tag.replace(' ', '_');
        ByteBuffer entry = entryOf(e, h);
        ByteBuffer agg = heapAgg ? ByteBuffer.allocate(n) : ByteBuffer.allocateDirect(n);
        long[] seq = new long[2 * k];
        long header, bytesWritten, fileAfterClose;
        File file;
        CountingWriter w = open();
        long mpos = 0, mfile, maxPos = 0, firstJumpIdx = -1, firstJumpBytes = -1, prevLen;
        boolean modelOk = true, throughOk = true;
        int mWrites = 0;
        long mBytesW = 0;
        try
        {
            file = w.getFile();
            header = file.length();
            mfile = header;
            prevLen = header;
            try (HintsWriter.Session s = w.newSession(agg))
            {
                for (int i = 0; i < k; i++)
                {
                    s.append(entry.duplicate());
                    long pos = agg.position(), len = file.length();
                    // model of Session.append (HintsWriter.java:200-222)
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
                    modelOk &= (pos == mpos && len == mfile);
                    maxPos = Math.max(maxPos, pos);
                    if (!fits)
                        throughOk &= (len - prevLen == e && pos == 0);
                    if (firstJumpIdx < 0 && len > header)
                    {
                        firstJumpIdx = i;
                        firstJumpBytes = len - header;
                    }
                    prevLen = len;
                    seq[2 * i] = len; seq[2 * i + 1] = pos;
                    say("STAGE4 append " + tag + " i=" + i + " bytesWritten=" + s.getBytesWritten() + " fileLen=" + len + " bufPos=" + pos);
                }
                bytesWritten = s.getBytesWritten();
            }
            fileAfterClose = file.length();
        }
        finally
        {
            w.close();
        }
        if (mpos > 0) { mWrites++; mBytesW += mpos; }          // close() flushes the remainder
        // byte-for-byte: header + K copies of the entry
        byte[] all = Files.readAllBytes(file.toPath());
        boolean bytesOk = all.length == header + (long) k * e;
        byte[] ev = new byte[e];
        entry.duplicate().get(ev);
        for (int i = 0; bytesOk && i < k; i++)
            bytesOk &= Arrays.equals(Arrays.copyOfRange(all, (int) header + i * e, (int) header + (i + 1) * e), ev);
        long sumW = 0;
        for (int x : w.writes) sumW += x;
        int maxWrite = w.writes.stream().mapToInt(x -> x).max().orElse(0);
        say("STAGE4 case " + tag + " entry=" + e + " k=" + k + " header=" + header + " bytesWritten=" + bytesWritten
            + " fileAfterClose=" + fileAfterClose + " channelWrites=" + w.writes.size() + " zeroLengthWriteCalls=" + w.zeroCalls + " channelWriteBytes=" + sumW
            + " maxWrite=" + maxWrite + " maxBufPos=" + maxPos + " firstJumpIdx=" + firstJumpIdx + " firstJumpBytes=" + firstJumpBytes
            + " writes=" + w.writes.subList(0, Math.min(8, w.writes.size())));
        check(c + "_model_each_append(flush points, position, file length)", "as B2f", modelOk ? "as B2f" : "differs", modelOk);
        check(c + "_bufpos_le_N", "<=" + n, maxPos, maxPos <= n);
        if (fits)
        {
            long expJump = (long) (n / e) * e;
            check(c + "_first_jump_after_N", "idx " + (n / e) + ", " + expJump + " B (<= N)", "idx " + firstJumpIdx + ", " + firstJumpBytes + " B",
                  firstJumpIdx == n / e && firstJumpBytes == expJump && firstJumpBytes <= n);
            check(c + "_every_channel_write_<=_N", "<=" + n, maxWrite, maxWrite <= n);
        }
        else
        {
            check(c + "_oversized_written_through(+E each append, buffer unchanged at 0)", "+" + e + " each, pos 0", throughOk ? "as expected" : "differs", throughOk);
            check(c + "_channel_writes_(one per entry, each E bytes)", k + " x " + e, w.writes.size() + " writes, max " + maxWrite,
                  w.writes.size() == k && w.writes.stream().allMatch(x -> x == e));
        }
        check(c + "_channel_writes_equal_model", mWrites + " writes, " + mBytesW + " B", w.writes.size() + " writes, " + sumW + " B",
              w.writes.size() == mWrites && sumW == mBytesW);
        check(c + "_bytesWritten", (long) k * e, bytesWritten, bytesWritten == (long) k * e);
        check(c + "_fileLen_after_close_=_header+K*E(nothing lost or refused)", header + (long) k * e, fileAfterClose, fileAfterClose == header + (long) k * e);
        check(c + "_file_bytes_identical_to_header+K_entries", "identical", bytesOk ? "identical" : "differs", bytesOk);
        if (!fits)
            check(c + "_through_check", "ok", throughOk, throughOk);
        return seq;
    }

    /** B2h positive control: flushInternal's loop with maxHintsFileSize = 1 MiB */
    static int fileSizeStop(int n, int h) throws IOException
    {
        int e = h + OVERHEAD;
        long max = MIB;
        ByteBuffer entry = entryOf(e, h);
        ByteBuffer agg = ByteBuffer.allocateDirect(n);
        int appended = 0;
        long posAtStop;
        CountingWriter w = open();
        try
        {
            try (HintsWriter.Session s = w.newSession(agg))
            {
                for (int i = 0; i < 100000; i++)         // an iterator with far more entries than the limit needs
                {
                    s.append(entry.duplicate());
                    appended++;
                    if (s.position() >= max)             // HintsWriteExecutor.java:247
                        break;
                }
                posAtStop = s.position();
            }
        }
        finally
        {
            w.close();
        }
        long header = w.getFile().length() - 0;           // after close the file holds header + all appended
        say("STAGE4 info filesizestop N=" + n + " H=" + h + " appended=" + appended + " positionAtStop=" + posAtStop + " fileAfterClose=" + header);
        return appended;
    }

    static void guarded(String what, IORun r)
    {
        try
        {
            r.run();
        }
        catch (Throwable t)
        {
            errors++;
            say("STAGE4 error " + what + " " + t);
            t.printStackTrace(System.out);
        }
    }

    interface IORun { void run() throws IOException; }

    @Test
    public void probe()
    {
        for (int rep = 1; rep <= 2; rep++)
        {
            final int r = rep;
            for (int n : NS)
                for (int h : HS)
                    guarded("cell " + n + " " + h, () -> cell(n, h, r, false));
        }
        // heap aggregation buffer, N = 256 KiB: same sequence as the direct one (B2h)
        for (int h : HS)
            guarded("heapagg " + h, () -> {
                long[] d = cell(256 * KIB, h, 9, false);
                long[] p = cell(256 * KIB, h, 9, true);
                check("heapagg_N=262144_H=" + h + "_same_(fileLen,pos)_sequence_as_direct", "equal", Arrays.equals(d, p) ? "equal" : "differs", Arrays.equals(d, p));
            });
        // positive control: the file-size stop binds and does not depend on N
        for (int h : HS)
        {
            final int hh = h;
            int[] stops = new int[NS.length];
            for (int i = 0; i < NS.length; i++)
            {
                final int ii = i;
                guarded("stop " + NS[i] + " " + h, () -> stops[ii] = fileSizeStop(NS[ii], hh));
            }
            int e = h + OVERHEAD;
            // header is 42 B in this build; read it from the first stop's info line is not needed: smallest k with header + k*E >= 1 MiB
            int expect = (int) Math.ceil((MIB - 42.0) / e);
            check("filesizestop_H=" + h + "_stops_at_1MiB,_same_for_every_N", "all = " + expect + " (header 42 B)", Arrays.toString(stops),
                  stops[0] == expect && stops[1] == expect && stops[2] == expect);
        }
        Assert.assertEquals("instrument or set-up errors (see STAGE4 error lines)", 0, errors);
    }
}
