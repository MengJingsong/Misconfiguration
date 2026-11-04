/*
 * Stage-4 harness, unit tier (B2) of hints-CompressedChecksummedDataInput-readBuffer-uncompressedSize--autonomous. Not upstream.
 * Compiled by unit-run.sh into a separate output directory (package org.apache.cassandra.hints, for the package-private
 * HintsWriter / HintsReader / HintsDescriptor); never copied into the repository's cassandra/cassandra-5.0.9/.
 *
 * One JVM per case (B2h, audit amendment R6), started by unit-run.sh with test/conf/cassandra.yaml plus a
 * file_cache_size line (so BufferPools' static threshold is the knob value).
 *   java ... ReaderBufferGrowthTest read    <label> <LZ4|Deflate> <fcsMiB> <blobBytesCSV> [forgedZ]
 *   java ... ReaderBufferGrowthTest control <label> <fcsMiB>
 *
 * read: one hint file, one block per listed blob (one Session per hint; audit R6), written by the production
 *   CompressedHintsWriter; the raw file is then parsed with this test's own 8-byte header reader (Z = uncompressedSize,
 *   C = compressedSize of every block; ground truth that does not depend on the reader). If forgedZ is given, block 1's
 *   Z field is rewritten in the file before the reader opens it. The file is read with HintsReader (pages, hints) and,
 *   after every hint, the reader's buffer capacity and compressedBuffer capacity (reflection) and the chunk-cache
 *   counters are printed. The model of the filed relations (audit amendments R1, R2, R5) is evaluated in the same JVM
 *   from the parsed Z, C and the fcs; each comparison is a "STAGE4 check ... ok|MISMATCH" line.
 * control: positive control (B2h, R1): 400 x get(65536) held at once from BufferPools.forChunkCache().
 * Output: "STAGE4 ..." lines to stdout and to -Dstage4.out if set. The program records mismatches and goes on; its exit
 * status is 0 unless set-up or the read itself failed unexpectedly (the readings are judged in the results file).
 */
package org.apache.cassandra.hints;

import java.io.FileWriter;
import java.io.PrintWriter;
import java.io.RandomAccessFile;
import java.lang.management.BufferPoolMXBean;
import java.lang.management.ManagementFactory;
import java.lang.reflect.Field;
import java.nio.ByteBuffer;
import java.nio.file.Files;
import java.util.ArrayList;
import java.util.Iterator;
import java.util.List;
import java.util.Random;
import java.util.UUID;

import com.google.common.collect.ImmutableMap;

import org.apache.cassandra.SchemaLoader;
import org.apache.cassandra.config.ParameterizedClass;
import org.apache.cassandra.cql3.statements.schema.CreateTableStatement;
import org.apache.cassandra.db.Mutation;
import org.apache.cassandra.db.RowUpdateBuilder;
import org.apache.cassandra.io.util.File;
import org.apache.cassandra.io.util.FileUtils;
import org.apache.cassandra.net.MessagingService;
import org.apache.cassandra.schema.KeyspaceParams;
import org.apache.cassandra.schema.TableMetadata;
import org.apache.cassandra.utils.memory.BufferPool;
import org.apache.cassandra.utils.memory.BufferPools;
import org.apache.cassandra.io.compress.BufferType;

public class ReaderBufferGrowthTest
{
    static final int KIB = 1024, MIB = 1 << 20;
    static final int NORMAL_CHUNK = 128 * KIB, MACRO = 8 * MIB, INITIAL = 4096;
    static final BufferPoolMXBean DIRECT = ManagementFactory.getPlatformMXBeans(BufferPoolMXBean.class).stream()
                                                            .filter(b -> b.getName().equals("direct")).findFirst().get();
    static PrintWriter out;
    static int checks, mismatches;
    static String label = "?";

    static void say(String s)
    {
        System.out.println(s);
        if (out != null)
            out.println(s);
    }

    static boolean check(String name, Object expected, Object actual)
    {
        boolean ok = String.valueOf(expected).equals(String.valueOf(actual));
        checks++;
        if (!ok)
            mismatches++;
        say("STAGE4 check " + label + " " + name + " expected=" + expected + " actual=" + actual + " " + (ok ? "ok" : "MISMATCH"));
        return ok;
    }

    static class Counters
    {
        final long size, used, ovf, direct;

