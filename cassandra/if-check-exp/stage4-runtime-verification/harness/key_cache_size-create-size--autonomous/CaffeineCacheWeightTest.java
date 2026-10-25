package org.apache.cassandra.cache;

import java.io.FileWriter;
import java.io.PrintWriter;
import java.nio.ByteBuffer;
import java.util.concurrent.atomic.AtomicLong;
import java.util.concurrent.atomic.AtomicBoolean;

import org.junit.Test;

import org.apache.cassandra.db.marshal.UTF8Type;
import org.apache.cassandra.io.sstable.Descriptor;
import org.apache.cassandra.io.sstable.SequenceBasedSSTableId;
import org.apache.cassandra.io.sstable.format.big.RowIndexEntry;
import org.apache.cassandra.io.util.File;
import org.apache.cassandra.schema.TableMetadata;
import org.apache.cassandra.utils.ByteBufferUtil;

/**
 * Stage-4 harness for key_cache_size-create-size--autonomous (unit tier, B2).
 * Records measurements as key=value lines in $STAGE4_OUT/unit.txt; the verdict is made by analyze_unit.py, not here.
 * The production weigher is exercised through CaffeineCache.create(long) (the target line CaffeineCache.java:65).
 */
public class CaffeineCacheWeightTest
{
    static final long MIB = 1024 * 1024;
    static final long W = 1024;
    static PrintWriter out;

    static final class K implements IMeasurableMemory
    {
        final long id; final long w;
        K(long id, long w) { this.id = id; this.w = w; }
        public long unsharedHeapSize() { return w; }
        public boolean equals(Object o) { return o instanceof K && ((K) o).id == id; }
        public int hashCode() { return Long.hashCode(id * 0x9E3779B97F4A7C15L); }
    }

    static final class V implements IMeasurableMemory
    {
        final long w;
        V(long w) { this.w = w; }
        public long unsharedHeapSize() { return w; }
    }

    static void rec(String s) { out.println(s); out.flush(); System.out.println("STAGE4 " + s); }

    static void settle(CaffeineCache<K, V> c) throws Exception
    {
        Thread.sleep(50);
        c.get(new K(-1, 0)); // a read schedules maintenance
        Thread.sleep(50);
    }

    @Test
    public void all() throws Exception
    {
        String dir = System.getenv().getOrDefault("STAGE4_OUT", "/tmp");
        out = new PrintWriter(new FileWriter(dir + "/unit.txt", false));
        try
        {
            fillArms();
            runtimeShrink();
            guard();
            controls();
            realClasses();
        }
        finally { out.close(); }
    }

    // B2c(1): N = 4*C/w distinct 1 KiB entries, from 1 and from 8 threads
    void fillArms() throws Exception
    {
        for (long capMiB : new long[]{ 1, 8, 64 })
            for (int threads : new int[]{ 1, 8 })
            {
                long cap = capMiB * MIB;
                final CaffeineCache<K, V> c = CaffeineCache.create(cap);
                final long n = 4 * cap / W;
                final AtomicLong maxW = new AtomicLong();
                final AtomicBoolean done = new AtomicBoolean();
                Thread sampler = new Thread(() -> { while (!done.get()) { long x = c.weightedSize(); maxW.accumulateAndGet(x, Math::max); } });
                sampler.start();
                Thread[] ts = new Thread[threads];
                for (int t = 0; t < threads; t++)
                {
                    final int tt = t; final int T = threads;
                    ts[t] = new Thread(() -> { for (long i = tt; i < n; i += T) c.put(new K(i, 0), new V(W)); });
                    ts[t].start();
                }
                for (Thread t : ts) t.join();
                long wImm = c.weightedSize(); int sImm = c.size();
                done.set(true); sampler.join();
                settle(c);
                rec(String.format("fill capMiB=%d threads=%d cap=%d puts=%d weightedSize_immediate=%d size_immediate=%d weightedSize_settled=%d size_settled=%d capacity=%d maxWeightedSizeSeenDuringPuts=%d",
                                  capMiB, threads, cap, n, wImm, sImm, c.weightedSize(), c.size(), c.capacity(), maxW.get()));
            }
    }

