/* Stage-4 harness (capacity-enforcement-exp, Cassandra extension order o100), unit tier B2: the case file's B2e.1 class verbatim,
 * except amendment S4-A2 (println of String.format instead of printf). Copied into test/unit/org/apache/cassandra/db/commitlog/
 * of /mydata/jingsong-cass-s4/o100/c509-unit only. */
package org.apache.cassandra.db.commitlog;

import java.lang.reflect.Field;
import java.util.Queue;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.AtomicLong;
import java.util.concurrent.locks.LockSupport;

import org.junit.Assert;
import org.junit.BeforeClass;
import org.junit.Test;

import org.apache.cassandra.SchemaLoader;
import org.apache.cassandra.db.ColumnFamilyStore;
import org.apache.cassandra.db.Keyspace;
import org.apache.cassandra.db.Mutation;
import org.apache.cassandra.db.RowUpdateBuilder;
import org.apache.cassandra.schema.KeyspaceParams;
import org.apache.cassandra.utils.concurrent.AsyncPromise;

public class ReplayOutstandingCountTest
{
    static final String KS = "ReplayCountKS", CF = "Standard1";
    static final int N = Integer.getInteger("replay.n", 20000);
    static final long CONSUMER_NANOS = Long.getLong("replay.consumer_nanos", 200_000L);
    static final long BYTES_CAP = Long.getLong("replay.bytes_cap", Long.MAX_VALUE);

    @BeforeClass
    public static void schema()
    {
        SchemaLoader.prepareServer();
        SchemaLoader.createKeyspace(KS, KeyspaceParams.simple(1), SchemaLoader.standardCFMD(KS, CF));
    }

    static final class SlowInitiator extends CommitLogReplayer.MutationInitiator
    {
        final ExecutorService consumer = Executors.newSingleThreadExecutor();
        final AtomicInteger notYetRun = new AtomicInteger();
        final AtomicLong handled = new AtomicLong();
        volatile int peakQueue, peakNotYetRun;
        volatile long peakPendingBytes;
        final Field futuresF, pendingF;

        SlowInitiator() throws Exception
        {
            futuresF = CommitLogReplayer.class.getDeclaredField("futures");
            futuresF.setAccessible(true);
            pendingF = CommitLogReplayer.class.getDeclaredField("pendingMutationBytes");
            pendingF.setAccessible(true);
        }

        @Override
        protected org.apache.cassandra.utils.concurrent.Future<Integer> initiateMutation(Mutation m, long segmentId, int size,
                                                                                         int entryLocation, CommitLogReplayer clr)
        {
            try
            {
                int q = ((Queue<?>) futuresF.get(clr)).size() + 1;   // size right after the coming offer
                long pb = pendingF.getLong(clr);                      // already includes this mutation
                if (q > peakQueue) peakQueue = q;
                if (pb > peakPendingBytes) peakPendingBytes = pb;
            }
            catch (IllegalAccessException e) { throw new AssertionError(e); }
            handled.incrementAndGet();
            int nyr = notYetRun.incrementAndGet();
            if (nyr > peakNotYetRun) peakNotYetRun = nyr;
            final Mutation[] hold = { m };                            // reachable until run, like the real FutureTask
            final AsyncPromise<Integer> p = new AsyncPromise<>();
            consumer.execute(() -> {
                if (CONSUMER_NANOS > 0) LockSupport.parkNanos(CONSUMER_NANOS);
                hold[0] = null;
                notYetRun.decrementAndGet();
                p.trySuccess(size);
            });
            return p;
        }
    }

    @Test
    public void measure() throws Exception
    {
        CommitLog.instance.resetUnsafe(true);
        ColumnFamilyStore cfs = Keyspace.open(KS).getColumnFamilyStore(CF);
        for (int i = 0; i < N; i++)
            new RowUpdateBuilder(cfs.metadata(), 0, "key" + i).clustering("c").add("val", "v").build().apply();

        Field capF = CommitLogReplayer.class.getDeclaredField("MAX_OUTSTANDING_REPLAY_COUNT");
        capF.setAccessible(true);
        int countCap = capF.getInt(null);

        long origBytes = CommitLogReplayer.MAX_OUTSTANDING_REPLAY_BYTES;
        CommitLogReplayer.MutationInitiator orig = CommitLogReplayer.mutationInitiator;
        SlowInitiator s = new SlowInitiator();
        CommitLogReplayer.MAX_OUTSTANDING_REPLAY_BYTES = BYTES_CAP;
        CommitLogReplayer.mutationInitiator = s;
        try
        {
            CommitLog.instance.resetUnsafe(false);   // stop without deleting segments, restart = replay
        }
        finally
        {
            CommitLogReplayer.mutationInitiator = orig;
            CommitLogReplayer.MAX_OUTSTANDING_REPLAY_BYTES = origBytes;
            s.consumer.shutdownNow();
        }
        // S4-A2 (2026-11-24): one println of a pre-formatted string; the test JVM routes System.out through the logger
        System.out.println(String.format("RESULT count_cap=%d bytes_cap=%d consumer_ns=%d N=%d handled=%d peak_queue=%d peak_not_yet_run=%d peak_pending_bytes=%d",
                          countCap, BYTES_CAP, CONSUMER_NANOS, N, s.handled.get(), s.peakQueue, s.peakNotYetRun, s.peakPendingBytes));
        Assert.assertTrue("replay did not see the workload", s.handled.get() >= N);
    }
}
