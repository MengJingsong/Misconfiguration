/*
 * Stage-4 harness, case max_queue_weight-acquireWeight-weight--autonomous, unit tier (B2, as amended U1-U5 2026-10-27).
 * Copied into test/unit/org/apache/cassandra/utils/concurrent/ of the run clone; never committed to Cassandra.
 * Output: one "MQW ..." line per reading on stdout (build/test/logs/.../TEST-<class>.log).
 * Run with -Dtest.jvm.args=-Dcassandra.netty_use_heap_allocator=true (U2) and _JAVA_OPTIONS=-Xmx4g (U1).
 */
package org.apache.cassandra.utils.concurrent;

import java.nio.ByteBuffer;
import java.util.Arrays;
import java.util.concurrent.LinkedBlockingQueue;
import java.util.concurrent.TimeUnit;

import org.junit.BeforeClass;
import org.junit.Test;

import org.apache.cassandra.config.DatabaseDescriptor;
import org.apache.cassandra.cql3.QueryOptions;
import org.apache.cassandra.db.ConsistencyLevel;
import org.apache.cassandra.fql.FullQueryLogger;
import org.apache.cassandra.service.QueryState;
import org.apache.cassandra.transport.CBUtil;
import org.apache.cassandra.utils.ByteBufferUtil;

public class WeightedQueueCapTest
{
    static final String QSTR = "INSERT INTO ks.t (k,v) VALUES (?,?)";
    static final int[] MS = { 1 << 20, 8 << 20, 64 << 20, 256 << 20 };   // 1, 8, 64 MiB and the default 256 MiB (U2)

    @BeforeClass
    public static void setup()
    {
        DatabaseDescriptor.daemonInitialization();
        System.out.println("MQW ENV allocator=" + CBUtil.allocator.getClass().getName() + " useHeap=" + CBUtil.USE_HEAP_ALLOCATOR
                           + " maxMemory=" + Runtime.getRuntime().maxMemory());
    }

    static FullQueryLogger.Query query(int valueSize)
    {
        QueryOptions o = QueryOptions.forInternalCalls(ConsistencyLevel.ONE, Arrays.asList(ByteBufferUtil.bytes(1), ByteBuffer.allocate(valueSize)));
        return new FullQueryLogger.Query(QSTR, o, QueryState.forInternalCalls(), System.currentTimeMillis());
    }

    // Runbook-defect fix D1 (2026-10-27): the live heap is the heap pools' own after-GC usage (MemoryPoolMXBean.getCollectionUsage),
    // read right after the last of three System.gc() calls; Runtime used bytes after a sleep also counted what background threads
    // allocated in eden since the GC.
    static long usedAfterGC() throws InterruptedException
    {
        for (int i = 0; i < 3; i++)
        {
            if (i > 0) Thread.sleep(200);
            System.gc();
        }
        long used = 0;
        for (java.lang.management.MemoryPoolMXBean p : java.lang.management.ManagementFactory.getMemoryPoolMXBeans())
            if (p.getType() == java.lang.management.MemoryType.HEAP && p.getCollectionUsage() != null)
                used += p.getCollectionUsage().getUsed();
        return used;
    }

    static int permits(WeightedQueue<?> q)
    {
        return q.availableWeight.permits();
    }

    static String where(Throwable e)
    {
        for (StackTraceElement s : e.getStackTrace())
            if (s.getClassName().equals(WeightedQueue.class.getName()))
                return s.getMethodName() + ":" + s.getLineNumber();
        return "none";
    }

    @Test
    public void cap() throws Exception
    {
        for (int M : MS)
        {
            FullQueryLogger.Query probe = query(4096);
            int w = probe.weight();
            probe.release();
            int nOff = (int) ((2L * M + w - 1) / w);
            WeightedQueue<FullQueryLogger.Query> wq = new WeightedQueue<>(M);
            long h0 = usedAfterGC();
            int nAcc = 0, firstFalse = -1, trueAfterFalse = 0, wmin = Integer.MAX_VALUE, wmax = 0;
            long W = 0;
            for (int i = 0; i < nOff; i++)
            {
                FullQueryLogger.Query q = query(4096);
                int wi = q.weight();
                wmin = Math.min(wmin, wi); wmax = Math.max(wmax, wi);
                boolean ok = wq.offer(q);
                if (ok)
                {
                    nAcc++; W += wi;
                    if (firstFalse >= 0) trueAfterFalse++;
                }
                else
                {
                    q.release();
                    if (firstFalse < 0) firstFalse = i;
                }
            }
            int p = permits(wq);
            long h1 = usedAfterGC();
            long dH = h1 - h0;
            System.out.println(String.format("MQW CAP M=%d w=%d wmin=%d wmax=%d nOff=%d nAcc=%d W=%d permits=%d firstFalse=%d trueAfterFalse=%d floorMw=%d MminusW=%d h0=%d h1=%d dH=%d dHoverW=%.4f",
                                             M, w, wmin, wmax, nOff, nAcc, W, p, firstFalse, trueAfterFalse, M / w, M - W, h0, h1, dH, (double) dH / W));
            FullQueryLogger.Query q;
            int drained = 0;
            while ((q = wq.poll()) != null) { q.release(); drained++; }
            System.out.println(String.format("MQW CAPDRAIN M=%d drained=%d permits=%d", M, drained, permits(wq)));
        }
    }