    // B2c(2): fill the 64 MiB cache, then setCapacity down to 8 MiB
    void runtimeShrink() throws Exception
    {
        long cap = 64 * MIB;
        CaffeineCache<K, V> c = CaffeineCache.create(cap);
        for (long i = 0; i < 4 * cap / W; i++) c.put(new K(i, 0), new V(W));
        settle(c);
        rec(String.format("shrink before capacity=%d weightedSize=%d size=%d", c.capacity(), c.weightedSize(), c.size()));
        c.setCapacity(8 * MIB);
        long wImm = c.weightedSize(); int sImm = c.size();
        settle(c);
        rec(String.format("shrink after capacity=%d weightedSize_immediate=%d size_immediate=%d weightedSize_settled=%d size_settled=%d", c.capacity(), wImm, sImm, c.weightedSize(), c.size()));
    }

    static void guardPut(CaffeineCache<K, V> c, String label, long kw, long vw)
    {
        K k = new K(1000 + label.hashCode(), kw);
        String ex = "none";
        try { c.put(k, new V(vw)); }
        catch (Throwable t) { ex = t.getClass().getName() + ":" + t.getMessage(); }
        boolean present = c.get(k) != null;
        rec(String.format("guard %s keyW=%d valueW=%d sum=%d exception=%s present=%b size=%d", label, kw, vw, kw + vw, ex, present, c.size()));
    }

    // B2c(3): weight at, below, above Integer.MAX_VALUE
    void guard() throws Exception
    {
        CaffeineCache<K, V> c = CaffeineCache.create(64 * MIB);
        long M = Integer.MAX_VALUE;
        guardPut(c, "below", 16, M - 16 - 1);
        guardPut(c, "sum_eq_max_key16", 16, M - 16);
        guardPut(c, "sum_eq_max_key0", 0, M);
        guardPut(c, "above_by1_key16", 16, M - 16 + 1);
        guardPut(c, "above_by1_key0", 0, M + 1);
        guardPut(c, "above_far", 0, 3L * M);
        // after a rejected put the cache must still work
        c.put(new K(7, 0), new V(W));
        settle(c);
        rec(String.format("guard after_rejects get_ok=%b size=%d", c.get(new K(7, 0)) != null, c.size()));
    }

    // B2h controls
    void controls() throws Exception
    {
        CaffeineCache<K, V> z = CaffeineCache.create(1 * MIB);
        for (long i = 0; i < 100000; i++) z.put(new K(i, 0), new V(0));
        settle(z);
        rec(String.format("control weight0 capacity=%d puts=100000 weightedSize=%d size=%d", z.capacity(), z.weightedSize(), z.size()));
        CaffeineCache<K, V> k = CaffeineCache.create(1000, (kk, vv) -> 1);
        for (long i = 0; i < 10000; i++) k.put(new K(i, 0), new V(W));
        settle(k);
        rec(String.format("control constweigher1 capacity=%d puts=10000(each 1KiB) weightedSize=%d size=%d", k.capacity(), k.weightedSize(), k.size()));
    }

    // weights of the real classes for a 24-byte key (calibrates the cluster arithmetic)
    void realClasses() throws Exception
    {
        try
        {
            org.apache.cassandra.config.DatabaseDescriptor.daemonInitialization();
            TableMetadata tm = TableMetadata.builder("ks", "t").addPartitionKeyColumn("pk", UTF8Type.instance).build();
            Descriptor d = new Descriptor(new File("/tmp"), "ks", "t", new SequenceBasedSSTableId(1));
            KeyCacheKey kk = new KeyCacheKey(tm, d, ByteBufferUtil.bytes("abcdefghijklmnopqrstuvwx"));
            RowIndexEntry e = new RowIndexEntry(12345L);
            CaffeineCache<KeyCacheKey, org.apache.cassandra.io.sstable.AbstractRowIndexEntry> c = CaffeineCache.create(1 * MIB);
            for (int i = 0; i < 200000; i++)
                c.put(new KeyCacheKey(tm, d, ByteBufferUtil.bytes(String.format("%024d", i))), e);
            settle2(c);
            rec(String.format("real KeyCacheKey_unsharedHeapSize=%d RowIndexEntry_unsharedHeapSize=%d sum=%d capacity=%d puts=200000 weightedSize=%d size=%d avgWeight=%.2f",
                              kk.unsharedHeapSize(), e.unsharedHeapSize(), kk.unsharedHeapSize() + e.unsharedHeapSize(), c.capacity(), c.weightedSize(), c.size(), (double) c.weightedSize() / c.size()));
        }
        catch (Throwable t) { rec("real FAILED " + t); }
    }

    static void settle2(CaffeineCache<?, ?> c) throws Exception { Thread.sleep(100); c.size(); Thread.sleep(100); }
}
