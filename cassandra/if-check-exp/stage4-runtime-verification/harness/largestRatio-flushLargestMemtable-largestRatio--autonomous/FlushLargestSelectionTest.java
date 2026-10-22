/*
 * Stage-4 harness, case largestRatio-flushLargestMemtable-largestRatio--autonomous (B2, with audit amendments R2-R3).
 * Copied into test/unit/org/apache/cassandra/db/memtable/ of a local clone at cassandra-5.0.9. Not upstream code.
 *
 * u1Selection  - U1: three tables of about 2/4/6 MiB; the test's own argmax (strict >, from 0f, iteration order of
 *                ColumnFamilyStore.all(), ratio = max(on, off) of the memtable plus its index memtables, as :266-273)
 *                against the CFS whose memtable flushLargestMemtable() actually switched.
 * u2ZeroRatio  - U2: after flushing every CFS, flushLargestMemtable() once more (R3 and runbook fix D1: up to 20
 *                attempts, each flush-all, 1 s, flush-all, while some ratio is > 0 at the call).
 * u3CapSkew / u3CapEven - U3: 4 writer threads, 13,000 x L/32MiB rows each (R2), 1 KiB values; skew: all on T1, even:
 *                thread i on Ti. A sampler reads MEMORY_POOL.onHeap every 5 ms.
 * Result lines ("PROBE ...") go to System.out and are appended to the file named by -Dprobe.out. -Dprobe.mutant labels
 * the build (M-orig / M-first / M-never); it does not change behaviour.
 */
package org.apache.cassandra.db.memtable;

import java.io.FileWriter;
import java.io.IOException;
import java.io.PrintWriter;
import java.nio.ByteBuffer;
import java.util.ArrayList;
import java.util.IdentityHashMap;
import java.util.List;
import java.util.Map;
import java.util.Random;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.TimeoutException;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicLong;

import org.junit.Test;

import org.apache.cassandra.cql3.CQLTester;
import org.apache.cassandra.cql3.QueryProcessor;
import org.apache.cassandra.db.ColumnFamilyStore;
import org.apache.cassandra.db.Keyspace;
import org.apache.cassandra.utils.memory.MemtablePool;

public class FlushLargestSelectionTest extends CQLTester
{
    static final MemtablePool POOL = AbstractAllocatorMemtable.MEMORY_POOL;
    static final long MIB = 1L << 20;
    static final String MUTANT = System.getProperty("probe.mutant", "M-orig");
    static final String OUT = System.getProperty("probe.out", "");

    static synchronized void probe(String s)
    {
        String line = "PROBE " + s;
        System.out.println(line);
        if (!OUT.isEmpty())
        {
            try (PrintWriter w = new PrintWriter(new FileWriter(OUT, true)))
            {
                w.println(line);
            }
            catch (IOException e)
            {
                throw new RuntimeException(e);
            }
        }
    }

    static String name(ColumnFamilyStore cfs)
    {
        return cfs.keyspace.getName() + "." + cfs.name;
    }

    /** ratio exactly as AbstractAllocatorMemtable.java:266-273 computes it; -1 for a non-allocator memtable (skipped at :260) */
    static float ratioOf(Memtable m)
    {
        if (!(m instanceof AbstractAllocatorMemtable))
            return -1f;
        AbstractAllocatorMemtable cur = (AbstractAllocatorMemtable) m;
        Memtable.MemoryUsage usage = Memtable.newMemoryUsage();
        cur.addMemoryUsageTo(usage);
        for (Memtable im : cur.owner.getIndexMemtables())
            if (im instanceof AbstractAllocatorMemtable)
                im.addMemoryUsageTo(usage);
        return Math.max(usage.ownershipRatioOnHeap, usage.ownershipRatioOffHeap);
    }

    static void flushAll()
    {
        for (ColumnFamilyStore cfs : ColumnFamilyStore.all())
            cfs.forceBlockingFlush(ColumnFamilyStore.FlushReason.UNIT_TESTS);
    }

    static ColumnFamilyStore cfs(String table)
    {
        return Keyspace.open(KEYSPACE).getColumnFamilyStore(table);
    }

    static ByteBuffer value(Random r)
    {
        byte[] b = new byte[1024];
        r.nextBytes(b);
        return ByteBuffer.wrap(b);
    }

    static void insert(String table, int pk, int ck, ByteBuffer v)
    {
        QueryProcessor.executeInternal(String.format("INSERT INTO %s.%s (pk, ck, v) VALUES (?, ?, ?)", KEYSPACE, table), pk, ck, v);
    }

    String newTable()
    {
        String t = createTable("CREATE TABLE %s (pk int, ck int, v blob, PRIMARY KEY (pk, ck))");
        cfs(t).disableAutoCompaction();
        return t;
    }

    static class Snap
    {
        final List<ColumnFamilyStore> order = new ArrayList<>();
        final Map<ColumnFamilyStore, Memtable> mem = new IdentityHashMap<>();
        final Map<ColumnFamilyStore, Float> ratio = new IdentityHashMap<>();
        final Map<ColumnFamilyStore, Integer> sstables = new IdentityHashMap<>();
        ColumnFamilyStore argmax;
        float argmaxRatio = 0f;
        int nonZero;