        Counters(BufferPool p)
        {
            size = p.sizeInBytes();
            used = p.usedSizeInBytes();
            ovf = p.overflowMemoryInBytes();
            direct = DIRECT.getMemoryUsed();
        }

        long pooled() { return size - ovf; }

        public String toString()
        {
            return "size=" + size + " used=" + used + " overflow=" + ovf + " pooled=" + pooled() + " direct=" + direct;
        }
    }

    // ------------------------------------------------------------------ model (audit amendments R1, R2, R5)

    /** the request x is served from a pool chunk: fcs allows a macro chunk, and x fits the normal chunk (BufferPool.java:443,940) */
    static boolean pooled(long fcsMiB, boolean heap, long x)
    {
        return !heap && fcsMiB * MIB >= MACRO && x <= NORMAL_CHUNK;
    }

    static class Model
    {
        long cap = INITIAL;
        boolean capInitial = true, capPooled;
        long compCap = -1;
        boolean compPooled;
        long ovf, pooledUsed;
        boolean anyPooled, tiny;
        final List<Long> caps = new ArrayList<>();
        final long fcs;
        final boolean heap;

        Model(long fcs, boolean heap) { this.fcs = fcs; this.heap = heap; }

        void get(long x, boolean forComp)
        {
            boolean p = pooled(fcs, heap, x);
            if (p) { pooledUsed += x; anyPooled = true; }
            else ovf += x;
            if (forComp) { compPooled = p; compCap = x; }
            else { capPooled = p; cap = x; capInitial = false; }
        }

        void block(long z, long c)
        {
            if (compCap < 0 || c > compCap)
            {
                long x = c + c / 20;
                if (compCap >= 0) { if (compPooled) pooledUsed -= compCap; else ovf -= compCap; }
                get(x, true);
            }
            if (cap < z)
            {
                long x = z + z / 20;
                if (capInitial) ovf -= INITIAL;               // put() of the unpooled, uncounted initial buffer (R5)
                else if (capPooled) pooledUsed -= cap;
                else ovf -= cap;
                get(x, false);
            }
            if (z > 0)
                caps.add(cap);                 // one entry per real block = per hint read
            if (c <= 1024)
                tiny = true;               // served by the tiny pool: its own chunk bookkeeping is not modelled for 'used'
        }

        void close()
        {
            if (compCap >= 0) { if (compPooled) pooledUsed -= compCap; else ovf -= compCap; }
            // super.close() is FileUtils.clean(buffer): the buffer's counters stay (R5)
        }
    }

    // ------------------------------------------------------------------ helpers

    static TableMetadata tbm;

    static void setUp() throws Exception
    {
        SchemaLoader.prepareServer();
        tbm = CreateTableStatement.parse("CREATE TABLE t (k int PRIMARY KEY, v blob)", "ks").build();
        SchemaLoader.createKeyspace("ks", KeyspaceParams.simple(1), tbm);
    }

    static Hint hintOf(int s, int key)
    {
        byte[] v = new byte[s];
        new Random(s + 31L * key).nextBytes(v);              // random: incompressible, so C is about Z
        Mutation m = new RowUpdateBuilder(tbm, System.currentTimeMillis() * 1000, key).add("v", ByteBuffer.wrap(v)).build();
        return Hint.create(m, System.currentTimeMillis());
    }

    static Object field(Object o, Class<?> c, String name) throws Exception
    {
        Field f = c.getDeclaredField(name);
        f.setAccessible(true);
        return f.get(o);
    }

    static Object field(Object o, String name) throws Exception
    {
        for (Class<?> c = o.getClass(); c != null; c = c.getSuperclass())
        {
            try
            {
                return field(o, c, name);
            }
            catch (NoSuchFieldException e) { /* next superclass */ }
        }
        throw new NoSuchFieldException(name);
    }

