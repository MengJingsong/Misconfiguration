/*
 * Stage-4 harness, autonomous: repair_session_space-setrepairsessionspaceinmib-sizeinmib (unit tier B2, added by the 2026-10-27 audit).
 * Helpers (reflection, countLeaves, validate, formula) are copied from the closed harness RepairSessionSpaceTreeTest.
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
import org.apache.cassandra.config.DataStorageSpec;
import org.apache.cassandra.config.DatabaseDescriptor;
import org.apache.cassandra.exceptions.ConfigurationException;
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

public class SessionSpaceSetterTest
{
    private static final String KS = "SessionSpaceSetterTest";
    private static final String T14 = "Standard14";   // 2^14 partitions: U3 init path, U4
    private static final String T16 = "Standard16";   // unused here
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

        private static Result validateNoSet(String table) throws Exception
    {
        ColumnFamilyStore cfs = Keyspace.open(KS).getColumnFamilyStore(table);
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
            Validator v = new Validator(SharedContext.Global.instance, new ValidationState(Clock.Global.clock(), desc, host), 0, true, false, PreviewKind.NONE);
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

    // ---------------------------------------------------------------- S1..S4: the setter check, and what the stored value does

    /** Calls the setter; returns whatever it threw (any Throwable: attempt 1 of the run crashed on an IllegalArgumentException the prediction did not foresee), or null. */
    private static Throwable setExpectReject(int v)
    {
        try
        {
            DatabaseDescriptor.setRepairSessionSpaceInMiB(v);
            return null;
        }
        catch (Throwable e)
        {
            return e;
        }
    }

    @Test
    public void s1SetterOutcomes() throws Exception
    {
        com.sun.management.ThreadMXBean tmx = (com.sun.management.ThreadMXBean) ManagementFactory.getThreadMXBean();
        tmx.setThreadAllocatedMemoryEnabled(true);
        long tid = Thread.currentThread().getId();
        long maxMem = Runtime.getRuntime().maxMemory();
        int warnAbove = (int) (maxMem / (4 * 1048576));
        value("S1 config", "maxMemory=" + maxMem + " heap_pressure_warn_above_MiB=" + warnAbove);
        DatabaseDescriptor.setRepairSessionSpaceInMiB(7);
        for (int v : new int[]{ 0, -1, Integer.MIN_VALUE })
        {
            long a0 = tmx.getThreadAllocatedBytes(tid);
            Throwable e = setExpectReject(v);
            long a1 = tmx.getThreadAllocatedBytes(tid);
            checkTrue("S1 reject v=" + v + " throws_ConfigurationException", "thrown", e instanceof ConfigurationException);
            if (e != null)
                check("S1 reject v=" + v + " message", "Cannot set repair_session_space to " + v + " < 1 mebibyte", e.getMessage());
            check("S1 reject v=" + v + " getter_unchanged", 7, DatabaseDescriptor.getRepairSessionSpaceInMiB());
            value("S1 reject v=" + v, "allocated_bytes_of_the_call=" + (a1 - a0));
            // the MBean wrapper turns it into IllegalArgumentException (ActiveRepairService.java:338-345)
            boolean iae = false;
            try { ActiveRepairService.instance().setRepairSessionSpaceInMiB(v); }
            catch (IllegalArgumentException x) { iae = true; }
            checkTrue("S1 reject v=" + v + " mbean_IllegalArgumentException", "thrown", iae);
            check("S1 reject v=" + v + " getter_unchanged_after_mbean", 7, DatabaseDescriptor.getRepairSessionSpaceInMiB());
        }
        for (int v : new int[]{ 1, 2, 4, 128, warnAbove, warnAbove + 1, 2048, Integer.MAX_VALUE })
        {
            long a0 = tmx.getThreadAllocatedBytes(tid);
            Throwable e = setExpectReject(v);
            long a1 = tmx.getThreadAllocatedBytes(tid);
            check("S1 accept v=" + v + " no_exception", "null", e == null ? "null" : e.getClass().getName() + ": " + e.getMessage());
            check("S1 accept v=" + v + " getter_equals", v, DatabaseDescriptor.getRepairSessionSpaceInMiB());
            value("S1 accept v=" + v, "allocated_bytes_of_the_call=" + (a1 - a0) + " above_warn_threshold=" + (v > warnAbove));
        }
    }

    @Test
    public void s2TreeFollowsStoredValue() throws Exception
    {
        IPartitioner p = DatabaseDescriptor.getPartitioner();
        DatabaseDescriptor.setRepairSessionMaxTreeDepth(20);
        // accepted values: the tree built by a real validation follows the stored value (the closed case's init path, 2^14 partitions)
        long[] expect = { 1 << 12, 1 << 13, 1 << 14 };
        int[] vals = { 1, 2, 4 };
        for (int i = 0; i < vals.length; i++)
            report("S2 accepted s=" + vals[i], validate(T14, vals[i], true), expect[i], p, vals[i], false);
        // a rejected value after an accepted one leaves the stored value, and so the tree, as it was
        DatabaseDescriptor.setRepairSessionSpaceInMiB(2);
        for (int bad : new int[]{ 0, -1 })
        {
            checkTrue("S2 reject " + bad, "thrown", setExpectReject(bad) instanceof ConfigurationException);
            Result r = validate(T14, DatabaseDescriptor.getRepairSessionSpaceInMiB(), true);   // validate() re-sets the (unchanged) stored value
            report("S2 after_rejected " + bad + " stored=2", r, 1 << 13, p, 2, false);
        }
        // accepted but large: the stored value is unbounded above, the tree is not larger (32-bit overflow, as the closed U4)
        for (int big : new int[]{ 1024, 2047, 2048, Integer.MAX_VALUE })
        {
            Result r;
            try
            {
                r = validate(T14, big, true);
            }
            catch (Throwable t)
            {
                value("S2 big s=" + big, "setter_threw " + t.getClass().getName() + ": " + t.getMessage() + " (no validation run)");
                mismatches++;
                emit("STAGE4 check S2 big s=" + big + " validation_ran expected=true actual=false MISMATCH");
                continue;
            }
            value("S2 big s=" + big, "int_product=" + (big * 1048576) + " leaves=" + r.leaves);
            check("S2 big s=" + big + " leaves_vs_formula", formula(p, big, r.n), r.leaves);
            checkTrue("S2 big s=" + big + " not_larger_than_partition_term", "<=" + (1L << (int) Math.ceil(Math.log(r.n) / Math.log(2))),
                      r.leaves <= (1L << (int) Math.ceil(Math.log(r.n) / Math.log(2))));
        }
    }

    @Test
    public void s3CheckBypassedRawValue() throws Exception
    {
        // What the world looks like without the check: write the raw config field the way the yaml loader does (no setter, no check).
        IPartitioner p = DatabaseDescriptor.getPartitioner();
        DatabaseDescriptor.setRepairSessionMaxTreeDepth(20);
        Result base = validate(T14, 1, true);
        value("S3 s=1", "leaves=" + base.leaves);
        for (int raw : new int[]{ 0, -1, -1000 })
        {
            try
            {
                DatabaseDescriptor.getRawConfig().repair_session_space = new DataStorageSpec.IntMebibytesBound(raw);
            }
            catch (Throwable t)
            {
                value("S3 raw=" + raw, "IntMebibytesBound constructor threw " + t.getClass().getName() + ": " + t.getMessage() + " (no config object, no validation run)");
                mismatches++;
                emit("STAGE4 check S3 raw=" + raw + " config_object_constructible expected=true actual=false MISMATCH");
                continue;
            }
            Result r = validateNoSet(T14);
            value("S3 raw=" + raw, "leaves=" + r.leaves + " measureDeep=" + r.deep);
            check("S3 raw=" + raw + " leaves_vs_formula", formula(p, raw, r.n), r.leaves);
            checkTrue("S3 raw=" + raw + " not_larger_than_s1", "<=" + base.leaves, r.leaves <= base.leaves);
        }
    }

    @AfterClass
    public static void failOnMismatch()
    {
        assertEquals("STAGE4 mismatches (see the STAGE4 lines)", 0, mismatches);
    }
}
