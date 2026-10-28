/*
 * Stage-4 harness, long path: repair_session_space-split-maxsize, case section 9e unit steps U1-U4.
 * Not upstream code. Copy into test/unit/org/apache/cassandra/repair/ of a clone at cassandra-5.0.9.
 *
 * Prints one line per reading, to stdout and to the file named by -Dstage4.out:
 *   STAGE4 check <name> expected=<x> actual=<y> ok|MISMATCH
 *   STAGE4 value <name> <text>
 * Every check is evaluated; the test fails at the end if any check is a MISMATCH.
 * Modelled on ValidatorTest (schema, CompactionsTest.populate, the outbound sink, submitValidation).
 */
package org.apache.cassandra.repair;

import java.io.FileWriter;
import java.io.IOException;
import java.io.PrintWriter;
import java.lang.management.ManagementFactory;
import java.lang.reflect.Constructor;
import java.lang.reflect.Method;
import java.util.ArrayList;
import java.util.Collections;
import java.util.Iterator;
import java.util.List;
import java.util.Map;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.TimeUnit;

import org.junit.AfterClass;
import org.junit.BeforeClass;
import org.junit.Test;

import org.apache.cassandra.SchemaLoader;
import org.apache.cassandra.Util;
import org.apache.cassandra.config.DatabaseDescriptor;
import org.apache.cassandra.db.ColumnFamilyStore;
import org.apache.cassandra.db.Keyspace;
import org.apache.cassandra.db.RowUpdateBuilder;
import org.apache.cassandra.db.compaction.CompactionsTest;
import org.apache.cassandra.dht.ByteOrderedPartitioner;
import org.apache.cassandra.dht.IPartitioner;
import org.apache.cassandra.dht.Murmur3Partitioner;
import org.apache.cassandra.dht.RandomPartitioner;
import org.apache.cassandra.dht.Range;
import org.apache.cassandra.dht.Token;
import org.apache.cassandra.io.sstable.format.SSTableReader;
import org.apache.cassandra.locator.InetAddressAndPort;
import org.apache.cassandra.net.Message;
import org.apache.cassandra.net.MessagingService;
import org.apache.cassandra.net.Verb;
import org.apache.cassandra.repair.messages.ValidationResponse;
import org.apache.cassandra.repair.state.ValidationState;
import org.apache.cassandra.schema.KeyspaceParams;
import org.apache.cassandra.service.ActiveRepairService;
import org.apache.cassandra.streaming.PreviewKind;
import org.apache.cassandra.utils.ByteBufferUtil;
import org.apache.cassandra.utils.Clock;
import org.apache.cassandra.utils.MerkleTree;
import org.apache.cassandra.utils.MerkleTrees;
import org.apache.cassandra.utils.ObjectSizes;
import org.apache.cassandra.utils.TimeUUID;

import static java.util.Collections.singletonList;
import static org.apache.cassandra.utils.TimeUUID.Generator.nextTimeUUID;
import static org.junit.Assert.assertEquals;

public class RepairSessionSpaceTreeTest
{
    private static final String KS = "RepairSessionSpaceTreeTest";
    private static final String T14 = "Standard14";   // 2^14 partitions: U3 init path, U4
    private static final String T16 = "Standard16";   // 2^16 partitions: U3 split path (amended 2026-10-14)
    private static final long MIB = 1048576L;

    private static PrintWriter out;
    private static int mismatches = 0;
    private static int defaultSpace;
    private static int defaultDepth;

    @BeforeClass
    public static void setUp() throws Exception
    {
        String f = System.getProperty("stage4.out");
        if (f != null)
            out = new PrintWriter(new FileWriter(f, true), true);
        SchemaLoader.prepareServer();
        SchemaLoader.createKeyspace(KS, KeyspaceParams.simple(1),
                                    SchemaLoader.standardCFMD(KS, T14),
                                    SchemaLoader.standardCFMD(KS, T16));
        defaultSpace = DatabaseDescriptor.getRepairSessionSpaceInMiB();
        defaultDepth = DatabaseDescriptor.getRepairSessionMaxTreeDepth();
        value("config", "partitioner=" + DatabaseDescriptor.getPartitioner().getClass().getSimpleName()
                        + " repair_session_space_default_MiB=" + defaultSpace
                        + " repair_session_max_tree_depth=" + defaultDepth
                        + " maxMemory=" + Runtime.getRuntime().maxMemory()
                        + " RF=" + Keyspace.open(KS).getReplicationStrategy().getReplicationFactor().allReplicas);
        load(T14, 1 << 14);
        load(T16, 1 << 16);
    }

