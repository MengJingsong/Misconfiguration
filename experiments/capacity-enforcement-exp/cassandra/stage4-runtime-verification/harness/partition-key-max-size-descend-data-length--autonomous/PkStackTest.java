package org.apache.cassandra.db.tries;

import java.nio.ByteBuffer;
import java.util.Random;

import org.apache.cassandra.db.DecoratedKey;
import org.apache.cassandra.dht.Murmur3Partitioner;
import org.apache.cassandra.io.compress.BufferType;
import org.apache.cassandra.utils.ObjectSizes;
import org.apache.cassandra.utils.bytecomparable.ByteComparable;

/**
 * Stage-4 harness for partition-key-max-size-descend-data-length--autonomous (unit tier, B2).
 * Lives in the trie package to read the package-private ApplyState.data.
 *
 * Modes (args[0]):
 *   lengths <csvL> <repeats>   one row per (bufferType, L, path, repeat): data.length, sizeOnHeap/OffHeap, measureDeep before/after
 *   bulk <nKeys> <keyLen>      N distinct short keys after a long key (L=65535) and on a fresh trie
 *   depth <csvK>               byte-comparable depth of a DecoratedKey with a K-byte random blob key
 */
public class PkStackTest
{
    static final ByteComparable.Version V = ByteComparable.Version.OSS50;

    static byte[] randomKey(Random r, int len)
    {
        byte[] b = new byte[len];
        r.nextBytes(b);
        for (int i = 0; i < len; i++)
            if (b[i] == 0 || b[i] == (byte) 0xFE) b[i] = 0x41; // avoid escaped bytes
        return b;
    }

    static InMemoryTrie.UpsertTransformer<Object, Object> T = (e, u) -> u;

    public static void main(String[] a) throws Exception
    {
        switch (a[0])
        {
            case "lengths": lengths(a[1], Integer.parseInt(a[2])); break;
            case "bulk": bulk(Integer.parseInt(a[1]), Integer.parseInt(a[2])); break;
            case "depth": depth(a[1]); break;
            default: throw new IllegalArgumentException(a[0]);
        }
    }

    static void lengths(String csv, int repeats) throws Exception
    {
        System.out.println("bufferType\tL\tpath\trep\tdataLen0\tdataLen1\tonHeap0\tonHeap1\toffHeap0\toffHeap1\tdeep0\tdeep1\tstatus");
        for (BufferType bt : new BufferType[]{ BufferType.ON_HEAP, BufferType.OFF_HEAP })
            for (String s : csv.split(","))
            {
                int L = Integer.parseInt(s.trim());
                for (int rep = 0; rep < repeats; rep++)
                    for (String path : new String[]{ "apply", "recursive" })
                    {
                        byte[] k = randomKey(new Random(1000 + L + rep), L);
                        InMemoryTrie<Object> t = new InMemoryTrie<>(bt);
                        long d0 = ObjectSizes.measureDeep(t), on0 = t.sizeOnHeap(), off0 = t.sizeOffHeap();
                        int len0 = t.applyState.data.length;
                        String status = "ok";
                        try
                        {
                            if (path.equals("apply"))
                                t.putSingleton(ByteComparable.fixedLength(k), new Object(), T);
                            else
                            {
                                final InMemoryTrie<Object> tt = t;
                                final Throwable[] err = new Throwable[1];
                                Thread th = new Thread(null, () -> {
                                    try { tt.putRecursive(ByteComparable.fixedLength(k), new Object(), T); }
                                    catch (Throwable e) { err[0] = e; }
                                }, "rec", 1L << 30);
                                th.start(); th.join();
                                if (err[0] != null) status = err[0].getClass().getSimpleName();
                            }
                        }
                        catch (Throwable e) { status = e.getClass().getSimpleName(); }
                        long d1 = ObjectSizes.measureDeep(t);
                        System.out.println(bt + "\t" + L + "\t" + path + "\t" + rep + "\t" + len0 + "\t" + t.applyState.data.length + "\t"
                                           + on0 + "\t" + t.sizeOnHeap() + "\t" + off0 + "\t" + t.sizeOffHeap() + "\t" + d0 + "\t" + d1 + "\t" + status);
                    }
            }
    }

    static void bulk(int n, int keyLen) throws Exception
    {
        System.out.println("scenario\tstage\tdataLen\tsizeOnHeap\tallocatedPosThresholdReached\tdeep\tthresholdMB");
        String thr = System.getProperty("cassandra.memtable.row_overhead_size", "default");
        for (String scenario : new String[]{ "fresh", "afterLong65535" })
        {
            InMemoryTrie<Object> t = new InMemoryTrie<>(BufferType.ON_HEAP);
            if (scenario.equals("afterLong65535"))
                t.putSingleton(ByteComparable.fixedLength(randomKey(new Random(7), 65535)), new Object(), T);
            System.out.println(scenario + "\tbefore\t" + t.applyState.data.length + "\t" + t.sizeOnHeap() + "\t" + t.reachedAllocatedSizeThreshold()
                               + "\t" + ObjectSizes.measureDeep(t) + "\t" + thr);
            Random r = new Random(42);
            for (int i = 0; i < n; i++)
            {
                byte[] b = new byte[keyLen];
                r.nextBytes(b);
                t.putSingleton(ByteComparable.fixedLength(b), new Object(), T);
            }
            System.out.println(scenario + "\tafter\t" + t.applyState.data.length + "\t" + t.sizeOnHeap() + "\t" + t.reachedAllocatedSizeThreshold()
                               + "\t" + ObjectSizes.measureDeep(t) + "\t" + thr);
        }
    }

    static void depth(String csv)
    {
        System.out.println("K\tcomparableBytes\textra");
        for (String s : csv.split(","))
        {
            int K = Integer.parseInt(s.trim());
            DecoratedKey dk = Murmur3Partitioner.instance.decorateKey(ByteBuffer.wrap(randomKey(new Random(5 + K), K)));
            org.apache.cassandra.utils.bytecomparable.ByteSource bs = dk.asComparableBytes(V);
            int n = 0;
            while (bs.next() != org.apache.cassandra.utils.bytecomparable.ByteSource.END_OF_STREAM) n++;
            System.out.println(K + "\t" + n + "\t" + (n - K));
        }
    }
}
