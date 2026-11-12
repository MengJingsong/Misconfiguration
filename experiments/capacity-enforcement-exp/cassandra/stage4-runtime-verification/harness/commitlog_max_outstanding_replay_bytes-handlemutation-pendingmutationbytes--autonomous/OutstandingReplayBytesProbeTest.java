/*
 * Stage-4 harness (capacity-enforcement-exp), case
 * commitlog_max_outstanding_replay_bytes-handlemutation-pendingmutationbytes--autonomous, unit tier (B2).
 * Copied into test/unit/org/apache/cassandra/db/commitlog/ of a local working tree by unit-run.sh; never
 * into the repository's source copy.
 *
 * For each limit L the test writes 1000 mutations of about 60 KB to keyspace ReplayProbe, then replays the
 * commit log with CommitLogReplayer.MAX_OUTSTANDING_REPLAY_BYTES = L and a probe MutationInitiator that does
 * not apply the mutation: it hands a 5 ms task to its own single-thread executor and returns serializedSize.
 * In initiateMutation (called from handleMutation right after line 517 added `size`) the probe reads the
 * replayer's private pendingMutationBytes by reflection and keeps its maximum (peakPending), and keeps the
 * maximum number of probe tasks not yet finished (maxQueued). Amendment M4: `calls` counts ReplayProbe
 * mutations only; other keyspaces are counted in callsOther.
 */
package org.apache.cassandra.db.commitlog;

import java.lang.reflect.Field;
import java.util.Arrays;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;

import org.junit.BeforeClass;
import org.junit.Test;

import org.apache.cassandra.SchemaLoader;
import org.apache.cassandra.db.ColumnFamilyStore;
import org.apache.cassandra.db.Keyspace;
import org.apache.cassandra.db.Mutation;
import org.apache.cassandra.db.RowUpdateBuilder;
import org.apache.cassandra.schema.KeyspaceParams;
import org.apache.cassandra.schema.TableMetadata;
import org.apache.cassandra.utils.concurrent.AsyncPromise;
import org.apache.cassandra.utils.concurrent.Future;

import static org.junit.Assert.assertEquals;

public class OutstandingReplayBytesProbeTest
{
    static final String KS = "ReplayProbe";
    static final String CF = "T";
    static final int N = 1000;
    static final int VALUE_CHARS = 60000;
    static final long SLEEP_MS = Long.parseLong(envOr("O32_SLEEP_MS", "5"));
    static final long[] LIMITS = Arrays.stream(envOr("O32_LIMITS", "1048576,4194304,16777216,1073741824").split(","))
                                       .mapToLong(Long::parseLong).toArray();

    static String envOr(String name, String dflt)
    {
        String v = System.getenv(name);
        return v == null || v.isEmpty() ? dflt : v;
    }

    static final Field PENDING;
    static
    {
        try
        {
            PENDING = CommitLogReplayer.class.getDeclaredField("pendingMutationBytes");
            PENDING.setAccessible(true);
        }
        catch (NoSuchFieldException e)
        {
            throw new AssertionError(e);
        }
    }

    static class Probe extends CommitLogReplayer.MutationInitiator
    {
        final ExecutorService exec = Executors.newSingleThreadExecutor();
        final AtomicInteger queued = new AtomicInteger();
        // written only by the replay reader thread (the caller of initiateMutation)
        long peakPending = Long.MIN_VALUE;
        long peakPendingAtCall = -1;
        int maxQueued, calls, callsOther, s, sMin = Integer.MAX_VALUE, maxOther;
        long firstNs, lastNs;

