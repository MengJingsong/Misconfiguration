/*
 * Stage 4, unit tier (B2) of maxHintsInProgress-checkHintOverload-totalHintsInProgress--autonomous.
 * B2e step 1's class, with audit amendment R2 (2026-10-21): the mutation is built through PartitionUpdate.SimpleBuilder
 * (the filed chain does not compile), HintsService is imported, and three facts are printed once (INFO line).
 * Everything else is the filed code: L in {1, 128, 1000, MAX}; MutationStage blocked by getConcurrentWriters() latch tasks;
 * 2000 x (checkHintOverload by reflection, then submitHint) with a 64 KiB blob each; RESULT and DRAINED lines per L.
 * The same file runs unchanged in the original and the patched build (B2a item 5).
 */
package org.apache.cassandra.service;

import java.lang.management.ManagementFactory;
import java.lang.management.MemoryMXBean;
import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Method;
import java.nio.ByteBuffer;
import java.util.ArrayList;
import java.util.List;
import java.util.UUID;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.atomic.AtomicInteger;

import org.junit.Test;

import org.apache.cassandra.concurrent.Stage;
import org.apache.cassandra.config.DatabaseDescriptor;
import org.apache.cassandra.cql3.CQLTester;
import org.apache.cassandra.db.Mutation;
import org.apache.cassandra.db.partitions.PartitionUpdate;
import org.apache.cassandra.dht.IPartitioner;
import org.apache.cassandra.dht.Range;
import org.apache.cassandra.exceptions.OverloadedException;
import org.apache.cassandra.hints.HintsService;
import org.apache.cassandra.locator.InetAddressAndPort;
import org.apache.cassandra.locator.Replica;
import org.apache.cassandra.metrics.StorageMetrics;

public class HintOverloadCheckTest extends CQLTester
{
    @Test
    public void sweep() throws Throwable
    {
        createTable("CREATE TABLE %s (k int PRIMARY KEY, v blob)");
        DatabaseDescriptor.getRawConfig().hint_window_persistent_enabled = false;
        InetAddressAndPort ep2 = InetAddressAndPort.getByName("127.0.0.2");
        StorageService.instance.getTokenMetadata().updateHostId(UUID.randomUUID(), ep2);
        IPartitioner p = DatabaseDescriptor.getPartitioner();
        Replica r = Replica.fullReplica(ep2, new Range<>(p.getMinimumToken(), p.getMinimumToken()));
        Method chk = StorageProxy.class.getDeclaredMethod("checkHintOverload", Replica.class);
        chk.setAccessible(true);
        Method pd = StorageProxy.class.getDeclaredMethod("getHintsInProgressFor", InetAddressAndPort.class);
        pd.setAccessible(true);
        MemoryMXBean mem = ManagementFactory.getMemoryMXBean();
        System.out.printf("INFO maxHeapMiB=%d concurrentWriters=%d defaultMaxHintsInProgress=%d totalHintsInProgress0=%d isSelf=%b counterClass=%s%n",
                          Runtime.getRuntime().maxMemory() >> 20, DatabaseDescriptor.getConcurrentWriters(),
                          StorageProxy.instance.getMaxHintsInProgress(), StorageMetrics.totalHintsInProgress.getCount(),
                          r.isSelf(), pd.invoke(null, ep2).getClass().getName());
        for (int L : new int[]{ 1, 128, 1000, Integer.MAX_VALUE })
        {
            StorageProxy.instance.setMaxHintsInProgress(L);
            CountDownLatch gate = new CountDownLatch(1);
            for (int t = 0; t < DatabaseDescriptor.getConcurrentWriters(); t++)
                Stage.MUTATION.execute(() -> { try { gate.await(); } catch (InterruptedException e) {} });
            Thread.sleep(500);
            System.gc(); System.gc(); System.gc();
            long h0 = mem.getHeapMemoryUsage().getUsed();
            int rejected = 0;
            List<Mutation> keep = new ArrayList<>();
            for (int i = 0; i < 2000; i++)
            {
                PartitionUpdate.SimpleBuilder b = PartitionUpdate.simpleBuilder(currentTableMetadata(), i);
                b.row().add("v", ByteBuffer.allocate(65536));
                Mutation m = b.buildAsMutation();
                try
                {
                    chk.invoke(null, r);
                    StorageProxy.submitHint(m, r, null);
                }
                catch (InvocationTargetException e)
                {
                    if (e.getCause() instanceof OverloadedException) rejected++;
                    else throw e.getCause();
                }
            }
            keep = null;
            System.gc(); System.gc(); System.gc();
            long h1 = mem.getHeapMemoryUsage().getUsed();
            long queued = StorageMetrics.totalHintsInProgress.getCount();
            int perDest = ((AtomicInteger) pd.invoke(null, ep2)).get();
            boolean same = pd.invoke(null, ep2) == pd.invoke(null, ep2);
            System.out.printf("RESULT L=%d queued=%d rejected=%d perDest=%d same=%b shouldHint=%b heapDeltaMiB=%d heapDeltaBytes=%d%n",
                              L, queued, rejected, perDest, same, StorageProxy.shouldHint(r), (h1 - h0) >> 20, h1 - h0);
            gate.countDown();
            long deadline = System.currentTimeMillis() + 120_000;
            while (StorageMetrics.totalHintsInProgress.getCount() > 0 && System.currentTimeMillis() < deadline)
                Thread.sleep(100);
            System.out.printf("DRAINED L=%d remaining=%d%n", L, StorageMetrics.totalHintsInProgress.getCount());
            HintsService.instance.deleteAllHints();
        }
    }
}
