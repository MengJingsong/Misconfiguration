/*
 * Stage-4 harness, unit tier, for max_hints_file_size-HintsWriteExecutor.flushInternal-session.position--autonomous
 * (case B2a-B2h as amended 2026-10-26). Copy into test/unit/org/apache/cassandra/hints/ of a cassandra-5.0.9 tree.
 * Package hints because Hint.serializer, HintsBuffer.ENTRY_OVERHEAD_SIZE and the descriptor are package-private.
 *
 * Real hints go through HintsService.instance.write() and are flushed with flushAndFsyncBlockingly(), so every file is
 * written by HintsWriteExecutor.flushInternal (the :247 comparison). Per run: a fresh fake host id, the knob set on the
 * raw config before the first hint, 64 MiB of 16 KiB hints (or 64 MiB of 1 KiB hints), then the host's files are read.
 *
 * Output (to the file named by -Dstage4.out, else stdout):
 *   STAGE4 value <name>=<v>
 *   STAGE4 run <key=value ...>          one per run, the readings
 *   STAGE4 check <name> expected=<e> actual=<a> ok|MISMATCH
 *   STAGE4 summary checks=<n> mismatches=<n>
 * The test fails at the end if any check mismatched. The checks restate the amended B2f relations; they are not the
 * verdict, which is read from the logs by the self-check.
 */
package org.apache.cassandra.hints;

import java.io.FileOutputStream;
import java.io.PrintStream;
import java.lang.management.BufferPoolMXBean;
import java.lang.management.ManagementFactory;
import java.net.UnknownHostException;
import java.nio.ByteBuffer;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Collections;
import java.util.List;
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

public class HintsFileSizeLimitTest
{
    private static final String KS = "mh_unit";
    private static final String TABLE = "t";
    private static final long MIB = 1024L * 1024L;
    private static final int ENTRY_OVERHEAD = HintsBuffer.ENTRY_OVERHEAD_SIZE;
    private static final long TOTAL_PAYLOAD = 64 * MIB;

