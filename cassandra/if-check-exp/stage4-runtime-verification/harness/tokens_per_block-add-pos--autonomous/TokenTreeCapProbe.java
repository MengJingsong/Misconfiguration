package org.apache.cassandra.index.sasi.disk;

import java.lang.management.ManagementFactory;
import java.nio.ByteBuffer;
import java.util.Arrays;
import java.util.Iterator;

import org.apache.cassandra.config.DatabaseDescriptor;
import org.apache.cassandra.db.DecoratedKey;
import org.apache.cassandra.db.marshal.UTF8Type;
import org.apache.cassandra.dht.Murmur3Partitioner;
import org.apache.cassandra.io.util.DataOutputBuffer;

/**
 * Stage-4 unit probe, tokens_per_block-add-pos--autonomous (B2, amended 2026-10-28). Package org.apache.cassandra.index.sasi.disk (protected members).
 * usage: TokenTreeCapProbe tree <N> <label>   DynamicTokenTreeBuilder with N ascending distinct tokens: TOKENS_PER_BLOCK (read reflectively from the loaded
 *                                             interface: the constant is inlined into this probe otherwise), tokenCount, numBlocks, serializedSize(), bytes of write(),
 *                                             max tokens per interior node and per leaf (walk of root.levelIterator()), thread-allocated bytes and median retained heap of 5 GCs.
 *        TokenTreeCapProbe ctl <M> <label>    OnDiskIndexBuilder (PREFIX) with M distinct 16-character terms: estimatedMemoryUse() and retained heap.
 */
public class TokenTreeCapProbe
{
    static final com.sun.management.ThreadMXBean TMX = (com.sun.management.ThreadMXBean) ManagementFactory.getThreadMXBean();
    static long tid() { return Thread.currentThread().getId(); }

    static long heap()
    {
        long[] s = new long[5];
        for (int i = 0; i < s.length; i++)
        {
            System.gc(); System.gc();
            Runtime r = Runtime.getRuntime();
            s[i] = r.totalMemory() - r.freeMemory();
        }
        Arrays.sort(s);
        return s[2];
    }

    static int constant() throws Exception
    {
        java.lang.reflect.Field f = TokenTreeBuilder.class.getField("TOKENS_PER_BLOCK");
        return f.getInt(null);
    }

    static class Probe extends DynamicTokenTreeBuilder
    {
        int maxInterior = 0, maxLeaf = 0, interiorNodes = 0, leaves = 0, levels = 0;
        void walk()
        {
            Iterator<Node> level = root.levelIterator();
            while (level != null)
            {
                Node first = null;
                levels++;
                while (level.hasNext())
                {
                    Node n = level.next();
                    if (first == null && !n.isLeaf()) first = ((InteriorNode) n).children.get(0);
                    if (n.isLeaf()) { leaves++; maxLeaf = Math.max(maxLeaf, n.tokenCount()); }
                    else { interiorNodes++; maxInterior = Math.max(maxInterior, ((InteriorNode) n).tokens.size()); }
                }
                level = first == null ? null : first.levelIterator();
            }
        }
        int blocks() { return numBlocks; }
    }

    public static void main(String[] a) throws Exception
    {
        DatabaseDescriptor.daemonInitialization();
        String mode = a[0];
        long n = Long.parseLong(a[1]);
        String id = "mode=" + mode + " n=" + n + " label=" + (a.length > 2 ? a[2] : "") + " TOKENS_PER_BLOCK=" + constant();
        // warm-up
        { Probe w = new Probe(); for (long i = 0; i < 1000; i++) w.add(i * 7, i); w.finish(); w.walk(); DataOutputBuffer o = new DataOutputBuffer(); w.write(o); }
        if (mode.equals("tree"))
        {
            long h0 = heap();
            long a0 = TMX.getThreadAllocatedBytes(tid());
            Probe p = new Probe();
            for (long i = 0; i < n; i++) p.add(i * 1000003L, i);
            long a1 = TMX.getThreadAllocatedBytes(tid());
            p.finish();
            long a2 = TMX.getThreadAllocatedBytes(tid());
            long hAfter = heap();
            p.walk();
            DataOutputBuffer out = new DataOutputBuffer();
            p.write(out);
            System.out.println("STAGE4 tree " + id + " tokenCount=" + p.getTokenCount() + " numBlocks=" + p.blocks() + " serializedSize=" + p.serializedSize() + " writtenBytes=" + out.getLength()
                               + " maxInteriorTokens=" + p.maxInterior + " maxLeafTokens=" + p.maxLeaf + " interiorNodes=" + p.interiorNodes + " leaves=" + p.leaves + " levels=" + p.levels
                               + " addAlloc=" + (a1 - a0) + " finishAlloc=" + (a2 - a1) + " retainedHeap=" + (hAfter - h0));
        }
        else
        {
            long h0 = heap();
            OnDiskIndexBuilder b = new OnDiskIndexBuilder(UTF8Type.instance, UTF8Type.instance, OnDiskIndexBuilder.Mode.PREFIX);
            for (long i = 0; i < n; i++)
            {
                String t = String.format("%016x", i * 2654435761L);
                DecoratedKey k = Murmur3Partitioner.instance.decorateKey(ByteBuffer.allocate(8).putLong(0, i));
                b.add(UTF8Type.instance.decompose(t), k, i);
            }
            long h1 = heap();
            System.out.println("STAGE4 control " + id + " estimatedMemoryUse=" + b.estimatedMemoryUse() + " expectedPerTerm=" + (64 + 48 + 16 + 60 + 40 + 8) + " retainedHeap=" + (h1 - h0));
        }
        System.exit(0);
    }
}
