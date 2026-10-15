/*
 * Stage-4 harness, unit tier, for max_hints_size_per_host-shouldHint-maxHintsSize (case 9e unit steps 1-6, amended
 * 2026-10-14). Copy into test/unit/org/apache/cassandra/hints/ of a cassandra-5.0.9 clone. In package hints rather than
 * service (9c) because Hint.Serializer and HintsBuffer.ENTRY_OVERHEAD_SIZE are package-private; StorageProxy is public.
 *
 * StorageProxy.shouldHint() with the REAL operand: hints written through HintsService.instance.write() and flushed with
 * flushAndFsyncBlockingly(), so getTotalHintsSize() is the size of real hint files. Fake endpoints with host ids, marked
 * dead, as in upstream StorageProxyTest.shouldHintTest(). Each step uses its own endpoint and host id.
 *
 * Prints "STAGE4 check <name> expected=<e> actual=<a> ok|MISMATCH" and "STAGE4 value <name>=<v>" to the file named by
 * -Dstage4.out (else stdout); fails at the end if any check mismatched.
 */
package org.apache.cassandra.hints;

import java.io.FileOutputStream;
import java.io.PrintStream;
import java.net.UnknownHostException;
import java.nio.ByteBuffer;
import java.util.Collections;
import java.util.UUID;
import java.util.concurrent.ThreadLocalRandom;

import org.junit.AfterClass;
import org.junit.Assert;
import org.junit.BeforeClass;
import org.junit.Test;

import org.apache.cassandra.SchemaLoader;
import org.apache.cassandra.config.DataStorageSpec;
import org.apache.cassandra.config.DatabaseDescriptor;
import org.apache.cassandra.db.Mutation;
import org.apache.cassandra.db.RowUpdateBuilder;
import org.apache.cassandra.db.marshal.AsciiType;
import org.apache.cassandra.db.marshal.BytesType;
import org.apache.cassandra.gms.EndpointState;
import org.apache.cassandra.gms.Gossiper;
import org.apache.cassandra.gms.HeartBeatState;
import org.apache.cassandra.io.util.File;
import org.apache.cassandra.locator.InetAddressAndPort;
import org.apache.cassandra.locator.Replica;
import org.apache.cassandra.net.MessagingService;
import org.apache.cassandra.schema.KeyspaceParams;
import org.apache.cassandra.schema.Schema;
import org.apache.cassandra.schema.TableMetadata;
import org.apache.cassandra.service.StorageProxy;
import org.apache.cassandra.service.StorageService;

import static org.apache.cassandra.locator.ReplicaUtils.full;

public class ShouldHintSizeTest
{
    private static final String KS = "mhs_unit";
    private static final String TABLE = "t";
    private static final long MIB = 1024L * 1024L;
    /** Size int, size CRC, hint CRC per entry. */
    private static final int ENTRY_OVERHEAD = HintsBuffer.ENTRY_OVERHEAD_SIZE;

    private static TableMetadata metadata;
    private static PrintStream out;
    private static int checks = 0;
    private static int mismatches = 0;
    private static int keySeq = 0;

    @BeforeClass
    public static void setUp() throws Exception
    {
        SchemaLoader.prepareServer();
        SchemaLoader.createKeyspace(KS, KeyspaceParams.simple(1),
                                    SchemaLoader.standardCFMD(KS, TABLE, 0, AsciiType.instance, BytesType.instance));
        metadata = Schema.instance.getTableMetadata(KS, TABLE);
        DatabaseDescriptor.setMaxHintWindow(24 * 3600 * 1000);
        String f = System.getProperty("stage4.out");
        out = f == null ? System.out : new PrintStream(new FileOutputStream(f, true), true);
        value("hintsDirectory", DatabaseDescriptor.getHintsDirectory().absolutePath());
        value("messagingVersion", MessagingService.current_version);
        value("hintsFlushPeriodMs", DatabaseDescriptor.getHintsFlushPeriodInMS());
        check("default limit bytes", 0L, DatabaseDescriptor.getMaxHintsSizePerHost());
        check("hinted handoff enabled", true, DatabaseDescriptor.hintedHandoffEnabled());
    }

    @AfterClass
    public static void tearDown()
    {
        DatabaseDescriptor.setMaxHintsSizePerHostInMiB(0);
        out.println("STAGE4 summary checks=" + checks + " mismatches=" + mismatches);
        if (out != System.out)
            out.close();
        Assert.assertEquals("STAGE4 mismatches", 0, mismatches);
    }

    // ------------------------------------------------------------------ helpers

    private static void value(String name, Object v)
    {
        out.println("STAGE4 value " + name + "=" + v);
    }

    private static void check(String name, Object expected, Object actual)
    {
        checks++;
        boolean ok = expected.equals(actual);
        if (!ok)
            mismatches++;
        out.println("STAGE4 check " + name + " expected=" + expected + " actual=" + actual + (ok ? " ok" : " MISMATCH"));
    }

