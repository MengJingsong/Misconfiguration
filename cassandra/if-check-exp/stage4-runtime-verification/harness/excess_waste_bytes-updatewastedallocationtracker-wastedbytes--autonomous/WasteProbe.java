package org.apache.cassandra.db.partitions;

import java.io.FileWriter;
import java.io.PrintWriter;
import java.lang.management.ManagementFactory;
import java.lang.reflect.Field;
import java.lang.reflect.Method;
import java.nio.ByteBuffer;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;
import java.util.TreeSet;
import java.util.concurrent.CyclicBarrier;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;

import org.apache.cassandra.config.Config;
import org.apache.cassandra.config.DatabaseDescriptor;
import org.apache.cassandra.db.DecoratedKey;
import org.apache.cassandra.db.DeletionTime;
import org.apache.cassandra.db.RangeTombstone;
import org.apache.cassandra.db.marshal.BytesType;
import org.apache.cassandra.db.marshal.Int32Type;
import org.apache.cassandra.db.memtable.AbstractAllocatorMemtable;
import org.apache.cassandra.db.rows.Row;
import org.apache.cassandra.index.transactions.UpdateTransaction;
import org.apache.cassandra.schema.TableMetadata;
import org.apache.cassandra.schema.TableMetadataRef;
import org.apache.cassandra.utils.ByteBufferUtil;
import org.apache.cassandra.utils.concurrent.ImmediateFuture;
import org.apache.cassandra.utils.concurrent.OpOrder;
import org.apache.cassandra.utils.memory.Cloner;
import org.apache.cassandra.utils.memory.MemtableAllocator;
import org.apache.cassandra.utils.memory.MemtableCleaner;
import org.apache.cassandra.utils.memory.MemtablePool;

/**
 * Stage-4 unit-tier probe for the four EXCESS_WASTE_* cases (AtomicBTreePartition), written 2026-10-28. Plain main(), run through the
 * java launcher by unit-run.sh. Package org.apache.cassandra.db.partitions so that BTreePartitionUpdater.heapSize is readable.
 * usage: WasteProbe <out-file> <mode>[,<mode>...]   modes: direct burst refill stream account cont control
 * Every result is one line "PROBE <kind> k=v ..." in <out-file> (and on stdout). The constant and its offset are read from the loaded
 * class by reflection, so the same code runs on every patched build (class directory put first on the class path).
 */
public class WasteProbe
{
    static PrintWriter out;
    static Method M;
    static Field TRK;
    static long C;
    static int OFF;
    static TableMetadata md;
    static TableMetadataRef ref;
    static final long MAX = Integer.MAX_VALUE;
    static final com.sun.management.ThreadMXBean TMX = (com.sun.management.ThreadMXBean) ManagementFactory.getThreadMXBean();

    static synchronized void p(String s)
    {
        out.println("PROBE " + s);
        out.flush();
        System.out.println("PROBE " + s);
    }

    static long s4(String f)
    {
        try
        {
            Class<?> c = Class.forName("org.apache.cassandra.db.partitions.S4Waste");
            Object adder = c.getField(f).get(null);
            return (Long) adder.getClass().getMethod("sum").invoke(adder);
        }
        catch (Throwable t)
        {
            return -1;
        }
    }

    static DecoratedKey key(int i)
    {
        return DatabaseDescriptor.getPartitioner().decorateKey(ByteBufferUtil.bytes(i));
    }

    static AtomicBTreePartition fresh()
    {
        return new AtomicBTreePartition(ref, key(0), null);
    }

    static boolean call(AtomicBTreePartition part, long w) throws Exception
    {
        return (Boolean) M.invoke(part, w);
    }

    static int tracker(AtomicBTreePartition part) throws Exception
    {
        return TRK.getInt(part);
    }

    static long units(long w)
    {
        return (w + 1023) / 1024;
    }

