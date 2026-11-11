/*
 * Stage-4 harness (unit tier B2 and the cluster tier's file producer) of
 * hints-EncryptedChecksummedDataInput-reusableBuffers-decryptBuffer--autonomous. Not upstream. Compiled by unit-run.sh into a separate
 * output directory (package org.apache.cassandra.hints for the package-private writer/reader/descriptor); never copied into the repository.
 *
 *   read    <label> <groups> [second=<groups>] [forged]   write an encrypted hints file (production EncryptedHintsWriter, one Session),
 *                                                          parse its raw block headers, read it back with HintsReader on a fresh
 *                                                          FastThreadLocalThread, report the retained thread-local capacity per page.
 *   c1      <label>                                       positive control: HintsBuffer.create(1 MiB).allocate(600 KiB) must throw, then a
 *                                                          600 KiB hint is written and read.
 *   produce <label> <dir> <hostId> <groups> [forged|plain]      cluster tier: write the file into <dir> named for <hostId>; prints its path.
 * groups = comma list of kind:size:count (kind r = random blob, z = zeros; size in bytes). forged = rewrite the file to
 * [descriptor][enc=512 MiB][plain=512 MiB][5 junk bytes] (audit R3).
 * Output: "STAGE4 ..." lines to stdout and to -Dstage4.out. Table ks.t (k int PRIMARY KEY, v blob) has the fixed ID below, so a hint
 * produced here is valid for a cluster table created WITH ID = that UUID.
 */
package org.apache.cassandra.hints;

import java.io.FileWriter;
import java.io.PrintWriter;
import java.io.RandomAccessFile;
import java.lang.management.ManagementFactory;
import java.lang.reflect.Field;
import java.nio.ByteBuffer;
import java.nio.file.Files;
import java.util.*;

import com.google.common.collect.ImmutableMap;
import io.netty.util.concurrent.FastThreadLocal;
import io.netty.util.concurrent.FastThreadLocalThread;

import org.apache.cassandra.SchemaLoader;
import org.apache.cassandra.config.DatabaseDescriptor;
import org.apache.cassandra.cql3.statements.schema.CreateTableStatement;
import org.apache.cassandra.db.Mutation;
import org.apache.cassandra.db.RowUpdateBuilder;
import org.apache.cassandra.io.FSReadError;
import org.apache.cassandra.io.util.File;
import org.apache.cassandra.io.util.FileUtils;
import org.apache.cassandra.schema.KeyspaceParams;
import org.apache.cassandra.schema.TableId;
import org.apache.cassandra.schema.TableMetadata;
import org.apache.cassandra.security.EncryptionContext;
import org.apache.cassandra.security.EncryptionContextGenerator;

public class EcProbe
{
    static final String TABLE_ID = "6f1b8c2e-4d3a-4e5b-9a77-0c0ffee00033";
    static PrintWriter out;
    static String label = "?";
    static int checks, mismatches;
    static TableMetadata tbm;
    static final com.sun.management.ThreadMXBean TMX = (com.sun.management.ThreadMXBean) ManagementFactory.getThreadMXBean();

    static void say(String s) { System.out.println(s); if (out != null) out.println(s); }

    static boolean check(String name, Object expected, Object actual)
    {
        boolean ok = String.valueOf(expected).equals(String.valueOf(actual));
        checks++; if (!ok) mismatches++;
        say("STAGE4 check " + label + " " + name + " expected=" + expected + " actual=" + actual + " " + (ok ? "ok" : "MISMATCH"));
        return ok;
    }

    static boolean checkRange(String name, long lo, long hi, long actual)
    {
        boolean ok = actual >= lo && actual <= hi;
        checks++; if (!ok) mismatches++;
        say("STAGE4 check " + label + " " + name + " expected=[" + lo + "," + hi + "] actual=" + actual + " " + (ok ? "ok" : "MISMATCH"));
        return ok;
    }

    static boolean isUp;