        Snap()
        {
            for (ColumnFamilyStore c : ColumnFamilyStore.all())
            {
                Memtable m = c.getTracker().getView().getCurrentMemtable();
                float r = ratioOf(m);
                order.add(c);
                mem.put(c, m);
                ratio.put(c, r);
                sstables.put(c, c.getLiveSSTables().size());
                if (r > 0)
                    nonZero++;
                if (r > argmaxRatio)   // strict >, starting from 0f, as :251/:274
                {
                    argmax = c;
                    argmaxRatio = r;
                }
            }
        }

        List<String> changedSince(StringBuilder detail)
        {
            List<String> changed = new ArrayList<>();
            for (ColumnFamilyStore c : order)
            {
                if (c.getTracker().getView().getCurrentMemtable() != mem.get(c))
                {
                    changed.add(name(c));
                    detail.append(String.format(" %s:sstables%+d", name(c), c.getLiveSSTables().size() - sstables.get(c)));
                }
            }
            return changed;
        }
    }

    @Test
    public void u1Selection() throws Throwable
    {
        long L = POOL.onHeap.limit;
        String t1 = newTable(), t2 = newTable(), t3 = newTable();
        flushAll();
        Random r = new Random(1);
        int[] rows = { 1500, 3000, 4500 };
        String[] ts = { t1, t2, t3 };
        for (int k = 0; k < 3; k++)
            for (int i = 0; i < rows[k]; i++)
                insert(ts[k], i / 100, i % 100, value(r));

        Snap before = new Snap();
        StringBuilder top = new StringBuilder();
        before.order.stream().filter(c -> before.ratio.get(c) > 0)
                    .sorted((a, b) -> Float.compare(before.ratio.get(b), before.ratio.get(a))).limit(6)
                    .forEach(c -> top.append(String.format(" %s=%.5f", name(c), before.ratio.get(c))));
        probe(String.format("u1 mutant=%s L=%d T1=%s r1=%.5f T2=%s r2=%.5f T3=%s r3=%.5f nonzero=%d poolUsed=%d argmax=%s argmaxRatio=%.5f top=[%s ]",
                            MUTANT, L, t1, before.ratio.get(cfs(t1)), t2, before.ratio.get(cfs(t2)), t3, before.ratio.get(cfs(t3)),
                            before.nonZero, POOL.onHeap.used(), before.argmax == null ? "none" : name(before.argmax), before.argmaxRatio, top));

        Boolean result = AbstractAllocatorMemtable.flushLargestMemtable().get(120, TimeUnit.SECONDS);
        StringBuilder detail = new StringBuilder();
        List<String> changed = before.changedSince(detail);
        probe(String.format("u1-result mutant=%s result=%s changed=%s detail=[%s ] argmax=%s match=%s",
                            MUTANT, result, changed, detail, before.argmax == null ? "none" : name(before.argmax),
                            before.argmax != null && changed.size() == 1 && changed.get(0).equals(name(before.argmax))));
    }

    @Test
    public void u2ZeroRatio() throws Throwable
    {
        for (int attempt = 1; attempt <= 20; attempt++)   // runbook fix D1: up to 20 attempts
        {
            flushAll();
            Thread.sleep(1000);
            flushAll();
            Snap before = new Snap();
            StringBuilder nz = new StringBuilder();
            for (ColumnFamilyStore c : before.order)
                if (before.ratio.get(c) > 0)
                    nz.append(String.format(" %s=%.6f", name(c), before.ratio.get(c)));
            Boolean result = AbstractAllocatorMemtable.flushLargestMemtable().get(120, TimeUnit.SECONDS);
            StringBuilder detail = new StringBuilder();
            List<String> changed = before.changedSince(detail);
            probe(String.format("u2 mutant=%s attempt=%d nonzeroBefore=%d nonzero=[%s ] poolUsed=%d result=%s changed=%s valid=%s",
                                MUTANT, attempt, before.nonZero, nz, POOL.onHeap.used(), result, changed, before.nonZero == 0));
            if (before.nonZero == 0)
                return;
        }
    }

    @Test
    public void u3CapSkew() throws Throwable
    {
        u3("skew");
    }

    @Test
    public void u3CapEven() throws Throwable
    {
        u3("even");
    }

