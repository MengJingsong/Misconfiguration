/*
 * Stage-4 harness (not upstream): unit tier of chunk_length_in_kb-loadNextChunk-compressedChunk--autonomous.
 * Drives CompressedInputStream.loadNextChunk() directly and reads the check's operand
 * (compressedChunk.capacity()) and the JVM's direct BufferPool use. One @Test runs the arms named in
 * $STAGE4_ARMS (comma list; default: the arms for the JVM limit given in $STAGE4_SET: main | cap | cap38).
 * Output: $STAGE4_OUT/results.csv, one line per arm.
 */
package org.apache.cassandra.streaming.compression;

import java.io.File;
import java.io.FileWriter;
import java.io.PrintWriter;
import java.lang.management.BufferPoolMXBean;
import java.lang.management.ManagementFactory;
import java.lang.reflect.Field;
import java.nio.ByteBuffer;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Collections;
import java.util.List;
import java.util.Random;

import org.junit.BeforeClass;
import org.junit.Test;

import org.apache.cassandra.config.DatabaseDescriptor;
import org.apache.cassandra.db.streaming.CompressedInputStream;
import org.apache.cassandra.db.streaming.CompressionInfo;
import org.apache.cassandra.io.compress.CompressionMetadata;
import org.apache.cassandra.io.compress.ICompressor;
import org.apache.cassandra.io.util.DataInputBuffer;
import org.apache.cassandra.io.util.RebufferingInputStream;
import org.apache.cassandra.schema.CompressionParams;
import org.apache.cassandra.utils.ChecksumType;

public class CompressedInputStreamOversizeTest
{
    static final int MiB = 1 << 20;

    @BeforeClass
    public static void setupDD()
    {
        DatabaseDescriptor.daemonInitialization();
    }

    static long pool()
    {
        for (BufferPoolMXBean b : ManagementFactory.getPlatformMXBeans(BufferPoolMXBean.class))
            if (b.getName().equals("direct"))
                return b.getMemoryUsed();
        throw new IllegalStateException("no direct pool");
    }

    static Field field(Class<?> c, String n) throws Exception
    {
        Field f = c.getDeclaredField(n);
        f.setAccessible(true);
        return f;
    }

    /** kind: natural | hand | ratio11 */
    static String run(String arm, String kind, int n, long L) throws Exception
    {
        Random rnd = new Random(12345);
        CompressionParams params;
        byte[] wire;
        byte[] plain = null;
        long wireLen;
        if (kind.equals("natural"))
        {
            params = new CompressionParams("LZ4Compressor", Collections.emptyMap(), n, 0.0);
            plain = new byte[n];
            rnd.nextBytes(plain);
            ICompressor c = params.getSstableCompressor();
            ByteBuffer out = ByteBuffer.allocate(c.initialCompressedBufferLength(n));
            c.compress(ByteBuffer.wrap(plain), out);
            int w = out.position();
            out.flip();
            long crc = ChecksumType.CRC32.of(out);
            wire = new byte[w + 4];
            System.arraycopy(out.array(), 0, wire, 0, w);
            wire[w] = (byte) (crc >>> 24); wire[w + 1] = (byte) (crc >>> 16); wire[w + 2] = (byte) (crc >>> 8); wire[w + 3] = (byte) crc;
            wireLen = w;
        }
        else if (kind.equals("ratio11"))
        {
            params = new CompressionParams("LZ4Compressor", n, (int) Math.ceil(n / 1.1), Collections.emptyMap());
            plain = new byte[n];
            rnd.nextBytes(plain);
            long crc = ChecksumType.CRC32.of(ByteBuffer.wrap(plain));
            wire = new byte[n + 4];
            System.arraycopy(plain, 0, wire, 0, n);
            wire[n] = (byte) (crc >>> 24); wire[n + 1] = (byte) (crc >>> 16); wire[n + 2] = (byte) (crc >>> 8); wire[n + 3] = (byte) crc;
            wireLen = n;
        }
        else
        {
            params = new CompressionParams("LZ4Compressor", Collections.emptyMap(), n, 0.0);
            wire = new byte[(int) L + 4];
            rnd.nextBytes(wire);
            wireLen = L;
        }
        CompressionInfo info = CompressionInfo.newInstance(new CompressionMetadata.Chunk[]{ new CompressionMetadata.Chunk(0, (int) wireLen) }, params);
        double chance = kind.equals("hand") ? 0.0 : 1.0;

        long p0 = pool();
        CompressedInputStream cis = null;
        String ctorEx = "";
        String posEx = "";
        long pCtor = -1, pPos = -1, pClose = -1;
        long ccAfter = -1, bufAfter = -1, ccBefore = -1, bufBefore = -1;
        String dataOk = "na";
        Field fcc = field(CompressedInputStream.class, "compressedChunk");
        Field fbuf = field(RebufferingInputStream.class, "buffer");
        try
        {
            cis = new CompressedInputStream(new DataInputBuffer(wire), info, ChecksumType.CRC32, () -> chance);
            pCtor = pool();
            ccBefore = ((ByteBuffer) fcc.get(cis)).capacity();
            bufBefore = ((ByteBuffer) fbuf.get(cis)).capacity();
            try
            {
                cis.position(0);
                if (plain != null)
                {
                    ByteBuffer b = (ByteBuffer) fbuf.get(cis);
                    byte[] got = new byte[b.limit()];
                    ByteBuffer d = b.duplicate();
                    d.position(0);
                    d.get(got);
                    dataOk = Arrays.equals(got, plain) ? "yes" : "no";
                }
            }
            catch (Throwable t)
            {
                posEx = t.getClass().getName() + ": " + String.valueOf(t.getMessage()).replace(',', ';');
            }
            pPos = pool();
            ccAfter = ((ByteBuffer) fcc.get(cis)).capacity();
            bufAfter = ((ByteBuffer) fbuf.get(cis)).capacity();
        }
        catch (Throwable t)
        {
            ctorEx = t.getClass().getName() + ": " + String.valueOf(t.getMessage()).replace(',', ';');
        }
        finally
        {
            if (cis != null)
                try { cis.close(); } catch (Throwable t) { /* ignore */ }
        }
        pClose = pool();
        return String.join(",", arm, kind, "" + n, "" + wireLen, "" + bufBefore, "" + ccBefore, "" + bufAfter, "" + ccAfter,
                           "" + p0, "" + pCtor, "" + pPos, "" + pClose, dataOk, "ctor:" + ctorEx, "pos:" + posEx);
    }

