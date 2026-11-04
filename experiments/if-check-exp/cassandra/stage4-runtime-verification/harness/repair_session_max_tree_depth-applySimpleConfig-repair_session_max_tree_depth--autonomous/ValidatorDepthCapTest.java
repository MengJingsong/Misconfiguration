/*
 * Stage-4 harness: repair_session_max_tree_depth-applySimpleConfig-repair_session_max_tree_depth--autonomous, unit tier
 * (B2, as amended 2026-10-24). Not upstream code. Copied into test/unit/org/apache/cassandra/repair/ of a clone at
 * cassandra-5.0.9 by unit-run.sh.
 *
 * Prints one line per reading, to stdout and to the file named by -Dstage4.out:
 *   STAGE4 reading <name> k=v ...     raw readings
 *   STAGE4 value <name> <text>        configuration and computed values (not readings)
 * The test asserts nothing about the readings (the session draws the conclusion from them); it fails only if a step
 * cannot run (timeout, an exception other than the expected one).
 * Modelled on ValidatorTest.testSizeLimiting (schema, CompactionsTest.populate, the outbound sink, submitValidation).
 */
package org.apache.cassandra.repair;

import java.io.FileWriter;
import java.io.PrintWriter;
import java.util.Collections;
import java.util.Iterator;
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
import org.apache.cassandra.db.compaction.CompactionsTest;
import org.apache.cassandra.dht.IPartitioner;
import org.apache.cassandra.dht.Murmur3Partitioner;
import org.apache.cassandra.dht.Range;
import org.apache.cassandra.dht.Token;
import org.apache.cassandra.exceptions.ConfigurationException;
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

public class ValidatorDepthCapTest
{
    private static final String KS = "ValidatorDepthCapTest";
    private static final String CF = "Standard1";
    private static final int KEYS_TO = 1 << 16;          // populate(ks, cf, 0, 1 << 16, 0): keys 0..2^16 inclusive (B2c)
    private static final int SPACE = 256;                // B2b
    private static PrintWriter out;

    @BeforeClass
    public static void setUp() throws Exception
    {
        String f = System.getProperty("stage4.out");
        if (f != null)
            out = new PrintWriter(new FileWriter(f, true), true);
        SchemaLoader.prepareServer();
        SchemaLoader.createKeyspace(KS, KeyspaceParams.simple(1), SchemaLoader.standardCFMD(KS, CF));
        value("config", "partitioner=" + DatabaseDescriptor.getPartitioner().getClass().getSimpleName()
                        + " repair_session_space_default_MiB=" + DatabaseDescriptor.getRepairSessionSpaceInMiB()
                        + " repair_session_max_tree_depth_default=" + DatabaseDescriptor.getRepairSessionMaxTreeDepth()
                        + " maxMemory=" + Runtime.getRuntime().maxMemory()
                        + " RF=" + rf());
    }

    @AfterClass
    public static void tearDown()
    {
        if (out != null)
            out.close();
    }

