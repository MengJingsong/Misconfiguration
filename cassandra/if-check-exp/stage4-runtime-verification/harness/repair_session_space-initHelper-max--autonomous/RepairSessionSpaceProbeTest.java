/*
 * Stage-4 harness: repair_session_space-initHelper-max--autonomous, unit tier (B2 as amended U1-U4 and D1, 2026-10-27).
 * Not upstream code. Copied into test/unit/org/apache/cassandra/repair/ of a clone at cassandra-5.0.9 by unit-run.sh.
 * Structure adapted from harness/repair_session_space-applySimpleConfig-repair_session_space--autonomous/ValidatorSpaceCapTest.java
 * (itself modelled on ValidatorTest.testSizeLimiting); values and checks are this case's own.
 *
 * Lines (stdout and the file named by -Dstage4.out):
 *   STAGE4 reading sweep|control s=.. readback=.. sstables=.. estKeys=.. pc=.. d_est=.. expected=.. size=.. leaves=.. rowCount=.. bytes=.. limit=..
 *   STAGE4 reading init k=.. hashdepth=.. size=.. leaves=..
 *   STAGE4 value <name> <text>        configuration / computed values, not readings
 * The test asserts nothing about readings; it fails only if a step cannot run.
 * -Dstage4.keys=<n> (default 262144 = 2^18) and -Dstage4.svalues=1,2,... are used only by the shakedown.
 */
package org.apache.cassandra.repair;

import java.io.FileWriter;
import java.io.PrintWriter;
import java.util.Collections;
import java.util.HashSet;
import java.util.Iterator;
import java.util.Map;
import java.util.Set;
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
import org.apache.cassandra.db.compaction.CompactionsTest;
import org.apache.cassandra.dht.IPartitioner;
import org.apache.cassandra.dht.Murmur3Partitioner;
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
import org.apache.cassandra.utils.Clock;
import org.apache.cassandra.utils.MerkleTree;
import org.apache.cassandra.utils.MerkleTrees;
import org.apache.cassandra.utils.ObjectSizes;
import org.apache.cassandra.utils.TimeUUID;

import static java.util.Collections.singletonList;
import static org.apache.cassandra.utils.TimeUUID.Generator.nextTimeUUID;

public class RepairSessionSpaceProbeTest
{
    private static final String KS = "RepairSessionSpaceProbeTest";
    private static final String CF = "Standard1";
    private static PrintWriter out;

    @BeforeClass
    public static void setUp() throws Exception
    {
        String f = System.getProperty("stage4.out");
        if (f != null)
            out = new PrintWriter(new FileWriter(f, true), true);
        SchemaLoader.prepareServer();
        // runbook-defect fix D1 (2026-10-27): the unit yaml's partitioner is ByteOrderedPartitioner (test/conf/cassandra.yaml:18);
        // B1 and B2f are about Murmur3, so the table is created under Murmur3 (as RepairMessageVerbHandlerOutOfRangeTest does)
        DatabaseDescriptor.setPartitionerUnsafe(Murmur3Partitioner.instance);
        SchemaLoader.createKeyspace(KS, KeyspaceParams.simple(1), SchemaLoader.standardCFMD(KS, CF));
        value("config", "partitioner=" + DatabaseDescriptor.getPartitioner().getClass().getSimpleName()
                        + " table_partitioner=" + Keyspace.open(KS).getColumnFamilyStore(CF).getPartitioner().getClass().getSimpleName()
                        + " repair_session_space_default_MiB=" + DatabaseDescriptor.getRepairSessionSpaceInMiB()
                        + " repair_session_max_tree_depth=" + DatabaseDescriptor.getRepairSessionMaxTreeDepth()
                        + " maxMemory=" + Runtime.getRuntime().maxMemory()
                        + " RF=" + Keyspace.open(KS).getReplicationStrategy().getReplicationFactor().allReplicas);
    }

    @AfterClass
    public static void tearDown()
    {
        if (out != null)
            out.close();
    }

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

    private static long distinctLeaves(MerkleTrees trees)
    {
        Set<String> seen = new HashSet<>();
        for (MerkleTree.TreeRange r : trees.rangeIterator())
            seen.add(r.left + ":" + r.right);
        return seen.size();
    }

