/*
 * Stage-4 harness, unit tier (B2, as amended 2026-10-26) of
 * batchlog_DEFAULT_PAGE_SIZE-processBatchlogEntries-positionInPage--autonomous.
 * Copied into the run clone's test/unit/org/apache/cassandra/batchlog/ by unit-run.sh. Not upstream code.
 *
 * Four cases (A-D of B2b). Each: truncate system.batches, reset the replay cursor (lastReplayedUuid, B2c amendment),
 * store the batches, flush if the case asks, check the SSTable precondition, record calculatePageSize and the mean,
 * replay once (performInitialReplay), and print one "BLP " line with the readings. Two Byteman rules record:
 *   - finishAndClearBatches AT ENTRY: the size of the list of unfinished (decoded) batches and the sum of their
 *     replayedBytes fields (the :296 boundary and the final partial page),
 *   - calculatePageSize AT EXIT: the page size computed inside the replay pass (:216).
 */
package org.apache.cassandra.batchlog;

import java.lang.reflect.Field;
import java.nio.ByteBuffer;
import java.util.ArrayList;
import java.util.List;
import java.util.Random;
import java.util.UUID;

import org.junit.BeforeClass;
import org.junit.Test;
import org.junit.runner.RunWith;

import org.apache.cassandra.SchemaLoader;
import org.apache.cassandra.Util;
import org.apache.cassandra.config.DatabaseDescriptor;
import org.apache.cassandra.db.ColumnFamilyStore;
import org.apache.cassandra.db.Keyspace;
import org.apache.cassandra.db.Mutation;
import org.apache.cassandra.db.RowUpdateBuilder;
import org.apache.cassandra.db.SystemKeyspace;
import org.apache.cassandra.db.marshal.BytesType;
import org.apache.cassandra.dht.Murmur3Partitioner;
import org.apache.cassandra.locator.InetAddressAndPort;
import org.apache.cassandra.locator.TokenMetadata;
import org.apache.cassandra.schema.KeyspaceParams;
import org.apache.cassandra.schema.SchemaConstants;
import org.apache.cassandra.schema.TableMetadata;
import org.apache.cassandra.service.StorageService;
import org.apache.cassandra.utils.ByteBufferUtil;
import org.apache.cassandra.utils.TimeUUID;
import org.jboss.byteman.contrib.bmunit.BMRule;
import org.jboss.byteman.contrib.bmunit.BMRules;
import org.jboss.byteman.contrib.bmunit.BMUnitRunner;

import static org.apache.cassandra.utils.Clock.Global.currentTimeMillis;
import static org.junit.Assert.assertEquals;
import static org.junit.Assert.assertTrue;

@RunWith(BMUnitRunner.class)
@BMRules(rules = {
    @BMRule(name = "page",
            targetClass = "org.apache.cassandra.batchlog.BatchlogManager",
            targetMethod = "finishAndClearBatches",
            targetLocation = "AT ENTRY",
            action = "org.apache.cassandra.batchlog.BatchlogPageBudgetTest.record($1)"),
    @BMRule(name = "replayPs",
            targetClass = "org.apache.cassandra.batchlog.BatchlogManager",
            targetMethod = "calculatePageSize",
            targetLocation = "AT EXIT",
            action = "org.apache.cassandra.batchlog.BatchlogPageBudgetTest.recordPs($!)")
})
public class BatchlogPageBudgetTest
{
    static final String BLP = "BLP";
    static final String T = "T";
    static final int KIB = 1024;

    // ---- recorder (called from the Byteman rules on the BatchlogTasks thread) ----
    static volatile boolean recording = false;
    static final List<Integer> counts = new ArrayList<>();
    static final List<Long> bytes = new ArrayList<>();
    static final List<Integer> replayPs = new ArrayList<>();

    public static synchronized void record(List<?> l)
    {
        if (!recording)
            return;
        long sum = 0;
        try
        {
            for (Object o : l)
            {
                Field f = o.getClass().getDeclaredField("replayedBytes");
                f.setAccessible(true);
                sum += f.getInt(o);
            }
        }
        catch (Exception e)
        {
            throw new RuntimeException(e);
        }
        counts.add(l.size());
        bytes.add(sum);
    }

    public static synchronized void recordPs(int ps)
    {
        if (recording)
            replayPs.add(ps);
    }

    static synchronized void reset()
    {
        counts.clear();
        bytes.clear();
        replayPs.clear();
    }

    @BeforeClass
    public static void defineSchema() throws Exception
    {
        DatabaseDescriptor.daemonInitialization();
        // Runbook fix 2026-10-26 (defect 1): the unit yaml enables read thresholds (test/conf/cassandra.yaml:63-67) and the
        // coordinator read-size check in SelectStatement.process also runs for the internal paged replay read; a node has
        // them disabled by default (Config.java:526). Disabled here, as on the node.
        DatabaseDescriptor.setReadThresholdsEnabled(false);
        Util.switchPartitioner(Murmur3Partitioner.instance);
        SchemaLoader.prepareServer();
        SchemaLoader.createKeyspace(BLP, KeyspaceParams.simple(1),
                                    SchemaLoader.standardCFMD(BLP, T, 1, BytesType.instance, BytesType.instance));
        TokenMetadata metadata = StorageService.instance.getTokenMetadata();
        InetAddressAndPort localhost = InetAddressAndPort.getByName("127.0.0.1");
        metadata.updateNormalToken(Util.token("A"), localhost);
        metadata.updateHostId(UUID.randomUUID(), localhost);
        System.out.println("BLP setup endpoints=" + metadata.getSizeOfAllEndpoints()
                           + " batchlogTimeout=" + BatchlogManager.getBatchlogTimeout()
                           + " DEFAULT_PAGE_SIZE=" + BatchlogManager.DEFAULT_PAGE_SIZE
                           + " maxMutationSize=" + DatabaseDescriptor.getMaxMutationSize()
                           + " readThresholdsEnabled=" + DatabaseDescriptor.getReadThresholdsEnabled());
    }