    private static TableMetadata metadata;
    private static PrintStream out;
    private static int checks = 0;
    private static int mismatches = 0;

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
        check("default max_hints_file_size bytes", 128 * MIB, DatabaseDescriptor.getMaxHintsFileSize());
        check("default max_hints_size_per_host bytes", 0L, DatabaseDescriptor.getMaxHintsSizePerHost());
        check("hints compression off", true, DatabaseDescriptor.getHintsCompression() == null);
        check("hints encryption off", true, !DatabaseDescriptor.getEncryptionContext().isEnabled());
    }

    @AfterClass
    public static void tearDown()
    {
        DatabaseDescriptor.setMaxHintsSizePerHostInMiB(0);
        DatabaseDescriptor.getRawConfig().max_hints_file_size = new DataStorageSpec.IntMebibytesBound(128);
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

    private static Hint hint(int seq, int payload)
    {
        byte[] v = new byte[payload];
        ThreadLocalRandom.current().nextBytes(v);
        Mutation m = new RowUpdateBuilder(metadata, System.currentTimeMillis(), String.format("k%06d", seq))
                     .clustering("c").add("val", ByteBuffer.wrap(v)).build();
        return Hint.create(m, System.currentTimeMillis());
    }

    private static long entrySize(Hint h)
    {
        return Hint.serializer.serializedSize(h, MessagingService.current_version) + ENTRY_OVERHEAD;
    }

    /** The host's .hints files, oldest first (the name carries the creation timestamp). */
    private static List<File> files(UUID hostId)
    {
        List<File> r = new ArrayList<>();
        for (File f : DatabaseDescriptor.getHintsDirectory().tryList())
            if (f.name().startsWith(hostId.toString()) && f.name().endsWith(".hints"))
                r.add(f);
        r.sort((a, b) -> a.name().compareTo(b.name()));
        return r;
    }

    private static void flush(UUID hostId)
    {
        HintsService.instance.flushAndFsyncBlockingly(Collections.singleton(hostId));
    }

    private static long directUsed()
    {
        for (BufferPoolMXBean b : ManagementFactory.getPlatformMXBeans(BufferPoolMXBean.class))
            if (b.getName().equals("direct"))
                return b.getMemoryUsed();
        throw new IllegalStateException("no direct pool");
    }

    private static void setLimit(long mib)
    {
        DatabaseDescriptor.getRawConfig().max_hints_file_size = new DataStorageSpec.IntMebibytesBound(mib);
        check("knob read back MiB=" + mib, mib * MIB, DatabaseDescriptor.getMaxHintsFileSize());
    }

    // ------------------------------------------------------------------ one run

    /** @return {sum of lengths, file count, memory delta} */
    private static long[] run(String name, boolean counted, long limitMib, int hints, int payload) throws Exception
    {
        setLimit(limitMib);
        UUID hostId = UUID.randomUUID();
        long L = limitMib * MIB;
        long e = entrySize(hint(0, payload));
        long nominalPerFile = (L + e - 1) / e;                    // h ~ 0
        long nominalFiles = (hints + nominalPerFile - 1) / nominalPerFile;
        out.println("STAGE4 predict name=" + name + " host=" + hostId + " L=" + L + " e=" + e + " hints=" + hints
                    + " nominalFiles=" + nominalFiles);
        long before = directUsed();
        for (int i = 0; i < hints; i++)
            HintsService.instance.write(hostId, hint(i, payload));
        flush(hostId);
        long after = directUsed();

        List<File> fs = files(hostId);
        long sum = 0, min = Long.MAX_VALUE, max = 0;
        int geL = 0;
        List<Long> closed = new ArrayList<>();
        for (int i = 0; i < fs.size(); i++)
        {
            long len = fs.get(i).length();
            sum += len;
            if (len >= L)
                geL++;
            if (i < fs.size() - 1)
            {
                closed.add(len);
                min = Math.min(min, len);
                max = Math.max(max, len);
            }
        }
        long last = fs.get(fs.size() - 1).length();
        long operand = HintsService.instance.getTotalHintsSize(hostId);
        long nLo = (sum + (L + e) - 1) / (L + e);
        long nHi = sum / L + 1;
        out.println("STAGE4 run name=" + name + " counted=" + counted + " host=" + hostId + " L=" + L + " hints=" + hints
                    + " payload=" + payload + " e=" + e + " T=" + sum + " operand=" + operand + " files=" + fs.size()
                    + " filesGeL=" + geL + " closedMin=" + (closed.isEmpty() ? -1 : min) + " closedMax=" + (closed.isEmpty() ? -1 : max)
                    + " last=" + last + " nLo=" + nLo + " nHi=" + nHi + " nominalFiles=" + nominalFiles
                    + " directBefore=" + before + " directAfter=" + after + " directDelta=" + (after - before));
        check(name + " operand == sum(File.length)", sum, operand);
        check(name + " files in [T/(L+e), T/L+1]", true, fs.size() >= nLo && fs.size() <= nHi);
        check(name + " files within nominal +-1", true, Math.abs(fs.size() - nominalFiles) <= 1);
        boolean allClosedInRange = true;
        for (long len : closed)
            allClosedInRange &= len >= L && len < L + e;
        check(name + " every closed file in [L, L+e)", true, allClosedInRange);
        check(name + " last file < L+e", true, last < L + e);
        if (counted)   // the excluded warm-up allocates the service's slabs (B2d)
            check(name + " direct delta within 1 MiB", true, Math.abs(after - before) <= MIB);
        // leave the files for the self-check; remove them only through the stores at the end of the class
        HintsService.instance.excise(hostId);
        return new long[]{ sum, fs.size(), after - before };
    }

    // ------------------------------------------------------------------ steps

    @Test
    public void sweepAndControl() throws Exception
    {
        int n16 = (int) (TOTAL_PAYLOAD / (16 * 1024));      // 4096
        int n1 = (int) (TOTAL_PAYLOAD / 1024);              // 65536
        run("warmup L=128", false, 128, n16, 16 * 1024);    // excluded: allocates the service's slabs

        long[] ls = { 1, 4, 16, 128 };
        long[][][] res = new long[3][ls.length][];
        for (int rep = 0; rep < 3; rep++)
            for (int i = 0; i < ls.length; i++)
                res[rep][i] = run("rep" + rep + " L=" + ls[i], true, ls[i], n16, 16 * 1024);

        // totals equal across L within 0.1%, memory spread within 1 MiB
        long ref = res[0][3][0];
        long dmin = Long.MAX_VALUE, dmax = Long.MIN_VALUE;
        boolean totalsEqual = true;
        for (int rep = 0; rep < 3; rep++)
            for (int i = 0; i < ls.length; i++)
            {
                totalsEqual &= Math.abs(res[rep][i][0] - ref) <= ref / 1000;
                dmin = Math.min(dmin, res[rep][i][2]);
                dmax = Math.max(dmax, res[rep][i][2]);
            }
        value("direct delta min", dmin);
        value("direct delta max", dmax);
        check("totals across L and reps equal within 0.1%", true, totalsEqual);
        check("direct delta spread across all runs within 1 MiB", true, dmax - dmin <= MIB);

        run("small-hints L=1", true, 1, n1, 1024);

        control();
    }

    /** B2h as amended: the real StorageProxy.shouldHint with max_hints_size_per_host = 16 MiB, file limit at its default. */
    private void control() throws Exception
    {
        setLimit(128);
        UUID hostId = UUID.randomUUID();
        Replica r = deadReplica("192.168.11.9", hostId);
        long cap = 16 * MIB;
        DatabaseDescriptor.setMaxHintsSizePerHostInMiB(16);
        try
        {
            check("control cap bytes", cap, DatabaseDescriptor.getMaxHintsSizePerHost());
            long e = entrySize(hint(0, 16 * 1024));
            long batch = 64 * e;
            int seq = 0, batches = 0;
            boolean refused = false;
            long t = 0;
            while (batches < 200)
            {
                if (!StorageProxy.shouldHint(r))
                {
                    refused = true;
                    break;
                }
                for (int i = 0; i < 64; i++)
                    HintsService.instance.write(hostId, hint(seq++, 16 * 1024));
                flush(hostId);
                batches++;
                t = HintsService.instance.getTotalHintsSize(hostId);
            }
            out.println("STAGE4 control host=" + hostId + " cap=" + cap + " e=" + e + " batchBytes=" + batch
                        + " batches=" + batches + " refused=" + refused + " Tstop=" + t + " files=" + files(hostId).size());
            check("control refused before 200 batches", true, refused);
            check("control T_stop > cap", true, t > cap);
            check("control T_stop <= cap + one batch + 200 B header slack", true, t <= cap + batch + 200);
            // no growth once refused: 20 more attempts write nothing
            int wrote = 0;
            for (int i = 0; i < 20; i++)
                if (StorageProxy.shouldHint(r))
                    wrote++;
            check("control stays refused (20 more checks)", 0, wrote);
            check("control T unchanged after refusals", t, HintsService.instance.getTotalHintsSize(hostId));
            // same cap lifted: allowed again, the same files
            DatabaseDescriptor.setMaxHintsSizePerHostInMiB(0);
            check("control allowed again at cap 0", true, StorageProxy.shouldHint(r));
        }
        finally
        {
            DatabaseDescriptor.setMaxHintsSizePerHostInMiB(0);
            HintsService.instance.excise(hostId);
        }
    }
}