    public static void main(String[] a) throws Exception
    {
        out = new PrintWriter(new FileWriter(a[0], true));
        DatabaseDescriptor.daemonInitialization();
        md = TableMetadata.builder("ks", "t").addPartitionKeyColumn("pk", Int32Type.instance)
                          .addClusteringColumn("ck", Int32Type.instance).addRegularColumn("v", BytesType.instance).build();
        ref = TableMetadataRef.forOfflineTools(md);
        M = AtomicBTreePartition.class.getDeclaredMethod("updateWastedAllocationTracker", long.class);
        M.setAccessible(true);
        TRK = AtomicBTreePartition.class.getDeclaredField("wasteTracker");
        TRK.setAccessible(true);
        Field fc = AtomicBTreePartition.class.getDeclaredField("EXCESS_WASTE_BYTES"), fo = AtomicBTreePartition.class.getDeclaredField("EXCESS_WASTE_OFFSET");
        fc.setAccessible(true);
        fo.setAccessible(true);
        C = fc.getLong(null);
        OFF = fo.getInt(null);
        p("config C=" + C + " OFFSET=" + OFF + " instrumented=" + (s4("attempts") >= 0) + " loadedFrom="
          + AtomicBTreePartition.class.getProtectionDomain().getCodeSource().getLocation());
        for (String m : a[1].split(","))
        {
            switch (m)
            {
                case "direct": direct(); break;
                case "burst": burst(); break;
                case "refill": refill(); break;
                case "stream": stream(); break;
                case "account": account(); break;
                case "cont": cont(); break;
                case "control": control(); break;
                case "memo": memo(); break;
                default: throw new IllegalArgumentException(m);
            }
        }
        p("done");
        out.close();
        System.exit(0);
    }

    // ---- direct sweep of the operand (first call on a fresh partition) ----
    static void direct() throws Exception
    {
        TreeSet<Long> ws = new TreeSet<>(Arrays.asList(0L, 1L, 1024L, 1025L, C - 2048, C - 1024, C - 1023, C - 1, C, C + 1, 2 * C, 64L << 20));
        for (long w : ws)
        {
            if (w < 0 || w > (1L << 41)) continue;
            AtomicBTreePartition part = fresh();
            boolean ret = call(part, w);
            int t = tracker(part);
            p("direct w=" + w + " ret=" + ret + " useLock=" + part.useLock() + " tracker=" + t + " sentinel=" + (t == MAX) + " units=" + units(w));
        }
        // latch: once true it stays true
        AtomicBTreePartition part = fresh();
        call(part, C);
        boolean allTrue = true;
        for (int i = 0; i < 10; i++) allTrue &= call(part, 1) && part.useLock();
        p("latch afterSentinelTenCallsOfOneByte=" + allTrue);
    }

    // ---- calls until the first true, back to back and with a gap ----
    static void burstOne(String label, long w, long gapMs, long maxCalls, long maxNs) throws Exception
    {
        AtomicBTreePartition part = fresh();
        long t0 = System.nanoTime();
        long calls = 0;
        boolean locked = false;
        while (calls < maxCalls && System.nanoTime() - t0 < maxNs)
        {
            calls++;
            if (call(part, w)) { locked = true; break; }
            if (gapMs > 0) Thread.sleep(gapMs);
        }
        long el = System.nanoTime() - t0;
        long u = units(w);
        long formula = w >= C ? 1 : (OFF + u - 1) / u;
        p("burst label=" + label + " w=" + w + " units=" + u + " gapMs=" + gapMs + " calls=" + calls + " elapsedNs=" + el + " locked=" + locked
          + " useLock=" + part.useLock() + " formulaCalls=" + formula + " creditUnits=" + (el >> 17) + " OFFSET=" + OFF);
    }

    static void burst() throws Exception
    {
        long[] ws = {1, 1024, 100 * 1024, 1 << 20, C / 8, C - 1024};
        for (long w : ws)
            if (w > 0) burstOne("gap0", w, 0, 5_000_000, 3_000_000_000L);
        for (long gap : new long[]{1, 10, 100})
            for (long w : new long[]{1024, 100 * 1024, 1 << 20})
                burstOne("gap" + gap, w, gap, 100_000, 4_000_000_000L);
        // k reports of C/8 back to back on a fresh partition each (does it lock at k?)
        for (int k : new int[]{6, 7, 8, 9, 10})
        {
            AtomicBTreePartition part = fresh();
            boolean r = false;
            for (int i = 0; i < k; i++) r = call(part, C / 8);
            p("burstk w=" + (C / 8) + " k=" + k + " lastRet=" + r + " useLock=" + part.useLock());
        }
    }