    private static Replica deadReplica(String ip, UUID hostId) throws UnknownHostException
    {
        InetAddressAndPort ep = InetAddressAndPort.getByName(ip);
        Replica replica = full(ep);
        StorageService.instance.getTokenMetadata().updateHostId(hostId, ep);
        EndpointState state = new EndpointState(new HeartBeatState(0, 0));
        Gossiper.runInGossipStageBlocking(() -> Gossiper.instance.markDead(replica.endpoint(), state));
        return replica;
    }

    private static Hint hint(int payload)
    {
        return hint(payload, "k" + (keySeq++), true);
    }

    /** A hint for key, payload bytes long (random, or zeros when only its size is needed). */
    private static Hint hint(int payload, String key, boolean random)
    {
        byte[] v = new byte[payload];
        if (random)
            ThreadLocalRandom.current().nextBytes(v);
        Mutation m = new RowUpdateBuilder(metadata, System.currentTimeMillis(), key)
                     .clustering("c").add("val", ByteBuffer.wrap(v)).build();
        return Hint.create(m, System.currentTimeMillis());
    }

    private static long entrySize(Hint h)
    {
        return Hint.serializer.serializedSize(h, MessagingService.current_version) + ENTRY_OVERHEAD;
    }

    /** Sum of File.length() over the host's .hints files in the hints directory. */
    private static long filesLength(UUID hostId)
    {
        long sum = 0;
        for (File f : DatabaseDescriptor.getHintsDirectory().tryList())
        {
            String n = f.name();
            if (n.startsWith(hostId.toString()) && n.endsWith(".hints"))
                sum += f.length();
        }
        return sum;
    }

    private static int filesCount(UUID hostId)
    {
        int c = 0;
        for (File f : DatabaseDescriptor.getHintsDirectory().tryList())
            if (f.name().startsWith(hostId.toString()) && f.name().endsWith(".hints"))
                c++;
        return c;
    }

    private static void flush(UUID hostId)
    {
        HintsService.instance.flushAndFsyncBlockingly(Collections.singleton(hostId));
    }

    private static long total(UUID hostId)
    {
        return HintsService.instance.getTotalHintsSize(hostId);
    }

    /** Step 5, the operand: after a flush getTotalHintsSize equals the files' lengths. */
    private static long flushAndCheckOperand(String step, UUID hostId)
    {
        flush(hostId);
        long t = total(hostId);
        check(step + " operand=sum(File.length)", filesLength(hostId), t);
        return t;
    }

    private static void writeHints(UUID hostId, int n, int payload)
    {
        for (int i = 0; i < n; i++)
            HintsService.instance.write(hostId, hint(payload));
    }

    /** Writes and flushes hints until getTotalHintsSize(hostId) is exactly target, with shouldHint checked true below it. */
    private static long fillExactly(String step, UUID hostId, Replica replica, long target)
    {
        long t = flushAndCheckOperand(step + " start", hostId);
        int flushes = 0;
        while (target - t > 64 * 1024)
        {
            writeHints(hostId, 10, 4096);
            t = flushAndCheckOperand(step + " fill" + (flushes++), hostId);
            if (!StorageProxy.shouldHint(replica))
                check(step + " shouldHint below the limit T=" + t, true, false);
        }
        // the rest: whole hints whose entry sizes add up to exactly target - t. The entry of a payload p is p plus an
        // overhead that depends only on the key and on vint lengths, so search p near d - overhead with the real key.
        while (t < target)
        {
            long d = target - t;
            String key = "k" + (keySeq++);
            long overhead = entrySize(hint(1000, key, false)) - 1000;
            Integer chosen = null;
            for (long p = d - overhead - 16; p <= d - overhead + 16; p++)
                if (p >= 0 && entrySize(hint((int) p, key, false)) == d)
                    chosen = (int) p;
            if (chosen == null)   // a vint boundary skips d: write about half and search again
                chosen = (int) Math.max(0, d / 2 - overhead);
            Hint last = hint(chosen, key, true);
            value(step + " entry", entrySize(last) + " for remaining " + d);
            HintsService.instance.write(hostId, last);
            t = flushAndCheckOperand(step + " exact", hostId);
        }
        return t;
    }

    // ------------------------------------------------------------------ steps