    static void read(String comp, long fcs, String blobs, long forgedZ) throws Exception
    {
        boolean heap = comp.equals("Deflate");
        setUp();
        BufferPool pool = BufferPools.forChunkCache();
        File dir = new File(Files.createTempDirectory("stage4-hu"));
        try
        {
            String[] bl = blobs.split(",");
            UUID host = UUID.randomUUID();
            long ts = System.currentTimeMillis();
            ImmutableMap<String, Object> params = ImmutableMap.of(HintsDescriptor.COMPRESSION,
                                                                  ImmutableMap.of(ParameterizedClass.CLASS_NAME, comp + "Compressor"));
            HintsDescriptor descriptor = new HintsDescriptor(host, ts, params);
            ByteBuffer wb = ByteBuffer.allocateDirect(HintsWriteExecutor.WRITE_BUFFER_SIZE);
            try (HintsWriter writer = HintsWriter.create(dir, descriptor))
            {
                for (int i = 0; i < bl.length; i++)
                    try (HintsWriter.Session s = writer.newSession(wb))
                    {
                        s.append(hintOf(Integer.parseInt(bl[i]), i));
                    }
            }
            File file = descriptor.file(dir);

            // ground truth from the raw file: descriptor length, then 8-byte block headers (big endian: Z, C)
            long hdrEnd = descriptor.serializedSize();
            say("STAGE4 info " + label + " descriptor length " + hdrEnd + " file length " + file.length());
            if (forgedZ > 0)
                try (RandomAccessFile raf = new RandomAccessFile(file.toJavaIOFile(), "rw"))
                {
                    raf.seek(hdrEnd);
                    raf.writeInt((int) forgedZ);
                    say("STAGE4 info " + label + " forged block 1 header Z=" + forgedZ);
                }
            List<long[]> blocks = new ArrayList<>();
            try (RandomAccessFile raf = new RandomAccessFile(file.toJavaIOFile(), "r"))
            {
                long pos = hdrEnd;
                while (pos < raf.length())
                {
                    raf.seek(pos);
                    long z = raf.readInt() & 0xFFFFFFFFL, c = raf.readInt() & 0xFFFFFFFFL;
                    blocks.add(new long[]{ z, c });
                    say("STAGE4 block " + label + " idx=" + blocks.size() + " Z=" + z + " C=" + c);
                    pos += 8 + c;
                }
                check("raw file ends on a block boundary", raf.length(), pos);
            }
            long nonEmpty = blocks.stream().filter(b -> b[0] > 0).count(), empty = blocks.size() - nonEmpty;
            long oversized = blocks.stream().filter(b -> b[0] > HintsWriteExecutor.WRITE_BUFFER_SIZE).count();
            check("non-empty blocks in file = hints written", bl.length, nonEmpty);
            check("empty blocks (Z=0) = hints larger than the 256 KiB write buffer", oversized, empty);
            say("STAGE4 info " + label + " empty blocks " + empty + " (Session.append flushes the empty aggregation buffer before an oversized hint)");

            Model m = new Model(fcs, heap);
            for (long[] b : blocks)
                m.block(b[0], b[1]);

            Counters c0 = new Counters(pool);
            say("STAGE4 counters " + label + " before " + c0);
            int hints = 0;
            try (HintsReader reader = HintsReader.open(file))
            {
                Object input = reader.getInput();
                check("input class", "CompressedChecksummedDataInput", input.getClass().getSimpleName());
                for (HintsReader.Page page : reader)
                {
                    Iterator<Hint> it = page.hintsIterator();
                    while (it.hasNext())
                    {
                        it.next();
                        hints++;
                        ByteBuffer buf = (ByteBuffer) field(input, "buffer");
                        Object cb = field(input, "compressedBuffer");
                        long ccap = cb == null ? -1 : ((ByteBuffer) cb).capacity();
                        Counters c = new Counters(pool);
                        say("STAGE4 hint " + label + " n=" + hints + " buffer.capacity=" + buf.capacity() + " buffer.isDirect=" + buf.isDirect()
                            + " compressedBuffer.capacity=" + ccap + " " + c);
                        if (hints <= m.caps.size())
                            check("capacity after hint " + hints, m.caps.get(hints - 1), buf.capacity());
                    }
                }
                Counters c1 = new Counters(pool);
                say("STAGE4 counters " + label + " after_read " + c1);
                check("hints read", nonEmpty, hints);
                long chunkDelta = m.anyPooled && c0.pooled() == 0 ? MACRO : 0;
                check("overflow delta after read", m.ovf, c1.ovf - c0.ovf);
                check("pooled-memory delta after read (chunks)", chunkDelta, c1.pooled() - c0.pooled());
                check("size delta after read", chunkDelta + m.ovf, c1.size - c0.size);
                if (m.tiny) say("STAGE4 info " + label + " used delta after read " + (c1.used - c0.used) + " (tiny-pool buffer present: not checked; model " + (m.pooledUsed + m.ovf) + ")");
                else check("used delta after read", m.pooledUsed + m.ovf, c1.used - c0.used);
                if (!heap)
                    say("STAGE4 info " + label + " direct-pool delta after read " + (c1.direct - c0.direct));
            }
            m.close();
            Counters c2 = new Counters(pool);
            say("STAGE4 counters " + label + " after_close " + c2);
            long chunkDelta = m.anyPooled && c0.pooled() == 0 ? MACRO : 0;
            check("overflow delta after close", m.ovf, c2.ovf - c0.ovf);
            if (m.tiny) say("STAGE4 info " + label + " used delta after close " + (c2.used - c0.used) + " (tiny-pool buffer present: not checked; model " + (m.pooledUsed + m.ovf) + ")");
            else check("used delta after close", m.pooledUsed + m.ovf, c2.used - c0.used);
            check("size delta after close", chunkDelta + m.ovf, c2.size - c0.size);
            say("STAGE4 case " + label + " comp=" + comp + " fcs=" + fcs + " blocks=" + blocks.size() + " final_capacity=" + m.cap
                + " overflow_delta_after_read=" + m.ovf + " threshold=" + fcs * MIB);
        }
        finally
        {
            FileUtils.deleteRecursive(dir);
        }
    }

