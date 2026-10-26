package org.apache.cassandra.io.compress;

import java.io.BufferedWriter;
import java.io.IOException;
import java.lang.management.BufferPoolMXBean;
import java.lang.management.ManagementFactory;
import java.lang.reflect.Field;
import java.nio.ByteBuffer;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.nio.file.StandardOpenOption;
import java.util.ArrayList;
import java.util.List;
import java.util.Random;

import org.junit.Assert;
import org.junit.BeforeClass;
import org.junit.Test;

import org.apache.cassandra.config.DatabaseDescriptor;
import org.apache.cassandra.db.ClusteringComparator;
import org.apache.cassandra.db.marshal.UTF8Type;
import org.apache.cassandra.io.sstable.metadata.MetadataCollector;
import org.apache.cassandra.io.util.File;
import org.apache.cassandra.io.util.SequentialWriterOption;
import org.apache.cassandra.schema.CompressionParams;

/**
 * Stage-4 harness for compressed-sequentialwriter-resetandtruncate-compressedbuffer--autonomous (unit tier, B2).
 * Drives CompressedSequentialWriter directly and reads its private 'compressed' buffer before and after
 * resetAndTruncate. Readings go to ~/s4-cs-logs/unit-readings.txt (one READING line per cell); expectations are
 * checked at the end so every cell is recorded even if one contradicts.
 */
public class ChunkBufferGrowthTest
{
    static final int[] CHUNKS = { 4096, 16384, 65536, 1048576 };
    static final Path OUT = Paths.get(System.getProperty("user.home"), "s4-cs-logs", "unit-readings.txt");
    final List<String> failures = new ArrayList<>();

    @BeforeClass
    public static void init()
    {
        DatabaseDescriptor.daemonInitialization();
    }

    static void log(String s) throws IOException
    {
        System.out.println(s);
        Files.write(OUT, (s + "\n").getBytes(StandardCharsets.UTF_8), StandardOpenOption.CREATE, StandardOpenOption.APPEND);
    }

    static Field field(Class<?> c, String n) throws Exception
    {
        for (Class<?> k = c; k != null; k = k.getSuperclass())
        {
            try
            {
                Field f = k.getDeclaredField(n);
                f.setAccessible(true);
                return f;
            }
            catch (NoSuchFieldException e) { /* try the superclass */ }
        }
        throw new NoSuchFieldException(n);
    }

    static long[] direct()
    {
        for (BufferPoolMXBean b : ManagementFactory.getPlatformMXBeans(BufferPoolMXBean.class))
            if (b.getName().equals("direct"))
                return new long[]{ b.getCount(), b.getTotalCapacity() };
        return new long[]{ -1, -1 };
    }

    static int lz4Bound(int n)
    {
        return 4 + n + n / 255 + 16;
    }

    void expect(boolean ok, String what)
    {
        if (!ok) failures.add(what);
    }