    static void setUp() throws Exception
    {
        if (isUp) return;
        isUp = true;
        SchemaLoader.prepareServer();
        tbm = CreateTableStatement.parse("CREATE TABLE t (k int PRIMARY KEY, v blob)", "ks").id(TableId.fromString(TABLE_ID)).build();
        SchemaLoader.createKeyspace("ks", KeyspaceParams.simple(1), tbm);
        EncryptionContext ec = EncryptionContextGenerator.createContext(true);
        DatabaseDescriptor.setEncryptionContext(ec);
        say("STAGE4 info " + label + " max_mutation_size=" + DatabaseDescriptor.getMaxMutationSize() + " maxHintsFileSize=" + DatabaseDescriptor.getMaxHintsFileSize());
    }

    static Hint hintOf(char kind, int s, int key)
    {
        byte[] v = new byte[s];
        if (kind == 'r') new Random(s + 31L * key).nextBytes(v);
        Mutation m = new RowUpdateBuilder(tbm, System.currentTimeMillis() * 1000, key).add("v", ByteBuffer.wrap(v)).build();
        return Hint.create(m, System.currentTimeMillis());
    }

    static Object field(Object o, String name) throws Exception
    {
        for (Class<?> c = o.getClass(); c != null; c = c.getSuperclass())
            try { Field f = c.getDeclaredField(name); f.setAccessible(true); return f.get(o); } catch (NoSuchFieldException e) { }
        throw new NoSuchFieldException(name);
    }

    @SuppressWarnings("unchecked")
    static int tlCapacity() throws Exception
    {
        Field f = EncryptedChecksummedDataInput.class.getDeclaredField("reusableBuffers");
        f.setAccessible(true);
        return ((FastThreadLocal<ByteBuffer>) f.get(null)).get().capacity();
    }

    static boolean plain;

    static File writeFile(File dir, UUID host, String groups, boolean forged) throws Exception
    {
        ImmutableMap<String, Object> params = plain ? ImmutableMap.<String, Object>of() : ImmutableMap.of(HintsDescriptor.ENCRYPTION, DatabaseDescriptor.getEncryptionContext().toHeaderParameters());
        HintsDescriptor d = new HintsDescriptor(host, System.currentTimeMillis(), params);
        check("descriptor is encrypted", !plain, d.isEncrypted());
        ByteBuffer wb = ByteBuffer.allocateDirect(HintsWriteExecutor.WRITE_BUFFER_SIZE);
        int key = 0, n = 0;
        try (HintsWriter w = HintsWriter.create(dir, d))
        {
            check("writer class", plain ? "HintsWriter" : "EncryptedHintsWriter", w.getClass().getSimpleName());
            try (HintsWriter.Session s = w.newSession(wb))
            {
                for (String g : groups.split(","))
                {
                    String[] p = g.split(":");
                    int size = Integer.parseInt(p[1]), cnt = Integer.parseInt(p[2]);
                    for (int i = 0; i < cnt; i++) { s.append(hintOf(p[0].charAt(0), size, key++)); n++; }
                }
            }
        }
        File file = d.file(dir);
        say("STAGE4 info " + label + " wrote " + n + " hints, file " + file.length() + " bytes, descriptor " + d.serializedSize());
        if (forged)
        {
            try (RandomAccessFile raf = new RandomAccessFile(file.toJavaIOFile(), "rw"))
            {
                raf.setLength(d.serializedSize());
                raf.seek(d.serializedSize());
                raf.writeInt(512 << 20); raf.writeInt(512 << 20);
                raf.write(new byte[]{ 1, 2, 3, 4, 5 });
            }
            say("STAGE4 info " + label + " forged: header enc=plain=" + (512 << 20) + " + 5 junk bytes, file now " + file.length());
        }
        return file;
    }

    static List<long[]> blocks(File file, HintsDescriptor unused, long hdrEnd) throws Exception
    {
        List<long[]> b = new ArrayList<>();
        try (RandomAccessFile raf = new RandomAccessFile(file.toJavaIOFile(), "r"))
        {
            long pos = hdrEnd;
            while (pos + 8 <= raf.length())
            {
                raf.seek(pos);
                long enc = raf.readInt() & 0xFFFFFFFFL, plain = raf.readInt() & 0xFFFFFFFFL;
                b.add(new long[]{ enc, plain });
                say("STAGE4 block " + label + " idx=" + b.size() + " enc=" + enc + " plain=" + plain);
                pos += 8 + enc;
            }
            if (!label.contains("forged") && !label.startsWith("s5")) check("raw file ends on a block boundary", raf.length(), pos);
        }
        return b;
    }

