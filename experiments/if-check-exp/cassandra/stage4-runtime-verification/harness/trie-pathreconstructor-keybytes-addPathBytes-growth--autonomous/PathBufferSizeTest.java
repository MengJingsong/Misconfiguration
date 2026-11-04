package org.apache.cassandra.db.tries;

// Stage-4 harness for trie-pathreconstructor-keybytes-addPathBytes-growth--autonomous (unit tier, B2 as amended B2i).
// Not upstream code. Reads the protected TriePathReconstructor.keyBytes capacity of a TrieEntriesIterator subclass after a full walk.

import java.io.FileWriter;
import java.io.PrintWriter;
import java.lang.management.ManagementFactory;
import java.util.ArrayList;
import java.util.List;
import java.util.Random;

import org.junit.Assert;
import org.junit.Test;

import org.apache.cassandra.io.compress.BufferType;
import org.apache.cassandra.utils.bytecomparable.ByteComparable;

public class PathBufferSizeTest
{
    static final InMemoryTrie.UpsertTransformer<Integer, Integer> TAKE_NEW = (existing, update) -> update;
    static final List<String> OUT = new ArrayList<>();

    /** Subclass in the tries package so that the protected keyBytes is reachable. */
    static class Probe extends TrieEntriesIterator<Integer, Integer>
    {
        Probe(Trie<Integer> trie) { super(trie); }
        @Override protected Integer mapContent(Integer content, byte[] bytes, int byteLength) { return content; }
        int capacity() { return keyBytes.length; }
    }

    static long splitmix(long x)   // a bijection on 64 bits: distinct inputs give distinct outputs
    {
        x += 0x9E3779B97F4A7C15L;
        x = (x ^ (x >>> 30)) * 0xBF58476D1CE4E5B9L;
        x = (x ^ (x >>> 27)) * 0x94D049BB133111EBL;
        return x ^ (x >>> 31);
    }

    static byte[] key(int i, int L, Random rnd)
    {
        byte[] k = new byte[L];
        rnd.nextBytes(k);
        long h = splitmix(i);
        for (int b = 0; b < 8 && b < L; b++)
            k[b] = (byte) (h >>> (56 - 8 * b));
        return k;
    }

    static long allocated()
    {
        return ((com.sun.management.ThreadMXBean) ManagementFactory.getThreadMXBean()).getThreadAllocatedBytes(Thread.currentThread().getId());
    }

    /** One cell: build a trie of N keys of length L, walk it fully, report. rep identifies the repeat. */
    static void cell(String group, BufferType bt, int L, int N, int rep) throws Exception
    {
        InMemoryTrie<Integer> trie = new InMemoryTrie<>(bt);
        Random rnd = new Random(1234 + L * 31L + N);
        for (int i = 0; i < N; i++)
            trie.putSingleton(ByteComparable.fixedLength(key(i, L, rnd)), i, TAKE_NEW, L <= TrieMemtableLike.MAX_RECURSIVE);
        Probe p = new Probe(trie);
        int before = p.capacity();
        long a0 = allocated();
        int entries = 0;
        while (p.hasNext()) { p.next(); entries++; }
        long a1 = allocated();
        int cap = p.capacity();
        System.out.println("PROBE," + System.identityHashCode(p) + "," + cap);
        Assert.assertEquals("entries walked", N, entries);
        String line = String.join(",", group, bt.name(), "L=" + L, "N=" + N, "rep=" + rep, "entries=" + entries,
                                  "capBefore=" + before, "capacity=" + cap, "sizeOnHeap=" + trie.sizeOnHeap(),
                                  "sizeOffHeap=" + trie.sizeOffHeap(), "iterAllocBytes=" + (a1 - a0));
        System.out.println("RESULT," + line);
        OUT.add(line);
        trie.discardBuffers();
    }

    /** The TrieMemtable constant (128), duplicated here only to avoid loading TrieMemtable's static init (DatabaseDescriptor). */
    static final class TrieMemtableLike { static final int MAX_RECURSIVE = 128; }

    @Test
    public void pathBufferSizes() throws Exception
    {
        int[] ls = { 16, 1000, 20000, 65535, 131070 };
        for (BufferType bt : new BufferType[]{ BufferType.ON_HEAP, BufferType.OFF_HEAP })
        {
            for (int rep = 1; rep <= 3; rep++)
            {
                cell("empty", bt, 16, 0, rep);                 // empty trie: capacity 32
                for (int L : ls)
                    cell("lsweep", bt, L, 1000, rep);
                for (int L : new int[]{ 16, 1000 })
                    for (int N : new int[]{ 1, 1000, 100000 })
                        cell("nsweep", bt, L, N, rep);
            }
        }
        String dir = System.getenv("STAGE4_OUT");
        if (dir != null)
            try (PrintWriter pw = new PrintWriter(new FileWriter(dir + "/results.csv")))
            {
                for (String l : OUT) pw.println(l);
            }
    }

    /** Instrument check (not a reading): small known-answer cells under the Byteman agent; PROBE lines give identityHashCode and capacity. */
    public static void main(String[] args) throws Exception
    {
        cell("check", BufferType.ON_HEAP, 16, 1000, 1);
        cell("check", BufferType.ON_HEAP, 1000, 100, 1);
        cell("check", BufferType.ON_HEAP, 65535, 50, 1);
        cell("check", BufferType.ON_HEAP, 1000, 1, 1);
    }
}
