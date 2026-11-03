package stage4;

import java.lang.management.ManagementFactory;
import java.util.ArrayList;
import java.util.IdentityHashMap;
import java.util.List;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.AtomicLong;

/**
 * Stage-4 helper for the cluster re-run (B3d (6), amendment 2026-10-28) of
 * coordinator_read_size_fail_threshold-validateReadThresholds-fail--autonomous. Observation only: it changes no Cassandra state.
 *
 * In-flight replica bytes of keyspace ks, by event (no sampling):
 *  - a request is one SelectStatement.execute(QueryState, QueryOptions, RequestTime) call on ks, on the native-transport request
 *    thread (reqStart at entry, reqEnd at exit or exception exit);
 *  - bindCmd(cmd): AbstractReadExecutor.executeAsync on the request thread names the ReadCommand of the request's page;
 *  - built(len, cap): exit of ReadResponse$LocalDataResponse.build on the replica read thread (stashed per thread);
 *  - hold(cmd): exit of ReadCommand.createResponse / createEmptyResponse on the same read thread: the stashed buffer is held
 *    for that command; HELD grows by its capacity;
 *  - reqEnd releases the buffers of the commands bound to the request: HELD.getAndAdd(-held) returns HELD just before the release,
 *    so the largest value printed over all reqEnd lines is the exact peak of HELD (HELD only decreases at reqEnd);
 *    REQ.getAndDecrement() likewise gives the exact peak number of in-flight requests.
 *  - readStart at entry of LocalReadRunnable.runMayThrow (read thread); readEnd where the read hands its response or failure to the
 *    request's callback (ReadCallback.response / onFailure; changed 2026-10-28 after the shakedown, D2), with exception exit and exit as
 *    fall-backs: rsum = bytes allocated so far by every ks local read in flight (including this one), m = their number.
 * Lines (returned for traceln):
 *   inflight-req ms=<end> t0=<start> n=<requests in flight just before this end> H=<HELD just before this release> cmds=<bound>
 *                bufs=<held buffers released> held=<sum cap> len=<sum len> pending=<held records not yet released> orphans=<holds without a built buffer>
 *   inflight-read ms=<end> m=<ks local reads in flight incl. this one> rsum=<their allocated bytes so far> own=<this read's bytes>
 */
public final class InFlight
{
    private static final com.sun.management.ThreadMXBean TMX = (com.sun.management.ThreadMXBean) ManagementFactory.getThreadMXBean();

    private static final AtomicInteger REQ = new AtomicInteger();
    private static final AtomicLong HELD = new AtomicLong();
    private static final AtomicLong ORPHANS = new AtomicLong();
    private static final Map<Object, long[]> BYCMD = new IdentityHashMap<>();   // guarded by BYCMD; value {bufs, held, len}
    private static final ConcurrentHashMap<Long, Long> READS = new ConcurrentHashMap<>();

    private static final class Req
    {
        final long t0 = System.currentTimeMillis();
        final List<Object> cmds = new ArrayList<>(2);
    }

    private static final ThreadLocal<Req> CUR = new ThreadLocal<>();
    private static final ThreadLocal<long[]> BUILT = new ThreadLocal<>();

    public static void reqStart()
    {
        CUR.set(new Req());
        REQ.incrementAndGet();
    }

    public static void bindCmd(Object cmd)
    {
        Req r = CUR.get();
        if (r != null)
            r.cmds.add(cmd);
    }

    public static void built(long len, long cap)
    {
        BUILT.set(new long[]{ len, cap });
    }

    public static void hold(Object cmd)
    {
        long[] b = BUILT.get();
        BUILT.remove();
        if (b == null)
        {
            ORPHANS.incrementAndGet();
            return;
        }
        synchronized (BYCMD)
        {
            long[] rec = BYCMD.get(cmd);
            if (rec == null)
                BYCMD.put(cmd, rec = new long[3]);
            rec[0] += 1;
            rec[1] += b[1];
            rec[2] += b[0];
        }
        HELD.addAndGet(b[1]);
    }

    public static String reqEnd()
    {
        Req r = CUR.get();
        CUR.remove();
        long bufs = 0, held = 0, len = 0;
        int cmds = 0, pending;
        synchronized (BYCMD)
        {
            if (r != null)
            {
                cmds = r.cmds.size();
                for (Object c : r.cmds)
                {
                    long[] rec = BYCMD.remove(c);
                    if (rec != null)
                    {
                        bufs += rec[0];
                        held += rec[1];
                        len += rec[2];
                    }
                }
            }
            pending = BYCMD.size();
        }
        long h = HELD.getAndAdd(-held);
        int n = REQ.getAndDecrement();
        return "inflight-req ms=" + System.currentTimeMillis() + " t0=" + (r == null ? -1 : r.t0) + " n=" + n + " H=" + h + " cmds=" + cmds
               + " bufs=" + bufs + " held=" + held + " len=" + len + " pending=" + pending + " orphans=" + ORPHANS.get();
    }

    public static void readStart()
    {
        long id = Thread.currentThread().getId();
        READS.put(id, TMX.getThreadAllocatedBytes(id));
    }

    /** True if the calling thread has a ks local read registered by readStart and not yet ended (rule condition, D2). */
    public static boolean reading()
    {
        return READS.containsKey(Thread.currentThread().getId());
    }

    public static String readEnd()
    {
        long self = Thread.currentThread().getId();
        long own = -1, rsum = 0;
        int m = 0;
        for (Map.Entry<Long, Long> e : READS.entrySet())
        {
            long now = TMX.getThreadAllocatedBytes(e.getKey());
            if (now < 0)
                continue;
            long d = now - e.getValue();
            if (e.getKey() == self)
                own = d;
            rsum += d;
            m++;
        }
        READS.remove(self);
        return "inflight-read ms=" + System.currentTimeMillis() + " m=" + m + " rsum=" + rsum + " own=" + own;
    }
}
