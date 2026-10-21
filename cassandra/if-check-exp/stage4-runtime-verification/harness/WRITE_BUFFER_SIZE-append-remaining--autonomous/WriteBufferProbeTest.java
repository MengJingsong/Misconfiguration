/*
 * Stage-4 harness, unit tier (B2) of WRITE_BUFFER_SIZE-append-remaining--autonomous. Not upstream.
 * Copy into test/unit/org/apache/cassandra/hints/ of a local clone (package-private HintsWriter, Session,
 * HintsWriteExecutor.WRITE_BUFFER_SIZE, HintsBuffer). Never into the shared cassandra-src clone.
 *
 * What it does (B2c-B2e):
 *  - one table ks.t (k int PRIMARY KEY, v blob); per hint size S (the blob value) one Hint, reused for every append;
 *  - variant H (append(Hint), the test-only overload) with the 256 KiB direct write buffer, S = 1, 100, 255, 257 KiB,
 *    1, 4, 15 MiB (+ 400 KiB for the control), N = 64 appends for S <= 255 KiB and 8 above, after 20 warm-up appends
 *    that are not measured;
 *  - variant B (append(ByteBuffer), the production overload) with the same buffer, the entry built once into a heap
 *    ByteBuffer (B2e step 4, as filed) and, supplementary, variant D: the entry as a direct slice of a real HintsBuffer
 *    slab, copied to a direct buffer (what HintsWriteExecutor.flushInternal passes is a direct slice);
 *  - variant H64: append(Hint) with a 64 KiB direct buffer, S = 100 KiB (B2e step 3);
 *  - every (variant, S) twice (rep 1, 2; B2h);
 *  - positive control (B2h): HintsBuffer.create(1 MiB).allocate(400 KiB) as filed (cannot throw: below 512 KiB, results
 *    §3 D1), allocate(600 KiB) must throw, allocate(100 KiB) must not, and the pair capacity/2 - 12 (admitted) / +1
 *    (refused); 400 and 600 KiB hints also go through the 256 KiB write buffer.
 * Per measured append: the calling thread's allocated bytes around the call (ThreadMXBean), buffer.remaining() after,
 * the file length after. Per (variant, S, rep): bytesWritten, file length after close, a read-back with HintsReader
 * (count and serialized size of every hint), the JVM direct pool before/after (reported only).
 * Output: "STAGE4 append ..." per measured append, "STAGE4 case ..." per (variant, S, rep), "STAGE4 check <name>
 * expected=... actual=... ok|MISMATCH" per check; also to -Dstage4.out if set. The test records every mismatch and goes
 * on; it fails at the end only on an instrument or set-up error (the readings are judged in the results file).
 */
package org.apache.cassandra.hints;

import java.io.FileWriter;
import java.io.IOException;
import java.io.PrintWriter;
import java.lang.management.BufferPoolMXBean;
import java.lang.management.ManagementFactory;
import java.nio.ByteBuffer;
import java.nio.file.Files;
import java.util.ArrayList;
import java.util.Collections;
import java.util.Iterator;
import java.util.List;
import java.util.Random;
import java.util.UUID;

import org.junit.AfterClass;
import org.junit.Assert;
import org.junit.BeforeClass;
import org.junit.Test;

import org.apache.cassandra.SchemaLoader;
import org.apache.cassandra.cql3.statements.schema.CreateTableStatement;
import org.apache.cassandra.db.Mutation;
import org.apache.cassandra.db.RowUpdateBuilder;
import org.apache.cassandra.io.util.File;
import org.apache.cassandra.io.util.FileUtils;
import org.apache.cassandra.net.MessagingService;
import org.apache.cassandra.schema.KeyspaceParams;
import org.apache.cassandra.schema.TableMetadata;

public class WriteBufferProbeTest
{
    static final int KIB = 1024, MIB = 1 << 20;
    static final int WARMUP = 20;
    static final int SMALL_BAND = 8 * KIB;          // B2f: "< 8 KiB" per append for S <= 255 KiB and for append(ByteBuffer)
    static final int[] SIZES = { KIB, 100 * KIB, 255 * KIB, 257 * KIB, MIB, 4 * MIB, 15 * MIB };