    private static int rf()
    {
        return Keyspace.open(KS).getReplicationStrategy().getReplicationFactor().allReplicas;
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

    private static int ceilLog2(long n)
    {
        return n > 0 ? (int) Math.ceil(Math.log(n) / Math.log(2)) : 0;   // as ValidationManager.java:79
    }

    /** B2e: clear, set (and read back), populate, flush, submit one validation, record. */
    private static void scenario(String name, int s, int depth) throws Exception
    {
        Keyspace ks = Keyspace.open(KS);
        ColumnFamilyStore cfs = ks.getColumnFamilyStore(CF);
        cfs.clearUnsafe();
        DatabaseDescriptor.setRepairSessionSpaceInMiB(s);
        DatabaseDescriptor.setRepairSessionMaxTreeDepth(depth);
        int spaceBack = DatabaseDescriptor.getRepairSessionSpaceInMiB();
        int depthBack = DatabaseDescriptor.getRepairSessionMaxTreeDepth();
        cfs.disableAutoCompaction();
        long t0 = System.nanoTime();
        CompactionsTest.populate(KS, CF, 0, KEYS_TO, 0);
        Util.flush(cfs);
        long loadMs = (System.nanoTime() - t0) / 1_000_000;

        Token first = null, last = null;
        for (SSTableReader r : cfs.getLiveSSTables())
        {
            if (first == null || r.getFirst().getToken().compareTo(first) < 0) first = r.getFirst().getToken();
            if (last == null || r.getLast().getToken().compareTo(last) > 0) last = r.getLast().getToken();
        }
        Range<Token> range = new Range<>(first, last);
        long estKeys = 0;                                   // as CassandraValidationIterator.java:227-236
        for (SSTableReader r : cfs.getLiveSSTables())
            estKeys += r.estimatedKeysForRanges(Collections.singleton(range));
        int D = ceilLog2(estKeys);

        IPartitioner p = cfs.getPartitioner();
        int dSpace = MerkleTree.estimatedMaxDepthForBytes(p, ((long) s * 1048576L) / rf(), 32);
        long expected = 1L << Math.min(D, Math.min(dSpace, depthBack));

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
            Message<?> m = sink.get(60, TimeUnit.SECONDS);
            MerkleTrees trees = ((ValidationResponse) m.payload).trees;
            int nTrees = 0;
            long leaves = 0;
            StringBuilder per = new StringBuilder();
            Iterator<Map.Entry<Range<Token>, MerkleTree>> it = trees.iterator();
            while (it.hasNext())
            {
                MerkleTree t = it.next().getValue();
                nTrees++;
                leaves += t.size();
                per.append(per.length() == 0 ? "" : ",").append(t.size());
            }
            long deep = ObjectSizes.measureDeep(trees);
            long ser = MerkleTrees.serializer.serializedSize(trees, MessagingService.current_version);
            emit("STAGE4 reading " + name + " s=" + s + " spaceback=" + spaceBack + " d=" + depth + " depthback=" + depthBack
                 + " sstables=" + cfs.getLiveSSTables().size() + " estKeys=" + estKeys + " D=" + D + " dSpace=" + dSpace
                 + " rowCount=" + trees.rowCount() + " trees=" + nTrees + " leaves=" + leaves + " perTree=" + per
                 + " expectedLeaves=" + expected + " measureDeep=" + deep + " serialized=" + ser + " loadMs=" + loadMs);
        }
        finally
        {
            MessagingService.instance().outboundSink.clear();
        }
    }

    @Test
    public void b2() throws Exception
    {
        IPartitioner p = DatabaseDescriptor.getPartitioner();
        // value lines: the space term (B2d), and the cluster-tier space terms frozen in B3a/B3h (re-printed as a check)
        value("space_depth", "partitioner=" + p.getClass().getSimpleName()
                             + " s=256 d=" + MerkleTree.estimatedMaxDepthForBytes(p, 256L * 1048576L, 32)
                             + " s=1 d=" + MerkleTree.estimatedMaxDepthForBytes(p, 1048576L, 32));
        for (int s : new int[]{ 4, 256, 1024 })
        {
            long b = (((long) s * 1048576L) / 3) / 3;
            value("murmur3_depth", "s=" + s + " budget=" + b
                                   + " d=" + MerkleTree.estimatedMaxDepthForBytes(Murmur3Partitioner.instance, b, 32)
                                   + " d095=" + MerkleTree.estimatedMaxDepthForBytes(Murmur3Partitioner.instance, (long) (b * 0.95), 32)
                                   + " d105=" + MerkleTree.estimatedMaxDepthForBytes(Murmur3Partitioner.instance, (long) (b * 1.05), 32));
        }
        DatabaseDescriptor.setRepairSessionSpaceInMiB(SPACE);
        value("space_set", "readback=" + DatabaseDescriptor.getRepairSessionSpaceInMiB());
        for (int d : new int[]{ 10, 12, 14, 16, 20 })
            scenario("sweep", SPACE, d);
        scenario("control", 1, 20);        // B2h
        DatabaseDescriptor.setRepairSessionSpaceInMiB(SPACE);
        value("restored", "space=" + DatabaseDescriptor.getRepairSessionSpaceInMiB()
                          + " depth=" + DatabaseDescriptor.getRepairSessionMaxTreeDepth());

        String cls = "none", msg = "";
        try
        {
            DatabaseDescriptor.setRepairSessionMaxTreeDepth(9);
        }
        catch (ConfigurationException e)
        {
            cls = e.getClass().getName();
            msg = e.getMessage();
        }
        emit("STAGE4 reading nine d=9 exception=" + cls + " message=[" + msg + "] after=" + DatabaseDescriptor.getRepairSessionMaxTreeDepth());
    }
}
