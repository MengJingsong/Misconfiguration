/*
 * Stage-4 harness, unit tier (B2) of hints-CompressedHintsWriter-compressionBuffer-capacity--autonomous (case file
 * amended 2026-10-25, sha256 recorded in the results file). Not upstream. Package org.apache.cassandra.hints because
 * HintsWriter.create, newSession, Session.append and HintsBuffer.create/allocate are package-private. Copied into a local
 * tree's test/unit/org/apache/cassandra/hints/ by unit-run.sh.
 *
 * Expected capacity of a compression buffer (LZ4, B2f and the case file's A3 note): exp(S) = 4 + (S + S/255 + 16) + 8
 * (integer division), where S is the byte count the writer compresses in one writeBuffer call.
 *
 * Checks (each prints "STAGE4 check <name> ok|MISMATCH <detail>"; a mismatch is recorded and the test goes on):
 *   lz4-bound        net.jpountz maxCompressedLength(n) == n + n/255 + 16 and initialCompressedBufferLength(n) == 4 + that
 *   asc-<S>          fresh LZ4 writer, one record of S bytes (100 B, 200 KiB, 256 KiB, 1 MiB, 4 MiB, 16 MiB): capacity == exp(S)
 *                    (exactly; the B2f tolerance is +/- 64 B)
 *   seq              one writer, S ascending 100 B, 1 MiB, 16 MiB then descending 1 MiB, 100 B, 200 KiB: capacity never shrinks,
 *                    ends at exp(16 MiB) (B2g "shrinks" row)
 *   filesize-<MiB>   max_hints_file_size 1 MiB and 128 MiB (set in the raw config): same capacity for 4 MiB and 16 MiB
 *   n-<N>            N = 1, 4, 16 writers holding a 4 MiB record each: direct pool MemoryUsed grows by N x exp(4 MiB) within 10 %
 *   uncompressed     HintsWriter (no compression): class is not CompressedHintsWriter, has no compressionBuffer field,
 *                    pool unchanged (+/- 64 KiB) after a 4 MiB record
 *   compressible     4 MiB of zeros: capacity == exp(4 MiB) (sized by the bound, not the result)
 *   deflate          DeflateCompressor writer: buffer on heap (isDirect false); LZ4 buffer isDirect true (pool delta printed as information)
 *   cap-boundary     HintsBuffer.create(32 MiB): allocate(16,777,204) accepted; allocate(16,777,205) and allocate(17 MiB) throw
 *                    IllegalArgumentException naming 16777216; the writer takes a 16 MiB record (asc-16MiB)
 *   cap-formula      max(2 x max_mutation_size, 32 MiB) / 2 for max_mutation_size 1, 4, 8, 16, 32, 64 MiB = 16, 16, 16, 16, 32, 64 MiB
 *   slab-control     positive control: pool MemoryUsed around HintsBuffer.create(C) rises by exactly C for C = 32 MiB and 128 MiB
 *                    (the slab size from max_mutation_size 16 / 64 MiB), Count +1; free() falls by C
 * Output on stdout and appended to the file named by -Dstage4.out. Working files under -Dstage4.dir.
 */
package org.apache.cassandra.hints;

import java.io.FileWriter;
import java.io.IOException;
import java.io.PrintWriter;
import java.lang.management.BufferPoolMXBean;
import java.lang.management.ManagementFactory;
import java.lang.reflect.Field;
import java.nio.ByteBuffer;
import java.util.ArrayList;
import java.util.List;
import java.util.Random;
import java.util.UUID;

import com.google.common.collect.ImmutableMap;
import org.junit.AfterClass;
import org.junit.BeforeClass;
import org.junit.Test;

import net.jpountz.lz4.LZ4Factory;
import org.apache.cassandra.config.DataStorageSpec;
import org.apache.cassandra.config.DatabaseDescriptor;
import org.apache.cassandra.io.util.File;

import static org.junit.Assert.assertEquals;

