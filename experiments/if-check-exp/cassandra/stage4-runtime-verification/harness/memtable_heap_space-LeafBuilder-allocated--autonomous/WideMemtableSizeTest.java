/*
 * Stage-4 harness: memtable_heap_space-LeafBuilder-allocated--autonomous, unit tier (B2 as amended U1-U5, 2026-10-27).
 * Re-run change (2026-10-27, after run 1, authorised by the user): the config line also prints the pinned skiplist overhead.
 * Not upstream code. Copied into test/unit/org/apache/cassandra/db/memtable/ of a clone at cassandra-5.0.9 by unit-run.sh.
 * A copy of MemtableSizeTestBase + MemtableSizeUnslabbedTest (unslabbed_heap_buffers, Murmur3, cleanup threshold 0.8,
 * the same three memtable classes, the same measureDeep meter and the same trie adjustment) with the case's changes:
 * partitions = 5,000, rowsPerPartition and write mode as parameters, delete phases removed; plus observe-only counters
 * (WideLeafCounters, fed by unit-counters.btm) and a synthetic known-answer check of the counters.
 *
 * Lines (stdout and the file named by -Dstage4.out):
 *   STAGE4 value <name> <text>      configuration and computed values, not readings
 *   STAGE4 ka <name> n2683=.. n2736=.. allocated=..   synthetic BTree.update known-answer check of the counters
 *   STAGE4 reading variant=.. class=.. rows=.. mode=.. partitions=.. ops=.. owns=.. trieOverhead=.. actual=.. deepBefore=..
 *          deepAfter=.. expected=.. diff=.. pct=.. n2683=.. n2736=.. allocOwns=.. poolUsed=.. flushed=..
 * The test asserts nothing about readings; it fails only if a step cannot run.
 * Properties: stage4.out, stage4.variant (V0|V1, label only), stage4.partitions (default 5000), stage4.classes,
 * stage4.rows, stage4.modes (comma lists; default all: skiplist,skiplist_sharded,trie / 4,256 / single,batch).
 */
package org.apache.cassandra.db.memtable;

import java.io.FileWriter;
import java.io.PrintWriter;
import java.lang.reflect.Field;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Comparator;
import java.util.List;

import org.junit.AfterClass;
import org.junit.BeforeClass;
import org.junit.Test;
import org.junit.runner.RunWith;
import org.junit.runners.Parameterized;

import org.apache.cassandra.ServerTestUtils;
import org.apache.cassandra.Util;
import org.apache.cassandra.config.Config;
import org.apache.cassandra.config.DatabaseDescriptor;
import org.apache.cassandra.cql3.CQLTester;
import org.apache.cassandra.db.ColumnFamilyStore;
import org.apache.cassandra.db.Keyspace;
import org.apache.cassandra.dht.Murmur3Partitioner;
import org.apache.cassandra.service.StorageService;
import org.apache.cassandra.utils.ObjectSizes;
import org.apache.cassandra.utils.btree.BTree;
import org.apache.cassandra.utils.btree.UpdateFunction;
import org.apache.cassandra.utils.memory.HeapPool;
import org.apache.cassandra.utils.memory.MemtablePool;
import org.github.jamm.MemoryMeter;
import org.github.jamm.MemoryMeter.Guess;

@RunWith(Parameterized.class)
public class WideMemtableSizeTest extends CQLTester
{
    static MemoryMeter meter = MemoryMeter.builder()
                                          .withGuessing(Guess.INSTRUMENTATION_AND_SPECIFICATION, Guess.UNSAFE)
                                          .build();

    static final int partitions = Integer.getInteger("stage4.partitions", 5_000);
    static final String variant = System.getProperty("stage4.variant", "V0");
    static PrintWriter out;

    @Parameterized.Parameter(0)
    public String memtableClass;
    @Parameterized.Parameter(1)
    public int rowsPerPartition;
    @Parameterized.Parameter(2)
    public String mode;

    static List<String> list(String prop, String def)
    {
        return Arrays.asList(System.getProperty(prop, def).split(","));
    }

    @Parameterized.Parameters(name = "{0}-{1}-{2}")
    public static List<Object[]> parameters()
    {
        List<Object[]> r = new ArrayList<>();
        for (String c : list("stage4.classes", "skiplist,skiplist_sharded,trie"))
            for (String rows : list("stage4.rows", "4,256"))
                for (String m : list("stage4.modes", "single,batch"))
                    r.add(new Object[]{ c, Integer.parseInt(rows), m });
        return r;
    }

    static void line(String s)
    {
        System.out.println(s);
        if (out != null)
            out.println(s);
    }

