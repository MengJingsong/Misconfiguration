/*
 * Stage-4 harness, case commitlog_max_compression_buffers_in_pool-simplecachedbufferpool-bufferpool--autonomous,
 * unit tier class 1 (B2a, audit amendments M2, M3). Modelled on CommitLogSegmentBackpressureTest (5.0.9).
 * CAP_N (env) = commitlog_max_compression_buffers_in_pool. LZ4, 1 MiB segments, sync blocked by Byteman.
 */
package org.apache.cassandra.db.commitlog;

import java.lang.management.BufferPoolMXBean;
import java.lang.management.ManagementFactory;
import java.nio.ByteBuffer;
import java.util.Random;
import java.util.concurrent.Semaphore;

import com.google.common.collect.ImmutableMap;

import org.junit.Test;
import org.junit.runner.RunWith;

import org.apache.cassandra.SchemaLoader;
import org.apache.cassandra.config.Config.CommitLogSync;
import org.apache.cassandra.config.DatabaseDescriptor;
import org.apache.cassandra.config.ParameterizedClass;
import org.apache.cassandra.db.ColumnFamilyStore;
import org.apache.cassandra.db.Keyspace;
import org.apache.cassandra.db.Mutation;
import org.apache.cassandra.db.RowUpdateBuilder;
import org.apache.cassandra.db.compaction.CompactionManager;
import org.apache.cassandra.db.marshal.AsciiType;
import org.apache.cassandra.db.marshal.BytesType;
import org.apache.cassandra.io.util.SimpleCachedBufferPool;
import org.apache.cassandra.schema.KeyspaceParams;
import org.jboss.byteman.contrib.bmunit.BMRule;
import org.jboss.byteman.contrib.bmunit.BMRules;
import org.jboss.byteman.contrib.bmunit.BMUnitRunner;

@RunWith(BMUnitRunner.class)
public class PoolCapManagerTest
{
    static final Semaphore allowSync = new Semaphore(1);
    private static final String KEYSPACE1 = "PoolCapTest";
    private static final String STANDARD1 = "Standard1";
    private static final byte[] entropy = new byte[1024 * 256];

    static BufferPoolMXBean direct()
    {
        return ManagementFactory.getPlatformMXBeans(BufferPoolMXBean.class).stream()
                                .filter(b -> b.getName().equals("direct")).findFirst().get();
    }

    static int used(SimpleCachedBufferPool p)
    {
        // toString(): "SimpleBufferPool: usedBuffers:<n>, maxBufferPoolSize:..."
        String s = p.toString();
        int i = s.indexOf("usedBuffers:") + "usedBuffers:".length();
        return Integer.parseInt(s.substring(i, s.indexOf(',', i)).trim());
    }

    static boolean inAwait(Thread t)
    {
        for (StackTraceElement e : t.getStackTrace())
            if (e.getClassName().endsWith("AbstractCommitLogSegmentManager") && e.getMethodName().equals("awaitAvailableSegment"))
                return true;
        return false;
    }

    static String top(Thread t)
    {
        StringBuilder sb = new StringBuilder();
        StackTraceElement[] st = t.getStackTrace();
        for (int i = 0; i < Math.min(st.length, 6); i++)
            sb.append(i == 0 ? "" : " < ").append(st[i].getClassName().replaceAll(".*\\.", "")).append('.').append(st[i].getMethodName());
        return sb.toString();
    }