    static void refill() throws Exception
    {
        long w = C - 1024;
        for (long gap : new long[]{0, 500, 1500})
        {
            AtomicBTreePartition part = fresh();
            boolean r1 = call(part, w);
            if (gap > 0) Thread.sleep(gap);
            boolean r2 = call(part, w);
            p("refill w=" + w + " gapMs=" + gap + " first=" + r1 + " second=" + r2 + " windowMs=" + (OFF * 131072L / 1_000_000L));
        }
    }

    static void stream() throws Exception
    {
        Object[][] cfg = {{1024L, 1L, 5000}, {8192L, 2L, 200}, {16384L, 1L, 5000}, {4096L, 1L, 5000}};
        for (Object[] c : cfg)
        {
            long w = (Long) c[0], gap = (Long) c[1];
            int n = (Integer) c[2];
            AtomicBTreePartition part = fresh();
            long t0 = System.nanoTime();
            int i = 0;
            boolean locked = false;
            for (; i < n; i++)
            {
                if (call(part, w)) { locked = true; i++; break; }
                Thread.sleep(gap);
            }
            long el = System.nanoTime() - t0;
            p("stream w=" + w + " gapMs=" + gap + " calls=" + i + " maxCalls=" + n + " locked=" + locked + " elapsedNs=" + el
              + " rateKiBperMs=" + String.format("%.2f", (w / 1024.0) * i / (el / 1e6)) + " allowanceKiBperMs=7.63");
        }
    }

    // ---- accounting ----
    static MemtablePool pool(Config.MemtableAllocationType t, long heap, long off, float th, AtomicInteger cleaned)
    {
        MemtableCleaner cl = () -> { cleaned.incrementAndGet(); return ImmediateFuture.success(false); };
        return AbstractAllocatorMemtable.createMemtableAllocatorPoolInternal(t, heap, off, th, cl);
    }

    static PartitionUpdate upd(int ckStart, int rows, int vb)
    {
        PartitionUpdate.SimpleBuilder b = PartitionUpdate.simpleBuilder(md, 0).timestamp(1000);
        byte[] v = new byte[vb];
        for (int i = 0; i < rows; i++)
            b.row(ckStart + i).add("v", ByteBuffer.wrap(v));
        return b.build();
    }

    static class Hook implements UpdateTransaction
    {
        final Runnable once;
        boolean fired;
        Hook(Runnable once) { this.once = once; }
        public void start() { }
        public void onPartitionDeletion(DeletionTime d) { }
        public void onRangeTombstone(RangeTombstone r) { }
        public void onInserted(Row row) { if (!fired) { fired = true; once.run(); } }
        public void onUpdated(Row e, Row u) { }
        public void commit() { }
    }

    static class Env
    {
        final MemtablePool pool;
        final MemtableAllocator alloc;
        final OpOrder ord = new OpOrder();
        final AtomicBTreePartition part;
        final AtomicInteger cleaned = new AtomicInteger();

        Env(Config.MemtableAllocationType t, long heap, long off)
        {
            pool = pool(t, heap, off, 0.9f, cleaned);
            alloc = pool.newAllocator("probe");
            part = new AtomicBTreePartition(ref, key(0), alloc);
        }

        BTreePartitionUpdater add(PartitionUpdate u, UpdateTransaction tx)
        {
            try (OpOrder.Group g = ord.start())
            {
                return part.addAll(u, alloc.cloner(g), g, tx);
            }
        }

        // one forced failed CAS: the nested write changes ref inside the outer merge (first onInserted only)
        BTreePartitionUpdater fail(PartitionUpdate outer, PartitionUpdate nested)
        {
            try (OpOrder.Group g = ord.start())
            {
                Cloner cl = alloc.cloner(g);
                Hook h = new Hook(() -> part.addAll(nested, cl, g, UpdateTransaction.NO_OP));
                return part.addAll(outer, cl, g, h);
            }
        }

        long on() { return alloc.onHeap().owns(); }
        long off() { return alloc.offHeap().owns(); }