    static void value(String name, String text)
    {
        line("STAGE4 value " + name + " " + text);
    }

    // Overrides CQLTester.setUpClass to run before it (as MemtableSizeUnslabbedTest does)
    @BeforeClass
    public static void setUpClass()
    {
        try
        {
            String f = System.getProperty("stage4.out");
            if (f != null)
                out = new PrintWriter(new FileWriter(f, true), true);
        }
        catch (Exception e)
        {
            throw new RuntimeException(e);
        }
        ServerTestUtils.daemonInitialization();
        try
        {
            Field confField = DatabaseDescriptor.class.getDeclaredField("conf");
            confField.setAccessible(true);
            Config conf = (Config) confField.get(null);
            conf.memtable_allocation_type = Config.MemtableAllocationType.unslabbed_heap_buffers;
            conf.memtable_cleanup_threshold = 0.8f; // as MemtableSizeTestBase: no flush during the test
        }
        catch (NoSuchFieldException | IllegalAccessException e)
        {
            throw new RuntimeException(e);
        }
        StorageService.instance.setPartitionerUnsafe(Murmur3Partitioner.instance);
        CQLTester.prepareServer();

        MemtablePool pool = AbstractAllocatorMemtable.MEMORY_POOL;
        value("config", "variant=" + variant
                        + " maxMemory=" + Runtime.getRuntime().maxMemory()
                        + " allocation_type=" + DatabaseDescriptor.getMemtableAllocationType()
                        + " memtable_heap_space_MiB=" + DatabaseDescriptor.getMemtableHeapSpaceInMiB()
                        + " cleanup_threshold=" + DatabaseDescriptor.getMemtableCleanupThreshold()
                        + " pool=" + pool.getClass().getSimpleName()
                        + " pool_onheap_limit=" + pool.onHeap.limit
                        + " heap_pool=" + (pool instanceof HeapPool)
                        + " partitioner=" + DatabaseDescriptor.getPartitioner().getClass().getSimpleName()
                        + " partitions=" + partitions
                        // added for the re-run (amendment of 2026-10-27 after run 1, authorised by the user): the pinned
                        // per-partition charge of the skiplist memtables (SkipListMemtable.java:72-80)
                        + " row_overhead_property=" + System.getProperty("cassandra.memtable.row_overhead_size", "unset")
                        + " skiplist_row_overhead=" + SkipListMemtable.ROW_OVERHEAD_HEAP_SIZE);
        value("btree", "BRANCH_SHIFT=" + BTree.BRANCH_SHIFT + " MIN_KEYS=" + BTree.MIN_KEYS + " MAX_KEYS=" + BTree.MAX_KEYS
                       + " sizeOfReferenceArray(15)=" + ObjectSizes.sizeOfReferenceArray(15)
                       + " sizeOfReferenceArray(17)=" + ObjectSizes.sizeOfReferenceArray(17)
                       + " sizeOfReferenceArray(31)=" + ObjectSizes.sizeOfReferenceArray(31));
        knownAnswer();
    }

    @AfterClass
    public static void closeOut()
    {
        if (out != null)
            out.close();
    }

    /** A non-simple update function (allocation tracking on, Updater.allocated = 0), counting what it is told. */
    static final class Tracking implements UpdateFunction<Object, Object>
    {
        long allocated;
        public Object insert(Object v) { return v; }
        public Object merge(Object replacing, Object update) { return update; }
        public void onAllocatedOnHeap(long heapSize) { allocated += heapSize; }
    }

    /** Synthetic check that the counters see the branches: the same tree shapes as the two write modes, without a memtable. */
    static void knownAnswer()
    {
        Comparator<Object> cmp = (a, b) -> Integer.compare((Integer) a, (Integer) b);
        Tracking fn = new Tracking();
        Object[] tree = BTree.empty();
        WideLeafCounters.start(Thread.currentThread());
        for (int k = 0; k < 256; k++)
            tree = BTree.update(tree, BTree.singleton(k), cmp, fn);
        WideLeafCounters.stop();
        line("STAGE4 ka single256 n2683=" + WideLeafCounters.n2683() + " n2736=" + WideLeafCounters.n2736()
             + " allocated=" + fn.allocated + " size=" + BTree.size(tree) + " depth=" + BTree.depth(tree));

        fn = new Tracking();
        List<Integer> first = new ArrayList<>(), second = new ArrayList<>();
        for (int k = 0; k < 128; k++) first.add(k);
        for (int k = 128; k < 256; k++) second.add(k);
        WideLeafCounters.start(Thread.currentThread());
        tree = BTree.update(BTree.empty(), BTree.build(first), cmp, fn);
        tree = BTree.update(tree, BTree.build(second), cmp, fn);
        WideLeafCounters.stop();
        line("STAGE4 ka batch2x128 n2683=" + WideLeafCounters.n2683() + " n2736=" + WideLeafCounters.n2736()
             + " allocated=" + fn.allocated + " size=" + BTree.size(tree) + " depth=" + BTree.depth(tree));
    }