    static ColumnFamilyStore batches()
    {
        return Keyspace.open(SchemaConstants.SYSTEM_KEYSPACE_NAME).getColumnFamilyStore(SystemKeyspace.BATCHES);
    }

    static void prepareCase() throws Exception
    {
        batches().truncateBlocking();
        Field f = BatchlogManager.class.getDeclaredField("lastReplayedUuid");
        f.setAccessible(true);
        f.set(BatchlogManager.instance, TimeUUID.minAtUnixMillis(0));
        DatabaseDescriptor.setBatchlogReplayThrottleInKiB(0);
        reset();
    }

    static final Random rnd = new Random(42);
    static long keySeq = 0;

    /** stores n batches of m mutations, each mutation carrying one blob of valueBytes; ids at base + i ms */
    static void store(int n, int m, int valueBytes, long baseMillis)
    {
        TableMetadata cfm = Keyspace.open(BLP).getColumnFamilyStore(T).metadata();
        for (int i = 0; i < n; i++)
        {
            List<Mutation> mutations = new ArrayList<>(m);
            for (int j = 0; j < m; j++)
            {
                byte[] v = new byte[valueBytes];
                rnd.nextBytes(v);
                mutations.add(new RowUpdateBuilder(cfm, (baseMillis + i) * 1000, ByteBufferUtil.bytes(keySeq++))
                              .clustering("c")
                              .add("val", ByteBuffer.wrap(v))
                              .build());
            }
            long ts = baseMillis + i;
            BatchlogManager.store(Batch.createLocal(TimeUUID.Generator.atUnixMillis(ts, 0), ts * 1000, mutations));
        }
    }

    static long old()
    {
        return currentTimeMillis() - 2 * BatchlogManager.getBatchlogTimeout() - 60_000;
    }

    static void replayAndPrint(String name, int n, int preSSTables) throws Exception
    {
        ColumnFamilyStore store = batches();
        double mean = store.getMeanPartitionSize();
        int ps = BatchlogManager.calculatePageSize(store);
        int stored = BatchlogManager.instance.countAllBatches();
        long before = BatchlogManager.instance.getTotalBatchesReplayed();
        recording = true;
        BatchlogManager.instance.performInitialReplay();
        recording = false;
        long replayed = BatchlogManager.instance.getTotalBatchesReplayed() - before;
        int after = BatchlogManager.instance.countAllBatches();
        int maxCount = 0;
        long maxBytes = 0;
        synchronized (BatchlogPageBudgetTest.class)
        {
            for (int c : counts) maxCount = Math.max(maxCount, c);
            for (long b : bytes) maxBytes = Math.max(maxBytes, b);
            System.out.println(String.format("BLP case=%s N=%d stored=%d sstables=%d mean=%.1f ps=%d replayPs=%s calls=%d maxCount=%d maxBytes=%d maxMiB=%.4f replayedDelta=%d afterCount=%d counts=%s bytes=%s",
                                             name, n, stored, preSSTables, mean, ps, replayPs, counts.size(), maxCount, maxBytes,
                                             maxBytes / (1024.0 * 1024.0), replayed, after, counts, bytes));
        }
    }

    // A: 260 x 64 KiB (2 x 32 KiB), memtable only -> :254 fallback, 128
    @Test
    public void caseA() throws Exception
    {
        prepareCase();
        store(260, 2, 32 * KIB, old());
        int ss = batches().getLiveSSTables().size();
        assertEquals("A precondition: no SSTables", 0, ss);
        replayAndPrint("A", 260, ss);
    }

    // B: 260 x 64 KiB, flushed -> :257
    @Test
    public void caseB() throws Exception
    {
        prepareCase();
        store(260, 2, 32 * KIB, old());
        batches().forceBlockingFlush(ColumnFamilyStore.FlushReason.UNIT_TESTS);
        int ss = batches().getLiveSSTables().size();
        assertTrue("B precondition: SSTable present", ss >= 1);
        replayAndPrint("B", 260, ss);
    }

    // C: 500 tiny (1 mutation, 100 B) flushed, then 260 x 64 KiB unflushed (newer ids) -> diluted mean, 128
    @Test
    public void caseC() throws Exception
    {
        prepareCase();
        long base = old();
        store(500, 1, 100, base);
        batches().forceBlockingFlush(ColumnFamilyStore.FlushReason.UNIT_TESTS);
        int ssTiny = batches().getLiveSSTables().size();
        store(260, 2, 32 * KIB, base + 1000);
        int ss = batches().getLiveSSTables().size();
        assertTrue("C precondition: tiny SSTable present", ssTiny >= 1);
        assertEquals("C precondition: large batches not flushed", ssTiny, ss);
        replayAndPrint("C", 760, ss);
    }

    // D: 12 x 1 MiB (2 x 512 KiB), flushed -> :257 near the budget
    @Test
    public void caseD() throws Exception
    {
        prepareCase();
        store(12, 2, 512 * KIB, old());
        batches().forceBlockingFlush(ColumnFamilyStore.FlushReason.UNIT_TESTS);
        int ss = batches().getLiveSSTables().size();
        assertTrue("D precondition: SSTable present", ss >= 1);
        replayAndPrint("D", 12, ss);
    }
}