    @AfterClass
    public static void tearDown()
    {
        DatabaseDescriptor.setRepairSessionSpaceInMiB(defaultSpace);
        DatabaseDescriptor.setRepairSessionMaxTreeDepth(defaultDepth);
        value("summary", "mismatches=" + mismatches);
        if (out != null)
            out.close();
    }

    private static void load(String table, int rows)
    {
        ColumnFamilyStore cfs = Keyspace.open(KS).getColumnFamilyStore(table);
        cfs.disableAutoCompaction();
        if (rows <= 1 << 14)
            CompactionsTest.populate(KS, table, 0, rows, 0);   // keys 0..rows inclusive, 10 rows each, as ValidatorTest.testSizeLimiting
        else
            populateOneRow(cfs, rows);                        // the same keys, one row each, so 2^16 keys fit one memtable (one sstable)
        Util.flush(cfs);
        assertEquals(1, cfs.getLiveSSTables().size());
        value("load", table + " keys=" + (rows + 1) + " sstables=" + cfs.getLiveSSTables().size());
    }

    /** As CompactionsTest.populate(), but one row per key. */
    private static void populateOneRow(ColumnFamilyStore cfs, int rows)
    {
        long timestamp = System.currentTimeMillis();
        for (int i = 0; i <= rows; i++)
            new RowUpdateBuilder(cfs.metadata(), timestamp, 0, Util.dk(Integer.toString(i)).getKey())
                .clustering("0")
                .add("val", ByteBufferUtil.EMPTY_BYTE_BUFFER)
                .build()
                .applyUnsafe();
    }

    // ---------------------------------------------------------------- output

    private static void emit(String line)
    {
        System.out.println(line);
        if (out != null)
            out.println(line);
    }

    private static void value(String name, String text)
    {
        emit("STAGE4 value " + name + " " + text);
    }

    private static boolean check(String name, Object expected, Object actual)
    {
        boolean ok = String.valueOf(expected).equals(String.valueOf(actual));
        if (!ok)
            mismatches++;
        emit("STAGE4 check " + name + " expected=" + expected + " actual=" + actual + (ok ? " ok" : " MISMATCH"));
        return ok;
    }

    private static boolean checkTrue(String name, String relation, boolean holds)
    {
        if (!holds)
            mismatches++;
        emit("STAGE4 check " + name + " expected=" + relation + " actual=" + holds + (holds ? " ok" : " MISMATCH"));
        return holds;
    }

    // ---------------------------------------------------------------- reflection on MerkleTree's package-private parts

    private static final Class<?> LEAF, INNER, NODE;
    static
    {
        try
        {
            LEAF = Class.forName("org.apache.cassandra.utils.MerkleTree$OnHeapLeaf");
            INNER = Class.forName("org.apache.cassandra.utils.MerkleTree$OnHeapInner");
            NODE = Class.forName("org.apache.cassandra.utils.MerkleTree$OnHeapNode");
        }
        catch (ClassNotFoundException e)
        {
            throw new AssertionError(e);
        }
    }

    private static Object newLeaf(byte[] hash) throws Exception
    {
        Constructor<?> c = hash == null ? LEAF.getDeclaredConstructor() : LEAF.getDeclaredConstructor(byte[].class);
        c.setAccessible(true);
        return hash == null ? c.newInstance() : c.newInstance((Object) hash);
    }

    private static Object newInner(Token t, Object l, Object r) throws Exception
    {
        Constructor<?> c = INNER.getDeclaredConstructor(Token.class, NODE, NODE);
        c.setAccessible(true);
        return c.newInstance(t, l, r);
    }

    /**
     * Leaves actually present in the tree, counted by walking it (not the size field). Distinct leaf nodes by identity:
     * TreeRangeIterator yields the leaf whose range wraps around twice by design (MerkleTree.java:623-626), so a plain
     * count of its ranges is one too high on a full-ring tree (fixed 2026-10-14, results section 3, defect 1).
     */
    private static long countLeaves(MerkleTree t) throws Exception
    {
        Method m = MerkleTree.class.getDeclaredMethod("rangeIterator");
        m.setAccessible(true);
        java.lang.reflect.Field nodeField = MerkleTree.TreeRange.class.getDeclaredField("node");
        nodeField.setAccessible(true);
        java.util.Set<Object> leaves = Collections.newSetFromMap(new java.util.IdentityHashMap<>());
        for (Object range : (Iterable<?>) m.invoke(t))
            leaves.add(nodeField.get(range));
        return leaves.size();
    }