    static void control(long fcs) throws Exception
    {
        BufferPool pool = BufferPools.forChunkCache();
        Counters c0 = new Counters(pool);
        say("STAGE4 counters " + label + " before " + c0 + " threshold=" + pool.memoryUsageThreshold());
        check("pool threshold = file_cache_size", fcs * MIB, pool.memoryUsageThreshold());
        List<ByteBuffer> held = new ArrayList<>();
        for (int i = 0; i < 400; i++)
            held.add(pool.get(64 * KIB, BufferType.OFF_HEAP));
        Counters c1 = new Counters(pool);
        say("STAGE4 counters " + label + " held400x64KiB " + c1);
        long total = 400L * 64 * KIB;
        long pooledExp = fcs * MIB >= MACRO ? Math.min((fcs * MIB / MACRO) * MACRO, ((total + MACRO - 1) / MACRO) * MACRO) : 0;
        long pooledCapacityBuffers = pooledExp == 0 ? 0 : Math.min(400, (pooledExp / MACRO) * 128);
        long ovfExp = (400 - pooledCapacityBuffers) * 64 * KIB;
        check("pooled bytes (size - overflow) after 400 x 64 KiB", pooledExp, c1.pooled() - c0.pooled());
        check("overflow bytes after 400 x 64 KiB", ovfExp, c1.ovf - c0.ovf);
        check("pooled bytes never exceed the threshold", true, c1.pooled() <= fcs * MIB);
        for (ByteBuffer b : held)
            pool.put(b);
        Counters c2 = new Counters(pool);
        say("STAGE4 counters " + label + " released " + c2);
        check("overflow returns to its start after put", 0, c2.ovf - c0.ovf);
        say("STAGE4 case " + label + " control fcs=" + fcs + " pooled=" + (c1.pooled() - c0.pooled()) + " overflow=" + (c1.ovf - c0.ovf));
    }

    public static void main(String[] a) throws Exception
    {
        String o = System.getProperty("stage4.out");
        out = o == null ? null : new PrintWriter(new FileWriter(o, true), true);
        label = a[1];
        int rc = 0;
        try
        {
            say("STAGE4 info " + label + " start mode=" + a[0] + " args=" + String.join(",", a) + " maxDirect=" + System.getProperty("stage4.maxdirect")
                + " messagingVersion=" + MessagingService.current_version);
            if (a[0].equals("read"))
                read(a[2], Long.parseLong(a[3]), a[4], a.length > 5 ? Long.parseLong(a[5]) : 0);
            else
            {
                SchemaLoader.prepareServer();
                control(Long.parseLong(a[2]));
            }
        }
        catch (Throwable t)
        {
            rc = 1;
            say("STAGE4 error " + label + " " + t);
            t.printStackTrace();
        }
        say("STAGE4 summary " + label + " checks=" + checks + " mismatches=" + mismatches + " rc=" + rc);
        if (out != null)
            out.close();
        System.exit(rc);
    }
}
