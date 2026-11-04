/*
 * Stage-4 unit-tier probe (B2, as amended 2026-10-26) of
 * batch_size_fail_threshold-verifyBatchSize-mutations--autonomous.
 * Not upstream. unit-run.sh copies it into test/unit/org/apache/cassandra/cql3/, runs it, and removes it.
 *
 * For F in {50, 100, 200} KiB (warn 1 KiB), B in {10, 24, 26, 60, 98, 102} KiB, shape in {multi, single}:
 *   TRUNCATE; operand = IMutation.dataSize(getMutations(...)) on the same bound values; memtable live data size before;
 *   executeNet (client path -> BatchStatement.execute -> verifyBatchSize); rows and memtable after.
 * One println per reading. Shakedown only: -Dprobe.f=<list> -Dprobe.b=<list> (comma-separated KiB).
 */
package org.apache.cassandra.cql3;

import java.nio.ByteBuffer;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;
import java.util.Random;

import org.junit.BeforeClass;
import org.junit.Test;

import org.apache.cassandra.config.DatabaseDescriptor;
import org.apache.cassandra.cql3.statements.BatchStatement;
import org.apache.cassandra.db.ConsistencyLevel;
import org.apache.cassandra.db.IMutation;
import org.apache.cassandra.service.ClientState;
import org.apache.cassandra.transport.Dispatcher;
import org.apache.cassandra.transport.ProtocolVersion;
import org.apache.cassandra.utils.FBUtilities;

public class BatchFailThresholdProbeTest extends CQLTester
{
    private static final String MULTI = "BEGIN BATCH INSERT INTO %1$s (k, c, v) VALUES (1, 0, ?); INSERT INTO %1$s (k, c, v) VALUES (2, 0, ?); APPLY BATCH";
    private static final String SINGLE = "BEGIN BATCH INSERT INTO %1$s (k, c, v) VALUES (1, 0, ?); INSERT INTO %1$s (k, c, v) VALUES (1, 1, ?); APPLY BATCH";

    @BeforeClass
    public static void setUpNetwork()
    {
        requireNetwork();
    }

    private static int[] kibList(String prop, int... dflt)
    {
        String s = System.getProperty(prop);
        if (s == null || s.isEmpty())
            return dflt;
        return Arrays.stream(s.split(",")).mapToInt(x -> Integer.parseInt(x.trim())).toArray();
    }

    private static void p(String s)
    {
        System.out.println(s);
    }

    private long mem()
    {
        return getCurrentColumnFamilyStore().getTracker().getView().getCurrentMemtable().getLiveDataSize();
    }

    @Test
    public void probe() throws Throwable
    {
        int[] fs = kibList("probe.f", 50, 100, 200);
        int[] bs = kibList("probe.b", 10, 24, 26, 60, 98, 102);
        createTable("CREATE TABLE %s (k int, c int, v blob, PRIMARY KEY (k, c))");
        Random rnd = new Random(20261026L);
        int cases = 0;
        for (int f : fs)
        {
            DatabaseDescriptor.setBatchSizeWarnThresholdInKiB(1);
            DatabaseDescriptor.setBatchSizeFailThresholdInKiB(f);
            p(String.format("PROBE readback F=%d failBytes=%d warnBytes=%d", f,
                            DatabaseDescriptor.getBatchSizeFailThreshold(), DatabaseDescriptor.getBatchSizeWarnThreshold()));
            for (int b : bs)
            {
                for (String shape : new String[]{ "multi", "single" })
                {
                    String q = shape.equals("multi") ? MULTI : SINGLE;
                    byte[] a1 = new byte[b * 1024], a2 = new byte[b * 1024];
                    rnd.nextBytes(a1);
                    rnd.nextBytes(a2);
                    ByteBuffer bb1 = ByteBuffer.wrap(a1), bb2 = ByteBuffer.wrap(a2);

                    execute("TRUNCATE %s");

                    // (i) the operand, on the same bound values
                    ClientState cs = ClientState.forInternalCalls();
                    BatchStatement bst = (BatchStatement) QueryProcessor.parseStatement(formatQuery(q), cs);
                    List<ByteBuffer> vals = new ArrayList<>();
                    vals.add(bb1.duplicate());
                    vals.add(bb2.duplicate());
                    QueryOptions opts = QueryOptions.forInternalCalls(ConsistencyLevel.ONE, vals);
                    List<? extends IMutation> muts = bst.getMutations(cs, BatchQueryOptions.withoutPerStatementVariables(opts), false,
                                                                      FBUtilities.timestampMicros(), FBUtilities.nowInSeconds(),
                                                                      Dispatcher.RequestTime.forImmediateExecution());
                    long dataSize = IMutation.dataSize(muts);

                    long m0 = mem();
                    boolean rejected = false;
                    String msg = "-";
                    try
                    {
                        executeNet(ProtocolVersion.CURRENT, q, bb1.duplicate(), bb2.duplicate());
                    }
                    catch (Throwable t)
                    {
                        rejected = true;
                        msg = t.getClass().getSimpleName() + ": " + String.valueOf(t.getMessage()).replace('\n', ' ');
                    }
                    long rows = execute("SELECT count(*) FROM %s").one().getLong("count");
                    long m1 = mem();
                    p(String.format("PROBE F=%d B=%d shape=%s mutations=%d dataSize=%d rejected=%s msg=%s rows=%d memDelta=%d",
                                    f, b, shape, muts.size(), dataSize, rejected, msg, rows, m1 - m0));
                    cases++;
                }
            }
        }
        p(String.format("PROBE done cases=%d", cases));
    }
}