    /**
     * One cell. mode: "normal" (mark at chunk boundary, 4 more chunks, reset) or "early" (mark inside the
     * current chunk, reset returns at line 233).
     */
    void cell(String name, CompressionParams params, int chunk, boolean random, String mode,
              long expBefore, long expAfter, boolean expSame) throws Exception
    {
        java.io.File dir = Files.createTempDirectory("csgrow").toFile();
        File data = new File(new java.io.File(dir, "d.db"));
        File offs = new File(new java.io.File(dir, "d.off"));
        byte[] chunkBytes = new byte[chunk];
        if (random) new Random(1).nextBytes(chunkBytes);
        Field fComp = field(CompressedSequentialWriter.class, "compressed");
        Field fBuf = field(CompressedSequentialWriter.class, "buffer");
        try (CompressedSequentialWriter w = new CompressedSequentialWriter(data, offs, null, SequentialWriterOption.DEFAULT, params,
                                                                           new MetadataCollector(new ClusteringComparator(UTF8Type.instance))))
        {
            ByteBuffer comp0 = (ByteBuffer) fComp.get(w);
            ByteBuffer buf0 = (ByteBuffer) fBuf.get(w);
            int cap0 = comp0.capacity();
            boolean isDirect = comp0.isDirect();
            long[] d0 = direct();
            long markChunkOffset;
            long lenBeforeReset;
            Object mark;
            long posAtMark;
            if (mode.equals("normal"))
            {
                w.write(chunkBytes);
                w.write(chunkBytes);                 // buffer full, chunks 0 flushed, chunk 1 buffered
                mark = w.mark();                     // flushes chunk 1; mark at start of chunk 2
                posAtMark = w.position();
                for (int i = 0; i < 4; i++) w.write(chunkBytes);
            }
            else
            {
                w.write(chunkBytes);
                w.write(chunkBytes, 0, chunk / 2);   // chunk 0 flushed, chunk 1 half full
                mark = w.mark();
                posAtMark = w.position();
                w.write(chunkBytes, 0, chunk / 4);
            }
            Field fMarkOff = mark.getClass().getDeclaredField("chunkOffset");
            fMarkOff.setAccessible(true);
            markChunkOffset = fMarkOff.getLong(mark);
            lenBeforeReset = data.length();
            long[] d1 = direct();
            w.resetAndTruncate((org.apache.cassandra.io.util.DataPosition) mark);
            ByteBuffer comp1 = (ByteBuffer) fComp.get(w);
            ByteBuffer buf1 = (ByteBuffer) fBuf.get(w);
            long lenAfter = data.length();
            long[] d2 = direct();
            boolean same = comp0 == comp1;
            log(String.format("READING cell=%s mode=%s chunk=%d data=%s compressedCapBefore=%d compressedCapAfter=%d sameObject=%s isDirect=%s bufferCap=%d bufferSame=%s " +
                              "markChunkOffset=%d fileLenBeforeReset=%d fileLenAfterReset=%d posAtMark=%d posAfter=%d directCount=%d/%d/%d directTotal=%d/%d/%d",
                              name, mode, chunk, random ? "random" : "zeros", cap0, comp1.capacity(), same, isDirect, buf0.capacity(), buf0 == buf1,
                              markChunkOffset, lenBeforeReset, lenAfter, posAtMark, w.position(), d0[0], d1[0], d2[0], d0[1], d1[1], d2[1]));
            expect(cap0 == expBefore, name + " before " + cap0 + " != " + expBefore);
            expect(comp1.capacity() == expAfter, name + " after " + comp1.capacity() + " != " + expAfter);
            expect(same == expSame, name + " sameObject " + same + " != " + expSame);
            expect(buf0.capacity() == chunk, name + " buffer capacity " + buf0.capacity());
            expect(w.position() == posAtMark, name + " position after reset " + w.position() + " != " + posAtMark);
            if (mode.equals("normal"))
                expect(lenAfter == markChunkOffset && lenBeforeReset > lenAfter, name + " file did not shrink to the mark's chunk offset");
            else
                expect(lenAfter == lenBeforeReset, name + " early-return arm changed the file length");
        }
        finally
        {
            for (java.io.File f : dir.listFiles()) f.delete();
            dir.delete();
        }
    }

    @Test
    public void growth() throws Exception
    {
        Files.write(OUT, ("# run " + System.currentTimeMillis() + "\n").getBytes(StandardCharsets.UTF_8), StandardOpenOption.CREATE, StandardOpenOption.APPEND);
        // LZ4, real compressor: chunk sweep x data
        for (int chunk : CHUNKS)
            for (boolean random : new boolean[]{ true, false })
            {
                CompressionParams p = CompressionParams.lz4(chunk);
                int b = lz4Bound(chunk);
                log("INFO lz4 chunk=" + chunk + " initialCompressedBufferLength=" + p.getSstableCompressor().initialCompressedBufferLength(chunk) + " formula=" + b);
                cell("lz4", p, chunk, random, "normal", b, b, true);
            }
        // early-return control
        cell("lz4-early", CompressionParams.lz4(16384), 16384, true, "early", lz4Bound(16384), lz4Bound(16384), true);
        // Mock forcing arm: ratio 2.0, min_compress_ratio 2.0 => capacity chunk/2, stored chunk = chunk
        for (int chunk : CHUNKS)
        {
            CompressionParams p = new CompressionParams(MockCompressor.class.getTypeName(), MockCompressor.paramsFor(2.0, 0), chunk, 2.0);
            cell("mock-force", p, chunk, true, "normal", chunk / 2, chunk, false);
        }
        // Mock ratio 0.5 (write-up's original arm): bound is 2 x chunk, must not fire
        for (int chunk : CHUNKS)
        {
            CompressionParams p = new CompressionParams(MockCompressor.class.getTypeName(), MockCompressor.paramsFor(0.5, 0), chunk, 0.0);
            cell("mock-ratio0.5", p, chunk, true, "normal", 2L * chunk, 2L * chunk, true);
        }
        log("SUMMARY failures=" + failures.size() + " " + failures);
        Assert.assertTrue(failures.toString(), failures.isEmpty());
    }
}
