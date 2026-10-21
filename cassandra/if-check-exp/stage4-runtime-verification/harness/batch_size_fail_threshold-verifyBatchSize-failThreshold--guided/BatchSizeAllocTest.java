/*
 * Stage-4 harness, unit tier, for batch_size_fail_threshold-verifyBatchSize-failThreshold--guided (case 9a Procedure 1
 * as amended by R8, 2026-10-20). Copy into test/unit/org/apache/cassandra/transport/ of a cassandra-5.0.9 clone together
 * with SendBatches.java, and run with the Byteman agent, batch-alloc.btm and stage4.Alloc on the boot class path
 * (unit-run.sh does all of it).
 *
 * CQLTester's in-process server, one protocol-v5 connection. The arms are those of the cluster tier (9e):
 *   ctl16k   threshold 50 KiB, 16 KiB batches (accepted)
 *   A/B      thresholds 50 KiB, 500 KiB, 5 MiB (setBatchSizeFailThresholdInKiB) x batches 1, 4, 16 MiB
 *   C        native_transport_max_message_size 512 KiB, threshold 50 KiB, 16 MiB batches (the transport discards them)
 * native_transport_max_message_size is 64 MiB in every other arm (R1, R8). Each arm prints its SendBatches req lines to
 * stdout and to -Dstage4.out, between "STAGE4 arm <name> begin" and "end" lines. The instrument known-answer check runs
 * first: stage4.Alloc around an 8 MiB byte[] must report 8 MiB to 8 MiB + 64 KiB. The analysis (analyze.py) is shared
 * with the cluster tier; the test itself only fails on an instrument or set-up error.
 */
package org.apache.cassandra.transport;

import java.io.FileOutputStream;
import java.io.IOException;
import java.io.PrintStream;
import java.util.List;

import org.junit.AfterClass;
import org.junit.Assert;
import org.junit.BeforeClass;
import org.junit.Test;

import org.apache.cassandra.config.DatabaseDescriptor;
import org.apache.cassandra.cql3.CQLTester;
import org.apache.cassandra.transport.messages.ResultMessage;

public class BatchSizeAllocTest extends CQLTester
{
    static final long KiB = 1024, MiB = 1024 * KiB;
    static final int PARTITIONS = 64, COUNT = Integer.getInteger("stage4.count", 20);
    static PrintStream out;
    static String trace;
    static long savedMaxMessageSize;
    static int savedFail;

    static class Tee extends PrintStream
    {
        Tee(PrintStream a) { super(a, true); }
        @Override public void println(String s) { System.out.println(s); super.println(s); }
    }

    @BeforeClass
    public static void setUp() throws IOException
    {
        String f = System.getProperty("stage4.out", "build/test/batch-size-alloc.out");
        out = new Tee(new PrintStream(new FileOutputStream(f, true), true));
        trace = System.getProperty("stage4.byteman.out");
        savedMaxMessageSize = DatabaseDescriptor.getNativeTransportMaxMessageSizeInBytes();
        savedFail = DatabaseDescriptor.getBatchSizeFailThresholdInKiB();
        requireNetwork();
    }

    @AfterClass
    public static void tearDown()
    {
        DatabaseDescriptor.setNativeTransportMaxMessageSizeInBytes(savedMaxMessageSize);
        DatabaseDescriptor.setBatchSizeFailThresholdInKiB(savedFail);
        if (out != null) out.close();
    }

    void arm(SimpleClient client, ResultMessage.Prepared prepared, String name, int failKiB, long maxMessage, long bytes) throws Exception
    {
        DatabaseDescriptor.setBatchSizeFailThresholdInKiB(failKiB);
        DatabaseDescriptor.setNativeTransportMaxMessageSizeInBytes(maxMessage);
        out.println("STAGE4 arm " + name + " begin fail_kib=" + DatabaseDescriptor.getBatchSizeFailThresholdInKiB()
                    + " fail_bytes=" + DatabaseDescriptor.getBatchSizeFailThreshold()
                    + " warn_bytes=" + DatabaseDescriptor.getBatchSizeWarnThreshold()
                    + " max_message=" + DatabaseDescriptor.getNativeTransportMaxMessageSizeInBytes()
                    + " in_flight=" + DatabaseDescriptor.getNativeTransportMaxRequestDataInFlightInBytes()
                    + " in_flight_ip=" + DatabaseDescriptor.getNativeTransportMaxRequestDataInFlightPerIpInBytes()
                    + " bytes=" + bytes + " ms=" + System.currentTimeMillis());
        SendBatches.run(client, prepared, trace, name, bytes, PARTITIONS, COUNT, 200, out);
        out.println("STAGE4 arm " + name + " end ms=" + System.currentTimeMillis());
    }

    @Test
    public void batchAllocation() throws Exception
    {
        Assert.assertNotNull("-Dstage4.byteman.out must name the Byteman trace", trace);

        // instrument known-answer check: the helper on the boot class path, around a known allocation
        stage4.Alloc.start("chk");
        byte[] b = new byte[(int) (8 * MiB)];
        stage4.Alloc.end("chk", "len=" + b.length);
        List<String> chk = SendBatches.linesAfter(trace, 0);
        long got = chk.stream().filter(l -> l.startsWith("chk ")).mapToLong(SendBatches::bytesOf).findFirst().orElse(-1);
        boolean ok = got >= 8 * MiB && got <= 8 * MiB + 64 * KiB;
        out.println("STAGE4 check alloc-known-answer expected=[8388608,8454144] actual=" + got + (ok ? " ok" : " MISMATCH"));
        Assert.assertTrue("Alloc known-answer check", ok);

        String table = createTable("CREATE TABLE %s (pk int PRIMARY KEY, v blob)");
        try (SimpleClient client = SimpleClient.builder(nativeAddr.getHostAddress(), nativePort)
                                               .protocolVersion(ProtocolVersion.V5).build().connect(false))
        {
            out.println("STAGE4 info protocol=" + client.connection.getVersion() + " heap_max=" + Runtime.getRuntime().maxMemory());
            ResultMessage.Prepared prepared = SendBatches.prepare(client, KEYSPACE, table);
            long big = 64 * MiB;
            arm(client, prepared, "ctl16k", 50, big, 16 * KiB);
            for (int failKiB : new int[]{ 50, 500, 5120 })
                for (long size : new long[]{ 1 * MiB, 4 * MiB, 16 * MiB })
                    arm(client, prepared, "t" + failKiB + "k-b" + size / MiB + "m", failKiB, big, size);
            arm(client, prepared, "C-msg512k-b16m", 50, 512 * KiB, 16 * MiB);
        }
    }
}