    static long readOn(File file, long hdrEnd, boolean expectFail, long[] retainedOut) throws Exception
    {
        final long[] res = new long[4];       // 0 hints, 1 tl capacity at end, 2 allocated bytes delta, 3 failed(1)
        final Throwable[] err = new Throwable[1];
        Thread t = new FastThreadLocalThread(() -> {
            try
            {
                res[1] = tlCapacity();
                long tid = Thread.currentThread().getId();
                long a0 = TMX.getThreadAllocatedBytes(tid);
                say("STAGE4 info " + label + " reader thread " + Thread.currentThread().getName() + " tl capacity at start " + res[1]);
                try (HintsReader reader = HintsReader.open(file))
                {
                    Object input = reader.getInput();
                    say("STAGE4 info " + label + " input class " + input.getClass().getSimpleName());
                    int pageNo = 0;
                    for (HintsReader.Page page : reader)
                    {
                        Iterator<Hint> it = page.hintsIterator();
                        while (it.hasNext()) { it.next(); res[0]++; }
                        pageNo++;
                        say("STAGE4 page " + label + " n=" + pageNo + " hints=" + res[0] + " tl.capacity=" + tlCapacity()
                            + " reader.buffer.capacity=" + ((ByteBuffer) field(input, "buffer")).capacity()
                            + " reader.buffer.isDirect=" + ((ByteBuffer) field(input, "buffer")).isDirect());
                    }
                }
                res[2] = TMX.getThreadAllocatedBytes(tid) - a0;
            }
            catch (Throwable e)
            {
                err[0] = e; res[3] = 1;
                try { res[2] = TMX.getThreadAllocatedBytes(Thread.currentThread().getId()); } catch (Throwable x) { }
            }
            try { res[1] = tlCapacity(); } catch (Throwable x) { }
        }, "ec-reader");
        t.start(); t.join();
        if (err[0] != null)
            say("STAGE4 info " + label + " read threw " + err[0].getClass().getName() + ": " + err[0].getMessage() + " cause=" + err[0].getCause());
        say("STAGE4 result " + label + " hints_read=" + res[0] + " tl_capacity_after=" + res[1] + " thread_allocated_bytes=" + res[2] + " failed=" + res[3]);
        retainedOut[0] = res[1]; retainedOut[1] = res[2]; retainedOut[2] = res[3]; retainedOut[3] = res[0];
        return res[1];
    }

    static void read(String groups, String second, boolean forged) throws Exception
    {
        setUp();
        File dir = new File(Files.createTempDirectory("stage4-ec"));
        try
        {
            File file = writeFile(dir, UUID.randomUUID(), groups, forged);
            HintsDescriptor d = HintsDescriptor.readFromFile(file);
            long hdrEnd = d.serializedSize();
            List<long[]> bl = blocks(file, d, hdrEnd);
            long maxEnc = 0; for (long[] b : bl) maxEnc = Math.max(maxEnc, b[0]);
            long[] r = new long[4];
            readOn(file, hdrEnd, forged, r);
            if (forged)
            {
                check("forged: read failed", 1, r[2]);
                check("forged: thread-local capacity unchanged (0)", 0, r[0]);
                say("STAGE4 check " + label + " forged: thread allocated >= 512 MiB expected=true actual=" + (r[1] >= (512L << 20)) + " (" + r[1] + ") " + (r[1] >= (512L << 20) ? "ok" : "MISMATCH"));
                checks++; if (r[1] < (512L << 20)) mismatches++;
            }
            else
            {
                check("read ok", 0, r[2]);
                check("retained capacity = max encrypted length of the raw blocks", maxEnc, r[0]);
                say("STAGE4 info " + label + " max_enc=" + maxEnc + " = " + maxEnc / 1024.0 + " KiB; vs 256 KiB: " + (maxEnc - 262144) + " bytes");
            }
            if (second != null)
            {
                File d2 = new File(Files.createTempDirectory("stage4-ec2"));
                File f2 = writeFile(d2, UUID.randomUUID(), second, false);
                HintsDescriptor dd = HintsDescriptor.readFromFile(f2);
                List<long[]> b2 = blocks(f2, dd, dd.serializedSize());
                say("STAGE4 info " + label + " second (smaller) file read on a NEW thread: thread-local is per thread, so shrink is tested in one thread below");
                FileUtils.deleteRecursive(d2);
            }
            say("STAGE4 case " + label + " groups=" + groups + " blocks=" + bl.size() + " max_enc=" + maxEnc + " retained=" + r[0] + " forged=" + forged
                + " max_mutation_size=" + DatabaseDescriptor.getMaxMutationSize());
        }
        finally { FileUtils.deleteRecursive(dir); }
    }

