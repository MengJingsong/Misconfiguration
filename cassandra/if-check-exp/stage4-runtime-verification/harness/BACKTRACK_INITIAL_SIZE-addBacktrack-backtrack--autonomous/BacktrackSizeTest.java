package org.apache.cassandra.db.tries;

// Stage-4 harness for BACKTRACK_INITIAL_SIZE-addBacktrack-backtrack--autonomous (unit tier, B2 as amended B2i).
// Not upstream code. Reads the private backtrack array of a trie cursor by reflection; builds combs with a linear-time generator.

import java.io.FileWriter;
import java.io.PrintWriter;
import java.lang.reflect.Field;
import java.util.ArrayList;
import java.util.List;

import org.junit.Test;

import org.apache.cassandra.io.compress.BufferType;
import org.apache.cassandra.utils.bytecomparable.ByteComparable;

public class BacktrackSizeTest
{
    static
    {
        // B2i.5c: the trie size threshold is read once per JVM from this property (MiB); set before any trie class loads.
        String t = System.getenv("STAGE4_THRESHOLD_MIB");
        if (t != null && !t.isEmpty())
            System.setProperty("cassandra.memtable.row_overhead_size", t);
    }

    static final Object CONTENT = "c";
    static final InMemoryTrie.UpsertTransformer<Object, Object> TAKE_NEW = (existing, update) -> update;

    /** Comb generator: spine of depth D along transition 0x00; every spine node at depth 0..D-1 also has the given sibling leaves. */
    static class CombTrie extends Trie<Object>
    {
        final int D;
        final int[] sibs;      // ascending, all > 0

        CombTrie(int D, int[] sibs) { this.D = D; this.sibs = sibs; }

        @Override
        protected Cursor<Object> cursor() { return new CombCursor(); }

        class CombCursor implements Cursor<Object>
        {
            int depth = 0, trans = -1, sib = -1;
            boolean onSpine = true;
            Object content = null;

            public int depth() { return depth; }
            public int incomingTransition() { return trans; }
            public Object content() { return content; }

            public int advance()
            {
                if (onSpine && depth < D)
                {
                    ++depth; trans = 0; content = depth == D ? CONTENT : null;
                    return depth;
                }
                return moveAfterCurrent();
            }

            public int skipChildren() { return moveAfterCurrent(); }

            private int moveAfterCurrent()
            {
                int lvl = depth - 1;
                int next = onSpine ? 0 : sib + 1;
                while (true)
                {
                    if (lvl < 0) { depth = -1; return -1; }
                    if (next < sibs.length)
                    {
                        depth = lvl + 1; trans = sibs[next]; content = CONTENT; sib = next; onSpine = false;
                        return depth;
                    }
                    --lvl; next = 0;
                }
            }
        }
    }

    static final Field F_BACKTRACK, F_DEPTH;
    static
    {
        try
        {
            Class<?> bs = InMemoryReadTrie.MemtableCursor.class.getSuperclass();
            F_BACKTRACK = bs.getDeclaredField("backtrack"); F_BACKTRACK.setAccessible(true);
            F_DEPTH = bs.getDeclaredField("backtrackDepth"); F_DEPTH.setAccessible(true);
        }
        catch (Exception e) { throw new RuntimeException(e); }
    }

    static int len(Object cursor) throws Exception { return ((int[]) F_BACKTRACK.get(cursor)).length; }
    static int bdepth(Object cursor) throws Exception { return F_DEPTH.getInt(cursor); }

    static PrintWriter out;
    static void result(String line)
    {
        System.out.println("RESULT," + line);
        if (out != null) { out.println(line); out.flush(); }
    }

    static ByteComparable key(int D, int lastByte)  // 0x00^D optionally followed by lastByte (-1 = none)
    {
        byte[] b = new byte[lastByte < 0 ? D : D + 1];
        if (lastByte >= 0) b[D] = (byte) lastByte;
        return ByteComparable.fixedLength(b);
    }

    static final int[] SPARSE = {1};
    static final int[] SPLIT = {1, 2, 3, 8, 0x40, 0x80};

    static InMemoryTrie<Object> build(BufferType bt, int D, int[] sibs) throws Exception
    {
        InMemoryTrie<Object> t = new InMemoryTrie<>(bt);
        t.apply(new CombTrie(D, sibs), TAKE_NEW);
        return t;
    }

    static InMemoryTrie<Object> buildChain(BufferType bt, int D) throws Exception
    {
        InMemoryTrie<Object> t = new InMemoryTrie<>(bt);
        t.putSingleton(key(D, -1), CONTENT, TAKE_NEW);
        return t;
    }

    /** Walks the whole trie with a fresh cursor; returns {initialL, maxBacktrackDepth, finalL, contentNodes, finalBacktrackDepth, cursorObjectForReuse}. */
    static Object[] walk(InMemoryTrie<Object> t) throws Exception
    {
        InMemoryReadTrie<Object>.MemtableCursor c = t.cursor();
        int l0 = len(c), maxE = bdepth(c), content = c.content() != null ? 1 : 0;
        long steps = 0;
        while (c.advance() >= 0)
        {
            ++steps;
            int e = bdepth(c);
            if (e > maxE) maxE = e;
            if (c.content() != null) ++content;
        }
        return new Object[]{ l0, maxE, len(c), content, bdepth(c), c, steps };
    }