        void close()
        {
            alloc.setDiscarding();
            alloc.setDiscarded();
            try { pool.shutdownAndWait(1, TimeUnit.SECONDS); } catch (Throwable t) { }
        }
    }

    static int rowsFor(long targetHeap, int vb, Config.MemtableAllocationType t) throws Exception
    {
        Env e = new Env(t, 1L << 30, 1L << 30);
        BTreePartitionUpdater u = e.add(upd(0, 2000, vb), UpdateTransaction.NO_OP);
        long per = Math.max(1, u.heapSize / 2000);
        e.close();
        return (int) Math.max(1, targetHeap / per);
    }

    static void account() throws Exception
    {
        for (Config.MemtableAllocationType t : new Config.MemtableAllocationType[]{ Config.MemtableAllocationType.heap_buffers, Config.MemtableAllocationType.offheap_objects })
        {
            String T = t.name();
            int vb = 100;
            // calibration
            Env e0 = new Env(t, 1L << 30, 1L << 30);
            BTreePartitionUpdater u0 = e0.add(upd(0, 2000, vb), UpdateTransaction.NO_OP);
            p("calib type=" + T + " rows=2000 vb=" + vb + " heapSize=" + u0.heapSize + " dataSize=" + u0.dataSize + " ownsOn=" + e0.on() + " ownsOff=" + e0.off()
              + " heapPerRow=" + (u0.heapSize / 2000));
            e0.close();
            // single forced failure at several waste sizes
            for (double f : new double[]{0.5, 1.2})
            {
                long target = (long) (f * C);
                if (target > (96L << 20)) { p("fail type=" + T + " factor=" + f + " skipped=target>" + (96 << 20)); continue; }
                int rows = rowsFor(target, vb, t);
                Env F = new Env(t, 1L << 30, 1L << 30);
                long f0 = s4("fails"), fh0 = s4("failHeap");
                BTreePartitionUpdater u = F.fail(upd(1_000_000, rows, vb), upd(5_000_000, 1, vb));
                int tr = tracker(F.part);
                long fails = s4("fails") - f0, failHeap = s4("failHeap") - fh0;
                Env R = new Env(t, 1L << 30, 1L << 30);
                R.add(upd(5_000_000, 1, vb), UpdateTransaction.NO_OP);
                R.add(upd(1_000_000, rows, vb), UpdateTransaction.NO_OP);
                p("fail type=" + T + " factor=" + f + " rows=" + rows + " targetW=" + target + " measuredW=" + (fails > 0 ? failHeap / fails : -1) + " fails=" + fails
                  + " retryHeapSize=" + u.heapSize + " tracker=" + tr + " sentinel=" + (tr == MAX) + " useLock=" + F.part.useLock()
                  + " ownsOn=" + F.on() + " ownsOff=" + F.off() + " refOwnsOn=" + R.on() + " refOwnsOff=" + R.off()
                  + " excessOn=" + (F.on() - R.on()) + " excessOff=" + (F.off() - R.off()) + " payloadOfFailedAttempt=" + ((long) rows * vb));
                F.close();
                R.close();
            }
            // K failures of about 1 MiB back to back on one partition
            {
                int rows = rowsFor(1 << 20, vb, t);
                Env F = new Env(t, 1L << 30, 1L << 30);
                for (int k = 1; k <= 12; k++)
                {
                    long f0 = s4("fails"), fh0 = s4("failHeap");
                    F.fail(upd(1_000_000 + k * 100_000, rows, vb), upd(9_000_000 + k, 1, vb));
                    long fl = s4("fails") - f0;
                    p("seqc type=" + T + " k=" + k + " rows=" + rows + " measuredW=" + (fl > 0 ? (s4("failHeap") - fh0) / fl : -1) + " tracker=" + tracker(F.part)
                      + " useLock=" + F.part.useLock());
                }
                F.close();
            }
            // 200 failures of 8 KiB, 2 ms apart
            {
                int rows = rowsFor(8192, vb, t);
                Env F = new Env(t, 1L << 30, 1L << 30);
                int firstLock = -1;
                long t0 = System.nanoTime();
                for (int k = 1; k <= 200; k++)
                {
                    F.fail(upd(1_000_000 + k * 1000, rows, vb), upd(9_000_000 + k, 1, vb));
                    if (firstLock < 0 && F.part.useLock()) firstLock = k;
                    Thread.sleep(2);
                }
                long el = System.nanoTime() - t0;
                p("seqd type=" + T + " failures=200 rows=" + rows + " firstLock=" + firstLock + " useLock=" + F.part.useLock() + " elapsedMs=" + el / 1_000_000
                  + " ownsOn=" + F.on() + " ownsOff=" + F.off());
                F.close();
            }
            // hook off: tracker stays 0
            {
                Env F = new Env(t, 1L << 30, 1L << 30);
                for (int k = 0; k < 50; k++) F.add(upd(k * 10, 5, vb), UpdateTransaction.NO_OP);
                p("nohook type=" + T + " tracker=" + tracker(F.part) + " useLock=" + F.part.useLock());
                F.close();
            }
            // sentinel vs not, same 1000 uncontended updates
            {
                Env S = new Env(t, 1L << 30, 1L << 30), N = new Env(t, 1L << 30, 1L << 30);
                TRK.setInt(S.part, (int) MAX);
                long dS = 0, dN = 0, hS = 0, hN = 0;
                for (int k = 0; k < 1000; k++)
                {
                    BTreePartitionUpdater us = S.add(upd(k * 5, 5, vb), UpdateTransaction.NO_OP), un = N.add(upd(k * 5, 5, vb), UpdateTransaction.NO_OP);
                    dS += us.dataSize; dN += un.dataSize; hS += us.heapSize; hN += un.heapSize;
                }
                p("sentinel type=" + T + " sentinelOwnsOn=" + S.on() + " sentinelOwnsOff=" + S.off() + " normalOwnsOn=" + N.on() + " normalOwnsOff=" + N.off()
                  + " dataSizeS=" + dS + " dataSizeN=" + dN + " heapSizeS=" + hS + " heapSizeN=" + hN + " useLockS=" + S.part.useLock() + " useLockN=" + N.part.useLock());
                S.close();
                N.close();
            }
        }
    }

