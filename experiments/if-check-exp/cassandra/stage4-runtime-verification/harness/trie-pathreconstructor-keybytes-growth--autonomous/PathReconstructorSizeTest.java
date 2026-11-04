/*
 * Stage-4 unit tier (B2) of trie-pathreconstructor-keybytes-growth--autonomous. Not part of Cassandra.
 * Copied into test/unit/org/apache/cassandra/db/tries/ of the run tree by unit-run.sh (package access to the
 * protected keyBytes of TriePathReconstructor through a TrieEntriesIterator subclass). Asserts nothing: prints
 * "TP33 ..." lines to build/test/tp33-unit.txt, which unit-analyze.py compares with B2f.
 */
package org.apache.cassandra.db.tries;

import java.io.PrintWriter;
import java.lang.management.ManagementFactory;
import java.nio.ByteBuffer;
import java.util.ArrayList;
import java.util.List;
import java.util.Random;

import org.junit.BeforeClass;
import org.junit.Test;

import org.apache.cassandra.config.DatabaseDescriptor;
import org.apache.cassandra.db.DecoratedKey;
import org.apache.cassandra.dht.Murmur3Partitioner;
import org.apache.cassandra.io.compress.BufferType;
import org.apache.cassandra.utils.bytecomparable.ByteComparable;
import org.apache.cassandra.utils.bytecomparable.ByteSource;

public class PathReconstructorSizeTest
{
    static final int[] LENGTHS = {8, 31, 32, 33, 1000, 32768, 65535};
    static PrintWriter out;

    /** TrieEntriesIterator exposing the protected scratch array; records the longest path handed to mapContent. */
    static class It extends TrieEntriesIterator<Object, Object>
    {
        int maxPath = 0;
        int entries = 0;
        It(Trie<Object> t) { super(t); }
        @Override
        protected Object mapContent(Object content, byte[] bytes, int byteLength)
        {
            maxPath = Math.max(maxPath, byteLength);
            entries++;
            return content;
        }
        int cap() { return keyBytes.length; }
    }

    @BeforeClass
    public static void init() throws Exception
    {
        DatabaseDescriptor.daemonInitialization();
        new java.io.File("build/test").mkdirs();
        out = new PrintWriter(new java.io.FileWriter("build/test/tp33-unit.txt"));
    }

    static void p(String s) { out.println("TP33 " + s); out.flush(); }

    static byte[] key(Random r, int len, String kind)
    {
        byte[] b = new byte[len];
        if (kind.equals("zero")) return b;                      // all 0x00
        r.nextBytes(b);
        for (int i = 0; i < len; i++) if (b[i] == 0) b[i] = 1; // no 0x00: escaped length = length
        return b;
    }

    static int zeros(byte[] b) { int z = 0; for (byte x : b) if (x == 0) z++; return z; }

    static int pathLength(ByteComparable bc)
    {
        ByteSource s = bc.asComparableBytes(ByteComparable.Version.OSS50);
        int n = 0;
        while (s.next() != ByteSource.END_OF_STREAM) n++;
        return n;
    }

    static void put(InMemoryTrie<Object> t, ByteComparable k, int keyLen) throws Exception
    {
        t.putSingleton(k, "v", (old, nw) -> nw, keyLen < 128);   // MAX_RECURSIVE_KEY_LENGTH = 128 (TrieMemtable.java:98)
    }

    /** One grid point: up to 3 keys of the kind, 3 repetitions after gc. */
    static void point(String kind, BufferType bt, int L, long seed) throws Exception
    {
        for (int rep = 1; rep <= 3; rep++)
        {
            Random r = new Random(seed);
            InMemoryTrie<Object> t = new InMemoryTrie<>(bt);
            int z = 0, P = 0;
            for (int i = 0; i < 3; i++)
            {
                byte[] kb = key(r, L, kind.equals("zero") ? "zero" : "rand");
                z = Math.max(z, zeros(kb));
                if (kind.equals("raw"))
                {
                    put(t, ByteComparable.fixedLength(kb), L);
                    P = Math.max(P, L);
                }
                else
                {
                    DecoratedKey dk = Murmur3Partitioner.instance.decorateKey(ByteBuffer.wrap(kb));
                    put(t, dk, dk.getKeyLength());
                    P = Math.max(P, pathLength(dk));
                }
                if (kind.equals("zero")) break;               // 3 identical zero keys would be one key
            }
            System.gc();
            long onB = t.sizeOnHeap(), offB = t.sizeOffHeap();
            It it = new It(t);
            int cap0 = it.cap();
            while (it.hasNext()) it.next();
            long onA = t.sizeOnHeap(), offA = t.sizeOffHeap();
            p(String.format("kind=%s bt=%s L=%d z=%d P=%d maxPath=%d cap0=%d cap=%d entries=%d onB=%d offB=%d onA=%d offA=%d rep=%d",
                            kind, bt, L, z, P, it.maxPath, cap0, it.cap(), it.entries, onB, offB, onA, offA, rep));
        }
    }

