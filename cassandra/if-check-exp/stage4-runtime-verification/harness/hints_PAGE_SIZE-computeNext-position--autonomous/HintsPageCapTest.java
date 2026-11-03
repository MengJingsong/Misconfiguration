/*
 * Stage-4 harness, unit tier (B2, as amended 2026-10-26) of hints_PAGE_SIZE-computeNext-position--autonomous.
 * Copied into test/unit/org/apache/cassandra/hints/ by unit-run.sh and removed afterwards (package-private classes).
 *
 * For each value size v in {1 KiB, 16 KiB, 600 KiB} and file format in {plain, lz4}: write N = ceil(8 MiB / v) hints into one
 * hints file (one single-row mutation of table hpcap.t (k int PRIMARY KEY, v blob) per hint, value = v bytes of the pattern
 * (byte)(j % 13), which LZ4 compresses well), then read it back page by page with HintsReader, once with buffersIterator()
 * and once with hintsIterator(), holding every element of a page in a list until the page ends.
 *
 * Lines (stdout -> build/test/logs/.../TEST-org.apache.cassandra.hints.HintsPageCapTest.log):
 *   HPCAP-FILE v=<v> fmt=<plain|lz4> N=<hints written> emin=<min e> emax=<max e> fileBytes=<hints file size on disk>
 *              (e = Hint.serializer.serializedSize(hint, descriptor version) + 12, computed per hint at write time)
 *   HPCAP v=<v> fmt=<fmt> it=<buffers|hints> page=<i> c=<elements> P=<seek position - page start> sum=<sum of remaining()
 *         (buffers) or of serializedSize (hints)>
 *   HPCAP-END v=<v> fmt=<fmt> it=<it> pages=<pages> read=<elements over all pages>
 * Default sizes may be overridden for a shakedown with -Dhpcap.sizes=1024,16384 (comma list).
 */
package org.apache.cassandra.hints;

import java.io.IOException;
import java.nio.ByteBuffer;
import java.nio.file.Files;
import java.util.ArrayList;
import java.util.Iterator;
import java.util.List;
import java.util.UUID;
import java.util.concurrent.TimeUnit;

import com.google.common.collect.ImmutableMap;
import org.junit.AfterClass;
import org.junit.Assert;
import org.junit.BeforeClass;
import org.junit.Test;

import org.apache.cassandra.SchemaLoader;
import org.apache.cassandra.config.ParameterizedClass;
import org.apache.cassandra.cql3.statements.schema.CreateTableStatement;
import org.apache.cassandra.db.Mutation;
import org.apache.cassandra.db.RowUpdateBuilder;
import org.apache.cassandra.io.util.File;
import org.apache.cassandra.io.util.FileUtils;
import org.apache.cassandra.schema.KeyspaceParams;
import org.apache.cassandra.schema.Schema;
import org.apache.cassandra.schema.TableMetadata;

public class HintsPageCapTest
{
    static final String KS = "hpcap";
    static final int PAGE = 512 << 10; // HintsReader.PAGE_SIZE (HintsReader.java:56), re-stated only to print predictions
    static final List<File> dirs = new ArrayList<>();

    @BeforeClass
    public static void setup()
    {
        SchemaLoader.prepareServer();
        SchemaLoader.createKeyspace(KS, KeyspaceParams.simple(1),
                                    CreateTableStatement.parse("CREATE TABLE t (k int PRIMARY KEY, v blob)", KS));
        System.out.println("HPCAP-SETUP page=" + PAGE);
    }

    @AfterClass
    public static void cleanup()
    {
        for (File d : dirs)
            FileUtils.deleteRecursive(d);
    }

    static boolean enabled(int v)
    {
        String s = System.getProperty("hpcap.sizes");
        if (s == null || s.isEmpty())
            return true;
        for (String x : s.split(","))
            if (Integer.parseInt(x.trim()) == v)
                return true;
        return false;
    }

