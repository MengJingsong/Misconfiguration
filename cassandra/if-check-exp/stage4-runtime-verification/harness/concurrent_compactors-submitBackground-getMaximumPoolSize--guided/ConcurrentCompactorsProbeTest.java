package org.apache.cassandra.db.compaction;

import java.io.FileWriter;
import java.io.PrintWriter;
import java.lang.reflect.Field;
import java.nio.ByteBuffer;
import java.util.ArrayList;
import java.util.List;
import java.util.Set;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;

import org.junit.Test;
import org.junit.runner.RunWith;

import org.apache.cassandra.config.DatabaseDescriptor;
import org.apache.cassandra.cql3.CQLTester;
import org.apache.cassandra.db.ColumnFamilyStore;
import org.apache.cassandra.io.sstable.format.SSTableReader;
import org.jboss.byteman.contrib.bmunit.BMRule;
import org.jboss.byteman.contrib.bmunit.BMUnitRunner;

import static org.junit.Assert.assertEquals;
import static org.junit.Assert.assertTrue;

/**
 * Stage 4 unit tier, concurrent_compactors-submitBackground-getMaximumPoolSize (case 9c).
 * For each pool size n: 8 tables with 4 equal SSTables each, every CompactionTask of those tables held at runMayThrow() entry
 * (Byteman); autocompaction is enabled on all 8 at once. Reads the check's operand (executor active task count) and the maximum
 * pool size by reflection, the number of held tasks, and the summed on-disk size of the held tasks' input SSTables.
 * Output lines "RESULT ..." go to -Dstage4.out (and stdout).
 */
@RunWith(BMUnitRunner.class)
public class ConcurrentCompactorsProbeTest extends CQLTester
{
    static final int TABLES = 8, SSTABLES = 4, ROWS = 64, VALUE = 8192;
    static final Set<AbstractCompactionTask> held = ConcurrentHashMap.newKeySet();
    static volatile CountDownLatch release = new CountDownLatch(1);
    static volatile String prefix = "cc_none";

    /** Called by the Byteman rule at CompactionTask.runMayThrow() entry. */
    public static void enter(Object o)
    {
        AbstractCompactionTask t = (AbstractCompactionTask) o;
        SSTableReader first = t.transaction.originals().iterator().next();
        if (!first.descriptor.cfname.startsWith(prefix))
            return;
        held.add(t);
        try { release.await(5, TimeUnit.MINUTES); } catch (InterruptedException e) { throw new RuntimeException(e); }
    }

    static void out(String s) throws Exception
    {
        System.out.println(s);
        String f = System.getProperty("stage4.out");
        if (f != null)
            try (PrintWriter w = new PrintWriter(new FileWriter(f, true))) { w.println(s); }
    }

    static Object executor() throws Exception
    {
        Field f = CompactionManager.class.getDeclaredField("executor");
        f.setAccessible(true);
        return f.get(CompactionManager.instance);
    }

    static int call(Object ex, String m) throws Exception
    {
        return (Integer) ex.getClass().getMethod(m).invoke(ex);
    }

    void round(int n) throws Exception
    {
        prefix = "cc_n" + n + "_";
        held.clear();
        release = new CountDownLatch(1);
        List<ColumnFamilyStore> cfss = new ArrayList<>();
        for (int t = 0; t < TABLES; t++)
        {
            String name = prefix + t;
            schemaChange(String.format("CREATE TABLE %s.%s (k int PRIMARY KEY, v blob) WITH compression = {'enabled':'false'} " +
                                       "AND compaction = {'class':'SizeTieredCompactionStrategy','min_threshold':4,'max_threshold':4}", KEYSPACE, name));
            ColumnFamilyStore cfs = org.apache.cassandra.db.Keyspace.open(KEYSPACE).getColumnFamilyStore(name);
            cfs.disableAutoCompaction();
            for (int s = 0; s < SSTABLES; s++)
            {
                for (int r = 0; r < ROWS; r++)
                {
                    byte[] b = new byte[VALUE];
                    new java.util.Random(s * 100000L + r + t).nextBytes(b);
                    execute(String.format("INSERT INTO %s.%s (k, v) VALUES (?, ?)", KEYSPACE, name), s * 100000 + r, ByteBuffer.wrap(b));
                }
                cfs.forceBlockingFlush(org.apache.cassandra.db.ColumnFamilyStore.FlushReason.UNIT_TESTS);
            }
            assertEquals(SSTABLES, cfs.getLiveSSTables().size());
            cfss.add(cfs);
        }
        long perTable = 0;
        for (SSTableReader r : cfss.get(0).getLiveSSTables()) perTable += r.onDiskLength();

        CompactionManager.instance.setConcurrentCompactors(n);
        DatabaseDescriptor.setConcurrentCompactors(n);
        Object ex = executor();
        int max = call(ex, "getMaximumPoolSize");

        for (ColumnFamilyStore cfs : cfss)
            cfs.enableAutoCompaction();
        int want = Math.min(n, TABLES);
        long deadline = System.nanoTime() + TimeUnit.SECONDS.toNanos(60);
        while (held.size() < want && System.nanoTime() < deadline)
            Thread.sleep(100);
        Thread.sleep(3000); // settle: no more than `want` may ever be held
        int heldN = held.size();
        int active = call(ex, "getActiveTaskCount");
        int pending = call(ex, "getPendingTaskCount");
        long inputs = 0;
        for (AbstractCompactionTask t : held)
            for (SSTableReader r : t.transaction.originals())
                inputs += r.onDiskLength();
        out(String.format("RESULT n=%d max_pool=%d expected_held=%d held=%d active=%d pending=%d held_input_bytes=%d per_table_input_bytes=%d ratio=%.2f",
                          n, max, want, heldN, active, pending, inputs, perTable, perTable == 0 ? 0.0 : (double) inputs / perTable));
        release.countDown();
        // let all 8 compactions finish
        deadline = System.nanoTime() + TimeUnit.SECONDS.toNanos(120);
        while (System.nanoTime() < deadline)
        {
            boolean done = true;
            for (ColumnFamilyStore cfs : cfss) done &= cfs.getLiveSSTables().size() == 1;
            if (done) break;
            Thread.sleep(200);
        }
        int left = 0;
        for (ColumnFamilyStore cfs : cfss) left += cfs.getLiveSSTables().size();
        out(String.format("RESULT n=%d finished tables_with_one_sstable=%d sstables_left=%d", n, TABLES, left));
        assertEquals(max, n);
        assertEquals(want, heldN);
        assertEquals(want, active);
        assertEquals(TABLES, left);
    }

    @Test
    @BMRule(name = "hold compaction tasks", targetClass = "CompactionTask", targetMethod = "runMayThrow", targetLocation = "AT ENTRY",
            action = "org.apache.cassandra.db.compaction.ConcurrentCompactorsProbeTest.enter($0)")
    public void sweep() throws Throwable
    {
        for (int n : new int[]{ 1, 2, 4, 8 })
            round(n);
    }
}