    /** The sizes estimatedMaxDepthForBytes() uses (MerkleTree.java:1520-1541), recomputed the same way. */
    private static long[] leafAndInner(IPartitioner p) throws Exception
    {
        Object left = newLeaf(new byte[32]);
        Object right = newLeaf(new byte[32]);
        Object inner = newInner(p.getMinimumToken(), left, right);
        Method fill = INNER.getDeclaredMethod("fillInnerHashes");
        fill.setAccessible(true);
        fill.invoke(inner);
        long innerTokenSize = ObjectSizes.measureDeep(p.getMinimumToken());
        long realInnerTokenSize = p.getMinimumToken().getHeapSize();
        long sizeOfLeaf = ObjectSizes.measureDeep(left);
        long sizeOfInner = ObjectSizes.measureDeep(inner) - (ObjectSizes.measureDeep(left) + ObjectSizes.measureDeep(right) + innerTokenSize) + realInnerTokenSize;
        return new long[]{ sizeOfLeaf, sizeOfInner };
    }

    // ---------------------------------------------------------------- U1: the check alone

    @Test
    public void u1CheckAlone() throws Exception
    {
        IPartitioner p = RandomPartitioner.instance;
        com.sun.management.ThreadMXBean tmx = (com.sun.management.ThreadMXBean) ManagementFactory.getThreadMXBean();
        tmx.setThreadAllocatedMemoryEnabled(true);
        long tid = Thread.currentThread().getId();

        long shallowLeaf = ObjectSizes.measure(newLeaf(null));
        long shallowInner = ObjectSizes.measure(newInner(p.getMinimumToken(), newLeaf(null), newLeaf(null)));
        long minSplit = shallowInner + 2 * shallowLeaf;
        value("U1 shallow", "OnHeapLeaf=" + shallowLeaf + " OnHeapInner=" + shallowInner + " inner+2leaves=" + minSplit);

        long baseline = 0;
        for (int i = 0; i < 1000; i++)
        {
            long a0 = tmx.getThreadAllocatedBytes(tid);
            long a1 = tmx.getThreadAllocatedBytes(tid);
            baseline = Math.max(baseline, a1 - a0);
        }
        value("U1 baseline", "max_empty_interval_bytes=" + baseline);

        for (long M : new long[]{ 2, 1024, 16384 })
        {
            Range<Token> full = new Range<>(p.getMinimumToken(), p.getMinimumToken());
            MerkleTree t = new MerkleTree(p, full, MerkleTree.RECOMMENDED_DEPTH, M);
            int budget = (int) M * 4 + 1000;
            List<Token> tokens = new ArrayList<>(budget);
            for (int i = 0; i < budget; i++)
                tokens.add(p.getRandomToken());

            long minAlloc = Long.MAX_VALUE, maxAlloc = 0, sumAlloc = 0, ok = 0;
            boolean refused = false;
            int i = 0;
            for (; i < budget; i++)
            {
                long a0 = tmx.getThreadAllocatedBytes(tid);
                boolean r = t.split(tokens.get(i));
                long a1 = tmx.getThreadAllocatedBytes(tid);
                if (!r)
                {
                    refused = true;
                    break;
                }
                ok++;
                long a = a1 - a0;
                minAlloc = Math.min(minAlloc, a);
                maxAlloc = Math.max(maxAlloc, a);
                sumAlloc += a;
            }
            check("U1 M=" + M + " first_false_reached", true, refused);
            check("U1 M=" + M + " size_at_first_false", M, t.size());
            check("U1 M=" + M + " leaves_counted", M, countLeaves(t));
            check("U1 M=" + M + " successful_splits", M - 1, ok);
            if (ok > 0)
            {
                value("U1 M=" + M + " alloc_per_success", "min=" + minAlloc + " mean=" + (sumAlloc / ok) + " max=" + maxAlloc);
                checkTrue("U1 M=" + M + " success_alloc_at_least_inner_plus_2_leaves", ">=" + minSplit, minAlloc >= minSplit);
            }

            long refusedMax = 0;
            boolean allFalse = true;
            for (int k = 0; k < 1000; k++)
            {
                Token tok = tokens.get((i + 1 + k) % budget);
                long a0 = tmx.getThreadAllocatedBytes(tid);
                boolean r = t.split(tok);
                long a1 = tmx.getThreadAllocatedBytes(tid);
                allFalse &= !r;
                refusedMax = Math.max(refusedMax, a1 - a0);
            }
            check("U1 M=" + M + " further_calls_all_false", true, allFalse);
            check("U1 M=" + M + " size_unchanged_after_1000_refusals", M, t.size());
            value("U1 M=" + M + " refused_alloc", "max_bytes=" + refusedMax + " baseline=" + baseline);
            checkTrue("U1 M=" + M + " refused_alloc_within_baseline", "<=" + baseline, refusedMax <= baseline);
        }
    }