    void u3(String variant) throws Throwable
    {
        long L = POOL.onHeap.limit;
        final int threads = 4;
        final int rowsPerThread = (int) (13000L * L / (32 * MIB));
        String[] t = { newTable(), newTable(), newTable(), newTable() };
        flushAll();
        ColumnFamilyStore[] c = new ColumnFamilyStore[4];
        long[] sw0 = new long[4], bf0 = new long[4];
        for (int i = 0; i < 4; i++)
        {
            c[i] = cfs(t[i]);
            sw0[i] = c[i].metric.memtableSwitchCount.getCount();
            bf0[i] = c[i].metric.bytesFlushed.getCount();
        }
        long allSw0 = 0;
        for (ColumnFamilyStore x : ColumnFamilyStore.all())
            allSw0 += x.metric.memtableSwitchCount.getCount();
        long blocked0 = POOL.blockedOnAllocating.getCount();
        long used0 = POOL.onHeap.used();

        AtomicBoolean stop = new AtomicBoolean();
        AtomicLong peakUsed = new AtomicLong(), peakReclaiming = new AtomicLong(), samples = new AtomicLong(), overL = new AtomicLong();
        StringBuilder series = new StringBuilder();
        long tStart = System.nanoTime();
        Thread sampler = new Thread(() -> {
            long lastSeries = 0;
            while (!stop.get())
            {
                long u = POOL.onHeap.used(), rc = POOL.onHeap.getReclaiming();
                peakUsed.accumulateAndGet(u, Math::max);
                peakReclaiming.accumulateAndGet(rc, Math::max);
                if (u > L)
                    overL.incrementAndGet();
                samples.incrementAndGet();
                long ms = (System.nanoTime() - tStart) / 1_000_000;
                if (ms - lastSeries >= 250)
                {
                    series.append(String.format(" %d:%.4f/%.4f", ms, u / (double) L, rc / (double) L));
                    lastSeries = ms;
                }
                try { Thread.sleep(5); } catch (InterruptedException e) { return; }
            }
        }, "u3-sampler");
        sampler.setDaemon(true);
        sampler.start();

        ExecutorService[] ins = new ExecutorService[threads];
        Thread[] drivers = new Thread[threads];
        long[] done = new long[threads];
        boolean[] timedOut = new boolean[threads];
        for (int k = 0; k < threads; k++)
        {
            ins[k] = Executors.newSingleThreadExecutor();
            final int kk = k;
            final String table = variant.equals("skew") ? t[0] : t[k];
            drivers[k] = new Thread(() -> {
                Random r = new Random(100 + kk);
                for (int i = 0; i < rowsPerThread; i++)
                {
                    final int pk = (kk * 1_000_000 + i) / 100, ck = i % 100;
                    final ByteBuffer v = value(r);
                    Future<?> f = ins[kk].submit(() -> insert(table, pk, ck, v));
                    try
                    {
                        f.get(30, TimeUnit.SECONDS);
                        done[kk]++;
                    }
                    catch (TimeoutException e)
                    {
                        timedOut[kk] = true;
                        return;
                    }
                    catch (Exception e)
                    {
                        throw new RuntimeException(e);
                    }
                }
            }, "u3-driver-" + k);
            drivers[k].start();
        }
        for (Thread d : drivers)
            d.join();
        long wallMs = (System.nanoTime() - tStart) / 1_000_000;
        stop.set(true);
        sampler.join();
        // end of the measurement window; read the counters now
        long[] sw = new long[4], bf = new long[4];
        for (int i = 0; i < 4; i++)
        {
            sw[i] = c[i].metric.memtableSwitchCount.getCount() - sw0[i];
            bf[i] = c[i].metric.bytesFlushed.getCount() - bf0[i];
        }
        long allSw = 0;
        for (ColumnFamilyStore x : ColumnFamilyStore.all())
            allSw += x.metric.memtableSwitchCount.getCount();
        allSw -= allSw0;
        long blocked = POOL.blockedOnAllocating.getCount() - blocked0;
        int stopped = 0;
        long rowsDone = 0;
        for (int k = 0; k < threads; k++)
        {
            stopped += timedOut[k] ? 1 : 0;
            rowsDone += done[k];
        }
        long swTotal = sw[0] + sw[1] + sw[2] + sw[3], bfTotal = bf[0] + bf[1] + bf[2] + bf[3];
        probe(String.format("u3 mutant=%s variant=%s L=%d rowsPerThread=%d rowsDone=%d timedOutThreads=%d used0=%d peakUsed=%d peakRatio=%.4f peakReclaiming=%d samplesOverL=%d samples=%d switchesT=%d,%d,%d,%d switchesTestTotal=%d switchesAllCfs=%d bytesFlushedTotal=%d meanFlushBytes=%d blockedOnAllocating=%d wallMs=%d usedAtEnd=%d",
                            MUTANT, variant, L, rowsPerThread, rowsDone, stopped, used0, peakUsed.get(), peakUsed.get() / (double) L,
                            peakReclaiming.get(), overL.get(), samples.get(), sw[0], sw[1], sw[2], sw[3], swTotal, allSw, bfTotal,
                            swTotal == 0 ? 0 : bfTotal / swTotal, blocked, wallMs, POOL.onHeap.used()));
        probe(String.format("u3-series mutant=%s variant=%s L=%d used/L,reclaiming/L every 250 ms:%s", MUTANT, variant, L, series));

        // after the window: release writers blocked on the pool (M-never), so the JVM can end; not a reading
        if (stopped > 0)
            for (ColumnFamilyStore x : c)
                x.forceFlush(ColumnFamilyStore.FlushReason.UNIT_TESTS);
        for (ExecutorService e : ins)
        {
            e.shutdown();
            if (!e.awaitTermination(120, TimeUnit.SECONDS))
                probe("u3-cleanup executor did not terminate within 120 s");
        }
        flushAll();
    }
}