    /** no-shrink: read a big file then a small file on the SAME thread */
    static void noShrink(String big, String small) throws Exception
    {
        setUp();
        File dir = new File(Files.createTempDirectory("stage4-ec"));
        try
        {
            File fb = writeFile(dir, UUID.randomUUID(), big, false), fs = writeFile(dir, UUID.randomUUID(), small, false);
            final long[] cap = new long[3];
            Thread t = new FastThreadLocalThread(() -> {
                try
                {
                    for (int i = 0; i < 2; i++)
                    {
                        try (HintsReader r = HintsReader.open(i == 0 ? fb : fs)) { for (HintsReader.Page p : r) { Iterator<Hint> it = p.hintsIterator(); while (it.hasNext()) it.next(); } }
                        cap[i] = tlCapacity();
                        say("STAGE4 info " + label + " after file " + (i + 1) + " tl.capacity=" + cap[i]);
                    }
                }
                catch (Throwable e) { say("STAGE4 error " + label + " " + e); }
            }, "ec-reader");
            t.start(); t.join();
            long bigMax = 0, smallMax = 0;
            HintsDescriptor d1 = HintsDescriptor.readFromFile(fb), d2 = HintsDescriptor.readFromFile(fs);
            for (long[] b : blocks(fb, d1, d1.serializedSize())) bigMax = Math.max(bigMax, b[0]);
            for (long[] b : blocks(fs, d2, d2.serializedSize())) smallMax = Math.max(smallMax, b[0]);
            check("after big file capacity = its max encrypted length", bigMax, cap[0]);
            check("after the smaller second file capacity unchanged (no shrink)", cap[0], cap[1]);
            check("second file's own max encrypted length is smaller", true, smallMax < bigMax);
        }
        finally { FileUtils.deleteRecursive(dir); }
    }

    static void c1() throws Exception
    {
        setUp();
        HintsBuffer b = HintsBuffer.create(1 << 20);
        String msg = null;
        try { b.allocate(600 * 1024); } catch (IllegalArgumentException e) { msg = e.getMessage(); }
        check("write-side cap rejects a 600 KiB hint in a 1 MiB slab", "Hint of 614400 bytes is too large - the maximum size is 524288", msg);
        read("r:614400:1", null, false);
    }

    static void produce(String dirName, String host, String groups, boolean forged) throws Exception
    {
        setUp();
        File f = writeFile(new File(dirName), UUID.fromString(host), groups, forged);
        HintsDescriptor d = HintsDescriptor.readFromFile(f);
        blocks(f, d, d.serializedSize());
        say("STAGE4 produced " + label + " " + f.absolutePath() + " " + f.length());
    }

    public static void main(String[] a) throws Exception
    {
        String o = System.getProperty("stage4.out");
        out = o == null ? null : new PrintWriter(new FileWriter(o, true), true);
        label = a[1];
        int rc = 0;
        try
        {
            say("STAGE4 info " + label + " start mode=" + a[0] + " args=" + String.join(",", a));
            switch (a[0])
            {
                case "read": { String second = null; boolean forged = false; for (int i = 3; i < a.length; i++) { if (a[i].equals("forged")) forged = true; else if (a[i].startsWith("second=")) second = a[i].substring(7); } read(a[2], second, forged); break; }
                case "noshrink": noShrink(a[2], a[3]); break;
                case "c1": c1(); break;
                case "produce": plain = a.length > 5 && a[5].equals("plain"); produce(a[2], a[3], a[4], a.length > 5 && a[5].equals("forged")); break;
                default: throw new IllegalArgumentException(a[0]);
            }
        }
        catch (Throwable t) { rc = 1; say("STAGE4 error " + label + " " + t); t.printStackTrace(); }
        say("STAGE4 summary " + label + " checks=" + checks + " mismatches=" + mismatches + " rc=" + rc);
        if (out != null) out.close();
        System.exit(rc);
    }
}
