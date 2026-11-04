package org.apache.cassandra.db.transform;

import java.io.PrintWriter;
import java.lang.management.ManagementFactory;
import java.nio.ByteBuffer;
import java.util.*;

import org.junit.Test;

import org.apache.cassandra.db.*;
import org.apache.cassandra.db.marshal.BytesType;
import org.apache.cassandra.db.marshal.Int32Type;
import org.apache.cassandra.db.partitions.AbstractUnfilteredPartitionIterator;
import org.apache.cassandra.db.partitions.UnfilteredPartitionIterator;
import org.apache.cassandra.db.rows.*;
import org.apache.cassandra.dht.Murmur3Partitioner;
import org.apache.cassandra.schema.ColumnMetadata;
import org.apache.cassandra.schema.TableMetadata;

/**
 * Stage-4 unit tier for transform-stack-capacity-splice-newCount--autonomous (case file B2/B2i). Package-private access to Stack fields.
 * Writes RAW observations to $STAGE4_OUT/raw.csv (the analysis script judges them against the frozen predictions; this class asserts nothing).
 */
public class StackSpliceCapacityTest
{
    static final Transformation<UnfilteredRowIterator> NOOP = new Transformation<UnfilteredRowIterator>() {};
    static TableMetadata metadata = TableMetadata.builder("ks", "t")
                                                 .addPartitionKeyColumn("pk", Int32Type.instance)
                                                 .addRegularColumn("v", BytesType.instance)
                                                 .partitioner(Murmur3Partitioner.instance)
                                                 .build();
    static PrintWriter raw;
    static long totRefills, totStackChanges, totMcChanges;
    static volatile Object sink; // keeps retained objects reachable

    static UnfilteredPartitionIterator emptyIter()
    {
        return new AbstractUnfilteredPartitionIterator()
        {
            public TableMetadata metadata() { return metadata; }
            public boolean hasNext() { return false; }
            public UnfilteredRowIterator next() { throw new NoSuchElementException(); }
        };
    }

    static UnfilteredPartitionIterator withNoops(UnfilteredPartitionIterator it, int n)
    {
        for (int i = 0; i < n; i++)
            it = Transformation.apply(it, NOOP);
        return it;
    }

    static UnfilteredPartitions asParts(UnfilteredPartitionIterator it) { return (UnfilteredPartitions) it; }

    static void out(String line) { raw.println(line); raw.flush(); }

    /** build-up arm: K adds, no refill. */
    static void buildUp(int k)
    {
        UnfilteredPartitions it = asParts(withNoops(Transformation.mutable(emptyIter()), k));
        out(String.join(",", "buildup", "" + k, "0", "0", "0", "0", "" + it.stack.length, "" + it.length));
    }

    /** refill arm: K noops, extend, M noops; replacement contents carries P noops and Q extends; R refills. */
    static void refill(int k, int m, int p, int q, int r)
    {
        final UnfilteredPartitions[] outer = new UnfilteredPartitions[1];
        final List<Object[]> snaps = new ArrayList<>(); // {stack array, length, moreContents array}
        final int[] calls = { 0 };
        MorePartitions<UnfilteredPartitionIterator> provider = () ->
        {
            UnfilteredPartitions o = outer[0];
            snaps.add(new Object[]{ o.stack, o.length, o.moreContents });
            if (calls[0]++ >= r)
                return null;
            UnfilteredPartitionIterator c = Transformation.mutable(emptyIter());
            for (int j = 0; j < q; j++)
                c = MorePartitions.extend(c, () -> null);
            return withNoops(c, p);
        };
        UnfilteredPartitionIterator it = withNoops(Transformation.mutable(emptyIter()), k);
        it = MorePartitions.extend(it, provider);
        it = withNoops(it, m);
        outer[0] = asParts(it);
        int capBefore = outer[0].stack.length;
        int lenBefore = outer[0].length;
        int mcBefore = outer[0].moreContents.length;
        while (it.hasNext())
            it.next().close();
        UnfilteredPartitions o = outer[0];
        // snaps: initial state at first provider call, then the state after each refill (taken at the start of the next call)
        int refills = snaps.size() - 1;
        int stackChanges = 0, mcChanges = 0;
        for (int i = 1; i < snaps.size(); i++)
        {
            if (snaps.get(i)[0] != snaps.get(i - 1)[0]) stackChanges++;
            if (snaps.get(i)[2] != snaps.get(i - 1)[2]) mcChanges++;
        }
        // the final state after drain must equal the last snapshot
        boolean finalSame = o.stack == snaps.get(snaps.size() - 1)[0] && o.moreContents == snaps.get(snaps.size() - 1)[2];
        totRefills += refills; totStackChanges += stackChanges; totMcChanges += mcChanges;
        out(String.join(",", "refill", "" + k, "" + m, "" + p, "" + q, "" + r,
                        "" + capBefore, "" + lenBefore, "" + mcBefore,
                        "" + o.stack.length, "" + o.length, "" + o.moreContents.length,
                        "" + refills, "" + stackChanges, "" + mcChanges, "" + finalSame));
    }

    static long usedHeap()
    {
        for (int i = 0; i < 3; i++) { System.gc(); try { Thread.sleep(50); } catch (InterruptedException e) { } }
        return ManagementFactory.getMemoryMXBean().getHeapMemoryUsage().getUsed();
    }