    @Test
    public void grid() throws Exception
    {
        long seed = 33;
        for (BufferType bt : new BufferType[]{BufferType.ON_HEAP, BufferType.OFF_HEAP})
            for (String kind : new String[]{"raw", "real", "zero"})
                for (int L : LENGTHS)
                    point(kind, bt, L, seed + L);

        // M control: L = 100 raw random keys, M = 10k and 100k
        for (BufferType bt : new BufferType[]{BufferType.ON_HEAP, BufferType.OFF_HEAP})
            for (int M : new int[]{10_000, 100_000})
            {
                Random r = new Random(7);
                InMemoryTrie<Object> t = new InMemoryTrie<>(bt);
                for (int i = 0; i < M; i++) put(t, ByteComparable.fixedLength(key(r, 100, "rand")), 100);
                System.gc();
                long onB = t.sizeOnHeap(), offB = t.sizeOffHeap();
                It it = new It(t);
                while (it.hasNext()) it.next();
                p(String.format("kind=mctl bt=%s L=100 M=%d P=%d maxPath=%d cap=%d entries=%d onB=%d offB=%d onA=%d offA=%d",
                                bt, M, 100, it.maxPath, it.cap(), it.entries, onB, offB, t.sizeOnHeap(), t.sizeOffHeap()));
            }

        // N concurrent iterators over one real-key trie, L = 65535
        com.sun.management.ThreadMXBean mx = (com.sun.management.ThreadMXBean) ManagementFactory.getThreadMXBean();
        Random r = new Random(65535);
        final InMemoryTrie<Object> t = new InMemoryTrie<>(BufferType.ON_HEAP);
        int P = 0;
        for (int i = 0; i < 3; i++)
        {
            DecoratedKey dk = Murmur3Partitioner.instance.decorateKey(ByteBuffer.wrap(key(r, 65535, "rand")));
            put(t, dk, dk.getKeyLength());
            P = Math.max(P, pathLength(dk));
        }
        for (int N : new int[]{1, 8, 64})
            for (int rep = 1; rep <= 3; rep++)
            {
                final long[] alloc = new long[N];
                final int[] caps = new int[N];
                List<Thread> ths = new ArrayList<>();
                long onB = t.sizeOnHeap();
                for (int i = 0; i < N; i++)
                {
                    final int ix = i;
                    ths.add(new Thread(() -> {
                        long a0 = mx.getThreadAllocatedBytes(Thread.currentThread().getId());
                        It it = new It(t);
                        while (it.hasNext()) it.next();
                        alloc[ix] = mx.getThreadAllocatedBytes(Thread.currentThread().getId()) - a0;
                        caps[ix] = it.cap();
                    }));
                }
                for (Thread th : ths) th.start();
                for (Thread th : ths) th.join();
                long sum = 0, mn = Long.MAX_VALUE;
                int capMax = 0, capMin = Integer.MAX_VALUE;
                for (int i = 0; i < N; i++)
                {
                    sum += alloc[i]; mn = Math.min(mn, alloc[i]);
                    capMax = Math.max(capMax, caps[i]); capMin = Math.min(capMin, caps[i]);
                }
                p(String.format("kind=conc N=%d L=65535 P=%d capMin=%d capMax=%d allocSum=%d allocMinPerThread=%d onB=%d onA=%d rep=%d",
                                N, P, capMin, capMax, sum, mn, onB, t.sizeOnHeap(), rep));
            }
        out.close();
    }
}