        @Override
        protected Future<Integer> initiateMutation(Mutation mutation, long segmentId, int serializedSize,
                                                   int entryLocation, CommitLogReplayer replayer)
        {
            long pending;
            try
            {
                pending = PENDING.getLong(replayer);
            }
            catch (IllegalAccessException e)
            {
                throw new AssertionError(e);
            }
            long now = System.nanoTime();
            if (calls + callsOther == 0)
                firstNs = now;
            lastNs = now;
            if (pending > peakPending)
            {
                peakPending = pending;
                peakPendingAtCall = calls + callsOther + 1;
            }
            if (KS.equals(mutation.getKeyspaceName()))
            {
                calls++;
                s = Math.max(s, serializedSize);
                sMin = Math.min(sMin, serializedSize);
            }
            else
            {
                callsOther++;
                maxOther = Math.max(maxOther, serializedSize);
            }
            int q = queued.incrementAndGet();
            if (q > maxQueued)
                maxQueued = q;
            AsyncPromise<Integer> p = new AsyncPromise<>();
            exec.execute(() -> {
                try
                {
                    Thread.sleep(SLEEP_MS);
                }
                catch (InterruptedException e)
                {
                    Thread.currentThread().interrupt();
                }
                queued.decrementAndGet();
                p.trySuccess(serializedSize);
            });
            return p;
        }
    }

    @BeforeClass
    public static void defineSchema()
    {
        SchemaLoader.prepareServer();
        SchemaLoader.createKeyspace(KS, KeyspaceParams.simple(1), SchemaLoader.standardCFMD(KS, CF));
    }

    @Test
    public void probe() throws Exception
    {
        StringBuilder sb = new StringBuilder(VALUE_CHARS);
        for (int i = 0; i < VALUE_CHARS; i++)
            sb.append((char) ('a' + (i % 26)));
        String big = sb.toString();

        System.out.println("O32 CONFIG N=" + N + " valueChars=" + VALUE_CHARS + " sleepMs=" + SLEEP_MS
                           + " countCap=" + System.getProperty("cassandra.commitlog_max_outstanding_replay_count", "1024(default)")
                           + " limits=" + Arrays.toString(LIMITS));
        for (long limit : LIMITS)
        {
            long originalLimit = CommitLogReplayer.MAX_OUTSTANDING_REPLAY_BYTES;
            CommitLogReplayer.MutationInitiator originalInitiator = CommitLogReplayer.mutationInitiator;
            Probe probe = new Probe();
            try
            {
                // a. fresh commit log, empty table
                CommitLog.instance.resetUnsafe(true);
                ColumnFamilyStore cfs = Keyspace.open(KS).getColumnFamilyStore(CF);
                cfs.truncateBlocking();
                TableMetadata metadata = cfs.metadata();
                // b. the workload
                for (int i = 0; i < N; i++)
                    new RowUpdateBuilder(metadata, 0, "k" + i).clustering("c").add("val", big).build().apply(); // durable: applyUnsafe() skips the commit log (defect D1, amendment M6)
                // c. knob and probe
                CommitLogReplayer.MAX_OUTSTANDING_REPLAY_BYTES = limit;
                CommitLogReplayer.mutationInitiator = probe;
                // d. restart the commit log: replays the written segments
                long t0 = System.nanoTime();
                int files = CommitLog.instance.resetUnsafe(false);
                long ms = TimeUnit.NANOSECONDS.toMillis(System.nanoTime() - t0);
                // e. readings
                System.out.println("O32 LIMIT=" + limit + " peakPending=" + probe.peakPending + " maxQueued=" + probe.maxQueued
                                   + " s=" + probe.s + " sMin=" + probe.sMin + " calls=" + probe.calls
                                   + " callsOther=" + probe.callsOther + " maxOther=" + probe.maxOther
                                   + " peakAtCall=" + probe.peakPendingAtCall + " files=" + files + " replayMs=" + ms
                                   + " readSpanMs=" + TimeUnit.NANOSECONDS.toMillis(probe.lastNs - probe.firstNs));
                assertEquals(N, probe.calls);
            }
            finally
            {
                // f. restore
                CommitLogReplayer.mutationInitiator = originalInitiator;
                CommitLogReplayer.MAX_OUTSTANDING_REPLAY_BYTES = originalLimit;
                probe.exec.shutdownNow();
            }
        }
    }
}
