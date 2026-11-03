/*
 * Stage-4 harness, case max_queue_weight-acquireWeight-weight--autonomous, unit tier (B2e step 5, as amended U1-U5 2026-10-27).
 * Copied into test/unit/org/apache/cassandra/utils/binlog/ of the run clone; never committed to Cassandra.
 * Blocking-writer pattern from BinLogTest:233-266. Output: "MQW BINLOG ..." lines on stdout.
 */
package org.apache.cassandra.utils.binlog;

import java.lang.reflect.Field;
import java.nio.ByteBuffer;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Arrays;
import java.util.concurrent.Semaphore;

import org.junit.BeforeClass;
import org.junit.Test;

import net.openhft.chronicle.queue.RollCycles;
import net.openhft.chronicle.wire.WireOut;
import org.apache.cassandra.config.DatabaseDescriptor;
import org.apache.cassandra.cql3.QueryOptions;
import org.apache.cassandra.db.ConsistencyLevel;
import org.apache.cassandra.fql.FullQueryLogger;
import org.apache.cassandra.io.util.File;
import org.apache.cassandra.service.QueryState;
import org.apache.cassandra.transport.CBUtil;
import org.apache.cassandra.utils.ByteBufferUtil;
import org.apache.cassandra.utils.concurrent.WeightedQueue;

public class BinLogCapTest
{
    static final String QSTR = "INSERT INTO ks.t (k,v) VALUES (?,?)";
    static final int[] MS = { 1 << 20, 8 << 20, 64 << 20, 256 << 20 };

    @BeforeClass
    public static void setup()
    {
        DatabaseDescriptor.daemonInitialization();
        System.out.println("MQW ENV allocator=" + CBUtil.allocator.getClass().getName() + " useHeap=" + CBUtil.USE_HEAP_ALLOCATOR
                           + " maxMemory=" + Runtime.getRuntime().maxMemory());
    }

    static FullQueryLogger.Query query(int valueSize)
    {
        QueryOptions o = QueryOptions.forInternalCalls(ConsistencyLevel.ONE, Arrays.asList(ByteBufferUtil.bytes(1), ByteBuffer.allocate(valueSize)));
        return new FullQueryLogger.Query(QSTR, o, QueryState.forInternalCalls(), System.currentTimeMillis());
    }

    static int permits(BinLog b) throws Exception
    {
        Field f = WeightedQueue.class.getDeclaredField("availableWeight");
        f.setAccessible(true);
        Object sem = f.get(b.sampleQueue);
        return ((org.apache.cassandra.utils.concurrent.Semaphore) sem).permits();
    }

    @Test
    public void binLogCap() throws Exception
    {
        for (int M : MS)
        {
            Path path = Files.createTempDirectory("mqwbinlog" + M);
            BinLog binLog = new BinLog.Builder().path(path)
                                                .rollCycle(RollCycles.TEST_SECONDLY.toString())
                                                .maxQueueWeight(M)
                                                .maxLogSize(4L << 30)
                                                .blocking(false)
                                                .build(false);
            Semaphore blockBinLog = new Semaphore(0);
            Semaphore binLogBlocked = new Semaphore(0);
            binLog.put(new BinLog.ReleaseableWriteMarshallable()
            {
                public void release() {}
                protected long version() { return 0; }
                protected String type() { return "test"; }
                public void writeMarshallablePayload(WireOut wire)
                {
                    binLogBlocked.release();
                    try { blockBinLog.acquire(); }
                    catch (InterruptedException e) { throw new RuntimeException(e); }
                }
            });
            long t0 = System.currentTimeMillis();
            boolean blocked = false;
            while (System.currentTimeMillis() - t0 < 60_000 && !(blocked = binLogBlocked.tryAcquire()))
                Thread.sleep(10);
            int p0 = permits(binLog);

            FullQueryLogger.Query probe = query(4096);
            int w = probe.weight();
            probe.release();
            int nOff = (int) ((2L * M + w - 1) / w);
            int nAcc = 0, firstFalse = -1, trueAfterFalse = 0;
            long W = 0;
            for (int i = 0; i < nOff; i++)
            {
                FullQueryLogger.Query q = query(4096);
                int wi = q.weight();
                if (binLog.offer(q))
                {
                    nAcc++; W += wi;
                    if (firstFalse >= 0) trueAfterFalse++;
                }
                else
                {
                    q.release();
                    if (firstFalse < 0) firstFalse = i;
                }
            }
            int p1 = permits(binLog);
            System.out.println(String.format("MQW BINLOG M=%d writerBlocked=%s permitsBefore=%d w=%d nOff=%d nAcc=%d W=%d permits=%d firstFalse=%d trueAfterFalse=%d floorMw=%d MminusW=%d",
                                             M, blocked, p0, w, nOff, nAcc, W, p1, firstFalse, trueAfterFalse, M / w, M - W));
            blockBinLog.release();
            t0 = System.currentTimeMillis();
            int p2;
            while ((p2 = permits(binLog)) != M && System.currentTimeMillis() - t0 < 60_000)
                Thread.sleep(10);
            long ms = System.currentTimeMillis() - t0;
            binLog.stop();
            for (File f : new File(path).tryList())
                f.tryDelete();
            new File(path).tryDelete();
            System.out.println(String.format("MQW BINLOGDRAIN M=%d permits=%d restored=%s ms=%d", M, p2, p2 == M, ms));
        }
    }
}