    @Test
    @BMRules(rules = {@BMRule(name = "Acquire Semaphore before sync",
                              targetClass = "AbstractCommitLogService$SyncRunnable",
                              targetMethod = "run",
                              targetLocation = "AT INVOKE org.apache.cassandra.db.commitlog.CommitLog.sync(boolean)",
                              action = "org.apache.cassandra.db.commitlog.PoolCapManagerTest.allowSync.acquire()"),
                      @BMRule(name = "Release Semaphore after sync",
                              targetClass = "AbstractCommitLogService$SyncRunnable",
                              targetMethod = "run",
                              targetLocation = "AFTER INVOKE org.apache.cassandra.db.commitlog.CommitLog.sync(boolean)",
                              action = "org.apache.cassandra.db.commitlog.PoolCapManagerTest.allowSync.release()")})
    public void capManager() throws Throwable
    {
        int n = Integer.parseInt(System.getenv().getOrDefault("CAP_N", "3"));
        new Random().nextBytes(entropy);
        DatabaseDescriptor.daemonInitialization();
        DatabaseDescriptor.setCommitLogCompression(new ParameterizedClass("LZ4Compressor", ImmutableMap.of()));
        DatabaseDescriptor.setCommitLogSegmentSize(1);
        DatabaseDescriptor.setCommitLogSync(CommitLogSync.periodic);
        DatabaseDescriptor.setCommitLogSyncPeriod(10_000);
        DatabaseDescriptor.setCommitLogMaxCompressionBuffersPerPool(n);
        DatabaseDescriptor.initializeCommitLogDiskAccessMode();
        SchemaLoader.prepareServer();
        SchemaLoader.createKeyspace(KEYSPACE1, KeyspaceParams.simple(1),
                                    SchemaLoader.standardCFMD(KEYSPACE1, STANDARD1, 0, AsciiType.instance, BytesType.instance));
        CompactionManager.instance.disableAutoCompaction();
        ColumnFamilyStore cfs1 = Keyspace.open(KEYSPACE1).getColumnFamilyStore(STANDARD1);
        final Mutation m = new RowUpdateBuilder(cfs1.metadata(), 0, "k").clustering("bytes")
                                                                      .add("val", ByteBuffer.wrap(entropy)).build();

        AbstractCommitLogSegmentManager clsm = CommitLog.instance.segmentManager;
        SimpleCachedBufferPool pool = clsm.getBufferPool();
        System.out.println("O44 CONFIG CAP_N=" + n + " compressor=" + DatabaseDescriptor.getCommitLogCompression()
                           + " segmentSize=" + DatabaseDescriptor.getCommitLogSegmentSize()
                           + " maxBuffers=" + DatabaseDescriptor.getCommitLogMaxCompressionBuffersInPool()
                           + " manager=" + clsm.getClass().getSimpleName() + " pool=" + pool
                           + " mutationBytes=" + Mutation.serializer.serializedSize(m, org.apache.cassandra.net.MessagingService.current_version));

        long d0 = direct().getMemoryUsed();
        int u0 = used(pool);
        long w0 = CommitLog.instance.metrics.waitingOnSegmentAllocation.getCount();
        System.out.println("O44 BASE CAP_N=" + n + " u0=" + u0 + " d0=" + d0 + " w0=" + w0 + " active0=" + clsm.getActiveSegments().size());

        allowSync.acquire();                                   // block sync: no segment can be closed
        Thread t = new Thread(() -> { for (int i = 0; i < 64; i++) CommitLog.instance.add(m); }, "o44-writer");
        t.setDaemon(true);
        t.start();
        for (int s : new int[]{ 3000, 2000 })
        {
            Thread.sleep(s);
            System.out.println(String.format("O44 SAMPLE CAP_N=%d t=%s active=%d used=%d atLimit=%b pool=[%s] directDelta=%d waits=%d alive=%b writerInAwait=%b writerTop=%s",
                                             n, s == 3000 ? "3s" : "5s", clsm.getActiveSegments().size(), used(pool), pool.atLimit(), pool,
                                             direct().getMemoryUsed() - d0,
                                             CommitLog.instance.metrics.waitingOnSegmentAllocation.getCount() - w0,
                                             t.isAlive(), inAwait(t), top(t)));
        }
        allowSync.release();
        t.join(60_000);
        System.out.println(String.format("O44 AFTER CAP_N=%d waitsAfter=%d activeAfter=%d used=%d writerDone=%b directDelta=%d",
                                         n, CommitLog.instance.metrics.waitingOnSegmentAllocation.getCount() - w0,
                                         clsm.getActiveSegments().size(), used(pool), !t.isAlive(), direct().getMemoryUsed() - d0));
    }
}