    // ---- contention: T threads on one partition vs the same updates applied by one thread ----
    static void cont() throws Exception
    {
        Object[][] cfgs = {{"c1", 8, 1000, 1, 100, 5, Config.MemtableAllocationType.heap_buffers},
                           {"c1o", 8, 1000, 1, 100, 3, Config.MemtableAllocationType.offheap_objects},
                           {"c3", 16, 60, 1, 65536, 3, Config.MemtableAllocationType.heap_buffers}};
        for (Object[] c : cfgs)
        {
            String label = (String) c[0];
            int threads = (Integer) c[1], per = (Integer) c[2], rowsPer = (Integer) c[3], vb = (Integer) c[4], reps = (Integer) c[5];
            Config.MemtableAllocationType t = (Config.MemtableAllocationType) c[6];
            Env B = new Env(t, 1L << 30, 1L << 30);
            for (int th = 0; th < threads; th++)
                for (int i = 0; i < per; i++)
                    B.add(upd((th * per + i) * rowsPer, rowsPer, vb), UpdateTransaction.NO_OP);
            p("cont label=" + label + " run=single type=" + t + " threads=1 updates=" + threads * per + " ownsOn=" + B.on() + " ownsOff=" + B.off() + " useLock=" + B.part.useLock());
            B.close();
            for (int r = 1; r <= reps; r++)
            {
                final Env E = new Env(t, 1L << 30, 1L << 30);
                final PartitionUpdate[][] ups = new PartitionUpdate[threads][per];
                for (int th = 0; th < threads; th++)
                    for (int i = 0; i < per; i++)
                        ups[th][i] = upd((th * per + i) * rowsPer, rowsPer, vb);
                CyclicBarrier bar = new CyclicBarrier(threads + 1);
                final long[] alloc = new long[threads];
                List<Thread> ts = new ArrayList<>();
                for (int th = 0; th < threads; th++)
                {
                    final int id = th;
                    final int perF = per;
                    Thread x = new Thread(() -> {
                        try
                        {
                            bar.await();
                            long a0 = TMX.getThreadAllocatedBytes(Thread.currentThread().getId());
                            for (int i = 0; i < perF; i++) E.add(ups[id][i], UpdateTransaction.NO_OP);
                            alloc[id] = TMX.getThreadAllocatedBytes(Thread.currentThread().getId()) - a0;
                        }
                        catch (Throwable e) { e.printStackTrace(); }
                    });
                    ts.add(x);
                    x.start();
                }
                long a0 = s4("attempts"), f0 = s4("fails"), fh0 = s4("failHeap"), la0 = s4("lockedAttempts"), lf0 = s4("lockedFails"), fl0 = s4("flips");
                bar.await();
                long t0 = System.nanoTime();
                for (Thread x : ts) x.join();
                long el = System.nanoTime() - t0;
                long sum = 0;
                for (long v : alloc) sum += v;
                p("cont label=" + label + " run=" + r + " type=" + t + " threads=" + threads + " updates=" + threads * per + " ownsOn=" + E.on() + " ownsOff=" + E.off()
                  + " useLock=" + E.part.useLock() + " elapsedMs=" + el / 1_000_000 + " threadAllocBytes=" + sum + " attempts=" + (s4("attempts") - a0)
                  + " fails=" + (s4("fails") - f0) + " failHeap=" + (s4("failHeap") - fh0) + " lockedAttempts=" + (s4("lockedAttempts") - la0)
                  + " lockedFails=" + (s4("lockedFails") - lf0) + " flips=" + (s4("flips") - fl0));
                E.close();
            }
        }
    }