public class CompressedHintsWriterCapProbeTest
{
    static final int KIB = 1 << 10, MIB = 1 << 20;
    static final int AGG = HintsWriteExecutor.WRITE_BUFFER_SIZE;      // 256 KiB
    static PrintWriter file;
    static int checks, mismatches;
    static File dir;

    @BeforeClass
    public static void setUp() throws IOException
    {
        DatabaseDescriptor.daemonInitialization();
        String f = System.getProperty("stage4.out");
        if (f != null)
            file = new PrintWriter(new FileWriter(f, true), true);
        String d = System.getProperty("stage4.dir", System.getProperty("java.io.tmpdir") + "/stage4-hw");
        dir = new File(d);
        dir.tryCreateDirectories();
        out("STAGE4 start java=" + System.getProperty("java.version") + " maxMemory=" + Runtime.getRuntime().maxMemory()
            + " AGG=" + AGG + " ENTRY_OVERHEAD_SIZE=" + HintsBuffer.ENTRY_OVERHEAD_SIZE
            + " getMaxMutationSize()=" + DatabaseDescriptor.getMaxMutationSize() + " (test yaml; informational)"
            + " maxHintsFileSize=" + DatabaseDescriptor.getMaxHintsFileSize());
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

    static long exp(long s)
    {
        return 4 + (s + s / 255 + 16) + 8;
    }

    static BufferPoolMXBean direct()
    {
        for (BufferPoolMXBean b : ManagementFactory.getPlatformMXBeans(BufferPoolMXBean.class))
            if (b.getName().equals("direct"))
                return b;
        throw new IllegalStateException("no direct pool");
    }

    static long[] settled() throws InterruptedException
    {
        for (int i = 0; i < 2; i++)
        {
            System.gc();
            Thread.sleep(300);
        }
        return new long[]{ direct().getMemoryUsed(), direct().getCount() };
    }

    static ByteBuffer record(int size, boolean zeros)
    {
        ByteBuffer b = ByteBuffer.allocateDirect(size);
        if (!zeros)
        {
            byte[] r = new byte[Math.min(size, MIB)];
            new Random(7).nextBytes(r);
            for (int off = 0; off < size; off += r.length)
                b.put(r, 0, Math.min(r.length, size - off));
        }
        b.clear();
        return b;
    }

    static HintsDescriptor descriptor(String compressor)
    {
        if (compressor == null)
            return new HintsDescriptor(UUID.randomUUID(), System.currentTimeMillis());
        return new HintsDescriptor(UUID.randomUUID(), System.currentTimeMillis(),
                                   ImmutableMap.of(HintsDescriptor.COMPRESSION,
                                                   ImmutableMap.of("class_name", compressor, "parameters", ImmutableMap.of())));
    }

    static ByteBuffer bufferOf(HintsWriter w) throws Exception
    {
        Field f = CompressedHintsWriter.class.getDeclaredField("compressionBuffer");
        f.setAccessible(true);
        return (ByteBuffer) f.get(w);
    }

    static long capOf(HintsWriter w) throws Exception
    {
        ByteBuffer b = bufferOf(w);
        return b == null ? -1 : b.capacity();
    }

    /** one session on w: append one record of the given content, close the session (flushes the aggregation buffer) */
    static void put(HintsWriter w, ByteBuffer agg, ByteBuffer rec) throws IOException
    {
        try (HintsWriter.Session s = w.newSession(agg))
        {
            s.append(rec.duplicate());
        }
    }

    @Test
    public void probe() throws Exception
    {
        ByteBuffer agg = ByteBuffer.allocateDirect(AGG);

        // lz4-bound: the arithmetic itself
        {
            boolean ok = true;
            StringBuilder d = new StringBuilder();
            HintsWriter w = HintsWriter.create(dir, descriptor("LZ4Compressor"));
            org.apache.cassandra.io.compress.ICompressor c = ((CompressedHintsWriter) w).getCompressor();
            for (int n : new int[]{ 0, 100, 200 * KIB, AGG, MIB, 4 * MIB, 8 * MIB, 16 * MIB })
            {
                int bound = LZ4Factory.fastestInstance().fastCompressor().maxCompressedLength(n);
                long formula = n + n / 255 + 16;
                int init = c.initialCompressedBufferLength(n);
                ok &= bound == formula && init == 4 + formula;
                d.append(String.format("n=%d bound=%d formula=%d init=%d exp=%d; ", n, bound, formula, init, exp(n)));
            }
            check("lz4-bound", ok, d.toString());
            w.close();
        }

        // asc-<S>, compressible
        int[] sizes = { 100, 200 * KIB, AGG, MIB, 4 * MIB, 16 * MIB };
        for (int s : sizes)
        {
            ByteBuffer rec = record(s, false);
            HintsWriter w = HintsWriter.create(dir, descriptor("LZ4Compressor"));
            put(w, agg, rec);
            long cap = capOf(w);
            check("asc-" + s, cap == exp(s), "S=" + s + " capacity=" + cap + " exp=" + exp(s) + " diff=" + (cap - exp(s))
                                              + " isDirect=" + bufferOf(w).isDirect());
            w.close();
        }

        // seq
        {
            HintsWriter w = HintsWriter.create(dir, descriptor("LZ4Compressor"));
            int[] seq = { 100, MIB, 16 * MIB, MIB, 100, 200 * KIB };
            long prev = -1;
            boolean mono = true;
            StringBuilder d = new StringBuilder();
            for (int s : seq)
            {
                put(w, agg, record(s, false));
                long cap = capOf(w);
                mono &= cap >= prev;
                prev = cap;
                d.append("S=" + s + ":" + cap + " ");
            }
            check("seq", mono && prev == exp(16 * MIB), d + "final=" + prev + " exp(16MiB)=" + exp(16 * MIB));
            w.close();
        }

        // filesize
        {
            long[] caps = new long[4];
            int k = 0;
            for (String fs : new String[]{ "1MiB", "128MiB" })
            {
                DatabaseDescriptor.getRawConfig().max_hints_file_size = new DataStorageSpec.IntMebibytesBound(fs);
                for (int s : new int[]{ 4 * MIB, 16 * MIB })
                {
                    HintsWriter w = HintsWriter.create(dir, descriptor("LZ4Compressor"));
                    put(w, agg, record(s, false));
                    caps[k++] = capOf(w);
                    w.close();
                }
            }
            check("filesize", caps[0] == caps[2] && caps[1] == caps[3] && caps[0] == exp(4 * MIB) && caps[1] == exp(16 * MIB),
                  "max_hints_file_size 1MiB: " + caps[0] + "," + caps[1] + "; 128MiB: " + caps[2] + "," + caps[3]
                  + " (getMaxHintsFileSize now " + DatabaseDescriptor.getMaxHintsFileSize() + ")");
            DatabaseDescriptor.getRawConfig().max_hints_file_size = new DataStorageSpec.IntMebibytesBound("128MiB");
        }

        // n-<N>
        {
            ByteBuffer rec = record(4 * MIB, false);
            for (int n : new int[]{ 1, 4, 16 })
            {
                long[] before = settled();
                List<HintsWriter> ws = new ArrayList<>();
                for (int i = 0; i < n; i++)
                {
                    HintsWriter w = HintsWriter.create(dir, descriptor("LZ4Compressor"));
                    put(w, agg, rec);
                    ws.add(w);
                }
                long[] after = settled();
                long delta = after[0] - before[0], want = n * exp(4 * MIB);
                check("n-" + n, Math.abs(delta - want) <= 0.10 * want,
                      "N=" + n + " pool delta=" + delta + " want N x exp(4MiB)=" + want + " ratio=" + String.format("%.4f", (double) delta / want)
                      + " count delta=" + (after[1] - before[1]));
                for (HintsWriter w : ws)
                    w.close();
                ws.clear();
            }
        }

        // uncompressed
        {
            ByteBuffer rec = record(4 * MIB, false);
            long[] before = settled();
            HintsWriter w = HintsWriter.create(dir, descriptor(null));
            put(w, agg, rec);
            long[] after = settled();
            boolean noField;
            try
            {
                w.getClass().getDeclaredField("compressionBuffer");
                noField = false;
            }
            catch (NoSuchFieldException e)
            {
                noField = true;
            }
            long delta = after[0] - before[0];
            check("uncompressed", !(w instanceof CompressedHintsWriter) && noField && Math.abs(delta) <= 64 * KIB,
                  "class=" + w.getClass().getSimpleName() + " noCompressionBufferField=" + noField + " pool delta=" + delta);
            w.close();
        }

        // compressible
        {
            HintsWriter w = HintsWriter.create(dir, descriptor("LZ4Compressor"));
            put(w, agg, record(4 * MIB, true));
            long cap = capOf(w);
            check("compressible", cap == exp(4 * MIB), "zeros 4 MiB capacity=" + cap + " exp=" + exp(4 * MIB));
            w.close();
        }

        // deflate
        {
            ByteBuffer rec = record(4 * MIB, false);
            long[] before = settled();
            HintsWriter w = HintsWriter.create(dir, descriptor("DeflateCompressor"));
            put(w, agg, rec);
            long[] after = settled();
            ByteBuffer b = bufferOf(w);
            HintsWriter l = HintsWriter.create(dir, descriptor("LZ4Compressor"));
            put(l, agg, rec);
            boolean lz4Direct = bufferOf(l).isDirect();
            // the pool delta is information only: FileChannel.write(heap buffer) caches a temporary direct buffer of the
            // write's size in the JDK (found in shakedown 1, 2026-10-25), so a heap compression buffer still moves the pool
            check("deflate", !b.isDirect() && lz4Direct,
                  "deflate capacity=" + b.capacity() + " isDirect=" + b.isDirect() + " pool delta (info, JDK temp buffer)=" + (after[0] - before[0])
                  + "; lz4 isDirect=" + lz4Direct);
            w.close();
            l.close();
        }

        // cap-boundary
        {
            HintsBuffer b = HintsBuffer.create(32 * MIB);
            String err1 = null, err2 = null;
            boolean accepted;
            try (HintsBuffer.Allocation a = b.allocate(16 * MIB - HintsBuffer.ENTRY_OVERHEAD_SIZE))
            {
                accepted = a != null;
            }
            try
            {
                b.allocate(16 * MIB - HintsBuffer.ENTRY_OVERHEAD_SIZE + 1);
            }
            catch (IllegalArgumentException e)
            {
                err1 = e.getMessage();
            }
            try
            {
                b.allocate(17 * MIB);
            }
            catch (IllegalArgumentException e)
            {
                err2 = e.getMessage();
            }
            check("cap-boundary", accepted && err1 != null && err1.contains("16777216") && err2 != null && err2.contains("16777216"),
                  "accepted(16777204)=" + accepted + " refused(16777205)=" + err1 + " refused(17MiB)=" + err2);
            b.free();
        }

        // cap-formula
        {
            StringBuilder d = new StringBuilder();
            boolean ok = true;
            int[] mms = { 1, 4, 8, 16, 32, 64 }, want = { 16, 16, 16, 16, 32, 64 };
            for (int i = 0; i < mms.length; i++)
            {
                long slab = Math.max((long) mms[i] * MIB * 2, 32L * MIB);
                ok &= slab / 2 == (long) want[i] * MIB;
                d.append("mms=" + mms[i] + "MiB slab=" + slab / MIB + "MiB cap=" + slab / 2 / MIB + "MiB; ");
            }
            check("cap-formula", ok, d.toString());
        }

        // slab-control
        for (int c : new int[]{ 32 * MIB, 128 * MIB })
        {
            long[] before = settled();
            HintsBuffer b = HintsBuffer.create(c);
            long[] mid = settled();
            b.free();
            long[] end = settled();
            check("slab-control-" + c / MIB, mid[0] - before[0] == c && mid[1] - before[1] == 1 && mid[0] - end[0] == c,
                  "C=" + c + " rise=" + (mid[0] - before[0]) + " count +" + (mid[1] - before[1]) + " after free() fall=" + (mid[0] - end[0]));
        }
        assertEquals("mismatches", 0, mismatches);
    }
}