    /** Steps 1, 2 and 4 on one endpoint: 0 allows with 2 MiB on disk, 1 MiB refuses, back to 0 allows again. */
    @Test
    public void steps124() throws Exception
    {
        UUID hostId = UUID.randomUUID();
        Replica r = deadReplica("192.168.11.1", hostId);
        try
        {
            DatabaseDescriptor.setMaxHintsSizePerHostInMiB(0);
            check("1 limit bytes", 0L, DatabaseDescriptor.getMaxHintsSizePerHost());
            check("1 T before any hint", 0L, total(hostId));
            Hint probe = hint(10_240);
            value("1 entry size of a 10240-byte payload", entrySize(probe));
            writeHints(hostId, 205, 10_240);
            long t = flushAndCheckOperand("1", hostId);
            value("1 T", t);
            value("1 files", filesCount(hostId));
            check("1 T above 2 MiB", true, t > 2 * MIB);
            check("1 shouldHint at limit 0", true, StorageProxy.shouldHint(r));
            check("1 shouldHint(false) at limit 0", true, StorageProxy.shouldHint(r, false));

            DatabaseDescriptor.setMaxHintsSizePerHostInMiB(1);
            check("2 limit bytes", MIB, DatabaseDescriptor.getMaxHintsSizePerHost());
            check("2 limit MiB read back", 1, StorageProxy.instance.getMaxHintsSizePerHostInMiB());
            check("2 shouldHint T=" + t + " > 1 MiB", false, StorageProxy.shouldHint(r));
            check("2 shouldHint(false) T > 1 MiB", false, StorageProxy.shouldHint(r, false));

            DatabaseDescriptor.setMaxHintsSizePerHostInMiB(0);
            check("4 shouldHint back at 0, same files", true, StorageProxy.shouldHint(r));
            check("4 T unchanged", t, total(hostId));
        }
        finally
        {
            DatabaseDescriptor.setMaxHintsSizePerHostInMiB(0);
        }
    }

    /** Step 3, the boundary: T == L allows (the comparison is '>'), L = T - 1 refuses, one more hint past L refuses. */
    @Test
    public void step3Boundary() throws Exception
    {
        UUID hostId = UUID.randomUUID();
        Replica r = deadReplica("192.168.11.2", hostId);
        try
        {
            DatabaseDescriptor.setMaxHintsSizePerHostInMiB(1);
            check("3 shouldHint with no files", true, StorageProxy.shouldHint(r));
            long t = fillExactly("3", hostId, r, MIB);
            check("3 T exactly 1 MiB", MIB, t);
            check("3 shouldHint T == L = 1048576", true, StorageProxy.shouldHint(r));

            DatabaseDescriptor.getRawConfig().max_hints_size_per_host = new DataStorageSpec.LongBytesBound(MIB - 1);
            check("3 limit bytes raw", MIB - 1, DatabaseDescriptor.getMaxHintsSizePerHost());
            check("3 shouldHint T == L + 1", false, StorageProxy.shouldHint(r));

            DatabaseDescriptor.setMaxHintsSizePerHostInMiB(1);
            check("3 shouldHint back at T == L", true, StorageProxy.shouldHint(r));
            Hint one = hint(100);
            HintsService.instance.write(hostId, one);
            long t2 = flushAndCheckOperand("3 one more", hostId);
            check("3 one more hint adds its entry", MIB + entrySize(one), t2);
            check("3 shouldHint T = L + one entry", false, StorageProxy.shouldHint(r));
        }
        finally
        {
            DatabaseDescriptor.setMaxHintsSizePerHostInMiB(0);
        }
    }

    /** Step 6, the lag: buffered hints do not move the operand until a flush session closes. */
    @Test
    public void step6FlushLag() throws Exception
    {
        UUID hostId = UUID.randomUUID();
        Replica r = deadReplica("192.168.11.3", hostId);
        try
        {
            DatabaseDescriptor.setMaxHintsSizePerHostInMiB(1);
            long t0 = fillExactly("6", hostId, r, MIB - 100_000);
            check("6 T0", MIB - 100_000, t0);
            long len0 = filesLength(hostId);
            long buffered = 0;
            for (int i = 0; i < 40; i++)
            {
                Hint h = hint(10_240);
                buffered += entrySize(h);
                HintsService.instance.write(hostId, h);
            }
            value("6 buffered bytes", buffered);
            long tBuffered = total(hostId);
            boolean bufferedTrue = StorageProxy.shouldHint(r);
            long len1 = filesLength(hostId);
            value("6 periodic flush intervened", len1 != len0);
            check("6 T unchanged with " + buffered + " B buffered", t0, tBuffered);
            check("6 shouldHint true while T0 + buffered > L", true, bufferedTrue);
            check("6 T0 + buffered above L", true, t0 + buffered > MIB);
            long t1 = flushAndCheckOperand("6 after flush", hostId);
            check("6 T after flush = T0 + buffered", t0 + buffered, t1);
            check("6 shouldHint after flush", false, StorageProxy.shouldHint(r));
            value("6 overshoot past L after the flush", t1 - MIB);
        }
        finally
        {
            DatabaseDescriptor.setMaxHintsSizePerHostInMiB(0);
        }
    }

}