    static TableMetadata tbm;
    static PrintWriter out;
    static File dir;
    static int mismatches = 0, checks = 0, errors = 0;
    static final com.sun.management.ThreadMXBean TMX = (com.sun.management.ThreadMXBean) ManagementFactory.getThreadMXBean();
    static final BufferPoolMXBean DIRECT = ManagementFactory.getPlatformMXBeans(BufferPoolMXBean.class).stream()
                                                           .filter(b -> b.getName().equals("direct")).findFirst().get();

    @BeforeClass
    public static void setUp() throws Exception
    {
        SchemaLoader.prepareServer();
        tbm = CreateTableStatement.parse("CREATE TABLE t (k int PRIMARY KEY, v blob)", "ks").build();
        SchemaLoader.createKeyspace("ks", KeyspaceParams.simple(1), tbm);
        String o = System.getProperty("stage4.out");
        out = o == null ? null : new PrintWriter(new FileWriter(o, true), true);
        dir = new File(Files.createTempDirectory("stage4-wbs"));
        say("STAGE4 info WRITE_BUFFER_SIZE=" + HintsWriteExecutor.WRITE_BUFFER_SIZE + " ENTRY_OVERHEAD_SIZE=" + HintsBuffer.ENTRY_OVERHEAD_SIZE
            + " maxMemory=" + Runtime.getRuntime().maxMemory() + " messagingVersion=" + MessagingService.current_version
            + " threadAllocMeasurement=" + TMX.isThreadAllocatedMemoryEnabled() + " dir=" + dir.path());
        Assert.assertTrue(TMX.isThreadAllocatedMemorySupported() && TMX.isThreadAllocatedMemoryEnabled());
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

    static long alloc()
    {
        return TMX.getThreadAllocatedBytes(Thread.currentThread().getId());
    }

    static Hint hintOf(int s, int key)
    {
        byte[] v = new byte[s];
        new Random(s + 31L * key).nextBytes(v);
        Mutation m = new RowUpdateBuilder(tbm, System.currentTimeMillis() * 1000, key).add("v", ByteBuffer.wrap(v)).build();
        return Hint.create(m, System.currentTimeMillis());
    }

    static int hintSize(Hint h)
    {
        return (int) Hint.serializer.serializedSize(h, MessagingService.current_version);
    }

    /** the entry (size, crc, hint, crc) as HintsBuffer.Allocation.write lays it out in a real slab; returned as a direct copy of that slice */
    static ByteBuffer slabEntry(HintsBuffer slab, UUID host, Hint h)
    {
        try (HintsBuffer.Allocation a = slab.allocate(hintSize(h)))
        {
            a.write(Collections.singleton(host), h);
        }
        Iterator<ByteBuffer> it = slab.consumingHintsIterator(host);
        ByteBuffer e = it.next();
        ByteBuffer copy = ByteBuffer.allocateDirect(e.remaining());
        copy.put(e.duplicate()).flip();
        return copy;
    }

    /**
     * One (variant, S, rep): appends WARMUP + n entries to a new hints file; measures the n after the warm-up.
     * variant: H (append(Hint)), B (append(heap ByteBuffer)), D (append(direct slice)); buffer is the session buffer.
     */
    static void runCase(String variant, int s, int rep, ByteBuffer buffer) throws IOException
    {
        String tag = variant + (buffer.capacity() == HintsWriteExecutor.WRITE_BUFFER_SIZE ? "" : "-buf" + buffer.capacity()) + " S=" + s + " rep=" + rep;
        Hint hint = hintOf(s, rep);
        int hs = hintSize(hint);
        int total = hs + HintsBuffer.ENTRY_OVERHEAD_SIZE;
        int n = s <= 255 * KIB ? 64 : 8;
        UUID host = UUID.randomUUID();
        ByteBuffer entry = null;
        HintsBuffer slab = null;
        if (!variant.equals("H"))
        {
            slab = HintsBuffer.create(Math.max(32 * MIB, 4 * total));
            ByteBuffer d = slabEntry(slab, host, hint);
            if (variant.equals("B"))
            {
                entry = ByteBuffer.allocate(d.remaining());
                entry.put(d.duplicate()).flip();
            }
            else
                entry = d;
            slab.free();
        }
        long directBefore = DIRECT.getMemoryUsed(), directCountBefore = DIRECT.getCount();
        HintsDescriptor desc = new HintsDescriptor(host, System.currentTimeMillis());
        List<long[]> rows = new ArrayList<>();
        long header, bytesWritten, fileAfterClose;
        File file;
        int cap = buffer.capacity();
        try (HintsWriter w = HintsWriter.create(dir, desc))
        {
            file = w.getFile();
            header = file.length();
            try (HintsWriter.Session session = w.newSession(buffer))
            {
                for (int i = 0; i < WARMUP + n; i++)
                {
                    ByteBuffer e = entry == null ? null : entry.duplicate();
                    long a0 = alloc();
                    if (e == null)
                        session.append(hint);
                    else
                        session.append(e);
                    long a1 = alloc();
                    if (i >= WARMUP)
                        rows.add(new long[]{ i - WARMUP, a1 - a0, buffer.remaining(), file.length(), buffer.capacity() });
                }
                bytesWritten = session.getBytesWritten();
            }
        }
        fileAfterClose = file.length();
        long directAfter = DIRECT.getMemoryUsed(), directCountAfter = DIRECT.getCount();
        // read-back (B2e step 5)
        int readCount = 0, readBadSize = 0;
        try (HintsReader r = HintsReader.open(file))
        {
            for (HintsReader.Page p : r)
            {
                Iterator<Hint> it = p.hintsIterator();
                while (it.hasNext())
                {
                    Hint h = it.next();
                    readCount++;
                    if (hintSize(h) != hs)
                        readBadSize++;
                }
            }
        }
        long minA = Long.MAX_VALUE, maxA = Long.MIN_VALUE, sumA = 0, flushes = 0, lastLen = -1;
        boolean capOk = true, remOk = true;
        long expectRem = -1;
        for (long[] row : rows)
        {
            say("STAGE4 append " + tag + " i=" + row[0] + " alloc=" + row[1] + " remaining=" + row[2] + " fileLen=" + row[3]);
            minA = Math.min(minA, row[1]);
            maxA = Math.max(maxA, row[1]);
            sumA += row[1];
            if (lastLen >= 0 && row[3] != lastLen)
                flushes++;
            lastLen = row[3];
            capOk &= row[4] == cap;
            // remaining after an append: the entry went into the buffer (prev - total, or cap - total after a flush)
            // or, if it can never fit, the buffer was flushed and left empty (cap)
            if (total > cap)
                remOk &= row[2] == cap;
            else
            {
                if (expectRem >= 0)
                {
                    long want = total <= expectRem ? expectRem - total : cap - total;
                    remOk &= row[2] == want;
                }
                expectRem = row[2];
            }
        }
        int count = WARMUP + n;
        say("STAGE4 case " + tag + " hintSize=" + hs + " totalSize=" + total + " n=" + n + " warmup=" + WARMUP
            + " allocMin=" + minA + " allocMedian=" + median(rows) + " allocMax=" + maxA + " allocMean=" + (sumA / Math.max(1, rows.size()))
            + " capacity=" + cap + " fileGrowthEvents=" + flushes + " bytesWritten=" + bytesWritten + " header=" + header
            + " fileAfterClose=" + fileAfterClose + " readBack=" + readCount + " readBadSize=" + readBadSize
            + " directUsedDelta=" + (directAfter - directBefore) + " directCountDelta=" + (directCountAfter - directCountBefore));

        String c = tag.replace(' ', '_');
        // written in full, nothing refused or truncated (B2f, all S; claim wrong if file bytes < sum of entries)
        check(c + "_bytesWritten", (long) count * total, bytesWritten, bytesWritten == (long) count * total);
        check(c + "_fileLen", header + (long) count * total, fileAfterClose, fileAfterClose == header + (long) count * total);
        check(c + "_readBack", count + " hints of " + hs, readCount + " (" + readBadSize + " bad size)", readCount == count && readBadSize == 0);
        check(c + "_capacity", cap, capOk ? cap : "changed", capOk);
        check(c + "_remaining", total > cap ? "cap after each append" : "drops by totalSize, resets after a flush", remOk ? "as expected" : "differs", remOk);
        boolean overflow = total > cap;
        if (variant.equals("H") && overflow)
            check(c + "_allocAtLeastS+12", ">=" + (s + 12), minA, minA >= s + 12);
        else if (variant.equals("H"))
            check(c + "_allocBelow8KiB", "<" + SMALL_BAND, maxA, maxA < SMALL_BAND);
        else if (variant.equals("B"))
            check(c + "_allocBelow8KiB", "<" + SMALL_BAND, maxA, maxA < SMALL_BAND);
        else
            say("STAGE4 info " + c + " (supplementary, direct slice) allocMax=" + maxA);
    }

    static long median(List<long[]> rows)
    {
        long[] a = rows.stream().mapToLong(r -> r[1]).sorted().toArray();
        return a.length == 0 ? -1 : a[a.length / 2];
    }

    static void guarded(String what, Runnable r)
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

    static Runnable io(IORun r)
    {
        return () -> { try { r.run(); } catch (IOException e) { throw new RuntimeException(e); } };
    }

    @Test
    public void probe()
    {
        ByteBuffer buf256 = ByteBuffer.allocateDirect(HintsWriteExecutor.WRITE_BUFFER_SIZE);
        ByteBuffer buf64 = ByteBuffer.allocateDirect(64 << 10);
        for (int rep = 1; rep <= 2; rep++)
        {
            final int r = rep;
            for (int s : SIZES)
                guarded("H " + s, io(() -> runCase("H", s, r, buf256)));
            guarded("H64", io(() -> runCase("H", 100 * KIB, r, buf64)));
            for (int s : SIZES)
                guarded("B " + s, io(() -> runCase("B", s, r, buf256)));
            for (int s : SIZES)
                guarded("D " + s, io(() -> runCase("D", s, r, buf256)));
            // control sizes through the same write buffer (B2h: "the same sizes pass through the 256 KiB write buffer")
            guarded("H 400k", io(() -> runCase("H", 400 * KIB, r, buf256)));
            guarded("H 600k", io(() -> runCase("H", 600 * KIB, r, buf256)));
        }
        guarded("control", WriteBufferProbeTest::control);
        Assert.assertEquals("instrument or set-up errors (see STAGE4 error lines)", 0, errors);
    }

    /** B2h positive control: a binding limit, HintsBuffer.allocate at slab.capacity()/2 */
    static void control()
    {
        HintsBuffer b = HintsBuffer.create(1 << 20);
        try
        {
            String msg = null;
            try (HintsBuffer.Allocation a = b.allocate(400 * KIB))
            {
                msg = "no exception";
            }
            catch (IllegalArgumentException e)
            {
                msg = e.getMessage();
            }
            // as filed in B2h; 400 KiB + 12 = 409,612 B is below capacity/2 = 524,288 B, so this check cannot pass (results §3, D1)
            check("control_allocate_400KiB_refused(filed)", "IllegalArgumentException ... maximum size is 524288", msg,
                  msg != null && msg.contains("too large") && msg.contains("524288"));
            String msg6;
            try (HintsBuffer.Allocation a = b.allocate(600 * KIB))
            {
                msg6 = "no exception";
            }
            catch (IllegalArgumentException e)
            {
                msg6 = e.getMessage();
            }
            check("control_allocate_600KiB_refused", "IllegalArgumentException ... maximum size is 524288", msg6,
                  msg6 != null && msg6.contains("too large") && msg6.contains("524288"));
            String ok;
            try (HintsBuffer.Allocation a = b.allocate(100 * KIB))
            {
                ok = "allocated";
            }
            catch (Throwable t)
            {
                ok = t.toString();
            }
            check("control_allocate_100KiB_admitted", "allocated", ok, ok.equals("allocated"));
            String edge;
            try (HintsBuffer.Allocation a = b.allocate(524288 - HintsBuffer.ENTRY_OVERHEAD_SIZE))
            {
                edge = "allocated";
            }
            catch (Throwable t)
            {
                edge = t.toString();
            }
            check("control_allocate_at_capacity/2_admitted", "allocated", edge, edge.equals("allocated"));
            String over;
            try (HintsBuffer.Allocation a = b.allocate(524288 - HintsBuffer.ENTRY_OVERHEAD_SIZE + 1))
            {
                over = "allocated";
            }
            catch (IllegalArgumentException e)
            {
                over = "refused";
            }
            check("control_allocate_at_capacity/2+1_refused", "refused", over, over.equals("refused"));
        }
        finally
        {
            b.free();
        }
    }
}