    @Test public void v1KiBPlain() throws Exception { run(1024, false); }
    @Test public void v1KiBLz4() throws Exception { run(1024, true); }
    @Test public void v16KiBPlain() throws Exception { run(16384, false); }
    @Test public void v16KiBLz4() throws Exception { run(16384, true); }
    @Test public void v600KiBPlain() throws Exception { run(614400, false); }
    @Test public void v600KiBLz4() throws Exception { run(614400, true); }

    static void run(int v, boolean lz4) throws IOException
    {
        if (!enabled(v))
            return;
        String fmt = lz4 ? "lz4" : "plain";
        int n = (int) ((8L * 1024 * 1024 + v - 1) / v);
        File dir = new File(Files.createTempDirectory("hpcap-" + v + "-" + fmt));
        dirs.add(dir);
        ImmutableMap<String, Object> params = lz4
            ? ImmutableMap.<String, Object>of(HintsDescriptor.COMPRESSION, ImmutableMap.<String, Object>of(ParameterizedClass.CLASS_NAME, "LZ4Compressor"))
            : ImmutableMap.<String, Object>of();
        HintsDescriptor d = new HintsDescriptor(UUID.randomUUID(), System.currentTimeMillis(), params);
        TableMetadata t = Schema.instance.getTableMetadata(KS, "t");

        byte[] value = new byte[v];
        for (int j = 0; j < v; j++)
            value[j] = (byte) (j % 13);

        long emin = Long.MAX_VALUE, emax = 0;
        ByteBuffer sbuf = ByteBuffer.allocateDirect(256 << 10);
        try (HintsWriter w = HintsWriter.create(dir, d))
        {
            Assert.assertEquals(lz4, w instanceof CompressedHintsWriter);
            try (HintsWriter.Session s = w.newSession(sbuf))
            {
                for (int i = 0; i < n; i++)
                {
                    long now = System.currentTimeMillis();
                    Mutation m = new RowUpdateBuilder(t, TimeUnit.MILLISECONDS.toMicros(now), i).add("v", ByteBuffer.wrap(value)).build();
                    Hint h = Hint.create(m, now);
                    long e = Hint.serializer.serializedSize(h, d.messagingVersion()) + HintsBuffer.ENTRY_OVERHEAD_SIZE;
                    emin = Math.min(emin, e);
                    emax = Math.max(emax, e);
                    s.append(h);
                }
            }
        }
        FileUtils.clean(sbuf);
        System.out.println("HPCAP-FILE v=" + v + " fmt=" + fmt + " N=" + n + " emin=" + emin + " emax=" + emax
                           + " fileBytes=" + d.file(dir).length());

        for (String it : new String[]{ "buffers", "hints" })
        {
            int pages = 0;
            long read = 0;
            try (HintsReader r = HintsReader.open(d.file(dir)))
            {
                for (HintsReader.Page p : r)
                {
                    List<Object> held = new ArrayList<>();
                    long sum = 0;
                    if (it.equals("buffers"))
                    {
                        Iterator<ByteBuffer> bi = p.buffersIterator();
                        while (bi.hasNext())
                        {
                            ByteBuffer b = bi.next();
                            held.add(b);
                            sum += b.remaining();
                        }
                    }
                    else
                    {
                        Iterator<Hint> hi = p.hintsIterator();
                        while (hi.hasNext())
                        {
                            Hint h = hi.next();
                            held.add(h);
                            sum += Hint.serializer.serializedSize(h, d.messagingVersion());
                        }
                    }
                    long pbytes = r.getInput().getSeekPosition().subtract(p.position);
                    System.out.println("HPCAP v=" + v + " fmt=" + fmt + " it=" + it + " page=" + pages + " c=" + held.size()
                                       + " P=" + pbytes + " sum=" + sum);
                    pages++;
                    read += held.size();
                }
            }
            System.out.println("HPCAP-END v=" + v + " fmt=" + fmt + " it=" + it + " pages=" + pages + " read=" + read);
            Assert.assertEquals(n, read);
        }
    }
}