    // ---------------------------------------------------------------- U2: init()

    @Test
    public void u2Init() throws Exception
    {
        IPartitioner p = RandomPartitioner.instance;
        for (long[] mExp : new long[][]{ { 2, 2 }, { 1024, 1024 }, { 16384, 16384 }, { 1000, 512 } })
        {
            long M = mExp[0];
            MerkleTree t = new MerkleTree(p, new Range<>(p.getMinimumToken(), p.getMinimumToken()), MerkleTree.RECOMMENDED_DEPTH, M);
            t.init();
            check("U2 M=" + M + " size", mExp[1], t.size());
            check("U2 M=" + M + " leaves_counted", mExp[1], countLeaves(t));
            long deep = ObjectSizes.measureDeep(t);
            value("U2 M=" + M + " heap", "measureDeep=" + deep + " per_leaf=" + (deep / mExp[1]));
        }
    }

    // ---------------------------------------------------------------- U3 and U4: the derivation, through a real validation

    private static final class Result
    {
        long n, size, maxsize, leaves, deep;
        int trees;
    }

    private static Result validate(String table, int spaceMiB, boolean even) throws Exception
    {
        ColumnFamilyStore cfs = Keyspace.open(KS).getColumnFamilyStore(table);
        DatabaseDescriptor.setRepairSessionSpaceInMiB(spaceMiB);
        SSTableReader sstable = cfs.getLiveSSTables().iterator().next();
        Range<Token> range = new Range<>(sstable.getFirst().getToken(), sstable.getLast().getToken());
        TimeUUID sid = nextTimeUUID();
        RepairJobDesc desc = new RepairJobDesc(sid, nextTimeUUID(), KS, table, singletonList(range));
        InetAddressAndPort host = InetAddressAndPort.getByName("127.0.0.2");
        ActiveRepairService.instance().registerParentRepairSession(sid, host, singletonList(cfs), desc.ranges, false,
                                                                   ActiveRepairService.UNREPAIRED_SSTABLE, false, PreviewKind.NONE);
        CompletableFuture<Message<?>> sink = new CompletableFuture<>();
        MessagingService.instance().outboundSink.add((m, to) -> {
            if (m.verb() == Verb.VALIDATION_RSP)
                sink.complete(m);
            return false;
        });
        try
        {
            Validator v = new Validator(SharedContext.Global.instance, new ValidationState(Clock.Global.clock(), desc, host), 0, even, false, PreviewKind.NONE);
            ValidationManager.instance.submitValidation(cfs, v);
            Message<?> m = sink.get(120, TimeUnit.SECONDS);
            MerkleTrees trees = ((ValidationResponse) m.payload).trees;
            Result r = new Result();
            r.n = sstable.estimatedKeysForRanges(Collections.singleton(range));
            Iterator<Map.Entry<Range<Token>, MerkleTree>> it = trees.iterator();
            while (it.hasNext())
            {
                MerkleTree t = it.next().getValue();
                r.trees++;
                r.size += t.size();
                r.maxsize += t.maxsize();
                r.leaves += countLeaves(t);
                r.deep += ObjectSizes.measureDeep(t);
            }
            return r;
        }
        finally
        {
            MessagingService.instance().outboundSink.clear();
        }
    }