    @Test
    public void testSize() throws Throwable
    {
        MemtablePool memoryPool = AbstractAllocatorMemtable.MEMORY_POOL;
        if (!(memoryPool instanceof HeapPool))
            throw new IllegalStateException("memtable pool is not a HeapPool: " + memoryPool);

        CQLTester.disablePreparedReuseForTest();
        String keyspace = createKeyspace("CREATE KEYSPACE %s with replication = { 'class' : 'SimpleStrategy', 'replication_factor' : 1 } and durable_writes = false");
        try
        {
            String table = createTable(keyspace, "CREATE TABLE %s ( userid bigint, picid bigint, commentid bigint, PRIMARY KEY(userid, picid))" +
                                                 " with compression = {'enabled': false}" +
                                                 " and memtable = '" + memtableClass + "'");
            String qt = keyspace + '.' + table;
            String insert = "INSERT INTO " + qt + "(userid,picid,commentid)VALUES(?,?,?)";
            int batchRows = Math.min(128, rowsPerPartition);
            StringBuilder sb = new StringBuilder("BEGIN UNLOGGED BATCH ");
            for (int b = 0; b < batchRows; b++)
                sb.append(insert).append("; ");
            sb.append("APPLY BATCH");
            String batch = sb.toString();
            forcePreparedValues();

            ColumnFamilyStore cfs = Keyspace.open(keyspace).getColumnFamilyStore(table);
            cfs.disableAutoCompaction();
            Util.flush(cfs);

            Memtable memtable = cfs.getTracker().getView().getCurrentMemtable();
            long deepSizeBefore = meter.measureDeep(memtable);
            long ops = 0;
            WideLeafCounters.start(Thread.currentThread());
            try
            {
                for (long i = 0; i < partitions; ++i)
                {
                    if (mode.equals("single"))
                    {
                        for (long j = 0; j < rowsPerPartition; ++j)
                        {
                            execute(insert, i, j, i + j);
                            ops++;
                        }
                    }
                    else
                    {
                        for (long j0 = 0; j0 < rowsPerPartition; j0 += batchRows)
                        {
                            Object[] v = new Object[3 * batchRows];
                            for (int b = 0; b < batchRows; b++)
                            {
                                long j = j0 + b;
                                v[3 * b] = i;
                                v[3 * b + 1] = j;
                                v[3 * b + 2] = i + j;
                            }
                            execute(batch, v);
                            ops++;
                        }
                    }
                }
            }
            finally
            {
                WideLeafCounters.stop();
            }
            long n2683 = WideLeafCounters.n2683(), n2736 = WideLeafCounters.n2736();

            boolean flushed = memtable != cfs.getTracker().getView().getCurrentMemtable();
            Memtable.MemoryUsage usage = Memtable.getMemoryUsage(memtable);
            long owns = usage.ownsOnHeap;
            long allocOwns = ((AbstractAllocatorMemtable) memtable).getAllocator().onHeap().owns();
            long poolUsed = memoryPool.onHeap.used();
            long deepSizeAfter = meter.measureDeep(memtable);
            long expected = deepSizeAfter - deepSizeBefore;
            long trieOverhead = memtable instanceof TrieMemtable ? ((TrieMemtable) memtable).unusedReservedMemory() : 0;
            long actual = owns + trieOverhead; // unslabbed_heap_buffers: as MemtableSizeTestBase
            long diff = actual - expected;
            line(String.format("STAGE4 reading variant=%s class=%s rows=%d mode=%s partitions=%d ops=%d owns=%d trieOverhead=%d actual=%d " +
                               "deepBefore=%d deepAfter=%d expected=%d diff=%d pct=%.4f n2683=%d n2736=%d allocOwns=%d poolUsed=%d flushed=%s",
                               variant, memtableClass, rowsPerPartition, mode, partitions, ops, owns, trieOverhead, actual,
                               deepSizeBefore, deepSizeAfter, expected, diff, 100.0 * diff / expected, n2683, n2736,
                               allocOwns, poolUsed, flushed));
        }
        finally
        {
            execute(String.format("DROP KEYSPACE IF EXISTS %s", keyspace));
        }
    }
}