    @Test
    public void runArms() throws Exception
    {
        String set = System.getenv().getOrDefault("STAGE4_SET", "main");
        String armsEnv = System.getenv("STAGE4_ARMS");
        List<String[]> all = new ArrayList<>();
        // name, kind, n, L
        if (set.equals("main"))
        {
            for (int n : new int[]{ 4096, 16384, 65536, MiB, 16 * MiB })
                all.add(new String[]{ "natural_" + n, "natural", "" + n, "0" });
            all.add(new String[]{ "hand_16384_16383", "hand", "16384", "16383" });
            all.add(new String[]{ "hand_16384_16384", "hand", "16384", "16384" });
            all.add(new String[]{ "hand_16384_16385", "hand", "16384", "16385" });
            all.add(new String[]{ "hand_16384_16468", "hand", "16384", "16468" });
            all.add(new String[]{ "hand_16384_24577", "hand", "16384", "24577" });
            all.add(new String[]{ "hand_16384_24576", "hand", "16384", "24576" });
            all.add(new String[]{ "hand_16384_32MiB", "hand", "16384", "" + 32L * MiB });
            all.add(new String[]{ "wire128MiB", "hand", "16384", "" + 128L * MiB });
            all.add(new String[]{ "hand_4096_4180", "hand", "4096", "4180" });
            all.add(new String[]{ "hand_65536_65620", "hand", "65536", "65620" });
            all.add(new String[]{ "ratio11_1MiB", "ratio11", "" + MiB, "0" });
            all.add(new String[]{ "ratio11_16MiB", "ratio11", "" + 16 * MiB, "0" });
        }
        else if (set.equals("cap"))
        {
            all.add(new String[]{ "cap_wire32MiB", "hand", "16384", "" + 32L * MiB });
            all.add(new String[]{ "cap_natural16MiB_init", "natural", "" + 16 * MiB, "0" });
        }
        else if (set.equals("cap38"))
        {
            all.add(new String[]{ "cap38_natural16MiB", "natural", "" + 16 * MiB, "0" });
            all.add(new String[]{ "cap38_ratio11_16MiB", "ratio11", "" + 16 * MiB, "0" });
        }
        List<String> only = armsEnv == null || armsEnv.isEmpty() ? null : Arrays.asList(armsEnv.split(","));
        File out = new File(System.getenv().getOrDefault("STAGE4_OUT", "/tmp"), "results-" + set + ".csv");
        try (PrintWriter w = new PrintWriter(new FileWriter(out, true)))
        {
            w.println("# set=" + set + " maxDirect=" + System.getProperty("sun.java.command", "") + " jvmargs=" + ManagementFactory.getRuntimeMXBean().getInputArguments());
            w.println("# arm,kind,n,wireLen,bufBefore,ccBefore,bufAfter,ccAfter,pool0,poolCtor,poolPos,poolClose,dataOk,ctorEx,posEx");
            for (String[] a : all)
            {
                if (only != null && !only.contains(a[0]))
                    continue;
                String line = run(a[0], a[1], Integer.parseInt(a[2]), Long.parseLong(a[3]));
                w.println(line);
                w.flush();
                System.out.println("RESULT " + line);
            }
        }
    }
}