    static void arm(String name, BufferType bt, String shape, int D, long F, long expectKeys, InMemoryTrie<Object> t, long buildMs) throws Exception
    {
        long on0 = t.sizeOnHeap(), off0 = t.sizeOffHeap();
        long t0 = System.nanoTime();
        Object[] w = walk(t);
        long ms = (System.nanoTime() - t0) / 1000000;
        long on1 = t.sizeOnHeap(), off1 = t.sizeOffHeap();
        long bytes = 16L + 4L * (int) w[2];
        result(String.join(",", name, bt.toString(), shape, "" + D, "" + F, "" + expectKeys, "" + w[3], "" + w[0], "" + w[1], "" + w[2], "" + bytes,
                           "" + on0, "" + on1, "" + off0, "" + off1, "" + buildMs, "" + ms, "" + w[6]));
    }

    @Test
    public void backtrackSizes() throws Exception
    {
        String dir = System.getenv("STAGE4_OUT");
        if (dir != null) out = new PrintWriter(new FileWriter(dir + "/results.csv", true));
        result("arm,buffer,shape,D,F,expectedContent,contentNodes,L0,E,L,arrayBytes,sizeOnBefore,sizeOnAfter,sizeOffBefore,sizeOffAfter,buildMs,walkMs,steps");
        int[] depths = {8, 64, 1024, 65535};
        for (BufferType bt : new BufferType[]{ BufferType.ON_HEAP, BufferType.OFF_HEAP })
        {
            for (int D : depths)
            {
                long b0 = System.nanoTime();
                InMemoryTrie<Object> t = buildChain(bt, D);
                arm("chain_" + D, bt, "chain", D, 0, 1, t, (System.nanoTime() - b0) / 1000000);
                b0 = System.nanoTime();
                t = build(bt, D, SPARSE);
                arm("sparse_" + D, bt, "sparse", D, 0, D + 1, t, (System.nanoTime() - b0) / 1000000);
                b0 = System.nanoTime();
                t = build(bt, D, SPLIT);
                arm("split_" + D, bt, "split", D, 0, 6L * D + 1, t, (System.nanoTime() - b0) / 1000000);
            }
            for (long F : new long[]{ 0, 100000, 1000000 })
            {
                long b0 = System.nanoTime();
                InMemoryTrie<Object> t = build(bt, 64, SPARSE);
                for (long i = 0; i < F; i++)
                {
                    long x = (i * 2654435761L) & 0xFFFFFFFFL;   // bijective on 32 bits: distinct keys
                    byte[] k = { 2, (byte) (x >>> 24), (byte) (x >>> 16), (byte) (x >>> 8), (byte) x };
                    t.putSingleton(ByteComparable.fixedLength(k), CONTENT, TAKE_NEW);
                }
                arm("fill_" + F, bt, "sparse+filler", 64, F, 65 + F, t, (System.nanoTime() - b0) / 1000000);
            }
            {   // equivalence: 1025 putSingleton calls
                long b0 = System.nanoTime();
                InMemoryTrie<Object> t = new InMemoryTrie<>(bt);
                for (int d = 0; d < 1024; d++)
                    t.putSingleton(key(d, 1), CONTENT, TAKE_NEW);
                t.putSingleton(key(1024, -1), CONTENT, TAKE_NEW);
                arm("put1024", bt, "sparse(put)", 1024, 0, 1025, t, (System.nanoTime() - b0) / 1000000);
            }
            {   // fresh vs reused cursor
                InMemoryTrie<Object> t = build(bt, 64, SPARSE);
                Object[] w = walk(t);
                Object c1 = w[5];
                InMemoryReadTrie<Object>.MemtableCursor c2 = t.cursor();
                result(String.join(",", "reuse", bt.toString(), "sparse", "64", "0", "65", "-", "" + len(c2), "-", "" + len(c1), "-", "-", "-", "-", "-", "-", "-", "-"));
            }
        }
        {   // positive control: trie size threshold (a cap that binds on allocated trie bytes), one JVM per T
            long thr = InMemoryTrie.ALLOCATED_SIZE_THRESHOLD;
            long T = thr >> 20;
            InMemoryTrie<Object> t = new InMemoryTrie<>(BufferType.OFF_HEAP);
            boolean f0 = t.reachedAllocatedSizeThreshold();
            long p1 = t.advanceAllocatedPos((int) ((T - 1) << 20));
            boolean f1 = t.reachedAllocatedSizeThreshold();
            long off1 = t.sizeOffHeap();
            long p2 = t.advanceAllocatedPos((int) (T << 20));
            boolean f2 = t.reachedAllocatedSizeThreshold();
            long off2 = t.sizeOffHeap();
            t.apply(new CombTrie(1024, SPARSE), TAKE_NEW);
            Object[] w = walk(t);
            result(String.join(",", "thr", "OFF_HEAP", "sparse", "1024", "0", "1025", "" + w[3], "" + w[0], "" + w[1], "" + w[2], "" + (16L + 4L * (int) w[2]),
                               "" + T + ";" + thr, "" + f0 + ";" + f1 + ";" + f2, "" + p1 + ";" + p2, "" + off1 + ";" + off2, "-", "-", "-"));
        }
        if (out != null) out.close();
    }

    /** Instrument check (B3i.5): one sparse D=64 comb, one cursor; run under the Byteman agent. */
    public static void main(String[] args) throws Exception
    {
        InMemoryTrie<Object> t = build(BufferType.ON_HEAP, 64, SPARSE);
        Object[] w = walk(t);
        System.out.println("MAIN_RESULT contentNodes=" + w[3] + " L0=" + w[0] + " E=" + w[1] + " L=" + w[2]);
        Thread.sleep(3500);   // let the helper's 2 s dump run
    }
}