    /** memory arm: K shared no-op entries; retained heap vs an Object[] of the same length. */
    static void heapStack(int k, int rep)
    {
        long b0 = usedHeap();
        UnfilteredPartitions it = asParts(withNoops(Transformation.mutable(emptyIter()), k));
        sink = it;
        long b1 = usedHeap();
        Object[] ref = new Object[it.stack.length];
        sink = new Object[]{ it, ref };
        long b2 = usedHeap();
        out(String.join(",", "heapstack", "" + k, "" + rep, "" + it.stack.length, "" + (b1 - b0), "" + (b2 - b1)));
        sink = null;
    }

    static UnfilteredPartitionIterator rowSource(final int n)
    {
        final ColumnMetadata col = metadata.getColumn(ByteBuffer.wrap("v".getBytes()));
        return new AbstractUnfilteredPartitionIterator()
        {
            int i = 0;
            public TableMetadata metadata() { return metadata; }
            public boolean hasNext() { return i < n; }
            public UnfilteredRowIterator next()
            {
                final DecoratedKey key = Murmur3Partitioner.instance.decorateKey(Int32Type.instance.decompose(i++));
                final Row row = BTreeRow.singleCellRow(Clustering.EMPTY, BufferCell.live(col, 1L, ByteBuffer.wrap(new byte[1024])));
                final boolean[] done = { false };
                return new AbstractUnfilteredRowIterator(metadata, key, DeletionTime.LIVE, metadata.regularAndStaticColumns(),
                                                         Rows.EMPTY_STATIC_ROW, false, EncodingStats.NO_STATS)
                {
                    protected Unfiltered computeNext()
                    {
                        if (done[0]) return endOfData();
                        done[0] = true;
                        return row;
                    }
                };
            }
        };
    }

    /** positive control: same pipeline (K=5, M=0, P=6, R=1) over n partitions of one 1 KiB cell; the rows are retained. n < 0: retain until OutOfMemoryError. */
    static void control(String arm, int n)
    {
        final UnfilteredPartitions[] outer = new UnfilteredPartitions[1];
        final int[] calls = { 0 };
        MorePartitions<UnfilteredPartitionIterator> provider = () -> calls[0]++ >= 1 ? null : withNoops(Transformation.mutable(emptyIter()), 6);
        UnfilteredPartitionIterator it = withNoops(Transformation.mutable(rowSource(n < 0 ? Integer.MAX_VALUE : n)), 5);
        it = MorePartitions.extend(it, provider);
        outer[0] = asParts(it);
        long b0 = usedHeap();
        ArrayList<Row> held = new ArrayList<>();
        boolean oom = false;
        long usedAtOom = 0; int heldAtOom = 0;
        try
        {
            while (it.hasNext())
            {
                try (UnfilteredRowIterator p = it.next())
                {
                    while (p.hasNext())
                        held.add((Row) p.next());
                }
            }
        }
        catch (OutOfMemoryError e)
        {
            oom = true;
            Runtime rt0 = Runtime.getRuntime();
            usedAtOom = rt0.totalMemory() - rt0.freeMemory(); // no allocation here
            heldAtOom = held.size();
            held.clear(); held.trimToSize();
        }
        int stackLen = outer[0].stack.length;
        int heldN = oom ? heldAtOom : held.size();
        long maxHeap = Runtime.getRuntime().maxMemory();
        long b1;
        if (oom)
        {
            held = null; it = null; outer[0] = null;
            b1 = usedAtOom; // recorded as "used at OOM"
        }
        else
        {
            sink = held;
            b1 = usedHeap();
        }
        out(String.join(",", "control", arm, "" + n, "" + heldN, "" + oom, "" + (b1 - b0), "" + stackLen, "" + maxHeap));
        sink = null;
    }

    @Test
    public void run() throws Exception
    {
        String dir = System.getProperty("stage4.out", System.getenv("STAGE4_OUT"));
        raw = new PrintWriter(dir + "/raw.csv");
        out("# header: buildup,K,0,0,0,0,stack.length,length | refill,K,M,P,Q,R,capBefore,lenBefore,mcBefore,stackLenAfter,lenAfter,mcLenAfter,refills,stackChanges,mcChanges,finalSame | heapstack,K,rep,stack.length,deltaIterator,deltaObjectArray | control,arm,n,heldRows,oom,heapDelta,stackLen,maxHeap");
        String only = System.getProperty("stage4.arms", "");
        boolean all = only.isEmpty();
        if (all || only.contains("buildup"))
            for (int k : new int[]{ 0, 1, 3, 5, 6, 10, 11, 20, 21, 40, 41, 1000, 100000 }) buildUp(k);
        int[][] grid = { {5,0,6,0}, {3,0,1,0}, {5,0,5,0}, {0,5,6,0}, {0,5,0,0}, {40,0,41,0}, {1000,0,100000,0}, {5,0,6,1}, {0,0,0,1} };
        if (all || only.contains("refill"))
            for (int[] g : grid)
                for (int r : new int[]{ 1, 10, 1000 })
                    refill(g[0], g[1], g[2], g[3], r);
        if (all || only.contains("heap"))
            for (int rep = 0; rep < 3; rep++) heapStack(1_000_000, rep);
        if (all || only.contains("control"))
        {
            for (int n : new int[]{ 20000, 80000, 160000 }) control("ctl_" + n, n);
            control("ctl_cap", -1);
        }
        out("# TOTAL refills=" + totRefills + " stackChanges=" + totStackChanges + " mcChanges=" + totMcChanges + " splice_calls_expected=" + (2 * totRefills) + " grow_expected=" + (totStackChanges + totMcChanges));
        raw.close();
    }
}