    @Test
    public void controls() throws Exception
    {
        int Mmax = MS[MS.length - 1];
        FullQueryLogger.Query probe = query(4096);
        int w = probe.weight();
        probe.release();
        int nOff = (int) ((2L * Mmax + w - 1) / w);

        // B2h control 1: WeightedQueue with M = Integer.MAX_VALUE, the same offers as the largest M; heap after each quarter
        WeightedQueue<FullQueryLogger.Query> wq = new WeightedQueue<>(Integer.MAX_VALUE);
        long h0 = usedAfterGC();
        int nAcc = 0; long W = 0;
        StringBuilder quarters = new StringBuilder();
        for (int i = 0; i < nOff; i++)
        {
            FullQueryLogger.Query q = query(4096);
            int wi = q.weight();
            if (wq.offer(q)) { nAcc++; W += wi; } else q.release();
            if ((i + 1) % (nOff / 4) == 0 && quarters.length() < 200)
                quarters.append(i + 1).append(':').append(usedAfterGC() - h0).append(',');
        }
        long dH = usedAfterGC() - h0;
        System.out.println(String.format("MQW CTRLMAX M=%d w=%d nOff=%d nAcc=%d W=%d permits=%d dH=%d dHoverW=%.4f quarters=%s",
                                         Integer.MAX_VALUE, w, nOff, nAcc, W, permits(wq), dH, (double) dH / W, quarters));
        FullQueryLogger.Query q;
        while ((q = wq.poll()) != null) q.release();
        wq = null;

        // B2h control 2: plain LinkedBlockingQueue, same records: per-record heap cost
        LinkedBlockingQueue<FullQueryLogger.Query> lbq = new LinkedBlockingQueue<>();
        h0 = usedAfterGC();
        W = 0;
        for (int i = 0; i < nOff; i++)
        {
            FullQueryLogger.Query r = query(4096);
            W += r.weight();
            lbq.offer(r);
        }
        dH = usedAfterGC() - h0;
        System.out.println(String.format("MQW CTRLLBQ n=%d W=%d dH=%d perRecord=%.1f dHoverW=%.4f", lbq.size(), W, dH, (double) dH / lbq.size(), (double) dH / W));
        while ((q = lbq.poll()) != null) q.release();
    }

    @Test
    public void overweight() throws Exception
    {
        int M = 64 << 10;
        WeightedQueue<FullQueryLogger.Query> wq = new WeightedQueue<>(M);
        FullQueryLogger.Query big = query(128 << 10);
        int wb = big.weight();
        boolean first = wq.offer(big);
        int p1 = permits(wq);
        FullQueryLogger.Query small = query(4096);
        int ws = small.weight();
        boolean second = wq.offer(small);
        if (!second) small.release();
        int p2 = permits(wq);
        FullQueryLogger.Query out = wq.poll();
        int p3 = permits(wq);
        if (out != null) out.release();
        System.out.println(String.format("MQW OVER M=%d wbig=%d first=%s permitsAfterFirst=%d wsmall=%d second=%s permitsAfterSecond=%d polledBig=%s permitsAfterPoll=%d",
                                         M, wb, first, p1, ws, second, p2, out == big, p3));
    }

    static class Fixed implements WeightedQueue.Weighable
    {
        final int w;
        Fixed(int w) { this.w = w; }
        public int weight() { return w; }
        public String toString() { return "Fixed(" + w + ")"; }
    }

    static class Mutable implements WeightedQueue.Weighable
    {
        volatile int w = 5;
        public int weight() { return w; }
        public String toString() { return "Mutable(" + w + ")"; }
    }

    @Test
    public void guards() throws Exception
    {
        int M = 1 << 20;
        for (int bad : new int[]{ 0, -1 })
        {
            for (String path : new String[]{ "offer", "offerTimed", "put" })
            {
                WeightedQueue<Object> wq = new WeightedQueue<>(M);
                String res = "accepted";
                try
                {
                    boolean r;
                    if (path.equals("offer")) r = wq.offer(new Fixed(bad));
                    else if (path.equals("offerTimed")) r = wq.offer(new Fixed(bad), 1, TimeUnit.SECONDS);
                    else { wq.put(new Fixed(bad)); r = true; }
                    res = "returned=" + r;
                }
                catch (IllegalArgumentException e)
                {
                    res = "IAE at=" + where(e) + " msg=[" + e.getMessage() + "]";
                }
                System.out.println(String.format("MQW GUARD weight=%d path=%s result=%s permits=%d M=%d", bad, path, res, permits(wq), M));
            }
        }
    }

    @Test
    public void leak() throws Exception
    {
        int M = 1 << 20;
        WeightedQueue<Object> wq = new WeightedQueue<>(M);
        Mutable m = new Mutable();
        boolean ok = wq.offer(m);
        int p1 = permits(wq);
        m.w = 0;
        String res = "no exception";
        try
        {
            Object o = wq.poll();
            res = "returned=" + o;
        }
        catch (IllegalArgumentException e)
        {
            res = "IAE at=" + where(e);
        }
        int p2 = permits(wq);
        Object next = wq.poll();
        int p3 = permits(wq);
        System.out.println(String.format("MQW LEAK M=%d offer=%s permitsAfterOffer=%d poll=%s permitsAfterPoll=%d nextPoll=%s permitsAfterNext=%d",
                                         M, ok, p1, res, p2, next, p3));
    }
}