    // ---- the tracker is one int: heap used does not grow with the amount of waste reported ----
    static void memo() throws Exception
    {
        AtomicBTreePartition part = fresh();
        System.gc(); System.gc();
        long u0 = Runtime.getRuntime().totalMemory() - Runtime.getRuntime().freeMemory();
        long total = 0;
        for (int i = 0; i < 3_000_000; i++)
        {
            long w = 1 + (i % 1000);
            total += w;
            call(part, w);
        }
        call(part, 64L << 20);
        System.gc(); System.gc();
        long u1 = Runtime.getRuntime().totalMemory() - Runtime.getRuntime().freeMemory();
        p("memo calls=3000001 reportedBytes=" + (total + (64L << 20)) + " heapUsedBefore=" + u0 + " heapUsedAfter=" + u1 + " deltaBytes=" + (u1 - u0) + " useLock=" + part.useLock());
    }

    // ---- positive control: a pool limit that binds (cleaner triggered when used exceeds limit x threshold) ----
    static void control() throws Exception
    {
        for (long limit : new long[]{8L << 20, 32L << 20})
        {
            for (Config.MemtableAllocationType t : new Config.MemtableAllocationType[]{ Config.MemtableAllocationType.heap_buffers, Config.MemtableAllocationType.offheap_objects, Config.MemtableAllocationType.unslabbed_heap_buffers })
            {
                AtomicInteger cleaned = new AtomicInteger();
                MemtablePool pl = pool(t, limit, limit, 0.5f, cleaned);
                MemtableAllocator al = pl.newAllocator("ctl");
                OpOrder ord = new OpOrder();
                int written = 0;
                for (int i = 0; i < 100_000 && cleaned.get() == 0; i++)
                {
                    AtomicBTreePartition part = new AtomicBTreePartition(ref, key(i), al);
                    try (OpOrder.Group g = ord.start())
                    {
                        part.addAll(upd(0, 4, 1024), al.cloner(g), g, UpdateTransaction.NO_OP);
                    }
                    written++;
                    if (written % 16 == 0) Thread.sleep(2);
                }
                Thread.sleep(300);
                p("control type=" + t + " limit=" + limit + " cleanThreshold=0.5 partitionsWritten=" + written + " cleanerCalls=" + cleaned.get() + " ownsOnAtFirstClean=" + al.onHeap().owns()
                  + " ownsOffAtFirstClean=" + al.offHeap().owns() + " limitTimesThreshold=" + (limit / 2));
                al.setDiscarding();
                al.setDiscarded();
                try { pl.shutdownAndWait(1, TimeUnit.SECONDS); } catch (Throwable x) { }
            }
        }
    }
}