    /** ValidationManager.createMerkleTrees():62-80 for one range with share 1, RF 1, in the code's own types. */
    private static long formula(IPartitioner p, int spaceMiB, long n)
    {
        long availableBytes = (spaceMiB * 1048576) / 1;            // int product, as :62
        int rangeAvailableBytes = Math.max(1, (int) (1.0 * availableBytes));
        int estimatedMaxDepth = MerkleTree.estimatedMaxDepthForBytes(p, rangeAvailableBytes, 32);
        int maxDepth = Math.min(estimatedMaxDepth, DatabaseDescriptor.getRepairSessionMaxTreeDepth());
        int depth = n > 0 ? (int) Math.min(Math.ceil(Math.log(n) / Math.log(2)), maxDepth) : 0;
        return (long) Math.pow(2, depth);
    }

    private static void report(String name, Result r, long casePrediction, IPartitioner p, int s, boolean splitPath)
    {
        value(name, "n=" + r.n + " ceil_log2_n=" + (int) Math.ceil(Math.log(r.n) / Math.log(2)) + " trees=" + r.trees
                    + " size=" + r.size + " maxsize=" + r.maxsize + " leaves=" + r.leaves
                    + " measureDeep=" + r.deep + " per_leaf=" + (r.leaves > 0 ? r.deep / r.leaves : 0));
        check(name + " trees", 1, r.trees);
        check(name + " leaves_vs_case_prediction", casePrediction, r.leaves);
        check(name + " leaves_vs_formula", formula(p, s, r.n), r.leaves);
        check(name + " size_field_equals_leaves", r.leaves, r.size);
        if (splitPath)
            check(name + " split_stopped_at_maxsize(not_TooDeep)", r.maxsize, r.size);
    }

    @Test
    public void u3Derivation() throws Exception
    {
        // the depth table the cluster prediction uses, for both partitioners (amended 2026-10-14)
        for (IPartitioner p : new IPartitioner[]{ ByteOrderedPartitioner.instance, Murmur3Partitioner.instance })
        {
            long[] li = leafAndInner(p);
            StringBuilder sb = new StringBuilder("leaf=" + li[0] + " inner=" + li[1] + " leaf+inner=" + (li[0] + li[1]));
            for (long b : new long[]{ MIB / 2, MIB, 2 * MIB, 4 * MIB, 8 * MIB, 32 * MIB, 64 * MIB })
                sb.append(" d(").append(b / 1024).append("KiB)=").append(MerkleTree.estimatedMaxDepthForBytes(p, b, 32));
            value("U3 depth_table " + p.getClass().getSimpleName(), sb.toString());
        }

        IPartitioner p = DatabaseDescriptor.getPartitioner();
        DatabaseDescriptor.setRepairSessionMaxTreeDepth(20);
        // init path (evenTreeDistribution = true), 2^14 partitions
        int[][] initRows = { { 1, 1 << 12 }, { 2, 1 << 13 }, { 4, 1 << 14 } };
        for (int[] row : initRows)
            report("U3 init s=" + row[0], validate(T14, row[0], true), row[1], p, row[0], false);
        // split path (evenTreeDistribution = false, ByteOrderedPartitioner), 2^16 partitions
        int[][] splitRows = { { 1, 1 << 12 }, { 2, 1 << 13 } };
        for (int[] row : splitRows)
            report("U3 split s=" + row[0], validate(T16, row[0], false), row[1], p, row[0], true);
        // depth cap
        DatabaseDescriptor.setRepairSessionMaxTreeDepth(10);
        try
        {
            report("U3 depthcap10 s=64", validate(T14, 64, true), 1 << 10, p, 64, false);
        }
        finally
        {
            DatabaseDescriptor.setRepairSessionMaxTreeDepth(20);
        }
    }

    @Test
    public void u4Overflow() throws Exception
    {
        IPartitioner p = DatabaseDescriptor.getPartitioner();
        DatabaseDescriptor.setRepairSessionMaxTreeDepth(20);
        int[][] rows = { { 2047, 1 << 14 }, { 2048, 2 }, { 4096, 2 }, { 4097, 1 << 12 }, { 5120, 1 << 14 } };
        for (int[] row : rows)
        {
            int s = row[0];
            int intProduct = s * 1048576;
            value("U4 s=" + s, "int_product=" + intProduct + " intended=" + (s * MIB));
            report("U4 s=" + s, validate(T14, s, true), row[1], p, s, false);
        }
    }

    @AfterClass
    public static void failOnMismatch()
    {
        assertEquals("STAGE4 mismatches (see the STAGE4 lines)", 0, mismatches);
    }
}