    /** One validation of the populated table with repair_session_space = s MiB (U2, U3). */
    private static void validate(String label, ColumnFamilyStore cfs, Range<Token> range, long estKeys, int s) throws Exception
    {
        DatabaseDescriptor.setRepairSessionSpaceInMiB(s);
        int readBack = DatabaseDescriptor.getRepairSessionSpaceInMiB();
        IPartitioner p = cfs.getPartitioner();
        int rf = cfs.keyspace.getReplicationStrategy().getReplicationFactor().allReplicas;
        long budget = ((long) s * 1048576L) / rf;       // ValidationManager.java:62-63 (ratio 1: one range)
        int dEst = MerkleTree.estimatedMaxDepthForBytes(p, (int) budget, 32);
        int pc = (int) Math.ceil(Math.log(estKeys) / Math.log(2));
        int dExp = Math.min(Math.min(dEst, DatabaseDescriptor.getRepairSessionMaxTreeDepth()), pc);

        TimeUUID sid = nextTimeUUID();
        RepairJobDesc desc = new RepairJobDesc(sid, nextTimeUUID(), KS, CF, singletonList(range));
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
            Message<?> m = sink.get(600, TimeUnit.SECONDS);
            MerkleTrees trees = ((ValidationResponse) m.payload).trees;
            int nTrees = 0;
            MerkleTree tree = null;
            Iterator<Map.Entry<Range<Token>, MerkleTree>> it = trees.iterator();
            while (it.hasNext())
            {
                tree = it.next().getValue();
                nTrees++;
            }
            long bytes = ObjectSizes.measureDeep(tree) - ObjectSizes.measureDeep(p);   // before rowCount (U3)
            long leaves = distinctLeaves(trees);
            long rows = trees.rowCount();
            emit("STAGE4 reading " + label + " s=" + s + " readback=" + readBack
                 + " sstables=" + cfs.getLiveSSTables().size() + " trees=" + nTrees + " estKeys=" + estKeys + " pc=" + pc
                 + " d_est=" + dEst + " expected=" + (1L << dExp) + " size=" + tree.size() + " leaves=" + leaves
                 + " rowCount=" + rows + " bytes=" + bytes + " limit=" + ((long) s * 1048576L));
        }
        finally
        {
            MessagingService.instance().outboundSink.clear();
        }
    }

    private static void initControl(int k, int hashdepth)
    {
        Token min = Murmur3Partitioner.instance.getMinimumToken();
        MerkleTrees mt = new MerkleTrees(Murmur3Partitioner.instance);
        MerkleTree t = mt.addMerkleTree((int) (1L << k), (byte) hashdepth, new Range<>(min, min));
        mt.init();
        emit("STAGE4 reading init k=" + k + " hashdepth=" + hashdepth + " size=" + t.size() + " leaves=" + distinctLeaves(mt));
    }

    @Test
    public void probe() throws Exception
    {
        int keys = Integer.getInteger("stage4.keys", 1 << 18);
        String sv = System.getProperty("stage4.svalues", "1,2,4,8,16");
        int control = Integer.getInteger("stage4.control", 64);

        // value lines for B3f (C6): cluster budgets S*2^20/3, Murmur3, this JDK
        for (int s : new int[]{ 1, 4, 16, 64, 127, 128, 1024 })
        {
            long b = ((long) s * 1048576L) / 3;
            value("cluster_d", "s=" + s + " budget=" + b + " d=" + MerkleTree.estimatedMaxDepthForBytes(Murmur3Partitioner.instance, (int) b, 32));
        }

        Keyspace ks = Keyspace.open(KS);
        ColumnFamilyStore cfs = ks.getColumnFamilyStore(CF);
        cfs.clearUnsafe();
        cfs.disableAutoCompaction();
        long t0 = System.nanoTime();
        CompactionsTest.populate(KS, CF, 0, keys, 0);     // keys 0..keys inclusive (U2)
        Util.flush(cfs);
        value("load", "keys_to=" + keys + " ms=" + (System.nanoTime() - t0) / 1_000_000 + " sstables=" + cfs.getLiveSSTables().size());

        Token first = null, last = null;
        for (SSTableReader r : cfs.getLiveSSTables())
        {
            if (first == null || r.getFirst().getToken().compareTo(first) < 0) first = r.getFirst().getToken();
            if (last == null || r.getLast().getToken().compareTo(last) > 0) last = r.getLast().getToken();
        }
        Range<Token> range = new Range<>(first, last);
        long estKeys = 0;
        for (SSTableReader r : cfs.getLiveSSTables())
            estKeys += r.estimatedKeysForRanges(Collections.singleton(range));

        for (String x : sv.split(","))
            validate("sweep", cfs, range, estKeys, Integer.parseInt(x.trim()));
        validate("control", cfs, range, estKeys, control);

        initControl(8, 126);
        initControl(12, 126);
        initControl(16, 126);
        initControl(12, 5);
        emit("STAGE4 end");
    }
}
