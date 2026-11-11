/*
 * Stage-4 harness, unit tier, for batch_size_warn_threshold-verifyBatchSize-size--autonomous (B2 as amended A1-A4,
 * 2026-10-26). Copy into test/unit/org/apache/cassandra/transport/ of a cassandra-5.0.9 tree together with
 * WarnBatches.java, and run with the Byteman agent, warn-size.btm and stage4.Alloc on the boot class path (unit-run.sh).
 *
 * CQLTester's in-process native server, one protocol-v4 SimpleClient connection (A1: CQLTester.execute would take
 * BatchStatement.executeLocally, which never calls verifyBatchSize). A fresh table per arm (B2h). 20 batches per arm.
 * Arms (fail threshold 100000 KiB unless stated; batches LOGGED, 1 KiB values):
 *   w<W>-p20, w<W>-p200  W in {1, 5, 1024, 65536} KiB: 20 and 200 partitions (about 20 KiB and 200 KiB of data)
 *   sp-w1                warn 1 KiB, one partition with 20 rows (the :334 early return control)
 *   fc                   warn 5 KiB, fail 10 KiB, 20 partitions: the fail control (A4), expected rejected, 0 rows
 *   inv                  warn 200 KiB, fail 10 KiB, 20 partitions: the inversion arm (A3), expected accepted
 * Each arm prints, between "arm <name> begin" and "end" lines, the WarnBatches req lines, then
 * "STAGE4 rows arm=<name> count=<n>" (SELECT count(*) of the arm's table), and "STAGE4 heap arm=<name> before=<b> after=<b>"
 * (used heap after System.gc(), information only). The instrument known-answer check runs first. The test fails only on
 * an instrument or set-up error; the readings are judged by analyze.py and the results file.
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
import org.apache.cassandra.cql3.statements.BatchStatement;
import org.apache.cassandra.transport.messages.ResultMessage;

public class BatchWarnProbeTest extends CQLTester
{
    static final long KiB = 1024, MiB = 1024 * KiB;
    static final int COUNT = Integer.getInteger("stage4.count", 20), VALUE = 1024, FAIL_MAIN = 100000;
    static PrintStream out;
    static String trace;
    static int savedWarn, savedFail;

    static class Tee extends PrintStream
    {
        Tee(PrintStream a) { super(a, true); }
        @Override public void println(String s) { System.out.println(s); super.println(s); }
    }

    @BeforeClass
    public static void setUp() throws IOException
    {
        String f = System.getProperty("stage4.out", "build/test/batch-warn.out");
        out = new Tee(new PrintStream(new FileOutputStream(f, true), true));
        trace = System.getProperty("stage4.byteman.out");
        savedWarn = DatabaseDescriptor.getBatchSizeWarnThresholdInKiB();
        savedFail = DatabaseDescriptor.getBatchSizeFailThresholdInKiB();
        requireNetwork();
    }

    @AfterClass
    public static void tearDown()
    {
        DatabaseDescriptor.setBatchSizeWarnThresholdInKiB(savedWarn);
        DatabaseDescriptor.setBatchSizeFailThresholdInKiB(savedFail);
        if (out != null) out.close();
    }

    static long usedHeap()
    {
        System.gc();
        Runtime r = Runtime.getRuntime();
        return r.totalMemory() - r.freeMemory();
    }

    void arm(SimpleClient client, String name, int warnKiB, int failKiB, int partitions, int rows) throws Throwable
    {
        // set the fail threshold first: the setter order is irrelevant, each is its own volatile field
        DatabaseDescriptor.setBatchSizeFailThresholdInKiB(failKiB);
        DatabaseDescriptor.setBatchSizeWarnThresholdInKiB(warnKiB);
        String table = createTable("CREATE TABLE %s (k int, c int, v blob, PRIMARY KEY (k, c))");
        ResultMessage.Prepared prepared = WarnBatches.prepare(client, KEYSPACE, table);
        out.println("STAGE4 arm " + name + " knobs warn_kib=" + DatabaseDescriptor.getBatchSizeWarnThresholdInKiB()
                    + " warn_bytes=" + DatabaseDescriptor.getBatchSizeWarnThreshold()
                    + " fail_kib=" + DatabaseDescriptor.getBatchSizeFailThresholdInKiB()
                    + " fail_bytes=" + DatabaseDescriptor.getBatchSizeFailThreshold());
        long before = usedHeap();
        WarnBatches.run(client, prepared, name, BatchStatement.Type.LOGGED, partitions, rows, VALUE, COUNT, 0, out);
        long after = usedHeap();
        long n = execute("SELECT count(*) FROM %s").one().getLong("count");
        out.println("STAGE4 rows arm=" + name + " count=" + n);
        out.println("STAGE4 heap arm=" + name + " before=" + before + " after=" + after);
    }

    @Test
    public void warnThreshold() throws Throwable
    {
        Assert.assertNotNull("-Dstage4.byteman.out must name the Byteman trace", trace);

        // instrument known-answer check: stage4.Alloc around a known allocation
        stage4.Alloc.start("chk");
        byte[] b = new byte[(int) (8 * MiB)];
        stage4.Alloc.end("chk", "len=" + b.length);
        List<String> chk = java.nio.file.Files.readAllLines(java.nio.file.Paths.get(trace));
        long got = chk.stream().filter(l -> l.startsWith("chk ")).mapToLong(l -> Long.parseLong(l.replaceFirst(".*bytes=(-?\\d+).*", "$1"))).findFirst().orElse(-1);
        boolean ok = got >= 8 * MiB && got <= 8 * MiB + 64 * KiB;
        out.println("STAGE4 check alloc-known-answer expected=[8388608,8454144] actual=" + got + (ok ? " ok" : " MISMATCH"));
        Assert.assertTrue("Alloc known-answer check", ok);

        try (SimpleClient client = SimpleClient.builder(nativeAddr.getHostAddress(), nativePort)
                                               .protocolVersion(ProtocolVersion.V4).build().connect(false))
        {
            out.println("STAGE4 info protocol=" + client.connection.getVersion() + " heap_max=" + Runtime.getRuntime().maxMemory());
            // warm-up (not analysed): the first requests in a JVM carry one-off allocation and JIT work
            arm(client, "warm20", 5, FAIL_MAIN, 20, 1);
            arm(client, "warm200", 5, FAIL_MAIN, 200, 1);
            arm(client, "warm20b", 1024, FAIL_MAIN, 20, 1);
            for (int w : new int[]{ 1, 5, 1024, 65536 })
            {
                arm(client, "w" + w + "-p20", w, FAIL_MAIN, 20, 1);
                arm(client, "w" + w + "-p200", w, FAIL_MAIN, 200, 1);
            }
            arm(client, "sp-w1", 1, FAIL_MAIN, 1, 20);
            arm(client, "fc", 5, 10, 20, 1);
            arm(client, "inv", 200, 10, 20, 1);
        }
    }
}
